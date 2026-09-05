# Handoff — SOCOM II PC recompilation (2026-09-05 19:50)

Read this first, then `docs/STATUS.md` (newest sections at the top of each day). This file is
written so a fresh agent can continue **autonomously** toward the project vision without asking.

## The vision (unchanged, this is what you are working toward)
A native SOCOM II EXE for modern PCs with controller + online play to a self-hosted server, built
by static recompilation of the PS2 game (no emulator). Milestones
(`docs/superpowers/plans/2026-09-04-implementation-plan.md`):
M1 toolchain ✅ · M2 boot-to-engine ✅ · **M3 menu render + pad (nearly done, you are here)** ·
M4 load and play a single-player mission · M5 online lobby against our Horizon server (already
stood up, app id 10472) · M6 portable package. Stop only when a mission plays or an online lobby
we host is reached. Copyrighted-game work stays inside `socom_pc/`; game assets are gitignored.

## How to work (the loop that has been productive)
Bounded steps: one hypothesis → one build → one run → read the log/screenshot → commit → update
STATUS. Never open more than one deep subsystem at a time. Prefer runtime evidence
(`PS2X_CALL_TRACE`, `PS2X_PEEK`, screenshots) over static reading; the decomp is huge and
Ghidra's function list is incomplete. Commit as you go with specific messages and the co-author
line (below). If the user is away, keep going: every open item below has a concrete first step.

## Where the game is now
`PS2X_SOCOM2_PAD=1 PS2X_SOCOM2_INPUT_SCRIPT="8:CROSS,12:CROSS,16:CROSS" ./run.sh 40` runs the
real first boot end to end: memory-card slot popup → "loading" warning → "no SOCOM data found"
→ StoreOptions → Sony logo (SONY448.PSS) → intro movie (INTRO_2.PSS) → `goto_menu` → **main menu
(dlgMenu) over the menu-loop movie at 60 fps on the OpenGL backend** (commits 916559a, 60fe75c,
67d3b01). Host keyboard/mouse input works (arrows, WASD/IJKL, Enter/Backspace, Z X C V = Square
Cross Circle Triangle, Space = Cross, Q/E, 1/3, 2/4; `PS2X_SOCOM2_MOUSE=1`).

What you see on screen at the menu: the SOCOM II logo only. What is missing and why (see next
task): all UI positions resolve to (0,0), so the six menu buttons are piled invisibly top-left and
popups sit top-left and dark; the 3D roller model never draws (VU1 packets carry no vertices).
CROSS at the menu is the **new_game** button; its script event (`UiprepMission1`) now runs through
its VALVE nodes (that was the previous blocker) but the run has not yet been followed past that
point (an intermittent crash at the dlgMenu load, item 2, got in the way twice).

## Next tasks, in order (each with a starting recipe)

### 1. UI positions are all at the origin (blocks seeing/using the menu)
Evidence: GS trace of a menu frame (`PS2X_GS_TRACE_CMDS=1500`) = ~234 textured glyph sprites in
rows 0-63 at x 19-60 (alpha 0x5a) + one big sprite (the logo). Popups earlier in the flow also
drew their panel at (0,0) with text at (19..60, 26). Child offsets work; the parent control's
position is 0. The pre-fix flow (before commit 60fe75c) positioned the load-game panel correctly,
so a path that *now* executes is zeroing positions — most likely valve/expression-driven layout.
- Control loader: `FUN_0036e880` (decomp lines 267680-267760) reads XPOS/YPOS/SPEC via
  `FUN_0032dd80` / `FUN_0032e970` / `FUN_0032f0d0(node, "HCENTERED"=0x3f91f8)` into the control
  at +0xac/+0xb0/+0xe8. `SetScreenOrigin` (`FUN_0027bf10`, writes DAT_004a4508/450c from UI vars
  0x3ef120/0x3ef130) is never called. Screen-size UI vars come from `UiParams.rdr` in
  `READERC.ZAR`.
- Recipe: `PS2X_CALL_TRACE="0x36e880:LoadControl,0x32dd80:ReadFloat,0x32e970:ReadInt"
  PS2X_CALL_TRACE_EVERY=1` on the boot flow; then `PS2X_PEEK` the control at `a0+0xac:4` once
  you know its address (heap addresses are deterministic for a given input script). Also check
  `EXPRESSION`/`VBIT`/`VWATCH` (exec 0x353260 / 0x353030) results with `[ret]` and the UI-var
  getter `FUN_00351ff0(name, type)` (a0 = name string → the tracer prints it).
