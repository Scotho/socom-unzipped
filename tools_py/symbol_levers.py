"""Sprint 11 Task 7b: two more levers on the SOCOM 1 demo's names -- position, and a third build.

Task 7 (`tools_py/ghidra_symbol_match.py`, `docs/research/44-demo-symbols.md`) placed 987 of the SOCOM
1 demo's 9,703 named functions onto our anonymous SOCOM II rows and proposed 479 of them as renames.
Its ceiling is the fingerprint: 78 % of the demo's functions have no byte-identical counterpart in our
image at all, because SOCOM II is a year of edits later. This module adds the two levers a peer review
(socom-pc-6c's measurement, 2026-09-24) measured as worth building, each with its OWN acceptance rule
and its own proposals file. Neither ever touches `recomp/socom2_ghidra.csv`.

LEVER 1 -- POSITION BETWEEN ANCHORS (`positional`). Link order survives between the two games. Sorted
by our address, consecutive Task 7 pairs keep the demo's order 92-98 % of the time inside each of our
overlays. (The whole-image longest increasing subsequence is only 492/984, because the demo's single
PT_LOAD interleaves what we split into three overlays -- so the walk runs PER REGION, never over the
whole image.) Between two consecutive anchors that are in order on both sides, when both builds hold
the same number of unplaced functions, the i-th on one side is the i-th on the other. That is a
CORRESPONDENCE, not evidence, so every candidate then has to buy its name with a size ratio and a body
or prologue hash whose key is unique across the WHOLE image -- see `POSITIONAL_RULE` and `EVIDENCE`.

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
import csv
import os
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from tools_py import address_matcher as am
from tools_py.fingerprint import fingerprint
# Imported rather than re-spelt: `is_anonymous` decides which of our rows a rename may take over, and
# a second copy of that predicate here would let the levers drift from Task 7 the day the placeholder
# set grows. `ghidra_symbol_match` does not import this module at import time (only inside `main`),
# so there is no cycle. PREFIX_WORDS is the prologue window, so "the prologue" means one thing in both.
from tools_py.ghidra_symbol_match import PREFIX_WORDS, c_identifier, is_anonymous

JR_RA = 0x03E00008
JAL = 0x03

# -- lever 1's thresholds, and where each number comes from -----------------------------------
#
# SIZE_RATIO 0.5 -- neither body more than twice the other -- is MEASURED, not chosen. Task 7's 159
# prefix-pass pairs are the sample of "the same routine, edited between the two games". Their min/max
# size ratios, six lowest first, are 0.090, 0.299, 0.394, 0.409, 0.478, 0.487 -- so exactly those six
# are under 0.50, 153 of the 159 (96.2 %) clear it, and the lowest ratio the cut keeps is 0.506.
# `size_ratio_calibration` prints that distribution; `--size-ratio-calibration` runs it. (An earlier
# draft called 0.478 "the 5th percentile". It is the fifth lowest OBSERVATION; the 5th percentile by
# nearest rank is 0.557. The corrected reading argues for a slightly tighter cut, not a looser one:
# 0.55 would keep 152 of the 159 instead of 153.)
#
# MIN_BODY 64 bytes is note 44's own hurdle 2, applied here unchanged and to BOTH tiers. An earlier
# draft gave tier A a 32-byte floor on the argument that tier A's hash is stronger; the reason note 44
# gives for its hurdle -- the `Name` column becomes a C identifier AND an output filename, inherited by
# every later reader with no record that it was a guess -- does not care which rule proposed the row.
# Raising it to 64 costs the default file nothing (every row that clears EVIDENCE's top level is over
# 64 B anyway) and costs the two weaker levels five rows.
SIZE_RATIO = 0.5
MIN_BODY = 64

# How much the body evidence is worth, strongest first. The distinction is the whole of finding F1 of
# the Task 7b review, and it decides what reaches the file:
#
#   image-wide  the candidate's body key is worn by exactly one demo function AND one of our rows in
#               the whole image. Nothing but this candidate could have produced that key on either
#               side, so the body really has checked the positional guess.
#   gap-only    the key is unique among the candidate's own GAP siblings but not image-wide. The
#               twins fell in other gaps; position is still the only thing choosing between them, and
#               a reader of the file cannot tell that from the row.
#   no          not even unique inside the gap -- the `sceSifQuery*` wrapper families, whose masked
#               hashes are equal BY CONSTRUCTION because `fingerprint` zeroes the immediate that
#               distinguishes them.
#
# Only `image-wide` reaches the file by default. Note that tier A can essentially never reach it, and
# that is structural rather than a property of this data: a tier-A key that is unique on both sides at
# the same length is exactly `address_matcher`'s relinked-body acceptance condition, so Task 7 would
# already have placed the pair and it would be an anchor, not a candidate. Tier A exists only where
# the key is ambiguous -- which is the definition of not image-wide unique.
EVIDENCE = ("image-wide", "gap-only", "no")

# `positional`'s census carries a second, overlapping breakdown under this prefix: how many
# candidates cleared each tier at each evidence level. It exists so that the structural claim above
# -- that tier A can essentially never be image-wide -- is a number a command prints rather than a
# sentence in a note. Anything summing the census's exclusive buckets must skip these keys.
TIER_KEY_PREFIX = "tier "

# The default proposals path is reserved for rows that cleared `image-wide`. A run at a looser level
# writes beside it, at <name>_loose.csv, and `write_proposals_7b` REFUSES to put a `gap-only` or `no`
# row at the strict path. Without that, a looser file has the same name and the same columns as the
# strict one and a reader who does not reach column 7 cannot tell them apart -- which makes "behind
# the flag" a convention rather than a boundary.
LOOSE_MARK = "_loose"

POSITIONAL_RULE = (
    "positional: the i-th unplaced function between two consecutive Task 7 anchors that are in order "
    "on both sides and inside one PT_LOAD of ours, when both builds hold the same count in that gap. "
    "A correspondence is not evidence, so each candidate must also clear a body rule -- tier A: equal "
    "body length and equal address-masked fingerprint (address_matcher's own relinked-body test, "
    "which it refused only for want of a unique hash). Tier B: equal address-masked %d-instruction "
    "prologue hash and size ratio >= %.2f (six of Task 7's 159 prefix-pass pairs, which ARE the same "
    "routine after a year of edits, fall under 0.50; the lowest ratio this keeps is 0.506). Both "
    "tiers: body >= %d bytes, which is note 44's hurdle 2 unchanged. AND the body key must be unique "
    "IMAGE-WIDE -- worn by one demo function and one of our rows in the whole image, not merely by "
    "one per gap: where a key has peers elsewhere, position alone is choosing between them and the "
    "body has checked nothing. The KeyPeers column gives both counts; Evidence says which level the "
    "row cleared. Never overrides a Task 7 pair or a hand-chosen name; the identifier hurdles are "
    "Task 7's."
) % (PREFIX_WORDS, SIZE_RATIO, MIN_BODY)

POSITIONAL_CAVEAT = (
    "How wrong the walk can be was measured by holding out Task 7's own pairs and re-deriving them "
    "(--holdout 3 --holdout-block 8, a one-off run, not a suite test). READ ITS BIAS WITH ITS RESULT: "
    "a held-out pair is by construction a function Task 7 COULD match -- one that survived into SOCOM "
    "II nearly intact -- while the candidates this file is drawn from are the ones it could not. The "
    "holdout measures the walk, not this population, and every accuracy figure from it is an UPPER "
    "BOUND. It also cannot speak for the image-wide rule at all, since a held-out pair's key is "
    "usually image-wide unique by construction. See docs/research/45-positional-and-bridge-names.md."
)

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
    evidence: str = "image-wide"           # one of EVIDENCE; see the block comment above
    key_peers: Tuple[int, int] = (1, 1)    # (demo functions, our rows) image-wide wearing this key

    @property
    def ratio(self) -> float:
        hi = max(self.demo_size, self.our_size)
        return min(self.demo_size, self.our_size) / hi if hi else 0.0


def _anchor_rows(anchors) -> List[Tuple[int, int, str]]:
    """`anchors` as (demo_addr, our_addr, how), accepting the two-element form as how=""."""
    out = []
    for row in anchors:
        if len(row) > 2:
            out.append((int(row[0]), int(row[1]), str(row[2])))
        else:
            out.append((int(row[0]), int(row[1]), ""))
    return out


def anchors_from_details(details: Dict) -> List[Tuple[int, int, str]]:
    """Task 7's pairs as anchors, keyed by the DEMO ADDRESS `details` carries.

    Never by name: one demo name can sit on two demo addresses -- a C `static` compiled into two
    translation units -- and a name-keyed anchor would put one of those two pairs at the other's
    address, which is the one error a positional walk cannot survive.
    """
    return sorted((info["demo_addr"], addr, info["how"]) for (_n, addr), info in details.items())


def anchor_composition(anchors) -> Dict[str, int]:
    """{pass: count} over the anchor set -- what the gaps are actually anchored on.

    This exists because the answer depends on `--prefix`: with it the anchor set is 987 pairs of
    which 159 are PROLOGUE-only matches that note 44's hurdle 3 forbids from ever being proposed;
    without it, 828. Both are legitimate anchor sets -- a prologue unique on both sides is a fine
    position marker even when it is not proof of identity -- but they produce different files, so the
    composition is printed by the CLI and written into the proposals file's header.
    """
    out: Dict[str, int] = {}
    for _d, _o, how in _anchor_rows(anchors):
        out[how or "unknown"] = out.get(how or "unknown", 0) + 1
    return out


def proved_anchors(anchors) -> set:
    """The demo addresses of the anchors Task 7 PROVED -- i.e. not the prologue-only ones.

    `holdout` draws its held-out truth from these and from nothing else. Note 44 §2 hurdle 3 refuses
    to treat a prologue agreement as proof of identity, and tier B's own evidence is a prologue, so
    holding out a prefix pair and re-deriving it at tier B is a prologue confirming a prologue.
    """
    return {d for d, _o, how in _anchor_rows(anchors) if not how.startswith("prefix")}


# ---- a function table for an image with no symbols ------------------------------------------

def scan_functions(segments, jal_seed: bool = True, ptr_seed: bool = False) -> List[Tuple[int, int, str]]:
    """[(start, end, "sub_xxxxxxxx")] for a STRIPPED image, from its bytes alone.

    Three rules, in decreasing reliability:

      * what follows a `jr $ra` and its delay slot (past any zero padding) is a function start. On
        MIPS you cannot fall through a return, so this one is nearly exact and it does the work.
      * every `jal` target inside the image is a function start. This catches the first function of
        a run and keeps a leading data block out of it.
      * every 32-bit word in the image that points at an aligned address inside it -- a vtable or
        constructor-table entry. OFF by default: it is measured below to make the table WORSE.

    A range then runs to the next start, with trailing zero padding trimmed, and is dropped if it is
    under two instructions or contains no `jr $ra` at all (that is data, or a jump table).

    MEASURED LIMITS, by running this on the SOCOM 1 demo -- whose `.symtab` is the ground truth --
    with `jal_seed=True, ptr_seed=False`: 9,532 ranges against 9,703 real functions; 9,353 of the
    real functions get their start right (recall 96.4 %, precision 98.1 %), and 9,177 (94.6 %) get
    BOTH boundaries right and so fingerprint like the real thing. Turning `ptr_seed` on drops that to
    92.2 %: a vtable slot pointing into the middle of a function splits it. The 5 % whose extent is
    wrong cost RECALL, not correctness -- a wrongly cut body fingerprints like nothing else, and
    `am.match` needs equal length AND an equal masked hash, so a mis-bounded range can only suppress
    a match, never manufacture one (`BridgeSafetyTest` asserts this). A function that is never a
    `jal` target and never follows a return (reached only through a register, in the middle of a run)
    is invisible to this, and its bytes are absorbed by its predecessor, which spoils that one too.
    `scan_accuracy` is this paragraph as a measurement.

    The same three boundary rules are spelt again in `tools_py/find_interior_functions.py`, which
    cannot be reused because it is a script that wants a Ghidra CSV to compare against. That script
    also seeds on `lui`+`addiu`-formed addresses, which this does not try; whether that seed beats
    94.6 % is unmeasured.
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

