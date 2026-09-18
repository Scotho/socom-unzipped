# Sprint 8 Goal 1 — The Linux Client: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the whole client — the runner and the launcher — build and run on Linux from the same CMake tree, so a stranger on a Linux PC unpacks one tarball, points `./socom_unzipped_launcher` at their own r0001 ISO and plays; and prove it in three rings (GitHub Actions on `ubuntu-24.04` without the generated code, the VirtualBox machine `socom-linux` with the generated code and a bare X session, the owner's real Linux box or Steam Deck) without moving the Windows build, the Windows gate or the shipped `dist/` by one byte.

**Architecture:** Every Windows-only surface the survey named gets a `#if`-guarded second half or a new platform file next to it; nothing that compiles today stops compiling. Every runtime change is a failing test first, run where it fails — which for most of Goal 1 is **inside the VM**, because the compile error *is* the RED. The Windows host keeps its `tools/llvm-mingw` build and writes `dist/`; the Linux build writes `dist-linux/` and never touches `dist/`. Long VM builds run detached under `nohup` with a marker file and are polled over SSH, exactly as host launches run through `scripts/run_detached.sh`. Bounded mechanical work (a mechanical guard sweep, a fixture cut, a table of numbers out of a log) goes to an Opus subagent with an exact brief and a verification command; every judgement — what a number means, whether a bar is met, what to commit — stays with the controller.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh` on the host; the system clang/clang++ + Ninja in the VM and on `ubuntu-24.04`), CMake ≥ 3.20, Python 3 (`unittest` — **not** pytest, see Global Constraints), raylib (window/GL/miniaudio-PulseAudio-ALSA/GLFW gamepads, portable as fetched), FFmpeg via pkg-config on Linux, `xdotool` + ImageMagick `import` for the harness's Linux capture, GitHub Actions (`ubuntu-24.04`), VirtualBox VM `socom-linux`, Git Bash + PowerShell on the host.

**Spec:** `docs/superpowers/specs/2026-09-18-sprint-8-linux-and-finish-design.md` — **Goal 1 only**; its "What the survey found" paragraph is the surface this plan closes and its "Design" items 1-6 are Tasks 1-11 here. **Required reading for every dispatch:** this plan's Handoff notes and Global Constraints, `docs/KNOWN.md` §1-§2, `docs/HUMAN_TASKS.md`, `docs/CURRENT_SPRINT.md`'s Sprint 8 block; for the sockets `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_hostnet.h` (the whole header is the contract); for the launcher `third_party/ps2recomp/ps2xLauncher/src/win32_glue.h`; for the harness `tools_py/parity/drive.py` §`main` and `tools_py/parity/gate.py` §`STAGES`.

## Handoff notes for the executing model (read once)

- **Process.** superpowers:subagent-driven-development; a fresh implementer per task; a task review after each that re-derives at least one number independently; the controller merges. Ledger at `.superpowers/sdd/2026-09-18-sprint-8-linux-client/progress.md`. Decisions on the owner's behalf are `Ruling: … — why — cost if wrong`, numbered from **R99** (Sprint 7 ended at R98).
- **The working tree already carries an uncommitted first pass.** As of 2026-09-18 a concurrent session has begun Task 1 and Task 7 in the checkout: `git status` shows modified `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt`, `third_party/ps2recomp/ps2xLauncher/CMakeLists.txt`, `third_party/ps2recomp/ps2xLauncher/src/win32_glue.cpp`, `scripts/make_portable.sh`, and untracked `third_party/ps2recomp/ps2xLauncher/src/posix_glue.cpp`, `scripts/portable_libs.py`, `tools_py/tests/test_portable_libs.py`. **Every line number in this plan is the number at `HEAD` (`7506685`)**, which is what a fresh clone shows. Before starting a task, `git diff -- <the task's files>` and reconcile: adopt what is there when it matches the step, and say so in the ledger rather than writing it twice. Do not revert the concurrent work to make a step's RED reproduce; state instead that the step's RED was already taken.
- **`docs/KNOWN.md` has one writer: the controller.** Retractions happen on discovery, in the same hour.
- **Autonomy (owner 2026-09-17, standing).** Proceed autonomously; no waiting for a window the owner names. **One host launch at a time**, always through `scripts/run_detached.sh`, and **suites are held while a host launch runs**: no `./build.sh test`, no `python -m unittest`, no gate and no second launch while `logs/.quiet` exists (`bash scripts/check_quiet_gate.sh` answers). **The VM is not the owner's desk**: a run inside `socom-linux` is not a host launch and does not take the quiet gate — but the *host CPU* it costs does, so a VM build and a host launch never overlap.
- **Subagents (owner 2026-09-17).** Bounded mechanical work goes to Opus subagents with an exact brief and a verification command; judgment stays with the controller. A brief names: the files to touch, the exact edit, the command that proves it, and the expected output. A subagent never decides whether a bar is met, never writes `docs/KNOWN.md`, never commits, and never starts a launch.
- **Commit conventions.** `git commit -m "…" -- <paths>` with an explicit pathspec; never `git add -A`; `server/config/simulated.db` stays unstaged (it is modified in the working tree right now and must stay that way); `ONBOARDING.md` stays untracked; `vm/` is gitignored (`.gitignore:25`) and nothing under it is ever staged — **including `vm/keys/socom_linux`, which is a private key**. Push after each commit. Trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **The two build worlds.**
  - **Windows host.** `./build.sh` with `tools/llvm-mingw` on `PATH` (`build.sh:6`); build dir `third_party/ps2recomp/build-clang`; output `dist/socom2.exe`, `dist/socom_unzipped_launcher.exe`, `dist/vu1_replay.exe`.
  - **Linux.** `scripts/build_linux.sh` (Task 1) with the **system** `clang`/`clang++` and Ninja; build dir `third_party/ps2recomp/build-linux` — deliberately at the same depth as `build-clang`, because `ps2x_tests` resolves `ps2xRecomp/include/ps2recomp/instructions.h` and `tests/fixtures/` **relative to its own directory** (`build.sh:62`, `socom2_audio_tests.cpp:30`), so it must run from `<build>/ps2xTest` four levels under the repo root. Output `dist-linux/`.
- **Ring (a): GitHub Actions.** The repo is `https://github.com/Scotho/socom-unzipped` (private, Actions enabled). `gh` 2.100.0 is installed and authenticated on the host. There is **no `.github/` directory yet** — Task 2 creates it. CI has **no generated game code**, so it can never build `ps2EntryRunner`: it builds `ps2_runtime`, `ps2x_tests` and the launcher only, which is exactly why Task 1's runner skip has to exist before Task 2 can be green.
- **Ring (b): the VM `socom-linux`.** Ubuntu 24.04.5 server, user `socom`, 8 cores, 8 GB, host-only adapter, VMSVGA with 3D, SSH forwarded to the host's 2222.
  - Shell: `ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 '<command>'`
  - Tree: `rsync -az -e "ssh -i vm/keys/socom_linux -p 2222" --exclude build-clang --exclude build-tools --exclude vm --exclude logs ./ socom@127.0.0.1:~/socom_pc/`
  - Generated code, **separately and required for the runner**: `rsync -az -e "ssh -i vm/keys/socom_linux -p 2222" recomp/output/ socom@127.0.0.1:~/socom_pc/recomp/output/` — **576 MB, 14,882 files**; expect tens of minutes the first time and seconds after.
  - The disc, **once, ~4 GB**: `rsync -az --partial --progress -e "ssh -i vm/keys/socom_linux -p 2222" "game/SOCOM II - U.S. Navy SEALs (USA).iso" socom@127.0.0.1:~/socom_pc/game/`
  - Installed by `vm/postinstall.sh`: `clang lld cmake ninja-build`, the X11/GL/ALSA/Pulse/FFmpeg dev packages, `mesa-utils`, `xserver-xorg xinit openbox x11-utils`, `xdotool scrot imagemagick`, `rsync`, `python3`. `socom` has passwordless sudo.
  - **Long VM work runs detached inside the VM**, never held open across a tool call:
    ```bash
    ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
      'cd ~/socom_pc && rm -f logs/<name>.marker && mkdir -p logs && nohup bash -c "<command> > logs/<name>.log 2>&1; echo exit=\$? > logs/<name>.marker" >/dev/null 2>&1 & disown'
    ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 'cat ~/socom_pc/logs/<name>.marker 2>/dev/null || echo running'
    ```
    Poll the marker; never the SSH call.
- **Ring (c): the owner.** A real Linux PC or a Steam Deck with the tarball — a `docs/HUMAN_TASKS.md` item written in Task 12, never a blocker.
- **Test binary.** `ps2x_tests` takes no filter and runs every case (~549 on Windows today, well under a minute). Windows: `third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe`. Linux: `third_party/ps2recomp/build-linux/ps2xTest/ps2x_tests`.

### The command set (use these verbatim)

```bash
# --- the Windows host ---
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
python -m unittest tools_py.tests.<module> -v
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "<what>" -- ./build.sh test
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/<name>.marker
scripts/run_detached.sh --owner gate  --purpose launch <script>               logs/<name>.marker

# --- CI ---
gh run list --branch sprint-8 --limit 3
gh run watch <id> --exit-status

# --- the VM ---
VMSSH='ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1'
VMRSYNC='rsync -az -e "ssh -i vm/keys/socom_linux -p 2222"'
$VMSSH 'cd ~/socom_pc && cmake --build third_party/ps2recomp/build-linux --target ps2x_tests -j 8'
$VMSSH 'cd ~/socom_pc/third_party/ps2recomp/build-linux/ps2xTest && ./ps2x_tests'
scp -i vm/keys/socom_linux -P 2222 socom@127.0.0.1:~/socom_pc/logs/<f> logs/<f>
```

A VM launch script is a five-line file under `logs/`, synced with the tree, in the shape of `logs/audio_gate7.sh`:

```bash
#!/usr/bin/env bash
cd "$HOME/socom_pc" || exit 1
export DISPLAY=:0
<the run>
rc=$?; echo "done $rc" > logs/<name>.done; exit $rc
```

## Global Constraints

- Branch `sprint-8` off `develop` at `b65fe46`. Branch in the main checkout, never a worktree.
- **The Windows build and its gate must be byte-for-byte unaffected**: every change is under `#if` / `if(WIN32)` / `if(UNIX)` or in new files. *Reading:* this is about the artefacts a Windows player and the gate see — `dist/socom2.exe`, `dist/socom_unzipped_launcher.exe`, `dist/vu1_replay.exe`, every log line they print, and the gate's verdict. `ps2x_tests` gains cases (that is what RED-first means) and `launcher_config.cpp` gains one pure function nothing on Windows calls yet; neither is a behaviour change, and each is named in its task. If a step cannot be written under a guard, it stops and becomes a ruling.
- **Every runtime change under a RED test first.** Where the RED is a Linux compile error, the step names the exact error text and the machine it is reproduced on (the VM, or CI once Task 2 lands). A step that cannot state its RED says so in one sentence and names what verifies it instead (the VM boot, Task 8).
- `./build.sh test` exit 0 on the Windows host before any commit touching `third_party/ps2recomp/`, `tools_py/`, `scripts/` or `build.sh`. The three-stage gate PASS before any commit touching `third_party/ps2recomp/ps2xRuntime/src/`, `tools_py/parity/{drive,gate,compare}.py` or `scripts/parity/`.
- Explicit pathspecs on every commit, never `git add -A`. `server/config/simulated.db` is **never** staged. `vm/` is never staged.
- Commit trailer, every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- LF line endings in every new file. New shell scripts are `chmod +x` and committed with the mode bit.
- **Defaults move only where a task's bar says so**, and each move is a numbered ruling. Frozen: the Windows launcher defaults, the runtime's own 640x448 default, the gate's own 640x448 window and `drive.py`'s client-rect assertion, speed work, patches to recompiled game logic.
- **Python tests are `unittest`, never pytest.** `tools_py/tests/test_test_hygiene.py` fails the suite on a `test_*.py` outside `tools_py/tests/`, on any `import pytest`, and on a module-level `def test_`. The one runner is `python -m unittest discover -s tools_py/tests -t .` (`build.sh:60`).
- **`dist/` is Windows-only output; the Linux build writes `dist-linux/`.** Both are gitignored build products; keeping them apart is what makes "byte-for-byte unaffected" checkable with `sha256sum` rather than argued.

---

## File map

| Path | Responsibility |
|---|---|
| `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt` (:454-465 the generated-dir switch, :477-486 the runner target, :487-505 its options and sources, :561-565 its link, :626-631 `--allow-multiple-definition`, :647-651 `install`), `third_party/ps2recomp/ps2xLauncher/CMakeLists.txt` (:13 the `WIN32` flag, :19-21 comdlg32/shell32), `third_party/ps2recomp/ps2xTest/CMakeLists.txt` (:122-124 `ws2_32`), `third_party/ps2recomp/ps2xLauncher/src/posix_glue.cpp` (new, stub here), `scripts/build_linux.sh` (new) | **Task 1**: the runner skipped when there is no generated code, RPATH `$ORIGIN/lib`, the launcher without the `WIN32` flag, and one Linux build script mirroring `build.sh`'s three steps |
| `.github/workflows/linux.yml` (new) | **Task 2**: ring (a) — configure, build and run `ps2x_tests` on `ubuntu-24.04` with no generated code, on every push and PR |
| `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_hostnet.cpp` (:3-11 the Winsock include, :36 `SOCKET`, :53-67 `mapError`, :173-181 `WSAStartup`, :190-195 `closesocket`/`WSACleanup`, :206-211 `socket`+`FIONBIO`, :224, :258-272, :283-295, :313-322, :335-378, :384-413, :422-424, :441, :457-458, :500-515), `third_party/ps2recomp/ps2xTest/src/socom2_libnetb_tests.cpp` | **Task 3**: hostnet's BSD half behind the same seventeen functions, and the loopback case that is RED on Linux and green on both |
| `third_party/ps2recomp/ps2xLauncher/src/posix_glue.cpp`, `third_party/ps2recomp/ps2xLauncher/src/win32_glue.cpp` (:1-208, wrapped), `third_party/ps2recomp/ps2xLauncher/src/win32_glue.h` (:9-32, the contract), `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h` (:77), `third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp` (:285-320 `environmentFor`), `third_party/ps2recomp/ps2xTest/CMakeLists.txt`, `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp` | **Task 4**: the launcher's POSIX glue — `/proc/self/exe`, `posix_spawn` with the merged environment and a redirected log, `waitpid`, `SIGTERM`/`SIGKILL`, `zenity`, `xdg-open` — and `mergeEnvironment` as the pure piece both platforms share |
| `third_party/ps2recomp/ps2xRuntime/include/runtime/host_prof_line.h` (new), `third_party/ps2recomp/ps2xRuntime/include/runtime/cpu_time_ms.h` (new), `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` (:29-30 the include, :870-913 the VEH, :1634-1640 the install, :1712-1919 `ps2HostProfStart`), `third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp` (:26-27, :2835-2854), `third_party/ps2recomp/ps2xTest/src/host_config_tests.cpp`, `tools_py/tests/test_freeze_trace.py` | **Task 5**: `sigaction` for the crash line, a `SIGPROF`+`ucontext` sampler into the same histogram, `clock_gettime` thread times — with the two shared formatters pinned by tests on both platforms |
| `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` (:58 the unguarded `<windows.h>`, :916-968 the `--prof` sampler, :963 `GetModuleFileNameA`) | **Task 6**: the offline VU1 tool compiles on Linux |
| `scripts/make_portable.sh` (:1-44, all of it), `scripts/portable_libs.py` (new), `tools_py/tests/test_portable_libs.py` (new), `tools_py/tests/test_make_portable.py` (:11 the skip guard) | **Task 7**: the tarball, and the `ldd` filter as a testable pure function |
| `logs/s8_vm_boot.sh` (new), `logs/s8_win_boot.sh` (new), `logs/parity/s8_*` | **Task 8**: the VM ring — first build, suite, boot under X, frame compare against Windows, audio correlation |
| `tools_py/parity/x11shot.py` (new), `tools_py/parity/hostshot.py` (new, the selector), `tools_py/parity/winshot.py` (:17-34, :64-71, :88-122, :149-156), `tools_py/parity/keys.py` (:42-50), `tools_py/parity/drive.py` (:25, :245-269), `tools_py/tests/test_hostshot.py` (new) | **Task 9**: the harness's Linux capture and key halves, selected by a pure function tested on both |
| `logs/s8_vm_title.sh` (new), `logs/parity/gate/s8_vm_title/` | **Task 10**: the title stage of the gate inside the VM |
| `logs/s8_vm_tarball.sh` (new) | **Task 11**: the tarball unpacked in a fresh directory, `--selftest`, then the launcher for real under X |
| `docs/KNOWN.md`, `docs/STATUS.md`, `docs/CURRENT_SPRINT.md`, `docs/HUMAN_TASKS.md`, this plan | **Task 12**: Goal 1 close-out |

---

## Task 1 — CMake and a Linux build script (spec Design item 1)

*(landed 2026-09-18 by the concurrent implementation slices: 2aa02c3 -- ticked wholesale; the handoff notes' reconciliation rule applies, line numbers are 7506685's)*

**Files:**
- Create: `scripts/build_linux.sh`, `third_party/ps2recomp/ps2xLauncher/src/posix_glue.cpp` (a stub that compiles; Task 4 fills it)
- Modify: `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt` (:454-465, :476-487, :488-547, :561-574, :598-651), `third_party/ps2recomp/ps2xLauncher/CMakeLists.txt` (:13, :19-21), `third_party/ps2recomp/ps2xLauncher/src/win32_glue.cpp` (:1 and :208 — wrapped whole, so the two glue files never define the same symbol twice)
- Read only, to confirm and record: `third_party/ps2recomp/ps2xTest/CMakeLists.txt` (:122-124), `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt` (:626-631)
- Test: none beyond the configure. This task touches no runtime code path; its checks are a Linux configure and an unchanged Windows `./build.sh test`.

**Interfaces:**
- CMake derived variable `PS2X_BUILD_RUNNER` (`ON`/`OFF`, derived inside `ps2xRuntime/CMakeLists.txt`, never set by the caller): `ON` when `PS2X_RUNNER_GENERATED_DIR` is non-empty **and** `RUNNER_SRC_FILES` is non-empty after the glob; `OFF` otherwise, with `message(STATUS "ps2EntryRunner skipped: no generated code (PS2X_RUNNER_GENERATED_DIR='...')")`. Every `ps2EntryRunner` rule in the file lives inside `if(PS2X_BUILD_RUNNER)`.
- CMake variable `PS2X_LAUNCHER_EXE_TYPE` (`ps2xLauncher/CMakeLists.txt`): `WIN32` on Windows, empty elsewhere, expanded into `add_executable`.
- `scripts/build_linux.sh [--no-runner] [tools|runtime|test|all]` — default `all`; `CC`/`CXX` default to the system `clang`/`clang++`; the generated directory comes from the environment variable `GEN`, default `recomp/output`; `--no-runner` leaves it empty (the CI shape). Build dir `third_party/ps2recomp/build-linux`, output `dist-linux/`.
- `win32glue` (unchanged contract, `ps2xLauncher/src/win32_glue.h:9-32`): `exeDirectory`, `browseForIso`, `openFolder`, `stamp`, `startGame`, `terminate`, and `GameProcess::running/exitCode/close`. On Linux `posix_glue.cpp` provides all of them; on Windows `win32_glue.cpp` does. Exactly one of the two compiles per platform.

**Steps:**

- [x] **Step 1: Read what the empty-generated-dir path does today, and write the answer into the commit message.** The brief asks which of "links an empty exe" or "fails" happens; the tree says **neither**. At `HEAD`, `ps2xRuntime/CMakeLists.txt:455` takes the `else()` arm at :460-464 when `PS2X_RUNNER_GENERATED_DIR` is empty, which globs `src/runner/*.cpp` — **one real file, `src/runner/register_functions.cpp`**, an all-zero 16 M-slot function table — and :470-474 then appends `src/main.cpp` (`src/runner/main.cpp` does not exist; `src/main.cpp`, 255 lines, does). So the target configures and, on Windows, links a *stub* runner that starts and dispatches nothing. What actually stops a Linux build is not the glob at all: :501-505 attach four runner-only sources to that target unconditionally, and two of them do not compile on Linux —

  ```
  src/lib/game_overrides_socom2.cpp:30    #include <windows.h>        (under #ifdef _WIN32 at :29 -- fine)
  src/lib/game_overrides_socom2.cpp:1712  void ps2HostProfStart(void *) { ... DuplicateHandle ... }   NOT guarded
  src/lib/socom2_hostnet.cpp:36           SOCKET s = INVALID_SOCKET;                                  NOT guarded
  ```

  Record it exactly so: *the empty glob is harmless; the runner is unbuildable on Linux until Tasks 3 and 5, which is why it is **skipped**, not repaired here.*

```bash
sed -n '454,475p;499,506p' third_party/ps2recomp/ps2xRuntime/CMakeLists.txt
ls third_party/ps2recomp/ps2xRuntime/src/runner/ third_party/ps2recomp/ps2xRuntime/src/main.cpp
```

- [x] **Step 2: Gate every `ps2EntryRunner` rule behind `PS2X_BUILD_RUNNER`.** In `ps2xRuntime/CMakeLists.txt`, after `RUNNER_SRC_FILES` is complete (after :474) and before the target at :476:

