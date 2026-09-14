# 27 — GL depth precision: the fix, and why it does NOT explain the Seeding Chaos shards

Written 2026-09-14 on branch `fix/gl-depth-precision` (off `develop` 2ae4d79), paused mid-task by the
owner. **Nothing is committed**; the working tree carries the change described in §2. Markings:
**[verified]** = measured in this pass; **[inference]** = follows from verified facts, not measured.

## 1. The defect that is real: GL depth quantisation

`gs_gl_backend.cpp` mapped integer GS z to depth as `z / 2^32` (`appendVertex`, was line 2630) and then
`gl_Position.z = aPos.z * 2.0 - 1.0` in the vertex shader (was line 235), with a
`GL_DEPTH_COMPONENT32F` attachment (line 1309) and `GL_GEQUAL` for ZTST 2 (line 2814). Near ndc −1 a
float32 has an ulp of 2^-24, so **window depth lands on multiples of 128 GS z units for every z below
~2^30** [verified: `ps2x_tests` suite `GSGlDepth`, and independently by numpy in research/26 §3.3].
The CPU backend compares integer z exactly (`gs_cpu_backend.cpp:856`), so the two backends disagree.

A Z16S scene therefore had ~512 distinct depths in total. The stream water of Seeding Chaos is Z16S
with z 1032–8693 (VU1 dump `logs/vu1dump3/vu1_prog_27.bin`, TEST_1 0x5000c, GEQUAL)
[verified in research/26 §3.2], i.e. ~70 usable levels: 1105, 1152, 1202 all collapsed onto 1152.

That quantisation is a genuine precision defect and is worth fixing on its own. **It is not what makes
the stream render as grey shards** — see §3.

## 2. The change sitting uncommitted

Two files, plus a test:

- **`ps2xRuntime/include/runtime/gs/gs_gl_depth.h`** (new). `GsGlDepth::Mode` (`Legacy`,
  `ClipZeroToOne`, `FragDepth`), `attribute(z)` = `min(z, 2^32-1) / 2^32`, `ndc()`, `windowFromZ()` —
  the CPU replica of the GPU's float32 depth path, so the mapping is testable without a GL context —
  plus `legacyRequested(env)` and `choose(legacy, clipAvailable)`.
- **`ps2xRuntime/src/lib/gs/gs_gl_backend.cpp`**:
  - the vertex/fragment shaders take a `PS2X_DEPTH_MODE` define, injected after the `#version` line
    by `withDepthMode()`; mode 1 sets `gl_Position.z = aPos.z` (no `*2-1`), mode 2 carries a
    `noperspective` varying and writes `gl_FragDepth`;
  - `probeClipControl()` resolves `glClipControl` through `glfwGetProcAddress` (raylib's glad stops
    short of GL 4.5), requires GL ≥ 4.5 or `GL_ARB_clip_control`, and verifies the call took by
    reading `GL_CLIP_DEPTH_MODE` back;
  - `ensureGl()` picks the mode once and logs it; `PS2X_GS_DEPTH_LEGACY=1` restores the old mapping;
  - `executeCommands()` sets `GL_ZERO_TO_ONE` around the guest replay and restores
    `GL_NEGATIVE_ONE_TO_ONE` at the end, because clip control is context-global and raylib's own 2D
    drawing sits at ndc −1 and would be clipped away;
  - `appendVertex` now calls `GsGlDepth::attribute`.
- **`ps2xTest/src/ps2_gs_tests.cpp`**: a `GSGlDepth` suite — legacy collisions (1105/1152/1202 and
  1280/1328), exactness and strict ordering of the new modes over
  {1105, 1152, 1202, 1280, 1328, 9000, 2^24−1, 2^31}, GEQUAL on 1152 vs 1160, and the mode choice.

**Status of the change** [verified, Run 1]:
- GL context is **3.3.0 NVIDIA 595.97**; the probe succeeds and the runtime logs
  `[gs-gl] depth mapping: clip-control (GL_ZERO_TO_ONE, z exact)`. The legacy A/B run logs the legacy
  line, so the knob works.
