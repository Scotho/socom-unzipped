#!/usr/bin/env bash
# Linux build (Sprint 8 Goal 1, design item 1): the same CMake tree as build.sh, with the system
# toolchain instead of tools/llvm-mingw.
#
# Usage: scripts/build_linux.sh [tools|runtime|test|all] [--no-runner]
#   tools     configure + build ps2_recomp / ps2_analyzer in build-linux-tools
#   runtime   configure + build the runner (when there is generated code) and the launcher in build-linux
#   test      the Python suite, then ps2x_tests
#   all       tools + runtime (the default)
#   --no-runner   build with no generated code at all: PS2X_RUNNER_GENERATED_DIR="", which skips the
#                 ps2EntryRunner target (see ps2xRuntime/CMakeLists.txt). This is the CI shape -- the
#                 recompiled game is produced from the owner's disc and is not in the repository.
#
# What this deliberately does NOT mirror from build.sh:
#   * the recomp step (make_overlay_elf.py / fix_ghidra_csv.py / ps2_recomp over socom2.toml): it needs
#     the owner's disc image and overlays, which no CI machine and no fresh clone has.
#   * scripts/check_quiet_gate.sh: that is the owner's host-quiet gate (a tasklist probe for a running
#     launch on their desk). Nothing here launches the game.
#   * the vu1_replay verify/vram-diff runs: src/tools/vu1_replay.cpp includes <windows.h> unguarded, so
#     the tool does not build on Linux yet. Restore those runs here once it does.
#   * copying the llvm-mingw and FFmpeg DLLs into dist/: that is the Windows runtime layout.
#     scripts/make_portable.sh grows the Linux lib/ layout in a later task (design item 5).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CC="${CC:-clang}"
CXX="${CXX:-clang++}"
export CC CXX

PS2R="$ROOT/third_party/ps2recomp"
TOOLBUILD="$PS2R/build-linux-tools"    # ps2_recomp / ps2_analyzer
RTBUILD="$PS2R/build-linux"            # runtime + tests + launcher (+ runner when there is generated code)
GEN="${PS2X_RUNNER_GENERATED_DIR:-$ROOT/recomp/output}"
DIST="$ROOT/dist-linux"

STEP=""
for arg in "$@"; do
  case "$arg" in
    --no-runner) GEN="" ;;
    tools|runtime|test|all) STEP="$arg" ;;
    *) echo "unknown argument $arg" >&2; exit 2 ;;
  esac
done
STEP="${STEP:-all}"

JOBS="$(nproc)"

cmake_configure() {   # $1 = build dir, rest = extra -D flags
  local build_dir="$1"; shift
  cmake -S "$PS2R" -B "$build_dir" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" "$@"
}

build_tools() {
  cmake_configure "$TOOLBUILD" >/dev/null
  cmake --build "$TOOLBUILD" --target ps2_recomp ps2_analyzer -j "$JOBS"
}

configure_runtime() {
  cmake_configure "$RTBUILD" \
        -DPS2X_RUNNER_GENERATED_DIR="$GEN" \
        -DPS2X_ENABLE_LTO="${LTO:-OFF}" \
        -DPS2X_GENERATED_OPT="${GENOPT:--O1}" >/dev/null
}

runtime() {
  configure_runtime
  mkdir -p "$DIST"
  if [ -n "$GEN" ] && compgen -G "$GEN/*.cpp" >/dev/null; then
    cmake --build "$RTBUILD" --target ps2EntryRunner -j "$JOBS"
    cp "$RTBUILD/ps2xRuntime/ps2EntryRunner" "$DIST/socom2"
  else
    echo "build_linux: no generated code in '${GEN:-<unset>}' -- building ps2_runtime only (no socom2)"
    cmake --build "$RTBUILD" --target ps2_runtime -j "$JOBS"
  fi
  cmake --build "$RTBUILD" --target socom_unzipped_launcher -j "$JOBS"
  cp "$RTBUILD/ps2xLauncher/socom_unzipped_launcher" "$DIST/"
  # The game ELF is produced by the recomp step on the owner's machine; carry it over when it is there.
  if [ -f "$ROOT/dist/socom2_game.elf" ]; then
    cp "$ROOT/dist/socom2_game.elf" "$DIST/"
  fi
  echo "built $DIST: $(ls "$DIST" | tr '\n' ' ')"
}

test_step() {
  # Python tests first, exactly as build.sh runs them: one runner, unittest (no pytest), discovered
  # from tools_py/tests with the repo root as the top-level directory.
  ( cd "$ROOT" && "${PYTHON:-python3}" -m unittest discover -s tools_py/tests -t . -v )
  configure_runtime
  cmake --build "$RTBUILD" --target ps2x_tests -j "$JOBS"
  # ps2x_tests reads ps2xRecomp/include/ps2recomp/instructions.h relative to its own directory.
  local repeat="${PS2X_TEST_REPEAT:-1}"
  ( cd "$RTBUILD/ps2xTest" && for i in $(seq 1 "$repeat"); do
      echo "ps2x_tests run $i/$repeat"
      if ! ./ps2x_tests; then
        echo "ps2x_tests run $i/$repeat FAILED"
        exit 1
      fi
    done )
  echo "tests: ok"
}

case "$STEP" in
  tools)   build_tools ;;
  runtime) runtime ;;
  test)    test_step ;;
  all)     build_tools; runtime ;;
  *) echo "unknown step $STEP"; exit 2 ;;
esac
