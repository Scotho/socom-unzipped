# Sprint 3 — Render-Target Scale, Fourth VU1 Family, Intro-Movie Macroblocks: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the native render path visibly better (a presentation-filter experiment, then a real integer render-target scale behind `PS2X_GS_SCALE`, verified bit-identical at 1× and sharper at 2×), finish the VU1 dispatcher (the fourth command family and, if feasible, `0x34`), give the host-draw equivalence check family-C coverage, and localise the intro-movie black macroblocks.

**Architecture:** The scale lands in four independently shippable stages from `docs/research/14-gs-render-target-scale-spike.md` §6: first the `RenderTarget` size field is split into native and host sizes with no behaviour change (S3-a), then every GPU→VRAM readback is redirected through a 1× native mirror resolved on the GPU (S3-b), then the scale itself (S3-c), then verification at 1× and 2× (S3-d). Before any of that, a ten-line presentation-filter experiment (S3-0) measures how much softness is the final window stretch. The VU1 work follows the Sprint 1/2 recipe: research note, one handler per commit, bit-exact against exact-interpreter goldens, pre-scan acceptance only when a list is fully implemented. The macroblock work is a bounded spike: reproduce, diff against PCSX2, localise, fix only if one step away.

**Tech Stack:** C++20 (llvm-mingw clang via `build.sh`), CMake/Ninja, OpenGL through raylib/rlgl, MiniTest, Python 3 (numpy, Pillow), Git Bash + PowerShell for detached runs.

**Spec:** `docs/superpowers/specs/2026-09-11-sprint-3-render-scale-and-fourth-family-design.md`

## Handoff notes for the executing model (read once)

- **Process.** Run this plan with superpowers:subagent-driven-development: a fresh implementer per task (Opus for C++ and research, Sonnet for Python/docs, Haiku for trivial re-reviews), a task review after each, a whole-branch review at the end, one fix wave, then a fast-forward merge of `sprint-3` into `develop` and `main`. Keep a ledger under `.superpowers/sdd/<plan-basename>/progress.md` (the `scripts/sdd-workspace` and `scripts/task-brief` helpers in the skill directory produce the workspace and per-task briefs). Record every decision you take on the user's behalf as `Ruling: … — why — cost if wrong` and list them all in the final message.
- **Standing rulings from Sprints 1-2 (reuse them).** Work on a branch in the main checkout, never a git worktree (the ignored `game/`, `tools/`, `recomp/output`, `build-clang` are multi-GB and a worktree cannot build). File-disjoint tasks may run in parallel; tell each implementer "if `git commit` fails with index.lock, wait 10 s and retry". Research tasks do not commit; the controller commits the note. A review finding the plan text contradicts is ruled on, not dismissed.
- **Build and run rules.** `bash scripts/loop_lock.sh take|wait|release <owner>` around `./build.sh runtime`, `./build.sh test` and every game run; `cmake --build third_party/ps2recomp/build-clang --target vu1_replay|ps2x_tests` needs no lock (prepend `tools/llvm-mingw/bin`, `tools/cmake/bin`, `tools/ninja` to PATH). Game runs go detached: a bash script under `logs/` started with PowerShell `Start-Process bash.exe -ArgumentList "<script>"`, polled through a `.done` marker; `python -m tools_py.parity.gate` takes the lock itself; **always `./build.sh runtime` before a gate** (the test step does not rebuild `dist/socom2.exe`). A full gate is ~20 minutes; `--only title|transition|mission` for iteration. Known: one intro-cinematic freeze was seen in the mission gate once (re-run once on that signature); the VSync scheduler-stop test is on watch (re-run once if it alone fails).
- **Verification vocabulary.** `dist/vu1_replay.exe --verify <golden.txt> [--native|--no-native] [--host-draw] [--regs all|none] <dumps>` (flags after the golden path; exit 1 on mismatch). Exact goldens are made with `PS2X_VU1_FAST=0 PS2X_VU1_GEN=0 dist/vu1_replay.exe --batch <dir> <dumps>`; the 0x1b50 dump lists are `logs/vu1entry0/dispatch_dumps.txt` (166 runs across `logs/vu1dump2/3/4`). Current native coverage 123/166. `dist/vu1_replay.exe --vram-diff <outdir> <dumps>` compares the GIF and host paths (hard differences over drawn pixels, 1 % tolerance, FAIL when nothing was checked). Gate captures score with `tools_py/parity/compare.score` against a reference run under `logs/parity/gate/<stamp>/`; the newest known-good stamps at sprint start are `hostdraw_fix` (host-draw on) and `tfix4` (transition).
- **Commit conventions.** From the repo root with explicit paths (never `git add -A`); `server/config/simulated.db` stays unstaged; push after each commit. Trailers: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Claude-Session: <the executing session's url>`.
- **The freeze.** No commits that change VU1/VU0 interpreter speed, scheduler batching, or GS/GL caching and upload paths for performance. The S3-b resolve pass and S3-c scale are correctness structures for a feature, not optimisations; anything else that "makes it faster" is out.

