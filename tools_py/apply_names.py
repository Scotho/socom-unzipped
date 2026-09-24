"""The applier: proposals files -> readable names in the names sidecar (Sprint 12 Task 3; S12-R13, S12-R18).

The ONLY writer of `recomp/socom2_names.csv`'s applied rows. `recomp/socom2_ghidra.csv` is read, never written
(S12-R13: a csv `Name` is function identity in this recompiler; the sidecar's `Name` is only the identifier the
recompiler emits):

    python -m tools_py.apply_names recomp/socom2_ghidra.csv recomp/socom2_names.csv \\
        game/demo_symbol_renames.csv game/demo_symbol_renames_7b.csv ... \\
        [--holds recomp/socom2_name_holds.csv] [--demo game/demo_scus_972_05/SCUS_972.05] \\
        [--report-only] [--strict] [--date YYYY-MM-DD]

Every proposals file a lever writes is read (`read_proposals`, tolerant of each lever's columns). Per address,
every proposal is gathered and ONE outcome decided (`plan`), in this order:

0. an existing sidecar row whose (Address, Mangled) is a holds-file (Address, Proposed) pair is REMOVED
   and printed `UN-APPLIED by hold` (S12-R24: a hold can un-apply);
1. not a csv start -> `refused: not a csv start`;
2. a proposal whose (Address, Mangled) is a holds-file (Address, Proposed) pair -> `held` (printed with the
   hold's reason; S12-R9, S12-R17, S12-R20); another name at a held address is judged like any other (S12-R21);
3. a csv `Name` that is not a placeholder -> `refused: csv already names it` (D2);
4. already in the sidecar: the same `Mangled` -> `noop`; another -> `refused: sidecar disagrees` (a rename
   of a rename is a hand edit);
5. proposals whose `Mangled` are equal after lower-casing and stripping a leading `socom2_` (the project's
   prefix in the toml) are an ALIAS: one name, the unprefixed spelling, every pass joined (S12-R24);
   otherwise proposals disagreeing on `Mangled` -> every one `contradiction`, printed with each file
   (S12-R18); a loose row counts here too, the safe direction;
6. all agreeing: applied when at least one row is STRICT; a loose row joins it only when its lever family
   differs from every strict row's (the promotion rule: two keys agreeing; a loose row plus another loose row
   is not promotion); loose-only -> `deferred: loose without a second lever`. `Pass` = the agreeing passes
   joined with `&` in file order (`+` is inside pass names), `Score` = the max, `Evidence` =
   `<pass>: <evidence>` joined with ` | `, `Source` likewise;
7. rendering: `readable_names.render` over the survivors, one entry per address, with `taken` = every
   non-placeholder csv Name + every sidecar Name and `demo_counts` from the demo's `.symtab` (`--demo`); a
   render refusal is `refused: <its reason>`, and R10's (one mangled name at k addresses, the demo holding it
   fewer times) reads `refused: one name, two addresses (...)`; a name the sidecar already holds at another
   address is refused the same way; `is_legal` is re-checked on every final name.

Nothing is written until the whole plan is computed AND `name_provenance.audit` over (csv, old sidecar + new
rows) is empty; otherwise nothing is written and the exit is 2 with the findings. Exit 1 with `--strict` when
anything was refused (a contradiction is a refusal), else 0. A held, refused, deferred or contradicted address
is always printed, never silently skipped. The census is printed per file and in total.
"""
import argparse
import collections
import csv
import datetime
import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional

from tools_py import name_provenance as npv
from tools_py import readable_names as rn

LOOSE_DEFAULT = 0.75
PROJECT_PREFIX = "socom2_"   # the project's own prefix in the toml's stub names (S12-R24's alias rule)
PASS_JOIN = "&"      # agreeing passes (S12-R18); `+` is inside pass names (`prefix+offsets`, `hash+callees`)
# A strict file that has no Score column: the pass's score from spec §1.4's table.
PASS_SCORE = {"positional": 0.80}
# A proposals file with no `#` header cites no note; the note that produced it.
NOTE_FALLBACK = {"demo_symbol_renames.csv": "research/44"}
# Files whose lever shares a key: one family (prefix+offsets and offset-multiset are both research/54's K1).
FAMILY_ALIAS = {"prefix_offsets": "offsets", "ui_derived": "ui"}

