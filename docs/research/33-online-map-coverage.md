# 33 — Online map coverage: control rounds on every untested map (Sprint 6 Task 6b)

Owner request (2026-09-16): "testing online matches in each of the untested online maps (without a kill requirement
initially)". Frostfire (kills), Medley and Vigilance (control rounds) were the only maps ever driven online.

## Method

- **The list.** The CREATE GAME PLAY LIST as scanned on 2026-09-13 (`logs/parity/ours_task8_mapscan`, capture k
  highlights entry k), 24 entries: Medley, Random, Vigilance, The Mixer, Foxhunt, Sujo, Enowapi, Shadow Falls,
  Fish Hook, Crossroads, Sandstorm, Chain Reaction, Guidance, Requiem, Blizzard, Frostfire, Abandoned, Desert Glory,
  Night Stalker, Rat's Nest, Bitter Jungle, Blood Lake, Death Trap, The Ruins (`online_login_ours.MAP_SCAN_ORDER`).
- **References.** One `scripts/parity/refs/map_<slug>.png` per entry, cut from that scan with choose_map's row
  geometry (x 78..292, y 117 + 20k, 12 px). `tests/test_map_refs.py`: every reference scores 0.00 against itself
  and >= 0.30 (the acceptance threshold) against every other -- no two maps confuse the verified selection.
- **The launch.** `scripts/parity/online_control_round.sh "<map>"`: A hosts the map (selection verified against the
  reference before CROSS), B joins, both READY, and after the control precondition nobody fires; both sides strafe
  in alternation until the round clock ends (`online_match_ours --control-round`, Task 6's negative control: exit 0
  only with total_mp_kills, aiteam_* and the health word unchanged). `scripts/parity/online_control_queue.sh` runs
  the twenty maps in list order, one retry pass for the failures, and appends one line per launch to
  `logs/parity/online_control_summary.txt`.
- **Bars per map** (CURRENT_SPRINT Task 6b): lobby reaches gameplay; both sides controllable on the control
  precondition; the round runs to its clock or 120 s of live rows; spawns recorded; no freeze alarm over 10 s. A map
  that fails control or liveness after its retry gets a KNOWN §2 row naming what failed.

## Results

Queue run 2026-09-17 00:14 -> 04:45 on exe `7b3816046a5bae9c` (the research/34 fix, harness `d2a9a55`); summary in
`logs/parity/online_control_summary.txt`, one directory per launch under `logs/parity/`. The first launch of The Mixer
(2026-09-16 21:04) and of Crossroads (21:26) on the day's earlier exe froze at STARTING ROUND on both sides -- the
CLUT-serial regression of research/34, not the maps; both play on the fixed exe below.

**18 of 20 maps ran a control round to the clock with both sides controllable and no kill.** The two others:

- **Foxhunt** (retry): the round ran to its clock, nobody fired, but B took fall damage strafing off a drop, so the
  negative control's health bar failed (exit 1). A harness matter: the blind strafe legs do not look for ledges.