def _prologue(side: am.Side, start: int, words: int = PREFIX_WORDS) -> Optional[str]:
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


def _body_key(side: am.Side, addr: int, tier: str, prologue_words: int = PREFIX_WORDS):
    """What the tier's body evidence actually sees of this function -- its discriminating power."""
    if tier == "A":
        return ("A", side.size.get(addr, 0), side.relfp(addr))
    return ("B", _prologue(side, addr, prologue_words))


def key_census(side: am.Side, tier: str, prologue_words: int = PREFIX_WORDS) -> Dict:
    """{body key: how many of this image's functions wear it} for one tier.

    The image-wide multiplicity finding F1 of the review asked for. Computed once per side per tier
    and handed to `_evidence`, because the alternative -- asking per candidate -- is 14,879 masked
    fingerprints per question.
    """
    out: Dict = {}
    for start in side.starts:
        key = _body_key(side, start, tier, prologue_words)
        out[key] = out.get(key, 0) + 1
    return out


def _tier(demo: am.Side, d_addr: int, ours: am.Side, o_addr: int,
          prologue_words: int = PREFIX_WORDS) -> Optional[str]:
    """"A", "B" or None -- which body rule, if either, this candidate clears.

    Both tiers carry `MIN_BODY`, which is note 44's hurdle 2 unchanged: the `Name` column becomes a C
    identifier and an output filename whichever rule proposed the row.
    """
    d_size, o_size = demo.size.get(d_addr, 0), ours.size.get(o_addr, 0)
    if not d_size or not o_size or d_size < MIN_BODY or o_size < MIN_BODY:
        return None
    if d_size == o_size:
        rel = demo.relfp(d_addr)
        if rel is not None and rel == ours.relfp(o_addr):
            return "A"
    if min(d_size, o_size) / max(d_size, o_size) >= SIZE_RATIO:
        pro = _prologue(demo, d_addr, prologue_words)
        if pro is not None and pro == _prologue(ours, o_addr, prologue_words):
            return "B"
    return None


