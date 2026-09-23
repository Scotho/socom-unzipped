# 41. The MrCoolTheCucumber/PS2Recomp fork, read for design: what is worth taking

Date: 2026-09-22. Sprint 10 close, milestone U item 4, on the owner's ruling of the same day ("Real cool cucumbers
work as well" -- read for design, identify specific pieces, do not merge wholesale). Read-only: nothing in this
repository changed except this note. Sources: a shallow clone of the fork in `research/ps2recomp-cucumber/`
(git-ignored) at HEAD `7978365` ("feat(runtime): add portable save states", 2026-08-16, the fork's last commit);
the GitHub compare and commit APIs for the 546 fork-only commit subjects and for individual patches; this tree's
`third_party/ps2recomp/`; `docs/research/40-upstream-divergence.md` (which exists only on branch `agent/upstream`,
commit `83c02d9`, not in this working tree); `docs/KNOWN.md`, `docs/STATUS.md`.

## Summary (ten lines)

1. The fork diverged from ran-j at `f3687c5a` ("Feature/random fixes platform support (#179)", 2026-07-22) --
   **four weeks and seven upstream PRs BEFORE our base `14b1e5c`**. It is 546 ahead, 10 behind; those 10 are
   upstream's VU1 refactor (#191), EE scheduler refactor (#184), EE timers (#203), GS refactor (#204), sceVu0
   (#183), the MMI2 opcode fix (#194) and two more -- all of which we have and it does not.
2. Consequence: **no cherry-pick into our GS, VU1 or EE scheduler can be clean.** Those three subsystems were
   rewritten by both sides from different ancestors. Anything from them is an idea, not a patch.
3. Worth taking, first: **three recompiler correctness fixes we still carry the bug for**, verified in our tree
   today -- MOVZ/MOVN clobbering the upper 64 bits (`3e2ea9f4`), BLEZ/BGTZ/BLTZ/BGEZ compared as signed 32-bit
   instead of 64 (`60d14c43`), VU FTOI not saturating (`78ce1a21`). ~40 lines of generator change plus tests, in
   files that are stable across the divergence. Cost: a full recomp+rebuild and a 3/3 gate, not the edit.
4. Worth taking, second: **the per-subsystem `*RuntimeState` refactor** (`ps2xRuntime/src/lib/Kernel/{Stubs,
   Syscalls}/Helpers/*RuntimeState.h`, 14 headers, ~1,100 lines, landed as ~30 paired commits on 2026-07-30, each
   a RED "test: expose cross-runtime X aliasing" followed by its fix). This is the shape that makes our reverted
   `955539c` Support.h hygiene change safe: one named struct per subsystem instead of nineteen private copies.
5. Worth taking, third: **the save-state container** (`ps2_save_state.h`/`.cpp`, 679 lines + 478 test lines) --
   magic, version, chunked, atomic write, bounded reader, zero dependencies. The 2,961-line chunk writer that
   fills it enumerates *their* runtime state and is not portable; only the container is.
6. **ADAPT, do not take:** the GS `Verify` renderer mode (run the accelerated backend and the software raster on
   the same draw and count mismatches) -- our `gs_cpu_backend.cpp` is already the oracle it needs; and the
   flush-reason / fallback-reason attribution arrays, which answer "why did this draw cost a readback" -- the
   question `docs/KNOWN.md` section 2's "21k texture uploads a second" row cannot currently ask.
7. **LEAVE:** the Vulkan GS backend (11.4k + 2.9k lines, 21 compute shaders, built on the pre-#204 GS) -- the
   owner's bar of "an overwhelming case" is not met; we have a working GL backend and a CPU oracle.
8. **LEAVE:** the performance HUD process (3.2k lines, Linux-only by construction: AF_UNIX, `posix_spawn`,
   `XDG_RUNTIME_DIR`, `/proc` thread sampling, imgui+raylib) -- our primary target is Windows.
9. **LEAVE:** the async VU1 owner thread with speculation and causal ordering, and the EE fiber backend. Ours are
   ahead for our purpose: a 162/166-native VU1 keyed by FNV program hash, and a single-executor EE scheduler with
   a per-guest-thread trace richer than anything the fork prints.
10. Licence: GPL-3.0 both sides, no obstacle. Three permissive third-party deps ride along only with pieces we are
    not taking (Xbyak BSD-3-Clause with the VU JIT, Boost.Context BSL-1.0 with the fiber backend, imgui/raylib
    with the HUD). Nothing in the fork is licence-incompatible with us.

---

## 1. Relationship to upstream, and to our base

`GET /repos/ran-j/PS2Recomp/compare/main...MrCoolTheCucumber:PS2Recomp:main` (2026-09-22):

| | |
|---|---|
| status | diverged |
| merge base | `f3687c5ae636afc8d95cd4f85becce03ca529e25`, 2026-07-22, "Feature/random fixes platform support (#179)" |
| ahead | 546 |
| behind | 10 |

The fork's own history runs 2026-07-23 (`3e2ea9f4`) to 2026-08-16 (`7978365`) -- 546 commits in 25 days, one
author, then silent for five weeks. Our base is `14b1e5c` (2026-08-18, upstream #214).

**The fork's merge base predates our base.** The ten commits it is behind are exactly the upstream work between
them, and they are the structural ones:

```
6970f3a2 2026-07-28 feat(hle): implement sceVu0 macro-mode matrix/vector math library (#183)
d87bff42 2026-08-01 fix(recomp): incorrect opcode mapping for MMI2 in PMADDH, PHMADH, PMSUBH and PHMSBH (#194)
61300792 2026-08-01 fix(recomp): include <cstdint> before elfio in elf_parser.h (#199)
f49ca4ed 2026-08-05 refactor: refactor VU1 (#191)
f4309cd1 2026-08-11 refactor: from guest threads to EE scheduler (#184)
8d7e8a5a 2026-08-12 Feature/ee timers and fixes (#203)
d74a3ce1 2026-08-14 Feature/gs refactor (#204)
d9ea4fb6 2026-08-18 Let a thread resume at the instruction after a syscall (#210)
14b1e5cb 2026-08-18 Start the main thread with COP0 Status.IE set (#214)   <- our base
75d729ce 2026-09-20 Feature/iop emulator (#244)                            <- after our base; research/40
```

So for VU1, the EE scheduler and the GS the fork and we are two independent rewrites of two different ancestors.
Its `ee_thread_scheduler.cpp` and our `Kernel/EeScheduler.cpp` share no lineage; its `ps2_gs_gpu.cpp` and our
`gs/gs_frontend.cpp` + `gs/gs_gl_backend.cpp` share no lineage. The only files where a patch can still apply by
context are the recompiler's translators (`ps2xRecomp/src/lib/*_translator.cpp`, `mmi_translation_helpers.cpp`,
`vu_translation_helpers.cpp`, `control_flow_emitter.cpp`), which both sides left largely alone -- and which are
where the cheapest wins are.

Rough shape of the fork, for scale: `ps2xRuntime` is 168,808 lines of `.cpp`/`.h`; `ps2_runtime.cpp` alone is
18,826, `ps2_gs_vulkan.cpp` 11,442, `ps2_memory.cpp` 10,617.

---

## 2. Portable save states

**Files.** `ps2xRuntime/include/runtime/ps2_save_state.h` (125), `src/lib/ps2_save_state.cpp` (554),
`src/lib/ps2_memory_save_state.cpp` (922), `src/lib/ps2_runtime_save_state.cpp` (2,961), tests
`ps2xTest/src/ps2_save_state_tests.cpp` (478). One commit, `7978365` "feat(runtime): add portable save states"
(+5,700 / -19 over 28 files), plus small serialisation hooks in `cop0_timing.cpp`, `ee_counters.cpp`,
`ee_event_scheduler.cpp`, `ee_thread_scheduler.cpp`, `ps2_vu1_command_stream.cpp`, `vu/ps2_vu1_core.cpp`,
`src/main.cpp` (the key binding).

**Design.** Two layers, cleanly split.

- *Container* (`ps2_save_state.h/.cpp`): an 8-byte magic, `kContainerVersion = 1`, at most 256 chunks, a 512 MiB
  file cap; `Writer`/`Reader` with explicit little-endian `u8/u16/u32/i32/u64/i64/f32/f64/bytes/sizedBytes/string`
  and `[[nodiscard]] bool` on every read; `Chunk{id, version, flags(Required), payload}`; `Document::find(id)`;
  `encode`/`decode`/`writeFileAtomically`/`readFile`. "Portable" means the byte layout is fixed and a reader that
  does not know a chunk skips it unless it is `Required`. **It depends on nothing** -- `<span>`, `<filesystem>`,
  `<vector>`. C++20.
- *Content*: seven chunks -- `META`, `MEM0`, `CORE`, `VU00`, `VU10`, `GS00`, `HLE0`. `HLE0` is written by
  enumerating the fork's fourteen `*RuntimeState` structs (section 3); `MEM0` is `ps2_memory_save_state.cpp`;
  `CORE` reaches into their COP0 timing, EE counters, event scheduler and thread scheduler.

**What it depends on that we do not have.** The content layer depends on (a) the `*RuntimeState` refactor, (b)
their EE thread scheduler and event scheduler shapes, (c) a VU1 that can be quiesced on command
(`Vu1SnapshotCommand` / `Vu1RestoreCommand` in `ps2_vu1_command_stream.h`, which only exist because their VU1 is
an owner thread). None of (b) or (c) maps onto us. Our own state also includes things theirs has never had: the
IOP model (`ps2xIOP`), `snd989_mixer`, the hostnet/libnetb socket state, the GL backend's texture cache.

**Map onto ours.** The container is a drop-in. The content would have to be written from scratch against our
`PS2Memory`, our `ee_scheduler.h`, our `vu/ps2_vu1_core.cpp` and our HLE stubs -- and a save state that captures
an online match is not meaningful anyway (the peer and the server are not in the file).

**Recommendation: TAKE the container, LEAVE the content.** ~680 lines of source and ~480 of tests, no
dependencies, no conflict surface, immediately useful for anything we need to serialise deterministically (a VU1
program table, a GS replay header, a parity fixture). The full save state is a Sprint-12-sized project of its own
and should be judged on its own merits, not smuggled in with a container.

---

## 3. The `*RuntimeState` refactor (not in the brief's list; the most valuable thing in the fork)

**Files.** `ps2xRuntime/src/lib/Kernel/Stubs/Helpers/{Audio,Cd,Dma,LibC,MemoryCard,Pad,Sif}RuntimeState.h` (52-83
lines each) and `Kernel/Syscalls/Helpers/{Alarm,Deci2,File,Interrupt,Kernel,Rpc,Sync,Thread}RuntimeState.h`
(35-576 lines). ~1,100 lines total excluding `ThreadRuntimeState.h` (576). Landed 2026-07-30 as ~30 paired
commits inside a 45-commit block (`53af236e...c0331678`, +9,557 / -2,809 over 74 files), every pair being
"test: expose cross-runtime X aliasing" then "runtime: isolate X state per runtime" -- `Deci2`, `audio`, `IO
path`, `libc and memory-card`, `pad`, `DMA`, `file and CD`, `SIF`, `EE RPC`, `EE kernel`, `MPEG`, `EE VSync and
GS callback`, `EE interrupt`, `EE sync`, `EE alarm`, `presentation cache`, `guest working directory`.

**Why it matters to us.** `docs/KNOWN.md` section 1 records, proven, 2026-09-21: moving
`Kernel/Stubs/Helpers/Support.h`'s anonymous-namespace state into a `.cpp` gave nineteen translation units one
shared `g_cdFilesByKey`, `g_cdStreamingLbn`, `g_cdMode`, `g_nextPseudoLbn`, `g_iopHeapNext` instead of nineteen
private copies, and the mission gate failed with an 18,852-command GL backlog; it was reverted (`955539c`) and the
item left open with the instruction "one group of state at a time, each with a gate."

The fork's `CdRuntimeState` is *literally that group*: `filesByKey`, `leafIndex`, `loosePathIndex`,
`nextPseudoLbn`, `mode`, `streamingLbn`, `streamingEndLbn`, `initialized`, plus a `resetLocked()` that names every
field. Their motive was different (several `PS2Runtime` instances in one process), but the target shape is the
one our open item needs, and the commit sequence is the method: a test that *exposes* the sharing, then the fix.

**Recommendation: ADAPT.** Not a cherry-pick -- our `Support.h` is 1,967 lines of SOCOM-specific stub state and
theirs is not. Take the pattern and the discipline: one `struct XRuntimeState` per group with an explicit
`reset()`, a test that fails before the change, a gate after. Estimate for the four groups our KNOWN row names
(CD, IOP heap, MPEG, audio): 600-1,200 lines of mechanical change plus four RED tests, four gates. This is the
piece with the clearest owner-visible payoff, because it closes a proven-open item rather than adding a feature.

---

## 4. The Vulkan GS backend and its batching diagnostics

**Files.** `src/lib/ps2_gs_vulkan.cpp` (11,442), `ps2_gs_vulkan_backend.cpp` (2,928),
`include/runtime/ps2_gs_vulkan.h` (1,763), `ps2_gs_vulkan_backend.h` (224), plus the seam:
`ps2_gs_backend.cpp` (2,761) / `.h` (660), `ps2_gs_coherency.cpp` (252), `ps2_gs_command_stream.cpp` (1,955),
`ps2_gs_gpu.cpp` (3,877), `ps2_gs_rasterizer.cpp` (6,845), `ps2_gs_replay.cpp` (662); and 21 compute shaders in
`src/lib/shaders/` (`ps2_gs_ct32_sprite.comp` etc., each with a checked-in `_spv.inc`). Roughly 130 commits,
2026-08-01 to 2026-08-16, from `a273c053` "gs: add backend-neutral draw command seam" through
`bfc52ef7` "gs: add Vulkan verification backend" to `7267ed2` "runtime: accelerate T8 RGB-only alpha failures".

**Design.** The software rasteriser is the truth. Each draw is classified before it is executed; an exactly
representable class is dispatched to a Vulkan compute kernel, everything else falls back to software:

```
enum class GsRendererMode : uint8_t { Software, Hybrid, Verify, GpuStrict };
```

and the classification is *explained*: `GsFallbackReason` has 32 named values (`EmptyBounds`, `InexactBounds`,
`UnsupportedTextureFilter`, `DestinationRead`, `ResourceAlias`, `UnknownMemoryLayout`, `CostModel`, ...) and
`GsFlushReason` 15 (`Transfer`, `CpuReadback`, `FeedbackSnapshot`, `ClutHazard`, `PresentationLatch`,
`QueueBackpressure`, `ResourceHazard`, `PipelineChange`, ...). Every draw carries a `GsDrawResources` of nine
512-bit VRAM page masks (framebuffer read/write, depth read/write, texture, mip, CLUT, aggregate read/write) plus
`readsDestination` / `framebufferDepthAlias` / `framebufferTextureAlias` / `framebufferClutAlias`; a batch of
draws crosses to the GPU only when their masks do not conflict. `GsHybridBatchPolicy{minimumPixels,
maximumCommands}` defers the backend choice until a run of compatible commands is worth a submission.

`Verify` mode runs both and counts `vulkanVerificationMismatches`.

**What it depends on that we do not have.** Vulkan headers (loaded dynamically -- `PS2X_ENABLE_GS_VULKAN`, no
link-time dependency, and prebuilt SPIR-V is checked in, so no glslang); their command-stream GS owner thread;
their page-coherency state machine; their software rasteriser as the authority. Our GS is a frontend
(`gs/gs_frontend.cpp`, 2,087) over a GL backend (`gs/gs_gl_backend.cpp`, 4,062) and a CPU backend
(`gs/gs_cpu_backend.cpp`, 2,009), with `gs/gs_backend.h` a 71-line seam.

**Map onto ours, and the recommendation.**

- **The Vulkan backend: LEAVE.** ~17k lines plus 21 shaders, on a GS that diverged before #204, to replace a GL
  backend that works. The brief set the bar at "an overwhelming case" and there is none: nothing in
  `docs/KNOWN.md` section 2 says our problem is raster throughput. Our GS problems are a texture cache that
  uploads 21k times a second, a defect on the streamed full-screen image path, and a back-pressure bound -- none
  of which a second GPU API addresses.
- **`Verify` mode: ADAPT, and this is the recommendation that matters.** We already have both halves: the CPU
  backend can render the same draw the GL backend rendered, and `vu1_replay --vram-diff` already proves we know
  how to diff two VRAM images with a tolerance. A `PS2X_GS_VERIFY` mode that runs the CPU backend beside GL on a
  bounded window and reports the first differing draw would turn "second, separate GS defect on the streamed
  full-screen image path" from a believed row into a located one. Estimate 300-500 lines in `gs_frontend.cpp` +
  the seam, plus a knob row and a test. No Vulkan, no new dependency.
- **The reason enums: ADAPT, cheap.** Our `[gs-gl stats]` line reports *how much* (calls, bytes, submit/transfer/
  upload/readback ms, textures, rts) and a rich back-pressure block, but never *why*. Two `std::array<uint64_t,
  N>` counters keyed by a `GsFlushReason` / `GsUploadReason` enum, printed on the existing 60-call cadence, is
  ~150-250 lines and is the instrument the 21k-uploads row is missing. The fork's enum values are a ready-made
  vocabulary; the mechanism is three lines.
- **`GsDrawResources` page masks: ADAPT only if the reason counters do not settle it.** The nine-mask hazard
  model is elegant and is what makes their batching safe, but it is a large change to a frontend that currently
  works. Cost if pursued: 800+ lines. Judge after the reason counters have named the cause.

---

## 5. The performance HUD

**Files.** `src/perf_hud/ps2_debug_hud.cpp` (1,220 -- a separate `ps2DebugHud` executable),
`src/lib/ps2_performance_hud.cpp` (643) / `.h` (22) -- the in-runtime server,
`src/lib/ps2_performance_telemetry.cpp` (902), `include/runtime/ps2_performance_telemetry.h` (230),
`src/lib/ps2_performance_threads_linux.cpp` (206), tests
`src/perf_hud/ps2_performance_telemetry_tests.cpp` (359). Commits `e0b9d80` "Add opt-in external performance HUD"
(+3,189) and `f112d4b` "Add renderer batching diagnostics to performance HUD" (+586), the fork's last two before
the save state.

**Design.** The runtime publishes a `TelemetrySnapshot` over a private AF_UNIX socket; a separate imgui/raylib
process connects, polls, and draws. The snapshot is versioned (`kTelemetrySchemaVersion = 2`) and JSON-encoded,
and the client computes `TelemetryRates` from two consecutive snapshots.

**What it depends on that we do not have.** Everything about the transport and the process:
`<sys/socket.h>`, `<sys/un.h>`, `<spawn.h>`, `<poll.h>`, `XDG_RUNTIME_DIR`, an `lstat`+`geteuid` ownership check
on the socket directory, `/proc`-based per-thread CPU sampling (`ps2_performance_threads_linux.cpp`,
`LinuxThreadRole`/`LinuxThreadSample`), and imgui + rlImGui + raylib in the client. `ps2xRuntime/CMakeLists.txt`
line 128 makes this explicit: *"PS2X_ENABLE_PERF_HUD currently supports Linux desktop builds only"*. Our
shipping target is Windows; our Linux build is the VM (`scripts/vm_sync.sh`) and CI builds library + launcher only.

**Map onto ours, and the recommendation.**

- **The HUD process: LEAVE.** Linux-only by construction, 3.2k lines, and it would be the fourth window in a
  project whose owner plays the game and reads logs.
- **The telemetry *schema*: ADAPT, small and worthwhile.** Two ideas are portable and good. (i) **Per-presentation
  normalisation**: every rate exists twice, `xPerSecond` and `xPerPresentation` (`softwareCommandsPerPresentation`,
  `routingFlushesPerPresentation`, `vulkanGpuToCpuPagesPerPresentation`, ...). A per-second figure hides cost when
  the renderer stalls -- exactly our failure mode ("render stall reads as frozen game", and the guest clock at
  0.04 s per wall second in the CLUT incident). Adding a `/frame` column beside the `/s` column in
  `[gs-gl stats]` is a handful of lines and makes two of our recorded incidents readable at a glance.
  (ii) **Validity flags** (`routingValid`, `presentationValid`, `batchingValid`, `coherencyValid`): a rate that
  cannot be computed says so instead of printing a plausible zero. `docs/KNOWN.md` has a row about a gate that
  kept passing while four captures were silently lost; the same discipline applies.
- Estimate for both: 100-200 lines in `gs_gl_backend.cpp`'s stats block and `vu1-stats`, plus a test on the
  arithmetic. No new dependency, no new process, no new window.

---

## 6. VU1 timing and causal ordering

**Files.** `include/runtime/ps2_vu1_command_stream.h` (1,271), `src/lib/ps2_vu1_command_stream.cpp` (5,296),
`vu/ps2_vu1_core.cpp` (2,181), `vu/ps2_vu_recompiler.cpp` (6,961), `vu/ps2_vu_analysis.cpp` (2,446),
`vu/ps2_vu_ir.cpp` (1,236), `vu/ps2_vu_program_cache.cpp`, `include/runtime/ps2_vu1.h`. Design docs
`docs/threaded-vu-gs-ownership.md` (773), `docs/vu-x64-recompiler.md` (329), `docs/vu1-workload-profiling.md`
(278), `docs/vu-backends.md`, `docs/vu-ir.md`, `docs/vu-program-cache.md`, `docs/vu-native-emitter-spike.md`.
~40 commits 2026-08-13 to 2026-08-16: `25bedb9` classify VU1 owner command traffic, `9468f3e` defer VU1 requeues
across VIF1 events, `c696ec2` extend late VU1 speculation without replay, `d4382ba`/`81281c3` coalesce and batch
VIF1 owner rendezvous, `a49512f` execute VU1 through exact checkpoint epochs, `823db0b` defer early coarse VU1
publication, `08b8a3f` harden coarse VU1 causal ordering, `0255a86`/`b647346` gate owner notifications.

**Design.** VU1 is a separate owner thread fed by a typed command stream (`Vu1DecodedUnpackCommand`,
`Vu1MscalCommand`, `Vu1InvocationCommand`, `Vu1AdvanceSliceCommand`, `Vu1BarrierCommand`, ...) with a
speculation model (`Vu1SpeculationStatistics`, `Vu1SpeculationResolution`) and two timing policies: "exact"
slices as the architectural oracle, and a bounded "coarse" mode that keeps one whole VU activation private to the
owner under cycle and PATH1 limits. The publication rule is stated in
`docs/threaded-vu-gs-ownership.md`: *"It does not authorize a worker to publish guest state according to host
completion time."* Access classes FF / OM / GO / DO / LC with a required treatment for each.

Separately, `docs/vu1-workload-profiling.md` describes a bounded JSON profiler grouping invocations by (reset
epoch, FNV-1a hash of the whole VU code memory, entry PC), with opcode histograms and, notably, whether an MPG
upload's bytes *were already identical at the destination*.

**How it is judged against ours.** `docs/STATUS.md` (2026-09-09 entries, Sprints 1-3): our VU1 has a
cycle-exact path, a fast path (100 -> 18 ns/cycle), a microcode recompiler, and a hand-written/generated native
program table dispatched by FNV program hash -- 162 of 166 programs native, `[vu1-stats]` showing 3-9k
native-ended/s in gameplay, with `vu1_replay --verify/--no-native/--vram-diff` as the oracle and per-fixture
goldens in CI. We are not throughput-bound in VU1 and we are not correctness-blind in VU1.

The fork's work solves a different problem: a *general* recompiler that must run any title's VU1 fast without a
per-title native table. Its speculation and causal-ordering machinery is the price of not having what we have.

**Recommendation: LEAVE the owner thread, the speculation, the epochs and the x64 JIT.** One small ADAPT:
the profiler's **"the uploaded bytes were already identical at the destination"** counter. Our dispatcher keys on
the program hash; a count of redundant MPG uploads is a cheap line in `ps2_vif1_interpreter.cpp` and would say
whether the 4 remaining non-native programs are re-uploads of programs we already have. ~40 lines. And one idea
worth reading rather than taking: the FF/OM/GO/DO/LC access-class table in `docs/threaded-vu-gs-ownership.md` is
the best short statement of the publication rule we have a recorded incident for -- worth linking from our own
notes when the GL back-pressure work resumes.

---

## 7. EE fiber-scheduler tracing

**Files.** `src/lib/ee_thread_scheduler.cpp` (1,673) / `include/runtime/ee_thread_scheduler.h` (532),
`ee_runtime_executor.cpp` (1,274), `ee_scheduler_executor.cpp` (436), `ee_execution_backend.cpp` (737),
`boost_ee_fiber.cpp` (681), `ee_event_scheduler.cpp` (290), `ee_counters.cpp` (912), `ee_cache.cpp` (416);
docs `docs/ee-execution-backends.md` (96), `docs/ee-event-scheduling.md` (182),
`docs/ee-generated-code-benchmark.md`, `docs/ee-random-retirement-benchmark.md`. Commits `648df345` migrate EE
execution to fibers, `66c038ee` pin Boost.Context, `42773d76` trace deterministic EE transitions, `967815f`
expose EE scheduler diagnostic counters, `73225c3`/`90ea6ee`/`de782b7`/`a1ba920` typed owner-local transitions,
`88951df2` measure scheduler compatibility in shadow mode, `306a69dd` complete Phase 3 backend differential.

**Design.** Two selectable backends -- `legacy-host-thread` (one host thread per guest thread) and
`legacy-cpp-fiber` (one executor, Boost.Context `fcontext` continuations) -- chosen by
`PS2X_EE_EXECUTION_BACKEND`, with a `PS2X_EE_CONTEXT_BUILD_MODE` that makes the contract explicit
(`production-fcontext` / `host-fallback` / `sanitizer-no-fcontext`) and *fails configuration* rather than
silently falling back. Diagnostics are counters (`owner_local_transitions_applied`, publications queued vs
applied) plus a rolling FNV hash of the accepted rotation sequence
(`kEeThreadDiagnosticRotationSequenceHashSeed`), served over their debug server.

**Map onto ours.** We already run every guest thread on one executor thread
(`ee_scheduler.h:403 onExecutorThread()`), so the fiber backend would buy us nothing we do not have; and it
would add Boost 1.91.0 as a configure-time FetchContent (a ~120 MB archive) to a build the owner already finds
slow. Our tracing is *ahead* for our purpose: `Kernel/SchedTrace.{h,cpp}` (374 lines, R2xx music work, 2026-09-21)
prints per-switch `out=/ran_ms=/waited_ms=/left=<why>/in=/prio=/pc=/ready=` lines, ready/invoke/run/idle/pace
lines, and per-stub timing wrapped onto the function table with zero cost when the knob is off. It is what found
the MPEG picture-count gate. The fork prints no such thing -- its diagnostics are about proving the scheduler's
own transitions correct, not about diagnosing what the guest did.

**Recommendation: LEAVE the fiber backend and the transition protocol. ADAPT one idea: shadow-mode
differential.** `88951df2` "measure scheduler compatibility in shadow mode" and the rolling rotation-sequence
hash together describe how to land a scheduler or state change safely: run the new path beside the old, hash the
decision sequence, compare, and only then switch. That is precisely the instrument the reverted `955539c` lacked
-- the KNOWN row's own conclusion is "one group of state at a time, each with a gate", and a sequence hash is a
cheaper gate than a 3/3 mission run. Estimate: a rolling FNV over `(tid, reason, prio)` at the switch site plus a
printed digest, ~60-100 lines, usable by the section 3 work.

---

## 8. Anything else that touches an open `docs/KNOWN.md` section 2 row

The fork carries 64 `fix(...)` commits, most from its first week (2026-07-23 to 2026-07-28), in areas both trees
still share. Four were checked against our tree by reading our source; three are defects we still carry.

| Fork commit | What it fixes | Our tree today |
|---|---|---|
| `3e2ea9f4` fix(recomp): preserve MOVZ and MOVN upper lanes | R5900 conditional moves write the low 64-bit lane; upstream emitted `SET_GPR_VEC`, clobbering the upper 64 bits | **still wrong** -- `ps2xRecomp/src/lib/special_translator.cpp:123-126` |
| `60d14c43` fix(recompiler): compare signed branches as 64-bit values | BLEZ/BLEZL/BGTZ/BGTZL and REGIMM BLTZ/BGEZ(AL)(L) compared `GPR_S32` | **still wrong** -- `ps2xRecomp/src/lib/control_flow_emitter.cpp:411-416` |
| `78ce1a21` fix(vu): saturate FTOI conversions | `_mm_cvttps_epi32` returns `0x80000000` on overflow; the VU saturates | **still wrong** -- `ps2xRecomp/src/lib/vu_translation_helpers.cpp:761`; no `Ps2VuFtoi` in our `ps2_runtime_macros.h` |
| `1a92945d` / `d07a5117` / `34fab651` PMULT{W,UW,H} product lanes | the open-coded `_mm_mul_epu32` accumulation loses lanes and HI/LO | **still open-coded** -- `mmi_translation_helpers.cpp:334`; worth the same check |

The two-line shape of the first, for reference (the only fork code quoted in this note):

```
- if (GPR_U64(ctx, {}) == 0) SET_GPR_VEC(ctx, {}, GPR_VEC(ctx, {}));
+ if (GPR_U64(ctx, {}) == 0) SET_GPR_U64(ctx, {}, GPR_U64(ctx, {}));
```

**Recommendation: TAKE, with a gate.** Each is a few lines in a generator plus a `code_generator_tests.cpp` case,
in files our own divergence barely touched. The cost is not the edit -- it is that changing recompiler output
means a full `./build.sh recomp` + `runtime` (~21 min) and a 3/3 gate on a game that currently works, because
"more correct" is not the same as "same behaviour". Sequence them one at a time. The remaining ~25 EE/VU/DMAC/MPEG
`fix(...)` commits deserve the same spot-check pass; this note checked four.

**Two GS rows worth a lead, not yet a take.**

- `88d2f33a` "Fix GS interlaced scanout geometry" divides DH by MAGV+1 and drops the hard 640x512 presentation
  clamp. Our `gs/gs_gl_backend.cpp:252-267` and `gs/gs_cpu_backend.cpp:352` decode MAGH and **ignore MAGV**, and
  clamp to `kHostFrameWidth`/`kHostFrameHeight`. For SOCOM II's NTSC interlaced mode MAGV is expected to be 0, so
  this probably changes nothing -- but *if* it changes the presented geometry it invalidates every reference image
  in `scripts/parity/refs/`. Do not take it blind: read the game's DISPLAY writes first (a one-line trace), and
  only then decide. This is also the most plausible lead on the open row "the console draws the online screens
  ~7% narrower than ours, centred": the console honours DW/MAGH, we clamp to a fixed 640.
- `51fb23c2` "fix(gs): match Sony libgraph display environments" rewrites `GsPutDispEnv`'s default environment
  (PMODE circuit selection, SMODE2 from the interlace/ffmode params). Relevant only if SOCOM II uses libgraph's
  default env rather than writing the registers itself; check before spending anything on it.

Nothing in the fork addresses our other open rows: the Bluetooth endpoint dropouts, the 989snd banks, the
virgin-memory-card first save, the glyph atlas, the online round clock, or the launcher. Its audio work
(`ps2_989snd.cpp`, 1,641 lines; `47255e57` render 989snd SBlk sound effects, `17b6a48c` model missing 989snd
command semantics, `88bb21ca` read Sony streaming payloads from IOP RAM) is a from-scratch model and is behind
ours, which is built on the Ziemas decompilation (`docs/research/36`) -- LEAVE.

---

## 9. Licence

Both trees are GPL-3.0-only; the fork's `LICENSE` is the GNU GPL and `THIRD_PARTY_NOTICES.md`'s ps2recomp row
already covers our side. Taking code from the fork is a GPL-3.0 -> GPL-3.0 move: no compatibility question, but
the fork's author (MrCoolTheCucumber) must be added to the ps2recomp row's copyright-holder list for anything
taken, and the fork's commit ids cited in the commit message.

Third-party code vendored or fetched inside the fork, and whether it rides along:

| Component | How | Licence | Rides along with |
|---|---|---|---|
| Xbyak 7.37 (`docs/third-party/xbyak.txt`, `FetchContent` from herumi/xbyak, pin `431abd86`) | configure-time fetch, linked into `ps2_runtime` | BSD-3-Clause | only the VU x64 JIT (`vu/ps2_vu_recompiler.cpp`) -- **not taken** |
| Boost 1.91.0, `context` only (`FetchContent`, exact release archive, `cmake/BoostContextReleaseArchive.cmake`) | configure-time fetch | BSL-1.0 | only `legacy-cpp-fiber` -- **not taken** |
| Dear ImGui + rlImGui + raylib | HUD client only | MIT / MIT / zlib | only `ps2DebugHud` -- **not taken** |
| Vulkan headers | `find_path(vulkan/vulkan.h)`, dynamic loading, no link dependency | Apache-2.0 / MIT | only the Vulkan backend -- **not taken** |
| SPIR-V `_spv.inc` blobs in `src/lib/shaders/` | checked in, generated from the fork's own `.comp` sources | GPL-3.0 (the fork's own) | only the Vulkan backend -- **not taken** |
| sse2neon | as upstream | MIT | already in our notices |

**Every piece this note recommends taking or adapting -- the save-state container, the `*RuntimeState` pattern,
the reason counters, per-presentation rates, `Verify` mode, the recompiler fixes -- carries no third-party
dependency at all.** They are GPL-3.0 fork code or pure ideas. No new row in `THIRD_PARTY_NOTICES.md` is needed
beyond crediting the fork's author on the existing ps2recomp row.

---

## 10. What to do, in order

1. The three recompiler fixes (section 8), one at a time, each with its generator test and a gate. Smallest,
   most certain, ~40 lines total.
2. The reason counters and the `/frame` column on `[gs-gl stats]` (sections 4 and 5). ~250-450 lines; aims
   directly at the 21k-uploads row.
3. The `*RuntimeState` pattern applied to the CD / IOP-heap / MPEG / audio groups (section 3), with the
   shadow-hash gate from section 7. 600-1,200 lines; closes a proven-open item.
4. `PS2X_GS_VERIFY` -- the CPU backend as a per-draw oracle for the GL backend (section 4). 300-500 lines; aims
   at the streamed full-screen image defect.
5. The save-state container, if and when something needs to serialise deterministically (section 2). ~680 lines,
   no dependencies, no urgency.

Everything else in the fork: read, admire the discipline of the commit sequences, and leave it where it is.