_NOTE = re.compile(r"docs/research/(\d+)-[A-Za-z0-9_.-]*?\.md")
_LOOSE_SCORE = re.compile(r"[Ss]core (\d\.\d+)")
STATUSES = ("applied", "noop", "held", "deferred", "refused", "contradiction")


class Proposal(NamedTuple):
    address: int
    mangled: str        # the demo's spelling; for a ui-binding-derived row the plain derived name
    pass_name: str
    score: float
    evidence: str
    source: str         # the file's basename + the note its header cites
    loose: bool
    file: str           # the file's basename
    family: str         # the lever family (the basename without `demo_symbol_renames`, `_loose`, aliases)


class Decision(NamedTuple):
    address: int
    status: str         # one of STATUSES
    reason: str
    proposals: List[Proposal]


class Plan(NamedTuple):
    decisions: List[Decision]       # one per proposed address, by address
    rows: List[dict]                # the new sidecar rows (no Date yet), by address
    findings: List[str]             # name_provenance.audit over (csv, kept sidecar + rows)
    sidecar: Dict[int, dict]        # the old sidecar less the rows a hold un-applies
    unapplied: List[dict] = []      # S12-R24: old sidecar rows whose (Address, Mangled) is a hold pair


def _family(base: str) -> str:
    stem = os.path.splitext(base)[0]
    stem = stem[len("demo_symbol_renames"):] if stem.startswith("demo_symbol_renames") else stem
    stem = stem.strip("_")
    if stem.endswith("_loose"):
        stem = stem[:-len("_loose")]
    elif stem == "loose":
        stem = ""
    stem = stem or "task7"
    return FAMILY_ALIAS.get(stem, stem)


def read_proposals(path: str) -> List[Proposal]:
    """One Proposal per data row of a lever's proposals file (its `#` lines are the header)."""
    base = os.path.basename(path)
    with open(path, newline="", encoding="utf-8") as fh:
        lines = fh.readlines()
    header = "".join(l for l in lines if l.startswith("#"))
    body = [l for l in lines if not l.startswith("#")]
    notes = []
    for n in _NOTE.findall(header):
        if "research/" + n not in notes:
            notes.append("research/" + n)
    if not notes and base in NOTE_FALLBACK:
        notes = [NOTE_FALLBACK[base]]
    source = base + ("; " + ", ".join(notes) if notes else "")
    file_loose = "_loose" in base
    loose_score = LOOSE_DEFAULT
    for line in header.splitlines():
        m = _LOOSE_SCORE.search(line)
        if m and "loose" in line.lower() and "strict" not in line.lower():
            loose_score = float(m.group(1))
            break
    family = _family(base)

    out = []
    reader = csv.DictReader(body)
    cols = set(reader.fieldnames or ())
    for row in reader:
        g = lambda k: (row.get(k) or "").strip()
        addr = int(g("Address"), 16)
        mangled = g("Mangled") or g("Proposed")
        if "Tier" in cols:                                         # Task 7b: its pass is its Source column
            pass_name = g("Pass") or g("How") or g("Source")
            evidence = "%s; %s; keypeers=%s; ratio=%s; gap=%s" % (g("Tier"), g("Evidence"), g("KeyPeers"),
                                                                   g("Ratio"), g("GapSize"))
        else:
            pass_name = g("Pass") or g("How")
            if "Class" in cols:                                    # Task 7c
                evidence = "vtable %s slot %s; fixed points %s; ratio=%s" % (g("Class"), g("Slot"),
                                                                            g("FixedPoints"), g("Ratio"))
            elif "Evidence" in cols:
                evidence = g("Evidence")
            else:                                                  # Task 7
                evidence = "fingerprint %s, %s B" % (g("How"), g("Size"))
        if not pass_name:
            raise ValueError("%s:%d: no pass (How/Pass/Source column)" % (path, reader.line_num))
        empty_score = "Score" in cols and not g("Score")
        loose = file_loose or g("Level") == "loose" or empty_score
        if g("Score"):
            score = float(g("Score"))
        elif loose:
            score = loose_score
        elif pass_name in PASS_SCORE:
            score = PASS_SCORE[pass_name]
        else:
            raise ValueError("%s:%d: a strict row with no score" % (path, reader.line_num))
        out.append(Proposal(addr, mangled, pass_name, score, evidence, source, loose, base, family))
    return out


