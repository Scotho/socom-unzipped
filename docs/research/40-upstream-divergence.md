# 40. Where the vendored PS2Recomp fork stands against upstream, and what PR #244 would replace

Date: 2026-09-22. Step zero of Sprint 11 milestone U item 1 (R241). Read-only audit; no code changed. Sources: this
tree's `third_party/ps2recomp/`, the git history of that directory (299 commits), the upstream clone in
`research/ps2recomp/` (git-ignored; `origin` = `github.com/ran-j/PS2Recomp`, fetched 2026-09-22), the disc's IRX files
under `game/disc/`, `docs/research/05`, `06`, `36`.

## 1. The base, and the lineage since

- **Base: upstream `14b1e5c`** ("Start the main thread with COP0 Status.IE set (#214)", 2026-08-19), vendored on
  2026-09-04 as `8736759` ("third_party: vendor PS2Recomp (GPL-3.0, upstream 14b1e5c)"). The commit subject was the
  only record of the base; `THIRD_PARTY_NOTICES.md`'s ps2recomp row now carries it too.
- **Upstream since the base is exactly one commit.** ran-j squash-merges, so `origin/main` is linear: `14b1e5c` →
  `75d729c` "Feature/iop emulator (#244)" (merged 2026-09-20 00:31 UTC, +15,592/−9,145 across 139 files). Every
  earlier upstream change the survey listed (#184 scheduler, #191/#158 VU1, #203 timers, #204 GS, #183 sceVu0, #120
  MPEG, #194 MMI) is BEFORE our base and already in the tree. The open PRs of item 2 (#226-#252) are branches on top
  of `75d729c`, i.e. on the post-#244 tree; each one must be checked for whether it touches ps2xIOP or the SIF stubs
  before it is cherry-picked onto ours.
- `research/ps2recomp/` was a shallow clone at the base; it is now unshallowed and has `origin/main` = `75d729c`.
  It is the reference copy for every diff in this note.

## 2. What we changed since the base

Measured by `diff -rq` of `third_party/ps2recomp/` against the base (excluding `build*/`, `android/`, `vita/`):
**82 base files modified, 89 files or directories added, 0 deleted.** 299 commits, all September 2026.

By subsystem (file-level; the heavy ones by diff size in parentheses, lines of `diff` output against the base):

| Subsystem | Modified base files | Added |
|---|---|---|
| **GS / VU1 / VIF** | `gs/gs_frontend.cpp` (392), `gs/gs_cpu_backend.cpp`, `gs/ps2_gs_memory.cpp`, `gs/ps2_gif_arbiter.cpp`, `ps2_vif1_interpreter.cpp`, `vu/ps2_vu1_{core,lower,upper}.cpp`, `include/runtime/gs/*.h`, `ps2_vu1.h` | `gs/gs_gl_backend.cpp` (the OpenGL renderer), `gs_frame_backpressure`, `gs_stall_coalescer`, `gs_gl_*.h` (caps, depth, target extent, texture/upload identity, upload trace), `vu/native/`, `vu/generated/`, `vu/ps2_vu1_ops.h`, `vu1_native_warning.h` |
| **Audio (host side)** | `ps2_audio.cpp`, `ps2_audio_vag.cpp`, `include/runtime/ps2_audio.h` | `snd989_mixer.cpp` (2,407 lines), `audio_volume.h`, `mix_device.h`, `mpeg_decode_ahead.h`, `ps2_vag.h`, `socom2_music_trace.h`, `host_mic.cpp`, `mic_format.h` |
| **IOP model (ps2xIOP)** | `include/ps2x/iop/iop_host.h` (248: `audioBank/audioNotify/audioIsPlaying/audioPcmWrite/audioPcmPosition`, the `mic*` seam), `src/builtin_profiles.cpp`, `src/module_factories.h` (317), `src/modules/dbcman.cpp` (368), `src/modules/mcserv.cpp`, `CMakeLists.txt` | `src/modules/snd989.cpp` (1,799: the 989snd RPC model of research/06 and /36), `src/modules/lgaud.cpp` (657: the headset), `src/modules/eznetcnf.cpp` (211: network configuration) |
| **SIF / RPC / IOP host (runtime side)** | `ps2_iop_host.cpp` (1,085), `ps2_iop_host.h` (217), `Kernel/Syscalls/RPC.cpp`, `Kernel/Stubs/SIF.cpp` (only 10) | `ps2_iop_transport.h` |
| **EE scheduler and kernel** | `Kernel/EeScheduler.cpp` (497), `include/runtime/ee_scheduler.h` (993), `Kernel/Syscalls/{System (2,033), Dispatcher (628), Thread, Sync, Interrupt, FileIO}.cpp`, `include/ps2_call_list.h` (1,398), `ps2_runtime_macros.h` (283), `ps2_memory.{h,cpp}` (928/287), `ps2_runtime.cpp` (560) | `Kernel/HleStats.*`, `Kernel/SchedTrace.*`, `ps2_guest_clock.h`, `ps2_fpu_trap.cpp` |
| **Other HLE stubs** | `Kernel/Stubs/{CD, GS, LibC, MPEG, MemoryCard, Pad}.cpp` and headers, `Stubs/Helpers/Support.h` | `injected_pad_latch.h`, `host_gamepad*.h`, `host_crouch_shortcut.h` |
| **SOCOM-specific** | `main.cpp`, `ps2_debug_panel.cpp`, `ps2_pad.cpp` | `game_overrides_socom2.cpp`, `socom2_{hostnet, libnetb, crypto, host_input, bank, cull_trace, freeze_fields, lum_readback, osk_prefill}.*`, `socom2_rsa_key.h`, `host_window_chrome*.cpp`, `ps2_window_size.h` |
| **Recompiler** | `instruction_translator.cpp`, `fpu_translator.cpp`, `control_flow_emitter.cpp`, `vu_translator.cpp`, `vu_translation_helpers.cpp`, `Translators/vu_translator.h` | — |
| **New modules** | — | `ps2xLauncher/` (raylib launcher), `ps2xShared/` (knob registry, exit codes) |
| **Tests** | 12 upstream test files (`ps2_runtime_expansion_tests.cpp` 3,618; `ps2_runtime_kernel_tests.cpp` 3,523; `ps2_runtime_io_tests.cpp` 1,996; `ps2_gs_tests.cpp` 1,372; `MiniTest.h`, `main.cpp`, …) | 20 new test files (`socom2_audio_tests`, `socom2_lgaud_tests`, `socom2_libnetb_tests`, `vu1_native_tests`, `gs_frame_backpressure_tests`, `launcher_tests`, `knobs_tests`, …), `mc0/` |

Not touched by us and identical to the base: `ps2xIOP/src/modules/libsd.cpp` (63 lines), `clfile.cpp`, `cri_dtx.cpp`,
`sdrdrv.cpp`, `tsnddrv.cpp`, `sound_update_stub.cpp`, `plugin_loader.cpp`, `plugin_api.h` -- the parts of the
upstream IOP model we never used.

## 3. What PR #244 is

`ps2xIOP` becomes an IOP **emulator**: an R3000A interpreter (`emulator/core/iop_cpu.cpp`), a virtual IOP kernel
(`iop_kernel.cpp`: threads, semaphores, events, message boxes), a separate 2 MB IOP RAM (`iop_memory.cpp`), an IRX
loader with relocation and export-table registration (`services/iop_module_loader.cpp`, `imports/iop_imports.cpp`),
a SIF RPC bridge (`services/iop_rpc.cpp`), native import providers for the ROM libraries, and 2,200 lines of tests.
No BIOS is needed.

- **Native import libraries** (dispatched in `iop_emulator.cpp:248-342`): sysmem, loadcore, intrman, sifman, sifcmd,
  ioman, modload, stdio, sysclib, thbase/threadman, thevent, thsemap, timrman, vblank, cdvdman, secrman, heaplib,
  dmacman. Anything else must come from a physically loaded IRX's export table.
- **Load policy** (`iop_subsystem.cpp:117-145`): a `loadModule(path)` tries the **physical IRX first** (bytes from the
  runtime's `PS2RomDevice`); only if that fails does it fall back to an HLE record for a recognised ROM-module name
  (the 39-name list in `iop_module_manager.cpp:11-49`, plus any registered service's aliases). There is no
  "prefer HLE for this module" switch. "A physical IRX RPC server is authoritative for its SID."
- **Remaining HLE services**: MCSERV (`0x80000400/0x80000480`), LIBSD (`0x80000701`, forwarded to
  `IopHost::audioCommand`), DBCMAN (`0x80001300`). Dormant until a recognised module load.
- **Deleted**: the game-profile plugin ABI (`plugin_api.h`, `plugin_loader.cpp`, `PluginExample.md`),
  `builtin_profiles.cpp`, the TSNDDRV / CRI DTX / CLFILE / SDRDRV / SOUND-stub HLE modules. `module_factories.h`
  shrinks by 147 lines.
- **IopHost gains** (with no-op defaults, so source-compatible): `readIopMemory`, `writeIopMemory`, `zeroIopMemory`,
  `normalizeIopAddress`, `sendSifCommand` (IOP → EE SIF command packets).
- **Runtime side**: `SIF.cpp` rewritten (133+/279−), `ps2_runtime.cpp` owns the subsystem and a `PS2Vfs` +
  `PS2RomDevice` (new `ps2_vfs.h`, `ps2_rom_device.h`), `EeScheduler` gains `advanceIopEeCycles(elapsed)` (the IOP
  runs on EE cycle accounting from the scheduler) and a `SifCommand` invocation kind, `FileIO.cpp` goes through the
  VFS, `sceSifRebootIop`/`sceSifResetIop` call `PS2Runtime::resetIop()`.
- **Also in the same squash, unrelated to the IOP**: `elf_parser.cpp` +1,196 lines and `ExportPS2Functions.java`
  +414 (a Ghidra export path), a GS texture page cache header, `gs_cache/` tests. These ride along with any merge.

## 4. The conflict surface

`comm` of "files we modified" against "files #244 touches": **40 files**, listed with our diff size against the base:

- Runtime core: `Kernel/Syscalls/System.cpp` (2,033), `ps2_iop_host.cpp` (1,085), `ee_scheduler.h` (993),
  `ps2_memory.h` (928), `Dispatcher.cpp` (628), `ps2_runtime.cpp` (560), `EeScheduler.cpp` (497), `gs_frontend.cpp`
  (392), `ps2_memory.cpp` (287), `ps2_runtime_macros.h` (283), `ps2_iop_host.h` (217), `ps2xRuntime/CMakeLists.txt`
  (173), `ps2_vif1_interpreter.cpp` (124), `gs_cpu_backend.cpp` (121), `Support.h` (100), `ps2_gs_memory.cpp` (88),
  `gs_backend.h`, `ps2_runtime.h`, `RPC.cpp`, `SIF.cpp` (10), `FileIO.cpp` (6), `ps2_debug_panel.cpp`, `gs_cpu_backend.h`,
  `ps2_gs_memory.h`, `ps2_call_list.h` (1,398).
- IOP: `iop_host.h` (248), `module_factories.h` (317), `modules/dbcman.cpp` (368), `modules/mcserv.cpp` (15),
  `ps2xIOP/CMakeLists.txt`; and **`builtin_profiles.cpp`, which we modified and #244 deletes.**
- Recompiler: `instruction_translator.cpp` (13).
- Tests: `ps2_runtime_expansion_tests.cpp` (3,618), `ps2_runtime_kernel_tests.cpp` (3,523), `ps2_runtime_io_tests.cpp`
  (1,996), `ps2_gs_tests.cpp` (1,372), `ps2_runtime_interrupt_tests.cpp` (323), `ps2_memory_tests.cpp`,
  `code_generator_tests.cpp`, `ps2_sif_rpc_tests.cpp`, `ps2xTest/CMakeLists.txt`.

Reading of the surface: #244's runtime-side changes are individually small (`EeScheduler.cpp` 56 lines, `ps2_iop_host.cpp`
68, `ps2_runtime.cpp` 89) and `SIF.cpp`, which it rewrites, is a file we barely touched. The cost is not the merge
of #244's lines; it is that our IOP host adapter, our four "builtin" profiles, our three IOP modules and their tests
(`ps2_iop_tests.cpp`, `fake_iop_plugin.cpp`, `fake_iop_missing_symbol.cpp`, `socom2_audio_tests.cpp`,
`socom2_lgaud_tests.cpp`) are written against an interface #244 removes, and that #244's load policy would run the
disc's IRX files where we run HLE.

## 5. What #244 replaces that we depend on

1. **The profile plugin ABI.** `PS2IopHostAdapter` (`ps2_iop_host.{h,cpp}`), `ps2_runtime.{h,cpp}`,
   `ps2_iop_transport.h` and five test files include `ps2x/iop/iop_host.h` / the profile types; our
   `builtin_profiles.cpp` defines four "builtin" profiles. All of that must be re-expressed as #244's
   `IopSubsystem(IopHost&)` + registered services + `setServiceModuleKeys`.
2. **Our HLE IOP modules would be bypassed by the load policy.** With the disc present, `loadModule("cdrom0:\...\989SND.IRX")`
   loads the physical IRX; our `snd989.cpp` service would never be routed to (a physical RPC server owns its SID). The
   same for `lgaud.cpp` (LGAUD.IRX), `eznetcnf.cpp`, and the EE-side network HLE (`socom2_libnetb.cpp`, the msifrpc
   HLE of `d738b29`): the physical LIBNETB.IRX / INET.IRX / INETCTL.IRX / DEV9.IRX would load and run against
   hardware the emulator does not model (DEV9/SMAP are a register bag), and online would die. **A "prefer HLE for
   these module names" policy is a prerequisite for any adoption**, and it does not exist upstream.
3. **The host audio seam.** Our `IopHost` extension (`audioBank`, `audioNotify`, `audioPcm*`, `mic*`) is ours and
   survives a merge, but in #244's world nothing calls it unless our services stay routed.
4. **The scheduler contract.** #244 drives the IOP from `EeScheduler` via `advanceIopEeCycles`; our scheduler
   (497 lines changed, `SchedTrace`, the guest clock, the stall bound of Q6) is where that hook has to land, and the
   IOP's interpreted cycles then compete with the frame budget the GS backpressure work tuned.
5. **IOP reboot.** Our `SIF.cpp:713` records that SOCOM II calls neither `sceSifRebootIop` nor `sceSifResetIop`;
   research/05 §"Reference boot" records PCSX2 seeing "IOP reboot with DNAS271.IMG" from the loader. Both can be
   true (the loader may reboot through `LoadExecPS2`/the BIOS path rather than the SIF stub) but it is unmeasured on
   our side and #244's `resetIop()` semantics differ from our reboot stub's. To be checked before any merge.

## 6. The finding that changes the plan: #244 has no SPU2

The owner's motive for item 1 is the unresolved audio: run SOCOM's own `989SND.IRX` instead of our model of it.
Traced through #244:

- `989SND.IRX` (163 KB, "Sep 22 2003") imports **libsd**, cdvdman, intrman, ioman, loadcore, sifcmd, sifman, stdio,
  sysclib, sysmem, thbase, thsemap, timrman, and exports `snd989`. `989DSTRM.IRX` imports `snd989`. `HEADSETO.IRX`
  imports `snd989` and `lgaud`. (Import tables read from the disc's files; the full table is §7.)
- **libsd is not a native import in #244.** It can only come from the physical `LIBSD.IRX` (28 KB; imports intrman,
  loadcore, sifman, sysclib, thevent; exports `libsd`), which #244 can load and run.
- `LIBSD.IRX` talks to the SPU2 through registers at `0x1F900000-0x1FA00000` and SPU DMA. In #244's `iop_memory.cpp`
  that range is a **plain register bag**: writes are stored in a map, reads return the stored word or 0
  (`readHardware32`/`writeHardware32`, lines 210-270). The only modelled behaviour is an SPU DMA `CHCR` start bit,
  which sets the SPU2 status bit `0x80` and schedules a DMA-complete interrupt after a cycle count derived from the
  block-control word. **No SPU RAM, no voices, no ADPCM decode, no ADSR, no mixing, no output.** `grep -i
  "voice|adpcm|envelope"` over `ps2xIOP/src/emulator` at `origin/main` matches nothing.
- The LIBSD **HLE service** #244 keeps is the EE-side RPC at SID `0x80000701` (the sdrdrv-style path some games
  use), forwarded to `IopHost::audioCommand`. 989snd does not use it; it calls libsd's exports in IOP address space.

So: **#244 as merged runs the real 989snd sequencer and the real streamer, correctly, into silence.** The audio
motive is not served by adoption alone. The options:

- **(A) An SPU2 core behind the register bag.** 48 voices, 2 MB SPU RAM, ADPCM, ADSR, pitch, per-voice and core
  volumes, DMA in/out, IRQ, core attributes. The right long-term answer and what PCSX2 has; several thousand lines
  and its own parity campaign. Weeks.
- **(B) A native `libsd` import provider** in #244's dispatch (the same shape as its `heaplib`/`dmacman` cases),
  implementing libsd's ~50 exports (`sceSdInit`, `SetParam`, `SetAddr`, `SetSwitch`, `SetCoreAttr`, `VoiceTrans`,
  `BlockTrans`, `SetTransCallback`, …) on a **voice-level** model: SPU RAM as a byte array the IRX uploads into, a
  voice table, key-on/off, and a mixer that decodes VAG from SPU RAM at the voice's pitch. Our `snd989_mixer.cpp`
  already has the VAG decoder, the resampler, the pan table and the device output; what changes is the unit of
  state, from "989snd handle" to "SPU2 voice". The real sequencer, the real stream engine, the real bank parser and
  the real handle/liveness logic (the things research/36 found our model diverging on) become authoritative.
  Estimate 1,500-2,500 lines plus tests. This is the version of "pull in the real IOP" that could resolve the audio
  defects; it is not a spike.
