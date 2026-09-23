#!/usr/bin/env bash
# The pipeline, parameterised by disc revision (Sprint 11 Task 9, Goal B):
#
#   bash scripts/build_revision.sh <rev> <APACHE00.ZDB> [--check-against <elf>] [--dry-run] [--stop-after <step>]
#                                  [--force] [--out <dir>] [--game <disc tree>] [--loader <elf>] [--loader-text-end 0x..]
#
#   rev   r + four digits, optionally followed by letters and digits (r0001, r0004, r0001check). The suffix form
#         exists so a check build of the r0001 disc never overwrites r0001's own products.
#   zdb   the revision's RUN/RAW/APACHE00.ZDB inside its extracted disc tree (scripts/disc_to_elf.sh makes the
#         tree; the tree must also hold the loader SCUS_972.xx and OVERLAY/REL/DNAS.dec.bin, because the
#         decryption runs the loader's own code under Unicorn -- tools_py/decrypt_apache.py's docstring).
#
# Five steps, each skipped when its product is already there (--force redoes it), the last two under the machine's
# loop lock (scripts/loop_lock.sh, owner build-revision):
#   1 decrypt           tools_py.decrypt_apache.main(<tree>, game/overlays_<rev>)  -> ftscore.bin, zsealetc.bin
#   2 make_overlay_elf  loader + both overlays                                    -> game/overlays_<rev>/socom2_game_<rev>.elf
#     --check-against <elf>: sha256 of that ELF against the given one; a mismatch prints both digests and exits 1
#   3 toml              recomp/socom2.toml with input/output/ghidra_output rewritten -> recomp/socom2_<rev>.toml;
#                       recomp/socom2_ghidra_<rev>.csv starts as a copy of r0001's map when the revision has none yet
#   4 recomp   [lock]   ps2_recomp socom2_<rev>.toml                               -> recomp/output_<rev>/
#   5 runtime  [lock]   cmake third_party/ps2recomp/build-clang-<rev>              -> dist/socom2_<rev>.exe (+ the ELF beside it)
#
#   --stop-after elf|recomp|runtime   stop after that step (runtime is the default); elf takes no lock at all
#   --out <dir>       every product under <dir> instead (overlays_<rev>/, recomp_<rev>/, build-clang-<rev>/, dist/),
#                     so a check build run from the main tree can land in a worktree
#   --dry-run         print the five steps with their paths and exit 0, touching nothing
#
# Exit 2 on a bad argument, 1 on a failed step or a --check-against mismatch, 0 otherwise. The shape is
# scripts/disc_to_elf.sh's (idempotent stages, one line per stage, --force); the pieces are build.sh's recomp() and
# runtime() (build.sh:31-70), which this script mirrors for one revision at a time.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$ROOT/tools/llvm-mingw/bin:$ROOT/tools/cmake/bin:$ROOT/tools/ninja:$PATH"

die2() { echo "build_revision: $*" >&2; exit 2; }
say() { echo "$*"; }

py=python
command -v python >/dev/null 2>&1 || py=python3

REV="" ZDB="" CHECK="" DRY=0 STOP="runtime" FORCE=0 OUT="" GAME="" LOADER="" LTE="" TAIL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --check-against) [ $# -ge 2 ] || die2 "--check-against needs a path"; CHECK="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --stop-after) [ $# -ge 2 ] || die2 "--stop-after needs one of elf, recomp, runtime"; STOP="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --out) [ $# -ge 2 ] || die2 "--out needs a directory"; OUT="$2"; shift 2 ;;
    --game) [ $# -ge 2 ] || die2 "--game needs the extracted disc tree"; GAME="$2"; shift 2 ;;
    --loader) [ $# -ge 2 ] || die2 "--loader needs the loader ELF"; LOADER="$2"; shift 2 ;;
    --loader-text-end) [ $# -ge 2 ] || die2 "--loader-text-end needs a hex address"; LTE="$2"; shift 2 ;;
    --_tail) TAIL=1; shift ;;      # internal: the lock-bound steps, re-entered under loop_lock.sh run
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    -*) die2 "unknown option $1" ;;
    *) if [ -z "$REV" ]; then REV="$1"; elif [ -z "$ZDB" ]; then ZDB="$1"; else die2 "unexpected argument $1"; fi; shift ;;
  esac
