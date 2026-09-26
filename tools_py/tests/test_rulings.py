"""tools_py/rulings.py: the generated rulings page (Sprint 14 Task D1).

The fixture tree under tools_py/tests/fixtures/rulings/ plants one ruling of each status the page reports --
active, superseded (a definition that says SUPERSEDED BY, a ledger row that says superseded by, an S12 name
"amended by" another), retracted (a struck definition and one that says RETRACTED), withdrawn (a definition and
a ledger-only row; an S13 name another ruling "retires"), vacant (a vacancy note and a ledger row that says deliberately vacant) -- plus the
negative controls that must not become rows: a citation, a quoted first telling, a mid-line S12 label.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools_py import docmaint, rulings

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURE = os.path.join(REPO, "tools_py", "tests", "fixtures", "rulings")
PLAN1 = "docs/superpowers/plans/2026-01-01-sprint-1.md"
PLAN2 = "docs/superpowers/plans/2026-01-02-sprint-2.md"
LEDGER = "docs/CURRENT_SPRINT.md"

EXPECTED = [
    # (number, date, status, home) in page order: global newest first, then S13, then S12.
    ("R20", None, "superseded", LEDGER + ":10"),
    ("R19", None, "vacant", LEDGER + ":9"),
    ("R17", None, "vacant", PLAN1 + ":17"),
    ("R16", None, "withdrawn", LEDGER + ":8"),
    ("R15", "2026-01-05", "retracted", PLAN1 + ":16"),
    ("R14", "2026-01-04", "withdrawn", PLAN1 + ":15"),
    ("R13", None, "active", PLAN1 + ":12"),
    ("R12", None, "retracted", PLAN1 + ":11"),
    ("R11", "2026-01-02", "superseded", PLAN1 + ":10"),
    ("R10", "2026-01-01", "active", PLAN1 + ":9"),
    ("S13-R2", "2026-01-09", "active", PLAN2 + ":10"),
    ("S13-R1", "2026-01-08", "superseded", PLAN2 + ":9"),
    ("S12-R2", "2026-01-07", "active", PLAN2 + ":8"),
    ("S12-R1", "2026-01-06", "superseded", PLAN2 + ":7"),
]


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.rows = rulings.rows(root=FIXTURE)
        self.by = {r["number"]: r for r in self.rows}

    def test_exactly_the_planted_rows_with_their_statuses(self):
        got = [(r["number"], r["date"], r["status"], r["home"]) for r in self.rows]
        self.assertEqual(got, EXPECTED)

    def test_keys(self):
        for r in self.rows:
            self.assertEqual(set(r), {"number", "date", "line", "status", "home"})

    def test_the_line_is_the_first_sentence_without_bold(self):
        self.assertEqual(self.by["R10"]["line"], "the first decision stands.")
        self.assertEqual(self.by["R11"]["line"], "the second decision, SUPERSEDED BY R13 on the fourth.")
        self.assertEqual(self.by["R12"]["line"], "the third decision, struck where it stood.")
        self.assertEqual(self.by["R14"]["line"], "the fifth decision.")
        self.assertEqual(self.by["R17"]["line"], "named in a brief and never issued.")
        self.assertEqual(self.by["S12-R2"]["line"], "the naming defaults narrowed.")
        self.assertEqual(self.by["S13-R1"]["line"], "the order is V, R, H.")

    def test_a_long_first_sentence_is_cut_at_160(self):
        line = self.by["R13"]["line"]
        self.assertLessEqual(len(line), 160)
        self.assertTrue(line.startswith("the fourth decision; a long first sentence"), line)
        self.assertTrue(line.endswith("…"), line)
        self.assertNotIn("**", line)
        self.assertIn("bold words stripped", line)
        self.assertNotIn("second sentence", line)
        self.assertEqual(line.count("`") % 2, 0, "a cut inside a code span leaves it open: " + line)

    def test_no_line_carries_a_marker_or_an_open_code_span(self):
        for r in self.rows:
            self.assertNotIn("<!--", r["line"], r["number"])
            self.assertEqual(r["line"].count("`") % 2, 0, r["number"])

    def test_a_ledger_only_row_takes_its_text_cell(self):
        self.assertIn("a ruling that has only its row", self.by["R16"]["line"])

    def test_root_is_restored(self):
        before = docmaint.ROOT
        rulings.rows(root=FIXTURE)
        self.assertEqual(docmaint.ROOT, before)


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.rows = rulings.rows(root=FIXTURE)
        self.page = rulings.render(self.rows)

    def test_stable(self):
        self.assertEqual(self.page, rulings.render(rulings.rows(root=FIXTURE)))

    def test_header_says_generated_and_counts(self):
        head = "\n".join(self.page.split("\n")[:8])
        self.assertIn("Generated", head)
        self.assertIn("do not edit", head)
        self.assertIn("python -m tools_py.rulings", head)
        self.assertIn("14 rulings", self.page)
        for count in ("4 active", "4 superseded", "2 retracted", "2 withdrawn", "2 vacant"):
            self.assertIn(count, self.page)

    def test_groups_in_order_and_pipes_escaped(self):
        g, s13, s12 = (self.page.index(h) for h in ("## Global", "## S13", "## S12"))
        self.assertLess(g, s13)
        self.assertLess(s13, s12)
        self.assertLess(self.page.index("| R20 |"), self.page.index("| R10 |"))
        self.assertIn("pipe \\| inside", self.page)
        self.assertIn("| R10 | 2026-01-01 | active | the first decision stands. | `%s:9` |" % PLAN1, self.page)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rulings_")
        self.root = os.path.join(self.tmp, "tree")
        shutil.copytree(FIXTURE, self.root)
        self.page = os.path.join(self.root, "docs", "RULINGS.md")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "tools_py.rulings", "--root", self.root] + list(args),
                              cwd=REPO, capture_output=True, text=True, encoding="utf-8")

    def test_write_then_check_is_clean(self):
        self.assertEqual(self.cli().returncode, 0)
        self.assertTrue(os.path.isfile(self.page))
        res = self.cli("--check")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_check_on_a_stale_file_exits_1_with_a_diff(self):
        self.assertEqual(self.cli().returncode, 0)
        with open(self.page, "a", encoding="utf-8") as fh:
            fh.write("| R99 | -- | active | a hand edit | `nowhere:1` |\n")
        res = self.cli("--check")
        self.assertEqual(res.returncode, 1)
        self.assertIn("R99", res.stdout)

    def test_check_on_a_missing_file_exits_1(self):
        res = self.cli("--check")
        self.assertEqual(res.returncode, 1)


class TreeTest(unittest.TestCase):
    """Class G: the page on this tree is held to its source every suite run (docs/DOC_MAINTENANCE.md section 1)."""

    def test_the_page_on_this_tree_is_current(self):
        with open(os.path.join(REPO, rulings.PAGE), "r", encoding="utf-8") as fh:
            on_disk = fh.read()
        self.assertTrue(on_disk == rulings.render(rulings.rows()),
                        "docs/RULINGS.md is stale: run python -m tools_py.rulings and commit it")


if __name__ == "__main__":
    unittest.main()
