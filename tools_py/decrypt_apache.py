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
    print(f"ELF loaded, entry {e_entry:#x}, gp {gp:#x}, patched {n} R5900 insns")
    return e_entry, gp


SELF_DECRYPT = 0x5412a0   # FUN_005412a0(start, size^key, key, flags): flags&1 ? re-encrypt : decrypt


def find_encrypted_blocks(d, base, text_off, text_size):
    """Static scan of `jal SELF_DECRYPT` sites -> [(start, size)] of self-encrypted code blocks."""
    blocks = []
    jal = 0x0c000000 | (SELF_DECRYPT >> 2)
    for off in range(text_off, text_off + text_size, 4):
        if struct.unpack_from('<I', d, off)[0] != jal:
            continue
        a0 = None
        hi = None
        for back in range(4, 40, 4):
            w = struct.unpack_from('<I', d, off - back)[0]
            if (w >> 16) == 0x2484 and a0 is None:          # addiu a0, a0, imm
                a0 = struct.unpack('<h', struct.pack('<H', w & 0xffff))[0]
            elif (w >> 16) == 0x3c04:                       # lui a0, hi
                hi = (w & 0xffff) << 16
                break
        if a0 is None or hi is None:
            continue
        start = (hi + a0) & 0xffffffff
        slot = struct.unpack_from('<I', d, off + 4)[0]        # delay slot: lw a2, 4(v1) => decrypt site
        if (slot >> 26) != 0x23 or ((slot >> 16) & 0x1f) != 6 or (slot & 0xffff) != 4:
            continue                                        # re-encrypt trailer site, skip
        flag_off = start - 0x14 - base
        w1, w2, w3 = struct.unpack_from('<III', d, flag_off + 4)
        blocks.append((start, w3 ^ w1))
    return sorted(set(blocks))


def load_overlay(ee, path, addr):
    d = open(path, 'rb').read()
    ee.write(addr, d)
    text, data, bss = struct.unpack_from('<III', d, 0x0c)
    ee.write(addr + len(d), bytes(bss))
    blocks = find_encrypted_blocks(d, addr, 0x80, text)
    total = sum(sz for _, sz in blocks)
    print(f"  {len(blocks)} self-encrypted blocks, {total:#x} bytes; first: {[(hex(a), hex(s)) for a, s in blocks[:3]]}")
    n = ee.patch_range(addr + 0x80, text, exclude=[(a, a + s) for a, s in blocks])
    print(f"overlay {os.path.basename(path)} @ {addr:#x}: text {text:#x} data {data:#x} bss {bss:#x}, patched {n}")

    # runtime hooks: patch a block after it is decrypted, un-patch before it is re-encrypted
    from unicorn import UC_HOOK_CODE
    pending = {}

    def on_return(uc, address, size, ud):
        if address in pending:
            start, sz = pending.pop(address)
            n = ee.patch_range(start, sz)
            if ee.verbose:
                print(f"  [decrypted block {start:#x}+{sz:#x}: patched {n}]")

    def on_selfdecrypt(uc, address, size, ud):
        a0, a1, a2, a3 = (ee.reg(4) & 0xffffffff, ee.reg(5) & 0xffffffff, ee.reg(6) & 0xffffffff, ee.reg(7) & 0xffffffff)
        blk = a1 ^ a2
        if a3 & 1:
            n = ee.unpatch_range(a0 - blk, blk)
            if ee.verbose:
                print(f"  [re-encrypting block {a0-blk:#x}+{blk:#x}: unpatched {n}]")
        else:
            pending[ee.reg(31) & 0xffffffff] = (a0, blk)

    ee.uc.hook_add(UC_HOOK_CODE, on_selfdecrypt, None, SELF_DECRYPT, SELF_DECRYPT)
    # return sites: every jal site + 8; hook the whole overlay text cheaply? no - hook exact return addrs
    jal = 0x0c000000 | (SELF_DECRYPT >> 2)
    for off in range(0x80, 0x80 + text, 4):
        if struct.unpack_from('<I', d, off)[0] == jal:
            ra = addr + off + 8
            ee.uc.hook_add(UC_HOOK_CODE, on_return, None, ra, ra)


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
    load_overlay(ee, os.path.join(GAME, 'OVERLAY', 'REL', 'DNAS.BIN'), 0x4c5380)
    ee.setreg(28, gp)
    SP = 0x01fe0000
    BUF = 0x01000000
    OUT8 = 0x00f00000
    OUT4 = 0x00f00010

    # trace helper for debugging: count instructions
    def fc(ee):  # FlushCache
        ee.setreg(2, 0)
    ee.syscall_handlers[0x64] = fc

    blobs = zdb_entries(os.path.join(GAME, 'RUN', 'RAW', 'APACHE00.ZDB'))
    print("ZDB entries:", {k: len(v) for k, v in blobs.items()})

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
    print("done")


if __name__ == '__main__':
    main()