## Global Constraints

- Branch `sprint-3` off `develop` (= `main` = 148dffa). Everything in the Handoff notes above.
- Header edits (`gs_gl_backend.h`, `gs_types.h`, `ps2_vu1.h`) cost a ~10-minute rebuild; batch them per task.
- `PS2X_GS_SCALE` default stays 1 for the whole sprint. `PS2X_VU1_HOST_DRAW` default stays off.
- At `PS2X_GS_SCALE=1` every stage must be bit-identical: gate green and every title capture ≥ 99 (`compare.score`) against the S3-a baseline run. At `PS2X_GS_SCALE=2` the score bar does not apply (captures are window-sized readbacks); the bar is gate green plus a human-inspected sheet.
- The CPU backend (`PS2X_GS_BACKEND=cpu`, used by `vu1_replay` and the unit tests) stays 1× and untouched.
- Native VU1 float maths through the `ps2_vu1_ops.h` helpers; every handler bit-exact (`--regs all`).
- Shell and Python files stay LF; C++ edits through the Edit tool or a Python patch script.

---

## File map

| Path | Responsibility |
|---|---|
| `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp` (~2585-2604) | S3-0 presentation filter behind `PS2X_PRESENT_FILTER` |
| `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h`, `src/lib/gs/gs_gl_backend.cpp` | S3-a size split; S3-b native mirror + resolve; S3-c scale |
| `docs/research/14-gs-render-target-scale-spike.md` | §3 site list (the audit checklist for S3-a); fix the 15-vs-18 headline while there |
| `docs/research/15-vu1-fourth-family.md` | (new) `0x70`/`0x52`/`0x66`/`0x40` and `0x34` |
| `third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp` | fourth-family handlers, `0x34`, pre-scan acceptance |
| `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` | family-C vram-diff coverage |
| `docs/research/16-intro-movie-macroblocks.md` | (new) the macroblock spike |
| `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/MPEG.cpp`, `src/lib/gs/gs_gl_backend.cpp` (upload path) | macroblock fix, only if bounded |
| `docs/STATUS.md`, `README.md`, `docs/LOOP_PROMPT.md`, this plan | knobs, counts, close-out |

---

