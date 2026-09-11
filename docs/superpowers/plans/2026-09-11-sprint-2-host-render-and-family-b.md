# Sprint 2 — Host-Resolution Drawing, Family B/C, Gate Hardening: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the native VU1 dispatcher hand the GS backend sub-pixel host-space triangles directly (behind a knob, proven equivalent, then at 2x), finish the dispatcher natively (family B and C command lists), and make the gates deterministic and runnable on a fresh clone.

**Architecture:** A public `GS::submitHostTriangle` fills the draw state from the GS's live context exactly as the GIF path does and submits the caller's three float vertices; the native packet builder (`0x1780`) uses it when `PS2X_VU1_HOST_DRAW=1` and still emits GIF packets otherwise, so the existing goldens keep proving the GIF path. An offline VRAM-diff mode in `vu1_replay` proves the two paths draw the same pixels; the gate proves it in-game. Family B/C follow Sprint 1's recipe: research addendum, one handler per commit, verified on the mission dump sets. Gate hardening adds captures during the drive script's settle waits, committed small fixtures, and a determinism check on the unit suite.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh`), CMake/Ninja, MiniTest, Python 3 (numpy, Pillow), Git Bash.

**Spec:** `docs/superpowers/specs/2026-09-11-sprint-2-host-render-and-family-b-design.md`

## Global Constraints

- Repo root `C:\projects\socom_pc`, remote `github.com/Scotho/socom-unzipped`, work on a branch `sprint-2` off `develop`; commit from the root with explicit paths (never `git add -A`), leave `server/config/simulated.db` unstaged, push after each commit. Trailers: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: <session url>`.
- Builds and game runs are serial under `scripts/loop_lock.sh take|wait|release <owner>`. `./build.sh runtime` (writes `dist/socom2.exe`) needs the lock; `cmake --build third_party/ps2recomp/build-clang --target vu1_replay|ps2x_tests` does not. Long game runs go detached (bash script under `logs/`, PowerShell `Start-Process bash.exe`, poll a `.done` marker). Always `./build.sh runtime` before `python -m tools_py.parity.gate`.
- Before any commit touching `third_party/ps2recomp/` or `recomp/`: `./build.sh test` exit 0 and the gate green.
- **Frozen:** VU1/VU0 interpreter speed, scheduler batching, GS/GL caching and upload paths for performance. Accuracy fixes the gate finds are allowed.
- Native VU1 float maths goes through the `ps2_vu1_ops.h` helpers; the GIF path of every native handler must stay bit-exact (`vu1_replay --verify --regs all` on `tests/fixtures/vu1/*` and the exact goldens of `logs/vu1dump{2,3,4}` 0x1b50 runs).
- Shell and Python files stay LF; C++ edits via the Edit tool or a Python patch script.
- Header edits to `ps2_vu1.h`, `gs_frontend.h`, `gs_types.h` cost a ~10-minute rebuild; batch them per task.

---

## File map

