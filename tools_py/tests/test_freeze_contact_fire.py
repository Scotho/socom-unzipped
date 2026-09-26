"""Sprint 5 Task 5 fix round, slice 2 -- freezes, contact and fire windows (reviews of finish (i)-(iii) and (iv)-(vi)):

  * I5: a guest-clock freeze PAUSES a contact run -- after the pause each liveness requirement (MoveScale on both sides,
    the clock string changing, f12) is granted its own window measured from the pause end, because on launch 8c the
    clock string changes 0.25 s after the clock runs and MoveScale resumes 0.18-2.3 s later;
  * minors: A's and B's pauses are merged before the paused span is subtracted; only FREEZES pause a run -- a round
    boundary breaks it (a contact run cannot bridge two rounds);
  * I3: after the fight loop, the fire windows are re-checked once their rows had FIRE_WINDOW_SETTLE_S (1.25 s) to
    arrive -- a freeze or a teleport in the LAST window, each visible only late;
  * I6: the same re-check for a window inside the loop, at the next iteration.

Sprint 10 (docs/HAZARDS.md harness, the CI flake): the stander / victim thread and the shooter share the Clock in lockstep
(online_rows.Clock), so the victim cannot walk legs while the shooter has not had its turn -- these tests ran 50
failures in 100 contended runs before that -- and the endgames end their side thread in simulated time
(M.join_in), which the last test of each class checks.

unittest only; simulated time.
"""
import math
import threading
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import Clock, f2w, item
from tools_py.tests.test_engagement_ladder import WalkShell, WalkWorld

P = 0.25


def freeze_world(t_on, t_off, freeze, string_lag_rows=0, calls_lag=0.0, gap=40.0, g0=50.37, steps=None):
    """Contact (3-D = gap) over [t_on, t_off], far (200) outside; the guest clock 0x4365c0 still over freeze=(f0, f1);
    the clock STRING still over [f0, f1 + string_lag_rows * P) and then on host time again (8c: 03:50 -> 03:40 one row
    after the clock ran); MoveScale / f12 lines stop at f0 and resume `calls_lag` s after f1 (8c B 0.18 s, A 2.3 s)."""
    rowsA, rowsB, rtA, rtB, clk, cA, cB, fA, fB = [], [], [], [], [], [], [], [], []
    g, k, t = g0, 0, t_on - 5.0
    while t <= t_off + 5.0 + 1e-9:
        frozen = freeze and freeze[0] <= t < freeze[1]
        if not frozen and k:
            g += 0.15
        d = gap if t_on <= t <= t_off else 200.0
        rowsA.append((t, 0.0, 100.0, 0.0, 1))
        rowsB.append((t + 0.05, d, 100.0, 0.0, 2))
        rtA.append((t, round(g, 4)))
        rtB.append((t + 0.05, round(g + 0.01, 4)))
        still = freeze and freeze[0] <= t < freeze[1] + string_lag_rows * P
        s = 300 - int(freeze[0] if still else t)
        clk.append((t, f"{s // 60:02d}:{s % 60:02d}"))
        k += 1
        t = round(t + P, 6)
    n, tt = 0, t_on - 5.0
    while tt <= t_off + 5.0:
        if not (freeze and freeze[0] <= tt < freeze[1] + calls_lag):
            n += 10
            cA.append((tt, n))
            cB.append((tt + 0.05, n))
            fA.append((tt, 1.0))
            fB.append((tt + 0.05, 1.0))
        tt = round(tt + 0.5, 6)
    return vc.score_contact(rowsA, rowsB, cA, cB, clk, (fA, fB), round_time_rows=(rtA, rtB),
                            round_steps=steps or ((), ()))


