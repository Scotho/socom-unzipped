#!/usr/bin/env bash
# Serializes runtime builds and game runs between agents (one game instance; no builds during runs).
#
# NEVER HOLD THE LOCK ACROSS TOOL CALLS EXCEPT THROUGH `run` OR `scripts/run_detached.sh`.
# A gap between two tool calls is not renewed, and the calling shell dies when its tool call returns,
# so nothing here is keyed on the calling shell's PID.
#
# Usage:
#   loop_lock.sh take <owner> [--purpose <p>]   claim; BUSY (exit 1) when held -- even by the same owner
#                                                (two of "main"'s chains overlapped on 2026-09-09)
#   loop_lock.sh renew <owner>                   refresh the heartbeat of a lock <owner> holds
#   loop_lock.sh release <owner>                 exit 1 if <owner> is not the holder
#   loop_lock.sh check                           FREE, or HELD with the heartbeat age
#   loop_lock.sh wait <owner> [max_minutes] [--purpose <p>]   take, retrying every minute (default 40)
#   loop_lock.sh run <owner> [--purpose <p>] [--wait <min>] -- <cmd...>
#       take (or wait up to <min> minutes), renew the heartbeat every LOOP_LOCK_RENEW_SEC (60) from a
#       background loop while <cmd> runs, release on exit (also on failure or a signal) and return
#       <cmd>'s exit code. If the lock cannot be taken, <cmd> does not run and the exit code is 75.
#
# Record (one line in $LOCK): <owner> <take_epoch> <heartbeat_epoch> <purpose...>
# The pre-Sprint-5 two-field record "<owner> <epoch>" is still read (heartbeat = epoch, purpose empty).
# The claim is atomic: `mkdir "$LOCK.d"`. A take on a held lock:
#   - REAPS it when the heartbeat is >= LOOP_LOCK_REAP_MIN (15) minutes old AND the busy list is empty,
#     appending the reaped record to .loop_lock_history beside the lock;
#   - refuses the stale break (heartbeat >= LOOP_LOCK_STALE_MIN, 45 minutes) while anything on the
#     busy list runs;
#   - otherwise reports BUSY.
# Busy list: socom2*.exe, pcsx2-qt.exe, cmake, ninja, clang*, ld*, ps2_recomp.exe, ps2x_tests.exe,
# vu1_replay.exe, and any python whose command line contains tools_py.parity or unittest. A process
# list that cannot be read (empty) counts as busy.
# Blind: a hung job whose wrapper keeps renewing is never reaped -- .done markers and log growth are
# the progress evidence.
#
# Nesting: `run` and run_detached.sh export LOOP_LOCK_HELD="<owner> <take_epoch>". A take, renew or
# release from inside that process tree (gate.py takes the lock itself) whose LOOP_LOCK_HELD matches
# the live record succeeds without effect (NESTED) instead of BUSY; the outer holder releases.
#
# Environment (tests): LOOP_LOCK_PATH (record path), LOOP_LOCK_PS_CMD (a shell command printing one
# "<Name>|<CommandLine>" line per process), LOOP_LOCK_RENEW_SEC, LOOP_LOCK_WAIT_SEC (wait poll, 60),
# LOOP_LOCK_REAP_MIN, LOOP_LOCK_STALE_MIN.
LOCK="${LOOP_LOCK_PATH:-$(cd "$(dirname "$0")/.." && pwd)/logs/.loop_lock}"
LOCKD="$LOCK.d"
HISTORY="$(dirname "$LOCK")/.loop_lock_history"
REAP_MIN="${LOOP_LOCK_REAP_MIN:-15}"
STALE_MIN="${LOOP_LOCK_STALE_MIN:-45}"
RENEW_SEC="${LOOP_LOCK_RENEW_SEC:-60}"
WAIT_SEC="${LOOP_LOCK_WAIT_SEC:-60}"
SELF="$0"

now() { date +%s; }
held() { [ -d "$LOCKD" ] || [ -f "$LOCK" ]; }

