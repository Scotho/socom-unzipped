#!/usr/bin/env bash
# Sprint 10 Goal 3, leg 2: the CONSOLE hosts (PCSX2 instance A through tools_py.parity.pcsx2_shell host), OURS joins
# (online_login_ours --join), both READY, the round runs, both walk. The reverse of mixed_match2.sh.
#
# Usage: scripts/parity/mixed_match2_leg2.sh [out dir] [pcsx2 persona] [--existing] [instance A|B]
#   default out logs/parity/mixed2_pcsx2_hosts, persona socomp, instance B. Leg 2d (2026-09-20): with instance A
#   hosting, ours' join reached the game and was "Disconnected from Game" -- A's peer UDP port is the default 3658,
#   the same port ours binds on the same host; B's pnach shifts it to 3660 (research/18 section 1 a), as in leg 1,
#   where ours hosted on 3658 and B joined from 3660. So the console host is B unless told otherwise. Needs what
#   mixed_match2.sh needs (the DNS stub on the LAN address answering SOCOM_SERVER_IP, tools/pcsx2 with the pnach and
#   a card carrying a network configuration). Run under the loop lock: two game instances.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# The done marker is promised from here on (fix round 2, N4). Every refusal before the run proper --
# env.sh's own `exit 1` when the revision cannot be established, this leg's render refusal below, the
# DNS-stub and PCSX2-launch checks -- must leave a marker, or a poller watching logs/<name>.done waits
# out the whole run on a leg that never started. The specific refusals write their own (with the
# reason); this trap catches anything that does not, including the `exit` inside a sourced env.sh.
OUT_EARLY="${1:-}"
NAME_EARLY="$(basename "${OUT_EARLY:-logs/parity/mixed2_pcsx2_hosts}")"
mkdir -p logs
rm -f "logs/${NAME_EARLY}.done"
_socom_refusal() {
  _rc=$?
  if [ "$_rc" -ne 0 ] && [ ! -f "logs/${NAME_EARLY}.done" ]; then
    echo "done $_rc refused-before-launch" > "logs/${NAME_EARLY}.done"
  fi
}
trap _socom_refusal EXIT
. "$(dirname "$0")/env.sh"
. "$(dirname "$0")/write_env.sh"    # write_env_ps2x: the PS2X_* record beside a capture (issue #38)
socom_require_python mixed_match2_leg2
# The DNS stub binds LAN_IP: it must be IPv4, and it has no default.
socom_require_ipv4 LAN_IP mixed_match2_leg2 || exit 9
OUT="${1:-logs/parity/mixed2_pcsx2_hosts}"
PERSONA="${2:-socomp}"
EXISTING="${3:-}"
TAG="${4:-B}"
if [ "$TAG" = A ]; then PINE=28011; else PINE=28012; fi
NAME="$(basename "$OUT")"
PCSX2_OUT="$OUT/pcsx2"
mkdir -p "$OUT" "$PCSX2_OUT"
export PATH="/usr/bin:/bin:$PATH"
rm -f "logs/${NAME}.done"
# THIS LEG'S NARROWER PS2X_PEEK, rendered per revision (Sprint 11 Task 19, review F2): no CZNetGame
# valve name bytes and no deref levels -- the console client is scored from its captures, not from
# valves. It OVERRIDES env.sh's wider block on purpose (a hard assignment, as the literal here
# always was), which is why it has to be rendered too: a literal here is env.sh's render undone,
# and an r0004 leg would cut its rows at r0001's addresses and score silence (s11_r0004_round1).
# The column comes from the image $SOCOM_GAME_ELF names, the same way env.sh picks its own.
if ! _socom_mixed_peek="$("$PYTHON" -m tools_py.parity.guest_addresses --env --profile mixed)"; then
  echo "${0##*/}: the per-revision instrument addresses could not be resolved (see above) -- refusing" >&2
  echo "  to hand this leg another revision's PS2X_PEEK" >&2
  unset _socom_mixed_peek
  # The done marker, like every other refusal here (fix round 2, N4): a poller watching
  # logs/<name>.done would otherwise wait out the whole run on a leg that never started.
  echo "done 8 instrument-addresses" > "logs/${NAME}.done"
  exit 8
fi
eval "$_socom_mixed_peek"
unset _socom_mixed_peek
export PS2X_PEEK
LAN="$LAN_IP"
if ! netstat -an | grep -q "$LAN:53 "; then
  echo "mixed_match2_leg2: the DNS stub is not listening on $LAN:53" >&2
  echo "done 5" > "logs/${NAME}.done"; exit 5
