"""Console-vs-ours comparison at a fixed gameplay moment: the Seeding Chaos spawn view (Sprint 6 Task 1b,
owner-agreed 2026-09-14).

The parity gate compares our runs only with our own earlier runs, so a defect present in every run -- the grey water
shards, in every gameplay frame since Sprint 3 -- scores as perfect agreement (KNOWN §4). This module scores the mission
stage's s28 capture against the PCSX2 slot-8 screenshot (`scripts/parity/refs/console_spawn_slot8.png`).

Two kinds of number:

* `score(ours, console)`: the masked whole-frame mean |diff| after the same content crop and 640x448 resize. Reported
  for the trend only. Measured 2026-09-15: ours vs console 44-46, dominated by our scene being globally darker
  (terrain 5-9 vs 33-ish, research/26 §6 / research/20 §4.3); ours vs ours 3-10 on clean frames. A brightness-normalised
  variant did not separate the two (0.41-0.43 vs 0.17-0.44), so no verdict is taken from a whole-frame number.
* `water_verdict(ours)`: PASS/FAIL from two statistics of the water footprint (WATER_BOX) that separate the console from
  every one of our runs by a wide margin: the fraction of pixels whose 7x7 local std is <= 1.2 ("flat": the shards are
  flat grey polygons, research/26 §1) and the fraction below grey 12 ("dark": the black holes).
      console 0.188 / 0.084;  ours (4 runs) 0.498-0.597 / 0.293-0.306.
  Floors WATER_FLAT_MAX = 0.35 and WATER_DARK_MAX = 0.20 sit between. What they do not separate: a different camera
  (the box is the spawn view's stream), a colour-only defect (flat brown water would pass), and the global darkness
  (which raises `dark` on its own -- a fix that only brightens the scene could pass `dark` while the shards remain,
  which is why `flat` is required too).
"""
import os

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

from tools_py.parity.drive import crop_to_content

CONSOLE_REF = os.path.join("scripts", "parity", "refs", "console_spawn_slot8.png")
SIZE = (640, 448)
WATER_BOX = (190, 340, 120, 520)      # rows y0..y1, cols x0..x1 of the stream in the spawn view
FLAT_STD = 1.2
DARK_LEVEL = 12
WATER_FLAT_MAX = 0.35
WATER_DARK_MAX = 0.20


def _grey(image):
    im = Image.open(image) if isinstance(image, (str, os.PathLike)) else image
    im = crop_to_content(im.convert("RGB")).resize(SIZE)
    return np.asarray(im.convert("L")).astype(np.float32)


def default_mask():
    """True where the whole-frame score applies: not the HUD band, the objective text box or the compass."""
    m = np.ones((SIZE[1], SIZE[0]), dtype=bool)
    m[340:448, :] = False          # HUD: weapon, ammo, squad plates
    m[50:100, 200:440] = False     # "CURRENT OBJECTIVE:" typed text
    m[0:120, 500:640] = False      # compass and rank stars
    return m


def score(ours, console=CONSOLE_REF, mask=None):
    a, b = _grey(ours), _grey(console)
    m = default_mask() if mask is None else mask
    return float(np.abs(a - b)[m].mean())


def water_stats(image):
    g = _grey(image)
    y0, y1, x0, x1 = WATER_BOX
    w = g[y0:y1, x0:x1]
    k = 7
    win = sliding_window_view(np.pad(w, k // 2, mode="edge"), (k, k))
    sd = win.std(axis=(-1, -2))
    return {"flat": float((sd <= FLAT_STD).mean()), "dark": float((w < DARK_LEVEL).mean()), "mean": float(w.mean())}


def water_verdict(image):
    st = water_stats(image)
    ok = st["flat"] <= WATER_FLAT_MAX and st["dark"] <= WATER_DARK_MAX
    detail = (f"water flat={st['flat']:.3f} (max {WATER_FLAT_MAX}) dark={st['dark']:.3f} (max {WATER_DARK_MAX}) "
              f"mean={st['mean']:.1f}")
    return ok, detail


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    ours = argv[0]
    console = argv[1] if len(argv) > 1 else CONSOLE_REF
    ok, detail = water_verdict(ours)
    print(f"{ours}: whole-frame score={score(ours, console):.2f} vs {console}; {'PASS' if ok else 'FAIL'} {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
