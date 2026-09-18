#!/usr/bin/env bash
# Sprint 7 Task 2d (spec Goal 2d; Sprint 6 Task 2 Step 4, ruling R85): the lobby rate, measured. Ten control rounds on
# ONE map (Frostfire), one launch after another under the loop lock the caller (scripts/run_detached.sh) holds, on a
# pinned harness, so the number means one thing: reached-gameplay / total, with the failure class of every miss.
# Results: logs/parity/lobby_rate_<nn>/ + logs/parity/drive_lobby_rate_<nn>.txt; one line per launch in
# logs/parity/lobby_rate_summary.txt; the rate read by `python -m tools_py.parity.lobby_report --bar 8/10 ...`.
#
# Usage: scripts/parity/lobby_rate_queue.sh [count] [map]      (default 10, "frostfire")
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COUNT="${1:-10}"
MAP="${2:-frostfire}"
SUMMARY="logs/parity/lobby_rate_summary.txt"
mkdir -p logs/parity
echo "# lobby rate queue $(date +%Y-%m-%dT%H:%M:%S) map=$MAP count=$COUNT harness=$(git rev-parse --short HEAD 2>/dev/null) exe=$(sha256sum dist/socom2.exe 2>/dev/null | cut -c1-16)" >> "$SUMMARY"
for i in $(seq -f "%02g" 1 "$COUNT"); do
  out="logs/parity/lobby_rate_${i}"
  start=$(date +%s)
  bash scripts/parity/online_control_round.sh "$MAP" "$out"
  rc=$?
  result="$(grep -a -o "RESULT [A-Z-]*[^\r]*" "logs/parity/drive_$(basename "$out").txt" 2>/dev/null | tail -1)"
  echo "${i} rc=${rc} $(( $(date +%s) - start ))s ${result}" >> "$SUMMARY"
  taskkill //F //IM socom2.exe >/dev/null 2>&1
  sleep 10
done
exit 0
