#!/usr/bin/env python
"""Find 16x16 movie blocks the GL render target is missing but shadow VRAM has.

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

Blocks that differ from the shadow WITHOUT being black are reported too, as `stale` -- a mirror
that kept the previous frame's pixels instead of black is the same failure with a different
leftover, and `gpu != shadow` is the stronger signal wherever the layers are supposed to agree.

HOW A PRESENT IS CLASSIFIED, and why it is done this way
--------------------------------------------------------
The test only means something where the GL target really is a mirror of the shadow. Where the GPU
draws -- the menu's text and panels, a briefing -- the shadow holds whatever was last uploaded to
those addresses and the target holds what was drawn; the two have no reason to agree. But a naive
"how much of the frame is byte-identical?" gate is NOT safe, because dropping blocks lowers it:
a 5% drop stays above the bar and fails the run, a 50% drop falls below it and is silently demoted,
so the check would pass hardest exactly when the bug is worst. Three rules avoid that:

* `content`  -- the fraction of blocks that are non-black in the SHADOW. Below --min-content the
  shadow holds no picture, so there is nothing this check could find. Skipped.
* `visible`  -- the fraction of blocks that are non-black in the GPU layer. Below --min-visible the
  target is showing essentially nothing (a cleared or freshly switched buffer, or a whole-frame
  loss) and is indistinguishable from a 100% drop; no per-block statement is possible. Skipped,
  and listed in the summary so it can never be mistaken for a pass.
* `agree`    -- of the blocks that are non-black in the shadow, the fraction whose GPU block is
  EITHER byte-identical OR pure black. Dropped blocks are counted as agreeing, so this number does
  not move when more blocks are dropped: 5%, 50% and 90% drops all keep agree = 1.00 and all land
  in the counted tier, reporting 5%, 50% and 90% of the blocks as missing. Drawn content is
  neither identical nor black, so a menu present sits near its mirrored fraction (~0.57) instead.

  >= --mirror-frac : a movie present. Every block is checked, and the result decides the exit code.
  below            : DEMOTED. Partly mirrored (the title menu's movie background under drawn
                     panels, agree ~0.57) or not a mirror at all. A demoted present cannot be
                     measured block-for-block, so it is checked only where it is locally mirrored:
                     a block counts when at least --neighbour-frac of its existing 8 neighbours are
                     byte-identical -- a local test that still tolerates a run of adjacent bad
                     blocks, since research/16's own (384,144)+(384,160) pair are each other's
                     neighbour. Anything found there -- black OR stale -- is printed as a `note`.
                     A demoted present FAILS the run when those notes are more than --note-frac of
                     its locally-mirrored region; below that they are printed and not fatal. That
                     density rule is not a fudge, it is the only thing that separates the two:
                     see below.

EVERY present prints a line, always, and every demoted present prints why it was demoted and what
was found on it. That is deliberate. Two rounds of review removed two ways this check could report
success by looking away: silence is the failure mode a regression test must not have. In
particular a present demoted through NON-black corruption used to be invisible -- the demoted path
only ever looked for black blocks -- so a capture of one clean present plus one 50%-corrupted
present printed nothing at all about the corruption and exited 0.

Why the density rule, and why a bare "any note fails" does not work. Real title-menu presents carry
11-12 stale notes each, and they are the SAME ELEVEN COORDINATES on every present of the capture --
(64,32) (560,32) (64,128) (560,128) (160,208) (464,208) (400,336) (160,400) (464,400) (160,416)
(464,416), symmetric x pairs: drawn menu decoration small enough to sit isolated inside the mirrored
background, which no local rule can tell from a mirror miss. They are 11 of ~619 locally-mirrored
blocks, 1.8%; the worst real present in that whole capture -- the fade into the attract movie --
reaches 5.2%. A 50% stale corruption is 202 of 439, 46%. Nothing separates them per block; the
density does. So isolated notes are printed and survive, and a present whose mirrored region is
more than --note-frac wrong fails. Be honest about what that buys: with the default 0.10 the bar
sits at roughly twice the worst real content, and the sensitivity floor for SCATTERED NON-BLACK
corruption is about a tenth of the mirrored region (a synthetic 10% stale present measures 10.1%
and does fail). Black drops have no such floor -- they stay in the counted tier and are reported
one block at a time, which is the flavour this defect produces.

A run that produces NO counted present exits non-zero. "Zero missing blocks out of nothing" is not
a pass, and a capture that never reached the movie is the most likely way to produce one.

    python -m tools_py.parity.movie_blocks logs/mb_s4
    python -m tools_py.parity.movie_blocks logs/mb_s4 --ref game/disc/RUN/MOVIES/INTRO_2.PSS

Prints one line per present and a final `MISSING blocks=<n> pictures=<n>`. `--ref` is optional and
changes no verdict: it decodes the named movie (or reads a directory of frames) and labels each
present with the nearest reference picture, so a report can be cross-referenced with research/16's
picture numbering (965, 1085, 1447).

Exit codes: 0 clean, 1 anything found (missing, stale, or a note on a demoted present), 2 nothing
measurable (no counted present and nothing found, or no dumps at all).

Known limit, stated precisely. `agree` treats a block that differs without being black as
disagreement, so heavy NON-black corruption demotes a present out of the counted tier: its blocks
are then judged by the neighbour rule instead of block-for-block, which under-reports when the
corruption is dense enough that bad blocks neighbour each other. It cannot pass silently -- the
present prints, the notes fail the run -- but the count is a floor, not a measurement. Black is the
leftover this defect actually produces (the GL texture starts cleared), which is why the counted
tier is built around it.

Measured, on mutations of one clean present: 5/50/90% black drops give MISSING 50/523/941, all
exit 1; an all-black pair exits 2; a 10% stale-content present exits 1 on its notes; and a mixed
capture of one clean present plus one 50% stale-corrupted present exits 1 with the corrupted
present printed (it exited 0, silently, before this was fixed). On the real Sprint 3 capture the
menu's 657 isolated stale notes stay non-fatal and the run still fails on its 7 genuinely missing
blocks -- the intended outcome in both directions.
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


def write_ppm(path, img):
    """Write an (h, w, 3) uint8 array as a binary P6 PPM (used by the tool's own tests)."""
    h, w = img.shape[:2]
    with open(path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h))
        f.write(np.ascontiguousarray(img, dtype=np.uint8).tobytes())


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


