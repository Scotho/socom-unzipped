#!/usr/bin/env python
"""Find 16x16 movie blocks that are black on the GPU but not black in shadow VRAM.

This is the check for the intro-movie macroblock defect (docs/research/16). The runtime's
`PS2X_GS_DUMP_DISPLAY=<dir>:<t0>:<t1>` writes the displayed buffer three ways at each sampled
present -- `gpu` (the GL render target, read back after `refreshDirtyRows` and before the present
blit, so it is exactly what the window shows), `shadow` (the render thread's VRAM, written by
`m_shadow->UploadImage`) and `cpu` (the game-thread VRAM). A movie picture is uploaded into the
display buffer as 16x16 blocks, so on a movie present the shadow holds the whole picture and the
GL target is supposed to be a mirror of it. The test is one line:

    missing = (gpu block is pure black) AND NOT (shadow block is pure black)

which is strictly stronger than research/16's ffmpeg recipe:

* it needs no reference decode -- research/16 section 3 proved the MPEG decode clean over 2067
  consecutive pictures and section 4 measured 0/48 dropped blocks in the shadow layer, so the
  shadow layer *is* the reference for the mirror stage;
* it never reports an absolute black count. INTRO_2.PSS is genuinely full of black macroblocks
  (a baked-in 16-pixel letterbox, a fade from black, long dark stretches) and the boot is
  reproducible, so an absolute "is this block black" detector fires on the same coordinates run
  after run and reads exactly like a deterministic bug. It is not one; that trap cost the Sprint 3
  spike a false positive (research/16 section 0). Only the differential is sound.

The test only means something where the GL target really is a mirror of the shadow. Where the GPU
draws -- the menu's text and panels, a briefing -- the shadow holds whatever was last uploaded to
those addresses and the target holds what was drawn; the two have no reason to agree, and
`gpu black & shadow not black` there says nothing about the mirror. So presents are sorted by how
much of the frame the two layers agree on, byte for byte, per 16x16 block:

* >= --mirror-frac (default 0.90): a movie present -- the attract intro movie fills the screen, and
  on a clean one *every* block is identical (research/16 section 2: clean frames match the offline
  decode at dist 0.00). Tested, counted, and it decides the exit code.
* >= --advisory-min (default 0.20): partly mirrored -- the title menu's movie background covers
  about 57% of the frame with drawn panels over the rest. Here a block is looked at only when at
  least --neighbour-frac of its existing 8 neighbours are byte-identical (a local mirror test that
  still tolerates a run of adjacent dropped blocks -- research/16's own (384,144)+(384,160) pair are
  each other's neighbour). Reported as `note`, NOT counted and NOT part of the exit code: these
  presents also carry legitimate layer differences, so a hit here is a lead, not a measurement.
* below that: the target mirrors nothing (a cleared or freshly switched buffer). Skipped.

    python -m tools_py.parity.movie_blocks logs/mb_s4
    python -m tools_py.parity.movie_blocks logs/mb_s4 --ref game/disc/RUN/MOVIES/INTRO_2.PSS

Prints one line per picture and a final `MISSING blocks=<n> pictures=<n>`; exits 1 when any tested
block is black on the GPU and not black in the shadow. `--ref` is optional and changes no verdict:
it decodes the named movie (or reads a directory of frames) and labels each present with the
nearest reference picture, so a report can be cross-referenced with research/16's picture numbering
(965, 1085, 1447).

Validated against Sprint 3's stored capture: `movie_blocks.py logs/parity/mb10_dispdump` reports
exactly the three divergences research/16 section 4 names, with exactly their block coordinates,
and nothing on the other 105 presents.
"""
import argparse
import glob
import os
import re
import subprocess
import sys

import numpy as np

BLOCK = 16
WIDTH, HEIGHT = 640, 448
NAME_RE = re.compile(r"^display_(\d+)s_fbp([0-9a-f]+)_gpu\.ppm$")


def read_ppm(path):
    """Read a binary P6 PPM into an (h, w, 3) uint8 array (the runtime writes maxval 255)."""
    with open(path, "rb") as f:
        data = f.read()
    fields, pos = [], 0
    while len(fields) < 4:
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            while pos < len(data) and data[pos:pos + 1] != b"\n":
                pos += 1
            continue
        start = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        fields.append(data[start:pos])
    if fields[0] != b"P6":
        raise ValueError("%s: not a binary PPM (%r)" % (path, fields[0]))
    w, h, maxval = int(fields[1]), int(fields[2]), int(fields[3])
    if maxval != 255:
        raise ValueError("%s: maxval %d unsupported" % (path, maxval))
    pos += 1   # exactly one whitespace byte separates the header from the raster
    px = np.frombuffer(data, dtype=np.uint8, count=w * h * 3, offset=pos)
    return px.reshape(h, w, 3)


def blocks(img):
    """(rows, cols, 16, 16, 3) view of the whole 16x16 blocks of an image."""
    h, w = img.shape[0] // BLOCK * BLOCK, img.shape[1] // BLOCK * BLOCK
    return img[:h, :w].reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK, 3).transpose(0, 2, 1, 3, 4)


def black_mask(img):
    """(rows, cols) bool: the block is pure black -- every one of its 768 bytes is 0."""
    return ~blocks(img).any(axis=(2, 3, 4))


def identical_mask(a, b):
    """(rows, cols) bool: the block is byte-identical in both layers."""
    return (blocks(a) == blocks(b)).all(axis=(2, 3, 4))


