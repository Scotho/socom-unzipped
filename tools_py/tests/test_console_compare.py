"""console_compare: the mission gate's console-vs-ours leg at the Seeding Chaos spawn (Sprint 6 Task 1b).

Measured 2026-09-15 on the slot-8 console reference and four of our clean s28 captures (s6_depth_m2, s6_depth_legacy,
s5_head_1x_b, s5_head_1x), all through the same content crop and 640x448 resize:

  whole-frame masked mean |diff|:  ours vs console 44-46;  ours vs ours 3-10 (24 against a HELP pop-up frame)
  brightness-normalised:            ours vs console 0.41-0.43;  ours vs ours 0.17-0.44   <- does NOT separate
  water footprint (rows 190-340, cols 120-520), 7x7 local std <= 1.2 "flat" fraction:  console 0.188;  ours 0.498-0.597
  water footprint near-black (< 12) fraction:                                            console 0.084;  ours 0.293-0.306

So the whole-frame numbers are reported for the trend (the global darkness divergence, research/20 §4.3, dominates
them) and the verdict rests on the two water statistics, whose margins are 2.6x and 3.5x."""
import unittest

import numpy as np
from PIL import Image

from tools_py.parity import console_compare as cc

CONSOLE = "scripts/parity/refs/console_spawn_slot8.png"
OURS = "tools_py/tests/fixtures/mission/gameplay_spawn.png"       # s6_depth_m2 s28: the shards


class Score(unittest.TestCase):
    def test_identical_frames_score_zero(self):
        self.assertEqual(cc.score(CONSOLE, CONSOLE), 0.0)

    def test_our_spawn_is_far_from_the_console_whole_frame(self):
        s = cc.score(OURS, CONSOLE)
        self.assertGreater(s, 30.0)          # 44.8 measured; informational, the verdict is not taken from it

    def test_mask_hides_the_hud_and_the_objective_text(self):
        m = cc.default_mask()
        self.assertEqual(m.shape, (448, 640))
        self.assertFalse(m[340:448, :].any())
        self.assertFalse(m[50:100, 200:440].any())
        self.assertTrue(m[200:300, 150:500].all())


class WaterVerdict(unittest.TestCase):
    def test_console_water_passes(self):
        ok, detail = cc.water_verdict(CONSOLE)
        self.assertTrue(ok, detail)

    def test_our_shards_fail(self):
        ok, detail = cc.water_verdict(OURS)
        self.assertFalse(ok, detail)
        st = cc.water_stats(OURS)
        self.assertGreater(st["flat"], cc.WATER_FLAT_MAX)
        self.assertGreater(st["dark"], cc.WATER_DARK_MAX)

    def test_stats_are_fractions(self):
        st = cc.water_stats(CONSOLE)
        for k in ("flat", "dark"):
            self.assertGreaterEqual(st[k], 0.0)
            self.assertLessEqual(st[k], 1.0)

    def test_a_uniform_grey_frame_is_all_flat(self):
        im = Image.fromarray(np.full((448, 640, 3), 40, dtype=np.uint8), "RGB")
        st = cc.water_stats(im)
        self.assertEqual(st["flat"], 1.0)
        self.assertEqual(st["dark"], 0.0)


if __name__ == "__main__":
    unittest.main()
