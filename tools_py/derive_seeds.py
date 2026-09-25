"""Sprint 12 Task 5 (S12-R5): derive address_matcher's `--seed` list from its own seedless run.

The matcher's last pass, seed+delta, tries the offset of every seed pair on each function the
fingerprint passes left over, and keeps a placement only where the other image has a function starting
there with the same fingerprint and length. The offsets that work are the ones the relink actually used,
and the seedless run already shows them: every `exact` placement is one (b - a). So the seed list is a
pure function of a seedless match.json, and the r0004 rate is reproducible from tracked inputs:

    python -m tools_py.address_matcher game/disc/socom2_game.elf recomp/socom2_ghidra.csv \\
        game/overlays_r0004/socom2_game_r0004.elf recomp/socom2_ghidra_r0004.csv \\
        --out game/r0004/match_noseed.json
    python -m tools_py.derive_seeds game/r0004/match_noseed.json --out recomp/r0004_seeds.txt
    python -m tools_py.address_matcher game/disc/socom2_game.elf recomp/socom2_ghidra.csv \\
        game/overlays_r0004/socom2_game_r0004.elf recomp/socom2_ghidra_r0004.csv \\
        $(sed 's/^/--seed /' recomp/r0004_seeds.txt | grep -v '^--seed #') --out game/r0004/match.json

One seed per distinct offset among the `exact` placements, the seed being the lowest-address pair with
that offset, most frequent offset first, ties by ascending offset. The matcher tries the offsets in the
order given, so the order is part of the result. Only `exact` counts: on the r0004 pair, adding the
`hash+callees` offsets gains three functions but re-pairs four seed+delta placements -- it does not
"never hurt", so it is left out. The seedless run's passes 1-3 are unchanged by seeds, so re-deriving
from the seeded run gives the same list.

The seed file is address pairs only -- one `0x%08X=0x%08X` per line under one `#` header line naming the
command and the two maps' row counts. No game bytes.
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter
from typing import Dict, List, Optional, Tuple

Seed = Tuple[int, int]
HOWS = ("exact",)


def _rows(match: dict) -> Dict[str, dict]:
    """The per-A-address rows, from a whole match.json or its bare `matches` mapping."""
    rows = match.get("matches", match)
    return rows if isinstance(rows, dict) else {}


def _offsets(match: dict) -> Tuple[Counter, Dict[int, int]]:
    """(count per offset, lowest a per offset) over the `exact` placements."""
    count: Counter = Counter()
    lowest: Dict[int, int] = {}
    for a_text, row in _rows(match).items():
        if not isinstance(row, dict) or row.get("how") not in HOWS or row.get("b") is None:
            continue
        a, b = int(a_text, 16), int(row["b"], 16)
        d = b - a
        count[d] += 1
        if d not in lowest or a < lowest[d]:
            lowest[d] = a
    return count, lowest


def offset_histogram(match: dict) -> List[Tuple[int, int]]:
    """[(offset, count)] over the `exact` placements, most frequent first, ties by ascending offset."""
    count, _lowest = _offsets(match)
    return sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))


def derive_seeds(match: dict, min_count: int = 1) -> List[Seed]:
    """One (a, b) per distinct `exact` offset seen at least `min_count` times, in histogram order."""
    _count, lowest = _offsets(match)
    return [(lowest[d], lowest[d] + d) for d, n in offset_histogram(match) if n >= min_count]


def write_seeds(path: str, seeds: List[Seed], header: str = "") -> None:
    """One `0x%08X=0x%08X` per line, under a single `# header` line."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# %s\n" % " ".join(header.split()))
        for a, b in seeds:
            fh.write("0x%08X=0x%08X\n" % (a, b))


def read_seeds(path: str) -> List[Seed]:
    """The pairs in a seed file, in order; `#` lines and blank lines are not seeds."""
    out: List[Seed] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            lhs, sep, rhs = line.partition("=")
            if not sep:
                raise ValueError("a seed is 0xA=0xB, not %r" % line)
            out.append((int(lhs, 16), int(rhs, 16)))
    return out


def _row_count(csv_path: Optional[str]) -> str:
    if not csv_path or not os.path.exists(csv_path):
        return "?"
    with open(csv_path, newline="") as fh:
        return str(sum(1 for _ in csv.DictReader(fh)))


def _signed(d: int) -> str:
    return "%s0x%08X" % ("-" if d < 0 else "+", abs(d))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("match", help="a seedless address_matcher --out report")
    ap.add_argument("--out", required=True, help="the seed file to write, e.g. recomp/r0004_seeds.txt")
    ap.add_argument("--min-count", type=int, default=1, metavar="N",
                    help="keep only offsets seen at least N times among the exact placements")
    args = ap.parse_args(argv)

    if not os.path.exists(args.match):
        print("NO-DATA: missing", args.match)
        return 2
    with open(args.match, encoding="utf-8") as fh:
        doc = json.load(fh)
    hist = offset_histogram(doc)
    seeds = derive_seeds(doc, args.min_count)
    a_csv = (doc.get("a") or {}).get("csv")
    b_csv = (doc.get("b") or {}).get("csv")
    command = "python -m tools_py.derive_seeds %s --out %s%s" % (
        args.match, args.out, "" if args.min_count == 1 else " --min-count %d" % args.min_count)
    header = "%s; a %s: %s rows; b %s: %s rows; %d exact placements, %d offsets, %d seeds" % (
        command, a_csv, _row_count(a_csv), b_csv, _row_count(b_csv), sum(n for _d, n in hist),
        len(hist), len(seeds))
    write_seeds(args.out, seeds, header)

    lowest = dict((b - a, a) for a, b in seeds)
    print("%d seeds (%d distinct exact offsets, min-count %d)" % (len(seeds), len(hist), args.min_count))
    print("top offsets:")
    for d, n in hist[:10]:
        a = lowest.get(d)
        print("  %s x%d%s" % (_signed(d), n, "" if a is None else "  seed 0x%08X=0x%08X" % (a, a + d)))
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
