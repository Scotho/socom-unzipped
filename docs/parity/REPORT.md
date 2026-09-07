# Parity report 2026-09-07 ours_d (text + placement fixed)

Golden: PCSX2 2.8.1 (`logs/parity/golden`). Run: `logs/parity/runs/ours_d`. Score = 100·(1 − 0.5·mad − 0.5·block) at 320x224; screens are the step script's capture points (`scripts/parity/launch_to_mission.txt`), same index on both sides.

**Mean score 91.9 over 6 screens (14 not reached).**

| screen | score | delta | mad | block | note |
|---|---|---|---|---|---|
| s00_CROSS | — |  |  |  | loading screen (logo + LOADING...) is black on ours |
| s01_CROSS | 99.6 | +0.5 | 0.0049 | 0.0036 | ours s00_CROSS; memory card slot popup |
| s02_CROSS | — |  |  |  | 'No SOCOM data' notice: text-only, black on ours |
| s03_CROSS | — |  |  |  | SCEA title card: text-only, black on ours |
| s04_CROSS | — |  |  |  | 'presents' title card: text-only, black on ours |
| s05_CROSS | — |  |  |  | 'Developed by Zipper' title card: text-only, black on ours |
| s06_CROSS | 78.0 | +3.0 | 0.0713 | 0.3679 | ours s01_CROSS; warning / intro screen (animated fade: score varies with capture timing, not a regression signal) |
| s07_CROSS | 79.1 | +2.2 | 0.076 | 0.3429 | ours s02_CROSS; main menu |
| s08_CROSS | 99.2 | +2.4 | 0.0162 | 0.0 | ours s03_CROSS; select rank |
| s09_CROSS | — |  |  |  | controller configuration: not drawn on ours |
| s10_CROSS | — |  |  |  | precision shooter configuration: not drawn on ours |
| s11_CROSS | — |  |  |  | save prompt (PCSX2 card flow) |
| s12_CROSS | — |  |  |  | save slot select (PCSX2 card flow) |
| s13_DOWN | — |  |  |  | saving notice (PCSX2 card flow) |
| s14_DOWN | — |  |  |  | configuration after save (PCSX2 card flow) |
| s15_DOWN | 99.3 | +0.0 | 0.0029 | 0.0107 | ours s04_CROSS; cinematic (black frame) |
| s16_DOWN | — |  |  |  | cinematic |
| s17_DOWN | — |  |  |  | cinematic caption |
| s18_CROSS | — |  |  |  | cinematic caption |
| s19_none | 96.2 | +7.0 | 0.0361 | 0.0393 | ours s05_CROSS; mission briefing |
