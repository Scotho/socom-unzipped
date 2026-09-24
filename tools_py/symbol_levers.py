"""Sprint 11 Task 7b: two more levers on the SOCOM 1 demo's names -- position, and a third build.

Task 7 (`tools_py/ghidra_symbol_match.py`, `docs/research/44-demo-symbols.md`) placed 987 of the SOCOM
1 demo's 9,703 named functions onto our anonymous SOCOM II rows and proposed 479 of them as renames.
Its ceiling is the fingerprint: 78 % of the demo's functions have no byte-identical counterpart in our
image at all, because SOCOM II is a year of edits later. This module adds the two levers a peer review
(socom-pc-6c's measurement, 2026-09-24) measured as worth building, each with its OWN acceptance rule
and its own proposals file. Neither ever touches `recomp/socom2_ghidra.csv`.

LEVER 1 -- POSITION BETWEEN ANCHORS (`positional`). Link order survives between the two games. Sorted
by our address, consecutive Task 7 pairs keep the demo's order 97.2 % of the time in the boot-loader
region, 90.7 % in FTSCore, 92.1 % in ZSealEtc. (The whole-image longest increasing subsequence is only
492/984, because the demo's single PT_LOAD interleaves what we split into three overlays -- so the walk
runs PER REGION, never over the whole image.) Between two consecutive anchors that are in order on both
sides, when both builds hold the same number of unplaced functions, the i-th on one side is the i-th on
the other. That is a correspondence, not yet evidence, so every candidate then has to buy its name with
a size ratio and a body or prologue hash -- see `POSITIONAL_RULE`.

LEVER 2 -- THE BRIDGE THROUGH THE AUG 18 2003 SOCOM II DEMO (`bridge`). `game/demo_scus_973_68/
SCUS_973.68` sits between SOCOM 1 and retail r0001 in time. It is STRIPPED -- zero symbols -- so it can
never contribute a NAME; its only possible contribution is body evidence, as a stepping stone: demo1 ->
demo2 -> retail, each hop by `tools_py/address_matcher.match`. It needs a function table, which
`scan_functions` derives from the bytes (see its docstring and its measured limits). On the real inputs
this lever adds ZERO names, and why is the interesting part -- see docs/research/45.

    python -m tools_py.ghidra_symbol_match \\
        game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf recomp/socom2_ghidra.csv \\
        --prefix --positional --bridge game/demo_scus_973_68/SCUS_973.68 \\
        --renames-7b game/demo_symbol_renames_7b.csv
"""
import bisect
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from tools_py import address_matcher as am
from tools_py.fingerprint import fingerprint

JR_RA = 0x03E00008
JAL = 0x03

# -- lever 1's thresholds, and where each number comes from -----------------------------------
#
# PROLOGUE_WORDS is `ghidra_symbol_match.PREFIX_WORDS`: the same 16-instruction window the prefix
# pass hashes, so "the prologue agrees" means the same thing in both modules. It is imported rather
# than re-spelt at the bottom of this file, to keep the two from drifting apart.
#
# SIZE_RATIO 0.5 -- neither body more than twice the other -- is MEASURED, not chosen. Task 7's 159
# prefix-pass pairs are the sample of "the same routine, edited between the two games": their
# min/max size ratio has a 5th percentile of 0.478 and 153 of the 159 (96.2 %) clear 0.5. A tighter
# cut starts refusing routines we have independent reason to believe are the same one; a looser one
# stops refusing anything at all.
#
# TIER_A_MIN_SIZE 32 bytes (eight instructions) is the floor under the body-hash tier. A `jr $ra;
# nop` thunk hashes the same in every program ever compiled, so under eight instructions the hash
# adds nothing to the position and the pair would rest on position alone.
#
# TIER_B_MIN_SIZE 64 bytes is Task 7's own `PROPOSE_MIN_SIZE`, kept because tier B's evidence is a
# prologue -- and a prologue that IS the whole function is not a prologue.
SIZE_RATIO = 0.5
TIER_A_MIN_SIZE = 32
TIER_B_MIN_SIZE = 64
# For the rule text only. The window itself is passed in from `ghidra_symbol_match.PREFIX_WORDS`,
# so that "the prologue" means one thing in both modules; this is that number spelt for a reader.
PROLOGUE_WORDS_DOC = 16