done

if [ "$TAIL" = 1 ]; then
  REV="$BR_REV"; STOP="$BR_STOP"; FORCE="$BR_FORCE"; OUT="$BR_OUT"
fi

[ -n "$REV" ] || die2 "usage: build_revision.sh <rev> <APACHE00.ZDB> [--check-against <elf>] [--dry-run] [--stop-after <step>]"
[[ "$REV" =~ ^r[0-9]{4}[a-z0-9]*$ ]] || die2 "revision must look like r0004 (r + four digits, an optional letters-and-digits suffix such as r0001check): got '$REV'"
case "$STOP" in elf|recomp|runtime) ;; *) die2 "--stop-after must be one of elf, recomp, runtime: got '$STOP'" ;; esac

# ---- where everything is ------------------------------------------------------------------------------------
PS2R="$ROOT/third_party/ps2recomp"
TOOLBUILD="$PS2R/build-tools"
if [ -n "$OUT" ]; then
  OUT="$(mkdir -p "$OUT" && cd "$OUT" && pwd)"
  OVERLAYS="$OUT/overlays_$REV"; RECOMP_DIR="$OUT/recomp_$REV"; GEN="$RECOMP_DIR/output"
  RTBUILD="$OUT/build-clang-$REV"; DIST="$OUT/dist"
  TOML_INPUT="../overlays_$REV/socom2_game_$REV.elf"; TOML_OUTPUT="./output/"
else
  OVERLAYS="$ROOT/game/overlays_$REV"; RECOMP_DIR="$ROOT/recomp"; GEN="$ROOT/recomp/output_$REV"
  RTBUILD="$PS2R/build-clang-$REV"; DIST="$ROOT/dist"
  TOML_INPUT="../game/overlays_$REV/socom2_game_$REV.elf"; TOML_OUTPUT="./output_$REV/"
fi
ELF="$OVERLAYS/socom2_game_$REV.elf"
TOML="$RECOMP_DIR/socom2_$REV.toml"
CSV="$RECOMP_DIR/socom2_ghidra_$REV.csv"
EXE="$DIST/socom2_$REV.exe"
rel() { case "$1" in "$ROOT"/*) echo "${1#"$ROOT"/}" ;; *) echo "$1" ;; esac; }
sha() { sha256sum "$1" | cut -d' ' -f1; }

if [ "$TAIL" = 0 ]; then
  [ -n "$ZDB" ] || die2 "usage: build_revision.sh <rev> <APACHE00.ZDB> [--check-against <elf>] [--dry-run] [--stop-after <step>]"
  [ -f "$ZDB" ] || die2 "no such package: $ZDB"
  ZDB="$(cd "$(dirname "$ZDB")" && pwd)/$(basename "$ZDB")"
  [ -n "$GAME" ] || GAME="$(dirname "$(dirname "$(dirname "$ZDB")")")"
  if [ -z "$LOADER" ]; then
    for cand in "$GAME"/SCUS_* "$GAME"/SCES_* "$GAME"/SLUS_* "$GAME"/SLES_*; do
      if [ -f "$cand" ]; then LOADER="$cand"; break; fi
    done
  fi
  [ -n "$LTE" ] || LTE="$(cat "$ROOT/recomp/loader_text_end.txt")"
  if [ -n "$CHECK" ] && [ "$DRY" = 0 ]; then
    [ -f "$CHECK" ] || die2 "no such ELF to check against: $CHECK"
  fi
fi

# ---- dry run ------------------------------------------------------------------------------------------------
if [ "$DRY" = 1 ]; then
  say "build_revision $REV (dry run): nothing is touched"
  say "  package        $(rel "$ZDB")"
  say "  disc tree      $(rel "$GAME")   loader $(rel "${LOADER:-<none found: SCUS_*/SCES_*/SLUS_*/SLES_* in the tree, or --loader>}")"
  say "  step 1  decrypt           tools_py.decrypt_apache.main(tree, overlays) -> $(rel "$OVERLAYS")/{ftscore,zsealetc}.bin"
  say "  step 2  make_overlay_elf  loader + overlays (--loader-text-end=$LTE) -> $(rel "$ELF")${CHECK:+   check-against $(rel "$CHECK")}"
  say "  step 3  toml              recomp/socom2.toml -> $(rel "$TOML") (input/output/ghidra_output rewritten); $(rel "$CSV") from socom2_ghidra.csv when absent"
  say "  step 4  recomp   [lock]   ps2_recomp socom2_$REV.toml -> $(rel "$GEN")/"
  say "  step 5  runtime  [lock]   cmake $(rel "$RTBUILD") -> $(rel "$EXE") (+ $(rel "$DIST")/socom2_game_$REV.elf)"
  [ "$STOP" = runtime ] || say "  stop after $STOP"
  exit 0