# Parse the live record into R_OWNER R_EPOCH R_HB R_PURPOSE. A claim dir with no record (a take
# interrupted between mkdir and the write) uses the dir's mtime for both clocks.
read_record() {
  R_OWNER=""; R_EPOCH=""; R_HB=""; R_PURPOSE=""
  local line=""
  if [ -f "$LOCK" ]; then IFS= read -r line < "$LOCK"; fi
  if [ -n "$line" ]; then
    read -r R_OWNER R_EPOCH R_HB R_PURPOSE <<< "$line"
  fi
  case "$R_EPOCH" in ''|*[!0-9]*) R_EPOCH=$(stat -c %Y "$LOCKD" 2>/dev/null || stat -c %Y "$LOCK" 2>/dev/null || now);; esac
  case "$R_HB" in ''|*[!0-9]*) R_HB="$R_EPOCH";; esac
}
hb_age_sec() { echo $(( $(now) - R_HB )); }
describe() {
  echo "${R_OWNER:-<no record>} taken $(( ($(now) - R_EPOCH) / 60 )) min ago, heartbeat $(( $(hb_age_sec) / 60 )) min ($(hb_age_sec) s) old${R_PURPOSE:+, purpose: $R_PURPOSE}"
}

write_record() {   # owner epoch heartbeat purpose -- atomic replace
  # Retried: on Windows a reader holding the file open for a moment can make the rename fail.
  local tmp="$LOCK.tmp.$$.$RANDOM" i
  printf '%s %s %s %s\n' "$1" "$2" "$3" "$4" > "$tmp" || return 1
  for i in 1 2 3 4 5 6 7 8 9 10; do mv -f "$tmp" "$LOCK" 2>/dev/null && return 0; sleep 0.2; done
  rm -f "$tmp"; return 1
}

# Busy-list processes, one per line. Empty output = nothing busy.
busy_list() {
  local out
  if [ -n "$LOOP_LOCK_PS_CMD" ]; then
    out=$(bash -c "$LOOP_LOCK_PS_CMD" 2>/dev/null)
  else
    out=$(powershell.exe -NoProfile -NonInteractive -Command \
      'Get-CimInstance Win32_Process | ForEach-Object { "$($_.Name)|$($_.CommandLine)" }' 2>/dev/null | tr -d '\r')
  fi
  if [ -z "$(printf '%s' "$out" | tr -d '[:space:]')" ]; then
    echo "<process list unavailable>"; return
  fi
  printf '%s\n' "$out" | awk '
    { i = index($0, "|"); if (i == 0) { name = tolower($0); cmd = "" } else { name = tolower(substr($0, 1, i - 1)); cmd = substr($0, i + 1) } }
    name == "" { next }
    name ~ /^socom2.*\.exe$/ || name == "pcsx2-qt.exe" || name ~ /^cmake(\.exe)?$/ || name ~ /^ninja(\.exe)?$/ ||
    name ~ /^clang/ || name ~ /^ld/ || name == "ps2_recomp.exe" || name == "ps2x_tests.exe" ||
    name == "vu1_replay.exe" { print name; next }
    name ~ /^python/ && (cmd ~ /tools_py\.parity/ || cmd ~ /unittest/) { print name ": " cmd }'
}

nested() {
  [ -n "$LOOP_LOCK_HELD" ] && held || return 1
  read_record
  [ "$LOOP_LOCK_HELD" = "$R_OWNER $R_EPOCH" ]
}

judge() {   # uses R_*; prints REAP or a BUSY line
  local age=$(( $(hb_age_sec) / 60 ))
  if [ "$age" -lt "$REAP_MIN" ]; then echo "BUSY: $(describe)"; return; fi
  local busy; busy=$(busy_list)
  if [ -z "$busy" ]; then echo REAP; return; fi
  busy=$(printf '%s' "$busy" | tr '\n' ';' | sed 's/;$//')
  if [ "$age" -ge "$STALE_MIN" ]; then
    echo "BUSY: $(describe) -- stale break REFUSED, busy list running: $busy"
  else
    echo "BUSY: $(describe) -- not reaped, busy list running: $busy"
  fi
}

