"""The names sidecar: one row of provenance per readable function name (Sprint 12 Task 2; R261, S12-R7).

`recomp/socom2_ghidra.csv` (and `recomp/socom2_ghidra_r0004.csv`) hold the function map the recompiler reads,
`Name,Start,End,Size`. A name there that is not a placeholder must say where it came from, and that is this
file's job: `recomp/socom2_names.csv` (and `recomp/socom2_names_r0004.csv`), one row per address:

    Address,Name,Mangled,Pass,Score,Evidence,Source,Date

Plain CSV: the column line first, no `#` line, `Address` as `0x%08x`, rows sorted by address, fields quoted
only where csv needs it (research/48 "The sidecar, decided"). It holds addresses, names and text only.

**The audit** (`audit`, and `python -m tools_py.name_provenance audit <ghidra.csv> <names.csv>`, exit 1 on a
finding): every csv row whose `Name` is not a placeholder has exactly one sidecar row with its `Address` and
`Name`; every sidecar row names a csv start. A sidecar row on a placeholder csv `Name` is a rename (S12-R13,
research/57: the recompiler reads display names from this file and the csv's `Name` column is never
rewritten), so it is allowed, but its own `Name` must not be a placeholder and must look legal
(`[A-Za-z_][A-Za-z0-9_]*`). It keys on `Address`, not `Name`: three Ghidra syscall names already repeat over
ten rows and build, because the generator suffixes `_0x<start>` (research/48 §1).

**A placeholder** is a name a tool made, not a name anyone chose. The predicate is anchored (research/48 §4):
`FUN_`/`LAB_`/`DAT_`/`SUB_`/`sub_` + 8 hex, `thunk_FUN_`/`thunk_EXT_FUN_` + 8 hex, `caseD_<hex>`,
`switchD_` + 8 hex, or `entry`. An unanchored 8-hex run would call `RTArray_Q23zdb6CDecal__ctor` and
`C2DBitmapPoly_SetUV_ffffffff` placeholders and miss `caseD_6`. `tools_py/carry_names.py` refuses to carry
the same set.
"""
import argparse
import csv
import re
import sys
from typing import Dict, Iterable, List, Optional

COLUMNS = ["Address", "Name", "Mangled", "Pass", "Score", "Evidence", "Source", "Date"]

# Names that are made from the address they sit at (Ghidra's and ps2recomp's shapes), and `entry`, which names
# no address but is Ghidra's label for the ELF entry point.
ADDRESS_NAME = re.compile(r"^(?:(?:FUN|LAB|DAT|SUB|sub)_[0-9A-Fa-f]{8}|thunk_(?:EXT_)?FUN_[0-9A-Fa-f]{8}"
                          r"|caseD_[0-9A-Fa-f]+|switchD_[0-9A-Fa-f]{8})$")


def is_address_name(name: str) -> bool:
    """True for a placeholder built from an address (every placeholder except `entry`)."""
    return bool(ADDRESS_NAME.match(name))


def is_placeholder(name: str) -> bool:
    """True for a tool-made name: it needs no sidecar row and never travels to another build."""
    return name == "entry" or is_address_name(name)


def _addr(text: str) -> int:
    return int(text, 16)


def read(path: str) -> Dict[int, dict]:
    """The sidecar as {address: row}; `row["Address"]` is an int. A repeated address or a wrong column line
    is a ValueError: the file is one row per address, and nothing else."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != COLUMNS:
            raise ValueError("%s: column line %r, want %r" % (path, reader.fieldnames, COLUMNS))
        out: Dict[int, dict] = {}
        for row in reader:
            a = _addr(row["Address"])
            if a in out:
                raise ValueError("%s:%d: address 0x%08x repeats" % (path, reader.line_num, a))
            row["Address"] = a
            out[a] = row
    return out


def write(path: str, rows: Iterable[dict]) -> None:
    """Write sidecar rows (Address an int or a hex string) sorted by address, one per address."""
    norm = []
    for r in rows:
        a = r["Address"] if isinstance(r["Address"], int) else _addr(r["Address"])
        norm.append((a, r))
    norm.sort(key=lambda x: x[0])
    for (a, _), (b, _) in zip(norm, norm[1:]):
        if a == b:
            raise ValueError("address 0x%08x repeats" % a)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLUMNS)
        for a, r in norm:
            w.writerow(["0x%08x" % a] + [r.get(c, "") or "" for c in COLUMNS[1:]])


def read_map(path: str) -> List[dict]:
    """A Ghidra function map (`Name,Start,End,Size`) as DictReader rows."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


LEGAL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def audit(csv_rows: List[dict], sidecar: Dict[int, dict]) -> List[str]:
    """The findings, one line each; empty when the csv and the sidecar agree (a row on a placeholder csv Name
    is a rename to a legal, non-placeholder name)."""
    findings = []
    names = {}
    for r in csv_rows:
        names.setdefault(_addr(r["Start"]), r["Name"])
    for a in sorted(names):
        n = names[a]
        row = sidecar.get(a)
        if is_placeholder(n):
            if row is None:
                continue
            if is_placeholder(row["Name"]):
                findings.append("0x%08x: %s is renamed to the placeholder %s" % (a, n, row["Name"]))
            elif not LEGAL_NAME.match(row["Name"]):
                findings.append("0x%08x: %s is renamed to the illegal name %r" % (a, n, row["Name"]))
        elif row is None:
            findings.append("0x%08x: %s has no sidecar row" % (a, n))
        elif row["Name"] != n:
            findings.append("0x%08x: the csv says %s, the sidecar says %s" % (a, n, row["Name"]))
    for a in sorted(set(sidecar) - set(names)):
        findings.append("0x%08x: sidecar row %s names no csv address" % (a, sidecar[a]["Name"]))
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    au = sub.add_parser("audit", help="every non-placeholder csv Name has its one sidecar row with that Name; every sidecar "
                        "row names a csv start; a row on a placeholder is a rename to a legal, non-placeholder name")
    au.add_argument("ghidra_csv")
    au.add_argument("names_csv")
    args = ap.parse_args(argv)

    rows = read_map(args.ghidra_csv)
    side = read(args.names_csv)
    findings = audit(rows, side)
    for f in findings:
        print(f)
    print("audit %s against %s: %d csv rows, %d sidecar rows, %d findings"
          % (args.ghidra_csv, args.names_csv, len(rows), len(side), len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
