#!/bin/sh
# The Claude Code SessionEnd and Stop hook (Sprint 14 G3): kill orphaned watcher processes (tail, grep, sleep,
# inotifywait whose parent shell is gone), never a shell. Wired in .claude/settings.json; the policy is
# tools_py/hooks/reap.py, tested by tools_py/tests/test_reap.py, and listed in docs/DEVELOPING.md, "Guards".
#
# Why: on 2026-09-25 the host carried 213 orphaned tail/grep watchers from dead monitors and every bash start took
# seconds (the autonomy review's note 02 section 4.5).
#
# It must NEVER block: on Stop, exit 2 would keep Claude from stopping (code.claude.com/docs/en/hooks). Every path
# here exits 0 and prints one line; the hook's stdout goes to Claude Code's debug log, not the transcript.
#
# It runs from its OWN repository (the script's directory, two up), not the caller's cwd.
cd "$(dirname "$0")/../.." 2>/dev/null || { echo "reap: skipped: no repository"; exit 0; }
. scripts/python_env.sh 2>/dev/null
if [ -z "${PYTHON:-}" ]; then
  echo "reap: skipped: no python"
  exit 0
fi
"$PYTHON" -m tools_py.hooks.reap || echo "reap: skipped: python exit $?"
exit 0
