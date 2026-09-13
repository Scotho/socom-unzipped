# 22 — The kill readout: facing, the single-player death run, aim calibration, the actor heading field

Sprint 5 Task 2 (Steps 1–6). Branch `sprint-5`. Tooling committed in `d0f4ccb` (Step 1,
`tools_py/parity/facing_check.py`) and `e685b82` (Steps 2–6: `scripts/parity/gameplay_death.txt`,
`tools_py/parity/sp_death_probe.py`, the arming change in `online_match_ours.py`).

**Summary.**

- The camera does not give the player's facing. **Do not adopt it** (§1).
- **No single-player death was observed** in three usable runs, so Goal 2 is **not observed** (§2).
  `+0x1044` was read live stepping down on damage, `1.0 → 0.978 → 0.721` and `1.0 → 0.392`.
  `+0xF7A` stayed 1 through damage and through a MISSION FAILURE. The `<= 0` half is still sourced
  but not read, so the first online death (Task 5 rung 3) is the confirmation.
- **The actor carries its own heading**: a rigid transform at `actor+0x70..+0xbc`. The walk
  direction `(-m[+0xa0], -m[+0xa8])` matched 17 live forward holds to p90 **1.57°**, 13 of them at
  the spawn heading (§4).
- **Yaw.** `|rx − 0x80| ≤ 48` is practically dead. Above it the turn axis and the angular velocity are
  strictly increasing. Per-hold sweeps in single player are unusable, because partial and full rx
  holds there **teleport the actor** (§3.1).
- **Pitch.** `ry = 0` lowers the camera, which looks up. `ry = 255` raises it, which looks down.
  Both sweep about 25° over a 1.0 s hold, plateauing by about 1.2 s (§3.2).

## 1. At-rest facing from the camera — DO NOT ADOPT

Source: Task 2 Step 1 (`d0f4ccb`), on Sprint 4's `kill1`–`kill3` logs, both sides, which is 163
forward holds.

- **Candidate.** `atan2(actor − camera 0x416054)` in the ground plane (x, z).
- **Sample time.** The last actor and camera rows at or before each forward hold starts.
- **Ground truth.** The hold's start→release displacement direction.
- **Gates**, in order:
  1. hold ≥ 1.25 s;
  2. rows within 1.0 s of start and release;
  3. camera not frozen over the 10 s before;
  4. same actor block;
  5. at rest (net drift ≤ 5 units in 10 s);
  6. displacement ≥ 3 units.

| | count |
|---|---|
| used | **9** |
| excluded: hold too short | 19 |
| excluded: not at rest | 132 |
| excluded: displacement too small | 2 |
| excluded: camera stale | 1 |

Over the 9 used holds, |error| had mean 7.69°, median 0.00° and **p90 23.85°**. The maximum was
52.49°. The bar was p90 ≤ 5°.

Six of the nine are opening holds on a settled camera, and those read 0.00°. The two mid-match
samples read **−16.69°** and **+52.49°**. No constant offset explains them. A looser rest gate
(117–132 holds) gives p90 of about 55°, and the big errors follow an rx turn 1.2–2.5 s earlier,
while the camera is still settling.

*Blind class:* Medley only, open ground. Camera collision near walls was not sampled.

**Verdict: DO NOT ADOPT.** Task 5 aims from the actor heading field in §4.

## 2. Single-player death confirmation (spec §5 Goal 2) — not observed

### 2.1 Runs

All runs used the same command, under the lock, with `kill_stale_drivers.ps1` first:

```
bash scripts/run_detached.sh --owner task2 --log logs/s5_t2_death<N>.log logs/s5_t2_death.sh logs/s5_t2_death<N>.done logs/parity/s5_t2_death<N> [--no-yaw --fire-every 20]
# logs/s5_t2_death.sh: df -h /c; powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1;
#                      python -m tools_py.parity.sp_death_probe --out "$OUT" "$@"
# probe env: PS2X_PEEK=<sp_death_probe.PEEK_SPEC> PS2X_PC_SAMPLER=0.25 PS2X_SOCOM2_INPUT_TRACE=1 PS2X_SOCOM2_INPUT_FILE=<out>/pad.txt
```

