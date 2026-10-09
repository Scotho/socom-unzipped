# 86 — macOS support: what the tree needs, sized in three tiers (2026-10-04)

> Superseded in part 2026-10-08 by Grswld's macOS port, taken by cherry-pick (`docs/MACOS.md`). His fork skipped
> tier (a) and did tier (b) first: native arm64, booting offline to a mission on 2026-10-01, about a day of work on
> a Mac. So this note's tier order and its tier (b) estimate are history. Confirmed by the port: `sigtimedwait` is
> absent, there is no `/proc`, sse2neon carries the runtime, the x87 rounding scope is x86-only, and GL 4.1 runs
> without clip control. Still open: FTOI and min/max NaN semantics under NEON (section 1, items 4-5), SIGPIPE on the
> sockets (LATER 102), and all of tier (c).

The owner's ask of 2026-10-04 ~14:40Z ("see what would be required for mac osx support"); one Opus research agent, read-only over sprint-17 at 7613eb8b and sprint-18 at f4c8435c, no build, no run, no Mac on hand. Markings: **[verified: file:line]** against this tree; **[inferred]** from memory, to confirm (Apple's OpenGL status, PCSX2's macOS layout). The headline: the Linux port did most of the work (every `_WIN32` site has a POSIX fallback; CMake already fetches sse2neon for arm64); tier (a) an x86-64 build for Intel or Rosetta is 4-6 loop-days of glue; tier (b) native Apple Silicon adds 4-8 (five direct x86 SIMD includes, x87 inline asm in `VuRoundingScope`, FTOI/min-max/long-double semantics to match); tier (c) a signed app bundle adds 5-8 plus the owner's Apple Developer steps. The gate on every tier: compiling the disc-derived generated code on a Mac, which no public CI runner may do. Found on the way: `send` without `MSG_NOSIGNAL` and no SIGPIPE handling (LATER 102).


Tree: C:\projects\socom_pc, sprint-17 (Sprint 18 PCSX2 code from branch `sprint-18`); paths are under `third_party/ps2recomp/`
unless they start with `docs/`, `scripts/`, `.github/` or `recomp/`. Nothing built or run; memory facts are [inferred].

## Bottom line
- The Linux port did most of the work. Every runtime and launcher `_WIN32` site has a POSIX `#else`, and the CMake
  files already handle APPLE (most `UNIX` blocks say `UNIX AND NOT APPLE`). The ARM path is wired too: root
  `CMakeLists.txt:39-56` fetches sse2neon v1.9.1 and defines `USE_SSE2NEON` on arm64, with a macOS-arm64 branch
  [verified: CMakeLists.txt:39-82]. Nobody has ever configured it on a Mac. No `__APPLE__` code exists apart from
  thread naming [verified: ps2xRuntime/include/ThreadNaming.h:25,73].
- The GL side is the least risky part. The backend uses a plain GL 3.3 core set, and the one GL 4.5 call
  (glClipControl) is probed and optional. The Linux VM already ran the game on Mesa GL 4.1 without it (details in 3).
- The blocker is logistics, not code. The game binary is compiled from 14,882 generated files that come from the
  owner's disc and are not in the public repo [verified: .github/workflows/linux.yml:2-4; `ls recomp/output` = 14882].
  So a Mac build of the game needs a Mac that holds that set. CI can only build the runtime, the launcher and the tests.

## 1. Build system and toolchain
- CMake 3.21 + Ninja. Windows uses llvm-mingw clang. Linux uses system clang/lld through `scripts/build_linux.sh`: the
  same CMake tree, `-DCMAKE_C_COMPILER=clang` [verified: scripts/build_linux.sh:1-3,60-64].
