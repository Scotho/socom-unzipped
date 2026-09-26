"""tools_py/flow.py: the generated flow page (Sprint 14 Task M1; the review's F8 and note 03's methods).

A throwaway repository is built per class, with fixed identities and UTC dates so every render is byte-identical:

    main:    c1 "feat: the root"                 2026-01-02  (session A)   root.txt +1
    feat/x:  c2 "fix(x): the thing"              2026-01-03                x.txt +1
             c3 "fix(x): review fix round 1"     2026-01-04  (session B)   x.txt +1 -1
    main:    c4 "docs: the note, again"          2026-01-05  (session A)   docs/a.md +1
    merge --no-ff feat/x                          2026-01-06

Expected: one merge, on 2026-01-06; on its branch one commit matching note 03's `review round|fix round` and two
matching the brief's broader `review round|fix round|fix\\(|review`; one " again" subject; two sessions with two
commits and one; the docs share of the churn 1 line of 5. A queue log of three TICKET lines: the median is the middle.
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools_py import flow

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSION_A = "claude://claude.ai/epitaxy/local_aaaa"
SESSION_B = "claude://claude.ai/epitaxy/local_bbbb"


class _Repo(object):

    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="flow_")
        self.git("init", "-q", "-b", "main")

    def git(self, *args, day=1):
        stamp = "2026-01-%02dT12:00:00+00:00" % day
        env = dict(os.environ, GIT_AUTHOR_NAME="Test Person", GIT_AUTHOR_EMAIL="test@example.com",
                   GIT_COMMITTER_NAME="Test Person", GIT_COMMITTER_EMAIL="test@example.com",
                   GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        out = subprocess.run(["git", "-c", "core.hooksPath=.no-hooks", "-c", "commit.gpgsign=false"] + list(args),
                             cwd=self.path, env=env, capture_output=True, text=True, check=True)
        return out.stdout.strip()

    def commit(self, name, lines, subject, day, session=None):
        full = os.path.join(self.path, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(l + "\n" for l in lines))
        self.git("add", "--", name, day=day)
        msg = subject if not session else "%s\n\nbody\n\nClaude-Session: %s" % (subject, session)
        self.git("commit", "-q", "-m", msg, "--", name, day=day)

    def remove(self):
        shutil.rmtree(self.path, ignore_errors=True)


def _build():
    r = _Repo()
    r.commit("root.txt", ["root"], "feat: the root", 2, SESSION_A)
    r.git("checkout", "-q", "-b", "feat/x", day=2)
    r.commit("x.txt", ["one"], "fix(x): the thing", 3)
    r.commit("x.txt", ["two"], "fix(x): review fix round 1", 4, SESSION_B)
    r.git("checkout", "-q", "main", day=4)
    r.commit("docs/a.md", ["note"], "docs: the note, again", 5, SESSION_A)
    r.git("merge", "-q", "--no-ff", "-m", "merge feat/x: the thing", "feat/x", day=6)
    return r


QUEUE = ("2026-01-02T00:00:00Z TICKET t1 waited 5\n"
         "2026-01-03T00:00:00Z TICKET t2 waited 40\n"
         "a line that is not a ticket\n"
         "2026-01-04T08:00:00Z TICKET t3 waited 12\n")

BACKLOG_WITH_DATES = """# Backlog

## 1. Open issues

| Issue | Title | Opened | Carried |
|---|---|---|---|
| #1 | one | 2025-12-27 | 0 |
| #2 | two | 2026-01-01 | 0 |
| #3 | three | 2026-01-05 | 1 |

## 2. Ruled not an issue

| Item | Ruling | Opened |
|---|---|---|
| x | no issue | 2020-01-01 |
"""

BACKLOG_WITHOUT_DATES = """# Backlog

## 1. Open issues

