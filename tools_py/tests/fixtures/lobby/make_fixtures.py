"""Regenerate the lobby signature fixtures from the launch 8a/8b/8c captures (git-ignored under logs/).

Each fixture is a grayscale crop of a 640x448 capture; FIXTURES records the crop box (x0, y0, x1, y1), and
the tests paste the crop back into a black 640x448 frame at that box. Run from the repo root:
    python tools_py/tests/fixtures/lobby/make_fixtures.py
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = (335, 110, 625, 380)       # SELECTED MAPS panel, x 335-625, y 110-380
READY = (14, 150, 175, 190)        # GAME LOBBY row 2 label (x 22-165, y 158-180) with a margin

FIXTURES = {
    "map_8b_pre.png": ("logs/parity/s5_t1_launch8b_medley/A_14b_map_medley.png", PANEL),
    "map_8b_post_dropped.png": ("logs/parity/s5_t1_launch8b_medley/A_15_play_list.png", PANEL),
    "map_8c_pre.png": ("logs/parity/s5_t1_launch8c_medley/A_14b_map_medley.png", PANEL),
    "map_8c_post_taken.png": ("logs/parity/s5_t1_launch8c_medley/A_15_play_list.png", PANEL),
    "ready_8a_A_dropped.png": ("logs/parity/s5_t1_launch8_medley/A_19_ready.png", READY),
    "ready_8a_B_taken.png": ("logs/parity/s5_t1_launch8_medley/B_19_ready.png", READY),
    "ready_8c_A_left_lobby.png": ("logs/parity/s5_t1_launch8c_medley/A_19_ready.png", READY),
}

if __name__ == "__main__":
    for name, (src, box) in FIXTURES.items():
        im = Image.open(src).convert("L")
        assert im.size == (640, 448), (src, im.size)
        im.crop(box).save(os.path.join(HERE, name), optimize=True)
        print(name, os.path.getsize(os.path.join(HERE, name)), "bytes")
