# Sprint 4 — Visible Defects, Gate Trust, and the First-Kill Online Test: Implementation Plan

> **ARCHIVED 2026-09-23 — Sprint 4's plan, closed 2026-09-13. Cited by `docs/archive/HANDOFF-reference-to-2026-09-13.md` and the Sprint 4 spec beside it; kept verbatim.**
> Moved here from `docs/superpowers/plans/` in Sprint 11; nothing below it was edited except those
> citations that pointed at this block's own old paths. It is a record, not an instruction.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the last defects you can see on screen (intro-movie macroblocks, ground height), make the parity gate incapable of hiding a red run, close the `--vram-diff` calibration, and then drive a two-instance online match to a first kill — the user's standing definition of "playable".

**Architecture:** Wave 1 is four independent bounded fixes, each with its own check, because the parity gate cannot see two of them. Wave 2 is strictly sequential and opens with a decisive experiment (S0) that decides whether the round-start freeze lives in our runtime or in the local Horizon server, so the expensive stages read the right body of code; S1 unblocks the round, S2 calibrates movement and aim, S3 reads the kill state and wires the acceptance test.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh`), CMake/Ninja, OpenGL through raylib/rlgl, MiniTest, Python 3 (numpy, Pillow), PCSX2 as the console reference, a local Horizon server (Medius/DME, C# sources under `server/`), Git Bash + PowerShell for detached runs.

**Spec:** `docs/archive/sprints-1-6/2026-09-12-sprint-4-visible-defects-and-first-kill-design.md`

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

- [x] **Step 1: Write the check first (it must fail on today's binary)**

`movie_blocks.py` reads the `PS2X_GS_DUMP_DISPLAY` triples, and for each picture computes the 16×16 pure-black block mask of the `gpu` layer and of the `shadow` layer, then reports `mask_gpu & ~mask_shadow` — blocks black on the GPU but not black in shadow VRAM. This is strictly stronger than research/16's ffmpeg recipe and needs no reference decode: the shadow layer *is* the reference for the mirror stage, and research/16 already proved the decode clean. Print block coordinates, never an absolute black count (the movie genuinely contains black blocks — this trap cost the Sprint 3 spike a false positive).

- [x] **Step 2: Capture and confirm the check fails**

Detached `title_only.txt` run with `PS2X_GS_DUMP_DISPLAY=logs/mb_s4:<t0>:<t1>` over the intro seconds. Run the check. Expected: a non-zero `MISSING` count naming blocks at multiples of 16 — the same signature research/16 recorded (pictures 965, 1085, 1447).

- [x] **Step 3: Do the count that decides candidate 1**
  > **Done, and it said NO.** The count that was supposed to prove candidate 1 measured the predicted byte-accumulator case at **zero** — see the Outcome section.

Add a temporary counter (stderr, env-gated, removed before the commit) or use `PS2X_GS_TRACE_PAGES`: per movie frame, count `executeTransfer` calls with `command.trxreg.rrw == 16 && command.trxreg.rrh == 16` against `refreshRenderTargetsFromShadow` calls made from `executeUpload`. Record both numbers in your report.

- [x] **Step 4: Fix, if the count proves it**
  > **A fix landed, for a different cause.** Candidate 1 was disproved; the defect was a cross-thread race on `m_currentTransfer` (`4a701f1`).

If refreshes are fewer than 16×16 transfers, candidate 1 is proven: `executeUpload` refreshes only when `m_uploadReceivedBytes >= m_uploadExpectedBytes` (line ~1280), and `executeTransfer` resets `m_uploadReceivedBytes = 0` and overwrites `m_currentTransfer` (lines ~1264-1266) — so any rectangle whose bytes did not complete before the next transfer began is written into shadow VRAM and **never mirrored to the GL texture**. Fix: before `executeTransfer` overwrites `m_currentTransfer`, if the previous transfer left `m_uploadExpectedBytes != 0 && m_uploadReceivedBytes != 0` (a partially-delivered rectangle), refresh the render targets for the *previous* rectangle first. Keep the change surgical and comment it with the counted evidence.

If the count *disproves* candidate 1 (refreshes match transfers), **do not guess**: record the numbers in research/16, name the next candidate, and report `DONE_WITH_CONCERNS` with no runtime change.

- [x] **Step 5: Prove the fix**

`./build.sh runtime`, re-capture, and re-run `movie_blocks.py`: expected `MISSING blocks=0`. Then `./build.sh test` exit 0 and a detached full gate (`--stamp s4_mb`) PASS 3/3 with title s00–s19 ≥ 99 against `logs/parity/gate/s3_head_1x/title`.

- [x] **Step 6: Commit**

`git add tools_py/parity/movie_blocks.py third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp docs/research/16-intro-movie-macroblocks.md && git commit -m "gs-gl: mirror a movie block whose upload was cut short by the next transfer (the blocks were in shadow VRAM, never on the GPU)" && git push`

---

### Task 2: `drive.py` crops to the non-black rect before scoring

**Files:**
- Modify: `tools_py/parity/drive.py` (`frame()` at 65-66; the `untilref`/`ifref` thumbnail builders at ~223 and ~251)
- Create: `tools_py/tests/test_drive_crop.py`

**Interfaces:**
- Consumes: `winshot.grab(hwnd)` returning a PIL Image of the window client area.
- Produces: `drive.crop_to_content(im, thresh=8)` → PIL Image with uniformly-black border rows/columns removed (returns the input unchanged when nothing is black-bordered, and when the whole frame is black); `frame()` and both reference-thumbnail builders call it before `.resize((160, 112))`.

- [x] **Step 1: Write the failing tests**

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

- [x] **Step 2: Run them and watch them fail**

`python -m unittest tools_py.tests.test_drive_crop -v` → FAIL, `ImportError: cannot import name 'crop_to_content'`.

- [x] **Step 3: Implement**

`crop_to_content` computes a per-row and per-column max over the greyscale frame, finds the first and last index above `thresh`, and crops to that box; if no index is above the threshold (an all-black frame) it returns the image unchanged — **the transition gate scores black frames on purpose, and cropping them away would break it.**

- [x] **Step 4: Tests pass, and the gate's own suite still passes**

`python -m unittest tools_py.tests.test_drive_crop -v` → 5 passed. `python -m unittest tools_py.tests.test_gate` → 24 passed.

- [x] **Step 5: Prove it on a real pillarboxed run**

Use `tools_py/parity/resize_window.py` (committed in Sprint 3 for exactly this) to drive a title run at a stretched window, then score it run-vs-run against `logs/parity/gate/s3_head_1x/title`. Before this task such a run fell to the 16/23 pass floor (Sprint 3 measured 66.4 on one capture); after it, the scores must land in the normal band. Record both numbers.

- [x] **Step 6: Commit**

`git add tools_py/parity/drive.py tools_py/tests/test_drive_crop.py && git commit -m "parity(drive): score the content rect, not the window -- a resized window degraded the title score smoothly to the pass floor instead of failing" && git push`

---

### Task 3: `--vram-diff` bucket calibration and `vu1dump4_prog_182`

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` (the classification loop at ~492-541)
- Modify: `tests/fixtures/vu1/dispatch_0x1b50/` (add `vu1dump4_prog_182.bin` + its golden line), `build.sh` (run 6 comment)

