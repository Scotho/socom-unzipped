# Project status — updated 2026-09-05 16:50

## Milestone board (from the design spec)
| # | Milestone | State |
|---|---|---|
| M1 | Fork + toolchain: merged ELF recompiles, runtime links, `socom2.exe` runs crt0→main | **done** |
| M2 | Loader → game entry → engine init without unimplemented-instruction faults | **done** — engine runs its main loop; audio init + DBCMAN reached |
| M3 | Legal/intro screens + main menu render, pad works, UI sounds | **in progress** — intro, title and slot dialog render on the new GPU backend at 60 fps; host input wired; dialog does not yet react to input (memory-card flow?) |
| M4 | Single-player mission playable | not started |
| M5 | Online: login/lobby/room on local Horizon, second client joins | server side ready; client side not started |
| M6 | Portable package | not started |

## What works today
- Full plaintext game code recovered (FTSCore.bin @0x1e7000, ZSealEtc.bin @0x4c5380; build id "SOCOM 2 r0001 17:22:21 Oct 11 2003"), see `docs/research/05-code-package-and-harness.md`.
- `./build.sh recomp && ./build.sh runtime` produces `dist/socom2.exe` (~160 MB, 14.7k generated functions). Build cycle: 10 s recomp, ~15 min full compile, ~3 min runtime-only.
- The exe boots the loader: memory-card check (DBCMAN/MCSERV HLE), skips the DNAS decrypt (override), restores the overlays after the loader's bss wipe, runs both overlays' static constructors, jumps to the game entry (0x4c53c0 → FTSCore main 0x1e7040), reads the ISO volume descriptor and builds the engine's disc TOC from the ISO (`IoPaths.cdImage`).
- Diagnostics: `PS2X_PC_SAMPLER=<s>` prints live guest PC + thread table (pc/ra/sp/status/wait) every s seconds; the runner window has a built-in debugger UI (CPU/Threads/Kernel/RPC/GS tabs).
- PCSX2 2.8.1 + BIOS (`tools/pcsx2`) boots the ISO; reference log in `logs/pcsx2_reference_boot.txt` (IRX load order, timings).
- Horizon Private Server runs locally for app id 10472 (`server/README.md`, `server/start-servers.ps1`; simulated DB, account socom/socom; the game's baked-in RSA key matches Horizon's).
- 989snd IOP service first version (`ps2xIOP/src/modules/snd989.cpp`, protocol in `docs/research/06-989snd-rpc.md`): answers all RPCs with correct framing, models banks/voices/streams, serves stream-safe CD reads; no audible output yet (host backend is libsd-only).

## Where the guest is now (2026-09-05 03:20)
Progress today, each a runtime fix: alarm handler discovered (main thread wakes) → all IRX modules load in the PCSX2 order → `lgaud` service answers lgAudInit (version 1.08, no headset) → `usbkb` bind → engine's scratchpad MFIFO renderer path implemented (fromSPR/toSPR DMA + ring drain; see research doc) → 989snd sound-system init runs through the service → `GetRomName` crash fixed (one-argument syscall) → the SCE-RT rt_crypt library generates a 512-bit RSA key pair at startup (two 256-bit primes by trial; takes minutes under recompiled code) → replaced with a fixed precomputed key via a recompile-time stub (`socom2_RsaGenerateKeyPair@0x0062B168` in `recomp/socom2.toml`, key in `socom2_rsa_key.h`).

Lessons: `runtime.replaceFunction()` only affects calls that go through the dispatch table; direct `jal` calls are compiled as direct C++ calls, so hooks on directly-called functions must be recompile-time stubs (`handler@0xADDR` in the TOML, handler name added to `PS2_STUB_LIST` in `ps2_call_list.h`, implementation in namespace `ps2_stubs`), and the recompiler must be rebuilt because it embeds that list (`build.sh recomp` now always rebuilds the tools). The crash reporter (`[crash]` lines with module-relative frames; symbolize with `llvm-nm -n dist/socom2.exe`) and the PC sampler (`PS2X_PC_SAMPLER`) are the two diagnostics that found every issue above.

## Where the guest is now (2026-09-05 08:00) — engine main loop running
Two fixes this session unblocked the boot:
1. **EE INTC I_STAT (0x1000F000) emulation** (`ps2_memory.cpp` `raiseIntcStatBit` + write-1-to-clear read/write; `EeScheduler.cpp` raises bit 2 on VBlankStart, bit 3 on VBlankEnd; `ps2_runtime.cpp` raises the bit for drained INTC causes). The engine's vsync wait `FUN_001a3fb0` clears I_STAT bit 2 and polls until the next vblank sets it.
2. **94 truncated `[mmio]` overrides fixed** (`tools_py/resolve_mmio.py`). A prior auto-generated table had folded many hardware-register accesses to their `lui` high-half (e.g. I_STAT 0x1000F000 → 0x10000000, GS 0x10002010 → 0x10000000, DMAC 0x1000dxxx → 0x10000000), silently routing guest MMIO to EE Timer0. The resolver backward-reconstructs each base register via lui/ori/addiu within its Ghidra function and computes base+imm. The three I_STAT poll sites (0x1a3fcc/0x1a3ff0/0x1a4020) were among them.

