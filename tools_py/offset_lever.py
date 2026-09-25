"""Sprint 12 Task 13: the `offset-multiset` lever, and `prefix+offsets` (research/54, S12-R12).

Task 7 (`tools_py/ghidra_symbol_match.py`) pairs a demo function with one of our rows when the two bodies
are the same stream of instructions up to masked addresses. A routine edited between SOCOM 1 and SOCOM II
fails that test the moment one instruction is inserted, although it still touches the same fields of the
same objects. This lever keys a body on exactly that: K1, the multiset of (primary opcode, signed 16-bit
displacement) over its loads and stores, with the order, the registers and every non-memory instruction
thrown away. Four kinds of access are dropped first, because their displacement says nothing about the
routine: `$sp`-based (the frame), `$gp`-based and lui-formed (half of a global's address, which moves with
every link -- `address_matcher.mask_address_operands`' rule, reused here), and `$zero`-based (absolute
low addresses; in our image they are mostly data inside rows Ghidra calls functions).

    python -m tools_py.offset_lever game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf \\
        recomp/socom2_ghidra.csv game/demo_symbol_matches.json \\
        --out game/demo_symbol_renames_offsets.csv --prefix-out game/demo_symbol_renames_prefix_offsets.csv

Two files, both PROPOSALS ONLY (git-ignored; `tools_py/apply_names.py` is what applies, and it is also what
joins the levers' files under S12-R18's cross-lever rule -- this module only writes):

  * `--out`: research/54 section 6's rule R7 (`OFFSET_RULE`), pass `offset-multiset`, score 0.75. A row
    whose link order is `outside` its flanking Task 7 anchors goes to `<out>_loose.csv` instead: link order
    is the only measurement of this key's false pairs (the holdout cannot see them -- `HOLDOUT_NOTE`).
  * `--prefix-out`: Task 7's prologue-only pairs (`prefix`, `prefix+size`) whose K1 key is also unique both
    ways and equal -- two independent keys (`PREFIX_OFFSETS_RULE`), pass `prefix+offsets`, score 0.80.

No bytes are written: names, addresses, sizes and counts only.
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
from tools_py.ghidra_symbol_match import PREFIX_WORDS, c_identifier
from tools_py.name_provenance import is_placeholder
from tools_py.symbol_levers import MIN_BODY, SIZE_RATIO

PASS = "offset-multiset"
PREFIX_PASS = "prefix+offsets"
SCORE = 0.75                      # below `positional` (0.80), whose own holdout is informative (research/54 §6)
PREFIX_SCORE = 0.80               # two independent keys, each unique both ways (S12-R12)
MIN_ACCESSES = 3                  # research/54 §2
STRONG_ACCESSES = 11              # research/54 §3a: est. false 0 from 11 accesses up
NEAR = 0x10000                    # research/54 §2a's `near` test: within 64 KB of a flanking anchor

# The loads and stores the key reads (R5900 forms included), by primary opcode; research/54 §1's list.
# Narrower than `address_matcher.MEM_OPS`, which also holds `pref`, `ll`/`sc` and the COP stores the mask
# must see: those are not field accesses, and the list is research/54's so that its counts reproduce.
MEM_DISP_OPS = frozenset((0x1A, 0x1B, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
                          0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x31, 0x35, 0x36, 0x37, 0x39, 0x3D, 0x3E,
                          0x3F))
SP_REG, ZERO_REG = 29, 0

OFFSET_RULE = (
    "offset-multiset (research/54 section 6, rule R7; S12-R12): the key K1 is the multiset of (primary "
    "opcode, signed 16-bit displacement) over every load and store in the body that is not based on $sp, "
    "$gp, $zero or a lui-formed address register (address_matcher's relinked-body mask decides which "
    "registers hold an address at each point). The key is worn by exactly one demo function and exactly "
    "one of our rows in the WHOLE image (functions under 64 B count as peers); it has >= %d accesses; both "
    "bodies are >= %d bytes and the size ratio is >= %.2f; neither side is one of Task 7's pairs; our row "
    "is still a placeholder. AND one tightening: the key has >= %d accesses, OR every demo callee that is "
    "one of Task 7's pairs maps into our body's call set (at least one does), OR the address-masked "
    "%d-instruction prologues are equal. Then Task 7's identifier hurdles (c_identifier, a spelling two "
    "candidates share refused for both, a name another proposals file spends at another address "
    "refused). Score %.2f. Evidence says which tightening carried a row under %d accesses (+ callees / "
    "+ prologue)."
) % (MIN_ACCESSES, MIN_BODY, SIZE_RATIO, STRONG_ACCESSES, PREFIX_WORDS, SCORE, STRONG_ACCESSES)

PREFIX_OFFSETS_RULE = (
    "prefix+offsets (research/54 section 2 and section 6's second use; S12-R12 amends S12-R3): a Task 7 "
    "prologue-only pair (pass prefix or prefix+size: the raw %d-instruction prologue unique on both "
    "sides) whose K1 offset-multiset key is ALSO unique both ways image-wide and equal on the two sides, "
    "with >= %d accesses and both bodies >= %d bytes; our row still a placeholder; Task 7's identifier "
    "hurdles. Two independent keys, each unique both ways, so research/44's hurdle 3 (a prologue alone is "
    "not a body) no longer applies. Score %.2f."
) % (PREFIX_WORDS, MIN_ACCESSES, MIN_BODY, PREFIX_SCORE)

LINK_ORDER_NOTE = (
    "Order: the link-order verdict against the two flanking Task 7 anchors inside our PT_LOAD (research/45 "
    "section 1's regions): `between` when the demo address lies between theirs, `outside` when it does not, "
    "`anchors-out-of-order` when the two anchors disagree, `edge` at a region end. research/54 section 2a "
    "measured this key's false pairs by link order (the `near` test: within 64 KB of a flanking anchor's demo "
    "address, truth rate from Task 7's 159 prologue pairs, null from the same pairs rotated), because nothing "
    "else can see them; so an `outside` row is written to the _loose file, never to the strict one."
)

HOLDOUT_NOTE = (
    "The holdout (research/45 section 3's shape over Task 7's 828 PROVED pairs) is printed but is blind to "
    "this key by construction (research/54 section 3): a proved pair is the same stream on both sides up to "
    "masked addresses, so its two bodies wear the same K1 key and the rule can refuse them but never pair them "
    "wrongly, so its zero says nothing. The link-order figure is the measurement."
)

PROPOSAL_COLUMNS = ["Address", "Current", "Proposed", "Mangled", "Score", "How", "Evidence", "Accesses",
                    "Order", "DemoAddr", "DemoSize", "OurSize", "Ratio"]


# ---- the key ----------------------------------------------------------------------------------

def accesses(code: bytes, census: Optional[collections.Counter] = None) -> List[Tuple[int, int, int]]:
    """[(opcode, base register, signed displacement)] of the loads and stores the key keeps.

    The lui tracking is `address_matcher.mask_address_operands`' own, step for step: a `lui` marks its
    target as holding an address, an `addiu`/`addi`/`ori` off such a register marks its own target, and any
    other write (`address_matcher._dest_reg`) clears the mark. `census`, when given, counts every access
    under `all` and then under exactly one of `$sp`, `$gp`, `$zero`, `lui-formed` or `kept`.
    """
    out = []
    holds: set = set()
    count = census if census is not None else collections.Counter()
    for i in range(0, len(code) - 3, 4):
        w = int.from_bytes(code[i:i + 4], "little")
        op = w >> 26
        rs, rt = (w >> 21) & 0x1F, (w >> 16) & 0x1F
        if op == am.LUI_OP:
            holds.add(rt)
            holds.discard(0)
            continue
        if op in am.LO_OPS and rs in holds:
            holds.add(rt)
            holds.discard(0)
            continue
        if op in MEM_DISP_OPS:
            disp = w & 0xFFFF
            disp = disp - 0x10000 if disp >= 0x8000 else disp
            count["all"] += 1
            if rs == SP_REG:
                count["$sp"] += 1
            elif rs == am.GP_REG:
                count["$gp"] += 1
            elif rs == ZERO_REG:
                count["$zero"] += 1
            elif rs in holds:
                count["lui-formed"] += 1
            else:
                count["kept"] += 1
                out.append((op, rs, disp))
        dest = am._dest_reg(w)
        if dest is not None:
            holds.discard(dest)
    return out


def key_of(code: bytes, census: Optional[collections.Counter] = None) -> Tuple[Tuple[int, int], ...]:
    """K1 over a body: the sorted tuple of (opcode, displacement). Its length is the access count."""
    return tuple(sorted((op, disp) for op, _reg, disp in accesses(code, census)))


def access_key(side: am.Side, start: int, end: int,
               census: Optional[collections.Counter] = None) -> Tuple[Tuple[int, int], ...]:
    """K1 over the bytes of `side` from `start` to `end` (empty when they are not in the image)."""
    return key_of(side.image.code(start, end), census)


class KeyIndex:
    """One side's K1 keys, sizes and masked prologues, computed once (the real pair takes ~20 s)."""

    def __init__(self, side: am.Side):
        self.side = side
        self.census = collections.Counter()
        self.key: Dict[int, tuple] = {}
        self.size: Dict[int, int] = {}
        for start in sorted(side.starts):
            body = side.body.get(start, b"")
            if not body:
                continue                     # a row with no bytes has no key (51 of ours)
            self.key[start] = key_of(body, self.census)
            self.size[start] = len(body)
        self.count = collections.Counter(self.key.values())
        self.by_key: Dict[tuple, List[int]] = collections.defaultdict(list)
        for start, k in self.key.items():
            self.by_key[k].append(start)
        self._pro: Dict[int, Optional[str]] = {}

    @classmethod
    def of(cls, side) -> "KeyIndex":
        return side if isinstance(side, cls) else cls(side)

    def prologue(self, start: int) -> Optional[str]:
        if start not in self._pro:
            self._pro[start] = sl._prologue(self.side, start)
        return self._pro[start]


