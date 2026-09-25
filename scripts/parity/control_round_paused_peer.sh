#!/usr/bin/env bash
# Sprint 13 Task V7 (#34) -- the control round with the PEER paused mid-round: does A's game keep running while the
# other side has gone quiet?
#
# #34's candidate (research/29 shape 2): a sceInetRecv with a timeout on a socket whose peer stopped sending held the
# EE executor inside libnetb's waitReadable for up to 10 s -- no guest instruction, no VBlank, no frame. V7 bounds the
# wait by the guest tick and parks the calling guest thread instead (`net_park=` on the sampler line). The round:
#
#   * A is traced with PS2X_PC_SAMPLER=0.25 PS2X_CLOCK_TRACE=1 PS2X_SOCOM2_NET_TRACE=1 (research/34's FreezeFields
#     line) and PS2X_GS_STATS=1 (the `[gs-gl stats] ... guest_frames=` lines); the same environment reaches the peer,
#     which is paused anyway.
#   * the peer is paused with tools_py/parity/peer_pause.py once A's round clock reads --at-clock s (30), for
#     --pause-s s (30: three times the 10 s cap), then resumed; A's frame is captured every 2 s from 10 s before the
#     pause to 20 s after it (the runtime's logs/parity/latest_frame_A.png, the file every harness capture reads).
#   * --peer ours (default): two instances of OUR exe through the two-instance driver, no watches (a --hold round:
#     the converge endgame's move-path watch would end the round on the stalled peer before the pause ended); the
#     peer is instance B (window SOCOM-B), suspended with NtSuspendProcess.
#     --peer console: #34's bar exactly -- the mixed leg (scripts/parity/mixed_match2.sh: ours hosts, PCSX2 client B
#     joins) with MIXED_HOLD holding ours in the round; the peer is PCSX2 B's process (pcsx2_ctl's state file).
#     Needs what that leg needs: LAN_IP (this machine's LAN address, the DNS stub binds it) and SOCOM_SERVER_IP as
#     an IPv4 address (the stub answers the console with it), both from the operator's environment -- never
#     tracked; START_DNS_STUB=1 starts tools_py.parity.dns_stub for the leg and stops it after.
#   * --before: the same round on an exe from before V7, for the contrast (a `[clock]` hole with net_wait=1). It
#     requires SOCOM_EXE to be set, so the record names the exe that ran.
#   * the verdict: tools_py/parity/control_round_readout.py paused-peer -> <out>/VERDICT.txt, and
#     freeze_trace over A's whole log (-> <out>/freeze_trace_A.txt).
#
# Usage (under the lock the controller holds; this script never takes it):
#   bash scripts/loop_lock.sh run s13 --wait <min> -- bash scripts/parity/control_round_paused_peer.sh \
#        [--before] [--peer ours|console] [--pause-s 30] [--at-clock 30] [out]
#   default out logs/parity/s13_v7_paused_peer_<stamp> (…_before_<stamp> with --before). Writes logs/<name>.done
#   as its last act: done <rc> <RESULT>. Knobs: PAUSED_HOLD_S (420: how long the driver holds the round after READY),
#   MIXED_PERSONA (socomq), MIXED_EXISTING (1: the persona is on the console's card).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. "$(dirname "$0")/env.sh"
. "$(dirname "$0")/write_env.sh"    # write_env_ps2x: the PS2X_* record beside a capture (issue #38)
socom_require_python control_round_paused_peer

MODE=after
PEER=ours
PAUSE_S=30
AT_CLOCK=30
while :; do
  case "${1:-}" in
    --before) MODE=before; shift ;;
    --peer) PEER="${2:?--peer ours|console}"; shift 2 ;;
    --pause-s) PAUSE_S="${2:?--pause-s <s>}"; shift 2 ;;
    --at-clock) AT_CLOCK="${2:?--at-clock <s>}"; shift 2 ;;
    *) break ;;
  esac
done
case "$PEER" in ours|console) ;; *) echo "control_round_paused_peer: --peer is ours or console, not '$PEER'" >&2; exit 2 ;; esac
if [ "$MODE" = before ]; then
  OUT="${1:-logs/parity/s13_v7_paused_peer_before_$(date +%Y%m%d_%H%M%S)}"
else
  OUT="${1:-logs/parity/s13_v7_paused_peer_$(date +%Y%m%d_%H%M%S)}"
fi
NAME="$(basename "$OUT")"
mkdir -p "$OUT" logs
rm -f "logs/${NAME}.done" "$OUT/.driver_rc"
export PATH="/usr/bin:/bin:$PATH"
finish() { echo "done $1 $2" > "logs/${NAME}.done"; exit "$1"; }

if [ "$MODE" = before ] && [ -z "${SOCOM_EXE:-}" ]; then
  echo "control_round_paused_peer: --before needs SOCOM_EXE naming the exe from before V7 (the record must say which" >&2
  echo "  exe gave the contrast; the default dist/socom2.exe is whatever was built last)" >&2
  finish 2 refused-before-without-exe
fi
if [ "$PEER" = console ]; then
  socom_require_ipv4 LAN_IP control_round_paused_peer || finish 9 refused-lan-ip
  socom_require_ipv4 SOCOM_SERVER_IP control_round_paused_peer || finish 9 refused-server-ip
fi

