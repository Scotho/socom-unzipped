"""The Claude Code PreToolUse guard (Sprint 14 Task G1): every refusal fired once against a planted command, one
allowed neighbour per rule, and the wiring -- scripts/hooks/claude_pretool.sh fed a hook JSON document on stdin.

The rules and their homes are listed in docs/DEVELOPING.md, "Guards".
"""
import json
import os
import subprocess
import tempfile
import unittest

from tools_py.hooks import pretool
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOK_SH = os.path.join(ROOT, "scripts", "hooks", "claude_pretool.sh")

CASES = [  # (command, is_worktree, expect_exit) -- the plan's Step 1 table (a commit names its paths)
    ("git add -A", False, 2), ("git add -- docs/KNOWN.md", False, 0),
    ("git add .", False, 2), ("git add -u", False, 2),
    ("git commit -m 'x'", False, 2), ("git commit --no-edit", False, 2),
    ("git commit -a -m 'x'", False, 2), ("git commit --all -m 'x'", False, 2),
    ("git commit -m 'x' -- docs/KNOWN.md", False, 0), ("git commit -m 'x' -- a", False, 0),
    ("git commit --no-verify -m 'x' -- a", False, 2), ("git push --no-verify", False, 2),
    ("git push origin sprint-14", True, 2), ("git push origin sprint-14", False, 0),
    ("git config remote.origin.pushurl x", True, 2), ("git config --worktree remote.origin.pushurl x", True, 0),
    ("git config --get user.name", True, 0), ("git config user.name x", False, 0),
    ("git worktree remove --force C:/projects/wt-x", False, 2),
    ("bash scripts/agent_worktree.sh remove wt-x", False, 0),
    ("bash scripts/loop_lock.sh take", False, 2), ("bash scripts/loop_lock.sh release", False, 2),
    ("bash scripts/loop_lock.sh check", False, 0), ("bash scripts/loop_lock.sh run -- ./build.sh runtime", False, 0),
]

MORE_CASES = [  # compound commands, quoting, spellings the table does not reach
    ("git status && git add -A", False, 2),
    ("git add -- a; git commit -m x", False, 2), ("git add -- a; git commit -m x -- a", False, 0),
    ("git commit --amend --no-edit", False, 2), ("git commit --amend --no-edit -- a", False, 0),
    ("git commit -m x --pathspec-from-file=list.txt", False, 0),
    ("echo 'git add -A'", False, 0),                        # a quoted string, not a command
    ("git commit -m 'unterminated", False, 0),              # shlex cannot parse it: allowed
    ("git add", False, 2), ("git add --all", False, 2), ("git add -- .", False, 2), ("git add -Av", False, 2),
    ("git add -f -- logs/x.txt", False, 0),
    ("git commit -am 'fix'", False, 2), ("git commit -m 'a -a' -- f", False, 0),
    ("git commit -n -m x -- f", False, 2),                  # -n is commit's --no-verify
    ("git -C /c/projects/wt-x push origin b", True, 2),
    ("git status | grep x || git add -u", False, 2),
    ("git status\ngit add .", False, 2),
    ("git config --list", True, 0), ("git config -l", True, 0), ("git config --get-regexp remote", True, 0),
    ("git config --get-all remote.origin.push", True, 0), ("git config user.name", True, 0),
    ("git worktree prune", False, 2), ("git worktree add ../wt-y", False, 2), ("git worktree list", False, 0),
    ("./scripts/loop_lock.sh take", False, 2), ("bash /c/projects/socom_pc/scripts/loop_lock.sh release", False, 2),
    ("bash scripts/loop_lock.sh wait 5", False, 0), ("bash scripts/loop_lock.sh version", False, 0),
    ("git commit -F - -- f <<'EOF'\ngit add -A\nEOF", False, 0),   # a heredoc body is not a command
]


