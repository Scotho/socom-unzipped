#!/usr/bin/env python
"""Report executable gaps between Ghidra CSV functions that look like real function bodies.

Ghidra's function list misses small leaves and trampolines; a table- or register-dispatched call
into one of them finds no recompiled target and silently does nothing (see docs/HANDOFF gotcha 1).
A gap counts as a function body when it is non-empty after padding and contains `jr $ra`.

Addresses that socom2.toml stubs (`name@0xADDR`) are skipped: those run as runtime stubs and must
not be recompiled from the guest body.

Usage: python tools_py/find_gap_functions.py <elf> <ghidra.csv> [--emit]
"""
import re, struct, sys

JR_RA = 0x03E00008

def segments(elf):
    d = open(elf, 'rb').read()
    phoff = struct.unpack_from('<I', d, 0x1c)[0]
    phnum = struct.unpack_from('<H', d, 0x2c)[0]
    segs = []
    for i in range(phnum):
        t, off, va, _pa, fsz, _msz, flags, _al = struct.unpack_from('<IIIIIIII', d, phoff + i * 32)
        if t == 1 and (flags & 1):          # PT_LOAD, executable
            segs.append((va, d[off:off + fsz]))
    return segs

def ranges(csv):
    out = []
    with open(csv) as f:
        next(f)
        for line in f:
            parts = line.strip().split(',')
            if len(parts) < 3:
                continue
            try:
                out.append((int(parts[1], 16), int(parts[2], 16)))
            except ValueError:
                pass
    return sorted(out)

def stub_addresses(toml='recomp/socom2.toml'):
    try:
        text = open(toml).read()
    except OSError:
        return set()
    return {int(m, 16) for m in re.findall(r'@0x([0-9A-Fa-f]+)', text)}

def main():
    elf, csv = sys.argv[1], sys.argv[2]
    emit = '--emit' in sys.argv
    stubs = stub_addresses()
    segs = segments(elf)
    covered = ranges(csv)
    found = []
    for va, data in segs:
        end = va + len(data)
        # walk the gaps between consecutive covered ranges inside this segment
        marks = [(s, e) for s, e in covered if s < end and e > va]
        cursor = va
        gaps = []
        for s, e in marks:
            if s > cursor:
                gaps.append((cursor, s))
            cursor = max(cursor, e)
        if cursor < end:
            gaps.append((cursor, end))
        for gs, ge in gaps:
            words = [struct.unpack_from('<I', data, a - va)[0] for a in range(gs, ge, 4)]
            # strip leading/trailing padding (nop / zero)
            start = 0
            while start < len(words) and words[start] == 0:
                start += 1
            stop = len(words)
            while stop > start and words[stop - 1] == 0:
                stop -= 1
            body = words[start:stop]
            if not body or JR_RA not in body:
                continue
            addr = gs + start * 4
            if addr in stubs:
                continue
            found.append((addr, len(body), body))
    for addr, n, body in found:
        kind = 'thunk' if n <= 3 else 'leaf'
        print(f'0x{addr:08x}  {n:3d} words  {kind}  first={body[0]:08x}')
    print(f'# {len(found)} candidate functions in CSV gaps', file=sys.stderr)
    if emit:
        with open('recomp/extra_functions.txt', 'a', newline='\n') as f:
            for addr, _n, _b in found:
                f.write(f'0x{addr:08x}\n')
        print(f'# appended {len(found)} entries to recomp/extra_functions.txt', file=sys.stderr)

main()
