# Sprint 9 Goal 2 — A Smaller, Checkable Download: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The archive a stranger downloads is as small as measurement allows, carries nothing the two shipped executables do not load, and comes with a `SHA256SUMS` they can check; the executable inside it is a `release` build that has passed the three-stage gate 3/3 *as that executable*, with its symbols kept in a separate file for crash diagnosis. Today (measured 2026-09-19 at `e8e60b8`): `dist/portable/socom2-portable.zip` is **65,494,194 bytes** for a **297,839,981-byte** folder; `socom2.exe` is 236,405,760 bytes raw and 41,144,142 compressed (63 % of the zip), of which `.text` is 191,886,198; the folder carries **31 DLLs, of which the two shipped executables reach 16** through their import tables (33,474,560 bytes raw / 14,097,831 compressed) and **15 are reached by nothing** (21,999,104 raw / 8,057,620 compressed — 12.3 % of the zip); nothing writes a checksum; and nothing can point the gate at any executable other than `dist/socom2.exe`.

**Architecture:** Four independent pieces, each decided by a pure function under a test. (1) **`SOCOM_EXE`**: one environment variable, read by `tools_py/parity/hostplatform.py:runtime_exe` and by `run.sh`, names the runner the gate, the harness and the exit-code suite start; the gate writes the executable's path, size and SHA-256 into its `summary.txt`, so a gate record says what it scored. (2) **`tools_py/portable_audit.py`**: a pure-Python PE import-table reader and ELF `DT_NEEDED` reader (no `objdump`, no `ldd`, so it audits a Windows folder on Linux and a Linux folder on Windows), the import **closure** of the shipped executables over a folder, an **audit** (`missing` = imported and neither in the folder nor the operating system's; `orphans` = carried and imported by nothing), and the `SHA256SUMS` writer and verifier. `scripts/make_portable.sh` copies the closure instead of `*.dll`, audits what it assembled, and writes `SHA256SUMS` beside the archive — both branches. (3) **The release configuration**: three CMake switches that default OFF (`PS2X_RELEASE_LINK`: `-ffunction-sections -fdata-sections`, `--gc-sections`, `--as-needed` on Linux; `PS2X_LINK_ICF`; `PS2X_LTO_SCOPE`), a `release` step in `build.sh` and `scripts/build_linux.sh` that configures **its own build tree** (`third_party/ps2recomp/build-release`, `build-linux-release`) into **its own output folder** (`dist-release/`, `dist-linux-release/`), strips the two executables and keeps `symbols/<name>.debug`. The developer tree, `dist/socom2.exe`, the daily gate and every harness default are untouched. (4) **`tools_py/release_metrics.py`**: the three numbers the spec's bar needs, read from artefacts that already exist — the runner's link time from `.ninja_log`, a frame-rate sanity figure from the gate's own `mission.game.log` (`[pc-sampler]` rows: `vsync=` and `ee=` against host `t=`), and folder/archive sizes.

**Tech Stack:** CMake >= 3.20 + Ninja, llvm-mingw clang 23 / lld on the host (`build.sh`), system clang in the VM and CI (`scripts/build_linux.sh`), `llvm-objcopy`/`llvm-strip` (host) and `objcopy`/`strip` (Linux), Python 3 `unittest` (**not** pytest), `scripts/run_detached.sh` + `scripts/loop_lock.sh` for every build and every gate.

**Spec:** `docs/superpowers/specs/2026-09-19-sprint-9-a-strangers-first-run-design.md` §2 "Goal 2 — a smaller, checkable download" and §4 (Goal 2: two extra launches; every moved default or skipped measurement is a numbered ruling, next **R140**). **The stop rule, verbatim:** *"if LTO pushes the runner's link past 30 minutes or changes a gate score, ship without it and record why."* **Required reading for every dispatch:** this plan's Handoff notes and Global Constraints; `build.sh:1-49` and `:251-258`; `scripts/build_linux.sh` (all 110 lines); `scripts/make_portable.sh` (all 134 lines); `scripts/portable_libs.py`; `third_party/ps2recomp/CMakeLists.txt:1-30`; `third_party/ps2recomp/ps2xRuntime/cmake/ReleaseMode.cmake` (all) and `cmake/CopyFfmpegDlls.cmake`; `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt:8-11`, `:255-378` (FFmpeg on each platform), `:454-475`, `:521-545`, `:653-671`; `tools_py/parity/hostplatform.py:30-38`; `tools_py/parity/drive.py:58-98`; `run.sh` (all 14 lines); `tools_py/parity/gate.py:539-581` and `:614-675`; `tools_py/tests/test_make_portable.py`; `.github/workflows/linux.yml`.

## Handoff notes for the executing model (read once)

- **Process.** superpowers:subagent-driven-development; a fresh implementer per task; a task review after each; the controller merges. Ledger at `.superpowers/sdd/2026-09-20-sprint-9-goal-2/progress.md`. Decisions on the owner's behalf are `Ruling: … — why — cost if wrong`, numbered from **R140** (R139 is the crouch shortcut's); this plan uses R140-R150 and the next free number is **R151**.

- **What the tree says that the spec and the brief do not, in the order it will bite.**
  1. **The developer build is already `CMAKE_BUILD_TYPE=Release`.** `build.sh:36` and `scripts/build_linux.sh:50` configure Release, so `ps2_runtime`, raylib and the launcher are already `-O3 -DNDEBUG`. What makes it a developer build is two arguments: `-DPS2X_GENERATED_OPT="${GENOPT:--O1}"` (the 14,882 generated files at `-O1`, appended after the configuration's `-O3` so it wins: `ps2xRuntime/CMakeLists.txt:521-526`) and `-DPS2X_ENABLE_LTO="${LTO:-OFF}"` (the CMake option itself defaults **ON**, `ReleaseMode.cmake:5`). "A release configuration" is therefore not a build type; it is a second tree with different values for those two and three new switches (R140).
  2. **`PS2X_ENABLE_LTO=ON` is already ThinLTO, and it covers the generated code.** CMake's `INTERPROCEDURAL_OPTIMIZATION` for Clang emits `-flto=thin`; `EnableFastReleaseMode` applies it to `ps2_runtime` **and** `ps2EntryRunner` (`ps2xRuntime/CMakeLists.txt:653-657`), whose sources are the 14,882 generated files. "ThinLTO only where the link time allows" needs a way to leave the generated code out: `PS2X_LTO_SCOPE=runtime` (Task 4).
  3. **Today's link takes about one second.** `third_party/ps2recomp/build-clang/.ninja_log`: `ps2xRuntime/ps2EntryRunner.exe` 0.93 s and 0.96 s (lld, no LTO, 467 unity objects). The 30-minute rule is only reachable with LTO over the generated code. What is slow is *compiling*: 467 unity translation units, 4,477 CPU-seconds at `-O1`, and one of them — `Unity/unity_393_cxx.cxx.obj` — takes **526 s alone**, so no `-j` makes a full build faster than that one unit, and `-O2` will lengthen it.
  4. **None of the fifteen unneeded DLLs is "harness-only".** `dist/vu1_replay.exe` (the one harness tool in `dist/`) imports only `libc++.dll` and `libunwind.dll` among local files. The fifteen arrive two ways: `cmake/CopyFfmpegDlls.cmake` globs the **whole** `bin/` of the prebuilt FFmpeg zip next to every target (`avformat`, `avfilter`, `avdevice`, `SDL2`, the six OpenEXR/Imath libraries, `freetype`, `harfbuzz`, `libwebpdecoder`, `libwebpdemux`), and `build.sh:45-47` copies `libwinpthread-1.dll` by name although llvm-mingw's `libc++.dll` does not import it. `scripts/make_portable.sh:100` then ships `"$DIST"/*.dll`. The table is in Task 3.
  5. **No debug information is being shipped, so stripping is worth about 3 %.** `socom2.exe`'s `.debug_*` sections total 0.7 MB (the CRT's); the COFF symbol table is about 7 MB of the 236. Verified on a copy of the launcher: `llvm-objcopy --only-keep-debug` + `llvm-strip --strip-all` + `--add-gnu-debuglink` takes 2,914,304 -> 2,621,440 bytes, the `.debug` file is 304,128 bytes, holds all 5,320 symbols at the same addresses (`llvm-nm -n` agrees on `main`), and the stripped copy still runs. The size is `.text` — 192 MB of recompiled code — which is what `-Os`/`-O2`, `--icf` and `--gc-sections` are being measured against.
  6. **`--gc-sections` will find little in the generated code.** Every generated function is referenced from `register_functions.cpp`'s table, so none is unreachable. Identical-code folding (`--icf=all`) is the link-time switch with a chance against 14,882 machine-written functions; the spec does not name it, so it is a measured candidate under the same stop rule as LTO (R149).
  7. **Nothing can point the gate at another executable, and on Windows `runtime_exe()` is not even what launches.** `hostplatform.runtime_exe` returns a fixed `dist/socom2.exe` / `dist-linux/socom2` and takes no override; on Windows `drive.py:79-80` starts `bash ./run.sh`, and `run.sh:12` hardcodes `"$ROOT/dist/socom2.exe"`. Only the Linux branch (`drive.py:96`) calls `runtime_exe()`. Task 1 adds `SOCOM_EXE` to both. The harness finds and kills the game **by process name** (`hostplatform.kill_argv`, `running_argv`), so the release runner must still be called `socom2.exe` — it lives in its own folder, not under another name.
  8. **The gate cannot prove the DLL set.** `run.sh:6` puts `tools/llvm-mingw/bin` on `PATH`, so a `libc++.dll` missing from the folder is found there. The proof is Task 3's audit plus one sub-second run with `PATH` cut to `System32` (`test_portable_folder.py`).
  9. **Linux links two FFmpeg libraries it never calls, with no `--as-needed`.** `pkg_check_modules` asks for `libavformat` and `libswresample` (`ps2xRuntime/CMakeLists.txt:343-349`); the Windows import table shows the runner uses neither (`avcodec-61`, `avutil-59`, `swscale-8` only; `swresample-5` comes in through `avcodec`). With the default linker behaviour both become `DT_NEEDED`, `ldd` reports `libavformat`'s whole closure, and `scripts/portable_libs.py` copies it into `lib/`. `PS2X_RELEASE_LINK` adds `-Wl,--as-needed`; the effect on the 109 MB tarball is measured in the VM (Task 6) — the VM was down when this plan was written (`ssh: connect to host 127.0.0.1 port 2222: Connection refused`), so there is no Linux "before" figure here beyond Sprint 8's "224 MB runner, 109 MB tarball".
  10. **The brief's paths.** `portable_libs.py` is `scripts/portable_libs.py` (not `tools_py/`); `hostplatform.py` is `tools_py/parity/hostplatform.py`.
  11. **`test_make_portable.py` builds its fake `dist/` from files containing `b"x"`.** Once the script reads import tables those are not PE files; Task 3 replaces them with 1 KB synthetic PEs from `tools_py/tests/binfmt_fixtures.py`. The test's skip guard (`bash` **and** `powershell`) means it has never run on Linux: Task 3 adds `test_make_portable_linux.py`, which runs in CI against the launcher CI already builds.
  12. **A second build tree would re-download everything.** `FetchContent` clones raylib, imgui, rlImGui and ten more into `<build>/_deps`, and the FFmpeg zip is an `ExternalProject` under `<build>/ThirdParty`. The `release` step passes `-DFETCHCONTENT_SOURCE_DIR_<NAME>=<developer tree>/_deps/<name>-src` for every source the developer tree already has (read-only use; build directories stay per tree). The FFmpeg zip is downloaded once more (about 90 MB, needs the network, once).
  13. **`dist-linux/` is not in `.gitignore`** (only `/dist/` is; `dist-linux/` exists only in the VM and CI). Task 4 adds `/dist-linux/`, `/dist-release/` and `/dist-linux-release/`. `/third_party/ps2recomp/build*/` already covers the new build trees.
  14. **The Linux CI job is already "the best part of an hour" against a 60-minute timeout** (`linux.yml:6-7`, `:21`). CI does not build the release configuration (R148).
  15. **Disk.** C: had 24 GB free. `build-clang` is 2.3 GB; `build-release` will be about the same, `dist-release` 0.3 GB, each measurement archive 60 MB. `run_detached.sh` refuses under `RUN_MIN_FREE_GB` (4).

- **`docs/KNOWN.md` has one writer: the controller.**

- **Autonomy (owner 2026-09-17, standing).** Proceed autonomously. **One host launch at a time**, always through `scripts/run_detached.sh`, and **suites are held while a host launch runs**: no `./build.sh test`, no `python -m unittest`, no build, no gate and no second launch while `logs/.quiet` exists (`bash scripts/check_quiet_gate.sh` answers).

