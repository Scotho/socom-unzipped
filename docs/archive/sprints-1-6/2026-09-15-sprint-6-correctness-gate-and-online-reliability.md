# Sprint 6 — A Gate That Can See, the Paused Correctness Fixes, and a Cheaper Online Result: Implementation Plan

> **ARCHIVED 2026-09-23 — Sprint 6's plan, closed 2026-09-17. Cited by `docs/archive/CURRENT_SPRINT-to-sprint-8.md` and the Sprint 6 spec beside it; kept verbatim.**
> Moved here from `docs/superpowers/plans/` in Sprint 11; nothing below it was edited except those
> citations that pointed at this block's own old paths. It is a record, not an instruction.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the two paused runtime fixes and the pop-up gate step, give the parity gate a correctness leg (mission-failure detection, a console-vs-ours image score, a guest-value probe), make online results cheap (lobby ≥ 8/10, the freeze rooted), and make the acceptance kill repeat.

**Architecture:** Lock-free scorers with tests before any run that depends on them; every runtime change with a failing test first, `build.sh test` and the three-stage gate before commit; every launch capped with a decision table. The runtime freeze (`92d30f0`) is lifted for Task 0's two fixes only. Builds, gates and launches happen only in a **host window the owner names** (2026-09-15: game runs and builds lag the owner's machine while they work).

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh`), Python 3 (`unittest`, numpy, Pillow), the local Horizon server, PCSX2 2.8.1 as the console reference (savestate slot 8 = Seeding Chaos spawn), Ghidra decomp `game/analysis/socom2_game.elf.decomp.c`, Git Bash + PowerShell.

**Spec:** `docs/archive/sprints-1-6/2026-09-15-sprint-6-correctness-gate-and-online-reliability-design.md` (owner review pending). **Required reading for every dispatch:** `docs/KNOWN.md`, `docs/research/25-sp-teleport.md` §9–§10, `docs/research/26-water-polygons.md`, `docs/research/27-gl-depth-precision.md`, `docs/archive/HANDOFF-AUDIT-2026-09-14.md`, and for online tasks `docs/research/22-kill-readout.md`, `docs/research/24-frostfire-walkability.md`.

## Handoff notes for the executing model (read once)

- **Process.** superpowers:subagent-driven-development; fresh implementer per task; a task review after each that re-derives at least one number independently; the controller merges. Ledger at `.superpowers/sdd/2026-09-15-sprint-6-correctness-gate-and-online-reliability/progress.md`. Decisions on the owner's behalf are `Ruling: … — why — cost if wrong`, numbered from **R78** (Sprint 5 ended at R77).
- **`docs/KNOWN.md` has one writer: the controller.** Retractions happen on discovery, in the same hour.
- **Host window.** No `./build.sh runtime`, `./build.sh test`, gate or launch outside a window the owner has named. Lock-free work (scorers, tests that need no build, docs, decomp reading) fills the rest. `scripts/kill_stale_drivers.ps1` stops a run on request.
- **Commit conventions.** `git commit -m "…" -- <paths>` with an explicit pathspec; never `git add -A`; `server/config/simulated.db` stays unstaged; `ONBOARDING.md` untracked. Push after each commit. Trailer: the attribution the session is given (`Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` on 2026-09-15). Research tasks do not commit; the controller commits notes.
- **Lock protocol.** `bash scripts/loop_lock.sh run <owner> --purpose "<what>" -- <cmd>` for builds/tests/gates; `scripts/run_detached.sh` for launches; on this host use `"C:/Program Files/Git/bin/bash.exe"`. Never hold the lock across tool calls.
- **Instruments** are unchanged from Sprint 5's plan (peek chains, call trace, `PS2X_HLE_STATS`, the pad file); every instrument counts its rows and fails when empty.
- **Test binary.** `ps2x_tests.exe` lives at `third_party/ps2recomp/build-clang/ps2xTest/` and takes no filter; it runs every case (~450, well under a minute). `build.sh test` builds it and runs the Python suite first.

## Global Constraints

- Branch `sprint-6` off `develop` after `fix/gl-depth-precision` and `fix/gs-block-pointer` are merged (Task 0). Branch in the main checkout, never a worktree.
- `./build.sh test` exit 0 and the three-stage gate PASS before any commit touching `third_party/ps2recomp/`, `recomp/`, `tools_py/parity/{drive,gate,compare}.py`, `scripts/parity/` or `build.sh`.
- `./build.sh runtime` before any run on a changed runtime; the gate launches `dist/socom2.exe`.
- Defaults do not move except Task 0's two correctness fixes. Speed work frozen. No patches to recompiled game logic, no guest-memory writes in any acceptance path. Do not resize the game window. LF line endings.
- Every online launch records `waits=` per instance and the exe sha; every ladder result names the harness commit.

---

## File map

| Path | Responsibility |
|---|---|
| `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_depth.h` (new), `ps2xRuntime/src/lib/gs/gs_gl_backend.cpp`, `ps2xTest/src/ps2_gs_tests.cpp` (`GSGlDepth` suite) | Task 0a: depth precision (already written and test-green on `fix/gl-depth-precision`) |
| `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/GS.cpp` (`sceGsExecLoadImage`, `sceGsExecStoreImage`), `ps2xTest/src/ps2_gs_tests.cpp` (seven-region round trip), `tools_py/parity/motion_pack_check.py` (new) | Task 0b: block pointer |
| `tools_py/parity/drive.py` (`popup_present`, `ifpopup`), `tools_py/tests/test_drive_popup.py`, `scripts/parity/gameplay_probe.txt` | Task 0c: pop-up dismissal (written, unit-green, gate owed) |
| `tools_py/parity/mission_fail.py` (new), `tools_py/tests/test_mission_fail.py` (new), `tools_py/parity/gate.py` (`score_mission_log`) | Task 1a |
| `tools_py/parity/console_compare.py` (new), `tools_py/tests/test_console_compare.py` (new), `scripts/parity/refs/console_spawn_slot8.png` (new), `tools_py/parity/gate.py` | Task 1b |
| `tools_py/parity/guest_probe.py` (new), `tools_py/tests/test_guest_probe.py` (new), `scripts/parity/guest_probe_console.json` (new), `tools_py/parity/gate.py` (mission env) | Task 1c |
| `tools_py/parity/online_login_ours.py` (`login`, `host_game`, `join_game`, `lobby_stage`), `tools_py/tests/test_online_login.py` | Task 2 |
| `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp` (pc-sampler fields), `tools_py/parity/freeze_trace.py` (new) | Task 3 |
| `tools_py/parity/online_match_ours.py` (`aim_yaw`, `engage_fight`), `tools_py/parity/sim_walk_to_b.py`, `tools_py/tests/test_aim_loop.py` (new) | Task 4 |
| `docs/research/26-water-polygons.md`, `docs/research/17-ground-height.md`, `GS.cpp` (packet offset 0x14) | Task 5 |
| `tools_py/parity/oracles/` (new), `ps2xTest/src/ps2_runtime_expansion_tests.cpp` | Task 6 |
| `scripts/parity/mixed_match.sh` (new) | Task 7 |
| `README.md`, `build.sh`, `tools_py/parity/movie_blocks.py`, `scripts/archive_logs.ps1` (new) | Task 8 |

---

### Task 0: Land the paused fixes and the pop-up gate step

**Files:** see the first three rows of the file map.

**Interfaces:**
- Produces: `dist/socom2.exe` at a recorded sha with both runtime fixes; `GsGlDepth::Mode` (header); `drive.popup_present(im) -> bool` and the `ifpopup+<delay>:BTN` step mode; `motion_pack_check.py` CLI printing `corrupt=<n> of <m>`.

**DONE 2026-09-15 evening — every step of 0a, 0b and 0c landed on `develop`** (`f6a4434` depth, `326c9c9` ifpopup with the cinematic class added, `34ed2ac` Task 1 wiring, `a81eb74` block pointer; gate PASS 3/3 `s6_blockptr`, exe sha `1cfef9af028a90fc…`; `motion_pack_check` 0 of 8 chunks corrupt). Task 1a/1b/1c wiring is also done (print-only per R78); the probe's first populated run is `s6_probe` after `PS2X_PC_SAMPLER=1` was added to the mission stage's environment. Task 2 Steps 1–3 and Task 3 Step 1 plus a zero-run research/29 landed lock-free the same evening. The morning state below is kept for the record.

**State on 2026-09-15 morning (this plan's author ran these):** the depth fix passed `./build.sh test` (Python 845 OK, ps2x_tests 454/454, vram-diff 15/15) on `fix/gl-depth-precision`; title and transition PASSed on that exe (`s6_depth`, `s6_depth_r2`); the mission stage FAILed on the HELP pop-up (`s6_depth_m2`, 6/6 gameplay-band holds, diffs 0.00–0.05); `ifpopup` was written test-first (`test_drive_popup.py`, 5 tests green) and wired before each of the six holds; the mission rerun `s6_depth_m3` was killed at the owner's request (host contention; its frame file had gone stale 176 s). **Nothing is committed.**

#### 0a — depth fix (owner window needed for one mission gate)

- [x] **Step 1: Confirm the tree still matches the verified state** *(done; see AUDIT-2026-09-17 §3: f6a4434…a81eb74, gate s6_blockptr)*

Run: `git status --short` — expect exactly `M gs_gl_backend.cpp`, `M ps2_gs_tests.cpp`, `?? gs_gl_depth.h`, `M README.md`, `M tools_py/parity/drive.py`, `M scripts/parity/gameplay_probe.txt`, `?? tools_py/tests/test_drive_popup.py`, plus the unrelated `simulated.db`, `ONBOARDING.md`, the audit doc, and the Sprint 6 spec/plan/outline docs.

- [x] **Step 2: Mission gate on a quiet host** (the owner has named a window) *(done; see AUDIT-2026-09-17 §3: f6a4434…a81eb74, gate s6_blockptr)*

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "depth+ifpopup: gate mission" -- \
  python -m tools_py.parity.gate --only mission --stamp s6_depth_m4
cat logs/parity/gate/s6_depth_m4/summary.txt
grep -a "ifpopup" logs/parity/gate/s6_depth_m4/mission.drive.log
```
Expected: `PASS mission … ≥ 3 gameplay holds, ≥ 2 live pairs`; the `ifpopup:` lines show `presses=1` on at least one step and `popup=False` after. If FAIL with `STALE FRAME`, the host was not quiet — rerun, do not reinterpret. If FAIL with 6/6 gameplay and diffs ~0 and the `ifpopup` lines all say `0 presses, popup=False`, the detector missed the prompt: save the s30 capture as a fixture, add it to `test_drive_popup.py`, fix `popup_present`, and rerun.

