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
                     panels, agree ~0.57) or not a mirror at all. Part of such a present is a
                     mirror and part is GPU-drawn, and the two are separated by the FURNITURE MAP
                     (see furniture_map below): blocks that differ from the shadow in present after
                     present are drawn furniture, blocks that differ in one present are a mirror
                     miss. The map is learned PER SCREEN (see screen_groups). Every differing block
                     outside this present's screen map is a finding -- black or stale -- and
                     findings fail the run.

EVERY present prints a line, always, and every demoted present prints why it was demoted and what
was found on it. That is deliberate. Two rounds of review removed two ways this check could report
success by looking away: silence is the failure mode a regression test must not have. In
particular a present demoted through NON-black corruption used to be invisible -- the demoted path
only ever looked for black blocks -- so a capture of one clean present plus one 50%-corrupted
present printed nothing at all about the corruption and exited 0.

Why not a local rule, and why this one is temporal. Two earlier drafts tried to find the mirrored
part of a demoted present from the present itself -- the fraction of the frame that is identical,
then the fraction of each block's 8 neighbours that are identical. Both failed the same way, in the
shape that matters most: clustered bad blocks disqualify EACH OTHER, so a contiguous patch scored
far below the same number of blocks scattered, and real macroblock drops are contiguous runs. On
identical fixtures the neighbour gate reported 100 corrupted blocks as 90/544 = 16.5% when
scattered but 8/522 = 1.5% when contiguous, and 300 blocks as 47.3% scattered against 1.5%
contiguous -- an 11x and a 32x hole in the direction of the real bug. The furniture map reports
15.6% / 15.6% and 47.0% / 47.0% on the same four fixtures.

A single present cannot do better, and the data says why: in `logs/parity/mb10_dispdump` the title
menu's drawn graphic is ONE large centred blob of differing blocks enclosed by mirrored background
on every side -- geometrically identical to a contiguous patch of dropped blocks. Nothing about a
frozen frame separates them. What separates them is time.

A run that produces NO counted present exits non-zero. "Zero missing blocks out of nothing" is not
a pass, and a capture that never reached the movie is the most likely way to produce one.

    python -m tools_py.parity.movie_blocks logs/mb_s4
    python -m tools_py.parity.movie_blocks logs/mb_s4 --ref game/disc/RUN/MOVIES/INTRO_2.PSS

Prints one line per present and a final `MISSING blocks=<n> pictures=<n>`. `--ref` is optional and
changes no verdict: it decodes the named movie (or reads a directory of frames) and labels each
present with the nearest reference picture, so a report can be cross-referenced with research/16's
picture numbering (965, 1085, 1447).

Exit codes: 0 clean, 1 anything found (missing or stale, on a counted or a demoted present), 2
nothing measurable (no counted present and nothing found, or no dumps at all).

Known limits, with the bar that actually applies rather than a comfortable paraphrase.

* THE ABSORPTION BAR IS LOW, and it is not "most of the capture". A block becomes furniture at
  `max(--furniture-min, ceil(--furniture-frac x presents of THAT SCREEN))` -- with the defaults,
  **3 presents, or 35% of the screen's presents, whichever is larger**. Corruption that repeats at
  the same coordinates that many times is absorbed, by construction, and the run can then pass.
  Measured on a healed 23-present fixture (20 demoted presents of one screen, bar = 7), the same
  100-block patch dropped in k of them:

      k =  0 -> 0 findings, exit 0        k = 3 -> 294 findings, exit 1
      k =  1 -> 98 findings, exit 1       k = 5 -> 490 findings, exit 1
      k =  2 -> 196 findings, exit 1      k = 10 -> 0 findings, EXIT 0  <-- absorbed

  Two things make that visible rather than silent. The per-screen line prints how many furniture
  blocks sit within one present of the bar, which is what corruption that only just cleared it
  looks like; and `--furniture-baseline` compares the learned map with a saved one and fails on any
  block that is furniture now and was not then. On the k=10 case above the map grows 484 -> 582 and
  the baseline check turns exit 0 into exit 1. A map that grows run over run is the signature.
* The map needs --furniture-min presents OF THE SAME SCREEN before it can tell furniture from a
  miss. Below that it is empty and EVERY differing block on that present is reported, which fails
  loudly rather than quietly -- the right way round, but noisy on a short capture.
* `agree` treats a block that differs without being black as disagreement, so heavy NON-black
  corruption demotes a present out of the counted tier. It is still measured block-for-block there,
  just against the screen's furniture map instead of the full frame.