def ratio(a: int, b: int) -> float:
    return min(a, b) / max(a, b) if max(a, b) else 0.0


def unique_pairs(demo: KeyIndex, ours: KeyIndex) -> Dict[int, int]:
    """{demo: ours} for every key worn by exactly one function on each side, image-wide (any length)."""
    out = {}
    for k, ds in demo.by_key.items():
        if len(ds) == 1 and ours.count.get(k, 0) == 1:
            out[ds[0]] = ours.by_key[k][0]
    return out


def callees_agree(d: int, o: int, demo: KeyIndex, ours: KeyIndex, anchor_map: Dict[int, int]) -> bool:
    """True when >= 1 demo callee is an anchor and every anchored demo callee maps into our callees."""
    mapped = [anchor_map[t] for t in demo.side.calls.get(d, ()) if t in anchor_map]
    if not mapped:
        return False
    have = set(ours.side.calls.get(o, ()))
    return all(t in have for t in mapped)


def prologue_equal(d: int, o: int, demo: KeyIndex, ours: KeyIndex) -> bool:
    p = demo.prologue(d)
    return p is not None and p == ours.prologue(o)


# ---- link order -------------------------------------------------------------------------------

def regions_of(side: am.Side) -> List[Tuple[int, int]]:
    """Our PT_LOADs: the walk is per region, as research/45 section 1 and `anchor_gaps` run it."""
    return sorted((v, v + len(data)) for v, data in side.image.segments)


