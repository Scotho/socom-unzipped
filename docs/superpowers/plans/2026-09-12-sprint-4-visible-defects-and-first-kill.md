# Sprint 4 — Visible Defects, Gate Trust, and the First-Kill Online Test: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the last defects you can see on screen (intro-movie macroblocks, ground height), make the parity gate incapable of hiding a red run, close the `--vram-diff` calibration, and then drive a two-instance online match to a first kill — the user's standing definition of "playable".

**Architecture:** Wave 1 is four independent bounded fixes, each with its own check, because the parity gate cannot see two of them. Wave 2 is strictly sequential and opens with a decisive experiment (S0) that decides whether the round-start freeze lives in our runtime or in the local Horizon server, so the expensive stages read the right body of code; S1 unblocks the round, S2 calibrates movement and aim, S3 reads the kill state and wires the acceptance test.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh`), CMake/Ninja, OpenGL through raylib/rlgl, MiniTest, Python 3 (numpy, Pillow), PCSX2 as the console reference, a local Horizon server (Medius/DME, C# sources under `server/`), Git Bash + PowerShell for detached runs.

**Spec:** `docs/superpowers/specs/2026-09-12-sprint-4-visible-defects-and-first-kill-design.md`

## Handoff notes for the executing model (read once)

- **Process.** Run with superpowers:subagent-driven-development: a fresh implementer per task (Opus for C++, guest-code tracing and server work; Sonnet for Python/docs; Haiku for trivial re-reviews), a task review after each, a whole-branch review at the end, one fix wave, then a fast-forward merge of `sprint-4` into `develop` and `main`. Ledger under `.superpowers/sdd/<plan-basename>/progress.md`. Record every decision taken on the user's behalf as `Ruling: … — why — cost if wrong` and list them all in the final message.
- **Standing rulings from Sprints 1-3 (reuse them).** Work on a branch in the main checkout, never a git worktree (the ignored `game/`, `tools/`, `recomp/output`, `build-clang` are multi-GB). File-disjoint tasks may run in parallel; tell each implementer "if `git commit` fails with index.lock, wait 10 s and retry". Research tasks do not commit; the controller commits the note. A review finding the plan text contradicts is ruled on, not dismissed. **Take the loop lock around every build, including `cmake --build … --target vu1_replay`** — concurrent ninja in one `build-clang` tree is unsafe.
- **The `>= 99` bar is a run-vs-run `compare.score`, never the gate's `summary.txt` numbers** (those score against the gate's internal reference and read much lower by design; this confused a reviewer in Sprint 3). `compare.score` takes **PIL Images, not paths**, and capture files are named `s00_none.png`:

  ```python
  import sys, os, glob
  sys.path.insert(0, '.')
  from PIL import Image
  from tools_py.parity.compare import score
  ref, run = 'logs/parity/gate/<ref>/title', 'logs/parity/gate/<run>/title'
  for a in sorted(glob.glob(ref + '/s*.png')):
      b = os.path.join(run, os.path.basename(a))
      if os.path.exists(b): print(os.path.basename(a), score(Image.open(a), Image.open(b))['score'])
  ```

  s20–s22 are attract-movie frames and score 85–100 between runs of identical binaries; the bar applies to s00–s19.
- **The reference gate stamps at sprint start** are `s3_head_1x` + `s3_head_1x_t2` (1×, on the merge-base binary) and `s3d_2x_host` (2×).
- **Two known transition-gate intermittencies.** (a) The save-dialog probe flake: too few frames *examined* (e.g. "3 … need 5"), peak 0. (b) A one-frame residual strip at rows 396-447, ~1 in 5 runs, reproduced on the pre-scale binary. **Neither is a regression signature.** Re-run the leg (`--only transition --stamp <s>_t2`); escalate to an A/B against the merge base only if the same signature repeats.
- **Verification vocabulary.** `dist/vu1_replay.exe --verify <goldendir>/state.txt [--native|--no-native] [--host-draw] [--regs all] <dumps>` — always point `--verify` at the `state.txt`, never a directory (a directory prints an error and exits 2); never read `$?` through a pipe. Exact goldens: `PS2X_VU1_FAST=0 PS2X_VU1_GEN=0 dist/vu1_replay.exe --batch <dir> --no-native <dumps>` — **`--no-native` is mandatory**, without it the native path is its own oracle; a correct golden prints `native entered=0 ended=0 handbacks=0`. **23 dump basenames collide across `logs/vu1dump2|3|4`** — build goldens per dump set.
- **Commit conventions.** From the repo root with explicit paths (never `git add -A`); `server/config/simulated.db` stays unstaged; `ONBOARDING.md` is untracked and not ours; push after each commit. Trailers: `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` and `Claude-Session: <the executing session's url>`.
- **The freeze.** No commits whose purpose is emulator speed (VU/VU0 interpreter, scheduler batching, GS/GL caching and upload performance). Accuracy fixes the gate or the acceptance test forces are in scope. Specifically: `resolveToMirror` resolving all 1024 rows instead of `usedHeight` is a known optimisation and is **out**.

