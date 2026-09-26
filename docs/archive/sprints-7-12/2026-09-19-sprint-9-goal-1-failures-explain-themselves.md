# Sprint 9 Goal 1 — A Failure Explains Itself: Implementation Plan

> **ARCHIVED 2026-09-25 -- a Sprint 9 plan; the sprint is closed and this is its record.**
> Moved here from `docs/superpowers/plans/` in Sprint 13 (Task R1, with the rest of Sprints 7-10's specs and
> plans); nothing below it was edited except citations that pointed at a path that has since moved. It is a
> record, not an instruction.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the game stops on a stranger's machine, the launcher's LAST RUN line says why in one sentence; `socom2` started with no argument reads the launcher's `config.json` beside it and plays; and one button writes one zip a stranger can attach to a report — log, config, GL line, crash record, versions, and nothing that identifies an account. Today: the only exit code with a meaning is 65 (`GsGlCaps::kExitCode`, `gs_gl_caps.h:24`), and its sentence hangs off a literal `65` in a file that "does not include the runtime's headers" (`launcher_config.cpp:314-317`); every other ending reads "the game exited" (`ps2xLauncher/src/main.cpp:682`); a bare `socom2` throws "Unable to determine executable path" and leaves with 1 (`ps2xRuntime/src/main.cpp:162`, `:254`); a missing disc is a WARNING followed by a black window (`game_overrides_socom2.cpp:577`); and COPY DIAGNOSTICS copies two files into a folder (`ps2xLauncher/src/main.cpp:125-138`).

**Architecture:** One new static library, **`ps2x_shared`** (`third_party/ps2recomp/ps2xShared/`), that both the runner and the launcher link and that links neither of them: plain C++20, no raylib, no GL, no `ps2_runtime`. It receives the three launcher files the runner now needs (`iso9660`, `sha256`, `launcher_config` — moved with their include paths and their `launcher::` namespace intact, R126) and gains seven small modules: `ps2x/exit_codes.h` (the taxonomy, header-only, one X-macro table that C++ and Python both read), `ps2x/preflight` (ELF present, card folder writable, disc found, disc is r0001 — before a window opens), `ps2x/bare_run` (config.json beside the exe becomes the environment; output goes to `logs/run_<stamp>.log`), `ps2x/exe_dir`, `ps2x/process_fatal` (the out-of-memory handler and the two `--fail-test` drivers), `ps2x/zip_store` (a STORE-only zip writer with CRC-32 — no archiver is vendored, R133) and `launcher/diagnostics` (what goes in the zip, as a pure function from strings to zip entries). The runner's `main()` gains a preflight in front of `runtime.initialize()`; the launcher's `exitMessage` becomes a lookup. Everything decidable is decided in a function that `ps2x_tests` checks on Windows, in CI and in the VM; the only untested lines are the ones that call the operating system, and each is named where it is written.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh` on the host; system clang + Ninja in the VM and on `ubuntu-24.04`), CMake >= 3.20, raylib (launcher window only), MiniTest (`ps2x_tests`; `PS2X_TEST_SUITE=<substring>` selects suites, `ps2xTest/include/MiniTest.h:134`), Python 3 `unittest` (**not** pytest), `scripts/run_detached.sh` + `scripts/loop_lock.sh` for the runtime build and the gate.

**Spec:** `docs/archive/sprints-7-12/2026-09-19-sprint-9-a-strangers-first-run-design.md` §2 "Goal 1 — a failure explains itself" and §4 (one gate per runtime commit; every moved default is a numbered ruling, next **R126**). **Required reading for every dispatch:** this plan's Handoff notes and Global Constraints; `third_party/ps2recomp/ps2xRuntime/src/main.cpp` (255 lines, all of it); `third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h` and `src/launcher_config.cpp` (the schema, `environmentFor`, `mergeEnvironment`, `exitMessage`); `third_party/ps2recomp/ps2xLauncher/src/main.cpp:60-138` (`readText`, `checkDisc`, `copyDiagnostics`), `:486-527` (the CLI modes), `:672-688` (where the child's exit is read), `:940-975` (the request handlers); `src/win32_glue.cpp:223-234` and `src/posix_glue.cpp:184-197` (`GameProcess::exitCode`); `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp:884-930` (the Windows vectored handler), `:932-1097` (the Linux `sigaction` handler), `:552-581` (`configureCdImage`); `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp:731-798` (`initialize`), `:1098-1116` (`configureIoPathsFromElf`, `PS2X_MC_DIR`); `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp:1-95` and `:288-295` (the MiniTest pattern and the one existing exit-code case).

## Handoff notes for the executing model (read once)

- **Process.** superpowers:subagent-driven-development; a fresh implementer per task; a task review after each; the controller merges. Ledger at `.superpowers/sdd/2026-09-19-sprint-9-goal-1/progress.md`. Decisions on the owner's behalf are `Ruling: … — why — cost if wrong`, numbered from **R126**; this plan uses R126-R138 and the next free number is **R139**.

- **What the tree says that the spec and the brief do not, in the order it will bite.**
  1. **The crash handlers choose no exit code.** On Windows `crashHandler` is a *vectored* handler that prints and returns `EXCEPTION_CONTINUE_SEARCH` (`game_overrides_socom2.cpp:929`), so the process dies with the NT status itself — `0xC0000005` for an access violation — which `GameProcess::exitCode` hands the launcher as a negative `int` (`win32_glue.cpp:232`). On Linux `crashReraise` restores `SIG_DFL` and re-raises (`:973-987`), so the launcher computes `128 + signal` (`posix_glue.cpp:194-195`): 139 for SIGSEGV. Neither fits "0-255 outside 126-165". An uncaught C++ exception goes through `setupTerminateLogger` to `std::abort()` (`ps2xRuntime/src/main.cpp:95-123`): exit 3 from the mingw CRT on Windows, 134 (SIGABRT, which the Linux handler does not catch) on Linux. `LoadExecPS2` also leaves with a literal 3 (`Kernel/Syscalls/Thread.cpp:206`). **R128** settles it: the handlers stay as they are, and the taxonomy's `classify()` folds the native statuses onto one code, 70.
  2. **There is no crash record file.** The "crash record" is `[crash]` lines in the run log (`:903-927`, `:1004-1063`), beside `[terminate]` (`main.cpp:99-120`) and `[main] fatal exception` (`:245-249`). The zip's `crash.txt` is those lines lifted out of the log (R135).
  3. **`config.json` has no password field, and no credential of any kind.** The schema is fifteen keys (`launcher_config.cpp:192-216`): `isoPath gsScale presentFilter windowSize fpsOverlay audioVolume mouseLook mouseSensitivity gamepadIndex padDeadZone micDevice serverPreset server profile secondInstance`. The game's account lives on the memory card, not here. The spec's "config with the password field removed" is therefore implemented as an **allowlist** (parse, then re-serialise: any key the schema does not know — `password`, `token`, whatever a later build adds — cannot survive) plus the one privacy redaction the schema does need: `isoPath` is cut to its file name, because its directory usually carries the OS account name (R134).
  4. **The launcher's fallback text is "the game exited", not "the game closed"** (`ps2xLauncher/src/main.cpp:682`), and `launcher_tests.cpp:293-294` *asserts* that codes 0 and 1 have no sentence. Task 2 changes those two assertions on purpose.
  5. **The runner opens its window before it looks at the ELF.** `main()` calls `runtime.initialize()` (InitWindow, InitAudioDevice) at `:221` and `loadELF` at `:227`. A check that runs after `initialize` flashes a window at a stranger and then closes it; this plan's preflight runs first.
  6. **A relative `PS2X_MC_DIR`.** `environmentFor` emits `PS2X_MC_DIR=cards/<profile>` (`launcher_config.cpp:371`), which works only because both glues start the child with the launcher's folder as its working directory (`win32_glue.cpp:323-324`, `posix_glue.cpp:272`). A double-clicked `socom2` has no such promise, so the bare run makes it absolute and changes directory to its own folder (R131).
  7. **`version.txt` is read and never written.** The launcher shows `readText(dir / "version.txt")` (`main.cpp:582`) or "development build" (`page_about.cpp:15`); nothing in `build.sh`, `scripts/build_linux.sh` or `scripts/make_portable.sh` creates it. Task 9 makes `make_portable.sh` write it, because the zip's `versions.txt` is otherwise always "development build".
  8. **The Windows glue does not use `mergeEnvironment`.** `win32_glue.cpp:268-300` carries its own copy of the merge loop; only `posix_glue.cpp:241` calls the pure function. Not this goal's to fix; noted so nobody builds the bare run on a function Windows never exercised (the bare run uses neither: it sets only what is unset, R131).
  9. **No zip, zlib or miniz anywhere in the tree** (`find third_party tools -iname 'miniz*' -o -iname 'zlib.h' -o -iname 'libzip*'` finds only llvm-mingw's unrelated `libzipfldr.a`). A CRC-32 table exists at `ps2_runtime.cpp:144-175` but is file-local to `ps2_runtime`, which the launcher must not link. Task 7 writes the writer out.

- **`docs/KNOWN.md` has one writer: the controller.**

- **Autonomy (owner 2026-09-17, standing).** Proceed autonomously. **One host launch at a time**, always through `scripts/run_detached.sh`, and **suites are held while a host launch runs**: no `./build.sh test`, no `python -m unittest`, no build, no gate and no second launch while `logs/.quiet` exists (`bash scripts/check_quiet_gate.sh` answers). This includes the Python cases below that start `socom2` or the launcher for a fraction of a second.

- **Subagents (owner 2026-09-17).** Bounded mechanical work goes to Opus subagents with an exact brief and a verification command; judgment stays with the controller. Each task below is marked **[Opus]** (the code and tests are written out; the brief is "make this text compile and these cases pass, change nothing else") or **[Judgment]** (touches `ps2xRuntime/src/`, needs a build, a gate, or a decision about what a stranger sees). A subagent never decides whether a bar is met, never writes `docs/KNOWN.md`, never commits, and never starts a launch.

- **Line numbers** are the numbers at `0e14323` (the branch tip when this was written). Before starting a task, `git diff 0e14323 -- <the task's files>` and reconcile, saying so in the ledger.

- **Test binary and its baseline.** Windows: `third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe`. Linux: `third_party/ps2recomp/build-linux/ps2xTest/ps2x_tests`. Sprint 8 closed at suite 611 / Python 1299. **Record the baselines `B` (C++ `Total Tests:`) and `P` (Python `Ran N tests`) in the ledger before Task 1**; every step states its expected total as `B + n` / `P + n`.

- **The launch budget.** One runtime build, one gate (`s9_g1_gate`) and one 60 s bare-run launch (`s9_g1_bare`), all in Task 6. Tasks 1-5 and 7-9 touch nothing under `ps2xRuntime/src/` and spend no launch. Task 6's and Task 9's Python cases start `socom2` / the launcher for well under a second each and are not launches in the budget's sense, but they obey the quiet gate.

### The command set (use these verbatim)

```bash
# --- build and suite (Windows host, Git Bash, repo root) ---
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8
( cd third_party/ps2recomp/build-clang/ps2xTest && PS2X_TEST_SUITE=<Name> ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|      - |Total Tests|Failed:"
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "<what>" -- ./build.sh test
python -m unittest tools_py.tests.<module> -v          # one Python module

# --- the launcher alone (no generated code needed) ---
cmake --build third_party/ps2recomp/build-clang --target socom_unzipped_launcher -j 8 \
  && cp third_party/ps2recomp/build-clang/ps2xLauncher/socom_unzipped_launcher.exe dist/

# --- the runner, for Task 6 ---
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/build_runtime.marker
cat logs/build_runtime.marker 2>/dev/null || echo running     # poll the marker, never the tool call

# --- the three-stage gate (shape of logs/s8_close_gate.sh) ---
scripts/run_detached.sh --owner gate --purpose launch logs/s9_g1_gate.sh logs/s9_g1_gate.marker
bash scripts/check_quiet_gate.sh                               # answers whether a suite may run

# --- Linux (the VM; CI runs the same script with --no-runner) ---
scripts/vm_sync.sh tree && scripts/vm_sync.sh ssh 'cd ~/socom_pc && bash scripts/build_linux.sh test'
```

`logs/s9_g1_gate.sh` (created in Task 6; `logs/` is git-ignored, so it is never committed):

```bash
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:$HOME/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
python -m tools_py.parity.gate --stamp s9_g1_gate --owner gate
rc=$?
echo "done $rc" > logs/s9_g1_gate.done
exit $rc
```

## Global Constraints

- Branch `sprint-9`, in the main checkout, never a worktree.
- **TDD, with RED watched.** Every step that adds behaviour names the case that fails before it and passes after, and the exact failure text; the implementer runs the RED and pastes its output into the ledger before writing the implementation. A step that cannot state a RED says so in one sentence and names what verifies it instead (there are four: Task 1's move, and Task 6's audio line, console detach and output redirect).
- **Never `git add -A`, never `git add .`.** Every commit is `git add <paths>` for new files followed by `git commit -m "…" -- <paths>` with the explicit pathspec given in the task. **`server/config/simulated.db` is never staged** (it is modified in the working tree and stays that way). **`ONBOARDING.md` is never staged.** `vm/`, `dist/`, `logs/` are git-ignored and nothing under them is ever staged. The untracked `*.bin` / `*.wav` files in the repo root and in `third_party/ps2recomp/` are not this goal's and are never staged. Never stage a file another running agent is editing (memory: commit-only-idle-files).
- Commit trailer, every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Push after each commit.
- `./build.sh test` exit 0 on the Windows host before any commit touching `third_party/ps2recomp/`, `tools_py/` or `scripts/`. **The three-stage gate PASS (3/3) — `scripts/run_detached.sh --owner gate --purpose launch logs/s9_g1_gate.sh logs/s9_g1_gate.marker` — before any commit touching `third_party/ps2recomp/ps2xRuntime/src/`** (Task 6 only).
- **No builds and no suites while a game launch runs** (`logs/.quiet`; `bash scripts/check_quiet_gate.sh`).
- **Windows and Linux both.** The Linux build is `scripts/build_linux.sh`; CI is `.github/workflows/linux.yml` (`--no-runner`: library, tests and launcher, no generated code). Anything that uses Win32 has its POSIX half **in the same file, in the same commit**: `exe_dir.cpp`, `bare_run.cpp` and `process_fatal.cpp` are the three places an `#ifdef _WIN32` is allowed in this goal, and each has an `#else`. Nothing in `ps2x_shared` may include `raylib.h` or any `ps2xRuntime` header; `<windows.h>` is included only inside those three `.cpp` files, never in a header (it redefines `Rectangle`, `CloseWindow`, `ShowCursor`, `DrawText`: `win32_glue.h:2`).
- **Exit codes fit a byte, avoid the shell's range, and 65 keeps its meaning.** Every code this goal adds is in 0-255, outside 126-165 (126/127 are the shell's "cannot execute"/"not found", 128+n is "killed by signal n"), and is not 65. Codes 1 and 3 already leave this process today and are *named*, not moved. `tools_py/tests/test_exit_codes_table.py` enforces all of it against the header.
- **One sentence per code, and it fits the line.** Each sentence is plain English a player can act on, at most 120 characters (the LAST RUN line is a single ellipsized row, `page_play.cpp:60`), contains no double quote (the Python reader is a regex) and ends with a full stop.
- **The zip contains no credential and no home directory.** Enforced by a C++ case (Task 8) and by a Python case that opens the real launcher's real zip with `zipfile` (Task 9).
- LF line endings in every new file. **Python tests are `unittest`, never pytest**, live in `tools_py/tests/`, and have no module-level `def test_` (`tools_py/tests/test_test_hygiene.py`).

---

## File map

| Path | Responsibility |
|---|---|
| `ps2xShared/CMakeLists.txt` (new), `ps2xShared/include/launcher/{iso9660,sha256,launcher_config}.h` and `ps2xShared/src/{iso9660,sha256,launcher_config}.cpp` (moved from `ps2xLauncher/`), `CMakeLists.txt`, `ps2xLauncher/CMakeLists.txt` | **Task 1 [Opus]**: `ps2x_shared` exists; nothing behaves differently |
| `ps2xShared/include/ps2x/exit_codes.h` (new), `ps2xRuntime/include/runtime/gs/gs_gl_caps.h:24`, `ps2xRuntime/CMakeLists.txt:584`, `ps2xShared/src/launcher_config.cpp` (`exitMessage`), `ps2xTest/src/exit_codes_tests.cpp` (new), `ps2xTest/src/main.cpp`, `ps2xTest/CMakeLists.txt`, `ps2xTest/src/launcher_tests.cpp:288-295`, `tools_py/exit_codes.py` (new), `tools_py/tests/test_exit_codes_table.py` (new) | **Task 2 [Opus]**: the taxonomy, in one header, read by C++ and Python |
| `ps2xShared/include/launcher/launcher_config.h`, `ps2xShared/src/launcher_config.cpp`, `ps2xLauncher/src/main.cpp` (:467, :497-505, :672-688), `ps2xTest/src/launcher_tests.cpp` | **Task 3 [Opus]**: LAST RUN shows the sentence, notices appended; `--selftest` lists every sentence |
| `ps2xShared/include/ps2x/preflight.h`, `ps2xShared/src/preflight.cpp`, `ps2xTest/src/preflight_tests.cpp` (all new) | **Task 4 [Opus]**: the four pre-window checks over a real temp directory |
| `ps2xShared/include/ps2x/{bare_run,exe_dir}.h`, `ps2xShared/src/{bare_run,exe_dir}.cpp`, `ps2xTest/src/bare_run_tests.cpp` (all new) | **Task 5 [Opus]**: `config.json` beside the exe becomes a launch plan |
| `ps2xShared/include/ps2x/process_fatal.h`, `ps2xShared/src/process_fatal.cpp` (new), `ps2xRuntime/src/main.cpp`, `ps2xRuntime/src/lib/ps2_runtime.cpp:772`, `tools_py/tests/test_runner_exit_codes.py` (new), `logs/s9_g1_gate.sh` (new, ignored) | **Task 6 [Judgment]**: the runner wired — preflight, bare run, out of memory, `--fail-test`, the audio notice; one build, one gate |
| `ps2xShared/include/ps2x/zip_store.h`, `ps2xShared/src/zip_store.cpp`, `ps2xTest/src/zip_store_tests.cpp` (all new) | **Task 7 [Opus]**: a STORE-only zip writer with CRC-32 |
| `ps2xShared/include/launcher/diagnostics.h`, `ps2xShared/src/diagnostics.cpp`, `ps2xTest/src/diagnostics_tests.cpp` (all new) | **Task 8 [Opus]**: what goes in the zip, from strings to entries; no credential |
| `ps2xLauncher/src/main.cpp` (:125-138, :486-527, :587, :951-952), `ps2xLauncher/src/ui/page_play.cpp:70`, `scripts/make_portable.sh`, `tools_py/tests/test_make_portable.py`, `tools_py/tests/test_diagnostics_zip.py` (new) | **Task 9 [Judgment, small]**: SAVE DIAGNOSTICS writes the zip; `--diagnostics`; `version.txt` |
| `docs/KNOWN.md`, `docs/STATUS.md`, `docs/CURRENT_SPRINT.md`, `docs/HUMAN_TASKS.md`, this plan | **Task 10 [Judgment]**: the Linux ring, close-out |

**All source paths in the tasks below are relative to `third_party/ps2recomp/`** unless they start with `tools_py/`, `scripts/`, `docs/`, `logs/` or `dist`. Commit pathspecs are always written from the repo root.

Tasks 1 -> 2 -> 3 are a chain. Task 4 needs 2. Task 5 needs 2. Task 6 needs 4 and 5. Task 7 needs 1. Task 8 needs 2 and 7. Task 9 needs 3 and 8. Tasks 4, 5 and 7 can run in parallel **only if** each agent's edits to the three shared list files (`ps2xShared/CMakeLists.txt`, `ps2xTest/CMakeLists.txt`, `ps2xTest/src/main.cpp`) are merged by the controller; with at most two C++-building agents (spec §4) the simple order is 1-10 as numbered.

### The taxonomy (decided here, implemented in Task 2)

| Code | Name | Slug | Sentence | Who sets it |
|---|---|---|---|---|
| 0 | `Ok` | `ok` | The last run exited normally. | `main()` (`:241`) |
| 1 | `Failed` | `failed` | The game stopped on an error it did not name. Press SAVE DIAGNOSTICS; the end of the log says more. | existing: `main()`'s catch blocks and `initialize` failing (`:224`, `:254`) |
| 3 | `Aborted` | `aborted` | The game stopped itself after an internal error. Press SAVE DIAGNOSTICS; the end of the log says why. | existing: `std::abort()` on the mingw CRT, `LoadExecPS2` (`Thread.cpp:206`) |
| 65 | `NoUsableGl` | `no-usable-gl` | Your GPU or driver is missing OpenGL 3.3 with dual-source blending; the game ran on the slow CPU renderer. | existing, verbatim (`ps2_runtime.cpp:2628`) |
| 66 | `DiscNotFound` | `disc-not-found` | The disc image was not found. Open the DISC page and choose your SOCOM II ISO again. | preflight |
| 67 | `DiscNotR0001` | `disc-not-r0001` | That disc image is not SOCOM II NTSC r0001 (SCUS-97275). This build plays only that disc. | preflight |
| 68 | `ElfMissing` | `elf-missing` | socom2_game.elf is missing or damaged. Unpack the download again and keep every file together. | preflight; `loadELF` failing |
| 69 | `ConfigUnreadable` | `config-unreadable` | config.json could not be read. Delete it and start the launcher, which writes a new one. | bare run |
| 70 | `Crashed` | `crashed` | The game crashed. Press SAVE DIAGNOSTICS and send the zip; it holds the crash record. | `classify()` from the native status (R128) |
| 71 | `OutOfMemory` | `out-of-memory` | The game ran out of memory. Close other programs, or lower the render scale on the VIDEO page. | the `std::new_handler` |
| 72 | `CardDirUnwritable` | `card-dir-unwritable` | The memory-card folder cannot be written. Move the game out of a protected folder and try again. | preflight |

Anything else: `The game closed with code <n>. Press SAVE DIAGNOSTICS to collect the log.` **Audio device absent is not an exit** (spec: "non-fatal, reported"): the runner prints `[notice] no-audio-device: No audio device was found; the game ran without sound.` and the launcher appends the sentence to whatever LAST RUN says (R129).

---

## Task 1 — `ps2x_shared` is born: three files move, nothing behaves differently  **[Opus]**

**Files:**
- Create: `ps2xShared/CMakeLists.txt`
- Move (`git mv`, contents untouched): `ps2xLauncher/include/launcher/iso9660.h`, `sha256.h`, `launcher_config.h` -> `ps2xShared/include/launcher/`; `ps2xLauncher/src/iso9660.cpp`, `sha256.cpp`, `launcher_config.cpp` -> `ps2xShared/src/`
- Modify: `CMakeLists.txt` (top level), `ps2xLauncher/CMakeLists.txt`
- Stay where they are: `ps2xLauncher/include/launcher/launcher_layout.h`, `mic_devices.h`, everything under `ps2xLauncher/src/ui/`

**Interfaces:** none change. Every `#include "launcher/iso9660.h"`, `"launcher/sha256.h"`, `"launcher/launcher_config.h"` in the tree keeps compiling because the new library exports an include root with the same `launcher/` subfolder; the `launcher::`, `iso9660::` and `sha256::` namespaces are untouched (R126).

**Steps:**

