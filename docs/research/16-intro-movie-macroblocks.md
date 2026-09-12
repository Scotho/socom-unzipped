# 16 — Intro-movie black macroblocks: the decode is clean, the shadow→GPU mirror drops blocks

Sprint 3, Task 10. Bounded spike on the user report of 2026-09-10 18:45 (black 16×16-ish
rectangles at the edges of the intro movie and of the title screen's movie background, flickering
per frame). The brief named two suspects: dropped/undecoded MPEG macroblocks in the IPU/PSS decode
path, or the 16×16-block upload into GS memory.

**Verdict: it is neither the MPEG decode nor the 16×16 GS *transfer*. Every decoded picture is
byte-for-black-block identical to a clean offline libavcodec decode of the same stream, and every
uploaded block reaches the render thread's shadow VRAM. The blocks are lost on the last hop —
the shadow-VRAM → GL-render-target mirror (`refreshRenderTargetsFromShadow` /
`refreshDirtyRows` in `gs_gl_backend.cpp`), which fails to `glTexSubImage2D` a small number of
individual 16×16 blocks per second, leaving whatever the GL texture already held (black).**
No fix landed: the fix belongs in `gs_gl_backend.cpp`, which Sprint 3's render-target-scale task
is rewriting, and the exact mechanism inside that mirror is not pinned to a single line yet.

## 0. The trap: the intro movie is genuinely full of black macroblocks

`RUN/MOVIES/INTRO_2.PSS` is 640×448, MPEG-2 Main, 29.97 fps, 3836 pictures. It opens on a fade
from black, carries a baked-in 16-pixel letterbox on the top and bottom macroblock rows, and has
long dark stretches. A detector that simply flags "this 16×16 block is pure black" fires on
hundreds of blocks per frame of legitimate content, and — because the boot flow is
reproducible — fires on **the same coordinates in run after run**, which reads exactly like a
deterministic bug. It is not one. Three of the four frames that looked like a smoking gun across
eleven stored gate runs (`w00_017` with (400,400)+(400,416), `w00_018` with eight blocks,
`w00_019` with three) are pixel-identical to the reference decode.

**Always diff against a reference decode of the same picture, never against "is it black".**

## 1. Method (all of it re-runnable, most of it without the game)

1. Decode the movie offline with the same decoder the runtime uses:
   `ffmpeg -v error -i game/disc/RUN/MOVIES/INTRO_2.PSS -map 0:v:0 -pix_fmt rgb24 -f rawvideo -`.
   It decodes all 3836 pictures with **zero** stderr output — no concealment, no errors. Keep two
   things per picture: an 80×56 luma thumbnail (for matching) and the 40×28 "block is pure black"
   mask (for diffing).
2. For each of our captures, find the reference picture with the smallest mean absolute
   thumbnail difference, then diff the two black-block masks. `extraBlack` = black in ours and
   not in the reference = a real dropped block. Clean frames match at **dist = 0.00**, i.e. our
   presented frame is identical to the offline decode of that picture; affected frames sit at
   0.03–0.20, and all of that difference is the dropped blocks.
3. Frames come from three sources, all 640×448 and 1:1 with the GS frame:
   - `logs/parity/gate/*/title/w00_*.png` — the 1 Hz captures the title gate's `untilref` step
     takes while the boot's intro movie plays (eleven stored runs, Sprint 2 and Sprint 3 builds);
   - `logs/parity/runs/mb10_ours/s1[456]_burst_*.png` — 0.2 s bursts on the attract intro movie,
     this task's run;
   - `PS2X_GS_DUMP_DISPLAY` triples (`gpu` = the GL render target, `shadow` = the render thread's
     VRAM, `cpu` = the game-thread VRAM), `logs/parity/mb10_dispdump`.
4. A temporary probe in `MPEG.cpp` (`PS2X_MPEG_DUMP_FRAME`, **removed before this commit**) ran the
   same black-block census over `frame.rgba` — the libavcodec output, before the strip write to
   guest RAM — so the decoder's own output could be compared with the offline decode.

## 2. The bug reproduces, at 4-5% of movie frames, 1-4 blocks each

| corpus | movie frames | frames with dropped blocks | dropped blocks |
|---|---|---|---|
| eleven stored gate title runs, boot intro (`w00_*`) | 296 | 11 (3.7%) | 55 |
| this task's run, attract intro, 0.2 s burst | 311 | 14 (4.5%) | 44 |
| this task's run, boot intro (`w00_*`) | 19 | 2 | 3 |

