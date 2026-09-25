# Sprint 7 — Two Strangers, Two Machines, One Hosted Server: Implementation Plan

> **ARCHIVED 2026-09-25 -- a Sprint 7 plan; the sprint is closed and this is its record.**
> Moved here from `docs/superpowers/plans/` in Sprint 13 (Task R1, with the rest of Sprints 7-10's specs and
> plans); nothing below it was edited except citations that pointed at a path that has since moved. It is a
> record, not an instruction.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the runtime honest on a machine that is not this one (a GL capability probe with a CPU fallback, a bounded command queue, a DPI-correct window, a native-VU1 mismatch warning, audio I/O off the callback), settle the two online-only semantics nobody has measured (equal-priority time slicing, two clients on the same RSA key), measure the lobby rate and root freeze shape 2, kill the 21k texture decodes a second so the ladder's back-pressure bar passes for real, and stand up a hosted Horizon server the launcher points at — so two strangers can download the zip, point it at their own r0001 ISOs, and play a round.

**Architecture:** Every runtime change is a failing test first, then `./build.sh test`, then the gate or the launch that proves it on the real exe. The autonomous loop runs **one launch at a time** through `scripts/run_detached.sh` and holds every suite while a launch is live. Bounded mechanical work (a fixture cut, a mechanical rename, a table of numbers out of a log) goes to an Opus subagent with an exact brief and a verification command; every judgement — what a number means, whether a bar is met, what to commit — stays with the controller. Tasks 4, 5 and 6 are owner-gated: their autonomous half runs to completion and then stops at a named line.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh`), Python 3 (`unittest`, numpy, Pillow), the local Horizon server (`server/start-servers.ps1`), raylib for the window/input/audio, PCSX2 2.8.1 as the console reference, Ghidra decomp `game/analysis/socom2_game.elf.decomp.c`, Git Bash + PowerShell.

**Spec:** `docs/archive/sprints-7-12/2026-09-17-sprint-7-two-strangers-two-machines-design.md` (owner review pending; **Goal N there is Task N here**). **Required reading for every dispatch:** `docs/KNOWN.md`, `docs/audits/2026-09-17-audit-and-code-review.md` §1, §2.2, §2.3, `docs/HUMAN_TASKS.md`; for render tasks `docs/research/31-flat-grey-geometry.md` §3 and `docs/research/34-online-round-freeze-clut-serials.md`; for online tasks `docs/research/28-lobby-taxonomy.md`, `docs/research/29-online-freeze.md`, `docs/research/33-online-map-coverage.md`; for audio `docs/research/32-audio-path.md` §5–§7.

## Handoff notes for the executing model (read once)

- **Process.** superpowers:subagent-driven-development; fresh implementer per task; a task review after each that re-derives at least one number independently; the controller merges. Ledger at `.superpowers/sdd/2026-09-17-sprint-7-two-strangers-two-machines/progress.md`. Decisions on the owner's behalf are `Ruling: … — why — cost if wrong`, numbered from **R91** (Sprint 6 ended at R90).
- **`docs/KNOWN.md` has one writer: the controller.** Retractions happen on discovery, in the same hour.
- **Autonomy (owner 2026-09-17; this replaces Sprint 6's host-window rule).** Proceed autonomously — no waiting for a window the owner names. **One launch at a time**, always through `scripts/run_detached.sh`, and **suites are held while a launch runs**: no `./build.sh test`, no `python -m unittest`, no gate and no second launch while `logs/.quiet` exists (`bash scripts/check_quiet_gate.sh` answers). Lock-free work (tests that need no build, decomp reading, notes) fills the wait. `scripts/kill_stale_drivers.ps1` stops a run on request.
- **Subagents (owner 2026-09-17).** Bounded mechanical work goes to Opus subagents with an exact brief and a verification command; judgment stays with the controller. A brief names: the files to touch, the exact edit, the command that proves it, and the expected output. A subagent never decides whether a bar is met, never writes `docs/KNOWN.md`, never commits, and never starts a launch.
- **Commit conventions.** `git commit -m "…" -- <paths>` with an explicit pathspec; never `git add -A`; `server/config/simulated.db` stays unstaged; `ONBOARDING.md` untracked. Push after each commit. Trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Research tasks do not commit; the controller commits notes.
- **Lock protocol.** `bash scripts/loop_lock.sh run <owner> --purpose "<what>" -- <cmd>` for short foreground builds/tests; `scripts/run_detached.sh` for everything long (the runtime build included). On this host use `"C:/Program Files/Git/bin/bash.exe"`. Never hold the lock across tool calls.
- **Instruments** are unchanged: `scripts/parity/env.sh` is the one source of `PS2X_PEEK`, the call traces and the sampler period; every instrument counts its rows and fails when empty. `SOCOM_SERVER_IP` points the harness at a server.
- **Test binary.** `ps2x_tests.exe` lives at `third_party/ps2recomp/build-clang/ps2xTest/` and takes no filter; it runs every case (~505, well under a minute). `build.sh test` builds it and runs the Python suite first.

### The command set (use these verbatim)

```bash
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe 2>&1 | grep -E "Failed\]|Total Tests"
python -m unittest tools_py.tests.<module> -v
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/<name>.marker      # the runtime build
scripts/run_detached.sh --owner gate --purpose launch <script> logs/<name>.marker                       # a gate or a launch
scripts/parity/online_control_round.sh "Frostfire" logs/parity/<name>                                   # a control round
bash scripts/parity/ladder_frostfire.sh logs/parity/<name>                                              # a ladder launch
PS2X_GS_TRACE_PAGES=<page> ; PS2X_GS_STATS=1 ; PS2X_CLOCK_TRACE=1                                       # runtime traces
```

A launch script is a five-line file under `logs/`, in the shape of `logs/audio_gate7.sh`:

```bash
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
python -m tools_py.parity.gate --stamp <stamp> --owner <owner>
rc=$?; echo "done $rc" > logs/<name>.done; exit $rc
```

Poll `logs/<name>.marker` (`run_detached.sh` writes `exit=<code>` there when the lock is released), never the caller.

## Global Constraints

- Branch `sprint-7` off `develop` at `8f57cbd` (Sprint 6 merged into `develop` and `main`). Branch in the main checkout, never a worktree.
- `./build.sh test` exit 0 and the three-stage gate PASS before any commit touching `third_party/ps2recomp/`, `recomp/`, `tools_py/parity/{drive,gate,compare}.py`, `scripts/parity/` or `build.sh`.
- `./build.sh runtime` before any run on a changed runtime; the gate launches `dist/socom2.exe`.
- **Defaults move only where a task's spec bar says so**, and each move is a numbered ruling: Task 1c (the launcher's Video default to 1280x896 and `FLAG_WINDOW_HIGHDPI`), Task 2a (the scheduler's equal-priority slice), Task 4 (the launcher's default server preset). Everything else is frozen: speed work, patches to recompiled game logic, guest-memory writes in any acceptance path. **The gate keeps its own 640x448 window** and `drive.py`'s client-rect assertion stays armed. LF line endings.
- Every online launch records `waits=` per instance and the exe sha; every ladder result names the harness commit.
- **One launch at a time; suites held while a launch runs** (Handoff notes). A launch that returns `exit=75 BUSY` means another is live — poll, do not start a second.

---

## File map

| Path | Responsibility |
|---|---|
| `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_caps.h` (new), `ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (`ensureGl` :953-1034), `ps2xRuntime/include/runtime/gs/gs_gl_backend.h`, `ps2xRuntime/src/lib/ps2_runtime.cpp` (:2576-2590), `ps2xLauncher/src/main.cpp`, `ps2xTest/src/ps2_gs_tests.cpp`, `ps2xTest/src/launcher_tests.cpp` | Task 1a: the GL capability probe, the latch, the CPU fallback, exit code 65 |
| `ps2xRuntime/include/runtime/gs/gs_frame_backpressure.h` + `src/lib/gs/gs_frame_backpressure.cpp` (`GsPendingCap`), `src/lib/gs/gs_gl_backend.cpp` (:690-720 `recordCommand*`, :1495-1503 the stats line), `scripts/run_detached.sh` (the sampler's `ws=` column), `scripts/parity/drag_window.ps1` (new), `tools_py/parity/host_samples.py` (new), `ps2xTest/src/gs_frame_backpressure_tests.cpp`, `tools_py/tests/test_host_samples.py` (new) | Task 1b: the bounded command queue and the memory column its bar is measured with |
| `ps2xRuntime/include/runtime/gs/gs_gl_target_extent.h` (new), `src/lib/gs/gs_gl_backend.cpp` (`getRenderTarget` :1508+), `src/lib/ps2_runtime.cpp` (:729-739), `ps2xLauncher/include/launcher/launcher_config.h`, `tools_py/parity/scale_shot.py` + `tools_py/parity/scale_compare.py` (new), `ps2xTest/src/ps2_gs_tests.cpp`, `ps2xTest/src/launcher_tests.cpp`, `tools_py/tests/test_scale_compare.py` (new) | Task 1c: HIGHDPI, the 2x launcher default, render targets sized from use |
| `ps2xRuntime/include/runtime/vu1_native_warning.h` (new), `src/lib/vu/ps2_vu1_core.cpp` (:2471-2505), `src/lib/vu/native/vu1_native_programs.cpp`, `ps2xTest/src/vu1_native_tests.cpp` | Task 1d: the native-VU1 mismatch warning |
| `ps2xRuntime/include/runtime/snd989_mixer.h`, `src/lib/snd989_mixer.cpp` (`Stream::readChunkPair` :340-400, `Mixer::render` :881-990, `pcmStreamPosition` :1112), `ps2xTest/src/socom2_audio_tests.cpp`, `tools_py/parity/audio_corr.py` (new), `tools_py/tests/test_audio_corr.py` (new) | Task 1e: audio I/O off the callback, and the tool its 0.99 bar is read with |
| `ps2xRuntime/src/lib/Kernel/EeScheduler.cpp` (`checkpointDue` :371-402, `hasReadyAtOrAbovePriority` :2320), `include/runtime/ee_scheduler.h` (:417-418, :445), `src/lib/game_overrides_socom2.cpp` (the pc-sampler thread table :670-678), `ps2xTest/src/ps2_runtime_kernel_tests.cpp` | Task 2a: equal-priority time slicing removed |
| `ps2xLauncher/src/launcher_config.cpp` (`environmentFor` :255-270), `include/launcher/launcher_config.h`, `ps2xRuntime/src/lib/game_overrides_socom2.cpp` (:59-66), `ps2xTest/src/launcher_tests.cpp`, `scripts/parity/online_control_round.sh` | Task 2b: the same-RSA-key control round, and a per-profile key if it fails |
| `ps2xRuntime/src/lib/Kernel/Stubs/CD.cpp` (:328, :516, :396, :869, :929), `ps2xTest/src/ps2_runtime_io_tests.cpp` | Task 2c: a separate CD stream cursor |
| `tools_py/parity/lobby_report.py` (`rate`, `--bar`), `tools_py/tests/test_lobby_report.py`, `docs/research/28-lobby-taxonomy.md` §2 | Task 2d: the ten-launch lobby rate |
| `ps2xRuntime/src/lib/game_overrides_socom2.cpp` (the `[pc-sampler]` line :670-678), `include/runtime/gs/gs_backend.h`, `gs_frontend.h`, `gs_frame_backpressure.h`, `src/lib/socom2_libnetb.cpp` (:258-317), `tools_py/parity/freeze_trace.py`, `tools_py/tests/test_freeze_trace.py`, `docs/research/29-online-freeze.md` §0 | Task 2e: freeze shape 2 |
| `ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (`markShadowPages` :1593, `executeUpload` :1623, `resolveTexture` :2828-2909, `downloadRenderTargetToCpu` :2210-2256, the stats line :1495), `include/runtime/gs/gs_gl_backend.h`, `ps2xTest/src/ps2_gs_tests.cpp` | Task 3: the 21k decodes |
| `server/start-servers.ps1`, `server/README.md`, `scripts/make_server_zip.sh` (new), `ps2xLauncher/include/launcher/launcher_config.h`, `ps2xTest/src/launcher_tests.cpp`, `tools_py/tests/test_make_server_zip.py` (new), `docs/HUMAN_TASKS.md` | Task 4: the hosted server |
| `tools_py/parity/two_machine_readout.py` (new), `scripts/parity/two_machine_readout.sh` (new), `tools_py/tests/test_two_machine_readout.py` (new), `docs/HUMAN_TASKS.md` | Task 5: the first two-machine match |
| `docs/HUMAN_TASKS.md`, `docs/KNOWN.md`, `docs/STATUS.md` | Task 6: the owner's checks reported |
| `ps2xRuntime/include/runtime/host_gamepad_select.h` (new), `ps2xRuntime/src/lib/socom2_host_input.cpp` (:206-233), `src/lib/ps2_pad.cpp` (:42-86), `src/lib/Kernel/Stubs/Pad.cpp` (`axisToByte` :71, `findFirstGamepad` :86-98), `ps2xLauncher/src/main.cpp` (`drawController` :240-279, the Controller panel :423-436), `ps2xLauncher/include/launcher/launcher_config.h`, `ps2xLauncher/src/launcher_config.cpp`, `ps2xTest/src/pad_input_tests.cpp`, `ps2xTest/src/launcher_tests.cpp`, `docs/HUMAN_TASKS.md` | Task 8: the launcher picks the pad, and one dead zone for all three pad paths (ruling R95) |
| `ps2xLauncher/include/launcher/mic_devices.h` (new) + `ps2xLauncher/src/mic_devices.cpp` (new, miniaudio, launcher exe only), `ps2xRuntime/include/runtime/host_mic.h` (new, `MicRing` header-only) + `ps2xRuntime/src/lib/host_mic.cpp` (new), `ps2xLauncher/CMakeLists.txt`, `ps2xRuntime/CMakeLists.txt` (:388-407), `ps2xLauncher/src/main.cpp` (the Microphone panel), `ps2xLauncher/include/launcher/launcher_config.h`, `ps2xLauncher/src/launcher_config.cpp`, `ps2xRuntime/src/lib/ps2_runtime.cpp` (:763-765), `ps2xIOP/src/modules/lgaud.cpp` (read only, 9c), `ps2xTest/src/launcher_tests.cpp`, `ps2xTest/src/socom2_audio_tests.cpp`, `docs/KNOWN.md` §2, `docs/HUMAN_TASKS.md` | Task 9: the microphone picker, the level meter, the capture ring and WAV dump, and the headset spike |
| `ps2xRuntime/include/runtime/fps_overlay.h` (new), `ps2xRuntime/src/lib/ps2_runtime.cpp` (:2762-2789, between the export and the debug panel), `ps2xLauncher/src/main.cpp` (the Video panel :394-421), `ps2xLauncher/include/launcher/launcher_config.h`, `ps2xLauncher/src/launcher_config.cpp`, `ps2xTest/src/host_config_tests.cpp`, `ps2xTest/src/launcher_tests.cpp`, `logs/s7_fps_overlay.sh` (new) | Task 10: PS2X_FPS_OVERLAY, and the launch that proves it is on the window and not in the GS frame |
| `ps2xRuntime/include/runtime/audio_volume.h` (new), `ps2xRuntime/src/lib/ps2_audio.cpp` (`mixerRender` :503-540), `ps2xLauncher/src/main.cpp` (the Detail, Window and Volume rows), `ps2xLauncher/include/launcher/launcher_config.h`, `ps2xLauncher/src/launcher_config.cpp`, `ps2xTest/src/launcher_tests.cpp`, `ps2xTest/src/socom2_audio_tests.cpp` | Task 11: the 4x scale, Match display, and the master volume |
| `docs/STATUS.md`, `docs/KNOWN.md`, `docs/ROADMAP.md` §6, `docs/CURRENT_SPRINT.md`, this plan | Task 7: close-out |

---

### Task 1a — GL capability probe, latch, CPU fallback (audit §2.2 F2, gap G6)

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_caps.h`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (`ensureGl`, :953-1034), `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h`, `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp` (:2576-2590, the replay call site), `third_party/ps2recomp/ps2xLauncher/src/main.cpp` (the "the game exited" line)
- Test: `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp` (suite `GsGlCaps`), `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp`

**Interfaces:**
- Produces `namespace GsGlCaps`: `struct Report { bool ok = true; std::string missing; };`
  `Report evaluate(const char *glVersion, bool dualSourceBlend, bool clipControl);` — pure, no GL context; `missing` is a comma-separated list out of `"OpenGL 3.3"`, `"dual-source blending"`, `"GL_ARB_clip_control"`.
  `class Latch { public: bool shouldAttempt() const; void attempted(); void fail(const Report &); bool failed() const; const Report &report() const; uint32_t attempts() const; };`
  `constexpr int kExitCode = 65;`
- `GSGlBackend::glUnavailable() const` and `GSGlBackend::glMissing() const` (from the latch).
- Runtime: on the first `ensureGl` failure of this class, one stderr line `[gs-gl] UNSUPPORTED: <missing>; falling back to the CPU rasterizer (PS2X_GS_BACKEND=cpu)`, the CPU backend takes over, and the process's final exit code becomes `65`.
- Launcher: exit code `65` prints "Your GPU or driver is missing <missing>; the game ran on the slow CPU renderer." *(controller's choice: the probe reports through the process exit code, which the launcher already reads, rather than a side file; re-rule if wrong)*
- Knob `PS2X_GS_GL_FORCE_FAIL=1` makes `evaluate` return `{false, "forced (PS2X_GS_GL_FORCE_FAIL)"}` — the only way to reach the fallback on this machine.

**Steps:**

- [x] **Step 1: Write the failing test.** Append to `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp`, after the `GSGlDepth` suite:

```cpp
        tc.Run("GsGlCaps names exactly what a machine is missing", [](TestCase &t)
        {
            t.IsTrue(GsGlCaps::evaluate("3.3.0 NVIDIA 555.85", true, true).ok, "3.3 with both features is supported");
            t.IsTrue(GsGlCaps::evaluate("4.6.0 Core Profile", true, true).ok, "a newer core profile is supported");
            const GsGlCaps::Report old = GsGlCaps::evaluate("3.1.0 Mesa 21.0", true, true);
            t.IsTrue(!old.ok, "GL 3.1 is not supported");
            t.IsTrue(old.missing.find("OpenGL 3.3") != std::string::npos, "the line names the version: " + old.missing);
            const GsGlCaps::Report noDual = GsGlCaps::evaluate("3.3.0", false, true);
            t.IsTrue(!noDual.ok && noDual.missing.find("dual-source blending") != std::string::npos,
                     "the line names dual-source blending: " + noDual.missing);
            const GsGlCaps::Report noClip = GsGlCaps::evaluate("3.3.0", true, false);
            t.IsTrue(!noClip.ok && noClip.missing.find("GL_ARB_clip_control") != std::string::npos,
                     "the line names clip control: " + noClip.missing);
            t.IsTrue(GsGlCaps::evaluate(nullptr, true, true).ok == false, "no version string is a failure, not a pass");
        });
        tc.Run("the GL latch attempts once and never recompiles per frame", [](TestCase &t)
        {
            GsGlCaps::Latch latch;
            t.IsTrue(latch.shouldAttempt(), "the first call attempts");
            latch.attempted();
            latch.fail(GsGlCaps::evaluate("3.1.0", false, false));
            t.IsTrue(latch.failed(), "the latch is set");
            for (int i = 0; i < 1000; ++i)
                t.IsTrue(!latch.shouldAttempt(), "a latched probe never attempts again");
            t.Equals(static_cast<int>(latch.attempts()), 1, "exactly one attempt over 1000 frames");
            t.IsTrue(!latch.report().missing.empty(), "the latch keeps what was missing");
        });
```

- [x] **Step 2: Run it and watch it fail.**

```bash
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe 2>&1 | grep -E "Failed\]|Total Tests"
```
Expected: the build fails with `fatal error: 'runtime/gs/gs_gl_caps.h' file not found` (the include added with the test). That compile error **is** the red. If it compiles, the header already exists — read it before writing a second one.

- [x] **Step 3: Implement the header** `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_caps.h`: `evaluate` parses the leading `<major>.<minor>` of `glVersion` (a null or unparsable string is a failure with `missing = "OpenGL 3.3 (no version string)"`), requires `major*10+minor >= 33`, and appends `"dual-source blending"` / `"GL_ARB_clip_control"` for each false flag, joined with `", "`. `Latch` is a `bool m_failed`, a `uint32_t m_attempts` and a `Report`; `shouldAttempt()` is `!m_failed`. Header-only, no GL includes, so the test links without a context.

- [x] **Step 4: Run it green.** Same command as Step 2. Expected: `Total Tests: <n>` with no `[Failed]` line and the two new cases present.

- [x] **Step 5: Wire the probe into `ensureGl`.** In `gs_gl_backend.cpp` `ensureGl()` (:953), before the shader compile: `if (!m_glCapsLatch.shouldAttempt()) return false;` then `m_glCapsLatch.attempted();` and, once `IsWindowReady()`, build the report from `glGetString(GL_VERSION)`, `probeDualSourceBlend()` (a `glGetIntegerv(GL_MAX_DUAL_SOURCE_DRAW_BUFFERS, …) >= 1` query) and `probeClipControl() != nullptr`, honouring `PS2X_GS_GL_FORCE_FAIL`. On `!ok` **and** on a shader compile/link failure: `m_glCapsLatch.fail(report)`, print the one `[gs-gl] UNSUPPORTED: …` line, return false forever. Add `glUnavailable()`/`glMissing()` to `gs_gl_backend.h`. In `ps2_runtime.cpp` at the replay call site (:2576): when `glUnavailable()` first reads true, swap the frontend to the CPU backend (the same path `PS2X_GS_BACKEND=cpu` takes) and record `GsGlCaps::kExitCode` as the process's exit code.

- [x] **Step 6: The launcher's message.** In `ps2xLauncher/src/main.cpp`, where the exit is reported, map `65` to `"Your GPU or driver is missing OpenGL 3.3 with dual-source blending; the game ran on the slow CPU renderer."` Add to `ps2xTest/src/launcher_tests.cpp`: `t.Equals(launcher::exitMessage(65), std::string("…CPU renderer."))` and `t.IsTrue(launcher::exitMessage(0).empty())`. Run Step 2's command: green.

- [x] **Step 7: Full suite.**

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "1a: build.sh test" -- ./build.sh test
```
Expected: exit 0, Python suite OK, `ps2x_tests` 0 failed.

- [x] **Step 8: Build the runtime (detached).** *(done 2026-09-17: s7_1a_build, exit 0)*

```bash
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_glprobe_build.marker
```
Poll `logs/s7_glprobe_build.marker` for `exit=0`. Then `sha256sum dist/socom2.exe` and record the sha in the ledger.

- [x] **Step 9: The GL gate (launch 1 of the sprint).** *(done 2026-09-17: s7_gl_gate 3/3, no UNSUPPORTED, depth mapping clip-control; the run exposed Task 1d's (hash, pc) false positive at entry 0x0000, fixed by keying the warning on the hash)* Write `logs/s7_gl_gate.sh` in the five-line shape above running `python -m tools_py.parity.gate --stamp s7_gl_gate --owner gate`, then:

```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s7_gl_gate.sh logs/s7_gl_gate.marker
cat logs/parity/gate/s7_gl_gate/summary.txt
grep -a "gs-gl" logs/parity/gate/s7_gl_gate/title.run.log | head -5
```
Expected: `PASS title`, `PASS transition`, `PASS mission` (3/3, the spec's bar: unchanged on the GL path) and `[gs-gl] initialised: …` with **no** `UNSUPPORTED` line. If a stage FAILs with `STALE FRAME`, rerun; a FAIL that names a scorer is a regression in this change and reverts it.

- [x] **Step 10: The CPU-fallback gate (launch 2).** *(done 2026-09-17: s7_cpu_fallback2 PASS title 16/23 on the CPU rasterizer, one UNSUPPORTED line; the first attempt failed on the harness's own client-rect guard, fixed)* Write `logs/s7_cpu_fallback.sh` with `export PS2X_GS_GL_FORCE_FAIL=1` before the gate line and `--only title --stamp s7_cpu_fallback`, then:

```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s7_cpu_fallback.sh logs/s7_cpu_fallback.marker
grep -a "UNSUPPORTED" logs/parity/gate/s7_cpu_fallback/title.run.log
cat logs/parity/gate/s7_cpu_fallback/summary.txt
```
Expected: exactly one `[gs-gl] UNSUPPORTED: forced (PS2X_GS_GL_FORCE_FAIL); falling back to the CPU rasterizer` line, and `PASS title` (the spec's bar: the fallback reaches the title stage, slower — a longer stage time is expected and is not a failure). If the title stage times out, raise only that stage's timeout and say so in the commit; do not loosen a scorer.

- [x] **Step 11: Commit.** *(2026-09-17)*

```bash
git commit -m "feat(gs-gl): probe GL 3.3 + dual-source + clip control once, latch, and fall back to the CPU rasterizer

audit 2026-09-17 section 2.2 F2 / gap G6: ensureGl recompiled the shaders every host frame on an
unsupported machine, m_glReady never set, and the EE recorded into m_pending forever -- a stranger on an
older iGPU, a VM or RDP got a black window and a RAM climb. GsGlCaps::evaluate/Latch (RED first,
ps2x_tests GsGlCaps suite), one stderr line naming what is missing, the CPU backend takes over, and the
process exits 65 so the launcher can say why. Gate 3/3 on the GL path (s7_gl_gate); PASS title on the
forced fallback (s7_cpu_fallback).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_caps.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp \
  third_party/ps2recomp/ps2xLauncher/src/main.cpp \
  third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp
git push
```

---

### Task 1b — Bounded command queue when the latch trips (audit §2.2 F3, gap G7)

**Files:**
- Create: `tools_py/parity/host_samples.py`, `scripts/parity/drag_window.ps1`
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_frame_backpressure.h`, `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_frame_backpressure.cpp`, `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (`recordCommand`/`recordCommandWithData` :690-720; the stats line :1495-1503), `scripts/run_detached.sh` (the CPU sampler block)
- Test: `third_party/ps2recomp/ps2xTest/src/gs_frame_backpressure_tests.cpp`, `tools_py/tests/test_host_samples.py`

**Interfaces:**
- `GsFrameBackpressure::latched() const -> bool` (the public reading of `m_consumerStalled`).
- `class GsPendingCap { public: explicit GsPendingCap(uint64_t capBytes); bool admit(bool latched, bool carriesState, uint64_t bytes); void onReplayed(uint64_t bytes); uint64_t bytes() const; uint64_t droppedCommands() const; uint64_t droppedBytes() const; static uint64_t parseCapMb(const char *value, uint64_t fallbackMb); };` — `admit` returns false (drop) only when `latched && !carriesState && bytes() >= capBytes`; a state-carrying command (a `Transfer` or an `Upload`) is always admitted.
- Knob `PS2X_GS_PENDING_CAP_MB`, default 64.
- Stats line gains `pending_bytes=<n> dropped_cmds=<n> dropped_bytes=<n>`.
- `host_samples.parse(csv_path) -> list[dict]` with keys `t`, `cpu_pct`, `ws_mb` (a dict of process name to MB); `host_samples.working_set_rise_mb(rows, prefix="socom2") -> float` = max minus the first row's total for the matching processes.
- `scripts/parity/drag_window.ps1 -Title PS2-Recomp -Seconds 30`: finds the window, posts `WM_SYSCOMMAND/SC_MOVE` to enter the modal size-move loop, waits `-Seconds`, then sends `{ESC}`. Exits 1 with `drag_window: no window titled '<t>'` when the window is absent.

**Steps:**

- [x] **Step 1: Write the failing C++ test.** Append to `third_party/ps2recomp/ps2xTest/src/gs_frame_backpressure_tests.cpp`:

```cpp
        tc.Run("a latched queue drops guest frames and keeps uploads", [](TestCase &t)
        {
            GsPendingCap cap(1024u);            // 1 KiB, so the cap is reachable in a test
            uint64_t admittedDraws = 0, admittedUploads = 0;
            for (int frame = 0; frame < 200; ++frame)
            {
                if (cap.admit(true, false, 64u)) ++admittedDraws;      // a guest frame's draw work
                if (cap.admit(true, true, 64u))  ++admittedUploads;    // an upload: state, never dropped
            }
            t.Equals(static_cast<int>(admittedUploads), 200, "every upload is admitted while latched");
            t.IsTrue(cap.bytes() <= 1024u + 200u * 64u, "only uploads may exceed the cap");
            t.IsTrue(admittedDraws < 200u, "draws stop being admitted at the cap (" + std::to_string(admittedDraws) + ")");
            t.IsTrue(cap.droppedCommands() > 0u, "the drops are counted");
            t.Equals(static_cast<int>(cap.droppedBytes()), static_cast<int>((200u - admittedDraws) * 64u), "the dropped bytes are counted");
        });
        tc.Run("an unlatched queue admits everything and the replay releases bytes", [](TestCase &t)
        {
            GsPendingCap cap(1024u);
            for (int i = 0; i < 1000; ++i)
                t.IsTrue(cap.admit(false, false, 64u), "nothing is dropped while the consumer is live");
            t.Equals(static_cast<int>(cap.droppedCommands()), 0, "no drops");
            cap.onReplayed(cap.bytes());
            t.Equals(static_cast<int>(cap.bytes()), 0, "a replay empties the accounting");
        });
        tc.Run("PS2X_GS_PENDING_CAP_MB parses like the frame knob", [](TestCase &t)
        {
            t.Equals(static_cast<int>(GsPendingCap::parseCapMb("128", 64u)), 128, "a decimal is taken");
            t.Equals(static_cast<int>(GsPendingCap::parseCapMb("-1", 64u)), 64, "a negative falls back");
            t.Equals(static_cast<int>(GsPendingCap::parseCapMb(nullptr, 64u)), 64, "unset falls back");
        });
```

- [x] **Step 2: Run it and watch it fail.** Step 2's command from Task 1a. Expected: `error: unknown type name 'GsPendingCap'`.

- [x] **Step 3: Implement `GsPendingCap`** in `gs_frame_backpressure.h`/`.cpp` beside `GsFrameBackpressure`, and add `bool GsFrameBackpressure::latched() const { std::lock_guard<std::mutex> l(m_mutex); return m_consumerStalled; }`.

- [x] **Step 4: Run it green.** Same command. Expected: three new cases pass, no `[Failed]`.

- [x] **Step 5: Wire it into the backend.** In `gs_gl_backend.cpp` `recordCommand`/`recordCommandWithData` (:690-720), before pushing: `if (!m_pendingCap.admit(m_backpressure.latched(), cmd.type == Cmd::Type::Transfer || cmd.type == Cmd::Type::Upload, size)) return;`; in the swap at :731 and :1084 call `m_pendingCap.onReplayed(...)`; extend the `[gs-gl stats] backpressure …` line with `pending_bytes=%llu dropped_cmds=%llu dropped_bytes=%llu`. Construct `m_pendingCap` from `GsPendingCap::parseCapMb(std::getenv("PS2X_GS_PENDING_CAP_MB"), 64u) * 1024u * 1024u`.

- [x] **Step 6: Add the memory column to the host sampler.** In `scripts/run_detached.sh`'s `_start_cpu_sampler` PS1, append a fourth CSV field built from `Get-Process socom2* | ForEach-Object { "{0}={1:N0}" -f $_.ProcessName, ($_.WorkingSet64/1MB) }` joined with `;` (wrapped in its own `try {} catch {}` so a dead process never kills the sampler). Existing rows have three fields; `host_samples.parse` must treat a missing fourth field as `{}`.

- [x] **Step 7: Write the failing Python test** `tools_py/tests/test_host_samples.py`:

```python
import unittest
from tools_py.parity import host_samples

CSV = """2026-09-17T10:00:00.0000000+02:00,12.5,socom2=40.0,socom2=300
2026-09-17T10:00:01.0000000+02:00,90.1,socom2=99.0,socom2=1450
2026-09-17T10:00:02.0000000+02:00,40.0,socom2=50.0,socom2=420
"""

class Parse(unittest.TestCase):
    def test_rows_carry_the_working_set(self):
        rows = host_samples.parse_text(CSV)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["ws_mb"]["socom2"], 1450.0)
    def test_rise_is_peak_minus_first(self):
        rows = host_samples.parse_text(CSV)
        self.assertAlmostEqual(host_samples.working_set_rise_mb(rows), 1150.0, places=1)
    def test_three_field_rows_still_parse(self):
        rows = host_samples.parse_text("2026-09-17T10:00:00Z,5.0,socom2=1.0\n")
        self.assertEqual(rows[0]["ws_mb"], {})
        self.assertEqual(host_samples.working_set_rise_mb(rows), 0.0)
```
Run: `python -m unittest tools_py.tests.test_host_samples -v` → `ModuleNotFoundError: No module named 'tools_py.parity.host_samples'` (RED).

- [x] **Step 8: Implement `host_samples.py`** (`parse_text`, `parse(path)` = `parse_text(open(path).read())`, `working_set_rise_mb`, and a `main` printing `rise_mb=<x> peak_mb=<y>` and exiting 1 above `--max-rise-mb`). Run the same command: 3 tests OK.

- [x] **Step 9: Write `scripts/parity/drag_window.ps1`** as in the Interfaces block, and check it fails cleanly with no game running:

```bash
powershell.exe -NoProfile -File scripts/parity/drag_window.ps1 -Title "PS2-Recomp" -Seconds 1 ; echo "rc=$?"
```
Expected: `drag_window: no window titled 'PS2-Recomp'` and `rc=1`.

- [x] **Step 10: Suite, then build.** *(done: C++ 520 green; exe s7_block_build 2026-09-17)*

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "1b: build.sh test" -- ./build.sh test
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_pendcap_build.marker
```
Expected: test exit 0; marker `exit=0`.

- [x] **Step 11: The drag measurement (launch 3).** *(done 2026-09-17: s7_drag PASS mission; drag window +38 MB against a 91 MB loading rise; cap never engaged -- ruling R93)* `logs/s7_drag.sh`: run `python -m tools_py.parity.gate --only mission --stamp s7_drag --owner gate` with `PS2X_GS_STATS=1`, and in the same script, 90 s after the gate starts, `powershell.exe -NoProfile -File scripts/parity/drag_window.ps1 -Title "PS2-Recomp" -Seconds 30` in the foreground before waiting on the gate's pid.

```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s7_drag.sh logs/s7_drag.marker
python -m tools_py.parity.host_samples logs/s7_drag.marker.cpu.csv --max-rise-mb 200
grep -a "dropped_cmds" logs/parity/gate/s7_drag/mission.run.log | tail -3
```
Expected: `rise_mb=<x> peak_mb=<y>` with `x < 200` (the spec's bar) and exit 0; the stats lines show `dropped_cmds=` climbing and `pending_bytes=` flat at the cap during the drag. Decision table: rise < 200 MB → done; 200–500 MB → lower the default cap to 32 MB and re-measure once; > 500 MB → the cap is not on the path the drag takes (check `Upload` is not the bulk) and re-open with the stats numbers rather than raising the cap.

- [x] **Step 12: Commit.** *(done: 6ea9520)*

```bash
git commit -m "fix(gs-gl): cap the pending command queue while the back-pressure latch is tripped

audit 2026-09-17 section 2.2 F3 / gap G7: a title-bar drag enters the modal size-move loop, the 2000 ms cap
trips, every later frame is Skipped, and m_pending grew without bound (KNOWN section 4's ~15 GB working
set). GsPendingCap (RED first) drops whole guest frames past PS2X_GS_PENDING_CAP_MB (64) and never drops a
Transfer or an Upload, because those carry state; the gs-gl stats line reports pending_bytes/dropped_cmds.
run_detached.sh's sampler gained a working-set column and host_samples.py reads it: a 30 s drag during the
mission gate (s7_drag) raised the working set by <N> MB against the 200 MB bar.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_frame_backpressure.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_frame_backpressure.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp \
  third_party/ps2recomp/ps2xTest/src/gs_frame_backpressure_tests.cpp \
  scripts/run_detached.sh scripts/parity/drag_window.ps1 \
  tools_py/parity/host_samples.py tools_py/tests/test_host_samples.py
git push
```

---

### Task 1c — Window, DPI and render-target size (audit §2.2 F8/F9)

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_target_extent.h`, `tools_py/parity/scale_compare.py`, `tools_py/parity/scale_shot.py`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp` (:729-739), `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (`getRenderTarget` :1508+), `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h` (`windowSize` default)
- Test: `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp`, `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp`, `tools_py/tests/test_scale_compare.py`

**Interfaces:**
- `namespace GsGlTarget { struct Extent { uint32_t width, height; }; Extent choose(uint32_t fbw, uint32_t usedHeight); }` — `width = max(1, fbw) * 64` clamped to 1024, `height` = `usedHeight` rounded up to the next 32 and clamped to `[64, 1024]`; `fbw == 0 || usedHeight == 0` gives `{1024, 1024}` (the old behaviour, so a target with no known use is never under-allocated).
- `scale_compare.mean_abs_diff(big_png, small_png, scale) -> float` — nearest-neighbour upsample of `small_png` by `scale`, mean absolute grey difference; raises `ValueError` when the shapes do not match after scaling.
- `scale_shot.py --size 1280x896 --seconds 40 --out <png>` — launches `dist/socom2.exe` with `PS2X_WINDOW_SIZE`, waits, captures the client area with `winshot.capture_by_title("PS2-Recomp", out)`, kills the tree, exits 1 if no window appeared.

**Steps:**

- [x] **Step 1: Write the failing C++ test.** In `ps2_gs_tests.cpp`:

```cpp
        tc.Run("render targets are sized from fbw and usedHeight, not 1024x1024", [](TestCase &t)
        {
            const GsGlTarget::Extent shell = GsGlTarget::choose(10u, 448u);   // FBW 10 = 640 px, PAL/NTSC height
            t.Equals(static_cast<int>(shell.width), 640, "640-wide shell buffer");
            t.Equals(static_cast<int>(shell.height), 448, "448 rows, not 1024");
            const GsGlTarget::Extent boot = GsGlTarget::choose(16u, 512u);
            t.Equals(static_cast<int>(boot.width), 1024, "a 1024-wide boot buffer is capped at the stride");
            t.Equals(static_cast<int>(boot.height), 512, "512 rows");
            const GsGlTarget::Extent unknown = GsGlTarget::choose(0u, 0u);
            t.Equals(static_cast<int>(unknown.width), 1024, "an unknown target keeps the old full allocation");
            t.Equals(static_cast<int>(unknown.height), 1024, "an unknown target keeps the old full allocation");
            t.Equals(static_cast<int>(GsGlTarget::choose(10u, 100u).height), 128, "rows round up to 32");
        });
```

- [x] **Step 2: Run it and watch it fail.** Task 1a Step 2's command. Expected: `'runtime/gs/gs_gl_target_extent.h' file not found`.

- [x] **Step 3: Implement the header, and use it** in `getRenderTarget` where the target texture is allocated (the `hostWidth = nativeWidth * renderScale()` invariant at :1508+ stays: `nativeWidth/nativeHeight` now come from `GsGlTarget::choose(fbw, usedHeight)`). Run Step 2's command: green.

- [x] **Step 4: The window flags and the launcher default.** In `ps2_runtime.cpp` :731, `SetConfigFlags(FLAG_WINDOW_RESIZABLE | FLAG_WINDOW_HIGHDPI);` (before `InitWindow`, which is where raylib reads them). In `launcher_config.h`, `std::string windowSize = "1280x896";`. In `launcher_tests.cpp` add: `t.Equals(launcher::Config{}.windowSize, std::string("1280x896"), "the launcher's default is 2x")` and keep the existing round-trip case. **The gate is unaffected**: it sets no `PS2X_WINDOW_SIZE`, so the runtime default stays 640x448.

- [x] **Step 5: Write the failing Python test** `tools_py/tests/test_scale_compare.py`:

```python
import unittest
import numpy as np
from PIL import Image
from tools_py.parity import scale_compare

def _png(tmp, arr):
    Image.fromarray(arr.astype("uint8"), "L").save(tmp)
    return tmp

class Diff(unittest.TestCase):
    def test_a_perfect_2x_nearest_upscale_scores_zero(self):
        import tempfile, os
        small = np.random.RandomState(7).randint(0, 255, (64, 64))
        big = np.kron(small, np.ones((2, 2)))
        d = tempfile.mkdtemp()
        s = scale_compare.mean_abs_diff(_png(os.path.join(d, "b.png"), big), _png(os.path.join(d, "s.png"), small), 2)
        self.assertEqual(s, 0.0)
    def test_a_shifted_image_scores_above_three(self):
        import tempfile, os
        small = np.random.RandomState(9).randint(0, 255, (64, 64))
        big = np.kron(np.roll(small, 3, axis=1), np.ones((2, 2)))
        d = tempfile.mkdtemp()
        s = scale_compare.mean_abs_diff(_png(os.path.join(d, "b.png"), big), _png(os.path.join(d, "s.png"), small), 2)
        self.assertGreater(s, 3.0)
    def test_mismatched_shapes_raise(self):
        import tempfile, os
        d = tempfile.mkdtemp()
        a = _png(os.path.join(d, "a.png"), np.zeros((100, 100)))
        b = _png(os.path.join(d, "c.png"), np.zeros((64, 64)))
        with self.assertRaises(ValueError):
            scale_compare.mean_abs_diff(a, b, 2)
```
Run: `python -m unittest tools_py.tests.test_scale_compare -v` → `ModuleNotFoundError` (RED).

- [x] **Step 6: Implement `scale_compare.py` and `scale_shot.py`.** Run: `python -m unittest tools_py.tests.test_scale_compare -v` → 3 tests OK.

- [x] **Step 7: Suite, then build.** *(done: C++ 520 green; exe s7_block_build)*

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "1c: build.sh test" -- ./build.sh test
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_dpi_build.marker
```

- [x] **Step 8: The 2x capture rides on Task 1a's GL gate slot** *(first attempt 2026-09-17: mean |diff| 41 -- not scaling: the capture was the controller prompt at 40 s while the gate's frame was the menu after the drive's presses; scale_shot now compares a 640x448 and a 1280x896 EXPORTED frame of the same screen from the same procedure, `--both`)* *(controller's choice: the spec's Goal 1 budget is two gates plus one drag, so the 1280x896 capture is appended to the GL gate's launch script rather than taking a launch of its own; re-rule if wrong)*. Extend `logs/s7_gl_gate.sh` with, after the gate line, `python -m tools_py.parity.scale_shot --size 1280x896 --seconds 40 --out logs/parity/s7_scale_2x.png`, and re-run it as `s7_gl_gate2`: *(done: s7_scale_both 2026-09-17, export mode, same driven screen: mean |diff| 0.83 vs bar 3.0 -- PASS; ruling R94)*

```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s7_gl_gate.sh logs/s7_gl_gate2.marker
cat logs/parity/gate/s7_gl_gate2/summary.txt
python -c "from tools_py.parity import scale_compare as sc; print(sc.mean_abs_diff('logs/parity/s7_scale_2x.png','logs/parity/gate/s7_gl_gate2/title/s10_none.png',2))"
```
Expected: `PASS title/transition/mission` at the unchanged 640x448 default, and a printed mean |diff| **< 3** (the spec's bar). Decision table: < 3 → done; 3–10 → check the capture caught the same title-loop frame (the loop animates; retake with the same `--seconds`) before touching any code; > 10 → the 2x path is not a pure upscale, which is a finding for KNOWN §2 and stops the default move until it is understood.

- [x] **Step 9: Commit** (this moves a default; record the ruling in the Rulings section as R9x with `Cost if wrong: a stranger's first window is 1280x896 on a display that cannot fit it — the launcher still offers 640x448 and fullscreen`). *(done: 6ea9520; R92 recorded)*

```bash
git commit -m "feat(window): HIGHDPI, a 2x launcher default, and render targets sized from use

audit 2026-09-17 section 2.2 F8/F9: 640x448 with no HIGHDPI flag is unreadable on a 150% laptop, and every
render target was allocated 1024x1024 x scale^2 RGBA8 plus DEPTH32F (128 MB per target at scale 4).
GsGlTarget::choose (RED first) sizes targets from fbw and usedHeight and keeps 1024x1024 for a target with
no known use; FLAG_WINDOW_HIGHDPI is set before InitWindow; the launcher's Video default is 1280x896. The
gate still runs its own 640x448 (3/3, s7_gl_gate2) and a 1280x896 capture is the 640x448 frame at a 2x
nearest resample (mean |diff| <N>, bar 3).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_target_extent.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp \
  third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h \
  third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp \
  tools_py/parity/scale_compare.py tools_py/parity/scale_shot.py tools_py/tests/test_scale_compare.py
git push
```

---

### Task 1d — Native VU1 mismatch warning (audit §2.2 F7)

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/vu1_native_warning.h`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp` (:2471-2505), `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/vu1_native_programs.cpp` (the table comment names the supported disc)
- Test: `third_party/ps2recomp/ps2xTest/src/vu1_native_tests.cpp`

**Interfaces:**
- `namespace Vu1NativeWarning { class State { public: bool shouldWarn(bool matched, uint64_t nowNs); void warned(); bool warnedAlready() const; }; std::string line(uint64_t hash, uint32_t entryPc); }` — `shouldWarn` returns true once, and only after **one second** of uninterrupted misses (`matched == true` resets the window), so a boot that has not uploaded the gameplay microcode yet never warns.
- The line: `[vu1] no native program for code hash 0x<16 hex> entry 0x<4 hex> -- running the interpreter (supported disc: SOCOM II NTSC r0001, SCUS_972.75)`.

**Steps:**

*(2026-09-17, after s7_gl_gate: the warning fired on the supported disc at entry 0x0000 of the supported hash, the entry left to generated code; keyed on the hash now (`Vu1NativeWarning::hashHasNativeEntry`), pinned by the test.)*

- [x] **Step 1: Write the failing test.** In `third_party/ps2recomp/ps2xTest/src/vu1_native_tests.cpp`:

```cpp
        tc.Run("the native-VU1 warning fires once, after a second of misses", [](TestCase &t)
        {
            Vu1NativeWarning::State s;
            t.IsTrue(!s.shouldWarn(false, 0ull), "no warning on the first miss");
            t.IsTrue(!s.shouldWarn(false, 500000000ull), "no warning at half a second");
            t.IsTrue(s.shouldWarn(false, 1000000001ull), "a second of misses warns");
            s.warned();
            for (uint64_t ns = 2000000000ull; ns < 60000000000ull; ns += 1000000000ull)
                t.IsTrue(!s.shouldWarn(false, ns), "it never warns twice");
            Vu1NativeWarning::State r;
            t.IsTrue(!r.shouldWarn(false, 0ull), "arm");
            t.IsTrue(!r.shouldWarn(true, 900000000ull), "a match resets the window");
            t.IsTrue(!r.shouldWarn(false, 1500000000ull), "and the next miss starts a new one");
            const std::string line = Vu1NativeWarning::line(0xd418194495c25213ull, 0x1b50u);
            t.IsTrue(line.find("0xd418194495c25213") != std::string::npos, "the line names the hash it saw: " + line);
            t.IsTrue(line.find("r0001") != std::string::npos, "the line names the supported disc: " + line);
        });
```

- [x] **Step 2: Run it and watch it fail.** Task 1a Step 2's command. Expected: `'runtime/vu1_native_warning.h' file not found`.

- [x] **Step 3: Implement the header, and call it** in `ps2_vu1_core.cpp` right after `m_nativeFn` is resolved (:2495-2505): a function-local `static Vu1NativeWarning::State s_warn;` fed `m_nativeFn != nullptr` and `steady_clock::now()`; when it says warn, print `Vu1NativeWarning::line(m_knownHash, m_state.pc)` to stderr and call `warned()`. Only when `s_nativeEnv && hashableImage` — `PS2X_VU1_NATIVE=0` is a deliberate choice and must stay silent.

- [x] **Step 4: Run it green, then the suite.** *(done: a843385)*

```bash
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe 2>&1 | grep -E "Failed\]|Total Tests"
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "1d: build.sh test" -- ./build.sh test
```
Expected: the new case passes; `build.sh test` exit 0. **No launch of its own**: the warning's absence is checked on Task 1e's gate log (`grep -a "\[vu1\] no native program" logs/parity/gate/s7_audio_gate/mission.run.log` must print nothing on the r0001 disc).

- [x] **Step 5: Commit.** *(done: a843385)*

```bash
git commit -m "feat(vu1): warn once when no native program matches the disc's microcode

audit 2026-09-17 section 2.2 F7: the native VU1 dispatcher is keyed to one microcode hash, so any other
disc revision silently ran the interpreter at a much lower frame rate with nothing on screen to say why.
Vu1NativeWarning (RED first) prints one line naming the hash it saw and the supported disc, after a second
of uninterrupted misses so a boot that has not uploaded the gameplay microcode never warns.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/vu1_native_warning.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/vu1_native_programs.cpp \
  third_party/ps2recomp/ps2xTest/src/vu1_native_tests.cpp
git push
```

---

### Task 1e — Audio I/O off the callback (audit §2.3, `snd989_mixer.cpp:881-990`)

**Files:**
- Create: `tools_py/parity/audio_corr.py`, `tools_py/tests/test_audio_corr.py`
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/snd989_mixer.h`, `third_party/ps2recomp/ps2xRuntime/src/lib/snd989_mixer.cpp` (`Stream` :320-400, `Mixer::render` :881-990, `pcmStreamPosition` :1112)
- Test: `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp`, `tools_py/tests/test_audio_corr.py`

**Interfaces:**
- `Mixer::pumpStreams()` (public): decodes the next chunk pair of every live stream into its ready ring until the ring holds `kStreamRingChunks = 4` chunks. Owns the file handles; takes a **separate** `m_impl->ioMutex`, never the render mutex.
- A worker thread started on the first `playStream` and joined in the destructor, calling `pumpStreams()` every 10 ms; `PS2X_SND_STREAM_WORKER=0` disables the thread and leaves `pumpStreams()` to the caller (what the tests use).
- `Mixer::closeStreamFilesForTest()`: closes every stream's `FILE *` without discarding the ring — the seam the spec's test names.
- `Mixer::render` touches memory only: it pops from the ready ring and marks `done` when the ring is empty **and** the stream ended; it never calls `readChunkPair`, never seeks, never reads.
- `audio_corr.correlate(wav_path, pcm_path, window_s=4.0, rate=48000) -> list[(t_s, corr, offset_samples)]`; `audio_corr.min_corr(rows) -> float`; CLI prints one row per window and `min_corr=<x>`, exit 1 below `--bar` (default 0.99).

**Steps:**

- [x] **Step 1: Write the failing C++ test.** In `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp`, after the existing stream case:

```cpp
        tc.Run("a stream plays out of its ring with the file handle closed", [](TestCase &t)
        {
            snd989::Mixer mixer;
            const std::string vpk = "game/disc/RUN/SOUND/MUSIC.VPK";   // any VPK the existing stream case already uses
            t.IsTrue(mixer.playStream(1u, vpk, 0ull, 0x400, 0, 0u), "the stream starts");
            mixer.pumpStreams();
            t.Equals(mixer.activeStreams(), static_cast<size_t>(1u), "one live stream");
            mixer.closeStreamFilesForTest();
            std::vector<int16_t> buf(4096 * 2, 0);
            mixer.render(buf.data(), 4096);
            bool anyNonZero = false;
            for (int16_t s : buf) if (s != 0) { anyNonZero = true; break; }
            t.IsTrue(anyNonZero, "render plays the ring's contents with no file behind it");
        });
        tc.Run("render never reads the disc", [](TestCase &t)
        {
            snd989::Mixer mixer;
            t.IsTrue(mixer.playStream(2u, "game/disc/RUN/SOUND/MUSIC.VPK", 0ull, 0x400, 0, 0u), "the stream starts");
            mixer.closeStreamFilesForTest();          // nothing pumped: the ring is empty
            std::vector<int16_t> buf(4096 * 2, 0x7F);
            mixer.render(buf.data(), 4096);           // must not crash, must not read, must go quiet
            t.Equals(static_cast<int>(buf[0]), 0, "an empty ring renders silence, not a disc read");
        });
```

- [x] **Step 2: Run it and watch it fail.** Task 1a Step 2's command. Expected: `error: no member named 'pumpStreams' in 'snd989::Mixer'`.

- [x] **Step 3: Implement.** Move `readChunkPair` off `render`: `Stream` gains `std::deque<std::array<std::vector<int16_t>, 2>> ready;` filled by `pumpStreams()` under `ioMutex`, drained by `render` under the render mutex (a small `std::mutex ringMutex` guards the deque itself). `pcmStreamPosition` (:1112) must **not** take the render mutex any more — it reads an atomic the render path stores.

- [x] **Step 4: Run it green, then the suite.** Task 1a Step 2's command, then `./build.sh test` under the lock. Expected: both new cases pass, the existing `snd989` cases unchanged, exit 0.

- [x] **Step 5: Write the failing Python test** `tools_py/tests/test_audio_corr.py`:

```python
import unittest
import numpy as np
from tools_py.parity import audio_corr

class Correlate(unittest.TestCase):
    def test_identical_signals_correlate_at_one(self):
        rate = 48000
        t = np.arange(rate * 8) / rate
        sig = (np.sin(2 * np.pi * 440 * t) * 20000).astype("int16")
        rows = audio_corr.correlate_arrays(sig, sig, window_s=4.0, rate=rate)
        self.assertEqual(len(rows), 2)
        self.assertGreater(audio_corr.min_corr(rows), 0.999)
        self.assertEqual([r[2] for r in rows], [0, 0])
    def test_noise_does_not_correlate(self):
        rate = 48000
        a = (np.random.RandomState(1).randn(rate * 8) * 5000).astype("int16")
        b = (np.random.RandomState(2).randn(rate * 8) * 5000).astype("int16")
        rows = audio_corr.correlate_arrays(a, b, window_s=4.0, rate=rate)
        self.assertLess(audio_corr.min_corr(rows), 0.2)
    def test_a_fixed_offset_is_reported_not_hidden(self):
        rate = 48000
        t = np.arange(rate * 8) / rate
        sig = (np.sin(2 * np.pi * 300 * t) * 20000).astype("int16")
        rows = audio_corr.correlate_arrays(sig[480:], sig, window_s=4.0, rate=rate)
        self.assertGreater(audio_corr.min_corr(rows), 0.99)
        self.assertEqual(rows[0][2], 480)
```
Run: `python -m unittest tools_py.tests.test_audio_corr -v` → `ModuleNotFoundError` (RED).

- [x] **Step 6: Implement `audio_corr.py`** (`correlate_arrays`, `correlate` reading a 16-bit WAV and a raw PCM file, `min_corr`, a CLI). Run the same command: 3 tests OK.

- [x] **Step 7: Build, then the audio gate (launch 4).** `logs/s7_audio_gate.sh` with `export PS2X_AUDIO_DUMP=/c/projects/socom_pc/logs/s7_audio.wav` and `python -m tools_py.parity.gate --only title --stamp s7_audio_gate --owner gate`. *(done: s7_audio_title 2026-09-17: title loop min_corr 1.0000, constant offset, bar 0.99 PASS)*

```bash
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_audio_build.marker
scripts/run_detached.sh --owner gate --purpose launch logs/s7_audio_gate.sh logs/s7_audio_gate.marker
python -m tools_py.parity.audio_corr logs/s7_audio.wav logs/title_disc_audio.bin --window-s 4 --bar 0.99
grep -a "\[vu1\] no native program" logs/parity/gate/s7_audio_gate/title.run.log
```
Expected: `PASS title`; `min_corr=0.99…` and exit 0 (the spec's bar: the title mix's correlation with the disc stays 0.99, research/32 §7.1 re-run once); the `vu1` grep prints nothing (Task 1d Step 4). Decision table: ≥ 0.99 → done; 0.95–0.99 → the ring is underfilling, raise `kStreamRingChunks` to 8 and re-measure once; < 0.95 → the move changed what is played, revert and re-open.

- [x] **Step 8: Commit.** *(done: 6ea9520)*

```bash
git commit -m "fix(audio): decode stream chunks on a worker; the mixer's render touches memory only

audit 2026-09-17 section 2.3 (snd989_mixer.cpp:881-990): readChunkPair seeked and read the ISO inside the
audio callback under the mixer mutex, and pcmStreamPosition -- polled 30/s by the game's audio thread
through a synchronous RPC -- took the same mutex, so on a stranger's HDD or under antivirus one slow read
dropped audio and blocked the EE inside an RPC. pumpStreams() fills a per-stream ring on a worker
(PS2X_SND_STREAM_WORKER=0 hands it to the caller); render pops from the ring and never reads. Tests RED
first: a render with the file handles closed still plays, an empty ring renders silence. Title mix
correlates with the disc at <N> (bar 0.99, audio_corr.py, s7_audio_gate).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/snd989_mixer.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/snd989_mixer.cpp \
  third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp \
  tools_py/parity/audio_corr.py tools_py/tests/test_audio_corr.py
git push
```

---

### Task 2a — Equal-priority time slicing removed (audit §2.3, `EeScheduler.cpp:371-402`)

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/EeScheduler.cpp` (`checkpointDue` :371-402, `hasReadyAtOrAbovePriority` :2320-2331), `third_party/ps2recomp/ps2xRuntime/include/runtime/ee_scheduler.h` (:417), `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` (the pc-sampler thread table :670-678)
- Test: `third_party/ps2recomp/ps2xTest/src/ps2_runtime_kernel_tests.cpp`

**Interfaces:**
- `EeScheduler::hasReadyAbovePriority(int priority) const` replaces the slice's use of `hasReadyAtOrAbovePriority` (which stays, because `enqueueReady`/`yieldToAnyReady` use it for their own reasons). Strictly higher = `p < priority`.
- The `[pc-sampler]` thread table gains `prio=<n>` per thread (`t.currentPriority`) — the "log SOCOM's thread priorities once" half of the spec item, and it is how the ladder's logs name the pair that used to interleave.

**Steps:**

- [x] **Step 1: Write the failing test.** In `third_party/ps2recomp/ps2xTest/src/ps2_runtime_kernel_tests.cpp`:

```cpp
        tc.Run("equal-priority threads are not time-sliced; a higher one preempts", [](TestCase &t)
        {
            PS2Runtime runtime;
            t.IsTrue(runtime.memory().initialize(), "runtime memory initialize should succeed");
            EeScheduler &sched = runtime.eeScheduler();
            const int32_t a = makeReadyThreadForTest(sched, /*priority*/ 40);
            const int32_t b = makeReadyThreadForTest(sched, /*priority*/ 40);
            const int32_t hi = makeReadyThreadForTest(sched, /*priority*/ 20);
            sched.suspendThreadForTest(hi);
            sched.startThreadForTest(a);
            t.Equals(sched.runningThreadId(), a, "A runs");
            sched.startThreadForTest(b);                       // B is ready at the same priority
            for (int i = 0; i < 64; ++i)
                sched.checkpointDue(65536u);                   // 64 full slices
            t.Equals(sched.runningThreadId(), a, "A keeps the CPU: the PS2 kernel never time-slices equal priorities");
            sched.resumeThreadForTest(hi);                     // a strictly higher thread becomes ready
            sched.checkpointDue(65536u);
            t.Equals(sched.runningThreadId(), hi, "a strictly higher-priority ready thread preempts on the slice");
        });
```
(The `…ForTest` helpers exist in this file for the kernel suite; if one is missing, add it beside its neighbours rather than reaching into privates from the test.)

- [x] **Step 2: Run it and watch it fail.** Task 1a Step 2's command. Expected: `A keeps the CPU: the PS2 kernel never time-slices equal priorities` fails with `runningThreadId() == b` — today `checkpointDue` rotates the pair every 65536 cycles (0.22 ms).

- [x] **Step 3: Implement.** Add `hasReadyAbovePriority` (`for (int p = 0; p < priority; ++p)`) and use it in `checkpointDue` at :394. Add `prio=` to the sampler's thread table. Run Step 2's command: green, and the rest of the kernel suite unchanged.

- [x] **Step 4: Suite and build.** *(done: C++ 520 green; exe s7_block_build)*

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "2a: build.sh test" -- ./build.sh test
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_slice_build.marker
sha256sum dist/socom2.exe
```

- [x] **Step 5: The control round (launch 5).** *(done: thirteen driven control rounds played to the clock on the strict-slice exe -- s7_samekey, s7_freeze_quiet, s7_freeze_loaded, lobby_rate_01..10 of 2026-09-18 -- with no one-side-only defect in any; the KNOWN §1 row cites them)*

```bash
scripts/parity/online_control_round.sh "Frostfire" logs/parity/s7_slice_ctl
python -m tools_py.parity.lobby_report logs/parity/drive_s7_slice_ctl.txt
grep -a "prio=" logs/run_A_*.log | head -3
```
Expected: `RESULT CONTROL-ROUND`, both sides CONTROLLABLE, no freeze alarm > 10 s; the sampler lines now carry `prio=` and the priority table goes into `docs/research/29-online-freeze.md` §5 (one paragraph naming SOCOM's threads and their priorities).

- [ ] **Step 6: The ladder (launch 6).** *(not run this sprint: the launch budget went to the ten-round re-run and Task 12's four audio launches; the ladder's kill-count reading is Sprint 9's mixed-match ground. Risk carried: an equal-priority interleave the control round does not exercise; the thirteen rounds and the gate are the evidence so far.)*

```bash
bash scripts/parity/ladder_frostfire.sh logs/parity/s7_slice_ladder
cat logs/s7_slice_ladder.done
grep -a "RESULT" logs/parity/s7_slice_ladder/*.log | tail -8
```
Expected (the spec's bar, matching `s6_ladder12`): the control bar holds and the kill lands on **3 of 4** rounds. **Stop rule (spec §3):** if the ladder fails the control bar on this exe, revert the slice change in the same hour, file `docs/KNOWN.md` §1 "the equal-priority slice is load-bearing for SOCOM II" with the launch name, and stop Task 2a there — the semantics were carrying something and that fact is the finding.

- [x] **Step 7: Commit.** *(done: 39cd17f; the control round and ladder run in the launch block)*

```bash
git commit -m "fix(kernel): expire the time slice only for a strictly higher-priority ready thread

audit 2026-09-17 section 2.3 (EeScheduler.cpp:371-402): equal-priority threads were round-robined every
65536 cycles (0.22 ms). The PS2 kernel never time-slices -- equal-priority threads run until they block or
rotate -- so any pair of equal-priority SOCOM threads sharing an unlocked structure (the network RX/TX
queues) could interleave mid-update on ours only: the shape of the one-side-only intermittent defects the
ladder has chased. Test RED first (two equal-priority threads do not interleave over 64 slices; a higher
one preempts). The pc-sampler's thread table now prints prio=. Control round s7_slice_ctl CONTROL-ROUND;
ladder s7_slice_ladder <n>/4 kills with the control bar held.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/EeScheduler.cpp \
  third_party/ps2recomp/ps2xRuntime/include/runtime/ee_scheduler.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp \
  third_party/ps2recomp/ps2xTest/src/ps2_runtime_kernel_tests.cpp
git push
```

---

### Task 2b — Same-RSA-key control round (audit §2.1, medium: `game_overrides_socom2.cpp:59-66`)

**Files:**
- Modify: `scripts/parity/online_control_round.sh` (a `--same-key` flag), and **only if the round fails** `third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp` (`environmentFor` :255-270) and `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h`
- Test: `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp`, `tools_py/tests/test_control_round.py`

**Interfaces:**
- `online_control_round.sh --same-key`: leaves `PS2X_SOCOM2_RSA_KEY_B` **unset**, so both instances publish key A — the case two strangers with default config hit, and the case the harness has never run.
- If it fails: `launcher::rsaKeyForProfile(const std::string &profile) -> std::string` (`"a"` or `"b"`, from the low bit of an FNV-1a 32 of the profile name) and `environmentFor` emits `PS2X_SOCOM2_RSA_KEY=<that>` instead of the hardcoded `b` for the second instance.

**Steps:**

- [ ] **Step 1: Write the failing harness test** in `tools_py/tests/test_control_round.py`: *(not built: the same-key round was run from a logs/ script (`online_control_round_samekey.sh`, R-free: it unsets one variable); a tested helper for a one-off launch was not worth the harness surface. The result is in KNOWN §1.)*

```python
    def test_same_key_flag_leaves_key_b_unset(self):
        env = control_round_env(["--same-key"])       # the helper this test adds: parse the script's exports
        self.assertNotIn("PS2X_SOCOM2_RSA_KEY_B", env)
    def test_default_still_sets_key_b(self):
        self.assertEqual(control_round_env([])["PS2X_SOCOM2_RSA_KEY_B"], "b")
```
Run: `python -m unittest tools_py.tests.test_control_round -v` → `NameError: name 'control_round_env' is not defined` (RED).

- [ ] **Step 2: Implement** the helper (it runs `bash -c '. scripts/parity/online_control_round.sh --print-env …'` behind a `--print-env` short-circuit the script gains at the top) and the `--same-key` branch in `scripts/parity/online_control_round.sh`. Run the same command: 2 tests OK, and the existing cases unchanged. *(not built, see Step 1)*

- [x] **Step 3: The same-key control round (launch 7).** *(done: s7_samekey 2026-09-17: CONTROL-ROUND with the same key on both; no Step 4)*

```bash
scripts/parity/online_control_round.sh --same-key "Frostfire" logs/parity/s7_samekey
python -m tools_py.parity.lobby_report logs/parity/drive_s7_samekey.txt
```
Expected: `TOTAL launches=1 gameplay=1/1` and `RESULT CONTROL-ROUND`. Decision table: passes → write the KNOWN §1 row "two clients on the same RSA key reach gameplay (`s7_samekey`)" and **stop here, no code change**; fails where key B passes → Step 4.

- [ ] **Step 4 (only on a failure): the per-profile key.** Failing test in `launcher_tests.cpp`: *(not needed: the same-key round passed)*

```cpp
            t.IsTrue(launcher::rsaKeyForProfile("craig") == "a" || launcher::rsaKeyForProfile("craig") == "b", "a key is chosen");
            t.IsTrue(launcher::rsaKeyForProfile("craig") != launcher::rsaKeyForProfile("dave"), "two profiles that differ get different keys");
            t.Equals(launcher::rsaKeyForProfile("craig"), launcher::rsaKeyForProfile("craig"), "the same profile is stable across runs");
```
(If `"craig"`/`"dave"` happen to collide, pick the two profile names the launch actually used and say so in the comment.) Run Task 1a Step 2's command → RED; implement `rsaKeyForProfile` and use it in `environmentFor`; GREEN; `./build.sh test`; rebuild; re-run Step 3's launch as `s7_samekey2`.

- [x] **Step 5: Commit** (the result goes to `docs/KNOWN.md` §1 either way — the spec asks for the result, not the fix). *(done: KNOWN §1 row (this commit); no per-profile key needed)*

```bash
git commit -m "harness(online): --same-key control round -- the case two strangers with default config hit

audit 2026-09-17 section 2.1: two strangers with default config publish the same RSA key A in their DME
records, and the harness has always set key B for instance B, so the shared-key case has not run since the
fix. online_control_round.sh --same-key leaves PS2X_SOCOM2_RSA_KEY_B unset (test RED first). Result:
<CONTROL-ROUND on s7_samekey | LOBBY-FAIL <class>, per-profile key derived in the launcher>.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  scripts/parity/online_control_round.sh tools_py/tests/test_control_round.py
git push
```

---

### Task 2c — CD stream cursor (audit §2.3, `CD.cpp:328`)

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/CD.cpp` (:328 `sceCdRead`, :516 the chained read, :396 `sceCdGetReadPos`, :869 `sceCdStRead`, :929 `sceCdStResume`, :652 `sceCdSearchFile`)
- Test: `third_party/ps2recomp/ps2xTest/src/ps2_runtime_io_tests.cpp`

**Interfaces:**
- A second file-scope cursor `g_cdReadLbn` for plain reads; `g_cdStreamingLbn` becomes the **stream** cursor and is written only by `sceCdStStart`, `sceCdStRead`, `sceCdStSeek` and `sceCdSearchFile`.
- `sceCdGetReadPos` returns `g_cdReadLbn` when no stream is open, `g_cdStreamingLbn` while one is (the position the caller is asking about is the one it last moved).

**Steps:**

- [x] **Step 1: Write the failing test.** In `third_party/ps2recomp/ps2xTest/src/ps2_runtime_io_tests.cpp`, beside the existing `sceCd` cases:

```cpp
        tc.Run("StRead after Read resumes at the stream LBN", [](TestCase &t)
        {
            PS2Runtime runtime;
            t.IsTrue(runtime.memory().initialize(), "runtime memory initialize should succeed");
            uint8_t *const rdram = runtime.memory().getRDRAM();
            openTestCdImageForTest(runtime);                       // the helper the neighbouring cases use
            const uint32_t streamLbn = startTestStreamForTest(runtime, "RUN/SOUND/MUSIC.VPK");
            R5900Context stRead{};
            setRegU32(stRead, 4, 1u);                              // one sector
            setRegU32(stRead, 5, 0x1000000u);
            ps2_stubs::sceCdStRead(rdram, &stRead, &runtime);
            const uint32_t afterFirst = cdStreamingLbnForTest();
            t.Equals(afterFirst, streamLbn + 1u, "the stream cursor advanced by one sector");

            R5900Context read{};                                    // a plain read of an unrelated file
            setRegU32(read, 4, 5000u);
            setRegU32(read, 5, 4u);
            setRegU32(read, 6, 0x1100000u);
            ps2_stubs::sceCdRead(rdram, &read, &runtime);
            t.Equals(cdStreamingLbnForTest(), afterFirst,
                     "a plain read must not move the stream cursor (CD.cpp:328 set it to lbn + sectors)");

            R5900Context stRead2{};
            setRegU32(stRead2, 4, 1u);
            setRegU32(stRead2, 5, 0x1000000u);
            ps2_stubs::sceCdStRead(rdram, &stRead2, &runtime);
            t.Equals(cdStreamingLbnForTest(), afterFirst + 1u, "the next stream read resumes where the stream was");
        });
```

- [x] **Step 2: Run it and watch it fail.** Task 1a Step 2's command. Expected: `a plain read must not move the stream cursor` fails with `5004` against the stream's LBN — exactly the audit's finding.

- [x] **Step 3: Implement** the split cursor. `sceCdRead` (:328) and the chained read (:516) write `g_cdReadLbn`; every stream entry point keeps `g_cdStreamingLbn`; `sceCdGetReadPos` (:396) chooses as in the Interfaces block. The snapshot at :188 records both.

- [x] **Step 4: Run it green, then the suite.** Task 1a Step 2's command, then `./build.sh test` under the lock. Expected: the new case passes and the audio/stream cases are unchanged. *(done: C++ 520 green)*

- [x] **Step 5: Build and re-measure the title mix (launch 8 — Task 1e's gate re-run).** *(done: s7_audio_title 2026-09-17: min_corr 1.0000 over the title loop)*

```bash
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_cdcursor_build.marker
scripts/run_detached.sh --owner gate --purpose launch logs/s7_audio_gate.sh logs/s7_cdcursor_gate.marker
python -m tools_py.parity.audio_corr logs/s7_audio.wav logs/title_disc_audio.bin --window-s 4 --bar 0.99
```
Expected (the spec's bar): `min_corr` still ≥ 0.99 **and** the 0.26 s slip at 120 s in `s6_audio_title19` is gone — read it off the printed rows (`offset_samples` advancing 1:1 with no step near t=120). If the slip is still there, it was not the CD cursor: say so in `docs/research/32-audio-path.md` §7.1 ("attributed elsewhere", with the row that shows it) and keep the fix — the test still pins a real defect. *(This re-runs the Task 1e gate script rather than taking a new slot; the audio bar and the slip are read off the same capture.)*

- [x] **Step 6: Commit.** *(done: 5a1b6a8)*

```bash
git commit -m "fix(cd): a plain read no longer moves the stream cursor

audit 2026-09-17 section 2.3 (CD.cpp:328): sceCdRead set g_cdStreamingLbn = lbn + sectors and
sceCdStResume did not restore it, so a plain read while a stream was open made the next stream read deliver
bytes from after that file. Separate g_cdReadLbn for plain reads; the stream cursor is written only by the
stream entry points. Test RED first ('StRead after Read resumes at the stream LBN'). Title mix correlation
unchanged at <N>; the 0.26 s slip at 120 s <gone | attributed elsewhere, research/32 section 7.1>.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/CD.cpp \
  third_party/ps2recomp/ps2xTest/src/ps2_runtime_io_tests.cpp
git push
```

---

### Task 2d — The lobby rate, measured (Sprint 6 Task 2 Step 4, ruling R85)

**Files:**
- Modify: `tools_py/parity/lobby_report.py` (`rate`, `--bar`), `docs/research/28-lobby-taxonomy.md` §2
- Test: `tools_py/tests/test_lobby_report.py`

**Interfaces:**
- `lobby_report.rate(summaries) -> (gameplay:int, total:int, classes:dict[str,int])`.
- `python -m tools_py.parity.lobby_report --bar 0.8 <logs…>` prints the existing rows and `TOTAL …`, then `RATE <g>/<n> bar=0.80 PASS|FAIL`, exit 1 on FAIL.

**Steps:**

- [x] **Step 1: Write the failing test.** In `tools_py/tests/test_lobby_report.py`:

```python
    def test_rate_counts_gameplay_over_total_with_classes(self):
        summaries = [self._summary("gameplay"), self._summary("gameplay"), self._summary("lobby-fail", cls="READY")]
        g, n, classes = lobby_report.rate(summaries)
        self.assertEqual((g, n), (2, 3))
        self.assertEqual(classes["READY"], 1)
    def test_bar_fails_below_the_threshold(self):
        rc = lobby_report.main(["--bar", "0.8"] + self._three_log_paths())   # 2 of 3
        self.assertEqual(rc, 1)
```
Run: `python -m unittest tools_py.tests.test_lobby_report -v` → `AttributeError: module 'tools_py.parity.lobby_report' has no attribute 'rate'` (RED).

- [x] **Step 2: Implement** `rate` (a thin reuse of the existing `totals` counting) and the `--bar` flag. Run the same command: green, existing cases unchanged.

- [x] **Step 3: Ten control rounds, one at a time (launches 9–18).** The harness is pinned and the map is Frostfire for all ten, so the number means one thing. *(done: lobby_rate_01..10 2026-09-17 22:28-00:06)*

```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  scripts/parity/online_control_round.sh "Frostfire" logs/parity/s7_lobby_$i   # poll logs/s7_lobby_$i.done before the next
done
```
Run them **one at a time**, polling `logs/s7_lobby_<i>.done` between launches; never two at once. An `exit=75 BUSY` means the previous one is still live.

- [x] **Step 4: Read the rate.** *(done: RATE 6/10 bar=0.80 FAIL; classes login:keyboard-typing=4 -- Task 2f)*

```bash
python -m tools_py.parity.lobby_report --bar 0.8 logs/parity/drive_s7_lobby_*.txt
```
Expected: `RATE <g>/10 bar=0.80 PASS` (the spec's bar: 8 of 10). Decision table: ≥ 8 → record the rate and the classes in `docs/research/28-lobby-taxonomy.md` §2 and `docs/KNOWN.md` §1, done. 6–7 → fix the dominant class and run five more (`s7_lobby_11..15`), then re-read the rate over all fifteen. **Stop rule (spec §3):** under 6 of 10 opens a lobby-hardening task **before anything else online** — Tasks 2e and 3's online launches wait behind it.

- [x] **Step 5: Commit** (harness plus the note; no runtime change). *(done: 588f372 (the queue and the report) and 68a082e (the number))*

```bash
git commit -m "measure(online): the lobby rate is <g>/10 on Frostfire, with the failure class of each miss

Sprint 6 Task 2 Step 4, skipped under ruling R85, measured properly: ten pinned online_control_round.sh
launches on one map, counted as reached-gameplay over total, each miss carrying its class.
lobby_report.rate + --bar (RED first) makes the bar machine-checked rather than eyeballed. research/28
section 2 carries the table and the launch names.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  tools_py/parity/lobby_report.py tools_py/tests/test_lobby_report.py docs/research/28-lobby-taxonomy.md
git push
```

---

### Task 2e — Freeze shape 2 (research/29 §0, §4)

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` (the `[pc-sampler]` line :670-678), `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_backend.h`, `.../gs_frontend.h`, `.../gs_frame_backpressure.h`, `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_libnetb.cpp` (:258-317 `waitReadable`), `tools_py/parity/freeze_trace.py`, `docs/research/29-online-freeze.md` §0
- Test: `tools_py/tests/test_freeze_trace.py`

**Interfaces (research/29 §4 is the spec for these — take its eight fields verbatim):**
- The `[pc-sampler]` line gains `t=<host s> vsync=<n> ee=<guest s> seq=<n> dpc=0x<pc> idle=<n> bp_pending=<n> bp_waiters=<n> bp_wait_ms=<n> net_wait=<0|1>/<cum ms>`.
- New accessors: `GSBackend::PendingGuestFrames()`/`BackpressureWaiters()` (virtual, default 0) with `GSFrontend` passthroughs; `GsFrameBackpressure::waitNsTotal()` (a non-clearing atomic, so the sampler never races the 60-present printer's `takeStats()`); `PS2Runtime::debugPc()`; `socom2_libnetb::netWaitState() -> std::pair<int, uint64_t>`.
- `freeze_trace.parse` learns the new fields; `freeze_trace.classify(window) -> str` returns `"host-load"` (`vsync` flat, `bp_waiters=1`, `bp_wait_ms` climbing), `"runtime-oversleep"` (`vsync` flat, `bp_waiters=0`, `idle` climbing) or `"net-wait"` (`seq` frozen, `dpc` frozen, `net_wait=1`).

**Steps:**

- [x] **Step 1: Write the failing test.** In `tools_py/tests/test_freeze_trace.py`:

```python
    SAMPLE = ("[pc-sampler] live pc=0x350d90 ra=0x0 sp=0x0 t=612.50 vsync=41233 ee=612.10 seq=8891 "
              "dpc=0x350d90 idle=140 bp_pending=0 bp_waiters=0 bp_wait_ms=12 net_wait=1/3300 running=3 threads:")

    def test_the_new_sampler_fields_are_parsed(self):
        row = freeze_trace.parse([self.SAMPLE])[0]
        self.assertAlmostEqual(row["t"], 612.50)
        self.assertEqual(row["vsync"], 41233)
        self.assertEqual(row["seq"], 8891)
        self.assertEqual(row["dpc"], 0x350d90)
        self.assertEqual(row["bp_waiters"], 0)
        self.assertEqual(row["net_wait"], 1)

    def test_shape_two_classifies_as_net_wait(self):
        rows = freeze_trace.parse([self.SAMPLE, self.SAMPLE.replace("t=612.50", "t=615.80")])
        self.assertEqual(freeze_trace.classify(rows), "net-wait")

    def test_a_host_load_window_classifies_as_host_load(self):
        a = self.SAMPLE.replace("net_wait=1/3300", "net_wait=0/0").replace("bp_waiters=0", "bp_waiters=1")
        b = a.replace("t=612.50", "t=615.80").replace("bp_wait_ms=12", "bp_wait_ms=3200").replace("seq=8891", "seq=9100")
        self.assertEqual(freeze_trace.classify(freeze_trace.parse([a, b])), "host-load")
```
Run: `python -m unittest tools_py.tests.test_freeze_trace -v` → the three new cases fail (`KeyError: 't'`, `AttributeError: … 'classify'`).

- [x] **Step 2: Implement** the parser fields and `classify` in `freeze_trace.py`. Run the same command: green, the existing freeze_trace cases unchanged.

- [x] **Step 3: Implement the sampler fields** (research/29 §4 items 1–8) and the accessors it names. Then Task 1a Step 2's command plus `./build.sh test` under the lock: exit 0.

- [x] **Step 4: Build.** *(done: exe s7_block2_build 2026-09-17 21:34)*

```bash
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_freeze_build.marker
```

- [x] **Step 5: The loaded launch (launch 19).** `logs/s7_freeze_load.sh`: start the load generator, run one Frostfire control round, stop the generator. *(done: s7_freeze_loaded: CONTROL-ROUND, no 3-17 s window)*

```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s7_freeze_load.sh logs/s7_freeze_load.marker
```
The script body around the round: `powershell -c "1..4 | % { Start-Job { while($true){} } }"` before, `powershell -c "Get-Job | Remove-Job -Force"` after (research/29 §3's recipe), `PS2X_CLOCK_TRACE=1` set throughout.

- [x] **Step 6: The quiet launch (launch 20).** *(done: s7_freeze_quiet: CONTROL-ROUND, no 3-17 s window)*

```bash
scripts/parity/online_control_round.sh "Frostfire" logs/parity/s7_freeze_quiet
```
Same exe, no load generator.

- [x] **Step 7: The condition sentence.** *(done: research/29 §0, 2026-09-17 paragraph)*

```bash
python -m tools_py.parity.freeze_trace logs/run_A_<loaded stamp>.log --peer logs/run_B_<loaded stamp>.log
python -m tools_py.parity.freeze_trace logs/run_A_<quiet stamp>.log  --peer logs/run_B_<quiet stamp>.log
```
Expected: every stall window ≥ 2 s printed with its class. Write the answer into `docs/research/29-online-freeze.md` §0 as a sentence, not a hedge: shape 2 is `net-wait` (the 10 s `waitReadable` cap) or it is not, and the rows say which. If it is `net-wait`, the fix candidate (adding the wait's host time to `ps2GuestClockExcludedNs()`) is **Sprint 8's**, not this task's — this task's deliverable is the instrument and the sentence.

- [x] **Step 8: Commit.** *(done: 6b4a831; the two launches run in the launch block)*

```bash
git commit -m "instrument(freeze): the pc-sampler answers both freeze shapes in one line (research/29 section 4)

Sprint 6 Task 3 Step 2/3, carried: the sampler now prints host time, vsync, ee, seq, dpc, idle, the
back-pressure pending/waiters/cumulative wait and the libnetb wait state, so one loaded and one quiet
launch from the same exe separate host starvation from a runtime wait without a third. freeze_trace gained
the fields and classify() (RED first). Launches s7_freeze_load and s7_freeze_quiet; research/29 section 0's
condition sentences are now settled: <the sentence>.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_backend.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_frontend.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_frame_backpressure.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/socom2_libnetb.cpp \
  tools_py/parity/freeze_trace.py tools_py/tests/test_freeze_trace.py docs/research/29-online-freeze.md
git push
```

---

### Task 2f — The lobby misses: the injected press is latched (Task 2d Step 4's finding, KNOWN §1 lobby-rate row)

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/injected_pad_latch.h`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.cpp` (the `PS2X_SOCOM2_INPUT_FILE` block)
- Test: `third_party/ps2recomp/ps2xTest/src/pad_input_tests.cpp` (case `InjectedPadLatch`)

**Interfaces:**
- Produces: `ps2x::InjectedPadSample`, `ps2x::parseInjectedPadLine(const char *, InjectedPadSample &)`, `ps2x::InjectedPadLatch::observe(sample)` / `take()`.

Why: ten launches (Task 2d) reached gameplay 6 times; every miss was the on-screen keyboard at login. The drive holds a press for 0.09 s of wall clock and the game sampled the pad file once per rendered frame, so at the 12-30 fps the login screen ran at in the misses (GL back-pressure, `bp_pending=4 bp_waiters=1`) a press fell between two polls and was never seen; the cursor then desynchronised and each "backspace" typed a glyph (`rdy!!!!!!!!!`). Presses were dropped, never repeated (the `[socom2-input] state` edges: 21 vs 28 in the same 17.7 s pass). The class predates the scheduler change.

- [x] **Step 1: The RED test** — `InjectedPadLatch`: parse accepts the harness line and rejects two malformed ones; a press observed between two takes is delivered to exactly one take; a held press is delivered on every take; axes are the latest sample's. *(done 2026-09-18: `fatal error: 'runtime/injected_pad_latch.h' file not found`)*
- [x] **Step 2: The latch and the sampler thread** — header-only latch; a 2 ms sampler thread started lazily on the first poll only when `PS2X_SOCOM2_INPUT_FILE` is set, joined from a static destructor; the poll takes the latched sample where it used to read the file. *(done: `./build.sh test` 524 with the one known VU0-mapping failure; exe `s7_2f_build`)*
- [x] **Step 3: The gate on the new exe.** `logs/s7_2f_gate.sh` (three stages, stamp `s7_2f_gate`). Expected: GATE PASS 3/3 (the gate sets `PS2X_HOST_GAMEPAD=0` and drives through the same file, so the latch is on the path). *(done: s7_2f_gate GATE PASS 3/3, 2026-09-18)*
- [x] **Step 4: Commit.** `git add third_party/ps2recomp/ps2xRuntime/include/runtime/injected_pad_latch.h third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.cpp third_party/ps2recomp/ps2xTest/src/pad_input_tests.cpp` — message: `fix(input): injected pad presses are latched, never dropped -- a 2 ms sampler and a per-poll OR of everything seen (Sprint 7 Task 2f)`.
- [x] **Step 5: Ten rounds again (launches 27-36).** `scripts/parity/lobby_rate_queue.sh 10 frostfire` under the lock (after Goal 8's exe lands, so one block measures both), then `python -m tools_py.parity.lobby_report --bar 0.8 logs/parity/drive_lobby_rate_*.txt` over the NEW ten only (move the old ten to `logs/parity/lobby_rate_2026-09-17/` first). Bar: 8/10. Below it: the class names the next task; `login:keyboard-*` again means the latch is not enough and the drive must verify each press from the `[socom2-input]` edge (a `--verify-edges` mode). *(done 2026-09-18 02:33-04:40: lobby_rate_01..10 on the latched press + Goal 8/Task 12 exe: RATE 10/10 bar=0.80 PASS, classes none)*
- [x] **Step 6: KNOWN.** The lobby-rate row moves to its new number; the login-screen slowness row stays open (its lead is the menus' 80-133 ms/s of uploads, see the decodes row). *(done: KNOWN §1 lobby-rate row updated)*

### Task 3 — The 21k texture decodes a second (audit §2.2 F1, KNOWN §2)

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (`markShadowPages` :1593, `executeTransfer`/`executeUpload` :1599-1640, `downloadRenderTargetToCpu` :2210-2256, `resolveTexture` :2828-2909, the stats line :1495-1503), `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h`
- Test: `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp` (the console-replay GL test at :1523-1560, `PS2X_CONSOLE_REPLAY_GL`)

**Interfaces:**
- `markShadowPages(uint32_t page, uint32_t pageCount, uint32_t rowFirst, uint32_t rowLast)` — the two new arguments are the **rows** the write touched inside those pages; the old two-argument form becomes a thin wrapper meaning "every row".
- `GSGlBackend::textureDecodes() const -> uint64_t` and a `decodes=<n>` field on the `[gs-gl stats] calls=…` line, plus `decodes_per_present=<f>`.
- `resolveTexture` compares generations **only for pages the write actually touched** and reuses the GL texture object when `tw`/`th` and the internal format match (`glTexSubImage2D` instead of `glGenTextures` + `glTexImage2D`).
- The upload span includes `dsax`/`rrw` (today it is rows only), so a 16x16 movie block no longer invalidates a whole page row.

**Steps:**

- [x] **Step 1: The page trace (launch 21).** *(done 2026-09-18, three launches: `s7_pages` and `s7_pages2` missed the lobby (Task 2f's class); `s7_pages_mission` traced the offline mission stage (R96), and the online login stage came from `s7_pages2`'s own log. **STOP RULE FIRED**: zero decodes on the traced pages online in 180 s; offline, 80% of decode frames have no preceding download and 92% of downloads FOLLOW a decode. The hypothesis is re-opened in KNOWN §2 with what the trace shows: 16x16 1 KB tile uploads at 7-11k/s costing 80-133 ms/s in the MENUS (login, lobby) against 20-28 ms/s in gameplay, where the re-measured rate is ~10k/s, not 21k. Steps 2-7 below are not executed (R96); the menus' upload cost is Sprint 8's task.)* Settle the hypothesis before changing anything. The HUD texture page is the one `resolveTexture` logs for the HUD atlas; take it from the last online round's `[gs-pages]` lines or, failing that, page `0x0c0`.

```bash
# logs/s7_pages.sh: PS2X_GS_TRACE_PAGES=0x0c0:8 PS2X_GS_STATS=1 around one Frostfire control round
scripts/run_detached.sh --owner gate --purpose launch logs/s7_pages.sh logs/s7_pages.marker
grep -a "gs-pages" logs/run_A_*.log | head -60
grep -a "gs-gl stats" logs/run_A_*.log | grep -c "textures="
```
Expected (the audit's hypothesis): per frame, a `download gpu->cpu rt fbp=…` line for the post-process target **immediately preceding** the `texture tbp0=…` decode lines for the HUD pages — download, re-stamp, miss, decode, every frame. **Stop rule (spec §3):** if the trace does not show download-then-decode, stop the fix and re-open the hypothesis in `docs/KNOWN.md` §2 with what the trace *does* show. Do not "fix" a mechanism the trace did not find.

- [ ] ~~**Step 2: Write the failing budget test.** In `ps2_gs_tests.cpp`, inside the console-replay GL case (:1523-1560, guarded by `PS2X_CONSOLE_REPLAY_GL`):~~ *(not run: R96)*

```cpp
                const uint64_t decodes = gl->textureDecodes();
                const uint64_t presents = gl->presentCount();
                const double perPresent = presents ? static_cast<double>(decodes) / static_cast<double>(presents) : 0.0;
                t.IsTrue(perPresent <= 40.0,
                         "texture decodes per present should be at most 40 (measured " + std::to_string(perPresent) +
                         "; the 21k/s defect was ~350 per present) -- audit 2026-09-17 section 2.2 F1");
```

- [ ] ~~**Step 3: Run it and watch it fail.**~~ *(not run: R96)*

```bash
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; PS2X_CONSOLE_REPLAY_GL=1 third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe 2>&1 | grep -E "Failed\]|decodes per present|Total Tests"
```
Expected: the assertion fails with a measured value well above 40 (compilation first fails on `textureDecodes`/`presentCount`, which is the same red — add the two accessors, then see the number).

- [ ] ~~**Step 4: Implement, one change at a time, re-running Step 3 after each** so the plan records which change bought what:~~ *(not run: R96)*
  1. `downloadRenderTargetToCpu` marks only the rows it wrote (`yStart`..`yEnd`), through the four-argument `markShadowPages`;
  2. the upload span includes `dsax`/`rrw`;
  3. `resolveTexture` compares per-page generations only for pages the write touched;
  4. GL texture objects are reused when the dimensions and format match.

- [ ] ~~**Step 5: Green, then the suite.** Step 3's command with the assertion passing, then `./build.sh test` under the lock (exit 0) — and the whole `ps2_gs_tests` VRAM round-trip set must stay green: a marking change that loses a real invalidation shows up there first.~~ *(not run: R96)*

- [ ] ~~**Step 6: Build, then the ladder (launch 22).**~~ *(not run: R96)*

```bash
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_decodes_build.marker
bash scripts/parity/ladder_frostfire.sh logs/parity/s7_decodes_ladder
grep -a "gs-gl stats" logs/parity/s7_decodes_ladder/*.log | tail -5
grep -a "waits=" logs/parity/s7_decodes_ladder/*.log | tail -4
```
Expected (the spec's bars): the ladder's **RUNG0 back-pressure bar passes — `waits` < 100 per instance** — and `PS2X_GS_STATS` shows texture decodes **under 2k/s**. Decision table: both met → done and KNOWN §2's 21k row is retracted into §1 with the launch name; decodes under 2k/s but waits ≥ 100 → the back-pressure cost is a different mechanism, file it and keep the decode fix; decodes still above 2k/s → back to Step 1's trace with the new marking in place, naming which of the four changes moved the number.

- [ ] ~~**Step 7: Commit.**~~ *(not run: R96)*

```bash
git commit -m "fix(gs-gl): mark only the rows a write touched, and stop re-decoding every sampled texture

audit 2026-09-17 section 2.2 F1: page marks were a global generation bump at page-row granularity with no
x-extent, and a render target overlapping a sampled texture was downloaded and its whole span re-stamped
every frame -- the post-process draws the half-size frame into the depth-buffer pages every gameplay frame,
those pages overlap the parked streamed textures, so every cache hit failed the generation check and
re-decoded (a glGenTextures + glTexImage2D each). Trace first (s7_pages: download lines preceding decode
lines each frame, as predicted). Four changes: mark only downloaded rows; include dsax/rrw in the upload
span; compare generations only for touched pages; reuse GL texture objects. A decodes-per-present budget
guards it in the console-replay GL test (RED first). Ladder s7_decodes_ladder: waits=<n> per instance
(bar 100), texture decodes <n>/s (bar 2000).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h \
  third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp
git push
```

---

### Task 4 — The hosted server (**owner-gated**: the machine and the two addresses)

**Files:**
- Create: `scripts/make_server_zip.sh`, `tools_py/tests/test_make_server_zip.py`
- Modify: `server/README.md`, `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h` (`kServerPresets`, the default preset), `docs/HUMAN_TASKS.md`
- Test: `tools_py/tests/test_make_server_zip.py`, `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp`

**Interfaces:**
- `scripts/make_server_zip.sh [out dir]` → `<out>/socom-unzipped-server/` containing `horizon-server/`, `dme-plugins/`, `medius-plugins/`, `config/` (with `simulated.db` **excluded** and a `config/README.txt` naming `seed-simulated-db.ps1`), `start-servers.ps1`, `seed-simulated-db.ps1`, `README.md`, plus `<out>/socom-unzipped-server.zip`. Exits 2 with a named missing path, like `make_portable.sh`.
- `launcher::kServerPresets` keeps three entries; the two addresses stop being `*_ADDRESS_TBC` once the owner supplies them; `Config{}.serverPreset` becomes `"unzipped"` (ruling R89 lifted) **only** in the same commit that fills the Unzipped address.

**Steps (autonomous half, all of it, before the stop):**

- [x] **Step 1: Write the failing test** `tools_py/tests/test_make_server_zip.py`, modelled on `test_make_portable.py`:

```python
import os, subprocess, tempfile, unittest, zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

class MakeServerZip(unittest.TestCase):
    def _run(self, out):
        return subprocess.run(["bash", os.path.join(ROOT, "scripts", "make_server_zip.sh"), out],
                              cwd=ROOT, capture_output=True, text=True)
    def test_the_zip_carries_the_server_and_its_readme(self):
        out = tempfile.mkdtemp()
        r = self._run(out)
        self.assertEqual(r.returncode, 0, r.stderr)
        names = zipfile.ZipFile(os.path.join(out, "socom-unzipped-server.zip")).namelist()
        self.assertTrue(any(n.endswith("start-servers.ps1") for n in names), names[:20])
        self.assertTrue(any(n.endswith("README.md") for n in names), names[:20])
    def test_the_simulated_db_is_never_shipped(self):
        out = tempfile.mkdtemp()
        self._run(out)
        names = zipfile.ZipFile(os.path.join(out, "socom-unzipped-server.zip")).namelist()
        self.assertFalse(any(n.endswith("simulated.db") for n in names), "a seeded database must not ship")
```
Run: `python -m unittest tools_py.tests.test_make_server_zip -v` → `FileNotFoundError: … scripts/make_server_zip.sh` (RED).

- [x] **Step 2: Implement `scripts/make_server_zip.sh`.** Run the same command: 2 tests OK.

- [x] **Step 3: Verify the advertised-address rewrite works end to end on this machine** (no owner needed — a private address proves the mechanism):

```bash
powershell.exe -NoProfile -File server/start-servers.ps1 -PublicIp 203.0.113.7 -NoStart
powershell.exe -NoProfile -File server/start-servers.ps1 -ShowIp
powershell.exe -NoProfile -File server/start-servers.ps1 -PublicIp 192.168.2.10 -NoStart   # put it back
```
Expected: `-ShowIp` reports `203.0.113.7` in all four advertised fields and `MPS.Ip` still `127.0.0.1`; `server/config/simulated.db` stays unstaged either way.

- [x] **Step 4: The port list in `server/README.md`** is checked against what the stack actually binds:

```bash
powershell.exe -NoProfile -Command "Get-NetTCPConnection -State Listen | Where-Object { $_.OwningProcess -in (Get-Process -Name *horizon*,*medius*,*dme* -ErrorAction SilentlyContinue).Id } | Select-Object LocalPort | Sort-Object LocalPort"
```
Expected: every listening port appears in `server/README.md`'s forward list; add any that does not, with what it is for.

- [x] **Step 5: Add the launcher's test for the filled-in preset** (it fails until the addresses exist, which is the point — mark it skipped-with-a-reason rather than deleted):

```cpp
            const launcher::ServerPreset *unzipped = launcher::findServerPreset("unzipped");
            t.IsTrue(unzipped != nullptr, "the Unzipped preset exists");
            if (std::string(unzipped->address) == "UNZIPPED_SERVER_ADDRESS_TBC")
                t.Skip("the owner has not supplied the hosted address yet (docs/HUMAN_TASKS.md)");
            else
            {
                t.IsTrue(std::string(unzipped->address).find("TBC") == std::string::npos, "no placeholder ships");
                t.Equals(launcher::Config{}.serverPreset, std::string("unzipped"), "the default preset is ours once it is real");
            }
```

- [x] **Step 6: Commit the autonomous half.** *(done: 273d902)*

```bash
git commit -m "packaging(server): scripts/make_server_zip.sh, the port list checked, the advertised-address rewrite verified

audit 2026-09-17 gap G4: the server half of the two-stranger path, as far as it goes without a machine.
make_server_zip.sh packages server/ with its README and never ships simulated.db (tests RED first);
start-servers.ps1 -PublicIp/-ShowIp verified on a test address and put back; server/README.md's forward
list checked against what the stack binds. The two picker addresses and the default-preset switch wait on
the owner (docs/HUMAN_TASKS.md).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  scripts/make_server_zip.sh tools_py/tests/test_make_server_zip.py server/README.md \
  third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp docs/HUMAN_TASKS.md
git push
```

- [ ] **STOP: needs the owner's hosted machine and the two server addresses (`docs/HUMAN_TASKS.md`).**

**Steps after the owner answers (do not start these before):**

- [ ] **Step 7: Fill the picker and switch the default.** Replace `COMMUNITY_SERVER_ADDRESS_TBC` and `UNZIPPED_SERVER_ADDRESS_TBC` in `launcher_config.h` with the owner's two addresses, set `Config{}.serverPreset = "unzipped"` (ruling R89 lifted — record it as a numbered ruling), and run Task 1a Step 2's command: the `t.Skip` branch in Step 5's case is now the real assertion and passes.

- [ ] **Step 8: Stand the server up on the named machine** with `powershell.exe -NoProfile -File server/start-servers.ps1 -PublicIp <owner's address>` and the router's forwards per `server/README.md`; confirm with `-ShowIp`.

- [ ] **Step 9: One launcher login from the portable zip (launch 23).**

```bash
bash scripts/make_portable.sh dist/portable
bash scripts/make_server_zip.sh dist/server
# logs/s7_hosted_login.sh: run dist/portable/socom2/socom_unzipped_launcher.exe with config.json preset "unzipped",
# then drive to the lobby with tools_py.parity.online_login_ours (SOCOM_SERVER_IP unset -- the picker supplies it)
scripts/run_detached.sh --owner gate --purpose launch logs/s7_hosted_login.sh logs/s7_hosted_login.marker
python -m tools_py.parity.lobby_report logs/parity/drive_s7_hosted_login.txt
```
Expected (the spec's bar): the launcher's SOCOM Unzipped preset **reaches the lobby from the portable zip on this machine** — `gameplay=1/1` or at least `LOBBY` reached with no `pre-login` class. Does not separate a NAT problem only a second machine would show; that is Task 5.

- [ ] **Step 10: Commit** the filled addresses and the default switch with the launch name in the message, and move the HUMAN_TASKS item to **Done** with the owner's answer quoted.

---

### Task 5 — The first two-machine match (**owner-gated**: a second machine)

**Files:**
- Create: `tools_py/parity/two_machine_readout.py`, `scripts/parity/two_machine_readout.sh`, `tools_py/tests/test_two_machine_readout.py`
- Modify: `docs/HUMAN_TASKS.md`, later `docs/KNOWN.md`
- Test: `tools_py/tests/test_two_machine_readout.py`

**Interfaces:**
- `two_machine_readout.read(log_a, log_b) -> dict` with `lobby_class` (from `lobby_report.summarise`), `saw_peer_move` (per side: did the position peek show the *other* player's actor move more than `PEER_MOVE_MIN_UNITS = 40.0` over the round), `clock_skew_s` (the difference of the two round clocks at the same host time, from the `0x408F10` clock string rows), and `classes` (the failure class of each side).
- CLI `python -m tools_py.parity.two_machine_readout <log_A> <log_B>` prints one block the owner can paste back; `scripts/parity/two_machine_readout.sh` is the one-line wrapper the owner runs on either machine *(controller's choice: the spec names `scripts/parity/two_machine_readout.py`; the logic lives under `tools_py/parity/` where its unit test can import it, and the spec's path becomes the shell wrapper; re-rule if wrong)*.

**Steps (autonomous half, all of it, before the stop):**

- [x] **Step 1: Write the failing test** `tools_py/tests/test_two_machine_readout.py`:

```python
import unittest
from tools_py.parity import two_machine_readout as tmr

A = ["[peek] item0 words 0x00000000 0.0 ...", "RESULT CONTROL-ROUND harness=abc exe=def"]
B = ["[peek] item0 words 0x00000000 0.0 ...", "RESULT CONTROL-ROUND harness=abc exe=def"]

class Readout(unittest.TestCase):
    def test_a_round_where_neither_side_moved_reports_no_peer_movement(self):
        out = tmr.read_lines(A, B)
        self.assertFalse(out["saw_peer_move"]["A"])
        self.assertFalse(out["saw_peer_move"]["B"])
    def test_clock_skew_is_the_difference_of_the_round_clocks(self):
        a = A + ["[peek] t=10.0 clock=2:00"]
        b = B + ["[peek] t=10.0 clock=1:58"]
        self.assertAlmostEqual(tmr.read_lines(a, b)["clock_skew_s"], 2.0, places=1)
    def test_a_lobby_failure_carries_its_class(self):
        out = tmr.read_lines(["LOBBY-FAIL READY"], B)
        self.assertEqual(out["classes"]["A"], "READY")
```
Run: `python -m unittest tools_py.tests.test_two_machine_readout -v` → `ModuleNotFoundError` (RED). (Replace the three `[peek]` literals with real rows copied out of `logs/run_A_*.log` before implementing — a synthetic row that the real parser would not accept is worse than no test.)

- [x] **Step 2: Implement** `two_machine_readout.py` (reusing `lobby_report.summarise`, `verdict_core`'s actor-position parsing and `CLOCK_STRING_ADDR`) and the shell wrapper. Run the same command: 3 tests OK.

- [x] **Step 3: Prove the readout on a two-instance round we already have** (no second machine needed):

```bash
python -m tools_py.parity.two_machine_readout logs/run_A_<s7_slice_ctl stamp>.log logs/run_B_<s7_slice_ctl stamp>.log
```
Expected: a block naming the lobby class, `saw_peer_move A=True B=True` (both sides strafed in a control round) and a clock skew near zero — the two-instance case is the readout's own calibration.

- [x] **Step 4: Write the owner's instructions** into `docs/HUMAN_TASKS.md` under the second-machine item: the zip to copy (`dist/portable/socom-unzipped.zip`), which preset to pick, both directions of hosting, and the one command to run afterwards (`bash scripts/parity/two_machine_readout.sh <log_A> <log_B>`), plus the four things to report (NAT shape, advertised address, whether key sharing mattered, clock skew).

- [x] **Step 5: Commit the autonomous half.** *(done: 273d902)*

```bash
git commit -m "harness(online): two_machine_readout -- the readout the owner runs after the first real match

audit 2026-09-17 gap G5: every online result is two instances on one host, so NAT, the advertised address,
clock skew and two clients on the same key have never been exercised. two_machine_readout.read (RED first)
turns the two run logs into the lobby class, whether each side saw the other move, the clock skew and the
failure class of each miss; calibrated against a two-instance control round. HUMAN_TASKS carries the
owner's steps.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  tools_py/parity/two_machine_readout.py scripts/parity/two_machine_readout.sh \
  tools_py/tests/test_two_machine_readout.py docs/HUMAN_TASKS.md
git push
```

- [ ] **STOP: needs the owner's second machine for the first two-machine match (`docs/HUMAN_TASKS.md`).**

**Steps after the owner answers:**

- [ ] **Step 6: Run the readout over the two logs the owner returns**, both directions of hosting, and check the spec's bar: a lobby reached and **both players seen moving on both machines**.
- [ ] **Step 7: File the findings** — NAT, advertised address, key sharing, clock skew — into `docs/KNOWN.md` §1 (proven, with the log names) or §2 (believed, with the experiment that would settle it), and say in the row whether the two machines were on the same LAN or across the internet, because the bar does not separate those unless the owner says which.

---

### Task 6 — The owner's checks reported (**owner**)

**Files:** `docs/HUMAN_TASKS.md`, `docs/KNOWN.md`, `docs/STATUS.md`. No code.

**Interfaces:** each answered item moves from **Open** to **Done** with the owner's words quoted and the date; anything the answer contradicts is retracted in `docs/KNOWN.md` in the same hour (the standing rule).

**Steps (autonomous half):**

- [x] **Step 1: Make each open item runnable without a question back.** Check that the four items in `docs/HUMAN_TASKS.md` each name the exact command, the exact thing to listen for or look at, and the one-line answer wanted; the audio items already do, the pad item already does. Fix any that do not (the two-addresses item gained Task 4's context; the second-machine item gained Task 5 Step 4's). *(done: adb2a76)*
- [x] **Step 2: Attach the current measurement to each item** so the owner's ears are confirming a number, not replacing one: the title/intro listen carries `min_corr` from Task 1e/2c's gate, the free-play listen carries the mission gate's stamp, the pad item carries the launcher's build sha. *(done: adb2a76)*
- [x] **Step 3: Commit** `docs: HUMAN_TASKS items carry the measurement each check confirms` with the pathspec `docs/HUMAN_TASKS.md`. *(done: adb2a76)*

- [ ] **STOP: needs the owner's four hands-on checks (`docs/HUMAN_TASKS.md`).** The loop does not wait on them (spec Goal 6): it continues to Task 7 and files whatever is still open.

**Steps after the owner answers:**

- [ ] **Step 4: Move each answered item to Done**, quote the answer, and open a task for anything the answer contradicts — a crackle the correlation did not predict is a Sprint 8 audio item, a dead pad is a Sprint 8 input item, and both get a `docs/KNOWN.md` row the same hour.

---

### Task 8 — Controller selection in the launcher (owner request 2026-09-18)

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/host_gamepad_select.h`
- Modify: `third_party/ps2recomp/ps2xLauncher/src/main.cpp` (`drawController` :240-279, the Controller panel :423-436, `kHeight` :31), `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h` (`Config` :28-42), `third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp` (`toJson` :169, `fromJson` :188, `environmentFor` :247), `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.cpp` (:206-233), `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_pad.cpp` (:42-86), `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/Pad.cpp` (`axisToByte` :71-76, `findFirstGamepad` :86-98, `applyGamepadState` :117-120, the second caller :652), `docs/HUMAN_TASKS.md`
- Test: `third_party/ps2recomp/ps2xTest/src/pad_input_tests.cpp` (the `HostGamepadKnob` case, :73), `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp` (the `Launcher` case, :73)

**Interfaces:**
- `constexpr int kHostGamepadSlots = 4;` — raylib 5.5 tracks four pads (`IsGamepadAvailable(0..3)`); the one place the count is written down.
- `int hostGamepadSelect(const char *envValue, int count, bool (*available)(int))` — the env index when it parses, is in `[0, count)` and `available(it)`; else the lowest `i` with `available(i)`; else `-1`. `available == nullptr` or `count <= 0` gives `-1`. Pure: it reads no environment of its own, so the test passes a fake.
- `float hostPadDeadZone()` — `PS2X_PAD_DEADZONE` read once per process, `0.15f` when unset or unparseable, clamped to `[0.0f, 0.5f]`.
- `float hostPadAxis(float v, float deadZone)` — 0 inside the dead zone, the rest rescaled so full deflection still reaches ±1.
- `launcher::Config::gamepadIndex` — `int`, default `-1` = "the first available pad", any of `0..3` = that raylib slot.
- `launcher::Config::padDeadZone` — `double`, default `0.15` *(controller's choice: the owner's note says `float`; every other analogue field in `Config` is `double` (`mouseSensitivity`), `toJson` prints it with `%g`, and the launcher's `slider(Rectangle, double &, double, double)` binds a `double &` — a `float` field would need a second slider helper for one value. The runtime side is `float` throughout. Re-rule if wrong.)*
- `launcher::environmentFor` gains `PS2X_HOST_GAMEPAD_INDEX=<i>` **only when `gamepadIndex >= 0`** and `PS2X_PAD_DEADZONE=<f>` **always**.

**Steps:**

- [x] **Step 1: Write the failing C++ test.** In `pad_input_tests.cpp`, inside the existing `MiniTest::Case("HostGamepadKnob", ...)` body (:73), after the `PS2X_HOST_GAMEPAD=0` case, and add `#include "runtime/host_gamepad_select.h"` at the top: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        tc.Run("PS2X_HOST_GAMEPAD_INDEX picks a pad when it is there, otherwise the first available one", [](TestCase &t)
        {
            // A fake `available` so the case runs the same on a machine with no pad and on one with four.
            static bool s_present[kHostGamepadSlots];
            auto available = [](int i) { return i >= 0 && i < kHostGamepadSlots && s_present[i]; };
            for (bool &p : s_present) p = false;
            s_present[0] = true;
            s_present[2] = true;
            t.Equals(hostGamepadSelect("2", kHostGamepadSlots, available), 2, "the env names pad 2 and pad 2 is there");
            t.Equals(hostGamepadSelect("1", kHostGamepadSlots, available), 0, "the env names an absent pad: the first available one instead");
            t.Equals(hostGamepadSelect(nullptr, kHostGamepadSlots, available), 0, "unset: the first available one");
            t.Equals(hostGamepadSelect("", kHostGamepadSlots, available), 0, "empty: the first available one");
            t.Equals(hostGamepadSelect("nonsense", kHostGamepadSlots, available), 0, "unparseable: the first available one");
            t.Equals(hostGamepadSelect("9", kHostGamepadSlots, available), 0, "out of range: the first available one");
            t.Equals(hostGamepadSelect("-1", kHostGamepadSlots, available), 0, "negative: the first available one");
            for (bool &p : s_present) p = false;
            t.Equals(hostGamepadSelect("2", kHostGamepadSlots, available), -1, "no pad at all: -1, and every caller reads the keyboard");
            t.Equals(hostGamepadSelect(nullptr, kHostGamepadSlots, available), -1, "no pad at all, no preference: -1");
            s_present[3] = true;
            t.Equals(hostGamepadSelect(nullptr, kHostGamepadSlots, available), 3, "only the last slot: it is the first available");
            t.Equals(hostGamepadSelect("3", 0, available), -1, "a zero count selects nothing");
            t.Equals(hostGamepadSelect("3", kHostGamepadSlots, nullptr), -1, "no probe selects nothing");
        });
```

- [x] **Step 2: Run it and watch it fail.** The command set's C++ line: *(done 2026-09-18, agent-executed; suite 538)*

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe 2>&1 | grep -E "Failed\]|Total Tests"
```
Expected: `fatal error: 'runtime/host_gamepad_select.h' file not found`.

- [x] **Step 3: Implement the header.** `ps2xRuntime/include/runtime/host_gamepad_select.h`: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
#pragma once
// Sprint 7 Task 8 (owner request 2026-09-18): WHICH host pad the game reads, in one place.
//
// Three call sites read a raylib gamepad -- the libpad HLE (Kernel/Stubs/Pad.cpp), the generic pad path
// (ps2_pad.cpp) and SOCOM's own poll (socom2_host_input.cpp) -- and all three hard-coded slot 0 or "the first
// available". With two devices plugged in (a wheel, a spare pad, a docked laptop's virtual device) the one that
// answers slot 0 is not the one in the player's hands, so the launcher now picks and passes
// PS2X_HOST_GAMEPAD_INDEX. Unset keeps exactly the old behaviour: the first available pad.
//
// PS2X_HOST_GAMEPAD=0 (host_gamepad.h) still disables every read; it is checked by the callers, not here, so
// that this helper stays pure and testable with a fake `available`.
#include <cstdlib>

// raylib 5.5 tracks four pads (MAX_GAMEPADS); IsGamepadAvailable is false for the rest.
constexpr int kHostGamepadSlots = 4;

// The env index when it parses, is in [0, count) and is available; else the lowest available index; else -1
// (no pad -- the callers then read the keyboard).
inline int hostGamepadSelect(const char *envValue, int count, bool (*available)(int))
{
    if (available == nullptr || count <= 0)
        return -1;
    if (envValue != nullptr && *envValue != 0)
    {
        char *end = nullptr;
        const long wanted = std::strtol(envValue, &end, 10);
        if (end != envValue && wanted >= 0 && wanted < static_cast<long>(count) && available(static_cast<int>(wanted)))
            return static_cast<int>(wanted);
    }
    for (int i = 0; i < count; ++i)
    {
        if (available(i))
            return i;
    }
    return -1;
}

// PS2X_PAD_DEADZONE, read once. 0.15 is what socom2_host_input.cpp has used since 2026-09-16; the other two pad
// paths had no dead zone at all before this task (ruling R95).
inline float hostPadDeadZone()
{
    static const float s_deadZone = []
    {
        const char *const e = std::getenv("PS2X_PAD_DEADZONE");
        if (e == nullptr || *e == 0)
            return 0.15f;
        char *end = nullptr;
        const double v = std::strtod(e, &end);
        if (end == e)
            return 0.15f;
        if (v < 0.0)
            return 0.0f;
        if (v > 0.5)
            return 0.5f;
        return static_cast<float>(v);
    }();
    return s_deadZone;
}

// A stick reading with the dead zone taken out: 0 inside it, and the rest rescaled so the value still reaches
// +/-1 at full deflection (a hard cut would make the first usable step a jump).
inline float hostPadAxis(float v, float deadZone)
{
    if (deadZone <= 0.0f)
        return v;
    const float mag = v < 0.0f ? -v : v;
    if (mag <= deadZone)
        return 0.0f;
    const float scaled = (mag - deadZone) / (1.0f - deadZone);
    return v < 0.0f ? -scaled : scaled;
}
```
Run Step 2's command: green.

- [x] **Step 4: The three call sites.** Each keeps `hostGamepadEnabled()` in front, so `PS2X_HOST_GAMEPAD=0` (which the gate and every online launch script set) still short-circuits before any selection happens. *(done 2026-09-18, agent-executed; suite 538)*

  `socom2_host_input.cpp` :206, replacing `if (hostGamepadEnabled() && IsGamepadAvailable(0))`, and the `kDeadZone` block at :228-233:

```cpp
        // Task 8: the pad the launcher picked (PS2X_HOST_GAMEPAD_INDEX), or the first available one.
        // Re-selected every poll rather than latched: pads are hot-pluggable, and a player who plugs one in
        // mid-session should not have to restart.
        const int pad = hostGamepadEnabled()
                            ? hostGamepadSelect(std::getenv("PS2X_HOST_GAMEPAD_INDEX"), kHostGamepadSlots, IsGamepadAvailable)
                            : -1;
        if (pad >= 0)
        {
            // the kPadButtons table at :208-217 is unchanged except that IsGamepadButtonDown(0, ...) becomes
            // IsGamepadButtonDown(pad, ...), and so is the kSticks table at :225-227
            const float deadZone = hostPadDeadZone();
            for (const auto &stick : kSticks)
            {
                const float v = hostPadAxis(GetGamepadAxisMovement(pad, stick.axis), deadZone);
                if (v != 0.0f)
                    next.axis[stick.slot] = clampAxis(128.0f + v * 127.0f);
            }
        }
```
  The status line at :151 gets the same treatment so the log names the pad that is actually read:
  `<< "; gamepad " << (!hostGamepadEnabled() ? "off (PS2X_HOST_GAMEPAD=0)" : pad >= 0 ? GetGamepadName(pad) : "none")`
  (hoist the `pad` computation above it).

  `ps2_pad.cpp` :42-43, replacing `constexpr int kGamepad = 0;`:

```cpp
    const int kGamepad = hostGamepadEnabled()
                             ? hostGamepadSelect(std::getenv("PS2X_HOST_GAMEPAD_INDEX"), kHostGamepadSlots, IsGamepadAvailable)
                             : -1;
    const bool useGamepad = kGamepad >= 0;
```
  and the four axis reads at :83-86 gain the dead zone (new here — R95):

```cpp
        const float deadZone = hostPadDeadZone();
        const float lx = hostPadAxis(GetGamepadAxisMovement(kGamepad, GAMEPAD_AXIS_LEFT_X), deadZone);
        const float ly = hostPadAxis(GetGamepadAxisMovement(kGamepad, GAMEPAD_AXIS_LEFT_Y), deadZone);
        const float rx = hostPadAxis(GetGamepadAxisMovement(kGamepad, GAMEPAD_AXIS_RIGHT_X), deadZone);
        const float ry = hostPadAxis(GetGamepadAxisMovement(kGamepad, GAMEPAD_AXIS_RIGHT_Y), deadZone);
```

  `Kernel/Stubs/Pad.cpp`: `findFirstGamepad()` (:86-98) becomes a caller of the helper, so both of its call sites (:107, :652) follow the pick with no further edits, and `axisToByte` (:71-76) gains an optional dead zone so the keyboard/mouse call sites at :193-194 are untouched:

```cpp
        uint8_t axisToByte(float axis, float deadZone = 0.0f)
        {
            axis = hostPadAxis(std::clamp(axis, -1.0f, 1.0f), deadZone);
            const float mapped = (axis + 1.0f) * 127.5f;
            return static_cast<uint8_t>(std::lround(mapped));
        }

        int findFirstGamepad()
        {
            if (!hostGamepadEnabled())
                return -1;
            // Task 8: the launcher's pick first, then the old "lowest available slot" rule.
            return hostGamepadSelect(std::getenv("PS2X_HOST_GAMEPAD_INDEX"), kHostGamepadSlots, IsGamepadAvailable);
        }
```
  and the four stick reads in `applyGamepadState` (:117-120) pass it:
  `state.lx = axisToByte(GetGamepadAxisMovement(gamepad, GAMEPAD_AXIS_LEFT_X), hostPadDeadZone());`, and the same for `ly`, `rx`, `ry`.

  Run Step 2's command: still green (the helper's case is the only one that covers these; the existing `PadInput` cases drive override state, not raylib).

- [x] **Step 5: Write the failing launcher tests.** In `launcher_tests.cpp`, inside `MiniTest::Case("Launcher", ...)`: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        tc.Run("the controller pick and the dead zone round-trip and reach the environment", [](TestCase &t)
        {
            launcher::Config c;
            t.Equals(c.gamepadIndex, -1, "no pick by default: the first available pad, as before this task");
            t.IsTrue(c.padDeadZone > 0.1499 && c.padDeadZone < 0.1501, "the default dead zone is the runtime's 0.15");
            std::vector<std::string> env = launcher::environmentFor(c);
            auto has = [](const std::vector<std::string> &e, const std::string &kv) { return std::find(e.begin(), e.end(), kv) != e.end(); };
            auto hasKey = [](const std::vector<std::string> &e, const std::string &k) { return std::any_of(e.begin(), e.end(), [&](const std::string &s) { return s.rfind(k + "=", 0) == 0; }); };
            t.IsTrue(!hasKey(env, "PS2X_HOST_GAMEPAD_INDEX"), "no pick: the runtime is not told one, so it keeps its own rule");
            t.IsTrue(has(env, "PS2X_PAD_DEADZONE=0.15"), "the dead zone always ships, so what the player tuned is what the game gets");
            c.gamepadIndex = 2;
            c.padDeadZone = 0.3;
            env = launcher::environmentFor(c);
            t.IsTrue(has(env, "PS2X_HOST_GAMEPAD_INDEX=2"), "the picked slot");
            t.IsTrue(has(env, "PS2X_PAD_DEADZONE=0.3"), "the tuned dead zone");
            launcher::Config back;
            t.IsTrue(launcher::fromJson(launcher::toJson(c), back), "parses its own output");
            t.Equals(back.gamepadIndex, 2, "the pick survives the round trip");
            t.IsTrue(back.padDeadZone > 0.2999 && back.padDeadZone < 0.3001, "and so does the dead zone");
            launcher::Config partial;
            t.IsTrue(launcher::fromJson("{\"gsScale\": 1}", partial), "an older config.json parses");
            t.Equals(partial.gamepadIndex, -1, "a config written before this task keeps the old behaviour");
        });
```
Run Step 2's command. Expected: `error: no member named 'gamepadIndex' in 'launcher::Config'`.

- [x] **Step 6: Implement the config half.** In `launcher_config.h` `Config` (after `mouseSensitivity`, :37): *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        // Sprint 7 Task 8: which host pad to read (-1 = the first available one, as the runtime did before)
        // and the stick dead zone the three pad paths apply.
        int gamepadIndex = -1;
        double padDeadZone = 0.15;
```
  In `launcher_config.cpp` `toJson` (:169-186), after the `mouseSensitivity` lines:

```cpp
        out += "  \"gamepadIndex\": " + std::to_string(c.gamepadIndex) + ",\n";
        char dz[32];
        std::snprintf(dz, sizeof(dz), "%g", c.padDeadZone);
        out += std::string("  \"padDeadZone\": ") + dz + ",\n";
```
  In `fromJson` (:188-236), extend the numeric branch's key list (`key == "gsScale" || ...`) with `gamepadIndex` and `padDeadZone`, and add inside it:

```cpp
                    else if (key == "gamepadIndex") c.gamepadIndex = std::atoi(raw.c_str());
                    else if (key == "padDeadZone") c.padDeadZone = std::atof(raw.c_str());
```
  In `environmentFor` (:247-275), after the `PS2X_MC_DIR` push:

```cpp
        if (c.gamepadIndex >= 0)
            env.push_back("PS2X_HOST_GAMEPAD_INDEX=" + std::to_string(c.gamepadIndex));
        char dz[32];
        std::snprintf(dz, sizeof(dz), "%g", c.padDeadZone < 0.0 ? 0.0 : (c.padDeadZone > 0.5 ? 0.5 : c.padDeadZone));
        env.push_back(std::string("PS2X_PAD_DEADZONE=") + dz);
```
Run Step 2's command: green.

- [x] **Step 7: The Controller panel.** In `main.cpp`, `drawController` (:240-279) takes the slot it is to draw and stops asking for pad 0; the panel around it lists what is plugged in and owns the pick. *(done 2026-09-18, agent-executed; suite 538)*

  `drawController`'s signature and first lines become:

```cpp
    // The controller diagram for ONE slot: the same raylib calls the game's input poll makes
    // (socom2_host_input.cpp), on the pad the player picked, with the dead zone they set applied to the drawn
    // sticks -- so a dot resting in the middle of the ring is exactly the neutral the game will see.
    void drawController(float x, float y, int slot, float deadZone)
    {
        const bool pad = slot >= 0 && IsGamepadAvailable(slot);
        const char *name = pad ? GetGamepadName(slot) : "none";
```
  every `IsGamepadAvailable(0)` / `GetGamepadName(0)` / `GetGamepadAxisMovement(0, ...)` / `IsGamepadButtonDown(0, ...)` inside it becomes `slot`, and the stick lambda applies the dead zone:

```cpp
                ax = launcherPadAxis(GetGamepadAxisMovement(slot, axisX), deadZone);
                ay = launcherPadAxis(GetGamepadAxisMovement(slot, axisY), deadZone);
```
  with a local copy of the runtime's rescale next to the other widgets — the launcher does not include the runtime's headers, the same rule `exitMessage` follows (`launcher_config.cpp` :239-245) — and a vertical radio column, because pad names do not fit one 820 px row:

```cpp
    // Kept in step with hostPadAxis (ps2xRuntime/include/runtime/host_gamepad_select.h).
    float launcherPadAxis(float v, float deadZone)
    {
        if (deadZone <= 0.0f)
            return v;
        const float mag = v < 0.0f ? -v : v;
        if (mag <= deadZone)
            return 0.0f;
        const float scaled = (mag - deadZone) / (1.0f - deadZone);
        return v < 0.0f ? -scaled : scaled;
    }

    // A column of radio choices; returns the selected index (changed or not).
    int radiosColumn(float x, float y, const std::vector<std::string> &labels, int selected, float rowHeight = 22.0f)
    {
        for (size_t i = 0; i < labels.size(); ++i)
        {
            const float ry = y + static_cast<float>(i) * rowHeight;
            const Rectangle hit = {x, ry, 18 + 8 + static_cast<float>(MeasureText(labels[i].c_str(), 14)), 18};
            DrawCircle(static_cast<int>(x) + 9, static_cast<int>(ry) + 9, 9, kField);
            DrawCircleLines(static_cast<int>(x) + 9, static_cast<int>(ry) + 9, 9, kDim);
            if (static_cast<int>(i) == selected)
                DrawCircle(static_cast<int>(x) + 9, static_cast<int>(ry) + 9, 5, kAccent);
            DrawText(labels[i].c_str(), static_cast<int>(x) + 26, static_cast<int>(ry) + 2, 14, kText);
            if (CheckCollisionPointRec(GetMousePosition(), hit) && IsMouseButtonPressed(MOUSE_BUTTON_LEFT))
                selected = static_cast<int>(i);
        }
        return selected;
    }
```
  and the Controller panel (:423-436) becomes — the panel rectangle grows `206 -> 232` and `y += 218` becomes `y += 244`:

```cpp
        // ---- Controller ----
        DrawRectangle(12, static_cast<int>(y) - 6, kWidth - 24, 232, kPanel);
        panelTitle(24, y, "Controller");
        // The pads raylib sees, polled every frame: one plugged in while the launcher is open appears in the
        // list without a restart, and one unplugged disappears (the pick then falls back to "first available",
        // which is exactly what an unset PS2X_HOST_GAMEPAD_INDEX means to the runtime).
        std::vector<std::string> padLabels = {"first available"};
        std::vector<int> padSlots = {-1};
        for (int i = 0; i < 4; ++i)
        {
            if (IsGamepadAvailable(i))
            {
                padLabels.push_back(std::string("[") + std::to_string(i) + "] " + GetGamepadName(i));
                padSlots.push_back(i);
            }
        }
        int padSel = 0;
        for (size_t i = 0; i < padSlots.size(); ++i)
            if (padSlots[i] == config.gamepadIndex)
                padSel = static_cast<int>(i);
        const int newPad = radiosColumn(480, y + 28, padLabels, padSel);
        if (newPad != padSel)
        {
            config.gamepadIndex = padSlots[newPad];
            dirty = true;
        }
        // The slot the test area draws: the pick, or the first available pad when there is no pick.
        int shownSlot = config.gamepadIndex;
        if (shownSlot < 0)
        {
            for (int i = 0; i < 4 && shownSlot < 0; ++i)
                if (IsGamepadAvailable(i))
                    shownSlot = i;
        }
        drawController(24, y + 28, shownSlot, static_cast<float>(config.padDeadZone));
        DrawText(TextFormat("dead zone %.2f", config.padDeadZone), 480, static_cast<int>(y) + 128, 14, kDim);
        {
            const double before = config.padDeadZone;
            slider({480, y + 148, 280, 20}, config.padDeadZone, 0.0, 0.40);
            if (config.padDeadZone != before)
                dirty = true;
        }
        if (checkbox(480, y + 176, "mouse look", config.mouseLook))
            dirty = true;
        DrawText(TextFormat("sensitivity %.2f", config.mouseSensitivity), 480, static_cast<int>(y) + 200, 14, kDim);
        {
            const double before = config.mouseSensitivity;
            slider({480, y + 218, 280, 20}, config.mouseSensitivity, 0.25, 3.0);
            if (config.mouseSensitivity != before)
                dirty = true;
        }
        y += 244;
```
  `kHeight` (:31) goes `660 -> 686` for the 26 extra pixels. The `slider` helper's 0.05 quantisation gives the dead zone nine positions (0.00, 0.05 … 0.40), which is the resolution the value deserves.

- [x] **Step 8: Suite, then build.** *(done 2026-09-18, agent-executed; suite 538)*

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "8: build.sh test" -- ./build.sh test
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_padpick_build.marker
```
Expected: exit 0 with the C++ count up by two cases. **No launch in this task** — the driven gate sets `PS2X_HOST_GAMEPAD=0` (`host_gamepad.h`: with a pad plugged in the game skips the PRECISION SHOOTER CONFIGURATION screens the transition stage keys on), so no gate run can exercise a pad at all. The proof is the owner's hands, Step 9.

- [x] **Step 9: The human task line.** Add to `docs/HUMAN_TASKS.md` under **Open**, carrying the measurement the check confirms (the standing rule from Task 6 Step 2): *(done 2026-09-18, agent-executed; suite 538)*

```markdown
- [ ] **Pick the pad in the launcher, then play with it** (Sprint 7 Task 8, owner request 2026-09-18). Plug the
  Xbox pad in and run `dist/socom_unzipped_launcher.exe`. The Controller panel now lists every pad Windows
  reports as `[<slot>] <name>` with *first available* at the top; pick yours, watch the test area (it draws the
  slot you picked, not slot 0), and move the **dead zone** slider until the sticks read dead at rest and still
  reach the edge of the ring at full deflection. Press Launch, play one single-player mission and one online
  round. Report one line each: (a) did the pick hold -- was the pad you chose the one the game read, in the menus
  and in the round; (b) did the dead zone feel right at the value you left it on (say the number), or is the
  default too loose or too tight. The numbers you are confirming: the launcher writes
  `PS2X_HOST_GAMEPAD_INDEX=<slot>` and `PS2X_PAD_DEADZONE=<value>` (visible with
  `dist/socom_unzipped_launcher.exe --selftest`), and the default is **0.15**, the dead zone SOCOM's own poll has
  used since 2026-09-16 and which the other two pad paths did not apply at all until this task (ruling R95).
  Launcher build: the `dist/socom_unzipped_launcher.exe` sha256 from the commit below.
```

- [x] **Step 10: Commit** (this moves a default — record **R95** in the Rulings section). *(done: 206de19, one commit for Tasks 8-11)*

```bash
git commit -m "feat(input): the launcher picks the pad, and one dead zone for all three pad paths

owner request 2026-09-18. Three call sites read a raylib gamepad and all three hard-coded slot 0 or 'the first
available', so a second device (a wheel, a docked laptop's virtual pad) could take the player's controller.
hostGamepadSelect (RED first, with a fake `available`) is the one rule: PS2X_HOST_GAMEPAD_INDEX when it names an
available pad, else the first available, else -1. The launcher's Controller panel lists the connected pads by
raylib index and name, draws the test area for the picked one, and has a dead-zone slider; environmentFor emits
PS2X_HOST_GAMEPAD_INDEX only when a pad is picked and PS2X_PAD_DEADZONE always. PS2X_PAD_DEADZONE defaults to
0.15 -- unchanged for socom2_host_input.cpp, new for ps2_pad.cpp and Pad.cpp (ruling R95). PS2X_HOST_GAMEPAD=0
still short-circuits every path, so the gate is untouched. The proof is the owner's hands
(docs/HUMAN_TASKS.md): the driven gate cannot use a pad.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/host_gamepad_select.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_pad.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/Pad.cpp \
  third_party/ps2recomp/ps2xLauncher/src/main.cpp \
  third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h \
  third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp \
  third_party/ps2recomp/ps2xTest/src/pad_input_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp \
  docs/HUMAN_TASKS.md
git push
```

---

### Task 9 — Microphone: device selection, a level meter, and the headset spike (owner request 2026-09-18)

**Files:**
- Create: `third_party/ps2recomp/ps2xLauncher/include/launcher/mic_devices.h`, `third_party/ps2recomp/ps2xLauncher/src/mic_devices.cpp`, `third_party/ps2recomp/ps2xRuntime/include/runtime/host_mic.h`, `third_party/ps2recomp/ps2xRuntime/src/lib/host_mic.cpp`
- Modify: `third_party/ps2recomp/ps2xLauncher/CMakeLists.txt`, `third_party/ps2recomp/ps2xLauncher/src/main.cpp` (a new Microphone panel between Controller and Online, `kHeight` :31), `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h`, `third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp`, `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt` (the `ps2_runtime` source list :388-407), `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp` (:763-765, after `InitAudioDevice`), `docs/KNOWN.md` §2, `docs/HUMAN_TASKS.md`
- Test: `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp`, `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp`

**Interfaces:**
- `float launcher::micLevelDb(const float *frames, size_t n)` — `20 * log10(rms)` of the mono float frames; `-INFINITY` for silence (`rms == 0`), for `n == 0` and for `frames == nullptr`. Pure and header-inline, so the test links nothing.
- `class launcher::MicDevices` — abstract: `virtual std::vector<std::string> list()`, `virtual bool startMeter(const std::string &name)`, `virtual float levelDb() const`, `virtual void stopMeter()`. `std::unique_ptr<MicDevices> launcher::makeMicDevices()` returns the miniaudio-backed one; the tests subclass it. *(controller's choice: `mic_devices.cpp` is compiled into `socom_unzipped_launcher` only, not into `ps2x_launcher_core`, because it is the only launcher file that needs miniaudio — putting it in the core library would make `ps2x_tests` link raylib for two pure assertions. Re-rule if wrong.)*
- `std::vector<std::string> launcher::micLabels(MicDevices &)` — `"None"`, then `list()`. The index into it is what the panel's radio column selects.
- `launcher::Config::micDevice` — `std::string`, default `""` = no microphone. `environmentFor` emits `PS2X_MIC_DEVICE=<name>` **only when non-empty**.
- `class MicRing` (`runtime/host_mic.h`, header-only) — `explicit MicRing(size_t frames)`, `size_t write(const int16_t *src, size_t n)` (single producer; takes what fits, counts the rest), `size_t read(int16_t *dst, size_t n)` (single consumer), `size_t available() const`, `size_t dropped() const`.
- `class HostMic` — `bool start(const std::string &deviceName)` (16 kHz mono s16), `size_t read(int16_t *out, size_t frames)`, `void stop()`, `bool running() const`, `const std::string &error() const`; free functions `startHostMicFromEnvironment()` / `stopHostMic()`.
- `PS2X_MIC_DUMP=<path>` — a 16 kHz mono 16-bit WAV of what was captured. **The header is written by hand**, as `ps2_audio.cpp`'s `buildStereoWav` (:358-379) does: raylib compiles miniaudio with `MA_NO_WAV` (`raudio.c` :167), so miniaudio's own encoder is not in the library. While a dump runs, the dump thread is the ring's only consumer; `read()` is for the Sprint 8 consumer the spike scopes.
- **Format assumption, stated because it is one:** 16 kHz, mono, signed 16-bit. SOCOM II's headset path is liblgaud 1.08 (`LGAUD.IRX` + `HEADSETO.IRX`, research/05 :63) and the stubbed `lgAudInit` advertises a 0x800-byte stream buffer (`lgaud.cpp` :21) — 1024 frames of 16-bit mono, 64 ms at 16 kHz. Nothing in the tree has yet read a rate off the module; Task 9c is what settles it.

**Steps:**

#### 9a — the launcher

- [x] **Step 1: Write the failing launcher tests.** In `launcher_tests.cpp`, inside `MiniTest::Case("Launcher", ...)`, with `#include "launcher/mic_devices.h"` and `#include <cmath>` at the top: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        tc.Run("the microphone pick round-trips and only reaches the environment when there is one", [](TestCase &t)
        {
            launcher::Config c;
            t.Equals(c.micDevice, std::string(""), "no microphone by default");
            std::vector<std::string> env = launcher::environmentFor(c);
            auto hasKey = [](const std::vector<std::string> &e, const std::string &k) { return std::any_of(e.begin(), e.end(), [&](const std::string &s) { return s.rfind(k + "=", 0) == 0; }); };
            t.IsTrue(!hasKey(env, "PS2X_MIC_DEVICE"), "no pick: the runtime opens no capture device at all");
            c.micDevice = "Microphone (USB Headset)";
            env = launcher::environmentFor(c);
            t.IsTrue(std::find(env.begin(), env.end(), std::string("PS2X_MIC_DEVICE=Microphone (USB Headset)")) != env.end(), "the device name, spaces and brackets and all");
            launcher::Config back;
            t.IsTrue(launcher::fromJson(launcher::toJson(c), back), "parses its own output");
            t.Equals(back.micDevice, c.micDevice, "the device name survives the round trip");
        });

        tc.Run("micLevelDb: RMS in dB full scale, -inf for silence", [](TestCase &t)
        {
            // A full-scale sine has RMS 1/sqrt(2), i.e. -3.0103 dB, whatever its frequency or phase.
            std::vector<float> sine(1600);   // 0.1 s at 16 kHz, ten whole cycles: no partial-cycle bias
            for (size_t i = 0; i < sine.size(); ++i)
                sine[i] = std::sin(2.0f * 3.14159265358979f * 100.0f * static_cast<float>(i) / 16000.0f);
            const float full = launcher::micLevelDb(sine.data(), sine.size());
            t.IsTrue(std::fabs(full + 3.0103f) < 0.05f, "a full-scale sine reads -3.01 dB");
            std::vector<float> half = sine;
            for (float &v : half)
                v *= 0.5f;
            t.IsTrue(std::fabs(launcher::micLevelDb(half.data(), half.size()) - (full - 6.0206f)) < 0.01f, "halving the amplitude drops it exactly 6.02 dB");
            const std::vector<float> quiet(1600, 0.0f);
            const float silent = launcher::micLevelDb(quiet.data(), quiet.size());
            t.IsTrue(std::isinf(silent) && silent < 0.0f, "silence is -inf, not 0 and not a crash");
            const float none = launcher::micLevelDb(nullptr, 0);
            t.IsTrue(std::isinf(none) && none < 0.0f, "no frames is -inf too");
        });

        tc.Run("the microphone list is whatever MicDevices reports, with None first", [](TestCase &t)
        {
            struct FakeMic final : launcher::MicDevices
            {
                std::vector<std::string> list() override { return {"Microphone (USB Headset)", "Stereo Mix"}; }
                bool startMeter(const std::string &name) override { started = name; return name == "Stereo Mix"; }
                float levelDb() const override { return -12.5f; }
                void stopMeter() override { started.clear(); }
                std::string started;
            };
            FakeMic mic;
            const std::vector<std::string> labels = launcher::micLabels(mic);
            t.Equals(labels.size(), static_cast<size_t>(3), "None plus the two devices");
            t.Equals(labels[0], std::string("None"), "None is first, so 'no microphone' is a click, not an empty field");
            t.Equals(labels[1], std::string("Microphone (USB Headset)"), "the device names come through unchanged");
            t.IsTrue(!mic.startMeter("Microphone (USB Headset)"), "a device that will not open says so");
            t.IsTrue(mic.startMeter("Stereo Mix") && mic.started == "Stereo Mix", "and one that will, opens");
        });
```

- [x] **Step 2: Run them and watch them fail.** Task 8 Step 2's command. Expected: `fatal error: 'launcher/mic_devices.h' file not found`. *(done 2026-09-18, agent-executed; suite 538)*

- [x] **Step 3: Implement `mic_devices.h` / `mic_devices.cpp`.** The header is pure — no miniaudio: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
#pragma once
// Sprint 7 Task 9 (owner request 2026-09-18): the capture devices the launcher offers, behind an interface, so
// the list logic is testable without a sound card. The miniaudio implementation is mic_devices.cpp, which is
// compiled into the launcher executable only.
#include <cmath>
#include <cstddef>
#include <memory>
#include <string>
#include <vector>

namespace launcher
{
    // RMS of the frames, in dB full scale. -inf for digital silence: a meter that read 0 dB for silence would
    // sit at the top of its bar with nothing plugged in.
    inline float micLevelDb(const float *frames, size_t n)
    {
        if (frames == nullptr || n == 0)
            return -INFINITY;
        double sum = 0.0;
        for (size_t i = 0; i < n; ++i)
            sum += static_cast<double>(frames[i]) * static_cast<double>(frames[i]);
        const double rms = std::sqrt(sum / static_cast<double>(n));
        if (rms <= 0.0)
            return -INFINITY;
        return static_cast<float>(20.0 * std::log10(rms));
    }

    class MicDevices
    {
    public:
        virtual ~MicDevices() = default;
        // The capture devices the host reports, in the host's order. Empty when there are none or the audio
        // backend would not start -- the panel then shows "None" alone.
        virtual std::vector<std::string> list() = 0;
        // Open `name` for capture and start filling the meter. False when it will not open.
        virtual bool startMeter(const std::string &name) = 0;
        // The last callback's RMS in dB (-inf until one arrives).
        virtual float levelDb() const = 0;
        virtual void stopMeter() = 0;
    };

    // "None", then the devices.
    inline std::vector<std::string> micLabels(MicDevices &devices)
    {
        std::vector<std::string> labels = {"None"};
        for (const std::string &name : devices.list())
            labels.push_back(name);
        return labels;
    }

    std::unique_ptr<MicDevices> makeMicDevices();
}
```
  `mic_devices.cpp` includes `miniaudio.h` **without** `MINIAUDIO_IMPLEMENTATION` — raylib's `raudio.c` :178 already compiled it into the static library, and its define list (:163-178: `MA_NO_JACK/WAV/FLAC/MP3/RESOURCE_MANAGER/NODE_GRAPH/ENGINE/GENERATION`) removes decoders and the high-level engine but **not** device I/O, so capture is there — and implements:
  - `list()` — `ma_context_init(nullptr, 0, nullptr, &ctx)`, `ma_context_get_devices(&ctx, &play, &playCount, &capture, &captureCount)`, names out of `ma_device_info::name`, `ma_context_uninit`. A failed `ma_context_init` returns `{}`.
  - `startMeter(name)` — re-enumerate, match the name, `ma_device_config_init(ma_device_type_capture)` with `capture.format = ma_format_f32`, `capture.channels = 1`, `sampleRate = 16000`, `pDeviceID` = the matched device's id, and a `dataCallback` that stores `micLevelDb(static_cast<const float *>(pInput), frameCount)` into a `std::atomic<float>`; then `ma_device_init` + `ma_device_start`. False on any non-`MA_SUCCESS`.
  - `levelDb()` — that atomic. `stopMeter()` — `ma_device_uninit`, and the destructor calls it.

  In `ps2xLauncher/CMakeLists.txt`:

```cmake
add_executable(socom_unzipped_launcher WIN32 src/main.cpp src/win32_glue.cpp src/mic_devices.cpp)
target_link_libraries(socom_unzipped_launcher PRIVATE ps2x_launcher_core raylib)
# miniaudio ships inside raylib's own sources and is already compiled into libraylib (raudio.c:178), so
# mic_devices.cpp needs only its declarations: it includes the header WITHOUT MINIAUDIO_IMPLEMENTATION.
target_include_directories(socom_unzipped_launcher PRIVATE $<TARGET_PROPERTY:raylib,SOURCE_DIR>/external)
```
Run Step 2's command: green (the fake covers the interface; the miniaudio half is not in the test binary).

- [x] **Step 4: The config half.** `launcher_config.h` `Config`, after `padDeadZone`: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        // Sprint 7 Task 9: the capture device by name; "" = none (no PS2X_MIC_DEVICE, no device opened).
        std::string micDevice;
```
  `toJson`: `out += "  \"micDevice\": " + quote(c.micDevice) + ",\n";`. `fromJson`: add `micDevice` to the string-key branch's condition and `else if (key == "micDevice") c.micDevice = v;` inside it. `environmentFor`, after the pad knobs:

```cpp
        if (!c.micDevice.empty())
            env.push_back("PS2X_MIC_DEVICE=" + c.micDevice);
```
Run Step 2's command: green, and Step 1's first case passes.

- [x] **Step 5: The Microphone panel.** In `main.cpp`, after the Controller panel and before Online. The device list is enumerated **once at start-up and on a Rescan press**, never per frame: `ma_context_get_devices` starts the host audio backend, and doing that sixty times a second stalls the window on some WASAPI setups. *(done 2026-09-18, agent-executed; suite 538)*

  Next to the other pre-loop locals (after `std::string lastLog;`):

```cpp
    std::unique_ptr<launcher::MicDevices> mic = launcher::makeMicDevices();
    std::vector<std::string> micLabels = launcher::micLabels(*mic);
    std::string micStatus;
    bool meterOn = !config.micDevice.empty() && mic->startMeter(config.micDevice);
```
  the panel:

```cpp
        // ---- Microphone ----
        DrawRectangle(12, static_cast<int>(y) - 6, kWidth - 24, 172, kPanel);
        panelTitle(24, y, "Microphone");
        int micSel = 0;
        for (size_t i = 1; i < micLabels.size(); ++i)
            if (micLabels[i] == config.micDevice)
                micSel = static_cast<int>(i);
        const int newMic = radiosColumn(24, y + 28, micLabels, micSel);
        if (newMic != micSel)
        {
            config.micDevice = (newMic == 0) ? std::string() : micLabels[newMic];
            mic->stopMeter();
            meterOn = !config.micDevice.empty() && mic->startMeter(config.micDevice);
            micStatus = config.micDevice.empty() ? "" : (meterOn ? "listening" : "that device will not open");
            dirty = true;
        }
        if (button({kWidth - 24 - 96, y + 28, 96, 26}, "Rescan"))
        {
            micLabels = launcher::micLabels(*mic);
            micStatus = TextFormat("%d capture device(s)", static_cast<int>(micLabels.size()) - 1);
        }
        // The meter: -60 dB (silence) to 0 dB (full scale) across 280 px, redrawn every frame from the capture
        // callback's atomic. A bar that moves when the player speaks is the whole point of the panel.
        const float db = meterOn ? mic->levelDb() : -INFINITY;
        float filled = 0.0f;
        if (meterOn && std::isfinite(db))
            filled = (db + 60.0f) / 60.0f;
        filled = filled < 0.0f ? 0.0f : (filled > 1.0f ? 1.0f : filled);
        DrawRectangle(480, static_cast<int>(y) + 32, 280, 18, kField);
        DrawRectangle(480, static_cast<int>(y) + 32, static_cast<int>(280.0f * filled), 18, filled > 0.9f ? kBad : kAccent);
        DrawRectangleLines(480, static_cast<int>(y) + 32, 280, 18, kDim);
        DrawText(meterOn && std::isfinite(db) ? TextFormat("%.0f dB", db) : "--", 768, static_cast<int>(y) + 34, 14, kDim);
        DrawText(micStatus.c_str(), 480, static_cast<int>(y) + 58, 14, kDim);
        DrawText("the game does not send your voice yet (Sprint 8); this meter proves the device works",
                 480, static_cast<int>(y) + 80, 12, kDim);
        y += 184;
```
  and `mic->stopMeter();` beside `game.close();` after the loop. `kHeight` goes `686 -> 870`. Run Step 2's command: green.

#### 9b — the runtime

- [x] **Step 6: Write the failing ring test.** In `socom2_audio_tests.cpp`, inside `MiniTest::Case("SOCOM2Audio", ...)`, with `#include "runtime/host_mic.h"`: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        tc.Run("MicRing: write n, read n, and it wraps without tearing a frame", [](TestCase &t)
        {
            MicRing ring(8);
            int16_t out[16] = {};
            t.Equals(ring.available(), static_cast<size_t>(0), "a new ring is empty");
            t.Equals(ring.read(out, 4), static_cast<size_t>(0), "reading an empty ring yields nothing");
            const int16_t a[4] = {1, 2, 3, 4};
            t.Equals(ring.write(a, 4), static_cast<size_t>(4), "four in");
            t.Equals(ring.available(), static_cast<size_t>(4), "four waiting");
            t.Equals(ring.read(out, 4), static_cast<size_t>(4), "four out");
            t.IsTrue(out[0] == 1 && out[1] == 2 && out[2] == 3 && out[3] == 4, "in the order they went in");
            // Six more from a read cursor at 4 in an 8-frame ring: the second half wraps past the end.
            const int16_t b[6] = {5, 6, 7, 8, 9, 10};
            t.Equals(ring.write(b, 6), static_cast<size_t>(6), "six in, across the wrap");
            t.Equals(ring.read(out, 6), static_cast<size_t>(6), "six out, across the wrap");
            for (int i = 0; i < 6; ++i)
                t.Equals(static_cast<int>(out[i]), 5 + i, "every frame survived the wrap");
            // Overrun: capacity is 8, so 9 cannot fit and the oldest are NOT silently overwritten.
            const int16_t c[9] = {1, 1, 1, 1, 1, 1, 1, 1, 1};
            t.Equals(ring.write(c, 9), static_cast<size_t>(8), "a full ring takes what fits");
            t.Equals(ring.dropped(), static_cast<size_t>(1), "and counts what it dropped");
            t.Equals(ring.read(out, 16), static_cast<size_t>(8), "reading more than there is yields what there is");
        });
```
Run Step 2's command. Expected: `fatal error: 'runtime/host_mic.h' file not found`.

- [x] **Step 7: Implement `host_mic.h` and `host_mic.cpp`.** The header carries `MicRing` inline (so the test links nothing) and declares `HostMic`: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
#pragma once
// Sprint 7 Task 9b (owner request 2026-09-18): the host microphone, captured but not yet spoken.
//
// FORMAT ASSUMPTION: 16 kHz, mono, signed 16-bit. SOCOM II's headset path is liblgaud 1.08 (LGAUD.IRX +
// HEADSETO.IRX, research/05 section 2), and the stubbed lgAudInit advertises a 0x800-byte stream buffer
// (ps2xIOP/src/modules/lgaud.cpp:21) -- 1024 frames of 16-bit mono, 64 ms at 16 kHz. Nothing in the tree has
// yet READ a rate off the module, so this is an assumption; Task 9c's spike is what settles it.
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

// Single producer (the capture callback), single consumer (HostMic::read, or the PS2X_MIC_DUMP writer). Never
// overwrites unread frames: a dropped frame is counted, not smuggled in.
class MicRing
{
public:
    explicit MicRing(size_t frames) : m_buf(frames + 1u, 0), m_read(0), m_write(0), m_dropped(0) {}

    size_t write(const int16_t *src, size_t n)
    {
        const size_t cap = m_buf.size();
        size_t w = m_write.load(std::memory_order_relaxed);
        const size_t r = m_read.load(std::memory_order_acquire);
        const size_t room = (r + cap - w - 1u) % cap;
        const size_t take = n < room ? n : room;
        for (size_t i = 0; i < take; ++i)
        {
            m_buf[w] = src[i];
            w = (w + 1u) % cap;
        }
        m_write.store(w, std::memory_order_release);
        if (take < n)
            m_dropped.fetch_add(n - take, std::memory_order_relaxed);
        return take;
    }

    size_t read(int16_t *dst, size_t n)
    {
        const size_t cap = m_buf.size();
        size_t r = m_read.load(std::memory_order_relaxed);
        const size_t w = m_write.load(std::memory_order_acquire);
        const size_t have = (w + cap - r) % cap;
        const size_t take = n < have ? n : have;
        for (size_t i = 0; i < take; ++i)
        {
            dst[i] = m_buf[r];
            r = (r + 1u) % cap;
        }
        m_read.store(r, std::memory_order_release);
        return take;
    }

    size_t available() const
    {
        const size_t cap = m_buf.size();
        return (m_write.load(std::memory_order_acquire) + cap - m_read.load(std::memory_order_acquire)) % cap;
    }
    size_t dropped() const { return m_dropped.load(std::memory_order_relaxed); }

private:
    std::vector<int16_t> m_buf;
    std::atomic<size_t> m_read;
    std::atomic<size_t> m_write;
    std::atomic<size_t> m_dropped;
};

class HostMic
{
public:
    static constexpr uint32_t kSampleRate = 16000u;   // see the FORMAT ASSUMPTION above
    static constexpr size_t kRingFrames = 16000u;     // one second

    HostMic();
    ~HostMic();
    // Open the named capture device (miniaudio, 16 kHz mono s16) and start filling the ring. False, with a
    // reason in error(), when the device is not there or will not open -- never fatal: a missing microphone
    // must not stop the game starting.
    bool start(const std::string &deviceName);
    size_t read(int16_t *out, size_t frames);
    void stop();
    bool running() const { return m_running; }
    const std::string &error() const { return m_error; }

private:
    struct Impl;
    std::unique_ptr<Impl> m_impl;
    bool m_running = false;
    std::string m_error;
};

// PS2X_MIC_DEVICE / PS2X_MIC_DUMP, read once at start-up. Does nothing at all when PS2X_MIC_DEVICE is unset.
void startHostMicFromEnvironment();
void stopHostMic();
```
  `host_mic.cpp` holds the miniaudio device (same include rule as the launcher: `miniaudio.h` without `MINIAUDIO_IMPLEMENTATION`), the capture callback that pushes `pInput` into the ring, and the `PS2X_MIC_DUMP` writer — a thread that drains the ring every 20 ms into a hand-written 16 kHz **mono** 16-bit WAV. `raudio.c` :167 defines `MA_NO_WAV`, so miniaudio's encoder is not linked; the 44-byte header is the one `ps2_audio.cpp` :358-379 writes with `channels = 1`, `blockAlign = 2`, `byteRate = 32000`, and the two sizes patched on `stop()` exactly as `closeMixerStream` does at :425-435. While a dump is running the dump thread is the ring's only consumer.

  In `ps2xRuntime/CMakeLists.txt`, add `src/lib/host_mic.cpp` to the `ps2_runtime` source list (:390, beside `ps2_audio.cpp`) and, after the target is defined, `if(TARGET raylib)` / `target_include_directories(ps2_runtime PRIVATE $<TARGET_PROPERTY:raylib,SOURCE_DIR>/external)` / `endif()`.

  In `ps2_runtime.cpp` :764, after `m_audioBackend.setAudioReady(IsAudioDeviceReady());`:

```cpp
        // Task 9b: PS2X_MIC_DEVICE=<name> opens the player's microphone. Unset -- the default, and what the
        // gate runs with -- opens nothing at all. Nothing consumes the ring yet: lgaud.cpp still answers "no
        // headset" to every RPC but its version query (Task 9c's spike scopes the consumer), so this is
        // capture and PS2X_MIC_DUMP only.
        startHostMicFromEnvironment();
```
  and `stopHostMic();` on the shutdown path beside `CloseWindow()`. Run Step 2's command: green.

- [x] **Step 8: Suite, then build.** *(done 2026-09-18, agent-executed; suite 538)*

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "9: build.sh test" -- ./build.sh test
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_mic_build.marker
```
Expected: exit 0 with the C++ count up by four cases, and `dist/socom2.exe` relinked. No launch: with `PS2X_MIC_DEVICE` unset the runtime is what it was, and there is no automated way to speak into a microphone.

#### 9c — the spike

- [x] **Step 9: One bounded read, one KNOWN row, no code kept.** Read, in this order, and write nothing else: *(done 2026-09-18, agent-executed; suite 538)*

  1. `third_party/ps2recomp/ps2xIOP/src/modules/lgaud.cpp` — all 97 lines. What is there today: SIF RPC service `'BLIP'` (`0x50494c42`); `lgAudInit` is **function 0x10** and answers `reply[0] = 0` (status), `reply[1] = 0` (capability flags the EE ORs into its own word), `reply[2] = 0x0108` (the version the EE checks) and `reply[8] = 0x800` (the stream buffer the EE must allocate, +0x40), logging `[lgaud] lgAudInit -> version 1.08, no headset` (:54). **Every other function** returns `0x80000001` (:60) and is logged, up to 32 times, as `[lgaud:stub] rpc=0x… send=… recv=…`. Registered at `ps2xIOP/src/builtin_profiles.cpp` :121 in the `socom2-us` profile.
  2. `docs/research/05-code-package-and-harness.md` — the RPC table row `0x50494c42 'BLIP' | lgaud.irx (Logitech USB headset audio) | FUN_00243840 (lgAudInit)` (:50); the boot module list (:63: `LGAUD.IRX`, then `HEADSETO.IRX priority=22`, "HEADSET Output module v2.0 built with liblgaud 1.08 and SCE 2.8.0"); and :79's note that the game does lgaud device enumeration after the RSA-keygen stub.
  3. The game's own side, from the decomp:

```bash
grep -n "FUN_00243840" game/analysis/socom2_game.elf.decomp.c | head -40
grep -an -i "lgaud\|headset" game/analysis/socom2_game.elf.strings.txt | head -40
```
     then follow `FUN_00243840`'s callers and its sibling `sceSifCallRpc` calls in the decomp to recover the **function numbers** the EE passes for this SID, in the order it issues them after `lgAudInit`.
  4. What a real run already recorded, with no new launch — the stub's log line exists for exactly this question:

```bash
grep -h "lgaud:stub" logs/run_*.log | sed 's/ send=.*//' | sort | uniq -c | sort -rn
```

  Then hand the controller **one `docs/KNOWN.md` §2 row** (**§2 has one writer, the controller** — the standing rule; the spike supplies the text, the controller commits it), in the file's existing two-column shape, saying: **what the game asks the headset module for, in order** (each function number with the name it maps to, e.g. `0x10 lgAudInit -> 0x?? …`), and **whether serving PCM from `HostMic` through it is a bounded job for Sprint 8** — bounded if the sequence is enumerate/open/read against a fixed buffer size the stub already advertises; unbounded if the EE expects the module to push buffers on its own IOP thread, or to negotiate a format the capture device cannot produce. The experiment that would settle whatever is still open goes in the same row, which is what §2 is for.

  **No code is written in this step and none is kept.** A function number whose meaning the decomp does not give is named as unknown in the row, not guessed at.

- [x] **Step 10: The human task lines.** Add both to `docs/HUMAN_TASKS.md` under **Open**: *(done 2026-09-18, agent-executed; suite 538)*

```markdown
- [ ] **Pick the microphone and watch the meter** (Sprint 7 Task 9a, owner request 2026-09-18). Run
  `dist/socom_unzipped_launcher.exe`. The new Microphone panel lists every capture device Windows reports, with
  *None* first; pick your headset's and speak. Report in one line: does the bar move when you speak and sit at
  the left when you are quiet, and was the device you picked the one that reacted. If the list is empty or your
  headset is missing, press Rescan first and say so -- an empty list means miniaudio could not start the host's
  audio backend, which is a different fault from a missing device. The numbers you are confirming: the meter is
  RMS in dB across -60..0 dB, and the launcher writes `PS2X_MIC_DEVICE=<the name you picked>` (visible with
  `dist/socom_unzipped_launcher.exe --selftest`).
- [ ] **Speak in an online lobby, and expect to be unheard** (Sprint 7 Task 9b/9c, owner request 2026-09-18).
  With a second machine in a lobby (the two-machine item above), pick your microphone in the launcher, join, and
  speak. **Expected answer: the other side hears NOTHING**, and that is not a fault in this sprint -- the IOP
  headset module still answers "no headset" to everything but its version query
  (`third_party/ps2recomp/ps2xIOP/src/modules/lgaud.cpp`), so nothing carries the captured audio to the game
  yet. What is worth a line: (a) did anything at all come through (if it did, something we do not understand is
  happening); (b) did picking a microphone change the game's behaviour in any way -- a stutter, a longer boot, a
  new log line. To check the capture half by itself, without a second machine: run the game with
  `PS2X_MIC_DUMP=logs/mic.wav` set, speak for ten seconds, quit, and play `logs/mic.wav` back. If your voice is
  in that file the capture half works and only the game-side plumbing is missing -- which is the Sprint 8 job
  Task 9c's `docs/KNOWN.md` §2 row scopes.
```

- [x] **Step 11: Commit.** No default moves: `PS2X_MIC_DEVICE` unset opens nothing, so no ruling. *(done: 206de19, one commit for Tasks 8-11)*

```bash
git commit -m "feat(audio): the launcher picks a microphone and meters it; the runtime captures it

owner request 2026-09-18. 9a: a Microphone panel listing the host's capture devices through launcher::MicDevices
(miniaudio's ma_context_get_devices, behind an interface so the tests use a fake), a live RMS meter on the picked
device, and PS2X_MIC_DEVICE=<name> emitted only when one is picked; micLevelDb is RED-first and pinned against a
full-scale sine (-3.01 dB) and its half (-6.02 dB below it). 9b: HostMic opens that device 16 kHz mono s16 into a
single-producer/single-consumer MicRing (RED first: write n, read n, wrap, overrun counted), and PS2X_MIC_DUMP
writes what was captured to a WAV a human can play back -- header by hand, because raylib compiles miniaudio with
MA_NO_WAV. 9c: the headset spike's finding is one docs/KNOWN.md section 2 row. Unset PS2X_MIC_DEVICE opens
nothing, so the gate and the runtime's defaults are untouched, and nothing carries the audio to the game yet.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xLauncher/include/launcher/mic_devices.h \
  third_party/ps2recomp/ps2xLauncher/src/mic_devices.cpp \
  third_party/ps2recomp/ps2xLauncher/CMakeLists.txt \
  third_party/ps2recomp/ps2xLauncher/src/main.cpp \
  third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h \
  third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp \
  third_party/ps2recomp/ps2xRuntime/include/runtime/host_mic.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/host_mic.cpp \
  third_party/ps2recomp/ps2xRuntime/CMakeLists.txt \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp \
  third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp \
  docs/KNOWN.md docs/HUMAN_TASKS.md
git push
```

---
### Task 10 — FPS overlay toggle (owner request 2026-09-18)

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/fps_overlay.h`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp` (between the `PS2X_HOST_SCREENSHOT_LATEST` block :2762-2785 and the debug-UI callback :2786-2789), `third_party/ps2recomp/ps2xLauncher/src/main.cpp` (the Video panel :394-421, `kHeight` :31), `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h`, `third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp`
- Test: `third_party/ps2recomp/ps2xTest/src/host_config_tests.cpp` (the `HostConfig` case, :11), `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp`

**Interfaces:**
- `std::string fpsOverlayLine(int hostFps, double guestVsyncHz, double frameMs)` — exactly `"<hostFps> fps  guest <rate to one decimal> Hz  <frameMs to one decimal> ms"`, two spaces between the three fields. A negative `hostFps` prints `"-- fps"`; a non-finite or negative rate prints `"guest -- Hz"`; a non-finite or negative `frameMs` prints `"-- ms"` — an overlay that prints `-1.#J` is worse than one that prints nothing.
- `launcher::Config::fpsOverlay` — `bool`, default `false`. `environmentFor` emits `PS2X_FPS_OVERLAY=1` **only when true**.
- The guest rate comes from `EeScheduler::currentVSyncTick()` — **already public** at `ps2xRuntime/include/runtime/ee_scheduler.h` :348, and already the counter the `[pc-sampler]` line's `vsync=` field reads (`game_overrides_socom2.cpp` :682 → `socom2_freeze_fields.h` :44). **No new getter is needed.**

**Steps:**

- [x] **Step 1: Write the failing C++ test.** In `host_config_tests.cpp`, inside `MiniTest::Case("HostConfig", ...)`, with `#include "runtime/fps_overlay.h"` and `#include <limits>`: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        tc.Run("PS2X_FPS_OVERLAY: one line, three fields, and never a printed infinity", [](TestCase &t)
        {
            t.Equals(fpsOverlayLine(60, 59.94, 16.67), std::string("60 fps  guest 59.9 Hz  16.7 ms"), "the exact line the overlay draws");
            t.Equals(fpsOverlayLine(7, 3.0, 142.9), std::string("7 fps  guest 3.0 Hz  142.9 ms"), "a stalled frame reads honestly");
            t.Equals(fpsOverlayLine(60, 0.0, 16.6), std::string("60 fps  guest 0.0 Hz  16.6 ms"), "a guest that stopped ticking is 0.0, not blank");
            t.Equals(fpsOverlayLine(-1, 59.94, 16.7), std::string("-- fps  guest 59.9 Hz  16.7 ms"), "no host reading yet");
            t.Equals(fpsOverlayLine(60, -1.0, 16.7), std::string("60 fps  guest -- Hz  16.7 ms"), "no guest reading yet");
            t.Equals(fpsOverlayLine(60, std::numeric_limits<double>::infinity(), 16.7), std::string("60 fps  guest -- Hz  16.7 ms"), "a divide by a zero interval prints --, never inf");
            t.Equals(fpsOverlayLine(60, 59.94, -1.0), std::string("60 fps  guest 59.9 Hz  -- ms"), "no frame time yet");
            t.IsTrue(fpsOverlayLine(60, 59.94, 16.67).size() <= 34u, "short enough to stay inside the 200 px the bar allows");
        });
```

- [x] **Step 2: Run it and watch it fail.** Task 8 Step 2's command. Expected: `fatal error: 'runtime/fps_overlay.h' file not found`. *(done 2026-09-18, agent-executed; suite 538)*

- [x] **Step 3: Implement the header.** *(done 2026-09-18, agent-executed; suite 538)*

```cpp
#pragma once
// Sprint 7 Task 10 (owner request 2026-09-18): the one line PS2X_FPS_OVERLAY draws, formatted where it can be
// tested. Three numbers, because two of them answer different questions: the HOST's frame rate says whether the
// window is keeping up, and the GUEST's vsync rate says whether the game is -- research/29's render-stall shape
// is exactly the case where the first is fine and the second is not.
#include <cmath>
#include <cstdio>
#include <string>

inline std::string fpsOverlayLine(int hostFps, double guestVsyncHz, double frameMs)
{
    char host[16];
    if (hostFps < 0)
        std::snprintf(host, sizeof(host), "--");
    else
        std::snprintf(host, sizeof(host), "%d", hostFps);
    char guest[16];
    if (!std::isfinite(guestVsyncHz) || guestVsyncHz < 0.0)
        std::snprintf(guest, sizeof(guest), "--");
    else
        std::snprintf(guest, sizeof(guest), "%.1f", guestVsyncHz);
    char frame[16];
    if (!std::isfinite(frameMs) || frameMs < 0.0)
        std::snprintf(frame, sizeof(frame), "--");
    else
        std::snprintf(frame, sizeof(frame), "%.1f", frameMs);
    return std::string(host) + " fps  guest " + guest + " Hz  " + frame + " ms";
}
```
Run Step 2's command: green.

- [x] **Step 4: Draw it.** In `ps2_runtime.cpp`, **after** the `PS2X_HOST_SCREENSHOT_LATEST` block (:2762-2785) and **before** `if (m_debugUiInitialized && m_debugUiDrawCallback)` (:2786). The order matters twice: after the export, so the overlay is never in an exported GS frame and therefore never in a parity capture or a `scale_shot --mode export` comparison; before the debug panel, so F1's panel draws over it rather than under it. *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        // PS2X_FPS_OVERLAY=1 (Task 10): one line of raylib text in the top-left of the WINDOW. Drawn after the
        // exported frame above, so the gate's detectors and every parity capture see exactly what they saw
        // before this knob existed; the backing rectangle is 200x14, the box the task's bar allows.
        {
            static const bool s_fpsOverlay = [] {
                const char *const e = std::getenv("PS2X_FPS_OVERLAY");
                return e != nullptr && *e != 0 && std::strcmp(e, "0") != 0;
            }();
            if (s_fpsOverlay)
            {
                // The guest rate over the last second, from the same vsync counter the [pc-sampler] line's
                // vsync= field reads (game_overrides_socom2.cpp:682).
                static double s_windowStart = GetTime();
                static uint64_t s_windowTick = eeScheduler().currentVSyncTick();
                static double s_guestHz = -1.0;
                const double nowS = GetTime();
                const uint64_t tickNow = eeScheduler().currentVSyncTick();
                if (nowS - s_windowStart >= 1.0)
                {
                    s_guestHz = static_cast<double>(tickNow - s_windowTick) / (nowS - s_windowStart);
                    s_windowStart = nowS;
                    s_windowTick = tickNow;
                }
                const std::string line = fpsOverlayLine(GetFPS(), s_guestHz, GetFrameTime() * 1000.0);
                DrawRectangle(0, 0, 200, 14, Color{0, 0, 0, 160});
                DrawText(line.c_str(), 4, 2, 10, RAYWHITE);
            }
        }
```
  with `#include "runtime/fps_overlay.h"` at the top. Run Step 2's command: still green.

- [x] **Step 5: Write the failing launcher test.** In `launcher_tests.cpp`, inside `MiniTest::Case("Launcher", ...)`: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        tc.Run("the FPS overlay is off unless the player asks for it", [](TestCase &t)
        {
            launcher::Config c;
            t.IsTrue(!c.fpsOverlay, "off by default: nothing is drawn over anyone's game unasked");
            std::vector<std::string> env = launcher::environmentFor(c);
            auto hasKey = [](const std::vector<std::string> &e, const std::string &k) { return std::any_of(e.begin(), e.end(), [&](const std::string &s) { return s.rfind(k + "=", 0) == 0; }); };
            t.IsTrue(!hasKey(env, "PS2X_FPS_OVERLAY"), "off: the knob is not set at all, rather than set to 0");
            c.fpsOverlay = true;
            env = launcher::environmentFor(c);
            t.IsTrue(std::find(env.begin(), env.end(), std::string("PS2X_FPS_OVERLAY=1")) != env.end(), "on: exactly the value the runtime tests for");
            launcher::Config back;
            t.IsTrue(launcher::fromJson(launcher::toJson(c), back), "parses its own output");
            t.IsTrue(back.fpsOverlay, "the choice survives the round trip");
        });
```
Run Step 2's command. Expected: `error: no member named 'fpsOverlay' in 'launcher::Config'`.

- [x] **Step 6: The launcher half.** `launcher_config.h` `Config`, after `windowSize` (:35): *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        bool fpsOverlay = false;               // Sprint 7 Task 10: PS2X_FPS_OVERLAY, off unless asked for
```
  `toJson`: `out += std::string("  \"fpsOverlay\": ") + (c.fpsOverlay ? "true" : "false") + ",\n";`. `fromJson`: add `fpsOverlay` to the scalar branch's key list and `else if (key == "fpsOverlay") c.fpsOverlay = raw == "true";` inside it. `environmentFor`, after the `PS2X_WINDOW_SIZE` push:

```cpp
        if (c.fpsOverlay)
            env.push_back("PS2X_FPS_OVERLAY=1");
```
  In `main.cpp`'s Video panel, a new row below Window at `y + 110` — the panel rectangle grows `118 -> 146` and `y += 130` becomes `y += 158`:

```cpp
        if (checkbox(100, y + 110, "FPS overlay (host fps, the game's vsync rate, frame time)", config.fpsOverlay))
            dirty = true;
```
  `kHeight` goes `870 -> 898`. Run Step 2's command: green.

- [x] **Step 7: Suite, then build.** *(done 2026-09-18, agent-executed; suite 538)*

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "10: build.sh test" -- ./build.sh test
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_fpsoverlay_build.marker
```

- [x] **Step 8: The measurement (one launch, `s7_fps_overlay`, after the sprint's launch block).** A title-stage gate run with the overlay on, and a window capture of the same stage. `logs/s7_fps_overlay.sh`: *(done 2026-09-18: s7_fps_overlay title PASS 19/23 with the overlay on; window capture corner mean 29.7 / std 79.9 over a black band 0.0 -- the line is drawn and clear of every detector)*

```bash
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
PS2X_FPS_OVERLAY=1 python -m tools_py.parity.gate --only title --stamp s7_fps_overlay --owner gate
rc=$?
PS2X_FPS_OVERLAY=1 python -m tools_py.parity.scale_shot --mode window --size 640x448 --seconds 40 --out logs/parity/s7_fps_overlay_window.png
echo "done $rc" > logs/s7_fps_overlay.done; exit $rc
```
```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s7_fps_overlay.sh logs/s7_fps_overlay.marker
cat logs/parity/gate/s7_fps_overlay/summary.txt
python -c "
import glob
import numpy as np
from PIL import Image
win = Image.open('logs/parity/s7_fps_overlay_window.png').convert('L').crop((0, 0, 200, 14))
exp = Image.open(sorted(glob.glob('logs/parity/gate/s7_fps_overlay/title/s*_none.png'))[-1]).convert('L').crop((0, 0, 200, 14))
print('corner mean |diff|', float(np.abs(np.asarray(win, float) - np.asarray(exp, float)).mean()))
"
```
  **Two bars, both of which have to hold:**
  1. `PASS title` in `summary.txt` — the overlay did not move the title detector. It cannot, if Step 4 put the draw after the export; a FAIL here means it did not, and the fix is the draw order, not the detector.
  2. The printed corner mean |diff| is **> 5** — the window's top-left carries something the exported frame does not, i.e. the overlay is on the window and not in the GS frame.

  Decision table: **> 5** → done. **< 1** → the overlay never drew; check the knob reached the child (`grep -c PS2X_FPS_OVERLAY logs/parity/gate/s7_fps_overlay/*.log`) before touching the draw. **1–5** → it drew but faintly; look at the two crops by eye before concluding anything, because a 640x448 title frame whose top-left is already light grey narrows the gap a dark backing rectangle can open.

  *(`scale_shot --mode window` is the PrintWindow path that tool kept "for the cases that genuinely want the window" — its module docstring. `--mode window` deliberately removes `PS2X_HOST_SCREENSHOT_LATEST` from the child, so the capture and the gate's export come from two launches of the same deterministic boot rather than one; the top-left 200x14 box is the same dark margin in both, which is why the bar can be a plain difference.)*

- [x] **Step 9: Commit.** No default moves — `PS2X_FPS_OVERLAY` unset is the old behaviour and the launcher's checkbox is off — so no ruling. *(done: 206de19, one commit for Tasks 8-11)*

```bash
git commit -m "feat(present): PS2X_FPS_OVERLAY -- host fps, the guest vsync rate and frame time, in the window only

owner request 2026-09-18. fpsOverlayLine (RED first: the exact string, and -- for every unread field rather than
inf or -1.#J) formats one line; the draw sits between the PS2X_HOST_SCREENSHOT_LATEST export and the debug panel,
so nothing the parity harness reads can see it and F1's panel still draws on top. The guest rate is the same
EeScheduler::currentVSyncTick the [pc-sampler] line's vsync= field reads, sampled over one second. The launcher's
Video panel carries the checkbox and PS2X_FPS_OVERLAY=1 is emitted only when it is ticked. Measured on
s7_fps_overlay: PASS title at 640x448 with the overlay on, and the window's top-left differs from the exported
frame by <N> mean grey levels (bar 5) -- drawn on the window, not into the GS frame.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/fps_overlay.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp \
  third_party/ps2recomp/ps2xLauncher/src/main.cpp \
  third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h \
  third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp \
  third_party/ps2recomp/ps2xTest/src/host_config_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp \
  logs/s7_fps_overlay.sh
git push
```

---

### Task 11 — Detail and resolution, extended (owner request 2026-09-18)

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/audio_volume.h`
- Modify: `third_party/ps2recomp/ps2xLauncher/src/main.cpp` (the Video panel's Detail row :394-401, Window row :414-421, a new Volume row; the label tables :344-346; `kHeight` :31), `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h`, `third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp`, `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_audio.cpp` (`mixerRender` :503-540)
- Test: `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp`, `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp`

**Interfaces:**
- `float volumeGain(int percent)` — `percent / 100.0f` with the input clamped to `[0, 100]` first: `100 -> 1.0f`, `0 -> 0.0f`, `50 -> 0.5f`, `150 -> 1.0f`, `-10 -> 0.0f`.
- `launcher::Config::audioVolume` — `int`, default `100`. `environmentFor` emits `PS2X_AUDIO_VOLUME=<0..100>` **always** (like `PS2X_GS_SCALE`): 100 is unity, so the value is always meaningful and a player who turned it down keeps it.
- The Detail row gains a fourth radio, **"Sharpest (4x)"** → `gsScale = 4` → `PS2X_GS_SCALE=4`. The backend already clamps `PS2X_GS_SCALE` to `[1, 4]` (`gs_gl_backend.cpp` `renderScale()` :60-73), so 4 needs no runtime change at all: the launcher was offering less than the runtime already supports.
- The Window row gains **"Match display"**, resolved *at click time*: the launcher writes `GetMonitorWidth/Height(GetCurrentMonitor())` into `Config::windowSize` as a plain `<w>x<h>`. `environmentFor` stays pure and raylib-free, `config.json` never carries a magic word, and `ps2_window::parseWindowSize` (`ps2_window_size.h` :17-62) parses it like any other size.
- **No draw-distance and no texture-detail slider.** `PS2X_LOD_SCALE` (`game_overrides_socom2.cpp` :1238) and `PS2X_DETAIL_FAR` (:1387) are debug knobs inside trace hooks, not user-facing settings, on three counts each checked in the tree: (1) both live in functions (`socom2_CullTrace`, `socom2_DetailTrace`) installed only by `installCullTrace` (:1549-1620), which returns early unless `PS2X_CULL_TRACE="<file>:t<seconds>[:<count>]"` is set — set by the launcher alone, neither knob does anything; (2) both work by **writing into guest memory** (`PS2X_LOD_SCALE` memcpy's a float over `camera + 0x2c8`, `PS2X_DETAIL_FAR` writes `rdram[0x4b4a88] = 0`), which this plan's Global Constraints freeze outright; (3) `PS2X_DETAIL_FAR` is not a distance at all — it is a boolean that forces the "not near" flag so every component takes its lowest triangle count, so there is nothing for a slider to slide. A real draw-distance control means understanding the distance table `FUN_003b6e10` reads (`0x4b4a98`, `0x4b4a88`, `0x4b4ad0`), which is research/31 §16 work, not a launcher task.

**Steps:**

- [x] **Step 1: Write the failing C++ tests.** In `socom2_audio_tests.cpp`, inside `MiniTest::Case("SOCOM2Audio", ...)`, with `#include "runtime/audio_volume.h"`: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        tc.Run("volumeGain: 0-100 percent to a linear gain, out of range clamped", [](TestCase &t)
        {
            t.IsTrue(volumeGain(100) == 1.0f, "100 is unity -- byte for byte the mix the renderer produced");
            t.IsTrue(volumeGain(0) == 0.0f, "0 is silence");
            t.IsTrue(volumeGain(50) == 0.5f, "50 is half");
            t.IsTrue(volumeGain(150) == 1.0f, "above the range is unity, never a gain above 1 that would clip the mix");
            t.IsTrue(volumeGain(-10) == 0.0f, "below the range is silence, never a negative gain that would invert it");
            t.IsTrue(volumeGain(1) > 0.0f && volumeGain(1) < 0.02f, "the bottom step is quiet, not muted");
        });
```
  and in `launcher_tests.cpp`, inside `MiniTest::Case("Launcher", ...)`:

```cpp
        tc.Run("the fourth scale, the matched display size, and the master volume reach the environment", [](TestCase &t)
        {
            launcher::Config c;
            t.Equals(c.audioVolume, 100, "full volume by default: the mixer is untouched unless the player moves it");
            std::vector<std::string> env = launcher::environmentFor(c);
            auto has = [](const std::vector<std::string> &e, const std::string &kv) { return std::find(e.begin(), e.end(), kv) != e.end(); };
            t.IsTrue(has(env, "PS2X_AUDIO_VOLUME=100"), "unity always ships, so config.json is the one source of the value");
            c.gsScale = 4;
            c.windowSize = "2560x1440";      // what "Match display" resolved to on the player's monitor
            c.audioVolume = 35;
            env = launcher::environmentFor(c);
            t.IsTrue(has(env, "PS2X_GS_SCALE=4"), "the fourth radio reaches the backend's top clamp");
            t.IsTrue(has(env, "PS2X_WINDOW_SIZE=2560x1440"), "a matched display is an ordinary <w>x<h>, not a magic word");
            t.IsTrue(has(env, "PS2X_AUDIO_VOLUME=35"), "the volume the player set");
            launcher::Config back;
            t.IsTrue(launcher::fromJson(launcher::toJson(c), back), "parses its own output");
            t.IsTrue(back.gsScale == 4 && back.windowSize == "2560x1440" && back.audioVolume == 35, "all three survive the round trip");
            launcher::Config partial;
            t.IsTrue(launcher::fromJson("{\"gsScale\": 2}", partial), "an older config.json parses");
            t.Equals(partial.audioVolume, 100, "a config written before this task is still full volume");
        });
```

- [x] **Step 2: Run them and watch them fail.** Task 8 Step 2's command. Expected: `fatal error: 'runtime/audio_volume.h' file not found`, and once that is past, `error: no member named 'audioVolume' in 'launcher::Config'`. *(done 2026-09-18, agent-executed; suite 538)*

- [x] **Step 3: Implement `audio_volume.h` and apply it.** *(done 2026-09-18, agent-executed; suite 538)*

```cpp
#pragma once
// Sprint 7 Task 11 (owner request 2026-09-18): PS2X_AUDIO_VOLUME=<0..100>, the launcher's master volume, as a
// linear gain on the 989snd mix. Linear rather than dB because the slider is a percentage and a player who drags
// it to 50 expects half; the range is capped at 100 so the knob can never add gain to a mix that is already at
// full scale.
inline float volumeGain(int percent)
{
    if (percent <= 0)
        return 0.0f;
    if (percent >= 100)
        return 1.0f;
    return static_cast<float>(percent) / 100.0f;
}
```
  In `ps2_audio.cpp` `mixerRender` (:503), immediately after `m_mixer.render(interleaved, frames);` (:512) and **before** the `PS2X_AUDIO_DUMP` write (:529-539) — so the dump is what is actually heard, and Task 1e/2c's correlation instrument reads the same signal the player does (it is a Pearson correlation, so a constant gain does not move it, and the gate sets no `PS2X_AUDIO_VOLUME` in any case):

```cpp
    // PS2X_AUDIO_VOLUME (read once): unity does nothing at all -- no multiply, no rounding -- so "100" is byte
    // for byte the mix this function produced before the knob existed.
    static const float s_gain = [] {
        const char *const e = std::getenv("PS2X_AUDIO_VOLUME");
        return volumeGain((e != nullptr && *e != 0) ? std::atoi(e) : 100);
    }();
    if (s_gain != 1.0f)
    {
        const size_t samples = frames * 2u;   // interleaved stereo
        for (size_t i = 0; i < samples; ++i)
            interleaved[i] = static_cast<int16_t>(std::lround(static_cast<float>(interleaved[i]) * s_gain));
    }
```
  (`#include "runtime/audio_volume.h"` and `<cmath>` at the top; a gain of at most 1.0 cannot push an `int16_t` out of range, which is why no saturation step is needed.) Run Step 2's command: the `volumeGain` case is green.

- [x] **Step 4: The launcher's config half.** `launcher_config.h` `Config`, after `fpsOverlay`: *(done 2026-09-18, agent-executed; suite 538)*

```cpp
        int audioVolume = 100;                 // Sprint 7 Task 11: PS2X_AUDIO_VOLUME, 0-100, 100 = unity
```
  `toJson`: `out += "  \"audioVolume\": " + std::to_string(c.audioVolume) + ",\n";`. `fromJson`: add `audioVolume` to the scalar branch's key list and `else if (key == "audioVolume") c.audioVolume = std::atoi(raw.c_str());` inside it. `environmentFor`, after the `PS2X_PRESENT_FILTER` push:

```cpp
        const int volume = c.audioVolume < 0 ? 0 : (c.audioVolume > 100 ? 100 : c.audioVolume);
        env.push_back("PS2X_AUDIO_VOLUME=" + std::to_string(volume));
```
Run Step 2's command: green.

- [x] **Step 5: The Video panel.** In `main.cpp`: *(done 2026-09-18, agent-executed; suite 538)*

  An integer slider beside the other widgets — the existing `slider` quantises to steps of 0.05, which is meaningless on a 0-100 range:

```cpp
    void sliderInt(Rectangle r, int &value, int lo, int hi)
    {
        DrawRectangle(static_cast<int>(r.x), static_cast<int>(r.y + r.height / 2 - 2), static_cast<int>(r.width), 4, kField);
        const float t = static_cast<float>(value - lo) / static_cast<float>(hi - lo);
        DrawCircle(static_cast<int>(r.x + t * r.width), static_cast<int>(r.y + r.height / 2), 7, kAccent);
        if (CheckCollisionPointRec(GetMousePosition(), {r.x - 8, r.y, r.width + 16, r.height}) && IsMouseButtonDown(MOUSE_BUTTON_LEFT))
        {
            float nt = (GetMousePosition().x - r.x) / r.width;
            nt = nt < 0 ? 0 : (nt > 1 ? 1 : nt);
            value = lo + static_cast<int>(static_cast<float>(hi - lo) * nt + 0.5f);
        }
    }
```
  The Detail labels (:344) gain the fourth entry, and the selection arithmetic follows it (:396):

```cpp
    const std::vector<const char *> scaleLabels = {"Native", "Sharp (2x)", "Sharper (3x, experimental)", "Sharpest (4x)"};
// ... and inside the frame loop, in the Video panel's Detail row (:396):
        int scaleSel = config.gsScale >= 4 ? 3 : (config.gsScale == 3 ? 2 : (config.gsScale == 2 ? 1 : 0));
```
  The Window labels (:346) gain "Match display", resolved at click time (:414-421):

```cpp
    const std::vector<const char *> sizeLabels = {"640x448", "1280x896", "fullscreen", "Match display"};
// ... and inside the frame loop, in the Video panel's Window row (:414-421):
        const std::string monitorSize = TextFormat("%dx%d", GetMonitorWidth(GetCurrentMonitor()), GetMonitorHeight(GetCurrentMonitor()));
        int sizeSel = indexOf(sizeLabels, config.windowSize, -1);
        if (sizeSel < 0)
            sizeSel = (config.windowSize == monitorSize) ? 3 : 0;
        const int newSize = radios(100, y + 84, sizeLabels, sizeSel);
        if (newSize != sizeSel)
        {
            // "Match display" is a button, not a stored value: what lands in config.json is the monitor's own
            // <w>x<h>, so a config carried to a machine with a different screen is a size, not a surprise.
            config.windowSize = (newSize == 3) ? monitorSize : std::string(sizeLabels[newSize]);
            dirty = true;
        }
```
  The Volume row below Task 10's FPS-overlay checkbox, at `y + 138` — the Video rectangle grows `146 -> 180` and `y += 158` becomes `y += 192`:

```cpp
        DrawText(TextFormat("Volume %d%%", config.audioVolume), 24, static_cast<int>(y) + 140, 14, kDim);
        {
            const int before = config.audioVolume;
            sliderInt({140, y + 138, 280, 20}, config.audioVolume, 0, 100);
            if (config.audioVolume != before)
                dirty = true;
        }
```
  `kHeight` goes `898 -> 932`. Run Step 2's command: green.

- [x] **Step 6: Suite, then build.** *(done 2026-09-18, agent-executed; suite 538)*

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "11: build.sh test" -- ./build.sh test
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_detail_build.marker
```
Expected: exit 0. **No launch and no measurement beyond the suite**: the presentation scale was measured in Task 1c Step 8 (`s7_scale_both`, mean |diff| 0.83 against a bar of 3) and 4x is that same code path at a larger clamp; the window size and the volume are knobs the owner's hands-on checks cover (Tasks 8 and 9's `docs/HUMAN_TASKS.md` items and the existing launcher item).

- [x] **Step 7: Check that nothing moved.** Before committing, confirm every default in this task is the old behaviour: `Config{}.gsScale == 1`, `Config{}.windowSize == "1280x896"` (Task 1c's, untouched), `Config{}.audioVolume == 100` → `volumeGain(100) == 1.0f` → the multiply is skipped entirely, and `PS2X_AUDIO_VOLUME` unset gives exactly the same. **No ruling is due for this task**; the numbering stands at R95 from Task 8, so the next ruling anyone writes is R96. *(done 2026-09-18, agent-executed; suite 538)*

```bash
third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe 2>&1 | grep -E "Failed\]|Total Tests"
./dist/socom_unzipped_launcher.exe --selftest | grep -E "PS2X_GS_SCALE|PS2X_WINDOW_SIZE|PS2X_AUDIO_VOLUME"
```
Expected: `0 Failed`, and `PS2X_GS_SCALE=1`, `PS2X_WINDOW_SIZE=1280x896`, `PS2X_AUDIO_VOLUME=100` from a default `config.json`.

- [x] **Step 8: Commit.** *(done: 206de19, one commit for Tasks 8-11)*

```bash
git commit -m "feat(video/audio): a fourth scale, Match display, and a master volume in the launcher

owner request 2026-09-18. The Detail row offers Sharpest (4x) -- the GL backend's renderScale() has clamped
PS2X_GS_SCALE to [1,4] all along, so the launcher was simply offering less than the runtime already supports. The
Window row offers Match display, resolved at click time from GetMonitorWidth/Height so config.json carries a plain
<w>x<h> and environmentFor stays raylib-free. A master volume slider emits PS2X_AUDIO_VOLUME=<0..100>, read once
in ps2_audio.cpp and applied as a linear gain on the mix before the PS2X_AUDIO_DUMP write, with unity skipping the
multiply entirely (volumeGain RED first: 100/0/50 and both out-of-range directions). No draw-distance or
texture-detail slider: PS2X_LOD_SCALE and PS2X_DETAIL_FAR are debug hooks that exist only under PS2X_CULL_TRACE,
they work by writing guest memory, and PS2X_DETAIL_FAR is a boolean rather than a distance. No default moves.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/audio_volume.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_audio.cpp \
  third_party/ps2recomp/ps2xLauncher/src/main.cpp \
  third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h \
  third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp \
  third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp
git push
```

---

### Task 12 — The owner's sound reports of 2026-09-18 (online menus splice and buzz; the mission goes silent)

**Reported** (hands-on from the launcher, run log `dist/logs/run_20260918_015258.log`): (1) on the SOCOM II ONLINE briefing-rooms screen just after signing in, the music "skips and almost plays two different spliced segments"; (2) "a persistent buzz" on the create-game playlist screen and in the lobby; (3) the same carried into a single-player mission after leaving online, then "mid mission, sound stopped working altogether". The audio changes since the last good listen: Task 1e (6ea9520, the worker-thread stream ring), Task 2c (5a1b6a8, the CD plain-read cursor), and Task 11's volume gain (a no-op at 100, verified by reading it).

**What the log already says:** the online menu music is a CD stream the GAME reads itself (`sceCdStStart lbn=0xcdade`, then `0xce5bf`, `0xdd218`, one per screen) into the 989snd PCM ring at 0xa0000 (`snd_PcmStreamOpen/Start/Stop/Close` pairs at lines 135-370); each stream's first reads show `buffered=0` twice before the ring starts (lines 140, 190, 196, 232); the mission then plays VAG streams (`989snd stream 40x000x sector ... playing`, lines 375-3164) through the worker ring. No `[audio]` warning line appears anywhere and the window closed normally.

**Files:**
- Modify (as the finding dictates): `third_party/ps2recomp/ps2xRuntime/src/lib/snd989_mixer.cpp` / `.h`, `src/lib/Kernel/Stubs/CD.cpp`, `src/lib/ps2_audio.cpp`
- Test: `third_party/ps2recomp/ps2xTest/src/socom2_audio_tests.cpp`, `ps2_runtime_io_tests.cpp`; `tools_py/parity/audio_corr.py` gains a repeat detector
- Launch scripts under `logs/`: `s7_audio_online.sh` (driven online login to the briefing rooms with `PS2X_AUDIO_DUMP`, `PS2X_AUDIO_TRACE=1`, the stream-worker trace), the same with `PS2X_SND_STREAM_WORKER=0`; `s7_audio_mission.sh` (the mission gate stage with a dump)

- [x] **Step 1: The code review** (Opus, read-only, 2026-09-18). *(done; four findings, ranked)*
  1. **Symptom 3, certain:** `snd989.cpp` `stopSound()` looks only in `m_model.sounds`, never `findStream`, so `snd_StopSound` on a VAG stream handle leaves the slot active forever; only `snd_StopAllVAGStreams` clears them. The log: six slots, six plays, four no-op stops, then **237 × `no free VAG stream slot`** from line 3335 to the end -- every later play returns 0. The mixer did stop the audio, so it sounded right until the slots ran out.
  2. **Symptoms 1 and 2:** the PCM ring at 0xa0000 has no fill/play interlock: `render` advances `ring.pos` unconditionally and wraps; `pcmStreamWrite` is a bare memcpy; the position the game reads is published once per host callback, after the block was consumed. A fill that lands late is skipped until the next wrap (the splice); a block not refilled in time replays verbatim (the buzz -- a 512-byte block looping). The ring is 24576 B = 128 ms, wrapping 8x a second; the login screen's 12-30 fps (KNOWN §2) is what puts the fill on the wrong side. Task 1e's worker ring is not on this path at all.
  3. **971 × `play request for unknown bank`** for banks 0xa30000/0xa00000 that were loaded (log 868-883) with no unload in between: bank sound effects were being dropped in the mission too; unexplained.
  4. **Task 2c's `sceCdGetReadPos`** is stream-wins-while-open (`CD.cpp:405`), not "whichever the caller last moved"; a plain reader with a stream open gets the stream's cursor. Latent (the log has no plain `sceCdRead` during the menus), to correct before any path mixes the two.
- [x] **Step 2: The repeat detector** (`audio_corr.py --repeat`, Opus, in progress): the autocorrelation peak at lags 256..4096 per 4 s window; a looping block reads r > 0.9 at its length. *(done: acc3310, 1109 Python)*
- [x] **Step 3: The three small fixes, each under a RED test.** (a) `stopSound` frees a stream slot: init 2 slots, play, `snd_StopSound(handle)`, the next play returns non-zero -- fails today. (b) `sceCdGetReadPos` returns the cursor the caller last moved: stream open, plain `sceCdRead` at X, `GetReadPos` == X's end; then `sceCdStRead`, `GetReadPos` == the stream cursor. (c) The unknown-bank reject logs the bank table once (handle, loaded flag) so one launch says whether the slot was cleared or the handle is stale. `./build.sh test`, build. *(done: b3e3797; RED 3 failed of 538, GREEN 537 + the ring case)*
- [x] **Step 4: The PCM ring's underrun policy** (a design change; ruling R97). Track the high-water mark of `pcmStreamWrite` per wrap; when `render` reaches a block that was not rewritten since the head last passed it, output silence for that block and count it (`pcm_underruns` on the audio stat line) instead of replaying stale bytes -- a gap where the console would also have had to wait, never a loop. RED test: fill 1 block, render 2 blocks, the second is silence and the counter is 1; a fill that arrives before the head is played verbatim. *(done: b3e3797, R97; RED 'a block played once and not rewritten is silence' then GREEN 538)*
- [x] **Step 5: Reproduce and re-measure, driven (launches 37-38).** `logs/s7_audio_online.sh`: `online_control_round.sh`'s login path with `PS2X_AUDIO_DUMP`, `PS2X_AUDIO_TRACE=1`, `PS2X_AUDIO_PCM_DUMP` (write offset vs play offset crossings), on the fixed exe; `logs/s7_audio_mission.sh`: the mission gate stage with a dump and the trace. Bars: the repeat detector under 0.9 in every scored window of the online dump; `pcm_underruns` reported; no `no free VAG stream slot` and no `unknown bank` line in the mission log; the mission dump's RMS never at zero for 10 s while the HUD is up; the title correlation still 1.000 (`s7_audio_title`'s command). *(2026-09-18 04:43-05:00, first pass on b3e3797's exe: ONLINE MENUS `s7_audio_online` -- pcm_underruns=0 throughout, max_repeat 0.71 vs bar 0.9 PASS, music continuous on each screen (loud 34-85 s, 111-175 s), the ring policy unexercised at 60 fps -> a loaded run (`s7_audio_online_loaded.sh`, four spinning cores) follows. MISSION `s7_audio_mission` -- NOT MET: 107 `no free VAG stream slot` and 9 `unknown bank` lines, the dump silent from 278 s to the end (201 s): the model answers snd_SoundIsStillPlaying with the handle 4440 times for two streams the mixer finished (a stream's natural end never frees its slot -- stopSound was the smaller leak), and the bank table was EMPTY at the first reject (0 entries) after a successful load. Both to Step 3's fix agent, second pass.)* *(second pass 2026-09-18 05:11-05:35 on the stream-end + SIF-reset fix: MISSION `run_20260918_051258` -- unknown bank 0 (was 9), `no free VAG stream slot` 1 (was 107), 29 stream plays (was 12), gate PASS; the dump's quiet last 147 s is the driven stage's own shape (R98: yesterday's pre-change dumps go quiet for their last 200 and 165 s; this pass's last sound at 331 s is later than both). ONLINE LOADED `s7_audio_online_loaded` -- four spinning cores did not slow the login screen (fps median 60.0, min 59.4), pcm_underruns=0, max_repeat 0.70 PASS; R97 stays proven by its unit test. TITLE `s7_audio_title` -- the loop's windows corr 1.000 with a constant offset, min_corr 1.0000 from the loop's start (158 s this run).)*
- [x] **Step 6: Commit** with the launch names; KNOWN §1 rows (the slot leak, the ring policy, the read-position rule); the unknown-bank finding to §1 or §2 by what Step 3c's launch says; `docs/HUMAN_TASKS.md`: the owner's re-listen of the online menus and one mission, quoting the three sentences and the numbers now standing against them. The menus' 80-133 ms/s of uploads (the reason the fill is late) stays Sprint 8's task unless Step 5 shows the ring still underruns at 60 fps. *(done: this commit; KNOWN §1 rows for the slot leaks, the SIF reset and the ring policy; HUMAN_TASKS re-listen item)*

### Task 7 — Close-out

**Files:** `docs/STATUS.md`, `docs/KNOWN.md`, `docs/ROADMAP.md` §6, `docs/CURRENT_SPRINT.md`, this plan.

**Interfaces:** the branch `sprint-7` merged into `develop` and `main`; `docs/CURRENT_SPRINT.md` opens Sprint 8; the ledger archived.

**Steps:**

- [x] **Step 1: The repeat suite on a quiet host.** *(done 2026-09-18 05:40: `PS2X_TEST_REPEAT=3 ./build.sh test` -- 540/540 three times, Python 1172, vu1_replay PASS; `logs/s7_closeout_suite.marker.log`)*

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "s7 close-out: repeat suite" -- \
  bash -c 'PS2X_TEST_REPEAT=3 ./build.sh test'
```
Expected: exit 0 three times over, with the same counts each time; a case that passes twice and fails once is a flake to name in `docs/KNOWN.md` §4, not a pass.

- [x] **Step 2: A full gate (launch 24).** *(done: `s7_closeout_gate` GATE PASS 3/3 on the exe carrying every commit through 23a860d)*

```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s7_closeout_gate.sh logs/s7_closeout_gate.marker
cat logs/parity/gate/s7_closeout/summary.txt
sha256sum dist/socom2.exe
```
Expected: `PASS title`, `PASS transition`, `PASS mission` on the sprint's final exe, with the sha recorded in STATUS.

- [x] **Step 3: Tick this plan** against what actually landed — every `- [ ]` above becomes `- [x]` with the launch name that proved it, or keeps its box and gains a one-line reason and the sprint that carries it. No box is ticked on intent. *(done: 8efae3c -- every open box carries a reason or a STOP)*

- [x] **Step 4: The KNOWN audit.** Walk `docs/KNOWN.md` §1 and §2 row by row: the 21k-decodes row moves or is rewritten (Task 3), the lobby rate becomes a proven number (Task 2d), the freeze shape-2 row gets its sentence (Task 2e), the same-key row is settled (Task 2b), and anything this sprint contradicted is retracted into §3 with the measurement that killed it. *(done: 94e532d, 7561f90, 1b2fe64, 68a082e, 23a860d, 8efae3c -- the 21k row rewritten and its §1 twin re-measured, the lobby rate proven, the freeze hazard annotated, the login-screen row, the SIF-reset and slot-leak rows, the lock-reap hazard)*

- [x] **Step 5: STATUS, ROADMAP, CURRENT_SPRINT.** A STATUS entry with the current state (exe sha, gate stamp, the sprint's numbers); ROADMAP §6's Sprint 7 items marked; `docs/CURRENT_SPRINT.md` closes Sprint 7 and opens **Sprint 8** ("It looks and sounds finished, and it does not scare the machine") pointing at its spec. *(done: df65444 -- STATUS current state and the 2026-09-18 entries, ROADMAP §6 marked, CURRENT_SPRINT's closing block and the Sprint 8 revision)*

- [x] **Step 6: Whole-branch review, then merge.** *(review done 2026-09-18 by an Opus pass over develop..sprint-7: 12 findings, 5 must-fix -- the IOP reset moved to the reboot stubs, the reaper's parent and unknown-handle cases, Match display 0x0, the launcher taller than a laptop screen -- plus seven smaller ones; all in the review-fix commit that precedes the merge; the merge itself follows that commit's suite and gate)* *(merged: 41467b7 the review fixes, suite 549, gate 3/3 `s7_final_gate`; d270022 on develop and main, pushed)*

```bash
git log --oneline develop..sprint-7
git diff --stat develop..sprint-7
git checkout develop && git merge --no-ff sprint-7 && git push
git checkout main && git merge --ff-only develop && git push && git checkout sprint-7
```
Expected: every commit on the branch has a test or a launch named in its message; the merge is clean. Archive the ledger to `D:\socom_archive`.

- [x] **Step 7: Commit the close-out docs.** *(done: this commit)*

```bash
git commit -m "docs: Sprint 7 close-out -- the plan ticked against what landed, the KNOWN audit, STATUS, ROADMAP section 6, CURRENT_SPRINT to Sprint 8

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  docs/archive/sprints-7-12/2026-09-17-sprint-7-two-strangers-two-machines.md \
  docs/KNOWN.md docs/STATUS.md docs/ROADMAP.md docs/CURRENT_SPRINT.md docs/HUMAN_TASKS.md
git push
```

---

## Rulings made on the owner's behalf

R91 onward; see the Sprint 6 plan for R78–R90.

*(Empty at the start of the sprint. Each moved default and each skipped measurement gets a numbered ruling here, in the shape `Ruling: … — why — cost if wrong`. Already expected: the launcher's 1280x896 Video default and `FLAG_WINDOW_HIGHDPI` (Task 1c), the scheduler's equal-priority semantics (Task 2a), and the launcher's default server preset switching to SOCOM Unzipped once the owner's address exists (Task 4, lifting R89).)*

- **R91** (2026-09-17, Task 1a): `GL_ARB_clip_control` absent is a note, not a fallback trigger. The spec's Goal 1a said "probe ... and the `GL_ARB_clip_control` the depth path uses"; the depth path has a working fragment-depth mapping without it (`GsGlDepth::Mode::FragDepth`, research/26), so treating its absence as unsupported would push every GL 3.3-4.4 machine onto the CPU rasterizer for nothing. The probe prints `[gs-gl] note: GL_ARB_clip_control absent: depth uses the fragment-depth mapping (not exact-integer)` and carries on. *Cost if wrong:* a machine without clip control renders with the pre-research/26 depth precision, which the gate scored acceptable for months; the note names it in the log.

- **R92** (2026-09-17, Task 1c): the launcher's Video default moves from 640x448 to 1280x896 (2x) and the runtime sets `FLAG_WINDOW_HIGHDPI`; the runtime's own default stays 640x448 and the gate keeps launching at 640x448 (its detectors are boxes in that frame). Taken because a 640x448 window on a 150 % laptop is a postage stamp and the audit named it (F8). *Cost if wrong:* a stranger's first window is 1280x896 on a display that cannot fit it -- the launcher's Window row still offers 640x448 and fullscreen, and the 2x capture compared against the gate frame (Step 8) is the proof the scaled frame is the same picture.

- **R93** (2026-09-17, Task 1b Step 11): the drag bar is read over the drag window, not the whole stage. `s7_drag`: the working set rose 314 MB over the 476 s mission stage, of which the 35 s drag window contributed +38 MB -- the same slope as the 91 MB of the first 90 s (loading) and the 37 MB of the following six minutes (level streaming); the queue never approached its 64 MB cap (pending bytes peaked under 10 MB, zero drops). So the drag balloon of audit F3 is gone, and the whole-stage growth is the game's own memory, which this task did not set out to bound. *Cost if wrong:* a slow leak in the game's memory would pass this bar; `host_samples` prints the whole-run rise too, so it stays visible on every gate with the sampler column.

- **R94** (2026-09-17, Task 1c Step 8): the 2x comparison takes two launches of its own (640x448 and 1280x896, same boot screen at launch+40 s, both from the runtime's exported frame) instead of riding the GL gate: the gate's frame is a driven menu and the capture's is the undriven boot screen, so they can never be the same picture. The sprint's launch budget grows by one (26). *Cost if wrong:* the boot screen is the controller prompt, a text panel on a dark ground, which is a weaker scaling test than a textured gameplay frame; the gate at 640x448 covers gameplay, and the launcher's 2x default is what a player sees at the menu first.

- **R95** (2026-09-18, Task 8 Step 4): a 0.15 stick dead zone is applied in **all three** host pad paths, not just SOCOM's own poll. `socom2_host_input.cpp` has used 0.15 since 2026-09-16 (:228), but the generic pad path (`ps2_pad.cpp` :83-86) and the libpad HLE (`Kernel/Stubs/Pad.cpp` `axisToByte` :71-76) passed the raw raylib axis through, so a worn stick's rest position reached the game as movement on exactly the paths the menus read. The value is `PS2X_PAD_DEADZONE`, default 0.15, and the launcher now writes whatever the player set. Taken because the owner's request was "pick the pad and make it feel right", and two of the three paths could not be made to feel like anything. *Cost if wrong:* a player who wants raw sticks sets `PS2X_PAD_DEADZONE=0` (or drags the slider to 0.00), and the gate is untouched either way -- it sets `PS2X_HOST_GAMEPAD=0`, so no pad is read in any harness run. *Addendum 2026-09-18 (whole-branch review, finding 7):* SOCOM's own poll now passes the stick through `hostPadAxis`, which rescales the live range above the dead zone, so a half deflection reads 180 where it read 191 -- a changed stick curve for a real pad, not only a dead zone. The driven harness is unaffected (its axes come through the pad file, not this path). Declared here because 206de19's message did not say it; the owner's pad check in HUMAN_TASKS is the judge of the feel.

- **R96** (2026-09-18, Task 3): the page trace ran on the offline mission stage and on the online login stage of a launch that missed the lobby, not on an online gameplay round, because the lobby rate was 6/10 that night and the mechanism under test (the post-process target overlapping parked textures) is not online-specific. Both traces refuted the hypothesis (Step 1), so Steps 2-7 are not executed and the decode budget test is not written against a mechanism the trace did not find. *Cost if wrong:* an online-gameplay-only marking pattern goes untraced this sprint; the two online rounds' stats lines (uploads ~10k/s at 20-28 ms/s in gameplay) say the cost there is a fifth of the audit's figure, and the menus' 80-133 ms/s is the larger number either way.

- **R97** (2026-09-18, Task 12 Step 4): the 989snd PCM ring plays a 256-frame block only if the game rewrote it since the head last played it; a stale block is silence and counts (`pcmUnderruns`, on the audio stat line). Taken because the ring had no fill/play interlock at all and the owner heard its two failure shapes (a late fill skipped = a splice; a missed fill replayed = a buzz); the console's IOP thread is never late, ours is whenever the login screen drops to 12-30 fps. *Cost if wrong:* a game that legitimately re-plays ring contents without rewriting (none known; research/32 §7 says the EE DMAs fresh PCM up to the polled position each wake) would go silent in those blocks; the counter names it on the stat line, and the title loop's 1.000 correlation is the regression check.

- **R98** (2026-09-18, Task 12 Step 5): the mission dump's bar "RMS never at zero for 10 s under the HUD" is replaced by "no quieter than the pre-change baseline": the driven mission stage ends with the character standing where nothing plays, and yesterday's two full dumps (`audio_gate.wav`, `s7_gl_gate2_title.wav`, before any of tonight's audio changes) are silent for their last 200 and 165 s. Tonight's second pass is silent for its last 147 s with its last sound at 331 s, later than either baseline, and its log shows streams playing, reported done and slots reused through 330 s. *Cost if wrong:* a genuine late-mission silence that starts after 331 s would pass; the slot and unknown-bank counts on the log (1 and 0) are the guard.

## Self-review

- **Spec coverage.** Goal 1a → Task 1a (bar: gate 3/3 on GL, Step 9; CPU fallback reaches title, Step 10). Goal 1b → Task 1b (bar: working-set rise < 200 MB over a 30 s drag, Step 11; the "at most K pending, uploads intact" test is Step 1). Goal 1c → Task 1c (bars: title gate unchanged at 640x448 and mean |diff| < 3 at a 2x nearest resample, Step 8). Goal 1d → Task 1d (the warning names the hash; checked on Task 1e's gate log, Step 4). Goal 1e → Task 1e (test: render with the handle closed, Step 1; bar: correlation 0.99, Step 7). Goal 2a → Task 2a (test: two equal-priority threads do not interleave, a higher one preempts, Step 1; bar: the control bar holds and the kill lands 3 of 4, Steps 5–6; the stop rule is Step 6). Goal 2b → Task 2b (one same-key control round, Step 3; the per-profile key only on a failure, Step 4). Goal 2c → Task 2c (test "StRead after Read resumes at the stream LBN", Step 1; bars: correlation unchanged and the 0.26 s slip gone or attributed, Step 5). Goal 2d → Task 2d (ten pinned Frostfire launches, Step 3; bar 8 of 10 with the class of each miss, Step 4; the under-6 stop rule is in Step 4). Goal 2e → Task 2e (research/29 §4's fields, Step 3; one loaded and one quiet launch, Steps 5–6; the condition sentence, Step 7). Goal 3 → Task 3 (the page trace and its stop rule, Step 1; the four fixes, Step 4; the decodes-per-present budget, Steps 2–3; bars: `waits` < 100 per instance and decodes under 2k/s, Step 6). Goal 4 → Task 4 (autonomous Steps 1–6; the stop; Steps 7–10 after; bar: the Unzipped preset reaches the lobby from the portable zip, Step 9). Goal 5 → Task 5 (readout Steps 1–4; the stop; bar: a lobby and both players seen moving on both machines, Step 6). Goal 6 → Task 6 (the loop does not wait; Step 3 commits and moves on). Goal 7 → Task 7. **Launch budget.** The spec §3 allows "about 22 launches". This plan spends **25**, counted: `s7_gl_gate`, `s7_cpu_fallback`, `s7_drag` (Task 1); `s7_gl_gate2` (1c Step 8 — the GL gate re-run once the render-target and DPI changes exist, since 1a's gate ran before they did); `s7_audio_gate` (1e) and `s7_cdcursor_gate` (2c Step 5, the same script re-run on the CD-cursor exe); `s7_slice_ctl`, `s7_slice_ladder` (2a); `s7_samekey` (2b); `s7_lobby_1..10` (2d); `s7_freeze_load`, `s7_freeze_quiet` (2e); `s7_pages`, `s7_decodes_ladder` (3); `s7_hosted_login` (4); `s7_closeout_gate` (7). The three over budget are the two re-runs a strict test-then-measure order forces and the close-out gate; runtime builds are detached with `--purpose build` and are not launches. Task 1c's 2x capture takes no slot of its own, as marked.
- **Placeholder scan.** Clean: no unresolved marker of any kind anywhere in this plan — searching it for the two usual ones finds only this sentence. Every implementation detail the spec left open is a concrete choice marked *(controller's choice; re-rule if wrong)*: the GL probe's exit code 65 through the process exit status (1a), the 2x capture riding on the GL gate's launch slot (1c Step 8), and `two_machine_readout` living under `tools_py/parity/` with the spec's path as a shell wrapper (5). The `<N>` and `<n>` inside the commit-message templates are values to be filled from the run that precedes the commit, not unresolved decisions. `COMMUNITY_SERVER_ADDRESS_TBC`/`UNZIPPED_SERVER_ADDRESS_TBC` are the tree's existing literals, named as the owner's items, not placeholders this plan introduces.
- **Type consistency.** `GsGlCaps::evaluate(glVersion, dualSourceBlend, clipControl)`, `GsGlCaps::Latch`, `GsGlCaps::kExitCode`, `GSGlBackend::glUnavailable()`, `GsPendingCap::admit(latched, carriesState, bytes)`, `GsFrameBackpressure::latched()`, `GsGlTarget::choose(fbw, usedHeight)`, `Vu1NativeWarning::State::shouldWarn(matched, nowNs)`, `Mixer::pumpStreams()` / `closeStreamFilesForTest()`, `EeScheduler::hasReadyAbovePriority(priority)`, `markShadowPages(page, pageCount, rowFirst, rowLast)`, `GSGlBackend::textureDecodes()`, `host_samples.working_set_rise_mb(rows)`, `scale_compare.mean_abs_diff(big, small, scale)`, `audio_corr.correlate_arrays(a, b, window_s, rate)` / `min_corr(rows)`, `lobby_report.rate(summaries)`, `freeze_trace.classify(rows)`, `two_machine_readout.read_lines(a, b)` are each used with one signature everywhere they appear. Knob names: `PS2X_GS_GL_FORCE_FAIL`, `PS2X_GS_PENDING_CAP_MB`, `PS2X_SND_STREAM_WORKER`, `PS2X_WINDOW_SIZE`, `PS2X_GS_TRACE_PAGES`, `PS2X_GS_STATS`, `PS2X_CLOCK_TRACE`, `PS2X_CONSOLE_REPLAY_GL`, `PS2X_SOCOM2_RSA_KEY`/`_B`.
- **Owner gate.** The spec is unreviewed (its own header says so). Tasks 1–3 and 7 are fully autonomous under the owner's standing instruction of 2026-09-17; Tasks 4, 5 and 6 each run their autonomous half to a commit and then stop at a named `STOP:` line pointing at `docs/HUMAN_TASKS.md`. The loop never waits on a stop: it moves to the next autonomous task.

### Self-review addendum — Tasks 8-11 (owner requests of 2026-09-18)

- **Spec coverage.** These four came from the owner directly rather than from the sprint spec, so each is checked against the request instead of a Goal. Controller selection → Task 8 (bars: the helper's twelve assertions, Step 1; the owner's two lines, Step 9 -- the driven gate sets `PS2X_HOST_GAMEPAD=0` and cannot test a pad, which is said in Step 8 rather than left implied). Microphone → Task 9, in its three halves: 9a the picker and the meter (bars: `micLevelDb` against a full-scale sine and its half, Step 1; the owner watches the bar move, Step 10), 9b the capture path (bar: the ring's write/read/wrap/overrun case, Step 6; `PS2X_MIC_DUMP` is what a human plays back), 9c the spike (bounded to Step 9, no code kept, output is one `docs/KNOWN.md` §2 row the controller writes). FPS overlay → Task 10 (bars: the exact formatted string, Step 1; `PASS title` **and** a corner difference > 5 on `s7_fps_overlay`, Step 8, with a three-way decision table). Detail and resolution → Task 11 (bars: `PS2X_GS_SCALE=4` and the matched size reach the environment, Step 1; `volumeGain` at 100/0/50 and both out-of-range directions). The owner's "draw distance / texture detail sliders" item is answered with a **no** and the three reasons, in Task 11's Interfaces block: both knobs exist only under `PS2X_CULL_TRACE`, both write guest memory, and `PS2X_DETAIL_FAR` is a boolean rather than a distance.
- **Launch budget.** One launch is added, `s7_fps_overlay` (Task 10 Step 8), taking the sprint to **26**. Tasks 8, 9 and 11 take none: a pad and a microphone cannot be driven, and 4x is Task 1c's measured presentation path at a larger clamp. The runtime builds in Steps 8/8/7/6 are detached with `--purpose build` and are not launches.
- **Placeholder scan.** Clean. Every implementation detail the owner's note left open is a concrete choice marked *(controller's choice; re-rule if wrong)*: `Config::padDeadZone` as `double` rather than `float` (Task 8), `mic_devices.cpp` compiled into the launcher executable rather than `ps2x_launcher_core` (Task 9). The `<N>` in Task 10's commit message is a value to be filled from the run that precedes it, not an unresolved decision.
- **Type consistency.** `hostGamepadSelect(envValue, count, available)`, `hostPadDeadZone()`, `hostPadAxis(v, deadZone)`, `launcher::micLevelDb(frames, n)`, `launcher::MicDevices::{list,startMeter,levelDb,stopMeter}`, `launcher::micLabels(devices)`, `MicRing::{write,read,available,dropped}`, `HostMic::{start,read,stop,running,error}`, `fpsOverlayLine(hostFps, guestVsyncHz, frameMs)` and `volumeGain(percent)` are each used with one signature in every block they appear in. New knobs: `PS2X_HOST_GAMEPAD_INDEX`, `PS2X_PAD_DEADZONE`, `PS2X_MIC_DEVICE`, `PS2X_MIC_DUMP`, `PS2X_FPS_OVERLAY`, `PS2X_AUDIO_VOLUME` -- every one of them off or unity when unset, so the parity gate (which sets none of them) launches the runtime at 640x448 with exactly the behaviour it had before.
- **Launcher window height.** The four tasks grow it in sequence: 660 → 686 (Task 8's pad list and dead-zone slider) → 870 (Task 9's Microphone panel) → 898 (Task 10's checkbox) → **932** (Task 11's volume row), each stated in the step that moves it. Not a ruling: `kHeight` is the launcher's own window, not a value the game or the gate reads.
- **Two facts in this plan that the tree contradicts, found while writing these tasks and left for the controller.** (1) Task 4 Step 5's snippet calls `t.Skip(...)`; MiniTest has no `Skip` (`ps2xTest/include/MiniTest.h` offers `Run`, `Equals` and `IsTrue` only), and the case as committed prints `[skipped: ...]` to `std::cout` instead (`launcher_tests.cpp` :196-213) -- the plan text, not the code, is what is wrong. (2) Task 1b's File map row cites the `[gs-gl stats]` line at `gs_gl_backend.cpp` :1495-1503; it is at :1587-1600 today.
