"""The committed AVAILABLE MAPS references must exist for every map the harness defaults to, and
must not match each other -- choose_map aborts without a reference, and two references that match
each other would let it accept the wrong map. The map-scan captures they were cut from are
git-ignored, so this checks only what a fresh clone has; the per-capture distances are recorded in
online_login_ours.py next to MAP_MATCH_THRESH."""
import inspect
import os
import unittest

import numpy as np
from PIL import Image

from tools_py.parity import online_login_ours as L


def load(name):
    return np.asarray(Image.open(L.map_ref_path(name)).convert("L"), dtype=np.float32)


class MapReferences(unittest.TestCase):
    MAPS = ("frostfire", "medley")

    def test_references_exist_with_row_geometry(self):
        x0, y0, x1, y1 = L.map_row_box(0)
        for name in self.MAPS:
            with self.subTest(map=name):
                self.assertTrue(os.path.exists(L.map_ref_path(name)))
                self.assertEqual(load(name).shape, (y1 - y0, x1 - x0))

    def test_each_matches_itself_and_not_the_other(self):
        for name in self.MAPS:
            self.assertLessEqual(L.map_mask_distance(load(name), load(name)), L.MAP_MATCH_THRESH)
        self.assertGreater(L.map_mask_distance(load("medley"), load("frostfire")), L.MAP_MATCH_THRESH)

    def test_host_game_default_map_has_a_reference(self):
        default = inspect.signature(L.host_game).parameters["game_map"].default
        self.assertTrue(os.path.exists(L.map_ref_path(default)), default)


if __name__ == "__main__":
    unittest.main()