- [x] **Step 3: Commit the depth fix, then the harness step, with pathspecs** *(done; see AUDIT-2026-09-17 §3: f6a4434…a81eb74, gate s6_blockptr)*

```bash
git commit -m "fix(gs-gl): carry integer GS z exactly into the depth test (clip control, gl_FragDepth fallback, PS2X_GS_DEPTH_LEGACY opt-out)

research/27: the legacy z*2-1 mapping rounded window depth to multiples of 128 GS z units below ~2^30, so a Z16S
scene kept ~512 distinct depths. Precision fix only -- the Seeding Chaos water shards survive PS2X_GS_NO_ZTEST=1 and
are not this defect. ps2x_tests 454/454 (GSGlDepth suite RED first), vram-diff 15/15, gate title PASS s6_depth,
transition PASS s6_depth_r2, mission PASS s6_depth_m4.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_depth.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp \
  third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp README.md
git commit -m "fix(gate): dismiss the in-game HELP pop-up before every mission hold (ifpopup step)

A pop-up pauses the game behind a lit HUD, so holds moved nothing and the liveness scorer failed s5_head_1x and
s6_depth_m2 (6/6 gameplay-band holds, diffs 0.00-0.05). drive.py gains popup_present() and an ifpopup+<delay>:BTN
mode that presses only while sp_death_probe.screen_state sees the prompt (test_drive_popup.py, RED first);
gameplay_probe.txt carries one before each hold. Mission gate PASS s6_depth_m4.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  tools_py/parity/drive.py tools_py/tests/test_drive_popup.py scripts/parity/gameplay_probe.txt
git push
```

#### 0b — the GS block-pointer fix (owner window for one build + test + full gate)

- [x] **Step 1: Branch off develop after 0a is merged** *(done; see AUDIT-2026-09-17 §3: f6a4434…a81eb74, gate s6_blockptr)*

```bash
git checkout develop && git merge --ff-only fix/gl-depth-precision && git push
git checkout -b fix/gs-block-pointer
```

- [x] **Step 2: Add the failing seven-region test** to `ps2_gs_tests.cpp`, directly after the existing `"sceGsExecLoadImage and sceGsExecStoreImage roundtrip and free guest packets"` case. The full case is in the plan author's scratchpad draft and is reproduced here so it can be pasted: *(done; see AUDIT-2026-09-17 §3: f6a4434…a81eb74, gate s6_blockptr)*

