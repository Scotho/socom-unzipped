"""drive.py's `ifpopup` step: dismiss an in-game HELP pop-up ("PRESS X TO CONTINUE") before a hold.

A HELP pop-up pauses gameplay behind a lit HUD, so a hold sent over it moves nothing and the mission
gate's liveness scorer (rightly) FAILs the run: `s5_head_1x` and `s6_depth_m2` both had 6/6 gameplay-band
holds with frame diffs 0.00-0.05 (docs/KNOWN.md section 4). The step presses CROSS only while the prompt
is on screen and never on a clean gameplay frame, where a stray CROSS would fire the weapon's alternate
action or dismiss nothing."""
import os
import tempfile
import types
import unittest

import numpy as np
from PIL import Image

from tools_py.parity import drive


def _popup_frame():
    return Image.open("scripts/parity/ref_hud_ours.png").convert("RGB")


def _clean_frame():
    rng = np.random.default_rng(7)
    return Image.fromarray(rng.integers(20, 200, size=(448, 640, 3), dtype=np.uint8), "RGB")


def _cinematic_frame():
    # s6_depth_m4 s31: the "X TO ABORT" objective cinematic that starts a few seconds after the HUD first shows;
    # letterboxed (bands 0.33), not black, and it swallowed the first four holds of that gate run.
    return Image.open("tools_py/tests/fixtures/mission/cinematic_abort.png").convert("RGB")


def _black_frame():
    return Image.fromarray(np.zeros((448, 640, 3), dtype=np.uint8), "RGB")


class PopupPresent(unittest.TestCase):
    def test_committed_hud_reference_carries_the_prompt(self):
        self.assertTrue(drive.popup_present(_popup_frame()))

    def test_lit_frame_without_prompt_is_clean(self):
        self.assertFalse(drive.popup_present(_clean_frame()))


class NeedsCross(unittest.TestCase):
    """needs_cross(im) -> (press, reason): anything a hold must not be sent over that CROSS dismisses."""

    def test_help_popup_needs_cross(self):
        press, reason = drive.needs_cross(_popup_frame())
        self.assertTrue(press, reason)
        self.assertIn("pop-up", reason)

    def test_letterboxed_cinematic_needs_cross(self):
        press, reason = drive.needs_cross(_cinematic_frame())
        self.assertTrue(press, reason)
        self.assertIn("cinematic", reason)

    def test_live_gameplay_needs_nothing(self):
        press, reason = drive.needs_cross(_clean_frame())
        self.assertFalse(press, reason)

    def test_black_loading_frame_needs_nothing(self):
        press, reason = drive.needs_cross(_black_frame())
        self.assertFalse(press, reason)


class IfPopupStep(unittest.TestCase):
    """run_steps with the window replaced by a scripted frame sequence and the key sender recorded."""

    def _run(self, frames, steps_text):
        presses = []
        seq = list(frames)

        def grab(hwnd, max_age=None):
            if len(seq) > 1:
                return seq.pop(0)
            return seq[0]

        saved = (drive.winshot.grab, drive.keys.press, drive.wait_stable, drive.time.sleep)
        drive.winshot.grab = grab
        drive.keys.press = lambda hwnd, b, target, hold_s=None: presses.append(b)
        drive.wait_stable = lambda *a, **k: (True, 0.0)
        drive.time.sleep = lambda s: None
        try:
            with tempfile.TemporaryDirectory() as out:
                a = types.SimpleNamespace(out=out, settle=0.0, maxwait=0.0, target="ours", tail=0.0)
                manifest = []
                drive.run_steps(a, drive.parse(steps_text), None, None, 0.0, None, manifest)
                caps = sorted(f for f in os.listdir(out) if f.startswith("s00_"))
        finally:
            drive.winshot.grab, drive.keys.press, drive.wait_stable, drive.time.sleep = saved
        return presses, caps

    def test_presses_cross_while_the_prompt_shows_and_stops_when_it_is_gone(self):
        # Two pop-up frames, then gameplay: two CROSS presses, none over the clean frame.
        presses, caps = self._run([_popup_frame(), _popup_frame(), _clean_frame()], "ifpopup+0.1:CROSS")
        self.assertEqual(presses, ["CROSS", "CROSS"])
        self.assertEqual(caps, ["s00_none.png"])       # the step's own press is consumed; nothing extra

    def test_presses_nothing_on_a_clean_gameplay_frame(self):
        presses, _ = self._run([_clean_frame()], "ifpopup+0.1:CROSS")
        self.assertEqual(presses, [])

    def test_gives_up_after_six_presses_on_a_prompt_that_never_clears(self):
        presses, _ = self._run([_popup_frame()], "ifpopup+0.1:CROSS")
        self.assertEqual(presses, ["CROSS"] * 6)

    def test_skips_a_cinematic_then_stops_on_gameplay(self):
        presses, _ = self._run([_cinematic_frame(), _clean_frame()], "ifpopup+0.1:CROSS")
        self.assertEqual(presses, ["CROSS"])

    def test_waits_through_a_black_frame_without_pressing(self):
        presses, _ = self._run([_black_frame()], "ifpopup+0.1:CROSS")
        self.assertEqual(presses, [])


if __name__ == "__main__":
    unittest.main()