- linux.yml has three jobs, which a macos.yml would mirror [verified: .github/workflows/linux.yml:44-216]: `changes`
  (any non-docs change?); `build` (apt toolchain + X11/Wayland/ALSA/Pulse/FFmpeg -dev, `build_linux.sh --no-runner`,
  `build_linux.sh test --no-runner` = Python suite + ps2x_tests, `build_synthetic_runner.sh`, upload the launcher);
  `recomp-ref` (rebuild ps2_recomp, diff a fixture's output).
- CMake fetches raylib 5.5, imgui and rlImGui [verified: ps2xRuntime/CMakeLists.txt:46-94]. FFmpeg is a prebuilt zip
  on Windows [verified: :114-205] and `pkg_check_modules` elsewhere [verified: :206-217], which Homebrew's ffmpeg
  would satisfy [inferred].
- x86 flags: the only arch flag is `-msse4.1`, set when the processor matches x86_64 [verified:
  ps2xRuntime/CMakeLists.txt:431-440,603-614]. There is no `-march`, no AVX, and no AVX2 outside the MSVC-only
  `/arch:AVX2` [verified: ps2xRuntime/cmake/ReleaseMode.cmake].
- Intrinsic counts (the recompiler emits intrinsics as text, so generated code inherits them) [verified: greps]:
  generated game code 694 of 14,882 files, 9,727 `_mm_*(` call sites, mostly cast/blendv/shuffle/shift/min/max (MMI
  and VU0 lowering), with no inline asm, `long double` or `fesetround`; runtime 16 files, about 1,066 sites
  (ps2_runtime_macros.h 190, vu/ps2_vu1_ops.h 179); recompiler emitters 6 files, 588 sites
  (vu_translation_helpers.cpp 151, mmi_translation_helpers.cpp 103). Generated files reach intrinsics only through
  `ps2_runtime.h`/`ps2_runtime_macros.h`, already sse2neon-guarded [verified: include/ps2_runtime.h:9-16;
  ps2_runtime_macros.h:12-15]. 128 distinct intrinsics; sse2neon claims SSE4.2 [inferred: github.com/DLTcollab/sse2neon].
- Breaks on arm64 today: (1) unguarded x86 headers in `ps2_vu1.h:8`, `vu/ps2_vu1_ops.h:16`, `vu/ps2_vu1_upper.cpp:10`,
  `vu/ps2_vu1_core.cpp:19` and `ps2xTest/src/vu1_ops_tests.cpp` [verified]; (2) x87 asm (`fnstcw`/`fldcw`) plus
  `_mm_getcsr`/`_mm_setcsr` in `VuRoundingScope`, run on every VU program [verified: vu/ps2_vu1_core.cpp:2149-2169];
  (3) `long double` in the VU FMAC slow path, 30 uses, which is 64-bit on Apple arm64 [inferred]; the default fast
  path avoids it [verified: ps2_vu1_core.cpp:2568-2570]; (4) FTOI relies on CVTTPS2DQ's 0x80000000 answer and flips
  lanes to saturate [verified: ps2_runtime_macros.h:222-232], while NEON `vcvtq_s32_f32` saturates and sends NaN to 0
  [inferred], so check sse2neon.h v1.9.1's `_mm_cvttps_epi32`; (5) min/max with NaN match x86 only with
  `SSE2NEON_PRECISE_MINMAX` [inferred: sse2neon README].
- Intel Mac or Rosetta 2: build x86_64 as on Linux, no SIMD change. Rosetta 2 translates SSE through SSE4.2 and we
  need only SSE4.1 [inferred: Apple "About the Rosetta translation environment"].
- Native Apple Silicon: needs the five include fixes, an arm64 rounding scope (FPCR, or sse2neon's
  `_MM_SET_ROUNDING_MODE`), the precise-semantics flags, and a numeric parity check (section 8).

## 2. Platform glue (Windows-only module, then its POSIX twin, then what macOS still needs)
- Launcher glue: `ps2xLauncher/src/win32_glue.cpp` (808 lines; comdlg32/shell32/winhttp,
  [verified: ps2xLauncher/CMakeLists.txt:114]). Its POSIX twin is `posix_glue.cpp` (764 lines), compiled whenever
  `UNIX` is set, which includes APPLE [verified: ps2xLauncher/CMakeLists.txt:98]. macOS still needs:
  - `/proc/self/exe` replaced by `_NSGetExecutablePath` in 3 copies [verified: posix_glue.cpp:119;
    ps2xShared/src/exe_dir.cpp:26; src/tools/vu1_replay.cpp]; today exe_dir silently falls back to the working
    directory [verified: exe_dir.cpp:32-35].
  - zenity replaced by `osascript` "choose file" or NSOpenPanel, and `xdg-open` by `open` [verified:
    posix_glue.cpp:134-165].
  - `gameRunningFrom` scans `/proc` and finds nothing on a Mac; libproc `proc_listpids`/`proc_pidpath` replaces it
    [verified: posix_glue.cpp:230-242].
  - `sigtimedwait` (posix_glue.cpp:574) does not exist on macOS [inferred]. `posix_spawn_file_actions_addchdir_np`
    (:304-307) exists on 10.15+ [inferred: check spawn.h].
  - Already fine: the X11 window switch compiles out (:41,363-366); chrome and min/max are no-op stubs (:175-178);
    HTTP is a `curl` subprocess, which macOS ships (:486-502) [verified].
- Runtime: `host_window_chrome_win32.cpp` and `host_move_loop_win32.cpp` are `#ifdef _WIN32` with stubs, so nothing
  is owed [verified: grep of their guards]. The other 25 `_WIN32` files (save state, IOP host, CD/MemoryCard stubs,
  personas WSAStartup, process_fatal, knobs, iso9660) use `#else` POSIX paths, which a Mac would take [verified:
  per-file grep].
- `__linux__`-only code a Mac silently loses [verified unless marked]: the crash handler that maps signals to exit 70
  (game_overrides_socom2.cpp:620,1987; it reads `REG_RIP` at :686, so a Mac needs `__ss.__rip` or arm64 `__pc`); the
  developer-only host sampler (x86_64 Linux, `timer_create`, :2135,2508; macOS has no POSIX timers [inferred]); IOP
  plugin `dlopen`, `.so` only (ps2xIOP/src/plugin_loader.cpp:18,694; unused in play [inferred]);
  `ExeDir::platformName()` answers "other", which feeds diagnostics and bug reports (exe_dir.cpp:38-46).
- Threads: a "GameThread" is spawned and the raylib draw loop stays on the main thread [verified:
  ps2xRuntime/src/lib/ps2_runtime.cpp:2918-2951,3089-3313], which is what Cocoa needs [inferred].
- macOS-only work beyond the Linux port: app bundle, Info.plist (microphone string: host_mic and the launcher's mic
  page capture through miniaudio), Gatekeeper and notarization, Retina scaling for the GL present. config.json, cards
  and logs live beside the exe [verified: docs/DEVELOPING.md:1375], and a signed or translocated .app is read-only
  [inferred: Apple "Gatekeeper and runtime protection"], so they move to `~/Library/Application Support/SOCOM
  Unzipped`. APFS is case-insensitive by default, kinder than the case-sensitive Linux the port handles [inferred].

## 3. Graphics
- The renderer is a GL 3.3 core shader set (`#version 330 core`). It calls only core entry points: framebuffers,
  glTexImage/SubImage, glReadPixels ×19, glBlitFramebuffer, glBindFragDataLocationIndexed (dual-source)
  [verified: gl* census over src/lib/gs]. It does not use debug output, timer queries, PBOs, persistent mapping,
  compute, buffer storage or fences [verified: same grep, zero hits].
- glClipControl (GL 4.5 or ARB_clip_control) is fetched through `glfwGetProcAddress` and probed. When it is missing
  the backend uses the fragment-depth mapping and logs a note, not a failure [verified:
  gs/gs_gl_backend.cpp:17-22,431-455; include/runtime/gs/gs_gl_caps.h:91-94]. Apple's GL stops at 4.1, so it would
  take that path [inferred: Apple "OpenGL capabilities tables"]. Linux already proved the path: the VM ran the game
  on Mesa GL 4.1, probe passing with "clip control absent", boot frame diff 0.008 [verified: docs/KNOWN.md:79-80].
- Dual-source blending is required; without it the game drops to the CPU rasterizer (correct, slow) [verified:
  gs_gl_caps.h:89-90]. Apple GL 4.1 exposes ARB_blend_func_extended [inferred: confirm in the same Apple table].
- ARB_conservative_depth (LATER 98) is GL 4.2, so it stays unavailable on a Mac. A Mac keeps the early-Z cost that
  LATER 98 describes [verified: docs/LATER.md:134].
- Risks [inferred]: Apple Silicon's GL is layered on Metal, so 19 synchronous glReadPixels may stall harder; on
  Retina raylib's window and framebuffer sizes differ; GL is deprecated but ships (`GL_SILENCE_DEPRECATION`).
- A Metal path is out of scope: a second gs_gl_backend.cpp (4,820 lines [verified: wc]), raylib bypassed for present,
  shaders in MSL; several weeks. MoltenVK does not help, because there is no Vulkan backend.
- Launcher: raylib 5.5 on macOS uses GLFW's Cocoa backend for the window, keyboard, mouse and gamepads [inferred:
  raylib wiki "Working on macOS"]. The launcher draws its own UI and needs no native widgets apart from the file
  picker in section 2.

