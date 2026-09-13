"""Sprint 5 Task 5 fix round, slice 4 -- dead-pulse escalation (review of finish (ii), I7):

  * one escalation per dead pulse: the deflection floor first, the side's lead (and so the hold) next -- never both;
  * the escalations decay after a delivered pulse (the floor never below a band a long pulse proved dead + 16);
  * a hold never plans a sweep beyond AIM_SWEEP_CAP (1.5) x |err| in delivered degrees;
  * rv5f1/plant4.py's failing case (dead zone 90 + lead 0.47 + ramp 0.15, 45 units, +-7 deg) converges in <= 6 pulses,
    and rv5f1/plant3.py's matrix (5 plants x 3 ranges x 5 errors) has no failure.

The plant is the review's rv5f1/plant.py: a continuous yaw (the research/22 table x gain above a dead zone, after a lead,
with an optional first-order ramp), rows at 4 Hz. unittest only; simulated time.
"""
import math
import threading
import unittest

from tools_py.parity import online_login_ours as L
from tools_py.parity import online_match_ours as M

W = M.wrap_deg


class Plant:
    def __init__(self, facing=0.0, gain=1.0, dz=48, lead=0.4, ramp=0.0):
        self.t, self.f = 0.0, facing
        self.gain, self.dz, self.lead, self.ramp = gain, dz, lead, ramp
        self.rx, self.hold_t, self.next_row = 0x80, None, 0.25
        self.heading_rows, self.rows, self._lock = [], [], threading.Lock()

    def __call__(self):
        return self.t

    def actor_ingame(self):
        return list(self.rows)

    def step(self, dt):
        dev = self.rx - 0x80
        if dev and self.t - self.hold_t >= self.lead:
            r = (0.0 if abs(dev) <= self.dz else M.yaw_rate_deg_s(abs(dev))) * self.gain
            if self.ramp:
                r *= min(1.0, (self.t - self.hold_t - self.lead) / self.ramp)
            self.f = W(self.f + math.copysign(r, dev) * dt)
        self.t = round(self.t + dt, 9)
        while self.t >= self.next_row - 1e-9:
            self.heading_rows.append((self.next_row, self.f, 0.0, 0.0))
            self.rows.append((self.next_row, 0.0, 100.0, 0.0, 1))
            self.next_row = round(self.next_row + 0.25, 9)

    def wait(self, sec):
        end = self.t + sec
        while self.t < end - 1e-9:
            self.step(min(0.01, end - self.t))


class Sh:
    def __init__(self, p):
        self.p, self.lines, self.pulses = p, [], []

    def log(self, m):
        self.lines.append(m)

    def pad(self, seconds, buttons=(), sticks=(), axes=None, abort=None):
        ax = L.pad_axes(sticks, axes)
        self.p.rx, self.p.hold_t = ax.get("rx", 0x80), self.p.t
        self.p.wait(seconds)
        self.p.rx = 0x80
        self.pulses.append((ax.get("rx"), round(seconds, 3)))


class Me(M.Side):
    def __init__(self):
        self.tag, self.yaw_gain, self.aims, self.aim_teleports = "A", 1.0, [], 0


def aim(err0, d, me=None, plant=None, **pk):
    p = plant or Plant(**pk)
    if plant is None:
        p.wait(1.0)
    ang = math.radians(p.f + err0)
    target = (d * math.cos(ang), d * math.sin(ang))
    me = me or Me()
    sh = Sh(p)
    before, after = M.aim_yaw(me, target, p, sh, clock=p, wait=p.wait)
    rec = me.aims[-1]
    return rec, after, sh, me, p


PLANT4 = dict(dz=90, lead=0.47, ramp=0.15)


class Plant4CaseTest(unittest.TestCase):
    def test_dead_zone_90_lead_047_ramp_015_at_45_units_converges_in_six(self):
        for err0 in (7.0, -7.0):
            rec, after, sh, me, p = aim(err0, 45.0, **PLANT4)
            self.assertIsNotNone(after)
            self.assertLessEqual(len(rec["holds"]), 6, sh.pulses)
            self.assertLessEqual(abs(after), rec["tol"], (err0, sh.pulses, sh.lines))

    def test_a_persistent_side_keeps_converging(self):
        p = Plant(**PLANT4)
        p.wait(1.0)
        me = Me()
        for err0 in (5, -6, 8, -5, 10, -4, 6):
            rec, after, sh, me, p = aim(err0, 45.0, me=me, plant=p)
            self.assertLessEqual(len(rec["holds"]), 6, sh.pulses)
            self.assertLessEqual(abs(after), rec["tol"], (err0, sh.pulses, sh.lines))
            p.wait(1.0)


class Plant3MatrixTest(unittest.TestCase):
    PLANTS = (("nominal", {}), ("gain .65", dict(gain=0.65)), ("lead .47+ramp .15", dict(lead=0.47, ramp=0.15)),
              ("dz 80", dict(dz=80)), ("dz 90", dict(dz=90)))

    def test_no_regression_over_the_matrix(self):
        fails = []
        for label, pk in self.PLANTS:
            for d in (10.0, 30.0, 45.0):
                for err0 in (5.0, 30.0, 90.0, 179.0, -179.0):
                    rec, after, sh, me, p = aim(err0, d, **pk)
                    if after is None or abs(after) > rec["tol"] or len(rec["holds"]) > 6:
                        fails.append((label, d, err0, after, sh.pulses))
        self.assertEqual(fails, [])


class OneEscalationTest(unittest.TestCase):
    def test_a_dead_pulse_escalates_the_deflection_or_the_hold_never_both(self):
        for err0 in (7.0, -7.0, 12.0):
            rec, after, sh, me, p = aim(err0, 45.0, **PLANT4)
            holds = rec["holds"]
            for k, (h0, h1) in enumerate(zip(holds, holds[1:])):
                if k + 1 < len(rec["reads"]) and abs(M.wrap_deg(rec["reads"][k + 1]["heading"]
                                                              - rec["reads"][k]["heading"])) < M.AIM_DEAD_DELIVERED_DEG:
                    d0, d1 = abs(h0["rx"] - 0x80), abs(h1["rx"] - 0x80)
                    self.assertFalse(d1 > d0 and h1["s"] >= h0["s"] + M.AIM_ESCALATE_HOLD_S - 1e-6,
                                     (err0, sh.pulses))

    def test_the_floor_decays_after_delivered_pulses_but_not_into_a_proven_dead_band(self):
        me = Me()
        me.aim_floor, me.aim_dead_band = 127, 70
        p = Plant(dz=48)
        p.wait(1.0)
        rec, after, sh, me, p = aim(20.0, 30.0, me=me, plant=p)
        self.assertLess(me.aim_floor, 127, sh.pulses)
        for _ in range(40):
            rec, after, sh, me, p = aim(20.0 if _ % 2 else -20.0, 30.0, me=me, plant=p)
        self.assertEqual(me.aim_floor, 70 + M.AIM_ESCALATE_DEFLECTION)

    def test_an_escalated_hold_never_plans_more_than_1_5_x_the_error(self):
        rx, secs, predicted = M.aim_plan(5.0, 1.0, min_deflection=127, lead=0.6, max_sweep=M.AIM_SWEEP_CAP * 5.0)
        self.assertLessEqual(predicted, M.AIM_SWEEP_CAP * 5.0 + 1e-6)
        self.assertAlmostEqual(secs - 0.6, predicted / M.yaw_rate_deg_s(127), places=6)


if __name__ == "__main__":
    unittest.main()
