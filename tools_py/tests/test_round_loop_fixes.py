"""Sprint 5 Task 5 fix round, slice 1 -- the round loop (review of finish (iv)-(vi)):

  * C1: wait_next_round waits for the clock RESTART past the frozen boundary value (running >= 1 s after it) and both
    sides at their spawns -- replayed on launch 8c's round-1 -> round-2 transition (it returned at 783.5 s, before the
    788.9 restart);
  * C2: after the engagement returns, the round end is waited for (KillWatch: 00:00 / the step / a kill) by the clock
    string's remaining time + 20 s, so an engagement ending 90 s before 00:00 still starts round 2;
  * I1: KillWatch.rearm filters on the ROW's time, not the poll's;
  * I2 (R68): a rung-0 failure is recorded and the rounds continue; a missing instrument is RESULT RUNG0-NO-DATA;
  * R47: a lobby failure (exit 4) is a launch summary with zero rounds, never a round;
  * minor: an unread mp_round_count at round start is NO-DATA at once, not a 45 s hang.

unittest only; simulated time.
"""
import json
import math
import os
import shutil
import tempfile
import unittest

from tools_py.parity import online_ladder as LD
from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import Clock, peek, tail

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "online", "launch8c_round_transition.txt")
SPAWNS_8C = {"A": (539.76, 159.53, 1456.11), "B": (1129.76, 65.05, 96.11)}


class Replay:
    """Feeds launch8c_round_transition.txt into two RunLogTails on one simulated host clock."""

    def __init__(self):
        self.events = []
        with open(FIXTURE) as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                side, t, rest = line.rstrip("\n").split(" ", 2)
                self.events.append((float(t), side, rest))
        self.t = self.events[0][0]
        self.tails = {g: M.RunLogTail("no_such.log", clock=self) for g in "AB"}
        self.i = 0

    def __call__(self):
        return self.t

    def feed_to(self, t):
        while self.i < len(self.events) and self.events[self.i][0] <= t:
            te, side, line = self.events[self.i]
            self.t = te
            self.tails[side]._line(line)
            self.i += 1
        self.t = t

    def wait(self, s):
        self.feed_to(self.t + s)


class NextRoundReplay8cTest(unittest.TestCase):
    def test_8c_next_round_waits_for_the_restart_and_the_reset(self):
        r = Replay()
        r.feed_to(779.0)
        info = {}
        ok, reason, actors = LD.wait_next_round(r.tails, 0, clock=r, wait=r.wait, spawns=SPAWNS_8C, info=info)
        self.assertTrue(ok, reason)
        self.assertGreaterEqual(r.t, 789.25)
        for g in "AB":
            self.assertAlmostEqual(info[g]["step"], 783.3, delta=0.3)
            self.assertAlmostEqual(info[g]["restart"], 789.1, delta=0.3)
            a = r.tails[g].actor_latest()
            self.assertLessEqual(math.hypot(a[1] - SPAWNS_8C[g][0], a[3] - SPAWNS_8C[g][2]), LD.NEXT_ROUND_SPAWN_UNITS)
        self.assertEqual(actors, {"A": 0x17941D0, "B": 0x17935C0})

    def test_without_spawns_nobody_is_at_spawn(self):
        r = Replay()
        r.feed_to(779.0)
        ok, reason, _ = LD.wait_next_round(r.tails, 0, clock=r, wait=r.wait, timeout=15.0)
        self.assertFalse(ok)
        self.assertIn("no-spawn", reason)

    def test_an_unread_round_count_is_no_data_at_once(self):
        r = Replay()
        r.feed_to(779.0)
        ok, reason, _ = LD.wait_next_round(r.tails, None, clock=r, wait=r.wait, spawns=SPAWNS_8C)
        self.assertFalse(ok)
        self.assertIn(vc.NO_DATA, reason)
        self.assertAlmostEqual(r.t, 779.0)


