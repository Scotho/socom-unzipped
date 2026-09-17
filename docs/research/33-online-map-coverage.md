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

| map | launch | lobby | control A/B | round | spawns | freeze peak | notes |
|---|---|---|---|---|---|---|---|
| The Mixer | `ours_control_the_mixer` (2026-09-16 21:04) | ok: map verified at row 3 (mask 0.000), teams 1/1, READY, liveness OK both | NO-CONTROL both (4+5 holds, net < 4 units in every direction) | not started: the STARTING ROUND 1 OF 11 banner stood through every hold while the round clock ran 05:59 -> 04:08; mp_round_count 0, aiteam 1/1 | A (2248.6, 35.5, 2687.4) | none | exit 3; compare Frostfire `ours_task8_frost1`, whose holds show no banner |
