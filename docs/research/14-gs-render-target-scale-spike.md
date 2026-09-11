# 14 — GL render-target scale spike (`PS2X_GS_SCALE`): 1:1 assumptions and the go/no-go

Sprint 2, task 3, steps 1-2 (2026-09-11). Read-only spike: no code was changed, nothing was built
or run. Sources: `third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_gl_backend.cpp` (2446 lines),
`include/runtime/gs/gs_gl_backend.h`, `src/lib/gs/gs_frontend.cpp`, `src/lib/ps2_runtime.cpp`.
All bare `NNN` line references below are `gs_gl_backend.cpp` at commit `2c89aac`.

## Decision (short)

**NO-GO for step 3b in Sprint 2.** Both halves of the brief's rule fail:

* **Touch points: 15 edit sites across 9 subsystems** (rule: ≤ 8), and that count *understates*
  the work, because `RenderTarget::width/height` is a single field that today means both "GL texel
  size" and "native GS pixel bound" and is read at ~22 sites (§3). Splitting it is a mechanical but
  wide refactor of exactly the code that owns the page/row semantics the game depends on.
* **Two readback paths need a downsample**, and one of them is precisely the page-copy path the
  brief names as the danger: `downloadRenderTargetToShadow` (1305) feeds `decodeTexture`, which is
  how SOCOM II's title labels are produced (STATUS 2026-09-09 02:15/12:10). The other,
  `downloadRenderTargetToCpu` (1369), writes the *authoritative* guest VRAM.

Carried to Sprint 3 with the staged plan in §6.

## 1. How the backend maps GS pixels to GL texels today

One render target per FRAME base page, always allocated `kMaxRtWidth` x `kRtHeight` = 1024 x 1024
RGBA8 (955-959) regardless of FBW, so a GS pixel `(x, y)` in that buffer is GL texel `(x, y)` in
the target's colour texture — for every FBW the game ever selects for that base. Everything else in
the file leans on that identity:

* vertices are `v.x - (ofx >> 4)` in float GS pixels and the vertex shader normalises by
  `uRtSize = (rt.width, rt.height)` (207, 2023-2024, 2281);
* the scissor and viewport are handed GS pixel coordinates unmodified (1261-1265, 2169-2176);
* shadow VRAM -> GPU uploads (`refreshDirtyRows`, 1152) write GS pixel `(x, y)` to texel `(x, y)`
  with `glTexSubImage2D`;
* GPU -> shadow/CPU downloads (1305, 1369) read `glReadPixels(0, 0, rt.width, usedHeight)` and
  index `pixels[y * rt.width + x]` as GS pixel `(x, y)`;
* a render target sampled as a texture (`resolveTexture`, 1930-1953) hands the shader
  `uTexSize = (rt.width, rt.height)` and lets the native texel coordinates normalise against it;
* presentation blits the top-left `display_w x display_h` rectangle of the target (1556-1583) and
  `ps2_runtime.cpp:2568-2604` draws that sub-rectangle of the full-size texture aspect-fit.

The *bookkeeping* (dirty bands, `usedHeight`, `gpuRowFirst/Last`, page spans) is all in native GS
rows and must stay that way at any scale, because it is VRAM addressing, not rasterisation.

## 2. Enumeration

"Risk" is **semantic** when the site can change bytes the guest can read back out of GS memory,
**cosmetic** when it only affects what is on screen, **perf/mem** when it is a cost not a
correctness issue. `S` = integer scale, `N` = native, `H` = host (= `N * S`).

### 2.1 Render-target / depth-target allocation

| Site | 1:1 assumption | Change for S | Risk |
|---|---|---|---|
| 22-23 `kMaxRtWidth`/`kRtHeight` | RT texel size == native buffer extent (1024x1024) | keep as the *native* extent; add `kScale` from `PS2X_GS_SCALE` (clamped, default 1) and `rt.hostWidth/hostHeight = native * S` | none (new plumbing) |
| 955-959 `getRenderTarget` | `rt.width/height` allocated at the native extent | allocate `glTexImage2D` at `N*S`; keep `rt.width/height` native, add host fields | perf/mem: 4 MB -> 16 MB per colour target at S=2 |
| 972-976 seed (`dirtyRowLast = 448`, `dirtyMask` bands 0..13) | seed rows are native | unchanged | none — confirms the bookkeeping is native |
| 980-999 `getDepthTarget` | depth texture sized from `rt->width/height`; `std::vector<float> zeros(w*h)` | must follow the host size; the zero-fill becomes 16 MB per depth target at S=2 | perf/mem; a one-off 16 MB heap spike per new ZBP |
| 2163 `getDepthTarget(zbp, rt->fbw, rt->width, rt->height)` | passes the native extent as the texel size | pass the host size | correctness: must match the colour size or the FBO is incomplete |

