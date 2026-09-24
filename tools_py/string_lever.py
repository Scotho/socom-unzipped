"""Sprint 12 Task 12: the `string-set` pass -- names from the set of shared strings a body references.

docs/research/53-string-correlator.md measured it (rule R3; `tools_py/research/symbols/string_correlator.py`
is the measurement, this is the pass). Task 7 (`ghidra_symbol_match`) placed 987 of the SOCOM 1 demo's
functions onto our rows by fingerprint; the fingerprint zeroes every address-forming immediate, so it
cannot see WHICH strings a body names. The string-bearing code -- the FTS application layer, menus, HUD,
lobby -- is exactly what a year of edits changed too much for a fingerprint, and what this pass reaches.

    python -m tools_py.string_lever game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf \\
        recomp/socom2_ghidra.csv game/demo_symbol_matches.json \\
        --out game/demo_symbol_renames_strings.csv [--holdout] [--loose]

The pieces, each reused rather than re-spelt:

  * a string is `address_matcher.Image.cstring`'s: NUL-terminated, >= 4 printable bytes;
  * a reference is `address_matcher.formed_addresses` (`lui` + low half), i.e. `Side.anchors()`'s own
    mechanism -- `string_keys` returns exactly `Side.anchors()` as a frozenset;
  * a SHARED string is one the code references in BOTH images (research/53 sec 0: a string only one
    side references can never make two keys equal, so it is dropped from both);
  * link order is research/45 sec 1's, per PT_LOAD of ours; the placed callees are Q7's kind, carried
    through Task 7's pairs; the folds are `symbol_levers.holdout`'s; `MIN_BODY`, `SIZE_RATIO`,
    `loose_path` and `is_loose_path` are `symbol_levers`'; the identifier hurdles are Task 7's
    (`c_identifier`) and the placeholder test is `name_provenance.is_placeholder`.

Nothing here writes `recomp/socom2_ghidra.csv` or the sidecar; the applier (Task 3) does that.
"""
import argparse
import bisect
import collections
import csv
import json
import os
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from tools_py import address_matcher as am
from tools_py.ghidra_symbol_match import c_identifier
from tools_py.name_provenance import is_placeholder
from tools_py.symbol_levers import (MIN_BODY, SIZE_RATIO, _anchor_rows, anchor_composition,
                                    anchors_from_details, is_loose_path, loose_path, proved_anchors)

SCORE = 0.80
HOW = "string-set"

STRING_RULE = (
    "string-set (research/53 rule R3, S12-R8): among the functions Task 7 left unplaced (its 987 pairs are "
    "the anchors), the set of SHARED strings a body references -- NUL-terminated, >= 4 printable bytes, "
    "its address formed by a lui pair, referenced by code in BOTH images -- is non-empty and worn by "
    "exactly one demo function and exactly one of our rows; both bodies >= %d B and size ratio >= %.2f; "
    "the placed callees (demo callees carried through Task 7's pairs, against ours that are Task 7 rows) "
    "not `disjoint`; link order against the flanking Task 7 anchors in our PT_LOAD not `outside`; and at "
    "least one positive signal: link order `between` or callees `overlap`. Then Task 7's identifier "
    "hurdles: our row still a placeholder, and a C identifier that no other row of this file, no other "
    "proposals file, no Task 7 pair and no csv name spends (one name on two of our rows is hurdle 4). Score %.2f, How `%s`; Evidence "
    "`strings=<n>;order=<verdict>;callees=<verdict>`."
) % (MIN_BODY, SIZE_RATIO, SCORE, HOW)

LOOSE_RULE = (
    "string-set LOOSE (research/53 rule R0): the same unique set, both bodies >= %d B, ratio >= %.2f, and "
    "NOTHING ELSE -- every row here failed R3 because a non-string signal spoke against it (callees "
    "disjoint, link order outside) or none spoke for it. Never applied without a body read; no score."
) % (MIN_BODY, SIZE_RATIO)