def _slice(sorted_starts: Sequence[int], lo: int, hi: int) -> List[int]:
    """The starts strictly between `lo` and `hi`."""
    return list(sorted_starts[bisect.bisect_right(sorted_starts, lo):bisect.bisect_left(sorted_starts, hi)])


def anchor_gaps(anchors, our_starts: Sequence[int], demo_starts: Sequence[int],
                regions: Sequence[Tuple[int, int]], placed_ours: set,
                placed_demo: set) -> List[List[Tuple[int, int]]]:
    """[[(our_addr, demo_addr), ...], ...] -- one list per usable gap, before any body check.

    `anchors` is [(demo address, our address[, how])]. The walk is PER REGION because the demo's
    single PT_LOAD interleaves our three overlays: run over the whole image, consecutive pairs
    disagree with the demo's order often enough to make nonsense of the gaps (the whole-image longest
    increasing subsequence is 492 of 984, against 92-98 % agreement inside each region). Within a
    region, a gap is used only when its two anchors are in order on BOTH sides and both sides hold
    the same number of unplaced starts.

    The GROUPING is kept rather than flattened because the acceptance rule needs it: a candidate's
    nearest rivals are the other functions in its own gap, and `_evidence` asks first whether the
    body evidence can tell it from them and then whether it can tell it from the whole image.
    """
    out: List[List[Tuple[int, int]]] = []
    rows = [(o, d) for d, o, _h in _anchor_rows(anchors)]
    for lo, hi in regions:
        inside = sorted((o, d) for o, d in rows if lo <= o < hi)
        for (o1, d1), (o2, d2) in zip(inside, inside[1:]):
            if d2 <= d1:
                continue                                   # the pair is out of order: no gap here
            ours_in = [x for x in _slice(our_starts, o1, o2) if x not in placed_ours]
            demo_in = [x for x in _slice(demo_starts, d1, d2) if x not in placed_demo]
            if not ours_in or len(ours_in) != len(demo_in):
                continue
            out.append(list(zip(ours_in, demo_in)))
    return out


