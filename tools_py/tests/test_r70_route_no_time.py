"""Sprint 5 R70 (ladder launch 1: drive_s5_t5_ladder1b) -- the route budget was sized on WALK_UNITS_PER_S_LONG (the
plant's hold speed with no aim/read latency), not the follower's measured wall-clock delivery, so every round's
route stopped on `time budget exceeded` while still progressing. This covers:

  * ROUTE_BUDGET = 20 + 3 x length / ROUTE_WALK_RATE_U_S (7.5 u/s, the launch-1 measurement), uncapped;
  * capped so >= ROUND_FIGHT_RESERVE_S (120 s) of round clock remains for the close and the fight;
  * a capped budget <= 0 is NO-DATA route-no-time, recorded before any leg is walked;
  * per-round closest_3d (the RESULT line) is that round's own minimum, not the whole run's (launch 1 printed
    113.27 on every round).

unittest only; red until the fix lands (wip_test_* is not picked up by `unittest discover`'s default test*.py
pattern)."""
import math
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import Clock, peek, tail
from tools_py.tests.test_route_budgets import make


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
    """follow_route itself, not just the pure formula: a capped-to-<=0 budget is recorded as NO-DATA route-no-time
    before a single leg is walked, and (endgame_route / endgame_cooperative) that NO-DATA reason reaches
    out['stop_reason'] unwrapped -- the round is not scored, never 'route failed: ...'."""

    def test_follow_route_fails_no_data_route_no_time_without_walking(self):
        c, w, sh, me = make()
        r = M.follow_route(me, [(0.0, 0.0), (840.0, 0.0)], clock=c, wait=c.wait, log=sh.log, clock_remaining=100.0)
        self.assertFalse(r["ok"])
        self.assertTrue(r["reason"].startswith(f"{vc.NO_DATA} route-no-time"), r)
        self.assertEqual(r["legs"], 0)                       # skipped before the first leg
        self.assertEqual([p for p in sh.pads if p[2]], [])   # nobody walked

    class DummySh:
        def log(self, m):
            pass

        def pad(self, *a, **k):
            pass

    def test_endgame_route_carries_no_data_unwrapped(self):
        c = Clock(0.0)
        ta, tb = tail(c, "A"), tail(c, "B")
        # a round clock with only 100 s left: 840 units at 7.5 u/s wants 356 s, capped to (100 - 120) <= 0
        ta._line(peek(x=0.0, y=100.0, z=0.0, clock="01:40", round_time=10.0))
        tb._line(peek(x=500.0, y=100.0, z=0.0, clock="01:40", round_time=10.0))
        sides = {"A": M.Side("A", self.DummySh(), ta), "B": M.Side("B", self.DummySh(), tb)}
        lines = []
        out = M.endgame_route(sides, M.Duel(), None, lines.append, "nomap", mover="A",
                              route=[(0.0, 0.0), (840.0, 0.0)], fight_s=5.0, clock=c, wait=c.wait)
        self.assertTrue((out["stop_reason"] or "").startswith(f"{vc.NO_DATA} route-no-time"), out["stop_reason"])
        self.assertNotIn("route failed", out["stop_reason"])

    def test_route_clock_remaining_reads_the_clock_string(self):
        c = Clock(0.0)
        t = tail(c, "A")
        t._line(peek(x=0.0, y=100.0, z=0.0, clock="02:10", round_time=10.0))  # 130 s left
        c.wait(5.0)
        self.assertAlmostEqual(M.route_clock_remaining_s(t, clock=c), 125.0, delta=0.5)


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
