"""Sprint 6 (launch s6_ladder3): fixtures for the AVAILABLE MAPS search in tools_py/parity/online_login_ours.py
(choose_map), read by tools_py/tests/test_map_search.py.

All are grayscale crops of real 640x448 captures under git-ignored logs/parity/. The tests paste them back into
a black frame at the MAP_ROW_* geometry (rows of 214x12 at x 78, y 117 + 20*i), so map_cursor and
map_mask_distance read the pixels where a live frame has them.

Two kinds:
  maplist_*.png  -- the whole six-row list region (78, 117, 292, 237) of one capture, for the real-capture
                    regression (which row is highlighted, which rows match a reference).
  maprow_*.png   -- one row (214x12), pasted at any row index to script a frame: a highlighted or pale
                    FROSTFIRE, a highlighted or pale other map, an empty row.

Run from the repo root:  python tools_py/tests/fixtures/lobby/make_map_fixtures.py
"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
X0, TOP, X1, PITCH, H, ROWS = 78, 117, 292, 20, 12, 6
LIST = (X0, TOP, X1, TOP + PITCH * ROWS)


def row(i):
    return X0, TOP + PITCH * i, X1, TOP + PITCH * i + H


SCAN = "logs/parity/ours_task8_mapscan"
LAD2 = "logs/parity/s5_t5_ladder2"
LAD3 = "logs/parity/s6_ladder3"

FIXTURES = {
    # the failing launch's last frame: cursor row 4 on THE RUINS, no FROSTFIRE anywhere (0.575 at best)
    "maplist_s6_lad3_not_found.png": (f"{LAD3}/A_14_map_frostfire_NOT_FOUND.png", LIST),
    # Sprint 5 ladder2's CHOOSE GAMES: cursor row 0 on Medley (0.000 against map_medley.png)
    "maplist_s5_lad2_medley.png": (f"{LAD2}/A_14_choose_games.png", LIST),
    # highlighted FROSTFIRE from a launch other than the reference's scan (0.005, cross-launch)
    "maprow_frostfire_lit_lad2.png": (f"{LAD2}/A_14b_map_frostfire.png", row(4)),
    # UNhighlighted FROSTFIRE (pale text, peak 170): 0.047 against the reference
    "maprow_frostfire_pale_scan17.png": (f"{SCAN}/A_mapscan_17.png", row(2)),
    # highlighted BLIZZARD (the entry above FROSTFIRE): 0.694 against map_frostfire.png
    "maprow_blizzard_lit_scan14.png": (f"{SCAN}/A_mapscan_14.png", row(4)),
    # pale REQUIEM: 0.667
    "maprow_requiem_pale_scan14.png": (f"{SCAN}/A_mapscan_14.png", row(3)),
    # an empty row past the end of the list (peak 110)
    "maprow_empty_scan23.png": (f"{SCAN}/A_mapscan_23.png", row(5)),
}


def main():
    for name, (src, box) in FIXTURES.items():
        Image.open(src).convert("L").crop(box).save(os.path.join(HERE, name))
        print(f"{name} <- {src} {box}")


if __name__ == "__main__":
    main()
