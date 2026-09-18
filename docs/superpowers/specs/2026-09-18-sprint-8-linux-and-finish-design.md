# Sprint 8 — "Linux, then it looks and sounds finished" — design

**Date:** 2026-09-18. **Branch:** `sprint-8` off `develop` at `b65fe46`. **Owner's words that opened it:** "add linux
support to the installer/launcher" and "if you can interact with my virtualbox feel free to add a linux machine (or use
docker i suppose)". The goal sentence is unchanged: SOCOM II running natively on PC with online play, that a stranger
runs by pointing the launcher at their own r0001 ISO and playing against another stranger on a hosted Horizon server.
"PC" now includes a Linux PC.

## 1. Where Sprint 7 leaves things

Merged at `d270022`/`b65fe46`: the stranger's Windows machine defended, the console's scheduler semantics, the lobby
rate 10/10, the launcher's selectors, the owner's sound reports fixed at the IOP model. Owner-gated and carried: the
hosted server and its two addresses, the second machine, six hands-on checks. Sprint 8's drafted items (the menus'
render cost, voice, audio residuals, window policy, bare-run robustness, knob retirement) stand and follow Goal 1.

## 2. Goals, in order

### Goal 1 — the client on Linux (autonomous; the owner's VM for what needs a display)

**Reading of the request.** The whole client: the launcher AND the runtime, because a Linux launcher that starts a
Windows exe would be nothing. There is no installer on Windows yet either (the Inno outline is Sprint 8's item 5), so
"installer" on Linux means the same portable folder as a tarball, run unpacked from anywhere.

**What the survey found (2026-09-18, the facts the design rests on).** The build is llvm-mingw clang with no target
flags; CMake already carries a Linux FFmpeg branch (pkg-config), UNIX `dl` branches and Android/Vita targets. The
generated game code is 14,882 plain C++ files (576 MB, 12.5 M lines) produced from the owner's disc and not in the
repository. The Windows-only surface, exhaustively: `socom2_hostnet.cpp` (Winsock, no BSD branch); the crash handler
(a vectored exception handler) and the host PC sampler (thread suspend + context) in `game_overrides_socom2.cpp`; the
`[vu1-stats]` thread times; an unguarded `<windows.h>` in the `vu1_replay` tool; the launcher's `win32_glue.cpp`
(`CreateProcessA` with a redirected log and a merged environment, `GetOpenFileNameA`, `ShellExecuteA`,
`GetModuleFileNameW`, each already with an empty `#else`); CMake's `WIN32` executable flag and `comdlg32`/`shell32`,
the `--allow-multiple-definition` link flag, `ws2_32` in the tests; `make_portable.sh`'s `Compress-Archive` and 31 DLLs.
raylib (window, GL, miniaudio with PulseAudio/ALSA, GLFW gamepads) is portable as fetched. The guest RAM is plain
`new[]`. The tests' Windows branches are all two-sided already.

**Design.**

1. **Build on Linux** with the system clang or gcc, Ninja, the same CMake tree. The CMake gets its missing `UNIX`
   branches: `ws2_32` only on WIN32; the launcher without the `WIN32` executable flag and its two libraries;
   `-Wl,--allow-multiple-definition` only where raylib clashes with WinAPI, so never on Linux; the FFmpeg pkg-config
   branch as it is; RPATH `$ORIGIN/lib` for the runner and the launcher so the tarball's `lib/` is found; the runner
   target skipped, not failed, when `PS2X_RUNNER_GENERATED_DIR` is absent (CI has no generated code). One
   `scripts/build_linux.sh` mirrors `build.sh`'s three steps with the native toolchain. The generated code builds at
   `-O1` as on Windows.
2. **Sockets.** `socom2_hostnet.cpp` gets its BSD half behind the same functions: `SOCKET` becomes `int`, `closesocket`
   becomes `close`, `ioctlsocket(FIONBIO)` becomes `fcntl(O_NONBLOCK)`, `FIONREAD` becomes `ioctl`, `WSAGetLastError`
   becomes `errno`, `WSAStartup`/`WSACleanup` become nothing. `socom2_libnetb.cpp` is untouched by design; it only
   calls hostnet.
3. **Crash handler and PC sampler.** `sigaction` on SIGSEGV, SIGBUS, SIGILL and SIGFPE prints the same line the
   vectored handler prints (fault address, the module base from `dladdr`, the guest pc from the same globals). The
   sampler on Linux arms a `SIGPROF` interval timer on the EE thread whose handler records the `ucontext` instruction
   pointer into the same ring the Windows sampler fills, so the `[pc-sampler]` line, the freeze fields and
   `freeze_trace.py` read identically on both. The `[vu1-stats]` thread times come from
   `clock_gettime(CLOCK_THREAD_CPUTIME_ID)`.
4. **Launcher on Linux.** `posix_glue.cpp` implements the same `win32glue` interface (the name stays, one header):
   `exeDirectory` from `/proc/self/exe`; `startGame` through `posix_spawn` with the merged environment (`environ` plus
   `environmentFor`), stdout and stderr to `logs/run_<stamp>.log` through file actions, `running`/`exitCode`/`close`/
   `terminate` on the pid; `browseForIso` runs `zenity --file-selection` when zenity exists and otherwise leaves the
   typed path (the field already accepts typing); `openFolder` runs `xdg-open`. The child is `./socom2`, no `.exe`.
5. **Packaging.** `scripts/make_portable.sh` learns the platform. On Linux it writes `dist/portable/socom2-linux/` with
   `socom2`, `socom2_game.elf`, `socom_unzipped_launcher`, `lib/` (the FFmpeg and any non-system `.so` the runner
   links, found with `ldd`, never glibc, libGL or libX11), `cards/`, `logs/`, `LICENSES/`, a `README.txt` (run
   `./socom_unzipped_launcher`; the distro packages it needs, if any), and a `.tar.gz`. An AppImage or a `.deb` is not
   this sprint.
6. **Verification, in three rings.** (a) GitHub Actions on `ubuntu-24.04`: configure and build `ps2_runtime`,
   `ps2x_tests` and the launcher without the generated code, run `ps2x_tests`, on every push of the port. (b) The
   owner's VirtualBox machine `socom-linux` (Ubuntu 24.04.5 server, 8 cores, 8 GB, SSH on the host's port 2222, a
   host-only adapter, VMSVGA with 3D): the full build with the generated code synced from the host, the suite, then the
   game itself under a bare X session: first the boot to the title screen with `PS2X_AUDIO_DUMP` and the exported
   frame, then the title stage of the gate once the harness's capture and key paths have Linux halves (`xdotool`,
   `import` or `scrot`; a task of its own). (c) The owner on a Linux PC or a Steam Deck with the tarball, when they
   have one.

