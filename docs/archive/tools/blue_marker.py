# ARCHIVED 2026-09-25 (Sprint 13 Task H4, harness audit H27) -- was tools_py/parity/blue_marker.py.
#   Sprint 9 Q0b's reader of tools_py/parity/frame_burst.py bursts: is the first mission's blue enemy-marker
#   arrow ever on screen. It last mattered on 2026-09-20, when the owner closed Q0b ("it was there": the arrow
#   shows on ours once a player approaches the first enemies; docs/KNOWN.md section 3). Nothing called it and no
#   document named it. frame_burst.py stays, as an entry point. Nothing here is an instruction.
"""Sprint 9 Q0b: find the frames of a burst in which a saturated BLUE marker appears -- the arrow that flies over the
first mission's opening on the console to point at the first enemies, which the owner does not recall on ours.

    python -m tools_py.parity.blue_marker <burst_dir> [--min-pixels 40] [--show 12]

Per frame: the count of pixels that are strongly blue (B high, B well above R and G) inside the game image
(the 640x448 client, or whatever the capture is). Prints the frames whose count rises well above the burst's median
-- a HUD arrow is a few hundred saturated pixels that are not there a second earlier -- and the totals. Reference-
free and crude on purpose: the question is "is there ever a blue thing", and the two bursts are read side by side.
"""
import os
import statistics
import sys

import numpy as np
from PIL import Image


def blue_pixels(path):
    im = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    # Two blues: a saturated pure blue, and the HUD's own teal (the compass at the top right of the gameplay frame
    # is 234 pixels of it and nothing of the first -- calibrated on the PCSX2 reference's s29). A static HUD element
    # sits in the median; the marker is what rises above it.
    pure = (b > 140) & (b - r > 70) & (b - g > 40)
    teal = (b > 110) & (g > 90) & (r < 100) & (b - r > 40)
    return int((pure | teal).sum())


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[2]); return 2
    d = argv[1]
    min_pixels = int(argv[argv.index("--min-pixels") + 1]) if "--min-pixels" in argv else 40
    show = int(argv[argv.index("--show") + 1]) if "--show" in argv else 12
    frames = sorted(f for f in os.listdir(d) if f.endswith(".png"))
    counts = [(f, blue_pixels(os.path.join(d, f))) for f in frames]
    if not counts:
        print("no frames in", d); return 1
    med = statistics.median(c for _, c in counts)
    spikes = [(f, c) for f, c in counts if c >= max(min_pixels, 3 * med + min_pixels)]
    print(f"{d}: {len(counts)} frames, median blue pixels {med:.0f}, {len(spikes)} frames with a blue marker-sized spike")
    for f, c in spikes[:show]:
        print(f"  {f}  blue={c}")
    if len(spikes) > show:
        print(f"  ... and {len(spikes) - show} more")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
