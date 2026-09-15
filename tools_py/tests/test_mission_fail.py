"""mission_fail.detect: the gate's mission stage must FAIL on a MISSION FAILURE screen.

Sprint 6 Task 1a (owner-agreed 2026-09-14). The fixtures are real captures: `failure_screen.png` is
`logs/parity/gate/s5_head_1x_b/mission/final.png` -- that gate PASSed while its s38/s40 holds sat on the
"MISSION FAILURE / MISSION STATISTICS FOR: SEEDING CHAOS" screen, because the letterbox-band test only asks
whether the bands are lit; `gameplay_spawn.png` is `s6_depth_m2/mission/s28_none.png`, the spawn view."""
import unittest

import numpy as np
from PIL import Image

from tools_py.parity import mission_fail

FAIL = "tools_py/tests/fixtures/mission/failure_screen.png"
PLAY = "tools_py/tests/fixtures/mission/gameplay_spawn.png"


class Detect(unittest.TestCase):
    def test_failure_screen_is_detected(self):
        failed, reason = mission_fail.detect(FAIL)
        self.assertTrue(failed, reason)

    def test_spawn_gameplay_is_not_a_failure(self):
        failed, reason = mission_fail.detect(PLAY)
        self.assertFalse(failed, reason)

    def test_a_black_frame_is_not_a_failure(self):
        im = Image.fromarray(np.zeros((448, 640, 3), dtype=np.uint8), "RGB")
        failed, reason = mission_fail.detect(im)
        self.assertFalse(failed, reason)

    def test_a_lit_random_frame_is_not_a_failure(self):
        rng = np.random.default_rng(3)
        im = Image.fromarray(rng.integers(20, 200, size=(448, 640, 3), dtype=np.uint8), "RGB")
        failed, reason = mission_fail.detect(im)
        self.assertFalse(failed, reason)

    def test_failure_banner_survives_a_small_vertical_shift(self):
        # A resized or slightly letterboxed capture moves the banner a few rows; the detector must not be pinned.
        im = Image.open(FAIL).convert("RGB")
        shifted = Image.fromarray(np.roll(np.asarray(im), 6, axis=0), "RGB")
        failed, reason = mission_fail.detect(shifted)
        self.assertTrue(failed, reason)


if __name__ == "__main__":
    unittest.main()
