"""Sprint 5 Task 3 Step 0 -- the pure online verdict scorers (`tools_py.parity.verdict_core`).

unittest only (no pytest, no module-level `def test_`). Two kinds of input:
  * synthetic rows built here, one hazard per test;
  * trimmed excerpts of Sprint 4's real run logs under `fixtures/online/` (provenance in that
    folder's README.md; regenerate with its make_fixtures.py).

Every scorer gets a negative control, a monotonicity check and one instance of the class it guards.
Deferred to Task 3 Step 1 (they need `online_match_ours.py` / `winshot.py`): `respawn` alone -> not
PASS, an armed health watch with zero reads -> FAIL, a back-dated frame file -> StaleFrameError.
"""
import contextlib
import io
import os
import struct
import unittest

from tools_py.parity import verdict_core as vc

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "online")

# kill2's two logs run on two process clocks. Each instance's MoveScale #0 is its round start
# (A 418.5 s, B 412.7 s in the full logs, run_*_20260912_231341.log), so B + 5.8 s ~ A.
KILL2_B_TO_A_OFFSET_S = 418.5 - 412.7


def fixture(name):
    with open(os.path.join(FIXTURES, name), "r") as f:
        return f.read().split("\n")


def parsed(name):
    return vc.parse_log(fixture(name))