## 4. Audio and input
- Output: miniaudio, a context with the default backend list [verified: ps2xRuntime/src/lib/ps2_audio.cpp:492].
  raylib's `InitAudioDevice` also uses miniaudio [verified: ps2_runtime.cpp:840]. Microphone capture is miniaudio
  too [verified: host_mic.cpp, launcher mic_devices.cpp]. miniaudio's default list includes Core Audio, so no code
  is needed [inferred: miniaud.io docs]. Microphone access triggers macOS's permission prompt, and a bundle needs
  `NSMicrophoneUsageDescription` [inferred].
- Pads: raylib/GLFW only (`IsGamepadButtonDown`/`GetGamepadAxisMovement`) [verified: ps2_pad.cpp, Kernel/Stubs/Pad.cpp,
  launcher main.cpp]. The Windows-only XInputGetStateEx guide-button read answers false on POSIX [verified:
  ps2xLauncher/src/win32_glue.h:67-75]. GLFW on macOS reads pads through IOKit HID with the SDL mapping database
  [inferred]. Whether the guide and touchpad buttons arrive is unknown, the same open question as on Linux
  [verified: docs/KNOWN.md:124].

## 5. Network and the PCSX2 door
- The Horizon client path (`socom2_hostnet.cpp`) is portable BSD sockets with Winsock shims, getaddrinfo and an
  EINTR-restarted poll [verified: socom2_hostnet.cpp:67-312,646,682]. `send` uses flags 0 and nothing ignores SIGPIPE
  [verified: no SIGPIPE in the runtime], so a peer reset could kill the process on Linux and macOS [inferred]; the
  fix is `SO_NOSIGPIPE` or `signal(SIGPIPE, SIG_IGN)`.