def _evidence(gap: Sequence[Tuple[int, int]], demo: am.Side, ours: am.Side, o_addr: int,
              d_addr: int, tier: str, census, prologue_words: int = PREFIX_WORDS):
    """(level, (demo peers, our peers)) -- how far the body evidence actually reaches.

    `census` is {"A": (demo counter, our counter), "B": (...)} from `key_census`.

    The two questions are different and the review's finding F1 is that only the second one supports
    the argument this hurdle is made of. The gap-local question -- can the body tell this candidate
    from its own gap siblings? -- catches the wrapper families (five `sceSifQuery*`, `stat`/`unlink`,
    `sceDmaSendN`/`sceDmaSendI`), whose masked hashes are equal by construction because `fingerprint`
    zeroes the immediate that distinguishes them. But the ARGUMENT for refusing them -- that a
    silently swapped `sceSifQueryMemSize` is a wrong name nobody ever catches -- is about the key
    being worn by more than one function, not about the twin happening to land in the same gap. On
    the real inputs 9 of the 16 rows an earlier draft accepted had a key with peers elsewhere in the
    image; `__ct__7CMatrixFv` is a 64-byte-rule-failing 40-byte body whose key 22 of our 14,879 rows
    wear. So the image-wide question is the one that decides the file.

    A cheaper strengthener was measured and does not work: `am.Side.anchors()` (the distinct strings
    a body forms the address of) rescues ZERO of the rows the image-wide rule refuses, because those
    bodies -- SDK thunks and tiny constructors -- reach no strings at all.
    """
    d_keys, o_keys = census[tier]
    d_key = _body_key(demo, d_addr, tier, prologue_words)
    o_key = _body_key(ours, o_addr, tier, prologue_words)
    peers = (d_keys.get(d_key, 0), o_keys.get(o_key, 0))
    for o_other, d_other in gap:
        if d_other != d_addr and _body_key(demo, d_other, tier, prologue_words) == d_key:
            return "no", peers
        if o_other != o_addr and _body_key(ours, o_other, tier, prologue_words) == o_key:
            return "no", peers
    return ("image-wide" if peers == (1, 1) else "gap-only"), peers


