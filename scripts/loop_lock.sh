#!/usr/bin/env bash
# Serializes runtime builds and game runs between agents (one game instance; no builds during runs).
#
# NEVER HOLD THE LOCK ACROSS TOOL CALLS EXCEPT THROUGH `run` OR `scripts/run_detached.sh`.
# A gap between two tool calls is not renewed, and the calling shell dies when its tool call returns,
# so nothing here is keyed on the calling shell's PID.
#
# Usage:
#   loop_lock.sh take <owner> [--purpose <p>] [--print-id]   claim; BUSY (exit 1) when held -- even by
#                                                the same owner (two of "main"'s chains overlapped 2026-09-09)
#   loop_lock.sh renew <owner>                   refresh the heartbeat of a lock <owner> holds
#   loop_lock.sh release <owner>                 exit 1 if <owner> is not the holder
#   loop_lock.sh check                           FREE, or HELD with the heartbeat age
#   loop_lock.sh wait <owner> [max_minutes] [--purpose <p>]   take, retrying every minute (default 40)
#   loop_lock.sh run <owner> [--purpose <p>] [--wait <min>] -- <cmd...>
#       take (or wait up to <min> minutes), renew the heartbeat every LOOP_LOCK_RENEW_SEC (60) from a
#       background loop while <cmd> runs, release on exit (also on failure or a signal) and return
#       <cmd>'s exit code. If the lock cannot be taken, <cmd> does not run and the exit code is 75.
#       If a renew finds the lock no longer ours, it prints "LOCK LOST" to stderr and stops renewing
#       (the command is not killed).
#   loop_lock.sh id                              print "<owner> <take_id>" of the live record
#   loop_lock.sh busy                            print the busy list as this caller sees it
#
# Layout: the claim dir "$LOCK.d" holds the record "$LOCK.d/record":
#   <owner> <take_id> <heartbeat_epoch> <purpose...>      take_id = <epoch>-<pid>x<random>
# The take_id is unique per claim, so "<owner> <take_id>" names one holding of the lock. A pre-Sprint-5
# lock -- the plain file "$LOCK" holding "<owner> <epoch>", no claim dir -- is still read (heartbeat =
# epoch, purpose empty).
#
# Every state transition (claim, reap, renew, release) runs under a short mutex, `mkdir "$LOCK.mx"`
# holding a token file t.<epoch>.<pid>.<rand>: acquire (bounded LOOP_LOCK_MUTEX_WAIT_SEC, 10 s; release
# waits LOOP_LOCK_RELEASE_WAIT_SEC, 45 s), re-read the record, decide, act, release. A mutex whose token
# NAME is older than LOOP_LOCK_MUTEX_STALE_SEC (30 s) is broken (one breaker at a time, via
# "$LOCK.mx.break"), with a history line; the holder re-checks its token before every destructive step
# and aborts if it was broken while it stalled. Readers (check, id, the first read of a take) take no mutex: the claim dir is renamed
# into place already holding its record and renamed away whole, so a reader sees a whole lock or none.
#
# A take on a held lock judges it OUTSIDE the mutex (the process list costs 1-2 s):
#   - REAP when the heartbeat is >= LOOP_LOCK_REAP_MIN (15) minutes old AND the busy list is empty;
#     then, under the mutex, the record is re-read and deleted only if it is still the line that was
#     judged (otherwise BUSY naming the new holder, or TAKEN if it has meanwhile become free); the reaped
#     record is appended to .loop_lock_history beside the lock;
#   - the stale break (heartbeat >= LOOP_LOCK_STALE_MIN, 45 minutes) is refused while anything on the
#     busy list runs;
#   - otherwise BUSY.
# Renew and release by <owner> fix the target holding ("<owner> <take_id>", or LOOP_LOCK_HELD when set)
# at their first read and act under the mutex only if the record still carries exactly that id.
#
# Busy list: socom2*.exe, pcsx2-qt.exe, cmake, ninja, clang*, ld.exe / ld.lld.exe / lld*.exe,
# ps2_recomp.exe, ps2x_tests.exe, vu1_replay.exe, and any python whose command line contains
# tools_py.parity or unittest -- EXCLUDING the caller's own ancestor chain (gate.py and `python -m
# unittest` take the lock themselves and must not count as busy against themselves). The chain is
# walked by ParentProcessId from the PowerShell process in the same CIM query (MSYS PIDs are not
# Windows PIDs), stopping at a parent created after its child (a reused PID). A process list that
# cannot be read (empty) counts as busy.
# Blind: a hung job whose wrapper keeps renewing is never reaped -- .done markers and log growth are
# the progress evidence.
#
# Nesting: `run` and run_detached.sh export LOOP_LOCK_HELD="<owner> <take_id>". A take, renew or
# release from inside that process tree (gate.py takes the lock itself) whose LOOP_LOCK_HELD matches
# the live record succeeds without effect (NESTED) instead of BUSY; the outer holder releases. A
# LOOP_LOCK_HELD that does not match the live record is stale: renew and release refuse.
#
# Environment (tests): LOOP_LOCK_PATH (lock base path), LOOP_LOCK_PS_CMD (a shell command printing one
# "<ProcessId>|<ParentProcessId>|<CreationStamp>|<Name>|<CommandLine>" line per process; the stamp is a
# sortable number or empty), LOOP_LOCK_SELF_WINPID (the Windows PID the ancestor walk starts from),
# LOOP_LOCK_RENEW_SEC, LOOP_LOCK_WAIT_SEC (wait poll, 60), LOOP_LOCK_REAP_MIN, LOOP_LOCK_STALE_MIN,
# LOOP_LOCK_MUTEX_WAIT_SEC, LOOP_LOCK_MUTEX_STALE_SEC, and LOOP_LOCK_TEST_PAUSE_AT=<point>[,...] with
# LOOP_LOCK_TEST_PAUSE_DIR: at a named point the script touches <dir>/<point>.paused and waits for
# <dir>/<point>.go (points: reap_before_mutex, reap_inside_mutex, renew_before_mutex, renew_inside_mutex,
# release_before_mutex); LOOP_LOCK_TEST_CS_DIR (critical-section overlap detector), LOOP_LOCK_TEST_CS_HOLD,
# LOOP_LOCK_RELEASE_WAIT_SEC.
LOCK="${LOOP_LOCK_PATH:-$(cd "$(dirname "$0")/.." && pwd)/logs/.loop_lock}"
LOCKD="$LOCK.d"
REC="$LOCKD/record"
MX="$LOCK.mx"
HISTORY="$(dirname "$LOCK")/.loop_lock_history"
REAP_MIN="${LOOP_LOCK_REAP_MIN:-15}"
STALE_MIN="${LOOP_LOCK_STALE_MIN:-45}"
RENEW_SEC="${LOOP_LOCK_RENEW_SEC:-60}"
WAIT_SEC="${LOOP_LOCK_WAIT_SEC:-60}"
MX_WAIT_SEC="${LOOP_LOCK_MUTEX_WAIT_SEC:-10}"
MX_STALE_SEC="${LOOP_LOCK_MUTEX_STALE_SEC:-30}"
SELF="$0"

