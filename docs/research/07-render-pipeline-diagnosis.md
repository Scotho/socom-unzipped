# Render pipeline diagnosis (2026-09-05)

The engine boots and runs its shell/main loop, but the screen stays black. This note
records the end-to-end instrumentation that localized why, so the next agent can resume
without redoing the measurements.

## How to reproduce the measurements

Build the runtime, then run with the frame dump:

```
./build.sh runtime
PS2X_FRAME_DUMP=logs/frames PS2X_PC_SAMPLER=5 dist/socom2.exe game/disc/socom2_game.elf
```

`PS2X_FRAME_DUMP=<dir>` (added in `gs_frontend.cpp::latchHostPresentationFrame`) prints a
`[frame-dump]` line every 15 presents and writes a PPM every 60. The line carries the whole
pipeline's live counters (all env-gated globals defined in `gs_frontend.cpp`, incremented in
`ps2_vif1_interpreter.cpp`, `vu/ps2_vu1_core.cpp`, `gs_cpu_backend.cpp`, `ps2_memory.cpp`):

```
frame  nonBlack  dispFbp srcFbp  enq enqQwc  vif1codes vif1bytes  mscal vuInsn mpgB xgkick  gsSubmits pixels pixFbp0 nbWrites someNZfbp
```

## What the counters say (steady state, ~frame 2340)

| Counter | Value | Meaning |
|---|---|---|
| `vif1codes` / `vif1bytes` | 129k / 1.5 MB | VIF1 DMA reaches `processVIF1Data` fine — geometry upload path works |
| `mscal` | 1047 | VU1 microprograms are launched (MSCAL VIFcode) |
| `vuInsn` | 87k | the VU1 interpreter executes real instructions (~84 per program) |
| `mpgB` | 15656 | ~2000 VU instructions of microcode uploaded via VIF MPG (code buffer is populated) |
| **`xgkick`** | **0** | **no microprogram ever executes XGKICK — no geometry is emitted to the GS** |
| `gsSubmits` | 1048 | ~0.45 draws per frame — essentially only the occasional clear |
| `pixels` / `pixFbp0` | 12.6M / 12.6M | every rasterized pixel goes to framebuffer page 0 |
| **`nbWrites`** | **0** | **every rasterized pixel is black** — the draws are black fills/clears |
| `someNZfbp` | 0 | nothing is ever drawn to any page other than 0 (incl. the displayed page 140) |
| `dispFbp` | 0 / 140 | the game double-buffers (pages 0 and 140) and flips DISPFB correctly |

## Conclusion

Every layer *below* the game is correct: VIF1 feed, VU1 launch + execution, the software
rasterizer (it faithfully draws the black clears it is given), framebuffer addressing, the
double-buffer flip, and host presentation. No VU reserved-instruction errors fire, so the
microprograms run clean.

The gap is *above*: the game is looping in its shell render dispatch (`FUN_00339de0`) but only
issues per-frame black clears. It is **not** submitting menu geometry, and the VU1 programs it
does run are utility programs (matrix/anim/cull) that contain no XGKICK. So the game has not
advanced to a state that draws content.

## What it is NOT

- Not a VIF1/MFIFO/DMA bug (that was the previous blocker; fixed via I_STAT + the 94 `[mmio]`
  corrections). VIF1 delivers 1.5 MB/frame to the interpreter.
- Not a rasterizer or presentation bug — pixels are written and presented; they are just black.
- Not an intro-movie/IPU wait — no MPEG/IPU/PSS activity or disc streaming in the log.
- Not a DBCMAN spin — only 3–4 DBCMAN RPCs at init, then silence (the game accepted the stub
  replies and moved on).

## Prioritized next investigations

1. **Controller/pad gate (most likely, and a required feature).** The shell state machine
   probably will not leave the attract/title state without a connected DualShock2 reporting
   input. `DBCMAN` (`ps2xIOP/src/modules/dbcman.cpp`) only answers the version RPC; RPCs
   0x80001301/0x80001302/0x80001304 return an untouched receive buffer. Implement the pad
   path (libpad/PADMAN or the DBCMAN pad broker): report one connected pad, DualShock2 mode,
   neutral state with pressure. Then re-measure — if `gsSubmits`/`nbWrites` jump, the menu is
   drawing.
2. **Trace the shell state machine.** `FUN_00339de0` selects the active screen from
   `DAT_0049e888[state]`. Find who advances `state` and what condition it waits on. Sampling
   a candidate state global over time will show whether the game is stuck or slowly advancing.
3. **Only if 1–2 show the game believes it is drawing content but still no XGKICK:** dump the
   uploaded VU1 microcode at MSCAL time and confirm the render programs (which must contain
   XGKICK) are being uploaded and MSCAL'd. If they are and still no XGKICK, inspect the VU1
   lower-op decode for the render programs' specific encodings.

## Instrumentation left in place (all env-gated, zero cost when `PS2X_FRAME_DUMP` unset)

- `gs_frontend.cpp`: frame dump + counter print; globals `g_gsSubmitCount`, `g_vif1CodeCount`,
  `g_vif1BytesCount`, `g_mscalCount`, `g_xgkickCount`, `g_vif1EnqCount`, `g_vif1EnqQwc`,
  `g_gsPixelCount`, `g_gsPixToFbp0`, `g_gsSomeNZFbp`, `g_gsNonBlackWrites`, `g_vuInsnCount`,
  `g_vuMpgBytes`.