def f2w(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


# ---------------------------------------------------------------------------------------------
# synthetic control rows
# ---------------------------------------------------------------------------------------------
HOLD_START, HOLD_S = 20.0, 2.0
RELEASE = HOLD_START + HOLD_S
PERIOD = 0.25


def pad_hold(start=HOLD_START, release=RELEASE, ly=0x00):
    return [vc.PadEvent(start, 0, 0x80, 0x80, 0x80, ly), vc.PadEvent(release, 0, 0x80, 0x80, 0x80, 0x80)]


def rows_from(fn, t0=0.0, t1=30.0, addr=0x17941D0, period=PERIOD):
    """Actor rows every `period` s (4 Hz by default), x = fn(t) (ground plane x; z 1000, y 50)."""
    out, i = [], 0
    while t0 + i * period <= t1 + 1e-9:
        t = round(t0 + i * period, 6)
        out.append((t, fn(t), 50.0, 1000.0, addr))
        i += 1
    return out


def correction(units_during_hold, units_back, begin_after_release, duration):
    """x(t): still before the hold, linear during it, still after release until release +
    `begin_after_release`, then a linear correction of `units_back` over `duration` s, then still."""
    rate = units_during_hold / HOLD_S

    def x(t):
        if t <= HOLD_START:
            return 100.0
        if t <= RELEASE:
            return 100.0 + rate * (t - HOLD_START)
        f = min(1.0, max(0.0, (t - RELEASE - begin_after_release) / duration))
        return 100.0 + units_during_hold - f * units_back
    return x


def walk(units_during_hold, coast=0.0, snap_at=None, snap_units=0.0, drift_per_s=0.0, period=PERIOD):
    """x(t): neutral drift before the hold, linear motion during it, optional coast after release
    (reached one sample later), optional snap-back of `snap_units` at release + `snap_at`."""
    rate = units_during_hold / HOLD_S

    def x(t):
        if t <= HOLD_START:
            return 100.0 + drift_per_s * (t - HOLD_START)
        if t <= RELEASE:
            return 100.0 + rate * (t - HOLD_START)
        v = 100.0 + units_during_hold + min(1.0, (t - RELEASE) / period) * coast
        if snap_at is not None and t >= RELEASE + snap_at:
            v -= snap_units
        return v
    return x


class ParseLogTest(unittest.TestCase):
    def test_zero_lines_reads_zero_rows(self):
        p = vc.parse_log([])
        self.assertEqual((p.lines, len(p.peek_rows), len(p.actor_rows), len(p.pad_events)), (0, 0, 0, 0))

    def test_actor_found_by_vtable_not_by_index(self):
        # item 0 missing (unresolved chain) -> the actor is item 0 of this row; still found
        words = ["006691a0(0)"] + ["00000000(0)"] * 6 + [f"{f2w(v):08x}({v})" for v in (1.0, 2.0, 3.0)]
        line = "[peek] @17941d0: " + " ".join(words)
        p = vc.parse_log([line, "[peek] @408c58: 017941d0(0)"])
        self.assertEqual(len(p.actor_rows), 1)
        self.assertEqual(p.actor_rows[0][1:4], (1.0, 2.0, 3.0))
        self.assertEqual(p.actor_rows[0][4], 0x17941D0)

    def test_clock_interpolates_between_call_stamps(self):
        lines = []
        for i in range(81):
            lines.append("[peek] @416054: 00000000(0)")
            if i in (0, 40, 80):
                lines.append(f"[call] {100.0 + i * 0.3:.1f}s MoveScale #{i} a0=0x0 ra=0x595028 f12=1.0 f13=0.0 f14=0")
        p = vc.parse_log(lines)
        t = [r[0] for r in p.peek_rows]
        self.assertAlmostEqual(t[40] - t[0], 12.0, delta=0.35)     # 0.3 s/row from the stamps, not 0.25
        self.assertEqual(p.calls["MoveScale"][1][1], 40)

    def test_torn_pad_line_is_recovered_and_counted(self):
        lines = ["[peek] @416054: 00000000(0)",
                 "[socom2-input] state bINFO: FILEIO: [x.png] Image exported successfully",
                 "uttons=0000 rx=80 ry=80 lx=80 ly=00",
                 "[peek] @416054: 00000000(0)"]
        p = vc.parse_log(lines)
        self.assertEqual(p.torn_pad_lines, 1)
        self.assertEqual(p.unrecovered_pad_lines, 0)
        self.assertEqual(len(p.pad_events), 1)
        self.assertEqual(p.pad_events[0].ly, 0x00)

    def test_unrecoverable_torn_pad_line_is_counted(self):
        lines = ["[peek] @416054: 00000000(0)", "[socom2-input] state buttoINFO: x", "garbage",
                 "[peek] @416054: 00000000(0)"]
        p = vc.parse_log(lines)
        self.assertEqual(p.unrecovered_pad_lines, 1)
        self.assertEqual(len(p.pad_events), 0)

    def test_line_after_an_unrecoverable_tear_is_still_parsed(self):
        lines = ["[peek] @416054: 00000000(0)", "[socom2-input] state buttoINFO: x",
                 "[call] 5.0s MoveScale #9 a0=0x0 ra=0x595028 f12=1.0 f13=0.0 f14=0",
                 "[peek] @416054: 00000000(0)"]
        p = vc.parse_log(lines)
        self.assertEqual(p.unrecovered_pad_lines, 1)
        self.assertEqual([c[1] for c in p.calls.get("MoveScale", [])], [9])

    def test_ret_rows_take_the_time_of_their_call(self):
        lines = ["[peek] @416054: 00000000(0)",
                 "[call] 5.0s NetIdleMs #7 a0=0x0 ra=0x594f88 f12=0.0 f13=0.0 f14=0",
                 "[ret] NetIdleMs #7 v0=0x106a f0=0.6"]
        p = vc.parse_log(lines)
        self.assertEqual(p.rets["NetIdleMs"], [(5.0, 7, 0x106A)])

    def test_forward_holds(self):
        ev = pad_hold() + [vc.PadEvent(25.0, 0, 0xFF, 0x80, 0x80, 0x80), vc.PadEvent(26.0, 0, 0x80, 0x80, 0x80, 0x80)]
        holds = vc.forward_holds(ev)
        self.assertEqual(holds, [vc.Hold(HOLD_START, RELEASE)])

    def test_forward_hold_with_a_turn_mixed_in_is_not_a_forward_hold(self):
        ev = [vc.PadEvent(20.0, 0, 0x80, 0x80, 0x80, 0x00), vc.PadEvent(21.0, 0, 0xFF, 0x80, 0x80, 0x00),
              vc.PadEvent(22.0, 0, 0x80, 0x80, 0x80, 0x80)]
        self.assertEqual(vc.forward_holds(ev), [])

    def test_unreleased_hold_is_not_a_hold(self):
        self.assertEqual(vc.forward_holds([vc.PadEvent(20.0, 0, 0x80, 0x80, 0x80, 0x00)]), [])


class ScoreControlTest(unittest.TestCase):
    def score(self, x, pads=None, rows=None):
        return vc.score_control(rows if rows is not None else rows_from(x), pads or pad_hold(),
                                vc.Hold(HOLD_START, RELEASE))

    def test_clean_hold_passes(self):
        v = self.score(walk(80.0, coast=5.0))
        self.assertEqual(v.status, "PASS", v)
        self.assertTrue(v.ok)
        self.assertAlmostEqual(v.net_units, 85.0, places=3)
        self.assertLessEqual(v.snapback_units, vc.CONTROL_SNAPBACK_MAX_UNITS)
        self.assertAlmostEqual(v.drift_units, 0.0, places=6)

    def test_negative_control_frozen_player_fails_although_drift_passes_trivially(self):
        v = self.score(lambda t: 100.0)
        self.assertEqual(v.status, "FAIL")
        self.assertFalse(v.ok)
        self.assertEqual(v.net_units, 0.0)
        self.assertEqual(v.drift_units, 0.0)

    def test_rubber_band_24_units_snapped_back_within_0_6s(self):
        v = self.score(walk(24.0, snap_at=0.5, snap_units=24.0))
        self.assertFalse(v.ok)
        self.assertEqual(v.status, "FAIL")

    def test_twenty_percent_snap_back(self):
        v = self.score(walk(80.0, snap_at=1.0, snap_units=16.0))
        self.assertGreaterEqual(v.net_units, vc.CONTROL_NET_MIN_UNITS)   # the 40 alone would pass it
        self.assertFalse(v.ok)
        self.assertGreater(v.snapback_units, vc.CONTROL_SNAPBACK_MAX_UNITS)

    def test_snap_back_at_release_plus_1_8s(self):
        v = self.score(walk(80.0, snap_at=1.8, snap_units=80.0))
        self.assertGreaterEqual(v.net_units, vc.CONTROL_NET_MIN_UNITS)   # measured at +1.5 s: not yet
        self.assertFalse(v.ok)
        self.assertGreater(v.snapback_units, vc.CONTROL_SNAPBACK_MAX_UNITS)

    def test_six_units_per_second_of_neutral_drift(self):
        v = self.score(walk(80.0, drift_per_s=6.0))
        self.assertFalse(v.ok)
        self.assertAlmostEqual(v.drift_units, 60.0, places=3)

    def test_drift_under_the_bar_passes(self):
        v = self.score(walk(80.0, drift_per_s=0.4))
        self.assertTrue(v.ok, v)

    def test_monotonic_in_displacement(self):
        results = [(d, self.score(walk(float(d))).ok) for d in range(0, 121, 5)]
        first_pass = next(d for d, ok in results if ok)
        for d, ok in results:
            if d >= first_pass:
                self.assertTrue(ok, f"{d} units failed where {first_pass} passed")
        self.assertEqual(first_pass, 40)

    def test_monotonic_in_snap_back(self):
        oks = [self.score(walk(80.0, snap_at=1.0, snap_units=float(s))).ok for s in range(0, 40, 2)]
        self.assertEqual(oks, sorted(oks, reverse=True))
        self.assertIn(True, oks)
        self.assertIn(False, oks)

    # -- fix round 1: the ±½-period pad timing must not leak hold motion into drift / snap-back --
    @staticmethod
    def moving(start_row_t, stop_row_t, rate=48.0):
        """stationary at 100 until the row at start_row_t, `rate` u/s until stop_row_t, then still."""
        def x(t):
            return 100.0 + rate * (min(max(t, start_row_t), stop_row_t) - start_row_t)
        return x

    def test_start_event_just_after_a_row_does_not_leak_into_drift(self):
        # the game saw the press just after the 20.00 row; parse_log gives the event the midpoint 20.125
        hold = vc.Hold(20.125, 22.125)
        pads = [vc.PadEvent(hold.start, 0, 0x80, 0x80, 0x80, 0x00), vc.PadEvent(hold.release, 0, 0x80, 0x80, 0x80, 0x80)]
        v = vc.score_control(rows_from(self.moving(20.0, 22.25)), pads, hold)
        self.assertAlmostEqual(v.drift_units, 0.0, places=6)
        self.assertEqual(v.status, "PASS", v)

    def test_release_reference_bounds_the_one_row_coast(self):
        # release seen just after the 22.00 row (event at 22.125); the actor moves until the row after
        # the next one (22.50) -- one sampler period of coast beyond the timing error, then still
        hold = vc.Hold(20.0, 22.125)
        pads = [vc.PadEvent(hold.start, 0, 0x80, 0x80, 0x80, 0x00), vc.PadEvent(hold.release, 0, 0x80, 0x80, 0x80, 0x80)]
        v = vc.score_control(rows_from(self.moving(20.0, 22.5)), pads, hold)
        self.assertLessEqual(v.snapback_units, 1e-6)
        self.assertEqual(v.status, "PASS", v)

    def test_boundary_net(self):
        self.assertFalse(self.score(walk(39.9)).ok)
        self.assertTrue(self.score(walk(40.0)).ok)

    def test_boundary_drift(self):
        self.assertTrue(self.score(walk(80.0, drift_per_s=0.49)).ok)
        v = self.score(walk(80.0, drift_per_s=0.51))
        self.assertEqual(v.status, "FAIL")
        self.assertAlmostEqual(v.drift_units, 5.1, places=6)

    # -- fix round 2: snap-back from the peak excursion, independent of the row period --
    def test_rubber_band_24_fails_on_snap_back_at_both_periods(self):
        for period in (0.25, 0.6):
            with self.subTest(period=period):
                v = self.score(None, rows=rows_from(walk(24.0, snap_at=0.5, snap_units=24.0, period=period),
                                                    period=period))
                self.assertFalse(v.ok)
                self.assertGreater(v.snapback_units, vc.CONTROL_SNAPBACK_MAX_UNITS)

    def test_thirty_unit_correction_in_0_3s_fails_on_snap_back_at_both_periods(self):
        for period in (0.25, 0.6):
            with self.subTest(period=period):
                v = self.score(None, rows=rows_from(correction(80.0, 30.0, 0.3, 0.3), period=period))
                self.assertGreaterEqual(v.net_units, vc.CONTROL_NET_MIN_UNITS)     # net alone passes
                self.assertFalse(v.ok)
                self.assertGreater(v.snapback_units, vc.CONTROL_SNAPBACK_MAX_UNITS)

    def test_coast_at_0_6s_rows_passes(self):
        v = self.score(None, rows=rows_from(walk(80.0, coast=10.0, period=0.6), period=0.6))
        self.assertEqual(v.status, "PASS", v)
        self.assertLessEqual(v.snapback_units, 1e-6)

    def test_torn_line_in_the_shifted_drift_window_is_no_data(self):
        # press seen just after the 20.00 row: the drift window evaluated is [10.00, 20.00]; a tear at
        # 10.05 lies inside it but outside [s - 10, ...] = [10.125, ...]
        hold = vc.Hold(20.125, 22.125)
        pads = [vc.PadEvent(hold.start, 0, 0x80, 0x80, 0x80, 0x00), vc.PadEvent(hold.release, 0, 0x80, 0x80, 0x80, 0x80)]
        v = vc.score_control(rows_from(self.moving(20.0, 22.25)), pads, hold, unrecovered_pad_times=[10.05])
        self.assertEqual(v.status, vc.NO_DATA)

    def test_boundary_snap_back(self):
        self.assertTrue(self.score(walk(80.0, snap_at=1.0, snap_units=9.9)).ok)
        v = self.score(walk(80.0, snap_at=1.0, snap_units=10.1))
        self.assertEqual(v.status, "FAIL")
        self.assertAlmostEqual(v.snapback_units, 10.1, places=6)

    def test_no_rows_is_no_data(self):
        v = self.score(None, rows=[])
        self.assertEqual(v.status, vc.NO_DATA)
        self.assertFalse(v.ok)

    def test_row_gap_inside_the_window_is_no_data(self):
        rows = [r for r in rows_from(walk(80.0)) if not (RELEASE < r[0] < RELEASE + 2.5)]
        v = self.score(None, rows=rows)
        self.assertEqual(v.status, vc.NO_DATA)

    def test_input_in_the_drift_window_is_no_data_not_pass(self):
        pads = [vc.PadEvent(15.0, 0, 0xFF, 0x80, 0x80, 0x80), vc.PadEvent(16.0, 0, 0x80, 0x80, 0x80, 0x80)] + pad_hold()
        v = self.score(walk(80.0), pads=pads)
        self.assertEqual(v.status, vc.NO_DATA)
        self.assertIsNone(v.drift_units)

    def test_input_after_release_is_no_data(self):
        pads = pad_hold() + [vc.PadEvent(RELEASE + 1.0, 0, 0xFF, 0x80, 0x80, 0x80),
                             vc.PadEvent(RELEASE + 2.0, 0, 0x80, 0x80, 0x80, 0x80)]
        v = self.score(walk(80.0), pads=pads)
        self.assertEqual(v.status, vc.NO_DATA)

    def test_a_frozen_player_still_fails_when_the_drift_window_is_unmeasurable(self):
        pads = [vc.PadEvent(15.0, 0, 0xFF, 0x80, 0x80, 0x80), vc.PadEvent(16.0, 0, 0x80, 0x80, 0x80, 0x80)] + pad_hold()
        v = self.score(lambda t: 100.0, pads=pads)
        self.assertEqual(v.status, "FAIL")

    def test_actor_block_repointed_inside_the_window_is_no_data(self):
        rows = [(r[0], r[1], r[2], r[3], 0x1000 if r[0] > RELEASE else r[4]) for r in rows_from(walk(80.0))]
        self.assertEqual(self.score(None, rows=rows).status, vc.NO_DATA)

    def test_side_stops_at_first_pass_and_caps_at_four_holds(self):
        rows = rows_from(lambda t: 100.0, t1=200.0)
        pads = []
        for k in range(6):
            s = 20.0 + 15.0 * k
            pads += [vc.PadEvent(s, 0, 0x80, 0x80, 0x80, 0x00), vc.PadEvent(s + 2.0, 0, 0x80, 0x80, 0x80, 0x80)]
        side = vc.score_control_side(rows, pads)
        self.assertEqual(side.status, vc.NO_CONTROL)
        self.assertEqual(len(side.holds), vc.PRECONDITION_MAX_HOLDS)

    def test_side_with_no_holds_is_no_data(self):
        self.assertEqual(vc.score_control_side(rows_from(walk(80.0)), []).status, vc.NO_DATA)

    def test_pair_result(self):
        ok = vc.SideControl(vc.CONTROLLABLE, [])
        bad = vc.SideControl(vc.NO_CONTROL, [])
        nod = vc.SideControl(vc.NO_DATA, [])
        self.assertEqual(vc.control_result({"A": ok, "B": ok}), "CONTROLLABLE")
        self.assertEqual(vc.control_result({"A": bad, "B": bad}), "NO-CONTROL")
        self.assertEqual(vc.control_result({"A": ok, "B": bad}), "NO-CONTROL side=B")
        self.assertEqual(vc.control_result({"A": ok, "B": nod}), vc.NO_DATA)
        self.assertEqual(vc.control_result({}), vc.NO_DATA)


class ControlFixtureTest(unittest.TestCase):
    """The spec's bar over Sprint 4's real actor rows."""

    def side(self, name):
        p = parsed(name)
        self.assertGreater(len(p.actor_rows), 50, f"{name}: fixture has no actor rows")
        return vc.score_control_side(p.actor_rows, p.pad_events)

    def test_frost1_is_no_control_on_both_sides(self):
        a, b = self.side("frost1_A.txt"), self.side("frost1_B.txt")
        self.assertEqual(vc.control_result({"A": a, "B": b}), "NO-CONTROL")
        for s in (a, b):
            self.assertTrue(s.holds)
            for h in s.holds:
                self.assertEqual(h.status, "FAIL")
                self.assertLess(h.net_units, 1.0)

    def test_kill2_is_controllable(self):
        a, b = self.side("kill2_A_probe.txt"), self.side("kill2_B_probe.txt")
        self.assertEqual(vc.control_result({"A": a, "B": b}), "CONTROLLABLE")
        for s in (a, b):
            self.assertGreater(s.holds[-1].net_units, 55.0)
            self.assertLess(s.holds[-1].drift_units, 3.0)

    def test_kill2_A_with_frost1_B_is_no_control_side_B(self):
        a, b = self.side("kill2_A_probe.txt"), self.side("frost1_B.txt")
        self.assertEqual(vc.control_result({"A": a, "B": b}), "NO-CONTROL side=B")

    def test_kill3_B_FINDING_controllable_on_actor_rows(self):
        """The brief expects NO-CONTROL side=B. Under the spec's bar on ACTOR rows B's first facing
        probe passes (net 66.93, snap 1.65, drift 0.00 as the CLI prints); Sprint 4 called B immobile from the 0x416054
        camera record, which froze on B while the actor moved. Asserted as measured; reported as a
        finding for the controller, not tuned away."""
        b = self.side("kill3_B_probes.txt")
        self.assertEqual(b.status, vc.CONTROLLABLE)
        first = b.holds[0]
        self.assertGreater(first.net_units, 60.0)
        self.assertLess(first.snapback_units, 2.0)
        self.assertLess(first.drift_units, 2.0)

    def test_kill3_B_pre_hold_drift_is_zero(self):
        # the actor block is unchanged 441.5-453.39 s in the raw log; hold motion must not leak in
        first = self.side("kill3_B_probes.txt").holds[0]
        self.assertLess(first.drift_units, 0.01)

    def test_kill3_B_camera_record_froze_during_the_passing_hold(self):
        p = parsed("kill3_B_probes.txt")
        h = vc.forward_holds(p.pad_events)[0]
        cams = {tuple(words[:3]) for t, items in p.peek_rows if h.start <= t <= h.release + 1.5
                for addr, words in items if addr == 0x416054}
        acts = {r[1:4] for r in p.actor_rows if h.start <= r[0] <= h.release + 1.5}
        self.assertLessEqual(len(cams), 2)
        self.assertGreater(len(acts), 5)


# ---------------------------------------------------------------------------------------------
class MovePathTest(unittest.TestCase):
    ALIVE = [(0.0, 1)]
    ROUND = [(0.0, 1)]

    @staticmethod
    def calls(t_end, rate=2.0, start=0.0, n0=300):
        out, t, n = [], start, n0
        while t <= t_end + 1e-9:
            out.append((round(t, 6), n))
            t += 1.0 / rate
            n += 10
        return out

    def test_advancing_is_ok(self):
        v = vc.score_move_path(self.calls(60.0), self.ALIVE, self.ROUND, now=60.0)
        self.assertEqual(v.status, "ok")

    def test_stalled_ten_seconds_while_alive(self):
        v = vc.score_move_path(self.calls(40.0), self.ALIVE, self.ROUND, now=50.5)
        self.assertEqual(v.status, "stalled")
        self.assertAlmostEqual(v.since, 40.0)

    def test_negative_control_just_under_ten_seconds(self):
        v = vc.score_move_path(self.calls(40.0), self.ALIVE, self.ROUND, now=49.9)
        self.assertEqual(v.status, "ok")

    def test_monotonic_in_gap(self):
        statuses = [vc.score_move_path(self.calls(40.0), self.ALIVE, self.ROUND, now=40.0 + g).status
                    for g in (0, 5, 9, 10, 11, 30, 300)]
        first = statuses.index("stalled")
        self.assertTrue(all(s == "stalled" for s in statuses[first:]), statuses)

    def test_stalled_while_dead_is_disarmed(self):
        alive = [(0.0, 1), (41.0, 0)]
        v = vc.score_move_path(self.calls(40.0), alive, self.ROUND, now=55.0)
        self.assertEqual(v.status, "disarmed")

    def test_rearmed_after_respawn_counts_from_the_respawn(self):
        alive = [(0.0, 1), (41.0, 0), (50.0, 1)]
        self.assertEqual(vc.score_move_path(self.calls(40.0), alive, self.ROUND, now=55.0).status, "disarmed")
        v = vc.score_move_path(self.calls(40.0), alive, self.ROUND, now=61.0)
        self.assertEqual(v.status, "stalled")
        self.assertAlmostEqual(v.since, 50.0)

    def test_within_fifteen_seconds_of_a_round_step_is_disarmed(self):
        rounds = [(0.0, 1), (45.0, 2)]
        self.assertEqual(vc.score_move_path(self.calls(40.0), self.ALIVE, rounds, now=59.0).status, "disarmed")
        v = vc.score_move_path(self.calls(40.0), self.ALIVE, rounds, now=71.0)
        self.assertEqual(v.status, "stalled")

    def test_stall_clock_restarts_at_the_end_of_the_round_disarm(self):
        rounds = [(0.0, 1), (45.0, 2)]                             # disarm ends at 60
        self.assertEqual(vc.score_move_path(self.calls(40.0), self.ALIVE, rounds, now=61.0).status, "disarmed")
        v = vc.score_move_path(self.calls(40.0), self.ALIVE, rounds, now=70.5)
        self.assertEqual(v.status, "stalled")
        self.assertAlmostEqual(v.since, 60.0)

    def test_alive_rows_only_after_now_is_no_data(self):
        v = vc.score_move_path(self.calls(40.0), [(70.0, 1)], self.ROUND, now=55.0)
        self.assertEqual(v.status, vc.NO_DATA)

    def test_never_logged_slot_is_no_data(self):
        v = vc.score_move_path([], self.ALIVE, self.ROUND, now=100.0)
        self.assertEqual(v.status, vc.NO_DATA)

    def test_stall_without_an_alive_read_is_no_data_not_stalled_or_ok(self):
        v = vc.score_move_path(self.calls(40.0), [], self.ROUND, now=60.0)
        self.assertEqual(v.status, vc.NO_DATA)
        self.assertIn("stall", v.detail)

    def test_stall_without_a_round_read_is_no_data(self):
        self.assertEqual(vc.score_move_path(self.calls(40.0), self.ALIVE, [], now=60.0).status, vc.NO_DATA)

    def test_repeated_index_is_not_an_advance(self):
        calls = self.calls(40.0) + [(45.0, self.calls(40.0)[-1][1]), (49.0, self.calls(40.0)[-1][1])]
        v = vc.score_move_path(calls, self.ALIVE, self.ROUND, now=51.0)
        self.assertEqual(v.status, "stalled")
        self.assertAlmostEqual(v.since, 40.0)

    def test_frost1_fixture_move_path_never_logged_in_window(self):
        p = parsed("frost1_A.txt")
        now = p.peek_rows[-1][0]
        v = vc.score_move_path([(t, n) for t, n, *_ in p.calls.get("MoveScale", [])], [], [], now)
        self.assertEqual(v.status, vc.NO_DATA)

    def test_kill2_fixture_move_path_advancing(self):
        p = parsed("kill2_A_probe.txt")
        now = p.peek_rows[-1][0]
        v = vc.score_move_path([(t, n) for t, n, *_ in p.calls["MoveScale"]], [], [], now)
        self.assertEqual(v.status, "ok")


# ---------------------------------------------------------------------------------------------
class StarvationTest(unittest.TestCase):
    @staticmethod
    def idle(peak=1490.0, at=30.0, n=120):
        return [(i * 0.5, peak if abs(i * 0.5 - at) < 1e-9 else 300.0) for i in range(n)]

    LAG0 = [(i * 0.5, 0) for i in range(120)]

    def test_healthy(self):
        v = vc.score_starvation(self.idle(), self.LAG0, side="A")
        self.assertEqual(v.status, "ok")
        self.assertTrue(v.bar_ok)

    def test_no_netidle_rows_is_no_data(self):
        v = vc.score_starvation([], self.LAG0, side="A")
        self.assertEqual(v.status, vc.NO_DATA)

    def test_netidle_4200_alarms(self):
        v = vc.score_starvation(self.idle(peak=4200.0), self.LAG0, side="B")
        self.assertEqual((v.status, v.side, v.signal), ("alarm", "B", "NetIdle"))
        self.assertAlmostEqual(v.since, 30.0)
        self.assertTrue(v.bar_ok)

    def test_negative_control_3999(self):
        self.assertEqual(vc.score_starvation(self.idle(peak=3999.0), self.LAG0, side="A").status, "ok")

    def test_over_the_bar(self):
        v = vc.score_starvation(self.idle(peak=5200.0), self.LAG0, side="A")
        self.assertEqual(v.status, "alarm")
        self.assertFalse(v.bar_ok)

    def test_lag_flag_alarms(self):
        lag = [(t, 1 if 20.0 <= t < 23.0 else 0) for t, _ in self.LAG0]
        v = vc.score_starvation(self.idle(), lag, side="A")
        self.assertEqual((v.status, v.signal), ("alarm", "ng+0xde"))
        self.assertAlmostEqual(v.since, 20.0)

    def test_monotonic_in_peak(self):
        st = [vc.score_starvation(self.idle(peak=float(p)), self.LAG0, side="A").status
              for p in (0, 1000, 3999, 4000, 4500, 6000, 60000)]
        first = st.index("alarm")
        self.assertTrue(all(s == "alarm" for s in st[first:]), st)
        self.assertEqual(first, 3)

    def test_lag_rows_while_move_path_silent_is_no_data(self):
        mp = vc.MovePathVerdict("stalled", 10.0, "")
        self.assertEqual(vc.score_starvation(self.idle(), self.LAG0, side="A", move_path=mp).status, vc.NO_DATA)

    def test_kill2_fixture_has_no_netidle_trace(self):
        p = parsed("kill2_A_probe.txt")
        rows = [(t, v) for t, n, v in p.rets.get("NetIdleMs", [])]
        self.assertEqual(vc.score_starvation(rows, vc.ng_lagflag_rows(p.peek_rows), side="A").status, vc.NO_DATA)


# ---------------------------------------------------------------------------------------------
class ValveTest(unittest.TestCase):
    NAME = 0x006A1234

    def test_right_name_pointer_reads_the_short(self):
        self.assertEqual(vc.read_valve((0x6A2000, [self.NAME, 0x00010003]), self.NAME), 3)

    def test_value_is_signed(self):
        self.assertEqual(vc.read_valve((0x6A2000, [self.NAME, 0x0001FFFF]), self.NAME), -1)

    def test_wrong_name_pointer_is_no_data(self):
        v = vc.read_valve((0x6A2000, [0x006A9999, 0x00010003]), self.NAME)
        self.assertIsInstance(v, vc.NoData)
        self.assertEqual(v.status, vc.NO_DATA)

    def test_missing_or_short_item_is_no_data(self):
        self.assertIsInstance(vc.read_valve(None, self.NAME), vc.NoData)
        self.assertIsInstance(vc.read_valve((0x6A2000, [self.NAME]), self.NAME), vc.NoData)

    def test_negative_control_zero_value_is_a_value(self):
        self.assertEqual(vc.read_valve((0x6A2000, [self.NAME, 0x00010000]), self.NAME), 0)

    def test_valve_rows_identify_by_name_pointer_not_position(self):
        other = 0x006A5555
        rows = [(1.0, [(0x1, [other, 7]), (0x2, [self.NAME, 2])]),
                (2.0, [(0x2, [self.NAME, 3])]),                        # indices shifted
                (3.0, [(0x1, [other, 9])])]                            # valve chain unresolved
        self.assertEqual(vc.valve_rows(rows, self.NAME), [(1.0, 2), (2.0, 3)])

    def test_lag_flag_from_the_ng_block(self):
        block = [0] * 84
        block[vc.NG_FINGERPRINT_WORD] = vc.NG_FINGERPRINT_VALUE
        block[0xDC // 4] = 0x00010000              # byte +0xde = 1
        other = [0] * 84                           # no fingerprint: not the ng block
        other[0xDC // 4] = 0x00010000
        rows = [(1.0, [(0x1BAD000, other)]), (2.0, [(0x1CE0000, block)])]
        self.assertEqual(vc.ng_lagflag_rows(rows), [(2.0, 1)])

    def test_lag_flag_from_the_ng_block_split_at_the_64_word_cap(self):
        # launch 1's spec: *0x437ce8:64 (+0x000..+0x0fc) and *0x437ce8+0x100:21 (+0x100..+0x150); the
        # 50.0f fingerprint at +0x118 is word 6 of the SECOND item (full log: 0 lag rows before the fix)
        head = [0] * 64
        head[0xDC // 4] = 0x00010000
        tail = [0] * 21
        tail[(0x118 - 0x100) // 4] = vc.NG_FINGERPRINT_VALUE
        decoy = [0] * 21                                   # right shape, wrong address
        decoy[6] = vc.NG_FINGERPRINT_VALUE
        rows = [(1.0, [(0x869360, head), (0x869460, tail)]),
                (2.0, [(0x869360, head), (0x999460, decoy)]),
                (3.0, [(0x869460, tail)])]
        self.assertEqual(vc.ng_lagflag_rows(rows), [(1.0, 1)])

    def test_clock_string(self):
        words = list(struct.unpack("<II", b"05:19\x00\x00\x00"))
        self.assertEqual(vc.clock_rows([(1.0, [(0x408F10, words)])]), [(1.0, "05:19")])


# ---------------------------------------------------------------------------------------------
class ContactTest(unittest.TestCase):
    @staticmethod
    def pair(n=40, gap=15.0, dy=0.0, t0=100.0):
        a = [(t0 + i * PERIOD, 500.0 + i * 0.5, 50.0, 500.0, 1) for i in range(n)]
        b = [(t0 + i * PERIOD + 0.05, 500.0 + i * 0.5 + gap, 50.0 + dy, 500.0, 2) for i in range(n)]
        return a, b

    @staticmethod
    def calls(t0=95.0, t1=112.0, rate=2.0):
        return [(t0 + k / rate, 300 + 10 * k) for k in range(int((t1 - t0) * rate) + 1)]

    @staticmethod
    def clock(t0=95.0, t1=112.0):
        return [(t0 + k * 0.25, f"04:{59 - int(k * 0.25) % 60:02d}") for k in range(int((t1 - t0) * 4) + 1)]

    @staticmethod
    def scales(v=1.0, t0=95.0, t1=112.0):
        return [(t0 + k * 0.5, v) for k in range(int((t1 - t0) * 2) + 1)]

    def score(self, a, b, ca=None, cb=None, clock=None, sa=None, sb=None):
        return vc.score_contact(a, b, self.calls() if ca is None else ca, self.calls() if cb is None else cb,
                                self.clock() if clock is None else clock,
                                (self.scales() if sa is None else sa, self.scales() if sb is None else sb))

    def test_healthy_pair_inside_the_gate(self):
        r = self.score(*self.pair())
        self.assertEqual(r.contact_rows, 40)
        self.assertEqual(r.status, "ok")

    def test_negative_control_outside_the_gate(self):
        self.assertEqual(self.score(*self.pair(gap=23.0)).contact_rows, 0)
        self.assertEqual(self.score(*self.pair(gap=5.0, dy=11.0)).contact_rows, 0)

    def test_monotonic_in_range(self):
        counts = [self.score(*self.pair(gap=float(g))).contact_rows for g in (0, 10, 21, 22, 22.5, 30, 100)]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertGreater(counts[0], 0)
        self.assertEqual(counts[-1], 0)

    def test_row_gap_of_1_06s_bridges_and_1_3s_breaks(self):
        def with_gap(gap):
            a, b = self.pair()
            shift = gap - PERIOD
            a = [(r[0] + (shift if i >= 20 else 0.0), 500.0 + (r[0] + (shift if i >= 20 else 0.0) - 100.0) * 2.0,
                  r[2], r[3], 1) for i, r in enumerate(a)]
            b = [(100.05 + i * PERIOD, 500.0 + (i * PERIOD + 0.05) * 2.0 + 15.0, 50.0, 500.0, 2) for i in range(44)]
            return self.score(a, b).contact_rows
        self.assertEqual(with_gap(1.06), 40)
        self.assertEqual(with_gap(1.3), 20)

    def test_boundary_range_and_dy(self):
        self.assertEqual(self.score(*self.pair(gap=22.0)).contact_rows, 40)
        self.assertEqual(self.score(*self.pair(gap=22.1)).contact_rows, 0)
        self.assertEqual(self.score(*self.pair(gap=5.0, dy=10.0)).contact_rows, 40)
        self.assertEqual(self.score(*self.pair(gap=5.0, dy=10.1)).contact_rows, 0)

    def test_no_pair_ever_formed_is_no_data(self):
        a, b = self.pair()
        b = [(r[0] + 100.0,) + tuple(r[1:]) for r in b]          # misaligned clocks
        r = self.score(a, b)
        self.assertEqual((r.status, r.contact_rows), (vc.NO_DATA, 0))

    def test_a_row_gap_breaks_the_run(self):
        a, b = self.pair()
        a = [row for i, row in enumerate(a) if not 18 <= i < 26]  # 2.25 s without A rows
        self.assertEqual(self.score(a, b).contact_rows, 18)

    def test_stale_b_rows_do_not_extend_the_run(self):
        a, _ = self.pair()
        b = [(tb, 500.0 + (tb - 100.0) * 2.0 + 15.0, 50.0, 500.0, 2)
             for tb in (100.05 + i * 1.3 for i in range(8))]                  # B sampled every 1.3 s (> CONTACT_ROW_MAX_GAP_S)
        self.assertLess(self.score(a, b).contact_rows, 5)

    def test_hung_instance_rows_repeating_clock_frozen(self):
        a, b = self.pair()
        b = [(r[0], b[0][1], b[0][2], b[0][3], 2) for r in b]           # B's rows repeat
        cb = self.calls(t1=99.0)                                         # B's move path stopped
        frozen = [(t, "04:59") for t, _ in self.clock()]
        self.assertEqual(self.score(a, b, cb=cb, clock=frozen).contact_rows, 0)

    def test_frozen_clock_alone_blocks_contact(self):
        frozen = [(t, "04:59") for t, _ in self.clock()]
        self.assertEqual(self.score(*self.pair(), clock=frozen).contact_rows, 0)

    def test_both_scales_zero_inside_the_gate(self):
        self.assertEqual(self.score(*self.pair(), sa=self.scales(0.0), sb=self.scales(0.0)).contact_rows, 0)

    def test_one_scale_starved(self):
        self.assertEqual(self.score(*self.pair(), sb=self.scales(0.5)).contact_rows, 0)

    def test_consecutive_run_is_the_longest_run(self):
        a, b = self.pair()
        b = [(r[0], r[1] + (50.0 if 10 <= i < 12 else 0.0), r[2], r[3], 2) for i, r in enumerate(b)]
        r = self.score(a, b)
        self.assertEqual(r.contact_rows, 28)
        self.assertEqual(r.total_rows, 38)

    def test_no_clock_rows_is_no_data(self):
        r = self.score(*self.pair(), clock=[])
        self.assertEqual((r.status, r.contact_rows), (vc.NO_DATA, 0))

    def test_no_rows_is_no_data(self):
        r = self.score([], [])
        self.assertEqual((r.status, r.contact_rows, r.rows_read), (vc.NO_DATA, 0, 0))

    def test_kill2_closest_approach_is_not_contact(self):
        pa, pb = parsed("kill2_A_closest.txt"), parsed("kill2_B_closest.txt")
        rows_b = [(r[0] + KILL2_B_TO_A_OFFSET_S,) + tuple(r[1:]) for r in pb.actor_rows]
        calls_b = [(t + KILL2_B_TO_A_OFFSET_S, n) for t, n, *_ in pb.calls["MoveScale"]]
        scales_b = [(t + KILL2_B_TO_A_OFFSET_S, f) for t, n, f, *_ in pb.calls["MoveScale"]]
        ca = [(t, n) for t, n, *_ in pa.calls["MoveScale"]]
        sa = [(t, f) for t, n, f, *_ in pa.calls["MoveScale"]]
        t0, t1 = pa.actor_rows[0][0], pa.actor_rows[-1][0]
        ticking = [(t0 + k * 0.25, str(int(k * 0.25))) for k in range(int((t1 - t0) * 4) + 1)]
        r = vc.score_contact(pa.actor_rows, rows_b, ca, calls_b, ticking, (sa, scales_b))
        self.assertEqual(r.status, "ok")
        self.assertGreater(r.rows_read, 100)
        self.assertEqual(r.contact_rows, 0)
        self.assertLess(r.closest_3d, 60.0)          # they were close -- just never inside the gate
        self.assertGreater(r.closest_dy, 10.0)
        # and without a clock peek (Sprint 4 never peeked 0x408f10) the answer is NO-DATA
        self.assertEqual(vc.score_contact(pa.actor_rows, rows_b, ca, calls_b, [], (sa, scales_b)).status, vc.NO_DATA)


# ---------------------------------------------------------------------------------------------
class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = vc.main(list(args))
        return code, out.getvalue()

    def test_score_control_frost1(self):
        code, out = self.run_cli("score-control", os.path.join(FIXTURES, "frost1_A.txt"),
                                 os.path.join(FIXTURES, "frost1_B.txt"))
        self.assertEqual(code, 3, out)
        self.assertIn("RESULT NO-CONTROL", out)
        self.assertIn("rows read", out)

    def test_score_control_kill2(self):
        code, out = self.run_cli("score-control", os.path.join(FIXTURES, "kill2_A_probe.txt"),
                                 os.path.join(FIXTURES, "kill2_B_probe.txt"))
        self.assertEqual(code, 0, out)
        self.assertIn("RESULT CONTROLLABLE", out)

    def test_zero_rows_exits_2(self):
        empty = os.path.join(FIXTURES, "README.md")
        for sub in ("score-control", "move-path", "starvation"):
            code, out = self.run_cli(sub, empty)
            self.assertEqual(code, 2, f"{sub}: {out}")
            self.assertIn("rows read", out)

    def test_starvation_without_netidle_exits_2(self):
        code, out = self.run_cli("starvation", os.path.join(FIXTURES, "kill2_A_probe.txt"))
        self.assertEqual(code, 2, out)
        self.assertIn("NO-DATA", out)

    def test_contact_prints_the_ladder_line(self):
        code, out = self.run_cli("contact", os.path.join(FIXTURES, "kill2_A_closest.txt"),
                                 os.path.join(FIXTURES, "kill2_B_closest.txt"),
                                 "--offset-b", str(KILL2_B_TO_A_OFFSET_S))
        self.assertIn("LADDER contact_rows=0 rows_read=", out)
        self.assertEqual(code, 2, out)               # no clock peek in Sprint 4's logs -> NO-DATA



# =============================================================================================
# Task 3 Steps 1-5: valves by NAME BYTES, actor fields, round state, the R6 stall context
# =============================================================================================
def name_words(text):
    raw = (text.encode("ascii") + b"\0" * 12)[:12]
    return list(struct.unpack("<III", raw))


# research/21 §2.2's expected name-bytes words (verified from spawn_ours3 and every row of launch 1c)
RESEARCH21_NAME_WORDS = {
    "mp_round_count": (0x725F706D, 0x646E756F, 0x756F635F),
    "mp_game_over": (0x675F706D, 0x5F656D61, 0x7265766F),
    "player_team": (0x79616C70, 0x745F7265, 0x006D6165),
    "mp_major_game_state": (0x6D5F706D, 0x726F6A61, 0x6D61675F),
    "mp_minor_game_state": (0x6D5F706D, 0x726F6E69, 0x6D61675F),
    "late_joiner": (0x6574616C, 0x696F6A5F, 0x0072656E),
    "aiteam_00": (0x65746961, 0x305F6D61, 0x00000030),
    "aiteam_08": (0x65746961, 0x305F6D61, 0x00000038),
    "total_mp_kills": (0x61746F74, 0x706D5F6C, 0x6C696B5F),
    "mission_abort": (0x7373696D, 0x5F6E6F69, 0x726F6261),
}
# research/21 §2.1: ours and the console differ by +0x20/+0x30/+0x40
OURS_PTR = {"mp_round_count": 0x006B7F30, "aiteam_00": 0x006CCAD4, "aiteam_08": 0x006CCAEC}
CONSOLE_PTR = {"mp_round_count": 0x006B7F60, "aiteam_00": 0x006CCB14, "aiteam_08": 0x006CCB2C}


def valve_items(name, ptr, value, value_addr=0x694C48):
    """The two peek items of one valve as the exe prints them: `*<ng>+<off>*:2` (word 0 = name
    pointer, low 16 bits of word 1 = value) and `*<ng>+<off>**:3` (printed AT the name pointer)."""
    return [(value_addr, [ptr, 0x00010000 | (value & 0xFFFF)]), (ptr, name_words(name))]


class ValveNameBytesTest(unittest.TestCase):
    def test_table_matches_research21_name_words(self):
        for name, words in RESEARCH21_NAME_WORDS.items():
            with self.subTest(valve=name):
                self.assertIn(name, vc.VALVES)
                self.assertTrue(vc.name_bytes_match(list(words), name))

    def test_by_name_on_ours(self):
        items = valve_items("mp_round_count", OURS_PTR["mp_round_count"], 2)
        self.assertEqual(vc.row_valve(items, "mp_round_count"), 2)

    def test_by_name_on_the_console_pointers_too(self):
        # the class the pointer-only read cannot separate: same valve, platform-shifted pointer
        items = valve_items("mp_round_count", CONSOLE_PTR["mp_round_count"], 1)
        self.assertEqual(vc.row_valve(items, "mp_round_count"), 1)
        self.assertIsInstance(vc.read_valve(items[0], OURS_PTR["mp_round_count"]), vc.NoData)

    def test_read_valve_accepts_identity_by_name_bytes(self):
        value, name = valve_items("aiteam_08", CONSOLE_PTR["aiteam_08"], 3)
        self.assertEqual(vc.read_valve(value, None, name_item=name, expected_name="aiteam_08"), 3)

    def test_wrong_name_bytes_is_no_data(self):
        # aiteam_00 and aiteam_08 differ only in byte 8: a name item for the other one must not do
        value, _ = valve_items("aiteam_08", OURS_PTR["aiteam_08"], 3)
        wrong = (OURS_PTR["aiteam_08"], name_words("aiteam_00"))
        v = vc.read_valve(value, None, name_item=wrong, expected_name="aiteam_08")
        self.assertIsInstance(v, vc.NoData)
        self.assertIsInstance(vc.row_valve([value, wrong], "aiteam_08"), vc.NoData)

    def test_name_item_at_a_different_pointer_is_no_data(self):
        value, name = valve_items("mp_round_count", OURS_PTR["mp_round_count"], 2)
        moved = (name[0] + 0x10, name[1])
        self.assertIsInstance(vc.row_valve([value, moved], "mp_round_count"), vc.NoData)

    def test_read_valve_by_name_rejects_a_value_item_pointing_elsewhere(self):
        value, name = valve_items("mp_round_count", OURS_PTR["mp_round_count"], 2)
        other = (value[0], [OURS_PTR["aiteam_00"], value[1][1]])
        v = vc.read_valve(other, None, name_item=name, expected_name="mp_round_count")
        self.assertIsInstance(v, vc.NoData)
        self.assertEqual(vc.read_valve(value, None, name_item=name, expected_name="mp_round_count"), 2)

    def test_missing_name_item_is_no_data_even_with_the_right_pointer(self):
        value, _ = valve_items("mp_round_count", OURS_PTR["mp_round_count"], 2)
        v = vc.row_valve([value], "mp_round_count")
        self.assertIsInstance(v, vc.NoData)
        self.assertIn("name", v.reason)

    def test_the_double_dereferenced_mission_abort_item_is_no_data(self):
        # launch 1c's `*0x43668c**:3` printed @7373696d (the first name word used as an address)
        value = (0x694D88, [0x006B7FB0, 0x00010000])
        bad = (0x7373696D, [0x00430000, 0x0042C800, 0x00000000])
        self.assertIsInstance(vc.row_valve([value, bad], "mission_abort"), vc.NoData)
        good = (0x006B7FB0, name_words("mission_abort"))
        self.assertEqual(vc.row_valve([value, good], "mission_abort"), 0)

    def test_negative_control_value_zero(self):
        self.assertEqual(vc.row_valve(valve_items("mp_game_over", 0x006B7F20, 0), "mp_game_over"), 0)

    def test_round_state(self):
        items = (valve_items("mp_round_count", 0x006B7F30, 1, 0x694C48)
                 + valve_items("mp_game_over", 0x006B7F20, 0, 0x694C20)
                 + valve_items("aiteam_00", 0x006CCAD4, 4, 0x694C84)
                 + [(0x408F10, list(struct.unpack("<II", b"05:47\x00\x00\x00")))])
        st = vc.row_round_state(items)
        self.assertEqual((st["mp_round_count"], st["mp_game_over"], st["aiteam_00"], st["clock"]),
                         (1, 0, 4, "05:47"))
        self.assertIsInstance(st["aiteam_08"], vc.NoData)


class ActorFieldTest(unittest.TestCase):
    ACTOR = 0x1583F60

    def items(self, alive_word=0x000101A4, stamp=0.0):
        block = [vc.ACTOR_VTABLE] + [0] * 9
        b400 = [0] * 12
        b400[8] = f2w(stamp)
        return [(self.ACTOR, block), (self.ACTOR + 0x400, b400), (self.ACTOR + 0xF78, [alive_word])]

    def test_alive_byte_is_byte_2_of_the_f78_word(self):
        self.assertEqual(vc.row_actor_field(self.items(), vc.ACTOR_ALIVE_OFFSET, "u8"), 1)
        self.assertEqual(vc.row_actor_field(self.items(alive_word=0x000001A4), vc.ACTOR_ALIVE_OFFSET, "u8"), 0)

    def test_stamp_420_is_word_8_of_the_400_block(self):
        self.assertAlmostEqual(vc.row_actor_field(self.items(stamp=3.5), vc.ACTOR_STAMP_OFFSET, "f32"), 3.5)

    def test_uncovered_offset_is_no_data(self):
        items = self.items()[:1]
        self.assertIsInstance(vc.row_actor_field(items, vc.ACTOR_ALIVE_OFFSET, "u8"), vc.NoData)

    def test_block_of_another_actor_is_not_read(self):
        items = [(self.ACTOR, [vc.ACTOR_VTABLE] + [0] * 9), (0x1990000 + 0xF78, [0x00010000])]
        self.assertIsInstance(vc.row_actor_field(items, vc.ACTOR_ALIVE_OFFSET, "u8"), vc.NoData)

    def test_no_actor_block_is_no_data(self):
        self.assertIsInstance(vc.row_actor_field([(0x1584ED8, [0x00010000])], vc.ACTOR_ALIVE_OFFSET, "u8"),
                              vc.NoData)


class Launch1cFixtureTest(unittest.TestCase):
    """launch 1c A (logs/run_A_20260913_073548.log, Frostfire): the move path stopped after
    MoveScale #15 at 380.5 s with actor+0x420 = 0.0 on every row (research/21 §6.4, R6)."""

    @classmethod
    def setUpClass(cls):
        cls.p = parsed("launch1c_A_movestop.txt")

    def test_all_nine_valves_read_by_name_on_every_row(self):
        for name in ("mp_round_count", "mp_game_over", "player_team", "mp_major_game_state",
                     "mp_minor_game_state", "late_joiner", "aiteam_00", "aiteam_08", "total_mp_kills"):
            with self.subTest(valve=name):
                rows = vc.valve_rows_by_name(self.p.peek_rows, name)
                self.assertEqual(len(rows), len(self.p.peek_rows))

    def test_mission_abort_is_no_data_on_every_row_spec_defect(self):
        self.assertEqual(vc.valve_rows_by_name(self.p.peek_rows, "mission_abort"), [])
        self.assertEqual(vc.valve_rows(self.p.peek_rows, vc.VALVES["mission_abort"].ours_name_ptr),
                         [(t, 0) for t, _ in self.p.peek_rows])

    def test_alive_and_stamp_rows(self):
        alive = vc.actor_field_rows(self.p.peek_rows, vc.ACTOR_ALIVE_OFFSET, "u8")
        stamp = vc.actor_field_rows(self.p.peek_rows, vc.ACTOR_STAMP_OFFSET, "f32")
        self.assertEqual(len(alive), len(self.p.actor_rows))
        self.assertEqual({v for _, v in alive}, {1})
        self.assertEqual({v for _, v in stamp}, {0.0})

    def test_move_path_stalled_with_the_r6_context(self):
        p = self.p
        calls = [(t, n) for t, n, *_ in p.calls["MoveScale"]]
        alive = vc.actor_field_rows(p.peek_rows, vc.ACTOR_ALIVE_OFFSET, "u8")
        rounds = vc.valve_rows_by_name(p.peek_rows, "mp_round_count")
        now = p.peek_rows[-1][0]
        v = vc.score_move_path(calls, alive, rounds, now)
        self.assertEqual(v.status, "stalled", v.detail)
        ctx = vc.stall_context(p.peek_rows[-1][1])
        self.assertIn("actor+0x420=0.000", ctx)
        self.assertIn("clock@0x4365c0=10.5", ctx)
        self.assertIn("0x45a0c1=1", ctx)

    def test_stall_context_without_the_items_says_so(self):
        self.assertIn("not peeked", vc.stall_context([]))

    def test_cli_move_path_reads_alive_and_round_by_name(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = vc.main(["move-path", os.path.join(FIXTURES, "launch1c_A_movestop.txt")])
        self.assertEqual(code, 1, out.getvalue())
        self.assertIn("MOVE-PATH stalled", out.getvalue())
        self.assertIn("actor+0x420=0.000", out.getvalue())

    def test_cli_starvation_finds_the_netidle_slot_under_its_launch_name(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            vc.main(["starvation", os.path.join(FIXTURES, "launch1c_A_movestop.txt")])
        self.assertIn("NetIdle rows=16", out.getvalue())

if __name__ == "__main__":
    unittest.main()