**Interfaces:**
- Consumes: the existing `boundaryAt(mask, x, y)` helper, the `drawnGif`/`drawnHost` masks, and the per-pixel `delta` loop.
- Produces: two widened buckets — `rounding` also accepts `delta <= 2` when **both** renderings drew the pixel and the dump's draws had alpha blending enabled (`ABE=1`); `edge` also accepts an *interior* pixel whose value appears within tolerance 2 in the other rendering's 3×3 neighbourhood. `hard` keeps its meaning: a wrong lane or a wrong context.

- [x] **Step 1: Record the baseline**

Run `dist/vu1_replay.exe --vram-diff <outdir> tests/fixtures/vu1/dispatch_0x1b50/*.bin` and save every `VRAMDIFF` line. These are the numbers the widening must not disturb for the 14 currently-passing dumps.

- [x] **Step 2: Implement the two widenings**

Blend-amplified rounding: at `ABE=1` a one-step source difference becomes a two-step destination difference, so `delta <= 2` is rounding *only* when `drawnGif[p] && drawnHost[p]` and the dump drew with blending on. Interior seams: a colour seam between two adjacent triangles can sit one pixel over while both sides are drawn, so `boundaryAt` never fires; accept it as `edge` when the pixel's RGBA appears within tolerance 2 somewhere in the other rendering's 3×3 neighbourhood. **The tolerance must be ≥ 2 — an exact-match lookup misses two of `prog_182`'s six large-delta pixels** (measured in Sprint 3).

- [x] **Step 3: Prove the widening is not a blanket pass**

The `+8 px` sanity experiment from Sprint 3 (deliberately offsetting one rendering by 8 pixels) must still score 29–55 %, i.e. the buckets still catch a real divergence. Run it and quote the number. Then re-run Step 1's 14 dumps: every number must be unchanged or lower, and none may newly fail.

- [x] **Step 4: Add the held-out dump**

Add `vu1dump4_prog_182.bin` to `tests/fixtures/vu1/dispatch_0x1b50/` with its golden line (regenerate the fixture golden with `--no-native`, checking the run prints `native entered=0 ended=0 handbacks=0`). It scored 1.488 % against the 1 % tolerance before the widening; report its new number. All four `./build.sh test` verify invocations (`--no-native`, `--native --regs all`, `--native --host-draw --regs all`) must pass with it present.

- [x] **Step 5: `./build.sh test` exit 0** with `checked=15 skipped=0` and no `[vu1_replay] WARNING`.

- [x] **Step 6: Commit**

`git add third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp tests/fixtures/vu1/dispatch_0x1b50 build.sh && git commit -m "vu1_replay(--vram-diff): blend-amplified rounding and interior seams are by-design, not hard -- prog_182 rejoins the fixture set" && git push`

---

### Task 4: Ground height

**Files:**
- Create: `docs/research/17-ground-height.md`
- Modify (only if the fix is bounded): the runtime file the trace implicates

