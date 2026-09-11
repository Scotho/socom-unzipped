# Sprint 3 — render-target scale, the fourth VU1 command family, intro-movie macroblocks: design

Status: scope approved by the user on 2026-09-11 ("proceed"). Project: SOCOM Unzipped,
repo `github.com/Scotho/socom-unzipped`, branch `develop` (= `main` = 148dffa at sprint start).
Executor: a separate Opus-class model following `docs/superpowers/plans/2026-09-11-sprint-3-render-scale-and-fourth-family.md`
with superpowers:subagent-driven-development.

## 1. Where Sprint 2 left things

- Native VU1 dispatcher (`src/lib/vu/native/socom2_dispatch_0x1b50.cpp`): families A, B, C native,
  123/166 recorded dispatcher runs bit-exact (`--regs all`). Residual: one list using command
  `0x34` (needs EFU maths: ERLENG/WAITP/MFP with immediate commit, plus an upper/lower same-lane
  write conflict at `0x2760`), and 42 dump3 lists of the shapes `70 06 08 40 42`, `70 08 40 42`,
  `52 66 08 40 42` (commands `0x70`, `0x52`, `0x66`, `0x40`: no research, no handlers).
- Host-space drawing: `GS::submitHostTriangle` exists and the native `0x28` handler uses it behind
  `PS2X_VU1_HOST_DRAW=1` (default off). Offline equivalence: `vu1_replay --vram-diff` (hard
  differences over drawn pixels, 1 % tolerance, can fail). In-game: gate green with the knob on.
  Family-C lists have no vram-diff coverage (they draw nothing in the synthetic context).
- Render-target scale: NO-GO in Sprint 2. `docs/research/14-gs-render-target-scale-spike.md`
  enumerates 15 touch points across 9 subsystems and the two GPU→VRAM readbacks that need a
  downsample (one is the title-label texture path). Its §6 gives the staged outline this sprint
  follows: S3-0 presentation-upscale experiment, S3-a de-overload `RenderTarget::width/height`,
  S3-b GPU-side native resolve, S3-c the scale knob, S3-d verification.
- Gates: `./build.sh test` (unit suite ×N, four fixture verifies, host-draw verify, vram-diff,
  clamp fixtures) and `python -m tools_py.parity.gate` (title/transition/mission; the transition
  gate now counts only frames at/after the burst step and its probe reaches the fade). Gate unit
  tests run from committed fixtures. `./build.sh runtime` must precede a gate.
- User-visible warts, unchanged since the audit: black 16×16 squares at the frame edges of the
  intro movie and the title's movie background, flickering per frame (STATUS 2026-09-10 18:45:
  likely dropped/undecoded MPEG macroblocks in the IPU/PSS path or the 16×16-block upload);
  one intro-cinematic freeze in two mission runs (parked).

## 2. Sprint goals, in order

1. **S3-0 — presentation upscale experiment.** Replace the final aspect-fit `GL_LINEAR` stretch of
   the 640×448 frame (`ps2_runtime.cpp:2585-2604`, present-copy filter `gs_gl_backend.cpp:1567-1568`)
   with integer-scale-then-fit or a sharp-bilinear present sampler behind `PS2X_PRESENT_FILTER`.
   Zero GS semantics. Outcome: a side-by-side sheet and a one-paragraph verdict on how much of the
   perceived softness is presentation.
2. **S3-a — de-overload the render-target size field.** Split `RenderTarget::width/height` into
   native and host sizes (both 1024 for now) and make every site in research/14 §3 name the one it
   means. No behaviour change: gate green and title captures ≥ 99 against the last known-good run.
3. **S3-b — GPU-side native resolve.** Each scaled target gets a 1× native mirror resolved by one
   blit/shader pass; both readbacks (`downloadRenderTargetToShadow`, `downloadRenderTargetToCpu`)
   read the native mirror, so the CPU loops and the PCIe cost stay at native size. Filter choice
   (point vs box) in one place behind `PS2X_GS_SCALE_FILTER`. At S = 1 the mirror is the target
   itself (no copy).
4. **S3-c — `PS2X_GS_SCALE`.** Allocation at N×S, `appendVertex` and both scissors scaled, the two
   upload loops expanding native pixels S×S, `uTexScale` for RT-as-texture sampling, presentation
   rects, frame-dump downsample; CPU backend stays 1×.