class World:
    """Two tails, a counting-down clock string, 0x4365c0, mp_round_count and actor rows, 4 Hz. At `end_s` the string
    reads 00:00; the step follows STEP_AFTER s later; the guest clock stands FREEZE_S; the players reset to their spawns
    at the restart."""
    STEP_AFTER, FREEZE_S = 5.4, 5.5

    def __init__(self, c, remaining_s, spawns=((0.0, 50.0, 0.0), (400.0, 50.0, 400.0)), away=(200.0, 50.0, 200.0)):
        self.c, self.t0, self.remaining = c, c.t, remaining_s
        self.tails = {g: tail(c, g) for g in "AB"}
        self.spawns = dict(zip("AB", spawns))
        self.away = away
        self.rt = 100.0
        c.hooks.append(self.tick)

    def tick(self, t):
        e = t - self.t0
        t_zero = self.remaining
        t_step, t_restart = t_zero + self.STEP_AFTER, t_zero + self.STEP_AFTER + self.FREEZE_S
        rc = 1 if e >= t_step else 0
        if not (t_step <= e < t_restart):
            self.rt += 0.15
        left = max(0, int(math.ceil(self.remaining - e))) if e < t_restart else 360 - int(e - t_restart)
        s = f"{left // 60:02d}:{left % 60:02d}"
        for g, tl in self.tails.items():
            x, y, z = self.spawns[g] if e >= t_restart else (self.away if g == "A" else self.spawns[g])
            tl._line(peek(x=x, y=y, z=z, clock=s, round_time=self.rt, round_count=rc))


class RoundEndThenNextRoundTest(unittest.TestCase):
    def test_an_engagement_ending_90_s_before_00_00_still_starts_round_2(self):
        c = Clock(1000.0)
        w = World(c, remaining_s=90.0)
        c.wait(1.0)
        kw = M.KillWatch(w.tails, {}, server_log="no_such.log", clock=c)
        c.hooks.append(lambda t: kw._check_round())
        played, lines = [], []

        def play(n, mover):
            played.append(n)
            kw.rearm()
            t_round = c.t
            fired = lambda: kw.fired if kw.fired and kw.fired["t"] >= t_round - 1.0 else None
            ev, why = LD.wait_round_end(w.tails, fired, clock=c, wait=c.wait)   # the engagement returned at once
            return LD.RoundScore(n=n, mover=mover, rung=1, verdict="FAIL no kill", line=f"LADDER round={n} {why}",
                                 fields={"ev": ev})

        spawns = {g: w.spawns[g] for g in "AB"}
        hist, stop = LD.run_ladder(2, play, lambda n: LD.wait_next_round(w.tails, 0, clock=c, wait=c.wait,
                                                                         spawns=spawns)[:2], lines.append)
        self.assertEqual(played, [1, 2], lines)
        self.assertIsNone(stop, lines)
        self.assertEqual(hist[0].fields["ev"]["kind"], "round")

    def test_the_round_end_wait_ends_by_the_remaining_time_plus_the_slack(self):
        c = Clock(0.0)
        w = World(c, remaining_s=10.0)
        w.STEP_AFTER = 1e9                                   # the round never steps and nothing fires
        c.wait(1.0)
        ev, why = LD.wait_round_end(w.tails, lambda: None, clock=c, wait=c.wait)
        self.assertIsNone(ev)
        self.assertIn("remaining time", why)
        self.assertAlmostEqual(c.t, 10.0 + LD.ROUND_END_SLACK_S, delta=1.5)

    def test_a_stop_reason_ends_the_wait(self):
        c = Clock(0.0)
        w = World(c, remaining_s=100.0)
        c.wait(1.0)
        ev, why = LD.wait_round_end(w.tails, lambda: None, clock=c, wait=c.wait,
                                    stop=lambda: "move path stalled" if c.t > 5.0 else None)
        self.assertEqual(why, "move path stalled")
        self.assertLess(c.t, 6.0)


class KillWatchRearmRaceTest(unittest.TestCase):
    def test_a_step_row_older_than_the_rearm_never_fires_the_new_round(self):
        c = Clock(0.0)
        t = tail(c, "A")
        kw = M.KillWatch({"A": t}, {}, server_log="no_such.log", clock=c)
        for k in range(4):
            c.t += 0.25
            t._line(peek(round_count=0, clock="01:00"))
        kw._check_round()
        c.t += 0.25
        t._line(peek(round_count=1, clock="01:00"))       # the step row arrives ...
        c.t += 5.0                                         # ... wait_next_round sees it; the next round starts ...
        kw.rearm()
        kw._check_round()                                  # ... and only now does KillWatch poll the step row
        self.assertIsNone(kw.fired)
        c.t += 0.25
        t._line(peek(round_count=2, clock="01:00"))       # a step in the new round fires it
        kw._check_round()
        self.assertEqual(kw.fired["detail"]["to"], 2)


