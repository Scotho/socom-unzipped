"""Normalize the Ghidra ExportPS2Functions CSV for PS2Recomp:
- Ghidra functions with non-contiguous bodies export End = max address of the body while
  Size = bytes actually in the body; PS2Recomp treats [Start, End) as the function, which
  swallows every function in between.  Force End = Start + Size.
- Append forced entry points listed in recomp/extra_functions.txt (one hex address per line),
  ending at the next known function start.
Usage: python fix_ghidra_csv.py recomp/socom2_ghidra.csv recomp/extra_functions.txt
"""
import bisect
import csv
import os
import sys

csv_path, extra_path = sys.argv[1], sys.argv[2]
rows = list(csv.reader(open(csv_path)))
hdr, body = rows[0], rows[1:]
fixed = 0
for r in body:
    s, e, sz = int(r[1], 16), int(r[2], 16), int(r[3])
    if e - s != sz:
        r[2] = f"0x{s + sz:08X}"
        fixed += 1
have = {int(r[1], 16) for r in body}
starts = sorted(have)
added = 0
if os.path.exists(extra_path):
    for line in open(extra_path):
        line = line.split('#')[0].strip()
        if not line:
            continue
        a = int(line, 16)
        if a in have:
            continue
        i = bisect.bisect_right(starts, a)
        nxt = starts[i] if i < len(starts) else a + 0x100
        body.append([f"FUN_{a:08x}", f"0x{a:08X}", f"0x{nxt:08X}", str(nxt - a)])
        added += 1
body.sort(key=lambda r: int(r[1], 16))
with open(csv_path, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(hdr)
    w.writerows(body)
print(f"fix_ghidra_csv: {fixed} ranges fixed, {added} forced entries added, {len(body)} functions")
