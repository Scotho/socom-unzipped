#!/usr/bin/env bash
# TEMPLATE -- the Sprint 5 engagement-ladder launch on FROSTFIRE (Task 5, Amendment A). Not run by any test except its
# --dry-run. Every ladder launch is fully armed and plays up to $ROUNDS rounds on one lobby success.
#
#   scripts/parity/ladder_frostfire.sh --dry-run [out_dir]   validate args, route file, peek/trace spec; no game, no lock
#   scripts/parity/ladder_frostfire.sh [out_dir]             launch DETACHED (scripts/run_detached.sh --purpose
#                                                            launch-ladder: loop lock, logs/.quiet, 1 s CPU sampler,
#                                                            refuses below 4 GB free on C:)
#
# The detached child pins the harness (scripts/pin_harness.sh: `git archive HEAD tools_py scripts` into
# <out_dir>/harness with HARNESS_COMMIT / EXE_BUILD) and runs it with PYTHONPATH=<snapshot> PYTHONSAFEPATH=1 from the
# repo root, so a 30 min launch is scored by the reviewed code and its RESULT lines print harness=<commit> exe=<sha>.
#
# Before a launch (plan Task 5 Step 3): the local Horizon stack running (server/), persona B on game/disc/mc0_b
# (--existing-b), no socom2.exe running, `powershell -File scripts/kill_stale_drivers.ps1`, no other heavy host work.
# PS2X_SOCOM2_SERVER must be this machine's LAN address (192.168.2.10 is the owner's).
#
# Instruments: scripts/parity/online_match_frostfire.sh's (MoveScale + NetIdle at EVERY=10; the actor block, +0x420,
# +0x174, +0xF78 alive byte, +0x1044 health; CZNetGame + valves with name bytes; mission abort; the round clocks
# 0x4365c0 and 0x408f10) plus PS2X_GS_STATS=1 for rung 0's back-pressure waits (A4).
#
# Knobs (environment): ROUTE (default tools_py/parity/routes/frostfire_v2.json), ROUNDS (4), MOVER (A),
# --auto-swap always (R66: a SWAP-MOVER continues with the other mover),
# SECONDS (2400: ~4 rounds of ~6.5 min + the lobby), PS2X_GS_MAX_PENDING_FRAMES (unset; 0 is the rung-0 A/B knob).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PATH="/usr/bin:/bin:$PATH"

MODE=launch
case "${1:-}" in
  --dry-run) MODE=dry; shift ;;
  --child) MODE=child; shift ;;
esac
OUT="${1:-logs/parity/ladder_frostfire_$(date +%Y%m%d_%H%M%S)}"
NAME="$(basename "$OUT")"
ROUTE="${ROUTE:-tools_py/parity/routes/frostfire_v2.json}"
ROUNDS="${ROUNDS:-4}"
MOVER="${MOVER:-A}"
SECONDS_RUN="${SECONDS_RUN:-2400}"

export PS2X_SOCOM2_SERVER="${PS2X_SOCOM2_SERVER:-192.168.2.10}" PS2X_SOCOM2_RSA_KEY_B=b PS2X_SOCOM2_INPUT_TRACE=1 \
       PS2X_PC_SAMPLER=0.25 PS2X_CALL_TRACE_EVERY=10 PS2X_CALL_TRACE="0x553dc0:MoveScale,0x30cd80:NetIdle" \
       PS2X_GS_STATS=1 \
       PS2X_PEEK="0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,*0x437ce8+0x0c*:2,*0x437ce8+0x10*:2,*0x437ce8+0x14*:2,*0x437ce8+0x20*:2,*0x437ce8+0x24*:2,*0x437ce8+0x2c*:2,*0x437ce8+0x58*:2,*0x437ce8+0x5c*:2,*0x437ce8+0x70*:2,*0x43668c:2,0x4365c0:1,0x45a0c0:1,0x3df1b0:1,0x45a1c8:1,*0x437ce8+0x0c**:3,*0x437ce8+0x10**:3,*0x437ce8+0x14**:3,*0x437ce8+0x20**:3,*0x437ce8+0x24**:3,*0x437ce8+0x2c**:3,*0x437ce8+0x58**:3,*0x437ce8+0x5c**:3,*0x437ce8+0x70**:3,*0x43668c*:3,0x408f10:2,0x408c58:4"

ARGS=(--existing-b --hold 30 --until-kill --map frostfire --route "$ROUTE" --rounds "$ROUNDS" --mover "$MOVER"
      --auto-swap --fight-seconds 150 --kill-timeout 470 --out "$OUT" --seconds "$SECONDS_RUN")

case "$MODE" in
  dry)
    exec python -m tools_py.parity.online_match_ours --dry-run "${ARGS[@]}"
    ;;
  launch)
    mkdir -p logs/parity "$(dirname "$OUT")"
    python -m tools_py.parity.online_match_ours --dry-run "${ARGS[@]}" || exit $?
    exec bash scripts/run_detached.sh --purpose launch-ladder --log "logs/parity/detached_${NAME}.txt" \
         "$0" "logs/${NAME}.done" --child "$OUT"
    ;;
  child)
    mkdir -p "$OUT"
    harness="$(bash scripts/pin_harness.sh "$OUT" | tail -1)"
    PYTHONPATH="$harness" PYTHONSAFEPATH=1 python -m tools_py.parity.online_match_ours "${ARGS[@]}" \
      > "logs/parity/drive_${NAME}.txt" 2>&1
    rc=$?
    echo "mpexit=$rc harness=$(cat "$harness/HARNESS_COMMIT" 2>/dev/null) $(cat "$harness/EXE_BUILD" 2>/dev/null)" \
      >> "logs/parity/drive_${NAME}.txt"
    exit $rc
    ;;
esac
