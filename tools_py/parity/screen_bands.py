"""The letterbox-band test: is a captured frame gameplay, or the letterboxed intro cinematic?

SOCOM II's mission-intro cinematics (the dust-road opening, the "TO ABORT" flyover) draw into a
640x230-ish picture with black bars above and below; gameplay draws to the full 640x448 frame. So the
two bands the bars occupy -- rows 2-95 and 340-446 of the 640x448 frame -- are black through a
cinematic and lit in gameplay. Rows scale with the frame height, so a 320x224 fixture reads the same.

Shared by drive.py's `untilref(...,lit)` (HUD reached must mean gameplay), gate.py's mission scorer
(the hold captures must be gameplay) and sp_death_probe.screen_state (which applies its own level).

Why level 3 / 0.75 here (R30, 2026-09-13): measured on every mission capture s27..s41 + final of the gate
runs s3a, s3b3, s3d_2x_host, famb, mission4, native_on and s5_task4_dbuff, each frame checked by eye:
  pixels > 3 : gameplay >= 0.86 (dark spawn views included), letterboxed <= 0.57 (a camera cut), 0.00 on
               the dust-road cinematic -- a clean gap.
  pixels > 12 (sp_death_probe's level, BAND_MIN 0.5): dark gameplay reads 0.48-0.50 (mission4 s30-s36,
               native_on s30) and a letterboxed cut reads 0.57 (s5_task4_dbuff s35), so it misfires
               both ways on these frames.
What it does NOT tell apart: a full-frame screen that is not gameplay -- a death fade that stays above
level 3, the MISSION FAILURE statistics screen -- reads lit. It answers "not the letterbox", nothing more.
"""
import numpy as np

BAND_ROWS_448 = ((2, 95), (340, 446))   # in the 640x448 frame
GAMEPLAY_LEVEL = 3
GAMEPLAY_MIN = 0.75


def _gray(im):
    """PIL image or HxW / HxWx3 array -> HxW float32 grey (channel mean, as screen_state has always used)."""
    a = np.asarray(im.convert("RGB") if hasattr(im, "convert") else im).astype(np.float32)
    return a.mean(axis=2) if a.ndim == 3 else a


def band_fraction(im, level):
    """min over the two letterbox bands of the fraction of pixels above `level`."""
    g = _gray(im)
    h = g.shape[0]
    fracs = []
    for r0, r1 in BAND_ROWS_448:
        y0, y1 = int(round(r0 * h / 448.0)), max(int(round(r1 * h / 448.0)), int(round(r0 * h / 448.0)) + 1)
        fracs.append(float((g[y0:y1] > level).mean()))
    return min(fracs)


def gameplay_band(im):
    """(gameplay, fraction): gameplay when both letterbox bands are lit (GAMEPLAY_LEVEL / GAMEPLAY_MIN)."""
    frac = band_fraction(im, GAMEPLAY_LEVEL)
    return frac >= GAMEPLAY_MIN, frac
