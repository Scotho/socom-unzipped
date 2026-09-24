"""Sprint 12 Task 6 -- the `bindiff` lever (tools_py/bindiff_lever, research/49, S12-R22).

The BinDiff result is a synthetic SQLite database in BinDiff 8's schema (the two tables the lever reads,
`functionalgorithm` and `function`, with a handful of rows), built in a temporary directory. Task 7's
pairs are a hand-written `details` map in `ghidra_symbol_match.match`'s shape. Our rows carry Ghidra
placeholder names (`FUN_<addr>`), the demo's the names a proposal would use.

No disc, no demo, no ELF, nothing under game/.
"""
import csv
import os
import sqlite3
import tempfile
import unittest

from tools_py import bindiff_lever as bl

HASH = "function: hash matching"
EDGES = "function: edges flowgraph MD index"
PRIME = "function: prime signature matching"
ADDRSEQ = "function: address sequence"
CALLREF = "function: call reference matching"

ALGORITHMS = [(1, HASH), (2, EDGES), (3, "function: edges callgraph MD index"),
              (4, "function: MD index matching (flowgraph MD index, top down)"),
              (5, "function: MD index matching (flowgraph MD index, bottom up)"), (6, PRIME),
              (9, "function: relaxed MD index matching"), (11, ADDRSEQ), (17, CALLREF)]