def link_order(ours: am.Side, anchors):
    """order(d, o, skip=None) -> between / outside / anchors-out-of-order / edge.

    The nearest anchors below and above `o` inside its PT_LOAD of ours; `skip` is an (our, demo) anchor to
    leave out, so that an anchor can be judged without vouching for itself. research/53's S4b verdict.
    """
    regions = regions_of(ours)
    rows = [(o, d) for d, o, _h in sl._anchor_rows(anchors)]
    per = {r: sorted((o, d) for o, d in rows if r[0] <= o < r[1]) for r in regions}

    def order(d: int, o: int, skip=None) -> str:
        for r in regions:
            if r[0] <= o < r[1]:
                lst = [x for x in per[r] if x != skip] if skip else per[r]
                i = bisect.bisect_left(lst, (o, -1))
                j = i + 1 if i < len(lst) and lst[i][0] == o else i
                if i == 0 or j >= len(lst):
                    return "edge"
                (_o1, d1), (_o2, d2) = lst[i - 1], lst[j]
                if d2 <= d1:
                    return "anchors-out-of-order"
                return "between" if d1 < d < d2 else "outside"
        return "edge"

    return order


def near_check(pairs, ref, regions) -> Tuple[collections.Counter, List[Tuple[int, int]]]:
    """research/54 section 2a's `bracket`/`near` counts over (demo, ours) pairs against `ref` pairs.

    The two nearest reference pairs by OUR address inside our PT_LOAD, skipping any at the same our address
    (a pair never vouches for itself). `near`: the demo address lies within NEAR bytes of either reference's
    demo address, on that reference's side. Returns the counter and the pairs that are not near.
    """
    per = []
    for lo, hi in regions:
        inside = sorted((o, d) for d, o in ref if lo <= o < hi)
        per.append((lo, hi, [o for o, _d in inside], [d for _o, d in inside]))
    out = collections.Counter()
    bad = []
    for d, o in pairs:
        for lo, hi, os_, ds_ in per:
            if not lo <= o < hi:
                continue
            i = bisect.bisect_left(os_, o)
            j = i
            while j < len(os_) and os_[j] == o:
                j += 1
            if i == 0 or j >= len(os_):
                out["edge"] += 1
                break
            dp, dn = ds_[i - 1], ds_[j]
            near = (dp < d <= dp + NEAR) or (dn - NEAR <= d < dn)
            out["bracket yes" if dp < d < dn else "bracket no"] += 1
            out["near yes" if near else "near no"] += 1
            if not near:
                bad.append((d, o))
            break
        else:
            out["edge"] += 1
    return out, bad


