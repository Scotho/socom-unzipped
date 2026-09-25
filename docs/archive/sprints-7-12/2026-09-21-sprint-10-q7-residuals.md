# Sprint 10 Q7 — Goal 6's residuals, the ones that need no launch (record)

> **ARCHIVED 2026-09-25 -- a Sprint 10 plan; the sprint is closed and this is its record.**
> Moved here from `docs/superpowers/plans/` in Sprint 13 (Task R1, with the rest of Sprints 7-10's specs and
> plans); nothing below it was edited except citations that pointed at a path that has since moved. It is a
> record, not an instruction.

Branch `agent/q7` off `sprint-10` at `1f1a91c`, worktree `C:\projects\wt-q7`, 2026-09-21. The brief:
`docs/CURRENT_SPRINT.md` row Q7 ("Goal 6 -- residuals, as filler"), `docs/KNOWN.md`'s row "Sprint 8 branch review,
filed for later" items (a), (b), (d), its §4 rows on the console-replay test and the Linux `version.txt` test, and
the Sprint 9 spec's Goal 6. Five items done test-first, each its own commit, `./build.sh test --no-runner` green after
each; six runtime-performance and gate-scored items NOT started, one paragraph each in §3 so the controller can
schedule them. Proposed rulings are numbered from **R222** (§4). Nothing here was launched: every item that touches
the runtime is the controller's to gate after the merge (§5).

## 1. What was done, in the brief's order