now() { printf '%(%s)T\n' -1; }
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
uniq_name() { echo "$1.$$.$RANDOM$RANDOM"; }
held() { [ -d "$LOCKD" ] || [ -f "$LOCK" ]; }

test_pause() {   # point
  case ",${LOOP_LOCK_TEST_PAUSE_AT}," in *",$1,"*) ;; *) return 0;; esac
  local d="${LOOP_LOCK_TEST_PAUSE_DIR:?}" i
  : > "$d/$1.paused"
  for i in $(seq 1 1200); do [ -f "$d/$1.go" ] && return 0; sleep 0.1; done
}

# ---- the mutex -------------------------------------------------------------------------------------
# $MX is a dir holding one token file t.<epoch>.<pid>.<rand>. mkdir is the exclusive step (rm and rmdir
# of one path are NOT exclusive on MSYS; neither is a rename). Staleness is judged from the epoch in the
# token's NAME, and a breaker deletes exactly that path, so it never judges one object and deletes
# another. Breaking is itself serialised by a second mkdir, "$MX.break". A token-less dir (a crash
# between mkdir and the token write) is broken only after two stale readings ~1 s apart. The holder
# re-checks its token (mx_mine) immediately before every destructive step and aborts if it is gone.
MX_TOKEN=""
mx_log() { printf '%s %s\n' "$(stamp)" "$*" >> "$HISTORY"; }
mx_token_epoch() {   # token-name -> its epoch (older token names without one: the file's mtime)
  local e="${1#t.}"; e="${e%%.*}"
  case "$e" in ''|*[!0-9]*) stat -c %Y "$MX/$1" 2>/dev/null; return;; esac
  if [ "${#e}" -ge 9 ]; then echo "$e"; else stat -c %Y "$MX/$1" 2>/dev/null; fi
}
mx_stale() { [ -n "$1" ] && [ $(( $(now) - $1 )) -gt "$MX_STALE_SEC" ]; }

