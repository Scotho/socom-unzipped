"""Sprint 11 Task 7b -- the two levers on the demo's names (tools_py/symbol_levers).

The fixture is three little images of hand-assembled MIPS: the SOCOM 1 demo, the stripped SOCOM II
demo, and ours. Each holds the same routines at a different base, over a different global. The
interesting ones are the TWINS -- two routines whose bodies differ only in which global they touch, so
their masked fingerprints are equal and `address_matcher` cannot choose between them. That is exactly
the population lever 1 exists for: the matcher leaves them unresolved, and position between anchors
says which is which. No disc, no demo, no ELF on disk.
"""
import csv
import io
import os
import struct
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
SIZE = 0x40                       # sixteen words: the prologue window, and full size weight


def _blob(words):
    return b"".join((w & 0xFFFFFFFF).to_bytes(4, "little") for w in words)


def _pad(words, size=SIZE):
    return list(words) + [NOP] * (size // 4 - len(words) - 2) + [jr_ra(), NOP]


def anchor_body(salt):
    """Pure register arithmetic: not one bit of this moves between links, so it matches `exact`."""
    return _pad([addu(V0, A0, A1), subu(V0, V0, A0), xor(A1, V0, A0), mult(V0, A1 + salt % 3),
                 addu(V0, V0, A1), subu(A0, A1, V0), xor(S0, S0, A0 + salt % 5),
                 addu(T0, T0, V0 + salt % 7), subu(V0, T0, S0), mult(S0, T0)])


def twin_body(global_addr):
    """A load and a store THROUGH a global: the displacement is half an address.

    Two twins over DIFFERENT globals have different plain fingerprints (the displacement is kept)
    and the same MASKED one (the displacement is blanked). So `exact` cannot see them at all and the
    relinked-body pass sees two candidates it cannot separate -- which leaves them for position.
    """
    hi, lo = ((global_addr + 0x8000) >> 16) & 0xFFFF, global_addr & 0xFFFF
    return _pad([lui(AT, hi), lw(V0, AT, lo), addiu(V0, V0, 1), lui(AT, hi), sw(V0, AT, lo),
                 lw(T0, A0, 0x18), addu(V0, V0, T0), subu(S0, V0, T0)])


# The layout every image shares: three anchors with a twin between each pair.
LAYOUT = ["anchor0", "twinA", "anchor1", "twinB", "anchor2"]


def image(base, g0, g1, names=None, extra=None):
    """(rows, segments) for one build: LAYOUT at `base`, twins over the globals `g0` and `g1`.

    `extra` inserts one more function right after `twinB`, which is how the "a gap that does not
    line up" fixture makes the two sides disagree on a count.
    """
    order = list(LAYOUT)
    if extra:
        order.insert(order.index("twinB") + 1, extra)
    bodies = {"anchor0": anchor_body(0), "anchor1": anchor_body(1), "anchor2": anchor_body(2),
              "twinA": twin_body(g0), "twinB": twin_body(g1)}
    if extra:
        bodies[extra] = anchor_body(9)
    # ONE segment covering the lot, as a real PT_LOAD is: the gap walk runs per PT_LOAD, so an
    # image of one-function segments would have no gaps at all and test nothing.
    rows, blob = [], b""
    cursor = base
    for name in order:
        body = _blob(bodies[name])
        rows.append((cursor, cursor + len(body), (names or {}).get(name, name)))
        blob += body
        cursor += len(body)
    return rows, [(base, blob)]


DEMO_BASE, OUR_BASE, DEMO2_BASE = 0x00140000, 0x00280000, 0x00200000
OURS_NAMES = {n: "FUN_%s" % n for n in LAYOUT + ["extra"]}


def demo_side():
    return image(DEMO_BASE, 0x00500120, 0x00500220)


def our_side(extra=None):
    names = {n: "FUN_%08x" % (OUR_BASE + i * SIZE) for i, n in enumerate(LAYOUT)}
    names["extra"] = "FUN_extra"
    return image(OUR_BASE, 0x00610a00, 0x00610b00, names=names, extra=extra)


def demo2_side():
    return image(DEMO2_BASE, 0x00570040, 0x00570140,
                 names={n: "sub_%s" % n for n in LAYOUT})


def task7_anchors(demo_rows, demo_segs, our_rows, our_segs):
    """[(demo_addr, our_addr)] -- what `ghidra_symbol_match.match` proves on this fixture."""
    details = {}
    gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details)
    return [(info["demo_addr"], addr) for (_n, addr), info in details.items()]


