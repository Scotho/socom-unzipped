"""Does a mission capture show the MISSION FAILURE screen?

Sprint 6 Task 1a (owner-agreed 2026-09-14). The mission stage's hold captures passed the letterbox-band and
liveness tests on `s5_head_1x_b` while s38/s40 and final.png were the "MISSION FAILURE / MISSION STATISTICS FOR:
SEEDING CHAOS" screen (the turn teleport had walked the player out of the mission area). The band test only asks
whether the bands are lit, and the statistics screen lights them.

The screen's title "MISSION FAILURE" is dim yellow text (grey ~60-97 on a ~20 background) at the top left. The
reference `scripts/parity/refs/mission_failure_banner.png` is that title cut from the s5_head_1x_b final frame
(rows 12..48, cols 10..230 of the 640x448 capture). It is binarised at BANNER_LEVEL and matched by mean XOR
distance at every start row in ROW_RANGE, so a capture shifted by a few rows (a resized window, a letterbox) still
matches. Measured 2026-09-15: the fixture itself 0.000; the spawn gameplay view 0.362; a black frame equals the
template density, 0.286; so the threshold is a wide margin on either side.
"""
import os

import numpy as np
from PIL import Image

BANNER_REF = os.path.join("scripts", "parity", "refs", "mission_failure_banner.png")
BANNER_LEVEL = 55
BANNER_COLS = (10, 230)
ROW_RANGE = (0, 60)          # start rows searched; the banner sits at row 12 on a native capture
MAX_DIST = 0.10

_TEMPLATE = {}


def banner_template():
    if "t" not in _TEMPLATE:
        with Image.open(BANNER_REF) as im:
            _TEMPLATE["t"] = np.asarray(im.convert("L")) > BANNER_LEVEL
    return _TEMPLATE["t"]


def detect(image):
    """image: a path or a PIL image of the 640x448 capture -> (failed, reason)."""
    im = Image.open(image) if isinstance(image, (str, os.PathLike)) else image
    g = np.asarray(im.convert("L")).astype(np.float32)
    tpl = banner_template()
    h, w = tpl.shape
    x0, x1 = BANNER_COLS
    if g.shape[0] < ROW_RANGE[1] + h or g.shape[1] < x1:
        return False, f"frame {g.shape[1]}x{g.shape[0]} too small for the banner search"
    best_y, best = -1, 1.0
    for y in range(ROW_RANGE[0], ROW_RANGE[1]):
        d = float(np.abs((g[y:y + h, x0:x1] > BANNER_LEVEL) ^ tpl).mean())
        if d < best:
            best_y, best = y, d
    if best < MAX_DIST:
        return True, f"MISSION FAILURE banner at y={best_y}, dist={best:.3f}"
    return False, f"no failure banner (best dist={best:.3f} at y={best_y})"
