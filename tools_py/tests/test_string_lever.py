"""Sprint 12 Task 12 -- the `string-set` pass (tools_py/string_lever.py; research/53 rule R3).

Synthetic images only: each side is one segment of hand-assembled MIPS followed by a rodata run of
NUL-terminated strings, and a function "references" a string by forming its address with a
`lui` + `addiu` pair, exactly as `address_matcher.formed_addresses` reads it. The two sides put the
same strings and the same functions at different addresses. No disc, no demo, no ELF on disk.
"""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from tools_py import address_matcher as am
from tools_py import string_lever as sv
from tools_py import symbol_levers as sl


# ---- the tiny assembler the Task 7 / 7b suites use -----------------------------------------------

def lui(rt, imm):        return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)
def addiu(rt, rs, imm):  return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def addu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21
def subu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x23
def jal(target):         return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)
def jr_ra():             return (31 << 21) | 8
NOP = 0
V0, A0, A1, T0 = 2, 4, 5, 8


def _blob(words):
    return b"".join((w & 0xFFFFFFFF).to_bytes(4, "little") for w in words)


def _body(size, str_addrs, callee_addrs, salt):
    words = []
    for a in str_addrs:
        words += [lui(A0, ((a + 0x8000) >> 16) & 0xFFFF), addiu(A0, A0, a & 0xFFFF)]
    for t in callee_addrs:
        words += [jal(t), NOP]
    i = 0
    while len(words) < size // 4 - 2:
        words.append(addu(T0, T0, V0) if (i + salt) % 2 else subu(V0, V0, A1))
        i += 1
    assert len(words) == size // 4 - 2, "a body spec does not fit its size"
    return words + [jr_ra(), NOP]


STRINGS = {
    "alpha": b"alpha routine text", "beta": b"beta routine text", "gamma": b"gamma shared text",
    "delta": b"delta wandering text", "eps": b"epsilon disjoint text", "zeta": b"zeta small body",
    "named": b"a row we named by hand", "spent": b"an identifier already spent",
    "sib1": b"sibling one stamp %s", "sib2": b"sibling two stamp", "held": b"held pair text",
}


def build(base, specs, names):
    """(rows, [(base, blob)], addr) -- one segment: the functions in order, then the strings.

    `specs` is [(key, size, [string keys], [callee keys])]; `names` maps key -> the row's name.
    """
    addr, cursor = {}, base
    for key, size, _s, _c in specs:
        addr[key] = cursor
        cursor += size
    cursor = (cursor + 15) & ~15
    s_addr, rodata = {}, b""
    for key, text in STRINGS.items():
        s_addr[key] = cursor + len(rodata)
        rodata += text + b"\x00"
        while len(rodata) % 4:
            rodata += b"\x00"
    code = b""
    rows = []
    for salt, (key, size, strs, callees) in enumerate(specs):
        code += _blob(_body(size, [s_addr[s] for s in strs], [addr[c] for c in callees], salt))
        rows.append((addr[key], addr[key] + size, names(key, addr[key])))
    pad = b"\x00" * (((len(code) + 15) & ~15) - len(code))
    return rows, [(base, code + pad + rodata)], addr


DEMO_BASE, OUR_BASE = 0x00140000, 0x00280000


def demo_name(key, _addr):
    return "%s__5CTestFv" % key.capitalize()


def our_name(key, a):
    return "HandNamed" if key == "named" else "FUN_%08x" % a


def anchor(k):
    return ("a%d" % k, 64, [], [])


# The main fixture. On both sides: anchors a0..a3 and, between them, the candidates:
#   cand   -- {alpha, beta}, calls a0, between a0 and a1 on both sides: the one strict pair
#   twinA/twinB -- both {gamma}: a set two functions share, so neither pairs
#   wander -- {delta}, calls a0; between a0/a1 in the demo but between a2/a3 in ours: `outside`
#   disj   -- {eps}; calls a2 in the demo and a3 in ours: callees `disjoint`
#   small  -- {zeta}, 32 bytes on both sides: under MIN_BODY
#   named  -- {named}, calls a0, between a2/a3; our row carries a hand name
#   spent  -- {spent}, calls a0, between a2/a3; its identifier is passed as already taken
DEMO_SPECS = [anchor(0), ("cand", 96, ["alpha", "beta"], ["a0"]), ("wander", 80, ["delta"], ["a0"]),
              anchor(1), ("twinA", 64, ["gamma"], []), ("twinB", 64, ["gamma"], []), anchor(2),
              ("disj", 72, ["eps"], ["a2"]), ("small", 32, ["zeta"], []),
              ("named", 64, ["named"], ["a0"]), ("spent", 64, ["spent"], ["a0"]), anchor(3)]
OUR_SPECS = [anchor(0), ("cand", 112, ["alpha", "beta"], ["a0"]), anchor(1),
             ("twinA", 64, ["gamma"], []), ("twinB", 64, ["gamma"], []), anchor(2),
             ("wander", 80, ["delta"], ["a0"]), ("disj", 72, ["eps"], ["a3"]),
             ("small", 32, ["zeta"], []), ("named", 64, ["named"], ["a0"]),
             ("spent", 64, ["spent"], ["a0"]), anchor(3)]