def coords(mask, limit=24):
    rows, cols = np.nonzero(mask)
    n = int(len(rows))
    shown = " ".join("(%d, %d)" % (c * BLOCK, r * BLOCK) for r, c in list(zip(rows, cols))[:limit])
    if n > limit:
        shown += " ... +%d more" % (n - limit)
    return n, shown


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dumpdir", help="directory written by PS2X_GS_DUMP_DISPLAY")
    ap.add_argument("--ref", help="optional: movie file or frame directory, to label presents only")
    ap.add_argument("--mirror-frac", type=float, default=0.95,
                    help="`agree` at or above which a present is a movie present: counted, and it "
                         "decides the exit code (default 0.95)")
    ap.add_argument("--partial-min", type=float, default=0.20,
                    help="`agree` at or above which a demoted present is called partly mirrored "
                         "rather than not a mirror at all; both are checked and printed either "
                         "way, this only labels the line (default 0.20)")
    ap.add_argument("--neighbour-frac", type=float, default=0.6,
                    help="on a demoted present, the fraction of a block's existing 8 neighbours "
                         "that must be byte-identical for the block to be checked (default 0.6)")
    ap.add_argument("--note-frac", type=float, default=0.10,
                    help="a demoted present fails the run when its notes are more than this "
                         "fraction of its locally-mirrored region; isolated notes below it are "
                         "printed and not fatal (default 0.10 -- a real menu present sits at "
                         "0.018, a 50%% stale corruption at 0.46)")
    ap.add_argument("--min-content", type=float, default=0.10,
                    help="fraction of blocks that must be non-black in the SHADOW for the present "
                         "to hold a picture worth checking (default 0.10)")
    ap.add_argument("--min-visible", type=float, default=0.05,
                    help="fraction of blocks that must be non-black in the GPU layer; below it the "
                         "target shows essentially nothing and no per-block statement is possible "
                         "(default 0.05)")
    args = ap.parse_args(argv)

    items = pairs(args.dumpdir)
    if not items:
        print("no display_*_{gpu,shadow}.ppm pairs in %s" % args.dumpdir)
        print("MISSING blocks=0 pictures=0   (NOT A PASS: nothing to measure)")
        return 2

    ref = load_reference(args.ref) if args.ref else None
    missing_blocks = missing_pictures = stale_blocks = tested = 0
    note_blocks = note_black = note_stale = note_pictures = 0
    fail_blocks = fail_pictures = 0
    demoted = blank = dark = 0

    for name, gpu_path, shadow_path in items:
        gpu, shadow = read_ppm(gpu_path), read_ppm(shadow_path)
        if gpu.shape != shadow.shape:
            print("%s  SKIP layers differ in size %s vs %s" % (name, gpu.shape, shadow.shape))
            continue
        same = identical_mask(gpu, shadow)
        gpu_black, shadow_black = black_mask(gpu), black_mask(shadow)
        content = float((~shadow_black).mean())
        visible = float((~gpu_black).mean())
        label = ""
        if ref is not None:
            dist = np.abs(ref - thumb(shadow)).mean(axis=(1, 2))
            label = " picture=%d(d%.2f)" % (int(np.argmin(dist)), float(dist.min()))

        if content < args.min_content:
            dark += 1
            print("%s  skip%s (shadow holds no picture: %.0f%% of blocks non-black)"
                  % (name, label, 100 * content))
            continue
        if visible < args.min_visible:
            # Indistinguishable from a 100% drop: say so loudly rather than count it either way.
            blank += 1
            print("%s  SKIP%s (GL target shows nothing: %.0f%% of blocks non-black against the "
                  "shadow's %.0f%% -- cleared/switched buffer or a whole-frame loss)"
                  % (name, label, 100 * visible, 100 * content))
            continue

        # `agree` over the shadow's non-black blocks; a dropped block counts as agreeing, so more
        # drops never demote a present out of the counted tier (see the module docstring).
        interesting = ~shadow_black
        agree = float((same | gpu_black)[interesting].mean())

        if agree >= args.mirror_frac:
            tested += 1
            lost = gpu_black & ~shadow_black
            stale = ~same & ~gpu_black & ~shadow_black
            n_lost, where = coords(lost)
            n_stale, where_stale = coords(stale)
            if n_lost or n_stale:
                missing_pictures += 1
                missing_blocks += n_lost
                stale_blocks += n_stale
                parts = []
                if n_lost:
                    parts.append("MISSING %d: %s" % (n_lost, where))
                if n_stale:
                    parts.append("STALE %d: %s" % (n_stale, where_stale))
                print("%s  movie agree=%.3f visible=%.0f%%%s  %s"
                      % (name, agree, 100 * visible, label, "; ".join(parts)))
            else:
                print("%s  movie agree=%.3f visible=%.0f%%%s  ok" % (name, agree, 100 * visible, label))
            continue

        # Demoted: not measurable block-for-block, so check where it is LOCALLY mirrored -- and say
        # so on every one of them, black or stale. A demoted present that printed nothing is the
        # hole review round 2 found: a 50% non-black corruption landed here and vanished.
        demoted += 1
        kind = "partial" if agree >= args.partial_min else "not-a-mirror"
        testable = neighbour_identical_frac(same) >= args.neighbour_frac
        n_b, where_b = coords(testable & gpu_black & ~shadow_black)
        n_s, where_s = coords(testable & ~same & ~gpu_black & ~shadow_black)
        head = "%s  %s agree=%.3f visible=%.0f%% locally-mirrored=%d%s" % (
            name, kind, agree, 100 * visible, int(testable.sum()), label)
        if n_b or n_s:
            note_pictures += 1
            note_blocks += n_b + n_s
            note_black += n_b
            note_stale += n_s
            density = (n_b + n_s) / max(1, int(testable.sum()))
            parts = []
            if n_b:
                parts.append("note-MISSING %d: %s" % (n_b, where_b))
            if n_s:
                parts.append("note-STALE %d: %s" % (n_s, where_s))
            verdict = "FAIL" if density > args.note_frac else "note"
            if verdict == "FAIL":
                fail_pictures += 1
                fail_blocks += n_b + n_s
            print("%s  %s(%.1f%% of the mirrored region)  %s"
                  % (head, verdict + " " if verdict == "FAIL" else "", 100 * density,
                     "; ".join(parts)))
        else:
            print("%s  ok" % head)

    print("presents=%d tested=%d demoted=%d skipped=%d (dark=%d blank=%d)"
          % (len(items), tested, demoted, dark + blank, dark, blank))
    print("note blocks=%d pictures=%d (black=%d stale=%d)  -- on demoted presents; a floor, not a "
          "measurement" % (note_blocks, note_pictures, note_black, note_stale))
    print("DEMOTED-FAIL blocks=%d pictures=%d  (notes denser than %.0f%% of the mirrored region)"
          % (fail_blocks, fail_pictures, 100 * args.note_frac))
    print("STALE blocks=%d" % stale_blocks)
    print("MISSING blocks=%d pictures=%d" % (missing_blocks, missing_pictures))
    if missing_blocks or stale_blocks or fail_blocks:
        if tested == 0:
            print("NOTE: nothing qualified as a movie present either -- %d dark, %d blank, %d demoted"
                  % (dark, blank, demoted))
        return 1
    if tested == 0:
        print("NOT A PASS: no present qualified as a movie present, so nothing was measured "
              "(%d dark, %d blank, %d demoted)" % (dark, blank, demoted))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