## Global Constraints

- Branch `sprint-4` off `develop` (= `main` = `0ec0724` at sprint start; the spec commit).
- Defaults do not move: `PS2X_GS_SCALE=1`, `PS2X_GS_SCALE_FILTER=point`, `PS2X_PRESENT_FILTER=linear`, `PS2X_VU1_HOST_DRAW` off, `PS2X_VU1_NATIVE` on.
- `./build.sh test` exit 0 and `python -m tools_py.parity.gate` green at the defaults before any commit that touches `third_party/ps2recomp/` or `recomp/`.
- `./build.sh runtime` MUST precede any gate (`./build.sh test` does not rebuild `dist/socom2.exe`). A header edit costs a ~10-minute rebuild; batch header changes.
- Game runs go DETACHED: a bash script under `logs/` launched with PowerShell `Start-Process -FilePath "C:\Program Files\Git\usr\bin\bash.exe" -ArgumentList "<script>"` (the bare `bash.exe` form fails), or `nohup bash <script> &` from the Bash tool, polled through a `.done` marker. A full gate is ~20 minutes.
- Do not resize the game window during a run.
- Shell and Python files stay LF; C++ edits through the Edit tool or a Python patch script.
- Kill any stray `pcsx2-qt.exe` / `socom2.exe` before a drive run.

---

## File map