### Task 1: S3-0 — presentation filter experiment (`PS2X_PRESENT_FILTER`)

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp` (the present block, ~2585-2604: `scale = min(screenW/srcW, screenH/srcH)`, one `DrawTexturePro` into `dstRect`, plus the optional circuit-2 draw)
- Modify: `README.md` (knobs), `docs/STATUS.md` (verdict)

**Interfaces:**
- Consumes: `presentTex` (a `Texture2D` wrapping the GL render target; `srcRect` is its top-left `presentWidth × presentHeight`), raylib `LoadRenderTexture`, `SetTextureFilter(tex, TEXTURE_FILTER_POINT|BILINEAR)`, `BeginTextureMode/EndTextureMode`, `rlDisableColorBlend`.
- Produces: `PS2X_PRESENT_FILTER=linear` (default, today's behaviour), `=integer` (draw the frame with point sampling into an intermediate render texture at `k = floor(scale)` times the source size, then draw that texture aspect-fit with linear filtering), `=point` (point sampling straight to the window). Read once into a static.

- [x] **Step 1: Implement**

Around the present block:
```cpp
static const std::string s_presentFilter = [] { const char *e = std::getenv("PS2X_PRESENT_FILTER"); return std::string(e ? e : "linear"); }();
static RenderTexture2D s_integerStage{};   // lazily (re)allocated at k*src size
if (s_presentFilter == "integer")
{
    const int k = std::max(1, static_cast<int>(std::floor(scale)));
    const int stageW = static_cast<int>(srcWidth) * k, stageH = static_cast<int>(srcHeight) * k;
    if (s_integerStage.texture.width != stageW || s_integerStage.texture.height != stageH)
    {
        if (s_integerStage.id) UnloadRenderTexture(s_integerStage);
        s_integerStage = LoadRenderTexture(stageW, stageH);
        SetTextureFilter(s_integerStage.texture, TEXTURE_FILTER_BILINEAR);
    }
    SetTextureFilter(presentTex, TEXTURE_FILTER_POINT);
    BeginTextureMode(s_integerStage);
    ClearBackground(BLACK);
    rlDisableColorBlend();
    DrawTexturePro(presentTex, srcRect, Rectangle{0, 0, (float)stageW, (float)stageH}, Vector2{0, 0}, 0.0f, WHITE);
    // circuit-2 draw here too, same rect, if tex2 != 0
    rlDrawRenderBatchActive();
    rlEnableColorBlend();
    EndTextureMode();
    // then present s_integerStage.texture (note raylib render textures are y-flipped: srcRect height negative)
    DrawTexturePro(s_integerStage.texture, Rectangle{0, 0, (float)stageW, -(float)stageH}, dstRect, Vector2{0, 0}, 0.0f, WHITE);
}
else { SetTextureFilter(presentTex, s_presentFilter == "point" ? TEXTURE_FILTER_POINT : TEXTURE_FILTER_BILINEAR); /* existing draw */ }
```
`SetTextureFilter` on a texture whose id belongs to the GL backend sets GL sampler state on that texture; restore it to linear when the mode is `linear` so the default path is unchanged byte for byte. Keep the PMODE circuit-2 blend semantics identical in both branches.

- [x] **Step 2: Verify no change at the default**

`./build.sh runtime` (lock), then a detached `--only title` gate (`--stamp pf_linear`); every capture ≥ 99 vs `logs/parity/gate/hostdraw_fix/title`.

- [x] **Step 3: The experiment**

Two more detached title gates: `PS2X_PRESENT_FILTER=integer` (`pf_integer`) and `=point` (`pf_point`); both must be GATE PASS (the title scorer uses a 320×224 resize, so scores stay ≥ 90 but need not be ≥ 99). Build one side-by-side sheet of the same capture (s05) in all three modes at window size (`tools_py/parity/montage.py` on a temp dir holding the three PNGs) and look at it with the Read tool. Write a one-paragraph verdict into STATUS: how much of the softness is presentation, and which mode should be the default (change the default only if the verdict says so and the gate is green with it).

- [x] **Step 4: Commit**

`git add third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp README.md docs/STATUS.md && git commit -m "present: PS2X_PRESENT_FILTER=linear|integer|point (integer-scale-then-fit); verdict in STATUS" && git push`

---

### Task 2: S3-a — split `RenderTarget::width/height` into native and host sizes (no behaviour change)

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/gs/gs_gl_backend.h` (`struct RenderTarget`, ~line 99), `src/lib/gs/gs_gl_backend.cpp` (every site in research/14 §3)
- Modify: `docs/research/14-gs-render-target-scale-spike.md` (tick the sites as audited; fix the 15-vs-18 headline)

