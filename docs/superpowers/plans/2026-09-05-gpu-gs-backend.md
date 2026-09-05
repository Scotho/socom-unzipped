# GPU GS backend — design and plan (2026-09-05)

Decision (user, 2026-09-05): replace the CPU rasterizer with a GPU backend rather than optimise
`SampleTexture`. The menu runs at 13-17 fps on the CPU path (≈370 sprites, ~1M textured pixels
per frame); a GPU path also opens resolution scaling for M4.

## Constraints that shape the design
- **OpenGL 3.3 through raylib 5.5** (already linked; `rlgl.h` + `external/glad.h` give raw GL).
  No new dependency, no Vulkan/D3D bring-up.
- **The GL context lives on the main thread.** GIF packets are parsed on the game thread
  (`processVIF1Data → GifArbiter::drain → GS::processGIFPacket → backend->Submit`), so the backend
  cannot issue GL calls where `Submit` is called. It records a command stream on the game thread
  and replays it on the main thread before each present.
- **VRAM semantics must survive.** The engine uploads textures/video frames with image transfers,
  reads local memory back (local→host), and can use a framebuffer as a texture. The existing
  `GSCpuBackend` already models all of that (swizzled 4 MB VRAM, transfers, CLUT). Keep it as the
  VRAM model; make the GPU a drawing accelerator on top.

## Architecture
```
game thread                                   main (render) thread
GS frontend ──Submit/Transfer/Present──► GSGlBackend (records Cmd stream) ──swap──► replay:
  ├─ m_cpu  (GSCpuBackend, authoritative VRAM: uploads applied immediately; reads served here)
  └─ dirty RT pages ── sync-on-read ◄─────── readback (glReadPixels → m_cpu.WriteVram)
                                              ├─ m_shadow (GSCpuBackend fed by replayed transfers;
                                              │            texture decode source)
                                              ├─ RT cache: (fbp,fbw,psm) → FBO+RGBA8 texture,
                                              │            depth textures keyed by zbp
                                              ├─ texture cache: decode key → GL texture, page-gen
                                              │            invalidation; RT-as-texture by page overlap
                                              └─ present: RT of DISPFB → raylib DrawTexturePro (no readback)
```
- Command stream: `Submit(batch)` (copies the 3-vertex batch + draw state), `BeginTransfer`,
  `UploadImage(bytes)` (copied), `WriteVram`, `ClearFramebuffer`, `Present(request)`, `Readback`
  (blocking handshake), `Reset`. Double-buffered vector, swapped under a mutex once per host frame.
- Game-thread reads (`ReadVram`, `SnapshotVram`, local→host, local→local sources) that touch
  GPU-dirty pages first post a `Readback` and wait for the main thread to download the dirty RTs
  into `m_cpu`'s VRAM. Rare in menus; correct in general.
- Draw batching on replay: vertices accumulate while the draw key (context regs, prim flags,
  texture key) is unchanged; a change/present/readback flushes one `glDrawArrays`.
- Shader (GLSL 330): vertex = GS pixel coords (12.4 already converted by the frontend) minus
  XYOFFSET → NDC over the RT size; z/2^32 → depth. Fragment = TFX modulate/decal/highlight(2),
  TCC, FST vs ST/Q, wrap/region clamp/repeat, alpha test (ATE/ATST/AREF, AFAIL≈discard except
  FB_ONLY/RGB_ONLY drawn), fog, FBA. Alpha blend = GS `(A-B)*C+D` mapped to `glBlendFuncSeparate`
  /`glBlendEquation` with **dual-source** alpha (`As` = min(2·alpha,1) on output 1) and
  `glBlendColor` for FIX. Depth: ZTE/ZTST → `glDepthFunc`, ZMSK → mask. FBMSK → `glColorMask`
  when it is per-channel 0x00/0xFF, otherwise ignored (logged once).
- Texture decode: per texel `GSMem::Read*` from the shadow VRAM + CLUT (CSM1) into an RGBA8
  buffer, TEXA applied; keyed by (tbp0,tbw,psm,tw,th,cbp,cpsm,csm,csa,texa,texclut); invalidated
  when any covered page's generation (bumped by replayed transfers/writes/clears) is newer.
  If the pages overlap a GPU-dirty RT, the RT is first downloaded into the shadow VRAM.
- Presentation: `Present` records the request; on replay the RT matching DISPFB's FBP becomes the
  host frame; `PS2Runtime::run` draws its GL texture with `DrawTexturePro` (flipped like a raylib
  RenderTexture). With `PS2X_FRAME_DUMP` set, `Present` blocks for a readback so the counters and
  PPM dumps keep working (diagnostic only).
- Selection: `PS2X_GS_BACKEND=gpu|cpu` (default gpu once the menu renders correctly).

## Stages
1. [x] Skeleton: command stream, RT cache, untextured triangles/sprites, depth, blend table,
       presentation of the RT, `PS2X_GS_BACKEND`. Verify: menu frames (colour boxes) at 60 fps.
2. [x] Textures (2026-09-05, commits 939655b..): decode cache + CLUT + TEXA, wrap/region modes, bilinear, ST/Q, TFX/TCC,
       RT-as-texture, uploads into RT pages refresh the RT. Verify: the slot dialog matches the
       CPU screenshot; video frames (image uploads) show; `PS2X_FRAME_DUMP` counters work.
3. [ ] Fidelity: alpha test AFAIL modes, DATE, fog, FBMSK/FBA, 16-bit targets, Z16/Z24 formats,
       field/interlace present, PMODE blending of two circuits.
4. [ ] Readback sync paths (local→host, local→local, ReadVram on dirty pages) exercised; make
       `gpu` the default; remove the CPU path from the hot loop; measure with the timeline recipe.
5. [ ] Resolution scaling (RT scale factor) — after M4 content renders.

## Known approximations (v1)
- `Ad` blend factor uses the RT's stored alpha (PS2 doubles it); `Cd*(1+C)` forms clamp to `Cd`.
- Dual-source blending needs GL 3.3 `ARB_blend_func_extended` (core) — required.
- Depth textures per ZBP are not aliased with colour pages.
- The debug panel's frame preview is empty in GPU mode (no per-frame readback).

## Status 2026-09-05 16:40
Stages 1-2 landed: the shell renders on the GPU at a steady 60 fps (`PS2X_GS_STATS=1` prints
elapsed/fps, replay timings, distinct blend/test states). Diagnostics: `PS2X_GS_DUMP_TEX=<dir>`
(decoded textures), `PS2X_GS_TRACE_CMDS=<skip presents>` (ordered replay trace),
`PS2X_GS_TEX_FROM_CPU=1` (decode from the game-thread VRAM; slow, experiment only).
Observed: SOCOM II streams every UI texture through one slot (tbp 0x3bf7, clut 0x3bf3) so the
texture cache re-decodes per draw (fine at 60 fps, ~150 draws/frame); the panel textures carry
alpha 0 palettes and rely on vertex alpha. Differences vs the CPU path still to verify against
PCSX2: the title logo stays visible behind the slot dialog on the GPU path.
