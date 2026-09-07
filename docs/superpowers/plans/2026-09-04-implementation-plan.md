# Implementation plan (living task list)

Conventions: one commit per task; run `./build.sh runtime` + `PS2X_PC_SAMPLER=5 ./run.sh 40`
after every runtime change; append findings to `docs/research/05-code-package-and-harness.md`;
update `docs/STATUS.md` at the end of a session.

## M2 — engine init (current)
1. [ ] Resume the interrupted build (`./build.sh runtime`), run, confirm the alarm handler
       0x34f120 wakes the main thread. If still asleep: check `EeScheduler` alarm → `queueInvocation`
       delivery while all threads sleep (event loop must process host-time events when idle).
2. [ ] Replace "End = next function start" for forced entries: feed `recomp/extra_functions.txt`
       to Ghidra (`MakeFunctions.java`, then analysis) and re-export so bounds are real; drop the
       unhandled-instruction noise back to ~11k.
3. [ ] Loop on `[guest-branch:missing-target]`: add each target to `extra_functions.txt`, rebuild.
       Consider extending `find_imm_targets.py` to `jalr`-fed tables (`lw rX, off(gp)` pointers in .data).
4. [ ] Implement `LoadExecPS2` in the runtime: reset scheduler/memory, reload the ELF, pass argv
       (loader `main(argc, argv)` parses `--menu_state <rdr>` etc.). Needed for error reboots and
       for the network-config flow.
5. [ ] Trace IOP module loads (`sceSifLoadModule` paths/args) and RPC binds to compare with the PCSX2
       reference order; stub any RPC the engine blocks on (eznetcnf/eznetctl 0x75499128/0x75488909,
       lgaud 'BLIP', usbkb 0x80000211).

## M3 — menu
6. [ ] DBCMAN/ds2u pad HLE: implement the libdbc RPC protocol (init, socket create, DS2 report
       with pressure) on top of the runtime's raylib gamepad/keyboard backend. XInput mapping in
       `ps2_pad.cpp` (crouch uses pressure-sensitive buttons).
7. [ ] Verify GS output of the legal/intro screens (software GS); fix VIF/GIF/DMA issues as they
       appear; MPEG intro (`INTRO_2.PSS`) via the runtime's libmpeg/FFmpeg path or skip.
8. [ ] 989snd host backend: decode bank VAG chunks and VAG streams from the ISO by sector, voices
       with volume/pan/pitch, master groups (see `docs/research/06-989snd-rpc.md` §5).
9. [ ] Memory card: `mc0` folder mapping works; confirm SOCOM's save/netcnf files persist.

## M3-parity — shell screens scored against PCSX2 (current, 2026-09-07 17:45)
Grade: `docs/parity/REPORT.md` (see HANDOFF "The grade"). Targets: ≥90 static screens, ≥75 animated.
- [x] 2D placement (vf00 writes clobbered the constant register) — popup 99.6, rank 99.2, briefing 96.2
- [x] Text (GL face culling, CSM1 CLUT swizzle, CPU sprite texcoords)
- [ ] Main menu 79: MENULOOP.PSS background + `mainmenu_roller` (UI_GEO/UI_MDL) via the VU1 packet path whose header kick flag is clear (HANDOFF task 0)
- [ ] Controller configuration screens (3D controller models, same path)
- [ ] Text-only title cards: appear but flash past our capture; align the script/timing
- [ ] Glyph weight slightly heavier than the original (shadow pass alpha?) — low priority

## M4 — mission (M2/M3 items above are done except 2, 4 and 8 — see STATUS)
9a. [x] Find why the mission tick ran twice in 30 s → the auto-exposure thread `FUN_003b1dd0`
        starved the main thread (its one-pixel GS readback `FUN_003b24c0` spun to timeout on the
        unimplemented VIF1 reverse-FIFO path). Stubbed via `socom2_LumReadPixel@0x003B24C0`.
9b. [ ] Verify with the stubbed build that `MissionTick` runs per frame and the frame counters move;
        if nothing draws, trace `FUN_0033bf30`/`FUN_0033be70`/`FUN_001fba70` submissions.
9c. [ ] Implement GS local→host readback (BUSDIR, VIF1 reverse DMA + FIFO/FQC) and drop the stub.
9d. [ ] Animation keyframe fault (`FUN_00289bb0`, unset keyframe pointer) — 16 non-fatal faults at load.
10. [ ] Streaming: `CFileCD`-style LBN reads at scale, `sceCdStRead` stream buffers, VAGSTORE streams.
11. [ ] VU1: identify SOCOM's microprograms (uploaded by VIF MPG from model data / zRender);
        verify interpreter output vs PCSX2 software renderer on the same frame.
12. [ ] GPU GS backend behind `GSRasterBackend` (Vulkan/D3D11) or parallel-gs integration; target
        1080p 60 fps.
13. [ ] Performance: generated code at -O2/-O3 with LTO for release builds (`LTO=ON ./build.sh runtime`).

## M5 — online
14. [ ] Network config without `SCUSNGUI.ELF`: HLE eznetcnf/netcnf to report a canned
        configuration (DHCP-less static config is fine) so the game skips the utility.
15. [ ] inet/libnetb HLE → Winsock (sceInet* socket calls: create/bind/connect/send/recv/select,
        DNS via hosts override for `socom2-prod.pdonline.scea.com`, `socom2-prod.muis.pdonline.scea.com`).
16. [ ] DNAS: stub libdnas2 authentication to success (r0001 bypass point 0x2cc670 in FTSCore;
        also the `sceDNAS2*` calls in the DNAS overlay slot — DNAS.BIN is never loaded now).
17. [ ] Medius 1.50 vs Horizon: capture the MAS handshake, fix message layouts in `RT.Models`
        (server/README.md lists the risks), UDP DME/rt_udp P2P path, NAT server.
18. [ ] Two clients (this exe + PCSX2 with DEV9 internal DNS → same Horizon) in one room.
19. [ ] Voice: lgaud/headset HLE (mic capture → rt_audio); stub first.

## M6 — package
20. [ ] First-run setup: ask for the ISO path, extract nothing, run in place; `mc0` in a user dir.
21. [ ] Portable zip: `socom2.exe`, DLLs, README, GPL sources pointer; optional installer.
22. [ ] Extension points documented: `game_overrides_socom2.cpp` (EE hooks), `ps2xIOP` services,
        Horizon plugins (`server/medius-plugins`).
