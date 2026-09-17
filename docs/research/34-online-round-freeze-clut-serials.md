# 34 — The online round that never started: CLUT snapshot serials and the starved guest clock (2026-09-16)

Task 6b's first two maps (The Mixer, Crossroads) reached gameplay with both players frozen and "STARTING ROUND 1
OF 11" standing through every hold while the round clock ran (research/33). Frostfire, which had passed a
control round the evening before (`s6_ladder8`, 2026-09-15 23:38), froze the same way on the day's build
(`ours_control_frostfire_regress`). Not a map problem: a regression in the day's GS commits, run to ground here.

## 1. Symptom, and the clock that named it

| run | exe | result | guest clock `DAT_004365c0` per wall second in the round |
|---|---|---|---|
| `s6_ladder8` (09-15 23:23) | before `6d05b18` | control both, kills | 0.70 s/s (ladder script, 48 fps) |
| `ours_task8_frost1` (09-13) | 09-13 build | control both | 0.85 s/s |
| `ours_control_the_mixer` (09-16 21:04) | `dfb6060` (HEAD) | NO-CONTROL both, banner stands | 0.05 s/s, decaying (1.6 s by t+15, 3.8 s by t+105) |
| `ours_control_crossroads` (21:26) | HEAD | same | 0.04 s/s, decaying |
| `ours_control_frostfire_regress` (21:41) | HEAD | same | 0.04 s/s, decaying |

