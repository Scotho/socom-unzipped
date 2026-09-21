# Third-party notices

SOCOM Unzipped is built on the work below. The project's own code is GPL-3.0 (`LICENSE` at the root: the vendored
recompiler is GPL-3.0 and the executable links it). Every licence text named in the **Licence** column is under
`LICENSES/<id>.txt` (the SPDX id, verbatim); the copyright holders are given here. This file ships inside every
release archive beside `LICENSES/`, and `tools_py/tests/test_third_party_notices.py` fails when a dependency the
build fetches, a directory vendored under `third_party/` or `server/`, or a DLL in the release folder has no row.

SOCOM, SOCOM II: U.S. Navy SEALs, PlayStation and PS2 are trademarks of Sony Interactive Entertainment. Zipper
Interactive made the game. This project is not affiliated with or endorsed by either. **No game code or game data
is in this repository or in the download**; the player supplies their own disc.

## Vendored in the tree

| Component | Where | Version | Licence | Copyright | Ships |
|---|---|---|---|---|---|
| PS2Recomp (ps2xRecomp, ps2xRuntime, ps2xAnalyzer, ps2xIOP, ps2xShared, ps2xStudio, ps2xTest, ps2xLauncher) | `third_party/ps2recomp/` | fork of ran-j/PS2Recomp, heavily modified | GPL-3.0-only | ran-j and PS2Recomp contributors; SOCOM Unzipped contributors | yes (the executables) |
| PS2Recomp's Vita and Android modules (`.suprx`, Gradle) | `third_party/ps2recomp/vita/`, `android/` | upstream, unmodified, NOT built | GPL-3.0-only | ran-j and PS2Recomp contributors | no |
| Horizon Server (Medius/DME/NAT/MUIS for the PS2 online stack) | `server/horizon-server/` | fork, app id 10472 configuration | MIT | 2020 Daniel Gerendasy | no (the hosted box runs it) |
| HighResolutionTimer | `server/horizon-server/HighResolutionTimer/` | as vendored by Horizon | MIT | 2020 Hakan Lindestaf | no |
| Saira Stencil One (font) | `third_party/ps2recomp/ps2xLauncher/assets/fonts/` | 2019 | OFL-1.1 | 2019 The Saira Stencil Project Authors (Omnibus-Type) | yes (embedded in the launcher) |
| Rajdhani (font) | `third_party/ps2recomp/ps2xLauncher/assets/fonts/` | 2014 | OFL-1.1 | 2014 Indian Type Foundry | yes (embedded in the launcher) |

## Fetched at configure time (CMake FetchContent / ExternalProject)

| Component | Declared in | Version | Licence | Copyright | Ships |
|---|---|---|---|---|---|
| raylib (window, input, audio device; bundles miniaudio, glfw, stb) | `ps2xRuntime/CMakeLists.txt` | 5.5 | Zlib | 2013-2024 Ramon Santamaria (@raysan5) | yes (static) |
| Dear ImGui | `ps2xRuntime/CMakeLists.txt` | v1.92.7-docking | MIT | 2014-2026 Omar Cornut | yes (static; the debug UI) |
| rlImGui | `ps2xRuntime/CMakeLists.txt` | Raylib_5_5 | Zlib | 2020-2021 Jeffery Myers | yes (static) |
| FFmpeg (libavcodec, libavutil, libswresample, libswscale; the LGPL build) | `ps2xRuntime/CMakeLists.txt` | n7.1-241205, System233/ffmpeg-msvc-prebuilt | LGPL-2.1-or-later | the FFmpeg developers | yes (`avcodec-61.dll`, `avutil-59.dll`, `swresample-5.dll`, `swscale-8.dll`) |
| libjxl (via the FFmpeg prebuilt) | `ps2xRuntime/CMakeLists.txt` | as bundled | BSD-3-Clause | the JPEG XL Project Authors | yes (`jxl.dll`, `jxl_cms.dll`, `jxl_threads.dll`) |
| libwebp (via the FFmpeg prebuilt) | `ps2xRuntime/CMakeLists.txt` | as bundled | BSD-3-Clause | 2010 Google Inc. | yes (`libwebp.dll`, `libwebpmux.dll`, `libsharpyuv.dll`) |
| Brotli (via the FFmpeg prebuilt) | `ps2xRuntime/CMakeLists.txt` | as bundled | MIT | 2009, 2010, 2013-2016 the Brotli Authors | yes (`brotlicommon.dll`, `brotlidec.dll`, `brotlienc.dll`) |
| zlib (via the FFmpeg prebuilt) | `ps2xRuntime/CMakeLists.txt` | as bundled | Zlib | 1995-2024 Jean-loup Gailly and Mark Adler | yes (`zlib1.dll`) |
| SDL2 (via the FFmpeg prebuilt, and ps2xStudio) | `ps2xRuntime/CMakeLists.txt`, `ps2xStudio/CMakeLists.txt` | as bundled | Zlib | 1997-2025 Sam Lantinga | no (not in the release closure) |
| OpenEXR and Imath (via the FFmpeg prebuilt) | `ps2xRuntime/CMakeLists.txt` | as bundled | BSD-3-Clause | Contributors to the OpenEXR Project | no (the developer `dist/` only; not in the release closure) |
| FreeType (via the FFmpeg prebuilt) | `ps2xRuntime/CMakeLists.txt` | as bundled | FTL OR GPL-2.0-only | The FreeType Project (David Turner, Robert Wilhelm, Werner Lemberg) | no (developer `dist/` only) |
| HarfBuzz (via the FFmpeg prebuilt) | `ps2xRuntime/CMakeLists.txt` | as bundled | MIT | 2010-2024 Google, Inc. and the HarfBuzz contributors | no (developer `dist/` only) |
| ELFIO | `ps2xRecomp/CMakeLists.txt` | Release_3.12 | MIT | 2001-present Serge Lamikhov-Center | no (the recompiler, a build tool) |
| toml11 | `ps2xRecomp/CMakeLists.txt` | v4.4.0 | MIT | 2017 Toru Niina | no (build tool) |
| {fmt} | `ps2xRecomp/CMakeLists.txt` | 12.1.0 | MIT | 2012-present Victor Zverovich and {fmt} contributors | no (build tool) |
| libdwarf | `ps2xRecomp/CMakeLists.txt` | v2.2.0 | LGPL-2.1-or-later | David Anderson and contributors | no (build tool) |
| rabbitizer | `ps2xRecomp/CMakeLists.txt` | 1.14.3 | MIT | 2022 Decompollaborate | no (build tool) |
| nlohmann/json | `ps2xAnalyzer/CMakeLists.txt` | as fetched | MIT | 2013-2022 Niels Lohmann | no (build tool) |
| sse2neon | `third_party/ps2recomp/CMakeLists.txt` | v1.9.1 | MIT | DLTcollab and contributors | no (ARM builds only) |
| imgui_club, ImGuiColorTextEdit, ImGuiFileDialog | `ps2xStudio/CMakeLists.txt` | as fetched | MIT | Omar Cornut; 2017 BalazsJako; 2018-2025 Stephane Cuillerdier | no (ps2xStudio, not built here) |

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
