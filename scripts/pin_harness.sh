#!/usr/bin/env bash
# scripts/pin_harness.sh <out_dir> [<sha>]
#
# Snapshots tools_py/ and scripts/ at <sha> (default HEAD) into <out_dir>/harness/, so a launch that
# runs for tens of minutes is scored by the harness code that was reviewed for it, not by whatever
# another agent lands in the live tree while it runs (Sprint 5 R46/A5; R49's "no build.sh test or
# unittest suites while a launch's logs/.quiet marker exists", written by run_detached.sh, is the
# write side of the same guarantee -- this is the read side).
#
# Writes:
#   <out_dir>/harness/HARNESS_COMMIT  -- the resolved sha (40 hex chars), one line
#   <out_dir>/harness/EXE_BUILD       -- "path=<...> mtime=<UTC ISO8601> sha256=<...>" for dist/socom2.exe
#                                        (build.sh's own cp destination), so a launch's report can show
#                                        the runtime binary did not change under a long run.
#
# HOW A LAUNCH SCRIPT USES THE PINNED COPY
# -----------------------------------------
# `online_match_ours.py` and `drive.py` ("must be run from the repo root", gate.py's own header)
# resolve every game/log/dist path as cwd-relative ("logs/parity/...", "dist/socom2.exe",
# "game/disc", the default --out) with no repo-root constant to override, so the harness process's
# cwd MUST stay the real repo root for those paths to hit the real game and log trees. That rules
# out `cd`-ing into the snapshot to pick up the pinned code.
#
# The other way to point at pinned code -- leave cwd at the repo root and put the snapshot on
# PYTHONPATH -- does NOT work unaided: `python -m`/`-c` always prepends the CURRENT DIRECTORY to
# sys.path ahead of PYTHONPATH, so with cwd = repo root, `import tools_py...` finds the repo root's
# OWN tools_py/ first regardless of PYTHONPATH. Verified 2026-09-13: with
# PYTHONPATH=<out_dir>/harness and cwd = repo root, `python -c "import tools_py.parity.gate as m;
# print(m.__file__)"` printed the repo root's gate.py, not the pinned one.
#
# The fix is Python 3.11+'s safe-path mode, which turns OFF that automatic prepend: PYTHONSAFEPATH=1
# (equivalently the `-P` flag). With that set, PYTHONPATH order wins and the pinned copy loads, while
# cwd is untouched so every cwd-relative game/log/dist path still resolves at the repo root. Verified
# 2026-09-13: the same import with PYTHONSAFEPATH=1 printed <out_dir>/harness/tools_py/parity/gate.py,
# and `python -m tools_py.parity.gate --score-title ...` ran correctly with cwd still at the repo root.
#
# A launch script therefore does, from the repo root:
#   harness=$(scripts/pin_harness.sh logs/parity/some_run | tail -1)     # prints <out_dir>/harness
#   PYTHONPATH="$harness" PYTHONSAFEPATH=1 \
#     python -m tools_py.parity.online_match_ours ...                    # cwd stays the repo root
# and its RESULT line should print the harness and exe commits, read back from
# <out_dir>/harness/HARNESS_COMMIT and <out_dir>/harness/EXE_BUILD.
#
# This script runs that same check itself (non-fatally: a WARNING, not a failure, since the snapshot
# is still usable for inspection even if the environment lacks PYTHONSAFEPATH) and prints
# "pin_harness: OK" or "pin_harness: WARNING" accordingly.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
. "$ROOT/scripts/python_env.sh"   # $PYTHON, resolved once for every script
cd "$ROOT"

if [ $# -lt 1 ]; then
  echo "usage: $0 <out_dir> [<sha>]"
  exit 2
fi
out_dir="$1"
sha="${2:-HEAD}"
harness="$out_dir/harness"

if ! resolved_sha="$(git rev-parse --verify --quiet "${sha}^{commit}" 2>/dev/null)"; then
  echo "pin_harness: cannot resolve '$sha' to a commit"
  exit 2
fi

rm -rf "$harness"
mkdir -p "$harness"
if ! git archive "$resolved_sha" tools_py scripts | tar -x -C "$harness"; then
  echo "pin_harness: git archive/tar failed for $resolved_sha"
  exit 1
fi
echo "$resolved_sha" > "$harness/HARNESS_COMMIT"

exe="$ROOT/dist/socom2.exe"
if [ -f "$exe" ]; then
  mtime=$(date -u -r "$exe" +%Y-%m-%dT%H:%M:%SZ)
  sha256=$(sha256sum "$exe" | cut -d' ' -f1)
  printf 'path=%s mtime=%s sha256=%s\n' "$exe" "$mtime" "$sha256" > "$harness/EXE_BUILD"
else
  echo "path=NOT-FOUND mtime= sha256=" > "$harness/EXE_BUILD"
  echo "pin_harness: WARNING -- game exe not found at $exe; EXE_BUILD has no mtime/sha256" >&2
fi

# Note: this command line contains "tools_py.parity", which is exactly what loop_lock.sh's own
# busy-list regex matches on a `python` process (scripts/loop_lock.sh's busy_list()) -- so a
# concurrent `take`/reap glancing at the process list while this runs would see it as busy. It is
# sub-second, so in practice this never lines up with a stale-break window, but it is the same class
# of process as the one the busy list exists to protect against.
# The comparison is python's, on real paths (close-out wave): a string prefix match WARNed whenever <out_dir> was
# relative (logs/parity/...) or an MSYS /c/... path, because python prints C:\... . The snapshot is handed over as
# MSYS resolves it (`pwd -W`: C:/...), which python can realpath.
harness_win=$(cd "$harness" && { pwd -W 2>/dev/null || pwd; })
check=$(PYTHONPATH="$harness_win" PYTHONSAFEPATH=1 "$PYTHON" -c \
  "import os, sys, tools_py.parity.online_match_ours as m
h = os.path.normcase(os.path.realpath(sys.argv[1])); f = os.path.normcase(os.path.realpath(m.__file__))
print(m.__file__); sys.exit(0 if f.startswith(h + os.sep) else 3)" "$harness_win" 2>&1)
if [ $? -eq 0 ]; then
  echo "pin_harness: OK -- $check"
else
  echo "pin_harness: WARNING -- pinned import check did not resolve under $harness: $check" >&2
fi

echo "$harness"