# S12-R9: the body read settled research/53 sec 4.3 -- Task 7's `exact` pair NetGetBuildTimeStamp ->
# 0x006473f0 (row 478, held in recomp/socom2_name_holds.csv) is wrong: 0x006473f0 is the demo's
# MediusGetBuildTimeStamp and 0x00620518 its NetGetBuildTimeStamp. The holdout scores against Task 7
# corrected by this (and prints the uncorrected count beside it).
ROW_478_CORRECTION = {0x006473f0: "MediusGetBuildTimeStamp", 0x00620518: "NetGetBuildTimeStamp"}

TAKEN_FILES = ("game/demo_symbol_renames.csv", "game/demo_symbol_renames_7b.csv",
               "game/demo_symbol_renames_7c.csv")

KINDS = ("set", "multiset", "sequence", "unique-string", "set+callees")


# ---- the keys ---------------------------------------------------------------------------------------

def string_refs(side: am.Side, start: int) -> List[bytes]:
    """The strings a body forms the address of, in instruction order, repeats kept."""
    out = []
    for addr in am.formed_addresses(side.body.get(start, b"")):
        text = side.image.cstring(addr)
        if text:
            out.append(text)
    return out


def string_keys(side: am.Side, shared: Optional[set] = None) -> Dict[int, frozenset]:
    """{start: the set of strings the body forms the address of} -- `Side.anchors()` as a frozenset,
    restricted to `shared` when given. A function with an empty key is left out: it never pairs."""
    out = {}
    for start in side.starts:
        if not side.body.get(start):
            continue
        key = frozenset(s for s in side.anchors(start) if shared is None or s in shared)
        if key:
            out[start] = key
    return out


def shared_strings(demo: am.Side, ours: am.Side) -> set:
    """The key alphabet: the strings code references in BOTH images (research/53 sec 0)."""
    def referenced(side):
        return {s for a in side.starts for s in side.anchors(a)}
    return referenced(demo) & referenced(ours)


def shared_keys(demo: am.Side, ours: am.Side) -> Tuple[Dict[int, frozenset], Dict[int, frozenset]]:
    shared = shared_strings(demo, ours)
    return string_keys(demo, shared), string_keys(ours, shared)


def pair_unique(keys_d: Dict[int, object], keys_o: Dict[int, object], pool_d, pool_o) -> Dict[int, int]:
    """{demo: ours} where the key is worn by exactly one pool function on each side."""
    by_d: Dict[object, List[int]] = collections.defaultdict(list)
    by_o: Dict[object, List[int]] = collections.defaultdict(list)
    for a, k in keys_d.items():
        if a in pool_d:
            by_d[k].append(a)
    for a, k in keys_o.items():
        if a in pool_o:
            by_o[k].append(a)
    return {v[0]: by_o[k][0] for k, v in by_d.items() if len(v) == 1 and len(by_o.get(k, ())) == 1}


# ---- the two signals that never look at a string ----------------------------------------------------

def _regions(ours: am.Side) -> List[Tuple[int, int]]:
    return [(v, v + len(b)) for v, b in ours.image.segments]


