#!/usr/bin/env bash
# Sprint 10 Goal 3, leg 1 on the verified flow: OURS hosts, a PCSX2 client joins -- the console side driven by
# tools_py.parity.pcsx2_shell (every press read back, dropped presses re-sent, a miss classified where it happens)
# instead of mixed_match.sh's fixed-timing macros, which lost their place at boot on 2026-09-17 (KNOWN section 2).
# Bars as before: gameplay reached on both, the movement bar on ours (the --play walk bursts against the position
# peek), and on the console client our player seen moving (motion_diff over PCSX2's 1 Hz captures during ours'
# walk vs. its stand).
#
# Usage: scripts/parity/mixed_match2.sh [out dir] [pcsx2 persona] [--existing]
#   default out logs/parity/mixed2_ours_hosts, persona socomq (created on B's card the first time; pass --existing
#   once it is there). Needs: the Horizon stack the DNS stub points at (SOCOM_SERVER_IP, env.sh), the DNS stub
#   listening on the LAN address, tools/pcsx2_b with the clientB pnach and a card carrying a network configuration
#   (research/18 section 1 a-c). Run under the loop lock: two game instances.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. "$(dirname "$0")/env.sh"
OUT="${1:-logs/parity/mixed2_ours_hosts}"
PERSONA="${2:-socomq}"
EXISTING="${3:-}"
NAME="$(basename "$OUT")"
PCSX2_OUT="$OUT/pcsx2"
mkdir -p "$OUT" "$PCSX2_OUT"
export PATH="/usr/bin:/bin:$PATH"
rm -f "logs/${NAME}.done"
export PS2X_PEEK="0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,0x4365c0:1,0x408f10:2,0x408c58:4"
LAN="${LAN_IP:-192.168.2.10}"
if ! netstat -an | grep -q "$LAN:53 "; then
  echo "mixed_match2: the DNS stub is not listening on $LAN:53 -- start tools_py.parity.dns_stub --bind $LAN --answer $SOCOM_SERVER_IP first" >&2
  echo "done 5" > "logs/${NAME}.done"; exit 5
fi
python -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
python -m tools_py.parity.pcsx2_ctl launch B > "$OUT/pcsx2_launch.txt" 2>&1 || { echo "done 6" > "logs/${NAME}.done"; exit 6; }
# Ours logs in and hosts (verified), holds the lobby and then walks; the console client joins beside it.
python -m tools_py.parity.online_match_ours --existing-b --foreign-b --hold 30 --play 4 --map "Frostfire" \
       --out "$OUT" --seconds 900 > "logs/parity/drive_${NAME}.txt" 2>&1 &
OURS_PID=$!
PYTHONPATH="$ROOT" python -m tools_py.parity.pcsx2_shell join B --name "$PERSONA" $EXISTING --out "$PCSX2_OUT" > "$OUT/pcsx2_join.txt" 2>&1
JOIN_RC=$?
echo "pcsx2 join rc=$JOIN_RC" >> "logs/parity/drive_${NAME}.txt"
if [ "$JOIN_RC" -eq 0 ]; then
  PYTHONPATH="$ROOT" python -m tools_py.parity.pcsx2_shell ready B --out "$PCSX2_OUT" > "$OUT/pcsx2_ready.txt" 2>&1
  echo "pcsx2 ready rc=$?" >> "logs/parity/drive_${NAME}.txt"
fi
# The console side of the movement bar: its own position over PINE (instance B, port 28012; the camera/player
# block cam_poll reads) once a second through the round, while it walks four 3 s bursts -- ours' peek and walk
# are the host's side (online_match_ours --play). Both instances then have a position trail through the same round.
sleep 45                                                  # the host's READY (joiner + 35 s) and the launch countdown
PYTHONPATH="$ROOT" python -m tools_py.parity.cam_poll --port 28012 --out "$OUT/pcsx2_pos.txt" --seconds 100 --every 1.0 > "$OUT/pcsx2_pos.log" 2>&1 &
POLL=$!
python -m tools_py.parity.pcsx2_ctl watch B play 60 1.0 --out "$PCSX2_OUT" > "$OUT/pcsx2_watch.txt" 2>&1 &
WATCH=$!
sleep 15
for i in 1 2 3 4; do
  python -m tools_py.parity.pcsx2_ctl hold B W 3.0 >> "$OUT/pcsx2_walk.txt" 2>&1
  sleep 12
done
wait $WATCH
wait $POLL
wait $OURS_PID
rc=$?
python -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
python - "$PCSX2_OUT" >> "logs/parity/drive_${NAME}.txt" <<'EOF'
import glob, os, sys
from PIL import Image
from tools_py.parity import motion_diff
d = sys.argv[1]
frames = [motion_diff.luma(Image.open(p)) for p in sorted(glob.glob(os.path.join(d, "B_play*.png")))]
ok, detail = motion_diff.motion_verdict(frames[:20], frames[-20:]) if len(frames) >= 40 else (False, f"NO-DATA {len(frames)} captures")
print(f"RESULT MIXED-MATCH console-sees-ours-moving={'yes' if ok else 'no'} ({detail})")
EOF
echo "mpexit=$rc" >> "logs/parity/drive_${NAME}.txt"
echo "done $rc" > "logs/${NAME}.done"
exit $rc
