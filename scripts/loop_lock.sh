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
#   loop_lock.sh id                              print "<owner> <take_epoch>" of the live record
#   loop_lock.sh busy                            print the busy list as this caller sees it
#
# Layout: the claim dir "$LOCK.d" holds the record "$LOCK.d/record":
#   <owner> <take_epoch> <heartbeat_epoch> <purpose...>
# A claim builds a private dir with its record and renames it onto "$LOCK.d" (`mv -T`: atomic, and
# it fails when "$LOCK.d" exists), so a claim dir never lacks its record. A pre-Sprint-5 lock -- the
# plain file "$LOCK" holding "<owner> <epoch>" (or the four-field form), no claim dir -- is still read:
# heartbeat = epoch, purpose empty.
#
# A take on a held lock:
#   - REAPS it when the heartbeat is >= LOOP_LOCK_REAP_MIN (15) minutes old AND the busy list is empty,
#     appending the reaped record to .loop_lock_history beside the lock;
#   - refuses the stale break (heartbeat >= LOOP_LOCK_STALE_MIN, 45 minutes) while anything on the
#     busy list runs;
#   - otherwise reports BUSY.
# A reap captures the full record line BEFORE judging, renames the claim dir to a unique grave, and
# goes ahead only if the grave's record is still that line; otherwise it renames the dir back and
# reports BUSY. Renew and release act only while the record still carries the caller's id, and
# release also goes through a grave rename, so a concurrent taker never sees a half-removed lock.
#
# Busy list: socom2*.exe, pcsx2-qt.exe, cmake, ninja, clang*, ld.exe / ld.lld.exe / lld*.exe,
# ps2_recomp.exe, ps2x_tests.exe, vu1_replay.exe, and any python whose command line contains
# tools_py.parity or unittest -- EXCLUDING the caller's own ancestor chain (gate.py and `python -m
# unittest` take the lock themselves and must not count as busy against themselves). The chain is
# walked by ParentProcessId from the PowerShell process in the same CIM query (MSYS PIDs are not
# Windows PIDs). A process list that cannot be read (empty) counts as busy.
# Blind: a hung job whose wrapper keeps renewing is never reaped -- .done markers and log growth are
# the progress evidence.
#
# Nesting: `run` and run_detached.sh export LOOP_LOCK_HELD="<owner> <take_epoch>". A take, renew or
# release from inside that process tree (gate.py takes the lock itself) whose LOOP_LOCK_HELD matches
# the live record succeeds without effect (NESTED) instead of BUSY; the outer holder releases. A
# LOOP_LOCK_HELD that does not match the live record is stale: renew and release refuse.
#
# Environment (tests): LOOP_LOCK_PATH (lock base path), LOOP_LOCK_PS_CMD (a shell command printing one
# "<ProcessId>|<ParentProcessId>|<Name>|<CommandLine>" line per process), LOOP_LOCK_SELF_WINPID (the
# Windows PID the ancestor walk starts from; the real query uses its own PowerShell PID),
# LOOP_LOCK_RENEW_SEC, LOOP_LOCK_WAIT_SEC (wait poll, 60), LOOP_LOCK_REAP_MIN, LOOP_LOCK_STALE_MIN.
LOCK="${LOOP_LOCK_PATH:-$(cd "$(dirname "$0")/.." && pwd)/logs/.loop_lock}"
LOCKD="$LOCK.d"
REC="$LOCKD/record"
HISTORY="$(dirname "$LOCK")/.loop_lock_history"
REAP_MIN="${LOOP_LOCK_REAP_MIN:-15}"
STALE_MIN="${LOOP_LOCK_STALE_MIN:-45}"
RENEW_SEC="${LOOP_LOCK_RENEW_SEC:-60}"
WAIT_SEC="${LOOP_LOCK_WAIT_SEC:-60}"
SELF="$0"

now() { date +%s; }
uniq_name() { echo "$1.$$.$RANDOM$RANDOM"; }
legacy() { [ ! -d "$LOCKD" ] && [ -f "$LOCK" ]; }
held() { [ -d "$LOCKD" ] || [ -f "$LOCK" ]; }