5. **S3-d — verification.** `PS2X_GS_SCALE=1`: full gate green, title captures ≥ 99 vs the S3-a
   baseline (bit-identical by construction). `PS2X_GS_SCALE=2 PS2X_VU1_HOST_DRAW=1`: gate green
   and a human-inspected mission sheet with a visibly sharper HUD (the ≥ 99 score cannot apply at
   S = 2: captures are window-sized readbacks; a sharper frame scores lower by design).
6. **Fourth command family.** Research note (`docs/research/15-vu1-fourth-family.md`) at the
   research/13 level for `0x70`, `0x52`, `0x66`, `0x40` and `0x34`, then handlers one per commit
   verified on the dump3 goldens; pre-scan accepts those lists only when complete.
7. **Family-C vram-diff coverage.** A fixture (or synthetic GS context) under which a family-C run
   draws through `0x28`, so `--vram-diff` checks it rather than SKIPping.
8. **Intro-movie macroblocks — bounded spike.** Reproduce with `PS2X_GS_DUMP_DISPLAY` over the
   intro and a PCSX2 burst capture of the same seconds; localise to the IPU/PSS decode or the
   16×16-block upload; fix if the cause is a runtime bug reachable in one bounded step, otherwise
   a note with the exact divergence for Sprint 4.

## 3. Non-goals

- Emulator speed work stays frozen (VU1/VU0 interpreter, scheduler, GS/GL caching and upload
  performance). Accuracy fixes the gate finds are allowed; the S3-b resolve pass is a correctness
  structure, not an optimisation.
- Widescreen, texture filtering changes, decompilation of EE game logic.
- The intro-cinematic freeze stays parked unless the macroblock spike lands on the same cause.
- The first-kill online acceptance test is untouched.

## 4. Definition of done

- `PS2X_PRESENT_FILTER` exists with a documented verdict (goal 1).
- `PS2X_GS_SCALE=1` is the default and the full gate is green with title captures ≥ 99 against
  the S3-a baseline (goals 2-5).
- `PS2X_GS_SCALE=2 PS2X_VU1_HOST_DRAW=1` full gate green; the mission sheet attached to STATUS
  shows a sharper HUD; `PS2X_GS_SCALE=2` with the host-draw knob off also gate green (scaled
  rasterisation of GIF-path triangles must not break anything).
- Every one of the 166 recorded dispatcher runs is native, or the residual set is listed with the
  reason (goal 6). `0x34` may remain if its EFU semantics cannot be made bit-exact in one sprint;
  say so.
- `vu1_replay --vram-diff` checks at least one family-C run (goal 7).
- The macroblock spike ends in either a fix gated green or a note naming the divergent
  macroblock, frame and decode stage (goal 8).
- `./build.sh test` deterministic (3 runs), gate green, docs (STATUS Current state, README knobs,
  LOOP_PROMPT goal text) updated, plan boxes ticked, branch `sprint-3` fast-forwarded into
  `develop` and `main`.

## 5. Carried over from Sprint 2 (deferred findings, verbatim from the sprint ledger)

- Task 9: title fixture s08 scores 94.4 (< 95 target, > 90 floor).
- Task 1: recordDrawDebugEventUnlocked duplication (one-token call-site change in vertexKick would fold it); ctxt test checks one pixel.
- Task 3: touch-point tally granularity inconsistent (15 headline vs 18 in the table) — fix the headline when research/14 is reopened and propagate to STATUS/LOOP_PROMPT.
- Task 4: -0.0 FMAND sign convention and the N>1 inline-block path are untested by the corpus.
- Task 8: transition floor calibrated on one binary and depends on capture cadence (1 Hz); montage sheets ~1.6x taller with w*.png; wait_capturer constructed for non-wait steps; the probe guards assume the memory-card dialog appears at steps 9/10 (a boot without it gives a false red, not a false green).
- Task 7: two test-only ceiling knobs ship in the runtime (narrow-only); clamps unreachable on real data (covered by the knob tests); prog_6 has one pixel of vram-diff headroom (0.806 % of 124 drawn vs 1.00 %).
- Final review M12/M13: test_gate monkeypatches drive.winshot.grab; the 1 Hz full-res grab inside the poll loop can stretch settle timing on a loaded host.
- Flaky VSync scheduler-stop test: not reproduced in 5 runs after the 2000 ms budget; still on watch.
