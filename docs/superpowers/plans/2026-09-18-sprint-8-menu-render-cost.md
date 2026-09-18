# Sprint 8 Goal 2 — The Menus' Render Cost, at the Root: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the login and lobby screens cost what a 2D menu should cost, by fixing the thing that makes them expensive rather than by hiding it — the 7-11k one-kilobyte 16x16 tile uploads a second that carry 80-133 ms/s of render time (four to six times gameplay's 20-28 ms/s) and drop the login screen to 12-30 fps with `bp_pending=4 bp_waiters=1` in four of ten driven launches. The bar is the login screen at 60 fps **under a four-core spinning host load**, `bp_pending` under 2 in every sampler row across the login screen, and `upload=` below 30 ms/s on the menus, with the three-stage gate still 3/3.

**Architecture:** Measure first, then batch, then prove. The cost is measured **per call, split by term**, before one line of the upload path changes (Task 1) — because the plan's own stop rule turns on which term dominates, and a fix aimed at the wrong term is worse than no fix. The change itself (Task 2) is one idea: the backend already records an *exact rectangle* per 16x16 tile and replays each one as its own `glTexSubImage2D`; consecutive tiles that **tile a bounding rectangle exactly** become one staging buffer and one GL call. Every new piece of arithmetic — the size histogram, the per-term accumulator, the rectangle coalescer — lives in a **header-only, GL-free** header next to `gs_gl_target_extent.h`, so `ps2x_tests` checks it on Windows, in CI and in the VM with no GL context; only the wiring lives in `gs_gl_backend.cpp`. The change is platform-neutral by construction: plain C++ in the shared GL backend, under no `#ifdef`, and the Linux port's rules (Goal 1) keep applying — Windows stays as measured, and a Linux build must not need a single extra guard because of this goal.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh` on the host; system clang + Ninja in the VM and on `ubuntu-24.04`), CMake ≥ 3.20, OpenGL 3.3 through raylib's context, MiniTest (`ps2x_tests`, no filter, runs every case), Python 3 `unittest` (**not** pytest, see Global Constraints), the online harness (`tools_py/parity/online_match_ours.py`, `tools_py/parity/gate.py`, `tools_py/parity/freeze_trace.py`), `scripts/run_detached.sh` + `scripts/loop_lock.sh` for every host launch.

**Spec:** `docs/superpowers/specs/2026-09-18-sprint-8-linux-and-finish-design.md` — **Goal 2 only** (§2 "Goal 2 — the menus' render cost at the root", and §3's stop rule: *"Goal 2 stops if batching does not move the ms/s number, filing the per-call breakdown instead"*). **Required reading for every dispatch:** this plan's Handoff notes and Global Constraints; `docs/KNOWN.md` §1 rows "The login screen runs at 12-30 fps under GL back-pressure in 4 of 10 launches" (:88) and "The 21k texture decodes a second: the page-marking hypothesis is falsified by its own trace, and the figure is stale" (:89), plus the uploads row at :69; `docs/research/34-online-round-freeze-clut-serials.md` §§3-4 (the 21k figure's origin and the stats-line table it came from); `docs/CURRENT_SPRINT.md`'s Sprint 8 block item 1 (:141-145); for the code `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` §§`executeCommands` (:1313-1630), `executeTransfer` (:1804-1825), `executeUpload` (:1827-1877), `refreshRenderTargetsFromShadow` (:1879-1945) and `refreshDirtyRows` (:1947-2080), and `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h:77-88` (`CmdType`) and `:156-160` (`DirtyRect`).

## Handoff notes for the executing model (read once)

- **Process.** superpowers:subagent-driven-development; a fresh implementer per task; a task review after each that re-derives at least one number independently; the controller merges. Ledger at `.superpowers/sdd/2026-09-18-sprint-8-menu-render-cost/progress.md`. Decisions on the owner's behalf are `Ruling: … — why — cost if wrong`, numbered from **R107** (Goal 1's plan ended at R106).
- **Read this before Task 1, because the brief this plan was written from is wrong about it.** The brief (and KNOWN §1:89's experiment line) describe the `[gs-gl stats]` `upload=<ms>/<count>` column as the cost of "the 1 KB tile path" including "the GL call itself (glTexSubImage2D or the PBO path)". The tree says otherwise, and the whole of Task 1 depends on knowing it:
  - `executeCommands` times each command into a bucket indexed by `static_cast<int>(cmd.type) & 7` (`gs_gl_backend.cpp:1577-1581`); `CmdType::Upload` is index 2, which is the `upload=` column at `:1596-1602`.
  - The only thing that runs inside that bucket is `executeUpload` (`:1501-1502` → `:1827-1877`): `m_shadow->UploadImage` (the CPU swizzle into shadow VRAM), `markShadowPages`, and `refreshRenderTargetsFromShadow`, which **only pushes a rectangle onto `rt.dirtyRects`** (`:1909-1915`).
  - **No `glTexSubImage2D` is reached from `executeUpload` at all.** The tree has exactly two `glTexSubImage2D` call sites (`:1998` and `:2016`), both inside the `uploadScaled` lambda in `refreshDirtyRows` (`:1947-2080`), which runs later — from `executeClear` (`:2094`), from the submit path and from the present path. **Its milliseconds are therefore charged to `clear=`, `submit=` and `present=`, never to `upload=`.**
  - **There is no PBO path.** `grep -n "PIXEL_UNPACK\|glMapBuffer" gs_gl_backend.cpp` finds nothing; the file's one `glBufferData` (`:3579`) is the vertex stream.
  - The consequence for this goal: **80-133 ms/s is the CPU-side half alone** (shadow swizzle + page marking + rect marking), and the GL half is real but currently unlabelled. Task 1 measures both and says which is which; Task 2's batching removes per-rect work on *both* sides (one staging buffer and one GL call instead of N), so it is not invalidated by the correction — but a step that claims `upload=` already contains the GL call would measure the wrong thing.
- **`docs/KNOWN.md` has one writer: the controller.** Retractions happen on discovery, in the same hour. KNOWN §1:89's experiment sentence ("is it the 1 KB tile path's per-call overhead — 10 us a tile — rather than the byte count") is the hypothesis this goal tests; Task 1's numbers either confirm it or retract it, and either way the row is rewritten in Task 4.
- **Autonomy (owner 2026-09-17, standing).** Proceed autonomously; no waiting for a window the owner names. **One host launch at a time**, always through `scripts/run_detached.sh`, and **suites are held while a host launch runs**: no `./build.sh test`, no `python -m unittest`, no gate and no second launch while `logs/.quiet` exists (`bash scripts/check_quiet_gate.sh` answers).
- **Subagents (owner 2026-09-17).** Bounded mechanical work goes to Opus subagents with an exact brief and a verification command; judgment stays with the controller. A brief names: the files to touch, the exact edit, the command that proves it, and the expected output. A subagent never decides whether a bar is met, never writes `docs/KNOWN.md`, never commits, and never starts a launch. In this plan the natural subagent jobs are Task 1 Step 7's table of numbers out of a 60 s log and Task 3 Step 3's per-row `bp_pending` scan.
- **Commit conventions.** `git commit -m "…" -- <paths>` with an explicit pathspec; never `git add -A`; `server/config/simulated.db` stays unstaged (it is modified in the working tree right now and must stay that way); `ONBOARDING.md` stays untracked; `vm/` is gitignored and nothing under it is ever staged. Push after each commit. Trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Line numbers.** Every line number in this plan is the number at `529f95b` (the branch tip when it was written). Goal 1's tasks are still landing in the same checkout; before starting a task, `git diff -- <the task's files>` and reconcile, saying so in the ledger rather than writing a step twice. Goal 1 touches `gs_gl_backend.cpp` **not at all**, so a collision is unlikely.
- **Test binary.** `ps2x_tests` takes no filter and runs every case (554 on Windows at `529f95b`, well under a minute). Windows: `third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe`. Linux: `third_party/ps2recomp/build-linux/ps2xTest/ps2x_tests`.
- **The launch budget.** Spec §3 allows Goal 2 "about four" launches on Windows. This plan spends **four**: `s8_upload_trace` (Task 1, 60 s hold), `s8_menu_bar` (Task 3, 60 s hold under load), and two gate runs (`s8_g2_batch`, `s8_g2_bar`). Nothing else launches the game.

### The command set (use these verbatim)

```bash
# --- build and suite (Windows host) ---
export PATH="$PWD/tools/llvm-mingw/bin:$PWD/tools/cmake/bin:$PWD/tools/ninja:$PATH"
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 ; ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "<what>" -- ./build.sh test

# --- the runner, for a launch ---
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/build_runtime.marker
scripts/run_detached.sh --owner gate  --purpose launch logs/<name>.sh           logs/<name>.marker
cat logs/<name>.marker 2>/dev/null || echo running     # poll the marker, never the tool call
bash scripts/check_quiet_gate.sh                       # answers whether a suite may run

# --- the gate (3/3) ---
python -m tools_py.parity.gate --only title,transition,mission --stamp s8_g2_<what>

# --- reading a run ---
grep -n "\[gs-gl stats\] calls=" logs/run_A_<stamp>.log | tail -40
grep -n "\[gs-upload\]" logs/run_A_<stamp>.log | tail -40
python -m tools_py.parity.freeze_trace logs/run_A_<stamp>.log     # bp_pending / bp_waiters per sampler row
```

A host launch script is a file under `logs/`, in the shape of `logs/s7_audio_online.sh` (the online instrument set comes from `scripts/parity/env.sh`, which is **sourced, never executed**):

