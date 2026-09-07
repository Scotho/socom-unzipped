# Parity report 2026-09-07 ours_a

Golden: PCSX2 2.8.1 (`logs/parity/golden`). Run: `logs/parity/runs/ours_a`. Score = 100·(1 − 0.5·mad − 0.5·block) at 320x224; screens are the step script's capture points (`scripts/parity/launch_to_mission.txt`), same index on both sides.

**Mean score 80.6 over 6 screens (14 not reached).**

| screen | score | delta | mad | block | note |
|---|---|---|---|---|---|
| s00_CROSS | — |  |  |  | loading screen (logo + LOADING...) is black on ours |
| s01_CROSS | 86.5 |  | 0.0415 | 0.2286 | ours s00_CROSS; memory card slot popup |
| s02_CROSS | — |  |  |  | 'No SOCOM data' notice: text-only, black on ours |
| s03_CROSS | — |  |  |  | SCEA title card: text-only, black on ours |
| s04_CROSS | — |  |  |  | 'presents' title card: text-only, black on ours |
| s05_CROSS | — |  |  |  | 'Developed by Zipper' title card: text-only, black on ours |
| s06_CROSS | 79.2 |  | 0.0669 | 0.35 | ours s01_CROSS; warning / intro screen |
| s07_CROSS | 63.7 |  | 0.1505 | 0.575 | ours s02_CROSS; main menu |
| s08_CROSS | 83.6 |  | 0.0701 | 0.2571 | ours s03_CROSS; select rank |
| s09_CROSS | — |  |  |  | controller configuration: not drawn on ours |
| s10_CROSS | — |  |  |  | precision shooter configuration: not drawn on ours |
| s11_CROSS | — |  |  |  | save prompt (PCSX2 card flow) |
| s12_CROSS | — |  |  |  | save slot select (PCSX2 card flow) |
| s13_DOWN | — |  |  |  | saving notice (PCSX2 card flow) |
| s14_DOWN | — |  |  |  | configuration after save (PCSX2 card flow) |
| s15_DOWN | 99.3 |  | 0.0024 | 0.0107 | ours s04_CROSS; cinematic (black frame) |
| s16_DOWN | — |  |  |  | cinematic |
| s17_DOWN | — |  |  |  | cinematic caption |
| s18_CROSS | — |  |  |  | cinematic caption |
| s19_none | 71.2 |  | 0.129 | 0.4464 | ours s05_CROSS; mission briefing |
