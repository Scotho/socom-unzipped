#!/usr/bin/env bash
# The endpoint A/B (fix wave A, 2026-09-22): the ten-minute briefing capture again, on a WIRED endpoint, with the
# DEVICE count per minute set beside the Bluetooth run's.
#
#   scripts/loop_lock.sh run <owner> --purpose "endpoint A/B" -- \
#     bash scripts/parity/endpoint_ab.sh --device HyperX [--minutes 10] [--stage briefing] [--baseline <dips.txt>]
#
# What it does, in order, and undoes on ANY exit (the trap):
#   1. tools_py/parity/endpoint_route.py set <device>: backs up the per-app routing key, removes our exes' entries
#      (dist\socom2.exe is pinned to the JBL there, so the default alone moves nothing -- docs/KNOWN.md section 4),
#      and makes <device> the default for the console and multimedia roles (the loopback recorder follows the
#      default; communications is left to whatever call may be up).
#   2. scripts/parity/mission_music_long.sh with the same arguments as the Bluetooth run
#      (logs/parity/mission_music_ours_20260922_024457: --stage briefing --minutes 10).
#   3. endpoint_route.py check on the run's own log: the `[audio] 989snd mix stream open (... device <name> ...)`
#      line must name <device>, or the run is NOT scored as this leg (rc 5). That refusal is the point: three
#      sprints of clean numbers were once taken on the wrong speaker.
#   4. Both runs' "DEVICE per minute" tables side by side, and the verdict line.
#   5. The trap: endpoint_route.py restore -- the defaults back, the routing key re-imported.
#
# The owner's default output device is the wired one for the length of the run (about 16 minutes). Run it only
# in a window they are away from the machine (the host-load rule), never while they are on a call.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

DEVICE=""
MINUTES=10
STAGE=briefing
BASELINE=logs/parity/mission_music_ours_20260922_024457/dips_rescored.txt
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --device) DEVICE=$2; shift 2 ;;
    --minutes) MINUTES=$2; shift 2 ;;
    --stage) STAGE=$2; shift 2 ;;
    --baseline) BASELINE=$2; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; sed -n '2,24p' "$0"; exit 2 ;;
  esac
done
[ -n "$DEVICE" ] || { echo "endpoint_ab: --device <substring of the wired endpoint's name> is required" >&2; exit 2; }

STAMP="endpoint_ab_$(date +%Y%m%d_%H%M%S)"
OUT="logs/parity/$STAMP"
mkdir -p "$OUT"
BACKUP="$OUT/routing_backup"
echo "endpoint A/B: device='$DEVICE' stage=$STAGE minutes=$MINUTES out=$OUT baseline=$BASELINE"
if [ "$DRY" = 1 ]; then
  echo "--dry-run: would set the default to '$DEVICE', run mission_music_long.sh --stage $STAGE --minutes $MINUTES --stamp ${STAMP}_wired, check, compare, restore"
  PYTHONPATH="$ROOT" python -m tools_py.parity.endpoint_route status
  exit 0
fi

PYTHONPATH="$ROOT" python -m tools_py.parity.endpoint_route status | tee "$OUT/routing_before.txt"
PYTHONPATH="$ROOT" python -m tools_py.parity.endpoint_route set "$DEVICE" --backup "$BACKUP" | tee "$OUT/routing_set.txt" || {
  echo "endpoint_ab: could not move the routing -- nothing launched, nothing to restore" >&2; exit 6; }
restore() {
  echo "endpoint_ab: restoring the routing and the defaults"
  PYTHONPATH="$ROOT" python -m tools_py.parity.endpoint_route restore --backup "$BACKUP" | tee "$OUT/routing_restore.txt"
  PYTHONPATH="$ROOT" python -m tools_py.parity.endpoint_route status | tee "$OUT/routing_after.txt"
}
trap restore EXIT

# The capture. mission_music_long.sh writes the run's mix-open line to endpoint_device.txt beside its dips.
bash scripts/parity/mission_music_long.sh --stage "$STAGE" --minutes "$MINUTES" --stamp "${STAMP}_wired"
rc=$?
echo "capture rc=$rc"
RUN="logs/parity/${STAMP}_wired"
log=$(ls -t logs/run_*.log 2>/dev/null | head -1)
PYTHONPATH="$ROOT" python -m tools_py.parity.endpoint_route check "$log" --expect "$DEVICE" | tee "$OUT/check.txt"
crc=${PIPESTATUS[0]}
if [ "$crc" != 0 ]; then
  echo "endpoint_ab: NOT SCORED -- the run did not render to '$DEVICE' (see $OUT/check.txt)"
  exit 5
fi

{
  echo "=== Bluetooth run ($BASELINE) ==="
  sed -n '/^DEVICE per minute:/,$p' "$BASELINE"
  echo "=== wired run ($RUN/dips.txt, $(cat "$RUN/endpoint_device.txt" 2>/dev/null)) ==="
  sed -n '/^DEVICE per minute:/,$p' "$RUN/dips.txt"
} | tee "$OUT/ab.txt"
bt=$(sed -n 's/^DEVICE total \([0-9]*\) over.*/\1/p' "$BASELINE")
wired=$(sed -n 's/^DEVICE total \([0-9]*\) over.*/\1/p' "$RUN/dips.txt")
echo "DEVICE total: Bluetooth $bt, wired ${wired:-?}" | tee -a "$OUT/ab.txt"
if [ -n "$wired" ] && [ -n "$bt" ]; then
  if [ "$wired" -le $((bt / 4)) ]; then
    echo "VERDICT: the DEVICE events belong to the Bluetooth path (wired $wired vs Bluetooth $bt)" | tee -a "$OUT/ab.txt"
  else
    echo "VERDICT: the DEVICE events survive on the wired endpoint (wired $wired vs Bluetooth $bt) -- they are ours" | tee -a "$OUT/ab.txt"
  fi
fi
echo "A/B in $OUT"
exit $rc