`DAT_004365c0` is the mission object's accumulated time (`0x4364e0+0xe0`, `FUN_002aa490(mission, dt)`, research/21
§3.4). Every gameplay timer runs off it: the message queue that expires "STARTING ROUND" and "OBJECTIVE" (both stood
stacked on B's HUD, `ours_control_frostfire_regress/B_hold02.png`), the actor movement, the 0.6 s snap-back window.
The round clock on the HUD does not (it is the network round timer), which is why the round "ran" while nothing moved.

`dt` is timer T0: `FUN_003aff30` zeroes `T0_COUNT` after every flip and reads it back before the next one, scaled
by `DAT_0049e2d8` into seconds (`0x4a449c`, accumulated at `0x4a44a0`, `0x4a4498` = fps). In the runtime the EE
timers follow the host clock while the EE is executing, minus the host time the render back-pressure wait and the
VU1 interpreter take (`EeScheduler::accountCycles`, `ps2GuestClockExcludedNs`). So a render thread that cannot
keep up does not slow the frame rate the guest sees — it stops the guest's clock.

## 2. Bisect (four launches, one exe each; `scripts/parity/online_control_round.sh frostfire`)

| step | runtime tree | result |
|---|---|---|
| regress | HEAD `dfb6060` | NO-CONTROL, banner stands |
| bisect1 | `545b85a` (drops `ea249f2` GIF dump, `c63729d` VU1 MSCAL/MSCNT, `9c38aff` hooks) | NO-CONTROL |
| bisect2 | `6d05b18~1` (before the gamepad knob) | LOBBY-FAIL twice: without `PS2X_HOST_GAMEPAD=0` the plugged-in pad reaches the old pad path and the OSK ENTER drops — not usable for the question |
| bisect3 | `6d05b18` (drops `3d37abc` blend/CLUT and `545b85a` exposure readback) | **CONTROL-ROUND, exit 0** (`ours_control_frostfire_bisect3`) |

So the regression sits in `3d37abc` or `545b85a`.

## 3. The mechanism, measured (`ours_control_frostfire_headstats`, HEAD with `PS2X_GS_STATS=1 PS2X_CLOCK_TRACE=1 PS2X_VU_STATS=1`)

`[gs-gl stats]` per second, lobby → round:

| textures in cache | submits/s | texture uploads/s | render fps | back-pressure waits | wait_ms |
|---|---|---|---|---|---|
| 414 | 2 214 | 0 | 58.3 | 0 | 0 |
| 16 353 | 325 124 | 26 007 | 11.2 | 23 | 2 910 |
| 55 483 | 792 358 | 64 328 | 2.0 | 60 | 25 150 |

`[clock]`: `eeCycle` 372.5 s at host 394.8 s, 375.0 s at host 437.0 s — 2.5 s of guest time in 42 s of wall time.
`readback=0.0/0` and no `exposure readback` line: the auto-exposure path (`545b85a`) never ran in this round, so the
cause is `3d37abc`'s CLUT snapshot and its place in the texture-cache key.

**The defect.** `GS::loadClutIfNeeded` gave every TEX0/TEX2 load whose palette bytes differed from the *previous*
load on that context a fresh serial (`++m_clutSerial`), and `GSGlBackend::TextureKey::clutId` carries it. SOCOM II's
HUD and player skins alternate between palettes on consecutive draws; each alternation minted a serial, each draw got
a key the cache had never seen, `decodeTexture` re-decoded and re-uploaded the texture, the cache (evicted only for
entries unused for 120 frames) grew without bound, and the render thread fell to 2 fps. The single-player gate
passed 3/3 on the same build (`s6_revert_gate`); why the Albania mission does not churn the same way was not measured
(an inference: fewer palette alternations per frame without a second player's skin and the online HUD), and the gate
has no guest-clock bar — §6.

## 4. The fix (`ps2_gs_tests` 'a CLUT re-loaded with the same bytes re-uses its snapshot id', RED → GREEN)

- `GS::loadClutIfNeeded`: the snapshot id is keyed by content — FNV-1a over `cbp`, `cpsm` and the 2 KiB snapshot —
  in `m_clutIds` (cleared past 4096 entries); a palette seen before gets its id back. The unchanged-palette fast path
  (`m_clutLast`) stays.
- `GSGlBackend`: palette snapshots are evicted by the last load or lookup (`m_clutUse`, `m_clutLoadSeq`), not by id
  distance, since ids are long-lived now. The CPU backend already keeps the 16 most recent loads and the frontend
  re-sends a snapshot on every palette switch, so both backends hold what the draws name.
- Test: A, B, A → ids `[1, 2, 1]`; ten thousand alternations → two distinct ids; the draw samples A through the
  re-used snapshot.

## 5. Verification

- **Online:** `ours_control_frostfire_clutfix` (2026-09-16 23:43, `PS2X_GS_STATS=1 PS2X_CLOCK_TRACE=1`): both sides
  controllable on the precondition, the control round ran to its clock, `RESULT CONTROL-ROUND`, exit 0. In the round:
  texture cache steady at 292 entries, render 43–45 fps, back-pressure 4–5 waits / 22–30 ms per second, guest clock
  0.74 s per wall second (`eeCycle` 626.4 → 627.1 over one host second). The uploads column is still 21k per second
  (45 ms/s): draws whose texture pages take a generation bump are re-decoded every frame — a cost, not a stall, and
  it was 26k–64k/s with the cache exploding. Left as a follow-up below.
- **C++ suite:** 468/468 (`logs/ps2x_tests_clut.txt`), the new test among them.
- **Gate:** `s6_clutfix_gate` — see STATUS.

## 6. Left open

- **21k texture uploads a second in the round even with stable ids** (45 ms/s of render-thread time). Something bumps
  the shadow-page generation of pages the HUD/skin textures sit on every frame (the palette rewrites share a page with
  a texture, or the uploads themselves), so `decodeTexture` re-runs for them. Measure with `PS2X_GS_STATS=1` and the
  `[gs-pages]` trace; the cache key's page span is the place to look.

- **FIXED 2026-09-17: the guest clock ran at 0.5–0.85 of wall time even on passing runs** (table in §1; the Task 6b
  sweep measured 0.42–0.90 across twenty maps, Requiem's joiner 0.38). Measured with the `[clock]` accounting added
  for it (`gap_ms` / `excluded_ms` / `lost_ms`, `ours_control_frostfire_clock`): of every host second in the round,
  ~195 ms of VU1 time and ~290 ms of render back-pressure wait were subtracted from the guest clock
  (`ps2GuestClockExcludedNs`, the 2026-09-08 `e163402` design, made when the VU1 interpreter ran at 3 fps and a
  300 ms dt diverged the camera spring). SOCOM II integrates every timer from T0's dt, so counting wall time is what
  it expects; the scheduler now counts it by default (`PS2X_CLOCK_EXCLUDE=1` restores the exclusion for an A/B) with
  a 100 ms cap on a single gap (`PS2X_CLOCK_CAP_MS`, default was off) so a stall stays a stall. Test-first:
  'accountCycles subtracts the excluded host time by default and counts it with the policy off' and 'the guest clock
  follows wall time by default'. Measured: gate `s6_clock_gate` title/mission PASS (spawn 22.6, water flat 0.183,
  hold diffs 3.6–127 vs 5–36 before); online `ours_control_frostfire_clockoff` CONTROL-ROUND exit 0 with **both sides
  at 1.00 s per wall second** (eeCycle tracks host 1:1, holds net 119 / 54 u vs 40–90). The transition stage's
  black-frame floor was calibrated on the slow clock (14 wait captures at two-thirds speed, 4 at wall speed, all
  peak 0): recalibrated to 3 (`gate.TRANSITION_MIN_FRAMES`, test-first).
