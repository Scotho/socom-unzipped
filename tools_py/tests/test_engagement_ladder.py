"""Sprint 5 Task 5 (c) -- the engagement: routes, the endgame modes, Step 1's feed legs, the LADDER line, and the
simulation's two-sided starvation model and two-floor terrain (sim_walk_to_b).

unittest only; every loop runs in simulated time (no sleeps, no game).
"""
import math
import os
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
class LadderLineTest(unittest.TestCase):
    def test_exact_format(self):
        line = M.ladder_line(rung=2, controllable=("yes", "yes"), contact_rows=23, rows_read=2406,
                             damage="no", kill="no", starvation_alarms=1, alarms_cleared=1,
                             max_idle_ms=(1547, 4210), lagflag_rows=(2759, 2733))
        self.assertEqual(line, "LADDER rung=2 controllable=yes,yes contact_s=NO-DATA contact_rows=23 sampler_s=NO-DATA "
                               "rows_read=2406 damage=no "
                               "kill=no starvation_alarms=1 alarms_cleared=1 max_idle_ms=1547,4210 "
                               "lagflag_rows=2759,2733")

    def test_zero_row_fields_are_no_data(self):
        line = M.ladder_line(rung=1, controllable=("yes", "yes"), contact_rows=None, rows_read=0,
                             damage="unarmed", kill="no", starvation_alarms=None, alarms_cleared=None,
                             max_idle_ms=(None, 900), lagflag_rows=(0, 12))
        self.assertIn("contact_rows=NO-DATA sampler_s=NO-DATA rows_read=NO-DATA", line)
        self.assertIn("starvation_alarms=NO-DATA alarms_cleared=NO-DATA", line)
        self.assertIn("max_idle_ms=NO-DATA,900 lagflag_rows=NO-DATA,12", line)

    def test_rung(self):
        # spec §5.1: the rung reads score_contact's `ok` (band, >= 5.0 s over >= 10 rows), not a row count
        self.assertEqual(M.ladder_rung(("yes", "yes"), True, "yes"), 3)
        self.assertEqual(M.ladder_rung(("yes", "yes"), True, "no"), 2)
        self.assertEqual(M.ladder_rung(("yes", "yes"), False, "yes"), 1)
        self.assertEqual(M.ladder_rung(("yes", "NO-DATA"), True, "yes"), 0)
        self.assertEqual(M.ladder_rung(("yes", "yes"), None, "no"), 1)


class DamageVerdictTest(unittest.TestCase):
    """Spec §5 Goal 5(d): the victim's +0x1044 drops below 1.0 during contact, the killer's R1 in the
    preceding 3 s, no victim y drop > 20 in the preceding 2 s."""

    def setup(self, drop_t=110.0, r1=(108.5,), fall=False, far=False):
        victim_rows, shooter_rows = [], []
        for i in range(80):
            t = 100.0 + 0.25 * i
            vy = 100.0 if not (fall and drop_t - 1.5 <= t < drop_t) else 130.0
            if fall and t < drop_t - 1.5:
                vy = 130.0
            victim_rows.append((t, 0.0, vy, 0.0, 1))
            shooter_rows.append((t, 60.0 if far else 15.0, 100.0, 0.0, 2))    # far: outside the 45-unit band
        hist = [(100.0, f2w(1.0), 1), (drop_t, f2w(0.8), 1)]
        return hist, victim_rows, shooter_rows, list(r1)

    def test_drop_in_contact_after_a_burst_is_damage(self):
        self.assertEqual(M.damage_verdict(*self.setup()), "yes")

    def test_no_burst_in_the_3s_before_is_not_damage(self):
        self.assertEqual(M.damage_verdict(*self.setup(r1=(105.0,))), "no")

    def test_a_fall_is_not_damage(self):
        self.assertEqual(M.damage_verdict(*self.setup(fall=True)), "no")

    def test_out_of_contact_is_not_damage(self):
        self.assertEqual(M.damage_verdict(*self.setup(far=True)), "no")

    def test_unarmed_and_zero_reads(self):
        self.assertEqual(M.damage_verdict(None, [], [], []), "unarmed")
        self.assertEqual(M.damage_verdict([], [], [], []), vc.NO_DATA)