- Also verify the memory-card popup text renders once positioned; the popup panel colour was
  dark — may be alpha-0 palette + vertex alpha like the earlier panel textures.

### 2. Intermittent crash when dlgMenu loads (2 of 5 runs)
`[guest-branch:missing-target] kind=DirectJump target=0x14 ra=0x36abc0`: `FUN_0036ab20`
("Add2dNode": a0 node data, a1 2D library 0x408dc0, a2 screen) calls
`screen->+0x60->+0x18(screen, node)` with `screen->+0x60 == 0`. The EE main thread then dies
(frame counter keeps rising, no more `[call]` lines, screen static). Timing dependent → an
animation/event probably tears down or swaps the screen object while nodes are still being
added (SwitchMenu → ShellGoto "dlgMenu.rdr" is posted 5 times in a row, see traces).
- Recipe: `PS2X_CALL_TRACE="0x36ab20:Add2dNode,0x27e720:SwitchMenu,0x365a00:ShellGoto,0x2cf410:SetState"
  PS2X_CALL_TRACE_EVERY=1 PS2X_PEEK=<screen>+0x60` and compare a crashing vs a clean run; the
  crash reproduces more often with extra scripted presses (`...,20:CROSS`). Look for who zeroes
  `+0x60` (decomp: `grep -n "+ 0x60) = 0;"` → lines 51258, 82092, 117088, 117278, 133793).
- A cheap mitigation while investigating: the runtime could treat a JALR to an address < 0x100
  as a no-op return (log once) instead of killing the thread — but find the real cause first.

### 3. VU1 packets carry no vertices (no 3D roller, likely same cause as 1)
`hdrKick=0/N` in `[frame-dump]`: every UI VU1 packet's header word w has bit 1 clear
(microcode 0x30 `IBEQ` skips the setup XGKICK at 0x50) and the program ends after ~82 steps
with no kick. `PS2X_TRACE_VU=<skip>` dumps the packet; the EE builds it from the model's mesh
after transform/cull, so zeroed transforms (item 1) would produce exactly this. Re-check after 1.

### 4. New game → mission load (M4)
Once the menu is visible, CROSS on NEW GAME → `UiprepMission1` → VALVE runner → expect
`SetMission` (0x27eb50) and a `ShellGoto` with a1="LOAD_SCREEN" → shell state 0x4085ac (the load
screen) → mission data streaming (`PS2X_CD_TRACE=1` shows `[cd] Read`; map LBNs to files with
`python tools_py/iso_lbn.py "game/SOCOM II - U.S. Navy SEALs (USA).iso" log <run.log>`; the game
reads by LBN table, `sceCdSearchFile` is never used). Also possible on the way: dlgSelectRank
(difficulty) and dlgControllerPresetsNewGame. Expect new unrecompiled-code holes (see gotcha 1)
and `[guest-fault]`s in mission code; the AI/mission commands (`ai::*`, VALVE 0x3d…0x56 game
commands) live in the APACHE00.ZDB overlay, which is recompiled too.
- Memory card: the HLE is a formatted 8 MB card with no `BASCUS-97275SOCOMII` dir; the game
  never tried Mkdir yet. Saving a profile will need Mkdir/Open/Write in
  `Kernel/Stubs/MemoryCard.cpp` (already implemented, untested) — watch `PS2X_MC_TRACE=1`.

### 5. Online (M5), after a mission runs
The Horizon server is up (app id 10472). DNAS is bypassed (research 05). Start from the shell's
`multiplayer_button` → `do_multi_or_medius` → dlgNetLogin/dlgNetConnect; the network stack
(inet/netcnf IRX) is not HLE'd yet — `docs/research/05` and the IOP module list in
`third_party/ps2recomp/ps2xIOP/src/modules/`.

### Secondary / cleanup
- GPU plan stage 3-5 (`docs/superpowers/plans/2026-09-05-gpu-gs-backend.md`): AFAIL modes,
  DATE, 16-bit targets, readback paths, resolution scaling.
- Make `PS2X_SOCOM2_PAD` default-on; `sceDmaSendI` should set TIE as well as TTE.
- `PS2X_FRAME_DUMP` pixels are stale on the GPU path (only counters are reliable); fix or
  document; use `PS2X_HOST_SCREENSHOT` for "what is on screen".

