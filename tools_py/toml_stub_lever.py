"""The `toml-stub` pass: the toml's own `name@addr` stub selectors as proposals (Sprint 12 Task 8, Goal 6;
docs/research/57-recompiler-naming-pipeline.md §2-§4; S12-R4, S12-R13, S12-R17, S12-R21).

    python -m tools_py.toml_stub_lever recomp/socom2.toml recomp/socom2_ghidra.csv recomp/socom2_names.csv \\
        --out game/demo_symbol_renames_toml.csv [--holds recomp/socom2_name_holds.csv]

`recomp/socom2.toml` names 656 functions as `name@addr` selectors (`[general].stubs`, which the recompiler reads
as its HLE handler selector, and `[general].untracked_stubs`, which nothing reads; `[performance].critical` holds
bare names, and a `name@addr` there would count too). The analyzer's SDK signature scanner gave those names; the
recompiler never uses them to NAME a function (research/57 §2). This pass writes them as a proposals file the
applier (`tools_py/apply_names.py`, Task 3) takes to the sidecar, the one home of a name (S12-R13). It reads
the toml, the Ghidra map and the sidecar and writes only `--out`; it never writes the csv or the sidecar.

`toml_names` returns every selector with its key and line (a line scan, cross-checked against `tomllib`);
`proposals` decides each one by `TOML_STUB_RULE`, in order, and counts it under exactly one `CENSUS` heading.
"""
import argparse
import collections
import csv
import os
import re
import sys
import tomllib
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple

from tools_py import name_provenance as npv
from tools_py.ghidra_symbol_match import c_identifier

PASS = "toml-stub"
SCORE = "0.90"
SOURCE = "research/57"
KEYS = ("general.stubs", "general.untracked_stubs", "performance.critical")

TOML_STUB_RULE = """\
toml-stub RULE (Sprint 12 Task 8, research/57, S12-R4/R13): every name@addr selector in recomp/socom2.toml's
[general].stubs, [general].untracked_stubs and [performance].critical (key and line recorded) is decided in order:
  1. its address is not a start of recomp/socom2_ghidra.csv -> refused: not a csv row (no route names it);
  2. the sidecar already has a row there -> counted: already named, agrees (its Mangled equals the toml name)
     or already named, differs (printed as a finding); no proposal either way;
  3. the csv row's Name is not a placeholder (and the sidecar has no row) -> refused: csv names it (D2);
  4. the toml gives the same address two different names -> refused: address named twice;
  5. the (address, name) pair is on recomp/socom2_name_holds.csv -> refused: held (S12-R17, S12-R21);
  6. otherwise proposed: How=toml-stub, Score=0.90 (the project's own hand names), Mangled=<the toml name>,
     Proposed=c_identifier(<the toml name>) (the applier renders the readable form), Duplicated=<the number of
     toml addresses that carry the name> (a name on several addresses is proposed at each; R10, kept unsuffixed
     only when the demo holds the name that many times, is the applier's render with --demo),
     Evidence="recomp/socom2.toml line <n> (<key>): the project's own stub selector", Source=research/57."""

CENSUS = ("proposed", "already named, agrees", "already named, differs", "not a csv row", "csv names it",
          "address named twice", "held")
COLUMNS = ["Address", "Current", "Proposed", "Mangled", "How", "Score", "Evidence", "Source", "Key", "Line",
           "Duplicated"]

Selector = Tuple[int, str, str, int]      # (address, name, key, line number)


class Result(NamedTuple):
    rows: List[dict]                          # the proposals, by address
    census: Dict[str, int]                    # one count per CENSUS heading; the headings sum to the selectors
    refused: Dict[str, List[Selector]]        # per refusing heading, its selectors
    differs: List[Tuple[int, str, str, int, str]]   # (address, toml name, key, line, the sidecar's Mangled)
    duplicated: Dict[str, List[int]]          # name -> every toml address it sits at (all keys), when several


# ---- the toml ---------------------------------------------------------------------------------------------

