#!/usr/bin/env bash
# End-to-end build: synthetic ELF -> recompiled C++ -> socom2 runner (clang / llvm-mingw).
# Usage: ./build.sh [recomp|runtime|all]   (default all)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="$ROOT/tools/llvm-mingw/bin:$ROOT/tools/cmake/bin:$ROOT/tools/ninja:$PATH"
STEP="${1:-all}"

PS2R="$ROOT/third_party/ps2recomp"
TOOLBUILD="$PS2R/build-tools"      # ps2_recomp / ps2_analyzer
RTBUILD="$PS2R/build-clang"        # runtime + runner with generated code
GEN="$ROOT/recomp/output"

build_tools() {
  cmake -S "$PS2R" -B "$TOOLBUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ >/dev/null
  cmake --build "$TOOLBUILD" --target ps2_recomp ps2_analyzer -j "$(nproc)"
}

recomp() {
  local lte
  lte="$(cat "$ROOT/recomp/loader_text_end.txt")"
  python "$ROOT/tools_py/make_overlay_elf.py" "--loader-text-end=$lte" \
      "$ROOT/game/overlays/socom2_game.elf" "$ROOT/game/disc/SCUS_972.75" \
      "$ROOT/game/overlays/ftscore.bin" "$ROOT/game/overlays/zsealetc.bin"
  cp "$ROOT/game/overlays/socom2_game.elf" "$ROOT/game/disc/socom2_game.elf"
  [ -x "$TOOLBUILD/ps2xRecomp/ps2_recomp.exe" ] || build_tools
  rm -rf "$GEN"
  (cd "$ROOT/recomp" && "$TOOLBUILD/ps2xRecomp/ps2_recomp.exe" socom2.toml > recomp_run.log 2>&1) \
      || { tail -20 "$ROOT/recomp/recomp_run.log"; exit 1; }
  echo "recomp: $(ls "$GEN" | wc -l) files, unhandled=$(grep -c unhandled-instruction "$ROOT/recomp/recomp_run.log" || true)"
}

runtime() {
  cmake -S "$PS2R" -B "$RTBUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
        -DPS2X_RUNNER_GENERATED_DIR="$GEN" -DPS2X_ENABLE_LTO="${LTO:-OFF}" >/dev/null
  cmake --build "$RTBUILD" --target ps2EntryRunner -j "$(nproc)"
  mkdir -p "$ROOT/dist"
  cp "$RTBUILD/ps2xRuntime/ps2EntryRunner.exe" "$ROOT/dist/socom2.exe"
  cp "$RTBUILD/ps2xRuntime/"*.dll "$ROOT/dist/" 2>/dev/null || true
  for d in libc++.dll libunwind.dll libwinpthread-1.dll; do
    [ -f "$ROOT/tools/llvm-mingw/bin/$d" ] && cp "$ROOT/tools/llvm-mingw/bin/$d" "$ROOT/dist/"
  done
  echo "built dist/socom2.exe"
}

case "$STEP" in
  tools)   build_tools ;;
  recomp)  recomp ;;
  runtime) runtime ;;
  all)     recomp; runtime ;;
  *) echo "unknown step $STEP"; exit 2 ;;
esac
