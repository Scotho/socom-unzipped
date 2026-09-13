#!/usr/bin/env bash
# The two-instance online acceptance run on FROSTFIRE, as it first reached gameplay there
# (Sprint 4 Task 8, run `ours_task8_frost1`, 2026-09-13). Committed so a fresh clone can start from
# it: the original lived at logs/s4_task8_frost1.sh, which is git-ignored. The command and the
# environment are that run's, unchanged; only the paths are parameterised. Sprint 5 Task 1 Step 3
# starts here and REPLACES `PS2X_PEEK`, `PS2X_CALL_TRACE` and `PS2X_CALL_TRACE_EVERY` with its own
# spec -- the peek below still carries `*0x408c58+0x200:32`, which covered the RETRACTED
# `+0x204`/`+0x208` health candidates (health is `actor+0x1044`, alive byte `actor+0xF7A`,
# docs/research/19 F1).
#
# What this run established (docs/STATUS.md 2026-09-13, docs/KNOWN.md): both instances reach
# Frostfire gameplay and NEITHER player moves after round start -- the move path runs ~18 calls in
# 0.6 s and never again. It did not reach a kill.
#
# Preconditions: the local Horizon stack running (server/), persona B already on game/disc/mc0_b
# (--existing-b), no socom2.exe running, and the loop lock held by the caller (a game run needs it).
# PS2X_SOCOM2_SERVER must be this machine's LAN address, or the exe advertises 127.0.0.1 as its own
# address (docs/HANDOFF.md); 192.168.2.10 is the owner's machine -- override it elsewhere.
#
# Usage: scripts/parity/online_match_frostfire.sh [out_dir]   (default logs/parity/ours_frostfire)
#
# Map selection is VERIFIED against scripts/parity/refs/map_frostfire.png before CROSS; the mined
# corridor is Medley-only and is dropped here (the banner reads `route=direct`). Health is
# DISARMED (no --health-offset): `respawn` is a round-end signal, never a PASS.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="${1:-logs/parity/ours_frostfire}"
NAME="$(basename "$OUT")"
mkdir -p "$(dirname "$OUT")"
export PATH="/usr/bin:/bin:$PATH"
rm -f "logs/${NAME}.done"
export PS2X_SOCOM2_SERVER="${PS2X_SOCOM2_SERVER:-192.168.2.10}" PS2X_SOCOM2_RSA_KEY_B=b \
       PS2X_SOCOM2_INPUT_TRACE=1 \
       PS2X_CALL_TRACE="0x553dc0:MoveScale" PS2X_CALL_TRACE_EVERY=10 \
       PS2X_PC_SAMPLER=0.25 \
       PS2X_PEEK="0x416054:3,*0x408c58:64,*0x408c58+0x200:32,*0x408c58+0xc0*:32,0x408c58:4"
python -m tools_py.parity.online_match_ours --existing-b --hold 30 --until-kill \
       --map frostfire --engage 22 --engage-dy 10 \
       --max-steps 60 --max-walk-seconds 240 \
       --fight-seconds 200 --kill-timeout 470 \
       --out "$OUT" --seconds 1200 \
       > "logs/parity/drive_${NAME}.txt" 2>&1
rc=$?
echo "mpexit=$rc" >> "logs/parity/drive_${NAME}.txt"
echo "done $rc" > "logs/${NAME}.done"
exit $rc