class EndgameArgsTest(unittest.TestCase):
    class A:
        endgame = "cooperative"
        control_round = False
        converge = False
        until_kill = True

    def test_cooperative_with_control_round_is_refused(self):
        a = self.A()
        a.control_round = True
        self.assertIn("--control-round", M.endgame_arg_problem(a))
        self.assertIsNone(M.endgame_arg_problem(self.A()))

    def test_preconditions_name_the_netidle_slot_ng_block_and_round_clock(self):
        env = {"PS2X_CALL_TRACE": "0x553dc0:MoveScale", "PS2X_PEEK": "*0x408c58:64"}
        probs = " ".join(M.endgame_preconditions(env))
        self.assertIn("NetIdle", probs)
        self.assertIn("*0x437ce8:64", probs)
        self.assertIn("0x4365c0", probs)
        ok = {"PS2X_CALL_TRACE": "0x553dc0:MoveScale,0x30cd80:NetIdle",
              "PS2X_PEEK": "*0x408c58:64,*0x437ce8:64,*0x437ce8+0x100:21,0x4365c0:1"}
        self.assertEqual(M.endgame_preconditions(ok), [])


# ---------------------------------------------------------------------------------------------
class SimStarvationModelTest(unittest.TestCase):
    """sim_walk_to_b.Net: per-side idle reset only by the OTHER side's traffic."""

    def test_scale_formula_and_lag_flag(self):
        self.assertEqual(S.Net.scale(0), 1.0)
        self.assertEqual(S.Net.scale(5500), 1.0)
        self.assertAlmostEqual(S.Net.scale(6000), 0.5)
        self.assertEqual(S.Net.scale(6500), 0.0)
        self.assertEqual(S.Net.scale(90000), 0.0)
        self.assertEqual(S.Net.lagflag(4500), 0)
        self.assertEqual(S.Net.lagflag(4501), 1)

    def test_only_the_other_sides_translation_resets(self):
        n = S.Net(t0=0.0)
        n.tick("A", 1.0, translated=True)
        self.assertEqual(n.idle_ms("A", 1.0), 1000)      # A's own traffic does not reset A
        self.assertEqual(n.idle_ms("B", 1.0), 0)         # it resets B
        self.assertEqual(n.idle_ms("B", 3.5), 2500)

    def test_rotation_feeds_iff_flag(self):
        for flag, want in ((False, 2000), (True, 0)):
            n = S.Net(rotation_feeds=flag, t0=0.0)
            n.tick("A", 2.0, rotated=True)
            self.assertEqual(n.idle_ms("B", 2.0), want)

    def test_firing_feeds_iff_flag(self):
        for flag, want in ((False, 2000), (True, 0)):
            n = S.Net(firing_feeds=flag, t0=0.0)
            n.tick("A", 2.0, fired=True)
            self.assertEqual(n.idle_ms("B", 2.0), want)

    def test_flags_default_false(self):
        n = S.Net()
        self.assertFalse(n.rotation_feeds)
        self.assertFalse(n.firing_feeds)

    def test_max_idle_is_recorded_per_side(self):
        n = S.Net(t0=0.0)
        n.tick("A", 1.0)
        n.idle_ms("B", 6.0)
        n.tick("A", 6.0, translated=True)
        n.idle_ms("B", 6.25)
        self.assertEqual(n.max_idle["B"], 6000)


class SimTerrainTest(unittest.TestCase):
    def setUp(self):
        self.t = S.TwoFloorTerrain()

    def test_lower_walker_passes_under_the_ledge(self):
        ok, floor = self.t.step("lower", 900.0, 650.0, 700.0, 650.0)
        self.assertTrue(ok)
        self.assertEqual(floor, "lower")
        self.assertEqual(self.t.y(floor, 700.0, 650.0), 100.0)

    def test_ramp_from_the_bottom_to_the_top(self):
        ok, floor = self.t.step("lower", 710.0, 470.0, 710.0, 490.0)
        self.assertEqual((ok, floor), (True, "ramp"))
        self.assertAlmostEqual(self.t.y(floor, 710.0, 540.0), 121.0)
        ok, floor = self.t.step("ramp", 710.0, 595.0, 710.0, 605.0)
        self.assertEqual((ok, floor), (True, "upper"))
        self.assertEqual(self.t.y(floor, 710.0, 605.0), 142.0)

    def test_the_ramp_is_solid_from_the_side_and_the_ledge_has_railings(self):
        self.assertFalse(self.t.step("lower", 800.0, 540.0, 740.0, 540.0)[0])
        self.assertFalse(self.t.step("ramp", 745.0, 540.0, 760.0, 540.0)[0])
        self.assertFalse(self.t.step("upper", 700.0, 770.0, 700.0, 800.0)[0])
        self.assertTrue(self.t.step("upper", 700.0, 610.0, 700.0, 590.0)[0])     # back down the ramp

    def test_lower_walker_under_the_ledge_cannot_enter_the_ramp_from_its_top(self):
        self.assertFalse(self.t.step("lower", 700.0, 610.0, 700.0, 590.0)[0])


