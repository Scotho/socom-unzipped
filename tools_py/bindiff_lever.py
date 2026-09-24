"""Sprint 12 Task 6: the `bindiff` lever -- BinDiff as the SECOND signal, never a proposer alone (S12-R22).

docs/research/49-bindiff-crosscheck.md measured it: BinDiff 8 over demo1 (primary) and r0001 (secondary)
contradicts 155 of Task 7's 828 proved pairs, 41 of them at similarity 1.00, so no similarity cut alone is
evidence. One rule reaches zero (§3.3): a STRUCTURAL matcher (one that compares a function's own flow graph
or bytes), both bodies >= 64 B, size ratio >= 0.50, similarity >= 0.95 -- 0 contradictions on 332
agreements, 0 other-name pairs on the toml's 205 hand names, 0 disagreements with 2,055 lever rows. This
module is that rule in code (`under_rule`, `BINDIFF_RULE`) and the three uses research/49 §7 recommends:

  `prefix_bindiff`  a Task 7 `prefix`/`prefix+size` pair that BinDiff pairs IDENTICALLY under the rule is
                    a strict row, How `prefix+bindiff`, Score 0.80 (S12-R3's second mechanical signal).
                    A prefix pair BinDiff pairs DIFFERENTLY under the rule is a contradiction: printed,
                    never written (research/49 §4 measured 0).
  `bindiff_new`     a pair under the rule with neither side one of the 987 and our row still a
                    placeholder goes to the `_loose` file at 0.75, How `bindiff`, only where no other lever
                    proposes that address: those are research/49 §5's 61 BinDiff-only pairs, applied only
                    when a second lever agrees. `write_proposals` refuses a `bindiff` row at a strict path.
  `confirmations`   every other proposals file's rows that BinDiff agrees with under the rule (and those
                    it contradicts): S12-R18's confirming key. The applier reads the agreements from
                    game/bindiff/confirmations.csv (Address, Mangled, File, Matcher, Similarity).

The BinDiff result is the SQLite file `bindiff demo1.BinExport r0001.BinExport` writes (research/49 §1,
commands A-E, about 8 minutes). The reading and the rule are copied from
tools_py/research/symbols/bindiff_join.py, so this lever does not depend on a research script.

    python -m tools_py.bindiff_lever game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf \\
        recomp/socom2_ghidra.csv game/demo_symbol_matches.json game/bindiff/demo1_vs_r0001.BinDiff \\
        --out game/demo_symbol_renames_bindiff.csv [--holds recomp/socom2_name_holds.csv] \\
        [--confirmations game/bindiff/confirmations.csv]

It never touches recomp/socom2_ghidra.csv or recomp/socom2_names.csv: applying is tools_py/apply_names.py's
step (S12-R13). Names, addresses, counts and similarity scores only; no byte of either image.
"""
import argparse
import collections
import csv
import glob
import json
import os
import sqlite3
import sys
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from tools_py import ghidra_symbol_match as gsm
from tools_py import symbol_levers as sl
from tools_py.ghidra_symbol_match import c_identifier
from tools_py.name_provenance import is_placeholder
from tools_py.symbol_levers import MIN_BODY, SIZE_RATIO, is_loose_path, loose_path

BINDIFF_MIN_SIMILARITY = 0.95   # research/49 §3.3: the first 0.05 step above the one contradiction (0.9213)
SCORE_STRICT = 0.80
SCORE_LOOSE = 0.75
HOW_STRICT = "prefix+bindiff"
HOW_LOOSE = "bindiff"
NOTE = "docs/research/49-bindiff-crosscheck.md"
DEFAULT_CONFIRMATIONS = "game/bindiff/confirmations.csv"

# BinDiff's matchers that compare a function's OWN flow graph (or its bytes). The others -- address
# sequence, call sequence, call reference, call-graph MD index, instruction count, string references,
# loop count -- place a function by its neighbours or by one scalar: position, not evidence about the body
# (research/49 §3.3). The names are BinDiff 8's `functionalgorithm.name` spellings.
RULE_MATCHERS = frozenset((
    "function: hash matching",
    "function: edges flowgraph MD index",
    "function: MD index matching (flowgraph MD index, top down)",
    "function: MD index matching (flowgraph MD index, bottom up)",
    "function: prime signature matching",
    "function: relaxed MD index matching",
))

