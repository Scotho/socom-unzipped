# Handoff — SOCOM II PC recompilation (2026-09-06 02:15)

Read this first, then `docs/STATUS.md` (newest sections at the top of each day). This file is
written so a fresh agent can continue **autonomously** toward the project vision without asking.

## The vision (unchanged, this is what you are working toward)
A native SOCOM II EXE for modern PCs with controller + online play to a self-hosted server, built
by static recompilation of the PS2 game (no emulator). Milestones
(`docs/superpowers/plans/2026-09-04-implementation-plan.md`):
M1 toolchain ✅ · M2 boot-to-engine ✅ · M3 menu render + pad ✅ (navigation works end to end) ·
**M4 load and play a single-player mission (the mission now loads and its engine runs — you are
here, and the blocker is that nothing is drawn)** · M5 online lobby against our Horizon server
(already stood up, app id 10472) · M6 portable package. Stop only when a mission plays or an online lobby
we host is reached. Copyrighted-game work stays inside `socom_pc/`; game assets are gitignored.

## The grade (added 2026-09-07): visual parity with the original, per screen
`docs/parity/REPORT.md` is the project's grade. It scores our screens against a golden set
captured from PCSX2 running the same ISO with the same posted-key script
(`scripts/parity/launch_to_mission.txt`, aligned by `scripts/parity/align.json`). The loop is:

```
python -m tools_py.parity.drive --target pcsx2 --out logs/parity/golden      # once, or after a script change
python -m tools_py.parity.drive --target ours  --out logs/parity/runs/<stamp> --seconds 300
python - <<'EOF'
import json; from tools_py.parity import compare
align={k:v for k,v in json.load(open("scripts/parity/align.json")).items() if not k.startswith("_")}
compare.report("logs/parity/golden","logs/parity/runs/<stamp>","docs/parity/REPORT.md",prev_md="docs/parity/REPORT.md",stamp="<stamp>",align=align)
EOF
python -m tools_py.parity.montage logs/parity/runs/<stamp> logs/parity/<stamp>_sheet.png   # then Read the sheet
```

Rules: a session's last act is a fresh report; the next task is the worst screen on the launch →
mission path unless a hard blocker (thread death, no frame) stops the path earlier; a change that
lowers any screen's score is a regression to fix before moving on; shell screens first, then the
mission. The metric flatters dark screens — read the `.diff.png` (golden | ours | heat) before
trusting a number. Screenshots stay under `logs/parity/` (not in git); the report is committed.
Escalate only on these triggers: `tools_py/parity/probe.py`-style memory comparison over PINE
(`pine.py`, `addresses.py`) when a diff image does not explain a low score; a PCSX2 GS dump
against `PS2X_GS_TRACE_CMDS` only when the same primitives land differently (renderer bug).
The two systemic causes found by the first report: 2D elements ignore their parent/dialog
offset (everything drawn at the top-left), and text never draws. Fix those before anything
screen-specific.

## How to work (the loop that has been productive)
Bounded steps: one hypothesis → one build → one run → read the log/screenshot → commit → update
STATUS. Never open more than one deep subsystem at a time. Prefer runtime evidence
(`PS2X_CALL_TRACE`, `PS2X_PEEK`, screenshots) over static reading; the decomp is huge and
Ghidra's function list is incomplete. Commit as you go with specific messages and the co-author
line (below). If the user is away, keep going: every open item below has a concrete first step.

## Where the game is now
One pad script walks the whole single-player entry end to end:

```
PS2X_SOCOM2_PAD=1 PS2X_SOCOM2_INPUT_SCRIPT="8:CROSS,12:CROSS,16:CROSS,20:CROSS,24:CROSS,30:DOWN,32:DOWN,34:DOWN,36:DOWN,38:DOWN,41:CROSS" ./run.sh 90
```