| Path | Responsibility |
|---|---|
| `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (`executeTransfer` 1245, `executeUpload` 1268, `refreshRenderTargetsFromShadow` 1320) | Task 1: the dropped 16×16 movie block |
| `tools_py/parity/movie_blocks.py` | (new) Task 1's check: per-picture black-block diff against a reference decode |
| `tools_py/parity/drive.py` (`frame` 65-66, the `untilref`/`ifref` thumbnails 210-251) | Task 2: crop to the non-black rect before the 160×112 resize |
| `tools_py/tests/test_drive_crop.py` | (new) Task 2's unit tests |
| `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` (bucket loop 492-541) | Task 3: widened `rounding`/`edge` buckets |
| `tests/fixtures/vu1/dispatch_0x1b50/` + `build.sh` (run 6) | Task 3: `vu1dump4_prog_182` added back |
| `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` | Tasks 4, 6: tracing knobs (`PS2X_CALL_TRACE(+_DUMP/_EVERY)`, `PS2X_PEEK`, `PS2X_TRIGGER`, `PS2X_RDRAM_DUMP_AT`, `PS2X_SOCOM2_NET_TRACE`, `PS2X_SOCOM2_INPUT_FILE`) |
| `docs/research/17-ground-height.md` | (new) Task 4's note |
| `docs/research/18-online-round-start.md` | (new) Tasks 5-6's note (S0 verdict + S1 localisation) |
| `server/horizon-server`, `server/dme-plugins`, `server/medius-plugins`, `server/logs` | Task 6, if S0 points server-side |
| `tools_py/parity/online_match_ours.py` | Tasks 7-8: movement/aim calibration, kill detection, the acceptance test |
| `docs/STATUS.md`, `README.md`, `docs/LOOP_PROMPT.md`, `docs/HANDOFF.md`, this plan | Task 9: close-out |

---

### Task 1: Intro-movie macroblocks — prove candidate 1, then fix it

**Files:**
- Create: `tools_py/parity/movie_blocks.py`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (`executeTransfer` ~1245-1266, `executeUpload` ~1268-1290)
- Modify: `docs/research/16-intro-movie-macroblocks.md` (record the count and the outcome)

**Interfaces:**
- Consumes: research/16 §7 (the counting step) and §8 (the capture-diff recipe); `PS2X_GS_DUMP_DISPLAY=<dir>:<t0>:<t1>` writing `shadow`/`gpu`/`cpu` PPM triples after `refreshDirtyRows` and before the present blit; `scripts/parity/title_only.txt`.
- Produces: `python -m tools_py.parity.movie_blocks <dumpdir> --ref <reference.mp4|dir>` printing one line per picture and a final `MISSING blocks=<n> pictures=<n>`, exit 1 when any block is missing from the `gpu` layer but present in `shadow`.

- [ ] **Step 1: Write the check first (it must fail on today's binary)**

`movie_blocks.py` reads the `PS2X_GS_DUMP_DISPLAY` triples, and for each picture computes the 16×16 pure-black block mask of the `gpu` layer and of the `shadow` layer, then reports `mask_gpu & ~mask_shadow` — blocks black on the GPU but not black in shadow VRAM. This is strictly stronger than research/16's ffmpeg recipe and needs no reference decode: the shadow layer *is* the reference for the mirror stage, and research/16 already proved the decode clean. Print block coordinates, never an absolute black count (the movie genuinely contains black blocks — this trap cost the Sprint 3 spike a false positive).

- [ ] **Step 2: Capture and confirm the check fails**

Detached `title_only.txt` run with `PS2X_GS_DUMP_DISPLAY=logs/mb_s4:<t0>:<t1>` over the intro seconds. Run the check. Expected: a non-zero `MISSING` count naming blocks at multiples of 16 — the same signature research/16 recorded (pictures 965, 1085, 1447).

- [ ] **Step 3: Do the count that decides candidate 1**

Add a temporary counter (stderr, env-gated, removed before the commit) or use `PS2X_GS_TRACE_PAGES`: per movie frame, count `executeTransfer` calls with `command.trxreg.rrw == 16 && command.trxreg.rrh == 16` against `refreshRenderTargetsFromShadow` calls made from `executeUpload`. Record both numbers in your report.

- [ ] **Step 4: Fix, if the count proves it**

If refreshes are fewer than 16×16 transfers, candidate 1 is proven: `executeUpload` refreshes only when `m_uploadReceivedBytes >= m_uploadExpectedBytes` (line ~1280), and `executeTransfer` resets `m_uploadReceivedBytes = 0` and overwrites `m_currentTransfer` (lines ~1264-1266) — so any rectangle whose bytes did not complete before the next transfer began is written into shadow VRAM and **never mirrored to the GL texture**. Fix: before `executeTransfer` overwrites `m_currentTransfer`, if the previous transfer left `m_uploadExpectedBytes != 0 && m_uploadReceivedBytes != 0` (a partially-delivered rectangle), refresh the render targets for the *previous* rectangle first. Keep the change surgical and comment it with the counted evidence.

If the count *disproves* candidate 1 (refreshes match transfers), **do not guess**: record the numbers in research/16, name the next candidate, and report `DONE_WITH_CONCERNS` with no runtime change.

- [ ] **Step 5: Prove the fix**

`./build.sh runtime`, re-capture, and re-run `movie_blocks.py`: expected `MISSING blocks=0`. Then `./build.sh test` exit 0 and a detached full gate (`--stamp s4_mb`) PASS 3/3 with title s00–s19 ≥ 99 against `logs/parity/gate/s3_head_1x/title`.

- [ ] **Step 6: Commit**

`git add tools_py/parity/movie_blocks.py third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp docs/research/16-intro-movie-macroblocks.md && git commit -m "gs-gl: mirror a movie block whose upload was cut short by the next transfer (the blocks were in shadow VRAM, never on the GPU)" && git push`

---

### Task 2: `drive.py` crops to the non-black rect before scoring

**Files:**
- Modify: `tools_py/parity/drive.py` (`frame()` at 65-66; the `untilref`/`ifref` thumbnail builders at ~223 and ~251)
- Create: `tools_py/tests/test_drive_crop.py`

**Interfaces:**
- Consumes: `winshot.grab(hwnd)` returning a PIL Image of the window client area.
- Produces: `drive.crop_to_content(im, thresh=8)` → PIL Image with uniformly-black border rows/columns removed (returns the input unchanged when nothing is black-bordered, and when the whole frame is black); `frame()` and both reference-thumbnail builders call it before `.resize((160, 112))`.

- [ ] **Step 1: Write the failing tests**

```python
# tools_py/tests/test_drive_crop.py
import numpy as np
from PIL import Image
from tools_py.parity.drive import crop_to_content