POSITIONAL_RULE = (
    "positional: the i-th unplaced function between two consecutive Task 7 anchors that are in order "
    "on both sides and inside one PT_LOAD of ours, when both builds hold the same count in that gap. "
    "Accepted only with body evidence -- tier A: equal body length and equal address-masked "
    "fingerprint (address_matcher's own relinked-body test, which the matcher refused only for want "
    "of a unique hash; position supplies it), body >= %d bytes. Tier B: equal address-masked "
    "%d-instruction prologue hash, both bodies >= %d bytes, size ratio >= %.2f (the 5th percentile "
    "of Task 7's 159 prefix-pass pairs, which ARE the same routine after a year of edits, is 0.478). "
    "And that evidence must be GAP-DISCRIMINATING: a candidate whose body key equals a sibling's in "
    "the same gap has not been checked by it, only re-asserted. Never overrides a Task 7 pair or a "
    "hand-chosen name; the identifier hurdles are Task 7's. Error measured by holding out Task 7's "
    "own 984 pairs in 3 folds and re-deriving them: singly, tier A 360 with 1 wrong and tier B 32 "
    "with 0; in blocks of 8, tier A 127 and tier B 8 with 0 wrong, against 19 untiered with 2 wrong. "
    "Reproduce with --holdout 3 --holdout-block 8."
) % (TIER_A_MIN_SIZE, PROLOGUE_WORDS_DOC, TIER_B_MIN_SIZE, SIZE_RATIO)

BRIDGE_RULE = (
    "bridge: a demo1 name reaches a retail row only when demo1 -> demo2 (SCUS_973.68, Aug 18 2003) "
    "and demo2 -> retail are BOTH `exact` or `relinked-body`, the composition contradicts no Task 7 "
    "pair, and our row is still FUN_*. demo2 is stripped, so it contributes body evidence only, "
    "never a name."
)


class Candidate(NamedTuple):
    """One positional or bridge pairing, with everything its acceptance rule weighed."""
    our_addr: int
    demo_addr: int
    demo_name: str
    our_name: str
    demo_size: int
    our_size: int
    tier: Optional[str]                    # "A" / "B" for positional; "exact+exact" etc. for bridge
    gap: int                               # how many functions shared this anchor gap (0 for bridge)
    discriminating: bool = True            # could the body evidence tell it from its gap siblings?

    @property
    def ratio(self) -> float:
        hi = max(self.demo_size, self.our_size)
        return min(self.demo_size, self.our_size) / hi if hi else 0.0


# ---- a function table for an image with no symbols ------------------------------------------

