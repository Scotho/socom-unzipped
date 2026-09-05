# Project status — updated 2026-09-05 08:00

## Milestone board (from the design spec)
| # | Milestone | State |
|---|---|---|
| M1 | Fork + toolchain: merged ELF recompiles, runtime links, `socom2.exe` runs crt0→main | **done** |
| M2 | Loader → game entry → engine init without unimplemented-instruction faults | **done** — engine runs its main loop; audio init + DBCMAN reached |
| M3 | Legal/intro screens + main menu render, pad works, UI sounds | **in progress** — libpad2 HLE lands (pad reported connected); now blocked in controller-config on DBCMAN rpc 0x8000131a |
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

## Current blocker (top task) — game stays on a black shell screen
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

Next step: reverse the DBCMAN 0x8000131a reply format (and the sibling 0x80001301/2/4 RPCs) and
have `ps2xIOP/src/modules/dbcman.cpp` return a small connection/config table describing one attached
DS2 pad, so the config lookup resolves. Reproduce: `PS2X_PC_SAMPLER=4 ./run.sh 60` — pinned at
0x32f174, DBCMAN RPCs print from the IOP.

## Known issues / debt
- Forced entries get `End = next function start`, which spans rodata: unhandled-instruction count rose from 11k to 114k (garbage that never executes, but +1,400 files). Better: hand the list to Ghidra (`MakeFunctions.java`) so real bounds are found, then re-export.
- Missing ctor targets seen at runtime: 0x231a10, 0x2cde70 (added to `extra_functions.txt`). Expect more "guest-branch:missing-target" lines; each is an entry point to add.
- `LoadExecPS2` (self-relaunch with `--menu_state ...`, and the network-config utility `SCUSNGUI.ELF`) is reported and exits; a real implementation (reset scheduler/memory, reload ELF with argv) is needed for error reboots and network setup.
- DBCMAN (pad) is a stub that only answers the version RPC: controller input must be implemented (libdbc/ds2u protocol, DualShock 2 report incl. pressure).
- GS is the CPU rasterizer at 640x448; fine for bring-up, replace with a GPU backend for M4.
- The loader's libcdvd is partly replaced by runtime stubs (sceCd*), partly recompiled; the engine reads sectors by LBN from the ISO (works). VAG streaming later goes through 989snd's stream-safe read path.
- Build hygiene: shell scripts must stay LF (`.gitattributes`); Python on Windows writes CRLF when opened in text mode without `newline='\n'`.

## Environment facts
- Windows 11, RTX 4070 SUPER, 28 threads, 32 GB. No Visual Studio C++ workload; everything uses the portable toolchain in `tools/`. Python 3.13 with `unicorn`, `capstone`, `pyelftools`.
- Repo is the parent monorepo `C:\projects` (branch `develop`); this project is `socom_pc/`. Unrelated untracked siblings exist — never `git add -A` from the parent.
- The user's desktop is often in use (games): do not steal focus or capture the screen repeatedly; prefer logs. The user may pause work when the machine is loaded.
