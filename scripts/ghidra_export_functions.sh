#!/usr/bin/env bash
# The Ghidra headless recipe that produced recomp/socom2_ghidra.csv, written down and parameterised by
# revision (Sprint 11 Task 19, the r0004 re-recompilation).
#
#   bash scripts/ghidra_export_functions.sh <elf> <out.csv> [--toml <out.toml>] [--project-dir <dir>]
#                                           [--project <name>] [--entries "0x.. 0x.."] [--force] [--keep]
#
# Until now the recipe existed only in Ghidra's own application.log (the r0001 run of 2026-09-04): nothing
# in the tree said which language, which entry points or which scripts, so a second revision could not be
# analysed the same way. It is three headless passes over one ELF:
#
#   1 import + analyze   the stock ELF loader picks r5900:LE:32:default:default (the EE extension in
#                        tools/ghidra/Ghidra/Extensions/ghidra-emotionengine-reloaded), every analyzer at its
#                        default, with MakeFunctions.java run BEFORE analysis on the three entry points that
#                        no flow reaches: the two overlay entries and main. Plain analysis finds ~11k
#                        functions; without these three the overlays are never disassembled at all.
#   2 FindPointerTargets creates functions at code addresses only a data word points at (Metrowerks vtables
#                        and callback tables). Run twice, as r0001's was: the second pass sees the data
#                        references the first pass's new functions produced.
#   3 ExportPS2Functions writes Name,Start,End,Size for every function plus every executable label, and the
#                        companion TOML. `askFile` in headless takes its answers from the script arguments
#                        in order, so the TOML path comes first and the CSV second.
#
# The CSV this writes is the RAW export: tools_py/fix_ghidra_csv.py (End = Start + Size, plus the forced
# entry points of recomp/extra_functions.txt) is a separate step that scripts/build_revision.sh runs.
#
# --entries defaults to r0001's three, which are the same addresses in r0004: the loader region and both
# overlay load addresses are unchanged between the two revisions by construction (the disc's SCUS_972.75
# stays, only APACHE00.ZDB is replaced).
# --project-dir defaults to a directory beside the CSV; the owner's ghidra_proj/socom is never touched.
# The project is kept (--keep is the default shape) so a later pass can -process it without re-analysing.
#
# Exit 2 on a bad argument or a missing input, 1 on a failed pass, 0 otherwise.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GHIDRA="$ROOT/tools/ghidra"
HEADLESS="$GHIDRA/support/analyzeHeadless"

die2() { echo "ghidra_export_functions: $*" >&2; exit 2; }
say() { echo "$*"; }

ELF="" OUT="" TOML="" PROJDIR="" PROJ="" ENTRIES="0x4c53c0 0x180008 0x1c4cc0" FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --toml) [ $# -ge 2 ] || die2 "--toml needs a path"; TOML="$2"; shift 2 ;;
    --project-dir) [ $# -ge 2 ] || die2 "--project-dir needs a directory"; PROJDIR="$2"; shift 2 ;;
    --project) [ $# -ge 2 ] || die2 "--project needs a name"; PROJ="$2"; shift 2 ;;
    --entries) [ $# -ge 2 ] || die2 "--entries needs a space-separated list of hex addresses"; ENTRIES="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --keep) shift ;;
    -h|--help) sed -n '2,33p' "$0"; exit 0 ;;
    -*) die2 "unknown option $1" ;;
    *) if [ -z "$ELF" ]; then ELF="$1"; elif [ -z "$OUT" ]; then OUT="$1"; else die2 "unexpected argument $1"; fi; shift ;;
  esac
done

[ -n "$ELF" ] && [ -n "$OUT" ] || die2 "usage: ghidra_export_functions.sh <elf> <out.csv> [--toml <out.toml>] [--entries \"0x.. 0x..\"]"
[ -f "$ELF" ] || die2 "no such ELF: $ELF"
[ -x "$HEADLESS" ] || [ -f "$HEADLESS" ] || die2 "no Ghidra under $GHIDRA (docs/DEVELOPING.md says where it goes)"

ELF="$(cd "$(dirname "$ELF")" && pwd)/$(basename "$ELF")"
mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
[ -n "$TOML" ] || TOML="${OUT%.csv}.toml"
mkdir -p "$(dirname "$TOML")"
TOML="$(cd "$(dirname "$TOML")" && pwd)/$(basename "$TOML")"
[ -n "$PROJDIR" ] || PROJDIR="$(dirname "$OUT")/ghidra_proj_$(basename "${OUT%.csv}")"
[ -n "$PROJ" ] || PROJ="$(basename "${OUT%.csv}")"
mkdir -p "$PROJDIR"
PROJDIR="$(cd "$PROJDIR" && pwd)"

if [ "$FORCE" = 0 ] && [ -f "$OUT" ]; then
  say "ghidra: $OUT is already there -- skipped (--force redoes it)"
  exit 0
fi

# Windows paths for the JVM's own arguments; MSYS converts the bare ones inconsistently.
w() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
PROG="$(basename "$ELF")"
SCRIPTS="$(w "$ROOT/ghidra_scripts")"

run() {
  say "ghidra: $*"
  # No MSYS_NO_PATHCONV here: the launcher hands java its own LaunchSupport.jar as a POSIX path and
  # needs MSYS to convert it ("Could not find or load main class LaunchSupport" otherwise). Every
  # argument of ours is already a Windows path from w(), which MSYS leaves alone.
  bash "$HEADLESS" "$(w "$PROJDIR")" "$PROJ" "$@" || return $?
}

if [ "$FORCE" = 1 ] || [ ! -d "$PROJDIR/$PROJ.rep" ]; then
  rm -rf "$PROJDIR/$PROJ.rep" "$PROJDIR/$PROJ.gpr" "$PROJDIR/$PROJ.lock" "$PROJDIR/$PROJ.lock~"
  # shellcheck disable=SC2086
  run -import "$(w "$ELF")" -overwrite -scriptPath "$SCRIPTS" \
      -preScript MakeFunctions.java $ENTRIES \
      || { echo "ghidra_export_functions: the import/analysis pass failed" >&2; exit 1; }
fi

for pass in 1 2; do
  run -process "$PROG" -scriptPath "$SCRIPTS" -preScript FindPointerTargets.java \
      || { echo "ghidra_export_functions: FindPointerTargets pass $pass failed" >&2; exit 1; }
done

run -process "$PROG" -scriptPath "$SCRIPTS" -postScript ExportPS2Functions.java "$(w "$TOML")" "$(w "$OUT")" \
    || { echo "ghidra_export_functions: the export pass failed" >&2; exit 1; }

[ -f "$OUT" ] || { echo "ghidra_export_functions: the export pass returned 0 but wrote no $OUT" >&2; exit 1; }
say "ghidra: $(( $(wc -l < "$OUT") - 1 )) rows in $OUT (+ $TOML); project kept in $PROJDIR"
