#!/usr/bin/env bash
# Task 8b Step 5 / packaging outline section 2 A: the portable folder. Assembles <out>/socom2/ from dist/ --
# socom2.exe, socom2_game.elf, the DLLs, the launcher, README.txt, LICENSES/, empty cards/ and logs/ -- and zips
# it. No registry, no admin; the user points the launcher at their ISO once. Usage:
#   scripts/make_portable.sh [out dir]      (default: dist/portable, dist-linux/portable on Linux)
# Sprint 8 Goal 1 item 5: on Linux it assembles dist-linux/portable/socom2-linux/ instead -- the same three
# binaries with their executable bits, lib/ filled from ldd through scripts/portable_libs.py, and a .tar.gz
# instead of a zip. The Windows branch below is unchanged (its here-docs need column-0 terminators).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case "$(uname -s)" in
  Linux)
    # Sprint 8 Goal 1 item 5: the same folder as a tarball. dist-linux/ holds the native build;
    # socom2_game.elf is platform-neutral, so take dist/'s copy when only Windows has built it.
    DIST="${DIST:-$ROOT/dist}"
    LDIST="${LDIST:-$ROOT/dist-linux}"
    OUT="${1:-$LDIST/portable}"
    PKG="$OUT/socom2-linux"
    mkdir -p "$LDIST"
    if [ ! -f "$LDIST/socom2_game.elf" ] && [ -f "$DIST/socom2_game.elf" ]; then
      cp "$DIST/socom2_game.elf" "$LDIST/socom2_game.elf"
    fi
    for f in socom2 socom2_game.elf socom_unzipped_launcher; do
      [ -f "$LDIST/$f" ] || { echo "make_portable: $LDIST/$f missing -- run scripts/build_linux.sh first" >&2; exit 2; }
    done
    command -v ldd >/dev/null || { echo "make_portable: ldd not found" >&2; exit 2; }
    command -v python3 >/dev/null || { echo "make_portable: python3 not found (scripts/portable_libs.py)" >&2; exit 2; }
    rm -rf "$PKG"
    mkdir -p "$PKG/lib" "$PKG/cards" "$PKG/logs" "$PKG/LICENSES"
    # -p keeps the executable bits; the tarball must unpack runnable.
    cp -p "$LDIST/socom2" "$LDIST/socom2_game.elf" "$LDIST/socom_unzipped_launcher" "$PKG/"
    chmod +x "$PKG/socom2" "$PKG/socom_unzipped_launcher"
    # Every shared library the runner AND the launcher pull in, minus the host's own stack.
    # RPATH $ORIGIN/lib (set by CMake) is what finds these at run time.
    LDD_OUT="$(ldd "$LDIST/socom2"; ldd "$LDIST/socom_unzipped_launcher")"
    if MISSING="$(printf '%s\n' "$LDD_OUT" | python3 "$ROOT/scripts/portable_libs.py" --missing)"; then
      :
    else
      echo "make_portable: ldd cannot resolve these libraries -- install them and rebuild:" >&2
      printf '  %s\n' $MISSING >&2
      exit 3
    fi
    printf '%s\n' "$LDD_OUT" | python3 "$ROOT/scripts/portable_libs.py" > "$OUT/.libs.txt"
    while read -r so; do
      [ -n "$so" ] || continue
      cp -L "$so" "$PKG/lib/"
    done < "$OUT/.libs.txt"
    NLIBS="$(ls "$PKG/lib" | wc -l)"
    rm -f "$OUT/.libs.txt"
    cp "$ROOT/third_party/ps2recomp/LICENSE" "$PKG/LICENSES/PS2Recomp-GPL-3.0.txt"
    cat > "$PKG/LICENSES/README.txt" <<'LIC'
