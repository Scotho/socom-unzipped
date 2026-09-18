# Sprint 7 — Two Strangers, Two Machines, One Hosted Server: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the runtime honest on a machine that is not this one (a GL capability probe with a CPU fallback, a bounded command queue, a DPI-correct window, a native-VU1 mismatch warning, audio I/O off the callback), settle the two online-only semantics nobody has measured (equal-priority time slicing, two clients on the same RSA key), measure the lobby rate and root freeze shape 2, kill the 21k texture decodes a second so the ladder's back-pressure bar passes for real, and stand up a hosted Horizon server the launcher points at — so two strangers can download the zip, point it at their own r0001 ISOs, and play a round.

**Architecture:** Every runtime change is a failing test first, then `./build.sh test`, then the gate or the launch that proves it on the real exe. The autonomous loop runs **one launch at a time** through `scripts/run_detached.sh` and holds every suite while a launch is live. Bounded mechanical work (a fixture cut, a mechanical rename, a table of numbers out of a log) goes to an Opus subagent with an exact brief and a verification command; every judgement — what a number means, whether a bar is met, what to commit — stays with the controller. Tasks 4, 5 and 6 are owner-gated: their autonomous half runs to completion and then stops at a named line.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh`), Python 3 (`unittest`, numpy, Pillow), the local Horizon server (`server/start-servers.ps1`), raylib for the window/input/audio, PCSX2 2.8.1 as the console reference, Ghidra decomp `game/analysis/socom2_game.elf.decomp.c`, Git Bash + PowerShell.

**Spec:** `docs/superpowers/specs/2026-09-17-sprint-7-two-strangers-two-machines-design.md` (owner review pending; **Goal N there is Task N here**). **Required reading for every dispatch:** `docs/KNOWN.md`, `docs/AUDIT-2026-09-17.md` §1, §2.2, §2.3, `docs/HUMAN_TASKS.md`; for render tasks `docs/research/31-flat-grey-geometry.md` §3 and `docs/research/34-online-round-freeze-clut-serials.md`; for online tasks `docs/research/28-lobby-taxonomy.md`, `docs/research/29-online-freeze.md`, `docs/research/33-online-map-coverage.md`; for audio `docs/research/32-audio-path.md` §5–§7.

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

- [ ] **Step 5: The control round (launch 5).**

```bash
scripts/parity/online_control_round.sh "Frostfire" logs/parity/s7_slice_ctl
python -m tools_py.parity.lobby_report logs/parity/drive_s7_slice_ctl.txt
grep -a "prio=" logs/run_A_*.log | head -3
```
Expected: `RESULT CONTROL-ROUND`, both sides CONTROLLABLE, no freeze alarm > 10 s; the sampler lines now carry `prio=` and the priority table goes into `docs/research/29-online-freeze.md` §5 (one paragraph naming SOCOM's threads and their priorities).

- [ ] **Step 6: The ladder (launch 6).**

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

- [ ] **Step 1: Write the failing harness test** in `tools_py/tests/test_control_round.py`:

```python
    def test_same_key_flag_leaves_key_b_unset(self):
        env = control_round_env(["--same-key"])       # the helper this test adds: parse the script's exports
        self.assertNotIn("PS2X_SOCOM2_RSA_KEY_B", env)
    def test_default_still_sets_key_b(self):
        self.assertEqual(control_round_env([])["PS2X_SOCOM2_RSA_KEY_B"], "b")
