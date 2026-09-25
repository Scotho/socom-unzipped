#!/usr/bin/env bash
# scripts/parity/write_env.sh -- the one way a capture script records the PS2X_* environment it ran with (issue #38).
#
# This file is SOURCED, never executed: `. "$(dirname "${BASH_SOURCE[0]}")/write_env.sh"`. It defines one function:
#
#     write_env_ps2x <out_dir> [note]
#
# which writes <out_dir>/env_ps2x.txt (every PS2X_* in force, the `PIN env sha256=...` line in the gate's summary
# shape, SOCOM_EXE and its sha256) and <out_dir>/env_pins.json (the same pin as a run record pins.load_record reads)
# through tools_py/parity/capture_env.py -- so the hash is the gate's own env pin, byte for byte, and a native
# interpreter reads the environment exactly as the native game will (MSYS converts /c/... values for both).
#
# Call it the moment before the launch, after every export: it records what the game is handed, not what the
# script had assembled so far. KNOWN section 4: "A capture that does not record its own environment cannot prove
# the 'off' half of an A/B" -- the W6 A/B of 2026-09-23 is the unrun experiment this exists to stop.
#
# The tools come from the tree this file is in (a worktree run records with the worktree's writer); the exe is
# $SOCOM_EXE, else the data root's dist/socom2.exe. Never fatal: a failed record prints why and the capture goes on
# (the file's absence is then itself the finding), because a capture lost to its own bookkeeping is worse.
_WRITE_ENV_TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$_WRITE_ENV_TOOLS/scripts/python_env.sh"

write_env_ps2x() {   # <out_dir> [note]
  local out="$1" note="${2:-}" exe
  exe="${SOCOM_EXE:-${SOCOM_DATA_ROOT:-${ROOT:-$_WRITE_ENV_TOOLS}}/dist/socom2.exe}"
  mkdir -p "$out"
  # The interpreter check runs in a subshell: socom_require_python exits, and this file is sourced by a capture that
  # must go on without its record (the absence is the finding), so the exit must not take the capture with it.
  (socom_require_python write_env_ps2x) || { echo "write_env_ps2x: the environment was not recorded into $out" >&2; return 0; }
  PYTHONPATH="$_WRITE_ENV_TOOLS" "$PYTHON" -P -m tools_py.parity.capture_env "$out" --exe "$exe" --note "$note" \
    || echo "write_env_ps2x: could not record the environment into $out (see above)" >&2
}
