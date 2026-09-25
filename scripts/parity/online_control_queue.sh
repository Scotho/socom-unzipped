#!/usr/bin/env bash
# Task 6b: control rounds on every map not yet driven online, one launch after another under the loop lock the
# caller (scripts/run_detached.sh) holds. Each map gets one attempt here; a failed map is retried once by the
# second pass; results land in logs/parity/ours_control_<slug>/ and logs/parity/drive_ours_control_<slug>.txt.
#
# Usage: scripts/parity/online_control_queue.sh [map ...]   (default: the 20 maps never driven online)
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/python_env.sh"    # $PYTHON, resolved once for every script
socom_require_python online_control_queue
cd "$ROOT"
if [ "$#" -gt 0 ]; then MAPS=("$@"); else
MAPS=("the mixer" "foxhunt" "sujo" "enowapi" "shadow falls" "fish hook" "crossroads" "sandstorm" "chain reaction"
      "guidance" "requiem" "blizzard" "abandoned" "desert glory" "night stalker" "rat's nest" "bitter jungle"
      "blood lake" "death trap" "the ruins")
fi
SUMMARY="logs/parity/online_control_summary.txt"
for pass in 1 2; do
  for m in "${MAPS[@]}"; do
    slug="$("$PYTHON" -c "import sys; from tools_py.parity import online_login_ours as L; print(L.map_slug(sys.argv[1]))" "$m")"
    out="logs/parity/ours_control_${slug}"
    if [ "$pass" = 2 ]; then
      grep -q "^${slug} .*rc=0" "$SUMMARY" 2>/dev/null && continue
      out="logs/parity/ours_control_${slug}_retry"
    fi
    start=$(date +%s)
    bash scripts/parity/online_control_round.sh "$m" "$out"
    rc=$?
    result="$(grep -o "RESULT [A-Z-]*[^\r]*" "logs/parity/drive_$(basename "$out").txt" 2>/dev/null | tail -1)"
    echo "${slug} pass=${pass} rc=${rc} $(( $(date +%s) - start ))s ${result}" >> "$SUMMARY"
    taskkill //F //IM socom2.exe >/dev/null 2>&1
    sleep 10
  done
done
exit 0
