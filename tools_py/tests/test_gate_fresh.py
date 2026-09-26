"""Sprint 14 E4: the gate refuses an exe older than its sources, and every record says which tree it measured.

The structure review's F3 (docs/audits/2026-09-26-autonomy-structure-review.md): "stale greens: a gate run that
predates the last edit". A gate launches whatever dist/socom2.exe (or $SOCOM_EXE) is on disk; `./build.sh test` does
not rebuild it, so a PASS could be the verdict on a binary built before the change it is quoted for. gate.freshness is
the pure comparison (the exe's mtime against the newest mtime under the source roots); gate.main refuses with
REFUSE_STALE unless --stale-ok. gate.tree_line is the `TREE <head> dirty=<n>` line every summary and pins.json carry.
Everything here runs on temp files: no build, no game, no lock.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools_py.parity import gate, hostplatform, pins
from tools_py.tests.test_gate_pins import BANNER_STAND_IN, _LaunchCase


def _touch(path, mtime, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    os.utime(path, (mtime, mtime))


class Freshness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.exe = os.path.join(self.tmp, "dist", "socom2.exe")
        self.src = os.path.join(self.tmp, "src")
        _touch(self.exe, 2000000000)

    def test_a_source_newer_than_the_exe_is_stale_and_named(self):
        _touch(os.path.join(self.src, "a", "old.cpp"), 1999999000)
        newer = os.path.join(self.src, "b", "deep", "new.h")
        _touch(newer, 2000000100)
        stale, path, mtime = gate.freshness(self.exe, [self.src])
        self.assertTrue(stale)
        self.assertEqual(os.path.normcase(path), os.path.normcase(newer))
        self.assertEqual(mtime, 2000000100)
        msg = gate.stale_message(2000000000, path, mtime)
        self.assertTrue(msg.startswith("gate: exe older than source ("), msg)
        self.assertIn("new.h", msg)
        self.assertTrue(msg.endswith("): rebuild, or --stale-ok"), msg)

    def test_sources_older_than_the_exe_are_fresh(self):
        _touch(os.path.join(self.src, "a.cpp"), 1999999000)
        single = os.path.join(self.tmp, "recomp", "socom2.toml")
        _touch(single, 1999999500)
        stale, path, mtime = gate.freshness(self.exe, [self.src, single])
        self.assertFalse(stale)
        self.assertEqual(os.path.normcase(path), os.path.normcase(single))
        self.assertEqual(mtime, 1999999500)

    def test_a_file_root_counts_and_a_missing_root_is_skipped(self):
        single = os.path.join(self.tmp, "recomp", "socom2_names.csv")
        _touch(single, 2000000500)
        stale, path, _ = gate.freshness(self.exe, [os.path.join(self.tmp, "absent"), single])
        self.assertTrue(stale)
        self.assertEqual(os.path.normcase(path), os.path.normcase(single))

    # What every exe is linked from (ps2xRuntime/CMakeLists.txt: ps2_runtime links ps2_iop, ps2x_shared and
    # ps2x_snd989, whose sources are ps2xRuntime/src/lib), what the recompiler is built from, and what decides
    # what is compiled -- for either revision.
    COMMON = ("third_party/ps2recomp/CMakeLists.txt", "third_party/ps2recomp/ps2xRuntime/CMakeLists.txt",
              "third_party/ps2recomp/ps2xRuntime/src", "third_party/ps2recomp/ps2xRuntime/include",
              "third_party/ps2recomp/ps2xRuntime/cmake",
              "third_party/ps2recomp/ps2xIOP/CMakeLists.txt", "third_party/ps2recomp/ps2xIOP/src",
              "third_party/ps2recomp/ps2xIOP/include",
              "third_party/ps2recomp/ps2xShared/CMakeLists.txt", "third_party/ps2recomp/ps2xShared/src",
              "third_party/ps2recomp/ps2xShared/include",
              "third_party/ps2recomp/ps2xRecomp/CMakeLists.txt", "third_party/ps2recomp/ps2xRecomp/src",
              "third_party/ps2recomp/ps2xRecomp/include",
              "build.sh", "tools_py/fix_ghidra_csv.py", "tools_py/make_overlay_elf.py",
              "recomp/loader_text_end.txt", "recomp/merge_ranges.txt")

    def _roots(self, revision):
        return [r.replace("\\", "/") for r in gate.freshness_roots("/r", revision)]

    def test_r0001_roots_are_the_common_set_and_r0001s_inputs_only(self):
        roots = self._roots("r0001")
        for want in self.COMMON + ("recomp/output", "recomp/socom2.toml", "recomp/socom2_names.csv",
                                   "recomp/socom2_ghidra.csv", "recomp/extra_functions.txt",
                                   "game/overlays/socom2_game.elf"):
            self.assertIn("/r/" + want, roots)
        self.assertFalse([r for r in roots if "r0004" in r], roots)
        self.assertFalse([r for r in roots if "names_proposals" in r or "name_holds" in r], roots)

    def test_r0004_roots_are_the_common_set_and_r0004s_inputs_only(self):
        roots = self._roots("r0004")
        for want in self.COMMON + ("recomp/output_r0004", "recomp/socom2_r0004.toml", "recomp/socom2_names_r0004.csv",
                                   "recomp/socom2_ghidra_r0004.csv", "recomp/extra_functions_r0004.txt",
                                   "recomp/socom2.toml", "scripts/build_revision.sh", "tools_py/revision_toml.py",
                                   "game/overlays_r0004/socom2_game_r0004.elf"):
            self.assertIn("/r/" + want, roots)
        for unwanted in ("recomp/output", "recomp/socom2_names.csv", "recomp/socom2_ghidra.csv",
                         "recomp/extra_functions.txt"):
            self.assertNotIn("/r/" + unwanted, roots)

    def test_the_revision_comes_from_the_exes_name_or_folder(self):
        self.assertEqual(gate.exe_revision("C:/x/dist/socom2.exe"), "r0001")
        self.assertEqual(gate.exe_revision("C:/x/dist/socom2_r0004.exe"), "r0004")
        self.assertEqual(gate.exe_revision("C:/x/dist-r0004/socom2.exe"), "r0004")
        self.assertEqual(gate.exe_revision("dist-linux/socom2"), "r0001")


class RevisionAndTree(unittest.TestCase):
    """exe_staleness on a planted checkout: the exe's own tree (the directory holding build.sh above it), and only
    its revision's inputs."""

    def setUp(self):
        self.tree = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tree, True)
        _touch(os.path.join(self.tree, "build.sh"), 1999999000)
        _touch(os.path.join(self.tree, "third_party", "ps2recomp", "ps2xRuntime", "src", "a.cpp"), 1999999000)
        _touch(os.path.join(self.tree, "recomp", "output", "sub_1.cpp"), 1999999000)
        _touch(os.path.join(self.tree, "recomp", "output_r0004", "sub_1.cpp"), 1999999000)

    def _exe(self, folder):
        exe = os.path.join(self.tree, folder, hostplatform.exe_name("socom2"))
        _touch(exe, 2000000000)
        return exe

    def test_the_roots_come_from_the_exes_own_checkout(self):
        exe = self._exe("dist")
        self.assertEqual(os.path.normcase(gate.exe_tree(exe)), os.path.normcase(self.tree))
        self.assertIsNone(gate.exe_staleness({"SOCOM_EXE": exe}))
        _touch(os.path.join(self.tree, "third_party", "ps2recomp", "ps2xIOP", "src", "iop.cpp"), 2000000100)
        msg = gate.exe_staleness({"SOCOM_EXE": exe})
        self.assertIsNotNone(msg)
        self.assertIn("third_party/ps2recomp/ps2xIOP/src/iop.cpp", msg)

    def test_no_build_sh_above_the_exe_falls_back_to_this_checkout(self):
        loose = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, loose, True)
        self.assertEqual(gate.exe_tree(os.path.join(loose, "socom2.exe")), gate.ROOT)

    def test_an_r0004_toml_rewrite_does_not_refuse_an_r0001_exe(self):
        exe = self._exe("dist")
        _touch(os.path.join(self.tree, "recomp", "socom2_r0004.toml"), 2000000100)
        _touch(os.path.join(self.tree, "recomp", "output_r0004", "sub_2.cpp"), 2000000100)
        self.assertIsNone(gate.exe_staleness({"SOCOM_EXE": exe}))

    def test_an_r0004_exe_after_a_stop_after_recomp_is_refused(self):
        exe = self._exe("dist-r0004")
        self.assertIsNone(gate.exe_staleness({"SOCOM_EXE": exe}))
        _touch(os.path.join(self.tree, "recomp", "output_r0004", "sub_2.cpp"), 2000000100)
        msg = gate.exe_staleness({"SOCOM_EXE": exe})
        self.assertIsNotNone(msg)
        self.assertIn("recomp/output_r0004/sub_2.cpp", msg)

    def test_an_r0001_output_does_not_refuse_an_r0004_exe(self):
        exe = self._exe("dist-r0004")
        _touch(os.path.join(self.tree, "recomp", "output", "sub_2.cpp"), 2000000100)
        _touch(os.path.join(self.tree, "recomp", "socom2_names.csv"), 2000000100)
        self.assertIsNone(gate.exe_staleness({"SOCOM_EXE": exe}))


