"""`tools_py/data_via_twin.py`: the derivation behind the r0004 guest-address column (Task 19 review F5).

Before this, `data-via-twin` was a procedure described in prose and four numbers nobody could re-run: the
matcher places functions, `addresses_from_match.py` takes DATA fields only through
`--override <field>=<addr>:hand,data-via-twin`, and `socom2_addresses.h:19` says *hand* in as many words.
A transposed digit in `guest_addresses.PROBE_ADDRESSES` would have been caught by nothing.

The control is the one thing that makes the rest worth anything: `cameraHolder 0x415ff0`, whose r0004
value `0x4429b0` the committed `runtime/socom2_addresses.h` already carries, established by hand before
this tool existed. The tool reproduces it from the two images, unanimously, and then reproduces the four
probe addresses the same way.

Skipped without the disc assets: `game/` is git-ignored, so a bare clone (CI) has no images to read.
"""
import os
import unittest

from tools_py import data_via_twin as dvt
from tools_py.parity import guest_addresses as ga

HAVE_IMAGES = all(os.path.isfile(p) for p in (dvt.A_ELF, dvt.B_ELF, dvt.A_CSV, dvt.MATCH))


@unittest.skipUnless(HAVE_IMAGES, "needs the two game images and game/r0004/match.json (game/ is git-ignored)")
class Control(unittest.TestCase):
    """One scan of both images for the whole class: it reads 10 MB and walks every executable word."""

    @classmethod
    def setUpClass(cls):
        cls.kw = dict(a=dvt.Image(dvt.A_ELF), b=dvt.Image(dvt.B_ELF),
                      match=dvt.load_match(), funcs=dvt.load_functions())

    def test_it_reproduces_socom2_addresses_h_camera_holder(self):
        """THE control. 84 materialising sites in r0001, 60 of them in functions match.json places by
        evidence, and every one of the 60 says 0x4429b0 -- the number the C++ table carries."""
        name, r0001, r0004 = dvt.CONTROL
        addr, votes, n_sites = dvt.resolve(r0001, **self.kw)
        self.assertEqual(addr, r0004, "%s: %s of %d sites" % (name, len(votes), n_sites))
        self.assertGreaterEqual(len(votes), 20, "the claim is unanimity over MANY referrers, not one")
        self.assertEqual({v.b_addr for v in votes}, {r0004}, "unanimous, or it fills nothing")

    def test_every_twin_rests_on_evidence_not_on_a_delta(self):
        """`seed+delta` says where to look, not what was found, so it may not establish a twin."""
        _addr, votes, _n = dvt.resolve(dvt.CONTROL[1], **self.kw)
        for v in votes:
            self.assertIn(v.how, dvt.ACCEPT, v.func)

    def test_every_address_the_tables_carry_is_what_this_tool_derives(self):
        """`guest_addresses`' whole r0004 column, regenerated -- the gate's four, the online instruments'
        six and the call trace's two. Referenced addresses come from the twin scan; actor_vtable is a
        VALUE in an object's word 0, which no lui/lo pair forms, so it is placed by its CONTENTS; and the
        two traced FUNCTIONS by the reading their own shape allows (a masked body, a thunk's target)."""
        for name, r0001, r0004, how in dvt.COLUMN:
            self.assertEqual(ga.address(name, "r0001"), r0001, name)
            if how == "vtable":
                got, translated, hits = dvt.vtable_by_contents(r0001, a=self.kw["a"], b=self.kw["b"],
                                                               match=self.kw["match"])
                self.assertGreaterEqual(translated, 3, "%s: too few slots to identify it" % name)
                self.assertEqual(hits, [r0004], "%s: one place in the image, or it is not placed" % name)
            elif how == "thunk":
                got, note = dvt.resolve_thunk(r0001, self.kw["a"], self.kw["b"], self.kw["match"])
                self.assertIsNotNone(got, "%s: %s" % (name, note))
            elif how == "masked-body":
                span = dvt.body_span(self.kw["funcs"], r0001)
                self.assertIsNotNone(span, "%s: the r0001 CSV has no function at 0x%08x" % (name, r0001))
                ok, differ = dvt.masked_body_matches(self.kw["a"], r0001, self.kw["b"], r0004, span[1])
                self.assertTrue(ok, "%s: the two bodies differ under the mask" % name)
                self.assertTrue(differ, "%s: nothing differs at all -- that is a relink, not this twin" % name)
                got = r0004
            else:
                got, votes, _n = dvt.resolve(r0001, **self.kw)
                self.assertEqual({v.b_addr for v in votes}, {r0004}, name)
            self.assertEqual(got, r0004, name)
            self.assertEqual(ga.address(name, "r0004"), r0004, name)

    def test_clock_string_is_one_referrer_function_wearing_two_votes(self):
        """The finding itself, held so it cannot quietly come back: both of clock_string's sites are in
        FUN_001f6b60, so a site count would call it corroborated and a function count does not."""
        _addr, votes, _n = dvt.resolve(0x00408F10, **self.kw)
        self.assertEqual(len(votes), 2)
        self.assertEqual(len({v.func for v in votes}), 1)
        self.assertIn("clock_string", ga.CORROBORATED)
        self.assertNotIn("clock_string", ga.UNCONFIRMED)

    def test_the_unconfirmed_values_are_exactly_the_uncorroborated_single_vote_ones(self):
        """`guest_addresses.UNCONFIRMED` is a claim about the evidence, so it is checked against the
        evidence -- in BOTH directions. A value with one evidence-twinned referrer is unconfirmed unless
        `CORROBORATED` says in words what else stands behind it (camera_record has a neighbour's 60
        unanimous twins and a run-time probe); a value with two or more may not be listed as either."""
        for name, r0001, _r0004, how in dvt.COLUMN:
            if how != "twin":
                continue
            _addr, votes, _n = dvt.resolve(r0001, **self.kw)
            # DISTINCT REFERRER FUNCTIONS, not vote sites (review F3): one function that materialises
            # the address twice is one piece of evidence, and `clock_string` read as "2 twinned,
            # unanimous" on the site count while both sites are inside FUN_001f6b60.
            thin = len({v.func for v in votes}) < 2
            self.assertEqual(thin, name in ga.UNCONFIRMED or name in ga.CORROBORATED,
                             "%s has %d evidence-twinned referrer function(s) (%d site(s)): it must be "
                             "in exactly one of UNCONFIRMED or CORROBORATED if that is fewer than 2, and "
                             "in neither if not" % (name, len({v.func for v in votes}), len(votes)))
            self.assertFalse(name in ga.UNCONFIRMED and name in ga.CORROBORATED, name)

    def test_the_masked_body_is_masking_the_displacement_that_moved(self):
        """SetMoveScale is the whole reason a masked body is needed here: the two raw words that differ
        are its two `swc1` stores, and they differ by exactly the actor displacement PROBE_OFFSETS
        carries (0x1368 -> 0x136c)."""
        a, b = self.kw["a"], self.kw["b"]
        r1, r4 = 0x00553DC0, 0x005590E0
        span = dvt.body_span(self.kw["funcs"], r1)
        _ok, differ = dvt.masked_body_matches(a, r1, b, r4, span[1])
        self.assertEqual(len(differ), 2)
        for i in differ:
            self.assertEqual(a.word(r1 + 4 * i) & 0xFFFF, ga.offset("move_scale", "r0001"))
            self.assertEqual(b.word(r4 + 4 * i) & 0xFFFF, ga.offset("move_scale", "r0004"))

    def test_the_main_entry_point_agrees_with_the_table(self):
        """`python -m tools_py.data_via_twin --control --column` exits 0 only when every value it derives
        is the value the table carries."""
        self.assertEqual(dvt.main(["--control", "--column"]), 0)


