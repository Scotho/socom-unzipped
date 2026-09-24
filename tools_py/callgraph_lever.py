"""Sprint 12 Task 15: the `callgraph` lever -- callers and callees of placed pairs name the bodies between.

docs/research/52-callgraph-propagation.md measured it; this module is the pass it recommends (§7, §9),
with its own CLI and its own two proposals files, like the other levers. It never touches
`recomp/socom2_ghidra.csv`: applying is Task 3's reviewed step, to the sidecar only (S12-R13).

THE GRAPHS (`graphs`). A call edge is a `jal` whose target is the start of a live table row (a row with
bytes). A `jal` into a body, or to an address no row covers, is dropped and counted. A `jalr` goes
through a register and is INVISIBLE: a third of each image has no static caller (virtual methods,
callbacks, table entries), so its caller key is empty by construction.

THE KEYS (`keys`). For every live function, with the anchors as the placed set, all in DEMO addresses:
K_callee (its placed callees), K_caller (its placed callers) and K_pair = (K_caller, K_callee). A key is
UNIQUE BOTH WAYS when it is non-empty and exactly one demo function and exactly one of our functions in
the WHOLE image wear it, both unplaced (research/45 §4's image-wide bar: an unplaced function sharing its
key with an anchor is refused).

THE RULE (`callgraph_pass`, `CALLGRAPH_RULE`): research/52's ORDERED rule. The union of three keys --
callee (|K| >= 1), caller (|K| >= 2), pair (|K_caller| + |K_callee| >= 3) -- each with both bodies
>= 64 B and a size ratio >= 0.50; a function claimed two ways is dropped; our row still a placeholder;
link order against the flanking anchors (in demo order, same PT_LOAD of ours, over that round's
anchors) not `outside`. Iterated: each round's pairs join the anchors, until a round adds nothing. The
|K| cuts and the order check are load-bearing (research/52 §4, §6.3, §7): without them the holdout
shows wrong pairs, or four real common-library false pairs pass that the holdout cannot see.

TWO FILES. Round 1 (evidence directly on the anchors) goes to the strict file at 0.80; rounds 2 and
later (evidence inherited from call-graph pairs, where research/52 §6.3's errors compounded) go to the
`_loose` file at 0.75, promoted only when another lever proposes the same (address, name) -- the
applier's cross-lever rule (S12-R18). `write_proposals` refuses a row at the wrong one.

    python -m tools_py.callgraph_lever game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf \\
        recomp/socom2_ghidra.csv game/demo_symbol_matches.json \\
        --out game/demo_symbol_renames_callgraph.csv [--holdout] [--holds recomp/socom2_name_holds.csv]

Names, addresses and counts only; no byte of either image is printed or written.
"""
import argparse
import bisect
import collections
import csv
import glob
import json
import os
import sys
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from tools_py import address_matcher as am
from tools_py import ghidra_symbol_match as gsm
from tools_py import symbol_levers as sl
from tools_py.ghidra_symbol_match import c_identifier
from tools_py.name_provenance import is_placeholder
from tools_py.symbol_levers import MIN_BODY, SIZE_RATIO, is_loose_path, loose_path

KINDS = ("callee", "caller", "pair")
MIN_K = {"callee": 1, "caller": 2, "pair": 3}      # research/52 §4: the cuts at 0 wrong in both holdouts
SCORE_ROUND_1 = 0.80
SCORE_LATER = 0.75
HOW = "callgraph"
JALR_FUNCT = 0x09
MAX_ROUNDS = 50

CALLGRAPH_RULE = (
    "callgraph (research/52's ORDERED rule): over the static jal graph (a jal to no row start is dropped; "
    "jalr is invisible), with the anchors as the placed set, an unplaced demo function and an unplaced "
    "row of ours are paired when one of three keys, written in demo addresses, is non-empty and worn by "
    "exactly one demo function and exactly one of our functions in the WHOLE image: the placed-callee "
    "set (|K| >= 1), the placed-caller set (|K| >= 2), or the (caller set, callee set) pair "
    "(|K| >= 3). Both bodies >= %d bytes, size ratio >= %.2f; a function claimed two ways is dropped; "
    "our row still a placeholder; link order against the flanking anchors (demo order, the same "
    "PT_LOAD of ours, that round's anchors) not `outside`. Iterated to a fixed point, each round's "
    "pairs anchoring the next. Round 1 is the strict file at %.2f; rounds 2+ are the _loose file at "
    "%.2f, promoted only when another lever proposes the same (address, name) (S12-R18). The anchors "
    "exclude every address in recomp/socom2_name_holds.csv. Task 7's identifier hurdles apply."
) % (MIN_BODY, SIZE_RATIO, SCORE_ROUND_1, SCORE_LATER)