### 2.2 Vertex transform, scissor, viewport

| Site | 1:1 assumption | Change for S | Risk |
|---|---|---|---|
| 2023-2024 `appendVertex` | `out.x/y` are native GS pixels; the shader divides by `uRtSize` | multiply by `S` after the `xyoffset >> 4` subtraction (the `>> 4` stays: XYOFFSET is 1/16 px and the subtraction is native-space) | cosmetic if wrong, but it is the whole point of the change |
| 2026-2040 `appendVertex` s/t/q/z | texel coords and Z are format-space, not screen-space | unchanged | none — textures stay native |
| 2071-2145 `executeSubmit` sprite/point/line expansion | `+1.0` point size and `±0.5` line half-width are native pixels | unchanged (pre-scale, so a 1-native-px line still covers `S` host px) | none |
| 2169 `glViewport(0,0,rt->width,rt->height)` | viewport == RT texel size | host size | cosmetic |
| 2175-2176 `glScissor` | SCISSOR is in native GS pixels | `x0*S`, `y0*S`, `(x1-x0+1)*S`, `(y1-y0+1)*S` | **semantic-adjacent**: an off-by-one leaks draws into rows that later get downloaded into VRAM |
| 1261-1265 `executeClear` viewport + scissor | same | same | same |
| 2281 `uRtSize` | normalises native x/y by the native RT size | host size (consistent with the scaled vertices) | cosmetic |

### 2.3 Dirty tracking (upload marks) — *no change needed*

| Site | 1:1 assumption | Change for S | Risk |
|---|---|---|---|
| 453-465 `markRtDirtyFromFrame` | `min(kRtHeight, scissor.y1+1)` is a native row count feeding `pageSpan` | unchanged | none |
| 1084-1149 `refreshRenderTargetsFromShadow` (1090, 1096, 1111, 1117, 1146) | `kRtHeight` bounds native rows; `dirtyRects` and the 32-row `dirtyMask` bands are native | unchanged | none |
| 1271-1272, 2178-2179 `usedHeight` / `noteGpuRows` calls | native rows | unchanged | none |
| 1280-1302 `noteGpuRows` page arithmetic | native rows -> pages | unchanged | none |

This is the good news: the page/row semantics the game depends on are already expressed in native
units and survive a scale untouched. The damage is all at the native<->host boundary.

### 2.4 Shadow VRAM -> GPU upload (`refreshDirtyRows`, 1152)

| Site | 1:1 assumption | Change for S | Risk |
|---|---|---|---|
| 1176 `w = min(rt.width, rt.fbw*64)` | clamps the native row width with the RT texel width | must clamp with the *native* extent; a scaled `rt.width` silently stops clamping | **semantic**: an unclamped `w` reads past `FBW*64`, i.e. into the next page row (the x=384 movie seam, see the comment at 1350-1353) |
| 1188-1203 exact-rect upload | `glTexSubImage2D(x0, y0, x1-x0, y1-y0)` in native coords | destination rect `*S`; the pixel buffer nearest-expanded to `S x S` per native pixel (or uploaded 1x to a staging texture and blit-upscaled) | cosmetic + perf: `S^2` upload bytes on the movie path (a full frame every frame) |
| 1214-1241 band upload | same, plus `y1 = min(end*32, rt.height)` mixing native rows with the texel height | same, and `rt.height` -> native extent | same |
| 1194 `y1 = min(r.y1, rt.height)` | native row vs texel height | native extent | correctness of the clamp |

Note the asymmetry this creates: an upload *destroys* sub-native detail in the rows it covers,
because the shadow only holds native pixels. That is already true of the movie path and is fine
there, but it means any RT region the game re-uploads loses the S× draw beneath it.

### 2.5 GPU -> shadow readback (`downloadRenderTargetToShadow`, 1305) — **the blocker**