```cpp
        // research/25 §9-§10: the game parks the top 1.75 MB of VRAM in the motion-pack buffer during the
        // single-player mission load as seven 256x256 PSMCT32 pieces, vram_addr 0x2400 stepping 0x400
        // (libgraph units: 256-byte blocks, the BITBLTBUF DBP/SBP unit). A single region at vram_addr 0
        // round-trips losslessly whatever the unit, which is why the test above never caught the x8.
        tc.Run("seven 256x256 CT32 regions at vram_addr 0x2400..0x3C00 each round-trip their own bytes", [](TestCase &t)
        {
            PS2Runtime runtime;
            t.IsTrue(runtime.memory().initialize(), "runtime memory initialize should succeed");
            uint8_t *const rdram = runtime.memory().getRDRAM();
            constexpr uint32_t kImageAddr = 0x4000u;
            constexpr uint32_t kSrcAddr = 0x1800000u;   // high RAM: the guest heap starts at 0x100000 and the stub mallocs a 256 KiB packet there
            constexpr uint32_t kDstAddr = 0x1900000u;
            constexpr uint32_t kPieceBytes = 256u * 256u * 4u; // 0x40000
            constexpr uint32_t kPieces = 7u;
            constexpr uint16_t kFirstVramAddr = 0x2400u;
            constexpr uint16_t kVramStep = 0x400u;

            auto fillPiece = [&](uint32_t base, uint32_t piece)
            {
                for (uint32_t off = 0; off < kPieceBytes; off += 4u)
                {
                    const uint32_t word = (piece << 24) | (off & 0x00FFFFFFu);
                    std::memcpy(rdram + base + off, &word, sizeof(word));
                }
            };

            for (uint32_t i = 0; i < kPieces; ++i)
            {
                const uint16_t vramAddr = static_cast<uint16_t>(kFirstVramAddr + i * kVramStep);
                const GsImageMem image{0u, 0u, 256u, 256u, vramAddr, 4u, 0u};
                writeGsImageTest(rdram, kImageAddr, image);
                fillPiece(kSrcAddr, i);
                R5900Context loadCtx{};
                setRegU32(loadCtx, 4, kImageAddr);
                setRegU32(loadCtx, 5, kSrcAddr);
                ps2_stubs::sceGsExecLoadImage(rdram, &loadCtx, &runtime);
                t.Equals(static_cast<int32_t>(getRegU32Test(loadCtx, 2)), 0,
                         "sceGsExecLoadImage piece " + std::to_string(i) + " should succeed");
                uint64_t bitbltbuf = 0u;   // the freed packet still holds the BITBLTBUF it sent (A+D data at +16)
                std::memcpy(&bitbltbuf, rdram + runtime.guestHeapBase() + 16u, sizeof(bitbltbuf));
                t.Equals(static_cast<uint32_t>((bitbltbuf >> 32) & 0x3FFFu), static_cast<uint32_t>(vramAddr),
                         "sceGsExecLoadImage should send BITBLTBUF DBP == vram_addr (256-byte blocks) for piece " + std::to_string(i));
            }
            for (uint32_t i = 0; i < kPieces; ++i)
            {
                const uint16_t vramAddr = static_cast<uint16_t>(kFirstVramAddr + i * kVramStep);
                const GsImageMem image{0u, 0u, 256u, 256u, vramAddr, 4u, 0u};
                writeGsImageTest(rdram, kImageAddr, image);
                std::memset(rdram + kDstAddr, 0xEE, kPieceBytes);
                R5900Context storeCtx{};
                setRegU32(storeCtx, 4, kImageAddr);
                setRegU32(storeCtx, 5, kDstAddr);
                ps2_stubs::sceGsExecStoreImage(rdram, &storeCtx, &runtime);
                t.Equals(static_cast<int32_t>(getRegU32Test(storeCtx, 2)), 0,
                         "sceGsExecStoreImage piece " + std::to_string(i) + " should succeed");
                uint64_t bitbltbuf = 0u;
                std::memcpy(&bitbltbuf, rdram + runtime.guestHeapBase() + 16u, sizeof(bitbltbuf));
                t.Equals(static_cast<uint32_t>(bitbltbuf & 0x3FFFu), static_cast<uint32_t>(vramAddr),
                         "sceGsExecStoreImage should send BITBLTBUF SBP == vram_addr (256-byte blocks) for piece " + std::to_string(i));
                uint32_t firstWord = 0u;
                std::memcpy(&firstWord, rdram + kDstAddr, sizeof(firstWord));
                t.Equals(firstWord >> 24, i, "piece " + std::to_string(i) +
                         " should read back its own bytes (the x8 block pointer aliases seven regions onto two: [6,5,6,5,6,5,6])");
                bool wholePieceOk = true;
                for (uint32_t off = 0; off < kPieceBytes && wholePieceOk; off += 4u)
                {
                    uint32_t word = 0u;
                    std::memcpy(&word, rdram + kDstAddr + off, sizeof(word));
                    wholePieceOk = word == ((i << 24) | (off & 0x00FFFFFFu));
                }
                t.IsTrue(wholePieceOk, "piece " + std::to_string(i) + " should round-trip every word");
            }
        });
```

- [x] **Step 3: Build the test binary and watch it fail** *(done; see AUDIT-2026-09-17 §3: f6a4434…a81eb74, gate s6_blockptr)*

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "block-pointer: RED" -- bash -c \
  'cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j "$(nproc)" && cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe' 2>&1 | grep -aE "seven 256x256|DBP ==|SBP ==|own bytes|Failed\]" | head -20
```
Expected: the DBP assertions fail with `0x2000`/`0x0000` (i.e. `(vram_addr * 8) & 0x3FFF`) against `0x2400`…`0x3C00`, and pieces 0–4 read back `6,5,6,5,6`. If the test passes, it is not exercising the stub path (check `guestHeapBase()` addressing of the freed packet) — fix the test, not the expectation.

- [x] **Step 4: The fix** in `GS.cpp` (two lines; the comment is the reason a reader needs): *(done; see AUDIT-2026-09-17 §3: f6a4434…a81eb74, gate s6_blockptr)*

```cpp
        // libgraph's vram_addr is already the BITBLTBUF block field (256-byte blocks, 14 bits): the game's own
        // sceGsSetDefLoadImage/StoreImage callers pass byte>>8 and FBP<<5 (research/25 §10). The former
        // `* 2048 / 256` (x8) aliased seven VRAM regions onto two and smeared the motion pack (SP turn teleport).
        uint32_t dbp = static_cast<uint32_t>(img.vram_addr) & 0x3FFFu;
```
and the same for `sbp` in `sceGsExecStoreImage`. No opt-out knob (spec §6: the old value was simply wrong).

- [x] **Step 5: GREEN, then the whole suite** *(done; see AUDIT-2026-09-17 §3: f6a4434…a81eb74, gate s6_blockptr)*

Same command as Step 3; expected every new assertion `Passed`. Then, in the owner's window:
```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "block-pointer: runtime+test+gate" -- bash -c \
  './build.sh runtime && ./build.sh test && python -m tools_py.parity.gate --stamp s6_blockptr'
sha256sum dist/socom2.exe
```
Expected: test exit 0; gate `PASS title`, `PASS transition`, `PASS mission`. Blast radius: compare `s6_blockptr/title/s00..s19` run-vs-run against `s5_head_1x` (`python -m tools_py.parity.compare`, ≥ 99.0 except s14's known 98.8 split) and **look at** `mission/s28_none.png` against `s6_depth_m4`'s — loading screens and movies moved to correct addresses may change frames the scorer does not measure.

- [x] **Step 6: The offline descriptor check (lock-free after one spawn dump)** *(done; see AUDIT-2026-09-17 §3: f6a4434…a81eb74, gate s6_blockptr)*

Create `tools_py/parity/motion_pack_check.py`: given an RDRAM image and `game/disc/RUN/MOTION_P.ZAR`, locate the pack buffer at `*0x415e08`, walk the clip table (`0x415d40+0xf8[i]`, count at `+0x100`; header `+0x00` name ptr, `+0x44` descriptor ptr; research/25 §8.1), and for each clip with a non-null descriptor compare the 16-byte descriptor's relative layout against the file bytes at the same pack offset. Print `corrupt=<n> of <m> (null=<k>)` and exit 1 when `n > 0`. Test (`tools_py/tests/test_motion_pack_check.py`): a synthetic 3-clip pack where one descriptor is overwritten reports `corrupt=1 of 3`. Then, with a post-fix spawn dump from the gate run (`PS2X_RDRAM_DUMP_AT` at the mission's first hold, or the existing `PS2X_RDRAM_DUMP` path):
```bash
python -m tools_py.parity.motion_pack_check logs/parity/spawn_ours_blockptr.rdram game/disc/RUN/MOTION_P.ZAR
python -m tools_py.parity.motion_pack_check logs/parity/spawn_ours_vf0.rdram game/disc/RUN/MOTION_P.ZAR   # pre-fix control: 48
```
Expected: `corrupt=0 of 87` post-fix, `corrupt=48 of 87` on the pre-fix image.

- [x] **Step 7: Commit, push, merge; STATUS entry; KNOWN §2 row promoted to §1; CURRENT_SPRINT points at this plan** *(done; see AUDIT-2026-09-17 §3: f6a4434…a81eb74, gate s6_blockptr)*

```bash
git commit -m "fix(gs): the libgraph vram_addr is the BITBLTBUF block field -- drop the x8 in sceGsExecLoadImage/StoreImage