class FixtureTest(unittest.TestCase):
    """The fixture only tests what it claims if the matcher really cannot place the twins."""

    def test_the_matcher_places_the_anchors_and_not_the_twins(self):
        demo_rows, demo_segs = demo_side()
        our_rows, our_segs = our_side()
        placed = task7_anchors(demo_rows, demo_segs, our_rows, our_segs)
        self.assertEqual(len(placed), 3)
        twins = {r[0] for r in demo_rows if r[2].startswith("twin")}
        self.assertFalse(twins & {d for d, _o in placed},
                         "the twins must be ambiguous, or lever 1 has nothing to do here")


class PositionalTest(unittest.TestCase):
    def setUp(self):
        self.demo_rows, self.demo_segs = demo_side()
        self.our_rows, self.our_segs = our_side()
        self.anchors = task7_anchors(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs)

    def run_lever(self, our_rows=None, our_segs=None, **kw):
        return sl.positional(self.demo_rows, self.demo_segs,
                             our_rows if our_rows is not None else self.our_rows,
                             our_segs if our_segs is not None else self.our_segs,
                             self.anchors, gsm.PREFIX_WORDS, **kw)

    def test_a_gap_that_lines_up_names_its_function(self):
        found, census = self.run_lever()
        self.assertEqual(census["candidates"], 2)
        self.assertEqual({c.demo_name for c in found}, {"twinA", "twinB"})
        by_name = {c.demo_name: c for c in found}
        self.assertEqual(by_name["twinA"].our_addr, OUR_BASE + SIZE)
        self.assertEqual(by_name["twinB"].our_addr, OUR_BASE + 3 * SIZE)
        self.assertEqual({c.tier for c in found}, {"A"})   # equal length, equal masked fingerprint

    def test_a_gap_that_does_not_line_up_names_nothing(self):
        our_rows, our_segs = our_side(extra="extra")
        anchors = task7_anchors(self.demo_rows, self.demo_segs, our_rows, our_segs)
        self.assertEqual(len(anchors), 3, "the three anchors must still pair after the insert")
        found, census = sl.positional(self.demo_rows, self.demo_segs, our_rows, our_segs,
                                      anchors, gsm.PREFIX_WORDS)
        # The second gap now holds two of our functions against the demo's one, so it is refused
        # whole. The first gap is untouched: the count rule is per gap, not per image.
        self.assertEqual(census["candidates"], 1)
        self.assertEqual([c.demo_name for c in found], ["twinA"])

    def test_it_never_takes_a_row_we_named_by_hand(self):
        our_rows, our_segs = our_side()
        our_rows = [(s, e, "CZSealBody_Tick" if s == OUR_BASE + SIZE else n)
                    for s, e, n in our_rows]
        found, census = self.run_lever(our_rows, our_segs)
        self.assertEqual(census["our row already named"], 1)
        self.assertEqual([c.demo_name for c in found], ["twinB"])

    def test_it_never_takes_a_row_task_7_already_paired(self):
        found, _census = self.run_lever()
        taken = {o for _d, o in self.anchors}
        self.assertFalse(taken & {c.our_addr for c in found})

    def test_anchors_out_of_order_on_the_demo_side_make_no_gap(self):
        # Reverse the demo order the anchors claim: no pair is then ascending on both sides.
        flipped = [(d, o) for d, o in
                   zip(sorted(d for d, _o in self.anchors)[::-1],
                       sorted(o for _d, o in self.anchors))]
        _found, census = sl.positional(self.demo_rows, self.demo_segs, self.our_rows,
                                       self.our_segs, flipped, gsm.PREFIX_WORDS)
        self.assertEqual(census["candidates"], 0)

    def test_a_gap_in_another_pt_load_of_ours_is_not_walked_into(self):
        # One region per function: no two anchors share a region, so there is no gap anywhere.
        regions = [(s, e) for s, e, _n in self.our_rows]
        _found, census = sl.positional(self.demo_rows, self.demo_segs, self.our_rows,
                                       self.our_segs, self.anchors, gsm.PREFIX_WORDS,
                                       regions=regions)
        self.assertEqual(census["candidates"], 0)