**Interfaces:**
- Consumes: research/14 §3's two lists — GL-texel-size sites `959, 1261, 1328, 1380, 1527, 1566, 1626, 2169, 2281` plus the strides at `1357, 1403`; native-GS-extent sites `1176, 1194, 1217, 1307, 1333, 1371, 1384, 1524, 1556-1557, 1632-1633, 1943, 2163` (line numbers at the spike's commit `dd5fca8`; re-derive with `git blame`/grep, since Sprint 2 shifted the file).
- Produces: `RenderTarget{ uint32_t nativeWidth, nativeHeight; uint32_t hostWidth, hostHeight; … }` with `hostWidth == nativeWidth` for now; a `static_assert`-style runtime check in `getRenderTarget` that `host == native * kScale` where `kScale` is a `constexpr 1u` this task and a knob in Task 4. No remaining reads of a bare `width`/`height` on `RenderTarget` (rename forces the audit: the compiler finds every site).

- [x] **Step 1: Rename and let the compiler enumerate**

Rename the two fields; build; for each error decide native vs host from the §3 lists and the surrounding arithmetic (a clamp against `fbw*64`, a page/row computation, a `usedHeight` comparison → native; a `glTexImage2D`, `glViewport`, `glReadPixels` size, a `uRtSize`/`uTexSize` uniform, a pixel-buffer stride → host). Record the decision per site in a table appended to research/14 (site, chosen size, one-clause reason). The four bug-scar clamps (`w = min(rt.width, fbw*64)` in `refreshDirtyRows`, `xEnd = min(rt.width, fbw*64)` in both downloads, `y1 = min(r.y1, rt.height)` / the band clamp) are **native**.

- [x] **Step 2: Prove no behaviour change**

`./build.sh test` exit 0 (the GL backend has no unit tests; the CPU backend is untouched). `./build.sh runtime` (lock), detached full gate (`--stamp s3a`): GATE PASS and every title capture ≥ 99 vs `logs/parity/gate/pf_linear/title` (or `hostdraw_fix` if Task 1 changed the default). This run is the **S3-a baseline** every later stage compares against.

- [x] **Step 3: Commit**

`git commit -m "gs-gl: RenderTarget native vs host size split (no behaviour change; every site audited per research/14 §3)"`

---

### Task 3: S3-b — native mirror and GPU-side resolve for readbacks

**Files:**
- Modify: `gs_gl_backend.h` (`RenderTarget` gains `GLuint mirrorTexture, mirrorFbo`), `gs_gl_backend.cpp` (`downloadRenderTargetToShadow`, `downloadRenderTargetToCpu`, `resolveTexture`, the frame-dump path, target destruction)

**Interfaces:**
- Consumes: the S3-a fields; `glBlitFramebuffer` (point resolve: `GL_NEAREST` from host to native size) or a fullscreen-triangle shader with a box average; `PS2X_GS_SCALE_FILTER=point|box` (default `point`).
- Produces: `const GLuint GSGlBackend::nativeView(RenderTarget &rt)` — returns `rt.colourTexture` when `hostWidth == nativeWidth` (no copy, no allocation), otherwise resolves host→mirror if the target was drawn since the last resolve (a `dirtySinceResolve` flag set in `executeSubmit`/`executeClear`) and returns the mirror. Both downloads and `resolveTexture` (RT sampled as a texture) read `nativeView(rt)` with native sizes. Frame dumps (`PS2X_GS_DUMP_DISPLAY`) read the native view.

- [x] **Step 1: Implement with the mirror disabled at 1×** (the `hostWidth == nativeWidth` early return), so this task is a pure refactor of the three readers onto `nativeView`.
- [x] **Step 2: Prove no behaviour change:** `./build.sh test`; `./build.sh runtime`; detached full gate `--stamp s3b`: PASS and title captures ≥ 99 vs the S3-a baseline.
- [x] **Step 3: Commit** `gs-gl: readbacks and RT-as-texture read a native view (mirror + resolve pass, inert at 1x)`.

---

### Task 4: S3-c — `PS2X_GS_SCALE`

