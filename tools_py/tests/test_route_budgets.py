"""Sprint 5 Task 5 finish, slice (iv) -- the slice-(c) review findings on the engagement, and the controller's route
rulings:

  * the route file is a CLI option (`--route <path>`, default routes/frostfire_v2.json for --map frostfire; the old
    3c-derived frostfire.json stays loadable); arrival and the off-floor check use each leg's expected_floor_y, and a
    narrow leg (clearance < 15) arrives within 8 units;
  * I3: follower time and no-progress budgets for route legs and the close -- oscillation or sliding trips in bounded
    time;
  * I4: alarms re-ask once both clocks are confirmed; the stop rule needs both clocks running for the alarm's whole
    duration; a freeze (or freeze-attributed alarm) overlapping a fire window makes the round NO-DATA;
  * I5: a live spawn > 20 units from the route file's spawn is NO-DATA spawn-mismatch before walking;
  * I6: a reset to spawn at a round end is a round boundary, not a FAIL teleport;
  * minors: endgame_arg_problem names every mode; the close failure carries the swap hint; the cooperative victim
    oscillates only inside ENDGAME_UNITS.

unittest only; simulated time.
"""
import json
import math
import os
import tempfile
import unittest

from tools_py.parity import online_login_ours as L
from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import Clock, f2w, item, peek, tail
from tools_py.tests.test_engagement_ladder import WalkShell, WalkWorld

ROUTES = os.path.join(os.path.dirname(os.path.abspath(M.__file__)), "routes")


