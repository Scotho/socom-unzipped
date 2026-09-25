#!/usr/bin/env bash
# scripts/parity/env.sh -- the shared environment for the online harness scripts.
#
# This file is SOURCED, never executed: `. "$(dirname "$0")/env.sh"`, right after the ROOT/cd preamble.
# Every online script under scripts/parity/ sources it, so the instrument set (PS2X_PEEK, the call trace,
# the sampler) lives in exactly one place -- when the peek block was copy-pasted into each script, a drift
# in one copy silently changed what that run measured while every RESULT line still looked the same.
#
# SOCOM_SERVER_IP is the one knob that points the harness at another server. It must be the LAN address of
# the machine running the Horizon stack, or the exe advertises 127.0.0.1 as its own address
# (docs/HANDOFF.md); 192.168.2.10 is the owner's machine.
#
#     SOCOM_SERVER_IP=10.0.0.5 bash scripts/parity/online_control_round.sh "foxhunt"
#
# Every value uses ${VAR:-default}, so whatever is already in the operator's environment wins and sourcing
# this file twice is harmless. No `set -e`/`set -u` here and nothing but assignments and one sourced helper
# -- it is safe to source from a script that has already set its own shell options.

# $PYTHON, resolved once for everybody (an explicit PYTHON, else `python`, else `python3`): a Linux machine
# has no `python`, and the harness scripts all invoke the interpreter. BASH_SOURCE, not $0 -- $0 is still the
# sourcing script's own name.
. "$(dirname "${BASH_SOURCE[0]}")/../python_env.sh"

SOCOM_SERVER_IP="${SOCOM_SERVER_IP:-192.168.2.10}"
export SOCOM_SERVER_IP
export PS2X_SOCOM2_SERVER="${PS2X_SOCOM2_SERVER:-$SOCOM_SERVER_IP}"

export PS2X_DEV="${PS2X_DEV:-1}"                            # everything below is a Dev knob (docs/KNOBS.md)
export PS2X_HOST_GAMEPAD="${PS2X_HOST_GAMEPAD:-0}"          # a launch boots with no controller (see gate.py)
export PS2X_SOCOM2_INPUT_TRACE="${PS2X_SOCOM2_INPUT_TRACE:-1}"
export PS2X_PC_SAMPLER="${PS2X_PC_SAMPLER:-0.25}"
export PS2X_CALL_TRACE_EVERY="${PS2X_CALL_TRACE_EVERY:-10}"

# THE INSTRUMENT ADDRESSES ARE PER REVISION (Sprint 11 Task 19). PS2X_PEEK -- the actor block, the
# snap-back pair, the alive byte and health, CZNetGame and its valves with their name bytes, the
# mission-abort valve, the round clock and its string -- and PS2X_CALL_TRACE's two functions were r0001
# literals here, and every online script sources this file. `s11_r0004_round1` is what that cost: two
# r0004 clients played a Frostfire round to its clock and it scored RESULT NO-DATA, because every chain
# pointed at somebody else's memory. A wrong address here is not an error, it is silence.
#
# `tools_py/parity/guest_addresses.py` is the one home for both strings now, and it picks the column the
# way gate.py picks its own: the build banner in the image $SOCOM_GAME_ELF names (launch_revision). An
# image that will not say which revision it is REFUSES here rather than handing an r0004 launch r0001's
# addresses. The one relaxation is gate.collect_pins': with no $SOCOM_GAME_ELF and no image at the default
# path -- a bare clone, where no launch can happen either -- the column is r0001 from the path's own name.
#
# The emitted lines are `VAR="${VAR:-<spec>}"`, so the operator's own PS2X_PEEK still wins and sourcing
# this file twice is still harmless -- the two properties the literals had, kept.
socom_require_python "parity/env.sh"
if ! _socom_instruments="$("$PYTHON" -m tools_py.parity.guest_addresses --env)"; then
  echo "scripts/parity/env.sh: the per-revision instrument addresses could not be resolved (see above)." >&2
  echo "  Refusing to hand this launch another revision's PS2X_PEEK -- that measures nothing and says so" >&2
  echo "  nowhere. Check \$SOCOM_GAME_ELF, or run: \$PYTHON -m tools_py.parity.guest_addresses --env" >&2
  unset _socom_instruments
  # `exit`, not `return`: a `return` would end THIS file and let the sourcing script carry on with no
  # PS2X_PEEK at all -- which is the silent measurement this whole change exists to stop.
  exit 1
fi
eval "$_socom_instruments"
unset _socom_instruments
export PS2X_PEEK PS2X_CALL_TRACE