**Files:**
- Modify: `gs_gl_backend.cpp` (`getRenderTarget`/`getDepthTarget` allocation at `native * S`; `appendVertex` multiplies `out.x/out.y` by `S` **after** the `xyoffset >> 4` subtraction; `glViewport`/`glScissor` in `executeSubmit` and `executeClear` scaled `x0*S, y0*S, (x1-x0+1)*S, (y1-y0+1)*S`; `uRtSize` = host size; `refreshDirtyRows` exact-rect and band uploads write each native pixel as an `S×S` block (expand on the CPU into a staging buffer, or upload 1× to a staging texture and blit with `GL_NEAREST`); presentation rects from the host size; the present-copy texture at host size), `gs_gl_backend.h` (`kScale` becomes `s_scale` read once from `PS2X_GS_SCALE`, clamped to 1..4)
- Modify: `README.md`, `docs/STATUS.md`

**Interfaces:**
- Consumes: Tasks 2-3. Point/line/sprite expansion in `executeSubmit` stays in native units (pre-scale), so a 1-native-pixel line covers `S` host pixels.
- Produces: `PS2X_GS_SCALE=1` (default) byte-identical to Task 3; `=2` renders every draw at 2× into 2× targets, resolves to native for every guest-visible read.

- [x] **Step 1: Implement** in the order allocation → vertex/scissor/viewport → uploads → presentation, building after each; keep a list of every `S` multiplication with its site in the commit message.
- [x] **Step 2: 1× unchanged:** `./build.sh test`; `./build.sh runtime`; detached full gate `--stamp s3c_1x`: PASS and title captures ≥ 99 vs the S3-a baseline.
- [x] **Step 3: Commit** `gs-gl: PS2X_GS_SCALE integer render-target scale (default 1)`.

---

### Task 5: S3-d — verification at 2×

**Files:**
- Modify: `docs/STATUS.md` (sheet paths + verdict), `README.md`

- [x] **Step 1:** `PS2X_GS_SCALE=2 PS2X_VU1_HOST_DRAW=1 PS2X_VU_STATS=1` detached full gate (`--stamp s3d_2x_host`). Expected GATE PASS (3/3). Read the mission sheet and the `native_default`/S3-a mission sheet side by side with the Read tool: the HUD text and squad panel must be visibly sharper. **(This expectation was wrong and was ruled so on the evidence: the HUD, menus and title are textured quads sampled from native-resolution textures — `uTexSize` stays native by design — so they cannot sharpen at any scale. Task 4 predicted it, Task 5 measured it: 3D-region gradient 5.88 -> 3.98 and anti-aliasing fraction 0.133 -> 0.423, HUD flat. The gate PASSed 3/3 as expected.)** If the title labels regress (the page-copy path), `PS2X_GS_SCALE_FILTER=box` vs `point` is the first lever; the second is research/14 §2.5's analysis.
- [x] **Step 2:** `PS2X_GS_SCALE=2` with host-draw off (`--stamp s3d_2x_gif`): GATE PASS (scaled rasterisation of GIF-path triangles).
- [x] **Step 3:** Record both sheets' paths and a verdict in STATUS; keep the default at 1. Commit `docs: PS2X_GS_SCALE=2 verified (sheets); default stays 1`.

---

### Task 6: Research — the fourth command family and `0x34`

**Files:**
- Create: `docs/research/15-vu1-fourth-family.md`

**Interfaces:**
- Consumes: research/12 §f and research/13 (conventions, the dispatcher, the jump table `0x1ba0 + 8*cmd`), `dist/vu1_replay.exe --pchist <hist.bin> <dumps>` and `--trace`, `python tools_py/vu1dis.py --start <pc> --count <n> <dump>`, the generated C++ `src/lib/vu/generated/vu1_d418194495c25213.cpp`, the 42 dump3 lists (`70 06 08 40 42`, `70 08 40 42`, `52 66 08 40 42`; select by list content from `logs/vu1entry0/famBC_dumps.txt` / `dispatch_dumps.txt`) and the single `0x34` dump (named in the Sprint 2 Task 6 report if it survives, else re-derive by scanning dump lists for command word `0x34`).
- Produces: for `0x70`, `0x52`, `0x66`, `0x40`: register roles, data-qword layout, loop structure, XGKICK sites and packet templates, live-in/live-out, hand-back rule, `[verified]`/`[guess]` per row — the level at which an engineer implements from the note alone. For `0x34`: the same plus the EFU semantics the interpreter models (`ERLENG`/`WAITP`/`MFP` in `ps2_vu1_core.cpp`, the P-register latency and how `fastCommit` commits it) and the exact upper-vs-lower same-lane write conflict at `0x2760` as the generated code resolves it (which write wins, and why).

