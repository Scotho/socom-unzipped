"""Sprint 5 Task 5 finish, slice (ii) -- the slice-(b) review findings on aim:

  * I1: pulse mode reaches tolerance in <= 6 iterations (Amendment A3's bar) -- a large error takes a LONGER pulse,
    still read 0.5 s after it ends;
  * I2: a pulse that delivered nothing is escalated (deflection / hold), never repeated identically;
  * I3: no walking credit for a row step during a stationary aim (a slow sampler hides a 40-unit jump otherwise);
  * I4: a teleport during a burst makes the round NO-DATA (the fire-window check);
  * minors: aim_yaw defaults to read="pulse" and the spec §5.1 tolerance; rows between the previous read and the
    next pulse are checked; Shell.pad releases the sticks in a `finally`.

unittest only; simulated time.
"""
import math
import os
import tempfile
import unittest

from tools_py.parity import online_login_ours as L
from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import Clock, f2w, item, peek
from tools_py.tests.test_aim_pad import AimShell, AimWorld


class ExactShell(AimShell):
    """rv5b/plant.py's continuous plant: a pulse turns rate(|rx - 0x80|) x gain for (seconds - lead) when outside the
    dead zone, applied at release (the 4 Hz world would quantise every turn to 0.25 s steps)."""

    def pad(self, seconds, buttons=(), sticks=(), axes=None, abort=None):
        ax = L.pad_axes(sticks, axes)
        w = self.world
        self.pads.append((w.clock.t, tuple(buttons), dict(ax), seconds))
        dev = ax.get("rx", 0x80) - 0x80
        w.clock.wait(seconds)
        if dev and abs(dev) > w.dz:
            w.facing = M.wrap_deg(w.facing + math.copysign(M.yaw_rate_deg_s(abs(dev)), dev) * w.gain
                                  * max(0.0, seconds - w.lead))


def run_aim(target, exact=False, **kw):
    aim_kw = {k: kw.pop(k) for k in ("tol", "max_iter", "fidget", "read") if k in kw}
    c = Clock()
    w = AimWorld(c, **kw)
    c.wait(1.0)
    sh = ExactShell(w) if exact else AimShell(w)
    me = M.Side("A", sh, w.tail)
    before, after = M.aim_yaw(me, target, w.tail, sh, clock=c, wait=c.wait, **aim_kw)
    return w, sh, me, before, after


def rx_pulses(sh):
    return [(p[2]["rx"], round(p[3], 3)) for p in sh.pads if p[2].get("rx", 0x80) != 0x80]


class PulseIterationCapTest(unittest.TestCase):
    def test_the_default_pulse_cap_is_six(self):
        self.assertEqual(M.AIM_PULSE_MAX_ITER, 6)
        w, sh, me, before, after = run_aim((0.0, 100.0), facing=0.0, responds=False, lag=False, tol=6.0)
        self.assertEqual(len(rx_pulses(sh)), 6)

    def test_a_half_turn_converges_in_six_with_a_longer_pulse(self):
        # rv5b/plant2.py: lead 0.47 s, err0 +179 took 11 pulses of <= 0.6 s and missed at 6
        for err0 in (179.0, -150.0, 120.0):
            target = (100.0 * math.cos(math.radians(err0)), 100.0 * math.sin(math.radians(err0)))
            w, sh, me, before, after = run_aim(target, exact=True, responds=False, facing=0.0, gain=1.0, lead=0.47, dz=48, lag=False,
                                               tol=6.0, read="pulse")
            self.assertIsNotNone(after)
            self.assertLessEqual(abs(after), 6.0, (err0, sh.lines))
            self.assertLessEqual(len(rx_pulses(sh)), 6, (err0, rx_pulses(sh)))
            self.assertGreater(max(s for _, s in rx_pulses(sh)), M.AIM_PULSE_MAX_S, rx_pulses(sh))

    def test_every_read_is_half_a_second_after_its_pulse(self):
        w, sh, me, before, after = run_aim((-100.0, 1.0), facing=0.0, gain=1.0, lead=0.47, lag=False, tol=6.0)
        for r in me.aims[-1]["reads"]:
            if r["after_rx"] is not None:
                self.assertGreaterEqual(r["t"] - r["after_rx"], M.AIM_PULSE_READ_S - 1e-6)


