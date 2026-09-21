"""Sprint 9 Goal 2: run.sh starts $SOCOM_EXE when it is set. On Windows the gate's drive launches through
run.sh (drive.py), so this is the line that lets a gate score dist-release/socom2.exe. The fake runner is a
two-line shell script; the run takes well under a second. Side effect: run.sh repoints logs/latest.log."""
import os
import stat
import subprocess
import tempfile
import unittest
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@unittest.skipUnless(BASH, "bash only")
class RunShExeTest(unittest.TestCase):
    def test_socom_exe_names_the_binary_run_sh_starts(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "socom2")
            with open(fake, "w", newline="\n") as fh:
                fh.write("#!/usr/bin/env bash\necho \"fake-runner got $1\"\n")
            os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
            log = os.path.join(tmp, "run.log")
            env = {**os.environ, "SOCOM_EXE": fake.replace("\\", "/"), "PS2X_RUN_LOG": log.replace("\\", "/")}
            r = subprocess.run([BASH, os.path.join(ROOT, "run.sh"), "5"], capture_output=True, text=True,
                               cwd=ROOT, env=env, timeout=60)
            self.assertIn("exe=" + fake.replace("\\", "/"), r.stdout, r.stdout + r.stderr)
            with open(log) as fh:
                self.assertIn("fake-runner got ", fh.read())
            self.assertIn("socom2_game.elf", open(log).read())


if __name__ == "__main__":
    unittest.main()