def _img(a):
    return Image.fromarray(a.astype(np.uint8))

def test_pillarboxed_frame_crops_to_content():
    a = np.zeros((112, 200, 3)); a[:, 40:160] = 200          # 120-wide content, black bars
    out = np.asarray(crop_to_content(_img(a)))
    assert out.shape[1] == 120 and out.shape[0] == 112

def test_letterboxed_frame_crops_to_content():
    a = np.zeros((200, 160, 3)); a[40:160, :] = 200
    out = np.asarray(crop_to_content(_img(a)))
    assert out.shape[0] == 120

def test_untouched_when_no_border():
    a = np.full((112, 160, 3), 128)
    assert np.asarray(crop_to_content(_img(a))).shape == (112, 160, 3)

def test_all_black_frame_is_returned_unchanged():
    a = np.zeros((112, 160, 3))                               # the transition gate scores these
    assert np.asarray(crop_to_content(_img(a))).shape == (112, 160, 3)

def test_near_black_content_is_not_cropped_away():
    a = np.zeros((112, 160, 3)); a[:, 40:120] = 12            # dim but above threshold
    assert np.asarray(crop_to_content(_img(a))).shape[1] == 80
```

- [ ] **Step 2: Run them and watch them fail**

`python -m unittest tools_py.tests.test_drive_crop -v` → FAIL, `ImportError: cannot import name 'crop_to_content'`.

- [ ] **Step 3: Implement**

`crop_to_content` computes a per-row and per-column max over the greyscale frame, finds the first and last index above `thresh`, and crops to that box; if no index is above the threshold (an all-black frame) it returns the image unchanged — **the transition gate scores black frames on purpose, and cropping them away would break it.**

- [ ] **Step 4: Tests pass, and the gate's own suite still passes**

`python -m unittest tools_py.tests.test_drive_crop -v` → 5 passed. `python -m unittest tools_py.tests.test_gate` → 24 passed.

- [ ] **Step 5: Prove it on a real pillarboxed run**

Use `tools_py/parity/resize_window.py` (committed in Sprint 3 for exactly this) to drive a title run at a stretched window, then score it run-vs-run against `logs/parity/gate/s3_head_1x/title`. Before this task such a run fell to the 16/23 pass floor (Sprint 3 measured 66.4 on one capture); after it, the scores must land in the normal band. Record both numbers.

- [ ] **Step 6: Commit**

`git add tools_py/parity/drive.py tools_py/tests/test_drive_crop.py && git commit -m "parity(drive): score the content rect, not the window -- a resized window degraded the title score smoothly to the pass floor instead of failing" && git push`

---

### Task 3: `--vram-diff` bucket calibration and `vu1dump4_prog_182`

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` (the classification loop at ~492-541)
- Modify: `tests/fixtures/vu1/dispatch_0x1b50/` (add `vu1dump4_prog_182.bin` + its golden line), `build.sh` (run 6 comment)