# The record line of a claim dir (arg) or of the legacy file; "NOREC <mtime>" for a claim dir without one.
line_of() {   # dir-or-empty
  local line=""
  if [ -n "$1" ]; then
    [ -f "$1/record" ] && IFS= read -r line < "$1/record"
    [ -n "$line" ] || line="NOREC $(stat -c %Y "$1" 2>/dev/null)"
  else
    [ -f "$LOCK" ] && IFS= read -r line < "$LOCK"
  fi
  printf '%s' "$line"
}
current_line() {
  if [ -d "$LOCKD" ]; then line_of "$LOCKD"; elif [ -f "$LOCK" ]; then line_of ""; fi
}

# Parse a record line into R_OWNER R_EPOCH R_HB R_PURPOSE (old two-field form: heartbeat = epoch).
parse_line() {
  R_OWNER=""; R_EPOCH=""; R_HB=""; R_PURPOSE=""
  read -r R_OWNER R_EPOCH R_HB R_PURPOSE <<< "$1"
  [ "$R_OWNER" = NOREC ] && R_OWNER=""
  case "$R_EPOCH" in ''|*[!0-9]*) R_EPOCH=$(now);; esac
  case "$R_HB" in ''|*[!0-9]*) R_HB="$R_EPOCH";; esac
}
id_of() { parse_line "$1"; echo "$R_OWNER $R_EPOCH"; }
hb_age_sec() { echo $(( $(now) - R_HB )); }
describe() {
  echo "${R_OWNER:-<no record>} taken $(( ($(now) - R_EPOCH) / 60 )) min ago, heartbeat $(( $(hb_age_sec) / 60 )) min ($(hb_age_sec) s) old${R_PURPOSE:+, purpose: $R_PURPOSE}"
}

# Replace a record file atomically (retried: on Windows a reader holding the file open can make the
# rename fail).
write_file() {   # path line
  local tmp i; tmp=$(uniq_name "$1.tmp")
  printf '%s\n' "$2" > "$tmp" 2>/dev/null || return 1
  for i in 1 2 3 4 5 6 7 8 9 10; do mv -f "$tmp" "$1" 2>/dev/null && return 0; sleep 0.2; done
  rm -f "$tmp"; return 1
}

# Rename with retries (a transient open handle on Windows fails a directory rename).
mv_retry() {   # src dst
  local i
  for i in 1 2 3 4 5; do
    mv -T "$1" "$2" 2>/dev/null && return 0
    [ -e "$1" ] || return 1
    [ -e "$2" ] && return 1
    sleep 0.1
  done
  return 1
}

# Busy-list processes (one per line, "<pid> <name>[: <cmd>]"), excluding the caller's ancestor chain.
busy_list() {
  local out self="$LOOP_LOCK_SELF_WINPID"
  if [ -n "$LOOP_LOCK_PS_CMD" ]; then
    out=$(bash -c "$LOOP_LOCK_PS_CMD" 2>/dev/null)
  else
    out=$(powershell.exe -NoProfile -NonInteractive -Command \
      '"#self|$PID"; Get-CimInstance Win32_Process | ForEach-Object { "$($_.ProcessId)|$($_.ParentProcessId)|$($_.Name)|$($_.CommandLine)" }' \
      2>/dev/null | tr -d '\r')
  fi
  if [ -z "$(printf '%s' "$out" | grep -v '^#self|' | tr -d '[:space:]')" ]; then
    echo "<process list unavailable>"; return
  fi
  printf '%s\n' "$out" | awk -v self="$self" '
    /^#self\|/ { if (self == "") self = substr($0, 7); next }
    {
      line = $0
      i = index(line, "|"); if (i == 0) next; pid = substr(line, 1, i - 1); line = substr(line, i + 1)
      i = index(line, "|"); if (i == 0) next; ppid = substr(line, 1, i - 1); line = substr(line, i + 1)
      i = index(line, "|"); if (i == 0) { nm = line; cmd = "" } else { nm = substr(line, 1, i - 1); cmd = substr(line, i + 1) }
      n++; P[n] = pid; PP[pid] = ppid; N[n] = tolower(nm); C[n] = cmd; exists[pid] = 1
    }
    END {
      cur = self; steps = 0
      while (cur != "" && (cur in exists) && !(cur in anc) && steps < 64) { anc[cur] = 1; cur = PP[cur]; steps++ }
      for (k = 1; k <= n; k++) {
        if (P[k] in anc) continue
        name = N[k]; cmd = C[k]
        if (name ~ /^socom2.*\.exe$/ || name == "pcsx2-qt.exe" || name ~ /^cmake(\.exe)?$/ || name ~ /^ninja(\.exe)?$/ ||
            name ~ /^clang/ || name ~ /^(ld|ld\.lld)(\.exe)?$/ || name ~ /^lld.*\.exe$/ || name == "ps2_recomp.exe" ||
            name == "ps2x_tests.exe" || name == "vu1_replay.exe") { print P[k] " " name; continue }
        if (name ~ /^python/ && (cmd ~ /tools_py\.parity/ || cmd ~ /unittest/)) print P[k] " " name ": " cmd
      }
    }'
}