class RouteTableTest(unittest.TestCase):
    """The default engagement's routes are DATA (tools_py/parity/routes/frostfire.json), every waypoint citing the
    launch 3c actor row it was mined from (logs/run_[AB]_20260913_115809.log): A spawns on the lower floor, B on the
    upper; A climbed at ~(686, 938), B descended via ~(652, 1230) (Amendment A)."""

    def test_frostfire_spawns(self):
        self.assertLess(math.dist(M.map_spawn("frostfire", "A"), (795.7, 100.0, 613.6)), 2.0)
        self.assertLess(math.dist(M.map_spawn("Frostfire", "B"), (535.7, 142.9, 1253.6)), 2.0)

    # routes/frostfire.json is the OLD 3c-derived route (still loadable; --map frostfire now defaults to frostfire_v2.json,
    # tested in test_route_budgets): these two checks are specific to it
    V1 = os.path.join(M.ROUTES_DIR, "frostfire.json")

    def test_the_a_route_leaves_a_spawn_and_climbs_the_ramp(self):
        route = [(w["x"], w["z"]) for w in M.route_for(mover="A", path=self.V1)]
        self.assertLess(math.dist(route[0], (795.7, 613.6)), 10.0)
        self.assertLess(min(math.dist(p, (686.0, 938.0)) for p in route), 15.0)
        for p, q in zip(route, route[1:]):
            self.assertLessEqual(math.dist(p, q), M.ROUTE_MAX_SPACING_UNITS, (p, q))

    def test_the_b_route_leaves_b_spawn_and_descends_near_652_1230(self):
        route = [(w["x"], w["z"]) for w in M.route_for(mover="B", path=self.V1)]
        self.assertLess(math.dist(route[0], (535.7, 1253.6)), 10.0)
        self.assertLess(min(math.dist(p, (652.0, 1230.0)) for p in route), 15.0)
        for p, q in zip(route, route[1:]):
            self.assertLessEqual(math.dist(p, q), M.ROUTE_MAX_SPACING_UNITS, (p, q))

    def test_every_waypoint_cites_its_source_row_and_the_floors_match(self):
        table = M.load_route_table("frostfire")
        self.assertIn("run_A_20260913_115809.log", table["source"]["A"])
        for side, first_y, last_y in (("A", 100.0, 142.0), ("B", 142.0, 100.0)):
            wps = table["routes"][side]["waypoints"]
            self.assertTrue(all("row_t" in w and "y" in w for w in wps))
            self.assertLess(abs(wps[0]["y"] - first_y), 2.0)
            self.assertLess(abs(wps[-1]["y"] - last_y), 2.0)

    def test_a_map_without_a_table_has_no_route(self):
        self.assertIsNone(M.route_for("medley", "A"))
        self.assertIsNone(M.map_spawn("medley", "A"))


class EngagementBandTest(unittest.TestCase):
    def test_aim_tolerance_is_min_6_and_0_8_atan_3_4_over_d(self):
        self.assertEqual(M.aim_tol_deg(10.0), M.AIM_TOL_DEG)
        self.assertAlmostEqual(M.aim_tol_deg(45.0), 0.8 * math.degrees(math.atan(3.4 / 45.0)), places=6)
        self.assertLess(M.aim_tol_deg(45.0), M.aim_tol_deg(35.0))

    def test_the_close_stops_inside_the_band(self):
        self.assertLess(M.ENGAGE_BAND_STOP_UNITS, M.ENGAGE_BAND_3D_UNITS)
        self.assertEqual(M.ENGAGE_BAND_3D_UNITS, 45.0)