- [x] **Step 1:** histogram + disassembly + two decoded lists per shape; **Step 2:** the note; **Step 3:** the controller commits it. No runtime code.

---

### Task 7: Fourth-family handlers

**Files:**
- Modify: `socom2_dispatch_0x1b50.cpp`

- [x] One handler per commit in frequency order; the pre-scan accepts the three shapes only when every command in them is implemented; verify after each commit with `--verify <dump3 exact golden> --native --regs all` (handbacks unchanged until acceptance, then dump3 `ended` rises from 9 toward 51); `./build.sh test` exit 0; a detached full gate at the end (`--stamp fam4`); STATUS "Current state" line 4 updated. Family-B-style clamps on every new loop count (Sprint 2 Task 7 pattern, `withinBounds`).
  **Scope ruled down after Task 6 (research/15 §9.3): `0x70` and `0x40` only.** `0x52` emits no GIF packets, ends the program and its correctness spans two `MSCAL`s; `0x66` is dispatched zero times from `0x1b50` in the whole corpus, so a handler for it would be unverifiable and shipping one inside the dispatcher was judged the larger risk. So dump3 `ended` went 9 -> 47 (not toward 51), handbacks 43 -> 5, and the two `52 66 08 40 42` commands stayed a documented residual. Gate `fam4` PASS 3/3.

---

### Task 8: `0x34`

**Files:**
- Modify: `socom2_dispatch_0x1b50.cpp`

