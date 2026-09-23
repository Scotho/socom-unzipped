#!/usr/bin/env bash
# Point this clone's git hooks at scripts/hooks/ -- the leak check before every commit and every push.
# Run once per clone: bash scripts/install_hooks.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
. scripts/python_env.sh            # $PYTHON, resolved once for every script
chmod +x scripts/hooks/* 2>/dev/null || true
git config core.hooksPath scripts/hooks
echo "hooks: core.hooksPath = $(git config core.hooksPath)"
"$PYTHON" -m tools_py.release.leakcheck staged >/dev/null && echo "hooks: the leak check runs (self-test passed)"
