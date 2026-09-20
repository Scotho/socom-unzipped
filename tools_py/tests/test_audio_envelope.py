"""Defect-injection tests for the reference-free audio symptom instrument.

Every signal here is synthetic: the point of `tools_py/parity/audio_envelope.py` is that it needs no
reference, so its tests must not need a fixture either. Each test injects exactly one of the defects the
owner reported ("getting louder and quieter", "jumping between tracks / glitched between samples", a
stream underrun) into a clean bed and asserts that the matching measurement -- and only it -- moves.
"""
import io
import os
import shutil
import struct
import tempfile
import unittest
import wave

import numpy as np

from tools_py.parity import audio_envelope as ae

RATE = 48000
BED_HZ = 220.25          # not a whole number of cycles per second: the hard cut lands near a peak
BED_AMP = 6000.0
BED_NOISE = 150.0


def bed(seconds=2.0, rate=RATE, seed=1234):
    """A steady tone bed with a little noise: the 'nothing wrong' signal every defect is injected into."""
    n = int(round(seconds * rate))
    t = np.arange(n, dtype=np.float64) / float(rate)
    rng = np.random.default_rng(seed)
    return BED_AMP * np.sin(2.0 * np.pi * BED_HZ * t) + rng.normal(0.0, BED_NOISE, n)


def fade(x, rate, at_s, length_s, rising):
    """Raised-cosine fade of `length_s` starting at `at_s`, in place."""
    start = int(round(at_s * rate))
    count = int(round(length_s * rate))
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(count, dtype=np.float64) / float(count))
    x[start:start + count] *= ramp if rising else ramp[::-1]


class TestEnvelope(unittest.TestCase):
    def test_windows_are_regular_and_report_the_level(self):
        env = ae.envelope(bed(1.0), RATE, window_s=0.05)
        self.assertEqual(len(env), 20)
        self.assertAlmostEqual(env[0][0], 0.0, places=9)
        self.assertAlmostEqual(env[1][0], 0.05, places=9)
        # a 6000-count tone plus 150 counts of noise: rms ~4245 of 32768, about -17.8 dBFS
        self.assertTrue(all(-19.0 < db < -16.5 for _, db in env), env)


class TestOscillation(unittest.TestCase):
    """'Getting louder and quieter' against music that simply has dynamics."""

    def test_steady_bed_scores_low_and_modulated_bed_scores_high(self):
        steady = ae.oscillation_score(ae.envelope(bed(4.0), RATE))
        t = np.arange(int(4.0 * RATE), dtype=np.float64) / float(RATE)
        wobbled = bed(4.0) * 10.0 ** (6.0 * np.sin(2.0 * np.pi * 1.0 * t) / 20.0)
        moving = ae.oscillation_score(ae.envelope(wobbled, RATE))
        self.assertLess(steady, 0.5, "a steady bed must not read as oscillating")
        # +/- 6 dB of swing is 6/sqrt(2) = 4.24 dB rms in the band
        self.assertGreater(moving, 3.0)
        self.assertGreater(moving, 20.0 * steady)

    def test_a_slow_fade_is_not_an_oscillation(self):
        """Music that rises over 20 s is normal dynamics: below the 0.2 Hz band edge, so it must not score."""
        n = int(20.0 * RATE)
        ramp = 10.0 ** (np.linspace(-12.0, 0.0, n) / 20.0)
        self.assertLess(ae.oscillation_score(ae.envelope(bed(20.0) * ramp, RATE)), 0.5)


class TestSplices(unittest.TestCase):
    """'Jumping between tracks / glitched between different samples'."""

    def test_clean_bed_has_no_splices(self):
        self.assertEqual(ae.splices(bed(2.0), RATE), [])

    def test_a_sound_starting_after_quiet_is_not_a_step(self):
        """The failure mode the real dump exposed: a gunshot beginning after a quiet passage.

        Judged only against the 20 ms *before* it, the first sample of a loud sound towers over near
        silence and reads as a discontinuity -- on mission_audio_playable.wav that produced 210 'splices'
        that were all onsets. A real join is anomalous against both sides; an onset is not, because the
        material that follows it has larger sample-to-sample differences than the join itself.
        """
        rng = np.random.default_rng(99)
        n = int(2.0 * RATE)
        t = np.arange(n, dtype=np.float64) / float(RATE)
        x = 300.0 * np.sin(2.0 * np.pi * BED_HZ * t) + rng.normal(0.0, 20.0, n)
        onset = int(1.0 * RATE)
        x[onset:] += rng.normal(0.0, 8000.0, n - onset)      # loud broadband, starting instantly
        self.assertGreater(abs(x[onset] - x[onset - 1]), ae.STEP_FLOOR,
                           "the onset must clear the absolute floor, or the test proves nothing")
        self.assertEqual([s for s in ae.splices(x, RATE) if s[1] == "step"], [])

    def test_hard_cut_is_exactly_one_splice_at_its_own_second(self):
        x = bed(2.0)
        cut = int(1.0 * RATE)
        x[cut:] = -0.6 * (x[cut:] - 0.0)      # phase flipped and 4.4 dB down: a different sample, mid-waveform
        found = ae.splices(x, RATE)
        self.assertEqual(len(found), 1, found)
        t, kind, magnitude = found[0]
        self.assertLess(abs(t - 1.0), 0.020, "splice reported at %.4f s" % t)
        self.assertIn(kind, ("step", "flux"))
        self.assertGreater(magnitude, 0.0)