| # | Item | Commit | RED | GREEN |
|---|---|---|---|---|
| 1 | The console-replay case that never ran | `99a059c` | The case opened two files and asserted nothing; no fixture existed; with a flat-grey `reference.ppm` the new bar reads 94.99 and fails; a replay cut at 1000 packets (`_STOP`) is a diagnostic and exempt | `tools_py/gsdump_extract.py` regenerates the fixture from the PCSX2 captures still under `tools/pcsx2/snaps/` (5386 packets, the note's number); the case finds it at `game/console_replay`, scores the CPU frame against the console's own picture (9.12 ≤ 16) and, with `PS2X_CONSOLE_REPLAY_GL=1`, the GL frame too (10.24 ≤ 16; GL vs CPU 7.59 ≤ 12); 7 Python cases on a synthetic dump |
| 2 | The Linux packaging `version.txt` test | `a4db0e1` | `MAKE_PORTABLE_SYSTEM=Linux` was not honoured: the Windows branch ran and exited 2 "socom2.exe missing" | Three seams in `make_portable.sh` (`MAKE_PORTABLE_SYSTEM`, `LDD`, `PYTHON3`), a synthetic `dist-linux/` of tiny ELFs and an `ldd` that answers for them; version.txt, the closure walk (a host-only library left behind), the tarball, SHA256SUMS, the audit, exit 3 on "not found", exit 2 without a build -- on this Windows host, ~5 s |
| 3 | KNOWN 110 (b): `micFramesNeeded` | `a997238` | `mic feed: 43299 of 44001 rates lose a frame; first at 4000 Hz, read 1 sample 0: got 3088 want 3104.0`; then 241 rates one SAMPLE short (4150 Hz, read 3: 210 of 211) from the resampler's running sum drifting past the product `micFramesNeeded` floors | `MicResampleFeed` (mic_format.h) carries the resampler's lookahead frame across consuming reads and owes a short read its debt; `micResampleLinear` reports `consumed` and walks `phase + step * k`; lgaud's Read is the feed over `micRead`; all 44001 rates 4000..48000 Hz clean |
| 4 | KNOWN 110 (d): the card | `dc5eeb1` | (i) 7999 clusters written beside the folder's one read 7999 free and a further byte was accepted; (ii) a card root that is a file answered type 2, formatted, 8000 free; (iii) twenty polls were twenty recursive walks | (i) `sceMcWrite` refuses growth past 8000 with `sceMcResFullDevice` (-3), whole; found on the way: Windows lists an OPEN file's size as 0 until close, so open files are sized from their handles; (ii) the root is probed once per port (`Preflight::directoryWritable`), a refusal is "no card" + the `[preflight] exit 72 card-dir-unwritable` line + `setPs2ProcessExitCode(72)`; (iii) the count is cached per port and forgotten by the mutating entry points (`MemoryCardDebugSnapshot::directoryWalks` counts walks) |
| 5 | The stub-state header into a `.cpp` | `50f8403` | (build hygiene, no RED) `Helpers/Support.h` was 2041 lines of definitions in an anonymous namespace, one copy of every global per TU across 19 stub files and two test files (AUDIT-2026-09-17 medium) | `Support.h` declares (types, constexpr, the template, `extern`s, prototypes), `Support.cpp` defines, namespace `stub_support` with a global using-directive so every call site is unchanged; split by script over the item structure, then read; 764/764 |

Suite after each commit: Python `Ran 1669 tests ... OK (skipped=100)`; `ps2x_tests` 759 → 759 → 761 → 764 → 764 passed,
0 failed; the VU1 fixture verify and vram-diff OK. (`./build.sh test --no-runner`, under the loop lock, in the
worktree's own `build-clang`.)

### 1.1 What the controller does for item 1, once

The fixture is game bytes and never enters the tree. In the main tree:

```
python tools_py/gsdump_extract.py "tools/pcsx2/snaps/SOCOM II - U.S. Navy SEALs_SCUS-97275_20260916033728_(2).gs" game/console_replay
```

(`gsdump_extract: 5386 packets (4507744 bytes) of 2 frame(s), state v9, screenshot 640x480`). From then on every
`build.sh test` on this machine runs the CPU replay (about 2.5 s); `PS2X_CONSOLE_REPLAY_GL=1` adds the GL pass on a
hidden window (about 1 s more). Without the fixture the case prints `console replay: skipped -- no fixture (...)` and
passes -- which is what it always did, but now it says so. CI never has the fixture (R222).

The dump format, for whoever regenerates from another capture: magic `0xFFFFFFFF`, u32 header size, nine u32
(state version, state size, serial offset/size, crc, screenshot w/h/offset/size; offsets count from byte 8), the
serial, the RGBA8 screenshot, the GSState freeze (v9: 0x1a9 bytes of registers, the 4 MiB VRAM, an 0x54-byte tail),
8 KiB of privileged registers, then records (0 transfer, 1 vsync, 2 FIFO read, 3 registers). research/31's
"file offset 0x12c1df" is 8 + 0x12c02e + 0x1a9. An unknown state version is refused, not guessed.

### 1.2 KNOWN rows this retires or corrects (the controller writes KNOWN)

- §4 "The pixel-identity console-replay test has never run in the suite, and its dump is gone": retire. The dump is
  regenerated by script from the surviving captures; the case runs wherever the fixture is and asserts a bar
  against the console's own picture. What the row should say instead, if anything: the fixture lives at
  `game/console_replay` (git-ignored), regenerated with the command above; the GL half needs
  `PS2X_CONSOLE_REPLAY_GL=1` (R109).
- The row at :127 "`test_make_portable` ... is skipped on Linux by its own guard ... so the Linux packaging branch's
  `version.txt` has no test": retire. Sprint 9 Goal 2's `MakePortableLinuxTest` already ran it for real on Linux CI;
  `MakePortableLinuxSyntheticTest` now runs the branch on this host too.
- :130 (b): closed. Correct the description while retiring: it was not "one input frame too many on some reads" only --
  at steps above 2 (rates under 8000 Hz) a frame REPEATED; 43299 of 44001 rates were affected; 8000 Hz was exact
  because the step is a whole number, and the lgaud harness opens at 8000, which is why nothing saw it.
- :130 (d): closed, all three clauses, plus the open-file size defect found under it.
- :130 (a) and (e): untouched -- (a) is a §3 paragraph; (e) was checked in Sprint 9 P2 per the brief.
- The AUDIT-2026-09-17 row "Mutable stub state in an anonymous namespace in a header": closed.

## 2. What the tree said that the brief did not

1. **The console-replay case was never a pixel-identity test.** It replayed and wrote PPMs for a person; its three
   assertions were "file opens", "file is 4 MiB", "file read". The Sprint 8 plan's sentence "the console-replay case
   in ps2x_tests is the pixel-identity check and is already in the suite run" was false twice. Deleting it would
   have been defensible; regenerating was possible because the six PCSX2 `.gs` captures of 2026-09-09/16 are still
   under `tools/pcsx2/snaps/` and the "0x12c1df" of research/31 is header arithmetic.
2. **CPU and GL do not render the console's draw list identically** (mean |diff| 7.59 per channel: bilinear against
   nearest, the dither, the GL brighten path). A bar, not identity, is what the case can hold. The bars (16 against
   the picture, 12 GL-vs-CPU) sit at roughly 1.6x today's readings; Sprint 6's 1.73x-dark frame (research/31 §12)
   would have read about 27.
3. **The "16 s a replay" of research/31 is not today's cost**: 2.5 s CPU, 1 s more GL, in a release build.
4. **The Linux branch had two Windows-only defects** that the synthetic run found and that were harmless on Linux:
   `portable_libs.py` prints CRLF under a Windows python and the `while read` kept the `\r`; `tar -f C:/...` reads as a
   remote host to GNU tar. Both fixed in the script (a `tr -d '\r'` as the Windows branch already had; the tarball
   written from inside `OUT`). MSYS's `chmod +x` does not reach NTFS, so the executable-bit assertion is Linux-only.
5. **The mic defect's real shape.** The ring read is consuming; the resampler must SEE one frame past what it
   advances over. At step 2 the two counts agree; at 1.4512 (11025 Hz, the game's rate) about half the reads lost
   the lookahead frame; at step 4 (4000 Hz) two frames repeated. And a second defect under it: the resampler walked
   its position as a running sum while `micFramesNeeded` floors the product, so 241 rates came up one sample short
   on some read. Nobody has heard either: the game's own voice path was measured at 8000 Hz by the harness.
6. **Windows lists an open file's size as the directory entry last saw it.** `recursive_directory_iterator`'s
   `file_size` said 0 for a 7999-cluster save still open for writing (Python's `os.scandir` agrees; `os.stat` does
   not). The card's free-space count therefore ignored the file the game was writing until it closed it. Open files
   are now sized from their own handles.
7. **Exit code 72 already existed** (`ExitCodes::kCardDirUnwritable`, Sprint 9 Goal 1's launch-time preflight) with
   the launcher's sentence; no new code was needed. The HLE reuses `Preflight::directoryWritable` and
   `Preflight::logLine`, so the diagnostics zip's `[preflight] exit` collector picks the line up.
8. **The stub helpers' per-TU copies were mostly single-TU in practice** (each `g_*` is referenced from one stub
   file), which is why the audit called it latent. Two counters were genuinely per-TU and are now global:
   `kMaxPrintfLogs = 200` (Compatibility, LibC and TTY each had 200) and `kMaxStubWarningsPerName = 8`.

## 3. The items NOT started -- what the tree says today, and what the measurement would be

**KNOWN 110 (a), the texture re-hash inside the decode.** `gs_gl_backend.cpp:3548-3570` (R123): when a generation
bump brings a cached texture to `resolveTexture`, `textureSourceHash` walks the shadow bytes a decode would read; on a
hit the entry is revalidated (counted and timed under `PS2X_GS_UPLOAD_TRACE`), on a miss the texture is deleted and
the decode below walks the same bytes again and then `entry.sourceHash = textureSourceHash(...)` (:3432) walks them a
third time. So a texture that really changed pays three walks of its source; a 640x512 CT32 movie frame (1.3 MB) is
the worst case, every movie frame. The fold: compute the hash inside the decode loop (the decoder already touches
every texel in order; FNV over the same bytes costs one multiply-xor per byte) and keep it for the entry, so a changed
texture pays one walk plus the decode. Measurement, no launch needed for the first half: the console-replay fixture
through the GL pass with `PS2X_GS_UPLOAD_TRACE`, decode microseconds per texture before and after; then the gate's
title stage (the atlas re-uploads that R123 was about) and a movie (`--only A --hold 60` through the intro) reading
`[gs-gl stats] decodes=` and the frame time. The risk is a hash that no longer equals what `hashTexels` computes over
the shadow -- the identity tests in `gs_gl_texture_identity` are the guard.

**The readback PBO ring.** Every readback is a synchronous `glReadPixels` on the render thread: the exposure
readback (`:2881`, one pixel, 10 Hz, the auto-exposure column of research/31 §12), the render-target downloads for
RT-overlap resolves (`:2721`, `:2774`, whole `nativeWidth x h` rows), the CPU-oracle path (`:2924`) and the display
snapshot (`:587`, `:600`). Each is a full pipeline drain. The ring: N pixel-buffer objects, `glReadPixels` into the
PBO (asynchronous), `glMapBufferRange` one or two frames later; the exposure readback tolerates a frame of latency
trivially; the RT downloads do not (the EE waits on them: AUDIT 2.2's "lock-step round trip"), so those need the
GPU-side blit the audit named instead, or `gpuRows` restricted downloads. Measurement: `PS2X_GS_STATS=1` prints
`readback=` per second and the render-thread frame time; a gameplay hold of 60 s before and after, the count of
readbacks per frame and the 99th-percentile frame time. Gate-scored: the three stages, since the RT path feeds the
textures the transition stage keys on.

**The invocation stack pool.** `EeScheduler::invocationStackTop` (`EeScheduler.cpp:1344`) hands each (thread, depth)
pair a 16 KiB stack from `PS2Runtime::reserveAsyncCallbackStack` (`ps2_runtime.cpp:2121`), which carves downward from
`PS2_RAM_SIZE` toward `m_asyncCallbackStackFloor` (`ps2_runtime.h:516`: 0x01F00000, the last MiB of RAM, so 64
stacks of 16 KiB -- the audit's "64 slots" is that arithmetic; `:549` and `:1032` move the floor to the guest heap's
hard limit at init) and never frees; stacks are keyed and reused per (thread, depth), so the pool grows with the
number of distinct threads that ever take a callback times their maximum nesting, not with time. Exhaustion throws
`"EE invocation stack space exhausted"`, which the game thread reports and exits on. The fix the audit named: a free-list per depth, or at least a loud `[ee] invocation stacks: N used, M KiB left`
line at each new allocation past a threshold. Measurement: over
the ladder's longest run (the two-instance online ladder is where thread counts are highest): a counter of distinct
keys in `invocationStackTop`, printed on the `PS2X_CLOCK_TRACE` cadence -- how many stacks exist at the end of a
20-minute online session, and how far the top is from the floor. If the number is small and flat,
the warning line is the whole fix.

**The VU0 macro-mode flag latency** (research/31 §17, KNOWN §4 "Open"). The recompiler lands MAC/STATUS flags the
instruction they are produced (`vu_translator.cpp:61-95`: CFC2 of STATUS/MAC reads `ctx->vu0_status` /
`ctx->vu0_mac_flags` directly); hardware lands them four cycles later, and the game's "needs clipping" test
(`FUN_00294a30`) reads them in that window, so objects inside the guard band take the unclipped VU1 family on ours.
Two latency models were built test-first and reverted the same evening because both darkened the spawn view (whole
frame 31.8 / 36.8 against 25.3): some other macro-mode reader depends on the immediate semantics, or on a CTC2 that
interlocks. The note's own instruction stands: trace `FUN_00294a30`'s CFC2 value on the console (PCSX2's COP2 flag
pipeline) before modelling again. Measurement now available without a launch of our game: the console-replay fixture
is a GS dump, not an EE trace, so it cannot see this; what can is a PCSX2 run with a CFC2 breakpoint at
`FUN_00294a30`, then the gate's geometry score (the 96-triangle terrain count of research/31 §17 and the whole-frame
score) on the rebuilt exe. The one visible cost today is one polygon at the spawn view.

**The audio residuals.** (i) *Stream-start underfill*: two things carried this name. The 989snd stream's first
callback starving was fixed in Sprint 9 Q0 (`playStream` decodes the first chunk pair on the caller's thread; KNOWN
row :26, `s9_q0_prefill_gate`). What remains is KNOWN :215's "the first ten seconds after a stream starts fill
short while the pipeline settles" on the sceMpeg PCM path (the title loop and the intro movie); the measurement is
`audio_corr` against the disc's PCM over the first ten seconds of the title loop, per second, before any change.
(ii) *Aside-cap parity*: `MPEG.cpp:1989-2006` still drops the OLDEST aside packet past `kMaxAsideAudioPackets = 64`;
packets are odd-length, so a drop flips sample parity until the next stream start (research/32 §7.1 fault 3).
Reachable only if the audio thread stops draining; the fix is to drop in pairs or drop the newest, and the test is a
parity check across a forced drop. (iii) *The scratch leak*: `MPEG.cpp:2021-2031` guestMallocs `asideScratchAddr`
per playback state and frees it only when growing it; `makeFreshPlaybackState()` (`:883`, taken at `:1640`, `:1651`,
`:2714` on a stream restart) makes a new state without freeing the old one's scratch, so the idle title screen leaks
one 8 KiB-or-larger guest block per loop. The fix is a free in the reset path; the measurement is the guest heap's
high-water mark over an hour of the title screen -- there is no heap instrument today (`PS2Runtime::guestMalloc`,
`ps2_runtime.cpp:1956`, counts nothing), so the first step is a `[heap]` line on the stats cadence -- before and after. None of the three needs the gate; (i) needs a listen.

**The window policy scored by the gate** (fullscreen at desktop resolution). `ps2_runtime.cpp:767-782`:
`PS2X_WINDOW_SIZE=<w>x<h> | fullscreen` (borderless), the launcher's choice; the runtime's default is 640x448, the
launcher's 1280x896 (the Goal 3 plan's handoff note 12). "Fullscreen at desktop resolution" is a policy question --
whether the launcher's VIDEO page defaults to the desktop's size, and whether a borderless window at desktop size
scores the same on the gate as the pinned 1280x896 the gate runs at today (Q1b's pins refuse a drift in
`PS2X_WINDOW_SIZE`, R185-R188). The measurement is exactly that: one gate at `fullscreen`, its three scores against
the pinned run's, and the capture path (`PS2X_HOST_SCREENSHOT_LATEST`) confirmed to grab the whole desktop-sized
frame. Owner-visible (the first thing a player sees), so the default belongs with the owner's playtest list.

## 4. Proposed rulings (numbered from R222; each is the owner's to overturn)

- **R222 -- the console-replay case runs wherever `game/console_replay` exists and says "skipped" where it does not;
  the GL half stays behind `PS2X_CONSOLE_REPLAY_GL=1` (R109).** The fixture is game bytes (the console's VRAM and its
  draw list), so it cannot be committed and CI never has it; the case therefore runs on the host and in any worktree
  whose `game/` holds the fixture, and prints its skipped line elsewhere. The bars: mean |diff| per channel ≤ 16
  against PCSX2's own screenshot (measured 9.12 CPU, 10.24 GL, the 480-row picture resampled linearly to the 448-row
  frame), and ≤ 12 GL against CPU on identical input (7.59). *Cost if wrong:* a bar at 1.6x the reading could let a
  small regression through; a tighter bar would flag the next bilinear-vs-nearest change as a defect. The Sprint 6
  class of defect (a whole-frame 1.73x) reads about 27 and is caught.