| Path | Responsibility |
|---|---|
| `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_frontend.h`, `src/lib/gs/gs_frontend.cpp` | `GS::submitHostTriangle` public entry, state fill shared with `buildDrawBatch` |
| `third_party/ps2recomp/ps2xRuntime/include/runtime/ps2_vu1.h`, `src/lib/vu/ps2_vu1_core.cpp` | `VU1Interpreter::activeGs()` public accessor |
| `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp` | host-triangle unit tests |
| `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp` | host-draw path in the `0x28` packet builder; family B/C handlers; per-handler clamps |
| `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` | `--vram-diff` equivalence mode, `--host-draw` |
| `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (+ `.h`) | render-target scale (Task 3b, only if the spike says so) |
| `docs/research/13-vu1-family-b-world-objects.md` | (new) family B/C handler descriptions |
| `docs/research/14-gs-render-target-scale-spike.md` | (new) every 1:1 assumption in the GL backend, decision |
| `tools_py/parity/drive.py`, `tools_py/parity/black_rows.py`, `tools_py/parity/gate.py`, `tools_py/tests/test_gate.py` | captures during settle waits; fixtures; floor back to 5 |
| `tests/fixtures/gate/{title,transition,mission}/` | (new) committed gate fixtures |
| `build.sh` | `test` runs the unit suite three times when `PS2X_TEST_REPEAT=3` |
| `docs/STATUS.md`, `docs/LOOP_PROMPT.md`, `README.md` | knobs and state |

---

### Task 1: `GS::submitHostTriangle` and `VU1Interpreter::activeGs()`

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_frontend.h` (public section, lines 99-156), `src/lib/gs/gs_frontend.cpp` (next to `buildDrawBatch` at ~1785 and `vertexKick` at ~1616)
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/ps2_vu1.h` (public section), `src/lib/vu/ps2_vu1_core.cpp`
- Test: `third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp`

**Interfaces:**
- Consumes: `GSVertex{float x,y; double z; uint8_t r,g,b,a; float q,s,t; uint16_t u,v; uint8_t fog}` (gs_types.h:103-118), `GSPrimReg` (195-206), `GSPrimitiveBatch` (252-257), `GS::buildDrawBatch(int) const` (gs_frontend.cpp:1785-1810), `updatePreferredDisplaySourceForDraw`, `g_gsSubmitCount`, `m_stateMutex`, `VU1Interpreter::m_activeGs` (ps2_vu1.h:267, set at ps2_vu1_core.cpp:2238).
- Produces:
```cpp
// gs_frontend.h, public:
// Draws one triangle with the current GS state of context prim.ctxt, from host-space vertices
// (x/y float pixels in XYOFFSET space exactly as the GIF path stores them, z the same integer
// the GIF path would carry, s/t/q floats with prim.fst == 0, fog byte). Equivalent to three
// XYZF2 kicks except that x/y keep their fraction.
void submitHostTriangle(const GSPrimReg &prim, const GSVertex &v0, const GSVertex &v1, const GSVertex &v2);
// ps2_vu1.h, public:
GS *activeGs() const { return m_activeGs; }   // valid during execute()/resume()
```

- [ ] **Step 1: Write the failing tests**

In `ps2_gs_tests.cpp`, inside `register_ps2_gs_tests()`'s `MiniTest::Case("PS2GS", ...)`, find an existing test that draws a flat triangle through `processGIFPacket` and reads pixels back (search for `GS_PRIM_TRIANGLE` or `XYZ2` and `ReadVram`/`getGSVRAM`; copy its frame/scissor register setup verbatim). Add:
```cpp
tc.Run("submitHostTriangle draws the same pixels as three XYZ2 kicks", [](TestCase &t)
{
    PS2Memory memA, memB;
    t.IsTrue(memA.initialize() && memB.initialize(), "memory");
    GS gsA, gsB;
    gsA.init(memA.getGSVRAM(), static_cast<uint32_t>(PS2_GS_VRAM_SIZE), &memA.gs());
    gsB.init(memB.getGSVRAM(), static_cast<uint32_t>(PS2_GS_VRAM_SIZE), &memB.gs());
    // <copy the reference test's FRAME/SCISSOR/XYOFFSET/TEST/PRIM register writes here for both>
    // A: three XYZ2 kicks of an integer-coordinate triangle (as the reference test does).
    // B: the same triangle through the hook.
    GSPrimReg prim{}; prim.type = GS_PRIM_TRIANGLE; prim.iip = 0; prim.tme = 0; prim.abe = 0; prim.ctxt = 0;
    GSVertex v0{}, v1{}, v2{};
    v0.x = 10.0f; v0.y = 10.0f; v1.x = 40.0f; v1.y = 10.0f; v2.x = 10.0f; v2.y = 40.0f;
    for (GSVertex *v : {&v0, &v1, &v2}) { v->r = 255; v->g = 0; v->b = 0; v->a = 128; v->q = 1.0f; }
    gsB.submitHostTriangle(prim, v0, v1, v2);
    // compare the frame buffer bytes of A and B
    t.Equals(std::memcmp(memA.getGSVRAM(), memB.getGSVRAM(), PS2_GS_VRAM_SIZE), 0,
             "host triangle must match the GIF triangle pixel for pixel");
});
tc.Run("submitHostTriangle honours the context selected by prim.ctxt", [](TestCase &t)
{
    // set FRAME_1 to a different fbp than FRAME_2 in one GS; prim.ctxt = 1; draw; assert the
    // pixels landed at FRAME_2's base and FRAME_1's region is untouched.
    // <fill from the reference test's register helpers>
});
```
The test binary runs with `PS2X_GS_BACKEND=cpu` (main.cpp env default), so the CPU rasteriser draws into VRAM synchronously; integer coordinates keep the CPU sprite/line truncation out of the comparison (this test uses triangles only).

- [ ] **Step 2: Run to verify they fail**

`cmake --build third_party/ps2recomp/build-clang --target ps2x_tests 2>&1 | grep -E "error" | head` — expected: `submitHostTriangle` is not a member of `GS`.

- [ ] **Step 3: Implement**

In `gs_frontend.cpp`, refactor `buildDrawBatch` so the state fill is shared:
```cpp
void GS::fillDrawState(GSDrawState &state, const GSPrimReg &prim) const
{
    state.context = m_ctx[prim.ctxt ? 1 : 0];
    state.prim = prim;
    state.texa = m_texa; state.texclut = m_texclut; state.pabe = m_pabe;
    state.scanmsk = m_scanmsk; state.dimx = m_dimx; state.dthe = m_dthe; state.colclamp = m_colclamp;
    state.fogR = m_fogR; state.fogG = m_fogG; state.fogB = m_fogB;
    state.textureWidth = static_cast<uint16_t>(1u << std::min<uint32_t>(state.context.tex0.tw, 10u));
    state.textureHeight = static_cast<uint16_t>(1u << std::min<uint32_t>(state.context.tex0.th, 10u));
    const uint64_t tex1 = state.context.tex1;
    const uint8_t mmag = static_cast<uint8_t>((tex1 >> 5u) & 0x1u);
    const uint8_t mmin = static_cast<uint8_t>((tex1 >> 6u) & 0x7u);
    state.linearFilter = mmag != 0u || mmin == 1u || (mmin & 0x4u) != 0u;
}

