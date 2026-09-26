"""tools_py/sitting.py: the owner's generated sitting page (Sprint 14 Task D3).

Fixtures: a three-row HUMAN_TASKS table (one row with a struck default: answered, never open), four rulings (two
dated before `since`, one undated, one after), a BACKLOG with one issue at Carried 2 and one at 0, and a PLAYTEST
with a build block and one without. Today is injected, so the days-waited arithmetic is fixed.
"""
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools_py import sitting

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULINGS_FIXTURE = os.path.join(REPO, "tools_py", "tests", "fixtures", "rulings")
TODAY = datetime.date(2026, 1, 11)

HUMAN_TASKS = """# Human tasks -- the owner's sitting

last sitting: 2026-01-05

The rule and the numbers.

| O | the decision or the hand | the default the loop is on | settles | first asked |
|---|---|---|---|---|
| O1 | **The legal position on shipping the exe** (Sprint 11 D2) -- to strangers. It blocks downloads. | no public download; builds reach testers by hand (`a|b`) | audit F3 | 2026-01-01 |
| O2 | ~~**The story's five missing days**, carried twice.~~ **Answered by default (keep), 2026-01-03.** | ~~keep; S13 S4 writes them~~ | carry C128 | 2026-01-02 |
| O3 | **The crouch default**: the launcher writes `l3`. | the launcher's `l3` | audit A10 | 2026-01-04 |

**How to answer.** One line per decision.
"""

RULINGS = [
    {"number": "R4", "date": "2026-01-10", "line": "The fourth ruling says a thing.", "status": "active",
     "home": "docs/plan.md **R4**"},
    {"number": "R3", "date": None, "line": "The undated one.", "status": "active", "home": "docs/plan.md **R3**"},
    {"number": "R2", "date": "2026-01-02", "line": "Before the sitting.", "status": "active",
     "home": "docs/plan.md **R2**"},
    {"number": "R1", "date": "2026-01-01", "line": "Before the sitting too.", "status": "active",
     "home": "docs/plan.md **R1**"},
]

BACKLOG = """# Backlog: the carry in one place

## 1. Open issues

2 open issues.

| Issue | Title | Area | Milestone | Carried | Closing bar (first sentence) |
|---|---|---|---|---|---|
| #25 | The Linux VM's suites are not green | linux | backlog | 2 | Each case fixed. |
| #41 | A menu-frame fixture is missing | harness | backlog | 0 | A fresh dump. |

## 2. Ruled out

| Item | Ruling | Bar |
|---|---|---|
| a thing | R1 | 2 |
"""

PLAYTEST_BUILT = """# The playtest

```
build:    2026-01-09 (evening), release at -O1   commit: abc1234
archive:  dist-release/portable/socom2-portable.zip  56,581,263 bytes
          sha256: c3058d286dd8bb299b2914faceae730128664f7bf3633aad93ffeaa4d7c05003
gate:     3/3 on the exe INSIDE that archive:
          socom2.exe 227,390,464 bytes, sha256 098cf126758b7dbdda175536d9dff34b5f43be594a56c343fd2d4caa2ff54997
```

> The block before it, for the record:
>
> ```
> build:    2025-12-01   commit: 0000000
> archive:  old.zip
>           sha256: ffff
> ```
"""

PLAYTEST_NOT_BUILT = """# The playtest

```
build:    NOT BUILT. No archive exists for the current tree.
```

> Superseded -- the block that stood here:
>
> ```
> build:    2025-12-01   commit: 0000000
> archive:  old.zip
>           sha256: c3058d286dd8bb299b2914faceae730128664f7bf3633aad93ffeaa4d7c05003
> ```
"""

PLAYTEST_NO_BLOCK = """# The playtest

Nothing has been built yet; the steps follow.
"""


def page(playtest=PLAYTEST_BUILT, rulings_rows=RULINGS, since="2026-01-05"):
    return sitting.build(HUMAN_TASKS, rulings_rows, BACKLOG, playtest, since, today=TODAY)


