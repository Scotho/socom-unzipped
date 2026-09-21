"""Sprint 5 R70 (ladder launch 1: drive_s5_t5_ladder1b) -- the route budget was sized on WALK_UNITS_PER_S_LONG (the
plant's hold speed with no aim/read latency), not the follower's measured wall-clock delivery, so every round's
route stopped on `time budget exceeded` while still progressing. This covers:

  * ROUTE_BUDGET = 20 + 3 x length / ROUTE_WALK_RATE_U_S (7.5 u/s, the launch-1 measurement), uncapped;
  * capped so >= ROUND_FIGHT_RESERVE_S (120 s) of round clock remains for the close and the fight;
  * a capped budget <= 0 is exactly ROUTE_NO_TIME_REASON, recorded before any leg is walked;
  * per-round closest_3d (the RESULT line) is that round's own minimum, not the whole run's (launch 1 printed
    113.27 on every round).

R70 fix round 1 (review of 89590c2) adds:
  * the ROUTE_NO_TIME_REASON passthrough at the two endgame_* call sites must match that EXACT tag, never the whole
    vc.NO_DATA family -- follow_route's pre-existing "NO-DATA heading or position" is still a scored route failure
    with the swap hint (R70 fix round 1, finding 1);
  * R71: when the round clock string can't be read at all, the budget is capped from the round's own elapsed time
    (route_no_clock_cap_s), not left uncapped, and the `remaining:.0f` format no longer raises on None
    (R70 fix round 1, finding 2).

unittest only; red until the fix lands (wip_test_* is not picked up by `unittest discover`'s default test*.py
pattern)."""
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.tests.online_rows import Clock, peek, tail
from tools_py.tests.test_route_budgets import make


class DummySh:
    """A Side's `.sh` with no game behind it: enough for aim_yaw's NO-DATA log line and (unused here) a pad."""

    def log(self, m):
        pass

    def pad(self, *a, **k):
        pass


class RouteBudgetFormulaTest(unittest.TestCase):
    def test_uncapped_budget_on_an_840_unit_route(self):
        # 20 + 3 * 840 / 7.5 = 356
        self.assertEqual(M.ROUTE_WALK_RATE_U_S, 7.5)
        self.assertAlmostEqual(M.route_budget_s(840.0), 356.0, places=6)

    def test_capped_by_250s_of_clock_left(self):
        # min(356, 250 - 120) = 130
        self.assertAlmostEqual(M.route_budget_s(840.0, clock_remaining=250.0), 130.0, places=6)

    def test_100s_left_is_route_no_time(self):
        # min(356, 100 - 120) = -20 <= 0
        self.assertLessEqual(M.route_budget_s(840.0, clock_remaining=100.0), 0.0)


class FollowRouteNoTimeTest(unittest.TestCase):
    """follow_route itself, not just the pure formula: a capped-to-<=0 budget is recorded as exactly
    ROUTE_NO_TIME_REASON before a single leg is walked, and (endgame_route / endgame_cooperative) that reason
    reaches out['stop_reason'] unwrapped -- the round is not scored, never 'route failed: ...'."""

    def test_follow_route_fails_no_data_route_no_time_without_walking(self):
        c, w, sh, me = make()
        r = M.follow_route(me, [(0.0, 0.0), (840.0, 0.0)], clock=c, wait=c.wait, log=sh.log, clock_remaining=100.0)
        self.assertFalse(r["ok"])
        self.assertTrue(r["reason"].startswith(M.ROUTE_NO_TIME_REASON), r)
        self.assertEqual(r["legs"], 0)                       # skipped before the first leg
        self.assertEqual([p for p in sh.pads if p[2]], [])   # nobody walked

    def test_endgame_route_carries_no_data_unwrapped(self):
        c = Clock(0.0)
        ta, tb = tail(c, "A"), tail(c, "B")
        # a round clock with only 100 s left: 840 units at 7.5 u/s wants 356 s, capped to (100 - 120) <= 0
        ta._line(peek(x=0.0, y=100.0, z=0.0, clock="01:40", round_time=10.0))
        tb._line(peek(x=500.0, y=100.0, z=0.0, clock="01:40", round_time=10.0))
        sides = {"A": M.Side("A", DummySh(), ta), "B": M.Side("B", DummySh(), tb)}
        lines = []
        out = M.endgame_route(sides, M.Duel(), None, lines.append, "nomap", mover="A",
                              route=[(0.0, 0.0), (840.0, 0.0)], fight_s=5.0, clock=c, wait=c.wait)
        self.assertTrue((out["stop_reason"] or "").startswith(M.ROUTE_NO_TIME_REASON), out["stop_reason"])
        self.assertNotIn("route failed", out["stop_reason"])

    def test_route_clock_remaining_reads_the_clock_string(self):
        c = Clock(0.0)
        t = tail(c, "A")
        t._line(peek(x=0.0, y=100.0, z=0.0, clock="02:10", round_time=10.0))  # 130 s left
        c.wait(5.0)
        self.assertAlmostEqual(M.route_clock_remaining_s(t, clock=c), 125.0, delta=0.5)