class PretoolPlantedTest(unittest.TestCase):
    def run_cases(self, cases):
        for cmd, wt, want in cases:
            code, why = pretool.decide("Bash", {"command": cmd}, "C:/projects/socom_pc", wt)
            self.assertEqual(code, want, (cmd, why))
            if want == 2:
                self.assertIn("home:", why)
            else:
                self.assertEqual(why, "")

    def test_each_planted_command(self):
        self.run_cases(CASES)

    def test_compound_and_edge_commands(self):
        self.run_cases(MORE_CASES)

    def test_a_bare_commit_passes_during_a_merge(self):
        # git refuses a partial commit while MERGE_HEAD exists, so the pathspec rule steps aside
        for cmd in ("git commit -m 'x'", "git commit --no-edit"):
            self.assertEqual(pretool.decide("Bash", {"command": cmd}, ".", False, merge_in_progress=True), (0, ""))
        self.assertEqual(pretool.decide("Bash", {"command": "git commit -a --no-edit"}, ".", False,
                                        merge_in_progress=True)[0], 2)

    def test_a_cd_into_a_worktree_is_followed(self):
        seen = []

        def worktree_of(path):
            seen.append(path)
            return "wt-" in path

        code, why = pretool.decide("Bash", {"command": "cd /c/projects/wt-s14-g1 && git push"},
                                   "C:/projects/socom_pc", False, worktree_of=worktree_of)
        self.assertEqual(code, 2, why)
        self.assertTrue(seen)
        code, why = pretool.decide("Bash", {"command": "cd /c/projects/socom_pc && git push"},
                                   "C:/projects/wt-s14-g1", True, worktree_of=worktree_of)
        self.assertEqual(code, 0, why)

    def test_other_tools_and_bad_input_pass(self):
        self.assertEqual(pretool.decide("Read", {"file_path": "x"}, ".", True), (0, ""))
        self.assertEqual(pretool.decide("Bash", {}, ".", True), (0, ""))
        self.assertEqual(pretool.decide("Bash", {"command": None}, ".", True), (0, ""))


class ClaudeDirIgnoreTest(unittest.TestCase):
    """The repository's .gitignore owns .claude/: settings.json, agents/ and skills/ tracked, the harness's local state
    ignored -- even on a machine whose global excludes file ignores `.claude/*` (the owner's does)."""

    def ignored(self, path):
        p = subprocess.run(["git", "check-ignore", "--no-index", "-q", path], cwd=ROOT, capture_output=True, text=True)
        self.assertIn(p.returncode, (0, 1), p.stderr)
        return p.returncode == 0

    def test_tracked_configuration_is_not_ignored(self):
        for path in (".claude/settings.json", ".claude/agents/x.md", ".claude/skills/x/SKILL.md"):
            self.assertFalse(self.ignored(path), path)

    def test_local_state_is_ignored(self):
        for path in (".claude/worktrees/x", ".claude/scheduled_tasks.lock", ".claude/settings.local.json",
                     ".claude/skills/s2u-bug-reports/SKILL.md"):
            self.assertTrue(self.ignored(path), path)


@unittest.skipUnless(BASH, "bash not found")
class PretoolWiringTest(unittest.TestCase):
    """The shell script, fed the JSON document Claude Code writes on stdin, run from somewhere else entirely."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pretool_")
        subprocess.run(["git", "init", "-q", self.tmp.name], check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, command, tool_name="Bash"):
        doc = {"session_id": "t", "cwd": self.tmp.name, "hook_event_name": "PreToolUse",
               "tool_name": tool_name, "tool_input": {"command": command}, "tool_use_id": "toolu_t"}
        # cwd is the temp repo, not this one: the script must find its own repository, not the caller's
        return subprocess.run([BASH, HOOK_SH.replace("\\", "/")], input=json.dumps(doc), capture_output=True,
                              text=True, cwd=self.tmp.name, timeout=60)

    def test_bulk_add_is_refused(self):
        p = self.hook("git add -A")
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("home:", p.stderr)

    def test_status_passes(self):
        p = self.hook("git status")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, "")

    def test_push_is_refused_only_from_a_linked_worktree(self):
        git = ["git", "-C", self.tmp.name, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "x"], check=True, capture_output=True)
        linked = os.path.join(self.tmp.name, "linked")
        subprocess.run(git + ["worktree", "add", "-q", linked], check=True, capture_output=True)
        self.assertEqual(self.hook("git push origin x").returncode, 0)          # the main tree
        self.assertTrue(pretool.is_worktree_dir(linked))
        self.assertFalse(pretool.is_worktree_dir(self.tmp.name))
        p = self.hook("cd '%s' && git push origin x" % linked.replace("\\", "/"))
        self.assertEqual(p.returncode, 2, p.stderr)

    def test_bare_commit_refused_then_allowed_mid_merge(self):
        git = ["git", "-C", self.tmp.name, "-c", "user.name=t", "-c", "user.email=t@t"]
        self.assertEqual(self.hook("git commit --no-edit").returncode, 2)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "base"], check=True, capture_output=True)
        head = subprocess.run(git + ["rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        with open(os.path.join(self.tmp.name, ".git", "MERGE_HEAD"), "w") as f:
            f.write(head + "\n")
        self.assertTrue(pretool.merge_in_progress_in(self.tmp.name))
        p = self.hook("git commit --no-edit")
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_other_tool_passes(self):
        self.assertEqual(self.hook("git add -A", tool_name="Read").returncode, 0)

    def test_garbage_on_stdin_passes(self):
        p = subprocess.run([BASH, HOOK_SH.replace("\\", "/")], input="not json", capture_output=True, text=True,
                           cwd=self.tmp.name, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
