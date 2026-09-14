"""Sprint 5 Task 5 fix round, slice 5 -- the reviews' minors:

  * ladder_rung: contact NO-DATA on a controllable pair is rung NO-DATA, not rung 1;
  * MovePathWatch: a short freeze does not restart the 10 s stall clock from its end -- the silence before it counts;
  * launch_refusal_lines: its RESULT lines carry harness= / exe=;
  * follow_route: arrival on a ramp leg tolerates 6 + grade x the arrival distance in y;
  * follow_route / close_to: near the waypoint (within ROUTE_PROGRESS_UNITS of arriving) any new minimum of the
    distance to go is progress -- an overshooting approach does not trip the stuck or no-progress budgets.

unittest only; simulated time.
"""
import math
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import Clock, peek, tail
from tools_py.tests.test_route_budgets import make


class LadderRungNoDataTest(unittest.TestCase):
    def test_contact_no_data_is_no_data(self):
        self.assertEqual(M.ladder_rung(("yes", "yes"), None, "no"), vc.NO_DATA)
        self.assertEqual(M.ladder_rung(("yes", "yes"), False, "no"), 1)
        self.assertEqual(M.ladder_rung(("yes", "no"), None, "no"), 0)


class MovePathPreFreezeSilenceTest(unittest.TestCase):
    ENV = {"PS2X_CALL_TRACE": "0x553dc0:MoveScale,0x30cd80:NetIdle", "PS2X_CALL_TRACE_EVERY": "10",
           "PS2X_PEEK": "*0x408c58:64,*0x408c58+0xF78:24,*0x437ce8+0x0c*:2,*0x437ce8+0x0c**:3,0x4365c0:1"}

    def run_watch(self, silent_before, freeze_s, after):
        c = Clock(0.0)
        tl = tail(c, "S")
        w = M.MovePathWatch({"X": tl}, lambda m: None, env=self.ENV, clock=c)
        rt, n = 10.0, 0
        for _ in range(8):                                   # 2 s of a live move path
            c.t = round(c.t + 0.25, 6)
            rt += 0.15
            tl._line(f"[call] {c.t:.1f}s MoveScale #{n} a0=0x1 ra=0x595028 f12=1.0")
            n += 5
            tl._line(peek(round_time=rt))
        for phase, secs in (("run", silent_before), ("freeze", freeze_s), ("run", after)):
            for _ in range(int(round(secs / 0.25))):
                c.t = round(c.t + 0.25, 6)
                if phase == "run":
                    rt += 0.15
                tl._line(peek(round_time=rt))
        return w.check()["X"]

    def test_the_silence_before_a_short_freeze_counts(self):
        v = self.run_watch(8.0, 2.0, 2.5)                    # 8 s silent + 2 s frozen + 2.5 s silent = 10.5 s silent
        self.assertEqual(v.status, "stalled", v.detail)

    def test_under_ten_seconds_of_silence_around_the_freeze_is_not_a_stall(self):
        v = self.run_watch(6.0, 2.0, 3.0)                    # 9 s silent
        self.assertEqual(v.status, "disarmed", v.detail)


class RefusalIdentityTest(unittest.TestCase):
    def test_result_lines_carry_the_identity(self):
        lines, code = M.launch_refusal_lines({}, 0xF7A, 0x1044, ident="harness=abc exe=def")
        results = [ln for ln in lines if ln.startswith("RESULT")]
        self.assertTrue(results)
        self.assertTrue(all(ln.endswith(" harness=abc exe=def") for ln in results), results)


class RampArrivalTest(unittest.TestCase):
    def test_arriving_on_a_ramp_leg_tolerates_its_grade(self):
        grade = 0.525
        ground = lambda x, z: 100.0 + grade * max(0.0, x)
        c, w, sh, me = make(ground=ground)
        route = [{"x": 0.0, "z": 0.0, "y": 100.0, "floor_y": 100.0, "arrive": 20.0, "ramp": False},
                 {"x": 140.0, "z": 0.0, "y": 173.5, "floor_y": 173.5, "arrive": 20.0, "ramp": True}]
        r = M.follow_route(me, route, clock=c, wait=c.wait, log=sh.log)
        self.assertTrue(r["ok"], (r, sh.lines[-4:]))
        self.assertGreater(abs(ground(w.x, w.z) - 173.5), M.ROUTE_FLOOR_TOL_Y)    # it arrived on the slope, not at the top

    def test_a_flat_leg_keeps_the_6_unit_floor_tolerance(self):
        c, w, sh, me = make()
        route = [{"x": 0.0, "z": 0.0, "y": 100.0, "floor_y": 100.0, "arrive": 20.0, "ramp": False},
                 {"x": 40.0, "z": 0.0, "y": 108.0, "floor_y": 108.0, "arrive": 20.0, "ramp": False}]
        r = M.follow_route(me, route, clock=c, wait=c.wait, log=sh.log)
        self.assertFalse(r["ok"])
        self.assertIn("floor", r["reason"])


class NearArrivalProgressTest(unittest.TestCase):
    def test_small_gains_near_the_waypoint_are_progress(self):
        state = {"leg_t": None}

        def script(w, t):
            new_leg = state["leg_t"] is None or t - state["leg_t"] > 0.3
            state["leg_t"] = t
            if not new_leg:
                return 0.0, 0.0
            d = 30.0 - w.x
            return (10.0 if d > 16.0 else 2.0), 0.0          # overshoot-limited: 2 units a leg near the waypoint
        c, w, sh, me = make(script=script)
        route = [{"x": 30.0, "z": 0.0, "y": 100.0, "floor_y": 100.0, "arrive": 4.0, "ramp": False}]
        r = M.follow_route(me, route, clock=c, wait=c.wait, log=sh.log)
        self.assertTrue(r["ok"], (r, sh.lines[-6:]))

    def test_far_from_the_waypoint_small_gains_still_trip(self):
        c, w, sh, me = make(script=lambda w, t: (0.4, 0.0))
        r = M.follow_route(me, [(0.0, 0.0), (200.0, 0.0)], clock=c, wait=c.wait, log=sh.log)
        self.assertFalse(r["ok"])
        self.assertTrue("no progress" in r["reason"] or "stuck" in r["reason"], r)


if __name__ == "__main__":
    unittest.main()