Result: the vsync wait completes, thread 1 (main) advances through the frame loop, and the live PC now spreads across engine subsystems (FIFO kick 0x350ab0, render 0x3b7130, 0x33xxxx/0x32xxxx). Threads 2/3 park correctly in `WaitSema`/`SleepThread` waiting for work. The game reaches audio-system init (`snd_StartSoundSystem`, master volumes, reverb, voice groups all set) and calls **DBCMAN** (controller/memory-card manager) — the shell/menu init path. Reproduce: `PS2X_PC_SAMPLER=1 ./run.sh 40`.

## Where the guest is now (2026-09-05 13:00) — intro video plays
**The pad-path wedge is fixed and the game plays its intro** (`PS2X_SOCOM2_PAD=1 ./run.sh 45`: 2445
frames, ~250k/287k non-black pixels per frame, 989snd banks loading, zero guest faults). Commit
db51455; full write-up in `docs/research/08-controller-and-dbcman.md §Resolution`.

Root cause (not the "config loop" the previous status guessed): with the pad reported connected,
the native `sceVibGetProfile` wrapper calls `sceDbcReceiveData` every frame with an
*uninitialised* max-length in the reply buffer's count field (+0x08). Our DBCMAN stub never wrote a
reply, so the wrapper read that garbage back as the received byte count and memcpy'd it out of the
0x1d62c0 RPC buffer into the pad object — running through the heap and overwriting the global
texture registry (0x45c3c0) with loader code bytes. The texture loader (`FUN_00354670`) then
dereferenced code words as pointers → TLB-miss fault → the runtime silently raised a COP0 address
error and re-dispatched the same function forever (the "grind" at 0x32f174/0x3546d0).

Found with **lldb** (ships in `tools/llvm-mingw/bin`): attach or launch under `lldb.exe --batch`,
break on `runtime_error::runtime_error` to get the host stack of the first guest fault (host frames
are named `sub_XXXXXXXX_0xXXXXXX`, so the host stack *is* the guest call chain), peek guest memory
as `$rcx + <guest addr>` at a `sub_*` entry (rcx = rdram, rdx = R5900Context, GPR n at rdx+16*n),
and `watchpoint set expression -s 4 -w write -- $rcx+0x8668c8` to catch the writer. Scripts used:
see the research doc.

Fixes: (1) `ps2xIOP/src/modules/dbcman.cpp` answers every libdbc RPC with a consistent "one DS2 on
socket 0, nothing received" state (count 0 at +0x08 is the crucial part) and publishes the 32-word
link table to the SetWorkAddr address. (2) `ps2_runtime.cpp` Load*/Store* fault handlers now print
a rate-limited `[guest-fault] op vaddr pc ra sp a0-a3 s0-s1 v0 (what)` line — these faults were
100% silent before. (3) `recomp/extra_functions.txt` += 0x3b7cf0, a static-init element ctor
Ghidra missed (the one `[guest-branch:missing-target]` at every boot).

Correction to research 08: `untracked_stubs` in the TOML is **informational only, ignored by the
recompiler** (ps2xAnalyzer/Readme.md) — those functions run natively. That is why
`sceVibGetProfile`/`scePad2GetButtonProfile`/`scePad2DeleteSocket` reached DBCMAN at all.

Step 2 (verified: `./run.sh 60` with the pad on shows only boot-time CheckVersion/SetWorkAddr/DeleteSocket DBCMAN traffic, no guest faults, content drawing, disc streaming): HLE `scePad2GetButtonProfile`,
`sceVibGetProfile`, `sceVibSetActParam` as recompile-time stubs so the pad state machine in
`FUN_002da930` advances 0→1 (GetButtonProfile could never succeed natively: it reads the DMA buffer
that only the native `scePad2CreateSocket` registers) and libdbc stays idle.

## Where the guest is now (2026-09-05 14:30) — menu UI renders, host input works
**Keyboard/mouse/scripted input** (`socom2_host_input.cpp`, commit 7aa0981): arrows = d-pad,
WASD/IJKL = sticks, Enter/Backspace = START/SELECT, ZXCV = Square/Cross/Circle/Triangle, QE/13/24 =
L1R1/L2R2/L3R3; `PS2X_SOCOM2_MOUSE=1` maps motion to the right stick and LMB/RMB to R1/L1;
`PS2X_SOCOM2_INPUT_SCRIPT="8:START,16:DOWN,18:CROSS"` presses buttons at those seconds (log-driven
testing). START at 8 s skips INTRO_2.PSS; the game then streams MENULOOP.PSS.
`tools_py/iso_lbn.py <iso> log <run.log>` maps a run's disc reads to file names.