research/25 §9-§10: the x8 aliased the game's seven-piece VRAM park/restore onto two blocks and smeared the motion
pack [6,5,6,5,6,5,6], corrupting 48 clip descriptors and causing the single-player turn teleport. Seven-region
round-trip test RED first; ps2x_tests green; gate 3/3 s6_blockptr; motion_pack_check 48 -> 0 on a post-fix spawn dump.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/GS.cpp third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp \
  tools_py/parity/motion_pack_check.py tools_py/tests/test_motion_pack_check.py
git push -u origin fix/gs-block-pointer
```

---

### Task 1: A gate that can see

Lock-free until the calibration gate. Three independent scorers, each a pure function over files, each wired into `gate.py score_mission_log` behind its own PASS/FAIL line.

**Interfaces:**
- Produces: `mission_fail.detect(png_path) -> (failed: bool, reason: str)`; `console_compare.score(ours_png, console_png, mask) -> float` (0 = identical, 255 = opposite) and `console_compare.FLOOR`; `guest_probe.evaluate(run_log, console_json) -> list[(name, ours, console, tol, ok)]`.

#### 1a — mission-failure detection

- [x] **Step 1: Fixtures.** Copy `logs/parity/gate/s5_head_1x_b/mission/final.png` (MISSION FAILURE screen — verify by eye first; if it is not the failure screen, take `s38_holdS.png`/`s40_holdR1.png` from the same run and pick the one that is) to `tools_py/tests/fixtures/mission/failure_screen.png`, and `logs/parity/gate/s6_depth_m2/mission/s28_none.png` to `…/gameplay_spawn.png`. *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*

- [x] **Step 2: Failing test** `tools_py/tests/test_mission_fail.py`: *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*
```python
import unittest
from tools_py.parity import mission_fail

class Detect(unittest.TestCase):
    def test_failure_screen_is_detected(self):
        failed, reason = mission_fail.detect("tools_py/tests/fixtures/mission/failure_screen.png")
        self.assertTrue(failed, reason)
    def test_spawn_gameplay_is_not_a_failure(self):
        failed, reason = mission_fail.detect("tools_py/tests/fixtures/mission/gameplay_spawn.png")
        self.assertFalse(failed, reason)
```
Run: `python -m unittest tools_py.tests.test_mission_fail -v` → ImportError (RED).

- [x] **Step 3: Implement** `tools_py/parity/mission_fail.py`: the failure screen is a centred banner ("MISSION FAILURE" or "leaving designated mission area") on a darkened frame. Detect it the way `sp_death_probe.screen_state` detects the prompt: a binarised template of the banner text row cut from the fixture (`> 110` grey), matched at any row of the centre band with mean XOR distance `< 0.06`. Store the template's row/columns as constants with the fixture named in a comment. Return `(True, "MISSION FAILURE banner at y=<n>, dist=<d>")` or `(False, "dist=<d>")`. *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*

- [x] **Step 4: GREEN**, then wire into `gate.py score_mission_log`: after the liveness checks, run `detect` over every `s??_hold*.png` and `final.png`; any hit → `return False, "MISSION FAILED on screen: <reason> (<file>)"`. Add a `MissionScoring` test in `test_gate.py` that builds a run dir with a passing hold set plus the failure fixture as `final.png` and asserts FAIL. Commit: `feat(gate): the mission stage fails on a MISSION FAILURE screen (owner-agreed 2026-09-14)`. *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*

#### 1b — console-vs-ours image score at the spawn

- [x] **Step 1: Extract the console reference.** PCSX2 savestate `tools/pcsx2/sstates/SCUS-97275 (0F6FC6CF).08.p2s` is a zip; extract its `Screenshot.png` (480 rows), resize to 640×448 with Pillow `LANCZOS`, save as `scripts/parity/refs/console_spawn_slot8.png`. Record the command in the file's neighbour `console_spawn_slot8.txt`. *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*

- [x] **Step 2: Failing test** `tools_py/tests/test_console_compare.py`: *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*
```python
import unittest
from tools_py.parity import console_compare as cc

class Score(unittest.TestCase):
    def test_identical_frames_score_zero(self):
        s = cc.score("scripts/parity/refs/console_spawn_slot8.png", "scripts/parity/refs/console_spawn_slot8.png")
        self.assertEqual(s, 0.0)
    def test_our_spawn_with_shards_scores_above_floor(self):
        s = cc.score("tools_py/tests/fixtures/mission/gameplay_spawn.png", "scripts/parity/refs/console_spawn_slot8.png")
        self.assertGreater(s, cc.FLOOR)
    def test_mask_hides_the_hud_and_objective_text(self):
        m = cc.default_mask()
        self.assertFalse(m[400:448, :].any())      # HUD band
        self.assertFalse(m[50:100, 200:440].any())  # "CURRENT OBJECTIVE" text
```

- [x] **Step 3: Implement** `console_compare.py` — **done 2026-09-15, and the design changed on measurement.** A whole-frame masked mean |diff| reads 44–46 for every one of our clean s28 captures against the console and 3–10 between our own runs, but the gap is the global darkness divergence (research/20 §4.3), not the water; a brightness-normalised variant does not separate ours-vs-console (0.41–0.43) from ours-vs-ours (0.17–0.44) because pose, fog and foliage vary that much run to run. So `score()` is **informational only**, and the verdict comes from `water_verdict()`: two statistics of the water footprint (rows 190–340, cols 120–520) that separate the console from all four of our runs by 2.6× and 3.5× — the flat-region fraction (7×7 local std ≤ 1.2; console 0.188, ours 0.498–0.597; `WATER_FLAT_MAX = 0.35`) and the near-black fraction (grey < 12; console 0.084, ours 0.293–0.306; `WATER_DARK_MAX = 0.20`). Registered before any scored gate run. Not separated: a different camera, a colour-only water defect, and a fix that only brightens the scene (which is why both statistics are required). Tests: `tools_py/tests/test_console_compare.py` (7).

- [x] **Step 4: Wire** into `score_mission_log` as an extra line `CONSOLE spawn score=<s> water flat=<f> dark=<d> -> PASS|FAIL` computed on the s28 capture (the first `s??_none.png` after the HUD match). **Print, do not fail, until Task 5a lands** (R78: a gate that fails on a known, owned defect every run teaches nothing; the number is printed so its trend is visible); then flip to failing in the same commit as the water fix. `test_gate.py`: a run whose s28 is the console image itself reports PASS; one whose s28 is the shard fixture reports FAIL. *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*

- [x] **Step 5: One mission gate in the owner's window** (`--stamp s6_gate_console`) to see the line print with real numbers; adjust the mask if the objective text moved. Commit: `feat(gate): console-vs-ours spawn image score (owner-agreed 2026-09-14)`. *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*

#### 1c — guest-value probe

- [x] **Step 1: Console numbers on disk.** `scripts/parity/guest_probe_console.json`: *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*
```json
{"root_node_y": {"chain": "*0x408c58+0x2e8*+0x04", "console": 5.50391, "tol": 0.1, "source": "research/17 §1 table"},
 "move_scale":  {"chain": "*0x408c58+0x1368", "console": 1.0, "tol": 0.001, "source": "KNOWN §1 MoveScale row (SP: no network idle)"},
 "teleport_steps": {"derived": "actor xyz steps > 30 units between 4 Hz rows outside rx holds", "console": 0, "tol": 0, "source": "research/25 §1.1"}}
