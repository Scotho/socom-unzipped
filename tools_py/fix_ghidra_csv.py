"""Normalize the Ghidra ExportPS2Functions CSV for PS2Recomp:
- Ghidra functions with non-contiguous bodies export End = max address of the body while
  Size = bytes actually in the body; PS2Recomp treats [Start, End) as the function, which
  swallows every function in between.  Force End = Start + Size.
- Append forced entry points listed in recomp/extra_functions.txt (one hex address per line),
  ending at the next known function start.  A forced entry that falls *inside* an existing range
  (two functions Ghidra merged into one) truncates that range, so the two do not overlap.
Usage: python fix_ghidra_csv.py <map.csv> <extra_functions.txt> --out <fixed.csv>

--out is required and may not name the map itself: the fixed rows are a build PRODUCT and the map stays a source
file, so a build leaves nothing modified in git status. build.sh's recomp step writes
recomp/build/socom2_ghidra.fixed.csv and scripts/build_revision.sh step 0 recomp/build/socom2_ghidra_<rev>.fixed.csv,
both git-ignored. Until Sprint 13 Task C5 a call without --out rewrote the map IN PLACE, which is what build.sh's
r0001 lane did on every recomp (issue #54 is the footprint that left in the tracked map).
"""
import bisect
import csv
import os
import sys

USAGE = "usage: fix_ghidra_csv.py <map.csv> <extra_functions.txt> --out <fixed.csv>"
out_path = None
positional = []
argv = sys.argv[1:]
i = 0
while i < len(argv):
    arg = argv[i]
    if arg in ("-h", "--help"):
        print(USAGE)
        print(__doc__)
        sys.exit(0)
    if arg == "--out":
        if i + 1 >= len(argv):
            sys.exit("fix_ghidra_csv: --out needs a path\n" + USAGE)
        out_path, i = argv[i + 1], i + 2
        continue
    if arg.startswith("--out="):
        out_path, i = arg[len("--out="):], i + 1
        continue
    if arg.startswith("-"):
        sys.exit(f"fix_ghidra_csv: unknown option {arg}\n" + USAGE)
    positional.append(arg)
    i += 1
if len(positional) != 2:
    sys.exit(USAGE)
csv_path, extra_path = positional
if out_path is None:
    sys.exit("fix_ghidra_csv: --out is required -- the map is a source and is never rewritten in place "
             "(build.sh and build_revision.sh write recomp/build/)\n" + USAGE)
if os.path.normcase(os.path.abspath(out_path)) == os.path.normcase(os.path.abspath(csv_path)):
    sys.exit("fix_ghidra_csv: --out names the map itself -- write the fixed rows somewhere else "
             "(recomp/build/ is git-ignored)\n" + USAGE)
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
    forced = set()
    for line in open(extra_path):
        line = line.split('#')[0].strip()
        if line:
            forced.add(int(line, 16))
    # Ascending and once each (Sprint 13 H7): the file is not sorted, and an entry placed before a LOWER one in
    # the same gap ran to the next map start while the lower one then ran over it -- two overlapping rows; an
    # address listed twice was two rows. In ascending order a later entry in the same gap is covered by the
    # row the earlier one made and splits it below.
    for a in sorted(forced - have):
        i = bisect.bisect_right(starts, a)
        nxt = starts[i] if i < len(starts) else a + 0x100
        # If a covering range exists, this forced entry is its second function: truncate the
        # parent at `a` and let the new row run to where the parent ended.
        end = nxt
        for r in body:
            rs, re_ = int(r[1], 16), int(r[2], 16)
            if rs < a < re_:
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
out_dir = os.path.dirname(out_path)
if out_dir:
    os.makedirs(out_dir, exist_ok=True)
with open(out_path, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(hdr)
    w.writerows(body)
print(f"fix_ghidra_csv: {fixed} ranges fixed, {added} forced entries added, {merged} rows merged, "
      f"{len(body)} functions -> {out_path}")
