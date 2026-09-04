"""Run SOCOM II's own loader code (boot ELF + DNAS overlay) under Unicorn to
decrypt the APACHE00.ZDB code package, then inflate the result and write the
plain overlays to disk.

Mirrors FUN_001c59c0 / FUN_001c5da0 in SCUS_972.75:
    load DNAS.BIN @0x4c5380 ; call 0x534830()
    for (name, dest) in [("ftscore", 0x1e7000), ("zsealetc", 0x4c5380)]:
        size  = read ZDB entry into buf
        rc    = 0x539d00(size, buf, &out8)      ; rc >= 0
        size2 = 0x539d50(size, out8, buf)       ; size2 > 0
        rc    = 0x534848(size2, buf, &out4)     ; rc == 0
        rc    = 0x535018(size2, out4, buf)      ; rc == 0
        inflate(buf[:out4]) -> dest
"""
import struct
import sys
import zlib
import time
import os

sys.path.insert(0, os.path.dirname(__file__))
from ee_unicorn import EE, sext32
from unicorn import UC_HOOK_CODE

GAME = os.path.join(os.path.dirname(__file__), '..', 'game', 'disc')
OUT = os.path.join(os.path.dirname(__file__), '..', 'game', 'overlays')
os.makedirs(OUT, exist_ok=True)


def load_elf(ee, path):
    d = open(path, 'rb').read()
    e_entry, e_phoff, e_shoff = struct.unpack_from('<III', d, 0x18)
    e_phnum = struct.unpack_from('<H', d, 0x2c)[0]
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from('<HHH', d, 0x2e)
    for i in range(e_phnum):
        p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from('<IIIIII', d, e_phoff + i * 32)
        if p_type != 1 or p_memsz == 0:
            continue
        if p_filesz:
            ee.write(p_vaddr, d[p_offset:p_offset + p_filesz])
        if p_memsz > p_filesz:
            ee.write(p_vaddr + p_filesz, b'\0' * (p_memsz - p_filesz))
    # .reginfo -> gp
    gp = 0
    for i in range(e_shnum):
        sh_type, sh_flags, sh_addr, sh_offset, sh_size = struct.unpack_from('<IIIII', d, e_shoff + i * e_shentsize + 4)
        if sh_type == 0x70000006:
            gp = struct.unpack_from('<I', d, sh_offset + 0x14)[0]
    # patch the code half (0x180000.. where entropy is non-zero)
    n = ee.patch_range(0x180000, 0xd5600 - 0x80000)
    if os.environ.get('TEXT_HOOKS'):
        ee.add_text_range(0x180000, 0x100000 + 0xd5600)
    print(f"ELF loaded, entry {e_entry:#x}, gp {gp:#x}, patched {n} R5900 insns")
    return e_entry, gp


SELF_DECRYPTORS = (0x4ee9e8, 0x52b9d0, 0x53a358, 0x5412a0)   # FUN(start, size^key, key, flags): flags&1 ? re-encrypt : decrypt


