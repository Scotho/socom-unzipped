"""Does link order survive between the SOCOM 1 demo and our image? (Task 7 review, socom-pc-6c)

Run from the repo root:  python <this file>

Reads game/demo_symbol_matches.json (Task 7's 987 pairs), the demo ELF's .symtab and
recomp/socom2_ghidra.csv. Prints, per PT_LOAD region of ours, how many consecutive pairs (sorted by
our address) keep the demo's address order, the whole-image longest increasing subsequence, and the
anchor-gap census: gaps between consecutive pairs where both builds hold the same number of
function starts, i.e. the functions that could be named by position.
"""
import bisect
import collections
import csv
import json
import os
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py.elf_symbols import read_elf  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
MATCHES = "game/demo_symbol_matches.json"
OURS = "recomp/socom2_ghidra.csv"
REGIONS = [(0x100000, 0x1D5000), (0x1E7000, 0x408480), (0x4C5380, 0x66A000)]


def main() -> None:
    elf = read_elf(DEMO)
    by_name = collections.defaultdict(list)
    for start, _end, name in elf.functions:
        by_name[name].append(start)
    demo_starts = sorted(start for start, _end, _name in elf.functions)
    our_starts = sorted(int(r["Start"], 16) for r in csv.DictReader(open(OURS)))

    pairs = json.load(open(MATCHES))["pairs"]
    # (our address, demo address); demo names that occur twice are skipped (1 collision)
    pp = sorted((int(p["addr"], 16), by_name[p["name"]][0])
                for p in pairs if len(by_name[p["name"]]) == 1)

    for lo, hi in REGIONS:
        seq = [d for o, d in pp if lo <= o < hi]
        asc = sum(1 for a, b in zip(seq, seq[1:]) if b > a)
        print(f"region {lo:#x}-{hi:#x}: pairs {len(seq)}, consecutive in demo order "
              f"{asc}/{max(1, len(seq) - 1)} ({asc / max(1, len(seq) - 1):.1%})")

    tails: list = []
    for _o, d in pp:
        i = bisect.bisect_left(tails, d)
        if i == len(tails):
            tails.append(d)
        else:
            tails[i] = d
    print(f"whole-image LIS {len(tails)} of {len(pp)} (low because the demo's one PT_LOAD "
          f"interleaves our three overlays; use the per-region figures)")

    def between(lst, a, b):
        return bisect.bisect_left(lst, b) - bisect.bisect_right(lst, a)

    gaps = equal = nameable = 0
    sizes = collections.Counter()
    for (o1, d1), (o2, d2) in zip(pp, pp[1:]):
        if d2 <= d1:
            continue
        gaps += 1
        co, cd = between(our_starts, o1, o2), between(demo_starts, d1, d2)
        if co == cd and co > 0:
            equal += 1
            nameable += co
            sizes[co] += 1
    print(f"ordered anchor gaps {gaps}; gaps with equal function counts on both sides {equal}; "
          f"functions nameable by position {nameable}")
    print("gap sizes (functions per gap -> gaps):", sorted(sizes.items()))


if __name__ == "__main__":
    main()