**The shell UI now draws** (commit 3c790b4): the slot/profile dialog ("SLOT MISSION RANK DATE
TIME") renders over the menu movie; XGKICK fires (6480 kicks by frame 825), no faults, no VU
errors. Three EE→VIF1 delivery bugs were in the way, found with `tools_py/vu1dis.py` + the VU/VIF
traces (details in `docs/research/07 §Resolution 2`):
1. DMAtag upper-half (VIFcode) transfer was unconditional for CNT/NEXT/CALL/RET/END and never for
   REF tags; hardware does it for every tag iff CHCR.TTE. The shell's eye vector (REF tag) never
   arrived, the VU backface cull rejected every UI triangle, no XGKICK.
2. DMAtag ADDR bit 31 (SPR) was dropped.
3. The HLE libdma sent chains with CHCR 0x185 (TIE) instead of 0x145 (TTE).

**Next bottleneck: the CPU rasterizer.** With the UI up the game submits ~370 sprites and ~1M
textured pixels per frame; `GSCpuBackend::SampleTexture` does a swizzled VRAM read plus a CLUT
lookup per texel (×4 when bilinear) so the frame rate drops to 13-17 fps (lldb shows the game
thread inside `DrawSprite`→`SampleTexture` from the guest's DMA kick — it is slow, not stuck).
Options: a decoded-texture cache keyed by (tbp0,tbw,psm,size,CLUT) with page-dirty invalidation,
or the M4 GPU backend. Also visible: the dialog's highlighted row renders as a striped bar
(likely a CLUT/format or alpha issue) — check once the frame rate is fixed.

## Where the guest is now (2026-09-05 16:50) — GPU backend, menu at 60 fps
**OpenGL 3.3 GS backend landed and is the default** (`GSGlBackend`, commits 939655b, f80a93b,
0a208a0; design + status in `docs/superpowers/plans/2026-09-05-gpu-gs-backend.md`). The game
thread records GS commands, the main (GL) thread replays them into per-framebuffer render targets
and presents the RT texture directly; two `GSCpuBackend` instances model VRAM (authoritative on
the game thread, a shadow on the render thread for texture decoding). The shell renders at a
steady 60 fps (`PS2X_GS_STATS=1`), vs 13-17 fps on the CPU rasterizer (`PS2X_GS_BACKEND=cpu`).
Diagnostics: `PS2X_GS_DUMP_TEX=<dir>`, `PS2X_GS_TRACE_CMDS=<skip presents>`, and
`PS2X_FRAME_DUMP` still works (Present blocks for a readback).

Observed with the traces: SOCOM II streams every UI texture through one VRAM slot (texture at
block 0x3bf7, palette at 0x3bf3, re-uploaded before each draw), so the texture cache re-decodes
per draw; the dialog panel textures have alpha-0 palettes and rely on vertex alpha; the only
visible difference from the CPU path is that the title logo stays visible behind the slot dialog
(plausible for the real game; verify against PCSX2 when convenient).

**Open:** the slot/profile dialog does not react to DOWN/CROSS/TRIANGLE/START from the input
script, and its list is empty (no saves). Traced (`PS2X_SOCOM2_PAD_TRACE=1`, commit after
0a208a0): the presses DO reach the game — `scePad2GetButtonInfo` is polled for the digital ids
0x00-0x0f and the pressure ids 0x14-0x1f, and each press shows as 0→1→0 (digital) and 0→ff→0
(pressure). MCSERV (`[MCSERV]` trace) is only ever asked op 0 (Init), 11 times; the shell never
queries card info. The gate is in the shell's UI layer: every UI input site uses the pad only when the current
screen object's +0x114 (local player index) is 0 (`FUN_00592ac0`). Next step and lldb recipe in
HANDOFF. The pad state machine itself (`FUN_002d9ff0`: states 0/1/2/3 + timers) is verified to
work with the HLE input. Pad sockets: only the newest socket reports connected (the boot-time
controller-check socket is deleted by the game; the HLE never sees the delete).

## Previous blocker (resolved 2026-09-05) — game stayed on a black shell screen
Full render-pipeline diagnosis in `docs/research/07-render-pipeline-diagnosis.md`. Using the new
`PS2X_FRAME_DUMP=<dir>` counters, every layer below the game is proven correct: VIF1 delivers
1.5 MB/frame to `processVIF1Data`, VU1 launches 1047 microprograms and executes 87k instructions,
the software rasterizer writes pixels, the double-buffer flip and presentation work. The gap is
above them: the game loops in its shell render dispatch (`FUN_00339de0`) but only issues per-frame
**black clears** — `xgkick=0` (no VU1 geometry ever emitted), `nbWrites=0` (every rasterized pixel
is black), ~0.45 GS draws/frame. So the game has not advanced to a state that draws content.

**Update:** the controller was the gate. libpad2 (`scePad2*`) HLE now reports a connected
DualShock2 (see `docs/research/08-controller-and-dbcman.md`), and the game advances out of the
attract loop into first-time controller configuration. It now wedges there on a new IOP RPC:
**DBCMAN `rpc=0x8000131a`**, which our DBCMAN stub leaves unanswered. The main thread pins at
guest 0x32f174 inside a config/asset lookup (`FUN_00321390` list-walk → `FUN_00354670` →
`FUN_0032f0e0` recursive string-tree search) that grinds because the config table DBCMAN 0x8000131a
should populate is empty.

**Unified conclusion (2026-09-05, verified by `PS2X_TRACE_VU`):** the render pipeline is *correct*
and the black screen is a **game-state** condition, not a GS/VU bug. Full write-up in
`docs/research/07 §Resolution`. The one render program the game MSCALs (startPC=0x0, ~748× identical)
reads its input command header from double-buffered VU memory at TOP (0x1a8/0x2d4) = `[0,0,0,1]`
(empty/skip) and correctly branches over the XGKICK at 0x50 — the game is feeding it an empty
display list. GS, rasterizer, framebuffer, presentation, VIF1 feed, VU1 execution and XGKICK decode
all work; when the game reaches an interactive screen it will submit real lists and XGKICK fires on
its own (watch `xgkick`/`nbWrites` rise under `PS2X_FRAME_DUMP`).

So the gate to visible graphics is **advancing the game state**, i.e. the controller path. The pad
HLE (`PS2X_SOCOM2_PAD`, default off to keep the fast render loop) makes the game try first-time DS2
configuration through Sony's proprietary **libdbc/DBCMAN** device-bus protocol and wedge on
`rpc=0x8000131a` (sceDbcReceiveData) at guest 0x32f174. Reply-buffer layouts for the DBCMAN RPCs are
decoded in `docs/research/08` (offsets in the 0x1d62c0 buffer).

(Superseded: the DBCMAN replies were implemented — see the 13:00 section above. The "config loop"
theory was wrong; it was heap corruption from an unanswered ReceiveData.)

## Known issues / debt
- Forced entries get `End = next function start`, which spans rodata: unhandled-instruction count rose from 11k to 114k (garbage that never executes, but +1,400 files). Better: hand the list to Ghidra (`MakeFunctions.java`) so real bounds are found, then re-export.
- Missing ctor targets seen at runtime: 0x231a10, 0x2cde70 (added to `extra_functions.txt`). Expect more "guest-branch:missing-target" lines; each is an entry point to add.
- `LoadExecPS2` (self-relaunch with `--menu_state ...`, and the network-config utility `SCUSNGUI.ELF`) is reported and exits; a real implementation (reset scheduler/memory, reload ELF with argv) is needed for error reboots and network setup.
- Controller input is HLE only (`scePad2*`/`sceVib*` stubs in `game_overrides_socom2.cpp`, shared state `g_socom2Pad`, neutral input): host keyboard/gamepad → `g_socom2Pad` injection is not wired yet. DBCMAN answers libdbc with a fixed "one DS2, nothing received" state; no real DS2 protocol.
- Guest memory faults are converted to COP0 address errors and the access returns 0 (silently until the `[guest-fault]` log, first 16 only). A fault inside a function makes the scheduler re-dispatch that function from `ctx->pc`; a repeated identical `[guest-fault]` line means a retry loop like the one fixed on 2026-09-05.
- GS is the CPU rasterizer at 640x448; fine for bring-up, replace with a GPU backend for M4.
- The loader's libcdvd is partly replaced by runtime stubs (sceCd*), partly recompiled; the engine reads sectors by LBN from the ISO (works). VAG streaming later goes through 989snd's stream-safe read path.
- Build hygiene: shell scripts must stay LF (`.gitattributes`); Python on Windows writes CRLF when opened in text mode without `newline='\n'`.

## Environment facts
- Windows 11, RTX 4070 SUPER, 28 threads, 32 GB. No Visual Studio C++ workload; everything uses the portable toolchain in `tools/`. Python 3.13 with `unicorn`, `capstone`, `pyelftools`.
- Repo is the parent monorepo `C:\projects` (branch `develop`); this project is `socom_pc/`. Unrelated untracked siblings exist — never `git add -A` from the parent.
- The user's desktop is often in use (games): do not steal focus or capture the screen repeatedly; prefer logs. The user may pause work when the machine is loaded.