def find_encrypted_blocks(d, base, text_off, text_size):
    """Static scan of `jal <decryptor>` sites.
    Returns (blocks, data): blocks = [(start, size)] of self-encrypted code, data = [(start, end)]
    of key/flag constant words living inside .text that must never be patched."""
    blocks = []
    data = []
    jals = {0x0c000000 | (a >> 2) for a in SELF_DECRYPTORS}

    def const_reg(off, reg):
        lo = None
        for back in range(4, 48, 4):
            w = struct.unpack_from('<I', d, off - back)[0]
            if (w >> 26) == 9 and ((w >> 21) & 0x1f) == reg and ((w >> 16) & 0x1f) == reg and lo is None:   # addiu reg, reg, imm
                lo = struct.unpack('<h', struct.pack('<H', w & 0xffff))[0]
            elif (w >> 26) == 0x0f and ((w >> 16) & 0x1f) == reg and lo is not None:                      # lui reg, hi
                return (((w & 0xffff) << 16) + lo) & 0xffffffff
        return None

    for off in range(text_off, text_off + text_size, 4):
        if struct.unpack_from('<I', d, off)[0] not in jals:
            continue
        slot = struct.unpack_from('<I', d, off + 4)[0]
        if (slot >> 26) != 0x23 or ((slot >> 16) & 0x1f) != 6:
            continue
        a0 = const_reg(off, 4)
        if a0 is None:
            continue
        if (slot & 0xffff) == 4:                     # decrypt site: lw a2, 4(v1); flag block at start-0x14
            flag = a0 - 0x14
            w1, w2, w3 = struct.unpack_from('<III', d, flag + 4 - base)
            blocks.append((a0, w3 ^ w1))
            data.append((flag, flag + 0x10))
        else:                                       # re-encrypt site: lw a2, 0(v0); constants at v0
            v0 = const_reg(off, 2)
            if v0 is not None:
                data.append((v0, v0 + 0xc))
    return sorted(set(blocks)), sorted(set(data))


def load_overlay(ee, path, addr):
    """Load the statically pre-decrypted DNAS overlay (see dnas_selfdecrypt.py) and neutralize
    the four runtime self-decrypt/re-encrypt routines so the plaintext stays intact."""
    d = open(path, 'rb').read()
    ee.write(addr, d)
    text, data, bss = struct.unpack_from('<III', d, 0x0c)
    ee.write(addr + len(d), bytes(bss))
    # key/flag words and re-encrypt trailer constants live inside .text: never trap-patch them
    _blocks, consts = find_encrypted_blocks(d, addr, 0x80, text)
    n = ee.patch_range(addr + 0x80, text, exclude=consts)
    if os.environ.get('TEXT_HOOKS'):     # NOTE: read hooks over code regions break Unicorn's translator
        ee.add_text_range(addr + 0x80, addr + 0x80 + text)
    print(f"overlay {os.path.basename(path)} @ {addr:#x}: text {text:#x} data {data:#x} bss {bss:#x}, patched {n}")

    def noop_decryptor(ee):
        a0, a1, a2, a3 = (ee.reg(4) & 0xffffffff, ee.reg(5) & 0xffffffff, ee.reg(6) & 0xffffffff, ee.reg(7) & 0xffffffff)
        if not (a3 & 1):                             # mark "decrypted" like the real routine would;
            ee.defer(lambda: ee.w32(a0 - 0x14, a0 - 0x14))   # deferred: it is a code-page write
        return 0
    for a in SELF_DECRYPTORS:
        ee.hook_function(a, noop_decryptor)


SIF_BIND = 0x1a6aa8     # sceSifBindRpc(cd, sid, mode)
SIF_CALL = 0x1a6c78     # sceSifCallRpc(cd, fno, mode, send, ssize, recv, rsize, endfunc, efarg)
rpc_clients = {}        # cd address -> sid
rpc_log = []