class NoDataHeadingStillScoredTest(unittest.TestCase):
    """R70 fix round 1, finding 1 (critical): the two endgame_* NO-DATA passthroughs matched the whole vc.NO_DATA
    family, so follow_route's OWN, pre-existing 'NO-DATA heading or position' (aim_yaw never resolving a heading)
    also skipped the scored 'route failed: ... swaps' wrap. It must not -- only the exact ROUTE_NO_TIME_REASON tag
    is unwrapped. Tested directly against the wrap-decision helpers (route_swap_stop_reason / route_stop_reason):
    going through the live endgame_route/endgame_cooperative call would also spin up their stander/victim thread,
    which free-runs the simulated Clock (no real wait) and races the main thread's follow_route -- a pre-existing
    harness hazard, not this fix's concern. (Sprint 10: that hazard is closed -- online_rows.Clock runs its threads
    in lockstep, test_lockstep_clock.py -- and these helper-level tests stay as they are.)"""

    def test_endgame_route_keeps_the_route_failed_wrap_and_swap_hint(self):
        reason = M.route_swap_stop_reason("NO-DATA heading or position", "B")
        self.assertEqual(reason, "route failed: NO-DATA heading or position -- --mover B swaps which side walks")

    def test_endgame_cooperative_keeps_the_route_failed_wrap_with_no_swap_hint(self):
        reason = M.route_stop_reason("NO-DATA heading or position")
        self.assertEqual(reason, "route failed: NO-DATA heading or position")

    def test_route_no_time_passes_through_unwrapped_both_modes(self):
        tagged = f"{M.ROUTE_NO_TIME_REASON}: 10s left on the round clock, under the 120s reserved -- skipped"
        self.assertEqual(M.route_swap_stop_reason(tagged, "B"), tagged)
        self.assertEqual(M.route_stop_reason(tagged), tagged)

    def test_a_real_follow_route_no_data_heading_feeds_the_same_wrap(self):
        # confirms the exact string follow_route raises (not a guess) still gets the scored wrap
        c = Clock(0.0)
        t = tail(c, "A")
        # actor position present, but peek() with no `facing=` writes an all-zero matrix: heading never resolves
        t._line(peek(x=0.0, y=100.0, z=0.0, clock="05:00", round_time=10.0))
        me = M.Side("A", DummySh(), t)
        r = M.follow_route(me, [(0.0, 0.0), (100.0, 0.0)], clock=c, wait=c.wait, log=lambda m: None)
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "NO-DATA heading or position")
        wrapped = M.route_swap_stop_reason(r["reason"], "B")
        self.assertTrue(wrapped.startswith("route failed: NO-DATA heading or position"), wrapped)
        self.assertIn("--mover B swaps which side walks", wrapped)