**Interfaces:**
- Consumes: STATUS 2026-09-09 01:30/02:10 — the vertical collision probe is identical to PCSX2's (hit y = -146.371, same normal) but the actor rests **14.7** above it on ours vs **20.1** on the console; mover vtable `0x6694b0`, actor vtable `0x6691a0` (mover at actor `+0xc0`); mover `+0x5c` = 4.0 vs 6.3338, `+0x70..+0x7c` differ; actor `+0x10` state `0x00080502` vs `0x2`; actor `+0x2bc..` holds a cached ground point on ours. Tools: `PS2X_CALL_TRACE="0xADDR:name"`, `PS2X_CALL_TRACE_DUMP="<Name>:a<k>[+0xOFF][*[+0xOFF]]:<words>"`, `PS2X_CALL_TRACE_EVERY`, `PS2X_PEEK` + `PS2X_TRIGGER`, `PS2X_RDRAM_DUMP_AT`.
- Produces: the note, naming the writer of `mover+0x90.y`, the value it writes, and where ours diverges from the console.

- [x] **Step 1: Find the writer.** Trace the mover's update method with `PS2X_CALL_TRACE_DUMP` on the mover object during `scripts/parity/gameplay_probe.txt`, dumping `+0x5c`, `+0x70..+0x7c` and `+0x90` per call. Identify which call changes `+0x90.y` and what it reads first.
- [x] **Step 2: Compare against the console.** The same trace under PCSX2 is not available, so use the captured console values (STATUS 01:30/02:10) as the reference and state explicitly which console numbers are measured and which are inferred. If the divergence is a *constant* (4.0 vs 6.3338 smells like a capsule radius or a step height), find where that constant is loaded on ours.
- [x] **Step 3: Fix only if bounded** — one hypothesis, one build, one `gameplay_probe.txt` run showing the rest height at ~20.1 with the mission gate still green. Otherwise write the note with the exact divergence and stop. **Commit either way** (note always; code if fixed).
  > **Note branch taken, deliberately.** No fix: Task 4 *reframed its own defect* (it is the camera, not the ground) rather than fixing it, and the localisation left two candidates a single run apart. See the Outcome section.

---

### Task 5: S0 — does the freeze reproduce on PCSX2 against our server?

**Files:**
- Create: `docs/research/18-online-round-start.md` (§1: the S0 verdict)
- Create: `logs/s4_pcsx2_match.sh` (the detached two-instance PCSX2 run script; `logs/` is gitignored, so copy the recipe into the note)

**Interfaces:**
- Consumes: `tools/pcsx2/` (one install — a second instance needs its own portable/config directory; `tools/pcsx2_b` from earlier sprints is gone and must be recreated as a copy), the local Horizon server under `server/` (`horizon-docker/` brings it up), `PS2X_SOCOM2_SERVER`-style host redirection for PCSX2 (PCSX2 has no such env knob — redirect via the host machine's hosts file or the server's own DNS/config, and record exactly what you did), `scripts/parity/` login scripts for reference on the click path.
- Produces: a recorded verdict — **runtime implicated** (PCSX2 reaches playable gameplay against our server) or **runtime exonerated** (PCSX2 freezes at "STARTING ROUND 1 OF 11" exactly as ours does) — with both instances' screens at the freeze point and the server-side log slice covering the same seconds.

- [x] **Step 1: Stand up two PCSX2 instances.** Copy `tools/pcsx2` to a second directory with its own config/memcard so two can run at once. Verify both boot the game to the main menu before involving the server.
- [x] **Step 2: Drive both to a match.** Follow the same click path `online_match_ours.py` uses (A hosts, B joins, `--same-team` equivalent so both spawn together). Capture screens each second from the lobby through 60 s past round start.
- [x] **Step 3: Read the verdict.** Frozen at "STARTING ROUND 1 OF 11" with only camera pitch responding → runtime exonerated, S1 goes server-side. Playable (the player walks) → runtime implicated, S1 goes guest-side. **Anything ambiguous is reported as ambiguous** — do not round toward the convenient answer.
- [x] **Step 4: Capture the server's view.** Slice `server/logs/console-DME.log` and `console-Medius.log` over the same seconds and include what the server did or did not send after both players readied.
- [x] **Step 5: Write §1 of research/18** with the verdict, the evidence, and the exact recipe (the note must let someone else re-run this). No runtime code, no commit by the implementer — the controller commits the note.

---

### Task 6: S1 — unblock the round start

**Files:**
- Modify: `docs/research/18-online-round-start.md` (§2: the state machine and the condition that never becomes true)
- Modify (whichever S0 implicates): `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp` and/or the runtime path it names; **or** `server/dme-plugins`, `server/medius-plugins`, `server/horizon-server`

**Interfaces:**
- Consumes: S0's verdict; the decoded peer protocol (22-byte reliable-channel packets, little-endian `00 01 0a 00 | 0 | 0 | T 00 02 00 | S 00 Q 00 | P 00`, T ∈ {0x81, 0x82, 0x89}, S = sender index, Q = per-sender sequence, P = payload word; acked both ways at ~1/s); `PS2X_SOCOM2_NET_TRACE=1` (udp counters plus hex of the first 16 peer packets); `PS2X_SOCOM2_SERVER=192.168.2.10` (without it the exe advertises 127.0.0.1 as its own address); `PS2X_CALL_TRACE` on `FUN_00247fe8` / `exUdpRecv`; the SCERT ids in `RT.Common/Types.cs` (CLIENT_CONNECT_AUX_UDP 0x16, SERVER_CONNECT_ACCEPT_AUX_UDP 0x19, CLIENT_HELLO 0x24, SERVER_HELLO 0x25, UDP_APP 0x0c, ECHO 0x05).
- Produces: either both instances leaving "STARTING ROUND 1 OF 11" with local control enabled (LX/LY/RX moving the player, proven by `PS2X_SOCOM2_INPUT_FILE` injection and screens), or §2 of the note naming the exact condition that never becomes true.

