"""tools_py/parity/cb_trace.py: the host audio callback trace read back -- late and dry callbacks, and DEVICE dips
laid against them honestly (fix round 1 of the audio-out review: C2, I1, I2, I3, I7, M2, M3).

Synthetic rows only: 20 ms callbacks with one 75 ms gap (late: the buffer was one period from dry) and one 100 ms
gap (dry: 20 ms of silence reached the endpoint), and an audio_dips report whose DEVICE dips fall on the late
callback, off it, before the trace, past it, or without a dump time. What is NOT covered here, because only a
capture can cover it: whether the mission music's real dips land on late callbacks.
"""
import os
import re
import unittest

from tools_py.parity import cb_trace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PS2_AUDIO = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xRuntime", "src", "lib", "ps2_audio.cpp")

HEADER = "# audio callback trace: t0_epoch_us=1700000000000000 period_us=20000 jitter_us=30000 late_us=60000 dry_us=80000 capacity=8\n"
COLUMNS = "seq,entry_us,exit_us,frames,out_frame,gap_us,render_us\n"
ROWS = (
    "0,0,500,960,960,0,500\n"
    "1,20000,20600,960,1920,20000,600\n"
    "2,40000,40400,960,2880,20000,400\n"
    "3,115000,115700,960,3840,75000,700\n"      # 75 ms after the third: late (over 60 ms), not dry (under 80 ms)
    "4,135000,135300,960,4800,20000,300\n"
    "5,235000,235400,960,5760,100000,400\n"     # 100 ms after the fifth: dry, 20 ms of silence at the endpoint
    "6,255000,255300,960,6720,20000,300\n"
    "garbage line that a cut-short flush could leave\n"
    "7,275000\n"
)
STATUS = "# dropped=0 recorded=8\n"
DIPS = (
    "alignment: endpoint = dump + 1.980 s (envelope correlation 0.31)\n"
    "  t(s)    dur(s)  depth  route          verdict\n"
    "    2.050    0.05    12.0  vag g1+vag g2  DEVICE                 in the endpoint, not in the dump at 0.07 s (offset 1.98 s)\n"
    "    3.000    0.05    11.0  vag g1+vag g2  DEVICE                 in the endpoint, not in the dump at 1.02 s (offset 1.98 s)\n"
    "    0.500    0.05    10.0  none           DEVICE                 in the endpoint, not in the dump at -1.48 s (offset 1.98 s)\n"
    "   50.000    0.05    10.0  none           DEVICE                 in the endpoint, not in the dump at 48.02 s (offset 1.98 s)\n"
    "    2.500    0.30    20.0  vag g2         STARVATION             pcm UNDERRUN frame=..\n"
    "    2.010    0.05    10.0  vag g2         DEVICE                 in the endpoint, not in the dump at 0.03 s (offset 1.98 s)\n"
)


def parsed():
    header, rows, skipped = cb_trace.parse(HEADER + COLUMNS + ROWS + STATUS)
    return header, rows, skipped


