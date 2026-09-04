"""Minimal EE (R5900) execution harness on top of Unicorn (MIPS64 LE).

Unicorn cannot decode R5900-specific encodings (3-operand mult, MMI, lq/sq,
pipeline-1 mult/div, ei/di, cache, pref).  We pre-scan loaded code, replace
every such instruction with a `syscall` carrying an index in its code field,
and emulate the original instruction in the interrupt hook.  Upper 64 bits of
the 128-bit GPRs and the LO1/HI1 pipeline registers live in Python-side tables.
"""
import struct
from unicorn import *
from unicorn.mips_const import *
from unicorn.unicorn_py3.unicorn import uccallback, HOOK_MEM_ACCESS_CFUNC

GPR = [UC_MIPS_REG_0 + i for i in range(32)]
M64 = (1 << 64) - 1
M32 = (1 << 32) - 1
M128 = (1 << 128) - 1


def sext32(v):
    v &= M32
    return v - (1 << 32) if v & 0x80000000 else v


def sext16(v):
    v &= 0xffff
    return v - (1 << 16) if v & 0x8000 else v


def sext64(v):
    v &= M64
    return v - (1 << 64) if v & (1 << 63) else v


class EE:
    def __init__(self, ram_size=32 * 1024 * 1024, verbose=False):
        self.uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS64 | UC_MODE_LITTLE_ENDIAN)
        self.uc.ctl_set_cpu_model(UC_CPU_MIPS64_MIPS64R2_GENERIC)
        self.uc.mem_map(0, ram_size)
        self.uc.mem_map(0x70000000, 0x4000)          # scratchpad
        self.uc.mem_map(0x10000000, 0x10000)         # hardware regs (dummy)
        self.uc.mem_map(0x12000000, 0x10000)         # GS regs (dummy)
        self.ram_size = ram_size
        self.hi64 = [0] * 32                         # upper halves of 128-bit GPRs
        self.lo1 = 0
        self.hi1 = 0
        self.patched = {}                            # addr -> original insn
        self.verbose = verbose
        self.syscall_handlers = {}
        self.syscall_counts = {}
        self.syscall_limit = 2_000_000
        self.deferred = []
        self.skip_once = None
        self.tmp_restored = []
        self._keep = []
        self.data_reads = set()
        self.uc.hook_add(UC_HOOK_INTR, self._intr)
        self.uc.hook_add(UC_HOOK_MEM_UNMAPPED, self._unmapped)

    # ---- memory helpers
    def write(self, addr, data):
        self.uc.mem_write(addr, bytes(data))

    def read(self, addr, n):
        return bytes(self.uc.mem_read(addr, n))

    def r32(self, a):
        return struct.unpack('<I', self.read(a, 4))[0]

    def w32(self, a, v):
        self.write(a, struct.pack('<I', v & M32))

    def r64(self, a):
        return struct.unpack('<Q', self.read(a, 8))[0]

    def w64(self, a, v):
        self.write(a, struct.pack('<Q', v & M64))

    def reg(self, i):
        return self.uc.reg_read(GPR[i]) & M64 if i else 0

    def setreg(self, i, v):
        if i:
            self.uc.reg_write(GPR[i], v & M64)

    def reg128(self, i):
        return (self.hi64[i] << 64) | self.reg(i)

    def setreg128(self, i, v):
        if i:
            self.setreg(i, v & M64)
            self.hi64[i] = (v >> 64) & M64

    # ---- code loading / patching
    def load_code(self, addr, data):
        self.write(addr, data)
        return self.patch_range(addr, len(data))

    def patch_range(self, addr, size, exclude=()):
        """Replace R5900-only instructions in [addr, addr+size) with trap syscalls.
        `exclude` is a list of (start, end) ranges left untouched (e.g. encrypted code).
        An instruction sitting in a branch delay slot is handled by trapping the *branch*
        instead (QEMU misbehaves when an exception fires inside a delay slot); the handler
        then emulates the branch/slot pair."""
        data = bytearray(self.read(addr, size & ~3))
        n = 0
        for off in range(0, len(data), 4):
            a = addr + off
            if any(s <= a < e for s, e in exclude):
                continue
            w = struct.unpack_from('<I', data, off)[0]
            if not self._needs_emulation(w):
                continue
            prev = struct.unpack_from('<I', data, off - 4)[0] if off >= 4 else self.r32(a - 4)
            if self._is_branch(prev) and not any(s <= a - 4 < e for s, e in exclude):
                if off >= 4:
                    self.patched[a - 4] = prev
                    struct.pack_into('<I', data, off - 4, 0x0000000c | (1 << 6))
                else:
                    self.patched[a - 4] = prev
                    self.w32(a - 4, 0x0000000c | (1 << 6))
            else:
                self.patched[a] = w
                struct.pack_into('<I', data, off, 0x0000000c | (1 << 6))
            n += 1
        self.write(addr, bytes(data))
        return n

    @staticmethod
    def _is_branch(w):
        op = w >> 26
        if op in (2, 3, 4, 5, 6, 7, 0x14, 0x15, 0x16, 0x17):
            return True
        if op == 0 and (w & 0x3f) in (8, 9):
            return True
        if op == 1 and ((w >> 16) & 0x1f) in (0, 1, 2, 3, 0x10, 0x11, 0x12, 0x13):
            return True
        if op == 0x11 and ((w >> 21) & 0x1f) == 8:
            return True
        return False

    def unpatch_range(self, addr, size):
        """Restore original instruction words in [addr, addr+size)."""
        n = 0
        for a in [a for a in self.patched if addr <= a < addr + size]:
            self.w32(a, self.patched.pop(a))
            n += 1
        return n

    @staticmethod
    def _needs_emulation(w):
        op = w >> 26
        fn = w & 0x3f
        rd = (w >> 11) & 0x1f
        if op == 0:
            if fn in (0x18, 0x19) and rd != 0:
                return True                                  # mult/multu 3-op
            if fn == 0x0f and w != 0x0000000f:
                return True                                  # sync.l / sync.p
            return False
        if op == 0x1c:
            return True                                      # MMI
        if op in (0x1e, 0x1f):
            return True                                      # lq / sq
        if op == 0x2f:
            return True                                      # cache
        if op == 0x33:
            return True                                      # pref
        if op == 0x10 and (w & 0x02000000):
            return True                                      # COP0 CO ops (ei/di/eret/tlb*)
        if op == 0x12:
            return True                                      # COP2 (VU0 macro) -> trap
        return False

    # ---- hooks
    def _unmapped(self, uc, access, addr, size, value, ud):
        pc = uc.reg_read(UC_MIPS_REG_PC)
        raise RuntimeError(f"unmapped access {access} at {addr:#x} size {size} pc={pc:#x}")

    def _intr(self, uc, intno, ud):
        pc = uc.reg_read(UC_MIPS_REG_PC)
        if intno != 17:
            raise RuntimeError(f"exception {intno} at pc={pc:#x}")
        addr = pc - 4
        insn = self.r32(addr)
        code = (insn >> 6) & 0xFFFFF
        if code == 0:
            # real Sony syscall; if it sits in a delay slot, evaluate the branch first
            prev = self.r32(addr - 4) if addr >= 4 else 0
            br = self._branch_eval(prev, addr - 4)
            if br is not None and br[2]:
                self.setreg(31, addr + 4)
            self._real_syscall(uc, addr)
            if br is not None:
                uc.reg_write(UC_MIPS_REG_PC, br[1] if br[0] else addr + 4)
            else:
                uc.reg_write(UC_MIPS_REG_PC, addr + 4)
            return
        orig = self.patched.get(addr)
        if orig is None:
            raise RuntimeError(f"trap with unknown index at {addr:#x}")
        if self._is_branch(orig):
            taken, target, link, likely = self._branch_eval(orig, addr)
            if link:
                self.setreg(31, addr + 8)
            if taken or not likely:
                self.emulate(self.r32(addr + 4), addr + 4)
            uc.reg_write(UC_MIPS_REG_PC, target if taken else addr + 8)
        else:
            self.emulate(orig, addr)
            uc.reg_write(UC_MIPS_REG_PC, addr + 4)

    def _branch_eval(self, w, baddr):
        """Return (taken, target, sets_link, likely) if w is a branch/jump, else None."""
        op = w >> 26
        rs = (w >> 21) & 0x1f
        rt = (w >> 16) & 0x1f
        fn = w & 0x3f
        off = sext16(w) << 2
        tgt = (baddr + 4 + off) & M32
        if op == 0 and fn in (8, 9):                  # jr / jalr
            return (True, self.reg(rs) & M32, fn == 9, False)
        if op in (2, 3):                              # j / jal
            return (True, ((baddr + 4) & 0xF0000000) | ((w & 0x3ffffff) << 2), op == 3, False)
        s = sext64(self.reg(rs))
        t = sext64(self.reg(rt))
        if op in (4, 0x14):
            return (s == t, tgt, False, op == 0x14)        # beq / beql
        if op in (5, 0x15):
            return (s != t, tgt, False, op == 0x15)        # bne / bnel
        if op in (6, 0x16):
            return (s <= 0, tgt, False, op == 0x16)        # blez
        if op in (7, 0x17):
            return (s > 0, tgt, False, op == 0x17)         # bgtz
        if op == 1:                                            # REGIMM
            if rt in (0, 2):
                return (s < 0, tgt, False, rt == 2)        # bltz / bltzl
            if rt in (1, 3):
                return (s >= 0, tgt, False, rt == 3)       # bgez / bgezl
            if rt in (0x10, 0x12):
                return (s < 0, tgt, True, rt == 0x12)   # bltzal
            if rt in (0x11, 0x13):
                return (s >= 0, tgt, True, rt == 0x13)  # bgezal
        if op == 0x11 and rs == 8:                             # bc1f/bc1t (+likely)
            fcr = self.uc.reg_read(UC_MIPS_REG_FCSR)
            c = (fcr >> 23) & 1
            return (c == (rt & 1), tgt, False, bool(rt & 2))
        return None

    def _real_syscall(self, uc, addr):
        num = sext64(self.reg(3))
        c = self.syscall_counts.get(num, 0) + 1
        self.syscall_counts[num] = c
        if c > self.syscall_limit:
            raise RuntimeError(f'syscall {num:#x} called {c} times (last at {addr:#x}) - runaway loop?')
        h = self.syscall_handlers.get(num)
        if h:
            h(self)
        else:
            if self.verbose:
                print(f"  [syscall {num:#x} at {addr:#x}] -> 0")
            self.setreg(2, 0)

    # ---- instruction emulation
    def emulate(self, w, addr):
        op = w >> 26
        rs = (w >> 21) & 0x1f
        rt = (w >> 16) & 0x1f
        rd = (w >> 11) & 0x1f
        sa = (w >> 6) & 0x1f
        fn = w & 0x3f
        if op == 0x2f or op == 0x33 or (op == 0 and fn == 0x0f):
            return                                                  # cache / pref / sync.*
        if op == 0x10:                                              # COP0 CO: ei/di/eret/tlb -> nop
            return
        if op == 0x12:
            raise NotImplementedError(f"COP2 insn {w:#010x} at {addr:#x}")
        if op == 0x1e:                                              # lq
            ea = (self.reg(rs) + sext16(w)) & M32 & ~0xf
            self.setreg128(rt, int.from_bytes(self.read_data(ea, 16), 'little'))
            return
        if op == 0x1f:                                              # sq
            ea = (self.reg(rs) + sext16(w)) & M32 & ~0xf
            self.write(ea, self.reg128(rt).to_bytes(16, 'little'))
            for a in range(ea, ea + 16, 4):
                self.patched.pop(a, None)
            return
        if op == 0 and fn in (0x18, 0x19):                          # mult/multu rd
            a = self.reg(rs)
            b = self.reg(rt)
            p = (sext32(a) * sext32(b)) if fn == 0x18 else ((a & M32) * (b & M32))
            lo = sext32(p) & M64
            hi = sext32(p >> 32) & M64
            self.uc.reg_write(UC_MIPS_REG_LO, lo)
            self.uc.reg_write(UC_MIPS_REG_HI, hi)
            self.setreg(rd, lo)
            return
        if op == 0x1c:
            return self._mmi(w, addr, rs, rt, rd, sa, fn)
        raise NotImplementedError(f"insn {w:#010x} at {addr:#x}")

    def _mmi(self, w, addr, rs, rt, rd, sa, fn):
        uc = self.uc
        if fn in (0x00, 0x01):                                      # madd / maddu (pipeline 0)
            a = self.reg(rs)
            b = self.reg(rt)
            acc = (sext32(uc.reg_read(UC_MIPS_REG_HI)) << 32) | (uc.reg_read(UC_MIPS_REG_LO) & M32)
            p = acc + ((sext32(a) * sext32(b)) if fn == 0 else ((a & M32) * (b & M32)))
            lo = sext32(p) & M64
            hi = sext32(p >> 32) & M64
            uc.reg_write(UC_MIPS_REG_LO, lo)
            uc.reg_write(UC_MIPS_REG_HI, hi)
            self.setreg(rd, lo)
            return
        if fn in (0x20, 0x21):                                      # madd1 / maddu1
            a = self.reg(rs)
            b = self.reg(rt)
            acc = (sext32(self.hi1) << 32) | (self.lo1 & M32)
            p = acc + ((sext32(a) * sext32(b)) if fn == 0x20 else ((a & M32) * (b & M32)))
            self.lo1 = sext32(p) & M64
            self.hi1 = sext32(p >> 32) & M64
            self.setreg(rd, self.lo1)
            return
        if fn in (0x18, 0x19):                                      # mult1 / multu1
            a = self.reg(rs)
            b = self.reg(rt)
            p = (sext32(a) * sext32(b)) if fn == 0x18 else ((a & M32) * (b & M32))
            self.lo1 = sext32(p) & M64
            self.hi1 = sext32(p >> 32) & M64
            self.setreg(rd, self.lo1)
            return
        if fn in (0x1a, 0x1b):                                      # div1 / divu1
            a = self.reg(rs)
            b = self.reg(rt)
            if fn == 0x1a:
                a = sext32(a)
                b = sext32(b)
                if b == 0:
                    q, r = (-1 if a >= 0 else 1), a
                else:
                    q = abs(a) // abs(b)
                    if (a < 0) != (b < 0):
                        q = -q
                    r = a - q * b
            else:
                a &= M32
                b &= M32
                if b == 0:
                    q, r = M32, a
                else:
                    q, r = a // b, a % b
            self.lo1 = sext32(q) & M64
            self.hi1 = sext32(r) & M64
            return
        if fn == 0x10:
            self.setreg(rd, self.hi1)
            return             # mfhi1
        if fn == 0x11:
            self.hi1 = self.reg(rs)
            return              # mthi1
        if fn == 0x12:
            self.setreg(rd, self.lo1)
            return             # mflo1
        if fn == 0x13:
            self.lo1 = self.reg(rs)
            return              # mtlo1
        if fn == 0x04:                                              # plzcw
            v = self.reg(rs)
            out = 0
            for i in range(2):
                e = (v >> (32 * i)) & M32
                top = (e >> 31) & 1
                n = 0
                for bit in range(30, -1, -1):
                    if ((e >> bit) & 1) == top:
                        n += 1
                    else:
                        break
                out |= n << (32 * i)
            self.setreg(rd, out)
            return
        if fn == 0x30:                                              # pmfhl
            lo = uc.reg_read(UC_MIPS_REG_LO) & M64
            hi = uc.reg_read(UC_MIPS_REG_HI) & M64
            lo128 = (self.lo1 << 64) | lo
            hi128 = (self.hi1 << 64) | hi
            if sa == 0:  # pmfhl.lw : rd = {hi[64:96], lo[64:96], hi[0:32], lo[0:32]}
                v = (lo128 & M32) | (((hi128) & M32) << 32) | (((lo128 >> 64) & M32) << 64) | (((hi128 >> 64) & M32) << 96)
                self.setreg128(rd, v)
                return
            if sa == 1:  # pmfhl.uw
                v = ((lo128 >> 32) & M32) | (((hi128 >> 32) & M32) << 32) | (((lo128 >> 96) & M32) << 64) | (((hi128 >> 96) & M32) << 96)
                self.setreg128(rd, v)
                return
        if fn in (0x34, 0x36, 0x37, 0x3c, 0x3e, 0x3f):              # psllh/psrlh/psrah/psllw/psrlw/psraw
            v = self.reg128(rt)
            width = 16 if fn < 0x38 else 32
            n = 128 // width
            out = 0
            s = sa & (width - 1)
            for i in range(n):
                e = (v >> (i * width)) & ((1 << width) - 1)
                if fn in (0x34, 0x3c):
                    e = (e << s) & ((1 << width) - 1)
                elif fn in (0x36, 0x3e):
                    e = e >> s
                else:
                    if e & (1 << (width - 1)):
                        e -= (1 << width)
                    e = (e >> s) & ((1 << width) - 1)
                out |= e << (i * width)
            self.setreg128(rd, out)
            return
        if fn in (0x08, 0x28, 0x09, 0x29):                          # MMI0/1/2/3
            sub = (w >> 6) & 0x1f
            return self._mmi_sub(fn, sub, w, addr, rs, rt, rd)
        raise NotImplementedError(f"MMI fn={fn:#x} insn {w:#010x} at {addr:#x}")

    def _mmi_sub(self, grp, sub, w, addr, rs, rt, rd):
        a = self.reg128(rs)
        b = self.reg128(rt)

        def lanes(v, width):
            return [(v >> (i * width)) & ((1 << width) - 1) for i in range(128 // width)]

        def pack(ls, width):
            out = 0
            for i, e in enumerate(ls):
                out |= (e & ((1 << width) - 1)) << (i * width)
            return out

        if grp == 0x08:   # MMI0
            if sub == 0x00:
                self.setreg128(rd, pack([x + y for x, y in zip(lanes(a, 32), lanes(b, 32))], 32))
                return   # paddw
            if sub == 0x01:
                self.setreg128(rd, pack([x - y for x, y in zip(lanes(a, 32), lanes(b, 32))], 32))
                return   # psubw
            if sub == 0x04:
                self.setreg128(rd, pack([x + y for x, y in zip(lanes(a, 16), lanes(b, 16))], 16))
                return   # paddh
            if sub == 0x05:
                self.setreg128(rd, pack([x - y for x, y in zip(lanes(a, 16), lanes(b, 16))], 16))
                return   # psubh
            if sub == 0x08:
                self.setreg128(rd, pack([x + y for x, y in zip(lanes(a, 8), lanes(b, 8))], 8))
                return      # paddb
            if sub == 0x09:
                self.setreg128(rd, pack([x - y for x, y in zip(lanes(a, 8), lanes(b, 8))], 8))
                return      # psubb
            if sub == 0x12:  # pextlw
                la, lb = lanes(a, 32), lanes(b, 32)
                self.setreg128(rd, pack([lb[0], la[0], lb[1], la[1]], 32))
                return
            if sub == 0x16:  # pextlh
                la, lb = lanes(a, 16), lanes(b, 16)
                self.setreg128(rd, pack([lb[0], la[0], lb[1], la[1], lb[2], la[2], lb[3], la[3]], 16))
                return
            if sub == 0x1a:  # pextlb
                la, lb = lanes(a, 8), lanes(b, 8)
                out = []
                for i in range(8):
                    out += [lb[i], la[i]]
                self.setreg128(rd, pack(out, 8))
                return
            if sub == 0x13:  # ppacw
                la, lb = lanes(a, 32), lanes(b, 32)
                self.setreg128(rd, pack([lb[0], lb[2], la[0], la[2]], 32))
                return
            if sub == 0x17:  # ppach
                la, lb = lanes(a, 16), lanes(b, 16)
                self.setreg128(rd, pack([lb[0], lb[2], lb[4], lb[6], la[0], la[2], la[4], la[6]], 16))
                return
            if sub == 0x1b:  # ppacb
                la, lb = lanes(a, 8), lanes(b, 8)
                self.setreg128(rd, pack([lb[i] for i in range(0, 16, 2)] + [la[i] for i in range(0, 16, 2)], 8))
                return
        if grp == 0x28:   # MMI1
            if sub == 0x12:
                la, lb = lanes(a, 32), lanes(b, 32)
                self.setreg128(rd, pack([lb[2], la[2], lb[3], la[3]], 32))
                return  # pextuw
            if sub == 0x16:
                la, lb = lanes(a, 16), lanes(b, 16)
                self.setreg128(rd, pack([lb[4], la[4], lb[5], la[5], lb[6], la[6], lb[7], la[7]], 16))
                return  # pextuh
            if sub == 0x1a:
                la, lb = lanes(a, 8), lanes(b, 8)
                out = []
                for i in range(8, 16):
                    out += [lb[i], la[i]]
                self.setreg128(rd, pack(out, 8))
                return  # pextub
            if sub == 0x18:
                self.setreg128(rd, pack([min(x + y, 255) for x, y in zip(lanes(a, 8), lanes(b, 8))], 8))
                return  # paddub
            if sub == 0x02:
                self.setreg128(rd, pack([M32 if x == y else 0 for x, y in zip(lanes(a, 32), lanes(b, 32))], 32))
                return  # pceqw
            if sub == 0x06:
                self.setreg128(rd, pack([0xffff if x == y else 0 for x, y in zip(lanes(a, 16), lanes(b, 16))], 16))
                return  # pceqh
            if sub == 0x0a:
                self.setreg128(rd, pack([0xff if x == y else 0 for x, y in zip(lanes(a, 8), lanes(b, 8))], 8))
                return  # pceqb
        if grp == 0x09:   # MMI2
            if sub == 0x12:
                self.setreg128(rd, a & b)
                return                                    # pand
            if sub == 0x13:
                self.setreg128(rd, a ^ b)
                return                                    # pxor
            if sub == 0x0e:  # pcpyld
                self.setreg128(rd, ((a & M64) << 64) | (b & M64))
                return
            if sub == 0x1c:  # pexeh
                l = lanes(b, 16)
                self.setreg128(rd, pack([l[2], l[1], l[0], l[3], l[6], l[5], l[4], l[7]], 16))
                return
            if sub == 0x1e:  # prot3w
                l = lanes(b, 32)
                self.setreg128(rd, pack([l[1], l[2], l[0], l[3]], 32))
                return
        if grp == 0x29:   # MMI3
            if sub == 0x12:
                self.setreg128(rd, a | b)
                return                                    # por
            if sub == 0x13:
                self.setreg128(rd, ~(a | b) & M128)
                return                         # pnor
            if sub == 0x0e:
                self.setreg128(rd, (a & (M64 << 64)) | (b >> 64))
                return           # pcpyud
            if sub == 0x1b:
                l = lanes(b, 16)
                self.setreg128(rd, pack([l[0], l[2], l[1], l[3], l[4], l[6], l[5], l[7]], 16))
                return  # pexch
            if sub == 0x1a:
                l = lanes(b, 32)
                self.setreg128(rd, pack([l[0], l[2], l[1], l[3]], 32))
                return  # pexcw
            if sub == 0x1b + 0x00 and False:
                pass
            if sub == 0x1d:  # pcpyh
                l = lanes(b, 16)
                self.setreg128(rd, pack([l[0]] * 4 + [l[4]] * 4, 16))
                return
        raise NotImplementedError(f"MMI grp={grp:#x} sub={sub:#x} insn {w:#010x} at {addr:#x}")

    # ---- data views of patched code
    def add_text_range(self, start, end):
        """Make guest *data* reads of patched code words see the original words:
        before a read we restore the original, after the read we re-insert the trap.
        Guest writes into patched words drop the patch (the guest's word wins)."""
        def before(uc, access, address, size, value, key):
            for a in range(address & ~3, address + size, 4):
                orig = self.patched.get(a)
                if orig is not None:
                    uc.mem_write(a, struct.pack('<I', orig))
                    self.tmp_restored.append(a)
                    self.data_reads.add(a)

        def after(uc, access, address, size, value, key):
            if self.tmp_restored:
                for a in self.tmp_restored:
                    if a in self.patched:
                        uc.mem_write(a, struct.pack('<I', 0x0000000c | (1 << 6)))
                self.tmp_restored = []

        def onwrite(uc, access, address, size, value, key):
            for a in range(address & ~3, address + size, 4):
                self.patched.pop(a, None)

        self.uc.hook_add(UC_HOOK_MEM_READ, before, None, start, end - 1)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, onwrite, None, start, end - 1)
        fn = uccallback(self.uc, HOOK_MEM_ACCESS_CFUNC)(after)
        self._keep.append(fn)
        self.uc._Uc__do_hook_add(UC_HOOK_MEM_READ_AFTER, fn, start, end - 1)

    def read_data(self, addr, n):
        """Read guest memory as the guest would see it (original words where patched)."""
        b = bytearray(self.read(addr, n))
        for a in range(addr & ~3, addr + n, 4):
            orig = self.patched.get(a)
            if orig is not None and addr <= a and a + 4 <= addr + n:
                struct.pack_into('<I', b, a - addr, orig)
        return bytes(b)

    # ---- function hooks (HLE replacement of guest functions)
    def hook_function(self, addr, handler):
        """Replace the guest function at `addr`: on entry call handler(ee) -> v0, then return to ra."""
        def cb(uc, address, size, ud):
            rv = handler(self)
            if rv is not None:
                self.setreg(2, rv)
            uc.reg_write(UC_MIPS_REG_PC, self.reg(31) & M32)
        self.uc.hook_add(UC_HOOK_CODE, cb, None, addr, addr)

    def arg(self, i):
        """i-th integer argument (0-based) under the EE ABI: a0-a3, t0-t3, then stack from 0x20(sp)."""
        if i < 8:
            return self.reg(4 + i) & M32 if i < 4 else self.reg(8 + i - 4) & M32
        return self.r32(self.reg(29) + 0x20 + (i - 8) * 8) if False else self.r32((self.reg(29) & M32) + (i - 8) * 8 + 0x40 - 0x20)

    # ---- calling
    RET = 0x000000F0

    def defer(self, fn):
        """Run fn() outside the emulation loop (safe for code memory writes), then resume."""
        self.deferred.append(fn)
        self.uc.emu_stop()

    def call(self, addr, args=(), sp=None, max_insns=0):
        uc = self.uc
        for i, a in enumerate(args):
            if i < 4:
                self.setreg(4 + i, a)
            else:
                self.setreg(8 + i - 4, a)
        if sp is not None:
            self.setreg(29, sp)
        self.setreg(31, self.RET)
        self.deferred = []
        pc = addr
        while True:
            self.resume_pc = pc
            uc.emu_start(pc, self.RET, count=max_insns)
            pc = uc.reg_read(UC_MIPS_REG_PC) & M32
            if not self.deferred:
                break
            for fn in self.deferred:
                fn()
            self.deferred = []
            self.skip_once = pc
        return self.reg(2)