| Site | 1:1 assumption | Change for S | Risk |
|---|---|---|---|
| 1307-1308 `h = min(usedHeight, rt.height)`; buffer `rt.width * h` | native rows sized against the texel height | host rect `(N_w*S, h*S)`, buffer `S^2` larger | perf: 4x the PCIe download at S=2; this path was ~26% of the GL thread before the RT-as-texture shortcut (STATUS 2026-09-09 13:30) |
| 1328 `glReadPixels(0, 0, rt.width, h)` | reads native pixels directly | read the host rect | perf |
| 1333 `xEnd = min(rt.width, fbw*64)` | native clamp via the texel width | native extent | **semantic** (the same page-row overrun as 1176) |
| 1355-1362 `pixels[y*rt.width+x]` -> `writeVramRaw(..., x, y, p)` | GS pixel `(x,y)` == texel `(x,y)` | **needs a downsample**: box-average or point-decimate the `S x S` block at `(x*S, y*S)` into one native texel | **semantic + content-altering.** This is the path that produces the title labels: the game draws into a buffer and the buffer's pages are later decoded as a texture. A box filter changes those bytes versus native; point decimation is exact only when the `S x S` blocks are uniform, which holds for axis-aligned native-resolution blits but *not* for the hooked VU1 host triangles the scale exists to sharpen. |
| 1342-1349 dirty-row skip | native rows | unchanged | none |

### 2.6 GPU -> CPU readback (`downloadRenderTargetToCpu`, 1369) — **the second blocker**

The same five issues as §2.5 at 1371-1372, 1380, 1384, 1401-1408, with a harder consequence: this
one calls `m_cpu->WriteVram` on the *authoritative* VRAM the guest reads through `ReadVram` (563),
`SnapshotVram` (582), local->host transfers (`BeginTransfer`, 481-489) and `ConsumeLocalToHostBytes`
(558). Whatever filter is chosen here is what the guest sees when it reads back a pixel it drew.

### 2.7 Render target sampled as a texture (`resolveTexture`, 1909)

| Site | 1:1 assumption | Change for S | Risk |
|---|---|---|---|
| 1943 `if (width > rt.width \|\| height > rt.height) continue;` | native TW/TH vs texel size | compare against the native extent | cosmetic (a scaled `rt.width` only makes it more permissive) |
| 1946-1947 `outWidth/outHeight = rt.width/rt.height` | the shader normalises *native* texel coords by the target's size (comment at 1924-1929) | `uTexSize` = host size **and** the texel coordinates pre-multiplied by `S` — a new `uTexScale` uniform applied to `tc` in the fragment shader (240-246) and to `uRegion` (2309-2310), since REGION_CLAMP bounds are native texels | **cosmetic but load-bearing**: get it wrong and every RT-as-texture draw (the full-screen display copies) samples the wrong quarter of the source |
| 240-246 fragment shader `wrapCoord` / `texture(uTex, vec2(u,v)/uTexSize)` | one texel per GS pixel for *both* decoded textures and RT textures | the two cases must diverge (`uTexScale = 1` for decoded textures, `S` for RT textures) | cosmetic |
| 1715-1907 `decodeTexture`, 1819-1830 `GSMem::ReadSpan` | textures are decoded from shadow VRAM at native resolution | unchanged — textures stay 1x | none (and this is why the scale buys sharper *geometry*, not sharper *texels*) |

### 2.8 Local-to-local copies

| Site | 1:1 assumption | Change for S | Risk |
|---|---|---|---|
| 1011-1020 `executeTransfer` direction 2 | the shadow performs the copy in native VRAM, then `refreshRenderTargetsFromShadow` marks the destination rows dirty so the GPU re-reads them | no code change | quality: a local-to-local copy is a native round trip (GPU -> §2.5 downsample -> VRAM -> §2.4 upscale), so the destination loses all S× detail. Correct, just not sharp. |
| 477-489 `BeginTransfer` source sync | posts a `Readback` before the copy so the source pages are current | unchanged | none — but it drags §2.6 in: every local-to-local read of a drawn buffer pays the downsample |

### 2.9 Presentation

