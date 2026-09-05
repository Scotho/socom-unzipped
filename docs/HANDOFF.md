# Handoff — SOCOM II PC recompilation

Read this first, then `docs/STATUS.md`. This is the fast on-ramp for a new agent. Work in
**bounded steps**: one hypothesis → one build → one run → read counters → commit. Do not open more
than one deep subsystem at a time.

## The goal (unchanged)
A native SOCOM II EXE for modern PCs with controller + online play to a self-hosted server, built
by static recompilation (no emulator). Stop only once we've booted, reached a mission or an online
lobby we host. This is copyrighted-game work confined to `socom_pc/`; game assets are gitignored.

## One-paragraph state
With the pad enabled (`PS2X_SOCOM2_PAD=1`) the game boots, plays the Sony/intro movies, START skips
the intro, and **the shell UI renders over the menu movie with working host input** (2026-09-05,
commits db51455 → 3c790b4). Keyboard is always mapped (arrows, WASD/IJKL, Enter/Backspace, ZXCV,
QE, 1/3, 2/4), mouse via `PS2X_SOCOM2_MOUSE=1`, and `PS2X_SOCOM2_INPUT_SCRIPT="8:START,16:DOWN"`
presses buttons on a timer for log-driven runs. Rendering runs on the **OpenGL 3.3 GS backend**
(default; `PS2X_GS_BACKEND=cpu` = the old rasterizer) at a steady 60 fps at the menu. Full story:
`docs/STATUS.md` (13:00, 14:30 and 16:50 sections), `docs/research/07 §Resolution 2`,
`docs/research/08 §Resolution`, `docs/superpowers/plans/2026-09-05-gpu-gs-backend.md`.

## Immediate next task
The menu is fast now (GPU backend, 60 fps). Make it *navigable*: the slot/profile dialog ignores
DOWN/CROSS/TRIANGLE/START from `PS2X_SOCOM2_INPUT_SCRIPT` and shows an empty list.

- Done: presses reach the game (`PS2X_SOCOM2_PAD_TRACE=1` shows digital 0→1→0 and pressure
  0→ff→0 per press) and MCSERV is only asked to Init (`[MCSERV]` lines). Neither is the gate.
- **Lead (2026-09-05 17:40):** the pad object is the global `DAT_0044f108` (per-button state
  bytes at +1+idx: 0 up, 1 just pressed, 2 held, 3 released; timers at +0x74+idx*4; updated by
  `FUN_002d9ff0` from `FUN_002da930` — verified working with the HLE input). The UI only takes the
  pad when the current screen object's field **+0x114 is 0**: every UI site does
  `pad = (*(screen+0xc0))->+0x114 == 0 ? DAT_0044f108 : 0` (see `FUN_00592ac0` and the readers at
  decomp lines 56650/62162/64708/77639/83899). +0x114 is a local-player index (assigned 1..N-1 in
  `FUN_002b2e50` line ~156089 when `DAT_00440c3c` > 1). So either the dialog's screen carries a
  non-zero player index, or the shell is polling a *different* screen object than the one drawn.
  Next: break in lldb on `FUN_00592ac0` (`FUN_00592ac0_0x592ac0`) and read `*(int*)(rcx+a0+0x114)`
  and `DAT_00440c3c` (0x440c3c) from rdram; if the index is non-zero, find who set it (the writers
  of +0x114 are listed by `grep -n "+ 0x114) = " game/analysis/socom2_game.elf.decomp.c`).
- Pad sockets: the game creates a socket at boot (deleted after the controller check) and a second
  one it actually reads; the HLE reports only the newest socket connected (commit after 3fd31d0).
- Then continue the GPU plan stage 3 (docs/superpowers/plans/2026-09-05-gpu-gs-backend.md).

## Previous next task (done 2026-09-05 16:50): make the menu fast enough to use

- **Texture sampling is the hot path**: `GSCpuBackend::SampleTexture` (gs_cpu_backend.cpp) does a
  swizzled `ReadVramUnlocked` + `LookupCLUT` per texel, ×4 with bilinear. Add a decoded-texture
  cache: key (tbp0, tbw, psm, tw, th, cbp, cpsm, csa, texa), value = linear RGBA8 buffer; invalidate
  by VRAM page (8 KB) dirty bits set from image uploads and framebuffer writes. `DrawSprite` then
  samples the linear buffer (or blits directly for axis-aligned, unfiltered sprites). Measure with
  the `[frame-dump]` line vs `PS2X_PC_SAMPLER` timestamps (see the timeline recipe in STATUS).
- Then drive the menu with the script: the first screen is the slot/profile dialog
  (`SLOT MISSION RANK DATE TIME`); try `DOWN`/`CROSS`/`TRIANGLE` and map disc reads with
  `tools_py/iso_lbn.py` to see which screen loads next. The memory-card side is the MCSERV HLE.
- Check the striped highlight bar in that dialog (CLUT/alpha?) once frames are cheap to capture.
- Verify: `PS2X_SOCOM2_PAD=1 PS2X_SOCOM2_INPUT_SCRIPT="8:START" PS2X_FRAME_DUMP=logs/frames
  PS2X_PC_SAMPLER=5 ./run.sh 30` — no `[guest-fault]`/`[VU1 xgkick]`/`[VU1 reserved]` lines,
  `xgkick` rising, frame count ≥ 1500 in 30 s. Convert a `.ppm` to view it (any PPM→PNG one-liner;
  pick the newest file by mtime, not by name — old frames linger in `logs/frames`).

