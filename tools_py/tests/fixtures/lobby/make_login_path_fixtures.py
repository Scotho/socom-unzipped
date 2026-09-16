"""Regenerate the main-menu ONLINE row and persona-stage fixtures (Sprint 6, launch s6_ladder7, `press_online` and
the verified persona CROSSes in `login`) from the git-ignored captures under logs/parity/. Each fixture is a
grayscale crop of a 640x448 capture at the box (x0, y0, x1, y1) recorded here; tools_py/tests/test_login_path.py
pastes it back into a black frame at that box. Run from the repo root:
    python tools_py/tests/fixtures/lobby/make_login_path_fixtures.py

The main menu of the block-pointer exe is NEW GAME / ONLINE / LAN (rows at y 278-296, 312-332, 348-364); the lit
row's text pulses in size (ONLINE lit spans x 267-370 in s6_ladder7's capture and 243-394 in wtb4's / 3b's), so the
detector reads the median of the text's core (x 262-368: lit 114-146, dim 15-43) and not its width or shape.
No capture shows this layout with NEW GAME lit (every timeout capture -- wtb4, 3b, s6_ladder7 -- shows ONLINE lit:
the DOWN registered and the CROSS was dropped); test_login_path builds that frame by swapping the lit and dim crops.

The persona-stage fixtures are the on-screen keyboard's panel area of B's 02_persona (the CONNECT TO SOCOM II form,
cursor on PASSWORD) and 03_name (the password keyboard open over it): 60 % of the whole-frame change the keyboard
makes (mean |diff| 16.5) lies in this box, so the pasted frames differ by ~9.9 and identical crops by 0.
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
LAD7 = "logs/parity/s6_ladder7"
MENU_X = (262, 368)                                     # the text core of the three menu rows
ROW_NEW_GAME = (MENU_X[0], 278, MENU_X[1], 296)
ROW_ONLINE = (MENU_X[0], 312, MENU_X[1], 332)
ROW_LAN = (MENU_X[0], 348, MENU_X[1], 364)
OSK_PANEL = (20, 200, 475, 432)                         # the keyboard's panel (title, text row, keys)

FIXTURES = {
    "menu_row_new_game_dim_lad7.png": (f"{LAD7}/A_lobby_fail_pre-login.png", ROW_NEW_GAME),
    "menu_row_online_lit_lad7.png": (f"{LAD7}/A_lobby_fail_pre-login.png", ROW_ONLINE),
    "menu_row_lan_dim_lad7.png": (f"{LAD7}/A_lobby_fail_pre-login.png", ROW_LAN),
    "menu_row_online_login_screen_lad7.png": (f"{LAD7}/B_00_login.png", ROW_ONLINE),
    "osk_panel_form_lad7.png": (f"{LAD7}/B_02_persona.png", OSK_PANEL),
    "osk_panel_kbd_lad7.png": (f"{LAD7}/B_03_name.png", OSK_PANEL),
}

if __name__ == "__main__":
    for name, (src, box) in FIXTURES.items():
        im = Image.open(src).convert("L")
        assert im.size == (640, 448), (src, im.size)
        im.crop(box).save(os.path.join(HERE, name), optimize=True)
        print(name, os.path.getsize(os.path.join(HERE, name)), "bytes")