- [x] **Step 1: Record the baselines.** `bash scripts/check_quiet_gate.sh`, then `./build.sh test` under the loop lock (command set). Write `B = <Total Tests>` and `P = <Ran N tests>` into the ledger. Expected: `Failed: 0`, `OK`.

- [x] **Step 2: Move the six files.**

```bash
cd third_party/ps2recomp
mkdir -p ps2xShared/include/launcher ps2xShared/include/ps2x ps2xShared/src
git mv ps2xLauncher/include/launcher/iso9660.h         ps2xShared/include/launcher/iso9660.h
git mv ps2xLauncher/include/launcher/sha256.h          ps2xShared/include/launcher/sha256.h
git mv ps2xLauncher/include/launcher/launcher_config.h ps2xShared/include/launcher/launcher_config.h
git mv ps2xLauncher/src/iso9660.cpp         ps2xShared/src/iso9660.cpp
git mv ps2xLauncher/src/sha256.cpp          ps2xShared/src/sha256.cpp
git mv ps2xLauncher/src/launcher_config.cpp ps2xShared/src/launcher_config.cpp
```

- [x] **Step 3: Write `ps2xShared/CMakeLists.txt`.**

```cmake
# Sprint 9 Goal 1: what the runner (socom2) and the launcher both need, and nothing either of them owns.
# Plain C++20: no raylib, no GL, no ps2_runtime. The runner links this so that it never links the launcher;
# the launcher's tested core (ps2x_launcher_core) links it PUBLIC, so every existing
# #include "launcher/launcher_config.h" keeps resolving.
add_library(ps2x_shared STATIC
    src/iso9660.cpp
    src/sha256.cpp
    src/launcher_config.cpp
)
target_include_directories(ps2x_shared PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(ps2x_shared PUBLIC cxx_std_20)
# The Android runner is a SHARED library (ps2xRuntime/CMakeLists.txt:489); objects it absorbs must be PIC.
set_target_properties(ps2x_shared PROPERTIES POSITION_INDEPENDENT_CODE ON)
```

- [x] **Step 4: Add it to the top-level `CMakeLists.txt`**, unconditionally, immediately **above** the block that reads `if(PS2X_BUILD_RUNTIME)` / `add_subdirectory("ps2xIOP")` (so the target exists when `ps2xRuntime` is configured):

```cmake
# Sprint 9 Goal 1: shared by the runner and the launcher; depends on nothing in this tree.
add_subdirectory("ps2xShared")
```

- [x] **Step 5: `ps2xLauncher/CMakeLists.txt`.** Replace the `add_library(ps2x_launcher_core STATIC …)` source list (lines 6-12) so the three moved files are gone, and link the new library PUBLIC directly under `target_compile_features(ps2x_launcher_core PUBLIC cxx_std_20)`:

```cmake
add_library(ps2x_launcher_core STATIC
    src/ui/focus.cpp
    src/ui/pad_geometry.cpp
)
```

```cmake
# Sprint 9 Goal 1: iso9660, sha256 and launcher_config moved to ps2x_shared (the runner reads config.json too).
target_link_libraries(ps2x_launcher_core PUBLIC ps2x_shared)
```

Also correct the comment on lines 2-3 of that file: `ps2x_launcher_core` now holds the pure UI logic (focus, pad geometry); the ISO 9660 lookup, SHA-256, `config.json` and the environment live in `ps2x_shared`.

