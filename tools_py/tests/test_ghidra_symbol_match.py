"""Sprint 11 Task 7 (U3) -- pairing the demo's named functions with ours (tools_py/ghidra_symbol_match).

The fixture is the brief's: two little images whose functions are hand-assembled MIPS words. One
function is byte-identical in both; one is the same code RELOCATED (the same stream with the `lui`/
`addiu` halves of an address moved, which is all a second link does to it); one reaches a global, so
its load displacement moves too and only the relinked-body pass can see through it; and each side has
a function the other does not, which must match nothing. No disc, no ELF, no demo needed.
"""
import unittest

from tools_py import ghidra_symbol_match as gsm


# ---- a tiny assembler (the same shapes as test_address_matcher's) --------------------------

def lui(rt, imm):        return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)
def addiu(rt, rs, imm):  return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def ori(rt, rs, imm):    return (0x0D << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def jal(target):         return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)
def lw(rt, base, imm):   return (0x23 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def sw(rt, base, imm):   return (0x2B << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def addu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21
def subu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x23
def xor(rd, rs, rt):     return (rs << 21) | (rt << 16) | (rd << 11) | 0x26
def mult(rs, rt):        return (rs << 21) | (rt << 16) | 0x18
def jr_ra():             return (31 << 21) | 8
NOP = 0

AT, V0, A0, A1, S0, T0, RA = 1, 2, 4, 5, 16, 8, 31
SIZE = 0x40                       # sixteen words: long enough to score at full weight
TINY = 0x08                       # two words: a thunk, which scores a quarter of that


def _pad(words, size=SIZE):
    return list(words) + [NOP] * (size // 4 - len(words))


def _blob(words):
    return b"".join(w.to_bytes(4, "little") for w in words)


def build(base, data, variant=0):
    """(rows, segments) for one image: four named functions of `SIZE` bytes plus one thunk.

    `base` is where the image loads, `data` is where its one global lives. Moving both is what a
    relink does; nothing about the code itself changes between the two images this returns.
    """
    order = ["identical", "relocated", "viaglobal", "onlyhere", "thunk"]
    at = {}
    cursor = base
    for name in order:
        at[name] = cursor
        cursor += TINY if name == "thunk" else SIZE
    hi, lo = ((data + 0x8000) >> 16) & 0xFFFF, data & 0xFFFF

    body = {
        # Pure register arithmetic: not one bit of this moves between links.
        "identical": _pad([addu(V0, A0, A1), subu(V0, V0, A0), xor(A1, V0, A0),
                           mult(V0, A1), addu(V0, V0, A1), subu(A0, A1, V0), jr_ra()]),
        # An address materialised into a register, and a call: every address word here moves.
        "relocated": _pad([lui(AT, hi), addiu(A0, AT, lo), jal(at["identical"]), NOP,
                           ori(A1, A0, 0x40), addu(V0, A0, A1), jr_ra()]),
        # A load and a store THROUGH the global's address: the displacement is half an address, so
        # the plain fingerprint differs between the images and only the masked one agrees.
        "viaglobal": _pad([lui(AT, hi), lw(V0, AT, lo), addiu(V0, V0, 1), lui(AT, hi),
                           sw(V0, AT, lo), lw(T0, A0, 0x18), addu(V0, V0, T0), jr_ra()]),
        "thunk": _pad([jr_ra(), NOP], TINY),
    }
    # Deliberately different code on each side, under a name the other side does not use.
    body["onlyhere"] = _pad([xor(V0, A0, A0), addu(V0, V0, V0), subu(S0, A0, A1),
                             mult(A0, A1), xor(S0, S0, V0), jr_ra()]
                            if variant == 0 else
                            [mult(A1, A1), subu(V0, A1, A0), addu(S0, V0, V0),
                             xor(A0, S0, A1), addu(V0, A0, S0), jr_ra()])

    rows, segs = [], []
    for name in order:
        blob = _blob(body[name])
        rows.append((at[name], at[name] + len(blob), name, blob))
        segs.append((at[name], blob))
    return rows, segs


DEMO_BASE, DEMO_DATA = 0x00140000, 0x00500124
OUR_BASE, OUR_DATA = 0x00280000, 0x00610ab8


def demo_side():
    return build(DEMO_BASE, DEMO_DATA)


def our_side():
    # A different load address and a different global: a second link, with `onlyhere` replaced by a
    # routine that is not in the demo at all.
    rows, segs = build(OUR_BASE, OUR_DATA, variant=1)
    renamed = [(s, e, "FUN_%08x" % s, c) for s, e, _n, c in rows]
    return renamed, segs


class ScoreTest(unittest.TestCase):
    def test_a_long_body_scores_its_method_in_full(self):
        self.assertEqual(gsm.score_of("exact", 0x100), 1.0)
        self.assertEqual(gsm.score_of("exact", 64), 1.0)

    def test_a_short_body_is_discounted(self):
        self.assertEqual(gsm.size_weight(8), 0.25)
        self.assertLess(gsm.score_of("exact", 8), gsm.score_of("exact", 64))
        self.assertLess(gsm.score_of("relinked-body", 64), gsm.score_of("exact", 64))


class MatchTest(unittest.TestCase):
    def setUp(self):
        demo_rows, _ = demo_side()
        our_rows, _ = our_side()
        self.hows = {}
        self.pairs = gsm.match(demo_rows, our_rows, hows=self.hows)
        self.by_name = {name: (addr, score) for name, addr, score in self.pairs}
        self.our_at = {name: start for start, _e, name, _c in build(OUR_BASE, OUR_DATA, variant=1)[0]}

    def test_the_byte_identical_function_matches(self):
        self.assertIn("identical", self.by_name)
        self.assertEqual(self.by_name["identical"][0], self.our_at["identical"])
        self.assertEqual(self.hows["identical"], "exact")
        self.assertEqual(self.by_name["identical"][1], 1.0)

    def test_the_relocated_function_matches(self):
        self.assertIn("relocated", self.by_name)
        self.assertEqual(self.by_name["relocated"][0], self.our_at["relocated"])

    def test_the_global_toucher_needs_the_relinked_body_pass(self):
        self.assertIn("viaglobal", self.by_name)
        self.assertEqual(self.by_name["viaglobal"][0], self.our_at["viaglobal"])
        self.assertEqual(self.hows["viaglobal"], "relinked-body")

    def test_the_unrelated_function_matches_nothing(self):
        self.assertNotIn("onlyhere", self.by_name)
        self.assertNotIn(self.our_at["onlyhere"], [a for _n, a, _s in self.pairs])

    def test_a_thunk_matches_but_is_scored_low(self):
        # `jr $ra; nop` is the same in every program ever compiled. It is only here because it is
        # unique on both sides; the score is what says not to rename anything on it.
        self.assertIn("thunk", self.by_name)
        self.assertLessEqual(self.by_name["thunk"][1], 0.25)

    def test_min_score_drops_the_weak_pairs(self):
        demo_rows, _ = demo_side()
        our_rows, _ = our_side()
        strong = gsm.match(demo_rows, our_rows, min_score=gsm.GOOD)
        self.assertNotIn("thunk", [n for n, _a, _s in strong])
        self.assertIn("identical", [n for n, _a, _s in strong])

    def test_every_pairing_is_one_to_one(self):
        coll = gsm.collisions(self.pairs)
        self.assertEqual(coll["names"], [])
        self.assertEqual(coll["addrs"], [])

    def test_rows_may_carry_segments_instead_of_bytes(self):
        demo_rows, demo_segs = demo_side()
        our_rows, our_segs = our_side()
        bare_demo = [(s, e, n) for s, e, n, _c in demo_rows]
        bare_ours = [(s, e, n) for s, e, n, _c in our_rows]
        again = gsm.match(bare_demo, bare_ours, demo_segs, our_segs)
        self.assertEqual(again, self.pairs)


class CollisionTest(unittest.TestCase):
    def test_one_name_on_two_addresses_is_reported(self):
        coll = gsm.collisions([("a", 0x10, 1.0), ("a", 0x20, 1.0), ("b", 0x30, 1.0)])
        self.assertEqual(coll["names"], [("a", [0x10, 0x20])])
        self.assertEqual(coll["addrs"], [])

    def test_two_names_on_one_address_is_reported(self):
        coll = gsm.collisions([("a", 0x10, 1.0), ("b", 0x10, 1.0)])
        self.assertEqual(coll["addrs"], [(0x10, ["a", "b"])])


class PrefixPassTest(unittest.TestCase):
    """The opt-in fourth pass: a routine EDITED between the two games, found by its prologue."""

    PROLOGUE = [addiu(29, 29, -0x30), sw(RA, 29, 0x20), sw(S0, 29, 0x18), addu(S0, A0, 0),
                lw(V0, S0, 0x0C), addu(A0, V0, 0), subu(A1, A1, A0), xor(T0, A0, A1),
                mult(V0, T0), addu(V0, V0, T0), subu(T0, V0, A1), xor(A0, T0, V0),
                addu(A1, A0, T0), subu(V0, A1, A0), mult(A0, A1), addu(V0, V0, A0)]

    def _sides(self, tail_len):
        """Two images: `edited` shares a prologue and differs after it; `same` is identical."""
        same = _pad([addu(V0, A0, A1), subu(V0, V0, A0), xor(A1, V0, A0), mult(V0, A1),
                     addu(V0, V0, A1), subu(A0, A1, V0), jr_ra()])

        def image(base, tail_word, tail_words):
            edited = self.PROLOGUE + [tail_word] * tail_words + [jr_ra(), NOP]
            rows = []
            at = base
            for name, words in (("edited", edited), ("same", same)):
                blob = _blob(words)
                rows.append((at, at + len(blob), name, blob))
                at += len(blob) + 0x10
            return rows

        demo = image(0x00140000, addu(S0, S0, V0), 16)
        ours = image(0x00280000, subu(S0, V0, S0), tail_len)
        return demo, [(s, e, "FUN_%08x" % s, c) for s, e, _n, c in ours]

    def test_off_by_default(self):
        demo, ours = self._sides(16)
        self.assertNotIn("edited", [n for n, _a, _s in gsm.match(demo, ours)])

    def test_an_edited_body_is_found_by_its_prologue(self):
        demo, ours = self._sides(24)
        hows = {}
        pairs = gsm.match(demo, ours, hows=hows, prefix=True)
        self.assertIn("edited", [n for n, _a, _s in pairs])
        self.assertEqual(hows["edited"], "prefix")
        self.assertEqual(dict((n, s) for n, _a, s in pairs)["edited"], 0.6)

    def test_an_equal_length_body_says_so(self):
        demo, ours = self._sides(16)
        hows = {}
        pairs = gsm.match(demo, ours, hows=hows, prefix=True)
        self.assertEqual(hows["edited"], "prefix+size")
        self.assertEqual(dict((n, s) for n, _a, s in pairs)["edited"], 0.7)

    def test_a_prefix_pair_can_never_reach_the_rename_line(self):
        demo, ours = self._sides(16)
        strong = gsm.match(demo, ours, min_score=gsm.GOOD, prefix=True)
        self.assertNotIn("edited", [n for n, _a, _s in strong])
        self.assertLess(max(gsm.METHOD_SCORE["prefix"], gsm.METHOD_SCORE["prefix+size"]), gsm.GOOD)


if __name__ == "__main__":
    unittest.main()
