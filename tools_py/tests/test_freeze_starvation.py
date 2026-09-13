"""Sprint 5 Task 5 finish, slice (i) -- the slice-(a) review findings on freezes and starvation, and spec §5.1.1's
freeze definition in the harness:

  * `verdict_core.clock_pauses`: a stall of the guest clock 0x4365c0 >= 1.0 s after merging stalls separated by one
    advancing row, or a window whose clock advance is < 25 % of its host span, is a FREEZE; the ~5.6 s pause from an
    mp_round_count step to the clock restart is a ROUND boundary, not a freeze;
  * StarvationWatch (I1): no NO-DATA stop at the end of a freeze -- launch 8c's own two-sided rows replayed, no stop;
  * MovePathWatch (I2): a freeze longer than FREEZE_MAX_S is NO-DATA, not an endless disarm;
  * attribution (I3): an alarm is the other side's freeze only when [t - idle, t] overlaps it (4501 ms for ng+0xde);
  * R24 (I4): a starved precondition hold says freeze(<peer>) when the peer's clock stood still;
  * a missing 0x4365c0 is logged once.

unittest only; simulated time.
"""
import os
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import Clock, peek, tail

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "online")


def clock_rows(spec, t0=100.0, period=0.25, v0=10.0, rate=0.6):
    """spec: [(seconds, 'run' | 'still' | ('creep', rate))] -> [(t, clock)] at 4 Hz."""
    rows, t, v = [], t0, v0
    for secs, kind in spec:
        for _ in range(int(round(secs / period))):
            if kind == "run":
                v += rate * period
            elif isinstance(kind, tuple):
                v += kind[1] * period
            rows.append((round(t, 6), round(v, 6)))
            t += period
    return rows


class ClockPausesTest(unittest.TestCase):
    def test_a_one_second_stall_is_a_freeze_and_three_quarters_is_not(self):
        p = vc.clock_pauses(clock_rows([(5, "run"), (1.25, "still"), (5, "run")]))
        self.assertEqual([k for *_, k in p], ["freeze"])
        self.assertEqual(vc.clock_pauses(clock_rows([(5, "run"), (0.75, "still"), (5, "run")])), [])

    def test_stalls_around_one_advancing_row_merge(self):
        rows = clock_rows([(4, "run"), (5, "still"), (0.25, "run"), (8, "still"), (4, "run")])
        p = vc.clock_pauses(rows)
        self.assertEqual(len(p), 1, p)
        self.assertAlmostEqual(p[0][1] - p[0][0], 13.25, delta=0.3)

    def test_the_real_8c_row_values_are_one_freeze(self):
        # launch 8c A: 54.402 still 500.71-505.63, ONE row at 55.487 (505.88), 55.587 still 506.13-514.07
        vals = ([53.436, 53.586, 53.736, 53.886, 54.052, 54.252] + [54.402] * 20 + [55.487] + [55.587] * 32
                + [55.703, 55.853, 56.053, 56.203])
        rows = [(499.21 + 0.25 * i, v) for i, v in enumerate(vals)]
        p = vc.clock_pauses(rows)
        self.assertEqual([(k, g) for _, _, g, k in p], [("freeze", False)], p)

    def test_a_creeping_clock_is_a_freeze_by_rate(self):
        p = vc.clock_pauses(clock_rows([(5, "run"), (6, ("creep", 0.1)), (5, "run")]))
        self.assertTrue(p and all(k == "freeze" for *_, k in p), p)
        self.assertEqual(vc.clock_pauses(clock_rows([(16, ("creep", 0.3))])), [])

    def test_the_round_step_pause_is_a_round_boundary(self):
        rows = clock_rows([(5, "run"), (5.5, "still"), (5, "run")])
        step = rows[20][0]                                  # mp_round_count steps on the first still row
        p = vc.clock_pauses(rows, round_steps=[step])
        self.assertEqual([k for *_, k in p], ["round"], p)
        self.assertEqual([k for *_, k in vc.clock_pauses(rows)], ["freeze"])

    def test_a_round_pause_longer_than_its_cap_is_a_freeze_beyond_it(self):
        rows = clock_rows([(5, "run"), (20, "still"), (5, "run")])
        p = vc.clock_pauses(rows, round_steps=[rows[20][0]])
        self.assertEqual([k for *_, k in p], ["round", "freeze"], p)
        self.assertAlmostEqual(p[1][0] - p[0][0], vc.ROUND_BOUNDARY_MAX_S, places=6)

    def test_a_stall_just_after_the_restart_is_still_the_boundary(self):
        # R63: the boundary runs from the step +-0.5 s to the clock restart + 1.25 s (at most 10 s)
        rows = clock_rows([(5, "run"), (5.5, "still"), (0.75, "run"), (1.5, "still"), (5, "run")])
        p = vc.clock_pauses(rows, round_steps=[rows[20][0]])
        self.assertEqual([k for *_, k in p], ["round", "round"], p)
        far = clock_rows([(5, "run"), (5.5, "still"), (3.0, "run"), (1.5, "still"), (5, "run")])
        self.assertEqual([k for *_, k in vc.clock_pauses(far, round_steps=[far[20][0]])], ["round", "freeze"])

    def test_ongoing(self):
        p = vc.clock_pauses(clock_rows([(5, "run"), (3, "still")]))
        self.assertTrue(p[-1][2])

    def test_round_steps(self):
        self.assertEqual(vc.round_steps([(1.0, 0), (2.0, 0), (3.0, 1), (4.0, 1), (5.0, 2)]), [3.0, 5.0])