def signals(demo: am.Side, ours: am.Side, amap: Dict[int, int]):
    """(order, callees) for a pair (d, o), from the anchors {demo: ours} in `amap`.

    order -- research/45 sec 1: in o's PT_LOAD take the nearest anchors below and above o; `between`
      when d lies between their demo addresses, `outside` when not, `anchors-out-of-order` when the two
      anchors disagree with each other, `edge` at a region end. `skip` leaves one anchor (o, d) out.
    callees -- the demo callees carried through `amap` against our callees that are anchors:
      `overlap`, `disjoint`, `one side` or `none`.
    """
    regions = _regions(ours)
    reg = {r: sorted((o, d) for d, o in amap.items() if r[0] <= o < r[1]) for r in regions}
    placed_o = set(amap.values())

    def order(d, o, skip=None):
        for r in regions:
            if r[0] <= o < r[1]:
                lst = [x for x in reg[r] if x != skip] if skip else reg[r]
                i = bisect.bisect_left(lst, (o, -1))
                j = i + 1 if i < len(lst) and lst[i][0] == o else i
                if i == 0 or j >= len(lst):
                    return "edge"
                (_o1, d1), (_o2, d2) = lst[i - 1], lst[j]
                if d2 <= d1:
                    return "anchors-out-of-order"
                return "between" if d1 < d < d2 else "outside"
        return "edge"

    def callees(d, o):
        a = {amap[t] for t in demo.calls.get(d, ()) if t in amap}
        b = {t for t in ours.calls.get(o, ()) if t in placed_o}
        if not a and not b:
            return "none"
        if not a or not b:
            return "one side"
        return "overlap" if a & b else "disjoint"

    return order, callees


def _sizes_ok(demo: am.Side, ours: am.Side, d: int, o: int) -> Tuple[bool, bool]:
    """(both >= MIN_BODY, ratio >= SIZE_RATIO)."""
    ds, os_ = demo.size.get(d, 0), ours.size.get(o, 0)
    big = ds >= MIN_BODY and os_ >= MIN_BODY
    return big, big and min(ds, os_) / max(ds, os_) >= SIZE_RATIO


def r3(order_v: str, callee_v: str) -> bool:
    """Rule R3's second-signal test: nothing against, something for."""
    return (callee_v != "disjoint" and order_v != "outside"
            and (order_v == "between" or callee_v == "overlap"))


# ---- the pass -----------------------------------------------------------------------------------------

class StringCandidate(NamedTuple):
    our_addr: int
    demo_addr: int
    demo_name: str
    our_name: str
    demo_size: int
    our_size: int
    strings: int              # distinct shared strings in the set
    order: str
    callees: str
    level: str                # "strict" (R3) or "loose" (R0 and not R3)

    @property
    def ratio(self) -> float:
        hi = max(self.demo_size, self.our_size)
        return min(self.demo_size, self.our_size) / hi if hi else 0.0

    @property
    def evidence(self) -> str:
        return "strings=%d;order=%s;callees=%s" % (self.strings, self.order, self.callees)


CENSUS_KEYS = ("anchors", "pool demo", "pool ours", "keyed demo", "keyed ours", "key unique both ways",
               "body under 64 B", "size ratio under 0.50", "R0",
               "refused: callees disjoint", "refused: link order outside", "refused: no positive signal",
               "R3", "our row already named", "identifier spent or collides",
               "strict", "loose")


def _r0_pairs(demo, ours, keys, anchors_rows):
    """(R0 {d: o}, census so far) -- the unique set over the unplaced pool, with the size floors."""
    keys_d, keys_o = keys
    anch_d = {d for d, _o, _h in anchors_rows}
    anch_o = {o for _d, o, _h in anchors_rows}
    pool_d = {a for a in demo.starts if demo.body.get(a)} - anch_d
    pool_o = {a for a in ours.starts if ours.body.get(a)} - anch_o
    census = collections.OrderedDict((k, 0) for k in CENSUS_KEYS)
    census["anchors"] = len(anchors_rows)
    census["pool demo"], census["pool ours"] = len(pool_d), len(pool_o)
    census["keyed demo"] = sum(1 for a in keys_d if a in pool_d)
    census["keyed ours"] = sum(1 for a in keys_o if a in pool_o)
    got = pair_unique(keys_d, keys_o, pool_d, pool_o)
    census["key unique both ways"] = len(got)
    r0 = {}
    for d, o in got.items():
        big, ratio = _sizes_ok(demo, ours, d, o)
        if not big:
            census["body under 64 B"] += 1
        elif not ratio:
            census["size ratio under 0.50"] += 1
        else:
            r0[d] = o
    census["R0"] = len(r0)
    return r0, census