`PEEK_SPEC` is:

```
0x416054:3,*0x408c58:64,*0x408c58+0xF78:1,*0x408c58+0x1044:1,*0x408c58+0xc0*:32,0x408c58:4,
*0x408c58+0x100:64,*0x408c58+0x200:64,*0x408c58+0x300:64,*0x408c58+0xFB4:1,*0x408c58+0x1368:1
```

| run | run log | binary | what happened | death? |
|---|---|---|---|---|
| 1 | `logs/run_sp_20260913_102205.log` | 09:44 (`07ffc0a`) | drive.py's HUD `untilref` matched the **intro cinematic**. The liveness hold moved 0.00 units, so the probe stopped (`FAIL NO-ACTOR`) | — (never stood) |
| 2 | `logs/run_sp_20260913_103014.log` | 09:44 | In gameplay. Health **1.0 → 0.392** at +262.6 s, after rx-hold teleports. A HELP pop-up the detector missed held the game for the whole 240 s stand | no |
| 3 | `logs/run_sp_20260913_104229.log` | 09:44 | Health **1.0 → 0.978** (+268.6 s) **→ 0.721** (+281.4 s), both after rx-hold teleports. At +286.7 s the actor block's word 0 became `0x4061c0`, the base vtable written by the destructor `FUN_0029ed30` (the actor was destroyed): a **MISSION FAILURE** screen ("Leaving designated mission area" had shown earlier). `+0x1044` then read heap data (the denormal 5.2e-42) and `+0xF7A` stayed 1. **Health > 0, so this is not a death** | no |
| 4 | `logs/run_sp_20260913_111931.log` | **11:03**, with Task 1's uncommitted vf0 runtime change | `--no-yaw --fire-every 20` with a 2 × 3 s walk (the brief's rerun after a mission failure). Health stayed 1.0. An eight-line pop-up put its prompt below the detector's row range (fixed afterwards), and the stand was held again | no |

### 2.2 Goal 2 table

| bar | result |
|---|---|
| `+0x1044` takes a value strictly in (0, 1) | **yes, read live**: 0.978, 0.721 (run 3); 0.392 (run 2). Each followed a teleport-and-land, so fall damage is believed, not proven |
| …then `<= 0` | **not observed** |
| `+0xF7A` leaves 1 within 2 s of the death row | **not observed**. It stayed 1 on every row, including after the mission-failure destruction (run 3) |
| watch `reads > 0`, `misses = 0` | **yes**: KillWatch replay (`sp_death_probe --replay`) gave run 2 1588/0, run 3 589/0, run 4 1454/0. Run 3's reads stop at the block's destruction, which is correct because the watch reads only a vtable-identified block |
| word 0 still `0x6691a0` at the death row | no death row. At run 3's mission failure the actor was **destroyed**: word 0 became the base vtable `0x4061c0`, written by the destructor `FUN_0029ed30`, which frees through `FUN_00180ad0`, and heap data followed in the block (`+0x1044` read the denormal 5.2e-42). A destroyed block is distinguishable, and since fix round 1 both `sp_death_probe.live_death_row` and `death_table`'s `goal2_pass` require word 0 == `0x6691a0` at the death row |
| KillWatch fires at the death rows (offline replay) | **cannot be shown**: there are no death rows. It **did not fire** on run 3's mission failure (0.721 → denormal on a destroyed block), which is the correct negative. The positive is shown only on synthetic rows (`test_kill_watch.KillWatchArmedDefaults`) |

**Verdict: not observed.** Goal 2's single-player half closes as "not observed". The first online
death at Task 5 rung 3 becomes the only confirmation before Task 6.

*Blind class* (unchanged from the spec): another float in [0, 1] that also changes on damage. The
drops here have no independent damage record, such as a HUD health bar crop.