def scan_functions(segments, jal_seed: bool = True, ptr_seed: bool = False) -> List[Tuple[int, int, str]]:
    """[(start, end, "sub_xxxxxxxx")] for a STRIPPED image, from its bytes alone.

    Three rules, in decreasing reliability:

      * what follows a `jr $ra` and its delay slot (past any zero padding) is a function start. On
        MIPS you cannot fall through a return, so this one is nearly exact and it does the work.
      * every `jal` target inside the image is a function start. This catches the first function of
        a run and anything the rule above lands one instruction off.
      * every 32-bit word in the image that points at an aligned address inside it -- a vtable or
        constructor-table entry. OFF by default: it is measured below to make the table WORSE.

    A range then runs to the next start, with trailing zero padding trimmed, and is dropped if it is
    under two instructions or contains no `jr $ra` at all (that is data, or a jump table).

    MEASURED LIMITS, by running this on the SOCOM 1 demo -- whose `.symtab` is the ground truth --
    with `jal_seed=True, ptr_seed=False`: 9,532 ranges against 9,703 real functions; 9,353 of the
    real functions get their start right (recall 96.4 %, precision 98.1 %), and 9,177 (94.6 %) get
    BOTH boundaries right and so fingerprint like the real thing. Turning `ptr_seed` on drops that to
    92.2 %: a vtable slot pointing into the middle of a function splits it. The 5 % whose extent is
    wrong cost RECALL, not correctness -- a wrongly cut body simply fingerprints like nothing else.
    A function that is never a `jal` target and never follows a return (reached only through a
    register, in the middle of a run) is invisible to this, and its bytes are absorbed by its
    predecessor, which spoils that one too. `scan_accuracy` is this paragraph as a measurement.
    """
    out: List[Tuple[int, int, str]] = []
    for vaddr, data in segments:
        n = len(data) // 4
        words = [int.from_bytes(data[i * 4:i * 4 + 4], "little") for i in range(n)]
        starts = {vaddr}
        i = 0
        while i < n - 1:
            if words[i] == JR_RA:
                j = i + 2                                  # past the delay slot
                while j < n and words[j] == 0:
                    j += 1                                 # past the inter-function padding
                if j < n:
                    starts.add(vaddr + j * 4)
                i = j
                continue
            i += 1
        if jal_seed:
            for i, w in enumerate(words):
                if (w >> 26) == JAL:
                    pc = vaddr + i * 4
                    target = ((pc + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
                    if vaddr <= target < vaddr + len(data):
                        starts.add(target)
        if ptr_seed:
            for w in words:
                if vaddr <= w < vaddr + len(data) and not (w & 3):
                    starts.add(w)
        ordered = sorted(starts)
        for k, start in enumerate(ordered):
            end = ordered[k + 1] if k + 1 < len(ordered) else vaddr + n * 4
            lo, hi = (start - vaddr) // 4, (end - vaddr) // 4
            body = words[lo:hi]
            if JR_RA not in body:
                continue                                   # data, or a jump table: not a function
            # Trim the inter-function padding, but never past the delay slot of the last `jr $ra`:
            # a `nop` delay slot IS a zero word, and trimming it would cut the function one
            # instruction short and make it fingerprint like nothing in either image.
            floor = lo + len(body) - 1 - body[::-1].index(JR_RA) + 2
            while hi > floor and words[hi - 1] == 0:
                hi -= 1
            end = vaddr + hi * 4
            if end - start < 8:
                continue
            out.append((start, end, "sub_%08x" % start))
    return sorted(out)


def scan_accuracy(elf) -> Dict[str, int]:
    """{ranges, starts_right, both_right, real} -- `scan_functions` against an ELF's own `.symtab`.

    This is the docstring's numbers, as a measurement anyone can re-run rather than a claim. It is
    what `--bridge` prints before it trusts the demo2 table, and what the test pins.
    """
    truth = {s: e for s, e, _n in elf.functions}
    got = scan_functions(elf.segments)
    return {"ranges": len(got), "real": len(truth),
            "starts_right": sum(1 for s, _e, _n in got if s in truth),
            "both_right": sum(1 for s, e, _n in got if truth.get(s) == e)}


# ---- lever 1: position between anchors -------------------------------------------------------

def _prologue(side: am.Side, start: int, words: int) -> Optional[str]:
    """The address-masked hash of this body's first `words` instructions, or None if it is shorter.

    Masked, where `ghidra_symbol_match._prefix_pass` hashes the raw stream: a prologue that reaches a
    global has half an address in a load displacement, and between two GAMES that half always moves.
    The mask is `address_matcher.mask_address_operands`, the same one the relinked-body pass uses.
    """
    body = side.body.get(start, b"")
    width = words * 4
    if len(body) < width:
        return None
    return fingerprint(am.mask_address_operands(body)[:width])


def _tier(demo: am.Side, d_addr: int, ours: am.Side, o_addr: int, prologue_words: int) -> Optional[str]:
    """"A", "B" or None -- which body rule, if either, this candidate clears."""
    d_size, o_size = demo.size.get(d_addr, 0), ours.size.get(o_addr, 0)
    if not d_size or not o_size:
        return None
    if d_size == o_size and d_size >= TIER_A_MIN_SIZE:
        rel = demo.relfp(d_addr)
        if rel is not None and rel == ours.relfp(o_addr):
            return "A"
    if d_size >= TIER_B_MIN_SIZE and o_size >= TIER_B_MIN_SIZE \
            and min(d_size, o_size) / max(d_size, o_size) >= SIZE_RATIO:
        pro = _prologue(demo, d_addr, prologue_words)
        if pro is not None and pro == _prologue(ours, o_addr, prologue_words):
            return "B"
    return None


def _slice(sorted_starts: Sequence[int], lo: int, hi: int) -> List[int]:
    """The starts strictly between `lo` and `hi`."""
    return list(sorted_starts[bisect.bisect_right(sorted_starts, lo):bisect.bisect_left(sorted_starts, hi)])


def anchor_gaps(anchors: Sequence[Tuple[int, int]], our_starts: Sequence[int],
                demo_starts: Sequence[int], regions: Sequence[Tuple[int, int]],
                placed_ours: set, placed_demo: set) -> List[List[Tuple[int, int]]]:
    """[[(our_addr, demo_addr), ...], ...] -- one list per usable gap, before any body check.

    `anchors` is [(our address, demo address)]. The walk is PER REGION because the demo's single
    PT_LOAD interleaves our three overlays: run over the whole image, consecutive pairs disagree with
    the demo's order often enough to make nonsense of the gaps (the peer's whole-image LIS is 492 of
    984, against 90-97 % agreement inside each region). Within a region, a gap is used only when its
    two anchors are in order on BOTH sides and both sides hold the same number of unplaced starts.

    The GROUPING is kept rather than flattened because the acceptance rule needs it: a candidate's
    real rivals are the other functions in its own gap, and `_discriminating` asks whether the body
    evidence can tell it from them.
    """
    out: List[List[Tuple[int, int]]] = []
    for lo, hi in regions:
        inside = sorted((o, d) for o, d in anchors if lo <= o < hi)
        for (o1, d1), (o2, d2) in zip(inside, inside[1:]):
            if d2 <= d1:
                continue                                   # the pair is out of order: no gap here
            ours_in = [x for x in _slice(our_starts, o1, o2) if x not in placed_ours]
            demo_in = [x for x in _slice(demo_starts, d1, d2) if x not in placed_demo]
            if not ours_in or len(ours_in) != len(demo_in):
                continue
            out.append(list(zip(ours_in, demo_in)))
    return out


def _body_key(side: am.Side, addr: int, tier: str, prologue_words: int):
    """What the tier's body evidence actually sees of this function -- its discriminating power."""
    if tier == "A":
        return ("A", side.size.get(addr, 0), side.relfp(addr))
    return ("B", _prologue(side, addr, prologue_words))


def _discriminating(gap: Sequence[Tuple[int, int]], demo: am.Side, ours: am.Side,
                    o_addr: int, d_addr: int, tier: str, prologue_words: int) -> bool:
    """Can the body evidence tell this pairing from the other functions in its own gap?

    This is the hurdle the first cut of this module did not have, and the measurement that put it
    there: of 37 pairs that cleared tier A or B, 18 shared their body key with a SIBLING IN THE SAME
    GAP -- the five `sceSifQuery*` wrappers, `stat` and `unlink`, `sceDmaSendN`/`sceDmaSendI`. Those
    families are the same instruction stream differing only in an immediate, and `fingerprint` zeroes
    `addiu`/`ori` immediates on purpose, so their masked hashes are equal by construction. For such a
    pair the body check confirms nothing that position did not already assert, and a reordering of
    two siblings between the two games would swap `sceSifQueryMemSize` and `sceSifQueryBlockSize`
    with no evidence anywhere that it had happened. The body evidence exists to CHECK the positional
    guess; where it cannot separate the candidate from its own neighbours it has not checked it.
    """
    mine_d = _body_key(demo, d_addr, tier, prologue_words)
    mine_o = _body_key(ours, o_addr, tier, prologue_words)
    for o_other, d_other in gap:
        if d_other != d_addr and _body_key(demo, d_other, tier, prologue_words) == mine_d:
            return False
        if o_other != o_addr and _body_key(ours, o_other, tier, prologue_words) == mine_o:
            return False
    return True


def positional(demo_funcs, demo_segments, our_funcs, our_segments, pairs_with_demo_addr,
               prologue_words: int, regions=None, allow_blurred: bool = False):
    """(accepted, census) -- lever 1.

    `pairs_with_demo_addr` is [(demo_addr, our_addr)] for every Task 7 pair; those are the anchors AND
    the rows a candidate may never take. `accepted` is [Candidate] with a tier; `census` counts every
    stage so the note's numbers have a source.

    `allow_blurred` (the CLI's `--positional-blurred`) admits the pairs `_discriminating` refuses.
    It is the one JUDGEMENT in this rule rather than a measurement, so it is a knob and its default
    is off: the 19 pairs it admits on the real inputs are wrapper families -- five `sceSifQuery*`,
    `stat`/`unlink`, `sceDmaSendN`/`sceDmaSendI`, `rt_mutex_platform_lock`/`_destroy` -- where the
    only thing separating a name from its sibling is the order the linker emitted them in. That
    order is source order and a reordering is unlikely; the holdout saw 10 such pairs and got all
    ten right. Ten is not a measurement, and a silently swapped `sceSifQueryMemSize` is the kind of
    wrong name nobody ever catches, so the default file leaves them out and the note names them.
    """
    demo = am.Side(demo_funcs, demo_segments)
    ours = am.Side(our_funcs, our_segments)
    if regions is None:
        regions = [(v, v + len(d)) for v, d in ours.image.segments]
    placed_demo = {d for d, _o in pairs_with_demo_addr}
    placed_ours = {o for _d, o in pairs_with_demo_addr}
    anchors = [(o, d) for d, o in pairs_with_demo_addr]
    gaps = anchor_gaps(anchors, sorted(ours.starts), sorted(demo.starts), regions,
                       placed_ours, placed_demo)

    census = {"anchors": len(anchors), "gaps": len(gaps),
              "candidates": sum(len(g) for g in gaps), "tier A": 0, "tier B": 0,
              "no body evidence": 0, "body evidence not gap-discriminating": 0,
              "our row already named": 0}
    accepted: List[Candidate] = []
    for gap in gaps:
        for o_addr, d_addr in gap:
            tier = _tier(demo, d_addr, ours, o_addr, prologue_words)
            if tier is None:
                census["no body evidence"] += 1
                continue
            sharp = _discriminating(gap, demo, ours, o_addr, d_addr, tier, prologue_words)
            if not sharp:
                census["body evidence not gap-discriminating"] += 1
                if not allow_blurred:
                    continue
            our_name = ours.name.get(o_addr, "")
            if not (our_name.startswith("FUN_") or our_name.startswith("thunk_FUN_")):
                census["our row already named"] += 1
                continue
            census["tier " + tier] += 1
            accepted.append(Candidate(o_addr, d_addr, demo.name[d_addr], our_name,
                                      demo.size[d_addr], ours.size[o_addr], tier, len(gap), sharp))
    return accepted, census


def holdout(demo_funcs, demo_segments, our_funcs, our_segments, pairs_with_demo_addr,
            prologue_words: int, folds: int = 3, regions=None, block: int = 1):
    """{tier: (re-derived, of those wrong)} -- lever 1's error rate, measured on known answers.

    Hold out every k-th Task 7 pair, run the walk with the rest as anchors, and check the held-out
    rows against the answer Task 7 already proved. This is the only honest way to put a number on
    "position implies identity", and it is why the rule above is two tiers rather than one.

    `block` holds out RUNS of that many consecutive pairs instead of single ones. It exists because
    `block=1` produces gaps that hold one held-out function each, and a gap of one is discriminating
    by definition -- so a single-pair holdout never exercises `_discriminating` at all and says
    nothing about the multi-function gaps the real run actually scores. `--holdout K --holdout-block
    B` reports both.

    Its BIAS is worth stating with its result: a held-out pair is by construction a function Task 7
    COULD match, i.e. one that survived into SOCOM II nearly intact. The candidates the real run
    scores are the ones Task 7 could not match. So this measures the walk, not the population, and
    it is an upper bound on the real accuracy.
    """
    demo = am.Side(demo_funcs, demo_segments)
    ours = am.Side(our_funcs, our_segments)
    if regions is None:
        regions = [(v, v + len(d)) for v, d in ours.image.segments]
    our_starts, demo_starts = sorted(ours.starts), sorted(demo.starts)
    pp = sorted((o, d) for d, o in pairs_with_demo_addr)
    truth = dict(pp)
    all_ours, all_demo = {o for o, _d in pp}, {d for _o, d in pp}

    out: Dict[str, List[int]] = {k: [0, 0] for k in ("A", "B", "blurred", "untiered")}
    block = max(1, int(block))
    for phase in range(folds):
        hold_i = [i for i in range(len(pp)) if (i // block) % folds == phase]
        held = [pp[i] for i in hold_i]
        keep = [pp[i] for i in range(len(pp)) if i not in set(hold_i)]
        held_ours = {o for o, _d in held}
        gaps = anchor_gaps(keep, our_starts, demo_starts, regions,
                           all_ours - held_ours, all_demo - {d for _o, d in held})
        for gap in gaps:
            for o_addr, d_addr in gap:
                if o_addr not in held_ours:
                    continue
                wrong = truth[o_addr] != d_addr
                tier = _tier(demo, d_addr, ours, o_addr, prologue_words)
                if tier is None:
                    bucket = "untiered"
                elif _discriminating(gap, demo, ours, o_addr, d_addr, tier, prologue_words):
                    bucket = tier
                else:
                    bucket = "blurred"          # a tier the gap's siblings make unfalsifiable
                out[bucket][0] += 1
                out[bucket][1] += int(wrong)
    return {k: tuple(v) for k, v in out.items()}


# ---- lever 2: the bridge through the stripped SOCOM II demo ----------------------------------

STRONG_HOPS = ("exact", "relinked-body")


def bridge(demo_funcs, demo_segments, demo2_funcs, demo2_segments, our_funcs, our_segments,
           pairs_with_demo_addr, strong=STRONG_HOPS):
    """(accepted, census) -- lever 2.

    Two independent runs of `address_matcher.match`, composed. A demo1 name reaches one of our rows
    only when BOTH hops are `exact` or `relinked-body` -- a `hash+callees` hop inherits the other
    hop's pairs as its evidence, and a prefix hop is a prologue, so neither belongs in a composition
    whose whole claim is that two bodies are the same body. A composed pair that names a demo
    function Task 7 already placed elsewhere, or one of our rows Task 7 already named, is a
    CONTRADICTION and is counted, never written.
    """
    hop1 = am.match(demo_funcs, demo_segments, demo2_funcs, demo2_segments)
    hop2 = am.match(demo2_funcs, demo2_segments, our_funcs, our_segments)
    demo_name = {s: n for s, _e, n in demo_funcs}
    demo_size = {s: e - s for s, e, _n in demo_funcs}
    our_name = {s: n for s, _e, n in our_funcs}
    our_size = {s: e - s for s, e, _n in our_funcs}
    t7_by_demo = dict(pairs_with_demo_addr)
    t7_by_our = {o: d for d, o in pairs_with_demo_addr}

    census = {"hop1 resolved": sum(1 for b, _h in hop1.values() if b is not None),
              "hop2 resolved": sum(1 for b, _h in hop2.values() if b is not None),
              "composed (any pass)": 0, "composed (both hops strong)": 0,
              "agrees with Task 7": 0, "contradicts Task 7": 0, "our row already named": 0,
              "new": 0}
    accepted: List[Candidate] = []
    for d_addr, (mid, how1) in sorted(hop1.items()):
        if mid is None:
            continue
        o_addr, how2 = hop2.get(mid, (None, "unresolved"))
        if o_addr is None:
            continue
        census["composed (any pass)"] += 1
        if how1 not in strong or how2 not in strong:
            continue
        census["composed (both hops strong)"] += 1
        if d_addr in t7_by_demo:
            key = "agrees with Task 7" if t7_by_demo[d_addr] == o_addr else "contradicts Task 7"
            census[key] += 1
            continue
        if o_addr in t7_by_our:
            census["contradicts Task 7"] += 1
            continue
        name = our_name.get(o_addr, "")
        if not (name.startswith("FUN_") or name.startswith("thunk_FUN_")):
            census["our row already named"] += 1
            continue
        census["new"] += 1
        accepted.append(Candidate(o_addr, d_addr, demo_name[d_addr], name, demo_size[d_addr],
                                  our_size.get(o_addr, 0), "%s+%s" % (how1, how2), 0))
    return accepted, census


# ---- the second proposals file ---------------------------------------------------------------

PROPOSAL_COLUMNS_7B = ["Address", "Current", "Proposed", "Mangled", "Source", "Tier",
                       "Discriminating", "DemoAddr", "DemoSize", "OurSize", "Ratio", "GapSize"]


def proposals_7b(candidates: Sequence[Tuple[str, Candidate]], taken: Sequence[str]):
    """(rows, held_back) for `game/demo_symbol_renames_7b.csv`.

    `candidates` is [(source, Candidate)] with `source` in ("positional", "bridge"); `taken` is every
    identifier Task 7's own proposals file already spends. The identifier hurdles are Task 7's,
    because the two files are applied to one CSV: a name the recompiler would see twice is two
    definitions of one C symbol whichever file proposed it.
    """
    from tools_py.ghidra_symbol_match import c_identifier

    held: Dict[str, int] = {}

    def hold(reason: str) -> None:
        held[reason] = held.get(reason, 0) + 1

    spelling: Dict[str, int] = {}
    for _source, cand in candidates:
        ident = c_identifier(cand.demo_name)
        spelling[ident] = spelling.get(ident, 0) + 1
    for ident in taken:
        spelling[ident] = spelling.get(ident, 0) + 1

    seen_addr = set()
    rows = []
    for source, cand in sorted(candidates, key=lambda sc: sc[1].our_addr):
        ident = c_identifier(cand.demo_name)
        if spelling[ident] > 1:
            hold("identifier already spent or collides")
            continue
        if cand.our_addr in seen_addr:
            hold("two proposals for one of our rows")
            continue
        seen_addr.add(cand.our_addr)
        rows.append({"Address": "0x%08x" % cand.our_addr, "Current": cand.our_name,
                     "Proposed": ident, "Mangled": cand.demo_name, "Source": source,
                     "Tier": cand.tier, "DemoAddr": "0x%08x" % cand.demo_addr,
                     "Discriminating": "yes" if cand.discriminating else "no",
                     "DemoSize": cand.demo_size, "OurSize": cand.our_size,
                     "Ratio": "%.2f" % cand.ratio, "GapSize": cand.gap})
    return rows, held


def write_proposals_7b(path: str, rows: Sequence[Dict], header: Sequence[str]) -> None:
    """The proposals file, its own rule stated in `#` lines above the column header."""
    import csv

    with open(path, "w", newline="") as fh:
        for line in header:
            fh.write("# %s\n" % line if line else "#\n")
        w = csv.DictWriter(fh, fieldnames=PROPOSAL_COLUMNS_7B)
        w.writeheader()
        for row in rows:
            w.writerow(row)
