"""Sprint 15 T2 (issue #67): the drag freeze's readout and the pure parts of its driver.

A title-bar drag puts the window's thread in the Win32 modal move loop (WM_ENTERSIZEMOVE to WM_EXITSIZEMOVE); before
#67's fix the guest clock stood still for the length of the drag. tools_py/parity/window_drag.py reads a game log's
`[pc-sampler]` rows (`t=` host seconds, `vsync=` the guest VBlank count) across the drag's window and says FROZEN,
SLOWED or ADVANCING. The window comes from the driver's `[window-drag] begin/end t=` stamps (its own file or the
log), else from the runtime's `[window] move loop entered/left` lines. Every log here is planted, not a real run.
"""
import contextlib
import io
import os
import tempfile
import unittest

from tools_py.parity import window_drag


def sampler(t, vsync, bp_wait_ms=0):
    return ("[pc-sampler] live pc=0x3b00a4 ra=0x3b00a4 sp=0x1f7fd90 t=%.2f vsync=%d ee=%.2f seq=1 dpc=0x1e70ec "
            "idle=1 bp_pending=1 bp_waiters=0 bp_wait_ms=%d net_wait=0/0 net_park=0/0 running=1 threads: "
            "[1 pc=0x33c06c ra=0x33c06c sp=0x1ffffd0 st=0 prio=5 wait=0/0]" % (t, vsync, t, bp_wait_ms))


def audio(t, late=0, dry=0, underruns=0):
    return ("[audio-trace] t=%.1fs rendered=%.2fs of wall (100%%) calls=10 frames/call=480 max_render=0.20ms "
            "pcm_underruns=%d cb_late=%d cb_dry=%d cb_jitter=0 cb_max_gap=10.0ms cb_silence=%.0fms"
            % (t, t, underruns, late, dry, 0.0))


def planted(rate_during, drag=(10.0, 20.0), end=30.0, step=0.25, rate=60.0, stamps=True, runtime_lines=False,
            audio_after=(0, 0, 0)):
    """A log with a sampler row every `step` s from t=0 to `end`; vsync at `rate`/s outside the drag and
    `rate_during`/s inside it; the driver's stamps and/or the runtime's move-loop lines at the drag's edges."""
    lines, v, t = [], 0.0, 0.0
    t0, t1 = drag
    lines.append(audio(0.0))
    while t <= end + 1e-9:
        if runtime_lines and abs(t - t0) < 1e-9:
            lines.append("[window] move loop entered (WM_ENTERSIZEMOVE): the GS back-pressure is released until it ends")
        lines.append(sampler(t, int(round(v))))
        if stamps and abs(t - t0) < 1e-9:
            lines.append("[window-drag] begin t=%.2f wall=1000.000 x=320 y=10" % t)
        if stamps and abs(t - t1) < 1e-9:
            lines.append("[window-drag] end t=%.2f wall=1010.000 moved_px=300" % t)
        if runtime_lines and abs(t - t1) < 1e-9:
            lines.append("[window] move loop left after 10000 ms (WM_EXITSIZEMOVE)")
        if abs(t - 5.0) < 1e-9:
            lines.append(audio(5.0))
        if abs(t - 25.0) < 1e-9:
            lines.append(audio(25.0, *audio_after))
        inside = t0 <= t < t1
        v += (rate_during if inside else rate) * step
        t += step
    return lines