**Interfaces:**
- Consumes: the existing `boundaryAt(mask, x, y)` helper, the `drawnGif`/`drawnHost` masks, and the per-pixel `delta` loop.
- Produces: two widened buckets — `rounding` also accepts `delta <= 2` when **both** renderings drew the pixel and the dump's draws had alpha blending enabled (`ABE=1`); `edge` also accepts an *interior* pixel whose value appears within tolerance 2 in the other rendering's 3×3 neighbourhood. `hard` keeps its meaning: a wrong lane or a wrong context.

- [ ] **Step 1: Record the baseline**

Run `dist/vu1_replay.exe --vram-diff <outdir> tests/fixtures/vu1/dispatch_0x1b50/*.bin` and save every `VRAMDIFF` line. These are the numbers the widening must not disturb for the 14 currently-passing dumps.

- [ ] **Step 2: Implement the two widenings**

Blend-amplified rounding: at `ABE=1` a one-step source difference becomes a two-step destination difference, so `delta <= 2` is rounding *only* when `drawnGif[p] && drawnHost[p]` and the dump drew with blending on. Interior seams: a colour seam between two adjacent triangles can sit one pixel over while both sides are drawn, so `boundaryAt` never fires; accept it as `edge` when the pixel's RGBA appears within tolerance 2 somewhere in the other rendering's 3×3 neighbourhood. **The tolerance must be ≥ 2 — an exact-match lookup misses two of `prog_182`'s six large-delta pixels** (measured in Sprint 3).

- [ ] **Step 3: Prove the widening is not a blanket pass**

The `+8 px` sanity experiment from Sprint 3 (deliberately offsetting one rendering by 8 pixels) must still score 29–55 %, i.e. the buckets still catch a real divergence. Run it and quote the number. Then re-run Step 1's 14 dumps: every number must be unchanged or lower, and none may newly fail.

- [ ] **Step 4: Add the held-out dump**

Add `vu1dump4_prog_182.bin` to `tests/fixtures/vu1/dispatch_0x1b50/` with its golden line (regenerate the fixture golden with `--no-native`, checking the run prints `native entered=0 ended=0 handbacks=0`). It scored 1.488 % against the 1 % tolerance before the widening; report its new number. All four `./build.sh test` verify invocations (`--no-native`, `--native --regs all`, `--native --host-draw --regs all`) must pass with it present.

- [ ] **Step 5: `./build.sh test` exit 0** with `checked=15 skipped=0` and no `[vu1_replay] WARNING`.

- [ ] **Step 6: Commit**

`git add third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp tests/fixtures/vu1/dispatch_0x1b50 build.sh && git commit -m "vu1_replay(--vram-diff): blend-amplified rounding and interior seams are by-design, not hard -- prog_182 rejoins the fixture set" && git push`

---

### Task 4: Ground height

**Files:**
- Create: `docs/research/17-ground-height.md`
- Modify (only if the fix is bounded): the runtime file the trace implicates

**Interfaces:**
- Consumes: STATUS 2026-09-09 01:30/02:10 — the vertical collision probe is identical to PCSX2's (hit y = -146.371, same normal) but the actor rests **14.7** above it on ours vs **20.1** on the console; mover vtable `0x6694b0`, actor vtable `0x6691a0` (mover at actor `+0xc0`); mover `+0x5c` = 4.0 vs 6.3338, `+0x70..+0x7c` differ; actor `+0x10` state `0x00080502` vs `0x2`; actor `+0x2bc..` holds a cached ground point on ours. Tools: `PS2X_CALL_TRACE="0xADDR:name"`, `PS2X_CALL_TRACE_DUMP="<Name>:a<k>[+0xOFF][*[+0xOFF]]:<words>"`, `PS2X_CALL_TRACE_EVERY`, `PS2X_PEEK` + `PS2X_TRIGGER`, `PS2X_RDRAM_DUMP_AT`.
- Produces: the note, naming the writer of `mover+0x90.y`, the value it writes, and where ours diverges from the console.