mx_try_break() {   # token-name-or-empty, as judged stale by the caller
  local tok="$1" cur e m1 m2 bm
  if ! mkdir "$MX.break" 2>/dev/null; then
    bm=$(stat -c %Y "$MX.break" 2>/dev/null)
    if mx_stale "$bm" && rmdir "$MX.break" 2>/dev/null; then mx_log "MUTEX-BREAK-LOCK-BROKEN (mtime $(( $(now) - bm )) s old)"; fi
    return
  fi
  cur=$(ls -A "$MX" 2>/dev/null | grep -v '^\.' | head -n 1)
  if [ -n "$tok" ]; then
    if [ "$cur" = "$tok" ]; then
      e=$(mx_token_epoch "$tok")
      if mx_stale "$e" && rm "$MX/$tok" 2>/dev/null; then
        rmdir "$MX" 2>/dev/null
        mx_log "MUTEX-BROKEN $tok (token $(( $(now) - e )) s old)"
      fi
    fi
  elif [ -d "$MX" ] && [ -z "$cur" ]; then
    m1=$(stat -c %Y "$MX" 2>/dev/null)
    if mx_stale "$m1"; then
      sleep 1
      cur=$(ls -A "$MX" 2>/dev/null | head -n 1); m2=$(stat -c %Y "$MX" 2>/dev/null)
      if [ -z "$cur" ] && [ "$m1" = "$m2" ] && mx_stale "$m2" && rmdir "$MX" 2>/dev/null; then
        mx_log "MUTEX-BROKEN <no token> (dir $(( $(now) - m2 )) s old, two readings)"
      fi
    fi
  fi
  rmdir "$MX.break" 2>/dev/null
}

mx_acquire() {   # [wait_seconds]
  local deadline=$(( $(now) + ${1:-$MX_WAIT_SEC} )) tok e m
  while :; do
    if mkdir "$MX" 2>/dev/null; then
      MX_TOKEN="$MX/t.$(now).$$.$RANDOM$RANDOM"
      if { : > "$MX_TOKEN"; } 2>/dev/null; then
        test_cs_enter
        return 0
      fi
      MX_TOKEN=""                                # our dir vanished under a breaker: start again
    else
      tok=$(ls -A "$MX" 2>/dev/null | head -n 1)
      if [ -n "$tok" ]; then
        e=$(mx_token_epoch "$tok")
        mx_stale "$e" && mx_try_break "$tok"
      elif [ -d "$MX" ]; then
        m=$(stat -c %Y "$MX" 2>/dev/null)
        mx_stale "$m" && mx_try_break ""
      fi
    fi
    [ "$(now)" -ge "$deadline" ] && return 1
    sleep 0.05
  done
}
mx_mine() { [ -n "$MX_TOKEN" ] && [ -f "$MX_TOKEN" ]; }
mx_release() {
  test_cs_leave
  if mx_mine; then rm -f "$MX_TOKEN"; rmdir "$MX" 2>/dev/null; fi
  MX_TOKEN=""
}

# Test hook: LOOP_LOCK_TEST_CS_DIR=<dir> records critical-section entries; a second process inside at the
# same time appends to <dir>/double.log.
test_cs_enter() {
  [ -n "$LOOP_LOCK_TEST_CS_DIR" ] || return 0
  local d="$LOOP_LOCK_TEST_CS_DIR" others
  others=$(ls "$d" 2>/dev/null | grep '^cs\.' | grep -v "^cs\.$$\$")
  [ -n "$others" ] && echo "$$ entered while inside: $others" >> "$d/double.log"
  : > "$d/cs.$$"
  sleep "${LOOP_LOCK_TEST_CS_HOLD:-0.3}"
}
test_cs_leave() {
  [ -n "$LOOP_LOCK_TEST_CS_DIR" ] && [ -n "$MX_TOKEN" ] || return 0
  rm -f "$LOOP_LOCK_TEST_CS_DIR/cs.$$"
}

