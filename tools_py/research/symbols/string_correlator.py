"""Strings as first-class evidence: a shared-string correlator between the SOCOM 1 demo and r0001.
(Sprint 12 research wave, question 8; docs/research/53-string-correlator.md)

Run from the repo root:  python tools_py/research/symbols/string_correlator.py

Read-only. Inputs: game/demo_scus_972_05/SCUS_972.05, game/disc/socom2_game.elf,
recomp/socom2_ghidra.csv. Task 7's 987 pairs (828 PROVED) are re-derived in-process by
`ghidra_symbol_match.match(..., prefix=True)` -- the same call research/44 command A makes -- because
game/demo_symbol_matches.json does not carry the demo address of a pair; the script checks that the
re-derived set has the JSON's size. Writes nothing. Prints counts, addresses and function NAMES only;
it never prints a string's bytes.

What it prints, section by section (the note's section numbers):

  S1  the string census: NUL-terminated printable strings >= 4 bytes in each image's PT_LOADs
      (occurrences, distinct values, shared byte-for-byte), the strings the code forms the address
      of (`address_matcher.Side.anchors()`'s mechanism), how many functions reference >= 1 string and
      >= 1 shared string, and the strings-per-function histogram on each side.
  S2  the set key -- the set of shared strings a function references -- paired when non-empty and
      unique both ways: pairs, agreement with the 987, pairs beyond the 987, >= 64 B, ratio >= 0.50.
  S3  the weaker/other keys, same columns: the multiset (reference counts, order ignored), the
      ordered sequence, the unique-string key, and the set key combined with the placed-callee set.
      Each at two scopes: `image-wide` (uniqueness over every function) and `unplaced` (over the
      functions Task 7 did not place).
  S4  research/45 sec 3's holdout over the 828 PROVED pairs (3 folds; blocks of 8 and of 1), per key
      kind and scope, and the rule variants with size floors.
  S4b the second signals, which never look at a string: link order against the flanking Task 7
      anchors (research/45 sec 1) and the placed callees, on the new pairs, on the 987 (leave-one-out)
      and on a random re-pairing; recomp/socom2.toml's hand names on the new pairs; the pairs where a
      string key contradicts Task 7, with both hypotheses' callers and nearest anchors; the rules
      R0-R3 with their real-run yield and their holdout.
  S5  what the new pairs are: engine vs SDK (`ghidra_symbol_match.is_engine`), readable class
      (a copy of `readable()` from readable_names.py), and the twelve largest bodies.
  S6  research/45's 501 'no body evidence' positional candidates: how many a string key confirms
      or contradicts, string-set agreement at the positional pairing, and research/45's positional
      holdout re-run with 'the string sets agree' as the body evidence.
"""
import bisect
import collections
import os
import re
import sys
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py import address_matcher as am  # noqa: E402
from tools_py import ghidra_symbol_match as gsm  # noqa: E402
from tools_py import symbol_levers as sl  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
OURS_ELF = "game/disc/socom2_game.elf"
OURS_CSV = "recomp/socom2_ghidra.csv"
MATCHES_JSON = "game/demo_symbol_matches.json"
TOML = "recomp/socom2.toml"
MIN_BODY = sl.MIN_BODY          # 64, note 44 hurdle 2
SIZE_RATIO = sl.SIZE_RATIO      # 0.50, note 45 sec 2
PRINTABLE = frozenset(list(range(32, 127)) + [9, 10, 13])   # address_matcher.Image.cstring's set


# ---- a copy of readable() (tools_py/research/symbols/readable_names.py), so this file imports no
# ---- sibling research script; the class is the part before the last '_' when the name is mangled.
OPERATORS = {
    "__ct": "ctor", "__dt": "dtor", "__as": "op_assign",
    "__pl": "op_add", "__mi": "op_sub", "__ml": "op_mul", "__dv": "op_div", "__md": "op_mod",
    "__eq": "op_eq", "__ne": "op_ne", "__lt": "op_lt", "__gt": "op_gt", "__le": "op_le", "__ge": "op_ge",
    "__vc": "op_index", "__cl": "op_call", "__nw": "op_new", "__dl": "op_delete",
    "__nwa": "op_new_array", "__dla": "op_delete_array",
    "__aa": "op_and", "__oo": "op_or", "__er": "op_xor", "__ad": "op_bitand", "__or": "op_bitor",
    "__ls": "op_lsh", "__rs": "op_rsh", "__nt": "op_not", "__ng": "op_neg", "__co": "op_compl",
    "__pp": "op_inc", "__mm": "op_dec", "__rf": "op_deref", "__rm": "op_arrow",
    "__apl": "op_addassign", "__ami": "op_subassign", "__amu": "op_mulassign", "__adv": "op_divassign",
}
_SPLIT = re.compile(r"^(.*?)__(?:Q\d|\d+)")
_SAFE = re.compile(r"[^A-Za-z0-9_]")