def spectral_jump(seconds=2.0, at_s=1.0, rate=RATE, lo_hz=220.0, hi_hz=1500.0):
    """Two different samples joined at a zero crossing: the waveform is continuous, the content is not.

    This is the 'glitched between different samples' case that carries no sample-value step at all, so
    only the spectral-flux detector can see it.
    """
    n = int(round(seconds * rate))
    cut = int(round(at_s * rate))
    t = np.arange(n, dtype=np.float64) / float(rate)
    x = BED_AMP * np.sin(2.0 * np.pi * lo_hz * t)
    x[cut:] = BED_AMP * np.sin(2.0 * np.pi * hi_hz * (t[cut:] - at_s))
    return x


class TestSpectralFlux(unittest.TestCase):
    def test_a_content_change_with_no_step_is_one_flux_splice(self):
        x = spectral_jump()
        self.assertLess(abs(x[int(1.0 * RATE)] - x[int(1.0 * RATE) - 1]), ae.STEP_FLOOR,
                        "the join must be continuous in value, or this is not a flux-only test")
        found = ae.splices(x, RATE)
        self.assertEqual(len(found), 1, found)
        t, kind, _ = found[0]
        self.assertEqual(kind, "flux")
        self.assertLess(abs(t - 1.0), 0.020, "flux splice reported at %.4f s" % t)

    def test_leading_silence_does_not_change_what_is_found(self):
        """A capture that starts with five seconds of nothing must report the same faults as one that
        does not. The mission dump is 52% digital zero, and a threshold derived from a statistic taken
        over every frame -- silent ones included -- moves with how much silence happens to be in the
        file. Two captures of the same mission are only comparable if this holds.
        """
        x = spectral_jump()
        # A whole number of hops, so the flux frame grid lands on the same samples either way: no framed
        # analysis can be invariant to a shift that splits its own hop, and that is not what is at issue.
        lead = 938 * ae.FLUX_HOP
        alone = ae.splices(x, RATE)
        padded = ae.splices(np.concatenate([np.zeros(lead), x]), RATE)
        self.assertEqual(len(padded), len(alone), (alone, padded))
        for (t0, kind0, _), (t1, kind1, _) in zip(alone, padded):
            self.assertEqual(kind0, kind1)
            self.assertAlmostEqual(t0 + lead / float(RATE), t1, places=6)


class TestSilences(unittest.TestCase):
    """A stream underrun is silence-then-resume, and that is what a reference-free measure can see."""

    def test_clean_bed_has_no_silence(self):
        self.assertEqual(ae.silences(bed(2.0), RATE), [])

    def test_a_hundred_millisecond_hole_is_one_silence_and_not_a_splice(self):
        x = bed(2.0)
        fade(x, RATE, 1.495, 0.005, rising=False)
        x[int(1.5 * RATE):int(1.6 * RATE)] = 0.0
        fade(x, RATE, 1.600, 0.005, rising=True)
        found = ae.silences(x, RATE)
        self.assertEqual(len(found), 1, found)
        t_start, duration = found[0]
        self.assertLess(abs(t_start - 1.5), 0.010, "silence starts at %.4f s" % t_start)
        self.assertLess(abs(duration - 0.1), 0.015, "silence lasts %.4f s" % duration)
        # The gap's own edges must not also be counted as splices: one underrun is one event, and the
        # splice detector holds off for SILENCE_GUARD_S either side of a gap it already reports.
        self.assertEqual(ae.splices(x, RATE), [])


class TestZeroSizeWav(unittest.TestCase):
    """The drive kills the game, so RIFF and data carry size 0; audio_corr already reads past that."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="audio_envelope_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_wav_with_zero_size_fields_reads_back(self):
        path = os.path.join(self.dir, "killed.wav")
        left = np.array([1000, -1000, 2000, -2000, 3000, -3000], dtype="<i2")
        right = np.array([500, -500, 1500, -1500, 2500, -2500], dtype="<i2")
        frames = np.empty(len(left) * 2, dtype="<i2")
        frames[0::2], frames[1::2] = left, right
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(frames.tobytes())
        with open(path, "r+b") as f:
            raw = bytearray(f.read())
            self.assertEqual(bytes(raw[0:4]), b"RIFF")
            raw[4:8] = struct.pack("<I", 0)        # the RIFF chunk size
            raw[40:44] = struct.pack("<I", 0)      # the data chunk size
            f.seek(0)
            f.write(raw)
        mono = ae.read_mono(path)
        np.testing.assert_allclose(mono, (left.astype(np.float64) + right.astype(np.float64)) / 2.0)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="audio_envelope_cli_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_one_line_per_segment_and_a_totals_line(self):
        path = os.path.join(self.dir, "bed.wav")
        mono = np.clip(bed(4.0), -32768, 32767).astype("<i2")
        frames = np.empty(len(mono) * 2, dtype="<i2")
        frames[0::2], frames[1::2] = mono, mono
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(frames.tobytes())
        out = io.StringIO()
        code = ae.main([path, "--segment", "2"], stream=out)
        self.assertEqual(code, 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 3, out.getvalue())
        self.assertTrue(lines[0].startswith("t=00:00-00:02"), lines[0])
        self.assertTrue(lines[1].startswith("t=00:02-00:04"), lines[1])
        self.assertTrue(lines[2].startswith("TOTAL"), lines[2])
        for line in lines[:2]:
            self.assertIn("osc=", line)
            self.assertIn("splices=0 (step=0 flux=0)", line)
            self.assertIn("silences=0", line)
            self.assertIn("rms_db=", line)
        # deterministic: the same file twice gives byte-identical output
        again = io.StringIO()
        ae.main([path, "--segment", "2"], stream=again)
        self.assertEqual(out.getvalue(), again.getvalue())


if __name__ == "__main__":
    unittest.main()