def _rate(c, test="near") -> float:
    y, n = c[test + " yes"], c[test + " no"]
    return y / (y + n) if y + n else 0.0


def null_rate(pairs, ref, regions, fractions=(0.2, 0.4, 0.6, 0.8)) -> float:
    """The `near` rate of the same pairs with the demo side rotated by large fractions of the list."""
    pairs = sorted(pairs, key=lambda p: p[1])
    ds = [d for d, _o in pairs]
    rates = []
    for fr in fractions:
        r = int(len(ds) * fr)
        if r == 0:
            continue
        rot = [(ds[(k + r) % len(ds)], o) for k, (_d, o) in enumerate(pairs)]
        rates.append(_rate(near_check(rot, ref, regions)[0]))
    return sum(rates) / len(rates) if rates else 0.0


def false_estimate(p_obs: float, p_true: float, p_null: float, n: int) -> float:
    """f*n where p_obs = (1-f) p_true + f p_null."""
    if p_true <= p_null:
        return float("nan")
    return max(0.0, (p_true - p_obs) / (p_true - p_null)) * n


def link_order_figures(cands, anchors, ours: am.Side) -> Dict[str, float]:
    """research/54 section 2a's measurement of the pass: near (ref = the anchors + the pass's pairs), its
    null, the truth rate from the prologue-only anchors, and the false pairs those imply."""
    rows = sl._anchor_rows(anchors)
    regions = regions_of(ours)
    ref = [(d, o) for d, o, _h in rows]
    truth = [(d, o) for d, o, h in rows if h.startswith("prefix")]
    p_true = _rate(near_check(truth, ref, regions)[0]) if truth else 0.0
    sub = sorted((c.demo_addr, c.our_addr) for c in cands)
    c, bad = near_check(sub, ref + sub, regions)
    decided = c["near yes"] + c["near no"]
    p_null = null_rate(sub, ref + sub, regions)
    return {"near": c["near yes"], "decided": decided, "rate": _rate(c), "null": p_null, "p_true": p_true,
            "truth pairs": len(truth), "est false": false_estimate(_rate(c), p_true, p_null, decided),
            "not near": bad}


# ---- the passes ---------------------------------------------------------------------------------

class Candidate(NamedTuple):
    our_addr: int
    demo_addr: int
    demo_name: str
    our_name: str
    demo_size: int
    our_size: int
    accesses: int
    how: str
    score: float
    evidence: str
    order: str
    carried: Tuple[str, ...] = ()     # which of accesses / callees / prologue held

    @property
    def ratio(self) -> float:
        return ratio(self.demo_size, self.our_size)


def offset_pass(demo, ours, anchors) -> Tuple[List[Candidate], collections.Counter]:
    """(candidates, census) -- research/54's rule R7 (`OFFSET_RULE`) up to the identifier hurdles.

    `demo`/`ours` are `address_matcher.Side`s (or `KeyIndex`es over them); `anchors` is Task 7's pairs as
    [(demo address, our address, how)], `anchors_from_details`' shape. The census is a funnel over the
    pairs the key makes (worn once on each side), each refused pair counted under its first failed rule.
    """
    demo, ours = KeyIndex.of(demo), KeyIndex.of(ours)
    rows = sl._anchor_rows(anchors)
    t7_d = {d for d, _o, _h in rows}
    t7_o = {o for _d, o, _h in rows}
    amap = {d: o for d, o, _h in rows}
    order = link_order(ours.side, rows)
    census = collections.Counter()
    for d, k in demo.key.items():
        if len(k) >= MIN_ACCESSES and demo.size[d] >= MIN_BODY and not (
                demo.count[k] == 1 and ours.count.get(k, 0) == 1):
            census["key not unique both ways"] += 1
    out = []
    for d, o in sorted(unique_pairs(demo, ours).items()):
        census["unique both ways (any length)"] += 1
        n = len(demo.key[d])
        if n < MIN_ACCESSES:
            census["under %d accesses" % MIN_ACCESSES] += 1
            continue
        if demo.size[d] < MIN_BODY or ours.size[o] < MIN_BODY:
            census["body under %d bytes" % MIN_BODY] += 1
            continue
        census["eligible (research/54 section 2's pairs)"] += 1
        if d in t7_d or o in t7_o:
            census["one of Task 7's pairs"] += 1
            continue
        r = ratio(demo.size[d], ours.size[o])
        if r < SIZE_RATIO:
            census["size ratio under %.2f" % SIZE_RATIO] += 1
            continue
        our_name = ours.side.name.get(o, "")
        if not is_placeholder(our_name):
            census["our row already named"] += 1
            continue
        cal = callees_agree(d, o, demo, ours, amap)
        pro = prologue_equal(d, o, demo, ours)
        carried = tuple(t for t, ok in (("accesses", n >= STRONG_ACCESSES), ("callees", cal),
                                        ("prologue", pro)) if ok)
        if not carried:
            census["no tightening (< %d accesses, callees, prologue)" % STRONG_ACCESSES] += 1
            continue
        evidence = "offset multiset unique both sides, %d accesses, ratio %.2f" % (n, r)
        if n < STRONG_ACCESSES:
            evidence += "".join(" + %s" % t for t in carried)
        verdict = order(d, o)
        census["proposed"] += 1
        census["order %s" % verdict] += 1
        out.append(Candidate(o, d, demo.side.name[d], our_name, demo.size[d], ours.size[o], n, PASS,
                             SCORE, evidence, verdict, carried))
    return out, census