def readable(mangled: str) -> str:
    m = _SPLIT.match(mangled)
    if not m:
        return _SAFE.sub("_", mangled)
    fn = m.group(1)
    rest = mangled[len(fn) + 2:]
    fn = OPERATORS.get(fn, fn)
    fn = re.sub(r"<.*>", "", fn)
    classes = []
    q = re.match(r"Q(\d)", rest)
    if q:
        pos = q.end()
        for _ in range(int(q.group(1))):
            n = re.match(r"(\d+)", rest[pos:])
            if not n:
                break
            length = int(n.group(1))
            pos += n.end()
            classes.append(rest[pos:pos + length])
            pos += length
    else:
        n = re.match(r"(\d+)", rest)
        if n:
            length = int(n.group(1))
            classes.append(rest[n.end():n.end() + length])
    return _SAFE.sub("_", "_".join(classes + [fn]) if classes else fn)


def readable_class(mangled: str) -> str:
    """The class part of readable(), or '(free)' for a name with no class marker."""
    if not re.search(r"__(Q\d|\d)", mangled):
        return "(free)"
    r = readable(mangled)
    return r.rsplit("_", 1)[0] if "_" in r else "(free)"


# ---- S1: the census ---------------------------------------------------------------------------

def string_census(segments) -> Dict[int, bytes]:
    """{address: bytes} for every maximal printable run of >= 4 bytes followed by a NUL, per PT_LOAD."""
    out: Dict[int, bytes] = {}
    for vaddr, data in segments:
        i, n = 0, len(data)
        while i < n:
            if data[i] in PRINTABLE:
                j = i
                while j < n and data[j] in PRINTABLE:
                    j += 1
                if j < n and data[j] == 0 and j - i >= 4:
                    out[vaddr + i] = bytes(data[i:j])
                i = j + 1
            else:
                i += 1
    return out


def refs_of(side: am.Side, start: int) -> List[bytes]:
    """The strings a body forms the address of, in instruction order, repeats kept.

    Side.anchors()'s own mechanism (`formed_addresses` + `Image.cstring`); `anchors()` is the
    sorted distinct set of this list, which main() asserts for every function.
    """
    out = []
    for addr in am.formed_addresses(side.body.get(start, b"")):
        text = side.image.cstring(addr)
        if text:
            out.append(text)
    return out


def histogram(counts: Sequence[int]) -> str:
    bins = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 7), (8, 15), (16, 31), (32, 10 ** 9)]
    parts = []
    for lo, hi in bins:
        k = sum(1 for c in counts if lo <= c <= hi)
        label = str(lo) if lo == hi else ("%d+" % lo if hi >= 10 ** 9 else "%d-%d" % (lo, hi))
        parts.append("%s:%d" % (label, k))
    return " ".join(parts)


# ---- the keys ----------------------------------------------------------------------------------

KINDS = ("set", "multiset", "sequence", "unique-string", "set+callees")


def build_keys(side: am.Side, refs: Dict[int, List[bytes]], shared: set) -> Dict[str, Dict[int, object]]:
    """{kind: {start: key}} for the string-only kinds; an empty key is left out (never pairs)."""
    out: Dict[str, Dict[int, object]] = {"set": {}, "multiset": {}, "sequence": {}}
    for start, lst in refs.items():
        sh = [s for s in lst if s in shared]
        if not sh:
            continue
        out["set"][start] = frozenset(sh)
        out["multiset"][start] = tuple(sorted(collections.Counter(sh).items()))
        out["sequence"][start] = tuple(sh)
    return out


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


def pair_unique_string(sets_d, sets_o, pool_d, pool_o) -> Tuple[Dict[int, int], int]:
    """({demo: ours}, conflicts): a shared string referenced by exactly one pool function on each
    side pairs those two; a function whose unique strings point at two partners pairs with neither."""
    users_d: Dict[bytes, List[int]] = collections.defaultdict(list)
    users_o: Dict[bytes, List[int]] = collections.defaultdict(list)
    for a, st in sets_d.items():
        if a in pool_d:
            for s in st:
                users_d[s].append(a)
    for a, st in sets_o.items():
        if a in pool_o:
            for s in st:
                users_o[s].append(a)
    part_d: Dict[int, set] = collections.defaultdict(set)
    part_o: Dict[int, set] = collections.defaultdict(set)
    for s, ud in users_d.items():
        uo = users_o.get(s, ())
        if len(ud) == 1 and len(uo) == 1:
            part_d[ud[0]].add(uo[0])
            part_o[uo[0]].add(ud[0])
    out = {}
    conflicts = 0
    for d, ps in part_d.items():
        if len(ps) == 1:
            o = next(iter(ps))
            if part_o[o] == {d}:
                out[d] = o
                continue
        conflicts += 1
    return out, conflicts