CALLGRAPH_CAVEAT = (
    "The holdout (research/45 sec 3's shape: the PROVED Task 7 pairs held out in 3 folds, blocks of 8 "
    "and of 1, a pair counted when either side is held out) cannot see this pass's real failure. A "
    "held-out pair is an UNEDITED body whose call set is intact on both sides; the candidates here are "
    "the routines SOCOM II edited, where one added or removed call breaks the true partner's key and "
    "another routine may wear the old set uniquely -- research/52 sec 6.3's four common-library false "
    "pairs, all link order `outside`, which the order check removes. 0 wrong in the holdout is an upper "
    "bound on accuracy, not a proof; research/52 sec 7 bounds the checked subset at about 4.5 % (95 %)."
)

COLUMNS = ["Address", "Current", "Proposed", "Mangled", "Score", "How", "Evidence", "Round", "Key",
           "KeySize", "Order", "DemoAddr", "DemoSize", "OurSize", "Ratio"]


# ---- the graphs ------------------------------------------------------------------------------

class Graph:
    """One Side's static call graph over `jal` targets that are live row starts."""

    def __init__(self, side: am.Side):
        self.side = side
        self.live = sorted(s for s in side.starts if side.fp[s] is not None)
        self.callees: Dict[int, set] = {s: set() for s in self.live}
        self.callers: Dict[int, set] = {s: set() for s in self.live}
        self.stats = collections.Counter()
        ordered = sorted(side.starts)
        for s in self.live:
            body = side.body[s]
            for i in range(0, len(body) - 3, 4):
                w = int.from_bytes(body[i:i + 4], "little")
                if (w >> 26) == 0 and (w & 0x3F) == JALR_FUNCT:
                    self.stats["jalr (invisible)"] += 1
            for t in side.calls[s]:
                self.stats["jal"] += 1
                if t in self.callers:
                    self.stats["jal to a function start"] += 1
                    self.callees[s].add(t)
                    self.callers[t].add(s)
                elif t in side.starts:
                    self.stats["jal to a row with no bytes"] += 1
                else:
                    j = bisect.bisect_right(ordered, t) - 1
                    if j >= 0 and t < ordered[j] + side.size.get(ordered[j], 0):
                        self.stats["jal into a function body (not its start)"] += 1
                    else:
                        self.stats["jal outside every table row"] += 1

    def census(self, subset: Optional[Iterable[int]] = None) -> Dict[str, int]:
        pop = self.live if subset is None else [s for s in self.live if s in set(subset)]
        return {"functions": len(pop),
                "zero static callers": sum(1 for s in pop if not self.callers[s]),
                "zero callees": sum(1 for s in pop if not self.callees[s]),
                "isolated": sum(1 for s in pop if not self.callers[s] and not self.callees[s])}


def graphs(side: am.Side) -> Graph:
    """The static call graph of `side`: `.callees`, `.callers`, `.live`, `.stats`, `.census()`."""
    return Graph(side)


# ---- the keys --------------------------------------------------------------------------------

def keys(graph: Graph, placed: Dict[int, int]) -> Dict[str, Dict[int, object]]:
    """{kind: {address: key}} for EVERY live function of `graph`'s side, in demo addresses.

    `placed` maps an address on this side to its demo address (the demo side passes {d: d}). The keys
    of placed functions are computed too: the image-wide uniqueness census counts them, so an unplaced
    function sharing its key with an anchor is refused.
    """
    ce = {s: frozenset(placed[t] for t in graph.callees[s] if t in placed) for s in graph.live}
    cr = {s: frozenset(placed[c] for c in graph.callers[s] if c in placed) for s in graph.live}
    return {"callee": ce, "caller": cr, "pair": {s: (cr[s], ce[s]) for s in graph.live}}


