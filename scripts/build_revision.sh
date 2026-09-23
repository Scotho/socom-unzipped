#!/usr/bin/env bash
# The pipeline, parameterised by disc revision (Sprint 11 Task 9, Goal B):
#
#   bash scripts/build_revision.sh <rev> <APACHE00.ZDB> [--check-against <elf>] [--dry-run] [--stop-after <step>]
#                                  [--force] [--out <dir>] [--game <disc tree>] [--loader <elf>] [--loader-text-end 0x..]
#                                  [--ghidra <csv>] [--ghidra-from-r0001]
#
#   rev   r + four digits, optionally followed by a letter and then letters and digits (r0001, r0004, r0001check).
#         The suffix form exists so a check build of the r0001 disc never overwrites r0001's own products.
#   zdb   the revision's RUN/RAW/APACHE00.ZDB inside its extracted disc tree (scripts/disc_to_elf.sh makes the
#         tree; the tree must also hold OVERLAY/REL/DNAS.dec.bin and its loader under the name SCUS_972.75 --
#         the only name step 1 can decrypt with, because tools_py/decrypt_apache.py:206 joins it onto the tree
#         itself and then runs that loader's own code under Unicorn).
#
# Five steps, each skipped when its product is already there (--force redoes it), the last two under the machine's
# loop lock (scripts/loop_lock.sh, owner build-revision):
#   1 decrypt           tools_py.decrypt_apache.main(<tree>, game/overlays_<rev>)  -> ftscore.bin, zsealetc.bin
#   2 make_overlay_elf  loader + both overlays                                    -> game/overlays_<rev>/socom2_game_<rev>.elf
#     --check-against <elf>: sha256 of that ELF against the given one; a mismatch prints both digests and exits 1
#   3 toml              recomp/socom2.toml with input/output/ghidra_output rewritten -> recomp/socom2_<rev>.toml;
#                       the revision's function map recomp/socom2_ghidra_<rev>.csv must already be there or be
#                       named with --ghidra <csv>. Only an r0001* revision falls back to r0001's own map
#                       silently; any other revision must ask for it with --ghidra-from-r0001, which warns that
#                       the generated code will be wrong until Task 10's matcher writes that revision a map.
#   4 recomp   [lock]   ps2_recomp socom2_<rev>.toml                               -> recomp/output_<rev>/
#   5 runtime  [lock]   cmake third_party/ps2recomp/build-clang-<rev>              -> dist/socom2_<rev>.exe (+ the ELF beside it)
#
#   Steps 4 and 5 mark their product with a .complete file when the step returns 0, and skip on that mark alone:
#   a tree or an exe left half-written by a failed or interrupted run is redone, never reported as done. The mark
#   is not generated code, so compare two generated trees with: diff -rq --exclude=.complete <a> <b>
#
#   --stop-after elf|recomp|runtime   stop after that step (runtime is the default); elf takes no lock at all
#   --out <dir>       every product under <dir> instead (overlays_<rev>/, recomp_<rev>/, build-clang-<rev>/, dist/),
#                     so a check build run from the main tree can land in a worktree
#   --dry-run         print the five steps with their paths and exit 0, touching nothing
#
# Exit 2 on a bad argument or a missing input, 1 on a failed step or a --check-against mismatch, 75 when the loop
# lock could not be taken within --wait (BUILD_REVISION_LOCK_WAIT, 60 minutes), 0 otherwise. The shape is
# scripts/disc_to_elf.sh's (idempotent stages, one line per stage, --force); the pieces are build.sh's recomp() and
# runtime() (build.sh:31-70), which this script mirrors for one revision at a time.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$ROOT/tools/llvm-mingw/bin:$ROOT/tools/cmake/bin:$ROOT/tools/ninja:$PATH"
. "$ROOT/scripts/python_env.sh"   # $PYTHON, resolved once for every script
socom_require_python build_revision

die2() { echo "build_revision: $*" >&2; exit 2; }
say() { echo "$*"; }

py="$PYTHON"

