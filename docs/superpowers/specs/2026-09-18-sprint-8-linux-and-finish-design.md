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

### Goals 4-8 — audio residuals, window policy, bare-run robustness, knob retirement, the rest (Goal 9 follows them in number only; it runs as soon as Goal 1 merges)

As drafted in `docs/CURRENT_SPRINT.md`'s Sprint 8 block (items 3-8), in that order, after Goals 1-3.

### Goal 9 — the launcher, redesigned (owner request 2026-09-19; autonomous, the owner judges the look)

The owner's words: "A full UI revamp of the launcher to give it a socom-inspired appearance but with modern ui
sensibilities and prioritizing usability and appearance. A full controller render would be cool if such a thing exists."

**What it is today.** One 680-line `main.cpp` of hand-rolled immediate-mode widgets in raylib's default bitmap font on a
flat grey ground: six stacked panels (Disc, Video, Controller, Microphone, Online, Launch) in a 960 px column that
scrolls on a short display. Everything works and is tested at the config layer; none of it looks like anything.

**The reference.** SOCOM II's own front end (the owner's screenshot of SOCOM II ONLINE is the touchstone): a near-black
teal ground with a faint grid and a ghosted photograph behind it; a gold, condensed, italic stencil headline; a left
rail of stacked slab buttons in dim teal with pale stencil labels, the selected one brighter with a gold label; a
content pane of table rows under a header band; a green status lamp top right; a bottom bar with the player's name at
the left and glyph-plus-verb prompts at the right (BACK, SELECT).

**The design.**
- *Layout*: a 1100x700 window, resizable, scaled by one factor from the window height (and DPI), minimum 800x520. Header
  band (the wordmark "SOCOM II" in gold with "UNZIPPED" small beneath, the status lamp and its one-line state at the
  right). Left rail, 220 px: PLAY, DISC, VIDEO, AUDIO, CONTROLLER, MICROPHONE, ONLINE, ABOUT. Content pane to the right:
  one page at a time, no scrolling in the common case. Bottom bar: the profile name at the left, context prompts in the
  middle (the keys or pad buttons that act on the focused control), LAUNCH at the right, always visible, disabled with a
  reason when the disc is not verified.
- *PLAY page* (the landing page): the disc verdict, the server in use, the pad in use, the video mode, each as a row
  with a CHANGE affordance that jumps to its page; the last run's exit line; a large LAUNCH. A stranger's whole path is
  this page plus DISC once.
