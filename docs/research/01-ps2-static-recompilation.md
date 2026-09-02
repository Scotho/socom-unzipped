# PS2 static recompilation — state of the art (research, 2026-09-02)

## Toolchains

### PS2Recomp (ran-j) — the only serious, active toolchain
- https://github.com/ran-j/PS2Recomp — C++20, CMake, **GPL-3.0**, ~3.2k stars. Announced Jan 2026; releases v0.0–v0.4 (Feb–Apr 2026); last commit Aug 2026.
- Modules: `ps2xAnalyzer` (ELF scan → TOML), `ps2xRecomp` (R5900 → literal C++; MMI + VU0 macro via SSE; relocations; multi-file), `ps2xRuntime` (32 MB RDRAM, function table for `jr`, syscalls, EE thread scheduler, CPU GS rasterizer, VU1 interpreter, raylib window), `ps2xIOP` (IOP HLE by SIF RPC service id; game profiles; plugin ABI).
- Recommended workflow: Ghidra → `ExportPS2Functions.java` → TOML/CSV → recompile → link with runtime. Per-game "Game Override Hooks".
- Maturity: RE Code Veronica X boots to memcard screen; Dark Cloud 2 boots with glitches. Nothing playable. README: "hardware emulation is partial and many paths are stubbed."
- Forks: BlackLineInteractive/SHO-GTA-VCS-PS2Recomp, ej-sanmartin/ps2recomp (stale), menaman123/Ps2Recomp (Crash Twinsanity, hand translation), sp00nznet/reo (RE Outbreak; claims SIF RPC bridge + planned SN@P network with DNAS bypassed — **unverified**, account has 190+ dubious repos), cualquiercosa327/psretrox (abandoned).
- AI tooling: hkmodd/ps2-recomp-Agent-SKILL, hkmodd/PCSX2-MCP (PCSX2 with MCP debug server).
- Siblings: N64Recomp, XenonRecomp/UnleashedRecomp, BlackLabelHQ/RecompOne (PS1, C#, Jul 2026).

## Decompilation efforts (matching decomps, splat + ee-gcc + m2c + objdiff + Ghidra EE)
- Sly 1 (TheOnlyZac/sly1, byte-matching), KH1 (ethteck/kh1), KH2FM (GovanifY/kh2), God Hand, Klonoa 2, Dark Cloud (adubbz/dcdecomp — overlays TITLE.BIN/DUN.BIN matching), Jak (OpenGOAL, special case).
- **SOCOM**: no decomp of SOCOM II. **reCOM** (NotEnoughPhotons/reCOM) decompiles the SOCOM 1 demo SCUS_972.05 which has full debug symbols — engine "GameZ". Community hacking: Zero1UP/SOCOM-2---r0005-Patch (Code Designer + kernel hooks).
- TCRF "PS2 Games With Debug Symbols" reportedly lists SOCOM II — **false for the retail SCUS_972.75**: `.symtab` is empty (verified locally).

## Analysis tools
- Ghidra + chaoticgd/ghidra-emotionengine-reloaded (MMI/VU0 decomp, .mdebug STABS, PCSX2 savestate import, VU overlay importer).
- chaoticgd/ccc (`stdump`, demangler), PCSX2 debugger, splat (PS2), ps2dis, decomp.me (ee-gcc), ps2tek (https://psi-rockin.github.io/ps2tek/), ps2sdk (https://github.com/ps2dev/ps2sdk), psdevwiki DNAS / IRX pages.

## HLE approaches and the irreducible hardware set
- Play! (jpd002) — only HLE-BIOS emulator; EE JIT, IOP modules HLE'd (sifcmd, padman, mcserv, cdvdfsv, libsd...), no inet/netcnf/smap HLE. Runs without a BIOS.
- DobieStation wiki "Making a PS2 Emulator: From Bits to Pixels" — best short EE→DMAC→GIF→GS explanation.
- paraLLEl-GS (Arntzen-Software) — standalone Vulkan-compute GS, LGPLv3+, depends on Granite; the obvious drop-in GS for a hybrid recomp.
- Minimum to reimplement even with recompiled EE code: GS (registers, GIF PACKED/REGLIST/IMAGE, swizzled VRAM/PSM, CLUT, rasterizer, PATH1/2/3 arbitration), VIF0/1 UNPACK/MSCAL/MPG, VU1 (interpreter first, static translation later), DMAC chain tags, EE kernel (threads/sema/alarms/INTC/DMAC handlers/SIF), IOP via SIF RPC HLE, timers/INTC.

## IOP bypass via SIF RPC HLE
- PS2Recomp `ps2xIOP` does exactly this for MCSERV, LIBSD, DBCMAN + per-game (TSNDDRV, CRI DTX, CLFILE, SDRDRV). Pad/CDVD handled as kernel-level stubs.
- Nobody has HLE'd Sony's libnet family (inet.irx, netcnf.irx, smap/dev9, msifrpc, libnetb) nor DNAS nor USB headset (usbd + lgaud). For SOCOM II this is new work: map sceInet* to Winsock, canned netcnf, DNAS stub → success, Medius traffic to Horizon-style servers, mic capture → voice packets.

## Feasibility consensus and pragmatic hybrid
1. Recompile EE (PS2Recomp or fork), VU0 macro inlined, function lookup + overlay support.
2. Link a GS library (paraLLEl-GS or PCSX2-GS derived) fed by a faithful VIF1/GIF/DMAC model.
3. VU1 interpreter first, then static translation of SOCOM's microprograms.
4. HLE the IOP via SIF RPC: padman, mcserv, cdvdfsv (read from extracted files/ISO), libsd/989snd (host mixer), inet/netcnf/DNAS/Medius, headset.
5. Host scheduler replaces EE kernel syscalls.
Expect items 2–4 to dominate; months of per-game triage.
