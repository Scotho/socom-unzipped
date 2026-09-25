#!/usr/bin/env bash
# Sprint 13 Task C3 -- the control round that proves F10 (the after-return trap in the rt_net config init, closed by
# performing the routine on the host: runtime/socom2_rtnet_config.h). The r0001 gate never runs that code -- the
# install happens only with PS2X_SOCOM2_UDP_SHIFT set -- so the proof is a round with a second instance:
#
#   1. (r0004, cheap) the r0004 image boots to the title with PS2X_SOCOM2_UDP_SHIFT=2 for R0004_BOOT_S seconds (45):
#      its log must carry the install line with the r0004 getter global. Skipped when the r0004 image or exe is not
#      there (R0004_ELF, default game/disc_r0004/socom2_game.elf; R0004_EXE, default dist-r0004/socom2.exe).
#   2. two instances of OUR exe against the server env.sh names (the hosted box unless SOCOM_SERVER_IP says
#      otherwise), through the two-instance driver online_match_ours --prefilled. Instance B carries
#      PS2X_SOCOM2_UDP_SHIFT=2 from the driver's own INSTANCES table and the second RSA pair from
#      PS2X_SOCOM2_RSA_KEY_B=b (docs/KNOBS.md); PS2X_SOCOM2_NET_TRACE=1 on both, so B's tcp sends and A's peer
#      sends are in the logs. Default: a one-round Frostfire control round (nobody fires, the round runs to its
#      clock), which is also C8's online leg (the msifrpc HLE and the RSA pair) and carries the NetIdle [ret] count
#      C3's F11 note asks for; --lobby-only drops the control round's watches and endgame and holds 60 s after READY
#      (the match still launches -- both instances READY -- so a round starts; only the driving stops).
#   3. the verdict: tools_py/parity/control_round_readout.py udp-shift -> <out>/VERDICT.txt.
#
# THE DME RECORD. B publishes its NetAddress pair in its DME client record; the server logs the payload, the client
# only dumps the first 96 bytes of each tcp send (and the stream may be encrypted). The readout reads
# <out>/server-dme.log when it is there, else B's tcp send hex, and says NO-DATA (RESULT INCOMPLETE) when neither
# shows the record. The hosted box's DME log is <server dir>/logs/dme.log (server/config/dme.json's LogPath); copy
# the round's stretch of it to <out>/server-dme.log (over SSH, docs of the box: vm/lightsail/README.md, not tracked)
# and re-run the readout: python -m tools_py.parity.control_round_readout udp-shift <out>
#
# Usage (under the lock the controller holds; this script never takes it):
#   bash scripts/loop_lock.sh run s13 --wait <min> -- bash scripts/parity/control_round_udp_shift.sh [--lobby-only] [--no-r0004] [out]
#   default out logs/parity/s13_c3_udp_shift_<stamp>. Writes logs/<name>.done as its last act: done <rc> <RESULT>.
# Needs: persona B on game/disc/mc0_b (--existing-b), no socom2.exe running.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. "$(dirname "$0")/env.sh"
. "$(dirname "$0")/write_env.sh"    # write_env_ps2x: the PS2X_* record beside a capture (issue #38)
socom_require_python control_round_udp_shift

LOBBY_ONLY=0
R0004=auto
while :; do
  case "${1:-}" in
    --lobby-only) LOBBY_ONLY=1; shift ;;
    --no-r0004) R0004=0; shift ;;
    --r0004) R0004=1; shift ;;
    *) break ;;
  esac
done
OUT="${1:-logs/parity/s13_c3_udp_shift_$(date +%Y%m%d_%H%M%S)}"
NAME="$(basename "$OUT")"
mkdir -p "$OUT" logs
rm -f "logs/${NAME}.done"
OUT_ABS="$(cd "$OUT" && pwd)"
export PATH="/usr/bin:/bin:$PATH"
finish() { echo "done $1 $2" > "logs/${NAME}.done"; exit "$1"; }

# The round's knobs (the instruments come from env.sh above).
export PS2X_SOCOM2_RSA_KEY_B=b          # instance B's second RSA pair (online_login_ours.INSTANCES reads it)
export PS2X_SOCOM2_NET_TRACE=1          # B's tcp send hex (the DME record), A's `udp peer send` rows
export PS2X_SOCOM2_NET_TRACE_PEERS=200  # the default 16 stops before research/18's send #16 (the pre-fix self-send)