def callee_keys(demo: am.Side, ours: am.Side, sets_d, sets_o, amap: Dict[int, int]):
    """(set, placed-callee set) keys; demo callees are carried to our addresses through `amap`."""
    placed_ours = set(amap.values())
    kd = {a: (st, frozenset(amap[t] for t in demo.calls[a] if t in amap)) for a, st in sets_d.items()}
    ko = {a: (st, frozenset(t for t in ours.calls[a] if t in placed_ours)) for a, st in sets_o.items()}
    return kd, ko


def derive(kind: str, demo, ours, keys_d, keys_o, pool_d, pool_o, amap) -> Dict[int, int]:
    if kind == "unique-string":
        return pair_unique_string(keys_d["set"], keys_o["set"], pool_d, pool_o)[0]
    if kind == "set+callees":
        kd, ko = callee_keys(demo, ours, keys_d["set"], keys_o["set"], amap)
        return pair_unique(kd, ko, pool_d, pool_o)
    return pair_unique(keys_d[kind], keys_o[kind], pool_d, pool_o)


def size_ok(demo, ours, d, o, ratio: bool) -> bool:
    ds, os_ = demo.size.get(d, 0), ours.size.get(o, 0)
    if ds < MIN_BODY or os_ < MIN_BODY:
        return False
    return (min(ds, os_) / max(ds, os_) >= SIZE_RATIO) if ratio else True


# ---- S4: research/45 sec 3's holdout, applied to a key ---------------------------------------

