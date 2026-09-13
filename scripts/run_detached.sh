#!/usr/bin/env bash
# Launch a long job (a game run, a build, a gate) detached from the agent's tool call, holding the loop
# lock for exactly as long as the job's PID lives.
#
# Usage: scripts/run_detached.sh [--owner <o>] [--purpose <p>] [--log <path>] <script> <marker> [args...]
#
#   - takes the loop lock as <owner> (default "detached"); if it is BUSY, writes "exit=75 BUSY ..." to
#     <marker> and exits 75 without launching;
#   - launches `bash <script> [args...]` under nohup, stdout+stderr to <log> (default <marker>.log), and
#     returns at once, printing "DETACHED pid=... marker=... log=...";
#   - renews the heartbeat every LOOP_LOCK_DETACHED_RENEW_SEC (300) while the JOB's PID lives -- the
#     renew loop watches the job, never the caller, whose shell dies when its tool call returns;
#   - when the job exits: releases the lock, then writes "exit=<code>" to <marker> (release first, so a
#     poller that sees the marker finds the lock free);
#   - on TERM/HUP/INT it kills the job's whole Windows process tree (`taskkill /T /F`), releases, and
#     writes "exit=143";
#   - if a renew finds the lock no longer ours, it writes a "LOCK LOST" line to <log> and to
#     <marker>.LOCK_LOST, stops renewing, and lets the job finish (the final marker line then reads
#     "exit=<code> LOCK_LOST"). The job is not killed.
#
# THE JOB SCRIPT MUST KEEP ITS WORK IN THE FOREGROUND. The lock lives exactly as long as the script's
# own PID: anything it backgrounds (`cmd &`, `nohup`, `Start-Process`) and does not wait for keeps
# running after the lock is released, unrenewed and unguarded (only the busy list stands between it and
# the next build).
#
# Poll the marker (`test -f <marker>`), never the caller. Inside the script, `loop_lock.sh take/release`
# (gate.py's own included) are NESTED no-ops: LOOP_LOCK_HELD is exported to the job.
# A pre-existing <marker> is deleted before launch. Environment: as loop_lock.sh (LOOP_LOCK_PATH, ...).
HERE="$(cd "$(dirname "$0")" && pwd)"
LOCKSH="$HERE/loop_lock.sh"
RENEW_SEC="${LOOP_LOCK_DETACHED_RENEW_SEC:-300}"

if [ "$1" = "--_child" ]; then
  shift
  owner="$1" log="$2" marker="$3" script="$4"; shift 4
  bash "$script" "$@" >> "$log" 2>&1 </dev/null &
  job=$!
  finish() {
    # Release only the lock this job took (a reaped-and-retaken lock of the same owner is not ours).
    "$LOCKSH" _release_id "$LOOP_LOCK_HELD" >> "$log" 2>&1
    case $? in
      0) echo "[run_detached] RELEASED" >> "$log";;
      3) echo "[run_detached] release failed: mutex busy; the lock stays held until reaped" >> "$log";;
      *) echo "[run_detached] not released: the lock no longer carries $LOOP_LOCK_HELD" >> "$log";;
    esac
    printf 'exit=%s%s\n' "$1" "${lost:+ LOCK_LOST}" > "$marker.tmp" && mv -f "$marker.tmp" "$marker"
  }
  on_signal() {
    local winpid
    winpid=$(cat "/proc/$job/winpid" 2>/dev/null)
    if [ -n "$winpid" ] && command -v taskkill >/dev/null 2>&1; then
      taskkill //T //F //PID "$winpid" >> "$log" 2>&1
    fi
    kill "$job" 2>/dev/null; wait "$job" 2>/dev/null
    echo "[run_detached] signalled: killed the job tree (winpid ${winpid:-?})" >> "$log"
    finish 143; exit 143
  }
  trap on_signal TERM HUP INT
  last=$SECONDS lost=""
  while kill -0 "$job" 2>/dev/null; do
    sleep 1
    if [ -z "$lost" ] && [ $((SECONDS - last)) -ge "$RENEW_SEC" ]; then
      last=$SECONDS
      r=$("$LOCKSH" renew "$owner" 2>&1)
      case "$r" in "not held"*)
        lost=1
        msg="[run_detached] LOCK LOST $(date -u +%Y-%m-%dT%H:%M:%SZ): $LOOP_LOCK_HELD is no longer the live lock (lock now: $("$LOCKSH" check)); renewal stopped, the job keeps running UNGUARDED"
        echo "$msg" >> "$log"; echo "$msg" > "$marker.LOCK_LOST";;
      esac
    fi
  done
  wait "$job"; rc=$?
  finish "$rc"
  exit 0
fi

owner="detached" purpose="" log=""
while [ $# -gt 0 ]; do
  case "$1" in
    --owner) owner="$2"; shift 2;;
    --purpose) purpose="$2"; shift 2;;
    --log) log="$2"; shift 2;;
    --) shift; break;;
    -*) echo "run_detached: unknown option $1"; exit 2;;
    *) break;;
  esac
done
if [ $# -lt 2 ]; then
  echo "usage: $0 [--owner <o>] [--purpose <p>] [--log <path>] <script> <marker> [args...]"; exit 2
fi
script="$1" marker="$2"; shift 2
[ -f "$script" ] || { echo "run_detached: no such script: $script"; exit 2; }
log="${log:-$marker.log}"
rm -f "$marker" "$marker.LOCK_LOST"
mkdir -p "$(dirname "$marker")" "$(dirname "$log")"

out=$("$LOCKSH" take "$owner" --purpose "${purpose:-detached $(basename "$script")}" --print-id)
rc=$?
held_id=$(printf '%s\n' "$out" | sed -n 's/^ID: //p')
out=$(printf '%s\n' "$out" | grep -v '^ID: ')
case "$out" in
  *NESTED*)
    # The outer holder would release while this job still runs.
    printf 'exit=2 REFUSED: run_detached inside a held lock (%s)\n' "$LOOP_LOCK_HELD" > "$marker"
    echo "run_detached: REFUSED -- called inside a lock held by '$LOOP_LOCK_HELD'; the job would outlive it"
    exit 2;;
esac
if [ $rc -ne 0 ]; then
  printf 'exit=75 %s\n' "$out" > "$marker"
  echo "run_detached: $out"; exit 75
fi
export LOOP_LOCK_HELD="$held_id"
nohup bash "$0" --_child "$owner" "$log" "$marker" "$script" "$@" </dev/null >/dev/null 2>&1 &
echo "DETACHED pid=$! owner=$owner marker=$marker log=$log ($out)"
