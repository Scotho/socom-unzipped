#!/usr/bin/env bash
# LEGACY converge path, superseded by scripts/parity/ladder_frostfire.sh (Sprint 5 Amendment A: pinned harness,
# --endgame route, --rounds, run_detached.sh). The acceptance PASS (ladder launch 2, research/22) came from the ladder
# template, not from this script, which is kept for its history and its instrument list (the ladder template reuses
# that list); prefer ladder_frostfire.sh for any new launch.
#
# The two-instance online acceptance run on FROSTFIRE. First committed as the run that first reached
# gameplay there (Sprint 4 Task 8, run `ours_task8_frost1`, 2026-09-13); its instruments were REPLACED in
# Sprint 5 Task 2's fix round 1 with the launch-2 instrument spec (logs/s5_t1_launch2.sh, Sprint 5 Task 1)
# minus that launch's heavy ground-probe traces, dumps, grid peeks and RDRAM dumps. Kept: MoveScale and
# NetIdle traced at EVERY=10 (the move-path and starvation watches refuse without them), the actor block,
# the mover, the snap-back pair (+0x420 in *0x408c58+0x400:12), +0x174, the alive byte (+0xF7A inside
# *0x408c58+0xF78:24) and health (*0x408c58+0x1044:8), CZNetGame and its valves with their name bytes, the
# mission-abort valve, the round clock (0x4365c0 and the string at 0x408f10), and 0x408c58:4.
#
# What frost1 established (docs/STATUS.md 2026-09-13, docs/KNOWN.md): both instances reach Frostfire
# gameplay and neither player moves after round start. Task 1's launches 1-2 traced why (research/21, 23).
#
# Preconditions: the local Horizon stack running (server/), persona B already on game/disc/mc0_b
# (--existing-b), no socom2.exe running, stale drivers killed (scripts/kill_stale_drivers.ps1) and the
# loop lock held by the caller (scripts/run_detached.sh). SOCOM_SERVER_IP (scripts/parity/env.sh) must be
# this machine's LAN address, or the exe advertises 127.0.0.1 as its own address (docs/HANDOFF.md);
# 192.168.2.10 is the owner's machine -- override SOCOM_SERVER_IP elsewhere.
#
# Usage: scripts/parity/online_match_frostfire.sh [out_dir]   (default logs/parity/ours_frostfire)
#
# Map selection is VERIFIED against scripts/parity/refs/map_frostfire.png before CROSS; the mined
# corridor is Medley-only and is dropped here (the banner reads `route=direct`). Health is ARMED by the
# harness defaults (--health-offset 0x1044, --alive-offset 0xF7A, e685b82): PASS needs a health
# transition, `round`/`respawn` end rounds and are never a PASS. research/22: the <= 0 half of the health
# readout HAS now been read live -- ladder launch 2 (logs/run_[AB]_20260913_230442, rounds 1-3: +0x1044
# 1.0 -> 0.298 -> 0.0 on the victim), through ladder_frostfire.sh, not this script.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
. "$(dirname "$0")/env.sh"
socom_require_python online_match_frostfire
OUT="${1:-logs/parity/ours_frostfire}"
NAME="$(basename "$OUT")"
mkdir -p "$(dirname "$OUT")"
export PATH="/usr/bin:/bin:$PATH"
rm -f "logs/${NAME}.done"
# Instruments come from scripts/parity/env.sh (sourced above); the B-side key is this script's own.
export PS2X_SOCOM2_RSA_KEY_B=b
"$PYTHON" -m tools_py.parity.online_match_ours --existing-b --hold 30 --until-kill \
       --map frostfire --engage 22 --engage-dy 10 \
       --max-steps 60 --max-walk-seconds 240 \
       --fight-seconds 200 --kill-timeout 470 \
       --out "$OUT" --seconds 1200 \
       > "logs/parity/drive_${NAME}.txt" 2>&1
rc=$?
echo "mpexit=$rc" >> "logs/parity/drive_${NAME}.txt"
echo "done $rc" > "logs/${NAME}.done"
exit $rc