- **R223 -- the card's cluster count is walked once per game-side change, not per poll.** What appears in the card
  folder behind the game's back (a person copying a save in while the game runs) is counted at the game's next own
  change to the card (a write that grows a file, an open, a mkdir, a delete, a rename, a format, an init). *Cost if
  wrong:* a free-space figure stale by one external edit for the rest of a session; nothing the project runs edits a
  card while the game has it (the gate copies `mc0_parity` BEFORE the launch).
- **R224 -- a card root that cannot take a file answers "no card" and leaves exit 72; it does not stop the game from
  inside the HLE.** The launch-time preflight already stops before the window for slot 0; a root that fails inside
  the run (the second slot, a folder gone read-only after launch) is reported as no card inserted -- true -- with the
  `[preflight] exit 72` line and the process exit code the launcher already turns into "The memory-card folder
  cannot be written". *Cost if wrong:* a player sees the game's "no memory card" for a session before the LAST RUN
  line explains it; a `_Exit(72)` from inside `sceMcGetInfo` would explain it sooner and lose the session.
- **R225 -- a write past the card's capacity is refused whole with `sceMcResFullDevice` (-3), never partially
  written.** libmc's answer; a partial write would leave a save the game believes complete. The check measures the
  write's growth in clusters against the cached count, so a rewrite inside a file's existing clusters is free.
