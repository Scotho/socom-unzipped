"""Sprint 5 Task 5 (a) -- the run's true closest approach and freeze tolerance:

  * `Duel`'s paired 3-D range (PairedRange): the TRUE run minimum and its dy, and the CURRENT paired distance for the
    `near` gate -- launch 3c printed closest_3d=166.76 against a true 52.42 at dy 42 (KNOWN §4);
  * freezes: the round clock 0x4365c0 standing still while rows keep coming (launch 8c, research/21 §9.8) disarms
    the move-path watch -- replayed on launch 8c's own rows, where the live watch fired three 10-11 s "stalls" --
    and attributes the other side's starvation alarm to `freeze(side)` in the StarvationWatch, which asks the
    other side to move only when both round clocks are advancing.

unittest only; every loop runs in simulated time (no sleeps, no game).
"""
import math
import os
import re
import struct
import tempfile
import threading
import unittest

from tools_py.parity import online_login_ours as L
from tools_py.parity import online_match_ours as M
from tools_py.parity import sim_walk_to_b as S
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import ACTOR, NG, Clock, f2w, item, matrix_words, name_words, peek, tail, tok


# ---------------------------------------------------------------------------------------------
def freeze_rows(t0=500.0, run1=4.0, frozen=7.9, run2=4.0, period=0.25, clock0=80.0):
    """Launch 8c's shape (research/21 §9.8, A 506.1-514.1): the round clock 0x4365c0 advances with host
    time, then stands still for `frozen` s while the peek sampler keeps writing rows, then runs again."""
    rows, t, c = [], t0, clock0
    for _ in range(int(run1 / period)):
        rows.append((t, c))
        t += period
        c += period
    for _ in range(int(frozen / period)):
        rows.append((t, c))
        t += period
    for _ in range(int(run2 / period)):
        c += period
        rows.append((t, c))
        t += period
    return rows


# ---------------------------------------------------------------------------------------------
class PairedRangeTest(unittest.TestCase):
    """Launch 3c's shape: the pair came within 52.42 (dy 42) mid-run and ended ~166 apart."""

    def rows(self):
        a, b = [], []
        for i in range(40):
            t = 100.0 + 0.25 * i
            ax = 0.0
            bx = 200.0 - 6.0 * i if i <= 25 else 50.0 + 5.0 * (i - 25)
            a.append((t, ax, 100.0, 0.0, 1))
            b.append((t + 0.1, bx, 142.0, 0.0, 2))
        return a, b

    def test_true_run_minimum_and_dy_at_it(self):
        a, b = self.rows()
        pr = M.PairedRange()
        for k in range(5, 41, 5):                       # incremental, as the live loop feeds it
            pr.update(a[:k], b[:k])
        r = vc.score_contact(a, b, [], [], [], ([], []))
        self.assertAlmostEqual(pr.closest, r.closest_3d, places=6)
        self.assertAlmostEqual(pr.closest_dy, r.closest_dy, places=6)
        self.assertAlmostEqual(pr.closest, math.hypot(50.0, 42.0), places=6)

    def test_current_is_the_latest_pair_not_the_minimum(self):
        a, b = self.rows()
        pr = M.PairedRange()
        pr.update(a, b)
        self.assertAlmostEqual(pr.current[1], math.hypot(120.0, 42.0), delta=6.0)
        self.assertGreater(pr.current[1], pr.closest + 50.0)

    def test_duel_best_dist_is_the_run_minimum_and_near_uses_current(self):
        a, b = self.rows()

        class T:
            def __init__(self, rows):
                self.rows_ = rows

            def actor_ingame(self):
                return list(self.rows_)
        d = M.Duel()
        d.observe("A", T(a[:20]))
        d.observe("B", T(b[:20]))
        d.update_pairs()
        d.observe("A", T(a))
        d.observe("B", T(b))
        d.update_pairs()
        self.assertAlmostEqual(d.best_dist(), math.hypot(50.0, 42.0), places=6)
        self.assertAlmostEqual(d.best_dy(), 42.0, places=6)
        self.assertGreater(d.current_d3(now=a[-1][0]), 100.0)
        self.assertIsNone(d.current_d3(now=a[-1][0] + 60.0))    # stale pair -> no current distance

    def test_unpaired_rows_do_not_count(self):
        pr = M.PairedRange()
        pr.update([(0.0, 0, 0, 0, 1)], [(5.0, 1, 0, 0, 2)])
        self.assertIsNone(pr.closest)


