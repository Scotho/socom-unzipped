"""Controller rulings after Task 5 finish:

  * R65: after the precondition the mover joins the route at the nearest waypoint on its floor (|dy| <= 10 against the
    leg's expected_floor_y) within 60 units, later waypoints in order; none qualifies -> `NO-DATA route-start`, no
    unrouted walk; rounds >= 2 start at waypoint 0;
  * R66: the ladder template passes --auto-swap;
  * R67: rung 0's instrument parameters are registered named constants (not acceptance bars, plan Amendment A4).
"""
import os
import unittest

from tools_py.parity import online_ladder as LD
from tools_py.parity import online_match_ours as M
from tools_py.tests.online_rows import Clock
from tools_py.tests.test_engagement_ladder import WalkShell, WalkWorld

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def wp(x, z, fy):
    return {"x": x, "z": z, "y": fy, "floor_y": fy, "arrive": 20.0, "ramp": False, "clearance": 30.0}


ROUTE = [wp(0.0, 0.0, 100.0), wp(50.0, 0.0, 100.0), wp(100.0, 0.0, 100.0), wp(150.0, 0.0, 142.0), wp(200.0, 0.0, 142.0)]


class RouteJoinTest(unittest.TestCase):
    def test_nearest_same_floor_waypoint_within_60(self):
        self.assertEqual(M.ROUTE_JOIN_MAX_UNITS, 60.0)
        self.assertEqual(M.route_join_index(ROUTE, (95.0, 100.0, 10.0)), 2)
        self.assertEqual(M.route_join_index(ROUTE, (148.0, 100.0, 0.0)), 2)       # wp3 is nearer but on y 142
        self.assertEqual(M.route_join_index(ROUTE, (148.0, 142.0, 0.0)), 3)
        self.assertIsNone(M.route_join_index(ROUTE, (100.0, 100.0, 90.0)))        # nothing within 60
        self.assertIsNone(M.route_join_index(ROUTE, (20.0, 125.0, 0.0)))          # no waypoint on this floor

    def run_endgame(self, start_x, join):
        c = Clock(0.0)
        wa, wb = WalkWorld(c, start_x, 0.0, 0.0), WalkWorld(c, 400.0, 0.0, 180.0)
        c.wait(1.0)
        sa = WalkShell(wa)
        sides = {"A": M.Side("A", sa, wa.tail), "B": M.Side("B", WalkShell(wb), wb.tail)}
        lines = []
        out = M.endgame_route(sides, M.Duel(), None, lines.append, "nomap", mover="A", route=ROUTE[:3], fight_s=1.0,
                              clock=c, wait=c.wait, route_join=join)
        return out, sa, lines

    def test_no_qualifying_waypoint_is_no_data_and_nobody_walks(self):
        out, sa, lines = self.run_endgame(-200.0, "nearest")
        self.assertTrue((out["stop_reason"] or "").startswith("NO-DATA route-start"), out["stop_reason"])
        self.assertEqual([p for p in sa.pads if p[2]], [])

    def test_joining_mid_route_skips_the_earlier_waypoints(self):
        out, sa, lines = self.run_endgame(55.0, "nearest")
        self.assertEqual(out["route_join"], 1)
        self.assertTrue(any("ROUTE A start: 2 waypoints" in m for m in lines), lines)    # wp0 is not walked back to

    def test_start_joins_at_waypoint_0(self):
        out, sa, lines = self.run_endgame(55.0, "start")
        self.assertEqual(out["route_join"], 0)


class TemplateAutoSwapTest(unittest.TestCase):
    def test_the_template_passes_auto_swap(self):
        text = open(os.path.join(ROOT, "scripts", "parity", "ladder_frostfire.sh")).read()
        args = text.split("ARGS=(", 1)[1].split(")", 1)[0]
        self.assertIn("--auto-swap", args)


class Rung0ParametersTest(unittest.TestCase):
    def test_registered_instrument_parameters(self):
        self.assertEqual(LD.RUNG0_INSTRUMENT_PARAMETERS,
                         {"movescale_min_per_s": 17.0, "window_s": 60.0, "clock_rate_min": 0.95, "bp_waits_max": 100})
        src = open(LD.__file__).read()
        self.assertIn("instrument parameters, not acceptance bars (plan Amendment A4)", src)


if __name__ == "__main__":
    unittest.main()
