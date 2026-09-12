import unittest

import numpy as np
from PIL import Image

from tools_py.parity.drive import crop_to_content


def _img(a):
    return Image.fromarray(a.astype(np.uint8))


class CropToContent(unittest.TestCase):
    """crop_to_content(im, thresh=8) is what frame() and the untilref/ifref reference-thumbnail
    builders call before the 160x112 resize, so a resized game window's black bars get cropped
    away instead of shifting every comparison."""

    def test_pillarboxed_frame_crops_to_content(self):
        a = np.zeros((112, 200, 3)); a[:, 40:160] = 200          # 120-wide content, black bars
        out = np.asarray(crop_to_content(_img(a)))
        self.assertEqual(out.shape[1], 120)
        self.assertEqual(out.shape[0], 112)

    def test_letterboxed_frame_crops_to_content(self):
        a = np.zeros((200, 160, 3)); a[40:160, :] = 200
        out = np.asarray(crop_to_content(_img(a)))
        self.assertEqual(out.shape[0], 120)

    def test_untouched_when_no_border(self):
        a = np.full((112, 160, 3), 128)
        self.assertEqual(np.asarray(crop_to_content(_img(a))).shape, (112, 160, 3))

    def test_all_black_frame_is_returned_unchanged(self):
        a = np.zeros((112, 160, 3))                               # the transition gate scores these
        self.assertEqual(np.asarray(crop_to_content(_img(a))).shape, (112, 160, 3))

    def test_near_black_content_is_not_cropped_away(self):
        a = np.zeros((112, 160, 3)); a[:, 40:120] = 12            # dim but above threshold
        self.assertEqual(np.asarray(crop_to_content(_img(a))).shape[1], 80)


if __name__ == "__main__":
    unittest.main()
