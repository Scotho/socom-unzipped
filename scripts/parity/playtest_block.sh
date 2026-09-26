#!/usr/bin/env bash
# The chain step that keeps docs/PLAYTEST.md runnable (Sprint 14 Task D5; spec Milestone D, D5: "the merged
# chain's last step builds the release archive and writes PLAYTEST's build block; PLAYTEST never says NOT BUILT
# after a green chain").
#
#   bash scripts/parity/playtest_block.sh [--release] [out dir]      (the arguments are make_portable.sh's)
#
# W2's merged chain (scripts/parity/merged_chain.sh) runs this LAST, inside the lock it already holds -- this step
# takes no lock of its own and must not be run bare while another session builds. It packages the build the chain
# just made (scripts/make_portable.sh, which writes <build dir>/manifest.json last, only when the archive exists)
# and then rewrites PLAYTEST's block between <!-- build:begin --> and <!-- build:end --> from that manifest.
# The chain writes the file; it commits nothing (no commits mid-chain) -- the close commits the block.
#
# The build dir is chosen the way make_portable.sh chooses it: by platform (MAKE_PORTABLE_SYSTEM, else uname -s)
# and --release -- dist/, dist-release/, dist-linux/, dist-linux-release/ -- honouring the same DIST / LDIST
# overrides. PLAYTEST_BLOCK_ROOT (default: this repository) is the tree whose docs/PLAYTEST.md is rewritten, and
# PLAYTEST_BLOCK_PRINT_DIR=1 prints the chosen dir and exits 3 (never 0: not a green step); both are for
# tools_py/tests/test_playtest_block.py.
#
# A failed packaging leaves no manifest, so the block is still rewritten and says NOT BUILT (the truth), and the
# step exits with make_portable's code so the chain is not green.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$ROOT/scripts/python_env.sh"   # $PYTHON
socom_require_python playtest_block
SUFFIX=""
if [ "${1:-}" = "--release" ]; then SUFFIX="-release"; fi
case "${MAKE_PORTABLE_SYSTEM:-$(uname -s)}" in
  Linux) BUILD_DIR="${LDIST:-$ROOT/dist-linux$SUFFIX}" ;;
  *)     BUILD_DIR="${DIST:-$ROOT/dist$SUFFIX}" ;;
esac
# The test switch exits 3 after printing (Sprint 14 W2 review): a switch leaked into a chain's environment must never
# turn this step green without packaging anything.
if [ "${PLAYTEST_BLOCK_PRINT_DIR:-}" = "1" ]; then echo "$BUILD_DIR"; exit 3; fi
bash "$ROOT/scripts/make_portable.sh" "$@"
rc=$?
( cd "$ROOT" && "$PYTHON" -m tools_py.playtest_block --root "${PLAYTEST_BLOCK_ROOT:-$ROOT}" \
    --manifest "$BUILD_DIR/manifest.json" ) || exit $?
exit $rc