class ContactFreezePausesTest(unittest.TestCase):
    SHAPES = (("immediate", dict()), ("string +1 row", dict(string_lag_rows=1)),
              ("MoveScale +0.18 s", dict(calls_lag=0.18)), ("MoveScale +2.3 s", dict(calls_lag=2.3)),
              ("string +1 row and MoveScale +2.3 s", dict(string_lag_rows=1, calls_lag=2.3)))

    def test_a_3_s_freeze_inside_6_s_of_contact_pauses_the_run_under_every_resume_shape(self):
        for label, kw in self.SHAPES:
            r = freeze_world(100.0, 109.0, (103.0, 106.0), **kw)
            self.assertTrue(r.ok, (label, r))
            self.assertAlmostEqual(r.contact_s, 6.0, delta=0.3, msg=label)

    def test_without_the_freeze_the_same_contact_is_9_s(self):
        r = freeze_world(100.0, 109.0, None)
        self.assertAlmostEqual(r.contact_s, 9.0, delta=0.01)

    def test_the_grace_is_only_the_requirement_window(self):
        # MoveScale never resumes after the freeze: the grace (3 s from the pause end) runs out and the run breaks
        r = freeze_world(100.0, 115.0, (103.0, 106.0), calls_lag=30.0)
        self.assertLess(r.contact_s, 6.5)

    def test_overlapping_a_and_b_pauses_are_subtracted_once(self):
        a = [(100.0 + i * P, 0.0, 100.0, 0.0, 1) for i in range(60)]
        b = [(100.05 + i * P, 30.0, 100.0, 0.0, 2) for i in range(60)]
        calls = [(95.0 + k * 0.5, 10 * k) for k in range(80)]
        clk = [(95.0 + k * P, "%02d:%02d" % divmod(299 - int(k * P), 60)) for k in range(160)]
        sc = [(95.0 + k * 0.5, 1.0) for k in range(80)]
        # A's and B's clocks stand over the same 1.2 s (a stall under the row-gap bridge): both pauses cover it
        rt = lambda off: [(95.0 + k * P + off, 50.0 + (min(k, 36) + max(0, k - 41)) * 0.15) for k in range(160)]
        r = vc.score_contact(a, b, calls, calls, clk, (sc, sc), round_time_rows=(rt(0.0), rt(0.05)))
        paused = sum(p[1] - p[0] for p in vc.clock_pauses(rt(0.0)))
        self.assertGreater(paused, 1.0)
        self.assertAlmostEqual(r.contact_s, 14.75 - paused, delta=0.3)

    def test_a_round_boundary_breaks_the_run(self):
        steps = ((103.0,), (103.05,))
        r = freeze_world(100.0, 109.0, (103.0, 106.0), steps=steps)
        self.assertLess(r.contact_s, 5.0, r)
        self.assertFalse(r.ok)


class ClockWalkWorld(WalkWorld):
    """WalkWorld plus the round clock 0x4365c0 (its own `[peek]` line), which stands still from `freeze_at` on, and one
    ground jump of `jump` units at the first tick after `jump_after()` returns a time."""

    def __init__(self, clock, *a, freeze_at=None, jump_after=None, jump=60.0, **kw):
        self.rt, self.freeze_at, self.jump_after, self.jump = 10.0, freeze_at, jump_after, jump
        super().__init__(clock, *a, **kw)

    def tick(self, t):
        ja = self.jump_after() if self.jump_after is not None else None
        if ja is not None and t > ja:
            self.x += self.jump
            self.jump_after = None
        super().tick(t)
        fa = self.freeze_at() if callable(self.freeze_at) else self.freeze_at
        if fa is None or t < fa:
            self.rt += 0.15
        self.tail._line("[peek] " + item(0x4365C0, [f2w(self.rt)]))


class BurstShell(WalkShell):
    def __init__(self, world):
        super().__init__(world)
        self.r1_end = []

    def pad(self, seconds, buttons=(), sticks=(), axes=None, abort=None):
        t0 = self.world.clock.t
        super().pad(seconds, buttons, sticks, axes, abort)
        if "R1" in buttons:
            self.r1_end.append((t0, self.world.clock.t))


def run_fight(fight_s, victim_kw):
    c = Clock(0.0)
    shooter = ClockWalkWorld(c, 0.0, 0.0, 0.0)
    ssh = BurstShell(shooter)
    first = lambda i: (lambda: ssh.r1_end[0][i] if ssh.r1_end else None)
    kw = {k: (first(v[1]) if isinstance(v, tuple) and v[0] == "burst" else v) for k, v in victim_kw.items()}
    if "jump_after" in kw:
        ja = kw["jump_after"]
        kw["jump_after"] = lambda: None if ja() is None else ja() + M.ENDGAME_BURST_GAP_S
    victim = ClockWalkWorld(c, 25.0, 0.0, 180.0, **kw)
    c.wait(1.0)
    sides = {"A": M.Side("A", ssh, shooter.tail), "B": M.Side("B", WalkShell(victim), victim.tail)}
    lines = []
    out = M.endgame_route(sides, M.Duel(), None, lines.append, "nomap", mover="A", route=[], fight_s=fight_s,
                          clock=c, wait=c.wait)
    return out, lines, c, ssh


