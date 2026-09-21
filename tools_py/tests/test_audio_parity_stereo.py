"""Sprint 10 round four (2026-09-20): the CONTENT measure the level scores could not see. Ours played the two
channels of every stereo VAG stream out of sync (R at +61 / -561 / +674 ms from L) and the per-window rms,
silences, holes, splices and osc all passed. `lr_corr0 / lr_lag_ms / lr_best / side_mid_db` per window, and
the stereo-desync compare rule, on synthetic wavs written to a temp dir."""
import json
import os
import tempfile
import unittest
import wave

import numpy as np

from tools_py.parity import audio_parity as ap

RATE = 48000
SECONDS = 6.0
DRIVE_STDOUT = "s00_MUSIC   t=   0.0s stable=True\n"     # one window, the whole capture


def noise(seconds, level=0.2, seed=1, rate=RATE):
    """White noise, seeded: a tone's correlation is periodic and would put the best lag anywhere."""
    rng = np.random.default_rng(seed)
    return rng.standard_normal(int(seconds * rate)) * level * 32767 / 3.0


def delayed(x, ms, rate=RATE):
    """`x` shifted later by `ms` (zeros in front), the same length."""
    n = int(round(ms / 1000.0 * rate))
    return np.concatenate([np.zeros(n), x[:len(x) - n]])


def write_wav(path, channels, rate=RATE):
    """`channels`: a list of float arrays (one = mono, two = stereo), written as 16-bit PCM."""
    frames = np.stack(channels, axis=1) if len(channels) > 1 else channels[0][:, None]
    data = np.clip(np.round(frames), -32768, 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(len(channels))
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)


