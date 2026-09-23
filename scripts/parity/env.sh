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
export PS2X_CALL_TRACE="${PS2X_CALL_TRACE:-0x553dc0:MoveScale,0x30cd80:NetIdle}"

# The instrument peek block (Sprint 5 Task 2's launch-2 spec, minus the heavy ground probes): the actor block
# and the snap-back pair (+0x420 inside *0x408c58+0x400:12), +0x174, the alive byte (+0xF7A inside
# *0x408c58+0xF78:24) and health (*0x408c58+0x1044:8), CZNetGame and its valves with their name bytes, the
# mission-abort valve, the round clock (0x4365c0 and the string at 0x408f10), and 0x408c58:4.
export PS2X_PEEK="${PS2X_PEEK:-0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,*0x437ce8+0x0c*:2,*0x437ce8+0x10*:2,*0x437ce8+0x14*:2,*0x437ce8+0x20*:2,*0x437ce8+0x24*:2,*0x437ce8+0x2c*:2,*0x437ce8+0x58*:2,*0x437ce8+0x5c*:2,*0x437ce8+0x70*:2,*0x43668c:2,0x4365c0:1,0x45a0c0:1,0x3df1b0:1,0x45a1c8:1,*0x437ce8+0x0c**:3,*0x437ce8+0x10**:3,*0x437ce8+0x14**:3,*0x437ce8+0x20**:3,*0x437ce8+0x24**:3,*0x437ce8+0x2c**:3,*0x437ce8+0x58**:3,*0x437ce8+0x5c**:3,*0x437ce8+0x70**:3,*0x43668c*:3,0x408f10:2,0x408c58:4}"