def prefix_offsets(demo, ours, details) -> Tuple[List[Candidate], collections.Counter]:
    """(candidates, census) -- Task 7's prologue-only pairs that K1 confirms (`PREFIX_OFFSETS_RULE`).

    `details` is `ghidra_symbol_match.match`'s out-parameter (it carries the demo address and the pass).
    """
    demo, ours = KeyIndex.of(demo), KeyIndex.of(ours)
    rows = sl.anchors_from_details(details)
    order = link_order(ours.side, rows)
    census = collections.Counter()
    out = []
    for d, o, how in rows:
        if not how.startswith("prefix"):
            continue
        census["prologue pairs"] += 1
        k = demo.key.get(d)
        if k is None or k != ours.key.get(o) or demo.count[k] != 1 or ours.count[k] != 1:
            census["key differs or not unique both ways"] += 1
            continue
        if len(k) < MIN_ACCESSES:
            census["under %d accesses" % MIN_ACCESSES] += 1
            continue
        if demo.size[d] < MIN_BODY or ours.size[o] < MIN_BODY:
            census["body under %d bytes" % MIN_BODY] += 1
            continue
        our_name = ours.side.name.get(o, "")
        if not is_placeholder(our_name):
            census["our row already named"] += 1
            continue
        census["confirmed"] += 1
        census["confirmed %s" % how] += 1
        evidence = ("prologue unique both sides + offset multiset unique both sides, %d accesses" % len(k))
        out.append(Candidate(o, d, demo.side.name[d], our_name, demo.size[d], ours.size[o], len(k),
                             PREFIX_PASS, PREFIX_SCORE, evidence, order(d, o, skip=(o, d)), (how,)))
    return out, census


