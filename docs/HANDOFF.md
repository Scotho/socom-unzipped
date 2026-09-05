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
the intro, and **the main menu (dlgMenu) runs with working host input** (2026-09-05, commits
db51455 → 916559a; only the load-game panel and logo are drawn so far, see next task). Keyboard is always mapped (arrows, WASD/IJKL, Enter/Backspace, ZXCV,
QE, 1/3, 2/4), mouse via `PS2X_SOCOM2_MOUSE=1`, and `PS2X_SOCOM2_INPUT_SCRIPT="8:START,16:DOWN"`
presses buttons on a timer for log-driven runs. Rendering runs on the **OpenGL 3.3 GS backend**
(default; `PS2X_GS_BACKEND=cpu` = the old rasterizer) at a steady 60 fps at the menu. Full story:
`docs/STATUS.md` (13:00, 14:30 and 16:50 sections), `docs/research/07 §Resolution 2`,
`docs/research/08 §Resolution`, `docs/superpowers/plans/2026-09-05-gpu-gs-backend.md`.

## Immediate next task (2026-09-05 19:35)
**Verified (commit 60fe75c):** with the two trampolines recompiled the shell runs the real
first-boot flow — `PS2X_SOCOM2_PAD=1 PS2X_SOCOM2_INPUT_SCRIPT="8:CROSS,12:CROSS,16:CROSS"` =
memory-card slot popup → loading warning → "no SOCOM data found" → StoreOptions → Sony logo →
intro movie → **dlgMenu with the menu-loop movie, VU1 kicking, 60 fps** (screenshots in
`logs/host`). Three open problems, in priority order:
1. **UI layout is at the origin.** Every popup and every text glyph is drawn relative to (0,0)
   (menu frame: ~234 glyph sprites in rows 0-63, the SplashLogo at its raw position); the six
   menu buttons are therefore invisible (piled top-left, alpha 0x5a) and popups sit top-left. The
   pre-fix flow positioned the load panel correctly, so a *now-executed* path zeroes positions:
   suspects are the HCENTERED/XPOS/YPOS control loader `FUN_0036e880` (decomp 267680-267760:
   reads XPOS/YPOS/SPEC via `FUN_0032dd80/FUN_0032e970/FUN_0032f0d0` into the control at
   +0xac/+0xb0/+0xe8), `SetScreenOrigin` (never called; writes DAT_004a4508/450c
   from UI vars 0x3ef120/0x3ef130) and screen-size UI vars from `UiParams.rdr`. Start with
   `PS2X_CALL_TRACE` on the loader function containing line 267707 and peek the control's
   position fields; compare against the pre-fix flow (`git stash` the extra_functions entries is
   NOT needed — just run the old exe if kept, or read positions from a GS trace).
2. **Intermittent null-vtable crash when dlgMenu loads** (2 of 5 runs):
   `[guest-branch:missing-target] target=0x14 ra=0x36abc0` = `FUN_0036ab20` ("Add2dNode") calls
   `param_3->+0x60->+0x18` with `param_3->+0x60 == 0`; param_3 is the screen object. The EE
   thread dies afterwards (frame counter keeps going, no more `[call]`s). Timing-dependent →
   probably an animation/event completing before the screen's interface is set. Trace 0x36ab20
   with EVERY=1 and peek `a2+0x60`.
3. **VU1 packets carry no vertices** (hdrKick 0, microcode 0x30 branch skips the setup kick at
   0x50; xgkick counts rise but the GS trace shows only sprites, no triangles) → the 3D roller
   model never draws. Likely the same layout/transform problem as 1 (objects culled).
Then: CROSS at the menu (new game) → expect `UiprepMission1` → VALVE runner → SetMission /
"LOAD_SCREEN" (`ShellGoto` a1) → state 0x4085ac → mission load (M4).

**Root cause of "CROSS does nothing" (19:10):** The screen after START is the *main
menu* (`dlgMenu.rdr`), CROSS = the new_game button → script event `UiprepMission1` → its third
sequence runner stalls on its first `VALVE` node because the VALVE command's exec handler at
**0x353d00 is a 2-instruction trampoline (`j 0x353fd0; addiu $a0,$a0,4`) that Ghidra never made
a function**, so the recompiler had no code for it (`[call-trace] no function at 0x353d00`) and
the guest call silently did nothing. `recomp/extra_functions.txt` now forces 0x353d00 and
0x2a98a0 (the other uncovered thunk: event-completion callback); a full `./build.sh recomp &&
./build.sh runtime` was started at 19:05.

1. **Verify** with `PS2X_SOCOM2_PAD=1 PS2X_CALL_TRACE="0x353d00:VALVE,0x2745a0:UI_COMMAND,
   0x27eb50:SetMission,0x27eb10:PopUpDialog,0x365a00:ShellGoto" PS2X_CD_TRACE=1
   PS2X_SOCOM2_INPUT_SCRIPT="8:START,16:CROSS" ./run.sh 30`: expect `[call] VALVE` lines after
   the press, then SetMission / a "LOAD_SCREEN" message (`ShellGoto` a1="LOAD_SCREEN" → state
   0x4085ac = load screen) and `[cd] SearchFile` for mission data. Also confirm
   `[guest-branch:missing-target] target=0x38e890` is gone (0x38e890/0x3b7cf0 were in
   extra_functions.txt but had never been recompiled in).