class FreezeTest(unittest.TestCase):
    def test_launch8c_style_freeze_is_one_episode(self):
        rows = freeze_rows()
        eps = M.freeze_episodes(rows, now=rows[-1][0])
        self.assertEqual(len(eps), 1)
        t0, t1, ongoing = eps[0]
        self.assertAlmostEqual(t1 - t0, 7.9, delta=0.5)
        self.assertFalse(ongoing)
        self.assertFalse(M.frozen_now(rows, rows[-1][0]))

    def test_frozen_now_inside_the_freeze(self):
        rows = [r for r in freeze_rows() if r[0] <= 508.0]
        self.assertTrue(M.frozen_now(rows, 508.0))

    def test_a_short_stand_is_not_a_freeze(self):
        # spec §5.1.1 (Task 5 finish): a stall >= 1.0 s is a freeze; 0.75 s (three repeated rows) is not
        rows = freeze_rows(frozen=0.75)
        self.assertEqual(M.freeze_episodes(rows, now=rows[-1][0]), [])
        self.assertEqual(M.FREEZE_CLOCK_STILL_S, 1.0)

    def test_no_round_clock_rows_is_never_frozen(self):
        self.assertEqual(M.freeze_episodes([], now=10.0), [])
        self.assertFalse(M.frozen_now([], 10.0))

    def test_last_freeze_end(self):
        rows = freeze_rows()
        self.assertAlmostEqual(M.last_freeze_end(rows, rows[-1][0]), 504.0 + 7.75, delta=0.5)
        self.assertIsNone(M.last_freeze_end(freeze_rows(frozen=0.0), 520.0))


class FreezeMovePathTest(unittest.TestCase):
    ENV = {"PS2X_CALL_TRACE": "0x553dc0:MoveScale,0x30cd80:NetIdle", "PS2X_CALL_TRACE_EVERY": "10",
           "PS2X_PEEK": "*0x408c58:64,*0x408c58+0xF78:24,*0x437ce8+0x0c*:2,*0x437ce8+0x0c**:3,0x4365c0:1"}

    def setUp(self):
        self.c = Clock(0.0)
        self.tails = {g: tail(self.c, g) for g in "AB"}
        self.logged = []
        self.w = M.MovePathWatch(self.tails, self.logged.append, env=self.ENV, clock=self.c)
        self.n = 0
        self.rt = 10.0

    def feed(self, seconds, calls=True, clock_runs=True):
        end = self.c.t + seconds
        while self.c.t < end - 1e-9:
            self.c.t = round(self.c.t + 0.25, 6)
            if clock_runs:
                self.rt += 0.25
            for g in "AB":
                if calls or g == "B":
                    self.tails[g]._line(f"[call] {self.c.t:.1f}s MoveScale #{self.n} a0=0x1 ra=0x595028 f12=1.0")
                self.tails[g]._line(peek(round_time=self.rt if (g == "B" or clock_runs) else self.rt))
            self.n += 5

    def test_a_17s_freeze_disarms_instead_of_stalling(self):
        self.feed(5.0)
        self.feed(17.0, calls=False, clock_runs=False)
        v = self.w.check()
        self.assertEqual(v["A"].status, "disarmed", v["A"].detail)
        self.assertIn("freeze", v["A"].detail)
        self.assertIsNone(self.w.stalled)
        self.feed(0.5)                                  # the freeze ends, MoveScale resumes at once
        self.assertEqual(self.w.check()["A"].status, "ok")
        self.assertIsNone(self.w.stalled)

    def test_the_stall_clock_restarts_at_the_freeze_end(self):
        self.feed(5.0)
        self.feed(12.0, calls=False, clock_runs=False)
        self.feed(6.0, calls=False, clock_runs=True)    # clock runs again, move path still silent
        self.assertNotEqual(self.w.check()["A"].status, "stalled")
        self.feed(5.0, calls=False, clock_runs=True)    # 11 s of a running clock and no MoveScale
        self.assertEqual(self.w.check()["A"].status, "stalled")

    def test_negative_control_silent_move_path_with_a_running_clock_stalls(self):
        self.feed(5.0)
        self.feed(11.0, calls=False, clock_runs=True)
        self.assertEqual(self.w.check()["A"].status, "stalled")