class NoClockCapTest(unittest.TestCase):
    """R71 (R70 fix round 1, finding 2): route_clock_remaining_s returning None must not drop the cap back to the
    raw, uncapped formula (~356 s on an 840-unit route) -- it falls back to route_no_clock_cap_s, derived from the
    round's own elapsed time."""

    def test_100s_since_round_start_caps_at_140(self):
        # ROUTE_BUDGET_NO_CLOCK_S (360) - ROUND_FIGHT_RESERVE_S (120) - 100 = 140
        self.assertAlmostEqual(M.route_no_clock_cap_s(1000.0, clock=lambda: 1100.0), 140.0, places=6)

    def test_300s_since_round_start_floors_at_zero(self):
        # 360 - 120 - 300 = -60 -> floored at 0
        self.assertEqual(M.route_no_clock_cap_s(1000.0, clock=lambda: 1300.0), 0.0)

    def test_without_a_round_start_the_cap_is_flat_120(self):
        self.assertEqual(M.route_no_clock_cap_s(None), M.ROUND_FIGHT_RESERVE_S)

    def _unreadable_clock_tail(self):
        # a tail that never received a single line: no round_rows at all -> route_clock_remaining_s is None
        return tail(Clock(0.0), "A")

    def test_follow_route_with_100s_elapsed_still_has_budget_to_try_the_route(self):
        t = self._unreadable_clock_tail()
        me = M.Side("A", DummySh(), t)
        lines = []
        # cap = 140 > 0: the immediate NO-DATA route-no-time precheck is skipped and the (empty) tail is read for
        # real, failing on 'stale actor rows' instead -- proof the budget was positive, not zero
        r = M.follow_route(me, [(0.0, 0.0), (840.0, 0.0)], clock=lambda: 1100.0, wait=lambda s: None,
                           log=lines.append, round_start=1000.0)
        self.assertFalse(r["ok"])
        self.assertNotIn(M.ROUTE_NO_TIME_REASON, r["reason"])
        self.assertEqual(r["reason"], "stale actor rows")

    def test_follow_route_with_300s_elapsed_is_route_no_time(self):
        t = self._unreadable_clock_tail()
        me = M.Side("A", DummySh(), t)
        lines = []
        r = M.follow_route(me, [(0.0, 0.0), (840.0, 0.0)], clock=lambda: 1300.0, wait=lambda s: None,
                           log=lines.append, round_start=1000.0)
        self.assertFalse(r["ok"])
        self.assertTrue(r["reason"].startswith(M.ROUTE_NO_TIME_REASON), r)
        self.assertEqual(r["legs"], 0)


class PerRoundClosestTest(unittest.TestCase):
    """A round-1 window far apart, then a round-2 window close together: ladder_contact's closest_3d (bounded to
    the round's own actor rows) must report round 1's own minimum, not round 2's closer approach -- what
    duel.best_dist() (the whole-run minimum) would wrongly report for round 1 too."""

    def test_closest_3d_is_scoped_to_the_round(self):
        c = Clock(0.0)
        ta, tb = tail(c, "A"), tail(c, "B")

        def feed(t0, n, ax, az, bx, bz):
            for i in range(n):
                c.t = t0 + 0.25 * i
                ta._line(peek(x=ax, y=100.0, z=az, clock="05:00"))
                tb._line(peek(x=bx, y=100.0, z=bz, clock="05:00"))

        feed(0.0, 12, 0.0, 0.0, 500.0, 0.0)       # round 1: ~500 apart throughout
        t_round1_end = c.t
        feed(20.0, 12, 0.0, 0.0, 50.0, 0.0)       # round 2: ~50 apart throughout

        contact1 = M.ladder_contact(ta, tb, 0.0, t_round1_end)
        self.assertAlmostEqual(contact1.closest_3d, 500.0, delta=1.0)

        duel = M.Duel()
        duel.observe("A", ta)
        duel.observe("B", tb)
        run_min = duel.best_dist()
        self.assertAlmostEqual(run_min, 50.0, delta=1.0)     # the whole-run minimum sees round 2
        self.assertGreater(contact1.closest_3d, run_min + 100.0)  # round 1's own closest is NOT the run minimum


if __name__ == "__main__":
    unittest.main()
