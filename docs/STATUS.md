# Project status — updated 2026-09-13

## Current state (keep to five lines; update when it changes, dated entries below are the log)
- Build: `./build.sh all`; tests `./build.sh test` (ps2x_tests 450/450 + vu1 fixture verify + `--vram-diff` at `checked=15 skipped=0`; **since Sprint 5 Task 0 it also runs the Python suite first** — `python -m unittest discover -s tools_py/tests -t .`, 802 tests — both required green before any commit touching `third_party/ps2recomp/`, `recomp/` or the parity tools). Gate `python -m tools_py.parity.gate`: title/transition/mission; **the mission stage now requires live gameplay** (`d2eb932`) — ≥ 2 consecutive gameplay hold pairs differing by mean ≥ 3.0 and a capture count matching the logged holds, not just the mission having loaded (it had scored the intro cinematic since 2026-09-12).
- Plays: title/menus 59 fps, Albania 5-1 at 36-42 fps. Online, two instances on local Horizon: **the acceptance test PASSED** — a Frostfire match ends in a kill read from guest memory, confirmed by two independent scorers (`docs/research/22`, `docs/research/assets/22-first-kill.png`). **Frostfire control is fixed** (VU0 `vf0.w = 0` on `StartThread` contexts, `b625291`) and **the single-player gameplay stall is fixed** (an unbounded GS command backlog, `8281254`/`7448601`/`92d30f0`). **The runtime is frozen at `92d30f0` for the online ladder** (R45/R61) until Sprint 6 reopens it.
- Sprint 4 (2026-09-13, entry below): intro-movie macroblocks fixed at the root (a cross-thread race on `m_currentTransfer`), the gate's silent-failure paths closed, `--vram-diff` 15/15, `rand()` 31-bit over the guest's own seed, soft-double ABI stubs re-bound, "ground height" reframed as the third-person camera (localised, not fixed), the online movement blocker fixed and A/B-proven on Medley, the acceptance test built and not passed.
- **Sprint 5 (2026-09-13): the acceptance test PASSED.** Ladder launch 2 on Frostfire, rounds 1–3 KILL on both scorers (KillWatch actor fields + `verdict_replay` valves), screens "socomc fragged socome with M4A1". Root causes fixed on the way: Frostfire's lost control (VU0 `vf0.w = 0` on `StartThread` contexts) and the single-player gameplay stall (an unbounded GS command backlog). Dated entry below.
- Native VU1 unchanged since Sprint 3: 162/166 lists native, bit-exact; the residual 4 (`52 66 08 40 42`) are a documented ruling (`docs/research/15`). Defaults unmoved: `PS2X_GS_SCALE=1`, `PS2X_GS_SCALE_FILTER=point`, `PS2X_PRESENT_FILTER=linear`, `PS2X_VU1_HOST_DRAW` off, `PS2X_VU1_NATIVE` on, `PS2X_SOCOM2_NET_STATS` on. Known open: the camera's skeleton-root decay (`docs/research/17` §4.3); single-player teleports; the online freeze root cause under host load; `movie_blocks.py` in no automation — all parked to Sprint 6 (`docs/ROADMAP.md` §6).

## 2026-09-13 (local) — Sprint 5 landed: THE ACCEPTANCE TEST PASSED — Frostfire control fixed, the single-player stall fixed, and a first online kill on three independent rounds

Sprint `2026-09-13-sprint-5-control-readout-and-first-kill`, branch `sprint-5`, Tasks 0-7 plus the
owner-requested broad review (Amendment A, mid-sprint). Every task implemented, independently
reviewed, fixed and re-reviewed; the plan's own `## Outcome` and `## Rulings made on the owner's
behalf` sections carry the full detail this entry summarises. Headline facts, and every retraction,
are in `docs/KNOWN.md`.

### The sentence that matters

**The acceptance test PASSED.** `bash scripts/parity/ladder_frostfire.sh --pinned
logs/parity/s5_t5_ladder2` (HEAD `171290b`, exe sha `234b4772cd0a8bf8`, runtime frozen at `92d30f0`)
scored `KILL killer=A victim=B t=141.33` on round 1 — both KillWatch (actor fields: `+0x1044`
1.0 → 0.298 → 0.0 in 0.25 s, `+0xF7A` 1 → 2, word 0 intact at `006691a0`) and `verdict_replay`
(valves: `total_mp_kills` 0→1 on the killer's own instance, `aiteam_08` 1→0 on both instances within
0.25 s, the killer's R1 burst 0.59 s before the death from 27.9-29.2 units in 3-D, `dy` 0) —
independently re-derived clause by clause by a second reviewer before the sprint declared it met.
Rounds 2 and 3 repeated the kill in the same lobby (t=244.10, t=336.51); round 4 reached rung 2
only (111 in-tolerance bursts, no damage — an aim bias that never corrected, not a broken damage
path). Both screens read "socomc fragged socome with M4A1 / ALL TERRORISTS ELIMINATED / SEALS
VICTORIOUS!", tiled into `docs/research/assets/22-first-kill.png` (`5f1de26`).

### What landed, per task

- **Task 0 (preconditions, `2b7c425`+3 fix rounds).** A heartbeat loop lock (`scripts/loop_lock.sh`)
  that reaps only a stale, idle holder and refuses the stale break while anything is busy;
  `scripts/run_detached.sh` and `kill_stale_drivers.ps1`; `build.sh test` now runs the Python suite
  first (`tools_py/tests`, unittest only); `docs/CURRENT_SPRINT.md` created as the loop's sprint
  pointer.
- **Task 1 (Frostfire control handover, `03d3aa6`/`b625291`/`0118c95`+`b89c4c0`, 8 + 2 over-cap
  launches).** The lead this sprint opened with — an uninitialised "ghost flag" `ng+0xd2` — was
  real but **retracted**: the chain is reachable and verified in the decomp, but it never fired
  (launch 1). The actual stop was `research/23`'s ground probe: at the Frostfire spawn,
  `ProbeEval` returns a miss with candidate count 0 because the ground models are linked into the
  collision grid by their **untranslated** bounds — cell (0,0)/(0,2) instead of the spawn's
  (4,3)/(3,7) — so the local player's `actor+0x420` (last ground-hit time) is never stamped and the
  online snap-back suppresses movement from clock 0.6 s. Root cause: `FUN_003085c0`'s
  `vmaddw.xyz vf9, vf7, vf0w` translation scale reads VU0 `vf0.w`, and `R5900Context()` zeroed
  `vf0` — correct for the main thread's constructed context, wrong everywhere else, because on real
  hardware `vf0` is the constant `(0,0,0,1)`. Every `StartThread`/`GuestThread`/`GuestInvocation`
  context (the level loader runs on one) inherited the zero. **Fixed** by setting `vf0 = (0,0,0,1)`
  in the constructor, authorised without a pre-fix trace because it is correct behaviour regardless
  of cause (R27) — confirmed by a post-fix census (all 48 translated Frostfire props now linked by
  world bounds, 0 of 48 before) and by launch 3, where both sides moved the whole 302 s round
  (MoveScale `f12 = 1.0` throughout, probe hits 1332/1332 and 1428/1428). The knob built as a first
  candidate fix, `PS2X_GUEST_MALLOC_ZERO` (default off), turned out not to be the cause and ships
  unused. The Medley control (launch 8c) supplied the unconditional clock round-end negative
  fixture Task 6 needed, and surfaced 8-17 s guest freezes under host load (parked to Sprint 6).
- **Task 2 (kill readout confirmation, `d0f4ccb`/`e685b82`/`6b0f258`, 4 single-player runs, 3
  usable).** Health `actor+0x1044` and alive `actor+0xF7A` (sourced statically last sprint) were
  armed as harness defaults; a single-player death was **not observed** in 3 usable runs (health
  dropped to 0.392 then the actor left the mission area — MISSION FAILURE, not a death) and this
  half closed "not observed" per the plan's own fallback (R28) — the first online death became the
  sole confirmation. The actor's own heading field was found along the way: quaternion
  `actor+0x70` → a 4×4 matrix at `+0x80..+0xbc`, walk direction `(-m[+0xa0], -m[+0xa8])`, p90 1.57°
  over 17 live holds at rest. The camera cannot supply a heading at all — `atan2(actor-camera)` has
  p90 error 23.85-55° depending on the sample gate — and Task 5 aimed from the actor matrix instead
  (R12).
- **Task 3 (a harness that cannot spend a match proving nothing, `736193c`+3 fix rounds+`24db942`+
  `42b1dd8`, lock-free).** Pure scorers (`verdict_core.py`) for control, contact, starvation and
  round-state, tested against real fixtures before any launch used them. A Sprint 4 reading was
  **retracted** along the way: `kill3`'s "lost mover" (0.00 units across two holds) was the camera
  record `0x416054` freezing while the actor itself walked ~65 and ~39 units on the two holds — the
  camera is not a liveness signal, only the actor's own position words are.
- **Task 4 (HLE and heap liveness audit, `ad32088`/`0cdb9a1`/`03d3aa6`/`3899b1e`/`07ffc0a`,
  zero-run + rides Task 1's build).** `object_diff.py` reproduces the uninitialised-heap signature
  by object rather than address, and corrected three ranges in last sprint's F3 list. A static
  census of all 223 bound HLE stubs (148 zero-call) found `sceGsSetDefDBuff` reading its trailing
  args from `$t0-$t2` where the guest passes them there directly — **fixed**, with the clear packet
  now seeded in context 1 and byte-exact against `title_pcsx2`. `PS2X_HLE_STATS=1` ships. The
  remaining ranked stubs (display-environment/zbp divergence, `rem_pio2f` precision) defer to
  Sprint 6 (one-line-fix rule, R20).
- **Tasks 5+6 (merged into one ladder by Amendment A, below).**
- **Task 7 (this close-out).**

### Root causes found

1. **Frostfire's lost control was VU0 `vf0.w = 0` on non-main-thread guest contexts**, not the
   "ghost flag" the sprint opened chasing. See Task 1 above.
2. **The single-player gameplay stall was an unbounded GS command backlog.** `GSGlBackend::record`/
   `Present` appended to `m_pending` with no bound; after the mission loaded, the GL replay thread
   fell to ~14 frames/s against 60/s recorded, so private bytes ran 275 MB → 13 GB in 4 minutes and
   the host presented one frame per 5-25 s. **Fixed** with bounded back-pressure
   (`PS2X_GS_MAX_PENDING_FRAMES`, default 3): the EE waits at `VBlankStart` while more than N frames
   are unreplayed, a consumer-progress heartbeat prevents the wait latching open on a large
   in-flight batch (R40), and the next VBlank deadline is clamped to drop accumulated debt instead
   of letting the guest run up to 4x real time to catch up (R41) — three fix rounds
   (`8281254`/`7448601`/`92d30f0`), the last of which also closed a idle-spin residual (R54).
3. **The mission-gate scorer had been scoring the intro cinematic since 2026-09-12.** `drive.py`'s
   HUD check matched a letterboxed cinematic frame after cropping the bars; **fixed** to require
   lit letterbox bands on the uncropped frame plus ≥ 2 consecutive gameplay hold pairs differing by
   mean ≥ 3.0 (`69e2a9d`/`d2eb932`), which is also what caught defect 2 above — the frozen-hold runs
   the old scorer had been calling PASS.

### Retractions this sprint

- **The uninitialised "ghost flag" `ng+0xd2`** as Frostfire's cause: the chain is real and verified
  in the decomp, but it never fires online (launch 1).
- **The exhausted-collision-grid theory** for the ground-probe miss: the grid is healthy (503 nodes
  + 7689 free = 8192, free head never 0 over ~2000 rows); the real cause is the untranslated-bounds
  linking above.
- **`kill3`'s "lost its second mover"**: the camera record froze, not the actor.
- **The "0.6 s host-clock coincidence"** note on Frostfire's move-path stop: the snap-back genuinely
  fires at guest clock 0.6 s; the "host wall clock" reading was the same threshold seen at coarser
  sampling resolution.

### The broad review and Amendment A

Mid-sprint, on request, an independent broad review (`.superpowers/sdd/…/broad-review.md`) judged
the plan's original Tasks 5-6 "not on track as planned" (~55-65% odds of a kill) against ~85-95%
with changes, on five re-derived facts: spawns are deterministic per map (Frostfire 691 units apart
on two discrete floors, dy 42); mutual standing does **not** starve either side online (~48 s at
full movement scale, contradicting a standing plan assumption); the actor-matrix yaw settles within
one 4 Hz row of a turn release; a clock round end keeps the actor block and resets both players to
spawn, so one lobby success can carry several rounds. **Amendment A** (`8672724`, rulings R42-R52)
merged Tasks 5 and 6 into one 16-launch ladder in which every round is its own acceptance attempt,
pre-registered the acceptance bars in spec §5.1/§5.1.1 before any match was scored, simplified the
default engagement to a host shooter following a recorded route to a standing victim, added launch
hygiene (a pinned harness snapshot per launch, a host CPU sampler, a `logs/.quiet` window, disk
refusal below 4 GB), and pulled a minimal lobby dropped-press re-send forward from Sprint 6. The
acceptance run came from this rewritten path, not the plan's original one.

### The acceptance run and its numbers

Ladder launch 2, one launch, no lobby failure. Per-round: round 1 contact 14.3 s / 58 rows, 1 burst,
victim health 1.0 → 0.298 → 0.0, closest 3-D 23.9 (dy 0); round 2 contact 6.1 s / 25 rows, 1 burst,
closest 20.6; round 3 contact 5.8 s / 24 rows, 2 bursts, closest 19.3; round 4 rung 2 only, 111
bursts at -4.1° aim error (inside the 5.68° tolerance, never corrected), 0/30 ammo twice over.
Frostfire's v2 route (derived from collision geometry, `docs/research/24`) arrived on all 4 rounds
in 77-89 s (9.5-11.3 u/s). `mp_round_count` steps ~33 s after a kill (not the ~5 s spec §5.1.1 had
estimated — corrected, no verdict depended on it); `total_mp_kills` steps on the killer's instance
only and resets to 0 next round.

### Launch counts against caps

| task | cap | used |
|---|---|---|
| Task 1 (Frostfire control) | 3 usable / 8 launches | **8 + 2 over-cap** (R33, the Medley control) |
| Task 2 (SP kill readout) | one run | **4 single-player runs** |
| Tasks 5+6 (merged ladder, Amendment A) | 16 launches | **3 of 16** (launch 1, 1b, 2) |

### Parked to Sprint 6

Per the broad review's revised order (`docs/ROADMAP.md` §6): lobby hardening to completion; the
online freeze root cause (3-17 s guest stops under host load, Task 1's launch 8c); single-player
teleports; the skeleton root decay (re-measured on the post-`vf0` exe first); a gameplay-state probe
as the gate's first correctness leg; the soft-double `exp` chain and `rem_pio2f` against exact
oracles; a mixed ours/PCSX2 match; HLE audit leg three; harness/gate process cleanup; the parity PNG
export off the GL thread; the display-environment/zbp A/B; VU memory aliasing; disk hygiene
automation. Also parked, and named as Sprint 7's headline item rather than Sprint 6's: **the close-
range aim loop has no ammo awareness or re-aim escalation** — round 4 fired 111 bursts at an
in-tolerance miss with no correction, which is exactly the repeatability gap `docs/KNOWN.md` §4
already flags (3 of 4 rounds killed; round 4 missed on an aim tolerance that never corrected).

## 2026-09-13 (local) — Sprint 4 landed: the online movement blocker fixed, the acceptance test built and NOT passed, Frostfire loses control at round start, and the first kill is Sprint 5's

Sprint `2026-09-12-sprint-4-visible-defects-and-first-kill`, branch `sprint-4`, Tasks 1-9 plus
2b, 4b and 4c added mid-sprint; each implemented, independently reviewed, fixed and re-reviewed.
Where reality diverged from the plan is in the plan's own `## Outcome` section; the findings that
outlive the sprint are in the 2026-09-13 "carried findings" entry immediately below; the headline
facts, and every retraction, are in `docs/KNOWN.md`. This entry is the outcome, stated without
flattery.

### The two sentences that matter

1. **The two-week online movement blocker is fixed.** Our HLE answered
   `sceInetInterfaceControl(0x200)` with a **constant**, so the guest's "ms since network activity"
   never reset and the multiplayer movement scale clamped to 0.0 on frame one; pitch survived only
   because it is not one of the three scaled axes (`abf35bb`). Proven by a **same-binary A/B in one
   match** (`5ed29ca`, `PS2X_SOCOM2_NET_STATS_B=0` turning the fix off for instance B only): fix ON,
   movement scale 1.0 on **330/330** calls and **89** distinct player positions; fix OFF, 0.0 on
   **339/339** and **0.46 units** of travel in the whole match. Proven **on Medley only**.
2. **The acceptance test did not reach a kill.** On the corrected measurement — the actor's own
   x/y/z, not the camera+facing reconstruction, which mis-placed players by up to ~50 units — the
   closest true 3-D separation the two players ever reached was **50.0 units**; over the last 400
   rows the median was **67.9** at **43.3°** of elevation, and **0 %** of rows were inside any
   contact gate (45 units in 3-D, 25, or within 10 of each other's height). The rifles fired (96 R1
   injections, ammo 30/30 → 0/30, impacts on the wall ahead of the muzzle) and hit nothing, because
   the players were never in range. **Whether damage was dealt is unknown**: the offsets watched at
   the time (`actor+0x204/+0x208`) were not health.

Not "frozen at round start". That description was retracted this sprint and must not come back:
**the round runs and the local player cannot move** — and on the two maps tried it has had two
different causes, one fixed and one open.

### What landed, in order

**Wave 1 — visible defects and a gate that cannot go quiet.**
- **Intro-movie black macroblocks: fixed at the root** (Task 1, `4a701f1`). Not the byte-accumulator
  case the plan predicted — the count it mandated measured that at zero — but a **cross-thread race
  on `m_currentTransfer`**: the game thread overwrote the transfer the GL mirror was about to mark,
  so the mirror refreshed someone else's rectangle and the real 16×16 block was never pushed. One
  deleted line. Transfer/refresh deficit **3,748 → 0**; `movie_blocks.py` `MISSING` **9 → 0**. The
  new check (`tools_py/parity/movie_blocks.py`, `docs/research/16` §9) went through four review
  rounds because each version could pass harder as the bug got worse; its remaining limits are in
  §9.1.1, and it is wired into nothing.
- **The gate's silent-failure paths closed.** `drive.py` crops the non-black rect before scoring
  (Task 2, `193ed92`, `a6f3cc4`): a deliberately pillarboxed run's title score went **0/23 → 18/23**
  instead of degrading quietly. The transition probe's burst now **follows the save dialog** instead
  of sitting at step 11 (Task 2b, `99c1865`, new `ifburst` script step): a late dialog used to leave
  the burst firing before the transition — too few frames examined, peak 0.
- **`--vram-diff` 15/15** (Task 3, `fc9f185`, `6c017c2`). Blend-amplified rounding and interior
  seams are classified by-design, `vu1dump4_prog_182` rejoins the fixture set at 0.000 %, and the
  seam clause is **budgeted** after review showed the unbudgeted widening made the oracle blind to a
  uniform one-pixel offset (+1 px x now fails 8/15, +1 px y 6/15; `seam=N` printed every run).
- **`rand()` is 31-bit over the guest's own seed** (Task 4b, `ede2096`, `60a19f2`). The stub had
  returned 15 host bits over a `_rand_next` frozen at 41, pinning every `rand`-derived float in the
  game (249 sites) within 1/65536 of its minimum. `docs/research/17` §6.1, including why a fixed
  clock would pin the seed and not the stream.
