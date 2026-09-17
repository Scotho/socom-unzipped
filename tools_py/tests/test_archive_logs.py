"""Sprint 6 Task 8: scripts/archive_logs.ps1 moves gate stamps and run logs older than N days to the archive
drive, never the ones docs/KNOWN.md section 1 names, dry-run by default."""
import os
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "archive_logs.ps1")


def _age(path, days):
    t = time.time() - days * 86400
    os.utime(path, (t, t))
    for dirpath, dirnames, filenames in os.walk(path):
        for n in dirnames + filenames:
            os.utime(os.path.join(dirpath, n), (t, t))
        os.utime(dirpath, (t, t))


def _run(args):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT] + args,
                          capture_output=True, text=True, cwd=ROOT)


@unittest.skipUnless(shutil.which("powershell"), "PowerShell only")
class ArchiveLogsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.logs = os.path.join(self.tmp, "logs")
        self.dest = os.path.join(self.tmp, "archive")
        gate = os.path.join(self.logs, "parity", "gate")
        for stamp in ("old_stamp", "s6_ladder8", "new_stamp"):
            d = os.path.join(gate, stamp, "title")
            os.makedirs(d)
            with open(os.path.join(d, "s00.png"), "wb") as f:
                f.write(b"x" * 1000)
        for log in ("run_A_20260901_000000.log", "run_A_20260913_115809.log", "run_A_20260917_000000.log"):
            with open(os.path.join(self.logs, log), "w") as f:
                f.write("log\n")
        _age(os.path.join(gate, "old_stamp"), 30)
        _age(os.path.join(gate, "s6_ladder8"), 30)
        _age(os.path.join(self.logs, "run_A_20260901_000000.log"), 30)
        _age(os.path.join(self.logs, "run_A_20260913_115809.log"), 30)
        self.known = os.path.join(self.tmp, "KNOWN.md")
        with open(self.known, "w") as f:
            f.write("## 1. Proven\n\n| `logs/parity/s6_ladder8` and `logs/run_[AB]_20260913_115809.log` |\n\n"
                    "## 2. Believed\n\n| `logs/parity/gate/old_stamp` is only believed |\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run_lists_the_old_unprotected_items_and_moves_nothing(self):
        r = _run(["-Root", self.logs, "-Dest", self.dest, "-Days", "14", "-Known", self.known])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRY RUN", r.stdout)
        self.assertIn("old_stamp", r.stdout)
        self.assertIn("run_A_20260901_000000.log", r.stdout)
        self.assertNotIn("s6_ladder8", r.stdout.split("->")[1])          # protected by section 1
        self.assertNotIn("run_A_20260913_115809", r.stdout.split("->")[1])
        self.assertNotIn("new_stamp", r.stdout)
        self.assertTrue(os.path.isdir(os.path.join(self.logs, "parity", "gate", "old_stamp")))
        self.assertFalse(os.path.exists(self.dest))

    def test_apply_moves_them_keeping_the_relative_paths(self):
        r = _run(["-Root", self.logs, "-Dest", self.dest, "-Days", "14", "-Known", self.known, "-Apply"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("MOVING", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "parity", "gate", "old_stamp", "title", "s00.png")))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "run_A_20260901_000000.log")))
        self.assertFalse(os.path.exists(os.path.join(self.logs, "parity", "gate", "old_stamp")))
        for kept in ("parity/gate/s6_ladder8", "parity/gate/new_stamp", "run_A_20260913_115809.log",
                     "run_A_20260917_000000.log"):
            self.assertTrue(os.path.exists(os.path.join(self.logs, kept)), kept)


if __name__ == "__main__":
    unittest.main()