```bash
#!/usr/bin/env bash
export PATH="/usr/bin:/mingw64/bin:/c/Users/Utilisateur/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
. scripts/parity/env.sh
<the exports this run needs>
python -m tools_py.parity.online_match_ours --only A --hold <s> --out logs/parity/<name>
rc=$?
taskkill //F //IM socom2.exe >/dev/null 2>&1
echo "done $rc" > logs/<name>.done
exit $rc
```

## Global Constraints

- Branch `sprint-8`. Branch in the main checkout, never a worktree.
- **Every runtime change under a RED test first.** Each step that changes `gs_gl_backend.cpp` names the case in `ps2_gs_tests.cpp` that fails before it and passes after, and the exact failure text. A step that cannot state its RED says so in one sentence and names the launch or the readback that verifies it instead.
- **The arithmetic lives in headers, the wiring lives in the backend.** New logic goes into `runtime/gs/gs_gl_upload_trace.h` and `runtime/gs/gs_gl_upload_batch.h` — header-only, `#include <cstdint>`-grade dependencies, **no GL header, no raylib**, exactly as `runtime/gs/gs_gl_target_extent.h` is (its own closing note: *"Header-only and free of GL includes on purpose, so ps2xTest can check the arithmetic without a context"*). That is what lets the coalescer's cases run in CI and in the VM where there is no context at all.
- **The trace costs nothing when it is off.** `PS2X_GS_UPLOAD_TRACE` is read once into a `static const bool` at the top of the function that uses it, as `PS2X_GS_STATS` is (`gs_gl_backend.cpp:1315`); with it unset no clock is read, no counter is touched and no branch is taken per tile beyond that one bool.
- **The batching changes pixels or it is a bug.** `refreshDirtyRows`'s exact-rectangle path exists because a band re-read dragged stale shadow rows back over newer GPU pixels (`gs_gl_backend.cpp:1898-1904` and `:2042-2044`: the movie strip at rows ~396-415 on the typing screen, user report 2026-09-09). **A merged rectangle must therefore be covered exactly by the rectangles it replaces** — never a bounding box with a hole in it. This is R108, and Task 2 Step 1's cases are written to fail if it is violated.
- `./build.sh test` exit 0 on the Windows host before any commit touching `third_party/ps2recomp/`, `tools_py/` or `scripts/`. **The three-stage gate PASS (3/3) before any commit touching `third_party/ps2recomp/ps2xRuntime/src/`** — which is every code commit in this plan.
- **The Windows numbers stay as measured** unless a bar says they move. Goal 1's constraint reads "the Windows build and its gate byte-for-byte unaffected"; this goal *does* change `dist/socom2.exe`, deliberately and at the root, so the substitute check is the gate's 3/3 and the mission stage's score band, named in Task 2 Step 6 and Task 3 Step 5.
- **Platform-neutral.** No `#ifdef _WIN32` is added by this goal. If a change cannot be written without one, it stops and becomes a ruling.
- Explicit pathspecs on every commit, never `git add -A`. `server/config/simulated.db` is **never** staged. `vm/` is never staged.
- Commit trailer, every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- LF line endings in every new file. New shell scripts are `chmod +x` and committed with the mode bit.
- **Python tests are `unittest`, never pytest.** `tools_py/tests/test_test_hygiene.py` fails the suite on a `test_*.py` outside `tools_py/tests/`, on any `import pytest`, and on a module-level `def test_`.

---

## File map

| Path | Responsibility |
|---|---|
| `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_trace.h` (new), `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (:1313-1330 the stats statics, :1501-1502 the Upload dispatch, :1577-1602 the bucket and the stats line, :1827-1877 `executeUpload`, :1879-1945 `refreshRenderTargetsFromShadow`, :1947-2080 `refreshDirtyRows`, :1994-2019 `uploadScaled`, :722-745 `record`), `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp` (new cases), `logs/s8_upload_trace.sh` (new) | **Task 1**: `PS2X_GS_UPLOAD_TRACE=1` — the size histogram, the per-call microseconds (shadow swizzle / page+rect marking / record / CPU convert / the GL call), the distinct destination textures per second, and one driven login launch that reads them |
| `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_batch.h` (new), `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h` (:156-160 `DirtyRect`), `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (:1968-1970 the rect swap, :2028-2041 the exact-rectangle loop, :1994-2019 `uploadScaled`), `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp` (the coalescer cases and the GL call-count case) | **Task 2**: coalesce the exactly-tiling tile rectangles of one guest frame into one staging buffer and one `glTexSubImage2D`, under a RED that counts GL upload calls and compares the readback byte for byte against the unbatched path |
| `logs/s8_menu_bar.sh` (new), `logs/parity/s8_menu_bar/` | **Task 3**: the bar — the login screen at 60 fps under a four-core spinning load, `bp_pending` < 2 in every sampler row, `upload=` < 30 ms/s on the menus, gate 3/3 |
| `docs/KNOWN.md`, `docs/STATUS.md`, `docs/CURRENT_SPRINT.md`, this plan | **Task 4**: Goal 2 close-out |

---

## Task 1 — Measure per call, before changing anything (spec Goal 2: "break the cost down per call")

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_trace.h`, `logs/s8_upload_trace.sh`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp`, `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp`
- Read only, to confirm and record: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_target_extent.h` (the header-only precedent), `logs/s7_audio_online.sh` (the launch-script shape), `scripts/parity/env.sh` (`PS2X_PC_SAMPLER=0.25` is already exported there — do not set it again)
- Test: new MiniTest cases in `ps2_gs_tests.cpp`, all context-free

**Interfaces:**
- `GsGlUploadTrace::bucketFor(size_t bytes) -> int` — 0 for ≤ 1 KB (the 16x16 PSMCT32 tile), then one bucket per doubling (2, 4, 8, 16, 32, 64 KB), 7 for anything larger. `kBuckets = 8`, `kBucketLabels` the matching names (`"1k"`, `"2k"`, …, `"big"`).
- `GsGlUploadTrace::Accum` — `uint64_t sizes[kBuckets]`, `uint64_t uploads`, `uint64_t rectsMarked`, `uint64_t glCalls`, `double shadowUs, markUs, recordUs, convertUs, glUs`, and `std::vector<uint32_t> dstTextures` (sorted-unique, bounded at 256 entries).
- `GsGlUploadTrace::note*` — `noteUpload(Accum&, size_t bytes, double shadowUs, double markUs)`, `noteRecord(Accum&, double us)`, `noteRect(Accum&)`, `noteGlUpload(Accum&, uint32_t texture, double convertUs, double glUs)`, `noteDst(Accum&, uint32_t)`.
- `GsGlUploadTrace::format(const Accum&, double elapsedMs) -> std::string` — one `[gs-upload]` line: counts per second, microseconds per call to one decimal.
- Knob `PS2X_GS_UPLOAD_TRACE=1`: print that line on the same 60-call cadence as `[gs-gl stats]` (`gs_gl_backend.cpp:1588`), and reset the accumulator with it. Off by default and free when off.

**Steps:**

- [ ] **Step 1: Write down where the 80-133 ms/s actually lands, before writing any code.** Re-derive the Handoff note's correction from the file itself and put the result in the ledger; it decides what Task 1 instruments and it is the one thing in the brief the tree contradicts.

```bash
sed -n '1577,1602p' third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp
sed -n '1827,1845p;1905,1916p' third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp
grep -n "glTexSubImage2D\|PIXEL_UNPACK\|glMapBuffer" third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp
grep -n "refreshDirtyRows(" third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp
```
  Expected, and record it exactly so: the `upload=` bucket is `CmdType::Upload` = index 2 (`gs_gl_backend.h:77-88`, `gs_gl_backend.cpp:1578-1581`); it times `executeUpload` only; `executeUpload` calls `m_shadow->UploadImage`, `markShadowPages` and `refreshRenderTargetsFromShadow`, and the last of those only appends to `rt.dirtyRects`; the **two** `glTexSubImage2D` sites are `:1998` and `:2016`, both in `refreshDirtyRows`, which no upload calls; there is **no PBO path**. So the brief's term (b) does not live in the column the brief points at, and the trace has to straddle two functions. Write that sentence into Step 5's commit message.

- [ ] **Step 2: RED — the accumulator's cases, before the header exists.** Add to `ps2_gs_tests.cpp`, in the GS suite next to the `GsGlTarget::choose` case at `:5577`:

```cpp
        tc.Run("GsGlUploadTrace buckets a 16x16 1 KB tile apart from a full-page upload", [](TestCase &t)
        {
            t.Equals(GsGlUploadTrace::bucketFor(1024u), 0, "16x16 PSMCT32 = 1024 bytes is bucket 0");
            t.Equals(GsGlUploadTrace::bucketFor(1u), 0, "a partial chunk still counts as the smallest bucket");
            t.Equals(GsGlUploadTrace::bucketFor(1025u), 1, "just over 1 KB moves up one bucket");
            t.Equals(GsGlUploadTrace::bucketFor(2048u), 1, "32x16 = 2 KB is bucket 1");
            t.Equals(GsGlUploadTrace::bucketFor(8192u), 3, "8 KB is bucket 3");
            t.Equals(GsGlUploadTrace::bucketFor(65536u), 6, "64 KB is bucket 6");
            t.Equals(GsGlUploadTrace::bucketFor(65537u), 7, "anything larger lands in the last bucket");
            t.Equals(std::string(GsGlUploadTrace::kBucketLabels[0]), std::string("1k"), "bucket 0 is labelled 1k");
            t.Equals(std::string(GsGlUploadTrace::kBucketLabels[7]), std::string("big"), "the last bucket is labelled big");
        });

        tc.Run("GsGlUploadTrace reports microseconds per call and destinations per second", [](TestCase &t)
        {
            GsGlUploadTrace::Accum a;
            for (int i = 0; i < 500; ++i)
            {
                GsGlUploadTrace::noteUpload(a, 1024u, 6.0, 2.0);   // 8 us of CPU per tile
                GsGlUploadTrace::noteRecord(a, 2.0);
                GsGlUploadTrace::noteGlUpload(a, 7u + static_cast<uint32_t>(i % 3), 1.0, 4.0);
            }
            t.Equals(static_cast<int>(a.uploads), 500, "500 uploads counted");
            t.Equals(static_cast<int>(a.sizes[0]), 500, "all of them in the 1 KB bucket");
            t.Equals(static_cast<int>(a.dstTextures.size()), 3, "three distinct destination textures");
            const std::string line = GsGlUploadTrace::format(a, 1000.0);
            t.IsTrue(line.find("[gs-upload]") == 0u, "the line is tagged [gs-upload]");
            t.IsTrue(line.find("uploads=500/s") != std::string::npos, "uploads per second");
            t.IsTrue(line.find("1k=500") != std::string::npos, "the histogram names the 1 KB bucket");
            t.IsTrue(line.find("shadow=6.0") != std::string::npos, "6 us of shadow swizzle per upload");
            t.IsTrue(line.find("mark=2.0") != std::string::npos, "2 us of page+rect marking per upload");
            t.IsTrue(line.find("record=2.0") != std::string::npos, "2 us of record per upload");
            t.IsTrue(line.find("convert=1.0") != std::string::npos, "1 us of CPU convert per GL upload call");
            t.IsTrue(line.find("gl=4.0") != std::string::npos, "4 us of glTexSubImage2D per GL upload call");
            t.IsTrue(line.find("dst_textures=3") != std::string::npos, "the destination count is on the line");
            // Half a second of wall clock doubles every per-second figure and leaves the per-call ones alone.
            const std::string half = GsGlUploadTrace::format(a, 500.0);
            t.IsTrue(half.find("uploads=1000/s") != std::string::npos, "per-second figures scale with elapsed");
            t.IsTrue(half.find("shadow=6.0") != std::string::npos, "per-call figures do not");
        });