# The round's knobs: research/34's FreezeFields line on the sampler, the clock trace, the net trace, the GS stats.
export PS2X_PC_SAMPLER=0.25
export PS2X_CLOCK_TRACE=1
export PS2X_SOCOM2_NET_TRACE=1
export PS2X_GS_STATS=1
export PS2X_SOCOM2_RSA_KEY_B=b          # instance B's second RSA pair (online_login_ours.INSTANCES reads it)
HOLD="${PAUSED_HOLD_S:-420}"

ROUND_TXT="$OUT/round.txt"
: > "$ROUND_TXT"
note() { echo "$1" >> "$ROUND_TXT"; }
note "ROUND=paused-peer"
note "MODE=$MODE"
note "PEER=$PEER"
note "PAUSE_S=$PAUSE_S"
note "AT_CLOCK=$AT_CLOCK"
note "SERVER=$PS2X_SOCOM2_SERVER"
note "EXE=${SOCOM_EXE:-dist/socom2.exe}"
note "STARTED=$(date -u +%FT%TZ)"

if "$PYTHON" -c "import sys; from tools_py.parity import hostplatform; sys.exit(0 if hostplatform.process_running('socom2') else 1)"; then
  echo "control_round_paused_peer: a socom2 is already running -- refusing (the round needs the host to itself)" >&2
  finish 6 refused-game-running
fi
if command -v powershell >/dev/null 2>&1; then
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 >/dev/null 2>&1
fi

touch "$OUT/.t0"
STUB_PID=""
if [ "$PEER" = ours ]; then
  DRIVE="$OUT/drive.txt"
  # Issue #38: the PS2X_* the launch is handed, beside its output, the moment before it starts.
  write_env_ps2x "$OUT" "control_round_paused_peer.sh mode=$MODE peer=ours hold=$HOLD"
  ( "$PYTHON" -m tools_py.parity.online_match_ours --existing-b --prefilled --hold "$HOLD" --map frostfire \
        --out "$OUT" --seconds 1500 > "$DRIVE" 2>&1
    echo $? > "$OUT/.driver_rc" ) &
  DRIVER=$!
else
  MIXED_OUT="$OUT/${NAME}_mixed"
  DRIVE="logs/parity/drive_$(basename "$MIXED_OUT").txt"
  if [ "${START_DNS_STUB:-0}" = 1 ] && ! netstat -an | grep -q "$LAN_IP:53 "; then
    "$PYTHON" -m tools_py.parity.dns_stub --bind "$LAN_IP" --answer "$SOCOM_SERVER_IP" > "$OUT/dns_stub.txt" 2>&1 &
    STUB_PID=$!
    sleep 3
  fi
  EXISTING=""
  [ "${MIXED_EXISTING:-1}" = 1 ] && EXISTING="--existing"
  # mixed_match2.sh records its own environment (write_env_ps2x) and runs ours with --hold $MIXED_HOLD.
  ( MIXED_HOLD="$HOLD" bash scripts/parity/mixed_match2.sh "$MIXED_OUT" "${MIXED_PERSONA:-socomq}" $EXISTING
    echo $? > "$OUT/.driver_rc" ) &
  DRIVER=$!
fi
note "DRIVE=$DRIVE"

"$PYTHON" -m tools_py.parity.peer_pause run --out "$OUT" --peer "$PEER" --pause-s "$PAUSE_S" --at-clock "$AT_CLOCK" \
      --mode "$MODE" --stop-file "$OUT/.driver_rc" --timeout 1200 > "$OUT/pause.txt" 2>&1
prc=$?
cat "$OUT/pause.txt"
wait "$DRIVER"
drc="$(cat "$OUT/.driver_rc" 2>/dev/null || echo none)"
if [ -n "$STUB_PID" ]; then kill "$STUB_PID" 2>/dev/null; fi
"$PYTHON" -c "from tools_py.parity import hostplatform; hostplatform.kill_process_by_name('socom2')" >/dev/null 2>&1

t0_logs() { find logs -maxdepth 1 -name "run_$1_*.log" -newer "$OUT/.t0" 2>/dev/null | sort | tail -1; }
A_LOG="$(t0_logs A)"
B_LOG="$(t0_logs B)"
note "A_LOG=$A_LOG"
note "B_LOG=$B_LOG"
note "PAUSE_RC=$prc"
note "DRIVER_RC=$drc"
if [ -n "$A_LOG" ]; then
  if [ -n "$B_LOG" ]; then
    "$PYTHON" -m tools_py.parity.freeze_trace "$A_LOG" --peer "$B_LOG" > "$OUT/freeze_trace_A.txt" 2>&1
  else
    "$PYTHON" -m tools_py.parity.freeze_trace "$A_LOG" > "$OUT/freeze_trace_A.txt" 2>&1
  fi
fi

BEFORE_FLAG=()
[ "$MODE" = before ] && BEFORE_FLAG=(--before)
"$PYTHON" -m tools_py.parity.control_round_readout paused-peer "$OUT" "${BEFORE_FLAG[@]}" > "$OUT/VERDICT.txt" 2>&1
vrc=$?
cat "$OUT/VERDICT.txt"
finish "$vrc" "$(grep -a -o 'RESULT PAUSED-PEER [A-Z]*' "$OUT/VERDICT.txt" | tail -1) driver=$drc pause=$prc"