BINDIFF_RULE = (
    "THE RULE (research/49 sec 3.3, S12-R22): a BinDiff pair counts only when its matcher is structural "
    "(hash, edges flowgraph MD index, flowgraph MD index top-down or bottom-up, prime signature, relaxed MD "
    "index -- never address sequence, call sequence, call reference, call-graph MD index or instruction "
    "count, which place a function by its neighbours or one scalar), both bodies >= %d bytes, size ratio "
    ">= %.2f, and similarity >= %.2f. On similarity alone BinDiff contradicts 41 of Task 7's 828 proved "
    "pairs even at 1.00; under the rule it contradicts 0 of them (332 agreements), names no other function "
    "on the toml's 205 hand-named addresses, and disagrees with none of 2,055 lever rows. prefix+bindiff "
    "(strict, Score %.2f): a Task 7 prefix/prefix+size pair (the 16-instruction prologue unique both sides) "
    "that BinDiff pairs identically under the rule. bindiff (the _loose file, Score %.2f): a pair under the "
    "rule with neither side one of Task 7's anchors, our row still a placeholder and no other lever "
    "proposing the address -- BinDiff never proposes alone, so these wait for a second lever (S12-R18). "
    "The anchors exclude every address in recomp/socom2_name_holds.csv, and a held (address, name) is "
    "refused; Task 7's identifier hurdles apply."
) % (MIN_BODY, SIZE_RATIO, BINDIFF_MIN_SIMILARITY, SCORE_STRICT, SCORE_LOOSE)

BINDIFF_CAVEAT = (
    "The limit, stated (research/49 sec 3.3): all 332 zero-error agreements sit at similarity 1.00, because "
    "the proved pairs are byte- or relink-identical bodies; the band 0.95 <= similarity < 1.00 has only the "
    "toml's few same-name pairs as independent evidence, which is why a BinDiff-only pair is loose. Every "
    "row carries its matcher and similarity in Evidence."
)

REPRODUCE = (
    "Reproduce: %s sec 1, commands A-E (the demo's function table; Ghidra 11.0.3 + the EE extension import "
    "and analysis; BinExport 12 with ghidra_scripts/binexport-r5900-blocks.patch; BinDiff 8 with name "
    "hashing removed; the join), about 8 minutes of wall time; then this command."
) % NOTE

COLUMNS = ["Address", "Current", "Proposed", "Mangled", "Score", "How", "Evidence", "Matcher", "Similarity",
           "Confidence", "DemoAddr", "DemoSize", "OurSize", "Ratio"]
CONFIRMATION_COLUMNS = ["Address", "Mangled", "File", "Matcher", "Similarity"]


class Match(NamedTuple):
    """One BinDiff function pair: address_a in the PRIMARY (the demo), address_b in the SECONDARY (ours)."""
    address_a: int
    address_b: int
    similarity: float
    confidence: float
    algorithm: str


class Sizes(NamedTuple):
    """Body lengths in bytes: {demo address: size}, {our address: size} (the function tables' rows)."""
    demo: Dict[int, int]
    ours: Dict[int, int]


class Candidate(NamedTuple):
    our_addr: int
    demo_addr: int
    demo_name: str
    our_name: str
    how: str
    score: float
    evidence: str
    match: Match
    demo_size: int
    our_size: int

    @property
    def ratio(self) -> float:
        return _ratio(self.demo_size, self.our_size)


class Contradiction(NamedTuple):
    demo_addr: int
    our_addr: int
    demo_name: str
    task7_how: str
    match: Match         # BinDiff's pair under the rule that places one side elsewhere


class Confirmations(NamedTuple):
    agree: List[Dict[str, str]]          # CONFIRMATION_COLUMNS rows, by (address, file)
    contradict: List[Dict[str, str]]     # the same shape, plus BinDiff's own pair
    per_file: Dict[str, collections.Counter]


# ---- the BinDiff result ----------------------------------------------------------------------------------