## How the shell works (decoded; details in STATUS 18:40 / 19:10)
- Top loop `FUN_001e7040`: `for(;;) stateMgr(0x4084c0)->tick(dt)` (`FUN_002ce9e0`, a message
  queue for push/pop/set state). Shell state 0x408538 update = `FUN_001f4640` → `FUN_003654c0`
  (input timer +0x900, script-event queue tick `FUN_0034e070(dt, 0x49ea50)`, UI messages →
  `FUN_00365a00(shell, "LOAD_SCREEN" | "POP_TO_MENU_STATE" | "MENU_SCREEN" | "SHUTDOWN" |
  "REBOOT")` → states 0x4085ac (load screen) / 0x408538 / 0x408758). The ELF's `FUN_001ebed0`
  is never called — do not chase it.
- UI = `game/disc/RUN/UI/READERC.ZAR` (111 `.rdr` dialogs; `dlgMenu.rdr` = main menu; locale
  text in `RUN/LOCALE/STATES/UIMNLOC.ZAR`, loaded fine). Scripts are animation sequences: node =
  `{u16 type, u16 size<<2, …}`; runner header 0x1c bytes (`+5` state: 1 idle, 2 start, 4 running,
  5 done; `+8` current node; `+0xc` length). Command ids = registration order of
  `FUN_0026a8e0(0x414bb0, "NAME", parse, create, exec, post)`: IF=2, OBJECT_ACTIVE_STATE=0x11,
  OBJECT_OPACITY_FROM_TO=0x19, SOUND=0x1e, CALL_ANIMATION=0x2d, TIMER=0x38, VALVE=0x3d
  (exec 0x353d00), VBIT=0x3e (0x353260), VWATCH=0x3f (0x353030), ui::UI_COMMAND=0x101
  (`FUN_002745a0` → script binding table), ai::*=0x2xx. Dispatcher `FUN_0026a6e0`; runner step
  `FUN_00269da0`; animation update `FUN_00270220`; named events via
  `FUN_0034e6b0(delay, 0x49ea50, "name", node, arg)`.
- Script binding table at ELF 0x3dd4d4: 207 `{name, fn, 0, id}` rows (16 bytes). Useful ones:
  SetMission 0x27eb50, SwitchMenu 0x27e720, SetMenuState 0x27c9f0, ReadyToLoad 0x27caf0,
  PopUpDialog 0x27eb10, SuspendMenuInput 0x277220, GetNumSavedGames 0x27dea0, LoadSavedGame
  0x27fa40, IsMemCardInserted 0x27e1b0, PlayMPEG 0x27ab30, SetScreenOrigin 0x27bf10. Dump the
  whole table with a 10-line Python ELF reader (pairs at 0x3dd4d4 + 16·i).
- Pad: HLE in `game_overrides_socom2.cpp` (scePad2*), game reader `FUN_002da930` →
  `FUN_002d9ff0` (states 0/1/2/3 per button at DAT_0044f108+1+idx). Works.

## Build / run
- `./build.sh runtime` (3-10 min) for runtime/IOP changes; **run from `socom_pc/`**. Editing
  `gs_backend.h`/`gs_frontend.h` also recompiles generated code (~15 min).
- `./build.sh recomp && ./build.sh runtime` (15-20 min) after touching `recomp/socom2.toml`,
  `PS2_STUB_LIST`, or `recomp/extra_functions.txt` — the forced-function list only takes
  effect through a recomp build.