2. If the mission load starts: M4 begins — follow `[cd]`/`[fio]` traces and `[guest-fault]`s.
3. Separately, the main menu draws only the load-game panel + logo: the six text buttons and the
   `mainmenu_roller` 3D model are missing (rendering, not logic — the VU1 packets for them carry
   no vertices / no setup kick). Compare `PS2X_GS_TRACE_CMDS` before/after `goto_menu`.
4. Then continue the GPU plan stage 3 (docs/superpowers/plans/2026-09-05-gpu-gs-backend.md).

### How the shell works (decoded 2026-09-05, see STATUS 18:40)
- Top loop `FUN_001e7040`: `for(;;) stateMgr(0x4084c0)->tick(dt)` = `FUN_002ce9e0` (message
  queue: push/pop/set state) → current state's update. Shell state 0x408538 update =
  `FUN_001f4640` → `FUN_003654c0` (ShellUpdate: input timer +0x900, script-event queue tick
  `FUN_0034e070(dt, 0x49ea50)`, UI messages → `FUN_00365a00(shell, "LOAD_SCREEN" |
  "POP_TO_MENU_STATE" | "MENU_SCREEN" | "SHUTDOWN" | "REBOOT")` → state 0x4085ac (load screen) /
  0x408538 / 0x408758). The ELF's `FUN_001ebed0` (fade countdown → `FUN_002a9a70` → push state
  0x4086a0) is **never called** — do not chase it.
- UI = `game/disc/RUN/UI/READERC.ZAR` (111 `.rdr` dialogs; `dlgMenu.rdr` = main menu). Scripts are
  **animation sequences**: nodes `{u16 type, u16 size<<2, …}`, runner header 0x1c bytes
  (`+5` state: 1 idle, 2 start, 4 running, 5 done; `+8` current node; `+0xc` length). Command ids:
  registration order of `FUN_0026a8e0(0x414bb0, "NAME", parse, create, exec, post)` (1-based:
  IF=2 … OBJECT_ACTIVE_STATE=0x11, OBJECT_OPACITY_FROM_TO=0x19, SOUND=0x1e, CALL_ANIMATION=0x2d,
  TIMER=0x38, VALVE=0x3d, VBIT=0x3e, VWATCH=0x3f, ui::UI_COMMAND=0x101, ai::*=0x2xx). Dispatcher
  `FUN_0026a6e0`; runner step `FUN_00269da0`; animation update `FUN_00270220`. `ui::UI_COMMAND`
  (`FUN_002745a0`) calls the **script binding table** (ELF 0x3dd4d4, 207 `{name, fn, 0, id}`
  rows: SetMission 0x27eb50, SwitchMenu 0x27e720, SetMenuState, ReadyToLoad, LoadSavedGame,
  GetNumSavedGames, IsMemCardInserted, SuspendMenuInput 0x277220, PopUpDialog 0x27eb10 …).
  Named events are scheduled with `FUN_0034e6b0(delay, 0x49ea50, "name", node, arg)`.
- Memory card: HLE = formatted 8 MB card with no `BASCUS-97275SOCOMII` dir; the shell lists
  SaveGame0..9 (none) and shows the load panel. Fine for a new game.

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
- **`PS2X_CALL_TRACE="0xADDR[:name],..."`** — logs every call of the listed guest functions
  (time, a0-a3, f12-f14, ra, string args) and `[ret] v0/f0`. Catches direct JALs (dense function
  table). 320 slots; `PS2X_CALL_TRACE_EVERY=k` (after the first 300 calls log every k-th; 1 =
  all). Prints `no function at 0x…` when the address is not recompiled — that itself is a finding.
- `PS2X_PEEK="0xADDR[:words],..."` — guest words (hex+float) with every `PS2X_PC_SAMPLER` line.
- `PS2X_CD_TRACE=1` (`[cd] SearchFile/Read`, `[fio] open`), `PS2X_MC_TRACE=1` (`[MC] GetInfo/Sync`).
- `PS2X_HOST_SCREENSHOT=<dir>[:<s>]` — PNG of what the window shows. On the GPU path the
  `PS2X_FRAME_DUMP` PPM/`nonBlack` can be **stale** (same frame re-reported); trust screenshots.
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
- **Code the recompiler never saw fails silently.** Ghidra misses 2-instruction trampolines
  (`j target; addiu $a0,$a0,imm`) and some callback targets; a guest call into such an address
  does nothing (only `[guest-branch:missing-target]` for JALR, nothing for table-dispatched
  calls). Scan: the Python snippet in STATUS 19:10 (thunks outside every CSV range); add hits to
  `recomp/extra_functions.txt`, then a **full** `./build.sh recomp && ./build.sh runtime` —
  entries added to that file without a recomp build are not in the EXE.
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
