import numpy as np
from PIL import Image
from tools_py.parity.drive import crop_to_content

def _img(a):
    return Image.fromarray(a.astype(np.uint8))

def test_pillarboxed_frame_crops_to_content():
    a = np.zeros((112, 200, 3)); a[:, 40:160] = 200          # 120-wide content, black bars
    out = np.asarray(crop_to_content(_img(a)))
    assert out.shape[1] == 120 and out.shape[0] == 112

def test_letterboxed_frame_crops_to_content():
    a = np.zeros((200, 160, 3)); a[40:160, :] = 200
    out = np.asarray(crop_to_content(_img(a)))
    assert out.shape[0] == 120

def test_untouched_when_no_border():
    a = np.full((112, 160, 3), 128)
    assert np.asarray(crop_to_content(_img(a))).shape == (112, 160, 3)

def test_all_black_frame_is_returned_unchanged():
    a = np.zeros((112, 160, 3))                               # the transition gate scores these
    assert np.asarray(crop_to_content(_img(a))).shape == (112, 160, 3)

def test_near_black_content_is_not_cropped_away():
    a = np.zeros((112, 160, 3)); a[:, 40:120] = 12            # dim but above threshold
    assert np.asarray(crop_to_content(_img(a))).shape[1] == 80
