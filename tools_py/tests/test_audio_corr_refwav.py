"""Sprint 8 Goal 3 Task 4: --ref-wav, a plain 16-bit WAV reference instead of the disc's PCM concatenation.

The voice reference is generated at 11025 Hz (scripts/parity/refs/make_voice_ref.py) but the game opens
the headset at 8000 (decomp :211849), so the reference has to be moved to the dump's rate before either
is scored. A resample that was silently wrong would show up as a low correlation and be read as "the
voice path is broken", so it is checked here against a signal whose answer is known.
"""
import math
import os
import struct
import tempfile
import unittest
import wave

import numpy as np

from tools_py.parity import audio_corr


def write_wav(path, samples, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))


def tone(seconds, rate, hz=300.0, amp=0.6):
    n = int(seconds * rate)
    return [int(round(amp * 32767.0 * math.sin(2.0 * math.pi * hz * i / rate))) for i in range(n)]


class ResampleTest(unittest.TestCase):
    def test_a_rate_change_changes_the_length_and_keeps_the_shape(self):
        at11025 = np.array(tone(1.0, 11025), dtype=np.float64)
        at8000 = audio_corr.resample_linear(at11025, 11025, 8000)
        self.assertEqual(len(at8000), 8000)
        # A 300 Hz tone stays a 300 Hz tone: the dominant FFT bin is at 300 in both.
        for arr, rate in ((at11025, 11025), (at8000, 8000)):
            spectrum = np.abs(np.fft.rfft(arr))
            peak = int(np.argmax(spectrum)) * rate / float(len(arr))
            self.assertAlmostEqual(peak, 300.0, delta=2.0)

    def test_the_same_rate_is_a_no_op(self):
        arr = np.arange(10, dtype=np.float64)
        self.assertTrue(np.array_equal(audio_corr.resample_linear(arr, 8000, 8000), arr))

    def test_an_empty_input_is_not_an_error(self):
        self.assertEqual(len(audio_corr.resample_linear(np.array([]), 11025, 8000)), 0)


class RefWavCorrelateTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ref = os.path.join(self.dir, "voice_ref.wav")
        self.mix = os.path.join(self.dir, "A_gameread.wav")
        write_wav(self.ref, tone(4.0, 11025), 11025)

    def test_the_same_signal_at_the_open_rate_correlates(self):
        # What the module serves: the reference, resampled 11025 -> 8000, which is what the game reads.
        served = audio_corr.resample_linear(np.array(tone(4.0, 11025), dtype=np.float64), 11025, 8000)
        write_wav(self.mix, [int(round(v)) for v in served], 8000)
        rows = audio_corr.correlate(self.mix, None, ref_wav=self.ref, rate=8000, window_s=1.0)
        self.assertTrue(rows, "at least one window is scored")
        self.assertGreaterEqual(audio_corr.min_corr(rows), 0.95)

    def test_an_unrelated_signal_does_not(self):
        write_wav(self.mix, tone(4.0, 8000, hz=1900.0), 8000)
        rows = audio_corr.correlate(self.mix, None, ref_wav=self.ref, rate=8000, window_s=1.0)
        self.assertLess(audio_corr.min_corr(rows), 0.5)


if __name__ == "__main__":
    unittest.main()
