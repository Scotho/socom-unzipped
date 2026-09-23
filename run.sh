#!/usr/bin/env bash
# Run the recompiled game for N seconds and keep the log.  Usage: [SOCOM_EXE=<runner>] ./run.sh [seconds] [extra args]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SECS="${1:-20}"; shift || true
export PATH="$ROOT/tools/llvm-mingw/bin:$PATH"
mkdir -p "$ROOT/logs"
# PS2X_RUN_LOG=<path> pins the log this run writes, so a driver that has to read the game's own
# output live (the online harness tails "[peek]" rows) knows which file to follow.
LOG="${PS2X_RUN_LOG:-$ROOT/logs/run_$(date +%Y%m%d_%H%M%S).log}"
ln -sf "$LOG" "$ROOT/logs/latest.log" 2>/dev/null || cp /dev/null "$ROOT/logs/latest.log"
# Sprint 9 Goal 2: SOCOM_EXE names another runner (the release build in dist-release/); the default is unchanged.
EXE="${SOCOM_EXE:-$ROOT/dist/socom2.exe}"
# Sprint 11 Task 19: SOCOM_GAME_ELF names another overlay image (a revision built by scripts/build_revision.sh,
# copied to a file CALLED socom2_game.elf -- the runtime keys its overrides on that name); the default is unchanged.
ELF="${SOCOM_GAME_ELF:-$ROOT/game/disc/socom2_game.elf}"
# Sprint 9 Goal 3: run.sh is a developer's and the harness's launcher, so it is a developer-mode launch -- the
# probes it is used with (PS2X_PEEK, the exported frame, the pad file) are ignored by the game otherwise.
# PS2X_DEV=0 ./run.sh is a stranger's run.
export PS2X_DEV="${PS2X_DEV:-1}"
timeout "$SECS" "$EXE" "$ELF" "$@" > "$LOG" 2>&1
echo "exit=$? log=$LOG exe=$EXE lines=$(wc -l < "$LOG")"
grep -v "^INFO: " "$LOG" | head -60