- **(C) Adopt #244 for the kernel and loader, keep every HLE we have** via the prefer-HLE policy of §5.2. Gains us
  upstream's tests, the VFS and the IRX loader, changes no audible behaviour. A refactor with no payoff for the
  owner's motive.

## 7. SOCOM's IRX set against #244's kernel

The game's load order (research/05, PCSX2 reference boot): loader `SIO2MAN, CDVDSTM, SIO2D, DBCMAN, DS2U_S1, MCMAN,
MCSERV` after an IOP reboot with `DNAS271.IMG`; game code `USBD, USBKB, DEV9, LIBSD, 989SND, 989DSTRM, LGAUD, HEADSETO`,
and for online `LIBNETB` (+ `MSIFRPC`, `INET`, `INETCTL`, `EZNETCNF`, `EZNETCTL`). Imports read from the files:

| Module | Imports not native in #244 | Hardware it drives | Under #244 as-is |
|---|---|---|---|
| SIO2MAN | — | SIO2 (register bag) | runs, no pads/cards behind it |
| SIO2D, DS2U_S1 | sio2man, sio2d, dbcman (from IRXs) | SIO2 | run; our pads are EE-side `scePad2` HLE (`594b887`), unaffected |
| MCMAN, MCSERV | sio2man, mcman (from IRXs) | SIO2 | would run for real and find no card; **must stay HLE** (MCSERV HLE exists upstream; MCMAN would need a prefer-HLE entry) |
| CDVDSTM | — | via cdvdman (native) | plausible |
| LIBSD | — | **SPU2 (register bag)** | runs, silent (§6) |
| 989SND, 989DSTRM | libsd, snd989 (from IRXs) | SPU2 via libsd, CD via cdvdman | run, silent |
| USBD, USBKB, LGAUD, HEADSETO | usbd, lgaud, snd989 (from IRXs) | USB (register bag) | run, enumerate nothing -- acceptable (our HLE reports no device) |
| DEV9, INET, INETCTL, LIBNETB, MSIFRPC, EZNET* | dev9, inet, inetctl, netcnf, msifrpc, modem… (from IRXs) | DEV9/SMAP (register bag) | run against nothing; **must stay EE-side HLE** |
| DNAS271.IMG (IOPRP) | — | IOP reboot image | not a module; see §5.5 |

Every import SOCOM's modules need is either native in #244 or exported by another module on the disc, so **loading
is not the blocker; hardware is.** The three hardware classes behind these modules (SIO2, SPU2, DEV9/USB) are all
register bags in #244.

## 8. What step (b) can and cannot measure inside the stop rule

The brief asks for the music parity pair measured with the real-IRX IOP running `989SND.IRX`, a number against the
current path, with a one-day stop rule to the title screen. §6 says that number is **zero by construction**: without
(A) or (B) the real IRX produces no audio, so the parity scorer would read silence against the console. Reaching the
title screen with #244 merged is plausible in a day only if the merge of §4 is skipped; with it, the merge alone is
the day.

The measurement that IS reachable, and that the audio motive actually needs first, is the **RPC differential**: run
the real `LIBSD.IRX` + `989SND.IRX` + `989DSTRM.IRX` on #244's `ps2xIOP` built standalone (`-DPS2X_IOP_BUILD_TESTS=ON`,
its own CMake, no game build), from a test host modelled on `iop_emulator_tests.cpp`'s `TestHost`, feed them the same
RPC sequences `socom2_audio_tests.cpp` feeds our `snd989.cpp` (bank load, play, `snd_SoundIsStillPlaying` polls,
`snd_SetSoundParams`, stream open/queue), and diff the answers and the libsd register/DMA traffic the IRX emits
against our model's answers. That is research/36's audit done by execution instead of by reading, on the exact IRX
build the disc ships (the decomp is v3.01; the disc's is older, with different struct offsets). It needs no SPU2,
no merge, and no lock beyond the small standalone build. Its output is a table of divergences with the IRX as the
oracle, which is the input (B) would be built from.

Recommendation for the controller: run the RPC differential as step (b) under the existing stop rule; treat (B) as
a Sprint 11 goal in its own right, sized from the differential's table; do not merge #244 into the fork until the
prefer-HLE policy (§5.2) and the reboot question (§5.5) are settled. Item 2's cherry-picks are independent of all
of this as long as each PR is checked for ps2xIOP/SIF contact (§1).

## 9. Numbers this note rests on (re-derivable)

- `git -C research/ps2recomp rev-list --count 14b1e5c..origin/main` = 1; `git log 14b1e5c..origin/main` = `75d729c`.
- `git log --oneline -- third_party/ps2recomp | wc -l` = 299; first is `8736759`.
- `diff -rq -x build -x .git -x android -x vita research/ps2recomp third_party/ps2recomp` (with the reference clone
  checked out at `14b1e5c`): 82 "differ", 89 "Only in third_party", 0 "Only in research".
- Overlap: `comm -12` of the 82 against `git diff --name-status 14b1e5c origin/main` (non-D) = 40; against D = 1.
- IRX import tables: scan each file under `game/disc/**/*.IRX` for the import magic `0x41e00000` (name at +12) and
  the export magic `0x41c00000`.
