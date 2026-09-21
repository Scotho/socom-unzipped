"""research/36 item 9: the dip detector, the endpoint/dump alignment and the DEVICE / STARVATION / COMMAND /
UNEXPLAINED labelling of tools_py/parity/audio_dips.py.

Synthetic signals throughout: a -20 dBFS tone with holes and dips cut into it, and a log written by hand in the
formats the mixer prints. The one test on a real capture (run 10, logs/parity/s10_r4k_music_ours) is skipped
when the capture is not on disk: the owner's phone recordings of that run place the dips they heard at the
seven times pinned there.
"""
import os
import struct
import tempfile
import unittest
import wave

import numpy as np

from tools_py.parity import audio_dips as ad

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tone(seconds, rate, amp=0.1, hz=440.0):
    t = np.arange(int(seconds * rate)) / rate
    return amp * np.sin(2 * np.pi * hz * t)


def cut(x, rate, at_s, dur_s, gain=0.0):
    a = int(at_s * rate)
    b = int((at_s + dur_s) * rate)
    x[a:b] *= gain
    return x


def write_wav(path, mono, rate):
    data = (np.clip(mono, -1, 1) * 32767).astype(np.int16)
    stereo = np.repeat(data[:, None], 2, axis=1).tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(stereo)


class DipDetector(unittest.TestCase):
    def test_a_hole_and_a_shallow_dip_are_found_with_their_lengths(self):
        rate = 48000
        x = tone(20.0, rate)
        cut(x, rate, 5.0, 0.15, 0.0)         # a 150 ms hole
        cut(x, rate, 9.0, 0.05, 10 ** (-12 / 20.0))   # a 50 ms dip of -12 dB
        dips = ad.find_dips(x, rate)
        self.assertEqual(len(dips), 2, [(d.start_s, d.dur_s) for d in dips])
        self.assertAlmostEqual(dips[0].start_s, 5.0, delta=0.06)
        self.assertAlmostEqual(dips[0].dur_s, 0.15, delta=0.06)
        self.assertGreater(dips[0].depth_db, 30.0)
        self.assertAlmostEqual(dips[1].start_s, 9.0, delta=0.06)
        self.assertAlmostEqual(dips[1].dur_s, 0.05, delta=0.06)
        self.assertAlmostEqual(dips[1].depth_db, 12.0, delta=1.5)

    def test_a_dip_under_the_threshold_and_silence_are_not_dips(self):
        rate = 48000
        x = tone(10.0, rate)
        cut(x, rate, 4.0, 0.2, 10 ** (-6 / 20.0))   # -6 dB: not a dip at the 10 dB threshold
        self.assertEqual(ad.find_dips(x, rate), [])
        self.assertEqual(ad.find_dips(np.zeros(rate * 5), rate), [])   # silence dipping is nothing

    def test_t0_offsets_the_times(self):
        rate = 48000
        x = tone(6.0, rate)
        cut(x, rate, 3.0, 0.1, 0.0)
        dips = ad.find_dips(x, rate, t0_s=100.0)
        self.assertAlmostEqual(dips[0].start_s, 103.0, delta=0.06)


class DumpReading(unittest.TestCase):
    def test_a_dump_killed_before_its_header_was_patched_is_read_by_length(self):
        rate = 48000
        x = tone(2.0, rate)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mix_dump.wav")
            write_wav(path, x, rate)
            with open(path, "r+b") as f:        # the mixer's unpatched header: RIFF size 36, data size 0
                f.seek(4)
                f.write(struct.pack("<I", 36))
                f.seek(40)
                f.write(struct.pack("<I", 0))
            mono, r = ad.read_mono(path)
        self.assertEqual(r, rate)
        self.assertEqual(len(mono), len(x))
        self.assertGreater(float(np.max(np.abs(mono))), 0.09)