def read_bindiff(path: str) -> List[Match]:
    """Every function pair of a BinDiff 8 result (SQLite: `function` joined to `functionalgorithm`)."""
    db = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        algo = dict(db.execute("SELECT id, name FROM functionalgorithm"))
        rows = db.execute("SELECT address1, address2, similarity, confidence, algorithm FROM function").fetchall()
    finally:
        db.close()
    return [Match(int(a1), int(a2), float(s), float(c), algo.get(al, str(al))) for a1, a2, s, c, al in rows]


def matcher_label(algorithm: str) -> str:
    """BinDiff's matcher name without its `function: ` prefix, as Evidence spells it."""
    return algorithm[len("function: "):] if algorithm.startswith("function: ") else algorithm


def _ratio(a: int, b: int) -> float:
    return min(a, b) / max(a, b) if max(a, b) else 0.0


def under_rule(match: Match, sizes: Sizes) -> bool:
    """research/49's rule: a structural matcher, both bodies >= MIN_BODY, ratio >= SIZE_RATIO, sim >= 0.95."""
    ds, os_ = sizes.demo.get(match.address_a, 0), sizes.ours.get(match.address_b, 0)
    return (match.algorithm in RULE_MATCHERS and min(ds, os_) >= MIN_BODY
            and _ratio(ds, os_) >= SIZE_RATIO and match.similarity >= BINDIFF_MIN_SIMILARITY)


def rule_index(matches: Iterable[Match], sizes: Sizes) -> Tuple[Dict[int, Match], Dict[int, Match]]:
    """({demo address: match}, {our address: match}) over the matches under the rule."""
    by_a, by_b = {}, {}
    for m in matches:
        if under_rule(m, sizes):
            by_a[m.address_a] = m
            by_b[m.address_b] = m
    return by_a, by_b


def _fmt_sim(x: float) -> str:
    return "%.3f" % x


# ---- the two passes --------------------------------------------------------------------------------------

def prefix_bindiff(details: Dict, matches: Sequence[Match], sizes: Sizes, our_names: Dict[int, str]):
    """(candidates, contradictions, census) over Task 7's prologue-only pairs.

    `details` is `ghidra_symbol_match.match`'s out-parameter ({(demo name, our addr): {how, demo_addr, ..}}).
    A prefix pair is CONFIRMED when BinDiff's pair of its demo function under the rule is exactly our row,
    CONTRADICTED when a pair under the rule places either side elsewhere, UNCONFIRMED otherwise.
    """
    by_a, by_b = rule_index(matches, sizes)
    census = collections.Counter()
    out, contra = [], []
    for (name, o), info in sorted(details.items(), key=lambda kv: kv[0][1]):
        how, d = info["how"], info["demo_addr"]
        if not how.startswith("prefix"):
            continue
        census["prologue pairs"] += 1
        a, b = by_a.get(d), by_b.get(o)
        if a is not None and a.address_b == o:
            our_name = our_names.get(o, "")
            if not is_placeholder(our_name):
                census["refused: our row not a placeholder"] += 1
                continue
            census["confirmed"] += 1
            census["confirmed %s" % how] += 1
            ds, os_ = sizes.demo.get(d, 0), sizes.ours.get(o, 0)
            evidence = ("prologue unique both sides + BinDiff %s %s, %d/%d B"
                        % (matcher_label(a.algorithm), _fmt_sim(a.similarity), ds, os_))
            out.append(Candidate(o, d, name, our_name, HOW_STRICT, SCORE_STRICT, evidence, a, ds, os_))
        elif a is not None or b is not None:
            census["contradicted"] += 1
            against = [m for m in (a, b) if m is not None]
            contra.append(Contradiction(d, o, name, how, max(against, key=lambda m: m.similarity)))
        else:
            census["unconfirmed"] += 1
    return out, contra, census