GSPrimitiveBatch GS::buildDrawBatch(int vertexCount) const
{
    GSPrimitiveBatch batch{};
    batch.vertexCount = static_cast<uint8_t>(std::min(vertexCount, 3));
    for (int i = 0; i < batch.vertexCount; ++i) batch.vertices[static_cast<size_t>(i)] = m_vtxQueue[i];
    fillDrawState(batch.state, m_prim);
    return batch;
}

void GS::submitHostTriangle(const GSPrimReg &prim, const GSVertex &v0, const GSVertex &v1, const GSVertex &v2)
{
    std::lock_guard<std::recursive_mutex> lock(m_stateMutex);
    if (!m_backend) return;
    GSPrimitiveBatch batch{};
    batch.vertexCount = 3;
    batch.vertices[0] = v0; batch.vertices[1] = v1; batch.vertices[2] = v2;
    GSPrimReg p = prim; p.type = GS_PRIM_TRIANGLE;   // the hook is triangles only (CPU backend truncates sprite/line x/y)
    fillDrawState(batch.state, p);
    updatePreferredDisplaySourceForDraw(batch);
    m_backend->Submit(batch);
    g_gsSubmitCount.fetch_add(1, std::memory_order_relaxed);
    recordHostDrawDebugEventUnlocked(batch);   // new: same event as recordDrawDebugEventUnlocked but from the batch
}
```
Declare `fillDrawState` (private, const) and `submitHostTriangle` (public) in `gs_frontend.h`; implement `recordHostDrawDebugEventUnlocked(const GSPrimitiveBatch&)` by copying `recordDrawDebugEventUnlocked` (gs_frontend.cpp:447-482) with the vertices read from the batch instead of `m_vtxQueue`. Do not change `vertexKick`.

In `ps2_vu1.h` add the public inline `GS *activeGs() const { return m_activeGs; }` (forward declaration `class GS;` already exists there).

- [ ] **Step 4: Run the tests**

Rebuild `ps2x_tests`, run from `build-clang/ps2xTest`: the two new tests pass, everything else unchanged (`exit=0`). Then `./build.sh test` (lock) exit 0 — the fixture verifies are untouched by this task.

- [ ] **Step 5: Commit**

```bash
git add third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_frontend.h third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_frontend.cpp third_party/ps2recomp/ps2xRuntime/include/runtime/ps2_vu1.h third_party/ps2recomp/ps2xTest/src/ps2_gs_tests.cpp
git commit -m "gs: public submitHostTriangle (host-space float vertices, state filled from the live context like the GIF path); VU1Interpreter::activeGs(); unit tests vs three XYZ2 kicks"
git push
```

---

### Task 2: The native packet builder draws through the hook behind `PS2X_VU1_HOST_DRAW`

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp` (the `0x28` handler, `cmdBuildPacket`, ~lines 800-1000)
- Modify: `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` (`--host-draw`, `--vram-diff`)
- Modify: `build.sh` (`test_step`: one `--vram-diff` line)

