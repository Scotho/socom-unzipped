# Sprint 8 Goal 2b — The Menus' Render Cost, at Its Measured Root: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Goal 2 measured the menus and stopped itself (R108): tile batching would have batched nothing, because the GL side already uploads whole bands — 31-38 calls a second for 8000 guest uploads, `rects=0/s`. The cost the measurement actually found is in two columns: the CPU-side shadow swizzle (`upload=`, 8.1-10.1 us x ~8000 uploads/s = 42-80 ms/s) and `transfer=` beside it at **157-277 ms/s**, three to four times the uploads, on a screen that draws a handful of 2D quads. Goal 2b finds out what those milliseconds are and removes them at the root. The root this plan is aimed at, and which Task 1 must confirm or kill before a line changes: **the game re-uploads the same menu atlas every frame into one destination texture, and every upload — identical bytes or not — bumps `m_generation` in `markShadowPages` (`gs_gl_backend.cpp:1843-1848`), which invalidates every cached texture overlapping those pages (`:3209-3222`) and forces a full `glDeleteTextures`/`glGenTextures`/`glTexImage2D` decode at the next draw (`:3105-3122`).** The bar is the login screen's `upload=` + `transfer=` under 60 ms/s, and under a four-core spinning host load the login screen at 55+ fps with `bp_pending` under 2 in every sampler row, gate 3/3, the title stage's score unchanged, and the GS suite's console-replay case still pixel-identical.

**Architecture:** Measure first, again, and in the same shape — because Goal 2's own stop rule saved four launches and one wrong fix, and the same discipline applies to a column nobody has ever split. Task 1 extends the existing `PS2X_GS_UPLOAD_TRACE` instrument (it is already wired, already committed, already free when off) with the `transfer=` breakdown **by phase and by direction**, with the single-chunk / multi-chunk split that decides what Task 2 is even allowed to skip, and with the one question the whole plan turns on: **are the uploaded bytes identical frame to frame?**, answered by a cheap rolling content hash per destination rectangle. Task 2 is one idea, and it is the cheapest possible one: an upload whose bytes already sit in the shadow at that rectangle does nothing — no swizzle, no page marking, no dirty rectangle, no generation bump — and counts in a `skipped_identical` stat. Task 3 is written conditionally on Task 1's numbers with both branches spelled out, because the second-largest term is not known yet and a plan that guesses it is a plan that gets rewritten. Every new piece of arithmetic lives in a **header-only, GL-free** header beside `gs_gl_upload_trace.h`, so `ps2x_tests` checks it on Windows, in CI and in the VM with no GL context; only the wiring lives in `gs_gl_backend.cpp`. Platform-neutral by construction: plain C++20 in the shared GL backend, under no `#ifdef`.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh` on the host; system clang + Ninja in the VM and on `ubuntu-24.04`), CMake ≥ 3.20, OpenGL 3.3 through raylib's context, MiniTest (`ps2x_tests`, no filter, runs every case), Python 3 `unittest` (**not** pytest, see Global Constraints), the online harness (`tools_py/parity/online_match_ours.py`, `tools_py/parity/gate.py`, `tools_py/parity/freeze_trace.py`), `scripts/run_detached.sh` + `scripts/loop_lock.sh` for every host launch.

**Spec:** `docs/superpowers/specs/2026-09-18-sprint-8-linux-and-finish-design.md` §2 "Goal 2 — the menus' render cost at the root" and §3's stop rule, carried forward by **R108** in `docs/superpowers/plans/2026-09-18-sprint-8-menu-render-cost.md`, whose closing sentence names this plan: *"The next experiment is a per-term trace of executeTransfer and a swizzle that skips unchanged tiles (the game re-uploads the same menu atlas every frame: one destination texture), which is Goal 2b's plan."* **Required reading for every dispatch:** this plan's Handoff notes and Global Constraints; the Goal 2 plan in full (its Task 1 is the measurement this one continues, and its R107-R110 still bind); `docs/KNOWN.md` §1's row "The login screen runs at 12-30 fps under GL back-pressure in 4 of 10 launches" (:98) with the 2026-09-19 measurement sentence; for the code `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` §§`executeCommands` (:1395-1650), `executeTransfer` (:1850-1870), `executeUpload` (:1873-1935), `markShadowPages` (:1843-1848), `refreshRenderTargetsFromShadow` (:1940-2011), `resolveTexture` (:3125-3240), `decodeTexture`'s tail (:3105-3122), `setupDrawState` (:3389-3400) and `flushBatch` (:3572-3578); `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_cpu_backend.cpp:1441-1456` (`GSCpuBackend::BeginTransfer`), `:1458-1560` (`UploadImage`), `:1616` and `:1656` (the two pixel-moving transfer paths); `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_frontend.cpp:938-943` and `:1842-1845` (how an IMAGE GIF tag becomes one `UploadImage`); `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h:77-88` (`CmdType`), `:148-165` (`gpuDirty`, `shadowStale`, `DirtyRect`), `:201-210` (`TextureEntry::generation`), `:309-320` (`m_gpuDirtyPages`, `m_shadowPageGeneration`, `m_generation`), `:381-385` (`m_currentTransfer`, the chunk counters).

## Handoff notes for the executing model (read once)

- **Process.** superpowers:subagent-driven-development; a fresh implementer per task; a task review after each that re-derives at least one number independently; the controller merges. Ledger at `.superpowers/sdd/2026-09-19-sprint-8-menu-cost-2b/progress.md`. Decisions on the owner's behalf are `Ruling: … — why — cost if wrong`, numbered from **R117** (R107-R110 are the Goal 2 plan's, R111-R116 are the hosted-server and voice plans').

- **Read this before Task 1, because the brief this plan was written from asks the wrong question about it.** The brief asks what `executeTransfer` does per call to cost 157-203 ms/s: *"host->local transfers? local->local VRAM moves? readbacks?"* The tree says **none of those**, and the whole of Task 1 depends on knowing it:
  - `executeCommands` takes its per-command clock at `gs_gl_backend.cpp:1402`, **before** the dispatch switch, and charges the interval to a bucket indexed by `static_cast<int>(cmd.type) & 7` at `:1613-1619`. `CmdType::BeginTransfer` is index 1 — the `transfer=` column at `:1627-1637`.
  - The `BeginTransfer` case is **two statements** (`:1535-1538`): `flushBatch();` and then `executeTransfer(cmd.transfer);`. Both are inside the timed interval. So `transfer=` is *flushBatch + executeTransfer*, not `executeTransfer`.
  - `executeTransfer` itself (`:1850-1870`) does, on a menu: `m_shadow->BeginTransfer(command)` — which for `direction == 0` (host->local, which is what a menu upload is) takes a mutex and copies the command into `m_transferState` and **moves no pixels at all** (`gs_cpu_backend.cpp:1441-1456`; the two pixel-moving paths, `PerformLocalToLocalTransfer` at `:1616` and `PerformLocalToHostTransfer` at `:1656`, run only for `direction == 2` and `direction == 1`) — then the movie-start sniff, `m_currentTransfer = command`, and two lines of expected-byte arithmetic. That is a handful of microseconds of struct copy, not 26.
  - `flushBatch` (`:3572-3578`) returns immediately when there is no pending batch, and otherwise calls `setupDrawState` (`:3389`), which calls `refreshDirtyRows(*rt)` (`:3393`) and resolves the batch's texture through `resolveTexture` (`:3125`). **That** is where the milliseconds are, and `transfer=` carries them because a transfer command is what interrupted the draw batch.
  - **The suspected root, stated as a chain, for Task 1 to confirm or kill:** `markShadowPages` (`:1843-1848`) does `++m_generation` and stamps every touched page **on every upload, unconditionally** → `resolveTexture`'s cache hit at `:3209-3222` compares the texture's pages' newest generation against `TextureEntry::generation` and, on any bump, `glDeleteTextures` + `m_textures.erase` → `decodeTexture` re-runs and ends in `glGenTextures` + `glTexImage2D` over the whole texture (`:3105-3122`). An identical re-upload of the menu atlas therefore costs a full texture decode and a full `glTexImage2D` at the next draw, and both are billed to `transfer=`.
  - The consequence for this goal: Task 1 must split `transfer=` into **flushBatch** and **executeTransfer proper**, and split flushBatch into `refreshDirtyRows` / texture decode / the draw itself. A step that instruments only `executeTransfer`'s body will measure a few microseconds and report that the column is a mystery.

- **Uploads arrive whole or in chunks, and it matters.** `gs_frontend.cpp:938-943` turns one IMAGE GIF tag into one `processImageData`, which is one `UploadImage` (`:1842-1845`); `executeUpload` accumulates `m_uploadReceivedBytes` against `m_uploadExpectedBytes` and only refreshes render targets when a rectangle is complete (`gs_gl_backend.cpp:1927-1935`). A transfer split across several GIF packets arrives as several `UploadImage` calls. **Task 2 may only skip an upload that is the whole transfer in one call** — skipping chunk 1 of 3 and then discovering chunk 2 differs would leave the shadow half-written. Task 1 counts the single-chunk share so Task 2 knows how much of the population it is allowed to touch.

- **`docs/KNOWN.md` has one writer: the controller.** Retractions happen on discovery, in the same hour. §1:98 currently carries the Goal 2 measurement and names this goal's experiment; Task 5 rewrites it with the answer.

- **Autonomy (owner 2026-09-17, standing).** Proceed autonomously; no waiting for a window the owner names. **One host launch at a time**, always through `scripts/run_detached.sh`, and **suites are held while a host launch runs**: no `./build.sh test`, no `python -m unittest`, no gate and no second launch while `logs/.quiet` exists (`bash scripts/check_quiet_gate.sh` answers).

- **Subagents (owner 2026-09-17).** Bounded mechanical work goes to Opus subagents with an exact brief and a verification command; judgment stays with the controller. A brief names: the files to touch, the exact edit, the command that proves it, and the expected output. A subagent never decides whether a bar is met, never writes `docs/KNOWN.md`, never commits, and never starts a launch. In this plan the natural subagent jobs are Task 1 Step 6's table of numbers out of a 60 s log and Task 4 Step 3's per-row `bp_pending` scan.

- **Commit conventions.** `git commit -m "…" -- <paths>` with an explicit pathspec; never `git add -A`; `server/config/simulated.db` stays unstaged (it is modified in the working tree right now and must stay that way); `ONBOARDING.md` stays untracked; `vm/` is gitignored and nothing under it is ever staged. Push after each commit. Trailer: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

- **Line numbers.** Every line number in this plan is the number at `01b7033` (the branch tip when it was written). Other Sprint 8 goals are landing in the same checkout; before starting a task, `git diff -- <the task's files>` and reconcile, saying so in the ledger rather than writing a step twice.

- **Test binary and its baseline.** `ps2x_tests` takes no filter and runs every case. Windows: `third_party/ps2recomp/build-clang/ps2xTest/ps2x_tests.exe`. Linux: `third_party/ps2recomp/build-linux/ps2xTest/ps2x_tests`. **Record the baseline total `B` in the ledger before Task 1 Step 2** (build and run once, read `Total Tests:`); every later step states its expected total as `B + n`, because Goals 3 and 5 are adding cases in the same checkout and a hard-coded number would be wrong by the time it is read.