class Mechanics(unittest.TestCase):
    """The lui/lo reading itself, on bytes this test writes -- no images needed."""

    class FakeImage:
        def __init__(self, words, base=0x00180000):
            self.base, self.words = base, words

        def word(self, a):
            i = (a - self.base) // 4
            return self.words[i] if 0 <= i < len(self.words) and (a - self.base) % 4 == 0 else None

        def exec_ranges(self):
            return [(self.base, 4 * len(self.words))]

    @staticmethod
    def _lui(rt, hi):
        return (0x0F << 26) | (rt << 16) | (hi & 0xFFFF)

    @staticmethod
    def _lw(rt, rs, lo):
        return (0x23 << 26) | (rs << 21) | (rt << 16) | (lo & 0xFFFF)

    def test_a_negative_low_half_borrows_from_the_high_half(self):
        """`lui $at, 0x42 ; lw $v0, -0x1000($at)` forms 0x0041f000, not 0x0042f000 -- the sign extension
        is the whole reason the address cannot be read off the lui alone."""
        img = self.FakeImage([self._lui(1, 0x0042), self._lw(2, 1, -0x1000)])
        self.assertEqual(dvt.formed(img, img.base, img.base + 4), (0x0041F000, "lw"))

    def test_ori_takes_its_low_half_unsigned(self):
        ori = (0x0D << 26) | (1 << 21) | (2 << 16) | 0xF000
        img = self.FakeImage([self._lui(1, 0x0042), ori])
        self.assertEqual(dvt.formed(img, img.base, img.base + 4), (0x0042F000, "ori"))

    def test_a_reloaded_register_ends_the_pair(self):
        """`lui $at, 0x41 ; lui $at, 0x42 ; lw $v0, 0x54($at)` materialises 0x00420054 once, from the
        SECOND lui -- the first one's register was overwritten before it was used."""
        img = self.FakeImage([self._lui(1, 0x0041), self._lui(1, 0x0042), self._lw(2, 1, 0x0054)])
        self.assertEqual(dvt.sites(img, 0x00420054), [(img.base + 4, img.base + 8, "lw")])
        self.assertEqual(dvt.sites(img, 0x00410054), [])


if __name__ == "__main__":
    unittest.main()