Blocks per affected frame: 1–4, with one outlier of 11. The blocks sit on the 16-pixel grid, are
pure `000000`, and their positions vary run to run — **the loss is not content-driven**. Over the
larger burst corpus they are spread across all 40 macroblock columns; the "frame edges" of the
user report is a real but partial impression (columns 38–39 took 33 of the first corpus's 55
blocks, but only 2 of the burst corpus's 44).

Named examples from this task's run (`logs/parity/runs/mb10_ours`):

- `w00_004.png` ↔ INTRO_2 picture **91**, block **(416, 192)**.
- `w00_008.png` ↔ picture **216**, blocks **(480, 80)** and **(480, 112)**.

## 3. The decode is clean — 2067 consecutive pictures, exactly

The `PS2X_MPEG_DUMP_FRAME` census logged the fully-black-macroblock set of every picture
`writeDecodedFrameToGuest` received. The attract playback of INTRO_2 gave 2067 consecutive
decoded pictures (HLE frames 4645–6711). Aligned against the offline reference (offset 109):

```
frames 4645..6711 (2067) -> ref offset 109, mean |count diff| = 0.000
  frames whose decoded black-block COUNT differs from the reference: 0
```

Zero. Over the very seconds during which the screen captures show 44 dropped blocks on 14 frames,
the decoder handed the runtime a complete picture every single time. `writeDecodedFrameToGuest`
then writes **every** pixel of **every** macroblock column of the aligned frame unconditionally
(there is no skip path in it), so the guest strip buffer is complete too.

**The IPU/PSS/MPEG decode path is cleared.** `MPEG.cpp` is not where this lives.

## 4. The GS transfer is clean, the GL mirror is not — three named divergences

`PS2X_GS_DUMP_DISPLAY` writes the displayed buffer three ways at each sampled present. 48 of the
sampled presents were of INTRO_2 pictures:

| layer | what it is | presents with dropped blocks |
|---|---|---|
| `shadow` | render-thread VRAM, written by `m_shadow->UploadImage` | **0 / 48** |
| `gpu` | the GL render target, what is blitted to the window | **3 / 48** |
| `cpu` | game-thread VRAM, written by `m_cpu->UploadImage` | 14 / 48 |

The three `gpu` divergences, with the blocks the GL texture is missing **and the shadow has**:

| dump | display buffer | INTRO_2 picture | blocks black on the GPU only |
|---|---|---|---|
| `display_195s_fbp000` | fbp 0x000 | 965 | (48, 48), (48, 80), (192, 416) |
| `display_199s_fbp000` | fbp 0x000 | 1085 | (432, 368), (272, 400) |
| `display_211s_fbp000` | fbp 0x000 | 1447 | (384, 144), (384, 160) |

`(384, 144)` and `(384, 160)` are vertically adjacent, i.e. **consecutive transfers** in the
game's upload order (`FUN_0030b770` loops DSAY inner, DSAX outer — research/09), which is what a
dropped run of transfers looks like rather than a dropped region of the picture.

So: the decoded picture is complete, the guest strip buffer is complete, the GS transfer reaches
shadow VRAM complete, and the GL texture that gets presented is missing individual 16×16 blocks.
**The divergence is in the shadow→GPU mirror.**

The dumps and the window captures are independent instruments and do not share a picture — the
dump fires every 2 s, the burst captures every 0.2 s (every sixth picture), and no burst frame
landed on pictures 965, 1085 or 1447. They agree on rate, which is the corroboration that they are
watching the same thing: 3 of 48 sampled presents (6.3%) against 14 of 311 captured frames (4.5%),
and 1–3 blocks per affected dump against 1–4 per affected capture. The code path ties them
together — the dump is taken inside `executePresent` after `refreshDirtyRows` and before the
present blit, off the same texture the blit reads, so the `gpu` layer *is* what the window shows.

## 5. Where in that mirror (candidates, in order of fit)

The mirror is three functions in `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp`:

- `executeUpload` — writes `m_shadow`, then calls `refreshRenderTargetsFromShadow` **only when**
  `m_uploadExpectedBytes != 0 && m_uploadReceivedBytes >= m_uploadExpectedBytes`;
- `refreshRenderTargetsFromShadow` — records an exact `DirtyRect` for a transfer in the target's
  own layout, or falls back to the 32-row band mask;
- `refreshDirtyRows` — `glTexSubImage2D`s those rects and bands out of the shadow into `rt.color`.

1. **The upload-completion accumulator in `executeUpload` (best fit).** A 16×16 PSMCT32 block is
   1024 bytes; the refresh fires only on the call that pushes `m_uploadReceivedBytes` to that
   total, and `executeTransfer` resets the counter for the next block. Any transfer whose image
   data does not close out before the next `executeTransfer` — a short or split delivery, a
   wrapping/overrunning packet taking the arbiter's copying path — silently never marks its block
   dirty, while `m_shadow->UploadImage` has already taken the bytes. That is the only path found
   that loses **one** block and leaves the shadow intact, which is exactly the measured signature.
2. **`refreshRenderTargetsFromShadow`'s `if (rowFirst >= rowLast) continue;`** sits *after* the
   `dirtyRects.push_back`. A transfer that takes that branch has pushed its rect but may leave
   `rt.dirtyRows` false; `refreshDirtyRows` returns immediately on `!dirtyRows`, so the rect waits
   for the next mark — one frame late at best. A weaker fit (it defers rather than loses) but it
   is a genuine ordering bug in the same function.
3. **The 4096-rect cap is ruled out.** On overflow `exact` stays false and the `if (!exact)` band
   mask is set over the same rows, and `refreshDirtyRows` re-reads the whole 32-row band from the
   shadow — so an overflowing block still lands. The cap costs precision, not pixels.

**Corroboration from the `cpu` layer.** `downloadRenderTargetToCpu` writes the GL target back into
the game-thread VRAM, skipping only rows that still have pending dirty marks. A block that was
never marked (candidate 1) is *not* skipped, so the GPU's black pixels are written over the
uploaded data in the CPU VRAM and stay there. That is why the `cpu` layer shows dropped blocks
about five times as often as a single sampled present does (14/48 vs 3/48): it accumulates the
GPU's transient holes. Those CPU-VRAM holes do not themselves reach the screen — that layer feeds
texture reads and readbacks, not the present — but they say the GPU target has holes considerably
more often than the present-time sample suggests.

## 6. Console reference

A PCSX2 run was driven over the same boot (`logs/parity/runs/mb10_pcsx2`, and the burst script in
the scratchpad). It did **not** capture the intro movie playing: with the shared script's presses
the PCSX2 boot ran past it, and the 337 burst frames sit on a static screen (best reference match
distance ~22, constant mean luma). A second attempt with a press-free burst was blocked on the
build/run lock and is not done. This is a gap in the write-up, but not in the argument: the
offline libavcodec decode of INTRO_2.PSS *is* the console-correct content of every picture, and it
is a stricter reference than a PCSX2 capture — it says exactly what the dropped blocks should have
contained, and our own frames match it at dist 0.00 everywhere else.

## 7. Why no fix landed

The brief's rule was one hypothesis, one build, one green title gate — otherwise write the note and
stop. Both remaining candidates live in `gs_gl_backend.cpp`, the file Sprint 3's render-target
scale task is actively rewriting, and candidate 1 needs the GIF/arbiter delivery of image data
traced before a change to the accumulator can be called correct rather than plausible. Neither is
one bounded step today. The note names the stage, the pictures and the blocks; the fix is a
follow-up that should be sequenced after the render-target-scale work settles.

Next step for whoever picks it up: count, per movie frame, `executeTransfer` calls with
`rrw == rrh == 16` against `refreshRenderTargetsFromShadow` calls from `executeUpload`. If the
second is smaller, candidate 1 is proven and the fix is to mark the rect from `executeTransfer`
(or on the transfer's completion regardless of how its bytes arrived) rather than from the byte
accumulator.

**That count was taken in Sprint 4 task 1 — see section 9. It came out 12 205 741 against
12 201 993, so the second is indeed smaller, but candidate 1's mechanism is disproved (zero
partially delivered rectangles) and the real cause is a data race on `m_currentTransfer`.
Sections 5 and 7 are kept as written for the record; section 9 supersedes them.**

## 8. Tooling

Throwaway scripts live in the session scratchpad; the recipe is the part worth keeping:

- reference build: `ffmpeg … -f rawvideo -` piped into a script that stores, per picture, an 80×56
  luma thumbnail and the 40×28 pure-black block mask;
- capture diff: nearest thumbnail match, then `mask_ours & ~mask_ref` — report the block
  coordinates, never the absolute black count;
- `PS2X_GS_DUMP_DISPLAY=<dir>:<t0>:<t1>` triples split GS-transfer failures (`shadow`) from
  mirror failures (`gpu`) in one shot — the dump is taken after `refreshDirtyRows` and before the
  present blit, so its `gpu` layer is exactly what the window shows;
- the `MPEG.cpp` census probe was temporary and is not in the tree.

## 9. Sprint 4, task 1 — the count, and what it found: a data race on `m_currentTransfer`

Section 7's next step was carried out. The count says candidate 1 is **half right and wrong about
the mechanism**: refreshes really are fewer than 16×16 transfers, but not one of the missing ones
is a "rectangle whose bytes have not all arrived". The loss is a cross-thread race on
`GSGlBackend::m_currentTransfer`.

### 9.1 The check: `tools_py/parity/movie_blocks.py`

Written before any runtime change, and it is the permanent form of section 8's recipe:

```
python -m tools_py.parity.movie_blocks <dumpdir> [--ref game/disc/RUN/MOVIES/INTRO_2.PSS]
```

Per `PS2X_GS_DUMP_DISPLAY` present, it reports `mask_gpu & ~mask_shadow` over 16×16 blocks —
black on the GL target, not black in shadow VRAM — prints the coordinates, never an absolute black
count, and exits 1 on any hit. It needs no reference decode: section 3 proved the decode clean and
section 4 measured 0/48 dropped blocks in the shadow, so **the shadow layer is the reference for
the mirror stage**. `--ref` only labels each present with its INTRO_2 picture number.

A drawn screen legitimately disagrees with the shadow, so presents have to be classified — and the
obvious classifier is a trap. Splitting on "how much of the frame is byte-identical" is **not
monotonic**: dropping blocks lowers it, so a 5% drop fails the run while a 50% drop falls under the
bar and is silently demoted. The check would then pass hardest exactly when the bug is worst. Three
rules avoid it:

- `content` — blocks non-black in the **shadow**; below 10% the shadow holds no picture and there
  is nothing to find. Skipped.
- `visible` — blocks non-black in the **gpu** layer; below 5% the target shows essentially nothing
  and is indistinguishable from a 100% drop. Skipped **loudly**, and counted in the summary.
- `agree` — of the shadow's non-black blocks, the fraction whose gpu block is *either*
  byte-identical *or* pure black. A dropped block counts as agreeing, so the number does not move
  as drops accumulate. ≥ 0.95 is a movie present: every block checked, counted, decides the exit
  code. Below that the present is **demoted** — the title menu's movie background under drawn
  panels sits at ~0.57 — and is checked only where it is *locally* mirrored, a block counting when
  most of its 8 neighbours are byte-identical.

**Every present prints a line, always**, demoted ones included, and every differing block on a
demoted present that is not *furniture* is a finding that fails the run.

Furniture is learned from the capture, not guessed from the frame. A demoted present is part mirror
and part GPU-drawn, and **within one present the two cannot be separated**: the menu's drawn
graphic is one large centred blob of differing blocks enclosed by mirrored background on every
side, geometrically identical to a contiguous patch of dropped blocks. Two local rules were tried
and both failed the same way — clustered bad blocks disqualify each other, so a contiguous patch
scored far *below* the same number scattered, which is backwards, because real macroblock drops are
contiguous runs. On identical fixtures the neighbour-agreement rule scored 100 injected blocks at
16.5% scattered against 1.5% contiguous, and 300 blocks at 47.3% against 1.5%.

What does separate them is time. Drawn furniture sits at the same coordinates present after
present; a mirror miss wanders — which is what §2 measured independently (positions vary run to run,
not content-driven). The capture says the same thing very sharply: over its 59 demoted presents the
per-coordinate recurrence is bimodal, **116 coordinates differ in exactly one present and 2 in two
presents, then nothing until 25, 51, 52, 55, 57, 58, 59**. So a block that differs in at least a
tenth of the demoted presents (6 of 59, sitting in a gap that runs from 2 to 25 — any threshold in
3..25 gives the same answer) is furniture; everything else is a finding. The decision is per block
and uses no neighbours, so the verdict does not depend on how the bad blocks are arranged: the same
injections now score 15.6% / 15.6% and 47.0% / 47.0% scattered against contiguous.

The cost, stated: corruption that recurs at the same coordinates across most of a capture is
absorbed as furniture by construction, and a capture with fewer than 3 demoted presents has no
furniture map at all and reports every differing block.

**A run with no counted present exits 2, not 0.** "Zero missing blocks out of nothing" is not a
pass, and a capture that never reached the movie is the most likely way to produce one.

Validation. Against Sprint 3's stored capture it reproduces section 4 exactly —

```
$ python -m tools_py.parity.movie_blocks logs/parity/mb10_dispdump
display_040s_fbp000  SKIP (GL target shows nothing: 0% of blocks non-black against the shadow's 89%)
display_048s_fbp000  demoted agree=0.568 visible=100% measurable=635  FAIL MISSING 2: (480, 288)
                     (480, 320)
display_195s_fbp000  movie agree=1.000 visible=93%  MISSING 3: (48, 48) (48, 80) (192, 416)
display_199s_fbp000  movie agree=1.000 visible=93%  MISSING 2: (432, 368) (272, 400)
display_211s_fbp000  movie agree=1.000 visible=90%  MISSING 2: (384, 144) (384, 160)
presents=108 tested=45 demoted=59 skipped=4 (dark=3 blank=1)
furniture blocks=485 of 1120 (learned from 59 demoted presents; 635 measurable)
demoted findings blocks=120 pictures=5 (black=35 stale=85)
STALE blocks=0
MISSING blocks=7 pictures=3        (exit 1)
```

— the same three presents, the same seven blocks, and no counted hit anywhere else (all 108
presents print; the excerpt drops the `ok` lines). 485 of the 1120 blocks are learned as the menu's
drawn furniture, leaving 635 measurable, and the 120 findings left on demoted presents are the
one-off differences in the title menu's movie background — the second half of the user's report.
`display_040s` is the whole-frame case the `visible` rule exists for: the GL target entirely black
against a shadow holding 89% content, which no per-block statement can describe.

And against synthetic mutations of one clean movie present (`display_193s_fbp000`), which is how
the monotonicity and the vacuous-pass hole were pinned down:

| mutation | result | exit |
|---|---|---|
| none | `tested=1 MISSING blocks=0` | 0 |
| 5% of blocks blacked out | `agree=1.000 visible=88% MISSING blocks=50` | 1 |
| 50% blacked out | `agree=1.000 visible=46% MISSING blocks=523` | 1 |
| 90% blacked out | `agree=1.000 visible=9% MISSING blocks=941` | 1 |
| both layers all black | `tested=0 … NOT A PASS` | 2 |
| 10% left holding the previous picture (stale, not black) | `demoted findings blocks=113` | 1 |
| one clean present + one 50% stale-corrupted | `demoted findings blocks=544`, `tested=1` | 1 |
| 100 blocks injected into 1 of 20 real menu presents, **scattered** | `99/635` findings | 1 |
| the same 100 blocks, **contiguous** | `99/636` findings | 1 |
| 300 blocks, scattered / contiguous | `299/636` / `299/636` | 1 |

The three drop rows are the point: 50 → 523 → 941, all still counted. Rows 5–7 are the false passes
earlier drafts produced — exit 0 on an all-black capture with a non-zero `tested=`; exit 0 on a
50–90% drop demoted out of the counted tier; exit 0 on a mixed capture whose corrupted present was
demoted and never printed at all. The last three rows are the arrangement test: with the old
neighbour rule those same fixtures scored 16.5% scattered against 1.5% contiguous, and 47.3%
against 1.5% — a contiguous patch, which is the shape the real defect takes, hid by being a patch.

### 9.2 The count

A temporary `PS2X_GS_COUNT_MB` counter (removed before the commit) over a full `title_menu.txt`
run on the pre-fix binary, 2026-09-12:

| quantity | count |
|---|---|
| `executeTransfer` calls with `trxreg.rrw == trxreg.rrh == 16` | **12 205 741** |
| `refreshRenderTargetsFromShadow` calls from `executeUpload` for such a transfer | **12 201 993** |
| deficit | **3 748** (0.03%) |
| 16×16 transfers whose bytes reached shadow VRAM with no refresh | **0** |
| 16×16 transfers that received no image data at all | **0** |
| 16×16 transfers that received a byte count other than their expected 1024 | **0** |

The deficit is real, so by section 7's rule candidate 1 "passes" — but its **mechanism is
disproved**: there is never a partially delivered rectangle. Every 16×16 transfer that received
bytes received exactly 1024 of them and the completion branch fired. The fix section 7 proposed
(refresh the previous rectangle when bytes are outstanding) would have been a no-op.

### 9.3 What the deficit actually is

`executeUpload` decides *which* rectangle to mark by reading `m_currentTransfer`. That member was
written in two places:

- `GSGlBackend::executeTransfer` — render thread, immediately before the upload it belongs to;
- `GSGlBackend::BeginTransfer` — **game thread**, which queues commands and runs ahead of the
  render thread.

So the game thread could overwrite the member between the render thread's `executeTransfer` and
its `executeUpload`, and the upload then marked a rectangle belonging to some *later* transfer.

That the window is open is what the deficit shows on its own, and it is the claim that survives
without any instrumentation: **3 748 refreshes went missing with zero partial deliveries to
explain them, and after the fix the deficit is 0.** A block can only lose its refresh here by
`executeUpload` reading a transfer that is not the one whose bytes it just took.

A second temporary counter sized the exposure while the fix was in flight. It kept the value the
game thread had last written and compared it, at every upload, with the transfer the render thread
had actually begun:

```
[gs-mb] frame=669 t16=1187 r16=1187 missed16=0 drop16=0 race=1272 race16=1187 tAll=1273
```

**1187 of 1187** on a movie frame, and **12 240 952 of 12 241 344 (100.0%)** over the run.
Read it for what it is, and no more:

- it is an **in-flight** measurement. The harness was removed before the commit (correctly — it is
  instrumentation, not product), so the exact definition of `race` cannot be reconstructed from
  the tree, only from this note;
- it counts **exposure, not proven stale reads**. It says the game thread had already advanced past
  the transfer being uploaded, which over-counts: a game-thread write that lands *before* the
  render thread's `executeTransfer` is harmless, because `executeTransfer` then overwrites it with
  the right value. What it establishes is that the window was open essentially always, not that
  every upload read through it.

The deficit of 3 748 is the part that is visible without any of that: `r16` counts a refresh only
when the *read-back* transfer is also 16×16, so those 0.03% are the reads where the stale value
happened to be a differently shaped transfer. A stale read that lands on another 16×16 transfer is
invisible to that counter and marks a wrong rectangle just the same.

`refreshRenderTargetsFromShadow` derives its exact `dirtyRects` entry from the transfer it is
passed, so a stale value does two things at once: it pushes some *other* block's rectangle, and the
real block's rectangle is never pushed at all.

Why the screen was mostly right anyway: the wrong rectangle was almost always another block of the
same movie frame, so the union of the marked rectangles still covered nearly the whole picture.
The blocks that fall out are the ones at the trailing edge of the lag window — the last blocks
uploaded before the present, at the end of the DSAX-outer loop. That is why section 2 found
columns 38–39 taking 33 of 55 dropped blocks, and why the Sprint 4 before-capture's nine blocks
all sit at x = 528/544/560.

Everything else section 4 measured follows: the shadow is untouched by the race (`GSCpuBackend`
keeps its own `m_transfer` under its own mutex, so `UploadImage` always writes the right address),
positions vary run to run because thread scheduling does, and vertically adjacent losses are
consecutive transfers in one scheduling window.

### 9.4 The fix

One line, in `GSGlBackend::BeginTransfer`: the game-thread write is deleted. Nothing on the game
thread reads `m_currentTransfer`, so no second member is needed; the header now says the member is
render-thread-only and why. `m_uploadExpectedBytes` and `m_uploadReceivedBytes` were already
touched only on the render thread.

### 9.5 Before and after, same script, same 16×16 upload path

| | before (HEAD of `sprint-4`) | after |
|---|---|---|
| `movie_blocks.py` on a `title_menu.txt` capture | `MISSING blocks=9 pictures=1` (present `display_198s_fbp000`, INTRO_2 picture 1640 at distance 0.00, blocks (528,320) (528,352) (544,352) (544,368) (560,368) (544,384) (544,400) (528,416) (544,416)) | `MISSING blocks=0 pictures=0` over 61 movie presents (and `note blocks=0` on the menu background, which had 6 before) |
| 16×16 transfers vs refreshes | 12 205 741 vs 12 201 993, deficit 3 748 | 12 241 344 vs 12 241 344, deficit 0 |

### 9.6 Two incidental findings

- `scripts/parity/title_only.txt` no longer reaches the title screen: its blind `CROSS` presses
  answer YES to the controller-configuration "save this configuration?" prompt and the run parks on
  the "Select MEMORY CARD slot" dialog for the rest of its 420 s. `scripts/parity/title_menu.txt`
  (`untilref`) clears it. Captures for this note were taken with the latter.
- The attract intro movie starts about 110 s after the main menu settles, so a capture needs the
  game alive for ~160 s past the menu — `drive.py --tail` keeps it there after the script ends.
