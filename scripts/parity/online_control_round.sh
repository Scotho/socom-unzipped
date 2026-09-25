#!/usr/bin/env bash
# Task 6b (owner 2026-09-16): one online control round on a named map -- A hosts, B joins, both go READY, and once
# both are controllable nobody fires; the round runs to its clock. RESULT CONTROL-ROUND on exit 0.
#
# Usage: scripts/parity/online_control_round.sh "<map name>" [out dir]
#   map name as it appears on the CREATE GAME PLAY LIST (case-insensitive: "the mixer", "rat's nest", ...); the
#   selection is verified against scripts/parity/refs/map_<slug>.png (online_login_ours.map_ref_path).
# Same instruments as online_match_frostfire.sh (position peek, MoveScale and NetIdle call traces, input trace).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. "$(dirname "$0")/env.sh"
socom_require_python online_control_round
MAP="${1:?map name}"
SLUG="$("$PYTHON" -c "import sys; from tools_py.parity import online_login_ours as L; print(L.map_slug(sys.argv[1]))" "$MAP")"
OUT="${2:-logs/parity/ours_control_${SLUG}}"
NAME="$(basename "$OUT")"
mkdir -p "$(dirname "$OUT")"
export PATH="/usr/bin:/bin:$PATH"
rm -f "logs/${NAME}.done"
# Instruments come from scripts/parity/env.sh (sourced above); the B-side key is this script's own.
export PS2X_SOCOM2_RSA_KEY_B=b
# --prefilled (Sprint 11 Task 19): both logins ENTER a keyboard the runtime opened already holding the
# persona and the password instead of walking it blind. Two games on one host run at ~32 fps, which is
# exactly where the typing walk drops and doubles keys (research/28 §5: 'ocom', '', 'xmfû'); the same class
# cost `s11_r0004_online1` its login the night this was added. Sprint 10 Goal 9, R180: the runtime prefills
# and never submits, the harness presses.
"$PYTHON" -m tools_py.parity.online_match_ours --existing-b --prefilled --hold 30 --control-round --rounds 1 \
       --map "$MAP" --max-steps 60 --max-walk-seconds 240 \
       --out "$OUT" --seconds 1200 \
       > "logs/parity/drive_${NAME}.txt" 2>&1
rc=$?
echo "mpexit=$rc" >> "logs/parity/drive_${NAME}.txt"
echo "done $rc" > "logs/${NAME}.done"
exit $rc
