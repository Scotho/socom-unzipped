#!/usr/bin/env bash
# End-to-end build: synthetic ELF -> recompiled C++ -> socom2 runner (clang / llvm-mingw).
# Usage: ./build.sh [tools|recomp|runtime|test|all]   (default all)
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
  python "$ROOT/tools_py/fix_ghidra_csv.py" "$ROOT/recomp/socom2_ghidra.csv" "$ROOT/recomp/extra_functions.txt"
  build_tools   # incremental; the recompiler embeds the runtime call list, keep it in sync
  rm -rf "$GEN"
  (cd "$ROOT/recomp" && "$TOOLBUILD/ps2xRecomp/ps2_recomp.exe" socom2.toml > recomp_run.log 2>&1) \
      || { tail -20 "$ROOT/recomp/recomp_run.log"; exit 1; }
  echo "recomp: $(ls "$GEN" | wc -l) files, unhandled=$(grep -c unhandled-instruction "$ROOT/recomp/recomp_run.log" || true)"
}

runtime() {
  cmake -S "$PS2R" -B "$RTBUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
        -DPS2X_RUNNER_GENERATED_DIR="$GEN" -DPS2X_ENABLE_LTO="${LTO:-OFF}" -DPS2X_GENERATED_OPT="${GENOPT:--O1}" >/dev/null
  cmake --build "$RTBUILD" --target ps2EntryRunner -j "$(nproc)"
  mkdir -p "$ROOT/dist"
  cp "$RTBUILD/ps2xRuntime/ps2EntryRunner.exe" "$ROOT/dist/socom2.exe"
  cp "$RTBUILD/ps2xRuntime/"*.dll "$ROOT/dist/" 2>/dev/null || true
  for d in libc++.dll libunwind.dll libwinpthread-1.dll; do
    [ -f "$ROOT/tools/llvm-mingw/bin/$d" ] && cp "$ROOT/tools/llvm-mingw/bin/$d" "$ROOT/dist/"
  done
  echo "built dist/socom2.exe"
}