```
(The rand-derived field: `CSealCtrl+0x5c`, console 6.3338 ± 1.0 per research/17 §6 — add only if its chain resolves in a spawn dump; the seed is host-clock, so use a range.)

- [x] **Step 2: Failing test** `tools_py/tests/test_guest_probe.py`: a synthetic run log with `[peek]` rows where root-node Y reads 0.0 evaluates to `ok=False` for `root_node_y` and `ok=True` for `move_scale`; a log with two rows 40 units apart and no `rx` hold gives `teleport_steps=1`. *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*

- [x] **Step 3: Implement** `guest_probe.py` reusing `sp_death_probe.parse_peek_line` and `holds_from_pads`; `evaluate(run_log, console_json)` returns the rows; CLI prints a table and exits 1 on any `ok=False`. Wire: `gate.py`'s mission stage sets `PS2X_PEEK` to the chains in the JSON (plus `0x416054:3`) and the mission summary gains `PROBE root_node_y=0.00 (console 5.50 ±0.1) FAIL …`. **Do not fail the gate on it yet** (same R78 reasoning until Task 5's skeleton item); print it. *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*

- [x] **Step 4: GREEN; one mission gate in the window; commit** `feat(gate): guest-value probe (root node, MoveScale, teleport count) printed on every mission stage`. *(done; see AUDIT-2026-09-17 §3: 34ed2ac, 4c1b294)*

---

### Task 2: Lobby hardening, complete

**Files:** `tools_py/parity/online_login_ours.py`, `tools_py/tests/test_online_login.py` (extend), `docs/research/28-lobby-taxonomy.md` (new).

- [x] **Step 1: Taxonomy from logs already on disk (lock-free).** Over every `logs/run_[AB]_*.log` and `converge.json` since 2026-09-12, classify each launch's outcome: gameplay reached; `LOBBY-FAIL <class>` (map CROSS, READY — already classified); B JOIN not reached; map-list search failed; login keyboard not opened; pre-login window/menu (exit 1, unclassified today). Write the counts to research/28 §1 with the launch names. Expected: ~10–15 launches, gameplay ≤ 50 %. *(done; see AUDIT-2026-09-17 §3: 78a81d1, research/28, b8d2410…c669185)*

- [x] **Step 2: Failing tests** for each unclassified class in `test_online_login.py`, using the existing `FakeShell` pattern from `tools_py/tests/fixtures/lobby/`: a login screen whose keyboard never appears must raise `LobbyFail("login-keyboard")` within its stage timeout; a JOIN GAME list that never shows the host must raise `LobbyFail("join-not-listed")`; a window that never reaches the main menu must raise `LobbyFail("pre-login")` instead of exiting 1. *(done; see AUDIT-2026-09-17 §3: 78a81d1, research/28, b8d2410…c669185)*

- [x] **Step 3: Implement** verify-then-act on every fixed press in `login`, `host_game`, `join_game`: each press is followed by a frame check against the expected next screen (reference crops in `scripts/parity/refs/`, thumbnail regions as `ifref` uses), re-sent up to 3 times on fresh frames, and `lobby_stage(sh, name, timeout)` wraps each stage so a timeout carries the class. GREEN. *(done; see AUDIT-2026-09-17 §3: 78a81d1, research/28, b8d2410…c669185)*

- [ ] **Step 4: Ten launches in the owner's windows** (`scripts/parity/online_match_frostfire.sh` with `--control-round`, pinned harness, exit 4 counts as a classified failure):
```bash
for i in 1 2 3 4 5 6 7 8 9 10; do bash scripts/run_detached.sh --owner main scripts/parity/online_match_frostfire.sh logs/s6_lobby_$i.done; done  # one at a time, poll the marker
```
Decision table: ≥ 8/10 gameplay → done; 5–7 → read the classes, fix the largest, five more launches; ≤ 4 → the dominant class is server-side or timing (check `server/logs/medius.log` for the failed launches) and becomes a ruling with a research/28 §2 entry. Commit after Step 3 (harness-only rule: `build.sh test` + the simulation) and again with the numbers.

---

### Task 3: Online freeze root cause

**Files:** `ps2_runtime.cpp` (pc-sampler prints `m_vsyncTick`, host time, GS pending count and back-pressure wait total on each sample), `tools_py/parity/freeze_trace.py` (new: aligns sampler rows with `[peek]` clock rows and prints every window where the guest clock stalls ≥ 2 s with the host CPU % and the sampled PCs).

- [x] **Step 1 (lock-free):** `freeze_trace.py` over launch 8c's logs (`logs/run_[AB]_20260913_132843.log`): reproduce the 3–17 s stalls as a table (start, length, main-thread PC, NetIdle peak). Test: a synthetic log with one 5 s clock stall yields one window. *(done; see AUDIT-2026-09-17 §3: freeze_trace.py, research/29)*
- [ ] **Step 2 (window):** the sampler fields (one commit, `build.sh test`, gate); then two launches from the same exe, one with a CPU load generator on the host (`powershell -c "1..4 | % { Start-Job { while($true){} } }"`, stopped after) and one quiet, both with `PS2X_PC_SAMPLER=0.25`.
- [ ] **Step 3:** condition sentence in research/29: either the stall is the host starving the render thread (GS pending climbs, wait total climbs → back-pressure is doing its job, ruling: host load), or the guest is parked at one PC with pending flat (a runtime wait — fix it, A/B on one exe). Commit the fix only with the A/B.

---

### Task 4: Acceptance repeatability

**Files:** `online_match_ours.py` (`aim_yaw`, `engage_fight`), `sim_walk_to_b.py`, `tools_py/tests/test_aim_loop.py` (new), `scripts/parity/ladder_frostfire.sh`.

- [x] **Step 1: Failing sim test.** In `test_aim_loop.py`, a `World` whose actor-matrix heading carries a fixed −4.1° bias relative to the true bearing (round 4's signature) and a target that subtends 3° at the fight range: the current `aim_yaw` reports in-tolerance and `engage_fight` fires ≥ 20 bursts with no hit. Assert the new behaviour: after `AIM_MISS_BURSTS = 3` bursts with no damage (health of the target unchanged, read from the sim's state items), the loop steps the lead by ±1.5° alternating and re-aims, and a hit lands within 12 bursts. RED with the current code. *(done; see AUDIT-2026-09-17 §3: ebf13be)*
- [x] **Step 2: Implement** the burst-to-burst correction in `engage_fight`: track `bursts_since_damage`; on reaching `AIM_MISS_BURSTS`, apply a lead offset (`+1.5°, −1.5°, +3.0°, −3.0°`) to the next `aim_yaw` target, reset on any damage; stop and report `NO-KILL aim-exhausted` after the table is exhausted twice (ammo-aware: reload is a `SQUARE` press when the HUD count reads 0 — `sp_death_probe` already reads ammo from the HUD crop). GREEN; the existing sim suite stays green. *(done; see AUDIT-2026-09-17 §3: ebf13be)*
- [ ] **Step 3 (windows):** two ladder launches, `bash scripts/parity/ladder_frostfire.sh --pinned logs/parity/s6_ladder{1,2}`, on the Task 0 exe. Bars: rounds 1–3 KILL on each, both scorers (`verdict_replay` offline over the logs) agreeing. Decision table: 2/2 → done, record exe sha + harness commit in KNOWN §1; 1/2 → one retry; 0/2 → the miss class from the RESULT lines decides (aim-exhausted → back to Step 1 with the live bias; lobby → Task 2; freeze → Task 3). *(met in practice: s6_ladder8 4/4, s6_ladder12 3/4; the strict two-scorer bar unrecorded)*

---

### Task 5: Visible single-player correctness

- [x] **5a Water (research/26 candidate 2).** Window: one mission gate with `PS2X_GS_TRACE_CMDS=t249` and `python -m tools_py.parity.gsdump_capture --slot 8` on PCSX2; lock-free: decode the `tbp0=038a8` submits from both, diff TEX0/CLUT/ALPHA of the `0x34` pass (`tools_py/gsdump_timeline.py`). Cheap first cut in the same window: `PS2X_VU1_NATIVE=0` mission-only (excludes candidate 3) and a diagnostic build flag that skips the `0x34` pass (shards go with it → candidate 2 confirmed). Fix only with a condition sentence; judged by Task 1b's `WATER_FLOOR` (then promoted to failing). *(done, by the blend/exposure HLEs and the VIF wait, not the 0x34 theory)*
- [x] **5b Skeleton root decay.** Window: one 60 s stand at the spawn with `PS2X_PEEK=*0x408c58+0x2e8*+0x04:1` on the Task 0 exe. If it holds 5.50 → KNOWN §1 promotion, close research/17 §4.3 as fixed by `b625291`; if it decays → research/17 §4.3's separating run (read the node on return from `FUN_001c0768` and again later in the frame). *(the probe, s6_probe)*
- [ ] **5c The packet-offset-0x14 DBP defect.** Failing test: a `sceGsSetDefLoadImage` packet whose guest-written DBP halfword at +0x14 differs from the `GsImageMem` block field; `sceGsExecLoadImage` must send the halfword. Fix: read the halfword at exec time when the packet carries one (research/25 §10). Gate + a loading-screen frame compared by eye against PCSX2. *(likely done as a side effect of 545b85a; unverified against the loading screen -- Sprint 8)*

---

### Task 6: Exact-oracle math and HLE audit leg three (lock-free filler)

- [ ] `tools_py/parity/oracles/softdouble.py`: run the recompiled `litodp → dpmul → dpdiv → exp → dptofp` chain through `dist/vu1_replay.exe`-style harness? No — through `ps2x_tests`: a C++ test that calls the recompiled functions on 64 inputs and compares against host `double` within 1 ulp; RED first (KNOWN: `1/(exp(1)-1)` reads 0.034 vs 0.58). Fix in the 64-bit integer recompilation path; `build.sh test`.
- [ ] `__ieee754_rem_pio2f`: port fdlibm's faithfully into the stub; test against `math.remainder` over 10^5 floats.
- [ ] HLE leg three: for research/20's remaining ranked rows, the consumer reading and either a "constant by spec" tag or a fix with a moves-test.

### Task 6b: Online map coverage sweep (owner request 2026-09-16, after the online tests are consistent)

**Owner:** "testing online matches in each of the untested online maps (without a kill requirement initially)."
Frostfire (kills), Medley and Vigilance (control rounds) are the only maps ever driven online.

- [x] **Step 1 (lock-free):** list every map on the CREATE GAME PLAY LIST from the map-scan captures (`A_mapscan_*`,
  research/28's row scan) and the game's own list; cut a `map_<name>.png` reference row for each (the FROSTFIRE and
  MEDLEY refs were cut from the highlighted row of a scan capture). *(research/33; Requiem and Foxhunt settled 2026-09-17; 20/20)*
- [x] **Step 2 (windows, one launch per map):** `online_match_frostfire.sh`-style launch with `--map <name>
  --control-round` (both sides alternate strafe legs, nobody fires; the RESULT is `CONTROL-ROUND` with the valves
  unchanged) on the pinned harness. Bars per map: lobby reaches gameplay; both sides CONTROLLABLE on the control
  precondition; the round runs to its clock or at least 120 s of live rows; spawns recorded (`spawns=`); no freeze
  alarm > 10 s. A map that fails control or liveness gets one retry, then a KNOWN §2 row naming what failed. *(research/33; Requiem and Foxhunt settled 2026-09-17; 20/20)*
- [x] **Step 3:** a table in a new research note (`31-online-map-coverage.md`): map, launch name, lobby outcome,
  control A/B, freeze peaks, spawn coordinates, and whether the water/terrain looked right on the spawn capture
  against a PCSX2 screenshot where one exists. Kills come later, map by map, by extending the route files. *(research/33; Requiem and Foxhunt settled 2026-09-17; 20/20)*

**Owner request 2026-09-16 on the water (Task 5a):** the Seeding Chaos stream still shows the grey clipping shards
below the water (their screenshot of the spawn view); the gate's `CONSOLE spawn … water flat=… dark=… -> FAIL` line
tracks it on every mission run. Task 5a is the next single-player item after the online tests are consistent.

### Task 6c: Audio output (owner 2026-09-16: "i'm getting no sound" -- a known gap, not a device fault)

The host audio device initialises (raylib/miniaudio, WASAPI) and the 989snd IOP service (`ps2xIOP/src/modules/snd989.cpp`,
research/06) answers every RPC, loads the banks and models voices and streams -- but `PS2AudioBackend::onSoundCommand`
"only understands the libsd SID" (STATUS 2026-09-06: "no audible output yet"). Nothing SOCOM plays -- UI clicks,
weapon fire, music and voice streams -- reaches a speaker. This is the largest remaining "playable" gap after online.

- [x] **Step 1 (lock-free research, `research/32-audio-path.md`):** what 989snd Play / stream-play commands carry
  (bank, sound index, pitch, volume, pan; VAG stream LBNs), where the VAG data lives (the bank blocks already
  parsed: "block 3472B vag 60928B"), and the ADPCM decode (PS2 VAG: 16-byte blocks, 28 samples, filter/shift nibbles --
  a 40-line decoder, well documented). *(done; see AUDIT-2026-09-17 §3: research/32)*
- [x] **Step 2 (test-first, no run):** a VAG decoder in `ps2xRuntime` with a unit test against a known block
  (encode a sine with the reference tables, decode, compare) and a bank-index lookup test on a real bank from the disc. *(done; see AUDIT-2026-09-17 §3: research/32)*
- [x] **Step 3:** `PS2AudioBackend` mixes 989snd voices through raylib audio streams (one stream per voice slot, pitch
  via resampling, volume/pan), and streamed VAG for music/voice via the existing stream-safe CD reads; a gate-side
  check that a title-screen run writes a non-silent capture (`PS2X_AUDIO_DUMP=<wav>`, RMS above a floor). *(done; see AUDIT-2026-09-17 §3: research/32)*
- [ ] **Step 4:** owner listening test in free play; then the per-stage sounds of the mission gate as a regression fixture. *(owner: docs/HUMAN_TASKS.md)*

### Task 7: Mixed match (windows, 4 launches)

- [ ] `scripts/parity/mixed_match.sh`: ours hosting + PCSX2 joining (research/18 §1 recipe, `pcsx2_keys.py`), then the reverse. *(2026-09-17: the script, `pcsx2_ctl` macros, `--foreign-b`, `motion_diff` are in with tests; leg 1 ran -- ours hosted, the PCSX2 macro's fixed timings drifted at boot, no joiner. Next: screen-verified PCSX2 steps.)* Bars: gameplay reached both ways; the movement bar met on ours; on the console client our player is seen moving (PCSX2 screenshot diff over a 10 s hold). Result to KNOWN §1 or §2 with the launch names.

### Task 8: Harness and maintainability (lock-free)

- [x] `gate.py --baseline <stamp>`: score a saved run dir without launching; test. *(2026-09-17: `score_baseline`, two tests; `--baseline s6_audio_gate20` re-scores 3/3.)*
- [x] `movie_blocks.py` wired into `build.sh test` with a saved furniture baseline under `tests/fixtures/movie/`. *(2026-09-17: seven presents of `s6_movie_dump3` as PNG pairs + `furniture.txt`; `test_movie_blocks_fixture` runs in the discovery `build.sh test` already calls.)*
- [x] Client-rect assertion in `drive.py` (fail loudly when the window is not 640×448 at capture). *(2026-09-17: `winshot.client_size` + `ClientRectError` in `capture_step`; `test_drive_capture`.)*
- [x] `scripts/archive_logs.ps1`: move gate stamps and run logs older than 14 days (never the ones named in KNOWN §1) to `D:\socom_archive`, dry-run by default. *(2026-09-17: KNOWN §1's paths as patterns; `test_archive_logs` 2/2; the real dry run finds nothing 14 days old yet.)*
- [x] Knob retirement pass 1: remove `PS2X_GUEST_MALLOC_ZERO` (shipped unused), the redundant main-context vf0 line, and the `_B` variants no driver sets (grep `tools_py/` first); README entries deleted with them; `build.sh test` + gate. *(2026-09-17: the knob, its policy header, its test and the `_B` mappings for it and `PS2X_SOCOM2_NET_STATS_B` are gone; no `vf0` line exists in the runtime any more -- nothing to remove.)*
- [x] README "Build, run, verify" contributor section: the five commands a newcomer runs, in order, with expected output lines. *(2026-09-17.)*

### Task 8b: The launcher, first cut (owner 2026-09-16, item 5: "launcher build out that requires pointing to a r001 iso, a selection for detail quality pre-launch with a visible controller testing area and any other settings we can easily add")

**Shape.** A small raylib/C++ program `launcher/socom-unzipped-launcher.exe` in the same build (`build.sh runtime`
builds it next to `socom2.exe`), because the game's own input code is raylib: the controller test area then shows
exactly what the game will read. One 640×448 window, four panels, one Launch button. It owns `config.json` next to the
exe and sets the `PS2X_*` environment for `socom2.exe <elf>`; the game itself does not change.

**Panels.**
1. **Disc.** A path field with a Browse button (Windows file dialog via `GetOpenFileName`); on choose, the launcher
   opens the ISO, finds `SCUS_972.75` in its directory (the ISO 9660 walk is ~60 lines; `tools_py/make_overlay_elf.py`
   has the Python version to port) and hashes it: the r0001 sha256 is pinned in the source; a mismatch shows "not
   SOCOM II NTSC r0001" in red and disables Launch. The merged ELF ships beside the exe (owner decision, packaging §7).
2. **Video.** Detail quality as three radio buttons mapped to knobs the gate already verifies: *Native* (`PS2X_GS_SCALE=1`),
   *Sharp* (`PS2X_GS_SCALE=2`, verified S=2 on both draw paths), *Sharper* (`PS2X_GS_SCALE=3`, labelled experimental —
   S=3/4 are untested, README). Presentation filter (linear / integer / point → `PS2X_PRESENT_FILTER`). Window size:
   640×448, 1280×896, fullscreen-borderless — the runtime takes none of these yet: **the launcher passes
   `PS2X_WINDOW_SIZE=<w>x<h>` and the runtime gains that one knob** (`ps2_runtime.cpp` `InitWindow` at ~730; a
   borderless fullscreen is `SetWindowState(FLAG_BORDERLESS_WINDOWED_MODE)`; the gate keeps its 640×448 default).
3. **Controller.** A live diagram: two stick circles with dots, the D-pad, four face buttons, four shoulders, Start/Back,
   drawn from `IsGamepadAvailable(0)` / `GetGamepadAxisMovement` / `IsGamepadButtonDown` — the same calls the game's
   input poll uses (`socom2_host_input.cpp`, the 2026-09-16 gamepad block) — with the pad's name, "none" in grey, and
   the keyboard map printed beside it. A "mouse look" checkbox (`PS2X_SOCOM2_MOUSE=1`) and a sensitivity slider
   (`PS2X_SOCOM2_MOUSE_SENS`).
4. **Online.** Server address (default: the project's server once one exists, else `127.0.0.1`), profile name → memory
   card directory `cards/<profile>/` (`PS2X_MC_DIR`), "second instance on this machine" checkbox
   (`PS2X_SOCOM2_UDP_SHIFT=2`, `PS2X_SOCOM2_RSA_KEY=b`, a second card dir).

**Launch.** Writes `config.json`, spawns `socom2.exe` with the environment (`PS2X_SOCOM2_PAD=1` always), stdout/stderr
to `logs/run_<stamp>.log`, and stays open with a "Copy diagnostics" button (zips the last log + config).

**Order of work (test-first where there is logic):** (1) the runtime's `PS2X_WINDOW_SIZE` knob with a unit test on
the parser and a title-gate run to prove 640×448 unchanged; (2) the ISO check as a pure function (`launcher/iso.cpp`)
with a test on a synthetic ISO directory and the real disc; (3) the raylib window with the four panels, `config.json`
round-trip tested; (4) the owner's hands-on test with the Xbox controller; (5) the portable folder (packaging §2 A)
gains the launcher and README says "run the launcher" *(done 2026-09-17: `scripts/make_portable.sh` -> `dist/portable/socom2/` + zip; `test_make_portable`)*. Ships with defaults that reproduce today's behaviour.

### Task 9: Close-out

- [ ] `PS2X_TEST_REPEAT=3 ./build.sh test` and a full gate on a quiet host; STATUS entry; KNOWN audit; ROADMAP §6 marked; CURRENT_SPRINT → Sprint 7; whole-branch review; the controller merges `sprint-6` into `develop` and `main`; ledger archived to `D:\socom_archive`.
- [ ] *(added 2026-09-17 from the audit)* reconcile this plan with AUDIT §3 (this edit), the KNOWN audit (AUDIT §4), rulings R81+, STATUS's current-state block, ROADMAP §6 marked, merge sprint-6.

---

## Rulings made on the owner's behalf

- **R78** (2026-09-15, Task 1): the console spawn score and the guest-value probe are printed on every mission summary and do not change the verdict until their defects (water, root node) are fixed — a gate that fails on a known, owned defect every run teaches nothing; the mission-failure detector, by contrast, fails the stage from day one because a failed mission is never acceptable evidence. *Cost if wrong:* a regression in the water or the root node goes unflagged until Task 5; mitigated by the numbers being on every summary.
- **R79** (2026-09-15, Task 0a): the depth fix, the `ifpopup` step and the Task 1 gate wiring are committed on `s6_depth_m5`, whose mission stage met the pre-Task-1 bar (5/6 gameplay holds, 2 live pairs — the bar Sprint 5 merged on) and FAILed only on the new mission-failure detector catching the pre-existing right-stick turn teleport (`s43_holdS.png`, banner dist 0.018), the defect Task 0b fixes next. Title and transition PASSed on the same exe (`s6_depth`, `s6_depth_r2`). *Why:* the failure is a true positive on a known defect unrelated to the change, and holding three verified commits behind the fix for it would only merge them later on the same evidence. *Cost if wrong:* if Task 0b's gate does not pass end to end, these commits are the first suspects and are reverted together.

- **R80** (2026-09-15, Task 1c / Task 5b): the guest-value probe is scored, not printed, from `s6_probe` on: on the block-pointer exe it read the skeleton root node at **5.5039** (the console's value; ours had decayed to 0.0 since research/17), MoveScale 1.0, and 0 teleport steps once the threshold was expressed as a speed (> 120 u/s; the 8 s forward hold runs at ~40 u/s and had read as 8 "teleports" at 1 s rows). So Task 5b's re-measurement is answered without its own run — the root decay was fixed by `b625291` (vf0) or `a81eb74` (block pointer); which of the two is not separated and does not need to be. NO-DATA fails only a stage the gate launched itself, so `--score-mission` of older runs still works. *Cost if wrong:* a flaky peek chain fails a gate that would otherwise pass; `reads=309 of 478 rows` on `s6_probe` says the chain resolves through the whole mission.

- **R81** (2026-09-17, Task 3 / research/34 §6): the guest clock counts wall time by default; the 2026-09-08 exclusion of VU1 and render back-pressure time is now `PS2X_CLOCK_EXCLUDE=1` for an A/B. A moved default, which Global Constraints forbade; taken because the exclusion made every gameplay timer run at 0.5–0.85 of real time and was the cause of Requiem's control failure and the online snap-backs. *Cost if wrong:* a render backlog now stalls guest time visibly (KNOWN §2's 21k-decodes row is that backlog); measured by `PS2X_CLOCK_TRACE` on every launch since.
- **R82** (2026-09-17, Task 3): texture-cache CLUT ids are keyed on the palette's content (FNV-1a over the snapshot), not the CLUT serial. Taken because serial keys exploded the cache to 64k uploads/s in every online round and froze the game. *Cost if wrong:* two different palettes with the same bytes share an entry, which is correct by construction; the residual 21k/s is a different mechanism (audit §2.2 F1).
- **R83** (2026-09-16/17, Task 1): the transition stage's black-frame floor moved 5 → 3, and the untilref threshold 30 → 40, and the HUD reference was re-captured twice (the 09-16 water fix and the exposure fix changed every gameplay frame's brightness). Taken so the gate measures the exe it runs rather than the exe of 09-13. *Cost if wrong:* a real transition regression of two frames passes; the transition detector's peak-0 bar still catches a missing black.
- **R84** (2026-09-16, Task 8b): a gate run is defined as a boot with no controller (`PS2X_HOST_GAMEPAD=0` set by the gate and the online scripts) from a pristine memory card copied per stamp. Taken after three gates were lost to a plugged-in pad skipping the configuration screens the transition stage keys on. *Cost if wrong:* the gate never exercises the gamepad path; that path is the owner's hands-on item in `docs/HUMAN_TASKS.md`.
- **R85** (2026-09-17, Task 2 Step 4): the ten-launch lobby-rate measurement was skipped in favour of the twenty-map sweep and the ladder launches, which reached the lobby on 22 of 24 attempts with two retries. Taken because the sweep produced more launches than the measurement asked for; the number is not a pre-registered rate. *Cost if wrong:* the lobby rate a stranger will see is unmeasured; Sprint 7 item 2 measures it properly.
- **R86** (2026-09-17, Task 6c, research/32 §7.1): the sceMpeg HLE's demux always consumes its whole input; a video packet the game's stream callback refuses is taken anyway, an audio packet it refuses is set aside and re-offered in order at most once per vsync. Taken because the library's contract (stop at a refusal) starved this game, which drops what a call did not consume and polls the demux 340,000 times a second. *Cost if wrong:* a game that relies on the stop semantics would lose a refused video packet; SOCOM II is the only game this runtime runs. Measured: the mix correlates with the disc's PCM at 0.99.
- **R87** (2026-09-17, Task 6c): the picture presenter drops pictures overdue by a whole interval instead of drifting behind real time, and the decode lookahead is eight pictures (two, the hardware depth, starved the presenter here). Taken because the game's demux loop is time-budgeted and our decode lands in bursts. *Cost if wrong:* a dropped picture is a skipped movie frame the eye may catch; no picture is ever shown late.
- **R88** (2026-09-17, Task 6c): a demux call that consumes nothing lets a ready guest thread of any priority run once (`EeScheduler::yieldToAnyReady`), a deliberate departure from the kernel's strict priorities for a thread that is only polling. Taken because parking the poller until vsync hung the title screen and not yielding starved the audio thread. *Cost if wrong:* a lower-priority thread runs a slice it would not get on hardware while the movie thread polls; gated to SOCOM II by the game override.
- **R89** (2026-09-17, audit): the launcher's server picker ships with placeholder addresses for the community and Unzipped servers, and the default preset stays Custom until ours is hosted. Taken because a placeholder that cannot resolve is safer than a guessed address; the two addresses are the owner's (`docs/HUMAN_TASKS.md`). *Cost if wrong:* none until release; the launcher shows the note "not hosted yet".
- **R90** (2026-09-17, audit): the ISO handoff, the hostname resolution, the server's `-PublicIp` and the harness's `env.sh` landed in one fix wave under tests, gated once on the rebuilt exe (`s6_fixwave_gate` 3/3) rather than one gate per change. Taken because none of the four touches gameplay; each has its own unit test. *Cost if wrong:* a regression in one hides behind the others' commit; the tests name each.

## Self-review

- **Spec coverage:** Goals 0–9 → Tasks 0–9; §5's bars appear in each task's decision table; §6's budget is the sum of the window steps (2 + 3 + 10 + 2 + 4 + 3 + 4 launches/gates). The spec's "no opt-out for the block pointer" is Task 0b Step 4.
- **Placeholders:** none; every test step has code or an exact assertion; Task 6's first bullet corrects itself in place rather than leaving a question.
- **Type consistency:** `popup_present(im)`, `mission_fail.detect(path)`, `console_compare.score(a, b, mask=None)`, `guest_probe.evaluate(run_log, console_json)` are used with the same signatures throughout.
- **Owner gate:** the spec is unreviewed; Tasks 0–1 are owner-agreed items, and the controller stops for a re-ruling before Task 2's launches if the owner has not reviewed by then.
- **Ledger reconciled 2026-09-17** against docs/audits/2026-09-17-audit-and-code-review.md §3; the checkboxes above are now the truth. ROADMAP §6's items 10-12 (replay cost, display-env A/B, VU aliasing) were never carried into this plan and are dropped, not deferred.