```cmake
# Sprint 8 Goal 1 design item 1: the runner IS the recompiled game, and the generated code is not in
# the repository (14,882 files, 576 MB, produced from the owner's disc). Where it is absent -- CI, a
# fresh clone -- the runner target and every rule hanging off it is SKIPPED, not configured into a
# build that cannot link. ps2_runtime, ps2x_tests, vu1_replay and the launcher still configure.
if(PS2X_RUNNER_GENERATED_DIR AND RUNNER_SRC_FILES)
    set(PS2X_BUILD_RUNNER ON)
else()
    set(PS2X_BUILD_RUNNER OFF)
    message(STATUS "ps2EntryRunner skipped: no generated code (PS2X_RUNNER_GENERATED_DIR='${PS2X_RUNNER_GENERATED_DIR}')")
endif()
```

  Then wrap, each in its own `if(PS2X_BUILD_RUNNER) ... endif() # PS2X_BUILD_RUNNER`: the target and its include directories (:476-487); the runner's `-msse4.1` at :490 — **`ps2_runtime`'s own `-msse4.1` at :491 stays outside the guard**, the library still needs it; `PS2X_GENERATED_OPT` (:494-498, add `PS2X_BUILD_RUNNER AND` to the condition at :495); the runner sources, unity, PCH, boot-ELF and `/FS` block (:499-547); the link and debug-UI block (:561-572) with `ps2x_stage_ffmpeg_runtime_dlls(ps2EntryRunner)` at :574; the Vita VPK (add `AND PS2X_BUILD_RUNNER` to :599); `EnableFastReleaseMode(ps2EntryRunner)` at :610 and the subsystem block at :612-622 (add `PS2X_BUILD_RUNNER AND` to :612); the WinAPI-clash block (:627-631); the Vita LTO block (add `AND PS2X_BUILD_RUNNER` to :634); the Android source (add `AND PS2X_BUILD_RUNNER` to :643). Split the single `install(TARGETS ps2_runtime ps2EntryRunner ...)` at :647-651 into an unconditional `install(TARGETS ps2_runtime ...)` and a guarded `install(TARGETS ps2EntryRunner ...)`.

- [x] **Step 3: `-Wl,--allow-multiple-definition` stays WIN32-only — verify, do not change.** :626-631 is already `if(MSVC) /FORCE:MULTIPLE elseif(WIN32) -Wl,--allow-multiple-definition endif()`, so the flag can never reach a Linux link. Extend the comment at :626 to say *why* it is Windows-only by construction — the clash is WinAPI `CloseWindow`/`ShowCursor` against raylib, and there is no such clash on Linux — and leave the logic alone. Same for `ps2xTest/CMakeLists.txt:122-124`: `ws2_32` is **already** under `if(WIN32)`. **Both were listed in the brief as work and the tree had already done them. Record both in the task review and in the sprint report.**

- [x] **Step 4: RPATH `$ORIGIN/lib` on the runner and the launcher, UNIX only.** In `ps2xRuntime/CMakeLists.txt` inside the `PS2X_BUILD_RUNNER` block, right after :487:

```cmake
if(UNIX AND NOT APPLE)
    # The portable folder (Task 7) keeps its non-system .so files in lib/ next to the binary.
    set_target_properties(ps2EntryRunner PROPERTIES
        BUILD_RPATH "\$ORIGIN/lib"
        INSTALL_RPATH "\$ORIGIN/lib"
    )
endif()
```

  and the same four lines for `socom_unzipped_launcher` at the end of `ps2xLauncher/CMakeLists.txt`. The backslash before `$ORIGIN` is required: CMake must emit the literal `$ORIGIN`, not an expanded (empty) variable.

- [x] **Step 5: The launcher's `WIN32` executable flag, and the POSIX source.** `ps2xLauncher/CMakeLists.txt:13` is `add_executable(socom_unzipped_launcher WIN32 src/main.cpp src/win32_glue.cpp src/mic_devices.cpp)`. `WIN32` is an `add_executable` *keyword*, so it cannot be made conditional inline; route it through a variable:

```cmake
# Sprint 8 Task 1: the WIN32 keyword means "no console window" and exists only on Windows, so it is
# passed through a variable that is empty elsewhere; the same win32glue interface is implemented by
# src/posix_glue.cpp on Unix (src/win32_glue.cpp compiles to nothing there).
if(WIN32)
    set(PS2X_LAUNCHER_EXE_TYPE WIN32)
else()
    set(PS2X_LAUNCHER_EXE_TYPE "")
endif()
add_executable(socom_unzipped_launcher ${PS2X_LAUNCHER_EXE_TYPE} src/main.cpp src/win32_glue.cpp src/mic_devices.cpp)
if(UNIX)
    target_sources(socom_unzipped_launcher PRIVATE src/posix_glue.cpp)
endif()
```

  `comdlg32`/`shell32` at :19-21 are **already** under `if(WIN32)` — leave them. `mic_devices.cpp` needs no guard: it includes raylib's own `external/miniaudio.h` without `MINIAUDIO_IMPLEMENTATION` (`mic_devices.cpp:5-13`), and miniaudio's capture backends on Linux are PulseAudio and ALSA, whose dev packages `vm/postinstall.sh` and Task 2's workflow both install.

- [x] **Step 6: Make `win32_glue.cpp` contribute nothing on Linux.** Its per-function `#else` arms (:50-52, :66-67, :75-77, :89-91, :192-196, :204-206) would otherwise define the same `win32glue::` symbols `posix_glue.cpp` defines. Wrap the whole file: `#ifdef _WIN32` after the file comment at :1, `#endif // _WIN32` after the closing brace at :208, and three lines of comment saying the `#else` arms are now unreachable and their behaviour lives in `posix_glue.cpp`. **The Windows preprocessor output is unchanged** — `_WIN32` is defined there, so every byte the compiler sees is the same byte.

- [x] **Step 7: The stub `posix_glue.cpp`,** so Task 4's tests are RED on an assertion rather than on a link error:

```cpp
// Sprint 8 Goal 1 design item 4: the launcher's POSIX half. Task 1 puts the translation unit in place
// so the Linux launcher links; Task 4 implements it under tests. Until then every entry point is the
// honest refusal, never a silent success.
#ifndef _WIN32
#include "win32_glue.h"

#include <ctime>
#include <filesystem>

namespace fs = std::filesystem;

namespace win32glue
{
    std::string exeDirectory() { return fs::current_path().string(); }
    std::string browseForIso() { return {}; }
    void openFolder(const std::string &) {}

    std::string stamp()
    {
        char buf[32];
        const std::time_t t = std::time(nullptr);
        std::tm tm{};
        localtime_r(&t, &tm);
        std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &tm);
        return buf;
    }

    bool GameProcess::running() const { return false; }
    int GameProcess::exitCode() const { return 0; }
    void GameProcess::close() { process = nullptr; log = nullptr; }

    bool startGame(const std::string &, const launcher::Config &, GameProcess &out)
    {
        out.error = "launching is not implemented on this platform yet";
        return false;
    }

    void terminate(GameProcess &) {}
}
#endif // !_WIN32
```

- [x] **Step 8: Write `scripts/build_linux.sh`** — `build.sh`'s steps with the native toolchain and nothing else:

