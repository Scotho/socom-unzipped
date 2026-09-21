"""Sprint 5 close-out fix wave, slice (b) -- launch robustness (the go/no-go review's parked items):

  4. ladder_frostfire.sh's launch mode pins by default; --live is the explicit opt-out (header line 11 is then true);
  5. the next-round spawn check accepts either side's spawn (sides swapped) and records spawns=swapped;
  6. pin_harness.sh's import check does not WARN for a relative or an MSYS /c/... out dir;
  7. an uncaught Python exception is exit 5, CRASH in the done marker -- never read as NO-KILL.

unittest only; no game (the launch test substitutes run_detached.sh).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools_py.parity import online_ladder as LD
from tools_py.parity import online_match_ours as M
from tools_py.tests.test_round_loop_fixes import SPAWNS_8C, Replay
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(ROOT, "scripts", "parity", "ladder_frostfire.sh").replace("\\", "/")
PIN = os.path.join(ROOT, "scripts", "pin_harness.sh").replace("\\", "/")


def fwd(p):
    return p.replace("\\", "/")


class SwappedSpawnsTest(unittest.TestCase):
    def test_swapped_sides_are_accepted_and_recorded(self):
        r = Replay()
        r.feed_to(779.0)
        info = {}
        swapped = {"A": SPAWNS_8C["B"], "B": SPAWNS_8C["A"]}
        ok, reason, actors = LD.wait_next_round(r.tails, 0, clock=r, wait=r.wait, spawns=swapped, info=info,
                                                timeout=30.0)
        self.assertTrue(ok, reason)
        self.assertEqual(info["spawns"], "swapped")
        self.assertEqual(actors, {"A": 0x17941D0, "B": 0x17935C0})

    def test_the_same_sides_record_same(self):
        r = Replay()
        r.feed_to(779.0)
        info = {}
        ok, reason, _ = LD.wait_next_round(r.tails, 0, clock=r, wait=r.wait, spawns=SPAWNS_8C, info=info)
        self.assertTrue(ok, reason)
        self.assertEqual(info["spawns"], "same")

    def test_the_round_start_line_carries_spawns(self):
        with open(M.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("spawns={info.get('spawns')}", src)


class CrashExitTest(unittest.TestCase):
    def test_an_uncaught_exception_is_exit_5(self):
        code = ("import sys; from tools_py.parity import online_match_ours as M\n"
                "def boom(): raise ValueError('boom')\n"
                "M.main = boom\nM.run_main()\n")
        p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, M.CRASH_EXIT, p.stdout + p.stderr)
        self.assertEqual(M.CRASH_EXIT, 5)
        self.assertIn("RESULT CRASH ValueError", p.stdout + p.stderr)
        self.assertIn("Traceback", p.stderr)

    def test_system_exit_passes_through(self):
        code = ("from tools_py.parity import online_match_ours as M\n"
                "def stop(): raise SystemExit(3)\n"
                "M.main = stop\nM.run_main()\n")
        p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)

    @unittest.skipUnless(BASH, "bash not found")
    def test_the_done_marker_says_crash(self):
        p = subprocess.run([BASH, TEMPLATE, "--outcome", "5", "/dev/null"], capture_output=True, text=True, cwd=ROOT,
                           timeout=60)
        self.assertEqual(p.stdout.strip(), "done 5 mpexit=5 CRASH")
        p = subprocess.run([BASH, TEMPLATE, "--outcome", "1", "/dev/null"], capture_output=True, text=True, cwd=ROOT,
                           timeout=60)
        self.assertEqual(p.stdout.strip(), "done 1 mpexit=1 NO-KILL")


@unittest.skipUnless(BASH, "bash not found")
class PinImportCheckTest(unittest.TestCase):
    def check(self, out_dir):
        p = subprocess.run([BASH, PIN, out_dir], capture_output=True, text=True, cwd=ROOT, timeout=180)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("pin_harness: OK", p.stdout, p.stdout + p.stderr)
        self.assertNotIn("WARNING -- pinned import", p.stdout + p.stderr)

    def test_a_relative_out_dir_is_ok(self):
        rel = "logs/parity/test_pin_rel_%d" % os.getpid()
        self.addCleanup(shutil.rmtree, os.path.join(ROOT, rel), True)
        self.check(rel)

    def test_an_msys_drive_path_is_ok(self):
        d = tempfile.mkdtemp(prefix="pin_msys_")
        self.addCleanup(shutil.rmtree, d, True)
        a = fwd(os.path.abspath(d))
        if len(a) > 2 and a[1] == ":":
            a = "/" + a[0].lower() + a[2:]
        self.check(a)


@unittest.skipUnless(BASH, "bash not found")
class PinnedByDefaultTest(unittest.TestCase):
    def launch(self, *flags):
        d = fwd(tempfile.mkdtemp(prefix="ladder_launch_"))
        self.addCleanup(shutil.rmtree, d, True)
        fake = d + "/fake_detached.sh"
        with open(fake, "w", newline="\n") as f:
            f.write('#!/usr/bin/env bash\nprintf "%s\n" "$@" > "' + d + '/detached_args.txt"\nexit 0\n')
        env = dict(os.environ, RUN_DETACHED_SH=fake)
        out = d + "/out"
        p = subprocess.run([BASH, TEMPLATE] + list(flags) + [out], capture_output=True, text=True, cwd=ROOT, env=env,
                           timeout=400)
        args = open(d + "/detached_args.txt").read().split("\n") if os.path.exists(d + "/detached_args.txt") else None
        return p, out, args

    def test_a_bare_launch_is_pinned(self):
        p, out, args = self.launch()
        text = p.stdout + p.stderr
        self.assertEqual(p.returncode, 0, text)
        self.assertTrue(os.path.exists(os.path.join(out, "harness", "HARNESS_COMMIT")), text)
        dry = next((ln for ln in text.splitlines() if ln.startswith("DRY-RUN OK")), "")
        self.assertRegex(dry, r" harness=[0-9a-f]{12} ", text)
        self.assertIsNotNone(args, text)
        self.assertIn("--child", args)
        self.assertNotIn("--live", args)

    def test_live_is_the_explicit_opt_out(self):
        p, out, args = self.launch("--live")
        text = p.stdout + p.stderr
        self.assertEqual(p.returncode, 0, text)
        self.assertFalse(os.path.exists(os.path.join(out, "harness")), text)
        dry = next((ln for ln in text.splitlines() if ln.startswith("DRY-RUN OK")), "")
        self.assertIn("-live", dry, text)
        self.assertIn("--live", args)

    def test_the_header_says_so(self):
        with open(TEMPLATE) as f:
            head = f.read().split("set -u", 1)[0]
        self.assertIn("--live [out_dir]", head)
        self.assertIn("PINNED BY DEFAULT", head)


if __name__ == "__main__":
    unittest.main()
