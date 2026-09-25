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
# The done marker is promised from here on (fix round 2, N4). Every refusal before the run proper --
# env.sh's own `exit 1` when the revision cannot be established, this leg's render refusal below, the
# DNS-stub and PCSX2-launch checks -- must leave a marker, or a poller watching logs/<name>.done waits
# out the whole run on a leg that never started. The specific refusals write their own (with the
# reason); this trap catches anything that does not, including the `exit` inside a sourced env.sh.
OUT_EARLY="${1:-}"
NAME_EARLY="$(basename "${OUT_EARLY:-logs/parity/mixed2_ours_hosts}")"
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
socom_require_python mixed_match2
# The DNS stub binds LAN_IP and answers SOCOM_SERVER_IP: both must be IPv4, and neither has a default.
socom_require_ipv4 LAN_IP mixed_match2 || exit 9
socom_require_ipv4 SOCOM_SERVER_IP mixed_match2 || exit 9
OUT="${1:-logs/parity/mixed2_ours_hosts}"
PERSONA="${2:-socomq}"
EXISTING="${3:-}"
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
  echo "mixed_match2: the DNS stub is not listening on $LAN:53 -- start tools_py.parity.dns_stub --bind $LAN --answer $SOCOM_SERVER_IP first" >&2
  echo "done 5" > "logs/${NAME}.done"; exit 5
fi
"$PYTHON" -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
# A host left over from the previous leg keeps its game up on the server, and the console client would join THAT
# (mixed2_ours_hosts_b joined socomc's game while this run's host refused to start: "socom2.exe is already running").
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 > /dev/null 2>&1
"$PYTHON" -c "from tools_py.parity import hostplatform; hostplatform.kill_process_by_name('socom2')" > /dev/null 2>&1
"$PYTHON" -m tools_py.parity.pcsx2_ctl launch B > "$OUT/pcsx2_launch.txt" 2>&1 || { echo "done 6" > "logs/${NAME}.done"; exit 6; }
# Ours logs in and hosts (verified), holds the lobby and then walks; the console client joins beside it.
"$PYTHON" -m tools_py.parity.online_match_ours --existing-b --foreign-b --hold 30 --play 4 --map "Frostfire" \
       --out "$OUT" --seconds 900 > "logs/parity/drive_${NAME}.txt" 2>&1 &
OURS_PID=$!
PYTHONPATH="$ROOT" "$PYTHON" -m tools_py.parity.pcsx2_shell join B --name "$PERSONA" $EXISTING --out "$PCSX2_OUT" > "$OUT/pcsx2_join.txt" 2>&1
JOIN_RC=$?
echo "pcsx2 join rc=$JOIN_RC" >> "logs/parity/drive_${NAME}.txt"
if [ "$JOIN_RC" -eq 0 ]; then
  sleep 35                                                # "The READY button will be available in 30 seconds": a press before that does nothing (leg 1c)
  PYTHONPATH="$ROOT" "$PYTHON" -m tools_py.parity.pcsx2_shell ready B --out "$PCSX2_OUT" > "$OUT/pcsx2_ready.txt" 2>&1
  echo "pcsx2 ready rc=$?" >> "logs/parity/drive_${NAME}.txt"
fi
# The console side of the movement bar: its own position over PINE (instance B, port 28012; the camera/player
# block cam_poll reads) once a second through the round, while it walks four 3 s bursts -- ours' peek and walk
# are the host's side (online_match_ours --play). Both instances then have a position trail through the same round.
sleep 45                                                  # the host's READY (joiner + 35 s) and the launch countdown
# `--spec 0x416054:3` here is the CONSOLE's address, read out of PCSX2 through PINE -- not ours and
# not env.sh's PS2X_PEEK. It stays an r0001 literal because PCSX2 in these legs boots the r0001
# disc, by definition of a mixed match (review F2): there is no other revision for it to be.
PYTHONPATH="$ROOT" "$PYTHON" -m tools_py.parity.cam_poll --port 28012 --spec 0x416054:3 --spec "*0x488de8+0x120:96" --out "$OUT/pcsx2_pos.txt" --seconds 100 --every 1.0 > "$OUT/pcsx2_pos.log" 2>&1 &
POLL=$!
"$PYTHON" -m tools_py.parity.pcsx2_ctl watch B play 60 1.0 --out "$PCSX2_OUT" > "$OUT/pcsx2_watch.txt" 2>&1 &
WATCH=$!
sleep 15
for i in 1 2 3 4; do
  "$PYTHON" -m tools_py.parity.pcsx2_ctl hold B LUP 3.0 >> "$OUT/pcsx2_walk.txt" 2>&1
  sleep 12
done
wait $WATCH
wait $POLL
wait $OURS_PID
rc=$?
"$PYTHON" -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
"$PYTHON" - "$PCSX2_OUT" >> "logs/parity/drive_${NAME}.txt" <<'EOF'
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
