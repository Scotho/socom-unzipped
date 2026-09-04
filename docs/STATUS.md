# Project status — updated 2026-09-04 12:00 (paused by user: machine under load)

## Milestone board (from the design spec)
| # | Milestone | State |
|---|---|---|
| M1 | Fork + toolchain: merged ELF recompiles, runtime links, `socom2.exe` runs crt0→main | **done** |
| M2 | Loader → game entry → engine init without unimplemented-instruction faults | **in progress** (see "Where the guest is now") |
| M3 | Legal/intro screens + main menu render, pad works, UI sounds | not started |
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

## Where the guest is now (last run, 11:18 build)
Both EE threads are parked in `SleepThread`:
- thread 1 (main) ra=0x35005c in `FUN_0034f9b0` (zSys init): `SetAlarm(0x7b0c, 0x34f120, tid); SleepThread();` — a ~2 s alarm whose handler wakes the thread. The handler at 0x34f120 (16 bytes between two Ghidra functions) was **not in the function map**, so the alarm invocation had nothing to run.
- thread 2 ra=0x3b1e00 in `FUN_003b1dd0` (render/present thread): `do { SleepThread(); ...VIF1/GS work... }` — woken per frame by the main thread.

Fix already committed: `tools_py/find_imm_targets.py` added 1,464 immediate-referenced code targets (incl. 0x34f120) to `recomp/extra_functions.txt`; `./build.sh recomp` was run with it (output in `recomp/output`, 14,729 files) and the runtime rebuild was interrupted at 192/~470 objects when the user paused. **Resume with:** `./build.sh runtime && PS2X_PC_SAMPLER=5 ./run.sh 40` (ninja resumes incrementally), then check that the main thread wakes and where it goes next.

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
