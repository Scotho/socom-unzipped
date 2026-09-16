"""Regenerate the CONNECT TO SOCOM II form fixtures (Sprint 6, launch s6_ladder6, `press_connect`) from the
git-ignored captures under logs/parity/. Each fixture is a grayscale crop of a 640x448 capture at the box
(x0, y0, x1, y1) recorded here; tools_py/tests/test_login_connect.py pastes it back into a black frame at that
box. Run from the repo root:
    python tools_py/tests/fixtures/lobby/make_login_fixtures.py
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CONNECT = (20, 366, 160, 390)      # the CONNECT button, bottom left (LOBBY_ROWS["connect"])
GENDER = (20, 226, 160, 246)       # the GENDER row (LOBBY_ROWS["gender"])
PROMPT = (150, 74, 490, 90)        # the form's prompt band (LOGIN_FORM_PROMPT reads x 230-415 of it)

FIXTURES = {
    "row_connect_lit_lad2.png": ("logs/parity/s5_t5_ladder2/A_06_connect_focus.png", CONNECT),
    "row_connect_unlit_lad6.png": ("logs/parity/s6_ladder6/A_06_connect_focus.png", CONNECT),
    "row_gender_lit_lad6.png": ("logs/parity/s6_ladder6/A_06_connect_focus.png", GENDER),
    "row_gender_unlit_lad2.png": ("logs/parity/s5_t5_ladder2/A_06_connect_focus.png", GENDER),
    "prompt_connect_lad2.png": ("logs/parity/s5_t5_ladder2/A_06_connect_focus.png", PROMPT),
    "prompt_gender_lad6.png": ("logs/parity/s6_ladder6/A_06_connect_focus.png", PROMPT),
    "prompt_password_lad2.png": ("logs/parity/s5_t5_ladder2/A_05_password.png", PROMPT),
    "prompt_gone_lad2.png": ("logs/parity/s5_t5_ladder2/A_07_after_connect.png", PROMPT),
    "prompt_eula_lad2.png": ("logs/parity/s5_t5_ladder2/A_08_eula.png", PROMPT),
}

if __name__ == "__main__":
    for name, (src, box) in FIXTURES.items():
        im = Image.open(src).convert("L")
        assert im.size == (640, 448), (src, im.size)
        im.crop(box).save(os.path.join(HERE, name), optimize=True)
        print(name, os.path.getsize(os.path.join(HERE, name)), "bytes")
