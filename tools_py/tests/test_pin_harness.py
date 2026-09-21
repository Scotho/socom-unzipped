"""scripts/pin_harness.sh: a launch-hygiene snapshot of tools_py/ and scripts/ pinned at a commit
(Sprint 5 R46/A5), so a launch running for tens of minutes is scored by the code that was reviewed
for it, not by whatever lands in the live tree meanwhile.

Runs against the real repo (git archive of tracked files only, into a temp out_dir) -- read-only,
no working-tree changes. Skipped where bash or a usable git tree is unavailable.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "pin_harness.sh")

@unittest.skipUnless(BASH, "bash not found")
class TestPinHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pin_harness_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_pin(self, *args, timeout=90):
        return subprocess.run([BASH, SCRIPT] + list(args), capture_output=True, text=True,
                              cwd=ROOT, timeout=timeout)

    def test_usage_with_no_args(self):
        p = self.run_pin()
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("usage", (p.stdout + p.stderr).lower())

    def test_unresolvable_sha_fails_cleanly(self):
        out_dir = os.path.join(self.tmp, "out")
        p = self.run_pin(out_dir, "not-a-real-sha-xyz")
        self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("cannot resolve", (p.stdout + p.stderr).lower())

    def test_default_sha_is_head_and_snapshot_is_complete(self):
        # This repo is shared by other concurrently-running agents (KNOWN.md): HEAD can move between
        # any two commands. Bracket the call with a HEAD read before and after rather than trusting a
        # value captured at module import time (which raced a real commit and failed once, 2026-09-13).
        def head():
            return subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True,
                                  text=True, check=True).stdout.strip()

        before = head()
        out_dir = os.path.join(self.tmp, "out")
        p = self.run_pin(out_dir)
        after = head()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        harness = os.path.join(out_dir, "harness")
        self.assertTrue(os.path.isdir(os.path.join(harness, "tools_py")), p.stdout)
        self.assertTrue(os.path.isdir(os.path.join(harness, "scripts")), p.stdout)
        # A file the tracked tree definitely carries, proving the archive actually ran.
        self.assertTrue(os.path.exists(os.path.join(harness, "scripts", "loop_lock.sh")))

        commit_file = os.path.join(harness, "HARNESS_COMMIT")
        self.assertTrue(os.path.exists(commit_file))
        with open(commit_file) as f:
            sha = f.read().strip()
        self.assertIn(sha, (before, after), "HEAD moved (another agent committed); pinned %r, saw "
                                            "before=%r after=%r" % (sha, before, after))
        self.assertRegex(sha, r"^[0-9a-f]{40}$")

    def test_pins_an_explicit_older_sha(self):
        # --verify, or a shallow clone (CI checks out depth 1) makes rev-parse echo "HEAD~1" back on
        # stdout with a non-zero status, and the skip below never fires.
        p = subprocess.run(["git", "-C", ROOT, "rev-parse", "--verify", "HEAD~1"], capture_output=True,
                           text=True)
        parent = p.stdout.strip()
        if p.returncode != 0 or len(parent) != 40:
            self.skipTest("no parent commit available (shallow clone?)")
        out_dir = os.path.join(self.tmp, "out")
        p = self.run_pin(out_dir, parent)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        with open(os.path.join(out_dir, "harness", "HARNESS_COMMIT")) as f:
            self.assertEqual(f.read().strip(), parent)

    def test_exe_build_file_names_mtime_and_sha256(self):
        exe = os.path.join(ROOT, "dist", "socom2.exe")
        if not os.path.exists(exe):
            self.skipTest("dist/socom2.exe not built in this environment")
        out_dir = os.path.join(self.tmp, "out")
        p = self.run_pin(out_dir)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        with open(os.path.join(out_dir, "harness", "EXE_BUILD")) as f:
            line = f.read().strip()
        self.assertIn("mtime=", line)
        self.assertIn("sha256=", line)
        m = re.search(r"sha256=([0-9a-f]{64})", line)
        self.assertIsNotNone(line)
        self.assertIsNotNone(m, line)
        # sha256sum prefixes the whole line with "\" when the path contains a backslash; use a
        # forward-slash path so the digest is the bare first token.
        real = subprocess.run(["sha256sum", exe.replace("\\", "/")], capture_output=True,
                              text=True).stdout.split()[0].lstrip("\\")
        self.assertEqual(m.group(1), real)

    def test_dry_import_check_resolves_under_the_pinned_copy(self):
        # This is the mechanism a launch script must use (documented in the script's own header):
        # cwd stays the repo root (online_match_ours.py/drive.py need cwd-relative game/log paths),
        # PYTHONPATH points at the pinned copy, and PYTHONSAFEPATH=1 stops Python from silently
        # prepending cwd (which would otherwise shadow the pin with the live tree's own tools_py/).
        out_dir = os.path.join(self.tmp, "out")
        p = self.run_pin(out_dir)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        harness = os.path.join(out_dir, "harness")
        env = dict(os.environ)
        env["PYTHONPATH"] = harness
        env["PYTHONSAFEPATH"] = "1"
        check = subprocess.run(
            [sys.executable, "-c", "import tools_py.parity.online_match_ours as m; print(m.__file__)"],
            capture_output=True, text=True, cwd=ROOT, env=env, timeout=30)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        resolved = check.stdout.strip()
        self.assertTrue(
            os.path.normcase(os.path.abspath(resolved)).startswith(os.path.normcase(os.path.abspath(harness))),
            "resolved to %r, not under the pinned copy %r" % (resolved, harness))
        # And the script's own built-in sanity check must have reported success.
        self.assertIn("pin_harness: OK", p.stdout)


if __name__ == "__main__":
    unittest.main()
