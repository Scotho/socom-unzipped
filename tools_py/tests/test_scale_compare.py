import unittest
import numpy as np
from PIL import Image
from tools_py.parity import scale_compare

def _png(tmp, arr):
    Image.fromarray(arr.astype("uint8"), "L").save(tmp)
    return tmp

class Diff(unittest.TestCase):
    def test_a_perfect_2x_nearest_upscale_scores_zero(self):
        import tempfile, os
        small = np.random.RandomState(7).randint(0, 255, (64, 64))
        big = np.kron(small, np.ones((2, 2)))
        d = tempfile.mkdtemp()
        s = scale_compare.mean_abs_diff(_png(os.path.join(d, "b.png"), big), _png(os.path.join(d, "s.png"), small), 2)
        self.assertEqual(s, 0.0)
    def test_a_shifted_image_scores_above_three(self):
        import tempfile, os
        small = np.random.RandomState(9).randint(0, 255, (64, 64))
        big = np.kron(np.roll(small, 3, axis=1), np.ones((2, 2)))
        d = tempfile.mkdtemp()
        s = scale_compare.mean_abs_diff(_png(os.path.join(d, "b.png"), big), _png(os.path.join(d, "s.png"), small), 2)
        self.assertGreater(s, 3.0)
    def test_mismatched_shapes_raise(self):
        import tempfile, os
        d = tempfile.mkdtemp()
        a = _png(os.path.join(d, "a.png"), np.zeros((100, 100)))
        b = _png(os.path.join(d, "c.png"), np.zeros((64, 64)))
        with self.assertRaises(ValueError):
            scale_compare.mean_abs_diff(a, b, 2)
