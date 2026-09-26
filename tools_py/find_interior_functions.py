#!/usr/bin/env python
"""Report function starts hidden *inside* a Ghidra CSV range.

Ghidra sometimes merges adjacent functions into one range. The recompiler keys generated bodies by
range start, so an indirect call to the second function's address finds no target and does nothing
(docs/archive/HANDOFF-reference-to-2026-09-13.md gotcha 1). A boundary is a `jr $ra` + delay slot followed, after any padding, by more
code inside the same range. Only boundaries that are actually *referenced* — as a `jal` target or as
a 32-bit word stored anywhere in the loaded image (a vtable / ctor-table entry) — are reported, so
a mid-function second return point is not mistaken for a new function.

Usage: python tools_py/find_interior_functions.py <elf> <ghidra.csv> [--emit]
"""
import re, struct, sys

JR_RA = 0x03E00008

def segments(elf):
    d = open(elf, 'rb').read()
    phoff = struct.unpack_from('<I', d, 0x1c)[0]
    phnum = struct.unpack_from('<H', d, 0x2c)[0]
    return [(va, d[off:off + fsz])
            for t, off, va, _pa, fsz, _m, fl, _al in
            (struct.unpack_from('<IIIIIIII', d, phoff + i * 32) for i in range(phnum))
            if t == 1 and (fl & 1)]

def word_at(segs, addr):
    for va, data in segs:
        if va <= addr < va + len(data) - 3:
            return struct.unpack_from('<I', data, addr - va)[0]
    return None

def stub_addresses(toml='recomp/socom2.toml'):
    try:
        return {int(m, 16) for m in re.findall(r'@0x([0-9A-Fa-f]+)', open(toml).read())}
    except OSError:
        return set()

def referenced_addresses(elf):
    """Every address a JAL targets, every 32-bit word in the image, and every address built by a
    `lui rX,hi` + `addiu/ori rY,rX,lo` pair (function pointers loaded as immediates)."""
    d = open(elf, 'rb').read()
    phoff = struct.unpack_from('<I', d, 0x1c)[0]
    phnum = struct.unpack_from('<H', d, 0x2c)[0]
    jal, words = set(), set()
    for i in range(phnum):
        t, off, va, _pa, fsz, _m, fl, _al = struct.unpack_from('<IIIIIIII', d, phoff + i * 32)
        if t != 1:
            continue
        blob = d[off:off + fsz]
        for a in range(0, len(blob) - 3, 4):
            w = struct.unpack_from('<I', blob, a)[0]
            words.add(w)
            if fl & 1 and (w >> 26) == 3:                 # JAL
                jal.add(((w & 0x3ffffff) << 2) | ((va + a) & 0xf0000000))
        if fl & 1:
            # lui rX, hi  followed within a short window by addiu/ori rY, rX, lo
            hi = {}
            for a in range(0, len(blob) - 3, 4):
                w = struct.unpack_from('<I', blob, a)[0]
                op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xffff
                if op == 0x0f:                            # lui
                    hi[rt] = (imm << 16, a)
                elif op in (0x09, 0x0d) and rs in hi:     # addiu / ori
                    base, at = hi[rs]
                    if a - at <= 64:
                        lo = imm - 0x10000 if (op == 0x09 and imm & 0x8000) else imm
                        jal.add((base + lo) & 0xffffffff)
    return jal | words

def main():
    elf, csv_path = sys.argv[1], sys.argv[2]
    referenced = referenced_addresses(elf)
    emit = '--emit' in sys.argv
    segs = segments(elf)
    stubs = stub_addresses()
    starts, ranges = set(), []
    with open(csv_path) as f:
        next(f)
        for line in f:
            p = line.strip().split(',')
            if len(p) >= 3:
                try:
                    s, e = int(p[1], 16), int(p[2], 16)
                except ValueError:
                    continue
                starts.add(s)
                ranges.append((s, e, p[0]))

    found = []
    for s, e, name in sorted(ranges):
        if e - s <= 8 or e - s > 0x4000:
            continue
        words = []
        for a in range(s, e, 4):
            w = word_at(segs, a)
            if w is None:
                words = []
                break
            words.append(w)
        if not words:
            continue
        i = 0
        while i < len(words) - 2:
            if words[i] == JR_RA:
                j = i + 2                     # skip the delay slot
                while j < len(words) and words[j] == 0:
                    j += 1                    # skip alignment padding
                if j < len(words):
                    addr = s + j * 4
                    if addr not in starts and addr not in stubs and addr in referenced:
                        found.append((addr, name, s))
                i = j
            else:
                i += 1
    seen = set()
    found = [f for f in found if not (f[0] in seen or seen.add(f[0]))]
    for addr, name, s in found:
        print(f'0x{addr:08x}  inside {name} (0x{s:08x})')
    print(f'# {len(found)} interior function starts', file=sys.stderr)
    if emit:
        with open('recomp/extra_functions.txt', 'a', newline='\n') as f:
            for addr, _n, _s in found:
                f.write(f'0x{addr:08x}\n')
        print(f'# appended {len(found)} entries', file=sys.stderr)

main()
