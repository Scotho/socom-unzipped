"""Sprint 12 Task 15 -- the `callgraph` lever (tools_py/callgraph_lever, research/52).

The fixture is two tiny images of hand-assembled MIPS, the demo's and ours, at different bases. A
function is a fixed-size body whose first words are `jal`s to chosen targets; the rest is register
arithmetic. The anchors are given by hand as (demo address, our address) pairs -- the call graph is
the only evidence under test, so no fingerprint pass runs. Our rows carry Ghidra placeholder names
(`FUN_<addr>`), the demo's carry the names a proposal would use.

No disc, no demo, no ELF on disk.
"""
import csv
import os
import tempfile
import unittest

from tools_py import address_matcher as am
from tools_py import callgraph_lever as cg


def addu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21
def jal(target):         return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)
def jr_ra():             return (31 << 21) | 8
NOP = 0
SIZE = 0x40                                        # sixteen words: MIN_BODY exactly
DEMO_BASE, OUR_BASE = 0x00140000, 0x00280000


def build(base, layout, calls, placeholder):
    """(Side, {name: address}) -- `layout` in link order, each body `SIZE` bytes, `calls` {name: [target]}."""
    addr = {n: base + i * SIZE for i, n in enumerate(layout)}
    blob, rows = b"", []
    for i, n in enumerate(layout):
        words = []
        for t in calls.get(n, ()):
            words += [jal(addr[t]), NOP]
        while len(words) < SIZE // 4 - 2:
            words.append(addu(8 + (len(words) + i) % 8, 4, 5))
        words += [jr_ra(), NOP]
        blob += b"".join((w & 0xFFFFFFFF).to_bytes(4, "little") for w in words)
        rows.append((addr[n], addr[n] + SIZE, "FUN_%08x" % addr[n] if placeholder else n))
    return am.Side(rows, [(base, blob)]), addr


def sides(layout, calls, our_layout=None, our_calls=None):
    demo, d = build(DEMO_BASE, layout, calls, placeholder=False)
    ours, o = build(OUR_BASE, our_layout or layout, calls if our_calls is None else our_calls, placeholder=True)
    return demo, d, ours, o


def run(demo, d, ours, o, anchor_names, holds=()):
    anchors = [(d[n], o[n]) for n in anchor_names]
    return cg.callgraph_pass(demo, ours, anchors, holds={o[n] for n in holds})


def paired(result):
    """{demo address: our address} over every round."""
    return {p.demo_addr: p.our_addr for p in result.pairs}


A = ["A0", "A1", "A2", "A3", "A4"]


class GraphTest(unittest.TestCase):
    def test_jal_targets_become_edges_and_a_target_outside_every_row_is_counted(self):
        demo, d = build(DEMO_BASE, ["A0", "F"], {"F": ["A0"]}, placeholder=False)
        g = cg.graphs(demo)
        self.assertEqual(g.callees[d["F"]], {d["A0"]})
        self.assertEqual(g.callers[d["A0"]], {d["F"]})
        self.assertEqual(g.stats["jal outside every table row"], 0)
        # a jal to an address no row covers
        rows = [(s, e, n) for s, e, n in demo.funcs if n != "A0"]
        cut = am.Side(rows, demo.image.segments)
        self.assertEqual(cg.graphs(cut).stats["jal outside every table row"], 1)

    def test_keys_map_our_callees_to_demo_addresses(self):
        demo, d, ours, o = sides(["A0", "A1", "F"], {"F": ["A0", "A1"]})
        k = cg.keys(cg.graphs(ours), {o["A0"]: d["A0"], o["A1"]: d["A1"]})
        self.assertEqual(k["callee"][o["F"]], frozenset({d["A0"], d["A1"]}))
        self.assertEqual(k["caller"][o["A0"]], frozenset())