### 2.3 Instrument findings the runs paid for

- **drive.py's `untilref(ref_hud_ours.png, …, 40, 30)` matches the letterboxed intro cinematic.**
  It matched in run 1 at 216 s with 0 presses. The mission gate's own frames at
  `logs/parity/gate/20260912_192900/mission/s30_holdW.png` onward are the cinematic too, so **the
  mission gate's "gameplay" steps have been scoring a cinematic.** The probe now decides gameplay
  itself: both letterbox bands lit (0.67–0.97 on HUD frames, 0.0–0.04 in the cinematic).
- **HELP pop-ups ("PRESS ⓧ TO CONTINUE") hold the game.** The first operation shows one about every
  15 s early on. The detector binarises the prompt line against the committed `ref_hud_ours.png`:
  0.000–0.006 on pop-ups, ≥ 0.218 elsewhere. Squad-plate colour, text brightness and the window
  frame all misfired first.

## 3. Aim calibration

### 3.1 Yaw — dead zone and monotonicity (single player, runs 2–3)

Yaw was read from the actor matrix (§4). "axis" is `actor+0x23c`, the scaled turn axis. "ω" is the
peak of `actor+0x48`, in deg/s. Each hold was 1.0 s from rest.

| rx − 0x80 | run 2: sweep° / ω / axis | run 3: sweep° / ω / axis |
|---|---|---|
| +16 | 0 / 0 / 0 | 0 / 0 / 0 |
| +32 | 0 / 0 / 0 | 0 / 0 / 0 |
| +48 | 0 / 0 / 0 | 0 / 0 / 0 |
| +64 | 0 / 0 / 0 † | +6.75 / 9.22 / −0.080 |
| +96 | +53.26 / 100.74 / −0.879 | +53.11 / 100.74 / −0.879 |
| +127 | +79.02 / 128.11 / −1.118 | +43.31 / 128.11 / −1.118 ‡ |
| −16 | 0 / 0 / 0 | 0 / 0 / 0 |
| −32 | 0 / 0 / 0 | 0 / 0 / 0 |
| −48 | 0 / 0 / 0 | −0.32 / 0.40 / +0.004 |
| −64 | −6.29 / 8.21 / +0.072 | −6.56 / 8.21 / +0.072 |
| −96 | −5.10 / 51.03 / +0.445 † | −18.48 / 81.64 / +0.712 ‡ |
| −127 | −61.05 / 128.11 / +1.118 | — ‡ |

† = held by a HELP pop-up during the hold (run 2). ‡ = the hold's rows are contaminated by a teleport
or by the mission-failure destruction (run 3).

- **Dead zone: |rx − 0x80| ≤ 48 is practically dead**, both directions. +48 read axis 0.000 but
  −48 read 0.004 (a −0.32° sweep in run 3), so the edge is not exactly 48. At 64 the axis is about
  0.075.
- **Strictly increasing above the dead zone: yes, on the axis and on ω.** The axis is 0.004 →
  0.07–0.08 → 0.71–0.88 → 1.118, and ω is 0.4 → 8.2–9.2 → 81.6–100.7 → 128.1 deg/s.
- **The sweep per hold is not usable** in single player, for the † and ‡ reasons above. The one
  clean pair is +96 at 53.1–53.3° in both runs. This does not meet the Goal 5(b) bar, which asks
  for a rate at ≥ 5 levels. The bar has to be re-measured online.
- **The response is steep.** The axis goes from 0.08 at 64 to 0.88 at 96: most of the stick's range
  lies between 64 and 96. The axis exceeds 1.0 at full deflection (1.118).
- **The rate law is confirmed.** ω = 2.0 rad/s × axis: 0.879 × 114.59 = 100.7 and
  1.118 × 114.59 = 128.1. This is `FUN_00550ef0`'s `actor+0x48 = DAT_0044c290 * actor+0x23c`, with
  `DAT_0044c290 = 2.0`.
- **Sign.** Positive rx (right) gives a negative axis, a negative ω and an increasing matrix yaw θ.
  The facing angle in atan2(dz, dx) terms is θ − 90°.