| Issue | Title | Area | Milestone | Carried | Closing bar (first sentence) |
|---|---|---|---|---|---|
| #25 | a title | linux | backlog | 2 | A bar. |
"""


class _WithRepo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repo = _build()
        cls.tmp = tempfile.mkdtemp(prefix="flow_files_")
        cls.queue = os.path.join(cls.tmp, "queue.log")
        with open(cls.queue, "w", encoding="utf-8") as fh:
            fh.write(QUEUE)
        cls.backlog = os.path.join(cls.tmp, "BACKLOG.md")
        with open(cls.backlog, "w", encoding="utf-8") as fh:
            fh.write(BACKLOG_WITH_DATES)

    @classmethod
    def tearDownClass(cls):
        cls.repo.remove()
        shutil.rmtree(cls.tmp, ignore_errors=True)


class MeasureTest(_WithRepo):

    def setUp(self):
        self.m = flow.measure(self.repo.path, "2026-01-01", self.queue, self.backlog)

    def test_one_merge_on_its_utc_day(self):
        self.assertEqual(self.m["merges_per_day"], {"2026-01-06": 1})

    def test_the_fix_round_histogram_counts_the_merged_branch(self):
        self.assertEqual(self.m["fix_rounds_per_merge"], {1: 1})
        self.assertEqual(self.m["fix_rounds_per_merge_broad"], {2: 1})

    def test_the_again_count(self):
        self.assertEqual(self.m["again_subjects"], 1)

    def test_the_docs_share_of_churn(self):
        self.assertEqual((self.m["churn_7d_docs"], self.m["churn_7d_all"]), (1, 5))
        self.assertAlmostEqual(self.m["docs_share_of_churn_7d"], 0.2)

    def test_the_median_ticket_wait_is_the_middle_value(self):
        self.assertEqual(self.m["median_ticket_wait_s"], 12)
        self.assertEqual(self.m["tickets"], 3)

    def test_sessions_and_commits_per_session(self):
        self.assertEqual(self.m["sessions"], 2)
        self.assertEqual(self.m["commits_per_session"], {SESSION_A: 2, SESSION_B: 1})

    def test_the_open_issue_age_is_the_median_of_the_open_table(self):
        # the rev's day is 2026-01-06: ages 10, 5, 1 -- the ruled-out table's date is not an open issue
        self.assertEqual(self.m["open_issue_age_days"], 5)

    def test_since_excludes_what_came_before(self):
        m = flow.measure(self.repo.path, "2026-01-05", self.queue, self.backlog)
        self.assertEqual(m["sessions"], 1)
        self.assertEqual(m["again_subjects"], 1)
        self.assertEqual(m["merges_per_day"], {"2026-01-06": 1})


class NotMeasuredTest(_WithRepo):

    def test_no_queue_log_and_no_dates_give_none(self):
        path = os.path.join(self.tmp, "nodates.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(BACKLOG_WITHOUT_DATES)
        m = flow.measure(self.repo.path, "2026-01-01", os.path.join(self.tmp, "absent.log"), path)
        self.assertIsNone(m["median_ticket_wait_s"])
        self.assertIsNone(m["open_issue_age_days"])
        page = flow.render(m)
        self.assertIn("**ticket wait**: not measured", page)
        self.assertIn("**open-issue age**: not measured", page)

    def test_a_ticket_stamped_after_the_rendered_commit_is_left_out(self):
        path = os.path.join(self.tmp, "late.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(QUEUE + "2027-01-01T00:00:00Z TICKET t4 waited 999\n2027-01-01T00:00:00Z TICKET t5 waited 999\n")
        m = flow.measure(self.repo.path, "2026-01-01", path, None)
        self.assertEqual((m["tickets"], m["median_ticket_wait_s"]), (3, 12))


class RenderTest(_WithRepo):

    def test_render_is_stable_and_every_number_names_its_command(self):
        m = flow.measure(self.repo.path, "2026-01-01", self.queue, self.backlog)
        page = flow.render(m)
        self.assertEqual(page, flow.render(flow.measure(self.repo.path, "2026-01-01", self.queue, self.backlog)))
        self.assertIn("Generated -- do not edit", page)
        self.assertIn("since 2026-01-01", page)
        for key in flow.NUMBERS:
            line = [l for l in page.splitlines() if l.startswith("- **%s**" % flow.LABELS[key])]
            self.assertEqual(len(line), 1, key)
            self.assertIn("command: `", line[0], key)
        self.assertEqual(flow.page_header(page), (m["rev"], "2026-01-01"))


class CliTest(_WithRepo):

    def setUp(self):
        self.out = os.path.join(tempfile.mkdtemp(prefix="flow_out_"), "FLOW.md")

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.out), ignore_errors=True)

    def run_main(self, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = flow.main(args)
        return rc, buf.getvalue()

    def test_write_then_check_then_stale(self):
        args = ["--repo", self.repo.path, "--out", self.out, "--queue-log", self.queue, "--backlog", self.backlog]
        self.assertEqual(self.run_main(args + ["--since", "2026-01-01"])[0], 0)
        self.assertEqual(self.run_main(args + ["--check"])[0], 0, "the page's own since and rev are reused")
        with open(self.out, "a", encoding="utf-8") as fh:
            fh.write("a hand edit\n")
        rc, said = self.run_main(args + ["--check"])
        self.assertEqual(rc, 1)
        self.assertIn("stale", said)

    def test_check_on_a_missing_file_exits_1(self):
        self.assertEqual(self.run_main(["--repo", self.repo.path, "--out", self.out, "--check"])[0], 1)

    def test_the_module_runs_as_a_command(self):
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write("stale\n")
        p = subprocess.run([sys.executable, "-m", "tools_py.flow", "--check", "--repo", self.repo.path,
                            "--out", self.out], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)


class UnstampedTicketTest(_WithRepo):

    def test_an_unstamped_ticket_line_is_left_out_and_counted_as_such(self):
        path = os.path.join(self.tmp, "unstamped.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(QUEUE + "TICKET t6 waited 999\nTICKET t7 waited 999\n")
        m = flow.measure(self.repo.path, "2026-01-01", path, None)
        self.assertEqual((m["tickets"], m["median_ticket_wait_s"], m["tickets_unstamped"]), (3, 12, 2))
        self.assertIn("2 unstamped TICKET lines left out", flow.render(m))


class IntegrationMergeTest(unittest.TestCase):
    """An agent branch merged into a sprint branch, then the sprint merged into main: the agent's fix round is
    counted once, at the agent merge. The integration merge's range also holds the agent merge commit (its subject
    says "fix round") and the controller's plan commit `docs(sprint-1): A fix round merged`: neither is a round."""

    @classmethod
    def setUpClass(cls):
        r = cls.repo = _Repo()
        r.commit("root.txt", ["root"], "feat: the root", 2)
        r.git("checkout", "-q", "-b", "sprint-1", day=2)
        r.git("checkout", "-q", "-b", "agent/a", day=2)
        r.commit("a.txt", ["one"], "feat(a): the thing", 3)
        r.commit("a.txt", ["two"], "fix(a): review fix round 1", 4)
        r.git("checkout", "-q", "sprint-1", day=4)
        r.git("merge", "-q", "--no-ff", "-m", "merge agent/a: review PASS after one fix round", "agent/a", day=5)
        r.commit("docs/plan.md", ["log"], "docs(sprint-1): A fix round merged", 6)
        r.git("checkout", "-q", "main", day=6)
        r.git("merge", "-q", "--no-ff", "-m", "Sprint 1: the sprint to main", "sprint-1", day=7)

    @classmethod
    def tearDownClass(cls):
        cls.repo.remove()

    def test_the_round_is_counted_once_at_the_agent_merge(self):
        m = flow.measure(self.repo.path, "2026-01-01", None, None)
        self.assertEqual(m["merges"], 2)
        self.assertEqual(m["fix_rounds_per_merge"], {0: 1, 1: 1})
        self.assertEqual(m["fix_rounds_per_merge_broad"], {0: 1, 1: 1})


class ShallowCloneTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repo = _build()
        cls.shallow = tempfile.mkdtemp(prefix="flow_shallow_")
        url = "file:///" + cls.repo.path.replace("\\", "/").lstrip("/")
        subprocess.run(["git", "clone", "-q", "--depth", "1", url, os.path.join(cls.shallow, "c")],
                       capture_output=True, check=True)
        cls.clone = os.path.join(cls.shallow, "c")

    @classmethod
    def tearDownClass(cls):
        cls.repo.remove()
        shutil.rmtree(cls.shallow, ignore_errors=True)

    def test_the_command_refuses_a_shallow_clone(self):
        out = os.path.join(self.shallow, "page.md")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = flow.main(["--repo", self.clone, "--out", out, "--since", "2026-01-01"])
        self.assertEqual(rc, 2)
        self.assertIn("shallow", buf.getvalue())
        self.assertFalse(os.path.exists(out))


class TreeTest(unittest.TestCase):
    """Class G: the page on this tree is a render of the commit it names, every suite run.

    The page counts commits, so it can never be a render of the commit that writes it (that commit is one more);
    it names the commit it was rendered at and the suite re-renders there. The ticket-wait line is left out of the
    comparison: the queue log is a git-ignored local file, so only `flow --check` on the machine that has it can
    hold that line."""

    def test_the_page_is_a_render_of_the_commit_it_names(self):
        reason = flow.changelog.shallow_reason(REPO)
        if reason:
            self.skipTest(reason)
        with open(os.path.join(REPO, flow.PAGE), "r", encoding="utf-8") as fh:
            on_disk = fh.read()
        rev, since = flow.page_header(on_disk)
        fresh = flow.render(flow.measure(REPO, since, None, None, rev=rev))

        def held(text):
            return [l for l in text.splitlines() if not l.startswith("- **%s**" % flow.LABELS["median_ticket_wait_s"])]

        self.assertTrue(held(on_disk) == held(fresh),
                        "docs/FLOW.md is not a render of %s: run python -m tools_py.flow and commit it" % rev)


if __name__ == "__main__":
    unittest.main()