```

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8
```
  Expected failure, before the header exists: `ps2_gs_tests.cpp: error: use of undeclared identifier 'GsGlUploadTrace'` (and `fatal error: 'runtime/gs/gs_gl_upload_trace.h' file not found` once the include is added). That compile error is the RED.

- [ ] **Step 3: Implement `gs_gl_upload_trace.h`.** Header-only, GL-free, in the shape of `gs_gl_target_extent.h`:

```cpp
#pragma once

// Sprint 8 Goal 2 Task 1: what a texture upload actually costs, per call.
//
// The [gs-gl stats] line says the menus spend 80-133 ms/s in `upload=` against gameplay's 20-28
// (KNOWN section 1, the 2026-09-18 re-measure), and that 100% of the traced uploads are 16x16
// PSMCT32 tiles of exactly 1024 bytes. What it does NOT say is which term of the tile path that
// time is: the shadow swizzle, the page/rect marking, the record under the queue mutex, the CPU
// convert in refreshDirtyRows, or glTexSubImage2D itself. Those live in three different functions
// and only the first two are inside the `upload=` bucket at all (gs_gl_backend.cpp:1577-1581 times
// executeUpload; the two glTexSubImage2D sites are in refreshDirtyRows and are charged to clear=,
// submit= and present=). This accumulator straddles them and prints one line.
//
// Header-only and free of GL includes on purpose, so ps2xTest can check the arithmetic without a
// context -- the same reason gs_gl_target_extent.h is.

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace GsGlUploadTrace
{
    constexpr int kBuckets = 8;
    // 1024 bytes is a 16x16 PSMCT32 tile: the entire menu upload population, per the [gs-pages]
    // trace. Each later bucket is a doubling, so a full 8 KB page and a 64 KB movie strip are
    // visibly separate columns rather than one "everything else".
    constexpr const char *kBucketLabels[kBuckets] = {"1k", "2k", "4k", "8k", "16k", "32k", "64k", "big"};

    inline int bucketFor(size_t bytes)
    {
        if (bytes <= 1024u)
            return 0;
        int b = 0;
        size_t limit = 1024u;
        while (b < kBuckets - 1 && bytes > limit)
        {
            limit <<= 1;
            ++b;
        }
        return b;
    }

    struct Accum
    {
        uint64_t sizes[kBuckets] = {0, 0, 0, 0, 0, 0, 0, 0};
        uint64_t uploads = 0;        // CmdType::Upload commands replayed
        uint64_t rectsMarked = 0;    // exact rectangles pushed onto rt.dirtyRects
        uint64_t glCalls = 0;        // glTexSubImage2D calls made by refreshDirtyRows
        double shadowUs = 0.0;       // (a) m_shadow->UploadImage: the CPU swizzle into shadow VRAM
        double markUs = 0.0;         // (a) markShadowPages + refreshRenderTargetsFromShadow
        double recordUs = 0.0;       // (c) GSGlBackend::record, game thread, under m_queueMutex
        double convertUs = 0.0;      // (a) the readVramRaw + convert + replicate loops feeding a GL upload
        double glUs = 0.0;           // (b) glTexSubImage2D itself
        // Distinct destination texture objects touched in the interval. Bounded: a menu screen has
        // a handful of render targets, and an unbounded set would be the trace's own hot spot.
        std::vector<uint32_t> dstTextures;
    };

    inline void noteDst(Accum &a, uint32_t texture)
    {
        if (a.dstTextures.size() >= 256u)
            return;
        const auto it = std::lower_bound(a.dstTextures.begin(), a.dstTextures.end(), texture);
        if (it == a.dstTextures.end() || *it != texture)
            a.dstTextures.insert(it, texture);
    }

    inline void noteUpload(Accum &a, size_t bytes, double shadowUs, double markUs)
    {
        ++a.uploads;
        ++a.sizes[bucketFor(bytes)];
        a.shadowUs += shadowUs;
        a.markUs += markUs;
    }

    inline void noteRecord(Accum &a, double us) { a.recordUs += us; }

    inline void noteRect(Accum &a) { ++a.rectsMarked; }

    inline void noteGlUpload(Accum &a, uint32_t texture, double convertUs, double glUs)
    {
        ++a.glCalls;
        a.convertUs += convertUs;
        a.glUs += glUs;
        noteDst(a, texture);
    }

    inline void reset(Accum &a) { a = Accum{}; }

    // One line: every count per second, every per-call figure in microseconds to one decimal.
    inline std::string format(const Accum &a, double elapsedMs)
    {
        const double perSec = elapsedMs > 0.0 ? 1000.0 / elapsedMs : 0.0;
        auto per = [](double total, uint64_t n) { return n ? total / static_cast<double>(n) : 0.0; };
        char buf[640];
        int n = std::snprintf(buf, sizeof(buf),
                              "[gs-upload] elapsed=%.0fms uploads=%.0f/s rects=%.0f/s gl_calls=%.0f/s sizes:",
                              elapsedMs, static_cast<double>(a.uploads) * perSec,
                              static_cast<double>(a.rectsMarked) * perSec,
                              static_cast<double>(a.glCalls) * perSec);
        for (int b = 0; b < kBuckets && n < 480; ++b)
            if (a.sizes[b])
                n += std::snprintf(buf + n, sizeof(buf) - n, " %s=%llu", kBucketLabels[b], (unsigned long long)a.sizes[b]);
        std::snprintf(buf + n, sizeof(buf) - n,
                      " us/upload: shadow=%.1f mark=%.1f record=%.1f us/gl_call: convert=%.1f gl=%.1f dst_textures=%zu",
                      per(a.shadowUs, a.uploads), per(a.markUs, a.uploads), per(a.recordUs, a.uploads),
                      per(a.convertUs, a.glCalls), per(a.glUs, a.glCalls), a.dstTextures.size());
        return std::string(buf);
    }
}
```
  Add `#include "runtime/gs/gs_gl_upload_trace.h"` to `ps2_gs_tests.cpp`'s include block (next to `gs_gl_target_extent.h` at `:14`).

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 && ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
```
  Expected: `Total Tests: 556` (554 + 2), `0 Failed`.

- [ ] **Step 4: Wire the measurement points into `gs_gl_backend.cpp`, behind one `static const bool`.** Six edits, and no seventh:

  1. **The knob and the accumulator**, next to the `s_stats` statics at `:1314-1320`:

```cpp
    // Sprint 8 Goal 2 Task 1: PS2X_GS_UPLOAD_TRACE=1 -- the per-call breakdown of the tile upload
    // path, on the same 60-call cadence as [gs-gl stats]. Read once; with it unset nothing below
    // reads a clock or touches a counter.
    static const bool s_uploadTrace = std::getenv("PS2X_GS_UPLOAD_TRACE") != nullptr;
```
  and the accumulator as a file-scope `GsGlUploadTrace::Accum g_uploadTrace;` in the anonymous namespace at `:43`. The render thread is its only writer; `record`'s contribution arrives through edit 4's atomic.

  2. **`executeUpload` (`:1827`) splits its own two terms.** Wrap `m_shadow->UploadImage(...)` and the `markShadowPages` + `refreshRenderTargetsFromShadow` pair each in a `steady_clock` pair taken only when `s_uploadTrace`, then `GsGlUploadTrace::noteUpload(g_uploadTrace, size, shadowUs, markUs)`. Do not move a single existing statement.

  3. **`refreshRenderTargetsFromShadow` counts the rect it pushes** — one `if (s_uploadTrace) GsGlUploadTrace::noteRect(g_uploadTrace);` beside `rt.dirtyRects.push_back(...)` at `:1912`. This is the number that says how much there is to batch: Task 2's whole claim is that `rects/s` is large and `gl_calls/s` equals it today.

  4. **`record` (`:722`) times itself**, because term (c) is the queue-mutex push on the **game** thread and is the one term not on the render thread. Time the whole body (lock acquisition included — the contention *is* the cost) and accumulate through a relaxed atomic rather than into the plain accumulator:

```cpp
    // The game thread writes this one; the render thread's formatter drains it. Relaxed is right:
    // the line is a diagnostic, and a torn microsecond does not change a verdict.
    static std::atomic<double> g_recordUsGameThread{0.0};
