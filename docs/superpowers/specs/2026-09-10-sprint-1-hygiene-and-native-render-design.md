# Sprint 1 — hygiene, freeze, and the first native render replacement: design

Status: direction approved by the user on 2026-09-10 after an external audit of the project
(the audit is summarised in §1). Project name from this date: **SOCOM Unzipped**, repository
`github.com/Scotho/socom-unzipped`.

## 1. Why this sprint (audit summary)

What exists is a working proof of concept: the recompiled game boots, menus run at 59 fps,
Albania 5-1 plays at 36-42 fps, and two instances complete the online lobby flow into gameplay
on a local Horizon server. By origin the code is:

| Component | Size | Nature |
|---|---|---|
| Generated game code (`recomp/output`) | 12.6 M lines, 14,882 files | literal per-instruction MIPS to C++ |
| Vendored PS2Recomp runtime (upstream) | ~45 k lines | EE kernel, DMAC/VIF/GIF, software GS, VU1 interpreter, IPU, IOP HLE |
| Fork additions since 2026-09-04 | 30 k lines, 68 files | generated VU1 code, GL backend, 989snd, VU1 recompiler, libnetb, hooks |
| Game functions replaced natively | 2 | RSA keygen, one pixel read |

Conclusions the sprint rests on:
- The runtime is the GS/VU/VIF/GIF/DMAC/IPU half of a PS2 emulator with the EE core
  precompiled in. Further emulator speed work (VU1 register allocation, scheduler batching, GS
  dirty rectangles) has PCSX2 parity as its ceiling and is gated only by eyeballed screenshots.
- A from-scratch rebuild is rejected: nothing would run until everything runs (reCOM is the
  cautionary tale). The N64-recomp model is the target instead: game logic stays recompiled,
  the renderer/audio/input/network are replaced natively at the hardware boundary. Audio and
  network are already there; the renderer is not, and it is where the frame time goes.
- Maintainability gaps: no repo of its own (fixed 2026-09-10), zero automated tests for the
  30 k fork lines (the upstream `ps2xTest` suite is not even built), three screenshot gates with
  no single command and no pass/fail, 79 `PS2X_*` env knobs and revert layers that never retire.

## 2. Sprint goals (the four points, in order)

1. **Hygiene.** Own repo with a remote (done). Build and run the upstream unit tests under our
   clang toolchain. One command that runs the three screenshot gates and exits non-zero on
   failure. Loop rules updated so a gate failure blocks a commit.
2. **Freeze emulator speed work.** Single-instance mission frame rate stays at the current
   36-42 fps; no further VU1/scheduler/GS optimisation commits this sprint. The two-instance
   19 fps is a test-rig concern: the second client of the acceptance test runs in PCSX2.
3. **First native render replacement.** Replace the VU1 microprogram that draws the 2D UI
   with hand-written host C++ behind a program registry, verified GIF-word-for-GIF-word against
   the interpreter on dumped runs, then gated by the title screen. This is the pattern every
   later program follows.
4. **Acceptance test untouched.** The first-kill two-instance online test continues as-is; it
   proves the online path and does not depend on 1-3.

## 3. Non-goals

- No decompilation of game logic. No new HLE of EE game functions beyond the render path.
- No GPU-side "host-resolution" drawing yet. Sprint 1's native program emits the same GIF
  packets the microprogram does; drawing meshes directly at host resolution is Sprint 2, on
  top of the registry and the golden harness this sprint builds.
- No retirement of `PS2X_*` knobs yet, except the ones a task explicitly names.

## 4. Definition of done

- `./build.sh test` builds the test executable and runs it; exit code 0.
- `python -m tools_py.parity.gate` runs title, transition and mission gates and prints one
  `PASS`/`FAIL` line per gate plus a summary; exit code is non-zero on any `FAIL`.
- `docs/LOOP_PROMPT.md` requires a green `gate` before any commit that touches
  `third_party/ps2recomp` or `recomp/`, and forbids emulator speed work this sprint.
- The UI VU1 program runs natively when `PS2X_VU1_NATIVE=1` (default on after the gates pass),
  `vu1_replay` reports zero GIF mismatches against the interpreter for every dumped run of that
  program, and the title gate is green with it on.
- STATUS.md has a short "Current state" section at the top that says the above in five lines.
