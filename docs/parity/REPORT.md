# Parity report 2026-09-07 ours_e (libvu0 un-stubbed; alignment shifted +1)

> **SNAPSHOT 2026-09-07, never updated.** This is one parity run from the week the renderer was being brought up (mean 91.6 over 6 screens, 14 capture points not reached). It is NOT the project's parity status: the game now plays missions and online rounds, and the live gate is `python -m tools_py.parity.gate` with its stamps under `logs/parity/`. Kept for the screen-by-screen breakdown only. See `docs/DOC_MAINTENANCE.md` (class S).


Golden: PCSX2 2.8.1 (`logs/parity/golden`). Run: `logs/parity/runs/ours_e`. Score = 100·(1 − 0.5·mad − 0.5·block) at 320x224; screens are the step script's capture points (`scripts/parity/launch_to_mission.txt`), same index on both sides.

**Mean score 91.6 over 6 screens (14 not reached).**

| screen | score | delta | mad | block | note |
|---|---|---|---|---|---|
| s00_CROSS | — |  |  |  | loading screen (logo + LOADING...) is black on ours |
| s01_CROSS | 99.6 |  | 0.0054 | 0.0036 | memory card slot popup |
| s02_CROSS | — |  |  |  | 'No SOCOM data' notice: text-only, black on ours |
| s03_CROSS | — |  |  |  | SCEA title card: text-only, black on ours |
| s04_CROSS | — |  |  |  | 'presents' title card: text-only, black on ours |
| s05_CROSS | — |  |  |  | 'Developed by Zipper' title card: text-only, black on ours |
| s06_CROSS | 74.9 |  | 0.0778 | 0.425 | ours s02_CROSS; warning / intro screen (animated fade: score varies with capture timing, not a regression signal) |
| s07_CROSS | 81.0 |  | 0.073 | 0.3071 | ours s03_CROSS; main menu |
| s08_CROSS | 99.0 |  | 0.0168 | 0.0036 | ours s04_CROSS; select rank |
| s09_CROSS | — |  |  |  | controller configuration: not drawn on ours |
| s10_CROSS | — |  |  |  | precision shooter configuration: not drawn on ours |
| s11_CROSS | — |  |  |  | save prompt (PCSX2 card flow) |
| s12_CROSS | — |  |  |  | save slot select (PCSX2 card flow) |
| s13_DOWN | — |  |  |  | saving notice (PCSX2 card flow) |
| s14_DOWN | — |  |  |  | configuration after save (PCSX2 card flow) |
| s15_DOWN | 98.9 |  | 0.004 | 0.0179 | ours s05_CROSS; cinematic (black frame) |
| s16_DOWN | — |  |  |  | cinematic |
| s17_DOWN | — |  |  |  | cinematic caption |
| s18_CROSS | — |  |  |  | cinematic caption |
| s19_none | 96.4 |  | 0.037 | 0.0357 | ours s06_CROSS; mission briefing |
