"""Carry one build's function names onto another build's addresses (Sprint 11 Task 19).

`tools_py/address_matcher.py` says which r0004 address each r0001 function landed on. This turns that
report plus r0004's own raw Ghidra export into the function map `scripts/build_revision.sh` wants:

    python -m tools_py.carry_names <match.json> <raw_b.csv> <out.csv>

Every row keeps the B side's own Start, End and Size -- those are facts about the B image and nothing
here may touch them. Only the Name column moves, and only for a name that is worth moving:

**A placeholder is not carried.** Ghidra's own `FUN_00408c58`, `LAB_...`, `caseD_6`, `thunk_FUN_...` name a
function after where it *was* (or, for `entry`, after what Ghidra guessed); carried onto a different address
the name becomes a lie, and -- worse -- it can collide with the name B's own export already gave to the
function that really lives there, which would make two different generated functions in
`recomp/output_r0004/` claim one symbol. B's own Ghidra name is the truthful one for those, so they keep it.
The rule is `name_provenance.is_placeholder`, the anchored predicate the sidecar audit uses (Sprint 12 Task 2,
research/48 §4). It replaced an 8-hex run anywhere in the name, which was wrong both ways: it let `caseD_<n>`
travel (6 of r0004's `caseD_` labels sit at a different r0001 address) and it silently dropped the readable
`C2DBitmapPoly_SetUV_ffffffff`. What is carried is the names that mean something independently of an
address: the 69 EE kernel syscall stubs in r0001's map (`SetGsCrt`, `CreateThread`, ...) and every readable
name applied later.

A carry that would duplicate a name already in the output is refused and counted, so the rule above is
enforced rather than assumed. A placed name refused for being a placeholder is counted too, separately. The
counts are printed:

    carried N, kept M (auto-named), refused K (name collision), refused P (placeholder), rows R

**The names sidecar travels with the names** (`--names <a_names.csv> --names-out <b_names.csv>`, both or
neither; the file is `tools_py/name_provenance.py`'s). Every carried name gets a B row with the A row's
`Mangled`, `Score`, `Source` and `Date`, `Pass=carried:<A pass>` and `Evidence=match.json <how> from
0x<A addr>; <A evidence>`. A carried name with no A row of that address and name is a defect (R261): it is
printed, no B row is written for it, and the exit is 1.

**The sidecar's renames travel too** (S12-R13: a display name lives in the sidecar, and the csv's Name is not
rewritten). An A sidecar row on a placeholder A csv name (match.json's `name` is the A csv name) gets a B row
the same way, when match.json places it on a B row still auto-named and no other A rename lands there; the B
csv keeps its placeholder. Counted apart: `carried (sidecar renames) N, refused (sidecar renames) K`.
"""
import argparse
import csv
import json
import sys
from typing import Dict, List, Optional, Tuple

from tools_py import name_provenance

# (B start, A start, match.json `how`, name) for one carried name
Carried = Tuple[int, int, str, str]


def is_addressy(name: str) -> bool:
    """True when the name is built from an address (`name_provenance.is_address_name`; `entry` is not)."""
    return name_provenance.is_address_name(name)


def carry_with_origin(matches: Dict[str, dict], rows: List[dict]) -> Tuple[Dict[str, int], List[Carried]]:
    """Rewrite `rows`' Name column in place from the matcher's report. Returns the counts and, for every name
    carried, where it came from."""
    counts = {"rows": len(rows), "carried": 0, "kept": 0, "refused": 0, "refused_placeholder": 0}
    wanted: Dict[int, Tuple[str, int, str]] = {}
    for a_addr, m in matches.items():
        b = m.get("b")
        name = m.get("name") or ""
        if not b or not name:
            continue
        if name_provenance.is_placeholder(name):
            counts["refused_placeholder"] += 1
            continue
        wanted.setdefault(int(b, 16), (name, int(a_addr, 16), m.get("how") or ""))
    have = {r["Name"] for r in rows}
    carried: List[Carried] = []
    for row in rows:
        start = int(row["Start"], 16)
        want = wanted.get(start)
        if want is None:
            counts["kept"] += 1
            continue
        name, a_addr, how = want
        if name != row["Name"]:
            if name in have:
                counts["refused"] += 1
                continue
            have.discard(row["Name"])
            have.add(name)
            row["Name"] = name
        counts["carried"] += 1
        carried.append((start, a_addr, how, name))
    return counts, carried


