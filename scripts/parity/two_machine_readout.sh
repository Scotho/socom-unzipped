#!/usr/bin/env bash
# Sprint 7 Task 5 (spec Goal 5): the one line the owner runs after the first TWO-MACHINE match, on
# either machine, once both run logs are in one place. It turns the pair into the lobby class, whether
# each side saw the other move, the clock skew between the two round clocks, and the failure class of
# each miss -- one block to paste back as the answer to row O6 of docs/HUMAN_TASKS.md (a line in the
# next session's prompt or a note in docs/STATUS.md).
#
#     bash scripts/parity/two_machine_readout.sh <log_A> <log_B> [<harness/drive log>...]
#
# <log_A>/<log_B> are the two machines' own run logs (logs/run_A_<stamp>.log and the second machine's
# copy of the same file). A run log carries the position peek and the round clock but no RESULT/LOBBY
# lines -- those are the driver's. If either machine was driven by this repo's harness, add its
# logs/parity/drive_<name>.txt and the lobby class fills in; without it the block says so and the rest
# still reads.
#
# The spec names this file scripts/parity/two_machine_readout.py; the logic lives in
# tools_py/parity/two_machine_readout.py, where its unit test can import it, and this is the wrapper
# (plan Task 5, controller's choice). Exit 0 only when the spec's bar is met: a lobby reached and both
# players seen moving.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/python_env.sh"    # $PYTHON, resolved once for every script
socom_require_python two_machine_readout
cd "$ROOT"
if [ "$#" -lt 2 ]; then
  echo "usage: bash scripts/parity/two_machine_readout.sh <log_A> <log_B> [<harness log>...]" >&2
  exit 2
fi
exec "$PYTHON" -m tools_py.parity.two_machine_readout "$@"