## Parallel/secondary
- Make `PS2X_SOCOM2_PAD` default-on (the flag only exists because the pad path used to wedge).
- `sceDmaSendI` should set TIE as well as TTE (the HLE currently ignores the "I" variants).

## Build / run
- Runtime-only change: `./build.sh runtime` (~3-10 min; **run it from `socom_pc/`, not a subdirectory**). Editing `gs_backend.h`/`gs_frontend.h` recompiles the generated code too (~15 min). Run: `./run.sh <seconds>` or
  `dist/socom2.exe game/disc/socom2_game.elf` (put `tools/llvm-mingw/bin` on PATH).
- Changed the TOML stub list / `PS2_STUB_LIST` / recompile-time stubs → full
  `./build.sh recomp && ./build.sh runtime` (~15-20 min) because the recompiler embeds the list.
- IOP module change (dbcman.cpp) is runtime-only.

## Diagnostics already built (all env-gated, zero cost when unset)
- `PS2X_PC_SAMPLER=<s>` — live guest PC + thread table every s seconds.
- `PS2X_FRAME_DUMP=<dir>` — per-present pipeline counters (vif1/mscal/vuInsn/xgkick/gsSubmits/
  pixels/nbWrites…) + a PPM every 60 frames. This is the primary "is it drawing?" signal.
- `PS2X_TRACE_VU=1` — VU1 program execution trace + input-header dump.
- `PS2X_TRACE_FIFO=1` — VIF/GIF/DMA channel trace.
- `PS2X_SOCOM2_PAD=1` — report a connected DualShock2 (default off; needed to exercise the pad path).
  With it: keyboard/mouse input (`socom2_host_input.h` has the map), `PS2X_SOCOM2_MOUSE=1`,
  `PS2X_SOCOM2_INPUT_SCRIPT="t:BTN[+BTN][:hold],..."`.
- `PS2X_TRACE_VU=<skip>` — after <skip> VU1 programs, trace the next three (PC path, header, 32
  qwords at TOP, VU data 24-47), dump VU1 data memory per program and the microcode once
  (`vu1_code.bin` → `python tools_py/vu1dis.py`). `[VU1 xgkick]` overrun lines print the bad tag,
  vi registers and save `vu1_overrun_data.bin`.
- `PS2X_TRACE_VIF=<skip>` — VIF1 codes (UNPACK addr/num/flg, STCYCL/OFFSET/BASE/MSCAL...) and the
  first 400 VIF1 DMA chain tags (id, qwc, addr, SPR, upper half, TTE).
- `tools_py/iso_lbn.py <iso> log <run.log>` — which disc files a run streamed (screen transitions).
- `[guest-fault]` lines (always on, first 16): a guest load/store hit a TLB miss or unaligned
  address; shows op, vaddr, pc/ra/sp, a0-a3, s0-s1, v0. The same line repeating = the scheduler is
  re-dispatching a faulting function forever (that is what the old "grind at 0x32f174" was).
- **lldb** (`tools/llvm-mingw/bin/lldb.exe`) gives real guest call chains: host frames are named
  `sub_XXXXXXXX_0xXXXXXX` / `FUN_xxxxxxxx_0xxxxxxx`, `rcx` = rdram and `rdx` = R5900Context at a
  `sub_*` entry (GPR n = `*(unsigned int*)($rdx+16*n)`), so `memory read -f x '$rcx + 0x45c3c0'`
  peeks guest memory and `watchpoint set expression -s 4 -w write -- $rcx+0xADDR` catches a guest
  writer. Batch recipe: `lldb.exe --batch -s cmds.lldb -- dist/socom2.exe game/disc/socom2_game.elf`
  with `breakpoint set -r runtime_error::runtime_error` / `run` / `bt 30` (see research 08).

## Gotchas (respect these)
- The git repo root is the parent monorepo `C:\projects`. **Never `git add -A`** — stage explicit
  `socom_pc/...` paths only. Unrelated untracked siblings exist.
- Shell/py scripts stay **LF** (`.gitattributes`); when writing files from Python use
  `newline='\n'`.
- Don't steal desktop focus or screenshot repeatedly — the user's machine is often gaming. Prefer
  logs. Pause if asked (machine under load).
- Commit as you go with specific messages; keep `docs/STATUS.md` current. Co-author line:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- If running via cron, re-arm a one-shot cron ~4 h ahead when you start, and correct its prompt to
  point at the *current* blocker (prompts go stale fast).

## Milestone map (docs/superpowers/plans/2026-09-04-implementation-plan.md)
M1 toolchain ✅ · M2 boot-to-engine ✅ · **M3 menu render + pad ← you are here** · M4 mission ·
M5 online (Horizon server already stood up, app id 10472) · M6 portable package.

## Landmarks
- Recompiler config: `recomp/socom2.toml` (stubs, mmio, patches). Generated code: `recomp/output/`.
- Game decomp/strings: `game/analysis/socom2_game.elf.decomp.c` / `.strings.txt`.
- Controller HLE: `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp`
  (`namespace ps2_stubs`, scePad2*). DBCMAN: `ps2xIOP/src/modules/dbcman.cpp`.
- Research: `docs/research/05` (code package/DNAS/MFIFO), `06` (989snd), `07` (render pipeline +
  resolution), `08` (controller/DBCMAN).