def string_pass(demo: am.Side, ours: am.Side, anchors, taken: Iterable[str] = (), keys=None):
    """(strict, loose, census) -- rule R3 (and the loose R0 remainder) over the unplaced functions.

    `anchors` is [(demo_addr, our_addr[, how])], Task 7's pairs: they are the anchors for link order
    and callees and the functions a candidate may never be. `taken` is every identifier already
    spent elsewhere (the other proposals files, Task 7's pairs, the csv's own names). `strict` and
    `loose` are [StringCandidate]; a loose row is an R0 row R3 refused, never a strict one.
    """
    rows = _anchor_rows(anchors)
    amap = {d: o for d, o, _h in rows}
    if keys is None:
        keys = shared_keys(demo, ours)
    r0, census = _r0_pairs(demo, ours, keys, rows)
    order, callees = signals(demo, ours, amap)
    cands = []
    for d, o in sorted(r0.items(), key=lambda p: p[1]):
        ov, cv = order(d, o), callees(d, o)
        if cv == "disjoint":
            census["refused: callees disjoint"] += 1
            level = "loose"
        elif ov == "outside":
            census["refused: link order outside"] += 1
            level = "loose"
        elif not r3(ov, cv):
            census["refused: no positive signal"] += 1
            level = "loose"
        else:
            census["R3"] += 1
            level = "strict"
        cands.append(StringCandidate(o, d, demo.name[d], ours.name.get(o, ""), demo.size[d],
                                     ours.size[o], len(keys[0][d]), ov, cv, level))

    # Task 7's identifier hurdles. A strict row is never knocked out by a loose one: the strict file's
    # spellings are counted over strict + taken, the loose file's over strict + loose + taken.
    # Hurdle 4 (one demo name on two of OUR rows) is the spelling count below: Task 7's 987 names are
    # in `taken`, and two candidates with one name count each other. A name the DEMO carries at several
    # addresses (a `static` in several translation units) is not refused: the key chose one of them,
    # and each carries that name.
    taken = list(taken)
    spell_strict = collections.Counter(c_identifier(c.demo_name) for c in cands if c.level == "strict")
    spell_all = collections.Counter(c_identifier(c.demo_name) for c in cands)
    for t in set(taken):
        spell_strict[t] += 1
        spell_all[t] += 1
    strict, loose = [], []
    for c in cands:
        if not is_placeholder(c.our_name):
            census["our row already named"] += 1
            continue
        spelling = spell_strict if c.level == "strict" else spell_all
        if spelling[c_identifier(c.demo_name)] > 1:
            census["identifier spent or collides"] += 1
            continue
        (strict if c.level == "strict" else loose).append(c)
    census["strict"], census["loose"] = len(strict), len(loose)
    return strict, loose, census


# ---- contradictions with Task 7 -----------------------------------------------------------------------

def _all_keys(demo: am.Side, ours: am.Side, amap: Dict[int, int]):
    """{kind: ({start: key} demo, {start: key} ours)} for the five kinds research/53 S2/S3 measured."""
    shared = shared_strings(demo, ours)
    out = {k: ({}, {}) for k in ("set", "multiset", "sequence", "set+callees")}
    placed_o = set(amap.values())
    for side_i, side in enumerate((demo, ours)):
        for start in side.starts:
            if not side.body.get(start):
                continue
            sh = [s for s in string_refs(side, start) if s in shared]
            if not sh:
                continue
            st = frozenset(sh)
            out["set"][side_i][start] = st
            out["multiset"][side_i][start] = tuple(sorted(collections.Counter(sh).items()))
            out["sequence"][side_i][start] = tuple(sh)
            if side_i == 0:
                cal = frozenset(amap[t] for t in side.calls.get(start, ()) if t in amap)
            else:
                cal = frozenset(t for t in side.calls.get(start, ()) if t in placed_o)
            out["set+callees"][side_i][start] = (st, cal)
    return out