first boot (memory-card popup → warnings → Sony logo → intro movie) → **main menu** → NEW GAME →
dlgSelectRank → dlgControllerPresetsNewGame → dlgControllerPresetsRG → dlgAlbaniaCinematic →
**dlg_Brief_Alb51** (the Albania 5-1 briefing; it draws its real photo panels) → the five DOWN
presses move the briefing selection from `overview_button` to `deploy_button` → CROSS fires
`OnDeployActivate` → `LoadMission` → `LOAD_SCREEN` → **the mission loads**: its systems register
(`CClutterAnimManager`, `diTick`, `Mission`, `ParticleTick`, `UnitTick`, `ai_pre_tick`,
`weapon_pre_tick`) and the level's AI scripts start (`Supply1-4_start`, `Sniper1/2_start`,
`Alarm1-4_start`, `PatrolWatch_start`, `set_iris`, `otc_init`). No `missing-target` lines, 60 fps
throughout. Details and the four fixes that got there are in STATUS 2026-09-06 02:15.

The briefing's six buttons are, in order: `overview_button`, `mission_details_button`,
`objective_button`, `map_button`, `equipment_button`, `deploy_button` (the last runs `LoadMission`).

What is **not** working: nothing is drawn once the mission starts (see task 1), and the menu's
button captions and 3D roller do not draw (task 3).

**Correction (2026-09-07):** the main thread does *not* go dormant by design and thread 2 is *not*
"the mission". Thread 2 is the game's auto-exposure thread (`FUN_003b1dd0`, priority 4, created by
`FUN_003b2450`, woken from the vsync path `FUN_0033c010` once a mission is up). Each pass samples a
grid of ~176 framebuffer pixels with `FUN_003b24c0`, a one-pixel GS local→host readback through the
VIF1 FIFO in reverse mode (BUSDIR=1, `VIF1_STAT` FQC). The runtime has no reverse-FIFO path, so
every wait in that function ran to its 16M-iteration timeout (~0.3 s per cell) and, being higher
priority, starved the main thread to one mission tick per minute — which is why the frame counters
froze and `FUN_001ebed0` was seen twice in 30 s. `FUN_00271650` (the old "scene-graph walk") is a
bounded script-runner reset and was never the hotspot. `FUN_003b24c0` is stubbed at recompile time
(`socom2_LumReadPixel`, mid-grey pixel) until the readback is implemented (secondary list).

## Next tasks, in order (each with a starting recipe)

### 0. (2026-09-07 17:00) Shell parity by score, then the mission thread
The shell now renders text and layout like the original (STATUS 17:00). By report score the next
screens are: **main menu** (79: soldier background art and the roller captions LOAD GAME / NEW GAME
/ ONLINE are missing — the art draws on the rank screen, so start from the menu's draw order /
clear; the roller is the VU1 "no vertices" path, `hdrKick=0/N`), then the **controller
configuration** screens (black on ours; golden s09/s10). Then verify the merged range
0x510970-0x5109a8 (`recomp/merge_ranges.txt`) stops the mission-thread halt: run the mission script
10 min, expect no `[guest-branch:missing-target]` and the tick to keep running; then the next
`missing-target`, if any, via `tools_py/find_escaping_branches.py` (only 2 functions have the
split-loop pattern; 0x534c4c is a real multi-entry function, leave it).

### 1. In-mission renderer submits no geometry (the M4 blocker)
Once the mission is running, `PS2X_FRAME_DUMP` counters freeze at their shell values
(`vif1codes=399073`, `mscal=22426`, `xgkick=4421`, `nonBlack=0/286720`) — the EE is not sending new
display lists. The in-mission tick `FUN_001ebed0` *is* running (the old handoff's "never called"
was true only before a mission could load). Sampling at 1 s shows the mission thread almost always
at 0x2716e0 — the resume point after the `jal` at 0x2716dc inside `FUN_00271650`, a recursive
scene-graph walk — with a **constant** guest sp, so it is not runaway recursion.
- Recipe: `PS2X_CALL_TRACE="0x1ebed0:MissionTick,0x271650:GraphWalk,0x26f210:GraphNode,0x339de0:Render,0x350ab0:FifoKick"
  PS2X_CALL_TRACE_EVERY=1` with the script above and `./run.sh 90`; `MissionTick` was seen only
  twice in 30 s, so measure how long one call takes and which callee owns the time. `FUN_001ebed0`
  calls `FUN_00339de0(0x4887c0, app+0xa0)` at 0x1ec148 (return 0x1ec150) and the
  `FUN_0033bf30`/`FUN_0033be70`/`FUN_001fba70` triples after it — those are the render submissions.