- `ps2_vif1_interpreter.cpp`: VIF1 code/byte + MSCAL + MPG-byte counters.
- `vu/ps2_vu1_core.cpp`: XGKICK + VU-instruction counters.
- `ps2_memory.cpp`: VIF1 enqueue counters.
- `gs_cpu_backend.cpp`: pixel-write, per-fbp, and non-black-write counters.

## Resolution (2026-09-05, later): the render pipeline is correct — the game is idle

Deeper VU1 tracing (`PS2X_TRACE_VU`, in `vu/ps2_vu1_core.cpp`/`ps2_vu1_lower.cpp`) settled the
question. Counters: every MSCAL'd program (`mscalXg == mscal`) contains a reachable XGKICK
(`xgReach > 0`), the XGKICK decode path is correct (case 0x6C → `startXgkick`), yet `xgDec == 0`
(XGKICK never decoded) and `xgkick == 0`.

Per-program trace of the render program (startPC=0x0, executed identically ~748×):
- pc=0x0 `XGKICK`-adjacent setup: `XTOP` reads the VIF1 double-buffer TOP into vi[1].
- pc=0x8/0x10 `ILW` load a command header from VU data memory at `data[TOP]`.
- pc=0x30 `IBEQ` (target 0x118) **branches over the XGKICK at 0x50**, program ends at 0x1b50 in
  82 steps having emitted nothing.
- The input header at TOP (0x1a8 and 0x2d4, both double-buffers) is `[0,0,0,1]` — an empty/skip
  command. VIF double-buffering (BASE/OFFSET/TOP toggle) and unpack-to-TOPS addressing check out.

So the VU program is **correctly** deciding there is nothing to draw: the game is feeding it an
empty display list. The software GS, rasterizer, framebuffer, presentation, VIF1 feed, VU1
execution and XGKICK decode are all functioning. The black screen is because the game is sitting
on a pre-content screen with no geometry to submit — a **game-state** condition, not a rendering
bug.

### Consequence for priorities
The gate to visible graphics is advancing the game past its idle/attract state, which means the
**controller/game-state path** (libpad2 + libdbc/DBCMAN — see `08-controller-and-dbcman.md`), not
the GS/VU pipeline. Once the game reaches an interactive screen it will submit real display lists
and XGKICK will fire on its own. The instrumentation added here (`PS2X_TRACE_VU`, `PS2X_FRAME_DUMP`
counters) is the tool to confirm that: when `xgkick`/`nbWrites` rise, content is drawing.

## Resolution 2 (2026-09-05 14:30) — why the shell never XGKICKed, and the fix

The earlier conclusion ("the game feeds empty display lists; XGKICK fires when it reaches an
interactive screen") was only half right. At the menu the VU1 programs *did* receive real UI
geometry and still never kicked. Tracing them (`PS2X_TRACE_VU=15000`, `tools_py/vu1dis.py`):

- The shell microprogram is a command interpreter: `XTOP vi1`, then a command list at VU data
  qword 340 dispatched through a jump table at 0x1ba0 (`JR vi5+884`). Handlers seen for a UI quad:
  0xb20 int→float vertices, 0x1638 **backface cull**, 0xdf8 transform/divide, 0x5d8 template
  fill, 0x1440 lighting, 0x1780 build GIF packet + `XGKICK vi2` (0x1920).
- The cull is `dot(eye - v0, normal)` via `MULAx/MADDAy/MADDz.w` then `FMAND vi13, 16` (MAC sign
  flag of w) → `IBGTZ` clears the triangle's visible bit. Both triangles were culled because the
  eye position (VU data qword 30, loaded by `LQ vf26, 30(vi0)`) contained `0x0044ca90 0 0 0` — a
  guest RAM address, not a vector.
- That qword is uploaded by a **REF DMAtag whose upper 64 bits hold the VIFcodes**. The chain
  walker (`ps2_memory.cpp`) injected tag upper halves unconditionally for ids 1/2/5/6/7 and never
  for REF/REFS/REFE; hardware (and PCSX2's `_chainVIF1`) transfers them for every tag iff
  `CHCR.TTE`. Fixed: TTE-gated, all ids. Also fixed: DMAtag ADDR bit 31 (SPR) was masked away.
- With the gate in place the *boot* chains broke: the HLE libdma (`Support.h submitDmaSend`)
  started chains with CHCR 0x185 (TIE) instead of Sony's 0x145 (TTE), so the END tags carrying
  `STBASE 0x1a8 / STOFFSET 0x12c` and `NOP / MPG` stopped delivering them and the microcode was
  parsed as VIFcodes (`[vif1] cmd=0x08 ...` = `ILW` words; TOPS became 0x3fd; index data flooded
  VU memory; `[VU1 xgkick] packet overrun`). Fixed to 0x145 (chain) / 0x101 (normal).

Result: XGKICK fires (`xgkick=6480` by frame 825), the slot/profile dialog draws over the menu
movie. The remaining cost is `GSCpuBackend::SampleTexture` (swizzled VRAM read + CLUT lookup per
texel, ×4 bilinear) at ~1M textured pixels/frame → 13-17 fps. The lldb backtrace at "the stall"
was `sub_00350AB0 (FIFO kick) → Store8 → runSprDma → processVIF1Data → GifArbiter::drain →
GS::vertexKick → DrawSprite → SampleTexture`: slow, not stuck.

Timeline recipe (sampler every 3 s vs frame-dump): `awk '/frame-dump/{...} /pc-sampler/{t+=3; print}'`
gives frames/second and GS submits/pixels per interval — see STATUS 14:30.
