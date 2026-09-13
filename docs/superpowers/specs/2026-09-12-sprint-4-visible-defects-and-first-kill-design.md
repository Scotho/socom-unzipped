# Sprint 4 — visible render defects, gate trust, and the first-kill online test: design

Status: scope approved by the user on 2026-09-12 ("Render defects, then online"; the online half
runs "all the way to a first kill"; the render wave includes ground height). Project: SOCOM
Unzipped, repo `github.com/Scotho/socom-unzipped`, branch `develop` (= `main` = 4868863 at sprint
start). Executor: an Opus-class model following
`docs/superpowers/plans/2026-09-12-sprint-4-visible-defects-and-first-kill.md` with
superpowers:subagent-driven-development.

## 1. Where Sprint 3 left things

- **Render scale.** `PS2X_GS_SCALE=1..4` (default 1) rasterises every draw into render targets S
  times their native GS extent while everything the guest can read back stays native, through a
  GPU-resolved native mirror (`PS2X_GS_SCALE_FILTER=point|box`). S=2 is verified on both draw
  paths and sharpens 3D rasterisation only — the HUD, menus and title are textured quads drawn at
  native texel density, so the scale cannot add detail there. S=3/S=4 are admitted by the clamp
  but deliberately untested.
- **Native VU1.** The `0x1b50` dispatcher runs 162/166 recorded lists natively, bit-exact
  (`--regs all`). The residual is 4 programs of the `52 66 08 40 42` shape and is a documented
  ruling, not unfinished work.
- **Equivalence.** `vu1_replay --vram-diff` checks 14 and skips 0, covering family C and the
  fourth family; `./build.sh test` now fails on the texture-in-blank-region warning instead of
  letting it scroll past.
- **The intro-movie black macroblocks are localised** (`docs/research/16-intro-movie-macroblocks.md`):
  the MPEG decode is clean — 2067 consecutive pictures identical to an offline libavcodec decode —
  and the loss is in the shadow-VRAM → GL-render-target mirror (`executeUpload` →
  `refreshRenderTargetsFromShadow` → `refreshDirtyRows`), with the divergent pictures and 16×16
  block coordinates named. No fix landed: both candidates lived in the file Sprint 3 was rewriting.
- **~~The online match has been frozen at round start since 2026-09-10.~~ RETRACTED by this
  sprint's own Tasks 5 and 6 — see the note under this bullet.** Both instances sit at
  "STARTING ROUND 1 OF 11"; only camera pitch, fire and stance respond. The peer transport is
  decoded and alive (22-byte reliable-channel packets, sequenced and acked both ways, no SCERT
  framing, no crypto), so the freeze is game logic above the transport. **~~HANDOFF records that the
  PCSX2 golden match sits in the same frozen state~~**, which this sprint treats as a lead rather
  than a footnote.

  > **Superseded by `docs/research/18-online-round-start.md` §1 and §4 (Tasks 5-6, fixed in
  > `abf35bb` + `5ed29ca`).** The premise this sprint was written on is false in both halves, and
  > it is left standing here so the next spec author sees what a two-week misdescription looks
  > like from the inside. (1) **Nothing was frozen.** The "STARTING ROUND 1 OF 11" banner is a
  > ~6-second transient on ours too and the round timer runs; the true sentence is **"the round
  > runs and the local player cannot move"**. (2) **The PCSX2 golden was not a match.** Two PCSX2
  > instances driven against our own Horizon stack play a full round and advance to round 2
  > (`docs/research/assets/18-s0-evidence.png`); the "golden" HANDOFF cited was two stills of a
  > match with no input ever sent. Treating it as a lead was right — treating it as evidence for
  > two weeks was not. The cause was local and entirely inside our own HLE:
  > `sceInetInterfaceControl(0x200)` returned a constant, `msSinceNetActivity` never reset, and the
  > movement scale clamped to 0.0 on frame one (pitch is not one of the three scaled axes, which is
  > the whole reason RY survived).

## 2. Sprint goals, in order

### Wave 1 — visible defects and a gate you can trust