- Sprint 18 (branch `sprint-18`) hard-codes Windows in four places: `kExeName = "pcsx2-qt.exe"` [verified:
  sprint-18:ps2xShared/include/launcher/pcsx2_install.h:19]; the asset suffix `-windows-x64-Qt.7z`, with a macOS
  asset a tested refusal [verified: sprint-18 plan docs/superpowers/plans/2026-10-01-sprint-18-tasks.md:667,723];
  extraction through `<SystemRoot>\System32\tar.exe` [verified: sprint-18:ps2xShared/src/pcsx2_install.cpp:330];
  adapters through GetAdaptersAddresses (POSIX may answer "not on this platform", plan :654,693). The data root is
  beside the exe with portable.txt, else Documents/PCSX2 (POSIX reads `$XDG_DOCUMENTS_DIR`) [verified:
  sprint-18:ps2xShared/include/launcher/pcsx2_files.h:18-25; pcsx2_files.cpp:99-110].
- PCSX2 on macOS differs in each [all inferred: confirm at pcsx2.net/docs and the GitHub release page]: the asset is
  `pcsx2-vX-macos-Qt.tar.xz`, a universal .app (the plan's own fixture names it); the binary is
  `PCSX2.app/Contents/MacOS/PCSX2`; non-portable data lives in `~/Library/Application Support/PCSX2`, and portable
  mode on macOS is unclear; /usr/bin/tar (bsdtar) unpacks xz; adapters are BSD names (en0) from getifaddrs; a curl
  download carries no quarantine flag (a browser download does, and Gatekeeper then prompts on first launch).

## 6. CI and release
- macos.yml would copy linux.yml's `build`: brew install cmake ninja pkg-config ffmpeg; a new
  `scripts/build_macos.sh --no-runner`; ps2x_tests, the synthetic runner and recomp-ref. build_linux.sh uses `nproc`,
  `sha256sum` and objcopy `--only-keep-debug/--add-gnu-debuglink` [verified: scripts/build_linux.sh:58,115-131];
  macOS needs `sysctl -n hw.ncpu`, `shasum -a 256`, `dsymutil` + `strip`. `build_synthetic_runner.sh` and
  `make_portable.sh` branch on `uname -s` with no Darwin case [verified: build_synthetic_runner.sh:32-38;
  make_portable.sh:221-222].
- Hosted runners: arm64 macos-14/15 are free for public repos. Intel runner images are being retired [inferred:
  GitHub "About GitHub-hosted runners"], which pushes Rosetta testing onto arm64 runners.
- Release archive: today a Windows zip and a Linux tar.gz with lib/ filled from ldd through
  `scripts/portable_libs.py` [verified: make_portable.sh:107-140]. macOS needs an otool -L closure, install_name_tool
  to `@executable_path/../Frameworks`, and a .app inside a .dmg or zip. The rpath settings are `$ORIGIN` and
  `--disable-new-dtags`, ELF-only and skipped on APPLE [verified: ps2xRuntime/CMakeLists.txt:419-430;
  ps2xLauncher/CMakeLists.txt:116-125].
- Owner-only steps (HUMAN_TASKS rows): an Apple Developer Program membership (money, identity) [inferred: $99/yr],
  a Developer ID certificate, notarytool credentials stored as CI secrets, and stapling. Without them players must
  bypass Gatekeeper by hand. Recent macOS removed the control-click bypass, so this goes through System Settings
  [inferred: confirm in Apple's macOS 15 release notes].

## 7. Game data
- Players supply only the ISO, and the launcher reads it in C++ (iso9660) [verified: ps2xShared/src/iso9660.cpp].
  The ELF ships with the release ("ship exe+ELF"). The runtime is HLE, and no BIOS is read by the launcher
  [verified: no "bios" in launcher main.cpp].
- Developer chain: `scripts/disc_to_elf.sh` is pure Python + Unicorn [verified: scripts/disc_to_elf.sh:8-13]. Unicorn
  and capstone have macOS arm64 wheels [inferred: PyPI]. The Windows-only Python rows (pycaw, comtypes, psutil,
  PyAudioWPatch) are marked `sys_platform == "win32"` [verified: requirements.txt].
- Windows-only dev tooling is harness and ops only: `scripts/archive_logs.ps1`, `kill_stale_drivers.ps1`,
  `tools_py/screenshot.ps1`, winshot. The parity gate's capture side is Windows (x11shot is its Linux half
  [verified: docs/DEVELOPING.md:330]). So a Mac has no gate harness. That is the evidence gap in section 8.

## 8. Sized plan (loop-day = one controller day of agent work, rough)
**(a) Runs on an Intel Mac or under Rosetta, x86_64 build, Linux code paths: 4-6 loop-days.**
- Files touched: the `CMakeLists.txt` files (APPLE rpath/frameworks, Homebrew FFmpeg); `exe_dir.cpp` and
  `posix_glue.cpp` (exe path, dialog, open, proc scan, sigtimedwait); `game_overrides_socom2.cpp` (Darwin crash
  handler); `plugin_loader.cpp` (`.dylib`); a new `scripts/build_macos.sh`; `make_portable.sh` + `portable_libs.py`
  (Darwin branch, otool); `.github/workflows/macos.yml`; tests for each.
- Risk: low to medium. Most of it is the Linux port's `#else` paths, and GL 4.1 without clip control is already
  proven on Mesa. What is not proven: Apple's GL driver, Retina present, Rosetta speed with -O1 generated code.

**(b) Native Apple Silicon: plus 4-8 loop-days.**
- Files touched: the 5 unguarded intrinsic includes; the `VuRoundingScope` asm (FPCR on arm64); the sse2neon
  precision flags (MINMAX, the cvttps semantics behind FTOI) checked against `ps2_runtime_macros.h:222`; the
  `long double` VU slow path (tolerance or soft-float). The host sampler stays x86 Linux.
- Risk: medium to high. The 9,727 generated sites compile through sse2neon without codegen changes, but numeric
  parity of the VU/MMI lanes on NEON is unproven. ps2x_tests' VU suites (`vu1_ops_tests`, `ps2_vu_tests`,
  `vu1_native_tests` with real dumps) on an arm64 runner give the first evidence cheaply.

