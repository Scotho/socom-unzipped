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
. "$(dirname "$0")/env.sh"
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
export PS2X_PEEK="0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,0x4365c0:1,0x408f10:2,0x408c58:4"
LAN="${LAN_IP:-192.168.2.10}"
if ! netstat -an | grep -q "$LAN:53 "; then
  echo "mixed_match2_leg2: the DNS stub is not listening on $LAN:53" >&2
  echo "done 5" > "logs/${NAME}.done"; exit 5
fi
python -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 > /dev/null 2>&1
python -c "from tools_py.parity import hostplatform; hostplatform.kill_process_by_name('socom2')" > /dev/null 2>&1
python -m tools_py.parity.pcsx2_ctl launch "$TAG" > "$OUT/pcsx2_launch.txt" 2>&1 || { echo "done 6" > "logs/${NAME}.done"; exit 6; }
# The console hosts first (verified: boot, login, CREATE GAME on Frostfire, the lobby); ours then logs in and joins.
PYTHONPATH="$ROOT" python -m tools_py.parity.pcsx2_shell host "$TAG" --name "$PERSONA" $EXISTING --game test --out "$PCSX2_OUT" > "$OUT/pcsx2_host.txt" 2>&1
HOST_RC=$?
echo "pcsx2 host rc=$HOST_RC" > "logs/parity/drive_${NAME}.txt"
if [ "$HOST_RC" -ne 0 ]; then
  grep -a "RESULT\|LOBBY class" "$OUT/pcsx2_host.txt" >> "logs/parity/drive_${NAME}.txt"
  python -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
  echo "done $HOST_RC" > "logs/${NAME}.done"; exit $HOST_RC
fi
python -m tools_py.parity.online_login_ours --existing --name socomc --join --hold 30 --play 4 --out "$OUT" --seconds 600 >> "logs/parity/drive_${NAME}.txt" 2>&1 &
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
PYTHONPATH="$ROOT" python -m tools_py.parity.pcsx2_shell ready "$TAG" --out "$PCSX2_OUT" > "$OUT/pcsx2_ready.txt" 2>&1
echo "pcsx2 ready rc=$?" >> "logs/parity/drive_${NAME}.txt"
sleep 40
PYTHONPATH="$ROOT" python -m tools_py.parity.cam_poll --port "$PINE" --spec 0x416054:3 --spec "*0x488de8+0x120:96" --out "$OUT/pcsx2_pos.txt" --seconds 100 --every 1.0 > "$OUT/pcsx2_pos.log" 2>&1 &
POLL=$!
python -m tools_py.parity.pcsx2_ctl watch "$TAG" play 60 1.0 --out "$PCSX2_OUT" > "$OUT/pcsx2_watch.txt" 2>&1 &
WATCH=$!
sleep 15
for i in 1 2 3 4; do
  python -m tools_py.parity.pcsx2_ctl hold "$TAG" LUP 3.0 >> "$OUT/pcsx2_walk.txt" 2>&1
  sleep 12
done
wait $WATCH
wait $POLL
wait $OURS_PID
rc=$?
python -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
python -c "from tools_py.parity import hostplatform; hostplatform.kill_process_by_name('socom2')" > /dev/null 2>&1
echo "mpexit=$rc" >> "logs/parity/drive_${NAME}.txt"
echo "done $rc" > "logs/${NAME}.done"
exit $rc