# ---- records ---------------------------------------------------------------------------------------
# The record line of a claim dir (arg) or of the legacy file; "NOREC <mtime>" for a claim dir without one.
# A missing or unreadable record is re-read a few times first: on Windows a reader can catch the instant
# of a record replace.
line_of() {   # dir-or-empty
  local line="" i
  if [ -n "$1" ]; then
    for i in 1 2 3 4 5; do
      [ -f "$1/record" ] && IFS= read -r line < "$1/record" 2>/dev/null
      [ -n "$line" ] && break
      [ -d "$1" ] || break
      sleep 0.05
    done
    [ -n "$line" ] || line="NOREC $(stat -c %Y "$1" 2>/dev/null)"
  else
    [ -f "$LOCK" ] && IFS= read -r line < "$LOCK" 2>/dev/null
  fi
  printf '%s' "$line"
}
current_line() {   # empty = free
  local line
  if [ -d "$LOCKD" ]; then
    line=$(line_of "$LOCKD")
    # A record-less read of a dir that has since been renamed away is a release in flight: free.
    case "$line" in NOREC*) [ -d "$LOCKD" ] || { [ -f "$LOCK" ] && line_of ""; return; };; esac
    printf '%s' "$line"
  elif [ -f "$LOCK" ]; then line_of ""; fi
}

# Parse a record line into R_OWNER R_EPOCH (the take id) R_T (its seconds) R_HB R_PURPOSE.
parse_line() {
  R_OWNER=""; R_EPOCH=""; R_HB=""; R_PURPOSE=""
  read -r R_OWNER R_EPOCH R_HB R_PURPOSE <<< "$1"
  [ "$R_OWNER" = NOREC ] && R_OWNER=""
  R_T="${R_EPOCH%%-*}"
  case "$R_T" in ''|*[!0-9]*) R_T=$(now); R_EPOCH="$R_T";; esac
  case "$R_HB" in ''|*[!0-9]*) R_HB="$R_T";; esac
}
id_of() { parse_line "$1"; echo "$R_OWNER $R_EPOCH"; }
hb_age_sec() { echo $(( $(now) - R_HB )); }
describe() {
  echo "${R_OWNER:-<no record>} taken $(( ($(now) - R_T) / 60 )) min ago, heartbeat $(( $(hb_age_sec) / 60 )) min ($(hb_age_sec) s) old${R_PURPOSE:+, purpose: $R_PURPOSE}"
}

# Under the mutex: replace a record file atomically. 0 ok, 1 write failed, 2 the mutex is no longer ours.
write_file() {   # path line
  local tmp i; tmp=$(uniq_name "$1.tmp")
  mx_mine || return 2
  { printf '%s\n' "$2" > "$tmp"; } 2>/dev/null || return 1
  for i in 1 2 3 4 5 6 7 8 9 10; do
    mx_mine || { rm -f "$tmp" 2>/dev/null; return 2; }
    mv -f "$tmp" "$1" 2>/dev/null && return 0
    sleep 0.2
  done
  rm -f "$tmp" 2>/dev/null; return 1
}

# Under the mutex: build a private dir with the record and rename it into place. Sets TAKEN_ID.
claim() {   # owner purpose
  local tmp t id i; tmp=$(uniq_name "$LOCKD.new"); t=$(now); id="$t-$$x$RANDOM$RANDOM"
  mkdir "$tmp" 2>/dev/null || return 1
  if ! { printf '%s %s %s %s\n' "$1" "$id" "$t" "$2" > "$tmp/record"; } 2>/dev/null; then rm -rf "$tmp"; return 1; fi
  for i in 1 2 3 4 5; do
    mx_mine || break
    if mv -T "$tmp" "$LOCKD" 2>/dev/null; then TAKEN_ID="$1 $id"; return 0; fi
    [ -e "$LOCKD" ] && break
    sleep 0.1
  done
  rm -rf "$tmp"; return 1
}

# Under the mutex: remove the live lock (legacy file or claim dir) whole. 1 = failed or mutex lost.
remove_lock() {
  local grave i
  if [ -d "$LOCKD" ]; then
    grave=$(uniq_name "$LOCKD.released")
    for i in 1 2 3 4 5 6 7 8 9 10; do
      mx_mine || return 1
      mv -T "$LOCKD" "$grave" 2>/dev/null && break
      sleep 0.2
    done
    [ -d "$LOCKD" ] && return 1
    rm -rf "$grave"
  fi
  if [ -f "$LOCK" ]; then mx_mine || return 1; rm -f "$LOCK"; fi
  return 0
}