def ksize(kind: str, key) -> int:
    return len(key[0]) + len(key[1]) if kind == "pair" else len(key)


def unique_pairs(kind: str, kd: Dict, ko: Dict, un_d: set, un_o: set) -> Dict[int, Tuple[int, int]]:
    """{demo addr: (our addr, |K|)} -- keys worn by exactly one live function per side, both unplaced."""
    cd, co = collections.defaultdict(list), collections.defaultdict(list)
    for s, k in kd.items():
        if ksize(kind, k):
            cd[k].append(s)
    for s, k in ko.items():
        if ksize(kind, k):
            co[k].append(s)
    out = {}
    for k, ds in cd.items():
        os_ = co.get(k)
        if len(ds) == 1 and os_ is not None and len(os_) == 1 and ds[0] in un_d and os_[0] in un_o:
            out[ds[0]] = (os_[0], ksize(kind, k))
    return out


def ratio(a: int, b: int) -> float:
    return min(a, b) / max(a, b) if max(a, b) else 0.0


# ---- link order (research/52 [7]'s bracket) ----------------------------------------------------

class Bracket:
    """Is our address between the our-images of the demo-order neighbouring anchors (same PT_LOAD)?"""

    def __init__(self, anchors, regions, our_live):
        self.rows = sorted(anchors)
        self.ds = [d for d, _o in self.rows]
        self.regions = regions

    def region(self, o):
        for lo, hi in self.regions:
            if lo <= o < hi:
                return lo
        return None

    def verdict(self, d: int, o: int) -> str:
        """'between', 'outside', or 'unknown' (no same-region demo-order neighbour on one side)."""
        i = bisect.bisect_left(self.ds, d)
        reg = self.region(o)
        prev = [r for r in self.rows[max(0, i - 12):i] if self.region(r[1]) == reg]
        nxt = [r for r in self.rows[i:i + 12] if r[0] != d and self.region(r[1]) == reg]
        if not prev or not nxt:
            return "unknown"
        return "between" if prev[-1][1] < o < nxt[0][1] else "outside"


def regions_of(side: am.Side) -> List[Tuple[int, int]]:
    """Our PT_LOADs as [lo, hi) -- symbol_levers' region logic: the demo's one PT_LOAD interleaves ours."""
    return [(v, v + len(d)) for v, d in side.image.segments]


# ---- the pass --------------------------------------------------------------------------------

class CgPair(NamedTuple):
    demo_addr: int
    our_addr: int
    round: int
    kinds: Tuple[str, ...]          # the keys that named this pair, in KINDS order
    ksizes: Tuple[int, ...]         # |K| of each, same order
    order: str                      # link-order verdict over that round's anchors

    @property
    def key_text(self) -> str:
        return "+".join(self.kinds)

    @property
    def ksize_text(self) -> str:
        return "+".join(str(k) for k in self.ksizes)


class Result(NamedTuple):
    pairs: List[CgPair]
    per_round: List[int]
    census: collections.Counter
    anchors: List[Tuple[int, int]]  # the anchors the pass started from (held addresses removed)


