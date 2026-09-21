"""Sprint 5 Task 5 finish, slice (vi) -- Amendment A4's rung 0 in round 1 and the launch integration (A5):

  * rung 0: MoveScale >= 17 calls/s over a 60 s window with both round clocks running, the clock string at >= 0.95 of
    real time, back-pressure waits not in the hundreds (parsed from `[gs-gl stats] backpressure ... waits=` into
    `bp_waits=<A,B>` on the LADDER line); a failure is recorded as `RUNG0 FAIL <reason>` (R68, never fatal);
  * the rung-0 rx pulse table (+-64/+-80/+-96, 0.3 s each at spawn, degrees per pulse; reported, not a gate);
  * RESULT lines carry `harness=<commit> exe=<sha256 prefix>`, read from a pinned snapshot's HARNESS_COMMIT /
    EXE_BUILD when present;
  * `--dry-run` validates the arguments, the route file and the peek spec without a game, and the launch template
    scripts/parity/ladder_frostfire.sh passes it.

unittest only; no game.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools_py.parity import online_ladder as LD
from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import Clock, peek, tail
from tools_py.tests.test_aim_pad import AimShell, AimWorld
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(ROOT, "scripts", "parity", "ladder_frostfire.sh")


def side_rows(rate=19.0, t0=0.0, t1=90.0, clock_rate=1.0, waits_per_s=0):
    calls = [(t0 + k * 0.5, int(k * 0.5 * rate)) for k in range(int((t1 - t0) * 2) + 1)]
    clock = [(t0 + k * 0.25, "%02d:%02d" % divmod(359 - int(k * 0.25 * clock_rate), 60)) for k in range(int((t1 - t0) * 4))]
    bp = [(t0 + k * 1.0, waits_per_s, 0.0, 0) for k in range(int(t1 - t0))]
    return {"calls": calls, "clock": clock, "bp": bp}


class Rung0VerdictTest(unittest.TestCase):
    def test_a_healthy_pair_passes(self):
        ok, reason, f = LD.rung0_verdict({"A": side_rows(), "B": side_rows(rate=17.5)}, [], 0.0, 90.0)
        self.assertTrue(ok, reason)
        self.assertAlmostEqual(f["movescale_B"], 17.5, delta=0.3)
        self.assertEqual(f["bp_waits_A"], 0)

    def test_movescale_under_17_fails(self):
        ok, reason, _ = LD.rung0_verdict({"A": side_rows(), "B": side_rows(rate=11.5)}, [], 0.0, 90.0)
        self.assertFalse(ok)
        self.assertIn("MoveScale B", reason)

    def test_a_slow_clock_string_fails(self):
        ok, reason, _ = LD.rung0_verdict({"A": side_rows(clock_rate=0.8), "B": side_rows()}, [], 0.0, 90.0)
        self.assertFalse(ok)
        self.assertIn("clock string A", reason)

    def test_back_pressure_in_the_hundreds_fails_and_no_stats_is_no_data(self):
        ok, reason, _ = LD.rung0_verdict({"A": side_rows(waits_per_s=2), "B": side_rows()}, [], 0.0, 90.0)
        self.assertFalse(ok)
        self.assertIn("back-pressure waits A", reason)
        b = side_rows()
        b["bp"] = []
        ok, reason, f = LD.rung0_verdict({"A": side_rows(), "B": b}, [], 0.0, 90.0)
        self.assertIn("[gs-gl stats] B no rows at all", reason)
        self.assertEqual(f["status"], vc.NO_DATA)                   # R68: a missing instrument, not a failed bar

    def test_the_window_must_avoid_pauses(self):
        pauses = [(20.0, 25.0, False, "freeze")]
        self.assertEqual(LD.clean_window(pauses, 0.0, 90.0), (25.0, 85.0))
        ok, reason, _ = LD.rung0_verdict({"A": side_rows(), "B": side_rows()}, pauses + [(70.0, 72.0, False, "freeze")],
                                         0.0, 90.0)
        self.assertFalse(ok)
        self.assertIn("no 60 s window", reason)


class BackPressureRowsTest(unittest.TestCase):
    def test_the_tail_parses_gs_stats_and_cap_hits(self):
        c = Clock(10.0)
        t = tail(c)
        t._line("[gs-gl stats] backpressure N=3 guest_frames=64 waits=7 wait_ms=37.5 timeouts=1 skipped=0 unlatched=0 pending=1")
        t._line("[gs-gl] back-pressure: replay made no progress within 2000 ms (N=3, 3 frames pending, 1 cap hits); the EE runs on until it does")
        self.assertEqual(t.bp_rows, [(10.0, 7, 37.5, 1)])
        self.assertEqual(t.bp_caps, [10.0])

    def test_the_ladder_line_carries_bp_waits(self):
        line = M.ladder_line(rung=1, controllable=("yes", "yes"), contact_rows=0, rows_read=10, damage="no", kill="no",
                             starvation_alarms=0, alarms_cleared=0, max_idle_ms=(1, 2), lagflag_rows=(3, 4),
                             bp_waits=(12, None), round_n=2)
        self.assertTrue(line.startswith("LADDER round=2 rung=1 "), line)
        self.assertIn(" bp_waits=12,NO-DATA", line)


class PulseTableTest(unittest.TestCase):
    def test_six_pulses_with_degrees_each(self):
        c = Clock()
        w = AimWorld(c, facing=0.0, gain=0.7, dz=56, lag=False)
        c.wait(1.0)
        sh = AimShell(w)
        me = M.Side("A", sh, w.tail)
        table = M.rx_pulse_table(me, clock=c, wait=c.wait)
        self.assertEqual([r["dev"] for r in table], list(LD.RUNG0_PULSE_TABLE))
        self.assertTrue(all(abs(p[3] - LD.RUNG0_PULSE_S) < 1e-9 for p in sh.pads if p[2].get("rx", 0x80) != 0x80))
        self.assertTrue(all(r["deg"] is not None for r in table), table)
        self.assertTrue(any(m.startswith("RUNG0 rx-table A rx=+64") for m in sh.lines), sh.lines)


class HarnessIdentityTest(unittest.TestCase):
    def test_a_pinned_snapshot_is_read(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, "HARNESS_COMMIT"), "w") as f:
            f.write("0123456789abcdef0123456789abcdef01234567\n")
        with open(os.path.join(d, "EXE_BUILD"), "w") as f:
            f.write("path=C:/x/dist/socom2.exe mtime=2026-09-13T00:00:00Z sha256=234b4772cd0a8bf8ffffffffffffffff\n")
        self.assertEqual(M.harness_identity(d), ("0123456789ab", "234b4772cd0a8bf8"))
        self.assertIn("harness=0123456789ab exe=234b4772cd0a8bf8", M.identity_tokens(d))

    def test_the_live_tree_says_so(self):
        commit, exe = M.harness_identity(tempfile.gettempdir())
        self.assertTrue(commit.endswith("-live") or commit == vc.NO_DATA, commit)




class DryRunTest(unittest.TestCase):
    def run_main(self, args, env_extra=None, env_drop=()):
        env = dict(os.environ)
        for k in env_drop:
            env.pop(k, None)
        env.update(env_extra or {})
        return subprocess.run([sys.executable, "-m", "tools_py.parity.online_match_ours", "--dry-run"] + args,
                              capture_output=True, text=True, cwd=ROOT, env=env, timeout=120)

    GOOD = {"PS2X_CALL_TRACE": "0x553dc0:MoveScale,0x30cd80:NetIdle", "PS2X_CALL_TRACE_EVERY": "10",
            "PS2X_GS_STATS": "1",
            "PS2X_PEEK": "0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,"
                         "*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,*0x437ce8+0x0c*:2,"
                         "*0x437ce8+0x10*:2,*0x437ce8+0x14*:2,*0x437ce8+0x20*:2,*0x437ce8+0x24*:2,*0x437ce8+0x2c*:2,"
                         "*0x437ce8+0x58*:2,*0x437ce8+0x5c*:2,*0x437ce8+0x70*:2,*0x43668c:2,0x4365c0:1,0x45a0c0:1,"
                         "0x3df1b0:1,0x45a1c8:1,*0x437ce8+0x0c**:3,*0x437ce8+0x10**:3,*0x437ce8+0x14**:3,"
                         "*0x437ce8+0x20**:3,*0x437ce8+0x24**:3,*0x437ce8+0x2c**:3,*0x437ce8+0x58**:3,"
                         "*0x437ce8+0x5c**:3,*0x437ce8+0x70**:3,*0x43668c*:3,0x408f10:2,0x408c58:4"}

    def test_a_good_environment_passes(self):
        p = self.run_main(["--until-kill", "--map", "frostfire"], env_extra=self.GOOD)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("DRY-RUN OK", p.stdout)
        self.assertIn("frostfire_v2.json", p.stdout)

    def test_a_bad_route_file_and_a_missing_clock_are_refused(self):
        env = dict(self.GOOD, PS2X_PEEK=self.GOOD["PS2X_PEEK"].replace("0x4365c0:1,", ""))
        p = self.run_main(["--until-kill", "--route", "tools_py/parity/routes/no_such.json"], env_extra=env)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("DRY-RUN REFUSED", p.stdout)
        self.assertIn("no_such.json", p.stdout)
        self.assertIn("0x4365c0", p.stdout)

    def test_no_gs_stats_is_refused(self):
        p = self.run_main(["--until-kill"], env_extra=self.GOOD, env_drop=("PS2X_GS_STATS",))
        env = dict(self.GOOD)
        env.pop("PS2X_GS_STATS")
        p = subprocess.run([sys.executable, "-m", "tools_py.parity.online_match_ours", "--dry-run", "--until-kill"],
                           capture_output=True, text=True, cwd=ROOT,
                           env={k: v for k, v in dict(os.environ, **env).items() if k != "PS2X_GS_STATS"}, timeout=120)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("PS2X_GS_STATS", p.stdout)

    @unittest.skipUnless(BASH, "bash not found")
    def test_the_launch_template_passes_its_own_dry_run(self):
        self.assertTrue(os.path.exists(TEMPLATE))
        with open(TEMPLATE) as f:
            text = f.read()
        with open(os.path.join(os.path.dirname(TEMPLATE), "env.sh")) as f:
            text += f.read()                          # the shared instruments the template sources
        for need in ("pin_harness.sh", "PYTHONSAFEPATH=1", "run_detached.sh", "--purpose launch-ladder",
                     "PS2X_GS_STATS=1", "0x4365c0:1", "--route", "env.sh"):
            self.assertIn(need, text)
        p = subprocess.run([BASH, TEMPLATE, "--dry-run"], capture_output=True, text=True, cwd=ROOT, timeout=180)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("DRY-RUN OK", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