def install_sif_hle(ee):
    def sifgetreg(ee):
        reg = ee.reg(4) & 0xffffffff
        v = {1: 0x00001000, 2: 0x00001000, 3: 0x000f0000, 4: 0x000f0000}.get(reg & 0xff, 0)
        ee.setreg(2, v)
    ee.syscall_handlers[0x7a] = sifgetreg                        # SifGetReg
    ee.syscall_handlers[0x79] = lambda ee: ee.setreg(2, ee.reg(5))   # SifSetReg
    ee.syscall_handlers[0x77] = lambda ee: ee.setreg(2, 1)      # SifSetDma -> id
    ee.syscall_handlers[0x76] = lambda ee: ee.setreg(2, 0xffffffffffffffff)  # SifDmaStat -> done
    ee.syscall_handlers[0x78] = lambda ee: ee.setreg(2, 0)      # SifSetDChain

    def bind(ee):
        cd, sid = ee.arg(0), ee.arg(1)
        rpc_clients[cd] = sid
        ee.w32(cd + 0x24, 0x1234)          # t_SifClientData.server: non-null => bound
        print(f"  [RPC bind cd={cd:#x} sid={sid:#x}]")
        return 0

    def call(ee):
        cd, fno, mode, send, ssize, recv, rsize = (ee.arg(i) for i in range(7))
        sid = rpc_clients.get(cd, 0)
        data = ee.read(send, min(ssize, 64)) if send and ssize else b""
        print(f"  [RPC call sid={sid:#x} fno={fno} mode={mode} send={send:#x}/{ssize} recv={recv:#x}/{rsize} data={data.hex()}]")
        rpc_log.append((sid, fno, ee.read(send, ssize) if send and ssize else b""))
        h = RPC_SERVERS.get(sid)
        if h:
            h(ee, fno, send, ssize, recv, rsize)
        elif recv and rsize:
            ee.write(recv, bytes(rsize))
        return 0

    ee.hook_function(SIF_BIND, bind)
    ee.hook_function(SIF_CALL, call)
    ee.hook_function(0x1a6e68, lambda ee: 0)        # sceSifCheckStatRpc -> idle
    ee.hook_function(0x1a6c78 + 0, call)


CONSOLE_ID = bytes.fromhex('0102030405060708')      # sceCdReadConsoleID (8 bytes) - any value
ILINK_ID = bytes.fromhex('00a0b0c0d0e0f001')
MECHACON_VER = bytes([0x03, 0x06, 0x00, 0x00])       # sceCdMV


def cdvd_scmd(ee, fno, send, ssize, recv, rsize):
    """cdvdfsv S-command server (SID 0x80000593): result word + payload."""
    payload = {0x24: CONSOLE_ID, 0x22: ILINK_ID, 0x26: MECHACON_VER, 0x0c: b'SCPH-39001' + bytes(6)}.get(fno, b'')
    if recv and rsize:
        buf = struct.pack('<I', 1) + payload
        ee.write(recv, (buf + bytes(rsize))[:rsize])


RPC_SERVERS = {0x80000593: cdvd_scmd}


def zdb_entries(path):
    d = open(path, 'rb').read()
    n = struct.unpack_from('<I', d, 0x98)[0]
    off = 0xa0
    out = {}
    for _ in range(n):
        sz = struct.unpack_from('<I', d, off)[0]
        name = d[off + 4:off + 0x44].split(b'\0')[0].decode()
        o, l = struct.unpack_from('<II', d, off + 0x44)
        out[name] = d[o:o + l]
        off += sz
    return out