def _round(dg: Graph, og: Graph, demo: am.Side, ours: am.Side, anchors, regions, live_d, live_o):
    """({d: (o, kinds, ksizes, verdict)} accepted, {(d, o): reason} refused) for one round."""
    placed_d = {d for d, _o in anchors}
    o2d = {o: d for d, o in anchors}
    un_d, un_o = live_d - placed_d, live_o - set(o2d)
    kd, ko = keys(dg, {d: d for d in placed_d}), keys(og, o2d)
    found = collections.defaultdict(list)              # d -> [(o, kind, |K|)]
    for kind in KINDS:
        for d, (o, k) in unique_pairs(kind, kd[kind], ko[kind], un_d, un_o).items():
            ds, os_ = demo.size.get(d, 0), ours.size.get(o, 0)
            if ds < MIN_BODY or os_ < MIN_BODY or ratio(ds, os_) < SIZE_RATIO or k < MIN_K[kind]:
                continue
            found[d].append((o, kind, k))
    by_o = collections.defaultdict(set)
    for d, hits in found.items():
        for o, _kind, _k in hits:
            by_o[o].add(d)
    br = Bracket(anchors, regions, live_o)
    out, refused = {}, {}
    for d, hits in found.items():
        os_ = {o for o, _k, _n in hits}
        o = next(iter(os_))
        if len(os_) > 1 or len(by_o[o]) > 1:
            for x in os_:
                refused[(d, x)] = "claimed two ways"
            continue
        if not is_placeholder(ours.name.get(o, "")):
            refused[(d, o)] = "our row not a placeholder"
            continue
        verdict = br.verdict(d, o)
        if verdict == "outside":
            refused[(d, o)] = "link order outside"
            continue
        hits = sorted(hits, key=lambda h: KINDS.index(h[1]))
        out[d] = (o, tuple(h[1] for h in hits), tuple(h[2] for h in hits), verdict)
    return out, refused


def callgraph_pass(demo: am.Side, ours: am.Side, anchors, holds: Iterable[int] = (),
                   regions=None, dg: Optional[Graph] = None, og: Optional[Graph] = None,
                   max_rounds: int = MAX_ROUNDS) -> Result:
    """research/52's ORDERED rule, iterated to a fixed point. See `CALLGRAPH_RULE`.

    `anchors` is [(demo address, our address[, how])]; any whose our address is in `holds` is removed
    first (a held pair is a measured wrong or misnamed pair and may not anchor anything). `dg`/`og` let
    a caller that runs the pass many times (the holdout) build the graphs once.
    """
    holds = set(holds)
    dg = dg or graphs(demo)
    og = og or graphs(ours)
    regions = regions if regions is not None else regions_of(ours)
    census = collections.Counter()
    start = []
    for row in anchors:
        d, o = int(row[0]), int(row[1])
        if o in holds:
            census["anchors excluded: held"] += 1
        else:
            start.append((d, o))
    census["anchors used"] = len(start)
    live_d, live_o = set(dg.live), set(og.live)
    grown = list(start)
    pairs: List[CgPair] = []
    per_round: List[int] = []
    refused_all: Dict[Tuple[int, int], str] = {}
    for rnd in range(1, max_rounds + 1):
        new, refused = _round(dg, og, demo, ours, grown, regions, live_d, live_o)
        refused_all.update(refused)
        if not new:
            break
        per_round.append(len(new))
        for d, (o, kinds, ks, verdict) in sorted(new.items()):
            pairs.append(CgPair(d, o, rnd, kinds, ks, verdict))
            grown.append((d, o))
    taken = {(p.demo_addr, p.our_addr) for p in pairs}
    placed_d = {p.demo_addr for p in pairs}
    for (d, o), why in refused_all.items():
        if (d, o) not in taken and d not in placed_d:
            census["refused: " + why] += 1
    return Result(pairs, per_round, census, start)


# ---- the holdout (research/45 sec 3's shape) ---------------------------------------------------

