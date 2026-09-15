# Sprint 6 — a gate that can see, the paused correctness fixes, and a cheaper online result: design

Status: written 2026-09-15 by the controller from `docs/ROADMAP.md` §6 (revised 2026-09-13, with the
owner's two 2026-09-14 additions to item 5), the 2026-09-14 handoff audit (`docs/HANDOFF-AUDIT-2026-09-14.md`
"Recommended Sprint 6 Order"), `docs/CURRENT_SPRINT.md`'s "Paused 2026-09-14" block, and research/25–27.
**The owner has not reviewed this document.** It rests on the standing instruction (2026-09-15: "proceed
as suggested autonomously, picking up where the last agent left off") and on items the owner agreed to
on 2026-09-14. Goals 0–1 are those already-agreed items; Goals 2 onward follow the roadmap's order and
are the first thing to re-rule when the owner returns. Branch `sprint-6` off `develop` after
`fix/gl-depth-precision` and `fix/gs-block-pointer` are merged. Executor: the autonomous loop following
`docs/superpowers/plans/2026-09-15-sprint-6-correctness-gate-and-online-reliability.md`. **Goal N here
is Task N in the plan.**

**Authority.** `docs/KNOWN.md` wins over this document wherever they disagree. Every numeric bar names
at least one failure class it does **not** separate. The runtime freeze at `92d30f0` (R45/R61) is
**lifted by this sprint for the two runtime fixes in Goal 0** and for nothing else; every online ladder
result quoted against Sprint 5's must name the exe sha it ran on.

## 1. Where Sprint 5 and the paused 2026-09-14 work leave things

- **The acceptance test PASSED once** (ladder launch 2, rounds 1–3 KILL on both scorers) and is **not
  repeatable on demand**: round 4 fired 111 bursts at a −4.1° aim error inside tolerance that never
  corrected (`KNOWN` §4). The lobby reaches gameplay ~4 in 10. Online instances freeze 3–17 s under
  host load (launch 8c), cause unrooted.
- **The parity pipeline cannot see a defect present in every run** (owner question, 2026-09-14; `KNOWN`
  §4 top): title and mission scoring compare our runs to our own earlier runs, and the mission stage
  checks only liveness. The grey water shards in Seeding Chaos have been in every gameplay gate frame
  since Sprint 3; a gate run that ended in MISSION FAILURE passed. The only console reference for that
  spot is a PCSX2 slot-8 screenshot that nothing compares against.
- **Two defects have a named, verified cause and (at the time of writing) no fix landed:**
  - **The single-player turn teleport** is corrupt animation-clip descriptors: our
    `sceGsExecLoadImage`/`sceGsExecStoreImage` HLE multiplies the libgraph block pointer by 8, so the
    game's seven-piece park/restore of 1.75 MB of VRAM through the motion-pack buffer aliases seven
    VRAM regions onto two and smears chunks `[6,5,6,5,6,5,6]` over the pack (research/25 §9–§10,
    independently confirmed; leftover packet decodes `DBP=0x2000` where `0x3C00` was required). Fix:
    use `vram_addr` as the DBP/SBP block field. A second, separate defect on the streamed
    loading-screen path (the guest advances DBP at packet offset 0x14; our stub re-reads only the
    12-byte `GsImageMem`) is **not** fixed by that.
  - **The grey water shards** are **not** GL depth quantisation: the shards survive
    `PS2X_GS_NO_ZTEST=1` (research/27 §3, retracted in `KNOWN` §3). The depth arithmetic was a real
    precision defect and its fix (clip control, `PS2X_GS_DEPTH_LEGACY=1` opt-out, `GSGlDepth` tests)
    is on `fix/gl-depth-precision`. Remaining candidates: the `0x34` env-map pass' texture/CLUT
    (TBP0 0x38a8 PSMT8, CBP 0x3852 CT16) or its geometry (research/26 §4 candidates 2–3).
- **The mission gate stage lands its holds on a HELP pop-up** ("You must MEET WITH MALLARD … PRESS X
  TO CONTINUE"), which pauses the game behind a lit HUD: `s5_head_1x` and `s6_depth_m2` failed with
  6/6 gameplay-band holds and frame diffs 0.00–0.05. Fixed 2026-09-15 by an `ifpopup` step in
  `drive.py` before every hold of `gameplay_probe.txt` (unit-tested; gate run `s6_depth_m3`).
- **Still open from Sprint 4:** the skeleton root-node decay (never re-measured on the post-`vf0`
  exe — `FUN_001c0768` is a vf0 w-term site), the soft-double `exp` chain, `rem_pio2f` precision, the
  display-environment/zbp divergence, `movie_blocks.py` wired into nothing.

## 2. Judgement on the roadmap's Sprint 6 order

The roadmap's order (lobby → freeze → teleports → skeleton → gate probe → math → mixed match → …) was
written before the owner's 2026-09-14 finding that the gate is blind to defects present in every run.
That finding changes the order: **a fix nobody can measure is not a fix**, and the teleport fix (which
moves loading screens, movies and textures too) and the water investigation both need a console
comparison to be judged. So the gate's correctness leg moves first, right after the paused fixes land.
Lobby and freeze then follow, because every online result still costs ~2.5 launches and repeatability
is the standing goal. The audit's "close Sprint 5 honestly" item is done (merged at `2ae4d79`).

Retired: ROADMAP §6 item 3's "a PCSX2 run of the same `rx`-hold script first" for the teleports — the
cause is named and verified offline; the PCSX2 run becomes the *acceptance* of the fix, not its search.

## 3. Sprint goals, in order (Goal N = plan Task N)

0. **Land the paused fixes** (runtime freeze lifted for exactly these): (a) the GL depth-precision
   fix, as the precision fix it is, not as a water fix; (b) the GS block-pointer fix with a
   seven-region round-trip test that fails on the ×8 and an offline descriptor-by-name check on a
   post-fix spawn dump (48 corrupt → 0); (c) the `ifpopup` gate step. Each with `build.sh test` and
   the three-stage gate green, merged to `develop`, and the exe sha recorded.
1. **A gate that can see** — the correctness leg the parity pipeline lacks, three parts:
   (a) **mission-failure detection**: the mission stage FAILs outright on a MISSION FAILURE or
   "leaving designated mission area" screen (pure scorer over the hold captures, tested on the
   `s5_head_1x_b` frames that passed while failing the mission);
   (b) **console-vs-ours image comparison at a fixed gameplay moment**: the spawn view of Seeding
   Chaos (PCSX2 slot 8) scored against our s28 capture with the same content-crop and a region mask
   for the HUD/objective text, reported as a number on every mission gate and **failing** below a
   pre-registered floor that the current shards do not meet;
   (c) **a guest-value probe**: root-node Y, MoveScale `+0x1368`, one rand-derived field and a
   teleport count (row steps > 30 units outside `rx` holds), compared to console numbers already on
   disk, run as part of the mission stage on the existing `PS2X_PEEK` path.
2. **Lobby hardening, complete**: verify-then-act on every fixed press in `host_game`/`join_game`/
   login, the per-launch failure-class taxonomy (B JOIN not reached, map-list search, login keyboard
   not opened, READY dropped, map CROSS dropped, pre-login window/menu), per-stage timeouts with
   in-place retry; measured over 10 launches on the pinned harness.
3. **Online freeze root cause**: the pc-sampler with `m_vsyncTick` and host time, a host CPU sampler,
   one loaded and one quiet launch from the same exe; separate host-load artefact, runtime pacing,
   VSync waits and GS back-pressure; a fix only if the mechanism is ours.
4. **Acceptance repeatability**: the close-range aim loop gains burst-to-burst correction (a miss
   inside tolerance tightens the tolerance or steps the lead; ammo-aware), proven in the simulator's
   negative test that reproduces round 4's fixed −4.1° bias; then **3 consecutive KILL rounds on each
   of 2 ladder launches** under the pinned harness on the Goal 0 exe.
5. **Visible single-player correctness**: the grey water (research/26 candidate 2 via
   `PS2X_GS_TRACE_CMDS` and a slot-8 GS dump, or the `0x34` pass suppressed as the cheap first cut),
   the skeleton root decay re-measured on the post-`vf0` exe, and the second GS load-image defect
   (packet offset 0x14) — each judged by Goal 1(b)'s comparison.
6. **Exact-oracle math and HLE audit leg three**: the soft-double chain against host `double`, a
   faithful `__ieee754_rem_pio2f`, consumer readings for research/20's remaining rows.
7. **Mixed match** (ours ↔ PCSX2, both directions) as the standing online parity test.
8. **Harness and maintainability**: `gate.py --baseline`, `movie_blocks.py` wired into `build.sh
   test`, the client-rect assertion, disk hygiene automated, the first knob-retirement pass
   (`PS2X_GUEST_MALLOC_ZERO`, the `_B` variants that no driver sets, the redundant main-context vf0
   line), and a contributor "build, run, verify" page in `README.md`.
9. **Close-out.**

## 4. Non-goals

- Speed work stays frozen (36–42 fps single, 19–21 two-instance). The replay-cost measurement and the
  PNG export off the GL thread are Sprint 7's.
- No patches to recompiled game logic, no community code patches, no guest-memory writes in any
  acceptance path. Defaults do not move except the two Goal 0 fixes (both are correctness).
- Window size, presentation and render scale stay as shipped (640×448, `PS2X_GS_SCALE=1`); the
  resizable-window product work is Sprint 8's (§7).
- VU memory aliasing (latent, no reachable caller) and the display-env/zbp A/B stay parked unless
  Goal 1(b) implicates them.

## 5. Definition of done — each bar with the class it does not separate

- **Goal 0.** `ps2x_tests` green with the seven-region round trip asserting `DBP == vram_addr` and every
  piece reading back its own bytes; on a post-fix spawn dump every motion-pack descriptor matches the
  console by name (48 → 0); the three-stage gate PASS on the same exe; title run-vs-run ≥ 99.0 on
  s00–s19 against `s5_head_1x`. *Does not separate:* a loading screen or movie upload moved to a
  correct-but-different VRAM address that the title/mission gates never look at — Goal 1(b) does.
- **Goal 1(a).** The scorer FAILs `s5_head_1x_b` (which ended in MISSION FAILURE) and PASSes a hold set
  from a run that stayed in the mission. *Does not separate:* a failure screen that appears after the
  last hold capture.
- **Goal 1(b).** A single number per mission gate; the floor is registered before the first scored run
  from ≥ 3 of our own runs vs slot 8, chosen so that today's shards FAIL and run-to-run variation of
  our own captures (pose, fog, foliage: measured 1.85/255 new-vs-new in research/27) PASSes. *Does not
  separate:* a colour-only defect inside the HUD mask, or a defect at any camera other than the spawn.
- **Goal 1(c).** Each value has a console number and a tolerance on disk; `NO-DATA` when a peek is
  missing. *Does not separate:* a field that is wrong in the same way on both platforms.
- **Goal 2.** Lobby reaches gameplay ≥ 8 of 10 consecutive launches on the pinned harness, every
  failure carrying a class. *Does not separate:* a server-side cause (Horizon) from a harness one.
- **Goal 3.** A condition sentence naming the freeze mechanism with a sampler trace, and either a fix
  with a loaded-vs-quiet A/B on one exe or a ruling that it is host load. *Does not separate:* two
  mechanisms with the same 3–17 s signature.
- **Goal 4.** Two ladder launches, rounds 1–3 KILL on each, both scorers agreeing, exe sha and harness
  commit recorded; the sim's negative test fails on the pre-fix aim loop. *Does not separate:* a bias
  the fixed loop corrects that the console would not have (only Goal 7 can).
- **Goal 5.** The spawn view scores above Goal 1(b)'s floor; the root node holds the console's 5.50
  ± 0.1 over a 60 s stand. *Does not separate:* water fixed by masking a symptom (the `0x34` pass
  suppressed is a diagnostic, never a fix).
- **Goals 6–8.** Unit tests for each oracle; the mixed match reaches gameplay in both directions with
  the movement bar met; `movie_blocks.py` runs in `build.sh test` with a saved furniture baseline.

## 6. Sequencing, budget, risk and realism

```
Goal 0 (two runtime fixes + gate step, serial under the lock) ─> merge ─> branch sprint-6
Goal 1 (a,b,c: scorers are lock-free; one mission gate each to calibrate) ─┬─> Goal 5 (needs 1b)
Goal 2 (10 launches) ─> Goal 3 (2 launches) ─> Goal 4 (sim first; 2 launches ×4 rounds) ───┤
Goal 6 (lock-free, fills lock time) ─────────────────────────────────────────────────────┴─> Goal 7 ─> Goal 8 ─> Goal 9
```

- **Budget.** Goal 0: 2 full gates (~40 min each). Goal 1: 3 mission gates. Goal 2: 10 launches
  (~10 min each). Goal 3: 2 launches. Goal 4: 2 ladder launches (~15 min each) plus 2 retries. Goal
  5: 2 mission gates. Goal 7: 4 launches. About 8 h of lock, which fits the cron loop over several
  nights, not one context. Four consecutive lobby failures pause the task for one lock-free step.
- **Risks.** The block-pointer fix moves other uploads (loading screens, movies, textures) — a full
  gate plus Goal 1(b) is the blast-radius check, and `PS2X_GS_BLOCK_PTR_X8=1` is **not** provided:
  the old value was simply wrong and an opt-out would only preserve a defect. The console comparison
  may need a mask wider than the HUD (typed objective text, help pop-ups). The aim-loop fix may
  reveal that round 4's miss was a hitbox/height issue rather than yaw — the sim negative test bounds
  that. Lobby failures may be server-side.
- **Realism.** Goals 0–1 are nearly certain and land value on their own. Goal 4's repeat is the
  uncertain one: one launch killed on 3 of 4 rounds; two launches at 3 of 3 each needs the aim fix to
  work and the lobby to cooperate twice. Goals 6–8 are lock-free filler and can slip to Sprint 7.

## 7. Charting forward — how this reaches the end goal

The end goal (owner, restated 2026-09-15): a PC-native SOCOM 2 with a fully functional online system,
consistent frame rate, and a resizable game region.

- **Sprint 6 (this):** the gate can see; the two known correctness defects are fixed; online results
  cost less; the kill repeats.
- **Sprint 7 — online as a product, and speed for two instances:** repeatability as a nightly job
  (N consecutive passes, lobby rate tracked); the speed freeze lifted for the two-instance case
  (replay cost, PNG export off the GL thread, the guest-malloc and MPEG demux levers from STATUS
  2026-09-09); a public-server recipe for the Horizon stack (`server/README.md`) so two machines,
  not two instances, play; PCSX2 interoperability from Goal 7 as a standing test.
- **Sprint 8 — the window and the package:** a chosen default window size and a fitted/stretched
  policy with the client-rect assertion in the gate; `PS2X_GS_SCALE=2` as a user option once
  Goal 1(b) can score it; knob retirement past the first pass; the portable package (M6) and the
  contributor path. The HUD, menus and title cannot sharpen with render scale (textured quads at
  native texel density) — a sharper UI is a texture-replacement feature, out of scope until the
  rest is stable.

## 8. Carried over

Sprint 5's ledger archiving (done); `KNOWN` §2's parked-opponent question on the console; writer-PC
watches (PS2Recomp PR #157); the three unexplained clip-header byte differences (research/25 §8.2);
research/25 §7.4's console `+0x2c` behaviour; the transition residual strip; the intro-cinematic
freeze (seen once).