def positional(demo_funcs, demo_segments, our_funcs, our_segments, anchors,
               prologue_words: int = PREFIX_WORDS, regions=None,
               min_evidence: str = "image-wide"):
    """(accepted, census) -- lever 1.

    `anchors` is [(demo_addr, our_addr[, how])] for every Task 7 pair; those are the anchors AND the
    rows a candidate may never take. `accepted` is [Candidate]; `census` counts every stage so the
    note's numbers have a source.

    `min_evidence` is the one JUDGEMENT in this rule rather than a measurement, so it is a knob and
    its default is the strictest level:

      "image-wide"  the body key is worn by one demo function and one of our rows in the whole image.
      "gap-only"    ...or merely by one per gap: the twins exist, they just fell elsewhere. Position
                    alone is choosing, and a reader of the file cannot see that from the row.
      "any"         ...or not even that: the wrapper families. Their name rests on link order alone.
                    That order is source order and a reordering is unlikely, but a silently swapped
                    `sceSifQueryMemSize` is the kind of wrong name nobody ever catches, and the
                    holdout has caught `gap-only` being wrong where it has never caught
                    `image-wide`. The counts move with every run, so they are not typed here:
                    `--holdout` prints them and docs/research/45 sec 3 quotes them with the command.

    Every accepted row carries the level it cleared and its image-wide peer counts, so a file written
    at a looser level says so row by row as well as in its header -- and `write_proposals_7b` refuses
    to put such a row at the strict default path at all, so the flag is a boundary and not a
    convention.

    `census` also carries a `tier <A|B> x <level>` breakdown, because the claim in `EVIDENCE` that
    tier A can essentially never be image-wide is a measurement and should read as one.
    """
    if min_evidence not in ("image-wide", "gap-only", "any"):
        raise ValueError("min_evidence is image-wide, gap-only or any, not %r" % (min_evidence,))
    allowed = {"image-wide": ("image-wide",),
               "gap-only": ("image-wide", "gap-only"),
               "any": EVIDENCE}[min_evidence]

    demo = am.Side(demo_funcs, demo_segments)
    ours = am.Side(our_funcs, our_segments)
    if regions is None:
        regions = [(v, v + len(d)) for v, d in ours.image.segments]
    rows = _anchor_rows(anchors)
    placed_demo = {d for d, _o, _h in rows}
    placed_ours = {o for _d, o, _h in rows}
    gaps = anchor_gaps(rows, sorted(ours.starts), sorted(demo.starts), regions,
                       placed_ours, placed_demo)
    census = {t: (key_census(demo, t, prologue_words), key_census(ours, t, prologue_words))
              for t in ("A", "B")}

    # Buckets that SUM to `candidates`, whatever `min_evidence` is: a candidate is counted once, by
    # the level it reached and whether that level was admitted. The `tier ... x ...` keys below are a
    # SECOND, independent breakdown of the same candidates and are excluded from that sum by their
    # prefix -- `TIER_KEY_PREFIX` is what the CLI and the tests filter on.
    counts = {"anchors": len(rows), "gaps": len(gaps), "candidates": sum(len(g) for g in gaps),
              "no body evidence": 0, "our row already named": 0}
    for level in EVIDENCE:
        counts["evidence %s: taken" % level] = 0
        counts["evidence %s: refused" % level] = 0
    for tier_name in ("A", "B"):
        for level in EVIDENCE:
            counts["%s%s x %s" % (TIER_KEY_PREFIX, tier_name, level)] = 0
    accepted: List[Candidate] = []
    for gap in gaps:
        for o_addr, d_addr in gap:
            tier = _tier(demo, d_addr, ours, o_addr, prologue_words)
            if tier is None:
                counts["no body evidence"] += 1
                continue
            level, peers = _evidence(gap, demo, ours, o_addr, d_addr, tier, census, prologue_words)
            counts["%s%s x %s" % (TIER_KEY_PREFIX, tier, level)] += 1
            if level not in allowed:
                counts["evidence %s: refused" % level] += 1
                continue
            our_name = ours.name.get(o_addr, "")
            if not is_anonymous(our_name):
                counts["our row already named"] += 1
                continue
            counts["evidence %s: taken" % level] += 1
            accepted.append(Candidate(o_addr, d_addr, demo.name[d_addr], our_name,
                                      demo.size[d_addr], ours.size[o_addr], tier, len(gap),
                                      level, peers))
    return accepted, counts