**Finding — in single player, the actor teleports, almost always during rx holds.** From |Δ| ≥ 64,
the velocity words `actor+0x2c..+0x34` read 250–2460 (a forward walk reads about 65). The actor jumped
up to **380 units in one 4 Hz row**, landing as far out as z = 0.0. Three rows later the vector
reappeared shifted by one component: (289.7, −292.2, −5.3) → (4.9, 289.7, −289.4).

- **Count (runs 2–4).** 45 of 47 row-to-row steps > 30 units fall inside rx holds (review count).
  With this note's window of release + 1.0 s the count is 44; the third is run 3 row 1073, just after
  an rx release.
- **The two exceptions had no rx:**
  - run 4 (the vf0 build), row 1216: 86 units at +305.2 s, after a pop-up CROSS and an R1 tap, with
    the pad neutral;
  - run 3, row 1096: 52 units.
- **The motion is real, not a peek artefact.** The camera record and matrix row 3 follow it.
- **Full deflection too** (run 2: rx = 1, 210 units).
- **Consequences.** It walked the player out of the mission area and caused the fall-damage steps
  in §2.
- **Online does not bound it.** kill2's full-deflection rows (rx 0/255, A/B) moved ≤ 4.7 units, but
  their velocity words read 0 throughout, which is a different path. **Online partial deflection has
  never been run**, and kill2 says nothing about it. Task 5's partial-stick aim must check for this
  before relying on it.
- **Candidate mechanism (open).** The root-motion accumulate `FUN_0028c250`, which samples through
  `FUN_00289bb0`, weights through `FUN_00309180` and blends through `FUN_00309280`. (This note first
  named `FUN_00309180` itself; it is a scalar multiply, ×1.0 at the `FUN_0057a330` site, and cannot
  produce the jump.) Research/21's VU0 `vf0.w = 0` is a possible feeder but is untested: run 4 had the
  vf0 build and no rx, and still teleported once.

### 3.2 Pitch (run 4; runs 2–3 had a frozen or freed camera)

| hold | camera elevation above actor, before → after | Δ | rate |
|---|---|---|---|
| `ry = 0` (stick up, key `I`), 1.0 s | 29.73° → 4.89° | **−24.84°** | −24.8°/s (sweep / 1 s) |
| `ry = 255` (stick down, key `K`), 1.0 s | 4.89° → 31.85° | **+26.96°** | +26.9°/s (sweep / 1 s) |

The quoted rate is the sweep divided by the 1 s hold, not a steady-state rate. The `ry = 0` hold
started while the elevation was still moving. Both holds plateau by about 1.2 s, and the in-hold peak
rate is about 30–40°/s (review re-derivation).

**Sign.** `ry = 0` lowers the orbit camera, which looks up and raises the muzzle. `ry = 255` raises
it, which looks down. This settles KNOWN §2's "which of I/K raises the muzzle": **I (ry = 0) raises
it** (inference from the camera orbit, not a muzzle read).

*Blind class:* the camera is the record that can freeze. Runs 2–3 read it frozen or absent. Pitch is
not among the movement-scaled axes, so SP and online rates should agree, but that is unmeasured.

## 4. The actor heading field

**Where (decomp).**

- **Turn input.** `FUN_00551ec0` copies the mover's three stick axes to `actor+0x23c/+0x240/+0x244`
  and multiplies them by the movement scale `actor+0x1368`. `FUN_00550ef0` sets
  `actor+0x48 = DAT_0044c290 (2.0) * actor+0x23c`, the angular velocity, so `+0x23c` is the turn axis.
  These two prove the axis and the rate only, not where the transform is written.
- **The transform's writer is `FUN_005483d0`.** Near its end it:
  - copies `+0xf54..+0xf5c` into `+0xb0..+0xb8` (matrix row 3);
  - calls `FUN_00307170(actor+0x70, actor+0x80)`, which builds the matrix from the quaternion;
  - copies the quaternion `+0x70..+0x7c` to `+0x50..+0x5c`.