def holdout(demo: am.Side, ours: am.Side, anchors3, holds: Iterable[int] = (), folds: int = 3,
            blocks: Sequence[int] = (8, 1), dg=None, og=None, regions=None) -> Dict[int, Dict]:
    """{block: {"round 1": (re-derived, wrong), "iterated": (re-derived, wrong), "wrong": [(d, o, truth)]}}.

    The truth is the PROVED Task 7 pairs (`symbol_levers.proved_anchors`) not at a held address; the
    prologue-only pairs stay anchors throughout. A derived pair counts when EITHER side is held out, and
    is wrong unless it is the held pair itself. Read with `CALLGRAPH_CAVEAT`.
    """
    holds = set(holds)
    dg = dg or graphs(demo)
    og = og or graphs(ours)
    rows = [(d, o, h) for d, o, h in sl._anchor_rows(anchors3) if o not in holds]
    proved = sl.proved_anchors(rows)
    pp = sorted((o, d) for d, o, _h in rows)
    eligible = [i for i, (_o, d) in enumerate(pp) if d in proved]
    out = {}
    for block in blocks:
        tally = {"round 1": [0, 0], "iterated": [0, 0], "wrong": []}
        for phase in range(folds):
            hold_i = {eligible[j] for j in range(len(eligible)) if (j // block) % folds == phase}
            held = [pp[i] for i in sorted(hold_i)]
            keep = [(d, o) for i, (o, d) in enumerate(pp) if i not in hold_i]
            truth_o = {o: d for o, d in held}
            truth_d = {d: o for o, d in held}
            res = callgraph_pass(demo, ours, keep, dg=dg, og=og, regions=regions)
            for p in res.pairs:
                if p.demo_addr in truth_d or p.our_addr in truth_o:
                    bad = truth_d.get(p.demo_addr) != p.our_addr
                    for label in (("round 1", "iterated") if p.round == 1 else ("iterated",)):
                        tally[label][0] += 1
                        tally[label][1] += int(bad)
                    if bad:
                        tally["wrong"].append((p.demo_addr, p.our_addr, truth_d.get(p.demo_addr)))
        out[block] = {"round 1": tuple(tally["round 1"]), "iterated": tuple(tally["iterated"]),
                      "wrong": tally["wrong"]}
    return out


def holdout_lines(result: Dict[int, Dict], demo: am.Side, n_proved: int, folds: int) -> List[str]:
    lines = ["holdout over the %d PROVED Task 7 pairs not held (%d folds): %s"
             % (n_proved, folds, "; ".join(
                 "blocks of %d: round 1 %d re-derived / %d wrong, iterated %d / %d"
                 % ((b,) + v["round 1"] + v["iterated"]) for b, v in sorted(result.items(), reverse=True)))]
    for b, v in sorted(result.items(), reverse=True):
        for d, o, t in v["wrong"]:
            lines.append("  holdout wrong (blocks of %d): %s @0x%06x -> 0x%08x; truth %s"
                         % (b, demo.name.get(d, "?"), d, o, "0x%08x" % t if t else "a held row of ours"))
    return lines


# ---- the proposals ---------------------------------------------------------------------------

def read_proposals(path: str) -> List[Tuple[int, str]]:
    """[(our address, proposed identifier)] from any renames file (its `#` header skipped)."""
    with open(path, newline="") as fh:
        body = [ln for ln in fh if not ln.startswith("#")]
    out = []
    for row in csv.DictReader(body):
        if row.get("Address") and row.get("Proposed"):
            out.append((int(row["Address"], 16), row["Proposed"]))
    return out


def read_holds(path: str) -> Dict[int, Dict[str, str]]:
    """{our address: row} from recomp/socom2_name_holds.csv (`Address, Proposed, Reason, Source`)."""
    with open(path, newline="") as fh:
        return {int(r["Address"], 16): r for r in csv.DictReader(fh)}


def proposals(result: Result, demo: am.Side, ours: am.Side, holds: Iterable[int] = (),
              others: Optional[Dict[str, List[Tuple[int, str]]]] = None, taken: Iterable[str] = ()):
    """(strict rows, loose rows, census) -- Task 7's identifier hurdles, then the other files.

    Refused, each counted under `refused: <reason>`: our row not a placeholder or at a held address; a
    demo name on two of this pass's pairs (a C `static` in two translation units: which is which is
    not knowable here); two pairs whose names sanitise to one identifier; an identifier in `taken`
    (the 987's names and our csv's own non-placeholder names); an identifier another renames file
    spends at another address; another file proposing a different name for this address (S12-R18:
    two levers disagreeing -- this file refuses its side and the census prints it). The same
    identifier at the same address in another file is an agreement, kept and counted.
    """
    holds = set(holds)
    others = others or {}
    census = collections.Counter()
    taken = set(taken)
    by_name = collections.Counter(demo.name[p.demo_addr] for p in result.pairs)
    by_ident = collections.Counter(c_identifier(demo.name[p.demo_addr]) for p in result.pairs)
    other_ident = collections.defaultdict(set)
    other_addr = collections.defaultdict(set)
    for _f, rows in others.items():
        for a, ident in rows:
            if a in holds:
                continue
            other_ident[ident].add(a)
            other_addr[a].add(ident)
    strict, loose = [], []
    for p in sorted(result.pairs, key=lambda q: q.our_addr):
        name, cur = demo.name[p.demo_addr], ours.name.get(p.our_addr, "")
        ident = c_identifier(name)
        if not is_placeholder(cur):
            census["refused: our row not a placeholder"] += 1
            continue
        if p.our_addr in holds:
            census["refused: held address (recomp/socom2_name_holds.csv)"] += 1
            continue
        if by_name[name] > 1:
            census["refused: demo name on two pairs"] += 1
            continue
        if by_ident[ident] > 1:
            census["refused: identifier collides after sanitising"] += 1
            continue
        if ident in taken:
            census["refused: identifier already carried by a Task 7 pair or a named row"] += 1
            continue
        if other_ident.get(ident, set()) - {p.our_addr}:
            census["refused: identifier spent by another file at another address"] += 1
            continue
        if other_addr.get(p.our_addr, set()) - {ident}:
            census["refused: another file proposes a different name for this address"] += 1
            continue
        if p.our_addr in other_ident.get(ident, set()):
            census["agrees with another file"] += 1
        score = SCORE_ROUND_1 if p.round == 1 else SCORE_LATER
        ds, os_ = demo.size[p.demo_addr], ours.size[p.our_addr]
        row = {"Address": "0x%08x" % p.our_addr, "Current": cur, "Proposed": ident, "Mangled": name,
               "Score": "%.2f" % score, "How": HOW,
               "Evidence": "callgraph round %d; key=%s; |K|=%s; order=%s"
                           % (p.round, p.key_text, p.ksize_text, p.order),
               "Round": p.round, "Key": p.key_text, "KeySize": p.ksize_text, "Order": p.order,
               "DemoAddr": "0x%08x" % p.demo_addr, "DemoSize": ds, "OurSize": os_,
               "Ratio": "%.2f" % ratio(ds, os_)}
        (strict if p.round == 1 else loose).append(row)
    return strict, loose, census


def other_files(out_path: str) -> Dict[str, List[Tuple[int, str]]]:
    """Every other game/demo_symbol_renames*.csv beside `out_path` (this pass's two files excluded)."""
    mine = {os.path.abspath(out_path), os.path.abspath(loose_path(out_path))}
    pattern = os.path.join(os.path.dirname(os.path.abspath(out_path)), "demo_symbol_renames*.csv")
    return {p: read_proposals(p) for p in sorted(glob.glob(pattern)) if os.path.abspath(p) not in mine}


def header_lines(path: str, result: Result, holdout_lines: Optional[Sequence[str]], anchor_note: str,
                 extra: Sequence[str] = ()) -> List[str]:
    loose = is_loose_path(path)
    lines = [
        "%s -- Sprint 12 Task 15 `callgraph` proposals, %s. PROPOSALS ONLY:"
        % (os.path.basename(path), "rounds 2+ at Score %.2f (LOOSE: needs a second lever)" % SCORE_LATER
           if loose else "round 1 at Score %.2f (strict)" % SCORE_ROUND_1),
        "recomp/socom2_ghidra.csv is unchanged; applying is Task 3's reviewed step, to the sidecar (S12-R13).",
        "Names come from the SOCOM 1 demo's .symtab. Addresses are OURS (r0001). "
        "docs/research/52-callgraph-propagation.md",
        "",
        CALLGRAPH_RULE,
        "",
        CALLGRAPH_CAVEAT,
        "",
        "Anchors: %s" % anchor_note,
        "Rounds: %d; %s; total %d" % (len(result.per_round), ", ".join(
            "round %d: %d" % (i + 1, n) for i, n in enumerate(result.per_round)), sum(result.per_round)),
    ]
    lines += list(holdout_lines) if holdout_lines else ["Holdout: not run for this file (--holdout)."]
    lines += list(extra)
    lines.append("")
    return lines


def write_proposals(path: str, rows: Sequence[Dict], header: Sequence[str]) -> None:
    """The file, its rule in `#` lines above the columns. A round-1 row belongs at the strict path and
    a later round at the `_loose` one; anything else is a ValueError, whoever calls this."""
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise ValueError("cannot write %s: %s is not a directory" % (path, directory))
    loose = is_loose_path(path)
    wrong = [r for r in rows if (int(r["Round"]) == 1) == loose]
    if wrong:
        raise ValueError("cannot write %s: %d row(s) of round %s belong at the %s path"
                         % (path, len(wrong), sorted({int(r["Round"]) for r in wrong}),
                            "strict" if loose else "loose (%s)" % loose_path(path)))
    with open(path, "w", newline="") as fh:
        for line in header:
            fh.write("# %s\n" % line if line else "#\n")
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row)


# ---- the CLI ---------------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="the callgraph lever (Sprint 12 Task 15, research/52)")
    ap.add_argument("demo_elf")
    ap.add_argument("our_elf")
    ap.add_argument("our_csv")
    ap.add_argument("matches", help="game/demo_symbol_matches.json: Task 7's pairs, checked against the re-derivation")
    ap.add_argument("--out", default="game/demo_symbol_renames_callgraph.csv")
    ap.add_argument("--holds", default="recomp/socom2_name_holds.csv")
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--holdout-folds", type=int, default=3)
    args = ap.parse_args(argv)
    for p in (args.demo_elf, args.our_elf, args.our_csv, args.matches, args.holds):
        if not os.path.exists(p):
            print("NO-DATA: missing %s" % p)
            return 2
    if is_loose_path(args.out):
        print("NO-DATA: --out names the strict file; the loose one is written beside it")
        return 2

    demo_rows, demo_segs = gsm.load_demo(args.demo_elf)
    our_rows, our_segs = gsm.load_ours(args.our_elf, args.our_csv)
    details: Dict = {}
    gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
    on_disk = {(p["name"], int(p["addr"], 16)) for p in json.load(open(args.matches))["pairs"]}
    if on_disk != set(details):
        print("NO-DATA: the re-derived Task 7 pairs (%d) differ from %s (%d): %d only re-derived, %d only on disk"
              % (len(details), args.matches, len(on_disk), len(set(details) - on_disk), len(on_disk - set(details))))
        return 2
    anchors3 = sl.anchors_from_details(details)
    holds = read_holds(args.holds)
    kept3 = [r for r in anchors3 if r[1] not in holds]
    comp = ", ".join("%s %d" % kv for kv in sorted(sl.anchor_composition(kept3).items()))
    proved = sl.proved_anchors(kept3)
    anchor_note = ("%d Task 7 pairs (re-derived with --prefix; agree with %s: %d of %d); %d held pair(s) "
                   "excluded (%s: %s); %d used (%s); %d PROVED"
                   % (len(anchors3), args.matches, len(on_disk & set(details)), len(on_disk),
                      len(anchors3) - len(kept3), args.holds,
                      ", ".join("0x%08x" % a for a in sorted(holds) if any(r[1] == a for r in anchors3)),
                      len(kept3), comp, len(proved)))
    print("anchors: " + anchor_note)

    demo, ours = am.Side(demo_rows, demo_segs), am.Side(our_rows, our_segs)
    dg, og = graphs(demo), graphs(ours)
    regions = regions_of(ours)
    placed_d = {d for d, _o, _h in kept3}
    placed_o = {o for _d, o, _h in kept3}
    graph_lines = []
    for label, g, placed in (("demo", dg, placed_d), ("ours", og, placed_o)):
        graph_lines.append("graph %s: %s" % (label, ", ".join("%s %d" % kv for kv in sorted(g.stats.items()))))
        graph_lines.append("graph %s: all live %s; unplaced %s" % (
            label, ", ".join("%s %d" % kv for kv in g.census().items()),
            ", ".join("%s %d" % kv for kv in g.census(set(g.live) - placed).items())))
    for ln in graph_lines:
        print(ln)

    res = callgraph_pass(demo, ours, kept3, dg=dg, og=og, regions=regions)
    print("pass: rounds %d, per round %s, total %d; %s"
          % (len(res.per_round), res.per_round, sum(res.per_round),
             ", ".join("%s %d" % kv for kv in sorted(res.census.items()))))
    orders = collections.Counter(("round 1" if p.round == 1 else "rounds 2+", p.order) for p in res.pairs)
    kinds = collections.Counter(("round 1" if p.round == 1 else "rounds 2+", p.key_text) for p in res.pairs)
    print("  order verdicts: " + ", ".join("%s %s %d" % (k[0], k[1], v) for k, v in sorted(orders.items())))
    print("  keys: " + ", ".join("%s %s %d" % (k[0], k[1], v) for k, v in sorted(kinds.items())))
    held_hit = [p for p in res.pairs if p.our_addr in holds]
    for p in held_hit:
        print("  pairs a held address: 0x%08x <- %s (round %d, key %s); hold: %s %s"
              % (p.our_addr, demo.name[p.demo_addr], p.round, p.key_text, holds[p.our_addr]["Proposed"],
                 holds[p.our_addr]["Source"]))

    taken = {c_identifier(demo.name[d]) for d, o, _h in kept3}
    taken |= {c_identifier(ours.name[s]) for s in ours.starts if not is_placeholder(ours.name[s])}
    others = other_files(args.out)
    strict, loose, census = proposals(res, demo, ours, holds=holds, others=others, taken=taken)
    print("proposals: strict %d, loose %d; %s" % (len(strict), len(loose),
                                                  ", ".join("%s %d" % kv for kv in sorted(census.items()))))
    all_rows = {int(r["Address"], 16): r["Proposed"] for r in strict + loose}
    idents = collections.defaultdict(set)
    for a, i in all_rows.items():
        idents[i].add(a)
    other_lines = []
    for path, rows in others.items():
        same = sum(1 for a, i in rows if all_rows.get(a) == i)
        ident_else = sorted((a, i) for a, i in rows if a not in holds and i in idents and a not in idents[i])
        addr_diff = sorted((a, i) for a, i in rows if a not in holds and a in all_rows and all_rows[a] != i)
        # what the hurdle refused: recompute over the pass's pairs
        refused_i = sorted((p.our_addr, c_identifier(demo.name[p.demo_addr])) for p in res.pairs
                           if any(x == c_identifier(demo.name[p.demo_addr]) and a != p.our_addr and a not in holds
                                  for a, x in rows))
        refused_a = sorted((p.our_addr, c_identifier(demo.name[p.demo_addr]), x) for p in res.pairs
                           for a, x in rows if a == p.our_addr and a not in holds
                           and x != c_identifier(demo.name[p.demo_addr]))
        other_lines.append("other file %s: %d rows; same (address, name) %d; this pass's identifier at "
                           "another address there %d; another name for this pass's address %d"
                           % (os.path.relpath(path), len(rows), same, len(refused_i), len(refused_a)))
        for a, i in refused_i:
            other_lines.append("  refused, identifier spent there elsewhere: 0x%08x %s" % (a, i))
        for a, i, x in refused_a:
            other_lines.append("  refused, two names for one address: 0x%08x callgraph %s, that file %s" % (a, i, x))
        assert not ident_else and not addr_diff     # the hurdle removed them from the written rows
    for ln in other_lines:
        print(ln)

    hold_lines = None
    if args.holdout:
        ho = holdout(demo, ours, kept3, holds=(), folds=args.holdout_folds, dg=dg, og=og, regions=regions)
        hold_lines = holdout_lines(ho, demo, len(proved), args.holdout_folds)
        for ln in hold_lines:
            print(ln)

    extra = (graph_lines
             + ["pass: rounds %d, per round %s; %s" % (len(res.per_round), res.per_round, ", ".join(
                 "%s %d" % kv for kv in sorted(res.census.items())))]
             + ["proposals: strict %d, loose %d; %s" % (len(strict), len(loose), ", ".join(
                 "%s %d" % kv for kv in sorted(census.items())))]
             + other_lines)
    try:
        for path, rows in ((args.out, strict), (loose_path(args.out), loose)):
            write_proposals(path, rows, header_lines(path, res, hold_lines, anchor_note, extra))
            print("wrote %s: %d rows" % (path, len(rows)))
    except ValueError as exc:
        print("NO-DATA: %s" % exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