def bindiff_new(matches: Sequence[Match], anchors, sizes: Sizes, demo_names: Dict[int, str],
                our_names: Dict[int, str]):
    """(candidates, census): pairs under the rule with neither side an anchor and our row a placeholder.

    `anchors` is [(demo address, our address[, how])] -- Task 7's pairs with the held ones already removed
    (`drop_held`). Every candidate is How `bindiff` at Score 0.75: the loose file, never the strict one.
    """
    placed_d = {int(r[0]) for r in anchors}
    placed_o = {int(r[1]) for r in anchors}
    census = collections.Counter()
    out = []
    for m in sorted(matches, key=lambda m: m.address_b):
        if not under_rule(m, sizes):
            continue
        census["pairs under the rule"] += 1
        if m.address_a in placed_d or m.address_b in placed_o:
            census["a side is one of the anchors"] += 1
            continue
        name = demo_names.get(m.address_a)
        if not name:
            census["refused: demo side is not a row of the demo's table"] += 1
            continue
        our_name = our_names.get(m.address_b, "")
        if not is_placeholder(our_name):
            census["refused: our row not a placeholder"] += 1
            continue
        census["new"] += 1
        ds, os_ = sizes.demo.get(m.address_a, 0), sizes.ours.get(m.address_b, 0)
        evidence = "BinDiff %s %s, %d/%d B; no other key" % (matcher_label(m.algorithm), _fmt_sim(m.similarity),
                                                             ds, os_)
        out.append(Candidate(m.address_b, m.address_a, name, our_name, HOW_LOOSE, SCORE_LOOSE, evidence, m,
                             ds, os_))
    return out, census


# ---- holds, other files, the hurdles ---------------------------------------------------------------------

def read_holds(path: str) -> Dict[int, Dict[str, str]]:
    """{our address: row} from recomp/socom2_name_holds.csv (`Address, Proposed, Reason, Source`)."""
    with open(path, newline="") as fh:
        return {int(r["Address"], 16): r for r in csv.DictReader(fh)}


def drop_held(anchors, holds) -> List[Tuple[int, int, str]]:
    """The anchors whose our address is not held (S12-R20: a held address is no anchor for any lever)."""
    return [(int(r[0]), int(r[1]), str(r[2]) if len(r) > 2 else "") for r in anchors if int(r[1]) not in holds]


def _is_held(holds, addr: int, name: str) -> bool:
    row = (holds or {}).get(addr)
    return row is not None and row.get("Proposed", "") in (name, c_identifier(name))


def read_rows(path: str) -> List[Dict[str, str]]:
    """A proposals file's data rows (its `#` header skipped)."""
    with open(path, newline="") as fh:
        return list(csv.DictReader(line for line in fh if not line.startswith("#")))


def other_files(out_path: str) -> Dict[str, List[Dict[str, str]]]:
    """Every other demo_symbol_renames*.csv beside `out_path` (this lever's two files excluded), strict and loose."""
    mine = {os.path.abspath(out_path), os.path.abspath(loose_path(out_path))}
    pattern = os.path.join(os.path.dirname(os.path.abspath(out_path)), "demo_symbol_renames*.csv")
    return {p: read_rows(p) for p in sorted(glob.glob(pattern)) if os.path.abspath(p) not in mine}


def proposed_pairs(files: Dict[str, List[Dict[str, str]]]) -> Dict[str, List[Tuple[int, str]]]:
    """{path: [(our address, Proposed identifier)]} -- the shape `proposals` takes as `others`."""
    return {p: [(int(r["Address"], 16), r["Proposed"]) for r in rows if r.get("Address") and r.get("Proposed")]
            for p, rows in files.items()}


