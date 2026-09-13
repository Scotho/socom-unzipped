"""Sprint 5 Task 5 (b) -- partial-deflection aim and the teleport detector:

  * `Shell.pad(..., axes=)`: explicit 0-255 axes through the pad file;
  * the actor-matrix heading (research/22 §4) and `aim_yaw`: closed loop to AIM_TOL_DEG in <= AIM_MAX_ITER holds,
    the heading read at rest (2 unchanged rows after any rx) or 0.5 s after each short pulse -- never the camera;
  * the teleport detector: an actor row step > 30 units during an aim pulse or a walk leg aborts the attempt.

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
class PadAxesTest(unittest.TestCase):
    def shell(self):
        sh = L.Shell.__new__(L.Shell)
        fd, path = tempfile.mkstemp(prefix="pad_", suffix=".txt")
        os.close(fd)
        sh.pad_file = path
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return sh, path

    def test_explicit_axes_are_written_and_released(self):
        sh, path = self.shell()
        seen = []
        orig = L.write_pad_file

        def spy(p, buttons=(), axes=None):
            orig(p, buttons, axes)
            seen.append(open(p).read().strip())
        L.write_pad_file = spy
        try:
            sh.pad(0.0, axes={"rx": 192, "lx": 64})
        finally:
            L.write_pad_file = orig
        self.assertEqual(seen[0], "b=0000 rx=192 ry=128 lx=64 ly=128")
        self.assertEqual(seen[-1], "b=0000 rx=128 ry=128 lx=128 ly=128")

    def test_axes_override_a_stick_on_the_same_axis_and_buttons_combine(self):
        self.assertEqual(L.pad_axes(sticks=["L", "W"], axes={"rx": 200}),
                         {"rx": 200, "ly": 0})
        sh, path = self.shell()
        orig, seen = L.write_pad_file, []
        L.write_pad_file = lambda p, buttons=(), axes=None: seen.append((tuple(buttons), dict(axes or {})))
        try:
            sh.pad(0.0, buttons=["R1"], sticks=["W"], axes={"lx": 100})
        finally:
            L.write_pad_file = orig
        self.assertEqual(seen[0], (("R1",), {"ly": 0, "lx": 100}))

    def test_out_of_range_axis_is_refused(self):
        for bad in ({"rx": 256}, {"lx": -1}, {"zz": 10}, {"ry": 1.5}):
            with self.assertRaises(ValueError):
                L.pad_axes(axes=bad)

    def test_abort_still_releases_early(self):
        sh, path = self.shell()
        ev = threading.Event()
        ev.set()
        sh.pad(30.0, axes={"rx": 200}, abort=ev)       # returns at once
        self.assertEqual(open(path).read().strip(), "b=0000 rx=128 ry=128 lx=128 ly=128")


# ---------------------------------------------------------------------------------------------
class HeadingFieldTest(unittest.TestCase):
    def test_matrix_heading_round_trips(self):
        for f in (-179.0, -90.0, 0.0, 33.3, 90.0, 150.0):
            block = [M.ACTOR_VTABLE] + [0] * 63
            block[32:48] = matrix_words(f)
            self.assertAlmostEqual(M.heading_from_matrix(block), f, places=3)

    def test_short_block_has_no_heading(self):
        self.assertIsNone(M.heading_from_matrix([M.ACTOR_VTABLE] + [0] * 20))
        self.assertIsNone(M.heading_from_matrix([M.ACTOR_VTABLE] + [0] * 63))   # all-zero matrix

    def test_tail_records_heading_lag_flag_round_time_and_netidle(self):
        c = Clock()
        t = tail(c)
        t._line(peek(x=10.0, z=20.0, facing=45.0, round_time=12.5, lag=1))
        t._line("[call] 400.0s NetIdle #7 a0=0x45a0c0 ra=0x594f88 f12=0.0")
        t._line("[ret] NetIdle #7 v0=0x1194 f0=0.6")
        self.assertAlmostEqual(t.heading_rows[-1][1], 45.0, places=3)
        self.assertEqual(t.heading_rows[-1][2:], (10.0, 20.0))
        self.assertEqual(t.lag_rows, [(c.t, 1)])
        self.assertEqual(t.round_time_rows, [(c.t, 12.5)])
        self.assertEqual(t.rets["NetIdle"][-1], (c.t, 7, 4500))


# ---------------------------------------------------------------------------------------------
class YawTableTest(unittest.TestCase):
    def test_dead_zone_and_measured_points(self):
        self.assertEqual(M.yaw_rate_deg_s(0), 0.0)
        self.assertEqual(M.yaw_rate_deg_s(48), 0.0)
        self.assertAlmostEqual(M.yaw_rate_deg_s(96), 100.7, places=1)
        self.assertAlmostEqual(M.yaw_rate_deg_s(127), 128.1, places=1)

    def test_strictly_increasing_above_the_dead_zone(self):
        rates = [M.yaw_rate_deg_s(d) for d in range(49, 128)]
        self.assertTrue(all(b > a for a, b in zip(rates, rates[1:])))

    def test_plan_never_commands_the_dead_zone_and_signs_by_error(self):
        for err in (-170.0, -40.0, -7.0, 6.5, 12.0, 60.0, 175.0):
            rx, secs, _ = M.aim_plan(err, gain=1.0)
            dev = rx - vc.PAD_NEUTRAL
            self.assertGreater(abs(dev), M.YAW_DEAD_ZONE)
            self.assertTrue(0 <= rx <= 255)
            self.assertEqual(dev > 0, err > 0)             # rx right sweeps positive (LOOK_RIGHT_SIGN)
            self.assertLessEqual(secs, M.AIM_HOLD_MAX_S + 1e-9)
            self.assertGreater(secs, M.AIM_LEAD_S)

    def test_a_low_gain_asks_for_more(self):
        # the third value is the sweep the TABLE predicts for the hold (gain 1): |err| / gain
        _, _, c1 = M.aim_plan(20.0, gain=1.0)
        _, _, c2 = M.aim_plan(20.0, gain=0.5)
        self.assertAlmostEqual(c1, 20.0, delta=1.0)
        self.assertAlmostEqual(c2, 40.0, delta=2.0)


class AimWorld:
    """A stationary player in simulated time: the pad's rx turns it through its OWN yaw response -- the
    harness's table times `gain`, a dead zone of `dz`, a lead of `lead` s -- and its matrix heading
    lags the true facing (halving each row). 4 Hz actor rows carry the matrix; the camera record is
    a lie, so reading it would be caught."""

    def __init__(self, clock, facing=0.0, gain=0.6, dz=56, lead=0.3, responds=True, teleport_at=None, lag=True):
        self.clock, self.facing, self.gain, self.dz, self.lead = clock, facing, gain, dz, lead
        self.lag = lag
        self.responds, self.teleport_at = responds, teleport_at
        self.mf = facing
        self.x, self.z = 0.0, 0.0
        self.rx, self.hold_t = 0x80, None
        self.tail = tail(clock)
        self.truth = []
        clock.hooks.append(self.tick)
        self.tick(clock.t)

    def set_rx(self, rx):
        if rx != self.rx:
            self.hold_t = self.clock.t if rx != 0x80 else None
        self.rx = rx

    def tick(self, t):
        dev = self.rx - 0x80
        if self.responds and dev and abs(dev) > self.dz and t - self.hold_t >= self.lead:
            self.facing = M.wrap_deg(self.facing + math.copysign(M.yaw_rate_deg_s(abs(dev)), dev)
                                     * self.gain * 0.25)
        if self.teleport_at is not None and dev and t >= self.teleport_at:
            self.x += 100.0
            self.teleport_at = None
        d = M.wrap_deg(self.facing - self.mf)
        self.mf = self.facing if (abs(d) < 0.5 or not self.lag) else M.wrap_deg(self.mf + d * 0.5)
        self.truth.append((t, self.facing, self.mf))
        self.tail._line(peek(x=self.x, z=self.z, facing=self.mf).replace(
            item(0x416054, [f2w(self.x - 20.0), f2w(70.0), f2w(self.z)]),
            item(0x416054, [f2w(9999.0), f2w(0.0), f2w(-9999.0)])))


class AimShell:
    def __init__(self, world):
        self.world, self.lines, self.pads = world, [], []

    def log(self, m):
        self.lines.append(m)

    def pad(self, seconds, buttons=(), sticks=(), axes=None, abort=None):
        ax = L.pad_axes(sticks, axes)
        self.pads.append((self.world.clock.t, tuple(buttons), dict(ax), seconds))
        self.world.set_rx(ax.get("rx", 0x80))
        self.world.clock.wait(seconds)
        self.world.set_rx(0x80)


class NoCameraTail:
    """Wraps a RunLogTail and fails the test on any camera-record read."""

    def __init__(self, t):
        self._t = t

    def __getattr__(self, name):
        if name in ("latest", "ingame", "window", "last_before", "rows"):
            raise AssertionError(f"aim_yaw read the camera record via {name}")
        return getattr(self._t, name)


class AimYawTest(unittest.TestCase):
    def run_aim(self, target_xz, **kw):
        c = Clock()
        w = AimWorld(c, **kw)
        c.wait(1.0)
        sh = AimShell(w)
        me = M.Side("A", sh, w.tail)
        # the at-rest loop at the brief's fixed 6 deg (aim_yaw's defaults became pulse reads and the §5.1 tolerance)
        before, after = M.aim_yaw(me, target_xz, NoCameraTail(w.tail), sh, clock=c, wait=c.wait, read="rest",
                                  tol=M.AIM_TOL_DEG)
        return w, sh, me, before, after

    def test_converges_within_tolerance_despite_wrong_gain_and_dead_zone(self):
        for target, facing in (((100.0, 0.0), 70.0), ((0.0, 100.0), -30.0), ((-100.0, -5.0), 10.0),
                               ((50.0, 50.0), 43.0)):
            w, sh, me, before, after = self.run_aim(target, facing=facing)
            self.assertIsNotNone(after)
            self.assertLessEqual(abs(after), M.AIM_TOL_DEG, (target, facing, before, after, sh.lines))
            rx_holds = [p for p in sh.pads if p[2].get("rx", 0x80) != 0x80]
            self.assertLessEqual(len(rx_holds), M.AIM_MAX_ITER)
            want = math.degrees(math.atan2(target[1], target[0]))
            self.assertLessEqual(abs(M.wrap_deg(want - w.facing)), M.AIM_TOL_DEG + 0.5)

    def test_already_aimed_makes_no_hold(self):
        w, sh, me, before, after = self.run_aim((100.0, 0.0), facing=2.0)
        self.assertEqual([p for p in sh.pads if p[2].get("rx", 0x80) != 0x80], [])
        self.assertAlmostEqual(before, -2.0, places=2)
        self.assertEqual(before, after)

    def test_heading_is_read_only_after_two_unchanged_rows_following_the_rx(self):
        w, sh, me, before, after = self.run_aim((0.0, 100.0), facing=-40.0)
        reads = me.aims[-1]["reads"]
        self.assertGreaterEqual(len(reads), 2)
        for r in reads:
            if r["after_rx"] is not None:
                self.assertGreaterEqual(r["t"] - r["after_rx"], 2 * 0.25 - 1e-6, r)
            # the heading read is the settled matrix == the true facing at that moment
            truth = [f for (t, f, mf) in w.truth if t <= r["t"]][-1]
            self.assertAlmostEqual(M.wrap_deg(r["heading"] - truth), 0.0, delta=0.6)

    def test_a_player_that_does_not_turn_stops_after_the_iteration_cap(self):
        w, sh, me, before, after = self.run_aim((0.0, 100.0), facing=0.0, responds=False)
        self.assertEqual(len([p for p in sh.pads if p[2].get("rx", 0x80) != 0x80]), M.AIM_MAX_ITER)
        self.assertGreater(abs(after), M.AIM_TOL_DEG)

    def test_teleport_during_a_hold_aborts_the_attempt(self):
        # the owner-requested review: an actor row step > 30 units during an aim pulse ABORTS (research/22 §3.1's SP
        # teleports reached 380 units per row inside rx holds; online partial deflection is untested)
        c = Clock()
        w = AimWorld(c, facing=-60.0, teleport_at=c.t + 1.5)
        c.wait(1.0)
        sh = AimShell(w)
        me = M.Side("A", sh, w.tail)
        with self.assertRaises(M.TeleportAbort) as cm:
            M.aim_yaw(me, (0.0, 100.0), w.tail, sh, clock=c, wait=c.wait, read="rest", tol=M.AIM_TOL_DEG)
        self.assertEqual((cm.exception.tag, cm.exception.during), ("A", "aim"))
        self.assertGreater(cm.exception.step, M.TELEPORT_STEP_UNITS)
        self.assertEqual(me.aim_teleports, 1)
        self.assertTrue(any("TELEPORT" in m for m in sh.lines), sh.lines)

    def run_pulse(self, target, facing, lag):
        c = Clock()
        w = AimWorld(c, facing=facing, lag=lag)
        c.wait(1.0)
        sh = AimShell(w)
        me = M.Side("A", sh, w.tail)
        before, after = M.aim_yaw(me, target, NoCameraTail(w.tail), sh, clock=c, wait=c.wait, read="pulse",
                                  tol=M.AIM_TOL_DEG)
        return w, sh, me, before, after

    def test_pulse_mode_reads_the_heading_half_a_second_after_each_pulse(self):
        w, sh, me, before, after = self.run_pulse((0.0, 100.0), -30.0, lag=False)
        self.assertLessEqual(abs(after), M.AIM_TOL_DEG, sh.lines)
        holds = me.aims[-1]["holds"]
        self.assertTrue(holds)
        # a pulse is capped at AIM_PULSE_MAX_S unless its turn is large (Task 5 finish: longer pulses, <= 6 of them)
        self.assertTrue(all(h["s"] <= M.pulse_hold_max(h["err"], h["gain"]) + 1e-3 for h in holds), holds)
        self.assertTrue(all(h["s"] <= M.AIM_PULSE_MAX_S + 1e-3 for h in holds
                            if abs(h["err"]) <= M.AIM_PULSE_LONG_ERR_DEG * h["gain"]), holds)
        for r in me.aims[-1]["reads"]:
            if r["after_rx"] is not None:
                self.assertGreaterEqual(r["t"] - r["after_rx"], M.AIM_PULSE_READ_S - 1e-6, r)
                self.assertLess(r["t"] - r["after_rx"], M.AIM_PULSE_READ_S + 0.5, r)

    def test_pulse_mode_converges_with_a_lagging_matrix_within_its_pulse_cap(self):
        for target, facing in (((100.0, 0.0), 70.0), ((0.0, 100.0), -30.0), ((-100.0, -5.0), 10.0)):
            w, sh, me, before, after = self.run_pulse(target, facing, lag=True)
            self.assertLessEqual(abs(after), M.AIM_TOL_DEG, (target, facing, sh.lines))
            self.assertLessEqual(len(me.aims[-1]["holds"]), M.AIM_PULSE_MAX_ITER)

    def test_a_wider_tolerance_stops_sooner(self):
        c = Clock()
        w = AimWorld(c, facing=78.0, lag=False)
        c.wait(1.0)
        sh = AimShell(w)
        me = M.Side("A", sh, w.tail)
        before, after = M.aim_yaw(me, (0.0, 100.0), w.tail, sh, clock=c, wait=c.wait, read="pulse", tol=15.0)
        self.assertEqual(me.aims[-1]["holds"], [])
        self.assertLessEqual(abs(after), 15.0)

    def test_no_heading_rows_is_no_data(self):
        c = Clock()
        t = tail(c)
        for _ in range(8):
            c.t += 0.25
            t._line(peek(x=1.0, z=1.0))                 # actor rows without a matrix
        sh = AimShell(AimWorld(Clock()))
        me = M.Side("A", sh, t)
        before, after = M.aim_yaw(me, (50.0, 0.0), t, sh, clock=c, wait=c.wait, read="rest")
        self.assertIsNone(before)
        self.assertIsNone(after)
        self.assertTrue(any("NO-DATA" in m for m in sh.lines))

    def test_fidget_is_offered_before_a_hold_and_its_motion_waits_for_rest_again(self):
        c = Clock()
        w = AimWorld(c, facing=-50.0)
        c.wait(1.0)
        sh = AimShell(w)
        me = M.Side("A", sh, w.tail)
        calls = []

        def fidget():
            calls.append(c.t)
            if len(calls) == 1:
                w.x += 3.0                              # a micro-strafe moved the player
                c.wait(0.3)
                return True
            return False
        M.aim_yaw(me, (0.0, 100.0), w.tail, sh, clock=c, wait=c.wait, fidget=fidget, read="rest", tol=M.AIM_TOL_DEG)
        self.assertGreaterEqual(len(calls), 1)


class TeleportDetectorTest(unittest.TestCase):
    """An actor row-to-row ground step > TELEPORT_STEP_UNITS (30) inside a window is a teleport -- unless the rows are
    far enough apart in time that walking covers it (a slow sampler: kill2 B ran 1.08 s/row under load)."""

    def walk(self, n=20, t0=100.0, dt=0.25, speed=40.0, actor=1):
        return [(t0 + i * dt, 500.0 + speed * dt * i, 100.0, 500.0, actor) for i in range(n)]

    def test_walking_is_not_a_teleport(self):
        self.assertIsNone(M.teleport_step(self.walk(), 100.0, 105.0))

    def test_a_jump_inside_the_window_is(self):
        rows = self.walk()
        rows[10] = (rows[10][0], rows[10][1] + 86.0, 100.0, 500.0, 1)
        rows[11:] = [(t, x + 86.0, y, z, a) for t, x, y, z, a in rows[11:]]
        hit = M.teleport_step(rows, 101.0, 104.0)
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit[0], rows[10][0])
        self.assertAlmostEqual(hit[1], 96.0, delta=0.01)

    def test_outside_the_window_is_ignored(self):
        rows = self.walk()
        rows[18:] = [(t, x + 200.0, y, z, a) for t, x, y, z, a in rows[18:]]
        self.assertIsNone(M.teleport_step(rows, 100.0, 103.0))

    def test_a_slow_sampler_row_is_not_a_teleport(self):
        rows = self.walk(n=6, dt=1.08)                  # 43 units per row at walking speed
        self.assertIsNone(M.teleport_step(rows, 100.0, 106.0))

    def test_an_actor_change_is_not_a_teleport(self):
        rows = self.walk(n=8)
        rows[4:] = [(t, x + 500.0, y, z, 2) for t, x, y, z, _ in rows[4:]]
        self.assertIsNone(M.teleport_step(rows, 100.0, 102.0))

    def test_the_abort_carries_what_the_result_line_needs(self):
        e = M.TeleportAbort("B", "walk", 96.0, 123.4)
        self.assertIn("teleport", str(e))
        self.assertIn("side=B", str(e))
        self.assertIn("during=walk", str(e))


if __name__ == "__main__":
    unittest.main()
