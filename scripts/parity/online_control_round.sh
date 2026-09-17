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
MAP="${1:?map name}"
SLUG="$(python -c "import sys; from tools_py.parity import online_login_ours as L; print(L.map_slug(sys.argv[1]))" "$MAP")"
OUT="${2:-logs/parity/ours_control_${SLUG}}"
NAME="$(basename "$OUT")"
mkdir -p "$(dirname "$OUT")"
export PATH="/usr/bin:/bin:$PATH"
rm -f "logs/${NAME}.done"
export PS2X_HOST_GAMEPAD=0   # a launch boots with no controller (see gate.py)
export PS2X_SOCOM2_SERVER="${PS2X_SOCOM2_SERVER:-192.168.2.10}" PS2X_SOCOM2_RSA_KEY_B=b        PS2X_SOCOM2_INPUT_TRACE=1        PS2X_PC_SAMPLER=0.25        PS2X_CALL_TRACE_EVERY=10        PS2X_CALL_TRACE="0x553dc0:MoveScale,0x30cd80:NetIdle"        PS2X_PEEK="0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,*0x437ce8+0x0c*:2,*0x437ce8+0x10*:2,*0x437ce8+0x14*:2,*0x437ce8+0x20*:2,*0x437ce8+0x24*:2,*0x437ce8+0x2c*:2,*0x437ce8+0x58*:2,*0x437ce8+0x5c*:2,*0x437ce8+0x70*:2,*0x43668c:2,0x4365c0:1,0x45a0c0:1,0x3df1b0:1,0x45a1c8:1,*0x437ce8+0x0c**:3,*0x437ce8+0x10**:3,*0x437ce8+0x14**:3,*0x437ce8+0x20**:3,*0x437ce8+0x24**:3,*0x437ce8+0x2c**:3,*0x437ce8+0x58**:3,*0x437ce8+0x5c**:3,*0x437ce8+0x70**:3,*0x43668c*:3,0x408f10:2,0x408c58:4"
python -m tools_py.parity.online_match_ours --existing-b --hold 30 --control-round --rounds 1 \
       --map "$MAP" --max-steps 60 --max-walk-seconds 240 \
       --out "$OUT" --seconds 1200 \
       > "logs/parity/drive_${NAME}.txt" 2>&1
rc=$?
echo "mpexit=$rc" >> "logs/parity/drive_${NAME}.txt"
echo "done $rc" > "logs/${NAME}.done"
exit $rc