def proposals(cands: Sequence[Candidate], others: Optional[Dict[str, List[Tuple[int, str]]]] = None,
              taken: Optional[Dict[str, set]] = None, holds: Optional[Dict[int, Dict]] = None,
              demo_counts: Optional[Dict[str, int]] = None):
    """(rows, census) -- Task 7's identifier hurdles, the holds, and the other levers' files.

    Refused, each counted: a held (address, name); a demo name the demo's .symtab holds at two addresses
    (a C `static` in two translation units); two candidates sanitising to one identifier; an identifier
    `taken` holds at another address (the anchors' names, our csv's own non-placeholder names); an
    identifier another file proposes at another address. The same identifier at the same address in
    another file is an agreement: a strict row is kept and counted (the applier joins agreeing passes); a
    `bindiff` row is NOT written -- BinDiff is then that row's confirming key (`confirmations`), and the
    loose file holds the BinDiff-only pairs. Another name at the same address: a strict row is kept and
    counted (the applier refuses both and prints them); a `bindiff` row is refused.
    """
    others = others or {}
    taken = taken or {}
    demo_counts = demo_counts or {}
    census = collections.Counter()
    spelling = collections.Counter(c_identifier(c.demo_name) for c in cands)
    ident_at = collections.defaultdict(set)
    addr_has = collections.defaultdict(set)
    for _path, pairs in others.items():
        for a, ident in pairs:
            if _is_held(holds, a, ident):
                continue
            ident_at[ident].add(a)
            addr_has[a].add(ident)
    rows = []
    for c in sorted(cands, key=lambda c: (c.our_addr, c.how)):
        ident = c_identifier(c.demo_name)
        loose = c.how == HOW_LOOSE
        if _is_held(holds, c.our_addr, c.demo_name):
            census["refused: held (address, name) (recomp/socom2_name_holds.csv)"] += 1
            continue
        if demo_counts.get(c.demo_name, 1) > 1:
            census["refused: demo name on two demo addresses"] += 1
            continue
        if spelling[ident] > 1:
            census["refused: identifier collides inside this lever"] += 1
            continue
        if set(taken.get(ident, ())) - {c.our_addr}:
            census["refused: identifier carried by a Task 7 pair or a named row elsewhere"] += 1
            continue
        if ident_at.get(ident, set()) - {c.our_addr}:
            census["refused: identifier proposed at another address by another file"] += 1
            continue
        differ = addr_has.get(c.our_addr, set()) - {ident}
        same = c.our_addr in ident_at.get(ident, set())
        if loose:
            if differ:
                census["refused: another file proposes a different name for this address"] += 1
                continue
            if same:
                census["already proposed by another file with the same name (a confirmation)"] += 1
                continue
        else:
            if same:
                census["agrees with another file (kept)"] += 1
            if differ:
                census["another file proposes a different name here (kept; the applier refuses both)"] += 1
        census["written %s" % c.how] += 1
        m = c.match
        rows.append({"Address": "0x%08x" % c.our_addr, "Current": c.our_name, "Proposed": ident,
                     "Mangled": c.demo_name, "Score": "%.2f" % c.score, "How": c.how, "Evidence": c.evidence,
                     "Matcher": matcher_label(m.algorithm), "Similarity": "%.4f" % m.similarity,
                     "Confidence": "%.4f" % m.confidence, "DemoAddr": "0x%08x" % c.demo_addr,
                     "DemoSize": c.demo_size, "OurSize": c.our_size, "Ratio": "%.2f" % c.ratio})
    return rows, census


# ---- BinDiff as the confirming key (S12-R18) -------------------------------------------------------------