class Alignment(unittest.TestCase):
    def test_the_offset_between_the_endpoint_and_the_dump_is_recovered(self):
        rate_dump, rate_ep = 48000, 44100
        dump = tone(12.0, rate_dump)
        for at in (2.0, 5.5, 8.25):
            cut(dump, rate_dump, at, 0.2, 0.0)
        # The endpoint hears the same thing 1.23 s later (at its own rate), with a little noise.
        ep = np.concatenate([np.zeros(int(1.23 * rate_ep)), np.interp(np.arange(int(12.0 * rate_ep)) / rate_ep, np.arange(len(dump)) / rate_dump, dump)])
        ep += 0.001 * np.random.default_rng(1).standard_normal(len(ep))
        offset, corr = ad.align(ep, rate_ep, dump, rate_dump, max_lag_s=5.0)
        self.assertAlmostEqual(offset, 1.23, delta=0.02)
        self.assertGreater(corr, 0.8)

    def test_local_offsets_follow_a_recorder_that_lost_time(self):
        # The dump: 40 s with a hole every 4 s. The endpoint: the same, 1.0 s late, but between 18 and 19 s of dump
        # time the recorder captured nothing (a starved device delivers no packets), so every later event lands a
        # second earlier: the offset is 1.0 s before the loss and 0.0 s after it.
        rate = 48000
        dump = tone(40.0, rate)
        for k in range(1, 10):
            cut(dump, rate, 4.0 * k, 0.2, 0.0)
        ep = np.concatenate([np.zeros(int(1.0 * rate)), dump[: int(18.0 * rate)], dump[int(19.0 * rate):]])
        dips = [ad.Dip(4.0 * k + (1.0 if k < 5 else 0.0), 0.2, -20.0, -60.0) for k in (2, 3, 6, 8)]
        offs = ad.local_offsets(ep, rate, dump, rate, dips, 1.0, span_s=6.0, search_s=2.0)
        self.assertAlmostEqual(offs[0], 1.0, delta=0.03)
        self.assertAlmostEqual(offs[1], 1.0, delta=0.03)
        self.assertAlmostEqual(offs[2], 0.0, delta=0.03)
        self.assertAlmostEqual(offs[3], 0.0, delta=0.03)


LOG = """\
[ps2xIOP] 989snd: snd_PlayVAGStreamByLoc (fno 0x0000002c) [0x001159a2, 0x00000000, 0x04000000, 0xffff0000, 0x00000001, 0x00000000, 0x00000000, 0x00000000] -> 0x040002a0
[audio] 989snd stream 040002a0 start frame=96000 detail=0
[audio] 989snd stream 040002a0 occupancy frame=100800 ahead=21000 chunks=3
[audio] 989snd stream 040002a0 occupancy frame=1195200 ahead=600 chunks=0 ended
[audio] 989snd stream 040002a0 UNDERRUN frame=240000 silent=2400
[audio] 989snd pcm occupancy frame=480000 ahead=12 blocks=24 pos=0 written=24576 underruns=0
[mpeg] frame=470000 tick=5870 park until=5890 (+20 ticks) decoded=2
[cd-stream] frame=440000 tick=5500 park need/buffered/wake 16 3 5503 lbn=0xcdade
[audio] 989snd pcm UNDERRUN frame=485000 silent=7200
[audio] 989snd cmd 0x22 frame=720000 [0x040002a0, 0x0, 0x1e0, 0x2]
[audio] 989snd cmd 0x9 frame=960000 [0x1, 0x2f5]
[audio] 989snd stream 040002a0 done frame=1200000 detail=0
"""