def alias_key(mangled: str) -> str:
    """S12-R24: two spellings are one name when equal after lower-casing and stripping `socom2_`."""
    k = mangled.lower()
    return k[len(PROJECT_PREFIX):] if k.startswith(PROJECT_PREFIX) else k


def _uniq(items):
    out = []
    for i in items:
        if i not in out:
            out.append(i)
    return out


def plan(csv_rows: List[dict], sidecar: Dict[int, dict], holds: Dict[int, dict], proposals: List[Proposal],
         demo_counts: Optional[Dict[str, int]] = None) -> Plan:
    """The whole decision, per address; nothing is written here."""
    demo_counts = demo_counts or {}
    unapplied = [dict(r, Reason=holds[a].get("Reason", "")) for a, r in sorted(sidecar.items())
                 if a in holds and r.get("Mangled") and r["Mangled"] == holds[a].get("Proposed", "")]
    sidecar = {a: r for a, r in sidecar.items() if a not in {u["Address"] for u in unapplied}}
    names: Dict[int, str] = {}
    for r in csv_rows:
        names.setdefault(int(r["Start"], 16), r["Name"])
    by_addr: Dict[int, List[Proposal]] = collections.defaultdict(list)
    for p in proposals:
        by_addr[p.address].append(p)
    side_by_mangled = collections.defaultdict(list)
    for a, r in sidecar.items():
        if r.get("Mangled"):
            side_by_mangled[r["Mangled"]].append(a)

    decided: Dict[int, Decision] = {}
    survivors: Dict[int, List[Proposal]] = {}       # address -> the proposals that make its row
    held: List[Decision] = []                       # S12-R21: a hold is the (Address, Proposed) pair
    for a in sorted(by_addr):
        ps = by_addr[a]
        if a in holds:
            hp = [p for p in ps if p.mangled == holds[a].get("Proposed", "")]
            if hp:
                held.append(Decision(a, "held", holds[a].get("Reason", ""), hp))
                ps = [p for p in ps if p not in hp]
                if not ps:
                    continue
                by_addr[a] = ps
        mangled = _uniq(p.mangled for p in ps)
        if len(mangled) > 1 and len({alias_key(m) for m in mangled}) == 1:     # S12-R24: an alias
            plain = [m for m in mangled if not m.lower().startswith(PROJECT_PREFIX)]
            chosen = (plain or mangled)[0]
            ps = [p if p.mangled == chosen else p._replace(mangled=chosen, evidence="%s (spelled %s)"
                                                                  % (p.evidence, p.mangled)) for p in ps]
            by_addr[a] = ps
            mangled = [chosen]
        if a not in names:
            decided[a] = Decision(a, "refused", "not a csv start", ps)
        elif not npv.is_placeholder(names[a]):
            decided[a] = Decision(a, "refused", "csv already names it", ps)
        elif a in sidecar:
            if mangled == [sidecar[a].get("Mangled", "")]:
                decided[a] = Decision(a, "noop", "", ps)
            else:
                decided[a] = Decision(a, "refused", "sidecar disagrees", ps)
        elif len(mangled) > 1:
            decided[a] = Decision(a, "contradiction", "proposals disagree", ps)
        else:
            strict = [p for p in ps if not p.loose]
            if not strict:
                decided[a] = Decision(a, "deferred", "loose without a second lever", ps)
                continue
            fams = {p.family for p in strict}
            survivors[a] = [p for p in ps if not p.loose or p.family not in fams]

    # a name the sidecar already holds at another address
    for a in list(survivors):
        m = survivors[a][0].mangled
        elsewhere = [x for x in side_by_mangled.get(m, []) if x != a]
        if elsewhere:
            decided[a] = Decision(a, "refused", "one name, two addresses (the sidecar holds it at %s)"
                                  % ", ".join("0x%08x" % x for x in elsewhere), by_addr[a])
            del survivors[a]

    taken = [n for n in names.values() if not npv.is_placeholder(n)] + [r["Name"] for r in sidecar.values()]
    result = rn.render([survivors[a][0].mangled for a in sorted(survivors)], taken=taken, demo_counts=demo_counts)
    rows = []
    for a in sorted(survivors):
        ps = survivors[a]
        m = ps[0].mangled
        if m in result.refused:
            why = result.refused[m]
            if why.startswith("R10"):
                why = "one name, two addresses (%s)" % why
            decided[a] = Decision(a, "refused", why, by_addr[a])
            continue
        name = result.names[m]
        bad = rn.is_legal(name)
        if bad:
            decided[a] = Decision(a, "refused", "%s: %s" % (name, bad), by_addr[a])
            continue
        decided[a] = Decision(a, "applied", "", by_addr[a])
        rows.append({"Address": a, "Name": name, "Mangled": m,
                     "Pass": PASS_JOIN.join(_uniq(p.pass_name for p in ps)),
                     "Score": "%.2f" % max(p.score for p in ps),
                     "Evidence": " | ".join(_uniq("%s: %s" % (p.pass_name, p.evidence) for p in ps)),
                     "Source": " | ".join(_uniq(p.source for p in ps))})

    merged = dict(sidecar)
    for r in rows:
        merged[r["Address"]] = dict(r, Date="")
    findings = npv.audit(csv_rows, merged)
    decisions = sorted(list(decided.values()) + held, key=lambda d: (d.address, d.status != "held"))
    return Plan(decisions, rows, findings, sidecar, unapplied)