def confirmations(matches: Sequence[Match], files: Dict[str, List[Dict[str, str]]], sizes: Sizes,
                  demo_names: Dict[int, str], holds: Optional[Dict[int, Dict]] = None) -> Confirmations:
    """Each file's rows against BinDiff under the rule.

    A row AGREES when BinDiff's pair under the rule at its address of ours is its demo function (by
    `DemoAddr` when the file has one, else by the demo name in `Mangled`). It is CONTRADICTED when that
    pair names another demo function, or when BinDiff's pair under the rule of its demo function (by
    `DemoAddr`, or a `Mangled` name unique in the demo) is another address of ours. Otherwise it has no
    rule pair. A row with neither `DemoAddr` nor `Mangled` (a derived name) has no demo key. A row whose
    (address, name) is held is counted as held and is never an agreement: on the real inputs BinDiff pairs
    two of the four held pairs identically at 1.00, because a relink-identical body has an identical flow
    graph -- there it is no witness independent of the fingerprint.
    """
    by_a, by_b = rule_index(matches, sizes)
    name_addrs = collections.defaultdict(list)
    for a, n in demo_names.items():
        name_addrs[n].append(a)
    agree, contra = [], []
    per_file: Dict[str, collections.Counter] = {}
    for path, rows in sorted(files.items()):
        base = os.path.basename(path)
        c = per_file.setdefault(base, collections.Counter())
        for r in rows:
            c["rows"] += 1
            o = int(r["Address"], 16)
            mangled = (r.get("Mangled") or "").strip()
            da = (r.get("DemoAddr") or "").strip()
            if not da and not mangled:
                c["no demo key"] += 1
                continue
            if _is_held(holds, o, mangled) or _is_held(holds, o, r.get("Proposed") or ""):
                c["held (address, name)"] += 1
                continue
            d = int(da, 16) if da else (name_addrs[mangled][0] if len(name_addrs.get(mangled, ())) == 1 else None)
            p = by_b.get(o)
            q = by_a.get(d) if d is not None else None
            row = {"Address": "0x%08x" % o, "Mangled": mangled, "File": base}
            if p is not None and ((da and p.address_a == d) or (not da and demo_names.get(p.address_a) == mangled)):
                c["same"] += 1
                row.update(Matcher=matcher_label(p.algorithm), Similarity=_fmt_sim(p.similarity))
                agree.append(row)
            elif p is not None or (q is not None and q.address_b != o):
                c["other"] += 1
                m = p if p is not None else q
                row.update(Matcher=matcher_label(m.algorithm), Similarity=_fmt_sim(m.similarity),
                           BinDiff="%s 0x%08x -> 0x%08x" % (demo_names.get(m.address_a, "?"), m.address_a,
                                                            m.address_b))
                contra.append(row)
            else:
                c["no rule pair"] += 1
    key = lambda r: (int(r["Address"], 16), r["File"])  # noqa: E731
    return Confirmations(sorted(agree, key=key), sorted(contra, key=key), per_file)


def write_confirmations(path: str, rows: Sequence[Dict[str, str]]) -> None:
    """game/bindiff/confirmations.csv: a plain CSV (no `#` lines), CONFIRMATION_COLUMNS, one agreement a row."""
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CONFIRMATION_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---- the files -------------------------------------------------------------------------------------------

def header_lines(path: str, census_lines: Sequence[str], anchor_note: str) -> List[str]:
    """The `#` lines above the columns (research/45 sec 8's convention): what the file is, the rule, the
    matchers, the threshold, the caveat, the counts, the anchors, the reproduction pointer."""
    loose = is_loose_path(path)
    first = ("%s -- Sprint 12 Task 6 `bindiff` proposals, %s. PROPOSALS ONLY:"
             % (os.path.basename(path),
                "BinDiff-only pairs at Score %.2f (LOOSE: applied only when a second lever agrees, S12-R22)"
                % SCORE_LOOSE if loose else
                "prefix+bindiff at Score %.2f (a prologue pair BinDiff confirms)" % SCORE_STRICT))
    lines = [first,
             "recomp/socom2_ghidra.csv and recomp/socom2_names.csv are unchanged; applying these is "
             "tools_py/apply_names.py's step, which also joins the levers' files (S12-R13, S12-R18).",
             "Names come from the SOCOM 1 demo's .symtab. Addresses are OURS (r0001). %s" % NOTE,
             "",
             BINDIFF_RULE,
             "",
             "Matchers under the rule (BinDiff 8 names): %s" % "; ".join(sorted(RULE_MATCHERS)),
             "Threshold: similarity >= %.2f (BINDIFF_MIN_SIMILARITY); both bodies >= %d B; size ratio >= %.2f"
             % (BINDIFF_MIN_SIMILARITY, MIN_BODY, SIZE_RATIO),
             "",
             BINDIFF_CAVEAT,
             ""]
    lines += list(census_lines)
    if anchor_note:
        lines.append(anchor_note)
    lines.append(REPRODUCE)
    return lines + [""]


def write_proposals(path: str, rows: Sequence[Dict], header: Sequence[str]) -> None:
    """The file, its rule in `#` lines above the columns. A `bindiff` row belongs at the `_loose` path and a
    `prefix+bindiff` row at the strict one; anything else is a ValueError, whoever calls this."""
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise ValueError("cannot write %s: %s is not a directory" % (path, directory))
    loose = is_loose_path(path)
    wrong = [r for r in rows if (r.get("How") == HOW_LOOSE) != loose]
    if wrong:
        raise ValueError("cannot write %s: %d `%s` row(s) belong at the %s path"
                         % (path, len(wrong), wrong[0].get("How"),
                            "strict" if loose else "loose (%s)" % loose_path(path)))
    with open(path, "w", newline="") as fh:
        for line in header:
            fh.write("# %s\n" % line if line else "#\n")
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row)


