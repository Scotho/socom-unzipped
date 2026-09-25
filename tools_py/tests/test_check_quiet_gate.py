"""scripts/check_quiet_gate.sh: the write side of Sprint 5 R46/A5's "no build.sh test / unittest
suites while a launch's logs/.quiet marker exists" is scripts/run_detached.sh; this is the read side,
called from build.sh's test_step before the Python stage.

All tests point it at a temp marker file (never the real logs/.quiet) and fake the process-liveness
probe via QUIET_GATE_TASKLIST_CMD, so no test depends on any real running process.
"""
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "check_quiet_gate.sh")


@unittest.skipUnless(BASH, "bash not found")
class TestCheckQuietGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="quiet_gate_test_")
        self.marker = os.path.join(self.tmp, "quiet")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_marker(self, owner="launcher", pid=999999, age_s=60):
        epoch = int(time.time()) - age_s
        with open(self.marker, "w", newline="\n") as f:
            f.write("%s %s %s\n" % (owner, pid, epoch))

    def run_check(self, alive, pid=999999, **env_extra):
        env = dict(os.environ)
        # A caller's FORCE_QUIET=1 (build.sh test run from a chain that already holds the lock) must not decide
        # what this test measures: the gate's refusal is the thing under test, and the override is its own case.
        env.pop("FORCE_QUIET", None)
        # The real probe's output must contain the pid for a hit; a fake "alive" answer must too.
        env["QUIET_GATE_TASKLIST_CMD"] = ("echo ALIVE %s" % pid) if alive else "echo nothing-here"
        env.update({k: str(v) for k, v in env_extra.items()})
        return subprocess.run([BASH, SCRIPT, self.marker], capture_output=True, text=True, env=env,
                              timeout=30)

    def test_no_marker_proceeds(self):
        p = self.run_check(alive=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_fresh_marker_with_live_pid_refuses(self):
        self.write_marker(owner="launcher9", pid=424242, age_s=30)
        p = self.run_check(alive=True, pid=424242)
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("launcher9", p.stdout + p.stderr)
        self.assertIn("424242", p.stdout + p.stderr)

    def test_fresh_marker_with_dead_pid_proceeds(self):
        self.write_marker(age_s=30)
        p = self.run_check(alive=False)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_stale_marker_proceeds_even_if_pid_looks_alive(self):
        self.write_marker(age_s=3 * 3600)
        p = self.run_check(alive=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_max_age_is_configurable(self):
        self.write_marker(age_s=100)
        p = self.run_check(alive=True, QUIET_GATE_MAX_AGE_S=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_force_quiet_overrides_a_live_fresh_marker(self):
        self.write_marker(age_s=30)
        p = self.run_check(alive=True, FORCE_QUIET=1)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("FORCE_QUIET", p.stdout + p.stderr)

    def test_default_marker_path_is_repo_logs_dot_quiet(self):
        # No path argument -> the MAIN tree's logs/.quiet (beside git's common dir, Sprint 13 H2 / audit H13; in a
        # worktree that is not this checkout's logs/), which normally does not exist. The worktree-to-main-tree case
        # itself is test_loop_lock.TestRunDetached.test_quiet_marker_lives_under_the_git_common_dir.
        env = dict(os.environ)
        env["QUIET_GATE_TASKLIST_CMD"] = "echo ALIVE"
        try:
            common = subprocess.run(["git", "-C", ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                    capture_output=True, text=True).stdout.strip()
        except OSError:
            common = ""
        main = os.path.dirname(common) if common and os.path.isdir(common) else ROOT
        real = os.path.join(main, "logs", ".quiet")
        if os.path.exists(real):
            self.skipTest("a real logs/.quiet exists right now (a launch may be running); skipping "
                          "rather than risk racing it")
        p = subprocess.run([BASH, SCRIPT], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
