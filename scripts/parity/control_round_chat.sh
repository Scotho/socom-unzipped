#!/usr/bin/env bash
# Sprint 13 Task O2 (#26) -- the chat round: A hosts, B joins, A opens the chat box and types a line; B's log must
# carry the chat receive wrap's `[socom2] chat receive bound: seen=<n>` line. R221's talk-slot peek rides the same
# round.
#
#   * the chat box is opened by R1 ("R1 TEXT CHAT" on the briefing room's button bar, "R1 Text chat." in the game
#     lobby's chat panel -- research/66); online_match_ours --chat does the step after B's join and writes
#     <out>/chat.json (each exchange's byte marks in both logs). The keyboard's read-back is the runtime's OSK wrap
#     line (purpose _361_EnterChatMessage_MSG), which --prefilled arms. When B's log shows nothing, B types back
#     once, so a failed round still says which direction (if any) a line crosses.
#   * the peek: PS2X_PEEK is env.sh's spec plus guest_addresses' talk_table_ptr and the 12 words it points at
#     (control_round_readout.chat_peek_items); the sampler (PS2X_PC_SAMPLER, env.sh) prints them 4x a second on
#     both instances, from boot through the READY'd round the drive holds (--hold).
#   * the verdict: tools_py/parity/control_round_readout.py chat -> <out>/VERDICT.txt.
#
# Usage (under the lock the caller holds; this script never takes it):
#   bash scripts/loop_lock.sh run <owner> --wait <min> -- bash scripts/parity/control_round_chat.sh [--text hello] [out]
#   default out logs/parity/s13_o2_chat_<stamp>. Writes logs/<name>.done as its last act: done <rc> <RESULT>.
#   Knobs: CHAT_HOLD_S (60: how long the drive holds the round after READY).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. "$(dirname "$0")/env.sh"
. "$(dirname "$0")/write_env.sh"    # write_env_ps2x: the PS2X_* record beside a capture (issue #38)
socom_require_python control_round_chat

TEXT=hello
while :; do
  case "${1:-}" in
    --text) TEXT="${2:?--text <line>}"; shift 2 ;;
    *) break ;;
  esac
done
OUT="${1:-logs/parity/s13_o2_chat_$(date +%Y%m%d_%H%M%S)}"
NAME="$(basename "$OUT")"
mkdir -p "$OUT" logs
rm -f "logs/${NAME}.done" "$OUT/.driver_rc"
export PATH="/usr/bin:/bin:$PATH"
finish() { echo "done $1 $2" > "logs/${NAME}.done"; exit "$1"; }

if ! REVISION="$("$PYTHON" -c "from tools_py.parity import guest_addresses as g; print(g.launch_revision(default_ok=True))")"; then
  echo "control_round_chat: the image's revision could not be read (SOCOM_GAME_ELF?)" >&2
  finish 9 refused-revision
fi
PEEK_ITEMS="$("$PYTHON" -c "from tools_py.parity import control_round_readout as r; print(r.chat_peek_items('$REVISION'))")" \
  || finish 9 refused-peek
export PS2X_PEEK="${PS2X_PEEK:+$PS2X_PEEK,}$PEEK_ITEMS"
export PS2X_SOCOM2_RSA_KEY_B=b          # instance B's second RSA pair (online_login_ours.INSTANCES reads it)
HOLD="${CHAT_HOLD_S:-60}"

ROUND_TXT="$OUT/round.txt"
: > "$ROUND_TXT"
note() { echo "$1" >> "$ROUND_TXT"; }
note "ROUND=chat"
note "TEXT=$TEXT"
note "REVISION=$REVISION"
note "PEEK_ITEMS=$PEEK_ITEMS"
note "HOLD=$HOLD"
note "SERVER=$PS2X_SOCOM2_SERVER"
note "EXE=${SOCOM_EXE:-dist/socom2.exe}"
note "STARTED=$(date -u +%FT%TZ)"

if "$PYTHON" -c "import sys; from tools_py.parity import hostplatform; sys.exit(0 if hostplatform.process_running('socom2') else 1)"; then
  echo "control_round_chat: a socom2 is already running -- refusing (the round needs the host to itself)" >&2
  finish 6 refused-game-running
fi
if command -v powershell >/dev/null 2>&1; then
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 >/dev/null 2>&1
fi

touch "$OUT/.t0"
DRIVE="$OUT/drive.txt"
note "DRIVE=$DRIVE"
write_env_ps2x "$OUT" "control_round_chat.sh text=$TEXT hold=$HOLD"
"$PYTHON" -m tools_py.parity.online_match_ours --existing-b --prefilled --chat "$TEXT" --hold "$HOLD" --map frostfire \
      --out "$OUT" --seconds 1200 > "$DRIVE" 2>&1
drc=$?
echo "$drc" > "$OUT/.driver_rc"
"$PYTHON" -c "from tools_py.parity import hostplatform; hostplatform.kill_process_by_name('socom2')" >/dev/null 2>&1

t0_logs() { find logs -maxdepth 1 -name "run_$1_*.log" -newer "$OUT/.t0" 2>/dev/null | sort | tail -1; }
A_LOG="$(t0_logs A)"
B_LOG="$(t0_logs B)"
note "A_LOG=$A_LOG"
note "B_LOG=$B_LOG"
note "DRIVER_RC=$drc"

"$PYTHON" -m tools_py.parity.control_round_readout chat "$OUT" > "$OUT/VERDICT.txt" 2>&1
vrc=$?
cat "$OUT/VERDICT.txt"
finish "$vrc" "$(grep -a -o 'RESULT CHAT [A-Z]*' "$OUT/VERDICT.txt" | tail -1) driver=$drc"