| Site | 1:1 assumption | Change for S | Risk |
|---|---|---|---|
| 1556-1557 `m_presentWidth/Height = min(display_wh, rt->wh)` | the DISPLAY size is in native pixels and indexes the RT directly | `min(display*S, host)` | cosmetic |
| 1558-1572 present copy texture | sized from `rt->width/height` | host size (automatic once the RT is scaled) | perf/mem: another 16 MB at S=2 |
| 1581-1583 `glBlitFramebuffer` | src rect == dst rect in native pixels | both rects in host pixels | cosmetic |
| 1618-1645 circuit-2 copy + blit | same | same | cosmetic |
| 693-699 `HostFrameTexture` + `ps2_runtime.cpp:2568-2604` | `srcRect` is `presentWidth x presentHeight` of a `hostFullW x hostFullH` texture, drawn aspect-fit | works unchanged *provided* both pairs scale consistently; the aspect-fit `DrawTexturePro` then minifies `H` -> window, which is the actual sharpness win | cosmetic; `GL_LINEAR` on the present copy (1567-1568) already gives a reasonable box-ish minification |
| 1700-1708 `PS2X_FRAME_DUMP` readback into `m_presentPixels` | a fixed `kHostFrameWidth x kHostFrameHeight` = 640x512 buffer, `memcpy` per row | must downsample `H` -> 640x512, or `Present` (541) silently hands back the top-left quarter | **semantic for the harness**: `PresentationFrame::pixels` is what the `tools_py` frame counters consume |

### 2.10 CPU backend interplay and debug dumps

* `PS2X_GS_BACKEND=cpu` (`gs_frontend.cpp:9-12`) selects `GSCpuBackend`, which rasterises into GS
  memory itself and **stays 1x unconditionally**. `PS2X_GS_SCALE` must be a no-op there and the
  banner at 328 should say so. `ps2xTest/src/main.cpp:59` and `tools/vu1_replay.cpp:250` both force
  the CPU backend, so the unit tests and the VU1 replay tool are unaffected by any of this.
* `PS2X_GS_DUMP_DISPLAY` (1520-1551) reads `rt->width x 448` and writes three PPMs (gpu / shadow /
  cpu) that are compared pixel-for-pixel by eye. At S>1 the "gpu" PPM would be a different size
  from the other two; it needs the same downsample as §2.5 or an explicit marker in the file name.
  Cosmetic (diagnostics only) — but it is the tool used for exactly this class of bug.
* The single-pixel probes at 1487, 1664-1671, 2362-2371, 2410-2412 (`PS2X_GS_TRACE_PRESENT`,
  `PS2X_GS_GL_DEBUG_PSM`, `PS2X_GS_PROBE`) hard-code native coordinates (320,224 / 320,200 /
  100,50 ...) and would sample the wrong place at S>1. Cosmetic; listed for completeness, not
  counted as touch points.

## 3. The real cost: `RenderTarget::width/height` is overloaded

The field pair is used in two incompatible senses and the compiler cannot tell them apart:

* **GL texel size** — 959, 1261, 1328, 1380, 1527, 1566, 1626, 2169, 2281, plus the
  `pixels[y * rt.width + x]` strides at 1357 and 1403;
* **native GS extent** — 1176, 1194, 1217, 1307, 1333, 1371, 1384, 1524, 1556-1557, 1632-1633,
  1943, 2163.

That is ~22 read sites, of which the 12 "native extent" ones become wrong the moment the field is
scaled — and four of them (1176, 1333, 1384, plus 1194/1217) are the clamps that exist *because* of
previously-fixed VRAM corruption bugs (the x=384 movie seam; the stale-band overwrite). Doing this
safely means splitting the field into `nativeWidth/nativeHeight` and `hostWidth/hostHeight` and
re-auditing every one of them. That is a Sprint-3-sized refactor with a real regression surface in
the most bug-scarred code in the backend, not a bounded 8-point change.

## 4. Is there a downsample that does not alter content?

Both readbacks (§2.5, §2.6) need one. The options:

* **Point decimation** (take texel `(x*S, y*S)`) — bit-exact whenever the `S x S` block is uniform.
  That holds for native-resolution axis-aligned sprite blits and clears, i.e. for most of the
  2D/UI/movie traffic, *including* the title-label page copies as they exist today. It does **not**
  hold for the hooked VU1 host triangles, whose sub-pixel edges are the reason for the scale: their
  readback would differ from native at every edge texel.
* **Box average** — never bit-exact for any non-uniform block. It would change the title-label
  pages relative to native even where point decimation would not, and it introduces colours that
  the 16-bit `rgba8888To5551` round-trip at 1358/1404 then quantises differently again.

So the honest answer: point decimation keeps the *known* dangerous path (label pages) exact, but no
filter keeps host-drawn geometry exact through a readback, and we have no inventory of which pages
the game reads back for which purpose. The brief's condition ("no readback path needing a downsample
filter that affects gameplay-visible content") is not met — it is met only for a subset we cannot
currently enumerate.

