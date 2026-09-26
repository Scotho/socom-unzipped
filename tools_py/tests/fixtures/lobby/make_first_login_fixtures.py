"""Regenerate the first-time-login fixtures (Sprint 8: a server with no saved persona) from the
git-ignored captures under logs/parity/. Each fixture is a grayscale crop of a 640x448 capture at the
box (x0, y0, x1, y1) recorded here; tools_py/tests/test_first_login.py pastes it back into a black
frame at that box. Run from the repo root:
    python tools_py/tests/fixtures/lobby/make_first_login_fixtures.py

The two sources are the reference captures of 2026-09-19:
  logs/parity/s8_lan_login_check/A_02_persona.png -- the LAN server (the dev box's LAN address): PLAYER NAME shows
      the persona saved on the card ("socomc") and the cursor is on PASSWORD;
  logs/parity/s8_hosted_control/A_02_persona.png -- the hosted Horizon (3.143.65.100), which keeps
      personas per server and has none: PLAYER NAME is empty and lit.
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROW_PLAYER_NAME = (20, 106, 160, 128)      # the PLAYER NAME row label (LOBBY_ROWS["player_name"])
ROW_PASSWORD = (20, 136, 160, 158)         # the PASSWORD row label (LOBBY_ROWS["password"])
NAME_VALUE = (172, 106, 400, 128)          # the PLAYER NAME value strip (LOGIN_NAME_VALUE)
OSK_TITLE = (24, 202, 400, 222)            # the keyboard panel's title (OSK_TITLE)

LAN = "logs/parity/s8_lan_login_check"
HOST = "logs/parity/s8_hosted_control"

FIXTURES = {
    # PLAYER NAME prefilled from the card ("socomc", 6 glyphs), cursor on PASSWORD
    "row_player_name_unlit_s8lan.png": (f"{LAN}/A_02_persona.png", ROW_PLAYER_NAME),
    "row_password_lit_s8lan.png": (f"{LAN}/A_02_persona.png", ROW_PASSWORD),
    "name_value_socomc_s8lan.png": (f"{LAN}/A_02_persona.png", NAME_VALUE),
    # a fresh server: PLAYER NAME empty and lit, PASSWORD unlit (and greyed)
    "row_player_name_lit_s8host.png": (f"{HOST}/A_02_persona.png", ROW_PLAYER_NAME),
    "row_password_unlit_s8host.png": (f"{HOST}/A_02_persona.png", ROW_PASSWORD),
    "name_value_empty_s8host.png": (f"{HOST}/A_02_persona.png", NAME_VALUE),
    # the same form after the harness typed the PASSWORD into the name ("socom", 5 glyphs)
    "name_value_socom_s8host.png": (f"{HOST}/A_05_password.png", NAME_VALUE),
    # the two keyboards: "Enter Player Name" (text ends at column 163) vs "Enter Player Password" (195)
    "osk_title_name_s8host.png": (f"{HOST}/A_04_pw_kbd.png", OSK_TITLE),
    "osk_title_password_s8lan.png": (f"{LAN}/A_04_pw_kbd.png", OSK_TITLE),
}

if __name__ == "__main__":
    total = 0
    for name, (src, box) in FIXTURES.items():
        im = Image.open(src).convert("L")
        assert im.size == (640, 448), (src, im.size)
        path = os.path.join(HERE, name)
        im.crop(box).save(path, optimize=True)
        total += os.path.getsize(path)
        print(name, os.path.getsize(path), "bytes")
    print("total", total, "bytes")
