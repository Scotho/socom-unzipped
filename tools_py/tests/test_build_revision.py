"""scripts/build_revision.sh: the pipeline parameterised by disc revision (Sprint 11 Task 9, Goal B).

    bash scripts/build_revision.sh <rev> <APACHE00.ZDB> [--check-against <elf>] [--dry-run] [--stop-after <step>]

These cases hold the script's argument handling, its preconditions, its dry run and the mark step 4 skips on,
through tools_py/tests/shell.BASH (a bare `bash` resolves to WSL's on a GitHub Windows runner). They touch no
disc, take no lock and run no Python stage: every case stops at a refusal, at the skip check, or at the dry run,
all of them before the first minute of Unicorn and before the first cmake.

NOT covered here, because only a disc can cover it: that the pipeline reproduces r0001 byte for byte. That is the
bar the controller runs from the main tree (`r0001check` against dist/socom2_game.elf and recomp/output); the
numbers are in docs/DEVELOPING.md "From your own disc to a buildable ELF".
"""
import os
import subprocess
import tempfile
import unittest

from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join("scripts", "build_revision.sh")
EMPTY_ZDB = os.path.join("tools_py", "tests", "fixtures", "empty.zdb")


def run_bash(*args, **kwargs):
    return subprocess.run([BASH] + list(args), capture_output=True, text=True, cwd=ROOT, **kwargs)


def sh(path):
    """A Windows path as the script's bash reads it: C:/x resolves, C:\\x does not."""
    return path.replace("\\", "/")


def touch(*parts):
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8"):
        pass
    return path


