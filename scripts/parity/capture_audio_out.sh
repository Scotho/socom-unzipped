#!/usr/bin/env bash
# Sprint 11 audio-out: one briefing capture with the callback trace on, under the machine lock, for the owner's
# quiet-endpoint measurement (docs/archive/HUMAN_TASKS-to-2026-09-25.md, "Ten quiet minutes for the music
# dropouts"; the loop took it on 2026-09-25, Sprint 13 V5 Step 1).
#
#   bash scripts/parity/capture_audio_out.sh            # ten minutes: the measurement
#   MINUTES=2 bash scripts/parity/capture_audio_out.sh  # two: the check that the capture's own records run
#
# It runs the tools and the runner of the tree it lives in (TOOLS) over the game, dist/ and logs/ of the data tree
# (SOCOM_DATA_ROOT, the main tree by default) -- an agent worktree never holds game/ (the agent-worktree skill). Tracked here, not
# under logs/: logs/ is ignored, and the worktree it used to live in disappears when this branch merges (audio-out
# fix round 2, R8). After the merge the two trees are the same one and nothing below changes.
TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MAIN="${SOCOM_DATA_ROOT:-/c/projects/socom_pc}"
export PATH="/usr/bin:/bin:/c/Windows/System32:$PATH"   # before anything that needs date/cygpath: a hidden bash has no /usr/bin
MINUTES="${MINUTES:-10}"
STAMP="audio_out_$(date -u +%Y%m%d_%H%M%S)"
LOG="$TOOLS/logs/capture_audio_out.log"
export SOCOM_DATA_ROOT="$MAIN"
export SOCOM_EXE="${SOCOM_EXE:-$TOOLS/dist/socom2.exe}"
export PS2X_DEV=1
export PS2X_AUDIO_TRACE=1
mkdir -p "$TOOLS/logs"
echo "capture start $(date -u +%FT%TZ) pid $$ stamp $STAMP minutes $MINUTES tools $TOOLS data $MAIN" >> "$LOG"
cd "$TOOLS" || exit 1
bash "$TOOLS/scripts/loop_lock.sh" run agent-audio-out --purpose "audio-out capture: briefing $MINUTES min, callback trace on" --wait 200 -- \
  bash "$TOOLS/scripts/parity/mission_music_long.sh" --stage briefing --minutes "$MINUTES" --stamp "$STAMP" >> "$LOG" 2>&1
echo "capture exit $? $(date -u +%FT%TZ)" >> "$LOG"
echo "capture done" >> "$LOG"