# ---------------------------------------------------------------------------------------------
class StarvationWatchTest(unittest.TestCase):
    def setUp(self):
        self.c = Clock(0.0)
        self.tails = {g: tail(self.c, g) for g in "AB"}
        self.lines = []
        self.w = M.StarvationWatch(self.tails, self.lines.append, clock=self.c)
        self.n = {"A": 0, "B": 0}
        self.rt = {"A": 10.0, "B": 10.0}
        self.idle = {"A": 300, "B": 300}

    def step(self, seconds, frozen=(), idle=None, netidle=True):
        idle = idle or {}
        end = self.c.t + seconds
        while self.c.t < end - 1e-9:
            self.c.t = round(self.c.t + 0.25, 6)
            for g in "AB":
                v = idle.get(g, self.idle[g])
                if g not in frozen:
                    self.rt[g] += 0.25
                    if netidle and self.n[g] % 2 == 0:
                        self.tails[g]._line(f"[call] {self.c.t:.1f}s NetIdle #{self.n[g]} a0=0x45a0c0 f12=0.0")
                        self.tails[g]._line(f"[ret] NetIdle #{self.n[g]} v0=0x{v:x} f0=0.6")
                    self.n[g] += 1
                self.tails[g]._line(peek(round_time=self.rt[g], lag=1 if v >= 4501 else 0))
            self.w.check()

    def test_healthy_pair_is_ok_with_no_alarm(self):
        self.step(10.0)
        self.assertEqual(self.w.starvation_alarms(), 0)
        self.assertIsNone(self.w.stop_reason)
        self.assertEqual(self.w.max_idle_ms(), {"A": 300, "B": 300})
        self.assertGreater(self.w.lag_rows_read()["A"], 0)

    def test_victim_alarm_asks_the_other_side_to_move_and_clears(self):
        self.step(4.0)
        self.step(1.0, idle={"B": 4200})
        self.assertEqual(self.w.starvation_alarms(), 1)
        self.assertTrue(self.w.take_request("A"))
        self.assertFalse(self.w.take_request("A"))       # consumed
        self.assertFalse(self.w.take_request("B"))
        self.w.moved("A", self.c.t)
        self.step(1.5)
        self.assertEqual(self.w.alarms_cleared(), 1)
        self.assertIsNone(self.w.stop_reason)
        self.assertTrue(any("STARVATION" in m and "side=B" in m for m in self.lines), self.lines)

    def test_an_alarm_that_cleared_on_its_own_leaves_no_stale_request(self):
        # sim endgame run 1: an approach-phase alarm cleared by the approach's own walk left A's request set, and A
        # later "suspended firing and strafed" for nothing at the start of the fight
        self.step(4.0)
        self.step(1.0, idle={"B": 4200})
        self.step(1.0)
        self.assertEqual(self.w.alarms_cleared(), 1)
        self.assertFalse(self.w.take_request("A"))

    def test_alarm_not_cleared_within_3s_of_the_move_stops(self):
        self.step(4.0)
        self.step(1.0, idle={"B": 4200})
        self.w.moved("A", self.c.t)
        self.step(3.5, idle={"B": 4700})
        self.assertIn("not cleared", self.w.stop_reason or "")

    def test_alarm_caused_by_the_other_instances_freeze_is_freeze_not_starvation(self):
        self.step(4.0)
        self.step(3.0, frozen=("A",))                    # A's guest stalls; B's idle climbs behind it
        self.step(3.0, frozen=("A",), idle={"B": 4600})
        self.assertEqual(self.w.starvation_alarms(), 0)
        self.assertEqual(self.w.freeze_alarms(), {"A": 1})
        self.assertFalse(self.w.take_request("A"))
        self.assertTrue(any("freeze(A)" in m for m in self.lines), self.lines)
        self.assertIsNone(self.w.stop_reason)            # A's own silent NetIdle is its freeze too

    def test_no_netidle_rows_is_no_data_and_stops(self):
        self.step(M.STARVATION_GRACE_S + M.STARVATION_NODATA_S + 1.0, netidle=False)
        self.assertIn("NO-DATA", self.w.stop_reason or "")

    def test_a_freeze_longer_than_the_cap_is_no_longer_tolerated(self):
        self.step(4.0)
        self.step(M.FREEZE_MAX_S + 4.0, frozen=("A",))
        self.assertIn("NO-DATA", self.w.stop_reason or "")

    def test_lag_flag_alone_is_the_primary_alarm(self):
        self.step(4.0)
        # NetIdle below the 4000 ms alarm but ng+0xde set (primary signal)
        end = self.c.t + 1.0
        while self.c.t < end:
            self.c.t = round(self.c.t + 0.25, 6)
            for g in "AB":
                self.rt[g] += 0.25
                self.tails[g]._line(f"[call] {self.c.t:.1f}s NetIdle #{self.n[g]} a0=0x45a0c0 f12=0.0")
                self.tails[g]._line(f"[ret] NetIdle #{self.n[g]} v0=0x100 f0=0.6")
                self.n[g] += 1
                self.tails[g]._line(peek(round_time=self.rt[g], lag=1 if g == "A" else 0))
            self.w.check()
        self.assertEqual(self.w.starvation_alarms(), 1)
        self.assertEqual(self.w.alarms[0]["signal"], "ng+0xde")
        self.assertTrue(self.w.take_request("B"))


FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "online")


class Launch8cFreezeReplayTest(unittest.TestCase):
    """Launch 8c's own rows (fixtures/online/launch8c_*_freeze*.txt, cut by make_fixtures.py): the LIVE move-path
    watch fired `stalled` three times there (A 10.7 s after #1370, A 10.9 s after #1860, B 10.2 s after #2870) on
    guest freezes -- the round clock 0x4365c0 stood still while the sampler kept writing rows. Replayed on the
    log's own clock, every one must read as a freeze (disarmed), never as a stall."""

    ENV = {"PS2X_CALL_TRACE": "0x553dc0:MoveScale,0x30cd80:NetIdle", "PS2X_CALL_TRACE_EVERY": "10",
           "PS2X_PEEK": "*0x408c58:64,*0x408c58+0xF78:24,*0x437ce8+0x0c*:2,*0x437ce8+0x0c**:3,0x4365c0:1"}

    def replay(self, name):
        with open(os.path.join(FIXTURES, name)) as f:
            lines = f.read().split(chr(10))
        p = vc.parse_log(lines)
        peek_t = iter([t for t, _ in p.peek_rows])
        clock = Clock(p.peek_rows[0][0] - 0.01)
        tl = tail(clock, name)
        logged = []
        watch = M.MovePathWatch({"X": tl}, logged.append, env=self.ENV, clock=clock)
        statuses = []
        for line in lines:
            if line.startswith("[peek]"):
                clock.t = next(peek_t)
                tl._line(line)
                statuses.append(watch.check()["X"])
            elif line.startswith("[call]"):
                m = vc._CALL.match(line)
                clock.t = max(clock.t, float(m.group(1))) if m else clock.t
                tl._line(line)
            elif line.startswith("[ret]"):
                tl._line(line)
        return watch, statuses, logged

    def check_freeze(self, name):
        watch, statuses, logged = self.replay(name)
        self.assertIsNone(watch.stalled, logged)
        self.assertTrue(any(v.status == "disarmed" and "freeze" in v.detail for v in statuses), logged)
        self.assertEqual(statuses[-1].status, "ok", logged)          # the move path resumed after the freeze

    def test_a_after_1370(self):
        self.check_freeze("launch8c_A_freeze1.txt")

    def test_a_after_1860(self):
        self.check_freeze("launch8c_A_freeze2.txt")

    def test_b_after_2870(self):
        self.check_freeze("launch8c_B_freeze.txt")

    def test_the_fixture_is_a_real_stall_without_the_freeze_rule(self):
        # the negative control: the same rows, the round clock item removed -> the watch stalls, as it did live
        with open(os.path.join(FIXTURES, "launch8c_A_freeze1.txt")) as f:
            lines = [re.sub(r" @4365c0: [0-9a-f]{8}\([^)]*\)", "", l) for l in f.read().split(chr(10))]
        p = vc.parse_log(lines)
        peek_t = iter([t for t, _ in p.peek_rows])
        clock = Clock(p.peek_rows[0][0] - 0.01)
        tl = tail(clock, "neg")
        watch = M.MovePathWatch({"X": tl}, lambda m: None, env=self.ENV, clock=clock)
        for line in lines:
            if line.startswith("[peek]"):
                clock.t = next(peek_t)
                tl._line(line)
                watch.check()
            elif line.startswith("[call]") or line.startswith("[ret]"):
                tl._line(line)
        self.assertIsNotNone(watch.stalled)