- [x] **Step 6: No RED exists for a move; the proof is that nothing changed.** Build and run:

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests socom_unzipped_launcher -j 8
( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests|Failed:"
```

Expected: `Total Tests: B`, `Failed: 0`. Then `git -C . status --short third_party/ps2recomp | grep '^R'` lists exactly six renames, and `grep -rn "ps2xLauncher/src/launcher_config\|ps2xLauncher/include/launcher/launcher_config" --include=CMakeLists.txt --include=*.cmake --include=*.sh --include=*.py --include=*.yml .` prints nothing (no script names the old paths; verified when this plan was written).

- [x] **Step 7: `./build.sh test` exit 0, then commit.**

```bash
git add third_party/ps2recomp/ps2xShared/CMakeLists.txt
git commit -m "refactor: ps2x_shared -- iso9660, sha256 and launcher_config move out of the launcher so the runner can read config.json without linking it (R126); no behaviour change

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared \
  third_party/ps2recomp/ps2xLauncher/include/launcher/iso9660.h \
  third_party/ps2recomp/ps2xLauncher/include/launcher/sha256.h \
  third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h \
  third_party/ps2recomp/ps2xLauncher/src/iso9660.cpp \
  third_party/ps2recomp/ps2xLauncher/src/sha256.cpp \
  third_party/ps2recomp/ps2xLauncher/src/launcher_config.cpp \
  third_party/ps2recomp/ps2xLauncher/CMakeLists.txt \
  third_party/ps2recomp/CMakeLists.txt
git push
```

---

## Task 2 — The taxonomy: one header, read by C++ and by Python  **[Opus]**

**Files:**
- Create: `ps2xShared/include/ps2x/exit_codes.h`, `ps2xTest/src/exit_codes_tests.cpp`, `tools_py/exit_codes.py`, `tools_py/tests/test_exit_codes_table.py`
- Modify: `ps2xRuntime/include/runtime/gs/gs_gl_caps.h` (:15-24), `ps2xRuntime/CMakeLists.txt` (:584), `ps2xShared/src/launcher_config.cpp` (`exitMessage`, :312-319 before the move), `ps2xShared/include/launcher/launcher_config.h` (:76-79, the comment), `ps2xTest/src/launcher_tests.cpp` (:288-295), `ps2xTest/src/main.cpp`, `ps2xTest/CMakeLists.txt`

**Interfaces (all `inline`/`constexpr`, namespace `ExitCodes`, header-only):**
- `PS2X_EXIT_CODE_TABLE(X)` — the table; each row is `X(Name, code, "slug", "sentence")`. **The only place a code or a sentence is written in the whole tree.**
- `constexpr int kOk, kFailed, kAborted, kNoUsableGl, kDiscNotFound, kDiscNotR0001, kElfMissing, kConfigUnreadable, kCrashed, kOutOfMemory, kCardDirUnwritable` — generated from the table.
- `struct Entry { int code; const char *name; const char *slug; const char *sentence; }`, `kTable[]`, `kTableSize`.
- `const Entry *find(int code)` — `nullptr` when the code is not in the table.
- `int classify(long long rawStatus)` — what the OS reported -> a taxonomy code. NT statuses `0xC0000000-0xCFFFFFFF` and `128 + {SIGILL 4, SIGABRT 6, SIGBUS 7, SIGFPE 8, SIGSEGV 11}` -> `kCrashed`; everything else unchanged.
- `std::string describe(long long rawStatus)` — the sentence; never empty.
- `struct Notice { const char *slug; const char *sentence; }`, `kNoAudioDevice`, `kNoticePrefix` (`"[notice] "`), `std::string noticeLine(const Notice &)`, `std::vector<std::string> noticesIn(const std::string &logText)` — the sentences of every `[notice] ` line, each once, in order.

**Steps:**

- [x] **Step 1: RED (C++).** Create `ps2xTest/src/exit_codes_tests.cpp`:

```cpp
// Sprint 9 Goal 1: the exit-code taxonomy -- one table, shared by the runner and the launcher.
#include "MiniTest.h"
#include "ps2x/exit_codes.h"
#include "runtime/gs/gs_gl_caps.h"
#include "launcher/launcher_config.h"

#include <set>
#include <string>
#include <vector>

void register_exit_codes_tests()
{
    MiniTest::Case("ExitCodes", [](TestCase &tc)
    {
        tc.Run("every code is a byte outside the shell's range, appears once, and has a sentence that fits the line", [](TestCase &t)
        {
            std::set<int> codes;
            std::set<std::string> slugs;
            for (const ExitCodes::Entry &e : ExitCodes::kTable)
            {
                t.IsTrue(e.code >= 0 && e.code <= 255, std::string(e.name) + ": fits a byte");
                t.IsTrue(e.code < 126 || e.code > 165, std::string(e.name) + ": outside the shell's 126-165");
                t.IsTrue(codes.insert(e.code).second, std::string(e.name) + ": its code is used once");
                t.IsTrue(slugs.insert(e.slug).second, std::string(e.name) + ": its slug is used once");
                const std::string s = e.sentence;
                t.IsTrue(!s.empty() && s.size() <= 120, std::string(e.name) + ": a sentence of at most 120 characters");
                t.IsTrue(!s.empty() && s.back() == '.', std::string(e.name) + ": ends with a full stop");
                t.IsTrue(s.find('"') == std::string::npos, std::string(e.name) + ": no double quote (tools_py/exit_codes.py reads the table with a regex)");
            }
            t.Equals(ExitCodes::kTableSize, 11, "eleven codes: 0, 1, 3, 65 and the seven this goal adds");
        });

        tc.Run("the codes themselves: 65 kept, 66-72 added, GsGlCaps agrees with the table", [](TestCase &t)
        {
            t.Equals(ExitCodes::kOk, 0, "ok");
            t.Equals(ExitCodes::kFailed, 1, "the runner's unnamed failure, as it leaves today");
            t.Equals(ExitCodes::kAborted, 3, "abort() on the mingw CRT, and LoadExecPS2");
            t.Equals(ExitCodes::kNoUsableGl, 65, "Sprint 7's code keeps its number");
            t.Equals(GsGlCaps::kExitCode, ExitCodes::kNoUsableGl, "gs_gl_caps.h takes its number from the table");
            t.Equals(ExitCodes::kDiscNotFound, 66, "disc not found");
            t.Equals(ExitCodes::kDiscNotR0001, 67, "disc is not r0001");
            t.Equals(ExitCodes::kElfMissing, 68, "game ELF missing");
            t.Equals(ExitCodes::kConfigUnreadable, 69, "config unreadable");
            t.Equals(ExitCodes::kCrashed, 70, "crash");
            t.Equals(ExitCodes::kOutOfMemory, 71, "out of memory");
            t.Equals(ExitCodes::kCardDirUnwritable, 72, "memory-card directory unwritable");
            t.IsNull(ExitCodes::find(64), "64 is not ours");
            t.IsNotNull(ExitCodes::find(72), "72 is");
        });

        tc.Run("classify: a native crash status is 70 on both platforms, a plain code is itself", [](TestCase &t)
        {
            t.Equals(ExitCodes::classify(static_cast<int>(0xC0000005u)), ExitCodes::kCrashed, "Windows access violation, as GetExitCodeProcess hands it over in an int");
            t.Equals(ExitCodes::classify(0xC0000005LL), ExitCodes::kCrashed, "and as Python's subprocess reports it, unsigned");
            t.Equals(ExitCodes::classify(static_cast<int>(0xC00000FDu)), ExitCodes::kCrashed, "stack overflow");
            t.Equals(ExitCodes::classify(static_cast<int>(0xC0000409u)), ExitCodes::kCrashed, "the UCRT's fast-fail abort");
            t.Equals(ExitCodes::classify(139), ExitCodes::kCrashed, "128 + SIGSEGV, posix_glue.cpp's convention");
            t.Equals(ExitCodes::classify(135), ExitCodes::kCrashed, "SIGBUS");
            t.Equals(ExitCodes::classify(132), ExitCodes::kCrashed, "SIGILL");
            t.Equals(ExitCodes::classify(136), ExitCodes::kCrashed, "SIGFPE");
            t.Equals(ExitCodes::classify(134), ExitCodes::kCrashed, "SIGABRT: std::terminate on Linux");
            t.Equals(ExitCodes::classify(137), 137, "SIGKILL is not a crash: someone, or the OOM killer, ended it");
            t.Equals(ExitCodes::classify(143), 143, "nor is SIGTERM");
            t.Equals(ExitCodes::classify(0), 0, "0 is 0");
            t.Equals(ExitCodes::classify(65), 65, "a taxonomy code is itself");
            t.Equals(ExitCodes::classify(-1), -1, "0xFFFFFFFF is not an NT error status");
        });

        tc.Run("describe: the table's sentence, the crash sentence for a native status, the number for a stranger", [](TestCase &t)
        {
            t.Equals(ExitCodes::describe(0), std::string("The last run exited normally."), "0");
            t.Equals(ExitCodes::describe(66), std::string("The disc image was not found. Open the DISC page and choose your SOCOM II ISO again."), "66");
            t.Equals(ExitCodes::describe(static_cast<int>(0xC0000005u)), std::string(ExitCodes::find(70)->sentence), "an access violation reads as the crash sentence");
            t.Equals(ExitCodes::describe(139), std::string(ExitCodes::find(70)->sentence), "so does SIGSEGV");
            t.Equals(ExitCodes::describe(42), std::string("The game closed with code 42. Press SAVE DIAGNOSTICS to collect the log."), "an unknown code names itself");
            t.Equals(launcher::exitMessage(65),
                     std::string("Your GPU or driver is missing OpenGL 3.3 with dual-source blending; the game ran on the slow CPU renderer."),
                     "the launcher's exitMessage is this table, and 65 kept Sprint 7's words");
            t.Equals(launcher::exitMessage(71), ExitCodes::describe(71), "exitMessage is describe");
        });

        tc.Run("notices: a non-fatal report is a log line the launcher can read back", [](TestCase &t)
        {
            const std::string line = ExitCodes::noticeLine(ExitCodes::kNoAudioDevice);
            t.Equals(line, std::string("[notice] no-audio-device: No audio device was found; the game ran without sound."), "the line's shape");
            const std::string log = "INFO: boot\r\n" + line + "\r\n[gs-gl] initialised: 3.3.0\n" + line + "\n[notice] malformed\n";
            const std::vector<std::string> found = ExitCodes::noticesIn(log);
            t.Equals(static_cast<int>(found.size()), 1, "one notice, reported once however often it was printed; a line with no sentence is skipped");
            if (!found.empty())
                t.Equals(found[0], std::string("No audio device was found; the game ran without sound."), "the sentence, without the tag, without the CR");
            t.IsTrue(ExitCodes::noticesIn("no notices here\n").empty(), "a clean log has none");
        });
    });
}
```

Register it: in `ps2xTest/src/main.cpp` add `void register_exit_codes_tests();` after line 27 (`void register_launcher_tests();`) and `register_exit_codes_tests();` after the `register_launcher_tests();` call (line 96); in `ps2xTest/CMakeLists.txt` add `    src/exit_codes_tests.cpp` after `    src/launcher_tests.cpp` in `ps2_test_lib`'s source list.

Run: `cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8`. **Expected RED:** the build fails with `fatal error: 'ps2x/exit_codes.h' file not found` in `exit_codes_tests.cpp`.

- [x] **Step 2: RED (Python).** Create `tools_py/tests/test_exit_codes_table.py`:

```python
"""Sprint 9 Goal 1: the exit-code table in ps2xShared/include/ps2x/exit_codes.h, read from Python.

The header is the one place a code or its sentence is written; tools_py/exit_codes.py reads it with a
regex so the harness, these tests and the launcher can never disagree about what 66 means."""
import unittest

from tools_py import exit_codes


class ExitCodeTableTest(unittest.TestCase):
    def test_the_header_parses_into_eleven_rows(self):
        rows = exit_codes.table()
        self.assertEqual([r["code"] for r in rows], [0, 1, 3, 65, 66, 67, 68, 69, 70, 71, 72])
        self.assertEqual(rows[3]["name"], "NoUsableGl")
        self.assertEqual(rows[3]["slug"], "no-usable-gl")

    def test_every_code_is_a_byte_outside_the_shells_range_and_unique(self):
        rows = exit_codes.table()
        codes = [r["code"] for r in rows]
        self.assertEqual(len(codes), len(set(codes)))
        for r in rows:
            self.assertTrue(0 <= r["code"] <= 255, r)
            self.assertFalse(126 <= r["code"] <= 165, r)
            self.assertTrue(0 < len(r["sentence"]) <= 120, r)
            self.assertTrue(r["sentence"].endswith("."), r)

    def test_65_is_still_the_gl_fallback(self):
        self.assertIn("OpenGL 3.3", exit_codes.sentence(65))

    def test_classify_folds_native_crash_statuses_onto_70(self):
        self.assertEqual(exit_codes.classify(3221225477), 70)   # 0xC0000005 as subprocess reports it on Windows
        self.assertEqual(exit_codes.classify(-11), 70)          # subprocess reports "killed by SIGSEGV" as -11 on POSIX
        self.assertEqual(exit_codes.classify(-6), 70)           # SIGABRT
        self.assertEqual(exit_codes.classify(139), 70)          # a shell's 128 + 11
        self.assertEqual(exit_codes.classify(-9), 137)          # SIGKILL is not a crash
        self.assertEqual(exit_codes.classify(66), 66)
        self.assertEqual(exit_codes.classify(0), 0)

    def test_describe_matches_the_headers_fallback(self):
        self.assertEqual(exit_codes.describe(42), "The game closed with code 42. Press SAVE DIAGNOSTICS to collect the log.")
        self.assertEqual(exit_codes.describe(-11), exit_codes.sentence(70))


if __name__ == "__main__":
    unittest.main()
```

Run: `python -m unittest tools_py.tests.test_exit_codes_table -v`. **Expected RED:** `ImportError: cannot import name 'exit_codes' from 'tools_py'`.

- [x] **Step 3: Write `ps2xShared/include/ps2x/exit_codes.h`.**

```cpp
#pragma once

// Sprint 9 Goal 1: what the game's exit code means -- decided once, for the runner that leaves with it
// and the launcher that reads it. Header-only and free of every other header in this tree, so
// ps2xRuntime, ps2xLauncher and ps2xTest can all include it; tools_py/exit_codes.py reads the table
// below with a regex, so a row's shape is part of the contract:
//
//     X(Name, <decimal code>, "slug", "One plain sentence, at most 120 characters, no double quote.")
//
// Rules (tools_py/tests/test_exit_codes_table.py and the ExitCodes suite enforce them): a code fits a
// byte, stays outside the shell's 126-165, is used once, and 65 keeps the meaning Sprint 7 gave it.
// 1 and 3 are not new: they are what this process already leaves with, given a name and a sentence.
//
// A crash has no row the runner ever returns. The Windows vectored handler and the Linux sigaction
// handler (game_overrides_socom2.cpp) print their report and let the process die the native way --
// an NT status such as 0xC0000005, or a signal the launcher reads as 128 + n -- and classify() folds
// those onto kCrashed for whoever reads the status (R128).

#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#define PS2X_EXIT_CODE_TABLE(X) \
    X(Ok, 0, "ok", "The last run exited normally.") \
    X(Failed, 1, "failed", "The game stopped on an error it did not name. Press SAVE DIAGNOSTICS; the end of the log says more.") \
    X(Aborted, 3, "aborted", "The game stopped itself after an internal error. Press SAVE DIAGNOSTICS; the end of the log says why.") \
    X(NoUsableGl, 65, "no-usable-gl", "Your GPU or driver is missing OpenGL 3.3 with dual-source blending; the game ran on the slow CPU renderer.") \
    X(DiscNotFound, 66, "disc-not-found", "The disc image was not found. Open the DISC page and choose your SOCOM II ISO again.") \
    X(DiscNotR0001, 67, "disc-not-r0001", "That disc image is not SOCOM II NTSC r0001 (SCUS-97275). This build plays only that disc.") \
    X(ElfMissing, 68, "elf-missing", "socom2_game.elf is missing or damaged. Unpack the download again and keep every file together.") \
    X(ConfigUnreadable, 69, "config-unreadable", "config.json could not be read. Delete it and start the launcher, which writes a new one.") \
    X(Crashed, 70, "crashed", "The game crashed. Press SAVE DIAGNOSTICS and send the zip; it holds the crash record.") \
    X(OutOfMemory, 71, "out-of-memory", "The game ran out of memory. Close other programs, or lower the render scale on the VIDEO page.") \
    X(CardDirUnwritable, 72, "card-dir-unwritable", "The memory-card folder cannot be written. Move the game out of a protected folder and try again.")

namespace ExitCodes
{
#define PS2X_EXIT_CODE_CONSTANT(Name, code, slug, sentence) constexpr int k##Name = code;
    PS2X_EXIT_CODE_TABLE(PS2X_EXIT_CODE_CONSTANT)
#undef PS2X_EXIT_CODE_CONSTANT

    struct Entry
    {
        int code;
        const char *name;
        const char *slug;
        const char *sentence;
    };

#define PS2X_EXIT_CODE_ENTRY(Name, code, slug, sentence) Entry{code, #Name, slug, sentence},
    inline constexpr Entry kTable[] = {PS2X_EXIT_CODE_TABLE(PS2X_EXIT_CODE_ENTRY)};
#undef PS2X_EXIT_CODE_ENTRY
    inline constexpr int kTableSize = static_cast<int>(sizeof(kTable) / sizeof(kTable[0]));

    inline const Entry *find(int code)
    {
        for (const Entry &e : kTable)
            if (e.code == code)
                return &e;
        return nullptr;
    }

    // What the operating system reported -> a code out of the table where there is one. `raw` is
    // GetExitCodeProcess's DWORD (as an int or unsigned), or posix_glue.cpp's WEXITSTATUS / 128 + signal.
    inline int classify(long long raw)
    {
        const uint32_t u = static_cast<uint32_t>(raw);
        if ((u & 0xF0000000u) == 0xC0000000u)
            return kCrashed;   // an NT error status: access violation, stack overflow, illegal instruction, fast-fail
        switch (raw)
        {
        case 128 + 4:    // SIGILL
        case 128 + 6:    // SIGABRT: std::terminate -> abort() on Linux
        case 128 + 7:    // SIGBUS
        case 128 + 8:    // SIGFPE
        case 128 + 11:   // SIGSEGV
            return kCrashed;
        default:
            return static_cast<int>(raw);
        }
    }

    // The sentence for whatever the process left with. Never empty.
    inline std::string describe(long long raw)
    {
        const int code = classify(raw);
        if (const Entry *e = find(code))
            return e->sentence;
        char buf[128];
        std::snprintf(buf, sizeof(buf), "The game closed with code %d. Press SAVE DIAGNOSTICS to collect the log.", code);
        return buf;
    }

    // ---- notices: something the player should hear about that is not a reason to stop ----------------
    // The runner prints noticeLine() to its log; the launcher reads the log back with noticesIn() and
    // appends the sentences to the LAST RUN line (R129).
    struct Notice
    {
        const char *slug;
        const char *sentence;
    };

    inline constexpr const char *kNoticePrefix = "[notice] ";
    inline constexpr Notice kNoAudioDevice{"no-audio-device", "No audio device was found; the game ran without sound."};

    inline std::string noticeLine(const Notice &notice)
    {
        return std::string(kNoticePrefix) + notice.slug + ": " + notice.sentence;
    }

    inline std::vector<std::string> noticesIn(const std::string &logText)
    {
        std::vector<std::string> out;
        const std::string prefix = kNoticePrefix;
        size_t pos = 0;
        while (pos < logText.size())
        {
            size_t end = logText.find('\n', pos);
            if (end == std::string::npos)
                end = logText.size();
            std::string line = logText.substr(pos, end - pos);
            pos = end + 1;
            if (!line.empty() && line.back() == '\r')
                line.pop_back();
            if (line.rfind(prefix, 0) != 0)
                continue;
            const size_t colon = line.find(": ", prefix.size());
            if (colon == std::string::npos || colon + 2 >= line.size())
                continue;
            const std::string sentence = line.substr(colon + 2);
            bool seen = false;
            for (const std::string &s : out)
                seen = seen || s == sentence;
            if (!seen)
                out.push_back(sentence);
        }
        return out;
    }
}
```

- [x] **Step 4: `gs_gl_caps.h` takes its number from the table.** In `ps2xRuntime/include/runtime/gs/gs_gl_caps.h` add `#include "ps2x/exit_codes.h"` after `#include <string>` (line 18) and replace line 24:

```cpp
    // The process exit code that says "the game ran, but on the CPU rasterizer". The number and its
    // sentence live in ps2x/exit_codes.h; this name stays because ps2_runtime.cpp:2628 sets it.
    constexpr int kExitCode = ExitCodes::kNoUsableGl;
    static_assert(kExitCode == 65, "Sprint 7 Task 1a's code does not move");
```

In `ps2xRuntime/CMakeLists.txt` line 584 becomes:

```cmake
target_link_libraries(ps2_runtime PUBLIC ps2_host_backend ffmpeg ps2_iop ps2x_shared)
```

- [x] **Step 5: `launcher::exitMessage` becomes the lookup.** In `ps2xShared/src/launcher_config.cpp` add `#include "ps2x/exit_codes.h"` under the first include and replace the body of `exitMessage`:

```cpp
    std::string exitMessage(int exitCode)
    {
        // Sprint 9 Goal 1: the sentence lives in the one table the runner also reads (ps2x/exit_codes.h).
        return ExitCodes::describe(exitCode);
    }
```

In `ps2xShared/include/launcher/launcher_config.h` replace the comment at lines 76-78 with: `// What the game's exit status means, in a sentence for the player: ExitCodes::describe (ps2x/exit_codes.h). Never empty.`

- [x] **Step 6: The old case's two assertions change on purpose.** `ps2xTest/src/launcher_tests.cpp:293-294` assert that 0 and 1 say nothing; that was Sprint 7's contract and this goal replaces it. Replace those two lines with:

```cpp
            t.Equals(launcher::exitMessage(0), std::string("The last run exited normally."), "a clean exit says so");
            t.IsTrue(launcher::exitMessage(1).find("SAVE DIAGNOSTICS") != std::string::npos, "an unnamed failure points at the diagnostics (Sprint 9 Goal 1: no ending is silent)");
```

- [x] **Step 7: Write `tools_py/exit_codes.py`.**

```python
"""The game's exit codes, read out of the C++ header that defines them.

`third_party/ps2recomp/ps2xShared/include/ps2x/exit_codes.h` is the one place a code or its sentence
is written (Sprint 9 Goal 1). This module parses its X-macro rows so Python never carries a copy."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADER = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xShared", "include", "ps2x", "exit_codes.h")

_ROW = re.compile(r'^\s*X\((\w+),\s*(\d+),\s*"([^"]+)",\s*"([^"]+)"\)', re.M)

CRASH_SIGNALS = (4, 6, 7, 8, 11)   # SIGILL, SIGABRT, SIGBUS, SIGFPE, SIGSEGV -- ExitCodes::classify's list


def table(path=HEADER):
    """[{name, code, slug, sentence}, ...] in the header's order."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return [{"name": m.group(1), "code": int(m.group(2)), "slug": m.group(3), "sentence": m.group(4)}
            for m in _ROW.finditer(text)]


def code(name, path=HEADER):
    for row in table(path):
        if row["name"] == name:
            return row["code"]
    raise KeyError(name)


def sentence(value, path=HEADER):
    for row in table(path):
        if row["code"] == value:
            return row["sentence"]
    return None


def classify(returncode, path=HEADER):
    """subprocess's returncode -> a taxonomy code. POSIX reports a signal death as -n; Windows reports an
    NT status as a large unsigned number. Mirrors ExitCodes::classify."""
    if returncode < 0:
        returncode = 128 - returncode
    if (returncode & 0xF0000000) == 0xC0000000:
        return code("Crashed", path)
    if returncode in tuple(128 + s for s in CRASH_SIGNALS):
        return code("Crashed", path)
    return returncode


def describe(returncode, path=HEADER):
    value = classify(returncode, path)
    found = sentence(value, path)
    if found is not None:
        return found
    return "The game closed with code %d. Press SAVE DIAGNOSTICS to collect the log." % value
```

- [x] **Step 8: GREEN.**

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests ps2_runtime -j 8
( cd third_party/ps2recomp/build-clang/ps2xTest && PS2X_TEST_SUITE=ExitCodes ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|      - |Total Tests|Failed:"
( cd third_party/ps2recomp/build-clang/ps2xTest && PS2X_TEST_SUITE=Launcher ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|      - |Total Tests|Failed:"
python -m unittest tools_py.tests.test_exit_codes_table -v
```

Expected: `Total Tests: 5` / `Failed: 0`; the Launcher suite `Failed: 0`; Python `Ran 5 tests … OK`. Building `ps2_runtime` proves `gs_gl_caps.h`'s new include resolves for the library the runner is made of (the runner itself is rebuilt in Task 6).

- [x] **Step 9: `./build.sh test` exit 0 (`Total Tests: B + 5`, Python `P + 5`), then commit.**

```bash
git add third_party/ps2recomp/ps2xShared/include/ps2x/exit_codes.h third_party/ps2recomp/ps2xTest/src/exit_codes_tests.cpp tools_py/exit_codes.py tools_py/tests/test_exit_codes_table.py
git commit -m "feat: the exit-code taxonomy in one header -- 65 kept, 66-72 added, 1 and 3 named, native crash statuses classified as 70 (R127, R128); the launcher's sentence is a lookup and Python reads the same table

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared/include/ps2x/exit_codes.h \
  third_party/ps2recomp/ps2xShared/src/launcher_config.cpp \
  third_party/ps2recomp/ps2xShared/include/launcher/launcher_config.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_caps.h \
  third_party/ps2recomp/ps2xRuntime/CMakeLists.txt \
  third_party/ps2recomp/ps2xTest/src/exit_codes_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/main.cpp \
  third_party/ps2recomp/ps2xTest/CMakeLists.txt \
  tools_py/exit_codes.py tools_py/tests/test_exit_codes_table.py
git push
```

---

## Task 3 — LAST RUN says the sentence; `--selftest` lists every one  **[Opus]**

**Files:**
- Modify: `ps2xShared/include/launcher/launcher_config.h`, `ps2xShared/src/launcher_config.cpp`, `ps2xLauncher/src/main.cpp` (:60-68 `readText`, :467, :497-505, :587, :672-688), `ps2xTest/src/launcher_tests.cpp`

**Interfaces (namespace `launcher`):**
- `std::string lastRunLine(long long rawExitStatus, const std::string &logText)` — `ExitCodes::describe(raw)`, then each notice found in `logText` appended after one space.
- `std::vector<std::string> selftestExitLines()` — one line per table row: `exit <code, width 3> <slug>: <sentence>`.

**Steps:**

- [x] **Step 1: RED.** In `ps2xTest/src/launcher_tests.cpp`, directly after the case that ends at line 295 (`"exit code 65 tells the player…"`), add:

```cpp
        tc.Run("LAST RUN: the code's sentence, a crash by its native status, a stranger by number, a notice appended", [](TestCase &t)
        {
            t.Equals(launcher::lastRunLine(0, ""), std::string("The last run exited normally."), "a clean run");
            t.Equals(launcher::lastRunLine(67, ""),
                     std::string("That disc image is not SOCOM II NTSC r0001 (SCUS-97275). This build plays only that disc."), "67");
            t.Equals(launcher::lastRunLine(static_cast<int>(0xC0000005u), ""),
                     std::string("The game crashed. Press SAVE DIAGNOSTICS and send the zip; it holds the crash record."), "Windows' access violation");
            t.Equals(launcher::lastRunLine(139, ""), launcher::lastRunLine(static_cast<int>(0xC0000005u), ""), "and Linux's SIGSEGV read the same");
            t.Equals(launcher::lastRunLine(42, ""), std::string("The game closed with code 42. Press SAVE DIAGNOSTICS to collect the log."), "never 'the game exited'");
            const std::string log = "INFO: AUDIO: Failed to initialize playback device\n[notice] no-audio-device: No audio device was found; the game ran without sound.\n";
            t.Equals(launcher::lastRunLine(0, log),
                     std::string("The last run exited normally. No audio device was found; the game ran without sound."),
                     "audio absent is not an exit: it rides on whatever the exit was");
        });

        tc.Run("the selftest lists every exit code with its sentence", [](TestCase &t)
        {
            const std::vector<std::string> lines = launcher::selftestExitLines();
            t.Equals(static_cast<int>(lines.size()), 11, "one line per code in the table");
            auto has = [&](const std::string &l) { return std::find(lines.begin(), lines.end(), l) != lines.end(); };
            t.IsTrue(has("exit   0 ok: The last run exited normally."), "0");
            t.IsTrue(has("exit  65 no-usable-gl: Your GPU or driver is missing OpenGL 3.3 with dual-source blending; the game ran on the slow CPU renderer."), "65");
            t.IsTrue(has("exit  72 card-dir-unwritable: The memory-card folder cannot be written. Move the game out of a protected folder and try again."), "72");
        });
```

Build `ps2x_tests`. **Expected RED:** `error: no member named 'lastRunLine' in namespace 'launcher'`.

- [x] **Step 2: Implement.** In `ps2xShared/include/launcher/launcher_config.h`, under `exitMessage`'s declaration:

```cpp
    // Sprint 9 Goal 1: the PLAY page's LAST RUN line. `rawExitStatus` is GameProcess::exitCode() as the
    // glue reports it (an NT status on Windows, 128 + signal on POSIX, else the runner's own code);
    // `logText` is the head of that run's log, read for "[notice] " lines (no audio device), whose
    // sentences follow the exit's own.
    std::string lastRunLine(long long rawExitStatus, const std::string &logText);

    // What --selftest prints: "exit <code> <slug>: <sentence>" for every row of ExitCodes::kTable.
    std::vector<std::string> selftestExitLines();
```

In `ps2xShared/src/launcher_config.cpp`, under `exitMessage`:

```cpp
    std::string lastRunLine(long long rawExitStatus, const std::string &logText)
    {
        std::string line = ExitCodes::describe(rawExitStatus);
        for (const std::string &notice : ExitCodes::noticesIn(logText))
            line += " " + notice;
        return line;
    }

    std::vector<std::string> selftestExitLines()
    {
        std::vector<std::string> lines;
        for (const ExitCodes::Entry &e : ExitCodes::kTable)
        {
            char head[64];
            std::snprintf(head, sizeof(head), "exit %3d %s: ", e.code, e.slug);
            lines.push_back(std::string(head) + e.sentence);
        }
        return lines;
    }
```

- [x] **Step 3: Wire `ps2xLauncher/src/main.cpp`.** Four edits:

  (a) Under `readText` (after line 68), a bounded reader — a run log can be hundreds of megabytes and the notice is printed at boot:

```cpp
    // The first `maxBytes` of a file: the run log's head, where the boot lines (GL, audio, notices) are.
    std::string readHead(const fs::path &p, size_t maxBytes)
    {
        std::ifstream in(p, std::ios::binary);
        if (!in)
            return {};
        std::string out(maxBytes, '\0');
        in.read(out.data(), static_cast<std::streamsize>(maxBytes));
        out.resize(static_cast<size_t>(in.gcount()));
        return out;
    }
```

  (b) Beside `std::string lastLog;` (line 587) add `long long lastExitRaw = 0; bool haveLastExit = false;` (Task 9 reads them).

  (c) Replace lines 678-683 (from the `// Task 1a: 65 means…` comment through `app.status = app.exitLine;`) with:

```cpp
                // Sprint 9 Goal 1: every ending has a sentence (ps2x/exit_codes.h), and a non-fatal notice
                // in the log -- no audio device -- rides along with it.
                lastExitRaw = game.exitCode();
                haveLastExit = true;
                game.close();
                app.exitLine = launcher::lastRunLine(lastExitRaw, readHead(lastLog, 256u * 1024u));
                app.status = app.exitLine;
```

  (d) In the `--selftest` block, after the `env:` loop (line 503), and in `fillFakeState` line 467:

```cpp
        for (const std::string &line : launcher::selftestExitLines())
            std::printf("%s\n", line.c_str());
```

```cpp
        app.exitLine = launcher::exitMessage(0);
```

- [x] **Step 4: GREEN.** Build `ps2x_tests` and `socom_unzipped_launcher`; `PS2X_TEST_SUITE=Launcher` -> `Failed: 0`. Then, with no game running, `dist/socom_unzipped_launcher.exe --selftest | grep -c "^exit "` prints `11` (the bar's "the launcher's selftest shows each sentence"; `--selftest` rewrites `dist/config.json` through `toJson`, as it always has).

- [x] **Step 5: `./build.sh test` exit 0 (`Total Tests: B + 7`), then commit.**

```bash
git commit -m "feat(launcher): LAST RUN shows the exit code's sentence instead of 'the game exited', with the log's notices appended; --selftest lists every sentence

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared/include/launcher/launcher_config.h \
  third_party/ps2recomp/ps2xShared/src/launcher_config.cpp \
  third_party/ps2recomp/ps2xLauncher/src/main.cpp \
  third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp
git push
```

---

## Task 4 — Preflight: four checks before a window opens  **[Opus]**

**Files:**
- Create: `ps2xShared/include/ps2x/preflight.h`, `ps2xShared/src/preflight.cpp`, `ps2xTest/src/preflight_tests.cpp`
- Modify: `ps2xShared/CMakeLists.txt`, `ps2xTest/CMakeLists.txt`, `ps2xTest/src/main.cpp`

**Interfaces (namespace `Preflight`):**
- `struct Input { std::filesystem::path elfPath; std::string cdImageEnv; std::filesystem::path cardDir; bool checkDisc = true; std::string discElfName = launcher::kSocom2ElfName; std::string expectedElfSha256 = launcher::kSocom2R0001ElfSha256; }`
- `struct Result { int code = ExitCodes::kOk; std::string detail; std::filesystem::path disc; }`
- `std::filesystem::path findDisc(const std::filesystem::path &elfPath, const std::string &cdImageEnv)` — **the same search `configureCdImage` does** (`game_overrides_socom2.cpp:552-581`): `PS2X_CD_IMAGE` when set, else the first `*.iso` (any case) beside the ELF, else one folder up; empty when none.
- `bool directoryWritable(const std::filesystem::path &dir, std::string &why)` — creates it if absent, writes and removes a probe file.
- `Result run(const Input &)` — order: ELF -> card folder -> disc found -> disc is r0001 (R130). The first failure wins.
- `std::string logLine(const Result &)` — `[preflight] exit <code> <slug>: <sentence> (<detail>)`.

**Steps:**

- [x] **Step 1: RED.** Create `ps2xTest/src/preflight_tests.cpp`:

```cpp
// Sprint 9 Goal 1: the checks the runner makes before it opens a window, each driven through the failing
// condition on a real temporary directory, each asserting the code and the sentence.
#include "MiniTest.h"
#include "ps2x/exit_codes.h"
#include "ps2x/preflight.h"

#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace
{
    namespace fs = std::filesystem;

    // <temp>/ps2x_preflight_<ticks>_<n>/outer/home -- two levels, so "one folder up" is ours too.
    fs::path makeHome()
    {
        static int counter = 0;
        const auto ticks = std::chrono::steady_clock::now().time_since_epoch().count();
        const fs::path root = fs::temp_directory_path() / ("ps2x_preflight_" + std::to_string(ticks) + "_" + std::to_string(counter++));
        std::error_code ec;
        fs::create_directories(root / "outer" / "home", ec);
        return root / "outer" / "home";
    }

    void removeHome(const fs::path &home)
    {
        std::error_code ec;
        fs::remove_all(home.parent_path().parent_path(), ec);
    }

    void writeBytes(const fs::path &p, const std::vector<uint8_t> &bytes)
    {
        std::ofstream out(p, std::ios::binary | std::ios::trunc);
        out.write(reinterpret_cast<const char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    }

    void writeText(const fs::path &p, const std::string &text)
    {
        writeBytes(p, std::vector<uint8_t>(text.begin(), text.end()));
    }

    // A 20-sector ISO 9660 image: PVD at 16, root directory at 18, one file at 19 holding "hello".
    // `fileName` is the root-directory name of that file ("SCUS_972.75;1" for a SOCOM-shaped disc).
    std::vector<uint8_t> isoWith(const char *fileName)
    {
        std::vector<uint8_t> img(20u * 2048u, 0u);
        uint8_t *pvd = img.data() + 16u * 2048u;
        pvd[0] = 1;
        std::memcpy(pvd + 1, "CD001", 5);
        auto put32both = [](uint8_t *at, uint32_t v)
        {
            at[0] = static_cast<uint8_t>(v); at[1] = static_cast<uint8_t>(v >> 8); at[2] = static_cast<uint8_t>(v >> 16); at[3] = static_cast<uint8_t>(v >> 24);
            at[4] = static_cast<uint8_t>(v >> 24); at[5] = static_cast<uint8_t>(v >> 16); at[6] = static_cast<uint8_t>(v >> 8); at[7] = static_cast<uint8_t>(v);
        };
        auto record = [&](uint8_t *at, uint32_t extent, uint32_t size, const char *name, size_t nameLen, uint8_t flags)
        {
            const uint8_t len = static_cast<uint8_t>((33 + nameLen + 1) & ~static_cast<size_t>(1));
            at[0] = len;
            put32both(at + 2, extent);
            put32both(at + 10, size);
            at[25] = flags;
            at[32] = static_cast<uint8_t>(nameLen);
            std::memcpy(at + 33, name, nameLen);
            return len;
        };
        uint8_t *root = pvd + 156;
        root[0] = 34;
        put32both(root + 2, 18u);
        put32both(root + 10, 2048u);
        root[25] = 2;
        root[32] = 1;
        uint8_t *dir = img.data() + 18u * 2048u;
        size_t off = 0;
        off += record(dir + off, 18u, 2048u, "\0", 1, 2);
        off += record(dir + off, 18u, 2048u, "\1", 1, 2);
        off += record(dir + off, 19u, 5u, fileName, std::strlen(fileName), 0);
        std::memcpy(img.data() + 19u * 2048u, "hello", 5);
        return img;
    }

    const char *kSha256OfHello = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824";

    std::string sentenceOf(int code)
    {
        const ExitCodes::Entry *e = ExitCodes::find(code);
        return e ? std::string(e->sentence) : std::string();
    }
}

void register_preflight_tests()
{
    MiniTest::Case("Preflight", [](TestCase &tc)
    {
        tc.Run("68: no socom2_game.elf in the folder", [](TestCase &t)
        {
            const fs::path home = makeHome();
            Preflight::Input in;
            in.elfPath = home / "socom2_game.elf";
            in.cardDir = home / "cards" / "player";
            const Preflight::Result r = Preflight::run(in);
            t.Equals(r.code, ExitCodes::kElfMissing, "the ELF is checked first");
            t.Equals(r.code, 68, "and that is 68");
            t.IsTrue(r.detail.find("socom2_game.elf") != std::string::npos, "the detail names the path it looked at");
            t.IsTrue(Preflight::logLine(r).find("[preflight] exit 68 elf-missing: " + sentenceOf(68)) == 0, "the log line carries the code, the slug and the sentence");
            removeHome(home);
        });

        tc.Run("72: the memory-card folder cannot be created or written", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "socom2_game.elf", "elf");
            writeText(home / "cards", "a file where the cards folder should be");   // portable: no chmod on Windows
            Preflight::Input in;
            in.elfPath = home / "socom2_game.elf";
            in.cardDir = home / "cards" / "player";
            const Preflight::Result r = Preflight::run(in);
            t.Equals(r.code, 72, "a card folder that cannot exist is 72, before the disc is looked for");
            t.IsTrue(Preflight::logLine(r).find(sentenceOf(72)) != std::string::npos, "with its sentence");
            std::string why;
            t.IsTrue(Preflight::directoryWritable(home / "saves" / "deep", why), "a folder that can be created is created and is writable");
            t.IsTrue(fs::is_directory(home / "saves" / "deep"), "it exists afterwards");
            t.IsTrue(!fs::exists(home / "saves" / "deep" / ".ps2x_write_probe"), "and the probe file is gone");
            removeHome(home);
        });

        tc.Run("66: no disc beside the ELF, none one folder up, and a PS2X_CD_IMAGE that is not there", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "socom2_game.elf", "elf");
            Preflight::Input in;
            in.elfPath = home / "socom2_game.elf";
            in.cardDir = home / "cards" / "player";
            Preflight::Result r = Preflight::run(in);
            t.Equals(r.code, 66, "nothing to mount");
            t.IsTrue(Preflight::logLine(r).find(sentenceOf(66)) != std::string::npos, "with its sentence");
            in.cdImageEnv = (home / "gone.iso").string();
            r = Preflight::run(in);
            t.Equals(r.code, 66, "PS2X_CD_IMAGE naming a missing file is the same code");
            t.IsTrue(r.detail.find("gone.iso") != std::string::npos, "and the detail names the file");
            removeHome(home);
        });

        tc.Run("findDisc mirrors configureCdImage: the environment first, then *.iso beside the ELF, then one folder up", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "socom2_game.elf", "elf");
            t.IsTrue(Preflight::findDisc(home / "socom2_game.elf", "").empty(), "nothing yet");
            writeText(home.parent_path() / "Game.ISO", "x");
            t.Equals(Preflight::findDisc(home / "socom2_game.elf", "").filename().string(), std::string("Game.ISO"), "one folder up, any case of .iso");
            writeText(home / "near.iso", "x");
            t.Equals(Preflight::findDisc(home / "socom2_game.elf", "").filename().string(), std::string("near.iso"), "beside the ELF wins over one folder up");
            t.Equals(Preflight::findDisc(home / "socom2_game.elf", "D:/elsewhere.iso").generic_string(), std::string("D:/elsewhere.iso"), "PS2X_CD_IMAGE wins over both, exists or not");
            removeHome(home);
        });

        tc.Run("67: a disc whose SCUS_972.75 is not r0001's, and a disc with no SCUS_972.75 at all", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "socom2_game.elf", "elf");
            writeBytes(home / "disc.iso", isoWith("SCUS_972.75;1"));
            Preflight::Input in;
            in.elfPath = home / "socom2_game.elf";
            in.cardDir = home / "cards" / "player";
            Preflight::Result r = Preflight::run(in);   // the pinned r0001 digest: "hello" is not it
            t.Equals(r.code, 67, "the executable on the disc does not hash to the pinned digest");
            t.IsTrue(Preflight::logLine(r).find(sentenceOf(67)) != std::string::npos, "with its sentence");
            writeBytes(home / "disc.iso", isoWith("SLUS_200.62;1"));
            r = Preflight::run(in);
            t.Equals(r.code, 67, "another game's disc is the same code");
            t.IsTrue(r.detail.find("SCUS_972.75") != std::string::npos, "and the detail says what was not found");
            writeText(home / "disc.iso", "not an iso at all");
            r = Preflight::run(in);
            t.Equals(r.code, 67, "a file that is not a disc image is 'not that disc', not 'not found'");
            removeHome(home);
        });

        tc.Run("0: every check passes, and a non-SOCOM ELF skips the disc", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "socom2_game.elf", "elf");
            writeBytes(home / "disc.iso", isoWith("SCUS_972.75;1"));
            Preflight::Input in;
            in.elfPath = home / "socom2_game.elf";
            in.cardDir = home / "cards" / "player";
            in.expectedElfSha256 = kSha256OfHello;   // the synthetic disc's own digest stands in for r0001's
            Preflight::Result r = Preflight::run(in);
            t.Equals(r.code, 0, "ELF present, card folder writable, disc found, digest matches");
            t.Equals(r.disc.filename().string(), std::string("disc.iso"), "and it says which disc it checked");
            t.IsTrue(fs::is_directory(home / "cards" / "player"), "the card folder now exists");
            fs::remove(home / "disc.iso");
            in.checkDisc = false;
            r = Preflight::run(in);
            t.Equals(r.code, 0, "checkDisc=false (another game's ELF): no disc is no error");
            removeHome(home);
        });
    });
}
```

Register it exactly as Task 2 Step 1 did (`void register_preflight_tests();`, the call, and `    src/preflight_tests.cpp` in `ps2_test_lib`). Build `ps2x_tests`. **Expected RED:** `fatal error: 'ps2x/preflight.h' file not found`.

- [x] **Step 2: Write `ps2xShared/include/ps2x/preflight.h`.**

```cpp
#pragma once

// Sprint 9 Goal 1: what the runner checks BEFORE it opens a window. Today main() calls
// runtime.initialize() (InitWindow, InitAudioDevice) and only then looks at the ELF, and a missing
// disc is a WARNING followed by a black screen (game_overrides_socom2.cpp:577). Each failure here is
// one exit code out of ps2x/exit_codes.h, decided before anything is shown.

#include "launcher/launcher_config.h"
#include "ps2x/exit_codes.h"

#include <filesystem>
#include <string>

namespace Preflight
{
    struct Input
    {
        std::filesystem::path elfPath;       // what main() is about to hand loadELF
        std::string cdImageEnv;              // PS2X_CD_IMAGE's value; empty when unset
        std::filesystem::path cardDir;       // where saves will go: PS2X_MC_DIR, else <elf dir>/mc0
        bool checkDisc = true;               // false for an ELF that is not SOCOM II's
        std::string discElfName = launcher::kSocom2ElfName;
        std::string expectedElfSha256 = launcher::kSocom2R0001ElfSha256;
    };

    struct Result
    {
        int code = ExitCodes::kOk;
        std::string detail;                  // the path or the reason, for the log line
        std::filesystem::path disc;          // the image that was checked, when one was
    };

    // The search configureCdImage() performs (game_overrides_socom2.cpp:552): the environment's image,
    // else the first *.iso beside the ELF, else the first one folder up. Empty when there is none.
    std::filesystem::path findDisc(const std::filesystem::path &elfPath, const std::string &cdImageEnv);

    // Creates `dir` when absent, then writes and removes a probe file in it.
    bool directoryWritable(const std::filesystem::path &dir, std::string &why);

    // ELF -> card folder -> disc found -> disc is r0001. The first failure wins.
    Result run(const Input &input);

    // "[preflight] exit 66 disc-not-found: <sentence> (<detail>)"
    std::string logLine(const Result &result);
}
```

- [x] **Step 3: Write `ps2xShared/src/preflight.cpp`** and add `    src/preflight.cpp` to `ps2x_shared`'s source list.

```cpp
#include "ps2x/preflight.h"

#include "launcher/iso9660.h"
#include "launcher/sha256.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <system_error>
#include <vector>

namespace Preflight
{
    namespace fs = std::filesystem;

    fs::path findDisc(const fs::path &elfPath, const std::string &cdImageEnv)
    {
        if (!cdImageEnv.empty())
            return fs::path(cdImageEnv);
        std::error_code ec;
        fs::path absolute = fs::absolute(elfPath, ec);
        if (ec)
            absolute = elfPath;
        const fs::path elfDir = absolute.parent_path();
        for (const fs::path &dir : {elfDir, elfDir.parent_path()})
        {
            if (dir.empty())
                continue;
            std::error_code iterEc;
            for (fs::directory_iterator it(dir, iterEc), end; !iterEc && it != end; it.increment(iterEc))
            {
                std::string ext = it->path().extension().string();
                std::transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
                if (ext == ".iso")
                    return it->path();
            }
        }
        return {};
    }

    bool directoryWritable(const fs::path &dir, std::string &why)
    {
        std::error_code ec;
        fs::create_directories(dir, ec);
        if (ec || !fs::is_directory(dir, ec))
        {
            why = "cannot create " + dir.string();
            return false;
        }
        const fs::path probe = dir / ".ps2x_write_probe";
        {
            std::ofstream out(probe, std::ios::binary | std::ios::trunc);
            out << 'x';
            out.flush();
            if (!out)
            {
                why = "cannot write in " + dir.string();
                return false;
            }
        }
        fs::remove(probe, ec);
        return true;
    }

    Result run(const Input &input)
    {
        Result r;
        std::error_code ec;
        if (!fs::is_regular_file(input.elfPath, ec))
        {
            r.code = ExitCodes::kElfMissing;
            r.detail = input.elfPath.string();
            return r;
        }
        std::string why;
        if (!directoryWritable(input.cardDir, why))
        {
            r.code = ExitCodes::kCardDirUnwritable;
            r.detail = why;
            return r;
        }
        if (!input.checkDisc)
            return r;

        r.disc = findDisc(input.elfPath, input.cdImageEnv);
        if (r.disc.empty())
        {
            r.code = ExitCodes::kDiscNotFound;
            r.detail = "no .iso beside " + input.elfPath.filename().string() + " or one folder up, and PS2X_CD_IMAGE is not set";
            return r;
        }
        if (!fs::is_regular_file(r.disc, ec))
        {
            r.code = ExitCodes::kDiscNotFound;
            r.detail = r.disc.string();
            return r;
        }
        const iso9660::Reader read = iso9660::fileReader(r.disc.string());
        if (!read)
        {
            r.code = ExitCodes::kDiscNotFound;
            r.detail = "cannot open " + r.disc.string();
            return r;
        }
        iso9660::FileEntry entry;
        std::vector<uint8_t> bytes;
        if (!iso9660::findRootFile(read, input.discElfName, entry) || !iso9660::readFile(read, entry, bytes))
        {
            r.code = ExitCodes::kDiscNotR0001;
            r.detail = "no readable " + input.discElfName + " in " + r.disc.string();
            return r;
        }
        const std::string digest = sha256::hex(bytes.data(), bytes.size());
        if (digest != input.expectedElfSha256)
        {
            r.code = ExitCodes::kDiscNotR0001;
            r.detail = input.discElfName + " in " + r.disc.string() + " hashes to " + digest;
            return r;
        }
        return r;
    }

    std::string logLine(const Result &result)
    {
        const ExitCodes::Entry *e = ExitCodes::find(result.code);
        return "[preflight] exit " + std::to_string(result.code) + " " + (e ? e->slug : "unknown") + ": " +
               (e ? e->sentence : "") + " (" + result.detail + ")";
    }
}
```

- [x] **Step 4: GREEN.** Build; `PS2X_TEST_SUITE=Preflight ./ps2x_tests.exe` -> `Total Tests: 6`, `Failed: 0`.

- [x] **Step 5: `./build.sh test` exit 0 (`Total Tests: B + 13`), then commit.**

```bash
git add third_party/ps2recomp/ps2xShared/include/ps2x/preflight.h third_party/ps2recomp/ps2xShared/src/preflight.cpp third_party/ps2recomp/ps2xTest/src/preflight_tests.cpp
git commit -m "feat: Preflight -- the ELF, the card folder, the disc and its r0001 digest checked before a window opens, each failure an exit code with its sentence (R130); not wired into the runner yet

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared/include/ps2x/preflight.h \
  third_party/ps2recomp/ps2xShared/src/preflight.cpp \
  third_party/ps2recomp/ps2xShared/CMakeLists.txt \
  third_party/ps2recomp/ps2xTest/src/preflight_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/main.cpp \
  third_party/ps2recomp/ps2xTest/CMakeLists.txt
git push
```

---

## Task 5 — The bare run: `config.json` beside the exe becomes a launch plan  **[Opus]**

**Files:**
- Create: `ps2xShared/include/ps2x/bare_run.h`, `ps2xShared/src/bare_run.cpp`, `ps2xShared/include/ps2x/exe_dir.h`, `ps2xShared/src/exe_dir.cpp`, `ps2xTest/src/bare_run_tests.cpp`
- Modify: `ps2xShared/CMakeLists.txt`, `ps2xTest/CMakeLists.txt`, `ps2xTest/src/main.cpp`

**Interfaces:**
- `const char *ExeDir::platformName()` — `"windows"`, `"linux"` or `"other"` (Task 9's `versions.txt`).
- `std::filesystem::path ExeDir::get()` — the folder holding the running executable (`GetModuleFileNameW` / `readlink("/proc/self/exe")`; the working directory when neither answers, as `win32glue::exeDirectory` does).
- `struct BareRun::Plan { int code = ExitCodes::kOk; std::string detail; std::filesystem::path home, elf, logDir; bool configFound = false; std::vector<std::string> environment; }`
- `BareRun::Plan BareRun::plan(const std::filesystem::path &home)` — `home/config.json` through `launcher::fromJson` and `launcher::environmentFor`, with a relative `PS2X_MC_DIR` made absolute against `home`. **Absent config is not an error** (defaults; the disc hunt may still succeed). Present but unopenable, empty or malformed is `kConfigUnreadable` (R131).
- `int BareRun::applyEnvironment(const std::vector<std::string> &keyValues)` — sets each `KEY=VALUE` **only when `KEY` is not already in the environment**; returns how many it set (R131: the spec's Goal 3 says "the env var kept as an override").
- `std::string BareRun::stamp()` — `YYYYMMDD_HHMMSS`, the launcher's log-name shape (`win32_glue.cpp:198-209`).
- `std::string BareRun::redirectOutput(const std::filesystem::path &logDir)` — stdout and stderr to `logDir/run_<stamp>.log`; returns the path, empty on failure. **Not unit-tested** (it would take the test binary's own stdout); Task 6's Python cases read the file it writes.
- `void BareRun::detachOwnConsole()` — Windows: `FreeConsole()` when this process is the console's only client (a double-click); a no-op otherwise and on POSIX. **Not unit-testable**; R132.

**Steps:**

- [x] **Step 1: RED.** Create `ps2xTest/src/bare_run_tests.cpp`:

```cpp
// Sprint 9 Goal 1: socom2 with no argument reads the launcher's config.json beside it.
#include "MiniTest.h"
#include "ps2x/bare_run.h"
#include "ps2x/exe_dir.h"
#include "ps2x/exit_codes.h"
#include "launcher/launcher_config.h"

#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace
{
    namespace fs = std::filesystem;

    fs::path makeHome()
    {
        static int counter = 0;
        const auto ticks = std::chrono::steady_clock::now().time_since_epoch().count();
        const fs::path home = fs::temp_directory_path() / ("ps2x_bare_" + std::to_string(ticks) + "_" + std::to_string(counter++));
        std::error_code ec;
        fs::create_directories(home, ec);
        return home;
    }

    void writeText(const fs::path &p, const std::string &text)
    {
        std::ofstream out(p, std::ios::binary | std::ios::trunc);
        out << text;
    }

    std::string valueOf(const std::vector<std::string> &env, const std::string &key)
    {
        for (const std::string &kv : env)
            if (kv.rfind(key + "=", 0) == 0)
                return kv.substr(key.size() + 1);
        return "<absent>";
    }
}

void register_bare_run_tests()
{
    MiniTest::Case("BareRun", [](TestCase &tc)
    {
        tc.Run("the launcher's config.json becomes the same environment the launcher would have set", [](TestCase &t)
        {
            const fs::path home = makeHome();
            launcher::Config c;
            c.isoPath = "D:/discs/socom2.iso";
            c.gsScale = 2;
            c.profile = "viper";
            c.serverPreset = "custom";
            c.server = "10.0.0.5";
            writeText(home / "config.json", launcher::toJson(c));
            const BareRun::Plan p = BareRun::plan(home);
            t.Equals(p.code, 0, "a readable config is a plan");
            t.IsTrue(p.configFound, "and it says it read one");
            t.Equals(p.elf, home / "socom2_game.elf", "the ELF is the one beside it");
            t.Equals(p.logDir, home / "logs", "the log goes where the launcher puts it");
            t.Equals(valueOf(p.environment, "PS2X_CD_IMAGE"), std::string("D:/discs/socom2.iso"), "the verified ISO");
            t.Equals(valueOf(p.environment, "PS2X_GS_SCALE"), std::string("2"), "the render scale");
            t.Equals(valueOf(p.environment, "PS2X_SOCOM2_SERVER"), std::string("10.0.0.5"), "the server");
            t.Equals(valueOf(p.environment, "PS2X_SOCOM2_PAD"), std::string("1"), "the pad, always");
            t.Equals(fs::path(valueOf(p.environment, "PS2X_MC_DIR")), (home / "cards" / "viper").lexically_normal(),
                     "cards/<profile> is made absolute against the folder: a double-click promises no working directory");
            std::vector<std::string> theirs = launcher::environmentFor(c);
            t.Equals(p.environment.size(), theirs.size(), "nothing added, nothing dropped relative to environmentFor");
            std::error_code ec;
            fs::remove_all(home, ec);
        });

        tc.Run("no config.json is the defaults, not an error", [](TestCase &t)
        {
            const fs::path home = makeHome();
            const BareRun::Plan p = BareRun::plan(home);
            t.Equals(p.code, 0, "a stranger who never opened the launcher still gets a run");
            t.IsTrue(!p.configFound, "and the plan says there was no file");
            t.Equals(valueOf(p.environment, "PS2X_CD_IMAGE"), std::string("<absent>"), "no ISO configured: Preflight's *.iso hunt decides");
            t.Equals(valueOf(p.environment, "PS2X_SOCOM2_SERVER"), launcher::effectiveServer(launcher::Config{}), "the default server");
            std::error_code ec;
            fs::remove_all(home, ec);
        });

        tc.Run("69: a config.json that is there and cannot be read", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "config.json", "{ \"isoPath\": \"D:/x.iso\", ");
            BareRun::Plan p = BareRun::plan(home);
            t.Equals(p.code, ExitCodes::kConfigUnreadable, "malformed JSON");
            t.Equals(p.code, 69, "is 69");
            t.IsTrue(p.detail.find("config.json") != std::string::npos, "and the detail names the file");
            t.IsTrue(p.environment.empty(), "no half-read settings reach the environment");
            writeText(home / "config.json", "");
            p = BareRun::plan(home);
            t.Equals(p.code, 69, "an empty file is unreadable too, not 'the defaults'");
            t.Equals(std::string(ExitCodes::find(69)->sentence),
                     std::string("config.json could not be read. Delete it and start the launcher, which writes a new one."), "the sentence the player sees");
            std::error_code ec;
            fs::remove_all(home, ec);
        });

        tc.Run("applyEnvironment sets what is unset and leaves what the caller already chose", [](TestCase &t)
        {
#ifdef _WIN32
            _putenv_s("PS2X_BARE_TEST_KEPT", "theirs");
            _putenv_s("PS2X_BARE_TEST_NEW", "");
#else
            setenv("PS2X_BARE_TEST_KEPT", "theirs", 1);
            unsetenv("PS2X_BARE_TEST_NEW");
#endif
            const int set = BareRun::applyEnvironment({"PS2X_BARE_TEST_KEPT=ours", "PS2X_BARE_TEST_NEW=ours", "not-a-pair"});
            t.Equals(set, 1, "one variable was unset, so one was set; a bare word is skipped");
            t.Equals(std::string(std::getenv("PS2X_BARE_TEST_KEPT")), std::string("theirs"), "the environment wins over config.json");
            const char *fresh = std::getenv("PS2X_BARE_TEST_NEW");
            t.Equals(std::string(fresh ? fresh : ""), std::string("ours"), "config.json fills what was not set");
        });

        tc.Run("the stamp and the executable's folder", [](TestCase &t)
        {
            const std::string s = BareRun::stamp();
            t.Equals(s.size(), static_cast<size_t>(15), "YYYYMMDD_HHMMSS");
            t.IsTrue(s.size() == 15 && s[8] == '_', "with the underscore where the launcher's log names have it");
            t.IsTrue(fs::is_directory(ExeDir::get()), "ExeDir::get() is a directory that exists");
            t.IsTrue(std::string(ExeDir::platformName()) == "windows" || std::string(ExeDir::platformName()) == "linux", "and the platform has a name on both hosts we build on");
#ifdef _WIN32
            const char *self = "ps2x_tests.exe";
#else
            const char *self = "ps2x_tests";
#endif
            t.IsTrue(fs::exists(ExeDir::get() / self), "and it is the one this test binary is in");
        });
    });
}
```

Register it (`void register_bare_run_tests();`, the call, `    src/bare_run_tests.cpp`). Build. **Expected RED:** `fatal error: 'ps2x/bare_run.h' file not found`.

(On Windows `_putenv_s(name, "")` *removes* the variable, which is what the second line relies on.)

- [x] **Step 2: Write `ps2xShared/include/ps2x/exe_dir.h` and `ps2xShared/src/exe_dir.cpp`.**

```cpp
#pragma once
// Sprint 9 Goal 1: the folder the running executable is in. The launcher has had this since Task 8b
// (win32glue::exeDirectory, both glues); the runner needs it for the bare run and must not link the glue.
#include <filesystem>

namespace ExeDir
{
    std::filesystem::path get();
    // "windows", "linux" or "other": for the diagnostics zip's versions.txt, so the launcher needs no #ifdef.
    const char *platformName();
}
```

```cpp
#include "ps2x/exe_dir.h"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace ExeDir
{
    std::filesystem::path get()
    {
#ifdef _WIN32
        wchar_t buf[32768];
        const DWORD n = GetModuleFileNameW(nullptr, buf, static_cast<DWORD>(sizeof(buf) / sizeof(buf[0])));
        if (n > 0 && n < sizeof(buf) / sizeof(buf[0]))
            return std::filesystem::path(buf).parent_path();
#else
        char buf[4096];
        const ssize_t n = ::readlink("/proc/self/exe", buf, sizeof(buf) - 1);
        if (n > 0 && static_cast<size_t>(n) < sizeof(buf))
        {
            buf[n] = '\0';
            return std::filesystem::path(buf).parent_path();
        }
#endif
        // No answer (a container without /proc, a BSD): what win32glue::exeDirectory falls back to.
        std::error_code ec;
        return std::filesystem::current_path(ec);
    }

    const char *platformName()
    {
#if defined(_WIN32)
        return "windows";
#elif defined(__linux__)
        return "linux";
#else
        return "other";
#endif
    }
}
```

- [x] **Step 3: Write `ps2xShared/include/ps2x/bare_run.h`.**

```cpp
#pragma once

// Sprint 9 Goal 1: `socom2` with no argument -- a double-click -- reads the launcher's own config.json
// beside it and starts the game the way the launcher would have. The launcher's Config, fromJson and
// environmentFor are the single schema (launcher/launcher_config.h, in this same library); nothing here
// parses JSON or names a knob of its own.

#include "ps2x/exit_codes.h"

#include <filesystem>
#include <string>
#include <vector>

namespace BareRun
{
    struct Plan
    {
        int code = ExitCodes::kOk;            // kConfigUnreadable when config.json is there and cannot be read
        std::string detail;
        std::filesystem::path home;           // the folder the game lives in
        std::filesystem::path elf;            // home/socom2_game.elf
        std::filesystem::path logDir;         // home/logs
        bool configFound = false;             // false: no config.json, the defaults were used
        std::vector<std::string> environment; // KEY=VALUE, PS2X_MC_DIR absolute
    };

    Plan plan(const std::filesystem::path &home);

    // Sets each KEY=VALUE only when KEY is not already set; returns how many were set. An entry with
    // no '=' is skipped.
    int applyEnvironment(const std::vector<std::string> &keyValues);

    // "YYYYMMDD_HHMMSS", local time: the launcher's run_<stamp>.log shape.
    std::string stamp();

    // stdout and stderr to logDir/run_<stamp>.log. Returns the path; empty when it could not be opened
    // (output then stays where it was).
    std::string redirectOutput(const std::filesystem::path &logDir);

    // Windows: when this process is the only client of its console -- Explorer made one for a
    // double-click -- let it go, so no empty black window sits behind the game. Elsewhere: nothing.
    void detachOwnConsole();
}
```

- [x] **Step 4: Write `ps2xShared/src/bare_run.cpp`** and add `src/bare_run.cpp` and `src/exe_dir.cpp` to `ps2x_shared`'s source list.

```cpp
#include "ps2x/bare_run.h"

#include "launcher/launcher_config.h"

#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <sstream>
#include <system_error>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <io.h>
#else
#include <unistd.h>
#endif

namespace BareRun
{
    namespace fs = std::filesystem;

    Plan plan(const fs::path &home)
    {
        Plan p;
        p.home = home;
        p.elf = home / "socom2_game.elf";
        p.logDir = home / "logs";

        launcher::Config config;
        const fs::path configPath = home / "config.json";
        std::error_code ec;
        if (fs::exists(configPath, ec))
        {
            std::ifstream in(configPath, std::ios::binary);
            std::stringstream text;
            if (in.is_open())
                text << in.rdbuf();
            if (!in.is_open() || !launcher::fromJson(text.str(), config))
            {
                p.code = ExitCodes::kConfigUnreadable;
                p.detail = configPath.string();
                return p;
            }
            p.configFound = true;
        }

        p.environment = launcher::environmentFor(config);
        const std::string cardKey = "PS2X_MC_DIR=";
        for (std::string &kv : p.environment)
        {
            if (kv.rfind(cardKey, 0) != 0)
                continue;
            const fs::path value(kv.substr(cardKey.size()));
            if (value.is_relative())
                kv = cardKey + (home / value).lexically_normal().string();
        }
        return p;
    }

    int applyEnvironment(const std::vector<std::string> &keyValues)
    {
        int set = 0;
        for (const std::string &kv : keyValues)
        {
            const size_t eq = kv.find('=');
            if (eq == std::string::npos || eq == 0)
                continue;
            const std::string key = kv.substr(0, eq);
            const std::string value = kv.substr(eq + 1);
            if (std::getenv(key.c_str()) != nullptr)
                continue;   // the caller's environment is the override (spec Goal 3's rule, applied early)
#ifdef _WIN32
            if (_putenv_s(key.c_str(), value.c_str()) == 0)
                ++set;
#else
            if (::setenv(key.c_str(), value.c_str(), 0) == 0)
                ++set;
#endif
        }
        return set;
    }

    std::string stamp()
    {
        const std::time_t now = std::time(nullptr);
        std::tm tm{};
#ifdef _WIN32
        localtime_s(&tm, &now);
#else
        localtime_r(&now, &tm);
#endif
        char buf[32];
        std::strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &tm);
        return buf;
    }

    std::string redirectOutput(const fs::path &logDir)
    {
        std::error_code ec;
        fs::create_directories(logDir, ec);
        const std::string path = (logDir / ("run_" + stamp() + ".log")).string();
        std::fprintf(stderr, "socom2: logging to %s\n", path.c_str());
        std::fflush(stdout);
        std::fflush(stderr);
        if (std::freopen(path.c_str(), "w", stdout) == nullptr)
            return {};
#ifdef _WIN32
        _dup2(_fileno(stdout), _fileno(stderr));
#else
        ::dup2(fileno(stdout), fileno(stderr));
#endif
        std::setvbuf(stderr, nullptr, _IONBF, 0);
        return path;
    }

    void detachOwnConsole()
    {
#ifdef _WIN32
        DWORD clients[2];
        if (GetConsoleProcessList(clients, 2) == 1)
            FreeConsole();
#endif
    }
}
```

- [x] **Step 5: GREEN.** Build; `PS2X_TEST_SUITE=BareRun ./ps2x_tests.exe` -> `Total Tests: 5`, `Failed: 0`.

- [x] **Step 6: `./build.sh test` exit 0 (`Total Tests: B + 18`), then commit.**

```bash
git add third_party/ps2recomp/ps2xShared/include/ps2x/bare_run.h third_party/ps2recomp/ps2xShared/include/ps2x/exe_dir.h \
        third_party/ps2recomp/ps2xShared/src/bare_run.cpp third_party/ps2recomp/ps2xShared/src/exe_dir.cpp \
        third_party/ps2recomp/ps2xTest/src/bare_run_tests.cpp
git commit -m "feat: BareRun -- the launcher's config.json beside the exe becomes the environment (set only where unset), the card folder absolute, 69 for a config that cannot be read (R131, R132); not wired into the runner yet

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared/include/ps2x/bare_run.h \
  third_party/ps2recomp/ps2xShared/include/ps2x/exe_dir.h \
  third_party/ps2recomp/ps2xShared/src/bare_run.cpp \
  third_party/ps2recomp/ps2xShared/src/exe_dir.cpp \
  third_party/ps2recomp/ps2xShared/CMakeLists.txt \
  third_party/ps2recomp/ps2xTest/src/bare_run_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/main.cpp \
  third_party/ps2recomp/ps2xTest/CMakeLists.txt
git push
```

---

## Task 6 — The runner, wired: preflight, the bare run, out of memory, the audio notice  **[Judgment]**

The one task that touches `ps2xRuntime/src/`, so the one task that needs the runtime build and the gate. Its RED is a Python module that starts the real `socom2` seven times in a temporary folder; every case is built to stop **before a window opens**, and the first run against the *old* `dist/socom2.exe` is the watched RED (the old `main()` treats `--home` as an ELF path, opens a window, fails `loadELF` and leaves with 1 — seven brief windows; mind the quiet gate).

**Files:**
- Create: `ps2xShared/include/ps2x/process_fatal.h`, `ps2xShared/src/process_fatal.cpp`, `tools_py/tests/test_runner_exit_codes.py`, `logs/s9_g1_gate.sh` (git-ignored)
- Modify: `ps2xShared/CMakeLists.txt`, `ps2xRuntime/src/main.cpp` (includes; a helper in the anonymous namespace; all of `main()`, :167-255), `ps2xRuntime/src/lib/ps2_runtime.cpp` (:772 and one include)

**Interfaces:**
- `void ProcessFatal::installOutOfMemoryHandler()` — `std::set_new_handler` with a handler that writes `[oom] exit 71 out-of-memory: <sentence>` to stderr without allocating and calls `std::_Exit(ExitCodes::kOutOfMemory)`. Safe from any thread; runs before `std::bad_alloc` would be thrown, so no catch block can turn it into a 1.
- `int ProcessFatal::failTest(const char *kind)` — `"crash"`: a write through a null pointer (the process dies the native way; never returns). `"oom"`: one allocation no machine can satisfy (the handler exits 71; never returns). Anything else: returns `ExitCodes::kFailed`. Exists so that codes 70 and 71 have a test that *drives the failing condition* (spec bar), R136.
- `socom2` — no argument: the bare run from `ExeDir::get()`. `socom2 --home <dir>`: the bare run as if the executable lived in `<dir>` (what the Python cases use; it never touches `dist/config.json`). `socom2 <elf> [...]`: exactly as today, plus the preflight. `socom2 --fail-test crash|oom`.

**Steps:**

- [x] **Step 1: RED.** Create `tools_py/tests/test_runner_exit_codes.py`:

```python
"""Sprint 9 Goal 1: a test per exit code that drives the failing condition on the real runner and asserts
the code and the sentence. Every case stops before a window opens (Preflight and BareRun run in front of
PS2Runtime::initialize), so this is a handful of sub-second processes, not a launch -- but it obeys the quiet
gate like every other suite. Skipped where there is no runner build (CI builds --no-runner)."""
import glob
import json
import os
import struct
import subprocess
import tempfile
import unittest

from tools_py import exit_codes
from tools_py.parity import hostplatform

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXE = os.path.join(ROOT, hostplatform.runtime_exe())


def _both(value):
    return struct.pack("<I", value) + struct.pack(">I", value)


def _record(extent, size, name, flags):
    length = (33 + len(name) + 1) & ~1
    rec = bytearray(length)
    rec[0] = length
    rec[2:10] = _both(extent)
    rec[10:18] = _both(size)
    rec[25] = flags
    rec[32] = len(name)
    rec[33:33 + len(name)] = name
    return bytes(rec)


def iso_with(name):
    """A 20-sector ISO 9660 image whose root directory holds one 5-byte file called `name` (bytes)."""
    img = bytearray(20 * 2048)
    pvd = 16 * 2048
    img[pvd] = 1
    img[pvd + 1:pvd + 6] = b"CD001"
    img[pvd + 156:pvd + 156 + 34] = _record(18, 2048, b"\x00", 2)
    body = _record(18, 2048, b"\x00", 2) + _record(18, 2048, b"\x01", 2) + _record(19, 5, name, 0)
    img[18 * 2048:18 * 2048 + len(body)] = body
    img[19 * 2048:19 * 2048 + 5] = b"hello"
    return bytes(img)


@unittest.skipUnless(os.path.isfile(EXE), "no runner build at " + EXE)
class RunnerExitCodeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # outer/home: "one folder up" from the ELF is ours too, so a stray .iso in %TEMP% cannot be found.
        self.home = os.path.join(self._tmp.name, "outer", "home")
        os.makedirs(self.home)
        # The developer's PS2X_* must not leak in: in a bare run the environment wins over config.json.
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("PS2X_")}

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, data):
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(os.path.join(self.home, name), mode) as fh:
            fh.write(data)

    def _run(self, *args):
        return subprocess.run([EXE, *args], capture_output=True, text=True, errors="replace",
                              timeout=60, env=self.env, cwd=self.home)

    def _log(self):
        logs = sorted(glob.glob(os.path.join(self.home, "logs", "run_*.log")))
        self.assertTrue(logs, "the bare run writes logs/run_<stamp>.log")
        with open(logs[-1], "r", errors="replace") as fh:
            return fh.read()

    def _assert_code(self, result, name):
        row = next(r for r in exit_codes.table() if r["name"] == name)
        self.assertEqual(exit_codes.classify(result.returncode), row["code"], result.stdout + result.stderr)
        line = "exit %d %s: %s" % (row["code"], row["slug"], row["sentence"])
        self.assertIn(line, self._log())

    def test_68_no_game_elf_beside_the_runner(self):
        self._assert_code(self._run("--home", self.home), "ElfMissing")

    def test_69_config_json_that_cannot_be_read(self):
        self._write("socom2_game.elf", "elf")
        self._write("config.json", '{ "isoPath": ')
        self._assert_code(self._run("--home", self.home), "ConfigUnreadable")

    def test_72_memory_card_folder_that_cannot_be_written(self):
        self._write("socom2_game.elf", "elf")
        self._write("cards", "a file where the cards folder should be")
        self._assert_code(self._run("--home", self.home), "CardDirUnwritable")

    def test_66_no_disc_anywhere(self):
        self._write("socom2_game.elf", "elf")
        self._assert_code(self._run("--home", self.home), "DiscNotFound")

    def test_66_the_configured_disc_is_gone(self):
        self._write("socom2_game.elf", "elf")
        self._write("config.json", json.dumps({"isoPath": os.path.join(self.home, "gone.iso")}))
        self._assert_code(self._run("--home", self.home), "DiscNotFound")

    def test_67_a_disc_that_is_not_r0001(self):
        self._write("socom2_game.elf", "elf")
        self._write("other.iso", iso_with(b"SCUS_972.75;1"))   # SCUS_972.75 is "hello": not the pinned digest
        self._write("config.json", json.dumps({"isoPath": os.path.join(self.home, "other.iso")}))
        self._assert_code(self._run("--home", self.home), "DiscNotR0001")

    def test_70_a_crash_is_classified_from_the_native_status(self):
        result = self._run("--fail-test", "crash")
        self.assertEqual(exit_codes.classify(result.returncode), exit_codes.code("Crashed"), result.returncode)
        self.assertEqual(exit_codes.describe(result.returncode), exit_codes.sentence(70))

    def test_71_out_of_memory(self):
        result = self._run("--fail-test", "oom")
        self.assertEqual(result.returncode, exit_codes.code("OutOfMemory"), result.stdout + result.stderr)
        self.assertIn("[oom] exit 71 out-of-memory: " + exit_codes.sentence(71), result.stderr)


if __name__ == "__main__":
    unittest.main()
```

Run (quiet gate first): `bash scripts/check_quiet_gate.sh && python -m unittest tools_py.tests.test_runner_exit_codes -v`. **Expected RED against the old `dist/socom2.exe`:** 8 failures; the first six read `AssertionError: 1 != 68` (…`69`, `72`, `66`, `66`, `67`) — or `AssertionError: [] is not true : the bare run writes logs/run_<stamp>.log` where the code comparison is reached second — and the last two `AssertionError: 1 != 70` / `1 != 71`. Paste the summary line into the ledger.

- [x] **Step 2: Write `ps2xShared/include/ps2x/process_fatal.h` and `ps2xShared/src/process_fatal.cpp`**; add `    src/process_fatal.cpp` to `ps2x_shared`'s source list.

```cpp
#pragma once
// Sprint 9 Goal 1: the two endings no check can see coming -- out of memory, and a crash -- and the
// switch that lets a test drive each on purpose.
namespace ProcessFatal
{
    // std::set_new_handler: "[oom] exit 71 out-of-memory: <sentence>" on stderr, then _Exit(71). The
    // handler allocates nothing and is safe from any thread.
    void installOutOfMemoryHandler();

    // "crash": writes through a null pointer; the process dies the native way (R128). "oom": asks for
    // memory no machine has; the handler above leaves with 71. Neither returns. Anything else returns
    // ExitCodes::kFailed.
    int failTest(const char *kind);
}
```

```cpp
#include "ps2x/process_fatal.h"

#include "ps2x/exit_codes.h"

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace ProcessFatal
{
    namespace
    {
        void onOutOfMemory()
        {
            // No allocation, no iostream: the heap is what just failed.
            std::fputs("[oom] exit 71 out-of-memory: ", stderr);
            if (const ExitCodes::Entry *e = ExitCodes::find(ExitCodes::kOutOfMemory))
                std::fputs(e->sentence, stderr);
            std::fputs("\n", stderr);
            std::fflush(stderr);
            std::fflush(stdout);
            std::_Exit(ExitCodes::kOutOfMemory);
        }

        void *volatile g_sink = nullptr;
    }

    void installOutOfMemoryHandler()
    {
        std::set_new_handler(onOutOfMemory);
    }

    int failTest(const char *kind)
    {
        if (kind != nullptr && std::strcmp(kind, "crash") == 0)
        {
#ifdef _WIN32
            // No "socom2.exe has stopped working" dialog in front of a test run.
            SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
#endif
            std::fputs("[fail-test] crash: writing through a null pointer\n", stderr);
            std::fflush(stderr);
            volatile int *nowhere = nullptr;
            *nowhere = 1;
            std::abort();   // not reached; SIGABRT / fast-fail still classifies as a crash
        }
        if (kind != nullptr && std::strcmp(kind, "oom") == 0)
        {
            std::fputs("[fail-test] oom: one allocation of half the address space\n", stderr);
            std::fflush(stderr);
            volatile std::size_t huge = static_cast<std::size_t>(-1) / 2;
            g_sink = ::operator new(huge);   // operator new calls the new_handler, which leaves with 71
            return ExitCodes::kFailed;       // reached only if the platform really had it
        }
        return ExitCodes::kFailed;
    }
}
```

- [x] **Step 3: `ps2xRuntime/src/main.cpp`.** Add to the includes (after `#include <cstdlib>`, line 16): `#include <cstring>`, `#include "ps2x/bare_run.h"`, `#include "ps2x/exe_dir.h"`, `#include "ps2x/exit_codes.h"`, `#include "ps2x/preflight.h"`, `#include "ps2x/process_fatal.h"`. Add to the anonymous namespace, directly above its closing brace (line 165):

```cpp
    // Sprint 9 Goal 1: every early ending goes through here -- one log line in Preflight's shape, then
    // the code. _Exit, as the end of main() does: no static destructors race the runtime's threads.
    [[noreturn]] void leaveWith(int code, const std::string &detail)
    {
        Preflight::Result result;
        result.code = code;
        result.detail = detail;
        std::cout.flush();
        std::cerr << Preflight::logLine(result) << std::endl;
        std::cerr.flush();
        std::_Exit(code);
    }
```

Replace `main()` from its opening brace (line 168) **through `PS2Runtime runtime;` (line 200)**, keeping everything between — the window-title block, lines 178-198 — exactly as it is, so that it reads:

```cpp
int main(int argc, char *argv[])
{
#if defined(__ANDROID__)
    redirectStdioToLogcat();
#endif
    setupTerminateLogger();
    // Sprint 9 Goal 1: running out of memory is exit 71 with a sentence, from whichever thread it happens on.
    ProcessFatal::installOutOfMemoryHandler();

    // socom2 --fail-test crash|oom: drives codes 70 and 71 for tools_py/tests/test_runner_exit_codes.py.
    if (argc > 2 && std::strcmp(argv[1], "--fail-test") == 0)
    {
        const int code = ProcessFatal::failTest(argv[2]);
        std::_Exit(code);
    }

    try
    {
        std::filesystem::path pathObj;
#if !defined(PS2X_DEFAULT_BOOT_ELF) && !defined(PLATFORM_VITA) && !defined(__ANDROID__)
        // The bare run: no argument (a double-click), or --home <dir> (the same, as if the executable lived
        // in <dir>). The launcher's config.json beside it becomes the environment -- only where the
        // environment has not already chosen -- and the output goes where the launcher would have put it.
        const bool homeArg = argc > 2 && std::strcmp(argv[1], "--home") == 0;
        if (argc < 2 || homeArg)
        {
            const std::filesystem::path home = homeArg ? std::filesystem::path(argv[2]) : ExeDir::get();
            const BareRun::Plan plan = BareRun::plan(home);
            BareRun::redirectOutput(plan.logDir);
            if (!homeArg)
                BareRun::detachOwnConsole();
            std::cout << "[bare-run] home " << plan.home.string() << ", config.json "
                      << (plan.configFound ? "read" : (plan.code == ExitCodes::kOk ? "absent: the defaults" : "unreadable")) << std::endl;
            if (plan.code != ExitCodes::kOk)
                leaveWith(plan.code, plan.detail);
            const int applied = BareRun::applyEnvironment(plan.environment);
            std::cout << "[bare-run] " << applied << " of " << plan.environment.size()
                      << " settings taken from config.json (the rest were already in the environment)" << std::endl;
            std::error_code cwdEc;
            std::filesystem::current_path(plan.home, cwdEc);   // what both launcher glues give the child
            pathObj = plan.elf;
        }
        else
#endif
        {
            pathObj = getExecutablePath(argc, argv);
        }

#if !defined(PLATFORM_VITA) && !defined(__ANDROID__)
        // Before a window exists: the ELF, the card folder, the disc, and that the disc is r0001.
        {
            Preflight::Input pre;
            pre.elfPath = pathObj;
            if (const char *cd = std::getenv("PS2X_CD_IMAGE"))
                pre.cdImageEnv = cd;
            std::error_code absEc;
            const char *mc = std::getenv("PS2X_MC_DIR");   // the same rule as PS2Runtime::configureIoPathsFromElf
            pre.cardDir = (mc != nullptr && *mc != '\0')
                              ? std::filesystem::absolute(std::filesystem::path(mc), absEc)
                              : std::filesystem::absolute(pathObj, absEc).parent_path() / "mc0";
            pre.checkDisc = pathObj.filename() == "socom2_game.elf";   // the override's own key (game_overrides_socom2.cpp:1890)
            const Preflight::Result checked = Preflight::run(pre);
            if (checked.code != ExitCodes::kOk)
                leaveWith(checked.code, checked.detail);
            if (!checked.disc.empty())
                std::cout << "[preflight] ok: " << checked.disc.string() << " is SOCOM II NTSC r0001" << std::endl;
        }
#endif

        std::string filePathStr = pathObj.string();
        std::string elfName = pathObj.filename().string();
        std::string normalizedId = normalizeGameId(elfName);
        // ... lines 182-198 unchanged: windowTitle, PS2X_WINDOW_TITLE, gameName ...

        PS2Runtime runtime;
```

Then three one-line changes below it: the `loadELF` failure (line 229-230) becomes

```cpp
            std::cerr << "Failed to load ELF file: " << filePathStr << std::endl;
            leaveWith(ExitCodes::kElfMissing, filePathStr);
```

`return 1;` after "Failed to initialize PS2 runtime" (line 224) becomes `leaveWith(ExitCodes::kFailed, "PS2Runtime::initialize");`, and the final `std::_Exit(1);` (line 254) becomes `std::_Exit(ExitCodes::kFailed);`. (The "lines 182-198 unchanged" comment above is an instruction to you, not text to paste.)

- [x] **Step 4: The audio notice, `ps2xRuntime/src/lib/ps2_runtime.cpp:771-772`.** Add `#include "ps2x/exit_codes.h"` with the file's other includes and replace the two lines:

```cpp
        InitAudioDevice();
        const bool audioReady = IsAudioDeviceReady();
        m_audioBackend.setAudioReady(audioReady);
        // Sprint 9 Goal 1: no audio device is not a reason to stop (spec: "non-fatal, reported"). The
        // launcher reads this line back out of the log and appends its sentence to LAST RUN.
        if (!audioReady)
            std::cout << ExitCodes::noticeLine(ExitCodes::kNoAudioDevice) << std::endl;
```

**There is no RED for this line**: driving it needs a machine with no audio endpoint, and neither this host, the VM under PulseAudio's null sink, nor CI (which has no runner) is one. What is tested is both ends of the pipe — `noticeLine`'s exact text and `noticesIn`/`lastRunLine` reading it back (Tasks 2 and 3). Task 10 files the hands-on check under the owner's Linux run.

- [x] **Step 5: Build the runner, detached, and watch GREEN.** *(2026-09-20: the bare-run launch was taken in the VM -- `--home`, 30 s, `[bare-run]` and `[preflight] ok:` in its own log, the game started; the Windows double-click is the owner's check (a) in HUMAN_TASKS.)* *(2026-09-19: built with `./build.sh runtime`, `test_runner_exit_codes` Ran 8 OK, `./build.sh test` 641 / 1312 OK; the 60 s bare-run launch, the gate and the commit are the controller's and are not done.)*

```bash
bash scripts/check_quiet_gate.sh
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/build_runtime.marker
cat logs/build_runtime.marker 2>/dev/null || echo running      # until it reads exit=0
python -m unittest tools_py.tests.test_runner_exit_codes -v   # Ran 8 tests ... OK
```

Then the two checks no unit test can make, by hand, once each, recorded in the ledger:
  - `cmd //c "cd /d C:\projects\socom_pc\dist && socom2.exe"` from a terminal: `socom2: logging to …\dist\logs\run_<stamp>.log` is printed, the game starts on the owner's `dist/config.json` (their ISO, their window size), and the new log's first lines are `[bare-run] home …, config.json read`, `[bare-run] N of M settings…`, `[preflight] ok: … is SOCOM II NTSC r0001`. Close it from its window; `echo $?` is 0. **This is a host launch: it goes through `scripts/run_detached.sh --owner gate --purpose launch` with a 60 s `timeout`, like any other** (script `logs/s9_g1_bare.sh`, the shape in the command set, its body `cd dist && timeout 60 ./socom2.exe; echo "rc=$?"`; `timeout`'s 124 is the expected result for a game that was still running).
  - The console detach (R132) cannot be seen from a terminal at all — it fires only for Explorer's own console. It is one line in `docs/HUMAN_TASKS.md` (Task 10): double-click `socom2.exe`, expect the game and no black window behind it.

- [x] **Step 6: The full suite, then the gate.** `./build.sh test` exit 0 (`Total Tests: B + 18` unchanged from Task 5 — this task adds no C++ case; Python `P + 13`). Create `logs/s9_g1_gate.sh` (the text is in the command set), then:

```bash
scripts/run_detached.sh --owner gate --purpose launch logs/s9_g1_gate.sh logs/s9_g1_gate.marker
cat logs/s9_g1_gate.marker 2>/dev/null || echo running         # exit=0, and logs/s9_g1_gate.done reads "done 0"
grep -n "\[preflight\]" "$(ls -t logs/run_A_*.log | head -1)"  # "[preflight] ok: ... is SOCOM II NTSC r0001" in a gate run's log
```

**Bar: 3/3.** The gate's launches pass `PS2X_CD_IMAGE` (`tools_py/parity/drive.py:42-53`) and the ELF as `argv[1]`, so they take the preflight and not the bare run; the `grep` proves the preflight ran and passed on the real disc. A gate stage that now exits 66/67/72 is this task's bug, not the gate's: read the `[preflight]` line in its log, fix, rebuild, and spend the gate again only after `test_runner_exit_codes` is green.

- [x] **Step 7: Commit.**

```bash
git add third_party/ps2recomp/ps2xShared/include/ps2x/process_fatal.h third_party/ps2recomp/ps2xShared/src/process_fatal.cpp tools_py/tests/test_runner_exit_codes.py
git commit -m "feat(runner): a failure explains itself -- preflight before the window (66 disc not found, 67 not r0001, 68 ELF, 72 card folder), socom2 with no argument reads config.json beside it (69 when it cannot), 71 from the new_handler, the no-audio notice; --home and --fail-test drive each code from a test. Gate 3/3 s9_g1_gate

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared/include/ps2x/process_fatal.h \
  third_party/ps2recomp/ps2xShared/src/process_fatal.cpp \
  third_party/ps2recomp/ps2xShared/CMakeLists.txt \
  third_party/ps2recomp/ps2xRuntime/src/main.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp \
  tools_py/tests/test_runner_exit_codes.py
git push
```

- [x] **Step 8: The Linux ring for this commit.** CI compiles `ps2x_shared`, `ps2_runtime` and the suites but **not** `ps2xRuntime/src/main.cpp` (`--no-runner` skips `ps2EntryRunner`), so the runner's POSIX half is proven only in the VM:

```bash
scripts/vm_sync.sh tree
scripts/vm_sync.sh ssh 'cd ~/socom_pc && bash scripts/build_linux.sh runtime && python3 -m unittest tools_py.tests.test_runner_exit_codes -v'
```

Expected: `Ran 8 tests … OK` (on Linux `test_70` sees `returncode == -11`, which `exit_codes.classify` folds to 70). Watch the pushed commit's `linux` workflow go green as well. A failure here is fixed forward in a follow-up commit under the same gate rule.

---

## Task 7 — A STORE-only zip writer with CRC-32  **[Opus]**

No archiver is vendored (Handoff note 9), and the launcher takes no new dependency for six small text files (R133). A zip whose entries are *stored* — method 0, no compression — is three fixed-layout records and a CRC; every zip reader opens it.

**Files:**
- Create: `ps2xShared/include/ps2x/zip_store.h`, `ps2xShared/src/zip_store.cpp`, `ps2xTest/src/zip_store_tests.cpp`
- Modify: `ps2xShared/CMakeLists.txt`, `ps2xTest/CMakeLists.txt`, `ps2xTest/src/main.cpp`

**Interfaces (namespace `ZipStore`):**
- `struct Entry { std::string name; std::string data; }` — `name` uses `/`, UTF-8.
- `uint32_t crc32(const uint8_t *data, size_t size, uint32_t crc = 0u)` — IEEE 802.3 (polynomial `0xEDB88320`, reflected), chainable through `crc`.
- `bool nameAllowed(const std::string &name)` — non-empty, at most 65535 bytes, no `\`, no `:`, no leading `/`, no empty, `.` or `..` segment.
- `bool dosDateTime(const std::string &stamp, uint16_t &date, uint16_t &time)` — from `YYYYMMDD_HHMMSS` (`win32glue::stamp()`); false, outputs untouched, when it is not one.
- `std::string build(const std::vector<Entry> &entries, uint16_t dosDate = 0x0021, uint16_t dosTime = 0)` — the archive's bytes; **empty** when a name is not allowed, there are more than 65534 entries, or anything would pass 4 GiB - 1 (no zip64). `0x0021` is 1980-01-01, the format's epoch.

**Steps:**

- [x] **Step 1: RED.** Create `ps2xTest/src/zip_store_tests.cpp`:

```cpp
// Sprint 9 Goal 1: the diagnostics zip's writer. STORE only; checked here byte by byte against the
// format (APPNOTE 4.3.7, 4.3.12, 4.3.16), and in tools_py/tests/test_diagnostics_zip.py by Python's zipfile.
#include "MiniTest.h"
#include "ps2x/zip_store.h"

#include <cstdint>
#include <string>
#include <vector>

namespace
{
    uint16_t rd16(const std::string &z, size_t at)
    {
        return static_cast<uint16_t>(static_cast<uint8_t>(z[at]) | (static_cast<uint8_t>(z[at + 1]) << 8));
    }
    uint32_t rd32(const std::string &z, size_t at)
    {
        return static_cast<uint32_t>(rd16(z, at)) | (static_cast<uint32_t>(rd16(z, at + 2)) << 16);
    }
    uint32_t crcOf(const std::string &s)
    {
        return ZipStore::crc32(reinterpret_cast<const uint8_t *>(s.data()), s.size());
    }
}

void register_zip_store_tests()
{
    MiniTest::Case("ZipStore", [](TestCase &tc)
    {
        tc.Run("crc32: the check value, the empty string, and chaining", [](TestCase &t)
        {
            t.Equals(crcOf("123456789"), 0xCBF43926u, "the CRC-32/ISO-HDLC check value");
            t.Equals(crcOf(""), 0u, "nothing hashes to 0");
            t.Equals(crcOf("hello"), 0x3610A686u, "hello");
            const std::string a = "1234", b = "56789";
            const uint32_t first = ZipStore::crc32(reinterpret_cast<const uint8_t *>(a.data()), a.size());
            t.Equals(ZipStore::crc32(reinterpret_cast<const uint8_t *>(b.data()), b.size(), first), 0xCBF43926u, "two halves chain to the whole");
        });

        tc.Run("names: forward slashes, relative, no way out of the folder", [](TestCase &t)
        {
            t.IsTrue(ZipStore::nameAllowed("config.json"), "a file");
            t.IsTrue(ZipStore::nameAllowed("log/run_20260919_084912.log"), "a file in a folder");
            t.IsFalse(ZipStore::nameAllowed(""), "empty");
            t.IsFalse(ZipStore::nameAllowed("/etc/passwd"), "absolute");
            t.IsFalse(ZipStore::nameAllowed("..\\x"), "a backslash");
            t.IsFalse(ZipStore::nameAllowed("a/../b"), "a parent segment");
            t.IsFalse(ZipStore::nameAllowed("a//b"), "an empty segment");
            t.IsFalse(ZipStore::nameAllowed("C:/x"), "a drive");
            t.IsTrue(ZipStore::build(std::vector<ZipStore::Entry>{ZipStore::Entry{"../x", "data"}}).empty(), "build refuses the whole archive rather than write a bad name");
        });

        tc.Run("the DOS date and time out of the launcher's stamp", [](TestCase &t)
        {
            uint16_t date = 1, time = 1;
            t.IsTrue(ZipStore::dosDateTime("20260919_084912", date, time), "a stamp parses");
            t.Equals(date, static_cast<uint16_t>(((2026 - 1980) << 9) | (9 << 5) | 19), "years since 1980, month, day");
            t.Equals(time, static_cast<uint16_t>((8 << 11) | (49 << 5) | (12 / 2)), "hours, minutes, two-second units");
            date = 7; time = 9;
            t.IsFalse(ZipStore::dosDateTime("2026-09-19", date, time), "anything else does not");
            t.IsFalse(ZipStore::dosDateTime("20261319_084912", date, time), "nor a thirteenth month");
            t.Equals(date, static_cast<uint16_t>(7), "and the outputs are left alone");
        });

        tc.Run("an empty archive is the 22-byte end record", [](TestCase &t)
        {
            const std::string z = ZipStore::build({});
            t.Equals(z.size(), static_cast<size_t>(22), "just the end of central directory");
            t.Equals(rd32(z, 0), 0x06054b50u, "its signature");
            t.Equals(rd16(z, 10), static_cast<uint16_t>(0), "no entries");
        });

        tc.Run("three stored entries: local headers, data, central directory, end record -- every field", [](TestCase &t)
        {
            const std::string bin("\0\1\2", 3);
            const std::vector<ZipStore::Entry> in = {{"a.txt", "hello"}, {"dir/b.bin", bin}, {"empty.txt", ""}};
            const std::string z = ZipStore::build(in, 0x5D33, 0x4626);
            // locals: (30+5+5) + (30+9+3) + (30+9+0) = 121; central: (46+5) + (46+9) + (46+9) = 157; end: 22
            t.Equals(z.size(), static_cast<size_t>(300), "the size is exactly headers + names + data");
            const size_t eocd = z.size() - 22;
            t.Equals(rd32(z, eocd), 0x06054b50u, "end record signature");
            t.Equals(rd16(z, eocd + 8), static_cast<uint16_t>(3), "entries on this disk");
            t.Equals(rd16(z, eocd + 10), static_cast<uint16_t>(3), "entries in total");
            t.Equals(rd32(z, eocd + 12), 157u, "central directory size");
            t.Equals(rd32(z, eocd + 16), 121u, "central directory offset");
            t.Equals(rd16(z, eocd + 20), static_cast<uint16_t>(0), "no comment");

            const uint32_t expectedOffset[3] = {0u, 40u, 82u};
            size_t cd = 121;
            for (size_t i = 0; i < in.size(); ++i)
            {
                const std::string &name = in[i].name;
                const std::string &data = in[i].data;
                const std::string which = "entry " + std::to_string(i) + ": ";
                t.Equals(rd32(z, cd), 0x02014b50u, which + "central signature");
                t.Equals(rd16(z, cd + 6), static_cast<uint16_t>(10), which + "version needed 1.0 (stored, no folders-as-entries)");
                t.Equals(rd16(z, cd + 8), static_cast<uint16_t>(0x0800), which + "flag bit 11: the name is UTF-8");
                t.Equals(rd16(z, cd + 10), static_cast<uint16_t>(0), which + "method 0: stored");
                t.Equals(rd16(z, cd + 12), static_cast<uint16_t>(0x4626), which + "time");
                t.Equals(rd16(z, cd + 14), static_cast<uint16_t>(0x5D33), which + "date");
                t.Equals(rd32(z, cd + 16), crcOf(data), which + "crc");
                t.Equals(rd32(z, cd + 20), static_cast<uint32_t>(data.size()), which + "compressed size == size");
                t.Equals(rd32(z, cd + 24), static_cast<uint32_t>(data.size()), which + "uncompressed size");
                t.Equals(rd16(z, cd + 28), static_cast<uint16_t>(name.size()), which + "name length");
                t.Equals(rd16(z, cd + 30), static_cast<uint16_t>(0), which + "no extra field");
                t.Equals(rd32(z, cd + 42), expectedOffset[i], which + "local header offset");
                t.Equals(z.substr(cd + 46, name.size()), name, which + "central name");

                const size_t lh = expectedOffset[i];
                t.Equals(rd32(z, lh), 0x04034b50u, which + "local signature");
                t.Equals(rd16(z, lh + 6), static_cast<uint16_t>(0x0800), which + "local flags");
                t.Equals(rd16(z, lh + 8), static_cast<uint16_t>(0), which + "local method");
                t.Equals(rd32(z, lh + 14), crcOf(data), which + "local crc (no data descriptor)");
                t.Equals(rd32(z, lh + 18), static_cast<uint32_t>(data.size()), which + "local compressed size");
                t.Equals(rd32(z, lh + 22), static_cast<uint32_t>(data.size()), which + "local size");
                t.Equals(rd16(z, lh + 26), static_cast<uint16_t>(name.size()), which + "local name length");
                t.Equals(rd16(z, lh + 28), static_cast<uint16_t>(0), which + "local extra length");
                t.Equals(z.substr(lh + 30, name.size()), name, which + "local name");
                t.Equals(z.substr(lh + 30 + name.size(), data.size()), data, which + "the bytes, as given");
                cd += 46 + name.size();
            }
            t.Equals(cd, eocd, "the central directory ends where the end record starts");
        });
    });
}
```

Register it (`void register_zip_store_tests();`, the call, `    src/zip_store_tests.cpp`). Build. **Expected RED:** `fatal error: 'ps2x/zip_store.h' file not found`.

- [x] **Step 2: Write `ps2xShared/include/ps2x/zip_store.h`.**

```cpp
#pragma once

// Sprint 9 Goal 1: a zip writer for the diagnostics bundle. STORE only (method 0, no compression), no
// zip64, no data descriptors, no encryption: three fixed-layout records and a CRC-32, so there is no
// dependency to vendor and nothing to audit but this file. The archive is built in memory -- the
// bundle is a few megabytes at most (launcher/diagnostics.h clips the log).

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace ZipStore
{
    struct Entry
    {
        std::string name;   // '/'-separated, relative, UTF-8
        std::string data;
    };

    // IEEE 802.3 CRC-32 (reflected, polynomial 0xEDB88320). Pass the previous result to continue.
    uint32_t crc32(const uint8_t *data, size_t size, uint32_t crc = 0u);

    bool nameAllowed(const std::string &name);

    // "YYYYMMDD_HHMMSS" -> MS-DOS date and time words. False (outputs untouched) when it is not one.
    bool dosDateTime(const std::string &stamp, uint16_t &date, uint16_t &time);

    // The archive's bytes; empty when a name is not allowed or a zip32 limit would be passed.
    std::string build(const std::vector<Entry> &entries, uint16_t dosDate = 0x0021, uint16_t dosTime = 0);
}
```

- [x] **Step 3: Write `ps2xShared/src/zip_store.cpp`** and add `    src/zip_store.cpp` to `ps2x_shared`'s source list.

```cpp
#include "ps2x/zip_store.h"

#include <array>

namespace ZipStore
{
    namespace
    {
        void put16(std::string &out, uint32_t v)
        {
            out.push_back(static_cast<char>(v & 0xFFu));
            out.push_back(static_cast<char>((v >> 8) & 0xFFu));
        }

        void put32(std::string &out, uint32_t v)
        {
            put16(out, v & 0xFFFFu);
            put16(out, (v >> 16) & 0xFFFFu);
        }

        bool digits(const std::string &s, size_t at, size_t count, int &value)
        {
            value = 0;
            for (size_t i = at; i < at + count; ++i)
            {
                if (s[i] < '0' || s[i] > '9')
                    return false;
                value = value * 10 + (s[i] - '0');
            }
            return true;
        }

        constexpr uint64_t kZip32Limit = 0xFFFFFFFEull;
    }

    uint32_t crc32(const uint8_t *data, size_t size, uint32_t crc)
    {
        static const std::array<uint32_t, 256> table = []
        {
            std::array<uint32_t, 256> values{};
            for (uint32_t i = 0; i < 256u; ++i)
            {
                uint32_t v = i;
                for (int bit = 0; bit < 8; ++bit)
                    v = (v & 1u) ? (0xEDB88320u ^ (v >> 1)) : (v >> 1);
                values[i] = v;
            }
            return values;
        }();
        crc = ~crc;
        for (size_t i = 0; i < size; ++i)
            crc = table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
        return ~crc;
    }

    bool nameAllowed(const std::string &name)
    {
        if (name.empty() || name.size() > 0xFFFFu || name.front() == '/')
            return false;
        if (name.find('\\') != std::string::npos || name.find(':') != std::string::npos)
            return false;
        size_t start = 0;
        while (start <= name.size())
        {
            size_t end = name.find('/', start);
            if (end == std::string::npos)
                end = name.size();
            const std::string segment = name.substr(start, end - start);
            if (segment.empty() || segment == "." || segment == "..")
                return false;
            start = end + 1;
        }
        return true;
    }

    bool dosDateTime(const std::string &stamp, uint16_t &date, uint16_t &time)
    {
        int y, mo, d, h, mi, s;
        if (stamp.size() != 15 || stamp[8] != '_')
            return false;
        if (!digits(stamp, 0, 4, y) || !digits(stamp, 4, 2, mo) || !digits(stamp, 6, 2, d) ||
            !digits(stamp, 9, 2, h) || !digits(stamp, 11, 2, mi) || !digits(stamp, 13, 2, s))
            return false;
        if (y < 1980 || y > 2107 || mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59)
            return false;
        date = static_cast<uint16_t>(((y - 1980) << 9) | (mo << 5) | d);
        time = static_cast<uint16_t>((h << 11) | (mi << 5) | (s / 2));
        return true;
    }

    std::string build(const std::vector<Entry> &entries, uint16_t dosDate, uint16_t dosTime)
    {
        if (entries.size() > 0xFFFEu)
            return {};
        std::string out;
        std::string central;
        for (const Entry &e : entries)
        {
            if (!nameAllowed(e.name) || e.data.size() > kZip32Limit)
                return {};
            if (static_cast<uint64_t>(out.size()) + 30u + e.name.size() + e.data.size() > kZip32Limit)
                return {};
            const uint32_t crc = crc32(reinterpret_cast<const uint8_t *>(e.data.data()), e.data.size());
            const uint32_t size = static_cast<uint32_t>(e.data.size());
            const uint32_t offset = static_cast<uint32_t>(out.size());

            put32(out, 0x04034b50u);   // local file header
            put16(out, 10);            // version needed: 1.0
            put16(out, 0x0800);        // bit 11: UTF-8 name
            put16(out, 0);             // method: stored
            put16(out, dosTime);
            put16(out, dosDate);
            put32(out, crc);
            put32(out, size);          // compressed
            put32(out, size);          // uncompressed
            put16(out, static_cast<uint32_t>(e.name.size()));
            put16(out, 0);             // extra
            out += e.name;
            out += e.data;

            put32(central, 0x02014b50u);   // central directory header
            put16(central, 20);            // made by: 2.0, MS-DOS attribute compatibility
            put16(central, 10);
            put16(central, 0x0800);
            put16(central, 0);
            put16(central, dosTime);
            put16(central, dosDate);
            put32(central, crc);
            put32(central, size);
            put32(central, size);
            put16(central, static_cast<uint32_t>(e.name.size()));
            put16(central, 0);             // extra
            put16(central, 0);             // comment
            put16(central, 0);             // disk number
            put16(central, 0);             // internal attributes
            put32(central, 0);             // external attributes
            put32(central, offset);
            central += e.name;
        }
        if (static_cast<uint64_t>(out.size()) + central.size() + 22u > kZip32Limit)
            return {};
        const uint32_t cdOffset = static_cast<uint32_t>(out.size());
        const uint32_t cdSize = static_cast<uint32_t>(central.size());
        out += central;
        put32(out, 0x06054b50u);   // end of central directory
        put16(out, 0);
        put16(out, 0);
        put16(out, static_cast<uint32_t>(entries.size()));
        put16(out, static_cast<uint32_t>(entries.size()));
        put32(out, cdSize);
        put32(out, cdOffset);
        put16(out, 0);             // comment
        return out;
    }
}
```

- [x] **Step 4: GREEN.** `PS2X_TEST_SUITE=ZipStore ./ps2x_tests.exe` -> `Total Tests: 5`, `Failed: 0`.

- [x] **Step 5: `./build.sh test` exit 0 (`Total Tests: B + 23`), then commit.**

```bash
git add third_party/ps2recomp/ps2xShared/include/ps2x/zip_store.h third_party/ps2recomp/ps2xShared/src/zip_store.cpp third_party/ps2recomp/ps2xTest/src/zip_store_tests.cpp
git commit -m "feat: ZipStore -- a STORE-only zip writer with CRC-32 for the diagnostics bundle; no archiver is vendored and none is added (R133)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared/include/ps2x/zip_store.h \
  third_party/ps2recomp/ps2xShared/src/zip_store.cpp \
  third_party/ps2recomp/ps2xShared/CMakeLists.txt \
  third_party/ps2recomp/ps2xTest/src/zip_store_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/main.cpp \
  third_party/ps2recomp/ps2xTest/CMakeLists.txt
git push
```

---

## Task 8 — What goes in the zip: from strings to entries, with no credential  **[Opus]**

**Files:**
- Create: `ps2xShared/include/launcher/diagnostics.h`, `ps2xShared/src/diagnostics.cpp`, `ps2xTest/src/diagnostics_tests.cpp`
- Modify: `ps2xShared/CMakeLists.txt`, `ps2xTest/CMakeLists.txt`, `ps2xTest/src/main.cpp`

**Interfaces (namespace `launcher::diagnostics`):**
- `constexpr size_t kLogHeadBytes = 256 KiB`, `kLogTailBytes = 4 MiB` (R135).
- `std::string sanitizedConfigJson(const std::string &configText)` — `fromJson` then `toJson` with `isoPath` cut to its file name: **an allowlist by construction** — a key the schema does not know (`password`, `token`, a later build's anything) is not in `Config` and cannot be written back. A malformed config becomes `{ "error": … }`; its text is never copied (R134).
- `std::string scrub(const std::string &text, const std::string &homeDir)` — every occurrence of the user's home directory (as given, and with `\` and `/` swapped) becomes `~`; a `homeDir` shorter than 4 bytes is ignored (never scrub `/` or `C:\`).
- `std::string glCapsLines(const std::string &logText)` — raylib's four `INFO:     > Vendor/Renderer/Version/GLSL` lines and the backend's `[gs-gl] initialised` / `depth mapping` / `note` / `switching to the CPU rasterizer` lines; `no GL line in this log\n` when there are none.
- `std::string crashRecord(const std::string &logText)` — the lines that start with `[crash]`, `[terminate]`, `[main] fatal`, `[oom]`, `[preflight] exit`, `[gs-gl] FATAL`; empty when there are none.
- `std::string joinClipped(const std::string &head, const std::string &tail, uint64_t omittedBytes)` and `std::string clipLog(const std::string &logText, size_t headBytes = kLogHeadBytes, size_t tailBytes = kLogTailBytes)`.
- `struct Inputs { std::string logName, logText, configText, version, platform, homeDir; bool haveLastExit = false; long long lastExit = 0; }`
- `std::string versionsText(const Inputs &)`, `std::vector<ZipStore::Entry> entries(const Inputs &)` — `log/<name>` (when there is a log), `config.json` (when there is a config), `gl_caps.txt` and `versions.txt` (always), `crash.txt` (only when there is a record).

**Steps:**

- [x] **Step 1: RED.** Create `ps2xTest/src/diagnostics_tests.cpp`:

```cpp
// Sprint 9 Goal 1: what the launcher's SAVE DIAGNOSTICS puts in its zip -- and what it must not.
#include "MiniTest.h"
#include "launcher/diagnostics.h"
#include "launcher/launcher_config.h"
#include "ps2x/zip_store.h"

#include <algorithm>
#include <string>
#include <vector>

namespace
{
    namespace diag = launcher::diagnostics;

    const char *kConfigWithSecrets =
        "{\n"
        "  \"isoPath\": \"C:\\\\Users\\\\secretuser\\\\Games\\\\SOCOM II (USA).iso\",\n"
        "  \"gsScale\": 2,\n"
        "  \"password\": \"hunter2\",\n"
        "  \"token\": \"abc123token\",\n"
        "  \"account\": {\"name\": \"viper\", \"sessionKey\": \"deadbeefcafe\"},\n"
        "  \"serverPreset\": \"custom\",\n"
        "  \"server\": \"10.0.0.5\",\n"
        "  \"profile\": \"viper\"\n"
        "}\n";

    const char *kLog =
        "INFO: GL: OpenGL device information:\r\n"
        "INFO:     > Vendor:   NVIDIA Corporation\r\n"
        "INFO:     > Renderer: NVIDIA GeForce RTX 4070 SUPER/PCIe/SSE2\r\n"
        "INFO:     > Version:  3.3.0 NVIDIA 595.97\r\n"
        "INFO:     > GLSL:     3.30 NVIDIA via Cg compiler\r\n"
        "[socom2] CD image: C:\\Users\\secretuser\\Games\\SOCOM II (USA).iso\r\n"
        "[gs-gl] depth mapping: clip-control (GL_ZERO_TO_ONE, z exact)\r\n"
        "[gs-gl] initialised: 3.3.0 NVIDIA 595.97\r\n"
        "[audio] 989snd mix stream open (48000 Hz stereo)\r\n"
        "[crash] code=0xc0000005 host=0x7ff6a1b2c3d4 module+0x1b2c3d4 access=read at 0x10\r\n"
        "[crash] backtrace (module-relative): 1b2c3d4 1b2c000\r\n"
        "[crash] guest live pc=0x2a1b40 ra=0x2a1b00 running=3 threads: [3 pc=0x2a1b40 ra=0x2a1b00 st=1]\r\n";

    const ZipStore::Entry *find(const std::vector<ZipStore::Entry> &entries, const std::string &name)
    {
        for (const ZipStore::Entry &e : entries)
            if (e.name == name)
                return &e;
        return nullptr;
    }

    diag::Inputs inputs()
    {
        diag::Inputs in;
        in.logName = "run_20260919_084912.log";
        in.logText = kLog;
        in.configText = kConfigWithSecrets;
        in.version = "SOCOM Unzipped 0e14323 (2026-09-19)";
        in.platform = "windows";
        in.homeDir = "C:\\Users\\secretuser";
        in.haveLastExit = true;
        in.lastExit = static_cast<int>(0xC0000005u);
        return in;
    }
}

void register_diagnostics_tests()
{
    MiniTest::Case("Diagnostics", [](TestCase &tc)
    {
        tc.Run("the bundle contains no credential and no home directory, whatever config.json and the log held", [](TestCase &t)
        {
            const std::vector<ZipStore::Entry> entries = diag::entries(inputs());
            const std::string zip = ZipStore::build(entries);
            t.IsTrue(!zip.empty(), "the entries make an archive");
            for (const char *secret : {"hunter2", "abc123token", "deadbeefcafe", "password", "sessionKey", "secretuser"})
            {
                t.IsTrue(zip.find(secret) == std::string::npos, std::string("the archive's bytes do not contain ") + secret);
                for (const ZipStore::Entry &e : entries)
                    t.IsTrue(e.data.find(secret) == std::string::npos, e.name + " does not contain " + secret);
            }
        });

        tc.Run("config.json: only the schema's keys, the ISO by file name only, the rest as the player set it", [](TestCase &t)
        {
            const std::string json = diag::sanitizedConfigJson(kConfigWithSecrets);
            launcher::Config c;
            t.IsTrue(launcher::fromJson(json, c), "what comes out is a config.json the launcher can read");
            t.Equals(c.isoPath, std::string("SOCOM II (USA).iso"), "the ISO's folder is gone, its name stays (it says which dump)");
            t.Equals(c.gsScale, 2, "settings survive");
            t.Equals(c.server, std::string("10.0.0.5"), "the custom server stays: an online report is useless without it (R134)");
            t.Equals(c.profile, std::string("viper"), "the profile stays: it names the card folder");
            t.Equals(json, launcher::toJson(c), "and it is exactly toJson of that: nothing else can be in it");
            launcher::Config forward;
            forward.isoPath = "/home/secretuser/discs/socom2.iso";
            t.IsTrue(diag::sanitizedConfigJson(launcher::toJson(forward)).find("secretuser") == std::string::npos, "forward slashes too");
            const std::string bad = diag::sanitizedConfigJson("{ \"password\": \"hunter2\", ");
            t.IsTrue(bad.find("hunter2") == std::string::npos, "a malformed config is never copied through");
            t.IsTrue(bad.find("\"error\"") != std::string::npos, "it is replaced by a note that says so");
        });

        tc.Run("scrub: the home directory becomes ~ in either slash style, and a short one is left alone", [](TestCase &t)
        {
            t.Equals(diag::scrub("at C:\\Users\\bob\\x and C:/Users/bob/y", "C:\\Users\\bob"), std::string("at ~\\x and ~/y"), "both styles");
            t.Equals(diag::scrub("/home/bob/socom2.iso", "/home/bob"), std::string("~/socom2.iso"), "POSIX");
            t.Equals(diag::scrub("/a/b", "/"), std::string("/a/b"), "a root is not a home");
            t.Equals(diag::scrub("text", ""), std::string("text"), "nor is nothing");
        });

        tc.Run("gl_caps.txt: raylib's device lines and the backend's own, CRs dropped", [](TestCase &t)
        {
            const std::string caps = diag::glCapsLines(kLog);
            t.Equals(caps, std::string("INFO:     > Vendor:   NVIDIA Corporation\n"
                                       "INFO:     > Renderer: NVIDIA GeForce RTX 4070 SUPER/PCIe/SSE2\n"
                                       "INFO:     > Version:  3.3.0 NVIDIA 595.97\n"
                                       "INFO:     > GLSL:     3.30 NVIDIA via Cg compiler\n"
                                       "[gs-gl] depth mapping: clip-control (GL_ZERO_TO_ONE, z exact)\n"
                                       "[gs-gl] initialised: 3.3.0 NVIDIA 595.97\n"), "the six lines, in the log's order");
            t.Equals(diag::glCapsLines("[audio] only\n"), std::string("no GL line in this log\n"), "a run that died before the window says so");
            t.IsTrue(diag::glCapsLines("[gs-gl] switching to the CPU rasterizer: OpenGL 3.3\n").find("switching") != std::string::npos, "the fallback line is a caps line");
        });

        tc.Run("crash.txt: there when the log has a record, absent when it has none", [](TestCase &t)
        {
            const std::vector<ZipStore::Entry> crashed = diag::entries(inputs());
            const ZipStore::Entry *record = find(crashed, "crash.txt");
            t.IsNotNull(record, "a log with [crash] lines yields crash.txt");
            if (record)
            {
                t.IsTrue(record->data.find("[crash] code=0xc0000005") == 0, "it starts with the handler's first line");
                t.IsTrue(record->data.find("[audio]") == std::string::npos, "and holds nothing else");
            }
            diag::Inputs clean = inputs();
            clean.logText = "[gs-gl] initialised: 3.3.0\n[audio] ok\n";
            t.IsNull(find(diag::entries(clean), "crash.txt"), "no record, no file");
            t.Equals(diag::crashRecord("[terminate] unhandled exception\n[main] fatal exception: x\n[oom] exit 71\n[preflight] exit 66 disc-not-found: s (d)\n[gs-gl] FATAL render target\n[pc] x\n"),
                     std::string("[terminate] unhandled exception\n[main] fatal exception: x\n[oom] exit 71\n[preflight] exit 66 disc-not-found: s (d)\n[gs-gl] FATAL render target\n"),
                     "every way this process announces its own death");
        });

        tc.Run("the entries: their names, the log under log/, versions.txt with the last exit explained", [](TestCase &t)
        {
            const std::vector<ZipStore::Entry> entries = diag::entries(inputs());
            for (const char *name : {"log/run_20260919_084912.log", "config.json", "gl_caps.txt", "crash.txt", "versions.txt"})
                t.IsNotNull(find(entries, name), std::string("has ") + name);
            t.Equals(static_cast<int>(entries.size()), 5, "and nothing else");
            const ZipStore::Entry *versions = find(entries, "versions.txt");
            if (versions)
            {
                t.IsTrue(versions->data.find("launcher: SOCOM Unzipped 0e14323 (2026-09-19)\n") != std::string::npos, "the launcher's version.txt");
                t.IsTrue(versions->data.find("platform: windows\n") != std::string::npos, "the platform");
                t.IsTrue(versions->data.find("last exit: -1073741819 -> 70 crashed: The game crashed.") != std::string::npos, "the raw status, the code and the sentence");
            }
            diag::Inputs bare;
            bare.platform = "linux";
            const std::vector<ZipStore::Entry> least = diag::entries(bare);
            t.Equals(static_cast<int>(least.size()), 2, "no log and no config: gl_caps.txt and versions.txt still");
            const ZipStore::Entry *v = find(least, "versions.txt");
            t.IsTrue(v && v->data.find("launcher: development build\n") != std::string::npos, "no version.txt reads as the About page reads it");
            t.IsTrue(v && v->data.find("last exit: no run in this launcher session\n") != std::string::npos, "and no run says so");
            diag::Inputs odd = inputs();
            odd.logName = "..\\..\\evil.log";
            t.IsNotNull(find(diag::entries(odd), "log/run.log"), "a log name the zip would refuse is stored as log/run.log");
        });

        tc.Run("a long log keeps its head and its tail and says what it dropped", [](TestCase &t)
        {
            std::string log(1000, 'h');
            log += std::string(5000, 'm');
            log += std::string(2000, 't');
            const std::string clipped = diag::clipLog(log, 1000, 2000);
            t.IsTrue(clipped.rfind(std::string(1000, 'h'), 0) == 0, "the head: the boot lines");
            t.IsTrue(clipped.size() >= 2000 && clipped.compare(clipped.size() - 2000, 2000, std::string(2000, 't')) == 0, "the tail: the ending");
            t.IsTrue(clipped.find("[diagnostics] 5000 bytes omitted here") != std::string::npos, "and the gap is named");
            t.IsTrue(std::count(clipped.begin(), clipped.end(), 'm') < 10, "the middle is gone (the only m left is the marker's)");
            t.Equals(diag::clipLog("short", 1000, 2000), std::string("short"), "a log that fits is left alone");
        });
    });
}
```

Register it (`void register_diagnostics_tests();`, the call, `    src/diagnostics_tests.cpp`). Build. **Expected RED:** `fatal error: 'launcher/diagnostics.h' file not found`.

- [x] **Step 2: Write `ps2xShared/include/launcher/diagnostics.h`.**

```cpp
#pragma once

// Sprint 9 Goal 1: the diagnostics zip's contents, as a pure function from what the launcher read off
// the disk to the entries ZipStore writes. Until now "Copy diagnostics" copied the log and config.json
// into a folder, verbatim (main.cpp copyDiagnostics).
//
// What must never be in it: a credential, and the player's home directory. config.json has no
// credential field today (the account lives on the memory card); the sanitiser is an allowlist so that
// stays true whatever a later build adds.

#include "ps2x/zip_store.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace launcher::diagnostics
{
    constexpr size_t kLogHeadBytes = 256u * 1024u;          // the boot: GL, audio, notices, preflight
    constexpr size_t kLogTailBytes = 4u * 1024u * 1024u;    // the ending: what went wrong

    std::string sanitizedConfigJson(const std::string &configText);
    std::string scrub(const std::string &text, const std::string &homeDir);
    std::string glCapsLines(const std::string &logText);
    std::string crashRecord(const std::string &logText);
    std::string joinClipped(const std::string &head, const std::string &tail, uint64_t omittedBytes);
    std::string clipLog(const std::string &logText, size_t headBytes = kLogHeadBytes, size_t tailBytes = kLogTailBytes);

    struct Inputs
    {
        std::string logName;      // "run_<stamp>.log"; empty when there is no log
        std::string logText;      // already clipped by the caller when it was read from a large file
        std::string configText;   // config.json as it is on disk; empty when there is none
        std::string version;      // version.txt's line; empty for a development build
        std::string platform;     // ExeDir::platformName()
        std::string homeDir;      // USERPROFILE / HOME; scrubbed out of every entry
        bool haveLastExit = false;
        long long lastExit = 0;   // GameProcess::exitCode(), raw
    };

    std::string versionsText(const Inputs &inputs);
    std::vector<ZipStore::Entry> entries(const Inputs &inputs);
}
```

- [x] **Step 3: Write `ps2xShared/src/diagnostics.cpp`** and add `    src/diagnostics.cpp` to `ps2x_shared`'s source list.

```cpp
#include "launcher/diagnostics.h"

#include "launcher/launcher_config.h"
#include "ps2x/exit_codes.h"

#include <algorithm>
#include <initializer_list>

namespace launcher::diagnostics
{
    namespace
    {
        bool startsWith(const std::string &line, const char *prefix)
        {
            return line.rfind(prefix, 0) == 0;
        }

        // The lines of `text` (CR dropped) that start with one of `prefixes`, each ended with '\n'.
        std::string linesStartingWith(const std::string &text, std::initializer_list<const char *> prefixes)
        {
            std::string out;
            size_t pos = 0;
            while (pos < text.size())
            {
                size_t end = text.find('\n', pos);
                if (end == std::string::npos)
                    end = text.size();
                std::string line = text.substr(pos, end - pos);
                pos = end + 1;
                if (!line.empty() && line.back() == '\r')
                    line.pop_back();
                for (const char *prefix : prefixes)
                    if (startsWith(line, prefix))
                    {
                        out += line;
                        out.push_back('\n');
                        break;
                    }
            }
            return out;
        }

        void replaceAll(std::string &text, const std::string &what, const std::string &with)
        {
            if (what.empty())
                return;
            size_t pos = 0;
            while ((pos = text.find(what, pos)) != std::string::npos)
            {
                text.replace(pos, what.size(), with);
                pos += with.size();
            }
        }
    }

    std::string sanitizedConfigJson(const std::string &configText)
    {
        Config config;
        if (!fromJson(configText, config))
            return "{\n  \"error\": \"config.json was malformed and is not included\"\n}\n";
        const size_t slash = config.isoPath.find_last_of("/\\");
        if (slash != std::string::npos)
            config.isoPath = config.isoPath.substr(slash + 1);
        return toJson(config);
    }

    std::string scrub(const std::string &text, const std::string &homeDir)
    {
        if (homeDir.size() < 4)
            return text;
        std::string out = text;
        std::string forward = homeDir, backward = homeDir;
        std::replace(forward.begin(), forward.end(), '\\', '/');
        std::replace(backward.begin(), backward.end(), '/', '\\');
        replaceAll(out, homeDir, "~");
        replaceAll(out, forward, "~");
        replaceAll(out, backward, "~");
        return out;
    }

    std::string glCapsLines(const std::string &logText)
    {
        const std::string lines = linesStartingWith(logText, {"INFO:     > Vendor:", "INFO:     > Renderer:", "INFO:     > Version:",
                                                              "INFO:     > GLSL:", "[gs-gl] initialised", "[gs-gl] depth mapping",
                                                              "[gs-gl] note", "[gs-gl] switching to the CPU rasterizer"});
        return lines.empty() ? std::string("no GL line in this log\n") : lines;
    }

    std::string crashRecord(const std::string &logText)
    {
        return linesStartingWith(logText, {"[crash]", "[terminate]", "[main] fatal", "[oom]", "[preflight] exit", "[gs-gl] FATAL"});
    }

    std::string joinClipped(const std::string &head, const std::string &tail, uint64_t omittedBytes)
    {
        return head + "\n[diagnostics] " + std::to_string(omittedBytes) + " bytes omitted here\n" + tail;
    }

    std::string clipLog(const std::string &logText, size_t headBytes, size_t tailBytes)
    {
        if (logText.size() <= headBytes + tailBytes)
            return logText;
        return joinClipped(logText.substr(0, headBytes), logText.substr(logText.size() - tailBytes),
                           logText.size() - headBytes - tailBytes);
    }

    std::string versionsText(const Inputs &in)
    {
        std::string out;
        out += "launcher: " + (in.version.empty() ? std::string("development build") : in.version) + "\n";
        out += "platform: " + (in.platform.empty() ? std::string("unknown") : in.platform) + "\n";
        out += "exit codes known: " + std::to_string(ExitCodes::kTableSize) + " (ps2x/exit_codes.h)\n";
        if (!in.haveLastExit)
        {
            out += "last exit: no run in this launcher session\n";
            return out;
        }
        const int code = ExitCodes::classify(in.lastExit);
        const ExitCodes::Entry *e = ExitCodes::find(code);
        out += "last exit: " + std::to_string(in.lastExit) + " -> " + std::to_string(code) + " " + (e ? e->slug : "unknown") + ": " +
               ExitCodes::describe(in.lastExit) + "\n";
        return out;
    }

    std::vector<ZipStore::Entry> entries(const Inputs &in)
    {
        std::vector<ZipStore::Entry> out;
        if (!in.logName.empty() || !in.logText.empty())
        {
            std::string name = "log/" + in.logName;
            if (in.logName.empty() || !ZipStore::nameAllowed(name) || in.logName.find('/') != std::string::npos)
                name = "log/run.log";
            out.push_back({name, scrub(clipLog(in.logText), in.homeDir)});
        }
        if (!in.configText.empty())
            out.push_back({"config.json", scrub(sanitizedConfigJson(in.configText), in.homeDir)});
        out.push_back({"gl_caps.txt", scrub(glCapsLines(in.logText), in.homeDir)});
        const std::string record = crashRecord(in.logText);
        if (!record.empty())
            out.push_back({"crash.txt", scrub(record, in.homeDir)});
        out.push_back({"versions.txt", scrub(versionsText(in), in.homeDir)});
        return out;
    }
}
```

- [x] **Step 4: GREEN.** `PS2X_TEST_SUITE=Diagnostics ./ps2x_tests.exe` -> `Total Tests: 7`, `Failed: 0`.

- [x] **Step 5: `./build.sh test` exit 0 (`Total Tests: B + 30`), then commit.**

```bash
git add third_party/ps2recomp/ps2xShared/include/launcher/diagnostics.h third_party/ps2recomp/ps2xShared/src/diagnostics.cpp third_party/ps2recomp/ps2xTest/src/diagnostics_tests.cpp
git commit -m "feat: the diagnostics bundle as a pure function -- the clipped log, config.json through an allowlist with the ISO by name only, the GL lines, the crash record, versions; the home directory scrubbed from every entry (R134, R135)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared/include/launcher/diagnostics.h \
  third_party/ps2recomp/ps2xShared/src/diagnostics.cpp \
  third_party/ps2recomp/ps2xShared/CMakeLists.txt \
  third_party/ps2recomp/ps2xTest/src/diagnostics_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/main.cpp \
  third_party/ps2recomp/ps2xTest/CMakeLists.txt
git push
```

---

## Task 9 — SAVE DIAGNOSTICS writes the zip; `--diagnostics`; `version.txt`  **[Judgment, small]**

**Files:**
- Create: `tools_py/tests/test_diagnostics_zip.py`
- Modify: `ps2xLauncher/src/main.cpp` (:7-8 the usage comment, :125-138 `copyDiagnostics`, :497 the CLI modes, :951-952 the request), `ps2xLauncher/src/ui/page_play.cpp` (:70), `scripts/make_portable.sh` (both branches), `tools_py/tests/test_make_portable.py`

**Interfaces:**
- `socom_unzipped_launcher --diagnostics <out.zip> [home]` — headless: writes the zip for `home` (default: the launcher's own folder), prints one line, exits 0 (written) or 1. No window, no raylib call: it runs in CI.
- The PLAY page's button reads **SAVE DIAGNOSTICS** (the spec's words; the node id `play.diagnostics` and its rect are unchanged, so the focus-model cases do not move), writes `diagnostics/socom_unzipped_<stamp>.zip` and opens that folder (R137).
- `scripts/make_portable.sh` writes `version.txt` — `SOCOM Unzipped <git describe --always --dirty> (<UTC date>)` — into the portable folder on both platforms (R138).

**Steps:**

- [x] **Step 1: RED (the zip, opened by a test).** Create `tools_py/tests/test_diagnostics_zip.py`:

```python
"""Sprint 9 Goal 1: the launcher's diagnostics zip, written by the real launcher and opened by Python's
zipfile -- an independent reader for ps2x/zip_store.h -- and searched for anything a stranger should not
be handing over. Runs wherever the launcher is built, CI included (--diagnostics opens no window)."""
import json
import os
import subprocess
import tempfile
import unittest
import zipfile

from tools_py.parity import hostplatform

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAUNCHER = os.path.join(ROOT, os.path.dirname(hostplatform.runtime_exe()),
                        hostplatform.exe_name("socom_unzipped_launcher"))

LOG = "\n".join([
    "INFO:     > Renderer: Test Renderer",
    "[gs-gl] initialised: 3.3.0 Test",
    "[socom2] CD image: {home}/Games/socom2.iso",
    "[crash] code=0xc0000005 host=0x1 module+0x1 access=read at 0x10",
    "",
])


@unittest.skipUnless(os.path.isfile(LAUNCHER), "no launcher build at " + LAUNCHER)
class DiagnosticsZipTest(unittest.TestCase):
    def test_the_zip_opens_holds_the_five_files_and_no_credential(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = os.path.join(tmp, "Users", "secretuser")
            game = os.path.join(tmp, "game")
            os.makedirs(os.path.join(game, "logs"))
            os.makedirs(fake_home)
            with open(os.path.join(game, "config.json"), "w") as fh:
                json.dump({"isoPath": os.path.join(fake_home, "Games", "socom2.iso"), "gsScale": 2,
                           "password": "hunter2", "token": "abc123token", "profile": "viper"}, fh)
            with open(os.path.join(game, "logs", "run_20200101_000000.log"), "w") as fh:
                fh.write("an older run\n")
            with open(os.path.join(game, "logs", "run_20260101_000000.log"), "w") as fh:
                fh.write(LOG.format(home=fake_home))
            with open(os.path.join(game, "version.txt"), "w") as fh:
                fh.write("SOCOM Unzipped test (2026-01-01)\n")
            out = os.path.join(tmp, "out.zip")
            env = {**os.environ, "USERPROFILE": fake_home, "HOME": fake_home}
            r = subprocess.run([LAUNCHER, "--diagnostics", out, game], capture_output=True, text=True,
                               timeout=20, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with zipfile.ZipFile(out) as z:
                self.assertIsNone(z.testzip())   # every CRC-32 checks out under an independent reader
                names = sorted(z.namelist())
                self.assertEqual(names, ["config.json", "crash.txt", "gl_caps.txt",
                                         "log/run_20260101_000000.log", "versions.txt"])
                for info in z.infolist():
                    self.assertEqual(info.compress_type, zipfile.ZIP_STORED, info.filename)
                blob = b"".join(z.read(n) for n in names)
                config = json.loads(z.read("config.json"))
                versions = z.read("versions.txt").decode()
                crash = z.read("crash.txt").decode()
            for secret in (b"hunter2", b"abc123token", b"password", b"secretuser"):
                self.assertNotIn(secret, blob)
            self.assertEqual(config["isoPath"], "socom2.iso")
            self.assertEqual(config["gsScale"], 2)
            self.assertNotIn("password", config)
            self.assertIn("launcher: SOCOM Unzipped test (2026-01-01)", versions)
            self.assertTrue(crash.startswith("[crash] code=0xc0000005"))


if __name__ == "__main__":
    unittest.main()
```

Run: `python -m unittest tools_py.tests.test_diagnostics_zip -v`. **Expected RED against the old launcher:** it does not know `--diagnostics`, so it opens its window and the test fails with `subprocess.TimeoutExpired: … timed out after 20 seconds` (a launcher window appears for 20 s and is killed; mind the quiet gate).

- [x] **Step 2: RED (`version.txt`).** In `tools_py/tests/test_make_portable.py`, inside `test_folder_has_the_game_the_launcher_the_dlls_the_readme_and_the_licences`, after the `README.txt` assertion (line 31), add:

```python
            # Sprint 9 Goal 1: the About page and the diagnostics zip read version.txt; nothing wrote it before.
            with open(os.path.join(pkg, "version.txt")) as fh:
                self.assertRegex(fh.read(), r"^SOCOM Unzipped \S+ \(\d{4}-\d{2}-\d{2}\)\n$")
```

Run: `python -m unittest tools_py.tests.test_make_portable -v`. **Expected RED:** `FileNotFoundError: … version.txt`.

- [x] **Step 3: `scripts/make_portable.sh`.** In the Linux branch directly after `chmod +x "$PKG/socom2" "$PKG/socom_unzipped_launcher"` (line 32), and in the Windows branch directly after `cp "$DIST"/*.dll "$PKG/"` (line 98), the same two lines:

```bash
# Sprint 9 Goal 1: the launcher's About page and its diagnostics zip read version.txt; until now nothing wrote it.
printf 'SOCOM Unzipped %s (%s)\n' "$(git -C "$ROOT" describe --always --dirty 2>/dev/null || echo unknown)" "$(date -u +%Y-%m-%d)" > "$PKG/version.txt"
```

- [x] **Step 4: `ps2xLauncher/src/main.cpp`.** Add `#include "launcher/diagnostics.h"`, `#include "ps2x/exe_dir.h"` and `#include "ps2x/zip_store.h"` after `#include "launcher/sha256.h"` (line 15), and `#include <cstdint>` among the standard headers. Replace `copyDiagnostics` (lines 125-138) with:

```cpp
    // The newest logs/run_<stamp>.log by name (the stamp sorts), for a launcher that has not started a
    // game this session -- or a game that was double-clicked (the bare run writes the same names).
    std::string newestRunLog(const fs::path &logs)
    {
        std::string best;
        std::error_code ec;
        for (fs::directory_iterator it(logs, ec), end; !ec && it != end; it.increment(ec))
        {
            const std::string name = it->path().filename().string();
            if (name.rfind("run_", 0) == 0 && it->path().extension() == ".log" && name > best)
                best = name;
        }
        return best.empty() ? std::string() : (logs / best).string();
    }

    // A log can be hundreds of megabytes; only its head and tail are ever read.
    std::string readLogClipped(const fs::path &p)
    {
        namespace diag = launcher::diagnostics;
        std::ifstream in(p, std::ios::binary);
        if (!in)
            return {};
        in.seekg(0, std::ios::end);
        const uint64_t size = static_cast<uint64_t>(in.tellg());
        in.seekg(0, std::ios::beg);
        if (size <= diag::kLogHeadBytes + diag::kLogTailBytes)
        {
            std::string all(static_cast<size_t>(size), '\0');
            in.read(all.data(), static_cast<std::streamsize>(size));
            return all;
        }
        std::string head(diag::kLogHeadBytes, '\0'), tail(diag::kLogTailBytes, '\0');
        in.read(head.data(), static_cast<std::streamsize>(head.size()));
        in.seekg(static_cast<std::streamoff>(size - diag::kLogTailBytes), std::ios::beg);
        in.read(tail.data(), static_cast<std::streamsize>(tail.size()));
        return diag::joinClipped(head, tail, size - diag::kLogHeadBytes - diag::kLogTailBytes);
    }

    // "Save diagnostics": one zip -- the last log, config.json through the allowlist, the GL lines, the
    // crash record if any, versions (launcher/diagnostics.h). `outZip` empty = diagnostics/ under `home`.
    bool saveDiagnostics(const fs::path &home, const fs::path &outZip, const std::string &lastLog,
                         bool haveLastExit, long long lastExit, std::string &message)
    {
        namespace diag = launcher::diagnostics;
        const std::string stamp = win32glue::stamp();
        const fs::path out = outZip.empty() ? home / "diagnostics" / ("socom_unzipped_" + stamp + ".zip") : outZip;
        std::error_code ec;
        if (out.has_parent_path())
            fs::create_directories(out.parent_path(), ec);

        diag::Inputs in;
        const std::string log = (!lastLog.empty() && fs::exists(lastLog)) ? lastLog : newestRunLog(home / "logs");
        if (!log.empty())
        {
            in.logName = fs::path(log).filename().string();
            in.logText = readLogClipped(log);
        }
        in.configText = readText(home / "config.json");
        in.version = readText(home / "version.txt");
        while (!in.version.empty() && (in.version.back() == '\n' || in.version.back() == '\r'))
            in.version.pop_back();
        in.platform = ExeDir::platformName();
        const char *homeDir = std::getenv("USERPROFILE");
        if (homeDir == nullptr || *homeDir == '\0')
            homeDir = std::getenv("HOME");
        in.homeDir = homeDir ? homeDir : "";
        in.haveLastExit = haveLastExit;
        in.lastExit = lastExit;

        uint16_t date = 0x0021, time = 0;
        ZipStore::dosDateTime(stamp, date, time);
        const std::string bytes = ZipStore::build(diag::entries(in), date, time);
        std::ofstream file(out, std::ios::binary | std::ios::trunc);
        if (bytes.empty() || !file)
        {
            message = "cannot write " + out.string();
            return false;
        }
        file.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
        file.flush();
        if (!file)
        {
            message = "cannot write " + out.string();
            return false;
        }
        message = "saved " + out.string();
        return true;
    }
```

Directly **above** the `--selftest` block (line 497), the headless mode:

```cpp
    if (argc > 2 && std::strcmp(argv[1], "--diagnostics") == 0)
    {
        // Sprint 9 Goal 1: the zip without the window -- for a report from a machine where the launcher
        // itself will not open, and for tools_py/tests/test_diagnostics_zip.py.
        std::string message;
        const bool ok = saveDiagnostics(argc > 3 ? fs::path(argv[3]) : dir, fs::path(argv[2]), std::string(), false, 0, message);
        std::printf("%s\n", message.c_str());
        return ok ? 0 : 1;
    }
```

The request handler (lines 951-952) becomes:

```cpp
            if (app.requestDiagnostics)
            {
                std::string message;
                if (saveDiagnostics(dir, fs::path(), lastLog, haveLastExit, lastExitRaw, message))
                    win32glue::openFolder((dir / "diagnostics").string());
                app.status = message;
            }
```

Add the third usage line to the file's header comment (after line 8): `//   socom_unzipped_launcher.exe --diagnostics <out.zip> [dir]   write the diagnostics zip for <dir> (default: this folder), no window`.

- [x] **Step 5: `ps2xLauncher/src/ui/page_play.cpp:70`** — the label only: `"COPY DIAGNOSTICS"` becomes `"SAVE DIAGNOSTICS"`. Then look at it: `dist/socom_unzipped_launcher.exe --screenshot logs/parity/launcher_ui_s9` and open `play_1100x700.png` and `play_900x600.png` (the names `main.cpp:1015` writes): the label fits its 200-unit button at both sizes, and LAST RUN reads "The last run exited normally." If the label is ellipsized or overflows at 900x600, shorten it to `DIAGNOSTICS` and say so in the ledger — do not resize the node (`focus.cpp:112`), the focus cases assert on it.

- [x] **Step 6: GREEN.**

```bash
cmake --build third_party/ps2recomp/build-clang --target socom_unzipped_launcher -j 8 \
  && cp third_party/ps2recomp/build-clang/ps2xLauncher/socom_unzipped_launcher.exe dist/
python -m unittest tools_py.tests.test_diagnostics_zip tools_py.tests.test_make_portable -v
```

Expected: `OK` (3 tests; `test_make_portable` is skipped where there is no PowerShell).

- [x] **Step 7: `./build.sh test` exit 0 (`Total Tests: B + 30`, Python `P + 14`), then commit.**

```bash
git add tools_py/tests/test_diagnostics_zip.py
git commit -m "feat(launcher): SAVE DIAGNOSTICS writes one zip (log, config through the allowlist, GL lines, crash record, versions) instead of copying a folder; --diagnostics writes it with no window; make_portable writes version.txt (R137, R138)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xLauncher/src/main.cpp \
  third_party/ps2recomp/ps2xLauncher/src/ui/page_play.cpp \
  scripts/make_portable.sh \
  tools_py/tests/test_make_portable.py \
  tools_py/tests/test_diagnostics_zip.py
git push
```

---

## Task 10 — The Linux ring and the close-out  **[Judgment]**

**Files:** `docs/KNOWN.md`, `docs/STATUS.md`, `docs/CURRENT_SPRINT.md`, `docs/HUMAN_TASKS.md`, this plan.

- [x] **Step 1: CI.** The `linux` workflow on the Task 9 commit is green: `ps2x_shared` compiles under system clang, `ps2x_tests` runs the six new suites (`ExitCodes`, `Preflight`, `BareRun`, `ZipStore`, `Diagnostics`, and the grown `Launcher`), and `test_diagnostics_zip` **runs** there (the launcher is built; `--diagnostics` needs no display). `test_runner_exit_codes` is skipped there by design. Read `logs/ci`'s uploaded `build_linux_test.log` for `Failed: 0` and for `test_the_zip_opens… ok` — a skip of the zip test in CI is a failure of this step (it means `LAUNCHER`'s path is wrong on Linux).
- [x] **Step 2: The VM.** `scripts/vm_sync.sh tree`, then in the VM `bash scripts/build_linux.sh all && bash scripts/build_linux.sh test` (Task 6 Step 8 already built the runner there): C++ `B_linux + 30`, Python with `test_runner_exit_codes` **run, not skipped** (8 tests). Then `bash scripts/make_portable.sh` in the VM and `tar -tzf dist-linux/portable/socom2-linux.tar.gz | grep version.txt` prints one line. Then, from the unpacked tarball with no `DISPLAY`: `./socom2 --home "$PWD/nowhere"; echo $?` prints `68` and `./socom_unzipped_launcher --diagnostics /tmp/d.zip && python3 -m zipfile -l /tmp/d.zip` lists the entries.
- [x] **Step 3: `docs/HUMAN_TASKS.md`**, three lines under the owner's launcher item: (a) double-click `socom2.exe` in the portable folder — the game starts on the launcher's settings and no black console window stays behind it (R132); (b) rename the ISO and press LAUNCH — LAST RUN reads the disc-not-found sentence; (c) on the real Linux box, with the audio device disabled, LAST RUN ends with "No audio device was found; the game ran without sound."
- [x] **Step 4: `docs/KNOWN.md` (controller only).** New proven rows, each naming its artefact: the taxonomy (`ps2x/exit_codes.h`, suites `ExitCodes` + `test_exit_codes_table`); the preflight and the bare run (`test_runner_exit_codes`, gate `s9_g1_gate`); the diagnostics zip (`test_diagnostics_zip`). New believed-not-proven rows: the console detach and the audio notice (Step 3's owner checks); "a gate or harness flow that drives a non-r0001 image now exits 67" (R130, no such flow exists today). Retract nothing unless a step above killed something.
- [x] **Step 5: `docs/STATUS.md` and `docs/CURRENT_SPRINT.md`.** A dated entry: what landed, the suite totals, the gate stamp, R126-R138 by one-line title; Goal 1 marked DONE in the Sprint 9 block with `next ruling: R139`; the pointer moved to Goal 2's plan.
- [x] **Step 6: Tick this plan's boxes; leave a reason on every one that stays open.** A box with neither a tick nor a reason is the failure mode the Sprint 6 close-out audit found.
- [x] **Step 7: Commit.**

```bash
git commit -m "docs: Sprint 9 Goal 1 closed -- a failure explains itself (the taxonomy, the bare run, the diagnostics zip); R126-R138

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  docs/KNOWN.md docs/STATUS.md docs/CURRENT_SPRINT.md docs/HUMAN_TASKS.md \
  docs/archive/sprints-7-12/2026-09-19-sprint-9-goal-1-failures-explain-themselves.md
git push
```

---

## Rulings made on the owner's behalf

R126 onward (Sprint 8's last was R125, in the Goal 2b plan). Each is a decision this plan made where the spec was silent or the tree disagreed with it; each is the controller's to overturn before the task that carries it starts.

- **R126** (Task 1): **the shared code lives in a new library, `third_party/ps2recomp/ps2xShared/` (`ps2x_shared`), and `iso9660`, `sha256` and `launcher_config` move into it with their include paths (`launcher/…`) and namespaces unchanged.** The runner needs `fromJson`/`environmentFor` (the bare run) and the ISO reader plus SHA-256 (is this disc r0001?). Linking `ps2x_launcher_core` would drag the launcher's focus model and pad geometry into `socom2`; pointing a runtime target at `../ps2xLauncher/src/*.cpp` would make the launcher's folder a dependency of a runner that ships without it on Vita and Android (the top-level `CMakeLists.txt` adds `ps2xLauncher` only on desktop, and *after* `ps2xRuntime`, so its targets do not exist when the runtime is configured). A third directory, added first and depending on nothing, is the only shape in which "the runtime does not link the launcher" is true at the directory level. Keeping `launcher/` and `launcher::` makes Task 1 six `git mv`s and two CMake edits with **zero** source edits. *Cost if wrong:* a namespace called `launcher` inside a library the runner links reads oddly; a rename is a mechanical follow-up, and doing it now would turn a no-behaviour-change commit into a 40-file diff.

- **R127** (Task 2): **the numbers are 66-72 contiguous, and 1 and 3 are named rather than moved.** 66 disc not found, 67 not r0001, 68 ELF, 69 config, 70 crash, 71 out of memory, 72 card folder: inside a byte, below the shell's 126-165, clear of 65, and clear of 75, which `scripts/run_detached.sh` writes to its marker for BUSY (a different namespace, but a harness log that shows "75" should mean one thing). 1 is what `main()`'s catch-all and a failed `initialize` already return, and 3 is what `abort()` yields on the mingw CRT *and* what `LoadExecPS2` exits with (`Thread.cpp:206`); renumbering either changes behaviour the gate and the harness have lived with, for no gain a stranger would see — they get sentences instead. The brief's "disc not found / not r0001" is split into two codes because the player's action differs (choose the file again vs. find the right disc). *Cost if wrong:* 3 means two things (an abort, a game-requested reboot); both sentences would be "it stopped itself, send the log", so one sentence serves.

- **R128** (Task 2, Task 6): **a crash keeps its native exit status, and `ExitCodes::classify` folds it onto 70 for whoever reads it; the crash handlers are not touched.** The spec says "crash (the handler's code)" — the handlers have none (Handoff note 1). Making them choose one means `TerminateProcess(…, 70)` from a first-chance vectored handler on Windows (wrong: it would kill the process on exceptions a later frame handles) or a second, unhandled-exception filter, and replacing Linux's re-raise with `_exit(70)` — which throws away the core dump, the shell's "Segmentation fault", and the exact behaviour Sprint 8's review hardened (F2, F3). The launcher and the harness are the only readers of the status, and both go through one function. *Cost if wrong:* a third-party wrapper that runs `socom2` and reads `$?` sees 139 or `0xC0000005`, not 70 — which is what it would see from any other program that crashed.

- **R129** (Tasks 2, 3, 6): **"audio device absent" is a `[notice] ` line in the log, read back by the launcher, not an exit code.** The spec says non-fatal and reported; an exit code can only report one thing and the run may also end in 65 or 70. One line format (`[notice] <slug>: <sentence>`), one reader (`noticesIn`), sentences appended to LAST RUN. *Cost if wrong:* the launcher reads the first 256 KiB of the log after each run — a millisecond — and a notice printed later than that (none exists) would be missed.

- **R130** (Tasks 4, 6): **the preflight is fatal, runs for every start of `socom2_game.elf` including the gate's, and has no off switch.** Order: ELF, card folder, disc found, disc is r0001 — cheapest first, and the card folder before the disc so each failure can be driven by a test without a real disc. Until now a missing disc was a WARNING and a black window; SOCOM cannot run without its disc, so nothing legitimate is lost. The r0001 check costs one read of `SCUS_972.75` (a few MB) and one SHA-256 per start. It applies only when the ELF's file name is `socom2_game.elf` — the same key the game override registers under — so the generic runner still starts other ELFs. No `PS2X_PREFLIGHT=0`: Goal 3 is retiring knobs, and an escape hatch is exactly the environment accident it exists to prevent; if a developer flow ever needs a patched image it belongs behind Goal 3's `--dev`. *Cost if wrong:* a harness flow that mounted a non-r0001 image would now stop with 67. None exists today (`drive.py:42-53` exports the one resolved ISO), and the failure is loud, immediate and names itself.

- **R131** (Tasks 5, 6): **the bare run — absent `config.json` is the defaults, the environment wins over the file, the card folder is made absolute, the process changes directory to its own folder, and `--home <dir>` is the same run rooted elsewhere.** Absent-is-defaults because a stranger who unpacks and double-clicks `socom2` before ever opening the launcher should get a game if their ISO is beside it, and otherwise the *disc* sentence (which tells them what to do) rather than a config sentence (which does not). Environment-wins because spec Goal 3 already says "the env var kept as an override", and because it keeps every existing developer invocation meaning what it meant. `--home` exists so the tests never touch `dist/config.json`, which is the owner's. *Cost if wrong:* the launcher's rule is the opposite (its settings win over the inherited environment, `mergeEnvironment`); a player who has a stray `PS2X_GS_SCALE` in their shell sees it beat `config.json` on a double-click but not from the launcher. The `[bare-run] N of M settings taken` log line makes that visible.

- **R132** (Tasks 5, 6): **a bare run writes `logs/run_<stamp>.log` itself and, on Windows, lets go of a console it alone owns.** Without the first, a double-clicked game has no log and SAVE DIAGNOSTICS has nothing to save; the name and folder are the launcher's own so `newestRunLog` finds it. Without the second, the double-click this goal exists for opens an empty black window behind the game (`socom2.exe` is a console-subsystem binary, and must stay one for the harness). `GetConsoleProcessList(...) == 1` is true only for a console Explorer created for us, so a run from a terminal keeps its terminal. Neither can be unit-tested; the first is exercised by every `test_runner_exit_codes` case, the second is an owner check (Task 10 Step 3). *Cost if wrong:* a developer who runs `socom2` with no argument in a terminal finds the output in a file instead of on screen — one stderr line says where before the switch.

- **R133** (Task 7): **the zip writer is written here: STORE only, CRC-32, no zip64, built in memory.** Nothing is vendored (Handoff note 9) and the brief rules out a new dependency. The bundle is text and a few megabytes; compression would save the player a second of upload and cost the project a deflate implementation to own. The 4 GiB and 65534-entry limits return an empty archive rather than a corrupt one. Verified twice, independently: byte-for-byte against the format in `ZipStore`'s suite, and by Python's `zipfile` (`testzip()` re-computes every CRC) on the real launcher's output. *Cost if wrong:* a 4 MB attachment where 400 KB was possible.

- **R134** (Task 8): **"credential fields removed" is an allowlist, the ISO path is cut to its file name, the home directory is scrubbed from every entry — and `server`, `profile` and `micDevice` stay.** The schema has no credential (Handoff note 3), so a denylist would be a list of nothing; re-serialising through `Config` means only the fifteen known keys can ever appear, which is the property the spec wants and one that survives a future `password` key without anyone remembering this file. The privacy additions are the brief's spirit rather than its letter: `isoPath` and the log's `[socom2] CD image:` line carry `C:\Users\<name>\…`. What stays is what a report needs: which server (the hosted one is public; a custom one is the first question in any online report), the profile (it names the card folder), the microphone's device name. *Cost if wrong:* a player who considers their LAN server's address private shares it in a zip they chose to send; the README line Task 10 does not add could say so — flagged for the owner's review rather than decided further here.

- **R135** (Task 8): **the crash record is the log's own `[crash]` / `[terminate]` / `[main] fatal` / `[oom]` / `[preflight] exit` / `[gs-gl] FATAL` lines, and the log is clipped to its first 256 KiB and last 4 MiB.** There is no crash file to include (Handoff note 2), and writing one from inside a signal handler is a change to the most delicate code in the runner for the sake of a copy of lines that are already on disk. The head holds the boot (GL, audio, notices, preflight), the tail holds the ending; launcher-started logs measured on this host run 0.3-1.6 MB for a session, harness logs with tracing reach 189 MB. *Cost if wrong:* a fault whose explanation sits in the omitted middle of a very long session; the zip says how many bytes it dropped, and the full log is still in `logs/`.

- **R136** (Task 6): **`socom2 --fail-test crash|oom` ships in the release executable.** The spec's bar is "a test per code that drives the failing condition"; a crash and an exhausted heap cannot be arranged from outside the process on both platforms. Two argv words, handled before anything is initialised, reachable only by someone who types them. *Cost if wrong:* a player who types `--fail-test crash` crashes a game they had not started.

- **R137** (Task 9): **the button is renamed SAVE DIAGNOSTICS, writes `diagnostics/socom_unzipped_<stamp>.zip`, and opens that folder.** The spec calls it "Save diagnostics"; "copy" promised a clipboard. Opening the folder is the difference between a status line that scrolls away and a file the player can drag into a message. The node id and rect are unchanged so no layout or focus case moves. *Cost if wrong:* a label the owner preferred; one string.

- **R138** (Task 9): **`scripts/make_portable.sh` writes `version.txt` (`SOCOM Unzipped <git describe> (<UTC date>)`).** The launcher has read that file since Sprint 8 and nothing has ever written it (Handoff note 7), so every shipped About page says "development build" and the zip's `versions.txt` would too. Written by the packaging script rather than compiled in, so a rebuild with no source change stays byte-identical (Goal 2's `SHA256SUMS` will care). *Cost if wrong:* the runner itself still prints no version; Goal 2's release configuration is the place to add one if a report ever needs it.

## Self-review

- **Goal coverage, against the spec's four bullets and its bar.** *Taxonomy in one header, each code a sentence the launcher shows* -> Tasks 2-3 (`ps2x/exit_codes.h`; `lastRunLine`; the literal `65` in `launcher_config.cpp` is gone). *`socom2` with no argument reads `config.json`* -> Tasks 5-6. *The diagnostics zip* -> Tasks 7-9. *Bar: a test per code that drives the failing condition and asserts the code and the sentence* -> `test_runner_exit_codes.py` on the real runner (66 twice, 67, 68, 69, 70, 71, 72) and the `Preflight`/`BareRun` suites on the library (the same codes, in CI where there is no runner); 65 keeps Sprint 7's gate stage (`PS2X_GS_GL_FORCE_FAIL`), 0/1/3 are named not driven. *The launcher's selftest shows each sentence* -> Task 3 Step 4. *The zip is opened by a test and contains no credential* -> Task 9 Step 1 (`zipfile`, in CI) and Task 8's first case.
- **What the tree contradicted, and what the plan does instead** — nine items, in the Handoff notes, each tied to a ruling or a task: the handlers choose no exit code (R128); there is no crash record file (R135); `config.json` has no password or any credential (R134); the fallback text is "the game exited" and a test asserts silence for 0 and 1 (Task 2 Step 6); the window opens before the ELF is looked at (Task 6's preflight placement); `PS2X_MC_DIR` is relative (R131); `version.txt` is read and never written (R138); the Windows glue duplicates `mergeEnvironment` (left alone, noted); no archiver is vendored (R133). One more, about the brief rather than the spec: it says the runner's `main` may live "under `src/` or the socom2 game overrides" — it is `third_party/ps2recomp/ps2xRuntime/src/main.cpp` (`RUNNER_MAIN_CPP`, `src/runner/main.cpp`, does not exist; `ps2xRuntime/CMakeLists.txt:478-485` falls back to the root one), and the crash handlers are the only relevant code in the overrides.
- **Launch budget.** One detached runtime build, one gate (`s9_g1_gate`), one 60 s bare-run launch (Task 6 Step 5) — the spec's "one gate per runtime commit" with one commit under `ps2xRuntime/src/`. The Python cases that start `socom2` and the launcher are sub-second, window-less after GREEN, and held by the quiet gate like any suite; their REDs against the old binaries do open windows (seven brief ones in Task 6, one 20 s launcher in Task 9) and the steps say so.
- **Placeholder scan.** No `TBD`, no "handle edge cases", no "similar to Task N". The values left to the executor are measurements: the baselines `B`, `B_linux` and `P` (recorded in Task 1 Step 1 because other goals add cases to the same binaries), and the gate's stamp output. The one comment inside a code block that is an instruction rather than code — "lines 182-198 unchanged" in Task 6 Step 3 — is called out as such in the sentence after the block.
- **Type consistency.** `ExitCodes::{kOk…kCardDirUnwritable, Entry, kTable, kTableSize, find(int), classify(long long) -> int, describe(long long) -> std::string, Notice, kNoticePrefix, kNoAudioDevice, noticeLine(const Notice&), noticesIn(const std::string&)}`; `launcher::{exitMessage(int), lastRunLine(long long, const std::string&), selftestExitLines()}`; `Preflight::{Input, Result, findDisc(path, string), directoryWritable(path, string&), run(const Input&), logLine(const Result&)}`; `BareRun::{Plan, plan(path), applyEnvironment(vector<string>) -> int, stamp(), redirectOutput(path) -> string, detachOwnConsole()}`; `ExeDir::{get(), platformName()}`; `ProcessFatal::{installOutOfMemoryHandler(), failTest(const char*) -> int}`; `ZipStore::{Entry, crc32(const uint8_t*, size_t, uint32_t), nameAllowed, dosDateTime(string, uint16_t&, uint16_t&), build(vector<Entry>, uint16_t, uint16_t)}`; `launcher::diagnostics::{kLogHeadBytes, kLogTailBytes, sanitizedConfigJson, scrub, glCapsLines, crashRecord, joinClipped, clipLog, Inputs, versionsText, entries}`. Python: `tools_py.exit_codes.{table, code, sentence, classify, describe}`. Each is used with one signature everywhere it appears. New argv words: `socom2 --home <dir>`, `socom2 --fail-test crash|oom`, `socom_unzipped_launcher --diagnostics <zip> [dir]`. **No new `PS2X_*` environment variable** — Goal 3 is counting them.
- **Platform halves.** `#ifdef _WIN32` appears in exactly three new `.cpp` files (`exe_dir`, `bare_run`, `process_fatal`), each with its POSIX branch in the same function; the launcher's `main.cpp` gains none (the platform name and the home directory come through `ExeDir::platformName()` and `getenv` of both `USERPROFILE` and `HOME`). CI proves the library, the suites and the launcher's zip on Linux; the VM proves the runner (Task 6 Step 8, Task 10 Step 2), because CI builds `--no-runner`.
- **Owner gate.** Autonomous end to end. Three checks only a person can make are filed, not waited for (Task 10 Step 3): the double-click and its console, the LAST RUN sentence seen in the real window, the audio notice on a machine without a device. R134's "what stays in the config" and R137's label are the two rulings most likely to be a matter of taste; both are one-line changes.