```
  with a `compare_exchange_weak` accumulate loop. **Only `CmdType::Upload` and `CmdType::BeginTransfer` are timed**: every tile costs one of each (`:838-882`), and timing `Submit` would fold the draw stream into the answer.

  5. **`uploadScaled` (`:1994`) splits convert from the GL call.** The convert loop lives in the callers (the `px` fill at `:2033-2037`, the `pixels` fill at `:2066-2076`), so time it there and pass the microseconds in; time `glTexSubImage2D` inside `uploadScaled`, and attribute the replication loop at `:2002-2015` to `convertUs`, not `glUs` — it is CPU work that happens to sit in the same lambda. Then `GsGlUploadTrace::noteGlUpload(g_uploadTrace, rt.color, convertUs, glUs)`.

  6. **The print**, inside the existing `if (s_stats && (++s_calls % 60u) == 0u)` block at `:1588`, after the back-pressure line:

```cpp
        if (s_uploadTrace)
        {
            g_uploadTrace.recordUs += g_recordUsGameThread.exchange(0.0);
            std::fprintf(stderr, "%s\n", GsGlUploadTrace::format(g_uploadTrace, elapsed).c_str());
            GsGlUploadTrace::reset(g_uploadTrace);
        }
```
  **RED for this step:** there is none a unit test can take — it is instrumentation of a GL-thread path that needs a context and a game. The verification is Step 6's launch: the line appears, its `uploads/s` is within 10% of the `[gs-gl stats]` line's `upload=<ms>/<count>` count over the same interval, and its `1k=` bucket holds essentially all of them. Say that sentence in the commit.

- [ ] **Step 5: Build the runtime, run the suite, commit the instrument.**

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "s8 goal2 task1 suite" -- ./build.sh test
```
  Expected: exit 0, `Total Tests: 556`, `0 Failed`, the Python suite unchanged at 1205.

```bash
git commit -m "feat(gs): PS2X_GS_UPLOAD_TRACE -- what a 1 KB tile upload costs, per call

Sprint 8 Goal 2 Task 1. The menus upload 7-11k 16x16 PSMCT32 tiles a second (1024 bytes each, 100% of
the traced uploads) at 80-133 ms/s against gameplay's 20-28, and KNOWN section 1 asks whether that is
per-call overhead rather than bytes. Nothing in the tree could answer it: the cost is spread over three
functions on two threads and the [gs-gl stats] upload= column sees only part of it.

Measured from the tree, and it corrects the brief this task was written from: upload= is the
CmdType::Upload bucket (executeCommands:1577-1581, CmdType index 2) and times executeUpload ONLY --
the shadow swizzle, markShadowPages and refreshRenderTargetsFromShadow, which merely appends a
rectangle to rt.dirtyRects. The two glTexSubImage2D call sites in this file are both inside
refreshDirtyRows, which no upload calls; their milliseconds land in clear=, submit= and present=.
There is no PBO path. So 80-133 ms/s is the CPU-side half alone.

gs_gl_upload_trace.h is a header-only, GL-free accumulator (the gs_gl_target_extent.h pattern, so
ps2xTest checks the arithmetic with no context): a size histogram by doubling from the 1 KB tile, and
five per-call terms -- shadow swizzle, page+rect marking, the queue-mutex record on the game thread,
the CPU convert feeding a GL upload, and glTexSubImage2D itself -- plus the distinct destination
texture objects touched. PS2X_GS_UPLOAD_TRACE=1 prints one [gs-upload] line on the same 60-call
cadence as [gs-gl stats]; unset, the knob is one static const bool and no clock is read.

Two MiniTest cases pin the bucket boundaries and the line's per-second vs per-call arithmetic
(556 total, 0 failed).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_trace.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp \
  third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp
git push
```

- [ ] **Step 6: One driven login launch, 60 s on the login screen, with both instruments on.** Write `logs/s8_upload_trace.sh` in the shape of `logs/s7_audio_online.sh` (`--only A` is the login-only path: `online_match_ours.py:4418`, *"A or B: run one instance's login only"*):

```bash
#!/usr/bin/env bash
# Sprint 8 Goal 2 Task 1 Step 6: the login screen's upload cost, per call. Instance A logs in and holds
# for 60 s with PS2X_GS_STATS (the upload=<ms>/<count> column, for the cross-check) and the new
# PS2X_GS_UPLOAD_TRACE (the breakdown). --only A is the login-only path: no B, no lobby, no match.
export PATH="/usr/bin:/mingw64/bin:/c/Users/Utilisateur/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
. scripts/parity/env.sh
export PS2X_GS_STATS=1 PS2X_GS_UPLOAD_TRACE=1
python -m tools_py.parity.online_match_ours --only A --hold 60 --out logs/parity/s8_upload_trace
rc=$?
taskkill //F //IM socom2.exe >/dev/null 2>&1
echo "done $rc" > logs/s8_upload_trace.done
exit $rc
```

```bash
chmod +x logs/s8_upload_trace.sh
bash scripts/check_quiet_gate.sh                 # must answer free before launching
scripts/run_detached.sh --owner gate --purpose launch logs/s8_upload_trace.sh logs/s8_upload_trace.marker
cat logs/s8_upload_trace.marker 2>/dev/null || echo running
```
  Expected: `exit=0` after ~2-3 minutes, and `logs/run_A_<stamp>.log` carrying interleaved `[gs-gl stats]` and `[gs-upload]` lines across the login screen. **Hold the suite while it runs** (`logs/.quiet` exists).

- [ ] **Step 7: The table.** Take the login-screen window of the log (from the login screen appearing to the end of the hold; the `[pc-sampler]` rows give the clock) and build one table — a good subagent brief, with `grep -n "\[gs-upload\]\|\[gs-gl stats\] calls=" logs/run_A_<stamp>.log` as the verification command and "a markdown table, no judgement" as the contract:

| interval | uploads/s | 1k share | us/upload shadow | mark | record | rects/s | gl_calls/s | us/gl_call convert | gl | dst_textures | `upload=` ms/s | fps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

  Then the arithmetic, by the controller and not the subagent:
  - **Cross-check the instrument**: `[gs-upload] uploads=<n>/s` against `[gs-gl stats] upload=<ms>/<count>`'s count over the same interval, within 10%. If they disagree by more, the trace is wired wrong and Step 4 is not done.
  - **Account for the milliseconds**: `uploads/s x (shadow + mark) us` should reproduce the `upload=` ms/s figure to within ~15%. If it does not, a term is missing, and the missing one is named before anything is changed.
  - **Name the dominant term**: the largest of `uploads/s x shadow`, `uploads/s x mark`, `uploads/s x record`, `gl_calls/s x convert`, `gl_calls/s x gl`, in ms/s.
