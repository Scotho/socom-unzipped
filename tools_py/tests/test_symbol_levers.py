"""Sprint 11 Task 7b -- the two levers on the demo's names (tools_py/symbol_levers).

The fixture is three little images of hand-assembled MIPS: the SOCOM 1 demo, the stripped SOCOM II
demo, and ours. Each holds the same routines at a different base, over a different global. Two shapes
carry the tests:

  * an EDITED routine -- the same sixteen-instruction prologue in both images with a different tail,
    so no pass of `address_matcher` can see it and only lever 1's tier B can. Its prologue hash is
    unique image-wide, so it is the only shape that reaches the default proposals file at all.
  * TWINS -- two routines whose bodies differ only in which global they touch, so their masked
    fingerprints are equal. The matcher cannot choose between them, and neither can the body
    evidence: they are what `image-wide` refuses and `gap-only`/`any` admit.

No disc, no demo, no ELF on disk.
"""
import csv
import io
import os
import tempfile
import unittest

from tools_py import address_matcher as am
from tools_py import ghidra_symbol_match as gsm
from tools_py import symbol_levers as sl


# ---- the same tiny assembler the Task 7 and Task 10 suites use ------------------------------

def lui(rt, imm):        return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)
def addiu(rt, rs, imm):  return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def lw(rt, base, imm):   return (0x23 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def sw(rt, base, imm):   return (0x2B << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def addu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21
def subu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x23
def xor(rd, rs, rt):     return (rs << 21) | (rt << 16) | (rd << 11) | 0x26
def mult(rs, rt):        return (rs << 21) | (rt << 16) | 0x18
def jal(target):         return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)
def jr_ra():             return (31 << 21) | 8
NOP = 0

AT, V0, A0, A1, S0, T0 = 1, 2, 4, 5, 16, 8
SIZE = 0x40                       # sixteen words -- the prologue window, and MIN_BODY exactly


def _blob(words):
    return b"".join((w & 0xFFFFFFFF).to_bytes(4, "little") for w in words)


def _fill(words, size=SIZE):
    """`words`, padded with arithmetic (never NOPs) to `size` bytes and ended `jr $ra; nop`."""
    out = list(words)
    while len(out) < size // 4 - 2:
        out.append(addu(T0, T0, V0))
    return out[:size // 4 - 2] + [jr_ra(), NOP]


def anchor_body(salt):
    """Pure register arithmetic: not one bit of this moves between links, so it matches `exact`."""
    return _fill([addu(V0, A0, A1), subu(V0, V0, A0), xor(A1, V0, A0), mult(V0, A1 + salt % 3),
                  addu(V0, V0, A1), subu(A0, A1, V0), xor(S0, S0, A0 + salt % 5),
                  addu(T0, T0, V0 + salt % 7), subu(V0, T0, S0), mult(S0, T0 + salt % 11)])


def twin_body(global_addr):
    """A load and a store THROUGH a global: the displacement is half an address.

    Two twins over DIFFERENT globals have different plain fingerprints (the displacement is kept)
    and the same MASKED one (the displacement is blanked). So `exact` cannot see them and the
    relinked-body pass sees two candidates it cannot separate -- which leaves them for position, and
    leaves position with no body evidence that can tell one from the other.
    """
    hi, lo = ((global_addr + 0x8000) >> 16) & 0xFFFF, global_addr & 0xFFFF
    return _fill([lui(AT, hi), lw(V0, AT, lo), addiu(V0, V0, 1), lui(AT, hi), sw(V0, AT, lo),
                  lw(T0, A0, 0x18), addu(V0, V0, T0), subu(S0, V0, T0)])


PROLOGUE = [addu(V0, A0, A1), mult(A0, A1), subu(S0, A1, A0), xor(T0, S0, V0),
            addu(A0, T0, S0), subu(V0, A0, T0), mult(S0, V0), xor(A1, A1, T0),
            addu(T0, A1, V0), subu(S0, T0, A1), mult(A0, S0), xor(V0, S0, A0),
            addu(A1, V0, S0), subu(T0, A1, V0), mult(V0, T0), xor(S0, T0, A1)]


def edited_body(tail_words):
    """The shared 16-instruction prologue plus `tail_words` words of a DIFFERENT tail.

    This is the only shape that reaches the default proposals file: its prologue agrees masked, its
    body does not, and nothing else in either image wears that prologue hash. Tier A is unreachable
    for it (the lengths differ), which is the point -- see `symbol_levers.EVIDENCE` on why tier A can
    essentially never be image-wide unique.
    """
    tail = [addu(V0, V0, A0 + (i % 4)) for i in range(max(0, tail_words - 2))]
    return list(PROLOGUE) + tail + [jr_ra(), NOP]


LAYOUT = ["anchor0", "edited", "anchor1", "twinA", "anchor2", "twinB", "anchor3"]


def image(base, g0, g1, edit_tail, names=None, extra=None, split=None, merge=None, swap=None):
    """(rows, [(base, blob)]) for one build -- ONE segment, as a real PT_LOAD is.

    `extra` inserts an unmatched function after `twinB`; `swap` exchanges two functions' POSITIONS,
    which is how a second link can reorder what the fingerprint still pairs correctly; `split` names
    a function whose ROW is cut in two without its bytes changing, and `merge` one whose row swallows
    its successor. The last two change the table, never the image -- exactly as a Ghidra boundary
    quirk does.
    """
    order = list(LAYOUT)
    if extra:
        order.insert(order.index("twinB") + 1, extra)
    if swap:
        i, j = order.index(swap[0]), order.index(swap[1])
        order[i], order[j] = order[j], order[i]
    bodies = {"anchor0": anchor_body(0), "anchor1": anchor_body(1), "anchor2": anchor_body(2),
              "anchor3": anchor_body(3), "edited": edited_body(edit_tail),
              "twinA": twin_body(g0), "twinB": twin_body(g1)}
    if extra:
        bodies[extra] = anchor_body(9)

    spans, blob, cursor = [], b"", base
    for name in order:
        part = _blob(bodies[name])
        spans.append((name, cursor, cursor + len(part)))
        blob += part
        cursor += len(part)

    rows, i = [], 0
    while i < len(spans):
        name, start, end = spans[i]
        label = (names or {}).get(name, name)
        if name == split:
            half = start + ((end - start) // 8) * 4
            rows.append((start, half, label + "_lo"))
            rows.append((half, end, label + "_hi"))
        elif name == merge and i + 1 < len(spans):
            rows.append((start, spans[i + 1][2], label))
            i += 1
        else:
            rows.append((start, end, label))
        i += 1
    return rows, [(base, blob)]


DEMO_BASE, OUR_BASE, DEMO2_BASE = 0x00140000, 0x00280000, 0x00200000


def demo_side(**kw):
    return image(DEMO_BASE, 0x00500120, 0x00500220, 6, **kw)


def our_side(edit_tail=10, **kw):
    """A second link: different base, different globals, and `edited` grown by a longer tail."""
    names = {n: "FUN_%s" % n for n in LAYOUT + ["extra"]}
    return image(OUR_BASE, 0x00610a00, 0x00610b00, edit_tail, names=names, **kw)


def demo2_side(**kw):
    return image(DEMO2_BASE, 0x00570040, 0x00570140, 6,
                 names={n: "sub_%s" % n for n in LAYOUT + ["extra"]}, **kw)


def task7_anchors(demo_rows, demo_segs, our_rows, our_segs):
    """[(demo_addr, our_addr, how)] -- what `ghidra_symbol_match.match` proves on this fixture."""
    details = {}
    gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details)
    return sl.anchors_from_details(details)


class FixtureTest(unittest.TestCase):
    """The fixture only tests what it claims if the matcher really cannot place the candidates."""

    def test_the_matcher_places_the_anchors_and_nothing_else(self):
        demo_rows, demo_segs = demo_side()
        our_rows, our_segs = our_side()
        placed = task7_anchors(demo_rows, demo_segs, our_rows, our_segs)
        self.assertEqual(len(placed), 4)
        loose = {r[0] for r in demo_rows if not r[2].startswith("anchor")}
        self.assertFalse(loose & {d for d, _o, _h in placed},
                         "edited and the twins must be unplaced, or lever 1 has nothing to do")

    def test_the_edited_pair_is_over_min_body_on_both_sides(self):
        demo_rows, _ = demo_side()
        our_rows, _ = our_side()
        d = next(e - s for s, e, n in demo_rows if n == "edited")
        o = next(e - s for s, e, n in our_rows if n == "FUN_edited")
        self.assertGreaterEqual(min(d, o), sl.MIN_BODY)
        self.assertNotEqual(d, o)                          # so tier A cannot apply


class PositionalTest(unittest.TestCase):
    def setUp(self):
        self.demo_rows, self.demo_segs = demo_side()
        self.our_rows, self.our_segs = our_side()
        self.anchors = task7_anchors(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs)

    def run_lever(self, our_rows=None, our_segs=None, anchors=None, **kw):
        return sl.positional(self.demo_rows, self.demo_segs,
                             our_rows if our_rows is not None else self.our_rows,
                             our_segs if our_segs is not None else self.our_segs,
                             self.anchors if anchors is None else anchors,
                             gsm.PREFIX_WORDS, **kw)

    def test_a_gap_that_lines_up_names_its_function(self):
        found, census = self.run_lever()
        self.assertEqual(census["candidates"], 3)          # edited, twinA, twinB
        self.assertEqual([c.demo_name for c in found], ["edited"])
        self.assertEqual(found[0].tier, "B")
        self.assertEqual(found[0].evidence, "image-wide")
        self.assertEqual(found[0].key_peers, (1, 1))
        self.assertEqual(found[0].our_addr,
                         next(s for s, _e, n in self.our_rows if n == "FUN_edited"))

    def test_a_gap_that_does_not_line_up_names_nothing_from_that_gap(self):
        our_rows, our_segs = our_side(extra="extra")
        anchors = task7_anchors(self.demo_rows, self.demo_segs, our_rows, our_segs)
        found, census = self.run_lever(our_rows, our_segs, anchors)
        # `extra` sits between twinB and anchor3, so that gap holds two of ours against the demo's
        # one and is refused whole. The `edited` gap is untouched: the rule is per gap, not per image.
        self.assertEqual(census["candidates"], 2)
        self.assertEqual([c.demo_name for c in found], ["edited"])

    def test_it_never_takes_a_row_we_named_by_hand(self):
        target = next(s for s, _e, n in self.our_rows if n == "FUN_edited")
        our_rows = [(s, e, "CZSealBody_Tick" if s == target else n) for s, e, n in self.our_rows]
        found, census = self.run_lever(our_rows, self.our_segs)
        self.assertEqual(census["our row already named"], 1)
        self.assertEqual(found, [])

    def test_it_never_takes_a_row_task_7_already_paired(self):
        found, _census = self.run_lever()
        self.assertFalse({o for _d, o, _h in self.anchors} & {c.our_addr for c in found})

    def test_anchors_out_of_order_on_the_demo_side_make_no_gap(self):
        flipped = [(d, o, "exact") for d, o in
                   zip(sorted(d for d, _o, _h in self.anchors)[::-1],
                       sorted(o for _d, o, _h in self.anchors))]
        _found, census = self.run_lever(anchors=flipped)
        self.assertEqual(census["candidates"], 0)

    def test_a_gap_in_another_pt_load_of_ours_is_not_walked_into(self):
        regions = [(s, e) for s, e, _n in self.our_rows]
        _found, census = self.run_lever(regions=regions)
        self.assertEqual(census["candidates"], 0)

    def test_the_census_buckets_sum_to_the_candidates_at_every_level(self):
        for level in ("image-wide", "gap-only", "any"):
            _found, census = self.run_lever(min_evidence=level)
            total = census["no body evidence"] + census["our row already named"]
            for name in sl.EVIDENCE:
                total += census["evidence %s: taken" % name]
                total += census["evidence %s: refused" % name]
            self.assertEqual(total, census["candidates"], level)

    def test_an_unknown_evidence_level_is_refused(self):
        with self.assertRaises(ValueError):
            self.run_lever(min_evidence="whatever")


class EvidenceLevelTest(unittest.TestCase):
    """The twins wear one body key between them, so the image-wide rule is what decides them."""

    def setUp(self):
        self.demo_rows, self.demo_segs = demo_side()
        self.our_rows, self.our_segs = our_side()
        self.anchors = task7_anchors(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs)

    def run_lever(self, level):
        return sl.positional(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs,
                             self.anchors, gsm.PREFIX_WORDS, min_evidence=level)

    def test_a_key_with_peers_elsewhere_in_the_image_is_refused_by_default(self):
        found, census = self.run_lever("image-wide")
        self.assertEqual(census["evidence gap-only: refused"], 2)     # twinA and twinB
        self.assertEqual({c.demo_name for c in found}, {"edited"})

    def test_gap_only_admits_them_and_the_row_says_so(self):
        found, census = self.run_lever("gap-only")
        self.assertEqual(census["evidence gap-only: taken"], 2)
        twins = [c for c in found if c.demo_name.startswith("twin")]
        self.assertEqual({c.evidence for c in twins}, {"gap-only"})
        self.assertEqual({c.key_peers for c in twins}, {(2, 2)})
        rows, _held = sl.proposals_7b([("positional", c) for c in twins], [])
        self.assertEqual({r["Evidence"] for r in rows}, {"gap-only"})
        self.assertEqual({r["KeyPeers"] for r in rows}, {"2/2"})

    def test_the_twins_really_are_paired_the_right_way_round(self):
        found, _census = self.run_lever("gap-only")
        by_name = {c.demo_name: c.our_addr for c in found}
        for name in ("twinA", "twinB"):
            self.assertEqual(by_name[name], next(s for s, _e, n in self.our_rows
                                                 if n == "FUN_" + name))


class GapLocalTest(unittest.TestCase):
    """Two twins in ONE gap: the body cannot tell them apart even locally -- the `no` level."""

    def setUp(self):
        def build(base, g, names):
            rows, blob, cursor = [], b"", base
            for i, body in enumerate([anchor_body(0), twin_body(g), twin_body(g), anchor_body(1)]):
                part = _blob(body)
                rows.append((cursor, cursor + len(part), names[i]))
                blob += part
                cursor += len(part)
            return rows, [(base, blob)]
        self.demo_rows, self.demo_segs = build(
            DEMO_BASE, 0x00500120, ["anchor0", "sceSifQueryMemSize", "sceSifQueryBlockSize", "a1"])
        self.our_rows, self.our_segs = build(
            OUR_BASE, 0x00610a00, ["FUN_a0", "FUN_t0", "FUN_t1", "FUN_a1"])
        self.anchors = task7_anchors(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs)

    def run_lever(self, level):
        return sl.positional(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs,
                             self.anchors, gsm.PREFIX_WORDS, min_evidence=level)

    def test_siblings_the_body_cannot_separate_are_refused_below_any(self):
        for level in ("image-wide", "gap-only"):
            found, census = self.run_lever(level)
            self.assertEqual(census["candidates"], 2)
            self.assertEqual(census["evidence no: refused"], 2, level)
            self.assertEqual(found, [], level)

    def test_any_admits_them_and_says_so_in_the_row(self):
        found, _census = self.run_lever("any")
        self.assertEqual(len(found), 2)
        self.assertEqual({c.evidence for c in found}, {"no"})
        rows, _held = sl.proposals_7b([("positional", c) for c in found], [])
        self.assertEqual({r["Evidence"] for r in rows}, {"no"})


class TierTest(unittest.TestCase):
    def setUp(self):
        self.demo = am.Side(*demo_side())
        self.ours = am.Side(*our_side())
        self.d = {n: s for s, _e, n in demo_side()[0]}
        self.o = {n: s for s, _e, n in our_side()[0]}

    def test_tier_a_is_equal_length_and_equal_masked_fingerprint(self):
        self.assertEqual(sl._tier(self.demo, self.d["twinA"], self.ours, self.o["FUN_twinA"]), "A")

    def test_tier_b_is_the_prologue_when_the_lengths_differ(self):
        self.assertEqual(sl._tier(self.demo, self.d["edited"], self.ours, self.o["FUN_edited"]), "B")

    def test_tier_b_refuses_a_size_ratio_under_the_cut(self):
        # Same prologue, a tail long enough to put the ratio under SIZE_RATIO. 0.63 accepts, 0.49
        # does not: this is the rule the loosest row of the real proposals file rests on.
        demo_rows, demo_segs = demo_side()
        demo = am.Side(demo_rows, demo_segs)
        d_addr = self.d["edited"]
        d_size = demo.size[d_addr]
        for our_tail, expect in ((round(d_size * 0.63 / 4) - 16, "B"),
                                 (round(d_size / 0.49 / 4) - 16, None)):
            rows, segs = our_side(edit_tail=max(3, our_tail))
            ours = am.Side(rows, segs)
            o_addr = next(s for s, _e, n in rows if n == "FUN_edited")
            got = sl._tier(demo, d_addr, ours, o_addr)
            ratio = min(d_size, ours.size[o_addr]) / max(d_size, ours.size[o_addr])
            self.assertEqual(got, expect, "ratio %.2f" % ratio)
            self.assertEqual(ratio >= sl.SIZE_RATIO, expect is not None)

    def test_a_body_under_min_body_clears_no_tier(self):
        short = _blob([lui(AT, 1), lw(V0, AT, 4), jr_ra(), NOP])       # sixteen bytes
        side = am.Side([(0x300000, 0x300010, "tiny")], [(0x300000, short)])
        side2 = am.Side([(0x400000, 0x400010, "FUN_00400000")], [(0x400000, short)])
        self.assertLess(0x10, sl.MIN_BODY)
        self.assertIsNone(sl._tier(side, 0x300000, side2, 0x400000))

    def test_unrelated_bodies_clear_no_tier(self):
        self.assertIsNone(sl._tier(self.demo, self.d["anchor0"], self.ours, self.o["FUN_twinA"]))

    def test_the_size_ratio_is_the_smaller_over_the_larger(self):
        c = sl.Candidate(1, 2, "n", "FUN_x", 100, 200, "B", 3)
        self.assertEqual(c.ratio, 0.5)
        self.assertEqual(sl.Candidate(1, 2, "n", "FUN_x", 0, 0, None, 0).ratio, 0.0)

    def test_the_key_census_counts_every_function_once(self):
        census = sl.key_census(self.demo, "A")
        self.assertEqual(sum(census.values()), len(self.demo.starts))
        twin_key = sl._body_key(self.demo, self.d["twinA"], "A")
        self.assertEqual(census[twin_key], 2, "the two twins share one tier-A key")


class SizeRatioTest(unittest.TestCase):
    def test_the_calibration_reports_the_distribution_the_cut_rests_on(self):
        details = {("a", 0x100): {"how": "prefix", "size": 100},
                   ("b", 0x200): {"how": "prefix+size", "size": 100},
                   ("c", 0x300): {"how": "exact", "size": 100}}
        our = [(0x100, 0x100 + 40, "FUN_a"), (0x200, 0x200 + 100, "FUN_b"),
               (0x300, 0x300 + 10, "FUN_c")]
        cal = sl.size_ratio_calibration(details, our)
        self.assertEqual(cal["pairs"], 2)                  # the exact pair is not in the sample
        self.assertEqual(cal["six lowest"], [0.4, 1.0])
        self.assertEqual(cal["kept"], 1)
        self.assertEqual(cal["lowest kept"], 1.0)
        self.assertEqual(cal["cut"], sl.SIZE_RATIO)


class HoldoutTest(unittest.TestCase):
    def setUp(self):
        self.demo_rows, self.demo_segs = demo_side()
        self.our_rows, self.our_segs = our_side()
        self.anchors = task7_anchors(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs)

    def test_it_re_derives_a_held_out_pair_and_calls_it_right(self):
        got = sl.holdout(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs,
                         self.anchors, gsm.PREFIX_WORDS, folds=2)
        tried = sum(n for n, _bad in got.values())
        self.assertGreater(tried, 0, "the holdout must actually re-derive something")
        self.assertEqual(sum(bad for _n, bad in got.values()), 0)

    def test_the_wrong_counter_counts(self):
        """Two functions RELINKED out of order: position re-derives both the wrong way round.

        Without this the holdout could report zero errors because it never detects one. `exact`
        pairs by fingerprint and does not care where a routine sits, so our link order really can
        differ from the demo's -- and that is precisely the shift a positional walk cannot see and
        the holdout exists to count.
        """
        demo_rows, demo_segs = demo_side()
        our_rows, our_segs = our_side(swap=("anchor1", "anchor2"))
        anchors = task7_anchors(demo_rows, demo_segs, our_rows, our_segs)
        demo_at = {n: s for s, _e, n in demo_rows}
        held = {demo_at["anchor1"], demo_at["anchor2"]}
        got = sl.holdout(demo_rows, demo_segs, our_rows, our_segs, anchors, gsm.PREFIX_WORDS,
                         folds=1, block=2, holdable=held)
        self.assertEqual(sum(n for n, _bad in got.values()), 2)
        self.assertEqual(sum(bad for _n, bad in got.values()), 2)
        self.assertEqual(got["untiered"], (2, 2), "two different bodies clear no tier")

    def test_holdable_restricts_what_may_be_held_out(self):
        one = {self.anchors[0][0]}
        got = sl.holdout(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs,
                         self.anchors, gsm.PREFIX_WORDS, folds=1, holdable=one)
        self.assertLessEqual(sum(n for n, _bad in got.values()), 1)

    def test_proved_anchors_drops_the_prologue_only_pairs(self):
        anchors = [(1, 10, "exact"), (2, 20, "prefix"), (3, 30, "prefix+size"),
                   (4, 40, "relinked-body")]
        self.assertEqual(sl.proved_anchors(anchors), {1, 4})
        self.assertEqual(sl.anchor_composition(anchors),
                         {"exact": 1, "prefix": 1, "prefix+size": 1, "relinked-body": 1})


class AlignmentTest(unittest.TestCase):
    """Counts equal, alignment wrong: a split and a merge INSIDE ONE GAP cancel each other.

    `anchor_gaps` refuses a gap whose two sides hold different counts, which catches a lone split or
    a lone merge (`test_a_gap_that_does_not_line_up...`). Two of them in one gap cancel: the count
    still agrees, the gap is used, and every pairing in it is shifted by one. Nothing but the body
    check stands between that and a wrong name -- so this is the fixture that says whether the
    check earns its place, and what `--positional-min-evidence any` really costs.
    """

    def build(self, base, globals_, names, split=None, merge=None):
        spans, blob, cursor = [], b"", base
        bodies = [anchor_body(0)] + [twin_body(g) for g in globals_] + [anchor_body(1)]
        for i, body in enumerate(bodies):
            part = _blob(body)
            spans.append((names[i], cursor, cursor + len(part)))
            blob += part
            cursor += len(part)
        rows, i = [], 0
        while i < len(spans):
            name, start, end = spans[i]
            if name == split:
                half = start + ((end - start) // 8) * 4
                rows += [(start, half, name + "_lo"), (half, end, name + "_hi")]
            elif name == merge and i + 1 < len(spans):
                rows.append((start, spans[i + 1][2], name))
                i += 1
            else:
                rows.append((start, end, name))
            i += 1
        return rows, [(base, blob)]

    def setUp(self):
        self.demo_rows, self.demo_segs = self.build(
            DEMO_BASE, (0x00500120, 0x00500220, 0x00500320),
            ["anchor0", "p", "q", "r", "anchor1"])
        # In OUR table `p` is cut in two and `q` swallows `r`: three rows against the demo's three,
        # every one of them shifted.
        self.our_rows, self.our_segs = self.build(
            OUR_BASE, (0x00610a00, 0x00610b00, 0x00610c00),
            ["FUN_anchor0", "FUN_p", "FUN_q", "FUN_r", "FUN_anchor1"],
            split="FUN_p", merge="FUN_q")
        self.anchors = task7_anchors(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs)

    def run_lever(self, level):
        return sl.positional(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs,
                             self.anchors, gsm.PREFIX_WORDS, min_evidence=level)

    def test_the_cancelling_quirks_leave_the_gap_usable_and_misaligned(self):
        _found, census = self.run_lever("image-wide")
        self.assertEqual(census["candidates"], 3, "the counts cancel, so the gap IS walked")

    def test_the_body_check_refuses_every_shifted_pairing(self):
        for level in ("image-wide", "gap-only"):
            found, _census = self.run_lever(level)
            self.assertEqual(found, [], level)

    def test_min_evidence_any_would_take_a_shifted_pairing(self):
        # This is the cost of the flag, asserted rather than asserted-about: with the hurdle off, a
        # merged row inherits the name of a function that is not in it.
        found, _census = self.run_lever("any")
        self.assertTrue(found)
        self.assertTrue(any(c.our_name != "FUN_" + c.demo_name for c in found),
                        "the shift must produce a demonstrably wrong pairing at `any`")
        self.assertEqual({c.evidence for c in found}, {"no"})


class ScanTest(unittest.TestCase):
    def test_it_finds_every_function_of_an_image_it_has_no_symbols_for(self):
        rows, segs = demo_side()
        found = sl.scan_functions(segs)
        self.assertEqual([(s, e) for s, e, _n in found], [(s, e) for s, e, _n in rows])
        self.assertTrue(all(n.startswith("sub_") for _s, _e, n in found))

    def test_a_nop_delay_slot_is_not_trimmed_as_padding(self):
        # Every body here ends `jr $ra; nop`. Trimming that nop as inter-function padding would cut
        # each range one instruction short, which is how the first cut of this scan lost 9 % of the
        # demo's functions (both boundaries right: 85.3 % before the fix, 94.6 % after).
        _rows, segs = demo_side()
        self.assertTrue(all((e - s) % 4 == 0 and e - s >= sl.MIN_BODY
                            for s, e, _n in sl.scan_functions(segs)))

    def test_the_jal_seed_keeps_a_leading_data_block_out_of_the_first_function(self):
        seg = (0x00100000, _blob([0x11111111, 0x22222222, 0x33333333, 0x44444444,
                                  jal(0x00100010), NOP, jr_ra(), NOP]))
        with_jal = sl.scan_functions([seg], jal_seed=True)
        without = sl.scan_functions([seg], jal_seed=False)
        self.assertEqual([(s, e) for s, e, _n in with_jal], [(0x00100010, 0x00100020)])
        self.assertEqual([(s, e) for s, e, _n in without], [(0x00100000, 0x00100020)])

    def test_a_range_with_no_return_in_it_is_not_a_function(self):
        data = _blob([0x11111111, 0x22222222, 0x33333333, 0x44444444])
        self.assertEqual(sl.scan_functions([(0x00100000, data)]), [])

    def test_scan_accuracy_scores_the_scan_against_a_real_symbol_table(self):
        from tools_py.elf_symbols import parse_elf
        from tools_py.tests.test_elf_symbols import tiny_elf
        acc = sl.scan_accuracy(parse_elf(tiny_elf()))
        self.assertEqual(acc["real"], 1)                   # tiny_elf has one sized, named FUNC
        self.assertLessEqual(acc["both_right"], acc["starts_right"])


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.demo_rows, self.demo_segs = demo_side()
        self.our_rows, self.our_segs = our_side()
        self.d2_rows, self.d2_segs = demo2_side()
        self.anchors = task7_anchors(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs)

    def run_bridge(self, anchors=None, d2=None):
        rows, segs = d2 if d2 else (self.d2_rows, self.d2_segs)
        return sl.bridge(self.demo_rows, self.demo_segs, rows, segs, self.our_rows, self.our_segs,
                         self.anchors if anchors is None else anchors)

    def test_a_bridge_that_agrees_with_task_7_adds_no_name_and_says_so(self):
        found, census = self.run_bridge()
        self.assertEqual(census["agrees with Task 7"], 4)
        self.assertEqual(census["contradicts Task 7"], 0)
        self.assertEqual(census["new"], 0)
        self.assertEqual(found, [])

    def test_a_bridge_that_contradicts_task_7_is_counted_and_never_written(self):
        bad = [(self.anchors[0][0], self.our_rows[-1][0], "exact")] + list(self.anchors[1:])
        found, census = self.run_bridge(bad)
        self.assertEqual(census["contradicts Task 7"], 1)
        self.assertEqual(census["new"], 0)
        self.assertEqual(found, [])

    def test_two_anchors_sharing_a_demo_address_do_not_collapse(self):
        # A demo `static` compiled into two translation units gives one demo address two of our
        # rows. Flattening the anchors with dict() would drop one and turn an agreement into a
        # contradiction.
        d, o, how = self.anchors[0]
        doubled = [(d, o, how), (d, self.our_rows[-1][0], how)] + list(self.anchors[1:])
        _found, census = self.run_bridge(doubled)
        self.assertEqual(census["contradicts Task 7"], 0)
        self.assertEqual(census["agrees with Task 7"], 4)

    def test_with_no_task_7_pairs_every_composition_is_new(self):
        found, census = self.run_bridge([])
        self.assertEqual(census["new"], 4)
        self.assertEqual({c.demo_name for c in found},
                         {"anchor0", "anchor1", "anchor2", "anchor3"})
        self.assertTrue(all("+" in c.tier for c in found))

    def test_a_weak_hop_is_refused(self):
        _found, census = sl.bridge(self.demo_rows, self.demo_segs, self.d2_rows, self.d2_segs,
                                   self.our_rows, self.our_segs, [], strong=("relinked-body",))
        self.assertEqual(census["new"], 0)
        self.assertEqual(census["composed (both hops strong)"], 0)
        self.assertEqual(census["composed (any pass)"], 4)

    def test_a_stripped_image_contributes_no_name(self):
        found, _census = self.run_bridge([])
        self.assertFalse([c for c in found if c.demo_name.startswith("sub_")])


class BridgeSafetyTest(unittest.TestCase):
    """A mis-bounded demo2 range costs RECALL, never correctness -- note 45 §7's claim, asserted."""

    def setUp(self):
        self.demo_rows, self.demo_segs = demo_side()
        self.our_rows, self.our_segs = our_side()

    def truth(self):
        return {n: s for s, _e, n in self.our_rows}

    def compose(self, d2_rows, d2_segs):
        return sl.bridge(self.demo_rows, self.demo_segs, d2_rows, d2_segs,
                         self.our_rows, self.our_segs, [])

    def test_a_split_or_merged_demo2_range_loses_matches_without_inventing_one(self):
        clean, clean_census = self.compose(*demo2_side())
        self.assertEqual(clean_census["new"], 4)
        for quirk in ({"split": "anchor1"}, {"merge": "anchor2"},
                      {"split": "anchor1", "merge": "anchor2"}):
            found, census = self.compose(*demo2_side(**quirk))
            self.assertLess(census["new"], clean_census["new"], quirk)
            truth = self.truth()
            for c in found:
                self.assertEqual(c.our_addr, truth["FUN_" + c.demo_name], (quirk, c.demo_name))
            self.assertEqual(census["contradicts Task 7"], 0, quirk)


class ProposalsTest(unittest.TestCase):
    def rows_for(self, names, evidence="image-wide"):
        return [("positional", sl.Candidate(0x400000 + i * 0x40, 0x100000 + i * 0x40, n,
                                            "FUN_%08x" % (0x400000 + i * 0x40), 64, 64, "A", 1,
                                            evidence, (1, 1)))
                for i, n in enumerate(names)]

    def test_an_identifier_task_7_already_spent_is_refused(self):
        rows, held = sl.proposals_7b(self.rows_for(["Tick__5CPipeFv"]), ["Tick__5CPipeFv"])
        self.assertEqual(rows, [])
        self.assertEqual(held["identifier already spent or collides"], 1)

    def test_two_proposals_that_sanitise_alike_are_both_refused(self):
        rows, held = sl.proposals_7b(self.rows_for(["f<a>", "f_a_"]), [])
        self.assertEqual(rows, [])
        self.assertEqual(held["identifier already spent or collides"], 2)

    def test_a_mangled_name_keeps_its_original_in_its_own_column(self):
        rows, _held = sl.proposals_7b(self.rows_for(["Draw__5CHUDFv"]), [])
        self.assertEqual(rows[0]["Mangled"], "Draw__5CHUDFv")
        self.assertEqual(rows[0]["Proposed"], "Draw__5CHUDFv")
        self.assertEqual(rows[0]["Source"], "positional")

    def test_a_template_name_is_sanitised_into_a_legal_identifier(self):
        rows, _held = sl.proposals_7b(self.rows_for(["DrawFunc<11CDynGrenade>__2aiFf"]), [])
        self.assertEqual(rows[0]["Proposed"], "DrawFunc_11CDynGrenade___2aiFf")
        self.assertNotIn("<", rows[0]["Proposed"])

    def test_the_file_states_its_rule_and_its_bias_above_the_column_header(self):
        rows, _held = sl.proposals_7b(self.rows_for(["Draw__5CHUDFv"]), [])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "renames_7b.csv")
            sl.write_proposals_7b(path, rows, [sl.POSITIONAL_RULE, sl.POSITIONAL_CAVEAT,
                                               sl.BRIDGE_RULE])
            with open(path) as fh:
                text = fh.read()
        self.assertTrue(text.startswith("# "))
        self.assertIn("IMAGE-WIDE", text)
        self.assertIn("UPPER BOUND", text)                 # the holdout's bias travels with the file
        self.assertIn("demo2 is stripped", text)
        body = [ln for ln in text.splitlines() if not ln.startswith("#")]
        parsed = list(csv.DictReader(io.StringIO("\n".join(body))))
        self.assertEqual(parsed[0]["Proposed"], "Draw__5CHUDFv")
        self.assertEqual(list(parsed[0]), sl.PROPOSAL_COLUMNS_7B)

    def test_a_bad_output_directory_is_a_sentence_not_a_traceback(self):
        with self.assertRaises(ValueError) as caught:
            sl.write_proposals_7b(os.path.join(os.sep, "no", "such", "dir", "x.csv"), [], [])
        self.assertIn("not a directory", str(caught.exception))


class CliTest(unittest.TestCase):
    def run_main(self, argv):
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = gsm.main(argv)
        return code, buf.getvalue()

    def test_a_missing_bridge_elf_is_one_sentence_and_exit_2(self):
        code, out = self.run_main(["nope.elf", "nope2.elf", "nope.csv", "--bridge", "nope3.elf"])
        self.assertEqual(code, 2)
        self.assertIn("NO-DATA: missing nope3.elf", out)

    def test_min_evidence_without_the_lever_is_refused_not_ignored(self):
        code, out = self.run_main(["a", "b", "c", "--positional-min-evidence", "any"])
        self.assertEqual(code, 2)
        self.assertIn("needs --positional", out)

    def test_a_proposals_file_with_no_lever_is_refused(self):
        code, out = self.run_main(["a", "b", "c", "--renames-7b", "x.csv"])
        self.assertEqual(code, 2)
        self.assertIn("not a proposals file", out)

    def test_the_rule_constants_carry_the_thresholds_they_claim(self):
        self.assertIn("%.2f" % sl.SIZE_RATIO, sl.POSITIONAL_RULE)
        self.assertIn(str(sl.MIN_BODY), sl.POSITIONAL_RULE)
        self.assertIn(str(gsm.PREFIX_WORDS), sl.POSITIONAL_RULE)
        self.assertEqual(sl.MIN_BODY, gsm.PROPOSE_MIN_SIZE, "note 44's hurdle 2, kept")
        self.assertIn("IMAGE-WIDE", sl.POSITIONAL_RULE)
        self.assertIn("UPPER BOUND", sl.POSITIONAL_CAVEAT)


if __name__ == "__main__":
    unittest.main()