_TABLE = re.compile(r"^\s*\[([A-Za-z0-9_.]+)\]\s*(?:#.*)?$")
_ARRAY = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*\[")
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _code(line: str) -> str:
    """`line` without its `#` comment (a `#` inside a string is not one)."""
    pos = 0
    for m in _STRING.finditer(line):
        cut = line.find("#", pos, m.start())
        if cut >= 0:
            return line[:cut]
        pos = m.end()
    cut = line.find("#", pos)
    return line if cut < 0 else line[:cut]


def _selector(text: str) -> Optional[Tuple[str, int]]:
    """`name@addr` split at the LAST `@` (ps2_recompiler.cpp parseFunctionSelector); None without an address."""
    name, at, addr = text.rpartition("@")
    if not at or not name.strip():
        return None
    try:
        return name.strip(), int(addr.strip(), 16)
    except ValueError:
        return None


def toml_names(toml_path: str) -> List[Selector]:
    """Every `name@addr` in `[general].stubs`, `[general].untracked_stubs` and `[performance].critical`, in file
    order, as (address, name, key, line number). The line scan is checked against `tomllib`'s parse of the same
    keys; a difference is a ValueError, never a silently missed selector."""
    with open(toml_path, "rb") as fh:
        raw = fh.read()
    table, key, out = "", None, []
    for no, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if key is None:
            m = _TABLE.match(line)
            if m:
                table = m.group(1)
                continue
            m = _ARRAY.match(line)
            if not m:
                continue
            full = "%s.%s" % (table, m.group(1)) if table else m.group(1)
            if full not in KEYS:
                continue
            key, line = full, line[m.end():]
        code = _code(line)
        for s in _STRING.findall(code):
            sel = _selector(s)
            if sel:
                out.append((sel[1], sel[0], key, no))
        if "]" in _STRING.sub("", code):
            key = None

    doc = tomllib.loads(raw.decode("utf-8"))
    want = []
    for k in KEYS:
        table_name, _, leaf = k.partition(".")
        for v in doc.get(table_name, {}).get(leaf, []) or []:
            sel = _selector(v) if isinstance(v, str) else None
            if sel:
                want.append((sel[1], sel[0], k))
    got = [(a, n, k) for a, n, k, _l in out]
    if sorted(got) != sorted(want):
        raise ValueError("%s: the line scan found %d selectors, tomllib %d" % (toml_path, len(got), len(want)))
    return out


# ---- the decision -----------------------------------------------------------------------------------------

def read_holds(path: str) -> Set[Tuple[int, str]]:
    """recomp/socom2_name_holds.csv as (address, proposed name) pairs (S12-R21: a hold names a pair)."""
    with open(path, newline="", encoding="utf-8") as fh:
        return {(int(r["Address"], 16), r["Proposed"].strip()) for r in csv.DictReader(fh)}


def proposals(selectors: Sequence[Selector], csv_rows: List[dict], sidecar: Dict[int, dict],
              holds: Iterable[Tuple[int, str]] = ()) -> Result:
    """Decide every selector by TOML_STUB_RULE."""
    holds = set(holds)
    starts: Dict[int, str] = {}
    for r in csv_rows:
        starts.setdefault(int(r["Start"], 16), r["Name"])
    at_name: Dict[str, List[int]] = collections.defaultdict(list)
    names_at: Dict[int, Set[str]] = collections.defaultdict(set)
    for a, n, _k, _l in selectors:
        if a not in at_name[n]:
            at_name[n].append(a)
        names_at[a].add(n)
    duplicated = {n: sorted(v) for n, v in at_name.items() if len(v) > 1}

    census = collections.Counter({c: 0 for c in CENSUS})
    refused: Dict[str, List[Selector]] = collections.defaultdict(list)
    differs, rows, seen = [], {}, set()
    for sel in selectors:
        a, n, k, line = sel
        if a not in starts:
            heading = "not a csv row"
        elif a in sidecar:
            if sidecar[a]["Mangled"] == n:
                census["already named, agrees"] += 1
            else:
                census["already named, differs"] += 1
                differs.append((a, n, k, line, sidecar[a]["Mangled"]))
            continue
        elif not npv.is_placeholder(starts[a]):
            heading = "csv names it"
        elif len(names_at[a]) > 1:
            heading = "address named twice"
        elif (a, n) in holds:
            heading = "held"
        elif (a, n) in seen:                   # the same selector under two keys: one proposal
            heading = "proposed"
        else:
            seen.add((a, n))
            census["proposed"] += 1
            rows[a] = {"Address": "0x%08x" % a, "Current": starts[a], "Proposed": c_identifier(n), "Mangled": n,
                       "How": PASS, "Score": SCORE,
                       "Evidence": "recomp/socom2.toml line %d (%s): the project's own stub selector" % (line, k),
                       "Source": SOURCE, "Key": k, "Line": str(line), "Duplicated": str(len(at_name[n]))}
            continue
        census[heading] += 1
        if heading != "proposed":
            refused[heading].append(sel)
    return Result([rows[a] for a in sorted(rows)], dict(census), dict(refused), differs, duplicated)


# ---- the file ---------------------------------------------------------------------------------------------

def header_lines(path: str, result: Result) -> List[str]:
    lines = [
        "%s -- Sprint 12 Task 8 `toml-stub` proposals at Score %s. PROPOSALS ONLY:" % (os.path.basename(path), SCORE),
        "recomp/socom2_ghidra.csv and recomp/socom2_names.csv are unchanged; applying is Task 3's reviewed step,",
        "to the sidecar (S12-R13). Names come from recomp/socom2.toml's own selectors. Addresses are OURS (r0001).",
        "docs/research/57-recompiler-naming-pipeline.md",
        "",
    ]
    lines += TOML_STUB_RULE.splitlines()
    lines += ["", "Census: " + "; ".join("%s %d" % (c, result.census.get(c, 0)) for c in CENSUS),
              "Proposed with a duplicated name (Duplicated > 1): %d" % duplicated_rows(result), ""]
    return lines


def write_proposals(path: str, rows: Sequence[dict], header: Sequence[str]) -> None:
    """The file, its rule in `#` lines above the columns."""
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise ValueError("cannot write %s: %s is not a directory" % (path, directory))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        for line in header:
            fh.write("# %s\n" % line if line else "#\n")
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def duplicated_rows(result: Result) -> int:
    """How many proposals carry a name the toml gives to more than one address."""
    return sum(1 for r in result.rows if int(r["Duplicated"]) > 1)


def report(result: Result, out=None) -> None:
    out = out or sys.stdout
    p = lambda s="": print(s, file=out)
    p("toml-stub census: " + "; ".join("%s %d" % (c, result.census.get(c, 0)) for c in CENSUS))
    p("  total selectors %d" % sum(result.census.get(c, 0) for c in CENSUS))
    for a, n, k, line, mangled in result.differs:
        p("  FINDING already named, differs: 0x%08x toml %s (%s line %d), sidecar Mangled %s" % (a, n, k, line, mangled))
    for heading in CENSUS[3:]:
        for a, n, k, line in result.refused.get(heading, []):
            p("  refused, %s: 0x%08x %s (%s line %d)" % (heading, a, n, k, line))
    p("  proposed with a duplicated name (Duplicated > 1; R10 is the applier's): %d" % duplicated_rows(result))
    for r in result.rows:
        if int(r["Duplicated"]) > 1:
            p("    %s %s Duplicated=%s (the toml puts it at %s)" % (r["Address"], r["Mangled"], r["Duplicated"],
              ", ".join("0x%08x" % x for x in result.duplicated[r["Mangled"]])))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="the toml-stub pass (Sprint 12 Task 8, research/57)")
    ap.add_argument("toml")
    ap.add_argument("ghidra_csv")
    ap.add_argument("names_csv")
    ap.add_argument("--out", default="game/demo_symbol_renames_toml.csv")
    ap.add_argument("--holds", default="recomp/socom2_name_holds.csv")
    args = ap.parse_args(argv)
    for path in (args.toml, args.ghidra_csv, args.names_csv, args.holds):
        if not os.path.exists(path):
            print("NO-DATA: missing %s" % path)
            return 2
    result = proposals(toml_names(args.toml), npv.read_map(args.ghidra_csv), npv.read(args.names_csv),
                       read_holds(args.holds))
    write_proposals(args.out, result.rows, header_lines(args.out, result))
    report(result)
    print("wrote %s: %d rows" % (args.out, len(result.rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