def fake_toolchain(tmp):
    """clang/cmake/ninja stubs for the lock-bound tail's toolchain check, so these cases run on a machine (or a
    CI runner) with no tools/ tree. Nothing here ever invokes them: both cases stop before the first cmake."""
    binaries = os.path.join(tmp, "fakebin")
    os.makedirs(binaries)
    for name in ("clang", "cmake", "ninja"):
        path = os.path.join(binaries, name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("#!/bin/sh\nexit 0\n")
        os.chmod(path, 0o755)
    return binaries


def tail_env(tmp, out, rev="r0004", stop="recomp"):
    """The environment loop_lock.sh hands the re-entered script for steps 4-5."""
    env = dict(os.environ)
    env.update(BR_REV=rev, BR_STOP=stop, BR_FORCE="0", BR_OUT=sh(out))
    env["PATH"] = fake_toolchain(tmp) + os.pathsep + env.get("PATH", "")
    return env


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
        p = run_bash(SCRIPT, "r00012", EMPTY_ZDB, "--dry-run")
        self.assertEqual(p.returncode, 2, "a suffix starts with a letter, so r00012 reads as a typo of r0012, "
                                          "not as a variant of r0001: " + p.stdout + p.stderr)

    def test_stop_after_and_check_against_are_shown_by_the_dry_run(self):
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--dry-run", "--stop-after", "elf", "--check-against", EMPTY_ZDB)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("check-against", p.stdout)
        self.assertIn("stop after elf", p.stdout)
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--dry-run", "--stop-after", "lunch")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("--stop-after", p.stderr)

    def test_an_unknown_option_is_refused(self):
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--wat")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("unknown option", p.stderr)

    def test_the_package_argument_is_required(self):
        p = run_bash(SCRIPT, "r0004")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("usage:", p.stderr)

    def test_a_missing_check_against_elf_is_refused(self):
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--check-against", "nope.elf")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("no such ELF to check against", p.stderr)


@unittest.skipUnless(BASH, "needs a bash that is not WSL's launcher")
class BuildRevisionPreconditionsTest(unittest.TestCase):
    """The inputs step 1 cannot work without, each refused with a sentence before the eight minutes of Unicorn.

    Every case builds a synthetic disc tree in a temporary directory (empty files under the real names) and sends
    every product to --out, so nothing is written inside the repository and no disc byte is involved.
    """

    def test_a_package_that_is_not_the_trees_own_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = os.path.join(tmp, "tree")
            touch(tree, "RUN", "RAW", "APACHE00.ZDB")
            touch(tree, "SCUS_972.75")
            touch(tree, "OVERLAY", "REL", "DNAS.dec.bin")
            stray = touch(tmp, "elsewhere", "APACHE00.ZDB")
            p = run_bash(SCRIPT, "r0004", sh(stray), "--game", sh(tree), "--ghidra-from-r0001",
                         "--out", sh(os.path.join(tmp, "out")))
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("must be the tree's own", p.stderr)

    def test_a_tree_whose_loader_is_not_scus_972_75_stops_with_a_sentence(self):
        # decrypt_apache.py:206 joins 'SCUS_972.75' onto the tree itself, so a PAL/SLUS tree cannot be decrypted
        # by this script; before this check it announced the eight minutes and then died in a Python traceback.
        with tempfile.TemporaryDirectory() as tmp:
            tree = os.path.join(tmp, "tree")
            zdb = touch(tree, "RUN", "RAW", "APACHE00.ZDB")
            touch(tree, "SLES_512.34")
            touch(tree, "OVERLAY", "REL", "DNAS.dec.bin")
            p = run_bash(SCRIPT, "r0004", sh(zdb), "--ghidra-from-r0001",
                         "--out", sh(os.path.join(tmp, "out")))
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("SCUS_972.75", p.stderr)
            self.assertIn("SLES_512.34", p.stderr)
            self.assertNotIn("about eight minutes", p.stdout)


@unittest.skipUnless(BASH, "needs a bash that is not WSL's launcher")
class BuildRevisionFunctionMapTest(unittest.TestCase):
    """r0001's function map is a starting point only for the r0001 disc; any other revision must ask for it."""

    def test_a_foreign_revision_without_a_map_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--out", sh(os.path.join(tmp, "out")))
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("socom2_ghidra_r0004.csv", p.stderr)
            self.assertIn("--ghidra-from-r0001", p.stderr)

    def test_borrowing_r0001s_map_for_a_foreign_revision_warns_on_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--ghidra-from-r0001",
                         "--out", sh(os.path.join(tmp, "out")))
            self.assertIn("WARNING", p.stderr)
            self.assertIn("Task 10", p.stderr)
            # It then stops for another reason (the fixture's tree holds no loader), which is not this test's
            # business; what matters is that the borrowing was announced before any of it.

    def test_the_r0001_disc_borrows_its_own_map_silently(self):
        p = run_bash(SCRIPT, "r0001check", EMPTY_ZDB, "--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("WARNING", p.stderr)

    def test_the_dry_run_says_which_map_step_3_will_use(self):
        # `r0009fake` rather than r0004: once a revision's own map is in recomp/, the dry run says "is
        # already there" instead, and this case is about what it says when there is none.
        p = run_bash(SCRIPT, "r0009fake", EMPTY_ZDB, "--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("--ghidra", p.stdout)

    def test_ghidra_naming_the_revisions_own_map_is_not_a_copy_onto_itself(self):
        """`--ghidra recomp/socom2_ghidra_<rev>.csv` names the map step 3 would use anyway; cp refuses a
        file onto itself, and under `set -e` that killed the run between the ELF and the TOML."""
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--dry-run",
                     "--ghidra", "recomp/socom2_ghidra_r0004.csv")
        if "no such function map" in p.stderr:
            self.skipTest("this tree has no recomp/socom2_ghidra_r0004.csv")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("nothing to copy", p.stdout)


@unittest.skipUnless(BASH, "needs a bash that is not WSL's launcher")
class BuildRevisionForcedEntryPointsTest(unittest.TestCase):
    """recomp/extra_functions.txt is r0001's list of addresses, so it is a per-revision input like the map.

    A revision with no list of its own falls back to r0001's -- 1,453 of whose 1,619 entries are overlay
    addresses that mean something only in r0001 -- so the fallback has to say so. `r0009fake` is used where
    the case must not depend on which recomp/extra_functions_<rev>.txt the working tree happens to hold.
    """

    def test_a_missing_list_is_refused(self):
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--dry-run", "--extra", "recomp/no_such_list.txt")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("no such forced-entry-point list", p.stderr)

    def test_extra_needs_a_path(self):
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--dry-run", "--extra")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)

    def test_the_dry_run_names_the_list_step_4_will_use(self):
        p = run_bash(SCRIPT, "r0004", EMPTY_ZDB, "--dry-run", "--extra", EMPTY_ZDB)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("forced entry points", p.stdout)
        self.assertIn("empty.zdb", p.stdout)

    def test_a_foreign_revision_borrowing_r0001s_list_says_so(self):
        p = run_bash(SCRIPT, "r0009fake", EMPTY_ZDB, "--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("recomp/extra_functions.txt", p.stdout)
        self.assertIn("another build's overlay addresses", p.stdout)

    def test_the_r0001_disc_uses_its_own_list_without_that_note(self):
        p = run_bash(SCRIPT, "r0001check", EMPTY_ZDB, "--dry-run")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("recomp/extra_functions.txt", p.stdout)
        self.assertNotIn("another build's overlay addresses", p.stdout)

    def test_a_foreign_revision_is_warned_on_stderr_outside_the_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = run_bash(SCRIPT, "r0009fake", EMPTY_ZDB, "--ghidra-from-r0001",
                         "--out", sh(os.path.join(tmp, "out")))
            self.assertIn("find_imm_targets.py", p.stderr)


@unittest.skipUnless(BASH, "needs a bash that is not WSL's launcher")
class BuildRevisionRecompSkipTest(unittest.TestCase):
    """Step 4 skips on the mark it writes when ps2_recomp returns 0, never on 'the directory has files in it'.

    Both cases enter the script the way loop_lock.sh does (--_tail with BR_*), with a stub toolchain on PATH.
    Neither reaches a cmake: the first stops at the skip, the second dies on the function map that a temporary
    --out tree does not have -- which is the point, since a run that skipped would never have looked at it.
    """

    def test_a_generated_tree_without_the_mark_is_not_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            gen = os.path.join(out, "recomp_r0004", "output")
            os.makedirs(gen)
            touch(gen, "half_a_game.cpp")
            p = run_bash(SCRIPT, "--_tail", env=tail_env(tmp, out))
            self.assertNotIn("skipped", p.stdout, "a failed recomp left this tree half-written: " + p.stdout)
            self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_a_generated_tree_that_finished_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            gen = os.path.join(out, "recomp_r0004", "output")
            os.makedirs(gen)
            touch(gen, "a_whole_game.cpp")
            touch(gen, ".complete")
            p = run_bash(SCRIPT, "--_tail", env=tail_env(tmp, out))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("skipped", p.stdout)
            self.assertIn("stop after recomp", p.stdout)


if __name__ == "__main__":
    unittest.main()