```
Run: `python -m unittest tools_py.tests.test_control_round -v` → `NameError: name 'control_round_env' is not defined` (RED).

- [ ] **Step 2: Implement** the helper (it runs `bash -c '. scripts/parity/online_control_round.sh --print-env …'` behind a `--print-env` short-circuit the script gains at the top) and the `--same-key` branch in `scripts/parity/online_control_round.sh`. Run the same command: 2 tests OK, and the existing cases unchanged.

- [ ] **Step 3: The same-key control round (launch 7).**

```bash
scripts/parity/online_control_round.sh --same-key "Frostfire" logs/parity/s7_samekey
python -m tools_py.parity.lobby_report logs/parity/drive_s7_samekey.txt
```
Expected: `TOTAL launches=1 gameplay=1/1` and `RESULT CONTROL-ROUND`. Decision table: passes → write the KNOWN §1 row "two clients on the same RSA key reach gameplay (`s7_samekey`)" and **stop here, no code change**; fails where key B passes → Step 4.

- [ ] **Step 4 (only on a failure): the per-profile key.** Failing test in `launcher_tests.cpp`:

```cpp
            t.IsTrue(launcher::rsaKeyForProfile("craig") == "a" || launcher::rsaKeyForProfile("craig") == "b", "a key is chosen");
            t.IsTrue(launcher::rsaKeyForProfile("craig") != launcher::rsaKeyForProfile("dave"), "two profiles that differ get different keys");
            t.Equals(launcher::rsaKeyForProfile("craig"), launcher::rsaKeyForProfile("craig"), "the same profile is stable across runs");
```
(If `"craig"`/`"dave"` happen to collide, pick the two profile names the launch actually used and say so in the comment.) Run Task 1a Step 2's command → RED; implement `rsaKeyForProfile` and use it in `environmentFor`; GREEN; `./build.sh test`; rebuild; re-run Step 3's launch as `s7_samekey2`.

- [ ] **Step 5: Commit** (the result goes to `docs/KNOWN.md` §1 either way — the spec asks for the result, not the fix).

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

- [ ] **Step 3: Ten control rounds, one at a time (launches 9–18).** The harness is pinned and the map is Frostfire for all ten, so the number means one thing.

```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  scripts/parity/online_control_round.sh "Frostfire" logs/parity/s7_lobby_$i   # poll logs/s7_lobby_$i.done before the next
done
```
Run them **one at a time**, polling `logs/s7_lobby_<i>.done` between launches; never two at once. An `exit=75 BUSY` means the previous one is still live.

- [ ] **Step 4: Read the rate.**

```bash
python -m tools_py.parity.lobby_report --bar 0.8 logs/parity/drive_s7_lobby_*.txt
```
Expected: `RATE <g>/10 bar=0.80 PASS` (the spec's bar: 8 of 10). Decision table: ≥ 8 → record the rate and the classes in `docs/research/28-lobby-taxonomy.md` §2 and `docs/KNOWN.md` §1, done. 6–7 → fix the dominant class and run five more (`s7_lobby_11..15`), then re-read the rate over all fifteen. **Stop rule (spec §3):** under 6 of 10 opens a lobby-hardening task **before anything else online** — Tasks 2e and 3's online launches wait behind it.

- [ ] **Step 5: Commit** (harness plus the note; no runtime change).

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

- [ ] **Step 5: The loaded launch (launch 19).** `logs/s7_freeze_load.sh`: start the load generator, run one Frostfire control round, stop the generator.

```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s7_freeze_load.sh logs/s7_freeze_load.marker
```
The script body around the round: `powershell -c "1..4 | % { Start-Job { while($true){} } }"` before, `powershell -c "Get-Job | Remove-Job -Force"` after (research/29 §3's recipe), `PS2X_CLOCK_TRACE=1` set throughout.

- [ ] **Step 6: The quiet launch (launch 20).**

```bash
scripts/parity/online_control_round.sh "Frostfire" logs/parity/s7_freeze_quiet
```
Same exe, no load generator.

- [ ] **Step 7: The condition sentence.**

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

- [ ] **Step 1: The page trace (launch 21).** Settle the hypothesis before changing anything. The HUD texture page is the one `resolveTexture` logs for the HUD atlas; take it from the last online round's `[gs-pages]` lines or, failing that, page `0x0c0`.

```bash
# logs/s7_pages.sh: PS2X_GS_TRACE_PAGES=0x0c0:8 PS2X_GS_STATS=1 around one Frostfire control round
scripts/run_detached.sh --owner gate --purpose launch logs/s7_pages.sh logs/s7_pages.marker
grep -a "gs-pages" logs/run_A_*.log | head -60
grep -a "gs-gl stats" logs/run_A_*.log | grep -c "textures="
```
Expected (the audit's hypothesis): per frame, a `download gpu->cpu rt fbp=…` line for the post-process target **immediately preceding** the `texture tbp0=…` decode lines for the HUD pages — download, re-stamp, miss, decode, every frame. **Stop rule (spec §3):** if the trace does not show download-then-decode, stop the fix and re-open the hypothesis in `docs/KNOWN.md` §2 with what the trace *does* show. Do not "fix" a mechanism the trace did not find.

- [ ] **Step 2: Write the failing budget test.** In `ps2_gs_tests.cpp`, inside the console-replay GL case (:1523-1560, guarded by `PS2X_CONSOLE_REPLAY_GL`):

```cpp
                const uint64_t decodes = gl->textureDecodes();
                const uint64_t presents = gl->presentCount();
                const double perPresent = presents ? static_cast<double>(decodes) / static_cast<double>(presents) : 0.0;
                t.IsTrue(perPresent <= 40.0,
                         "texture decodes per present should be at most 40 (measured " + std::to_string(perPresent) +
                         "; the 21k/s defect was ~350 per present) -- audit 2026-09-17 section 2.2 F1");
