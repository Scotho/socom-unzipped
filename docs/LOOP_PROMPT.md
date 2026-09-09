# Autonomous loop prompt (SOCOM II PC) — fired every 30 minutes by the session cron

You are continuing the SOCOM II PC static-recompilation project at C:/projects/socom_pc
autonomously. The user (Craig) is away and has given full authority to use best judgement;
plans are suggestions. Ordered goals (user, 2026-09-09):

1. A playable ONLINE MATCH on our native exe (highest priority; PCSX2 clients already play a
   match on the local Horizon stack; ours reaches SELECT UNIVERSE).
2. System-native frame rate (the VU1 interpreter runs the mission at a few fps — this blocks
   every "playable" goal, mission and online alike).
3. 90-95% visual match with the original (docs/parity/REPORT.md is the grade; the user watches
   the TITLE SCREEN closely — its labels must be clean in every build).
4. Playable first mission (Albania 5-1).
Long term: a full PC-native recreation.

## Every firing
1. If a game run or build is in progress (check `logs/.loop_lock` — a file with the owner and
   a start time under 20 minutes old — or a running `socom2*.exe`/`pcsx2-qt.exe`), do NOT start
   another; only one game instance and no builds during runs. Wait for the next firing.
2. Read `docs/HANDOFF.md` "START HERE" and the newest `docs/STATUS.md` entries; `git log -5`.
3. Pick the top open item that advances goal 1 or 2 (then 3, 4). Work in bounded steps: one
   hypothesis -> one build -> one run -> read the evidence -> commit -> STATUS entry (newest on
   top) -> refresh the "START HERE" section of HANDOFF.md when the pick-up changes.
4. Subagents are welcome for offline/static work (decomp reading, VU1 fast-path/recompiler work
   verified with `dist/vu1_replay.exe` against the interpreter, server-side Horizon checks) but
   builds of the runtime and game runs are SERIAL: take `logs/.loop_lock` first.
5. Commit with explicit `socom_pc/...` paths from C:\projects (never `git add -A`; leave
   `server/config/simulated.db` unstaged), trailers
   `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: <url>`.
6. Never regress: title labels clean (s05/s06 of every run sheet), online reaches SELECT
   UNIVERSE, mission loads. A regression is fixed before moving on.

## Run recipes and gotchas
See docs/HANDOFF.md ("The run you will repeat", "Build", "Gotchas"). Key ones: `./build.sh
runtime` (3 min; header change = 10 min); `python -m tools_py.parity.drive --target ours
--script scripts/parity/<script> --out logs/parity/runs/<stamp> --seconds N`; montage with
`python -m tools_py.parity.montage <run> <sheet.png>` then Read the sheet; kill stray
`pcsx2-qt.exe` before drive.py; `PS2X_VU1_DUMP`/`PS2X_RDRAM_DUMP` need existing directories;
RDRAM dump paths must be Windows paths.

## Lock protocol
`scripts/loop_lock.sh take <owner>` before any `./build.sh`, `run.sh` or drive.py run;
`scripts/loop_lock.sh release <owner>` after; `check` to inspect; `wait <owner> [minutes]` blocks
until it is free (stale after 45 min). Offline tools (vu1_replay, python analysis) need no lock.