def apply(p: Plan, sidecar_path: str, date: str) -> None:
    """Write the kept sidecar (less the rows a hold un-applies) plus the plan's new rows, dated `date`."""
    rows = [dict(r) for r in p.sidecar.values()]
    rows += [dict(r, Date=date) for r in p.rows]
    npv.write(sidecar_path, rows)


def read_holds(path: str) -> Dict[int, dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return {int(r["Address"], 16): r for r in csv.DictReader(fh)}


def demo_name_counts(elf_path: str) -> Dict[str, int]:
    """How often the demo's `.symtab` holds each FUNC name (R10's multiplicity)."""
    from tools_py import elf_symbols
    elf = elf_symbols.read_elf(elf_path)
    return dict(collections.Counter(s.name for s in elf.symbols if s.kind == elf_symbols.STT_FUNC and s.name))


def _label(d: Decision) -> str:
    """The census bucket: the status, and for a refusal or a deferral the class of its reason."""
    if d.status in ("applied", "noop", "held", "contradiction"):
        return d.status
    return "%s: %s" % (d.status, _reason_class(d.reason))


def _reason_class(reason: str) -> str:
    """A census bucket for a free-text reason (the full text is on the address's printed line)."""
    if reason.startswith("one name, two addresses"):
        return "one name, two addresses"
    m = re.match(r"(R\d+)", reason)
    if m:
        return m.group(1)
    if ": " in reason:                                  # `<name>: <why>` from render or is_legal
        return re.split(r" with | \(|, ", reason.split(": ", 1)[1])[0]
    return reason


def census_lines(p: Plan, files: List[str]) -> List[str]:
    per_file = collections.OrderedDict((os.path.basename(f), collections.Counter()) for f in files)
    total = collections.Counter()
    for d in p.decisions:
        lab = _label(d)
        total[lab] += 1
        for f in _uniq(x.file for x in d.proposals):
            per_file.setdefault(f, collections.Counter())[lab] += sum(1 for x in d.proposals if x.file == f)

    def fmt(c):
        head = ["%s %d" % (s, c.get(s, 0)) for s in ("applied", "noop", "held", "contradiction")]
        rest = ["%s %d" % (k, v) for k, v in sorted(c.items()) if k not in ("applied", "noop", "held",
                                                                             "contradiction")]
        return ", ".join(head + rest)

    out = ["census per file (proposal rows, by their address's outcome):"]
    for f, c in per_file.items():
        out.append("  %-46s rows %4d: %s" % (f, sum(c.values()), fmt(c)))
    out.append("census total (addresses): %d: %s" % (sum(total.values()), fmt(total)))
    out.append("un-applied by a hold (S12-R24): %d" % len(p.unapplied))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ghidra_csv")
    ap.add_argument("names_csv")
    ap.add_argument("proposals", nargs="+")
    ap.add_argument("--holds", help="recomp/socom2_name_holds.csv (Address,Proposed,Reason,Source)")
    ap.add_argument("--demo", help="the demo ELF, for R10's .symtab name multiplicity")
    ap.add_argument("--report-only", action="store_true", help="print the plan and the census; write nothing")
    ap.add_argument("--strict", action="store_true", help="exit 1 when anything was refused")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args(argv)

    files, props = [], []
    for f in args.proposals:
        if not os.path.exists(f):
            print("SKIP %s: absent" % f)
            continue
        with open(f, encoding="utf-8") as fh:
            head = "".join(l for l in fh if l.startswith("#"))
        if "incomplete" in head.lower():
            print("SKIP %s: its header says it is incomplete" % f)
            continue
        got = read_proposals(f)
        print("read %s: %d rows (%d loose)" % (f, len(got), sum(1 for x in got if x.loose)))
        files.append(f)
        props.extend(got)
    holds = read_holds(args.holds) if args.holds else {}
    demo_counts = demo_name_counts(args.demo) if args.demo else {}
    csv_rows = npv.read_map(args.ghidra_csv)
    p = plan(csv_rows, npv.read(args.names_csv), holds, props, demo_counts)

    for u in p.unapplied:
        print("UN-APPLIED by hold 0x%08x: %s (%s)" % (u["Address"], u["Name"], u["Reason"]))
    for d in p.decisions:
        if d.status == "contradiction":
            print("CONTRADICTION 0x%08x: %s" % (d.address, "; ".join(
                _uniq("%s=%s%s" % (x.file, x.mangled, " (loose)" if x.loose else "") for x in d.proposals))))
        elif d.status == "held":
            print("HELD 0x%08x %s: %s" % (d.address, d.proposals[0].mangled, d.reason))
        elif d.status in ("refused", "deferred"):
            print("%s 0x%08x %s [%s]: %s" % (d.status.upper(), d.address, d.proposals[0].mangled,
                                             ",".join(_uniq(x.file for x in d.proposals)), d.reason))
    for line in census_lines(p, files):
        print(line)
    refused = sum(1 for d in p.decisions if d.status in ("refused", "contradiction"))
    if p.findings:
        for f in p.findings:
            print("AUDIT:", f)
        print("audit failed (%d findings): nothing written" % len(p.findings))
        return 2
    if args.report_only:
        print("report only: nothing written (%d rows would be added)" % len(p.rows))
    else:
        apply(p, args.names_csv, args.date)
        print("wrote %s: %d rows added, %d removed by a hold, %d rows in all"
              % (args.names_csv, len(p.rows), len(p.unapplied), len(p.sidecar) + len(p.rows)))
    return 1 if args.strict and refused else 0


if __name__ == "__main__":
    sys.exit(main())
