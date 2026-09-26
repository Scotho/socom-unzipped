"""tools_py/changelog.py: the changelog generated from merge commits and tags (Sprint 14 Task S1, R272).

A throwaway repository is built per class: on `main`, a root commit, two `--no-ff` merges (`feat/one` with a house
subject, `feat/two` with git's default subject), an annotated tag `v0.1`, a direct commit that is NOT a merge and
must not appear, then `feat/three`, into which `main` is merged first (the reverse direction), merged `--no-ff`.
Expected: two entries under `v0.1`; after it, the `feat/three` merge on the first-parent line and, under it, the
`main`-into-`feat/three` merge from the merged branch's own line.
"""
import os
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools_py import changelog

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Repo(object):
    """A small git repository with fixed identities and dates, so every render of it is byte-identical."""

    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="changelog_")
        self.tick = 0
        self.git("init", "-q", "-b", "main")

    def git(self, *args):
        self.tick += 1
        stamp = "2026-01-%02dT12:00:00+00:00" % min(self.tick, 28)
        env = dict(os.environ, GIT_AUTHOR_NAME="Test Person", GIT_AUTHOR_EMAIL="test@example.com",
                   GIT_COMMITTER_NAME="Test Person", GIT_COMMITTER_EMAIL="test@example.com",
                   GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        out = subprocess.run(["git", "-c", "core.hooksPath=.no-hooks", "-c", "commit.gpgsign=false",
                              "-c", "tag.gpgsign=false"] + list(args),
                             cwd=self.path, env=env, capture_output=True, text=True, check=True)
        return out.stdout.strip()

    def commit(self, name, text):
        with open(os.path.join(self.path, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        self.git("add", "--", name)
        self.git("commit", "-q", "-m", "add " + name, "--", name)
        return self.git("rev-parse", "HEAD")

    def merge(self, branch, message=None):
        args = ["merge", "-q", "--no-ff", branch]
        if message:
            args[3:3] = ["-m", message]
        self.git(*args)
        return self.git("rev-parse", "HEAD")

    def remove(self):
        shutil.rmtree(self.path, ignore_errors=True)


class EntriesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        r = cls.repo = _Repo()
        r.commit("root.txt", "root\n")
        r.git("checkout", "-q", "-b", "feat/one")
        r.commit("one.txt", "one\n")
        r.git("checkout", "-q", "main")
        cls.m1 = r.merge("feat/one", "merge feat/one: the first thing -- and its details\n\nThe body of one.")
        r.git("checkout", "-q", "-b", "feat/two")
        r.commit("two.txt", "two\n")
        r.git("checkout", "-q", "main")
        cls.m2 = r.merge("feat/two")                       # git's default subject: "Merge branch 'feat/two'"
        r.git("tag", "-a", "v0.1", "-m", "the first release")
        cls.direct = r.commit("direct.txt", "not a merge\n")
        r.git("checkout", "-q", "-b", "feat/three", cls.m2)
        r.commit("three.txt", "three\n")
        cls.back = r.merge("main")                         # the reverse direction: main merged into the branch
        r.git("checkout", "-q", "main")
        cls.m3 = r.merge("feat/three", "merge feat/three: the third thing")
        cls.rows = changelog.entries(r.path)
        cls.tags = changelog.tags(r.path)

    @classmethod
    def tearDownClass(cls):
        cls.repo.remove()

    def by_sha(self, sha):
        return [e for e in self.rows if e["sha"] == sha][0]

    def test_two_entries_under_the_tag_and_the_rest_after_it(self):
        self.assertEqual([t["name"] for t in self.tags], ["v0.1"])
        under = [e["sha"] for e in self.rows if e["tag"] == "v0.1"]
        after = [e["sha"] for e in self.rows if e["tag"] is None]
        self.assertEqual(under, [self.m2, self.m1], "newest first")
        self.assertEqual(after, [self.m3, self.back], "the merged branch's own merge follows the merge that brought it")

    def test_a_non_merge_commit_never_appears(self):
        self.assertNotIn(self.direct, [e["sha"] for e in self.rows])
        self.assertEqual(len(self.rows), 4)

    def test_the_fields_of_a_house_subject(self):
        e = self.by_sha(self.m1)
        self.assertEqual(set(e), {"sha", "date", "branch", "subject_head", "body", "tag", "via", "direction"})
        self.assertEqual(e["branch"], "feat/one")
        self.assertEqual(e["subject_head"], "the first thing")
        self.assertEqual(e["body"], "The body of one.")
        self.assertEqual(e["date"], "2026-01-10")
        self.assertIsNone(e["via"])

    def test_a_default_subject_is_kept_as_is(self):
        e = self.by_sha(self.m2)
        self.assertEqual(e["subject_head"], "Merge branch 'feat/two'")
        self.assertEqual(e["branch"], "feat/two")

    def test_main_merged_into_a_branch_is_listed_as_main_merged_in(self):
        e = self.by_sha(self.back)
        self.assertEqual(e["via"], self.m3)
        self.assertEqual(e["branch"], "main")
        self.assertEqual(e["direction"], "main merged in")
        self.assertIsNone(self.by_sha(self.m3)["direction"])

    def test_render_is_stable_and_newest_first(self):
        page = changelog.render(self.rows, self.tags)
        self.assertEqual(page, changelog.render(self.rows, self.tags))
        self.assertIn("python -m tools_py.changelog", page)
        self.assertIn("4 merges", page)
        since, tagged = page.index("## Since v0.1"), page.index("## v0.1")
        self.assertLess(since, tagged)
        self.assertIn("`%s`" % self.m1[:8], page)
        self.assertIn("[main, main merged in]", page)
        self.assertNotIn("add direct.txt", page)

    def test_a_house_subject_names_its_branch(self):
        cases = [
            ("merge agent/s14-d2: the ruling scope rule (Sprint 14 D2)", "agent/s14-d2",
             "the ruling scope rule (Sprint 14 D2)"),
            ("merge: origin/main (9b566459, PR #64 build_revision) into sprint-14; KNOWN's #56 row settled",
             "origin/main", "origin/main (9b566459, PR #64 build_revision) into sprint-14; KNOWN's #56 row settled"),
            ("Merge pull request #49 from Scotho/sprint-11", "sprint-11", "Merge pull request #49 from Scotho/sprint-11"),
            ("Merge remote-tracking branch 'origin/main' into sprint-9", "origin/main",
             "Merge remote-tracking branch 'origin/main' into sprint-9"),
            ("Merge agent/s13-o2 (Sprint 13 O2, #26: the chat step -- R1 opens the box) into sprint-13", "agent/s13-o2",
             "Sprint 13 O2, #26: the chat step"),
            ("merge: Sprint 12 to main -- the readable image; v0.12.0", "sprint-12", "Sprint 12 to main"),
            ("Sprint 13: nothing carried twice (#61)", "sprint-13", "Sprint 13: nothing carried twice (#61)"),
            ("Merge sprint-9: A stranger's first run (v0.9.0)", "sprint-9", "A stranger's first run (v0.9.0)"),
            ("merge: agent/disc -- the new-developer build chain closed -- (43 tests)", "agent/disc",
             "the new-developer build chain closed"),
            ("merge: the dev chain's record -- `docs/X.md` and more", "", "the dev chain's record"),
        ]
        for subject, branch, head in cases:
            with self.subTest(subject=subject):
                self.assertEqual(changelog.branch_of(subject), branch)
                self.assertEqual(changelog.subject_head(subject), head)

    def test_main_is_recognised_in_either_spelling(self):
        self.assertEqual(changelog.direction_of("origin/main"), "main merged in")
        self.assertEqual(changelog.direction_of("main"), "main merged in")
        self.assertIsNone(changelog.direction_of("sprint-13"))


class CliTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        r = cls.repo = _Repo()
        r.commit("root.txt", "root\n")
        r.git("checkout", "-q", "-b", "feat/one")
        r.commit("one.txt", "one\n")
        r.git("checkout", "-q", "main")
        r.merge("feat/one")

    @classmethod
    def tearDownClass(cls):
        cls.repo.remove()

    def setUp(self):
        self.out = os.path.join(tempfile.mkdtemp(prefix="changelog_out_"), "CHANGELOG.md")

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.out), ignore_errors=True)

    def run_main(self, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = changelog.main(args)
        return rc, buf.getvalue()

    def test_write_then_check_then_stale(self):
        args = ["--repo", self.repo.path, "--out", self.out]
        self.assertEqual(self.run_main(args)[0], 0)
        self.assertEqual(self.run_main(args + ["--check"])[0], 0)
        with open(self.out, "a", encoding="utf-8") as fh:
            fh.write("a hand edit\n")
        rc, said = self.run_main(args + ["--check"])
        self.assertEqual(rc, 1)
        self.assertIn("-a hand edit", said, "the diff head is printed")

    def test_check_on_a_missing_file_exits_1(self):
        self.assertEqual(self.run_main(["--repo", self.repo.path, "--out", self.out, "--check"])[0], 1)

    def test_the_module_runs_as_a_command(self):
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write("stale\n")
        p = subprocess.run([sys.executable, "-m", "tools_py.changelog", "--check", "--repo", self.repo.path,
                            "--out", self.out], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("stale", p.stdout)


class ShallowCloneTest(unittest.TestCase):
    """A depth-1 clone has no merges to read: the skip condition is computed from git, and the tool refuses
    rather than rendering "0 merges" as though that were the history."""

    @classmethod
    def setUpClass(cls):
        r = cls.repo = _Repo()
        r.commit("root.txt", "root\n")
        r.git("checkout", "-q", "-b", "feat/one")
        r.commit("one.txt", "one\n")
        r.git("checkout", "-q", "main")
        r.merge("feat/one")
        cls.shallow = tempfile.mkdtemp(prefix="changelog_shallow_")
        url = "file:///" + r.path.replace("\\", "/").lstrip("/")
        subprocess.run(["git", "clone", "-q", "--depth", "1", url, os.path.join(cls.shallow, "c")],
                       capture_output=True, check=True)
        cls.clone = os.path.join(cls.shallow, "c")

    @classmethod
    def tearDownClass(cls):
        cls.repo.remove()
        shutil.rmtree(cls.shallow, ignore_errors=True)

    def test_a_shallow_clone_gives_a_reason(self):
        reason = changelog.shallow_reason(self.clone)
        self.assertTrue(reason and "shallow" in reason, reason)

    def test_a_full_repository_gives_none(self):
        self.assertIsNone(changelog.shallow_reason(self.repo.path))

    def test_entries_refuse_a_shallow_clone(self):
        with self.assertRaises(changelog.ShallowHistory):
            changelog.entries(self.clone)

    def test_the_command_refuses_a_shallow_clone_with_a_sentence(self):
        out = os.path.join(self.shallow, "page.md")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = changelog.main(["--repo", self.clone, "--out", out, "--check"])
        self.assertEqual(rc, 2)
        self.assertIn("shallow", buf.getvalue())
        self.assertFalse(os.path.exists(out))


class TreeTest(unittest.TestCase):
    """Class G: the page on this tree is held to the history it was rendered from, every suite run.

    It is rendered at the commit that last wrote it (or at HEAD while it has uncommitted changes), not at HEAD: a
    merge commit that lands after it -- the controller's own merge of an agent branch, a pull request's synthetic
    merge in CI, the sprint's merge on `main` -- must not redden the suite. Whether the page is current with HEAD is
    `python -m tools_py.changelog --check`'s question, asked at every merge's follow-up and at the close.
    """

    def test_the_page_on_this_tree_is_a_render_of_its_own_history(self):
        # A depth-1 checkout (windows.yml's second job runs the whole suite on one) holds one commit and no merges:
        # the page cannot be rendered there, so the test says so instead of failing (test_story_cite's
        # TestShallowClone is the precedent for a check that must know it is on a shallow clone).
        reason = changelog.shallow_reason(REPO)
        if reason:
            self.skipTest(reason)
        with open(os.path.join(REPO, changelog.PAGE), "r", encoding="utf-8") as fh:
            on_disk = fh.read()
        rev = changelog.page_rev(REPO)
        fresh = changelog.render(changelog.entries(REPO, rev), changelog.tags(REPO, rev))
        self.assertTrue(on_disk == fresh,
                        "docs/CHANGELOG.md is not a render of %s: run python -m tools_py.changelog and commit it" % rev)


if __name__ == "__main__":
    unittest.main()
