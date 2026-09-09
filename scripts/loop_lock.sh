#!/usr/bin/env bash
# Serializes runtime builds and game runs between agents (only one game instance; no builds during runs).
# Usage: scripts/loop_lock.sh take <owner> | release <owner> | check | wait <owner> [max_minutes]
LOCK="$(cd "$(dirname "$0")/.." && pwd)/logs/.loop_lock"
STALE_MIN=45
age_min() { echo $(( ( $(date +%s) - $(cut -d' ' -f2 "$LOCK") ) / 60 )); }
case "$1" in
  take)
    # A held, non-stale lock is BUSY for everyone, including its own owner (a second job of the
    # same owner must queue behind the first: two of "main"'s chains overlapped on 2026-09-09).
    if [ -f "$LOCK" ] && [ "$(age_min)" -lt $STALE_MIN ]; then
      echo "BUSY: $(cat "$LOCK") (age $(age_min) min)"; exit 1; fi
    echo "$2 $(date +%s)" > "$LOCK"; echo "TAKEN by $2";;
  renew)
    # Refresh the timestamp of a lock this owner holds (long jobs; keeps it from going stale).
    if [ -f "$LOCK" ] && [ "$(cut -d' ' -f1 "$LOCK")" = "$2" ]; then echo "$2 $(date +%s)" > "$LOCK"; echo "RENEWED by $2"; else echo "not held by $2"; exit 1; fi;;
  release) [ -f "$LOCK" ] && [ "$(cut -d' ' -f1 "$LOCK")" = "$2" ] && rm -f "$LOCK" && echo "RELEASED" || echo "not held by $2";;
  check) if [ -f "$LOCK" ]; then echo "HELD: $(cat "$LOCK") (age $(age_min) min, stale after $STALE_MIN)"; else echo "FREE"; fi;;
  wait)
    max=${3:-40}; for i in $(seq 1 $max); do
      if "$0" take "$2" >/dev/null 2>&1; then echo "TAKEN by $2 after $i min"; exit 0; fi; sleep 60; done
    echo "TIMEOUT waiting for lock: $(cat "$LOCK")"; exit 1;;
  *) echo "usage: $0 take|renew|release|check|wait <owner>"; exit 2;;
esac
