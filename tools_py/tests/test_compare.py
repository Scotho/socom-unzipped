"""compare.score / compare.side_by_side -- the title gate's scoring core.

Moved from tools_py/parity/test_compare.py (Sprint 5 Task 0): it was pytest-style and had never run.
"""
import unittest

from PIL import Image, ImageDraw

from tools_py.parity import compare


def logo(x):
    im = Image.new("RGB", (640, 448), (10, 10, 40))
    ImageDraw.Draw(im).rectangle([x, 45, x + 200, 120], fill=(230, 230, 230))
    return im


class TestCompare(unittest.TestCase):
    def test_identical_is_100(self):
        self.assertEqual(compare.score(logo(70), logo(70))["score"], 100)

    def test_shift_scores_lower(self):
        small = compare.score(logo(70), logo(80))["score"]
        big = compare.score(logo(70), logo(300))["score"]
        self.assertLess(big, small)
        self.assertLess(small, 100)

    def test_side_by_side_size(self):
        self.assertEqual(compare.side_by_side(logo(70), logo(80)).size, (960, 224))


if __name__ == "__main__":
    unittest.main()
