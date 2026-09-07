"""Normalize the Ghidra ExportPS2Functions CSV for PS2Recomp:
- Ghidra functions with non-contiguous bodies export End = max address of the body while
  Size = bytes actually in the body; PS2Recomp treats [Start, End) as the function, which
  swallows every function in between.  Force End = Start + Size.
- Append forced entry points listed in recomp/extra_functions.txt (one hex address per line),
  ending at the next known function start.  A forced entry that falls *inside* an existing range
  (two functions Ghidra merged into one) truncates that range, so the two do not overlap.
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
    hole = (e - s) - sz
    # Small holes are cold blocks of other tiny functions inside this one: keep the full
    # range (the recompiler needs the whole body).  Huge holes mean a thunk whose jump
    # target Ghidra merged in: cut to the real size.
    if hole > 0 and (hole > 1024 or hole > sz):
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
        # If a covering range exists, this forced entry is its second function: truncate the
        # parent at `a` and let the new row run to where the parent ended.
        end = nxt
        for r in body:
            rs, re_ = int(r[1], 16), int(r[2], 16)
            if rs < a < re_:
                end = max(end, re_) if re_ <= nxt else re_
                end = re_
                r[2] = f"0x{a:08X}"
                r[3] = str(a - rs)
                break
        body.append([f"FUN_{a:08x}", f"0x{a:08X}", f"0x{end:08X}", str(end - a)])
        added += 1
# recomp/merge_ranges.txt: "0xSTART 0xEND" lines. Every row starting inside [START, END) is folded
# into the row that starts at START (a loop body Ghidra split into a "thunk" row plus a gap plus a
# second row makes the backward branch an unwind to an address no function owns — see
# tools_py/find_escaping_branches.py). Only merge when nothing calls the inner rows directly.
merge_path = os.path.join(os.path.dirname(extra_path), 'merge_ranges.txt')
merged = 0
if os.path.exists(merge_path):
    for line in open(merge_path):
        line = line.split('#')[0].strip()
        if not line:
            continue
        lo, hi = (int(x, 16) for x in line.split())
        keep = []
        for r in body:
            rs = int(r[1], 16)
            if rs == lo:
                r[2] = f"0x{hi:08X}"
                r[3] = str(hi - lo)
                keep.append(r)
            elif lo < rs < hi:
                merged += 1
            else:
                keep.append(r)
        body = keep
body.sort(key=lambda r: int(r[1], 16))
with open(csv_path, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(hdr)
    w.writerows(body)
print(f"fix_ghidra_csv: {fixed} ranges fixed, {added} forced entries added, {merged} rows merged, {len(body)} functions")