# LOOP_LOCK_HELD matches the live record.
nested() { [ -n "$LOOP_LOCK_HELD" ] && held && [ "$LOOP_LOCK_HELD" = "$(id_of "$(current_line)")" ]; }

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

reap_log() {   # judged-line
  printf '%s REAPED "%s" heartbeat_age_s=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$(hb_age_sec)" >> "$HISTORY"
}

# Atomic claim: a private dir with the record, renamed onto $LOCKD. 0 = claimed.
claim() {   # owner purpose
  local tmp; tmp=$(uniq_name "$LOCKD.new")
  local t; t=$(now)
  mkdir "$tmp" 2>/dev/null || return 1
  if ! printf '%s %s %s %s\n' "$1" "$t" "$t" "$2" > "$tmp/record"; then rm -rf "$tmp"; return 1; fi
  if mv -T "$tmp" "$LOCKD" 2>/dev/null; then return 0; fi
  rm -rf "$tmp"; return 1
}

do_take() {   # owner purpose ; 0 = TAKEN (maybe NESTED/REAPED), 1 = BUSY
  local owner="$1" purpose="$2" judged verdict attempt grave
  if nested; then parse_line "$(current_line)"; echo "TAKEN by $owner (NESTED under $R_OWNER)"; return 0; fi
  for attempt in 1 2 3; do
    if legacy; then
      # A pre-Sprint-5 lock file with no claim dir: claim the dir first (the mutex), then judge the file.
      judged=$(line_of "")
      claim "$owner" "$purpose" || continue
      parse_line "$judged"; verdict=$(judge)
      if [ "$verdict" != REAP ] || [ "$(line_of "")" != "$judged" ]; then
        grave=$(uniq_name "$LOCKD.released"); mv_retry "$LOCKD" "$grave" && rm -rf "$grave"
        [ "$verdict" = REAP ] && verdict="BUSY: $(describe) (legacy record changed while judging)"
        echo "$verdict"; return 1
      fi
      reap_log "$judged"; rm -f "$LOCK"
      echo "TAKEN by $owner (REAPED $R_OWNER, heartbeat $(( $(hb_age_sec) / 60 )) min old)"; return 0
    fi
    if [ ! -d "$LOCKD" ]; then
      claim "$owner" "$purpose" && { echo "TAKEN by $owner"; return 0; }
      continue
    fi
    judged=$(line_of "$LOCKD")
    [ -d "$LOCKD" ] || continue            # released while we read it
    parse_line "$judged"; verdict=$(judge)
    if [ "$verdict" != REAP ]; then echo "$verdict"; return 1; fi
    # Reap: the rename is atomic, so of racing reapers only one moves the dir; the mover then checks it
    # moved the record it judged (not a claim made after the judgement) and puts the dir back if not.
    grave=$(uniq_name "$LOCKD.reaped")
    if ! mv -T "$LOCKD" "$grave" 2>/dev/null; then
      parse_line "$(current_line)"; echo "BUSY: $(describe) (lost a reap race)"; return 1
    fi
    if [ "$(line_of "$grave")" != "$judged" ]; then
      if mv_retry "$grave" "$LOCKD"; then
        parse_line "$(current_line)"; echo "BUSY: $(describe) (claimed during the reap)"; return 1
      fi
      # Could not put it back (another claim landed in the instant between): record it loudly.
      printf '%s DISPLACED "%s" by a reap race; left in %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "$(line_of "$grave")" "$grave" >> "$HISTORY"
      parse_line "$(current_line)"; echo "BUSY: $(describe) (reap race displaced a claim; see history)"; return 1
    fi
    reap_log "$judged"
    rm -rf "$grave"
    local reaped="$R_OWNER" age=$(( $(hb_age_sec) / 60 ))
    if claim "$owner" "$purpose"; then echo "TAKEN by $owner (REAPED $reaped, heartbeat $age min old)"; return 0; fi
    parse_line "$(current_line)"; echo "BUSY: $(describe) (claimed by another taker after the reap)"; return 1
  done
  parse_line "$(current_line)"; echo "BUSY: $(describe) (lock changing under us)"; return 1
}