def main():
    ee = EE(verbose=True)
    entry, gp = load_elf(ee, os.path.join(GAME, 'SCUS_972.75'))
    BUF = 0x01000000
    OUT8 = 0x00f00000
    OUT4 = 0x00f00010

    # trace helper for debugging: count instructions
    ee.install_kernel_hle()
    install_sif_hle(ee)

    blobs = zdb_entries(os.path.join(GAME, 'RUN', 'RAW', 'APACHE00.ZDB'))
    print("ZDB entries:", {k: len(v) for k, v in blobs.items()})

    # Run the ELF's crt0 (register/FPU clear, bss clear, SetupThread/SetupHeap, MSL init) and
    # stop at the entry of main(), so libc state (heap!) is valid for the DNAS code.
    def setup_thread(ee):          # SetupThread(gp, stack, stack_size, args, root) -> sp
        stack, size = ee.reg(5) & 0xffffffff, ee.reg(6) & 0xffffffff
        if stack == 0xffffffff:                    # -1: kernel places the stack at the top of RAM
            ee.setreg(2, 0x01fffff0)
        else:
            ee.setreg(2, (stack + size) & ~0xf)
    def setup_heap(ee):            # SetupHeap(start, size) -> heap end
        start, size = ee.reg(4) & 0xffffffff, ee.reg(5) & 0xffffffff
        ee.setreg(2, 0x01f80000 if size == 0xffffffff else start + size)
    ee.syscall_handlers[0x3c] = setup_thread
    ee.syscall_handlers[0x3d] = setup_heap
    ee.hook_function(0x1ac9d8, lambda ee: 0)     # _InitSys kernel-patch search (FindAddress loop) - not applicable
    MAIN = 0x1c4cc0
    stopped = []
    def at_main(uc, address, size, ud):
        stopped.append(True)
        ee.stop_requested = True
        uc.emu_stop()
    ee.uc.hook_add(UC_HOOK_CODE, at_main, None, MAIN, MAIN)
    ee.run(entry, MAIN)
    print(f"crt0 done: reached main={bool(stopped)} sp={ee.reg(29):#x} gp={ee.reg(28):#x} syscalls={ee.syscall_counts}")
    # the overlay region is part of the ELF's bss, which crt0 just zero-filled: load DNAS now (as main() does)
    load_overlay(ee, os.path.join(GAME, 'OVERLAY', 'REL', 'DNAS.dec.bin'), 0x4c5380)
    SP = None

    # what main() does before touching DNAS: sceSifInitRpc(0), sceCdInit(SCECdINIT)
    print("sceSifInitRpc ->", ee.call(0x1a6368, (0,)))
    print("sceCdInit ->", ee.call(0x18ea98, (0,)))
    t0 = time.time()
    print("call 0x534830 (init)")
    r = ee.call(0x534830, (), sp=SP)
    print(f"  -> {r:#x}  ({time.time()-t0:.1f}s, syscalls {ee.syscall_counts})")

    for name, dest in (("ftscore", 0x1e7000), ("zsealetc", 0x4c5380)):
        blob = blobs[name]
        ee.write(BUF, blob)
        size = len(blob)
        ee.w64(OUT8, 0)
        ee.w32(OUT4, 0)
        t0 = time.time()
        rc = sext32(ee.call(0x539d00, (size, BUF, OUT8), sp=SP))
        print(f"{name}: 0x539d00 -> {rc}  out8={ee.r64(OUT8):#x} ({time.time()-t0:.1f}s)")
        if rc < 0:
            raise SystemExit("step1 failed")
        t0 = time.time()
        size2 = sext32(ee.call(0x539d50, (size, ee.r32(OUT8), BUF), sp=SP))
        print(f"{name}: 0x539d50 -> {size2}  ({time.time()-t0:.1f}s)")
        if size2 <= 0:
            raise SystemExit("step2 failed")
        t0 = time.time()
        rc = sext32(ee.call(0x534848, (size2, BUF, OUT4), sp=SP))
        print(f"{name}: 0x534848 -> {rc} out4={ee.r32(OUT4):#x} ({time.time()-t0:.1f}s)")
        if rc != 0:
            raise SystemExit("step3 failed")
        t0 = time.time()
        rc = sext32(ee.call(0x535018, (size2, ee.r32(OUT4), BUF), sp=SP))
        print(f"{name}: 0x535018 -> {rc} ({time.time()-t0:.1f}s)")
        if rc != 0:
            raise SystemExit("step4 failed")
        comp = ee.read(BUF, ee.r32(OUT4))
        print(f"{name}: compressed head {comp[:8].hex()}")
        plain = zlib.decompress(comp)
        print(f"{name}: inflated {len(plain)} bytes, head {plain[:16].hex()}")
        with open(os.path.join(OUT, name + '.bin'), 'wb') as f:
            f.write(plain)
        # after the first blob the game keeps DNAS resident; the second blob is
        # decrypted with DNAS still loaded (dest 0x4c5380 is only written by inflate)
    print("data reads hitting patched words:", len(ee.data_reads), sorted(hex(a) for a in list(ee.data_reads)[:20]))
    print("done")


if __name__ == '__main__':
    main()