def carry(matches: Dict[str, dict], rows: List[dict]) -> Dict[str, int]:
    """Rewrite `rows`' Name column in place from the matcher's report. Returns the counts."""
    return carry_with_origin(matches, rows)[0]


def carry_names_sidecar(carried: List[Carried], a_names: Dict[int, dict]) -> Tuple[List[dict], List[str]]:
    """The B sidecar rows for the carried names, and a line for each carried name with no A row."""
    out, missing = [], []
    for b, a, how, name in carried:
        src = a_names.get(a)
        if src is None or src["Name"] != name:
            missing.append("0x%08x %s (from 0x%08x): no A sidecar row with this name" % (b, name, a))
            continue
        out.append({"Address": b, "Name": name, "Mangled": src["Mangled"], "Pass": "carried:" + src["Pass"],
                    "Score": src["Score"], "Evidence": "match.json %s from 0x%08x; %s" % (how, a, src["Evidence"]),
                    "Source": src["Source"], "Date": src["Date"]})
    return out, missing


def carry_sidecar_renames(matches: Dict[str, dict], rows: List[dict],
                          a_names: Dict[int, dict]) -> Tuple[List[dict], int]:
    """S12-R13: the B sidecar rows for the A sidecar's renames, and how many were refused.

    A rename is an A sidecar row whose A csv Name is a placeholder (match.json's `name` for that address is the
    A csv name). It travels when match.json places its address on a B row whose (already carried) Name is still
    a placeholder and no other A rename lands there; both of two renames on one B address are refused. The B
    csv is not rewritten for these: a display name lives in the sidecar only."""
    b_names = {int(r["Start"], 16): r["Name"] for r in rows}
    want: Dict[int, List[Tuple[int, str]]] = {}
    refused = 0
    for a, src in sorted(a_names.items()):
        m = matches.get("0x%08x" % a)
        if m is None or not name_provenance.is_placeholder(m.get("name") or ""):
            continue                                     # not placed, or not a rename: the Name carry's job
        b = m.get("b")
        if not b:
            continue                                     # unresolved: stays A-only
        want.setdefault(int(b, 16), []).append((a, m.get("how") or ""))
    out = []
    for b, srcs in sorted(want.items()):
        if len(srcs) > 1 or b not in b_names or not name_provenance.is_placeholder(b_names[b]):
            refused += len(srcs)
            continue
        a, how = srcs[0]
        src = a_names[a]
        out.append({"Address": b, "Name": src["Name"], "Mangled": src["Mangled"], "Pass": "carried:" + src["Pass"],
                    "Score": src["Score"], "Evidence": "match.json %s from 0x%08x; %s" % (how, a, src["Evidence"]),
                    "Source": src["Source"], "Date": src["Date"]})
    return out, refused


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
    ap.add_argument("--names", metavar="A_NAMES_CSV", help="the A build's names sidecar")
    ap.add_argument("--names-out", metavar="B_NAMES_CSV", help="where to write the B build's names sidecar")
    args = ap.parse_args(argv)
    if (args.names is None) != (args.names_out is None):
        ap.error("--names and --names-out come together")

    with open(args.match_json, encoding="utf-8") as fh:
        doc = json.load(fh)
    with open(args.raw_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("NO-DATA: empty", args.raw_csv)
        return 2

    a_names = name_provenance.read(args.names) if args.names else None
    counts, carried = carry_with_origin(doc.get("matches", {}), rows)
    write_csv(args.out_csv, rows)
    print("carried %d, kept %d (auto-named), refused %d (name collision), refused %d (placeholder), rows %d"
          % (counts["carried"], counts["kept"], counts["refused"], counts["refused_placeholder"], counts["rows"]))
    print("wrote", args.out_csv)
    if a_names is None:
        return 0
    b_rows, missing = carry_names_sidecar(carried, a_names)
    renamed, refused = carry_sidecar_renames(doc.get("matches", {}), rows, a_names)
    name_provenance.write(args.names_out, b_rows + renamed)
    for line in missing:
        print("NO-PROVENANCE:", line)
    print("carried (sidecar renames) %d, refused (sidecar renames) %d (B address named or shared)"
          % (len(renamed), refused))
    print("names sidecar: %d rows, %d carried names without an A row" % (len(b_rows) + len(renamed), len(missing)))
    print("wrote", args.names_out)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