**Bars.** CI green on every port commit. In the VM: `ps2x_tests` all green; the runner boots to the title screen and
its exported frame matches the Windows frame of the same screen at mean |diff| under 3, both at 640x448; the title
stage of the gate passes in the VM, or, when the VM's GL is below the probe's floor, the CPU fallback's exit 65 with the
same frame. The launcher in the VM starts the game and its log carries the same first lines as a Windows run. The
tarball runs unpacked from a fresh directory in the VM.

**Stop rules.** If the VM's VMSVGA 3D cannot give GL 3.3 with dual-source blending, the CPU rasterizer is the VM's path
and the GL bar moves to the owner's real Linux machine (a HUMAN_TASKS item). If the generated code's Linux build takes
over three hours in the VM, the VM gets more cores (the host has 28) before anything else changes.

### Goal 2 — the menus' render cost at the root (autonomous)

As drafted: the login and lobby screens' 7-11k one-kilobyte tile uploads at 80-133 ms/s; trace the login screen's
pages, break the cost down per call, batch the tiles. Bar: the login screen at 60 fps under a four-core load with
`bp_pending` under 2.

### Goal 3 — voice: serve the headset (autonomous up to the two-machine check)

As drafted from Task 9c's spike: Enumerate answers one device when `PS2X_MIC_DEVICE` is set, Open succeeds, Read serves
HostMic's ring; a WAV of what the game read is the proof; then the owner's "can you hear me" on two machines.

### Goals 4-8 — audio residuals, window policy, bare-run robustness, knob retirement, the rest

As drafted in `docs/CURRENT_SPRINT.md`'s Sprint 8 block (items 3-8), in that order, after Goals 1-3.

## 3. Budget and stop rules

Launches on Windows: Goal 2's login-screen measurements (about four), Goal 3's dump (one). In the VM: the boot, the
title stage, the tarball run (about six; the VM is not the owner's desk, so the host-quiet rule applies to the host's
CPU, not the VM's screen). Stop rules per goal above; Goal 2 stops if batching does not move the ms/s number, filing the
per-call breakdown instead.

## 4. What this sprint does not do

An installer on either platform beyond the portable folder; macOS; ARM Linux (the CMake's ARM branches stay as they
are); the harness's PCSX2 mixed match on Linux; signing.