- [ ] **Step 8: The spec's stop rule — apply it before Task 2, in writing.** Spec §3: *"Goal 2 stops if batching does not move the ms/s number, filing the per-call breakdown instead"*; the brief's form: **if per-call overhead is not the dominant term, file the breakdown and stop.** Concretely:
  - **Per-call overhead dominates** — the terms that scale with the *number* of calls (`mark`, `record`, `gl`, and `convert`'s fixed part) sum to more than half the menus' total, **or** `gl_calls/s` is within a factor of two of `uploads/s` (each tile still costing its own GL call) — then **continue to Task 2**.
  - **Bytes dominate** — `shadow` alone carries the bulk and is proportional to the 1 KB payload, with `gl_calls/s` already far below `uploads/s` — then **STOP**: batching cannot help, because the same bytes get swizzled either way. File the table in `docs/KNOWN.md` §1 as a proven row (replacing §1:89's experiment sentence), write a `STOP:` line on Task 2 and Task 3 here, and go straight to Task 4 with the goal reported as *measured and stopped by its own rule* — a result, not a failure.
  - Either way, record the verdict as a numbered ruling in the ledger with the two numbers it rests on.

```bash
git commit -m "docs: the menus' per-call upload breakdown, measured (Sprint 8 Goal 2 Task 1)

<the table>, from logs/run_A_<stamp>.log over <N> s of the login screen with PS2X_GS_UPLOAD_TRACE=1 and
PS2X_GS_STATS=1 (logs/s8_upload_trace.sh, --only A --hold 60). The dominant term is <term> at <X> ms/s of
<Y> total. The stop rule of the spec's section 3 <is not triggered: Task 2 proceeds | is triggered: Goal 2
stops here and the breakdown is the deliverable>.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  logs/s8_upload_trace.sh docs/KNOWN.md
git push
```

---

## Task 2 — Batch the tiles (spec Goal 2: "batch the tiles")

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_batch.h`
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h` (:156-160, `DirtyRect` becomes an alias of the header's `Rect`), `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (:1968-1970, :1994-2019, :2028-2041), `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp`
- Read only, to confirm and record: `gs_gl_backend.cpp:1898-1904` and `:2042-2044` (why the exact-rectangle path exists at all — the 2026-09-09 movie-strip report), `:1909-1915` (the 4096-rect cap, above which `exact` is false and the band path takes over)
- Test: the coalescer's cases (context-free, run everywhere) **and** the end-to-end GL call-count + readback case (needs a context; guarded, see R109)

**Interfaces:**
- `GsGlUploadBatch::Rect { uint32_t x0, y0, x1, y1; }` — half-open, native pixels, the same meaning `RenderTarget::DirtyRect` has today. `GSGlBackend::RenderTarget::DirtyRect` becomes `using DirtyRect = GsGlUploadBatch::Rect;` so nothing else in the backend changes shape.
- `GsGlUploadBatch::coalesce(std::vector<Rect> &rects) -> void` — in place; merges only rectangles whose union **is exactly** the merged rectangle (R108). Two passes: horizontal (same `y0`/`y1`, `x1 == next.x0`), then vertical (same `x0`/`x1`, `y1 == next.y0`). Exact duplicates collapse first. Never merges across a gap and never grows a rectangle by one pixel.
- `GsGlUploadBatch::glUploadCalls() -> uint64_t`, `noteGlUpload()`, `resetCounters()` — a relaxed atomic counter of `glTexSubImage2D` calls made by `refreshDirtyRows`, exposed the way the stats counters are, so a test can assert "one call, not forty" without a GL query.
- Knob `PS2X_GS_NO_UPLOAD_BATCH=1` — the A/B: skip `coalesce` and replay the rectangles one by one, exactly as `:2028-2041` does today. It is what the readback-equality test compares against and what a bisect uses if a menu ever looks wrong.

**Steps:**

- [ ] **Step 1: RED — the coalescer's cases, before the header exists.** The first four are the ones that matter; the fifth is the rule that keeps the 2026-09-09 bug dead.

```cpp
        tc.Run("GsGlUploadBatch merges a run of adjacent 16x16 tiles into one rectangle", [](TestCase &t)
        {
            std::vector<GsGlUploadBatch::Rect> r;
            for (uint32_t x = 0; x < 640u; x += 16u)
                r.push_back({x, 48u, x + 16u, 64u});          // one full 640-wide row of tiles
            t.Equals(static_cast<int>(r.size()), 40, "forty tiles in");
            GsGlUploadBatch::coalesce(r);
            t.Equals(static_cast<int>(r.size()), 1, "one rectangle out");
            t.Equals(static_cast<int>(r[0].x0), 0, "x0");
            t.Equals(static_cast<int>(r[0].x1), 640, "x1 spans the row");
            t.Equals(static_cast<int>(r[0].y0), 48, "y0");
            t.Equals(static_cast<int>(r[0].y1), 64, "y1 is one tile tall");
        });

        tc.Run("GsGlUploadBatch merges a block of tiles vertically once the rows are whole", [](TestCase &t)
        {
            std::vector<GsGlUploadBatch::Rect> r;
            for (uint32_t y = 0; y < 64u; y += 16u)
                for (uint32_t x = 0; x < 64u; x += 16u)
                    r.push_back({x, y, x + 16u, y + 16u});    // a 4x4 grid of tiles
            t.Equals(static_cast<int>(r.size()), 16, "sixteen tiles in");
            GsGlUploadBatch::coalesce(r);
            t.Equals(static_cast<int>(r.size()), 1, "one 64x64 rectangle out");
            t.Equals(static_cast<int>(r[0].x1 - r[0].x0), 64, "64 wide");
            t.Equals(static_cast<int>(r[0].y1 - r[0].y0), 64, "64 tall");
        });

        tc.Run("GsGlUploadBatch refuses to merge across a gap -- the bounding box would resurrect stale rows", [](TestCase &t)
        {
            // gs_gl_backend.cpp:1898-1904: a band re-read dragged the last cinematic frame back over
            // the GPU's newer pixels (the movie strip at rows ~396-415, user report 2026-09-09). A
            // bounding box with a hole in it is that bug with a new name.
            std::vector<GsGlUploadBatch::Rect> r{{0u, 48u, 16u, 64u}, {32u, 48u, 48u, 64u}};
            GsGlUploadBatch::coalesce(r);
            t.Equals(static_cast<int>(r.size()), 2, "a one-tile gap keeps the two rectangles apart");
            std::vector<GsGlUploadBatch::Rect> rows{{0u, 48u, 16u, 64u}, {0u, 80u, 16u, 96u}};
            GsGlUploadBatch::coalesce(rows);
            t.Equals(static_cast<int>(rows.size()), 2, "a row gap keeps them apart too");
            std::vector<GsGlUploadBatch::Rect> ragged{{0u, 48u, 16u, 64u}, {16u, 48u, 48u, 64u}, {0u, 64u, 16u, 80u}};
            GsGlUploadBatch::coalesce(ragged);
            t.Equals(static_cast<int>(ragged.size()), 2, "a ragged second row merges its own run and no more");
            t.Equals(static_cast<int>(ragged[0].x1), 48, "the full first row merged");
        });

        tc.Run("GsGlUploadBatch is idempotent, order-free and duplicate-safe", [](TestCase &t)
        {
            std::vector<GsGlUploadBatch::Rect> r{{16u, 48u, 32u, 64u}, {0u, 48u, 16u, 64u}, {16u, 48u, 32u, 64u}};
            GsGlUploadBatch::coalesce(r);
            t.Equals(static_cast<int>(r.size()), 1, "out-of-order input with a duplicate still merges to one");
            t.Equals(static_cast<int>(r[0].x0), 0, "x0");
            t.Equals(static_cast<int>(r[0].x1), 32, "x1 -- the duplicate did not widen it");
            const size_t before = r.size();
            GsGlUploadBatch::coalesce(r);
            t.Equals(static_cast<int>(r.size()), static_cast<int>(before), "coalescing twice changes nothing");
            std::vector<GsGlUploadBatch::Rect> empty;
            GsGlUploadBatch::coalesce(empty);
            t.Equals(static_cast<int>(empty.size()), 0, "empty in, empty out");
        });

        tc.Run("GsGlUploadBatch covers exactly the pixels it was given", [](TestCase &t)
        {
            // The invariant, by area over a pseudo-random tile soup: the merged rectangles cover the
            // same pixel set the input did -- no pixel added (R108), none dropped.
            std::vector<GsGlUploadBatch::Rect> r;
            uint32_t seed = 12345u;
            std::set<std::pair<uint32_t, uint32_t>> covered;
            for (int i = 0; i < 300; ++i)
            {
                seed = seed * 1103515245u + 12345u;
                const uint32_t x = ((seed >> 8) % 40u) * 16u, y = ((seed >> 20) % 28u) * 16u;
                r.push_back({x, y, x + 16u, y + 16u});
                for (uint32_t yy = y; yy < y + 16u; ++yy)
                    for (uint32_t xx = x; xx < x + 16u; ++xx)
                        covered.insert({xx, yy});
            }
            GsGlUploadBatch::coalesce(r);
            std::set<std::pair<uint32_t, uint32_t>> after;
            for (const GsGlUploadBatch::Rect &q : r)
                for (uint32_t yy = q.y0; yy < q.y1; ++yy)
                    for (uint32_t xx = q.x0; xx < q.x1; ++xx)
                        after.insert({xx, yy});
            t.IsTrue(after == covered, "the merged rectangles cover exactly the input pixels, no more and no less");
            t.IsTrue(r.size() < 300u, "and there are fewer of them");
        });
```

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8
```
  Expected failure: `error: use of undeclared identifier 'GsGlUploadBatch'` / `fatal error: 'runtime/gs/gs_gl_upload_batch.h' file not found`.

- [ ] **Step 2: Implement `gs_gl_upload_batch.h`.** Header-only, GL-free:

```cpp
#pragma once

// Sprint 8 Goal 2 Task 2: one glTexSubImage2D for a run of tiles, instead of one per tile.
//
// The menus upload 7-11k 16x16 PSMCT32 tiles a second (1024 bytes each). Each one is marked as its
// own exact rectangle on rt.dirtyRects (gs_gl_backend.cpp:1909-1915) and replayed as its own CPU
// convert loop, its own std::vector, and its own glTexSubImage2D (:2028-2041). Tiles that land next
// to each other in the same guest frame -- which is how a menu atlas is drawn -- can share all three.
//
// THE RULE (R108): a merge is allowed only when the merged rectangle is covered EXACTLY by the
// rectangles it replaces. The exact-rectangle path exists precisely because re-reading pixels nobody
// uploaded drags stale shadow rows back over newer GPU pixels -- the movie strip at rows ~396-415 on
// the typing screen, user report 2026-09-09, gs_gl_backend.cpp:1898-1904. A bounding box with a hole
// in it is that bug wearing a new hat, so this merges runs and grids and nothing else.
//
// Header-only and free of GL includes on purpose, so ps2xTest can check the arithmetic without a
// context -- the same reason gs_gl_target_extent.h is.

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <vector>

namespace GsGlUploadBatch
{
    struct Rect
    {
        uint32_t x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    };

    // Exposed for tests the way the [gs-gl stats] counters are: how many glTexSubImage2D calls the
    // shadow->GPU refresh path has made. Relaxed -- it is a counter, not a fence.
    inline std::atomic<uint64_t> g_glUploadCalls{0};
    inline void noteGlUpload() { g_glUploadCalls.fetch_add(1u, std::memory_order_relaxed); }
    inline uint64_t glUploadCalls() { return g_glUploadCalls.load(std::memory_order_relaxed); }
    inline void resetCounters() { g_glUploadCalls.store(0u, std::memory_order_relaxed); }

    inline void coalesce(std::vector<Rect> &rects)
    {
        if (rects.size() < 2u)
            return;
        // Row-major: same row band first, then left to right. Duplicates become adjacent.
        std::sort(rects.begin(), rects.end(), [](const Rect &a, const Rect &b) {
            if (a.y0 != b.y0) return a.y0 < b.y0;
            if (a.y1 != b.y1) return a.y1 < b.y1;
            if (a.x0 != b.x0) return a.x0 < b.x0;
            return a.x1 < b.x1;
        });
        std::vector<Rect> strips;
        strips.reserve(rects.size());
        for (const Rect &r : rects)
        {
            if (r.x1 <= r.x0 || r.y1 <= r.y0)
                continue;
            if (!strips.empty())
            {
                Rect &last = strips.back();
                if (last.y0 == r.y0 && last.y1 == r.y1)
                {
                    if (r.x0 == last.x0 && r.x1 == last.x1)   // exact duplicate
                        continue;
                    if (r.x0 == last.x1)                      // contiguous: no overlap, no gap
                    {
                        last.x1 = r.x1;
                        continue;
                    }
                }
            }
            strips.push_back(r);
        }
        // Vertical pass: a strip sitting exactly on top of another with the same columns and no gap.
        std::stable_sort(strips.begin(), strips.end(), [](const Rect &a, const Rect &b) {
            if (a.x0 != b.x0) return a.x0 < b.x0;
            if (a.x1 != b.x1) return a.x1 < b.x1;
            return a.y0 < b.y0;
        });
        std::vector<Rect> merged;
        merged.reserve(strips.size());
        for (const Rect &r : strips)
        {
            if (!merged.empty())
            {
                Rect &last = merged.back();
                if (last.x0 == r.x0 && last.x1 == r.x1 && last.y1 == r.y0)
                {
                    last.y1 = r.y1;
                    continue;
                }
            }
            merged.push_back(r);
        }
        rects.swap(merged);
    }
}
```

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 && ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
```
  Expected: `Total Tests: 561`, `0 Failed`. **If the ragged case or the area case fails, the coalescer is wrong and the backend is not touched until it passes** — that case is the whole safety argument.

- [ ] **Step 3: RED — the end-to-end case: N adjacent tile uploads, one GL call, identical pixels.** This one needs a GL context, so it follows the console-replay case's shape (`ps2_gs_tests.cpp:1626-1637`: `SetConfigFlags(FLAG_WINDOW_HIDDEN); InitWindow(640, 448, …)`) and is guarded by `PS2X_GS_TESTS_GL` (R109), which is off in CI and in the VM and on in the host's own pre-commit run.

```cpp
        tc.Run("adjacent 16x16 uploads to one page replay as ONE glTexSubImage2D with identical pixels (PS2X_GS_TESTS_GL)", [](TestCase &t)
        {
            if (!std::getenv("PS2X_GS_TESTS_GL"))
                return;
            // A synthetic stream in the shape the menus produce: BITBLTBUF / TRXPOS / TRXREG / TRXDIR
            // then 1024 bytes of image data, forty times across one 640-wide row of a CT32 target.
            auto runOnce = [&](bool batched, std::vector<uint8_t> &outVram) -> uint64_t
            {
#ifdef _WIN32
                _putenv_s("PS2X_GS_BACKEND", "gpu");
                _putenv_s("PS2X_GS_NO_UPLOAD_BATCH", batched ? "" : "1");
#else
                setenv("PS2X_GS_BACKEND", "gpu", 1);
                if (batched) unsetenv("PS2X_GS_NO_UPLOAD_BATCH"); else setenv("PS2X_GS_NO_UPLOAD_BATCH", "1", 1);
#endif
                std::vector<uint8_t> vram(PS2_GS_VRAM_SIZE, 0u);
                GS gs;
                gs.init(vram.data(), static_cast<uint32_t>(vram.size()), nullptr);
                GsGlUploadBatch::resetCounters();
                clearTargetOnce(gs, /*fbp*/ 0u, /*fbw*/ 10u);   // so the render target exists
                for (uint32_t x = 0; x < 640u; x += 16u)
                    uploadTile(gs, /*dbp*/ 0u, /*dbw*/ 10u, x, 48u, tilePixels(x));
                gs.hostRenderFrame();
                gs.refreshDisplaySnapshot();
                uint32_t snapSize = 0u;
                if (const uint8_t *snap = gs.lockDisplaySnapshot(snapSize))
                    if (snapSize >= vram.size())
                        outVram.assign(snap, snap + vram.size());
                gs.unlockDisplaySnapshot();
                return GsGlUploadBatch::glUploadCalls();
            };
            SetConfigFlags(FLAG_WINDOW_HIDDEN);
            InitWindow(640, 448, "upload batch");
            std::vector<uint8_t> unbatched, batched;
            const uint64_t callsUnbatched = runOnce(false, unbatched);
            const uint64_t callsBatched = runOnce(true, batched);
            CloseWindow();
            t.Equals(static_cast<int>(callsUnbatched), 40, "unbatched: one glTexSubImage2D per tile");
            t.Equals(static_cast<int>(callsBatched), 1, "batched: one glTexSubImage2D for the whole row");
            t.IsTrue(!batched.empty() && batched.size() == unbatched.size(), "both readbacks came back");
            t.IsTrue(batched == unbatched, "the batched path writes byte-identical pixels");
        });
```
  `clearTargetOnce`, `uploadTile` and `tilePixels` are three small file-local helpers in the test's anonymous namespace, built from the A+D quadword assembly the GS suite already uses for BITBLTBUF / TRXPOS / TRXREG / TRXDIR (`ps2_gs_tests.cpp:1655-1680`).

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 && ( cd third_party/ps2recomp/build-clang/ps2xTest && PS2X_GS_TESTS_GL=1 ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
```
  Expected failure, before the backend is wired: `batched: one glTexSubImage2D for the whole row  expected 1, got 0` — `glUploadCalls()` returns 0 on both paths because nothing calls `noteGlUpload` yet, and after edit 3 of Step 4 alone it would read 40 on both because nothing coalesces. Either reading is the same RED.

- [ ] **Step 4: Wire the coalescer into `refreshDirtyRows`.** Three edits, and no fourth:

  1. `gs_gl_backend.h:156-160`: `struct DirtyRect { uint32_t x0, y0, x1, y1; };` becomes

```cpp
        // Sprint 8 Goal 2: the type lives in gs_gl_upload_batch.h so the coalescer can be tested
        // without a GL context; the meaning (half-open, native pixels) is unchanged.
        using DirtyRect = GsGlUploadBatch::Rect;
```
  with `#include "runtime/gs/gs_gl_upload_batch.h"` added to the header's include block at `:3-6`.

  2. `gs_gl_backend.cpp:1968-1970`, immediately after `rects.swap(rt.dirtyRects);`:

```cpp
    // Sprint 8 Goal 2 Task 2: a menu frame marks thousands of 16x16 tiles; tiles that tile a
    // rectangle exactly become one staging buffer and one glTexSubImage2D. PS2X_GS_NO_UPLOAD_BATCH=1
    // is the A/B (and what the readback-equality test compares against).
    static const bool s_noBatch = std::getenv("PS2X_GS_NO_UPLOAD_BATCH") != nullptr;
    if (!s_noBatch)
        GsGlUploadBatch::coalesce(rects);
```

  3. `uploadScaled` (`:1994`) gains `GsGlUploadBatch::noteGlUpload();` beside **each** of its two `glTexSubImage2D` calls (`:1998`, `:2016`) — one per GL call, whichever scale path runs.

  Nothing else moves: the exact-rectangle loop at `:2028-2041` already handles a rectangle of any size, the `px` buffer it allocates is sized from the rectangle, and `usedHeight` is already taken from `y1`.

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 && ( cd third_party/ps2recomp/build-clang/ps2xTest && PS2X_GS_TESTS_GL=1 ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
```
  Expected: `Total Tests: 562`, `0 Failed` — including `batched: one glTexSubImage2D for the whole row` and `the batched path writes byte-identical pixels`.

- [ ] **Step 5: The A/B on the real menus, from Task 1's own instrument.** Rebuild the runner; the batched measurement is **Task 3 Step 2's run** and the unbatched one is **Task 1 Step 6's log** — same machine, same screen, same hold, so no fifth launch is spent here. Compare in one table: `uploads/s`, `rects/s`, `gl_calls/s`, `upload=` ms/s, the `clear=`/`submit=`/`present=` columns (where the GL half lives, per Task 1 Step 1), and fps. **The claim to check is `gl_calls/s` collapsing while `rects/s` stays put** — that is batching working. `upload=` moving is Task 3's bar, not this step's.

```bash
scripts/run_detached.sh --owner build --purpose build logs/build_runtime_job.sh logs/build_runtime.marker
cat logs/build_runtime.marker 2>/dev/null || echo running
```

- [ ] **Step 6: Gate 3/3, then commit.** This commit touches `third_party/ps2recomp/ps2xRuntime/src/`, so the three-stage gate is mandatory and is the check that stands in for "the Windows numbers are unmoved": the mission stage renders the game's own frames through this exact path.

```bash
bash scripts/check_quiet_gate.sh
python -m tools_py.parity.gate --only title,transition,mission --stamp s8_g2_batch
```
  Expected: `PASS title/transition/mission` 3/3, the title stage inside the calibrated 93.2-99.4 band.

```bash
git commit -m "perf(gs): batch the menus' 1 KB tile uploads into one glTexSubImage2D per run

Sprint 8 Goal 2 Task 2. refreshDirtyRows replayed one CPU convert loop, one std::vector and one
glTexSubImage2D per 16x16 tile, and the menus mark 7-11k of them a second. gs_gl_upload_batch.h
coalesces the exact rectangles of a guest frame before the replay; the wiring is three edits -- the
type alias, the coalesce call after the rect swap, and a counter beside each glTexSubImage2D.

The rule the coalescer keeps (R108): a merge is allowed ONLY where the merged rectangle is covered
exactly by the rectangles it replaces -- runs and grids, never a bounding box with a hole. The exact-
rectangle path exists because re-reading pixels nobody uploaded drags stale shadow rows over newer GPU
pixels (the movie strip at rows ~396-415 on the typing screen, user report 2026-09-09,
gs_gl_backend.cpp:1898-1904); a hole in a merged box is that bug with a new name. Five context-free
cases pin it, including an area invariant over a 300-tile soup: the merged rectangles cover exactly the
input pixels, no more and no less.

The end-to-end case (PS2X_GS_TESTS_GL=1, a hidden raylib window, the console-replay case's shape)
replays forty adjacent tile uploads to one page and asserts 40 GL upload calls unbatched against 1
batched, with byte-identical readbacks. PS2X_GS_NO_UPLOAD_BATCH=1 is the A/B and the bisect.

On the login screen: gl_calls/s <G0> -> <G> at rects/s <R>; upload= <X> -> <Y> ms/s; fps <A> -> <B>.
Gate 3/3 (s8_g2_batch). 562 tests, 0 failed.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_batch.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp \
  third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp
git push
```

---

## Task 3 — The bar: 60 fps on the login screen under a four-core load

**Files:**
- Create: `logs/s8_menu_bar.sh`, `logs/parity/s8_menu_bar/`
- Read only, to confirm and record: `logs/s7_freeze_loaded.sh` (the load generator's shape and **why the drafted `Start-Job` recipe does not survive** — four `powershell -c "while($true){}"` processes started by pid and killed by pid), `tools_py/parity/freeze_trace.py:80-81` (the freeze fields' names), `third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_freeze_fields.h:45` (the `[pc-sampler]` line that carries them)
- Test: none new; the bar is a measurement and the gate is the regression net

**Interfaces:** the four numbers, each with the command that reads it —
- **60 fps on the login screen under load**: `[gs-gl stats] elapsed=<ms> (<fps> fps)` — the mean over the login-screen window ≥ 59.0, and no interval below 55.
- **`bp_pending` < 2 in every sampler row across the login screen**: `python -m tools_py.parity.freeze_trace logs/run_A_<stamp>.log`, `bp_pending` **max** over the window ≤ 1 (the failing launches sat at 4 with `bp_waiters=1`).
- **`upload=` below 30 ms/s on the menus**: the `[gs-gl stats] calls=… upload=<ms>/<count>` column, mean over the same window.
- Plus the standing one from `docs/CURRENT_SPRINT.md:145`: **`pcm_underruns` stays 0** on the `[audio-trace]` line.

**Steps:**

- [ ] **Step 1: Write `logs/s8_menu_bar.sh` — the login-only path with `s7_freeze_loaded.sh`'s load generator.**

```bash
#!/usr/bin/env bash
# Sprint 8 Goal 2 Task 3: the bar. The LOGIN screen only (online_match_ours --only A), held 60 s, with
# research/29 section 3's load generator around it: four CPU-bound host processes spinning for the whole
# run, which is what "under host load" means in KNOWN.md section 4 -- nothing else, no disk or GPU load.
#
# The load is four `powershell -c "while($true){}"` processes started here and killed by pid, NOT the
# drafted `1..4 | % { Start-Job { while($true){} } }`: Start-Job's children belong to the powershell that
# -c exits out of immediately, and a second powershell has its own empty job table, so Remove-Job would
# find nothing to stop (logs/s7_freeze_loaded.sh, same reasoning, same fix).
export PATH="/usr/bin:/mingw64/bin:/c/Users/Utilisateur/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
. scripts/parity/env.sh
export PS2X_GS_STATS=1 PS2X_GS_UPLOAD_TRACE=1 PS2X_AUDIO_TRACE=1
LOAD_PIDS=()
for _ in 1 2 3 4; do
    powershell -NoProfile -NonInteractive -c "while(\$true){}" >/dev/null 2>&1 &
    LOAD_PIDS+=($!)
done
echo "load generator pids: ${LOAD_PIDS[*]}"
python -m tools_py.parity.online_match_ours --only A --hold 60 --out logs/parity/s8_menu_bar
rc=$?
kill "${LOAD_PIDS[@]}" 2>/dev/null
wait "${LOAD_PIDS[@]}" 2>/dev/null
taskkill //F //IM socom2.exe >/dev/null 2>&1
echo "done $rc" > logs/s8_menu_bar.done
exit $rc
```

```bash
chmod +x logs/s8_menu_bar.sh
bash scripts/check_quiet_gate.sh
scripts/run_detached.sh --owner gate --purpose launch logs/s8_menu_bar.sh logs/s8_menu_bar.marker
cat logs/s8_menu_bar.marker 2>/dev/null || echo running
```

- [ ] **Step 2: Read the numbers, and read them over the login-screen window only.** The window runs from the login screen appearing to the end of the hold — not the boot loads, which legitimately reach 35-46k uploads/s and are not what this goal is about (R110). Mark it from the harness's own screenshots and timestamps in `logs/parity/s8_menu_bar/`, and state its start and end seconds in the commit.

```bash
grep -n "\[gs-gl stats\] elapsed=\|\[gs-gl stats\] calls=" logs/run_A_<stamp>.log | tail -60
grep -n "\[gs-upload\]" logs/run_A_<stamp>.log | tail -40
python -m tools_py.parity.freeze_trace logs/run_A_<stamp>.log
grep -c "pcm_underruns=[1-9]" logs/run_A_<stamp>.log     # expected: 0
```

- [ ] **Step 3: The `bp_pending` sweep — every row, not the mean.** The KNOWN row's failure is *four launches in ten*, and the symptom is a maximum: one row at `bp_pending=4 bp_waiters=1` fails the bar even if the mean is 0.2. A subagent brief suits this: "print every `[pc-sampler]` row between seconds A and B with `bp_pending`, `bp_waiters` and `bp_wait_ms`, then the max of each; verification command `python -m tools_py.parity.freeze_trace <log>`; no judgement."

- [ ] **Step 4: If a bar is missed, say which and stop rather than tune.** The honest outcomes, in order of preference, each a ruling:
  - **All four met** → Step 5.
  - **`upload=` and `gl_calls/s` fell but fps did not reach 60 under load** → the remaining cost is not the tile path. Record the new dominant term from the same run's `[gs-upload]` line and file it. Goal 2's spec bar is the fps one, so this is a partial and is reported as one; the sprint does not get a second attempt at a different subsystem under this goal's name.
  - **Nothing moved** → the spec §3 stop rule fires late: file the breakdown, keep the instrument, revert nothing (the batching is proven byte-identical and is not a risk to carry), and close the goal as measured.
  - **A menu renders wrong** → `PS2X_GS_NO_UPLOAD_BATCH=1` is the immediate bisect and the coalescer's area invariant is where the bug is. This is the one outcome that reverts.
- [ ] **Step 5: Gate 3/3 and commit the bar.**

```bash
python -m tools_py.parity.gate --only title,transition,mission --stamp s8_g2_bar
```

```bash
git commit -m "test(gs): the menus' bar, measured under a four-core load (Sprint 8 Goal 2 Task 3)

logs/s8_menu_bar.sh: the login screen only (online_match_ours --only A --hold 60) with four spinning
host processes around it -- the same load generator shape as logs/s7_freeze_loaded.sh, and the same
reason its literal Start-Job recipe is not used.

Over the login-screen window (t=<A>..<B> s of logs/run_A_<stamp>.log):
  fps            <X> mean, <Y> minimum interval   (bar: 60 mean, nothing under 55)
  bp_pending     max <P>, bp_waiters max <W>      (bar: under 2; the failing launches sat at 4/1)
  upload=        <U> ms/s mean                    (bar: under 30; was 80-133)
  gl_calls/s     <G> against rects/s <R>          (unbatched, Task 1's run: <G0>)
  pcm_underruns  <N>                              (bar: 0)
Gate 3/3 (s8_g2_bar).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- logs/s8_menu_bar.sh
git push
```

---

## Task 4 — Close-out for Goal 2

**Files:**
- Modify: `docs/KNOWN.md` (§1 Proven; §3 Retracted if the per-call hypothesis dies), `docs/STATUS.md` (the current-state bullet and a dated entry), `docs/CURRENT_SPRINT.md` (the Sprint 8 block's item 1 and the pointer to Goal 3), `docs/superpowers/plans/2026-09-18-sprint-8-menu-render-cost.md` (this file: tick the boxes; any box left open carries a one-line reason or a `STOP:`)

**Steps:**

- [ ] **Step 1: `docs/KNOWN.md` §1 — the rows, each naming its artefact.** Up to three, written only with numbers actually measured:
  - **What a 1 KB tile upload costs, per call** — the Task 1 table, its dominant term, and the correction that `upload=<ms>/<count>` times `executeUpload` alone while the two `glTexSubImage2D` sites live in `refreshDirtyRows` and are charged to `clear=`/`submit=`/`present=`. Artefact: `logs/run_A_<stamp>.log`'s `[gs-upload]` lines, `logs/s8_upload_trace.sh`.
  - **Tile batching: `gl_calls/s` from `<G0>` to `<G>` at unchanged `rects/s`, pixels byte-identical** — artefact: the `PS2X_GS_TESTS_GL` case (40 vs 1, equal readbacks) and the A/B pair of runs.
  - **The login screen under a four-core load: `<X>` fps, `bp_pending` max `<P>`, `upload=` `<U>` ms/s** — artefact: `logs/run_A_<stamp>.log` over `t=<A>..<B>`, `logs/s8_menu_bar.sh`, gate `s8_g2_bar` 3/3.
- [ ] **Step 2: Rewrite §1:88 and §1:89's experiment sentences, and retract what the measurement killed.** §1:89 currently proposes the experiment this goal ran ("is it the 1 KB tile path's per-call overhead — 10 us a tile — rather than the byte count"); replace it with the answer and the number. If per-call overhead turned out **not** to be the dominant term, that hypothesis goes to **§3 Retracted** in the file's own shape — believed, then killed by measurement, with the artefact — exactly as the page-marking hypothesis was. §1:88's login-screen row keeps its history and gains the resolution line.
- [ ] **Step 3: `docs/STATUS.md`.** Replace the current-state bullet's opening with the branch and the Goal 2 verdict in one sentence, and add a dated entry in the file's own voice: what landed, the bars and their numbers, and that the next goal is Goal 3 (voice: serve the headset — spec §2, `docs/CURRENT_SPRINT.md`'s Sprint 8 item 2).
- [ ] **Step 4: `docs/CURRENT_SPRINT.md`'s Sprint 8 block.** Mark item 1 done or partly done with its numbers, name this plan as the one it carried, and move the pointer to item 2.
- [ ] **Step 5: Tick this plan's boxes, and leave a reason on every one that stays open.** A box with neither a tick nor a reason is the failure mode the Sprint 6 close-out audit found; a `STOP:` line citing Task 1 Step 8's verdict is a valid reason.
- [ ] **Step 6: Commit.**

```bash
git commit -m "docs: Sprint 8 Goal 2 closed -- the menus' render cost, measured and batched

KNOWN gains the per-call breakdown of the 1 KB tile upload path with the correction it forced (the
upload= column times executeUpload alone; both glTexSubImage2D sites are in refreshDirtyRows and are
charged to clear=/submit=/present=), the batching result (gl_calls/s <G0> -> <G> at unchanged rects/s,
byte-identical readbacks) and the login screen's numbers under a four-core load (<X> fps, bp_pending max
<P>, upload= <U> ms/s against a bar of 30). Section 1's login-screen and decodes rows lose their
experiment sentences and carry the answer; <the per-call hypothesis is confirmed | the per-call
hypothesis is retracted into section 3 with its artefact>. STATUS and CURRENT_SPRINT carry the verdict
and move the pointer to Goal 3 (voice).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  docs/KNOWN.md docs/STATUS.md docs/CURRENT_SPRINT.md \
  docs/superpowers/plans/2026-09-18-sprint-8-menu-render-cost.md
git push
```

---

## Rulings made on the owner's behalf

R107 onward; see the Goal 1 plan for R99-R106 and the Sprint 7 plan for R91-R98.

- **R107** (Task 1): **the per-call trace is a new knob on its own line, not a widening of the `[gs-gl stats]` line.** The stats line is parsed by eye and by `grep` in a dozen places across `docs/research` and `logs/`, and Sprint 7's tables were read from it; adding five columns would break every one of those readings for a diagnostic that will be on for exactly two launches. `[gs-upload]` is its own line under its own knob, printed inside the same 60-call block so the two are always about the same interval. *Cost if wrong:* one more line in a traced log, and a reader has to match two tags instead of one — which is what the `elapsed=` field on both lines is for.

- **R108** (Task 2): **a merge is allowed only where the merged rectangle is covered exactly by the rectangles it replaces.** The tempting version — take the bounding box of a frame's rects and upload it once — is strictly fewer GL calls and is a bug: `refreshDirtyRows`'s exact-rectangle path exists *because* re-reading shadow pixels nobody uploaded drags stale rows back over newer GPU contents (`gs_gl_backend.cpp:1898-1904`, the movie strip at rows ~396-415 on the typing screen, user report 2026-09-09; `:2042-2044` says the same about bands). A bounding box with a hole in it is that bug with a new name, and it would appear on exactly the screens this goal is meant to fix. The coalescer therefore merges runs and grids only, and the area invariant in Task 2 Step 1 is the case that fails if anyone loosens it. *Cost if wrong in the other direction:* some menu layouts coalesce into several rectangles instead of one, so the win is smaller than it could be — which the `rects/s` vs `gl_calls/s` pair in the trace makes visible rather than mysterious.

- **R109** (Task 2, Step 3): **the end-to-end GL case is guarded by `PS2X_GS_TESTS_GL`, and the coalescer's own cases are not.** `ps2x_tests` runs in three places with no display: GitHub Actions on `ubuntu-24.04` (Goal 1 Task 2), the `socom-linux` VM's headless build, and any fresh clone. A case that calls `InitWindow` unconditionally would fail in all three, and the existing console-replay GL case already takes the env-guard route (`ps2_gs_tests.cpp:1561`, `PS2X_CONSOLE_REPLAY_GL`). The arithmetic that can be wrong silently — the coalescer — is context-free and runs *everywhere, always*; the wiring that needs a context is checked on the host before every commit that touches it, and the commit says so. *Cost if wrong:* a wiring regression could reach CI green; the gate's mission stage and the byte-identical readback assertion are the two things standing behind that, and both run on the host before the commit.

- **R110** (Task 3): **the bar is read over the login-screen window, not over the whole run.** The boot loads legitimately reach 35-46k uploads/s at ~30 ms/s (KNOWN §1:89) and would drag any whole-run mean; the goal's sentence, its KNOWN row and its spec bar are all about the login screen. The window's start and end seconds go in the commit message so the number can be re-derived. *Cost if wrong:* a reader who takes the whole-run mean gets a worse number than the bar claims, which is the safe direction, and the commit tells them where to look.

## Self-review

- **Spec coverage.** Goal 2's sentence has three clauses and each is a task: *"trace the login screen's pages"* and *"break the cost down per call"* → Task 1 (the `PS2X_GS_UPLOAD_TRACE` histogram, the five terms, the destination count, and one driven `--only A --hold 60` launch that reads them); *"batch the tiles"* → Task 2 (the exactly-tiling coalescer, the GL call counter, the byte-identical readback); *"Bar: the login screen at 60 fps under a four-core load with `bp_pending` under 2"* → Task 3, which also carries the brief's third number (`upload=` under 30 ms/s) and `docs/CURRENT_SPRINT.md:145`'s standing `pcm_underruns` 0. The spec §3 stop rule is carried **twice**, deliberately: as a pre-condition in Task 1 Step 8 (per-call overhead is not dominant → stop before changing anything) and as a post-condition in Task 3 Step 4 (nothing moved → file and close). Task 4 closes the goal either way.
- **Launch budget.** Spec §3 allows "about four" on Windows for Goal 2. Spent: `s8_upload_trace` (Task 1 Step 6, 60 s hold), `s8_menu_bar` (Task 3 Step 1, 60 s hold under load), and two gate runs (`s8_g2_batch`, `s8_g2_bar`) — four, with Task 2's A/B reading Task 1's log rather than adding a fifth. Runtime builds go through `run_detached.sh` with a marker and are not launches.
- **Placeholder scan.** Clean: no `TBD`, no "handle edge cases", no "similar to Task N". Every value left to be filled is a **measurement**, marked `<X>`, `<G0>`, `<A>..<B>`, `<stamp>` inside a commit-message or KNOWN template, replaced by the run that precedes the commit. Four implementation choices the spec left open are named as rulings: the separate trace line (R107), the exact-cover merge rule (R108), the GL test's guard (R109), the measurement window (R110).
- **Type consistency.** `GsGlUploadTrace::bucketFor(size_t) -> int`, `kBuckets`/`kBucketLabels`, `Accum`, `noteUpload(Accum&, size_t, double, double)`, `noteRecord(Accum&, double)`, `noteRect(Accum&)`, `noteGlUpload(Accum&, uint32_t, double, double)`, `noteDst(Accum&, uint32_t)`, `reset(Accum&)`, `format(const Accum&, double) -> std::string`; `GsGlUploadBatch::Rect{x0,y0,x1,y1}`, `coalesce(std::vector<Rect>&)`, `noteGlUpload()`, `glUploadCalls() -> uint64_t`, `resetCounters()`; `GSGlBackend::RenderTarget::DirtyRect = GsGlUploadBatch::Rect`. Each is used with one signature everywhere it appears. Knobs: `PS2X_GS_UPLOAD_TRACE`, `PS2X_GS_NO_UPLOAD_BATCH`, `PS2X_GS_TESTS_GL`, and the existing `PS2X_GS_STATS`, `PS2X_GS_TRACE_PAGES`, `PS2X_GS_BACKEND`, `PS2X_GS_SCALE`, `PS2X_GS_NO_DIRTY_REFRESH`, `PS2X_PC_SAMPLER`, `PS2X_AUDIO_TRACE`.
- **What the tree contradicted in the brief, and what this plan does instead.** One, and it is load-bearing: the brief asks for the per-call cost of "the GL call itself (glTexSubImage2D or the PBO path)" **inside the `[gs-gl stats]` line's `upload=<ms>/<count>` column**. `gs_gl_backend.cpp:1577-1581` charges that column to `CmdType::Upload` = `executeUpload` (`:1827-1877`), which never calls `glTexSubImage2D`; the file's only two such calls are `:1998` and `:2016`, inside `refreshDirtyRows` (`:1947-2080`), which runs from `executeClear` (`:2094`), the submit path and the present path — so the GL half is charged to `clear=`, `submit=` and `present=`. There is **no PBO path** (`:3579`'s `glBufferData` is the vertex stream). This plan therefore instruments both functions and labels each term by where it runs, rather than assuming one column holds them; Task 1 Step 1 re-derives the correction from the file before any code is written, and the Handoff notes state it so no dispatch starts from the brief's version. Two smaller notes, neither a contradiction: the brief's "`bp_pending=4 bp_waiters=1` (the pc-sampler line's freeze fields)" is right — they are formatted by `socom2_freeze_fields.h:45` and parsed by `freeze_trace.py:80-81`; and `scripts/parity/env.sh:25` already exports `PS2X_PC_SAMPLER=0.25`, so neither launch script sets it again.
- **Owner gate.** Goal 2 is autonomous end to end under the owner's standing instruction of 2026-09-17: four host launches, no second machine, no owner check. The one judgement that could want an owner is the R108 trade-off (fewer GL calls against never re-reading an unwritten pixel), and it is decided the safe way, against the goal's own performance interest, because the alternative reintroduces a bug the owner reported himself.

