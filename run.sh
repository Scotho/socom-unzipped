#!/usr/bin/env bash
# Run the recompiled game for N seconds and keep the log.  Usage: ./run.sh [seconds] [extra args]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
SECS="${1:-20}"; shift || true
export PATH="$ROOT/tools/llvm-mingw/bin:$PATH"
mkdir -p "$ROOT/logs"
# PS2X_RUN_LOG=<path> pins the log this run writes, so a driver that has to read the game's own
# output live (the online harness tails "[peek]" rows) knows which file to follow.
LOG="${PS2X_RUN_LOG:-$ROOT/logs/run_$(date +%Y%m%d_%H%M%S).log}"
ln -sf "$LOG" "$ROOT/logs/latest.log" 2>/dev/null || cp /dev/null "$ROOT/logs/latest.log"
timeout "$SECS" "$ROOT/dist/socom2.exe" "$ROOT/game/disc/socom2_game.elf" "$@" > "$LOG" 2>&1
echo "exit=$? log=$LOG lines=$(wc -l < "$LOG")"
grep -v "^INFO: " "$LOG" | head -60
