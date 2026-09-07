#!/usr/bin/env python
"""Report conditional branches whose target lies outside their own Ghidra CSV range.

The recompiler emits a branch to an address outside the function as a scheduler unwind
(`ctx->pc = target; return;`). If no function *starts* at that address the dispatcher reports
`[guest-branch:missing-target]` and the thread silently dies (a loop head that Ghidra split into a
neighbouring "thunk" row is the typical case: FUN_00510980 / thunk_FUN_00510980). Each report
names the function, the branch pc, the target, and which CSV row (if any) owns the target.

Usage: python tools_py/find_escaping_branches.py <elf> <ghidra.csv> [--fix <csv-out>]
With --fix, every reported function is merged with the row that owns its target (and everything
in between) into one range keyed by the lowest start; the merged row keeps the lowest start's name.
"""
import bisect, csv, struct, sys

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

def branch_target(pc, w):
    op = w >> 26
    rs = (w >> 21) & 31
    rt = (w >> 16) & 31
    imm = w & 0xffff
    if imm & 0x8000:
        imm -= 0x10000
    if op in (4, 5, 6, 7, 0x14, 0x15, 0x16, 0x17):
        return pc + 4 + imm * 4
    if op == 1 and rt in (0, 1, 2, 3, 0x10, 0x11, 0x12, 0x13):   # bltz/bgez(+l, +al)
        return pc + 4 + imm * 4
    if op in (0x11, 0x12) and rs == 8:                            # bc1*/bc2*
        return pc + 4 + imm * 4
    return None

def main():
    elf, csvp = sys.argv[1], sys.argv[2]
    fix_out = sys.argv[sys.argv.index('--fix') + 1] if '--fix' in sys.argv else None
    segs = segments(elf)
    rows = list(csv.reader(open(csvp)))
    hdr, body = rows[0], rows[1:]
    ranges = sorted(((int(r[1], 16), int(r[2], 16), r[0]) for r in body), key=lambda x: x[0])
    starts = [r[0] for r in ranges]
    def owner(a):
        i = bisect.bisect_right(starts, a) - 1
        if i >= 0 and ranges[i][0] <= a < ranges[i][1]:
            return ranges[i]
        return None
    reports = []
    for s, e, name in ranges:
        for pc in range(s, e, 4):
            w = word_at(segs, pc)
            if w is None:
                break
            t = branch_target(pc, w)
            if t is None or s <= t < e:
                continue
            o = owner(t)
            reports.append((s, e, name, pc, t, o))
    merges = {}
    for s, e, name, pc, t, o in reports:
        oname = f"{o[2]} [{o[0]:#x},{o[1]:#x})" if o else "NO ROW (gap)"
        entry = "entry" if (o and o[0] == t) else "mid"
        print(f"{name} [{s:#x},{e:#x}) branch at {pc:#x} -> {t:#x} : {oname} {entry}")
        lo = min(s, o[0] if o else t)
        hi = max(e, o[1] if o else t + 8)
        merges.setdefault(s, [lo, hi])
        merges[s][0] = min(merges[s][0], lo)
        merges[s][1] = max(merges[s][1], hi)
    print(f"{len(reports)} escaping branches in {len(merges)} functions", file=sys.stderr)
    if fix_out:
        # merge each reported function with everything between lo and hi
        spans = sorted(merges.values())
        merged = []
        for lo, hi in spans:
            if merged and lo <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        out = []
        for r in body:
            s, e = int(r[1], 16), int(r[2], 16)
            keep = True
            for lo, hi in merged:
                if lo <= s < hi:
                    if s == lo:
                        r = [r[0], f"0x{lo:08X}", f"0x{hi:08X}", str(hi - lo)]
                    else:
                        keep = False
                    break
            if keep:
                out.append(r)
        with open(fix_out, 'w', newline='') as f:
            w = csv.writer(f, lineterminator='\n')
            w.writerow(hdr)
            w.writerows(out)
        print(f"wrote {fix_out}: {len(body) - len(out)} rows folded into {len(merged)} merged ranges", file=sys.stderr)

if __name__ == '__main__':
    main()