class ParseTest(unittest.TestCase):
    def test_the_header_the_status_line_and_the_rows_parse_and_broken_rows_are_counted(self):
        header, rows, skipped = parsed()
        self.assertEqual(header["t0_epoch_us"], 1700000000000000)
        self.assertEqual((header["period_us"], header["late_us"], header["dry_us"], header["capacity"]), (20000, 60000, 80000, 8))
        self.assertEqual((header["dropped"], header["recorded"]), (0, 8), "the flusher's status line lands in the header")
        self.assertEqual([r.seq for r in rows], [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(skipped, 2, "two lines that are not rows: a garbage line and a cut-short row")


class HolesTest(unittest.TestCase):
    def test_late_is_past_the_early_warning_and_dry_is_past_the_whole_buffer_with_its_silence(self):
        header, rows, _ = parsed()
        late = cb_trace.late_callbacks(rows, header["late_us"], header["dry_us"], header["period_us"])
        self.assertEqual([(h.seq, h.gap_us, h.dry, h.silence_us) for h in late],
                         [(3, 75000, False, 0), (5, 100000, True, 20000)],
                         "a 75 ms gap is late but the 80 ms buffer still covered it: no silence; 100 ms is dry by 20 ms")

    def test_the_report_states_late_dry_and_silence_separately(self):
        header, rows, skipped = parsed()
        late = cb_trace.late_callbacks(rows, header["late_us"], header["dry_us"], header["period_us"])
        text = cb_trace.report(header, rows, skipped, late, None)
        self.assertIn("late 2 (1 dry), silence 20 ms in all", text)
        self.assertIn("max gap 100.0 ms, max render 0.70 ms", text)
        self.assertNotIn("DEVICE dips", text)

    def test_a_saturated_or_dropping_trace_is_said_loudly(self):
        header, rows, skipped = cb_trace.parse(HEADER + COLUMNS + ROWS + "# dropped=3 recorded=8\n")
        text = cb_trace.report(header, rows, skipped, [], None)
        self.assertIn("WARNING: the trace dropped 3 callbacks", text)
        header2 = dict(header, capacity=7, dropped=0)
        text2 = cb_trace.report(header2, rows, skipped, [], None)
        self.assertIn("WARNING: the trace is full", text2)


class DumpTimeAttributionTest(unittest.TestCase):
    def test_every_dip_is_late_cleared_or_unattributable_with_its_reason(self):
        header, rows, _ = parsed()
        late = cb_trace.late_callbacks(rows, header["late_us"], header["dry_us"], header["period_us"])
        dips, alignment = cb_trace.parse_dips(DIPS)
        self.assertEqual([d.dump_s for d in dips], [0.07, 1.02, -1.48, 48.02, 0.03])
        self.assertEqual([d.offset_s for d in dips], [1.98] * 5, "the per-dip offset the scorer printed")
        self.assertEqual(alignment, (1.98, 0.31))
        att = cb_trace.attribute_by_dump(dips, rows, late, period_us=header["period_us"])
        self.assertEqual([a.state for a in att], ["late", "unattributable", "unattributable", "unattributable", "cleared"])
        self.assertEqual(att[0].hole.seq, 3, "dump time 0.07 s = frame 3360, rendered by the late fourth callback")
        self.assertEqual(att[1].reason, "past the trace", "1.02 s = frame 48960 is past the last row's clock")
        self.assertEqual(att[2].reason, "before the trace", "a negative dump time is before the trace, never seq 0")
        self.assertEqual(att[3].reason, "past the trace")
        self.assertEqual(att[4].reason, "", "0.03 s = frame 1440: rendered by seq 1, 95 ms before the late fourth: cleared")
        text = cb_trace.report(header, rows, 0, late, att, alignment=alignment)
        self.assertIn("DEVICE dips 5: 1 late, 1 cleared, 3 unattributable (1 before the trace, 2 past it)", text)
        self.assertIn("LATE CALLBACK seq=3", text)
        self.assertIn("UNATTRIBUTABLE (past the trace)", text)
        self.assertIn("(offset 1.98 s)", text)

    def test_a_dip_without_a_dump_time_is_unattributable_for_that_reason(self):
        header, rows, _ = parsed()
        d = cb_trace.DeviceDip(2.05, 0.05, 12.0, "none", None, None)
        att = cb_trace.attribute_by_dump([d], rows, [], period_us=header["period_us"])
        self.assertEqual((att[0].state, att[0].reason), ("unattributable", "no dump time"))

    def test_the_dump_mode_tolerance_is_a_few_periods_not_a_quarter_second(self):
        header, rows, _ = parsed()
        late = cb_trace.late_callbacks(rows, header["late_us"], header["dry_us"], header["period_us"])
        # Dump time 0.05 s = frame 2400, rendered by seq 2 at entry 40 000 us: the late seq 3 is 75 ms away.
        d = cb_trace.DeviceDip(2.03, 0.05, 12.0, "none", 0.05, 1.98)
        att = cb_trace.attribute_by_dump([d], rows, late, period_us=header["period_us"])
        self.assertEqual(att[0].state, "cleared", "three periods (60 ms) either side: a late callback 75 ms away does not claim the dip")
        att = cb_trace.attribute_by_dump([d], rows, late, period_us=header["period_us"], tolerance_s=0.25)
        self.assertEqual(att[0].state, "late", "the old quarter-second tolerance would have")

    def test_a_low_envelope_correlation_marks_every_attribution_low_confidence(self):
        header, rows, _ = parsed()
        late = cb_trace.late_callbacks(rows, header["late_us"], header["dry_us"], header["period_us"])
        dips, alignment = cb_trace.parse_dips(DIPS)
        att = cb_trace.attribute_by_dump(dips, rows, late, period_us=header["period_us"])
        text = cb_trace.report(header, rows, 0, late, att, alignment=alignment)
        self.assertIn("LOW CONFIDENCE: envelope correlation 0.31 is under 0.50", text)
        text = cb_trace.report(header, rows, 0, late, att, alignment=(1.98, 0.9))
        self.assertNotIn("LOW CONFIDENCE", text)

    def test_callback_at_out_frame_refuses_frames_outside_the_trace(self):
        _, rows, _ = parsed()
        self.assertIsNone(cb_trace.callback_at_out_frame(rows, -1))
        self.assertEqual(cb_trace.callback_at_out_frame(rows, 0).seq, 0)
        self.assertEqual(cb_trace.callback_at_out_frame(rows, 959).seq, 0)
        self.assertEqual(cb_trace.callback_at_out_frame(rows, 960).seq, 1)
        self.assertEqual(cb_trace.callback_at_out_frame(rows, 6719).seq, 6)
        self.assertIsNone(cb_trace.callback_at_out_frame(rows, 6720), "the clock after the last row is past the trace")


class RuntimePublicationTest(unittest.TestCase):
    """Fix round 2, R1: the trace is handed to a LIVE audio thread. The call site is what decides whether a
    callback can see a half-built trace, so it is pinned here: the trace must be created and published BEFORE
    ma_device_start opens the callback, and the audio thread must read it through the slot's acquire load, never
    off a unique_ptr another thread is storing into. (The slot's own semantics are pinned in C++, in
    ps2xTest/src/audio_cb_trace_tests.cpp.)"""

    def source(self):
        with open(PS2_AUDIO, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def test_the_trace_is_published_before_the_device_starts(self):
        text = self.source()
        opened = text.find("cbTrace.open(")
        started = text.find("ma_device_start(")
        self.assertGreater(opened, 0, "the callback trace is opened through the slot")
        self.assertGreater(started, 0)
        self.assertLess(opened, started,
                        "the trace must exist before the audio thread does: published after ma_device_start, the "
                        "first callbacks are lost and the publication itself is a data race (R1)")

    def test_the_audio_thread_reads_the_trace_through_the_slots_acquire_load(self):
        text = self.source()
        self.assertEqual(text.count("m_impl->cbTrace->"), 0,
                         "the audio thread must not dereference the owner's unique_ptr while it is being stored into")
        self.assertTrue(re.search(r"m_impl->cbTrace\.live\(\)", text) is not None,
                        "the callback takes the trace from the slot (an acquire load of an atomic pointer)")


class RecorderClockAttributionTest(unittest.TestCase):
    def test_the_first_packet_stamp_less_one_read_places_the_files_first_frame(self):
        header, rows, _ = parsed()
        late = cb_trace.late_callbacks(rows, header["late_us"], header["dry_us"], header["period_us"])
        # The recorder's first read returned its 1024 frames one read after t0: the file's frame 0 sits at t0 itself,
        # so endpoint time 0.115 s is trace time 0.115 s -- the late fourth callback's entry.
        first_packet = 1700000000000000 / 1e6 + 1024 / 48000
        dip = cb_trace.DeviceDip(0.115, 0.05, 12.0, "none", None, None)
        att = cb_trace.attribute_by_recorder([dip], rows, late, header["t0_epoch_us"], first_packet,
                                             period_us=header["period_us"], rate=48000)
        self.assertEqual(att[0].state, "late")
        self.assertEqual(att[0].hole.seq, 3)
        self.assertAlmostEqual(att[0].delta_s, 0.0, places=3)

    def test_a_dip_outside_the_traces_span_is_unattributable_in_the_recorder_mode_too(self):
        """Fix round 2, R3: C2's guard was in the dump mode only, so a dip past the last callback read as
        `cleared` -- 201 of the sixteen-minute capture's 562 were exactly that (the recorder outlived the game)."""
        header, rows, _ = parsed()
        late = cb_trace.late_callbacks(rows, header["late_us"], header["dry_us"], header["period_us"])
        first_packet = 1700000000000000 / 1e6 + 1024 / 48000
        dips = [cb_trace.DeviceDip(0.115, 0.05, 12.0, "none"),     # on the late fourth callback
                cb_trace.DeviceDip(0.280, 0.05, 10.0, "none"),     # 5 ms past the last callback's period: no data
                cb_trace.DeviceDip(50.0, 0.05, 10.0, "none"),      # long past the trace: the game was already dead
                cb_trace.DeviceDip(-1.0, 0.05, 10.0, "none")]      # before the trace began
        att = cb_trace.attribute_by_recorder(dips, rows, late, header["t0_epoch_us"], first_packet,
                                             period_us=header["period_us"], rate=48000)
        self.assertEqual([a.state for a in att], ["late", "unattributable", "unattributable", "unattributable"])
        self.assertEqual([a.reason for a in att[1:]], ["past the trace", "past the trace", "before the trace"])
        text = cb_trace.report(header, rows, 0, late, att)
        self.assertIn("DEVICE dips 4: 1 late, 0 cleared, 3 unattributable (1 before the trace, 2 past it)", text)

    def test_a_dip_inside_the_last_callbacks_own_period_is_still_attributed(self):
        """The trace's span ends one period after the last callback's entry -- that callback rendered it."""
        header, rows, _ = parsed()
        late = cb_trace.late_callbacks(rows, header["late_us"], header["dry_us"], header["period_us"])
        first_packet = 1700000000000000 / 1e6 + 1024 / 48000
        dip = cb_trace.DeviceDip(0.270, 0.05, 10.0, "none")       # 255 ms entry + 15 ms: inside the last period
        att = cb_trace.attribute_by_recorder([dip], rows, late, header["t0_epoch_us"], first_packet,
                                             period_us=header["period_us"], rate=48000)
        self.assertEqual(att[0].state, "late", "the last callback's own period is still data: this dip lies on the dry sixth")
        self.assertEqual(att[0].hole.seq, 5)


if __name__ == "__main__":
    unittest.main()
