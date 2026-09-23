#!/usr/bin/env bash
# scripts/python_env.sh -- where every shell script in this repository finds Python. One rule, one place.
#
# This file is SOURCED, never executed: `. "$(dirname "$0")/python_env.sh"` (or `../python_env.sh` from
# scripts/parity/), right after the ROOT/cd preamble. scripts/parity/env.sh sources it too, so the online
# harness gets it without a second line.
#
# The rule, in order:
#   1. PYTHON already in the environment wins -- an operator pointing at a venv or a specific build;
#   2. else `python`, if the PATH has one (the Windows host, and a CI runner with actions/setup-python);
#   3. else `python3` (every Debian/Ubuntu machine: the distribution ships python3 and nothing called
#      `python` unless somebody installs python-is-python3).
# A script that then needs the interpreter calls socom_require_python, which dies with a sentence rather
# than letting "python: command not found" arrive as exit 127 in the middle of a run.
#
# Why this exists: the socom-linux VM ran the suite on 2026-09-22 and sixteen scripts died on the bare word
# `python` -- scripts/parity/ladder_frostfire.sh:121 and scripts/make_portable.sh:91 were the two that
# reached the report. Linux CI was green throughout, because actions/setup-python puts a `python` shim on
# the PATH and hides the whole class. tools_py/tests/test_python_resolution.py holds the seam: it drives
# the scripts on a PATH with python3 and no python, the VM's shape.
#
# Every value uses ${VAR:-default}, so sourcing this file twice is harmless and whatever the operator
# exported still wins. No `set -e`/`set -u` here and nothing but an assignment and a function -- it is safe
# to source from a script that has already set its own shell options (the `|| true` keeps the command
# substitution from tripping `set -e` on a machine with no interpreter at all).

PYTHON="${PYTHON:-$(command -v python 2>/dev/null || command -v python3 2>/dev/null || true)}"
export PYTHON

# socom_require_python [name] -- exit 2 with a sentence when there is no interpreter to run.
socom_require_python() {
  if [ -z "${PYTHON:-}" ] || ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "${1:-${0##*/}}: no Python on the PATH -- neither \`python\` nor \`python3\`. Python 3 is what does the work here; install it (Debian/Ubuntu: apt install python3) or set PYTHON to the interpreter, and run this again." >&2
    exit 2
  fi
}
