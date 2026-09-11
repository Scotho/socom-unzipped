# Sprint 2 — host-resolution drawing, the rest of the dispatcher, gate hardening: design

Status: contents approved by the user on 2026-09-11 ("approved. proceed into sprint 2 after 1 is
finished"). Project: SOCOM Unzipped, repo `github.com/Scotho/socom-unzipped`, branch `develop`.

## 1. Where Sprint 1 left the render path

- One VU1 image (FNV `d418194495c25213`). Entry 0 uploads the command list; entry `0x1b50` is the
  command dispatcher (`docs/research/12-vu1-entry0-ui-path.md`).
- `src/lib/vu/native/socom2_dispatch_0x1b50.cpp` runs family-A (UI-quad) lists natively, bit-exact
  against the interpreter (76/76 runs across dump2/3/4, `--regs all`), default on
  (`PS2X_VU1_NATIVE=0` reverts). Family B/C lists (world objects, the `0x3618` subroutine, the
  looping `0x4c`/`0x32` commands) hand back whole.
- The native program still emits the same GIF packets the microcode does; the GS frontend converts
  them to `GSPrimitiveBatch` (float x/y in pixel units) and the only producer of
  `GSRasterBackend::Submit` is the private `GS::vertexKick`. Nothing lets a caller submit
  host-space vertices.
- Gates: `./build.sh test` (428 unit tests + four fixture verifies), `python -m tools_py.parity.gate`
  (title/transition/mission). The transition gate counts black-screen frames only inside burst
  steps; drive.py captures nothing during its settle waits, so the count is capture luck. The gate's
  positive unit tests skip on a fresh clone (fixtures live under git-ignored `logs/`).

## 2. Sprint goals, in order

1. **Host-resolution submit hook.** A public `GS::submitHostBatch(const GSPrimitiveBatch&)` (or
   equivalent) that hands the active backend a batch built by native code, with the current
   context's draw state, bypassing the 12.4 fixed-point GIF round trip. First consumer: the
   family-A packet builder (`0x1780`) draws its triangles through the hook when
   `PS2X_VU1_HOST_DRAW=1`, otherwise it emits GIF packets as today. Verified two ways: the GIF
   path stays bit-exact (existing goldens), and the host path renders the same picture (gate
   title/mission sheets compared with `compare.score` ≥ the Sprint 1 thresholds).
2. **Host resolution.** The hook carries sub-pixel float coordinates; the GL backend renders the
   hooked batches at the host framebuffer scale (initially 1x to prove equivalence, then a
   `PS2X_GS_SCALE` integer factor). Widescreen is out of scope this sprint.
3. **Family B and C handlers.** The world-object command set (`0x02 0x0a 0x12 0x56 0x1a 0x2a 0x4c`,
   the `0x3618` subroutine, the C variant) implemented natively with the Sprint 1 recipe:
   research note first (research/12 §f corrections and the "not implementable yet" handlers),
   then one handler per commit verified on the existing mission dump sets, hand-back rules per
   §f.3 (family B is only safe at list start and program end).
4. **Per-handler work clamps.** Each handler clamps its loop count against the documented
   ceilings at read time, so a header rewritten mid-list cannot defeat the entry pre-scan.
5. **Gate hardening.** drive.py captures during settle waits (the transition gate then measures
   rendering, not timing); one small title run and one 2-frame transition run committed as
   fixtures so `tools_py/tests/test_gate.py` runs its positive cases on a fresh clone; the flaky
   VSync test either fixed properly or moved to an advisory suite.

## 3. Non-goals

- Emulator speed work stays frozen (VU1/VU0 interpreter, scheduler, GS/GL caching).
- No widescreen, no texture filtering changes, no decompilation of EE game logic.
- The intro-cinematic freeze and the black macroblocks on the intro movie stay parked (goal-3
  items outside the render path).

## 4. Definition of done

- `PS2X_VU1_HOST_DRAW=1` renders the title, menus and the mission HUD through the host hook with
  the gate green; `PS2X_GS_SCALE=2` produces a visibly sharper HUD in the mission sheet with the
  gate green.
- All 166 dispatcher runs in dump2/3/4 run native end to end with zero mismatches (`--regs all`),
  or the remaining hand-back set is listed with the reason.
- `python -m unittest tools_py.tests.test_gate` runs every positive case on a fresh clone.
- The transition gate examines ≥ 5 black-screen frames on every run of a clean build.
- `./build.sh test` is deterministic across three consecutive runs.

## 5. Carried over from Sprint 1 (deferred findings, verbatim from the sprint ledger)

- Task 1: minor (deferred): suite runs only the reference GS/VU1/XGKICK modes, not the runner's default fast/GL paths — follow-up: a second run of ps2x_tests with the runner defaults.
- Task 1: minor (deferred): upstream ps2_memory_tests.cpp:1405,1512 index captured[0] after a non-fatal size assert (the segfault path); untracked 0-byte vu1_packets.bin in repo root (vu1_replay default --out), remove at finish.
- Task 1: minor (deferred): ps2xTest main.cpp comment claims env overrides are possible but PS2X_VU1_XGKICK_CYCLE_EXACT is presence-tested (ps2_vu1_core.cpp:1073) — comment wrong / scope var to the one test; no assertion that the reference modes took effect; build.sh `all` does not run the suite (decide deliberately); usage comment omits `tools`.
- Task 2: minor (deferred): brief's dump size (32,848) is wrong, real 33,360; fix in the plan text at finish.
- Task 2: minor (deferred): '<no golden line>' MISMATCH shape differs from the interface text; --regs accepts any non-"none" string as all.
- Task 4: minor (deferred): HANDOFF dropped the Mandate paragraph's "user watches the title screen closely" sentence (LOOP_PROMPT step 6 keeps the rule).
- Task 6: minor (deferred): hash+native check evaluated on every run() incl. VU0 macro programs (negligible, note for the freeze); m_knownGeneration = ~0ull in the override hook is a no-op in practice.
- Task 5: minor (deferred): f.4 staging row says "with Q in .w" — vf31.w holds clip w, and PACKED ST's Q is the .z lane; drop/correct the parenthetical. 0xf90's vf24/vf25 loads are dead (native must not read-modify-write prior fog); vf15 chain of the pipelined pair not shown. Carry both into the Task 7 dispatch.
- Task 3: minor (deferred): step-index regexes stop at 100; hold-threshold wording.
- Task 6: minor (deferred, hygiene): ps2_runtime_interrupt_tests.cpp:574 'scheduler stop wakes an idle VSync wait without a timeout' is flaky (80 ms wall-clock waitUntil), alternated pass/fail on an unmodified binary — makes ./build.sh test non-deterministic; needs a fix or a generous timeout.
- Task 3: minor (deferred, runtime): mission run mission3 froze in the intro cinematic (s29-s41 identical frames, no fault in the game log) while mission4 played it — 1 freeze in 2 runs; the mission gate is green but not yet proven stable. Investigate under goal 3 (cinematic/IPU) after the sprint.
- Task 7: minor (deferred): inside handler loops ops appear pair-by-pair with deferred writes (pipeline order needed for --regs all); acceptable trade-off, documented in the file.
- Task 7: minor (deferred): vu1_replay `--verify` consumes the next token positionally (`--verify <golden> --native ...` order matters) — document in usage; the 256/256 ceiling is policy, exceeding lists fall back silently (counters only).