- **R226 -- the microphone resampler walks the product `phase + step * k`, not a running sum, and reports what it
  consumed.** Output samples can differ from before by one LSB at some positions (the interpolation fraction is now
  computed from the product); no listen was made -- the game's voice path was never measured at 11025 Hz, only at
  the harness's 8000, where the arithmetic is exact either way. *Cost if wrong:* a one-LSB difference in the voice
  stream nobody can hear; the alternative (keeping the sum) leaves 241 rates one sample short per read.
- **R227 -- the stub helpers live in namespace `stub_support` with a global using-directive in the header.** The
  anonymous namespace was at global scope, so every stub file and two test files used the names unqualified; the
  using-directive preserves that and the same ambiguity rules, and the stub files' own nested anonymous namespaces
  compiled without a clash. The two log caps that were per-TU are now global (200 printf lines, 8 warnings per
  name). *Cost if wrong:* fewer `[printf]` lines in a log where three subsystems each used to get 200.
- **R228 -- the synthetic Linux packaging test asserts the executable bit on Linux only.** MSYS's `chmod +x` does
  not reach NTFS; the real-Linux test (`MakePortableLinuxTest`, CI) keeps that assertion.

## 5. For the controller

- **Gate these** (runtime touched): `a997238` (mic: `mic_format.h`, `lgaud.cpp` -- the voice path; a headset listen at
  the game's 11025 Hz is the only thing that would hear the difference), `dc5eeb1` (the card HLE -- the gate's boot
  from `mc0_parity` and a save in a round read this code; note the exit-72 path fires only on a root that cannot take
  a file), `50f8403` (the stub helpers -- every stub file; no behaviour change intended beyond the two log caps).
  `99a059c` changes only a test and adds a script; `a4db0e1` only the packaging script and its test.
- **Regenerate the fixture once** (§1.1) so the console-replay case runs on the host's suite; consider adding
  `PS2X_CONSOLE_REPLAY_GL=1` to the pre-commit run for GL-touching work (R109 keeps it off in CI).
- **KNOWN edits** are listed in §1.2.
- **Not verified by me:** anything on a running game; the mic fix on a real headset; the card's exit-72 path on a
  real read-only folder (the test uses a file in the folder's place; Windows ignores the read-only attribute on
  directories for file creation, so a true permission failure was not reproduced); Linux for the packaging seams
  (the real-Linux test is CI's).

## 6. Files

- `tools_py/gsdump_extract.py`, `tools_py/tests/test_gsdump_extract.py` (new);
  `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp` (the case).
- `scripts/make_portable.sh`; `tools_py/tests/test_make_portable_linux.py`.
- `third_party/ps2recomp/ps2xRuntime/include/runtime/mic_format.h`; `third_party/ps2recomp/ps2xIOP/src/modules/lgaud.cpp`;
  `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp`.
- `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/MemoryCard.{cpp,h}`;
  `third_party/ps2recomp/ps2xTest/src/ps2_runtime_io_tests.cpp`.
- `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/Helpers/Support.h`, `Support.cpp` (new).