1. **Intro-movie macroblocks — fix.** research/16 §7 names the next step exactly: per movie frame,
   count `executeTransfer` calls with `rrw == rrh == 16` against `refreshRenderTargetsFromShadow`
   calls from `executeUpload`. If the second is smaller, candidate 1 is proven and the fix is to
   mark the dirty rect from the transfer itself (or on the transfer's completion, regardless of how
   its bytes arrived) rather than from the byte accumulator. The parity gate cannot see this defect
   — it moves a title score by ~0.1 % — so the task ships its own check using research/16 §8's
   capture-diff recipe.
2. **`drive.py` crop-to-non-black.** A resized window currently degrades the title score *smoothly*
   to its 16/23 pass floor rather than failing, so the gate can hide a red run. Crop each capture
   to its non-black rect before the 160×112 resize.
3. **`--vram-diff` bucket calibration.** Widen the `hard` scorer's two by-design buckets — delta ≤ 2
   counts as rounding only when the destination was written *and* ABE=1; interior seams qualify via
   a 3×3 membership test with tolerance ≥ 2 — then add the held-out `vu1dump4_prog_182` (1.488 %)
   to the fixture set. This changes the equivalence oracle and is reviewed as such.
4. **Ground height.** The player rests 14.7 above the vertical collision point on ours against 20.1
   on the console, with an identical collision probe (hit y = -146.371, same normal). The captured
   diff: mover (vtable `0x6694b0`) `+0x5c` = 4.0 vs 6.3338 and `+0x70..+0x7c` differ; actor (vtable
   `0x6691a0`) `+0x10` state `0x00080502` vs `0x2`; actor `+0x2bc..` holds a cached ground point on
   ours. First step is to trace the mover's update method and find the writer of `mover+0x90.y`.

### Wave 2 — the first-kill acceptance test

The user's standing definition of "playable": an automated test that drives a two-instance online
match to its end by one player shooting the other or killing them with a grenade, with the
kill/round-end state read from guest memory or the Horizon world state and both screens captured.

5. **S0 — aim the work before spending it.** Reproduce the round-start freeze with two **PCSX2**
   instances against our local Horizon server. If it freezes identically, our runtime is largely
   exonerated and the target is the server or the protocol above the transport — and
   `server/horizon-server`, `server/dme-plugins` and `server/medius-plugins` are in source. If
   PCSX2 reaches playable gameplay, the runtime is implicated and the target is guest-side. One
   controlled run decides which body of code the rest of the wave reads.
6. **S1 — unblock the round start.** Trace whichever side S0 implicates. Guest-side: the callers of
   the libnetb_ex UDP send/recv (`FUN_00247fe8` / `exUdpRecv`) under `PS2X_CALL_TRACE(+_DUMP)` on
   both instances to read the P2P state machine, then the actor/controller flag that ignores
   LX/LY/RX while RY works. Server-side: the DME/Medius message the retail server sends that ours
   does not, read from the plugin sources against `server/logs`.
7. **S2 — movement and aim.** Pad injection exists (`PS2X_SOCOM2_INPUT_FILE`, drivers write
   `logs/pad_A.txt`/`pad_B.txt`). Calibrate degrees per second of turn against the compass, then
   steer A toward B from the two `0x416054` position peeks.
8. **S3 — kill and round end.** Read the per-player health/kills record near the player actor
   (vtable `0x6691a0`) or the DME world state under `server/logs`, capture the round-end screens on
   both instances, and wire the whole thing into `tools_py/parity/online_match_ours.py` so the
   acceptance test is one command.

## 3. Non-goals

- Emulator speed work stays **frozen** (VU1/VU0 interpreter, scheduler batching, GS/GL caching and
  upload performance). The two-instance frame rate is a test-rig concern; the second client may run
  in PCSX2. Accuracy fixes the gate or the acceptance test forces are allowed.
- No default changes: `PS2X_GS_SCALE=1`, `PS2X_GS_SCALE_FILTER=point`, `PS2X_PRESENT_FILTER=linear`,
  `PS2X_VU1_HOST_DRAW` off, `PS2X_VU1_NATIVE` on.
- S=3 and S=4 stay untested; the 4-program VU1 residual stays closed.
- No widescreen, no texture-filtering changes, no decompilation of EE game logic beyond what S1
  needs to read a state machine.
