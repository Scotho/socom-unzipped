#!/usr/bin/env bash
# scripts/check_quiet_gate.sh [<quiet_marker>]
#
# The read side of Sprint 5 R46/A5's launch hygiene (scripts/run_detached.sh writes the marker; this
# is what build.sh's test_step calls before its Python stage). Exits 0 (proceed) unless
# <quiet_marker> (default <repo root>/logs/.quiet) exists, is younger than QUIET_GATE_MAX_AGE_S
# (default 7200 = 2h), AND names a still-live pid -- in which case it exits 3 and prints who holds
# it. FORCE_QUIET=1 overrides unconditionally (prints that it did).
#
# QUIET_GATE_TASKLIST_CMD overrides the liveness probe for tests: run as-is (no placeholder), and
# the marker's process counts as alive iff the marker's pid text appears in that command's stdout.
# Default: `tasklist //FI "PID eq <pid>"` (the real pid already substituted in).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
marker="${1:-$ROOT/logs/.quiet}"
max_age="${QUIET_GATE_MAX_AGE_S:-7200}"

if [ "${FORCE_QUIET:-0}" = "1" ]; then
  echo "check_quiet_gate: FORCE_QUIET=1 -- proceeding regardless of $marker"
  exit 0
fi

[ -f "$marker" ] || exit 0

read -r q_owner q_pid q_epoch _ < "$marker" 2>/dev/null
if [ -z "${q_epoch:-}" ]; then
  echo "check_quiet_gate: $marker is unreadable or empty; proceeding"
  exit 0
fi

now=$(date +%s)
age=$(( now - q_epoch ))
if [ "$age" -ge "$max_age" ]; then
  echo "check_quiet_gate: $marker is $((age/60)) min old (>= $((max_age/60)) min) -- treating as stale, proceeding"
  exit 0
fi

tasklist_cmd="${QUIET_GATE_TASKLIST_CMD:-tasklist //FI \"PID eq $q_pid\"}"
out=$(eval "$tasklist_cmd" 2>/dev/null)
if printf '%s' "$out" | grep -q "$q_pid"; then
  echo "build.sh test: REFUSED -- $marker is held by '$q_owner' (pid $q_pid, $((age/60))m old): a" \
       "launch is running quiet (R46/A8: no build.sh test/unittest/sims while it exists). Set" \
       "FORCE_QUIET=1 to override."
  exit 3
fi
echo "check_quiet_gate: $marker names pid $q_pid, which is not running -- treating as stale, proceeding"
exit 0
