# SOCOM II: U.S. Navy SEALs — native PC recompilation: design

Status: approved by delegation (the user set the goal and asked for fully autonomous execution on 2026-09-02; decisions below are mine and are recorded here so they can be revisited).

## 1. Goal and success criteria

Make the US retail SOCOM II (SCUS_972.75, r0001) run natively on 64-bit Windows without a PS2 emulator, with online play against a server we host.

Done when, on the developer's machine:
1. The rebuilt executable boots from a cold start to the main menu using the user's own disc image for assets.
2. A single-player mission loads and is playable (movement, shooting, AI, HUD, sound).
3. The client logs into a locally hosted Medius server, creates or joins a lobby room and starts a multiplayer round.

Portable distribution (a folder the user unzips; game assets supplied by the user from their ISO) is the packaging target; an installer is optional.

## 2. Constraints and facts the design rests on

- The boot ELF is a loader. The game code is two Metrowerks overlays decrypted from `RUN/RAW/APACHE00.ZDB` (see `docs/research/05-code-package-and-harness.md`): FTSCore @0x1e7000 (2.0 MB text) and ZSealEtc @0x4c5380 (1.6 MB text). Both are recovered in plaintext and merged with the loader into `game/overlays/socom2_game.elf` (address ranges disjoint; DNAS.BIN, which shares ZSealEtc's slot, is only used for authentication and content decryption and will be replaced by host code).
- No symbols. Ghidra (r5900 + EE extension) finds ~8,400 functions over the three images; PS2Recomp's analyzer identifies Sony SDK library functions by signature (sceCd*, sceSif*, scePad*, sceMc*, sceGs*, sceDma*, sceVu0*, sceMpeg*, sceUsb*, sceDbc*, Metrowerks MSL).
- Instruction census of the game code: ~917k instructions, 40k FPU, 36k lq/sq, only 426 COP2 (VU0 macro) and 45 MMI → the EE side is ordinary MIPS+FPU and recompiles well. Rendering is driven through VIF/GIF DMA chains embedded in model data and VU1 microprograms (to be located in Ghidra; the engine's zRender module owns them).
- Network: SCE-RT DME client 1.32, rt_udp, rt_audio (voice), Medius Client Library **1.50.0013**; MUIS/MAS/MLS hostnames `socom2-prod(.muis).pdonline.scea.com`; DNAS via libdnas2 2.7.1 in the DNAS overlay; IOP side uses inet.irx/netcnf.irx/libnetb.irx/smap.irx/msifrpc.irx (+ppp/pppoe/eznetcnf).
- Audio: 989snd (989snd.irx/989dstrm.irx) on the IOP; VAG streams from `RUN/SOUNDS/VAGSTORE.ZAR`; USB headset via lgaud.irx (+ "Game Speech API V2.02.01" voice recognition).
- Platform: Windows 11, RTX 4070 SUPER, 28 threads, 32 GB. Portable toolchain in `tools/`: llvm-mingw clang 23, CMake 4.4, Ninja, Ghidra 12.1.3, PCSX2 2.8.1 (no BIOS available yet). PS2Recomp builds with clang except one raylib/user32 duplicate-symbol link issue.
- Licensing: PS2Recomp is GPL-3.0; the resulting port must be GPL-3.0 and ship no game data. Horizon Private Server is MIT.

## 3. Approaches considered

1. **Fork PS2Recomp (recommended, chosen).** Static translation of the merged ELF to C++, its EE kernel scheduler, VIF/GIF/GS/VU1 models and IOP-HLE framework exist and are tested; we add what SOCOM needs (989snd, netcnf/inet/DNAS, lgaud, overlay awareness, disc file access, a GPU renderer later). Risk: runtime immaturity (only two games boot to menus); mitigated by owning the fork and by our Unicorn harness for differential debugging.
2. Write our own recompiler + runtime from scratch. Full control, no GPL entanglement, but months of work re-deriving what PS2Recomp already has (VU1 interpreter alone is ~3k lines with tests). Rejected for schedule.
3. Hybrid "recompile EE, embed PCSX2's GS/VU as libraries". PCSX2's GS is not a library and its build is heavy; parallel-gs (Vulkan compute) is the realistic GPU path later. Kept as the phase-2 renderer option, not the bring-up path.

## 4. Architecture

```
socom2.exe (C++20, clang/mingw or MSVC, x64)
├─ recompiled/            EE code from socom2_game.elf → C++ (PS2Recomp fork output)
├─ runtime/  (fork of ps2xRuntime)
│   ├─ EE kernel scheduler (threads, semas, alarms, INTC/DMAC handlers, VBLANK)
│   ├─ memory: 32 MB RDRAM + SPR + I/O (timers, DMAC, VIF0/1, GIF), uncached mirrors
│   ├─ GS: frontend + CPU rasterizer (bring-up) → GPU backend behind GSRasterBackend (phase 2)
│   ├─ VU0 macro (inlined) / VU1 interpreter (MPG/MSCAL/XGKICK)
│   ├─ host I/O: window+input (raylib now; SDL3 acceptable), audio out, gamepad, mic
│   └─ game overrides for SOCOM II (address-bound HLE hooks)
├─ iop/  (fork of ps2xIOP): SIF-RPC services
│   ├─ existing: MCSERV (mc0 → folder), LIBSD, DBCMAN(pad)
│   └─ new: CDVDFSV file access over extracted disc dir / ISO, 989snd, lgaud/headset stub,
│           inet+netcnf+libnetb (→ Winsock), msifrpc, DNAS stub
├─ assets/  (user-provided) extracted disc tree RUN/…, or the ISO read in place
└─ server/  Horizon Private Server (.NET) configured for app id 10472, +DNS/hosts redirection
```

### 4.1 Code images and dispatch
One merged ELF (loader + FTSCore + ZSealEtc) → one dense function table (PS2Recomp's model). DNAS.BIN is never loaded: the loader's "load DNAS + decrypt APACHE00" path (`FUN_001c59c0` / `FUN_001c5b30`) and the `OVERLAY/REL/DNAS.BIN` loader (`FUN_00181c90`) are replaced by host hooks that report success, since the overlays are already resident. Later DNAS authentication calls from FTSCore (sceDNAS2* entry points inside the overlay slot) are hooked to return "authenticated"; the public r0001 bypass address 0x2cc670 is the FTSCore-side check.

### 4.2 Disc access
The game reads via libcdvd (`sceCdSearchFile` + `sceCdRead`/`sceCdStRead`, streaming for VAG/PSS) and its own TOC (`CFileCD::BuildTOC`). Bring-up: point the runtime's cdrom0 root at the extracted disc directory; implement `sceCdSearchFile` against real ISO9660 directory records so LBNs are consistent, by reading the user's ISO directly (preferred, zero extraction step). Movies (`.PSS`) are decoded by the existing libmpeg stubs/FFmpeg path or skipped.

### 4.3 Rendering
Phase 1: PS2Recomp's software GS at native 640x448, enough to validate boot and gameplay logic. Phase 2: GPU backend (Vulkan or D3D11) implementing GIF primitive rendering with swizzled-VRAM emulation, or integrating parallel-gs; target 60 fps at 1080p+. VU1 microprograms are dumped once identified and left interpreted until profiling says otherwise.

### 4.4 Audio
989snd HLE: decode the RPC command set (bank load, play/stop/params, VAG stream start/stop) into a host mixer (XAudio2/WASAPI via miniaudio or raylib audio). Stream data is read from VAGSTORE.ZAR by the EE side (the IOP only receives buffers), so the HLE mostly maps commands to voices.

### 4.5 Input and headset
DualShock 2 report from XInput/DirectInput via raylib/SDL, including pressure-sensitive buttons (crouch uses them). Headset: lgaud HLE presenting a "connected" device; microphone capture feeds rt_audio voice packets (phase 3; stub first).

### 4.6 Networking
- inet.irx/netcnf.irx/libnetb HLE: `sceInet*`/`sceNetCnf*` RPC servers backed by Winsock (TCP/UDP sockets, DNS with a hosts override so `socom2-prod*.pdonline.scea.com` resolve to our server).
- DME/rt_udp traffic is plain UDP/TCP from the EE side, so it flows through the same socket HLE unchanged.
- DNAS: stubbed at the client (never contacts a server).
- Server: Horizon Private Server (MAS 10075, MLS 10078, MPS 10077, NAT 10070/udp, MUIS 10071) with app id 10472 added; SQL Server (local instance or LocalDB) + middleware. Expect Medius 1.50 message-layout differences; resolve them against the decompiled client (the ZSealEtc Medius library has full message name strings). Fallback if Horizon diverges too far: write a minimal Medius 1.50 MAS/MLS/MUIS/NAT server in C# reusing Horizon's RT crypto.

### 4.7 Validation
- Unicorn harness (`tools_py/ee_unicorn.py`) for differential tests of recompiled pure functions (zlib, ZAR/ZED parsers, math) against the original code.
- PCSX2 as the reference once a BIOS is supplied (network via its internal DNS to the same Horizon instance); Play! as a BIOS-free fallback for boot comparison.
- Frame dumps: compare GS output of the software backend with PCSX2 software renderer on the same GIF stream.

## 5. Milestones (each ends with a runnable artifact and a commit)

| # | Milestone | Exit test |
|---|---|---|
| M1 | Fork + toolchain | PS2Recomp fork vendored in repo, builds with clang; merged ELF recompiles to C++; runtime links; `socom2.exe` runs crt0 → `main()` with syscalls logged |
| M2 | Loader → game entry | Memory-card + APACHE00 path HLE'd; control reaches 0x4c53c0; engine init runs (zSys, IRX loads stubbed) without unimplemented-instruction throws |
| M3 | Menu | Legal/intro screens and main menu render (software GS), pad works, 989snd plays UI sounds |
| M4 | Mission | Single-player mission loads from ISO, is playable at ≥30 fps software or with the GPU backend |
| M5 | Online | Horizon with app id 10472 up; client logs in, lobby, create room, second client (PCSX2 or a second socom2.exe instance) joins, round starts |
| M6 | Package | Portable zip: exe + runtime + `install.bat`-free first-run that asks for the ISO path; README, GPL sources |

## 6. Risks
- Runtime bugs in PS2Recomp's GS/VU1/DMAC surfacing only with SOCOM's data (likely, per-game triage is the norm). Mitigation: own the fork, log-driven bring-up, harness diffs.
- Medius 1.50 vs Horizon message formats. Mitigation: message names/handlers recoverable from client decompilation; minimal own server as fallback.
- Performance of the software GS. Mitigation: GPU backend is a planned phase, interface already exists.
- VU1 microprogram location/behaviour unknown until Ghidra work is done. Mitigation: interpreter handles any program; dump via runtime logging.
- No PS2 BIOS for PCSX2. Mitigation: harness + Play!; ask user again when validation is otherwise blocked.