fi
"$PYTHON" -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 > /dev/null 2>&1
"$PYTHON" -c "from tools_py.parity import hostplatform; hostplatform.kill_process_by_name('socom2')" > /dev/null 2>&1
"$PYTHON" -m tools_py.parity.pcsx2_ctl launch "$TAG" > "$OUT/pcsx2_launch.txt" 2>&1 || { echo "done 6" > "logs/${NAME}.done"; exit 6; }
# The console hosts first (verified: boot, login, CREATE GAME on Frostfire, the lobby); ours then logs in and joins.
PYTHONPATH="$ROOT" "$PYTHON" -m tools_py.parity.pcsx2_shell host "$TAG" --name "$PERSONA" $EXISTING --game test --out "$PCSX2_OUT" > "$OUT/pcsx2_host.txt" 2>&1
HOST_RC=$?
echo "pcsx2 host rc=$HOST_RC" > "logs/parity/drive_${NAME}.txt"
if [ "$HOST_RC" -ne 0 ]; then
  grep -a "RESULT\|LOBBY class" "$OUT/pcsx2_host.txt" >> "logs/parity/drive_${NAME}.txt"
  "$PYTHON" -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
  echo "done $HOST_RC" > "logs/${NAME}.done"; exit $HOST_RC
fi
# Issue #38: the PS2X_* the launch is handed (env.sh's instruments and this script's own), beside its output,
# the moment before it starts; the driver adds only per-instance plumbing (screenshot path, card dir) on top.
write_env_ps2x "$OUT" "mixed_match2_leg2.sh (ours; the PCSX2 side has no PS2X_* knobs)"
"$PYTHON" -m tools_py.parity.online_login_ours --existing --name socomc --join --hold 30 --play 4 --out "$OUT" --seconds 600 >> "logs/parity/drive_${NAME}.txt" 2>&1 &
OURS_PID=$!
# The host readies only once ours has joined and dismissed the notice (leg 2e: a host already READY launched the
# match the moment ours joined, and ours' harness, still verifying the lobby, read the map briefing instead).
# Ours readies 35 s after its join; the console a few seconds after ours' notice is gone; the launch follows both.
for i in $(seq 1 80); do
  grep -a -q "join:continue press=cross verified=True" "logs/parity/drive_${NAME}.txt" 2>/dev/null && break
  if ! kill -0 $OURS_PID 2>/dev/null; then break; fi
  sleep 5
done
sleep 8
PYTHONPATH="$ROOT" "$PYTHON" -m tools_py.parity.pcsx2_shell ready "$TAG" --out "$PCSX2_OUT" > "$OUT/pcsx2_ready.txt" 2>&1
echo "pcsx2 ready rc=$?" >> "logs/parity/drive_${NAME}.txt"
sleep 40
# `--spec 0x416054:3` here is the CONSOLE's address, read out of PCSX2 through PINE -- not ours and
# not env.sh's PS2X_PEEK. It stays an r0001 literal because PCSX2 in these legs boots the r0001
# disc, by definition of a mixed match (review F2): there is no other revision for it to be.
PYTHONPATH="$ROOT" "$PYTHON" -m tools_py.parity.cam_poll --port "$PINE" --spec 0x416054:3 --spec "*0x488de8+0x120:96" --out "$OUT/pcsx2_pos.txt" --seconds 100 --every 1.0 > "$OUT/pcsx2_pos.log" 2>&1 &
POLL=$!
"$PYTHON" -m tools_py.parity.pcsx2_ctl watch "$TAG" play 60 1.0 --out "$PCSX2_OUT" > "$OUT/pcsx2_watch.txt" 2>&1 &
WATCH=$!
sleep 15
for i in 1 2 3 4; do
  "$PYTHON" -m tools_py.parity.pcsx2_ctl hold "$TAG" LUP 3.0 >> "$OUT/pcsx2_walk.txt" 2>&1
  sleep 12
done
wait $WATCH
wait $POLL
wait $OURS_PID
rc=$?
"$PYTHON" -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
"$PYTHON" -c "from tools_py.parity import hostplatform; hostplatform.kill_process_by_name('socom2')" > /dev/null 2>&1
echo "mpexit=$rc" >> "logs/parity/drive_${NAME}.txt"
echo "done $rc" > "logs/${NAME}.done"
exit $rc
