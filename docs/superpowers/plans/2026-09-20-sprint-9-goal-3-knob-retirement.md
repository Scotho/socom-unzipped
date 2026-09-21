# Sprint 9 Goal 3 — Knob Retirement, Pass 2: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A stranger's environment cannot change how the game behaves by accident. Today (measured 2026-09-19 at `8e5d778`) the shipped executables read **134 distinct `PS2X_*` names** through **198 direct `getenv` calls in 32 files and 15 more reads behind seven helpers** (the spec's "190" was an estimate; the full table is below), every one of them honoured unconditionally, by whoever happens to have it set. After this goal every read goes through one accessor backed by one registry; **17 names are SHIPPING** (the launcher's own channel to the game, already fields of `config.json`), **112 are DEV** (honoured only with `--dev` or `PS2X_DEV=1`), **5 are DEAD** (deleted with the code they guard); the runner prints one `[knobs]` line at start naming what is in effect and what it ignored, and the diagnostics zip carries it; the launcher stops handing inherited `PS2X_*` variables to the game; `docs/KNOBS.md` is generated from the registry and a test fails when the source and the registry disagree in either direction.

**Architecture:** Five pieces. (1) **`ps2xShared/include/ps2x/knobs.h` + `src/knobs.cpp`**: an X-macro table (name, class, kind, default, one-line meaning) that *is* the accessor's lookup table, in the shape of `ps2x/exit_codes.h`; `ps2x::knob(name)` returns the value or `nullptr`, `ps2x::knobOn(name, dflt)` applies the one flag rule; `ps2x::knobs::devMode()` is `--dev` or `PS2X_DEV`; an **enforcement switch that is OFF until Task 7**, so Tasks 1-5 change no behaviour at all. (2) **`tools_py/knobs.py`**: reads the header with a regex (as `tools_py/exit_codes.py` does), renders `docs/KNOBS.md`, and scans the source for `PS2X_*` string literals, raw `getenv("PS2X_` calls and namespace-scope reads; `tools_py/tests/test_knobs_registry.py` turns those scans into the spec's bar. (3) **Developer mode wired into every launcher of the runner before it matters**: `run.sh`, `scripts/parity/env.sh`, `hostplatform.dev_env` (used by `drive.py`'s Linux branch and `scale_shot.py`), `ps2x_tests`' `main`, `vu1_replay`'s `main`. (4) **The migration**: eight mechanical batches by subsystem, each `./build.sh test` exit 0, one gate after the last (R157). (5) **The flip** (Task 7): enforcement on, seven presence-tested A/B switches moved to the flag rule, the pad on by default, the launcher's inherited-knob filter, the `knobs:` line in `versions.txt` — its own gate, one 90-second poisoned-environment launch, one online control round.

**Tech Stack:** C++20 (`ps2x_shared`, header + one `.cpp`, no dependency beyond the standard library), MiniTest (`ps2xTest`), Python 3 `unittest` (**not** pytest), Git Bash, `scripts/run_detached.sh` + `scripts/loop_lock.sh` for every build and every launch.

**Spec:** `docs/superpowers/specs/2026-09-19-sprint-9-a-strangers-first-run-design.md` §2 "Goal 3 — knob retirement, pass 2" and §4 (every moved default or skipped measurement is a numbered ruling, next **R152**; at most two C++-building agents). **The bar, verbatim:** *"a generated table in `docs/KNOBS.md` checked by a test against the source (a knob read in code and absent from the table fails the suite); the gate 3/3 with an empty environment."* The second half is **not reachable as written** and is restated by R163 (Handoff note 3). **Required reading for every dispatch:** this plan's Handoff notes and Global Constraints; `third_party/ps2recomp/ps2xShared/include/ps2x/exit_codes.h` and `tools_py/exit_codes.py` (the pattern this goal copies); `third_party/ps2recomp/ps2xShared/src/launcher_config.cpp:342-451` (`mergeEnvironment`, `environmentFor`); `third_party/ps2recomp/ps2xShared/src/bare_run.cpp:66-88`; `third_party/ps2recomp/ps2xRuntime/src/main.cpp:191-275`; `run.sh` (all of it); `scripts/parity/env.sh` (all); `tools_py/parity/drive.py:57-98`; `tools_py/parity/gate.py:539-581`; `third_party/ps2recomp/ps2xTest/src/main.cpp:36-76`.

## Handoff notes for the executing model (read once)

- **Process.** superpowers:subagent-driven-development; a fresh implementer per task; a task review after each; the controller merges. Ledger at `.superpowers/sdd/2026-09-20-sprint-9-goal-3/progress.md`. Decisions on the owner's behalf are `Ruling: … — why — cost if wrong`, numbered from **R152**; this plan uses R152-R168 and the next free number is **R169**.

- **What the tree says that the spec and the brief do not, in the order it will bite.**
  1. **The number is 134, not 190.** `grep -rnaE '"PS2X_[A-Z0-9_]+' ps2xRuntime/{src,include} ps2xIOP ps2xShared ps2xLauncher` finds 134 names read by the shipped executables (133 by the runner, `PS2X_LAUNCHER_SHOT` by the launcher). Beyond them: **8 test-only** names read by `ps2x_tests` (`PS2X_TEST_SUITE`, `PS2X_TEST_SKIP`, five `PS2X_CONSOLE_REPLAY_*`, `PS2X_PK_REPLAY`), **3 harness-only** names no C++ reads (`PS2X_RUN_LOG` in `run.sh`/`drive.py`, `PS2X_TEST_REPEAT` in the build scripts, `PS2X_SOCOM2_RSA_KEY_B` in the online scripts), **2 ghosts** that exist only in prose (`PS2X_VU1_XGKICK_IMMEDIATE` in `README.md:89` and a comment at `ps2_vu1_core.cpp:1071`; `PS2X_GS_COUNT_MB` in a comment at `gs_gl_backend.cpp:923`), and about 120 `PS2X_*` identifiers that are CMake options, ABI constants and include guards and are no concern of this goal. **Use `grep -a`**: `socom2_libnetb.cpp`, `socom2_audio_tests.cpp` and `MiniTest.h` carry a non-UTF-8 byte and plain `grep` reports them as binary and prints nothing.
  2. **Goal 8 is in flight beside this plan and adds a 135th name.** Session work on the launcher's bug report added `ps2xShared/include/launcher/bug_report.h:32` — `constexpr const char *kApiBaseEnv = "PS2X_LAUNCHER_API_BASE";` (test-only, loopback-only) — and is editing `ps2xShared/CMakeLists.txt`, `ps2xTest/CMakeLists.txt` and `ps2xTest/src/main.cpp`, which Task 1 also edits. Before Task 1: `git status --short third_party/` and `git log -5 --oneline -- third_party/ps2recomp/ps2xShared`; if that work has landed, add the row `X("PS2X_LAUNCHER_API_BASE", Dev, Text, "https://s2u.scotho.com", "Launcher tests only: a loopback base URL for the bug-report and stats calls.")` in its sorted place (between `PS2X_JALR_TRACE` and `PS2X_LAUNCHER_SHOT`) and have its read go through `ps2x::knob`; if it has not, the registry test will fail the day it does, which is the test doing its job. Never stage a file that session is editing (memory: commit-only-idle-files).
  3. **The spec's bar "the gate 3/3 with an empty environment" cannot be met as written, by construction.** The gate is an instrument, and its instruments are knobs: every stage captures frames through `PS2X_HOST_SCREENSHOT_LATEST` (`drive.py:65`; a GDI grab of the GL window comes back white on this host), the mission stage scores `[pc-sampler]`/`[peek]` rows that only `PS2X_PC_SAMPLER` and `PS2X_PEEK` produce (`gate.py:565-571`), it boots with `PS2X_HOST_GAMEPAD=0` so a plugged-in controller cannot skip the screens the transition stage keys on (`gate.py:554`), it runs on a per-stamp card through `PS2X_MC_DIR` (`gate.py:560-563`), and on Linux it presses buttons through `PS2X_SOCOM2_INPUT_FILE` (`drive.py:73-77`). Four of those six are probes and become DEV. **R163 restates the bar** as two statements that can each be proven: *(a) the game is deaf to a stranger's environment* — with no `--dev` and no `PS2X_DEV`, a launch whose environment is poisoned with six behaviour-changing DEV knobs runs on the GL backend, prints no sampler row, and names all six on its `[knobs]` line as ignored (Task 7 Step 9); *(b) the gate needs nothing from the operator* — the gate passes 3/3 started from a shell with no `PS2X_*` variable set, because it sets its own instruments and its own developer mode (it already sets the former; Task 3 adds the latter).
  4. **Four reads happen before `main`, where `--dev` cannot have been seen.** Namespace-scope statics: `ps2_memory.cpp:12` (`g_traceFifo`), `ps2_vif1_interpreter.cpp:24` (`g_vif1NoIrqStall`), `gs/ps2_gif_arbiter.cpp:22` (`s_prioritySort`), `socom2_libnetb.cpp:74` (`g_verbose`, non-const, 9 uses). Each becomes a function with a function-local static in its batch (Task 4), and `test_knobs_registry` refuses a new one.
  5. **One read lives in a header that every one of the 14,882 generated files includes.** `ps2xRuntime/include/ps2_runtime_macros.h:785` (`PS2X_FPU_TRAP`). Touching it rebuilds all 467 unity units: about 4,500 CPU-seconds with a 526-second floor for one unit (Goal 2 plan, Handoff note 3). It is its own batch, last, built once, in a window the owner names (R165). **No other batch may dirty a generated unit**: before every batch build, `ninja -C third_party/ps2recomp/build-clang -n | grep -c "Unity/unity_"` must print `0`.
  6. **Hot reads that are not cached today.** Almost every site reads once into a function-local `static`. These do not, and sit on paths that run hundreds to thousands of times a second: `ps2_runtime.cpp:672` (`PS2X_TRACE_VU`, inside the VU1 MSCAL callback — every microprogram start), `gs/gs_frontend.cpp:1012` (`PS2X_GIF_DUMP`, every image upload — thousands a second in the menus), `game_overrides_socom2.cpp:190` (`PS2X_SOCOM2_NET_TRACE`, every libnetb RPC), `Kernel/Stubs/MemoryCard.cpp:1053` and `:1390` (`PS2X_MC_TRACE`, every GetInfo and Sync — Sync is polled), `ps2_vif1_interpreter.cpp:42/328/382/871` (`PS2X_TRACE_FIFO`), and `PS2X_HOST_GAMEPAD_INDEX` on every pad poll at `Pad.cpp:94`, `ps2_pad.cpp:45`, `socom2_host_input.cpp:232/314`. The batches cache exactly these (the code is in Task 4); `ps2x::knob` itself stays a plain `getenv` on the unset path so it is never slower than today (R154).
  7. **The launcher hands the game its whole inherited environment.** `mergeEnvironment` (`launcher_config.cpp:342`, used by `posix_glue.cpp:241`) and the same loop written out again in `win32_glue.cpp:270-300` copy every inherited variable the launcher did not itself set. So a stale `PS2X_GS_BACKEND=cpu` reaches the game through the launcher today, and — worse, because DEV gating would not stop it — so do the **six SHIPPING names the launcher only sends conditionally**: `PS2X_MIC_DEVICE` (empty = not sent), `PS2X_HOST_GAMEPAD_INDEX` (-1), `PS2X_PAD_CROUCH_SHORTCUT` (off), `PS2X_SOCOM2_MOUSE`/`_MOUSE_SENS` (mouse look off), `PS2X_SOCOM2_UDP_SHIFT`/`PS2X_SOCOM2_RSA_KEY` (no second instance). A stale `PS2X_SOCOM2_UDP_SHIFT=2` from a two-instance session silently moves a stranger's UDP ports. Task 7 filters inherited `PS2X_*` out of the child's environment unless the launcher itself was started with `PS2X_DEV=1` (R156).
  8. **Precedence is opposite on the two paths, on purpose, and stays that way (R164).** Through the launcher, `config.json` wins over the environment (`mergeEnvironment`: "ours win by key", under a test). In a bare run the environment wins over `config.json` (`BareRun::applyEnvironment`, `bare_run.cpp:77`, under a test, commented "spec Goal 3's rule, applied early"). "The env var kept as an override" is therefore true exactly where a developer is — a by-hand or harness run — and false in the launcher, where the player's own setting must not lose to a forgotten variable.
  9. **All 17 SHIPPING names are already `config.json` settings.** `launcher::Config` has a field behind every one (`secondInstance` stands behind `PS2X_SOCOM2_UDP_SHIFT` and `PS2X_SOCOM2_RSA_KEY`; `PS2X_SOCOM2_PAD` is the constant `1`). Nothing has to be "moved into `config.json`"; what is missing is the *identity*, so Task 1 adds a test that the set of names `environmentFor` can emit equals the registry's Shipping class.
  10. **`PS2X_SOCOM2_PAD` is opt-in by presence, and a by-hand `socom2 game.elf` therefore has no controller.** `game_overrides_socom2.cpp:280`: unset means `scePad2Init` returns 0 and the game sees no pad. All four launch paths set it (`environmentFor`, BareRun through it, `drive.py:66`, `online_login_ours.py:81`); the comment that justifies the default ("so the default boot stays in the renderable shell loop") describes a runtime from before input worked. Task 7 makes it on by default, `0` turns it off (R160).
  11. **"`X=0` turns X on" for every presence-tested switch.** `PS2X_GS_NO_ZTEST=0` disables the depth test; `PS2X_VU1_XGKICK_CYCLE_EXACT=0` selects the per-cycle model that drops the game's object geometry (`ps2xTest/src/main.cpp:66-72` documents that trap for itself). Task 7 moves the seven presence-tested switches that change *behaviour* (and the pad) to the flag rule `socom2_libnetb.cpp:76-85` already states ("unset or empty = default; 0, false, off = false; anything else = true"); the presence-tested *traces* stay as they are and the table says `Presence` (R161).
  12. **Defaults the runtime and the launcher disagree on** (both are right; the registry records the runtime's): `PS2X_WINDOW_SIZE` 640x448 against the launcher's 1280x896; `PS2X_SOCOM2_MOUSE_SENS` 4.0 (`socom2_host_input.cpp:47`) against the launcher's 1.0; `PS2X_PAD_CROUCH_SHORTCUT` off against the launcher's `l3`. The `[knobs]` line prints a SHIPPING name only when its value differs from the *runtime's* default, so a launcher run always lists these three.
  13. **`ps2x_tests` and `vu1_replay` set DEV knobs on themselves** (`ps2xTest/src/main.cpp:73-75`: `PS2X_GS_BACKEND=cpu`, `PS2X_VU1_FAST=0`, `PS2X_VU1_XGKICK_CYCLE_EXACT=1`; `vu1_replay.cpp:946-980`; and tests set `PS2X_SND_STREAM_WORKER`, `PS2X_WINDOW_TITLE`, `PS2X_MIC_GAMEREAD_DUMP`, `PS2X_SOCOM2_NET_STATS`, `PS2X_VU1_NATIVE` mid-process). Both call `ps2x::knobs::setDevMode(true)` first thing in `main` (Task 3). Because tests change variables mid-process, **the accessor must not snapshot the environment** (R154).
  14. **`ps2_iop` does not link `ps2x_shared`.** `ps2xIOP/src/modules/snd989.cpp:395,983` read `PS2X_MPEG_TRACE`. Batch E adds `target_link_libraries(ps2_iop PRIVATE ps2x_shared)`; `ps2xShared` is added before `ps2xIOP` in the top `CMakeLists.txt` (`:109` against `:112`).
  15. **The brief's paths.** There is no `src/` at the repository root; everything is under `third_party/ps2recomp/`. `tools_py/tests/` is discovered by `python -m unittest discover -s tools_py/tests -t .` (`build.sh:109`).

- **`docs/KNOWN.md` has one writer: the controller.**

- **Autonomy (owner 2026-09-17, standing).** Proceed autonomously. **One host launch at a time**, always through `scripts/run_detached.sh`, and **suites are held while a host launch runs**: no `./build.sh test`, no `python -m unittest`, no build, no gate and no second launch while `logs/.quiet` exists (`bash scripts/check_quiet_gate.sh` answers).

- **Host load (owner, memory `host-load-sensitivity`).** Batches A-G rebuild the runtime library only (minutes). **Batch H rebuilds every generated unit**: it runs detached, never while a game launch runs, never beside two other C++-building agents, and when the owner is at the desk it waits for a window the owner names.

- **Subagents (owner 2026-09-17).** Bounded mechanical work goes to Opus subagents with an exact brief and a verification command; judgment stays with the controller. Each task below is marked **[Opus]** (the code and tests are written out; the brief is "make this text work and these cases pass, change nothing else") or **[Judgment]** (needs a build on the host, a gate, a read of a log, or a decision). A subagent never decides whether a bar is met, never writes `docs/KNOWN.md`, never commits, never pushes, and never starts a launch or a full rebuild.

- **Line numbers** are the numbers at `8e5d778` (the branch tip when this was written). Before starting a task, `git diff 8e5d778 -- <the task's files>` and reconcile, saying so in the ledger. Every edit below also names the **text** it replaces, so a moved line is found by `grep -an`.

- **Test baselines.** **Record `P` (Python `Ran N tests`) and `B` (C++ `Total Tests:`) in the ledger before Task 1.** Each task states what it adds.

- **The launch budget.** Spec §4: one gate per runtime commit. This goal has about fourteen runtime commits and spends **four launches**: `s9_g3_batches_gate` (Task 5, one gate for all eight no-behaviour-change batches, R157), `s9_g3_gating_gate` (Task 7, which also covers Task 6's deletions, R158), `s9_g3_poisoned_env` (Task 7, 90 seconds, no harness) and one online control round `s9_g3_control` (Task 7, R166). A failed gate triggers the bisect in Task 5 Step 5 (at most four more gates). A sixth launch of any other kind needs the controller's say-so in the ledger.

### The command set (use these verbatim)

```bash
# --- suites (Windows host, Git Bash, repo root) ---
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
python -m unittest tools_py.tests.<module> -v          # one Python module
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "<what>" -- ./build.sh test
bash scripts/check_quiet_gate.sh                       # answers whether a suite or a build may run now

# --- will this build touch generated code? (must print 0 for batches A-G) ---
cmake --build third_party/ps2recomp/build-clang --target ps2EntryRunner -- -n | grep -c "Unity/unity_"

# --- the runtime (dist/socom2.exe), detached ---
scripts/run_detached.sh --owner build --purpose build logs/s9_g3_build.sh logs/s9_g3_build.marker
cat logs/s9_g3_build.marker 2>/dev/null || echo running        # poll the marker, never the tool call

# --- a gate ---
scripts/run_detached.sh --owner gate --purpose launch logs/s9_g3_<stamp>.sh logs/s9_g3_<stamp>.marker

# --- the registry ---
python -m tools_py.knobs write        # regenerate docs/KNOBS.md from knobs.h
python -m tools_py.knobs check        # exit 1 when docs/KNOBS.md is stale or the source and the registry disagree
python -m tools_py.knobs sites        # every PS2X_* literal with file:line, for the ledger

# --- Linux (the VM) ---
scripts/vm_sync.sh tree && scripts/vm_sync.sh ssh 'cd ~/socom_pc && bash scripts/build_linux.sh test'
```

`logs/s9_g3_build.sh` (created in Task 5; `logs/` is git-ignored, so it is never committed):

```bash
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
./build.sh runtime > logs/s9_g3_build.log 2>&1
rc=$?
echo "done $rc" > logs/s9_g3_build.done
exit $rc
```

`logs/s9_g3_batches_gate.sh` (`logs/s9_g3_gating_gate.sh` is the same file with the stamp changed). Note what it does **not** export: no `PS2X_*` at all — the gate sets its own (R163 b):

```bash
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:$HOME/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
for v in $(compgen -e | grep -E '^PS2X_'); do unset "$v"; done
python -m tools_py.parity.gate --stamp s9_g3_batches_gate --owner gate
rc=$?
echo "done $rc" > logs/s9_g3_batches_gate.done
exit $rc
```

## Global Constraints

- Branch `sprint-9`, in the main checkout, never a worktree.
- **TDD, with RED watched.** Every step that adds behaviour names the case that fails before it and passes after, and the exact failure text; the implementer runs the RED and pastes its output into the ledger before writing the implementation. The migration batches (Task 4) add no behaviour; their RED is `test_knobs_registry`'s pending-file check, which fails the moment a file is taken off the pending list while it still holds a raw read.
- **Never `git add -A`, never `git add .`.** Every commit is `git add <paths>` for new files followed by `git commit -m "…" -- <paths>` with the explicit pathspec given in the task. **`server/config/simulated.db` is never staged. `ONBOARDING.md` is never staged.** `vm/`, `dist/`, `dist-release/`, `logs/` are git-ignored and nothing under them is ever staged. The untracked `*.bin` / `*.wav` files in the repo root and in `third_party/ps2recomp/` are not this goal's. Never stage a file another running agent is editing (memory: commit-only-idle-files) — today that is Goal 8's `bug_report.*`, `bug_report_tests.cpp` and whatever else `git status` shows modified that this plan did not modify.
- Commit trailer, every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **`./build.sh test` exit 0 on the Windows host before every commit** touching `third_party/ps2recomp/`, `tools_py/` or `scripts/`.
- **Push rule (R157).** Tasks 1-3 push after each commit (no runtime behaviour, and Task 3's only runtime edit is a log line and a flag). **Task 4's eight commits are made locally and pushed together only after Task 5's gate is PASS 3/3.** Task 6's commit is local until Task 7's gate; Task 7 pushes after its gate. If the session must end with unpushed batch commits, say so at the top of the ledger with the list of hashes.
- **No builds and no suites while a game launch runs** (`logs/.quiet`; `bash scripts/check_quiet_gate.sh`).
- **Windows and Linux both.** Every C++ edit compiles on both (no Win32-only call outside an `#ifdef _WIN32`); `_putenv_s`/`setenv` pairs in tests follow the existing pattern in `bare_run_tests.cpp:111-117`. CI (`.github/workflows/linux.yml`, `--no-runner`) builds `ps2x_shared`, the launcher and `ps2x_tests` and runs the Python suite: **`test_knobs_registry` runs in CI** (it needs no build), so a knob added without a registry row fails the push.
- **No behaviour change before Task 6.** Tasks 1-5 leave every knob doing exactly what it does at `8e5d778`: `ps2x::knob` is `std::getenv` while enforcement is off, the five DEAD names are registered as Dev until Task 6 deletes them, and the only observable difference is the `[knobs]` line in the log and a `--dev` argument that is accepted and does nothing.
- **No new `PS2X_*` name except `PS2X_DEV`.**
- LF line endings in every new file. **Python tests are `unittest`, never pytest**, live in `tools_py/tests/`, and have no module-level `def test_` (`tools_py/tests/test_test_hygiene.py`).

---

## The inventory (the plan's core artefact)

134 names read by the shipped executables at `8e5d778`. **Verdict**: SHIPPING = a player-facing setting with a `launcher::Config` field behind it, honoured always; DEV = a probe, trace, dump or A/B switch, honoured only in developer mode after Task 7; **DEAD** = deleted in Task 6 (evidence below the table). **Kind**: `Flag` is read with `ps2x::knobOn` (the one rule); `Presence` means any value — including `0` — switches it on (R161 moves eight of these to `Flag` in Task 7: `PS2X_GIF_PRIORITY_SORT`, `PS2X_GS_NO_DIRTY_REFRESH`, `PS2X_GS_NO_TEX_REVALIDATE`, `PS2X_GS_NO_ZTEST`, `PS2X_VIF1_NO_IRQ_STALL`, `PS2X_VU1_FMAC_CHECK`, `PS2X_VU1_XGKICK_CYCLE_EXACT`, and `PS2X_SOCOM2_PAD`, which also starts defaulting to on); `Int`/`Float`/`Text`/`Path`/`Spec` are parsed at the site. **Read sites**: file names are unique in the tree (`main.cpp` with three reads at `:253/:256/:276` is `ps2xRuntime/src/main.cpp`; `main.cpp:730` is `ps2xLauncher/src/main.cpp`); a `C` site that runs once at start-up (constructors, `install*`, `initialise`, `loadHosts`) is left as it is — the hot ones are Handoff note 6. **Set by**: "launcher, bare run" is `launcher::environmentFor` (`launcher_config.cpp:405-451`), which `BareRun::plan` reuses; "operator" means a person types it, and the tool named reads the output. The one-line meaning of every name is the registry row in Task 1.

**Names built at run time:** none is concatenated. Seven helpers take the name as a parameter, and their call sites carry the literal: `GSGlBackend::traceSkip(const char *env)` (`gs_gl_backend.cpp:1339`, an 8-entry cache, called with `PS2X_GS_TRACE_PRESENT`, `PS2X_GS_TRACE_CMDS`, `PS2X_GS_DUMP_TEX_FROM`), `WavSink{knob, what}` (`host_mic.cpp:453`, `PS2X_MIC_GAMEREAD_DUMP`, `PS2X_MIC_DUMP_PLAYBACK`), `HleStats` `envOn(name)` (`HleStats.cpp:46`), libnetb `envFlag(name, dflt)` (`socom2_libnetb.cpp:79`), `envCeiling(name, fallback)` (`socom2_dispatch_0x1b50.cpp:662`), `BareRun::applyEnvironment` (`bare_run.cpp:77`, any key out of `environmentFor`), and `launcher::bugreport::kApiBaseEnv` (Handoff note 2). Pure parsers that are handed the value, not the name: `GsPendingCap::parseCapMb`, `GsFrameBackpressure::parseMaxPendingFrames`, `GsGlDepth::legacyRequested`, `GsGlCaps::evaluate`, `hostGamepadSelect`, `hostGamepadAllowed`, `crouchShortcutFromEnv`, `ps2_window::parseWindowSize`, `traceBlockList`.

| Name | Verdict | Kind | Default | Read sites (`S` once into a static, `C` on each call of that line) | Set by |
|---|---|---|---|---|---|
| `PS2X_AUDIO_DUMP` | DEV | Path | unset | `ps2_audio.cpp:397C` | operator (audio_corr.py reads it) |
| `PS2X_AUDIO_PCM_DUMP` | DEV | Path | unset | `ps2_audio.cpp:587C` | - |
| `PS2X_AUDIO_TRACE` | DEV | Presence | unset | `ps2_audio.cpp:516S` | - |
| `PS2X_AUDIO_VOLUME` | SHIPPING | Int | `100` | `ps2_audio.cpp:525C` | launcher, bare run |
| `PS2X_CALL_TRACE` | DEV | Spec | unset | `game_overrides_socom2.cpp:1294C` | env.sh, online_match_ours, freeze_trace, sim_walk_to_b |
| `PS2X_CALL_TRACE_DUMP` | DEV | Spec | unset | `game_overrides_socom2.cpp:1221S` | - |
| `PS2X_CALL_TRACE_EVERY` | DEV | Int | `500` | `game_overrides_socom2.cpp:1139C` | env.sh (10), online_match_ours |
| `PS2X_CD_IMAGE` | SHIPPING | Path | unset | `game_overrides_socom2.cpp:557C` `main.cpp:253C` | launcher, bare run, drive.py, hostplatform |
| `PS2X_CD_TRACE` | DEV | Presence | unset | `CD.cpp:12S` `FileIO.cpp:100S` | - |
| `PS2X_CLOCK_CAP_MS` | DEV | Float | `100` | `EeScheduler.cpp:465C` | - |
| `PS2X_CLOCK_EXCLUDE` | DEV | Int | `0` | `EeScheduler.cpp:423S` | - |
| `PS2X_CLOCK_TRACE` | DEV | Presence | unset | `EeScheduler.cpp:483S` | - |
| `PS2X_CULL_PARTIAL_CLIP` | DEV | Int | `0` | `game_overrides_socom2.cpp:1443S` `game_overrides_socom2.cpp:1737C` | - |
| `PS2X_CULL_TRACE` | DEV | Spec | unset | `game_overrides_socom2.cpp:1734C` | operator (tools_py/research/terrain) |
| `PS2X_CYCLE_CLOCK` | DEV | Text | unset | `EeScheduler.cpp:418S` `EeScheduler.cpp:2295S` | - |
| `PS2X_DETAIL_FAR` | DEV | Int | `0` | `game_overrides_socom2.cpp:1570S` | - |
| `PS2X_EE_ROUND` | DEV | Text | unset | `ps2_runtime.cpp:2549C` | - |
| `PS2X_FPS_OVERLAY` | SHIPPING | Int | `0` | `ps2_runtime.cpp:2810C` | launcher, bare run |
| `PS2X_FPU_TRAP` | DEV | Float | `-1` | `ps2_runtime_macros.h:785S` | - |
| `PS2X_FRAME_DUMP` | DEV | Path | unset | `gs_frontend.cpp:656S` `gs_gl_backend.cpp:982S` `ps2_vu1_core.cpp:953C` `ps2_vu1_core.cpp:2407C` `ps2_vu1_core.cpp:2422C` | - |
| `PS2X_GIF_DUMP` | DEV | Spec | unset | `gs_frontend.cpp:781S` `gs_frontend.cpp:1012C` | operator (research/terrain) |
| `PS2X_GIF_PRIORITY_SORT` | DEV | Presence | unset | `ps2_gif_arbiter.cpp:22S` | - |
| `PS2X_GIF_TRACE` | DEV | Int | `0` | `ps2_memory.cpp:2019S` | operator (gif_submit_timeline.py) |
| `PS2X_GS_BACKEND` | DEV | Text | `gpu` | `gs_frontend.cpp:12C` | ps2x_tests main, vu1_replay |
| `PS2X_GS_DEPTH_LEGACY` | DEV | Int | `0` | `gs_gl_backend.cpp:1115C` | - |
| `PS2X_GS_DUMP_DISPLAY` | DEV | Spec | unset | `gs_gl_backend.cpp:2732S` | operator (movie_blocks.py) |
| `PS2X_GS_DUMP_TEX` | DEV | Path | unset | `gs_gl_backend.cpp:3127S` `gs_gl_backend.cpp:3191S` | - |
| `PS2X_GS_DUMP_TEX_EVERY` | DEV | Int | `1` | `gs_gl_backend.cpp:3198S` | - |
| `PS2X_GS_DUMP_TEX_FROM` | DEV | Int | unset | `gs_gl_backend.cpp:3200S` `gs_gl_backend.cpp:3203S` | - |
| `PS2X_GS_DUMP_TEX_MAX` | DEV | Int | `6` | `gs_gl_backend.cpp:3199S` | - |
| `PS2X_GS_DUMP_TEX_TBP0` | DEV | Spec | unset | `gs_gl_backend.cpp:3197S` | - |
| `PS2X_GS_GL_DEBUG_AFTER` | DEV | Int | `0` | `gs_gl_backend.cpp:3128S` `gs_gl_backend.cpp:3193S` `gs_gl_backend.cpp:3795S` | - |
| `PS2X_GS_GL_DEBUG_NODEPTH` | **DEAD** | Presence | unset | `gs_gl_backend.cpp:3843S` | - |
| `PS2X_GS_GL_DEBUG_PSM` | DEV | Int | `-1` | `gs_gl_backend.cpp:3792S` | - |
| `PS2X_GS_GL_FORCE_FAIL` | DEV | Text | unset | `gs_gl_caps.h:100C` | - |
| `PS2X_GS_MAX_PENDING_FRAMES` | DEV | Int | `3` | `gs_gl_backend.cpp:686C` | operator (ladder rung-0 A/B) |
| `PS2X_GS_NO_DIRTY_REFRESH` | DEV | Presence | unset | `gs_gl_backend.cpp:2113S` | - |
| `PS2X_GS_NO_TEX_REVALIDATE` | DEV | Presence | unset | `gs_gl_backend.cpp:3395S` | - |
| `PS2X_GS_NO_ZTEST` | DEV | Presence | unset | `gs_gl_backend.cpp:3637S` | - |
| `PS2X_GS_PENDING_CAP_MB` | DEV | Int | `64` | `gs_gl_backend.cpp:683C` | - |
| `PS2X_GS_PENDING_HARD_CAP_MB` | DEV | Int | `1024` | `gs_gl_backend.cpp:684C` | - |
| `PS2X_GS_PROBE` | **DEAD** | Int | `-1` | `gs_gl_backend.cpp:3886S` | - |
| `PS2X_GS_RT_TEXTURE` | DEV | Int | `1` | `gs_gl_backend.cpp:3301S` | - |
| `PS2X_GS_SCALE` | SHIPPING | Int | `1` | `gs_gl_backend.cpp:104C` | launcher, bare run |
| `PS2X_GS_SCALE_FILTER` | DEV | Text | unset | `gs_gl_backend.cpp:492C` | - |
| `PS2X_GS_SCALE_SELFTEST` | DEV | Int | `0` | `gs_gl_backend.cpp:516C` | - |
| `PS2X_GS_SKIP_TBP0` | DEV | Spec | unset | `gs_gl_backend.cpp:1570S` | - |
| `PS2X_GS_STATS` | DEV | Presence | unset | `gs_gl_backend.cpp:1392S` | ladder_frostfire.sh, online_ladder, online_match_ours |
| `PS2X_GS_TEX_FROM_CPU` | **DEAD** | Presence | unset | `gs_gl_backend.cpp:3080S` | - |
| `PS2X_GS_TRACE_CMDS` | DEV | Int | unset | `gs_gl_backend.cpp:1404S` `gs_gl_backend.cpp:1460S` | - |
| `PS2X_GS_TRACE_CMDS_BOX` | DEV | Spec | unset | `gs_gl_backend.cpp:1477S` | - |
| `PS2X_GS_TRACE_CMDS_FROM` | DEV | Int | `-1` | `gs_gl_backend.cpp:1458S` | - |
| `PS2X_GS_TRACE_CMDS_MAX` | DEV | Int | `4000` | `gs_gl_backend.cpp:1457S` | - |
| `PS2X_GS_TRACE_CMDS_PER_FRAME` | DEV | Int | `0` | `gs_gl_backend.cpp:1467S` | - |
| `PS2X_GS_TRACE_CMDS_TBP0` | DEV | Spec | unset | `gs_gl_backend.cpp:1466S` | - |
| `PS2X_GS_TRACE_DIRTY` | DEV | Int | `-1` | `gs_gl_backend.cpp:2079S` | - |
| `PS2X_GS_TRACE_DISPFB` | DEV | Presence | unset | `gs_gl_backend.cpp:2275S` `gs_gl_backend.cpp:2927S` | - |
| `PS2X_GS_TRACE_PAGES` | DEV | Spec | unset | `gs_gl_backend.cpp:124S` | - |
| `PS2X_GS_TRACE_PRESENT` | DEV | Int | `-1` | `gs_gl_backend.cpp:1409C` `gs_gl_backend.cpp:1993C` `gs_gl_backend.cpp:2122C` `gs_gl_backend.cpp:2540C` `gs_gl_backend.cpp:2706S` `gs_gl_backend.cpp:2902S` `gs_gl_backend.cpp:3038C` | - |
| `PS2X_GS_UPLOAD_TRACE` | DEV | Presence | unset | `gs_gl_backend.cpp:771S` `gs_gl_backend.cpp:1396S` `gs_gl_backend.cpp:1949S` `gs_gl_backend.cpp:2035S` `gs_gl_backend.cpp:2111S` `gs_gl_backend.cpp:3281S` | - |
| `PS2X_HLE_STATS` | DEV | Flag | `0` | `HleStats.cpp:144S` | - |
| `PS2X_HLE_STATS_PERIOD` | DEV | Int | `30` | `HleStats.cpp:320C` | - |
| `PS2X_HLE_STATS_TOML` | DEV | Path | `recomp/socom2.toml` | `HleStats.cpp:287C` | - |
| `PS2X_HOST_GAMEPAD` | DEV | Int | `1` | `host_gamepad.h:20S` | gate.py, env.sh |
| `PS2X_HOST_GAMEPAD_INDEX` | SHIPPING | Int | unset | `Pad.cpp:94C` `ps2_pad.cpp:45C` `socom2_host_input.cpp:232C` `socom2_host_input.cpp:314C` | launcher, bare run |
| `PS2X_HOST_PROF` | DEV | Float | unset | `game_overrides_socom2.cpp:2059C` `game_overrides_socom2.cpp:2268C` `game_overrides_socom2.cpp:2415C` | operator (hostprof_*.py read its file) |
| `PS2X_HOST_PROF_ALL` | DEV | Presence | unset | `game_overrides_socom2.cpp:2068C` `game_overrides_socom2.cpp:2274C` | - |
| `PS2X_HOST_PROF_MAIN` | DEV | Presence | unset | `game_overrides_socom2.cpp:2070C` `game_overrides_socom2.cpp:2275C` | - |
| `PS2X_HOST_PROF_OUT` | DEV | Path | `logs/hostprof.txt` | `game_overrides_socom2.cpp:2063C` `game_overrides_socom2.cpp:2272C` | - |
| `PS2X_HOST_PROF_STACKS` | DEV | Presence | unset | `game_overrides_socom2.cpp:2086C` `game_overrides_socom2.cpp:2276C` | - |
| `PS2X_HOST_SCREENSHOT` | DEV | Spec | unset | `ps2_runtime.cpp:2839S` | - |
| `PS2X_HOST_SCREENSHOT_LATEST` | DEV | Path | unset | `ps2_runtime.cpp:2787S` | drive.py, online_login_ours, scale_shot, sp_death_probe |
| `PS2X_JALR_TRACE` | DEV | Spec | unset | `ps2_runtime.cpp:1415C` | - |
| `PS2X_LAUNCHER_SHOT` | DEV | Path | unset | `main.cpp:730C` | - |
| `PS2X_LOD_SCALE` | DEV | Float | `0` | `game_overrides_socom2.cpp:1421S` | - |
| `PS2X_MC_DIR` | SHIPPING | Path | unset | `ps2_runtime.cpp:1092C` `ps2_runtime.cpp:1116C` `main.cpp:256C` | launcher, bare run, gate.py, online_login_ours (B) |
| `PS2X_MC_DIR_SLOT1` | DEV | Path | unset | `MemoryCard.cpp:128C` | - |
| `PS2X_MC_TRACE` | DEV | Presence | unset | `MemoryCard.cpp:1053C` `MemoryCard.cpp:1390C` | operator (mc_trace.py reads the log) |
| `PS2X_MIC_DEVICE` | SHIPPING | Text | unset | `host_mic.cpp:585C` | launcher, bare run |
| `PS2X_MIC_DUMP` | DEV | Path | unset | `host_mic.cpp:608C` | - |
| `PS2X_MIC_DUMP_PLAYBACK` | DEV | Path | unset | `host_mic.cpp:540C` | - |
| `PS2X_MIC_FAKE` | DEV | Path | unset | `host_mic.cpp:584C` | operator (voice rounds) |
| `PS2X_MIC_GAMEREAD_DUMP` | DEV | Path | unset | `host_mic.cpp:539C` | operator (voice rounds), ps2x_tests |
| `PS2X_MPEG_PIC_TRACE` | **DEAD** | Presence | unset | `MPEG.cpp:2269S` `MPEG.cpp:2928S` | - |
| `PS2X_MPEG_TRACE` | DEV | Presence | unset | `MPEG.cpp:34S` `snd989.cpp:395S` `snd989.cpp:983S` | - |
| `PS2X_PACK_TRACE` | DEV | Path | unset | `game_overrides_socom2.cpp:1675C` | - |
| `PS2X_PAD_CROUCH_SHORTCUT` | SHIPPING | Text | `off` | `socom2_host_input.cpp:331S` | launcher, bare run |
| `PS2X_PAD_DEADZONE` | SHIPPING | Float | `0.15` | `host_gamepad_select.h:44C` | launcher, bare run |
| `PS2X_PC_SAMPLER` | DEV | Float | unset | `game_overrides_socom2.cpp:680C` | gate.py (1), env.sh (0.25), sp_death_probe, freeze_trace |
| `PS2X_PEEK` | DEV | Spec | unset | `game_overrides_socom2.cpp:718C` | gate.py (guest probe), env.sh, mixed_match.sh, online_match_ours, sp_death_probe, sim_walk_to_b |
| `PS2X_PRESENT_FILTER` | SHIPPING | Text | `linear` | `ps2_runtime.cpp:2680C` | launcher, bare run |
| `PS2X_RDRAM_DUMP` | DEV | Spec | unset | `game_overrides_socom2.cpp:864C` | operator (rdr_tree.py, ee_compare.py) |
| `PS2X_RDRAM_DUMP_AT` | DEV | Spec | unset | `game_overrides_socom2.cpp:848C` | - |
| `PS2X_SND_STREAM_WORKER` | DEV | Int | `1` | `snd989_mixer.cpp:573C` | ps2x_tests |
| `PS2X_SOCOM2_HOSTS` | DEV | Spec | unset | `socom2_hostnet.cpp:222C` | - |
| `PS2X_SOCOM2_INPUT_FILE` | DEV | Path | unset | `socom2_host_input.cpp:420S` | drive.py (Linux), online_login_ours, sp_death_probe, x11shot |
| `PS2X_SOCOM2_INPUT_SCRIPT` | DEV | Spec | unset | `socom2_host_input.cpp:228C` | - |
| `PS2X_SOCOM2_INPUT_TRACE` | DEV | Presence | unset | `socom2_host_input.cpp:442S` | env.sh, sp_death_probe |
| `PS2X_SOCOM2_MOUSE` | SHIPPING | Int | `0` | `socom2_host_input.cpp:224C` | launcher, bare run |
| `PS2X_SOCOM2_MOUSE_SENS` | SHIPPING | Float | `4` | `socom2_host_input.cpp:226C` | launcher, bare run |
| `PS2X_SOCOM2_NET_STATS` | DEV | Flag | `1` | `socom2_libnetb.cpp:99C` | ps2x_tests |
| `PS2X_SOCOM2_NET_TRACE` | DEV | Presence | unset | `game_overrides_socom2.cpp:190C` `socom2_libnetb.cpp:74C` | - |
| `PS2X_SOCOM2_NET_TRACE_ALL` | DEV | Flag | `0` | `socom2_libnetb.cpp:105S` | - |
| `PS2X_SOCOM2_NET_TRACE_PEERS` | DEV | Int | `16` | `socom2_libnetb.cpp:120C` | - |
| `PS2X_SOCOM2_PAD` | SHIPPING | Presence | unset | `game_overrides_socom2.cpp:280S` | launcher, bare run, drive.py, online_login_ours |
| `PS2X_SOCOM2_PAD_TRACE` | DEV | Presence | unset | `game_overrides_socom2.cpp:299C` `game_overrides_socom2.cpp:348S` `game_overrides_socom2.cpp:375S` | - |
| `PS2X_SOCOM2_RSA_KEY` | SHIPPING | Text | `a` | `game_overrides_socom2.cpp:80C` | launcher (second instance), online_login_ours (B) |
| `PS2X_SOCOM2_SERVER` | SHIPPING | Text | `127.0.0.1` | `socom2_hostnet.cpp:211C` | launcher, bare run, env.sh |
| `PS2X_SOCOM2_UDP_SHIFT` | SHIPPING | Int | `0` | `game_overrides_socom2.cpp:1354C` `socom2_libnetb.cpp:220S` | launcher (second instance), online_login_ours (B) |
| `PS2X_TIMER_TRACE` | **DEAD** | Presence | unset | `ps2_memory.cpp:2410S` | - |
| `PS2X_TRACE_FIFO` | DEV | Presence | unset | `EeScheduler.cpp:1398S` `ps2_memory.cpp:12S` `ps2_vif1_interpreter.cpp:42C` `ps2_vif1_interpreter.cpp:328C` `ps2_vif1_interpreter.cpp:382C` `ps2_vif1_interpreter.cpp:871C` | operator (marker_timeline.py, patch_fifo_trace.py) |
| `PS2X_TRACE_VIF` | DEV | Spec | unset | `ps2_memory.cpp:1480S` `ps2_vif1_interpreter.cpp:387S` | - |
| `PS2X_TRACE_VU` | DEV | Int | unset | `ps2_runtime.cpp:672C` `ps2_vu1_core.cpp:2358S` `ps2_vu1_core.cpp:2361S` | vu1_replay --trace |
| `PS2X_TRACE_VU_FLAGS` | DEV | Presence | unset | `ps2_vu1_lower.cpp:249S` | - |
| `PS2X_TRACE_VU_STEPS` | DEV | Int | `1200` | `ps2_vu1_core.cpp:2597S` | - |
| `PS2X_TRIGGER` | DEV | Spec | unset | `game_overrides_socom2.cpp:811S` | - |
| `PS2X_VIF1_NO_IRQ_STALL` | DEV | Presence | unset | `ps2_vif1_interpreter.cpp:24S` | - |
| `PS2X_VU0_FAST` | DEV | Int | `1` | `ps2_vu1_core.cpp:2468S` | - |
| `PS2X_VU1_BAILHIST` | DEV | Presence | unset | `ps2_vu1_core.cpp:2560S` | operator (vu1stats_summary.py) |
| `PS2X_VU1_DUMP` | DEV | Path | unset | `ps2_vu1_core.cpp:2309S` | operator (vu1dis.py, fixtures) |
| `PS2X_VU1_DUMP_AFTER` | DEV | Float | `0` | `ps2_vu1_core.cpp:2313S` | - |
| `PS2X_VU1_FAST` | DEV | Int | `1` | `ps2_vu1_core.cpp:2465S` | ps2x_tests main, vu1_replay |
| `PS2X_VU1_FMAC_CHECK` | DEV | Presence | unset | `ps2_vu1_upper.cpp:98S` | - |
| `PS2X_VU1_GEN` | DEV | Int | `1` | `ps2_vu1_core.cpp:2470S` | vu1_replay |
| `PS2X_VU1_HOST_DRAW` | DEV | Int | `0` | `socom2_dispatch_0x1b50.cpp:1816C` | vu1_replay (always explicit) |
| `PS2X_VU1_NATIVE` | DEV | Int | `1` | `ps2_vu1_core.cpp:2475S` | vu1_replay --native/--no-native, ps2x_tests |
| `PS2X_VU1_NATIVE_TEST_CEILING` | DEV | Int | unset | `socom2_dispatch_0x1b50.cpp:675S` `socom2_dispatch_0x1b50.cpp:681S` | build.sh test (run 8) |
| `PS2X_VU1_NATIVE_TEST_CLIP_CEILING` | DEV | Int | unset | `socom2_dispatch_0x1b50.cpp:688C` | build.sh test (run 9) |
| `PS2X_VU1_XGKICK_CYCLE_EXACT` | DEV | Presence | unset | `socom2_dispatch_0x1b50.cpp:926S` `ps2_vu1_core.cpp:1077S` | ps2x_tests main |
| `PS2X_VU_STATS` | DEV | Presence | unset | `ps2_vu1_core.cpp:2817S` | operator (vu1stats_summary.py) |
| `PS2X_WATCH` | DEV | Spec | unset | `game_overrides_socom2.cpp:591C` | - |
| `PS2X_WATCH_HUGE` | DEV | Spec | unset | `game_overrides_socom2.cpp:608C` | - |
| `PS2X_WINDOW_SIZE` | SHIPPING | Text | `640x448` | `ps2_runtime.cpp:766C` | launcher, bare run, scale_shot.py |
| `PS2X_WINDOW_TITLE` | DEV | Text | unset | `host_mic.cpp:548C` `main.cpp:276C` | online_login_ours (A, B), ps2x_tests |

**Beyond the 134.** Test-only, registered as class `Test` so the scan covers `ps2xTest` too: `PS2X_TEST_SUITE`, `PS2X_TEST_SKIP` (`MiniTest.h:134,153`), `PS2X_CONSOLE_REPLAY_DIR`/`_STOP`/`_FBP`/`_GL`/`_PIXEL` (`ps2_gs_tests.cpp:1535-1576`; Goal 6 decides whether that test lives), `PS2X_PK_REPLAY` (`ps2_gs_tests.cpp:1758`). Harness-only, never read by C++, listed in `tools_py/knobs.py` `HARNESS_ONLY`: `PS2X_RUN_LOG`, `PS2X_TEST_REPEAT`, `PS2X_SOCOM2_RSA_KEY_B`. Test fixtures that are not knobs: `PS2X_BARE_TEST_KEPT`, `PS2X_BARE_TEST_NEW` (`bare_run_tests.cpp`). New: `PS2X_DEV` (class `Switch`).

**The five DEAD verdicts, with their evidence** (R159; each is the controller's to overturn into a DEV row at no cost before Task 6):

| Name | Evidence |
|---|---|
| `PS2X_GS_TEX_FROM_CPU` | The project's own record retires it: `docs/STATUS.md:289` — "two instruments retired: the CPU-VRAM twin `PS2X_GS_TEX_FROM_CPU=1` renders noise on every screen from the boot on and drops to a frame every few seconds (`s6_water_texcpu2`; research/31 §7) — it cannot tell VRAM bytes from cache." It snapshots 4 MiB of VRAM on every texture decode. No script, tool or test names it. |
| `PS2X_GS_PROBE` | A one-investigation probe with the investigation's constants compiled in: frame buffer `0x8c`, rows 200/420/440 at x=320, untextured sprites only ("the movie strip investigation, 2026-09-09", fixed by `refreshDirtyRows`, `gs_gl_backend.cpp:2270-2274`). `docs/research/14-gs-render-target-scale-spike.md:167` records that it samples the wrong place at any scale above 1. `PS2X_GS_DUMP_DISPLAY` answers the same question for any buffer. No script, tool or test names it. |
| `PS2X_GS_GL_DEBUG_NODEPTH` | Named nowhere outside its own line: no document, script, tool or test (`git grep -aw` finds one hit). Introduced by `8653933` (2026-09-07) to bisect the culled-glyph bug that commit fixed. It sits inside the `PS2X_GS_GL_DEBUG_PSM` print and disables `GL_DEPTH_TEST` for the draw being *inspected*, so switching it on changes the picture the print is describing. |
| `PS2X_MPEG_PIC_TRACE` | Named nowhere outside its two identical blocks (`MPEG.cpp:2269`, `:2928`). Introduced by `2d23351` (2026-09-08, "the mission intro movie plays") and never documented; `PS2X_MPEG_TRACE` logs the same picture events with more fields. |
| `PS2X_TIMER_TRACE` | Named nowhere outside `ps2_memory.cpp:2410`. Same commit, same closed bug. It sits on the EE timer-count read, which the game's frame pacer polls in a busy loop; `PS2X_CLOCK_TRACE` reports T0 against host time once a second from the scheduler instead. |

Considered and **kept as DEV**: `PS2X_PACK_TRACE` (no reference anywhere, but it is one of the terrain hooks of `9c38aff` and the terrain holes are an open owner priority); `PS2X_CYCLE_CLOCK` (`docs/KNOWN.md:270` says it is "not an A/B of the pre-R54 path" — a working alternate mode with a misleading name, which is a documentation defect, fixed in its registry row); `PS2X_GS_GL_DEBUG_PSM` (native-coordinate probes wrong above scale 1, said in its row); `PS2X_HOST_SCREENSHOT` (superseded for the harness by `_LATEST`, still the documented way to keep a series); `PS2X_LOD_SCALE`, `PS2X_DETAIL_FAR`, `PS2X_CULL_PARTIAL_CLIP` (terrain experiments that write guest memory — exactly what must be DEV); `PS2X_HLE_STATS_PERIOD`/`_TOML`, `PS2X_GS_DUMP_TEX_EVERY`/`_FROM`/`_MAX` (undocumented parameters of documented probes).

---

## File map

| Path | Responsibility |
|---|---|
| `ps2xShared/include/ps2x/knobs.h` (new), `ps2xShared/src/knobs.cpp` (new), `ps2xShared/CMakeLists.txt`, `ps2xTest/src/knobs_tests.cpp` (new), `ps2xTest/CMakeLists.txt`, `ps2xTest/src/main.cpp` | **Task 1 [Opus]**: the registry that is the accessor's table; enforcement off |
| `tools_py/knobs.py` (new), `tools_py/tests/test_knobs_registry.py` (new), `docs/KNOBS.md` (new, generated) | **Task 2 [Opus]**: the generated table and the test that holds the source to it |
| `ps2xRuntime/src/main.cpp`, `ps2xTest/src/main.cpp`, `ps2xRuntime/src/tools/vu1_replay.cpp`, `run.sh`, `scripts/parity/env.sh`, `tools_py/parity/hostplatform.py`, `tools_py/parity/drive.py`, `tools_py/parity/scale_shot.py`, `tools_py/tests/test_hostplatform.py`, `tools_py/tests/test_run_sh_exe.py` | **Task 3 [Opus]**: `--dev`, the `[knobs]` line, and developer mode in every launcher of the runner — while it still changes nothing |
| the 32 files of the inventory, `ps2xIOP/CMakeLists.txt`, `tools_py/knobs.py` (`RAW_GETENV_PENDING`) | **Task 4 [Opus] x8**: batches A1, A2, B, C, D, E, F, then H |
| `logs/s9_g3_build.sh`, `logs/s9_g3_batches_gate.sh` (ignored) | **Task 5 [Judgment]**: build, one gate, push — or bisect |
| `gs_gl_backend.cpp`, `MPEG.cpp`, `ps2_memory.cpp`, `ps2_vu1_core.cpp`, `knobs.h`, `README.md`, `docs/KNOBS.md` | **Task 6 [Opus]**: the five deletions and the two ghosts |
| `knobs.cpp`, `knobs.h`, nine switch sites, `game_overrides_socom2.cpp`, `launcher_config.{h,cpp}`, `win32_glue.cpp`, `posix_glue.cpp`, `diagnostics.{h,cpp}`, `knobs_tests.cpp`, `launcher_tests.cpp`, `diagnostics_tests.cpp`, `tools_py/tests/test_knobs_line.py` (new), `logs/s9_g3_gating_gate.sh`, `logs/s9_g3_poisoned_env.sh` | **Task 7 [Judgment]**: the flip, its gate, the poisoned launch, the control round |
| the VM | **Task 8 [Judgment]**: the Linux ring |
| `README.md`, `docs/HANDOFF.md`, `docs/KNOWN.md`, `docs/STATUS.md`, `docs/CURRENT_SPRINT.md`, this plan | **Task 9 [Judgment]**: close-out |

All paths in this table and below that start with `ps2x` are under `third_party/ps2recomp/`. Task 2 needs Task 1's header. Task 3 needs 1. Task 4 needs 1-3. Tasks 1 and 2 compile no generated code and can run beside one other C++-building agent.

---

## Task 1 — The registry that is the accessor's table  **[Opus]**

**Files:**
- Create: `third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h`, `third_party/ps2recomp/ps2xShared/src/knobs.cpp`, `third_party/ps2recomp/ps2xTest/src/knobs_tests.cpp`
- Modify: `third_party/ps2recomp/ps2xShared/CMakeLists.txt` (the `add_library` list), `third_party/ps2recomp/ps2xTest/CMakeLists.txt` (the `ps2_test_lib` source list, after `src/diagnostics_tests.cpp`), `third_party/ps2recomp/ps2xTest/src/main.cpp` (one declaration, one call)

**Interfaces:**
- `const char *ps2x::knob(const char *name)` — the value, or `nullptr`. Enforcement off (now): exactly `std::getenv(name)`. Enforcement on (Task 7): `nullptr` when unset, **empty** (R162), unregistered, or class Dev outside developer mode. The unset path is one `getenv` and no table search.
- `bool ps2x::knobOn(const char *name, bool dflt = false)` — `dflt` when `knob` is `nullptr` or empty; `false` for `0`, `false`, `off`; `true` otherwise.
- `ps2x::knobs::{Class{Shipping,Dev,Test,Switch}, Kind{Flag,Presence,Int,Float,Text,Path,Spec}, Entry{name,cls,kind,dflt,meaning}, kTable, kTableSize, find(name), className(Class), kindName(Kind), flagValue(value,dflt), devMode(), setDevMode(bool), resetDevModeForTests(), enforcement(), setEnforcement(bool), consumeDevFlag(int&,char**), Pairs, describe(const Pairs&,bool honourDev), startupLine()}`.
- A row's shape is part of the contract (`tools_py/knobs.py` reads it with a regex): `X("PS2X_NAME", Class, Kind, "default", "One line, at most 110 characters, no double quote.")`, rows sorted by name in `strcmp` order.

**Steps:**

- [x] **Step 1: RED.** Create `third_party/ps2recomp/ps2xTest/src/knobs_tests.cpp`: *[done 2026-09-21; RED: fatal error: 'ps2x/knobs.h' file not found]*

```cpp
// Sprint 9 Goal 3: the knob registry -- one table that is the accessor's lookup, the generated docs/KNOBS.md
// and the launcher's list of settings at once.
#include "MiniTest.h"
#include "launcher/launcher_config.h"
#include "ps2x/knobs.h"

#include <cstdlib>
#include <cstring>
#include <set>
#include <string>
#include <vector>

namespace
{
    void setVar(const char *name, const char *value)
    {
#ifdef _WIN32
        _putenv_s(name, value ? value : "");   // an empty value removes the variable on Windows
#else
        if (value)
            setenv(name, value, 1);
        else
            unsetenv(name);
#endif
    }

    // Every case here moves process-wide switches; the suites after this one must find them as they were.
    struct KnobStateGuard
    {
        bool dev = ps2x::knobs::devMode();
        bool enforce = ps2x::knobs::enforcement();
        ~KnobStateGuard()
        {
            ps2x::knobs::setEnforcement(enforce);
            ps2x::knobs::setDevMode(dev);
        }
    };

    const char *kDevName = "PS2X_WATCH_HUGE";             // Dev, read once at start-up by the runner only
    const char *kShippingName = "PS2X_SOCOM2_MOUSE_SENS"; // Shipping, read once by socom2_host_input's initialise
}

void register_knobs_tests()
{
    MiniTest::Case("Knobs", [](TestCase &tc)
    {
        tc.Run("the table: sorted, unique, every row well formed", [](TestCase &t)
        {
            std::set<std::string> seen;
            for (size_t i = 0; i < ps2x::knobs::kTableSize; ++i)
            {
                const ps2x::knobs::Entry &e = ps2x::knobs::kTable[i];
                const std::string name = e.name;
                t.IsTrue(name.rfind("PS2X_", 0) == 0, name + ": starts with PS2X_");
                t.IsTrue(seen.insert(name).second, name + ": appears once");
                if (i > 0)
                    t.IsTrue(std::strcmp(ps2x::knobs::kTable[i - 1].name, e.name) < 0, name + ": sorted after its predecessor (find() is a binary search)");
                const std::string meaning = e.meaning;
                t.IsTrue(!meaning.empty() && meaning.size() <= 110, name + ": a meaning of at most 110 characters");
                t.IsTrue(meaning.find('"') == std::string::npos, name + ": no double quote (tools_py/knobs.py reads the row with a regex)");
            }
            t.IsTrue(ps2x::knobs::kTableSize >= 130u, "the 134 shipped names, the test-only ones and PS2X_DEV");
        });

        tc.Run("find: a registered name, an unregistered one, null", [](TestCase &t)
        {
            const ps2x::knobs::Entry *scale = ps2x::knobs::find("PS2X_GS_SCALE");
            t.IsNotNull(scale, "PS2X_GS_SCALE is registered");
            if (scale)
            {
                t.IsTrue(scale->cls == ps2x::knobs::Class::Shipping, "and is a shipping setting");
                t.Equals(std::string(scale->dflt), std::string("1"), "whose default is 1");
            }
            const ps2x::knobs::Entry *first = ps2x::knobs::find(ps2x::knobs::kTable[0].name);
            const ps2x::knobs::Entry *last = ps2x::knobs::find(ps2x::knobs::kTable[ps2x::knobs::kTableSize - 1].name);
            t.IsTrue(first == &ps2x::knobs::kTable[0], "the first row is found");
            t.IsTrue(last == &ps2x::knobs::kTable[ps2x::knobs::kTableSize - 1], "the last row is found");
            t.IsNull(ps2x::knobs::find("PS2X_NO_SUCH_KNOB"), "an unregistered name is not");
            t.IsNull(ps2x::knobs::find(nullptr), "null is not");
            const ps2x::knobs::Entry *dev = ps2x::knobs::find("PS2X_DEV");
            t.IsTrue(dev != nullptr && dev->cls == ps2x::knobs::Class::Switch, "PS2X_DEV is the switch");
        });

        tc.Run("the flag rule: unset or empty is the default; 0, false, off are false; anything else is true", [](TestCase &t)
        {
            using ps2x::knobs::flagValue;
            t.IsTrue(flagValue(nullptr, true) && !flagValue(nullptr, false), "unset -> the default");
            t.IsTrue(flagValue("", true) && !flagValue("", false), "empty -> the default");
            t.IsFalse(flagValue("0", true), "0");
            t.IsFalse(flagValue("false", true), "false");
            t.IsFalse(flagValue("off", true), "off");
            t.IsTrue(flagValue("1", false), "1");
            t.IsTrue(flagValue("yes", false), "anything else");
        });

        tc.Run("enforcement off: knob() is getenv -- a Dev knob is readable with no developer mode", [](TestCase &t)
        {
            KnobStateGuard guard;
            ps2x::knobs::setEnforcement(false);
            ps2x::knobs::setDevMode(false);
            setVar(kDevName, "0x100:4");
            const char *v = ps2x::knob(kDevName);
            t.IsTrue(v != nullptr && std::string(v) == "0x100:4", "the value, untouched");
            setVar(kDevName, nullptr);
            t.IsNull(ps2x::knob(kDevName), "and unset is null");
        });

        tc.Run("enforcement on: Dev needs developer mode, Shipping never does, empty is unset, unregistered is null", [](TestCase &t)
        {
            KnobStateGuard guard;
            ps2x::knobs::setEnforcement(true);
            setVar(kDevName, "0x100:4");
            setVar(kShippingName, "2.5");
            ps2x::knobs::setDevMode(false);
            t.IsNull(ps2x::knob(kDevName), "a stranger's environment cannot switch a probe on");
            const char *s = ps2x::knob(kShippingName);
            t.IsTrue(s != nullptr && std::string(s) == "2.5", "the launcher's channel is always open");
            ps2x::knobs::setDevMode(true);
            const char *d = ps2x::knob(kDevName);
            t.IsTrue(d != nullptr && std::string(d) == "0x100:4", "developer mode opens the probe");
#ifndef _WIN32
            setenv(kShippingName, "", 1);   // Windows cannot hold an empty variable; POSIX can, and a shell's `export X=` makes one
            t.IsNull(ps2x::knob(kShippingName), "empty is unset (R162)");
#endif
            setVar("PS2X_NO_SUCH_KNOB", "1");
            t.IsNull(ps2x::knob("PS2X_NO_SUCH_KNOB"), "a name the registry does not hold reads as unset");
            setVar("PS2X_NO_SUCH_KNOB", nullptr);
            setVar(kDevName, nullptr);
            setVar(kShippingName, nullptr);
        });

        tc.Run("knobOn: the flag rule on top of knob(), the default when the knob is hidden", [](TestCase &t)
        {
            KnobStateGuard guard;
            ps2x::knobs::setEnforcement(true);
            ps2x::knobs::setDevMode(true);
            setVar("PS2X_SOCOM2_NET_STATS", "0");
            t.IsFalse(ps2x::knobOn("PS2X_SOCOM2_NET_STATS", true), "0 is off even where the default is on");
            ps2x::knobs::setDevMode(false);
            t.IsTrue(ps2x::knobOn("PS2X_SOCOM2_NET_STATS", true), "hidden from a stranger: the default");
            setVar("PS2X_SOCOM2_NET_STATS", nullptr);
        });

        tc.Run("developer mode: PS2X_DEV decides until someone says otherwise", [](TestCase &t)
        {
            KnobStateGuard guard;
            setVar("PS2X_DEV", "1");
            ps2x::knobs::resetDevModeForTests();
            t.IsTrue(ps2x::knobs::devMode(), "PS2X_DEV=1");
            setVar("PS2X_DEV", "0");
            ps2x::knobs::resetDevModeForTests();
            t.IsFalse(ps2x::knobs::devMode(), "PS2X_DEV=0 is off: the flag rule, not presence");
            setVar("PS2X_DEV", nullptr);
            ps2x::knobs::resetDevModeForTests();
            t.IsFalse(ps2x::knobs::devMode(), "unset is off");
            ps2x::knobs::setDevMode(true);
            t.IsTrue(ps2x::knobs::devMode(), "--dev (setDevMode) wins over the environment");
        });

        tc.Run("consumeDevFlag: --dev is taken out of argv wherever it stands, argv[0] never", [](TestCase &t)
        {
            char a0[] = "socom2", a1[] = "--dev", a2[] = "--home", a3[] = "dir", a4[] = "--dev";
            char *argv[] = {a0, a1, a2, a3, a4, nullptr};
            int argc = 5;
            t.IsTrue(ps2x::knobs::consumeDevFlag(argc, argv), "found");
            t.Equals(argc, 3, "both copies removed");
            t.Equals(std::string(argv[1]), std::string("--home"), "what follows moves up");
            t.Equals(std::string(argv[2]), std::string("dir"), "in order");
            t.IsNull(argv[3], "argv stays null-terminated");
            char b0[] = "--dev", b1[] = "game.elf";
            char *argv2[] = {b0, b1, nullptr};
            int argc2 = 2;
            t.IsFalse(ps2x::knobs::consumeDevFlag(argc2, argv2), "argv[0] is the program, whatever it is called");
            t.Equals(argc2, 2, "and nothing moved");
        });

        tc.Run("describe: what is in effect, what was ignored, paths cut to their file name, long values clipped", [](TestCase &t)
        {
            const ps2x::knobs::Pairs set = {
                {"PS2X_CD_IMAGE", "C:\\Users\\someone\\Games\\SOCOM II (USA).iso"},
                {"PS2X_GS_BACKEND", "cpu"},
                {"PS2X_GS_SCALE", "1"},
                {"PS2X_PEEK", "0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12"},
                {"PS2X_TEST_SUITE", "Knobs"},
                {"PS2X_WINDOW_SIZE", "1280x896"},
            };
            t.Equals(ps2x::knobs::describe(set, false),
                     std::string("[knobs] dev=0 set: PS2X_CD_IMAGE=\"SOCOM II (USA).iso\" PS2X_WINDOW_SIZE=1280x896"
                                 " | ignored without --dev: PS2X_GS_BACKEND PS2X_PEEK"),
                     "a stranger: the default-valued scale is not news, the test-only name never is, the path keeps no directory");
            t.Equals(ps2x::knobs::describe(set, true),
                     std::string("[knobs] dev=1 set: PS2X_CD_IMAGE=\"SOCOM II (USA).iso\" PS2X_GS_BACKEND=cpu"
                                 " PS2X_PEEK=0x416054:3,*0x408c58:64,*0x408c58+0xc0*:... PS2X_WINDOW_SIZE=1280x896"),
                     "a developer: every set knob, values clipped at 40 characters");
            t.Equals(ps2x::knobs::describe({}, false), std::string("[knobs] dev=0 set: none"), "nothing set");
        });

        tc.Run("the Shipping class is exactly what the launcher can send", [](TestCase &t)
        {
            launcher::Config c;
            c.isoPath = "game.iso";
            c.fpsOverlay = true;
            c.gamepadIndex = 0;
            c.crouchShortcut = "l2";
            c.micDevice = "Microphone";
            c.mouseLook = true;
            c.secondInstance = true;
            std::set<std::string> sent;
            for (const std::string &kv : launcher::environmentFor(c))
                sent.insert(kv.substr(0, kv.find('=')));
            std::set<std::string> shipping;
            for (const ps2x::knobs::Entry &e : ps2x::knobs::kTable)
                if (e.cls == ps2x::knobs::Class::Shipping)
                    shipping.insert(e.name);
            for (const std::string &name : sent)
                t.IsTrue(shipping.count(name) == 1, name + ": sent by the launcher, so it must be Shipping");
            for (const std::string &name : shipping)
                t.IsTrue(sent.count(name) == 1, name + ": Shipping, so config.json must be able to set it");
            t.Equals(static_cast<int>(shipping.size()), 17, "seventeen settings");
        });
    });
}
```

  In `ps2xTest/src/main.cpp` add `void register_knobs_tests();` after `void register_diagnostics_tests();` and `register_knobs_tests();` after `register_diagnostics_tests();`. In `ps2xTest/CMakeLists.txt` add `    src/knobs_tests.cpp` after `    src/diagnostics_tests.cpp`. (If Goal 8's `bug_report_tests.cpp` lines are there, add after them.) (`|` is legal in a meaning; the Markdown writer escapes it, and Task 2 tests that.)

  Build: `cmake --build third_party/ps2recomp/build-clang --target ps2x_tests`. Expected RED: `fatal error: 'ps2x/knobs.h' file not found`. Paste it into the ledger.

- [x] **Step 2: GREEN — the header.** Create `third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h`: *[done; 154 rows, not 143 -- the eleven new names are in the ledger]*

```cpp
#pragma once

// Sprint 9 Goal 3: every PS2X_* environment name the shipped executables read, decided once. This table
// IS the accessor's lookup (ps2x::knob), the source of docs/KNOBS.md (tools_py/knobs.py reads the rows with
// a regex, so a row's shape is part of the contract) and the launcher's list of settings:
//
//     X("PS2X_NAME", Class, Kind, "default", "One line, at most 110 characters, no double quote.")
//
// Rows are sorted by name in strcmp order (find() is a binary search; the Knobs suite and
// tools_py/tests/test_knobs_registry.py both check it). Adding a getenv of a PS2X_* name anywhere in
// ps2xRuntime, ps2xIOP, ps2xShared or ps2xLauncher without a row here fails the Python suite, and so does a
// row nothing reads.
//
// Class:  Shipping  a player-facing setting; launcher::Config has a field behind it; always honoured.
//         Dev       a probe, trace, dump or A/B switch; honoured only in developer mode (--dev on the runner's
//                   command line, or PS2X_DEV=1). A stranger's environment cannot switch one on.
//         Test      read by ps2x_tests only, never by a shipped executable.
//         Switch    PS2X_DEV itself.
// Kind:   Flag      read with ps2x::knobOn -- unset or empty is the default; 0, false, off are false; anything
//                   else is true.
//         Presence  any value, including 0, switches it on (traces; see docs/KNOBS.md).
//         Int, Float, Text, Path, Spec   parsed where they are read.

#include <cstddef>
#include <string>
#include <utility>
#include <vector>

#define PS2X_KNOB_TABLE(X) \
    X("PS2X_AUDIO_DUMP", Dev, Path, "", "Write the mixed host audio (48 kHz stereo s16) to this file.") \
    X("PS2X_AUDIO_PCM_DUMP", Dev, Path, "", "Write what the EE DMAs into the 989snd PCM ring to this file (first 16 MiB).") \
    X("PS2X_AUDIO_TRACE", Dev, Presence, "", "Every 5 s: how the host audio callback is serviced against wall time.") \
    X("PS2X_AUDIO_VOLUME", Shipping, Int, "100", "Master volume 0-100; 100 is unity and touches no sample.") \
    X("PS2X_CALL_TRACE", Dev, Spec, "", "0xADDR:Name[,...]: wrap these guest functions and log their calls.") \
    X("PS2X_CALL_TRACE_DUMP", Dev, Spec, "", "Name:a<k>[+off][*]:<words>: dump guest words reached from an argument after a traced call.") \
    X("PS2X_CALL_TRACE_EVERY", Dev, Int, "500", "After the first 300 traced calls log every k-th.") \
    X("PS2X_CD_IMAGE", Shipping, Path, "", "The disc image to mount; unset hunts for an .iso beside the ELF.") \
    X("PS2X_CD_TRACE", Dev, Presence, "", "Print CD file lookups and sector reads.") \
    X("PS2X_CLOCK_CAP_MS", Dev, Float, "100", "Longest single gap of host time the guest clock may absorb; 0 = uncapped.") \
    X("PS2X_CLOCK_EXCLUDE", Dev, Int, "0", "1 restores the 2026-09-08 exclusion of VU1 and render waits from guest time (A/B).") \
    X("PS2X_CLOCK_TRACE", Dev, Presence, "", "Once a second: the cycle clock against host time, T0, the next deadline.") \
    X("PS2X_CONSOLE_REPLAY_DIR", Test, Path, "", "ps2x_tests: folder holding a console GS dump to replay through the rasterisers.") \
    X("PS2X_CONSOLE_REPLAY_FBP", Test, Int, "", "ps2x_tests: frame buffer page to compare in the console replay.") \
    X("PS2X_CONSOLE_REPLAY_GL", Test, Presence, "", "ps2x_tests: replay through the GL backend as well.") \
    X("PS2X_CONSOLE_REPLAY_PIXEL", Test, Text, "", "ps2x_tests: x,y of a pixel to watch during the console replay.") \
    X("PS2X_CONSOLE_REPLAY_STOP", Test, Int, "", "ps2x_tests: stop the console replay after this packet.") \
    X("PS2X_CULL_PARTIAL_CLIP", Dev, Int, "0", "Experiment (research/31 s16): answer needs-clipping for partial boxes inside the guard band.") \
    X("PS2X_CULL_TRACE", Dev, Spec, "", "Trace the terrain cull/LOD/detail decisions to a file (research/31 tools read it).") \
    X("PS2X_CYCLE_CLOCK", Dev, Text, "", "guest = estimate-driven cycle accounting instead of wall time (not an A/B of pre-R54).") \
    X("PS2X_DETAIL_FAR", Dev, Int, "0", "Experiment: force the far detail level by writing guest byte 0x4b4a88.") \
    X("PS2X_DEV", Switch, Flag, "0", "Developer mode: Dev-class knobs are honoured. The same as --dev on the runner command line.") \
    X("PS2X_EE_ROUND", Dev, Text, "", "nearest = host FPU rounds to nearest on the game thread instead of toward zero.") \
    X("PS2X_FPS_OVERLAY", Shipping, Int, "0", "1 draws the frame-rate box in the window (never in exported frames).") \
    X("PS2X_FPU_TRAP", Dev, Float, "-1", "Seconds after which EE divisions by zero and saturated square roots are reported with their pc.") \
    X("PS2X_FRAME_DUMP", Dev, Path, "", "Directory: a PPM every 60 presents plus the VU1 trace dumps; forces a pixel readback per present.") \
    X("PS2X_GIF_DUMP", Dev, Spec, "", "<file>[:<seconds>]: record the GIF stream and a VRAM snapshot in PCSX2-dump shape.") \
    X("PS2X_GIF_PRIORITY_SORT", Dev, Presence, "", "Restore the GIF arbiter priority sort (A/B of the 2026-09-08 change).") \
    X("PS2X_GIF_TRACE", Dev, Int, "0", "Print the first n GIF submissions with their path and BITBLTBUF.") \
    X("PS2X_GS_BACKEND", Dev, Text, "gpu", "cpu selects the CPU rasteriser; the GL probe falls back to it by itself (exit 65).") \
    X("PS2X_GS_DEPTH_LEGACY", Dev, Int, "0", "1 forces the legacy depth mapping instead of clip control.") \
    X("PS2X_GS_DUMP_DISPLAY", Dev, Spec, "", "<dir>:<t0>:<t1>: every ~2 s write the displayed buffer three ways (gpu, shadow, cpu).") \
    X("PS2X_GS_DUMP_TEX", Dev, Path, "", "Directory: write every decoded texture as PPM + PGM, and the CLUT diagnostic.") \
    X("PS2X_GS_DUMP_TEX_EVERY", Dev, Int, "1", "With GS_DUMP_TEX: keep one decode in n.") \
    X("PS2X_GS_DUMP_TEX_FROM", Dev, Int, "", "With GS_DUMP_TEX: start at this frame, or trig.") \
    X("PS2X_GS_DUMP_TEX_MAX", Dev, Int, "6", "With GS_DUMP_TEX: files per texture.") \
    X("PS2X_GS_DUMP_TEX_TBP0", Dev, Spec, "", "With GS_DUMP_TEX: only these texture base blocks.") \
    X("PS2X_GS_GL_DEBUG_AFTER", Dev, Int, "0", "Presents to wait before GS_GL_DEBUG_PSM and GS_DUMP_TEX act.") \
    X("PS2X_GS_GL_DEBUG_NODEPTH", Dev, Presence, "", "Inside the GS_GL_DEBUG_PSM print: disable the depth test for that draw.") \
    X("PS2X_GS_GL_DEBUG_PSM", Dev, Int, "-1", "Print the first batches drawn with this texture format (native coordinates; wrong above scale 1).") \
    X("PS2X_GS_GL_FORCE_FAIL", Dev, Text, "", "Make the GL capability probe fail (the only way to reach exit 65 on a machine that works).") \
    X("PS2X_GS_MAX_PENDING_FRAMES", Dev, Int, "3", "Back-pressure: presents the render thread may fall behind; 0 = unbounded.") \
    X("PS2X_GS_NO_DIRTY_REFRESH", Dev, Presence, "", "Drop pending dirty rows instead of re-reading them (A/B).") \
    X("PS2X_GS_NO_TEX_REVALIDATE", Dev, Presence, "", "Restore decode-on-every-invalidation instead of content-hash revalidation (A/B of R117-R125).") \
    X("PS2X_GS_NO_ZTEST", Dev, Presence, "", "Every draw passes the depth test (A/B).") \
    X("PS2X_GS_PENDING_CAP_MB", Dev, Int, "64", "Soft ceiling on pending render bytes.") \
    X("PS2X_GS_PENDING_HARD_CAP_MB", Dev, Int, "1024", "Hard ceiling on pending render bytes (R124).") \
    X("PS2X_GS_PROBE", Dev, Int, "-1", "Frame from which to read back rows 200/420/440 of fbp 0x8c after untextured sprites.") \
    X("PS2X_GS_RT_TEXTURE", Dev, Int, "1", "0 restores the readback + decode for render targets used as textures.") \
    X("PS2X_GS_SCALE", Shipping, Int, "1", "Internal render scale 1-4.") \
    X("PS2X_GS_SCALE_FILTER", Dev, Text, "", "box = box-filter the resolve of a scaled target.") \
    X("PS2X_GS_SCALE_SELFTEST", Dev, Int, "0", "1 checks the native mirror of a scaled target against a fresh resolve each frame.") \
    X("PS2X_GS_SKIP_TBP0", Dev, Spec, "", "Drop every textured draw binding one of these texture blocks (a bisect).") \
    X("PS2X_GS_STATS", Dev, Presence, "", "The [gs-gl stats] line every 60 command buffers.") \
    X("PS2X_GS_TEX_FROM_CPU", Dev, Presence, "", "Decode textures from the game thread VRAM instead of the shadow.") \
    X("PS2X_GS_TRACE_CMDS", Dev, Int, "", "Presents to skip (or trig), then print the replayed GS commands.") \
    X("PS2X_GS_TRACE_CMDS_BOX", Dev, Spec, "", "With GS_TRACE_CMDS: only draws touching this screen box.") \
    X("PS2X_GS_TRACE_CMDS_FROM", Dev, Int, "-1", "With GS_TRACE_CMDS: start at this frame.") \
    X("PS2X_GS_TRACE_CMDS_MAX", Dev, Int, "4000", "With GS_TRACE_CMDS: line budget.") \
    X("PS2X_GS_TRACE_CMDS_PER_FRAME", Dev, Int, "0", "With GS_TRACE_CMDS: lines per frame; 0 = no per-frame limit.") \
    X("PS2X_GS_TRACE_CMDS_TBP0", Dev, Spec, "", "With GS_TRACE_CMDS: only draws binding these texture blocks.") \
    X("PS2X_GS_TRACE_DIRTY", Dev, Int, "-1", "From this frame: log dirty marks landing in the visible rows of a display buffer.") \
    X("PS2X_GS_TRACE_DISPFB", Dev, Presence, "", "Log display-buffer selection and clears.") \
    X("PS2X_GS_TRACE_PAGES", Dev, Spec, "", "<page>[:count]: log every event touching these VRAM pages, with the frame number.") \
    X("PS2X_GS_TRACE_PRESENT", Dev, Int, "-1", "Presents to skip (or trig), then trace uploads, downloads and the present path.") \
    X("PS2X_GS_UPLOAD_TRACE", Dev, Presence, "", "Per-call timing of the tile upload path on the [gs-gl stats] cadence.") \
    X("PS2X_HLE_STATS", Dev, Flag, "0", "Count calls per bound HLE stub and print the table periodically.") \
    X("PS2X_HLE_STATS_PERIOD", Dev, Int, "30", "With HLE_STATS: seconds between tables.") \
    X("PS2X_HLE_STATS_TOML", Dev, Path, "recomp/socom2.toml", "With HLE_STATS: the recompiler config naming the stubs.") \
    X("PS2X_HOST_GAMEPAD", Dev, Int, "1", "0 disables every host gamepad read (a harness run must not depend on what is plugged in).") \
    X("PS2X_HOST_GAMEPAD_INDEX", Shipping, Int, "", "Which host pad slot to read; unset = the first available.") \
    X("PS2X_HOST_PROF", Dev, Float, "", "Sampling host profiler period in ms (min 0.2).") \
    X("PS2X_HOST_PROF_ALL", Dev, Presence, "", "With HOST_PROF: sample every thread.") \
    X("PS2X_HOST_PROF_MAIN", Dev, Presence, "", "With HOST_PROF: sample the main (GL) thread instead of the game thread.") \
    X("PS2X_HOST_PROF_OUT", Dev, Path, "logs/hostprof.txt", "With HOST_PROF: the histogram file.") \
    X("PS2X_HOST_PROF_STACKS", Dev, Presence, "", "With HOST_PROF: record call stacks.") \
    X("PS2X_HOST_SCREENSHOT", Dev, Spec, "", "<dir>[:<seconds>]: save what the window shows every n seconds (default 5).") \
    X("PS2X_HOST_SCREENSHOT_LATEST", Dev, Path, "", "Rewrite this PNG with the current frame twice a second; every harness capture reads it.") \
    X("PS2X_JALR_TRACE", Dev, Spec, "", "0xSRC[,...]: log the resolved target of indirect calls issued from these pcs.") \
    X("PS2X_LAUNCHER_SHOT", Dev, Path, "", "Launcher: after 120 frames save the real window to this PNG and quit.") \
    X("PS2X_LOD_SCALE", Dev, Float, "0", "Experiment: force both LOD scale floats of the camera (writes guest memory).") \
    X("PS2X_MC_DIR", Shipping, Path, "", "Memory-card folder for slot 0; unset = mc0 beside the ELF.") \
    X("PS2X_MC_DIR_SLOT1", Dev, Path, "", "A folder to serve as the second card slot; unset = no card in slot 1.") \
    X("PS2X_MC_TRACE", Dev, Presence, "", "Log every memory-card GetInfo and Sync.") \
    X("PS2X_MIC_DEVICE", Shipping, Text, "", "Capture device name for the headset; unset = no microphone.") \
    X("PS2X_MIC_DUMP", Dev, Path, "", "Tee the captured microphone PCM to this WAV.") \
    X("PS2X_MIC_DUMP_PLAYBACK", Dev, Path, "", "WAV of what lgaud 0x09 asked the headset to play ({title} expands to the window tag).") \
    X("PS2X_MIC_FAKE", Dev, Path, "", "Feed this WAV as the microphone; beats MIC_DEVICE (R115).") \
    X("PS2X_MIC_GAMEREAD_DUMP", Dev, Path, "", "WAV of what lgaud 0x08 served the game.") \
    X("PS2X_MPEG_PIC_TRACE", Dev, Presence, "", "Log the first five decoded MPEG pictures and every 300th.") \
    X("PS2X_MPEG_TRACE", Dev, Presence, "", "Log the sceMpeg HLE lifecycle and the IOP stream opens.") \
    X("PS2X_PACK_TRACE", Dev, Path, "", "Trace the terrain pack function 0x25a5d0 to this file (research/31 s17).") \
    X("PS2X_PAD_CROUCH_SHORTCUT", Shipping, Text, "off", "l3 | touchpad | l2: the host control that sends a light Triangle (R139).") \
    X("PS2X_PAD_DEADZONE", Shipping, Float, "0.15", "Stick dead zone 0-0.5 on all three pad paths.") \
    X("PS2X_PC_SAMPLER", Dev, Float, "", "Seconds between [pc-sampler] rows (guest pc/ra per thread); PEEK rides on it.") \
    X("PS2X_PEEK", Dev, Spec, "", "0xADDR[:words][,...] with * dereferences: guest words printed with each sampler row.") \
    X("PS2X_PK_REPLAY", Test, Path, "", "ps2x_tests: a vu1_replay packet file to push through the GS frontend.") \
    X("PS2X_PRESENT_FILTER", Shipping, Text, "linear", "linear | integer | point: how the frame is scaled into the window.") \
    X("PS2X_RDRAM_DUMP", Dev, Spec, "", "<file>[:<seconds>]: dump guest RAM after n seconds (default 10).") \
    X("PS2X_RDRAM_DUMP_AT", Dev, Spec, "", "<file>:<0xPC>#<count>: dump guest RAM when a pc has been reached n times.") \
    X("PS2X_SND_STREAM_WORKER", Dev, Int, "1", "0 reads audio streams on the mixer thread instead of the worker (A/B).") \
    X("PS2X_SOCOM2_HOSTS", Dev, Spec, "", "name=ip[,...]: extra host-name answers for the resolver the game uses.") \
    X("PS2X_SOCOM2_INPUT_FILE", Dev, Path, "", "Pad-state injection file polled by a sampler thread; how the harness presses buttons.") \
    X("PS2X_SOCOM2_INPUT_SCRIPT", Dev, Spec, "", "t:BTN[+BTN][:hold],...: press buttons at those seconds.") \
    X("PS2X_SOCOM2_INPUT_TRACE", Dev, Presence, "", "Log every change of the pad state the game will read.") \
    X("PS2X_SOCOM2_MOUSE", Shipping, Int, "0", "1 maps the mouse to the right stick.") \
    X("PS2X_SOCOM2_MOUSE_SENS", Shipping, Float, "4", "Mouse-look sensitivity (the launcher sends its own value, default 1).") \
    X("PS2X_SOCOM2_NET_STATS", Dev, Flag, "1", "The periodic [net-stats] line; 0 silences it.") \
    X("PS2X_SOCOM2_NET_TRACE", Dev, Presence, "", "Verbose libnetb: every RPC, socket and datagram header.") \
    X("PS2X_SOCOM2_NET_TRACE_ALL", Dev, Flag, "0", "With NET_TRACE: hex-dump datagrams on every port, not only the peer ports.") \
    X("PS2X_SOCOM2_NET_TRACE_PEERS", Dev, Int, "16", "With NET_TRACE: peer packets to hex-dump in each direction.") \
    X("PS2X_SOCOM2_PAD", Shipping, Presence, "", "The libpad2 HLE and host input path; opt-in by presence today, on by default after Task 7 (R160).") \
    X("PS2X_SOCOM2_PAD_TRACE", Dev, Presence, "", "Log the scePad2 socket lifecycle and reads.") \
    X("PS2X_SOCOM2_RSA_KEY", Shipping, Text, "a", "b selects the second precomputed RSA pair (a second instance on one host).") \
    X("PS2X_SOCOM2_SERVER", Shipping, Text, "127.0.0.1", "Address or name every Medius/DNAS host name resolves to.") \
    X("PS2X_SOCOM2_UDP_SHIFT", Shipping, Int, "0", "Shift the fixed UDP ports 3658.. by n (a second instance on one host).") \
    X("PS2X_TEST_SKIP", Test, Text, "", "ps2x_tests: skip tests whose name contains one of these substrings.") \
    X("PS2X_TEST_SUITE", Test, Text, "", "ps2x_tests: run only suites whose name contains this.") \
    X("PS2X_TIMER_TRACE", Dev, Presence, "", "Once a second: how the guest polls EE timer 0.") \
    X("PS2X_TRACE_FIFO", Dev, Presence, "", "Log VIF1/GIF FIFO stalls, resumes and the IRQ dispatch.") \
    X("PS2X_TRACE_VIF", Dev, Spec, "", "<skip> | t<seconds> | trig: print VIF1 codes and chain tags.") \
    X("PS2X_TRACE_VU", Dev, Int, "", "Skip n VU1 programs then dump the next three; forces the cycle-exact scheduler.") \
    X("PS2X_TRACE_VU_FLAGS", Dev, Presence, "", "Log what the VU flag readers see.") \
    X("PS2X_TRACE_VU_STEPS", Dev, Int, "1200", "With TRACE_VU: instruction budget per traced program.") \
    X("PS2X_TRIGGER", Dev, Spec, "", "lo:hi: arm the trig trace modes when the first PEEK word, as a float, lies in the range.") \
    X("PS2X_VIF1_NO_IRQ_STALL", Dev, Presence, "", "Restore VIF1 without the i-bit stall (A/B).") \
    X("PS2X_VU0_FAST", Dev, Int, "1", "0 keeps VU0 micro programs on the cycle-exact scheduler.") \
    X("PS2X_VU1_BAILHIST", Dev, Presence, "", "Histogram of where generated VU1 code bails to the interpreter.") \
    X("PS2X_VU1_DUMP", Dev, Path, "", "Dump VU1 program state at each run for vu1_replay (armed by TRIGGER or VU1_DUMP_AFTER).") \
    X("PS2X_VU1_DUMP_AFTER", Dev, Float, "0", "With VU1_DUMP: arm after this many seconds.") \
    X("PS2X_VU1_FAST", Dev, Int, "1", "0 selects the cycle-exact VU1 scheduler.") \
    X("PS2X_VU1_FMAC_CHECK", Dev, Presence, "", "Cross-check the SIMD MAC-flag classifier against the long double path.") \
    X("PS2X_VU1_GEN", Dev, Int, "1", "0 disables the generated VU1 programs.") \
    X("PS2X_VU1_HOST_DRAW", Dev, Int, "0", "1 draws the native dispatcher triangles in host space instead of kicking GIF packets.") \
    X("PS2X_VU1_NATIVE", Dev, Int, "1", "0 reverts the hand-written native VU1 programs to the generated/interpreted path.") \
    X("PS2X_VU1_NATIVE_TEST_CEILING", Dev, Int, "", "Test hook: lower the native dispatcher vertex and triangle ceilings.") \
    X("PS2X_VU1_NATIVE_TEST_CLIP_CEILING", Dev, Int, "", "Test hook: lower the native dispatcher clipped-vertex ceiling.") \
    X("PS2X_VU1_XGKICK_CYCLE_EXACT", Dev, Presence, "", "Restore the per-cycle XGKICK transfer model (drops SOCOM II object geometry).") \
    X("PS2X_VU_STATS", Dev, Presence, "", "Once a second: VU1 programs, cycles and host time.") \
    X("PS2X_WATCH", Dev, Spec, "", "0xADDR[,...]: poll guest words every ~0.5 ms and print each change with pc/ra.") \
    X("PS2X_WATCH_HUGE", Dev, Spec, "", "0xADDR:words: report floats in the range that turn huge or NaN.") \
    X("PS2X_WINDOW_SIZE", Shipping, Text, "640x448", "<w>x<h> | fullscreen (the launcher sends 1280x896 by default).") \
    X("PS2X_WINDOW_TITLE", Dev, Text, "", "Window-title tag for a second instance; the harness finds windows by it.")

namespace ps2x
{
    // The value of a registered knob, or nullptr. While enforcement is off this is std::getenv(name). With it
    // on: nullptr when the variable is unset or empty, when the name is not in the table, or when the knob is
    // Dev and the process is not in developer mode. Never caches -- tests and BareRun::applyEnvironment change
    // the environment while the process runs -- so a site on a hot path reads once into its own static.
    const char *knob(const char *name);

    // The one flag rule on top of knob(): dflt when knob() is nullptr (or empty); false for "0", "false", "off";
    // true for anything else.
    bool knobOn(const char *name, bool dflt = false);

    namespace knobs
    {
        enum class Class { Shipping, Dev, Test, Switch };
        enum class Kind { Flag, Presence, Int, Float, Text, Path, Spec };

        struct Entry
        {
            const char *name;
            Class cls;
            Kind kind;
            const char *dflt;
            const char *meaning;
        };

#define PS2X_KNOB_ENTRY(name, cls, kind, dflt, meaning) Entry{name, Class::cls, Kind::kind, dflt, meaning},
        inline constexpr Entry kTable[] = {PS2X_KNOB_TABLE(PS2X_KNOB_ENTRY)};
#undef PS2X_KNOB_ENTRY
        inline constexpr size_t kTableSize = sizeof(kTable) / sizeof(kTable[0]);

        const Entry *find(const char *name);
        const char *className(Class cls);
        const char *kindName(Kind kind);
        bool flagValue(const char *value, bool dflt);

        // Developer mode: setDevMode() (the runner's --dev, ps2x_tests, vu1_replay) or, failing that,
        // PS2X_DEV under the flag rule, read once on first use.
        bool devMode();
        void setDevMode(bool on);
        void resetDevModeForTests();   // forget the decision so the next devMode() reads PS2X_DEV again

        // Off until Sprint 9 Goal 3 Task 7: while off, knob() is a plain getenv and nothing is hidden.
        bool enforcement();
        void setEnforcement(bool on);

        // Removes every "--dev" after argv[0], closes the gap, keeps argv null-terminated. True when one was there.
        bool consumeDevFlag(int &argc, char **argv);

        // One line for the log: what is set and honoured, and what was set and ignored. `set` is the non-empty
        // PS2X_* variables in table order. A Shipping value equal to its default is not news; a Path is cut to
        // its last component (the diagnostics zip must not carry a home directory); 40 characters a value.
        using Pairs = std::vector<std::pair<std::string, std::string>>;
        std::string describe(const Pairs &set, bool honourDev);
        std::string startupLine();     // describe() over this process's environment
    }
}
```

- [x] **Step 3: GREEN — the implementation.** Create `third_party/ps2recomp/ps2xShared/src/knobs.cpp`: *[done; R204's pathInsideHome added in its own commit]*

```cpp
#include "ps2x/knobs.h"

#include <atomic>
#include <cstdlib>
#include <cstring>

namespace ps2x
{
    namespace knobs
    {
        namespace
        {
            std::atomic<int> g_dev{-1};           // -1: not decided yet, PS2X_DEV decides on first use
            std::atomic<bool> g_enforce{false};   // Sprint 9 Goal 3 Task 7 turns this on

            std::string printable(const Entry &e, const std::string &value)
            {
                std::string v = value;
                if (e.kind == Kind::Path)
                {
                    const size_t slash = v.find_last_of("/\\");
                    if (slash != std::string::npos && slash + 1 < v.size())
                        v = v.substr(slash + 1);
                }
                if (v.size() > 40)
                    v = v.substr(0, 40) + "...";
                if (v.find(' ') != std::string::npos)
                    v = "\"" + v + "\"";
                return v;
            }
        }

        const Entry *find(const char *name)
        {
            if (name == nullptr)
                return nullptr;
            size_t lo = 0, hi = kTableSize;
            while (lo < hi)
            {
                const size_t mid = lo + (hi - lo) / 2;
                const int c = std::strcmp(kTable[mid].name, name);
                if (c == 0)
                    return &kTable[mid];
                if (c < 0)
                    lo = mid + 1;
                else
                    hi = mid;
            }
            return nullptr;
        }

        const char *className(Class cls)
        {
            switch (cls)
            {
            case Class::Shipping: return "Shipping";
            case Class::Dev: return "Dev";
            case Class::Test: return "Test";
            case Class::Switch: return "Switch";
            }
            return "?";
        }

        const char *kindName(Kind kind)
        {
            switch (kind)
            {
            case Kind::Flag: return "Flag";
            case Kind::Presence: return "Presence";
            case Kind::Int: return "Int";
            case Kind::Float: return "Float";
            case Kind::Text: return "Text";
            case Kind::Path: return "Path";
            case Kind::Spec: return "Spec";
            }
            return "?";
        }

        bool flagValue(const char *value, bool dflt)
        {
            if (value == nullptr || *value == 0)
                return dflt;
            return !(std::strcmp(value, "0") == 0 || std::strcmp(value, "false") == 0 || std::strcmp(value, "off") == 0);
        }

        bool devMode()
        {
            int v = g_dev.load(std::memory_order_acquire);
            if (v < 0)
            {
                // The one raw read of a PS2X_* name outside this function's callers: the switch cannot be read
                // through the accessor it controls. tools_py/knobs.py allows getenv("PS2X_ in this file only.
                v = flagValue(std::getenv("PS2X_DEV"), false) ? 1 : 0;
                g_dev.store(v, std::memory_order_release);
            }
            return v != 0;
        }

        void setDevMode(bool on) { g_dev.store(on ? 1 : 0, std::memory_order_release); }
        void resetDevModeForTests() { g_dev.store(-1, std::memory_order_release); }
        bool enforcement() { return g_enforce.load(std::memory_order_acquire); }
        void setEnforcement(bool on) { g_enforce.store(on, std::memory_order_release); }

        bool consumeDevFlag(int &argc, char **argv)
        {
            bool found = false;
            int out = 0;
            for (int i = 0; i < argc; ++i)
            {
                if (i > 0 && argv[i] != nullptr && std::strcmp(argv[i], "--dev") == 0)
                {
                    found = true;
                    continue;
                }
                argv[out++] = argv[i];
            }
            if (found)
                argv[out] = nullptr;   // out < argc, and argv[argc] was already null
            argc = out;
            return found;
        }

        std::string describe(const Pairs &set, bool honourDev)
        {
            std::string shown, ignored;
            for (const auto &pair : set)
            {
                const Entry *e = find(pair.first.c_str());
                if (e == nullptr || e->cls == Class::Test || pair.second.empty())
                    continue;
                if (e->cls == Class::Dev && !honourDev)
                {
                    ignored += " " + pair.first;
                    continue;
                }
                if (e->cls != Class::Dev && pair.second == e->dflt)
                    continue;
                shown += " " + pair.first + "=" + printable(*e, pair.second);
            }
            std::string out = std::string("[knobs] dev=") + (honourDev ? "1" : "0") + " set:" + (shown.empty() ? std::string(" none") : shown);
            if (!ignored.empty())
                out += " | ignored without --dev:" + ignored;
            return out;
        }

        std::string startupLine()
        {
            Pairs set;
            for (const Entry &e : kTable)
            {
                const char *v = std::getenv(e.name);
                if (v != nullptr && *v != 0)
                    set.emplace_back(e.name, v);
            }
            return describe(set, devMode() || !enforcement());
        }
    }

    const char *knob(const char *name)
    {
        const char *v = std::getenv(name);
        if (!knobs::enforcement())
            return v;
        if (v == nullptr || *v == 0)
            return nullptr;               // the common case costs what it cost before: one getenv
        const knobs::Entry *e = knobs::find(name);
        if (e == nullptr)
            return nullptr;               // test_knobs_registry keeps this unreachable for a literal name
        if (e->cls == knobs::Class::Dev && !knobs::devMode())
            return nullptr;
        return v;
    }

    bool knobOn(const char *name, bool dflt)
    {
        return knobs::flagValue(knob(name), dflt);
    }
}
```

  In `ps2xShared/CMakeLists.txt` add `    src/knobs.cpp` to the `add_library(ps2x_shared STATIC` list, after `    src/diagnostics.cpp` (or after Goal 8's `src/bug_report.cpp` if it is there).

  **The `dev=` label while enforcement is off** reads `dev=1` for everyone, because every knob *is* honoured for everyone until Task 7; that is the truth about the process, and Task 7's poisoned launch is where `dev=0` first appears in a game log.

- [x] **Step 4: Run.** `cmake --build third_party/ps2recomp/build-clang --target ps2x_tests && (cd third_party/ps2recomp/build-clang/ps2xTest && PS2X_TEST_SUITE=Knobs ./ps2x_tests.exe)`. Expected: the ten `Knobs` cases pass. Then the whole thing: `./build.sh test` exit 0, `Total Tests:` = `B + 10`. The "Shipping class" case passing is the proof of Handoff note 9; if it fails on a name, **stop and tell the controller** — the inventory is wrong, not the test. *[done; the Shipping case asserts 18, PS2X_INPUT_MAPPING being the eighteenth]*
- [x] **Step 5: Commit and push.** *[committed on agent/knobs; NOT pushed (the controller merges)]*

```bash
git add third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h third_party/ps2recomp/ps2xShared/src/knobs.cpp \
        third_party/ps2recomp/ps2xTest/src/knobs_tests.cpp
git commit -m "feat(shared): the knob registry -- 134 PS2X_* names classified in one table that is ps2x::knob's lookup; enforcement off, so nothing changes yet (Sprint 9 Goal 3 Task 1)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h third_party/ps2recomp/ps2xShared/src/knobs.cpp \
  third_party/ps2recomp/ps2xShared/CMakeLists.txt third_party/ps2recomp/ps2xTest/src/knobs_tests.cpp \
  third_party/ps2recomp/ps2xTest/CMakeLists.txt third_party/ps2recomp/ps2xTest/src/main.cpp
git push
```

  If `ps2xShared/CMakeLists.txt`, `ps2xTest/CMakeLists.txt` or `ps2xTest/src/main.cpp` carry Goal 8's uncommitted lines at that moment, **do not commit them**: wait for that session's commit, or stage only this task's hunks with `git apply --cached` on a hand-cut patch, and say which in the ledger.

---

## Task 2 — `docs/KNOBS.md`, generated, and the test that holds the source to it  **[Opus]**

**Files:**
- Create: `tools_py/knobs.py`, `tools_py/tests/test_knobs_registry.py`, `docs/KNOBS.md` (generated — never edited by hand)

**Interfaces:**
- `knobs.table(path=HEADER) -> [{"name","cls","kind","default","meaning"}]`
- `knobs.render(rows=None) -> str` (the whole of `docs/KNOBS.md`); `knobs.literals(root=ROOT) -> {name: ["file:line", ...]}`; `knobs.raw_getenv_sites(root) -> ["file:line", ...]`; `knobs.test_reads(root) -> {name: [...]}`; `knobs.harness_names(root) -> {name: [...]}`; `knobs.early_reads(root) -> ["file:line", ...]`; `knobs.accessor_mismatches(root, rows) -> [str]`; `knobs.problems(root=ROOT) -> [str]` (everything the test asserts, as sentences); `knobs.main(argv)`: `write`, `check` (exit 1 on any problem or a stale file), `sites`.
- `knobs.RAW_GETENV_PENDING`: the files Task 4 has not migrated yet. **It may only shrink.** `knobs.HARNESS_ONLY`, `knobs.NOT_KNOBS`.

**Steps:**

- [x] **Step 1: RED.** Create `tools_py/tests/test_knobs_registry.py`: *[done; RED: ImportError: cannot import name 'knobs']*

```python
"""Sprint 9 Goal 3: the knob registry (ps2xShared/include/ps2x/knobs.h) against the source.

The spec's bar: a knob read in code and absent from the table fails the suite. It fails the other way round
too (a row nothing reads), and docs/KNOBS.md is the table rendered -- stale is a failure. No build needed, so
this runs in CI."""
import os
import tempfile
import unittest

from tools_py import knobs


class RegistryShapeTest(unittest.TestCase):
    def test_the_header_parses_and_is_sorted_and_unique(self):
        rows = knobs.table()
        names = [r["name"] for r in rows]
        self.assertGreaterEqual(len(names), 130)
        self.assertEqual(names, sorted(names), "rows are in strcmp order: ps2x::knobs::find is a binary search")
        self.assertEqual(len(names), len(set(names)))
        for r in rows:
            self.assertIn(r["cls"], ("Shipping", "Dev", "Test", "Switch"), r)
            self.assertIn(r["kind"], ("Flag", "Presence", "Int", "Float", "Text", "Path", "Spec"), r)
            self.assertTrue(0 < len(r["meaning"]) <= 110, r)

    def test_the_parser_counts_every_row_the_macro_holds(self):
        with open(knobs.HEADER, "r", encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(len(knobs.table()), text.count('    X("PS2X_'),
                         "a row the regex cannot read would vanish from docs/KNOBS.md and from every check here")

    def test_seventeen_shipping_settings_and_one_switch(self):
        rows = knobs.table()
        self.assertEqual(sum(1 for r in rows if r["cls"] == "Shipping"), 17)
        self.assertEqual([r["name"] for r in rows if r["cls"] == "Switch"], ["PS2X_DEV"])


class SourceAgainstRegistryTest(unittest.TestCase):
    def test_no_problem_in_the_tree(self):
        self.assertEqual(knobs.problems(), [])

    def test_a_literal_with_no_row_is_a_problem(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "third_party", "ps2recomp", "ps2xRuntime", "src")
            os.makedirs(src)
            with open(os.path.join(src, "x.cpp"), "w") as fh:
                fh.write('static const bool s = ps2x::knob("PS2X_BRAND_NEW") != nullptr;\n')
            found = knobs.literals(root)
            self.assertIn("PS2X_BRAND_NEW", found)
            self.assertTrue(found["PS2X_BRAND_NEW"][0].endswith("x.cpp:1"))

    def test_a_raw_getenv_is_found_and_the_switch_file_is_exempt(self):
        with tempfile.TemporaryDirectory() as root:
            rt = os.path.join(root, "third_party", "ps2recomp", "ps2xRuntime", "src")
            sh = os.path.join(root, "third_party", "ps2recomp", "ps2xShared", "src")
            os.makedirs(rt)
            os.makedirs(sh)
            with open(os.path.join(rt, "y.cpp"), "w") as fh:
                fh.write('const char *e = std::getenv( "PS2X_GS_SCALE");\n')
            with open(os.path.join(sh, "knobs.cpp"), "w") as fh:
                fh.write('v = flagValue(std::getenv("PS2X_DEV"), false);\n')
            sites = knobs.raw_getenv_sites(root)
            self.assertEqual(len(sites), 1)
            self.assertTrue(sites[0].endswith("y.cpp:1"))

    def test_a_read_before_main_is_found(self):
        with tempfile.TemporaryDirectory() as root:
            rt = os.path.join(root, "third_party", "ps2recomp", "ps2xRuntime", "src")
            os.makedirs(rt)
            with open(os.path.join(rt, "z.cpp"), "w") as fh:
                fh.write('static const bool g_traceFifo = (ps2x::knob("PS2X_TRACE_FIFO") != nullptr);\n'
                         'namespace {\n        bool g_verbose = ps2x::knob("PS2X_SOCOM2_NET_TRACE") != nullptr;\n}\n'
                         'void f() {\n    static const bool s_on = ps2x::knob("PS2X_CD_TRACE") != nullptr;\n}\n')
            early = knobs.early_reads(root)
            self.assertEqual(len(early), 2, early)

    def test_the_pending_list_only_holds_files_that_still_need_it(self):
        raw_files = {site.rsplit(":", 1)[0] for site in knobs.raw_getenv_sites()}
        self.assertEqual(sorted(knobs.RAW_GETENV_PENDING - raw_files), [],
                         "a migrated file is still on RAW_GETENV_PENDING: take it off in the batch that migrates it")


class GeneratedDocTest(unittest.TestCase):
    def test_docs_knobs_md_is_the_registry_rendered(self):
        with open(knobs.DOC, "r", encoding="utf-8") as fh:
            on_disk = fh.read()
        self.assertEqual(on_disk, knobs.render(), "docs/KNOBS.md is stale: python -m tools_py.knobs write")

    def test_a_pipe_in_a_meaning_cannot_break_the_table(self):
        rows = [{"name": "PS2X_X", "cls": "Dev", "kind": "Text", "default": "", "meaning": "linear | integer"}]
        self.assertIn("linear \\| integer", knobs.render(rows))


if __name__ == "__main__":
    unittest.main()
```

  Run `python -m unittest tools_py.tests.test_knobs_registry -v`. Expected RED: `ImportError: cannot import name 'knobs' from 'tools_py'`.

- [x] **Step 2: GREEN.** Create `tools_py/knobs.py`: *[done, plus helper_getenv_sites (R203)]*

```python
"""The PS2X_* knob registry, read out of the C++ header that defines it (Sprint 9 Goal 3).

`third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h` is the one place a knob's class, kind, default and
meaning are written. This module parses its X-macro rows (as tools_py/exit_codes.py does for the exit codes),
renders docs/KNOBS.md from them, and scans the source so the two cannot drift:

    python -m tools_py.knobs write     regenerate docs/KNOBS.md
    python -m tools_py.knobs check     exit 1 on a stale docs/KNOBS.md or any disagreement below
    python -m tools_py.knobs sites     every PS2X_* string literal with its file:line
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECOMP = os.path.join("third_party", "ps2recomp")
HEADER = os.path.join(ROOT, RECOMP, "ps2xShared", "include", "ps2x", "knobs.h")
DOC = os.path.join(ROOT, "docs", "KNOBS.md")

# Where a shipped executable's source lives. ps2xTest is scanned separately (its getenv reads only).
SHIPPED_TREES = [os.path.join(RECOMP, "ps2xRuntime", "src"), os.path.join(RECOMP, "ps2xRuntime", "include"),
                 os.path.join(RECOMP, "ps2xIOP"), os.path.join(RECOMP, "ps2xShared"), os.path.join(RECOMP, "ps2xLauncher")]
TEST_TREE = os.path.join(RECOMP, "ps2xTest")
HARNESS_PATHS = ["tools_py", os.path.join("scripts", "parity"), "run.sh"]

REGISTRY_FILE = "knobs.h"          # its rows are the registry, not reads
SWITCH_FILE = "knobs.cpp"          # the one file that may getenv("PS2X_DEV")

# Names the harness uses that no C++ reads.
HARNESS_ONLY = {"PS2X_RUN_LOG", "PS2X_TEST_REPEAT", "PS2X_SOCOM2_RSA_KEY_B"}
# PS2X_* tokens in harness files that are not environment names at all.
NOT_KNOBS = {"PS2X_"}
# ps2xTest fixtures that are set and read back by one test and mean nothing to the runtime.
TEST_FIXTURE_PREFIXES = ("PS2X_BARE_TEST_",)

# Sprint 9 Goal 3 Task 4: files that still call getenv("PS2X_...") directly. Each batch takes its files off
# this list in the commit that migrates them; test_knobs_registry fails if a listed file has no raw read left,
# and if an unlisted file has one. When the set is empty, delete this comment and leave the empty set.
RAW_GETENV_PENDING = {
    "third_party/ps2recomp/ps2xIOP/src/modules/snd989.cpp",
    "third_party/ps2recomp/ps2xLauncher/src/main.cpp",
    "third_party/ps2recomp/ps2xRuntime/include/ps2_runtime_macros.h",
    "third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_caps.h",
    "third_party/ps2recomp/ps2xRuntime/include/runtime/host_gamepad.h",
    "third_party/ps2recomp/ps2xRuntime/include/runtime/host_gamepad_select.h",
    "third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/EeScheduler.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/HleStats.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/CD.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/MPEG.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/MemoryCard.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/Pad.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Syscalls/FileIO.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_frontend.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/gs/ps2_gif_arbiter.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/host_mic.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/ps2_audio.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/ps2_memory.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/ps2_pad.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/ps2_vif1_interpreter.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/snd989_mixer.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/socom2_hostnet.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/socom2_libnetb.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_lower.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_upper.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/main.cpp",
}

_ROW = re.compile(r'^\s*X\("(PS2X_[A-Z0-9_]+)",\s*(\w+),\s*(\w+),\s*"([^"]*)",\s*"([^"]*)"\)', re.M)
_LITERAL = re.compile(r'"(PS2X_[A-Z0-9_]+)(?=["=])')
_RAW_GETENV = re.compile(r'getenv\s*\(\s*"PS2X_')
_TEST_READ = re.compile(r'getenv\s*\(\s*"(PS2X_[A-Z0-9_]+)"')
_TOKEN = re.compile(r'PS2X_[A-Z0-9_]*')
_ACCESSOR = re.compile(r'ps2x::(knobOn|knob)\s*\(\s*"(PS2X_[A-Z0-9_]+)"')
# A knob read that initialises a namespace-scope object runs before main(), where --dev has not been seen. This
# tree names its globals g_ and writes file-level statics at column 0; a function-local static is indented
# and called s_.
_EARLY = re.compile(r'^(?:static\b.*|\s*(?:static\s+)?(?:const\s+)?[\w:<>]+\s+g_\w+\s*=.*)ps2x::knob')


def table(path=HEADER):
    """[{name, cls, kind, default, meaning}, ...] in the header's order."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return [{"name": m.group(1), "cls": m.group(2), "kind": m.group(3), "default": m.group(4), "meaning": m.group(5)}
            for m in _ROW.finditer(text)]


def _files(root, trees, suffixes=(".cpp", ".h")):
    for tree in trees:
        top = os.path.join(root, tree)
        if os.path.isfile(top):
            yield top
            continue
        for folder, dirs, names in os.walk(top):
            dirs[:] = [d for d in dirs if not d.startswith("build") and d != "__pycache__"]
            for name in sorted(names):
                if name.endswith(suffixes):
                    yield os.path.join(folder, name)


def _lines(path):
    # latin-1: three files in the tree carry a byte that is not UTF-8, and every name we look for is ASCII.
    with open(path, "r", encoding="latin-1") as fh:
        return fh.read().split("\n")


def _rel(root, path):
    return os.path.relpath(path, root).replace("\\", "/")


def literals(root=ROOT):
    """{name: [file:line, ...]} for every "PS2X_NAME" / "PS2X_NAME=..." string literal in the shipped trees."""
    found = {}
    for path in _files(root, SHIPPED_TREES):
        if os.path.basename(path) == REGISTRY_FILE:
            continue
        for number, line in enumerate(_lines(path), 1):
            for name in _LITERAL.findall(line):
                found.setdefault(name, []).append("%s:%d" % (_rel(root, path), number))
    return found


def raw_getenv_sites(root=ROOT):
    sites = []
    for path in _files(root, SHIPPED_TREES):
        if os.path.basename(path) == SWITCH_FILE:
            continue
        for number, line in enumerate(_lines(path), 1):
            if _RAW_GETENV.search(line):
                sites.append("%s:%d" % (_rel(root, path), number))
    return sites


def test_reads(root=ROOT):
    found = {}
    for path in _files(root, [TEST_TREE]):
        for number, line in enumerate(_lines(path), 1):
            for name in _TEST_READ.findall(line):
                if not name.startswith(TEST_FIXTURE_PREFIXES):
                    found.setdefault(name, []).append("%s:%d" % (_rel(root, path), number))
    return found


def harness_names(root=ROOT):
    found = {}
    for path in _files(root, HARNESS_PATHS, suffixes=(".py", ".sh", ".txt", ".json")):
        rel = _rel(root, path)
        if rel.startswith("tools_py/tests/") or rel == "tools_py/knobs.py":
            continue
        for number, line in enumerate(_lines(path), 1):
            for name in _TOKEN.findall(line):
                if name not in NOT_KNOBS and not name.endswith("_"):
                    found.setdefault(name, []).append("%s:%d" % (rel, number))
    return found


def early_reads(root=ROOT):
    sites = []
    for path in _files(root, SHIPPED_TREES):
        for number, line in enumerate(_lines(path), 1):
            if _EARLY.search(line):
                sites.append("%s:%d" % (_rel(root, path), number))
    return sites


def accessor_mismatches(root=ROOT, rows=None):
    kinds = {r["name"]: r["kind"] for r in (table() if rows is None else rows)}
    out = []
    for path in _files(root, SHIPPED_TREES):
        for number, line in enumerate(_lines(path), 1):
            for accessor, name in _ACCESSOR.findall(line):
                kind = kinds.get(name)
                where = "%s:%d" % (_rel(root, path), number)
                if kind == "Flag" and accessor == "knob":
                    out.append("%s: %s is a Flag and is read with ps2x::knob (use knobOn: the one flag rule)" % (where, name))
                if kind is not None and kind != "Flag" and accessor == "knobOn":
                    out.append("%s: %s is read with ps2x::knobOn but its row says %s" % (where, name, kind))
    return out


def problems(root=ROOT):
    """Every disagreement between the registry and the tree, as sentences. [] is the bar."""
    rows = table(os.path.join(root, os.path.relpath(HEADER, ROOT)))
    by_name = {r["name"]: r for r in rows}
    out = []
    lits = literals(root)
    for name in sorted(lits):
        if name not in by_name:
            out.append("%s is read at %s and has no row in knobs.h" % (name, lits[name][0]))
        elif by_name[name]["cls"] == "Test":
            out.append("%s is class Test and a shipped executable names it at %s" % (name, lits[name][0]))
    reads = test_reads(root)
    for name in sorted(reads):
        if name not in by_name:
            out.append("%s is read by ps2x_tests at %s and has no row in knobs.h" % (name, reads[name][0]))
    for r in rows:
        if r["cls"] == "Test" and r["name"] not in reads:
            out.append("%s is class Test and ps2x_tests does not read it: delete the row" % r["name"])
        if r["cls"] in ("Shipping", "Dev", "Switch") and r["name"] not in lits:
            out.append("%s has a row in knobs.h and no shipped executable reads it: delete the row" % r["name"])
    harness = harness_names(root)
    for name in sorted(harness):
        if name not in by_name and name not in HARNESS_ONLY:
            out.append("%s is used by the harness at %s and the runtime does not know it (a deleted knob, or a typo)"
                       % (name, harness[name][0]))
    pending = {p.replace("\\", "/") for p in RAW_GETENV_PENDING}
    for site in raw_getenv_sites(root):
        if site.rsplit(":", 1)[0] not in pending:
            out.append("%s calls getenv on a PS2X_* name: read it with ps2x::knob (ps2x/knobs.h)" % site)
    for site in early_reads(root):
        out.append("%s reads a knob while initialising a namespace-scope object, before main() has seen --dev: "
                   "make it a function with a function-local static" % site)
    out.extend(accessor_mismatches(root, rows))
    return out


_CLASS_TITLES = [
    ("Shipping", "Shipping settings",
     "Player-facing. Each is a field of `config.json` that the launcher (and a bare run of `socom2`) turns into "
     "this variable. Always honoured. Through the launcher `config.json` wins over an inherited variable; in a "
     "bare run or a harness run the variable wins over `config.json`."),
    ("Switch", "The switch",
     "`PS2X_DEV=1` is the same as `--dev` on the runner's command line. `run.sh`, `scripts/parity/env.sh` and the "
     "parity harness set it; the launcher never does, and it removes inherited `PS2X_*` variables from the "
     "game's environment unless it was itself started with `PS2X_DEV=1`."),
    ("Dev", "Developer knobs",
     "Probes, traces, dumps and A/B switches. **Ignored unless the process is in developer mode**; the game's "
     "`[knobs]` log line names the ones it ignored. A `Presence` knob is switched on by any value, including `0`."),
    ("Test", "Test-only",
     "Read by `ps2x_tests`, never by a shipped executable."),
]


def _cell(text):
    return text.replace("|", "\\|")


def render(rows=None):
    rows = table() if rows is None else rows
    out = ["# Knobs", "",
           "Generated by `python -m tools_py.knobs write` from "
           "`third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h`. **Do not edit**: change the header and "
           "regenerate. `tools_py/tests/test_knobs_registry.py` fails when this file is stale, when the source reads "
           "a `PS2X_*` name that has no row, and when a row is read by nothing.", "",
           "%d names: %s." % (len(rows), ", ".join("%d %s" % (sum(1 for r in rows if r["cls"] == cls), cls)
                                                   for cls, _, _ in _CLASS_TITLES)), ""]
    for cls, title, blurb in _CLASS_TITLES:
        mine = [r for r in rows if r["cls"] == cls]
        if not mine:
            continue
        out += ["## " + title, "", blurb, "", "| Name | Kind | Default | Meaning |", "|---|---|---|---|"]
        for r in mine:
            default = "`%s`" % _cell(r["default"]) if r["default"] else "unset"
            out.append("| `%s` | %s | %s | %s |" % (r["name"], r["kind"], default, _cell(r["meaning"])))
        out.append("")
    out += ["## Harness-only names", "",
            "Used by the scripts and the Python harness; no C++ reads them: " +
            ", ".join("`%s`" % n for n in sorted(HARNESS_ONLY)) + ".", ""]
    return "\n".join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else "check"
    if command == "write":
        with open(DOC, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render())
        print("wrote %s (%d names)" % (os.path.relpath(DOC, ROOT), len(table())))
        return 0
    if command == "sites":
        found = literals()
        for name in sorted(found):
            print("%-36s %s" % (name, " ".join(found[name])))
        return 0
    if command == "check":
        found = problems()
        try:
            with open(DOC, "r", encoding="utf-8") as fh:
                if fh.read() != render():
                    found.append("docs/KNOBS.md is stale: python -m tools_py.knobs write")
        except OSError:
            found.append("docs/KNOBS.md is missing: python -m tools_py.knobs write")
        for line in found:
            print(line)
        return 1 if found else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 3: Generate and run.** `python -m tools_py.knobs write`, then `python -m unittest tools_py.tests.test_knobs_registry -v` — 10 cases pass — then `python -m tools_py.knobs check` exits 0. **What to do with each kind of failure in `test_no_problem_in_the_tree`:** "has no row" for `PS2X_LAUNCHER_API_BASE` → Handoff note 2; "used by the harness … the runtime does not know it" → read the line: a CMake name in a harness file or a name in prose goes into `NOT_KNOBS` with a comment saying what it is, anything else is a real finding for the controller; "calls getenv" on a file not in `RAW_GETENV_PENDING` → the tree moved since `8e5d778`, add the file and say so in the ledger. `early_reads` finds nothing yet (it looks for `ps2x::knob`, and nothing calls it before Task 4). `P + 10`. *[done; 11 cases; the drift handled as this step says (SchedTrace.cpp pending, leakcheck's control string in NOT_KNOBS)]*
- [x] **Step 4: Commit and push.** *[committed; not pushed]*

```bash
git add tools_py/knobs.py tools_py/tests/test_knobs_registry.py docs/KNOBS.md
git commit -m "feat(tools): docs/KNOBS.md generated from knobs.h, and the test that fails on a knob without a row, a row without a read, a raw getenv outside the pending list and a read before main (Sprint 9 Goal 3 Task 2)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- tools_py/knobs.py tools_py/tests/test_knobs_registry.py docs/KNOBS.md
git push
```

---

## Task 3 — `--dev`, the `[knobs]` line, and developer mode in every launcher of the runner  **[Opus]**

Done now, while enforcement is off and none of it can break anything, so that Task 5's gate proves the wiring and Task 7's flip is small.

**Every launcher of the runner in the tree** (`git grep -nE 'run\.sh|runtime_exe\(|Popen\(\[exe' -- tools_py scripts` plus the C++ mains):

| Launcher | How it starts `socom2` | Developer mode comes from |
|---|---|---|
| `run.sh` | `timeout N $EXE game/disc/socom2_game.elf "$@"` | **`export PS2X_DEV="${PS2X_DEV:-1}"`** (this task) |
| `tools_py/parity/drive.py:79` (Windows: the gate, every `drive` script, `sp_death_probe`) | `bash ./run.sh` | `run.sh` |
| `tools_py/parity/online_login_ours.py:90` (every online script: `online_match_ours`, `online_ladder`, the control round, the ladder, `lobby_rate_queue`, `online_control_queue`, `two_machine_readout`) | `bash ./run.sh` | `run.sh` |
| `tools_py/parity/drive.py:96` (Linux: the VM's gate) | `timeout N <runtime_exe> <elf>` | **`hostplatform.dev_env`** (this task) |
| `tools_py/parity/scale_shot.py:151` | `[exe, elf]` | **`child_env` sets it** (this task) |
| `scripts/parity/*.sh` that source `env.sh` (`ladder_frostfire`, `mixed_match`, `online_control_round`, `online_match_frostfire`) | through the Python above | `run.sh`; **`env.sh` exports it too**, so the instrument set and the mode that makes it work live in the same file |
| `tools_py/tests/test_runner_exit_codes.py`, `test_diagnostics_zip.py`, `test_portable_folder.py` | the runner directly, `PS2X_*` stripped | none wanted: they test what a stranger gets |
| `ps2x_tests` (`ps2xTest/src/main.cpp`), `vu1_replay` (`ps2xRuntime/src/tools/vu1_replay.cpp`) | are the process | **`ps2x::knobs::setDevMode(true)` first thing in `main`** (this task) |
| the launcher (`win32_glue.cpp:270-330`, `posix_glue.cpp:241`) | `socom2 socom2_game.elf` with `environmentFor` | **never** (R156); Task 7 adds the filter |
| a player's double-click (`BareRun`) | no argument | never |

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/main.cpp`, `third_party/ps2recomp/ps2xTest/src/main.cpp`, `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp`, `run.sh`, `scripts/parity/env.sh`, `tools_py/parity/hostplatform.py`, `tools_py/parity/drive.py`, `tools_py/parity/scale_shot.py`, `tools_py/tests/test_hostplatform.py`, `tools_py/tests/test_run_sh_exe.py`, `tools_py/tests/test_scale_shot.py`

**Steps:**

- [x] **Step 1: RED (Python).** Append to `tools_py/tests/test_hostplatform.py`, above its `if __name__` block: *[done; the three RED texts as predicted]*

```python
class DevEnvTest(unittest.TestCase):
    """Sprint 9 Goal 3: every harness launch of the runner is a developer-mode launch -- the instruments the
    harness reads (the exported frame, the sampler, the peek rows, the pad file) are Dev knobs."""

    def test_it_sets_the_switch_and_returns_the_same_dict(self):
        env = {"PATH": "x"}
        self.assertIs(hostplatform.dev_env(env), env)
        self.assertEqual(env["PS2X_DEV"], "1")

    def test_an_operators_own_choice_is_left_alone(self):
        self.assertEqual(hostplatform.dev_env({"PS2X_DEV": "0"})["PS2X_DEV"], "0")
```

  Add to `RunShExeTest` in `tools_py/tests/test_run_sh_exe.py` (same fixture; the fake runner prints what it was given):

```python
    def test_run_sh_is_a_developer_mode_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "socom2")
            with open(fake, "w", newline="\n") as fh:
                fh.write("#!/usr/bin/env bash\necho \"dev=${PS2X_DEV:-unset}\"\n")
            os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
            log = os.path.join(tmp, "run.log")
            env = {k: v for k, v in os.environ.items() if k != "PS2X_DEV"}
            env.update({"SOCOM_EXE": fake.replace("\\", "/"), "PS2X_RUN_LOG": log.replace("\\", "/")})
            subprocess.run(["bash", os.path.join(ROOT, "run.sh"), "5"], capture_output=True, text=True,
                           cwd=ROOT, env=env, timeout=60)
            with open(log) as fh:
                self.assertIn("dev=1", fh.read())
            env["PS2X_DEV"] = "0"
            subprocess.run(["bash", os.path.join(ROOT, "run.sh"), "5"], capture_output=True, text=True,
                           cwd=ROOT, env=env, timeout=60)
            with open(log) as fh:
                self.assertIn("dev=0", fh.read(), "an operator can still ask for a stranger's run")
```

  Add to `ChildEnv` in `tools_py/tests/test_scale_shot.py`:

```python
    def test_the_child_is_in_developer_mode(self):
        env = scale_shot.child_env("640x448", latest="out/frame.png", base={})
        self.assertEqual(env["PS2X_DEV"], "1")    # PS2X_HOST_SCREENSHOT_LATEST is a Dev knob
```

  Run the three modules. Expected RED: `AttributeError: module 'tools_py.parity.hostplatform' has no attribute 'dev_env'`; `AssertionError: 'dev=1' not found in 'dev=unset\n'`; `KeyError: 'PS2X_DEV'`.

- [x] **Step 2: GREEN (Python and shell).** *[done]*
  - `tools_py/parity/hostplatform.py`, after `EXE_OVERRIDE_ENV = "SOCOM_EXE"`:

```python
DEV_ENV = "PS2X_DEV"


def dev_env(env):
    """Sprint 9 Goal 3: mark a child environment as a developer-mode launch (in place; returns it). The runner
    honours Dev-class knobs -- every instrument the harness reads -- only with this or --dev. An operator's own
    PS2X_DEV wins, so `PS2X_DEV=0 ./run.sh` is still a stranger's run."""
    env.setdefault(DEV_ENV, "1")
    return env
```

  - `tools_py/parity/drive.py:66`: `env = cd_image_env(dict(os.environ, PS2X_SOCOM2_PAD="1"))` becomes `env = hostplatform.dev_env(cd_image_env(dict(os.environ, PS2X_SOCOM2_PAD="1")))`.
  - `tools_py/parity/scale_shot.py`, in `child_env`, after `env["PS2X_WINDOW_SIZE"] = …`: `env.setdefault("PS2X_DEV", "1")   # the exported frame is a Dev knob (Sprint 9 Goal 3)`.
  - `run.sh`, after the `EXE=` line:

```bash
# Sprint 9 Goal 3: run.sh is a developer's and the harness's launcher, so it is a developer-mode launch -- the
# probes it is used with (PS2X_PEEK, the exported frame, the pad file) are ignored by the game otherwise.
# PS2X_DEV=0 ./run.sh is a stranger's run.
export PS2X_DEV="${PS2X_DEV:-1}"
```

  - `scripts/parity/env.sh`, before the `PS2X_HOST_GAMEPAD` line:

```bash
export PS2X_DEV="${PS2X_DEV:-1}"                            # everything below is a Dev knob (docs/KNOBS.md)
```

- [x] **Step 3: The C++ half.** No RED of its own: `consumeDevFlag`, `setDevMode` and `startupLine` are under Task 1's cases; what is added here is three call sites, and Task 5's gate log is where they are seen. *[done]*
  - `ps2xRuntime/src/main.cpp`: add `#include "ps2x/knobs.h"` with the other `ps2x/` includes. In `main`, directly after `ProcessFatal::installOutOfMemoryHandler();`:

```cpp
    // Sprint 9 Goal 3: --dev, anywhere after argv[0], is developer mode (the same as PS2X_DEV=1): Dev-class
    // knobs are honoured. Taken out of argv here, before anything below looks at argv[1].
    if (ps2x::knobs::consumeDevFlag(argc, argv))
        ps2x::knobs::setDevMode(true);
```

    and directly before the `#if !defined(PLATFORM_VITA) && !defined(__ANDROID__)` that opens the preflight block (after the bare-run `if/else`, so `config.json`'s settings are already in the environment):

```cpp
        // One line, so a bug report says which knobs were in effect and which were ignored (docs/KNOBS.md).
        std::cout << ps2x::knobs::startupLine() << std::endl;
```

  - `ps2xTest/src/main.cpp`: `#include "ps2x/knobs.h"`; first statement after the `setvbuf` line: `ps2x::knobs::setDevMode(true);   // the suite selects reference paths through Dev knobs (below) and tests set more`.
  - `ps2xRuntime/src/tools/vu1_replay.cpp`: `#include "ps2x/knobs.h"`; first statement of `main`: `ps2x::knobs::setDevMode(true);   // the tool steers the runtime through Dev knobs (replaySetEnv)`.
- [x] **Step 4: Run.** The three Python modules pass (`P + 14`); `./build.sh test` exit 0 (`B` unchanged; `vu1_replay`'s nine verify runs are part of it and prove the tool still selects its paths). *[done]*
- [x] **Step 5: Commit and push.** *[committed; not pushed]*

```bash
git commit -m "feat(runtime,harness): --dev and the [knobs] start-up line; run.sh, env.sh, drive.py, scale_shot.py, ps2x_tests and vu1_replay are developer-mode launches -- ahead of the enforcement that will need it (Sprint 9 Goal 3 Task 3)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/src/main.cpp third_party/ps2recomp/ps2xTest/src/main.cpp \
  third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp run.sh scripts/parity/env.sh \
  tools_py/parity/hostplatform.py tools_py/parity/drive.py tools_py/parity/scale_shot.py \
  tools_py/tests/test_hostplatform.py tools_py/tests/test_run_sh_exe.py tools_py/tests/test_scale_shot.py
git push
```

  This commit touches `ps2xRuntime/src/main.cpp`. It is covered by Task 5's gate (R157); it prints one line and accepts one flag.

---

## Task 4 — The migration: eight mechanical batches  **[Opus] x8**

198 direct `getenv("PS2X_…")` calls in 32 files, and 15 reads behind helpers. One subagent per batch, one commit per batch, **no push** (R157). Two batches may run at once only if the controller builds them one after the other; they never share a file.

**The rules, identical for every batch (the brief the subagent gets, with its batch's row and its "Beyond the rule" list):**

1. In the batch's files, every `std::getenv("PS2X_NAME")` becomes `ps2x::knob("PS2X_NAME")` — those characters and nothing else on the line. A line that calls it twice (`std::getenv("X") ? std::atoi(std::getenv("X")) : d`) gets both replaced and is otherwise left alone.
2. A helper that takes the name as a parameter (`traceSkip`, `WavSink::write`, `envOn`, `envFlag`, `envCeiling`) gets `std::getenv(name)` -> `ps2x::knob(name)` in its body. Its callers do not change.
3. `#include "ps2x/knobs.h"` is added after the file's last `#include "…"` of a project header (for a header file: after its own `#include <…>` block).
4. `std::getenv` of anything that is not a `PS2X_*` name (`USERPROFILE`, `HOME`, `PATH`, `BareRun::applyEnvironment`'s `key.c_str()`) is **not touched**.
5. Nothing is reformatted, renamed, reordered or "improved". No default moves. No `knobOn` yet (Task 7).
6. The batch's files come off `RAW_GETENV_PENDING` in `tools_py/knobs.py` in the same commit (a file shared by two batches comes off in the second).
7. **Verification, in this order:** `grep -acE 'getenv\s*\(\s*"PS2X_' <each file>` prints `0`; `python -m unittest tools_py.tests.test_knobs_registry -v` passes (it fails if rule 6 was skipped, and `early_reads` fails it if a namespace-scope read was left behind); `cmake --build third_party/ps2recomp/build-clang --target ps2EntryRunner -- -n | grep -c "Unity/unity_"` prints `0` (batches A1-F; Handoff note 5); `./build.sh test` exit 0 with `B + 10` and the Python total unchanged. The subagent reports the four outputs; the controller commits.
8. `socom2_libnetb.cpp` carries a byte that is not UTF-8: edit it with exact-string replacement only, and check `git diff --stat` shows the line counts this plan predicts and no more.

| Batch | Files | Direct calls | Beyond the rule |
|---|---|---|---|
| **A1** GS backend, first half | `ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` from the top to the line before `void GSGlBackend::refreshRenderTargetsFromShadow(` | 24 | rule 2 for `traceSkip` (`e = std::getenv(env);`); the file stays on the pending list |
| **A2** GS backend, second half, and the GS front | `gs_gl_backend.cpp` from `refreshRenderTargetsFromShadow` to the end; `gs/gs_frontend.cpp`; `gs/ps2_gif_arbiter.cpp`; `include/runtime/gs/gs_gl_caps.h` | 35 + 4 + 1 + 1 | (a), (b) below |
| **B** VU | `vu/ps2_vu1_core.cpp`, `vu/ps2_vu1_lower.cpp`, `vu/ps2_vu1_upper.cpp`, `vu/native/socom2_dispatch_0x1b50.cpp` | 22 + 1 + 1 + 3 | rule 2 for `envCeiling` |
| **C** game overrides | `ps2xRuntime/src/lib/game_overrides_socom2.cpp` | 38 | (c) below |
| **D** kernel, stubs, EE, VIF | `Kernel/EeScheduler.cpp`, `Kernel/HleStats.cpp`, `Kernel/Stubs/CD.cpp`, `Kernel/Syscalls/FileIO.cpp`, `Kernel/Stubs/MemoryCard.cpp`, `Kernel/Stubs/MPEG.cpp`, `ps2_memory.cpp`, `ps2_vif1_interpreter.cpp`, `ps2_runtime.cpp` | 6 + 3 + 1 + 1 + 3 + 3 + 5 + 6 + 10 | rule 2 for `envOn`; (d), (e), (f), (g) below |
| **E** audio, microphone, IOP | `ps2_audio.cpp`, `snd989_mixer.cpp`, `host_mic.cpp`, `ps2xIOP/src/modules/snd989.cpp`, `ps2xIOP/CMakeLists.txt` | 4 + 1 + 5 + 2 | rule 2 for `WavSink::write`; (h) below |
| **F** input, net, the two mains | `socom2_host_input.cpp`, `Kernel/Stubs/Pad.cpp`, `ps2_pad.cpp`, `include/runtime/host_gamepad.h`, `include/runtime/host_gamepad_select.h`, `socom2_hostnet.cpp`, `socom2_libnetb.cpp`, `ps2xRuntime/src/main.cpp`, `ps2xLauncher/src/main.cpp` (the `PS2X_LAUNCHER_SHOT` line only) | 8 + 1 + 1 + 1 + 1 + 2 + 4 + 3 + 1 | rule 2 for `envFlag`; (i), (j) below |
| **H** the header the generated code includes — **last, alone, scheduled (R165)** | `include/ps2_runtime_macros.h`, `ps2_runtime.cpp` | 1 | (k) below; rule 7's `grep -c Unity` prints **467**, which is the point |

**Beyond the rule — the complete text of every edit that is not the one-token replacement.** Each is a read that was a `getenv` on a hot path (Handoff note 6) or ran before `main` (Handoff note 4). None changes what any run does: the environment cannot change under a running game, and no test changes these names.

- **(a)** `gs/gs_frontend.cpp`, in the image-upload path (the line `if (std::getenv("PS2X_GIF_DUMP"))` under the comment "The image-upload HLE writes registers directly"):

```cpp
    static const bool s_gifDump = ps2x::knob("PS2X_GIF_DUMP") != nullptr;   // was a getenv on every image upload
    if (s_gifDump)
```

- **(b)** `gs/ps2_gif_arbiter.cpp`: the namespace-scope `static const bool s_prioritySort = std::getenv("PS2X_GIF_PRIORITY_SORT") != nullptr;` becomes

```cpp
// Read on first use, not while the process is still initialising its statics: main() has not seen --dev by then.
static bool prioritySort()
{
    static const bool s_on = ps2x::knob("PS2X_GIF_PRIORITY_SORT") != nullptr;
    return s_on;
}
```

  and its two uses (`if (m_queueCount == 0u && !s_prioritySort)`, `if (s_prioritySort)`) read `prioritySort()`.

- **(c)** `game_overrides_socom2.cpp`, `socom2LibnetbCall`: `if (std::getenv("PS2X_SOCOM2_NET_TRACE"))` becomes

```cpp
        static const bool s_netTrace = ps2x::knob("PS2X_SOCOM2_NET_TRACE") != nullptr;   // was a getenv on every libnetb RPC
        if (s_netTrace)
```

- **(d)** `Kernel/Stubs/MemoryCard.cpp`: directly after `mcSlot1DirOverride()`'s closing brace, in the same anonymous namespace,

```cpp
        bool mcTraceEnabled()
        {
            static const bool s_on = ps2x::knob("PS2X_MC_TRACE") != nullptr;   // was a getenv on every GetInfo and Sync
            return s_on;
        }
```

  and both `if (std::getenv("PS2X_MC_TRACE")) std::cout << …` lines start `if (mcTraceEnabled()) std::cout << …`.

- **(e)** `ps2_memory.cpp`: line 12, `static const bool g_traceFifo = (std::getenv("PS2X_TRACE_FIFO") != nullptr);`, becomes

```cpp
#include "ps2x/knobs.h"
static bool traceFifo()   // on first use: a namespace-scope read ran before main() had seen --dev
{
    static const bool s_on = ps2x::knob("PS2X_TRACE_FIFO") != nullptr;
    return s_on;
}
```

  and its two uses (`if (g_traceFifo)`, `if (g_traceFifo && mfifoDrain)`) read `traceFifo()`.

- **(f)** `ps2_vif1_interpreter.cpp`: `static const bool g_vif1NoIrqStall = std::getenv("PS2X_VIF1_NO_IRQ_STALL") != nullptr;` becomes

```cpp
static bool vif1NoIrqStall()   // on first use, not before main()
{
    static const bool s_on = ps2x::knob("PS2X_VIF1_NO_IRQ_STALL") != nullptr;
    return s_on;
}
static bool vif1TraceFifo()    // was a getenv at each of the four stall and resume sites
{
    static const bool s_on = ps2x::knob("PS2X_TRACE_FIFO") != nullptr;
    return s_on;
}
```

  `if (!g_vif1NoIrqStall)` reads `if (!vif1NoIrqStall())`, and the four `if (std::getenv("PS2X_TRACE_FIFO"))` read `if (vif1TraceFifo())`.

- **(g)** `ps2_runtime.cpp`, inside the `setVu1MscalCallback` lambda: `if (std::getenv("PS2X_TRACE_VU"))` becomes

```cpp
                                     static const bool s_traceVu = ps2x::knob("PS2X_TRACE_VU") != nullptr;   // was a getenv on every VU1 microprogram start
                                     if (s_traceVu)
```

- **(h)** `ps2xIOP/CMakeLists.txt`: after the `add_library(ps2_iop STATIC …)` block, `target_link_libraries(ps2_iop PRIVATE ps2x_shared)   # Sprint 9 Goal 3: snd989.cpp reads PS2X_MPEG_TRACE through ps2x::knob`. If the file already has a `target_link_libraries(ps2_iop PRIVATE ${CMAKE_DL_LIBS})` inside a platform `if`, leave it and add this one unconditionally above it.

- **(i)** `include/runtime/host_gamepad_select.h`, after `hostPadDeadZone()`:

```cpp
// PS2X_HOST_GAMEPAD_INDEX, read once. It was a getenv on every pad poll in all three pad paths.
inline const char *hostGamepadIndexKnob()
{
    static const char *const s_value = ps2x::knob("PS2X_HOST_GAMEPAD_INDEX");
    return s_value;
}
```

  and the four `hostGamepadSelect(std::getenv("PS2X_HOST_GAMEPAD_INDEX"), …)` calls (`Pad.cpp`, `ps2_pad.cpp`, `socom2_host_input.cpp` twice) pass `hostGamepadIndexKnob()`.

- **(j)** `socom2_libnetb.cpp`: `bool g_verbose = std::getenv("PS2X_SOCOM2_NET_TRACE") != nullptr;` becomes

```cpp
        bool verbose()   // on first use, not before main()
        {
            static const bool s_on = ps2x::knob("PS2X_SOCOM2_NET_TRACE") != nullptr;
            return s_on;
        }
```

  and the eight other occurrences of `g_verbose` in the file read `verbose()` (`grep -ac g_verbose` is 9 before and 0 after).

- **(k)** `include/ps2_runtime_macros.h`: above `inline bool ps2_fpu_trap_enabled()` add the declaration, and change the one line in its body:

```cpp
double ps2_fpu_trap_after_seconds();      // ps2_runtime.cpp: PS2X_FPU_TRAP through ps2x::knob; -1 when it is off
inline bool ps2_fpu_trap_enabled()
{
    static const double s_after = ps2_fpu_trap_after_seconds();
```

  `ps2_runtime.cpp`, directly above the definition of `ps2_fpu_trap_site_ok`:

```cpp
double ps2_fpu_trap_after_seconds()
{
    const char *e = ps2x::knob("PS2X_FPU_TRAP");
    return e ? std::atof(e) : -1.0;
}
```

  The header gains no include — the generated code must not start including `ps2x/knobs.h`. `RAW_GETENV_PENDING` becomes the empty set in this commit.

**Steps (per batch):**

- [x] **A1** — edit, verify (rule 7), controller commits: `git commit -m "refactor(gs): gs_gl_backend's knob reads through ps2x::knob, first half -- no behaviour change (Sprint 9 Goal 3 Task 4 A1)` + trailer `-- third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` *[done]*
- [x] **A2** — `… -- <gs_gl_backend.cpp> <gs_frontend.cpp> <ps2_gif_arbiter.cpp> <gs_gl_caps.h> tools_py/knobs.py` *[done]*
- [x] **B** — `… -- <the four vu files> tools_py/knobs.py` *[done]*
- [x] **C** — `… -- third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp tools_py/knobs.py` *[done]*
- [x] **D** — `… -- <the nine files> tools_py/knobs.py` *[done, ten files: SchedTrace.cpp joined]*
- [x] **E** — `… -- <the four sources> third_party/ps2recomp/ps2xIOP/CMakeLists.txt tools_py/knobs.py` *[done]*
- [x] **F** — `… -- <the nine files> tools_py/knobs.py`. `ps2xLauncher/src/main.cpp` is a file the launcher sessions edit: check `git status` for it first (commit-only-idle-files). *[done; the launcher's constant-named read, and the loopback test's PS2X_DEV=1 (R202)]*
- [x] **H** — after A1-F are committed. `bash scripts/check_quiet_gate.sh`; when the owner is at the desk, ask for the window. The full rebuild is Task 5 Step 1's build; H is committed before it so one build serves both. *[done in the --no-runner tree, which compiles no generated unit: the controller's full build pays R165]*

Every commit message ends with the trailer. Write each pathspec out in full in the actual command; the angle brackets above are this table's files.

---

## Task 5 — One build, one gate, then push — or bisect  **[Judgment]**

- [ ] **Step 1: Build.** `bash scripts/check_quiet_gate.sh`; create `logs/s9_g3_build.sh` (the command set); `scripts/run_detached.sh --owner build --purpose build logs/s9_g3_build.sh logs/s9_g3_build.marker`; poll the marker. Expect a full generated rebuild (batch H): about 10-15 minutes of all cores. `tail -3 logs/s9_g3_build.log` ends `built dist/socom2.exe`.
- [ ] **Step 2: The cheap proofs, before spending a launch.** `./build.sh test` exit 0. `python -m tools_py.knobs check` exit 0 and `python -c "from tools_py import knobs; print(len(knobs.RAW_GETENV_PENDING), len(knobs.raw_getenv_sites()))"` prints `0 0`. One sub-second run: `PS2X_GS_BACKEND=cpu dist/socom2.exe --dev --home logs/s9_g3_nohome; cat logs/s9_g3_nohome/logs/run_*.log` shows `[knobs] dev=1 set: PS2X_GS_BACKEND=cpu` and `exit 68 elf-missing` — `--dev` was taken out of argv before `--home` was looked for.
- [ ] **Step 3: The gate.** Create `logs/s9_g3_batches_gate.sh` (the command set) and start it detached. PASS is `GATE PASS (3/3)` in `logs/parity/gate/s9_g3_batches_gate/summary.txt`, title at its usual 19/23 or better.
- [ ] **Step 4: Read the `[knobs]` lines and keep them.** `grep -h "^\[knobs\]" logs/parity/gate/s9_g3_batches_gate/*.game.log` — paste all three into the ledger. They are this goal's first measurement: **the complete list of knobs the gate depends on**, written by the game itself. Expected on the mission stage: `PS2X_CD_IMAGE`, `PS2X_DEV`, `PS2X_HOST_GAMEPAD`, `PS2X_HOST_SCREENSHOT_LATEST`, `PS2X_MC_DIR`, `PS2X_PC_SAMPLER`, `PS2X_PEEK`, `PS2X_SOCOM2_PAD`. **Anything else on those lines leaked in from the operator's shell despite the job script's `unset` loop — find out how before going on.** None of Task 6's five names may appear (R158 rests on that).
- [ ] **Step 5: On PASS, push** the eight batch commits and Task 3's (`git push`), and record the hashes. **On FAIL, bisect — do not push:**
  1. Re-score first (`python -m tools_py.parity.gate --baseline s9_g3_batches_gate`): a title stage at 18/23 on its known margin is re-run once before anything is blamed (the Goal 2 plan's reserve rule).
  2. Diff the failing stage's `game.log` against `logs/parity/gate/s9_g2_release_gate/` (or the last developer-build gate) for the first line that differs other than timestamps; a knob read that changed meaning shows up as a missing or extra trace line within the first seconds.
  3. Bisect by batch, in the main checkout (no worktree: Global Constraints), with `git revert --no-commit` so nothing is rewritten. **H first, because it is the only batch that touches generated code and every later step is cheap once it is settled:** `git revert --no-commit <H>`, rebuild (full, once), gate `s9_g3_bisect_1`. PASS -> H is the cause, and H is one line (edit (k)): read it. FAIL -> leave H reverted and halve A1-F: `git revert --no-commit <F> <E> <D>` (newest first), runtime-only rebuild (minutes), gate `s9_g3_bisect_2`; halve again for `s9_g3_bisect_3`; `s9_g3_bisect_4` at the latest names the batch. Inside a batch the cause is found by reading, not by launching: a batch is one token repeated plus the listed edits (a)-(k), and the edits are the suspects.
  4. Fix forward under a RED test where one can be written, `git revert --abort` the bisect state, rebuild, and run the gate again as `s9_g3_batches_gate2`. Every bisect gate is a launch: write each into the ledger's budget line.

---

## Task 6 — Delete the five dead knobs and the two ghosts  **[Opus]**

Runtime code is deleted here and the commit is **not gated on its own**: every deleted block is reachable only with its knob set, and Task 5 Step 4 is the record that the gate sets none of them (R158). It is committed locally and rides on Task 7's gate.

**Files:** `ps2xRuntime/src/lib/gs/gs_gl_backend.cpp`, `ps2xRuntime/src/lib/Kernel/Stubs/MPEG.cpp`, `ps2xRuntime/src/lib/ps2_memory.cpp`, `ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp`, `ps2xShared/include/ps2x/knobs.h`, `README.md`, `docs/KNOBS.md`

- [x] **Step 1: RED.** Delete the five rows from `knobs.h` (`PS2X_GS_GL_DEBUG_NODEPTH`, `PS2X_GS_PROBE`, `PS2X_GS_TEX_FROM_CPU`, `PS2X_MPEG_PIC_TRACE`, `PS2X_TIMER_TRACE`). `python -m unittest tools_py.tests.test_knobs_registry` fails with five `… is read at … and has no row in knobs.h` and `docs/KNOBS.md is stale`. That is the RED: the registry now says they are gone and the source disagrees. *[done]*
- [x] **Step 2: GREEN — the deletions**, each found by its text: *[done; the second MPEG block was not identical to the first (s_calls, the queue depth) and went too; README had already lost both ghosts]*
  - `gs_gl_backend.cpp`, **`PS2X_GS_TEX_FROM_CPU`**: delete the two comment lines starting `// Experiment: PS2X_GS_TEX_FROM_CPU=1 decodes from` and the four lines `static const bool s_fromCpu = …;`, `static std::vector<uint8_t> s_cpuCopy;`, `if (s_fromCpu)`, `m_cpu->SnapshotVram(s_cpuCopy);`; the next line becomes `uint8_t *vram = m_shadowMemory.data();`. `grep -an "s_fromCpu\|s_cpuCopy"` prints nothing afterwards. `GSCpuBackend::SnapshotVram` stays (the display dump uses it).
  - `gs_gl_backend.cpp`, **`PS2X_GS_PROBE`**: delete the whole brace block that follows `glDrawArrays(GL_TRIANGLES, 0, static_cast<GLsizei>(m_vertices.size()));` — from its `{` and the comment `// PS2X_GS_PROBE=<frame>: for 400 frames from there …` through the matching `}` that closes after the `[gs-gl probe]` `fprintf`. The next statement is `if (debugThis && m_vertices.size() >= 6)`.
  - `gs_gl_backend.cpp`, **`PS2X_GS_GL_DEBUG_NODEPTH`**: delete the three lines `static const bool s_noDepth = …;`, `if (s_noDepth)`, `glDisable(GL_DEPTH_TEST);`.
  - `MPEG.cpp`, **`PS2X_MPEG_PIC_TRACE`**: in **both** blocks (they are identical; `grep -an s_picTrace` finds 4 lines) delete the inner brace block `{ static const bool s_picTrace = …; static uint64_t s_frames = 0; ++s_frames; if (s_picTrace && …) std::fprintf(…); }` whole. Check `s_frames` has no other use in either function before deleting it (`grep -an "s_frames"` shows only those blocks).
  - `ps2_memory.cpp`, **`PS2X_TIMER_TRACE`**: under `case kEeTimerCountOffset:` delete the comment `// PS2X_TIMER_TRACE=1: once a second …`, the `static const bool s_trace = …;` line and the whole `if (s_trace && timerIndex == 0u) { … }` block with the statics it declares. The read of the counter that follows is untouched.
  - **The ghosts.** `ps2_vu1_core.cpp`: the comment line `// PS2X_VU1_XGKICK_IMMEDIATE=1: copy the whole packet at kick time (what most emulators do)` names a knob that does not exist; reword it to `// The default: copy the whole packet at kick time (what most emulators do).` `gs_gl_backend.cpp`: in the comment `// Counted with PS2X_GS_COUNT_MB over a title_menu.txt run`, replace `with PS2X_GS_COUNT_MB` by `with a temporary counter`. `README.md:89`: delete `` `PS2X_VU1_XGKICK_IMMEDIATE`, `` and, on the line above, `` , `PS2X_GS_TEX_FROM_CPU` `` (Task 9 replaces the whole paragraph; this keeps the tree true in between).
- [x] **Step 3:** `python -m tools_py.knobs write`; `test_knobs_registry` passes; change the `Knobs` suite's `kTableSize >= 130u` comment to say 129 shipped names; `./build.sh test` exit 0. *[done; 149 rows]*
- [x] **Step 4: Commit (local).** *[committed on agent/knobs]*

```bash
git commit -m "refactor(runtime): five dead knobs deleted with the code they guarded (GS_TEX_FROM_CPU retired in STATUS, GS_PROBE and GS_GL_DEBUG_NODEPTH one-off probes, MPEG_PIC_TRACE and TIMER_TRACE never documented); two names that were only prose removed (Sprint 9 Goal 3 Task 6)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/MPEG.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_memory.cpp third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp \
  third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h third_party/ps2recomp/ps2xTest/src/knobs_tests.cpp README.md docs/KNOBS.md
```

---

## Task 7 — The flip  **[Judgment]** (the code is written out; the launches and their reading are the controller's)

The one task that changes behaviour, and the one that can break the harness. Five changes, one commit, one gate, one poisoned launch, one control round.

**Files:**
- Modify: `ps2xShared/src/knobs.cpp`, `ps2xShared/include/ps2x/knobs.h` (eight `Kind`s), `ps2xRuntime/src/lib/gs/ps2_gif_arbiter.cpp`, `ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (3 sites), `ps2xRuntime/src/lib/ps2_vif1_interpreter.cpp`, `ps2xRuntime/src/lib/vu/ps2_vu1_upper.cpp`, `ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp`, `ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp`, `ps2xRuntime/src/lib/game_overrides_socom2.cpp`, `ps2xShared/include/launcher/launcher_config.h`, `ps2xShared/src/launcher_config.cpp`, `ps2xLauncher/src/win32_glue.cpp`, `ps2xLauncher/src/posix_glue.cpp`, `ps2xShared/include/launcher/diagnostics.h`, `ps2xShared/src/diagnostics.cpp`, `ps2xTest/src/knobs_tests.cpp`, `ps2xTest/src/launcher_tests.cpp`, `ps2xTest/src/diagnostics_tests.cpp`, `docs/KNOBS.md`
- Create: `tools_py/tests/test_knobs_line.py`; `logs/s9_g3_gating_gate.sh`, `logs/s9_g3_poisoned_env.sh` (ignored)

**Steps:**

- [ ] **Step 1: RED (C++).** Append four cases. In `knobs_tests.cpp`, inside the `Knobs` case:

```cpp
        tc.Run("enforcement is on by default: a process that says nothing is a stranger's", [](TestCase &t)
        {
            // ps2x_tests' main calls setDevMode(true) and nothing calls setEnforcement: what is read here is the default.
            t.IsTrue(ps2x::knobs::enforcement(), "Sprint 9 Goal 3 Task 7");
        });

        tc.Run("the behaviour-changing switches are Flags: 0 no longer switches one on", [](TestCase &t)
        {
            for (const char *name : {"PS2X_GIF_PRIORITY_SORT", "PS2X_GS_NO_DIRTY_REFRESH", "PS2X_GS_NO_TEX_REVALIDATE", "PS2X_GS_NO_ZTEST",
                                     "PS2X_SOCOM2_PAD", "PS2X_VIF1_NO_IRQ_STALL", "PS2X_VU1_FMAC_CHECK", "PS2X_VU1_XGKICK_CYCLE_EXACT"})
            {
                const ps2x::knobs::Entry *e = ps2x::knobs::find(name);
                t.IsTrue(e != nullptr && e->kind == ps2x::knobs::Kind::Flag, std::string(name) + ": Kind::Flag, read with knobOn");
            }
            const ps2x::knobs::Entry *pad = ps2x::knobs::find("PS2X_SOCOM2_PAD");
            t.IsTrue(pad != nullptr && std::string(pad->dflt) == "1", "the pad is on unless someone turns it off (R160)");
        });
```

  In `launcher_tests.cpp`, beside the existing `mergeEnvironment` case:

```cpp
        tc.Run("mergeEnvironment: an inherited PS2X_* variable reaches the game only when the launcher is in developer mode (R156)", [](TestCase &t)
        {
            const char *base[] = {"PATH=/bin", "PS2X_GS_BACKEND=cpu", "ps2x_peek=0x100:4", "PS2X_GS_SCALE=4", "PS2XX=kept", nullptr};
            const std::vector<std::string> ours = {"PS2X_GS_SCALE=2"};
            auto has = [](const std::vector<std::string> &env, const char *kv)
            { return std::find(env.begin(), env.end(), std::string(kv)) != env.end(); };

            const std::vector<std::string> stranger = launcher::mergeEnvironment(base, ours, false);
            t.Equals(static_cast<int>(stranger.size()), 3, "PATH, the near-miss name, and ours");
            t.IsTrue(has(stranger, "PATH=/bin") && has(stranger, "PS2XX=kept") && has(stranger, "PS2X_GS_SCALE=2"), "what belongs there");
            t.IsFalse(has(stranger, "PS2X_GS_BACKEND=cpu"), "a forgotten probe does not reach the game");
            t.IsFalse(has(stranger, "ps2x_peek=0x100:4"), "Windows variable names are case-insensitive, so the filter is too");

            const std::vector<std::string> developer = launcher::mergeEnvironment(base, ours, true);
            t.Equals(static_cast<int>(developer.size()), 5, "everything inherited, ours winning by key as before");
            t.IsTrue(has(developer, "PS2X_GS_BACKEND=cpu") && has(developer, "PS2X_GS_SCALE=2") && !has(developer, "PS2X_GS_SCALE=4"), "as before");

            t.IsTrue(launcher::isKnobKey("PS2X_MC_DIR") && launcher::isKnobKey("ps2x_mc_dir"), "the prefix, either case");
            t.IsFalse(launcher::isKnobKey("PS2XX") || launcher::isKnobKey("PS2") || launcher::isKnobKey(""), "and nothing shorter or different");
        });
```

  In `diagnostics_tests.cpp`, inside the `Diagnostics` case:

```cpp
        tc.Run("versions.txt carries the game's [knobs] line, or says there was none", [](TestCase &t)
        {
            diag::Inputs in = inputs();
            in.logText = std::string(kLog) + "[knobs] dev=0 set: PS2X_GS_SCALE=2 | ignored without --dev: PS2X_GS_BACKEND\r\n";
            t.IsTrue(diag::versionsText(in).find("knobs: [knobs] dev=0 set: PS2X_GS_SCALE=2 | ignored without --dev: PS2X_GS_BACKEND\n") != std::string::npos,
                     "the line as the game wrote it, CR dropped");
            t.IsTrue(diag::versionsText(inputs()).find("knobs: no [knobs] line in this log\n") != std::string::npos, "an older runner, or a run that died first");
            t.Equals(diag::knobsLine("[audio] only\n"), std::string("no [knobs] line in this log\n"), "the function by itself");
        });
```

  (`diag` is that file's existing alias for the diagnostics namespace; use whatever name the file already uses.) Expected RED: `no member named 'isKnobKey' in namespace 'launcher'`, `no matching function for call to 'mergeEnvironment'`, `no member named 'knobsLine'`; after those compile, `enforcement is on by default` fails and the eight-Flag case fails on all eight.

- [ ] **Step 2: RED (Python).** Create `tools_py/tests/test_knobs_line.py`:

```python
"""Sprint 9 Goal 3: what a stranger's environment can do to the runner -- nothing -- and how the log says so.
Sub-second bare runs that stop at exit 68 before a window opens (as test_runner_exit_codes does); they obey the
quiet gate like every suite. Skipped where there is no runner build."""
import glob
import os
import subprocess
import tempfile
import unittest

from tools_py.parity import hostplatform

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXE = os.path.join(ROOT, hostplatform.runtime_exe())


@unittest.skipUnless(os.path.isfile(EXE), "no runner build at " + EXE)
class KnobsLineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self._tmp.name, "outer", "home")
        os.makedirs(self.home)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("PS2X_")}

    def tearDown(self):
        self._tmp.cleanup()

    def _knobs_line(self, *args, **extra):
        subprocess.run([EXE, *args, "--home", self.home], capture_output=True, text=True, errors="replace",
                       timeout=60, env=dict(self.env, **extra), cwd=self.home)
        logs = sorted(glob.glob(os.path.join(self.home, "logs", "run_*.log")))
        self.assertTrue(logs, "the bare run writes logs/run_<stamp>.log")
        with open(logs[-1], "r", errors="replace") as fh:
            lines = [line.rstrip("\r\n") for line in fh if line.startswith("[knobs]")]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def test_a_stranger_with_a_forgotten_probe_is_told_it_was_ignored(self):
        line = self._knobs_line(PS2X_GS_BACKEND="cpu", PS2X_GS_NO_ZTEST="1")
        self.assertTrue(line.startswith("[knobs] dev=0 set:"), line)
        self.assertIn("| ignored without --dev: PS2X_GS_BACKEND PS2X_GS_NO_ZTEST", line)
        self.assertNotIn("PS2X_GS_BACKEND=cpu", line)

    def test_the_dev_flag_opens_them_and_may_stand_before_home(self):
        line = self._knobs_line("--dev", PS2X_GS_BACKEND="cpu")
        self.assertTrue(line.startswith("[knobs] dev=1 set:"), line)
        self.assertIn("PS2X_GS_BACKEND=cpu", line)
        self.assertNotIn("ignored", line)

    def test_the_variable_is_the_same_switch(self):
        line = self._knobs_line(PS2X_DEV="1", PS2X_GS_BACKEND="cpu")
        self.assertIn("dev=1", line)
        self.assertIn("PS2X_DEV=1", line)
        self.assertIn("PS2X_GS_BACKEND=cpu", line)

    def test_a_shipping_setting_needs_no_switch_and_a_default_is_not_news(self):
        line = self._knobs_line(PS2X_GS_SCALE="2", PS2X_AUDIO_VOLUME="100")
        self.assertIn("PS2X_GS_SCALE=2", line)
        self.assertNotIn("PS2X_AUDIO_VOLUME", line)
        self.assertNotIn("ignored", line)


if __name__ == "__main__":
    unittest.main()
```

  A bare run with no `config.json` applies `environmentFor(Config{})`, so every line also lists the launcher's own non-default values (`PS2X_WINDOW_SIZE=1280x896`, `PS2X_PAD_CROUCH_SHORTCUT=l3`, `PS2X_MC_DIR=player`, `PS2X_SOCOM2_SERVER=…`) — the assertions above are all `assertIn`/`assertNotIn` for that reason. Expected RED against the Task 5 runner: the first case fails with `'[knobs] dev=1 set: … PS2X_GS_BACKEND=cpu …'` (enforcement is off, everyone is a developer).

- [ ] **Step 3: GREEN — enforcement.** `knobs.cpp`: `std::atomic<bool> g_enforce{false};   // Sprint 9 Goal 3 Task 7 turns this on` becomes `std::atomic<bool> g_enforce{true};    // a process that says nothing is a stranger's (Sprint 9 Goal 3 Task 7)`. In `knobs.h` the comment above `enforcement()` becomes `// On. setEnforcement(false) exists for the Knobs suite, which proves what off meant.`
- [ ] **Step 4: GREEN — the eight switches (R160, R161).** In `knobs.h` change `Presence` to `Flag` and the default to `"0"` on seven rows, and `PS2X_SOCOM2_PAD` to `X("PS2X_SOCOM2_PAD", Shipping, Flag, "1", "The libpad2 HLE and host input path; 0 boots with no controller.")`. The eight sites:

| Site (by its text) | Becomes |
|---|---|
| `ps2_gif_arbiter.cpp`: `static const bool s_on = ps2x::knob("PS2X_GIF_PRIORITY_SORT") != nullptr;` | `static const bool s_on = ps2x::knobOn("PS2X_GIF_PRIORITY_SORT");` |
| `gs_gl_backend.cpp`: `static const bool s_noRefresh = ps2x::knob("PS2X_GS_NO_DIRTY_REFRESH") != nullptr;` | `… = ps2x::knobOn("PS2X_GS_NO_DIRTY_REFRESH");` |
| `gs_gl_backend.cpp`: `static const bool s_noRevalidate = ps2x::knob("PS2X_GS_NO_TEX_REVALIDATE") != nullptr;` | `… = ps2x::knobOn("PS2X_GS_NO_TEX_REVALIDATE");` |
| `gs_gl_backend.cpp`: `static const bool s_noZtest = ps2x::knob("PS2X_GS_NO_ZTEST") != nullptr;` | `… = ps2x::knobOn("PS2X_GS_NO_ZTEST");` |
| `ps2_vif1_interpreter.cpp`, `vif1NoIrqStall()`: `… = ps2x::knob("PS2X_VIF1_NO_IRQ_STALL") != nullptr;` | `… = ps2x::knobOn("PS2X_VIF1_NO_IRQ_STALL");` |
| `ps2_vu1_upper.cpp`: `static const bool s_check = ps2x::knob("PS2X_VU1_FMAC_CHECK") != nullptr;` | `… = ps2x::knobOn("PS2X_VU1_FMAC_CHECK");` |
| `ps2_vu1_core.cpp`: `static const bool s_immediate = ps2x::knob("PS2X_VU1_XGKICK_CYCLE_EXACT") == nullptr;` and `socom2_dispatch_0x1b50.cpp`: `static const bool immediate = ps2x::knob("PS2X_VU1_XGKICK_CYCLE_EXACT") == nullptr;` | `… = !ps2x::knobOn("PS2X_VU1_XGKICK_CYCLE_EXACT");` (both) |
| `game_overrides_socom2.cpp`, `socom2PadEnabled()`: `static const bool on = (ps2x::knob("PS2X_SOCOM2_PAD") != nullptr);` | `static const bool on = ps2x::knobOn("PS2X_SOCOM2_PAD", true);   // R160: on unless 0` — and the comment above it becomes `// The pad HLE is on by default (Sprint 9 Goal 3, R160); PS2X_SOCOM2_PAD=0 boots with no controller, as every boot did before input worked.` |

  `ps2xTest/src/main.cpp:66-72`'s comment about `PS2X_VU1_XGKICK_CYCLE_EXACT` ("presence-tested … setting it to 0 does NOT turn it back off") is now false: replace those seven lines with `//   PS2X_VU1_XGKICK_CYCLE_EXACT: XGKICK copies the whole packet at kick time by default; the PATH1 test asserts the per-cycle model. A Flag since Sprint 9 Goal 3: 0 in the environment selects the immediate copy for an A/B.` `test_knobs_registry`'s `accessor_mismatches` is what fails if a site and its row disagree.

- [ ] **Step 5: GREEN — the launcher's filter (R156).** `launcher_config.h`, replacing the `mergeEnvironment` declaration:

```cpp
    // Sprint 9 Goal 3 (R156): is this environment key one of ours? "PS2X_" as a prefix, either case (Windows
    // variable names are case-insensitive).
    bool isKnobKey(const std::string &key);
    // The child's environment: `base` minus whatever `ours` overrides, plus `ours`. With keepInheritedKnobs false
    // an inherited PS2X_* variable the launcher did not itself choose is dropped, so a stranger's forgotten
    // variable cannot reach the game; the launcher passes true only when it was itself started in developer mode.
    std::vector<std::string> mergeEnvironment(const char *const *base, const std::vector<std::string> &ours, bool keepInheritedKnobs);
    inline std::vector<std::string> mergeEnvironment(const char *const *base, const std::vector<std::string> &ours)
    {
        return mergeEnvironment(base, ours, true);   // the pure merge, as the existing cases test it
    }
```

  `launcher_config.cpp`: above `mergeEnvironment`,

```cpp
    bool isKnobKey(const std::string &key)
    {
        static const char kPrefix[] = "PS2X_";
        if (key.size() < sizeof(kPrefix) - 1)
            return false;
        for (size_t i = 0; i + 1 < sizeof(kPrefix); ++i)
        {
            char c = key[i];
            if (c >= 'a' && c <= 'z')
                c = static_cast<char>(c - 'a' + 'A');
            if (c != kPrefix[i])
                return false;
        }
        return true;
    }
```

  give `mergeEnvironment` its third parameter, and change `if (!overridden)` to `if (!overridden && (keepInheritedKnobs || !isKnobKey(key)))`. `posix_glue.cpp:241`: `launcher::mergeEnvironment(environ, launcher::environmentFor(config), ps2x::knobs::devMode())` with `#include "ps2x/knobs.h"`. `win32_glue.cpp`: `#include "ps2x/knobs.h"`; before the `GetEnvironmentStringsW` loop `const bool keepInheritedKnobs = ps2x::knobs::devMode();   // R156`; and `if (!overridden && !key.empty() && key[0] != '=')` becomes `if (!overridden && !key.empty() && key[0] != '=' && (keepInheritedKnobs || !launcher::isKnobKey(key)))`. When the launcher *is* in developer mode `PS2X_DEV=1` is itself inherited, so the game is too.

- [ ] **Step 6: GREEN — the diagnostics line.** `diagnostics.h`, after `crashRecord`: `std::string knobsLine(const std::string &logText);   // the game's [knobs] line(s), or a sentence saying there is none`. `diagnostics.cpp`, after `crashRecord`:

```cpp
    std::string knobsLine(const std::string &logText)
    {
        const std::string lines = linesStartingWith(logText, {"[knobs]"});
        return lines.empty() ? std::string("no [knobs] line in this log\n") : lines;
    }
```

  and in `versionsText`, after the `exit codes known:` line: `out += "knobs: " + knobsLine(in.logText);`. The line holds no directory (`describe` cuts a `Path` to its file name) and the zip's `scrub` runs over it like every other entry. Goal 8's bug report takes its log through the same `clipLog`/`scrub`, so the line travels with a report for free.
- [ ] **Step 7: Build and the cheap proofs.** `python -m tools_py.knobs write`. Build through `logs/s9_g3_build.sh` (runtime only; `grep -c Unity` is 0). `./build.sh test` exit 0: `B + 14`, Python `P + 18`. `test_knobs_line` passes against the new runner. **The harness's own proof before a launch is spent:** `PS2X_PEEK=0x100:4 ./run.sh 3 >/dev/null; grep -h "^\[knobs\]" logs/latest.log` shows `dev=1 … PS2X_DEV=1 … PS2X_PEEK=0x100:4` (three seconds, no window reached; it obeys the quiet gate and the loop lock).
- [ ] **Step 8: The gate.** `logs/s9_g3_gating_gate.sh`, detached. PASS 3/3. Then `grep -h "^\[knobs\]" logs/parity/gate/s9_g3_gating_gate/*.game.log`: each reads `dev=1`, lists the same names as Task 5 Step 4 (the pad now absent when the harness still sends `1`, because `1` is its default), and has **no `ignored` clause** — an `ignored` clause in a gate log means a harness launch that is not in developer mode, which is the failure this task exists to catch. On FAIL: the suspects are, in order, a harness path that does not reach `run.sh` or `dev_env` (the log says `dev=0`), one of the eight switches (the log names it under `set:`), and the empty-is-unset rule (R162: look for a knob the harness sets to `""` on purpose — `online_login_ours.py:75` does for `PS2X_SOCOM2_RSA_KEY`, where empty and unset both mean key A).
- [ ] **Step 9: The poisoned launch — R163 (a).** Create `logs/s9_g3_poisoned_env.sh`:

```bash
#!/usr/bin/env bash
# Sprint 9 Goal 3: a stranger's run with six forgotten probes in the environment. No run.sh (it would set
# PS2X_DEV), no harness: the runner, the disc and the card folder the launcher would have sent, and the poison.
export PATH="/usr/bin:/mingw64/bin:$HOME/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
for v in $(compgen -e | grep -E '^(PS2X|SOCOM)_'); do unset "$v"; done
ISO="$(python -c 'from tools_py.parity import hostplatform; print(hostplatform.iso_path())')"
CARD="$PWD/logs/s9_g3_poisoned_card"; mkdir -p "$CARD"
LOG="$PWD/logs/s9_g3_poisoned_env.log"
export PATH="$PWD/tools/llvm-mingw/bin:$PATH"
PS2X_CD_IMAGE="$ISO" PS2X_MC_DIR="$CARD" \
PS2X_GS_BACKEND=cpu PS2X_GS_NO_ZTEST=1 PS2X_EE_ROUND=nearest PS2X_VU1_XGKICK_CYCLE_EXACT=1 PS2X_PC_SAMPLER=1 PS2X_PEEK=0x408c58:4 \
  timeout 90 dist/socom2.exe game/disc/socom2_game.elf > "$LOG" 2>&1
rc=$?
echo "done $rc" > logs/s9_g3_poisoned_env.done
exit 0
```

  `scripts/run_detached.sh --owner gate --purpose launch logs/s9_g3_poisoned_env.sh logs/s9_g3_poisoned_env.marker`. **PASS is all five:** `done 124` (alive at the timeout); the line `[knobs] dev=0 set: PS2X_CD_IMAGE=… PS2X_MC_DIR=s9_g3_poisoned_card | ignored without --dev: PS2X_EE_ROUND PS2X_GS_BACKEND PS2X_GS_NO_ZTEST PS2X_PC_SAMPLER PS2X_PEEK PS2X_VU1_XGKICK_CYCLE_EXACT`; `grep -c "^\[gs-gl\] initialised" "$LOG"` is 1 (the GL backend, not the CPU one that was asked for); `grep -c "^\[pc-sampler\]\|^\[peek\]" "$LOG"` is 0; `grep -c "^\[crash\]\|^\[terminate\]" "$LOG"` is 0. Record the five answers in the ledger and the Results table.
- [ ] **Step 10: The online control round — R166.** In a window the owner is away (Goal 5's rule), under the loop lock, against our own server only: `bash scripts/parity/online_control_round.sh "foxhunt"` with stamp `s9_g3_control` as that script takes it. PASS is the round's usual verdict (the round runs to its clock, no kill expected) **and** both instances' logs showing `[knobs] dev=1` with `PS2X_SOCOM2_INPUT_FILE`, `PS2X_WINDOW_TITLE`, `PS2X_PEEK`, `PS2X_CALL_TRACE` under `set:` and, on instance B, `PS2X_SOCOM2_UDP_SHIFT=2` and `PS2X_MC_DIR`. If no away window comes before the goal otherwise closes, the round is carried as an open item in Task 9 with its command, and `docs/KNOWN.md` says "believed, not proven: the online harness under enforcement" — it is not skipped silently.
- [ ] **Step 11: Commit and push** (after Step 8's PASS; Steps 9-10 are recorded in the close-out).

```bash
git add tools_py/tests/test_knobs_line.py
git commit -m "feat(runtime,launcher): a stranger's environment cannot change the game -- Dev knobs need --dev or PS2X_DEV, eight 'X=0 switches it on' traps become flags, the pad is on by default, the launcher stops handing inherited PS2X_* to the game, versions.txt carries the [knobs] line (Sprint 9 Goal 3 Task 7)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared/src/knobs.cpp third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/ps2_gif_arbiter.cpp third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/ps2_vif1_interpreter.cpp third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_upper.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp \
  third_party/ps2recomp/ps2xShared/include/launcher/launcher_config.h third_party/ps2recomp/ps2xShared/src/launcher_config.cpp \
  third_party/ps2recomp/ps2xLauncher/src/win32_glue.cpp third_party/ps2recomp/ps2xLauncher/src/posix_glue.cpp \
  third_party/ps2recomp/ps2xShared/include/launcher/diagnostics.h third_party/ps2recomp/ps2xShared/src/diagnostics.cpp \
  third_party/ps2recomp/ps2xTest/src/knobs_tests.cpp third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp \
  third_party/ps2recomp/ps2xTest/src/diagnostics_tests.cpp third_party/ps2recomp/ps2xTest/src/main.cpp \
  tools_py/tests/test_knobs_line.py docs/KNOBS.md
git push
```

### Results (filled by Tasks 5, 7 and 8; a row left empty carries its reason)

| Measurement | Value | Artefact |
|---|---|---|
| `P` / `B` before Task 1 | 1622 / 722 in the worktree (1624 / 722 the main tree's last count) | the execution ledger |
| Names in the registry after Task 1 / after Task 6 | **154 / 149** (18 Shipping, 122 Dev, 8 Test, 1 Switch after Task 6; the plan's 143 / 138 counted 134 shipped names at `8e5d778`, the tree at `a3aa99a` reads 145) | `docs/KNOBS.md` |
| `s9_g3_batches_gate` | | `logs/parity/gate/s9_g3_batches_gate/summary.txt` |
| The gate's own knobs, per stage (the `[knobs]` lines) | | ledger |
| `s9_g3_gating_gate` | | |
| Poisoned launch: exit / ignored list / GL initialised / sampler rows / crash lines | | `logs/s9_g3_poisoned_env.log` |
| `s9_g3_control` | | |
| Linux: C++ suite, Python suite, `test_knobs_line` on `dist-linux/socom2` | | VM |
| Bisect gates spent | | |

---

## Task 8 — The Linux ring  **[Judgment]**

- [ ] **Step 1: CI.** The push after Task 2 already runs `test_knobs_registry` on ubuntu-24.04; after Task 7's push check the run is green (the `Knobs`, `Launcher` and `Diagnostics` suites run there; `posix_glue.cpp` compiles there and nowhere on the host).
- [ ] **Step 2: The VM.** `scripts/vm_sync.sh tree && scripts/vm_sync.sh ssh 'cd ~/socom_pc && bash scripts/build_linux.sh runtime && bash scripts/build_linux.sh test'`. Then `scripts/vm_sync.sh ssh 'cd ~/socom_pc && python3 -m unittest tools_py.tests.test_knobs_line tools_py.tests.test_runner_exit_codes -v'` — the four knob-line cases on `dist-linux/socom2`, including the POSIX-only empty-value case in the `Knobs` suite. Batch H costs the VM a full generated rebuild too (8 cores: budget an hour; run it when nothing else needs the VM).
- [ ] **Step 3: One driven title stage in the VM** (`python3 -m tools_py.parity.gate --stamp s9_g3_vm_title --stages title`, as Sprint 8 Task 10 ran it) **only if** Step 2 is green and the VM is otherwise idle: its purpose is the one Linux-only path, `drive.py:96` + `dev_env` + `PS2X_SOCOM2_INPUT_FILE`. The stage is marginal at llvmpipe's 1.6 fps (R107, R148); what is read is the log — `[knobs] dev=1` with `PS2X_SOCOM2_INPUT_FILE` under `set:` and the `[input]` trace showing presses arriving — not the score. R167.

---

## Task 9 — Close-out  **[Judgment]**

**Files:** `README.md`, `docs/HANDOFF.md`, `docs/KNOWN.md`, `docs/STATUS.md`, `docs/CURRENT_SPRINT.md`, this plan.

- [ ] **Step 1: `README.md`.** Replace the paragraph that starts `Knobs (the behaviour-changing ones documented in full below; this is not the complete list` and everything up to the end of that knob prose with: *"Knobs: `docs/KNOBS.md` is the complete, generated list. The 17 **Shipping** names are `config.json` settings the launcher sends. Everything else is a **Dev** knob and is ignored unless the run is in developer mode — `--dev` on `socom2`'s command line or `PS2X_DEV=1`; `run.sh`, the gate and every script under `scripts/parity/` are developer-mode launches already. The game's first log lines include `[knobs] dev=… set: … | ignored without --dev: …`. To add a knob: a row in `ps2xShared/include/ps2x/knobs.h`, read it with `ps2x::knob` / `ps2x::knobOn`, `python -m tools_py.knobs write`."* Keep the keyboard map and the `vu1_replay` recipe that paragraph carries, as their own sentences.
- [ ] **Step 2: `docs/HANDOFF.md`.** One paragraph at the top of its diagnostics section: every recipe below that sets a `PS2X_*` probe works through `./run.sh` unchanged (it is a developer-mode launch) and needs `--dev` or `PS2X_DEV=1` when the runner is started any other way; the five deleted names, so a reader who finds them in `docs/STATUS.md`'s history knows they are gone.
- [ ] **Step 3: `docs/KNOWN.md` (controller only).** Proven, each with its artefact: a stranger's environment cannot switch a probe on (`Knobs` suite, `test_knobs_line`, `s9_g3_poisoned_env`); the launcher does not hand inherited `PS2X_*` to the game (`Launcher` suite); the registry and the source agree in both directions and `docs/KNOBS.md` is generated (`test_knobs_registry`, in CI); the gate's complete knob list, by stage (the `[knobs]` lines of `s9_g3_gating_gate`). Believed, not proven: whatever of Task 7 Step 10 and Task 8 Step 3 did not run. Retract: any row that still tells a reader to set one of the five deleted names.
- [ ] **Step 4: `docs/STATUS.md` and `docs/CURRENT_SPRINT.md`.** A dated entry: 134 names counted (not 190), 17/112/5, the mechanism in two sentences, the four launches and their stamps, R152-R168 by one-line title; Goal 3 marked DONE with `next ruling: R169`; **the spec's bar recorded as restated by R163**, with the sentence that replaces it, so the owner sees the change where they read the sprint.
- [ ] **Step 5: Tick this plan's boxes; leave a reason on every one that stays open. Commit.**

```bash
git commit -m "docs: Sprint 9 Goal 3 closed -- 134 knobs classified (17 shipping, 112 developer, 5 deleted), one accessor, docs/KNOBS.md generated and held to the source by a test, a stranger's environment proven inert; the spec's empty-environment bar restated (R163); R152-R168

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  README.md docs/HANDOFF.md docs/KNOWN.md docs/STATUS.md docs/CURRENT_SPRINT.md \
  docs/superpowers/plans/2026-09-20-sprint-9-goal-3-knob-retirement.md
git push
```

---

## Execution ledger (Sprint 10 Q2, the Opus agent on `agent/knobs`, worktree `C:\projects\wt-knobs`, started 2026-09-21)

The plan's Handoff note 1 said the ledger lives at `.superpowers/sdd/...`; nothing there is tracked (HANDOFF trap 11),
so the ledger is this section. Tasks 1, 2, 3, 4 (A1-H) and 6 are the agent's; Tasks 5, 7, 8, 9 are the controller's
and are not started here. The controller merges `agent/knobs` into `sprint-10` in the main tree; nothing was pushed.

### The inventory, reconciled to the tree (Task 2 Step 3)

The plan was written against `8e5d778`; the branch point of this work is `a3aa99a` (sprint-10). `grep -rhoaE
'"PS2X_[A-Z0-9_]+' ps2xRuntime/{src,include} ps2xIOP ps2xShared ps2xLauncher` finds **145** names read by the shipped
executables, the plan's 134 plus eleven, none removed:

| New name | Read at | Verdict / Kind / Default | Where it came from |
|---|---|---|---|
| `PS2X_AUDIO_INSTRUMENT` | `ps2_audio.cpp:492S` `snd989_mixer.cpp:2003S` | DEV, Presence | research/36 item 9 (music round four) |
| `PS2X_CD_STREAM_TRACE` | `CD.cpp:51S` `MPEG.cpp:3188S` `MPEG.cpp:3204S` | DEV, Presence | the movie feeder / MPEG gate work |
| `PS2X_INPUT_MAPPING` | `socom2_host_input.cpp:232C` (`resolveMapping`, once) | **SHIPPING**, Spec | Sprint 10 Goal 8 (R174): `environmentFor` sends it when the profile's mapping is not the default. **The Shipping class is 18, not 17**; the "Shipping class is exactly what the launcher can send" case sets a custom mapping so the name is emitted, and asserts 18. |
| `PS2X_LAUNCHER_API_BASE` | `bug_report.h:32` (the literal), read at `ps2xLauncher/src/main.cpp:275` as `std::getenv(br::kApiBaseEnv)` | DEV, Text, `https://s2u.scotho.com` | Sprint 9 Goal 8, exactly as Handoff note 2 foresaw. Batch F migrates the read; `tools_py/tests/test_launcher_bug_report.py` gets `PS2X_DEV=1` in the launcher's environment in the same commit, because a test seam is a Dev knob and the launcher process reads `PS2X_DEV` (R156) -- harmless before the flip, required after it. |
| `PS2X_SCHED_TRACE` | `SchedTrace.cpp:122S` (through its own `envOn`) | DEV, Flag, `0` | `a384dfb`, research/36 item 16 |
| `PS2X_SCHED_TRACE_MAX_LINES_PER_S` | `EeScheduler.cpp:2495S` | DEV, Int, `4000` | same |
| `PS2X_SCHED_TRACE_SAMPLE_MS` | `SchedTrace.cpp:134S` (`envMsToNs`) | DEV, Float, `20` | same |
| `PS2X_SCHED_TRACE_STUBS` | `SchedTrace.cpp:207S` `SchedTrace.cpp:282C` | DEV, Spec | same |
| `PS2X_SCHED_TRACE_STUB_MS` | `SchedTrace.cpp:128S` (`envMsToNs`) | DEV, Float, `1` | same |
| `PS2X_SCHED_TRACE_TOML` | `SchedTrace.cpp:251C` (once, at install) | DEV, Path, `recomp/socom2.toml` | same |
| `PS2X_SOCOM2_MUSIC_TRACE` | `game_overrides_socom2.cpp:1408C` (`installMusicTrace`, once) | DEV, Presence | music round four |

Two more helpers that take the name as a parameter, beyond the plan's seven: `SchedTrace.cpp`'s `envOn(name)` and
`envMsToNs(name, defaultMs)` (batch D, rule 2). `Kernel/SchedTrace.cpp` is a new file with three literal reads and
joins `RAW_GETENV_PENDING` (batch D). The registry after Task 1 therefore holds **154** rows (18 Shipping, 127 Dev,
8 Test, 1 Switch), not the plan's 143; after Task 6, 149.

Not in the tree: `PS2X_SOCOM2_LOGIN_NAME` / `PS2X_SOCOM2_LOGIN_PASS` (the brief said they might exist -- the Goal 9
agent is running beside this one; the only occurrences are a planted control string in `tools_py/release/leakcheck.py:437`
and a scrub test in `diagnostics_tests.cpp:117`, neither a read). `harness_names` finds the leakcheck string and it is
in `NOT_KNOBS` with its reason. The Goal 9 merge will add real names; the registry test will fail the day it does, which
is the test doing its job (the same shape as Handoff note 2).

Per-file raw-`getenv` line counts moved too (`gs_gl_backend.cpp` 46 lines, `game_overrides_socom2.cpp` 36,
`ps2_vu1_core.cpp` 15, `host_mic.cpp` 4 -- the plan's call counts were per call, not per line, and three files gained or
lost reads since `8e5d778`); the batches are defined by file, so nothing in the batch table changes except the additions
named above.

**The gate's env pin (Q1b, after the plan was written).** `pins.env_pin` hashes `gate.launch_env(...)`: `os.environ`
plus the gate's own three knobs (`PS2X_HOST_GAMEPAD`, `PS2X_PC_SAMPLER`, `PS2X_PEEK`). Task 3 puts `PS2X_DEV` where
the plan says -- `run.sh`, `drive.py`'s launch (`hostplatform.dev_env`), `scale_shot.child_env`, `env.sh` -- all of
which sit *below* the pin, beside `PS2X_SOCOM2_PAD=1` and `PS2X_HOST_SCREENSHOT_LATEST`, which the pin does not see
either. So the pin's three lines are byte-identical after Task 3 and a gate started from a clean shell is not refused;
`PS2X_DEV=1` appears on the game's own `[knobs]` line (Task 5 Step 4 expects it). Proposed ruling R200 below says so.

### Baselines and counts

| | Python (`Ran N tests`) | C++ (`Total Tests:`) |
|---|---|---|
| `P` / `B` before Task 1, in the worktree (the suite at `a3aa99a` with this branch's 15 new Python cases subtracted; the main tree's last count was 1624/722) | 1622 | 722 |
| Tasks 1-3 (`d76ec8d`, `1f94bae`, `0b20c21`) | 1637 OK | 732/732 (the Knobs suite alone 10/10) |
| R204 (`d8a80e6`) | 1637 OK | 733/733 |
| A1 `58d7979`, A2 `b8d90e5`, B `096686f`, C `f6e5f15`, D `a9bd6f7`, E `785ac50`, F `9cf25cc` | 1637 OK each | 733/733 each |
| H, first try (the plan's placement in `ps2_runtime.cpp`) | 1637 OK | **red**: `vu1_replay` failed to link (`ps2_stubs::socom2HostInputShutdown`, `ps2HostProfStart`, `g_ps2RecompiledFunctionTable`...): the inline `ps2_fpu_trap_enabled()` is reached from the VU code, so its callee's object is pulled into every executable that links `ps2_runtime`, and `ps2_runtime.cpp.obj` drags the whole `PS2Runtime` behind it |
| H, second try (`4b0d6f2`: the definition in its own unit `src/lib/ps2_fpu_trap.cpp`) | 1637 OK | 733/733 |
| Task 6 (`a6fdca4`) | 1637 OK | 733/733 |

Every suite above is `./build.sh test --no-runner` (the Python suite, `ps2x_tests`, the nine `vu1_replay` verify runs), run
under the machine-wide lock by one chain script (`logs/knobs_chain.sh`, `knobs_chain2.sh`, git-ignored) that applied
each state, ran the suite, and committed only a green state with its explicit pathspec; thirteen suite runs in all,
one red. The RED of Task 1 was watched by the same chain (the header moved aside: `fatal error: 'ps2x/knobs.h' file
not found` from `knobs_tests.cpp`, `ps2xTest/src/main.cpp` and `knobs.cpp`), the RED of Task 6 by
`test_knobs_registry` (five `... has no row in knobs.h` and `docs/KNOBS.md is stale`, `logs/task6_red.txt`). Rule 7's
`grep -c "Unity/unity_"` is vacuous in the `--no-runner` tree, which has no generated unit at all; the controller's
full build is where batch H's cost is paid (R165).

Registry counts: 154 rows after Task 1 (18 Shipping, 127 Dev, 8 Test, 1 Switch); **149 after Task 6 (18 Shipping,
122 Dev, 8 Test, 1 Switch)**. `RAW_GETENV_PENDING` is the empty set; `raw_getenv_sites`, `helper_getenv_sites` and
`early_reads` all return `[]`; the only `getenv` calls left in the shipped trees are `knobs.cpp` (the accessor and
`PS2X_DEV`), `bare_run.cpp` (`config.json`'s keys), `USERPROFILE`/`HOME` in the launcher and `PATH` in `posix_glue.cpp`.

**What the controller inherits (Tasks 5, 7, 8, 9 untouched):**
- `4b0d6f2` changed `ps2_runtime_macros.h`: the next `./build.sh runtime` with generated code recompiles every unity
  unit (R165). Nothing else in these thirteen commits touches a generated unit's inputs.
- The gate's env pin needs no `--accept-pins` for these commits (R200): the pinned lines are unchanged; `PS2X_DEV=1`
  appears on the game's `[knobs]` line, where Task 5 Step 4 expects it.
- Task 7's poisoned launch script sets `PS2X_MC_DIR` to a folder under the repository root and starts the runner
  from there, so R204 honours it; a card folder outside the game folder would now read as
  `| refused, outside the game folder: PS2X_MC_DIR`.
- `tools_py/tests/test_launcher_bug_report.py` already runs the launcher with `PS2X_DEV=1` (R202), so it stays green
  after the flip.
- Batch E made `ps2_iop` link `ps2x_shared`; the Linux build (CI, the VM) has not been run on this branch -- Task 8.
- Every commit carries the trailer this session was given (`Claude Opus 5 (1M context)`, HANDOFF �5 rule 3), not the
  `Fable 5.1` one the Global Constraints name; the branch was not pushed (the push rule R157 is the controller's).

---

## Rulings made on the owner's behalf

R152 onward (Goal 2 used R140-R151). Each is a decision this plan made where the spec was silent or the tree disagreed with it; each is the controller's to overturn before the task that carries it starts.

- **R152** (the inventory): **the number is 134, and the scope is what a shipped executable reads.** The spec's 190 was an estimate. 8 test-only names are registered as class `Test` so the scan covers `ps2x_tests`; 3 harness-only names live in `tools_py/knobs.py` `HARNESS_ONLY`; `SOCOM_*` (`SOCOM_ISO`, `SOCOM_EXE`, `SOCOM_SERVER_IP`) are the harness's and no C++ reads one. *Cost if wrong:* none — the test scans, it does not trust this count.

- **R153** (Tasks 1, 2): **the registry is the accessor's table — one X-macro header in `ps2x_shared`, read by Python with a regex, exactly as `exit_codes.h` is.** No JSON, no generated C++, no second list: a generated header would put a Python step in front of every C++ build, and a JSON file would need a loader in a library that has none. *Cost if wrong:* a row the regex cannot parse silently leaves `docs/KNOBS.md` — which is why `test_the_parser_counts_every_row_the_macro_holds` compares the regex's count with a plain substring count.

- **R154** (Task 1): **`ps2x::knob` never snapshots the environment, and its unset path is one `getenv` with no table search; the ten hot sites cache at the site.** Tests, `vu1_replay` and `BareRun::applyEnvironment` all change variables while the process runs, so a snapshot taken at first use would be wrong in all three. With the search behind the "is it set" test, the common case costs what it costs today, and the sites that ran a `getenv` thousands of times a second (Handoff note 6) get cheaper than today. *Cost if wrong:* a future hot per-call read is as slow as the ones this goal found — visible in a host profile, as these were not.

- **R155** (Task 3): **developer mode is `--dev` or `PS2X_DEV=1`; the harness gets it from `run.sh`, `env.sh` and `hostplatform.dev_env`, by default-if-unset, so `PS2X_DEV=0 ./run.sh` is still a stranger's run; `ps2x_tests` and `vu1_replay` are always developer processes.** The variable rather than the flag for the harness, because `drive.py` and `online_login_ours.py` build an environment and reach the runner through `run.sh`; a flag would have to be threaded through both. *Cost if wrong:* a developer who starts `dist/socom2.exe` by hand with a probe set and no `--dev` gets no probe — and a log line naming the probe as ignored, which is the design.

- **R156** (Task 7): **the launcher never sets developer mode and gets no hidden option; it drops inherited `PS2X_*` variables from the game's environment unless it was itself started with `PS2X_DEV=1`.** A hidden checkbox is one more thing a stranger can find and a tester can leave on; a developer who wants probes under the launcher starts the launcher from a shell with `PS2X_DEV=1`, and everything — the probes and the switch — is inherited as it is today. The filter is what closes Handoff note 7: DEV gating alone would not stop a stale `PS2X_SOCOM2_UDP_SHIFT` or `PS2X_MIC_DEVICE`, because those are Shipping. *Cost if wrong:* the owner wanted the hidden option — it is a `Config` bool and one line in `environmentFor`, a small follow-up; and a tester who relied on setting a Shipping variable in a shell before starting the launcher finds `config.json` is now the only way, which is what the UI says anyway.

- **R157** (Tasks 4, 5): **one gate for all eight no-behaviour-change batches, not one per runtime commit; the batch commits stay local until it passes.** Spec §4 budgets a gate per runtime commit; eight gates for a change whose every line is `getenv` -> `knob` with enforcement off would be two hours of launches proving the same thing eight times, on a host whose owner feels each one. The bisect (Task 5 Step 5) is bounded at four gates and is only paid on a failure. *Cost if wrong:* a failure costs up to five launches instead of one, and unpushed commits sit on one machine for a session — the ledger lists their hashes.

- **R158** (Task 6): **the five deletions ride on Task 7's gate rather than their own.** Each deleted block is behind a knob; Task 5 Step 4 records, from the game's own `[knobs]` lines, that the gate sets none of the five. A gate cannot tell a run with the block from a run without it. *Cost if wrong:* a deletion that broke compilation or an adjacent line — caught by `./build.sh test` and by Task 7's gate, one task later than it might have been.

- **R159** (Task 6): **five names are DEAD** on the evidence in the inventory section; two more were never knobs. The bar used: the project's own record retires it (`GS_TEX_FROM_CPU`), or it is a one-investigation probe with that investigation's constants compiled in and a general tool beside it (`GS_PROBE`), or no document, script, tool or test has ever named it and its bug is closed (`GS_GL_DEBUG_NODEPTH`, `MPEG_PIC_TRACE`, `TIMER_TRACE`). **What was not deleted on the same evidence, and why:** `PS2X_PACK_TRACE` is also named nowhere, but belongs to the terrain-holes work the owner has open. *Cost if wrong:* someone wants one back — `git revert` of one commit, or `git show` of a twenty-line block.

- **R160** (Task 7): **`PS2X_SOCOM2_PAD` flips from opt-in-by-presence to on-by-default; it stays Shipping and the launcher keeps sending `1`.** Every launch path already sets it; the only run that does not is a by-hand `socom2 game.elf`, which today boots a game that cannot be played. *Cost if wrong:* a by-hand boot that used to sit in the shell loop now sees a pad; `PS2X_SOCOM2_PAD=0` restores it.

- **R161** (Task 7): **seven presence-tested A/B switches (and the pad) move to the flag rule; presence-tested traces do not.** `PS2X_GS_NO_ZTEST=0` disabling the depth test is a trap even for developers (the test binary's own `main` documents falling into it). Traces are left alone because `PS2X_TRACE_VU=0` and `PS2X_GS_TRACE_PRESENT=0` are *values* ("skip none"), and moving forty trace reads to a rule that would break those buys nothing a stranger can feel. `docs/KNOBS.md` says `Presence` where it is presence. *Cost if wrong:* a muscle-memory `PS2X_GS_NO_ZTEST=` with an empty value, which already did nothing on Windows.

- **R162** (Task 7): **under enforcement an empty value is unset, for every knob.** `socom2_libnetb.cpp` already states that rule for its own flags after a review found them disagreeing; `PS2X_SOCOM2_MOUSE=""` currently switches mouse look **on** (`mouse[0] != '0'`). Windows cannot hold an empty variable at all, so this only changes POSIX and Git Bash's `export X=`. The one deliberate empty value in the harness (`PS2X_SOCOM2_RSA_KEY=""` for "key A") means the same either way. *Cost if wrong:* a knob for which empty was meaningful — none was found in 213 read sites.

- **R163** (the bar): **"the gate 3/3 with an empty environment" is restated** as: *(a) with no developer mode, a launch whose environment holds six behaviour-changing Dev knobs runs as if they were not there and names them as ignored (`s9_g3_poisoned_env`, five checks); (b) the gate passes 3/3 started from a shell with no `PS2X_*` variable set, setting its own instruments and its own developer mode (`s9_g3_gating_gate`, whose job script unsets every `PS2X_*` first).* As written the bar asks an instrument to work with its instruments switched off (Handoff note 3). The alternative — classing the gate's four probes as Shipping so the gate needs no developer mode — would leave `PS2X_PEEK`, the sampler, the frame export and the gamepad switch open to every stranger, which is the opposite of the goal. *Cost if wrong:* the owner meant something narrower — for instance "the gate passes without `env.sh`", which has been true since `gate.py` began setting its own defaults and is what (b) proves.

- **R164** (Handoff note 8): **precedence stays asymmetric: `config.json` beats an inherited variable under the launcher; the variable beats `config.json` in a bare run.** Both are existing, tested behaviour (the latter is Goal 1's, commented as this goal's rule). The spec's "env var kept as an override" is honoured where a developer is. After R156 the launcher side is moot for strangers anyway: inherited `PS2X_*` no longer reaches the game. *Cost if wrong:* a bare-run stranger with a stale Shipping variable gets the variable, not their `config.json` — and a `[knobs]` line that says so.

- **R165** (Task 4 H): **`PS2X_FPU_TRAP` is migrated too, at the price of one full generated rebuild (twice: the host and the VM; and the release tree the next time `build.sh release` runs), scheduled, last.** The alternative is a permanent exemption for `ps2_runtime_macros.h` in the raw-`getenv` check, which would leave one Dev knob — one that prints guest pcs to a stranger's log — outside the gate for ever, and an "except this file" in a rule whose value is having no exceptions. *Cost if wrong:* 10-15 minutes of all cores on a load-sensitive host, once; if the owner's window never comes, H is the one batch that can be deferred past Task 7 with the file left on `RAW_GETENV_PENDING` and the consequence written into `docs/KNOWN.md`.

- **R166** (Task 7): **one online control round after the flip, although no online knob's meaning changes.** The brief's test is "only if an online knob is touched"; what is touched is whether the two-instance harness's instruments (`PS2X_SOCOM2_INPUT_FILE`, `PS2X_WINDOW_TITLE`, per-instance `PS2X_PEEK`/`PS2X_CALL_TRACE`) are honoured, and the gate exercises none of them on Windows. Against our own server, in an away window. *Cost if wrong:* one round spent proving what `run.sh`'s one line already implies.

- **R167** (Task 8): **Linux is proven by CI, the VM's C++ and Python suites and `test_knobs_line` on the Linux runner; the VM's title stage is read for its log, not its score.** R107 and R148 already record that the VM's gate cannot discriminate at 1.6 fps. *Cost if wrong:* a Linux-only break in `drive.py`'s direct launch — which Step 3 exists to catch when the VM is free.

- **R168** (Task 2): **the namespace-scope-read check is a heuristic on this tree's naming (`g_` globals, column-0 `static`), not a parser.** It catches all four reads that exist today and the shapes a fifth would most likely take. *Cost if wrong:* an early read written some other way is honoured under `PS2X_DEV=1` and ignored under `--dev` — a confusing afternoon for a developer, never a stranger's problem.

### Proposed rulings from the Q2 agent (2026-09-21; the controller numbers them -- next free is R200)

- **Proposed R200 (Task 3, the env pin).** **`PS2X_DEV` enters the harness below the gate's env pin, and the pin is
  not widened for it.** Q1b's `pins.env_pin` hashes `gate.launch_env` -- the operator's environment plus the gate's
  own three knobs -- and never saw `drive.py`'s `PS2X_SOCOM2_PAD=1` or `PS2X_HOST_SCREENSHOT_LATEST` either. Task 3
  puts `PS2X_DEV=1` beside those (in `run.sh`, `hostplatform.dev_env` in `drive.py`, `scale_shot.child_env`,
  `env.sh`), so the pinned lines are byte-identical and the controller's Task 5 gate is accepted without
  `--accept-pins`; the game's `[knobs]` line is where `PS2X_DEV` is read back (Task 5 Step 4). *Why not widen the
  pin to the launched environment:* the pin's job is to refuse an operator's stray variable, and `drive.py`'s
  additions are code, not environment -- a change there is a commit the harness pin records. *Cost if wrong:* the
  pin does not prove the harness's own additions; a later Q1 pass can hash `drive.launch`'s environment instead.

- **Proposed R201 (Task 1, the inventory).** **`PS2X_INPUT_MAPPING` is the eighteenth Shipping name.** It is sent by
  `environmentFor` when the profile's mapping is not the default (R174), so the "Shipping class is exactly what the
  launcher can send" case sets a custom mapping before comparing. *Cost if wrong:* none -- the test scans, and 18
  is what the launcher emits.

- **Proposed R202 (batch F).** **`PS2X_LAUNCHER_API_BASE` is a Dev knob read through `ps2x::knob` in the launcher,
  and the launcher's Python test sets `PS2X_DEV=1` on the launcher it starts.** A test seam is a probe: after the
  flip a stranger's `PS2X_LAUNCHER_API_BASE` is ignored exactly as a runner probe is. The launcher process reads
  `PS2X_DEV` for R156's filter anyway, so no new switch is added. *Cost if wrong:* a developer running the launcher
  by hand against a loopback service needs `PS2X_DEV=1` too -- one variable, and the header's comment says so.

- **Proposed R203 (Task 4 D).** **The two helpers `SchedTrace.cpp` grew after the plan (`envOn`, `envMsToNs`) are
  migrated under rule 2 like the plan's seven, and a check that no non-literal `getenv` remains in the shipped trees
  outside `knobs.cpp` and `bare_run.cpp` joins `test_knobs_registry` when the last helper migrates (batch F).**
  Without it the pending-list check proves only the literal reads; a helper that took the name as a parameter
  could keep a raw `getenv` for ever. *Cost if wrong:* a future helper needs an exemption in `tools_py/knobs.py`
  with its reason, as `bare_run.cpp`'s `applyEnvironment` (which applies `config.json`'s keys, not knobs) has.

- **Proposed R204 (path knobs; the sprint file's addition).** **Every Path-kind knob is constrained to the portable
  folder, or refused -- but not in this pass.** The registry now says which names are paths (Kind `Path`: 24 rows
  after Task 6, `PS2X_MC_DIR` and `PS2X_MC_DIR_SLOT1` among them) and after the flip every Dev one of them is
  ignored for a stranger; the two that a stranger can still reach are `PS2X_MC_DIR` (Shipping, already a name not a
  path through `normalizeProfile`) and, through `config.json`, nothing else. The `remove_all` on the card root
  (`KNOWN.md` row 110(c)) is a MemoryCard defect and is not made worse or better here. The constraint itself
  (resolve under the home, refuse outside it) is one function at the accessor's edge and a test per Path row; it is
  queued as the first item after the flip, because doing it before the flip changes what a launch with today's
  environment does (a dump path outside the folder that works today would be refused), which Trap 1 forbids.
  *Cost if wrong:* a stranger with a Dev path knob set gets nothing (the flip); a developer keeps today's behaviour.

## Self-review

- **Goal coverage, against the spec's bullet and its bar.** *Classify every one* -> the inventory table (134 rows, with site, read mode, default, setter) and the registry rows (the meaning), cross-checked by machine while this plan was written: every name the scan finds has a row and every row has a site. *Delete the dead* -> Task 6, five names with evidence, two ghosts. *Move the shipping ones into `config.json` with the env var kept as an override* -> already true for all 17 (Handoff note 9), now locked by the "Shipping class is exactly what the launcher can send" case; the override's two precedences are R164. *Put the probes behind one `--dev` switch* -> Tasks 1, 3, 7. *So a stranger's environment cannot change behaviour by accident* -> enforcement (Task 7 Step 3), the launcher's filter (Step 5, which closes the hole DEV gating cannot), the flag rule (Step 4), R162. *Bar: a generated table checked by a test against the source* -> Task 2, in both directions, in CI. *The gate 3/3 with an empty environment* -> not reachable as written; R163 restates it and Task 7 Steps 8-9 prove both halves.
- **The brief's six investigations.** (1) the inventory with helpers and indirect names — the section above; (2) who sets each — the "Set by" column, from `environmentFor`, `BareRun`, `env.sh`, `gate.py`, `drive.py`, the online scripts, `build.sh`, `vu1_replay` and the C++ tests; CI sets none; (3) the classes with evidence for every DEAD verdict; (4) the accessor: unset for Dev outside developer mode, one start-up line tied into `versions.txt`, cheap on the per-call reads that were found (R154), every launcher of the runner listed and wired (Task 3's table), the launcher's hidden option decided against (R156); (5) the registry is the accessor's table (R153), `docs/KNOBS.md` generated, the test fails on a literal without a row and a row without a read; (6) the order — registry and test with nothing changed, the wiring with nothing changed, eight batches with nothing changed, one gate, deletions, the flip with its own gate, docs — and the honest answer on the bar.
- **What the tree contradicted** — fifteen Handoff notes. The ones that change the work: 134 not 190; the gate's instruments are themselves knobs, so the bar had to be restated; four reads run before `main`; one read is in the header all generated code includes; ten reads were unmemoised on hot paths; the launcher passes the whole inherited environment, including six Shipping names DEV gating would not stop; the pad is off by default for a by-hand run; `=0` switches presence knobs on; the test binary and `vu1_replay` steer themselves with Dev knobs and tests change variables mid-process, which rules out a snapshotting accessor; `ps2_iop` does not link the shared library; Goal 8 is adding a 135th name in files Task 1 touches.
- **Launch budget.** Four: two gates, one 90-second poisoned launch, one control round. Up to four bisect gates on a failure. The VM's title stage is optional and is not a host launch.
- **Placeholder scan.** No `TBD`. The angle-bracket pathspecs in Task 4's step list are the files of that batch's table row and the text says to write them out. What is left to the executor is measurement (`P`, `B`, the Results table, the `[knobs]` lines) and two judgments with stated rules (when to schedule batch H; whether the control round's window comes).
- **Type consistency.** `ps2x::knob(const char*) -> const char*`; `ps2x::knobOn(const char*, bool=false) -> bool`; `ps2x::knobs::{Class, Kind, Entry, kTable, kTableSize (size_t), find, className, kindName, flagValue, devMode, setDevMode, resetDevModeForTests, enforcement, setEnforcement, consumeDevFlag(int&, char**), Pairs, describe(const Pairs&, bool), startupLine}`; `launcher::{isKnobKey(const std::string&), mergeEnvironment(base, ours, bool)}` with the two-argument overload kept; `diagnostics::knobsLine(const std::string&)`; `hostGamepadIndexKnob()`; `ps2_fpu_trap_after_seconds()`; Python `knobs.{HEADER, DOC, RAW_GETENV_PENDING, HARNESS_ONLY, NOT_KNOBS, table, literals, raw_getenv_sites, test_reads, harness_names, early_reads, accessor_mismatches, problems, render, main}`; `hostplatform.{DEV_ENV, dev_env(env)}`. One new environment name: `PS2X_DEV`.
- **Platform halves.** Every C++ test that sets a variable has its `_putenv_s`/`setenv` pair; the empty-value case is POSIX-only and says why; `win32_glue.cpp` and `posix_glue.cpp` get the filter in the same commit; `run.sh` (Windows) and `drive.py:96` (Linux) get developer mode in the same commit; `test_knobs_registry` needs no build and runs in CI; `test_knobs_line` runs on both runners.
- **Owner gate.** Autonomous end to end. For the owner's eye at close-out: R163 (the bar, restated), R156 (no hidden developer option in the launcher; inherited `PS2X_*` no longer reaches the game), R160 (the pad on by default), R159 (the five deletions), and the window for batch H's full rebuild (R165).