def neighbour_identical_frac(same):
    """Per block, the fraction of its existing 8 neighbours that are byte-identical."""
    h, w = same.shape
    pad = np.pad(same.astype(np.float32), 1)
    ones = np.pad(np.ones((h, w), dtype=np.float32), 1)
    hits = np.zeros((h, w), dtype=np.float32)
    count = np.zeros((h, w), dtype=np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            hits += pad[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
            count += ones[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
    return hits / np.maximum(count, 1.0)


def thumb(img):
    """80x56 luma thumbnail (8x8 means) -- the picture matcher of research/16 section 8."""
    h, w = img.shape[0] // 8 * 8, img.shape[1] // 8 * 8
    luma = img[:h, :w].astype(np.float32).mean(axis=2)
    return luma.reshape(h // 8, 8, w // 8, 8).mean(axis=(1, 3))


def load_reference(ref):
    """Thumbnails of every reference picture, from a movie file (ffmpeg) or a directory of PPMs."""
    if os.path.isdir(ref):
        paths = sorted(glob.glob(os.path.join(ref, "*.ppm")))
        if not paths:
            raise SystemExit("--ref %s holds no .ppm frames" % ref)
        return np.stack([thumb(read_ppm(p)) for p in paths])
    cmd = ["ffmpeg", "-v", "error", "-i", ref, "-map", "0:v:0", "-pix_fmt", "rgb24",
           "-f", "rawvideo", "-"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise SystemExit("ffmpeg failed on %s: %s" % (ref, proc.stderr.decode(errors="replace")[:400]))
    frame = WIDTH * HEIGHT * 3
    count = len(proc.stdout) // frame
    if count == 0:
        raise SystemExit("--ref %s decoded no %dx%d frames" % (ref, WIDTH, HEIGHT))
    raw = np.frombuffer(proc.stdout, dtype=np.uint8, count=count * frame).reshape(count, HEIGHT, WIDTH, 3)
    return np.stack([thumb(raw[i]) for i in range(count)])


def pairs(dumpdir):
    """(name, gpu_path, shadow_path) for every dumped present that has both layers, in order."""
    out = []
    for path in sorted(glob.glob(os.path.join(dumpdir, "display_*_gpu.ppm"))):
        if not NAME_RE.match(os.path.basename(path)):
            continue
        shadow = path[:-len("_gpu.ppm")] + "_shadow.ppm"
        if os.path.exists(shadow):
            out.append((os.path.basename(path)[:-len("_gpu.ppm")], path, shadow))
    return out


def coords(lost):
    rows, cols = np.nonzero(lost)
    return int(len(rows)), " ".join("(%d, %d)" % (c * BLOCK, r * BLOCK) for r, c in zip(rows, cols))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dumpdir", help="directory written by PS2X_GS_DUMP_DISPLAY")
    ap.add_argument("--ref", help="optional: movie file or frame directory, to label pictures only")
    ap.add_argument("--mirror-frac", type=float, default=0.90,
                    help="fraction of blocks that must be byte-identical for a present to be a "
                         "movie present, i.e. tested and counted (default 0.90)")
    ap.add_argument("--advisory-min", type=float, default=0.20,
                    help="below --mirror-frac and at or above this, a present is reported but not "
                         "counted; below it the target mirrors nothing and is skipped (default 0.20)")
    ap.add_argument("--neighbour-frac", type=float, default=0.6,
                    help="on an advisory present, the fraction of a block's existing 8 neighbours "
                         "that must be byte-identical for it to be looked at (default 0.6)")
    ap.add_argument("--verbose", action="store_true", help="also print the skipped presents")
    args = ap.parse_args(argv)

    items = pairs(args.dumpdir)
    if not items:
        print("no display_*_{gpu,shadow}.ppm pairs in %s" % args.dumpdir)
        return 2

    ref = load_reference(args.ref) if args.ref else None
    missing_blocks = missing_pictures = tested = 0
    note_blocks = note_pictures = advisory = 0

    for name, gpu_path, shadow_path in items:
        gpu, shadow = read_ppm(gpu_path), read_ppm(shadow_path)
        if gpu.shape != shadow.shape:
            print("%s  SKIP layers differ in size %s vs %s" % (name, gpu.shape, shadow.shape))
            continue
        same = identical_mask(gpu, shadow)
        frac = float(same.mean())
        if frac < args.advisory_min:
            if args.verbose:
                print("%s  skip (mirrors nothing, %.1f%% of blocks identical)" % (name, 100 * frac))
            continue
        label = ""
        if ref is not None:
            dist = np.abs(ref - thumb(shadow)).mean(axis=(1, 2))
            label = " picture=%d(d%.2f)" % (int(np.argmin(dist)), float(dist.min()))
        lost = black_mask(gpu) & ~black_mask(shadow)
        if frac >= args.mirror_frac:
            tested += 1
            n, where = coords(lost)
            if n:
                missing_pictures += 1
                missing_blocks += n
                print("%s  movie %.1f%%%s  MISSING %d: %s" % (name, 100 * frac, label, n, where))
            else:
                print("%s  movie %.1f%%%s  ok" % (name, 100 * frac, label))
            continue
        advisory += 1
        n, where = coords(lost & (neighbour_identical_frac(same) >= args.neighbour_frac))
        if n:
            note_pictures += 1
            note_blocks += n
            print("%s  partial %.1f%%%s  note %d (not counted): %s" % (name, 100 * frac, label, n, where))
        elif args.verbose:
            print("%s  partial %.1f%%%s  ok" % (name, 100 * frac, label))

    print("presents=%d tested=%d advisory=%d" % (len(items), tested, advisory))
    print("note blocks=%d pictures=%d  (partly-mirrored presents, not counted)"
          % (note_blocks, note_pictures))
    print("MISSING blocks=%d pictures=%d" % (missing_blocks, missing_pictures))
    return 1 if missing_blocks else 0


if __name__ == "__main__":
    sys.exit(main())