class DeadPulseEscalationTest(unittest.TestCase):
    def test_a_dead_pulse_is_never_repeated_identically(self):
        # rv5b/plant2.py "dz 80": err0 +7 repeated (204, 0.562) twelve times and never turned
        w, sh, me, before, after = run_aim((100.0 * math.cos(math.radians(7.0)), 100.0 * math.sin(math.radians(7.0))),
                                           exact=True, facing=0.0, gain=1.0, dz=80, lag=False, tol=6.0,
                                           responds=False)
        pulses = rx_pulses(sh)
        self.assertTrue(all(p != q for p, q in zip(pulses, pulses[1:])), pulses)
        self.assertLessEqual(abs(after), 6.0, (pulses, sh.lines))
        self.assertLessEqual(len(pulses), 6)

    def test_the_escalated_floor_carries_to_the_next_aim(self):
        c = Clock()
        w = AimWorld(c, facing=0.0, gain=1.0, dz=80, lag=False, responds=False)
        c.wait(1.0)
        sh = ExactShell(w)
        me = M.Side("A", sh, w.tail)
        M.aim_yaw(me, (100.0, 12.0), w.tail, sh, clock=c, wait=c.wait, tol=3.0)
        first = len(rx_pulses(sh))
        M.aim_yaw(me, (100.0, -12.0), w.tail, sh, clock=c, wait=c.wait, tol=3.0)
        second = rx_pulses(sh)[first:]
        self.assertTrue(second and abs(second[0][0] - 0x80) > 80, second)


class SlowRowWorld(AimWorld):
    """AimWorld whose actor rows arrive once a second (a loaded sampler), jumping `jump` units at `jump_at`."""

    def __init__(self, clock, jump_at=None, jump=40.0, **kw):
        self.jump_at, self.jump, self.k = jump_at, jump, 0
        super().__init__(clock, **kw)

    def tick(self, t):
        if self.jump_at is not None and t >= self.jump_at:
            self.x += self.jump
            self.jump_at = None
        self.k += 1
        if self.k % 4 == 0:
            super().tick(t)
        else:
            dev = self.rx - 0x80
            if self.responds and dev and abs(dev) > self.dz and t - self.hold_t >= self.lead:
                self.facing = M.wrap_deg(self.facing + math.copysign(M.yaw_rate_deg_s(abs(dev)), dev) * self.gain * 0.25)


class StationaryTeleportTest(unittest.TestCase):
    def test_teleport_step_without_walking_credit(self):
        rows = [(100.0 + 1.08 * i, 500.0 + (43.0 if i >= 3 else 0.0), 100.0, 500.0, 1) for i in range(6)]
        self.assertIsNone(M.teleport_step(rows, 100.0, 106.0))
        hit = M.teleport_step(rows, 100.0, 106.0, walking=False)
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit[1], 43.0)

    def test_a_40_unit_jump_on_a_slow_sampler_aborts_a_stationary_aim(self):
        c = Clock()
        w = SlowRowWorld(c, facing=-90.0, lag=False, gain=1.0, jump_at=c.t + 2.2)
        c.wait(1.0)
        sh = AimShell(w)
        me = M.Side("A", sh, w.tail)
        with self.assertRaises(M.TeleportAbort):
            M.aim_yaw(me, (0.0, 100.0), w.tail, sh, clock=c, wait=c.wait, tol=2.0)

    def test_rows_between_the_last_read_and_the_next_pulse_are_checked(self):
        c = Clock()
        w = AimWorld(c, facing=-60.0, lag=False)
        c.wait(1.0)
        sh = AimShell(w)
        me = M.Side("A", sh, w.tail)
        calls = []

        def fidget():
            calls.append(c.t)
            if len(calls) == 1:
                w.x += 80.0                                     # a jump while the aim waited (not inside a pulse)
                c.wait(0.5)
                return True
            return False
        with self.assertRaises(M.TeleportAbort):
            M.aim_yaw(me, (0.0, 100.0), w.tail, sh, clock=c, wait=c.wait, fidget=fidget, tol=6.0)