class StarvationReactionConditionTest(unittest.TestCase):
    """The other side is asked to move only when one side is starved AND both round clocks are advancing
    (the owner-requested review: launch 3c stood ~48 s both still at f12 = 1.0; every recorded alarm was a freeze
    or a stuck mover)."""

    def run_case(self, with_round_clock):
        c = Clock(0.0)
        tails = {g: tail(c, g) for g in "AB"}
        lines = []
        w = M.StarvationWatch(tails, lines.append, clock=c)
        rt, n = 10.0, 0
        for k in range(24):
            c.t = round(c.t + 0.25, 6)
            rt += 0.25
            idle = {"A": 300, "B": 4300 if k >= 16 else 300}
            for g in "AB":
                tails[g]._line(f"[call] {c.t:.1f}s NetIdle #{n} a0=0x45a0c0 f12=0.0")
                tails[g]._line(f"[ret] NetIdle #{n} v0=0x{idle[g]:x} f0=0.6")
                tails[g]._line(peek(round_time=rt if with_round_clock else None, lag=0))
            n += 1
            w.check()
        return w, lines

    def test_both_clocks_advancing_asks_the_other_side(self):
        w, lines = self.run_case(True)
        self.assertEqual(w.starvation_alarms(), 1)
        self.assertTrue(w.take_request("A"))

    def test_a_scale_below_0_99_alone_is_an_alarm(self):
        # Amendment A: the reaction also fires on a side's MoveScale f12 < 0.99 (with both round clocks running)
        c = Clock(0.0)
        tails = {g: tail(c, g) for g in "AB"}
        w = M.StarvationWatch(tails, lambda m: None, clock=c)
        rt, n = 10.0, 0
        for k in range(24):
            c.t = round(c.t + 0.25, 6)
            rt += 0.25
            for g in "AB":
                f12 = 0.6 if (g == "B" and k >= 16) else 1.0
                tails[g]._line(f"[call] {c.t:.1f}s MoveScale #{n} a0=0x1 ra=0x595028 f12={f12}")
                tails[g]._line(f"[call] {c.t:.1f}s NetIdle #{n} a0=0x45a0c0 f12=0.0")
                tails[g]._line(f"[ret] NetIdle #{n} v0=0x100 f0=0.6")
                tails[g]._line(peek(round_time=rt, lag=0))
            n += 1
            w.check()
        self.assertEqual(w.starvation_alarms(), 1)
        self.assertEqual(w.alarms[0]["signal"], "f12")
        self.assertTrue(w.take_request("A"))

    def test_unconfirmed_clocks_count_the_alarm_but_ask_nobody(self):
        w, lines = self.run_case(False)
        self.assertEqual(w.starvation_alarms(), 1)
        self.assertFalse(w.take_request("A"))
        self.assertTrue(any("not both advancing" in m for m in lines), lines)


if __name__ == "__main__":
    unittest.main()