**(c) Polished app bundle: plus 5-8 loop-days, plus owner steps.**
- .app layout (launcher in Contents/MacOS, game exe beside it, ELF and licences in Resources, dylibs in Frameworks);
  Info.plist with the microphone string; `.icns` from `assets/logo`; config, cards and logs moved to Application
  Support; universal2 via lipo; a signed, notarized DMG; Cmd-Q and menu-bar behaviour; the macOS PCSX2 door (asset
  pick, .app exe path, Library data root, getifaddrs adapters).
- Risk: medium, and mostly in the owner's hands (Apple account, signing secrets).

**Hardest single item:** proving the native arm64 game matches. The SSE semantics behind FTOI, rounding and min/max
go through sse2neon or a 64-bit long double, with no Mac to run the parity gate and a gate harness that is
Windows-first. A close second, and the gate on every tier: someone has to compile the disc-derived generated set on a
Mac (about 90 min on Windows today; see the memory notes), and it cannot go to a public CI runner.

**Evidence we lack, and how to get it:** (1) a GitHub macos arm64 runner, free, no disc: build runtime + launcher +
ps2x_tests + synthetic runner + recomp-ref natively and as x86_64 under Rosetta (`arch -x86_64`), proving compile,
link, the VU suites under sse2neon and a byte-identical recompiler; (2) a real Mac for the game, borrowed or cloud
(AWS EC2 mac2 dedicated host, 24 h minimum; MacStadium/Scaleway) [inferred: check pricing pages], which costs money
or puts disc-derived code on a third-party box, so it is the owner's decision (a HUMAN_TASKS row); then boot, title,
one mission, a frame-time read and the GL caps line against the Windows refs; (3) a Mac player's pad, microphone
prompt and Retina window, which only the owner or a tester can check.
