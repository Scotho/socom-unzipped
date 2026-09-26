#!/usr/bin/env python
"""Reduce a run log's [gif-submit] lines (PS2X_GIF_TRACE) to the events that matter for the
title labels, in guest submission order: the set[11] flush chain (first BITBLTBUF dbp 0x2fcc,
holds the LOAD GAME / NEW GAME / ONLINE label images), the 512x256 background uploads
(dbp 0x2bc0 overlaps the label pages, 0x33d9 does not) and every TEX0 bind of a label texture.

Run: python -m tools_py.gif_submit_timeline logs/run_X.log [--from N] [--count M]
"""
import argparse
import re

RE = re.compile(r"\[gif-submit\] path(\d) bytes=(\d+)")
RE_BLT = re.compile(r"bitblt dbp=([0-9a-f]+) dbw=(\d+) trx=(\d+)x(\d+)")
RE_TEX = re.compile(r"tex0 tbp0=([0-9a-f]+) tbw=(\d+) psm=([0-9a-f]+) (\d+)x(\d+)")
LABELS = {0x3207, 0x3247, 0x3287, 0x3107, 0x3147, 0x3187, 0x31c7, 0x32c7, 0x3307, 0x3347, 0x3387}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--from", dest="start", type=int, default=0, help="skip this many matching events")
    ap.add_argument("--count", type=int, default=120)
    a = ap.parse_args()
    n = 0
    shown = 0
    for line in open(a.log, errors="replace"):
        if not line.startswith("[gif-submit]"):
            continue
        m = RE.search(line)
        if not m:
            continue
        path, size = m.groups()
        mb = RE_BLT.search(line)
        mt = RE_TEX.search(line)
        dbp, dbw, w, h = mb.groups() if mb else (None, None, None, None)
        tbp0, tbw, psm, tw, th = mt.groups() if mt else (None, None, None, None, None)
        ev = None
        if dbp is not None:
            d = int(dbp, 16)
            if d == 0x2fcc and int(size) > 100000:
                ev = f"P{path} SET11-FLUSH {int(size)//1024} KB (labels re-uploaded)"
            elif w == "512" and h == "256":
                ev = f"P{path} BG-UPLOAD 512x256 -> dbp={dbp}{' (OVERLAPS LABELS)' if d == 0x2bc0 else ''}"
            elif d in LABELS:
                ev = f"P{path} upload dbp={dbp} {w}x{h}"
        if tbp0 is not None and int(tbp0, 16) in LABELS:
            ev = (ev + "; " if ev else f"P{path} ") + f"BIND label tbp0={tbp0} {tw}x{th} (draw follows)"
        elif tbp0 is not None and int(tbp0, 16) in (0x2bc0, 0x33d9):
            ev = (ev + "; " if ev else f"P{path} ") + f"BIND BG tbp0={tbp0} {tw}x{th} (draw follows)"
        if ev is None:
            continue
        n += 1
        if n <= a.start:
            continue
        print(ev)
        shown += 1
        if shown >= a.count:
            break


if __name__ == "__main__":
    main()
