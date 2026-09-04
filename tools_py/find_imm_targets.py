"""Find code addresses materialized as immediates (lui rX,hi ; addiu/ori rY,rX,lo) that are
not covered by any function in the Ghidra CSV, and append them to extra_functions.txt.
These are callbacks (alarm/interrupt handlers, thread entries, function tables built at
runtime) that neither flow analysis nor the data pointer scan can see.

Usage: python find_imm_targets.py socom2_game.elf socom2_ghidra.csv extra_functions.txt
"""
import bisect
import csv
import struct
import sys

elf_path, csv_path, extra_path = sys.argv[1:4]
d = open(elf_path, 'rb').read()
e_phoff = struct.unpack_from('<I', d, 0x1c)[0]
e_phnum = struct.unpack_from('<H', d, 0x2c)[0]
segs = []
for i in range(e_phnum):
    p_type, p_off, p_vaddr, _, p_filesz, p_memsz, p_flags = struct.unpack_from('<IIIIIII', d, e_phoff + i * 32)
    if p_type == 1 and p_filesz and (p_flags & 1):
        segs.append((p_vaddr, p_filesz, p_off))


def in_exec(a):
    return any(v <= a < v + sz for v, sz, _ in segs)


def word(a):
    for v, sz, off in segs:
        if v <= a < v + sz:
            return struct.unpack_from('<I', d, off + a - v)[0]
    return None


rows = list(csv.reader(open(csv_path)))[1:]
funcs = sorted((int(r[1], 16), int(r[2], 16)) for r in rows)
starts = [s for s, _ in funcs]


def covered(a):
    i = bisect.bisect_right(starts, a) - 1
    return i >= 0 and funcs[i][0] <= a < funcs[i][1]


def plausible(w):
    op = w >> 26
    rs = (w >> 21) & 0x1f
    rt = (w >> 16) & 0x1f
    fn = w & 0x3f
    if w == 0:
        return False
    if op == 9 and rs == 29 and rt == 29:
        return True          # addiu sp,sp
    if op in (0x0f, 2, 3, 4, 5, 6, 7, 1, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 9, 0x11, 0x12, 0x1e, 0x1f):
        return True
    if 0x20 <= op <= 0x2e or 0x30 <= op <= 0x3f:
        return True
    if op == 0 and fn in (8, 9, 0x25, 0x2d, 0x21, 0x23, 0x24, 0x2b, 0x2a, 0):
        return True
    return False


known = {int(l.split('#')[0], 16) for l in open(extra_path) if l.split('#')[0].strip()} if True else set()
cands = {}
for v, sz, off in segs:
    words = struct.unpack_from('<%dI' % (sz // 4), d, off)
    for i, w in enumerate(words):
        if (w >> 16) & 0xfc00 != 0x3c00:
            continue                      # lui
        rt = (w >> 16) & 0x1f
        hi = (w & 0xffff) << 16
        for j in range(i + 1, min(i + 6, len(words))):
            w2 = words[j]
            op = w2 >> 26
            if op == 9 and ((w2 >> 21) & 0x1f) == rt:               # addiu rY, rt, lo
                lo = struct.unpack('<h', struct.pack('<H', w2 & 0xffff))[0]
                a = (hi + lo) & 0xffffffff
            elif op == 0x0d and ((w2 >> 21) & 0x1f) == rt:          # ori
                a = hi | (w2 & 0xffff)
            else:
                continue
            if a & 3 or not in_exec(a) or covered(a) or a in known:
                break
            ww = word(a)
            if ww is not None and plausible(ww):
                cands.setdefault(a, v + 4 * i)
            break
with open(extra_path, 'a') as f:
    for a in sorted(cands):
        f.write(f"0x{a:x}  # imm target from 0x{cands[a]:x}\n")
print(f"find_imm_targets: {len(cands)} new code targets appended")