def holdout(demo, ours, anchors, folds: int = 3, block: int = 8) -> Tuple[int, int]:
    """(re-derived, wrong) -- research/45 section 3's shape: the PROVED pairs held out in runs of `block`,
    R7 re-run with the rest as anchors (callees through the kept anchors only). BLIND to this key by
    construction (`HOLDOUT_NOTE`); printed because the brief's standard asks for it, labelled as such."""
    demo, ours = KeyIndex.of(demo), KeyIndex.of(ours)
    rows = sl._anchor_rows(anchors)
    proved = sl.proved_anchors(rows)
    pp = sorted((o, d) for d, o, _h in rows)
    truth_d = {d: o for o, d in pp}
    truth_o = {o: d for o, d in pp}
    eligible = [i for i, (_o, d) in enumerate(pp) if d in proved]
    base = {d: o for d, o in unique_pairs(demo, ours).items()
            if len(demo.key[d]) >= MIN_ACCESSES and demo.size[d] >= MIN_BODY and ours.size[o] >= MIN_BODY}
    got = bad = 0
    for phase in range(folds):
        hold = {eligible[j] for j in range(len(eligible)) if (j // block) % folds == phase}
        held_o = {pp[i][0] for i in hold}
        held_d = {pp[i][1] for i in hold}
        kept = {pp[i][1]: pp[i][0] for i in range(len(pp)) if i not in hold}
        for d, o in base.items():
            if d not in held_d and o not in held_o:
                continue
            if not (len(demo.key[d]) >= STRONG_ACCESSES or callees_agree(d, o, demo, ours, kept)
                    or prologue_equal(d, o, demo, ours)):
                continue
            got += 1
            bad += int(truth_d.get(d) != o or truth_o.get(o) != d)
    return got, bad


# ---- the proposals files ------------------------------------------------------------------------

def other_proposals(paths: Iterable[str]) -> Dict[str, Dict[int, List[str]]]:
    """{Proposed identifier: {our address: [file basenames]}} over the proposals files that exist."""
    out: Dict[str, Dict[int, List[str]]] = {}
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, newline="") as fh:
            for row in csv.DictReader(line for line in fh if not line.startswith("#")):
                name, addr = row.get("Proposed"), row.get("Address")
                if not name or not addr:
                    continue
                out.setdefault(name, {}).setdefault(int(addr, 16), []).append(os.path.basename(path))
    return out


def proposals(cands: Sequence[Candidate], taken: Dict[str, Dict[int, List[str]]]):
    """(rows, held) -- Task 7's identifier hurdles, and the other proposals files.

    `taken` is `other_proposals`' map. A spelling two candidates share is refused for both; a name another
    file proposes at ANOTHER address is refused (two rows cannot carry one name); the same name at the SAME
    address is kept and counted -- that is S12-R18's agreement, which the applier promotes on. A different
    name at the same address is kept and counted too: the applier refuses both and prints them, and it can
    only do that if it sees both.
    """
    held: Dict[str, int] = collections.Counter()
    spelling = collections.Counter(c_identifier(c.demo_name) for c in cands)
    by_addr: Dict[int, set] = {}
    for name, addrs in taken.items():
        for a in addrs:
            by_addr.setdefault(a, set()).add(name)
    rows = []
    for c in sorted(cands, key=lambda c: c.our_addr):
        ident = c_identifier(c.demo_name)
        if spelling[ident] > 1:
            held["identifier collides inside this pass"] += 1
            continue
        elsewhere = taken.get(ident, {})
        if any(a != c.our_addr for a in elsewhere):
            held["identifier already proposed at another address"] += 1
            continue
        if c.our_addr in elsewhere:
            held["agrees with another file (kept)"] += 1
        if by_addr.get(c.our_addr, set()) - {ident}:
            held["our row proposed under another name elsewhere (kept; the applier refuses both)"] += 1
        rows.append({"Address": "0x%08x" % c.our_addr, "Current": c.our_name, "Proposed": ident,
                     "Mangled": c.demo_name, "Score": "%.2f" % c.score, "How": c.how,
                     "Evidence": c.evidence, "Accesses": c.accesses, "Order": c.order,
                     "DemoAddr": "0x%08x" % c.demo_addr, "DemoSize": c.demo_size, "OurSize": c.our_size,
                     "Ratio": "%.2f" % c.ratio})
    return rows, dict(held)


def write_proposals(path: str, rows: Sequence[Dict], header: Sequence[str]) -> None:
    """One proposals file, its rule in `#` lines above the column line. An `outside` row may not be
    written to a strict (non-_loose) path: the boundary is enforced at the write, as `write_proposals_7b`
    enforces its own."""
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise ValueError("cannot write %s: %s is not a directory" % (path, directory))
    if not sl.is_loose_path(path):
        outside = sum(1 for r in rows if r.get("Order") == "outside")
        if outside:
            raise ValueError("cannot write %s: %d row(s) with link order `outside` belong at %s"
                             % (path, outside, sl.loose_path(path)))
    with open(path, "w", newline="") as fh:
        for line in header:
            fh.write("# %s\n" % line if line else "#\n")
        w = csv.DictWriter(fh, fieldnames=PROPOSAL_COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_split(path: str, rows: Sequence[Dict], header: Sequence[str]) -> Dict[str, int]:
    """The strict file at `path` and the `outside` rows at its _loose twin (both always written, so a
    stale loose file never outlives a run). Returns {path: rows written}."""
    loose = sl.loose_path(path)
    strict_rows = [r for r in rows if r.get("Order") != "outside"]
    loose_rows = [r for r in rows if r.get("Order") == "outside"]
    write_proposals(path, strict_rows, header)
    write_proposals(loose, loose_rows, list(header) + [
        "", "THIS IS THE LOOSE FILE: every row here has link order `outside` its flanking Task 7 anchors. "
        "research/54 measured this key's false pairs by link order, so these rows wait for a second lever "
        "(S12-R18) or a reader."])
    return {path: len(strict_rows), loose: len(loose_rows)}


def _preamble(path: str) -> List[str]:
    return ["%s -- Sprint 12 Task 13 proposals. PROPOSALS ONLY:" % path,
            "recomp/socom2_ghidra.csv and recomp/socom2_names.csv are unchanged; applying these is "
            "tools_py/apply_names.py's step, which also joins the levers' files (S12-R18).",
            "Names come from the SOCOM 1 demo's .symtab. Addresses are OURS (r0001). "
            "docs/research/54-offset-multiset.md", ""]


def _census_line(label: str, census) -> str:
    return "%s: %s" % (label, ", ".join("%s %d" % kv for kv in sorted(census.items())))


def header(path: str, census, held, figures: Dict[str, str], anchors_note: str = "") -> List[str]:
    """The strict file's `#` lines: the rule, the link-order note, the holdout's label, the census, the
    measured figures (`figures`: label -> text), the anchor composition."""
    lines = _preamble(path) + [OFFSET_RULE, "", LINK_ORDER_NOTE, "", HOLDOUT_NOTE, ""]
    lines.append(_census_line("census", census))
    if held:
        lines.append(_census_line("identifier hurdles", held))
    for label, text in figures.items():
        lines.append("%s: %s" % (label, text))
    if anchors_note:
        lines.append(anchors_note)
    return lines + [""]


def prefix_header(path: str, census, held, anchors_note: str = "") -> List[str]:
    lines = _preamble(path) + [PREFIX_OFFSETS_RULE, "", LINK_ORDER_NOTE + " Here each pair is itself one of "
                               "Task 7's anchors, judged with itself left out.", "", _census_line("census", census)]
    if held:
        lines.append(_census_line("identifier hurdles", held))
    if anchors_note:
        lines.append(anchors_note)
    return lines + [""]


# ---- the CLI ------------------------------------------------------------------------------------

def _under_game(path: str) -> bool:
    return os.path.abspath(path).startswith(os.path.abspath("game") + os.sep)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="the offset-multiset lever (research/54, S12-R12)")
    ap.add_argument("demo_elf")
    ap.add_argument("our_elf")
    ap.add_argument("our_csv")
    ap.add_argument("matches_json", help="game/demo_symbol_matches.json: its count checks the re-derivation")
    ap.add_argument("--out", help="the strict proposals file (under game/); `outside` rows go to its _loose twin")
    ap.add_argument("--prefix-out", dest="prefix_out", help="the prefix+offsets proposals file (under game/)")
    ap.add_argument("--no-holdout", dest="holdout", action="store_false", help="skip the (blind) holdout")
    args = ap.parse_args(argv)

    missing = [p for p in (args.demo_elf, args.our_elf, args.our_csv) if not os.path.exists(p)]
    if missing:
        for p in missing:
            print("NO-DATA: missing %s" % p)
        return 2
    for p in (args.out, args.prefix_out):
        if p and not _under_game(p):
            print("NO-DATA: %s must be under game/ (git-ignored)" % p)
            return 2

    demo_rows, demo_segs = gsm.load_demo(args.demo_elf)
    our_rows, our_segs = gsm.load_ours(args.our_elf, args.our_csv)
    details: Dict = {}
    pairs = gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
    anchors = sl.anchors_from_details(details)
    json_n = None
    if os.path.exists(args.matches_json):
        with open(args.matches_json) as fh:
            json_n = json.load(fh).get("matched")
    comp = sl.anchor_composition(anchors)
    anchors_note = ("Anchors: %d Task 7 pairs re-derived with --prefix (%s; %s says %s); %d PROVED, the rest "
                    "prologue-only" % (len(anchors), ", ".join("%s %d" % kv for kv in sorted(comp.items())),
                                       args.matches_json, json_n, len(sl.proved_anchors(anchors))))
    print(anchors_note)
    if json_n is not None and json_n != len(pairs):
        print("NO-DATA: Task 7 re-derived %d pairs but %s says %d" % (len(pairs), args.matches_json, json_n))
        return 2

    demo = KeyIndex(am.Side(demo_rows, demo_segs))
    ours = KeyIndex(am.Side(our_rows, our_segs))
    for label, k in (("demo", demo), ("ours", ours)):
        c = k.census
        print("  %s accesses %d; dropped $sp %d, $gp %d, $zero %d, lui-formed %d; kept %d"
              % (label, c["all"], c["$sp"], c["$gp"], c["$zero"], c["lui-formed"], c["kept"]))

    found, census = offset_pass(demo, ours, anchors)
    print("\n" + _census_line("offset-multiset funnel", census))
    strong = [c for c in found if "accesses" in c.carried]
    weak = [c for c in found if "accesses" not in c.carried]
    tight = (">= %d accesses %d (callees also agree %d, prologue also equal %d); under %d carried "
             "by callees only %d, prologue only %d, both %d; callees agree overall %d, prologue equal overall %d"
             % (STRONG_ACCESSES, len(strong), sum("callees" in c.carried for c in strong),
                sum("prologue" in c.carried for c in strong), STRONG_ACCESSES,
                sum(c.carried == ("callees",) for c in weak), sum(c.carried == ("prologue",) for c in weak),
                sum(c.carried == ("callees", "prologue") for c in weak),
                sum("callees" in c.carried for c in found), sum("prologue" in c.carried for c in found)))
    print("tightening: " + tight)
    fig = link_order_figures(found, anchors, ours.side)
    near = ("near (ref = Task 7's %d + this pass's %d) %d/%d (%.1f%%, null %.1f%%); truth from the %d "
            "prologue pairs %.1f%%; est. false %.1f (research/54 section 3a: 186/192, est. 0.0, 2 sigma ~5)"
            % (len(anchors), len(found), fig["near"], fig["decided"], 100 * fig["rate"], 100 * fig["null"],
               fig["truth pairs"], 100 * fig["p_true"], fig["est false"]))
    print(near)
    oname = ours.side.name
    for d, o in sorted(fig["not near"], key=lambda p: -demo.size[p[0]]):
        c = next(x for x in found if x.demo_addr == d)
        print("    not near: 0x%08x demo 0x%08x %5d/%5d %3d acc %-18s order %-8s %s"
              % (o, d, c.demo_size, c.our_size, c.accesses, "+".join(c.carried), c.order, c.demo_name[:70]))
    regions = regions_of(ours.side)
    split = ", ".join("0x%06x-0x%06x %d (engine %d)" % (lo, hi, sum(lo <= c.our_addr < hi for c in found),
                                                          sum(lo <= c.our_addr < hi and gsm.is_engine(c.demo_name)
                                                              for c in found))
                      for lo, hi in regions)
    print("per PT_LOAD of ours: %s; engine-shaped %d of %d"
          % (split, sum(gsm.is_engine(c.demo_name) for c in found), len(found)))
    print("twelve largest (by demo size): our addr, demo/our B, accesses, carried, order, name")
    for c in sorted(found, key=lambda c: -c.demo_size)[:12]:
        print("  0x%08x %5d/%5d %3d %-18s %-8s %s" % (c.our_addr, c.demo_size, c.our_size, c.accesses,
                                                     "+".join(c.carried), c.order, c.demo_name))

    hold = ""
    if args.holdout:
        parts = []
        for block in (8, 1):
            got, bad = holdout(demo, ours, anchors, block=block)
            parts.append("block %d: %d re-derived, %d wrong" % (block, got, bad))
        hold = "; ".join(parts) + " -- BLIND to this key by construction (research/54 section 3), not a rate"
        print("holdout over the %d PROVED pairs (3 folds): %s" % (len(sl.proved_anchors(anchors)), hold))

    pfound, pcensus = prefix_offsets(demo, ours, details)
    print("\n" + _census_line("prefix+offsets", pcensus)
          + "; engine-shaped %d" % sum(gsm.is_engine(c.demo_name) for c in pfound))
    pcensus.update("order %s" % c.order for c in pfound)
    print("  link order (each judged with itself left out): %s" % ", ".join(
        "%s %d" % kv for kv in sorted(collections.Counter(c.order for c in pfound).items())))
    for c in pfound:
        if c.order == "outside":
            print("    outside -> loose: 0x%08x demo 0x%08x %d/%d B %d acc %s %s"
                  % (c.our_addr, c.demo_addr, c.demo_size, c.our_size, c.accesses, c.carried[0], c.demo_name))

    ours_paths = set()
    for p in (args.out, args.prefix_out):
        if p:
            ours_paths |= {os.path.abspath(p), os.path.abspath(sl.loose_path(p))}
    others = sorted(p for p in glob.glob("game/demo_symbol_renames*.csv") if os.path.abspath(p) not in ours_paths)
    taken = other_proposals(others)
    print("other proposals files read: %s (%d identifiers)" % (", ".join(others) or "none", len(taken)))
    rows, held = proposals(found, taken)
    prows, pheld = proposals(pfound, taken)
    for label, cands, hd in (("offset-multiset", found, held), ("prefix+offsets", pfound, pheld)):
        print("%s identifier hurdles: %s" % (label, ", ".join("%s %d" % kv for kv in sorted(hd.items())) or "none"))
        for c in cands:
            ident = c_identifier(c.demo_name)
            for a, files in sorted(taken.get(ident, {}).items()):
                print("    %s 0x%08x in %s: %s at 0x%08x" % ("agrees" if a == c.our_addr else "COLLIDES",
                                                            c.our_addr, ",".join(files), ident, a))
            for name, addrs in taken.items():
                if name != ident and c.our_addr in addrs:
                    print("    ADDRESS 0x%08x: %s here, %s in %s" % (c.our_addr, ident, name,
                                                                   ",".join(addrs[c.our_addr])))

    figures = {"tightening": tight, "link order (the measurement)": near,
               "order verdicts": ", ".join("%s %d" % (k[6:], v) for k, v in sorted(census.items())
                                           if k.startswith("order "))}
    if hold:
        figures["holdout (blind)"] = hold
    try:
        if args.out:
            written = write_split(args.out, rows, header(args.out, census, held, figures, anchors_note))
            for p, n in written.items():
                print("wrote %s (%d rows)" % (p, n))
        if args.prefix_out:
            written = write_split(args.prefix_out, prows,
                                  prefix_header(args.prefix_out, pcensus, pheld, anchors_note))
            for p, n in written.items():
                print("wrote %s (%d rows)" % (p, n))
    except (ValueError, OSError) as exc:
        print("NO-DATA: %s" % exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
