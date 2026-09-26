#!/usr/bin/env bash
# The chain step that keeps docs/PLAYTEST.md runnable (Sprint 14 Task D5; spec Milestone D, D5: "the merged
# chain's last step builds the release archive and writes PLAYTEST's build block; PLAYTEST never says NOT BUILT
# after a green chain").
#
#   bash scripts/parity/playtest_block.sh [--release]
#
# W2's merged chain (scripts/parity/merged_chain.sh) runs this LAST, inside the lock it already holds -- this step
# takes no lock of its own and must not be run bare while another session builds. It packages the build the chain
# just made (scripts/make_portable.sh, which writes <build dir>/manifest.json last, only when the archive exists)
# and then rewrites PLAYTEST's block between <!-- build:begin --> and <!-- build:end --> from that manifest.
# The chain writes the file; it commits nothing (no commits mid-chain) -- the close commits the block.
#
# A failed packaging leaves no manifest, so the block is still rewritten and says NOT BUILT (the truth), and the
# step exits with make_portable's code so the chain is not green.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/python_env.sh"   # $PYTHON
socom_require_python playtest_block
DIST="$ROOT/dist"
if [ "${1:-}" = "--release" ]; then DIST="$ROOT/dist-release"; fi
bash "$ROOT/scripts/make_portable.sh" "$@"
rc=$?
( cd "$ROOT" && "$PYTHON" -m tools_py.playtest_block --manifest "$DIST/manifest.json" ) || exit $?
exit $rc