REV="" ZDB="" CHECK="" DRY=0 STOP="runtime" FORCE=0 OUT="" GAME="" LOADER="" LTE="" TAIL=0 GHIDRA="" GHIDRA_R0001=0
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
    --ghidra) [ $# -ge 2 ] || die2 "--ghidra needs the revision's function map (a Ghidra ExportPS2Functions CSV)"; GHIDRA="$2"; shift 2 ;;
    --ghidra-from-r0001) GHIDRA_R0001=1; shift ;;
    --_tail) TAIL=1; shift ;;      # internal: the lock-bound steps, re-entered under loop_lock.sh run
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    -*) die2 "unknown option $1" ;;
    *) if [ -z "$REV" ]; then REV="$1"; elif [ -z "$ZDB" ]; then ZDB="$1"; else die2 "unexpected argument $1"; fi; shift ;;
  esac
done

if [ "$TAIL" = 1 ]; then
  REV="$BR_REV"; STOP="$BR_STOP"; FORCE="$BR_FORCE"; OUT="$BR_OUT"
fi

[ -n "$REV" ] || die2 "usage: build_revision.sh <rev> <APACHE00.ZDB> [--check-against <elf>] [--dry-run] [--stop-after <step>]"
[[ "$REV" =~ ^r[0-9]{4}([a-z][a-z0-9]*)?$ ]] || die2 "revision must look like r0004 (r + four digits, an optional suffix that starts with a letter, such as r0001check): got '$REV'"
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
  if [ -z "$LTE" ]; then
    [ -f "$ROOT/recomp/loader_text_end.txt" ] || die2 "recomp/loader_text_end.txt is missing -- pass --loader-text-end 0x..."
    LTE="$(cat "$ROOT/recomp/loader_text_end.txt")"
  fi
  if [ -n "$CHECK" ] && [ "$DRY" = 0 ]; then
    [ -f "$CHECK" ] || die2 "no such ELF to check against: $CHECK"
  fi
  # The revision's function map, decided here so a wrong one is refused before the eight minutes of step 1 and
  # not after them. r0001's map is the right starting point for the r0001 disc and for nothing else: handed to
  # another revision it is a knowingly wrong map whose recompiled code still exits 0, so it must be asked for.
  GHIDRA_SRC="" GHIDRA_NEED=0
  if [ -n "$GHIDRA" ]; then
    [ -f "$GHIDRA" ] || die2 "no such function map: $GHIDRA"
    GHIDRA_SRC="$(cd "$(dirname "$GHIDRA")" && pwd)/$(basename "$GHIDRA")"
  elif [ ! -f "$CSV" ]; then
    case "$REV" in
      r0001*) GHIDRA_SRC="$ROOT/recomp/socom2_ghidra.csv" ;;
      *) if [ "$GHIDRA_R0001" = 1 ]; then
           GHIDRA_SRC="$ROOT/recomp/socom2_ghidra.csv"
           echo "WARNING: $REV has no function map of its own; starting from r0001's. The generated code will be wrong until Sprint 11 Task 10's matcher writes socom2_ghidra_$REV.csv." >&2
         else
           GHIDRA_NEED=1
         fi ;;
    esac
  fi
  [ "$GHIDRA_NEED" = 0 ] || [ "$DRY" = 1 ] \
    || die2 "$REV has no function map of its own ($(rel "$CSV")): pass --ghidra <csv>, or --ghidra-from-r0001 to start from r0001's map knowing the generated code will be wrong until Sprint 11 Task 10's matcher writes one"
fi

