#!/usr/bin/env bash
# Sprint 10 Goal 1 -- "it stays up": one scheduled run of the engagement ladder against the hosted server.
#
#   scripts/ladder_job.sh [rounds]        # default 4
#
# Meant to be fired by a scheduler in windows the owner is away (they name the machine and the windows --
# docs/HUMAN_TASKS.md; the Task Scheduler entry is created DISABLED). It refuses to run when the machine is not
# quiet (scripts/check_quiet_gate.sh), when the loop lock is held, or when a game is already running -- a run that
# lags the owner while they are at the machine is a defect in the scheduling (the spec's stop rule). Launches the
# ladder PINNED and DETACHED exactly as scripts/parity/ladder_frostfire.sh does, waits for its done marker, then
# appends the record to logs/ladder/ledger.jsonl and re-renders docs/LADDER.md. Never against a server that is
# not ours: SOCOM_SERVER_IP is the project's hosted box, fixed here.
set -u
ROOT=/c/projects/socom_pc; cd "$ROOT" || exit 1
export PATH="/usr/bin:/mingw64/bin:/c/Users/Utilisateur/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
ROUNDS="${1:-4}"
export SOCOM_SERVER_IP=3.143.65.100
export ROUNDS
mkdir -p logs/ladder
log="logs/ladder/job_$(date +%Y%m%d_%H%M%S).log"
exec >> "$log" 2>&1
echo "ladder_job: $(date -u +%FT%TZ) rounds=$ROUNDS server=$SOCOM_SERVER_IP"
if ! bash scripts/check_quiet_gate.sh; then echo "ladder_job: not quiet -- skipped"; exit 75; fi
if ! bash scripts/loop_lock.sh check | grep -q "^FREE"; then echo "ladder_job: lock held -- skipped"; exit 75; fi
if powershell -NoProfile -Command '(Get-Process socom2,pcsx2-qt -ErrorAction SilentlyContinue | Measure-Object).Count' 2>/dev/null | grep -qv '^0'; then
  echo "ladder_job: a game is running -- skipped"; exit 75
fi
if [ "$(df -BG --output=avail /c | tail -1 | tr -d ' G')" -lt 6 ]; then echo "ladder_job: under 6 GB free -- skipped"; exit 75; fi
stamp="ladder_$(date +%Y%m%d_%H%M%S)"
out="logs/parity/$stamp"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1 >/dev/null 2>&1
bash scripts/parity/ladder_frostfire.sh "$out"
rc=$?
# The ladder writes its done marker at logs/<stamp>.done (ladder_frostfire.sh's last act), not beside the run
# directory under logs/parity/ -- the first scheduled run waited its whole hour on the wrong path.
done_marker="logs/$stamp.done"
echo "ladder_job: launch rc=$rc; waiting for $done_marker"
deadline=$(( $(date +%s) + 3600 ))
while [ ! -f "$done_marker" ] && [ "$(date +%s)" -lt "$deadline" ]; do sleep 30; done
if [ -f "$done_marker" ]; then cat "$done_marker"; else echo "ladder_job: no done marker after an hour"; fi
python -m tools_py.parity.ladder_ledger add "$out" "$SOCOM_SERVER_IP"
echo "ladder_job: done $(date -u +%FT%TZ)"
