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

## Ladder launch 1

**Draft, uncommitted (the controller commits).** Sprint 5 merged Task 5/6 ladder (Amendment A), launch 1 of the
16-launch cap. Per-round figures below come from an offline script in the session scratchpad (`ladder1b.py`,
untracked). It uses `verdict_core.parse_log`, aligns the logs on MoveScale `#0` (B + 6.10 s) and drops the
step → step + 8 s reset span when it measures distances.

### Launches and the command

Both launches used this command, from the repo root, at `sprint-5` HEAD `dc6a625`:

`bash scripts/parity/ladder_frostfire.sh --pinned logs/parity/s5_t5_ladder1[b]`

| # | per-instance logs | out dir | outcome (`logs/<name>.done`) |
|---|---|---|---|
| 1 | `logs/run_[AB]_20260913_212452.log` (5.0 / 4.9 MB) | `logs/parity/s5_t5_ladder1` | `done 4 mpexit=4 LOBBY-FAIL map-list-search`. The real failure came earlier. After `lobby_news`, A's CROSS toward BRIEFING ROOMS did not take: `A_timeout_rooms.png` shows the lobby menu with MESSAGES highlighted. The stage waited (`TIMEOUT waiting for rooms`, then `briefing_room`) and the fixed presses drifted into IGNORE LIST (`A_lobby_fail_map-list-search.png`). B reached the briefing room. No round was played. |
| 1b | **`logs/run_[AB]_20260913_213048.log`** (44.8 / 45.1 MB) | `logs/parity/s5_t5_ladder1b` | `done 1 mpexit=1 NO-KILL`. The lobby passed after one map-CROSS re-send (`LOBBY RESEND map-cross-dropped attempt=1`), the first live rescue by the R47 detector. The launch played 4 of 4 usable rounds. |

Identity on every RESULT/LADDER line was `harness=dc6a625571d7 exe=234b4772cd0a8bf8`. The done marker carried
`harness=dc6a625571d778883146da3911413fe22a69a7f8` and `sha256=234b4772cd0a8bf8fe0e…`.

