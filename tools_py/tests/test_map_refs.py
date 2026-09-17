"""The CHOOSE GAMES map references (scripts/parity/refs/map_<slug>.png): one per map on the CREATE GAME PLAY
LIST as scanned on 2026-09-13 (online_login_ours.MAP_SCAN_ORDER), cut from logs/parity/ours_task8_mapscan by
the crop geometry choose_map uses, and named by a slug so that RAT'S NEST or THE MIXER give plain file names."""
import os
import unittest

import numpy as np
from PIL import Image

from tools_py.parity import online_login_ours as L

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MapRefNames(unittest.TestCase):
    def test_slug_names(self):
        self.assertEqual(os.path.basename(L.map_ref_path("frostfire")), "map_frostfire.png")
        self.assertEqual(os.path.basename(L.map_ref_path("FROSTFIRE")), "map_frostfire.png")
        self.assertEqual(os.path.basename(L.map_ref_path("RAT'S NEST")), "map_rats_nest.png")
        self.assertEqual(os.path.basename(L.map_ref_path("the mixer")), "map_the_mixer.png")
        self.assertEqual(os.path.basename(L.map_ref_path("Shadow Falls")), "map_shadow_falls.png")

    def test_every_scanned_map_has_a_reference_of_the_row_size(self):
        self.assertEqual(len(L.MAP_SCAN_ORDER), 24)
        for name in L.MAP_SCAN_ORDER:
            path = os.path.join(ROOT, L.map_ref_path(name))
            self.assertTrue(os.path.exists(path), path)
            with Image.open(path) as im:
                self.assertEqual(im.size, (L.MAP_ROW_X1 - L.MAP_ROW_X0, L.MAP_ROW_H), path)

    def test_references_do_not_confuse_each_other(self):
        """Every reference scores under 0.05 against itself and at least MAP_MATCH_THRESH against every other."""
        refs = {name: L.map_ref(name) for name in L.MAP_SCAN_ORDER}
        for a, ra in refs.items():
            for b, rb in refs.items():
                d = L.map_mask_distance(ra, rb)
                if a == b:
                    self.assertLess(d, 0.05, (a, b, d))
                else:
                    self.assertGreaterEqual(d, L.MAP_MATCH_THRESH, (a, b, d))


if __name__ == "__main__":
    unittest.main()
