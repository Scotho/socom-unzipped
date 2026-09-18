"""Sprint 7 Task 1e: the correlation the audio bar is read with (tools_py/parity/audio_corr.py)."""
import unittest
import numpy as np
from tools_py.parity import audio_corr


class Correlate(unittest.TestCase):
    def test_identical_signals_correlate_at_one(self):
        rate = 48000
        t = np.arange(rate * 8) / rate
        sig = (np.sin(2 * np.pi * 440 * t) * 20000).astype("int16")
        rows = audio_corr.correlate_arrays(sig, sig, window_s=4.0, rate=rate)
        self.assertEqual(len(rows), 2)
        self.assertGreater(audio_corr.min_corr(rows), 0.999)
        self.assertEqual([r[2] for r in rows], [0, 0])

    def test_noise_does_not_correlate(self):
        rate = 48000
        a = (np.random.RandomState(1).randn(rate * 8) * 5000).astype("int16")
        b = (np.random.RandomState(2).randn(rate * 8) * 5000).astype("int16")
        rows = audio_corr.correlate_arrays(a, b, window_s=4.0, rate=rate)
        self.assertLess(audio_corr.min_corr(rows), 0.2)

    def test_a_fixed_offset_is_reported_not_hidden(self):
        # Not a tone: 480 samples is exactly three periods of a 300 Hz sine, so the shifted signal is
        # bit-for-bit the unshifted one and no method can report the 480. Music is not that periodic.
        rate = 48000
        sig = (np.random.RandomState(3).randn(rate * 8) * 5000).astype("int16")
        rows = audio_corr.correlate_arrays(sig[480:], sig, window_s=4.0, rate=rate)
        self.assertGreater(audio_corr.min_corr(rows), 0.99)
        self.assertEqual(rows[0][2], 480)



    def test_a_wav_whose_header_says_zero_is_read_by_file_length(self):
        # The runtime patches the WAV's size fields on a clean close; a game the drive kills leaves them 0, and a
        # header-honouring reader then sees no samples at all (s7_gl_gate2: 480 s of audio, "windows=0").
        import os, struct, tempfile
        from tools_py.parity import audio_corr
        n = 48000 * 2 * 2   # one second, stereo, s16
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "killed.wav")
            with open(p, "wb") as f:
                f.write(b"RIFF" + struct.pack("<I", 0) + b"WAVE" + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 2, 48000, 192000, 4, 16)
                        + b"data" + struct.pack("<I", 0) + bytes(n))
            left, right = audio_corr.read_wav(p)
        self.assertEqual(len(left), 48000)
        self.assertEqual(len(right), 48000)


    def test_a_time_range_scores_only_that_span_with_absolute_times(self):
        import os, tempfile, wave
        import numpy as np
        from tools_py.parity import audio_corr
        rng = np.random.default_rng(3)
        ref = (rng.uniform(-8000, 8000, size=48000 * 8)).astype(np.int16)         # 8 s of reference
        noise = (rng.uniform(-8000, 8000, size=48000 * 8)).astype(np.int16)       # 8 s of something else
        mix = np.concatenate([noise, ref])                                         # the reference plays from 8 s
        with tempfile.TemporaryDirectory() as tmp:
            wav = os.path.join(tmp, "mix.wav"); pcm = os.path.join(tmp, "ref.bin")
            with wave.open(wav, "wb") as w:
                w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
                w.writeframes(np.repeat(mix, 2).tobytes())
            blocks = ref.reshape(-1, 256)
            with open(pcm, "wb") as f:
                f.write(bytes(40))
                for b in blocks:
                    f.write(b.tobytes()); f.write(b.tobytes())                     # L block, R block
            rows = audio_corr.correlate(wav, pcm, from_s=8.0, to_s=16.0)
        self.assertTrue(rows and all(t >= 8.0 for t, _, _ in rows), "rows carry absolute times")
        scored = [c for _, c, _ in rows if c == c]
        self.assertTrue(scored and min(scored) > 0.99, f"the reference span correlates: {scored}")


if __name__ == "__main__":
    unittest.main()
