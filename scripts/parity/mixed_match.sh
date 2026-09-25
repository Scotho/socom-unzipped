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
# The done marker is promised from here on (fix round 2, N4). Every refusal before the run proper --
# env.sh's own `exit 1` when the revision cannot be established, this leg's render refusal below, the
# DNS-stub and PCSX2-launch checks -- must leave a marker, or a poller watching logs/<name>.done waits
# out the whole run on a leg that never started. The specific refusals write their own (with the
# reason); this trap catches anything that does not, including the `exit` inside a sourced env.sh.
OUT_EARLY="${1:-}"
NAME_EARLY="$(basename "${OUT_EARLY:-logs/parity/mixed_ours_hosts}")"
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
socom_require_python mixed_match
# The DNS stub binds and answers SOCOM_SERVER_IP here, so it must be the LAN IP, not env.sh's hosted name.
socom_require_ipv4 SOCOM_SERVER_IP mixed_match || exit 9
OUT="${1:-logs/parity/mixed_ours_hosts}"
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

if ! netstat -an | grep -q "$SOCOM_SERVER_IP:53 "; then
  echo "mixed_match: the DNS stub is not listening on $SOCOM_SERVER_IP:53 -- start tools_py.parity.dns_stub first" >&2
  echo "done 5" > "logs/${NAME}.done"; exit 5
fi

# PCSX2 B boots first (a cold boot is ~90 s; the join macro waits it out), while ours logs in and hosts.
"$PYTHON" -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
"$PYTHON" -m tools_py.parity.pcsx2_ctl launch B > "$OUT/pcsx2_launch.txt" 2>&1 || { echo "done 6" > "logs/${NAME}.done"; exit 6; }
"$PYTHON" -m tools_py.parity.online_match_ours --existing-b --foreign-b --hold 30 --play 4 --map "Frostfire" \
       --out "$OUT" --seconds 900 > "logs/parity/drive_${NAME}.txt" 2>&1 &
OURS_PID=$!
# the joiner: the macro's fixed timings put its JOIN press ~3.5 min after boot, when ours' game lobby is up
"$PYTHON" -m tools_py.parity.pcsx2_ctl join B --name socomx7 --game test --out "$PCSX2_OUT" > "$OUT/pcsx2_join.txt" 2>&1
# the console client's captures at 1 Hz through ours' hold and walk (60 s covers --hold 30 and four 3 s bursts)
"$PYTHON" -m tools_py.parity.pcsx2_ctl watch B play 60 1.0 --out "$PCSX2_OUT" > "$OUT/pcsx2_watch.txt" 2>&1
wait $OURS_PID
rc=$?
"$PYTHON" -m tools_py.parity.pcsx2_ctl kill > /dev/null 2>&1
# the console-side motion verdict: the first 20 captures (ours holds still) against the last 20 (ours walks)
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