fi

# ---- steps 1-3, lock-free -----------------------------------------------------------------------------------
if [ "$TAIL" = 0 ]; then
  mkdir -p "$OVERLAYS" "$RECOMP_DIR" "$DIST"
  # 1 decrypt
  if [ "$FORCE" = 0 ] && [ -f "$OVERLAYS/ftscore.bin" ] && [ -f "$OVERLAYS/zsealetc.bin" ]; then
    say "decrypt: ftscore.bin and zsealetc.bin are already in $(rel "$OVERLAYS") -- skipped (--force redoes it)"
  else
    [ -n "$LOADER" ] || die2 "no loader ELF (SCUS_*, SCES_*, SLUS_*, SLES_*) in $GAME -- pass --loader, or --game with the extracted disc tree"
    [ -f "$GAME/OVERLAY/REL/DNAS.dec.bin" ] || die2 "$GAME/OVERLAY/REL/DNAS.dec.bin is missing: the decryption needs the decrypted DNAS overlay (scripts/disc_to_elf.sh --stages dnas makes it)"
    [ "$ZDB" = "$GAME/RUN/RAW/APACHE00.ZDB" ] || die2 "the package must be the tree's own RUN/RAW/APACHE00.ZDB ($GAME/RUN/RAW/APACHE00.ZDB): the decryption runs the tree's loader on it"
    say "decrypt: running the loader's decryption under Unicorn (about eight minutes; the progress lines go to $(rel "$OVERLAYS")/build_revision-decrypt.log)"
    if ! (cd "$ROOT" && "$py" -c 'import sys; from tools_py import decrypt_apache; decrypt_apache.main(sys.argv[1], sys.argv[2])' "$GAME" "$OVERLAYS") > "$OVERLAYS/build_revision-decrypt.log" 2>&1; then
      tail -20 "$OVERLAYS/build_revision-decrypt.log" >&2
      echo "build_revision: decrypt failed (the log above)" >&2; exit 1
    fi
    say "decrypt: ftscore.bin ($(stat -c %s "$OVERLAYS/ftscore.bin") B) + zsealetc.bin ($(stat -c %s "$OVERLAYS/zsealetc.bin") B) written"
  fi
  # 2 elf
  if [ "$FORCE" = 0 ] && [ -f "$ELF" ]; then
    say "elf: $(rel "$ELF") is already there -- skipped (--force redoes it)"
  else
    [ -n "$LOADER" ] || die2 "no loader ELF (SCUS_*, SCES_*, SLUS_*, SLES_*) in $GAME -- pass --loader"
    "$py" "$ROOT/tools_py/make_overlay_elf.py" "--loader-text-end=$LTE" "$ELF" "$LOADER" "$OVERLAYS/ftscore.bin" "$OVERLAYS/zsealetc.bin"
  fi
  ELF_SHA="$(sha "$ELF")"
  say "elf: sha256 $ELF_SHA  $(rel "$ELF")"
  if [ -n "$CHECK" ]; then
    CHECK_SHA="$(sha "$CHECK")"
    if [ "$ELF_SHA" = "$CHECK_SHA" ]; then
      say "check-against: identical to $(rel "$CHECK")"
    else
      echo "check-against: MISMATCH" >&2
      echo "  produced  $ELF_SHA  $(rel "$ELF")" >&2
      echo "  expected  $CHECK_SHA  $(rel "$CHECK")" >&2
      exit 1
    fi
  fi
  [ "$STOP" = elf ] && { say "stop after elf"; exit 0; }
  # 3 toml (+ the revision's Ghidra map, r0001's as the starting point)
  if [ ! -f "$CSV" ]; then
    cp "$ROOT/recomp/socom2_ghidra.csv" "$CSV"
    say "toml: $(rel "$CSV") starts as a copy of r0001's function map (socom2_ghidra.csv); a revision's own map replaces it"
  fi
  sed -e "s|^input *=.*|input = \"$TOML_INPUT\"|" \
      -e "s|^output *=.*|output = \"$TOML_OUTPUT\"|" \
      -e "s|^ghidra_output *=.*|ghidra_output = \"socom2_ghidra_$REV.csv\"|" \
      "$ROOT/recomp/socom2.toml" > "$TOML"
  say "toml: $(rel "$TOML") (input $TOML_INPUT, output $TOML_OUTPUT, ghidra_output socom2_ghidra_$REV.csv)"
  # 4-5 under the lock, re-entering this script
  export BR_REV="$REV" BR_STOP="$STOP" BR_FORCE="$FORCE" BR_OUT="$OUT"
  exec bash "$ROOT/scripts/loop_lock.sh" run build-revision --purpose "build_revision $REV: recomp$([ "$STOP" = runtime ] && echo ' + runtime')" \
       --wait "${BUILD_REVISION_LOCK_WAIT:-60}" -- bash "$ROOT/scripts/build_revision.sh" --_tail