def fixture(demo_specs=DEMO_SPECS, our_specs=OUR_SPECS):
    d_rows, d_segs, d_addr = build(DEMO_BASE, demo_specs, demo_name)
    o_rows, o_segs, o_addr = build(OUR_BASE, our_specs, our_name)
    demo, ours = am.Side(d_rows, d_segs), am.Side(o_rows, o_segs)
    anchors = [(d_addr[k], o_addr[k], "exact") for k in d_addr if k.startswith("a") and k[1:].isdigit()]
    return demo, ours, sorted(anchors), d_addr, o_addr


class KeysTest(unittest.TestCase):
    def test_string_keys_are_the_shared_strings_a_body_forms_the_address_of(self):
        demo, ours, _anchors, d, o = fixture()
        kd, ko = sv.shared_keys(demo, ours)
        self.assertEqual(kd[d["cand"]], frozenset({STRINGS["alpha"], STRINGS["beta"]}))
        self.assertEqual(ko[o["cand"]], kd[d["cand"]])
        self.assertNotIn(d["a0"], kd)                      # an empty key is left out: it never pairs

    def test_string_keys_agree_with_side_anchors(self):
        demo, _ours, _a, d, _o = fixture()
        keys = sv.string_keys(demo)
        self.assertEqual(tuple(sorted(keys[d["cand"]])), demo.anchors(d["cand"]))


class StringPassTest(unittest.TestCase):
    def setUp(self):
        self.demo, self.ours, self.anchors, self.d, self.o = fixture()
        self.strict, self.loose, self.census = sv.string_pass(
            self.demo, self.ours, self.anchors, taken=["Spent__5CTestFv"])
        self.strict_pairs = {(c.demo_addr, c.our_addr) for c in self.strict}
        self.loose_pairs = {(c.demo_addr, c.our_addr) for c in self.loose}

    def pair(self, key):
        return (self.d[key], self.o[key])

    def test_a_unique_string_set_pairs(self):
        self.assertIn(self.pair("cand"), self.strict_pairs)
        c = next(c for c in self.strict if c.demo_addr == self.d["cand"])
        self.assertEqual((c.order, c.callees, c.strings), ("between", "overlap", 2))
        self.assertEqual(c.evidence, "strings=2;order=between;callees=overlap")
        self.assertEqual(c.level, "strict")

    def test_a_set_two_functions_share_does_not_pair(self):
        for key in ("twinA", "twinB"):
            self.assertNotIn(self.d[key], {p[0] for p in self.strict_pairs | self.loose_pairs})

    def test_an_outside_link_order_refuses(self):
        self.assertNotIn(self.pair("wander"), self.strict_pairs)
        c = next(c for c in self.loose if c.demo_addr == self.d["wander"])
        self.assertEqual((c.order, c.callees), ("outside", "overlap"))   # overlap alone does not save it

    def test_disjoint_callees_refuse(self):
        self.assertNotIn(self.pair("disj"), self.strict_pairs)
        c = next(c for c in self.loose if c.demo_addr == self.d["disj"])
        self.assertEqual((c.order, c.callees), ("between", "disjoint"))  # between alone does not save it

    def test_a_body_under_64_bytes_refuses_even_at_the_loose_level(self):
        self.assertNotIn(self.pair("small"), self.strict_pairs | self.loose_pairs)
        self.assertGreaterEqual(self.census["body under 64 B"], 1)

    def test_a_hand_named_row_and_a_spent_identifier_refuse(self):
        self.assertNotIn(self.pair("named"), self.strict_pairs | self.loose_pairs)
        self.assertNotIn(self.pair("spent"), self.strict_pairs | self.loose_pairs)
        self.assertEqual(self.census["our row already named"], 1)
        self.assertEqual(self.census["identifier spent or collides"], 1)

    def test_strict_and_loose_are_disjoint_and_loose_is_r0_minus_r3(self):
        self.assertEqual(self.strict_pairs, {self.pair("cand")})
        self.assertEqual(self.loose_pairs, {self.pair("wander"), self.pair("disj")})
        # named and spent clear R3 and are then refused by the name hurdles, so R3 counts them
        self.assertEqual((self.census["R0"], self.census["R3"]), (5, 3))
        self.assertEqual(self.census["R0"], self.census["R3"] + len(self.loose))

    def test_the_rule_constant_carries_its_thresholds(self):
        for text in ("64", "0.50", "outside", "between", "overlap", "0.80", "string-set"):
            self.assertIn(text, sv.STRING_RULE)


