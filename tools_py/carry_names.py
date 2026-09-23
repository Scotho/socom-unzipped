"""Carry one build's function names onto another build's addresses (Sprint 11 Task 19).

`tools_py/address_matcher.py` says which r0004 address each r0001 function landed on. This turns that
report plus r0004's own raw Ghidra export into the function map `scripts/build_revision.sh` wants:

    python -m tools_py.carry_names <match.json> <raw_b.csv> <out.csv>

Every row keeps the B side's own Start, End and Size -- those are facts about the B image and nothing
here may touch them. Only the Name column moves, and only for a name that is worth moving:

**A name that embeds an address is not carried.** Ghidra's own `FUN_00408c58`, `LAB_...`, `caseD_...`,
`thunk_FUN_...` name a function after where it *was*; carried onto a different address the name becomes
a lie, and -- worse -- it can collide with the name B's own export already gave to the function that
really lives there, which would make two different generated functions in `recomp/output_r0004/` claim
one symbol. B's own Ghidra name is the truthful one for those, so they keep it. What is carried is the
names that mean something independently of an address: the 129 SDK and thunk symbols in r0001's map
(`SetGsCrt`, `CreateThread`, `entry`, ...) and any hand-written name added later.

A carry that would duplicate a name already in the output is refused and counted, so the rule above is
enforced rather than assumed. The counts are printed:

    carried N, kept M (auto-named), refused K (name collision), rows R
"""
import argparse
import csv
import json
import re
import sys
from typing import Dict, List, Optional

# An 8-hex-digit run anywhere in the name means the name is derived from an address.
ADDRESSY = re.compile(r"[0-9A-Fa-f]{8}")


def is_addressy(name: str) -> bool:
    """True when the name embeds an address, so it must not travel to a different one."""
    return bool(ADDRESSY.search(name))


def carry(matches: Dict[str, dict], rows: List[dict]) -> Dict[str, int]:
    """Rewrite `rows`' Name column in place from the matcher's report. Returns the counts."""
    wanted: Dict[int, str] = {}
    for _a_addr, m in matches.items():
        b = m.get("b")
        name = m.get("name") or ""
        if not b or not name or is_addressy(name):
            continue
        wanted.setdefault(int(b, 16), name)
    have = {r["Name"] for r in rows}
    counts = {"rows": len(rows), "carried": 0, "kept": 0, "refused": 0}
    for row in rows:
        start = int(row["Start"], 16)
        name = wanted.get(start)
        if name is None:
            counts["kept"] += 1
            continue
        if name == row["Name"]:
            counts["carried"] += 1
            continue
        if name in have:
            counts["refused"] += 1
            continue
        have.discard(row["Name"])
        have.add(name)
        row["Name"] = name
        counts["carried"] += 1
    return counts


def write_csv(path: str, rows: List[dict]) -> None:
    """The exact shape ExportPS2Functions.java writes, which fix_ghidra_csv.py and ps2_recomp read."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write("Name,Start,End,Size\n")
        for r in rows:
            fh.write("%s,0x%08X,0x%08X,%s\n"
                     % (r["Name"], int(r["Start"], 16), int(r["End"], 16), r["Size"]))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("match_json", help="tools_py.address_matcher --out")
    ap.add_argument("raw_csv", help="the B build's own Ghidra export (Name,Start,End,Size)")
    ap.add_argument("out_csv")
    args = ap.parse_args(argv)

    with open(args.match_json, encoding="utf-8") as fh:
        doc = json.load(fh)
    with open(args.raw_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("NO-DATA: empty", args.raw_csv)
        return 2

    counts = carry(doc.get("matches", {}), rows)
    write_csv(args.out_csv, rows)
    print("carried %d, kept %d (auto-named), refused %d (name collision), rows %d"
          % (counts["carried"], counts["kept"], counts["refused"], counts["rows"]))
    print("wrote", args.out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