# Graves of the pre-mutex version (a stranded *.reaped.* / *.released.* / *.new.* dir) older than 1 h.
clean_old_graves() {
  find "$(dirname "$LOCK")" -maxdepth 1 -type d -name "$(basename "$LOCK").d.*" -mmin +60 \
    -exec rm -rf {} + 2>/dev/null
}

# ---- the busy list ---------------------------------------------------------------------------------
# Busy-list processes (one per line, "<pid> <name>[: <cmd>]"), excluding the caller's ancestor chain.
busy_list() {
  local out self="$LOOP_LOCK_SELF_WINPID"
  if [ -n "$LOOP_LOCK_PS_CMD" ]; then
    out=$(bash -c "$LOOP_LOCK_PS_CMD" 2>/dev/null)
  else
    out=$(powershell.exe -NoProfile -NonInteractive -Command \
      '"#self|$PID"; Get-CimInstance Win32_Process | ForEach-Object { $c = ""; if ($_.CreationDate) { $c = $_.CreationDate.ToUniversalTime().ToString("yyyyMMddHHmmssffffff") }; "$($_.ProcessId)|$($_.ParentProcessId)|$c|$($_.Name)|$($_.CommandLine)" }' \
      2>/dev/null | tr -d '\r')
  fi
  if [ -z "$(printf '%s' "$out" | grep -v '^#self|' | tr -d '[:space:]')" ]; then
    echo "<process list unavailable>"; return
  fi
  printf '%s\n' "$out" | awk -v self="$self" '
    function field() { i = index(line, "|"); if (i == 0) { f = line; line = ""; return f } f = substr(line, 1, i - 1); line = substr(line, i + 1); return f }
    /^#self\|/ { if (self == "") self = substr($0, 7); next }
    {
      line = $0
      if (index(line, "|") == 0) next
      pid = field(); ppid = field(); cr = field(); nm = field(); cmd = line
      n++; P[n] = pid; PP[pid] = ppid; CR[pid] = cr; N[n] = tolower(nm); C[n] = cmd; exists[pid] = 1
    }
    END {
      cur = self; steps = 0
      while (cur != "" && (cur in exists) && !(cur in anc) && steps < 64) {
        anc[cur] = 1; par = PP[cur]; steps++
        # A parent created after its child is a reused PID, not the parent: stop the walk there.
        if ((par in CR) && CR[par] != "" && CR[cur] != "" && CR[par] > CR[cur]) break
        cur = par
      }
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

# LOOP_LOCK_HELD matches the live record (re-read once on a miss: a reader can catch a record replace).
nested() {
  [ -n "$LOOP_LOCK_HELD" ] && held || return 1
  [ "$LOOP_LOCK_HELD" = "$(id_of "$(current_line)")" ] && return 0
  sleep 0.2
  held && [ "$LOOP_LOCK_HELD" = "$(id_of "$(current_line)")" ]
}

# ---- verbs -----------------------------------------------------------------------------------------
TAKEN_ID=""
MX_BUSY_MSG='BUSY: the lock mutex stayed held (see "check")'
do_take() {   # owner purpose ; 0 = TAKEN (maybe NESTED/REAPED), 1 = BUSY
  local owner="$1" purpose="$2" line line2 verdict attempt reaped age
  if nested; then TAKEN_ID="$LOOP_LOCK_HELD"; parse_line "$(current_line)"; echo "TAKEN by $owner (NESTED under $R_OWNER)"; return 0; fi
  clean_old_graves
  for attempt in 1 2 3 4 5; do
    line=$(current_line)
    if [ -z "$line" ]; then
      mx_acquire || { echo "$MX_BUSY_MSG"; return 1; }
      if [ -z "$(current_line)" ] && claim "$owner" "$purpose"; then mx_release; echo "TAKEN by $owner"; return 0; fi
      if ! mx_mine; then mx_release; echo "BUSY: the lock mutex was broken while claiming"; return 1; fi
      mx_release; continue                      # someone claimed first: re-read and judge them
    fi
    parse_line "$line"; verdict=$(judge)       # outside the mutex: the process list is slow
    if [ "$verdict" != REAP ]; then echo "$verdict"; return 1; fi
    test_pause reap_before_mutex
    mx_acquire || { echo "$MX_BUSY_MSG"; return 1; }
    line2=$(current_line)
    if [ "$line2" = "$line" ]; then
      parse_line "$line"; reaped="$R_OWNER"; age=$(( $(hb_age_sec) / 60 ))
      test_pause reap_inside_mutex
      if remove_lock; then
        printf '%s REAPED "%s" heartbeat_age_s=%s\n' "$(stamp)" "$line" "$(hb_age_sec)" >> "$HISTORY"
        if claim "$owner" "$purpose"; then
          mx_release; echo "TAKEN by $owner (REAPED $reaped, heartbeat $age min old)"; return 0
        fi
      fi
      if ! mx_mine; then
        mx_release; parse_line "$(current_line)"
        echo "BUSY: $(describe) (the lock mutex was broken while this reap stalled; nothing more done)"; return 1
      fi
      mx_release; parse_line "$(current_line)"; echo "BUSY: $(describe) (reap could not complete)"; return 1
    fi
    mx_release
    [ -z "$line2" ] && continue                 # became free while we judged: take it
    parse_line "$line2"; echo "BUSY: $(describe) (the judged holder changed while judging)"; return 1
  done
  parse_line "$(current_line)"; echo "BUSY: $(describe) (lock changing under us)"; return 1
}

# The holding a renew/release by <owner> targets, fixed at its first read: LOOP_LOCK_HELD when set,
# else "<owner> <take_id>" of the live record if <owner> holds it. Empty = not held.
target_id() {   # owner
  local line; line=$(current_line)
  [ -n "$line" ] || return 0
  parse_line "$line"
  [ -n "$R_OWNER" ] || return 0
  if [ -n "$LOOP_LOCK_HELD" ]; then
    [ "$LOOP_LOCK_HELD" = "$R_OWNER $R_EPOCH" ] && echo "$LOOP_LOCK_HELD"
  elif [ "$R_OWNER" = "$1" ]; then
    echo "$R_OWNER $R_EPOCH"
  fi
}
# The same, but a miss is confirmed under the mutex before it counts (no "not held" from a torn read).
target_id_confirmed() {   # owner
  local want; want=$(target_id "$1")
  if [ -z "$want" ] && mx_acquire; then want=$(target_id "$1"); mx_release; fi
  echo "$want"
}

do_renew() {
  local owner="$1" want line rc
  want=$(target_id_confirmed "$owner")
  [ -n "$want" ] || { echo "not held by $owner"; return 1; }
  test_pause renew_before_mutex
  mx_acquire || { echo "renew: the lock mutex stayed held; not renewed this time"; return 1; }
  line=$(current_line)
  if [ -z "$line" ] || [ "$(id_of "$line")" != "$want" ]; then mx_release; echo "not held by $owner"; return 1; fi
  parse_line "$line"
  test_pause renew_inside_mutex
  local target="$REC"; [ -d "$LOCKD" ] || target="$LOCK"
  write_file "$target" "$R_OWNER $R_EPOCH $(now) $R_PURPOSE"; rc=$?
  mx_release
  case $rc in
    0) ;;
    2) echo "renew aborted: the lock mutex was broken while this renew stalled; nothing written"; return 1;;
    *) echo "renew: write failed"; return 1;;
  esac
  if [ "$R_OWNER" = "$owner" ]; then echo "RENEWED by $owner"; else echo "RENEWED by $R_OWNER (NESTED $owner)"; fi
  return 0
}