- **Superseded 2026-09-07** by the exposure-thread finding above; the recipe stays valid for
  measuring the tick. The JAL-as-call cost question is closed (the walk is bounded, ~1.5k calls per
  run). Verify with the stubbed build: `MissionTick` should now run every frame after the load
  (the load itself is ~13 s of synchronous work inside the first tick), and the `PS2X_FRAME_DUMP`
  counters (`vif1codes`, `xgkick`, `mscal`) should move. If they still do not, the next suspects are
  the render submissions `FUN_0033bf30`/`FUN_0033be70`/`FUN_001fba70` after `FUN_00339de0` in
  `FUN_001ebed0` — trace them with `PS2X_JALR_TRACE` on their call sites.
- 16 `[guest-fault] load16` with garbage addresses (0xfd9302aa, pc=0x289c5c ra=0x28c2b8) appear
  during the mission load. `FUN_00289bb0` is an animation keyframe interpolator reading
  `*param_1 + index*6` with an unset keyframe pointer. Non-fatal; resolve once something draws.

### 2. Keep the mission running long enough to see it (M4)
After task 1, drive past the load: watch for the mission camera/HUD, then try movement on the left
stick (`PS2X_SOCOM2_MOUSE=1` maps the mouse to the right stick). `PS2X_HOST_SCREENSHOT=<dir>:<s>`
is the truth for what is displayed; `PS2X_FRAME_DUMP` pixels are stale on the GPU path.

### 3. Menu button captions and the 3D roller do not draw
Positions are **not** the problem (the previous handoff's claim that everything resolves to (0,0)
is disproved — see STATUS 2026-09-06). Every dlgMenu control has its real XPOS/YPOS in the parsed
tree, in the 17 design records and in the 2D nodes at +0x30/+0x34, and the SOCOM II logo draws in
the right place. The six buttons carry `CAPTION " "` (a single space) in the rdr, so their text
must come from a UI variable or locale lookup at draw time.
- Recipe: dump RAM at the menu with `PS2X_RDRAM_DUMP_AT="<path>:LoadList#6"` and print the tree
  with `python tools_py/rdr_tree.py <dump> <root> 6` (the root is the `a1` of that traced call);
  compare a button's SPEC with what the text renderer receives. `FUN_0026ecb0(DAT_00414be8, name)`
  resolves a caption id; `FUN_00351ff0(name, type)` reads a UI variable.
- The 3D roller is the same VU1 "no vertices" symptom as before (`hdrKick=0/N`); re-check it after
  the in-mission renderer works, since both go through the same path.

### 4. Online (M5), after a mission plays
The Horizon server is up (app id 10472). DNAS is bypassed (research 05). Start from the shell's
`multiplayer_button` → `do_multi_or_medius` → dlgNetLogin/dlgNetConnect; the network stack
(inet/netcnf IRX) is not HLE'd yet — `docs/research/05` and the IOP module list in
`third_party/ps2recomp/ps2xIOP/src/modules/`.

### Secondary / cleanup
- **GS local→host readback** so the exposure stub can go: `FUN_003b24c0` sends a 7-qword VIF1
  packet (BITBLTBUF/TRXPOS/TRXREG/TRXDIR=1), waits for `GS_CSR` FINISH (bit 1), sets `GS_BUSDIR=1`
  and `VIF1_STAT` FDR (0x800000), then DMAs `DAT_004a45a8` qwords *from* VIF1 (`CHCR=0x100`) and
  reads the remainder from `VIF1_FIFO` while `VIF1_STAT & 0x1f000000` (FQC) is non-zero. The CPU
  backend already has `PerformLocalToHostTransfer`/`ConsumeLocalToHostBytes`; the GL backend defers
  to it, and the VIF1 reverse DMA/FIFO consumer is what is missing. The stub answers 0x80 grey.