**Environment:**
- Horizon stack up, not restarted: UniverseInformation 10071, Dme 10073, Medius 10075/10077/10078.
- LAN address 192.168.2.10.
- Persona B present on `game/disc/mc0_b`.
- 7.7 GB free on C:.
- `kill_stale_drivers.ps1`: 0 killed, before both launches.
- `logs/.quiet` absent and the lock FREE before both launches.
- **Host load (the owner's, not touched):** Valheim (5.07 GB working set) and VirtualBox (VBoxSVC/VBoxSDS) were running.
- The CPU sampler (`logs/s5_t5_ladder1b.detached.cpu.csv`) recorded total CPU at mean 36.4 %, p90 42.4 % and max 54.0 %.
- **The sampler wrote a row every ~3.1 s, not every 1 s** (593 rows over 31 min).

### Harness lines (1b)

```
RUNG0 rx-table A rx=+64 0.3s -> +1.39 deg | -64 -> -1.10 | +80 -> +3.35 | -80 -> -3.26 | +96 -> +3.38 | -96 -> -5.10
RUNG0 rx-table B rx=+64 0.3s -> +2.31 deg | -64 -> -1.92 | +80 -> +8.40 | -80 -> -6.78 | +96 -> +9.98 | -96 -> -11.57
RUNG0 bp_waits_A=359 bp_waits_B=348 clock_rate_A=1.00 clock_rate_B=1.01 movescale_A=14.86 movescale_B=26.25 status=FAIL
RUNG0 FAIL MoveScale A 14.9/s < 17; back-pressure waits A 359 >= 100; back-pressure waits B 348 >= 100 -- recorded; the rounds continue (R68)
LADDER round=1 rung=1 controllable=yes,yes contact_s=0.00 contact_rows=0 sampler_s=0.25 rows_read=2389 damage=no kill=no starvation_alarms=0 alarms_cleared=0 max_idle_ms=1418,1567 lagflag_rows=1195,1194 aim_iters=20/20:5,2,2,1,0,0,0,2,1,0,2,0,1,0,3,1,0,0,1,2 bp_waits=1796,1901 mover=A RUNG0 FAIL ...
LADDER round=2 rung=1 controllable=yes,yes contact_s=0.00 contact_rows=0 sampler_s=0.25 rows_read=2849 damage=NO-DATA kill=no starvation_alarms=0 alarms_cleared=0 max_idle_ms=1209,1594 lagflag_rows=1425,1424 aim_iters=29/29:... bp_waits=2308,2357 mover=A
LADDER round=3 rung=1 controllable=yes,yes contact_s=0.00 contact_rows=0 sampler_s=0.25 rows_read=2851 damage=NO-DATA kill=no starvation_alarms=0 alarms_cleared=0 max_idle_ms=1529,1559 lagflag_rows=1426,1425 aim_iters=26/26:... bp_waits=2226,2284 mover=A
SWAP-MOVER after usable rounds [1, 2, 3] at rung 1 without rung 2 (mover A): --auto-swap -- rounds 4.. walk B along the route file's routes.B, A stands
LADDER round=4 rung=1 controllable=yes,yes contact_s=0.00 contact_rows=0 sampler_s=0.25 rows_read=2852 damage=NO-DATA kill=no starvation_alarms=0 alarms_cleared=0 max_idle_ms=1596,1537 lagflag_rows=1426,1426 aim_iters=27/27:... bp_waits=2052,2135 mover=B
LADDER-SUMMARY rounds=4/4 usable=4 best_rung=1 kills=0 rungs=1,1,1,1 movers=A,A,A,B stop=rounds done RUNG0 FAIL ...
RESULT round=1..4 ROUND-END (round; unattributed -- NOT a kill) signal=round valve clock 00:01 -> 00:00; closest_3d=113.267 dy_at_closest=41.996 contact=False health_watch=armed misses A/B 0/0
```

`verdict_replay --per-round` (B + 6.10 s, MoveScale `#0`) gave `NO-KILL no-death` for rounds 1 through 4, exit 1. It
read `+0x1044` at [1.0] on both sides in every round, and `total_mp_kills` unchanged. The scorers agree.

### Per round (1b)

| round | mover | rung | route outcome | contact s / band rows | aim iters | bursts (R1) | victim `+0x1044` min | alarms | freezes (guest clock) | teleports | bp waits A/B | closest 3-D (dy) | closest same floor |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | A | 1 | Reached wp15 (689 u) at 78.2 s. **Failed: "time budget 82s exceeded at wp16".** | 0.00 / 0 | 20, max 5 | 0 | 1.0 | 0 | A 5.1 + 1.0 + 8.7 s, B 6.9 + 4.0 s, all in the neutral wait (656–672 s), none during the engagement | 0 | 1796 / 1901 | 113.27 (42.0), A at the ramp foot (688, 100, 1220) | none (B y 142, A y 100) |
| 2 | A | 1 | Reached wp17 (748 u, ramp foot) at 81.9 s. The wp18 ramp leg gained 4.3 u. **Failed: "time budget 85s exceeded at wp18".** A was at mid-ramp (652, 116, 1227) at the round end. | 0.00 / 0 | 29, max 2 | 0 | 1.0 | 0 | none | 0 | 2308 / 2357 | 123.07 (26.0) | none |
| 3 | A | 1 | Reached wp15 (689 u) at 83.3 s. **Failed: "time budget 85s exceeded at wp16".** | 0.00 / 0 | 26, max 2 | 0 | 1.0 | 0 | none | 0 | 2226 / 2284 | 178.24 (42.0) | none |
| 4 | B (auto-swap) | 1 | B descended the ramp, went through the underpass and reached wp16 (626 u, (684, 100, 795)) at 83.7 s. **Failed: "time budget 84s exceeded at wp17".** | 0.00 / 0 | 27, max 2 | 0 | 1.0 (A) | 0 | A 5.2 + 1.8 + 6.6 + 5.2 s, B 1.5 s, all in the neutral wait (1743–1771 s) | 0 | 2052 / 2135 | 175.08 (0.0) | **175.08**: B (678, 100, 741) and A at spawn |

- **Sampler.** Contact is judged on 4 Hz rows (`sampler_s=0.25`).
- **RESULT's `closest_3d`.** It is the minimum over the whole run, so every round prints round 1's 113.27. The per-round values above come from the offline script.
- **`aim_iters`.** These are the route's heading aims (no aim at a target happened). 102/102 converged in ≤ 6 pulses.

### Reading

- **Rung 1 in all four rounds.** Both sides stayed controllable. There were no starvation alarms (NetIdle peak ≤ 1596 ms), no teleports, and no freeze during any engagement.
- **Rung 2 was never attempted.** Every round's route was aborted by `follow_route`'s **whole-route time budget** while the walker was still making progress. No waypoint was stuck, the no-progress rule never fired, and there was no floor failure.
  - The budget is `ROUTE_TIME_SLACK_S + ROUTE_TIME_FACTOR × length / WALK_UNITS_PER_S_LONG` = 20 + 3 × 821–866 / 40 ≈ 82–85 s. That assumes an effective 13.3 u/s.
  - The follower's live cadence (≤ 1.5 s walk legs, an aim pulse read 0.5 s later, then a re-read) delivered **7.5–9.1 u/s** (A 8.8 / 9.1 / 8.3, B 7.5). Covering the route at that pace takes ~95–115 s, before the ramp and the close.
- **The route geometry holds in both directions.**
  - A reached the ramp foot twice and stood mid-ramp at y 116 at the end of round 2. `A_final_r2.png` shows A on the ramp and B visible at its top.
  - B descended the ramp and walked the underpass to (684, 100, 795) on the lower floor.
  - The A3/R64 route is not refuted.
- **After the route failure each round stood neutral for ~210 s until the clock ended it** (C2). There was no second attempt, so about 70 % of every round's time went unused.
- **Next rung's failure:** route time budget at wp16 / wp18 / wp16 (A) and wp17 (B). Contact was never approached, and aim, fire and damage were never exercised.

### Rung 0 — FAIL (recorded, R68)

- **MoveScale.** A ran 14.9/s against the ≥ 17 bar; B ran 26.3/s.
- **Back-pressure waits.** A had 359 and B 348 in the 60 s window, against < 100.
- **Clock rate.** 1.00 / 1.01, which passes.
- **Host load.** Valheim and VirtualBox were running. Total CPU averaged 36 %.
- **The `rx` table is asymmetric between instances.** A's 0.3 s pulses swept 1.1–5.1°, B's 1.9–11.6°. The route aims still converged on both sides.

## Ladder launch 2

**Draft, uncommitted (the controller commits).** Sprint 5 merged Task 5/6 ladder (Amendment A). This is the third
launch against the 16-launch cap (1, 1b, 2). **Round 1 is the acceptance PASS: KillWatch and `verdict_replay` both
score `KILL killer=A victim=B`.** Rounds 2 and 3 repeated it; round 4 reached rung 2 only. The only commit is the tiled
screen pair `docs/research/assets/22-first-kill.png` (`5f1de26`). Per-round figures come from an offline script in the
session scratchpad (`ladder2.py`, untracked, the `ladder1b.py` method: `verdict_core.parse_log`, B aligned on
MoveScale `#0` (B + 5.60 s), the step → step + 8 s reset span dropped).

### Launch and the command

`bash scripts/parity/ladder_frostfire.sh --pinned logs/parity/s5_t5_ladder2`, from the repo root at `sprint-5` HEAD
`171290b` (R70: route budget `20 + 3·len/7.5`, capped to leave 120 s of round clock).

| per-instance logs | out dir | outcome (`logs/s5_t5_ladder2.done`) |
|---|---|---|
| **`logs/run_[AB]_20260913_230442.log`** (29.1 / 29.5 MB) | `logs/parity/s5_t5_ladder2` | `done 0 mpexit=0 KILL harness=171290b5524e4949753ccda0d813754fd6e397c8 … sha256=234b4772cd0a8bf8…`; `.detached` `exit=0` |

- **Timing.** The launch ran 23:04:37–23:25:49 (21 min), with the lobby done at T+466 s.
- **Lobby.** A timed out waiting for the persona screen at 179 s and recovered on its own. One `LOBBY RESEND
  map-cross-dropped attempt=1` rescued the map selection (the second live R47 rescue). Class `ok`.
- **Identity.** Every RESULT/LADDER line reads `harness=171290b5524e exe=234b4772cd0a8bf8`.

**Environment:**
- Horizon listening on 10071/10073/10075/10077/10078, not restarted.
- Persona B present on `game/disc/mc0_b`.
- No socom2 running; `kill_stale_drivers.ps1` killed 0.
- `logs/.quiet` absent and the lock FREE before the launch.
- 78.6 GB free on C:.
- **Host load.** Valheim was closed. VirtualBox was open, per the owner: VBoxSDS, VBoxSVC, the VirtualBox GUI and three
  VirtualBoxVM processes (one at a 121 MB working set, so a VM was probably running).
- **CPU sampler** (`logs/s5_t5_ladder2.detached.cpu.csv`). Total CPU averaged 40.7 %, with p90 51.9 % and max 73.5 %.
  **It wrote a row every 3.1 s, not every 1 s** (401 rows).

### Harness lines

```
RUNG0 rx-table A: +64 +1.54 | -64 -1.65 | +80 +4.67 | -80 -3.28 | +96 +5.31 | -96 -6.11 (deg, 0.3 s)
RUNG0 rx-table B: +64 +2.29 | -64 -2.04 | +80 +7.76 | -80 -7.62 | +96 +12.44 | -96 -11.41
RUNG0 bp_waits_A=380 bp_waits_B=10 clock_rate_A=1.00 clock_rate_B=1.00 movescale_A=17.66 movescale_B=32.23 status=FAIL
RUNG0 FAIL back-pressure waits A 380 >= 100 -- recorded; the rounds continue (R68)
RESULT round=1 PASS signal=health on=B t=T+99.1s detail={"value": 0.0, "offset": 4164, "actor": 22572784, "alive_value": 0.2978736162185669} closest_3d=23.93 dy_at_closest=0.0 contact=False health_watch=armed reads A/B 399/399 misses 0/0 stale_shots=[] missing_shots=[]
LADDER round=1 rung=3 controllable=yes,yes contact_s=14.30 contact_rows=58 sampler_s=0.25 rows_read=798 damage=yes kill=yes starvation_alarms=0 alarms_cleared=0 max_idle_ms=1524,668 lagflag_rows=399,399 aim_iters=2/2:3,0 bp_waits=443,3 mover=A
RESULT round=2 PASS signal=health on=B t=T+231.6s (alive_value 0.2979) closest_3d=23.80 reads 925/925 misses 0/0 stale_shots=[] missing_shots=[]
LADDER round=2 rung=3 controllable=yes,yes contact_s=6.05 contact_rows=25 sampler_s=0.25 rows_read=746 damage=yes kill=yes starvation_alarms=0 alarms_cleared=0 max_idle_ms=1508,700 lagflag_rows=373,373 aim_iters=2/2:1,0 bp_waits=431,13 mover=A
RESULT round=3 PASS signal=health on=B t=T+351.7s (alive_value 0.2671) closest_3d=32.85 reads 1405/1404 misses 0/0 stale_shots=[] missing_shots=[]
LADDER round=3 rung=3 controllable=yes,yes contact_s=5.77 contact_rows=24 sampler_s=0.26 rows_read=651 damage=yes kill=yes starvation_alarms=0 alarms_cleared=0 max_idle_ms=1512,467 lagflag_rows=326,325 aim_iters=3/3:1,0,0 bp_waits=408,8 mover=A
RESULT round=4 ROUND-END (round; unattributed -- NOT a kill) signal=round on=B t=T+750.8s clock 00:01->00:00 closest_3d=25.78 reads 2989/2988 misses 0/0
LADDER round=4 rung=2 controllable=yes,yes contact_s=272.85 contact_rows=1086 sampler_s=0.26 rows_read=2847 damage=NO-DATA kill=no starvation_alarms=0 alarms_cleared=0 max_idle_ms=1226,1555 lagflag_rows=1423,1424 aim_iters=111/111:(all 0) bp_waits=1950,68 mover=A
LADDER-SUMMARY rounds=4/4 usable=4 best_rung=3 kills=3 rungs=3,3,3,2 movers=A,A,A,A stop=rounds done RUNG0 FAIL back-pressure waits A 380 >= 100
STARVATION-WATCH alarms=0 cleared=0 freeze_alarms=0 round_alarms=0 max_idle_ms={'A': 1226, 'B': 1555}
```

### The two scorers

`python -m tools_py.parity.verdict_replay logs/run_A_20260913_230442.log logs/run_B_20260913_230442.log --per-round`
(default alignment B + 5.60 s, MoveScale `#0`) exits 0:

```
KILL killer=A victim=B t=141.33 round=1
  victim-death   B +0x1044=0.000 word0=006691a0 at shared 586.05 guest 141.33
  round-state    round 1 (mp_round_count 0 on both); no step, no 00:00, no game over; B clock 03:21; A clock 03:21
  freeze         B window 574.65..590.11 none; A window 582.20..586.05 none
  no-fall        B max y drop 0.00;  no-self-grenade  B pad mask f700: none;  killer-alive  A min +0x1044 1.000 over 4 rows
  attribution    A fire mask 0800 over A guest 96.67..99.67: press at 585.46; max |dy| 0.00 (<= 10), max 3-D 29.22 (<= 60)
  victim-team    B player_team 8 -> aiteam_08; A player_team 0; B +0xC8 80000100
  cross-instance A kill row at 586.08 = death +0.03 s host, round 1 on both
  total_mp_kills A 0->1 at 586.08; B none
  aiteam_08      1->0 on both: B at 586.30 (guest +0.20), A at 586.08
  +0xF7A         B: 8 intact rows reading 1 in the 2 s before; leaves 1 at +0.00 s
KILL killer=A victim=B t=244.10 round=2    (attribution max 3-D 35.81; A kill row death -0.08 s; the same clauses ok)
KILL killer=A victim=B t=336.51 round=3    (attribution max 3-D 37.55; A kill row death -0.02 s; the same clauses ok)
NO-KILL no-death round=4                   (A +0x1044 [1.0] over 1454 rows; B [0.0, 1.0] over 1455 -- the 0.0 is round 3's body before the respawn)
```

The run without `--per-round` also exits 0, with `KILL killer=A victim=B t=141.33 round=1` and a note of 3 candidate
deaths. **The negative control still holds:** re-scored at the same HEAD, 8c (`run_[AB]_20260913_132843`) gives
`NO-KILL no-death` for rounds 1 and 2.

**Screens.** `A_kill_r1.png` and `B_kill_r1.png` were written 0.28 s and 0.33 s after KillWatch's death read
(23:14:29.48 host). The harness refuses frame files older than 2 s, and `stale_shots=[]`. Both show the kill feed
"socomc fragged socome with M4A1 / ALL TERRORISTS ELIMINATED / SEALS VICTORIOUS!" and the round clock 03:21. B's frame
also shows "You have died."; A's shows 27/30 rounds, one 3-round burst spent. Rounds 2 and 3 have the same pairs, 0.23–0.38 s
after their death reads.

### Per round

| r | rung | route (budget) | close | contact s (harness) / band rows | aim iters | bursts (R1 edges) | victim `+0x1044` | alarms | freezes | teleports | bp waits A/B | closest 3-D (dy) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **KILL** | Arrived: wp1→wp19, 823 u in 86.4 s (9.5 u/s), budget 173 s (capped, ~293 s of clock left) | Band at 3-D 28.9, 5.3 s before the first burst | 14.30 / 184 (both include the post-death rows) | 2, max 3 | 1 | 1.0 → 0.298 → **0.0** within 0.25 s of one burst | 0 | none | 0 | 443 / 3 | 23.93 (0) |
| 2 | **KILL** | Arrived: 866 u in 88.7 s (9.8 u/s), budget 238 s | Band at 25.7 | 6.05 / 152 | 2, max 1 | 1 | 1.0 → 0.298 → **0.0** | 0 | none | 0 | 431 / 13 | 20.57 (0) |
| 3 | **KILL** | Arrived: 866 u in 76.6 s (11.3 u/s), budget 238 s | Band at 33.3 | 5.77 / 156 | 3, max 1 | 2 | 1.0 → 0.638 → 0.267 → **0.0** over two bursts | 0 | none | 0 | 408 / 8 | 19.25 (0) |
| 4 | 2 | Arrived: 866 u in 85.2 s (10.2 u/s), budget 238 s | Band at 26.6 | 272.85 / 1088 | 111, all 0 pulses | 111 | 1.0 throughout | 0 | none | 0 | 1950 / 68 | 25.78 (0) |

- **Freezes.** The only guest-clock pauses were the lobby, before round 1, and the three round boundaries (5.0–5.4 s each).
- **Teleports.** No row step exceeded 30 u outside a round reset.
- **Starvation.** NetIdle peaked at ≤ 1555 ms.

### Reading

- **The first two-instance online kill on ours.** It was A's M4A1, from the v2 route, at 3-D 24–38 on B's floor. The
  damage path writes `+0x1044` online: one 3-round burst takes 1.0 → 0.298 → 0.0.
  - `+0xF7A` leaves 1 on the death row.
  - `total_mp_kills` steps 0→1 **on the killer's instance only** and reads 0 again next round.
  - `aiteam_08` drops 1→0 on both instances within 0.25 s.
  - `mp_round_count` steps **~33 s after the death** (32.9 / 33.1 / 34.5 s), not the ~5 s written in §5.1.1 R60.
    `verdict_replay`'s windows handled it.
- **The R70 budget fix worked.** All four routes arrived in 77–89 s against a 173–238 s budget. The follower ran
  9.5–11.3 u/s, faster than launch 1's 7.5–9.1.
- **Round 4 did not kill.**
  - The aim loop read the same −4.1° error on every one of 111 cycles. That is inside its 5.68° tolerance, so it
    never pulsed, and A fired 111 bursts for ~150 s with no damage.
  - A's `A_final_r4.png` shows 0/30 with no magazines left (180 rounds, i.e. ~60 bursts, then dry fire). The reticle
    is above and to the right of B's figure, which A's view renders low.
  - Class: shots missing, a sub-tolerance aim bias with no re-aim. It is not a damage-path failure; rounds 1–3
    settle that. Grenade option A7: moot.

### Rung 0 compared with launch 1 (Valheim closed, VirtualBox open)

| | launch 1b (Valheim + VirtualBox) | launch 2 (VirtualBox only) |
|---|---|---|
| MoveScale A / B (calls/s, 60 s) | 14.86 / 26.25 | **17.66 / 32.23** |
| back-pressure waits A / B (60 s) | 359 / 348 | **380 / 10** |
| clock rate A / B | 1.00 / 1.01 | 1.00 / 1.00 |
| status | FAIL (MoveScale A, bp A, bp B) | FAIL (bp A only) |
| per-round bp waits A / B | 1796–2308 / 1901–2357 | 408–1950 / 3–68 |
| total CPU mean (sampler) | 36.4 % | 40.7 % |

- **What closing Valheim changed.** B's back-pressure disappeared, and both MoveScale rates rose 19–23 %, clearing A's
  17/s bar.
- **A's did not change.** A is the host, and its waits stayed at ~380 per 60 s and ~5/s over whole rounds. So A's
  back-pressure is not Valheim's; the cause is open. The `rx` table is still asymmetric (A 1.5–6.1°, B 2.0–12.4°).