- Run: `./run.sh <seconds>` (writes `logs/run_<stamp>.log`; newest = `ls -t logs/run_*.log | head -1`).
- Never run two game instances at once (they skew each other's timing); never rebuild while a
  run is active (the link overwrites `dist/socom2.exe`).

## Diagnostics (env-gated, zero cost when unset)
- `PS2X_CALL_TRACE="0xADDR[:name],..."` — every call of the listed guest functions: time,
  a0-a3, f12-f14, ra, any argument that points at text, and `[ret] v0/f0`. 320 slots.
  `PS2X_CALL_TRACE_EVERY=k` (after the first 300 calls log every k-th; 1 = all). Prints
  `no function at 0x…` for unrecompiled targets — that itself is a finding.
- `PS2X_PEEK="0xADDR[:words],..."` with `PS2X_PC_SAMPLER=<s>` — guest words (hex+float) every s.
- `PS2X_CD_TRACE=1` (`[cd] Read lbn`, `[fio] open`), `PS2X_MC_TRACE=1` (`[MC] GetInfo/Sync`).
- `PS2X_HOST_SCREENSHOT=<dir>[:<s>]` — PNG of the window every s seconds (the truth for
  "what is displayed"). `PS2X_GS_TRACE_PRESENT=<skip>` — per-present state incl. copy pixel.
- `PS2X_FRAME_DUMP=<dir>` — per-present counters (`xgkick`, `hdrKick`, `gsSubmits`, `mscal`…).
- `PS2X_GS_TRACE_CMDS=<skip presents>` — 4000 replayed GS commands (submits with coords/rgba,
  uploads, transfers, presents). `PS2X_GS_STATS=1`, `PS2X_GS_DUMP_TEX=<dir>`,
  `PS2X_GS_BACKEND=cpu` (reference rasterizer).
- `PS2X_TRACE_VU=<skip>` (VU1 program path + data dumps; `tools_py/vu1dis.py`),
  `PS2X_TRACE_VIF=<skip>`, `PS2X_TRACE_FIFO=1`.
- `PS2X_SOCOM2_PAD=1` (+ `PS2X_SOCOM2_PAD_TRACE=1`, `PS2X_SOCOM2_MOUSE=1`,
  `PS2X_SOCOM2_INPUT_SCRIPT="t:BTN[+BTN][:hold],..."`).
- `[guest-fault]` (first 16, always on) and `[guest-branch:missing-target]` lines: silent
  guest failures. lldb recipe in `docs/research/08` (host frames are named after guest functions;
  `rcx` = rdram, `rdx` = R5900Context at a `sub_*` entry). Batch-mode breakpoints proved slow
  and flaky; prefer `PS2X_CALL_TRACE`.

## Gotchas (respect these)
1. **Code the recompiler never saw fails silently.** Ghidra misses 2-instruction trampolines
   (`j target; addiu $a0,$a0,imm`) and some callback targets; table-dispatched calls into them do
   nothing. Scan (Python over the ELF text segments): every `j` word (`w>>26 == 2`) followed by
   `addiu $a0,$a0,imm` (`>>16 == 0x2484`) or nop whose address is neither a CSV `Start` nor inside
   any `[Start,End)` → add to `recomp/extra_functions.txt` → full recomp. Two were found and
   fixed (0x353d00, 0x2a98a0); rerun the scan when new symptoms of "call does nothing" appear.
2. Shell heredocs mangle backslashes: never write C string escapes (`\n`) through a bash
   heredoc; use the Edit tool (or Python with `newline='\n'`, checking the result).
3. Git root is the parent monorepo `C:\projects`: **never `git add -A`**, stage explicit
   `socom_pc/...` paths. Shell/py files stay LF.
4. Don't steal desktop focus or screenshot the desktop; the raylib window screenshot
   (`PS2X_HOST_SCREENSHOT`) is fine. Pause if the user says the machine is under load.
5. Commit trailer:
   `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`
   `Claude-Session: https://claude.ai/code/session_011tbmAp4gkXRTbbAoNMtvg7`
6. If running via cron, re-arm a one-shot ~4 h ahead when you start and point its prompt at the
   *current* blocker.

## Landmarks
- Recompiler: `recomp/socom2.toml` (stubs/mmio/patches), `recomp/extra_functions.txt`,
  `recomp/socom2_ghidra.csv` (name,Start,End,Size), generated code `recomp/output/`
  (MIPS listing in comments — use it when the decomp lacks a function).
- Decomp/strings: `game/analysis/socom2_game.elf.decomp.c` / `.strings.txt`; overlay decomps
  (`DNAS.*`, `SCUS_972.75`) alongside. Disc tree: `game/disc/` (ISO in `game/`).
- Runtime: `third_party/ps2recomp/ps2xRuntime/src/lib/` — `ps2_runtime.cpp` (runner, present),
  `gs/gs_gl_backend.cpp` (OpenGL GS), `gs/gs_cpu_backend.cpp`, `game_overrides_socom2.cpp`
  (pad HLE, call tracer, peek, PC sampler), `Kernel/Stubs/{CD,MemoryCard,FileIO}.cpp`,
  `src/lib/socom2_host_input.cpp` (keyboard/mouse/script). IOP: `ps2xIOP/src/modules/`
  (dbcman, mcserv, snd989…).
- Research: `docs/research/05` (code package/DNAS/MFIFO), `06` (989snd), `07` (render
  pipeline), `08` (controller/DBCMAN). GPU plan: `docs/superpowers/plans/2026-09-05-gpu-gs-backend.md`.