# ---- dry run ------------------------------------------------------------------------------------------------
if [ "$DRY" = 1 ]; then
  say "build_revision $REV (dry run): nothing is touched"
  say "  package        $(rel "$ZDB")"
  say "  disc tree      $(rel "$GAME")   loader $(rel "${LOADER:-<none found: SCUS_*/SCES_*/SLUS_*/SLES_* in the tree, or --loader>}")"
  say "  step 1  decrypt           tools_py.decrypt_apache.main(tree, overlays) -> $(rel "$OVERLAYS")/{ftscore,zsealetc}.bin"
  say "  step 2  make_overlay_elf  loader + overlays (--loader-text-end=$LTE) -> $(rel "$ELF")${CHECK:+   check-against $(rel "$CHECK")}"
  if [ "$GHIDRA_NEED" = 1 ]; then
    MAPNOTE="$(rel "$CSV") is not there -- the run will refuse it: pass --ghidra <csv>, or --ghidra-from-r0001"
  elif [ -n "$GHIDRA_SRC" ]; then
    MAPNOTE="$(rel "$CSV") copied from $(rel "$GHIDRA_SRC")"
  else
    MAPNOTE="$(rel "$CSV") is already there"
  fi
  say "  step 3  toml              recomp/socom2.toml -> $(rel "$TOML") (input/output/ghidra_output rewritten); $MAPNOTE"
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
    # decrypt_apache.py:206 is load_elf(ee, os.path.join(game, 'SCUS_972.75')) -- the name is hardcoded, so a
    # tree whose loader is any other one cannot get past step 1, and says so here rather than eight minutes in.
    [ -f "$GAME/SCUS_972.75" ] || die2 "step 1 can only decrypt with SCUS_972.75 (tools_py/decrypt_apache.py:206 joins that name onto the tree): $GAME holds $(basename "$LOADER") -- decrypt that tree with scripts/disc_to_elf.sh first, or give decrypt_apache a loader parameter"
    if [ ! -f "$GAME/OVERLAY/REL/DNAS.dec.bin" ]; then
      # The decryption loads the decrypted DNAS overlay first; a tree made before disc_to_elf's dnas stage existed
      # (or one whose derived files were cleaned) lacks it. It is two seconds under Unicorn, verified against
      # tools_py/disc_to_elf_expected.json, so make it here rather than send the reader to another command.
      [ -f "$GAME/OVERLAY/REL/DNAS.BIN" ] || die2 "$GAME/OVERLAY/REL/DNAS.BIN is missing: $GAME is not an extracted disc tree (scripts/disc_to_elf.sh makes one)"
      say "dnas: $(rel "$GAME")/OVERLAY/REL/DNAS.dec.bin is missing -- decrypting the DNAS overlay first (tools_py.disc_to_elf.stage_dnas, a few seconds)"
      if ! (cd "$ROOT" && "$py" -c 'import json, sys; from tools_py import disc_to_elf as d; e = json.load(open(d.EXPECTED_PATH, encoding="utf-8")); d.stage_dnas(sys.argv[1], sys.argv[2], e)' "$GAME" "$OVERLAYS") > "$OVERLAYS/build_revision-dnas.log" 2>&1; then
        tail -20 "$OVERLAYS/build_revision-dnas.log" >&2
        echo "build_revision: the DNAS stage failed (the log above); a disc whose DNAS.BIN is not r0001's needs its own entry in tools_py/disc_to_elf_expected.json (Sprint 11 Task 10) -- the stage refuses an unrecorded one" >&2; exit 1
      fi
    fi
    [ "$ZDB" = "$GAME/RUN/RAW/APACHE00.ZDB" ] || die2 "the package must be the tree's own RUN/RAW/APACHE00.ZDB ($GAME/RUN/RAW/APACHE00.ZDB): the decryption runs that tree's SCUS_972.75 on it"
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
  # 3 toml (+ the revision's function map, whose source was settled before step 1)
  if [ -n "$GHIDRA_SRC" ]; then
    cp "$GHIDRA_SRC" "$CSV"
    say "toml: $(rel "$CSV") copied from $(rel "$GHIDRA_SRC")"
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
if [ "$FORCE" = 0 ] && [ -f "$GEN/.complete" ]; then
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
  : > "$GEN/.complete"      # the mark the skip above trusts: written only when ps2_recomp returned 0
fi
[ "$STOP" = recomp ] && { say "stop after recomp"; exit 0; }
# 5 runtime
if [ "$FORCE" = 0 ] && [ -f "$EXE" ] && [ -f "$EXE.complete" ]; then
  say "runtime: $(rel "$EXE") is already there -- skipped (--force redoes it)"
else
  cmake -S "$PS2R" -B "$RTBUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
        -DPS2X_RUNNER_GENERATED_DIR="$GEN" -DPS2X_ENABLE_LTO="${LTO:-OFF}" -DPS2X_GENERATED_OPT="${GENOPT:--O1}" >/dev/null
  cmake --build "$RTBUILD" --target ps2EntryRunner -j "$(nproc)"
  mkdir -p "$DIST"
  cp "$RTBUILD/ps2xRuntime/ps2EntryRunner.exe" "$EXE"
  cp "$ELF" "$DIST/socom2_game_$REV.elf"
  : > "$EXE.complete"       # after both copies, so an interrupted copy is redone rather than shipped
  say "runtime: $(rel "$EXE") ($(stat -c %s "$EXE") B) + $(rel "$DIST")/socom2_game_$REV.elf"
fi
say "build_revision $REV: done"