def _pair_unique_string(sets_d, sets_o, pool_d, pool_o) -> Dict[int, int]:
    """research/53's `unique-string` key: a shared string referenced by one pool function on each side
    pairs them; a function whose unique strings point at two partners pairs with neither."""
    users_d, users_o = collections.defaultdict(list), collections.defaultdict(list)
    for a, st in sets_d.items():
        if a in pool_d:
            for s in st:
                users_d[s].append(a)
    for a, st in sets_o.items():
        if a in pool_o:
            for s in st:
                users_o[s].append(a)
    part_d, part_o = collections.defaultdict(set), collections.defaultdict(set)
    for s, ud in users_d.items():
        uo = users_o.get(s, ())
        if len(ud) == 1 and len(uo) == 1:
            part_d[ud[0]].add(uo[0])
            part_o[uo[0]].add(ud[0])
    out = {}
    for d, ps in part_d.items():
        if len(ps) == 1:
            o = next(iter(ps))
            if part_o[o] == {d}:
                out[d] = o
    return out


def contradictions(demo: am.Side, ours: am.Side, anchors) -> List[Dict]:
    """The Task 7 pairs a string key (any kind, image-wide) contradicts -- research/53 S4b.

    One entry per string pairing (d, o) that touches a Task 7 pair on either side and is not that pair:
    {demo_addr, our_addr, demo_name, kinds, task7_our (where Task 7 put d, or None), rival_demo (the
    demo function Task 7 put on o, or None), rival_how}. Reported only; the holds file is the applier's.
    """
    rows = _anchor_rows(anchors)
    amap = {d: o for d, o, _h in rows}
    how_d = {d: h for d, _o, h in rows}
    inv = {o: d for d, o in amap.items()}
    keys = _all_keys(demo, ours, amap)
    live_d = {a for a in demo.starts if demo.body.get(a)}
    live_o = {a for a in ours.starts if ours.body.get(a)}
    found: Dict[Tuple[int, int], List[str]] = collections.defaultdict(list)
    for kind in KINDS:
        if kind == "unique-string":
            got = _pair_unique_string(keys["set"][0], keys["set"][1], live_d, live_o)
        else:
            got = pair_unique(keys[kind][0], keys[kind][1], live_d, live_o)
        for d, o in got.items():
            if (d in amap or o in inv) and amap.get(d) != o:
                found[(d, o)].append(kind)
    out = []
    for (d, o), kinds in sorted(found.items()):
        rival = inv.get(o)
        out.append({"demo_addr": d, "our_addr": o, "demo_name": demo.name[d], "kinds": kinds,
                     "demo_size": demo.size.get(d, 0), "our_size": ours.size.get(o, 0),
                     "task7_our": amap.get(d), "task7_how": how_d.get(d),
                     "rival_demo": rival, "rival_how": how_d.get(rival) if rival is not None else None})
    return out


# ---- the holdout ---------------------------------------------------------------------------------------

