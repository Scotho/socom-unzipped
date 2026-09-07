from PIL import Image, ImageDraw
from tools_py.parity import compare


def logo(x):
    im = Image.new("RGB", (640, 448), (10, 10, 40))
    ImageDraw.Draw(im).rectangle([x, 45, x + 200, 120], fill=(230, 230, 230))
    return im


def test_identical_is_100():
    assert compare.score(logo(70), logo(70))["score"] == 100


def test_shift_scores_lower():
    small = compare.score(logo(70), logo(80))["score"]
    big = compare.score(logo(70), logo(300))["score"]
    assert big < small < 100


def test_side_by_side_size():
    assert compare.side_by_side(logo(70), logo(80)).size == (960, 224)