class WalkWorld:
    """One player in simulated time: rx turns (table x gain, dead zone, lead, no matrix lag), W walks along the facing
    at `speed` unless `wall(x, z)`; 4 Hz actor rows with the matrix; the camera record is garbage."""

    def __init__(self, clock, x, z, facing, gain=0.7, speed=40.0, wall=None, teleport_at=None):
        self.clock, self.x, self.z, self.facing = clock, x, z, facing
        self.gain, self.speed, self.wall, self.teleport_at = gain, speed, wall, teleport_at
        self.axes, self.hold_t = {}, None
        self.tail = tail(clock)
        clock.hooks.append(self.tick)
        self.tick(clock.t)

    def set_axes(self, axes):
        rx = axes.get("rx", 0x80)
        if rx != 0x80 and self.hold_t is None:
            self.hold_t = self.clock.t
        if rx == 0x80:
            self.hold_t = None
        self.axes = axes

    def tick(self, t):
        dev = self.axes.get("rx", 0x80) - 0x80
        if dev and abs(dev) > 56 and t - self.hold_t >= 0.3:
            self.facing = M.wrap_deg(self.facing + math.copysign(M.yaw_rate_deg_s(abs(dev)), dev) * self.gain * 0.25)
        fwd = (0x80 - self.axes.get("ly", 0x80)) / 128.0
        if fwd > 0.3:
            if self.teleport_at is not None and t >= self.teleport_at:
                self.x += 120.0
                self.teleport_at = None
            nx = self.x + self.speed * 0.25 * fwd * math.cos(math.radians(self.facing))
            nz = self.z + self.speed * 0.25 * fwd * math.sin(math.radians(self.facing))
            if self.wall is None or not self.wall(nx, nz):
                self.x, self.z = nx, nz
        self.tail._line(peek(x=self.x, y=100.0, z=self.z, facing=self.facing).replace(
            item(0x416054, [f2w(self.x - 20.0), f2w(120.0), f2w(self.z)]),
            item(0x416054, [f2w(-9999.0), f2w(0.0), f2w(9999.0)])))


class WalkShell:
    def __init__(self, world):
        self.world, self.lines, self.pads = world, [], []

    def log(self, m):
        self.lines.append(m)

    def pad(self, seconds, buttons=(), sticks=(), axes=None, abort=None):
        ax = L.pad_axes(sticks, axes)
        self.pads.append((self.world.clock.t, tuple(buttons), dict(ax), seconds))
        self.world.set_axes(ax)
        self.world.clock.wait(seconds)
        self.world.set_axes({})


class FollowRouteTest(unittest.TestCase):
    ROUTE = [(0.0, 0.0), (80.0, 10.0), (120.0, 90.0), (60.0, 160.0)]

    def run_route(self, **kw):
        c = Clock(0.0)
        w = WalkWorld(c, 0.0, 0.0, -120.0, **kw)
        c.wait(1.0)
        sh = WalkShell(w)
        me = M.Side("A", sh, w.tail)
        return w, sh, me, c

    def test_walks_every_waypoint_and_arrives(self):
        w, sh, me, c = self.run_route()
        r = M.follow_route(me, self.ROUTE, clock=c, wait=c.wait, log=sh.log)
        self.assertTrue(r["ok"], (r, sh.lines))
        self.assertEqual(r["reason"], "arrived")
        self.assertLessEqual(math.dist((w.x, w.z), self.ROUTE[-1]), M.ROUTE_ARRIVE_UNITS)
        self.assertTrue(all("R1" not in p[1] for p in sh.pads))

    def test_a_wall_is_a_failed_route_not_a_hang(self):
        w, sh, me, c = self.run_route(wall=lambda x, z: x > 100.0)
        r = M.follow_route(me, self.ROUTE, clock=c, wait=c.wait, log=sh.log)
        self.assertFalse(r["ok"])
        self.assertTrue(r["reason"].startswith("stuck"), r)

    def test_a_teleport_during_a_walk_leg_aborts(self):
        w, sh, me, c = self.run_route(teleport_at=4.0)
        with self.assertRaises(M.TeleportAbort) as cm:
            M.follow_route(me, self.ROUTE, clock=c, wait=c.wait, log=sh.log)
        self.assertEqual(cm.exception.during, "walk")

    def test_the_route_never_reads_the_camera(self):
        w, sh, me, c = self.run_route()

        class NoCam:
            def __init__(self, t):
                self._t = t

            def __getattr__(self, name):
                if name in ("latest", "ingame", "window", "last_before", "rows"):
                    raise AssertionError(name)
                return getattr(self._t, name)
        me.tail = NoCam(w.tail)
        self.assertTrue(M.follow_route(me, self.ROUTE, clock=c, wait=c.wait, log=sh.log)["ok"])


class SimKeepaliveModelTest(unittest.TestCase):
    def test_keepalive_resets_the_other_side_without_traffic(self):
        n = S.Net(t0=0.0, keepalive=True)
        n.tick("A", 3.0)
        self.assertEqual(n.idle_ms("B", 3.0), 0)
        n2 = S.Net(t0=0.0)
        n2.tick("A", 3.0)
        self.assertEqual(n2.idle_ms("B", 3.0), 3000)


if __name__ == "__main__":
    unittest.main()