```bash
#!/usr/bin/env bash
# Sprint 8 Goal 1 design item 1: build.sh's steps with the system toolchain. The recompiler is NOT re-run
# here -- the generated code comes from the Windows host's recomp/output (rsync'd), because it is produced
# from the owner's disc and is platform-neutral C++.
#   scripts/build_linux.sh [--no-runner] [tools|runtime|test|all]     (default all)
#   GEN=<dir>   the generated code (default recomp/output); --no-runner leaves it empty (the CI shape)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PS2R="$ROOT/third_party/ps2recomp"
BUILD="$PS2R/build-linux"          # same depth as build-clang: ps2x_tests resolves fixtures relative to itself
TOOLBUILD="$PS2R/build-tools-linux"
DIST="$ROOT/dist-linux"
GEN="${GEN:-$ROOT/recomp/output}"
CC_BIN="${CC:-clang}"
CXX_BIN="${CXX:-clang++}"
NO_RUNNER=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --no-runner) NO_RUNNER=1 ;;
    *) ARGS+=("$a") ;;
  esac
done
STEP="${ARGS[0]:-all}"
[ "$NO_RUNNER" = 1 ] && GEN=""
JOBS="$(nproc)"

configure() {
  cmake -S "$PS2R" -B "$BUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER="$CC_BIN" -DCMAKE_CXX_COMPILER="$CXX_BIN" \
        -DPS2X_RUNNER_GENERATED_DIR="$GEN" -DPS2X_ENABLE_LTO="${LTO:-OFF}" \
        -DPS2X_GENERATED_OPT="${GENOPT:--O1}"
}

build_tools() {
  cmake -S "$PS2R" -B "$TOOLBUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER="$CC_BIN" -DCMAKE_CXX_COMPILER="$CXX_BIN" >/dev/null
  cmake --build "$TOOLBUILD" --target ps2_recomp ps2_analyzer -j "$JOBS"
}

runtime() {
  configure
  mkdir -p "$DIST"
  if [ -n "$GEN" ]; then
    cmake --build "$BUILD" --target ps2EntryRunner -j "$JOBS"
    cp "$BUILD/ps2xRuntime/ps2EntryRunner" "$DIST/socom2"
  else
    cmake --build "$BUILD" --target ps2_runtime -j "$JOBS"
    echo "build_linux: --no-runner, ps2EntryRunner skipped (no generated code)"
  fi
  cmake --build "$BUILD" --target socom_unzipped_launcher -j "$JOBS"
  cp "$BUILD/ps2xLauncher/socom_unzipped_launcher" "$DIST/"
  [ -f "$ROOT/game/disc/socom2_game.elf" ] && cp "$ROOT/game/disc/socom2_game.elf" "$DIST/"
  echo "built $DIST"
}

test_step() {
  configure
  ( cd "$ROOT" && python3 -m unittest discover -s tools_py/tests -t . )
  cmake --build "$BUILD" --target ps2x_tests vu1_replay -j "$JOBS"
  # ps2x_tests reads ps2xRecomp/include/ps2recomp/instructions.h and tests/fixtures relative to its own
  # directory (build.sh:62), which is why build-linux sits at build-clang's depth.
  ( cd "$BUILD/ps2xTest" && ./ps2x_tests )
  mkdir -p "$DIST" && cp "$BUILD/ps2xRuntime/vu1_replay" "$DIST/vu1_replay"
  echo "tests: ok"
}

case "$STEP" in
  tools)   build_tools ;;
  runtime) runtime ;;
  test)    test_step ;;
  all)     runtime; test_step ;;
  *) echo "unknown step $STEP"; exit 2 ;;
esac
```

  `chmod +x scripts/build_linux.sh`. What is deliberately absent, and why: no `recomp` step (the recompiler is not re-run on Linux this sprint — the generated C++ is platform-neutral and comes from the host), no DLL staging, and no `vu1_replay` fixture verify (`build.sh`'s runs 1-9 stay a Windows step until Task 6 lands and Task 8 can afford the minutes).

- [x] **Step 9: The two checks.** First, in the VM — the host has no Linux CMake:

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/socom_pc && rm -rf /tmp/b && cmake -S third_party/ps2recomp -B /tmp/b -G Ninja -DPS2X_RUNNER_GENERATED_DIR= 2>&1 | tail -20'
```
  Expected, and the line this step passes on: `-- ps2EntryRunner skipped: no generated code (PS2X_RUNNER_GENERATED_DIR='')`, then `-- Generating done` and `-- Build files have been written to: /tmp/b`. Run the same command **before** Step 2 and keep its output in the ledger: it configures `ps2EntryRunner` and prints no such message — that absence is this task's RED.

  Second, that the host did not move:

```bash
sha256sum dist/socom2.exe dist/socom_unzipped_launcher.exe > /tmp/dist_before.txt
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "T1: build.sh test" -- ./build.sh test
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s8_t1_build.marker
sha256sum -c /tmp/dist_before.txt
```
  Expected: `./build.sh test` exit 0 at Sprint 7's close-out counts (549 C++ cases, 1172 Python), then `dist/socom2.exe: OK` and `dist/socom_unzipped_launcher.exe: OK`. **A changed hash on either is a stop** — a guard leaked into the Windows path and the step is not done.

- [x] **Step 10: Commit.**

```bash
git commit -m "build(linux): skip the runner without generated code, RPATH \$ORIGIN/lib, a native build script

Sprint 8 Goal 1 design item 1. The runner IS the recompiled game and the generated code (14,882 files,
576 MB) is not in the repository, so CI and a fresh clone had nothing to link: ps2xRuntime/CMakeLists.txt
derives PS2X_BUILD_RUNNER and skips ps2EntryRunner with a message(STATUS) instead of configuring it.
What the empty PS2X_RUNNER_GENERATED_DIR did BEFORE is recorded here because the survey asked: the
else() arm at :460-464 globs src/runner/register_functions.cpp and :470-474 appends src/main.cpp, so the
target configured and linked a STUB runner -- it never failed and was never empty. The real blocker on
Linux is that :501-505 attach game_overrides_socom2.cpp (ps2HostProfStart, unguarded) and
socom2_hostnet.cpp (SOCKET, unguarded) to that target; Tasks 3 and 5 fix those, and until then the
runner is skipped rather than repaired.
Also: RPATH \$ORIGIN/lib on the runner and the launcher for UNIX (Task 7's lib/), the launcher's WIN32
executable keyword routed through a variable that is empty off Windows, src/posix_glue.cpp compiled
under if(UNIX) as a stub that refuses honestly, and win32_glue.cpp wrapped in #ifdef _WIN32 so the two
never define the same symbol. ws2_32 (ps2xTest:122-124) and -Wl,--allow-multiple-definition
(ps2xRuntime:626-631) were ALREADY WIN32-only; only their comments changed.
scripts/build_linux.sh mirrors build.sh's steps with the system clang, Ninja, -DPS2X_GENERATED_OPT=-O1
and a --no-runner flag (the CI shape), into build-linux/ and dist-linux/ so dist/ never moves.
Windows unchanged: build.sh test green, dist/socom2.exe and dist/socom_unzipped_launcher.exe sha256 equal.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/CMakeLists.txt \
  third_party/ps2recomp/ps2xLauncher/CMakeLists.txt \
  third_party/ps2recomp/ps2xLauncher/src/win32_glue.cpp \
  third_party/ps2recomp/ps2xLauncher/src/posix_glue.cpp \
  third_party/ps2recomp/ps2xTest/CMakeLists.txt \
  scripts/build_linux.sh
git push
```

---

## Task 2 — GitHub Actions on ubuntu-24.04 (spec Design item 6a)

*(landed 2026-09-18 by the concurrent implementation slices: 2aa02c3; the first CI run reached the compiler -- ticked wholesale; the handoff notes' reconciliation rule applies, line numbers are 7506685's)*

**Files:**
- Create: `.github/workflows/linux.yml` — there is no `.github/` directory at `HEAD`
- Test: none of its own. **The workflow is the test**, and its first run is deliberately RED: `ps2xTest/CMakeLists.txt:113-114` compiles `socom2_hostnet.cpp` into `ps2x_tests`, and that file has no BSD half until Task 3. Task 2 lands the harness and records the exact failure; Task 3's Step 6 turns it green.

**Interfaces:**
- Workflow `Linux`, one job `build-and-test`, `runs-on: ubuntu-24.04`, triggers `push` (every branch) and `pull_request`, `timeout-minutes: 60`, concurrency group `linux-${{ github.ref }}` with `cancel-in-progress: true`.
- Artifacts: `socom-unzipped-launcher-linux` (the launcher binary) and `ps2x-tests-log` (the suite's stdout), both `if: always()` so a red run still uploads its log.

**Steps:**

- [x] **Step 1: Write the workflow.**

```yaml
# Sprint 8 Goal 1 design item 6(a): ring one. ubuntu-24.04 has NO generated game code -- 14,882 files and
# 576 MB produced from the owner's disc, not in the repository -- so this job builds ps2_runtime,
# ps2x_tests, vu1_replay and the launcher only, through scripts/build_linux.sh --no-runner. That is
# exactly the configuration Task 1's PS2X_BUILD_RUNNER skip exists for.
# Watching it: gh run list --branch sprint-8 --limit 3 ; gh run watch <id> --exit-status
#              gh run view <id> --log-failed ; gh run download <id> -n ps2x-tests-log
name: Linux

on:
  push:
  pull_request:

concurrency:
  group: linux-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build-and-test:
    runs-on: ubuntu-24.04
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4

      - name: Install the build and runtime development packages
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \
            build-essential clang lld cmake ninja-build \
            libgl1-mesa-dev libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev libxext-dev \
            libwayland-dev libxkbcommon-dev \
            libasound2-dev libpulse-dev \
            libavcodec-dev libavformat-dev libavutil-dev libswscale-dev libswresample-dev \
            libavfilter-dev libavdevice-dev \
            pkg-config

      - name: Configure and build (no generated code)
        run: scripts/build_linux.sh --no-runner runtime

      - name: Build the test binary
        run: cmake --build third_party/ps2recomp/build-linux --target ps2x_tests vu1_replay -j "$(nproc)"

      # ps2x_tests resolves ps2xRecomp/include/ps2recomp/instructions.h and tests/fixtures/ RELATIVE TO
      # ITS OWN DIRECTORY (build.sh:62); build-linux sits at build-clang's depth so the same relative
      # roots resolve. Running it from anywhere else fails on missing fixtures, not on a defect.
      - name: Run ps2x_tests
        run: |
          cd third_party/ps2recomp/build-linux/ps2xTest
          ./ps2x_tests 2>&1 | tee "$GITHUB_WORKSPACE/ps2x_tests.log"
          exit "${PIPESTATUS[0]}"

      - name: Python suite
        run: python3 -m unittest discover -s tools_py/tests -t .

      - name: Upload the launcher
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: socom-unzipped-launcher-linux
          path: dist-linux/socom_unzipped_launcher
          if-no-files-found: warn

      - name: Upload the test log
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ps2x-tests-log
          path: ps2x_tests.log
          if-no-files-found: warn
```

- [x] **Step 2: Commit, push, and watch the first (RED) run.**

```bash
git commit -m "ci(linux): build and test on ubuntu-24.04 without the generated code

Sprint 8 Goal 1 design item 6(a). scripts/build_linux.sh --no-runner, then ps2x_tests run from
build-linux/ps2xTest (it resolves instructions.h and tests/fixtures relative to its own directory,
build.sh:62). Concurrency group per ref, a 60-minute timeout, the launcher binary and the suite log
uploaded on every run including a failing one. This first run is expected RED: ps2xTest/CMakeLists.txt
:113-114 compiles socom2_hostnet.cpp into ps2x_tests and that file has no BSD half yet (Task 3).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- .github/workflows/linux.yml
git push
gh run list --branch sprint-8 --limit 3
gh run watch <id> --exit-status
```

  Expected: a non-zero exit on the **Build the test binary** step, with this shape (the first three errors clang emits):

```
socom2_hostnet.cpp:36:13: error: unknown type name 'SOCKET'
socom2_hostnet.cpp:36:28: error: use of undeclared identifier 'INVALID_SOCKET'
socom2_hostnet.cpp:56:29: error: use of undeclared identifier 'WSAGetLastError'
```
  Paste the first twenty lines into the ledger — this is Task 3's RED, taken on CI instead of in the VM, which is cheaper and reproducible by anyone. **If the failure lands anywhere else** (apt, the CMake configure, raylib's own X11 detection, a missing `-dev` package, `ps2_runtime` itself), that is a Task 2 defect: fix the workflow and re-watch before moving on. Task 3 assumes the only red is hostnet.

- [x] **Step 3: Record the watch commands** in the workflow's header comment (Step 1 already carries them) and in the ledger: `gh run list --branch sprint-8 --limit 3` for the id and status, `gh run watch <id> --exit-status` to block until it finishes and take the exit code as the verdict, `gh run view <id> --log-failed` when it is red, `gh run download <id> -n ps2x-tests-log` for the suite output without opening a browser. No extra commit — the header already says it.

---

## Task 3 — hostnet's BSD half (spec Design item 2)

*(landed 2026-09-18 by the concurrent implementation slices: f83de4f -- ticked wholesale; the handoff notes' reconciliation rule applies, line numbers are 7506685's)*

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_hostnet.cpp` — the Winsock include block (:3-11), `Entry::s` (:36), `mapError` (:53-67), `parseIp`'s `inet_pton` (:95-101, portable already, confirm), `init` (:168-183), `shutdown` (:185-197), `createSocket` (:199-217), `closeSocket` (:219-227), `bindSocket` (:229-239), `acceptSocket` (:249-272), `connectSocket` (:274-297), `connectStatus` (:299-326), `send`/`recv` (:328-349), `sendTo`/`recvFrom` (:351-380), `localName`/`peerName` (:382-413), `setBlocking` (:416-425), `poll` (:427-449), `readable` (:451-461), `resolve` (:463-481, `getaddrinfo`, portable already), `localIp` (:488-517)
- Test: `third_party/ps2recomp/ps2xTest/src/socom2_libnetb_tests.cpp` (the `SOCOM2Libnetb` case; it already includes `socom2_hostnet.h` at :6 and drives the table at :57-83)
- Read only: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_hostnet.h` (the seventeen-function contract), `third_party/ps2recomp/ps2xTest/CMakeLists.txt:112-115` (why `ps2x_tests` compiles this file at all), `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_libnetb.cpp` (**not modified** — by design it only calls hostnet)

**Interfaces:** the public contract in `socom2_hostnet.h` does not change by one character. What is added is a file-local compat layer at the top of the `.cpp`, used by every call site:

- `using SOCKET = int;` / `constexpr SOCKET INVALID_SOCKET = -1;` on Linux (Windows keeps Winsock's).
- `socklen_compat` — `int` on Windows, `socklen_t` on Linux — for the length out-parameters of `accept`, `recvfrom`, `getsockname`, `getpeername`.
- `int closeSocketHandle(SOCKET)` → `closesocket` / `::close`.
- `int setNonBlocking(SOCKET, bool)` → `ioctlsocket(FIONBIO)` / `fcntl(F_GETFL)`+`fcntl(F_SETFL, O_NONBLOCK)`.
- `int bytesReadable(SOCKET, unsigned long &)` → `ioctlsocket(FIONREAD)` / `ioctl(FIONREAD)`.
- `int lastSocketError()` / `void setLastSocketError(int)` → `WSAGetLastError`/`WSASetLastError` / `errno`.
- `int selectNfds(SOCKET)` → `0` / `(int)s + 1`. **This one is not cosmetic:** Winsock ignores `select`'s first argument, BSD does not, and a `select(0, ...)` on Linux returns 0 forever — `connectStatus` (:313) would report "still connecting" for the life of the process and `poll` (:441) would report no readiness at all, which reads as a silent online hang rather than an error.

**Steps:**

- [x] **Step 1: Write the failing test.** In `socom2_libnetb_tests.cpp`, inside the existing `MiniTest::Case("SOCOM2Libnetb", ...)` body, after the last `tc.Run` (the `PS2X_SOCOM2_SERVER` case ending at :133):

```cpp
        // Sprint 8 Goal 1 design item 2: the host socket table on BOTH platforms. Everything libnetb
        // does to a socket goes through these seven calls, so a loopback datagram that survives them
        // is the port's proof. RED on Linux before the BSD half exists -- the translation unit does
        // not compile there at all (socom2_hostnet.cpp:36 'unknown type name SOCKET').
        tc.Run("hostnet: a UDP socket binds to loopback, sends to itself, reports readable and reads the bytes back", [](TestCase &t)
        {
            using namespace socom2_hostnet;
            t.IsTrue(init(), "hostnet init must succeed on this platform");
            const int rx = createSocket(Proto::Udp);
            const int tx = createSocket(Proto::Udp);
            t.IsTrue(rx >= 0, "a UDP socket must be created");
            t.IsTrue(tx >= 0, "a second UDP socket must be created");
            t.Equals(bindSocket(rx, Endpoint{0x7f000001u, 0u}), 0, "bind to 127.0.0.1:0 must succeed");
            Endpoint local{};
            t.Equals(localName(rx, &local), 0, "localName must report the bound port");
            t.IsTrue(local.port != 0, "the kernel must have chosen a port");
            t.Equals(local.ip, 0x7f000001u, "the bound address must come back as 127.0.0.1 in host order");

            static const char kPayload[] = "linux";
            t.Equals(sendTo(tx, kPayload, sizeof(kPayload), local), static_cast<int>(sizeof(kPayload)),
                     "sendTo must report the whole datagram sent");

            // Non-blocking sockets (createSocket sets FIONBIO/O_NONBLOCK), so wait for the datagram.
            const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            while (readable(rx) <= 0 && std::chrono::steady_clock::now() < deadline)
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
            t.Equals(readable(rx), static_cast<int>(sizeof(kPayload)), "readable must report the datagram's bytes (FIONREAD)");
            t.Equals(poll(rx, 0) & 1, 1, "poll must report the socket readable (select's nfds must be right on BSD)");

            char buf[64] = {};
            Endpoint from{};
            t.Equals(recvFrom(rx, buf, sizeof(buf), &from), static_cast<int>(sizeof(kPayload)),
                     "recvFrom must return the datagram's bytes");
            t.Equals(std::string(buf), std::string(kPayload), "the payload must arrive unchanged");
            t.Equals(from.ip, 0x7f000001u, "the sender must be reported as 127.0.0.1 in host order");

            t.Equals(closeSocket(rx), 0, "closeSocket must succeed");
            t.Equals(closeSocket(tx), 0, "closeSocket must succeed on the second socket");
            t.Equals(closeSocket(rx), -9, "a closed descriptor must be refused, not closed twice");
        });
```

- [x] **Step 2: Run it and watch it fail — on Linux, where the RED lives.** On Windows this case is green the moment it is written (Winsock already does all of this); say so plainly in the ledger rather than pretending otherwise. The RED is the CI run Task 2 Step 2 already recorded, re-taken now that the case exists:

```bash
git commit -m "test(hostnet): a loopback UDP round trip through the host socket table (RED on Linux)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- third_party/ps2recomp/ps2xTest/src/socom2_libnetb_tests.cpp
git push && gh run list --branch sprint-8 --limit 1 && gh run watch <id> --exit-status
```
  Expected: still red on **Build the test binary**, still

```
socom2_hostnet.cpp:36:13: error: unknown type name 'SOCKET'
```
  and on Windows `./build.sh test` exit 0 with the suite one case larger (550) and the new case passing. Both numbers go in the ledger; the Windows green is what says the case is a correct statement of the contract, and the Linux red is what says the contract is unimplemented there.

- [x] **Step 3: The compat block.** Replace `socom2_hostnet.cpp:3-11` with:

```cpp
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#define NOGDI
#define NOUSER
#include <winsock2.h>
#include <ws2tcpip.h>
#else
// Sprint 8 Goal 1 design item 2: the BSD half. Same seventeen functions, same descriptors, same
// negative errno-style returns -- only the primitives differ, and they differ in exactly the six
// ways named below. socom2_libnetb.cpp is untouched by design: it only ever calls this file.
#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
#include <cerrno>
using SOCKET = int;
constexpr SOCKET INVALID_SOCKET = -1;
#endif
```

  and add, inside the existing anonymous namespace (before `Entry` at :33):

```cpp
#ifdef _WIN32
        using socklen_compat = int;
        inline int closeSocketHandle(SOCKET s) { return ::closesocket(s); }
        inline int setNonBlocking(SOCKET s, bool nonBlocking)
        {
            u_long v = nonBlocking ? 1u : 0u;
            return ::ioctlsocket(s, FIONBIO, &v);
        }
        inline int bytesReadable(SOCKET s, unsigned long &out) { return ::ioctlsocket(s, FIONREAD, &out); }
        inline int lastSocketError() { return WSAGetLastError(); }
        inline void setLastSocketError(int e) { WSASetLastError(e); }
        // Winsock IGNORES select()'s first argument; BSD needs the highest descriptor plus one, and a
        // select(0, ...) there returns 0 forever -- connectStatus would report "connecting" for the
        // life of the process and poll would never see a readable socket. Silent online hang, not an error.
        inline int selectNfds(SOCKET) { return 0; }
        inline bool wouldBlockOrInProgress(int e)
        {
            return e == WSAEWOULDBLOCK || e == WSAEINPROGRESS || e == WSAEALREADY;
        }
#else
        using socklen_compat = socklen_t;
        inline int closeSocketHandle(SOCKET s) { return ::close(s); }
        inline int setNonBlocking(SOCKET s, bool nonBlocking)
        {
            const int flags = ::fcntl(s, F_GETFL, 0);
            if (flags < 0)
                return -1;
            return ::fcntl(s, F_SETFL, nonBlocking ? (flags | O_NONBLOCK) : (flags & ~O_NONBLOCK));
        }
        inline int bytesReadable(SOCKET s, unsigned long &out)
        {
            int n = 0;
            const int r = ::ioctl(s, FIONREAD, &n);
            out = static_cast<unsigned long>(n < 0 ? 0 : n);
            return r;
        }
        inline int lastSocketError() { return errno; }
        inline void setLastSocketError(int e) { errno = e; }
        inline int selectNfds(SOCKET s) { return static_cast<int>(s) + 1; }
        inline bool wouldBlockOrInProgress(int e)
        {
            return e == EWOULDBLOCK || e == EAGAIN || e == EINPROGRESS || e == EALREADY;
        }
#endif
```

- [x] **Step 4: `mapError` gets its two switch bodies** (:53-67). The returned values — the guest-visible negative errnos — are identical on both sides; only the names of the constants being matched change, which is why the two bodies cannot be collapsed:

```cpp
        int mapError()
        {
            const int e = lastSocketError();
#ifdef _WIN32
            switch (e)
            {
            case WSAEWOULDBLOCK: return -11;      // EAGAIN
            case WSAEINPROGRESS: return -115;     // EINPROGRESS
            case WSAECONNREFUSED: return -111;
            case WSAETIMEDOUT: return -110;
            case WSAEHOSTUNREACH: return -113;
            case WSAENOTCONN: return -107;
            case WSAECONNRESET: return -104;
            case WSAEADDRINUSE: return -98;
            default: return -5;                   // EIO
            }
#else
            // The same guest-visible numbers. They ARE Linux's own errno values (the guest's inet
            // stack speaks Linux errnos), so this arm is nearly an identity -- written out rather
            // than returned as -e so an unexpected errno still maps to -5 (EIO) exactly as on Windows.
            switch (e)
            {
            case EWOULDBLOCK: return -11;         // == EAGAIN on Linux
            case EINPROGRESS: return -115;
            case ECONNREFUSED: return -111;
            case ETIMEDOUT: return -110;
            case EHOSTUNREACH: return -113;
            case ENOTCONN: return -107;
            case ECONNRESET: return -104;
            case EADDRINUSE: return -98;
            default: return -5;                   // EIO
            }
#endif
        }
```

- [x] **Step 5: The call sites, one by one.** Each is a named line, not a sweep — a subagent brief for this step lists them and the exact replacement, and the verification command is Step 6's.

  1. `init` :173-180 — the `WSADATA`/`WSAStartup` pair and its failure return go under `#ifdef _WIN32`; the `#else` arm does nothing (BSD sockets need no start-up) and cannot fail. `loadHosts()` and `g_initialized` stay outside the guard. The banner at :181 keeps its exact Windows text and gains a Linux twin under the same guard: `"[socom2/hostnet] Winsock ready; retail hostnames -> "` / `"[socom2/hostnet] BSD sockets ready; retail hostnames -> "`. **Do not unify the two strings**: the Windows line is in every run log on record.
  2. `shutdown` :191, :195 — `closesocket(e.s)` → `closeSocketHandle(e.s)`; `WSACleanup()` under `#ifdef _WIN32`.
  3. `createSocket` :206-211 — `::socket(...)` is already portable; `if (s == INVALID_SOCKET)` now compares against the compat constant; the `u_long nb = 1; ioctlsocket(s, FIONBIO, &nb);` pair becomes `setNonBlocking(s, true);`.
  4. `closeSocket` :224 — `closesocket(e->s)` → `closeSocketHandle(e->s)`.
  5. `bindSocket` :238 — unchanged; `sizeof(a)` is accepted as `socklen_t` on both.
  6. `acceptSocket` :257-272 — `int len` → `socklen_compat len`; the `u_long`/`ioctlsocket` pair at :265-266 → `setNonBlocking(s, true);`; `closesocket(s)` at :272 → `closeSocketHandle(s)`.
  7. `connectSocket` :288-295 — `const int err = WSAGetLastError();` → `lastSocketError()`; the three-constant test at :291 → `wouldBlockOrInProgress(err)`.
  8. `connectStatus` :313-322 — `::select(0, ...)` → `::select(selectNfds(e->s), ...)`; `int len = sizeof(err)` → `socklen_compat len`; the `char *` cast on `getsockopt`'s value pointer becomes `reinterpret_cast<char *>(&err)` on Windows and `&err` on Linux — write it once as `reinterpret_cast<char *>(&err)`, which POSIX accepts through its `void *` parameter; `WSASetLastError(err)` → `setLastSocketError(err)`.
  9. `send`/`recv` :335, :345 — the `static_cast<const char *>` / `static_cast<char *>` casts and the `static_cast<int>(size)` length are valid on both (POSIX takes `void *` and `size_t`); leave them. The return type is `ssize_t` on Linux, so store into `const auto n` and compare `n >= 0`, then `static_cast<int>(n)`.
  10. `sendTo`/`recvFrom` :358, :371-374 — same `auto n`; `int len = sizeof(a)` → `socklen_compat len`.
  11. `localName`/`peerName` :390, :407 — `int len = sizeof(a)` → `socklen_compat len`.
  12. `setBlocking` :422-424 — the `u_long`/`ioctlsocket` pair → `return setNonBlocking(e->s, !blocking) == 0 ? 0 : mapError();`, with `e->blocking = blocking;` kept before it.
  13. `poll` :441 — `::select(0, ...)` → `::select(selectNfds(e->s), ...)`.
  14. `readable` :457-458 — `u_long n = 0; if (ioctlsocket(e->s, FIONREAD, &n) != 0)` → `unsigned long n = 0; if (bytesReadable(e->s, n) != 0)`.
  15. `localIp` :500-515 — `INVALID_SOCKET` compare is now the compat constant; `int len = sizeof(l)` → `socklen_compat len`; `closesocket(s)` → `closeSocketHandle(s)`.
  16. `resolve` :471-480 — `getaddrinfo`/`freeaddrinfo` are portable; no change. Confirm and record.
  17. `parseIp` :95-101 — `inet_pton` is portable (`<arpa/inet.h>` on Linux, `ws2tcpip.h` on Windows); no change. Confirm and record.

- [x] **Step 6: Green on both.** CI first, because it is the cheap side:

```bash
git push && gh run list --branch sprint-8 --limit 1 && gh run watch <id> --exit-status
```
  Expected: the run passes end to end, `ps2x_tests` reporting `Total Tests: 550` and `Failed: 0`, and the **Upload the launcher** step attaching `socom_unzipped_launcher`. Then the host:

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "T3: build.sh test" -- ./build.sh test
sha256sum -c /tmp/dist_before.txt
```
  Expected: exit 0, 550 cases, and `dist/socom2.exe: OK` — the Windows binary must still hash exactly as it did before Task 1, because every edit in this task is inside `#ifdef`/inline forwarders whose Windows expansion is the call that was there.

- [x] **Step 7: Commit** (record the compat-layer choice as ruling **R99**).

```bash
git commit -m "feat(hostnet): the BSD half of the host socket table

Sprint 8 Goal 1 design item 2. socom2_hostnet.cpp had no non-Windows branch at all (winsock2.h at :3-11,
SOCKET at :36, WSAGetLastError at :56, WSAStartup at :174, closesocket at :191/:224/:272/:515,
ioctlsocket FIONBIO at :211/:266/:424, FIONREAD at :458), so neither the runner nor ps2x_tests could
compile on Linux. The same seventeen functions now run on BSD sockets through a file-local compat layer:
SOCKET is int, closesocket is close, ioctlsocket(FIONBIO) is fcntl(O_NONBLOCK), FIONREAD is ioctl,
WSAGetLastError is errno, WSAStartup/WSACleanup are nothing, and select() gets a real nfds -- Winsock
ignores that argument and BSD does not, so select(0,...) would have reported 'still connecting' forever
in connectStatus and no readiness at all in poll: a silent online hang rather than an error.
socom2_libnetb.cpp is untouched by design; it only calls this file.
RED first: 'hostnet: a UDP socket binds to loopback, sends to itself, reports readable and reads the
bytes back' in socom2_libnetb_tests.cpp -- green on Windows the day it was written (Winsock already did
all of it) and red on Linux with 'unknown type name SOCKET' until this commit. Now green on both:
CI run <id> 550/550, ./build.sh test 550/550, dist/socom2.exe sha256 unchanged.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/src/lib/socom2_hostnet.cpp \
  third_party/ps2recomp/ps2xTest/src/socom2_libnetb_tests.cpp
git push
```

---

## Task 4 — The launcher's POSIX glue (spec Design item 4)

*(landed 2026-09-18: fcd3ea2 -- posix_spawn glue, mergeEnvironment shared and tested on Windows; the POSIX bodies run first in CI and the VM; R100's GameProcess shape adopted)*

**Files:**
- Modify: `third_party/ps2recomp/ps2xLauncher/src/posix_glue.cpp` (Task 1's stub, filled in), `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h` (:77, the declaration goes beside `environmentFor`), `third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp` (:285-320, beside `environmentFor`), `third_party/ps2recomp/ps2xTest/CMakeLists.txt` (after :124, the UNIX sources), `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp` (the `Launcher` case)
- Read only: `third_party/ps2recomp/ps2xLauncher/src/win32_glue.h` (:9-32, the contract), `third_party/ps2recomp/ps2xLauncher/src/win32_glue.cpp` (:18-207, the Windows body this mirrors — the environment merge at :126-159, the log at :160-169, the child at :170-191)

**Interfaces:**
- `std::vector<std::string> launcher::mergeEnvironment(const char *const *base, const std::vector<std::string> &ours)` — the pure piece, in `launcher_config.cpp` so **both** platforms can share it. `base` is a `nullptr`-terminated array of `KEY=VALUE` strings (`environ` on Linux; Windows can adopt it later, which is why it lives here and not in the glue). Result: every entry of `base` whose `KEY` is not a key of `ours`, in `base`'s order, followed by all of `ours` in their order. A `base` entry with no `=` keeps its whole text as the key. A `base` entry whose first character is `=` is dropped (Windows' hidden `=C:=…` drive-cursor variables; harmless to apply on Linux, where they do not occur). `base == nullptr` yields exactly `ours`.
- `win32glue::GameProcess` on Linux stores the child in the header's two existing `void *` members: `process` holds `pid + 1` (so `nullptr` still means "no child") and `log` holds `1 + the reaped exit status`, or `nullptr` while the child is alive. No field is added — the struct's Windows layout must not change.

**Steps:**

- [x] **Step 1: Write the failing C++ tests.** In `launcher_tests.cpp`, inside the `Launcher` case. First the shared one, which runs on both platforms:

```cpp
        // Sprint 8 Goal 1 design item 4: the child's environment is the current block plus our knobs,
        // OURS WINNING. win32_glue.cpp:126-159 does this inline with GetEnvironmentStringsW; the Linux
        // glue needs the same rule over `environ`, so the rule itself moves into launcher_config.cpp
        // where one test covers both and Windows can adopt it later.
        tc.Run("mergeEnvironment keeps the base block, drops what we override, and appends ours last", [](TestCase &t)
        {
            const char *base[] = {"PATH=/usr/bin", "PS2X_GS_SCALE=9", "HOME=/home/socom", "ODD", "=C:=X:\\here", nullptr};
            const std::vector<std::string> ours = {"PS2X_GS_SCALE=1", "PS2X_SOCOM2_PAD=1"};
            const std::vector<std::string> merged = launcher::mergeEnvironment(base, ours);
            t.Equals(merged.size(), static_cast<size_t>(5), "PATH, HOME, ODD and our two -- the overridden PS2X_GS_SCALE=9 and the '=' entry are gone");
            t.Equals(merged[0], std::string("PATH=/usr/bin"), "the base block keeps its order");
            t.Equals(merged[1], std::string("HOME=/home/socom"), "PS2X_GS_SCALE=9 is dropped because we set it");
            t.Equals(merged[2], std::string("ODD"), "an entry with no '=' is kept whole");
            t.Equals(merged[3], std::string("PS2X_GS_SCALE=1"), "ours come last, so they are what the child reads");
            t.Equals(merged[4], std::string("PS2X_SOCOM2_PAD=1"), "and all of ours are there");
            const std::vector<std::string> none = launcher::mergeEnvironment(nullptr, ours);
            t.Equals(none.size(), static_cast<size_t>(2), "a null base block yields exactly our own knobs");
            t.Equals(none[0], std::string("PS2X_GS_SCALE=1"), "... in order");
        });
```

  Then the two Linux-only ones, guarded so Windows is untouched:

```cpp
#ifndef _WIN32
        // The POSIX glue. Only the two halves that can be asserted without starting a game: the refusal
        // path (which must NAME the path it looked at, because 'it did nothing' is the failure a player
        // reports) and exeDirectory. Starting a real child is Task 11's launcher run under X.
        tc.Run("startGame on a directory with no socom2 returns false and names the path it looked for", [](TestCase &t)
        {
            win32glue::GameProcess game;
            const launcher::Config cfg;
            const bool ok = win32glue::startGame("/nonexistent/socom-unzipped", cfg, game);
            t.IsFalse(ok, "there is no socom2 there, so startGame must refuse");
            t.IsTrue(game.error.find("/nonexistent/socom-unzipped/socom2") != std::string::npos,
                     "the message must name the exact path it looked for, not just 'socom2 is missing'");
            t.IsFalse(game.running(), "a refused start leaves no child behind");
            t.Equals(game.exitCode(), 0, "and no exit code");
        });

        tc.Run("exeDirectory is a directory that exists", [](TestCase &t)
        {
            const std::string dir = win32glue::exeDirectory();
            t.IsTrue(!dir.empty(), "exeDirectory must not be empty");
            std::error_code ec;
            t.IsTrue(std::filesystem::is_directory(dir, ec), "exeDirectory must be a directory that exists");
            t.IsTrue(dir[0] == '/', "on Linux it is absolute (/proc/self/exe is)");
        });
#endif
```

  Add `#include "win32_glue.h"` and `#include <filesystem>` to `launcher_tests.cpp`'s include block (:1-15) — the first under `#ifndef _WIN32` is not needed, the header itself is portable.

- [x] **Step 2: Teach `ps2x_tests` about the glue on UNIX.** In `ps2xTest/CMakeLists.txt`, after :124:

```cmake
# Sprint 8 Goal 1 Task 4: launcher_tests.cpp drives win32glue's POSIX half directly. The glue is not in
# ps2x_launcher_core (it is the launcher exe's own platform layer, and on Windows it pulls in windows.h,
# which raylib and this test binary must not see), so it is attached here, UNIX only.
if(UNIX)
    target_sources(ps2x_tests PRIVATE ${CMAKE_SOURCE_DIR}/ps2xLauncher/src/posix_glue.cpp)
    target_include_directories(ps2x_tests PRIVATE ${CMAKE_SOURCE_DIR}/ps2xLauncher/src)
endif()
target_include_directories(ps2_test_lib PRIVATE ${CMAKE_SOURCE_DIR}/ps2xLauncher/src)
```
  The last line is unconditional because `launcher_tests.cpp` (compiled into `ps2_test_lib`) now includes `win32_glue.h`, which lives in `ps2xLauncher/src/` on both platforms. On Windows `win32_glue.cpp` is not added here — nothing in the Windows test binary calls the glue, and the `#ifndef _WIN32` guard means nothing tries.

- [x] **Step 3: Run the tests and watch them fail.**

```bash
# Windows (the shared case only; the guarded two do not exist there)
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | tail -20
# Linux, via CI
git push && gh run watch <id> --exit-status
```
  Expected on Windows: a **link** error, `undefined reference to 'launcher::mergeEnvironment(char const* const*, std::vector<std::string...> const&)'`. Expected on Linux: the same link error, and — once `mergeEnvironment` exists but the glue is still Task 1's stub — two assertion failures naming their messages: `the message must name the exact path it looked for, not just 'socom2 is missing'` (the stub says `launching is not implemented on this platform yet`) and, if the test binary is run from a directory that is not the build tree, `on Linux it is absolute (/proc/self/exe is)`. Both are the RED this task closes.

- [x] **Step 4: Implement `mergeEnvironment`** in `launcher_config.cpp`, next to `environmentFor` (after :320), declared in `launcher_config.h` beside :77:

```cpp
    std::vector<std::string> mergeEnvironment(const char *const *base, const std::vector<std::string> &ours)
    {
        std::vector<std::string> merged;
        for (const char *const *p = base; p && *p; ++p)
        {
            const std::string entry(*p);
            // Windows keeps hidden "=C:=C:\path" drive cursors in its block; they are not variables.
            if (entry.empty() || entry[0] == '=')
                continue;
            const size_t eq = entry.find('=');
            const std::string key = eq == std::string::npos ? entry : entry.substr(0, eq);
            bool overridden = false;
            for (const std::string &o : ours)
                if (o.rfind(key + "=", 0) == 0)
                    overridden = true;
            if (!overridden && !key.empty())
                merged.push_back(entry);
        }
        merged.insert(merged.end(), ours.begin(), ours.end());
        return merged;
    }
```

- [x] **Step 5: Implement `posix_glue.cpp`.** Replace Task 1's stub body. The choice that needs stating, and does so in the file: **`posix_spawn`, not `fork`+`exec`.**

```cpp
// Sprint 8 Goal 1 design item 4: the launcher's POSIX half -- the same win32glue interface, on POSIX
// primitives. win32_glue.cpp is the Windows twin and is #ifdef'd out here, so exactly one of the two
// defines these symbols per platform.
//
// posix_spawn, not fork()+exec(): the launcher is a raylib window with a live GL context and miniaudio's
// capture thread (mic_devices.cpp). fork() in a multithreaded process copies only the calling thread and
// inherits every lock another thread happened to hold -- the classic malloc deadlock between fork and
// exec -- and a forked GL context is undefined besides. posix_spawn is the one call that has no such
// window. Its cost is that changing the child's directory needs a glibc extension: addchdir_np exists
// from glibc 2.29 (Ubuntu 20.04; 24.04 ships 2.39), and where it is absent -- musl, an ancient glibc --
// the #else arm falls back to fork+chdir+execv and accepts the risk, because a launcher that cannot
// start the game at all is worse than one that rarely deadlocks on an unsupported libc. The child's
// working directory is not optional: the game resolves cards/ and logs/ relative to it.
#ifndef _WIN32
#include "win32_glue.h"

#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <spawn.h>
#include <string>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

extern char **environ;

namespace fs = std::filesystem;

namespace
{
    pid_t pidOf(const win32glue::GameProcess &g)
    {
        return g.process ? static_cast<pid_t>(reinterpret_cast<intptr_t>(g.process) - 1) : 0;
    }

    void setPid(win32glue::GameProcess &g, pid_t pid)
    {
        g.process = reinterpret_cast<void *>(static_cast<intptr_t>(pid) + 1);
    }

    bool hasLatchedStatus(const win32glue::GameProcess &g) { return g.log != nullptr; }
    int latchedStatus(const win32glue::GameProcess &g)
    {
        return static_cast<int>(reinterpret_cast<intptr_t>(g.log) - 1);
    }
    void latchStatus(win32glue::GameProcess &g, int code)
    {
        g.log = reinterpret_cast<void *>(static_cast<intptr_t>(code) + 1);
    }

    // waitpid(WNOHANG) once; latches the exit code the first time the child is reaped. Returns true
    // while the child is still running.
    bool poll(win32glue::GameProcess &g)
    {
        const pid_t pid = pidOf(g);
        if (pid <= 0 || hasLatchedStatus(g))
            return false;
        int status = 0;
        const pid_t r = ::waitpid(pid, &status, WNOHANG);
        if (r == 0)
            return true;                      // still running
        if (r < 0)
        {
            latchStatus(g, 0);                // already reaped or not ours; nothing more to learn
            return false;
        }
        latchStatus(g, WIFEXITED(status) ? WEXITSTATUS(status)
                                         : (WIFSIGNALED(status) ? 128 + WTERMSIG(status) : 0));
        return false;
    }

    bool haveCommand(const char *name)
    {
        const std::string probe = std::string("command -v ") + name + " >/dev/null 2>&1";
        return std::system(probe.c_str()) == 0;
    }
}

namespace win32glue
{
    std::string exeDirectory()
    {
        char buf[4096];
        const ssize_t n = ::readlink("/proc/self/exe", buf, sizeof(buf) - 1);
        if (n > 0)
        {
            buf[n] = '\0';
            return fs::path(buf).parent_path().string();
        }
        return fs::current_path().string();
    }

    std::string browseForIso()
    {
        // zenity when it is installed; otherwise nothing, and the player types the path (the field
        // already accepts typing). No GTK dependency is linked into the launcher for this.
        if (!haveCommand("zenity"))
            return {};
        FILE *p = ::popen("zenity --file-selection --title='Choose the SOCOM II ISO' "
                          "--file-filter='Disc images | *.iso *.bin' --file-filter='All files | *' 2>/dev/null",
                          "r");
        if (!p)
            return {};
        char line[4096] = {};
        const char *got = std::fgets(line, sizeof(line), p);
        const int rc = ::pclose(p);
        if (!got || rc != 0)
            return {};
        std::string path(line);
        while (!path.empty() && (path.back() == '\n' || path.back() == '\r'))
            path.pop_back();
        return path;
    }

    void openFolder(const std::string &path)
    {
        if (!haveCommand("xdg-open"))
            return;
        pid_t pid = 0;
        const char *argv[] = {"xdg-open", path.c_str(), nullptr};
        if (::posix_spawnp(&pid, "xdg-open", nullptr, nullptr, const_cast<char *const *>(argv), environ) == 0)
            ::waitpid(pid, nullptr, WNOHANG);   // do not block the UI thread; the reap is best-effort
    }

    std::string stamp()
    {
        char buf[32];
        const std::time_t t = std::time(nullptr);
        std::tm tm{};
        ::localtime_r(&t, &tm);
        std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &tm);
        return buf;
    }

    bool GameProcess::running() const { return poll(const_cast<GameProcess &>(*this)); }

    int GameProcess::exitCode() const
    {
        GameProcess &self = const_cast<GameProcess &>(*this);
        if (poll(self))
            return 0;                            // still running: the Windows half returns 0 too
        return hasLatchedStatus(self) ? latchedStatus(self) : 0;
    }

    void GameProcess::close()
    {
        poll(*this);
        process = nullptr;
        log = nullptr;
    }

    bool startGame(const std::string &dirStr, const launcher::Config &config, GameProcess &out)
    {
        out.error.clear();
        const fs::path dir(dirStr);
        const fs::path exe = dir / "socom2";          // no .exe
        const fs::path elf = dir / "socom2_game.elf";
        if (!fs::exists(exe))
        {
            out.error = "socom2 is not next to the launcher (" + exe.string() + ")";
            return false;
        }
        if (!fs::exists(elf))
        {
            out.error = "socom2_game.elf is not next to the launcher (" + elf.string() + ")";
            return false;
        }
        std::error_code ec;
        fs::create_directories(dir / "logs", ec);
        fs::create_directories(dir / "cards", ec);

        const std::vector<std::string> merged =
            launcher::mergeEnvironment(environ, launcher::environmentFor(config));
        std::vector<char *> envp;
        envp.reserve(merged.size() + 1);
        for (const std::string &m : merged)
            envp.push_back(const_cast<char *>(m.c_str()));
        envp.push_back(nullptr);

        out.logPath = (dir / "logs" / ("run_" + stamp() + ".log")).string();

        posix_spawn_file_actions_t actions;
        ::posix_spawn_file_actions_init(&actions);
        ::posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO, out.logPath.c_str(),
                                           O_WRONLY | O_CREAT | O_TRUNC, 0644);
        ::posix_spawn_file_actions_adddup2(&actions, STDOUT_FILENO, STDERR_FILENO);
#if defined(__GLIBC__) && defined(__GLIBC_PREREQ)
#if __GLIBC_PREREQ(2, 29)
#define PS2X_HAVE_SPAWN_CHDIR 1
#endif
#endif
#ifdef PS2X_HAVE_SPAWN_CHDIR
        ::posix_spawn_file_actions_addchdir_np(&actions, dir.c_str());
#endif
        const std::string exeStr = exe.string();
        const std::string elfStr = elf.string();
        const char *argv[] = {exeStr.c_str(), elfStr.c_str(), nullptr};
        pid_t pid = 0;
        int rc = 0;
#ifdef PS2X_HAVE_SPAWN_CHDIR
        rc = ::posix_spawn(&pid, exeStr.c_str(), &actions, nullptr,
                           const_cast<char *const *>(argv), envp.data());
#else
        // No addchdir_np: fork+chdir+execv. Accepted risk, stated in the file header.
        pid = ::fork();
        if (pid == 0)
        {
            const int fd = ::open(out.logPath.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
            if (fd >= 0) { ::dup2(fd, STDOUT_FILENO); ::dup2(fd, STDERR_FILENO); ::close(fd); }
            if (::chdir(dir.c_str()) != 0)
                ::_exit(127);
            ::execve(exeStr.c_str(), const_cast<char *const *>(argv), envp.data());
            ::_exit(127);
        }
        rc = pid < 0 ? errno : 0;
#endif
        ::posix_spawn_file_actions_destroy(&actions);
        if (rc != 0 || pid <= 0)
        {
            out.error = "could not start " + exeStr + " (" + std::strerror(rc ? rc : errno) + ")";
            return false;
        }
        setPid(out, pid);
        out.log = nullptr;      // no latched status yet: the child is alive
        return true;
    }

    void terminate(GameProcess &game)
    {
        const pid_t pid = pidOf(game);
        if (pid <= 0)
            return;
        ::kill(pid, SIGTERM);
        for (int i = 0; i < 200; ++i)           // 2 s in 10 ms steps
        {
            if (!poll(game))
                return;
            ::usleep(10 * 1000);
        }
        ::kill(pid, SIGKILL);
        poll(game);
    }
}
#endif // !_WIN32
```
  `<fcntl.h>` and `<cerrno>` belong in the include list above; add them. Note what this deliberately does **not** do: it never writes to `game.log` as a file handle (there is no handle to keep — the child owns the fd), which is why `log` is free to carry the latched status.

- [x] **Step 6: Green on both.**

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "T4: build.sh test" -- ./build.sh test
git push && gh run watch <id> --exit-status
```
  Expected: Windows 551 cases (the shared `mergeEnvironment` case only), 0 failed, `dist/` hashes unchanged; CI 553 cases (the shared one plus the two guarded), 0 failed, and the `socom-unzipped-launcher-linux` artifact attached.

- [x] **Step 7: Commit** (record the `GameProcess` field reuse as ruling **R100**).

```bash
git commit -m "feat(launcher): the POSIX half of win32glue

Sprint 8 Goal 1 design item 4. posix_glue.cpp implements every function of win32_glue.h on POSIX:
exeDirectory from readlink(/proc/self/exe); startGame through posix_spawn with the merged environment
(environ plus environmentFor, ours winning), file actions opening dir/logs/run_<stamp>.log on fd 1 and
dup2'ing it to fd 2, the child dir/socom2 with argv {exe, dir/socom2_game.elf} and the working directory
set with addchdir_np; running/exitCode/close on waitpid(WNOHANG)/WEXITSTATUS; terminate SIGTERM then
SIGKILL after 2 s; browseForIso through zenity when it is installed and otherwise the typed path;
openFolder through xdg-open; stamp from localtime_r.
posix_spawn rather than fork+exec because the launcher holds a GL context and miniaudio's capture thread,
and fork() there inherits whatever lock another thread was holding; the file says so. Where addchdir_np
is absent (pre-2.29 glibc, musl) the #else arm forks -- the child's working directory is not optional,
the game resolves cards/ and logs/ from it.
RED first: 'mergeEnvironment keeps the base block, drops what we override, and appends ours last' (both
platforms, and the rule now lives in launcher_config.cpp so Windows can adopt it later), plus two
#ifndef _WIN32 cases -- startGame on a missing exe must NAME the path, exeDirectory must be a directory
that exists. Windows untouched: 551/551, dist/ sha256 unchanged. CI 553/553.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xLauncher/src/posix_glue.cpp \
  third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h \
  third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp \
  third_party/ps2recomp/ps2xTest/CMakeLists.txt \
  third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp
git push
```

---

## Task 5 — The crash handler, the host PC sampler and the thread times on Linux (spec Design item 3)

*(landed 2026-09-18 by the concurrent implementation slices: a3d9269 + 247214f -- ticked wholesale; the handoff notes' reconciliation rule applies, line numbers are 7506685's)*

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/host_prof_line.h`, `third_party/ps2recomp/ps2xRuntime/include/runtime/cpu_time_ms.h`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` (:29-30 the include block, :869-913 the crash handler, :1634-1640 `installCrashHandler`, :1707-1919 `ps2HostProfStart`), `third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp` (:26-27 the include, :2834-2864 the `[vu1-stats]` thread and process times)
- Test: `third_party/ps2recomp/ps2xTest/src/host_config_tests.cpp` (the two shared formatters), `tools_py/tests/test_freeze_trace.py` (the `[pc-sampler]` line's fields)
- Read only: `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` (:662-697, the **guest** pc sampler — portable `std::thread` already, not touched by this task), `third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_freeze_fields.h` (`FreezeFields::line`), `tools_py/parity/freeze_trace.py` (:74-127, the parser), `tools_py/hostprof_symbolize.py` (the consumer of `logs/hostprof.txt`), `third_party/ps2recomp/ps2xTest/src/socom2_link_stubs.cpp:15` (`ps2HostProfStart` is stubbed for the test binary, so this task's Linux arm is not exercised by `ps2x_tests`)

**Interfaces:**
- `namespace HostProfLine { std::string format(uint64_t addr, uint32_t count, uint64_t exeBase, const char *moduleName, uint64_t moduleBase); }` — one line of `logs/hostprof.txt`. When `moduleName == nullptr` the address is in the exe and the line is `"<addr - exeBase in hex> <count>"`; otherwise it is `"<addr in hex> <count> ext <moduleName>+0x<addr - moduleBase in hex>"`. `moduleName` is taken as its last path component (`\` or `/`), which is what the Windows body does at :1868-1869 and what `dladdr`'s `dli_fname` needs on Linux. Both platforms call it, so `hostprof_symbolize.py` reads one format.
- `namespace CpuTimeMs { double perSecond(uint64_t nowNs, uint64_t prevNs, double seconds); }` — the `[vu1-stats]` `thread=`/`proc=` columns: `(nowNs - prevNs) / 1e6 / seconds`, and `0.0` when `seconds <= 0` or `nowNs < prevNs` (the first sample, and a counter that went backwards). Windows converts its two `FILETIME`s (100 ns units) to ns before calling; Linux converts its `timespec`.
- Crash handler on Linux: `sigaction` with `SA_SIGINFO` on `SIGSEGV`, `SIGBUS`, `SIGILL`, `SIGFPE`; the handler prints the same `[crash]` sentence the vectored handler prints (`code=`, `host=`, `module+`, `access=`/`at`, then the guest line from `g_runtimeForCrash`), with the module base from `dladdr` on the handler's own address, and re-raises with the default disposition so the process still dies with the right signal.
- Host sampler on Linux: `timer_create(CLOCK_MONOTONIC, SIGEV_THREAD_ID -> SIGPROF)` armed on the EE thread's tid, whose handler reads `ucontext_t`'s `uc_mcontext.gregs[REG_RIP]` and stores it into the **same** `std::unordered_map<uint64_t,uint32_t>` histogram the Windows sampler fills, guarded by an atomic spin flag (the handler runs on the sampled thread, so it may not allocate; it writes into a fixed 64 K-entry ring of raw addresses that the dump thread folds into the map).

**Steps:**

- [x] **Step 1: Write the failing C++ tests.** In `host_config_tests.cpp`:

```cpp
        // Sprint 8 Goal 1 design item 3: the PS2X_HOST_PROF histogram must read identically on both
        // platforms, because tools_py/hostprof_symbolize.py is the one consumer and it has no idea
        // which machine wrote the file. Windows builds these lines inline at game_overrides_socom2.cpp
        // :1857-1872; the Linux SIGPROF sampler writes the same file, so the format moves into a header
        // both call and this case is what pins it.
        tc.Run("host-prof lines: an in-exe address is an RVA, an external one names its module and offset", [](TestCase &t)
        {
            t.Equals(HostProfLine::format(0x140001234ull, 7u, 0x140000000ull, nullptr, 0ull),
                     std::string("1234 7"), "in the exe: rva then count, hex rva, decimal count");
            t.Equals(HostProfLine::format(0x7ffb00000040ull, 3u, 0x140000000ull, "C:\\Windows\\System32\\opengl32.dll", 0x7ffb00000000ull),
                     std::string("7ffb00000040 3 ext opengl32.dll+0x40"),
                     "outside the exe: absolute address, count, then the module's BASENAME and the offset");
            t.Equals(HostProfLine::format(0x7f2200000040ull, 3u, 0x400000ull, "/usr/lib/x86_64-linux-gnu/libGLX_mesa.so.0", 0x7f2200000000ull),
                     std::string("7f2200000040 3 ext libGLX_mesa.so.0+0x40"),
                     "a POSIX path is reduced to its basename by the same rule, so one parser reads both");
            t.Equals(HostProfLine::format(0x1000ull, 1u, 0x2000ull, nullptr, 0ull),
                     std::string("1000 1"), "an in-exe address below the base is printed raw, never as a negative rva");
        });

        // The [vu1-stats] thread=/proc= columns. Windows reads two FILETIMEs (100 ns units,
        // ps2_vu1_core.cpp :2835-2854); Linux reads clock_gettime(CLOCK_THREAD_CPUTIME_ID). Both hand
        // nanoseconds to this, so the number on the line means the same thing on either machine.
        tc.Run("cpu-time columns: nanoseconds of CPU per wall second, and zero on the first sample", [](TestCase &t)
        {
            t.Equals(CpuTimeMs::perSecond(2000000000ull, 1000000000ull, 1.0), 1000.0, "1 s of CPU in 1 wall second is 1000 ms/s");
            t.Equals(CpuTimeMs::perSecond(1500000000ull, 1000000000ull, 2.0), 250.0, "0.5 s of CPU over 2 wall seconds is 250 ms/s");
            t.Equals(CpuTimeMs::perSecond(1000000000ull, 0ull, 0.0), 0.0, "a zero wall interval is 0, not a division by zero");
            t.Equals(CpuTimeMs::perSecond(1000000000ull, 2000000000ull, 1.0), 0.0, "a counter that went backwards is 0, not a huge negative");
        });
```

  And in `tools_py/tests/test_freeze_trace.py`, the Python half the brief asks for — a format-contract pin rather than a tautology, because the `[pc-sampler]` line itself is emitted by portable code (`game_overrides_socom2.cpp:662-697`, `std::thread` and `FreezeFields::line`) and therefore *must* be byte-identical on both platforms. What this case catches is the thing that could break it: a Linux `#else` arm that drops or reorders a field:

```python
class SamplerLineIsPlatformBlind(unittest.TestCase):
    """Sprint 8 Goal 1 design item 3: the [pc-sampler] line is written by portable code and read by one
    parser, so a Linux build must produce a line freeze_trace parses into exactly the same row. The line
    below is copied verbatim from a Windows run log; the Linux boot (Task 8) re-runs this assertion
    against the VM's own log via the --check-line entry point."""

    LINE = ("[pc-sampler] live pc=0x3097f8 ra=0x30a114 sp=0x1ffd00 t=12.500 vsync=748 ee=12.480 "
            "seq=7412 dpc=0x3097f8 idle=3 bp_pending=1 bp_waiters=0 bp_wait_ms=0 net_wait=0/0 "
            "running=1 threads: [1 pc=0x3097f8 ra=0x30a114 sp=0x1ffd00 st=1 prio=48 wait=0/0]")

    def test_every_documented_field_is_present_and_parsed(self):
        rows = ft.parse([self.LINE])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["live_pc"], 0x3097F8)
        self.assertEqual(row["running"], 1)
        self.assertEqual(set(row["threads"]), {1})
        for key in ("t", "vsync", "ee", "seq", "dpc", "idle",
                    "bp_pending", "bp_waiters", "bp_wait_ms", "net_wait"):
            self.assertIsNotNone(row[key], "%s missing: a platform arm dropped a freeze field" % key)

    def test_the_same_line_from_two_logs_parses_to_the_same_row(self):
        win = ft.parse([self.LINE])[0]
        vm = ft.parse([self.LINE])[0]
        self.assertEqual(win, vm)
```
  Adjust the field-key names to whatever `freeze_trace._FIELDS` (:81-85) and `_sampler_fields` (:111-127) actually return when the case is written — read those two functions first and make the assertion match the parser's own keys, not this text.

- [x] **Step 2: Run them and watch them fail.**

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8
python -m unittest tools_py.tests.test_freeze_trace -v
```
  Expected: `'runtime/host_prof_line.h' file not found` from the C++ build, and the Python case passing on the first run — which is the honest outcome and is itself the statement worth having: the sampler line is already platform-blind, and this case is what will fail the day a Linux arm changes it. Record that distinction in the ledger rather than inventing a red.

- [x] **Step 3: Implement the two headers and route Windows through them.** `host_prof_line.h` and `cpu_time_ms.h` are header-only. Then replace `game_overrides_socom2.cpp` :1857-1872's inline line building with `HostProfLine::format(kv.first, kv.second, base, inExe ? nullptr : name, inExe ? 0 : (uint64_t)mod)`, and `ps2_vu1_core.cpp` :2841/:2849's two divisions with `CpuTimeMs::perSecond(...)` after converting the `FILETIME` pairs to ns. Run Step 2's commands: green, and **`./build.sh test` plus one gate stage before going further** — this is the one place in Task 5 where Windows code changes shape, so the proof that it did not change behaviour is a real run:

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "T5: build.sh test" -- ./build.sh test
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/s8_t5_build.marker
PS2X_HOST_PROF=1 dist/socom2.exe game/disc/socom2_game.elf   # via run.sh, 60 s; then:
head -3 logs/hostprof.txt
```
  Expected: `logs/hostprof.txt` still begins `base 0x<hex> total <n>` followed by `<rva> <count>` lines, and `python tools_py/hostprof_symbolize.py logs/hostprof.txt --top 10` still prints function names. A changed shape here is a defect, not a design choice.

- [x] **Step 4: The crash handler's Linux half.** `game_overrides_socom2.cpp` :869-913 keeps its `#ifdef _WIN32` body; add an `#else` arm before the `#endif` at :913:

```cpp
#else
    void crashHandler(int sig, siginfo_t *info, void *)
    {
        static int reported = 0;
        if (reported++ > 2)
            return;
        Dl_info me{};
        const uintptr_t base = ::dladdr(reinterpret_cast<void *>(&crashHandler), &me) && me.dli_fbase
                                   ? reinterpret_cast<uintptr_t>(me.dli_fbase)
                                   : 0;
        const auto addr = reinterpret_cast<uintptr_t>(info ? info->si_addr : nullptr);
        std::ostringstream o;
        // The same sentence the vectored handler prints, so one reader serves both logs. The signal
        // number stands where Windows prints its exception code; both are "what kind of crash".
        o << "[crash] code=0x" << std::hex << sig << " host=0x" << addr
          << " module+0x" << (addr >= base ? addr - base : 0);
        if (sig == SIGSEGV || sig == SIGBUS)
            o << " access=fault at 0x" << addr;
        o << std::dec << std::endl;
        void *frames[48];
        const int n = ::backtrace(frames, 48);
        o << "[crash] backtrace (module-relative):";
        for (int i = 0; i < n; ++i)
        {
            const auto f = reinterpret_cast<uintptr_t>(frames[i]);
            o << " " << std::hex << (f >= base ? f - base : f) << std::dec;
        }
        o << std::endl;
        if (g_runtimeForCrash)
        {
            const R5900Context *c = &g_runtimeForCrash->cpu();
            o << "[crash] guest live pc=0x" << std::hex << c->pc << " ra=0x" << GPR_U32(c, 31) << std::dec;
            const EeKernelSnapshot snap = g_runtimeForCrash->eeScheduler().snapshot();
            o << " running=" << snap.runningThreadId << " threads:";
            for (const auto &t : snap.threads)
                o << " [" << t.id << " pc=0x" << std::hex << t.pc << " ra=0x" << t.ra << std::dec
                  << " st=" << static_cast<int>(t.status) << "]";
            o << std::endl;
        }
        std::cerr << o.str() << std::flush;
        std::cout << o.str() << std::flush;
        // The Windows handler returns EXCEPTION_CONTINUE_SEARCH -- it reports and lets the process die.
        // The POSIX equivalent is to restore the default disposition and re-raise, so the exit status
        // the launcher reads is the real signal and not 0.
        ::signal(sig, SIG_DFL);
        ::raise(sig);
    }
#endif
```
  `installCrashHandler` (:1634-1640) gains the `#else` arm next to `AddVectoredExceptionHandler`:

```cpp
#else
        struct sigaction sa {};
        sa.sa_sigaction = crashHandler;
        sa.sa_flags = SA_SIGINFO | SA_RESTART;
        sigemptyset(&sa.sa_mask);
        for (int sig : {SIGSEGV, SIGBUS, SIGILL, SIGFPE})
            ::sigaction(sig, &sa, nullptr);
#endif
```
  Add `#include <dlfcn.h>`, `<execinfo.h>`, `<csignal>` to the `#else` arm of the include block at :29-30. `backtrace()` needs `-rdynamic` for readable names; it is not linked for names here (the line is module-relative addresses, symbolized offline exactly as on Windows), so no link flag changes.

- [x] **Step 5: The host sampler's Linux half.** Wrap the whole of `ps2HostProfStart` (:1712-1919) so its body is `#ifdef _WIN32 <the existing 200 lines> #else <the SIGPROF sampler> #endif`, sharing the env parsing at :1714-1724 (`PS2X_HOST_PROF`, `PS2X_HOST_PROF_OUT`, `PS2X_HOST_PROF_ALL`, `PS2X_HOST_PROF_MAIN`) and the dump loop's use of `HostProfLine::format`. The Linux arm:

  - A fixed `std::array<std::atomic<uint64_t>, 65536> g_ring` plus an atomic write index; the signal handler stores `((ucontext_t *)ctx)->uc_mcontext.gregs[REG_RIP]` into the ring and returns. Nothing in it allocates, locks or calls into the C++ runtime: it runs **on the sampled thread**, so anything else can deadlock the very thread it is measuring.
  - A `std::thread` that arms `timer_create` with `SIGEV_THREAD_ID` on the target tid (`nativeHandle` is a `pthread_t`; the tid comes from a one-shot `PS2X_HOST_PROF` handshake where the EE thread records its own `gettid()` — read `ps2_runtime.cpp:2562`, which passes `gameThread.native_handle()`, and add the tid the same way under `#ifndef _WIN32`), sets `it_interval` to the same `periodMs`, then every `periodMs` drains the ring into the same `std::unordered_map<uint64_t,uint32_t> counts` and every 10 s writes `outPath` with the same `base 0x.. total ..` header and `HostProfLine::format` lines.
  - `PS2X_HOST_PROF_ALL` and `PS2X_HOST_PROF_STACKS` are **not** implemented on Linux this sprint: the arm prints `[host-prof] PS2X_HOST_PROF_ALL/_STACKS are Windows-only in this build` once and samples the one thread. Say so rather than silently ignoring the knob.
  - `base` comes from `dladdr` on `&ps2HostProfStart`, and an address outside the exe is named with `dladdr`'s `dli_fname` and `dli_fbase` — the two arguments `HostProfLine::format` already takes.

- [x] **Step 6: The `[vu1-stats]` thread times.** `ps2_vu1_core.cpp` :2835-2854's `#ifdef _WIN32` block gains an `#else`:

```cpp
#else
                {
                    static uint64_t s_lastThread = 0, s_lastProc = 0;
                    timespec ts{};
                    if (::clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts) == 0)
                    {
                        const uint64_t t = static_cast<uint64_t>(ts.tv_sec) * 1000000000ull + ts.tv_nsec;
                        threadMs = CpuTimeMs::perSecond(t, s_lastThread, seconds);
                        s_lastThread = t;
                    }
                    if (::clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts) == 0)
                    {
                        const uint64_t t = static_cast<uint64_t>(ts.tv_sec) * 1000000000ull + ts.tv_nsec;
                        procMs = CpuTimeMs::perSecond(t, s_lastProc, seconds);
                        s_lastProc = t;
                    }
                }
#endif
```
  The `[vu1-stats]` format string at :2860 does not change, so `tools_py/vu1stats_summary.py` reads both.

- [x] **Step 7: State what is not tested here, and where it is verified.** The `sigaction` handler, the `SIGPROF` timer and the two `clock_gettime` calls have no pure piece left to assert once `HostProfLine::format` and `CpuTimeMs::perSecond` are extracted: what remains is OS plumbing whose only honest check is running it. **They are verified by Task 8's VM boot**, which asserts that the boot log carries a `[vu1-stats]` line with non-zero `thread=` and `proc=`, and by a deliberate fault: Task 8 Step 9 runs the VM's runner once with `PS2X_SOCOM2_FORCE_CRASH=1` if such a knob exists, and otherwise sends the live process `SIGSEGV` with `kill -SEGV` and requires a `[crash] code=0xb host=0x… module+0x…` line in the log. Write that sentence into this step, not into the commit message alone.

- [x] **Step 8: Green, then commit.**

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "T5: build.sh test" -- ./build.sh test
sha256sum -c /tmp/dist_before.txt || echo "EXPECTED: dist/socom2.exe MOVED (HostProfLine/CpuTimeMs are now called from Windows code)"
git push && gh run watch <id> --exit-status
```
  Expected: Windows 553 cases (the two new C++ cases), 0 failed; the Python suite 1174; CI green. **`dist/socom2.exe`'s hash does change in this task** — Step 3 routes Windows code through the two new headers — and that is the one sanctioned change in the sprint, which is why Step 3 re-ran `hostprof_symbolize.py` against a real run before the change was accepted. Record the before/after hashes and the `hostprof.txt` head in the ledger.

```bash
git commit -m "feat(linux): the crash line, the host PC sampler and the thread times on Linux

Sprint 8 Goal 1 design item 3. game_overrides_socom2.cpp's vectored exception handler (:870-913,
installed :1637) gets a sigaction #else arm on SIGSEGV/SIGBUS/SIGILL/SIGFPE that prints the same
[crash] sentence -- fault address, the module base from dladdr, the guest pc and the thread table --
and then restores SIG_DFL and re-raises, which is the POSIX equivalent of EXCEPTION_CONTINUE_SEARCH.
ps2HostProfStart (:1712-1919, unguarded until now and the reason the runner could not compile on Linux
at all) gets a SIGPROF interval timer armed on the EE thread whose handler stores the ucontext RIP into
a lock-free ring the dump thread folds into the SAME histogram; PS2X_HOST_PROF_ALL and _STACKS say out
loud that they are Windows-only rather than being silently ignored. ps2_vu1_core.cpp:2835-2854's
GetThreadTimes/GetProcessTimes pair gets clock_gettime(CLOCK_THREAD_CPUTIME_ID / _PROCESS_CPUTIME_ID).
RED first on the two pieces that have one: HostProfLine::format (one hostprof.txt line -- an in-exe RVA
or an external module basename plus offset, so tools_py/hostprof_symbolize.py reads one format from
either machine) and CpuTimeMs::perSecond (the [vu1-stats] thread=/proc= columns, zero on the first
sample and on a counter that went backwards). Windows now CALLS both, so dist/socom2.exe moves: the
proof it did not change behaviour is a real PS2X_HOST_PROF run whose hostprof.txt still symbolizes.
The sigaction and SIGPROF paths have no pure piece left and are verified by Task 8's VM boot.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/host_prof_line.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/cpu_time_ms.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp \
  third_party/ps2recomp/ps2xTest/src/host_config_tests.cpp \
  tools_py/tests/test_freeze_trace.py
git push
```

---

## Task 6 — The `vu1_replay` tool's unguarded `<windows.h>` (spec: the survey's fourth item)

*(landed 2026-09-18 by the concurrent implementation slices: a3d9269 + ab85233/31447c5 -- ticked wholesale; the handoff notes' reconciliation rule applies, line numbers are 7506685's)*

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` (:58 the unguarded `#include <windows.h>`; :916-968, the `--prof` sampler that needs it — `DuplicateHandle` :922, `GetModuleHandleW` :924, `SuspendThread` :934, `CONTEXT`/`GetThreadContext` :936-939, `ResumeThread` :940, `GetModuleHandleExW` :954-955, `MAX_PATH` :961, `GetModuleFileNameA` :963)
- Test: none beyond compiling. `vu1_replay` is an offline developer tool with no runtime path; `build_linux.sh test` already builds it (`--target ps2x_tests vu1_replay`), so "it compiles on Linux" is asserted by CI from the moment this lands.

**Interfaces:** `vu1_replay --prof <file>` keeps its meaning and its output format on both platforms — `base 0x<hex> total <n>` then `HostProfLine::format` lines (Task 5's header, reused here so there is one format in the tree, not two).

**Steps:**

- [x] **Step 1: Take the RED.** It is already on record from Task 2 if CI built `vu1_replay`; if not, take it explicitly:

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/socom_pc && cmake --build third_party/ps2recomp/build-linux --target vu1_replay 2>&1 | head -10'
```
  Expected: `vu1_replay.cpp:58:10: fatal error: 'windows.h' file not found`.

- [x] **Step 2: Guard the include and split the sampler.** At :58, `#include <windows.h>` becomes

```cpp
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <csignal>
#include <ctime>
#include <dlfcn.h>
#include <ucontext.h>
#include <unistd.h>
#endif
#include "runtime/host_prof_line.h"
```

  and the `--prof` block at :916-968 becomes `#ifdef _WIN32 <the existing body, with the line building at :957-964 replaced by HostProfLine::format> #else <the POSIX body> #endif`. The POSIX body is the small self-contained twin of Task 5's sampler — `vu1_replay` samples **its own** thread, which makes it fifteen lines rather than Task 5's ring:

```cpp
        // The same histogram from a POSIX interval timer. vu1_replay samples the thread that is doing
        // the work (itself), so the handler can write straight into a fixed ring and the stopping
        // thread folds it -- no DuplicateHandle, no suspend, no unwind tables.
        static std::atomic<uint64_t> s_ring[16384];
        static std::atomic<uint32_t> s_write{0};
        struct sigaction sa {};
        sa.sa_flags = SA_SIGINFO | SA_RESTART;
        sa.sa_sigaction = [](int, siginfo_t *, void *ctx) {
            const auto *uc = static_cast<ucontext_t *>(ctx);
            s_ring[s_write.fetch_add(1, std::memory_order_relaxed) % 16384].store(
                static_cast<uint64_t>(uc->uc_mcontext.gregs[REG_RIP]), std::memory_order_relaxed);
        };
        sigemptyset(&sa.sa_mask);
        ::sigaction(SIGPROF, &sa, nullptr);
        itimerval tv{};
        tv.it_interval.tv_usec = 200;      // the Windows body's 0.2 ms
        tv.it_value = tv.it_interval;
        ::setitimer(ITIMER_PROF, &tv, nullptr);
```
  with the drain-and-write half in the same place the Windows body writes its file, and the module naming at :957-964 becoming:

```cpp
        Dl_info self{};
        const uint64_t base = ::dladdr(reinterpret_cast<void *>(&main), &self) && self.dli_fbase
                                  ? reinterpret_cast<uint64_t>(self.dli_fbase) : 0;
        // The /proc/self/exe half of GetModuleFileNameA: dladdr names the module an address belongs to,
        // and for the exe itself dli_fname is argv[0], which can be a relative path -- so the exe's own
        // name is resolved once through readlink("/proc/self/exe") and every address at `base` uses it.
        char exePath[4096] = {};
        const ssize_t exeLen = ::readlink("/proc/self/exe", exePath, sizeof(exePath) - 1);
        if (exeLen > 0) exePath[exeLen] = '\0';
        // ... per entry:
        Dl_info di{};
        const bool known = ::dladdr(reinterpret_cast<void *>(kv.first), &di) != 0;
        const bool inExe = known && reinterpret_cast<uint64_t>(di.dli_fbase) == base;
        f << HostProfLine::format(kv.first, kv.second, base,
                                  inExe ? nullptr : (known ? di.dli_fname : "?"),
                                  known ? reinterpret_cast<uint64_t>(di.dli_fbase) : 0) << '\n';
```

- [x] **Step 3: Compile on both.**

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/socom_pc && cmake --build third_party/ps2recomp/build-linux --target vu1_replay -j 8'
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "T6: build.sh test" -- ./build.sh test
```
  Expected: the VM links `build-linux/ps2xRuntime/vu1_replay`, and the host's `./build.sh test` still runs its nine `vu1_replay` fixture verifies (`--verify` x5, `--vram-diff`, the clamp run, and the two ceiling overrides) to `tests: ok`. The nine verifies are the regression check that guarding the include changed nothing — they exercise the whole tool except `--prof`.

- [x] **Step 4: Commit.**

```bash
git commit -m "fix(vu1_replay): compile on Linux -- guard windows.h and give --prof a POSIX half

Sprint 8 Goal 1, the survey's fourth Windows-only item. src/tools/vu1_replay.cpp:58 included windows.h
unconditionally, for the --prof sampler alone (:916-968). The include is now guarded and the sampler
split: Windows keeps DuplicateHandle/SuspendThread/GetThreadContext, Linux arms ITIMER_PROF and reads
the ucontext RIP in the handler -- the tool samples its own thread, so there is nothing to suspend.
GetModuleFileNameA at :963 becomes dladdr for foreign modules plus readlink(/proc/self/exe) for the
tool's own name, and both platforms now emit their histogram lines through HostProfLine::format
(Task 5), so one parser reads either file. No new test: build_linux.sh test already builds this target,
so CI asserts the compile, and the host's nine vu1_replay fixture verifies assert nothing else moved.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp
git push
```

---

## Task 7 — Packaging: the Linux branch of `make_portable.sh` (spec Design item 5)

*(landed 2026-09-18 by the concurrent implementation slices: 2aa02c3 -- ticked wholesale; the handoff notes' reconciliation rule applies, line numbers are 7506685's)*

**Files:**
- Create: `scripts/portable_libs.py`, `tools_py/tests/test_portable_libs.py`
- Modify: `scripts/make_portable.sh` (all of it — the whole script becomes a `case "$(uname -s)"`), `tools_py/tests/test_make_portable.py` (:11, the `skipUnless` guard, so the Windows case is skipped on Linux instead of failing there)
- Read only: `third_party/ps2recomp/ps2xLauncher/CMakeLists.txt` and `ps2xRuntime/CMakeLists.txt` (Task 1's `INSTALL_RPATH "$ORIGIN/lib"` — the reason `lib/` works at all)

**Interfaces:**
- `scripts/portable_libs.py` reads `ldd` output on **stdin** (several binaries' output concatenated is fine) and prints one absolute path per line — the libraries to copy. `--missing` instead prints the sonames `ldd` could not resolve and exits 1 if there are any. Public functions, which is what the test drives: `entries(ldd_text) -> [(soname, path_or_None)]`, `is_host_library(soname) -> bool`, `libraries_to_copy(ldd_text) -> [path]` (de-duplicated, in first-seen order), `unresolved(ldd_text) -> [soname]`.
- The host's own stack is never copied: glibc and the loader (`libc.`, `libm.`, `libpthread.`, `libdl.`, `librt.`, `libresolv.`, `ld-linux`, `linux-vdso`), the compiler runtime (`libgcc_s.`, `libstdc++.`), the GL dispatch (`libGL.`, `libGLX.`, `libEGL.`, `libGLdispatch.`), X/xcb/wayland (`libX11.`, `libXext.`, `libXrandr.`, `libXinerama.`, `libXcursor.`, `libXi.`, `libxcb`, `libxkbcommon`, `libwayland`), and sound and the session bus (`libasound.`, `libpulse`, `libdbus`, `libsystemd`, `libudev`). What is left is the FFmpeg family and whatever it drags in, which is exactly what a distribution may not have.
- `scripts/make_portable.sh` on Linux writes `dist-linux/portable/socom2-linux/` containing `socom2`, `socom2_game.elf`, `socom_unzipped_launcher` (executable bits preserved), `lib/`, `cards/`, `logs/`, `LICENSES/`, `README.txt`, and `dist-linux/portable/socom2-linux.tar.gz`. The Windows branch is byte-identical to today's script.

**Steps:**

- [x] **Step 1: Write the failing Python test** `tools_py/tests/test_portable_libs.py` (`unittest`, no pytest — `test_test_hygiene.py` enforces it):

```python
"""Sprint 8 Goal 1 design item 5: which shared libraries the Linux tarball carries in lib/.

The filter is the whole decision, so it is a pure function over ldd text rather than a pipeline of
grep inside the shell script. The fixture is real `ldd dist-linux/socom2` output from the VM, trimmed.
"""
import unittest

from scripts import portable_libs

LDD = """\
\tlinux-vdso.so.1 (0x00007ffc93bd9000)
\tlibavcodec.so.60 => /usr/lib/x86_64-linux-gnu/libavcodec.so.60 (0x00007f0e4a000000)
\tlibavformat.so.60 => /usr/lib/x86_64-linux-gnu/libavformat.so.60 (0x00007f0e49c00000)
\tlibswresample.so.4 => /usr/lib/x86_64-linux-gnu/libswresample.so.4 (0x00007f0e49b00000)
\tlibGL.so.1 => /usr/lib/x86_64-linux-gnu/libGL.so.1 (0x00007f0e49a00000)
\tlibX11.so.6 => /usr/lib/x86_64-linux-gnu/libX11.so.6 (0x00007f0e49800000)
\tlibasound.so.2 => /usr/lib/x86_64-linux-gnu/libasound.so.2 (0x00007f0e49700000)
\tlibpulse.so.0 => /usr/lib/x86_64-linux-gnu/libpulse.so.0 (0x00007f0e49600000)
\tlibstdc++.so.6 => /usr/lib/x86_64-linux-gnu/libstdc++.so.6 (0x00007f0e49400000)
\tlibgcc_s.so.1 => /usr/lib/x86_64-linux-gnu/libgcc_s.so.1 (0x00007f0e49300000)
\tlibc.so.6 => /usr/lib/x86_64-linux-gnu/libc.so.6 (0x00007f0e49000000)
\tlibm.so.6 => /usr/lib/x86_64-linux-gnu/libm.so.6 (0x00007f0e48f00000)
\tlibvpx.so.9 => /usr/lib/x86_64-linux-gnu/libvpx.so.9 (0x00007f0e48d00000)
\t/lib64/ld-linux-x86-64.so.2 (0x00007f0e4b000000)
"""

MISSING = "\tlibswscale.so.7 => not found\n"


class Filter(unittest.TestCase):
    def test_the_ffmpeg_family_and_its_own_dependencies_are_copied(self):
        self.assertEqual(portable_libs.libraries_to_copy(LDD), [
            "/usr/lib/x86_64-linux-gnu/libavcodec.so.60",
            "/usr/lib/x86_64-linux-gnu/libavformat.so.60",
            "/usr/lib/x86_64-linux-gnu/libswresample.so.4",
            "/usr/lib/x86_64-linux-gnu/libvpx.so.9",
        ])

    def test_the_host_stack_is_never_copied(self):
        copied = portable_libs.libraries_to_copy(LDD)
        for never in ("libGL.so.1", "libX11.so.6", "libasound.so.2", "libpulse.so.0",
                      "libstdc++.so.6", "libgcc_s.so.1", "libc.so.6", "libm.so.6",
                      "ld-linux-x86-64.so.2", "linux-vdso.so.1"):
            self.assertFalse(any(p.endswith(never) for p in copied), never)

    def test_two_binaries_concatenated_yield_each_library_once(self):
        self.assertEqual(portable_libs.libraries_to_copy(LDD + LDD), portable_libs.libraries_to_copy(LDD))

    def test_an_unresolved_library_is_reported_and_never_silently_skipped(self):
        self.assertEqual(portable_libs.unresolved(LDD + MISSING), ["libswscale.so.7"])
        self.assertEqual(portable_libs.unresolved(LDD), [])

    def test_is_host_library_answers_for_a_soname_alone(self):
        self.assertTrue(portable_libs.is_host_library("libGLdispatch.so.0"))
        self.assertTrue(portable_libs.is_host_library("libxcb-dri3.so.0"))
        self.assertFalse(portable_libs.is_host_library("libavutil.so.58"))
```
  Run: `python -m unittest tools_py.tests.test_portable_libs -v` → `ModuleNotFoundError: No module named 'scripts'` (RED). `scripts/` needs an `__init__.py`, or the test imports by path — **choose the path import** (`importlib.util.spec_from_file_location`) so `scripts/` does not become a package and `test_test_hygiene.py`'s walk of `tools_py/` is unaffected. Rewrite the import as a three-line helper at the top of the test and re-run: `ModuleNotFoundError` becomes `FileNotFoundError: scripts/portable_libs.py`, which is the RED this step wants.

- [x] **Step 2: Implement `scripts/portable_libs.py`** with the four public functions and the `HOST_PREFIXES` tuple above, plus the `--missing` CLI. Run: `python -m unittest tools_py.tests.test_portable_libs -v` → 5 tests OK.

- [x] **Step 3: Give `make_portable.sh` a platform switch.** Wrap the existing body in `case "$(uname -s)" in Linux) <new> ;; *) <the current 38 lines, unchanged> ;; esac`. **The Windows arm is not reindented** — its two here-docs (`LIC` at :19-31 and `RD` at :32-42) need their terminators at column 0, and moving them is how a packaging script silently starts shipping a truncated README. Say so in the header comment. The Linux arm:
  - `DIST=dist-linux` (`LDIST`), refusing with exit 2 and `run scripts/build_linux.sh first` when `socom2`, `socom2_game.elf` or `socom_unzipped_launcher` is missing — `socom2_game.elf` is platform-neutral, so fall back to `dist/socom2_game.elf` when only Windows has built it.
  - `ldd` on **both** binaries, piped once through `portable_libs.py --missing` (exit 3 with the names when anything is unresolved: a tarball that is missing a library is a bug report, not a download) and once through `portable_libs.py` to fill `lib/` with `cp -L` (dereference: `ldd` hands back symlinks).
  - `cp -p` for the three binaries plus an explicit `chmod +x`, because a `.tar.gz` that unpacks non-executable is the classic Linux packaging failure.
  - A Linux `README.txt`: run `./socom_unzipped_launcher`; what the machine must already have (an OpenGL driver, PulseAudio or ALSA, the distribution's `libstdc++` — and why we do not ship ours); `zenity` optional, otherwise type the ISO path; logs in `logs/`; nothing is installed and nothing is written outside the folder.
  - A `LICENSES/README.txt` naming the same components as the Windows one minus `libwinpthread`, plus a line saying `lib/`'s libraries carry their distribution's licences and that glibc, `libstdc++`, the GL driver, X11 and the sound libraries are the host's and are not shipped.
  - `tar -C "$OUT" -czf "$OUT/socom2-linux.tar.gz" socom2-linux`, and a final line reporting the entry count, the library count and the tarball's size.

- [x] **Step 4: Keep the Windows packaging test honest.** `tools_py/tests/test_make_portable.py:11` is `@unittest.skipUnless(shutil.which("bash") and shutil.which("powershell"), "bash and PowerShell only")`, which already skips the whole class in the VM and on CI (no `powershell` there). Confirm it does, and add one Linux-only case beside it that runs the new branch against a fake `dist-linux/` — three stub binaries, a stubbed `ldd` on `PATH` printing the fixture, and assertions that the tarball exists, that `lib/` holds exactly the four non-host libraries, and that `README.txt` says `./socom_unzipped_launcher`. Guard it with `@unittest.skipUnless(sys.platform.startswith("linux"), "the Linux branch")`.

- [x] **Step 5: Green on all three.**

```bash
python -m unittest tools_py.tests.test_portable_libs tools_py.tests.test_make_portable -v
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "T7: build.sh test" -- ./build.sh test
bash scripts/make_portable.sh          # the Windows branch, unchanged: dist/portable + socom2-portable.zip
git push && gh run watch <id> --exit-status
```
  Expected: the Windows folder and zip built exactly as before (compare `ls dist/portable/socom2 | wc -l` against the last run's count in `docs/STATUS.md`), the Python suite up by 6 cases, CI green.

- [x] **Step 6: Commit.**

```bash
git commit -m "feat(packaging): a Linux branch for make_portable.sh, and the ldd filter as a tested function

Sprint 8 Goal 1 design item 5. make_portable.sh becomes a case on uname: the Windows branch is
byte-identical (its here-doc terminators stay at column 0 on purpose) and the Linux branch writes
dist-linux/portable/socom2-linux/ -- socom2, socom2_game.elf, socom_unzipped_launcher with their
executable bits, lib/ filled from ldd, cards/, logs/, LICENSES/, a Linux README.txt, and a .tar.gz.
lib/ is found at run time through the RPATH \$ORIGIN/lib Task 1 set on both binaries.
Which libraries go in lib/ is the whole decision, so it is scripts/portable_libs.py -- a pure filter
over ldd text -- rather than grep inside the shell script, and it is RED-first: the FFmpeg family and
what it drags in are copied; glibc, the loader, libgcc_s/libstdc++, the GL dispatch, X/xcb/wayland and
ALSA/Pulse/dbus never are, because they belong to the machine whose driver and sound server they talk
to (a copied libstdc++ is the classic way to break a newer host's GL driver). An soname ldd cannot
resolve exits 3 with its name instead of shipping a tarball that cannot start.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  scripts/make_portable.sh scripts/portable_libs.py \
  tools_py/tests/test_portable_libs.py tools_py/tests/test_make_portable.py
git push
```

---

## Task 8 — The VM ring: first build, suite, boot, frame compare (spec Design item 6b, first two bars)

**Files:**
- Create: `logs/s8_vm_boot.sh`, `logs/s8_vm_audio.sh`, `logs/s8_win_boot.sh` (launch scripts, five lines each)
- Writes: `logs/parity/s8_vm_boot.png`, `logs/parity/s8_win_boot.png`, `logs/parity/s8_vm_audio.wav`, `logs/linux_build.log`
- Read only: `tools_py/parity/scale_compare.py` (`mean_abs_diff(big, small, scale)` — **library only, there is no CLI**; the Sprint 7 plan drove it with `python -c`, and so does this task), `tools_py/parity/audio_corr.py` (:47 `read_wav`, :159 `correlate_arrays`, :204 `min_corr`, :304 the CLI), `tools_py/parity/drive.py:34-35` (the exported-frame knob), `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp:2772-2794` (the knob itself)
- Test: none new. This task is measurement; its assertions are the two bars below.

**Interfaces / the exact knobs:**
- **The exported frame is `PS2X_HOST_SCREENSHOT_LATEST=<file.png>`** — `ps2_runtime.cpp:2778` reads it once and, from :2782, re-exports the GL frame every 0.15 s to `<file>.tmp.png` and renames it into place. The survey's "`logs/parity/latest_frame.png`" is `drive.py:34`'s default for that same variable, not a separate mechanism. It is taken **before** the debug UI and before the FPS overlay draw (:2776-2777, :2796-2798), so the exported PNG is the game's frame and nothing else — which is what makes a cross-platform pixel comparison meaningful at all.
- `PS2X_CD_IMAGE=<iso>` (`launcher_config.cpp:293`), `PS2X_AUDIO_DUMP=<wav>` (`ps2_audio.cpp:397`), `PS2X_WINDOW_SIZE=640x448`.
- Bars: **mean |diff| < 3** between the VM's exported frame and a Windows export of the same boot screen, both 640x448 (`scale_compare.mean_abs_diff(win, vm, 1)`); **audio correlation ≥ 0.99** over the intro (`audio_corr.min_corr`).

**Steps:**

- [ ] **Step 1: Sync the tree, the generated code and the disc.** Three separate transfers, because they have three different costs and only the first is repeated:

```bash
rsync -az -e "ssh -i vm/keys/socom_linux -p 2222" --exclude build-clang --exclude build-tools \
      --exclude vm --exclude logs ./ socom@127.0.0.1:~/socom_pc/
rsync -az -e "ssh -i vm/keys/socom_linux -p 2222" recomp/output/ socom@127.0.0.1:~/socom_pc/recomp/output/
rsync -az --partial --progress -e "ssh -i vm/keys/socom_linux -p 2222" \
      "game/SOCOM II - U.S. Navy SEALs (USA).iso" socom@127.0.0.1:~/socom_pc/game/
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/socom_pc && ls recomp/output | wc -l && du -sh recomp/output game/*.iso && mkdir -p logs/parity'
```
  Expected: `14882`, `576M recomp/output`, `4.1G game/SOCOM II - U.S. Navy SEALs (USA).iso`. **A count under 14,882 is a stop** — a partial generated tree links a runner with holes in its function table and every later result is worthless. The ISO transfer is once; the other two are re-run before each later VM step in one line each.

- [ ] **Step 2: The first full Linux build, detached.** The generated code is 12.5 M lines at `-O1` on 8 cores; the spec's stop rule is three hours.

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/socom_pc && rm -f logs/linux_build.marker && nohup bash -c "scripts/build_linux.sh runtime > logs/linux_build.log 2>&1; echo exit=\$? > logs/linux_build.marker" >/dev/null 2>&1 & disown'
# poll, minutes apart; never hold the ssh open
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cat ~/socom_pc/logs/linux_build.marker 2>/dev/null || tail -2 ~/socom_pc/logs/linux_build.log'
```
  Expected: `exit=0`, and `ls -l ~/socom_pc/dist-linux/` showing `socom2` and `socom_unzipped_launcher`. **Stop rule (spec §Goal 1):** past three hours, give the VM more cores (the host has 28) before changing anything else, and record the wall time either way — it is the number the owner needs to decide whether ring (b) is a habit or a one-off.

- [ ] **Step 3: The suite in the VM.**

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/socom_pc && scripts/build_linux.sh test 2>&1 | tail -30'
```
  Expected: the Python suite's `OK`, then `ps2x_tests` reporting `Failed: 0` at the same total the host reports. **Bar: all green.** A case that fails only here is the sprint's most valuable finding — record its name and message verbatim before touching anything.

- [ ] **Step 4: Bring up X and openbox.** The VM is a server install with no display manager; `xinit` starts one on the console.

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'nohup startx /usr/bin/openbox-session -- :0 vt1 > ~/xorg.log 2>&1 & disown; sleep 5; DISPLAY=:0 xdpyinfo | head -5'
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 'DISPLAY=:0 glxinfo -B'
```
  Expected: `xdpyinfo` naming a screen, and `glxinfo -B` printing the renderer and `OpenGL core profile version string`. **Write the renderer and the GL version into the ledger now** — they are what the stop rule below is judged against, and they are the first thing the owner will ask.

- [ ] **Step 5: The boot launch, 40 s, exported frame.** `logs/s8_vm_boot.sh`, synced with the tree:

```bash
#!/usr/bin/env bash
# Sprint 8 Goal 1 Task 8: the first boot of the Linux runner, under a bare X session, with the frame
# the parity harness reads exported every 150 ms. 40 s reaches the boot/controller screen.
cd "$HOME/socom_pc" || exit 1
export DISPLAY=:0
export PS2X_CD_IMAGE="$HOME/socom_pc/game/SOCOM II - U.S. Navy SEALs (USA).iso"
export PS2X_HOST_SCREENSHOT_LATEST="$HOME/socom_pc/logs/parity/s8_vm_boot.png"
export PS2X_WINDOW_SIZE=640x448
export PS2X_HOST_GAMEPAD=0
cd dist-linux && timeout 40 ./socom2 socom2_game.elf > "$HOME/socom_pc/logs/s8_vm_boot.log" 2>&1
rc=$?; echo "done $rc" > "$HOME/socom_pc/logs/s8_vm_boot.done"; exit $rc
```
```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/socom_pc && rm -f logs/s8_vm_boot.marker && nohup bash -c "bash logs/s8_vm_boot.sh; echo exit=\$? > logs/s8_vm_boot.marker" >/dev/null 2>&1 & disown'
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 'cat ~/socom_pc/logs/s8_vm_boot.marker; ls -l ~/socom_pc/logs/parity/s8_vm_boot.png'
scp -i vm/keys/socom_linux -P 2222 socom@127.0.0.1:~/socom_pc/logs/parity/s8_vm_boot.png logs/parity/s8_vm_boot.png
scp -i vm/keys/socom_linux -P 2222 socom@127.0.0.1:~/socom_pc/logs/s8_vm_boot.log logs/s8_vm_boot.log
```
  **Read the log before the picture.** It must carry, in order: `Using argv boot path`; `[gs-gl] OpenGL backend active (PS2X_GS_BACKEND=cpu for the rasterizer)` **or** the probe's refusal and `exit 65`; `[socom2] applying SOCOM II overrides`; `[socom2/hostnet] BSD sockets ready; retail hostnames -> 127.0.0.1` (Task 3's line — its presence is the port's first end-to-end proof); and at least one `[vu1-stats]` line with **non-zero `thread=` and `proc=`** (Task 5's `clock_gettime` arm, which has no unit test and is verified here).

- [ ] **Step 6: The Windows reference, same screen, same size.** One host launch through the lock:

```bash
cat > logs/s8_win_boot.sh <<'SH'
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
export PS2X_HOST_SCREENSHOT_LATEST=/c/projects/socom_pc/logs/parity/s8_win_boot.png
export PS2X_WINDOW_SIZE=640x448 PS2X_HOST_GAMEPAD=0
timeout 40 dist/socom2.exe game/disc/socom2_game.elf > logs/s8_win_boot.log 2>&1
rc=$?; echo "done $rc" > logs/s8_win_boot.done; exit $rc
SH
scripts/run_detached.sh --owner gate --purpose launch logs/s8_win_boot.sh logs/s8_win_boot.marker
```
  The two runs must reach the **same screen**: no drive script, no presses, the same 40 s, the same `PS2X_WINDOW_SIZE`. That is what makes the comparison a comparison (Sprint 7's R94 is the precedent — the 2x capture failed at mean 41 the first time because two different screens were compared).

- [ ] **Step 7: The frame comparison. Bar: mean |diff| < 3.**

```bash
python -c "from tools_py.parity import scale_compare as sc; print(sc.mean_abs_diff('logs/parity/s8_win_boot.png','logs/parity/s8_vm_boot.png',1))"
```
  `scale_compare` has **no CLI** — it is `mean_abs_diff`, `upsample_nearest` and `_grey` only, and `upsample_nearest` at scale 1 is the identity, so scale 1 is the right call for two 640x448 frames. It raises `ValueError` on a shape mismatch, which is the guard that catches a VM window that came up at some other size. Decision table: **< 3 → the bar is met**; **3-10 → check the two captures are the same screen** (the boot sequence animates; re-take both at the same `--seconds` before touching any code); **> 10 → a finding**, which goes to `docs/KNOWN.md` §2 with both PNGs and stops Task 10 until it is understood.

- [ ] **Step 8: The audio dump. Bar: correlation ≥ 0.99 over the intro.** A second VM launch, 120 s, because the intro's music is what `logs/title_loop_pcm.bin` is a reference for and 40 s may not reach it:

```bash
# logs/s8_vm_audio.sh: as s8_vm_boot.sh but timeout 120, PS2X_AUDIO_DUMP=$HOME/socom_pc/logs/parity/s8_vm_audio.wav,
# and no PS2X_HOST_SCREENSHOT_LATEST (the export costs a GL readback every 150 ms and this run wants the CPU).
scp -i vm/keys/socom_linux -P 2222 socom@127.0.0.1:~/socom_pc/logs/parity/s8_vm_audio.wav logs/parity/s8_vm_audio.wav
python -m tools_py.parity.audio_corr logs/parity/s8_vm_audio.wav logs/title_loop_pcm.bin --bar 0.99
```
  Expected: one `mix <t> s: ref <t> s corr <x>` row per 4 s window and a final `min_corr=<x>` at or above 0.99, exit 0. If every row prints `silent`, the boot did not reach the intro inside 120 s — that is a finding about the VM's speed, not about audio: record the wall time the log shows for the first `[snd989]`/stream line and re-run at 240 s once only.

- [ ] **Step 9: Verify Task 5's two untested Linux paths, deliberately.** While a VM run is live:

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 'pkill -SEGV -f "dist-linux/socom2"; sleep 2; grep -c "^\[crash\]" ~/socom_pc/logs/s8_vm_boot.log'
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 'grep -m1 "^\[crash\]" ~/socom_pc/logs/s8_vm_boot.log'
```
  Expected: at least two `[crash]` lines, the first of the shape `[crash] code=0xb host=0x… module+0x…`, followed by the `backtrace (module-relative)` line and the `guest live pc=` line — the same three lines a Windows crash prints. And for the sampler, one run with `PS2X_HOST_PROF=1`:

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 'head -3 ~/socom_pc/dist-linux/logs/hostprof.txt'
```
  Expected: `base 0x<hex> total <n>` then `<rva> <count>` lines — the same format `tools_py/hostprof_symbolize.py` reads, which is what `HostProfLine::format` exists to guarantee.

- [ ] **Step 10: The GL stop rule.** If Step 4's `glxinfo -B` is below the probe's floor, or the boot log carries the probe's refusal, the runner exits **65** and falls back to the CPU rasterizer (Sprint 7 Task 1a, `GsGlCaps::kExitCode`). **That is accepted**: the frame comparison in Step 7 is then made against the CPU rasterizer's frame on both sides (re-run Step 6 with `PS2X_GS_BACKEND=cpu`), the same mean |diff| < 3 bar applies, and the GL bar moves to the owner's real Linux machine as a `docs/HUMAN_TASKS.md` item written in Task 12. Record the exit code, the renderer string and which path produced the compared frames — a mean |diff| of 0.8 means two different things depending on that answer.

- [ ] **Step 11: Commit the launch scripts and the numbers.** No source changes here; the commit carries the three scripts and the ledger's numbers land in `docs/KNOWN.md` in Task 12.

```bash
git commit -m "test(linux): the VM ring -- first build, suite, boot, frame and audio compared to Windows

Sprint 8 Goal 1 design item 6(b). socom-linux built the whole tree with the generated code in <N>
minutes on 8 cores at -O1, ps2x_tests <M>/<M> green, and the runner booted under a bare X session
(openbox via startx) to the same screen a Windows run reaches in 40 s. Exported-frame comparison
(PS2X_HOST_SCREENSHOT_LATEST, both 640x448, no drive script on either side so it is the same screen):
mean |diff| <X> against the bar of 3. Audio: PS2X_AUDIO_DUMP over 120 s against logs/title_loop_pcm.bin,
min_corr <Y> against the bar of 0.99. GL: <renderer>, <version>; <the probe passed | exit 65, CPU
rasterizer, and the GL bar moves to the owner's machine>. Task 5's two untested Linux paths are checked
here as planned: a delivered SIGSEGV produces the same three [crash] lines a Windows crash produces, and
PS2X_HOST_PROF writes a hostprof.txt hostprof_symbolize.py reads.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  logs/s8_vm_boot.sh logs/s8_vm_audio.sh logs/s8_win_boot.sh
git push
```

---

## Task 9 — The harness's Linux capture and key halves (spec Design item 6b, the gate's prerequisite)

*(landed 2026-09-18 by the concurrent implementation slices: 2aa02c3 -- ticked wholesale; the handoff notes' reconciliation rule applies, line numbers are 7506685's)*

**Files:**
- Create: `tools_py/parity/x11shot.py`, `tools_py/parity/hostshot.py`, `tools_py/tests/test_hostshot.py`
- Modify: `tools_py/parity/winshot.py` (no logic change — only the module docstring at :1, saying it is the Windows half of the `hostshot` pair), `tools_py/parity/keys.py` (:6-10 the ctypes import, :42-50 `press`, :30-39 `child_windows`), `tools_py/parity/drive.py` (:25 the import, :235-238 the "already running" check, :245-269 the window search and the kill)
- Read only: `tools_py/parity/gate.py` (:132 the `title` stage's script and seconds, :563-578 the scorers), `tools_py/parity/online_login.py:130`, `online_login_ours.py:1705`, `online_match_ours.py:5144`, `pcsx2_ctl.py:233`, `scale_shot.py:101-103`, `sp_death_probe.py:1061` — the other six `taskkill` sites, **out of scope here** and named in Task 12's KNOWN row so nobody assumes the whole harness is portable

**Interfaces:**
- `hostshot.module_name(platform_name) -> str` — the pure piece, tested on both: `"tools_py.parity.winshot"` for a platform string starting with `win`, `"tools_py.parity.x11shot"` for one starting with `linux`, and `ValueError` naming the platform otherwise (macOS is out of scope for this sprint and must say so rather than silently picking X11).
- `hostshot.load()` -> the module itself, via `importlib.import_module(module_name(sys.platform))`, memoised. `drive.py` does `from tools_py.parity import hostshot` then `winshot = hostshot.load()` and **nothing else in `drive.py` changes**: `x11shot` exposes the same names `winshot` does — `find_window(title_substring, pid=None)`, `window_title(hwnd)`, `client_size(hwnd)`, `grab(hwnd, max_age=None)`, `capture(hwnd)`, `capture_by_title(substring, path)`, `keep_on_top(hwnd)`, `ensure_client_size(hwnd, w, h)`, `register_frame_file(hwnd, path)`, and the two exception classes `ClientRectError` and `StaleFrameError`.
- `hostshot.kill_game(image_name)` — the `taskkill` / `pkill` switch: `["cmd", "/c", "taskkill /F /IM " + image]` on Windows, `["pkill", "-f", image]` on Linux, where `image` is `"socom2.exe"` or `"socom2"`.
- On Linux an "hwnd" is the X11 window id `xdotool` prints (an `int`), so every function takes and returns the same type it does on Windows and `drive.py`'s `_frame_files` dict keyed by handle keeps working unchanged.

**Steps:**

- [x] **Step 1: Write the failing test** `tools_py/tests/test_hostshot.py`:

```python
"""Sprint 8 Goal 1 Task 9: the harness picks its capture module by platform.

Only the SELECTION is testable on both machines -- the X11 functions need an X server and are verified
by Task 10's gate run in the VM. The selection is worth a test of its own because the failure it
prevents is silent: a macOS or a BSD checkout that imported winshot would die inside ctypes.windll with
an AttributeError forty lines from the cause.
"""
import unittest

from tools_py.parity import hostshot


class ModuleSelection(unittest.TestCase):
    def test_windows_gets_winshot(self):
        self.assertEqual(hostshot.module_name("win32"), "tools_py.parity.winshot")

    def test_linux_gets_x11shot(self):
        self.assertEqual(hostshot.module_name("linux"), "tools_py.parity.x11shot")
        self.assertEqual(hostshot.module_name("linux2"), "tools_py.parity.x11shot")

    def test_anything_else_says_so_by_name(self):
        with self.assertRaises(ValueError) as cm:
            hostshot.module_name("darwin")
        self.assertIn("darwin", str(cm.exception))

    def test_the_two_modules_expose_the_same_names(self):
        import importlib
        wanted = {"find_window", "window_title", "client_size", "grab", "capture", "capture_by_title",
                  "keep_on_top", "ensure_client_size", "register_frame_file",
                  "ClientRectError", "StaleFrameError"}
        # x11shot must import on every platform (it shells out; it links nothing), which is what lets
        # this run on the Windows host as well as in the VM.
        x11 = importlib.import_module("tools_py.parity.x11shot")
        self.assertTrue(wanted <= set(dir(x11)), sorted(wanted - set(dir(x11))))

    def test_kill_game_is_taskkill_on_windows_and_pkill_on_linux(self):
        self.assertEqual(hostshot.kill_command("win32", "socom2.exe"), ["cmd", "/c", "taskkill /F /IM socom2.exe"])
        self.assertEqual(hostshot.kill_command("linux", "socom2"), ["pkill", "-f", "socom2"])
```
  Run: `python -m unittest tools_py.tests.test_hostshot -v` → `ModuleNotFoundError: No module named 'tools_py.parity.hostshot'` (RED).

- [x] **Step 2: Write `x11shot.py`** — the same four behaviours `winshot.py` provides, through the tools `vm/postinstall.sh` installed. Every function shells out; nothing is linked, so the module imports anywhere:

```python
"""The Linux half of the capture pair (winshot.py is the Windows half; hostshot.py picks).

xdotool finds and raises windows, ImageMagick's `import` captures one by id, and the game's own
exported frame (PS2X_HOST_SCREENSHOT_LATEST) is preferred exactly as on Windows -- grab() below is
winshot.grab's logic verbatim, because that path is already platform-free and is what the gate uses.
`import -window <id>` is the X11 twin of PrintWindow: it reads the window's own pixels, so another
window on top does not end up in the capture the way a root-window screenshot would.
"""
```
  - `find_window(title_substring, pid=None)`: `xdotool search --onlyvisible --name <substring>` (case-insensitive by default), then `--pid` narrowing when `pid` is given via `xdotool search --pid`; returns the first id as `int`, or `None`.
  - `window_title(hwnd)`: `xdotool getwindowname <id>`.
  - `client_size(hwnd)`: `xdotool getwindowgeometry --shell <id>` and parse `WIDTH=`/`HEIGHT=`; `None` for an id that is not a window, matching `winshot.client_size`'s contract at :67-68 (the tests attach shells to fake handles).
  - `capture(hwnd)`: `import -silent -window <id> png:-` into `PIL.Image.open(BytesIO(...))`, converted to RGB; raise `RuntimeError("window has an empty client area (minimised?)")` on a zero-sized geometry, the same message `winshot.capture` raises at :164 so the callers' `except RuntimeError` paths behave identically.
  - `grab(hwnd, max_age=None)`: **copy `winshot.grab` (:88-122) verbatim**, including `FRAME_RETRY_S = 3.0`, `_frame_files`, `StaleFrameError` and the atomic-rename retry. It is the path the gate actually takes, and two divergent copies of it is how a stale-frame bug becomes platform-specific. Import the two exception classes from a new shared module rather than defining them twice — put `ClientRectError` and `StaleFrameError` in `tools_py/parity/hostshot.py` and have both `winshot` and `x11shot` re-export them, so `except winshot.StaleFrameError` in `drive.py:150` and `online_login_ours.py:337` still catches what `x11shot` raises.
  - `keep_on_top(hwnd)`: `xdotool windowraise <id>`. There is no X11 always-on-top without a window manager hint; openbox honours `wmctrl -i -r <id> -b add,above` and the VM has `x11-utils` but not `wmctrl`, so **`windowraise` is what this does**, and the docstring says the difference plainly: a raise is momentary where `SetWindowPos(HWND_TOPMOST)` is sticky, and the gate's drive loop re-raises before each capture as a result.
  - `ensure_client_size(hwnd, width=640, height=448)`: `xdotool windowsize <id> <w> <h>`, returning `True` when the geometry had to change. Openbox sizes the frame, not the client, so read the geometry back and correct once — the same correction `winshot.ensure_client_size` makes at :142-145.
  - `register_frame_file(hwnd, path)`: the same one-line dict insert.

- [x] **Step 3: Write `hostshot.py`** — `module_name`, `kill_command`, `load`, `kill_game`, and the two exception classes. Run Step 1's command: 5 tests OK **on the Windows host**, which is the point: the selector and the name parity are provable without an X server.

- [x] **Step 4: `keys.py` gets its Linux half.** :6-10's `user32 = ctypes.windll.user32` is a module-level statement, so the file cannot even be imported on Linux. Restructure: the two `MAPS` and `WINDOW_TITLES` (:12-27) are platform-free and stay at module level; the ctypes binding moves under `if sys.platform.startswith("win")`. `press(main_hwnd, button, target, hold_s=0.15)` (:42-50) becomes a switch:

```python
def press(main_hwnd, button, target, hold_s=0.15):
    if sys.platform.startswith("win"):
        return _press_win32(main_hwnd, button, target, hold_s)
    return _press_x11(main_hwnd, button, target, hold_s)


# xdotool key --window <id> posts a synthetic key to ONE window without taking focus, which is the same
# guarantee PostMessageW gives us on Windows (drive.py depends on it: the harness keeps working while
# another window has focus). --clearmodifiers keeps a stuck Shift from a previous step out of the press.
X11_KEYS = {"UP": "Up", "DOWN": "Down", "LEFT": "Left", "RIGHT": "Right",
            "CROSS": "x", "CIRCLE": "c", "SQUARE": "z", "TRIANGLE": "v",
            "START": "Return", "SELECT": "BackSpace", "L1": "q", "R1": "e", "L2": "1", "R2": "3",
            "W": "w", "A": "a", "S": "s", "D": "d", "I": "i", "J": "j", "K": "k", "L": "l"}


def _press_x11(hwnd, button, target, hold_s):
    if target != "ours":
        raise ValueError("PCSX2 is Windows-only in this harness; there is no Linux key map for it")
    key = X11_KEYS[button.upper()]
    subprocess.run(["xdotool", "keydown", "--window", str(hwnd), "--clearmodifiers", key], check=True)
    time.sleep(hold_s)
    subprocess.run(["xdotool", "keyup", "--window", str(hwnd), "--clearmodifiers", key], check=True)
```
  The X11 key names are the `"ours"` map's own keys read back from `socom2_host_input.cpp`'s keyboard map (`keys.py:22-25` documents it: arrows, Enter = START, Backspace = SELECT, Z/X/C/V = Square/Cross/Circle/Triangle, Q/E = L1/R1, 1/3 = L2/R2, WASD and IJKL for the sticks) — **not** a translation of the Windows virtual-key codes, which is a trap: `0x4B` is `K` in the `"ours"` map and `CROSS` in the `"pcsx2"` map. `child_windows` (:30-39) is a Windows-only helper; on Linux `press` targets the one window id and there are no children to fan out to, which the docstring says.

- [x] **Step 5: `drive.py` imports the platform module and kills with the platform command.** Three edits, no logic change:
  - :25 `from tools_py.parity import keys, screen_bands, winshot` → `from tools_py.parity import hostshot, keys, screen_bands` then `winshot = hostshot.load()`. The name `winshot` stays bound so the other 18 call sites (:58, :87, :140-154, :207, :245-259, :329-441) are untouched — deliberately, because this is a port, not a refactor.
  - :235-238's "already running" check uses `tasklist`, which does not exist on Linux: switch to `hostshot.running_game_names()` returning the lower-cased process list (`tasklist` on Windows, `ps -eo comm=` on Linux) and keep the same refusal message.
  - :267-269's `taskkill` → `subprocess.run(hostshot.kill_command(sys.platform, "socom2.exe" if sys.platform.startswith("win") else "socom2"), capture_output=True)`, keeping the PCSX2 branch Windows-only with the same `ValueError` `_press_x11` raises.

- [x] **Step 6: Green on both, and say what is not covered.**

```bash
python -m unittest tools_py.tests.test_hostshot tools_py.tests.test_drive_capture tools_py.tests.test_drive_crop tools_py.tests.test_drive_popup -v
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "T9: build.sh test" -- ./build.sh test
scripts/run_detached.sh --owner gate --purpose launch logs/s7_final_gate.sh logs/s8_t9_gate.marker
```
  Expected: the new module's 5 cases green, the three `drive` test modules unchanged, the Python suite green, and **the Windows gate still `PASS title/transition/mission` 3/3** — that gate run is the whole safety net for touching `drive.py` and `keys.py`, and it is non-negotiable before the commit. The X11 functions themselves are verified by **Task 10**; write that sentence in the commit, and note in the ledger that `online_login.py:130`, `online_login_ours.py:1705`, `online_match_ours.py:5144`, `pcsx2_ctl.py:233`, `scale_shot.py:101-103` and `sp_death_probe.py:1061` still call `taskkill` directly and are therefore still Windows-only.

- [x] **Step 7: Commit.**

```bash
git commit -m "feat(harness): a Linux capture and key half, picked by platform

Sprint 8 Goal 1: the gate's title stage has to run in the VM, and every step of it went through
winshot.py (ctypes.windll at module scope) and keys.py (PostMessageW). x11shot.py is the same surface
over xdotool and ImageMagick: find_window is 'xdotool search --onlyvisible --name', client_size is
'xdotool getwindowgeometry --shell', capture is 'import -window <id>' (the X11 twin of PrintWindow --
it reads the window's own pixels, so an overlapping window cannot end up in the frame), keep_on_top is
'xdotool windowraise', and grab() is winshot.grab's logic verbatim because the exported-frame path is
already platform-free and two copies of a stale-frame rule is how a bug becomes platform-specific.
keys.press posts through 'xdotool key --window <id>', the same no-focus guarantee PostMessageW gives.
hostshot.py is the selector and the only piece testable on both machines, so it is the RED: winshot for
win*, x11shot for linux*, a ValueError naming anything else (macOS must say so, not silently pick X11),
and the two modules asserted to expose the same names. drive.py binds the module and its taskkill
becomes pkill -f socom2; PCSX2 stays Windows-only and raises rather than pretending.
Still Windows-only, and named here so nobody assumes otherwise: online_login.py:130,
online_login_ours.py:1705, online_match_ours.py:5144, pcsx2_ctl.py:233, scale_shot.py:101,
sp_death_probe.py:1061. The X11 functions are verified by Task 10's gate run in the VM.
Windows gate 3/3 after the change.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  tools_py/parity/x11shot.py tools_py/parity/hostshot.py tools_py/parity/winshot.py \
  tools_py/parity/keys.py tools_py/parity/drive.py tools_py/tests/test_hostshot.py
git push
```

---

## Task 10 — The title stage of the gate, inside the VM (spec Design item 6b, third bar)

**Files:**
- Create: `logs/s8_vm_title.sh`
- Writes: `logs/parity/gate/s8_vm_title/title/` (19 captures `s00..s18` plus the `wNN_k` waits and `manifest.json`), `logs/parity/gate/s8_vm_title/summary.txt`
- Read only: `tools_py/parity/gate.py` (:132 `"title": dict(script="scripts/parity/title_menu.txt", seconds=170, tail=8)`, :149 `score_title`, :49-54 the calibration — 19 menu captures scoring 93.2-99.4 against the reference, `s19` the negative control), `scripts/parity/title_menu.txt`
- Test: none new; this **is** the test, and it is what verifies every X11 function Task 9 wrote.

**Interfaces:** `python -m tools_py.parity.gate --only title --stamp s8_vm_title` — the same command the host runs nightly, with no Linux-specific flag. That is the bar: if the gate needs an argument it does not need on Windows, the port is not done.

**Steps:**

- [ ] **Step 1: Re-sync and confirm the prerequisites.** The gate's title stage launches the game itself (`drive.py:34-38`), drives 19 steps of `scripts/parity/title_menu.txt` and scores each capture, so everything Task 9 wrote is exercised in one run.

```bash
rsync -az -e "ssh -i vm/keys/socom_linux -p 2222" --exclude build-clang --exclude build-tools \
      --exclude vm --exclude logs ./ socom@127.0.0.1:~/socom_pc/
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/socom_pc && python3 -c "import numpy, PIL; print(numpy.__version__, PIL.__version__)" && which xdotool import && DISPLAY=:0 xdpyinfo | head -2'
```
  Expected: numpy and Pillow present (install with `sudo apt-get install -y python3-numpy python3-pil` if not — `vm/postinstall.sh` did not list them, which is a gap to note), `xdotool` and `import` on `PATH`, and X alive on `:0`.

- [ ] **Step 2: `drive.py`'s launcher on Linux.** `drive.py:37` runs `["bash", "./run.sh", str(seconds)]` and `run.sh:12` runs `dist/socom2.exe`. In the VM the binary is `dist-linux/socom2`. Make `run.sh` choose:

```bash
# run.sh, replacing the single dist/socom2.exe line:
EXE="$ROOT/dist/socom2.exe"
[ -x "$EXE" ] || EXE="$ROOT/dist-linux/socom2"
ELF="$ROOT/game/disc/socom2_game.elf"
timeout "$SECS" "$EXE" "$ELF" "$@" > "$LOG" 2>&1
```
  and `drive.py:245`'s `keys.WINDOW_TITLES["ours"]` is `"PS2-Recomp"`, which raylib sets on both platforms — confirm with `xdotool search --name PS2-Recomp` during Step 3 rather than assuming. This is a **Windows-affecting** edit to `run.sh`: `dist/socom2.exe` exists there, so the first branch always wins and the host's behaviour is unchanged; prove it by re-running the host gate in Step 5.

- [ ] **Step 3: Run the title stage, detached.** `logs/s8_vm_title.sh`:

```bash
#!/usr/bin/env bash
# Sprint 8 Goal 1 Task 10: the gate's title stage inside socom-linux, under openbox on :0.
cd "$HOME/socom_pc" || exit 1
export DISPLAY=:0
export PS2X_CD_IMAGE="$HOME/socom_pc/game/SOCOM II - U.S. Navy SEALs (USA).iso"
export PS2X_HOST_GAMEPAD=0
python3 -m tools_py.parity.gate --only title --stamp s8_vm_title --owner gate
rc=$?; echo "done $rc" > logs/s8_vm_title.done; exit $rc
```
```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/socom_pc && rm -f logs/s8_vm_title.marker && nohup bash -c "bash logs/s8_vm_title.sh; echo exit=\$? > logs/s8_vm_title.marker" >/dev/null 2>&1 & disown'
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 'cat ~/socom_pc/logs/s8_vm_title.marker 2>/dev/null; tail -5 ~/socom_pc/logs/parity/gate/s8_vm_title/summary.txt 2>/dev/null'
```
  **Bar: `PASS title`.** The stage is ~3 minutes plus the boot.

- [ ] **Step 4: If it fails, name the detector and keep its screenshot.** Do not adjust a threshold. `score_title` (`gate.py:149`) reports which of the 19 captures scored below the calibrated band (93.2-99.4 on the four stored clean runs, `gate.py:49-54`). Pull the failing capture and the reference:

```bash
scp -i vm/keys/socom_linux -P 2222 -r socom@127.0.0.1:~/socom_pc/logs/parity/gate/s8_vm_title logs/parity/gate/
python -m tools_py.parity.gate --score-title logs/parity/gate/s8_vm_title/title
```
  The **exact detector name, its score, its band and the path to its screenshot** go into `docs/KNOWN.md` §2 in Task 12, as the spec's alternative bar allows ("the title stage of the gate passes in the VM, or … the exact detector that fails named in KNOWN with its screenshot"). Three failure shapes to tell apart before writing that row, because they mean different things: (a) a capture that is the *right screen, wrong pixels* → a rendering difference, which is a real finding; (b) a capture that is a *different screen* → a press that did not land, i.e. a Task 9 `xdotool` defect, which is fixed here not filed; (c) a capture that is *blank or another window* → `windowraise` is momentary where `HWND_TOPMOST` is sticky (Task 9 Step 2's noted difference), which is also fixed here, by re-raising inside the capture loop.

- [ ] **Step 5: The Windows gate, unchanged.**

```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s7_final_gate.sh logs/s8_t10_gate.marker
cat logs/parity/gate/s8_t10_gate/summary.txt
```
  Expected: `PASS title/transition/mission`, 3/3. `run.sh` was edited in Step 2, so this is not optional.

- [ ] **Step 6: Commit.**

```bash
git commit -m "test(linux): the gate's title stage passes in the VM

Sprint 8 Goal 1 design item 6(b), third bar: 'python -m tools_py.parity.gate --only title --stamp
s8_vm_title' inside socom-linux under openbox, with no Linux-specific flag -- which is the bar, because
a gate that needs an extra argument on Linux is not the same gate. Result: <PASS | FAIL with the
detector named>. This run is what verifies every X11 function Task 9 wrote: find_window, client_size,
capture, keep_on_top and xdotool key --window are all on the path of its 19 captures and 19 presses.
run.sh now prefers dist/socom2.exe and falls back to dist-linux/socom2, so drive.py's launcher works on
both; the Windows gate is 3/3 after that edit (s8_t10_gate).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  logs/s8_vm_title.sh run.sh
git push
```

---

## Task 11 — The tarball in the VM, and the launcher run (spec Design item 6b, fourth and fifth bars)

**Files:**
- Create: `logs/s8_vm_tarball.sh`
- Read only: `third_party/ps2recomp/ps2xLauncher/src/main.cpp` (:6 documents the flag, :356 `if (argc > 1 && std::strcmp(argv[1], "--selftest") == 0)` — **confirmed present**), `dist/logs/run_20260918_015258.log` (the real Windows launcher run whose first lines are the reference), `scripts/make_portable.sh` (Task 7's Linux branch)
- Test: none new; the bars are below.

**Interfaces:**
- `./socom_unzipped_launcher --selftest` — loads `config.json`, verifies the ISO if one is set, prints the environment and exits (`main.cpp:6`). Exit 0 with the ISO's verdict printed is the bar.
- **The three log lines to compare**, taken from the newest real Windows launcher run (`dist/logs/run_20260918_015258.log`, lines 1-3):
  1. `Using argv boot path`
  2. `[gs-gl] OpenGL backend active (PS2X_GS_BACKEND=cpu for the rasterizer)`
  3. `[gs-gl] PS2X_GS_SCALE=1 (render targets 1x native, resolve filter point)`
  Line 2 is the one that can legitimately differ: if the VM's GL is below the probe's floor the runner prints its refusal and falls back, and Task 8 Step 10's stop rule already accepted that. Lines 1 and 3 must match **exactly** — line 1 says the launcher passed the ELF as `argv[1]` rather than the runner hunting for it, and line 3 says the launcher's `PS2X_GS_SCALE` reached the child, which together are the whole claim that the Linux launcher starts the game the way the Windows one does.

**Steps:**

- [ ] **Step 1: Build the tarball in the VM and unpack it somewhere fresh.**

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/socom_pc && scripts/make_portable.sh 2>&1 | tail -3'
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'rm -rf ~/unpack && mkdir ~/unpack && tar -C ~/unpack -xzf ~/socom_pc/dist-linux/portable/socom2-linux.tar.gz && ls -l ~/unpack/socom2-linux ~/unpack/socom2-linux/lib | head -30'
```
  Expected: the script's last line reporting the entry count, the library count and the tarball size; the unpacked folder holding `socom2`, `socom2_game.elf`, `socom_unzipped_launcher` **with their executable bits** (`-rwxr-xr-x`), `lib/`, `cards/`, `logs/`, `LICENSES/`, `README.txt`. **A non-executable binary here is the bug this step exists to catch** — it is the classic tarball failure and it is invisible until someone else downloads it.

- [ ] **Step 2: `--selftest`, from the fresh directory.**

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/unpack/socom2-linux && ./socom_unzipped_launcher --selftest; echo "exit=$?"'
```
  Expected: `exit=0`, the environment block printed, and — with no `config.json` yet — the "no ISO set" path rather than a crash. Then write a `config.json` pointing at the VM's ISO and run it again:

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 \
  'cd ~/unpack/socom2-linux && printf "{\"isoPath\":\"%s\"}\n" "$HOME/socom_pc/game/SOCOM II - U.S. Navy SEALs (USA).iso" > config.json && ./socom_unzipped_launcher --selftest; echo "exit=$?"'
```
  Expected: `exit=0` and the ISO verified — `SCUS_972.75` found and its SHA-256 matching the r0001 disc, the same verdict the Windows launcher prints. **This is the first proof the ISO 9660 reader and the SHA-256 in `ps2x_launcher_core` behave identically on Linux**, and it costs nothing; say so.

- [ ] **Step 3: The launcher for real, under X, with the ISO typed.** No zenity in the VM (`vm/postinstall.sh` does not install it, deliberately — the typed path is the fallback the design names, and this exercises it):

```bash
# logs/s8_vm_tarball.sh
#!/usr/bin/env bash
cd "$HOME/unpack/socom2-linux" || exit 1
export DISPLAY=:0
nohup ./socom_unzipped_launcher > "$HOME/launcher.log" 2>&1 & disown
sleep 6
WID="$(xdotool search --onlyvisible --name 'SOCOM Unzipped' | head -1)"
echo "launcher window: $WID"
xdotool windowraise "$WID"
# The ISO field already holds the path from config.json (Step 2), so this run only presses Launch.
xdotool key --window "$WID" --clearmodifiers Return
sleep 45
echo "done" > "$HOME/socom_pc/logs/s8_vm_tarball.done"
```
  If `Return` does not press Launch (the launcher is a raylib immediate-mode window, and its buttons are hit-tested by mouse position, not by a focus ring), click it instead: read the Launch row's rectangle from `launcher_layout.h`, then `xdotool mousemove --window "$WID" <x> <y> click 1`. Decide which by looking at the window once with `import -window "$WID" launcher.png` and scp'ing it back — do not guess.

- [ ] **Step 4: Compare the child's log with a Windows run's. Bar: lines 1 and 3 identical.**

```bash
ssh -i vm/keys/socom_linux -p 2222 socom@127.0.0.1 'head -3 "$(ls -t ~/unpack/socom2-linux/logs/run_*.log | head -1)"'
head -3 "$(ls -t dist/logs/run_*.log | head -1)"
```
  Expected, side by side:

```
Using argv boot path
[gs-gl] OpenGL backend active (PS2X_GS_BACKEND=cpu for the rasterizer)      # or the probe's refusal
[gs-gl] PS2X_GS_SCALE=1 (render targets 1x native, resolve filter point)
```
  Also confirm the log **exists where the launcher said it would** — `logs/run_<stamp>.log` inside the unpacked folder, not in the home directory — which is Task 4's `posix_spawn` file actions and its working directory working together. A log in `~` means `addchdir_np` did not take and the game would resolve `cards/` outside the folder.

- [ ] **Step 5: Commit.**

```bash
git commit -m "test(linux): the tarball unpacks and runs from a fresh directory in the VM

Sprint 8 Goal 1 design item 6(b), the last two bars. make_portable.sh's Linux branch produced
socom2-linux.tar.gz (<N> entries, <M> libraries in lib/, <S>); unpacked into a fresh ~/unpack it keeps
its executable bits, ./socom_unzipped_launcher --selftest exits 0 and verifies the r0001 ISO -- the
first proof the launcher's ISO 9660 reader and SHA-256 behave identically on Linux -- and the launcher
under X started the game with the ISO typed rather than picked (no zenity installed, which is the
fallback the design names). The child's log lines 1 and 3 match a Windows run's exactly ('Using argv
boot path', '[gs-gl] PS2X_GS_SCALE=1 (render targets 1x native, resolve filter point)'), which is what
says the launcher passed the ELF as argv[1] and its environment reached the child; line 2 is the GL
backend line and differs only where the probe falls back. The log landed inside the unpacked folder,
so posix_spawn's addchdir_np took and cards/ resolves where it should.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- logs/s8_vm_tarball.sh
git push
```

---

## Task 12 — Close-out for Goal 1

**Files:**
- Modify: `docs/KNOWN.md` (§1 Proven, one row per settled fact; §2 for anything the VM refused), `docs/STATUS.md` (the current-state bullet at :3-6 and a dated entry), `docs/CURRENT_SPRINT.md` (the Sprint 8 block at :11-25), `docs/HUMAN_TASKS.md` (the Open list), `docs/superpowers/plans/2026-09-18-sprint-8-linux-client.md` (this file: tick the boxes, and any box left open carries a one-line reason or a `STOP:`)

**Steps:**

- [ ] **Step 1: `docs/KNOWN.md` §1 — one row per fact, each naming its artefact.** Four rows, and they are written only with the numbers actually measured:
  - **The client builds and its suite passes on Linux with no generated code** — artefact: CI run `<id>` on `ubuntu-24.04`, `ps2x_tests <N>/<N>`, the launcher artifact attached; the Windows binaries' sha256 unchanged across Tasks 1-4 and 6-7.
  - **The Linux runner boots SOCOM II to the same screen as Windows** — artefact: `logs/parity/s8_vm_boot.png` vs `logs/parity/s8_win_boot.png`, mean |diff| `<X>` (bar 3), both 640x448 exported frames of an undriven 40 s boot; the VM's GL renderer `<renderer>` at `<version>`; `<the probe passed | exit 65 and the CPU rasterizer>`.
  - **The gate's title stage `<passes | fails at detector D>` in the VM** — artefact: `logs/parity/gate/s8_vm_title/summary.txt`, and on a failure the capture's path and its score against the calibrated 93.2-99.4 band.
  - **The tarball runs unpacked from a fresh directory** — artefact: the `--selftest` exit 0 with the r0001 verdict, and the child log's lines 1 and 3 equal to a Windows run's.
- [ ] **Step 2: `docs/KNOWN.md` §2 — what the VM refused, and what is still Windows-only.** At minimum: the six `taskkill` sites Task 9 left alone (`online_login.py:130`, `online_login_ours.py:1705`, `online_match_ours.py:5144`, `pcsx2_ctl.py:233`, `scale_shot.py:101`, `sp_death_probe.py:1061`), so the online harness is Windows-only and nobody assumes a Linux ladder run is a command away; `PS2X_HOST_PROF_ALL` and `_STACKS` (Task 5, Windows-only by decision); PCSX2 as the console reference (no Linux key map, `keys.py` raises); `keep_on_top` being a momentary raise rather than a sticky topmost; and the VM's GL result with its consequence.
- [ ] **Step 3: `docs/STATUS.md`.** Replace the current-state bullet's opening with the branch and the Goal 1 verdict in one sentence, and add a dated entry in the file's own voice: what landed, the four bars and their numbers, and what the next goal is (Goal 2, the menus' render cost — `docs/CURRENT_SPRINT.md`'s Sprint 8 item 2).
- [ ] **Step 4: `docs/CURRENT_SPRINT.md`'s Sprint 8 block.** Mark Goal 1 done or partly done with its bars' numbers, note that `docs/superpowers/plans/2026-09-18-sprint-8-linux-client.md` is the plan it names at :14 and is now ticked, and move the pointer to Goal 2. Update the "human tasks" line's count.
- [ ] **Step 5: `docs/HUMAN_TASKS.md` — the owner's item, ring (c).** One entry in the file's existing shape (what to do, what to look for, the command, and the number being confirmed):

```markdown
- [ ] **Run the Linux tarball on a real machine** (Sprint 8 Goal 1, ring (c)). Any Linux PC or a Steam
  Deck in desktop mode. Download `socom2-linux.tar.gz` from the branch's CI artifacts (or copy it from
  `dist-linux/portable/`), `tar xzf` it anywhere, `cd` in and run `./socom_unzipped_launcher`. Point it
  at your own SOCOM II ISO — the file picker appears only if `zenity` is installed; otherwise type the
  path, the field accepts it. What to report, one line each: did the launcher open and verify the disc;
  did Launch start the game and reach the title screen; how did it sound; and what `./socom2 --version`
  style line the log's first three rows carry (`logs/run_*.log` inside the folder). The number you are
  confirming: the VM reached the same boot frame as Windows at mean |diff| <X> against a bar of 3, on
  <renderer>. A real GPU is the case the VM cannot speak for — <and, if the VM fell back, the GL bar
  itself lives here rather than in the VM>. If anything needs installing before it runs, that line is
  the most valuable thing in the report: it becomes the README's prerequisites.
```
- [ ] **Step 6: Tick this plan's boxes, and leave a reason on every one that stays open.** A box with neither a tick nor a reason is the failure mode the Sprint 6 close-out audit found; a `STOP:` line pointing at `docs/HUMAN_TASKS.md` is a valid reason.
- [ ] **Step 7: Commit.**

```bash
git commit -m "docs: Sprint 8 Goal 1 closed -- the Linux client builds, boots and packages

KNOWN gains four proven rows (CI green with no generated code; the VM's boot frame against Windows at
mean |diff| <X>, bar 3; the gate's title stage <verdict>; the tarball run from a fresh directory) and a
section 2 row for what stays Windows-only: the six taskkill sites in the online harness, PCSX2 as the
console reference, PS2X_HOST_PROF_ALL/_STACKS, and keep_on_top being a raise rather than a sticky
topmost. STATUS and CURRENT_SPRINT carry the verdict and move the pointer to Goal 2 (the menus' render
cost). HUMAN_TASKS gains ring (c): the owner's own Linux PC or Steam Deck with the tarball, which is the
one case the VM cannot speak for.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  docs/KNOWN.md docs/STATUS.md docs/CURRENT_SPRINT.md docs/HUMAN_TASKS.md \
  docs/superpowers/plans/2026-09-18-sprint-8-linux-client.md
git push
```

---

## Rulings made on the owner's behalf

R99 onward; see the Sprint 7 plan for R91-R98.

- **R99** (Task 3): **hostnet's BSD half is a per-platform compat block plus inline forwarders, not a `#else` clause inside each of the seventeen functions.** The alternative doubles a 530-line file and makes every future socket change two edits that can silently diverge — which is precisely how the Windows-only state this task is fixing came about. The Windows arm of every forwarder (`closeSocketHandle` → `closesocket`, `setNonBlocking` → `ioctlsocket(FIONBIO)`, `lastSocketError` → `WSAGetLastError`, `selectNfds` → `0`) expands to the exact call the line made before, so the Windows object is semantically identical and `dist/socom2.exe`'s hash is checked unchanged in Task 3 Step 6. *Cost if wrong:* a reader of `socom2_hostnet.cpp` has one indirection to follow before seeing the syscall; the compat block is thirty lines at the top of the file and each forwarder is one line.

- **R100** (Task 4): **`win32glue::GameProcess` gains its POSIX state as extra members under `#ifndef _WIN32`, not by packing a pid into the existing `void *process`.** `win32_glue.h:15-32` is one struct shared by both platforms and the spec's design item 4 says the interface and the header stay one ("the same `win32glue` interface, the name stays, one header"), so the two candidates were packing (`process` = `pid + 1`, `log` = `status + 1`) and guarded fields. **Guarded fields win**, and the working tree had already taken that choice when this plan was written (`win32_glue.h:21-28`: `int pid`, `int logFd`, `mutable bool exited`, `mutable int status`): the Windows layout is byte-identical because the block is inside `#ifndef _WIN32`, `running()`/`exitCode()` are `const` and need a `mutable` cache for the one reap `waitpid` allows, and a reader sees a pid called `pid`. Task 4's Step 5 is written against the packing form; **adopt the header's fields instead** and simplify `pidOf`/`setPid`/`latchStatus` into direct member access — the handoff notes' reconciliation rule covers this, and the behaviour the tests assert is identical either way. *Cost if wrong:* `sizeof(GameProcess)` differs between the platforms, which nothing serializes or ABI-matches; the struct is a launcher-local value type held once.

- **R101** (Task 4): **`posix_spawn` with `posix_spawn_file_actions_addchdir_np`, with a `fork`+`chdir`+`execv` fallback only where the extension is absent.** The launcher holds a live GL context and miniaudio's capture thread, and `fork()` there copies one thread while inheriting every lock the others held — the classic malloc deadlock between fork and exec, and an undefined GL context besides. `addchdir_np` is glibc ≥ 2.29 (Ubuntu 20.04; 24.04 ships 2.39), so the fallback is musl and ancient glibc only. The child's working directory is not optional: the game resolves `cards/` and `logs/` from it. *Cost if wrong:* on musl the launcher takes the fork path and could, rarely, hang between fork and exec; a launcher that cannot start the game at all on those systems is worse, and Task 11 Step 4 checks the child's log landed inside the folder, which is what proves the chdir took.

- **R102** (Task 1): **the Linux build writes `dist-linux/`, not `dist/`.** The sprint's first constraint is "the Windows build and its gate byte-for-byte unaffected", and a shared output directory makes that a matter of argument rather than of `sha256sum`. It also lets a host with both trees present keep a Windows `dist/` and a VM-synced `dist-linux/` without either clobbering the other. *Cost if wrong:* one more directory in `.gitignore` and one more path in `make_portable.sh`; `socom2_game.elf` is platform-neutral and the Linux branch falls back to `dist/`'s copy when only Windows has built it.

- **R103** (Task 5): **`PS2X_HOST_PROF_ALL` and `PS2X_HOST_PROF_STACKS` are not implemented on Linux this sprint, and say so out loud.** All-threads sampling needs a per-thread timer and tid enumeration through `/proc/self/task`, and stack walking needs `libunwind` or frame pointers the `-O1` generated code does not keep — both are a task of their own and neither is on Goal 1's path. The arm prints `[host-prof] PS2X_HOST_PROF_ALL/_STACKS are Windows-only in this build` once. *Cost if wrong:* a Linux performance investigation gets single-thread samples only, which is what the knob gave on Windows before Sprint 6 added `_ALL`; the line in the log means nobody spends an afternoon wondering why the histogram looks thin.

- **R104** (Task 9): **`keep_on_top` on Linux is `xdotool windowraise`, a momentary raise, not a sticky always-on-top.** X11 has no focus-free topmost without a window-manager hint, and the VM has `x11-utils` but not `wmctrl`. The gate's drive loop re-raises before each capture, and `import -window <id>` reads the window's own pixels rather than the root's, so an overlapping window cannot corrupt a capture the way it could through `PrintWindow`'s BitBlt fallback (`winshot.py:173-182`). *Cost if wrong:* a capture taken while something covers the window is still correct on Linux — the failure `keep_on_top` exists to prevent on Windows does not have a Linux counterpart; the difference is written into `x11shot.keep_on_top`'s docstring so nobody ports the Windows reasoning across.

- **R105** (Task 5, Step 3): **`dist/socom2.exe` is allowed to move exactly once in this sprint** — when `HostProfLine::format` and `CpuTimeMs::perSecond` are extracted and the Windows code starts calling them. Everywhere else the constraint is checked with `sha256sum -c`. The alternative, two copies of each formatter, would leave `tools_py/hostprof_symbolize.py` and `tools_py/vu1stats_summary.py` reading a format that only one platform is tested against. The proof that behaviour did not change is a real `PS2X_HOST_PROF` run whose `hostprof.txt` still symbolizes, taken before the change is accepted. *Cost if wrong:* a formatting regression in a developer tool's output, caught by the two MiniTest cases and by that run.

## Self-review

- **Spec coverage.** Design item 1 → Tasks 1 (CMake, the build script) and 2 (CI is the configuration item 1's runner-skip exists for). Item 2 (sockets) → Task 3, bar: the loopback case green on both, CI 550/550. Item 3 (crash handler, sampler, thread times) → Task 5, with the two extractable pieces under RED tests and the OS plumbing verified in Task 8 Steps 5 and 9. Item 4 (the launcher) → Task 4, bars: `mergeEnvironment` on both platforms, the refusal naming its path, `exeDirectory` real. Item 5 (packaging) → Task 7, bar: the `ldd` filter's five cases, and the tarball itself in Task 11. Item 6(a) → Task 2. Item 6(b) → Tasks 8 (build, suite, boot, frame, audio), 9 (the harness halves the title stage needs), 10 (the title stage), 11 (the tarball and the launcher run). Item 6(c) → Task 12 Step 5. The survey's fourth Windows-only item, `vu1_replay`'s unguarded `<windows.h>`, → Task 6. **The spec's four bars map to:** CI green on every port commit → Task 2 Step 2 and every later task's `gh run watch`; `ps2x_tests` all green in the VM → Task 8 Step 3; the boot frame at mean |diff| < 3 → Task 8 Step 7; the title stage in the VM → Task 10; the launcher's log lines → Task 11 Step 4; the tarball from a fresh directory → Task 11 Step 1. Both spec stop rules are carried: the GL floor in Task 8 Step 10, the three-hour build in Task 8 Step 2.
- **Launch budget.** The spec §3 allows "about six" in the VM plus the host's own. This plan spends **five VM launches** (`s8_vm_boot` 40 s, `s8_vm_audio` 120 s, `s8_vm_title` ~4 min, `s8_vm_tarball` ~1 min, plus one `PS2X_HOST_PROF` run folded into Task 8 Step 9) and **three host launches** (`s8_win_boot` for the reference frame, `s8_t9_gate` and `s8_t10_gate` for the two mandatory Windows gate re-runs after `drive.py`/`keys.py`/`run.sh` change, plus the `PS2X_HOST_PROF` run in Task 5 Step 3 which is a 60 s run, not a gate). VM builds are detached with a marker and are not launches.
- **Placeholder scan.** Clean: no `TBD`, no "handle edge cases", no "similar to Task N" anywhere in this plan — searching it for those three finds only this sentence. Every value left to be filled is a **measurement**, marked `<X>`, `<N>`, `<id>`, `<renderer>` inside a commit-message or KNOWN template, to be replaced by the run that precedes the commit. Seven implementation details the spec left open are named as controller's choices with rulings: the compat-layer shape (R99), `GameProcess`'s POSIX state (R100), the spawn mechanism (R101), the output directory (R102), the unimplemented profiler knobs (R103), the raise-vs-topmost difference (R104), and the one sanctioned Windows binary change (R105).
- **Type consistency.** `PS2X_BUILD_RUNNER` (CMake, `ON`/`OFF`), `PS2X_LAUNCHER_EXE_TYPE` (CMake, `WIN32`/empty), `socklen_compat`, `closeSocketHandle(SOCKET)`, `setNonBlocking(SOCKET, bool)`, `bytesReadable(SOCKET, unsigned long &)`, `lastSocketError()`, `setLastSocketError(int)`, `selectNfds(SOCKET)`, `wouldBlockOrInProgress(int)`, `launcher::mergeEnvironment(const char *const *, const std::vector<std::string> &)`, `HostProfLine::format(uint64_t, uint32_t, uint64_t, const char *, uint64_t)`, `CpuTimeMs::perSecond(uint64_t, uint64_t, double)`, `portable_libs.libraries_to_copy(str)` / `unresolved(str)` / `is_host_library(str)` / `entries(str)`, `hostshot.module_name(str)` / `kill_command(str, str)` / `load()`, and `x11shot`'s nine names mirroring `winshot`'s — each is used with one signature everywhere it appears. Knob names: `PS2X_RUNNER_GENERATED_DIR`, `PS2X_GENERATED_OPT`, `PS2X_HOST_SCREENSHOT_LATEST`, `PS2X_CD_IMAGE`, `PS2X_AUDIO_DUMP`, `PS2X_WINDOW_SIZE`, `PS2X_HOST_GAMEPAD`, `PS2X_HOST_PROF`, `PS2X_GS_BACKEND`, `GEN`, `LDIST`.
- **What the tree contradicted in the brief, and what this plan does instead.** Five things, each verified by reading the file: (1) `ps2xTest/CMakeLists.txt:122-124` already has `ws2_32` under `if(WIN32)`; (2) `ps2xLauncher/CMakeLists.txt:19-21` already has `comdlg32`/`shell32` under `if(WIN32)` — only the `WIN32` *executable keyword* at :13 was unguarded; (3) the launcher's glue header is `ps2xLauncher/src/win32_glue.h`, not `include/launcher/win32_glue.h`; (4) `tools_py` uses **`unittest`**, and `tools_py/tests/test_test_hygiene.py` fails the suite on any `import pytest`; (5) `tools_py/parity/scale_compare.py` has **no CLI** — it is a three-function library, driven with `python -c` as the Sprint 7 plan drove it. A sixth, smaller: an empty `PS2X_RUNNER_GENERATED_DIR` neither fails nor links an empty exe; it links a stub runner from `src/runner/register_functions.cpp` plus `src/main.cpp`.
- **Owner gate.** Goal 1 is autonomous end to end under the owner's standing instruction of 2026-09-17. The one item that cannot be done here is ring (c), the owner's real Linux machine, and it is written as a `docs/HUMAN_TASKS.md` entry in Task 12 Step 5 rather than as a block — the loop files it and moves to Goal 2.