def holdout(kind, scope, demo, ours, keys_d, keys_o, rows, proved, folds=3, block=8):
    """{filter: (re-derived, wrong)} summed over the folds.

    Same fold construction as `symbol_levers.holdout`: the 987 pairs sorted by our address; only the
    828 PROVED are eligible to be held out; runs of `block` consecutive eligible pairs go to fold
    (j // block) % folds. The kept pairs are the anchors (they feed the callee map and, at scope
    `unplaced`, leave the pool). A derived pair is judged when either side is held out; it is wrong
    when it does not reproduce Task 7's answer.
    """
    pp = sorted((o, d) for d, o, _h in rows)
    truth_d = {d: o for o, d in pp}
    eligible = [i for i, (_o, d) in enumerate(pp) if d in proved]
    all_d = {d for _o, d in pp}
    all_o = {o for o, _d in pp}
    out = {"any size": [0, 0], ">=64": [0, 0], ">=64+ratio": [0, 0]}
    for phase in range(folds):
        hold = {eligible[j] for j in range(len(eligible)) if (j // block) % folds == phase}
        held_d = {pp[i][1] for i in hold}
        held_o = {pp[i][0] for i in hold}
        amap = {d: o for i, (o, d) in enumerate(pp) if i not in hold}
        if scope == "unplaced":
            pool_d = demo.starts - (all_d - held_d)
            pool_o = ours.starts - (all_o - held_o)
        else:
            pool_d, pool_o = demo.starts, ours.starts
        for d, o in derive(kind, demo, ours, keys_d, keys_o, pool_d, pool_o, amap).items():
            if d not in held_d and o not in held_o:
                continue
            wrong = truth_d.get(d) != o
            for label, ok in (("any size", True), (">=64", size_ok(demo, ours, d, o, False)),
                              (">=64+ratio", size_ok(demo, ours, d, o, True))):
                if ok:
                    out[label][0] += 1
                    out[label][1] += int(wrong)
    return {k: tuple(v) for k, v in out.items()}


def positional_string_holdout(demo, ours, sets_d, sets_o, rows, proved, folds=3, block=8):
    """research/45's positional holdout (anchor gaps from the kept pairs), with the held-out rows
    that have NO body evidence (untiered) bucketed by whether their shared-string sets agree."""
    regions = [(v, v + len(d)) for v, d in ours.image.segments]
    our_starts, demo_starts = sorted(ours.starts), sorted(demo.starts)
    pp = sorted((o, d) for d, o, _h in rows)
    truth = dict(pp)
    all_o, all_d = {o for o, _d in pp}, {d for _o, d in pp}
    eligible = [i for i, (_o, d) in enumerate(pp) if d in proved]
    out = collections.Counter()
    for phase in range(folds):
        hold = {eligible[j] for j in range(len(eligible)) if (j // block) % folds == phase}
        held = [pp[i] for i in sorted(hold)]
        keep = [(d, o, "") for i, (o, d) in enumerate(pp) if i not in hold]
        held_o = {o for o, _d in held}
        gaps = sl.anchor_gaps(keep, our_starts, demo_starts, regions,
                              all_o - held_o, all_d - {d for _o, d in held})
        for gap in gaps:
            for o, d in gap:
                if o not in held_o:
                    continue
                tier = sl._tier(demo, d, ours, o)
                a, b = sets_d.get(d), sets_o.get(o)
                if a and b:
                    agree = "strings equal" if a == b else "strings differ"
                elif a or b:
                    agree = "strings on one side"
                else:
                    agree = "no strings"
                bucket = ("tiered" if tier else "untiered") + ", " + agree
                wrong = truth[o] != d
                out[(bucket, "n")] += 1
                out[(bucket, "wrong")] += int(wrong)
                if agree == "strings equal" and size_ok(demo, ours, d, o, True):
                    out[(bucket + ", >=64+ratio", "n")] += 1
                    out[(bucket + ", >=64+ratio", "wrong")] += int(wrong)
    return out


# ---- second signals: link order and placed callees ---------------------------------------------

def signals(demo: am.Side, ours: am.Side, amap: Dict[int, int]):
    """(order, callees): two checks of a pair (d, o) that do not look at strings at all.

    order(d, o[, skip]) -- research/45 sec 1's link order: in o's PT_LOAD, take the nearest anchors
      below and above o; 'between' when d lies between their demo addresses, 'outside' when it does
      not, 'anchors-out-of-order' when the two anchors themselves disagree, 'edge' at a region end.
      `skip` leaves one anchor out (the leave-one-out baseline over the anchors themselves).
    callees(d, o) -- the placed callees (Q7's kind): demo callees carried through `amap` against our
      callees that are anchors; 'overlap', 'disjoint', 'one side' or 'none'.
    """
    regions = [(v, v + len(b)) for v, b in ours.image.segments]
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


RULES = (
    ("R0 key, >=64 B, ratio >= 0.50", lambda o_, c_: True),
    ("R1 R0 + placed callees not disjoint", lambda o_, c_: c_ != "disjoint"),
    ("R2 R1 + link order not outside", lambda o_, c_: c_ != "disjoint" and o_ != "outside"),
    ("R3 R2 + a positive second signal", lambda o_, c_: c_ != "disjoint" and o_ != "outside"
     and (o_ == "between" or c_ == "overlap")),
)


def rule_pairs(kind, demo, ours, keys_d, keys_o, pool_d, pool_o, amap, test):
    """The pairs a key makes in the pool that clear the size floors and a RULES test."""
    order, callees = signals(demo, ours, amap)
    got = derive(kind, demo, ours, keys_d, keys_o, pool_d, pool_o, amap)
    return {d: o for d, o in got.items()
            if size_ok(demo, ours, d, o, True) and test(order(d, o), callees(d, o))}


def rule_holdout(kind, test, demo, ours, keys_d, keys_o, rows, proved, disputed, folds=3, block=8):
    """(re-derived, wrong, wrong other than the disputed pairs) -- `holdout` at scope `unplaced`, for
    a RULES test whose second signals are computed from the KEPT anchors only."""
    pp = sorted((o, d) for d, o, _h in rows)
    truth_d = {d: o for o, d in pp}
    eligible = [i for i, (_o, d) in enumerate(pp) if d in proved]
    all_d, all_o = {d for _o, d in pp}, {o for o, _d in pp}
    n = wrong = wrong_x = 0
    for phase in range(folds):
        hold = {eligible[j] for j in range(len(eligible)) if (j // block) % folds == phase}
        held_d = {pp[i][1] for i in hold}
        held_o = {pp[i][0] for i in hold}
        amap = {d: o for i, (o, d) in enumerate(pp) if i not in hold}
        pool_d = demo.starts - (all_d - held_d)
        pool_o = ours.starts - (all_o - held_o)
        for d, o in rule_pairs(kind, demo, ours, keys_d, keys_o, pool_d, pool_o, amap, test).items():
            if d not in held_d and o not in held_o:
                continue
            n += 1
            if truth_d.get(d) != o:
                wrong += 1
                wrong_x += int(d not in disputed and o not in disputed.values())
    return n, wrong, wrong_x


# ---- main ---------------------------------------------------------------------------------------

def main() -> int:
    for p in (DEMO, OURS_ELF, OURS_CSV):
        if not os.path.exists(p):
            print("NO-DATA: missing", p)
            return 2
    demo_rows, demo_segs = gsm.load_demo(DEMO)
    our_rows, our_segs = gsm.load_ours(OURS_ELF, OURS_CSV)
    details: Dict = {}
    gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
    rows = sl.anchors_from_details(details)
    proved = sl.proved_anchors(rows)
    print("Task 7 re-derived (research/44 command A's match, --prefix): %d pairs, %d PROVED"
          % (len(rows), len(proved)))
    if os.path.exists(MATCHES_JSON):
        import json
        with open(MATCHES_JSON) as fh:
            print("  %s says matched %d" % (MATCHES_JSON, json.load(fh)["matched"]))
    amap = {d: o for d, o, _h in rows}
    how_of = {d: h for d, _o, h in rows}
    anch_d, anch_o = set(amap), set(amap.values())

    demo = am.Side(demo_rows, demo_segs)
    ours = am.Side(our_rows, our_segs)
    # Only functions with bytes take part in the keys (51 of our rows have none; research/44 sec 1).
    # Side.starts itself is left whole: research/45's gaps count every row, and S6 reproduces them.
    live_d = {a for a in demo.starts if demo.body.get(a)}
    live_o = {a for a in ours.starts if ours.body.get(a)}

    # ---- S1
    print("\n== S1 the string census ==")
    cen_d, cen_o = string_census(demo_segs), string_census(our_segs)
    dist_d, dist_o = set(cen_d.values()), set(cen_o.values())
    both = dist_d & dist_o
    print("NUL-terminated printable strings >= 4 B in the PT_LOADs: demo %d occurrences / %d distinct; "
          "ours %d / %d; shared byte-for-byte (distinct) %d"
          % (len(cen_d), len(dist_d), len(cen_o), len(dist_o), len(both)))
    print("  of which >= 128 B (Image.cstring's reach is 127): demo %d distinct, ours %d distinct, shared %d"
          % (sum(1 for s in dist_d if len(s) >= 128), sum(1 for s in dist_o if len(s) >= 128),
             sum(1 for s in both if len(s) >= 128)))
    refs_d = {a: refs_of(demo, a) for a in live_d}
    refs_o = {a: refs_of(ours, a) for a in live_o}
    mismatch = sum(1 for a in live_d if tuple(sorted(set(refs_d[a]))) != demo.anchors(a))
    mismatch += sum(1 for a in live_o if tuple(sorted(set(refs_o[a]))) != ours.anchors(a))
    print("refs_of() agrees with Side.anchors() on every function: %s (%d disagree)"
          % ("yes" if not mismatch else "NO", mismatch))
    ref_d = set(s for v in refs_d.values() for s in v)
    ref_o = set(s for v in refs_o.values() for s in v)
    shared = ref_d & ref_o
    print("strings the code forms the address of (distinct): demo %d, ours %d; referenced on BOTH sides "
          "(the key alphabet) %d; of those also in the census-shared set %d"
          % (len(ref_d), len(ref_o), len(shared), len(shared & both)))
    n_any_d = sum(1 for v in refs_d.values() if v)
    n_any_o = sum(1 for v in refs_o.values() if v)
    n_sh_d = sum(1 for v in refs_d.values() if any(s in shared for s in v))
    n_sh_o = sum(1 for v in refs_o.values() if any(s in shared for s in v))
    print("functions referencing >= 1 string: demo %d of %d, ours %d of %d; >= 1 SHARED string: demo %d, ours %d"
          % (n_any_d, len(live_d), n_any_o, len(live_o), n_sh_d, n_sh_o))
    print("distinct strings per function, demo: " + histogram([len(set(v)) for v in refs_d.values()]))
    print("distinct strings per function, ours: " + histogram([len(set(v)) for v in refs_o.values()]))
    print("distinct SHARED strings per function, demo: "
          + histogram([len(set(s for s in v if s in shared)) for v in refs_d.values()]))
    print("distinct SHARED strings per function, ours: "
          + histogram([len(set(s for s in v if s in shared)) for v in refs_o.values()]))
    users_d = collections.Counter(s for v in refs_d.values() for s in set(v) if s in shared)
    users_o = collections.Counter(s for v in refs_o.values() for s in set(v) if s in shared)
    print("shared strings referenced by exactly one function on each side: %d of %d"
          % (sum(1 for s in shared if users_d[s] == 1 and users_o[s] == 1), len(shared)))
    anch_with = sum(1 for d, o in amap.items() if refs_d.get(d) and refs_o.get(o))
    anch_eq = sum(1 for d, o in amap.items()
                  if refs_d.get(d) and set(refs_d[d]) & shared
                  and frozenset(s for s in refs_d[d] if s in shared) == frozenset(s for s in refs_o.get(o, []) if s in shared))
    print("of the %d Task 7 pairs: both sides reference a string %d; shared-string sets equal and non-empty %d"
          % (len(amap), anch_with, anch_eq))

    keys_d = build_keys(demo, refs_d, shared)
    keys_o = build_keys(ours, refs_o, shared)

    # ---- S2 / S3
    print("\n== S2/S3 the keys on the real run (anchors = the %d Task 7 pairs) ==" % len(amap))
    print("columns: pairs | touch a Task-7 pair: agree / contradict | beyond the 987 | of those >=64 B both "
          "| and ratio >= 0.50 | of those our row still FUN_")
    results: Dict[Tuple[str, str], Dict[int, int]] = {}
    for scope in ("image-wide", "unplaced"):
        if scope == "unplaced":
            pool_d, pool_o = live_d - anch_d, live_o - anch_o
        else:
            pool_d, pool_o = live_d, live_o
        for kind in KINDS:
            got = derive(kind, demo, ours, keys_d, keys_o, pool_d, pool_o, amap)
            results[(kind, scope)] = got
            agree = sum(1 for d, o in got.items() if amap.get(d) == o)
            contra = sum(1 for d, o in got.items() if (d in anch_d or o in anch_o) and amap.get(d) != o)
            beyond = {d: o for d, o in got.items() if d not in anch_d and o not in anch_o}
            b64 = {d: o for d, o in beyond.items() if size_ok(demo, ours, d, o, False)}
            br = {d: o for d, o in beyond.items() if size_ok(demo, ours, d, o, True)}
            fun = sum(1 for o in br.values() if gsm.is_anonymous(ours.name.get(o, "")))
            extra = ""
            if kind == "unique-string":
                extra = "  (conflicts refused %d)" % pair_unique_string(keys_d["set"], keys_o["set"],
                                                                        pool_d, pool_o)[1]
            print("  %-13s %-10s %5d | %4d / %3d | %4d | %4d | %4d | %4d%s"
                  % (kind, scope, len(got), agree, contra, len(beyond), len(b64), len(br), fun, extra))
    print("  (for scale: demo functions with a non-empty shared-string set %d, ours %d; distinct set keys "
          "demo %d, ours %d)" % (len(keys_d["set"]), len(keys_o["set"]),
                                 len(set(keys_d["set"].values())), len(set(keys_o["set"].values()))))
    # overlap between kinds, beyond the 987, >=64+ratio
    def strong(kind, scope):
        return {(d, o) for d, o in results[(kind, scope)].items()
                if d not in anch_d and o not in anch_o and size_ok(demo, ours, d, o, True)}
    u = set()
    for kind in KINDS:
        for scope in ("image-wide", "unplaced"):
            u |= strong(kind, scope)
    print("  union over every kind and scope, beyond the 987, >=64+ratio: %d pairs" % len(u))
    conflict_d = collections.Counter(d for d, _o in u)
    conflict_o = collections.Counter(o for _d, o in u)
    print("  of which a demo function paired two ways %d, our row paired two ways %d"
          % (sum(1 for c in conflict_d.values() if c > 1), sum(1 for c in conflict_o.values() if c > 1)))
    print("  set/image-wide within set/unplaced: %d of %d"
          % (len(strong("set", "image-wide") & strong("set", "unplaced")), len(strong("set", "image-wide"))))

    # ---- S4
    print("\n== S4 the holdout over the %d PROVED pairs (3 folds) ==" % len(proved))
    print("cells: re-derived / wrong, for: any size | >=64 B both | >=64 B and ratio >= 0.50")
    for block in (8, 1):
        print(" blocks of %d:" % block)
        for scope in ("image-wide", "unplaced"):
            for kind in KINDS:
                h = holdout(kind, scope, demo, ours, keys_d, keys_o, rows, proved, block=block)
                print("  %-13s %-10s %4d / %2d | %4d / %2d | %4d / %2d"
                      % (kind, scope, *h["any size"], *h[">=64"], *h[">=64+ratio"]))


    # ---- S4b: second signals and the rules
    print("\n== S4b second signals on the pairs beyond the 987 (>=64 B, ratio >= 0.50) ==")
    order, callees = signals(demo, ours, amap)
    base = collections.Counter(order(d, o, skip=(o, d)) for d, o in amap.items())
    print("baseline, the 987 Task 7 pairs leave-one-out: link order %s" % dict(sorted(base.items())))
    for kind, scope in (("set", "unplaced"), ("sequence", "unplaced"), ("unique-string", "unplaced"),
                        ("set+callees", "unplaced")):
        ps = strong(kind, scope)
        oc = collections.Counter(order(d, o) for d, o in ps)
        cc = collections.Counter(callees(d, o) for d, o in ps)
        print("%s/%s: %d pairs; link order %s; placed callees %s"
              % (kind, scope, len(ps), dict(sorted(oc.items())), dict(sorted(cc.items()))))
        if kind == "set":
            import random
            rng = random.Random(1)
            ds, os_ = [d for d, _o in ps], [o for _d, o in ps]
            shuf = collections.Counter()
            for _ in range(20):
                rng.shuffle(os_)
                shuf.update(order(d, o) for d, o in zip(ds, os_))
            print("  the same %d demo and our functions paired at random (20 shuffles, mean): %s"
                  % (len(ps), {k: round(v / 20, 1) for k, v in sorted(shuf.items())}))
    tn = {}
    if os.path.exists(TOML):
        with open(TOML) as fh:
            tn = {int(a, 16): n for n, a in re.findall(r'"([^"@]+)@0x([0-9A-Fa-f]+)"', fh.read())}
    for kind, scope in (("set", "unplaced"), ("set", "image-wide")):
        ps = strong(kind, scope)
        on = [(d, o) for d, o in ps if o in tn]
        print("recomp/socom2.toml's name@addr (%d entries) on the %s/%s pairs: %d named there, %d the same name"
              % (len(tn), kind, scope, len(on), sum(1 for d, o in on if tn[o] == demo.name[d])))
    on = [(d, o) for d, o in amap.items() if o in tn]
    print("  (the same check on the 987: %d named there, %d the same name)"
          % (len(on), sum(1 for d, o in on if tn[o] == demo.name[d])))

    # the pairs where a string key contradicts Task 7
    disputed = {}
    for kind in KINDS:
        for d, o in results[(kind, "image-wide")].items():
            if (d in anch_d or o in anch_o) and amap.get(d) != o:
                disputed[d] = o
    inv_amap = {o: d for d, o in amap.items()}
    print("\npairs where a string key (any kind, image-wide) contradicts Task 7: %d" % len(disputed))
    for d, o in sorted(disputed.items()):
        t7 = amap.get(d)
        rival = inv_amap.get(o)
        print("  string key: demo %s 0x%08x -> our 0x%08x (%d/%d B); Task 7: %s"
              % (demo.name[d], d, o, demo.size[d], ours.size[o],
                 ("-> our 0x%08x by %s" % (t7, how_of[d])) if t7 is not None else
                 ("our row held by %s (%s)" % (demo.name.get(rival), how_of.get(rival)))))
        if t7 is not None:
            # both hypotheses, side by side: what calls each function, and the nearest Task 7 anchor
            # below it (ours by our address, the demo's by demo address), the anchor under dispute
            # itself left out.
            others = sorted({x for k in KINDS for x, y in results[(k, "image-wide")].items() if y == t7})
            anc_o = sorted((oo, dd) for dd, oo in amap.items() if dd != d)
            anc_d = sorted((dd, oo) for dd, oo in amap.items() if dd != d)

            def below(lst, addr):
                i = bisect.bisect_left(lst, (addr, -1))
                return lst[i - 1] if i else None
            for dd in [d] + others:
                a = below(anc_d, dd)
                print("    demo %-24s 0x%08x: demo callers %d; nearest anchor below it in the demo: %s"
                      % (demo.name[dd], dd, sum(1 for z in demo.starts if dd in demo.calls.get(z, ())),
                         demo.name[a[0]] if a else None))
            for oo in (t7, o):
                a = below(anc_o, oo)
                print("    our  0x%08x (%d B): our callers %d; nearest anchor below it in ours: 0x%08x = %s"
                      % (oo, ours.size[oo], sum(1 for z in ours.starts if oo in ours.calls.get(z, ())),
                         a[0], demo.name[a[1]]))
            print("    Task 7 says 0x%08x = %s; the string keys say 0x%08x = %s and 0x%08x = %s"
                  % (t7, demo.name[d], o, demo.name[d], t7,
                     ", ".join(demo.name[x] for x in others) or "(nothing)"))

    print("\nthe rules (key at scope unplaced; the holdout's second signals use the kept anchors only):")
    print("cells: real-run pairs beyond the 987 | holdout blocks of 8: re-derived / wrong / wrong but "
          "the disputed | blocks of 1: same")
    for kind in ("set", "sequence", "unique-string", "set+callees"):
        for label, test in RULES:
            real = rule_pairs(kind, demo, ours, keys_d, keys_o, live_d - anch_d, live_o - anch_o, amap, test)
            h8 = rule_holdout(kind, test, demo, ours, keys_d, keys_o, rows, proved, disputed, block=8)
            h1 = rule_holdout(kind, test, demo, ours, keys_d, keys_o, rows, proved, disputed, block=1)
            print("  %-13s %-38s %4d | %3d / %d / %d | %3d / %d / %d" % (kind, label, len(real), *h8, *h1))

    # ---- S5
    print("\n== S5 what the new pairs are ==")
    rec_label, rec_test = RULES[3]
    rec = rule_pairs("set", demo, ours, keys_d, keys_o, live_d - anch_d, live_o - anch_o, amap, rec_test)
    views = (("set/unplaced R0", {(d, o) for d, o in strong("set", "unplaced")}),
             ("set/unplaced R3", set(rec.items())),
             ("unique-string/unplaced R0", strong("unique-string", "unplaced")),
             ("set+callees/unplaced R0", strong("set+callees", "unplaced")))
    names987 = collections.Counter(demo.name[d] for d in amap)
    for label, ps in views:
        names = [demo.name[d] for d, _o in ps]
        eng = sum(1 for n in names if gsm.is_engine(n))
        classes = collections.Counter(readable_class(n) for n in names)
        print("%s: %d pairs, is_engine %d, not %d; readable classes %d; largest %s"
              % (label, len(ps), eng, len(ps) - eng, len(classes), classes.most_common(12)))
    ps = sorted(rec.items(), key=lambda p: -demo.size[p[0]])
    regions = [(v, v + len(b)) for v, b in ours.image.segments]
    per = collections.Counter(next(("0x%x-0x%x" % r for r in regions if r[0] <= o < r[1]), "?") for _d, o in ps)
    print("R3 pairs per our PT_LOAD: %s" % dict(sorted(per.items())))
    dup_in = collections.Counter(demo.name[d] for d, _o in ps)
    print("R3 demo names also on a Task 7 pair: %d; names on two R3 pairs: %d; identifiers colliding "
          "after c_identifier with the 987 or within R3: %d"
          % (sum(1 for n in dup_in if n in names987), sum(1 for c in dup_in.values() if c > 1),
             len(ps) - len({gsm.c_identifier(demo.name[d]) for d, _o in ps}
                          - {gsm.c_identifier(n) for n in names987})))
    print("the twelve largest R3 bodies (our address, demo/our size, readable, is_engine, link order, callees):")
    for d, o in ps[:12]:
        print("   0x%08x %5d/%5d  %-34s %-6s %-21s %s"
              % (o, demo.size[d], ours.size[o], readable(demo.name[d]),
                 "engine" if gsm.is_engine(demo.name[d]) else "not", order(d, o), callees(d, o)))

    # ---- S6
    print("\n== S6 research/45's positional candidates with no body evidence ==")
    regions = [(v, v + len(d)) for v, d in ours.image.segments]
    gaps = sl.anchor_gaps(rows, sorted(ours.starts), sorted(demo.starts), regions, anch_o, anch_d)
    cands = [(o, d) for g in gaps for o, d in g]
    nobody = [(o, d) for o, d in cands if sl._tier(demo, d, ours, o) is None]
    print("gaps %d, candidates %d, no body evidence %d (research/45 sec 5: 156 / 528 / 501)"
          % (len(gaps), len(cands), len(nobody)))
    sd, so = keys_d["set"], keys_o["set"]
    agree = collections.Counter()
    for o, d in nobody:
        a, b = sd.get(d), so.get(o)
        if a and b:
            agree["equal" if a == b else "differ"] += 1
        elif a or b:
            agree["one side only"] += 1
        else:
            agree["neither side"] += 1
    print("shared-string sets at the positional pairing: equal %d, differ %d, one side only %d, neither %d"
          % (agree["equal"], agree["differ"], agree["one side only"], agree["neither side"]))
    eq_strong = [(o, d) for o, d in nobody if sd.get(d) and sd.get(d) == so.get(o)
                 and size_ok(demo, ours, d, o, True)]
    print("  equal and >=64 B and ratio >= 0.50: %d" % len(eq_strong))
    got_set = results[("set", "unplaced")]
    print("  of those: paired the same way by the set key (unplaced) %d, and by R3 %d; equal but the set "
          "is not unique (position alone picks the partner) %d"
          % (sum(1 for o, d in eq_strong if got_set.get(d) == o), sum(1 for o, d in eq_strong if rec.get(d) == o),
             sum(1 for o, d in eq_strong if d not in got_set)))
    for kind in KINDS:
        for scope in ("image-wide", "unplaced"):
            got = results[(kind, scope)]
            inv = {o: d for d, o in got.items()}
            conf = sum(1 for o, d in nobody if got.get(d) == o)
            contra = sum(1 for o, d in nobody if (d in got and got[d] != o) or (o in inv and inv[o] != d))
            print("  %-13s %-10s confirms %3d, contradicts %3d" % (kind, scope, conf, contra))
            if (kind, scope) == ("set", "unplaced"):
                for o, d in nobody:
                    if (d in got and got[d] != o) or (o in inv and inv[o] != d):
                        alt_o, alt_d = got.get(d), inv.get(o)
                        in_rec = (alt_o is not None and rec.get(d) == alt_o) or \
                                 (alt_d is not None and rec.get(alt_d) == o)
                        print("     positional 0x%08x <- %s (%d/%d B); string key%s: %s%s"
                              % (o, demo.name[d], demo.size[d], ours.size[o],
                                 " (in R3)" if in_rec else " (not in R3)",
                                 ("demo side -> our 0x%08x (%d B, link order %s) " % (alt_o, ours.size[alt_o], order(d, alt_o)))
                                 if alt_o is not None else "",
                                 ("our side <- %s (%d B, link order %s)" % (demo.name[alt_d], demo.size[alt_d], order(alt_d, o)))
                                 if alt_d is not None else ""))
    for block in (8, 1):
        c = positional_string_holdout(demo, ours, sd, so, rows, proved, block=block)
        print(" positional holdout, blocks of %d (re-derived / wrong):" % block)
        for bucket in sorted({k for k, _t in c}):
            print("   %-50s %4d / %2d" % (bucket, c[(bucket, "n")], c[(bucket, "wrong")]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