- [ ] **Step 1: Find the writer.** Trace the mover's update method with `PS2X_CALL_TRACE_DUMP` on the mover object during `scripts/parity/gameplay_probe.txt`, dumping `+0x5c`, `+0x70..+0x7c` and `+0x90` per call. Identify which call changes `+0x90.y` and what it reads first.
- [ ] **Step 2: Compare against the console.** The same trace under PCSX2 is not available, so use the captured console values (STATUS 01:30/02:10) as the reference and state explicitly which console numbers are measured and which are inferred. If the divergence is a *constant* (4.0 vs 6.3338 smells like a capsule radius or a step height), find where that constant is loaded on ours.
- [ ] **Step 3: Fix only if bounded** — one hypothesis, one build, one `gameplay_probe.txt` run showing the rest height at ~20.1 with the mission gate still green. Otherwise write the note with the exact divergence and stop. **Commit either way** (note always; code if fixed).

---

### Task 5: S0 — does the freeze reproduce on PCSX2 against our server?

**Files:**
- Create: `docs/research/18-online-round-start.md` (§1: the S0 verdict)
- Create: `logs/s4_pcsx2_match.sh` (the detached two-instance PCSX2 run script; `logs/` is gitignored, so copy the recipe into the note)

**Interfaces:**
- Consumes: `tools/pcsx2/` (one install — a second instance needs its own portable/config directory; `tools/pcsx2_b` from earlier sprints is gone and must be recreated as a copy), the local Horizon server under `server/` (`horizon-docker/` brings it up), `PS2X_SOCOM2_SERVER`-style host redirection for PCSX2 (PCSX2 has no such env knob — redirect via the host machine's hosts file or the server's own DNS/config, and record exactly what you did), `scripts/parity/` login scripts for reference on the click path.
- Produces: a recorded verdict — **runtime implicated** (PCSX2 reaches playable gameplay against our server) or **runtime exonerated** (PCSX2 freezes at "STARTING ROUND 1 OF 11" exactly as ours does) — with both instances' screens at the freeze point and the server-side log slice covering the same seconds.

- [ ] **Step 1: Stand up two PCSX2 instances.** Copy `tools/pcsx2` to a second directory with its own config/memcard so two can run at once. Verify both boot the game to the main menu before involving the server.
- [ ] **Step 2: Drive both to a match.** Follow the same click path `online_match_ours.py` uses (A hosts, B joins, `--same-team` equivalent so both spawn together). Capture screens each second from the lobby through 60 s past round start.
- [ ] **Step 3: Read the verdict.** Frozen at "STARTING ROUND 1 OF 11" with only camera pitch responding → runtime exonerated, S1 goes server-side. Playable (the player walks) → runtime implicated, S1 goes guest-side. **Anything ambiguous is reported as ambiguous** — do not round toward the convenient answer.
- [ ] **Step 4: Capture the server's view.** Slice `server/logs/console-DME.log` and `console-Medius.log` over the same seconds and include what the server did or did not send after both players readied.
- [ ] **Step 5: Write §1 of research/18** with the verdict, the evidence, and the exact recipe (the note must let someone else re-run this). No runtime code, no commit by the implementer — the controller commits the note.

---

### Task 6: S1 — unblock the round start

**Files:**
- Modify: `docs/research/18-online-round-start.md` (§2: the state machine and the condition that never becomes true)
- Modify (whichever S0 implicates): `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` and/or the runtime path it names; **or** `server/dme-plugins`, `server/medius-plugins`, `server/horizon-server`

