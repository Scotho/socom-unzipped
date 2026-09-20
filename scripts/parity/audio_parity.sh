#!/usr/bin/env bash
# The audio parity check (Sprint 9 Q0, owner 2026-09-20: "an audio parity test with PCSX2 like our visual parity
# test"). One target, one capture, one score file; then `compare` against the pinned console reference.
#
#   scripts/parity/audio_parity.sh capture <pcsx2|ours> <stamp> [script.txt]   # under the loop lock: a game run
#   scripts/parity/audio_parity.sh compare <stamp> [ref.json]                  # lock-free: PASS/FAIL per step window
#
# The capture records what Windows sends to the DEFAULT output endpoint (WASAPI loopback) while drive.py plays the
# step script on the target -- so it measures the whole path to the speaker, which is what the owner hears and what
# the visual gate's audio dump never could. Reference: scripts/parity/refs/audio_<script>.pcsx2.json, pinned from a
# PCSX2 capture of the same script. Windows routes PCSX2 per app (KNOWN section 4): instance A's override silences
# it at every endpoint, so for a pcsx2 capture this script removes that override for the run and restores it after.
set -u
ROOT=/c/projects/socom_pc; cd "$ROOT"
cmd=${1:-}; shift || true
case "$cmd" in
  capture)
    target=$1; stamp=$2; script=${3:-scripts/parity/launch_to_mission_xl.txt}
    OUT="logs/parity/$stamp"; mkdir -p "$OUT"
    restore=""
    if [ "$target" = pcsx2 ]; then
      restore="$OUT/pcsx2_override_backup.txt"
      powershell -NoProfile -Command "\$b='HKCU:\Software\Microsoft\Internet Explorer\LowRegistry\Audio\PolicyConfig\PropertyStore'; Get-ChildItem \$b | ForEach-Object { \$v=(Get-ItemProperty \$_.PSPath).'(default)'; if (\$v -like '*pcsx2-qt*' -and \$v -notlike '*pcsx2_b*') { Add-Content -Path '$restore' -Value (\$_.PSChildName + '|' + \$v) -Encoding utf8; Remove-Item -Path \$_.PSPath -Recurse -Force } }" >/dev/null 2>&1
      PYTHONPATH="$ROOT" python logs/pcsx2_resize_loop.py 90 > "$OUT/resize.log" 2>&1 &
    fi
    date +%s.%N > "$OUT/.capture_started"
    # 620 s, not 480: the drive runs 600 s and PCSX2 reaches the mission HUD at ~350 s, so a 480 s recording ended
    # 130 s into the console's mission and every later reference window scored digital silence (run 8, 2026-09-20).
    python -m tools_py.parity.loopback_record "$OUT/endpoint.wav" 620 > "$OUT/loopback.log" 2>&1 &
    REC=$!
    sleep 1
    # The per-app session volume Windows remembers for the exe on this endpoint sits BEFORE the loopback tap: hold
    # the launched game at 1.0 / unmuted while it runs and log what it was (music round four, 2026-09-20).
    exe=socom2.exe; [ "$target" = pcsx2 ] && exe=pcsx2-qt.exe
    PYTHONPATH="$ROOT" python -m tools_py.parity.app_volume hold "$exe" --seconds 600 > "$OUT/app_volume.log" 2>&1 &
    VOL=$!
    date +%s.%N > "$OUT/.drive_started"
    # --seconds is OUR game's run length (drive.py defaults to 400): launch_to_mission_xl runs past 400 s, and a game
    # killed at 400 s leaves the last eleven windows as digital silence that reads as a FAIL of the mix (s9_q1_parity_ours).
    python -m tools_py.parity.drive --target "$target" --script "$script" --out "$OUT" --tail 10 --seconds 600 > "$OUT/drive.stdout" 2>&1
    rc=$?
    kill $VOL 2>/dev/null
    wait $REC
    if [ -n "$restore" ] && [ -s "$restore" ]; then
      powershell -NoProfile -Command "\$b='HKCU:\Software\Microsoft\Internet Explorer\LowRegistry\Audio\PolicyConfig\PropertyStore'; Get-Content '$restore' | ForEach-Object { \$i=\$_.IndexOf('|'); \$k=\$_.Substring(0,\$i); \$v=\$_.Substring(\$i+1); \$p=Join-Path \$b \$k; if (-not (Test-Path \$p)) { New-Item -Path \$p -Force | Out-Null }; Set-ItemProperty -Path \$p -Name '(default)' -Value \$v }" >/dev/null 2>&1
    fi
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 >/dev/null 2>&1
    powershell -NoProfile -Command 'Get-Process pcsx2-qt -ErrorAction SilentlyContinue | Stop-Process -Force' >/dev/null 2>&1
    offset=$(python -c "print(round(float(open('$OUT/.drive_started').read())-float(open('$OUT/.capture_started').read()),2))")
    rate=$(python -c "import wave; print(wave.open('$OUT/endpoint.wav').getframerate())")
    echo "target=$target script=$script drive_rc=$rc offset=${offset}s rate=$rate" > "$OUT/capture.txt"
    PYTHONPATH="$ROOT" python -m tools_py.parity.audio_parity score "$OUT/endpoint.wav" "$rate" "$OUT/drive.stdout" "$offset" "$OUT/audio_scores.json" --target "$target" --script "$(basename "$script")" > "$OUT/scores.txt" 2>&1
    echo "scored -> $OUT/audio_scores.json ($(grep -c ':' "$OUT/scores.txt") windows)"; cat "$OUT/capture.txt"
    exit $rc ;;
  compare)
    stamp=$1; ref=${2:-}
    OUT="logs/parity/$stamp"
    if [ -z "$ref" ]; then
      script=$(python -c "import json; print(json.load(open('$OUT/audio_scores.json'))['meta'].get('script','launch_to_mission_xl.txt'))")
      ref="scripts/parity/refs/audio_${script%.txt}.pcsx2.json"
    fi
    PYTHONPATH="$ROOT" python -m tools_py.parity.audio_parity compare "$ref" "$OUT/audio_scores.json" | tee "$OUT/audio_parity.txt"
    exit ${PIPESTATUS[0]} ;;
  *) sed -n '2,12p' "$0"; exit 2 ;;
esac
