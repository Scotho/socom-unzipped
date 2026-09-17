#!/usr/bin/env bash
# Task 8b Step 5 / packaging outline section 2 A: the portable folder. Assembles <out>/socom2/ from dist/ --
# socom2.exe, socom2_game.elf, the DLLs, the launcher, README.txt, LICENSES/, empty cards/ and logs/ -- and zips
# it. No registry, no admin; the user points the launcher at their ISO once. Usage:
#   scripts/make_portable.sh [out dir]      (default: dist/portable)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