class AimDefaultsTest(unittest.TestCase):
    def test_defaults_are_pulse_reads_and_the_spec_tolerance(self):
        import inspect
        sig = inspect.signature(M.aim_yaw)
        self.assertEqual(sig.parameters["read"].default, "pulse")
        # 5 deg off at 45 units is outside min(6, 0.8 atan(3.4/45)) = 3.46 deg -> a pulse; at 10 units it is inside 6
        far = (45.0 * math.cos(math.radians(5.0)), 45.0 * math.sin(math.radians(5.0)))
        w, sh, me, before, after = run_aim(far, facing=0.0, lag=False, gain=1.0)
        self.assertTrue(rx_pulses(sh), sh.lines)
        self.assertEqual(me.aims[-1]["read"], "pulse")
        near = (10.0 * math.cos(math.radians(5.0)), 10.0 * math.sin(math.radians(5.0)))
        w, sh, me, before, after = run_aim(near, facing=0.0, lag=False, gain=1.0)
        self.assertEqual(rx_pulses(sh), [])


class FireWindowTeleportTest(unittest.TestCase):
    """Amendment A3: 'inside a fire window the round is NO-DATA'."""

    def test_a_victim_jump_during_the_burst_is_no_data(self):
        from tools_py.tests.test_engagement_ladder import WalkShell, WalkWorld

        class JumpWorld(WalkWorld):
            def __init__(self, clock, *a, jump_when=None, **kw):
                self.jump_when = jump_when
                super().__init__(clock, *a, **kw)

            def tick(self, t):
                if self.jump_when is not None and self.jump_when():
                    self.x += 60.0
                    self.jump_when = None
                super().tick(t)
        c = Clock(0.0)
        shooter = WalkWorld(c, 0.0, 0.0, 0.0)
        ssh = WalkShell(shooter)
        victim = JumpWorld(c, 25.0, 0.0, 180.0, jump_when=lambda: any("R1" in p[1] for p in ssh.pads))
        c.wait(1.0)
        sides = {"A": M.Side("A", ssh, shooter.tail), "B": M.Side("B", WalkShell(victim), victim.tail)}
        lines = []
        out = M.endgame_route(sides, M.Duel(), None, lines.append, "nomap", mover="A", route=[], fight_s=6.0,
                              clock=c, wait=c.wait)
        self.assertIsNotNone(out.get("fire_teleport"), lines)
        self.assertTrue(out["stop_reason"].startswith("NO-DATA"), out["stop_reason"])
        self.assertEqual(out["bursts"], 1)


class PadReleaseTest(unittest.TestCase):
    def test_the_sticks_are_released_when_the_hold_is_interrupted(self):
        sh = L.Shell.__new__(L.Shell)
        fd, path = tempfile.mkstemp(prefix="pad_", suffix=".txt")
        os.close(fd)
        sh.pad_file = path
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        orig = L.time.sleep

        def boom(s):
            raise KeyboardInterrupt
        L.time.sleep = boom
        try:
            with self.assertRaises(KeyboardInterrupt):
                sh.pad(5.0, axes={"rx": 255, "lx": 0})
        finally:
            L.time.sleep = orig
        self.assertEqual(open(path).read().strip(), "b=0000 rx=128 ry=128 lx=128 ly=128")


if __name__ == "__main__":
    unittest.main()


class AimItersFieldTest(unittest.TestCase):
    def test_per_cycle_counts_and_the_ok_share(self):
        aims = [{"t0": 10.0, "holds": [1, 2], "err_after": 1.0, "tol": 3.0},
                {"t0": 20.0, "holds": [1] * 6, "err_after": 5.0, "tol": 3.0},
                {"t0": 30.0, "holds": [], "err_after": 0.5, "tol": 6.0},
                {"t0": 1.0, "holds": [1], "err_after": 0.0, "tol": 6.0}]
        self.assertEqual(M.aim_iters_field(aims, t0=5.0), "2/3:2,6!,0")
        self.assertEqual(M.aim_iters_field([], t0=5.0), vc.NO_DATA)
        line = M.ladder_line(rung=1, controllable=("yes", "yes"), contact_rows=0, rows_read=10, damage="no", kill="no",
                             starvation_alarms=0, alarms_cleared=0, max_idle_ms=(1, 2), lagflag_rows=(3, 4),
                             aim_iters="2/3:2,6!,0")
        self.assertTrue(line.endswith(" aim_iters=2/3:2,6!,0"), line)