```

- [ ] **Step 3: Run it and watch it fail.**

```bash
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; PS2X_CONSOLE_REPLAY_GL=1 third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe 2>&1 | grep -E "Failed\]|decodes per present|Total Tests"
```
Expected: the assertion fails with a measured value well above 40 (compilation first fails on `textureDecodes`/`presentCount`, which is the same red — add the two accessors, then see the number).

- [ ] **Step 4: Implement, one change at a time, re-running Step 3 after each** so the plan records which change bought what:
  1. `downloadRenderTargetToCpu` marks only the rows it wrote (`yStart`..`yEnd`), through the four-argument `markShadowPages`;
  2. the upload span includes `dsax`/`rrw`;
  3. `resolveTexture` compares per-page generations only for pages the write touched;
  4. GL texture objects are reused when the dimensions and format match.

- [ ] **Step 5: Green, then the suite.** Step 3's command with the assertion passing, then `./build.sh test` under the lock (exit 0) — and the whole `ps2_gs_tests` VRAM round-trip set must stay green: a marking change that loses a real invalidation shows up there first.

- [ ] **Step 6: Build, then the ladder (launch 22).**

```bash
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s7_decodes_build.marker
bash scripts/parity/ladder_frostfire.sh logs/parity/s7_decodes_ladder
grep -a "gs-gl stats" logs/parity/s7_decodes_ladder/*.log | tail -5
grep -a "waits=" logs/parity/s7_decodes_ladder/*.log | tail -4
```
Expected (the spec's bars): the ladder's **RUNG0 back-pressure bar passes — `waits` < 100 per instance** — and `PS2X_GS_STATS` shows texture decodes **under 2k/s**. Decision table: both met → done and KNOWN §2's 21k row is retracted into §1 with the launch name; decodes under 2k/s but waits ≥ 100 → the back-pressure cost is a different mechanism, file it and keep the decode fix; decodes still above 2k/s → back to Step 1's trace with the new marking in place, naming which of the four changes moved the number.

- [ ] **Step 7: Commit.**

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

### Task 7 — Close-out

**Files:** `docs/STATUS.md`, `docs/KNOWN.md`, `docs/ROADMAP.md` §6, `docs/CURRENT_SPRINT.md`, this plan.

**Interfaces:** the branch `sprint-7` merged into `develop` and `main`; `docs/CURRENT_SPRINT.md` opens Sprint 8; the ledger archived.

**Steps:**

- [ ] **Step 1: The repeat suite on a quiet host.**

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "s7 close-out: repeat suite" -- \
  bash -c 'PS2X_TEST_REPEAT=3 ./build.sh test'
```
Expected: exit 0 three times over, with the same counts each time; a case that passes twice and fails once is a flake to name in `docs/KNOWN.md` §4, not a pass.

- [ ] **Step 2: A full gate (launch 24).**

```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s7_closeout_gate.sh logs/s7_closeout_gate.marker
cat logs/parity/gate/s7_closeout/summary.txt
sha256sum dist/socom2.exe
```
Expected: `PASS title`, `PASS transition`, `PASS mission` on the sprint's final exe, with the sha recorded in STATUS.

- [ ] **Step 3: Tick this plan** against what actually landed — every `- [ ]` above becomes `- [x]` with the launch name that proved it, or keeps its box and gains a one-line reason and the sprint that carries it. No box is ticked on intent.

- [ ] **Step 4: The KNOWN audit.** Walk `docs/KNOWN.md` §1 and §2 row by row: the 21k-decodes row moves or is rewritten (Task 3), the lobby rate becomes a proven number (Task 2d), the freeze shape-2 row gets its sentence (Task 2e), the same-key row is settled (Task 2b), and anything this sprint contradicted is retracted into §3 with the measurement that killed it.

- [ ] **Step 5: STATUS, ROADMAP, CURRENT_SPRINT.** A STATUS entry with the current state (exe sha, gate stamp, the sprint's numbers); ROADMAP §6's Sprint 7 items marked; `docs/CURRENT_SPRINT.md` closes Sprint 7 and opens **Sprint 8** ("It looks and sounds finished, and it does not scare the machine") pointing at its spec.

- [ ] **Step 6: Whole-branch review, then merge.**

```bash
git log --oneline develop..sprint-7
git diff --stat develop..sprint-7
git checkout develop && git merge --no-ff sprint-7 && git push
git checkout main && git merge --ff-only develop && git push && git checkout sprint-7
```
Expected: every commit on the branch has a test or a launch named in its message; the merge is clean. Archive the ledger to `D:\socom_archive`.

- [ ] **Step 7: Commit the close-out docs.**

```bash
git commit -m "docs: Sprint 7 close-out -- the plan ticked against what landed, the KNOWN audit, STATUS, ROADMAP section 6, CURRENT_SPRINT to Sprint 8

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  docs/superpowers/plans/2026-09-17-sprint-7-two-strangers-two-machines.md \
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

## Self-review

- **Spec coverage.** Goal 1a → Task 1a (bar: gate 3/3 on GL, Step 9; CPU fallback reaches title, Step 10). Goal 1b → Task 1b (bar: working-set rise < 200 MB over a 30 s drag, Step 11; the "at most K pending, uploads intact" test is Step 1). Goal 1c → Task 1c (bars: title gate unchanged at 640x448 and mean |diff| < 3 at a 2x nearest resample, Step 8). Goal 1d → Task 1d (the warning names the hash; checked on Task 1e's gate log, Step 4). Goal 1e → Task 1e (test: render with the handle closed, Step 1; bar: correlation 0.99, Step 7). Goal 2a → Task 2a (test: two equal-priority threads do not interleave, a higher one preempts, Step 1; bar: the control bar holds and the kill lands 3 of 4, Steps 5–6; the stop rule is Step 6). Goal 2b → Task 2b (one same-key control round, Step 3; the per-profile key only on a failure, Step 4). Goal 2c → Task 2c (test "StRead after Read resumes at the stream LBN", Step 1; bars: correlation unchanged and the 0.26 s slip gone or attributed, Step 5). Goal 2d → Task 2d (ten pinned Frostfire launches, Step 3; bar 8 of 10 with the class of each miss, Step 4; the under-6 stop rule is in Step 4). Goal 2e → Task 2e (research/29 §4's fields, Step 3; one loaded and one quiet launch, Steps 5–6; the condition sentence, Step 7). Goal 3 → Task 3 (the page trace and its stop rule, Step 1; the four fixes, Step 4; the decodes-per-present budget, Steps 2–3; bars: `waits` < 100 per instance and decodes under 2k/s, Step 6). Goal 4 → Task 4 (autonomous Steps 1–6; the stop; Steps 7–10 after; bar: the Unzipped preset reaches the lobby from the portable zip, Step 9). Goal 5 → Task 5 (readout Steps 1–4; the stop; bar: a lobby and both players seen moving on both machines, Step 6). Goal 6 → Task 6 (the loop does not wait; Step 3 commits and moves on). Goal 7 → Task 7. **Launch budget.** The spec §3 allows "about 22 launches". This plan spends **25**, counted: `s7_gl_gate`, `s7_cpu_fallback`, `s7_drag` (Task 1); `s7_gl_gate2` (1c Step 8 — the GL gate re-run once the render-target and DPI changes exist, since 1a's gate ran before they did); `s7_audio_gate` (1e) and `s7_cdcursor_gate` (2c Step 5, the same script re-run on the CD-cursor exe); `s7_slice_ctl`, `s7_slice_ladder` (2a); `s7_samekey` (2b); `s7_lobby_1..10` (2d); `s7_freeze_load`, `s7_freeze_quiet` (2e); `s7_pages`, `s7_decodes_ladder` (3); `s7_hosted_login` (4); `s7_closeout_gate` (7). The three over budget are the two re-runs a strict test-then-measure order forces and the close-out gate; runtime builds are detached with `--purpose build` and are not launches. Task 1c's 2x capture takes no slot of its own, as marked.
- **Placeholder scan.** Clean: no unresolved marker of any kind anywhere in this plan — searching it for the two usual ones finds only this sentence. Every implementation detail the spec left open is a concrete choice marked *(controller's choice; re-rule if wrong)*: the GL probe's exit code 65 through the process exit status (1a), the 2x capture riding on the GL gate's launch slot (1c Step 8), and `two_machine_readout` living under `tools_py/parity/` with the spec's path as a shell wrapper (5). The `<N>` and `<n>` inside the commit-message templates are values to be filled from the run that precedes the commit, not unresolved decisions. `COMMUNITY_SERVER_ADDRESS_TBC`/`UNZIPPED_SERVER_ADDRESS_TBC` are the tree's existing literals, named as the owner's items, not placeholders this plan introduces.
- **Type consistency.** `GsGlCaps::evaluate(glVersion, dualSourceBlend, clipControl)`, `GsGlCaps::Latch`, `GsGlCaps::kExitCode`, `GSGlBackend::glUnavailable()`, `GsPendingCap::admit(latched, carriesState, bytes)`, `GsFrameBackpressure::latched()`, `GsGlTarget::choose(fbw, usedHeight)`, `Vu1NativeWarning::State::shouldWarn(matched, nowNs)`, `Mixer::pumpStreams()` / `closeStreamFilesForTest()`, `EeScheduler::hasReadyAbovePriority(priority)`, `markShadowPages(page, pageCount, rowFirst, rowLast)`, `GSGlBackend::textureDecodes()`, `host_samples.working_set_rise_mb(rows)`, `scale_compare.mean_abs_diff(big, small, scale)`, `audio_corr.correlate_arrays(a, b, window_s, rate)` / `min_corr(rows)`, `lobby_report.rate(summaries)`, `freeze_trace.classify(rows)`, `two_machine_readout.read_lines(a, b)` are each used with one signature everywhere they appear. Knob names: `PS2X_GS_GL_FORCE_FAIL`, `PS2X_GS_PENDING_CAP_MB`, `PS2X_SND_STREAM_WORKER`, `PS2X_WINDOW_SIZE`, `PS2X_GS_TRACE_PAGES`, `PS2X_GS_STATS`, `PS2X_CLOCK_TRACE`, `PS2X_CONSOLE_REPLAY_GL`, `PS2X_SOCOM2_RSA_KEY`/`_B`.
- **Owner gate.** The spec is unreviewed (its own header says so). Tasks 1–3 and 7 are fully autonomous under the owner's standing instruction of 2026-09-17; Tasks 4, 5 and 6 each run their autonomous half to a commit and then stop at a named `STOP:` line pointing at `docs/HUMAN_TASKS.md`. The loop never waits on a stop: it moves to the next autonomous task.