- `ps2x_tests`: **454/454**, RED first (2 failures with the new modes stubbed to the legacy maths).
- `build.sh test` **vram-diff PASS, checked=15 skipped=0**.
- Gate `s6_depth`: title **PASS 19/23** (same band as `s5_head_1x`); title run-vs-run against
  `s5_head_1x` s00–s19 is **98.7 min, 19 of 20 at 99.6–100** — the one 98.7 is s14, whose animated
  background movie is at a different phase (menu text and logo identical).
- Transition FAILed once (the probe hit the "Overwritten data will be lost" dialog and never answered
  it) and **PASSed on the rerun** (`s6_depth_r2`, 18 black frames at/after burst s15). Flow flake,
  not rendering.

**What is unfinished**: nothing in the code is half-written, but (a) the `FragDepth` fallback has
never executed on this host — clip control is always available here, so mode 2 is compile-tested only;
(b) no commit has been made, and `docs/research/26-water-polygons.md` has not had a verified section
appended; (c) the mission stage never produced a clean gameplay s28 in the new mode, so the water A/B
rests on the frames named in §3.

## 3. Negative results — do not re-run these

- **The fix does not remove the shards.** [verified] The only like-for-like spawn-camera frames are
  `s6_depth/mission/final.png` and `s6_depth_r2/mission/final.png` (new mapping, HELP pop-up) against
  `s6_depth_legacy/mission/s28_none.png` and `.../final.png` (legacy mapping, same build). The grey
  angular shards are present in **both** mappings. New-vs-legacy differs by mean 11.6/255 over the
  frame, but new-vs-new across two runs differs by 1.85, so most of that is run-to-run variation
  (pose, fog, foliage), not the depth change.
- **The depth test is not the mechanism at all.** [verified, the decisive one] A mission run with
  `PS2X_GS_NO_ZTEST=1` (`logs/parity/gate/s6_depth_noztest`, every draw passes the depth test) still
  shows the same shards — see `mission/s38_holdS.png` and `mission/final.png`. With the depth test
  disabled there is no z comparison left to get wrong, so research/26 §0's condition sentence
  ("the water, bed and banks tie or invert in the GEQUAL test") is **refuted**. The shard edges must
  come from the geometry or the colour/alpha of the `0x34` env-map pass, i.e. research/26 §4
  candidate 2 (TEX0 0x38a8 PSMT8 + CBP 0x3852 CT16 CLUT) or candidate 3.
- The mission gate stage is flaky on this host irrespective of the change: 4 of 5 mission runs today
  landed on the intro cinematic ("X TO ABORT", bands 0.34) or the HELP pop-up, in the **legacy** build
  as well as the new one. Reruns, not a regression. Two of those runs were slowed by another agent's
  launch holding the host (`sp-settle`).

## 4. Exact next step

1. Commit the change in §2 with explicit pathspecs (`gs_gl_depth.h`, `gs_gl_backend.cpp`,
   `ps2_gs_tests.cpp`) as the precision fix it is, and append a verified section to research/26 saying
   its condition sentence is refuted by the `PS2X_GS_NO_ZTEST=1` run. Do **not** claim the water is
   fixed. Push `fix/gl-depth-precision`; the controller merges.
2. Then take the shards to research/26 candidate 2: `PS2X_GS_TRACE_CMDS` at the spawn, find the
   `tbp0=038a8` submits, and compare the decoded texture and CLUT against a PCSX2 slot-8 GS dump
   (`python -m tools_py.parity.gsdump_capture --slot 8`). A cheaper first cut: re-run the mission with
   the `0x34` pass suppressed and see whether the shards go with it.

## 5. Artefacts from this pass

`logs/parity/gate/s6_depth` (full gate, new mapping), `s6_depth_r2` (transition PASS + mission),
`s6_depth_legacy` (`PS2X_GS_DEPTH_LEGACY=1` mission), `s6_depth_noztest` (`PS2X_GS_NO_ZTEST=1`
mission), `s6_depth_r3` (mission, HUD never matched).
