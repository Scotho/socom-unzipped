# PS2Recomp internals — engineering brief (2026-09-02, HEAD 14b1e5c)

Repo clone: `research/ps2recomp`. GPL-3.0.

## Input model
- `ps2xRecomp` consumes one TOML + one ELF (`config_manager.cpp`): `[general] input/output/ghidra_output/single_file_output/low_memory_mode/output_worker_threads/patch_syscalls/patch_cop0/patch_cache/stubs/skip`, `[patches] instructions`, `[mmio]`, `[[jump_tables.table]]`.
- ELF via ELFIO; section headers optional (PT_LOAD → pseudo-sections `LOADn`, exec iff PF_X: `elf_parser.cpp:36-102`). Symbols/relocs optional (relocs only name call sites).
- Function boundaries: .symtab, DWARF, JAL-scan fallback, **Ghidra CSV** (`Name,Start,End,Size`, rows `name,0xSTART,0xEND_EXCL,size`; plus synthetic `entry_XXXXXXXX`). `discoverAdditionalEntryPoints()` adds a `switch(ctx->pc)` resume prologue per function.
- **No overlay support**: single image, dense function table indexed by `(pc-base)>>2` over one range (`function_table_emitter.cpp:145-171`, `ps2_runtime.cpp:1031-1050`). To add SOCOM's overlays: wrap dumps as synthetic ET_EXEC ELFs with PT_LOAD at the fixed load address; either merge all images into one ELF with multiple PT_LOADs (works today if address ranges are disjoint) or fork the table emitter for multiple ranges (needed because DNAS and zsealetc share 0x4c5380).

## Generated code
- `void fn(uint8_t* rdram, R5900Context* ctx, PS2Runtime* runtime)`; `R5900Context` has `__m128i r[32]`, pc, hi/lo/hi1/lo1, sa, full VU0 macro state, COP0 regs, llbit, `float f[32]`, fcr31.
- Memory: flat 32 MB `rdram`; fast path `rdram[addr & 0x1FFFFFF]`; special addresses (scratchpad 0x70000000, I/O 0x10000000, GS 0x12000000, VU mem 0x11000000, BIOS) go through `PS2Memory::read*/write*` with TLB, timers, DMAC, VIF/GIF FIFOs.
- Branches: delay slots inline, likely-variants handled, `goto label_X` internal, `dispatchGuestBranch` for external, `JR $ra` returns to dispatcher, `JR rN` via TOML jump tables else dispatch. Backward edges call `eeCheckpointDue()` for preemption.
- Coverage: full integer/64-bit, LQ/SQ, LL/SC, MULT/DIV (32-bit HI/LO), MMI0-3/PMFHL/PMTHL via SSE, COP0 incl. TLB/ERET/EI/DI, VU0 macro incl. VCALLMS → VU1 interpreter core on VU0 mem. **FPU is plain IEEE float** (no PS2 clamping). Unimplemented → `throw` at runtime.

## Runtime
- Boot: `initialize` (raylib window), `loadELF` (PT_LOAD → RDRAM/SPR, CRC32, IOP profile, overrides), `run` (sp=0x01FFFFF0, GameThread runs `EeScheduler`; main thread presents GS frame 640x512).
- `EeScheduler` (2100 lines): cooperative EE kernel on one host thread — threads/priorities, semaphores, event flags, alarms, INTC/DMAC handlers, `EeDispatcherTransfer` for blocking syscalls, 65536-cycle timeslice, VBLANK every 16667 µs waking `waitVSync` + INTC cause 2/3.
- Syscalls: ResetEE, GsSetCrt, thread/sema/eventflag families, alarms, INTC/DMAC handler mgmt, FlushCache, GsGet/PutIMR, SetVSyncFlag, SetSyscall, sceSifDmaStat/SetDma/SetDChain, GetMemorySize, InitTLB, Deci2Call… unknown → throw. Name-bound stubs for libc, sceCd*, sceDma*, sceGs*, sceGifPk/sceVif1Pk, scePad*, sceMc*, sceMpeg*, sceSif*, sceVu0*, sceSd* (many TODO).
- DMAC: only VIF0/VIF1/GIF channels execute (normal + source chain). SIF DMA at API level (`sceSifSetDma` copies immediately). No SPR/IPU/SIF channel register emulation.
- GIF/VIF: PATH1/2/3 arbiter; VIF1 interpreter with all UNPACK formats, MPG, DIRECT, MSCAL/MSCNT, STCYCL/MASK/ROW/COL.
- GS: software only (`gs_frontend.cpp` + `gs_cpu_backend.cpp` 1900 lines): all prim types, alpha/Z/DATE tests, blending, fog, swizzled PSM read/write (CT32/24/16/16S, T8/T4/T8H/T4HL/T4HH, Z formats), CLUT CSM1, TFX modes, bilinear; no mipmaps/dither. `GSRasterBackend` is a virtual interface → GPU backend slot exists.
- VU1: cycle-modeled interpreter (~3100 lines) with pipelines/flags, MPG upload, MSCAL, XGKICK as PATH1. Most substantial hardware piece.
- Audio: no SPU2; VAG capture + raylib playback driven by IOP `libsd` service (SID 0x80000701). Pad: raylib gamepad/keyboard → DualShock report. Memcard: `mc0:` → host dir. CDVD: no ISO9660; `cdrom0:\PATH;1` → host files with synthetic LBNs; raw image fallback `IoPaths.cdImage`.

## IOP HLE (`ps2xIOP`)
- No R3000. `SifCallRpc` stubs build `RpcRequest{sid, function, send, receive}` → `IopSubsystem::handleRpc`; unhandled SIDs log "[IOP/RPC trace:unhandled]". EE-side `SifRegisterRpc` servers are invoked as guest callbacks.
- Services: MCSERV, LIBSD, DBCMAN core; profiles recvx-us, lotr-two-towers-us, fatal-frame-us. Plugin ABI v1 (`plugin_api.h`). To add SOCOM: `IopService` subclasses (989snd SID, inet/netcnf/msifrpc, lgaud, DNAS) in a `socom2-us` profile; network primitives must be added to `IopHost`.

## Build
- CMake ≥3.21, C++20; FetchContent: ELFIO, toml11, fmt, libdwarf, rabbitizer (recompiler); nlohmann_json; raylib 5.5, imgui, rlImGui, FFmpeg (MSVC prebuilt on Windows). CI: Linux gcc/clang, Windows MSVC. clang on Windows untested (llvm-mingw should work with tweaks). Generated code → `ps2xRuntime/src/runner/*.cpp` → `ps2EntryRunner`. Tests: `ps2xTest` (~22k lines).

## Maturity (per subsystem)
| Area | State |
|---|---|
| R5900 translate | mature (FPU IEEE) |
| Function discovery | Ghidra-dependent; single image |
| EE kernel | solid |
| DMAC | GIF/VIF only |
| GS | complete-ish CPU rasterizer, no GPU |
| VU1 | cycle-accurate interpreter |
| Audio | VAG capture only |
| CDVD | host-file lookup |
| IOP | HLE per title |
| Network | none |

## SOCOM II implications
Overlays (build), GPU GS backend (perf), 989snd IopService + real mixer, disc streaming (game LBN tables → provide ISO reader), inet/netcnf/DNAS/Medius/headset (all new), GPL-3 for the whole distributed port (assets not covered).
