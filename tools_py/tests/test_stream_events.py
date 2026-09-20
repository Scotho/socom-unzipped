"""Sprint 9 Q0: the reader for the mixer's stream-event trace -- start / done / UNDERRUN on the output-frame clock."""
import os
import tempfile
import unittest

from tools_py.parity import stream_events as se


LOG = """\
[ps2xIOP] 989snd: snd_PlayVAGStreamByLoc (fno 0x0000002c) [0x0011e17d, 0x00000000, 0x04000000, 0xffff0000, 0x00000001, 0x00000000, 0x00000000, 0x00000000] -> 0x04000443
[audio] 989snd stream 04000443 start frame=1200000 detail=0
[audio] 989snd stream 04000443 sector 11e17d+0 playing
[ps2xIOP] 989snd: snd_SoundIsStillPlaying (fno 0x00000019) [0x04000443] -> 0x04000443
[audio] 989snd stream 04000443 UNDERRUN frame=1250000 silent=480
[audio] 989snd stream 04000443 UNDERRUN frame=1250480 silent=480
[audio] 989snd stream 04000443 done frame=1408000 detail=0
[ps2xIOP] 989snd: snd_SoundIsStillPlaying (fno 0x00000019) [0x04000443] -> 0x00000000
[ps2xIOP] 989snd: snd_PlayVAGStreamByLoc (fno 0x0000002c) [0x0011f0d0, 0x00000000, 0x04000000, 0xffff0000, 0x00000001, 0x00000000, 0x00000000, 0x00000000] -> 0x04000450
[audio] 989snd stream 04000450 start frame=1412800 detail=0
[ps2xIOP] 989snd: snd_PlayVAGStreamByLoc (fno 0x0000002c) [0x00102e81, 0x00000000, 0x00000000, 0xffff0000, 0x00000002, 0x00000000, 0x00000000, 0x00000000] -> 0x04010451
[audio] 989snd stream 04010451 start frame=1412800 detail=0
[audio] 989snd stream 04000450 done frame=1537600 detail=0
"""


class StreamEventsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "run.log")
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(LOG)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_stream_gets_its_group_sector_start_done_and_underruns(self):
        streams = se.read(self.path)
        self.assertEqual([s.handle for s in streams], [0x04000443, 0x04000450, 0x04010451])
        a = streams[0]
        self.assertEqual((a.group, a.sector), (1, 0x11e17d), "the play call's group and sector are attached")
        self.assertEqual((a.start, a.done), (1200000, 1408000))
        self.assertEqual(a.underruns, [(1250000, 480), (1250480, 480)])
        self.assertEqual(a.silent_frames, 960)
        self.assertIsNone(streams[2].done, "a stream still playing at the end of the log has no done frame")

    def test_the_real_log_prints_the_play_call_after_the_mixers_start_line_and_the_group_still_attaches(self):
        # The mixer's start line is printed from inside the RPC, before the IOP module logs the call and its
        # handle -- so in a real run the play line FOLLOWS the start line. The first driven run with the trace
        # attached no group to any of its 42 streams for exactly this reason.
        real = chr(10).join([
            "[audio] 989snd stream 0400000c start frame=1710239 detail=0",
            "[audio] 989snd stream 400000c sector 1319ce+0 playing",
            "[ps2xIOP] 989snd: snd_PlayVAGStreamByLoc (fno 0x0000002c) [0x001319ce, 0x00000000, 0x04000000, 0xffff0000, 0x00000001, 0x00000000, 0x00000000, 0x00000004] -> 0x0400000c",
            "[audio] 989snd stream 0400000c done frame=3164000 detail=0",
        ]) + chr(10)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(real)
        streams = se.read(self.path)
        self.assertEqual(len(streams), 1)
        self.assertEqual((streams[0].group, streams[0].sector), (1, 0x1319ce), "the group attaches even when its line comes second")
        self.assertEqual((streams[0].start, streams[0].done), (1710239, 3164000))

    def test_a_music_boundary_is_the_gap_from_one_stems_done_to_the_next_stems_start(self):
        gaps = se.music_gaps(se.read(self.path), group=1)
        self.assertEqual(len(gaps), 1, "one boundary between the two music stems; the group-2 stream is not a boundary")
        g = gaps[0]
        self.assertEqual((g.prev, g.next), (0x04000443, 0x04000450))
        self.assertEqual(g.frames, 4800)
        self.assertAlmostEqual(g.ms, 100.0, places=3)

    def test_a_stem_that_starved_reports_it_and_its_stretch(self):
        s = se.read(self.path)[0]
        self.assertEqual(s.played_frames, 1408000 - 1200000)
        # 4.3 s of 32 kHz VPK is 206400 output frames; this stem took 208000, and 960 of those were silence.
        self.assertEqual(s.silent_frames, 960)

    def test_the_report_names_the_worst_gap_and_the_underrun_total(self):
        text = se.report(se.read(self.path), group=1)
        self.assertIn("boundaries=1", text)
        self.assertIn("worst=100.0ms", text)
        self.assertIn("underrun_frames=960", text)
        self.assertIn("04000443->04000450", text)


if __name__ == "__main__":
    unittest.main()