class Classification(unittest.TestCase):
    def setUp(self):
        self.ev = ad.read_events(LOG)

    def test_the_log_is_read(self):
        ev = self.ev
        self.assertEqual(ev.stream_start["040002a0"], 96000)
        self.assertEqual(ev.stream_done["040002a0"], 1200000)
        self.assertEqual(ev.stream_group["040002a0"], 1)
        self.assertEqual(ev.stream_underrun, [("040002a0", 240000, 2400)])
        self.assertEqual(ev.stream_occupancy, [("040002a0", 100800, 21000, False), ("040002a0", 1195200, 600, True)])

    def test_a_stream_running_out_at_its_end_is_not_starvation(self):
        # 24.9 s = frame 1195200: the producer has read the last chunk ("ended"), 600 frames left, then done at 25 s.
        rows = ad.classify([ad.Dip(24.9, 0.2, -20.0, -40.0)], None, 0.0, self.ev)
        self.assertEqual(rows[0].label, "COMMAND")
        self.assertIn("done", rows[0].reason)

    def test_the_pcm_and_command_lines_are_read(self):
        ev = self.ev
        self.assertEqual(ev.pcm_underrun, [(485000, 7200)])
        self.assertEqual(ev.pcm_occupancy, [(480000, 12, 24576)])
        self.assertEqual([(f, fr) for f, fr, _ in ev.commands], [(0x22, 720000), (0x9, 960000)])
        self.assertEqual(ev.feeder_parks, [("mpeg", 470000, 20), ("cd-stream", 440000, 3)])

    def test_a_pcm_starvation_names_the_feeder_park_before_it(self):
        # The stale run at frame 485000: the mpeg park at 470000 (0.3 s earlier) is the nearest feeder park before it.
        rows = ad.classify([ad.Dip(10.1, 0.15, -20.0, -40.0)], None, 0.0, self.ev)
        self.assertEqual(rows[0].label, "STARVATION")
        self.assertIn("the feeder parked on mpeg at frame 470000 for 20 ticks", rows[0].reason)

    def test_labels(self):
        dip = lambda t, dur=0.1: ad.Dip(t, dur, -20.0, -40.0)
        offset = 1.5
        # in the dump at 5.0 s = frame 240000: the stream's UNDERRUN -> STARVATION on the vag route
        # in the dump at 10.1 s = frame 484800: the pcm ring's stale run -> STARVATION, pcm + vag live
        # in the dump at 15.0 s = frame 720000: the AutoVol on the live handle -> COMMAND
        # in the dump at 20.0 s = frame 960000: master volume -> COMMAND
        # in the dump at 12.0 s: nothing near -> UNEXPLAINED
        # in the endpoint only, at 30.0 + offset -> DEVICE
        dump_dips = [dip(5.0), dip(10.1, 0.15), dip(15.0), dip(20.0), dip(12.0)]
        ep_dips = [dip(t + offset) for t in (5.0, 10.1, 15.0, 20.0, 12.0)] + [dip(30.0 + offset)]
        rows = ad.classify(ep_dips, dump_dips, offset, self.ev)
        by_t = {round(r.start_s - offset, 1): r for r in rows}
        self.assertEqual(by_t[5.0].label, "STARVATION")
        self.assertIn("UNDERRUN", by_t[5.0].reason)
        self.assertEqual(by_t[10.1].label, "STARVATION")
        self.assertIn("pcm ring stale run", by_t[10.1].reason)
        self.assertEqual(by_t[10.1].route, "pcm+vag g1")
        self.assertEqual(by_t[15.0].label, "COMMAND")
        self.assertIn("AutoVol", by_t[15.0].reason)
        self.assertEqual(by_t[20.0].label, "COMMAND")
        self.assertIn("SetMasterVolume", by_t[20.0].reason)
        self.assertEqual(by_t[12.0].label, "UNEXPLAINED")
        self.assertEqual(by_t[30.0].label, "DEVICE")
        self.assertEqual(by_t[30.0].route, "none")   # the stream ended at frame 1200000 = 25 s
        text = ad.report(rows, offset, 0.9)
        self.assertIn("alignment: endpoint = dump + 1.500 s", text)
        self.assertIn("DEVICE", text)
        self.assertIn("summary", text)

    def test_a_dump_dip_the_endpoint_missed_is_listed_as_dump_only(self):
        rows = ad.classify([], [ad.Dip(5.0, 0.1, -20.0, -40.0)], 0.0, self.ev)
        self.assertEqual(rows[0].label, "STARVATION (dump only)")

    def test_without_a_dump_the_endpoint_dips_are_read_against_the_log(self):
        rows = ad.classify([ad.Dip(6.5, 0.1, -20.0, -40.0)], None, 1.5, self.ev)   # 6.5 - 1.5 = 5.0 s: the UNDERRUN
        self.assertEqual(rows[0].label, "STARVATION")


class Run10GroundTruth(unittest.TestCase):
    """The owner's phone recordings of run 10, placed on its loopback by envelope correlation: the dips they heard."""
    CAPTURE = os.path.join(ROOT, "logs", "parity", "s10_r4k_music_ours", "endpoint.wav")
    HEARD = [(173.9, 0.15), (176.0, 0.05), (148.1, 4.0), (249.0, 11.5), (358.6, 18.0), (419.7, 0.10), (420.1, 0.45)]

    def test_the_seven_dips_the_owner_heard_are_detected(self):
        if not os.path.exists(self.CAPTURE):
            self.skipTest("run 10's capture is not on disk")
        mono, rate = ad.read_mono(self.CAPTURE)
        dips = ad.find_dips(mono[int(140 * rate): int(425 * rate)], rate, t0_s=140.0)
        starts = [d.start_s for d in dips]
        for t, dur in self.HEARD:
            near = [d for d in dips if abs(d.start_s - t) <= 0.3]
            self.assertTrue(near, "no dip within 0.3 s of %.1f s (found %s)" % (t, [round(s, 2) for s in starts if abs(s - t) < 3]))
            if dur >= 1.0:
                self.assertGreater(near[0].dur_s, 0.9 * dur - 0.5, "the %.1f s silence at %.1f s is shorter than heard: %.2f s" % (dur, t, near[0].dur_s))


if __name__ == "__main__":
    unittest.main()
