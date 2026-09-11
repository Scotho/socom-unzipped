#!/usr/bin/env python
"""Report the brightest pixel in a row band of every black-screen capture of a run directory (default rows
396..447 of the 448-row frame, the band that must stay black on the transition to the briefing;
STATUS 2026-09-09 12:10). Frames are the 640x448 (or scaled) PNGs written by drive.py: both its
per-step `s*.png` captures and the `w*.png` it takes during its settle waits.

Usage: python tools_py/parity/black_rows.py logs/parity/runs/<run> [--rows 396 448] [--max 8]
Exit code 1 when any capture has a pixel brighter than --max in the band.
"""
import argparse
import glob
import os
import sys

from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--rows", type=int, nargs=2, default=(396, 448))
    ap.add_argument("--max", type=int, default=8)
    a = ap.parse_args()
    bad = 0
    # Both capture families drive.py writes: `s*.png` (the settled screen of each step, plus its
    # burst frames) and `w*.png` (one frame per second of every settle wait). The fade into the
    # briefing does not settle, so it lives almost entirely in the w frames.
    caps = glob.glob(os.path.join(a.run, "s*.png")) + glob.glob(os.path.join(a.run, "w*.png"))
    for path in sorted(caps):
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
