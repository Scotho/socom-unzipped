"""scripts/build_revision.sh: the pipeline parameterised by disc revision (Sprint 11 Task 9, Goal B).

    bash scripts/build_revision.sh <rev> <APACHE00.ZDB> [--check-against <elf>] [--dry-run] [--stop-after <step>]

These cases hold the script's argument handling and its dry run, through tools_py/tests/shell.BASH (a bare `bash`
resolves to WSL's on a GitHub Windows runner). They touch no disc, take no lock and run no Python stage: the
revision-name check and the package check happen before anything runs, and --dry-run prints the five steps with
their paths and exits.

NOT covered here, because only a disc can cover it: that the pipeline reproduces r0001 byte for byte. That is the
bar the controller runs from the main tree (`r0001check` against dist/socom2_game.elf and recomp/output); the
numbers are in docs/DEVELOPING.md "From your own disc to a buildable ELF".
"""
import os
import subprocess
import unittest

from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join("scripts", "build_revision.sh")
EMPTY_ZDB = os.path.join("tools_py", "tests", "fixtures", "empty.zdb")


def run_bash(*args):
    return subprocess.run([BASH] + list(args), capture_output=True, text=True, cwd=ROOT)


@unittest.skipUnless(BASH, "needs a bash that is not WSL's launcher")
class BuildRevisionArgsTest(unittest.TestCase):
    def test_a_bad_revision_name_is_refused_before_anything_runs(self):
        p = run_bash(SCRIPT, "R4", "nope.zdb")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("revision must look like r0004", p.stderr)

    def test_a_missing_package_is_refused(self):
        p = run_bash(SCRIPT, "r0004", "does/not/exist.zdb")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("no such package", p.stderr)

    def test_dry_run_prints_the_five_steps_and_their_paths(self):
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for s in ("decrypt", "game/overlays_r0004/", "make_overlay_elf", "recomp/output_r0004/", "dist/socom2_r0004.exe"):
            self.assertIn(s, p.stdout)

    def test_a_revision_may_carry_a_suffix_so_a_check_build_never_overwrites_the_real_one(self):
        # The bar is run as `r0001check`: the same disc under a name that cannot collide with r0001's products.
        p = run_bash(SCRIPT, "r0001check", EMPTY_ZDB, "--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("game/overlays_r0001check/", p.stdout)
        p = run_bash(SCRIPT, "r0001-check", EMPTY_ZDB, "--dry-run")
        self.assertEqual(p.returncode, 2, "a suffix is letters and digits only: " + p.stdout + p.stderr)

    def test_stop_after_and_check_against_are_shown_by_the_dry_run(self):
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--dry-run", "--stop-after", "elf", "--check-against", EMPTY_ZDB)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("check-against", p.stdout)
        self.assertIn("stop after elf", p.stdout)
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--dry-run", "--stop-after", "lunch")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("--stop-after", p.stderr)


if __name__ == "__main__":
    unittest.main()