def size_ratio_calibration(details: Dict, our_funcs) -> Dict:
    """The distribution `SIZE_RATIO` is calibrated on, as a measurement rather than a comment.

    `details` is `ghidra_symbol_match.match`'s out-parameter. The prefix-pass pairs are the sample:
    a prologue unique on both sides says "the same routine, edited", which is precisely the
    population a positional candidate is drawn from, and their size ratios are what a real edit does
    to a body length. Reproduced by `--size-ratio-calibration`; pinned by `SizeRatioTest`.
    """
    our_size = {s: e - s for s, e, _n in our_funcs}
    ratios = []
    for (_name, addr), info in details.items():
        if not str(info.get("how", "")).startswith("prefix"):
            continue
        d, o = int(info.get("size", 0)), our_size.get(addr, 0)
        if d and o:
            ratios.append(round(min(d, o) / max(d, o), 4))
    ratios.sort()
    kept = [r for r in ratios if r >= SIZE_RATIO]
    return {"pairs": len(ratios), "six lowest": ratios[:6], "cut": SIZE_RATIO,
            "kept": len(kept), "lowest kept": kept[0] if kept else None,
            "percent kept": round(100 * len(kept) / len(ratios), 1) if ratios else 0.0}


def holdout(demo_funcs, demo_segments, our_funcs, our_segments, anchors,
            prologue_words: int = PREFIX_WORDS, folds: int = 3, regions=None, block: int = 1,
            holdable=None):
    """{level: (re-derived, of those wrong)} -- lever 1's error rate, measured on known answers.

    Hold out every k-th Task 7 pair, run the walk with the rest as anchors, and check the held-out
    rows against the answer Task 7 already proved. This is the only honest way to put a number on
    "position implies identity", and it is why the rule above is tiered rather than flat.

    `holdable` is the set of demo addresses eligible to be held out, and the CLI passes
    `proved_anchors(anchors)` -- the 828 pairs Task 7 PROVED. Note 44 hurdle 3 refuses to treat a
    prologue agreement as proof of identity, and tier B's own evidence is a prologue, so holding out
    a prefix pair and re-deriving it at tier B is a prologue confirming a prologue. Pass None to hold
    out everything and get the looser figure the first draft of this module reported.

    `block` holds out RUNS of that many consecutive pairs instead of single ones. It exists because
    `block=1` produces gaps that hold one held-out function each, and a gap of one is gap-unique by
    definition -- so a single-pair holdout never exercises the `no` level at all and says little
    about the multi-function gaps the real run scores.

    TWO BIASES, both one-directional, both to be read with the result. A held-out pair is by
    construction a function Task 7 COULD match, i.e. one that survived into SOCOM II nearly intact,
    where the candidates the real run scores are the ones it could not -- so this is an UPPER BOUND.
    And a held-out pair's body key is usually image-wide unique by construction (that is often WHY
    Task 7 matched it), so the holdout can barely speak for the image-wide rule at all: it measures
    the positional walk and the tiers, not the hurdle that decides the file.
    """
    demo = am.Side(demo_funcs, demo_segments)
    ours = am.Side(our_funcs, our_segments)
    if regions is None:
        regions = [(v, v + len(d)) for v, d in ours.image.segments]
    our_starts, demo_starts = sorted(ours.starts), sorted(demo.starts)
    rows = _anchor_rows(anchors)
    pp = sorted((o, d) for d, o, _h in rows)
    truth = dict(pp)
    all_ours, all_demo = {o for o, _d in pp}, {d for _o, d in pp}
    census = {t: (key_census(demo, t, prologue_words), key_census(ours, t, prologue_words))
              for t in ("A", "B")}
    eligible = [i for i, (_o, d) in enumerate(pp) if holdable is None or d in holdable]

    out: Dict[str, List[int]] = {k: [0, 0] for k in EVIDENCE + ("untiered",)}
    block = max(1, int(block))
    for phase in range(folds):
        hold_i = {eligible[j] for j in range(len(eligible)) if (j // block) % folds == phase}
        held = [pp[i] for i in sorted(hold_i)]
        keep = [(d, o, "") for i, (o, d) in enumerate(pp) if i not in hold_i]
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
                else:
                    bucket, _peers = _evidence(gap, demo, ours, o_addr, d_addr, tier, census,
                                               prologue_words)
                out[bucket][0] += 1
                out[bucket][1] += int(wrong)
    return {k: tuple(v) for k, v in out.items()}


# ---- lever 2: the bridge through the stripped SOCOM II demo ----------------------------------

STRONG_HOPS = ("exact", "relinked-body")


def bridge(demo_funcs, demo_segments, demo2_funcs, demo2_segments, our_funcs, our_segments,
           anchors, strong=STRONG_HOPS):
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
    rows = _anchor_rows(anchors)
    # Keyed by demo address on one side and our address on the other, as SETS of pairs rather than a
    # dict either way: a dict() over the demo address would silently drop the second of two anchors
    # sharing one (the `_request_end` shape), and the contradiction test is the last place to blur it.
    t7_by_demo: Dict[int, set] = {}
    t7_by_our: Dict[int, set] = {}
    for d, o, _h in rows:
        t7_by_demo.setdefault(d, set()).add(o)
        t7_by_our.setdefault(o, set()).add(d)

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
            key = "agrees with Task 7" if o_addr in t7_by_demo[d_addr] else "contradicts Task 7"
            census[key] += 1
            continue
        if o_addr in t7_by_our:
            census["contradicts Task 7"] += 1
            continue
        name = our_name.get(o_addr, "")
        if not is_anonymous(name):
            census["our row already named"] += 1
            continue
        census["new"] += 1
        accepted.append(Candidate(o_addr, d_addr, demo_name[d_addr], name, demo_size[d_addr],
                                  our_size.get(o_addr, 0), "%s+%s" % (how1, how2), 0))
    return accepted, census


# ---- the second proposals file ---------------------------------------------------------------

PROPOSAL_COLUMNS_7B = ["Address", "Current", "Proposed", "Mangled", "Source", "Tier",
                       "Evidence", "KeyPeers", "DemoAddr", "DemoSize", "OurSize", "Ratio",
                       "GapSize"]


def proposals_7b(candidates: Sequence[Tuple[str, Candidate]], taken: Sequence[str]):
    """(rows, held_back) for `game/demo_symbol_renames_7b.csv`.

    `candidates` is [(source, Candidate)] with `source` in ("positional", "bridge"); `taken` is every
    identifier Task 7's own proposals file already spends. The identifier hurdles are Task 7's,
    because the two files are applied to one CSV: a name the recompiler would see twice is two
    definitions of one C symbol whichever file proposed it.

    Known gap, inherited from `ghidra_symbol_match.proposals` and not fixed here because fixing it in
    one of the two would be worse than in neither: neither file checks its proposed identifier
    against the 113 names already in `recomp/socom2_ghidra.csv`'s own `Name` column. None of the rows
    this produces collides today. Whatever APPLIES either file is the right place for that check.
    """
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
                     "Tier": cand.tier, "Evidence": cand.evidence,
                     "KeyPeers": "%d/%d" % cand.key_peers,
                     "DemoAddr": "0x%08x" % cand.demo_addr,
                     "DemoSize": cand.demo_size, "OurSize": cand.our_size,
                     "Ratio": "%.2f" % cand.ratio, "GapSize": cand.gap})
    return rows, held