fi

# ---- steps 4-5, under the lock -------------------------------------------------------------------------------
command -v clang >/dev/null 2>&1 && command -v cmake >/dev/null 2>&1 && command -v ninja >/dev/null 2>&1 \
  || die2 "no toolchain under tools/ -- run: bash scripts/bootstrap_windows.sh"
# 4 recomp
if [ "$FORCE" = 0 ] && [ -d "$GEN" ] && [ -n "$(ls -A "$GEN" 2>/dev/null)" ]; then
  say "recomp: $(ls "$GEN" | wc -l) files already in $(rel "$GEN") -- skipped (--force redoes it)"
else
  "$py" "$ROOT/tools_py/fix_ghidra_csv.py" "$CSV" "$ROOT/recomp/extra_functions.txt"
  cmake -S "$PS2R" -B "$TOOLBUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ >/dev/null
  cmake --build "$TOOLBUILD" --target ps2_recomp ps2_analyzer -j "$(nproc)"
  rm -rf "$GEN"
  (cd "$RECOMP_DIR" && "$TOOLBUILD/ps2xRecomp/ps2_recomp.exe" "socom2_$REV.toml" > "recomp_run_$REV.log" 2>&1) \
      || { tail -20 "$RECOMP_DIR/recomp_run_$REV.log" >&2; echo "build_revision: recomp failed (the log above)" >&2; exit 1; }
  say "recomp: $(ls "$GEN" | wc -l) files in $(rel "$GEN"), unhandled=$(grep -c unhandled-instruction "$RECOMP_DIR/recomp_run_$REV.log" || true)"
fi
[ "$STOP" = recomp ] && { say "stop after recomp"; exit 0; }
# 5 runtime
if [ "$FORCE" = 0 ] && [ -f "$EXE" ]; then
  say "runtime: $(rel "$EXE") is already there -- skipped (--force redoes it)"
else
  cmake -S "$PS2R" -B "$RTBUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
        -DPS2X_RUNNER_GENERATED_DIR="$GEN" -DPS2X_ENABLE_LTO="${LTO:-OFF}" -DPS2X_GENERATED_OPT="${GENOPT:--O1}" >/dev/null
  cmake --build "$RTBUILD" --target ps2EntryRunner -j "$(nproc)"
  mkdir -p "$DIST"
  cp "$RTBUILD/ps2xRuntime/ps2EntryRunner.exe" "$EXE"
  cp "$ELF" "$DIST/socom2_game_$REV.elf"
  say "runtime: $(rel "$EXE") ($(stat -c %s "$EXE") B) + $(rel "$DIST")/socom2_game_$REV.elf"
fi
say "build_revision $REV: done"