- **The soft-double ABI stubs re-bound** (Task 4c, `db7a992`): `sin`/`cos`/`tan`/`fabs`/`floor`
  take `$a0` and return `$v0`. A **latent** defect — identity at 19 of 22 sites, the 3 garbage
  sites unreachable — with three live divergences (`FUN_00308020`'s gimbal guard, `FUN_00294070`'s
  projection matrix, `FUN_003C7280`'s `tan`). `docs/research/17` §5.1.
- **"Ground height" reframed as the camera** (Task 4, `docs/research/17`). There is no ground-height
  defect: the player's feet match the console to **0.008**, and the 14.7/20.1 figures were
  camera-eye minus collision-hit. The third-person camera sits ~5.4 low because the player actor's
  skeleton root node decays 11.4845 → 0 while its saved copy holds the console's 5.50391.
  **Localised, not fixed**: two candidates (a lerp dropping its `a·w` term, or a second writer)
  that `research/17` §4.3's single run separates.

**Wave 2 — the online round.**
- **S0 (Task 5, `docs/research/18` §1): runtime implicated.** Two PCSX2 instances against **our own**
  Horizon stack play a full round and advance to round 2. The "PCSX2 golden is frozen too" belief
  that had pointed two weeks of work at the server was two stills of a match with no input sent.
- **S1 (Task 6): fixed**, per sentence 1 above, after five hypotheses were falsified by measurement
  — two of them real divergences whose fixes reached the wire and moved nothing (the advertised peer
  port and a shared RSA keypair, `acb603e`; both fixes kept).
- **S2 (Task 7, `research/18` §3.13): honest partial.** Movement and look calibrated; `--walk-to-b`
  steers and does not arrive — one mover cannot close Medley inside a round (38.6 % closure
  efficiency, ~450 s needed against a ~360 s round). It measured the aim floor: the harness sends
  only full stick deflection, so the shortest usable hold sweeps 35-40° against a body subtending
  15-20° at contact range (the pad file itself accepts 0-255 — a harness limit, not the runtime's).
- **S3 (Task 8, `research/18` §4): honest partial.** Both players walk (`--converge`, then
  `--until-kill`): **1485.5 → 50.0 units in ~127 s**, the first time two online players have been
  in the same place, and no kill (sentence 2). Review found the loop's own distance wrong by tens of
  units, rebuilt contact as 3-D plus height, and **reserved `RESULT PASS` for a kill**: a round
  ending on its clock prints `ROUND-END (unattributed -- NOT a kill)` and exits non-zero, and an
  armed health watch that read nothing fails the run. With no confirmed health offset,
  `--until-kill` **cannot currently print PASS** — the honest state of the instrument.

### Frostfire — the default test map, and neither player moved

The owner set the default test map to **Frostfire** on 2026-09-13 (`--map frostfire`, verified
against a reference crop of the highlighted row before CROSS is pressed; the harness previously
blind-pressed whatever was highlighted, which was Medley). Frostfire's spawns are **692 units
apart** against Medley's **1485**, with a 42-unit height difference. One run, `ours_task8_frost1`:
gameplay reached on both instances, pad reaching the guest, movement scale 1.0, round clock running
— and **neither player moved** (A's record spanned 2.5 units, B's 0.0, over 240 s). The move path
`FUN_00553dc0` ran **18 calls in 0.6 s** at round start and never again across 2634 sampler rows,
where Medley runs it ~18.9/s. That reads as **control never being handed over**, not as a slow map.
(A first reading of the same log said "about one a second": `PS2X_CALL_TRACE` logs the first 300
calls unconditionally, so dividing a short trace's line count by `EVERY` overstated it ~20×.)

**The movement fix above is proven on Medley and is not in question here; Frostfire is a second,
different cause.** One run cannot separate a map-specific defect from a match that never handed over
control, and nothing about the cause is proven yet.

### research/19 — community and engine resources

A research wave over community memory tools, reCOM and other recompilation/HLE projects
(`docs/research/19-community-and-engine-resources.md`, `7e81197`). Every address pinned to
SCUS_972.75 r0001:
- **Health is `actor+0x1044`** (float, 1.0 full, `<= 0` dead) and **`actor+0xF7A` is the alive
  byte** (1 = alive) — two independent community tools, one explicitly r0001, confirmed against our
  decomp's `<= 0.0` / `< 0.2` / `< 0.5` compares. **This retracts `+0x204/+0x208`.** Read in every
  image, ours and the console's; **not yet read live in an online match.**
- **The multiplayer round state is the `CZNetGame` object at `*0x437ce8`**: `total_mp_kills`,
  `mp_round_count`, `mp_game_over`, rounds won and alive per team, and the major/minor/"my"
  round-state bytes at `+0x113..+0x115` — a kill and round-end readout that needs no screenshot.
- **Bytes the game never initialises in that object read `0xAF` on ours and `0x00` on the
  console** — among them `+0xd2`, the flag behind "You are a ghost. You will play the next round as
  a real player", tested by five online routines. The object is allocated per map from our
  replacement heap, so the garbage can differ by map. **This is Sprint 5's first lead for
  Frostfire.** The divergence is measured; the causation is inference.
- Our valve pool sits **0x20 lower** than the console's, so community absolute addresses are right
  for PCSX2 and wrong for us — resolve through the pointer.

It also widens the carried HLE hazard below: a wrong value need not come from a stub at all —
memory the game never initialised, filled differently by our heap, is the same class.

### Not done, and why

- **No kill**, on either map (above). Sprint 5 is built on it.
- **The camera height is not fixed** — localised to one run's distance, deliberately not guessed.
- **The plan's final gate with run-vs-run title scores against `s3_head_1x` was not run** at
  close-out, which was barred from builds and game runs. The current binary's last full gate is PASS
  3/3 (`20260912_192900`); no runtime source changed after it.
- **`build.sh test` still runs no Python tests**, and `movie_blocks.py` is in no automation — both
  are Sprint 5 Task 0.

### New knobs and flags (documented in README "Build and run")

`PS2X_SOCOM2_NET_STATS` (default on; `0` restores the constant and reproduces the defect),
`PS2X_SOCOM2_NET_TRACE_ALL`, `PS2X_SOCOM2_RSA_KEY=b`, `PS2X_RUN_LOG`, and the driver-side
`PS2X_SOCOM2_NET_STATS_B` / `PS2X_SOCOM2_RSA_KEY_B` (instance B only); `online_match_ours.py`
`--converge`, `--until-kill`, `--engage`/`--engage-dy`, `--fight-seconds`, `--kill-timeout`,
`--map`/`--map-scan`, `--health-offset`/`--health-range`, `--no-route`; `drive.py`'s `ifburst`
script step; `python -m tools_py.parity.movie_blocks`.

## 2026-09-13 (local) — Sprint 4 carried findings: the HLE constant-value hazard, and the online-harness rules that cost a run each to learn

Sprint 4's per-task reports live in `.superpowers/sdd/2026-09-12-sprint-4-visible-defects-and-first-kill/`,
which is **gitignored and deleted at close-out**. This entry is the durable copy of the things in
them that outlive the sprint. It is not the "what landed" entry — that is separate. Headline facts
are in `docs/KNOWN.md`; the retractions are marked in place at `HANDOFF.md` item 0 / item 2, the
2026-09-10 20:10 and 2026-09-09 01:30 entries below, and the Sprint 4 spec §1.

### The cross-cutting finding: our HLE returns a constant where the guest expects a live value

**This is the most valuable thing in the sprint and it is a standing hazard, not an anecdote.**
Three defects found independently in three different subsystems turned out to be the same shape —
an HLE boundary handing the guest a value that does not move when the thing it represents moves:

| the HLE | what it returned | what the guest did with it |
|---|---|---|
| `rand()` (`0x00197740`) | `std::rand() & 0x7FFF` — 15 bits, from the **host** CRT, over a guest `_rand_next` frozen at **41** | every `rand`-derived float pinned to within 1/65536 of its minimum, at **249** sites (`grep -c 4.656613e-10` over the decomp). `+0x5c` could not exceed 4.0000458 where the console reads 6.3338 |
| `sceInetInterfaceControl(0x200)` | a constant | `msSinceNetActivity` never reset → the movement scale clamped to **0.0 on frame one**. This is the two-week "the online match is frozen" blocker; pitch survived only because it is not one of the three scaled axes |
| five soft-double routines (litodp/dpmul/dpdiv/exp/dptofp) | a **stale register** — the ABI binding returned `$v0` as it stood | identity at 19 of 22 sites and therefore invisible; genuinely wrong at three live ones, including a gimbal-lock guard that became a control-flow divergence (research/17 §5.1) |

Two properties make this worth a rule rather than three bug entries:

- **Each was invisible to the parity gate.** A frozen seed, a frozen clock and a stale register all
  render perfectly. The gate proves *no worse than the reference*; it has never proved *correct*.
- **Each presented as a game bug**, in a subsystem that had nothing to do with the real cause: a
  capsule radius, a peer-transport handshake, a movement throttle curve. Three sessions, a week of
  server work and a protocol decode were spent inside those wrong subsystems.

**The rule.** Presume remaining gameplay wrongness is this shape until shown otherwise. When a guest
value looks wrong, ask *what feeds it across an HLE boundary, and does that thing change?* before
reading any guest code. The cheap test is the one that caught all three: dump the suspect word from
several of our RDRAM images and from the PCSX2 console image — **a value identical across all of
ours and different on the console's is the signature**, and it costs no run at all. An HLE that
returns a constant is a defect even when nothing visibly breaks today, because the thing that
eventually reads it will be in a different subsystem from the stub.

### Harness rules from Tasks 6-8 — each of these cost at least one run

The online harness is expensive (budget ~two runs per result; the lobby flow reaches gameplay about
four times in ten) and it is very good at producing complete, convincing evidence of nothing.

- **Verify `peek @416054` is non-zero before believing any screenshot or any movement claim.** One
  run drove sixteen stick probes and wrote sixteen screenshots against a **lobby keyboard**; three
  of six runs in that task were unusable. Note the weaker form of the same rule: the liveness check
  counts *non-zero* position rows, not *distinct* ones, so it passes while the player is in-game and
  not yet controllable — `ours_task8_kill3` had 161 in-game rows, movement scale 1.0, and moved
  **0.00** units across a forward hold, a turn and a second forward hold.
- **An instrument that emits zero rows is a FAILED run, not a quiet one.** Task 6's idle-ms trace
  logged nothing for a whole session because it pointed at `0x30be80` while the guest calls the
  thunk at `0x30cd80` — inside the very task that had just written the warning about checks
  attesting to nothing. Zero rows means the instrument is wrong until proven otherwise.
- **A `MediusPlayerReport` in the Medius log is NOT a round end.** It is a periodic client stats
  report. In `ours_task8_kill1` exactly one arrived, at T+156.7 s, with the two players **603 units
  apart**, both still walking and no respawn in either position record — and the harness printed
  `RESULT PASS signal=server` for it. Any round-end signal must require something only a real round
  end produces; `KillWatch` now records the report and never fires on it.
- **A finished `drive.py` taskkills the NEXT run's game.** Its cleanup runs
  `taskkill /F /IM socom2.exe`, so an earlier driver reaching its own end takes down whatever is
  running now: `run_t8probe2` died 66 s in, its log froze at 127 sampler rows, and `drive.py` went
  on screenshotting a dead game for four more minutes. Kill the previous *driver*, not just the
  game, before starting anything.
- **One script per run.** The corollary of the above: overlapping drivers do not merely skew timing,
  they silently void each other's evidence, and the voided run still writes a full set of
  screenshots.

`docs/KNOWN.md` §4 carries these alongside the rest of the standing hazards.

## 2026-09-12 (local) — Sprint 3 landed: `PS2X_GS_SCALE` integer render-target scale (default 1), the fourth VU1 command family and `0x34` (162/166 native), family-C + fourth-family `--vram-diff` coverage, the intro-movie macroblocks localised

Sprint `2026-09-11-sprint-3-render-scale-and-fourth-family`, branch `sprint-3`, Tasks 1-11, each
implemented, independently reviewed, fixed and re-reviewed. Task 5's own S3-d verification entry is
immediately below this one and carries the 2x measurements in full; this entry is the sprint around
it and does not repeat them. What exists now:

- **`PS2X_PRESENT_FILTER=linear|integer|point`** (Task 1, `ps2_runtime.cpp` present block). **Verdict:
  at the 640x448 window the desktop build opens the fit scale is exactly 1.0, so all three modes are
  the same 1:1 blit and none of the perceived softness is presentation.** The default stays `linear`
  and is byte for byte the pre-knob behaviour on both the host and CPU present paths. The knob only
  bites on a stretched window, where it measures real (at 1818x1132: `linear` softest, `point`
  crispest but uneven, `integer` between them) — `python -m tools_py.parity.resize_window <w> <h>`
  was committed for driving that comparison. Gate stamps `pf2_linear` / `pf2_integer` / `pf2_point`,
  all PASS; sheet `logs/pf_runs/s05_sheet.png` (three identical pictures, as the arithmetic predicts).
- **Render-target scale, in four independently shipped stages (Tasks 2-5).**
  *S3-a:* `RenderTarget`'s single size field split into `nativeWidth/nativeHeight` and
  `hostWidth/hostHeight`, with all **37 read sites / 50 field references** classified site by site in
  `docs/research/14-gs-render-target-scale-spike.md` §8 and **seven** native/host hand-offs recorded
  in §8.1 for the later stages. The audit caught research/14 §3 classifying `getDepthTarget`'s size
  as native: following that would have given an incomplete FBO and a black screen at S > 1.
  *S3-b:* a per-target native mirror plus a GPU resolve behind `nativeView()` / `nativeViewFbo()`,
  with `PS2X_GS_SCALE_FILTER=point|box` (`point` = a `GL_NEAREST` blit, `box` = an SxS average);
  inert at 1x by an early return, so it allocates and copies nothing there.
  *S3-c:* **`PS2X_GS_SCALE`, default 1, clamped 1..4**, every `* S` site listed in research/14 §10.2.
  *S3-d:* verification (the entry below).
  **At 1x nothing observable changed at any stage:** a full gate PASS 3/3 after every one of them,
  and every title capture 99.8-100.0 run-vs-run against the pre-scale S3-a baseline
  `logs/parity/gate/s3a` — against a bar of >= 99, and with no capture anywhere in the sprint's 1x
  gates below 99.7 (the attract-movie captures s20-s22 are exempt: they are playback-phase dependent
  and span 85.5-100.0 between any two runs, modified or not). The one number
  that argued otherwise — a transition `rows 396-447 peak 7` — was settled by a ten-run interleaved
  A/B of the parent and scaled binaries: the artefact is run-to-run variance present on the
  **pre-scale** binary too (see the flake list below), and the three peak-7 `w13_001.png` captures
  are byte-identical PNGs across a Task 3 binary and the S3-c binary.
  **At 2x:** `s3d_2x_host` GATE PASS 3/3; the GIF path green on all three legs but **across two
  stamps** — `s3d_2x_gif` (title + mission) and `s3d_2x_gif_t2` (transition, re-run after a
  documented save-dialog probe flake) — so it has *not* passed 3/3 in a single run. The resolve path
  itself was checked directly with `PS2X_GS_SCALE_SELFTEST=1` on full gameplay runs, because no gate
  capture at any scale goes through it: **0 stale mirror reads** under each filter (11,704 reads
  served from an already-clean mirror across the two runs) and 0 of 229,376 x 24 content samples
  outside their host block, `point` `logs/run_20260912_074912.log` and `box`
  `logs/run_20260912_075604.log`.
  **The headline, stated precisely: 2x gives sharper 3D rasterisation and does NOT sharpen the HUD,
  menus or title.** Those are textured quads drawn from native-resolution textures (`uTexSize` stays
  native by design), so scaling the render target cannot add detail to them. Measured on a matched
  mission frame: 3D-region gradient **5.88 -> 3.98** with anti-aliasing fraction **0.133 -> 0.423**,
  against a flat HUD whose glyph raster is identical at 4x zoom. Do not write "2x is sharper"
  unqualified.
  **`S=3` and `S=4` are deliberately untested.** The clamp admits them, but at S=4 a colour target is
  67 MB and `getDepthTarget`'s zero-fill is a 67 MB one-off per ZBP. Documented as a known limit, not
  as tested behaviour.
  Sheets and stamps: `logs/parity/gate/s3c_1x_final/mission_sheet.png` (1x, the default-knob gate),
  `logs/parity/gate/s3d_2x_host/mission_sheet.png` and `logs/parity/gate/s3d_2x_gif/mission_sheet.png`
  (2x), transition from `logs/parity/gate/s3d_2x_gif_t2/`.
- **The VU1 dispatcher went 123/166 -> 162/166 native (Tasks 6-8).** `docs/research/15-vu1-fourth-family.md`
  decodes the fourth command family (`0x70`, `0x52`, `0x66`, `0x40`) and `0x34` to implementation
  level; then native handlers for `0x70` and `0x40` (dump3 `ended` 9 -> 47) and for `0x34`'s
  sphere-map ST and rim alpha (-> 48), each bit-exact against exact-interpreter goldens with
  `--regs all`. Per dump set, entered/ended/handbacks: **dump2 31/31/0, dump3 52/48/4, dump4 83/83/0**.
  **The residual is 4 programs**, all the `52 66 08 40 42` shape: `0x52` emits no GIF packets, ends
  the program (E bit `0x33b8`, end pc `0x33c8`) and its correctness spans two `MSCAL`s, and `0x66` is
  never dispatched from `0x1b50` anywhere in the corpus, so a handler for it could not be verified and
  shipping an unverifiable handler inside the dispatcher was judged the larger risk. That residual is
  a deliberate, documented ruling, not an unfinished task. Gate `fam4` PASS 3/3 after the fourth-family
  handlers; `0x34` needed no gate (no shared path changes behaviour, proven by the unchanged counts).
- **`--vram-diff` went from `checked=10 skipped=2` to `checked=14 skipped=0` (Task 9)**, covering
  family C **and** the fourth family. Diagnosis: the family-C lists' own render-state packets point
  `TEX0` at a texture the dump does not carry, so every texel read back 0 and their `ALPHA_1 = 0x44`
  (`(Cs - Cd) * As + Cd`, `As = 0`) left the framebuffer untouched — the draws happened and wrote
  nothing distinguishable from "not drawn". `vu1_replay` now neutral-fills VRAM outside the frame and
  z buffers, gives the z buffer its own pages, `static_assert`s that the parked texel stays above the
  zeroed region, and warns when a kicked packet points `TEX0` inside it. **`./build.sh test` now fails
  on that warning** instead of letting it scroll past. All ten pre-existing `VRAMDIFF` lines are
  numerically identical before and after. One dump, `vu1dump4_prog_182` (1.488 %), is held out with
  pixel evidence: `hard` misclassifies blend-amplified gouraud rounding (delta 2, not 1) and one-pixel
  shifts of *interior* seams; widening those two buckets — then adding the dump — is a Sprint 4
  follow-up, deliberately not done here because it changes what the check scores.
- **The intro-movie black macroblocks are localised** (Task 10, `docs/research/16-intro-movie-macroblocks.md`),
  at 4-5 % of movie frames with 1-4 blocks each. **The MPEG decode is clean**: 2067 consecutive decoded
  pictures have exactly the black-macroblock census of an offline libavcodec decode of the same file
  (mean |count diff| 0.000), and the guest strip write has no skip path. The loss is in the shadow-VRAM
  -> GL-render-target mirror — `executeUpload` -> `refreshRenderTargetsFromShadow` -> `refreshDirtyRows`
  in `gs_gl_backend.cpp` — with three-layer `PS2X_GS_DUMP_DISPLAY` triples showing shadow 0/48 presents
  affected against the GL target's 3/48, and the exact pictures and block coordinates named in the note.
  **No fix**, correctly under the spike's decision rule: the candidate sits in the file the scale work
  was rewriting, and confirming it needs a transfer-vs-refresh count first.

**Known flakes and harness notes, new this sprint.**

- **Transition gate, intermittency 1 — measured.** Roughly **1 in 5** `--only transition` runs FAIL on
  a one-frame dim residual strip at rows 396-447 in an otherwise black sequence. It is **pre-existing
  and not a scale regression**: a five-pair interleaved A/B of the pre-scale parent binary and the
  scaled branch failed once on each side, the **parent's** instance being the worse of the two
  (parent peak 36, scaled branch peak 18), and counting every stamp on record the rates are
  indistinguishable (Fisher exact p ~ 0.6).
- **Transition gate, intermittency 1's cause — a hypothesis, with no isolation test behind it.** It is
  attributed to `refreshDirtyRows` / `executeClear` ordering because that is the class of artefact the
  ordering fix exists to suppress. Nothing has been run to isolate it; treat the attribution as
  unproven and the ~1-in-5 rate as the measured part.
- **Transition gate, intermittency 2 — the already-known save-dialog probe flake.** `transition_probe.txt`'s
  `ifref` guards match several steps late, the burst runs before the dialog is answered, and the leg
  FAILs for too few frames *examined* with every examined frame at peak 0. Distinguish the two by the
  band peak: **peak 0 with too few frames is (2); a non-zero band peak is (1)**.
- **Harness: 1x and 2x frames must be matched by content, never by step name.** At 2x the mission-load
  `untilref` press loop needs one extra press, which shifts every later step by ~21 s; every step up to
  that point lands within 0.3 s across scales. Comparing `sNN` to `sNN` across scales compares different
  moments and manufactures a spurious regression.
- **The title gate can be silently degraded by a window resize from outside the process** (seen twice in
  Task 1, once taking a 19/23 run to 16/23 — one step off a red gate with a green binary): `drive.py`'s
  `untilref`/`ifref` references are 640x448 frames and never match a pillarboxed window. Cropping to the
  non-black rectangle before the 160x112 resize would fix it.

**Where reality diverged from the plan.**

- Plan Task 7 was scoped as "the fourth-family handlers" generally; the controller ruled it down to
  **`0x70` and `0x40` only**, leaving `0x52` and `0x66` as the documented residual above (research/15
  §9.3). Plan Task 8's `0x34` then landed, so the residual is 4 programs rather than the 5 Task 7 left.
- **The spec's "sharper HUD" expectation was wrong.** Plan Task 5 Step 1 asked for "the HUD text and
  squad panel must be visibly sharper" at 2x. They are not, and cannot be: `uTexSize` stays native, so
  a screen-aligned textured quad is magnified from a native texture and minified straight back. Task 4
  predicted this before it was measured; Task 5 measured it. The gain is in rasterisation only.
- research/14's headline "15 touch points" (quoted in the Sprint 2 entry below) is superseded: the
  authoritative figure for the refactor is **37 read sites / 50 field references**, in research/14 §8.
- Task 10's PCSX2 comparison run was never made (the lock was taken and this task had lowest priority);
  the offline libavcodec decode is a stricter reference and is what the conclusion rests on.

## 2026-09-12 (local) — Sprint 3, Task 5 (S3-d): `PS2X_GS_SCALE=2` verified on both draw paths — sharper geometry, unchanged HUD, **default stays 1**

`PS2X_GS_SCALE=2` was run through the full gate twice on the S3-c binary (`466918b`, no source
change in this task) and through the resolve self-test twice, once per filter.

**Gates.** `s3d_2x_host` (`PS2X_GS_SCALE=2 PS2X_VU1_HOST_DRAW=1 PS2X_VU_STATS=1`) — **GATE PASS
3/3**: title 19/23, transition 17 frames examined at/after the burst step with rows 396-447 peak 0,
mission HUD reached with 6 hold steps. `s3d_2x_gif` (`PS2X_GS_SCALE=2`, host-draw off, i.e. scaled
rasterisation of GIF-path triangles) — title PASS, mission PASS, transition FAIL on the **documented
save-dialog probe flake** (4 frames examined, need 5; `ref_save_prompt_ours.png` matched at s12/s13
instead of s08/s09, and every examined frame peak 0 — the probe arrived late, nothing was drawn into
the band). Re-run of that leg alone, `s3d_2x_gif_t2`: **PASS** — 17 frames examined, rows 396-447
peak 0, the save-dialog `ifref` matching at the early position again. **So the GIF path is green
on all three legs across two stamps** (`s3d_2x_gif` title + mission, `s3d_2x_gif_t2` transition);
it did not pass 3/3 in one go, `s3d_2x_host` did. The two 2x runs agree with each other —
same step, same scene, `compare.score` 99.8 / mad 0.0043 — so the two draw paths rasterise the same
picture at 2x.

**Presentation is inert.** Each 2x title capture scored against its 1x twin in `s3c_1x_final/title`:
s00-s19 **99.6-99.9** (host-draw) and **99.8-99.9** (GIF). The title screen is a render-target-as-
texture display copy sampled at native resolution, so it neither gains nor loses at 2x; research/14
§10.5 also records that a 2x title run performs **no** guest-visible render-target read at all, so
the title leg is a presentation-and-inertness check and proves nothing about the mirror.

**The resolve path, checked directly** (`PS2X_GS_SCALE_SELFTEST=1`, full `gameplay_probe.txt` runs,
because no gate capture at any scale goes through the resolve — the parity captures are
`LoadImageFromScreen()` window screenshots):

| filter | run log | native-view reads | served from an already-clean mirror | STALE | lit content windows (after a resolve / served clean) | samples outside the host block range |
|---|---|---|---|---|---|---|
| `point` | `logs/run_20260912_074912.log` | 39,000+ | 6,352 | **0** | 24 (12 / 12) | **0** of 229,376 x 24 |
| `box` | `logs/run_20260912_075604.log` | 33,000+ | 5,352 | **0** | 24 (12 / 12) | **0** of 229,376 x 24 |

**Sharpness, measured and looked at.** The >= 99 title bar does not apply at 2x, so: mean gradient
energy (`grad`, the Sprint-3 review's metric) plus an anti-aliasing fraction (`aa` — of the pixels
on a real edge, the fraction that are partially covered rather than a hard step; supersampling
raises it). On the matched mission-start frame (1x `s3c_1x_final/mission/s28_none.png` vs 2x
`s3d_2x_host/mission/s29_none.png`), over the 3D region: grad **5.88 -> 3.98**, aa **0.133 ->
0.423**. Same direction on a genuinely identical cutscene frame (grad 7.69 -> 5.79, aa 0.267 ->
0.402), and at population level every 2x gameplay capture scores aa >= 0.419 while 13 of 14 1x
captures score <= 0.32. By eye at 4x zoom the difference is obvious: 1x foliage is stippled with
isolated pixels and hard alpha-test staircases, 2x foliage has continuous edges.

**But the HUD is not sharper, and that is the honest half of the result.** Over the squad panel and
the ammo panel — opaque-backed, fixed-position, directly comparable — grad moves 19.37 -> 20.04 and
10.04 -> 9.54 and aa moves +0.03, i.e. nothing; at 4x zoom the glyphs are the same raster with the
same stair-steps. `uTexSize` stays native by design, so a screen-aligned textured quad is magnified
from a native texture into the 2x target and minified straight back at present. **2x buys
rasterisation, and SOCOM II's HUD, menus, briefings and title are not rasterisation.** (Beware the
radar crop: it appears to improve a lot, but the improvement is the 3D foliage behind the
translucent ring, not the ring.)

**Verdict: `PS2X_GS_SCALE=2` works, is worth having for gameplay, and the default stays 1.** Sheets:
`logs/parity/gate/s3d_2x_host/mission_sheet.png` and `logs/parity/gate/s3d_2x_gif/mission_sheet.png`
against `logs/parity/gate/s3c_1x_final/mission_sheet.png` (structurally identical; sheet tiles are
~60 px and cannot show aliasing — the sharpness judgement is on full-size frames). `S=3` and `S=4`
remain deliberately untested. 1x is unchanged and is `s3c_1x_final`, GATE PASS 3/3, cited not re-run.

**Two gate intermittencies, recorded here for the first time**, both scale-independent and neither
in the flake list until now: (a) the **save-dialog probe flake** — `transition_probe.txt`'s `ifref`
guard matches several steps late, the burst runs before the dialog is answered, and the leg FAILs
for too few frames *examined* (seen at 1x in Task 4's `s3c_1x`, and here in `s3d_2x_gif`); (b) the
**residual-strip artefact** — a one-frame dim strip at rows 396-447 in an otherwise black sequence,
~1 transition gate in 5 on **both** the S3-b parent binary (peak 36) and the S3-c binary (peak 18),
attributed to `refreshDirtyRows` / `executeClear` ordering. (b) did not fire in any of this task's
transition legs. A FAIL with peak 0 is (a); a FAIL with a non-zero band peak is (b).

**Also measured, because it will confuse the next person:** scripted probes drift at 2x. Every step
through s27 lands within 0.3 s of the 1x run; the mission-load `untilref` then needs 4 presses at 2x
instead of 3, which shifts everything after it by ~21 s (s34 at 216.0-217.7 s vs 196.1 s at 1x —
inside the 196.1-218.3 s band 1x runs already show). The same scripted inputs therefore land later
in game time and both 2x mission runs ended in MISSION FAILURE where the 1x run's last capture was
already showing "Leaving designated mission area". Match 1x and 2x frames by content, never by `sNN`.

## 2026-09-12 (local) — Sprint 3, Task 1 (S3-0): `PS2X_PRESENT_FILTER` — the presentation stretch is not where the softness comes from at the shipped window size

`PS2X_PRESENT_FILTER=linear|integer|point` (read once, `ps2_runtime.cpp` present block) picks how
the presented PS2 frame reaches the window: `linear` is the default and byte for byte what the
code did before the knob (one aspect-fit `DrawTexturePro` per read circuit, sampler state left as
whoever created the texture set it — GL_LINEAR for the host render-target copy, GL_NEAREST for the
CPU fallback); `point` samples nearest straight to the window; `integer` point-samples the frame
into an off-screen stage at k = floor(fit scale) times its size and then fits that stage with
linear filtering. Both branches draw the read circuits identically — circuit 1 unblended (the GS
frame's alpha is game data) and the optional PMODE circuit 2 alpha-blended over it — only into a
different target; the `integer` branch's final stage-to-window draw is unblended for the same
reason circuit 1 is.

**Verdict.** At the window the desktop build opens, and for as long as the game presents a full
frame, the knob cannot change a pixel and none of the perceived softness is presentation. The
desktop window is created at `HOST_WINDOW_WIDTH x HOST_WINDOW_HEIGHT` = 640x448
(`ps2_runtime.cpp:45-56`), exactly the frame the title screens present, so the aspect-fit scale is
1.0, k = 1 and all three modes reduce to the same 1:1 identity blit. Two edges to that statement:
`PLATFORM_VITA` opens 960x544, where the scale is 1.21 and the knob does bite; and the fit is
computed from `presentWidth/presentHeight`, which come from the live host texture, so a game state
that presents a rect smaller than 640x448 is also being scaled. Both are outside what the title
gate exercises -- the claim is measured for the desktop build on the screens the gate reaches, not
proved for every frame the game can produce. The measurements agree: title gates `pf_linear`,
`pf_integer` and `pf_point` are all PASS 19/23 with per-capture scores equal to within run noise,
and the three-mode s05 sheet is three identical pictures. The softness on those screens is the
render resolution itself, which is what `PS2X_GS_SCALE` (Tasks 2-5) attacks — this experiment does not
buy any of it back. The knob only bites on a stretched window, and there it measures real: the
same screen captured in all three modes at a 1818x1132 window (fit scale 2.53, k = 2) shows
`linear` softest (every glyph edge a 2-3 pixel ramp), `point` crispest but visibly uneven (a
source pixel lands on 2 or 3 window pixels, so stroke widths wobble and letterforms stair-step),
and `integer` between them — 1-pixel edges with even stroke weight, `point`'s crispness (edge
gradient energy 1.058 vs `linear`'s 1.007, `point`'s 1.057) without its unevenness, 0.44/255 mean
absolute difference from `linear` over the whole frame. **The default stays `linear`**: it is
identical to `integer` at the size the game actually opens at, and the sprint's render-target
scale is the change that matters. `integer` is the one to reach for the moment the window is bigger than the frame -- which is
one drag away, since the window already carries `FLAG_WINDOW_RESIZABLE`.

Gate stamps: `pf_linear` / `pf_integer` / `pf_point`, each `--only title`, each GATE PASS;
`pf_linear`'s menu captures s00..s19 score 99.7-99.9 against `hostdraw_fix/title` (its three
attract-movie captures s20..s22 score 85.5-88.6, inside the 85.5-100.0 band that any two
unmodified runs of this gate show on those frames — the movie is at a different playback phase,
confirmed by eye). The stretched-window captures come from `pfwin_linear` / `pfwin_integer` /
`pfwin_point`, which FAIL the title gate for a harness reason, not a rendering one: `drive.py`'s
`untilref`/`ifref` references are 640x448 frames, and a pillarboxed 1818x1132 window never matches
them at 160x112, so the probe stalls on the controller-configuration "select memory card slot"
dialog and captures that screen 23 times. `python -m tools_py.parity.resize_window <w> <h>` is
that helper, kept for whoever revisits this. After the review fixes (the PMODE overlay texture now
takes the mode's filter too, a guard on a failed stage allocation, a warning on an unrecognised
value) the three title gates were re-run as `pf2_linear` / `pf2_integer` / `pf2_point`, all PASS
19/23, and `pf2_linear`'s menu captures still score 99.7-99.9 against `hostdraw_fix/title`. **Open, worth a look:** the window is resizable and one
run (`pf_point_stuck`) came up at 1818x1132 with nothing in the run asking for it, and so failed
the title gate the same way; the re-run at the default size passed. A gate that can be silently
defeated by a window resize is a gate weakness.

## 2026-09-11 03:45 (local) — Sprint 2 landed: host-space triangle draw behind a knob, family B and C native (123/166), gates hardened and deterministic on a fresh clone
Sprint `2026-09-11-sprint-2-host-render-and-family-b`, branch `sprint-2`, Tasks 1-11, all reviewed.
What exists now:

- **Host-space draw hook.** `GS::submitHostTriangle(const GSPrimReg&, const GSVertex&, const GSVertex&, const GSVertex&)` (gs_frontend.h/.cpp) fills draw state from the live GS context exactly as `buildDrawBatch` does (shared `fillDrawState`) and submits the caller's float vertices straight to the backend; `VU1Interpreter::activeGs()` exposes the GS the dispatcher is running against. Unit tests prove it draws the same pixels as three XYZ2 kicks and honours `prim.ctxt` (Task 1).
- **`PS2X_VU1_HOST_DRAW`.** The native `0x28` packet builder in `socom2_dispatch_0x1b50.cpp` submits each triangle through the hook instead of packing/kicking it when the knob is set (default off — GIF packets still built and kicked otherwise, so every existing golden keeps proving the GIF path); every data-memory write and register update the GIF path performs still happens, so `--regs all` stays identical with the knob on. `vu1_replay --host-draw` sets the env for offline verification; `vu1_replay --no-native` forces the interpreted path for comparison; `vu1_replay --vram-diff <outdir> [--vram-tol <pct>]` re-execs itself once per mode per dump (two processes, since the knob is a read-once static) and diffs the rendered VRAM region, with SKIP accounting for dumps that draw nothing (drawn=0). `./build.sh test` runs the vram-diff check on the dispatch_0x1b50 fixtures (Tasks 2, 7).
- **Render-target scale: NO-GO this sprint.** `docs/research/14-gs-render-target-scale-spike.md` enumerates 15 places the GL backend assumes GS pixels are 1:1 with GL texels (**corrected by Sprint 3 Task 2: the authoritative count is 37 read sites / 50 field references, research/14 §8 — the "15" was never reproducible from the document and is superseded**); both readback paths (RT-to-shadow-VRAM and the title-label texture-set page copies) need a content-altering downsample filter, so `PS2X_GS_SCALE` is deferred to Sprint 3 (RenderTarget size refactor first, a presentation-upscale filter as the cheap win in the meantime) (Task 3).
- **Family B and C native.** `docs/research/13-vu1-family-b-world-objects.md` documents the `0x3618` primitive subroutine and every family-B/C handler. The dispatcher now runs 123/166 lists native across dump2/3/4 (dump2 31/0, dump3 9/43, dump4 83/0 ended/handbacks), bit-exact against the exact-interpreter goldens (`--regs all`). Residual: one 0x34 list (EFU maths plus a same-lane write conflict) and 42 dump3 lists using commands this dispatcher does not implement at all (0x70/0x52/0x66/0x40 — a fourth command family, left for Sprint 3 research) (Tasks 4-6).
- **Per-handler clamps.** Every handler that reads a loop count from the header or the primitive-index list clamps against the measured header maxima (`tools_py/vu1_headers.py`: dump2 50/31, dump3 78/73, dump4 76/44, all well under the 256/256 ceilings) and hands back safely on violation; a synthetic test (`TOP+2.z` rewritten to 300) proves the hand-back matches an exact golden of the modified dump, run by `./build.sh test` (Task 7).
- **Gate hardening.** `drive.py` captures `w{i:02d}_{k:03d}.png` every second during settle waits (not just during scripted bursts); `black_rows.py` counts them alongside `s*.png`. `tests/fixtures/gate/{title,transition,mission}` are committed (title 16 frames, transition 5, mission good/bad `.drive.txt`), so `python -m unittest tools_py.tests.test_gate` (24 tests) runs its positive cases on a fresh clone with no prior run needed. `PS2X_TEST_REPEAT=N ./build.sh test` runs the unit suite N times (5/5 green; no flake reproduced) (Tasks 8-10).
- **The transition gate was vacuous between `wcap1` and the final fix wave, and is now enforced.** The controller-configuration "save to memory card?" dialog started appearing on boot; `gameplay_probe.txt` guards it with `ifref` pairs and `transition_probe.txt` did not, so the transition probe stalled on the dialog and never reached the briefing - while `black_rows.py` counted black frames from anywhere in the run, so the boot's own black screens kept the gate green. Every transition run in that window examined **0** frames at or after its burst step and would now FAIL: `wcap1` (10 black frames, 0 after), `wcap2` (13/0), `famb` (11/0), `famc` (10/0), `hostdraw_on` (11/0), `hostdraw_fix` (9/0). Fixed by porting `gameplay_probe.txt`'s guard pairs into `transition_probe.txt` and putting its burst on the NO press (the press that takes the game to the black screen before the briefing); `black_rows.py --from-step N`, `gate.first_burst_step()` and `score_transition` now examine ONLY frames from that step on. Recalibrated on two consecutive clean runs of the fixed probe, `tfix3` (18 frames at/after the burst step) and `tfix4` (17), both peak 0; `TRANSITION_MIN_FRAMES` stays 5 and `tests/fixtures/gate/transition` is regenerated from `tfix4`'s post-burst frames.
- **Gates.** Last full gate run: title / transition / mission PASS 3/3 (stamps `hostdraw_on`, `famb`, `famc`); the mission HUD with `PS2X_VU1_HOST_DRAW=1` scores >= 95 against the native-default sheet.

Known open, carried forward:
- ~~**Host-draw has no family-C coverage in `--vram-diff`**~~ — closed by Sprint 3 Task 9: the family-C render-state packets pointed TEX0 at a texture the dump does not carry, so every texel read back 0 and their `ALPHA_1 = 0x44` (`(Cs - Cd) * As + Cd`, `As = 0`) left the framebuffer untouched. `vu1_replay` now neutral-fills VRAM outside the frame and z buffers and gives the z buffer its own pages; `checked=14 skipped=0`. **Residual:** `hard` misclassifies two by-design differences on alpha-blended draws — blend-amplified gouraud rounding (max delta 2, not 1) and one-pixel shifts of *interior* seams between adjacent triangles (7-22 steps, drawn in both renderings so not a coverage boundary). `vu1dump4_prog_182` scores 1.488% for exactly those two reasons and is not in the fixture set.
- **Mid-list hand-backs are bit-exact only because no FMAND sits within four pairs of `0x1b60`** in the current fixture/dump set — a program that branches on flags in that window is unverified.
- **Black 16x16 squares on the intro movie** (user report, goal-3 item, not a gate) — unchanged from Sprint 1.
- **Intro-cinematic freeze seen once** (Sprint 1, mission gate run `mission3`) — not reproduced again, still open under goal 3.
- **Flaky VSync scheduler-stop test** — not reproduced in 5 `PS2X_TEST_REPEAT` runs this sprint; kept on watch rather than closed.

## 2026-09-11 00:45 (local) — Sprint 1 landed: the project is testable (`./build.sh test` + one gate command) and the first hand-written native VU1 program (the 0x1b50 dispatcher) is on by default
Sprint `2026-09-10-sprint-1-hygiene-and-native-render`, branch `sprint-1`, Tasks 1-8 plus this
review/fix wave. What exists now:

- **Own repo.** The project is its own git repo, remote `github.com/Scotho/socom-unzipped`.
- **Unit tests.** `ps2x_tests` links and runs under llvm-mingw (`-Wl,--stack`, SOCOM runner link
  stubs): **428/428 pass**, run by `./build.sh test`.
- **VU1 fixture verification.** `dist/vu1_replay.exe --verify <golden> [--native|--no-native]`
  replays committed dumps and compares packets *and* the whole register/data-memory state against
  a golden file. Two fixture sets: `tests/fixtures/vu1/title` (12 title-screen dumps, entry pc 0)
  and `tests/fixtures/vu1/dispatch_0x1b50`. `./build.sh test` runs both sets on both paths.
- **One gate command.** `python -m tools_py.parity.gate` drives the three screenshot scripts and
  scores them numerically: **title / transition / mission, each PASS or FAIL**, non-zero exit on
  any FAIL. It launches `dist/socom2.exe`, so `./build.sh runtime` must precede it — `./build.sh
  test` does not rebuild the exe.
- **Freeze rules.** Emulator speed work (VU1/VU0 interpreter, scheduler batching, GS/GL caching
  and upload performance) is FROZEN for this sprint; 36-42 fps single instance is enough, and the
  two-instance frame rate is a test-rig concern (run the second client in PCSX2). Recorded in
  `docs/LOOP_PROMPT.md` (goal 2) and `docs/HANDOFF.md`.
- **research/12.** `docs/research/12-vu1-entry0-ui-path.md` plus its §f dispatcher addendum:
  microcode **entry 0 is a trivial upload stub**; the program that actually draws is the command
  dispatcher at **entry pc 0x1b50** of image `d418194495c25213`. §f documents the command
  encoding, register roles, the staging array and the hand-back rules.
- **Native registry + the 0x1b50 program.** A registry keyed by (microcode FNV hash, entry pc)
  sits in front of the generated-code dispatch; `socom2_dispatch_0x1b50.cpp` implements the
  dispatcher and all seven **family-A** (UI quad / 2D) handlers natively: **76/76 family-A lists
  run native across dump2/3/4, bit-exact** (packets, registers and VU data memory identical to
  the interpreter). Family B and C lists hand back whole at 0x1b50. It is **on by default**
  (`kVu1NativeDefault`); `PS2X_VU1_NATIVE=0` reverts to the generated/interpreted path.
- **Gate green with native on**: title PASS (19/23 menu captures over threshold), transition PASS,
  mission PASS; in-game `[vu1-stats]` shows `native-ended/s` ~3-9k during gameplay.

Open items carried out of the sprint:
- **Family B/C handlers → Sprint 2.** Family B keeps vi12 (the primitive counter) live across the
  dispatcher back-edge, so mid-list hand-back is unsafe (research/12 §f.3); family C is untouched.
- **The transition gate only captures during drive.py's bursts**, so how many black-screen frames
  a run yields is capture luck, not rendering — the floor is 1. Durable fix: capture during the
  settle waits in drive.py.
- **Intro-cinematic freeze seen once** (mission gate run `mission3`: identical frames s29-s41, no
  fault in the game log; `mission4` played it). 1 in 2 runs. Investigate under goal 3.
- **Flaky VSync scheduler-stop test** (`ps2_runtime_interrupt_tests.cpp`, 80 ms wall-clock
  `waitUntil`) made `./build.sh test` non-deterministic; the budget is now 2000 ms, assertions
  unchanged.

## 2026-09-10 20:35 (local) — peer packets decoded (probe10): the peer transport is ALIVE (acked, sequenced 22-byte packets, ~1/s), not SCERT-framed and not encrypted; the freeze is above the transport
Run ours_match_probe10 (net trace with `udp peer send/recv` hex). Every peer packet has the same
22-byte shape, little-endian: `00 01 0a 00 | 00 00 00 00 | 00 00 00 00 | T 00 02 00 | S 00 Q 00 | P 00`
with T = 0x81 / 0x82 / 0x89 (message type), S = sender index (0 = A the host, 1 = B), Q = a
per-sender sequence number (A 0x3f, 0x40, 0x41..; B 0x30, 0x31..), P = a small payload word
(A always 0x0a; B 0x00 for 0x82, 0x0c/0x05 for 0x89/0x81). The two sides alternate: A 0x81 ->
B 0x82 (ack) ; A 0x89, 0x81 -> B 0x82, 0x81 ; ... at one packet per second each way, every
packet answered. So the game's own P2P reliable channel is up and both peers see each other;
nothing here is an RT_MSG (SCERT) frame and there is no crypto handshake — hypothesis (1) of the
20:10 entry (shared RSA key) is ruled out. What is missing is the game-state stream that a
running round would put on this channel, so the blocker is game logic: the round's "go" (or
the local player's control enable) is never reached on either side, while the HUD timer runs.
Note A also sends the first packet to its own address (192.168.2.10:3658) — the player list
includes itself; harmless.
Next (in order): (a) find the P2P protocol code: grep the decomp/generated code for the header
words (0x00000a0100 / the 0x81/0x82/0x89 type dispatch) or trace the callers of the libnetb_ex
UDP send (FUN_00247fe8) and recv (exUdpRecv's guest caller) with PS2X_CALL_TRACE +
PS2X_CALL_TRACE_DUMP to see the sender's state machine and what 0x81/0x89 carry (0x0a vs 0x05/
0x0c payloads look like state codes: "loading", "ready"?); (b) the local control gate: the pad
floats at pad+0x210.. are produced (RY works), so find the actor/controller flag that ignores
LX/LY/RX online (compare the player actor's state word +0x10 in an online spawn vs the
single-player spawn, 0x6691a0 vtable, PS2X_PEEK on both); (c) if (a) shows a "waiting for
players" state, check what the 1.50 client expects from the host over this channel at round
start (the host is our own instance A, so both ends are ours: trace both).
Session hygiene: the loop cron was stopped and the run lock released at the end of this session;
the run recipe is logs/run_match_probe10.sh (PS2X_SOCOM2_SERVER=192.168.2.10, NET_TRACE,
INPUT_TRACE, PEEK 0x416054:3; --existing-b --hold 60).

## 2026-09-10 20:10 (local) — ~~ONLINE MATCH IS FROZEN AT ROUND START~~ (RETRACTED, see below) on both instances: only camera pitch and fire respond; peer UDP runs at ~1 packet/s (a handshake that never completes), not a game-state stream. Pad-state file injection replaces posted keys.

> **Superseded by `docs/research/18-online-round-start.md` §1 and §4, and FIXED (Sprint 4 Tasks 5-6,
> `abf35bb` + `5ed29ca`).** The match was never frozen and no peer handshake was ever missing.
> **The round runs and the local player cannot move** — that is the whole symptom, and it is local.
> Two facts in this very entry said so and were read past: "the HUD timer runs regardless" (line
> below), and RY working while RX/LX/LY did not — a *transport* failure cannot deliver pitch and
> withhold yaw.
>
> Cause: `sceInetInterfaceControl(0x200)` was HLE'd to a **constant**, so the guest's
> `msSinceNetActivity` never reset and the movement scale clamped to 0.0 on frame one; pitch is not
> one of the three scaled axes. Same-binary A/B in one match (`5ed29ca`): fix ON `MoveScale f12 =
> 1.0` on 330/330 calls, idle max 1490 ms, 89 distinct player x; fix OFF `f12 = 0.0` on 339/339,
> idle 504,210 ms, **0.46 units** of travel.
>
> Retracted with it: **"the PCSX2 golden match is the same frozen state"** (`HANDOFF.md`'s open
> item 0). Two PCSX2 instances against our own Horizon stack play a full round and advance to round 2
> (research/18 §1, `docs/research/assets/18-s0-evidence.png`); that "golden" was two stills of a
> match with **no input ever sent**. The peer-packet decode, the local-IP fix and the input-delivery
> fix below all stand — only the conclusion drawn from them is withdrawn.

Runs ours_match_sweep1..3, probe4..9 (logs/parity/ours_match_*, drive logs drive_match_*.txt,
per-instance run logs with `[peek] @416054` = the local player's camera-orbit position, 1 row/s).
- **Input delivery fixed (2561a29):** posted WM_KEYDOWN/UP reach raylib only when the window
  thread pumps, so scripted holds were dropped or their release was seen only at the next press
  (probe6: J->L->W transitions with no neutral state between). `PS2X_SOCOM2_INPUT_FILE=<path>`
  is read on every pad poll ("b=<hex mask> rx= ry= lx= ly="); the online drivers write
  logs/pad_A.txt / pad_B.txt (Shell.pad / Shell.hold). probe7: every 3 s hold lands as a clean
  press/release pair, twice over.
- **Mapping in the online match (probe7/9, identical twice):** RY (K/I) pitches the camera
  (the 0x416054 record moves 27 units along the facing and 10 in y: it is the orbiting camera,
  not the feet), R1 fires (ammo drops), CROSS/TRIANGLE change the camera/stance. RX, LX, LY do
  NOTHING: no turn, no walk (single-player, same build family: LY walked 137 units in 8 s, RX
  turned the view). OPTIONS -> CONTROLLER PRESETS says "1 - Precision Shooter preset is
  currently selected" (presets_explore sheet), so the preset is right; the player is frozen.
- **Netcode (PS2X_SOCOM2_NET_TRACE=1 + udp send/recv counters, this commit):** during the
  8-minute match each instance sends ~1.5 UDP packets/s in total: DME aux (50000/50001)
  keepalives and ONE 22/32-byte packet per second to the peer (A 3658 <-> B 3660, both
  directions arrive). A real SOCOM II match streams tens of packets/s peer-to-peer. The DME
  TCP side only carries the join/address exchange (APP_SINGLE 0x18 with two NetAddresses per
  client) and a handful of broadcasts at spawn, then silence until disconnect. So both clients
  sit at "STARTING ROUND 1 OF 11" waiting for a peer handshake/sync that never completes; the
  HUD timer runs regardless.
- **Local IP:** the exe derived its own address from the universe-server host (default
  127.0.0.1), so both clients advertised 127.0.0.1:3658 as their first NetAddress (A sent peer
  packets to itself). `PS2X_SOCOM2_SERVER=192.168.2.10` makes it 192.168.2.10 (probe9: no
  loopback sends) — correct, but the match stays frozen. Keep the env in the run scripts.
- Same-team is a dead end (probe4: no SEALs -> the lobby never starts the round). The joiner's
  lobby cursor never leaves NOT READY (sweep2/3: UP and DOWN both ignored); the host's cursor
  moves normally (lobby_select), so `--host-switch` is the way to move players between teams.
- The PCSX2 golden (logs/parity/online/match/A_18_hold05, B_20_hold05) is the same frozen
  state (same spawns, timer 05:04); movement was never verified on the reference, and
  tools/pcsx2_b (client B) no longer exists (data-loss incident).
Next: probe10 dumps the first 16 peer packets in hex (`udp peer send/recv`; SCERT ids:
CLIENT_CONNECT_AUX_UDP 0x16, SERVER_CONNECT_ACCEPT_AUX_UDP 0x19, CLIENT_HELLO 0x24, SERVER_HELLO
0x25, UDP_APP 0x0c, ECHO 0x05, PEER_QUERY 0x27..). Hypotheses in order: (1) both instances use the
same fixed RSA keypair (socom2_rsa_key.h) and the peer SCERT handshake rejects/derives a bad
session with an identical key (PCSX2 clients had distinct random keys) — test by giving instance
B a second key (env-selected); (2) the peer connect message carries an address/port the receiver
validates against the DME address list (sceInetAddress layout in exUdpRecv addrOut/portOut);
(3) the P2P layer needs a libnetb feature the HLE answers wrongly (poll/available on UDP).

## 2026-09-10 18:45 (local) — USER REPORT: black squares still visible on the opening cutscene
The user (watching the live runs) sees black squares in the opening cutscene (the intro movie /
location cinematic). The title-gate sheets show the same on the movie background: 16x16-ish black
rectangles at the frame edges in a few captures (vr_title s00/s01 left of the logo, xg_title s14
right edge). Size and placement say dropped/undecoded MPEG macroblocks (IPU/PSS decode or the
16x16-block upload path, STATUS 2026-09-09 12:10 describes that upload), not a GS/dirty-rect
issue. The user adds they flicker in and out very fast, occasionally: per-frame, so either single
decoded frames miss blocks or the two display buffers alternate a stale block (the 12:10 menu-video
strip flickered every other frame the same way; a `burst` capture at 0.2 s catches it). Open under
goal 3; first step: PS2X_GS_DUMP_DISPLAY over the intro and a PCSX2 burst
capture of the same seconds (transition_probe_pcsx2.txt style), then compare the block grid.

## 2026-09-10 17:40 (local) — VU1 register-file build landed (841a6fc); two instances of our exe reach ONLINE GAMEPLAY on it (ours_match_play5); A walks into a wall, next = same-team sweep for the first kill
Picked up the VU1 agent's uncommitted work (stale lock, 26 h): the generated VU1 code keeps the VF
register file in a local (xmm-resident across pairs, written back around interpreter fallbacks),
XGKICK bookkeeping is reset without zeroing the 64 KB packet buffer (`m_xgkick = {}` was ~24% of
the game thread), the VU rounding mode is set through the x87/MXCSR control words instead of
fesetround (142 ns per run(), VU0 macro programs run by the thousand per frame), and VU0 runs skip
the steady_clock reads. Rebuilt (header change, 10 min) and gated on this build:
- title_menu.txt (run vr_title, sheet logs/parity/vr_title_sheet.png): 20 clean captures, labels
  crisp, movie background, 59 syncv/s at the menu.
- gameplay_probe.txt (run vr_gameplay): did NOT reach the mission — not a build regression: this
  boot showed the controller-configuration screens (yesterday's xg_gameplay run skipped them, the
  known drift) and the probe's blind CROSS answered YES to "save to the memory card?", then looped
  on "overwritten data will be lost? [NO]". Fix 7bf0160: drive.py `ifref(<png>,y0,y1,x0,x1,thresh)`
  presses only when the settled screen matches; the probe presses RIGHT (NO) on that prompt
  (ref scripts/parity/ref_save_prompt_ours.png, dist 0 on the prompt, 16 on the overwrite dialog,
  35+ elsewhere; threshold 8).
- **Two-instance online match (logs/parity/ours_match_play5, sheet match_play5_sheet.png), the
  goal-1 run:** A (socomc) hosts test/Medley, B (socome) joins and switches to TERRORISTS, both
  READY -> VIGILANCE -> both in gameplay with HUD, round timer, compass; A fires (27/30 after two
  R1 bursts), B moves. 19-21 syncv/s per instance with both running (two game threads + two GL
  threads on the host). Horizon: world 0 registered, both clients CONNECT_COMPLETE on DME TCP +
  aux UDP (50000/50001), APP_SINGLE/BROADCAST relayed, no faults in either run log. The driver's
  "B_TIMEOUT waiting for persona" at 180 s was spurious: B had already passed the persona screen
  and continued to the EULA/lobby/briefing room (fix the message when touching the driver next).
- A never moved: every A_play frame is the same view (a stone wall 2 m ahead); `hold W 3 s` walks
  into it. B's frames change (it turns/moves). So position feedback is needed for A to hunt.
Next (bounded): `--same-team --sweep 24` in online_match_ours.py (added, untested): B stays on
SEALs so both spawn together; A rotates in place firing a burst per step; both instances run with
`PS2X_PC_SAMPLER=1 PS2X_PEEK=0x416054:3` (local player x/y/z, one row per second in each
logs/run_*.log) so the two positions and any death (B's y / respawn) are readable from the logs.
Then the kill/round-end readout: B's HUD/death screen, and the DME world log slice
(server/logs/console-DME.log from the line count the run script records as dme0=).
Run hygiene: the harness kills long background shells, so runs go through a detached script
(logs/run_match_play5.sh via PowerShell Start-Process) and a `.done` marker; the loop cron fires
every 30 min and skips while `logs/.loop_lock` is held by a live run.

## 2026-09-09 15:05 (local) — online match driver on the 60 fps shell: three timing/matcher fixes; instance A logs in to the lobby, B stalls on a missed press (fixed, re-run queued)
Runs ours_match_play1..4 (logs/parity/ours_match_play*/, drive logs logs/parity/drive_match_play*.txt).
The two-instance driver (tools_py/parity/online_match_ours.py, `--play N` adds a gameplay phase: A
walks + fires, B turns) had not been run since the shell went from ~20 to 59 fps; three things broke:
1. Screen matcher: the renderer now draws the UI ~8 px left and a little darker than the
   scripts/parity/refs bands (raw diff 22 vs an 8 threshold). Shell.diff is now a normalised,
   shift- (+-20/+-6 px) and horizontal-scale- (0.90-1.04) tolerant distance; correct screens
   score 0.26-0.44, wrong ones 0.45+ (prompts 0.5); is_screen also requires the best match among
   references sharing a band. Validated on the play1-4 captures.
2. Key holds: 0.15 s = 9 frames trips the UI's held-button repeat. On-screen keyboard typing lost
   characters and overshot ("9`^h", 3 dots for a 5-char password); CROSS on the SERVER NEWS popup
   closed it and the repeat reopened it 8 times in a row. Keyboard presses hold 0.06 s, all other
   driver presses 0.08 s (5 frames).
3. press_until_gone treated one missed frame as "gone" and skipped the press that connects to
   the universe on instance B; a screen is gone only after two consecutive misses 0.6 s apart.
Also: scripts/loop_lock.sh `take` is BUSY for its own owner too (two chains of one owner
overlapped and stole/released each other's lock); `renew <owner>` refreshes a held lock. Host
memory: ~2.5 GB available of 32 (other apps hold ~70 GB committed); the harness kills background
shell tasks under that pressure, so long game runs are launched detached
(logs/run_match_queued.sh via Start-Process) and polled by file.
State: play4 — A: login -> universe -> persona -> password -> CONNECT -> write-down notice ->
EULA -> SOCOM II ONLINE lobby (SERVER NEWS), Medius AccountLogin MediusSuccess; B: stuck on
SELECT UNIVERSE (fix 3). play5 with all fixes is queued behind the VU1 agent's lock.

## 2026-09-09 13:30 (local) — FIRST MISSION IS PLAYABLE: scripted walk / fire / turn drives the game (enemies spotted, objective failed, squad engaging) at 36-42 frames/s
Run logs/parity/runs/gameplay_probe5 (sheet logs/parity/gameplay_probe5_sheet.png, log
logs/parity/gameplay_probe5.log) with scripts/parity/gameplay_probe.txt on the current build
(ff7bdac + input trace): boot -> NEW GAME -> briefing -> DEPLOY -> mission intro -> HUD detected by
screen state (untilref on the squad panel, 34 CROSS presses through the cinematics) -> hold W 8 s
(player walks: x/z 939,832 -> 940,969, i.e. ~137 units; the actor's y follows the terrain)
-> R1 (fire) x2 -> hold L 3 s (right stick: view turns, "Enemies spotted!") -> hold S 8 s
(walks back: to 774,2047 — the walk-back went somewhere else, fine for a probe) -> R1. The game
responds like the console: JESTER/WARDOG/VANDAL name tags, "OBJECTIVE FAILED: TEAM SPOTTED",
squad status FOLLOWING -> ENGAGING, the first-operation help popup. New PS2X_SOCOM2_INPUT_TRACE=1
logs every pad-state change (buttons mask + axes) so a probe's presses are provable in the log
([socom2-input] state buttons=0800 = R1, ly=00 = stick up, rx=ff = right).
Frame rate ([vu1-stats] syncv/s) in gameplay: 36.5-41.9 (mission intro cinematics 20-28).
Known gaps toward the user's "playable" acceptance (a two-instance match ended by a shot or a
grenade): (1) no kill/round-end readout from guest memory yet — find the round/score state the
DME world reports (server/logs has the Horizon side) or the HUD text; (2) online_match_ours.py
needs the same hold/burst steps and the fixed R1 key; (3) HUD text is slightly soft vs the console
(texture filtering) — parity item, not a blocker. Also seen: the probe's DOWN through the briefing
now needs 34 presses since the faster boot (no functional issue).
Tools: drive.py `hold+<s>:KEY` (W/A/S/D left stick, I/J/K/L right stick, R1/L1... buttons),
`untilref(<png>,y0,y1,x0,x1,loops,thresh)`, `burst+<s>:NONE`; scripts/parity/ref_hud_ours.png.

## 2026-09-09 13:30 (local) — GL thread: cached trace switches, row-span texture decode, buffer pooling, render targets sampled directly (no readback); all three parity gates clean
Commits ff7bdac and 1c63db7 (gs_gl_backend.cpp, after main's 9dbe933 dirty-rect fix, whose
semantics are untouched): traceSkip caches its getenv lookups (4.4% of the GL thread with tracing
off); decodeTexture reads row spans through GSMem::ReadSpan and converts per row (14%); the
executed CommandBuffer is a member swapped with m_pending so both keep their capacity (no per-frame
vector growth on the game thread, ~7% of it); and resolveTexture samples a GPU-drawn render
target's own colour texture when a texel-coordinate, clamp/region-clamp draw textures from exactly
that target in CT32 (pending shadow->GPU rectangles applied first; never for the target being drawn
into) — the readback+decode was 26% of the GL thread. `PS2X_GS_RT_TEXTURE=0` restores the readback.

**Gates.** title_menu.txt (runs gl_title, rt_title): 20 clean title captures (movie background,
crisp LOAD GAME / NEW GAME / ONLINE) then the attract cinematic; transition_probe.txt (gl_transition,
rt_transition): rows 396-447 peak 0 on every black-screen frame (`tools_py/parity/black_rows.py`,
scores only frames whose upper rows are black; main's rects_transition baselines at 0); mission
diag (gl_mission, rt_mission): sheets identical to sched2_1, HUD text / minimap / squad panel crisp.

**Numbers.** [vu1-stats] `proc` minus `thread`: the GL thread went from ~1000 ms/s (a full core,
half of it the vsync wait) to 0-650 ms/s in the mission; main's gameplay probe on this build
reports 36-42 fps (cdd2c4c). Mission frame rate in the diag script varies with the scene (2.4-4.2 M
VU1 cycles per frame between runs), so compare phases by cycles/frame. GL-thread profile of this
build: pending (run glprof_3 queued behind the lock).

## 2026-09-09 12:10 (local) — menu-video strip before the briefing FIXED: shadow->GPU refresh now re-reads exactly the uploaded rectangle, not the enclosing rows
User report (07:45): a strip of the main-menu video at the bottom of the black screen just before
the mission briefing (rows 396-447 of the 448-row frame, flickering every other frame). Console
(PCSX2 burst capture, logs/parity/runs/transition_pcsx2) shows pure black there. Evidence chain
(runs transition1..15, tools: burst step in drive.py, PS2X_GS_DUMP_DISPLAY three-layer dumps of
the displayed buffer, PS2X_GS_TRACE_DIRTY, PS2X_GS_PROBE post-draw pixel reads):
- The game double-buffers at fbp 0 / 0x8c (448 rows each). The letterboxed cinematic
  (alb_aop.pss, 640x368) is uploaded into the display buffer as 16x16 blocks from a base one page
  row below the buffer (dbp 0x12c0 / 0x140), so its last block row lands at rows 384..399.
  VRAM rows 400..447 still hold the main-menu movie's leftovers (the menu movie is uploaded
  through the same path). The game's full-screen black sprite (0,0)-(640,448) does paint the GPU
  target black there (probe: rows 420/440 = 000000 right after every such sprite).
- Our GL backend mirrors uploads into the GPU target lazily: an upload marks the target's rows
  dirty and the next draw/present re-reads them from the shadow VRAM. The dirty window was a
  single merged [first,last) row range, then (this morning) 32-row bands: a 16-row block at rows
  384..399 re-read rows 384..415, i.e. also the stale rows 400..415 the GPU had just painted
  black — and the previous merged-range scheme re-read everything between the topmost and
  bottommost mark. The GPU's own draws are never in the shadow, so any re-read beyond the
  uploaded pixels resurrects old content.
- Fix (gs_gl_backend.cpp): uploads in the target's own layout (same dbw/psm, page-row aligned)
  record an exact DirtyRect (dsax/dsay/rrw/rrh) that refreshDirtyRows re-reads with a
  glTexSubImage2D of just that rectangle; other layouts keep the 32-row band mask (dirtyMask);
  executeClear applies pending rows before clearing. Verified: transition run rects_transition
  (black screen band 0.0, was 8.1), title-menu run rects_title (24 clean captures, movie
  background and labels intact). Mission sheet still to be re-checked by the next mission run.
New switches: PS2X_GS_TRACE_DISPFB=1 (display buffer + clear log), PS2X_GS_NO_DIRTY_REFRESH,
PS2X_GS_NO_ZTEST, PS2X_GS_TRACE_DIRTY=<frame>, PS2X_GS_PROBE=<frame>,
PS2X_GS_DUMP_DISPLAY=<dir>:<t0>:<t1>, PS2X_GS_TRACE_CMDS_FROM/_MAX; drive.py `burst+<s>:NONE`
captures a frame every 0.2 s (transition flashes). Wrong turns worth not repeating: the CPU GS
backend (PS2X_GS_BACKEND=cpu) does not feed PS2X_HOST_SCREENSHOT_LATEST, so it cannot A/B a
display bug; PS2X_GS_TRACE_CMDS=<n> is relative to the movie-start frame (use _FROM for an
absolute frame); PS2X_GS_TRACE_DIRTY without a row filter floods the log and stalls the run.

## 2026-09-09 07:30 (local) — scheduler fast paths, direct XGKICK submit, VU0 fast path: mission gameplay 28.7 frames/s (best 30 s: 31)
Fresh game-thread stack profile after the GS spans (run gtprof_2): startXgkick 9% in memcpy (the
kicked packet was copied VU memory -> kick buffer -> arbiter), processPendingEvents 6% in mutex
calls on every checkpoint return, selectReady 4% self (128 empty priority deques scanned on every
idle wake), VU0 micro programs 4.5% (still the cycle-exact scheduler), GS front end ~12%
(GSGlBackend record/Cmd growth, main's file). Fixes (commit below): the immediate XGKICK path
walks the GIFtags in VU memory and submits the packet from there (the arbiter's copy is the only
one; the copying paths remain for wrapping/overrunning packets), processPendingEvents clears the
checkpoint request without the event mutex when nothing is posted (atomic event count) and no
deadline is due, selectReady returns at once when the ready count is zero, and VU0 micro programs
use the fast path too (`PS2X_VU0_FAST=0` restores the exact scheduler; the semantics are the same
code that is golden-verified on VU1). The mission program was regenerated with the newest
hand-back pcs added to logs/vu1_seeds_mission.txt (900-dump golden green, FMAC check clean).

**Result** (run_20260909_07xx sched2_1, sheet identical): gameplay phase **28.7 syncv/s over the
last 60 s, 31.0 in the best 30 s**, 7.0 ns/cycle, 69 M VU1 cycles/s, 2.4 M VU1 cycles/frame,
hand-backs 33/s (0x3828 now the top one). Progression today: 3 -> 10 -> 13 -> 19 -> 22 -> 29.
GSMem::ReadSpan (row-span texture reads, mirror of WriteSpan) is in for the GL backend's
decodeTexture (per-pixel ReadCT32 today, 14% of the GL thread; main's file).

**07:50 addendum.** GifArbiter::submit now processes a packet straight from the caller's buffer
when its queue is empty (order-preserving: nothing but other submissions happens between a submit
and the drain), which removes the per-XGKICK memcpy (run arb_1: 26-28 frames/s, sheet identical).
The title screen and main menu run the mission VU1 image with entry pc 0 (150 dumps at the title,
all hash 638cb8f0), so the recompiler already covers them (`interp-programs/s=0` at the title);
the title itself runs at ~30 syncv/s with the game thread at 100% and VU1 at 2 ms/s — the menu
movie decode/upload path, not VU1, if that ever matters. Online lobby image: dump in progress.

**08:20 addendum — one VU1 image everywhere.** The online lobby (SELECT UNIVERSE on the local
Horizon universe, run online_dump3, 59 syncv/s) and the title/main menu both run the mission
microcode image (hash 638cb8f0, entry pc 0): 150 dumps each, `interp-programs/s=0`,
`handbacks/s=0`. So the single generated program covers title, menus, mission and lobby. The
fixed-press online scripts no longer line up with the faster boot (they land on NEW GAME);
`scripts/parity/launch_to_online_fast.txt` drives the menu by screen state (`untilref` on the
main-menu reference) and reaches the lobby.

## 2026-09-09 06:20 (local) — VU1 program regenerated from 900 dumps (300 gameplay): hand-backs 850 -> 32/s, mission gameplay 22-29 frames/s
The in-game `[vu1-bail]` histogram showed the generated code handing ~1100 programs/s to the
interpreter at computed-jump targets (command handlers) the 300 intro-window dumps never
reached (0x1c30, then 0x1c70/0x1a78 one hop further). 300 gameplay programs were dumped with
`PS2X_VU1_DUMP=logs/vu1dump4:300 PS2X_VU1_DUMP_AFTER=220`, their exact-interpreter golden
recorded (logs/vu1golden/d4, 1.1 M cycles), and the program regenerated from all 900 dumps plus
the bail pcs (`vu1_replay --gen --seeds logs/vu1_seeds_mission.txt`). The generated code equals
the exact interpreter on all 900 programs (d2/d3/d4 diff 0, FMAC check clean); the gameplay
dumps run at 6.9 ns/cycle offline. In the mission (run_20260909_053430-ish seeds_2, sheet
identical): hand-backs 32/s, 5.9-10.7 ns/cycle, VU1 host 430-480 ms/s incl. GS work, and
**syncv/s 21.8 over the last 60 s, 29.0 in the best 30 s phase** (2.5-3.1 M VU1 cycles/frame).
Remaining hand-back pc 0x3d18 (4211 in the run) is next in the seeds. PS2X_HOST_PROF_MAIN=1
samples the main/GL thread (it uses a full core: next profile target).

## 2026-09-09 05:30 (local) — stage 3: host stack profiler; scheduler clock batching; row-span GS uploads + pooled arbiter -> mission gameplay 12.7 -> 19 frames/s
**Measuring.** `PS2X_HOST_PROF=1` now writes module names for external addresses and runs its
sampler at time-critical priority (the old sampler under-sampled compute and blamed `_setmode`);
`PS2X_HOST_PROF_STACKS=1` unwinds the x64 call stack of every sample (RtlVirtualUnwind) and
`tools_py/hostprof_stacks.py` prints inclusive shares, the exe callers of DLL time and folded
stacks. `[vu1-stats]` prints `thread=`/`proc=` CPU ms/s, `interp-programs/s` (images without
generated code, named once as `[vu1] program image <hash> ... has no generated code`),
`handbacks/s`, and with `PS2X_VU1_BAILHIST=1` the top hand-back pcs (`[vu1-bail]`);
`tools_py/vu1stats_summary.py <log>` summarizes a run by 30 s phase with VU1 cycles per frame.
Frame rate = `syncv/s` (sceGsSyncV, one per presented frame; the game never calls
sceGsSwapDBuff). The game thread is 100% of one core; the process uses ~2 cores (GL thread).

**Profile of the game thread in the mission (run_20260909_043923, stacks).** Inclusive:
EeScheduler::accountCycles 21% (13% inside ntdll: a QueryPerformanceCounter on every recompiled
checkpoint), GS::processGIFPacket 15.5% (GSCpuBackend::UploadImage 9.2% = a std::function call per
pixel into GSMem::WriteP8/P4/CT32; GSGlBackend::record copies 3%; vector<GSGlBackend::Cmd> growth
2.2%), processDueDeadlines 4.6% (mutex + clock per call), dispatchIrq 3.4% (std::getenv per IRQ),
VU1 generated code ~9%, VU1 interpreter ~12% (hand-backs, see below), recompiled EE code ~3%.

**Fixes (commits 9b4212b, 5ef9c5b).** accountCycles converts the host clock once per 5000
estimated guest cycles (~17 us; waitForEvent forces a conversion); processDueDeadlines returns
before m_nextDeadlineCycle without locking; dispatchIrq caches its trace switch; publishSnapshot
(a138ad3) publishes at most every 50 ms of guest time. GSMem::WriteSpan writes host-to-local
transfers in row spans (same PixelStorageTraits<psm>::Write per pixel, inlined, no std::function;
the per-pixel path stays for formats without a span writer) and GifArbiter reuses its packet
slots/buffers. Sheets sched_1 and gsup_1 are identical to vu1gen_1 (title labels, briefing
textures, cinematics, HUD).

**Result.** Gameplay phase of the mission (HUD on screen, ~2.9 M VU1 cycles per frame):
run_20260909_051059 **19.0 syncv/s** at 10 ns/cycle (56 M VU1 cycles/s, VU1 host 560 ms/s incl.
the GS work done inside XGKICK) vs 12.7 before the scheduler/GS changes (the scheduler-only run
sched_1 measured 11.7 in a heavier phase — the phases do not align run to run; compare the
gameplay phase and cycles/frame). Menus 55-57/s.

**Open.** The generated VU1 code hands ~1100 programs/s back to the interpreter at computed-jump
targets the 300 dumps never reached (0x1c30: 200k, 0x1e50: 28k, 0x1d80, 0x1d30, 0x1d90, 0x3d10 ...):
those pcs are now generator seeds (logs/vu1_seeds_mission.txt, `vu1_replay --gen --seeds`) and a
gameplay dump (PS2X_VU1_DUMP_AFTER) is being taken for a second golden. Still in gs_gl_backend.cpp
(main's file, pending its commit): pooled record/Cmd buffers (~5%). Then: what the other core does
(the GL thread is at 100%: decode/upload on the render thread may be the next wall), and the VU1
register file in host registers.

## 2026-09-09 04:05 (local) — VU1 microcode recompiler ("known programs"): 18 -> 12 ns/cycle in the mission, frame rate 10 -> 13 per second; the other 35 ms/frame is now outside VU1
**What landed (commit 6dcf73d, default on; `PS2X_VU1_GEN=0` disables).** `vu1_replay --gen`
turns a dumped 16 KB VU1 code image into one goto-threaded C++ function
(src/lib/vu/generated/vu1_d418194495c25213.cpp for the mission image, md5 638cb8f0, all 300
dumped programs) registered in vu1_known_programs.cpp; the interpreter hashes VU1 code memory
(FNV-1a, only when the VIF MPG generation changes) and runs the matching function. The generated
code is a static unrolling of the fast path with constant register indices and the same shared
SSE FMAC helpers (ps2_vu1_ops.h): flag ring / Q / P timing kept exactly (commits deferred to
readers, loop heads and every 16 pushes on a 64-entry ring), same-pair shadow rule, delay slots
(also a branch inside a delay slot), E-bit end, and a hand-back to the interpreter with
m_state.pc set for anything unsupported (cycle budget, computed-jump targets not seen in the
profile, D/T bits). A dataflow pass over the image (per-lane "pairs since the last write" slack,
"lane holds a normalized value") removes the ready checks and operand normalizations that cannot
matter (1400 -> 62 VF ready checks in the mission image); the MADD/MSUB flag classification has a
proved-exact float fast path (double/long double only near zero, overflow or cancellation; proof
in ps2_vu1_ops.h); ACC stays in a host register across pairs; XGKICK copies whole GIFtag
payloads. Tooling: `--pchist`/`--bailhist`/dispatch counters, `-g1` on the generated file so
`--prof` maps to pairs (scratch script genprof), `[vu1-stats]` now prints `flips/s`
(sceGsSwapDBuff — SOCOM II never calls it) and `syncv/s` (sceGsSyncV = one wait per presented
frame: the frame-rate number).

**Verification.** Offline: identical to the exact interpreter on all 300 dumps (packets,
registers, flags, cycle counts), 0 hand-backs, `PS2X_VU1_FMAC_CHECK=1` clean; 10.0 ns/cycle vs
21.4 (fast interpreter) and 92 (exact) in the same tool. In-game (same build, mission phase,
last 60 s of each run): generated `[vu1-stats]` 45.1 M cycles/s at 12.1 ns/cycle, 27.9k
programs/s, host 546 ms/s, **syncv/s 12.7** (run_20260909_034405, sheet vu1gen_1: title clean,
intro clean, gameplay HUD at s33); `PS2X_VU1_GEN=0` baseline 32.9 M cycles/s at 18.5 ns/cycle,
21.6k programs/s, host 605 ms/s, **syncv/s 10.2** (run_20260909_035139). Menus run at 50-57
syncv/s in both. Yesterday's exact interpreter: 6.9 M cycles/s at 100 ns/cycle.

**Where the time goes now.** The mission issues ~3.3-3.5 M VU1 cycles per presented frame
(~2100 programs), so at 12 ns/cycle VU1 costs ~42 ms/frame and the rest of the runtime (EE
recompiled code, VIF/DMA, GS front end on the game thread) ~35 ms/frame: frame time ~77 ms.
Even a 4 ns/cycle VU1 (14 ms) leaves ~50 ms/frame -> 20 fps, so the next step for frame rate is
a `PS2X_HOST_PROF` profile of the mission with this build to find the non-VU1 hot spots (the
earlier profile, STATUS 2026-09-08 17:30, was taken when VU1 was 70% of the time). VU1 itself:
the generated code's remaining cost is the FMAC flag build/push (~40% of its time), startXgkick
(~5%), fastCommit (~3%); the register file still lives in memory (store-forwarding latency on
dependent pairs), which a per-block register allocator could remove.

**Caveats.** Only the mission image is recompiled; the title/UI and online images run on the
fast interpreter until dumped (`PS2X_VU1_DUMP` at those screens, then `vu1_replay --gen` and a
line in vu1_known_programs.cpp). The generator's DIV/SQRT/RSQRT skip the PS2X_FPU_TRAP
diagnostics. Regenerating needs a bootstrap when the helper signatures change (scratch
regen.sh: remove the generated file and its table entry, build vu1_replay, --gen, restore,
build).

## 2026-09-09 02:40 (local) — VU1 fast path: 100 -> 18 ns/cycle in the mission (5.4x VU1 throughput), default on; the run reaches gameplay with the HUD
The cycle-exact VU1 scheduler (per-instruction ready scan, pending-write queues, long double FMAC
flags) is replaced by a non-cycle-exact fast path (commit 773991c, default on since this entry;
`PS2X_VU1_FAST=0` restores the exact path, a VU trace forces it):
- VF/VI/ACC writes and stores land immediately. Every VF write in the model has the same 4-cycle
  latency and every read stalls on the register, so immediate writes give the same values; the
  same-pair rule (the lower reads the old value of the upper's destination, the upper wins a
  write to the same register) and the one-instruction VI branch bypass are kept.
- The cycle counter still advances by the modeled stalls (per-lane VF and VI ready cycles, Q/P
  and EFU resources, WAITQ/WAITP), so MAC/STATUS/CLIP flags (8-entry ring in issue order,
  +4 cycles), Q (+7/+13) and P land at exactly the cycles the exact path shows them — the
  game's FMAND backface test and FCAND clip tests see the same flags. E-bit, branch delay,
  D/T halts, XGKICK at kick time, the 65536-cycle budget and the flush at program end are
  unchanged.
- FMAC lanes run on SSE2 for the four lanes together. The Z/S/U/O classification comes from the
  chop-rounded float (single ops) or double (product-sum: the float product is exact in double)
  result and drops to the long double computation only when a result lands exactly on FLT_MAX;
  proof sketch in ps2_vu1_upper.cpp (a single chop-rounded op has |r| <= |exact| < |r| + ulp), so
  the flags and stored values are bit-identical to the old long double path. `PS2X_VU1_FMAC_CHECK=1`
  cross-checks every FMAC against that path (0 differences over the 300 dumps). applyDest and the
  vf0 reset store 16 bytes (scalar lane stores followed by the FMAC's vector load stalled store
  forwarding); normalizeOperand/microAddressMask/fastReadyCycle inlined; the decoded-code cache is
  validated once per program instead of per pair.

**Verification.** `dist/vu1_replay.exe --batch <dir> <dumps>` writes a golden per dump (packet
bytes + FNV hash, cycle count, end pc, MAC/STATUS/CLIP/R/Q/P/I, all VI/VF/ACC, VU data memory
hash). The fast path equals the exact interpreter on all 300 dumped mission programs
(logs/vu1dump2 + logs/vu1dump3: 287k cycles, 274k pairs, 118 programs with packets) in every
field, including cycle counts. Timing with `--repeat 100` (`--prof` samples the host pc): exact
92 ns/cycle (same tool; the tool now runs programs from PS2Memory's VU1 buffers so the decoded
cache applies), fast 21.4 ns/cycle. In the mission (logs/run_20260909_021205.log, run
vu1fast_1, sheet logs/parity/vu1fast_1_sheet.png): `[vu1-stats]` 34-37 M cycles/s at 17.7-19.1
ns/cycle, 21-23k programs/s, vs 6.5-8.2 M cycles/s at 93-103 ns/cycle, 6.5-8.7k programs/s in the
last stats run (run_20260908_171207). The host still spends ~650 ms/s in VU1: the game is VU1-
bound and simply runs ~3x more frames (programs/s), so the next speed step is still VU1 (a
block recompiler to host; the interpreter's remaining cost is the per-pair dispatch, the
Windows-ABI xmm save/restore of execUpper and the ready-cycle scan). Screens: title labels clean
(s05/s06), mission loads, the intro cinematics play (s21-s27, no giant polygons), and for the
first time the 420 s run reaches gameplay with the HUD (s34-s37, "RENDEZVOUS WITH MALLARD",
squad status, help popup); same 16 pre-existing guest faults as before; no hang with the VIF1
i-bit stall (16af5ad).

**Not done / caveats.** ps2x_tests does not link on this toolchain (pre-existing: bad
`--stack` link option, then unresolved runner symbols ps2HostProfStart, ps2_stubs::sceVibGetProfile,
socom2_RsaGenerateKeyPair, scePad2GetState), so the VU unit tests were not run; the 300-dump
golden and the FMAC check stand in. The fast path is VU1 only (VU0 micro programs keep the exact
scheduler; they are tiny). The exact path's behaviour of reading the previous I register in an
I-bit pair's upper instruction is preserved (not re-examined). No frame counter exists in the
log; frame rate is inferred from programs/s (~3x) — add a flips/s line to PS2X_VU_STATS next.

## 2026-09-09 02:15 (local) — TITLE LABELS FIXED: VIF1 i-bit stall + prompt IRQ delivery; the console never stops the menu movie (that lead was built on the wrong savestate)
The garbled LOAD GAME / NEW GAME / ONLINE labels are gone: logs/parity/title_stall5_sheet.png
holds 24 main-menu captures over 2+ minutes, all clean (before: logs/parity/title_trace7_sheet.png,
garbled from s10 on). Root cause, established with a PCSX2 GS dump of the real main menu
(savestate slot 21; slot 6 — the "title" image every 03:20 conclusion was built on — is the
SELECT RANK dialog, so "the console has no movie set at the title" was never a valid comparison;
the user confirmed the menu movie is correct and must stay):
- Console per-frame GS order (tools_py/gsdump_timeline.py on tools/pcsx2/snaps/*.gs, captured by
  tools_py/parity/gsdump_capture.py --slot 21): 512x256 background upload -> background sprite ->
  the 11 label textures (set [11], 0x3107..0x3387) -> label draws. Ours (tools_py/gif_submit_timeline.py
  on a PS2X_GIF_TRACE run, which now also prints TEX0 binds): set [11] flush -> background upload
  (to 0x2bc0 every other frame, overlapping the label pages) -> label draws. One step out of phase,
  so the labels were drawn from the background's pixels every other frame.
- The game sequences texture-set uploads against its draw stream with a marker protocol: each
  set flush appends an entry to the render queue at 0x4887c0 (FUN_0033bf30/be70/bd90) and emits
  [FLUSH][DIRECT 1qw][FLUSHA][NOP with the VIF i-bit] into the VIF1 MFIFO ring. VIF1 stalls at the
  i-bit code and raises INTC5; the handler FUN_0033c010 kicks the GIF chain of entry[index++]
  (PATH3 upload), re-bases sets (FUN_00355de0) and writes FBRST.STC to release VIF1. FUN_00339de0
  (frame begin) resets the index. Two runtime defects broke the mapping between markers and entries:
  1. VIF1 never stalled on an i-bit VIFcode (it raised INTC5 and carried on), so the next segment's
     draws ran before the handler kicked their uploads. Fixed: ps2_vif1_interpreter.cpp holds the rest
     of the stream after an i-bit code (STAT.VIS|INT) until FBRST.STC (ps2xVif1StallCancel resumes it);
     PS2X_VIF1_NO_IRQ_STALL=1 restores the old behaviour for A/B.
  2. The 7th (last) marker of a frame is committed to the ring by FUN_00350ab0 with a BYTE store to
     D8_CHCR (0x1000d001); only PS2Runtime::Store32 drained pending INTC causes, so that interrupt
     was delivered at the next 32-bit MMIO store — inside FUN_00339de0, after it had reset the index —
     and every chain of the new frame was kicked one marker early (the label set before the
     background instead of after it). Fixed: Store8/16/64/128 drain completed DMAC/INTC causes too.
  Evidence: tools_py/marker_timeline.py merges FrameBegin/AppendFlush/Vif1Irq call traces, stalls,
  STC, GIF kicks and submissions (run logs/run_20260909_020018.log = before, 020640 = after).
- Also landed: scripts/parity/title_menu.txt reaches the main menu by screen state
  (drive.py `untilref(<png>)` presses CROSS until the frame matches ref_main_menu_ours.png, then
  holds) — boot drift made fixed press counts land on SELECT RANK in 2 of 3 runs.
Not re-verified in this step (the VU1 agent's mission run is next and covers it): the mission
load and online screens with the i-bit stall. If a run ever hangs with VIF1 stalled, the game
did not STC — A/B with PS2X_VIF1_NO_IRQ_STALL=1 and report.

## 2026-09-09 03:20 (local) — title labels (user report 01:50): the label VRAM pages are overwritten by a 512x256 upload from the menu-movie texture set; the console never runs that set at the title
The garbled LOAD GAME / NEW GAME / ONLINE labels are NOT a rounding or GS-decode fault any
more: the label images the EE uploads (128x32 CT32 at blocks 0x3207/0x3247/0x3287 = pages
0x190/0x192/0x194, texture set [11] base 0x2fcc) decode cleanly (PS2X_GS_DUMP_TEX). New
diagnostics `PS2X_GS_TRACE_PAGES=0x190:6` (every upload/copy/refresh/download/draw/decode on
those pages) and `PS2X_GIF_TRACE` (each GIF submission with path, PATH3 mask, GIFtag and
BITBLTBUF) show a PATH3 upload of a 512x256 CT32 image to block 0x2bc0 (pages 0x15e..0x19d,
covering the label pages) every third frame; the label textures are decoded right after it
and hold background pixels until the next label upload. The packet is built by the
texture-set flusher FUN_00356e90 -> FUN_00356d20 (CNT 6 qwords + IMAGE 0x7fff + REF) for a
set object (class vtable 0x6f0330) with base 0x2bc0 / limit 0x33d8 living at 0x7abcc0 on
ours; its image source is the 512x256 double buffer 0x15493b0/0x15c93b0 (stale logo bitmap in
it). PCSX2's title memory (new savestate slot 6 = title; `tools_py/parity/p2s_extract.py`
pulls eeMemory/Scratchpad out of a .p2s) has the same 16 texture-set managers as ours (all
equal, labels in set [11] at the same addresses) but NO set with base 0x2bc0/limit 0x33d8 and
no packet uploading to 0x2bc0 anywhere (main RAM or scratchpad), and its title background is
static for 90 s (captures 6 s apart differ only in the roller box). Both sides hold the dlgMenu
element with `run/movies/common/menuloop.pss`; on ours a live movie element exists (object at
0x7ab940.., "ui/assetlib/uisk..") streaming MENULOOP (sceCdStRead every frame) and pushing
frames through that overlapping set — the set is meant to be used only while the shell set
[11] is not (they overlap in VRAM by design). The CPU backend renders the labels clean only
because the timing of the interleaved uploads differs (title_cpu4); GL runs with extra render
work (title_gl4, texture dumps) were clean for the same reason. In progress (title_trace5):
PS2X_MPEG_TRACE/PIC_TRACE lifecycle at the title to see why our menu movie starts when the
console's does not (candidates: sceMpegIsEnd/GetPicture semantics after the intro skip, or the
attract-mode idle timer). Fix direction: make the menu movie behave like the console (not
running at the title) — not a GS/arbiter change.

## 2026-09-09 01:30 (local) — the collision probe is IDENTICAL to PCSX2's; ~~ground height: the actor rests at a different height above the same hit~~ (RETRACTED, see below)

> **Superseded by `docs/research/17-ground-height.md` §0.1 (Sprint 4 Task 4). The framing of this
> entry is wrong, and the entry contains its own refutation.** "The actor rests 20.11 / 14.69 above
> the hit" is neither the actor nor a height above the ground: both numbers are **camera-eye minus
> collision-hit**, differenced from the *camera* y values this entry prints in the very next
> clause — 20.11 = −126.264 − (−146.371), 14.69 = −131.68 − (−146.371). The **player's feet match
> the console to 0.008** (ours −145.875, console −145.8672; and this entry's own line 829 records
> our −145.875 as a cached ground point). What is 5.4 low is the **third-person camera**, and
> research/17 §4 localises that to the player actor's skeleton root node decaying 11.4845 → 0
> while its saved copy freezes at the console's 5.50391 — an animation-blend defect, not terrain,
> not collision, not the mover.
>
> The cost of the wrong name: "ground height" sent three sessions at terrain, the collision grid
> and the mover's gravity/step logic. Nothing below this line about the probe, the structures or
> the field offsets is retracted — only the sentence that says what the difference *is*.
>
> Also retracted, from line 819 below: **`*0x488de8+0xbc` is the camera's follow pointer, not a
> route to the player actor** — this entry says so correctly ("is null in the spawn images") and it
> was read as an actor route anyway, then carried into later work. The player actor is `*0x408c58`
> (`@408c58` word0 = `017941d0`, `@17941d0` word0 = `006691a0`, `*(actor+0xc0)` = mover
> `006694b0`), verified in five of our RDRAM images, the PCSX2 console image and live online
> (`9c28fe0`, research/18 §4.1).

With the new tracer (`PS2X_CALL_TRACE_DUMP="GroundQuery:a1:16,GroundQuery:a1+0x48*:16"`,
run mission_s19) every GroundQuery (FUN_002d49c0) prints its ray and hit records. The player's
vertical probe at (939.24, 832.6) returns ONE hit at y = -146.371, normal (0.070, 0.997, 0.021)
— exactly PCSX2's (polled live over PINE at savestate 8 with the new
tools_py/parity/probe_poll.py: -146.37, (0.0698, 0.9973, 0.0212)). So terrain, collision grid
and the probe math agree; the 5.5-unit difference is how far the actor rests ABOVE the hit:
PCSX2 20.11 (y = -126.264), ours 14.69 (y = -131.68). At spawn ours is placed at -125.97 (the
console value), drops to -135.9 and settles at -131.7 (s16 peek rows), PCSX2 never drops.
Structures: the player actor (class vtable 0x6691a0, PCSX2 spawn image 0x1713ce0) points at
+0xc0 to its mover (vtable 0x6694b0, 0x170d510) whose +0x90 is the position; the static records
0x416050/0x4160b0/0x416110/0x416170 are four horizontal segment probes cast from that position
(FUN_0029bf70) and never hit on PCSX2 — they do not set the height. The per-frame vertical
GroundQuery via FUN_0031dfd0 only feeds the surface material (+0x2c0 of the actor's +0xb4
object). The height therefore comes from the mover's own gravity/step logic or an animation
root offset. In progress: run mission_s21 dumps RDRAM at rest (400 s and at GroundQuery #350)
to diff the mover object against PCSX2's (candidate fields: +0x88/+0xf8 = 25.0, +0xf0 = 60,
+0x54.. = (4, 3, 6.33)). Gotcha: the camera's follow pointer (*0x488de8+0xbc) is null in the
spawn images; find the actor through the vtable scan instead. spawn_ours3.rdram (s18, 318 s)
was taken before the spawn (boot drift) and holds the post-load position (935.6, -120.0, 834.4),
identical to PCSX2's post-load record.
Update 02:10: mission_s21's 400 s image (logs/parity/rest_ours.rdram) holds the player at rest
(939.24, -131.73, 831.95); the player's actor is the one whose mover has vtable 0x6694b0 (AI
actors' movers use 0x6693f0). Diff against PCSX2's spawn image (scratch moverdiff.py: actor
0x1a5e4b0/mover 0x1785ee0 vs 0x1713ce0/0x170d510): mover +0x5c = 4.0 (PCSX2 6.3338, with
+0x54/+0x58 = 4.0/3.0 on both), +0x70..+0x7c = (-12.43, -39.13, -10.48, -14.29) vs (-11.86,
-41.58, -5.99, -12.96); actor +0x10 state word 0x00080502 vs 0x2, actor +0x24/+0xb8 = 856.39 vs
857.07 (a second position copy with y = 856?), actor +0x2bc..+0x2c4 = (939.24, -145.875, 856.39)
on ours vs zeros on PCSX2 (a cached ground point: -145.875 vs the probe's -146.371). No
constant 6.3338 in the decomp (computed). Parked here: the next step is the mover's update
method (writer of mover+0x90 y / reader of +0x5c) — trace it with PS2X_CALL_TRACE_DUMP on
the mover object — but the title-screen labels come first (user report 01:50).

## 2026-09-09 00:10 (local) — ROOT CAUSE of the giant sky polygons: VU0 macro-mode ops never set the MAC/STATUS flags, so the EE's frustum test called every object "fully inside" and sent it through the no-clip VU1 path
The object at the camera (STATUS 23:10) was the terrain/road strip the camera stands next to
(a 2x5 vertex grid at 90-unit spacing, world space; the transform's eye solves to the camera
position (938.6, -124.4, 832.5), which is also VU constant 30 — not a "player" test). Its VU1
command list [0x68, 6, 0x64, 8, 0x10, 0x28, 0x30] is built by `FUN_003b5f20`: word 8 (0xdf8,
transform without clipping) when the global `DAT_004b4eb0` is nonzero, word 2 (0x1f70 -> the
CLIPw subroutine at 0x3618 + edge clipping at 0x3a90/0x3ad0) when it is zero. The flag is the
third argument of `FUN_003b6b20` and comes from `FUN_00290c30`, the camera-frustum test of the
mesh's bounding box (FUN_003374c0 <- FUN_00338480 path; 2 = culled, 1 = fully inside, 0 =
intersects). That test is VU0 macro code: `FUN_00294ac0` multiplies the 8 corners by the
view-projection, runs VCLIPw and reads the CLIP flag register with CFC2; when a corner is
outside, `FUN_00294a30` does the fine test with two VSUBs and reads the STATUS register's sticky
sign/zero bits (CFC2 vi16 & 0xC0). Our recompiler never updated `vu0_status`/`vu0_mac_flags`
from any VU0 arithmetic (only CTC2 wrote them), so the fine test always returned "no corner
outside" and the near strip went out unclipped with q < 0 vertices. Also found: the macro-mode
VCLIP had the +/- bits swapped (bit0 must be x > +|w|) and compared against w instead of |w|.
Fix (recompiler): `VuTranslator::appendFmacFlags` appends `ps2_vu0_fmac_flags(ctx, res, dest)`
to every FMAC-class emission (ADD/SUB/MUL/MADD/MSUB/OPMULA/OPMSUB, broadcast/i/q/A forms; MAX,
MINI, FTOI/ITOF, MOVE, ABS untouched as on hardware); the helper in ps2_runtime_macros.h
rewrites the MAC flags (Z/S/O per lane) and STATUS (Z/S/O + sticky bits 6-9 ORed until CTC2).
VCLIP fixed to the manual's bit order with |w|. VERIFIED (logs/parity/runs/mission_s16,
logs/parity/mission_s16_sheet.png): the mission intro now renders every shot like the golden
run — helicopter over the valley, the car on the dirt road, the river/bridge scene, the forest —
with no sky-coloured polygons; the title screen (s05) is unchanged. The run ends in the forest
fly-by because the frame rate is still a few fps (item 3 below). CONFIRMED by the dump run
(logs/vu1dump3, mission_s17): 0 of 3164 kicked vertices have q < 0 (was 108 of 1878) and six
of the 150 programs now run the clipping list (word 2) that never appeared before. Gotcha: `PS2X_VU1_DUMP` does not
create its directory — mkdir it first or the run dumps nothing (silent fopen failure).
Remaining in order: ground height (-131.7 vs PCSX2 -126.3 at 0x416054), frame rate (VU1 fast
path / recompiler), then the mission parity report.

## 2026-09-08 23:10 (local) — the behind-camera triangles come from a no-clip object path; player stands 6.6 units lower than on the console
Offline replay of 150 dumped VU1 runs at the gameplay camera (logs/vu1dump2, `dist/vu1_replay.exe`
+ tools_py/gif_packets.py): 108 of 1878 kicked vertices have q < 0, all from four consecutive
frames of ONE object rendered through the 0x1b50 command-list entry (8 triangles, two texture
passes, tbp0 0x3621/0x3661 psm 8-bit, positioned at the player). Its command list is
b20 (vertex decompress: ITOF4 xyz + offset, ITOF15/ITOF12 normals/uv, ITOF0 colour) ->
0x1638 (per-triangle BACKFACE test: FMAND 0x10 on dot(cam - v, n), bit0 of the triangle record)
-> 0x4a8 -> 0xdf8 (transform, DIV Q = 1/w, NO near-plane clipping) -> 0xf90 (lighting) ->
0x1780 (emit: draws when bit0 && (bit1 || global word 39)) -> 0x22a0. The other 27 invocations
of 0x1b50 (a 60-vertex object every frame) and all 119 pc=0 runs are clean. The MAC-flag path
works as the manual says (traced with `PS2X_TRACE_VU_FLAGS=1`: the FMAND four instructions after
the FMAC sees that FMAC's flags). So the microcode is not clipping by design and the console must
never feed it this object in this state: the EE either culls it or gives it other data. Related
EE-side divergence found in the same run: the player stands at y = -132.9 (PCSX2: -126.26) with
x/z equal — the ground height from the collision grid differs by 6.6 units, and this object
(at the player) straddles the near plane. Next: find the EE submitter of the 0x1b50 list with
commands [52,3,50,4,8,20,24,...] (the JR table at 0x1ba0 indexes 340(vi14) words) and its
bounding/visibility test, and chase the ground-height difference (collision query FUN_002d49c0 /
FUN_002d2890 vs PCSX2's spawn image logs/parity/spawn_pcsx2.rdram).

## 2026-09-08 22:30 (local) — title-screen labels: the EE FPU chops; the game thread now rounds toward zero
The garbled LOAD GAME / NEW GAME / ONLINE labels (user report ~21:00) are 128x32 CT32 images the
EE composes and uploads (host->local to dbp 0x3207/0x3247/0x3287/... dbw=2), so the GS was drawing
what it was given; the CPU rasterizer garbles them in every run, the GL backend only when its
texture cache happens to re-decode (the cache made earlier runs look clean). The 8x8 blocks in the
logo's colours are glyph cells fetched from the wrong source: an index computed from a float.
The game writes FCR31 = 0 at entry (`ctc1 $zero`), PCSX2 truncates CVT.W regardless and runs the
EE FPU and VU in "Chop/Zero" rounding, and our host math rounded to nearest — the old
round-to-nearest cvt.w had masked the difference; today's hardware-correct truncating cvt.w
exposed it. Test: `PS2X_EE_ROUND=chop` (host rounding toward zero on the game thread) on the CPU
backend renders the labels correctly (logs/parity/runs/title_chop). Now the default in
ps2_runtime.cpp (game thread `fesetround(FE_TOWARDZERO)`; `PS2X_EE_ROUND=nearest` restores the
old mode). Expect other small parity shifts from this: every EE/VU0 float result now truncates.

## 2026-09-08 21:40 (local) — object geometry appears (XGKICK copied at kick time); behind-camera triangles and a title-screen regression remain
**Root cause of the missing objects.** With `PS2X_GS_TRACE_CMDS` armed at the gameplay camera
(new `PS2X_TRIGGER=lo:hi` on the first PS2X_PEEK word, `trig` mode of the GS/VIF traces), every
object triangle (1700 per frame, one texture, trees/bushes/characters) reached the GS as three
identical vertices at the GS origin with z=0xFFFF: the VU1 program re-templates its output buffer
right after XGKICK, and the per-cycle PATH1 model (one qword per two cycles while the program
runs on) still had the transfer in flight. Copying the packet at the kick (PCSX2's default; commit
089516b, `PS2X_VU1_XGKICK_CYCLE_EXACT=1` restores the old model) brings the objects back: trees
with foliage, and mission_s13's last frame is the road-through-trees scene of the golden run.

**Still wrong in-mission:** ~1/3 of the world triangles have q < 0 (vertices behind the near
plane, z wrapped to ~0xFFxxxx) and straddle the screen as giant sky-coloured polygons. The
microprogram (dumped with `PS2X_VU1_DUMP=<dir>[:count]`, disassembled with tools_py/vu1dis.py)
clips against the near plane geometrically: it forms per-vertex w sums with MULAx/MADDAy/MADDz,
reads the MAC sign flags four instructions later (`FMAND vi, 0x20` = z lane, `0x10` = w lane) and
branches into an edge-clipping path (DIV Q, vf26w, vf25w). Our MAC flag layout and the 4-cycle
flag latency match the manual on inspection, so the offline replay is the next step:
`dist/vu1_replay.exe <dump> --out p.pk` runs a dumped program through the runtime's interpreter
(registers restored from the dump), `tools_py/gif_packets.py p.pk` lists the kicked vertices and
their q sign. The three programs dumped so far (entries 0x0 / 0x1b50 / 0x33c8 of one 16 KB
microprogram) produced no negative q; a 150-program dump run is queued.

**Title-screen regression (reported by the user 21:0x):** since the XGKICK change the main menu's
LOAD GAME / NEW GAME / ONLINE labels render as teal/white noise (mission_s12..s14 s05/s06;
mission_s9, same copy mode via the env var, was clean once). Suspected the GIF arbiter's
priority sort (vendored: stable-sorts all queued packets PATH1 < PATH2 < PATH3 at drain, so a
PATH1 packet overtakes PATH3 uploads queued by the same DMA chain); it now processes packets in
submission order (`PS2X_GIF_PRIORITY_SORT=1` restores the sort) — the text is still garbled, so
that was not it. A/B run with `PS2X_VU1_XGKICK_CYCLE_EXACT=1` on scripts/parity/title_only.txt
in progress. Harness: drive.py `until(x0,y0,x1,y1)+<delay>:BTN` presses until the box shows the
briefing's highlight tint (G-R > 25), on settled screens only, and `long` waits up to 150 s.

## 2026-09-08 17:30 (local) — game state matches PCSX2 in-mission; the render does not (downstream of the EE)
With the SQRT.S fix the whole mission intro replays PCSX2's path: fly-by camera at (-3787,-109,..)
with the same rotation rows, spawn camera (939.4, 3.4, -843.6) / player (939.4, -131.7, 833.3) vs
PCSX2 (939.8, 8.3, -841.3) / (939.4, -126.3, 832.2), second fly-by, hold at (-3328, 282), then the
gameplay camera. The camera object's derived matrices (+0x2f0 world matrix, +0x330 view-projection,
+0x370 projection, +0x3b0 screen: `PS2X_PEEK="*0x488de8+0x2f0:64"`) equal PCSX2's to four
decimals. The picture at that camera is still a few giant flat polygons and sky (mission_s5/s6)
and the *pre-change* run of this morning (mission_z2, 06:54) shows the same frames, while the
online-match urban map rendered correctly on 2026-09-07 (logs/parity/online/match/A_18_hold05.png)
— so this is not a regression of today's float work but a mission-map rendering fault
downstream of the EE: VIF1 unpack, VU1 program or GS. Suspects in order: VIF unpack formats the
urban map does not use (STROW/STMASK/mode offsets for terrain chunks), a VU1 micro path, GS depth.
Discriminators prepared: `PS2X_GS_TRACE_CMDS=t<sec>` (per-batch vertex count + XYZ extents at
host time), `PS2X_TRACE_VIF=t<sec>` (UNPACK format/mode/mask/row histogram), and a
`PS2X_GS_BACKEND=cpu` mission run (GL vs reference rasterizer).

**VU1 interpreter: 158 -> 111 ns/cycle (commit 4960120).** A mission-only host profile
(diff of two PS2X_HOST_PROF dumps, logs/hostprof_mission.txt) put calculatePairReadyCycle at
20%, commitReadyPipelines at 20%, run() 8%, long-double FMAC rounding ~6%, and 15% in DLLs
outside the exe (unsymbolized). The commit scan now early-outs on an "earliest pending cycle",
the readiness scan on a "latest ready cycle", VI reads walk a bit mask, decoded pairs are served
by reference and XGKICK copies a qword at a time. Still ~700 ms of every host second in VU1 at
5 M cycles/s: the next step for frame rate is the fast (non-cycle-exact) path or a recompiler.

## 2026-09-08 16:15 (local) — ROOT CAUSE of the exploding actors: SQRT.S read the wrong register
The recompiler emitted SQRT.S with the *fs* field as its source. On the EE, `sqrt.s fd, ft` reads
**ft** (fs is zero in the encoding) and `rsqrt.s fd, fs, ft` is fs / sqrt(ft). Every square root
in the game therefore computed sqrt($f0) — usually 0.0 — e.g. the axis-angle length in the
quaternion builder FUN_003067b0 (`sqrt.s $f21, $f1` -> sqrt($f0) = 0), so sin(0)/0 saturated to
FLT_MAX and the actor orientations became (2^64, 2^64, ...). Found by the float traps
(`PS2X_FPU_TRAP`): the site divided 0 by 0 right after a `length == 0` guard that could not have
been skipped, and the generated code showed `FPU_SQRT_S(ctx->f[0])` for an instruction the
disassembler had printed as an unknown `c1 0x10544`. Fixed in ps2xRecomp/src/lib/fpu_translator.cpp
(SQRT uses ft; RSQRT takes fs and ft) and FPU_RSQRT_S became two-argument. VERIFIED 16:30
(logs/run_20260908_162132.log, screens logs/parity/runs/mission_s3): the teammate quaternion
node 0x1a83cb0 now holds unit-quaternion values (1.0, 0.707, 0.706) instead of +/-FLT_MAX, the
0x306854 trap site is gone, the collision free list stays non-empty (0xdf3538) and the player
holds y = -120 on the terrain instead of falling. The camera follows the mission intro fly-by at
(-3787, -109, ...) exactly where PCSX2's trace has it at t=202-207 s. The fly-by had not finished
by the end of the 320 s run because the game still runs at a few frames per second (VU1
interpreter); the gameplay camera (939, 8.3, ...) needs a longer run.
Along the way the FPU comparisons now flush denormals (hardware behaviour; not the cause here).

## 2026-09-08 13:30 (local) — the fall through the floor: collision grid collapse traced to exploding actor orientations
Guest-memory comparison against a PCSX2 savestate (`tools/pcsx2` + PINE work locally; the state
file's eeMemory.bin is zstd inside a zip, `logs/parity/spawn_pcsx2.rdram`) versus our
`PS2X_RDRAM_DUMP` images:
- After the level load our collision grid (world+0x684: 36x25 cells, 8192-node pool, cells at
  +0x30, free list at +0x38) is identical to PCSX2's: 3566 nodes, 1262 objects.
- At ~182 s the four squad-member collision nodes get rotation rows saturated to +/-FLT_MAX
  (translation sane), so `FUN_002d7580` inserts each into all 900 cells; the pool drains, the next
  insert links a null node and cuts the cell chain; the terrain leaves the grid, the ground probes
  return nothing and the player sinks (PCSX2 holds the player at y=-126.26, ours rests at -131.4).
  The camera runaway during the intro shots is the same objects (the camera follows them).
- The node matrix is copied from the actor's own matrix (`FUN_00315820`, called from
  `FUN_005483d0` at ra 0x549910); the actor's orientation quaternions (object+0x54/+0x5c and
  +0x74/+0x7c, class vtable 0x6691a0) jump from (-0.383, -0.924) to exactly 2^64 in every
  component. 2^64 == sqrt(FLT_MAX): a saturated maximum went through a square root, i.e. a
  division by zero happened on ours and not on the console.
- Census of saturated words: ours 798 at load / 1306 at rest, PCSX2 18. 33 heap objects of
  class 0x408330 (scene/bone nodes) hold 24 saturated matrix words each already at load.
- The EE FPU trap (`PS2X_FPU_TRAP=1`: divisions by zero, square roots of a saturated operand,
  with the guest pc) fired zero times in a full run, so the overflow originates in VU0 macro-mode
  math or a VU microprogram; traps for those are in the build being tested.
Tools added on the way (commit 91e7588): pointer-chain `PS2X_PEEK`, `PS2X_WATCH` word poller,
`PS2X_WATCH_HUGE` range scanner, `PS2X_HOST_PROF` sampling profiler, `PS2X_VU_STATS`,
`tools_py/parity/cam_poll.py` (PINE chains).

## 2026-09-08 10:30 (local) — intro movie seam fixed; in-mission camera diverges because the VU1 interpreter caps the game at 3 flips/s
**Movie seam (commit df9f8fe).** Render-target downloads wrote all 1024 texture columns back into
VRAM; past FBW*64 the page arithmetic lands in the *next* page row's first columns, so the black GPU
rows 64..96 of the movie staging buffer (FBW 10) overwrote frame rows 96..128 of page columns 0-5
after every upload — the x=384 seam on every intro-movie frame. Downloads now stop at FBW*64.
Found with a per-command shadow-VRAM probe (PS2X_GS_TRACE_PRESENT=-1 arms it from the first
seam-like decode; negative values count from the first movie block upload).

**EE FPU / VU float semantics (uncommitted, needs `./build.sh recomp`).** The generated code used
IEEE math; the EE FPU and the VUs have no infinities or NaNs (overflow saturates to +/-FLT_MAX, x/0
gives +/-FLT_MAX, denormals flush to 0, SQRT takes |x|). FPU_* macros, the DIV/RSQRT emitters, the
PS2_V* macros and the VDIV/VSQRT/VRSQRT emitters now saturate (VRSQRT also ignored its numerator
register before). The archived menu camera showed the effect: fog coefficient
`255 - near * (-255 / (far - near))` with far == near is 255 on the PS2 and NaN under IEEE.

**In-mission picture: camera, not renderer.** PCSX2 (tools/pcsx2, PINE port 28011) runs the
mission script fine — `tools_py/parity/cam_poll.py` reads the camera object (`*(0x488de8)`, static
scene 0x4887c0 + 0x628) over PINE while `drive --target pcsx2` runs; ours uses
`PS2X_PEEK="*0x488de8+0x320:3"` (peek now dereferences pointers). Fog block, frustum, view matrix
and spawn position match PCSX2 word for word at spawn. Then ours lets the camera height decay
(8.8 -> 3.1 in one second; PCSX2 holds 8.35) and the position grows exponentially to +/-FLT_MAX for
~22 s (the scripted shots), returns to spawn, and the later scripted move happens on both sides.
The sky-dome-from-below frames are that runaway camera.

**Root cause of the divergence: frame time.** `FUN_003aff30` (flip) reads T0 as the frame time and
resets it; the camera update `FUN_002998f0` integrates with it. Per-second flip counts (call trace
on 0x3aff30) are 2-16 in the mission (PCSX2: 60). A host-level sampling profiler
(`PS2X_HOST_PROF=<ms>` + `tools_py/hostprof_symbolize.py`) puts ~80% of the game thread in the
VU1 interpreter's cycle-exact bookkeeping (`calculatePairReadyCycle`, `commitReadyPipelines`,
long-double FMAC rounding); `PS2X_VU_STATS=1` measures 4-7 M VU1 cycles/s at 120 ns/cycle,
i.e. ~1 M VU1 cycles per game frame, 0.5-0.8 s of host time per second. Ruled out on the way: the
scratchpad slow store path (fast path added anyway), the GS command queue (no backpressure),
guest-clock overhead. A 60 fps mission needs ~16 ns/VU1 cycle: a VU1 recompiler/JIT, not
interpreter tuning (2-3x at best from mask-based hazard checks and an early-out commit).

**Interim fix in progress:** guest time must exclude the host time spent in the VU1 interpreter
(`ps2GuestClockExcludedNs`, subtracted in `EeScheduler::accountCycles`), so the game sees ~1/60 s
per frame and runs in slow motion instead of integrating a 300 ms step (a per-gap cap did nothing:
the interpreter runs in ~1000-cycle slices). Result: see the next entry.

## 2026-09-08 (local) — our exe completes the SCERT handshake with Horizon; menu movie merged
Two fronts landed since the 22:40 entry.

**Menu background movie (merged to develop, commits 8c01711/1f15173/db44f62).** The runtime already
had an FFmpeg-backed sceMpeg HLE; two protocol gaps (sceMpegCreate not zeroing the libmpeg work
buffer, and GetPicture parking the only feeder thread) stopped every movie. Fixed in
Kernel/Stubs/MPEG.cpp. Main-menu parity 81.0 -> 98.8; the Sony/intro/cinematic movies play too.
Boot now has two more screens than before, so the online script uses five boot presses.

**Exe online netstack (uncommitted until this entry's commit).** From black-screen after the network
IRX loads to a completed SCERT TCP handshake with the real MUIS (10071). Layers:
- SIF sreg handshake echo (socom2_SifSendCmd) and msifrpc init/bind/call/unbind HLE.
- eznetcnf/eznetctl IOP service (ps2xIOP/src/modules/eznetcnf.cpp): one "Setting 1" combination,
  interface always up. DNAS tick (FUN_002cc670) reports done.
- libnetb (socom2_libnetb.cpp): the simple RPCs (sceInetCreate/Open/Recv/Send/Name2Address/poll/
  interface events) and the libnetb_ex ring path (FUN_002472c8/74f8/7738/7d30/7fe8/79b8/7bd8)
  replaced by host Winsock (socom2_hostnet.cpp). Contract: docs/research/10-libnetb-rpc.md.
- rt_crypt on the host (socom2_crypto.cpp): 512-bit RSA modexp (FUN_0062b948), SHA-1 prefix
  (FUN_0062eec0) and the RC4 variant (FUN_0062a638/5a8/720/7c8). The fixed client keypair
  (socom2_rsa_key.h) was regenerated as a FULL 512-bit modulus: a 511-bit N let the server's
  512-bit RC4 session key exceed N and broke the CONNECT_TCP decrypt.
Result: the exe resolves the retail hostnames to PS2X_SOCOM2_SERVER (default 127.0.0.1), connects
TCP to MUIS, the server accepts CONNECT_TCP and sends CONNECT_ACCEPT + CONNECT_COMPLETE, the
client sends the LobbyExt/0x03 universe query and shows SELECT UNIVERSE with the Horizon universe
and its news (2026-09-08). Later the same night the exe logs in (MAS), reaches the lobby (MLS),
joins Channel 1 and hosts a game: GAME LOBBY with a live DME world (TCP + aux UDP), driven by
`tools_py/parity/online_login_ours.py --existing --host`; parity 98-99 vs the PCSX2 golden set.
**02:40 — a full online match between two instances of our exe** (`online_match_ours.py`: A hosts,
B joins and switches team, both READY → VIGILANCE/SUPPRESSION → in mission; Horizon world
WorldStaging → WorldActive). The second instance uses PS2X_WINDOW_TITLE / PS2X_MC_DIR /
PS2X_SOCOM2_UDP_SHIFT. M5 (online lobby + match against our own server) is reached. The earlier stall was the frozen COP0 Count: `mfc0 Count` reads
ctx->cop0_count, which nothing advanced, so SCE-RT's clock stayed at 0 and the connected-state
send gate (30 ms since the last flush) never opened; the runtime now refreshes cop0_count from the
host steady clock at 294.912 MHz on every syscall and scheduler switch-in.
Driver: `python -m tools_py.parity.drive --target ours --script scripts/parity/launch_to_online_ours.txt`
with the Horizon stack up (no dns_stub needed; the exe resolves internally).

Reference: tools/reference/reCOM (git-ignored) and docs/research/11-recom-applicability.md map
~70 of our FUN_ addresses to SOCOM 1 / GameZ names.

## 2026-09-07 22:40 (local) — our exe reaches LOGIN TO SOCOM II ONLINE (netstack bring-up started)
ONLINE on our exe used to go black after loading the network IRX set. Three layers were missing:
- SIF sreg handshake: msifrpc's init sends SETSREG (0x80000001) to the IOP and spins on the EE
  sreg table until the IOP module echoes it. `socom2_SifSendCmd` mirrors the write (sreg table
  at 0x1da6c0). `sceSifGetSreg` is not stubbed — it is the game's own code reading that table.
- msifrpc (multi-SIF RPC, SCE-RT's transport for libnetb, service 0x80001201): init/bind/call/
  unbind (FUN_001bcd80/1bd050/1bd320/1bd200) are replaced by host handlers; the call is answered
  synchronously by `socom2LibnetbCall` (for now every fno logs and returns -1). EE ABI: args 5-8
  in t0-t3.
- eznetcnf/eznetctl (0x75499128/0x75488909) are a new ps2xIOP service
  (ps2xIOP/src/modules/eznetcnf.cpp): one "Setting 1" combination, interface always connected.
- DNAS: FUN_002cc670 bound to ret0 (the pnach's `jr ra` equivalent).
The login screen appears; it still says "No Network Adaptor detected" because libnetb fno 8
(interface list) / fno 9 (interface control) return -1. Reverse-engineering of the libnetb RPC
contract (LIBNETB.IRX decompiled to game/analysis/LIBNETB.IRX.decomp.c, spec going to
docs/research/10-libnetb-rpc.md) is in progress; the socket layer (Winsock) comes next.
Driver: `python -m tools_py.parity.drive --target ours --script scripts/parity/launch_to_online_ours.txt`.
Reference: tools/reference/reCOM (git-ignored clone of NotEnoughPhotons/reCOM, a SOCOM 1/2 +
GameZ decomp with demo-disc symbol names) for naming engine functions.

## 2026-09-07 21:10 (local) — ONLINE MATCH: two PCSX2 clients play VIGILANCE on the local Horizon stack
`python -m tools_py.parity.online_match` logs two retail clients in (socom / socomb), A creates a
game (Medley play list), B joins it, B switches team, both press READY and the match launches:
both screens show VIGILANCE / SUPPRESSION in-game with the round timer (logs/parity/online/match/,
A_18_hold05 and B_20_hold05). DME world with two clients, TCP + aux UDP, broadcasts flowing.

Fixes since the 18:45 entry (commits a2fdc45, 1ce3047, and the match commit):
- Lobby/0xEC channel list request + 0x70-byte 0xED entries (briefing rooms).
- CreateGameRequest1: Attributes optional (1.50 sends 0xD0 bytes).
- Game.OnWorldReport(MediusWorldReport0) copies GameStats — the 1.50 client keeps map/rounds
  there; without it the joiner shows "unknown" and refuses to join.
Second client plumbing (tools/pcsx2_b, git-ignored; templates in scripts/parity/pcsx2/):
- robocopy of tools/pcsx2 with PINESlot 28012, Slot2 memory card disabled.
- Its own savestate 5 of the LOGIN screen made by booting it (main menu → ONLINE): a state copied
  from the other install re-probes the card on load and drops the network configuration.
- Its card already holds A's persona, so the persona list needs Up, Cross, Down, Cross.
- Two guests on one host adapter both bind host UDP 3658/3659 (PCSX2 Sockets mode) and DME replies
  went to the wrong socket; a B-only pnach changes `li a0,0xE4A` at 0x620678 to 3660. (The
  host-only adapter alternative fails: Windows strong-host routing, no admin for weakhost.)
Still unhandled by Horizon and harmless so far: Lobby 0x86, 0xB2, 0xCE, 0xEF, LobbyExt 0x08.

Next: our exe. The PS2 side is now fully characterised (every request/reply the 1.50 client needs
is in server/logs); bring the recomp's inet/netcnf HLE up (Winsock) so socom2.exe reaches the
same screens, scored by the harness against these PCSX2 captures.

## 2026-09-07 18:45 (local) — online: a PCSX2 client logs into Horizon and reaches the SOCOM II ONLINE lobby
Priority is online play (user, 21:30 entry in HANDOFF). Result tonight: the retail client running in
PCSX2 goes LOGIN → LOCATING UNIVERSES → SELECT UNIVERSE ("SOCOM II Local", news text) → CONNECT TO
SOCOM II (persona/password typed on the on-screen keyboard) → ACCOUNT LOGIN → USER AGREEMENT →
SOCOM II ONLINE lobby with the SERVER NEWS popup from Horizon. Screens: logs/parity/online/login/.

Plumbing (all under tools/pcsx2, git-ignored; templates in scripts/parity/pcsx2/):
- DEV9 Sockets on the Realtek adapter, InterceptDHCP, manual DNS = 192.168.2.10 (host LAN IP).
  PCSX2's [DEV9/Eth/Hosts] table was not honoured, so `tools_py/parity/dns_stub.py` answers the
  game's hostnames (socom2-prod[.muis].pdonline.scea.com, gate1.*.dnas.playstation.org) on UDP 53.
- DNAS bypass pnach (unconditional; labelled groups are opt-in and were skipped).
- Memory card recreated with mymcplus (the original was unformatted) and a saved network config.
- Horizon configs advertise 192.168.2.10, not 127.0.0.1 (the guest cannot reach loopback).
- Savestate 9 = the LOGIN TO SOCOM II ONLINE screen. Only this state is usable: states saved after
  any network traffic restore with a stuck SMAP transmit ring (BD_TX storm) or dead input.

Protocol fixes in Horizon (commit e990033), found by reading the 1.50 client library in the decomp:
- Universe query is LobbyExt/0x03 → ExtraInfo list LobbyExt/0x04 (0x338 bytes) **and** a
  UniverseNews reply (Lobby/0xC9); completion needs InfoType == accumulated bits (DAT_006561b0).
- AccountLoginResponse must be exactly 0xC4 bytes: NetConnectionInfo's 2-byte alignment pad is
  now unconditional (the PS2 client sends no CLIENT_HELLO, so Horizon assumed version 108).
- The client's VersionServer request (Lobby/0x86) can stay unanswered: no game callback.

Method that worked: handler ids are assigned sequentially per class by FUN_0063c8a0, so id N of
class 1 is the N-th registration after line 564046 of the decomp; the handler returns the expected
byte count. Reading the slot table over PINE (e.g. 0x686f14) gives the live ids.

Unhandled by Horizon so far (client still proceeds): Lobby 0xB2 FileListFiles (WeapProfile_1.dat),
0xEC ChannelList_ExtraInfo0 (lobby room list — needed next), 0xEF LadderList_ExtraInfo0,
LobbyExt/0x08 GetBuddyInvitations, Lobby 0x86 VersionServer.

Next: close server news → BRIEFING ROOMS (channel list) → create/join a room; then a second
PCSX2 instance (separate ini/memcard/PINE port; the "never two instances" rule is about our exe
sharing logs, but two PCSX2 processes also need distinct DEV9 MACs) and a match through DME.

## 2026-09-07 20:00 — roller renders; mission renders textured; report ours_e
After un-stubbing libvu0 (commit fb97a7b): the main menu shows the 3D roller with LOAD GAME /
NEW GAME / ONLINE (menu 79 → 81; the MENULOOP.PSS movie background is still black), popup 99.6,
select rank 99.0, briefing 96.4, and the mission frame is now textured (rock walls, timber) instead
of flat grey — the same wrong-order matrix maths had been feeding the mission's transforms.
`scripts/parity/align.json` shifted by one step (our side now captures an extra early frame).
Still open on the shell: the menu movie background; the controller-configuration screens (our
step after Select Rank is a black frame where the original shows two screens with 3D controller
models). Mission: camera/HUD/movement not yet looked at.

## 2026-09-07 19:30 — main menu roller: culled by a wrong clip matrix from the libvu0 HLE
Chain of evidence (all at the real main menu, two presses; the earlier "menu" numbers in this file
were taken one press too late, on Select Rank): the roller model loads (23 mesh parts under a
type-2 node with 12 leaf children, bbox ±13.7), is added to the scene (`FUN_0031f240`) and is handed
to the node draw `FUN_0033b110` every frame — identical node/scene state to PCSX2 read over PINE.
The children traversal `FUN_003389c0` then asks the frustum test `FUN_00290c30` and gets 2
("fully outside") every frame, so no leaf part is ever submitted (`xgkick=0` at the menu). The
camera object (static path `0x4887c0+0x628`) matches PCSX2 word for word except the clip matrix at
+0x330: rows 0-1 equal, ours rows 2-3 = `[-320 0 319 1] / [0 0 0.40 0]` vs PCSX2
`[0 0 -1.004 -1] / [-457 0 320.9 320]`. `FUN_00294070` builds it as
`sceVu0MulMatrix(clip, proj, viewInv)` and PCSX2's result is viewInv·proj, so the HLE stub in
`Kernel/Stubs/VU.cpp` multiplies in the wrong operand order (its "ViewScreenMatrix" and friends are
guesses too). Fix: stop hand-emulating libvu0 — the 29 `sceVu0*` stubs are removed from
`recomp/socom2.toml` and the uncovered entry points forced in `recomp/extra_functions.txt`, so
Sony's own VU0-macro code runs (safe now that vf00 writes are ignored). Recomp rebuild pending
verification: popup placement must stay, the roller and the controller-config models should appear.
Side note: camera +0x130 holds NaN on ours vs 255 on PCSX2 (a clamp/lerp path), unexplained.

## 2026-09-07 18:10 — mission thread no longer dies (merged Ghidra range)
With `recomp/merge_ranges.txt` folding 0x510970-0x5109a8 (the while-loop whose body Ghidra had
left in a gap between a "thunk" row and the loop condition), the 400 s mission run shows
`MissionTick` #1560 at 305 s and zero `[guest-branch:missing-target]` (it used to halt ~30 s into
the mission, around tick 660). Geometry keeps flowing (`xgkick` 1.5M by frame 2685) and the frame
stays a flat-shaded blue-grey world from a fixed camera: no textures, no HUD, no visible camera
motion yet — those are the next mission items once the shell screens are scored ≥90.
`tools_py/find_escaping_branches.py` found only two functions with this split-loop shape; the
other (0x534c4c) is a real multi-entry function and is left alone.
Caveat: two 400 s runs of this build overlapped by accident (a background wait loop launched
one 13 s before the hand-started one: `run_20260907_154947.log` and `_155000.log`). Both show
zero `missing-target` and ticks continuing to the end (#1800 / #1560), which is a control-flow
result and holds; their frame-rate and counter values are skewed and should not be quoted.

## 2026-09-07 17:00 — the shell looks like the original (text, placement, palettes fixed)
Parity report `ours_d` (docs/parity/REPORT.md): memory-card popup 99.6, select rank 99.2,
mission briefing 96.2 (all text, tabs, fireteam loadout, typewriter effect), main menu 79.1
(soldier background art and the roller captions still missing), warning screen 78 (animated;
capture timing). Four fixes, each verified with the popup screenshot and then the full run:
1. **vf00 writes** (recompiler, `instruction_translator.cpp`): the game's `qmtc2.i $a0,$vf0` /
   `vaddx vf0,vf0,vf0x` / `lqc2 $vf0` idioms are no-ops on hardware; we executed them and every
   `vmaddw … vf0w` translation term went to garbage — all 2D elements sat at the origin.
2. **Face culling** (`gs_gl_backend.cpp` setupDrawState): raylib's rlglInit enables GL_CULL_FACE
   and the GS backend never disabled it; glyph sprites (second vertex above the first) have the
   opposite winding and were culled. Diagnosed with the new `PS2X_GS_GL_DEBUG_PSM=<psm>` print
   (state, bound texture texel, region readback before/after the draw: "0 of 216 pixels changed").
3. **CSM1 CLUT swizzle** (GL): 4-bit palettes are 8x2 blocks, address bits 3/4 swapped; the GL
   resolver read a linear strip, so the bright half of every 4-bit palette was wrong (dim text).
   The CPU rasterizer already had `swizzleClutIndexCSM1`.
4. **CPU sprites** swap texcoords with corners (text was flipped on the reference rasterizer).
Also: `recomp/merge_ranges.txt` (+ `fix_ghidra_csv.py`) folds the split loop 0x510970-0x5109a8
that killed the mission thread; recomp rebuild pending verification.
Remaining shell gaps (next by score): main menu background art + roller captions; the
controller-configuration screens (our s04 is black where the original shows two screens — likely
the same class as the menu art); the text-only title cards flash past on our side (not captured);
glyphs render slightly heavier than the original (shadow pass alpha?).

## 2026-09-07 — mission draws; parity harness is the grade; two systemic UI bugs found

**Mission (M4):** the "renderer submits nothing" blocker was thread starvation, not rendering.
Thread 2 is the priority-4 auto-exposure thread (`FUN_003b1dd0`) which, once a mission is up, reads
~176 framebuffer pixels per pass with `FUN_003b24c0` (GS local→host through the VIF1 reverse FIFO).
The runtime has no reverse-FIFO path, so each read spun to its 16M-iteration timeout (~0.3 s) and
the main thread got one tick per minute. `FUN_003b24c0` is stubbed at recompile time
(`socom2_LumReadPixel@0x003B24C0`, mid-grey pixel). Result: `MissionTick` ~20/s after the load,
geometry counters climb (xgkick 4k → 700k), flat-shaded world polygons and a night sky on screen —
the first in-mission frames. ~30 s in, the main thread dies at 0x510978: a list-search loop whose
head Ghidra split into an 8-byte "thunk" row, so the backward branch becomes an unwind to an
address no function owns (`[guest-branch:missing-target]`). `tools_py/find_escaping_branches.py`
lists every such branch (35k in 1.1k functions, mostly harmless case chunks); the fix is to merge
rows whose branch target is not another row's entry. Queued behind the shell parity work.

**Parity harness (the new grade, see HANDOFF "The grade"):** `tools_py/parity/` — `winshot.py`
(PrintWindow capture, no focus), `keys.py` (posted keys to PCSX2's Qt window or our raylib window,
both accept them without focus), `drive.py` (one step script for both sides, `next` = wait for a
new settled screen, screens labelled by step index), `compare.py` (score + side-by-side diff +
`docs/parity/REPORT.md`), `pine.py`/`addresses.py` (PCSX2 PINE memory reads, escalation aid),
`montage.py`. PCSX2 2.8.1 in `tools/pcsx2` with PINE on 28011; its card was formatted offline with
`mymcplus` so the save prompts do not loop. First report (`ours_a`): 6 of 20 golden screens have a
matching screen on our side; our sequence skips the loading screen, the "No SOCOM data" notice and
the three text-only title cards (all black), draws the main menu as logo-only, and reaches the
briefing. `scripts/parity/align.json` maps golden steps to ours by content until the sequences
converge.

**What the first side-by-side proved (GS command trace at the memory-card popup):**
1. **Text is submitted, not missing.** Glyphs are tiny textured sprites (4-bit PSMT4 font page
   512x128 at tbp 0x3bf7, CLUT at 0x3bf3) drawn with the second vertex *above* the first. The CPU
   rasterizer drew them vertically flipped because `DrawSprite` swapped the corner coordinates
   without swapping the texture coordinates — fixed (text now upright with `PS2X_GS_BACKEND=cpu`).
   The GL backend still draws nothing for them (decode of the 4-bit page is correct — verified with
   `PS2X_GS_DUMP_TEX`; the difference from the 8-bit box that does draw is not yet understood).
2. **Every 2D element is drawn at the origin.** The popup box is submitted at (0,0)-(340,100) and
   both slot buttons at (0,0); the element drawer (`FUN_003643b0`) transforms its local rect through
   the node matrix with `FUN_00308640`, whose translation term is `vmaddw.xyz vf9, vf7, vf0w`. The
   recompiled game *writes vf00*: `qmtc2.i $a0,$vf0` (an interlock idiom, e.g. 0x30702c/0x3076b4
   right next to the transform helper), `vaddx vf0,vf0,vf0x` and `lqc2 $vf0,…($k1)`. On hardware
   vf00 is the read-only constant (0,0,0,1); we clobbered it, so every translation multiplied by
   garbage. Fix in `instruction_translator.cpp`: writes to vf00 are emitted as comments (recomp
   rebuild in progress at the time of writing — verify with the popup: box centred, logo centred).

**Docs/process:** HANDOFF gained "The grade" (parity loop, rules, escalation triggers) and gotchas
7-9; spec `docs/superpowers/specs/2026-09-07-parity-harness-design.md`, plan
`docs/superpowers/plans/2026-09-07-parity-harness.md` (with the design simplification amendment).


## Milestone board (from the design spec)
| # | Milestone | State |
|---|---|---|
| M1 | Fork + toolchain: merged ELF recompiles, runtime links, `socom2.exe` runs crt0→main | **done** |
| M2 | Loader → game entry → engine init without unimplemented-instruction faults | **done** — engine runs its main loop; audio init + DBCMAN reached |
| M3 | Legal/intro screens + main menu render, pad works, UI sounds | **done for navigation** — first boot runs to the main menu at 60 fps, input drives every shell screen; button captions and the 3D roller still do not draw |
| M4 | Single-player mission playable | **in progress** — the Albania 5-1 mission loads from the briefing screen and its engine, AI and mission scripts run at 60 fps; the in-mission renderer submits no geometry |
| M5 | Online: login/lobby/room on local Horizon, second client joins | server side ready; client side not started |
| M6 | Portable package | not started |

## What works today
- Full plaintext game code recovered (FTSCore.bin @0x1e7000, ZSealEtc.bin @0x4c5380; build id "SOCOM 2 r0001 17:22:21 Oct 11 2003"), see `docs/research/05-code-package-and-harness.md`.
- `./build.sh recomp && ./build.sh runtime` produces `dist/socom2.exe` (~160 MB, 14.7k generated functions). Build cycle: 10 s recomp, ~15 min full compile, ~3 min runtime-only.
- The exe boots the loader: memory-card check (DBCMAN/MCSERV HLE), skips the DNAS decrypt (override), restores the overlays after the loader's bss wipe, runs both overlays' static constructors, jumps to the game entry (0x4c53c0 → FTSCore main 0x1e7040), reads the ISO volume descriptor and builds the engine's disc TOC from the ISO (`IoPaths.cdImage`).
- Diagnostics: `PS2X_PC_SAMPLER=<s>` prints live guest PC + thread table (pc/ra/sp/status/wait) every s seconds; the runner window has a built-in debugger UI (CPU/Threads/Kernel/RPC/GS tabs).
- PCSX2 2.8.1 + BIOS (`tools/pcsx2`) boots the ISO; reference log in `logs/pcsx2_reference_boot.txt` (IRX load order, timings).
- Horizon Private Server runs locally for app id 10472 (`server/README.md`, `server/start-servers.ps1`; simulated DB, account socom/socom; the game's baked-in RSA key matches Horizon's).
- 989snd IOP service first version (`ps2xIOP/src/modules/snd989.cpp`, protocol in `docs/research/06-989snd-rpc.md`): answers all RPCs with correct framing, models banks/voices/streams, serves stream-safe CD reads; no audible output yet (host backend is libsd-only).

## 2026-09-06 02:15 — the first single-player mission loads and runs (M4 opened)

Driving the pad script `8:CROSS,12:CROSS,16:CROSS,20:CROSS,24:CROSS,30:DOWN,32:DOWN,34:DOWN,
36:DOWN,38:DOWN,41:CROSS` now walks the whole single-player entry: first boot → main menu →
NEW GAME → dlgSelectRank → dlgControllerPresetsNewGame → dlgControllerPresetsRG →
dlgAlbaniaCinematic → **dlg_Brief_Alb51** (the Albania 5-1 briefing, which draws its real
photo panels) → five DOWN presses move the briefing selection from `overview_button` to
`deploy_button` → CROSS fires `OnDeployActivate` → `LoadMission` → `LOAD_SCREEN` → the mission's
own systems register (`CClutterAnimManager`, `diTick`, `Mission`, `ParticleTick`, `UnitTick`,
`ai_pre_tick`, `entity_pre_tick`, `weapon_pre_tick`) and the level's AI scripts start
(`Supply1-4_start`, `Informant_start`, `Sniper1/2_start`, `Alarm1-4_start`, `PatrolWatch_start`,
`set_iris`, `otc_init`). Zero `[guest-branch:missing-target]`, and the engine holds 60 fps.

Four fixes got there, in order:

1. **The EE dispatcher mistook a scheduler unwind for a return** (commit 2acef9c).
   `dispatchGuestBranch` decided "the callee returned" by comparing `ctx->pc` with the entry pc it
   dispatched to. A callee that leaves through a scheduler checkpoint while its pc still equals its
   own entry address is indistinguishable that way, so the caller resumed with the *callee's*
   registers. That is what killed the EE thread when dlgMenu loaded: the 2D-node lookup
   `FUN_00315a80` called from `Add2dNode` (`FUN_0036ab20`) came back with s1 = 1 and the caller
   dereferenced `screen+0x60` through `0x1` → `missing-target target=0x14 ra=0x36abc0`. The runtime
   now carries an explicit unwind flag (`markDispatchUnwind` / `clearDispatchUnwind`) that
   `eeCheckpointDue`, the non-call path and the missing-target path set and the scheduler clears
   before every dispatch. 5 of 5 runs reach dlgMenu with all 17 of its controls created.

2. **Interrupt handlers ran on the interrupted thread's stack** (commit 3eb4285).
   `AddIntcHandler`/`AddDmacHandler`, `SetAlarm` and `sceGsSyncVCallback` registered the *caller's*
   sp as the handler's sp, so a handler firing later trampled live frames of whatever that thread
   was doing. They now pass sp = 0, which makes the scheduler allocate its per-(thread, depth)
   invocation stack — the same stack every other invocation kind already uses. This reduced the
   dlgMenu crash rate but was not its root cause (that was item 1); it is still a real bug fixed.

3. **136 function bodies Ghidra never listed** (commit 1754184). `tools_py/find_gap_functions.py`
   walks the gaps between CSV function ranges and reports every gap whose body contains `jr $ra`,
   skipping anything `socom2.toml` stubs. A register-dispatched call into one of these found no
   recompiled target and silently did nothing (gotcha 1). The 4-instruction leaf at 0x346300 was
   hit during "new game" and ended the run. Same commit: `ControlFlowEmitter::emitStaticJump` was
   emitting `goto label_X` for a JAL whose target is one of the function's own entry points, so a
   self-recursive call ran in the caller's host frame and its `jr $ra` returned out of the host
   function — 97k scheduler unwinds in a single 24 s menu run, all from the rdr tree search
   `FUN_0032f0e0`. A JAL is now always emitted as a call.

4. **Six merged Ghidra ranges whose second function is called by pointer** (commit 316dafd).
   `tools_py/find_interior_functions.py` looks inside every CSV range for a `jr $ra` + delay slot
   followed by more code, and keeps the boundary only when that address is actually referenced — as
   a JAL target, as a 32-bit word in the image, or as an address built by a `lui`/`addiu` pair.
   That reference test is what separates a real second function from a second return point: 362 raw
   boundaries reduce to 6 referenced ones. `fix_ghidra_csv.py` now truncates the parent range at a
   forced entry inside it so the two do not overlap. The one that mattered: the static-array
   construct helper at 0x181fb4 calls the element constructor 0x5550c0, which lived inside
   `FUN_005550b0`'s range and blocked the mission load.

**Correction to the previous handoff:** "all UI positions resolve to (0,0)" is wrong. Dumping guest
RAM at the moment dlgMenu's CONTROLS list loads (`PS2X_RDRAM_DUMP_AT`, then `tools_py/rdr_tree.py`)
shows the parsed tree carries the real values — `new_game_button` XPOS 256 YPOS 330, `SplashLogo`
70/45 — the 17 design records built from it hold the same numbers, and the 2D nodes created from
those records have them at +0x30/+0x34 as floats. The SOCOM II logo does draw at its correct
position. What is actually missing on the menu is the button *captions* (their rdr CAPTION is a
single space; the text comes from elsewhere) and the 3D roller.

**Where it stops now:** in the mission, `FUN_001ebed0` (the in-mission tick — the previous handoff
said it is never called, which was true only before the mission could load) runs, but the frame
counters freeze at the values they had in the shell (`vif1codes=399073`, `mscal=22426`,
`xgkick=4421`, `nonBlack=0`), so the in-mission renderer submits no new geometry. The EE main
thread (1) goes dormant when the mission starts and the mission runs on thread 2; sampling shows
that thread spending essentially all its time at the resume point 0x2716e0 inside `FUN_00271650`,
a recursive scene-graph walk, with a *constant* guest sp (so it is not runaway recursion).

New diagnostics this session: `PS2X_JALR_TRACE="0xSRC,..."` (resolved target of the indirect calls
issued from those pcs), `[ret-clobber]`/`[ret-unwound]` lines from the `PS2X_CALL_TRACE` thunk (a
traced function returning with a callee-saved register changed / leaving through a scheduler
unwind, in which case its `[ret] v0` is not its result), `PS2X_RDRAM_DUMP="<path>:<seconds>"` and
`PS2X_RDRAM_DUMP_AT="<path>:<TracedName>#<n>"` (32 MB guest RAM to a file), and
`tools_py/rdr_tree.py` to print a parsed .rdr tree out of such a dump.

## Where the guest is now (2026-09-05 03:20)
Progress today, each a runtime fix: alarm handler discovered (main thread wakes) → all IRX modules load in the PCSX2 order → `lgaud` service answers lgAudInit (version 1.08, no headset) → `usbkb` bind → engine's scratchpad MFIFO renderer path implemented (fromSPR/toSPR DMA + ring drain; see research doc) → 989snd sound-system init runs through the service → `GetRomName` crash fixed (one-argument syscall) → the SCE-RT rt_crypt library generates a 512-bit RSA key pair at startup (two 256-bit primes by trial; takes minutes under recompiled code) → replaced with a fixed precomputed key via a recompile-time stub (`socom2_RsaGenerateKeyPair@0x0062B168` in `recomp/socom2.toml`, key in `socom2_rsa_key.h`).

Lessons: `runtime.replaceFunction()` only affects calls that go through the dispatch table; direct `jal` calls are compiled as direct C++ calls, so hooks on directly-called functions must be recompile-time stubs (`handler@0xADDR` in the TOML, handler name added to `PS2_STUB_LIST` in `ps2_call_list.h`, implementation in namespace `ps2_stubs`), and the recompiler must be rebuilt because it embeds that list (`build.sh recomp` now always rebuilds the tools). The crash reporter (`[crash]` lines with module-relative frames; symbolize with `llvm-nm -n dist/socom2.exe`) and the PC sampler (`PS2X_PC_SAMPLER`) are the two diagnostics that found every issue above.

## Where the guest is now (2026-09-05 08:00) — engine main loop running
Two fixes this session unblocked the boot:
1. **EE INTC I_STAT (0x1000F000) emulation** (`ps2_memory.cpp` `raiseIntcStatBit` + write-1-to-clear read/write; `EeScheduler.cpp` raises bit 2 on VBlankStart, bit 3 on VBlankEnd; `ps2_runtime.cpp` raises the bit for drained INTC causes). The engine's vsync wait `FUN_001a3fb0` clears I_STAT bit 2 and polls until the next vblank sets it.
2. **94 truncated `[mmio]` overrides fixed** (`tools_py/resolve_mmio.py`). A prior auto-generated table had folded many hardware-register accesses to their `lui` high-half (e.g. I_STAT 0x1000F000 → 0x10000000, GS 0x10002010 → 0x10000000, DMAC 0x1000dxxx → 0x10000000), silently routing guest MMIO to EE Timer0. The resolver backward-reconstructs each base register via lui/ori/addiu within its Ghidra function and computes base+imm. The three I_STAT poll sites (0x1a3fcc/0x1a3ff0/0x1a4020) were among them.

Result: the vsync wait completes, thread 1 (main) advances through the frame loop, and the live PC now spreads across engine subsystems (FIFO kick 0x350ab0, render 0x3b7130, 0x33xxxx/0x32xxxx). Threads 2/3 park correctly in `WaitSema`/`SleepThread` waiting for work. The game reaches audio-system init (`snd_StartSoundSystem`, master volumes, reverb, voice groups all set) and calls **DBCMAN** (controller/memory-card manager) — the shell/menu init path. Reproduce: `PS2X_PC_SAMPLER=1 ./run.sh 40`.

## Where the guest is now (2026-09-05 13:00) — intro video plays
**The pad-path wedge is fixed and the game plays its intro** (`PS2X_SOCOM2_PAD=1 ./run.sh 45`: 2445
frames, ~250k/287k non-black pixels per frame, 989snd banks loading, zero guest faults). Commit
db51455; full write-up in `docs/research/08-controller-and-dbcman.md §Resolution`.

Root cause (not the "config loop" the previous status guessed): with the pad reported connected,
the native `sceVibGetProfile` wrapper calls `sceDbcReceiveData` every frame with an
*uninitialised* max-length in the reply buffer's count field (+0x08). Our DBCMAN stub never wrote a
reply, so the wrapper read that garbage back as the received byte count and memcpy'd it out of the
0x1d62c0 RPC buffer into the pad object — running through the heap and overwriting the global
texture registry (0x45c3c0) with loader code bytes. The texture loader (`FUN_00354670`) then
dereferenced code words as pointers → TLB-miss fault → the runtime silently raised a COP0 address
error and re-dispatched the same function forever (the "grind" at 0x32f174/0x3546d0).

Found with **lldb** (ships in `tools/llvm-mingw/bin`): attach or launch under `lldb.exe --batch`,
break on `runtime_error::runtime_error` to get the host stack of the first guest fault (host frames
are named `sub_XXXXXXXX_0xXXXXXX`, so the host stack *is* the guest call chain), peek guest memory
as `$rcx + <guest addr>` at a `sub_*` entry (rcx = rdram, rdx = R5900Context, GPR n at rdx+16*n),
and `watchpoint set expression -s 4 -w write -- $rcx+0x8668c8` to catch the writer. Scripts used:
see the research doc.

Fixes: (1) `ps2xIOP/src/modules/dbcman.cpp` answers every libdbc RPC with a consistent "one DS2 on
socket 0, nothing received" state (count 0 at +0x08 is the crucial part) and publishes the 32-word
link table to the SetWorkAddr address. (2) `ps2_runtime.cpp` Load*/Store* fault handlers now print
a rate-limited `[guest-fault] op vaddr pc ra sp a0-a3 s0-s1 v0 (what)` line — these faults were
100% silent before. (3) `recomp/extra_functions.txt` += 0x3b7cf0, a static-init element ctor
Ghidra missed (the one `[guest-branch:missing-target]` at every boot).

Correction to research 08: `untracked_stubs` in the TOML is **informational only, ignored by the
recompiler** (ps2xAnalyzer/Readme.md) — those functions run natively. That is why
`sceVibGetProfile`/`scePad2GetButtonProfile`/`scePad2DeleteSocket` reached DBCMAN at all.

Step 2 (verified: `./run.sh 60` with the pad on shows only boot-time CheckVersion/SetWorkAddr/DeleteSocket DBCMAN traffic, no guest faults, content drawing, disc streaming): HLE `scePad2GetButtonProfile`,
`sceVibGetProfile`, `sceVibSetActParam` as recompile-time stubs so the pad state machine in
`FUN_002da930` advances 0→1 (GetButtonProfile could never succeed natively: it reads the DMA buffer
that only the native `scePad2CreateSocket` registers) and libdbc stays idle.

## Where the guest is now (2026-09-05 14:30) — menu UI renders, host input works
**Keyboard/mouse/scripted input** (`socom2_host_input.cpp`, commit 7aa0981): arrows = d-pad,
WASD/IJKL = sticks, Enter/Backspace = START/SELECT, ZXCV = Square/Cross/Circle/Triangle, QE/13/24 =
L1R1/L2R2/L3R3; `PS2X_SOCOM2_MOUSE=1` maps motion to the right stick and LMB/RMB to R1/L1;
`PS2X_SOCOM2_INPUT_SCRIPT="8:START,16:DOWN,18:CROSS"` presses buttons at those seconds (log-driven
testing). START at 8 s skips INTRO_2.PSS; the game then streams MENULOOP.PSS.
`tools_py/iso_lbn.py <iso> log <run.log>` maps a run's disc reads to file names.

**The shell UI now draws** (commit 3c790b4): the slot/profile dialog ("SLOT MISSION RANK DATE
TIME") renders over the menu movie; XGKICK fires (6480 kicks by frame 825), no faults, no VU
errors. Three EE→VIF1 delivery bugs were in the way, found with `tools_py/vu1dis.py` + the VU/VIF
traces (details in `docs/research/07 §Resolution 2`):
1. DMAtag upper-half (VIFcode) transfer was unconditional for CNT/NEXT/CALL/RET/END and never for
   REF tags; hardware does it for every tag iff CHCR.TTE. The shell's eye vector (REF tag) never
   arrived, the VU backface cull rejected every UI triangle, no XGKICK.
2. DMAtag ADDR bit 31 (SPR) was dropped.
3. The HLE libdma sent chains with CHCR 0x185 (TIE) instead of 0x145 (TTE).

**Next bottleneck: the CPU rasterizer.** With the UI up the game submits ~370 sprites and ~1M
textured pixels per frame; `GSCpuBackend::SampleTexture` does a swizzled VRAM read plus a CLUT
lookup per texel (×4 when bilinear) so the frame rate drops to 13-17 fps (lldb shows the game
thread inside `DrawSprite`→`SampleTexture` from the guest's DMA kick — it is slow, not stuck).
Options: a decoded-texture cache keyed by (tbp0,tbw,psm,size,CLUT) with page-dirty invalidation,
or the M4 GPU backend. Also visible: the dialog's highlighted row renders as a striped bar
(likely a CLUT/format or alpha issue) — check once the frame rate is fixed.

## Where the guest is now (2026-09-05 16:50) — GPU backend, menu at 60 fps
**OpenGL 3.3 GS backend landed and is the default** (`GSGlBackend`, commits 939655b, f80a93b,
0a208a0; design + status in `docs/superpowers/plans/2026-09-05-gpu-gs-backend.md`). The game
thread records GS commands, the main (GL) thread replays them into per-framebuffer render targets
and presents the RT texture directly; two `GSCpuBackend` instances model VRAM (authoritative on
the game thread, a shadow on the render thread for texture decoding). The shell renders at a
steady 60 fps (`PS2X_GS_STATS=1`), vs 13-17 fps on the CPU rasterizer (`PS2X_GS_BACKEND=cpu`).
Diagnostics: `PS2X_GS_DUMP_TEX=<dir>`, `PS2X_GS_TRACE_CMDS=<skip presents>`, and
`PS2X_FRAME_DUMP` still works (Present blocks for a readback).

Observed with the traces: SOCOM II streams every UI texture through one VRAM slot (texture at
block 0x3bf7, palette at 0x3bf3, re-uploaded before each draw), so the texture cache re-decodes
per draw; the dialog panel textures have alpha-0 palettes and rely on vertex alpha; the only
visible difference from the CPU path is that the title logo stays visible behind the slot dialog
(plausible for the real game; verify against PCSX2 when convenient).

**Open:** the slot/profile dialog does not react to DOWN/CROSS/TRIANGLE/START from the input
script, and its list is empty (no saves). Traced (`PS2X_SOCOM2_PAD_TRACE=1`, commit after
0a208a0): the presses DO reach the game — `scePad2GetButtonInfo` is polled for the digital ids
0x00-0x0f and the pressure ids 0x14-0x1f, and each press shows as 0→1→0 (digital) and 0→ff→0
(pressure). MCSERV (`[MCSERV]` trace) is only ever asked op 0 (Init), 11 times; the shell never
queries card info. **Presentation bug (reported by the user as a smaller frame, black squares and flicker on the GPU
path; fixed 2026-09-05 17:55):** the runner was told the presented texture was 640x448 while the
render target texture is 640x1024, so raylib squeezed the whole target into the display rectangle
(picture squashed into the lower part, unused black rows visible, alternating targets flickering).
`HostFrameTexture` now reports the texture's full size and the runner draws only the top-left
presented rectangle. Depth textures are also cleared to 0 on creation now (were undefined).

The gate is in the shell's UI layer: every UI input site uses the pad only when the current
screen object's +0x114 (local player index) is 0 (`FUN_00592ac0`). Next step and lldb recipe in
HANDOFF. The pad state machine itself (`FUN_002d9ff0`: states 0/1/2/3 + timers) is verified to
work with the HLE input. Pad sockets: only the newest socket reports connected (the boot-time
controller-check socket is deleted by the game; the HLE never sees the delete).

## Where the guest is now (2026-09-05 18:40) — main menu reached, "new game" hand-off stalls
The "+0x114 player-index gate" theory above is dead: the presses work. What the shell shows after
START is the **main menu screen** (`dlgMenu.rdr` in `game/disc/RUN/UI/READERC.ZAR`: buttons
new_game/load_game/multiplayer/options/extras/LAN, the `SavedGames` list box with the
`popup_load.tif` panel, the SplashLogo, a 3D `mainmenu_roller` model). We only see the load-game
panel and the logo; the buttons and the roller are not drawn (open rendering question, see below).
The user confirms that panel is not what the real game shows there.

How it was found (all new diagnostics, env-gated, zero cost when unset):
- `PS2X_CALL_TRACE="0xADDR[:name],..."` (game_overrides_socom2.cpp): logs every call of the
  listed guest functions — time, a0-a3, f12-f14, ra, any argument that points at text — and the
  return value (`[ret] name #n v0=… f0=…`). Works through the dense function table, so direct
  JALs are caught. 320 slots. Traced set that decoded the shell: the **script binding table** at
  ELF 0x3dd4d4..0x3de1c4 (207 `{name, fn, 0, id}` rows, 16 bytes each — SetMission, SwitchMenu,
  SetMenuState, ReadyToLoad, LoadSavedGame, ListSavedGames, GetNumSavedGames, IsMemCardInserted,
  SuspendMenuInput, PlayMPEG, …; dump: `tools_py` one-liner in the 18:40 session, list saved in
  the scratchpad as script_bindings.txt) plus the **animation-sequence command table** registered
  by `FUN_0026a8e0(0x414bb0, "NAME", 0, create, execute, 0)` at decomp lines 106865-106930
  (OBJECT_OPACITY_FROM_TO exec 0x25f880, CALL_ANIMATION 0x25d550, ui::UI_COMMAND 0x2745a0 = the
  dispatcher for the binding table, OBJECT_ACTIVE_STATE 0x263aa0, IF 0x25e7a0 / ELSE 0x25e6d0 /
  ENDIF 0x25e6a0, CALL_SEQUENCE 0x25d270, …). `FUN_0034e6b0(delay, queue 0x49ea50, "event",
  node, arg)` schedules a named script event ("goto_menu", "UiprepMission1" …).
- `PS2X_CD_TRACE=1`: `[cd] SearchFile`/`[cd] Read`/`[fio] open` on stdout (the RUNTIME_LOG
  versions are compiled out). `PS2X_MC_TRACE=1` now prints GetInfo/Sync on stdout.
- `PS2X_PEEK="0xADDR[:words],..."` dumps guest words (hex + float) with every PC-sampler line.
- `PS2X_FRAME_DUMP` pixels were **stale** on the GPU path (the same frame re-reported forever) —
  do not trust the PPMs/`nonBlack` for "what is on screen"; `PS2X_HOST_SCREENSHOT=<dir>[:<s>]`
  saves what the window shows. Display-off presents (PMODE EN1=EN2=0) now blank the dump.

Shell flow observed (call trace, `8:START,16:CROSS`): boot → `do_onstart`, `intro_onstart`,
`load_initial_config`, SwitchMenu → START → `goto_menu` → SwitchMenu(5) → `menu_fade_up`,
`PulseArrows`, `UiStopAttract`, `SetMenuValve`, `has_memcard_changed`, `CleanupMissionMemory`,
`Ensure_MC_Dirs_Fast` (sceMcGetDir root, sceMcChdir, sceMcGetDir "BASCUS-97275SOCOMII" → 0),
GetNumSavedGames (sceMcGetDir SaveGame0..9 → none), `IF GotSaveGames > …` → then a 1.5 s
`has_memcard_changed` poll loop. CROSS = the **new_game_button** → event `UiprepMission1`:
SOUND, `SuspendMenuInput 0.75` (writes shell+0x900, decremented per frame in `FUN_003654c0`),
OBJECT_ACTIVE_STATE ×3 (menu objects → INACTIVE: this is why the screen goes black), then the
sequence engine stops ticking. The engine's main tick `FUN_001ebed0(dt, app)` then runs its
fade-to-mission countdown branch (`app+0xc8 -= dt; f = app+0xc8 * app+0xc4; f < 0 →
FUN_002a9a70(0x4364e0)` → push mission state 0x4086a0 via `FUN_002cf380(0x4084c0, …)`), but
`FUN_002a9a70` never fires (traced, 6 s). Current step: peek app+0xb8..+0xc8 and dt to see why
the countdown does not complete (app object address = a1 of the traced `FUN_001ebed0`).

Other facts: memory card HLE reports a formatted 8 MB card with no `BASCUS-97275SOCOMII` dir;
the game does not try to create it (Mkdir never called) — fine for now. After CROSS no disc
reads or fio opens happen. VU1 keeps running programs (mscal rises) but XGKICKs stop: the UI
packets carry the "no setup kick" flag (header.w bit 1 clear at microcode 0x30) and no vertices.

## 2026-09-05 19:35 — first-boot flow runs end to end; main menu reached (commit 60fe75c)
After the full recomp with 0x353d00/0x2a98a0 forced, `PS2X_SOCOM2_INPUT_SCRIPT="8:CROSS,12:CROSS,
16:CROSS"` drives: memory-card slot popup → "loading" warning → "no SOCOM data found" →
StoreOptions → Sony logo (SONY448.PSS) → intro (INTRO_2.PSS) → `goto_menu` → dlgMenu over
MENULOOP.PSS, VU1 kicking, 60 fps. (The pre-fix flow had skipped the whole valve-guarded
memory-card path, which is why it went straight to the menu with a load-game panel.)
Also fixed: the GL present drew the frame with alpha blending, and the menu frame's alpha is 0,
so the window was black while the RT was fine — the present is now drawn opaque
(`rlDisableColorBlend`), plus a full colour mask before the present blit.
Open (see HANDOFF next task): UI positions all at (0,0) (buttons invisible, popups top-left),
an intermittent null-vtable crash in `FUN_0036ab20` when dlgMenu loads, VU1 packets with no
vertices (no 3D roller). Locale archives do load (`LoadLocale "UIMn"` ok), so captions exist.

## 2026-09-05 19:10 — root cause of the stalled "new game": an unrecompiled trampoline
Runner R2 of the `UiprepMission1` animation (three runners: button anim → SOUND, motion,
`SuspendMenuInput`; fade → OBJECT_OPACITY_FROM_TO + OBJECT_ACTIVE_STATE×3; then a sequence of
14 `VALVE` nodes) stays in state 4 with its current node pointer on the first VALVE node
forever. VALVE is registered by `FUN_0026a8e0(0x414bb0, "VALVE", parse=0x3535d0, 0,
exec=0x353d00, 0)` (decomp line 252352) and **0x353d00 is not a function in the Ghidra CSV**: it is
the two-instruction thunk `j 0x353fd0; addiu $a0,$a0,4`. The dispatcher's table call into it
had no recompiled target and returned without doing anything, so the runner never advanced
(`PS2X_CALL_TRACE=0x353d00:VALVE` prints `[call-trace] no function at 0x353d00`).

Scan for the same class (thunks outside every CSV function range) found exactly two: 0x353d00
and 0x2a98a0 (event-completion callback passed to `FUN_0034e6b0`). Both added to
`recomp/extra_functions.txt`; full recomp started 19:05. Also noticed: 0x38e890/0x3b7cf0 were
listed there since 17:00 but the EXE still reported `missing-target 0x38e890` — the forced list
only takes effect with `./build.sh recomp`.

Scan snippet (Python, from `socom_pc/`): parse the ELF program headers, for every executable
segment word `w` with `w>>26 == 2` (j) whose next word is `addiu $a0,$a0,imm` (`>>16 == 0x2484`)
or nop, compute `target = ((w & 0x3ffffff) << 2) | (addr & 0xf0000000)`, and report `addr` when
it is neither a CSV `Start` nor inside any `[Start, End)` range (bisect over the sorted starts).

## Previous blocker (resolved 2026-09-05) — game stayed on a black shell screen
Full render-pipeline diagnosis in `docs/research/07-render-pipeline-diagnosis.md`. Using the new
`PS2X_FRAME_DUMP=<dir>` counters, every layer below the game is proven correct: VIF1 delivers
1.5 MB/frame to `processVIF1Data`, VU1 launches 1047 microprograms and executes 87k instructions,
the software rasterizer writes pixels, the double-buffer flip and presentation work. The gap is
above them: the game loops in its shell render dispatch (`FUN_00339de0`) but only issues per-frame
**black clears** — `xgkick=0` (no VU1 geometry ever emitted), `nbWrites=0` (every rasterized pixel
is black), ~0.45 GS draws/frame. So the game has not advanced to a state that draws content.

**Update:** the controller was the gate. libpad2 (`scePad2*`) HLE now reports a connected
DualShock2 (see `docs/research/08-controller-and-dbcman.md`), and the game advances out of the
attract loop into first-time controller configuration. It now wedges there on a new IOP RPC:
**DBCMAN `rpc=0x8000131a`**, which our DBCMAN stub leaves unanswered. The main thread pins at
guest 0x32f174 inside a config/asset lookup (`FUN_00321390` list-walk → `FUN_00354670` →
`FUN_0032f0e0` recursive string-tree search) that grinds because the config table DBCMAN 0x8000131a
should populate is empty.

**Unified conclusion (2026-09-05, verified by `PS2X_TRACE_VU`):** the render pipeline is *correct*
and the black screen is a **game-state** condition, not a GS/VU bug. Full write-up in
`docs/research/07 §Resolution`. The one render program the game MSCALs (startPC=0x0, ~748× identical)
reads its input command header from double-buffered VU memory at TOP (0x1a8/0x2d4) = `[0,0,0,1]`
(empty/skip) and correctly branches over the XGKICK at 0x50 — the game is feeding it an empty
display list. GS, rasterizer, framebuffer, presentation, VIF1 feed, VU1 execution and XGKICK decode
all work; when the game reaches an interactive screen it will submit real lists and XGKICK fires on
its own (watch `xgkick`/`nbWrites` rise under `PS2X_FRAME_DUMP`).

So the gate to visible graphics is **advancing the game state**, i.e. the controller path. The pad
HLE (`PS2X_SOCOM2_PAD`, default off to keep the fast render loop) makes the game try first-time DS2
configuration through Sony's proprietary **libdbc/DBCMAN** device-bus protocol and wedge on
`rpc=0x8000131a` (sceDbcReceiveData) at guest 0x32f174. Reply-buffer layouts for the DBCMAN RPCs are
decoded in `docs/research/08` (offsets in the 0x1d62c0 buffer).

(Superseded: the DBCMAN replies were implemented — see the 13:00 section above. The "config loop"
theory was wrong; it was heap corruption from an unanswered ReceiveData.)

## Known issues / debt
- Forced entries get `End = next function start`, which spans rodata: unhandled-instruction count rose from 11k to 114k (garbage that never executes, but +1,400 files). Better: hand the list to Ghidra (`MakeFunctions.java`) so real bounds are found, then re-export.
- Missing ctor targets seen at runtime: 0x231a10, 0x2cde70 (added to `extra_functions.txt`). Expect more "guest-branch:missing-target" lines; each is an entry point to add.
- `LoadExecPS2` (self-relaunch with `--menu_state ...`, and the network-config utility `SCUSNGUI.ELF`) is reported and exits; a real implementation (reset scheduler/memory, reload ELF with argv) is needed for error reboots and network setup.
- Controller input is HLE only (`scePad2*`/`sceVib*` stubs in `game_overrides_socom2.cpp`, shared state `g_socom2Pad`, neutral input): host keyboard/gamepad → `g_socom2Pad` injection is not wired yet. DBCMAN answers libdbc with a fixed "one DS2, nothing received" state; no real DS2 protocol.
- Guest memory faults are converted to COP0 address errors and the access returns 0 (silently until the `[guest-fault]` log, first 16 only). A fault inside a function makes the scheduler re-dispatch that function from `ctx->pc`; a repeated identical `[guest-fault]` line means a retry loop like the one fixed on 2026-09-05.
- GS is the CPU rasterizer at 640x448; fine for bring-up, replace with a GPU backend for M4.
- The loader's libcdvd is partly replaced by runtime stubs (sceCd*), partly recompiled; the engine reads sectors by LBN from the ISO (works). VAG streaming later goes through 989snd's stream-safe read path.
- Build hygiene: shell scripts must stay LF (`.gitattributes`); Python on Windows writes CRLF when opened in text mode without `newline='\n'`.

## Environment facts
- Windows 11, RTX 4070 SUPER, 28 threads, 32 GB. No Visual Studio C++ workload; everything uses the portable toolchain in `tools/`. Python 3.13 with `unicorn`, `capstone`, `pyelftools`.
- Repo: since 2026-09-10 this directory is its own git repo (branch `develop`, remote github.com/Scotho/socom-unzipped, project name SOCOM Unzipped). Never `git add -A`; push after committing.
- The user's desktop is often in use (games): do not steal focus or capture the screen repeatedly; prefer logs. The user may pause work when the machine is loaded.