def holdout(demo: am.Side, ours: am.Side, anchors, folds: int = 3, block: int = 8,
            corrections: Optional[Dict[int, int]] = None, keys=None) -> Dict[str, int]:
    """{re-derived, wrong, wrong by Task 7} -- rule R3 re-deriving Task 7's PROVED pairs.

    research/45 sec 3's folds, as `symbol_levers.holdout` builds them: the pairs sorted by our address;
    only the PROVED ones (not `prefix*`) are eligible to be held out; runs of `block` consecutive
    eligible pairs go to fold (j // block) % folds. The kept pairs are the anchors -- for the pool, the
    link order and the callees. A pair R3 derives is judged when either side is held out, and is wrong
    when it is not the truth. `corrections` is {our_addr: demo_addr} overriding Task 7's answer (the
    S12-R9 body read); `wrong by Task 7` is the same count against the uncorrected answer.
    """
    rows = _anchor_rows(anchors)
    if keys is None:
        keys = shared_keys(demo, ours)
    keys_d, keys_o = keys
    pp = sorted((o, d) for d, o, _h in rows)
    proved = proved_anchors(rows)
    t7 = {d: o for o, d in pp}
    truth = dict(t7)
    for o, d in (corrections or {}).items():
        truth[d] = o
    eligible = [i for i, (_o, d) in enumerate(pp) if d in proved]
    all_d, all_o = {d for _o, d in pp}, {o for o, _d in pp}
    live_d = {a for a in demo.starts if demo.body.get(a)}
    live_o = {a for a in ours.starts if ours.body.get(a)}
    n = wrong = wrong_t7 = 0
    block = max(1, int(block))
    for phase in range(folds):
        hold = {eligible[j] for j in range(len(eligible)) if (j // block) % folds == phase}
        held_d = {pp[i][1] for i in hold}
        held_o = {pp[i][0] for i in hold}
        amap = {d: o for i, (o, d) in enumerate(pp) if i not in hold}
        pool_d = live_d - (all_d - held_d)
        pool_o = live_o - (all_o - held_o)
        order, callees = signals(demo, ours, amap)
        for d, o in pair_unique(keys_d, keys_o, pool_d, pool_o).items():
            if d not in held_d and o not in held_o:
                continue
            if not _sizes_ok(demo, ours, d, o)[1] or not r3(order(d, o), callees(d, o)):
                continue
            n += 1
            wrong += int(truth.get(d) != o)
            wrong_t7 += int(t7.get(d) != o)
    return {"re-derived": n, "wrong": wrong, "wrong by Task 7": wrong_t7}


# ---- the proposals file --------------------------------------------------------------------------------

PROPOSAL_COLUMNS = ["Address", "Current", "Proposed", "Mangled", "Score", "How", "Size", "Evidence",
                    "Level", "DemoAddr", "DemoSize", "OurSize", "Ratio"]


def proposal_rows(cands: Sequence[StringCandidate]) -> List[Dict]:
    """The file's rows, by our address. `Size` is the demo body, as in Task 7's file; a loose row has
    How `string-set-loose` and no score, so no reader can mistake it for a proposal."""
    out = []
    for c in sorted(cands, key=lambda c: c.our_addr):
        strict = c.level == "strict"
        out.append({"Address": "0x%08x" % c.our_addr, "Current": c.our_name,
                    "Proposed": c_identifier(c.demo_name), "Mangled": c.demo_name,
                    "Score": "%.2f" % SCORE if strict else "", "How": HOW if strict else HOW + "-loose",
                    "Size": c.demo_size, "Evidence": c.evidence, "Level": c.level,
                    "DemoAddr": "0x%08x" % c.demo_addr, "DemoSize": c.demo_size,
                    "OurSize": c.our_size, "Ratio": "%.2f" % c.ratio})
    return out


def write_proposals(path: str, rows: Sequence[Dict], header: Sequence[str]) -> None:
    """The file, its rule in `#` lines above the column header. The strict path refuses a loose row and
    the loose path (`symbol_levers.loose_path`) a strict one -- a ValueError, raised before writing."""
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise ValueError("cannot write %s: %s is not a directory" % (path, directory))
    want = "loose" if is_loose_path(path) else "strict"
    wrong = [r for r in rows if r.get("Level") != want]
    if wrong:
        raise ValueError("cannot write %s: %d row(s) at level %s do not belong at the %s path"
                         % (path, len(wrong), ", ".join(sorted({r.get("Level", "") for r in wrong})), want))
    with open(path, "w", newline="") as fh:
        for line in header:
            fh.write("# %s\n" % line if line else "#\n")
        w = csv.DictWriter(fh, fieldnames=PROPOSAL_COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def read_taken(paths: Iterable[str]) -> Tuple[List[str], Dict[str, int]]:
    """(identifiers, {path: count read}) from the `Proposed` column of every proposals file present."""
    names, seen = [], {}
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, newline="") as fh:
            got = [r["Proposed"] for r in csv.DictReader(line for line in fh if not line.startswith("#"))
                   if r.get("Proposed")]
        names += got
        seen[p] = len(got)
    return names, seen


# ---- the CLI ---------------------------------------------------------------------------------------------

def _fmt_holdout(h: Dict[str, int]) -> str:
    return "%d re-derived / %d wrong (%d by Task 7's uncorrected answer)" % (
        h["re-derived"], h["wrong"], h["wrong by Task 7"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="the string-set pass (research/53 rule R3)")
    ap.add_argument("demo_elf")
    ap.add_argument("our_elf")
    ap.add_argument("our_csv")
    ap.add_argument("matches_json", help="Task 7's --out JSON: the anchor set is checked against it")
    ap.add_argument("--out", required=True, help="the strict proposals csv (never applied here)")
    ap.add_argument("--holdout", action="store_true", help="research/45 sec 3's holdout, blocks of 8 and 1")
    ap.add_argument("--loose", action="store_true", help="also write the R0 remainder to <out>_loose.csv")
    ap.add_argument("--taken", action="append", default=None,
                    help="a proposals file whose Proposed names are spent (default: %s)" % ", ".join(TAKEN_FILES))
    args = ap.parse_args(list(argv) if argv is not None else None)

    if is_loose_path(args.out):
        print("NO-DATA: --out %s is a loose path; give the strict path and --loose" % args.out)
        return 2
    missing = [p for p in (args.demo_elf, args.our_elf, args.our_csv, args.matches_json)
               if not os.path.exists(p)]
    if missing:
        for p in missing:
            print("NO-DATA: missing %s" % p)
        return 2

    from tools_py import ghidra_symbol_match as gsm
    try:
        demo_rows, demo_segs = gsm.load_demo(args.demo_elf)
        our_rows, our_segs = gsm.load_ours(args.our_elf, args.our_csv)
    except ValueError as exc:
        print("NO-DATA: %s" % exc)
        return 2
    # Task 7's pairs, re-derived as research/44 command A makes them (--prefix): the JSON carries no
    # demo address, so it is the check, not the source.
    details: Dict = {}
    gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
    anchors = anchors_from_details(details)
    with open(args.matches_json) as fh:
        js = json.load(fh)
    js_pairs = {(p["name"], int(p["addr"], 16)) for p in js.get("pairs", [])}
    if js.get("matched") != len(anchors) or js_pairs != set(details):
        print("NO-DATA: %s says %s pairs; the re-derived Task 7 run has %d (%d differ) -- the anchor set "
              "moved; re-run Task 7 first" % (args.matches_json, js.get("matched"), len(anchors),
                                               len(js_pairs ^ set(details))))
        return 2
    comp = anchor_composition(anchors)
    anchor_note = ("Anchors: %d Task 7 pairs (%s); %d PROVED, the rest prologue-only; %s agrees."
                   % (len(anchors), ", ".join("%s %d" % kv for kv in sorted(comp.items())),
                      len(proved_anchors(anchors)), args.matches_json))
    print(anchor_note)

    demo, ours = am.Side(demo_rows, demo_segs), am.Side(our_rows, our_segs)
    keys = shared_keys(demo, ours)
    taken_files = args.taken if args.taken is not None else list(TAKEN_FILES)
    taken, seen = read_taken(taken_files)
    t7_names = [c_identifier(details_key[0]) for details_key in details]
    csv_names = [n for _s, _e, n in our_rows if not is_placeholder(n)]
    taken_all = taken + t7_names + [c_identifier(n) for n in csv_names]
    print("identifiers spent: %s; Task 7's %d pairs; %d non-placeholder csv names"
          % (", ".join("%s %d" % kv for kv in seen.items()) or "no proposals file found",
             len(t7_names), len(csv_names)))

    strict, loose, census = string_pass(demo, ours, anchors, taken=taken_all, keys=keys)
    print("census: " + ", ".join("%s %d" % kv for kv in census.items()))
    print("strict rows by link order %s; by callees %s"
          % (dict(sorted(collections.Counter(c.order for c in strict).items())),
             dict(sorted(collections.Counter(c.callees for c in strict).items()))))
    print("the twelve largest strict bodies (our address, demo/our size, link order, callees, demo name):")
    for c in sorted(strict, key=lambda c: -c.demo_size)[:12]:
        print("   0x%08x %5d/%5d  %-21s %-8s %s" % (c.our_addr, c.demo_size, c.our_size, c.order,
                                                    c.callees, c.demo_name))

    found = contradictions(demo, ours, anchors)
    print("Task 7 pairs a string key (any kind, image-wide) contradicts: %d line(s)" % len(found))
    for f in found:
        if f["task7_our"] is not None:
            t7 = "Task 7: -> our 0x%08x by %s" % (f["task7_our"], f["task7_how"])
        else:
            t7 = "Task 7: our row held by %s (%s)" % (demo.name.get(f["rival_demo"]), f["rival_how"])
        print("  %s: demo %s 0x%08x -> our 0x%08x (%d/%d B); %s"
              % ("/".join(f["kinds"]), f["demo_name"], f["demo_addr"], f["our_addr"],
                 f["demo_size"], f["our_size"], t7))

    by_name = collections.defaultdict(list)
    for a in demo.starts:
        by_name[demo.name[a]].append(a)
    corrections = {o: by_name[n][0] for o, n in ROW_478_CORRECTION.items() if len(by_name[n]) == 1}
    hold_lines = ["holdout not run in this invocation (--holdout)."]
    if args.holdout:
        hold_lines = []
        for block in (8, 1):
            h = holdout(demo, ours, anchors, folds=3, block=block, corrections=corrections, keys=keys)
            line = ("holdout, 3 folds, blocks of %d, over the %d PROVED pairs, truth = Task 7 with the "
                    "S12-R9 row-478 correction: %s" % (block, len(proved_anchors(anchors)), _fmt_holdout(h)))
            print(line)
            hold_lines.append(line)

    header_common = [anchor_note,
                     "Identifiers spent before this file: %d from %s; the 987's own names; the csv's %d."
                     % (len(taken), ", ".join(seen) or "no proposals file", len(csv_names))] + hold_lines + [
        "Contradictions with Task 7 found by a string key: %d line(s); the holds file "
        "(recomp/socom2_name_holds.csv) is the applier's." % len(found),
        "Census: " + ", ".join("%s %d" % kv for kv in census.items())]
    preamble = ["%s -- Sprint 12 Task 12 proposals. PROPOSALS ONLY:",
                "recomp/socom2_ghidra.csv and recomp/socom2_names.csv are unchanged; applying is Task 3's.",
                "Names come from the SOCOM 1 demo's .symtab. Addresses are OURS (r0001).",
                "docs/research/53-string-correlator.md; tools_py/string_lever.py.", ""]
    try:
        head = [preamble[0] % args.out] + preamble[1:] + [STRING_RULE, ""] + header_common
        write_proposals(args.out, proposal_rows(strict), head)
        print("wrote %s: %d rows (proposals only)" % (args.out, len(strict)))
        if args.loose:
            lp = loose_path(args.out)
            head = [preamble[0] % lp] + preamble[1:] + [LOOSE_RULE, "", STRING_RULE, ""] + header_common
            write_proposals(lp, proposal_rows(loose), head)
            print("wrote %s: %d rows (loose; never applied without a body read)" % (lp, len(loose)))
    except (ValueError, OSError) as exc:
        print("NO-DATA: %s" % exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