- [x] Implement per research/15 with the EFU result committed through the same helper path the interpreter uses (mirror `fastCommit`'s P-register half; a KEEP IN SYNC note); the same-lane conflict resolved exactly as the generated code does, with the pc cited. Verify on the `0x34` dump's exact golden with `--regs all`. If bit-exactness cannot be reached in one bounded attempt, leave the command unimplemented, document why in the file header and STATUS, and move on — this is the one task in the sprint allowed to end as a documented residual.

---

### Task 9: Family-C coverage in `--vram-diff`

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/src/tools/vu1_replay.cpp` (`setupReplayGsContext`, the vram-diff driver), possibly `tests/fixtures/vu1/dispatch_0x1b50/` (one added family-C dump + golden line)

- [x] **Step 1:** find out why the family-C fixtures draw nothing in the synthetic context (`drawn=0`): run one with `--trace`/`PS2X_GS_TRACE_CMDS` under `--vram-dump`; likely candidates are a FRAME/ZBUF/TEST state the inline packets set to a region outside the 640×448 readback, or an alpha/test state that rejects every pixel. **Step 2:** give the synthetic context what it needs (or read back the region the inline packets target) so at least one family-C run has `drawn > 0`, and add one family-C dump that draws to the fixture set with its golden line. **Step 3:** `./build.sh test` exit 0 with the vram-diff line reporting `checked` including that dump. Commit.

---

### Task 10: Intro-movie macroblocks — bounded spike

**Files:**
- Create: `docs/research/16-intro-movie-macroblocks.md`
- Modify (only if the fix is one step): `src/lib/Kernel/Stubs/MPEG.cpp` or the 16×16-block upload path in `gs_gl_backend.cpp`

**Interfaces:**
- Consumes: STATUS 2026-09-10 18:45 (user report: 16×16-ish black rectangles at the frame edges of the intro movie and the title's movie background, flickering per frame; suspected dropped/undecoded MPEG macroblocks or the 16×16-block upload), STATUS 2026-09-09 12:10 (the block upload and the dirty-rect refresh), `PS2X_GS_DUMP_DISPLAY`, `scripts/parity/title_only.txt`, `scripts/parity/transition_probe_pcsx2.txt` (burst capture on PCSX2 with `--target pcsx2`), `tools_py/parity/compare.py`.

- [x] **Step 1: Reproduce.** Detached run of `title_only.txt` on ours with `PS2X_GS_DUMP_DISPLAY` over the intro seconds and a `burst` step; the same seconds on PCSX2 (`drive.py --target pcsx2`, the PCSX2 transition script's burst). Find frames where ours shows black 16×16 blocks and PCSX2 does not; note the block grid positions (x, y multiples of 16) and whether they alternate between consecutive frames (two display buffers) or vary per decoded frame.
- [x] **Step 2: Localise.** Compare the decoded frame in the IPU/MPEG path (add a one-off `PS2X_MPEG_DUMP_FRAME=<n>` if needed; remove after) against the uploaded blocks: if the decoded frame already lacks the blocks, the bug is in MPEG.cpp (macroblock decode/skip handling, edge macroblocks); if the frame is complete but the upload leaves blocks, it is the 16×16 upload/dirty-rect path. Name the stage, the frame and the block.
- [x] **Step 3: Fix only if bounded** (one hypothesis → one build → one title gate green with the blocks gone in the burst frames, and `PS2X_GS_DUMP_DISPLAY` frames clean). Otherwise write the note with the exact divergence and stop. Commit either way (note always; code if fixed).

---

### Task 11: Docs and close

- [x] STATUS "Current state" (five lines: knobs `PS2X_GS_SCALE`, `PS2X_PRESENT_FILTER`, `PS2X_VU1_HOST_DRAW`; native count; residual; gate state), one dated Sprint 3 entry with the sheet paths; README knobs; LOOP_PROMPT goal 3 text; tick the plan boxes; `PS2X_TEST_REPEAT=3 ./build.sh test` exit 0; commit; ~~fast-forward `develop` and `main` to `sprint-3` and push~~. Final message lists every ruling with its cost if wrong.
  **The merge is struck out deliberately: the user runs it himself after the whole-branch review.** Task 11 ends at its own commit and push on `sprint-3`; `develop` and `main` were not touched.

---

## Self-review

- **Spec coverage:** §2.1 → Task 1; §2.2-2.5 → Tasks 2-5; §2.6 → Tasks 6-8; §2.7 → Task 9; §2.8 → Task 10; §4 DoD → Tasks 5, 7/8 (residual listing), 9, 10, 11.
- **Placeholders:** Task 1's code is a concrete raylib pattern; Tasks 2-4 name the exact sites via research/14 §3 (line numbers re-derived by the compiler after the rename); Tasks 6-8 are procedural by design (the handler set is Task 6's output), as in Sprints 1-2; Task 10 is a spike with a decision rule.
- **Type consistency:** `nativeWidth/nativeHeight/hostWidth/hostHeight` (Task 2) are what Tasks 3-4 read; `nativeView(rt)` (Task 3) is what Task 4's readers and dumps use; `PS2X_GS_SCALE`, `PS2X_GS_SCALE_FILTER`, `PS2X_PRESENT_FILTER` are named identically in Tasks 1, 3, 4, 5, 11.

---

## Outcome (close-out, Task 11, 2026-09-12)

Every task landed, each independently reviewed, fixed and re-reviewed. The full evidence is in the
per-task reports under `.superpowers/sdd/2026-09-11-sprint-3-render-scale-and-fourth-family/`
(gitignored) and the summary is the 2026-09-12 "Sprint 3 landed" entry in `docs/STATUS.md`.

| Task | Outcome |
|---|---|
| 1 | `PS2X_PRESENT_FILTER=linear\|integer\|point` (`ce501fc`, `5ed4e31`). At the shipped 640x448 window the fit scale is 1.0, so all three modes are the same 1:1 blit — **none of the perceived softness is presentation**. Default stays `linear`. `tools_py/parity/resize_window.py` committed for driving a stretched window. |
| 2 | S3-a size split (`141ba9a`). **37 read sites / 50 field references**, all classified in research/14 §8; research/14 §3's `getDepthTarget` row corrected (it would have made an incomplete FBO at S > 1). Gate `s3a` PASS 3/3 is the sprint's pixel baseline. |
| 3 | S3-b native mirror + GPU resolve (`ff10102`, `1059bcf`), `PS2X_GS_SCALE_FILTER=point\|box`, inert at 1x. Review caught the staleness flag being set at batch setup rather than at the draw — dormant at 1x, wrong at S > 1. |
| 4 | S3-c `PS2X_GS_SCALE` (`219ab9c`, `466918b`), default 1, clamped 1..4. `m_presentWidth/Height` split into `m_presentHost*`/`m_presentNative*`, which settled research/14 §8.1 item 2 and §9.5 together. 1x gate `s3c_1x_final` PASS 3/3, title captures 99.8-100.0 against `s3a`. |
| 5 | S3-d verification (`66e8a07`, docs only). `s3d_2x_host` PASS 3/3; the GIF path green across `s3d_2x_gif` + `s3d_2x_gif_t2`; self-test 0 stale reads under both filters. Default stays 1. |
| 6 | research/15 (`c8f1bd0`): `0x70`, `0x52`, `0x66`, `0x40` and `0x34` decoded to implementation level, with the `0x2760` write conflict and the EFU semantics. |
| 7 | `0x70` and `0x40` native (`5ccb428`, `e27f415`, `e730c4d`): dump3 `ended` 9 -> 47, corpus 123 -> 161. Gate `fam4` PASS 3/3. |
| 8 | `0x34` native (`415fe36`): dump3 48, corpus **162/166**, residual 4. `N != 1` refused, and research/13's `N > 1` guess corrected in the process. |
| 9 | `--vram-diff` `checked=10 skipped=2` -> **`checked=14 skipped=0`** (`a590466`, `1c4a5c1`, `c2b00ee`), family C and the fourth family both covered; the tool's texture-in-blank-region warning now fails `./build.sh test`. `vu1dump4_prog_182` (1.488 %) held out with pixel evidence. |
| 10 | research/16 (`812063f`, `f1e4fc5`): the MPEG decode is **clean** (2067 consecutive pictures identical to an offline libavcodec decode); the blocks are lost in the shadow-VRAM -> GL mirror, with exact pictures and coordinates named. No fix, per the spike's decision rule. |
| 11 | This close-out: STATUS "Current state" rewritten, one dated Sprint 3 entry, README knobs, LOOP_PROMPT goal 3, these boxes, `PS2X_TEST_REPEAT=3 ./build.sh test` exit 0 (3 x 431/431, `checked=14 skipped=0`). The merge is the user's. |

**Where reality diverged from this plan**

1. **Task 7's scope was ruled down to `0x70`/`0x40`** (see the note on that task). `0x52` and `0x66`
   are a deliberate, documented residual of 4 programs, not unfinished work.
2. **The spec's "sharper HUD" expectation (Task 5 Step 1) was wrong** (see the note there). 2x buys
   rasterisation; the HUD, menus, briefings and title are textured quads and do not move.
3. **research/14's "15 touch points" headline was not reproducible** from the document and is
   superseded by 37 read sites / 50 field references (Task 2). `docs/STATUS.md`'s Sprint 2 entry
   carries the correction inline.
4. **Task 10's PCSX2 comparison run was never made** — the lock was contended and the task had
   lowest priority. The offline libavcodec decode of `INTRO_2.PSS` is a stricter reference and is
   what the conclusion rests on; the runner script is on disk if anyone wants the PCSX2 half.
5. **Two transition-gate intermittencies were discovered rather than planned for**, one measured
   (~1 in 5, pre-existing on the pre-scale binary) and one already known (the save-dialog probe
   flake). Both are in the STATUS flake list now; neither belongs to the scale work.