reap_log() {
  printf '%s REAPED "%s %s %s %s" heartbeat_age_s=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$R_OWNER" "$R_EPOCH" "$R_HB" "$R_PURPOSE" "$(hb_age_sec)" >> "$HISTORY"
}

# Identity of the lock state a reaper judged: the record's "owner epoch", or the claim dir's mtime.
state_id() {   # dir
  local line=""
  if [ -f "$LOCK" ]; then IFS= read -r line < "$LOCK"; fi
  if [ -n "$line" ]; then echo "$line" | awk '{print $1, $2}'; else echo "- $(stat -c %Y "$1" 2>/dev/null)"; fi
}

claim_fresh() {   # owner purpose extra-message
  local t; t=$(now); write_record "$1" "$t" "$t" "$2"
  echo "TAKEN by $1$3"
}

do_take() {   # owner purpose ; 0 = TAKEN (maybe NESTED/REAPED), 1 = BUSY
  local owner="$1" purpose="$2" verdict
  if nested; then echo "TAKEN by $owner (NESTED under $R_OWNER)"; return 0; fi
  if mkdir "$LOCKD" 2>/dev/null; then
    if [ -f "$LOCK" ]; then
      # A record with no claim dir (written by the pre-Sprint-5 script): judge it as a held lock.
      read_record; verdict=$(judge)
      if [ "$verdict" != REAP ]; then rmdir "$LOCKD" 2>/dev/null; echo "$verdict"; return 1; fi
      reap_log
      claim_fresh "$owner" "$purpose" " (REAPED $R_OWNER, heartbeat $(( $(hb_age_sec) / 60 )) min old)"; return 0
    fi
    claim_fresh "$owner" "$purpose" ""; return 0
  fi
  read_record; verdict=$(judge)
  if [ "$verdict" != REAP ]; then echo "$verdict"; return 1; fi
  # Reap. Renaming the claim dir is atomic, so of two racing reapers only one moves it; the winner then
  # checks it moved the state it judged (not a claim made after the judgement) and puts it back if not.
  local judged; judged=$(state_id "$LOCKD")
  local grave="$LOCKD.reaped.$$.$RANDOM"
  if ! mv "$LOCKD" "$grave" 2>/dev/null; then read_record; echo "BUSY: $(describe) (lost a reap race)"; return 1; fi
  if [ "$(state_id "$grave")" != "$judged" ]; then
    mv "$grave" "$LOCKD" 2>/dev/null; read_record; echo "BUSY: $(describe) (claimed during the reap)"; return 1
  fi
  reap_log
  rm -f "$LOCK"; rm -rf "$grave"
  if mkdir "$LOCKD" 2>/dev/null; then
    claim_fresh "$owner" "$purpose" " (REAPED $R_OWNER, heartbeat $(( $(hb_age_sec) / 60 )) min old)"; return 0
  fi
  read_record; echo "BUSY: $(describe) (claimed by another taker after the reap)"; return 1
}

do_renew() {
  local owner="$1"
  if nested && [ "$R_OWNER" != "$owner" ]; then
    write_record "$R_OWNER" "$R_EPOCH" "$(now)" "$R_PURPOSE" || { echo "renew: write failed"; return 1; }; echo "RENEWED by $R_OWNER (NESTED $owner)"; return 0
  fi
  if held; then
    read_record
    if [ "$R_OWNER" = "$owner" ] && { [ -z "$LOOP_LOCK_HELD" ] || [ "$LOOP_LOCK_HELD" = "$R_OWNER $R_EPOCH" ]; }; then
      mkdir -p "$LOCKD" 2>/dev/null
      write_record "$R_OWNER" "$R_EPOCH" "$(now)" "$R_PURPOSE" || { echo "renew: write failed"; return 1; }; echo "RENEWED by $owner"; return 0
    fi
  fi
  echo "not held by $owner"; return 1
}