class MovePathFreezeCapTest(unittest.TestCase):
    ENV = {"PS2X_CALL_TRACE": "0x553dc0:MoveScale,0x30cd80:NetIdle", "PS2X_CALL_TRACE_EVERY": "10",
           "PS2X_PEEK": "*0x408c58:64,*0x408c58+0xF78:24,*0x437ce8+0x0c*:2,*0x437ce8+0x0c**:3,0x4365c0:1"}

    def run_phases(self, phases, with_clock=True):
        c = Clock(0.0)
        tl = tail(c, "S")
        logged = []
        w = M.MovePathWatch({"X": tl}, logged.append, env=self.ENV, clock=c)
        rt, n = 10.0, 0
        for dur, calls, runs in phases:
            for _ in range(int(round(dur / 0.25))):
                c.t = round(c.t + 0.25, 6)
                rt += 0.17 if runs else 0.0
                if calls:
                    tl._line(f"[call] {c.t:.1f}s MoveScale #{n} a0=0x1 ra=0x595028 f12=1.0")
                    n += 5
                tl._line(peek(round_time=rt if with_clock else None))
                w.check()
        return w, logged

    def test_a_freeze_longer_than_the_cap_is_no_data(self):
        # rv5a/repro_adv.py: a 60 s still clock read `disarmed` for the whole 60 s
        w, logged = self.run_phases([(5, True, True), (M.FREEZE_MAX_S + 5.0, False, False)])
        self.assertEqual(w.verdicts["X"].status, vc.NO_DATA, logged)
        self.assertIsNotNone(w.freeze_nodata)
        self.assertIsNone(w.stalled)

    def test_a_freeze_under_the_cap_is_still_disarmed(self):
        w, logged = self.run_phases([(5, True, True), (15.0, False, False)])
        self.assertEqual(w.verdicts["X"].status, "disarmed")
        self.assertIsNone(w.freeze_nodata)

    def test_missing_round_clock_is_logged_once(self):
        w, logged = self.run_phases([(12, True, True)], with_clock=False)
        notes = [m for m in logged if "0x4365c0" in m and "blind" in m]
        self.assertEqual(len(notes), 1, logged)


def load_events():
    ev = []
    with open(os.path.join(FIXTURES, "launch8c_starvation_events.txt")) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            side, t, kind, *vals = line.split()
            ev.append((float(t), side, kind, vals))
    return ev


def replay_8c(lo, hi, strip_clock=False):
    """Launch 8c's two sides through a live StarvationWatch on a 0.25 s check grid (the review's I1 repro)."""
    ev = [e for e in load_events() if lo <= e[0] <= hi]
    c = Clock(lo)
    tails = {g: tail(c, g) for g in "AB"}
    lines = []
    w = M.StarvationWatch(tails, lambda m: lines.append((c.t, m)), clock=c)
    grid, i = lo, 0
    while i < len(ev):
        t = ev[i][0]
        while grid + 0.25 <= t:
            grid += 0.25
            c.t = grid
            w.check()
        c.t = t
        group = {}
        while i < len(ev) and ev[i][0] == t:
            _, side, kind, vals = ev[i]
            g = group.setdefault(side, {})
            if kind == "idle":
                tails[side]._line(f"[call] {t:.1f}s NetIdle #{vals[0]} a0=0x45a0c0 f12=0.0")
                tails[side]._line(f"[ret] NetIdle #{vals[0]} v0=0x{int(vals[1]):x} f0=0.6")
            elif kind == "ms":
                tails[side]._line(f"[call] {t:.1f}s MoveScale #{vals[0]} a0=0x1 ra=0x595028 f12={vals[1]}")
            else:
                g[kind] = float(vals[0]) if kind == "rt" else int(vals[0])
            i += 1
        for side, g in group.items():
            if "rt" in g or "lag" in g:
                tails[side]._line(peek(round_time=None if strip_clock else g.get("rt"), lag=g.get("lag"),
                                       alive=g.get("alive", 1), round_count=g.get("round", 0)))
    return w, lines