def section(text, n):
    """The body of section n (`## n. ...`) up to the next section."""
    start = text.index("\n## %d. " % n)
    nxt = text.find("\n## %d. " % (n + 1), start + 1)
    return text[start:nxt if nxt != -1 else len(text)]


class ORowsTest(unittest.TestCase):
    def test_open_rows_with_their_hand_default_and_days_waited(self):
        rows = sitting.o_rows(HUMAN_TASKS, today=TODAY)
        self.assertEqual([r["number"] for r in rows], ["O1", "O2", "O3"])
        o1, o2, o3 = rows
        self.assertEqual(o1["hand"], "The legal position on shipping the exe")
        self.assertEqual(o1["default"], "no public download; builds reach testers by hand (`a|b`)")
        self.assertEqual(o1["first_asked"], "2026-01-01")
        self.assertEqual(o1["days"], 10)
        self.assertEqual(o3["days"], 7)
        self.assertFalse(o1["struck"])
        self.assertTrue(o2["struck"])
        self.assertIsNone(o2["days"])

    def test_the_struck_row_is_listed_as_answered_not_open(self):
        s1 = section(page(), 1)
        self.assertIn("2 open", s1)
        self.assertIn("1 answered or struck", s1)
        open_part, _, answered_part = s1.partition("Answered or struck")
        self.assertIn("| O1 |", open_part)
        self.assertIn("| O3 |", open_part)
        self.assertNotIn("O2", open_part)
        self.assertIn("O2", answered_part)
        self.assertIn("Answered by default (keep), 2026-01-03.", answered_part)

    def test_the_days_waited_column(self):
        s1 = section(page(), 1)
        o1 = [l for l in s1.split("\n") if l.startswith("| O1 |")][0]
        self.assertTrue(o1.rstrip().endswith("| 2026-01-01 | 10 |"), o1)

    def test_a_pipe_in_a_row_is_escaped(self):
        self.assertIn("`a\\|b`", section(page(), 1))

    def test_the_last_sitting_stamp(self):
        self.assertEqual(sitting.last_sitting(HUMAN_TASKS), "2026-01-05")
        self.assertIsNone(sitting.last_sitting("# no stamp\n"))


class RulingsSectionTest(unittest.TestCase):
    def test_only_the_active_dated_rulings_on_or_after_since(self):
        s2 = section(page(), 2)
        self.assertIn("1 active ruling dated on or after 2026-01-05", s2)
        self.assertIn("**R4**", s2)
        for gone in ("**R1**", "**R2**", "**R3**"):
            self.assertNotIn(gone, s2)

    def test_the_undated_rows_are_counted_as_excluded(self):
        self.assertIn("1 active ruling has no date", section(page(), 2))

    def test_each_line_ends_overturn_by_number(self):
        lines = [l for l in section(page(), 2).split("\n") if l.startswith("- **R")]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].endswith("overturn by number"), lines[0])

    def test_since_is_inclusive_and_a_non_active_ruling_is_left_out(self):
        rows = RULINGS + [{"number": "R5", "date": "2026-01-05", "line": "Gone.", "status": "superseded",
                           "home": "x **R5**"}]
        s2 = section(page(rulings_rows=rows, since="2026-01-02"), 2)
        self.assertIn("**R2**", s2)
        self.assertIn("**R4**", s2)
        self.assertNotIn("**R5**", s2)
        self.assertNotIn("**R1**", s2)


class CarriedTest(unittest.TestCase):
    def test_the_issues_carried_twice(self):
        s3 = section(page(), 3)
        self.assertIn("1 issue carried twice", s3)
        self.assertIn("#25", s3)
        self.assertNotIn("#41", s3)

    def test_rows_of_the_second_table_are_not_issues(self):
        self.assertEqual([r["issue"] for r in sitting.carried_twice(BACKLOG)], ["#25"])