**Interfaces:**
- Consumes: `GS::submitHostTriangle`, `vu.activeGs()`, the handler's staging qwords (`+0` ST with `.z` = Q, `+1` RGBAQ after `ftoi<0>`, `+2` XYZF2 after `ftoi<4>`; research/12 f.4), the GIFtag template at qwords 290/300 (`PRIM` field, `REGS = 0x412`, `NLOOP = 3`, `EOP`), `vu.startXgkick(vi2)`.
- Produces: with `PS2X_VU1_HOST_DRAW=1` each triangle is submitted through the hook instead of being packed and kicked; the data-memory writes that the GIF path performs (the nine register qwords, the ping-pong swap, `vi2`/`vi8`) are still performed so `--regs all` and `data=` stay identical; only the `startXgkick` call is replaced. `vu1_replay --host-draw` sets the env; `vu1_replay --vram-diff <outdir>` runs every dump twice (GIF path, host path) into fresh GS VRAM and prints `VRAMDIFF <name> differing=<n> of <pixels> (<pct>%)`, exit 1 if any dump exceeds `--vram-tol` (default 1.0 %).

- [ ] **Step 1: Read the pre-conversion floats**

In `cmdBuildPacket`, the XYZF2 quad for each vertex is produced by `ftoi<4>` from the transformed float position (`vf` from `0xdf8`, staging `+2` before conversion is not stored — check research/12 f.4: `0x1780` loads `+42` and applies `ftoi<4,...>` before `SQ` to `vi2+3/6/9`). Capture the float x/y before `ftoi<4>` for the three vertices of the triangle; keep the converted integers for z and for the packet qwords.

- [ ] **Step 2: Emit through the hook**

Where the handler calls `vu.startXgkick((uint32_t)(uint16_t)c.vi(2))`, add:
```cpp
static const bool s_hostDraw = std::getenv("PS2X_VU1_HOST_DRAW") != nullptr && std::atoi(std::getenv("PS2X_VU1_HOST_DRAW")) != 0;
if (s_hostDraw && c.vu.activeGs() != nullptr)
{
    GSPrimReg prim = primFromGifTag(c.qw(kGifTagPingA /* 290 or 300, whichever this kick uses */));
    GSVertex v[3];
    for (int i = 0; i < 3; ++i)
    {
        v[i].x = hostXY[i][0];                  // float, pre-ftoi<4>, already in XYOFFSET space (same as the GIF x/16)
        v[i].y = hostXY[i][1];
        v[i].z = static_cast<double>(xyzfWord[i].z);   // the 24-bit integer the packet carries
        v[i].fog = xyzfWord[i].f;
        v[i].r = rgbaq[i].r; v[i].g = rgbaq[i].g; v[i].b = rgbaq[i].b; v[i].a = rgbaq[i].a;
        v[i].s = st[i].s; v[i].t = st[i].t; v[i].q = st[i].q;   // prim.fst == 0: STQ path
    }
    c.vu.activeGs()->submitHostTriangle(prim, v[0], v[1], v[2]);
    g_xgkickDecoded.fetch_add(1, std::memory_order_relaxed);   // keep the diagnostic count comparable
}
else
{
    g_xgkickDecoded.fetch_add(1, std::memory_order_relaxed);
    c.vu.startXgkick((uint32_t)(uint16_t)c.vi(2));
}
```
`primFromGifTag` decodes the 64-bit GIFtag's PRIM field (bits 47-57) into `GSPrimReg` exactly as `gs_frontend.cpp`'s GIFtag handler does (copy its bit layout; `PRE` must be set in the template, assert it in a debug check). The host path still executes every data-memory write and register update the GIF path does, so the goldens stay green with the knob on.

- [ ] **Step 3: `vu1_replay --host-draw` and `--vram-diff`**

