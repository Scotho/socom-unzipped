#!/usr/bin/env bash
# W7 (fix wave A, 2026-09-22): the mission-music instrument. The owner, on tonight's playthrough: "one song
# playing with stutters or skips ... it is not playing linearly ... fine the first while, gets much worse as I
# proceed", and: "You may have to write tests that skip the cutscenes and move faster to catch these issues."
#
# So: reach gameplay by the fast path (scripts/parity/mission_music_fast.txt -- the cinematics skipped, the
# flyover pressed through until the HUD band matches), then HOLD IN THE MISSION for as long as the run asks,
# with the audio captured twice over -- the mixer's own pre-device WAV (PS2X_AUDIO_DUMP) and the WASAPI
# loopback of what Windows actually sends the speaker -- and score the capture minute by minute so the
# degradation the owner describes is a column of numbers rather than an impression.
#
#   scripts/parity/mission_music_long.sh [--minutes N] [--target ours|pcsx2] [--stamp S] [--no-score] [--dry-run]
#
# --dry-run generates the drive script and prints the lengths, launching nothing: it is how the script itself is
# checked without the loop lock (and how tools_py/tests/test_mission_music_fast.py checks the generated hold).
#
# Run it under the loop lock (it launches a game):
#   scripts/loop_lock.sh run <owner> --purpose "W7 mission music" -- scripts/parity/mission_music_long.sh --minutes 12
#
# --minutes is the IN-MISSION hold (default 12: the owner's "fine the first while, gets much worse as I
# proceed" needs the capture to contain both halves, and W7's bar is at least ten minutes of mission). The hold
# is built by copying mission_music_fast.txt and appending `wait+8.0:NONE` lines to it, so the generated script
# is committed nowhere and is written beside the capture it produced (logs/parity/<stamp>/drive_script.txt) --
# the schedule is an argument, the path is the file.
#
# The capture itself is scripts/parity/audio_parity.sh's, unchanged apart from its new length arguments: the
# loopback recorder, the per-app volume hold (Windows remembers a per-exe session volume that sits BEFORE the
# loopback tap) and drive.py, sequenced as the audio parity runs already sequence them. AUDIO_DUMP is passed
# through to the launched game as PS2X_AUDIO_DUMP, with PS2X_DEV=1 beside it: that knob is Dev-class (R238
# weighed reclassing it Shipping and did not), and a Dev knob needs developer mode to be honoured at all.
#
# Scoring (W7 reuses, it does not invent):
#   * tools_py/parity/audio_envelope.py --segment 60 is the primary read. It is REFERENCE-FREE and its four
#     measurements are the owner's four words: envelope (the loudness curve), oscillation_score ("louder and
#     quieter"), splices ("jumping between tracks" / "not playing linearly") and silences (a stream underrun
#     heard as a skip). One line per minute plus a totals line means "fine at first, much worse later" is read
#     straight off the per-segment column -- which is the thing W7 has to show and which no ours-vs-console
#     score can show, because both machines are scored within one capture over time here.
#   * tools_py/parity/audio_dips.py is the follow-up when the envelope finds dips: it aligns the endpoint
#     recording to the mixer's dump and classifies each dip DEVICE / STARVATION / COMMAND / UNEXPLAINED
#     against the game log, which is what says whether a skip was lost after render() or starved before it.
#   * tools_py/parity/audio_parity.py is deliberately NOT the scorer here: it scores step-aligned windows
#     against a PCSX2 reference pinned per script (scripts/parity/refs/audio_<script>.pcsx2.json), and no such
#     reference exists for this script -- pinning one costs a console run of the same length, and it would
#     still compare ours to the console rather than the capture's start to its end. `audio_parity.sh capture`
#     writes its audio_scores.json anyway as a by-product; it is evidence, not the verdict.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

MINUTES=12
TARGET=ours
STAMP=""
SCORE=1
DRY=0
BASE=scripts/parity/mission_music_fast.txt
while [ $# -gt 0 ]; do
  case "$1" in
    --minutes) MINUTES=$2; shift 2 ;;
    --target) TARGET=$2; shift 2 ;;
    --stamp) STAMP=$2; shift 2 ;;
    --script) BASE=$2; shift 2 ;;
    --no-score) SCORE=0; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,45p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; sed -n '2,45p' "$0"; exit 2 ;;
  esac
done
case "$TARGET" in ours|pcsx2) ;; *) echo "--target must be ours or pcsx2" >&2; exit 2 ;; esac
[ -f "$BASE" ] || { echo "no such script: $BASE" >&2; exit 2; }
[ -n "$STAMP" ] || STAMP="mission_music_${TARGET}_$(date +%Y%m%d_%H%M%S)"
OUT="logs/parity/$STAMP"
mkdir -p "$OUT"

