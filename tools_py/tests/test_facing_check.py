"""Sprint 5 Task 2 Step 1 -- `tools_py.parity.facing_check`.

unittest only (no pytest, no module-level `def test_`). Two kinds of input, matching
test_online_verdict.py's own convention:
  * synthetic rows built here, one gate per test, with the error known by construction;
  * one small synthetic log built as text, run through the real parse_log/forward_holds path, to
    check the module's own extraction (camera-by-address, actor-by-vtable) end to end.
"""
import math
import struct
import unittest

from tools_py.parity import facing_check as fc
from tools_py.parity import verdict_core as vc


def f2w(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def hexf(v):
    return f"{f2w(v):08x}({v})"


# ---------------------------------------------------------------------------------------------
# geometry, built directly on (t, x, y, z[, addr]) rows -- the error is known by construction
# ---------------------------------------------------------------------------------------------
class KnownErrorTest(unittest.TestCase):
    def test_estimate_truth_error_and_radius(self):
        # Camera fixed at the origin; the actor rests at (20, 0, 0) -- estimate = atan2(0, 20) = 0,
        # radius = 20. It then walks to (50, 0, 40): truth = atan2(40, 30) ~= 53.13 deg, so the
        # signed, wrapped error is exactly -atan2(40, 30) in degrees.
        actor_series = [(t, 20.0, 0.0, 0.0, 0xAAA) for t in (90.0, 95.0, 100.0)]
        actor_series.append((102.0, 50.0, 0.0, 40.0, 0xAAA))
        camera_series = [(t, 0.0, 0.0, 0.0) for t in (90.0, 95.0, 100.0, 102.0)]
        hold = vc.Hold(100.0, 102.0)

        s = fc.build_sample("synthetic", "A", actor_series, camera_series, hold)

        self.assertTrue(s.used, s.reason)
        expect_truth = math.degrees(math.atan2(40.0, 30.0))
        self.assertAlmostEqual(s.estimate_deg, 0.0, places=6)
        self.assertAlmostEqual(s.truth_deg, expect_truth, places=6)
        self.assertAlmostEqual(s.error_deg, fc.wrap_deg(0.0 - expect_truth), places=6)
        self.assertAlmostEqual(s.camera_radius, 20.0, places=6)
        self.assertFalse(s.stale)

    def test_wrap_deg_wraps_to_plus_minus_180(self):
        self.assertAlmostEqual(fc.wrap_deg(190.0), -170.0, places=6)
        self.assertAlmostEqual(fc.wrap_deg(-190.0), 170.0, places=6)
        self.assertAlmostEqual(fc.wrap_deg(180.0), -180.0, places=6)
        self.assertAlmostEqual(fc.wrap_deg(0.0), 0.0, places=6)


# ---------------------------------------------------------------------------------------------
# the gates, one hazard per test
# ---------------------------------------------------------------------------------------------
class GatesTest(unittest.TestCase):
    def test_stale_camera_excludes_even_though_at_rest_bar_would_also_fail(self):
        # Camera bit-frozen at (0, 50, 0) across the whole rest window while the actor's z climbs
        # 0 -> 60 (path length 60, comfortably over STALE_ACTOR_PATH_MIN_UNITS) -- the KNOWN.md
        # 2026-09-13 kill3 B shape. Both this gate and the plain "not at rest" gate would fire;
        # stale must win and be named, not the generic one.
        actor_series = [
            (90.0, 0.0, 0.0, 0.0, 0xAAA), (93.0, 0.0, 0.0, 20.0, 0xAAA),
            (96.0, 0.0, 0.0, 40.0, 0xAAA), (100.0, 0.0, 0.0, 60.0, 0xAAA),
            (102.0, 0.0, 0.0, 110.0, 0xAAA),
        ]
        camera_series = [(t, 0.0, 50.0, 0.0) for t in (90.0, 93.0, 96.0, 100.0, 102.0)]
        hold = vc.Hold(100.0, 102.0)

        s = fc.build_sample("synthetic", "A", actor_series, camera_series, hold)

        self.assertFalse(s.used)
        self.assertEqual(s.reason, fc.REASON_STALE_CAMERA)
        self.assertTrue(s.stale)

    def test_same_actor_motion_without_a_frozen_camera_is_not_at_rest_not_stale(self):
        # Same actor path as above, but the camera keeps pace (not bit-identical) -- this is
        # ordinary motion before the hold, not a freeze, so it must fall through to the plain
        # "not at rest" gate instead.
        actor_series = [
            (90.0, 0.0, 0.0, 0.0, 0xAAA), (93.0, 0.0, 0.0, 20.0, 0xAAA),
            (96.0, 0.0, 0.0, 40.0, 0xAAA), (100.0, 0.0, 0.0, 60.0, 0xAAA),
            (102.0, 0.0, 0.0, 110.0, 0xAAA),
        ]
        camera_series = [
            (90.0, 0.0, 50.0, -20.0), (93.0, 0.0, 50.0, 0.0),
            (96.0, 0.0, 50.0, 20.0), (100.0, 0.0, 50.0, 40.0), (102.0, 0.0, 50.0, 90.0),
        ]
        hold = vc.Hold(100.0, 102.0)

        s = fc.build_sample("synthetic", "A", actor_series, camera_series, hold)

        self.assertFalse(s.used)
        self.assertEqual(s.reason, fc.REASON_NOT_AT_REST)
        self.assertFalse(s.stale)

    def test_degenerate_displacement_excluded(self):
        actor_series = [(t, 20.0, 0.0, 0.0, 0xAAA) for t in (90.0, 95.0, 100.0)]
        actor_series.append((102.0, 20.5, 0.0, 0.5, 0xAAA))   # ~0.7 units -- below the bar
        camera_series = [(t, 0.0, 0.0, 0.0) for t in (90.0, 95.0, 100.0, 102.0)]
        hold = vc.Hold(100.0, 102.0)

        s = fc.build_sample("synthetic", "A", actor_series, camera_series, hold)

        self.assertFalse(s.used)
        self.assertEqual(s.reason, fc.REASON_DEGENERATE)

    def test_actor_repointed_during_rest_window_excluded(self):
        # A respawn (or any block re-point) inside the rest window makes the "was it at rest"
        # question unanswerable from these rows -- excluded rather than silently measured across
        # two different actor blocks.
        actor_series = [
            (90.0, 20.0, 0.0, 0.0, 0x111), (95.0, 20.0, 0.0, 0.0, 0x222),
            (100.0, 20.0, 0.0, 0.0, 0x222), (102.0, 50.0, 0.0, 40.0, 0x222),
        ]
        camera_series = [(t, 0.0, 0.0, 0.0) for t in (90.0, 95.0, 100.0, 102.0)]
        hold = vc.Hold(100.0, 102.0)

        s = fc.build_sample("synthetic", "A", actor_series, camera_series, hold)

        self.assertFalse(s.used)
        self.assertEqual(s.reason, fc.REASON_REPOINTED)

    def test_no_row_near_start_excluded(self):
        actor_series = [(50.0, 20.0, 0.0, 0.0, 0xAAA)]   # 50s stale by the time the hold starts
        camera_series = [(50.0, 0.0, 0.0, 0.0)]
        hold = vc.Hold(100.0, 102.0)

        s = fc.build_sample("synthetic", "A", actor_series, camera_series, hold)

        self.assertFalse(s.used)
        self.assertEqual(s.reason, fc.REASON_NO_ROW_AT_START)

    def test_no_row_near_release_excluded(self):
        actor_series = [(t, 20.0, 0.0, 0.0, 0xAAA) for t in (90.0, 95.0, 100.0)]
        # nothing between hold start (100) and release (102) -- last row is > ROW_MAX_GAP_S stale
        camera_series = [(t, 0.0, 0.0, 0.0) for t in (90.0, 95.0, 100.0)]
        hold = vc.Hold(100.0, 102.0)

        s = fc.build_sample("synthetic", "A", actor_series, camera_series, hold)

        self.assertFalse(s.used)
        self.assertEqual(s.reason, fc.REASON_NO_ROW_AT_RELEASE)

    def test_hold_shorter_than_bar_excluded_before_geometry(self):
        # No peek rows at all -- if the length gate did not run first, this would blow up trying
        # to read actor/camera rows that do not exist, instead of naming the real reason.
        lines = [
            "[socom2-input] state buttons=0000 rx=80 ry=80 lx=80 ly=00",
            "[socom2-input] state buttons=0000 rx=80 ry=80 lx=80 ly=80",
        ]
        samples = fc.analyze_log(lines, "synthetic", "A")
        self.assertEqual(len(samples), 1)
        self.assertFalse(samples[0].used)
        self.assertEqual(samples[0].reason, fc.REASON_HOLD_TOO_SHORT)


# ---------------------------------------------------------------------------------------------
# end to end: a tiny synthetic log through the real parse_log / forward_holds path
# ---------------------------------------------------------------------------------------------
def peek_line(cam_xyz, actor_xyz, actor_addr="17941d0"):
    cam_words = " ".join(hexf(v) for v in cam_xyz)
    actor_words = [hexf(0.0)] * 10   # word 0 overwritten below with the vtable
    actor_words[0] = f"{vc.ACTOR_VTABLE:08x}(0)"
    for i, v in zip(vc.ACTOR_POS_WORDS, actor_xyz):
        actor_words[i] = hexf(v)
    return f"[peek] @416054: {cam_words} @{actor_addr}: " + " ".join(actor_words)


class EndToEndSyntheticLogTest(unittest.TestCase):
    def test_one_clean_probe_is_extracted_and_scored(self):
        # Camera fixed away from the origin (not (0, 0, 0) -- that reads as "not yet populated"
        # and is filtered, same convention parse_log itself uses for the actor).
        cam = (1000.0, 0.0, 0.0)
        lines = []
        # 10 s of rest: actor at (1020, 0, 0), one row per second -- well inside REST_WINDOW_S and
        # comfortably under ROW_MAX_GAP_S between rows.
        for i in range(11):
            lines.append(peek_line(cam, (1020.0, 0.0, 0.0)))
        lines.append("[socom2-input] state buttons=0000 rx=80 ry=80 lx=80 ly=00")   # hold starts
        # the hold: actor walks from (1020, 0, 0) to (1050, 0, 40) over six rows (1.5s at 4 Hz --
        # comfortably over MIN_HOLD_S so the length gate does not eat this probe).
        for i in range(1, 7):
            f = i / 6.0
            lines.append(peek_line(cam, (1020.0 + f * 30.0, 0.0, f * 40.0)))
        lines.append("[socom2-input] state buttons=0000 rx=80 ry=80 lx=80 ly=80")   # released

        samples = fc.analyze_log(lines, "synthetic", "A")

        used = [s for s in samples if s.used]
        self.assertEqual(len(used), 1, [(s.reason, s.detail) for s in samples if not s.used])
        s = used[0]
        expect_truth = math.degrees(math.atan2(40.0, 30.0))
        self.assertAlmostEqual(s.estimate_deg, 0.0, places=3)
        self.assertAlmostEqual(s.truth_deg, expect_truth, places=3)
        self.assertAlmostEqual(s.camera_radius, 20.0, places=3)
        self.assertFalse(s.stale)


# ---------------------------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------------------------
class SummarizeTest(unittest.TestCase):
    def _sample(self, err, used=True, reason=""):
        return fc.Sample(run="r", side="A", t=0.0, used=used, reason=reason, error_deg=err)

    def test_percentile_matches_hand_computation(self):
        errs = sorted(float(v) for v in range(11))   # 0..10
        # p90 of 0..10 (11 values): k = 10*0.9 = 9.0 -> exact index 9 -> 9.0
        self.assertAlmostEqual(fc._percentile(errs, 0.90), 9.0, places=6)

    def test_summarize_counts_used_and_excluded_reasons(self):
        samples = [
            self._sample(1.0), self._sample(3.0), self._sample(-2.0),
            self._sample(None, used=False, reason=fc.REASON_NOT_AT_REST),
            self._sample(None, used=False, reason=fc.REASON_NOT_AT_REST),
            self._sample(None, used=False, reason=fc.REASON_STALE_CAMERA),
        ]
        stats = fc.summarize(samples)
        self.assertEqual(stats["n_used"], 3)
        self.assertEqual(stats["n_excluded"], 3)
        self.assertEqual(stats["reasons"][fc.REASON_NOT_AT_REST], 2)
        self.assertEqual(stats["reasons"][fc.REASON_STALE_CAMERA], 1)
        self.assertAlmostEqual(stats["mean"], (1.0 + 3.0 + 2.0) / 3, places=6)
        self.assertAlmostEqual(stats["median"], 2.0, places=6)
        self.assertAlmostEqual(stats["max"], 3.0, places=6)

    def test_sign_convention_reports_constant_180_offset(self):
        used = [self._sample(179.0), self._sample(-178.0), self._sample(180.0)]
        msg = fc.sign_convention_report(used)
        self.assertIn("180", msg)

    def test_sign_convention_reports_consistent_near_zero(self):
        used = [self._sample(1.0), self._sample(-2.0), self._sample(3.0)]
        msg = fc.sign_convention_report(used)
        self.assertIn("0 deg", msg)

    def test_sign_convention_reports_inconsistent_mix(self):
        used = [self._sample(1.0), self._sample(179.0)]
        msg = fc.sign_convention_report(used)
        self.assertIn("NOT a constant offset", msg)


if __name__ == "__main__":
    unittest.main()