def make_db(path, rows):
    """A BinDiff 8 result holding `rows` = [(address1, address2, similarity, confidence, algorithm id)]."""
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE functionalgorithm (id SMALLINT PRIMARY KEY,name TEXT)")
    db.execute("CREATE TABLE function (id INT,address1 BIGINT,name1 TEXT,address2 BIGINT,name2 TEXT,"
               "similarity DOUBLE PRECISION,confidence DOUBLE PRECISION,flags INTEGER,algorithm SMALLINT,"
               "evaluate BOOLEAN,commentsported BOOLEAN,basicblocks INTEGER,edges INTEGER,instructions INTEGER,"
               "UNIQUE(address1, address2),PRIMARY KEY(id))")
    db.executemany("INSERT INTO functionalgorithm VALUES (?, ?)", ALGORITHMS)
    for i, (a1, a2, sim, conf, alg) in enumerate(rows, 1):
        db.execute("INSERT INTO function VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (i, a1, "n%d" % i, a2, "sub_%X" % a2, sim, conf, 0, alg, 0, 0, 3, 2, 20))
    db.commit()
    db.close()


def M(a, b, sim=1.0, alg=PRIME, conf=0.9):
    return bl.Match(a, b, sim, conf, alg)


# demo 0x1000.. / ours 0x2000..; sizes chosen per case
D_PFX, O_PFX = 0x1000, 0x2000          # a Task 7 prefix pair BinDiff confirms
D_PFX2, O_PFX2 = 0x1100, 0x2100        # a Task 7 prefix pair BinDiff contradicts
D_PFX3, O_PFX3 = 0x1200, 0x2200        # a Task 7 prefix pair BinDiff pairs elsewhere BELOW the rule
D_EX, O_EX = 0x1300, 0x2300            # a Task 7 exact pair (never a prefix+bindiff row)
D_NEW, O_NEW = 0x1400, 0x2400          # a BinDiff pair outside the 987
D_NAMED, O_NAMED = 0x1500, 0x2500      # ... onto a row of ours that already carries a name
D_OTHER, O_OTHER = 0x1600, 0x2600      # the demo function BinDiff pairs our O_PFX2 with

SIZES = bl.Sizes(
    demo={D_PFX: 236, D_PFX2: 200, D_PFX3: 300, D_EX: 128, D_NEW: 464, D_NAMED: 96, D_OTHER: 200},
    ours={O_PFX: 248, O_PFX2: 200, O_PFX3: 320, O_EX: 128, O_NEW: 516, O_NAMED: 96, O_OTHER: 200,
          0x2900: 200})
DEMO_NAMES = {D_PFX: "Flash__4CHUDFv", D_PFX2: "Tick__5CThingFv", D_PFX3: "Open__5CDoorFv",
              D_EX: "memcpy", D_NEW: "sceFsInit", D_NAMED: "strlen", D_OTHER: "Tock__5CThingFv"}
OUR_NAMES = {a: "FUN_%08x" % a for a in SIZES.ours}
OUR_NAMES[O_NAMED] = "strlen"
DETAILS = {
    (DEMO_NAMES[D_PFX], O_PFX): {"how": "prefix", "size": 248, "demo_addr": D_PFX},
    (DEMO_NAMES[D_PFX2], O_PFX2): {"how": "prefix+size", "size": 200, "demo_addr": D_PFX2},
    (DEMO_NAMES[D_PFX3], O_PFX3): {"how": "prefix", "size": 320, "demo_addr": D_PFX3},
    (DEMO_NAMES[D_EX], O_EX): {"how": "exact", "size": 128, "demo_addr": D_EX},
}
MATCHES = [
    M(D_PFX, O_PFX, 0.97, EDGES),               # confirms the prefix pair
    M(D_OTHER, O_PFX2, 1.0, PRIME),             # pairs our O_PFX2 with ANOTHER demo function, under the rule
    M(D_PFX3, 0x2900, 0.20, ADDRSEQ),           # parks D_PFX3 elsewhere, but not under the rule
    M(D_EX, O_EX, 1.0, HASH),                   # agrees with the exact pair
    M(D_NEW, O_NEW, 0.957, EDGES),              # a new pair under the rule
    M(D_NAMED, O_NAMED, 1.0, PRIME),            # a new pair onto a named row of ours
]


class ReadBinDiffTest(unittest.TestCase):
    def test_reads_matches_with_their_matcher_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a_vs_b.BinDiff")
            make_db(path, [(0x1000, 0x2000, 0.97, 0.5, 2), (0x1100, 0x2100, 0.25, 0.1, 11),
                           (0x1200, 0x2200, 1.0, 0.99, 6)])
            got = bl.read_bindiff(path)
        self.assertEqual(sorted(got), [bl.Match(0x1000, 0x2000, 0.97, 0.5, EDGES),
                                       bl.Match(0x1100, 0x2100, 0.25, 0.1, ADDRSEQ),
                                       bl.Match(0x1200, 0x2200, 1.0, 0.99, PRIME)])

    def test_rule_matchers_are_research_49s_structural_six(self):
        self.assertEqual(len(bl.RULE_MATCHERS), 6)
        for name in (HASH, EDGES, PRIME, "function: relaxed MD index matching",
                     "function: MD index matching (flowgraph MD index, top down)",
                     "function: MD index matching (flowgraph MD index, bottom up)"):
            self.assertIn(name, bl.RULE_MATCHERS)
        for name in (ADDRSEQ, CALLREF, "function: edges callgraph MD index", "function: instruction count",
                     "function: call sequence matching(sequence)"):
            self.assertNotIn(name, bl.RULE_MATCHERS)
        self.assertEqual(bl.BINDIFF_MIN_SIMILARITY, 0.95)


class UnderRuleTest(unittest.TestCase):
    def sizes(self, d, o):
        return bl.Sizes(demo={1: d}, ours={2: o})

    def test_accepts_a_structural_match_over_the_cuts(self):
        self.assertTrue(bl.under_rule(M(1, 2, 0.97, PRIME), self.sizes(128, 128)))
        self.assertTrue(bl.under_rule(M(1, 2, 0.95, EDGES), self.sizes(64, 128)))     # both boundaries

    def test_refuses_a_positional_matcher(self):
        self.assertFalse(bl.under_rule(M(1, 2, 1.0, ADDRSEQ), self.sizes(128, 128)))
        self.assertFalse(bl.under_rule(M(1, 2, 1.0, CALLREF), self.sizes(128, 128)))

    def test_refuses_a_small_body_on_either_side(self):
        self.assertFalse(bl.under_rule(M(1, 2, 1.0, PRIME), self.sizes(60, 64)))
        self.assertFalse(bl.under_rule(M(1, 2, 1.0, PRIME), self.sizes(64, 60)))
        self.assertFalse(bl.under_rule(M(1, 2, 1.0, PRIME), bl.Sizes(demo={}, ours={2: 128})))

    def test_refuses_a_size_ratio_under_half(self):
        self.assertFalse(bl.under_rule(M(1, 2, 1.0, PRIME), self.sizes(64, 132)))

    def test_refuses_a_similarity_under_the_threshold(self):
        self.assertFalse(bl.under_rule(M(1, 2, 0.9499, PRIME), self.sizes(128, 128)))


class PrefixBinDiffTest(unittest.TestCase):
    def setUp(self):
        self.cands, self.contra, self.census = bl.prefix_bindiff(DETAILS, MATCHES, SIZES, OUR_NAMES)

    def test_a_confirmed_prefix_pair_is_a_strict_row(self):
        self.assertEqual([(c.our_addr, c.demo_addr, c.how) for c in self.cands],
                         [(O_PFX, D_PFX, "prefix+bindiff")])
        c = self.cands[0]
        self.assertEqual(c.score, 0.80)
        self.assertEqual(c.demo_name, "Flash__4CHUDFv")
        self.assertEqual(c.evidence, "prologue unique both sides + BinDiff edges flowgraph MD index 0.970, 236/248 B")
        rows, _census = bl.proposals(self.cands)
        self.assertEqual(rows[0]["How"], "prefix+bindiff")
        self.assertEqual(rows[0]["Score"], "0.80")
        self.assertEqual(rows[0]["Proposed"], "Flash__4CHUDFv")

    def test_a_contradicted_prefix_pair_is_reported_not_proposed(self):
        self.assertEqual(len(self.contra), 1)
        x = self.contra[0]
        self.assertEqual((x.demo_addr, x.our_addr), (D_PFX2, O_PFX2))
        self.assertEqual((x.match.address_a, x.match.address_b), (D_OTHER, O_PFX2))
        self.assertEqual(self.census["contradicted"], 1)

    def test_a_disagreement_below_the_rule_is_unconfirmed_and_exact_pairs_are_not_read(self):
        self.assertEqual(self.census["prologue pairs"], 3)
        self.assertEqual(self.census["unconfirmed"], 1)
        self.assertEqual(self.census["confirmed"], 1)


class BinDiffNewTest(unittest.TestCase):
    def anchors(self):
        return [(info["demo_addr"], o, info["how"]) for (_n, o), info in DETAILS.items()]

    def test_a_new_pair_goes_to_the_loose_file(self):
        cands, census = bl.bindiff_new(MATCHES, self.anchors(), SIZES, DEMO_NAMES, OUR_NAMES)
        self.assertEqual([(c.our_addr, c.demo_addr, c.how, c.score) for c in cands],
                         [(O_NEW, D_NEW, "bindiff", 0.75)])
        self.assertEqual(cands[0].evidence, "BinDiff edges flowgraph MD index 0.957, 464/516 B; no other key")
        self.assertEqual(census["refused: our row not a placeholder"], 1)
        # the rule pairs touching the 987 (the exact agreement, the prefix confirmation, the contradiction)
        self.assertEqual(census["a side is one of the anchors"], 3)

    def test_the_strict_path_refuses_a_bindiff_row(self):
        cands, _census = bl.bindiff_new(MATCHES, self.anchors(), SIZES, DEMO_NAMES, OUR_NAMES)
        rows, _c = bl.proposals(cands)
        with tempfile.TemporaryDirectory() as tmp:
            strict = os.path.join(tmp, "demo_symbol_renames_bindiff.csv")
            with self.assertRaises(ValueError):
                bl.write_proposals(strict, rows, ["h"])
            loose = os.path.join(tmp, "demo_symbol_renames_bindiff_loose.csv")
            bl.write_proposals(loose, rows, ["h"])
            with open(loose) as fh:
                got = list(csv.DictReader(l for l in fh if not l.startswith("#")))
        self.assertEqual([(r["Address"], r["How"], r["Score"]) for r in got], [("0x%08x" % O_NEW, "bindiff", "0.75")])

    def test_the_loose_path_refuses_a_prefix_bindiff_row(self):
        cands, _c, _n = bl.prefix_bindiff(DETAILS, MATCHES, SIZES, OUR_NAMES)
        rows, _census = bl.proposals(cands)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                bl.write_proposals(os.path.join(tmp, "x_bindiff_loose.csv"), rows, ["h"])

    def test_a_new_pair_another_file_already_proposes_is_a_confirmation_not_a_row(self):
        cands, _census = bl.bindiff_new(MATCHES, self.anchors(), SIZES, DEMO_NAMES, OUR_NAMES)
        rows, census = bl.proposals(cands, others={"game/x_strings.csv": [(O_NEW, "sceFsInit")]})
        self.assertEqual(rows, [])
        self.assertEqual(census["already proposed by another file with the same name (a confirmation)"], 1)
        rows, census = bl.proposals(cands, others={"game/x_strings.csv": [(O_NEW, "sceFsOther")]})
        self.assertEqual(rows, [])
        self.assertEqual(census["refused: another file proposes a different name for this address"], 1)


class HoldsTest(unittest.TestCase):
    HOLDS = {O_NEW: {"Address": "0x%08x" % O_NEW, "Proposed": "sceFsInit", "Reason": "r", "Source": "s"}}

    def test_a_held_address_and_name_is_refused_and_counted(self):
        cands, _census = bl.bindiff_new(MATCHES, [], SIZES, DEMO_NAMES, OUR_NAMES)
        rows, census = bl.proposals(cands, holds=self.HOLDS)
        self.assertNotIn("0x%08x" % O_NEW, [r["Address"] for r in rows])
        self.assertEqual(census["refused: held (address, name) (recomp/socom2_name_holds.csv)"], 1)

    def test_a_held_anchor_is_no_anchor(self):
        anchors = [(D_NEW, O_NEW, "exact"), (D_EX, O_EX, "exact")]
        kept = bl.drop_held(anchors, self.HOLDS)
        self.assertEqual(kept, [(D_EX, O_EX, "exact")])
        cands, _census = bl.bindiff_new(MATCHES, kept, SIZES, DEMO_NAMES, OUR_NAMES)
        self.assertIn(O_NEW, [c.our_addr for c in cands])


class HurdlesTest(unittest.TestCase):
    def test_same_address_same_name_elsewhere_is_kept_as_an_agreement(self):
        cands, _c, _n = bl.prefix_bindiff(DETAILS, MATCHES, SIZES, OUR_NAMES)
        rows, census = bl.proposals(cands, others={"p_offsets.csv": [(O_PFX, "Flash__4CHUDFv")]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(census["agrees with another file (kept)"], 1)

    def test_an_identifier_spent_at_another_address_is_refused(self):
        cands, _c, _n = bl.prefix_bindiff(DETAILS, MATCHES, SIZES, OUR_NAMES)
        rows, census = bl.proposals(cands, others={"f.csv": [(0x2999, "Flash__4CHUDFv")]})
        self.assertEqual(rows, [])
        self.assertEqual(census["refused: identifier proposed at another address by another file"], 1)
        rows, census = bl.proposals(cands, taken={"Flash__4CHUDFv": {0x2998}})
        self.assertEqual(rows, [])
        self.assertEqual(census["refused: identifier carried by a Task 7 pair or a named row elsewhere"], 1)

    def test_a_demo_name_on_two_demo_addresses_is_refused(self):
        cands, _census = bl.bindiff_new(MATCHES, [], SIZES, DEMO_NAMES, OUR_NAMES)
        rows, census = bl.proposals(cands, demo_counts={"sceFsInit": 2})
        self.assertNotIn("sceFsInit", [r["Mangled"] for r in rows])
        self.assertEqual(census["refused: demo name on two demo addresses"], 1)


class ConfirmationsTest(unittest.TestCase):
    def test_agreements_and_contradictions_per_file(self):
        files = {"game/demo_symbol_renames_callgraph_loose.csv": [
                     {"Address": "0x%08x" % O_NEW, "Mangled": "sceFsInit", "DemoAddr": "0x%08x" % D_NEW},
                     {"Address": "0x%08x" % O_EX, "Mangled": "memmove"},                 # BinDiff says memcpy
                     {"Address": "0x00002777", "Mangled": "nothing"}],                    # no rule pair
                 "game/demo_symbol_renames.csv": [{"Address": "0x%08x" % O_EX, "Mangled": "memcpy"}]}
        conf = bl.confirmations(MATCHES, files, SIZES, DEMO_NAMES)
        self.assertEqual([(r["Address"], r["Mangled"], r["File"]) for r in conf.agree],
                         [("0x%08x" % O_EX, "memcpy", "demo_symbol_renames.csv"),
                          ("0x%08x" % O_NEW, "sceFsInit", "demo_symbol_renames_callgraph_loose.csv")])
        self.assertEqual(conf.agree[1]["Matcher"], "edges flowgraph MD index")
        self.assertEqual(conf.agree[1]["Similarity"], "0.957")
        self.assertEqual([(r["Address"], r["Mangled"]) for r in conf.contradict], [("0x%08x" % O_EX, "memmove")])
        per = conf.per_file["demo_symbol_renames_callgraph_loose.csv"]
        self.assertEqual((per["same"], per["other"], per["no rule pair"]), (1, 1, 1))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "confirmations.csv")
            bl.write_confirmations(path, conf.agree)
            with open(path) as fh:
                got = list(csv.DictReader(fh))
        self.assertEqual(list(got[0].keys()), ["Address", "Mangled", "File", "Matcher", "Similarity"])
        self.assertEqual(len(got), 2)

    def test_a_held_row_is_never_an_agreement(self):
        files = {"game/demo_symbol_renames.csv": [{"Address": "0x%08x" % O_EX, "Mangled": "memcpy"}]}
        holds = {O_EX: {"Address": "0x%08x" % O_EX, "Proposed": "memcpy", "Reason": "r", "Source": "s"}}
        conf = bl.confirmations(MATCHES, files, SIZES, DEMO_NAMES, holds=holds)
        self.assertEqual(conf.agree, [])
        self.assertEqual(conf.per_file["demo_symbol_renames.csv"]["held (address, name)"], 1)

    def test_a_row_whose_demo_function_bindiff_places_elsewhere_is_contradicted(self):
        files = {"game/demo_symbol_renames_strings.csv": [
            {"Address": "0x00002777", "Mangled": "sceFsInit", "DemoAddr": "0x%08x" % D_NEW}]}
        conf = bl.confirmations(MATCHES, files, SIZES, DEMO_NAMES)
        self.assertEqual([r["Address"] for r in conf.contradict], ["0x00002777"])
        self.assertIn("0x%08x" % O_NEW, conf.contradict[0]["BinDiff"])


class HeaderTest(unittest.TestCase):
    def test_the_header_carries_the_rule_the_matchers_the_threshold_and_the_reproduction(self):
        for path in ("game/demo_symbol_renames_bindiff.csv", "game/demo_symbol_renames_bindiff_loose.csv"):
            text = "\n".join(bl.header_lines(path, ["census: confirmed 21"], "Anchors: 987"))
            self.assertIn(bl.BINDIFF_RULE, text)
            for name in bl.RULE_MATCHERS:
                self.assertIn(name, text)
            self.assertIn("0.95", text)
            self.assertIn("census: confirmed 21", text)
            self.assertIn("Anchors: 987", text)
            self.assertIn("docs/research/49-bindiff-crosscheck.md", text)
            self.assertIn("A-E", text)
        loose = bl.header_lines("game/demo_symbol_renames_bindiff_loose.csv", [], "")
        self.assertIn("Score 0.75", loose[0])
        self.assertIn("LOOSE", loose[0])

    def test_written_header_lines_are_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "demo_symbol_renames_bindiff.csv")
            bl.write_proposals(path, [], bl.header_lines(path, [], ""))
            with open(path) as fh:
                lines = fh.read().splitlines()
        body = [l for l in lines if not l.startswith("#")]
        self.assertEqual(body, [",".join(bl.COLUMNS)])


if __name__ == "__main__":
    unittest.main()