# The id a renew/release by <owner> may act on: LOOP_LOCK_HELD when set, else "<owner> <live epoch>".
caller_matches() {   # owner line
  parse_line "$2"
  [ -n "$R_OWNER" ] || return 1
  if [ -n "$LOOP_LOCK_HELD" ]; then [ "$LOOP_LOCK_HELD" = "$R_OWNER $R_EPOCH" ]; else [ "$R_OWNER" = "$1" ]; fi
}

do_renew() {
  local owner="$1" line target
  if legacy; then line=$(line_of ""); target="$LOCK"; else line=$(line_of "$LOCKD"); target="$REC"; fi
  if held && caller_matches "$owner" "$line"; then
    # Never creates the claim dir: if it vanished since the read, the write fails and so does the renew.
    if [ "$target" = "$REC" ] && [ ! -d "$LOCKD" ]; then echo "not held by $owner"; return 1; fi
    write_file "$target" "$R_OWNER $R_EPOCH $(now) $R_PURPOSE" || { echo "renew: write failed"; return 1; }
    if [ "$R_OWNER" = "$owner" ]; then echo "RENEWED by $owner"; else echo "RENEWED by $R_OWNER (NESTED $owner)"; fi
    return 0
  fi
  echo "not held by $owner"; return 1
}

release_id() {   # "owner epoch" -- remove the lock only if its record still carries that id
  local want="$1" grave
  if legacy; then
    [ "$(id_of "$(line_of "")")" = "$want" ] && rm -f "$LOCK" && return 0
    return 1
  fi
  [ -d "$LOCKD" ] || return 1
  [ "$(id_of "$(line_of "$LOCKD")")" = "$want" ] || return 1
  grave=$(uniq_name "$LOCKD.released")
  mv_retry "$LOCKD" "$grave" || return 1
  if [ "$(id_of "$(line_of "$grave")")" != "$want" ]; then mv_retry "$grave" "$LOCKD"; return 1; fi
  rm -rf "$grave"; return 0
}

do_release() {
  local owner="$1" line
  if nested; then parse_line "$(current_line)"; echo "RELEASED $owner (NESTED: $R_OWNER keeps the lock)"; return 0; fi
  if held; then
    line=$(current_line)
    if caller_matches "$owner" "$line" && release_id "$R_OWNER $R_EPOCH"; then echo "RELEASED"; return 0; fi
    parse_line "$line"
    if [ -n "$LOOP_LOCK_HELD" ] && [ "$R_OWNER" = "$owner" ]; then
      echo "not held by $owner (stale LOOP_LOCK_HELD=\"$LOOP_LOCK_HELD\"; the live lock is $R_OWNER $R_EPOCH)"; return 1
    fi
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

valid_owner() { case "$1" in ''|-*|NOREC|*[[:space:]]*) echo "owner must be a non-empty word"; exit 2;; esac; }

do_wait() {   # owner max_minutes purpose
  local max="$2" i out
  for i in $(seq 1 "$max"); do
    if out=$(do_take "$1" "$3"); then echo "$out after $i attempt(s)"; return 0; fi
    [ "$i" -lt "$max" ] && sleep "$WAIT_SEC"
  done
  parse_line "$(current_line)"; echo "TIMEOUT waiting for lock: $(describe)"; return 1
}

case "$1" in
  take)
    valid_owner "$2"; parse_opts "${@:3}"; do_take "$2" "$PURPOSE"; exit $?;;
  renew)
    valid_owner "$2"; do_renew "$2"; exit $?;;
  release)
    valid_owner "$2"; do_release "$2"; exit $?;;
  check)
    if held; then parse_line "$(current_line)"; echo "HELD: $(describe) (reapable after $REAP_MIN min without a heartbeat and with the busy list empty)"; else echo "FREE"; fi;;
  id)
    if held; then id_of "$(current_line)"; else exit 1; fi;;
  _release_id)
    release_id "$2"; exit $?;;
  busy)
    busy_list;;
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
    held_id=$(id_of "$(current_line)")
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
      if release_id "$held_id"; then echo "[loop_lock] RELEASED"; else echo "[loop_lock] not released: the lock no longer carries $held_id"; fi
    }
    trap cleanup EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    "${REST[@]}"
    exit $?;;
  *) echo "usage: $SELF take|renew|release|check|wait|run|id|busy <owner> ..."; exit 2;;
esac
