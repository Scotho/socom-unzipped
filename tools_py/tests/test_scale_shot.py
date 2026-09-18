"""Sprint 7 Task 1c: the pure parts of scale_shot -- nothing here launches the game.

The two things the scale comparison rests on and that a unit test can hold:

  * the child's environment -- PS2X_WINDOW_SIZE at the asked size, and PS2X_HOST_SCREENSHOT_LATEST
    pointing at this run's own export file (export mode) or absent entirely (window mode, where the
    readback must not stand in for PrintWindow);
  * the newest-frame selection -- the runtime writes <path>.tmp.png and renames it onto <path>, so
    the frame to copy is the newest *final* png and never the half-written .tmp.png.

The 2026-09-17 failure this guards: Step 8 compared two different screens, because the capture came
from the window (overlay and all) of a launch of its own rather than from the runtime's export.
"""
import os
import tempfile
import time
import unittest
from unittest import mock

from tools_py.parity import scale_shot


class ChildEnv(unittest.TestCase):
    def test_export_mode_sets_both_variables(self):
        base = {"PATH": "x"}
        env = scale_shot.child_env("1280x896", latest="out/frame.png", base=base)
        self.assertEqual(env["PS2X_WINDOW_SIZE"], "1280x896")
        self.assertEqual(env["PS2X_HOST_SCREENSHOT_LATEST"], os.path.abspath("out/frame.png"))
        self.assertEqual(base, {"PATH": "x"})           # the caller's dict is not mutated

    def test_window_mode_drops_an_inherited_export_path(self):
        base = {"PS2X_HOST_SCREENSHOT_LATEST": "logs/parity/latest_frame.png"}
        env = scale_shot.child_env("640x448", latest=None, base=base)
        self.assertEqual(env["PS2X_WINDOW_SIZE"], "640x448")
        self.assertNotIn("PS2X_HOST_SCREENSHOT_LATEST", env)

    def test_a_bad_size_is_refused_before_anything_launches(self):
        with self.assertRaises(ValueError):
            scale_shot.child_env("1280", latest=None, base={})


class NewestFrame(unittest.TestCase):
    def _touch(self, path, mtime):
        with open(path, "wb") as fp:
            fp.write(b"x")
        os.utime(path, (mtime, mtime))

    def test_the_half_written_tmp_is_never_chosen(self):
        d = tempfile.mkdtemp()
        latest = os.path.join(d, "latest_frame.png")
        now = time.time()
        self._touch(os.path.join(d, "old.png"), now - 100)
        self._touch(latest, now - 10)
        self._touch(latest + ".tmp.png", now)        # newest of all, and torn
        self.assertEqual(scale_shot.newest_frame(latest), latest)

    def test_no_export_yet_is_none_not_a_crash(self):
        d = tempfile.mkdtemp()
        self.assertIsNone(scale_shot.newest_frame(os.path.join(d, "latest_frame.png")))

    def test_a_missing_directory_is_none(self):
        self.assertIsNone(scale_shot.newest_frame(
            os.path.join(tempfile.mkdtemp(), "nope", "latest_frame.png")))


class BothExitCode(unittest.TestCase):
    """--both's contract, with the two launches stubbed out: same seconds, 1x first, then 2x."""

    def _run(self, diff):
        calls = []

        def fake_shoot(out, size, seconds, *a, **kw):
            calls.append((out, size, seconds))
            return 0

        with mock.patch.object(scale_shot, "shoot", fake_shoot), \
             mock.patch.object(scale_shot.scale_compare, "mean_abs_diff", lambda b, s, k: diff):
            rc = scale_shot.both("out/s7_scale", seconds=40)
        return rc, calls

    def test_below_the_bar_is_zero_and_runs_1x_first(self):
        rc, calls = self._run(0.4)
        self.assertEqual(rc, 0)
        self.assertEqual([c[1] for c in calls], ["640x448", "1280x896"])
        self.assertEqual([c[2] for c in calls], [40, 40])
        self.assertEqual([os.path.basename(c[0]) for c in calls],
                         ["s7_scale_1x.png", "s7_scale_2x.png"])

    def test_above_the_bar_is_one(self):
        rc, _ = self._run(7.5)
        self.assertEqual(rc, 1)

    def test_a_failed_launch_stops_before_the_second_size(self):
        calls = []
        with mock.patch.object(scale_shot, "shoot",
                               lambda out, size, seconds, *a, **kw: calls.append(size) or 1):
            self.assertEqual(scale_shot.both("out/s7_scale", seconds=40), 1)
        self.assertEqual(calls, ["640x448"])


if __name__ == "__main__":
    unittest.main()