# Remove the lock only if its record still carries that id. 0 released, 1 not that holding (or the mutex
# was broken mid-release), 3 the mutex could not be had. Waits past the mutex stale threshold.
release_id() {   # "owner take_id"
  local want="$1" line
  mx_acquire "${LOOP_LOCK_RELEASE_WAIT_SEC:-45}" || return 3
  line=$(current_line)
  if [ -z "$line" ] || [ "$(id_of "$line")" != "$want" ]; then mx_release; return 1; fi
  remove_lock; local rc=$?
  mx_release; return $rc
}

do_release() {
  local owner="$1" want rc
  if nested; then parse_line "$(current_line)"; echo "RELEASED $owner (NESTED: $R_OWNER keeps the lock)"; return 0; fi
  if [ -n "$LOOP_LOCK_HELD" ] && held; then
    parse_line "$(current_line)"
    if [ "$R_OWNER" = "$owner" ]; then
      echo "not held by $owner (stale LOOP_LOCK_HELD=\"$LOOP_LOCK_HELD\"; the live lock is $R_OWNER $R_EPOCH)"; return 1
    fi
  fi
  want=$(target_id_confirmed "$owner")
  [ -n "$want" ] || { echo "not held by $owner"; return 1; }
  test_pause release_before_mutex
  release_id "$want"; rc=$?
  case $rc in
    0) echo "RELEASED"; return 0;;
    3) echo "release failed: mutex busy; the lock stays held until reaped"; return 1;;
    *) echo "not held by $owner"; return 1;;
  esac
}

