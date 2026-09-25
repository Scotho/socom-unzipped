#!/usr/bin/env bash
# Sprint 13 Task C1: compile the game's own files and link the runner against a SYNTHETIC generated set.
#
# The runner (ps2EntryRunner) is the recompiled game plus the files only it compiles: game_overrides_socom2.cpp,
# socom2_crypto.cpp, socom2_host_input.cpp, socom2_hostnet.cpp, socom2_libnetb.cpp and src/main.cpp. The real
# generated set (recomp/output/, 14,882 files) comes from the owner's disc and is not in the repository, so without
# one CMake skips the runner and CI never compiled those files or linked them -- a syntax error in the overrides file
# reached `main` unbuilt (the 2026-09-25 audit, code-runtime.md F7 and F41).
#
# tests/fixtures/synthetic_recomp/ is the smallest set the link accepts, in the recompiler's shape, written by hand
# (nothing in it comes from the disc; tools_py/tests/test_workflows.py holds its shape): an entry, a leaf, a
# stub wrapper, the dense function table, the two generated headers. This script configures a tree with
# PS2X_RUNNER_GENERATED_DIR pointing there, builds ps2EntryRunner, and runs it once against a missing ELF: it must
# leave with 68 (elf-missing) from the preflight, before any window -- so the static registrations of the overrides
# file and the table's initializer ran and the process exited cleanly. The binary is not a game and is never copied
# into dist/ or dist-linux/.
#
# Usage: scripts/build_synthetic_runner.sh [--build-dir DIR]
#   --build-dir DIR  the CMake tree to use. Default: its own (third_party/ps2recomp/build-synthetic, or
#                    build-linux-synthetic on Linux), never the developer's build-clang/build-linux -- pointing
#                    a tree that holds the real generated set here would recompile all 14,882 files on the way back.
#                    CI passes the job's own tree (built a step earlier with no generated code), so only the runner's
#                    own sources compile.
# The linux and windows workflows run this in their build / build-windows jobs (tools_py/tests/test_workflows.py).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PS2R="$ROOT/third_party/ps2recomp"
SYN="$ROOT/tests/fixtures/synthetic_recomp"
EXE_SUFFIX=""
BUILD="$PS2R/build-linux-synthetic"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    EXE_SUFFIX=".exe"
    BUILD="$PS2R/build-synthetic"
    # build.sh's toolchain: the pinned llvm-mingw, CMake and Ninja under tools/ (scripts/bootstrap_windows.sh).
    export PATH="$ROOT/tools/llvm-mingw/bin:$ROOT/tools/cmake/bin:$ROOT/tools/ninja:$PATH"
    ;;
esac
while [ $# -gt 0 ]; do
  case "$1" in
    --build-dir) BUILD="$2"; shift 2 ;;
    --build-dir=*) BUILD="${1#--build-dir=}"; shift ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done
CC="${CC:-clang}"
CXX="${CXX:-clang++}"
for tool in "$CXX" cmake ninja; do
  command -v "$tool" >/dev/null 2>&1 || { echo "build_synthetic_runner: no $tool on the PATH" >&2; exit 2; }
done
[ -f "$SYN/register_functions.cpp" ] || { echo "build_synthetic_runner: no synthetic set at $SYN" >&2; exit 2; }

echo "build_synthetic_runner: tree $BUILD, generated set $SYN ($(ls "$SYN"/*.cpp | wc -l) .cpp files)"
cmake -S "$PS2R" -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" \
      -DPS2X_RUNNER_GENERATED_DIR="$SYN" -DPS2X_ENABLE_LTO=OFF -DPS2X_GENERATED_OPT=-O1 \
      -DPS2X_GAME_REVISION=r0001 >/dev/null
cmake --build "$BUILD" --target ps2EntryRunner -j "$(nproc)"

RUNNER="$BUILD/ps2xRuntime/ps2EntryRunner$EXE_SUFFIX"
[ -f "$RUNNER" ] || { echo "build_synthetic_runner: the build reported success and left no $RUNNER" >&2; exit 1; }
echo "build_synthetic_runner: linked $RUNNER ($(wc -c < "$RUNNER") bytes)"

# The smoke: a missing ELF is the preflight's first refusal (ps2xShared/src/preflight.cpp, ExitCodes::kElfMissing).
missing="$BUILD/synthetic-smoke/no_such_game.elf"
rc=0
out="$(PS2X_MC_DIR="$BUILD/synthetic-smoke/mc0" "$RUNNER" "$missing" 2>&1)" || rc=$?
printf '%s\n' "$out" | tail -5
if [ "$rc" -ne 68 ] || ! printf '%s\n' "$out" | grep -q 'elf-missing'; then
  echo "build_synthetic_runner: the runner against a missing ELF left with $rc, not 68 elf-missing" >&2
  exit 1
fi
echo "build_synthetic_runner: ok (the runner starts and refuses a missing ELF with 68)"