- **Requiem** (both passes, identical): A controllable, B's four holds net 13-38 units against the 40-unit bar. B moves;
  its guest clock runs at 0.38 s per wall second there (A 0.57; the sweep's range is 0.42-0.90), and a 2 s host-time
  hold buys B under a second of game time. The slow guest clock is research/34 §6 / KNOWN §2, not a Requiem defect.

The guest-clock column (`DAT_004365c0` over the first 90 s of the round, per side) is the sweep's other finding: no
map runs the game at wall speed, and the joiner is often slower than the host.

| map | launch | lobby | control A/B | round | spawns | freeze peak | notes |
|---|---|---|---|---|---|---|---|
| The Mixer | `ours_control_the_mixer` (2026-09-17 00:14, pass 1) | LOBBY-FAIL login:keyboard-typing | - | - | - | none logged | guest clock s/s: -; exit 4; the 21:04 launch (NO-CONTROL, banner standing) was the research/34 regression, not the map |
| Foxhunt | `ours_control_foxhunt` (2026-09-17 00:17, pass 1) | LOBBY-FAIL login:keyboard-enter | - | - | - | none logged | guest clock s/s: -; exit 4 |
| Sujo | `ours_control_sujo` (2026-09-17 00:21, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 446 legs, clock00:01->00:00 | A (873, 143, 279), B (658, -25, 2245) | none logged | guest clock s/s: A 0.49, B 0.50; exit 0 |
| Enowapi | `ours_control_enowapi` (2026-09-17 00:34, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 446 legs, clock00:01->00:00 | A (802, 4, 340), B (1442, 277, 1231) | none logged | guest clock s/s: A 0.60, B 0.60; exit 0 |
| Shadow Falls | `ours_control_shadow_falls` (2026-09-17 00:47, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 447 legs, clock00:01->00:00 | A (1607, 36, 2160), B (445, 38, 811) | none logged | guest clock s/s: A 0.78, B 0.81; exit 0 |
| Fish Hook | `ours_control_fish_hook` (2026-09-17 01:00, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (2+1 holds) | ran to the clock: 422 legs, clock00:01->00:00 | A (1199, 73, 1450), B (1892, 175, 758) | none logged | guest clock s/s: A 0.78, B 0.90; exit 0 |
| Crossroads | `ours_control_crossroads` (2026-09-17 01:12, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 446 legs, clock00:01->00:00 | A (1972, 68, 2150), B (748, 93, 766) | none logged | guest clock s/s: A 0.47, B 0.67; exit 0 |
| Sandstorm | `ours_control_sandstorm` (2026-09-17 01:25, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 448 legs, clock00:01->00:00 | A (2303, 201, 2017), B (857, 85, 1306) | none logged | guest clock s/s: A 0.83, B 0.78; exit 0 |
| Chain Reaction | `ours_control_chain_reaction` (2026-09-17 01:39, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 445 legs, clock00:01->00:00 | A (1256, 272, 1254), B (1457, 26, 2374) | none logged | guest clock s/s: A 0.75, B 0.72; exit 0 |
| Guidance | `ours_control_guidance` (2026-09-17 01:52, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 448 legs, clock00:01->00:00 | A (900, 55, 2803), B (2011, 21, 1377) | none logged | guest clock s/s: A 0.71, B 0.58; exit 0 |
| Requiem | `ours_control_requiem` (2026-09-17 02:06, pass 1) | ok: teams ok; A liveness OK B liveness OK | A CONTROLLABLE / B NO-CONTROL (4+4 holds) | not reached: B's holds net 13 / 36-38 / 18 / 38 u against the 40 u bar on both passes, A passes; B moves, on a guest clock at 0.38 s per wall second (the slowest of the sweep; research/34 §6) | A (1928, 224, 2591), B (676, 187, 789) | none logged | guest clock s/s: A 0.57, B 0.38; exit 3 |
| Blizzard | `ours_control_blizzard` (2026-09-17 02:14, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 446 legs, clock00:01->00:00 | A (2562, 272, 3113), B (1789, 75, 1385) | none logged | guest clock s/s: A 0.69, B 0.67; exit 0 |
| Abandoned | `ours_control_abandoned` (2026-09-17 02:27, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 446 legs, clock00:01->00:00 | A (1172, 82, 2260), B (927, 168, 622) | none logged | guest clock s/s: A 0.72, B 0.83; exit 0 |
| Desert Glory | `ours_control_desert_glory` (2026-09-17 02:39, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 446 legs, clock00:01->00:00 | A (837, -5, 1901), B (1865, 66, 1221) | none logged | guest clock s/s: A 0.81, B 0.65; exit 0 |
| Night Stalker | `ours_control_night_stalker` (2026-09-17 02:52, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 446 legs, clock00:01->00:00 | A (648, 124, 1675), B (2310, 163, 1458) | none logged | guest clock s/s: A 0.78, B 0.73; exit 0 |
| Rat's Nest | `ours_control_rats_nest` (2026-09-17 03:06, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 447 legs, clock00:01->00:00 | A (1601, 166, 905), B (188, 165, 948) | none logged | guest clock s/s: A 0.67, B 0.66; exit 0 |
| Bitter Jungle | `ours_control_bitter_jungle` (2026-09-17 03:18, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (3+1 holds) | ran to the clock: 398 legs, clock00:01->00:00 | A (1065, 30, 1253), B (2749, 31, 911) | none logged | guest clock s/s: A 0.76, B 0.74; exit 0 |
| Blood Lake | `ours_control_blood_lake` (2026-09-17 03:31, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 446 legs, clock00:01->00:00 | A (1098, 35, 626), B (884, 52, 2004) | none logged | guest clock s/s: A 0.73, B 0.71; exit 0 |
| Death Trap | `ours_control_death_trap` (2026-09-17 03:45, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+2 holds) | ran to the clock: 420 legs, clock00:01->00:00 | A (1170, 163, 1572), B (1628, 1, 247) | none logged | guest clock s/s: A 0.65, B 0.67; exit 0 |
| The Ruins | `ours_control_the_ruins` (2026-09-17 03:57, pass 1) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 446 legs, clock00:01->00:00 | A (2063, 68, 1114), B (486, 69, 1309) | none logged | guest clock s/s: A 0.78, B 0.73; exit 0 |
| The Mixer | `ours_control_the_mixer_retry` (2026-09-17 04:11, pass 2) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 445 legs, clock00:01->00:00 | A (2254, 40, 2688), B (3802, 101, 2044) | none logged | guest clock s/s: A 0.42, B 0.78; exit 0 |
| Foxhunt | `ours_control_foxhunt_retry` (2026-09-17 04:24, pass 2) | ok: teams ok; A liveness OK B liveness OK | CONTROLLABLE both (1+1 holds) | ran to the clock: 446 legs, clock 00:01->00:00; **negative control failed on B's health**: 1.0 -> 0.738 at T+224 s, B strafed off a 110-unit drop (y 167 -> 57 in 1.2 s, `run_B_20260917_042414.log`) -- fall damage, no kill, no counter step | A (3407, 144, 4904), B (3212, 212, 1817) | none logged | guest clock s/s: A 0.72, B 0.74; exit 1 |
| Requiem | `ours_control_requiem_retry` (2026-09-17 04:37, pass 2) | ok: teams ok; A liveness OK B liveness OK | A CONTROLLABLE / B NO-CONTROL (2+4 holds) | not reached: B's holds net 13 / 36-38 / 18 / 38 u against the 40 u bar on both passes, A passes; B moves, on a guest clock at 0.38 s per wall second (the slowest of the sweep; research/34 §6) | A (1928, 224, 2592), B (676, 187, 789) | none logged | guest clock s/s: A 0.59, B 0.38; exit 3 |