# ---- the CLI ---------------------------------------------------------------------------------------------

def _census_text(census) -> str:
    return ", ".join("%s %d" % kv for kv in sorted(census.items())) or "none"


def _under_game(path: str) -> bool:
    return os.path.abspath(path).startswith(os.path.abspath("game") + os.sep)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="the bindiff lever (Sprint 12 Task 6, research/49, S12-R22)")
    ap.add_argument("demo_elf")
    ap.add_argument("our_elf")
    ap.add_argument("our_csv")
    ap.add_argument("matches", help="game/demo_symbol_matches.json: Task 7's pairs, checked against the re-derivation")
    ap.add_argument("bindiff", help="the .BinDiff SQLite result (demo primary, r0001 secondary)")
    ap.add_argument("--out", default="game/demo_symbol_renames_bindiff.csv",
                    help="the strict file (under game/); the loose one is written beside it")
    ap.add_argument("--holds", default="recomp/socom2_name_holds.csv")
    ap.add_argument("--confirmations", default=DEFAULT_CONFIRMATIONS,
                    help="where BinDiff's agreements with the other files go (under game/)")
    args = ap.parse_args(argv)
    for p in (args.demo_elf, args.our_elf, args.our_csv, args.matches, args.bindiff, args.holds):
        if not os.path.exists(p):
            print("NO-DATA: missing %s" % p)
            return 2
    if is_loose_path(args.out):
        print("NO-DATA: --out names the strict file; the loose one is written beside it")
        return 2
    for p in (args.out, args.confirmations):
        if not _under_game(p):
            print("NO-DATA: %s must be under game/ (git-ignored)" % p)
            return 2

    demo_rows, demo_segs = gsm.load_demo(args.demo_elf)
    our_rows, our_segs = gsm.load_ours(args.our_elf, args.our_csv)
    details: Dict = {}
    gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
    with open(args.matches) as fh:
        on_disk = {(p["name"], int(p["addr"], 16)) for p in json.load(fh)["pairs"]}
    if on_disk != set(details):
        print("NO-DATA: the re-derived Task 7 pairs (%d) differ from %s (%d)" % (len(details), args.matches,
                                                                                len(on_disk)))
        return 2
    anchors3 = sl.anchors_from_details(details)
    holds = read_holds(args.holds)
    kept = drop_held(anchors3, holds)
    comp = ", ".join("%s %d" % kv for kv in sorted(sl.anchor_composition(kept).items()))
    anchor_note = ("Anchors: %d Task 7 pairs re-derived with --prefix (identical to %s); %d held excluded "
                   "(%s: %s); %d used (%s); %d PROVED, the rest prologue-only"
                   % (len(anchors3), args.matches, len(anchors3) - len(kept), args.holds,
                      ", ".join("0x%08x" % r[1] for r in anchors3 if r[1] in holds), len(kept), comp,
                      len(sl.proved_anchors(kept))))
    print(anchor_note)

    matches = read_bindiff(args.bindiff)
    sizes = Sizes({s: e - s for s, e, _n in demo_rows}, {s: e - s for s, e, _n in our_rows})
    demo_names = {s: n for s, _e, n in demo_rows}
    our_names = {s: n for s, _e, n in our_rows}
    demo_counts = collections.Counter(n for _s, _e, n in demo_rows)
    by_alg = collections.Counter(matcher_label(m.algorithm) for m in matches if under_rule(m, sizes))
    print("BinDiff: %d pairs; under the rule %d (%s)" % (len(matches), sum(by_alg.values()), _census_text(by_alg)))

    kept_details = {k: v for k, v in details.items() if k[1] not in holds}
    strict_c, contra, pcensus = prefix_bindiff(kept_details, matches, sizes, our_names)
    print("prefix+bindiff: %s" % _census_text(pcensus))
    for x in contra:
        m = x.match
        print("  CONTRADICTION: %s demo 0x%08x -> ours 0x%08x (%s); BinDiff under the rule 0x%08x -> 0x%08x %s %s"
              % (x.demo_name, x.demo_addr, x.our_addr, x.task7_how, m.address_a, m.address_b,
                 matcher_label(m.algorithm), _fmt_sim(m.similarity)))
    new_c, ncensus = bindiff_new(matches, kept, sizes, demo_names, our_names)
    print("bindiff (new): %s" % _census_text(ncensus))

    files = other_files(args.out)
    others = proposed_pairs(files)
    taken = collections.defaultdict(set)
    for d, o, _h in kept:
        taken[c_identifier(demo_names[d])].add(o)
    for s, n in our_names.items():
        if not is_placeholder(n):
            taken[c_identifier(n)].add(s)
    strict_rows, scensus = proposals(strict_c, others, taken, holds, demo_counts)
    loose_rows, lcensus = proposals(new_c, others, taken, holds, demo_counts)
    print("strict hurdles: %s" % _census_text(scensus))
    print("loose hurdles: %s" % _census_text(lcensus))
    for r in strict_rows:
        elsewhere = sorted(os.path.basename(p) for p, pairs in others.items()
                           if (int(r["Address"], 16), r["Proposed"]) in pairs)
        print("  strict 0x%s %-44s %s%s" % (r["Address"][2:], r["Mangled"][:44], r["Evidence"],
                                            "  [also in %s]" % ", ".join(elsewhere) if elsewhere else ""))

    conf = confirmations(matches, files, sizes, demo_names, holds)
    placed_o = {o for _d, o, _h in kept}
    placed_d = {d for d, _o, _h in kept}
    new_rule = [m for m in matches if under_rule(m, sizes) and m.address_a not in placed_d
                and m.address_b not in placed_o and is_placeholder(our_names.get(m.address_b, ""))
                and not _is_held(holds, m.address_b, demo_names.get(m.address_a, ""))]
    proposed_by = collections.defaultdict(set)
    for path, pairs in others.items():
        for a, ident in pairs:
            proposed_by[(a, ident)].add(os.path.basename(path))
    new_agree = [m for m in new_rule if (m.address_b, c_identifier(demo_names.get(m.address_a, ""))) in proposed_by]
    conf_lines = ["confirmations (BinDiff under the rule against every other proposals file): agreements %d, "
                  "contradictions %d; of the rule's %d new pairs (held ones excluded), %d are another file's "
                  "proposal with the same name" % (len(conf.agree), len(conf.contradict), len(new_rule), len(new_agree))]
    for base, c in sorted(conf.per_file.items()):
        conf_lines.append("  %s: rows %d; same %d, other %d, no rule pair %d, no demo key %d, held %d"
                          % (base, c["rows"], c["same"], c["other"], c["no rule pair"], c["no demo key"],
                             c["held (address, name)"]))
    for r in conf.contradict:
        conf_lines.append("  CONTRADICTS %s %s (%s): BinDiff %s %s %s"
                          % (r["Address"], r["Mangled"], r["File"], r["BinDiff"], r["Matcher"], r["Similarity"]))
    for ln in conf_lines:
        print(ln)

    census_lines = ["prefix+bindiff census: %s" % _census_text(pcensus),
                    "prefix+bindiff hurdles: %s" % _census_text(scensus),
                    "bindiff (new) census: %s" % _census_text(ncensus),
                    "bindiff (new) hurdles: %s" % _census_text(lcensus),
                    "BinDiff: %d pairs, %d under the rule (%s)" % (len(matches), sum(by_alg.values()),
                                                                  _census_text(by_alg)),
                    "written: strict %d, loose %d" % (len(strict_rows), len(loose_rows))] + conf_lines
    try:
        for path, rows in ((args.out, strict_rows), (loose_path(args.out), loose_rows)):
            write_proposals(path, rows, header_lines(path, census_lines, anchor_note))
            print("wrote %s: %d rows" % (path, len(rows)))
        write_confirmations(args.confirmations, conf.agree)
        print("wrote %s: %d agreements" % (args.confirmations, len(conf.agree)))
    except (ValueError, OSError) as exc:
        print("NO-DATA: %s" % exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