def score_file(d, name, channels):
    """Run the real `score` command on a wav and return its one window's scores and the meta."""
    wav = os.path.join(d, name + ".wav")
    stdout = os.path.join(d, name + ".stdout")
    out = os.path.join(d, name + ".json")
    write_wav(wav, channels)
    with open(stdout, "w", encoding="utf-8") as fh:
        fh.write(DRIVE_STDOUT)
    rc = ap.main(["audio_parity", "score", wav, str(RATE), stdout, "0", out, "--target", "ours"])
    assert rc == 0
    with open(out, encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc["scores"]["s00"], doc["meta"]


class AlignmentTest(unittest.TestCase):
    def test_r_delayed_by_300_ms_reads_as_a_positive_300_ms_lag(self):
        left = noise(SECONDS)
        corr0, lag_ms, best = ap.lr_alignment(left, delayed(left, 300), RATE)
        self.assertAlmostEqual(lag_ms, 300.0, delta=1.0, msg="positive = R lags L")
        self.assertGreater(best, 0.9)
        self.assertLessEqual(best, 1.0, "normalised over the overlap: R's leading zeros cannot push it past 1")
        self.assertLess(abs(corr0), 0.1, "white noise against its own delayed copy is uncorrelated at lag 0")

    def test_l_delayed_reads_as_a_negative_lag(self):
        right = noise(SECONDS)
        _, lag_ms, _ = ap.lr_alignment(delayed(right, 120), right, RATE)
        self.assertAlmostEqual(lag_ms, -120.0, delta=1.0)

    def test_an_identical_pair_correlates_fully_at_lag_zero(self):
        x = noise(SECONDS)
        corr0, lag_ms, best = ap.lr_alignment(x, x, RATE)
        self.assertAlmostEqual(corr0, 1.0, places=3)
        self.assertEqual(lag_ms, 0.0)
        self.assertAlmostEqual(best, 1.0, places=3)

    def test_a_silent_channel_reads_as_nothing_to_align(self):
        self.assertEqual(ap.lr_alignment(noise(SECONDS), np.zeros(int(SECONDS * RATE)), RATE), (0.0, 0.0, 0.0))

    def test_the_lag_search_is_capped_at_two_seconds_and_half_the_window(self):
        left = noise(SECONDS)
        _, lag_ms, best = ap.lr_alignment(left, delayed(left, 2500), RATE)
        self.assertLessEqual(abs(lag_ms), 2000.0)
        self.assertLess(best, 0.5, "a 2.5 s offset is outside the search and cannot be the best lag")


class SideMidTest(unittest.TestCase):
    def test_identical_pair_is_all_mid_and_an_inverted_pair_all_side(self):
        x = noise(SECONDS)
        self.assertEqual(ap.side_mid_db(x, x), -90.0)
        self.assertEqual(ap.side_mid_db(x, -x), 90.0)

    def test_an_uncorrelated_pair_of_equal_power_reads_about_zero(self):
        self.assertAlmostEqual(ap.side_mid_db(noise(SECONDS, seed=1), noise(SECONDS, seed=2)), 0.0, delta=0.5)


class StereoWindowTest(unittest.TestCase):
    def test_a_short_window_reports_null(self):
        x = noise(1.5)
        self.assertEqual(ap.stereo_window(x, x, RATE), ap.STEREO_NULL)

    def test_a_quiet_window_reports_null(self):
        x = noise(SECONDS, level=0.0002)     # about -80 dBFS
        self.assertEqual(ap.stereo_window(x, x, RATE), ap.STEREO_NULL)

    def test_score_capture_without_a_pair_carries_the_keys_as_null(self):
        x = noise(SECONDS)
        scores = ap.score_capture(x, RATE, ap.step_windows(DRIVE_STDOUT))
        for k in ap.STEREO_KEYS:
            self.assertIsNone(scores["s00"][k])
        self.assertIn("rms_db", scores["s00"])


class ScoreAndCompareTest(unittest.TestCase):
    """Through the real `score` command (wav on disk, drive stdout, JSON out) and then `compare`."""

    def setUp(self):
        self.ref = {"s00": {"rms_db": -25.0, "silences": 0, "silence_s": 0.0, "holes": 0, "splices": 0, "osc": 1.0,
                            "lr_corr0": 0.4, "lr_lag_ms": 0.0, "lr_best": 0.4, "side_mid_db": -2.0}}

    def test_r_delayed_by_300_ms_scores_the_lag_and_fails_compare_as_a_stereo_desync(self):
        left = noise(SECONDS)
        with tempfile.TemporaryDirectory() as d:
            s, meta = score_file(d, "desync", [left, delayed(left, 300)])
        self.assertEqual(meta["channels"], 2)
        self.assertAlmostEqual(s["lr_lag_ms"], 300.0, delta=1.0)
        self.assertGreater(s["lr_best"], 0.9)
        self.assertLess(abs(s["lr_corr0"]), 0.05)
        self.assertAlmostEqual(s["side_mid_db"], 0.0, delta=0.5)
        ours = {"s00": dict(s, rms_db=-25.0, osc=1.0, splices=0)}     # only the stereo rule is under test
        v = ap.compare(self.ref, ours)
        self.assertFalse(v.passed)
        self.assertEqual(len(v.failures), 1)
        self.assertIn("stereo desync: ours best +300 ms (corr ", v.failures[0])
        self.assertIn(", lag0 ", v.failures[0])
        self.assertIn(") vs ref lag0 0.40", v.failures[0])
        self.assertEqual(v.stereo_skipped, 0)
        self.assertFalse(any(line.startswith("NOTE") for line in v.lines))

    def test_the_same_wav_with_r_equal_to_l_passes(self):
        left = noise(SECONDS)
        with tempfile.TemporaryDirectory() as d:
            s, _ = score_file(d, "aligned", [left, left.copy()])
        self.assertAlmostEqual(s["lr_corr0"], 1.0, places=2)
        self.assertEqual(s["lr_lag_ms"], 0.0)
        self.assertEqual(s["side_mid_db"], -90.0)
        ours = {"s00": dict(s, rms_db=-25.0, osc=1.0, splices=0)}
        v = ap.compare(self.ref, ours)
        self.assertTrue(v.passed, v.lines)
        self.assertIn("lr0 1.0/0.4", v.lines[0])

    def test_a_mono_wav_reports_null_and_the_rule_is_skipped_with_a_note(self):
        with tempfile.TemporaryDirectory() as d:
            s, meta = score_file(d, "mono", [noise(SECONDS)])
        self.assertEqual(meta["channels"], 1)
        for k in ap.STEREO_KEYS:
            self.assertIn(k, s)
            self.assertIsNone(s[k])
        ours = {"s00": dict(s, rms_db=-25.0, osc=1.0, splices=0)}
        v = ap.compare(self.ref, ours)
        self.assertTrue(v.passed, v.lines)
        self.assertEqual(v.stereo_skipped, 1)
        self.assertEqual(sum(1 for line in v.lines if line.startswith("NOTE")), 1)
        self.assertIn("skipped on 1/1 windows", v.lines[-1])

    def test_a_reference_pinned_before_the_measure_still_compares(self):
        old_ref = {"s00": {"rms_db": -25.0, "silences": 0, "silence_s": 0.0, "holes": 0, "splices": 0, "osc": 1.0}}
        ours = {"s00": dict(old_ref["s00"], lr_corr0=0.01, lr_lag_ms=61.0, lr_best=0.22, side_mid_db=0.1)}
        v = ap.compare(old_ref, ours)
        self.assertTrue(v.passed, v.lines)
        self.assertEqual(v.stereo_skipped, 1)
        self.assertTrue(v.lines[-1].startswith("NOTE stereo alignment rule skipped on 1/1"))

    def test_ours_decorrelated_everywhere_is_not_a_desync(self):
        ours = {"s00": dict(self.ref["s00"], lr_corr0=0.01, lr_lag_ms=500.0, lr_best=0.08)}
        v = ap.compare(self.ref, ours)
        self.assertTrue(v.passed, v.lines)

    def test_ours_aligned_at_lag_zero_but_better_elsewhere_is_not_a_desync(self):
        ours = {"s00": dict(self.ref["s00"], lr_corr0=0.3, lr_lag_ms=61.0, lr_best=0.5)}
        v = ap.compare(self.ref, ours)
        self.assertTrue(v.passed, v.lines)

    def test_the_documented_example_reads_as_documented(self):
        ours = {"s00": dict(self.ref["s00"], lr_corr0=0.05 - 1e-9, lr_lag_ms=61.0, lr_best=0.22)}
        ref = {"s00": dict(self.ref["s00"], lr_corr0=0.26)}
        v = ap.compare(ref, ours)
        self.assertEqual(v.failures, ["s00: stereo desync: ours best +61 ms (corr 0.22, lag0 0.05) vs ref lag0 0.26"])


if __name__ == "__main__":
    unittest.main()