def loose_path(path: str) -> str:
    """`path` with `_loose` before its extension -- where a below-`image-wide` run writes."""
    root, ext = os.path.splitext(path)
    return path if root.endswith(LOOSE_MARK) else root + LOOSE_MARK + ext


def is_loose_path(path: str) -> bool:
    return os.path.splitext(path)[0].endswith(LOOSE_MARK)


def write_proposals_7b(path: str, rows: Sequence[Dict], header: Sequence[str]) -> None:
    """The proposals file, its own rule stated in `#` lines above the column header.

    Two refusals, both `ValueError` so that `main` can turn them into one `NO-DATA:` line: a bad
    output path is one sentence rather than a traceback, and a row that did not clear `image-wide`
    may not be written to the strict default path. The second is the boundary `LOOSE_MARK` describes
    -- enforced here, at the write, rather than only in the CLI that happens to call it.
    """
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise ValueError("cannot write %s: %s is not a directory" % (path, directory))
    if not is_loose_path(path):
        loose = sorted({r.get("Evidence", "") for r in rows} - {"image-wide", ""})
        if loose:
            raise ValueError(
                "cannot write %s: %d row(s) at evidence %s belong at %s, not at the strict path"
                % (path, sum(1 for r in rows if r.get("Evidence") in loose), ", ".join(loose),
                   loose_path(path)))
    with open(path, "w", newline="") as fh:
        for line in header:
            fh.write("# %s\n" % line if line else "#\n")
        w = csv.DictWriter(fh, fieldnames=PROPOSAL_COLUMNS_7B)
        w.writeheader()
        for row in rows:
            w.writerow(row)