- **Host load (owner, memory `host-load-sensitivity`).** A release build is every generated file at a higher `-O` level: tens of minutes of all cores. **Every release build runs detached through `scripts/run_detached.sh --owner build --purpose build …`, never while a game launch runs, and never while two other C++-building agents are running (at most two at once, spec §4).** When the owner is at the desk, heavy builds (M1, M2, M5 in Task 5) wait for a window the owner names; if one must run meanwhile, `REL_JOBS=14` (half the host's 28 threads). Poll the marker file, never the tool call.

- **Subagents (owner 2026-09-17).** Bounded mechanical work goes to Opus subagents with an exact brief and a verification command; judgment stays with the controller. Each task below is marked **[Opus]** (the code and tests are written out; the brief is "make this text work and these cases pass, change nothing else") or **[Judgment]** (needs a build, a gate, a measurement read, or a decision about what ships). A subagent never decides whether a bar is met, never writes `docs/KNOWN.md`, never commits, and never starts a launch or a release build.

- **Line numbers** are the numbers at `e8e60b8` (the branch tip when this was written). Before starting a task, `git diff e8e60b8 -- <the task's files>` and reconcile, saying so in the ledger. The working tree at that moment carried another task's uncommitted edits under `ps2xLauncher/`, `ps2xRuntime/src/lib/`, `ps2xShared/` and `ps2xTest/` (the crouch shortcut, R139); none of this plan's files overlap them.

- **Test baselines.** Goal 1 closed on its own totals; **record `P` (Python `Ran N tests`) and `B` (C++ `Total Tests:`) in the ledger before Task 1.** This goal adds Python cases only (`P + n` is stated per task); `B` must not move.

- **The launch budget.** Spec §4: "Goal 2 two extra" beyond the usual one. This goal commits nothing under `ps2xRuntime/src/`, so the usual one is the gate on the chosen release executable (`s9_g2_release_gate`, Task 5 Step 6). The two extras: one for the LTO candidate if its link survives the 30-minute rule (`s9_g2_lto_gate`, Task 5 Step 8), and one reserve — spent only to re-run a gate whose title stage fell on its known margin (19/23 against a bar of 19), or to gate the other `-O` level if the first choice fails (Task 5 Step 7). **Three gates at most; a fourth needs the owner.** The sub-second runs (`--home` for exit 68, `--diagnostics`, `--selftest`) open no window and are not launches, but they obey the quiet gate.

### The command set (use these verbatim)

```bash
# --- suites (Windows host, Git Bash, repo root) ---
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
python -m unittest tools_py.tests.<module> -v          # one Python module
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "<what>" -- ./build.sh test

# --- a release build (Task 5; the job script is written in Task 5 Step 1) ---
scripts/run_detached.sh --owner build --purpose build logs/s9_g2_build_release.sh logs/s9_g2_build_<label>.marker <label> <genopt> <lto> <scope> <icf> <cap s>
cat logs/s9_g2_build_<label>.marker 2>/dev/null || echo running     # poll the marker, never the tool call

# --- the three-stage gate on ANOTHER executable ---
scripts/run_detached.sh --owner gate --purpose launch logs/s9_g2_release_gate.sh logs/s9_g2_release_gate.marker
bash scripts/check_quiet_gate.sh                                    # answers whether a suite may run

# --- the numbers ---
python -m tools_py.release_metrics link third_party/ps2recomp/build-release ps2EntryRunner.exe
python -m tools_py.release_metrics speed logs/parity/gate/<stamp>/mission.game.log
python -m tools_py.release_metrics sizes dist-release/portable/socom2 dist-release/portable/socom2-portable.zip
python tools_py/portable_audit.py audit dist-release/portable/socom2

# --- Linux (the VM) ---
scripts/vm_sync.sh tree && scripts/vm_sync.sh ssh 'cd ~/socom_pc && bash scripts/build_linux.sh release'
```

`logs/s9_g2_release_gate.sh` (created in Task 5; `logs/` is git-ignored, so it is never committed). `logs/s9_g2_lto_gate.sh` is the same file with the stamp changed:

```bash
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:/c/Users/Utilisateur/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
export SOCOM_EXE=/c/projects/socom_pc/dist-release/socom2.exe
python -m tools_py.parity.gate --stamp s9_g2_release_gate --owner gate
rc=$?
echo "done $rc" > logs/s9_g2_release_gate.done
exit $rc
```

## Global Constraints

- Branch `sprint-9`, in the main checkout, never a worktree.
- **TDD, with RED watched.** Every step that adds behaviour names the case that fails before it and passes after, and the exact failure text; the implementer runs the RED and pastes its output into the ledger before writing the implementation. A step that cannot state a RED says so in one sentence and names what verifies it instead (there are three: Task 4's CMake switches, whose proof is `ninja: no work to do` in the developer tree and the flags in the release tree's `compile_commands.json`; Task 4's strip, whose proof is `llvm-nm`; and the measurements themselves).
- **Never `git add -A`, never `git add .`.** Every commit is `git add <paths>` for new files followed by `git commit -m "…" -- <paths>` with the explicit pathspec given in the task. **`server/config/simulated.db` is never staged** (it is modified in the working tree and stays that way). **`ONBOARDING.md` is never staged.** `vm/`, `dist/`, `dist-release/`, `logs/` are git-ignored and nothing under them is ever staged. The untracked `*.bin` / `*.wav` files in the repo root and in `third_party/ps2recomp/` are not this goal's and are never staged. Never stage a file another running agent is editing (memory: commit-only-idle-files) — in particular the crouch-shortcut files listed under "Line numbers" above.
- Commit trailer, every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Push after each commit.
- `./build.sh test` exit 0 on the Windows host before any commit touching `third_party/ps2recomp/`, `tools_py/` or `scripts/`. **The three-stage gate PASS (3/3) before any commit touching `third_party/ps2recomp/ps2xRuntime/src/`** — this goal has no such commit; if a task finds it needs one, stop and tell the controller.
- **No builds and no suites while a game launch runs** (`logs/.quiet`; `bash scripts/check_quiet_gate.sh`).
- **Windows and Linux both.** The Linux build is `scripts/build_linux.sh`; CI is `.github/workflows/linux.yml` (`--no-runner`: library, tests and launcher, no generated code). Every packaging change lands in **both branches of `scripts/make_portable.sh` in the same commit**, and every new CMake switch has its non-Windows half in the same edit.
- **The developer build does not move.** `./build.sh runtime`, `scripts/build_linux.sh runtime`, `third_party/ps2recomp/build-clang`, `build-linux`, `dist/`, `dist-linux/`, `run.sh` with no `SOCOM_EXE`, and the gate with no `SOCOM_EXE` behave exactly as at `e8e60b8`. Every new CMake switch defaults OFF/empty and is passed only by the `release` step.
- **No new `PS2X_*` environment variable** (Goal 3 is counting them). This goal's variables are the harness's and the build scripts': `SOCOM_EXE` (beside the existing `SOCOM_ISO`), `REL_GENOPT`, `REL_LTO`, `REL_LTO_SCOPE`, `REL_ICF`, `REL_JOBS`.
- **The stop rule is the spec's, verbatim:** "if LTO pushes the runner's link past 30 minutes or changes a gate score, ship without it and record why." R144 says how each half is read.
- LF line endings in every new file. **Python tests are `unittest`, never pytest**, live in `tools_py/tests/`, and have no module-level `def test_` (`tools_py/tests/test_test_hygiene.py`).

---

## File map

| Path | Responsibility |
|---|---|
| `tools_py/parity/hostplatform.py` (:30-38), `run.sh` (:12-13), `tools_py/parity/gate.py` (:614-675), `tools_py/tests/test_hostplatform.py`, `tools_py/tests/test_run_sh_exe.py` (new), `tools_py/tests/test_gate_exe_line.py` (new) | **Task 1 [Opus]**: `SOCOM_EXE` points the gate, the harness and the exit-code suite at another runner; the gate's summary says which one it scored |
| `tools_py/portable_audit.py` (new), `tools_py/tests/binfmt_fixtures.py` (new), `tools_py/tests/test_portable_audit.py` (new) | **Task 2 [Opus]**: import tables, the closure, the audit, `SHA256SUMS` — pure Python, both formats on both hosts |
| `scripts/make_portable.sh` (both branches), `tools_py/tests/test_make_portable.py`, `tools_py/tests/test_make_portable_linux.py` (new), `tools_py/tests/test_portable_folder.py` (new) | **Task 3 [Opus]**: the folder carries the closure and nothing else; `SHA256SUMS` beside each archive; `--release`; a Linux test that runs in CI |
| `third_party/ps2recomp/CMakeLists.txt` (:21), `third_party/ps2recomp/ps2xRuntime/cmake/ReleaseMode.cmake`, `build.sh`, `scripts/build_linux.sh`, `.gitignore` | **Task 4 [Judgment]**: the release configuration — three switches, its own tree, its own folder, stripped with symbols kept |
| `tools_py/release_metrics.py` (new), `tools_py/tests/test_release_metrics.py` (new), `logs/s9_g2_build_release.sh`, `logs/s9_g2_release_gate.sh`, `logs/s9_g2_lto_gate.sh` (new, ignored), this plan's Results table | **Task 5 [Judgment]**: the measurement matrix on Windows, the choice, the gate 3/3 on the release executable, LTO under the stop rule |
| the VM; this plan's Results table | **Task 6 [Judgment]**: the Linux ring — release build, `--as-needed`, tarball before/after, audit, exit codes on the release runner |
| `docs/KNOWN.md`, `docs/STATUS.md`, `docs/CURRENT_SPRINT.md`, `docs/HUMAN_TASKS.md`, this plan | **Task 7 [Judgment]**: close-out |

Tasks 1 and 2 are independent. Task 3 needs 2. Task 4 is independent of 1-3 (different files) but Task 5 needs all of 1-4. Task 6 needs 3 and 4. With at most two C++-building agents and no C++ compiled before Task 5, Tasks 1-4 can run two at a time if the controller merges `tools_py/tests/` additions.

---

## Task 1 — `SOCOM_EXE`: the gate can be pointed at another runner  **[Opus]**

**Files:**
- Modify: `tools_py/parity/hostplatform.py` (:30-38), `run.sh` (:12-13), `tools_py/parity/gate.py` (imports; a new function above `main`; `main` :648-672), `tools_py/tests/test_hostplatform.py`
- Create: `tools_py/tests/test_run_sh_exe.py`, `tools_py/tests/test_gate_exe_line.py`

**Interfaces:**
- `hostplatform.EXE_OVERRIDE_ENV = "SOCOM_EXE"`; `hostplatform.runtime_exe(system=None, env=None)` returns `env["SOCOM_EXE"]` when it is set (absolute, or relative to the repo root, returned as given), else today's value. A value whose file name is not `socom2.exe` (Windows) / `socom2` (Linux) raises `ValueError` — the harness finds and kills the game by that name (R141).
- `run.sh` starts `${SOCOM_EXE:-$ROOT/dist/socom2.exe}` and prints `exe=` on its summary line.
- `gate.exe_line(env=None) -> str`: `EXE <path> bytes=<n> sha256=<64 hex>` (or `EXE <path> UNREADABLE (<why>)`); printed when the gate starts and written as the **last** line of `summary.txt` (the stage lines stay first; nothing parses `summary.txt` today — `grep -rn summary.txt tools_py scripts` finds only other files' summaries).

**Steps:**

- [x] **Step 1: RED (`runtime_exe`).** Append to `tools_py/tests/test_hostplatform.py`, above its `if __name__` block:

```python
class RuntimeExeOverrideTest(unittest.TestCase):
    """Sprint 9 Goal 2: SOCOM_EXE names the runner the gate and the harness start (the release build lives
    in dist-release/, and the developer's dist/socom2.exe stays the default)."""

    def test_default_is_unchanged_with_an_empty_environment(self):
        self.assertEqual(hostplatform.runtime_exe("Windows", env={}), os.path.join("dist", "socom2.exe"))
        self.assertEqual(hostplatform.runtime_exe("Linux", env={}), os.path.join("dist-linux", "socom2"))

    def test_an_empty_value_is_not_an_override(self):
        self.assertEqual(hostplatform.runtime_exe("Windows", env={"SOCOM_EXE": ""}),
                         os.path.join("dist", "socom2.exe"))

    def test_the_override_is_returned_as_given(self):
        self.assertEqual(hostplatform.runtime_exe("Windows", env={"SOCOM_EXE": "C:/x/dist-release/socom2.exe"}),
                         "C:/x/dist-release/socom2.exe")
        self.assertEqual(hostplatform.runtime_exe("Windows", env={"SOCOM_EXE": "dist-release\\SOCOM2.EXE"}),
                         "dist-release\\SOCOM2.EXE")
        self.assertEqual(hostplatform.runtime_exe("Linux", env={"SOCOM_EXE": "dist-linux-release/socom2"}),
                         "dist-linux-release/socom2")

    def test_a_runner_under_another_name_is_refused(self):
        # process_running / kill_process_by_name look for "socom2": a runner called anything else would be
        # started and then never seen, never killed.
        with self.assertRaises(ValueError) as caught:
            hostplatform.runtime_exe("Windows", env={"SOCOM_EXE": "dist/socom2_release.exe"})
        self.assertIn("socom2.exe", str(caught.exception))
        with self.assertRaises(ValueError):
            hostplatform.runtime_exe("Linux", env={"SOCOM_EXE": "dist-linux-release/socom2.exe"})
```

(If the file does not already `import os`, add it.) Run `python -m unittest tools_py.tests.test_hostplatform -v`. Expected RED: four errors, each `TypeError: runtime_exe() got an unexpected keyword argument 'env'`.

- [x] **Step 2: GREEN.** In `tools_py/parity/hostplatform.py` replace `runtime_exe` (:30-38) with:

```python
EXE_OVERRIDE_ENV = "SOCOM_EXE"


def runtime_exe(system=None, env=None):
    """The game binary this host launches, relative to the repo root: the Windows build writes
    `dist/socom2.exe` and the Linux build `dist-linux/socom2` (Sprint 8 Task 1), and the two never
    overwrite each other -- so the gate's drive must ask which one it is looking at.

    Sprint 9 Goal 2: $SOCOM_EXE names another runner (the release build in dist-release/), absolute or
    relative to the repo root, returned as given. Its file name must still be socom2[.exe]: the
    harness finds and kills the game by that name (kill_argv, running_argv)."""
    env = os.environ if env is None else env
    override = env.get(EXE_OVERRIDE_ENV)
    if override:
        want = exe_name("socom2", system)
        got = override.replace("\\", "/").rsplit("/", 1)[-1]
        if got.lower() != want.lower():
            raise ValueError("%s=%s: the runner must be called %s (the harness finds and kills it by name); "
                             "put it in its own folder instead" % (EXE_OVERRIDE_ENV, override, want))
        return override
    if is_windows(system):
        return os.path.join("dist", "socom2.exe")
    return os.path.join("dist-linux", "socom2")
```

Run the module: `P + 4`, all pass.

- [x] **Step 3: RED (`run.sh`).** Create `tools_py/tests/test_run_sh_exe.py`:

```python
"""Sprint 9 Goal 2: run.sh starts $SOCOM_EXE when it is set. On Windows the gate's drive launches through
run.sh (drive.py), so this is the line that lets a gate score dist-release/socom2.exe. The fake runner is a
two-line shell script; the run takes well under a second. Side effect: run.sh repoints logs/latest.log."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@unittest.skipUnless(shutil.which("bash"), "bash only")
class RunShExeTest(unittest.TestCase):
    def test_socom_exe_names_the_binary_run_sh_starts(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "socom2")
            with open(fake, "w", newline="\n") as fh:
                fh.write("#!/usr/bin/env bash\necho \"fake-runner got $1\"\n")
            os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
            log = os.path.join(tmp, "run.log")
            env = {**os.environ, "SOCOM_EXE": fake.replace("\\", "/"), "PS2X_RUN_LOG": log.replace("\\", "/")}
            r = subprocess.run(["bash", os.path.join(ROOT, "run.sh"), "5"], capture_output=True, text=True,
                               cwd=ROOT, env=env, timeout=60)
            self.assertIn("exe=" + fake.replace("\\", "/"), r.stdout, r.stdout + r.stderr)
            with open(log) as fh:
                self.assertIn("fake-runner got ", fh.read())
            self.assertIn("socom2_game.elf", open(log).read())


if __name__ == "__main__":
    unittest.main()
```

Run it. Expected RED: `AssertionError: 'exe=…/socom2' not found in 'exit=… log=… lines=…'` (and, where `dist/socom2.exe` exists, run.sh starts the **real game** for 5 seconds — so run this RED only when `bash scripts/check_quiet_gate.sh` allows, and expect a window; after GREEN no window opens).

- [x] **Step 4: GREEN.** In `run.sh` replace lines 12-13 (`timeout "$SECS" "$ROOT/dist/socom2.exe" …` and the `echo "exit=$? …"` line) with:

```bash
# Sprint 9 Goal 2: SOCOM_EXE names another runner (the release build in dist-release/); the default is unchanged.
EXE="${SOCOM_EXE:-$ROOT/dist/socom2.exe}"
timeout "$SECS" "$EXE" "$ROOT/game/disc/socom2_game.elf" "$@" > "$LOG" 2>&1
echo "exit=$? log=$LOG exe=$EXE lines=$(wc -l < "$LOG")"
```

Also change the comment on line 2 to `# Run the recompiled game for N seconds and keep the log.  Usage: [SOCOM_EXE=<runner>] ./run.sh [seconds] [extra args]`. Run the test: passes.

- [x] **Step 5: RED (`exe_line`).** Create `tools_py/tests/test_gate_exe_line.py`:

```python
"""Sprint 9 Goal 2: a gate record says which executable it scored -- the release build is gated as itself."""
import hashlib
import os
import tempfile
import unittest

from tools_py.parity import gate


class GateExeLineTest(unittest.TestCase):
    def test_names_the_runner_its_size_and_its_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "socom2.exe" if os.name == "nt" else "socom2")
            with open(exe, "wb") as fh:
                fh.write(b"not really a runner")
            line = gate.exe_line(env={"SOCOM_EXE": exe})
            self.assertEqual(line, "EXE %s bytes=19 sha256=%s"
                             % (exe, hashlib.sha256(b"not really a runner").hexdigest()))

    def test_a_missing_runner_is_said_not_raised(self):
        name = "socom2.exe" if os.name == "nt" else "socom2"
        line = gate.exe_line(env={"SOCOM_EXE": os.path.join("no", "such", "folder", name)})
        self.assertTrue(line.startswith("EXE "), line)
        self.assertIn("UNREADABLE", line)


if __name__ == "__main__":
    unittest.main()
```

Expected RED: `AttributeError: module 'tools_py.parity.gate' has no attribute 'exe_line'`.

- [x] **Step 6: GREEN.** In `tools_py/parity/gate.py`: add `import hashlib` to the imports if it is not there; directly above `def main(argv=None):` add

```python
def exe_line(env=None):
    """Which runner this gate scores: path, size, SHA-256. Sprint 9 Goal 2 gates the release build through
    $SOCOM_EXE (hostplatform.runtime_exe), and a record that does not say which binary it ran proves nothing."""
    path = hostplatform.runtime_exe(env=env)
    full = path if os.path.isabs(path) else os.path.join(hostplatform.ROOT, path)
    try:
        digest = hashlib.sha256()
        with open(full, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return "EXE %s bytes=%d sha256=%s" % (path, os.path.getsize(full), digest.hexdigest())
    except OSError as e:
        return "EXE %s UNREADABLE (%s)" % (path, e.strerror or e)
```

and in `main`, immediately after the `if take.returncode != 0:` block (:651-654) add

```python
    exe = exe_line()
    print(exe, flush=True)
```

and change the summary write (:669-670) to

```python
        with open(os.path.join(out_root, "summary.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(line for _, line in results) + "\n" + exe + "\n")
```

Run `python -m unittest tools_py.tests.test_gate_exe_line tools_py.tests.test_hostplatform tools_py.tests.test_run_sh_exe -v`: all pass; Python total `P + 7`.

- [x] **Step 7: Suite and commit.** `./build.sh test` exit 0 (under the loop lock, quiet gate permitting).

```bash
git add tools_py/tests/test_run_sh_exe.py tools_py/tests/test_gate_exe_line.py
git commit -m "feat(harness): SOCOM_EXE points the gate, run.sh and the exit-code suite at another runner; the gate's summary names the executable it scored (Sprint 9 Goal 2 Task 1, R141)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  tools_py/parity/hostplatform.py tools_py/parity/gate.py run.sh \
  tools_py/tests/test_hostplatform.py tools_py/tests/test_run_sh_exe.py tools_py/tests/test_gate_exe_line.py
git push
```

---

## Task 2 — Import tables, the closure, the audit and `SHA256SUMS`, in pure Python  **[Opus]**

**Files:**
- Create: `tools_py/portable_audit.py`, `tools_py/tests/binfmt_fixtures.py`, `tools_py/tests/test_portable_audit.py`

**Interfaces** (`tools_py/portable_audit.py`):
- `pe_imports(path) -> [str]` — DLL names from the import directory and the delay-import directory of a PE32/PE32+ file; `ValueError` for anything else.
- `elf_needed(path) -> [str]` — `DT_NEEDED` names of a 64-bit little-endian ELF; `ValueError` for anything else; `[]` for a static binary.
- `is_windows_system(name) -> bool`; `is_linux_host(name) -> bool` (delegates to `scripts/portable_libs.py:is_host_library`, the one list of what the host provides).
- `closure(exes, folder, system) -> (needed, missing)` — `needed`: `{file name in the folder: who first imported it}`; `missing`: `{imported name: importer}` for names that are neither in the folder nor the operating system's.
- `audit(folder, system=None) -> {"needed": [...], "missing": {...}, "orphans": [...]}` — Windows: the folder's `socom2.exe` + `socom_unzipped_launcher.exe` against its `*.dll`; Linux: `socom2` + `socom_unzipped_launcher` against `lib/*`.
- `write_sha256sums(out_dir, names) -> path`; `verify_sha256sums(out_dir) -> [problem strings]`. Format: `<64 hex>  <name>\n` (what `sha256sum -c` reads), LF, sorted by name.
- CLI: `closure --dir <folder> <exe>...` (names, one per line, LF even on Windows; exit 3 and the missing names on stderr), `audit <folder> [--system Windows|Linux]` (exit 4 on any finding), `sha256sums <out dir> <name>...`, `verify <out dir>` (exit 5 on any problem).

**Steps:**

- [x] **Step 1: The fixtures.** Create `tools_py/tests/binfmt_fixtures.py` (a helper, not a test module — `online_rows.py` is the precedent):

```python
"""Sprint 9 Goal 2: the smallest PE and ELF files that carry an import list -- so the packaging tests can
build a fake dist/ whose executables really import what the test says, on any host, with no toolchain."""
import struct


def tiny_pe(imports):
    """A PE32+ image with one section holding an import directory that names `imports`. Not runnable."""
    table_len = 20 * (len(imports) + 1)
    names, offsets = b"", []
    for name in imports:
        offsets.append(table_len + len(names))
        names += name.encode("ascii") + b"\0"
    body = b"".join(struct.pack("<IIIII", 0, 0, 0, 0x1000 + off, 0) for off in offsets) + b"\0" * 20 + names
    dos = bytearray(64)
    dos[:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 64)
    coff = struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 240, 0x22)
    opt = bytearray(240)
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<I", opt, 108, 16)
    struct.pack_into("<II", opt, 112 + 8, 0x1000, table_len)
    section = b".idata\0\0" + struct.pack("<IIII", len(body), 0x1000, len(body), 0x200) + b"\0" * 16
    head = bytes(dos) + b"PE\0\0" + coff + bytes(opt) + section
    return head + b"\0" * (0x200 - len(head)) + body


def tiny_elf(needed):
    """A 64-bit little-endian ELF with a .dynstr and a .dynamic section naming `needed`. Not runnable."""
    strtab, offsets = b"\0", []
    for name in needed:
        offsets.append(len(strtab))
        strtab += name.encode("ascii") + b"\0"
    dynamic = b"".join(struct.pack("<qQ", 1, off) for off in offsets) + struct.pack("<qQ", 0, 0)
    str_off = 64
    dyn_off = str_off + len(strtab)
    sh_off = dyn_off + len(dynamic)

    def header(kind, offset, size, link=0):
        return struct.pack("<IIQQQQIIQQ", 0, kind, 0, 0, offset, size, link, 0, 1, 0)

    sections = header(0, 0, 0) + header(3, str_off, len(strtab)) + header(6, dyn_off, len(dynamic), link=1)
    ehdr = bytearray(64)
    ehdr[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHI", ehdr, 16, 3, 62, 1)
    struct.pack_into("<Q", ehdr, 0x28, sh_off)
    struct.pack_into("<HHHHHH", ehdr, 0x34, 64, 0, 0, 64, 3, 0)
    return bytes(ehdr) + strtab + dynamic + sections
```

- [x] **Step 2: RED.** Create `tools_py/tests/test_portable_audit.py`:

```python
"""Sprint 9 Goal 2: what the portable folder must carry is read from the import tables of the two shipped
executables, by a reader that needs no objdump and no ldd -- so the same audit runs on the Windows host,
in CI and in the VM, over either platform's folder."""
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

from tools_py import portable_audit
from tools_py.tests.binfmt_fixtures import tiny_elf, tiny_pe

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL_EXE = os.path.join(ROOT, "dist", "socom2.exe")


def put(folder, name, data):
    path = os.path.join(folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


class ImportReadersTest(unittest.TestCase):
    def test_pe_imports_in_table_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = put(tmp, "a.exe", tiny_pe(["KERNEL32.dll", "avcodec-61.dll", "libc++.dll"]))
            self.assertEqual(portable_audit.pe_imports(exe), ["KERNEL32.dll", "avcodec-61.dll", "libc++.dll"])
            self.assertEqual(portable_audit.pe_imports(put(tmp, "b.dll", tiny_pe([]))), [])

    def test_elf_needed_in_table_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            so = put(tmp, "socom2", tiny_elf(["libavcodec.so.60", "libc.so.6"]))
            self.assertEqual(portable_audit.elf_needed(so), ["libavcodec.so.60", "libc.so.6"])

    def test_anything_else_is_a_value_error_naming_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            junk = put(tmp, "junk.bin", b"x")
            for reader in (portable_audit.pe_imports, portable_audit.elf_needed):
                with self.assertRaises(ValueError) as caught:
                    reader(junk)
                self.assertIn("junk.bin", str(caught.exception))

    @unittest.skipUnless(os.path.isfile(REAL_EXE), "no dist/socom2.exe on this machine")
    def test_the_real_runner_imports_the_three_ffmpeg_libraries_it_calls(self):
        names = {n.lower() for n in portable_audit.pe_imports(REAL_EXE)}
        self.assertLessEqual({"avcodec-61.dll", "avutil-59.dll", "swscale-8.dll", "libc++.dll", "kernel32.dll"}, names)
        self.assertNotIn("avformat-61.dll", names)


class WindowsFolderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        put(self.dir, "socom2.exe", tiny_pe(["KERNEL32.dll", "api-ms-win-crt-heap-l1-1-0.dll", "AVCODEC-61.DLL"]))
        put(self.dir, "socom_unzipped_launcher.exe", tiny_pe(["USER32.dll", "libc++.dll"]))
        put(self.dir, "avcodec-61.dll", tiny_pe(["zlib1.dll", "bcrypt.dll"]))
        put(self.dir, "zlib1.dll", tiny_pe(["KERNEL32.dll"]))
        put(self.dir, "libc++.dll", tiny_pe([]))

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_closed_folder_has_no_findings(self):
        result = portable_audit.audit(self.dir, "Windows")
        self.assertEqual(result["needed"], ["avcodec-61.dll", "libc++.dll", "zlib1.dll"])
        self.assertEqual(result["missing"], {})
        self.assertEqual(result["orphans"], [])

    def test_a_dll_nothing_imports_is_an_orphan(self):
        put(self.dir, "OpenEXR-3_3.dll", tiny_pe(["KERNEL32.dll"]))
        put(self.dir, "avformat-61.dll", tiny_pe(["avcodec-61.dll"]))   # imports, but is imported by nothing
        self.assertEqual(portable_audit.audit(self.dir, "Windows")["orphans"], ["OpenEXR-3_3.dll", "avformat-61.dll"])

    def test_an_import_that_is_not_in_the_folder_is_missing_and_says_who_wanted_it(self):
        os.remove(os.path.join(self.dir, "zlib1.dll"))
        put(self.dir, "socom_unzipped_launcher.exe", tiny_pe(["USER32.dll", "libc++.dll", "VCRUNTIME140.dll"]))
        self.assertEqual(portable_audit.audit(self.dir, "Windows")["missing"],
                         {"zlib1.dll": "avcodec-61.dll", "VCRUNTIME140.dll": "socom_unzipped_launcher.exe"})

    def test_the_cli_prints_the_closure_with_lf_and_fails_on_a_missing_import(self):
        tool = os.path.join(ROOT, "tools_py", "portable_audit.py")
        exes = [os.path.join(self.dir, "socom2.exe"), os.path.join(self.dir, "socom_unzipped_launcher.exe")]
        r = subprocess.run([sys.executable, tool, "closure", "--dir", self.dir] + exes, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"avcodec-61.dll\nlibc++.dll\nzlib1.dll\n")
        os.remove(os.path.join(self.dir, "libc++.dll"))
        r = subprocess.run([sys.executable, tool, "closure", "--dir", self.dir] + exes, capture_output=True)
        self.assertEqual(r.returncode, 3)
        self.assertIn(b"libc++.dll", r.stderr)
        r = subprocess.run([sys.executable, tool, "audit", self.dir, "--system", "Windows"], capture_output=True)
        self.assertEqual(r.returncode, 4)


class LinuxFolderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        put(self.dir, "socom2", tiny_elf(["libavcodec.so.60", "libGL.so.1", "libc.so.6", "libstdc++.so.6"]))
        put(self.dir, "socom_unzipped_launcher", tiny_elf(["libc.so.6", "libX11.so.6"]))
        put(self.dir, "lib/libavcodec.so.60", tiny_elf(["libvpx.so.9", "libc.so.6"]))
        put(self.dir, "lib/libvpx.so.9", tiny_elf(["libc.so.6"]))

    def tearDown(self):
        self._tmp.cleanup()

    def test_host_libraries_are_neither_missing_nor_wanted_in_lib(self):
        result = portable_audit.audit(self.dir, "Linux")
        self.assertEqual(result, {"needed": ["libavcodec.so.60", "libvpx.so.9"], "missing": {}, "orphans": []})

    def test_a_library_nothing_needs_is_an_orphan_and_a_needed_one_gone_is_missing(self):
        put(self.dir, "lib/libavformat.so.60", tiny_elf(["libavcodec.so.60"]))
        os.remove(os.path.join(self.dir, "lib", "libvpx.so.9"))
        result = portable_audit.audit(self.dir, "Linux")
        self.assertEqual(result["orphans"], ["libavformat.so.60"])
        self.assertEqual(result["missing"], {"libvpx.so.9": "libavcodec.so.60"})


class Sha256SumsTest(unittest.TestCase):
    def test_written_in_sha256sum_format_and_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            put(tmp, "b.zip", b"bbb")
            put(tmp, "a.tar.gz", b"aaa")
            path = portable_audit.write_sha256sums(tmp, ["b.zip", "a.tar.gz"])
            self.assertEqual(os.path.basename(path), "SHA256SUMS")
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), ("%s  a.tar.gz\n%s  b.zip\n" % (
                    hashlib.sha256(b"aaa").hexdigest(), hashlib.sha256(b"bbb").hexdigest())).encode())
            self.assertEqual(portable_audit.verify_sha256sums(tmp), [])

    def test_a_changed_archive_a_missing_one_and_a_missing_file_are_each_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(portable_audit.verify_sha256sums(tmp), ["SHA256SUMS: not found"])
            put(tmp, "a.zip", b"aaa")
            put(tmp, "b.zip", b"bbb")
            portable_audit.write_sha256sums(tmp, ["a.zip", "b.zip"])
            put(tmp, "a.zip", b"aaX")
            os.remove(os.path.join(tmp, "b.zip"))
            self.assertEqual(portable_audit.verify_sha256sums(tmp), ["a.zip: checksum differs", "b.zip: not found"])


if __name__ == "__main__":
    unittest.main()
```

Run `python -m unittest tools_py.tests.test_portable_audit -v`. Expected RED: `ImportError: cannot import name 'portable_audit' from 'tools_py'`.

- [x] **Step 3: GREEN.** Create `tools_py/portable_audit.py`:

```python
#!/usr/bin/env python3
"""Sprint 9 Goal 2: what the portable folder carries is decided from import tables, and checked.

  closure  the local libraries the shipped executables reach -- scripts/make_portable.sh copies these
           and nothing else (it used to copy dist/*.dll: 31 files, of which the executables reach 16);
  audit    a finished folder: `missing` = imported, not in the folder, not the operating system's;
           `orphans` = carried, imported by nothing;
  sha256sums / verify   the SHA256SUMS file beside each archive.

Pure Python (struct): no objdump, no ldd -- so a Windows folder is audited in CI and a Linux one on the
host. The Linux "host provides it" list is scripts/portable_libs.py's, the one the tarball is built with.

  python tools_py/portable_audit.py closure --dir <folder> <exe>...
  python tools_py/portable_audit.py audit <folder> [--system Windows|Linux]
  python tools_py/portable_audit.py sha256sums <out dir> <archive name>...
  python tools_py/portable_audit.py verify <out dir>
"""
import argparse
import hashlib
import importlib.util
import os
import platform
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# What Windows itself provides, as imported today by the two executables and the sixteen DLLs they reach
# (llvm-objdump -p over dist/, 2026-09-19), plus the four FFmpeg's import libraries name. Anything else that
# is imported and absent -- VCRUNTIME140.dll is the classic -- is a finding, because a stranger's machine
# may not have it.
WINDOWS_SYSTEM = frozenset((
    "kernel32.dll", "user32.dll", "gdi32.dll", "shell32.dll", "winmm.dll", "ws2_32.dll", "comdlg32.dll",
    "ole32.dll", "bcrypt.dll", "advapi32.dll", "secur32.dll", "oleaut32.dll",
))
WINDOWS_SYSTEM_PREFIXES = ("api-ms-win-",)
SHIPPED = {"Windows": ("socom2.exe", "socom_unzipped_launcher.exe"), "Linux": ("socom2", "socom_unzipped_launcher")}
SUMS_NAME = "SHA256SUMS"


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _cstr(data, offset):
    return data[offset:data.index(b"\0", offset)].decode("ascii", "replace")


def pe_imports(path):
    """DLL names a PE32/PE32+ file imports: the import directory, then the delay-import directory."""
    data = _read(path)
    try:
        if data[:2] != b"MZ":
            raise ValueError("no MZ header")
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        if data[pe:pe + 4] != b"PE\0\0":
            raise ValueError("no PE signature")
        section_count, = struct.unpack_from("<H", data, pe + 6)
        optional_size, = struct.unpack_from("<H", data, pe + 20)
        optional = pe + 24
        magic, = struct.unpack_from("<H", data, optional)
        if magic not in (0x10B, 0x20B):
            raise ValueError("optional header magic 0x%x" % magic)
        directories = optional + (112 if magic == 0x20B else 96)
        directory_count, = struct.unpack_from("<I", data, directories - 4)
        sections = []
        for i in range(section_count):
            at = optional + optional_size + 40 * i
            sections.append(struct.unpack_from("<IIII", data, at + 8))   # vsize, vaddr, rawsize, rawptr

        def offset_of(rva):
            for vsize, vaddr, rawsize, rawptr in sections:
                if vaddr <= rva < vaddr + max(vsize, rawsize):
                    return rawptr + (rva - vaddr)
            raise ValueError("rva 0x%x is in no section" % rva)

        names = []
        for index, entry_size, name_at in ((1, 20, 12), (13, 32, 4)):
            if index >= directory_count:
                continue
            rva, _size = struct.unpack_from("<II", data, directories + 8 * index)
            if not rva:
                continue
            at = offset_of(rva)
            while at + entry_size <= len(data):
                name_rva, = struct.unpack_from("<I", data, at + name_at)
                if not name_rva:
                    break
                names.append(_cstr(data, offset_of(name_rva)))
                at += entry_size
        return names
    except (struct.error, ValueError) as e:
        raise ValueError("%s: not a PE file this reader understands (%s)" % (path, e))


def elf_needed(path):
    """DT_NEEDED names of a 64-bit little-endian ELF; [] when it has no dynamic section."""
    data = _read(path)
    try:
        if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
            raise ValueError("not a 64-bit little-endian ELF")
        section_table, = struct.unpack_from("<Q", data, 0x28)
        entry_size, count = struct.unpack_from("<HH", data, 0x3A)

        def section(i):
            _name, kind, _flags, _addr, offset, size, link = struct.unpack_from(
                "<IIQQQQI", data, section_table + i * entry_size)
            return kind, offset, size, link

        for i in range(count):
            kind, offset, size, link = section(i)
            if kind != 6:                      # SHT_DYNAMIC
                continue
            _kind, strings, _size, _link = section(link)
            names = []
            for at in range(offset, offset + size, 16):
                tag, value = struct.unpack_from("<qQ", data, at)
                if tag == 0:
                    break
                if tag == 1:                   # DT_NEEDED
                    names.append(_cstr(data, strings + value))
            return names
        return []
    except (struct.error, ValueError) as e:
        raise ValueError("%s: not an ELF file this reader understands (%s)" % (path, e))


def is_windows_system(name):
    lowered = name.lower()
    return lowered in WINDOWS_SYSTEM or lowered.startswith(WINDOWS_SYSTEM_PREFIXES)


_portable_libs = None


def is_linux_host(name):
    """scripts/portable_libs.py:is_host_library -- glibc, libstdc++, GL, X11, the sound servers."""
    global _portable_libs
    if _portable_libs is None:
        spec = importlib.util.spec_from_file_location("portable_libs", os.path.join(ROOT, "scripts", "portable_libs.py"))
        _portable_libs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_portable_libs)
    return _portable_libs.is_host_library(name)


def closure(exes, folder, system):
    """(needed, missing): needed = {file name in `folder`: first importer}, missing = {imported name: importer}
    for names that are neither in `folder` nor provided by the operating system. Windows matches names without
    regard to case, as its loader does."""
    windows = system == "Windows"
    imports, provided = (pe_imports, is_windows_system) if windows else (elf_needed, is_linux_host)
    fold = (lambda s: s.lower()) if windows else (lambda s: s)
    local = {fold(n): n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n))}
    needed, missing, todo = {}, {}, list(exes)
    while todo:
        path = todo.pop(0)
        importer = os.path.basename(path)
        for name in imports(path):
            if fold(name) in local:
                found = local[fold(name)]
                if found not in needed:
                    needed[found] = importer
                    todo.append(os.path.join(folder, found))
            elif not provided(name):
                missing.setdefault(name, importer)
    return needed, missing


def audit(folder, system=None):
    system = system or platform.system()
    windows = system == "Windows"
    libs = folder if windows else os.path.join(folder, "lib")
    exes = [os.path.join(folder, n) for n in SHIPPED["Windows" if windows else "Linux"]]
    needed, missing = closure(exes, libs, system) if os.path.isdir(libs) else ({}, {})
    if windows:
        carried = [n for n in os.listdir(folder) if n.lower().endswith(".dll")]
    else:
        carried = [n for n in os.listdir(libs)] if os.path.isdir(libs) else []
    return {"needed": sorted(needed), "missing": missing, "orphans": sorted(set(carried) - set(needed))}


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256sums(out_dir, names):
    path = os.path.join(out_dir, SUMS_NAME)
    with open(path, "w", newline="\n", encoding="ascii") as fh:
        for name in sorted(names):
            fh.write("%s  %s\n" % (_sha256(os.path.join(out_dir, name)), name))
    return path


def verify_sha256sums(out_dir):
    path = os.path.join(out_dir, SUMS_NAME)
    if not os.path.isfile(path):
        return [SUMS_NAME + ": not found"]
    problems = []
    with open(path, encoding="ascii") as fh:
        for line in fh.read().splitlines():
            want, _, name = line.partition("  ")
            target = os.path.join(out_dir, name)
            if not os.path.isfile(target):
                problems.append(name + ": not found")
            elif _sha256(target) != want:
                problems.append(name + ": checksum differs")
    return problems


def _out(lines):
    sys.stdout.buffer.write("".join(line + "\n" for line in lines).encode())   # LF on Windows too: bash reads this


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("closure")
    c.add_argument("--dir", required=True)
    c.add_argument("--system", choices=("Windows", "Linux"))
    c.add_argument("exes", nargs="+")
    a = sub.add_parser("audit")
    a.add_argument("folder")
    a.add_argument("--system", choices=("Windows", "Linux"))
    s = sub.add_parser("sha256sums")
    s.add_argument("out_dir")
    s.add_argument("names", nargs="+")
    v = sub.add_parser("verify")
    v.add_argument("out_dir")
    args = ap.parse_args(argv)
    if args.cmd == "closure":
        needed, missing = closure(args.exes, args.dir, args.system or platform.system())
        if missing:
            for name, importer in sorted(missing.items()):
                print("missing: %s (imported by %s)" % (name, importer), file=sys.stderr)
            return 3
        _out(sorted(needed))
        return 0
    if args.cmd == "audit":
        result = audit(args.folder, args.system)
        for name, importer in sorted(result["missing"].items()):
            print("missing: %s (imported by %s)" % (name, importer), file=sys.stderr)
        for name in result["orphans"]:
            print("orphan: %s (nothing imports it)" % name, file=sys.stderr)
        _out(["audit %s: %d needed, %d missing, %d orphans"
              % (args.folder, len(result["needed"]), len(result["missing"]), len(result["orphans"]))])
        return 4 if result["missing"] or result["orphans"] else 0
    if args.cmd == "sha256sums":
        _out([write_sha256sums(args.out_dir, args.names)])
        return 0
    problems = verify_sha256sums(args.out_dir)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 5 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
```

Run the module: 12 cases pass on the host (11 where there is no `dist/socom2.exe`); Python total `P + 7 + 12`.

- [x] **Step 4: The real folder, read by the new reader (no RED; this is the measurement the plan was written from, re-taken by the tool that will enforce it).** `python tools_py/portable_audit.py audit dist/portable/socom2 --system Windows`. Expected: exit 4, `0 missing`, and **15 orphans** — exactly `Iex-3_3.dll IlmThread-3_3.dll Imath-3_1.dll OpenEXR-3_3.dll OpenEXRCore-3_3.dll OpenEXRUtil-3_3.dll SDL2.dll avdevice-61.dll avfilter-10.dll avformat-61.dll freetype.dll harfbuzz.dll libwebpdecoder.dll libwebpdemux.dll libwinpthread-1.dll`. A different list means `dist/` changed since `e8e60b8`: paste it into the ledger and tell the controller before Task 3.

- [x] **Step 5: Suite and commit.**

```bash
git add tools_py/portable_audit.py tools_py/tests/binfmt_fixtures.py tools_py/tests/test_portable_audit.py
git commit -m "feat(packaging): portable_audit -- PE and ELF import readers, the import closure, the folder audit (missing / orphans) and SHA256SUMS, in pure Python (Sprint 9 Goal 2 Task 2)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  tools_py/portable_audit.py tools_py/tests/binfmt_fixtures.py tools_py/tests/test_portable_audit.py
git push
```

---

## Task 3 — The folder carries the closure and nothing else; `SHA256SUMS` beside each archive  **[Opus]**

**The DLL findings this task implements** (import tables of `dist/socom2.exe` and `dist/socom_unzipped_launcher.exe`, followed through every local DLL they reach; `llvm-objdump -p`, 2026-09-19; no delay-import directory in either executable; no `LoadLibrary`/`dlopen` in `ps2xRuntime/src`, `ps2xLauncher/src` or `ps2xShared/src`):

| | Files | Raw bytes | In the zip |
|---|---|---|---|
| **Needed — imported by an executable** | `avcodec-61` `avutil-59` `swscale-8` (runner); `libc++` `libunwind` (both) | | |
| **Needed — imported by a needed DLL** | `swresample-5` `zlib1` `jxl` `jxl_threads` `libwebp` `libwebpmux` (by `avcodec-61`); `jxl_cms` `brotlidec` `brotlienc` (by `jxl`); `brotlicommon` (by `brotlienc`); `libsharpyuv` (by `libwebp`) | 33,474,560 (16 files) | 14,097,831 |
| **Not needed — imported by nothing shipped** | `avformat-61` `avfilter-10` `avdevice-61` `SDL2` `freetype` `harfbuzz` `Iex-3_3` `IlmThread-3_3` `Imath-3_1` `OpenEXR-3_3` `OpenEXRCore-3_3` `OpenEXRUtil-3_3` `libwebpdecoder` `libwebpdemux` | 21,728,768 (14 files) | |
| **Not needed by the tables, copied by name on purpose** | `libwinpthread-1` (`build.sh:45`) — imported by no file in `dist/`, including llvm-mingw's own `libc++.dll` | 270,336 | 8,057,620 (all 15) |
| **Unsure** | none. The one residual doubt is a library loaded by name at run time; the tree has no such call, and the proof is Task 5's gate on a folder that carries only the sixteen plus `test_portable_folder`'s run with `PATH` cut to `System32` | | |

**Files:**
- Modify: `scripts/make_portable.sh` (header comment, a flag parser above the `case`, both branches), `tools_py/tests/test_make_portable.py` (rewritten)
- Create: `tools_py/tests/test_make_portable_linux.py`, `tools_py/tests/test_portable_folder.py`

**Interfaces:**
- `scripts/make_portable.sh [--release] [out dir]` — `--release` takes the binaries from `dist-release/` (Linux: `dist-linux-release/`) and defaults the output to `dist-release/portable` (`dist-linux-release/portable`). `DIST` / `LDIST` still override.
- Windows copies `portable_audit.py closure` instead of `*.dll`; both branches run `portable_audit.py audit` on the assembled folder (exit **4** on a finding) and write `SHA256SUMS` beside the archive. Exit 2 (no build) and 3 (an import that is nowhere) keep their meanings.

**Steps:**

- [x] **Step 1: RED (Windows).** Replace `tools_py/tests/test_make_portable.py` with:

```python
"""Task 8b Step 5: scripts/make_portable.sh assembles the portable folder (outline section 2 A) from dist/.
Sprint 9 Goal 2: the folder carries the import closure of the two executables and nothing else, and a
SHA256SUMS sits beside the archive."""
import os
import shutil
import subprocess
import tempfile
import unittest

from tools_py import portable_audit
from tools_py.tests.binfmt_fixtures import tiny_pe

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "make_portable.sh")

FAKE_DIST = {
    "socom2.exe": tiny_pe(["KERNEL32.dll", "avcodec-61.dll", "libc++.dll"]),
    "socom_unzipped_launcher.exe": tiny_pe(["USER32.dll", "libc++.dll"]),
    "avcodec-61.dll": tiny_pe(["zlib1.dll", "KERNEL32.dll"]),
    "zlib1.dll": tiny_pe(["KERNEL32.dll"]),
    "libc++.dll": tiny_pe([]),
    "avformat-61.dll": tiny_pe(["avcodec-61.dll"]),      # in dist/, imported by nothing shipped
    "OpenEXR-3_3.dll": tiny_pe(["KERNEL32.dll"]),        # likewise
    "vu1_replay.exe": tiny_pe(["libc++.dll"]),           # a harness tool: never shipped
    "socom2_game.elf": b"x",
}


def fake_dist(tmp, without=()):
    dist = os.path.join(tmp, "dist")
    os.makedirs(dist)
    for name, data in FAKE_DIST.items():
        if name not in without:
            with open(os.path.join(dist, name), "wb") as fh:
                fh.write(data)
    return dist


@unittest.skipUnless(shutil.which("bash") and shutil.which("powershell"), "bash and PowerShell only")
class MakePortableTest(unittest.TestCase):
    def _run(self, dist, *args):
        return subprocess.run(["bash", SCRIPT] + list(args), capture_output=True, text=True, cwd=ROOT,
                              env={**os.environ, "DIST": dist})

    def test_folder_has_the_game_the_launcher_the_closure_the_readme_and_the_licences(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            r = self._run(fake_dist(tmp), out)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            pkg = os.path.join(out, "socom2")
            for f in ("socom2.exe", "socom2_game.elf", "socom_unzipped_launcher.exe", "avcodec-61.dll", "zlib1.dll",
                      "libc++.dll", "README.txt", os.path.join("LICENSES", "PS2Recomp-GPL-3.0.txt"),
                      os.path.join("LICENSES", "README.txt")):
                self.assertTrue(os.path.isfile(os.path.join(pkg, f)), f)
            for d in ("cards", "logs"):
                self.assertTrue(os.path.isdir(os.path.join(pkg, d)), d)
            self.assertIn("Run socom_unzipped_launcher.exe", open(os.path.join(pkg, "README.txt")).read())
            # Sprint 9 Goal 1: the About page and the diagnostics zip read version.txt; nothing wrote it before.
            with open(os.path.join(pkg, "version.txt")) as fh:
                self.assertRegex(fh.read(), "^SOCOM Unzipped \\S+ \\(\\d{4}-\\d{2}-\\d{2}\\)\\n$")
            self.assertTrue(os.path.isfile(os.path.join(out, "socom2-portable.zip")))

    def test_what_nothing_imports_stays_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            self.assertEqual(self._run(fake_dist(tmp), out).returncode, 0)
            pkg = os.path.join(out, "socom2")
            for f in ("avformat-61.dll", "OpenEXR-3_3.dll", "vu1_replay.exe"):
                self.assertFalse(os.path.exists(os.path.join(pkg, f)), f)
            self.assertEqual(portable_audit.audit(pkg, "Windows"),
                             {"needed": ["avcodec-61.dll", "libc++.dll", "zlib1.dll"], "missing": {}, "orphans": []})

    def test_sha256sums_sits_beside_the_zip_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            self.assertEqual(self._run(fake_dist(tmp), out).returncode, 0)
            with open(os.path.join(out, "SHA256SUMS")) as fh:
                self.assertRegex(fh.read(), "^[0-9a-f]{64}  socom2-portable\\.zip\\n$")
            self.assertEqual(portable_audit.verify_sha256sums(out), [])
            with open(os.path.join(out, "socom2-portable.zip"), "ab") as fh:
                fh.write(b"tampered")
            self.assertEqual(portable_audit.verify_sha256sums(out), ["socom2-portable.zip: checksum differs"])

    def test_an_import_that_is_nowhere_stops_the_packaging(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self._run(fake_dist(tmp, without=("zlib1.dll",)), os.path.join(tmp, "out"))
            self.assertEqual(r.returncode, 3, r.stderr + r.stdout)
            self.assertIn("zlib1.dll", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(tmp, "out", "socom2-portable.zip")))

    def test_release_flag_is_accepted_in_front_of_the_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            r = self._run(fake_dist(tmp), "--release", out)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertTrue(os.path.isfile(os.path.join(out, "socom2-portable.zip")))

    def test_refuses_without_a_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self._run(os.path.join(tmp, "nodist"), os.path.join(tmp, "out"))
            self.assertEqual(r.returncode, 2)
            self.assertIn("run ./build.sh runtime first", r.stderr)


if __name__ == "__main__":
    unittest.main()
```

Run it. Expected RED against today's script: `test_what_nothing_imports_stays_behind` fails on `avformat-61.dll` (the script copies `*.dll`); `test_sha256sums…` fails with `FileNotFoundError … SHA256SUMS`; `test_an_import_that_is_nowhere…` fails `0 != 3`; `test_release_flag…` fails because `--release` is taken as the output directory (`out/socom2-portable.zip` absent). The first and last cases pass.

- [x] **Step 2: GREEN (the flag, and the Windows branch).** In `scripts/make_portable.sh`:

  (a) Replace the usage comment's line `#   scripts/make_portable.sh [out dir]      (default: dist/portable, dist-linux/portable on Linux)` with

```bash
#   scripts/make_portable.sh [--release] [out dir]   (default: dist/portable, dist-linux/portable on Linux;
#                                                     --release: dist-release/portable, dist-linux-release/portable)
# Sprint 9 Goal 2: the folder carries the import closure of socom2 and the launcher and nothing else
# (tools_py/portable_audit.py: closure, then an audit of what was assembled -- exit 4 on a finding), and
# SHA256SUMS is written beside the archive. Exit 2 = no build, 3 = an imported library is nowhere.
```

  (b) Directly after `ROOT="$(cd "$(dirname "$0")/.." && pwd)"` add

```bash
SUFFIX=""
if [ "${1:-}" = "--release" ]; then SUFFIX="-release"; shift; fi
AUDIT="$ROOT/tools_py/portable_audit.py"
```

  (c) In the Windows branch replace `DIST="${DIST:-$ROOT/dist}"` / `OUT="${1:-$ROOT/dist/portable}"` with

```bash
DIST="${DIST:-$ROOT/dist$SUFFIX}"
OUT="${1:-$ROOT/dist$SUFFIX/portable}"
PY="${PYTHON:-python}"
```

  and change the missing-build message to name the right step: `echo "make_portable: $DIST/$f missing -- run ./build.sh runtime first${SUFFIX:+ (or ./build.sh release)}" >&2`.

  (d) Replace `cp "$DIST"/*.dll "$PKG/"` with

```bash
# Sprint 9 Goal 2: only what the two executables reach through their import tables (16 of dist/'s 31 DLLs on
# 2026-09-19 -- the rest is the FFmpeg zip's whole bin/ and a libwinpthread nothing imports).
if NEEDED="$("$PY" "$AUDIT" closure --system Windows --dir "$DIST" "$DIST/socom2.exe" "$DIST/socom_unzipped_launcher.exe")"; then
  :
else
  echo "make_portable: an imported library is neither in $DIST nor part of Windows (see above)" >&2
  exit 3
fi
printf '%s\n' "$NEEDED" | tr -d '\r' | while read -r dll; do
  [ -n "$dll" ] || continue
  cp "$DIST/$dll" "$PKG/"
done
```

  (e) Replace the two lines that zip and report (`( cd "$OUT" && rm -f socom2-portable.zip && powershell … )` and the `echo "portable folder: …"`) with

```bash
"$PY" "$AUDIT" audit "$PKG" --system Windows || { echo "make_portable: the assembled folder failed its audit" >&2; exit 4; }
( cd "$OUT" && rm -f socom2-portable.zip SHA256SUMS && powershell -NoProfile -Command "Compress-Archive -Path 'socom2' -DestinationPath 'socom2-portable.zip' -Force" )
"$PY" "$AUDIT" sha256sums "$OUT" socom2-portable.zip >/dev/null
echo "portable folder: $PKG ($(ls "$PKG" | wc -l) entries), zip: $OUT/socom2-portable.zip ($(wc -c < "$OUT/socom2-portable.zip") bytes), $OUT/SHA256SUMS"
```

  Keep the column-0 here-doc terminators exactly where they are. Run the module on the host: 6 pass.

- [x] **Step 3: RED (Linux, in CI).** Create `tools_py/tests/test_make_portable_linux.py`:

```python
"""Sprint 9 Goal 2: the Linux branch of scripts/make_portable.sh, run for real. test_make_portable.py needs
PowerShell and has never run on Linux, so until now nothing checked this branch's version.txt (Goal 1, R138)
or anything else about it. CI builds the launcher and no runner; the launcher stands in for both binaries
(the script asks only that the three files exist), which is enough for ldd, lib/, the tarball, version.txt,
SHA256SUMS and the audit to be exercised on ubuntu-24.04."""
import hashlib
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from tools_py import portable_audit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "make_portable.sh")
LAUNCHER = os.path.join(ROOT, "dist-linux", "socom_unzipped_launcher")


@unittest.skipUnless(platform.system() == "Linux" and os.path.isfile(LAUNCHER) and shutil.which("ldd")
                     and shutil.which("bash"), "Linux with a built launcher (dist-linux/) only")
class MakePortableLinuxTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = self._tmp.name
        self.ldist = os.path.join(tmp, "ldist")
        os.makedirs(self.ldist)
        shutil.copy2(LAUNCHER, os.path.join(self.ldist, "socom_unzipped_launcher"))
        shutil.copy2(LAUNCHER, os.path.join(self.ldist, "socom2"))
        with open(os.path.join(self.ldist, "socom2_game.elf"), "wb") as fh:
            fh.write(b"x")
        self.out = os.path.join(tmp, "out")
        self.result = subprocess.run(["bash", SCRIPT, self.out], capture_output=True, text=True, cwd=ROOT,
                                     env={**os.environ, "LDIST": self.ldist, "DIST": os.path.join(tmp, "nodist")})
        self.pkg = os.path.join(self.out, "socom2-linux")
        self.tarball = os.path.join(self.out, "socom2-linux.tar.gz")

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_tarball_unpacks_runnable_with_a_version(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr + self.result.stdout)
        with open(os.path.join(self.pkg, "version.txt")) as fh:
            self.assertRegex(fh.read(), "^SOCOM Unzipped \\S+ \\(\\d{4}-\\d{2}-\\d{2}\\)\\n$")
        with tarfile.open(self.tarball) as tar:
            names = tar.getnames()
            self.assertIn("socom2-linux/version.txt", names)
            self.assertTrue(tar.getmember("socom2-linux/socom2").mode & 0o100, "socom2 lost its executable bit")

    def test_sha256sums_sits_beside_the_tarball_and_verifies(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr + self.result.stdout)
        with open(self.tarball, "rb") as fh:
            want = hashlib.sha256(fh.read()).hexdigest()
        with open(os.path.join(self.out, "SHA256SUMS")) as fh:
            self.assertEqual(fh.read(), "%s  socom2-linux.tar.gz\n" % want)
        self.assertEqual(portable_audit.verify_sha256sums(self.out), [])
        if shutil.which("sha256sum"):
            check = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=self.out, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_lib_holds_what_the_binaries_need_and_nothing_else(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr + self.result.stdout)
        found = portable_audit.audit(self.pkg, "Linux")
        self.assertEqual((found["missing"], found["orphans"]), ({}, []))
        shutil.copy2(LAUNCHER, os.path.join(self.pkg, "lib", "libnothing_needs_me.so.1"))
        self.assertEqual(portable_audit.audit(self.pkg, "Linux")["orphans"], ["libnothing_needs_me.so.1"])


if __name__ == "__main__":
    unittest.main()
```

  RED is watched **in the VM or in CI**, not on the Windows host (where the class is skipped): before Step 4, `test_sha256sums…` fails with `FileNotFoundError: …/SHA256SUMS`; the other two pass (R138's `version.txt` is already written, and today's `lib/` is whatever `ldd` says, which is closed by construction).

- [x] **Step 4: GREEN (the Linux branch).** In `scripts/make_portable.sh`'s `Linux)` branch: replace `LDIST="${LDIST:-$ROOT/dist-linux}"` with `LDIST="${LDIST:-$ROOT/dist-linux$SUFFIX}"`; change the missing-build message to `… run scripts/build_linux.sh first${SUFFIX:+ (or scripts/build_linux.sh release)}`; and replace the last three lines of the branch (`rm -f "$OUT/socom2-linux.tar.gz"`, `tar …`, `echo …`) with

```bash
    python3 "$AUDIT" audit "$PKG" --system Linux || { echo "make_portable: the assembled folder failed its audit" >&2; exit 4; }
    rm -f "$OUT/socom2-linux.tar.gz" "$OUT/SHA256SUMS"
    tar -C "$OUT" -czf "$OUT/socom2-linux.tar.gz" socom2-linux
    python3 "$AUDIT" sha256sums "$OUT" socom2-linux.tar.gz >/dev/null
    echo "portable folder: $PKG ($(ls "$PKG" | wc -l) entries, $NLIBS libraries in lib/), tarball: $OUT/socom2-linux.tar.gz ($(wc -c < "$OUT/socom2-linux.tar.gz") bytes), $OUT/SHA256SUMS"
```

- [x] **Step 5: RED then GREEN (the real folders on this machine).** Create `tools_py/tests/test_portable_folder.py`:

```python
"""Sprint 9 Goal 2: every portable folder that exists on this machine is closed -- the shipped executables
import nothing the folder lacks, and the folder carries nothing they do not import -- and the Windows runner
loads with nothing on PATH but System32 (run.sh puts tools/llvm-mingw/bin on PATH, so a gate cannot show that a
folder is complete). The run is `socom2 --home <empty dir>`: the loader resolves every static import before
main(), the preflight finds no ELF and leaves with 68 before a window opens."""
import os
import subprocess
import tempfile
import unittest

from tools_py import exit_codes, portable_audit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FOLDERS = [
    ("Windows", os.path.join(ROOT, "dist", "portable", "socom2")),
    ("Windows", os.path.join(ROOT, "dist-release", "portable", "socom2")),
    ("Linux", os.path.join(ROOT, "dist-linux", "portable", "socom2-linux")),
    ("Linux", os.path.join(ROOT, "dist-linux-release", "portable", "socom2-linux")),
]


class RealPortableFoldersTest(unittest.TestCase):
    def test_every_portable_folder_on_this_machine_is_closed(self):
        present = [(system, folder) for system, folder in FOLDERS if os.path.isdir(folder)]
        if not present:
            self.skipTest("no portable folder on this machine (scripts/make_portable.sh writes one)")
        for system, folder in present:
            with self.subTest(folder=folder):
                found = portable_audit.audit(folder, system)
                self.assertEqual(found["missing"], {}, "imported, and not in the folder")
                self.assertEqual(found["orphans"], [], "in the folder, and imported by nothing")

    @unittest.skipUnless(os.name == "nt", "Windows loader only")
    def test_the_windows_runner_and_launcher_load_with_only_system32_on_path(self):
        present = [folder for system, folder in FOLDERS if system == "Windows" and os.path.isdir(folder)]
        if not present:
            self.skipTest("no Windows portable folder on this machine")
        system_root = os.environ.get("SystemRoot", "C:\\Windows")
        for folder in present:
            with self.subTest(folder=folder), tempfile.TemporaryDirectory() as tmp:
                env = {"SystemRoot": system_root, "PATH": os.path.join(system_root, "System32"),
                       "TEMP": tmp, "TMP": tmp, "USERPROFILE": tmp}
                home = os.path.join(tmp, "home")
                os.makedirs(home)
                r = subprocess.run([os.path.join(folder, "socom2.exe"), "--home", home], env=env, cwd=home,
                                   capture_output=True, timeout=60)
                self.assertEqual(exit_codes.classify(r.returncode), exit_codes.code("ElfMissing"), r.stderr[-400:])
                out = os.path.join(tmp, "d.zip")
                r = subprocess.run([os.path.join(folder, "socom_unzipped_launcher.exe"), "--diagnostics", out, home],
                                   env=env, cwd=home, capture_output=True, timeout=60)
                self.assertEqual(r.returncode, 0, r.stderr[-400:])


if __name__ == "__main__":
    unittest.main()
```

  RED on the host: `dist/portable/socom2` is the 2026-09-17 folder, so the first case fails listing the fifteen orphans of Task 2 Step 4 (`AssertionError: Lists differ: ['Iex-3_3.dll', …] != []`). The second case is expected to **pass** even now (a loader failure here — `0xC0000135`, which `classify` does not fold onto 68 — would be a finding about today's folder: stop and tell the controller). GREEN: `bash scripts/make_portable.sh` (quiet gate permitting; it needs `dist/` built at HEAD, which it is), then the module passes both cases, and the script's own line reads `16 needed, 0 missing, 0 orphans`.

- [x] **Step 6: Record the first "after".** `python -m tools_py.release_metrics` does not exist yet; use `wc -c < dist/portable/socom2-portable.zip` and `du -sb dist/portable/socom2`. Write both into this plan's Results table, row **P1** (before: 65,494,194 / 297,839,981; expected after: about 57.4 MB / 275.8 MB). The developer executable is the same file, so this row isolates the DLL change.

- [x] **Step 7: Suite and commit.** `./build.sh test` exit 0; Python total `P + 7 + 12 + 6` on the host (`test_make_portable` 2 -> 6 is +4, `test_portable_folder` +2), and `+3` more where Linux has a launcher.

```bash
git add tools_py/tests/test_make_portable_linux.py tools_py/tests/test_portable_folder.py
git commit -m "feat(packaging): the portable folder carries the import closure and nothing else (15 DLLs stay behind), is audited as assembled, and gets SHA256SUMS beside the archive -- both branches; --release; a Linux packaging test that runs in CI (Sprint 9 Goal 2 Task 3, R145, R147, R150)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  scripts/make_portable.sh tools_py/tests/test_make_portable.py \
  tools_py/tests/test_make_portable_linux.py tools_py/tests/test_portable_folder.py
git push
```

- [ ] **Step 8: CI.** On that commit the `linux` workflow's test log (`linux-test-output` artefact) shows `test_the_tarball_unpacks_runnable_with_a_version … ok`, `test_sha256sums_sits_beside_the_tarball_and_verifies … ok`, `test_lib_holds_what_the_binaries_need_and_nothing_else … ok`. **A skip of these three in CI is a failure of this step** — it means `LAUNCHER`'s path is wrong there.

  *Open (2026-09-19): the Task 3 commit was made but not pushed (the dispatch forbade pushing), so no CI run exists yet. Check this step on the first push of `sprint-9`; the VM was off and must not be started, so the Linux RED was not watched there either — the three cases skip on the Windows host.*

---

## Task 4 — The release configuration: three switches, its own tree, its own folder  **[Judgment]**

**Files:**
- Modify: `third_party/ps2recomp/CMakeLists.txt` (after the option block, :21), `third_party/ps2recomp/ps2xRuntime/cmake/ReleaseMode.cmake` (:5, :39), `build.sh` (:3, :11-12, a new function after `runtime()`, the `case`), `scripts/build_linux.sh` (usage, variables, a new function, the argument loop, the `case`), `.gitignore`

**Interfaces:**
- CMake, all defaulting to today's behaviour: `PS2X_RELEASE_LINK` (BOOL, OFF) — `-ffunction-sections -fdata-sections` on everything compiled in the tree (raylib included), `-Wl,--gc-sections` on every link, `-Wl,--as-needed` on ELF targets; `PS2X_LINK_ICF` (STRING, empty; `safe` or `all`) — `-Wl,--icf=<value>`, with `-fuse-ld=lld` on ELF targets because GNU ld has no ICF; `PS2X_LTO_SCOPE` (STRING, `all`; or `runtime`) — with `runtime`, `EnableFastReleaseMode` skips IPO for `ps2EntryRunner`, so the generated code is compiled to native objects and only `ps2_runtime` takes part in ThinLTO.
- `./build.sh release` and `scripts/build_linux.sh release [--no-runner]`: configure `build-release` / `build-linux-release`, build the runner and the launcher, write `dist-release/` / `dist-linux-release/` = the two executables **stripped**, the game ELF, the import closure (Windows), and `symbols/<name>.debug` + `symbols/INDEX.txt`. Read from the environment: `REL_GENOPT` (default `-O2`), `REL_LTO` (`OFF`), `REL_LTO_SCOPE` (`all`), `REL_ICF` (empty), `REL_JOBS` (`nproc`). Task 5 moves the defaults to what it measured.

**Steps:**

- [ ] **Step 1: The switches.** In `third_party/ps2recomp/CMakeLists.txt`, directly after `option(PS2X_BUILD_STUDIO "Build ps2xStudio" ON)` add:

```cmake
# Sprint 9 Goal 2: the release configuration's link hygiene. OFF in the developer build (build.sh runtime,
# scripts/build_linux.sh runtime), which must not change; ON only from `build.sh release` /
# `scripts/build_linux.sh release`, in their own build trees. Declared here, before any add_subdirectory,
# so raylib and every library in the tree are compiled into sections too.
option(PS2X_RELEASE_LINK "Release link hygiene: function/data sections, --gc-sections, --as-needed on ELF" OFF)
set(PS2X_LINK_ICF "" CACHE STRING "Identical-code folding at link: empty (off), safe or all")
if(PS2X_RELEASE_LINK AND NOT MSVC)
    add_compile_options(-ffunction-sections -fdata-sections)
    add_link_options(-Wl,--gc-sections)
    if(UNIX AND NOT APPLE)
        # Link only what is called: the runner names libavformat and libswresample (pkg_check_modules) and
        # calls neither, and without this both become DT_NEEDED and drag their closure into the tarball's lib/.
        add_link_options(-Wl,--as-needed)
    endif()
endif()
if(PS2X_LINK_ICF AND NOT MSVC)
    if(UNIX AND NOT APPLE)
        add_link_options(-fuse-ld=lld)      # GNU ld has no --icf
    endif()
    add_link_options(-Wl,--icf=${PS2X_LINK_ICF})
endif()
```

  In `ps2xRuntime/cmake/ReleaseMode.cmake`, after the `option(PS2X_ENABLE_LTO …)` line add

```cmake
set(PS2X_LTO_SCOPE "all" CACHE STRING "all: LTO every target EnableFastReleaseMode names; runtime: leave ps2EntryRunner (the generated code) out")
```

  and replace `if(IPO_SUPPORTED AND PS2X_ENABLE_LTO)` … `elseif(NOT PS2X_ENABLE_LTO)` with

```cmake
    if(PS2X_ENABLE_LTO AND PS2X_LTO_SCOPE STREQUAL "runtime" AND TargetName STREQUAL "ps2EntryRunner")
        message("> LTO skipped for ${TargetName} (PS2X_LTO_SCOPE=runtime: the generated code stays native objects)")
    elseif(IPO_SUPPORTED AND PS2X_ENABLE_LTO)
        set_property(TARGET ${TargetName} PROPERTY INTERPROCEDURAL_OPTIMIZATION_RELEASE TRUE)
    elseif(NOT PS2X_ENABLE_LTO)
```

  (the rest of the `if` chain is unchanged).

- [ ] **Step 2: Prove the developer tree did not move (this step's verification; there is no RED for a switch that is off).** Quiet gate permitting, and with no other agent building in `build-clang`:

```bash
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake -S third_party/ps2recomp -B third_party/ps2recomp/build-clang >/dev/null    # re-reads the edited lists; cache values kept
cmake --build third_party/ps2recomp/build-clang --target ps2EntryRunner socom_unzipped_launcher ps2x_tests -- -n | tail -3
```

  Expected last line: `ninja: no work to do.` If ninja lists compile edges, a flag reached the developer build: stop, read `build.ninja`'s diff, fix the `if()`. Paste the line into the ledger. (If another agent left `build-clang` with genuinely stale objects, `-n` lists those; tell them apart by running the same `-n` on a stash of Step 1 first.)

- [ ] **Step 3: `build.sh release`.** In `build.sh`: change line 3 to `# Usage: ./build.sh [tools|recomp|runtime|release|test|all]   (default all; release is never part of all)`; after `RTBUILD=…` add

```bash
RELBUILD="$PS2R/build-release"     # Sprint 9 Goal 2: the release configuration -- its own tree, never the developer's
RELDIST="$ROOT/dist-release"       # ... and its own folder; dist/socom2.exe stays the gate's and the harness's default
```

  after the `runtime()` function add

```bash
# Sprint 9 Goal 2. The same sources and the same Release build type as runtime(); what differs is the generated
# code's -O level, the link hygiene (PS2X_RELEASE_LINK), optionally ICF and ThinLTO, and that the two executables
# are stripped with their symbols kept beside them. Every value is an environment variable so the measurement
# matrix (the Goal 2 plan, Task 5) builds each candidate with this one function.
release() {
  local genopt="${REL_GENOPT:--O2}" lto="${REL_LTO:-OFF}" scope="${REL_LTO_SCOPE:-all}" icf="${REL_ICF:-}"
  local fc=() src name
  # Reuse the developer tree's fetched sources read-only (raylib, imgui, ...): a second tree would clone them all again.
  for src in "$RTBUILD"/_deps/*-src; do
    [ -d "$src" ] || continue
    name="$(basename "$src")"; name="${name%-src}"
    fc+=("-DFETCHCONTENT_SOURCE_DIR_$(printf '%s' "$name" | tr 'a-z' 'A-Z')=$src")
  done
  cmake -S "$PS2R" -B "$RELBUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
        -DPS2X_RUNNER_GENERATED_DIR="$GEN" -DPS2X_GENERATED_OPT="$genopt" \
        -DPS2X_ENABLE_LTO="$lto" -DPS2X_LTO_SCOPE="$scope" \
        -DPS2X_RELEASE_LINK=ON -DPS2X_LINK_ICF="$icf" ${fc[@]+"${fc[@]}"} >/dev/null
  cmake --build "$RELBUILD" --target ps2EntryRunner socom_unzipped_launcher -j "${REL_JOBS:-$(nproc)}"
  local stage="$RELDIST/.stage" tag
  tag="$(git -C "$ROOT" describe --always --dirty 2>/dev/null || echo unknown)"
  rm -rf "$stage"; mkdir -p "$stage" "$RELDIST/symbols"
  cp "$RELBUILD/ps2xRuntime/ps2EntryRunner.exe" "$stage/socom2.exe"
  cp "$RELBUILD/ps2xLauncher/socom_unzipped_launcher.exe" "$stage/"
  cp "$RELBUILD/ps2xRuntime/"*.dll "$stage/" 2>/dev/null || true
  for d in libc++.dll libunwind.dll libwinpthread-1.dll; do
    [ -f "$ROOT/tools/llvm-mingw/bin/$d" ] && cp "$ROOT/tools/llvm-mingw/bin/$d" "$stage/"
  done
  rm -f "$RELDIST"/*.dll
  python "$ROOT/tools_py/portable_audit.py" closure --system Windows --dir "$stage" \
      "$stage/socom2.exe" "$stage/socom_unzipped_launcher.exe" | tr -d '\r' | while read -r dll; do
    [ -n "$dll" ] && cp "$stage/$dll" "$RELDIST/"
  done
  for exe in socom2.exe socom_unzipped_launcher.exe; do
    # The symbol table leaves the shipped file and stays here: llvm-nm -n symbols/<exe>.debug turns a crash
    # line's module+0x<rva> back into a function, and tools_py/hostprof_symbolize.py --exe takes the same file.
    llvm-objcopy --only-keep-debug "$stage/$exe" "$RELDIST/symbols/$exe.debug"
    llvm-strip --strip-all "$stage/$exe"
    ( cd "$RELDIST/symbols" && llvm-objcopy --add-gnu-debuglink="$exe.debug" "$stage/$exe" )
    cp "$stage/$exe" "$RELDIST/$exe"
    printf '%s %s %s\n' "$tag" "$(sha256sum "$RELDIST/$exe" | cut -d' ' -f1)" "$exe" >> "$RELDIST/symbols/INDEX.txt"
  done
  [ -f "$ROOT/dist/socom2_game.elf" ] && cp "$ROOT/dist/socom2_game.elf" "$RELDIST/"
  rm -rf "$stage"
  echo "built dist-release/socom2.exe ($(wc -c < "$RELDIST/socom2.exe") bytes; genopt=$genopt lto=$lto/$scope icf=${icf:-off}; symbols in dist-release/symbols)"
}
```

  and in the `case` add `release) release ;;` after the `runtime)` line. (`set -o pipefail` is on: a closure failure — exit 3 — fails the step, as it should.)

- [ ] **Step 4: `scripts/build_linux.sh release`.** Usage comment: add `#   release   the release configuration (Sprint 9 Goal 2) in build-linux-release -> dist-linux-release, stripped, symbols kept`. After `DIST="$ROOT/dist-linux"` add `RELBUILD="$PS2R/build-linux-release"` and `RELDIST="$ROOT/dist-linux-release"`. In the argument loop change `tools|runtime|test|all)` to `tools|runtime|release|test|all)`. After `runtime()` add

```bash
release() {   # Sprint 9 Goal 2: see build.sh release(); same switches, the system toolchain, ELF strip
  local genopt="${REL_GENOPT:--O2}" lto="${REL_LTO:-OFF}" scope="${REL_LTO_SCOPE:-all}" icf="${REL_ICF:-}"
  local fc=() src name objcopy tag
  for src in "$RTBUILD"/_deps/*-src; do
    [ -d "$src" ] || continue
    name="$(basename "$src")"; name="${name%-src}"
    fc+=("-DFETCHCONTENT_SOURCE_DIR_$(printf '%s' "$name" | tr 'a-z' 'A-Z')=$src")
  done
  cmake_configure "$RELBUILD" -DPS2X_RUNNER_GENERATED_DIR="$GEN" -DPS2X_GENERATED_OPT="$genopt" \
        -DPS2X_ENABLE_LTO="$lto" -DPS2X_LTO_SCOPE="$scope" \
        -DPS2X_RELEASE_LINK=ON -DPS2X_LINK_ICF="$icf" ${fc[@]+"${fc[@]}"} >/dev/null
  objcopy="${OBJCOPY:-$(command -v llvm-objcopy || command -v objcopy)}"
  tag="$(git -C "$ROOT" describe --always --dirty 2>/dev/null || echo unknown)"
  mkdir -p "$RELDIST/symbols"
  local built=()
  if [ -n "$GEN" ] && compgen -G "$GEN/*.cpp" >/dev/null; then
    cmake --build "$RELBUILD" --target ps2EntryRunner -j "${REL_JOBS:-$JOBS}"
    cp "$RELBUILD/ps2xRuntime/ps2EntryRunner" "$RELDIST/socom2.new"; built+=(socom2)
  fi
  cmake --build "$RELBUILD" --target socom_unzipped_launcher -j "${REL_JOBS:-$JOBS}"
  cp "$RELBUILD/ps2xLauncher/socom_unzipped_launcher" "$RELDIST/socom_unzipped_launcher.new"; built+=(socom_unzipped_launcher)
  for exe in "${built[@]}"; do
    "$objcopy" --only-keep-debug "$RELDIST/$exe.new" "$RELDIST/symbols/$exe.debug"
    "$objcopy" --strip-all "$RELDIST/$exe.new"
    ( cd "$RELDIST/symbols" && "$objcopy" --add-gnu-debuglink="$exe.debug" "$RELDIST/$exe.new" )
    mv -f "$RELDIST/$exe.new" "$RELDIST/$exe"
    printf '%s %s %s\n' "$tag" "$(sha256sum "$RELDIST/$exe" | cut -d' ' -f1)" "$exe" >> "$RELDIST/symbols/INDEX.txt"
  done
  if [ -f "$ROOT/dist/socom2_game.elf" ]; then cp "$ROOT/dist/socom2_game.elf" "$RELDIST/"; fi
  echo "built $RELDIST: $(ls "$RELDIST" | tr '\n' ' ') (genopt=$genopt lto=$lto/$scope icf=${icf:-off})"
}
```

  and `release) release ;;` in the `case`. `bash -n build.sh && bash -n scripts/build_linux.sh` must both exit 0.

- [ ] **Step 5: `.gitignore`.** After the `/dist/` line add three lines: `/dist-release/`, `/dist-linux/`, `/dist-linux-release/`. (`/third_party/ps2recomp/build*/` already covers the new trees; `dist-linux/` was never ignored because it only ever existed in the VM and CI.)

- [ ] **Step 6: Configure only, and read the flags (the verification for Step 1's ON side; no compile yet).** Needs the network once (the FFmpeg zip is fetched at *build* time, not here; the fetched sources are reused):

```bash
cmake -S third_party/ps2recomp -B third_party/ps2recomp/build-release -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DPS2X_RUNNER_GENERATED_DIR="$PWD/recomp/output" \
  -DPS2X_GENERATED_OPT=-O2 -DPS2X_ENABLE_LTO=OFF -DPS2X_RELEASE_LINK=ON \
  $(for s in third_party/ps2recomp/build-clang/_deps/*-src; do n=$(basename "$s"); n=${n%-src}; printf -- '-DFETCHCONTENT_SOURCE_DIR_%s=%s ' "$(printf '%s' "$n" | tr a-z A-Z)" "$PWD/$s"; done) | tail -5
grep -c -- '-ffunction-sections' third_party/ps2recomp/build-release/compile_commands.json
grep -o -- '-O3 [^"]*-O2' third_party/ps2recomp/build-release/compile_commands.json | head -1
grep -- '--gc-sections' third_party/ps2recomp/build-release/build.ninja | head -2
ls third_party/ps2recomp/build-release/_deps | grep -c -- '-src$'
```

  Expected: the first count is in the thousands (every compile command); the second prints a line in which `-O2` follows `-O3` for a runner unit (the override wins, `ps2xRuntime/CMakeLists.txt:523`); the third prints link lines carrying `--gc-sections`; the fourth prints **0** (no source was cloned into the release tree). Anything else: stop and fix before Task 5 spends an hour of CPU on it.

- [ ] **Step 7: Suite and commit.** `./build.sh test` exit 0 (it builds in `build-clang`, which Step 2 showed unchanged).

```bash
git commit -m "feat(build): a release configuration in its own tree (build-release -> dist-release): PS2X_RELEASE_LINK, PS2X_LINK_ICF, PS2X_LTO_SCOPE, all off in the developer build; build.sh release and build_linux.sh release strip the two executables and keep symbols/<name>.debug (Sprint 9 Goal 2 Task 4, R140, R146)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/CMakeLists.txt third_party/ps2recomp/ps2xRuntime/cmake/ReleaseMode.cmake \
  build.sh scripts/build_linux.sh .gitignore
git push
```

---

## Task 5 — Measure, choose, gate the release executable; LTO under the stop rule  **[Judgment]**

**Files:**
- Create: `tools_py/release_metrics.py`, `tools_py/tests/test_release_metrics.py`; `logs/s9_g2_build_release.sh`, `logs/s9_g2_release_gate.sh`, `logs/s9_g2_lto_gate.sh` (ignored, never committed)
- Modify: `build.sh` and `scripts/build_linux.sh` (the four `REL_*` defaults, Step 9), this plan (the Results table)

**The baseline this task measures against** (taken 2026-09-19 from artefacts on disk, no launch): developer executable `-O3` runtime / `-O1` generated, no LTO: `socom2.exe` 236,405,760 bytes; zip 65,494,194; link 0.93-0.96 s; the longest compile unit 526 s. From `logs/parity/gate/s9_g1_gate/mission.game.log` (479 one-second `[pc-sampler]` rows): **54.5 vsync/s and `ee/t` 0.995 over the whole run; 46.3 vsync/s and `ee/t` 0.999 over the last 120 s** (the mission hold); `bp_wait_ms` 40,880.

**Steps:**

- [ ] **Step 1: RED -> GREEN, the three readers.** Create `tools_py/tests/test_release_metrics.py`:

```python
"""Sprint 9 Goal 2: the three numbers the release bar needs, read from artefacts that already exist."""
import os
import tempfile
import unittest

from tools_py import release_metrics

NINJA_LOG = ("# ninja log v6\n"
             "100\t4100\t0\tps2xRuntime/CMakeFiles/ps2EntryRunner.dir/Unity/unity_1_cxx.cxx.obj\tabc\n"
             "5000\t905000\t0\tps2xRuntime/ps2EntryRunner.exe\tdef\n"
             "10\t130\t0\tps2xLauncher/socom_unzipped_launcher.exe\t123\n")


def sampler(t, vsync, ee, wait):
    return ("[pc-sampler] live pc=0x180008 ra=0x0 sp=0x1fffff0 t=%.2f vsync=%d ee=%.2f seq=19 dpc=0x34fe0c idle=99 "
            "bp_pending=0 bp_waiters=0 bp_wait_ms=%d net_wait=0/0 running=0 threads: [1 pc=0x1a3a48]\n" % (t, vsync, ee, wait))


class ReleaseMetricsTest(unittest.TestCase):
    def test_link_seconds_is_the_runner_edge(self):
        self.assertEqual(release_metrics.edge_seconds(NINJA_LOG, "ps2EntryRunner.exe"), 900.0)
        self.assertEqual(release_metrics.edge_seconds(NINJA_LOG, "socom_unzipped_launcher.exe"), 0.12)
        self.assertIsNone(release_metrics.edge_seconds(NINJA_LOG, "nothing.exe"))

    def test_speed_is_vsync_and_guest_clock_against_host_time_whole_run_and_tail(self):
        text = "INFO: noise\n" + "".join(sampler(t, 60 * t if t <= 100 else 6000 + 30 * (t - 100), t, 5 * t)
                                        for t in range(1, 201))
        got = release_metrics.sampler_figures(text, tail_s=50)
        self.assertEqual(got["samples"], 200)
        self.assertAlmostEqual(got["vsync_per_s"], 9000 / 200.0)
        self.assertAlmostEqual(got["tail_vsync_per_s"], 30.0)
        self.assertAlmostEqual(got["tail_s"], 50.0)
        self.assertAlmostEqual(got["ee_ratio"], 1.0)
        self.assertEqual(got["bp_wait_ms"], 1000)
        self.assertIsNone(release_metrics.sampler_figures("no rows here\n"))

    def test_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "f", "lib"))
            for name, size in (("f/a", 10), ("f/lib/b", 5), ("z.zip", 7)):
                with open(os.path.join(tmp, name), "wb") as fh:
                    fh.write(b"x" * size)
            self.assertEqual(release_metrics.sizes(os.path.join(tmp, "f"), os.path.join(tmp, "z.zip")),
                             {"folder_bytes": 15, "files": 2, "archive_bytes": 7})


if __name__ == "__main__":
    unittest.main()
```

  RED: `ImportError: cannot import name 'release_metrics'`. Then create `tools_py/release_metrics.py`:

```python
#!/usr/bin/env python3
"""Sprint 9 Goal 2: the release bar's numbers, from artefacts that already exist.

  link   <build dir> <output suffix>   seconds the named link edge took (.ninja_log; ms since that ninja started)
  speed  <game log>                    a frame-rate sanity figure from the gate's own mission.game.log: the
                                       [pc-sampler] rows (the gate sets PS2X_PC_SAMPLER=1 for the mission stage)
                                       give host seconds, the vsync tick and the guest clock -- vsync/s and
                                       ee/t over the whole run and over the last 120 s (the mission hold)
  sizes  <folder> <archive>            bytes
"""
import json
import os
import re
import sys

_SAMPLE = re.compile(r"^\[pc-sampler\] live .*? t=([0-9.]+) vsync=(\d+) ee=([0-9.]+) .*?bp_wait_ms=(\d+)", re.M)


def edge_seconds(ninja_log_text, output_suffix):
    found = None
    for line in ninja_log_text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4 and not line.startswith("#") and parts[3].endswith(output_suffix):
            found = (int(parts[1]) - int(parts[0])) / 1000.0
    return found


def sampler_figures(game_log_text, tail_s=120.0):
    rows = [(float(t), int(v), float(e), int(w)) for t, v, e, w in _SAMPLE.findall(game_log_text)]
    if len(rows) < 2:
        return None
    t1, v1, e1, w1 = rows[-1]
    t0, v0, e0, _w0 = next(row for row in rows if row[0] >= t1 - tail_s)
    if t1 <= t0:
        t0, v0, e0, _w0 = rows[0]
    return {"samples": len(rows), "host_s": t1, "vsync_per_s": v1 / t1, "ee_ratio": e1 / t1,
            "tail_s": t1 - t0, "tail_vsync_per_s": (v1 - v0) / (t1 - t0), "tail_ee_ratio": (e1 - e0) / (t1 - t0),
            "bp_wait_ms": w1}


def sizes(folder, archive):
    total, files = 0, 0
    for dirpath, _dirs, names in os.walk(folder):
        for name in names:
            total += os.path.getsize(os.path.join(dirpath, name))
            files += 1
    return {"folder_bytes": total, "files": files, "archive_bytes": os.path.getsize(archive)}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 3 and argv[0] == "link":
        with open(os.path.join(argv[1], ".ninja_log"), errors="replace") as fh:
            print(json.dumps({"link_seconds": edge_seconds(fh.read(), argv[2])}))
        return 0
    if len(argv) == 2 and argv[0] == "speed":
        with open(argv[1], errors="replace") as fh:
            print(json.dumps(sampler_figures(fh.read())))
        return 0
    if len(argv) == 3 and argv[0] == "sizes":
        print(json.dumps(sizes(argv[1], argv[2])))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

  GREEN: 3 pass. Check it against the record: `python -m tools_py.release_metrics speed logs/parity/gate/s9_g1_gate/mission.game.log` prints `vsync_per_s` 54.5, `tail_vsync_per_s` 46.3, `tail_ee_ratio` 0.999 (the baseline above). Commit with the pathspec `tools_py/release_metrics.py tools_py/tests/test_release_metrics.py` after `./build.sh test`.

- [ ] **Step 2: The build job.** Write `logs/s9_g2_build_release.sh`:

```bash
#!/usr/bin/env bash
# usage: s9_g2_build_release.sh <label> <genopt> <lto ON|OFF> <scope all|runtime> <icf -|safe|all> <cap seconds, 0 = none>
# One release candidate: builds it, packages it, and writes logs/s9_g2_measure_<label>.txt. The work stays in
# this script's foreground (it waits on the build), as run_detached.sh requires.
export PATH="/usr/bin:/mingw64/bin:/c/Users/Utilisateur/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 9
label="$1"; export REL_GENOPT="$2" REL_LTO="$3" REL_LTO_SCOPE="$4"; icf="$5"; cap="${6:-0}"
[ "$icf" = "-" ] && icf=""
export REL_ICF="$icf" REL_JOBS="${REL_JOBS:-$(nproc)}"
out="logs/s9_g2_measure_$label.txt"
start=$(date +%s)
./build.sh release > "logs/s9_g2_build_$label.log" 2>&1 &
job=$!
while kill -0 "$job" 2>/dev/null; do
  if [ "$cap" -gt 0 ] && [ $(( $(date +%s) - start )) -gt "$cap" ]; then
    MSYS_NO_PATHCONV=1 cmd /c "taskkill /T /F /PID $(cat /proc/$job/winpid)" >/dev/null 2>&1
    echo "label=$label STOPPED_BY_CAP cap_s=$cap genopt=$REL_GENOPT lto=$REL_LTO/$REL_LTO_SCOPE icf=${icf:-off}" > "$out"
    exit 124
  fi
  sleep 10
done
wait "$job"; rc=$?
wall=$(( $(date +%s) - start ))
if [ "$rc" -ne 0 ]; then echo "label=$label BUILD_FAILED rc=$rc wall_s=$wall" > "$out"; tail -30 "logs/s9_g2_build_$label.log"; exit "$rc"; fi
bash scripts/make_portable.sh --release > "logs/s9_g2_portable_$label.log" 2>&1 || { echo "label=$label PACKAGE_FAILED wall_s=$wall" > "$out"; exit 4; }
cp dist-release/portable/socom2-portable.zip "logs/s9_g2_zip_$label.zip"
{
  echo "label=$label genopt=$REL_GENOPT lto=$REL_LTO/$REL_LTO_SCOPE icf=${icf:-off} jobs=$REL_JOBS wall_s=$wall"
  python -m tools_py.release_metrics link third_party/ps2recomp/build-release ps2EntryRunner.exe
  python -m tools_py.release_metrics sizes dist-release/portable/socom2 dist-release/portable/socom2-portable.zip
  echo "socom2_exe_bytes=$(wc -c < dist-release/socom2.exe) symbols_bytes=$(wc -c < dist-release/symbols/socom2.exe.debug)"
  tools/llvm-mingw/bin/llvm-objdump -h dist-release/socom2.exe | awk '$2==".text"||$2==".rdata"||$2==".data"{printf "%s=%d ", $2, strtonum("0x"$3)} END{print ""}'
} > "$out"
cat "$out"
```

- [ ] **Step 3: The matrix.** One candidate at a time, each `scripts/run_detached.sh --owner build --purpose build logs/s9_g2_build_release.sh logs/s9_g2_build_<label>.marker <args>`, never while `logs/.quiet` exists, heavy ones in a window the owner names. Poll the marker. Fill the Results table from `logs/s9_g2_measure_<label>.txt`.

| Label | Args after the marker | Cost | What it answers |
|---|---|---|---|
| `M1_O2` | `M1_O2 -O2 OFF all - 0` | heavy: every unit recompiles | the generated code at `-O2`, sections + gc, stripped |
| `M2_Os` | `M2_Os -Os OFF all - 0` | heavy | the same at `-Os` |
| `M3_icf` | `M3_icf <winner's -O> OFF all all 0` | a relink (seconds) **only if M3 follows the winner directly**; otherwise heavy | what identical-code folding finds in 14,882 generated functions |

  The winner between M1 and M2 is chosen by **R143**: the smaller `archive_bytes` wins, unless the two are within 2 % of each other, in which case `-O2` wins. Order the builds so the expected winner (`-Os`, on size) is built **second**, so M3 is a relink; if `-O2` wins instead, M3 costs a third heavy build — record that, do not skip it. `wall_s` of the winner is **T_compile** for Step 8's cap. M3 is kept only if it is smaller **and** Step 6's gate passes on it (it is the executable that gets gated if it is kept — decide before Step 6, not after).

  **Not built, by R142:** `-Os` for the runtime library. `dist/vu1_replay.exe` links the whole of `ps2_runtime` and is 3,031,040 bytes; the runtime is at most 1.3 % of `socom2.exe`, its hot loops (the GS, the VU interpreter, the mixer) are what the 58-60 fps of R123 rests on, and a heavy build to shave under 1 MB is not a trade.

- [ ] **Step 4: Verify the symbols are usable (no RED; a release without this is a release nobody can debug).**

```bash
export PATH="$PWD/tools/llvm-mingw/bin:$PATH"
llvm-nm dist-release/socom2.exe 2>&1 | head -1                       # expect: "...: no symbols"
llvm-nm -n dist-release/symbols/socom2.exe.debug | grep -c ' [Tt] '  # expect: tens of thousands
llvm-nm -n dist-release/symbols/socom2.exe.debug | grep ' T main$'
llvm-objdump -h dist-release/socom2.exe | grep -c gnu_debuglink      # expect: 1
tail -2 dist-release/symbols/INDEX.txt
```

  Then one address end to end: take any `module+0x<rva>` from an old `[crash]` line (or pick `main`'s own address minus the image base), write `<rva> 1` into `logs/s9_g2_rva.txt`, and `python tools_py/hostprof_symbolize.py logs/s9_g2_rva.txt --exe dist-release/symbols/socom2.exe.debug` names the function. If `hostprof_symbolize` cannot read the `.debug` file, that is a finding: record it and keep an unstripped copy (`cp build-release/ps2xRuntime/ps2EntryRunner.exe dist-release/symbols/socom2.exe.unstripped`) as the symbol file instead — 230 MB on the owner's disk, nothing in the download.

- [ ] **Step 5: The cheap proofs on the release folder, before spending a launch.** Quiet gate permitting:

```bash
python tools_py/portable_audit.py audit dist-release/portable/socom2 --system Windows     # 16 needed, 0 missing, 0 orphans
python tools_py/portable_audit.py verify dist-release/portable                            # exit 0
python -m unittest tools_py.tests.test_portable_folder -v                                  # both folders closed; loads with System32 only
SOCOM_EXE="$PWD/dist-release/socom2.exe" python -m unittest tools_py.tests.test_runner_exit_codes tools_py.tests.test_diagnostics_zip -v
dist-release/socom_unzipped_launcher.exe --selftest; echo "selftest rc=$?"
```

  Expected: the exit-code suite's 8 cases pass **on the release runner** (66 twice, 67, 68, 69, 70, 71, 72 — `--fail-test crash` is the case most likely to move under `--gc-sections`/ICF, because it depends on a function the optimiser would love to remove); the diagnostics zip case passes on the release launcher; `selftest rc=0`. A failure here is a failed candidate: fall back per Step 7 without spending a gate.

- [ ] **Step 6: The gate on the release executable (the usual one).** Write `logs/s9_g2_release_gate.sh` (the command set above) and run it detached. Bar: **`GATE PASS (3/3)`**, and `logs/parity/gate/s9_g2_release_gate/summary.txt`'s last line is `EXE /c/projects/socom_pc/dist-release/socom2.exe bytes=… sha256=…` with the SHA-256 that `dist-release/symbols/INDEX.txt`'s last `socom2.exe` line carries. Then `python -m tools_py.release_metrics speed logs/parity/gate/s9_g2_release_gate/mission.game.log`. **The speed floor:** `tail_vsync_per_s >= 44.9` and `tail_ee_ratio >= 0.97` (97 % of the developer build's 46.3 and 0.999). It is a sanity floor, not a ranking: the developer build already runs the mission at the guest clock's own rate, so a release build cannot score higher, only fail to keep up. Record all figures in the Results table.

- [ ] **Step 7: If Step 5 or 6 fails.** One stage failing on the title stage's known margin (19/23 against 19) with the other two passing and the speed floor held: spend the **reserve** gate on the same executable, once. Any other failure: the candidate is out. Fall back in this order, rebuilding as needed and re-running Steps 4-6 with the reserve gate: drop ICF (if M3 was kept) -> the other `-O` level -> `PS2X_RELEASE_LINK` off (`-O2`, stripped only; needs a one-line `REL_LINK` variable in `release()` — add it then, not before). Each fallback is a ruling with what failed and the stamp. If the reserve is spent and nothing passes, **the download ships the developer executable, stripped, with the closure and SHA256SUMS** (Task 3's gain stands on its own), and the release configuration is recorded as built-but-not-shipped.

- [ ] **Step 8: LTO, under the stop rule.** Only after Step 6 passed. Two candidates, cheapest first, each with a cap of **T_compile + 1800** seconds (R144: ThinLTO's compile phase does less work than a normal compile, so a build that outlives a normal build by 30 minutes has spent them in the link):

| Label | Args | What it answers |
|---|---|---|
| `M4_lto_rt` | `M4_lto_rt <winner's -O> ON runtime <winner's icf or -> <T_compile + 1800>` | ThinLTO over `ps2_runtime` only; the generated objects are reused if M4 follows the winner directly |
| `M5_lto_all` | `M5_lto_all <winner's -O> ON all <winner's icf or -> <T_compile + 1800>` | ThinLTO over everything; every unit recompiles to bitcode |

  Read `link_seconds` from each measure file. **The stop rule, verbatim: "if LTO pushes the runner's link past 30 minutes or changes a gate score, ship without it and record why."**
  - `STOPPED_BY_CAP`, or `link_seconds > 1800`: that candidate is out; write the figure and "link past 30 minutes" into the Results table and the rulings. If CMake printed `Interprocedural optimization not supported` (read `logs/s9_g2_build_<label>.log`), the candidate never was one: record that instead.
  - A candidate that links in time and is **at least 1 % smaller in `archive_bytes` or at least 3 % higher in nothing** — that is: LTO is kept only for size, since speed is already at the ceiling — goes to Step 5's cheap proofs and then to the **second extra gate** (`logs/s9_g2_lto_gate.sh`, stamp `s9_g2_lto_gate`). Only one LTO candidate is gated: the smaller of those that linked in time. "Changes a gate score" is read by R144: any stage PASS -> FAIL; or the title count dropping by 2 or more against `s9_g2_release_gate`; or any PROBE line flipping; or the speed floor missed. Any of them: ship without LTO, record which.
  - A candidate that links in time but saves under 1 %: not gated, not shipped, recorded ("LTO bought N bytes; not worth a second configuration to maintain").
  - **Whatever happens, `dist-release/` must end this step holding the executable that passed its gate.** If the last build was a rejected candidate, rebuild the shipped configuration (heavy only if the `-O` level or the LTO scope changed) and check `sha256sum dist-release/socom2.exe` against… nothing: a rebuild is not byte-identical (link order and timestamps), so re-run Step 5's cheap proofs on it and say in the ledger that the gated SHA-256 and the shipped one differ and why. If the launch budget still holds a gate, spend it here; if not, R144's note covers it.

- [ ] **Step 9: Make the measured choice the default.** In `build.sh` and `scripts/build_linux.sh`, set the four defaults in `release()` (`REL_GENOPT`, `REL_LTO`, `REL_LTO_SCOPE`, `REL_ICF`) to what shipped, with a one-line comment naming the Results row. `bash -n` both. `./build.sh test` exit 0. Commit (`build.sh scripts/build_linux.sh` and this plan with its Results table filled).

### Results (filled by Tasks 3, 5 and 6; a row left empty carries its reason)

| Row | Configuration | `socom2` bytes | `.text` | Folder bytes | Archive bytes | Build wall s | Link s | Gate | tail vsync/s | tail ee/t |
|---|---|---|---|---|---|---|---|---|---|---|
| P0 | developer exe, `*.dll` (2026-09-17 zip) | 236,405,760 | 191,886,198 | 297,839,981 | 65,494,194 | — | 0.93-0.96 | `s9_g1_gate` 3/3 | 46.3 | 0.999 |
| P1 | developer exe, closure only (Task 3) | 236,409,856 | 191,886,198 | 277,687,904 | 58,221,191 | — | — | (same exe) | — | — |
| M1_O2 | | | | | | | | | | |
| M2_Os | | | | | | | | | | |
| M3_icf | | | | | | | | | | |
| M4_lto_rt | | | | | | | | | | |
| M5_lto_all | | | | | | | | | | |
| **Shipped** | | | | | | | | | | |
| L0 | Linux developer tarball (Sprint 8: 109 MB, runner 224 MB) | | | | | | | — | — | — |
| L1 | Linux release tarball | | | | | | | — | — | — |

P1 measured 2026-09-19 after `bash scripts/make_portable.sh` at `8220078`: 16 DLLs instead of 31, folder −20,152,077 bytes (−6.8 %), zip −7,273,003 bytes (−11.1 %), `16 needed, 0 missing, 0 orphans`. The exe is 4,096 bytes larger than P0's figure (the runner was relinked by `c40a318`, the crouch shortcut) and 176,128 bytes larger than the one P0's *folder* carried (that folder was packed 2026-09-17, before Goal 1's preflight landed), so the DLL saving alone is 20,328,205 folder bytes.

---

## Task 6 — The Linux ring  **[Judgment]**

**Files:** none in the repository beyond this plan's Results table; the work is in the VM (`scripts/vm_sync.sh`, memory `linux-vm-socom-linux`; never the owner's `Work` VM).

- [ ] **Step 1: The "before".** Start the VM, `scripts/vm_sync.sh tree`, then in the VM: `bash scripts/build_linux.sh all` (incremental), `bash scripts/make_portable.sh`, and record row **L0** from the script's own last line plus `ls dist-linux/portable/socom2-linux/lib | wc -l` and `readelf -d dist-linux/socom2 | grep NEEDED`. Expected in the `NEEDED` list: `libavformat` and `libswresample`, which the runner never calls (Handoff note 9).
- [ ] **Step 2: The release build.** In the VM, detached the VM's way (`nohup … &` with a marker; the host-load rule still applies — the VM's 8 cores are the host's): `REL_GENOPT=<shipped> REL_LTO=<shipped> REL_LTO_SCOPE=<shipped> REL_ICF=<shipped> bash scripts/build_linux.sh release`. If ICF shipped, the VM needs `lld` (CI's package list has it; `sudo apt-get install -y lld` in the VM if absent). Then `bash scripts/make_portable.sh --release`. Record row **L1**, the new `lib/` count and the new `NEEDED` list: `libavformat` must be gone from it (`--as-needed`); if it is still there, something does call it — read `nm -D --undefined-only dist-linux-release/socom2 | grep -i avformat` and record what.
- [ ] **Step 3: The proofs.** In the VM: `python3 tools_py/portable_audit.py audit dist-linux-release/portable/socom2-linux --system Linux` (0 missing, 0 orphans); `python3 tools_py/portable_audit.py verify dist-linux-release/portable` and `( cd dist-linux-release/portable && sha256sum -c SHA256SUMS )`; `python3 -m unittest tools_py.tests.test_make_portable_linux tools_py.tests.test_portable_folder -v` (**run, not skipped**); `SOCOM_EXE="$PWD/dist-linux-release/socom2" python3 -m unittest tools_py.tests.test_runner_exit_codes -v` (8 pass on the release runner); from the unpacked tarball in a fresh directory with no `DISPLAY`: `./socom2 --home "$PWD/nowhere"; echo $?` prints `68` and `./socom_unzipped_launcher --diagnostics /tmp/d.zip` exits 0; `file socom2` says `stripped`; `readelf -p .gnu_debuglink socom2` names `socom2.debug`; `nm dist-linux-release/symbols/socom2.debug | wc -l` is large.
- [ ] **Step 4: No VM gate.** R148: the three-stage bar is the Windows gate's; the VM's title stage runs at llvmpipe's 1.6 fps and is marginal by Sprint 8's own record (3 of 4), so a pass or a fail there says nothing about an optimisation level. What Linux gets is Step 3 plus the owner's real-GPU run of the tarball (already filed in `docs/HUMAN_TASKS.md`), which should now be pointed at the release tarball.

---

## Task 7 — Close-out  **[Judgment]**

**Files:** `docs/KNOWN.md`, `docs/STATUS.md`, `docs/CURRENT_SPRINT.md`, `docs/HUMAN_TASKS.md`, this plan.

- [ ] **Step 1: `docs/HUMAN_TASKS.md`**, three lines: (a) signing is the owner's (spec §5): when there is a certificate, sign `dist-release/socom2.exe` and the launcher **before** `make_portable.sh --release` so `SHA256SUMS` covers the signed files; (b) keep `dist-release/symbols/` (and the Linux one) with every archive that is published — `symbols/INDEX.txt` ties each `.debug` file to the SHA-256 of the executable it belongs to, and a crash report from a release whose symbols were deleted cannot be read; (c) one check from another machine: download the zip and `SHA256SUMS`, run `Get-FileHash socom2-portable.zip -Algorithm SHA256` (Linux: `sha256sum -c SHA256SUMS`), compare. Also repoint the existing real-GPU Linux item at `dist-linux-release/portable/socom2-linux.tar.gz`.
- [ ] **Step 2: `docs/KNOWN.md` (controller only).** New proven rows, each naming its artefact: the portable folder is the import closure (`test_portable_folder`, `test_make_portable`, `test_make_portable_linux`; the 15-name list); `SHA256SUMS` (`test_make_portable*`); the release executable passes the gate as itself (`s9_g2_release_gate`, its `EXE` line); the archive's before/after (Results table); LTO's outcome under the stop rule, with the figure. Believed-not-proven: the release build under a heavier scene than the gate's mission (a 16-player online round) — the speed floor was read from the single-player hold only; the release executable has not run an online round. Retract nothing unless a step above killed something.
- [ ] **Step 3: `docs/STATUS.md` and `docs/CURRENT_SPRINT.md`.** A dated entry: what landed, the Python total, the gate stamps, the Results table's Shipped row in one sentence ("the download went from 65.5 MB to N MB: −8 MB from 15 DLLs nothing loads, −M MB from …"), R140-R150 by one-line title; Goal 2 marked DONE in the Sprint 9 block with `next ruling: R151`; the pointer moved to Goal 3's plan.
- [ ] **Step 4: Tick this plan's boxes; leave a reason on every one that stays open.**
- [ ] **Step 5: Commit.**

```bash
git commit -m "docs: Sprint 9 Goal 2 closed -- a smaller, checkable download (the import closure, SHA256SUMS, the release configuration gated as itself); R140-R150

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  docs/KNOWN.md docs/STATUS.md docs/CURRENT_SPRINT.md docs/HUMAN_TASKS.md \
  docs/superpowers/plans/2026-09-20-sprint-9-goal-2-release-build.md
git push
```

---

## Rulings made on the owner's behalf

R140 onward (Goal 1 used R126-R138; R139 is the crouch shortcut's). Each is a decision this plan made where the spec was silent or the tree disagreed with it; each is the controller's to overturn before the task that carries it starts.

- **R140** (Task 4): **"release" is a second build tree with different switch values, not a CMake build type; it writes `dist-release/` and nothing else reads that folder unless told to.** The developer build is already `CMAKE_BUILD_TYPE=Release` (Handoff note 1), so a new build type would mean re-deriving `-O3 -DNDEBUG` for every third-party target to change two arguments. Three switches that default off, passed only by `build.sh release`, leave `build-clang` bit-for-bit alone — proven by `ninja: no work to do` (Task 4 Step 2), not asserted. The gate, the harness, the ladder and `test_runner_exit_codes` keep using `dist/socom2.exe`; the daily instrument does not change under this goal. *Cost if wrong:* two trees (about 2.3 GB each) and a release executable that is only exercised when someone sets `SOCOM_EXE`. The alternative — making the release build the daily one — would put a 2-3x longer rebuild in every runtime task's loop.

- **R141** (Task 1): **the override is `SOCOM_EXE`, beside `SOCOM_ISO`, not a `PS2X_*` name and not a `--exe` flag; the runner must still be called `socom2[.exe]`; the gate's summary names what it scored.** Goal 3 is counting `PS2X_*` names and this is a harness setting, not a runtime one. An environment variable reaches all three consumers (`run.sh` on Windows, `drive.py` on Linux, `test_runner_exit_codes`) through the one inherited environment; a flag would have to be threaded through `gate.py` -> `drive.py` -> `run.sh`. The name check exists because `kill_argv`/`running_argv` work by process name: a runner called `socom2_release.exe` would be started and never found. *Cost if wrong:* a stale `SOCOM_EXE` in a shell silently gates the wrong binary — which is why the `EXE` line with its SHA-256 is printed first and written into `summary.txt`.

- **R142** (Task 5, a skipped measurement): **the runtime library stays at `-O3`; `-Os` for it is not built.** Bounded by arithmetic instead: `vu1_replay.exe` links all of `ps2_runtime` and is 3.0 MB, so the runtime is at most 1.3 % of the 236 MB executable, and its loops are what R123's 58-60 fps rests on. *Cost if wrong:* under 1 MB of download.

- **R143** (Task 5): **between `-O2` and `-Os` for the generated code, the smaller archive wins unless they are within 2 %, in which case `-O2`; speed is a floor (97 % of the developer build's tail figures), not a ranking.** The developer build's generated code is at `-O1` and already holds the guest clock (`ee/t` 0.999), so neither candidate can score higher on the gate's mission; they can only differ in size and in headroom the gate does not measure. *Cost if wrong:* `-Os` costs headroom in scenes heavier than the gate's (a full online round) — recorded as believed-not-proven in Task 7, and `REL_GENOPT=-O2` is a one-variable rebuild.

- **R144** (Task 5): **how the stop rule is read.** *"Past 30 minutes"*: `link_seconds` from `.ninja_log`, and — because a runaway link must be stoppable without watching it — a wall-clock cap of `T_compile + 1800 s` on the whole LTO build, `T_compile` being the measured wall time of the same configuration without LTO; ThinLTO's compile phase does less than a normal compile, so a build past that cap has spent over 30 minutes linking. *"Changes a gate score"*: the gate's scores are not deterministic (captures are timed), so "changes" means a stage PASS -> FAIL, the title count dropping by two or more against the non-LTO release gate, a PROBE line flipping, or the speed floor missed. And LTO is only worth a gate if it saves at least 1 % of the archive. The last rebuild of the shipped configuration is not byte-identical to the gated one (Task 5 Step 8); the cheap proofs are re-run on it and the ledger says so. *Cost if wrong:* a marginal LTO win is left on the table; the spec's own rule already prefers that.

- **R145** (Task 3): **the Windows folder ships the sixteen DLLs the import tables reach, and `libwinpthread-1.dll` is dropped with the other fourteen.** It was copied by name (`build.sh:45`) on the reasonable assumption that a mingw C++ runtime needs it; llvm-mingw's `libc++.dll` uses Win32 threads and imports it nowhere, and no file in `dist/` does. `jxl`, `brotli*`, `libwebp*` and `libsharpyuv` (7.6 MB raw) **stay** although the game decodes nothing but MPEG-2: `avcodec-61.dll` imports them statically and will not load without them. A slimmer FFmpeg (an `--enable-decoder=mpeg2video` build would be a few MB instead of 33) is the largest remaining DLL saving and is **not** this goal: it means owning an FFmpeg build. `dist/` itself keeps all 31 (the developer folder is not the download). *Cost if wrong:* a DLL loaded by name at run time that the tables cannot show — caught by the gate on a folder holding only the sixteen and by the `System32`-only run.

- **R146** (Task 4): **symbols are the symbol table split out with `objcopy --only-keep-debug`, not DWARF; the release is not built with `-g`.** The crash handler prints `module+0x<rva>` and the project's symboliser (`hostprof_symbolize.py`) works from `llvm-nm`, so the symbol table is what crash diagnosis actually uses; `-g1` over 192 MB of generated code would multiply compile time and object size for line numbers into machine-written files nobody reads. `symbols/` stays on the build machine, outside the archive, indexed by the executable's SHA-256; keeping it per published release is the owner's (Task 7 Step 1). *Cost if wrong:* a crash inside the hand-written runtime resolves to a function, not a line.

- **R147** (Task 3): **`SHA256SUMS` is an integrity check, one file per archive directory, in `sha256sum -c` format; it is not a signature and the archives are not reproducible.** Zip and tar entries carry timestamps and `Compress-Archive` is not deterministic, so two packagings of one build differ; the file answers "did my download arrive intact", which is what the spec asks ("checkable"). Authenticity is signing, which the spec leaves to the owner. When both archives are published in one place, the two files are concatenated. *Cost if wrong:* someone expects `SHA256SUMS` to prove who built it; the landing page (Sprint 11) should say what it does prove.

- **R148** (Tasks 5, 6): **the 3/3 bar is the Windows gate's; Linux's release build is proven by the exit-code suite on the release runner, the audit, the checksum and the tarball's own self-tests in the VM, and CI does not build the release configuration.** The VM's gate is title-only and marginal at 1.6 fps (Sprint 8, R107), so it cannot discriminate between optimisation levels; CI has no generated code and is already near its 60-minute timeout. *Cost if wrong:* a Linux-only miscompile at the release `-O` level that the eight exit-code cases and a boot do not reach — the owner's real-GPU tarball run is the backstop, and it is now pointed at the release tarball.

- **R149** (Task 5): **identical-code folding (`--icf=all`) is measured although the spec does not name it, and ships only under the same stop rule as LTO.** Every generated function is referenced from the registration table, so `--gc-sections` — the spec's switch — has almost nothing to collect there (Handoff note 6); ICF is the link-time switch aimed at what the file is actually made of, and costs a relink. It can break code that compares function addresses; the gate and the exit-code suite are the judges. *Cost if wrong:* one relink and, if kept wrongly, a fold that merges two functions a debugger then shows under one name (the `.debug` file records the surviving name only).

- **R150** (Task 3): **the closure rule applies to the developer packaging too (`make_portable.sh` with no flag), not only to `--release`.** One rule, one audit, one test; the 8 MB saving does not depend on the release build surviving its gate, which is what makes Task 5 Step 7's last fallback ("ship the developer executable, stripped") a real option. *Cost if wrong:* none identified; `dist/` itself is untouched.

## Self-review

- **Goal coverage, against the spec's two bullets and its bar.** *A release configuration (`-O2`/`-Os` measured, LTO where the link time allows, stripped, harness-only DLLs dropped from the portable folder), on both platforms' packaging scripts* -> Task 4 (the configuration, both build scripts, strip + symbols), Task 5 Steps 3 and 8 (`-O2` vs `-Os`, ICF, ThinLTO in two scopes — measured, with the one skipped measurement ruled, R142), Task 3 (the DLLs, both branches of `make_portable.sh`), Task 6 (Linux). *`SHA256SUMS` written beside each archive and verified by a test* -> Task 2 (`write_`/`verify_sha256sums`), Task 3 (`test_make_portable` on Windows, `test_make_portable_linux` in CI, `sha256sum -c` as an independent reader). *Bar: the three-stage gate 3/3 on the release exe* -> Task 1 (the mechanism, which did not exist) and Task 5 Step 6 (the `EXE` line proves which binary). *The archive's size recorded before/after* -> the Results table, with the DLL change (P1) isolated from the compiler's (M rows). *The stop rule* -> quoted verbatim in the header, the Global Constraints and Task 5 Step 8; R144 says how each half is read and enforced.
- **The brief's additions.** *Selectable without disturbing the developer build or its build directory* -> R140, Task 4 Step 2's `ninja: no work to do`. *Candidate flags measured not assumed* -> the matrix; the only assumption-by-arithmetic is R142. *Symbols stripped into a separate file kept for crash diagnosis* -> Task 4 Step 3, Task 5 Step 4 (verified end to end through the project's own symboliser; the split itself was tried on a copy of the launcher while writing this plan). *A test that fails when the shipped exe imports a DLL that is not in the folder or the folder carries a DLL nothing imports* -> `test_portable_audit` (synthetic, both formats, every host), `test_make_portable` (the script), `test_portable_folder` (the real folders on the machine — RED today on the 15 orphans). *The Linux branch's `version.txt` and `SHA256SUMS` under a test that runs on Linux CI* -> `test_make_portable_linux`, with "a skip in CI is a failure" as Task 3 Step 8. *Link time, a frame-rate sanity figure from the gate's own logs* -> `release_metrics` (`.ninja_log`; `[pc-sampler]` rows, which the gate's mission stage already emits). *Budget: two gate launches beyond the usual one* -> three gates named, a fourth needs the owner. *Host load* -> Handoff notes; every build through `run_detached.sh --purpose build`.
- **What the tree contradicted, and what the plan does instead** — fifteen items in the Handoff notes. The ones that change the work: the developer build is already Release (R140); LTO is already ThinLTO and already covers the generated code (hence `PS2X_LTO_SCOPE`); the link takes a second and the compile has a 526 s floor; none of the fifteen DLLs is harness-only (they are the FFmpeg zip's whole `bin/` plus `libwinpthread`); no debug info ships, so stripping is about 3 % and the mass is `.text`; `--gc-sections` has nothing to collect in table-registered code (R149); nothing could point the gate elsewhere, and on Windows the launch goes through `run.sh`, not `runtime_exe()`; the gate cannot prove the DLL set because `run.sh` extends `PATH`; Linux links `libavformat` without calling it; two of the brief's paths are elsewhere; the packaging test's fake executables must become real PE files; `dist-linux/` was never git-ignored.
- **Launch budget.** One gate on the shipped release executable, one on the LTO candidate if one survives its link, one reserve: three. Sub-second window-less runs (exit 68, `--diagnostics`, `--selftest`) are held by the quiet gate like any suite. Task 1 Step 3's RED starts the real game for 5 seconds where `dist/socom2.exe` exists, and says so.
- **Placeholder scan.** No `TBD`, no "handle edge cases", no "similar to Task N". What is left to the executor is measurement: `P` and `B`; the Results table; `T_compile`; which `-O` level, ICF and LTO scope ship (decided by stated rules: R143, R144, R149). The `<winner's -O>` and `<T_compile + 1800>` tokens in Task 5's tables are those measured values, named where they are produced. Task 5 Step 7's `REL_LINK` variable is deliberately not written until a fallback needs it.
- **Type consistency.** `hostplatform.{EXE_OVERRIDE_ENV, runtime_exe(system=None, env=None)}`; `gate.exe_line(env=None) -> str`; `portable_audit.{pe_imports(path), elf_needed(path), is_windows_system(name), is_linux_host(name), closure(exes, folder, system) -> (dict, dict), audit(folder, system=None) -> {"needed": list, "missing": dict, "orphans": list}, write_sha256sums(out_dir, names) -> path, verify_sha256sums(out_dir) -> list, main(argv)}` with CLI exits 3 (closure: missing), 4 (audit: finding), 5 (verify: problem); `binfmt_fixtures.{tiny_pe(imports), tiny_elf(needed)}`; `release_metrics.{edge_seconds(text, suffix), sampler_figures(text, tail_s=120.0), sizes(folder, archive)}`. `make_portable.sh` exits: 2 no build, 3 an import is nowhere, 4 the audit failed. CMake: `PS2X_RELEASE_LINK` (BOOL), `PS2X_LINK_ICF` (STRING), `PS2X_LTO_SCOPE` (STRING). Environment: `SOCOM_EXE`, `REL_GENOPT`, `REL_LTO`, `REL_LTO_SCOPE`, `REL_ICF`, `REL_JOBS`. **No new `PS2X_*` environment variable.**
- **Platform halves.** Every `make_portable.sh` change is in both branches in one commit; every CMake switch has its ELF half in the same block (`--as-needed`, `-fuse-ld=lld` for ICF); both build scripts gain the same `release()`. The audit reads both formats on both hosts, so the Windows host can audit a tarball pulled from the VM and CI can run the PE cases.
- **Owner gate.** Autonomous end to end. Filed, not waited for (Task 7 Step 1): signing; keeping `symbols/` with each published archive; one checksum check from another machine. The rulings most likely to be a matter of judgment rather than measurement: R143 (smaller wins over faster, because the gate cannot see headroom), R145's "a slimmer FFmpeg is not this goal" (it is the biggest saving left on the table: about 30 MB raw), and R148 (no release configuration in CI).
