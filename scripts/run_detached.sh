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
#     poller that sees the marker finds the lock free).
#
# Poll the marker (`test -f <marker>`), never the caller. Inside the script, `loop_lock.sh take/release`
# (gate.py's own included) are NESTED no-ops: LOOP_LOCK_HELD is exported to the job.
# A pre-existing <marker> is deleted before launch. Environment: as loop_lock.sh (LOOP_LOCK_PATH, ...).
HERE="$(cd "$(dirname "$0")" && pwd)"
LOCKSH="$HERE/loop_lock.sh"
RENEW_SEC="${LOOP_LOCK_DETACHED_RENEW_SEC:-300}"
LOCKFILE="${LOOP_LOCK_PATH:-$(cd "$HERE/.." && pwd)/logs/.loop_lock}"

if [ "$1" = "--_child" ]; then
  shift
  owner="$1" log="$2" marker="$3" script="$4"; shift 4
  bash "$script" "$@" >> "$log" 2>&1 </dev/null &
  job=$!
  finish() {
    local rc="$1"
    # Release only the lock this job took (a reaped-and-retaken lock of the same owner name is not ours).
    local cur; cur=$(awk '{print $1, $2}' "$LOCKFILE" 2>/dev/null)
    if [ "$cur" = "$LOOP_LOCK_HELD" ]; then LOOP_LOCK_HELD="" "$LOCKSH" release "$owner" >> "$log" 2>&1; fi
    printf 'exit=%s\n' "$rc" > "$marker.tmp" && mv -f "$marker.tmp" "$marker"
  }
  trap 'kill "$job" 2>/dev/null; wait "$job" 2>/dev/null; finish 143; exit 143' TERM HUP INT
  last=$SECONDS
  while kill -0 "$job" 2>/dev/null; do
    sleep 1
    if [ $((SECONDS - last)) -ge "$RENEW_SEC" ]; then last=$SECONDS; "$LOCKSH" renew "$owner" >/dev/null 2>&1; fi
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
rm -f "$marker"
mkdir -p "$(dirname "$marker")" "$(dirname "$log")"

out=$("$LOCKSH" take "$owner" --purpose "${purpose:-detached $(basename "$script")}")
rc=$?
case "$out" in
  *NESTED*)
    # The outer holder would release while this job still runs.
    "$LOCKSH" release "$owner" >/dev/null 2>&1
    printf 'exit=2 REFUSED: run_detached inside a held lock (%s)\n' "$LOOP_LOCK_HELD" > "$marker"
    echo "run_detached: REFUSED -- called inside a lock held by '$LOOP_LOCK_HELD'; the job would outlive it"
    exit 2;;
esac
if [ $rc -ne 0 ]; then
  printf 'exit=75 %s\n' "$out" > "$marker"
  echo "run_detached: $out"; exit 75
fi
LOOP_LOCK_HELD="$(awk '{print $1, $2}' "$LOCKFILE")"
export LOOP_LOCK_HELD
nohup bash "$0" --_child "$owner" "$log" "$marker" "$script" "$@" </dev/null >/dev/null 2>&1 &
echo "DETACHED pid=$! owner=$owner marker=$marker log=$log ($out)"