test_step() {
  cmake --build "$RTBUILD" --target ps2x_tests vu1_replay -j "$(nproc)"
  # ps2x_tests reads ps2xRecomp/include/ps2recomp/instructions.h relative to its own directory.
  local ps2x_test_repeat="${PS2X_TEST_REPEAT:-1}"
  ( cd "$RTBUILD/ps2xTest" && for i in $(seq 1 "$ps2x_test_repeat"); do
      echo "ps2x_tests run $i/$ps2x_test_repeat"
      if ! ./ps2x_tests.exe; then
        echo "ps2x_tests run $i/$ps2x_test_repeat FAILED"
        exit 1
      fi
    done )
  mkdir -p "$ROOT/dist"
  cp "$RTBUILD/ps2xRuntime/vu1_replay.exe" "$ROOT/dist/vu1_replay.exe"
  # Four verify runs over the two fixture sets, then the two host-draw checks. The native registry is ON by default
  # (kVu1NativeDefault), so the path a run takes has to be selected explicitly: --no-native forces
  # the generated/interpreted path, --native forces the registry. Both flags must follow the golden
  # path -- --verify consumes the next argument. Every run prints
  # "[vu1_replay] native entered=.. ended=.. handbacks=..", which says which path actually ran.
  #
  #   1-2 (--no-native): the generated/interpreted path over both sets; both report entered=0.
  #   3   (--native):    the title set enters at pc 0, which no native program claims, so it is a
  #                      no-op for the registry and also reports entered=0 -- this line is a
  #                      regression check that the native programs do NOT intercept the title set,
  #                      not native coverage.
  #   4   (--native):    the 0x1b50 dispatcher set is the one with native coverage; it reports a
  #                      non-zero entered=.. (entered = ended + handbacks) and must still match the
  #                      same golden packets and registers as run 2.
  "$ROOT/dist/vu1_replay.exe" --verify "$ROOT/tests/fixtures/vu1/title/golden.txt" --no-native "$ROOT"/tests/fixtures/vu1/title/*.bin
  "$ROOT/dist/vu1_replay.exe" --verify "$ROOT/tests/fixtures/vu1/dispatch_0x1b50/golden.txt" --no-native "$ROOT"/tests/fixtures/vu1/dispatch_0x1b50/*.bin
  "$ROOT/dist/vu1_replay.exe" --verify "$ROOT/tests/fixtures/vu1/title/golden.txt" --native "$ROOT"/tests/fixtures/vu1/title/*.bin
  "$ROOT/dist/vu1_replay.exe" --verify "$ROOT/tests/fixtures/vu1/dispatch_0x1b50/golden.txt" --native "$ROOT"/tests/fixtures/vu1/dispatch_0x1b50/*.bin
  # 5: the same set with PS2X_VU1_HOST_DRAW=1 (command 0x28 draws through GS::submitHostTriangle
  #    instead of kicking its packet). There are no packets to compare then, so this run checks end
  #    pc, VU data memory and the register file -- the knob must not change any of them.
  "$ROOT/dist/vu1_replay.exe" --verify "$ROOT/tests/fixtures/vu1/dispatch_0x1b50/golden.txt" --native --host-draw "$ROOT"/tests/fixtures/vu1/dispatch_0x1b50/*.bin
  # 6: and what the two paths actually draw, pixel for pixel, into a 640x448 framebuffer. The host
  #    path keeps the sub-1/16-pixel fraction the GIF path truncates, so edge and gouraud-rounding
  #    pixels differ by design; anything past the tolerance means a wrong lane or a wrong context.
  "$ROOT/dist/vu1_replay.exe" --vram-diff "$ROOT/logs/vramdiff_fixtures" "$ROOT"/tests/fixtures/vu1/dispatch_0x1b50/*.bin
  # 7: the work-ceiling refusal path. tests/fixtures/vu1/clamp holds vu1dump4_prog_11 with TOP+2.z
  #    rewritten from 76 to 300 -- above kMaxVertices -- and a golden taken from the microcode path
  #    on that patched dump (which runs 5.6M cycles to produce nothing, i.e. exactly the runaway
  #    the ceiling exists to stop). The native path must refuse it: this run has to report
  #    "entered=1 ended=0 handbacks=1" and still match end pc, VU data memory and every register.
  #    Regenerate with:
  #      python -m tools_py.vu1_headers --set-vertices 300 --out tests/fixtures/vu1/clamp \
  #          tests/fixtures/vu1/dispatch_0x1b50/vu1dump4_prog_11.bin
  #      PS2X_VU1_FAST=0 PS2X_VU1_GEN=0 dist/vu1_replay.exe --batch tests/fixtures/vu1/clamp \
  #          --no-native tests/fixtures/vu1/clamp/*.bin     # then state.txt -> golden.txt
  "$ROOT/dist/vu1_replay.exe" --verify "$ROOT/tests/fixtures/vu1/clamp/golden.txt" --native --regs all "$ROOT"/tests/fixtures/vu1/clamp/*.bin
  # 8-9: the per-handler clamps. Run 7 exercises the PRE-SCAN's ceiling -- a header above it is
  #    refused whole at 0x1b50 and no handler is ever entered -- so it says nothing about the
  #    clamps inside the handlers. Those cannot be reached with data at all: the pre-scan reads
  #    the same two header words first, and vi10 is bounded by the clipper that produces it. They
  #    are reached instead with the two test-only ceiling overrides, which lower the HANDLER-side
  #    ceilings and leave the pre-scan's real constants alone (socom2_dispatch_0x1b50.cpp:
  #    vertexCeiling / triangleCeiling / clippedVertexCeiling). Nothing in the game sets either.
  #
  #    Both runs check against run 4's own unmodified golden, with no new fixture bytes, because
  #    that is the whole claim: a clamp hand-back has to leave exactly the state the microcode then
  #    finishes the list from, so the end state must be the microcode's to the last register.
  #
  #    8: PS2X_VU1_NATIVE_TEST_CEILING=2 trips cmdUnpackVertices' clamp at 0x0b28 (TOP+2.z is 8..76
  #       across the set) on the FIRST command of all twelve lists, every one of which starts 68.
  #    9: PS2X_VU1_NATIVE_TEST_CLIP_CEILING=2 leaves every family-A count alone and trips
  #       cmdClippedTransform's clamp at 0x0f38 (vi10) MID-LIST on the six lists that contain
  #       family-B commands -- after 68/06/02 have run and the clipper has written qwords 40-111,
  #       112 and 329.z and left vi8/vi10/vi12/vi15 live. That is the hand-back research/13 6.3
  #       calls the inside of an indivisible unit, and the one this file's whole-state
  #       reproduction is what makes safe; the other six (family A and C-over-A) still run to
  #       their E bit, which is what makes the run a two-sided check rather than a blanket refusal.
  expect_native() { # $1 = the exact counts to require, then the command
    local want="$1"; shift
    local out
    out="$("$@" 2>&1)"
    printf '%s\n' "$out" | grep -E 'native entered|PASS|FAIL' || true
    if ! printf '%s\n' "$out" | grep -q "\[vu1_replay\] native $want"; then
      printf 'clamp check: expected "native %s", got: %s\n' \
        "$want" "$(printf '%s\n' "$out" | grep 'native entered')" >&2
      return 1
    fi
    printf '%s\n' "$out" | grep -q '^PASS' || { echo "clamp check: verify did not PASS" >&2; return 1; }
  }
  expect_native "entered=12 ended=0 handbacks=12" \
    env PS2X_VU1_NATIVE_TEST_CEILING=2 "$ROOT/dist/vu1_replay.exe" \
      --verify "$ROOT/tests/fixtures/vu1/dispatch_0x1b50/golden.txt" --native --regs all \
      "$ROOT"/tests/fixtures/vu1/dispatch_0x1b50/*.bin
  expect_native "entered=12 ended=6 handbacks=6" \
    env PS2X_VU1_NATIVE_TEST_CLIP_CEILING=2 "$ROOT/dist/vu1_replay.exe" \
      --verify "$ROOT/tests/fixtures/vu1/dispatch_0x1b50/golden.txt" --native --regs all \
      "$ROOT"/tests/fixtures/vu1/dispatch_0x1b50/*.bin
  echo "tests: ok"
}

case "$STEP" in
  tools)   build_tools ;;
  recomp)  recomp ;;
  runtime) runtime ;;
  test)    test_step ;;
  all)     recomp; runtime ;;
  *) echo "unknown step $STEP"; exit 2 ;;
esac