class PassTest(unittest.TestCase):
    def test_a_unique_callee_set_pairs(self):
        layout = ["A0", "F", "A1", "G", "A2"]
        calls = {"F": ["A0", "A1"], "G": ["A2"]}
        demo, d, ours, o = sides(layout, calls)
        res = run(demo, d, ours, o, ["A0", "A1", "A2"])
        got = paired(res)
        self.assertEqual(got.get(d["F"]), o["F"])
        self.assertEqual(got.get(d["G"]), o["G"])
        f = next(p for p in res.pairs if p.demo_addr == d["F"])
        self.assertEqual((f.round, f.kinds[0], f.order), (1, "callee", "between"))

    def test_a_callee_set_two_functions_share_does_not_pair(self):
        layout = ["A0", "F", "A1", "F2", "A2"]
        calls = {"F": ["A0", "A1"], "F2": ["A0", "A1"]}
        demo, d, ours, o = sides(layout, calls)
        got = paired(run(demo, d, ours, o, ["A0", "A1", "A2"]))
        self.assertNotIn(d["F"], got)
        self.assertNotIn(d["F2"], got)

    def test_a_caller_only_key_pairs(self):
        # H calls nothing; two anchors call it, so |K_caller| = 2 and the caller rule (K >= 2) holds.
        layout = ["A0", "H", "A1", "A2"]
        calls = {"A0": ["H"], "A1": ["H"]}
        demo, d, ours, o = sides(layout, calls)
        res = run(demo, d, ours, o, ["A0", "A1", "A2"])
        self.assertEqual(paired(res).get(d["H"]), o["H"])
        h = next(p for p in res.pairs if p.demo_addr == d["H"])
        self.assertEqual(h.kinds, ("caller",))
        self.assertEqual(h.ksizes, (2,))

    def test_one_caller_is_not_enough(self):
        layout = ["A0", "H", "A1", "A2"]
        demo, d, ours, o = sides(layout, {"A0": ["H"]})
        self.assertNotIn(d["H"], paired(run(demo, d, ours, o, ["A0", "A1", "A2"])))

    def test_link_order_outside_refuses(self):
        # In ours F sits after A2, outside the bracket (A0, A1) its demo neighbours give.
        layout = ["A0", "F", "A1", "A2"]
        demo, d, ours, o = sides(layout, {"F": ["A0", "A1"]}, our_layout=["A0", "A1", "A2", "F"])
        res = run(demo, d, ours, o, ["A0", "A1", "A2"])
        self.assertNotIn(d["F"], paired(res))
        self.assertEqual(res.census["refused: link order outside"], 1)

    def test_a_second_round_uses_the_first_rounds_pairs_and_goes_to_the_loose_file(self):
        # K calls only F; F is unplaced until round 1 pairs it through {A0, A1}.
        layout = ["A0", "F", "A1", "K", "A2"]
        calls = {"F": ["A0", "A1"], "K": ["F"]}
        demo, d, ours, o = sides(layout, calls)
        res = run(demo, d, ours, o, ["A0", "A1", "A2"])
        by_d = {p.demo_addr: p for p in res.pairs}
        self.assertEqual(by_d[d["F"]].round, 1)
        self.assertEqual(by_d[d["K"]].round, 2)
        self.assertEqual(by_d[d["K"]].our_addr, o["K"])
        self.assertEqual(res.per_round, [1, 1])
        strict, loose, _held = cg.proposals(res, demo, ours)
        self.assertEqual([r["Proposed"] for r in strict], ["F"])
        self.assertEqual([r["Proposed"] for r in loose], ["K"])
        self.assertEqual((strict[0]["Score"], loose[0]["Score"]), ("0.80", "0.75"))
        self.assertEqual(strict[0]["How"], "callgraph")
        self.assertTrue(strict[0]["Evidence"].startswith("callgraph round 1; key=callee; |K|=2; order="))
        self.assertTrue(loose[0]["Evidence"].startswith("callgraph round 2; "))

    def test_a_held_address_is_not_an_anchor(self):
        layout = ["A0", "J", "A1", "A2"]
        calls = {"J": ["A1"]}
        demo, d, ours, o = sides(layout, calls)
        self.assertIn(d["J"], paired(run(demo, d, ours, o, ["A0", "A1", "A2"])))
        res = run(demo, d, ours, o, ["A0", "A1", "A2"], holds=["A1"])
        self.assertNotIn(d["J"], paired(res))
        self.assertEqual(res.census["anchors excluded: held"], 1)
        self.assertNotIn(o["A1"], {x for _d, x in res.anchors})


class ProposalsTest(unittest.TestCase):
    def setUp(self):
        layout = ["A0", "F", "A1", "K", "A2"]
        calls = {"F": ["A0", "A1"], "K": ["F"]}
        self.demo, self.d, self.ours, self.o = sides(layout, calls)
        self.res = run(self.demo, self.d, self.ours, self.o, ["A0", "A1", "A2"])

    def test_an_identifier_another_file_spends_elsewhere_is_refused(self):
        other = {"x.csv": [(0x00999990, "F")]}
        strict, _loose, held = cg.proposals(self.res, self.demo, self.ours, others=other)
        self.assertEqual(strict, [])
        self.assertEqual(held["refused: identifier spent by another file at another address"], 1)

    def test_the_same_name_at_the_same_address_in_another_file_is_an_agreement(self):
        other = {"x.csv": [(self.o["F"], "F")]}
        strict, _loose, held = cg.proposals(self.res, self.demo, self.ours, others=other)
        self.assertEqual([r["Proposed"] for r in strict], ["F"])
        self.assertEqual(held.get("agrees with another file"), 1)

    def test_the_header_carries_the_rule_and_the_strict_path_refuses_a_later_round(self):
        strict, loose, _held = cg.proposals(self.res, self.demo, self.ours)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "renames_callgraph.csv")
            header = cg.header_lines(path, self.res, holdout_lines=None, anchor_note="3 synthetic")
            cg.write_proposals(path, strict, header)
            with open(path) as fh:
                text = fh.read()
            self.assertIn(cg.CALLGRAPH_RULE, text)
            self.assertIn("round 1: 1", text)
            body = [ln for ln in text.splitlines() if not ln.startswith("#")]
            rows = list(csv.DictReader(body))
            self.assertEqual(rows[0]["Proposed"], "F")
            with self.assertRaises(ValueError):
                cg.write_proposals(path, loose, header)
            cg.write_proposals(cg.loose_path(path), loose, header)


if __name__ == "__main__":
    unittest.main()