The orientation sits inside `*0x408c58:64`:

| offset | content |
|---|---|
| `+0x50..+0x5c` | copy of the quaternion (`FUN_005483d0`) |
| `+0x70..+0x7c` | unit quaternion (x, y, z, w). Its angle is **−θ** relative to the matrix: (0, sin(−θ/2), 0, cos(−θ/2)), i.e. the matrix is Rᵀ of the quaternion (review: 589/589 rows; recount on run 3: 141/141 rows away from 0°/180°, the other 448 ambiguous) |
| `+0x80..+0x8c` | matrix row 0 = (cos θ, 0, sin θ, 0) |
| `+0x90..+0x9c` | row 1 = (0, 1, 0, 0) |
| `+0xa0..+0xac` | row 2 = (−sin θ, 0, cos θ, 0) |
| `+0xb0..+0xbc` | row 3 = position copied from `+0xf54..+0xf5c`, then 1. **Not identical to `+0x1c/+0x20/+0x24`**: while moving, y differs by up to ~19 and z by up to ~52 (run 3: 19.2 / 53.1). Read position from `+0x1c` |
| `+0x48` | angular velocity about y, rad/s |

**Units.** The matrix holds unit-vector components, not an angle. θ = atan2(m[+0x88], m[+0x80]).
**The walk direction is −row2 = (−m[+0xa0], −m[+0xa8])** in (x, z), so
facing = atan2(−m[+0xa8], −m[+0xa0]) = θ − 90°.

**The field moves with rx and holds still at rest.**

- *Offline, kill2 A.* `field_search`, comparing rows before and after each of 50 rx holds against 9
  rest gaps, flagged exactly `+0x54, +0x5c, +0x74, +0x7c, +0x80, +0x88, +0xa0, +0xa8`. Each changed
  on 50/50 rx holds and 0/9 rest gaps.
  - `+0x74/+0x7c` are the quaternion's y and w.
  - `+0x54/+0x5c` are the same pair in the quaternion copy `FUN_005483d0` writes to `+0x50..+0x5c`.
- *Live.* The matrix yaw drifted **0.000°** across all 15 rest windows in runs 2–4 (≥ 1 s of neutral, from 1.5 s after release).
- *Live.* It changed only on rx holds, with ω matching 2.0 × axis.

**Validation against forward-hold displacement.** The estimate is the facing at the last row at or
before hold start. The truth is the start → release + 0.5 s displacement. Holds must move ≥ 10 units
with straightness ≥ 0.8.

| data | n | median \|err\| | **p90 \|err\|** | max |
|---|---|---|---|---|
| live, runs 2–4, all | **17** | 1.28° | **1.57°** | 1.59° |
| …at the spawn heading (90°) | 13 | 1.33° | 0.72–1.59° per hold | 1.59° |
| …off the spawn heading (95°, 137°, 142°, −149°) | 4 | — | 0.00 / 0.81 / 0.99 / 0.75° | 0.99° |
| offline kill1–3, straight holds with no rx in the 3 s before | 11 | 0.44° | 1.43° | 4.92° |
| offline kill1–3, straight holds (any rx history) | 36 | 0.44° | 30.0° | 54.9° |

**Adopt for Task 5, at rest.** p90 is 1.57° over 17 live holds, against the 5° bar.

*Blind classes:*

- **Right after a turn.** The offline "any rx history" row shows 30° p90. Read the heading at least
  one rest period (≥ 2.5 s used here) after an rx hold. Whether the error comes from the matrix
  lagging or from the walk path is not separated.
- **Headings.** 13 of the 17 live holds are at the spawn heading and carry a consistent walk bias there
  (0.72–1.59°, median 1.33°); the 4 off-spawn holds read 0.00–0.99°. The p90 is dominated by one heading and one
  walk line, and only 5 distinct headings were sampled live.
- **Mode.** The live holds are single player. The offline ones are online on Medley.