do_release() {
  local owner="$1"
  if nested; then echo "RELEASED $owner (NESTED: $R_OWNER keeps the lock)"; return 0; fi
  if held; then
    read_record
    if [ "$R_OWNER" = "$owner" ]; then rm -f "$LOCK"; rm -rf "$LOCKD"; echo "RELEASED"; return 0; fi
  fi
  echo "not held by $owner"; return 1
}

parse_opts() {   # sets PURPOSE, WAITMIN, REST (the args after --)
  PURPOSE=""; WAITMIN=""; REST=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --purpose) PURPOSE="$2"; shift 2;;
      --wait) WAITMIN="$2"; shift 2;;
      --) shift; REST=("$@"); return 0;;
      *) REST=("$@"); return 0;;
    esac
  done
}

valid_owner() { case "$1" in ''|-*|*[[:space:]]*) echo "owner must be a non-empty word"; exit 2;; esac; }

do_wait() {   # owner max_minutes purpose
  local max="$2" i out
  for i in $(seq 1 "$max"); do
    if out=$(do_take "$1" "$3"); then echo "$out after $i attempt(s)"; return 0; fi
    [ "$i" -lt "$max" ] && sleep "$WAIT_SEC"
  done
  read_record; echo "TIMEOUT waiting for lock: $(describe)"; return 1
}

case "$1" in
  take)
    valid_owner "$2"; parse_opts "${@:3}"; do_take "$2" "$PURPOSE"; exit $?;;
  renew)
    valid_owner "$2"; do_renew "$2"; exit $?;;
  release)
    valid_owner "$2"; do_release "$2"; exit $?;;
  check)
    if held; then read_record; echo "HELD: $(describe) (reapable after $REAP_MIN min without a heartbeat and with the busy list empty)"; else echo "FREE"; fi;;
  wait)
    valid_owner "$2"
    case "$3" in ''|-*) max=40; parse_opts "${@:3}";; *) max="$3"; parse_opts "${@:4}";; esac
    do_wait "$2" "$max" "$PURPOSE"; exit $?;;
  run)
    owner="$2"; valid_owner "$owner"; parse_opts "${@:3}"
    if [ ${#REST[@]} -eq 0 ]; then echo "usage: $SELF run <owner> [--purpose <p>] [--wait <min>] -- <cmd...>"; exit 2; fi
    if [ -n "$WAITMIN" ]; then out=$(do_wait "$owner" "$WAITMIN" "$PURPOSE"); rc=$?
    else out=$(do_take "$owner" "$PURPOSE"); rc=$?; fi
    echo "[loop_lock] $out"
    [ $rc -eq 0 ] || exit 75
    case "$out" in *NESTED*) exec "${REST[@]}";; esac
    read_record
    held_id="$R_OWNER $R_EPOCH"
    export LOOP_LOCK_HELD="$held_id"
    main_pid=$$
    # The renewer is tied to this wrapper's PID (not the agent's shell): if the wrapper dies, renewal
    # stops, and the busy list then keeps a still-running job from being reaped.
    (
      trap 'exit 0' TERM
      last=$SECONDS   # wall clock (a bash builtin, no fork), not a count of 1 s sleeps
      while kill -0 "$main_pid" 2>/dev/null; do
        sleep 1
        if [ $((SECONDS - last)) -ge "$RENEW_SEC" ]; then
          last=$SECONDS
          # Stop only when the lock is no longer ours; a transient write failure retries next interval.
          case "$("$SELF" renew "$owner" 2>&1)" in "not held"*) exit 0;; esac
        fi
      done
    ) </dev/null >/dev/null 2>&1 &
    renewer=$!
    cleanup() {
      kill "$renewer" 2>/dev/null; wait "$renewer" 2>/dev/null
      if held; then
        read_record
        if [ "$R_OWNER $R_EPOCH" = "$held_id" ]; then
          LOOP_LOCK_HELD="" do_release "$owner" | sed 's/^/[loop_lock] /'
        fi
      fi
    }
    trap cleanup EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    "${REST[@]}"
    exit $?;;
  *) echo "usage: $SELF take|renew|release|check|wait|run <owner> ..."; exit 2;;
esac
