"""Issue #30: the title stage's verdict must refuse a lost MENU capture, whatever the count says.

The title run holds the main menu for 23 captures six seconds apart (scripts/parity/title_menu.txt).
On every clean run since the first archived stamp (native_on, 2026-09-10) s00..s18 are the menu and
score 92.0-99.4 against scripts/parity/ref_main_menu_ours.png (the lowest, 92.0, is 2.0 over the 90 bar;
the lowest s18 alone is 93.0), and s19..s22 are the game's idle attract
sequence (the menu fading to black, then the mission flyovers), which is correct behaviour and scores
50-89. The old bar (>= 16 of 23 at 90) therefore had three captures of slack INSIDE the menu window:
s7_cpu_fallback2 (2026-09-17) froze on the menu-over-black at s16 and PASSED at 16/23.

The rule under test (research/64): every capture in the menu window s00..s18 that a run wrote must
score >= TITLE_MIN_SCORE, because on the reference record each of those positions matched the
reference, and so did the capture before it. The attract tail s19..s22 is printed, not counted.

Why a fixed window and not Task V1 Step 2's literal rule ("refuse a capture under 90 whose predecessor
matched the reference"): applied at run time to every capture, the literal rule refuses every clean run
at the fade, because s18 matches and s19 (the menu fading to black) scores 83-89 -- 130 of the 144
archived stamps whose menu window is whole (the 123 standing 19/23 runs and the 7 with the attract one
capture late; research/64, command G). The predecessor evidence is used where it holds: the window
s00..s18 is the set of positions that matched, capture after capture, on the whole record.

The fixtures are synthetic: a small generated gradient stands in for the menu reference, a copy of it
for a menu capture, and a dark or inverted frame for anything else. No game bytes.
"""
import os
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from tools_py.parity import gate


def _menu_image():
    """A 320x224 stand-in for the menu: horizontal and vertical ramps, so an inverted or darkened
    copy differs in every 16x16 block compare.score looks at."""
    x = np.linspace(0, 255, 320, dtype=np.float32)[None, :]
    y = np.linspace(0, 255, 224, dtype=np.float32)[:, None]
    rgb = np.stack([np.broadcast_to(x, (224, 320)),
                    np.broadcast_to(y, (224, 320)),
                    np.broadcast_to((x + y) / 2, (224, 320))], axis=2)
    return Image.fromarray(rgb.astype("uint8"), "RGB")


def _faded(img, factor):
    """The menu fading to black (the first attract frame on a real run scores 83-92)."""
    return Image.fromarray((np.asarray(img, dtype=np.float32) * factor).astype("uint8"), "RGB")


def _other(img):
    """Not the menu at all: the attract flyover, a frozen black frame."""
    return Image.fromarray(255 - np.asarray(img), "RGB")


class TitleMenuWindow(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.menu = _menu_image()
        self.ref = os.path.join(self.root, "ref_menu.png")
        self.menu.save(self.ref)
        patcher = mock.patch.object(gate, "TITLE_REF", self.ref)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, frames):
        """frames: 23 PIL images for s00..s22, written as sNN_none.png like drive.py does."""
        run = os.path.join(self.root, "title")
        os.makedirs(run, exist_ok=True)
        for i, im in enumerate(frames):
            im.save(os.path.join(run, "s%02d_none.png" % i))
        return gate.score_title(run)

    def test_the_fixture_frames_score_where_the_real_ones_do(self):
        """Guard on the fixture itself: a copy is >= 90, a dark fade and an inverted frame are < 90."""
        with Image.open(self.ref) as ref:
            self.assertGreaterEqual(gate.compare.score(ref, self.menu)["score"], gate.TITLE_MIN_SCORE)
            self.assertLess(gate.compare.score(ref, _faded(self.menu, 0.6))["score"], gate.TITLE_MIN_SCORE)
            self.assertLess(gate.compare.score(ref, _other(self.menu))["score"], gate.TITLE_MIN_SCORE)

    def test_standing_run_passes(self):
        """The shape of every clean gate since 2026-09-10: s00..s18 the menu, s19 the fade, s20..s22
        the flyovers -- 19/23, PASS."""
        frames = [self.menu] * 19 + [_faded(self.menu, 0.6)] + [_other(self.menu)] * 3
        ok, detail = self._run(frames)
        self.assertTrue(ok, detail)

    def test_attract_one_capture_late_passes(self):
        """s8_close_gate's shape (20/23): the fade landed on s20 instead of s19. The attract's phase
        moves by a capture between runs; that is not a loss."""
        frames = [self.menu] * 20 + [_faded(self.menu, 0.6)] + [_other(self.menu)] * 2
        ok, detail = self._run(frames)
        self.assertTrue(ok, detail)

    def test_no_attract_passes_and_is_named(self):
        """s8_audio_mc_gate2's shape (23/23): the attract never started inside the window. The menu is
        whole, so PASS, but the detail says the attract was not reached."""
        ok, detail = self._run([self.menu] * 23)
        self.assertTrue(ok, detail)
        self.assertIn("attract not reached", detail)

    def test_a_lost_menu_capture_is_refused(self):
        """The 'kept passing' half of #30: s18 matched the reference on the record, and so did s17,
        the capture before it; here s18 falls under 90 while the count (18/23) is still over 16.
        The old verdict passed this; the stage must refuse it and name the capture."""
        frames = [self.menu] * 18 + [_faded(self.menu, 0.6)] + [_other(self.menu)] * 4
        ok, detail = self._run(frames)
        self.assertFalse(ok, detail)
        self.assertIn("s18", detail.split("scores:")[0])

    def test_frozen_at_the_fade_is_refused(self):
        """s7_cpu_fallback2's shape (2026-09-17, PASSED at 16/23): the game stuck on the menu-over-
        black from s16 on, s16..s22 all ~82.7. Three menu captures lost."""
        frames = [self.menu] * 16 + [_faded(self.menu, 0.6)] * 7
        ok, detail = self._run(frames)
        self.assertFalse(ok, detail)
        head = detail.split("scores:")[0]
        for name in ("s16", "s17", "s18"):
            self.assertIn(name, head)

    def test_short_run_keeps_the_old_floor(self):
        """A run that wrote fewer captures than the menu window (the committed 16-capture fixture under
        tests/fixtures/gate/title) is judged on the captures it has, with TITLE_MIN_MATCHES as the
        floor on how many that must be."""
        ok, detail = self._run([self.menu] * gate.TITLE_MIN_MATCHES)
        self.assertTrue(ok, detail)
        run = os.path.join(self.root, "short")
        os.makedirs(run)
        for i in range(gate.TITLE_MIN_MATCHES - 1):
            self.menu.save(os.path.join(run, "s%02d_none.png" % i))
        ok, detail = gate.score_title(run)
        self.assertFalse(ok, detail)


if __name__ == "__main__":
    unittest.main()
