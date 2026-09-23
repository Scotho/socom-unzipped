"""tools_py/parity/cb_trace.py: the host audio callback trace read back -- holes, and DEVICE dips laid against them.

Synthetic rows only: a trace of 20 ms callbacks with one 75 ms gap, and an audio_dips report whose one DEVICE dip
falls on that gap and whose other does not. What is NOT covered here, because only a capture can cover it: whether
the mission music's real dips land on late callbacks. That is the capture the Sprint 11 audio-out task takes.
"""
import unittest

from tools_py.parity import cb_trace

HEADER = "# audio callback trace: t0_epoch_us=1700000000000000 period_us=20000 jitter_us=30000 hole_us=60000 capacity=8\n"
COLUMNS = "seq,entry_us,exit_us,frames,out_frame,gap_us,render_us\n"
ROWS = (
    "0,0,500,960,960,0,500\n"
    "1,20000,20600,960,1920,20000,600\n"
    "2,40000,40400,960,2880,20000,400\n"
    "3,115000,115700,960,3840,75000,700\n"      # the fourth callback came 75 ms after the third: a hole
    "4,135000,135300,960,4800,20000,300\n"
    "garbage line that a cut-short flush could leave\n"
)
DIPS = (
    "  t(s)    dur(s)  depth  route          verdict\n"
    "    2.115    0.05    12.0  vag g1+vag g2  DEVICE                 in the endpoint, not in the dump at 0.13 s (offset 1.98 s)\n"
    "    3.000    0.05    11.0  vag g1+vag g2  DEVICE                 in the endpoint, not in the dump at 1.02 s (offset 1.98 s)\n"
    "    2.500    0.30    20.0  vag g2         STARVATION             pcm UNDERRUN frame=..\n"
)


class CbTraceTest(unittest.TestCase):
    def test_the_header_and_the_rows_parse_and_a_broken_row_is_skipped(self):
        header, rows = cb_trace.parse(HEADER + COLUMNS + ROWS)
        self.assertEqual(header["t0_epoch_us"], 1700000000000000)
        self.assertEqual(header["period_us"], 20000)
        self.assertEqual(header["hole_us"], 60000)
        self.assertEqual([r.seq for r in rows], [0, 1, 2, 3, 4])
        self.assertEqual(rows[3].gap_us, 75000)
        self.assertEqual(rows[3].render_us, 700)

    def test_a_gap_past_the_buffer_is_a_hole_with_its_silence(self):
        header, rows = cb_trace.parse(HEADER + COLUMNS + ROWS)
        found = cb_trace.holes(rows, header["hole_us"], header["period_us"])
        self.assertEqual([(h.seq, h.gap_us, h.silence_us, h.out_frame) for h in found], [(3, 75000, 55000, 3840)])

    def test_a_device_dip_on_the_hole_is_the_late_callback_and_one_off_it_is_not(self):
        header, rows = cb_trace.parse(HEADER + COLUMNS + ROWS)
        found = cb_trace.holes(rows, header["hole_us"], header["period_us"])
        dips = cb_trace.parse_dips(DIPS)
        self.assertEqual([d.start_s for d in dips], [2.115, 3.0], "DEVICE rows only")
        # The recorder started 2.0 s before the trace's t0: endpoint 2.115 s is trace wall 0.115 s, the hole's entry.
        att = cb_trace.attribute(dips, found, header["t0_epoch_us"], recorder_start_epoch_s=1700000000000000 / 1e6 - 2.0)
        self.assertIsNotNone(att[0].hole)
        self.assertEqual(att[0].hole.seq, 3)
        self.assertAlmostEqual(att[0].delta_s, 0.0, places=3)
        self.assertIsNone(att[1].hole, "the 3.0 s dip is 885 ms from the only hole: not a late callback")
        text = cb_trace.report(header, rows, found, att)
        self.assertIn("holes 1", text)
        self.assertIn("DEVICE dips 2: 1 on a late callback, 1 on none", text)
        self.assertIn("LATE CALLBACK seq=3", text)
        self.assertIn("NO LATE CALLBACK", text)

    def test_a_dip_is_laid_against_the_callback_that_rendered_its_dump_time_without_any_recorder_clock(self):
        header, rows = cb_trace.parse(HEADER + COLUMNS + ROWS)
        found = cb_trace.holes(rows, header["hole_us"], header["period_us"])
        dips = cb_trace.parse_dips(DIPS)
        self.assertEqual([d.dump_s for d in dips], [0.13, 1.02], "the scorer's dump-aligned time on each DEVICE row")
        # Dump time 0.13 s is output frame 6240, rendered by the callback whose out_frame passes it: seq 4 (4800 -> ...)?
        # No: seq 3 leaves the clock at 3840 and seq 4 at 4800, so frame 6240 is past every row; a dip past the trace
        # is unattributable. Frame 0.07 s = 3360 falls in seq 3's render, the late one.
        dips[0].dump_s = 0.07
        att = cb_trace.attribute_by_dump(dips, rows, found)
        self.assertIsNotNone(att[0].hole)
        self.assertEqual(att[0].hole.seq, 3, "the callback that rendered the dip's dump time was the late one")
        self.assertIsNone(att[1].hole, "a dump time past the trace's last callback attributes to nothing")
        self.assertIsNone(cb_trace.callback_at_out_frame(rows, 10000))
        self.assertEqual(cb_trace.callback_at_out_frame(rows, 0).seq, 0)
        self.assertEqual(cb_trace.callback_at_out_frame(rows, 959).seq, 0)
        self.assertEqual(cb_trace.callback_at_out_frame(rows, 960).seq, 1)

    def test_the_report_stands_without_dips(self):
        header, rows = cb_trace.parse(HEADER + COLUMNS + ROWS)
        found = cb_trace.holes(rows, header["hole_us"], header["period_us"])
        text = cb_trace.report(header, rows, found, None)
        self.assertIn("callbacks 5 over 0.1 s, period 20 ms, hole threshold 60 ms; max gap 75.0 ms, max render 0.70 ms", text)
        self.assertIn("hole seq=3", text)
        self.assertNotIn("DEVICE dips", text)


if __name__ == "__main__":
    unittest.main()