class Readout(unittest.TestCase):
    def test_vsync_standing_still_across_the_drag_is_frozen(self):
        r = window_drag.readouts(planted(rate_during=0.0))
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0].verdict, "FROZEN")
        self.assertEqual(r[0].vsync_delta, 0)
        self.assertAlmostEqual(r[0].t0, 10.0)
        self.assertAlmostEqual(r[0].t1, 20.0)
        self.assertGreaterEqual(r[0].longest_still_s, 9.9)
        self.assertEqual(r[0].source, "driver")

    def test_vsync_moving_at_the_normal_rate_is_advancing(self):
        r = window_drag.readouts(planted(rate_during=60.0))
        self.assertEqual(r[0].verdict, "ADVANCING")
        self.assertEqual(r[0].vsync_delta, 600)
        self.assertAlmostEqual(r[0].rate_hz, 60.0, places=1)
        self.assertAlmostEqual(r[0].baseline_hz, 60.0, places=1)
        self.assertLess(r[0].longest_still_s, 0.5)

    def test_a_crawl_is_slowed_not_advancing(self):
        # The pre-#67 shape where the back-pressure's 2 s cap fires and the guest crawls: moving, but far under rate.
        r = window_drag.readouts(planted(rate_during=30.0))
        self.assertEqual(r[0].verdict, "SLOWED")

    def test_a_long_still_stretch_inside_an_otherwise_moving_window_is_not_advancing(self):
        lines = planted(rate_during=60.0)
        # Freeze vsync for 3 s (t=11..14) inside the drag, then let it catch up by the end: the rate is fine, the
        # stretch is not.
        out = []
        for line in lines:
            m = window_drag.SAMPLER_RE.search(line)
            if m and 11.0 <= float(m.group(1)) <= 14.0:
                line = sampler(float(m.group(1)), 660)
            out.append(line)
        r = window_drag.readouts(out)
        self.assertNotEqual(r[0].verdict, "ADVANCING")
        self.assertGreaterEqual(r[0].longest_still_s, 3.0)

    def test_the_runtime_move_loop_lines_give_the_window_without_the_driver(self):
        r = window_drag.readouts(planted(rate_during=60.0, stamps=False, runtime_lines=True))
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0].source, "runtime")
        self.assertEqual(r[0].verdict, "ADVANCING")
        self.assertAlmostEqual(r[0].t0, 10.0, delta=0.26)
        self.assertAlmostEqual(r[0].t1, 20.0, delta=0.26)

    def test_the_driver_stamps_win_over_the_runtime_lines(self):
        r = window_drag.readouts(planted(rate_during=60.0, stamps=True, runtime_lines=True))
        self.assertEqual([x.source for x in r], ["driver"])

    def test_stamps_from_a_separate_file(self):
        lines = planted(rate_during=0.0, stamps=False)
        stamps = ["[window-drag] begin t=10.00 wall=1000.000 x=320 y=10",
                  "[window-drag] end t=20.00 wall=1010.000 moved_px=300"]
        r = window_drag.readouts(lines, stamp_lines=stamps)
        self.assertEqual(r[0].verdict, "FROZEN")
        self.assertEqual(r[0].source, "driver")

    def test_no_window_or_too_few_rows_is_no_data(self):
        self.assertEqual(window_drag.readouts(planted(rate_during=60.0, stamps=False)), [])
        lines = [sampler(10.0, 600), "[window-drag] begin t=10.00 wall=1 x=1 y=1",
                 "[window-drag] end t=10.00 wall=2 moved_px=0"]
        self.assertEqual(window_drag.readouts(lines)[0].verdict, "NO-DATA")

    def test_audio_counters_across_the_drag(self):
        r = window_drag.readouts(planted(rate_during=60.0))
        self.assertEqual(r[0].audio_delta, {"cb_late": 0, "cb_dry": 0, "pcm_underruns": 0})
        r = window_drag.readouts(planted(rate_during=60.0, audio_after=(2, 1, 3)))
        self.assertEqual(r[0].audio_delta, {"cb_late": 2, "cb_dry": 1, "pcm_underruns": 3})
        self.assertIn("cb_dry +1", window_drag.format_readout(r[0]))

    def test_format_names_the_verdict_the_window_and_the_rates(self):
        text = window_drag.format_readout(window_drag.readouts(planted(rate_during=0.0))[0])
        self.assertTrue(text.startswith("DRAG t=10.00-20.00 s"), text)
        self.assertIn("FROZEN", text)
        self.assertIn("vsync +0", text)


class Cli(unittest.TestCase):
    def _run(self, lines, *extra):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "game.log")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = window_drag.main(["readout", path] + list(extra))
            return code, out.getvalue()

    def test_exit_codes(self):
        self.assertEqual(self._run(planted(rate_during=60.0))[0], 0)
        code, text = self._run(planted(rate_during=0.0))
        self.assertEqual(code, 1)
        self.assertIn("FROZEN", text)
        self.assertEqual(self._run(planted(rate_during=60.0, stamps=False))[0], 2)


class DriverPureParts(unittest.TestCase):
    def test_last_sampler_t_reads_the_tail(self):
        text = "\n".join([sampler(1.0, 60), "[gs-gl] noise", sampler(1.25, 75), "[audio-trace] t=1.0s"])
        self.assertAlmostEqual(window_drag.last_sampler_t(text), 1.25)
        self.assertIsNone(window_drag.last_sampler_t("no rows here"))

    def test_the_drag_path_goes_out_and_comes_back(self):
        path = window_drag.drag_path(100, 50, dx=300, seconds=10.0, step_s=0.05)
        self.assertEqual(path[0], (100, 50))
        self.assertEqual(path[-1], (100, 50))
        self.assertEqual(max(x for x, _ in path), 400)
        self.assertTrue(all(y == 50 for _, y in path))
        self.assertEqual(len(path), 201)

    def test_the_caption_point_sits_above_the_client_area(self):
        # Window rect (left, top, right, bottom) and the client area's top edge in screen coordinates.
        x, y = window_drag.caption_point((100, 200, 780, 700), client_top=231)
        self.assertEqual(y, 215)
        self.assertEqual(x, 100 + (780 - 100) // 3)


if __name__ == "__main__":
    unittest.main()
