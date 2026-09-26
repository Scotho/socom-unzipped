"""tools_py/sitting.py: the owner's generated sitting page (Sprint 14 Task D3).

Fixtures: a three-row HUMAN_TASKS table (one row with a struck default: answered, never open), four rulings (two
dated before `since`, one undated, one after), a BACKLOG with one issue at Carried 2 and one at 0, and a PLAYTEST
with a build block and one without. Today is injected, so the days-waited arithmetic is fixed.
"""
import contextlib
import datetime
import io
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

# Before the sitting: R10 and R12 (dated). After it: R14 (dated); R13 undated but numbered above R12, the highest
# active ruling dated before it (placed by number); S13-R1 undated, its home's filename dated after it (placed by
# home). Unplaceable: R11 (undated, below R12) and S13-R2 (undated, an undated home).
RULINGS = [
    {"number": "R14", "date": "2026-01-10", "line": "The fourth ruling says a thing.", "status": "active",
     "home": "docs/plan.md **R14**"},
    {"number": "R13", "date": None, "line": "Undated, above the counter.", "status": "active",
     "home": "docs/plan.md **R13**"},
    {"number": "R12", "date": "2026-01-02", "line": "Before the sitting.", "status": "active",
     "home": "docs/plan.md **R12**"},
    {"number": "R11", "date": None, "line": "The undated one.", "status": "active", "home": "docs/plan.md **R11**"},
    {"number": "R10", "date": "2026-01-01", "line": "Before the sitting too.", "status": "active",
     "home": "docs/plan.md **R10**"},
    {"number": "S13-R2", "date": None, "line": "Local, undated, no dated home.", "status": "active",
     "home": "docs/plan.md **S13-R2**"},
    {"number": "S13-R1", "date": None, "line": "Local, undated, a dated home.", "status": "active",
     "home": "docs/superpowers/plans/2026-01-08-sprint-13.md **S13-R1**"},
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


# Sprint 14 D4 (R271): the stamp has grown to the history of sittings. O1 was asked before both (the mark); O2
# before both but struck (answered: no mark); O3 between them (one sitting: no mark); O4 on the second sitting's
# own date (a sitting on the day a row is asked has not seen it -- section 2's rule for a ruling: no sitting); O5
# on the first sitting's date (only the second counts: no mark; a third sitting marks it).
HUMAN_TASKS_TWO = HUMAN_TASKS.replace(
    "last sitting: 2026-01-05", "sittings: 2026-01-03, 2026-01-05 (read by tools_py.sitting)").replace(
    "| O3 | **The crouch default**: the launcher writes `l3`. | the launcher's `l3` | audit A10 | 2026-01-04 |",
    "| O3 | **The crouch default**: the launcher writes `l3`. | the launcher's `l3` | audit A10 | 2026-01-04 |\n"
    "| O4 | **The pad map**, asked at the sitting. | the shipped map | audit A11 | 2026-01-05 |\n"
    "| O5 | **The mic gate**, asked at the first sitting. | the gate off | audit A12 | 2026-01-03 |")
BREAKER = "closes by default at the next close (R271)"


class CircuitBreakerTest(unittest.TestCase):
    def test_the_stamp_history_in_both_forms(self):
        self.assertEqual(sitting.stamps(HUMAN_TASKS), ["2026-01-05"])
        self.assertEqual(sitting.stamps(HUMAN_TASKS_TWO), ["2026-01-03", "2026-01-05"])
        self.assertEqual(sitting.last_sitting(HUMAN_TASKS_TWO), "2026-01-05")
        stamp = [l for l in HUMAN_TASKS_TWO.split("\n") if l.startswith("sittings:")][0]
        self.assertLess(len(stamp.encode("utf-8")), 80)

    def test_the_rows_that_stood_through_two_sittings(self):
        rows = {r["number"]: r for r in sitting.o_rows(HUMAN_TASKS_TWO, today=TODAY)}
        self.assertEqual({n: r["sittings"] for n, r in rows.items()},
                         {"O1": 2, "O2": 2, "O3": 1, "O4": 0, "O5": 1})
        self.assertEqual({n: r["closes"] for n, r in rows.items()},
                         {"O1": True, "O2": False, "O3": False, "O4": False, "O5": False})

    def test_a_row_asked_on_the_first_sittings_date_needs_two_later_sittings(self):
        three = HUMAN_TASKS_TWO.replace("sittings: 2026-01-03, 2026-01-05", "sittings: 2026-01-03, 2026-01-05, 2026-01-07")
        rows = {r["number"]: r for r in sitting.o_rows(three, today=TODAY)}
        self.assertEqual((rows["O5"]["sittings"], rows["O5"]["closes"]), (2, True))
        self.assertEqual((rows["O4"]["sittings"], rows["O4"]["closes"]), (1, False))
        s1 = section(sitting.build(three, RULINGS, BACKLOG, PLAYTEST_BUILT, "2026-01-07", today=TODAY), 1)
        self.assertIn("3 rows close by default at the next close (R271)", s1)   # O1, O3, O5

    def test_the_mark_on_the_page(self):
        s1 = section(sitting.build(HUMAN_TASKS_TWO, RULINGS, BACKLOG, PLAYTEST_BUILT, "2026-01-05", today=TODAY), 1)
        by = {l.split("|")[1].strip(): l for l in s1.split("\n") if l.startswith("| O")}
        self.assertIn(BREAKER, by["O1"])
        for n in ("O3", "O4", "O5"):
            self.assertNotIn(BREAKER, by[n])
        self.assertNotIn("O2", by)   # struck: answered, listed apart
        self.assertEqual(s1.count(BREAKER), 1 + 1, s1)   # the row and the section's count sentence
        self.assertIn("1 row closes by default at the next close (R271).", s1)

    def test_one_sitting_marks_nothing(self):
        self.assertNotIn(BREAKER, section(page(), 1))
        self.assertFalse(any(r["closes"] for r in sitting.o_rows(HUMAN_TASKS, today=TODAY)))


class RulingsSectionTest(unittest.TestCase):
    def lines(self, text):
        return [l for l in section(text, 2).split("\n") if l.startswith("- **")]

    def test_the_dated_and_the_placed_in_the_counters_order(self):
        s2 = section(page(), 2)
        self.assertIn("3 active rulings on or after 2026-01-05", s2)
        self.assertEqual([l.split("**")[1] for l in self.lines(page())], ["R13", "R14", "S13-R1"])
        for gone in ("**R10**", "**R11**", "**R12**", "**S13-R2**"):
            self.assertNotIn(gone, s2)

    def test_each_listed_ruling_says_how_it_was_placed(self):
        got = {l.split("**")[1]: l.split("(", 1)[1].split(")", 1)[0] for l in self.lines(page())}
        self.assertEqual(got, {"R13": "placed by number", "R14": "2026-01-10", "S13-R1": "placed by home"})

    def test_the_counts(self):
        listed, n_dated, n_placed, n_unplaceable = sitting.active_since(RULINGS, "2026-01-05")
        self.assertEqual((len(listed), n_dated, n_placed, n_unplaceable), (3, 1, 2, 2))
        self.assertIn("Left out: 2 active rulings with no date", section(page(), 2))

    def test_each_line_ends_overturn_by_number(self):
        lines = self.lines(page())
        self.assertEqual(len(lines), 3)
        for line in lines:
            self.assertTrue(line.endswith("overturn by number"), line)

    def test_since_is_inclusive_and_a_non_active_ruling_is_left_out(self):
        rows = RULINGS + [{"number": "R15", "date": "2026-01-05", "line": "Gone.", "status": "superseded",
                           "home": "x **R15**"}]
        s2 = section(page(rulings_rows=rows, since="2026-01-02"), 2)
        self.assertIn("**R12**", s2)
        self.assertIn("**R14**", s2)
        self.assertNotIn("**R15**", s2)
        self.assertNotIn("**R10**", s2)
        self.assertIn("**R11** (placed by number)", s2)   # R10 is now the highest dated before the sitting


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
        self.assertIn("3 active rulings since 2026-01-05 (1 dated, 2 placed by number or home, "
                      "2 undated and unplaceable, not listed)", head)
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

    def test_a_page_written_with_since_passes_a_check_with_that_since(self):
        self.assertEqual(self.cli("--since", "2026-01-01").returncode, 0)
        res = self.cli("--check", "--since", "2026-01-01")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_a_bare_check_holds_the_page_to_the_stamp(self):
        # D3's review (a): a page whose `since` is not HUMAN_TASKS' latest stamp is stale to a bare --check -- a
        # page written with --since, or a new sitting stamped with no regenerate.
        self.assertEqual(self.cli("--since", "2026-01-01").returncode, 0)
        res = self.cli("--check")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("2026-01-05", res.stdout)
        self.assertIn("stale", res.stdout)
        self.assertEqual(self.cli().returncode, 0)
        self.write("HUMAN_TASKS.md", HUMAN_TASKS.replace(
            "last sitting: 2026-01-05", "sittings: 2026-01-05, 2026-01-10 (read by tools_py.sitting)"))
        res = self.cli("--check")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("2026-01-10", res.stdout)
        self.assertIn("stale", res.stdout)
        self.assertEqual(self.cli().returncode, 0)
        res = self.cli("--check")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


class AtCommitTest(unittest.TestCase):
    """The suite's contract (tools_py.changelog's): the page is a render of its sources at the commit that last
    wrote it, so a later source change does not redden the suite; the bare --check still reports it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sitting_git_")
        self.root = os.path.join(self.tmp, "tree")
        shutil.copytree(RULINGS_FIXTURE, self.root)
        for name, text in (("HUMAN_TASKS.md", HUMAN_TASKS), ("BACKLOG.md", BACKLOG), ("PLAYTEST.md", PLAYTEST_BUILT)):
            self.write(name, text)
        self.git("init", "-q", "-b", "main")
        self.git("add", "--", "docs")
        self.git("commit", "-q", "-m", "sources", "--", "docs")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, text):
        with open(os.path.join(self.root, "docs", name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def git(self, *args):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.invalid")
        return subprocess.run(["git", "-c", "core.hooksPath=.no-hooks", "-c", "commit.gpgsign=false",
                               "-c", "core.autocrlf=false"] + list(args),
                              cwd=self.root, env=env, capture_output=True, text=True, check=True).stdout

    def main(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return sitting.main(["--root", self.root] + list(args))

    def on_disk(self):
        with open(os.path.join(self.root, sitting.PAGE), encoding="utf-8") as fh:
            return fh.read()

    def render_as_the_suite_does(self):
        today, since = sitting.page_stamps(self.on_disk())
        return sitting.render_at(self.root, sitting.page_rev(self.root), since=since, today=today)

    def test_a_later_source_commit_leaves_the_page_a_render_of_its_commit(self):
        self.assertEqual(self.main(), 0)
        self.assertIsNone(sitting.page_rev(self.root))            # uncommitted: the working tree
        self.git("add", "--", sitting.PAGE)
        self.git("commit", "-q", "-m", "page", "--", sitting.PAGE)
        self.assertEqual(sitting.page_rev(self.root), self.git("rev-parse", "HEAD").strip())
        self.write("HUMAN_TASKS.md", HUMAN_TASKS.replace("The crouch default", "The crouch choice"))
        self.git("commit", "-q", "-m", "a later O row", "--", "docs/HUMAN_TASKS.md")
        self.assertEqual(self.on_disk(), self.render_as_the_suite_does())
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(sitting.main(["--root", self.root, "--check"]), 1)   # the close's question
        self.assertIn("The crouch choice", out.getvalue())

    def test_a_hand_edit_of_the_committed_page_is_caught(self):
        self.assertEqual(self.main(), 0)
        self.git("add", "--", sitting.PAGE)
        self.git("commit", "-q", "-m", "page", "--", sitting.PAGE)
        with open(os.path.join(self.root, sitting.PAGE), "a", encoding="utf-8", newline="\n") as fh:
            fh.write("- a hand edit\n")
        self.git("commit", "-q", "-m", "hand edit", "--", sitting.PAGE)
        self.assertNotEqual(self.on_disk(), self.render_as_the_suite_does())


class TreeTest(unittest.TestCase):
    """Class G: the page on this tree is held to its sources AT THE COMMIT THAT LAST WROTE IT (or the working tree
    while it has uncommitted changes), every suite run. Whether it is current with HEAD's sources is
    `python -m tools_py.sitting --check`'s question, asked at the close (docs/DOC_MAINTENANCE.md section 3)."""

    def test_the_page_on_this_tree_is_a_render_of_its_commit(self):
        reason = sitting.shallow_reason(REPO)
        if reason:
            self.skipTest(reason)
        with open(os.path.join(REPO, sitting.PAGE), "r", encoding="utf-8") as fh:
            on_disk = fh.read()
        today, since = sitting.page_stamps(on_disk)
        rev = sitting.page_rev(REPO)
        self.assertTrue(on_disk == sitting.render_at(REPO, rev, since=since, today=today),
                        "docs/SITTING.md is not a render of its sources at %s: run python -m tools_py.sitting and "
                        "commit it" % (rev or "the working tree"))


if __name__ == "__main__":
    unittest.main()