- GPU plan stage 3-5 (`docs/superpowers/plans/2026-09-05-gpu-gs-backend.md`): AFAIL modes,
  DATE, 16-bit targets, readback paths, resolution scaling.
- Make `PS2X_SOCOM2_PAD` default-on; `sceDmaSendI` should set TIE as well as TTE.
- `PS2X_FRAME_DUMP` pixels are stale on the GPU path (only counters are reliable); fix or document.
- Re-run both coverage scanners after any Ghidra CSV change:
  `python tools_py/find_gap_functions.py game/disc/socom2_game.elf recomp/socom2_ghidra.csv` and
  `python tools_py/find_interior_functions.py ...` (add `--emit` to append to
  `recomp/extra_functions.txt`), then a full `./build.sh recomp && ./build.sh runtime`.

## How the shell works (decoded; details in STATUS 18:40 / 19:10)
- Top loop `FUN_001e7040`: `for(;;) stateMgr(0x4084c0)->tick(dt)` (`FUN_002ce9e0`, a message
  queue for push/pop/set state). Shell state 0x408538 update = `FUN_001f4640` → `FUN_003654c0`
  (input timer +0x900, script-event queue tick `FUN_0034e070(dt, 0x49ea50)`, UI messages →
  `FUN_00365a00(shell, "LOAD_SCREEN" | "POP_TO_MENU_STATE" | "MENU_SCREEN" | "SHUTDOWN" |
  "REBOOT")` → states 0x4085ac (load screen) / 0x408538 / 0x408758). `FUN_001ebed0` is the
  *in-mission* tick: never called while the shell is up, called once the mission state is pushed.
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
- `PS2X_JALR_TRACE="0xSRC,..."` — the resolved target of every indirect call/jump issued from
  those pcs (which function a vtable slot or function pointer actually reached).
- `PS2X_RDRAM_DUMP="<path>:<seconds>"` and `PS2X_RDRAM_DUMP_AT="<path>:<TracedName>#<n>"` — write
  the 32 MB guest RAM to a file (the second fires on the n-th call of a `PS2X_CALL_TRACE` name);
  read `.rdr` trees out of it with `python tools_py/rdr_tree.py <dump> <hex node addr> [depth]`.
- `[ret-clobber]` / `[ret-unwound]` lines from the call tracer: a traced function returned with a
  callee-saved register changed, or left through a scheduler unwind (then its `[ret] v0` is not
  the function's result).
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
5. Commit trailer: the `Co-Authored-By:` line names the model you are, and `Claude-Session:` is
   this session's URL — both are given to you at the start of the session; do not copy old ones.
6. If running via cron, re-arm a one-shot ~4 h ahead when you start and point its prompt at the
   *current* blocker.
7. **Read the sampler's thread table before chasing a "slow" function.** `[pc-sampler] live pc`
   is the main context; `running=N` names the scheduled thread and `[N pc=… st=…]` its saved state.
   A live pc frozen at a function *entry* with constant sp while `running` is another thread means
   the main thread is preempted and starved (PS2 threads are strict priority), not that the function
   is slow. Then trace the running thread's function with `PS2X_CALL_TRACE` and read its `[ret]`
   cadence — the exposure thread was found this way in two 90 s runs.
8. Bounded spin loops on MMIO (`while (REG & bit) if (++n > 0x1000000) fail`) are the engine's
   way of waiting for hardware; an unimplemented path shows up as a ~0.3 s stall per call, not a
   hang. Grep the decomp for `0x1000000 <` to find them.
9. Background shell commands are capped at 10 min; a full `./build.sh recomp && ./build.sh runtime`
   is longer. Launch it detached (`nohup bash -c '… > logs/build_x.log 2>&1; echo done > logs/build_x.done' &`)
   and poll for the marker file. `python -` through a heredoc mangles backslashes exactly like
   bash does — use the Edit tool for C/C++ macro lines.

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