class BuildTest(unittest.TestCase):
    def test_the_archive_and_its_hashes(self):
        s4 = section(page(), 4)
        self.assertIn("dist-release/portable/socom2-portable.zip", s4)
        self.assertIn("c3058d286dd8bb299b2914faceae730128664f7bf3633aad93ffeaa4d7c05003", s4)
        self.assertIn("098cf126758b7dbdda175536d9dff34b5f43be594a56c343fd2d4caa2ff54997", s4)
        self.assertNotIn("old.zip", s4)   # the quoted record of an older block is not the build
        self.assertNotIn("NOT BUILT", s4)

    def test_not_built_in_bold(self):
        s4 = section(page(playtest=PLAYTEST_NOT_BUILT), 4)
        self.assertIn("**NOT BUILT**", s4)
        self.assertNotIn("old.zip", s4)
        self.assertNotIn("c3058d28", s4)

    def test_no_block_is_not_built(self):
        self.assertIn("**NOT BUILT**", section(page(playtest=PLAYTEST_NO_BLOCK), 4))


class PageTest(unittest.TestCase):
    def test_header_says_generated_the_command_and_the_counts(self):
        head = page().split("\n## 1. ")[0]
        self.assertIn("Generated", head)
        self.assertIn("python -m tools_py.sitting", head)
        self.assertIn("2 open O rows (1 answered or struck)", head)
        self.assertIn("1 active ruling since 2026-01-05", head)
        self.assertIn("1 issue carried twice", head)
        self.assertIn("the build: built", head)
        self.assertIn("as of 2026-01-11", head)
        self.assertIn("the build: **NOT BUILT**", page(playtest=PLAYTEST_NOT_BUILT).split("\n## 1. ")[0])

    def test_under_8000_bytes(self):
        self.assertLess(len(page().encode("utf-8")), 8000)

    def test_stable(self):
        self.assertEqual(page(), page())


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sitting_")
        self.root = os.path.join(self.tmp, "tree")
        shutil.copytree(RULINGS_FIXTURE, self.root)
        for name, text in (("HUMAN_TASKS.md", HUMAN_TASKS), ("BACKLOG.md", BACKLOG), ("PLAYTEST.md", PLAYTEST_BUILT)):
            self.write(name, text)
        self.page = os.path.join(self.root, "docs", "SITTING.md")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, text):
        with open(os.path.join(self.root, "docs", name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "tools_py.sitting", "--root", self.root] + list(args),
                              cwd=REPO, capture_output=True, text=True, encoding="utf-8")

    def test_write_then_check_is_clean(self):
        self.assertEqual(self.cli().returncode, 0)
        self.assertTrue(os.path.isfile(self.page))
        res = self.cli("--check")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_since_defaults_to_the_stamp_and_can_be_overridden(self):
        self.assertEqual(self.cli().returncode, 0)
        with open(self.page, encoding="utf-8") as fh:
            self.assertIn("since 2026-01-05", fh.read())
        self.assertEqual(self.cli("--since", "2026-01-01").returncode, 0)
        with open(self.page, encoding="utf-8") as fh:
            self.assertIn("since 2026-01-01", fh.read())

    def test_check_on_a_stale_file_exits_1_with_a_diff(self):
        self.assertEqual(self.cli().returncode, 0)
        self.write("HUMAN_TASKS.md", HUMAN_TASKS.replace("The crouch default", "The crouch choice"))
        res = self.cli("--check")
        self.assertEqual(res.returncode, 1)
        self.assertIn("The crouch choice", res.stdout)
        self.assertIn("stale", res.stdout)

    def test_check_on_a_missing_file_exits_1(self):
        self.assertEqual(self.cli("--check").returncode, 1)


class TreeTest(unittest.TestCase):
    """Class G: the page on this tree is held to its sources every suite run (docs/DOC_MAINTENANCE.md section 1)."""

    def test_the_page_on_this_tree_is_current(self):
        res = subprocess.run([sys.executable, "-m", "tools_py.sitting", "--check"], cwd=REPO,
                             capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, 0, "docs/SITTING.md is stale: run python -m tools_py.sitting and commit "
                                            "it\n" + res.stdout)


if __name__ == "__main__":
    unittest.main()