class Launch8cStarvationReplayTest(unittest.TestCase):
    """Review I1 (rv5a/repro_starv8c.py): the watch stopped `NO-DATA starvation side=A` at 506.0 s, inside A's freeze,
    because the freeze split into two episodes around one advancing row and NetIdle resumes after the clock."""

    def check_window(self, lo, hi):
        w, lines = replay_8c(lo, hi)
        self.assertIsNone(w.stop_reason, [m for _, m in lines])
        self.assertEqual(w.starvation_alarms(), 0, w.alarms)
        return w, lines

    def test_both_first_freezes(self):
        w, _ = self.check_window(495.0, 522.0)
        self.assertEqual(w.freeze_alarms(), {"A": 1}, w.alarms)          # B's 7145 ms idle is A's freeze

    def test_a_second_freeze(self):
        w, _ = self.check_window(543.0, 566.0)
        self.assertGreaterEqual(w.freeze_alarms().get("A", 0), 1, w.alarms)

    def test_b_17s_freeze(self):
        w, _ = self.check_window(612.0, 650.0)
        self.assertGreaterEqual(w.freeze_alarms().get("B", 0), 1, w.alarms)

    def test_the_round_step_pause_is_not_no_data(self):
        w, lines = self.check_window(772.0, 800.0)
        self.assertTrue(any("round(" in m for _, m in lines), [m for _, m in lines])

    def test_negative_control_without_the_round_clock_the_watch_stops(self):
        w, _ = replay_8c(495.0, 522.0, strip_clock=True)
        self.assertIn("NO-DATA", w.stop_reason or "")


class AttributionOverlapTest(unittest.TestCase):
    """Review I3 (rv5a/repro_attr.py): an alarm within 6 s of the other side's freeze end was `freeze(A)` even when its
    idle window began after the freeze -- that hides real starvation."""

    def setUp(self):
        self.c = Clock(0.0)
        self.tails = {g: tail(self.c, g) for g in "AB"}
        self.lines = []
        self.w = M.StarvationWatch(self.tails, self.lines.append, clock=self.c)
        self.rt = {"A": 10.0, "B": 10.0}
        self.n = {"A": 0, "B": 0}

    def step(self, sec, frozen=(), idle=None, lag=None):
        idle, lag = idle or {}, lag or {}
        end = self.c.t + sec
        while self.c.t < end - 1e-9:
            self.c.t = round(self.c.t + 0.25, 6)
            for g in "AB":
                v = idle.get(g, 300)
                if g not in frozen:
                    self.rt[g] += 0.25
                    if self.n[g] % 2 == 0:
                        self.tails[g]._line(f"[call] {self.c.t:.1f}s NetIdle #{self.n[g]} a0=0x45a0c0 f12=0.0")
                        self.tails[g]._line(f"[ret] NetIdle #{self.n[g]} v0=0x{v:x} f0=0.6")
                    self.n[g] += 1
                self.tails[g]._line(peek(round_time=self.rt[g], lag=lag.get(g, 1 if v >= 4501 else 0)))
            self.w.check()

    def test_an_idle_window_after_the_freeze_is_starvation(self):
        self.step(5.0)
        self.step(2.5, frozen=("A",))                      # A frozen 5.0-7.5 s
        self.step(4.5)                                     # both run to 12.0 s
        self.step(1.0, idle={"B": 4200})                   # B alarms at ~12.5 s: idle window starts ~8.3 s
        self.assertEqual([a["cause"] for a in self.w.alarms], ["starvation"], self.w.alarms)

    def test_an_idle_window_overlapping_the_freeze_is_the_freeze(self):
        self.step(5.0)
        self.step(2.5, frozen=("A",))
        self.step(1.0)
        self.step(1.0, idle={"B": 4200})                   # alarm at ~8.75 s: window from ~4.55 s overlaps
        self.assertEqual([a["cause"] for a in self.w.alarms], ["freeze(A)"], self.w.alarms)

    def test_a_lag_flag_alarm_uses_4501_ms(self):
        self.step(5.0)
        self.step(2.5, frozen=("A",))                      # 5.0-7.5
        self.step(3.5)                                     # to 11.0
        self.step(0.5, lag={"B": 1})                       # flag at ~11.25: [6.75, 11.25] overlaps the freeze
        self.assertEqual([a["cause"] for a in self.w.alarms], ["freeze(A)"], self.w.alarms)


class R24FreezeRetryTest(unittest.TestCase):
    """Review I4: a starved precondition hold (f12 < 1.0) is retried as NO-DATA; when the PEER's round clock stood still
    around it, the reason says freeze(<peer>)."""

    def run_case(self, peer_runs):
        from tools_py.tests.test_online_harness import FakeClock, FakeShell, ScaledWorld
        clock = FakeClock()
        world = ScaledWorld(clock, scale=0.4, responds=False)
        peer = tail(clock, "B")
        rt = [50.0]
        orig_wait = clock.wait

        def wait(s):
            end = clock() + s
            while clock() < end - 1e-9:
                orig_wait(min(0.25, end - clock()))
                rt[0] += 0.15 if peer_runs else 0.0
                peer._line(peek(round_time=rt[0]))
        clock.wait = wait
        wait(3.0)
        sh = FakeShell(world, clock)
        return M.assert_controllable("A", world, sh, clock=clock, wait=wait, peer=("B", peer))

    def test_the_retry_names_the_peer_freeze(self):
        side = self.run_case(peer_runs=False)
        self.assertTrue(side.holds and all("freeze(B)" in v.reason for v in side.holds), [v.reason for v in side.holds])

    def test_no_peer_freeze_no_label(self):
        side = self.run_case(peer_runs=True)
        self.assertTrue(side.holds and all("freeze(" not in v.reason for v in side.holds),
                        [v.reason for v in side.holds])


if __name__ == "__main__":
    unittest.main()