- *Theme*: palette constants in one header (ground #0B1416, panel #12262A, panel-hi #1B3A40, line #2C5158, text #C9D6D2,
  dim #7D918D, gold #C9A24A, gold-hi #E8C76A, lamp-green #3BE06A, warn #E0A030, bad #D0503A); 2 px lines, no rounded
  corners beyond 2 px, a 1 px inner highlight on the focused control, a subtle 32 px grid and a vignette drawn
  procedurally (no photograph: nothing from the game's disc ships in the launcher). Motion: 120 ms eased transitions on
  focus and page change, nothing else moves.
- *Type*: two open-licensed (SIL OFL) families embedded in the exe as byte arrays so the portable folder stays
  self-contained: a condensed stencil or military display face for the wordmark and rail (first choice Saira Stencil
  One; fallback Black Ops One), and a clean condensed sans for everything else (first choice Rajdhani; fallback Saira
  Condensed). Their OFL texts go into LICENSES/. Loaded at 2x and drawn with bilinear filtering so they stay sharp under
  the scale factor.
- *Input*: every control reachable by mouse, by keyboard (arrows or tab to move, enter or space to act, escape to go
  back to the rail) and by gamepad (d-pad or left stick to move, the bottom face button to act, the right one to go
  back, the shoulders to change page, START to launch). One focus model drives all three; the bottom bar's prompts show
  the glyphs of whichever device was used last.
- *The controller page*: a procedurally drawn pad, front view, about 520 px wide: the body silhouette from arcs and
  rounded rectangles, the d-pad, four face buttons, two sticks that move with the axes inside their wells (the dead zone
  drawn as a ring that the slider resizes live), two shoulder buttons and two triggers drawn above the body as bars that
  fill with the analog value, START/SELECT, stick clicks; every element lights gold while pressed. The face glyphs follow
  the detected pad's family (A/B/X/Y for XInput-style names, the PlayStation shapes otherwise), since the owner plays on
  an Xbox pad and the game prompts with PlayStation shapes; a small legend maps one to the other. Beside it: the pad
  picker (the connected pads by name), the dead-zone slider, mouse-look and its sensitivity. With no pad connected the
  drawing is dim with "connect a controller" across it.
- *Code shape*: `main.cpp` shrinks to the loop; new `src/ui/` files: `theme.h` (palette, metrics, scale), `fonts.cpp`
  (the embedded faces), `widgets.cpp/.h` (button, toggle, slider, radio row, text field, list row, all focus-aware),
  `focus.cpp/.h` (the navigation model, pure), `pages_*.cpp` (one per page), `pad_render.cpp/.h` (the drawing, with a
  pure geometry function the tests use), `glyphs.cpp/.h` (the prompt glyphs). The config layer, the process glue, the
  microphone and the disc check are untouched.
- *Proof without eyes*: a `--screenshot <dir>` mode renders every page once at 1100x700 and at 800x520 with a fixed fake
  state (a verified disc, one pad named "Xbox Wireless Controller" with a few buttons held, a microphone at -18 dB) and
  writes PNGs; the loop reads them, and HUMAN_TASKS carries them for the owner.

**Bars.** Every existing launcher test still passes and `--selftest` prints the same environment. New tests: the focus
model (from each control, each direction lands where the layout says; no control is unreachable; page change keeps the
rail in step), the scale function (1100x700 gives 1.0, 800x520 clamps to the minimum, 2200x1400 gives 2.0), the pad
geometry (every button's hit circle lies inside the body's bounds; the stick's drawn offset is the axis times the well's
radius, zero inside the dead zone), the glyph family choice by pad name, the launch-disabled reason strings. The Linux CI
job builds the new launcher. The screenshots exist for every page at both sizes and the controller page shows the held
buttons lit. The owner's verdict on the look is a HUMAN_TASKS item, with the PNGs.

**Stop rule.** If embedding the fonts fails on either platform (raylib's LoadFontFromMemory, the OFL download), ship the
redesign on the default font scaled up rather than block it, and say so in KNOWN.

### Goal 10 — the community server and its r0004 (owner request 2026-09-19; autonomous up to the owner's file)

The owner's words: "https://psrewired.com/servers/10472 this is the community server that is in the launcher with a
placeholder. i'm noticing they run r004 though, so we may need to include an option to play on that patch in the
launcher."

**What was established (2026-09-19; sources in the investigation, repo evidence in research/02, /03, /05, /19).**
PSRewired is reached by DNS: PS2s set 67.222.156.250 as primary DNS. Resolved through it, `socom2-prod.pdonline.scea.com`,
`socom2-prod.muis.pdonline.scea.com` and `gate1.us.dnas.playstation.org` all answer 67.222.156.250 itself, so our
single-address redirect (`PS2X_SOCOM2_SERVER`, every game hostname to one IP) fits and the preset's value is that address.
Their DNS does not serve `updates.pdonline.scea.com` or the svo name (NXDOMAIN): the update does not travel the retail
path; their guide gives PS2 and PCSX2 users a patch that enables the download from their server. r0004 is not a delta:
the disc's `SCUS_972.75` is a loader, the game is `RUN/RAW/APACHE00.ZDB` (two DNAS-layered, compressed overlays,
ftscore at 0x1e7000 and zsealetc at 0x4c5380), and the boot code looks for `BASCUS-97275SOCOMII/APACHE00.ZDB` on a memory
card first -- r0004 is a whole replacement package, about 1.5 MB, with code and statics moved throughout (ftscore statics
+0x2C9C0 on four verified addresses; the DNAS check relocated; three more maps; a render-fix option). There is no
version field to declare: the revision is the loaded code, and r0001 against r0004 peers would run different code with
different layouts. Whether their server refuses an r0001 login outright is not documented. No r0004 package exists on
this machine (the four PCSX2 cards hold r0001 saves only).

**Design.** A second recompilation, selected in the launcher; never a spoof.
1. *The preset*: `kServerPresets`' community entry becomes 67.222.156.250, with a test; the launcher shows the server's
   required revision beside each preset (community: r0004; SOCOM Unzipped and Custom: r0001 unless told otherwise).
2. *A revision-parameterised pipeline*: `scripts/build_revision.sh <rev> <APACHE00.ZDB>` runs `decrypt_apache.py`,
   `make_overlay_elf.py` and `ps2_recomp` into `recomp/output_<rev>/` and builds `dist/socom2_<rev>.exe` beside its
   `socom2_game_<rev>.elf`, leaving today's r0001 paths exactly as they are. Proof without the owner's file: run it on
   the DISC's package as `r0001check` and compare -- the decrypted overlays and the ELF must be byte-identical to
   `game/overlays/*.bin` and `dist/socom2_game.elf`, and the generated tree must be identical to `recomp/output/`.
3. *The address map*: the HLE overrides, probes and harness peeks name r0001 addresses. They move behind a per-revision
   table (`socom2_addresses.h`: a struct of named addresses, one instance per revision, chosen at start from the ELF's
   identity). Filling r0004's instance is a function-matching job: a fingerprint matcher (normalised instruction hashes,
   call-graph neighbours, the +0x2C9C0 statics rule as a seed) between the two images, with every override's address
   resolved and each unresolved one listed. The matcher and the table land first and are proven on r0001 against itself
   (identity) and against a shifted copy (a synthetic relocation), so they are ready when the r0004 image arrives.
4. *The launcher option*: "Game version" on the PLAY and ONLINE pages: r0001 (your disc) or r0004 (community update),
   the second enabled only when `socom2_r0004.exe` exists, with the reason when it does not; choosing the community
   preset with r0001 selected warns, and the reverse. The r0004 memory-card load stays answered "no update present" in
   both builds (the package is compiled in, never hot-loaded).
5. *The r0004 build itself* (owner-gated on the file): the pipeline on the owner's package, the matcher filling the
   table, the unresolved overrides fixed by hand, then the gate's three stages on the r0004 exe and one control round
   on our own Horizon (r0004 against r0004), before any connection to PSRewired.
6. *Connecting to PSRewired* (owner-gated): their rules are not public (Discord); a non-console client on a community
   server is theirs to allow. The owner asks; the first login is the owner's, hands-on, with their account.

**Bars.** The pipeline's r0001 reproduction is byte-identical. The matcher resolves 100% on identity and on the synthetic
relocation. The preset and the revision option carry tests and appear in the launcher's screenshot mode. With the
owner's file: `socom2_r0004.exe` reaches the main menu showing r0004, gate 3/3, one r0004 control round.

**Stop rules.** If the r0004 package's DNAS layering does not decrypt with the disc's keys, stop at the pipeline and
file what differs. If the matcher leaves more than a tenth of the overrides unresolved on the real image, stop and list
them: that is a hand job with its own sprint. No connection to PSRewired before the owner reports their answer.

## 3. Budget and stop rules

Launches on Windows: Goal 2's login-screen measurements (about four), Goal 3's dump (one). In the VM: the boot, the
title stage, the tarball run (about six; the VM is not the owner's desk, so the host-quiet rule applies to the host's
CPU, not the VM's screen). Stop rules per goal above; Goal 2 stops if batching does not move the ms/s number, filing the
per-call breakdown instead.

## 4. What this sprint does not do

An installer on either platform beyond the portable folder; macOS; ARM Linux (the CMake's ARM branches stay as they
are); the harness's PCSX2 mixed match on Linux; signing.