The trade behind all of this: research/16 section 2 measured that this defect's dropped positions
vary run to run and are not content-driven, and the capture agrees -- 116 of the 118 transient
coordinates appear in exactly one present. Corruption that repeats identically is a different
defect from the one this tool was built to catch, and the baseline check is how you would notice
it.

Measured. 5/50/90% black drops give MISSING 50/523/941, all exit 1; an all-black pair exits 2; a
10% stale-content present exits 1; a mixed capture of one clean plus one 50% stale-corrupted
present exits 1 with the corrupted present printed. 100 and 300 corrupted blocks injected into one
of 20 real menu presents give 99 and 299 findings whether scattered or contiguous -- the
arrangement does not matter. The stored capture still reports exactly research/16 section 4's three
presents and seven blocks, and with the per-screen map its odd screen out, the fade
`display_163s_fbp08c`, now reports all 267 of its differing blocks instead of the 114 a single
global map left after masking 153 of them with the title menu's furniture.
"""
import argparse
import glob
import io
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


def screen_groups(diff_masks, similar):
    """Group demoted presents by which SCREEN they are, using their own difference masks.

    A furniture map learned from one screen must not be applied to another: on
    `logs/parity/mb10_dispdump` a single global map, learned mostly from 58 title-menu presents,
    masked 153 of the 267 differing blocks of `display_163s_fbp08c` -- the fade into the attract
    movie, a different screen that happens to share a display buffer with the menu. Keying on the
    buffer (the `fbpNNN` in the file name) does not fix it, because that is where the screen was
    drawn, not which screen it is.

    What identifies the screen is the difference mask itself: which blocks the GPU draws over. The
    separation is not marginal. Jaccard similarity of every demoted mask in that capture against a
    typical menu present: 58 of them score 0.99-1.00 and the fade scores 0.25, with nothing in
    between -- any threshold in (0.25, 0.99) gives the same grouping.

    Single-pass greedy grouping against each group's first mask; returns a list of index lists.
    """
    groups = []
    for i, m in enumerate(diff_masks):
        for g in groups:
            a, b = diff_masks[g[0]], m
            union = int((a | b).sum())
            if union == 0 or (a & b).sum() / union >= similar:
                g.append(i)
                break
        else:
            groups.append([i])
    return groups


def furniture_map(diff_masks, min_presents, frac):
    """Blocks the GPU draws over on this screen, learned from the capture instead of guessed.

    A demoted present is part mirror and part GPU-drawn, and WITHIN ONE PRESENT the two are not
    separable: `logs/parity/mb10_dispdump`'s menu graphic is a single large centred blob of blocks
    that differ from the shadow, enclosed by mirrored background on every side -- geometrically
    indistinguishable from a contiguous patch of dropped blocks. No local rule can tell them apart,
    and the one this tool used to use (a block counts only if most of its 8 neighbours are
    byte-identical) was actively harmful: clustered bad blocks disqualify each other, so a
    contiguous patch scored LOWER than the same number of blocks scattered.

    What does separate them is that they behave differently over time. Drawn furniture is at the
    same coordinates in present after present; a mirror miss wanders (research/16 section 2: the
    dropped positions vary run to run and are not content-driven). Measured on that capture: 484
    blocks differ in more than half of the 62 demoted presents, and with those excluded the median
    present has ZERO findings left.

    So a block is furniture when it differs in at least `frac` of this screen's demoted presents,
    and never in fewer than `min_presents` of them. The decision is per block and uses no
    neighbours at all, which is what makes the result independent of how the bad blocks are
    arranged.

    The threshold is not delicate, and that is the point of measuring it. On
    `logs/parity/mb10_dispdump` the per-coordinate recurrence over the menu screen's presents is
    sharply bimodal: 116 coordinates differ in exactly ONE present and 2 in two presents, then
    nothing at all until 25, 51, 52, 55, 57, 58 and 59. Anything between 3 and 25 gives the same
    answer. The transient cluster is the mirror misses, which is what research/16 section 2
    independently says they do: their positions vary run to run and are not content-driven.

    Needs `min_presents` presents OF THIS SCREEN to say anything. Below that there is no evidence
    either way and the map is empty, so every differing block is reported -- conservative on
    purpose.

    Returns (map, support, need). `support` is the per-block count of presents it differed in, so
    callers can see how close each furniture block sat to the bar.
    """
    shape = diff_masks[0].shape
    if len(diff_masks) < min_presents:
        return np.zeros(shape, dtype=bool), np.zeros(shape, dtype=int), 0
    support = np.stack(diff_masks).sum(axis=0)
    need = max(min_presents, int(np.ceil(frac * len(diff_masks))))
    return support >= need, support, need


def read_mask(path):
    rows = [ln.rstrip("\n") for ln in io.open(path, encoding="utf-8") if ln.strip()]
    return np.array([[ch == "#" for ch in r] for r in rows], dtype=bool)


def write_mask(path, mask):
    with io.open(path, "w", encoding="utf-8") as f:
        for r in mask:
            f.write("".join("#" if v else "." for v in r) + "\n")


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
    ap.add_argument("--furniture-frac", type=float, default=0.35,
                    help="a block that differs from the shadow in at least this fraction of the "
                         "demoted presents (never fewer than --furniture-min of them) is GPU-drawn "
                         "furniture, not a mirror miss (default 0.35). The measured gap it sits "
                         "in runs from 2 of 59 presents to 25 of 59, i.e. 0.034..0.42; 0.35 is as "
                         "high inside that gap as the evidence allows, which is what sets how many "
                         "repeats of the same corruption get absorbed")
    ap.add_argument("--screen-frac", type=float, default=0.5,
                    help="Jaccard similarity of two presents' difference masks at or above which "
                         "they are the same screen and share a furniture map (default 0.5; the "
                         "measured gap runs from 0.25 to 0.99, so the value is not delicate)")
    ap.add_argument("--write-furniture", metavar="PATH",
                    help="write the learned furniture map (union over screens) as a 28x40 mask")
    ap.add_argument("--furniture-baseline", metavar="PATH",
                    help="compare the learned furniture map against this saved one; any block that "
                         "is furniture now and was not then is reported and fails the run. A map "
                         "that grows run over run is what corruption being learned as furniture "
                         "looks like")
    ap.add_argument("--furniture-min", type=int, default=3,
                    help="demoted presents needed before furniture can be told from a miss at all; "
                         "below this every differing block is reported (default 3)")
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

    # Pass 1: classify every present and keep its block masks (1120 bools each, nothing large).
    seen = []
    for name, gpu_path, shadow_path in items:
        gpu, shadow = read_ppm(gpu_path), read_ppm(shadow_path)
        if gpu.shape != shadow.shape:
            seen.append(dict(name=name, kind="badsize",
                             text="SKIP layers differ in size %s vs %s" % (gpu.shape, shadow.shape)))
            continue
        same = identical_mask(gpu, shadow)
        gpu_black, shadow_black = black_mask(gpu), black_mask(shadow)
        content = float((~shadow_black).mean())
        visible = float((~gpu_black).mean())
        label = ""
        if ref is not None:
            dist = np.abs(ref - thumb(shadow)).mean(axis=(1, 2))
            label = " picture=%d(d%.2f)" % (int(np.argmin(dist)), float(dist.min()))
        rec = dict(name=name, label=label, same=same, gpu_black=gpu_black,
                   shadow_black=shadow_black, content=content, visible=visible)
        if content < args.min_content:
            rec["kind"] = "dark"
        elif visible < args.min_visible:
            rec["kind"] = "blank"
        else:
            interesting = ~shadow_black
            rec["agree"] = float((same | gpu_black)[interesting].mean())
            rec["kind"] = "movie" if rec["agree"] >= args.mirror_frac else "demoted"
        seen.append(rec)

    # Furniture is learned PER SCREEN. One global map applied to every demoted present under-reports
    # on a capture's minority screens: on logs/parity/mb10_dispdump a global map, learned mostly
    # from 58 title-menu presents, masked 153 of the 267 differing blocks of display_163s_fbp08c
    # (the fade into the attract movie -- a different screen sharing a display buffer with the
    # menu, so keying on fbp does not help either).
    demoted_idx = [i for i, r in enumerate(seen) if r.get("kind") == "demoted"]
    demoted_diffs = [~seen[i]["same"] for i in demoted_idx]
    blank_map = np.zeros((HEIGHT // BLOCK, WIDTH // BLOCK), dtype=bool)
    groups = screen_groups(demoted_diffs, args.screen_frac) if demoted_diffs else []
    group_info = []
    for gi, g in enumerate(groups):
        fmap, support, need = furniture_map([demoted_diffs[j] for j in g],
                                            args.furniture_min, args.furniture_frac)
        marginal = int(((support >= need) & (support <= need + 1)).sum()) if need else 0
        group_info.append(dict(size=len(g), fmap=fmap, need=need, marginal=marginal,
                               names=[seen[demoted_idx[j]]["name"] for j in g]))
        for j in g:
            seen[demoted_idx[j]]["fmap"] = fmap
            seen[demoted_idx[j]]["group"] = gi
    union = blank_map.copy()
    for gi in group_info:
        union |= gi["fmap"]

    missing_blocks = missing_pictures = stale_blocks = tested = 0
    note_blocks = note_black = note_stale = note_pictures = 0
    demoted = blank = dark = 0

    for r in seen:
        kind = r.get("kind")
        if kind == "badsize":
            print("%s  %s" % (r["name"], r["text"]))
            continue
        name, label = r["name"], r["label"]
        if kind == "dark":
            dark += 1
            print("%s  skip%s (shadow holds no picture: %.0f%% of blocks non-black)"
                  % (name, label, 100 * r["content"]))
            continue
        if kind == "blank":
            # Indistinguishable from a 100% drop: say so loudly rather than count it either way.
            blank += 1
            print("%s  SKIP%s (GL target shows nothing: %.0f%% of blocks non-black against the "
                  "shadow's %.0f%% -- cleared/switched buffer or a whole-frame loss)"
                  % (name, label, 100 * r["visible"], 100 * r["content"]))
            continue
        same, gpu_black, shadow_black = r["same"], r["gpu_black"], r["shadow_black"]
        if kind == "movie":
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
                      % (name, r["agree"], 100 * r["visible"], label, "; ".join(parts)))
            else:
                print("%s  movie agree=%.3f visible=%.0f%%%s  ok"
                      % (name, r["agree"], 100 * r["visible"], label))
            continue

        # Demoted: part mirror, part drawn. Judge every differing block that is not furniture, one
        # block at a time and with no reference to its neighbours, so the verdict does not depend
        # on how the bad blocks happen to be arranged.
        demoted += 1
        fmap = r.get("fmap", blank_map)
        bad = ~same & ~fmap
        n_b, where_b = coords(bad & gpu_black & ~shadow_black)
        n_s, where_s = coords(bad & ~gpu_black & ~shadow_black)
        head = "%s  demoted agree=%.3f visible=%.0f%% screen=%s measurable=%d%s" % (
            name, r["agree"], 100 * r["visible"],
            ("#%d/%d" % (r.get("group", -1), group_info[r["group"]]["size"])
             if "group" in r else "?"),
            int((~fmap).sum()), label)
        if n_b or n_s:
            note_pictures += 1
            note_blocks += n_b + n_s
            note_black += n_b
            note_stale += n_s
            parts = []
            if n_b:
                parts.append("MISSING %d: %s" % (n_b, where_b))
            if n_s:
                parts.append("STALE %d: %s" % (n_s, where_s))
            print("%s  FAIL %s" % (head, "; ".join(parts)))
        else:
            print("%s  ok" % head)

    print("presents=%d tested=%d demoted=%d skipped=%d (dark=%d blank=%d)"
          % (len(items), tested, demoted, dark + blank, dark, blank))
    for gi, info in enumerate(group_info):
        print("screen #%d: %d presents, furniture=%d blocks (bar=%d presents, %d of them at the "
              "bar +/-1)%s" % (gi, info["size"], int(info["fmap"].sum()), info["need"],
                               info["marginal"],
                               "" if info["need"] else "  -- too few presents, nothing masked"))
    print("furniture blocks=%d of %d (union over %d screens)"
          % (int(union.sum()), union.size, len(group_info)))
    grown = 0
    if args.write_furniture:
        write_mask(args.write_furniture, union)
        print("furniture map written to %s" % args.write_furniture)
    if args.furniture_baseline:
        base = read_mask(args.furniture_baseline)
        if base.shape != union.shape:
            print("FURNITURE BASELINE shape %s != %s -- cannot compare" % (base.shape, union.shape))
            grown = 1
        else:
            new_blocks = union & ~base
            grown, where = coords(new_blocks)
            print("furniture vs baseline %s: %d blocks are furniture now and were not then%s"
                  % (args.furniture_baseline, grown, (": " + where) if grown else ""))
    print("demoted findings blocks=%d pictures=%d (black=%d stale=%d)"
          % (note_blocks, note_pictures, note_black, note_stale))
    print("STALE blocks=%d" % stale_blocks)
    print("MISSING blocks=%d pictures=%d" % (missing_blocks, missing_pictures))
    if missing_blocks or stale_blocks or note_blocks or grown:
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