SOCOM Unzipped ships these components; their licence texts are the ones named here.
  socom2, socom2_game.elf, socom_unzipped_launcher -- the PS2Recomp fork: GPL-3.0 (PS2Recomp-GPL-3.0.txt)
  raylib (window, input, audio)                             -- zlib
  ffmpeg (avcodec/avformat/avutil/swscale/...)             -- LGPL-2.1-or-later, shared libraries, unmodified
  SDL2                                                      -- zlib
  OpenEXR, Imath, IlmThread, Iex                            -- BSD-3-Clause
  freetype                                                  -- FTL
  harfbuzz                                                  -- MIT
  brotli                                                    -- MIT
The libraries in lib/ carry their own licences from the distribution they were built by; glibc,
libstdc++, the OpenGL driver, X11 and the sound libraries are the host's and are not shipped.
The game's disc image is not included: point the launcher at your own SOCOM II (NTSC, r0001) ISO.
LIC
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
    rm -f "$OUT/socom2-linux.tar.gz"
    tar -C "$OUT" -czf "$OUT/socom2-linux.tar.gz" socom2-linux
    echo "portable folder: $PKG ($(ls "$PKG" | wc -l) entries, $NLIBS libraries in lib/), tarball: $OUT/socom2-linux.tar.gz ($(du -h "$OUT/socom2-linux.tar.gz" | cut -f1))"
    ;;
  *)
DIST="${DIST:-$ROOT/dist}"
OUT="${1:-$ROOT/dist/portable}"
PKG="$OUT/socom2"
for f in socom2.exe socom2_game.elf socom_unzipped_launcher.exe; do
  [ -f "$DIST/$f" ] || { echo "make_portable: $DIST/$f missing -- run ./build.sh runtime first" >&2; exit 2; }
done
rm -rf "$PKG"
mkdir -p "$PKG/cards" "$PKG/logs" "$PKG/LICENSES"
cp "$DIST/socom2.exe" "$DIST/socom2_game.elf" "$DIST/socom_unzipped_launcher.exe" "$PKG/"
cp "$DIST"/*.dll "$PKG/"
cp "$ROOT/third_party/ps2recomp/LICENSE" "$PKG/LICENSES/PS2Recomp-GPL-3.0.txt"
cat > "$PKG/LICENSES/README.txt" <<'LIC'
SOCOM Unzipped ships these components; their licence texts are the ones named here.
  socom2.exe, socom2_game.elf, socom_unzipped_launcher.exe -- the PS2Recomp fork: GPL-3.0 (PS2Recomp-GPL-3.0.txt)
  raylib (window, input, audio)                             -- zlib
  ffmpeg (avcodec/avformat/avutil/swscale/...)             -- LGPL-2.1-or-later, shared libraries, unmodified
  SDL2                                                      -- zlib
  OpenEXR, Imath, IlmThread, Iex                            -- BSD-3-Clause
  freetype                                                  -- FTL
  harfbuzz                                                  -- MIT
  brotli                                                    -- MIT
  libc++, libunwind, libwinpthread                          -- Apache-2.0 with LLVM exception / MIT
The game's disc image is not included: point the launcher at your own SOCOM II (NTSC, r0001) ISO.
LIC
cat > "$PKG/README.txt" <<'RD'
SOCOM Unzipped -- SOCOM II: U.S. Navy SEALs on PC

1. Run socom_unzipped_launcher.exe.
2. Point it at your SOCOM II ISO (NTSC, SCUS-97275 r0001). The launcher checks the disc and says so.
3. Pick the video size and quality, plug in a controller (the test area shows what the game will see), press Launch.

Online: enter the server address in the launcher's Online panel; your profile name picks the memory card
directory under cards/. Logs land in logs/ -- send the newest run_*.log with any report.
Everything lives in this folder; delete it to uninstall.
RD
( cd "$OUT" && rm -f socom2-portable.zip && powershell -NoProfile -Command "Compress-Archive -Path 'socom2' -DestinationPath 'socom2-portable.zip' -Force" )
echo "portable folder: $PKG ($(ls "$PKG" | wc -l) entries), zip: $OUT/socom2-portable.zip"
    ;;
esac
