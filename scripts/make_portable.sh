#!/usr/bin/env bash
# Task 8b Step 5 / packaging outline section 2 A: the portable folder. Assembles <out>/socom2/ from dist/ --
# socom2.exe, socom2_game.elf, the DLLs, the launcher, README.txt, LICENSES/, empty cards/ and logs/ -- and zips
# it. No registry, no admin; the user points the launcher at their ISO once. Usage:
#   scripts/make_portable.sh [--release] [out dir]   (default: dist/portable, dist-linux/portable on Linux;
#                                                     --release: dist-release/portable, dist-linux-release/portable)
# Sprint 9 Goal 2: the folder carries the import closure of socom2 and the launcher and nothing else
# (tools_py/portable_audit.py: closure, then an audit of what was assembled -- exit 4 on a finding), and
# SHA256SUMS is written beside the archive. Exit 2 = no build, 3 = an imported library is nowhere,
# 4 = the folder failed its import audit, 5 = the folder failed the leak check (Sprint 10 H6).
# Sprint 8 Goal 1 item 5: on Linux it assembles dist-linux/portable/socom2-linux/ instead -- the same three
# binaries with their executable bits, lib/ filled from ldd through scripts/portable_libs.py, and a .tar.gz
# instead of a zip. The Windows branch below is unchanged (its here-docs need column-0 terminators).
# Sprint 10 Q7: the Linux branch takes its platform from MAKE_PORTABLE_SYSTEM (default `uname -s`) and its ldd
# from LDD, so tools_py/tests/test_make_portable_linux.py can drive it on the Windows host with a synthetic
# dist-linux/ and an ldd that answers for it; a real run sets neither. The interpreter is $PYTHON like
# everywhere else (scripts/python_env.sh) -- there was a second rule here, PYTHON3, and it disagreed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/scripts/python_env.sh"   # $PYTHON, resolved once for every script
socom_require_python make_portable
SUFFIX=""
if [ "${1:-}" = "--release" ]; then SUFFIX="-release"; shift; fi
AUDIT="$ROOT/tools_py/portable_audit.py"
PY="$PYTHON"
case "${MAKE_PORTABLE_SYSTEM:-$(uname -s)}" in
  Linux)
    LDD="${LDD:-ldd}"
    # Sprint 8 Goal 1 item 5: the same folder as a tarball. dist-linux/ holds the native build;
    # socom2_game.elf is platform-neutral, so take dist/'s copy when only Windows has built it.
    DIST="${DIST:-$ROOT/dist}"
    LDIST="${LDIST:-$ROOT/dist-linux$SUFFIX}"
    OUT="${1:-$LDIST/portable}"
    PKG="$OUT/socom2-linux"
    mkdir -p "$LDIST"
    if [ ! -f "$LDIST/socom2_game.elf" ] && [ -f "$DIST/socom2_game.elf" ]; then
      cp "$DIST/socom2_game.elf" "$LDIST/socom2_game.elf"
    fi
    for f in socom2 socom2_game.elf socom_unzipped_launcher; do
      [ -f "$LDIST/$f" ] || { echo "make_portable: $LDIST/$f missing -- run scripts/build_linux.sh first${SUFFIX:+ (or scripts/build_linux.sh release)}" >&2; exit 2; }
    done
    command -v "$LDD" >/dev/null || { echo "make_portable: ldd not found" >&2; exit 2; }
    rm -rf "$PKG"
    mkdir -p "$PKG/lib" "$PKG/cards" "$PKG/logs" "$PKG/LICENSES"
    # -p keeps the executable bits; the tarball must unpack runnable.
    cp -p "$LDIST/socom2" "$LDIST/socom2_game.elf" "$LDIST/socom_unzipped_launcher" "$PKG/"
    chmod +x "$PKG/socom2" "$PKG/socom_unzipped_launcher"
    # Sprint 9 Goal 1: the launcher's About page and its diagnostics zip read version.txt; until now nothing wrote it.
    printf 'SOCOM Unzipped %s (%s)\n' "$(git -C "$ROOT" describe --always --dirty 2>/dev/null || echo unknown)" "$(date -u +%Y-%m-%d)" > "$PKG/version.txt"
    # Every shared library the runner AND the launcher pull in, minus the host's own stack.
    # RPATH $ORIGIN/lib (set by CMake) is what finds these at run time.
    LDD_OUT="$("$LDD" "$LDIST/socom2"; "$LDD" "$LDIST/socom_unzipped_launcher")"
    if MISSING="$(printf '%s\n' "$LDD_OUT" | "$PY" "$ROOT/scripts/portable_libs.py" --missing)"; then
      :
    else
      echo "make_portable: ldd cannot resolve these libraries -- install them and rebuild:" >&2
      printf '  %s\n' $MISSING >&2
      exit 3
    fi
    # The executables are the roots of the walk: a library is carried only when they reach it through
    # libraries we carry ourselves (ldd's flat list also names what only a host library needs -- libXau).
    # (tr: a Windows python prints CRLF, and the test drives this branch there -- as the Windows branch's NEEDED.)
    printf '%s\n' "$LDD_OUT" | "$PY" "$ROOT/scripts/portable_libs.py" \
      "$LDIST/socom2" "$LDIST/socom_unzipped_launcher" | tr -d '\r' > "$OUT/.libs.txt"
    while read -r so; do
      [ -n "$so" ] || continue
      cp -L "$so" "$PKG/lib/"
    done < "$OUT/.libs.txt"
    NLIBS="$(ls "$PKG/lib" | wc -l)"
    rm -f "$OUT/.libs.txt"
    # Sprint 10 H5: the inventory is THIRD_PARTY_NOTICES.md at the root (tools_py/tests/test_third_party_notices.py keeps
    # it complete) and the licence texts are LICENSES/<SPDX id>.txt; both ship as they are.
    cp "$ROOT/THIRD_PARTY_NOTICES.md" "$PKG/"
    cp "$ROOT"/LICENSES/*.txt "$PKG/LICENSES/"
    cat > "$PKG/README.txt" <<'RD'
SOCOM Unzipped -- SOCOM II: U.S. Navy SEALs on PC (Linux)

1. Open a terminal in this folder and run ./socom_unzipped_launcher
2. Point it at your SOCOM II ISO (NTSC, SCUS-97275 r0001). The launcher checks the disc and says so.
3. Pick the video size and quality, plug in a controller (the test area shows what the game will see), press Launch.

What your machine must already have: a working OpenGL driver (the distribution's mesa or the vendor's),
PulseAudio or ALSA for sound, and the distribution's libstdc++ (every desktop distribution ships it; shipping
our own would break your GL driver). Everything else the game needs is in lib/ next to the binaries.
Optional: zenity for the launcher's file picker -- without it, type the ISO path into the field.

Online: enter the server address in the launcher's Online panel; your profile name picks the memory card
directory under cards/. Logs land in logs/ -- send the newest run_*.log with any report.
Nothing is installed and nothing is written outside this folder; delete the folder to remove it.
RD
    "$PY" "$AUDIT" audit "$PKG" --system Linux || { echo "make_portable: the assembled folder failed its audit" >&2; exit 4; }
    ( cd "$ROOT" && "$PY" -m tools_py.release.leakcheck artifact "$PKG" ) \
      || { echo "make_portable: the assembled folder failed the leak check (exit $?) -- nothing archived" >&2; exit 5; }
    rm -f "$OUT/socom2-linux.tar.gz" "$OUT/SHA256SUMS"
    # (from inside OUT: a drive-letter path after -f reads as a remote host to GNU tar on the Windows host.)
    ( cd "$OUT" && tar -czf socom2-linux.tar.gz socom2-linux )
    "$PY" "$AUDIT" sha256sums "$OUT" socom2-linux.tar.gz >/dev/null
    echo "portable folder: $PKG ($(ls "$PKG" | wc -l) entries, $NLIBS libraries in lib/), tarball: $OUT/socom2-linux.tar.gz ($(wc -c < "$OUT/socom2-linux.tar.gz") bytes), $OUT/SHA256SUMS"
    ;;
  *)
DIST="${DIST:-$ROOT/dist$SUFFIX}"
OUT="${1:-$ROOT/dist$SUFFIX/portable}"
PY="$PYTHON"
PKG="$OUT/socom2"
for f in socom2.exe socom2_game.elf socom_unzipped_launcher.exe; do
  [ -f "$DIST/$f" ] || { echo "make_portable: $DIST/$f missing -- run ./build.sh runtime first${SUFFIX:+ (or ./build.sh release)}" >&2; exit 2; }
done
rm -rf "$PKG"
mkdir -p "$PKG/cards" "$PKG/logs" "$PKG/LICENSES"
cp "$DIST/socom2.exe" "$DIST/socom2_game.elf" "$DIST/socom_unzipped_launcher.exe" "$PKG/"
# Sprint 9 Goal 2: only what the two executables reach through their import tables (16 of dist/'s 31 DLLs on
# 2026-09-19 -- the rest is the FFmpeg zip's whole bin/ and a libwinpthread nothing imports).
if NEEDED="$("$PY" "$AUDIT" closure --system Windows --dir "$DIST" "$DIST/socom2.exe" "$DIST/socom_unzipped_launcher.exe")"; then
  :
else
  echo "make_portable: an imported library is neither in $DIST nor part of Windows (see above)" >&2
  exit 3
fi
printf '%s\n' "$NEEDED" | tr -d '\r' | while read -r dll; do
  [ -n "$dll" ] || continue
  cp "$DIST/$dll" "$PKG/"
done
# Sprint 9 Goal 1: the launcher's About page and its diagnostics zip read version.txt; until now nothing wrote it.
printf 'SOCOM Unzipped %s (%s)\n' "$(git -C "$ROOT" describe --always --dirty 2>/dev/null || echo unknown)" "$(date -u +%Y-%m-%d)" > "$PKG/version.txt"
# Sprint 10 H5: the inventory is THIRD_PARTY_NOTICES.md at the root (tools_py/tests/test_third_party_notices.py keeps
# it complete) and the licence texts are LICENSES/<SPDX id>.txt; both ship as they are.
cp "$ROOT/THIRD_PARTY_NOTICES.md" "$PKG/"
cp "$ROOT"/LICENSES/*.txt "$PKG/LICENSES/"
cat > "$PKG/README.txt" <<'RD'
SOCOM Unzipped -- SOCOM II: U.S. Navy SEALs on PC

1. Run socom_unzipped_launcher.exe.
2. Point it at your SOCOM II ISO (NTSC, SCUS-97275 r0001). The launcher checks the disc and says so.
3. Pick the video size and quality, plug in a controller (the test area shows what the game will see), press Launch.

Online: enter the server address in the launcher's Online panel; your profile name picks the memory card
directory under cards/. Logs land in logs/ -- send the newest run_*.log with any report.
Everything lives in this folder; delete it to uninstall.
RD
"$PY" "$AUDIT" audit "$PKG" --system Windows || { echo "make_portable: the assembled folder failed its audit" >&2; exit 4; }
( cd "$ROOT" && "$PY" -m tools_py.release.leakcheck artifact "$PKG" ) \
  || { echo "make_portable: the assembled folder failed the leak check (exit $?) -- nothing archived" >&2; exit 5; }
( cd "$OUT" && rm -f socom2-portable.zip SHA256SUMS && powershell -NoProfile -Command "Compress-Archive -Path 'socom2' -DestinationPath 'socom2-portable.zip' -Force" )
"$PY" "$AUDIT" sha256sums "$OUT" socom2-portable.zip >/dev/null
echo "portable folder: $PKG ($(ls "$PKG" | wc -l) entries), zip: $OUT/socom2-portable.zip ($(wc -c < "$OUT/socom2-portable.zip") bytes), $OUT/SHA256SUMS"
    ;;
esac
