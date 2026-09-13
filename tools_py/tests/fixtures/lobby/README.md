# Lobby signature fixtures (Sprint 5 R47, plan Amendment A6)

Grayscale crops of real 640x448 captures from Sprint 5 Task 1 launch 8, read by
`tools_py/tests/test_lobby_resend.py`. The source captures live under git-ignored `logs/parity/`;
`make_fixtures.py` in this folder is the record of each crop and regenerates them
(`python tools_py/tests/fixtures/lobby/make_fixtures.py` from the repo root). The tests paste each crop back into
a black 640x448 frame at its box, so the detectors read the same pixel coordinates as a live frame.

Launch report: `.superpowers/sdd/2026-09-13-sprint-5-control-readout-and-first-kill/task-1-launch8-report.md`.

| fixture | source capture | box (x0, y0, x1, y1) | what it shows |
|---|---|---|---|
| `map_8b_pre.png` | `s5_t1_launch8b_medley/A_14b_map_medley.png` | 335, 110, 625, 380 | SELECTED MAPS panel before the map CROSS |
| `map_8b_post_dropped.png` | `s5_t1_launch8b_medley/A_15_play_list.png` | same | after the CROSS (and SQUARE): byte-identical, the CROSS was dropped (8b's lobby failure) |
| `map_8c_pre.png` | `s5_t1_launch8c_medley/A_14b_map_medley.png` | same | before the map CROSS (same bytes as 8b's) |
| `map_8c_post_taken.png` | `s5_t1_launch8c_medley/A_15_play_list.png` | same | after the CROSS and SQUARE: Medley listed, mean abs diff 8.95 |
| `ready_8a_A_dropped.png` | `s5_t1_launch8_medley/A_19_ready.png` | 14, 150, 175, 190 | 3 s after A's READY CROSS: still READY, label right edge col 48 (8a's lobby failure) |
| `ready_8a_B_taken.png` | `s5_t1_launch8_medley/B_19_ready.png` | same | 3 s after B's CROSS: NOT READY, edge col 83 (82 on the later holds) |
| `ready_8c_A_left_lobby.png` | `s5_t1_launch8c_medley/A_19_ready.png` | same | 3 s after A's CROSS on 8c: no label (the match was launching), not retried |

Caveat: no saved capture shows the SELECTED MAPS panel after a taken CROSS *alone*. The taken fixture is after
CROSS + SQUARE (8.95). The one CROSS-only reading is 8c's live driver log: 3.52 (`drive_s5_t1_launch8c_medley.txt`),
which is why `MAP_CROSS_DROPPED_MAX_DIFF` is 1.0 rather than the driver's 3.0.