class RouteFileTest(unittest.TestCase):
    def test_frostfire_defaults_to_v2_and_v1_stays_loadable(self):
        self.assertEqual(os.path.basename(M.default_route_path("frostfire")), "frostfire_v2.json")
        self.assertIsNone(M.default_route_path("medley"))
        v1 = M.load_route_table(path=os.path.join(ROUTES, "frostfire.json"))
        self.assertEqual(len(v1["routes"]["A"]["waypoints"]), len(M.route_for(path=os.path.join(ROUTES, "frostfire.json"), mover="A")))

    def test_v2_structure(self):
        path = os.path.join(ROUTES, "frostfire_v2.json")
        for mover, other in (("A", "B"), ("B", "A")):
            wps = M.route_waypoints(M.load_route_table(path=path), mover)
            self.assertLess(math.dist((wps[0]["x"], wps[0]["y"], wps[0]["z"]), M.map_spawn(path=path, tag=mover)), 1.0)
            for p, q in zip(wps, wps[1:]):
                self.assertLessEqual(math.dist((p["x"], p["z"]), (q["x"], q["z"])), 60.0, (p, q))
                self.assertIsInstance(q["floor_y"], float, q)
        self.assertEqual(M.problems_route_file(path), [])

    def test_a_narrow_leg_arrives_within_8(self):
        path = os.path.join(ROUTES, "frostfire_v2.json")
        wps = M.route_waypoints(M.load_route_table(path=path), "A")
        for w in wps[1:]:
            want = M.ROUTE_ARRIVE_NARROW_UNITS if w["clearance"] < M.ROUTE_NARROW_CLEARANCE else M.ROUTE_ARRIVE_UNITS
            self.assertEqual(w["arrive"], want, w)
        self.assertEqual(M.ROUTE_ARRIVE_NARROW_UNITS, 8.0)

    def test_a_broken_route_file_is_named(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.addCleanup(os.remove, path)
        with open(path, "w") as f:
            json.dump({"version": 2, "spawns": {"A": {"x": 0, "y": 100, "z": 0}}, "routes": {"A": {"waypoints": [
                {"x": 0, "y": 100, "z": 0}, {"x": 90, "y": 100, "z": 0}]}}}, f)
        probs = " ".join(M.problems_route_file(path))
        self.assertIn("spawn B", probs)
        self.assertIn("expected_floor_y", probs)
        self.assertIn("spacing", probs)
        self.assertTrue(M.problems_route_file(os.path.join(ROUTES, "no_such.json")))


class FloorWorld(WalkWorld):
    """WalkWorld with a ground height: y(x, z) (a ramp), and a walk that can be scripted per leg."""

    def __init__(self, clock, x, z, facing, ground=lambda x, z: 100.0, script=None, **kw):
        self.ground, self.script, self.leg = ground, script, 0
        super().__init__(clock, x, z, facing, **kw)

    def tick(self, t):
        fwd = (0x80 - self.axes.get("ly", 0x80)) / 128.0
        if self.script is not None and fwd > 0.3:
            dx, dz = self.script(self, t)
            self.x += dx
            self.z += dz
            self.tail._line(peek(x=self.x, y=self.ground(self.x, self.z), z=self.z, facing=self.facing))
            return
        dev = self.axes.get("rx", 0x80) - 0x80
        if dev and abs(dev) > 56 and t - self.hold_t >= 0.3:
            self.facing = M.wrap_deg(self.facing + math.copysign(M.yaw_rate_deg_s(abs(dev)), dev) * self.gain * 0.25)
        if fwd > 0.3:
            nx = self.x + self.speed * 0.25 * fwd * math.cos(math.radians(self.facing))
            nz = self.z + self.speed * 0.25 * fwd * math.sin(math.radians(self.facing))
            if self.wall is None or not self.wall(nx, nz):
                self.x, self.z = nx, nz
        self.tail._line(peek(x=self.x, y=self.ground(self.x, self.z), z=self.z, facing=self.facing))


def make(x=0.0, z=0.0, facing=0.0, **kw):
    c = Clock(0.0)
    w = FloorWorld(c, x, z, facing, gain=1.0, **kw)
    c.wait(1.0)
    sh = WalkShell(w)
    return c, w, sh, M.Side("A", sh, w.tail)


class FollowerBudgetTest(unittest.TestCase):
    def test_an_oscillating_walker_trips_the_no_progress_budget(self):
        # review I3: legs alternately gaining and losing 8 units reset the per-leg stuck counter forever
        state = {"n": 0, "leg_t": None}

        def script(w, t):
            if state["leg_t"] is None or t - state["leg_t"] > 0.3:
                state["n"] += 1
            state["leg_t"] = t
            return (2.0 if state["n"] % 2 else -2.0), 0.0
        c, w, sh, me = make(script=script)
        t0 = c.t
        r = M.follow_route(me, [(0.0, 0.0), (200.0, 0.0)], clock=c, wait=c.wait, log=sh.log)
        self.assertFalse(r["ok"])
        self.assertIn("no progress", r["reason"])
        self.assertLessEqual(c.t - t0, M.ROUTE_NO_PROGRESS_S + 2 * (M.ROUTE_LEG_MAX_S + 4.0), (c.t - t0, r))

    def test_a_sliding_walker_trips_too(self):
        # slides sideways along a wall: moves every leg, never nearer
        c, w, sh, me = make(script=lambda w, t: (0.0, 3.0))
        r = M.follow_route(me, [(0.0, 0.0), (200.0, 0.0)], clock=c, wait=c.wait, log=sh.log)
        self.assertFalse(r["ok"])
        self.assertTrue("no progress" in r["reason"] or "stuck" in r["reason"], r)

    def test_the_close_has_the_same_budget(self):
        c, w, sh, me = make(script=lambda w, t: (0.0, 3.0))
        other_w = WalkWorld(c, 300.0, 0.0, 180.0)
        other = M.Side("B", WalkShell(other_w), other_w.tail)
        c.wait(0.5)
        t0 = c.t
        r = M.close_to(me, other, clock=c, wait=c.wait, log=sh.log)
        self.assertFalse(r["ok"])
        self.assertTrue("no progress" in r["reason"] or "stuck" in r["reason"], r)
        self.assertLessEqual(c.t - t0, M.ROUTE_NO_PROGRESS_S + 2 * (M.ROUTE_LEG_MAX_S + 4.0))

    def test_a_route_over_its_time_budget_fails(self):
        # R70: the raw formula (factor 3 over the measured 7.5 u/s) is generous enough that any walker fast enough
        # to avoid "stuck" also meets it -- what still cuts a route off MID-route (legs > 0, not the upfront NO-DATA
        # route-no-time check) is a tight round-clock cap.
        c, w, sh, me = make()
        route = [(55.0 * k, 0.0) for k in range(8)]
        r = M.follow_route(me, route, clock=c, wait=c.wait, log=sh.log, clock_remaining=130.0)
        self.assertFalse(r["ok"])
        self.assertIn("budget", r["reason"])
        self.assertGreater(r["legs"], 0)

    def test_arrival_needs_the_leg_floor(self):
        # a waypoint on the upper floor (y 142) is not reached by standing under it on the lower floor
        c, w, sh, me = make()
        route = [{"x": 0.0, "z": 0.0, "y": 100.0, "floor_y": 100.0, "arrive": 20.0, "ramp": False},
                 {"x": 40.0, "z": 0.0, "y": 142.0, "floor_y": 142.0, "arrive": 20.0, "ramp": False}]
        r = M.follow_route(me, route, clock=c, wait=c.wait, log=sh.log)
        self.assertFalse(r["ok"])
        self.assertIn("floor", r["reason"])

    def test_a_ramp_route_arrives(self):
        ground = lambda x, z: 100.0 + max(0.0, min(42.0, (x - 20.0) * 0.525))    # 100 -> 142 over x 20..100
        c, w, sh, me = make(ground=ground)
        route = [{"x": 0.0, "z": 0.0, "y": 100.0, "floor_y": 100.0, "arrive": 20.0, "ramp": False},
                 {"x": 20.0, "z": 0.0, "y": 100.0, "floor_y": 100.0, "arrive": 8.0, "ramp": False},
                 {"x": 60.0, "z": 0.0, "y": 121.0, "floor_y": 121.0, "arrive": 8.0, "ramp": True},
                 {"x": 100.0, "z": 0.0, "y": 142.0, "floor_y": 142.0, "arrive": 8.0, "ramp": True}]
        r = M.follow_route(me, route, clock=c, wait=c.wait, log=sh.log)
        self.assertTrue(r["ok"], (r, sh.lines[-5:]))
        self.assertLessEqual(math.dist((w.x, w.z), (100.0, 0.0)), 8.0)


class SpawnAndRoundResetTest(unittest.TestCase):
    def test_spawn_mismatch_is_no_data_before_walking(self):
        c = Clock(0.0)
        wa, wb = WalkWorld(c, 30.0, 0.0, 0.0), WalkWorld(c, 300.0, 0.0, 180.0)
        c.wait(1.0)
        sa, sb = WalkShell(wa), WalkShell(wb)
        sides = {"A": M.Side("A", sa, wa.tail), "B": M.Side("B", sb, wb.tail)}
        lines = []
        out = M.endgame_route(sides, M.Duel(), None, lines.append, "nomap", mover="A", route=[(30.0, 0.0), (300.0, 0.0)],
                              fight_s=5.0, clock=c, wait=c.wait,
                              spawns={"A": (0.0, 100.0, 0.0), "B": (300.0, 100.0, 0.0)})
        self.assertTrue(out["stop_reason"].startswith("NO-DATA spawn-mismatch side=A"), out["stop_reason"])
        self.assertEqual([p for p in sa.pads if p[2]], [])                 # nobody walked

    def test_a_reset_to_spawn_after_a_round_step_is_a_round_boundary(self):
        c = Clock(0.0)
        wa = WalkWorld(c, 0.0, 0.0, 0.0)
        c.wait(1.0)
        rt = tail(c, "A")
        rows = [(10.0 + 0.25 * i, 100.0 + 0.25 * i, 100.0, 0.0, 1) for i in range(20)] + [(15.0, 0.5, 100.0, 0.0, 1)]
        hit = M.teleport_step(rows, 10.0, 15.0)
        self.assertIsNotNone(hit)
        steps = [9.0]
        self.assertTrue(M.is_round_reset(hit, rows, spawn=(0.0, 100.0, 0.0), round_steps=steps))
        self.assertFalse(M.is_round_reset(hit, rows, spawn=(0.0, 100.0, 0.0), round_steps=[]))
        self.assertFalse(M.is_round_reset(hit, rows, spawn=(60.0, 100.0, 0.0), round_steps=steps))


class AlarmStopRuleTest(unittest.TestCase):
    """spec §5.1: stop only on an alarm with both round clocks running for its whole duration; re-ask when an alarm
    that opened unconfirmed becomes confirmed."""

    def setUp(self):
        self.c = Clock(0.0)
        self.tails = {g: tail(self.c, g) for g in "AB"}
        self.lines = []
        self.w = M.StarvationWatch(self.tails, self.lines.append, clock=self.c)
        self.rt = {"A": 10.0, "B": 10.0}
        self.n = {"A": 0, "B": 0}

    def step(self, sec, frozen=(), idle=None, no_clock=()):
        idle = idle or {}
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
                self.tails[g]._line(peek(round_time=None if g in no_clock else self.rt[g], lag=1 if v >= 4501 else 0))
            self.w.check()

    def test_an_alarm_that_opened_unconfirmed_is_asked_once_confirmed(self):
        self.step(4.0, no_clock=("B",))
        self.step(1.0, idle={"B": 4200}, no_clock=("B",))            # B alarms; B's clock unread -> not asked
        self.assertFalse(self.w.take_request("A"))
        self.step(1.0, idle={"B": 4300})                             # B's clock rows arrive: re-ask
        self.assertTrue(self.w.take_request("A"), self.lines)
        self.assertTrue(any("re-asked" in m for m in self.lines), self.lines)

    def test_no_stop_when_a_clock_paused_during_the_alarm(self):
        self.step(4.0)
        self.step(1.0, idle={"B": 4200})
        self.assertTrue(self.w.take_request("A"))
        self.w.moved("A", self.c.t)
        self.step(1.5, idle={"B": 4400}, frozen=("A",))              # A's clock stands still 1.5 s after the move
        self.step(3.0, idle={"B": 4600})
        self.assertIsNone(self.w.stop_reason, self.lines)

    def test_negative_control_both_clocks_running_stops(self):
        self.step(4.0)
        self.step(1.0, idle={"B": 4200})
        self.assertTrue(self.w.take_request("A"))
        self.w.moved("A", self.c.t)
        self.step(4.0, idle={"B": 4600})
        self.assertIn("not cleared", self.w.stop_reason or "")


class FireWindowFreezeTest(unittest.TestCase):
    def test_a_freeze_overlapping_a_burst_is_no_data(self):
        from tools_py.tests.test_engagement_ladder import WalkShell as WS, WalkWorld as WW
        c = Clock(0.0)
        shooter, victim = WW(c, 0.0, 0.0, 0.0), WW(c, 25.0, 0.0, 180.0)
        rt = {"v": 10.0}

        def clock_rows(t):
            burst = any("R1" in p[1] for p in ssh.pads)
            if not burst:
                rt["v"] += 0.15
            victim.tail._line(peek(x=victim.x, y=100.0, z=victim.z, facing=victim.facing, round_time=rt["v"]))
        ssh = WS(shooter)
        c.hooks.append(clock_rows)
        c.wait(1.0)
        sides = {"A": M.Side("A", ssh, shooter.tail), "B": M.Side("B", WS(victim), victim.tail)}
        lines = []
        out = M.endgame_route(sides, M.Duel(), None, lines.append, "nomap", mover="A", route=[], fight_s=8.0,
                              clock=c, wait=c.wait)
        self.assertTrue((out["stop_reason"] or "").startswith("NO-DATA freeze"), (out["stop_reason"], lines))


class MinorsTest(unittest.TestCase):
    def test_endgame_arg_problem_names_every_mode(self):
        class A:
            endgame, control_round = "route", True
        msg = M.endgame_arg_problem(A())
        for mode in ("route", "cooperative", "converge"):
            self.assertIn(mode, msg)

    def test_close_failure_carries_the_swap_hint(self):
        c = Clock(0.0)
        wa, wb = WalkWorld(c, 0.0, 0.0, 0.0), FloorWorld(c, 200.0, 0.0, 180.0, ground=lambda x, z: 160.0)
        c.wait(1.0)
        sides = {"A": M.Side("A", WalkShell(wa), wa.tail), "B": M.Side("B", WalkShell(wb), wb.tail)}
        # B stands 60 units above A: the close fails off-floor
        out = M.endgame_route(sides, M.Duel(), None, lambda m: None, "nomap", mover="A", route=[], fight_s=3.0,
                              clock=c, wait=c.wait)
        self.assertIn("--mover B", out["stop_reason"] or "")

    def test_cooperative_victim_oscillates_only_inside_endgame_units(self):
        self.assertEqual(M.ENDGAME_UNITS, 150.0)
        self.assertFalse(M.victim_should_oscillate(None))
        self.assertFalse(M.victim_should_oscillate(151.0))
        self.assertTrue(M.victim_should_oscillate(150.0))


if __name__ == "__main__":
    unittest.main()
