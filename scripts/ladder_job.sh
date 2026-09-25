#!/usr/bin/env bash
# Sprint 10 Goal 1 -- "it stays up": one scheduled run of the engagement ladder against the hosted server.
#
#   scripts/ladder_job.sh [rounds]        # default 4
#
# Meant to be fired by a scheduler in windows the owner is away (they name the machine and the windows --
# docs/HUMAN_TASKS.md; the Task Scheduler entry is created DISABLED). It refuses to run when the machine is not
# quiet (scripts/check_quiet_gate.sh) or when a game is already running -- a run that lags the owner while they are
# at the machine is a defect in the scheduling (the spec's stop rule). Launches the ladder PINNED and DETACHED
# exactly as scripts/parity/ladder_frostfire.sh does, waits for its done marker, then appends the record to
# logs/ladder/ledger.jsonl and re-renders docs/LADDER.md. Never against a server that is not ours: SOCOM_SERVER_IP
# is the project's hosted box, fixed here.
#
# THE LOCK (Sprint 13 H2, issue #37): the job never checks the lock and then takes it -- an agent build took that
# gap four times in a row on 2026-09-23. The acquisition is the test: ladder_frostfire.sh's run_detached.sh call
# comes back through this script (RUN_DETACHED_SH, role "detach" below), which adds `--wait LADDER_LOCK_WAIT_MIN`
# (default 60) so the launch QUEUES for the lock (a ticket, served in arrival order) instead of exiting 75, and
# makes the detached job this script again (role "--_in_lock"), so scripts/kill_stale_drivers.ps1 runs only while
# the ladder HOLDS the lock -- run before the wait, it would kill the drivers of whatever job holds it.
#
# The tree is the script's own (audit H14): a scheduled run executes the checkout the scheduler points at, with
# that checkout's harness -- not whatever the main tree has checked out.
#
# Knobs (tests): LADDER_LOCK_WAIT_MIN (60), LADDER_POLL_SEC (30, the done-marker poll), LADDER_GAME_COUNT_CMD (a
# shell command printing how many games run; default the Get-Process query), and loop_lock.sh's / run_detached.sh's
# own environment (LOOP_LOCK_PATH, RUN_QUIET_MARKER, RUN_FREE_GB_CMD, ...).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT" || exit 1

if [ "${1:-}" = "--_in_lock" ]; then
  # Role 3, run_detached's job: the lock is held. Clear stale drivers, then become the ladder's child.
  shift
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 >/dev/null 2>&1
  exec bash "$@"
fi

if [ "${LADDER_JOB_ROLE:-}" = detach ]; then
  # Role 2, called by ladder_frostfire.sh as its RUN_DETACHED_SH:
  #   [--owner o] [--purpose p] [--log l] [--quiet] <script> <marker> [args...]
  unset LADDER_JOB_ROLE RUN_DETACHED_SH
  opts=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --owner|--purpose|--log) opts+=("$1" "$2"); shift 2;;
      --quiet) opts+=("$1"); shift;;
      --) shift; break;;
      *) break;;
    esac
  done
  script="$1" marker="$2"; shift 2
  exec bash "$ROOT/scripts/run_detached.sh" --wait "${LADDER_LOCK_WAIT_MIN:-60}" "${opts[@]}" \
       "$ROOT/scripts/ladder_job.sh" "$marker" --_in_lock "$script" "$@"
fi

. "$ROOT/scripts/python_env.sh"   # $PYTHON, resolved once for every script
socom_require_python ladder_job
export PATH="/usr/bin:/mingw64/bin:$HOME/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
ROUNDS="${1:-4}"
export SOCOM_SERVER_IP=3.143.65.100
export ROUNDS
mkdir -p logs/ladder
log="logs/ladder/job_$(date +%Y%m%d_%H%M%S).log"
exec >> "$log" 2>&1
echo "ladder_job: $(date -u +%FT%TZ) rounds=$ROUNDS server=$SOCOM_SERVER_IP tree=$ROOT"
if ! bash scripts/check_quiet_gate.sh; then echo "ladder_job: not quiet -- skipped"; exit 75; fi
games=$(eval "${LADDER_GAME_COUNT_CMD:-powershell -NoProfile -Command '(Get-Process socom2,pcsx2-qt -ErrorAction SilentlyContinue | Measure-Object).Count'}" 2>/dev/null | tr -d '\r')
if printf '%s\n' "$games" | grep -v '^[[:space:]]*$' | grep -qv '^0$'; then echo "ladder_job: a game is running -- skipped"; exit 75; fi
if [ "$(df -BG --output=avail /c | tail -1 | tr -d ' G')" -lt 6 ]; then echo "ladder_job: under 6 GB free -- skipped"; exit 75; fi
stamp="ladder_$(date +%Y%m%d_%H%M%S)"
out="logs/parity/$stamp"
RUN_DETACHED_SH="$ROOT/scripts/ladder_job.sh" LADDER_JOB_ROLE=detach bash scripts/parity/ladder_frostfire.sh "$out"
rc=$?
# The ladder writes its done marker at logs/<stamp>.done (ladder_frostfire.sh's last act), not beside the run
# directory under logs/parity/ -- the first scheduled run waited its whole hour on the wrong path.
done_marker="logs/$stamp.done"
if [ "$rc" -eq 0 ]; then
  echo "ladder_job: launch rc=$rc; waiting for $done_marker"
  deadline=$(( $(date +%s) + 3600 ))
  while [ ! -f "$done_marker" ] && [ "$(date +%s)" -lt "$deadline" ]; do sleep "${LADDER_POLL_SEC:-30}"; done
  if [ -f "$done_marker" ]; then cat "$done_marker"; else echo "ladder_job: no done marker after an hour"; fi
else
  echo "ladder_job: launch rc=$rc -- not launched (75: the lock was not had within ${LADDER_LOCK_WAIT_MIN:-60} min); no done marker to wait for"
fi
"$PYTHON" -m tools_py.parity.ladder_ledger add "$out" "$SOCOM_SERVER_IP"
echo "ladder_job: done $(date -u +%FT%TZ)"