HOLD_S=$((MINUTES * 60))
# The base script already ends with one `wait+8.0:NONE`; the rest of the hold is appended here. Eight seconds is
# the hold step every mission script in this directory uses, and a `wait` step is a plain sleep in drive.py (no
# settle poll, one capture at its end), so 8 s of hold costs one PNG rather than eight.
EXTRA=$(( (HOLD_S - 8 + 7) / 8 ))
[ "$EXTRA" -lt 0 ] && EXTRA=0
# An `ifpopup+1.0:CROSS` every POPUP_EVERY hold steps, for the reason music_only_mission.txt interleaves them: an
# in-game HELP pop-up PAUSES the game behind a lit HUD (needs_cross, s5_head_1x / s6_depth_m2). One that arrives at
# minute two and is never answered makes the remaining ten minutes a capture of a paused game -- which would read as
# exactly the degradation W7 is looking for and be an artefact of the harness. An ifpopup over live gameplay costs
# ~2.5 s (wait_stable's 2 s cap, then no press) and takes nothing away from the capture.
POPUP_EVERY=8
SCRIPT="$OUT/drive_script.txt"
cp "$BASE" "$SCRIPT"
POPUPS=0
{
  echo "# --- $EXTRA hold steps appended by mission_music_long.sh for a ${MINUTES}-minute in-mission capture,"
  echo "# --- with an ifpopup guard every $POPUP_EVERY of them ---"
  i=0
  while [ "$i" -lt "$EXTRA" ]; do
    echo "wait+8.0:NONE"
    i=$((i + 1))
    if [ $((i % POPUP_EVERY)) -eq 0 ] && [ "$i" -lt "$EXTRA" ]; then
      echo "ifpopup+1.0:CROSS"
      POPUPS=$((POPUPS + 1))
    fi
  done
} >> "$SCRIPT"

# The boot allowance is what the run may spend BEFORE the hold. Measured on our exe (logs/parity/s9_q1_parity_ours,
# launch_to_mission_xl): the DEPLOY press lands at t=87 s and the mission is up by ~137 s; the fast path's untilref
# then presses through the flyover. 240 s leaves that better than a 70% margin. PCSX2 reaches the mission HUD at
# ~350 s on the same script (audio_parity.sh's own note), so the console needs 480.
BOOT_S=240
[ "$TARGET" = pcsx2 ] && BOOT_S=480
# drive.py's --seconds is the game's own run length (run.sh's timeout): the boot, the hold, the --tail 10 the
# capture passes, and 50 s of slack. A game killed mid-hold leaves the rest of the capture as digital silence,
# which reads as a catastrophic FAIL of the mix rather than as a short run (s9_q1_parity_ours).
DRIVE_S=$((BOOT_S + HOLD_S + POPUPS * 3 + 60))
REC_S=$((DRIVE_S + 20))
DUMP="$OUT/mix.wav"
# PS2X_AUDIO_DUMP is read by a NATIVE Windows binary through python and run.sh, and an MSYS "/c/..." path
# does not survive that as an environment variable the way a command-line argument does (the MSYS path
# conversion applies to arguments, MEMORY "MSYS converts /c/ args"). Hand it the native spelling where
# there is one; on Linux cygpath does not exist and the POSIX path is already right.
DUMP_ENV="$ROOT/$DUMP"
if command -v cygpath >/dev/null 2>&1; then DUMP_ENV="$(cygpath -w "$ROOT/$DUMP")"; fi

echo "stamp=$STAMP target=$TARGET minutes=$MINUTES hold=${HOLD_S}s steps=+$EXTRA popups=$POPUPS drive=${DRIVE_S}s record=${REC_S}s"
echo "script=$SCRIPT dump=$DUMP env=$DUMP_ENV"
if [ "$DRY" = 1 ]; then
  echo "--dry-run: nothing launched. $(grep -c '^wait+8.0:NONE' "$SCRIPT") hold steps, $(grep -cv '^[[:space:]]*\(#.*\)\?$' "$SCRIPT") steps in all."
  exit 0
fi
AUDIO_DUMP="$DUMP_ENV" scripts/parity/audio_parity.sh capture "$TARGET" "$STAMP" "$SCRIPT" "$DRIVE_S" "$REC_S"
rc=$?
echo "capture rc=$rc"

# The proof that the hold really was in the mission, not on a cinematic: the fast path's untilref line.
grep -E "^untilref\(|^ifpopup:" "$OUT/drive.stdout" 2>/dev/null || echo "(no untilref/ifpopup line in $OUT/drive.stdout)"

if [ "$SCORE" = 1 ]; then
  for wav in "$OUT/mix.wav" "$OUT/endpoint.wav"; do
    [ -s "$wav" ] || { echo "no capture at $wav -- skipping its score"; continue; }
    name=$(basename "$wav" .wav)
    echo "=== audio_envelope --segment 60  $wav ==="
    PYTHONPATH="$ROOT" python -m tools_py.parity.audio_envelope "$wav" --segment 60 \
      > "$OUT/envelope_$name.txt" 2>&1 || true
    cat "$OUT/envelope_$name.txt"
  done
  if [ -s "$OUT/endpoint.wav" ] && [ -s "$OUT/mix.wav" ]; then
    echo "=== audio_dips  endpoint vs mix ==="
    log=$(ls -t logs/run_*.log 2>/dev/null | head -1)
    PYTHONPATH="$ROOT" python -m tools_py.parity.audio_dips "$OUT/endpoint.wav" --dump "$OUT/mix.wav" \
      ${log:+--log "$log"} > "$OUT/dips.txt" 2>&1 || true
    tail -40 "$OUT/dips.txt"
  fi
fi
echo "capture and scores in $OUT"
exit $rc