- The intro-cinematic freeze (seen once in Sprint 1) stays parked unless Wave 1 item 1 lands on it.

## 4. Definition of done

- **Wave 1 item 1:** the intro run's capture diff (`mask_ours & ~mask_ref`) reports **zero** missing
  blocks across the sampled pictures, the title gate is green, and the check that proves it is
  committed and runnable — or, if the count in §2.1 disproves candidate 1, a note naming what the
  count showed and the next candidate, with no speculative fix.
- **Wave 1 item 2:** a deliberately pillarboxed run scores within the normal band of a native run,
  or fails loudly; `python -m unittest tools_py.tests.test_gate` green.
- **Wave 1 item 3:** `vu1dump4_prog_182` is in the fixture set and passes; the `+8 px` sanity
  experiment still scores 29–55 % against the widened buckets; `./build.sh test` green.
- **Wave 1 item 4:** the ground offset matches the console within the mover's own precision, or a
  research note names the writer, the value and the exact divergence.
- **Wave 2 S0:** a recorded verdict — runtime implicated or exonerated — with the run logs behind
  it. This is a required deliverable; the rest of Wave 2 is aimed by it.
- **Wave 2 S1:** both instances leave "STARTING ROUND 1 OF 11" with local control enabled, proven
  by pad injection moving the player on both sides (LX/LY/RX, not just RY) — or a research note
  naming the exact condition that never becomes true and why the fix is not one bounded step.
- **Wave 2 S2/S3:** `python -m tools_py.parity.online_match_ours …` drives a match to a kill or
  grenade death, reads the kill/round-end state, and captures both instances' screens. If S1 does
  not land, S2 and S3 are not attempted and the sprint says so.
- `./build.sh test` deterministic (3 runs), `python -m tools_py.parity.gate` green at the defaults,
  docs updated (STATUS Current state, README knobs, LOOP_PROMPT goal text), plan boxes ticked, and
  `sprint-4` fast-forwarded into `develop` and `main`.

## 5. Sequencing and risk

Wave 1's four items are file-disjoint from each other except items 1 and 2, which both touch the
capture path only at its ends; they may run in parallel under the build lock. Wave 2 is strictly
sequential: S0 aims S1, S1 gates S2, S2 gates S3.

**S1 is the sprint's real risk.** It has blocked the acceptance test since 2026-09-10, and its cause
is not yet known to be in code we control. The wave is therefore built so each stage lands
independently: S0's verdict is worth having even if S1 stalls, and S1's localisation is worth having
even if the fix is not bounded. The sprint does not fail if the first kill is not reached — it fails
if it reaches the end with nothing said about why.

## 6. Carried over from Sprint 3 (deferred, not this sprint's scope unless listed above)

- Host-draw's uniform-fill blind spot: with a uniform texel, any ST/UV/Q divergence between the GIF
  and host paths is invisible, so family C's *texturing* is still unmeasured. A patterned
  deterministic fill would restore that axis.
- `cmdUnpackScaledVertices` is a 115-line clone of `cmdUnpackVertices` differing in 8 lines, where
  the file's convention for a variant is a shared loop plus a thin prologue.
- `resolveToMirror` resolves all 1024 native rows though readers need only `usedHeight` — **taking
  this would be a freeze violation**; it stays deferred deliberately.
- `--verify` does not compare `cycles`; `s_integerStage` has no teardown; the `rt`-vs-`rt2` slip at
  `gs_gl_backend.cpp:1639` is benign while every RT is 1024².
- Two transition-gate intermittencies: the save-dialog probe flake (too few frames examined, peak 0)
  and a one-frame residual strip at rows 396-447 (~1 in 5 runs, reproduced on the pre-scale binary;
  the `refreshDirtyRows`/`executeClear` attribution is a hypothesis with no isolation test behind
  it). Wave 1 item 2 does not fix these.
- At 2× one extra mission-load `untilref` press shifts every later step by ~21 s, so 1× and 2×
  frames must be matched by content, never by step name.
- The flaky VSync scheduler-stop test remains on watch.