class DiscriminationTest(unittest.TestCase):
    """Two twins over the SAME global sit in one gap and the body cannot tell them apart."""

    def setUp(self):
        # anchor0, twinA, twinA', anchor1 -- one gap of two, both bodies identical.
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

    def test_body_evidence_that_cannot_separate_siblings_is_refused(self):
        found, census = sl.positional(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs,
                                      self.anchors, gsm.PREFIX_WORDS)
        self.assertEqual(census["candidates"], 2)
        self.assertEqual(census["body evidence not gap-discriminating"], 2)
        self.assertEqual(found, [])

    def test_positional_blurred_admits_them_and_says_so_in_the_row(self):
        found, _census = sl.positional(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs,
                                       self.anchors, gsm.PREFIX_WORDS, allow_blurred=True)
        self.assertEqual(len(found), 2)
        self.assertEqual({c.discriminating for c in found}, {False})
        rows, _held = sl.proposals_7b([("positional", c) for c in found], [])
        self.assertEqual({r["Discriminating"] for r in rows}, {"no"})


class TierTest(unittest.TestCase):
    def setUp(self):
        self.demo = am.Side(*demo_side())
        self.ours = am.Side(*our_side())

    def test_tier_a_is_equal_length_and_equal_masked_fingerprint(self):
        self.assertEqual(sl._tier(self.demo, DEMO_BASE + SIZE, self.ours, OUR_BASE + SIZE,
                                  gsm.PREFIX_WORDS), "A")

    def test_a_body_under_the_tier_a_floor_is_not_tier_a(self):
        short = _blob([lui(AT, 1), lw(V0, AT, 4), jr_ra(), NOP])       # sixteen bytes
        rows = [(0x300000, 0x300010, "tiny")]
        side = am.Side(rows, [(0x300000, short)])
        rows2 = [(0x400000, 0x400010, "FUN_00400000")]
        side2 = am.Side(rows2, [(0x400000, short)])
        self.assertIsNone(sl._tier(side, 0x300000, side2, 0x400000, gsm.PREFIX_WORDS))

    def test_unrelated_bodies_clear_no_tier(self):
        self.assertIsNone(sl._tier(self.demo, DEMO_BASE, self.ours, OUR_BASE + SIZE,
                                   gsm.PREFIX_WORDS))

    def test_the_size_ratio_is_the_smaller_over_the_larger(self):
        c = sl.Candidate(1, 2, "n", "FUN_x", 100, 200, "B", 3)
        self.assertEqual(c.ratio, 0.5)
        self.assertEqual(sl.Candidate(1, 2, "n", "FUN_x", 0, 0, None, 0).ratio, 0.0)


