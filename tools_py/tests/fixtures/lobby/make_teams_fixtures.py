"""Regenerate the GAME LOBBY team-column and READY-label fixtures for tools_py/tests/test_lobby_teams.py
(Sprint 6, launch s6_ladder9: both players under SEALS, the host's row "NOT READY 3").

Each fixture is a grayscale crop of a 640x448 capture (git-ignored under logs/parity/); FIXTURES records the
crop box (x0, y0, x1, y1) and the tests paste the crop back into a black 640x448 frame at that box. Run from
the repo root:
    python tools_py/tests/fixtures/lobby/make_teams_fixtures.py
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TEAMS = (180, 240, 615, 300)       # SEALS (x 180-390) and TERRORISTS (x 405-615) name columns, rows 240..300
READY = (14, 150, 175, 190)        # GAME LOBBY row 2 label (x 22-165, y 158-180) with a margin, as make_fixtures.py

FIXTURES = {
    # team columns: (seals, terrorists) bright-text pixels as lobby_teams_of reads them
    "teams_lad9_both_seals.png": ("logs/parity/s6_ladder9/A_lobby_fail_timeout_launch.png", TEAMS),   # (288, 0)
    "teams_lad8_one_each.png": ("logs/parity/s6_ladder8/B_16_game_lobby.png", TEAMS),                 # (143, 144)
    "teams_lad5_one_each.png": ("logs/parity/s6_ladder5/B_16_game_lobby.png", TEAMS),                 # (143, 144)
    "teams_lad8_host_alone.png": ("logs/parity/s6_ladder8/A_17_game_lobby_ok.png", TEAMS),            # (143, 0)
    # row-2 label: highlighted (teal fill, text ~117-147) and dim (no cursor on the row, text 83-85)
    "ready_lad9_not_ready_3_lit.png": ("logs/parity/s6_ladder9/A_lobby_fail_timeout_launch.png", READY),
    "ready_lad9_not_ready_34_dim.png": ("logs/parity/s6_ladder9/A_19_ready.png", READY),   # the [None, None] frame
    "ready_lad9_not_ready_lit.png": ("logs/parity/s6_ladder9/B_hold00.png", READY),        # no count suffix
    "ready_lad8_ready_lit.png": ("logs/parity/s6_ladder8/B_16_game_lobby.png", READY),
    "ready_lad8_ready_3_dim.png": ("logs/parity/s6_ladder8/A_17_game_lobby_ok.png", READY),
}

if __name__ == "__main__":
    for name, (src, box) in FIXTURES.items():
        im = Image.open(src).convert("L")
        assert im.size == (640, 448), (src, im.size)
        im.crop(box).save(os.path.join(HERE, name), optimize=True)
        print(name, os.path.getsize(os.path.join(HERE, name)), "bytes")