parse_opts() {   # sets PURPOSE, WAITMIN, PRINT_ID, REST (the args after --)
  PURPOSE=""; WAITMIN=""; PRINT_ID=""; REST=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --purpose) PURPOSE="$2"; shift 2;;
      --wait) WAITMIN="$2"; shift 2;;
      --print-id) PRINT_ID=1; shift;;
      --) shift; REST=("$@"); return 0;;
      *) REST=("$@"); return 0;;
    esac
  done
}

valid_owner() { case "$1" in ''|-*|NOREC|*[[:space:]]*) echo "owner must be a non-empty word"; exit 2;; esac; }

do_wait() {   # owner max_minutes purpose  (sets TAKEN_ID)
  local max="$2" i out rc
  for i in $(seq 1 "$max"); do
    out=$(do_take "$1" "$3"; rc=$?; echo "@@ID $TAKEN_ID"; exit $rc); rc=$?
    TAKEN_ID=$(printf '%s\n' "$out" | sed -n 's/^@@ID //p')
    out=$(printf '%s\n' "$out" | grep -v '^@@ID ')
    if [ $rc -eq 0 ]; then echo "$out after $i attempt(s)"; return 0; fi
    [ "$i" -lt "$max" ] && sleep "$WAIT_SEC"
  done
  parse_line "$(current_line)"; echo "TIMEOUT waiting for lock: $(describe)"; return 1
}

case "$1" in
  take)
    valid_owner "$2"; parse_opts "${@:3}"; do_take "$2" "$PURPOSE"; rc=$?
    [ $rc -eq 0 ] && [ -n "$PRINT_ID" ] && echo "ID: $TAKEN_ID"
    exit $rc;;
  renew)
    valid_owner "$2"; do_renew "$2"; exit $?;;
  release)
    valid_owner "$2"; do_release "$2"; exit $?;;
  check)
    line=$(current_line)
    if [ -n "$line" ]; then parse_line "$line"; echo "HELD: $(describe) (reapable after $REAP_MIN min without a heartbeat and with the busy list empty)"; else echo "FREE"; fi;;
  id)
    line=$(current_line)
    if [ -n "$line" ]; then id_of "$line"; else exit 1; fi;;
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
    if [ -n "$WAITMIN" ]; then
      out=$(do_wait "$owner" "$WAITMIN" "$PURPOSE"; rc=$?; echo "@@ID $TAKEN_ID"; exit $rc); rc=$?
    else
      out=$(do_take "$owner" "$PURPOSE"; rc=$?; echo "@@ID $TAKEN_ID"; exit $rc); rc=$?
    fi
    held_id=$(printf '%s\n' "$out" | sed -n 's/^@@ID //p')
    echo "[loop_lock] $(printf '%s\n' "$out" | grep -v '^@@ID ')"
    [ $rc -eq 0 ] || exit 75
    case "$out" in *NESTED*) exec "${REST[@]}";; esac
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
          # A transient failure (mutex busy, write failed) retries next interval; "not held" is final.
          r=$("$SELF" renew "$owner" 2>&1)
          case "$r" in "not held"*)
            echo "[loop_lock] LOCK LOST: $held_id is no longer the live lock (lock now: $("$SELF" check)); renewal stopped, the command keeps running UNGUARDED" >&2
            exit 0;;
          esac
        fi
      done
    ) </dev/null >/dev/null &
    renewer=$!
    cleanup() {
      kill "$renewer" 2>/dev/null; wait "$renewer" 2>/dev/null
      release_id "$held_id"
      case $? in
        0) echo "[loop_lock] RELEASED";;
        3) echo "[loop_lock] release failed: mutex busy; the lock stays held until reaped";;
        *) echo "[loop_lock] not released: the lock no longer carries $held_id";;
      esac
    }
    trap cleanup EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    "${REST[@]}"
    exit $?;;
  *) echo "usage: $SELF take|renew|release|check|wait|run|id|busy <owner> ..."; exit 2;;
esac