class HoldoutTest(unittest.TestCase):
    def test_it_re_derives_a_held_out_pair_and_calls_it_right(self):
        demo_rows, demo_segs = demo_side()
        our_rows, our_segs = our_side()
        anchors = task7_anchors(demo_rows, demo_segs, our_rows, our_segs)
        got = sl.holdout(demo_rows, demo_segs, our_rows, our_segs, anchors, gsm.PREFIX_WORDS,
                         folds=3)
        tried = sum(n for n, _bad in got.values())
        wrong = sum(bad for _n, bad in got.values())
        self.assertGreater(tried, 0, "the holdout must actually re-derive something")
        self.assertEqual(wrong, 0)


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
        self.assertTrue(all(e - s == SIZE for s, e, _n in sl.scan_functions(segs)))

    def test_the_jal_seed_keeps_a_leading_data_block_out_of_the_first_function(self):
        # Four words of data, then a function that calls itself. Without the `jal` seed the only
        # start is the segment's own base, and the data is swallowed into the function's body.
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
        from tools_py.tests.test_elf_symbols import tiny_elf
        from tools_py.elf_symbols import parse_elf
        acc = sl.scan_accuracy(parse_elf(tiny_elf()))
        self.assertEqual(acc["real"], 1)                   # tiny_elf has one sized, named FUNC
        self.assertIn("ranges", acc)
        self.assertLessEqual(acc["both_right"], acc["starts_right"])


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.demo_rows, self.demo_segs = demo_side()
        self.our_rows, self.our_segs = our_side()
        self.d2_rows, self.d2_segs = demo2_side()
        self.anchors = task7_anchors(self.demo_rows, self.demo_segs, self.our_rows, self.our_segs)

    def run_bridge(self, anchors=None):
        return sl.bridge(self.demo_rows, self.demo_segs, self.d2_rows, self.d2_segs,
                         self.our_rows, self.our_segs,
                         self.anchors if anchors is None else anchors)

    def test_a_bridge_that_agrees_with_task_7_adds_no_name_and_says_so(self):
        found, census = self.run_bridge()
        self.assertEqual(census["agrees with Task 7"], 3)
        self.assertEqual(census["contradicts Task 7"], 0)
        self.assertEqual(census["new"], 0)
        self.assertEqual(found, [])

    def test_a_bridge_that_contradicts_task_7_is_counted_and_never_written(self):
        # Claim the first anchor maps to the LAST of our rows. The composition disagrees.
        bad = [(self.anchors[0][0], self.our_rows[-1][0])] + list(self.anchors[1:])
        found, census = self.run_bridge(bad)
        self.assertEqual(census["contradicts Task 7"], 1)
        self.assertEqual(census["new"], 0)
        self.assertEqual(found, [])

    def test_with_no_task_7_pairs_every_composition_is_new(self):
        found, census = self.run_bridge([])
        self.assertEqual(census["new"], 3)
        self.assertEqual({c.demo_name for c in found}, {"anchor0", "anchor1", "anchor2"})
        self.assertTrue(all("+" in c.tier for c in found))

    def test_a_weak_hop_is_refused(self):
        _found, census = sl.bridge(self.demo_rows, self.demo_segs, self.d2_rows, self.d2_segs,
                                   self.our_rows, self.our_segs, [], strong=("relinked-body",))
        self.assertEqual(census["new"], 0)
        self.assertEqual(census["composed (both hops strong)"], 0)
        self.assertEqual(census["composed (any pass)"], 3)

    def test_a_stripped_image_contributes_no_name(self):
        # Every name in the output comes from the demo1 side, never from demo2's `sub_*` table.
        found, _census = self.run_bridge([])
        self.assertFalse([c for c in found if c.demo_name.startswith("sub_")])


class ProposalsTest(unittest.TestCase):
    def rows_for(self, names):
        cands = [("positional", sl.Candidate(0x400000 + i * 0x40, 0x100000 + i * 0x40, n,
                                             "FUN_%08x" % (0x400000 + i * 0x40), 64, 64, "A", 1))
                 for i, n in enumerate(names)]
        return cands

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

    def test_the_file_states_its_rule_above_the_column_header(self):
        rows, _held = sl.proposals_7b(self.rows_for(["Draw__5CHUDFv"]), [])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "renames_7b.csv")
            sl.write_proposals_7b(path, rows, [sl.POSITIONAL_RULE, "", sl.BRIDGE_RULE])
            with open(path) as fh:
                text = fh.read()
        self.assertTrue(text.startswith("# "))
        self.assertIn("GAP-DISCRIMINATING", text)
        self.assertIn("demo2 is stripped", text)
        body = [ln for ln in text.splitlines() if not ln.startswith("#")]
        parsed = list(csv.DictReader(io.StringIO("\n".join(body))))
        self.assertEqual(parsed[0]["Proposed"], "Draw__5CHUDFv")
        self.assertEqual(list(parsed[0]), sl.PROPOSAL_COLUMNS_7B)


class CliTest(unittest.TestCase):
    def test_a_missing_bridge_elf_is_one_sentence_and_exit_2(self):
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = gsm.main(["nope.elf", "nope2.elf", "nope.csv", "--bridge", "nope3.elf"])
        self.assertEqual(code, 2)
        self.assertIn("NO-DATA: missing nope3.elf", buf.getvalue())

    def test_the_rule_constants_carry_the_thresholds_they_claim(self):
        self.assertIn("%.2f" % sl.SIZE_RATIO, sl.POSITIONAL_RULE)
        self.assertIn(str(sl.TIER_A_MIN_SIZE), sl.POSITIONAL_RULE)
        self.assertIn(str(sl.TIER_B_MIN_SIZE), sl.POSITIONAL_RULE)
        self.assertEqual(sl.PROLOGUE_WORDS_DOC, gsm.PREFIX_WORDS)


if __name__ == "__main__":
    unittest.main()