## 5. Cost estimate at S=2 (for the Sprint 3 ticket)

* Memory: each colour target 4 MB -> 16 MB, each depth target 4 MB -> 16 MB, plus two present-copy
  textures. The backend keeps one target per FRAME base page seen; a handful of targets plus depth
  puts S=2 in the 150-300 MB range and S=4 out of reach on modest GPUs. A scale cap and an eviction
  policy would be needed.
* Bandwidth: §2.5/§2.6 downloads and §2.4 uploads all scale by `S^2`. The download path was measured
  at ~26% of the GL thread before the RT-as-texture shortcut removed most of it; any frame that
  still takes it (movies, local-to-local copies, guest VRAM reads) pays 4x at S=2.
* The `std::vector<float> zeros` depth initialiser at 996 becomes a 16 MB allocation per new ZBP.

## 6. Sprint 3 outline (staged, each stage independently shippable)

1. **S3-a — de-overload the field (no behaviour change).** Split `RenderTarget::width/height` into
   `nativeWidth/nativeHeight` and `hostWidth/hostHeight`, both 1024 for now, and fix every one of
   the ~22 sites in §3 to name the one it means. The gate must be bit-identical (captures ≥ 99 vs
   `native_default`). This is the de-risking step and is worth doing even if the scale never lands.
2. **S3-b — GPU-side resolve.** Give each scaled target a 1x "native mirror" texture and resolve
   `host -> native` with a single blit/shader pass instead of a CPU loop, so §2.5 and §2.6 keep
   reading a native-sized rect and the `S^2` PCIe cost disappears. The filter choice (point vs box)
   then lives in one place and is switchable (`PS2X_GS_SCALE_FILTER`).
3. **S3-c — `PS2X_GS_SCALE` on top of S3-a/S3-b.** Allocation, `appendVertex`, both scissors, the
   two upload loops, `uTexScale` for RT-as-texture, presentation rects, frame-dump downsample.
4. **S3-d — verification.** `PS2X_GS_SCALE=1` full gate green with title captures ≥ 99 against
   `native_default` (S=1 must be bit-identical by construction, not by luck); then
   `PS2X_GS_SCALE=2 PS2X_VU1_HOST_DRAW=1` gate green with the mission sheet's HUD visibly sharper.
   Note for whoever writes that ticket: at S=2 the `compare.score ≥ 99` criterion **cannot** apply —
   captures come from `PS2X_HOST_SCREENSHOT_LATEST`, a window-sized GL readback
   (`tools_py/parity/winshot.py:61-66`), so a sharper frame scores *lower* against `native_default`
   by design. The S=2 gate must be "gate green + a human looks at the sheet"; the ≥ 99 bar is for
   S=1 only.

**Cheaper alternative worth pricing first (S3-0):** the sharpness complaint may be mostly the final
aspect-fit upscale in `ps2_runtime.cpp:2585-2604`, which stretches a 640x448 texture to the window
with `GL_LINEAR` (present-copy filter, 1567-1568). An integer-scale-then-fit, or a sharp-bilinear
sampler at present time, costs ~10 lines, touches zero GS semantics, and would tell us how much of
the perceived softness is the render resolution at all. It does not sharpen geometry, but it is a
one-evening experiment that changes nothing the guest can observe.

## 7. Open questions

* Which VRAM pages does SOCOM II actually read back for non-display purposes? `PS2X_GS_TRACE_PAGES`
  (28-46) plus the `[gs-pages] download gpu->cpu` line at 1385-1391 could produce that inventory in
  one mission run; without it, "no readback path affects gameplay-visible content" cannot be
  asserted, only hoped.
* Does anything downstream of `ConsumeLocalToHostBytes` (558) hash or compare frame-buffer bytes
  (memory-card screenshots, the online client)? If so, §2.6's filter is a correctness question, not
  a quality one.
* Would per-target opt-in scaling (scale only targets never downloaded or decoded from, demote to
  1x on first read) bound the risk enough to justify the extra state machine? It does not reduce
  the §3 refactor, so it is only interesting after S3-a.
* `getRenderTarget` keys targets by base page and takes the maximum stride (938-956). At S>1 a
  target whose FBW changes mid-frame still maps correctly, but the host rect for uploads/downloads
  is derived from `fbw * 64 * S`; that deserves an explicit test in S3-c.
