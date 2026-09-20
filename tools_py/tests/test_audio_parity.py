"""Sprint 9 Q0 (owner, 2026-09-20): "an audio parity test with PCSX2 like our visual parity test." The pure half:
step windows from a drive's step times, per-window scores, and a comparison that can fail."""
import json
import os
import tempfile
import unittest

import numpy as np

from tools_py.parity import audio_parity as ap

RATE = 48000


def tone(seconds, hz=440.0, level=0.2, rate=RATE):
    t = np.arange(int(seconds * rate)) / rate
    return (np.sin(2 * np.pi * hz * t) * level * 32767).astype(np.float64)


class WindowsTest(unittest.TestCase):
    def test_step_windows_come_from_the_drives_step_times_and_end_at_the_next_step(self):
        stdout = "s00_CROSS   t=   4.8s stable=True\ns01_CROSS   t=  12.0s stable=True\ns02_none    t=  20.5s stable=True\n"
        w = ap.step_windows(stdout, capture_offset_s=1.0)
        self.assertEqual([x.label for x in w], ["s00", "s01", "s02"])
        self.assertAlmostEqual(w[0].start, 5.8)
        self.assertAlmostEqual(w[0].end, 13.0)
        self.assertAlmostEqual(w[2].start, 21.5)
        self.assertIsNone(w[2].end, "the last step runs to the end of the capture")


class ScoreTest(unittest.TestCase):
    def test_a_window_is_scored_for_level_silence_holes_splices_and_oscillation(self):
        audio = np.concatenate([tone(2.0), np.zeros(int(0.1 * RATE)), tone(2.0)])
        s = ap.score_window(audio, RATE)
        self.assertGreater(s["rms_db"], -30.0)
        self.assertEqual(s["silences"], 1)
        self.assertEqual(s["holes"], 1, "a 100 ms gap is a sub-second hole")
        self.assertIn("splices", s)
        self.assertIn("osc", s)

    def test_an_empty_or_silent_window_scores_without_crashing(self):
        s = ap.score_window(np.zeros(RATE), RATE)
        self.assertLess(s["rms_db"], -80.0)
        self.assertEqual(s["holes"], 0)


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.ref = {"s10": {"rms_db": -25.0, "silences": 0, "silence_s": 0.0, "holes": 0, "splices": 10, "osc": 2.0},
                    "s11": {"rms_db": -30.0, "silences": 1, "silence_s": 0.7, "holes": 0, "splices": 4, "osc": 1.0}}

    def test_ours_within_tolerance_passes_every_window(self):
        ours = {"s10": {"rms_db": -27.0, "silences": 0, "silence_s": 0.0, "holes": 1, "splices": 12, "osc": 2.5},
                "s11": {"rms_db": -31.0, "silences": 1, "silence_s": 0.9, "holes": 0, "splices": 5, "osc": 1.2}}
        verdict = ap.compare(self.ref, ours)
        self.assertTrue(verdict.passed, verdict.lines)
        self.assertEqual(len(verdict.failures), 0)

    def test_the_device_dropouts_of_2026_09_20_would_have_failed_the_first_run(self):
        ours = dict(self.ref)
        ours["s10"] = {"rms_db": -25.0, "silences": 41, "silence_s": 5.0, "holes": 41, "splices": 60, "osc": 9.0}
        verdict = ap.compare(self.ref, ours)
        self.assertFalse(verdict.passed)
        self.assertTrue(any("s10" in f and "holes" in f for f in verdict.failures), verdict.failures)

    def test_a_window_missing_on_our_side_is_a_failure_not_a_pass(self):
        ours = {"s10": self.ref["s10"]}
        verdict = ap.compare(self.ref, ours)
        self.assertFalse(verdict.passed)
        self.assertTrue(any("s11" in f for f in verdict.failures))

    def test_scores_round_trip_through_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ref.json")
            ap.save_scores(self.ref, p, meta={"target": "pcsx2", "script": "launch_to_mission.txt"})
            loaded, meta = ap.load_scores(p)
            self.assertEqual(loaded, self.ref)
            self.assertEqual(meta["target"], "pcsx2")


if __name__ == "__main__":
    unittest.main()