Arg parsing: `--host-draw` → `_putenv("PS2X_VU1_HOST_DRAW=1")`; `--vram-diff <outdir>` + optional `--vram-tol <pct>`. In `--vram-diff` mode, for each dump: run once with `PS2X_VU1_HOST_DRAW=0` into a fresh `GS`/VRAM (`memory.getGSVRAM()` zeroed, `gs.reset()`), copy the first 640×448×4 bytes of the frame region (fbp 0, the CPU backend's default frame if no FRAME register was set — confirm in `gs_frontend.cpp` what an unset FRAME resolves to; if draws need a FRAME register, write one through `gs.writeRegister` before each run, identically for both), then run again with `=1`, and count differing 32-bit pixels. Because `s_hostDraw` is a read-once static in the native file, the two runs must happen in two processes: implement `--vram-diff` as a driver that re-executes `vu1_replay` itself (`argv[0]`) with `--vram-dump <file>` for each mode and compares the two files. Print one `VRAMDIFF` line per dump and `PASS`/`FAIL` at the end; exit 1 on FAIL. Save `<outdir>/<dump>.{gif,host}.rgba` for inspection.

- [ ] **Step 4: Verify offline**

```bash
cmake --build third_party/ps2recomp/build-clang --target vu1_replay | tail -1 && cp third_party/ps2recomp/build-clang/ps2xRuntime/vu1_replay.exe dist/
dist/vu1_replay.exe --verify tests/fixtures/vu1/dispatch_0x1b50/golden.txt --native --host-draw --regs all tests/fixtures/vu1/dispatch_0x1b50/*.bin | tail -1    # PASS: registers and data unchanged with host draw on
dist/vu1_replay.exe --vram-diff logs/vramdiff_fixtures tests/fixtures/vu1/dispatch_0x1b50/*.bin | tail -3       # every dump ≤ 1.0 % differing pixels
```
Expected: `PASS` on both. If `--vram-diff` exceeds tolerance, inspect the `.rgba` pair (convert with a 5-line Python/Pillow script) — edge pixels differ by design (sub-pixel coverage), interior pixels must not; an interior difference means a wrong lane (ST vs RGBAQ) or a wrong context.

Add to `build.sh` `test_step`, after the four verify lines:
```bash
  "$ROOT/dist/vu1_replay.exe" --vram-diff "$ROOT/logs/vramdiff_fixtures" "$ROOT"/tests/fixtures/vu1/dispatch_0x1b50/*.bin
```

- [ ] **Step 5: Verify in-game**

`./build.sh runtime` (lock), then a detached full gate with `PS2X_VU1_HOST_DRAW=1 PS2X_VU_STATS=1` (`--stamp hostdraw_on`). Expected `GATE PASS (3/3)`; the mission sheet's HUD must look identical to `logs/parity/gate/native_default/mission_sheet.png` (score the two title run dirs against each other with `compare.score`: every capture ≥ 95).

- [ ] **Step 6: Commit**

```bash
git add third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp build.sh
git commit -m "vu1(native): 0x28 draws through GS::submitHostTriangle when PS2X_VU1_HOST_DRAW=1 (GIF path untouched, goldens green); vu1_replay --host-draw and --vram-diff equivalence check in build.sh test"
git push
```

---

### Task 3: Render-target scale spike (decision gate) and, if feasible, `PS2X_GS_SCALE`

**Files:**
- Create: `docs/research/14-gs-render-target-scale-spike.md`
- Modify (3b only): `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp`, `include/runtime/gs/gs_gl_backend.h`

**Interfaces:**
- Consumes: `kMaxRtWidth = 1024`, `kRtHeight = 1024`, `kHostFrameWidth/Height = 640/512` (gs_gl_backend.cpp:22-25), `appendVertex` (2019-2047), `executeSubmit` (2049-2152), `markRtDirtyFromFrame`, `refreshRenderTargetsFromShadow`/`refreshDirtyRows`, `resolveTexture` (render targets sampled directly, STATUS 2026-09-09 13:30), `HostFrameTexture`, the readback-to-shadow-VRAM path, `PS2X_GS_DUMP_DISPLAY`.
- Produces: the note lists every place the GL backend assumes GS pixels are 1:1 with GL texels (render-target allocation, dirty rows, upload of shadow VRAM into RTs, RT-as-texture sampling, readback/download to shadow VRAM, scissor, display presentation, local-to-local copies), with the change each needs for an integer factor `S`. Decision rule: if the change set is ≤ 8 touch points and no readback path needs a downsample filter that affects gameplay-visible content (e.g. the title labels' page copies), implement `PS2X_GS_SCALE` (3b); otherwise stop, record why, and carry it to Sprint 3.

- [ ] **Step 1: Enumerate (read-only)** — grep the backend for `kRtHeight`, `kMaxRtWidth`, `640`, `448`, `512`, `>> 4`, `xyoffset`, `scissor`, `ReadSpan`, `glReadPixels`/`rlReadTexturePixels`, `HostFrameTexture`; for each hit write one table row: line, what it assumes, change for scale S, risk. Include the CPU backend interplay (`PS2X_GS_BACKEND=cpu` stays 1x; state it).
- [ ] **Step 2: Decide** — apply the rule above; write the decision and the plan for 3b (or Sprint 3) at the end of the note. Commit the note: `git commit -m "research: GL backend 1:1 assumptions for a render-target scale; decision"`.
- [ ] **Step 3 (3b, only on a "go"):** implement `PS2X_GS_SCALE` (integer, default 1) applied to RT allocation, vertex x/y/scissor in `appendVertex`/scissor setup, dirty-row bands, RT-as-texture coordinates, and the readback (box-filter downsample to 1x shadow VRAM); presentation at RT size. Verify: `PS2X_GS_SCALE=1` gate green and title captures score ≥ 99 against `native_default`; `PS2X_GS_SCALE=2 PS2X_VU1_HOST_DRAW=1` gate green and the mission sheet's HUD text visibly sharper (attach the sheet path to STATUS). Commit per sub-step.

---

### Task 4: Research addendum — family B and C handlers

**Files:**
- Create: `docs/research/13-vu1-family-b-world-objects.md`

**Interfaces:**
- Consumes: research/12 §f (the f.1 table: `0x02`→`0x1f70` world-object setup with `BAL vi15, 0x3618` at `0x2070`; `0x0a`→`0xf08` kick 423; `0x12`→`0x1108`; `0x56`→`0x640` template fill base 150; `0x1a`→`0x15b0`; `0x2a`→`0x1a78` flush/kick; `0x4c`→`0x20c8` loop back-edge; the `0x3618-0x3d20` subroutine with inner `BAL 0x3ad0`/`0x3a90`; the `0x1980-0x1a70` shared flush tail with `XGKICK vi6`/`vi5`; family C: `0x64`→`0x4a8` kick 330, `0x32`→`0x23b0`, `0x30`→`0x22a0`, `0x72`, `0x74`), `dist/vu1_replay.exe --pchist`, `tools_py/vu1dis.py`, the generated C++ labels, `logs/vu1dump{2,3,4}` and `logs/vu1entry0/dispatch_dumps.txt`.
- Produces: for every family-B and family-C handler and for `0x3618` (with its inner subroutines) the same description level research/12 f.4 gives for `0xdf8`/`0xf90`: register roles, data-qword layout (the per-primitive index list `0x2070` walks, the 150-based template, qwords 327-330/423), loop structure, XGKICK sites and packet templates, live-in/live-out per handler, the exact hand-back contract for family B (list start and program end only, unless a handler is proven independent), and the executed order of the C lists (which handler rewrites `vi14`, to what). Every row `[verified]`/`[guess]`.

- [ ] **Step 1:** histogram of the 90 family-B/C dumps (select by list content from `dispatch4_lists.txt` and the dump3/dump2 equivalents); disassemble each handler range; decode two family-B and two family-C lists end to end (executed order via `--trace` on one dump each).
- [ ] **Step 2:** write the note; self-check: could an engineer implement `0x02` + `0x3618` + `0x4c` from it alone? Commit: `git commit -m "research: VU1 family B/C handlers and the 0x3618 primitive subroutine"`.

---

### Task 5: Native family B

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp`

**Interfaces:**
- Consumes: research/13, the existing `Ctx`, `isFamilyARun` pre-scan, `handleCommand` switch, the `Vu1Gen`/`vu1ops` helpers, `--verify --native --regs all` goldens (`logs/vu1golden/dump4_1b50_exact` etc., regenerate with the exact interpreter if missing).
- Produces: the pre-scan accepts family-B lists (`68 [06] 02 0a 12 [56] 1a 2a 4c 42`, with the `0x4c` back-edge semantics: `y` = branch-target index, count from the header) when every command is implemented; otherwise whole hand-back as today. New handlers: `0x02` (calls a native `primSubroutine3618`), `0x0a`, `0x12`, `0x56`, `0x1a`, `0x2a`, `0x4c`. `0x3618` implemented as a native function with the same clamp discipline.

- [ ] **Step 1:** implement `0x0a`, `0x56`, `0x12`, `0x1a`, `0x2a` (the small ones) one per commit; since family-B lists still contain `0x02`/`0x4c`, the pre-scan keeps handing them back until all are done — verify each commit with `--verify --native --regs all` on all three dump sets (must stay PASS, handbacks unchanged).
- [ ] **Step 2:** implement `0x3618` (+ inner `0x3ad0`/`0x3a90`) as `primSubroutine3618(Ctx&)`, then `0x02`, then `0x4c` (the loop: re-read the command index from `y`, decrement the primitive count, end via `0x1b40` when it reaches 0). After `0x4c`, enable family-B lists in the pre-scan. Expected: `native ended` rises from 76 to 76 + (25 dump4 + the dump3/dump2 B counts), `--regs all` PASS on every set. Commit per handler with handbacks before/after.
- [ ] **Step 3:** `./build.sh test` exit 0; gate (native default on) green; STATUS "Current state" line 4 updated with the new native count.

---

### Task 6: Native family C

**Files:** same as Task 5.

- [ ] **Step 1:** implement `0x64` (`vi2 = 330; XGKICK vi2; B 0x1b60`), `0x30` (tail-jumps into `0x1780` with `vi6 = 752` — reuse `cmdBuildPacket` with the entry offset research/13 documents), `0x32`, `0x72`, `0x74`; the pre-scan must handle the C lists' executed order (a handler rewrites `vi14`): if research/13 shows the executed order is not derivable from the static list, the pre-scan may only accept a C list when the dispatcher loop itself can validate each command on the fly and a mid-list hand-back is safe at `0x1b60` for C handlers — otherwise C stays whole-hand-back and the report says so.
- [ ] **Step 2:** verify on all sets; `./build.sh test`; gate; commit per handler. Target: 166/166 native or the residual set listed with reasons in STATUS.

---

### Task 7: Per-handler work clamps

**Files:**
- Modify: `socom2_dispatch_0x1b50.cpp` (every handler that reads a loop count from `TOP+2.z/.w` or from the index list)

- [ ] **Step 1:** at each read of a loop count (`0xb28`, `0xe08`, `0xf90`, `0x5e0`, `0x1458` read `TOP+2.z`; `0x17d0`, `0x1640` read `TOP+2.w`; family-B counts per research/13), clamp against `kMaxVertices`/`kMaxTriangles`/the family-B ceilings; on violation set `c.vi(14)` to the current index, `m_state.pc = 0x1b60`, and return false from the handler (mid-list hand-back is safe for family A; for family B hand back only if research/13 proves it, otherwise finish the primitive and hand back at the `0x4c` boundary). Document the rule in the file header.
- [ ] **Step 2:** synthetic test: take one fixture dump, rewrite `TOP+2.z` to 300 with a small Python script into `logs/`, run `--verify --native` against an exact golden of the modified dump: the native path must hand back and match. `./build.sh test` exit 0. Commit: `git commit -m "vu1(native): per-handler loop-count clamps hand back instead of running unbounded"`.

---

### Task 8: Capture during settle waits; transition floor back to 5

**Files:**
- Modify: `tools_py/parity/drive.py` (`wait_stable` 68-91, step loop ~141-255), `tools_py/parity/black_rows.py` (glob at line 24), `tools_py/parity/gate.py` (`TRANSITION_MIN_FRAMES`), `tools_py/tests/test_gate.py`

**Interfaces:**
- Consumes: `wait_stable(hwnd, settle, maxwait, thresh=1.0, changed_from=None, change_thresh=0.3)` polling every 0.25 s; capture naming `s{i:02d}_...png`; `black_rows.py` selects `s*.png`; `gate.score_title` globs `s[0-9][0-9]_*.png` minus `burst`.
- Produces: `wait_stable(..., on_frame=None)` calls `on_frame(elapsed)` every poll; `run_steps` passes a callback that saves `w{i:02d}_{k:03d}.png` (full-resolution `winshot.grab`) every 1.0 s of every wait; `black_rows.py` globs `s*.png` and `w*.png`; the title scorer is unaffected (pattern starts with `s`); `TRANSITION_MIN_FRAMES = 5` restored with the calibration comment updated from a fresh run.

- [ ] **Step 1 (test first):** in `test_gate.py` add `test_wait_frames_count_toward_transition` using a temp dir with three near-black `w00_000.png..w00_002.png` (`Image.new("RGB",(640,448),(0,0,0))`) and two `s01_none.png` black frames: `score_transition` must report 5 frames examined once the floor is 5. Run → FAIL (black_rows ignores `w*`).
- [ ] **Step 2:** implement the callback and the glob; `python -m unittest tools_py.tests.test_gate -v` green.
- [ ] **Step 3:** `./build.sh runtime` not needed; run the transition gate twice detached (`--only transition`, stamps `wcap1`, `wcap2`): both must examine ≥ 5 frames with `peak 0`; set the floor to 5 and record the counts in the comment. Commit: `git commit -m "parity: drive.py captures every second during settle waits (w*.png); black_rows counts them; transition floor back to 5"`.

---

### Task 9: Committed gate fixtures

**Files:**
- Create: `tests/fixtures/gate/title/s00_none.png` … `s15_none.png` (320×224, from a clean run, resized with `Image.BOX`), `tests/fixtures/gate/transition/s00_none.png`, `s01_burst_000.png` (two near-black 320×224 frames from a real run), `tests/fixtures/gate/mission/good.drive.log`, `bad.drive.log` (copies of `logs/parity/drive_gameplay_probe5.txt` and `logs/parity/vr_gameplay.drive.log`, trimmed to the lines the scorer reads)
- Modify: `tools_py/tests/test_gate.py`

- [ ] **Step 1:** produce the fixtures with a small Python script (resize with `Image.BOX` to 320×224; `compare.score` resizes to that size anyway); check each title fixture scores ≥ 95 against `scripts/parity/ref_main_menu_ours.png` (if resizing drops the score below 90, keep them at 640×448 instead and note the size). Total should stay under 1 MB.
- [ ] **Step 2:** point the positive tests at the fixtures (no `skipUnless`), keep the `logs/`-based tests as additional skip-guarded cases. `python -m unittest tools_py.tests.test_gate -v` → all positive cases run and pass. Commit: `git commit -m "parity: committed gate fixtures so test_gate's positive cases run on a fresh clone"`.

---

### Task 10: Unit-suite determinism

**Files:**
- Modify: `build.sh` (`test_step`), `third_party/ps2recomp/ps2xTest/src/ps2_runtime_interrupt_tests.cpp` (only if a flake remains)

- [ ] **Step 1:** `build.sh test` runs `ps2x_tests.exe` `${PS2X_TEST_REPEAT:-1}` times; run with `PS2X_TEST_REPEAT=5` under the lock. Expected: 5 × exit 0.
- [ ] **Step 2:** if any run fails, capture which test, read it, fix the root cause (a wall-clock assumption becomes a condition wait with a generous budget, or an ordering assumption gets a barrier) — never loosen an assertion; re-run 5×. Commit: `git commit -m "test: ps2x_tests deterministic across repeated runs (PS2X_TEST_REPEAT)"`.

---

### Task 11: Docs and state

**Files:** `docs/STATUS.md`, `docs/LOOP_PROMPT.md`, `README.md`, `docs/superpowers/plans/2026-09-11-sprint-2-host-render-and-family-b.md`

- [ ] **Step 1:** STATUS "Current state" lines updated (knobs `PS2X_VU1_HOST_DRAW`, `PS2X_GS_SCALE` if landed, native coverage count, gate determinism), one dated Sprint 2 entry; README "Build and run" lists the new knobs; LOOP_PROMPT goal 3 text updated to the Sprint 2 spec; plan boxes ticked. Commit and push. Merge `sprint-2` into `develop` (fast-forward) and `main`.

---

## Self-review

- **Spec coverage:** §2.1 hook → Task 1-2; §2.2 host resolution → Task 3 (spike with decision gate, 3b implements); §2.3 family B/C → Tasks 4-6; §2.4 clamps → Task 7; §2.5 gate hardening → Tasks 8-10; §4 DoD: host-draw gate green (Task 2 step 5), `PS2X_GS_SCALE=2` sharper HUD (Task 3b or a recorded deferral), 166/166 or listed residual (Task 6), fresh-clone gate tests (Task 9), ≥ 5 transition frames (Task 8), deterministic suite (Task 10).
- **Placeholders:** Task 1's test copies register setup from an existing GS draw test (named by search terms, not invented); Tasks 4-6 are procedural like Sprint 1's Task 7 because the handler set is Task 4's output; Task 3 is an explicit spike with a decision rule rather than blind code.
- **Type consistency:** `submitHostTriangle(const GSPrimReg&, const GSVertex&, const GSVertex&, const GSVertex&)` and `activeGs()` match between Tasks 1 and 2; `--host-draw`/`--vram-diff` flags match between Task 2 and build.sh; `w{i:02d}_{k:03d}.png` matches between drive.py, black_rows.py and the Task 8 test.