ROUND_TXT="$OUT/round.txt"
: > "$ROUND_TXT"
note() { echo "$1" >> "$ROUND_TXT"; }
note "ROUND=udp-shift"
note "SERVER=$PS2X_SOCOM2_SERVER"
note "LOBBY_ONLY=$LOBBY_ONLY"
note "STARTED=$(date -u +%FT%TZ)"

if "$PYTHON" -c "import sys; from tools_py.parity import hostplatform; sys.exit(0 if hostplatform.process_running('socom2') else 1)"; then
  echo "control_round_udp_shift: a socom2 is already running -- refusing (the round needs the host to itself)" >&2
  finish 6 refused-game-running
fi
if command -v powershell >/dev/null 2>&1; then
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 >/dev/null 2>&1
fi

# 1. The r0004 boot: the install line only (a title boot; no instruments -- PS2X_PEEK is env.sh's r0001 render).
R0004_ELF="${R0004_ELF:-game/disc_r0004/socom2_game.elf}"
R0004_EXE="${R0004_EXE:-dist-r0004/socom2.exe}"
if [ "$R0004" != 0 ] && [ -f "$R0004_ELF" ] && [ -f "$R0004_EXE" ]; then
  (
    unset PS2X_PEEK PS2X_CALL_TRACE
    export SOCOM_GAME_ELF="$R0004_ELF" SOCOM_EXE="$R0004_EXE" PS2X_SOCOM2_UDP_SHIFT=2 PS2X_SOCOM2_RSA_KEY=b
    export PS2X_RUN_LOG="$OUT_ABS/r0004_boot.log"
    write_env_ps2x "$OUT/r0004" "control_round_udp_shift.sh r0004 boot (title only, UDP shift 2)"
    bash ./run.sh "${R0004_BOOT_S:-45}" > "$OUT/r0004_run_sh.txt" 2>&1
  )
  note "R0004_LOG=$OUT/r0004_boot.log"
  "$PYTHON" -c "from tools_py.parity import hostplatform; hostplatform.kill_process_by_name('socom2')" >/dev/null 2>&1
  sleep 5
elif [ "$R0004" = 1 ]; then
  echo "control_round_udp_shift: --r0004 given but $R0004_ELF or $R0004_EXE is missing" >&2
  finish 8 refused-no-r0004
else
  note "R0004_LOG="
fi

# 2. The two-instance round.
DRIVE="$OUT/drive.txt"
touch "$OUT/.t0"
if [ "$LOBBY_ONLY" = 1 ]; then
  ARGS=(--existing-b --prefilled --hold 60 --map frostfire --out "$OUT" --seconds 900)
else
  ARGS=(--existing-b --prefilled --hold 30 --control-round --rounds 1 --map frostfire
        --max-steps 60 --max-walk-seconds 240 --out "$OUT" --seconds 1200)
fi
# Issue #38: the PS2X_* the launch is handed, beside its output, the moment before it starts.
write_env_ps2x "$OUT" "control_round_udp_shift.sh lobby_only=$LOBBY_ONLY (B: PS2X_SOCOM2_UDP_SHIFT=2 from the driver)"
"$PYTHON" -m tools_py.parity.online_match_ours "${ARGS[@]}" > "$DRIVE" 2>&1
rc=$?
echo "mpexit=$rc" >> "$DRIVE"
t0_logs() { find logs -maxdepth 1 -name "run_$1_*.log" -newer "$OUT/.t0" 2>/dev/null | sort | tail -1; }
note "A_LOG=$(t0_logs A)"
note "B_LOG=$(t0_logs B)"
note "DRIVE=$DRIVE"
note "MPEXIT=$rc"

# 3. The verdict.
"$PYTHON" -m tools_py.parity.control_round_readout udp-shift "$OUT" > "$OUT/VERDICT.txt" 2>&1
vrc=$?
cat "$OUT/VERDICT.txt"
finish "$vrc" "$(grep -a -o 'RESULT UDP-SHIFT [A-Z]*' "$OUT/VERDICT.txt" | tail -1) mpexit=$rc"