class LaunchRefusesAStaleExe(unittest.TestCase):
    """main() up to the lock: the exe is a temp file named through SOCOM_EXE, the roots a temp tree."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.exe = os.path.join(self.tmp, "dist", hostplatform.exe_name("socom2"))
        _touch(self.exe, 2000000000)
        self.src = os.path.join(self.tmp, "src")
        elf = os.path.join(self.tmp, "r0001_stand_in.elf")
        with open(elf, "wb") as f:
            f.write(BANNER_STAND_IN % b"r0001 17:22:21 Oct 11 2003")
        self.stamp = "e4_fresh_test_%d" % os.getpid()
        self.addCleanup(shutil.rmtree, os.path.join("logs", "parity", "gate", self.stamp), True)
        env = mock.patch.dict(os.environ, {"SOCOM_EXE": self.exe, "SOCOM_GAME_ELF": elf}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for p in (mock.patch.object(gate, "free_gb", return_value=99.0),
                  mock.patch.object(gate, "check_pins", return_value=([], {}, False)),
                  mock.patch.object(gate, "freshness_roots", return_value=[self.src])):
            p.start()
            self.addCleanup(p.stop)

    def _main(self, argv=()):
        busy = subprocess.CompletedProcess(["x"], 1, "BUSY: test\n", "")
        out = io.StringIO()
        with mock.patch.object(gate, "_lock", return_value=busy) as lock, contextlib.redirect_stdout(out):
            rc = gate.main(["--stamp", self.stamp, "--only", "title"] + list(argv))
        return rc, out.getvalue(), lock

    def test_a_newer_source_refuses_before_the_lock(self):
        _touch(os.path.join(self.src, "runtime.cpp"), 2000000100)
        rc, out, lock = self._main()
        self.assertEqual(rc, gate.REFUSE_STALE, out)
        self.assertIn("gate: exe older than source (", out)
        self.assertIn("runtime.cpp", out)
        self.assertIn("): rebuild, or --stale-ok", out)
        lock.assert_not_called()
        self.assertFalse(os.path.isdir(os.path.join("logs", "parity", "gate", self.stamp)), "a refusal writes nothing")

    def test_stale_ok_proceeds_and_says_so(self):
        _touch(os.path.join(self.src, "runtime.cpp"), 2000000100)
        rc, out, lock = self._main(["--stale-ok"])
        self.assertEqual(rc, 2, out)      # past the refusal, into the (busy) lock
        self.assertIn("gate: STALE exe accepted (--stale-ok)", out)
        lock.assert_called()

    def test_an_older_source_proceeds_silently(self):
        _touch(os.path.join(self.src, "runtime.cpp"), 1999999000)
        rc, out, lock = self._main()
        self.assertEqual(rc, 2, out)
        self.assertNotIn("STALE", out)
        self.assertNotIn("exe older than source", out)

    def test_the_refusal_code_is_its_own(self):
        self.assertNotIn(gate.REFUSE_STALE, (0, 1, 2, 3, 4, 7, gate.REFUSE_REVISION))


class TreeLine(unittest.TestCase):
    def _git(self, repo, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                               "-c", "core.autocrlf=false", "-c", "core.hooksPath=/dev/null"] + list(args),
                              cwd=repo, capture_output=True, text=True, check=True).stdout

    def test_head_and_one_modified_file_outside_logs_and_game(self):
        repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repo, True)
        self._git(repo, "init", "-q")
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("one\n")
        self._git(repo, "add", "a.txt")
        self._git(repo, "commit", "-q", "-m", "init")
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("two\n")
        for rel in ("logs/run_1.log", "game/disc/x.bin"):
            os.makedirs(os.path.dirname(os.path.join(repo, rel)), exist_ok=True)
            with open(os.path.join(repo, rel), "w") as f:
                f.write("noise\n")
        head = self._git(repo, "rev-parse", "--short", "HEAD").strip()
        self.assertEqual(gate.tree_line(repo), "TREE %s dirty=1" % head)

    def test_the_porcelain_count_skips_logs_and_game_and_reads_renames(self):
        status = (" M tools_py/parity/gate.py\n?? logs/\n?? game/r0004/\nR  old.txt -> logs/new.txt\n"
                  "?? \"docs/a b.md\"\n")
        self.assertEqual(gate.dirty_count(status), 2)

    def test_not_a_repository_says_unknown(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": os.path.dirname(d)}):
            self.assertTrue(gate.tree_line(d).startswith("TREE unknown"), gate.tree_line(d))


class TreeInTheRecord(_LaunchCase):
    def test_summary_and_pins_json_carry_the_tree_line(self):
        with mock.patch.object(gate, "tree_line", return_value="TREE abc1234 dirty=3"):
            rc, out, _ = self._main([])
        self.assertEqual(rc, 0, out)
        self.assertIn("TREE abc1234 dirty=3", out)
        self.assertIn("TREE abc1234 dirty=3\n", self._summary())
        with open(os.path.join(self.out_root, pins.RECORD_NAME), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["tree"], "TREE abc1234 dirty=3")


if __name__ == "__main__":
    unittest.main()