- **The launch budget.** Three host launches: `s8_transfer_trace` (Task 1, 60 s hold), `s8_menu_bar2` (Task 4, 60 s hold under a four-core load), and one gate run (`s8_g2b_bar`). Task 2's and Task 3's evidence comes from `ps2x_tests` and from Task 4's single run; a second gate run (`s8_g2b_skip`) is spent only if Task 3 lands code, and the plan says so where it does.

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
python -m tools_py.parity.gate --only title,transition,mission --stamp s8_g2b_<what>

# --- reading a run ---
grep -n "\[gs-gl stats\] calls=" logs/run_A_<stamp>.log | tail -40
grep -n "\[gs-upload\]" logs/run_A_<stamp>.log | tail -40
python -m tools_py.parity.freeze_trace logs/run_A_<stamp>.log     # bp_pending / bp_waiters per sampler row
```

A host launch script is a file under `logs/`, in the shape of `logs/s8_upload_trace.sh` (the online instrument set comes from `scripts/parity/env.sh`, which is **sourced, never executed**, and already exports `PS2X_PC_SAMPLER=0.25` — do not set it again):

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
- **The arithmetic lives in headers, the wiring lives in the backend.** New logic goes into `runtime/gs/gs_gl_upload_trace.h` (extended) and `runtime/gs/gs_gl_upload_identity.h` (new) — header-only, `#include <cstdint>`-grade dependencies, **no GL header, no raylib**, exactly as `runtime/gs/gs_gl_target_extent.h` and `gs_gl_upload_trace.h` already are. That is what lets the cases run in CI and in the VM where there is no context at all.
- **The trace costs nothing when it is off.** `PS2X_GS_UPLOAD_TRACE` is read once into a `static const bool` at the top of each function that uses it, as it already is at `gs_gl_backend.cpp:1876` and `:1944`; with it unset no clock is read, no counter is touched and no branch is taken per upload beyond that one bool. **The Task 2 skip is different and deliberately so: it is ON by default** (it is the fix, not a diagnostic) with `PS2X_GS_NO_UPLOAD_SKIP=1` as the A/B and the bisect. Its hash is the only per-upload work it adds, and Task 2 Step 5 measures that cost before the commit.
- **Skipping an upload changes pixels or it is a bug.** A skip is legal only when the shadow already holds exactly those bytes at that rectangle **and** nothing has happened since that could have made the shadow disagree with what the GPU shows: no other writer touched those pages (`m_shadowPageGeneration`), and no render target overlapping them is `gpuDirty` or `shadowStale` (`gs_gl_backend.h:148-149`, set at `gs_gl_backend.cpp:2207` and `:3421` when the GPU draws into a target). This is **R118**, and Task 2 Step 1's cases are written to fail if it is violated.
- **Never skip a partial upload.** Only a call that delivers the whole transfer in one go (`m_uploadReceivedBytes == 0 && size == m_uploadExpectedBytes`) is a skip candidate. This is **R119**.
- `./build.sh test` exit 0 on the Windows host before any commit touching `third_party/ps2recomp/`, `tools_py/` or `scripts/`. **The three-stage gate PASS (3/3) before any commit touching `third_party/ps2recomp/ps2xRuntime/src/`.**
- **The Windows numbers stay as measured** unless a bar says they move. The substitute checks for a change to `dist/socom2.exe` are the gate's 3/3, the title stage's score band, and the GS suite's console-replay case being pixel-identical (`ps2_gs_tests.cpp:1526-1600`).
- **Platform-neutral.** No `#ifdef _WIN32` is added by this goal. If a change cannot be written without one, it stops and becomes a ruling.
- Explicit pathspecs on every commit, never `git add -A`. `server/config/simulated.db` is **never** staged. `vm/` is never staged.
- Commit trailer, every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- LF line endings in every new file. New shell scripts are `chmod +x` and committed with the mode bit.
- **Python tests are `unittest`, never pytest.** `tools_py/tests/test_test_hygiene.py` fails the suite on a `test_*.py` outside `tools_py/tests/`, on any `import pytest`, and on a module-level `def test_`.

---

## File map

