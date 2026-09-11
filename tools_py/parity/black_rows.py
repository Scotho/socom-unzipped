#!/usr/bin/env python
"""Report the brightest pixel in a row band of every black-screen capture of a run directory (default rows
396..447 of the 448-row frame, the band that must stay black on the transition to the briefing;
STATUS 2026-09-09 12:10). Frames are the 640x448 (or scaled) PNGs written by drive.py: both its
per-step `s*.png` captures and the `w*.png` it takes during its settle waits.

Usage: python tools_py/parity/black_rows.py logs/parity/runs/<run> [--rows 396 448] [--max 8]
                                            [--from-step N]
Exit code 1 when any capture has a pixel brighter than --max in the band.

--from-step N examines only captures whose step index (the NN of `sNN_*` / `wNN_*`, which is
drive.py's position in the step script) is >= N. Without it every black-screen frame of the run
counts, and a boot sequence contributes ten or more of those before the run has pressed a button
in anger -- so a count taken over the whole run says nothing about the screen the run was aimed
at. See tools_py/parity/gate.py score_transition.
"""
import argparse
import glob
import os
import re
import sys

from PIL import Image

STEP_RE = re.compile(r"^[sw](\d+)_")


def step_index(name):
    """drive.py's step index for a capture file name (`s09_burst_003.png` -> 9, `w10_001.png` ->
    10). Anything that does not carry one sorts before every step, so a --from-step filter drops
    it: `final.png` and `manifest.json` are not step captures."""
    m = STEP_RE.match(name)
    return int(m.group(1)) if m else -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--rows", type=int, nargs=2, default=(396, 448))
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--from-step", type=int, default=None, dest="from_step",
                    help="only examine captures whose sNN_/wNN_ step index is >= N")
    a = ap.parse_args()
    bad = 0
    # Both capture families drive.py writes: `s*.png` (the settled screen of each step, plus its
    # burst frames) and `w*.png` (one frame per second of every settle wait). The fade into the
    # briefing does not settle, so it lives almost entirely in the w frames.
    caps = glob.glob(os.path.join(a.run, "s*.png")) + glob.glob(os.path.join(a.run, "w*.png"))
    for path in sorted(caps):
        if a.from_step is not None and step_index(os.path.basename(path)) < a.from_step:
            continue
        im = Image.open(path).convert("RGB")
        w, h = im.size
        y0 = a.rows[0] * h // 448
        y1 = a.rows[1] * h // 448
        top = im.crop((0, 0, w, y0))
        topPeak = max(max(px) for px in top.getdata())
        if topPeak > a.max:
            continue  # not a black-screen frame: the band may legitimately hold content
        band = im.crop((0, y0, w, y1))
        peak = max(max(px) for px in band.getdata())
        flag = "" if peak <= a.max else "  <-- NOT BLACK"
        if flag:
            bad += 1
        print(f"{os.path.basename(path):16s} black screen, rows {y0}-{y1}: peak {peak:3d}{flag}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
