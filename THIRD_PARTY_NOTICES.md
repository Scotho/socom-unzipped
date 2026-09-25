# Third-party notices

SOCOM Unzipped is built on the work below. The project's own code is GPL-3.0 (`LICENSE` at the root: the vendored
recompiler is GPL-3.0 and the executable links it). Every licence text named in the **Licence** column is under
`LICENSES/<id>.txt` (the SPDX id, verbatim; a `LicenseRef-` id is a text SPDX does not list, quoted from its
source); the copyright holders are given here. This file ships inside every release archive beside `LICENSES/`, and
`tools_py/tests/test_third_party_notices.py` fails when a dependency the build fetches, a directory vendored under
`third_party/` or `server/`, a DLL in the release folder, or a library in the Linux tarball's `lib/` has no row.
Every fetched dependency is pinned to bytes -- a commit or a SHA-256 -- and `tools_py/tests/test_supply_chain_pins.py`
fails on one that is not (Sprint 13 C6).

SOCOM, SOCOM II: U.S. Navy SEALs, PlayStation and PS2 are trademarks of Sony Interactive Entertainment. Zipper
Interactive made the game. This project is not affiliated with or endorsed by either. **No game code or game data
is in this repository or in the download**; the player supplies their own disc.

## Vendored in the tree

| Component | Where | Version | Licence | Copyright | Ships |
|---|---|---|---|---|---|
| PS2Recomp (ps2xRecomp, ps2xRuntime, ps2xAnalyzer, ps2xIOP, ps2xShared, ps2xTest, ps2xLauncher) | `third_party/ps2recomp/` | fork of ran-j/PS2Recomp at upstream `14b1e5c` (#214, 2026-08-19; vendored 2026-09-04 as `8736759`), heavily modified; upstream since the base is the single squash commit `75d729c` (#244), see `docs/research/40-upstream-divergence.md`; the save-state container (`ps2xRuntime/.../ps2_save_state.*`) takes its byte format and API from the MrCoolTheCucumber/PS2Recomp fork at `7978365`, see `docs/research/41-cucumber-fork.md` | GPL-3.0-only | ran-j and PS2Recomp contributors; MrCoolTheCucumber; SOCOM Unzipped contributors | yes (the executables) |
| Horizon Server (Medius/DME/NAT/MUIS for the PS2 online stack) | `server/horizon-server/` | fork, app id 10472 configuration | MIT | 2020 Daniel Gerendasy | no (the hosted box runs it) |
| HighResolutionTimer | `server/horizon-server/HighResolutionTimer/` | as vendored by Horizon | MIT | 2020 Hakan Lindestaf | no |
| Saira Stencil One (font) | `third_party/ps2recomp/ps2xLauncher/assets/fonts/` | 2019 | OFL-1.1 | 2019 The Saira Stencil Project Authors (Omnibus-Type) | yes (embedded in the launcher at build time by `scripts/embed_font.py`) |
| Rajdhani (font) | `third_party/ps2recomp/ps2xLauncher/assets/fonts/` | 2014 | OFL-1.1 | 2014 Indian Type Foundry | yes (embedded in the launcher at build time by `scripts/embed_font.py`) |

## Fetched at configure time (CMake FetchContent / ExternalProject)

| Component | Declared in | Version | Licence | Copyright | Ships |
|---|---|---|---|---|---|
| raylib (window, input, audio device; bundles miniaudio, glfw, stb) | `ps2xRuntime/CMakeLists.txt` | 5.5 at `c1ab645ca298` | Zlib | 2013-2024 Ramon Santamaria (@raysan5) | yes (static) |
| Dear ImGui | `ps2xRuntime/CMakeLists.txt` | v1.92.7-docking at `b1bcb12a624a` | MIT | 2014-2026 Omar Cornut | yes (static; the debug UI) |
| rlImGui | `ps2xRuntime/CMakeLists.txt` | Raylib_5_5 at `118221c8a532` | Zlib | 2020-2021 Jeffery Myers | yes (static) |
| FFmpeg (libavcodec, libavutil, libswresample, libswscale; the LGPL build, configured `--enable-version3`) | `ps2xRuntime/CMakeLists.txt` | 7.1.5 (`ffmpeg-7.1.5` of System233/ffmpeg-msvc-prebuilt, vcpkg's shared LGPL build, 2026-06-27; SHA-256 `6c9fcb0ef313...e95c`) | LGPL-3.0-or-later | the FFmpeg developers | yes (`avcodec-61.dll`, `avutil-59.dll`, `swresample-5.dll`, `swscale-8.dll`) |
| ELFIO | `ps2xRecomp/CMakeLists.txt` | Release_3.12 at `8ae6cec5d604` | MIT | 2001-present Serge Lamikhov-Center | no (the recompiler, a build tool) |
| toml11 | `ps2xRecomp/CMakeLists.txt` | v4.4.0 at `be08ba2be2a9` | MIT | 2017 Toru Niina | no (build tool) |
| {fmt} | `ps2xRecomp/CMakeLists.txt` | 12.1.0 at `407c905e45ad` | MIT | 2012-present Victor Zverovich and {fmt} contributors | no (build tool) |
| libdwarf | `ps2xRecomp/CMakeLists.txt` | v2.2.0 at `2e088b983562` | LGPL-2.1-or-later | David Anderson and contributors | no (build tool) |
| rabbitizer | `ps2xRecomp/CMakeLists.txt` | 1.14.3 at `d5804fa48847` | MIT | 2022 Decompollaborate | no (build tool) |
| nlohmann/json | `ps2xAnalyzer/CMakeLists.txt` | v3.11.3 at `9cca280a4d0c` | MIT | 2013-2022 Niels Lohmann | no (build tool) |
| sse2neon | `third_party/ps2recomp/CMakeLists.txt` | v1.9.1 at `92f6de174717` | MIT | DLTcollab and contributors | no (ARM builds only) |

The commit column is abbreviated; the CMake files carry the full 40-hex commit with the tag's name beside it.

## Inside the FFmpeg DLLs (linked statically by the prebuilt; Windows)

Since 7.1.5 the prebuilt links its codecs into the FFmpeg DLLs rather than shipping them as DLLs of their own, so
the release carries these inside the four DLLs above. The list is each DLL's `Libs.private` in the archive's
`lib/pkgconfig/*.pc`; the versions are vcpkg's at the build (the archive's `share/ffmpeg/vcpkg_abi_info.txt`).
`avformat-61.dll`, `avfilter-10.dll` and `avdevice-61.dll` are copied into the developer `dist/` beside them and are
not in the release closure (`socom2.exe` imports avcodec, avutil and swscale; avcodec imports swresample); what is
linked inside those three (OpenSSL, libxml2, libssh, SRT, ZeroMQ, FreeType, HarfBuzz, SDL2, ...) is listed by
their own `.pc` files and is not distributed.

| Component | Where | Version | Licence | Copyright | Ships |
|---|---|---|---|---|---|
| libaom | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-2-Clause | the Alliance for Open Media | yes (inside `avcodec-61.dll`) |
| dav1d | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-2-Clause | VideoLAN and the dav1d authors | yes (inside `avcodec-61.dll`) |
| OpenH264 | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-2-Clause | Cisco Systems, Inc. | yes (inside `avcodec-61.dll`) |
| OpenJPEG | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-2-Clause | Universite catholique de Louvain and the OpenJPEG contributors | yes (inside `avcodec-61.dll`) |
| libvpx | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause | the WebM project authors (Google) | yes (inside `avcodec-61.dll`) |
| libwebp (webp, webpmux, sharpyuv) | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause | Google Inc. | yes (inside `avcodec-61.dll`) |
| libjxl (jxl, jxl_cms, jxl_threads) | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause | the JPEG XL Project Authors | yes (inside `avcodec-61.dll`) |
| Highway | the FFmpeg prebuilt | as bundled (vcpkg) | Apache-2.0 OR BSD-3-Clause | Google LLC | yes (inside `avcodec-61.dll`) |
| Little CMS | the FFmpeg prebuilt | as bundled (vcpkg) | MIT | Marti Maria Saguer | yes (inside `avcodec-61.dll`) |
| Brotli | the FFmpeg prebuilt | as bundled (vcpkg) | MIT | the Brotli Authors | yes (inside `avcodec-61.dll`) |
| zlib | the FFmpeg prebuilt | as bundled (vcpkg) | Zlib | Jean-loup Gailly and Mark Adler | yes (inside `avcodec-61.dll`) |
| liblzma (XZ Utils) | the FFmpeg prebuilt | as bundled (vcpkg) | 0BSD | Lasse Collin and the XZ Utils authors | yes (inside `avcodec-61.dll`) |
| Snappy | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause | Google Inc. | yes (inside `avcodec-61.dll`) |
| libogg, libvorbis, libtheora | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause | the Xiph.Org Foundation | yes (inside `avcodec-61.dll`) |
| Opus | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause | Xiph.Org, Skype Limited, Octasic, Jean-Marc Valin, Timothy B. Terriberry, CSIRO and others | yes (inside `avcodec-61.dll`) |
| Speex | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause | the Xiph.Org Foundation, Jean-Marc Valin and the Speex authors | yes (inside `avcodec-61.dll`) |
| libilbc | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause | The WebRTC project authors | yes (inside `avcodec-61.dll`) |
| FAST corner detector (fastfeat) | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause | Edward Rosten | yes (inside `avcodec-61.dll`) |
| SVT-AV1 | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause-Clear | the Alliance for Open Media and Intel Corporation | yes (inside `avcodec-61.dll`) |
| VVenC | the FFmpeg prebuilt | as bundled (vcpkg) | BSD-3-Clause-Clear | Fraunhofer-Gesellschaft (Fraunhofer HHI) | yes (inside `avcodec-61.dll`) |
| LAME (with its mpglib/hip decoder) | the FFmpeg prebuilt | as bundled (vcpkg) | LGPL-2.0-or-later | the LAME developers | yes (inside `avcodec-61.dll`) |
| GNU libiconv | the FFmpeg prebuilt | as bundled (vcpkg) | LGPL-2.1-or-later | Free Software Foundation, Inc. | yes (inside `avcodec-61.dll`) |
| OpenSSL | the FFmpeg prebuilt | as bundled (vcpkg) | Apache-2.0 | The OpenSSL Project Authors | yes (inside `avutil-59.dll`) |
| OpenCL ICD Loader | the FFmpeg prebuilt | as bundled (vcpkg) | Apache-2.0 | The Khronos Group Inc. | yes (inside `avutil-59.dll`) |
| libsoxr | the FFmpeg prebuilt | as bundled (vcpkg) | LGPL-2.1-or-later | Rob Sykes | yes (inside `swresample-5.dll`) |

## The Linux tarball's `lib/` (Ubuntu 24.04's FFmpeg and what it loads)

`scripts/make_portable.sh` on Linux copies into `socom2-linux/lib/` the shared libraries the binaries load, walked
from the executables through `DT_NEEDED` and stopped at the host's own stack (`scripts/portable_libs.py`: glibc, the
compiler runtime, GL, X11/Wayland, ALSA/PulseAudio, VA-API/VDPAU/DRM stay the player's). Those libraries are
Ubuntu 24.04's builds: the FFmpeg family at 7:6.1.1-3ubuntu5 (`.github/workflows/linux.yml` pins it) and what it
depends on. Ubuntu builds FFmpeg with `--enable-gpl` and links x264, x265 and Xvid, so the libav* in this tarball
are GPL-2.0-or-later as combined (the project's own GPL-3.0 is compatible). The rows are per Ubuntu source package;
the licence is the library's as the package's `debian/copyright` states it, in SPDX terms. The list is the
package-level closure (`tools_py/tests/fixtures/linux_tarball_lib.txt` says how it was read), a superset of what one
build's `lib/` holds; the versions are those in the noble archive on 2026-09-25, and a library's source is Ubuntu's
source package of that version.

| Component | Where | Version | Licence | Copyright | Ships |
|---|---|---|---|---|---|
| Brotli | Ubuntu 24.04 `brotli` | 1.1.0-2build2 | MIT | the Brotli Authors | yes (`libbrotlicommon.so.1`, `libbrotlidec.so.1`, `libbrotlienc.so.1`) |
| bzip2 | Ubuntu 24.04 `bzip2` | 1.0.8-5.1ubuntu0.1 | bzip2-1.0.6 | 1996-2019 Julian R Seward | yes (`libbz2.so.1`) |
| cairo | Ubuntu 24.04 `cairo` | 1.18.0-3build1 | LGPL-2.1-only OR MPL-1.1 | the cairo authors (Carl Worth, Keith Packard and others) | yes (`libcairo-gobject.so.2`, `libcairo.so.2`) |
| Chromaprint | Ubuntu 24.04 `chromaprint` | 1.5.1-5 | MIT AND LGPL-2.1-or-later | 2010-2019 Lukas Lalinsky | yes (`libchromaprint.so.1`) |
| cJSON | Ubuntu 24.04 `cjson` | 1.7.17-1 | MIT | 2009-2017 Dave Gamble and cJSON contributors | yes (`libcjson.so.1`, `libcjson_utils.so.1`) |
| codec2 | Ubuntu 24.04 `codec2` | 1.2.0-2build1 | LGPL-2.1-only | David Rowe and the codec2 contributors | yes (`libcodec2.so.1.2`) |
| dav1d | Ubuntu 24.04 `dav1d` | 1.4.1-1build1 | BSD-2-Clause | VideoLAN and the dav1d authors | yes (`libdav1d.so.7`) |
| Expat | Ubuntu 24.04 `expat` | 2.6.1-2ubuntu0.6 | MIT | Thai Open Source Software Center Ltd, Clark Cooper and the Expat maintainers | yes (`libexpat.so.1`, `libexpatw.so.1`) |
| FFmpeg (Ubuntu's build, configured --enable-gpl) | Ubuntu 24.04 `ffmpeg` | 7:6.1.1-3ubuntu5 | LGPL-2.1-or-later AND GPL-2.0-or-later | the FFmpeg developers | yes (`libavcodec.so.60`, `libavformat.so.60`, `libavutil.so.58`, `libswresample.so.4`, `libswscale.so.7`) |
| Fontconfig | Ubuntu 24.04 `fontconfig` | 2.15.0-1.1ubuntu2 | HPND-sell-variant | Keith Packard and the Fontconfig authors | yes (`libfontconfig.so.1`) |
| FreeType | Ubuntu 24.04 `freetype` | 2.13.2+dfsg-1ubuntu0.1 | FTL OR GPL-2.0-only | The FreeType Project (David Turner, Robert Wilhelm, Werner Lemberg) | yes (`libfreetype.so.6`) |
| Game_Music_Emu | Ubuntu 24.04 `game-music-emu` | 0.6.3-7build1 | LGPL-2.1-or-later | Shay Green and the Game_Music_Emu authors | yes (`libgme.so.0`) |
| GdkPixbuf | Ubuntu 24.04 `gdk-pixbuf` | 2.42.10+dfsg-3ubuntu3.3 | LGPL-2.0-or-later | the gdk-pixbuf authors (the GNOME Project) | yes (`libgdk_pixbuf-2.0.so.0`) |
| GLib | Ubuntu 24.04 `glib2.0` | 2.80.0-6ubuntu3.9 | LGPL-2.1-or-later | the GLib authors (the GNOME Project) | yes (`libgio-2.0.so.0`, `libglib-2.0.so.0`, `libgmodule-2.0.so.0`, `libgobject-2.0.so.0`, `libgthread-2.0.so.0`) |
| GMP | Ubuntu 24.04 `gmp` | 2:6.3.0+dfsg-2ubuntu6.1 | LGPL-3.0-or-later OR GPL-2.0-or-later | Free Software Foundation, Inc. | yes (`libgmp.so.10`) |
| GNU FriBidi | Ubuntu 24.04 `fribidi` | 1.0.13-3build1 | LGPL-2.1-or-later | the GNU FriBidi authors | yes (`libfribidi.so.0`) |
| GNU Libtasn1 | Ubuntu 24.04 `libtasn1-6` | 4.19.0-3ubuntu0.24.04.2 | LGPL-2.1-or-later | Free Software Foundation, Inc. | yes (`libtasn1.so.6`) |
| GNU libunistring | Ubuntu 24.04 `libunistring` | 1.1-2build1.1 | LGPL-3.0-or-later OR GPL-2.0-or-later | Free Software Foundation, Inc. | yes (`libunistring.so.5`) |
| GnuTLS | Ubuntu 24.04 `gnutls28` | 3.8.3-1.1ubuntu3.6 | LGPL-2.1-or-later | Free Software Foundation, Inc. and the GnuTLS authors | yes (`libgnutls.so.30`) |
| Graphite2 | Ubuntu 24.04 `graphite2` | 1.3.14-2ubuntu0.24.04.1 | LGPL-2.1-or-later OR MPL-1.1 OR GPL-2.0-or-later | SIL International | yes (`libgraphite2.so.3`) |
| HarfBuzz | Ubuntu 24.04 `harfbuzz` | 8.3.0-2build2 | MIT-Modern-Variant | the HarfBuzz contributors | yes (`libharfbuzz.so.0`) |
| Highway | Ubuntu 24.04 `highway` | 1.0.7-8.1build1 | Apache-2.0 | Google LLC | yes (`libhwy.so.1`, `libhwy_contrib.so.1`, `libhwy_test.so.1`) |
| ICU | Ubuntu 24.04 `icu` | 74.2-1ubuntu3.1 | Unicode-3.0 | Unicode, Inc. and others | yes (`libicudata.so.74`, `libicui18n.so.74`, `libicuio.so.74`, `libicutest.so.74`, `libicutu.so.74`, `libicuuc.so.74`) |
| JBIG-KIT | Ubuntu 24.04 `jbigkit` | 2.1-6.1ubuntu2 | GPL-2.0-or-later | Markus Kuhn | yes (`libjbig.so.0`) |
| LAME | Ubuntu 24.04 `lame` | 3.100-6build1 | LGPL-2.0-or-later | the LAME developers | yes (`libmp3lame.so.0`) |
| LERC | Ubuntu 24.04 `lerc` | 4.0.0+ds-4ubuntu2 | Apache-2.0 | Esri | yes (`libLerc.so.4`) |
| libaom (AV1) | Ubuntu 24.04 `aom` | 3.8.2-2ubuntu0.2 | BSD-2-Clause | the Alliance for Open Media | yes (`libaom.so.3`) |
| libblkid, libmount (util-linux) | Ubuntu 24.04 `util-linux` | 2.39.3-9ubuntu6.6 | LGPL-2.1-or-later | the util-linux authors | yes (`libblkid.so.1`, `libmount.so.1`) |
| libbluray | Ubuntu 24.04 `libbluray` | 1:1.3.4-1build1 | LGPL-2.1-or-later | the libbluray authors (VideoLAN) | yes (`libbluray.so.2`) |
| libbsd | Ubuntu 24.04 `libbsd` | 0.12.1-1build1.1 | BSD-3-Clause | the libbsd authors (Guillem Jover and others) | yes (`libbsd.so.0`) |
| libcom_err (e2fsprogs) | Ubuntu 24.04 `e2fsprogs` | 1.47.0-2.4~exp1ubuntu4.1 | MIT | 1987-1988 the Student Information Processing Board of MIT | yes (`libcom_err.so.2`) |
| libdatrie | Ubuntu 24.04 `libdatrie` | 0.2.13-3build1 | LGPL-2.1-or-later | Theppitak Karoonboonyanan | yes (`libdatrie.so.1`) |
| libdeflate | Ubuntu 24.04 `libdeflate` | 1.19-1build1.1 | MIT | Eric Biggers | yes (`libdeflate.so.0`) |
| libffi | Ubuntu 24.04 `libffi` | 3.4.6-1build1 | MIT | Anthony Green, Red Hat, Inc and others | yes (`libffi.so.8`) |
| Libgcrypt | Ubuntu 24.04 `libgcrypt20` | 1.10.3-2ubuntu0.2 | LGPL-2.1-or-later | Free Software Foundation, Inc. and g10 Code GmbH | yes (`libgcrypt.so.20`) |
| libgomp (GCC) | Ubuntu 24.04 `gcc-14` | 14.2.0-4ubuntu2~24.04.1 | GPL-3.0-or-later WITH GCC-exception-3.1 | Free Software Foundation, Inc. | yes (`libgomp.so.1`) |
| libgpg-error | Ubuntu 24.04 `libgpg-error` | 1.47-3build2.1 | LGPL-2.1-or-later | g10 Code GmbH and the libgpg-error authors | yes (`libgpg-error.so.0`) |
| libgsm | Ubuntu 24.04 `libgsm` | 1.0.22-1build1 | TU-Berlin-2.0 | 1992-1994 Jutta Degener and Carsten Bormann, Technische Universitaet Berlin | yes (`libgsm.so.1`) |
| Libidn2 | Ubuntu 24.04 `libidn2` | 2.3.7-2build1.1 | LGPL-3.0-or-later OR GPL-2.0-or-later | Simon Josefsson and Tim Ruehsen | yes (`libidn2.so.0`) |
| libjpeg-turbo | Ubuntu 24.04 `libjpeg-turbo` | 2.1.5-2ubuntu2 | IJG AND BSD-3-Clause AND Zlib | the Independent JPEG Group; D. R. Commander and the libjpeg-turbo authors | yes (`libjpeg.so.8`) |
| libjxl | Ubuntu 24.04 `jpeg-xl` | 0.7.0-10.2ubuntu6.1 | BSD-3-Clause | the JPEG XL Project Authors | yes (`libjxl.so.0.7`, `libjxl_threads.so.0.7`) |
| libkeyutils | Ubuntu 24.04 `keyutils` | 1.6.3-3build1 | LGPL-2.0-or-later | Red Hat, Inc. (David Howells) | yes (`libkeyutils.so.1`) |
| liblzma (XZ Utils 5.4.5) | Ubuntu 24.04 `xz-utils` | 5.6.1+really5.4.5-1ubuntu0.3 | LicenseRef-Public-Domain | Lasse Collin and the XZ Utils authors (placed in the public domain) | yes (`liblzma.so.5`) |
| libmd | Ubuntu 24.04 `libmd` | 1.1.0-2build1.1 | BSD-3-Clause | the libmd authors (Guillem Jover and others) | yes (`libmd.so.0`) |
| libnuma | Ubuntu 24.04 `numactl` | 2.0.18-1ubuntu0.24.04.1 | LGPL-2.1-only | Silicon Graphics, Inc.; Andi Kleen, SUSE Labs | yes (`libnuma.so.1`) |
| libogg | Ubuntu 24.04 `libogg` | 1.3.5-3build1 | BSD-3-Clause | the Xiph.Org Foundation | yes (`libogg.so.0`) |
| libopenmpt | Ubuntu 24.04 `libopenmpt` | 0.7.3-1.1build3 | BSD-3-Clause | OpenMPT Project Developers and Contributors | yes (`libopenmpt.so.0`) |
| libpng | Ubuntu 24.04 `libpng1.6` | 1.6.43-5ubuntu0.6 | libpng-2.0 | The PNG Reference Library Authors | yes (`libpng16.so.16`) |
| librist | Ubuntu 24.04 `librist` | 0.2.10+dfsg-2 | BSD-2-Clause | the librist authors (SipRadius LLC and others) | yes (`librist.so.4`) |
| librsvg | Ubuntu 24.04 `librsvg` | 2.58.0+dfsg-1build1 | LGPL-2.0-or-later | the librsvg authors (the GNOME Project) | yes (`librsvg-2.so.2`) |
| libselinux | Ubuntu 24.04 `libselinux` | 3.5-2ubuntu2.1 | LicenseRef-Public-Domain | the SELinux project (placed in the public domain) | yes (`libselinux.so.1`) |
| libsodium | Ubuntu 24.04 `libsodium` | 1.0.18-1ubuntu0.24.04.1 | ISC | Frank Denis | yes (`libsodium.so.23`) |
| libsoxr | Ubuntu 24.04 `libsoxr` | 0.1.3-4build3 | LGPL-2.1-or-later | Rob Sykes | yes (`libsoxr.so.0`) |
| libssh | Ubuntu 24.04 `libssh` | 0.10.6-2ubuntu0.5 | LGPL-2.1-or-later | the libssh team | yes (`libssh-gcrypt.so.4`) |
| libthai | Ubuntu 24.04 `libthai` | 0.1.29-2build1 | LGPL-2.1-or-later | Theppitak Karoonboonyanan and the libthai authors | yes (`libthai.so.0`) |
| libtheora | Ubuntu 24.04 `libtheora` | 1.1.1+dfsg.1-16.1build3 | BSD-3-Clause | the Xiph.Org Foundation | yes (`libtheora.so.0`, `libtheoradec.so.1`, `libtheoraenc.so.1`) |
| LibTIFF | Ubuntu 24.04 `tiff` | 4.5.1+git230720-4ubuntu2.5 | libtiff | Sam Leffler and Silicon Graphics, Inc. | yes (`libtiff.so.6`) |
| libudfread | Ubuntu 24.04 `libudfread` | 1.1.2-1build1 | LGPL-2.1-or-later | Petri Hintukainen | yes (`libudfread.so.0`) |
| libvorbis (vorbis, vorbisenc, vorbisfile) | Ubuntu 24.04 `libvorbis` | 1.3.7-1build3 | BSD-3-Clause | the Xiph.Org Foundation | yes (`libvorbis.so.0`, `libvorbisenc.so.2`, `libvorbisfile.so.3`) |
| libvpx | Ubuntu 24.04 `libvpx` | 1.14.0-1ubuntu2.3 | BSD-3-Clause | the WebM project authors (Google) | yes (`libvpx.so.9`) |
| libwebp (webp, webpmux, sharpyuv) | Ubuntu 24.04 `libwebp` | 1.3.2-0.4build3 | BSD-3-Clause | Google Inc. | yes (`libsharpyuv.so.0`, `libwebp.so.7`, `libwebpmux.so.3`) |
| libxml2 | Ubuntu 24.04 `libxml2` | 2.9.14+dfsg-1.3ubuntu3.9 | MIT | Daniel Veillard and the libxml2 authors | yes (`libxml2.so.2`) |
| libXrender | Ubuntu 24.04 `libxrender` | 1:0.9.10-1.1build1 | HPND-sell-variant | SuSE, Inc.; Keith Packard | yes (`libXrender.so.1`) |
| Little CMS | Ubuntu 24.04 `lcms2` | 2.14-2ubuntu0.1 | MIT | Marti Maria Saguer | yes (`liblcms2.so.2`) |
| Mbed TLS (mbedcrypto) | Ubuntu 24.04 `mbedtls` | 2.28.8-1 | Apache-2.0 OR GPL-2.0-or-later | The Mbed TLS Contributors | yes (`libmbedcrypto.so.7`) |
| MIT Kerberos (GSSAPI, krb5, k5crypto, krb5support) | Ubuntu 24.04 `krb5` | 1.20.1-6ubuntu2.10 | MIT | the Massachusetts Institute of Technology and the Kerberos contributors | yes (`libgssapi_krb5.so.2`, `libk5crypto.so.3`, `libkrb5.so.3`, `libkrb5support.so.0`) |
| mpg123 | Ubuntu 24.04 `mpg123` | 1.32.5-1ubuntu1.1 | LGPL-2.1-only | the mpg123 project (Michael Hipp and others) | yes (`libmpg123.so.0`) |
| Nettle (nettle, hogweed) | Ubuntu 24.04 `nettle` | 3.9.1-2.2build1.1 | LGPL-3.0-or-later OR GPL-2.0-or-later | Niels Moeller and the Nettle authors | yes (`libhogweed.so.6`, `libnettle.so.8`) |
| NORM | Ubuntu 24.04 `norm` | 1.5.9+dfsg-3.1build1 | LicenseRef-NRL-2-clause | Naval Research Laboratory: This product includes software written and developed by Code 5520 of the Naval Research Laboratory (NRL). | yes (`libnorm.so.1`) |
| ocl-icd (the OpenCL ICD loader) | Ubuntu 24.04 `ocl-icd` | 2.3.2-1build1 | BSD-2-Clause | Brice Videau, Vincent Danjean | yes (`libOpenCL.so.1`) |
| oneVPL dispatcher (libvpl) | Ubuntu 24.04 `onevpl` | 2023.3.0-1build1 | MIT | Intel Corporation | yes (`libvpl.so.2`) |
| OpenJPEG | Ubuntu 24.04 `openjpeg2` | 2.5.0-2ubuntu0.5 | BSD-2-Clause | Universite catholique de Louvain and the OpenJPEG contributors | yes (`libopenjp2.so.7`) |
| OpenPGM | Ubuntu 24.04 `libpgm` | 5.3.128~dfsg-2.1build1 | LGPL-2.1-only | Miru Limited | yes (`libpgm-5.3.so.0`) |
| OpenSSL | Ubuntu 24.04 `openssl` | 3.0.13-0ubuntu3.15 | Apache-2.0 | The OpenSSL Project Authors | yes (`libcrypto.so.3`, `libssl.so.3`) |
| Opus | Ubuntu 24.04 `opus` | 1.4-1build1 | BSD-3-Clause | Xiph.Org, Skype Limited, Octasic, Jean-Marc Valin, Timothy B. Terriberry, CSIRO and others | yes (`libopus.so.0`) |
| p11-kit | Ubuntu 24.04 `p11-kit` | 0.25.3-4ubuntu2.2 | BSD-3-Clause | Red Hat, Inc. and the p11-kit authors | yes (`libp11-kit.so.0`) |
| Pango | Ubuntu 24.04 `pango1.0` | 1.52.1+ds-1build1 | LGPL-2.0-or-later | the Pango authors (Red Hat, Inc. and others) | yes (`libpango-1.0.so.0`, `libpangocairo-1.0.so.0`, `libpangoft2-1.0.so.0`) |
| PCRE2 | Ubuntu 24.04 `pcre2` | 10.42-4ubuntu2.1 | BSD-3-Clause WITH PCRE2-exception | University of Cambridge (Philip Hazel) | yes (`libpcre2-8.so.0`) |
| pixman | Ubuntu 24.04 `pixman` | 0.42.2-1build1 | MIT | the pixman authors (Keith Packard and others) | yes (`libpixman-1.so.0`) |
| rabbitmq-c | Ubuntu 24.04 `librabbitmq` | 0.11.0-1ubuntu0.2 | MIT | Alan Antonuk, VMware Inc. and the rabbitmq-c authors | yes (`librabbitmq.so.4`) |
| rav1e | Ubuntu 24.04 `rust-rav1e` | 0.7.1-2 | BSD-2-Clause | the rav1e contributors | yes (`librav1e.so.0`) |
| shine | Ubuntu 24.04 `shine` | 3.1.1-2build1 | LGPL-2.0-only | the shine authors | yes (`libshine.so.3`) |
| Snappy | Ubuntu 24.04 `snappy` | 1.1.10-1build1 | BSD-3-Clause | Google Inc. | yes (`libsnappy.so.1`) |
| Speex | Ubuntu 24.04 `speex` | 1.2.1-2ubuntu2.24.04.1 | BSD-3-Clause | the Xiph.Org Foundation, Jean-Marc Valin and the Speex authors | yes (`libspeex.so.1`) |
| SRT | Ubuntu 24.04 `srt` | 1.5.3-1build2 | MPL-2.0 | Haivision Systems Inc. | yes (`libsrt-gnutls.so.1.5`) |
| SVT-AV1 | Ubuntu 24.04 `svt-av1` | 1.7.0+dfsg-2build1 | BSD-3-Clause-Clear | the Alliance for Open Media and Intel Corporation | yes (`libSvtAv1Enc.so.1`) |
| TwoLAME | Ubuntu 24.04 `twolame` | 0.4.0-2build3 | LGPL-2.0-or-later | Nicholas J Humfrey and the TwoLAME authors | yes (`libtwolame.so.0`) |
| x264 | Ubuntu 24.04 `x264` | 2:0.164.3108+git31e19f9-1 | GPL-2.0-or-later | the x264 project (Laurent Aimar, Loren Merritt, Fiona Glaser and others) | yes (`libx264.so.164`) |
| x265 | Ubuntu 24.04 `x265` | 3.5-2build1 | GPL-2.0-or-later | MulticoreWare, Inc. | yes (`libx265.so.199`) |
| Xvid | Ubuntu 24.04 `xvidcore` | 2:1.3.7-1build1 | GPL-2.0-or-later | the Xvid Team | yes (`libxvidcore.so.4`) |
| ZeroMQ | Ubuntu 24.04 `zeromq3` | 4.3.5-1build2 | MPL-2.0 | the ZeroMQ authors | yes (`libzmq.so.5`) |
| zlib | Ubuntu 24.04 `zlib` | 1:1.3.dfsg-3.1ubuntu2.2 | Zlib | Jean-loup Gailly and Mark Adler | yes (`libz.so.1`) |
| Zstandard | Ubuntu 24.04 `libzstd` | 1.5.5+dfsg2-2build1.1 | BSD-3-Clause OR GPL-2.0-only | Meta Platforms, Inc. and affiliates | yes (`libzstd.so.1`) |
| ZVBI | Ubuntu 24.04 `zvbi` | 0.2.42-2 | LGPL-2.0-or-later | Michael H. Schimek and the ZVBI authors | yes (`libzvbi-chains.so.0`, `libzvbi.so.0`) |

## The toolchain's runtime, copied beside the executables

| Component | Where | Version | Licence | Copyright | Ships |
|---|---|---|---|---|---|
| libc++, libunwind (llvm-mingw) | `tools/llvm-mingw/bin/` (`scripts/bootstrap_windows.sh`) | LLVM 23.1.0, llvm-mingw 20260826 | Apache-2.0 WITH LLVM-exception | the LLVM Project | yes (`libc++.dll`, `libunwind.dll`) |
| winpthreads (mingw-w64) | `tools/llvm-mingw/bin/` | llvm-mingw 20260826 | MIT | 2011 mingw-w64 project | when the closure needs it (`libwinpthread-1.dll`) |

## References this project was modelled on (no code copied)

- **OpenGOAL** (open-goal/jak-project, ISC): its 989snd re-implementation is the public-API reference the mixer's
  bank-sound player and grain sequencer are written against (`ps2xRuntime/src/lib/snd989*.cpp` say where).
- **Ziemas/989snd**: the decompiled IOP driver, the reference the audio model was audited against (research note 36).
- **PSRewired**: the community's server documentation and Medius app-id list (research note 02). Nothing here implies
  their endorsement.
- **PCSX2**: the console reference every parity measurement compares against; not part of the build or the download.