- [x] **Step 1: Read the state machine on the implicated side.** Guest-side: trace the callers of the UDP send/recv on **both** instances simultaneously (`PS2X_CALL_TRACE` + `_DUMP` on the receiver's buffer) and reconstruct who waits for what. Server-side: find where the DME/Medius plugin decides a world is ready to start and what it broadcasts, and diff that against what `server/logs` shows it actually sent.
- [x] **Step 2: Name the condition.** One sentence of the form "X never becomes true because Y never arrives / never fires", with the evidence line beside it. Write it into §2 before attempting any fix — a fix without this sentence is a guess.
- [x] **Step 3: Fix if bounded.** One hypothesis → one build/server change → one two-instance run. Success is both instances in gameplay with the player moving under pad injection on both sides. **Two attempts maximum**; if the second fails, stop, finish the note, and report `DONE_WITH_CONCERNS` — S2 and S3 then do not run and the sprint says so plainly.
- [x] **Step 4: Guard the regression.** If a fix lands, capture the working state as a run recipe in the note so a later change that re-freezes the round is caught by re-running it.
- [x] **Step 5: Commit** the note and any code/server change together.

---

### Task 7: S2 — movement and aim calibration

**Only runs if Task 6 unblocked the round.**

**Files:**
- Modify: `tools_py/parity/online_match_ours.py`
- Modify: `docs/research/18-online-round-start.md` (§3: the calibration numbers)

**Interfaces:**
- Consumes: `PS2X_SOCOM2_INPUT_FILE` pad injection (drivers write `logs/pad_A.txt` / `logs/pad_B.txt`), `PS2X_SOCOM2_INPUT_TRACE=1` to prove inputs reached the guest, `PS2X_PEEK="0x416054:3"` printing each instance's position once per second, the existing `--sweep`/`--sweep-hold`/`--turn-key` flags (`L` = right stick right / Precision Shooter look, `D` = left stick right / Sure Shot turn).
- Produces: `--walk-to-b` — A reads both positions, computes the bearing to B, turns by a timed hold using the measured degrees-per-second, walks until within a set distance, and stops; the measured constants recorded in the note and as named constants in the module (no magic numbers at call sites).

- [x] **Step 1: Calibrate the turn.** Hold the turn key for a fixed time from a known heading, read the compass in the captured frames, and derive degrees per second for both `L` and `D`. Repeat three times; report the spread, not just the mean.
- [x] **Step 2: Calibrate the walk.** Same method for forward movement using the two `0x416054` position peeks: units per second.
- [x] **Step 3: Implement `--walk-to-b`** using those constants, with a hard step cap so a mis-calibration cannot run the match forever.
- [ ] **Step 4: Prove it.** One run where A ends within the set distance of B, shown by the position rows, with the frames captured.
  > **Not met by Task 7.** The approach loop works and is calibrated, but a single mover cannot close the map inside a round (39 % closure efficiency, ~450 s needed against a ~360 s round). Two movers, in Task 8, closed 1485.5 → 50.0 units in ~127 s.
- [x] **Step 5: Commit.**

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
  > **Partial.** ~~`actor+0x204` (1.0) / `+0x208` (100000.0) are the candidates and read the same in every image, our own and the console's~~ — but the brief's bar is confirmation across **two separate kills** and this sprint got **zero**. ~~They stay in `KNOWN.md` §2, not §1.~~
  >
  > **Superseded 2026-09-13 by `docs/research/19` F1: `+0x204`/`+0x208` are NOT health — retracted in `KNOWN.md` §3.** Health is `actor+0x1044` (float, 1.0 full, `<= 0` dead) with an alive byte at `actor+0xF7A`, sourced from two community memory tools and confirmed against the decomp's damage-threshold compares. Still never read live online, so the box stays open: the *sourcing* moved; the *two-kill confirmation* did not happen.
- [x] **Step 2: Cross-check against the server.** The DME log should show the same event; if the two disagree, prefer the server's and say why in the note.
- [x] **Step 3: Implement `--until-kill`** with a timeout, so a failed match ends as a clean FAIL rather than hanging.
- [ ] **Step 4: Run the acceptance test end to end** — one command, A kills B, both screens captured, exit 0. Record the command and the artefact paths; this is the sprint's headline evidence.
  > ~~**In flight at the time of this close-out**; the box is left open deliberately rather than ticked on an expectation.~~
  > **Not met (Task 9b, 2026-09-13).** The test is one command (`online_match_ours.py --until-kill`) and it ran end to end on two maps; A never killed B. **Medley** (`ours_task8_kill2`): both players walked, closest true 3-D separation **50.0 units**, 0 % of rows inside any contact gate, rifles fired, no kill. **Frostfire**, the default map from 2026-09-13 (`ours_task8_frost1`): **neither player moved** — the move path ran 18 calls in 0.6 s at round start and never again. `RESULT PASS` is now reserved for a kill and cannot print until the health readout is confirmed. The first kill is Sprint 5's.
- [x] **Step 5: Commit.**

---

### Task 9: Docs and close

- [x] `docs/STATUS.md` "Current state" (five lines) + one dated Sprint 4 entry with the artefact paths; `README.md` knobs; `docs/LOOP_PROMPT.md` goals 3 and 4 (goal 4's text changes materially if the acceptance test now runs); `docs/HANDOFF.md` "START HERE"; tick this plan's boxes and note where reality diverged.
- [x] Record what did **not** land with the reason (especially if Wave 2 stopped at S0 or S1) — the spec's definition of done requires the sprint to say why.
- [x] `PS2X_TEST_REPEAT=3 ./build.sh test` exit 0; a final full gate at the defaults (`--stamp s4_head_1x`) PASS 3/3 with title s00–s19 ≥ 99 against `logs/parity/gate/s3_head_1x/title`.
  > ~~**Half done.**~~ `PS2X_TEST_REPEAT=3 ./build.sh test`: **exit 0** — 434 passed / 0 failed on each of the 3 passes, `--vram-diff` `checked=15 skipped=0` (Task 9b, under the loop lock). **The `s4_head_1x` gate was not run** — close-out was barred from runtime builds and game runs while Task 8 held the harness. The current `dist/socom2.exe` (the 19:17 build of `5ed29ca`) last passed a full gate 3/3 at `logs/parity/gate/20260912_192900`, and no runtime source has changed since; the run-vs-run ≥ 99 title comparison against `s3_head_1x` is the part that has no evidence. ~~Left open rather than ticked on that inference.~~
  >
  > **Closed with evidence, 2026-09-13 (final fix wave).** The missing comparison was computed offline rather than inferred: `logs/parity/gate/20260912_192900/title` s00–s19 scored run-vs-run against `logs/parity/gate/s3_head_1x/title` with `compare.score` (golden = `s3_head_1x`) gives **99.8–100.0** on all twenty (block 0.0 on every one; s19 = 100.0). That gate is PASS 3/3 (title, transition, mission — its `summary.txt`) on the same `dist/socom2.exe` the sprint ends on, and nothing under the runtime has changed since `5ed29ca` (`git diff 5ed29ca..HEAD` touches `run.sh`'s log path only, outside the exe). The evidence therefore sits under the stamp **`20260912_192900`**, not a directory named `s4_head_1x`; no new gate was run for the name alone.
- [x] Commit and push. **The controller runs the merge**, not this task.

---

## Self-review

- **Spec coverage:** §2.1 → Task 1; §2.2 → Task 2; §2.3 → Task 3; §2.4 → Task 4; §2.5 → Task 5; §2.6 → Task 6; §2.7 → Task 7; §2.8 → Task 8; §4 DoD → Tasks 1-8 plus Task 9's "what did not land" requirement; §5's sequencing → Tasks 5-8 are gated on each other explicitly, Tasks 1-4 are marked file-disjoint.
- **Placeholders:** Task 2 carries its full test code; Tasks 1 and 3 name exact functions, line ranges and the decision rule; Tasks 5-8 are procedural by necessity (their content is the previous stage's output) but each carries its own stop rule and a named deliverable, as the macroblock spike did successfully in Sprint 3.
- **Type consistency:** `crop_to_content(im, thresh=8)` (Task 2) is the only new Python helper and is called from three sites named in the file map; `movie_blocks.py`'s CLI contract (Task 1) is used only by Task 1 and Task 9's evidence; `--walk-to-b` (Task 7) is consumed by `--until-kill` (Task 8); the bucket names `rounding`/`edge`/`hard` (Task 3) match the existing printout.
- **Known risk, stated in the plan not just the spec:** Task 6 has a two-attempt cap (in the event a third, separately authorised attempt landed the fix — see Outcome §4) and an explicit "S2/S3 do not run" consequence, so the sprint cannot silently become an open-ended investigation.

---

## Outcome — what actually happened, and where reality diverged from this plan

Written at close-out (Task 9a, finished by Task 9b once Task 8 settled, 2026-09-13). The boxes
above are ticked against reality, not against intent; the four still open (Task 7 Step 4, Task 8
Steps 1 and 4, Task 9's gate box) are open on purpose and say why inline. Headline facts live
in `docs/KNOWN.md`; the sprint's carried findings are at `docs/STATUS.md` 2026-09-13,
`docs/research/16` §9.1.1 and `docs/research/17` §5.1 / §6.1.

**The plan's shape held. Its predictions mostly did not.** Wave 1's four bounded fixes stayed
bounded; Wave 2's decisive-experiment-first sequencing (S0 before S1) was the single best call in
the document and is the reason the sprint ended with a fix rather than another protocol decode.
What follows is where the text was wrong.

### 1. Three tasks were added mid-sprint and are not in this plan at all

| task | what it was | why it was not planned |
|---|---|---|
| **2b** | `drive.py` `ifburst` step — fire only if the preceding reference match succeeded (`99c1865`) | fell out of Task 2's review; the acceptance test needed it |
| **4b** | `rand()` re-implemented as newlib's LCG over the guest's own `_rand_next` (`ede2096`) | Task 4 found the 15-bit stub while diffing the mover, and the blast radius (249 sites) made deferring it worse than doing it |
| **4c** | five soft-double routines re-bound (`db7a992`) | same: found by Task 4 as an incidental in a table diff |

Both 4b and 4c came out of the *one task that was told not to fix anything*. That is not an
accident of scoping — a careful diff of two memory images is a high-yield instrument, and this plan
budgeted it as a single investigation step inside a task whose fix gate it could never meet.

### 2. Task 1's fix was **not** the cause this plan predicted

The plan committed to candidate 1 in advance: "count `executeTransfer` calls with `rrw == rrh == 16`
against `refreshRenderTargetsFromShadow` calls from `executeUpload`. If the second is smaller,
candidate 1 is proven and the fix is to mark the dirty rect from the transfer itself … rather than
from the byte accumulator."

The count ran and **measured the predicted byte-accumulator case at zero**. The real defect was a
**cross-thread race on `m_currentTransfer`** (`4a701f1`); the deficit went 3,748 → 0 and
`MISSING` 9 → 0. The plan was right that a count would decide it and wrong about what it would
decide — which is the good failure mode, and only because the step was written as *do the count*
rather than *apply the fix*. A step phrased as "make the change candidate 1 implies" would have
shipped a no-op and closed the ticket.

### 3. Task 4 **reframed its own defect** instead of fixing it

Task 4 was scoped as "ground height: make the actor rest at ~20.1". It established that there is
no ground-height defect at all: the player's feet match the console to **0.008**, and the 14.7 /
20.1 figures this plan quotes in its own Interfaces block are **camera-eye minus collision-hit**,
reconstructible from `STATUS.md`'s own recorded camera y values. The defect is the third-person
camera, ~5.4 low, localised to the player actor's skeleton root node decaying 11.4845 → 0
(`research/17` §4). No fix landed, deliberately: the evidence supports two candidates that one run
separates, and guessing sends the next reader to audit a VU0 macro-mode primitive that may be
innocent.

**The plan inherited the wrong frame from HANDOFF and restated it as fact in its Interfaces
block.** A plan that quotes a prior belief should quote it as a belief.

### 4. Wave 2 ran further than the plan's own risk note allowed for — and stopped short of a kill

- **Task 5 (S0)** reversed the project's documented world model: PCSX2 against **our** server plays
  a full round and advances to round 2. The "golden" that had said otherwise was two stills of a
  match with no input ever sent. Verdict: **runtime implicated**.
- **Task 6 (S1)** fixed it — ~~inside the two-attempt cap~~ **on a third fix attempt**, authorised by the controller as a separate decision after the plan's two attempts were spent and a bounded diagnostic (research/18 §3.9) had narrowed the layer: `sceInetInterfaceControl(0x200)` returned a
  constant, so `msSinceNetActivity` never reset and the movement scale clamped to 0.0 on frame one
  (`abf35bb`, then a same-binary A/B in one match, `5ed29ca`). Five hypotheses were falsified by
  measurement first — including two real divergences (advertised port, shared RSA keypair) whose
  fixes reached the wire and **moved nothing**.
- **Task 7 (S2)** is an honest partial. Calibration works; a single mover cannot close the map
  inside a round (39 % closure efficiency; ~450 s needed against a ~360 s round). It also measured
  the aim floor: `PAD_AXIS` injects only full deflection, so the shortest usable hold sweeps 35-40°
  against a body subtending 15-20° at contact range.
- **Task 8 (S3)** is an honest partial. Two movers closed the map — **1485.5 → 50.0 units** in
  ~127 s, **the first time two online players have met** — the rifles fired (96 R1 injections, ammo 30/30 → 0/30, impacts on
  the wall ahead of the muzzle), and **nobody died**: minimum separation **50.0** units, median
  **67.9**, **43.3°** of elevation between them, **0 %** of rows inside the 45-unit engage
  threshold in 3-D, and the sweep covered yaw only.

  > **Provenance, because this close-out itself got it wrong once.** Those are the **actor-row**
  > figures. An earlier draft of this section quoted "1392 units" and "~90 units apart with
  > 29-44°" — both from the camera+facing reconstruction, which mis-places a player by up to
  > two orbit radii (~50 units) and had already been superseded by the actor's own x/y/z at
  > words 7/8/9. It was superseded **silently**: the replacement measurement was published
  > without the one it replaced being marked, so a retracted number was written into a tracked
  > document *by the close-out task whose job was retracting things*.
  >
  > **The rule this earns: when a measurement replaces another, mark the predecessor superseded
  > where it is written** — the same discipline a false sentence gets. A number carries no
  > visible sign of being stale, which makes it the more dangerous of the two.

  ~~The health record is a *candidate*, not a fact: the brief's bar is two separate kills and the
  sprint got zero, so `actor+0x204`/`+0x208` stay in `KNOWN.md` §2.~~ **Superseded the same day by
  `docs/research/19` F1** (applying the rule in the blockquote above to this section's own
  sentence): `+0x204`/`+0x208` were never health and are retracted. Health is `actor+0x1044` with
  alive byte `actor+0xF7A` — sourced, confirmed statically, **not yet read live**.

  **And then the map changed.** On the owner's decision the default test map became **Frostfire**
  (spawns 692 units apart against Medley's 1485). The one Frostfire run reached gameplay on both
  instances with the pad arriving and the movement scale at 1.0 — and **neither player moved**:
  the move path `FUN_00553dc0` ran 18 calls in 0.6 s at round start and never again. Task 6's fix
  is proven on Medley and not in question; this is a second cause. Its lead (`research/19` F3) is
  uninitialised bytes in the `CZNetGame` round-state object at `*0x437ce8` — `0xAF` on ours,
  `0x00` on the console — including the "you are a ghost" flag `+0xd2`.

### 5. What the plan did not budget for at all

- **The harness costs about two runs per result**, and the online lobby flow reaches gameplay about
  four times in ten. Four of Task 6's runs failed to reach gameplay, three consecutively, each
  having written a full set of convincing screenshots first.
- **Retractions.** The plan folded them into Task 9, so four sentences known to be false stayed in
  the files every fresh session is told to read first — for a day, and in one case for two weeks.
  `docs/process-audit.md` now carries the rule: a review finding a committed sentence false
  produces a same-hour edit, and close-out *verifies* retractions rather than performing them.
- **KNOWN.md did not exist when this plan was written.** It was created mid-sprint (`2d9f73a`) at
  the user's request and is now the live proven / believed / retracted list, audited after every
  task. A future plan should name it as an output, not discover the need for it.

### 6. How the sprint ended (Task 9b, once Task 8 settled)

- **The spec's definition of done is not met on its headline.** The acceptance test exists, runs
  end to end from one command, and has never printed `PASS`, because no kill has happened on either
  map. That is recorded as a failure of the goal, not rounded to "nearly".
- **What it did deliver is the premise Sprint 5 stands on:** the movement blocker fixed and A/B'd,
  a position readout that is the actor's own coordinates rather than a reconstruction, contact
  measured in 3-D, a `PASS` that can only mean a kill, a verified map selection, and — from the
  research wave commissioned at the end of the sprint — a sourced health field and round-state
  object that make the kill readable without screenshots.
- **The sprint's last finding reversed its own map assumption.** Everything in Wave 2 was measured on
  Medley; the owner's switch to Frostfire exposed a second, unrelated control failure within one
  run. "The movement fix works" is true and map-scoped, and every movement claim from this sprint
  should be read with "on Medley" attached.
- **Handed to Sprint 5** (`docs/archive/sprints-1-6/2026-09-13-sprint-5-control-readout-and-first-kill-design.md`,
  `ee10842`): Frostfire control handover, confirming `actor+0x1044`/`+0xF7A` live, an online harness
  that cannot spend a match proving nothing, the HLE and heap liveness audit, the engagement ladder,
  and the acceptance run. ~~Also handed over unrun: this plan's `s4_head_1x` gate (Task 9's open box).~~ That box was closed with offline evidence in the final fix wave (title s00–s19 99.8–100.0 vs `s3_head_1x`; see Task 9).

## Rulings made on the owner's behalf

Every decision the controller took without the owner, in the order taken, each with its reasoning and
what it costs if wrong. Copied out of the gitignored sprint ledger before that ledger is deleted, so
these survive the workspace. Where a ruling was later reversed or corrected, the later entry says so.

1. Wave 1 Tasks 1, 2, 3 run in PARALLEL (file-disjoint; builds serialise on the lock), Task 4 follows when game-run pressure eases, and Wave 2 starts after Task 2 has landed so every online capture is scored by the fixed drive.py. Cost if wrong: wall-clock only.

2. the merge is the controller's, not Task 9's — same as Sprint 3.

3. the brief specified pytest-style bare test functions, but this repo's only runner is `python -m unittest` (build.sh and every script; tools_py/tests/test_gate.py uses unittest.TestCase) and pytest is invoked nowhere. Tests the project's runner cannot discover will never run again, so the five tests must be converted to unittest.TestCase methods with the same cases and assertions. Handed to the reviewer as a constraint to VERIFY rather than discover, since the plan text caused it. Cost if wrong: the tests are slightly more verbose than the brief's form.

4. this is a plan gap, not a task defect. Adding TASK 2b — make the transition probe's burst FOLLOW the dialog answer instead of sitting at a fixed index. Sprint 4's theme is a gate you can trust, and a gate whose burst can miss the thing it measures is the same class of defect Task 2 just fixed. Cost if wrong: one extra harness task; the alternative is re-running gates until the boot happens to be short, which is how a flake becomes a habit.

5. PARK the reviewer's unflagged gap (--furniture-baseline/--write-furniture are opt-in and nothing wires them in, so the safeguard is not load-bearing in any automated path) as a documented limitation plus a close-out note, rather than spending round 5. The residual it guards needs ALL of: corruption repeating above the bar, on the demoted tier only, while the counted tier stays clean — and black drops, the flavour this bug actually produces, never touch the furniture map at all (counted tier only, no absorption path). Cost if wrong: a future regression of a different flavour needs a manual baseline run to catch.

6. the two-attempt cap was on FIX attempts and both are spent, but the task's deliverable is the CONDITION SENTENCE and it is half-written. I authorised ONE further BOUNDED DIAGNOSTIC (no fix): the implementer's own §3.7 proposal, a single-process online-vs-single-player comparison of the movement branch — no second instance, no server, no wire, and cheaper than anything tried so far. It must stop and report after naming the condition; whether a third fix attempt follows is MY decision, not a continuation of the task. Cost if wrong: one cheap diagnostic run against a sprint goal the user explicitly chose to pursue to the end.

7. do NOT finish the starved A/B run. The reviewer judged the static evidence stronger than the A/B would be and named the exact three divergence sites; tracing those three argument values during gameplay answers the same question far more cheaply if anyone wants a measured delta. Cost if wrong: no measured before/after for a fix already shown correct by construction.

8. ONE more bounded diagnostic authorised and it is the LAST — the implementer's own §3.9 (resolve controller->vtbl_0x14 / vtbl_0x8c from the vtable pointer in both paths and compare). End-states fixed in advance: if it names the gate, the condition sentence is completed and I decide separately whether one fix attempt follows; if it does not, S1 closes as a documented residual and Tasks 7/8 do not run. Rationale: each step so far has excluded a real candidate rather than wandering, and the user chose the aggressive scope. Cost if wrong: one more diagnostic run against a goal the user explicitly chose to pursue to the end.

9. REDIRECTED the last diagnostic away from the vtable to two cheaper moves, on the reviewer's recommendation. Move 1: analyse the guard-operand dumps already on disk (ZERO new runs) and name which disjunct admits each path — if actor+0x174 != 8 online while it IS 8 in SP, that is very likely the missing half, since every consumer of that controllable-state field would be off, which is the symptom's exact shape (dead movement, live camera). Move 2: re-run the online probe on a build INCLUDING db7a992 — every Task 6 run predates the 15:28 soft-double fix, and dead yaw + dead translation while pitch still works is suspiciously the shape of broken yaw trig (broken floor makes __kernel_rem_pio2 return zero identically; the gimbal guard tested sinPitch < 1.0 instead of |sinPitch| < 1.0). SP moving on the broken build argues against sufficiency, but the re-run costs one match and would be embarrassing to skip. Cost if wrong: one match's wall-clock, against a lead the review rates above the instrument I had authorised.

10. ONE FIX ATTEMPT AUTHORISED (the separate decision I reserved), with the explicit constraint to fix the CAUSE not the symptom: neutering the cVar7 == 0 arm would make the player move and teach us nothing, since that arm fires on real hardware too. The attempt must first answer WHY cVar7 is 0 online on ours — if it is an input-authority/ownership flag, the defect is upstream and that is what to fix. Three cheap reads required first as preparation (disassemble 0x00567340; read DAT_0045a1ca at runtime; map axis indices 0/1/2 to LX/LY/RX so the three-not-four argument rests on measurement, not on the count matching), with instructions to stop if any contradicts the story. Cost if wrong: one build and one match, against a named gate.

11. the authorised fix attempt is REDIRECTED, not spent — one measurement run first (PS2X_PEEK=0x45a1ca:1 and 0x45a1c0:1 plus actor+0x1368; expect 1 and 0.0, stop if either reads otherwise), then fix the CAUSE in our runtime: make libnetb sceInetInterfaceControl code 0x200 return a real monotonic counter (host RX packets/bytes) instead of the constant 0. That is a correctness fix to our HLE of a PS2 network API — the right layer — and the opposite of patching FUN_00594cf0. Cost if wrong: one measurement run, which also falsifies the named gate for free.

12. NO second research wave yet. Every lead research/19 produced is settled by one peek or one A/B, which is cheaper and more decisive than more web research; a wave goes out if the Frostfire relaunch or the health read comes back contradicting the community sources. Cost if wrong: a second wave one run later than it could have been.

13. fix it in Sprint 4 rather than carry a flaky harness test into Sprint 5, and prefer REMOVING the race (stop the other side's in-flight hold on contact) over LOOSENING the bound — the overshoot is the same geometry failure the task fought all sprint, so it is correct live behaviour too. Required proof: five sequential solo passes of the full suite, reporting any failure rather than retrying, since the sim is wall-clock-timed. Cost if wrong: one short round.

14. this is the LAST amendment round run through review. Anything remaining afterwards I adjudicate myself and ledger, rather than looping — the plan has converged from three Criticals to one, and further rounds cost more than executing and learning. Cost if wrong: a residual design flaw surfaces in Task 5's first match instead of in review.

15. PARK the circling and stack-oscillation defects into Sprint 5 rather than a further Sprint 4 round. Sprint 5's engagement ladder redesigns exactly that endgame (strafing victim, stepping shooter, both-sides idle watch), so fixing the current endgame now would be rework. Cost if wrong: Sprint 5 inherits a harness that fails ~1 run in 5 until its ladder lands.

16. PARK that residual into Sprint 5 — its acceptance already requires three independent signals from different objects and processes, which is the structural answer; distinguishing a freed actor from a dead one on the health field alone is not cheap. Cost if wrong: a freed-actor transition could satisfy one of three required signals.
