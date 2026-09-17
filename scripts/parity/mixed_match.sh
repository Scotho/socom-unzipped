#!/usr/bin/env bash
# Sprint 6 Task 7: the mixed match, leg 1 -- OURS hosts, a PCSX2 client joins (research/18 section 1's recipe,
# played by tools_py.parity.pcsx2_ctl). Bars: gameplay reached on both (ours: the HUD in its captures; PCSX2: its
# own captures), the movement bar on ours (the --play walk bursts against the position peek), and on the console
# client our player seen moving (motion_diff over PCSX2's 1 Hz captures during ours' walk vs. its stand).
#
# Usage: scripts/parity/mixed_match.sh [out dir]        (default logs/parity/mixed_ours_hosts)
# Needs: the Horizon stack (server/start-servers.ps1 -Status), the DNS stub
# (python -m tools_py.parity.dns_stub; it reads SOCOM_SERVER_IP too), tools/pcsx2_b with the clientB
# pnach and a card carrying a network configuration (research/18 section 1 a-c).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. "$(dirname "$0")/env.sh"
OUT="${1:-logs/parity/mixed_ours_hosts}"
NAME="$(basename "$OUT")"
PCSX2_OUT="$OUT/pcsx2"
mkdir -p "$OUT" "$PCSX2_OUT"
export PATH="/usr/bin:/bin:$PATH"
rm -f "logs/${NAME}.done"
# Instruments come from scripts/parity/env.sh (sourced above). This leg keeps its own, shorter peek set:
# no CZNetGame valve name bytes and no deref levels -- the console client is scored from its captures.
export PS2X_PEEK="0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,0x4365c0:1,0x408f10:2,0x408c58:4"

if ! netstat -an | grep -q "$SOCOM_SERVER_IP:53 "; then
  echo "mixed_match: the DNS stub is not listening on $SOCOM_SERVER_IP:53 -- start tools_py.parity.dns_stub first" >&2
  echo "done 5" > "logs/${NAME}.done"; exit 5
fi

# PCSX2 B boots first (a cold boot is ~90 s; the join macro waits it out), while ours logs in and hosts.
python -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
python -m tools_py.parity.pcsx2_ctl launch B > "$OUT/pcsx2_launch.txt" 2>&1 || { echo "done 6" > "logs/${NAME}.done"; exit 6; }
python -m tools_py.parity.online_match_ours --existing-b --foreign-b --hold 30 --play 4 --map "Frostfire" \
       --out "$OUT" --seconds 900 > "logs/parity/drive_${NAME}.txt" 2>&1 &
OURS_PID=$!
# the joiner: the macro's fixed timings put its JOIN press ~3.5 min after boot, when ours' game lobby is up
python -m tools_py.parity.pcsx2_ctl join B --name socomx7 --game test --out "$PCSX2_OUT" > "$OUT/pcsx2_join.txt" 2>&1
# the console client's captures at 1 Hz through ours' hold and walk (60 s covers --hold 30 and four 3 s bursts)
python -m tools_py.parity.pcsx2_ctl watch B play 60 1.0 --out "$PCSX2_OUT" > "$OUT/pcsx2_watch.txt" 2>&1
wait $OURS_PID
rc=$?
python -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
# the console-side motion verdict: the first 20 captures (ours holds still) against the last 20 (ours walks)
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