| Path | Responsibility |
|---|---|
| `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_trace.h` (extend), `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (:1402 the clock, :1535-1538 the BeginTransfer case, :1613-1637 the buckets and the stats line, :1843-1848 `markShadowPages`, :1850-1870 `executeTransfer`, :1873-1935 `executeUpload`, :3105-3122 `decodeTexture`'s tail, :3209-3222 the cache gate, :3389-3393 `setupDrawState`, :3572-3578 `flushBatch`), `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp` (new cases), `logs/s8_transfer_trace.sh` (new) | **Task 1**: split `transfer=` by phase and by direction, count single-chunk vs chunked uploads, count texture-cache invalidations and decodes, and answer "are the bytes identical frame to frame?" with a rolling content hash — one driven login launch that reads them |
| `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_identity.h` (new), `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.h` (:381-385, the identity cache member), `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (:1873-1935 `executeUpload`), `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp` | **Task 2**: an upload whose bytes the shadow already holds is a no-op — no swizzle, no page marking, no generation bump, no dirty rectangle — under R118's guard and R119's whole-transfer rule, counted as `skipped_identical` |
| `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (branch A: :1850-1870; branch B: :1535-1538 and `flushBatch`), `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp` | **Task 3**: the same idea for `executeTransfer` if Task 1 shows repeated identical local transfers (branch A), else the specific fix Task 1's breakdown points at (branch B) — both written out, one executed |
| `logs/s8_menu_bar2.sh` (new), `logs/parity/s8_menu_bar2/` | **Task 4**: the bar — `upload=`+`transfer=` under 60 ms/s, 55+ fps under a four-core load with `bp_pending` < 2 in every row, gate 3/3, title score unchanged, console-replay pixel-identical |
| `docs/KNOWN.md`, `docs/STATUS.md`, `docs/CURRENT_SPRINT.md`, `docs/superpowers/plans/2026-09-18-sprint-8-menu-render-cost.md`, this plan | **Task 5**: Goal 2b close-out |

---

## Task 1 — Split `transfer=`, and ask whether the bytes repeat (R108's named experiment)

**Files:**
- Create: `logs/s8_transfer_trace.sh`
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_trace.h`, `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp`, `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp`
- Read only, to confirm and record: `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_cpu_backend.cpp:1441-1456`, `logs/s8_upload_trace.sh` (the launch-script shape this one copies), `logs/run_A_20260919_003832.log` (Goal 2's run, for the before-numbers)
- Test: new MiniTest cases in `ps2_gs_tests.cpp`, all context-free

**Interfaces:**
- `GsGlUploadTrace::Accum` gains, beside the fields it has today:
  - `uint64_t transfers`, `uint64_t transfersByDir[4]` — `BeginTransfer` commands replayed, and how many were host->local (0), local->host (1), local->local (2), other (3).
  - `double flushUs, transferBodyUs` — the two halves of the `transfer=` bucket: `flushBatch()` and `executeTransfer()` (`gs_gl_backend.cpp:1535-1538`).
  - `double dirtyRowsUs, decodeUs, drawUs` — the three phases inside a non-empty `flushBatch`: `refreshDirtyRows` (`:3393`), `decodeTexture` (`:3105-3122`), and everything left in `setupDrawState` + the draw call.
  - `uint64_t flushesEmpty, flushesReal` — how many of the 8000 flushes a second had nothing to draw.
  - `uint64_t decodes, cacheInvalidations` — textures decoded, and cache entries thrown away by the generation gate at `:3209-3222`.
  - `uint64_t uploadsWhole, uploadsChunked` — R119's population split.
  - `uint64_t uploadsIdentical` — uploads whose bytes hash-match what the shadow already holds for that rectangle (Task 1 counts them; Task 2 acts on them).
- `GsGlUploadTrace::noteTransfer(Accum&, uint32_t direction, double flushUs, double bodyUs)`, `noteFlushPhases(Accum&, double dirtyRowsUs, double decodeUs, double drawUs, bool empty)`, `noteDecode(Accum&, bool wasInvalidation)`, `noteUploadShape(Accum&, bool whole, bool identical)`.
- `GsGlUploadTrace::format` gains a second line, tagged `[gs-transfer]`, so the existing `[gs-upload]` line keeps the shape Goal 2's tables were read from (R107 again): `GsGlUploadTrace::formatTransfer(const Accum&, double elapsedMs) -> std::string`.
- `GsGlUploadIdentity::hash64(const uint8_t *data, size_t size) -> uint64_t` — FNV-1a 64. Lives in the new header (Task 2's home) because Task 1 already needs it; Task 2 adds the cache around it.
- `GsGlUploadIdentity::Key` / `Cache` — see Task 2's Interfaces; Task 1 uses the cache **read-only for counting** and never suppresses a write.

**Steps:**

- [ ] **Step 1: Re-derive where the `transfer=` milliseconds land, before writing any code.** This is the one thing the brief this task was written from gets wrong, and it decides what Task 1 instruments.

```bash
sed -n '1400,1404p;1533,1545p;1610,1640p' third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp
sed -n '1843,1870p' third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp
sed -n '1441,1458p' third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_cpu_backend.cpp
sed -n '3389,3396p;3572,3579p' third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp
sed -n '3205,3225p' third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp
```
  Expected, and record it exactly so in the ledger: the clock is taken at `:1402` before the switch; the `BeginTransfer` case at `:1535-1538` is `flushBatch(); executeTransfer(cmd.transfer);` and **both are timed into the `transfer=` bucket**; `executeTransfer`'s own body moves no pixels for `direction == 0` (`gs_cpu_backend.cpp:1441-1456` — `PerformLocalToLocalTransfer` and `PerformLocalToHostTransfer` are the `direction == 2` and `direction == 1` paths only); `flushBatch` at `:3572-3578` early-returns on an empty batch and otherwise enters `setupDrawState`, which calls `refreshDirtyRows(*rt)` at `:3393` and resolves the texture through `resolveTexture` at `:3125`; `markShadowPages` at `:1843-1848` does `++m_generation` on every upload; `resolveTexture`'s gate at `:3209-3222` erases and re-decodes any cached texture whose pages carry a newer generation. Write that paragraph into Step 4's commit message.

- [ ] **Step 2: RED — the new accumulator fields and the hash, before they exist.** Add to `ps2_gs_tests.cpp`, inside the existing `MiniTest::Case("GsGlUploadTrace", …)` block that ends at `:5637`:

```cpp
        tc.Run("GsGlUploadTrace splits the transfer bucket into flush and body, by direction", [](TestCase &t)
        {
            GsGlUploadTrace::Accum a;
            for (int i = 0; i < 400; ++i)
            {
                // gs_gl_backend.cpp:1535-1538 -- the BeginTransfer case is flushBatch() then
                // executeTransfer(), and the clock at :1402 charges both to transfer=.
                GsGlUploadTrace::noteTransfer(a, 0u, 18.0, 2.0);
                GsGlUploadTrace::noteFlushPhases(a, 6.0, 9.0, 3.0, false);
            }
            for (int i = 0; i < 100; ++i)
            {
                GsGlUploadTrace::noteTransfer(a, 2u, 0.0, 40.0);   // a local->local VRAM move
                GsGlUploadTrace::noteFlushPhases(a, 0.0, 0.0, 0.0, true);
            }
            t.Equals(static_cast<int>(a.transfers), 500, "500 transfers counted");
            t.Equals(static_cast<int>(a.transfersByDir[0]), 400, "400 host->local");
            t.Equals(static_cast<int>(a.transfersByDir[2]), 100, "100 local->local");
            t.Equals(static_cast<int>(a.flushesEmpty), 100, "100 flushes had nothing to draw");
            t.Equals(static_cast<int>(a.flushesReal), 400, "400 flushes actually drew");
            const std::string line = GsGlUploadTrace::formatTransfer(a, 1000.0);
            t.IsTrue(line.find("[gs-transfer]") == 0u, "the line is tagged [gs-transfer]");
            t.IsTrue(line.find("transfers=500/s") != std::string::npos, "transfers per second");
            t.IsTrue(line.find("dir0=400") != std::string::npos, "the direction histogram names host->local");
            t.IsTrue(line.find("dir2=100") != std::string::npos, "and local->local");
            // 400 x 18 us of flush = 7.2 ms/s; 400 x 2 + 100 x 40 = 4.8 ms/s of body.
            t.IsTrue(line.find("flush=7.2ms/s") != std::string::npos, "the flush half of transfer= in ms/s");
            t.IsTrue(line.find("body=4.8ms/s") != std::string::npos, "the executeTransfer half in ms/s");
            t.IsTrue(line.find("dirty_rows=2.4ms/s") != std::string::npos, "refreshDirtyRows inside the flush");
            t.IsTrue(line.find("decode=3.6ms/s") != std::string::npos, "decodeTexture inside the flush");
            t.IsTrue(line.find("draw=1.2ms/s") != std::string::npos, "the draw itself inside the flush");
        });

        tc.Run("GsGlUploadTrace counts whole vs chunked uploads and identical bytes", [](TestCase &t)
        {
            GsGlUploadTrace::Accum a;
            for (int i = 0; i < 90; ++i)
                GsGlUploadTrace::noteUploadShape(a, true, i < 72);    // 80% identical, all whole
            for (int i = 0; i < 10; ++i)
                GsGlUploadTrace::noteUploadShape(a, false, false);    // chunked, never skippable (R119)
            t.Equals(static_cast<int>(a.uploadsWhole), 90, "90 whole-transfer uploads");
            t.Equals(static_cast<int>(a.uploadsChunked), 10, "10 arrived in pieces");
            t.Equals(static_cast<int>(a.uploadsIdentical), 72, "72 carried bytes the shadow already held");
            const std::string line = GsGlUploadTrace::formatTransfer(a, 1000.0);
            t.IsTrue(line.find("whole=90") != std::string::npos, "the whole-transfer count is on the line");
            t.IsTrue(line.find("chunked=10") != std::string::npos, "and the chunked one");
            t.IsTrue(line.find("identical=72") != std::string::npos, "and the identical-bytes count");
        });

        tc.Run("GsGlUploadTrace counts texture-cache invalidations against decodes", [](TestCase &t)
        {
            // gs_gl_backend.cpp:3209-3222: a cached entry whose pages carry a newer generation is
            // deleted and re-decoded. markShadowPages (:1843) bumps that generation on EVERY upload,
            // identical bytes or not, so this pair is the suspected root of the transfer= column.
            GsGlUploadTrace::Accum a;
            for (int i = 0; i < 30; ++i)
                GsGlUploadTrace::noteDecode(a, true);
            for (int i = 0; i < 4; ++i)
                GsGlUploadTrace::noteDecode(a, false);
            t.Equals(static_cast<int>(a.decodes), 34, "34 decodes");
            t.Equals(static_cast<int>(a.cacheInvalidations), 30, "30 of them replaced a live cache entry");
            const std::string line = GsGlUploadTrace::formatTransfer(a, 1000.0);
            t.IsTrue(line.find("decodes=34/s") != std::string::npos, "decodes per second");
            t.IsTrue(line.find("invalidations=30/s") != std::string::npos, "invalidations per second");
        });

        tc.Run("GsGlUploadIdentity::hash64 separates a one-byte change and is order-sensitive", [](TestCase &t)
        {
            std::vector<uint8_t> a(1024u, 0x5Au);
            std::vector<uint8_t> b = a;
            t.IsTrue(GsGlUploadIdentity::hash64(a.data(), a.size()) ==
                     GsGlUploadIdentity::hash64(b.data(), b.size()), "equal bytes hash equal");
            b[517] ^= 0x01u;
            t.IsTrue(GsGlUploadIdentity::hash64(a.data(), a.size()) !=
                     GsGlUploadIdentity::hash64(b.data(), b.size()), "one flipped bit in the middle changes the hash");
            std::vector<uint8_t> c{1u, 2u, 3u, 4u}, d{4u, 3u, 2u, 1u};
            t.IsTrue(GsGlUploadIdentity::hash64(c.data(), 4u) != GsGlUploadIdentity::hash64(d.data(), 4u),
                     "the same bytes in a different order hash differently");
            t.IsTrue(GsGlUploadIdentity::hash64(nullptr, 0u) == GsGlUploadIdentity::hash64(nullptr, 0u),
                     "an empty buffer is well defined");
        });
```
  Add `#include "runtime/gs/gs_gl_upload_identity.h"` to `ps2_gs_tests.cpp`'s include block, next to the `gs_gl_upload_trace.h` include.

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8
```
  Expected failure, before the header and the fields exist: `ps2_gs_tests.cpp: error: no member named 'noteTransfer' in namespace 'GsGlUploadTrace'` and `fatal error: 'runtime/gs/gs_gl_upload_identity.h' file not found`. That compile error is the RED.

- [ ] **Step 3: Implement the header changes.** `gs_gl_upload_identity.h` first, header-only and GL-free in the shape of `gs_gl_upload_trace.h`:

```cpp
#pragma once

// Sprint 8 Goal 2b: is the game re-uploading bytes the shadow already holds?
//
// Goal 2's measurement (R108) found the login screen pushing ~8000 host->local transfers a second
// into ONE destination texture, at 42-80 ms/s of CPU swizzle plus a transfer= column of 157-277.
// The menu atlas does not change between frames, so the suspicion is that most of those uploads
// write bytes that are already there -- and every one of them still calls markShadowPages, which
// bumps m_generation (gs_gl_backend.cpp:1843-1848) and throws away every cached texture overlapping
// the pages (:3209-3222), forcing a full decode and glTexImage2D at the next draw.
//
// This header is the arithmetic for answering that, and then for acting on it: a 64-bit FNV-1a over
// the incoming bytes, and a bounded cache keyed by the destination rectangle that remembers the
// hash, the byte count, and the shadow generation the rectangle carried when the hash was taken.
// The generation is what makes a hit trustworthy: if any other writer has touched those pages since,
// the remembered hash says nothing about what the shadow holds now.
//
// Header-only and free of GL includes on purpose, so ps2xTest can check the arithmetic without a
// context -- the same reason gs_gl_target_extent.h and gs_gl_upload_trace.h are.

#include <cstddef>
#include <cstdint>
#include <unordered_map>

namespace GsGlUploadIdentity
{
    inline uint64_t hash64(const uint8_t *data, size_t size)
    {
        uint64_t h = 1469598103934665603ull;               // FNV-1a 64 offset basis
        for (size_t i = 0; i < size; ++i)
        {
            h ^= static_cast<uint64_t>(data[i]);
            h *= 1099511628211ull;                          // FNV-1a 64 prime
        }
        return h;
    }

    // One destination rectangle, exactly as executeUpload knows it from m_currentTransfer.
    struct Key
    {
        uint32_t dbp = 0, dbw = 0, dsax = 0, dsay = 0, rrw = 0, rrh = 0;
        uint32_t dpsm = 0;
        bool operator==(const Key &o) const
        {
            return dbp == o.dbp && dbw == o.dbw && dsax == o.dsax && dsay == o.dsay &&
                   rrw == o.rrw && rrh == o.rrh && dpsm == o.dpsm;
        }
    };

    struct KeyHash
    {
        size_t operator()(const Key &k) const
        {
            uint64_t h = 1469598103934665603ull;
            const uint32_t f[7] = {k.dbp, k.dbw, k.dsax, k.dsay, k.rrw, k.rrh, k.dpsm};
            for (uint32_t v : f)
            {
                h ^= static_cast<uint64_t>(v);
                h *= 1099511628211ull;
            }
            return static_cast<size_t>(h);
        }
    };

    struct Entry
    {
        uint64_t hash = 0;
        uint64_t size = 0;
        uint64_t generation = 0;   // the max m_shadowPageGeneration over the rectangle's pages, then
        uint64_t lastUse = 0;      // eviction: the frame counter at the last hit or store
    };

    // Bounded: a menu screen keys a few hundred rectangles; an unbounded map would become the
    // measurement's own hot spot and, worse, a slow leak on a long mission.
    constexpr size_t kMaxEntries = 4096u;

    class Cache
    {
    public:
        // True when this rectangle was last written with exactly these bytes AND nothing has stamped
        // its pages since. `generation` is the caller's max m_shadowPageGeneration over the pages.
        bool matches(const Key &k, uint64_t hash, uint64_t size, uint64_t generation) const
        {
            const auto it = m_entries.find(k);
            return it != m_entries.end() && it->second.hash == hash && it->second.size == size &&
                   it->second.generation == generation;
        }

        void store(const Key &k, uint64_t hash, uint64_t size, uint64_t generation, uint64_t frame)
        {
            if (m_entries.size() >= kMaxEntries && m_entries.find(k) == m_entries.end())
                evict(frame);
            Entry &e = m_entries[k];
            e.hash = hash;
            e.size = size;
            e.generation = generation;
            e.lastUse = frame;
        }

        void touch(const Key &k, uint64_t frame)
        {
            const auto it = m_entries.find(k);
            if (it != m_entries.end())
                it->second.lastUse = frame;
        }

        // Anything that invalidates the shadow wholesale (a Reset, a readback that repaints it)
        // invalidates every remembered hash with it.
        void clear() { m_entries.clear(); }

        size_t size() const { return m_entries.size(); }

    private:
        void evict(uint64_t frame)
        {
            for (auto it = m_entries.begin(); it != m_entries.end();)
                it = (it->second.lastUse + 120ull < frame) ? m_entries.erase(it) : std::next(it);
            if (m_entries.size() >= kMaxEntries)
                m_entries.clear();      // a pathological frame: start again rather than grow
        }

        std::unordered_map<Key, Entry, KeyHash> m_entries;
    };
}
```
  Then extend `gs_gl_upload_trace.h` with the fields and the `note*` functions named in this task's Interfaces, and add `formatTransfer`, which prints **milliseconds per second** for the phase terms (not microseconds per call — the question here is "which phase owns the column", and ms/s is the unit the `[gs-gl stats]` line is already read in):

```cpp
    inline std::string formatTransfer(const Accum &a, double elapsedMs)
    {
        const double perSec = elapsedMs > 0.0 ? 1000.0 / elapsedMs : 0.0;
        const double msPerSec = elapsedMs > 0.0 ? 1000.0 / elapsedMs : 0.0;   // us totals -> ms/s
        auto ms = [&](double us) { return us * msPerSec / 1000.0; };
        char buf[768];
        int n = std::snprintf(buf, sizeof(buf),
                              "[gs-transfer] elapsed=%.0fms transfers=%.0f/s dir0=%llu dir1=%llu dir2=%llu dir3=%llu"
                              " flush=%.1fms/s body=%.1fms/s dirty_rows=%.1fms/s decode=%.1fms/s draw=%.1fms/s"
                              " flush_empty=%llu flush_real=%llu decodes=%.0f/s invalidations=%.0f/s",
                              elapsedMs, static_cast<double>(a.transfers) * perSec,
                              (unsigned long long)a.transfersByDir[0], (unsigned long long)a.transfersByDir[1],
                              (unsigned long long)a.transfersByDir[2], (unsigned long long)a.transfersByDir[3],
                              ms(a.flushUs), ms(a.transferBodyUs), ms(a.dirtyRowsUs), ms(a.decodeUs), ms(a.drawUs),
                              (unsigned long long)a.flushesEmpty, (unsigned long long)a.flushesReal,
                              static_cast<double>(a.decodes) * perSec,
                              static_cast<double>(a.cacheInvalidations) * perSec);
        std::snprintf(buf + n, sizeof(buf) - n, " whole=%llu chunked=%llu identical=%llu skipped=%llu",
                      (unsigned long long)a.uploadsWhole, (unsigned long long)a.uploadsChunked,
                      (unsigned long long)a.uploadsIdentical, (unsigned long long)a.skippedIdentical);
        return std::string(buf);
    }
```
  (`skippedIdentical` is zero until Task 2 fills it; it is declared here so the line's shape does not change between Task 1's run and Task 4's, and the two are comparable by `grep`.)

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 && ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
```
  Expected: `Total Tests: B + 4`, `0 Failed`.

- [ ] **Step 4: Wire the measurement points into `gs_gl_backend.cpp`, behind the existing `static const bool`.** Six edits, and no seventh:

  1. **The `BeginTransfer` case (`:1535-1538`) times its two halves separately.** Take a clock before `flushBatch()`, one between it and `executeTransfer()`, one after, only when the trace is on, then `GsGlUploadTrace::noteTransfer(g_uploadTrace, cmd.transfer.direction, flushUs, bodyUs)`. Do not move either statement.

  2. **`flushBatch` (`:3572`) reports whether it did anything**, and `setupDrawState` (`:3389`) times `refreshDirtyRows(*rt)` and the texture resolve separately from the rest. The cleanest shape that touches no control flow: file-scope `thread_local double g_flushDirtyRowsUs, g_flushDecodeUs;` zeroed at the top of `flushBatch`, added to by the two timed regions, and drained by `GsGlUploadTrace::noteFlushPhases(g_uploadTrace, g_flushDirtyRowsUs, g_flushDecodeUs, restUs, /*empty=*/!hadBatch)` at the end of `flushBatch` — `restUs` being the flush's own elapsed minus the two.

  3. **`decodeTexture`'s tail (`:3118-3122`) counts itself**, and `resolveTexture`'s gate (`:3218-3222`) says whether the decode replaced a live entry: `GsGlUploadTrace::noteDecode(g_uploadTrace, /*wasInvalidation=*/true)` on the `glDeleteTextures` + `erase` branch, `false` on a cold miss. This is the number that tests the suspected root: if `invalidations/s` tracks the frame rate times the number of menu textures, the cache is being thrown away every frame.

  4. **`executeUpload` (`:1873`) classifies each upload and hashes it.** Before `m_shadow->UploadImage`, when the trace is on: build the `GsGlUploadIdentity::Key` from `m_currentTransfer`, compute `hash64(data, size)`, compute the rectangle's `generation` as the max `m_shadowPageGeneration[p]` over `[page, page + span)`, ask `m_uploadIdentity.matches(...)`, and call `GsGlUploadTrace::noteUploadShape(g_uploadTrace, /*whole=*/(m_uploadReceivedBytes == 0u && size == m_uploadExpectedBytes), /*identical=*/matched)`. **Task 1 stores and counts but never suppresses**: the write always happens, so this step cannot change a pixel. Store back with `m_uploadIdentity.store(key, hash, size, <the generation AFTER markShadowPages>, m_frameCounter)`.

  5. **The member.** `GsGlUploadIdentity::Cache m_uploadIdentity;` next to `m_currentTransfer` in `gs_gl_backend.h:381-385` (render thread only — `executeUpload` has no other caller), cleared wherever the shadow is reset wholesale (`gs_gl_backend.cpp:690` and the `CmdType::Reset` case at `:1607`).

  6. **The print**, inside the existing `if (s_stats && (++s_calls % 60u) == 0u)` block, immediately after the `[gs-upload]` line: `std::fprintf(stderr, "%s\n", GsGlUploadTrace::formatTransfer(g_uploadTrace, elapsed).c_str());` — before the existing `GsGlUploadTrace::reset(g_uploadTrace)`, so both lines describe the same interval.

  **RED for this step:** there is none a unit test can take — it is instrumentation of a GL-thread path that needs a context and a game. The verification is Step 5's launch: the `[gs-transfer]` line appears; its `transfers=<n>/s` is within 10% of the `[gs-gl stats]` line's `transfer=<ms>/<count>` count over the same interval; and `flush + body` in ms/s reproduces that line's `transfer=<ms>` to within ~15%. Say that sentence in the commit.

- [ ] **Step 5: Build the runtime, run the suite, commit the instrument, and take one driven login launch.**

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "s8 goal2b task1 suite" -- ./build.sh test
```
  Expected: exit 0, `Total Tests: B + 4`, `0 Failed`, the Python suite unchanged at 1205.

```bash
git commit -m "feat(gs): the transfer column, split -- and a hash that asks whether the menu bytes repeat

Sprint 8 Goal 2b Task 1. Goal 2 stopped itself at R108: on the login screen the GL side is already
batched (31-38 whole-band calls a second against 8000 guest uploads, rects 0/s), so tile batching had
nothing to batch. What it left unexplained is transfer= at 157-277 ms/s beside upload='s 42-80, on a
screen that draws a handful of 2D quads.

Measured from the tree, and it corrects the brief this task was written from: transfer= is not what
executeTransfer does. The per-command clock is taken at executeCommands:1402, BEFORE the dispatch
switch, and the CmdType::BeginTransfer case at :1535-1538 is two statements -- flushBatch() and then
executeTransfer(). executeTransfer's own body moves no pixels for a host->local transfer, which is what
a menu upload is (gs_cpu_backend.cpp:1441-1456; the local->local and local->host paths at :1616 and
:1656 are the only ones that copy). The milliseconds are the DRAW BATCH the transfer interrupted:
flushBatch (:3572) enters setupDrawState (:3389), which calls refreshDirtyRows (:3393) and resolves the
batch's texture (:3125). And markShadowPages (:1843-1848) bumps m_generation on every upload, identical
bytes or not, which makes resolveTexture's gate (:3209-3222) delete the cached texture and re-decode it
into a fresh glTexImage2D (:3105-3122) at the next draw.

This commit measures that chain rather than assuming it. [gs-transfer], a second line under the same
PS2X_GS_UPLOAD_TRACE knob and on the same 60-call cadence (R107: the [gs-gl stats] line's shape is
parsed by eye and by grep in a dozen places and is not widened), carries: the transfer count by
direction; the flush/body split of the column; refreshDirtyRows, decodeTexture and the draw inside the
flush; empty against real flushes; decodes and cache invalidations a second; and the upload population
split into whole-transfer against chunked, with a rolling count of uploads whose bytes hash-match what
the shadow already holds. gs_gl_upload_identity.h is header-only and GL-free (the gs_gl_target_extent.h
pattern): FNV-1a 64 plus a bounded rectangle-keyed cache that remembers the hash, the byte count and the
shadow generation, because a remembered hash means nothing if another writer has touched the pages.

Task 1 counts and never suppresses: every upload still writes. Four MiniTest cases pin the new
arithmetic.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_identity.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_trace.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp \
  third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp
git push
```

  Then `logs/s8_transfer_trace.sh`, in the shape of `logs/s8_upload_trace.sh`:

```bash
#!/usr/bin/env bash
# Sprint 8 Goal 2b Task 1 Step 5: the login screen's transfer= column, split by phase, plus the
# identical-bytes count. Instance A logs in and holds for 60 s with PS2X_GS_STATS (the transfer=<ms>/<count>
# column, for the cross-check) and PS2X_GS_UPLOAD_TRACE (both [gs-upload] and the new [gs-transfer]).
# --only A is the login-only path: no B, no lobby, no match.
export PATH="/usr/bin:/mingw64/bin:/c/Users/Utilisateur/AppData/Local/Microsoft/WindowsApps:/c/Windows/system32:/c/Windows:$PATH"
cd /c/projects/socom_pc || exit 1
. scripts/parity/env.sh
export PS2X_GS_STATS=1 PS2X_GS_UPLOAD_TRACE=1
python -m tools_py.parity.online_match_ours --only A --hold 60 --out logs/parity/s8_transfer_trace
rc=$?
taskkill //F //IM socom2.exe >/dev/null 2>&1
echo "done $rc" > logs/s8_transfer_trace.done
exit $rc
```

```bash
chmod +x logs/s8_transfer_trace.sh
bash scripts/check_quiet_gate.sh                 # must answer free before launching
scripts/run_detached.sh --owner gate --purpose launch logs/s8_transfer_trace.sh logs/s8_transfer_trace.marker
cat logs/s8_transfer_trace.marker 2>/dev/null || echo running
```
  Expected: `exit=0` after ~2-3 minutes, and `logs/run_A_<stamp>.log` carrying interleaved `[gs-gl stats]`, `[gs-upload]` and `[gs-transfer]` lines across the login screen. **Hold the suite while it runs** (`logs/.quiet` exists).

- [ ] **Step 6: The table.** Take the login-screen window of the log (from the login screen appearing to the end of the hold; the `[pc-sampler]` rows give the clock) and build one table — a good subagent brief, with `grep -n "\[gs-transfer\]\|\[gs-upload\]\|\[gs-gl stats\] calls=" logs/run_A_<stamp>.log` as the verification command and "a markdown table, no judgement" as the contract:

| interval | fps | `transfer=` ms/s | flush ms/s | body ms/s | dirty_rows | decode | draw | flush_empty/real | decodes/s | invalidations/s | `upload=` ms/s | whole | chunked | identical | identical % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

  Then the arithmetic, by the controller and not the subagent:
  - **Cross-check the instrument**: `[gs-transfer] transfers=<n>/s` against `[gs-gl stats] transfer=<ms>/<count>`'s count over the same interval, within 10%; and `flush + body` against that line's `<ms>`, within 15%. If either disagrees by more, the trace is wired wrong and Step 4 is not done.
  - **Name the dominant phase**: the largest of `flush`'s three sub-terms and `body`, in ms/s, as a share of `transfer=`.
  - **Answer the identical-bytes question**: `identical / (whole + chunked)` as a percentage, and `whole / (whole + chunked)` — the second is the ceiling on what Task 2 may touch (R119).
  - **Test the suspected root**: is `invalidations/s` close to `fps x <the menu's texture count>` (the `[gs-gl stats]` line's `textures=` field is ~40)? If so, the cache is being thrown away every frame by the generation bump, and Task 2 removes the bump for identical uploads.

- [ ] **Step 7: The stop rule — apply it before Task 2, in writing.** Carried forward from spec §3 and R108, in this goal's terms:
  - **STOP** if **identical-bytes uploads are under 30% of the upload population** *and* **no single transfer phase carries more than half of `transfer=`**. Then there is no concentrated cost to remove: file the table in `docs/KNOWN.md` §1 as a proven row, write a `STOP:` line on Tasks 2, 3 and 4 here, and go straight to Task 5 with the goal reported as *measured and stopped by its own rule* — a result, not a failure.
  - **CONTINUE to Task 2** if identical-bytes uploads are **30% or more** of the population. The saving is then two-sided and both sides are named before the code is written: the swizzle those uploads pay for (`identical/s x shadow us`, in ms/s) and the decode storm their generation bumps cause (`decode` ms/s x the invalidation share).
  - **CONTINUE to Task 3 branch B only** if identical uploads are under 30% but one transfer phase carries more than half the column: skip Task 2, and Task 3's branch B addresses that phase directly.
  - Either way, record the verdict as a numbered ruling in the ledger with the two numbers it rests on.

```bash
git commit -m "docs: the menus' transfer column, split -- and how often the bytes repeat (Sprint 8 Goal 2b Task 1)

<the table>, from logs/run_A_<stamp>.log over <N> s of the login screen with PS2X_GS_UPLOAD_TRACE=1 and
PS2X_GS_STATS=1 (logs/s8_transfer_trace.sh, --only A --hold 60). transfer= is <F> ms/s of flushBatch
against <Y> ms/s of executeTransfer proper; inside the flush the dominant phase is <phase> at <Z> ms/s.
<I>% of uploads carry bytes the shadow already holds, <W>% arrive as a whole transfer in one call. The
texture cache is invalidated <V> times a second against <T> cached textures at <FPS> fps. The stop rule
<is not triggered: Task 2 proceeds | is triggered: Goal 2b stops here and the breakdown is the deliverable>.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  logs/s8_transfer_trace.sh docs/KNOWN.md
git push
```

---

## Task 2 — An identical upload does nothing (R108's "skip the swizzle for tiles whose bytes did not change")

*Precondition: Task 1 Step 7 said CONTINUE to Task 2. If it said STOP, this task carries a `STOP:` line and no code.*

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_identity.h` (the guard), `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_trace.h` (`skippedIdentical`), `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (:1873-1935 `executeUpload`), `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp`
- Read only, to confirm and record: `gs_gl_backend.h:148-149` (`gpuDirty`, `shadowStale`), `gs_gl_backend.cpp:2207` and `:3421` (where they are set), `:1714`, `:2501`, `:2550` (where they are cleared), `:309-310` of the header (`m_gpuDirtyPages` and its mutex), `gs_cpu_backend.cpp:1458-1560` (`UploadImage` writes the **swizzled** result through `GSMem::WriteSpan` — the shadow keeps no copy of the raw guest layout, which is why this compares a hash of the incoming bytes against a remembered hash and not a `memcmp` against shadow memory)
- Test: new MiniTest cases in `ps2_gs_tests.cpp`, context-free (the guard is arithmetic; the end-to-end behaviour is checked by the gate and by Task 4's launch)

**Interfaces:**
- `GsGlUploadIdentity::Cache::skippable(const Key&, uint64_t hash, uint64_t size, uint64_t generation, bool wholeTransfer, bool shadowSuspect) -> bool` — `matches(...) && wholeTransfer && !shadowSuspect`. One function so the rule lives in one place and one test pins it.
- `GSGlBackend::shadowSuspectForPages(uint32_t page, uint32_t pageCount) const -> bool` — true when any render target overlapping those pages has `gpuDirty` or `shadowStale` set, or when `m_gpuDirtyPages[p]` is set for any page in the span. **R118's guard**: if the GPU has drawn over the region since the shadow last matched it, the second identical upload is what puts the shadow's pixels back on the GPU, and skipping it would leave the GPU's newer pixels standing.
- `GsGlUploadTrace::Accum::skippedIdentical` + `GsGlUploadTrace::noteSkip(Accum&)`.
- Knob `PS2X_GS_NO_UPLOAD_SKIP=1` — the A/B: never skip, exactly as the tree behaves today. It is the bisect if a menu ever looks wrong, and it is what Task 4's before/after pair is measured against.

**Steps:**

- [ ] **Step 1: RED — the skip rule's cases, before `skippable` exists.** Add to `ps2_gs_tests.cpp` in the `GsGlUploadTrace` case block:

```cpp
        tc.Run("GsGlUploadIdentity skips a byte-identical whole-transfer upload and nothing else", [](TestCase &t)
        {
            GsGlUploadIdentity::Cache c;
            const GsGlUploadIdentity::Key k{0x0c0u, 10u, 64u, 48u, 16u, 16u, 0u};
            std::vector<uint8_t> bytes(1024u, 0x7Eu);
            const uint64_t h = GsGlUploadIdentity::hash64(bytes.data(), bytes.size());
            t.IsTrue(!c.skippable(k, h, 1024u, 7u, true, false), "an unseen rectangle is never skippable");
            c.store(k, h, 1024u, 7u, 1u);
            t.IsTrue(c.skippable(k, h, 1024u, 7u, true, false), "the same bytes at the same generation are skippable");

            // A one-byte change is not.
            bytes[900] ^= 0x01u;
            const uint64_t h2 = GsGlUploadIdentity::hash64(bytes.data(), bytes.size());
            t.IsTrue(!c.skippable(k, h2, 1024u, 7u, true, false), "one changed byte is not skippable");

            // A different rectangle with the same bytes is a different key.
            const GsGlUploadIdentity::Key k2{0x0c0u, 10u, 80u, 48u, 16u, 16u, 0u};
            t.IsTrue(!c.skippable(k2, h, 1024u, 7u, true, false), "the rectangle is part of the key");

            // R119: a chunk of a larger transfer is never skippable, however well it matches.
            t.IsTrue(!c.skippable(k, h, 1024u, 7u, false, false), "a partial upload is never skippable");

            // R118: the GPU drew over the region, so the shadow no longer describes what is on screen.
            t.IsTrue(!c.skippable(k, h, 1024u, 7u, true, true), "a gpu-dirty destination is never skippable");

            // Another writer stamped the pages: the remembered hash says nothing about the shadow now.
            t.IsTrue(!c.skippable(k, h, 1024u, 8u, true, false), "a newer shadow generation invalidates the hit");

            // A size change at the same key is a different upload even if the prefix hashes alike.
            t.IsTrue(!c.skippable(k, h, 2048u, 7u, true, false), "the byte count is part of the match");
        });

        tc.Run("GsGlUploadIdentity forgets everything when the shadow is reset, and stays bounded", [](TestCase &t)
        {
            GsGlUploadIdentity::Cache c;
            const GsGlUploadIdentity::Key k{0x0c0u, 10u, 0u, 0u, 16u, 16u, 0u};
            c.store(k, 42u, 1024u, 1u, 1u);
            t.IsTrue(c.skippable(k, 42u, 1024u, 1u, true, false), "stored and matching");
            c.clear();
            t.IsTrue(!c.skippable(k, 42u, 1024u, 1u, true, false), "a shadow reset forgets every hash");
            for (uint32_t i = 0; i < 6000u; ++i)
                c.store({0x0c0u, 10u, i % 640u, i / 640u, 16u, 16u, 0u}, i, 1024u, 1u, 500u + i);
            t.IsTrue(c.size() <= GsGlUploadIdentity::kMaxEntries,
                     "the cache never grows past its bound, whatever a pathological frame does");
        });

        tc.Run("GsGlUploadTrace counts a skipped upload apart from an identical one", [](TestCase &t)
        {
            GsGlUploadTrace::Accum a;
            for (int i = 0; i < 50; ++i)
            {
                GsGlUploadTrace::noteUploadShape(a, true, true);
                if (i < 40)
                    GsGlUploadTrace::noteSkip(a);   // ten were identical but guarded out (R118/R119)
            }
            t.Equals(static_cast<int>(a.uploadsIdentical), 50, "50 identical");
            t.Equals(static_cast<int>(a.skippedIdentical), 40, "40 of them actually skipped");
            const std::string line = GsGlUploadTrace::formatTransfer(a, 1000.0);
            t.IsTrue(line.find("identical=50") != std::string::npos, "identical is on the line");
            t.IsTrue(line.find("skipped=40") != std::string::npos, "and skipped, so the gap is visible");
        });
```

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8
```
  Expected failure: `error: no member named 'skippable' in 'GsGlUploadIdentity::Cache'` and `error: no member named 'noteSkip' in namespace 'GsGlUploadTrace'`.

- [ ] **Step 2: Implement `skippable`, `noteSkip` and `skippedIdentical`.** `skippable` is the three-clause conjunction above and nothing more; keep the rule in one expression so the next reader can see all of it at once.

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 && ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
```
  Expected: `Total Tests: B + 7`, `0 Failed`.

- [ ] **Step 3: RED — the backend's own behaviour, as a replay case.** This one needs the GS test harness's shadow-backend fixture rather than a GL context: it drives `GSGlBackend` through its public `BeginTransfer` / `UploadImage` entry points with the backend in its no-GL mode (the same construction the existing CPU-side GS cases use at `ps2_gs_tests.cpp:1526-1600`; read how that case builds its backend and copy it exactly rather than inventing a second way). Three assertions, and the third is the one that keeps R118 honest:

```cpp
        tc.Run("An identical upload marks nothing dirty and bumps no generation", [](TestCase &t)
        {
            // gs_gl_backend.cpp:1843-1848 -- markShadowPages does ++m_generation unconditionally, and
            // :3209-3222 throws away every cached texture whose pages carry a newer generation. That is
            // the chain this skip breaks, so the generation is what the test watches.
            GsTestBackend b;                                  // the fixture the console-replay case uses
            const auto tr = makeTransfer(/*dbp=*/0x0c0u, /*dbw=*/10u, /*dpsm=*/0u, /*dsax=*/0u, /*dsay=*/0u, 16u, 16u);
            std::vector<uint8_t> px(1024u, 0x33u);

            b.BeginTransfer(tr); b.UploadImage(px.data(), 1024u); b.drainForTest();
            const uint64_t genAfterFirst = b.shadowGenerationForTest();
            const size_t rectsAfterFirst = b.dirtyRectCountForTest(0x0c0u);

            b.BeginTransfer(tr); b.UploadImage(px.data(), 1024u); b.drainForTest();
            t.Equals(static_cast<int>(b.shadowGenerationForTest() - genAfterFirst), 0,
                     "the second, identical upload bumps no shadow generation");
            t.Equals(static_cast<int>(b.dirtyRectCountForTest(0x0c0u) - rectsAfterFirst), 0,
                     "and marks no new dirty rectangle, so nothing is re-uploaded to the GPU");
            t.Equals(static_cast<int>(b.skippedIdenticalForTest()), 1, "and it is counted as a skip");

            px[512] ^= 0xFFu;                                  // one byte
            b.BeginTransfer(tr); b.UploadImage(px.data(), 1024u); b.drainForTest();
            t.IsTrue(b.shadowGenerationForTest() > genAfterFirst,
                     "a one-byte change is not skipped: the generation moves");
            t.IsTrue(b.dirtyRectCountForTest(0x0c0u) > rectsAfterFirst,
                     "and the rectangle is marked dirty again");
        });

        tc.Run("A render target drawn over the region makes the next identical upload NOT skippable", [](TestCase &t)
        {
            // R118. gs_gl_backend.cpp:2207 and :3421 set shadowStale/gpuDirty when the GPU draws into a
            // target; :1714, :2501 and :2550 clear them when the shadow is brought back in line. While
            // the flag stands, the shadow no longer describes what is on screen, so re-uploading the
            // same bytes is exactly how the menu's pixels get put back -- and skipping it is the bug.
            GsTestBackend b;
            const auto tr = makeTransfer(0x0c0u, 10u, 0u, 0u, 0u, 16u, 16u);
            std::vector<uint8_t> px(1024u, 0x33u);
            b.BeginTransfer(tr); b.UploadImage(px.data(), 1024u); b.drainForTest();
            const size_t rectsBefore = b.dirtyRectCountForTest(0x0c0u);

            b.markRenderTargetGpuDirtyForTest(0x0c0u);         // a draw landed on those pages
            b.BeginTransfer(tr); b.UploadImage(px.data(), 1024u); b.drainForTest();
            t.IsTrue(b.dirtyRectCountForTest(0x0c0u) > rectsBefore,
                     "the identical upload still marks its rectangle: the shadow must be put back on the GPU");
            t.Equals(static_cast<int>(b.skippedIdenticalForTest()), 0, "and nothing was skipped");
        });
```
  If the fixture does not expose `shadowGenerationForTest` / `dirtyRectCountForTest` / `markRenderTargetGpuDirtyForTest` / `skippedIdenticalForTest`, add them as `#if defined(PS2X_TESTING)`-free plain const accessors on `GSGlBackend` — they read existing members and add no branch to a hot path. **Do not** add a test-only code path inside `executeUpload`.

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 && ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
```
  Expected failure, before the skip exists: `[Failed] the second, identical upload bumps no shadow generation: expected 0, got 1`.

- [ ] **Step 4: Implement the skip in `executeUpload` (`gs_gl_backend.cpp:1873-1935`).** Exactly one new early branch, placed **before** `m_shadow->UploadImage`:

  1. Read the knob once: `static const bool s_noSkip = std::getenv("PS2X_GS_NO_UPLOAD_SKIP") != nullptr;`.
  2. Build the `Key` from `m_currentTransfer`, compute `page`/`span` with the same `pageSpan` call the function already makes, compute `generation` as the max `m_shadowPageGeneration[p]` over the span, compute `hash64(data, size)`.
  3. `const bool whole = (m_uploadReceivedBytes == 0u && m_uploadExpectedBytes != 0u && size == m_uploadExpectedBytes);`
  4. `if (!s_noSkip && m_uploadIdentity.skippable(key, hash, size, generation, whole, shadowSuspectForPages(page, span)))` → `m_uploadIdentity.touch(key, m_frameCounter); m_uploadReceivedBytes = 0u;` (the transfer is complete, so the chunk counter resets exactly as the completed-rectangle branch does at `:1929`), `if (s_uploadTrace) { GsGlUploadTrace::noteUploadShape(...); GsGlUploadTrace::noteSkip(g_uploadTrace); }`, `return;`.
  5. Otherwise fall through unchanged, and after `markShadowPages` store the new hash with the **post-mark** generation.
  6. `shadowSuspectForPages` walks `m_renderTargets` for overlap (the same page-span overlap test `refreshRenderTargetsFromShadow` uses at `:1946-1951`) and returns true on any `gpuDirty || shadowStale`; it also takes `m_dirtyMutex` and checks `m_gpuDirtyPages[p]` across the span.

  The hash is the only cost added to the non-skipped path. It is a byte-at-a-time FNV over 1-64 KB; Step 5 measures it and the commit states the number.

```bash
cmake --build third_party/ps2recomp/build-clang --target ps2x_tests -j 8 && ( cd third_party/ps2recomp/build-clang/ps2xTest && ./ps2x_tests.exe ) 2>&1 | grep -E "Failed\]|Total Tests"
```
  Expected: `Total Tests: B + 9`, `0 Failed`.

- [ ] **Step 5: The cost of the hash, and the suite, and the gate.** The hash runs on every upload that is not skipped, so it must be cheaper than the swizzle it guards. Read it from the `[gs-upload]` line's `shadow=` term in Task 4's run against Task 1's: the delta is the hash. **Before** Task 4 exists, bound it on the host with the suite's own numbers — a MiniTest micro-case is not a benchmark, so state the bound instead: FNV-1a over 1 KB is a 1024-iteration loop with one xor and one multiply, against a `GSMem::WriteSpan` swizzle measured at 8.1-10.1 us for the same kilobyte. If Task 4's `shadow=` per-upload figure rises by more than 1.0 us, say so and replace the byte loop with an 8-bytes-at-a-time variant under the same tests.

```bash
"C:/Program Files/Git/bin/bash.exe" scripts/loop_lock.sh run main --purpose "s8 goal2b task2 suite" -- ./build.sh test
python -m tools_py.parity.gate --only title,transition,mission --stamp s8_g2b_skip
```
  Expected: `./build.sh test` exit 0; gate **3/3**, and the title stage's score in its usual band (23/23 at the Goal 2 close-out — read the previous stamp's `summary.txt` and compare, do not assume). The console-replay case in `ps2x_tests` is the pixel-identity check and is already in the suite run.

- [ ] **Step 6: Commit.**

```bash
git commit -m "perf(gs): an upload whose bytes the shadow already holds does nothing (Sprint 8 Goal 2b Task 2)

Task 1 measured <I>% of the login screen's uploads carrying bytes the shadow already held, re-written
every frame into one destination texture. Each of them paid the full CPU swizzle (8.1-10.1 us a
kilobyte) and then bumped m_generation in markShadowPages (gs_gl_backend.cpp:1843-1848), which makes
resolveTexture's gate (:3209-3222) delete the cached texture and decode it again into a fresh
glTexImage2D (:3105-3122) at the next draw -- billed to transfer=, because a transfer is what
interrupts the draw batch (:1535-1538).

executeUpload now hashes the incoming bytes (FNV-1a 64) against a bounded rectangle-keyed cache and,
on a match, returns without swizzling, without marking a page, without bumping a generation and
without pushing a dirty rectangle. Three guards, each with its own case:
  R118 -- never skip when a render target overlapping the pages is gpuDirty or shadowStale
          (gs_gl_backend.h:148-149, set at :2207 and :3421): the shadow no longer describes what is on
          screen, and the re-upload is exactly what puts the menu's pixels back.
  R119 -- never skip a chunk of a larger transfer: gs_frontend.cpp:938-943 delivers one IMAGE tag per
          call and a big rectangle can span several, and half a skipped rectangle is a corrupt one.
  The remembered hash carries the shadow generation it was taken at, so any other writer touching the
  pages invalidates it.
PS2X_GS_NO_UPLOAD_SKIP=1 restores the old behaviour for an A/B or a bisect.

Five MiniTest cases: the rule's whole truth table, the cache's bound and reset, the trace's
identical-vs-skipped pair, and two replay cases on the backend itself -- the same upload twice marks
no second rectangle and moves no generation, a one-byte change does both, and a draw over the region
makes the next identical upload NOT skippable. Suite <B+9>, 0 failed. Gate 3/3 (s8_g2b_skip), title
stage <N>/23.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_identity.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_upload_trace.h \
  third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h \
  third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp \
  third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp
git push
```

---

## Task 3 — The second term, whichever Task 1 named (both branches written; one is executed)

*Which branch runs is decided by Task 1 Step 6's table and recorded as a ruling before a line is written. The other branch gets a one-line `not run:` reason in Task 5 Step 5.*

### Branch A — repeated identical local transfers

**Runs when** Task 1's table shows `dir2` (local->local) transfers at more than 10% of the transfer count **and** their destinations repeat frame to frame (the same `[gs-transfer]` `dir2` count every interval, against one or two destination pages).

**Files:** modify `gs_gl_backend.cpp:1850-1870` (`executeTransfer`), `gs_gl_upload_identity.h`, `ps2_gs_tests.cpp`.

**Interfaces:** the same `Cache`, keyed on the *source* rectangle as well — `GsGlUploadIdentity::LocalKey { Key dst; uint32_t sbp, sbw, ssax, ssay, spsm; }` — because a local->local move carries no bytes of its own and its identity is "this source rectangle, unchanged, into this destination rectangle, unchanged".

**Steps:**
- [ ] **A1: RED.** A case asserting that two identical `direction == 2` transfers, with no intervening write to either the source or the destination pages, leave the second one marking no pages and pushing no dirty rectangle — and that a write to the **source** pages between them makes the second one run in full. Expected failure before the change: `[Failed] the second identical local copy marks no pages: expected 0, got 1`.
- [ ] **A2: Implement.** In `executeTransfer`, before `m_shadow->BeginTransfer(command)`, when `command.direction == 2u`: compute the source rectangle's generation (max `m_shadowPageGeneration` over its page span) and the destination's; if both equal what the cache remembers for this `LocalKey`, skip `m_shadow->BeginTransfer`, `markShadowPages` and `refreshRenderTargetsFromShadow`, and still set `m_currentTransfer` and the byte counters (the frontend's protocol does not change). Guard with `shadowSuspectForPages` on the destination span, same as Task 2. Knob: the same `PS2X_GS_NO_UPLOAD_SKIP=1`.
- [ ] **A3: Suite + gate.** `./build.sh test` exit 0; gate 3/3 stamped `s8_g2b_local`. Commit with the pathspecs of the three files and the trailer.

### Branch B — the flush is the column

**Runs when** Task 1's table shows `flush` carrying more than half of `transfer=` and `dir2` under 10% — i.e. the milliseconds are the draw batch a transfer interrupted, not a transfer.

**The measurement that decides what B does:** re-read the `[gs-transfer]` line **after Task 2** (Task 4's run gives it for free). Task 2 removes the generation bumps, so `invalidations/s` and `decode` ms/s should collapse on their own. Two sub-cases, and the ruling says which:

- [ ] **B1 (decode was the flush): nothing further is built.** If `decode` was the dominant sub-term and Task 2 drops it below a fifth of `transfer=`, branch B is *satisfied by Task 2* and this task closes with a ruling saying so and the two numbers. This is the expected outcome given `markShadowPages` bumps unconditionally, and closing without new code is a result, not a shortfall.
- [ ] **B2 (`dirty_rows` or `draw` was the flush, or decode survives Task 2): stop the needless flush.** `flushBatch()` at `:1535` runs before *every* transfer, including the ~8000 a second whose destination has nothing to do with the pending batch. Add, under a RED that counts flushes: a transfer whose destination page span intersects neither the pending batch's render target (`m_batchRt->fbp` and its page span) nor the pending batch's bound texture pages does not need the batch drained first, so `flushBatch()` is not called for it.
  - **RED**: a case that queues a textured batch, replays a transfer to an unrelated page span, and asserts the batch is still pending (`flushesEmpty` unchanged, the draw not yet issued); then replays a transfer into the batch's own target and asserts the flush happened. Expected failure before the change: `[Failed] an unrelated transfer does not drain the pending batch: expected 0 flushes, got 1`.
  - **The correctness argument, which must be in the commit**: the flush exists so that a transfer cannot change VRAM under a draw that has already been recorded but not issued. If the transfer's pages touch neither the target being drawn into nor the texture being sampled, that ordering is not observable. If it touches either, the flush stays. **When in doubt, flush** — the test's third assertion is an overlap case that must still flush.
  - Suite + gate 3/3 stamped `s8_g2b_flush`; commit with explicit pathspecs and the trailer.

---

## Task 4 — The bar

**Files:**
- Create: `logs/s8_menu_bar2.sh`, `logs/parity/s8_menu_bar2/`
- Read only, to confirm and record: `logs/s7_freeze_loaded.sh` (the load generator's shape, and **why the drafted `Start-Job` recipe does not survive** — four `powershell -c "while($true){}"` processes started by pid and killed by pid), `tools_py/parity/freeze_trace.py:80-81` (the freeze fields' names), `third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_freeze_fields.h:45` (the `[pc-sampler]` line that carries them)
- Test: none new; the bar is a measurement and the gate plus the console-replay case are the regression net

**Interfaces:** the six numbers, each with the command that reads it —
- **`upload=` + `transfer=` under 60 ms/s on the login screen**: the `[gs-gl stats] calls=… transfer=<ms>/<count> upload=<ms>/<count>` columns, summed, mean over the login-screen window. (Before: 42-80 + 157-277.)
- **55+ fps under a four-core spinning load**: `[gs-gl stats] elapsed=<ms> (<fps> fps)` — the mean over the window ≥ 55.0.
- **`bp_pending` under 2 in every sampler row**: `python -m tools_py.parity.freeze_trace logs/run_A_<stamp>.log`, `bp_pending` **max** over the window ≤ 1 (the failing launches sat at 4 with `bp_waiters=1`).
- **Gate 3/3** and **the title stage's score unchanged** against the previous stamp's `summary.txt`.
- **The GS suite's console-replay case still pixel-identical**: it is in `./build.sh test`, which must be exit 0.
- Plus the standing one from `docs/CURRENT_SPRINT.md`: **`pcm_underruns` stays 0** on the `[audio-trace]` line.

**Steps:**

- [ ] **Step 1: Write `logs/s8_menu_bar2.sh` — the login-only path with `s7_freeze_loaded.sh`'s load generator.**

```bash
#!/usr/bin/env bash
# Sprint 8 Goal 2b Task 4: the bar. The LOGIN screen only (online_match_ours --only A), held 60 s, with
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
python -m tools_py.parity.online_match_ours --only A --hold 60 --out logs/parity/s8_menu_bar2
rc=$?
kill "${LOAD_PIDS[@]}" 2>/dev/null
wait "${LOAD_PIDS[@]}" 2>/dev/null
taskkill //F //IM socom2.exe >/dev/null 2>&1
echo "done $rc" > logs/s8_menu_bar2.done
exit $rc
```

```bash
chmod +x logs/s8_menu_bar2.sh
bash scripts/check_quiet_gate.sh
scripts/run_detached.sh --owner gate --purpose launch logs/s8_menu_bar2.sh logs/s8_menu_bar2.marker
cat logs/s8_menu_bar2.marker 2>/dev/null || echo running
```

- [ ] **Step 2: Read the numbers, and read them over the login-screen window only.** The window runs from the login screen appearing to the end of the hold — not the boot loads, which legitimately reach 35-46k uploads/s and are not what this goal is about (R110, carried forward). Mark it from the harness's own screenshots and timestamps in `logs/parity/s8_menu_bar2/`, and state its start and end seconds in the commit.

```bash
grep -n "\[gs-gl stats\] elapsed=\|\[gs-gl stats\] calls=" logs/run_A_<stamp>.log | tail -60
grep -n "\[gs-upload\]\|\[gs-transfer\]" logs/run_A_<stamp>.log | tail -60
python -m tools_py.parity.freeze_trace logs/run_A_<stamp>.log
grep -c "pcm_underruns=[1-9]" logs/run_A_<stamp>.log     # expected: 0
```

- [ ] **Step 3: The `bp_pending` sweep — every row, not the mean.** The KNOWN row's failure is *four launches in ten*, and the symptom is a maximum: one row at `bp_pending=4 bp_waiters=1` fails the bar even if the mean is 0.2. A subagent brief suits this: "print every `[pc-sampler]` row between seconds A and B with `bp_pending`, `bp_waiters` and `bp_wait_ms`, then the max of each; verification command `python -m tools_py.parity.freeze_trace <log>`; no judgement."

- [ ] **Step 4: If a bar is missed, say which and stop rather than tune.** The honest outcomes, in order of preference, each a ruling:
  - **All six met** → Step 5.
  - **The ms/s bar met but fps short of 55 under load** → the remaining cost is not the upload or transfer path. Record the new dominant term from the same run's two trace lines and file it. This is a partial and is reported as one; the sprint does not get a second attempt at a different subsystem under this goal's name.
  - **`skipped=0` or near it** → the identical-bytes hypothesis held in Task 1's counting run and not under load, which means the guard is firing. Print which guard: add nothing, read `identical` against `skipped` on the `[gs-transfer]` line — the gap is exactly R118 plus R119. File that, and close the goal as measured.
  - **A menu renders wrong, or the title score drops** → `PS2X_GS_NO_UPLOAD_SKIP=1` is the immediate bisect and R118's guard is where the bug is. This is the one outcome that reverts.

- [ ] **Step 5: Gate 3/3 and commit the bar.**

```bash
python -m tools_py.parity.gate --only title,transition,mission --stamp s8_g2b_bar
```

```bash
git commit -m "test(gs): the menus' bar, measured under a four-core load (Sprint 8 Goal 2b Task 4)

logs/s8_menu_bar2.sh: the login screen only (online_match_ours --only A --hold 60) with four spinning
host processes around it -- the same load generator shape as logs/s7_freeze_loaded.sh, and the same
reason its literal Start-Job recipe is not used.

Over the login-screen window (t=<A>..<B> s of logs/run_A_<stamp>.log):
  upload= + transfer=  <U> + <T> = <S> ms/s      (bar: under 60; was 42-80 + 157-277)
  fps                  <X> mean, <Y> min         (bar: 55 mean under load)
  bp_pending           max <P>, bp_waiters <W>   (bar: under 2; the failing launches sat at 4/1)
  identical / skipped  <I> / <K> per interval    (the gap is R118's and R119's guards, by design)
  decodes/s            <D>, invalidations/s <V>  (Task 1's run: <D0> / <V0>)
  pcm_underruns        <N>                       (bar: 0)
Gate 3/3 (s8_g2b_bar), title stage <M>/23, the console-replay case pixel-identical in ./build.sh test.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- logs/s8_menu_bar2.sh
git push
```

---

## Task 5 — Close-out for Goal 2b

**Files:**
- Modify: `docs/KNOWN.md` (§1 Proven; §3 Retracted if a hypothesis died), `docs/STATUS.md` (the current-state bullet and a dated entry), `docs/CURRENT_SPRINT.md` (the Sprint 8 block and the pointer to the next goal), `docs/superpowers/plans/2026-09-18-sprint-8-menu-render-cost.md` (its Task 4 close-out gains the pointer to this plan's result), `docs/superpowers/plans/2026-09-19-sprint-8-menu-cost-2b.md` (this file: tick the boxes; any box left open carries a one-line reason or a `STOP:`)

**Steps:**

- [ ] **Step 1: `docs/KNOWN.md` §1 — the rows, each naming its artefact.** Up to three, written only with numbers actually measured:
  - **What the `transfer=` column is** — that it is `flushBatch` + `executeTransfer` (`gs_gl_backend.cpp:1402` takes the clock before the switch; `:1535-1538` is two statements), that `executeTransfer`'s own body moves no pixels for a host->local transfer (`gs_cpu_backend.cpp:1441-1456`), and the phase split with its numbers. Artefact: `logs/run_A_<stamp>.log`'s `[gs-transfer]` lines, `logs/s8_transfer_trace.sh`.
  - **The menu atlas is re-uploaded unchanged, and that is what cost the frame** — `<I>%` identical uploads, the generation bump at `:1843-1848` invalidating the texture cache at `:3209-3222` `<V>` times a second, and the after-numbers. Artefact: the two runs' `[gs-upload]` / `[gs-transfer]` pairs and the five MiniTest cases.
  - **The login screen under a four-core load: `<X>` fps, `bp_pending` max `<P>`, `upload=`+`transfer=` `<S>` ms/s** — artefact: `logs/run_A_<stamp>.log` over `t=<A>..<B>`, `logs/s8_menu_bar2.sh`, gate `s8_g2b_bar` 3/3.
- [ ] **Step 2: Rewrite §1:98's experiment sentence.** It currently proposes exactly this goal's experiment ("the same per-term split inside executeTransfer, then skip the swizzle for tiles whose bytes did not change… Sprint 8 Goal 2b"). Replace it with the answer and the numbers, and move the login-screen row to **proven** if the bar was met. Anything believed and then killed by this measurement goes to **§3 Retracted** in the file's own shape — believed, then killed, with the artefact.
- [ ] **Step 3: `docs/STATUS.md`.** Replace the current-state bullet's Goal 2 sentence (it currently reads "Goal 2 stopped by its measurement (R108: the menus' cost is CPU-side conversion and the transfer path)") with the Goal 2b verdict in one sentence, and add a dated entry in the file's own voice: what landed, the bars and their numbers, and what the next goal is.
- [ ] **Step 4: `docs/CURRENT_SPRINT.md`'s Sprint 8 block.** Mark the menu-cost item done or partly done with its numbers, name this plan as the one that carried it, and move the pointer on.
- [ ] **Step 5: Tick this plan's boxes, and leave a reason on every one that stays open.** A box with neither a tick nor a reason is the failure mode the Sprint 6 close-out audit found; a `STOP:` line citing Task 1 Step 7's verdict, or a `not run: branch <A|B>` on Task 3's other branch, is a valid reason. Add one line to the Goal 2 plan's Task 4 pointing at this plan's result, so the R108 stop reads as a handover and not a dead end.
- [ ] **Step 6: Commit.**

```bash
git commit -m "docs: Sprint 8 Goal 2b closed -- the menus' cost at its measured root

KNOWN gains what the transfer= column actually is (flushBatch + executeTransfer, the clock taken at
executeCommands:1402 before the switch; executeTransfer's own body moves no pixels for the host->local
transfers a menu sends, gs_cpu_backend.cpp:1441-1456), the phase split that followed, and the root it
exposed: the game re-uploads the menu atlas unchanged every frame, each upload bumping m_generation in
markShadowPages (:1843-1848) and throwing away every cached texture overlapping the pages (:3209-3222)
for a full decode and glTexImage2D at the next draw. An identical upload is now a no-op under three
guards (R118 gpu-dirty, R119 whole-transfer, and the remembered shadow generation). The login screen
under a four-core load: <X> fps, bp_pending max <P>, upload=+transfer= <S> ms/s against a bar of 60.
Section 1's login-screen row loses its experiment sentence and carries the answer. STATUS and
CURRENT_SPRINT carry the verdict and move the pointer on.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" -- \
  docs/KNOWN.md docs/STATUS.md docs/CURRENT_SPRINT.md \
  docs/superpowers/plans/2026-09-18-sprint-8-menu-render-cost.md \
  docs/superpowers/plans/2026-09-19-sprint-8-menu-cost-2b.md
git push
```

---

## Rulings made on the owner's behalf

R117 onward; see the Goal 2 plan for R107-R110, the hosted-server and voice plans for R111-R116.

- **R117** (Task 1): **`[gs-transfer]` is a second line under the existing knob, not a widening of `[gs-upload]` or of `[gs-gl stats]`.** R107 made this call once for the upload trace and the reasoning has only got stronger: Goal 2's tables were read out of `[gs-upload]`'s exact field order, and Task 4 compares a before-run against an after-run by `grep`. A new line under the same `PS2X_GS_UPLOAD_TRACE` knob, printed inside the same 60-call block, keeps both readings working and keeps the two lines about the same interval. *Cost if wrong:* one more line in a traced log, and a reader matches three tags instead of two — which is what the `elapsed=` field on all three is for.

- **R118** (Task 2): **an identical upload is skipped only when no render target overlapping its pages is `gpuDirty` or `shadowStale`.** The tempting version — "the bytes match, so the write is redundant" — is true of the *shadow* and false of the *GPU*. `refreshRenderTargetsFromShadow` exists because an upload's job is not only to write shadow VRAM but to push those pixels back onto a GPU texture the draw stream may have painted over since (`gs_gl_backend.cpp:2207` and `:3421` set the flags; `:1714`, `:2501` and `:2550` clear them when the two are brought back in line). Skipping across a GPU draw is the 2026-09-09 movie-strip bug's mirror image: instead of stale shadow rows resurrecting over newer GPU pixels, newer GPU pixels would survive where the game meant to repaint. The guard costs a walk of `m_renderTargets` (there are two on this screen) and a page-span check. *Cost if wrong in the other direction:* fewer skips on screens where something is being drawn into the atlas's pages, which the `identical` vs `skipped` gap on the trace line makes visible rather than mysterious.

- **R119** (Task 2): **only an upload that delivers the whole transfer in one call is a skip candidate.** `gs_frontend.cpp:938-943` turns one IMAGE GIF tag into one `UploadImage`, and `executeUpload` accumulates `m_uploadReceivedBytes` against `m_uploadExpectedBytes` precisely because a large rectangle can span several tags. A per-chunk hash cannot decide the rectangle's identity, and skipping chunk 1 before seeing chunk 2 differ leaves a half-written rectangle — a corruption that would show as a torn menu and bisect to nothing. The whole-transfer test is two comparisons the function already has the operands for. *Cost if wrong:* the chunked share of the population (Task 1 counts it) is never skipped, so the win is smaller than the identical-bytes percentage suggests — which is why the trace prints `whole`, `chunked`, `identical` and `skipped` as four separate numbers.

- **R120** (Task 2): **the identity check is a hash of the incoming bytes, not a `memcmp` against the shadow.** The brief offers both. The tree decides it: `GSCpuBackend::UploadImage` writes through `GSMem::WriteSpan` into **swizzled** VRAM (`gs_cpu_backend.cpp:1458-1560`), so the shadow keeps no copy of the raw guest layout to compare against, and a comparison in the swizzled domain would mean running the address arithmetic for every pixel — the very cost the skip exists to avoid. A 64-bit FNV-1a over the packet plus a remembered shadow generation is one linear pass with no addressing at all. *Cost if wrong:* a 64-bit hash collision would skip an upload that differs, showing as one stale menu rectangle; at ~8000 uploads a second over a 60 s screen that is ~5x10^5 comparisons against a 1.8x10^19 space, and `PS2X_GS_NO_UPLOAD_SKIP=1` distinguishes it from any other menu defect in one run.

- **R121** (Task 3): **Task 3's content is chosen by Task 1's table, not by this plan, and the branch not taken is recorded as such.** Both branches are written out here with their REDs and their correctness arguments, because a task written as "then fix whatever Task 1 found" is not a plan. Branch A (identical local->local transfers) and branch B (the flush is the column, with B1 "Task 2 already fixed it" and B2 "stop the needless flush") cover the outcomes Task 1 can produce; if it produces a third, Task 3 becomes a ruling and a one-task addendum rather than an improvisation inside this file. *Cost if wrong:* one branch's prose is never executed, which costs reading time and buys the executing model a decision it does not have to make alone.

## Self-review

- **Goal coverage.** R108's closing sentence names two experiments and both are tasks: *"a per-term trace of executeTransfer"* → Task 1 (the `[gs-transfer]` line, split by phase and direction, cross-checked against `[gs-gl stats] transfer=`, with one driven `--only A --hold 60` launch); *"a swizzle that skips unchanged tiles"* → Task 2 (the hash, the three guards, five cases). The brief's third question — *"is it the SAME bytes every frame?"* — is Task 1's `identical` counter and is what the stop rule turns on. Task 3 carries the second term conditionally; Task 4 is the bar, with all six numbers including the two the brief added (the title stage's score and the console-replay case's pixel identity); Task 5 closes the goal either way.
- **The stop rule is carried twice, deliberately.** As a pre-condition in Task 1 Step 7 (identical under 30% and no dominant phase → file and stop before changing anything) and as a post-condition in Task 4 Step 4 (nothing moved → file and close). Task 5 runs in both cases.
- **Launch budget.** Three launches plus at most two gate runs: `s8_transfer_trace` (Task 1 Step 5), `s8_menu_bar2` (Task 4 Step 1), gate `s8_g2b_bar`; plus gate `s8_g2b_skip` after Task 2 (required by the standing rule that the gate passes before any commit touching `ps2xRuntime/src/`) and, only if Task 3 lands code, `s8_g2b_local` or `s8_g2b_flush`. Runtime builds go through `run_detached.sh` with a marker and are not launches.
- **Placeholder scan.** Clean: no `TBD`, no "handle edge cases", no "similar to Task N". Every value left to be filled is a **measurement**, marked `<X>`, `<I>`, `<A>..<B>`, `<stamp>`, or the suite baseline `B`, inside a commit-message or KNOWN template, replaced by the run or the build that precedes the commit. `B` is a baseline rather than a literal on purpose: Goals 3 and 5 are adding cases to the same binary in the same checkout, and a hard-coded 556 would be wrong by the time this plan is executed — the Handoff notes say to record it in the ledger first. Five implementation choices the goal left open are named as rulings: the second trace line (R117), the gpu-dirty guard (R118), the whole-transfer rule (R119), hash-not-memcmp (R120), and the conditional Task 3 (R121).
- **Type consistency.** `GsGlUploadIdentity::hash64(const uint8_t*, size_t) -> uint64_t`, `Key{dbp,dbw,dsax,dsay,rrw,rrh,dpsm}`, `KeyHash`, `Entry{hash,size,generation,lastUse}`, `kMaxEntries`, `Cache::matches/skippable/store/touch/clear/size`, `LocalKey{dst,sbp,sbw,ssax,ssay,spsm}` (branch A only); `GsGlUploadTrace::noteTransfer(Accum&, uint32_t, double, double)`, `noteFlushPhases(Accum&, double, double, double, bool)`, `noteDecode(Accum&, bool)`, `noteUploadShape(Accum&, bool, bool)`, `noteSkip(Accum&)`, `formatTransfer(const Accum&, double) -> std::string`, and the existing `bucketFor`/`noteUpload`/`noteRecord`/`noteRect`/`noteGlUpload`/`noteDst`/`reset`/`format` unchanged; `GSGlBackend::shadowSuspectForPages(uint32_t, uint32_t) const -> bool`. Each is used with one signature everywhere it appears. Knobs: `PS2X_GS_UPLOAD_TRACE` (existing), `PS2X_GS_NO_UPLOAD_SKIP` (new), and the existing `PS2X_GS_STATS`, `PS2X_GS_TRACE_PAGES`, `PS2X_PC_SAMPLER`, `PS2X_AUDIO_TRACE`.
- **What the tree contradicted in the brief, and what this plan does instead.** One, and it is load-bearing. The brief asks what `executeTransfer` does per call to be worth 157-203 ms/s — *"host->local transfers? local->local VRAM moves? readbacks?"* — and the answer from the code is **none of the three**. `executeCommands` takes its clock at `gs_gl_backend.cpp:1402`, before the dispatch switch; the `CmdType::BeginTransfer` case at `:1535-1538` is `flushBatch();` **then** `executeTransfer(cmd.transfer);`, so the `transfer=` column is the pending draw batch being drained, charged to the command that interrupted it. `executeTransfer`'s own body (`:1850-1870`) moves no pixels for the host->local transfers a menu sends: `GSCpuBackend::BeginTransfer` (`gs_cpu_backend.cpp:1441-1456`) only copies the command into `m_transferState` unless `direction` is 1 or 2. This plan therefore instruments the flush and the body separately, and splits the flush into `refreshDirtyRows`, texture decode and the draw, rather than timing a function that will report a few microseconds and leave the column a mystery. Two smaller notes, neither a contradiction: the brief's "`transfer=` (executeTransfer)" gloss comes from `docs/KNOWN.md` §1:98, which Task 5 Step 2 corrects in the same sentence it rewrites; and the brief's "memcmp on the raw guest layout if the shadow keeps it" is answered by the tree with "it does not" — `UploadImage` writes swizzled through `GSMem::WriteSpan`, which is R120.
- **The hypothesis this plan is built on is stated so it can be killed.** The chain — identical bytes → `markShadowPages` bumps `m_generation` unconditionally (`:1843-1848`) → `resolveTexture`'s gate erases the cached texture (`:3209-3222`) → a full decode and `glTexImage2D` (`:3105-3122`) inside the flush charged to `transfer=` — is the plan's reason for existing, and Task 1 Step 6's last bullet is the test that kills it: if `invalidations/s` is *not* close to `fps x textures`, the cache is not being thrown away every frame and Task 2's second saving does not exist. The first saving (the swizzle) survives either way, which is why Task 2 is not conditional on that bullet but Task 3 branch B1 is.
- **Owner gate.** Goal 2b is autonomous end to end under the owner's standing instruction of 2026-09-17: three host launches, no second machine, no owner check. The judgement that could want an owner is R118's trade-off (fewer skips against never leaving a GPU-painted region unrepainted), and it is decided the safe way, against the goal's own performance interest, because the alternative is a rendering defect on exactly the screens this goal is meant to fix.