class Rung0RecordedTest(unittest.TestCase):
    def side(self, calls=True, bp=True, rate=19.0):
        return {"calls": [(k * 0.5, int(k * 0.5 * rate)) for k in range(181)] if calls else [],
                "clock": [(k * 0.25, "%02d:%02d" % divmod(359 - int(k * 0.25), 60)) for k in range(360)],
                "bp": [(float(k), 0, 0.0, 0) for k in range(90)] if bp else []}

    def test_a_failed_bar_is_fail_and_a_missing_instrument_is_no_data(self):
        ok, why, f = LD.rung0_verdict({"A": self.side(), "B": self.side(rate=11.0)}, [], 0.0, 90.0)
        self.assertEqual(f["status"], "FAIL")
        tok, lines = LD.rung0_report(ok, why, f, "harness=x exe=y")
        self.assertTrue(tok.startswith("FAIL MoveScale B"), tok)
        self.assertTrue(any(ln.startswith("RUNG0 FAIL MoveScale B") for ln in lines), lines)
        self.assertFalse(any(ln.startswith("RESULT") for ln in lines), lines)
        ok, why, f = LD.rung0_verdict({"A": self.side(bp=False), "B": self.side(calls=False)}, [], 0.0, 90.0)
        self.assertEqual(f["status"], vc.NO_DATA)
        tok, lines = LD.rung0_report(ok, why, f, "harness=x exe=y")
        self.assertTrue(tok.startswith("NO-DATA"), tok)
        self.assertTrue(any(ln.startswith("RESULT RUNG0-NO-DATA") and "harness=x" in ln for ln in lines), lines)
        ok, why, f = LD.rung0_verdict({"A": self.side(), "B": self.side()}, [], 0.0, 90.0)
        self.assertEqual(LD.rung0_report(ok, why, f), ("PASS", []))

    def test_the_rounds_continue_and_the_summary_and_round_1_say_so(self):
        for tok in ("FAIL MoveScale B 11.0/s < 17", "NO-DATA [gs-gl stats] A no rows at all"):
            lines, played = [], []

            def play(n, mover, tok=tok):
                played.append(n)
                line = M.ladder_line(rung=2, controllable=("yes", "yes"), contact_rows=40, rows_read=9, damage="no",
                                     kill="no", starvation_alarms=0, alarms_cleared=0, max_idle_ms=(1, 2),
                                     lagflag_rows=(0, 0), round_n=n, mover=mover, rung0=tok if n == 1 else None)
                return LD.RoundScore(n=n, mover=mover, rung=1, verdict="FAIL no kill", line=line,
                                     rung0=tok if n == 1 else None)
            hist, stop = LD.run_ladder(2, play, lambda n: (True, ""), lines.append)
            self.assertEqual(played, [1, 2])
            self.assertTrue(lines[0].endswith(f" RUNG0 {tok}"), lines[0])
            self.assertTrue(lines[-1].startswith("LADDER-SUMMARY rounds=2/2"), lines[-1])
            self.assertTrue(lines[-1].endswith(f" RUNG0 {tok}"), lines[-1])


class LobbyFailTest(unittest.TestCase):
    def test_a_lobby_failure_is_a_launch_summary_with_no_rounds(self):
        from tools_py.parity import online_login_ours as L
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        lines = []
        cls = M.record_lobby_fail(d, 4, L.LobbyFail("ready-dropped", "READY never registered"), lines.append,
                                  "harness=x exe=y")
        self.assertEqual(cls, "ready-dropped")
        self.assertEqual(lines, ["LADDER-SUMMARY rounds=0/4 usable=0 best_rung=0 kills=0 rungs=- movers=- "
                                 "stop=LOBBY-FAIL ready-dropped harness=x exe=y"])
        with open(os.path.join(d, "converge.json")) as f:
            j = json.load(f)
        self.assertEqual((j["lobby_fail"], j["rounds"], j["usable_rounds"]), ("ready-dropped", [], 0))


class NoDataRungTest(unittest.TestCase):
    def test_a_no_data_rung_is_not_usable_and_the_summary_reads_its_best_numeric_rung(self):
        s = LD.RoundScore(n=1, mover="A", rung=vc.NO_DATA, verdict="FAIL no kill")
        self.assertFalse(s.usable)
        lines = []
        LD.run_ladder(1, lambda n, m: s, lambda n: (True, ""), lines.append)
        self.assertIn("best_rung=0 kills=0 rungs=NO-DATA", lines[-1])


if __name__ == "__main__":
    unittest.main()