**Interfaces:**
- Consumes: S0's verdict; the decoded peer protocol (22-byte reliable-channel packets, little-endian `00 01 0a 00 | 0 | 0 | T 00 02 00 | S 00 Q 00 | P 00`, T ∈ {0x81, 0x82, 0x89}, S = sender index, Q = per-sender sequence, P = payload word; acked both ways at ~1/s); `PS2X_SOCOM2_NET_TRACE=1` (udp counters plus hex of the first 16 peer packets); `PS2X_SOCOM2_SERVER=192.168.2.10` (without it the exe advertises 127.0.0.1 as its own address); `PS2X_CALL_TRACE` on `FUN_00247fe8` / `exUdpRecv`; the SCERT ids in `RT.Common/Types.cs` (CLIENT_CONNECT_AUX_UDP 0x16, SERVER_CONNECT_ACCEPT_AUX_UDP 0x19, CLIENT_HELLO 0x24, SERVER_HELLO 0x25, UDP_APP 0x0c, ECHO 0x05).
- Produces: either both instances leaving "STARTING ROUND 1 OF 11" with local control enabled (LX/LY/RX moving the player, proven by `PS2X_SOCOM2_INPUT_FILE` injection and screens), or §2 of the note naming the exact condition that never becomes true.

- [ ] **Step 1: Read the state machine on the implicated side.** Guest-side: trace the callers of the UDP send/recv on **both** instances simultaneously (`PS2X_CALL_TRACE` + `_DUMP` on the receiver's buffer) and reconstruct who waits for what. Server-side: find where the DME/Medius plugin decides a world is ready to start and what it broadcasts, and diff that against what `server/logs` shows it actually sent.
- [ ] **Step 2: Name the condition.** One sentence of the form "X never becomes true because Y never arrives / never fires", with the evidence line beside it. Write it into §2 before attempting any fix — a fix without this sentence is a guess.
- [ ] **Step 3: Fix if bounded.** One hypothesis → one build/server change → one two-instance run. Success is both instances in gameplay with the player moving under pad injection on both sides. **Two attempts maximum**; if the second fails, stop, finish the note, and report `DONE_WITH_CONCERNS` — S2 and S3 then do not run and the sprint says so plainly.
- [ ] **Step 4: Guard the regression.** If a fix lands, capture the working state as a run recipe in the note so a later change that re-freezes the round is caught by re-running it.
- [ ] **Step 5: Commit** the note and any code/server change together.

---

### Task 7: S2 — movement and aim calibration

**Only runs if Task 6 unblocked the round.**

**Files:**
- Modify: `tools_py/parity/online_match_ours.py`
- Modify: `docs/research/18-online-round-start.md` (§3: the calibration numbers)

**Interfaces:**
- Consumes: `PS2X_SOCOM2_INPUT_FILE` pad injection (drivers write `logs/pad_A.txt` / `logs/pad_B.txt`), `PS2X_SOCOM2_INPUT_TRACE=1` to prove inputs reached the guest, `PS2X_PEEK="0x416054:3"` printing each instance's position once per second, the existing `--sweep`/`--sweep-hold`/`--turn-key` flags (`L` = right stick right / Precision Shooter look, `D` = left stick right / Sure Shot turn).
- Produces: `--walk-to-b` — A reads both positions, computes the bearing to B, turns by a timed hold using the measured degrees-per-second, walks until within a set distance, and stops; the measured constants recorded in the note and as named constants in the module (no magic numbers at call sites).

- [ ] **Step 1: Calibrate the turn.** Hold the turn key for a fixed time from a known heading, read the compass in the captured frames, and derive degrees per second for both `L` and `D`. Repeat three times; report the spread, not just the mean.
- [ ] **Step 2: Calibrate the walk.** Same method for forward movement using the two `0x416054` position peeks: units per second.
- [ ] **Step 3: Implement `--walk-to-b`** using those constants, with a hard step cap so a mis-calibration cannot run the match forever.
- [ ] **Step 4: Prove it.** One run where A ends within the set distance of B, shown by the position rows, with the frames captured.
- [ ] **Step 5: Commit.**

---

### Task 8: S3 — kill detection and the acceptance test

**Only runs if Task 7 landed.**

**Files:**
- Modify: `tools_py/parity/online_match_ours.py`
- Modify: `docs/research/18-online-round-start.md` (§4: where the kill state lives)

**Interfaces:**
- Consumes: Task 7's `--walk-to-b`; the player actor (vtable `0x6691a0`) and the per-player record near it; `PS2X_PEEK` with `PS2X_TRIGGER="lo:hi"` (fires when the first peeked word enters a range — the mechanism for "health crossed zero"); the DME world state in `server/logs`.
- Produces: `--until-kill` — the run ends when B's death or the round end is observed, with both instances' screens captured at that moment and a single line printed stating which signal fired (guest memory or server log) and at what time.

- [ ] **Step 1: Find the health/kills record.** With both instances in gameplay, fire at B and watch candidate offsets near the actor for a value that changes on damage and reaches zero on death. Confirm across two separate kills before believing it.
- [ ] **Step 2: Cross-check against the server.** The DME log should show the same event; if the two disagree, prefer the server's and say why in the note.
- [ ] **Step 3: Implement `--until-kill`** with a timeout, so a failed match ends as a clean FAIL rather than hanging.
- [ ] **Step 4: Run the acceptance test end to end** — one command, A kills B, both screens captured, exit 0. Record the command and the artefact paths; this is the sprint's headline evidence.
- [ ] **Step 5: Commit.**

---

### Task 9: Docs and close

- [ ] `docs/STATUS.md` "Current state" (five lines) + one dated Sprint 4 entry with the artefact paths; `README.md` knobs; `docs/LOOP_PROMPT.md` goals 3 and 4 (goal 4's text changes materially if the acceptance test now runs); `docs/HANDOFF.md` "START HERE"; tick this plan's boxes and note where reality diverged.
- [ ] Record what did **not** land with the reason (especially if Wave 2 stopped at S0 or S1) — the spec's definition of done requires the sprint to say why.
- [ ] `PS2X_TEST_REPEAT=3 ./build.sh test` exit 0; a final full gate at the defaults (`--stamp s4_head_1x`) PASS 3/3 with title s00–s19 ≥ 99 against `logs/parity/gate/s3_head_1x/title`.
- [ ] Commit and push. **The controller runs the merge**, not this task.

---

## Self-review

- **Spec coverage:** §2.1 → Task 1; §2.2 → Task 2; §2.3 → Task 3; §2.4 → Task 4; §2.5 → Task 5; §2.6 → Task 6; §2.7 → Task 7; §2.8 → Task 8; §4 DoD → Tasks 1-8 plus Task 9's "what did not land" requirement; §5's sequencing → Tasks 5-8 are gated on each other explicitly, Tasks 1-4 are marked file-disjoint.
- **Placeholders:** Task 2 carries its full test code; Tasks 1 and 3 name exact functions, line ranges and the decision rule; Tasks 5-8 are procedural by necessity (their content is the previous stage's output) but each carries its own stop rule and a named deliverable, as the macroblock spike did successfully in Sprint 3.
- **Type consistency:** `crop_to_content(im, thresh=8)` (Task 2) is the only new Python helper and is called from three sites named in the file map; `movie_blocks.py`'s CLI contract (Task 1) is used only by Task 1 and Task 9's evidence; `--walk-to-b` (Task 7) is consumed by `--until-kill` (Task 8); the bucket names `rounding`/`edge`/`hard` (Task 3) match the existing printout.
- **Known risk, stated in the plan not just the spec:** Task 6 has a two-attempt cap and an explicit "S2/S3 do not run" consequence, so the sprint cannot silently become an open-ended investigation.