class ProposalsFileTest(unittest.TestCase):
    def setUp(self):
        demo, ours, anchors, _d, _o = fixture()
        self.strict, self.loose, _c = sv.string_pass(demo, ours, anchors, taken=["Spent__5CTestFv"])

    def test_a_row_carries_score_how_and_evidence(self):
        row = sv.proposal_rows(self.strict)[0]
        self.assertEqual((row["Score"], row["How"], row["Proposed"]), ("0.80", "string-set", "Cand__5CTestFv"))
        self.assertEqual(row["Evidence"], "strings=2;order=between;callees=overlap")

    def test_the_strict_path_refuses_a_loose_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "demo_symbol_renames_strings.csv")
            with self.assertRaises(ValueError):
                sv.write_proposals(path, sv.proposal_rows(self.loose), ["rule"])
            self.assertFalse(os.path.exists(path))

    def test_the_loose_path_refuses_a_strict_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = sl.loose_path(os.path.join(tmp, "demo_symbol_renames_strings.csv"))
            with self.assertRaises(ValueError):
                sv.write_proposals(path, sv.proposal_rows(self.strict), ["rule"])
            self.assertFalse(os.path.exists(path))

    def test_each_path_takes_its_own_rows_under_a_hash_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "demo_symbol_renames_strings.csv")
            sv.write_proposals(path, sv.proposal_rows(self.strict), [sv.STRING_RULE])
            sv.write_proposals(sl.loose_path(path), sv.proposal_rows(self.loose), [sv.STRING_RULE])
            with open(path) as fh:
                text = fh.read()
            self.assertTrue(text.startswith("# string-set"))
            self.assertIn("Cand__5CTestFv", text)
            with open(sl.loose_path(path)) as fh:
                self.assertIn("Wander__5CTestFv", fh.read())


# Siblings: Task 7's answer is crossed (sibA's demo on our sibB and the reverse), as row 478 was.
SIB_DEMO = [anchor(0), anchor(1), ("sibA", 64, ["sib1"], ["a0"]), ("sibB", 64, ["sib2"], ["a0"]),
            anchor(2), anchor(3), anchor(4), anchor(5)]


def sibling_fixture():
    demo, ours, anchors, d, o = fixture(SIB_DEMO, SIB_DEMO)
    crossed = [(d["sibA"], o["sibB"], "exact"), (d["sibB"], o["sibA"], "exact")]
    return demo, ours, sorted(anchors + crossed), d, o


class ContradictionsTest(unittest.TestCase):
    def test_a_string_key_that_contradicts_a_task_7_pair_is_reported(self):
        demo, ours, anchors, d, o = sibling_fixture()
        found = sv.contradictions(demo, ours, anchors)
        got = {(c["demo_addr"], c["our_addr"]) for c in found}
        self.assertEqual(got, {(d["sibA"], o["sibA"]), (d["sibB"], o["sibB"])})
        line = next(c for c in found if c["demo_addr"] == d["sibA"])
        self.assertEqual(line["task7_our"], o["sibB"])
        self.assertIn("set", line["kinds"])

    def test_an_agreeing_anchor_is_not_reported(self):
        demo, ours, _anchors, d, o = fixture()
        anchors = sorted(_anchors + [(d["cand"], o["cand"], "exact")])
        self.assertEqual(sv.contradictions(demo, ours, anchors), [])


# The holdout fixture: `held` is a PROVED Task 7 pair with a unique string set, between a1 and a2 and
# calling a0 on both sides, so with the other pairs kept the pass re-derives it.
HELD = [anchor(0), anchor(1), ("held", 64, ["held"], ["a0"]), anchor(2), anchor(3), anchor(4)]


class HoldoutTest(unittest.TestCase):
    def test_the_holdout_re_derives_a_held_out_pair(self):
        demo, ours, anchors, d, o = fixture(HELD, HELD)
        anchors = sorted(anchors + [(d["held"], o["held"], "exact")])
        got = sv.holdout(demo, ours, anchors, folds=3, block=1)
        self.assertEqual((got["re-derived"], got["wrong"]), (1, 0))

    def test_a_prefix_pair_is_never_held_out(self):
        demo, ours, anchors, d, o = fixture(HELD, HELD)
        anchors = sorted(anchors + [(d["held"], o["held"], "prefix")])
        got = sv.holdout(demo, ours, anchors, folds=3, block=1)
        self.assertEqual(got["re-derived"], 0)

    def test_the_wrong_counter_counts_and_a_correction_rights_it(self):
        demo, ours, anchors, d, o = sibling_fixture()
        got = sv.holdout(demo, ours, anchors, folds=3, block=2)
        self.assertEqual((got["re-derived"], got["wrong"]), (2, 2))
        fixed = sv.holdout(demo, ours, anchors, folds=3, block=2,
                           corrections={o["sibA"]: d["sibA"], o["sibB"]: d["sibB"]})
        self.assertEqual((fixed["re-derived"], fixed["wrong"], fixed["wrong by Task 7"]), (2, 0, 2))


class CliTest(unittest.TestCase):
    def test_missing_inputs_are_one_sentence_and_exit_2(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = sv.main(["/nonexistent/demo", "/nonexistent/elf", "/nonexistent/csv",
                            "/nonexistent/json", "--out", "/nonexistent/out.csv"])
        self.assertEqual(code, 2)
        self.assertIn("NO-DATA", buf.getvalue())

    def test_the_out_path_may_not_be_a_loose_path(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = sv.main(["a", "b", "c", "d", "--out", "x_loose.csv"])
        self.assertEqual(code, 2)
        self.assertIn("loose", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