class FireWindowLateTest(unittest.TestCase):
    def test_a_freeze_in_the_last_window_seen_late_is_no_data(self):
        out, lines, c, ssh = run_fight(0.1, {"freeze_at": ("burst", 0)})
        self.assertEqual(out["bursts"], 1, lines)
        self.assertIsNotNone(out.get("fire_freeze"), lines)
        self.assertTrue(out["stop_reason"].startswith("NO-DATA freeze in a fire window"), out["stop_reason"])

    def test_a_teleport_in_the_last_window_seen_late_is_no_data(self):
        out, lines, c, ssh = run_fight(0.1, {"jump_after": ("burst", 1)})
        self.assertEqual(out["bursts"], 1, lines)
        self.assertIsNotNone(out.get("fire_teleport"), lines)
        self.assertTrue(out["stop_reason"].startswith("NO-DATA teleport in a fire window"), out["stop_reason"])

    def test_a_teleport_seen_late_inside_the_loop_stops_at_the_next_iteration(self):
        out, lines, c, ssh = run_fight(6.0, {"jump_after": ("burst", 1)})
        self.assertIsNotNone(out.get("fire_teleport"), lines)
        self.assertEqual(out["bursts"], 1, lines)

    def test_a_quiet_fight_is_not_no_data(self):
        out, lines, c, ssh = run_fight(0.1, {})
        self.assertEqual(out["bursts"], 1, lines)
        self.assertIsNone(out.get("fire_freeze"), lines)
        self.assertIsNone(out.get("fire_teleport"), lines)

    def test_the_stander_thread_ends_with_the_fight(self):
        # Sprint 10: the stander was joined outside the clock (a native join with a 3 s timeout) and, under lockstep,
        # could not take the poll that ends it -- the join timed out in real time and the thread leaked
        out, lines, c, ssh = run_fight(0.1, {})
        self.assertEqual(c.threads(), [threading.current_thread()], "a side thread outlived the fight")
        self.assertGreater(out["t_end"], out["t_fight"])


class CooperativeFireWindowTest(unittest.TestCase):
    """Minor (fix round): the cooperative mode classifies round resets and runs the fire-window freeze check too."""

    def run_coop(self, victim_kw):
        c = Clock(0.0)
        shooter = ClockWalkWorld(c, 0.0, 0.0, 0.0)
        ssh = BurstShell(shooter)
        kw = {k: ((lambda: ssh.r1_end[0][0] if ssh.r1_end else None) if v == "burst" else v)
              for k, v in victim_kw.items()}
        victim = ClockWalkWorld(c, 18.0, 0.0, 180.0, **kw)
        c.wait(1.0)
        sides = {"A": M.Side("A", ssh, shooter.tail), "B": M.Side("B", WalkShell(victim), victim.tail)}
        lines = []
        out = M.endgame_cooperative(sides, M.Duel(), None, lines.append, route=[], fight_s=0.1, micro_strafe=False,
                                    rule=False, clock=c, wait=c.wait)
        return out, lines, c

    def test_a_freeze_in_the_last_window_is_no_data(self):
        out, lines, c = self.run_coop({"freeze_at": "burst"})
        self.assertGreaterEqual(out["bursts"], 1, lines)
        self.assertIsNotNone(out.get("fire_freeze"), lines)

    def test_a_quiet_fight_is_not(self):
        out, lines, c = self.run_coop({})
        self.assertGreaterEqual(out["bursts"], 1, lines)
        self.assertIsNone(out.get("fire_freeze"), lines)

    def test_both_side_threads_end_with_the_fight(self):
        # Sprint 10: the shooter and the victim are both daemon threads here; the caller joins each through the
        # injected wait, and the victim's last leg is walked in simulated time, not abandoned at a real timeout
        out, lines, c = self.run_coop({})
        self.assertEqual(c.threads(), [threading.current_thread()], "a side thread outlived the fight")
        self.assertGreater(out["t_end"], out["t_fight"])


if __name__ == "__main__":
    unittest.main()
