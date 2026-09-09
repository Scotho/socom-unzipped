# Project status — updated 2026-09-09 07:30

## 2026-09-09 07:30 (local) — scheduler fast paths, direct XGKICK submit, VU0 fast path: mission gameplay 28.7 frames/s (best 30 s: 31)
Fresh game-thread stack profile after the GS spans (run gtprof_2): startXgkick 9% in memcpy (the
kicked packet was copied VU memory -> kick buffer -> arbiter), processPendingEvents 6% in mutex
calls on every checkpoint return, selectReady 4% self (128 empty priority deques scanned on every
idle wake), VU0 micro programs 4.5% (still the cycle-exact scheduler), GS front end ~12%
(GSGlBackend record/Cmd growth, main's file). Fixes (commit below): the immediate XGKICK path
walks the GIFtags in VU memory and submits the packet from there (the arbiter's copy is the only
one; the copying paths remain for wrapping/overrunning packets), processPendingEvents clears the
checkpoint request without the event mutex when nothing is posted (atomic event count) and no
deadline is due, selectReady returns at once when the ready count is zero, and VU0 micro programs
use the fast path too (`PS2X_VU0_FAST=0` restores the exact scheduler; the semantics are the same
code that is golden-verified on VU1). The mission program was regenerated with the newest
hand-back pcs added to logs/vu1_seeds_mission.txt (900-dump golden green, FMAC check clean).

**Result** (run_20260909_07xx sched2_1, sheet identical): gameplay phase **28.7 syncv/s over the
last 60 s, 31.0 in the best 30 s**, 7.0 ns/cycle, 69 M VU1 cycles/s, 2.4 M VU1 cycles/frame,
hand-backs 33/s (0x3828 now the top one). Progression today: 3 -> 10 -> 13 -> 19 -> 22 -> 29.
GSMem::ReadSpan (row-span texture reads, mirror of WriteSpan) is in for the GL backend's
decodeTexture (per-pixel ReadCT32 today, 14% of the GL thread; main's file).

**07:50 addendum.** GifArbiter::submit now processes a packet straight from the caller's buffer
when its queue is empty (order-preserving: nothing but other submissions happens between a submit
and the drain), which removes the per-XGKICK memcpy (run arb_1: 26-28 frames/s, sheet identical).
The title screen and main menu run the mission VU1 image with entry pc 0 (150 dumps at the title,
all hash 638cb8f0), so the recompiler already covers them (`interp-programs/s=0` at the title);
the title itself runs at ~30 syncv/s with the game thread at 100% and VU1 at 2 ms/s — the menu
movie decode/upload path, not VU1, if that ever matters. Online lobby image: dump in progress.

## 2026-09-09 06:20 (local) — VU1 program regenerated from 900 dumps (300 gameplay): hand-backs 850 -> 32/s, mission gameplay 22-29 frames/s
The in-game `[vu1-bail]` histogram showed the generated code handing ~1100 programs/s to the
interpreter at computed-jump targets (command handlers) the 300 intro-window dumps never
reached (0x1c30, then 0x1c70/0x1a78 one hop further). 300 gameplay programs were dumped with
`PS2X_VU1_DUMP=logs/vu1dump4:300 PS2X_VU1_DUMP_AFTER=220`, their exact-interpreter golden
recorded (logs/vu1golden/d4, 1.1 M cycles), and the program regenerated from all 900 dumps plus
the bail pcs (`vu1_replay --gen --seeds logs/vu1_seeds_mission.txt`). The generated code equals
the exact interpreter on all 900 programs (d2/d3/d4 diff 0, FMAC check clean); the gameplay
dumps run at 6.9 ns/cycle offline. In the mission (run_20260909_053430-ish seeds_2, sheet
identical): hand-backs 32/s, 5.9-10.7 ns/cycle, VU1 host 430-480 ms/s incl. GS work, and
**syncv/s 21.8 over the last 60 s, 29.0 in the best 30 s phase** (2.5-3.1 M VU1 cycles/frame).
Remaining hand-back pc 0x3d18 (4211 in the run) is next in the seeds. PS2X_HOST_PROF_MAIN=1
samples the main/GL thread (it uses a full core: next profile target).

## 2026-09-09 05:30 (local) — stage 3: host stack profiler; scheduler clock batching; row-span GS uploads + pooled arbiter -> mission gameplay 12.7 -> 19 frames/s
**Measuring.** `PS2X_HOST_PROF=1` now writes module names for external addresses and runs its
sampler at time-critical priority (the old sampler under-sampled compute and blamed `_setmode`);
`PS2X_HOST_PROF_STACKS=1` unwinds the x64 call stack of every sample (RtlVirtualUnwind) and
`tools_py/hostprof_stacks.py` prints inclusive shares, the exe callers of DLL time and folded
stacks. `[vu1-stats]` prints `thread=`/`proc=` CPU ms/s, `interp-programs/s` (images without
generated code, named once as `[vu1] program image <hash> ... has no generated code`),
`handbacks/s`, and with `PS2X_VU1_BAILHIST=1` the top hand-back pcs (`[vu1-bail]`);
`tools_py/vu1stats_summary.py <log>` summarizes a run by 30 s phase with VU1 cycles per frame.
Frame rate = `syncv/s` (sceGsSyncV, one per presented frame; the game never calls
sceGsSwapDBuff). The game thread is 100% of one core; the process uses ~2 cores (GL thread).

**Profile of the game thread in the mission (run_20260909_043923, stacks).** Inclusive:
EeScheduler::accountCycles 21% (13% inside ntdll: a QueryPerformanceCounter on every recompiled
checkpoint), GS::processGIFPacket 15.5% (GSCpuBackend::UploadImage 9.2% = a std::function call per
pixel into GSMem::WriteP8/P4/CT32; GSGlBackend::record copies 3%; vector<GSGlBackend::Cmd> growth
2.2%), processDueDeadlines 4.6% (mutex + clock per call), dispatchIrq 3.4% (std::getenv per IRQ),
VU1 generated code ~9%, VU1 interpreter ~12% (hand-backs, see below), recompiled EE code ~3%.

**Fixes (commits 9b4212b, 5ef9c5b).** accountCycles converts the host clock once per 5000
estimated guest cycles (~17 us; waitForEvent forces a conversion); processDueDeadlines returns
before m_nextDeadlineCycle without locking; dispatchIrq caches its trace switch; publishSnapshot
(a138ad3) publishes at most every 50 ms of guest time. GSMem::WriteSpan writes host-to-local
transfers in row spans (same PixelStorageTraits<psm>::Write per pixel, inlined, no std::function;
the per-pixel path stays for formats without a span writer) and GifArbiter reuses its packet
slots/buffers. Sheets sched_1 and gsup_1 are identical to vu1gen_1 (title labels, briefing
textures, cinematics, HUD).

**Result.** Gameplay phase of the mission (HUD on screen, ~2.9 M VU1 cycles per frame):
run_20260909_051059 **19.0 syncv/s** at 10 ns/cycle (56 M VU1 cycles/s, VU1 host 560 ms/s incl.
the GS work done inside XGKICK) vs 12.7 before the scheduler/GS changes (the scheduler-only run
sched_1 measured 11.7 in a heavier phase — the phases do not align run to run; compare the
gameplay phase and cycles/frame). Menus 55-57/s.

**Open.** The generated VU1 code hands ~1100 programs/s back to the interpreter at computed-jump
targets the 300 dumps never reached (0x1c30: 200k, 0x1e50: 28k, 0x1d80, 0x1d30, 0x1d90, 0x3d10 ...):
those pcs are now generator seeds (logs/vu1_seeds_mission.txt, `vu1_replay --gen --seeds`) and a
gameplay dump (PS2X_VU1_DUMP_AFTER) is being taken for a second golden. Still in gs_gl_backend.cpp
(main's file, pending its commit): pooled record/Cmd buffers (~5%). Then: what the other core does
(the GL thread is at 100%: decode/upload on the render thread may be the next wall), and the VU1
register file in host registers.

## 2026-09-09 04:05 (local) — VU1 microcode recompiler ("known programs"): 18 -> 12 ns/cycle in the mission, frame rate 10 -> 13 per second; the other 35 ms/frame is now outside VU1
**What landed (commit 6dcf73d, default on; `PS2X_VU1_GEN=0` disables).** `vu1_replay --gen`
turns a dumped 16 KB VU1 code image into one goto-threaded C++ function
(src/lib/vu/generated/vu1_d418194495c25213.cpp for the mission image, md5 638cb8f0, all 300
dumped programs) registered in vu1_known_programs.cpp; the interpreter hashes VU1 code memory
(FNV-1a, only when the VIF MPG generation changes) and runs the matching function. The generated
code is a static unrolling of the fast path with constant register indices and the same shared
SSE FMAC helpers (ps2_vu1_ops.h): flag ring / Q / P timing kept exactly (commits deferred to
readers, loop heads and every 16 pushes on a 64-entry ring), same-pair shadow rule, delay slots
(also a branch inside a delay slot), E-bit end, and a hand-back to the interpreter with
m_state.pc set for anything unsupported (cycle budget, computed-jump targets not seen in the
profile, D/T bits). A dataflow pass over the image (per-lane "pairs since the last write" slack,
"lane holds a normalized value") removes the ready checks and operand normalizations that cannot
matter (1400 -> 62 VF ready checks in the mission image); the MADD/MSUB flag classification has a
proved-exact float fast path (double/long double only near zero, overflow or cancellation; proof
in ps2_vu1_ops.h); ACC stays in a host register across pairs; XGKICK copies whole GIFtag
payloads. Tooling: `--pchist`/`--bailhist`/dispatch counters, `-g1` on the generated file so
`--prof` maps to pairs (scratch script genprof), `[vu1-stats]` now prints `flips/s`
(sceGsSwapDBuff — SOCOM II never calls it) and `syncv/s` (sceGsSyncV = one wait per presented
frame: the frame-rate number).

**Verification.** Offline: identical to the exact interpreter on all 300 dumps (packets,
registers, flags, cycle counts), 0 hand-backs, `PS2X_VU1_FMAC_CHECK=1` clean; 10.0 ns/cycle vs
21.4 (fast interpreter) and 92 (exact) in the same tool. In-game (same build, mission phase,
last 60 s of each run): generated `[vu1-stats]` 45.1 M cycles/s at 12.1 ns/cycle, 27.9k
programs/s, host 546 ms/s, **syncv/s 12.7** (run_20260909_034405, sheet vu1gen_1: title clean,
intro clean, gameplay HUD at s33); `PS2X_VU1_GEN=0` baseline 32.9 M cycles/s at 18.5 ns/cycle,
21.6k programs/s, host 605 ms/s, **syncv/s 10.2** (run_20260909_035139). Menus run at 50-57
syncv/s in both. Yesterday's exact interpreter: 6.9 M cycles/s at 100 ns/cycle.

**Where the time goes now.** The mission issues ~3.3-3.5 M VU1 cycles per presented frame
(~2100 programs), so at 12 ns/cycle VU1 costs ~42 ms/frame and the rest of the runtime (EE
recompiled code, VIF/DMA, GS front end on the game thread) ~35 ms/frame: frame time ~77 ms.
Even a 4 ns/cycle VU1 (14 ms) leaves ~50 ms/frame -> 20 fps, so the next step for frame rate is
a `PS2X_HOST_PROF` profile of the mission with this build to find the non-VU1 hot spots (the
earlier profile, STATUS 2026-09-08 17:30, was taken when VU1 was 70% of the time). VU1 itself:
the generated code's remaining cost is the FMAC flag build/push (~40% of its time), startXgkick
(~5%), fastCommit (~3%); the register file still lives in memory (store-forwarding latency on
dependent pairs), which a per-block register allocator could remove.

**Caveats.** Only the mission image is recompiled; the title/UI and online images run on the
fast interpreter until dumped (`PS2X_VU1_DUMP` at those screens, then `vu1_replay --gen` and a
line in vu1_known_programs.cpp). The generator's DIV/SQRT/RSQRT skip the PS2X_FPU_TRAP
diagnostics. Regenerating needs a bootstrap when the helper signatures change (scratch
regen.sh: remove the generated file and its table entry, build vu1_replay, --gen, restore,
build).

## 2026-09-09 02:40 (local) — VU1 fast path: 100 -> 18 ns/cycle in the mission (5.4x VU1 throughput), default on; the run reaches gameplay with the HUD
The cycle-exact VU1 scheduler (per-instruction ready scan, pending-write queues, long double FMAC
flags) is replaced by a non-cycle-exact fast path (commit 773991c, default on since this entry;
`PS2X_VU1_FAST=0` restores the exact path, a VU trace forces it):
- VF/VI/ACC writes and stores land immediately. Every VF write in the model has the same 4-cycle
  latency and every read stalls on the register, so immediate writes give the same values; the
  same-pair rule (the lower reads the old value of the upper's destination, the upper wins a
  write to the same register) and the one-instruction VI branch bypass are kept.
- The cycle counter still advances by the modeled stalls (per-lane VF and VI ready cycles, Q/P
  and EFU resources, WAITQ/WAITP), so MAC/STATUS/CLIP flags (8-entry ring in issue order,
  +4 cycles), Q (+7/+13) and P land at exactly the cycles the exact path shows them — the
  game's FMAND backface test and FCAND clip tests see the same flags. E-bit, branch delay,
  D/T halts, XGKICK at kick time, the 65536-cycle budget and the flush at program end are
  unchanged.
- FMAC lanes run on SSE2 for the four lanes together. The Z/S/U/O classification comes from the
  chop-rounded float (single ops) or double (product-sum: the float product is exact in double)
  result and drops to the long double computation only when a result lands exactly on FLT_MAX;
  proof sketch in ps2_vu1_upper.cpp (a single chop-rounded op has |r| <= |exact| < |r| + ulp), so
  the flags and stored values are bit-identical to the old long double path. `PS2X_VU1_FMAC_CHECK=1`
  cross-checks every FMAC against that path (0 differences over the 300 dumps). applyDest and the
  vf0 reset store 16 bytes (scalar lane stores followed by the FMAC's vector load stalled store
  forwarding); normalizeOperand/microAddressMask/fastReadyCycle inlined; the decoded-code cache is
  validated once per program instead of per pair.

**Verification.** `dist/vu1_replay.exe --batch <dir> <dumps>` writes a golden per dump (packet
bytes + FNV hash, cycle count, end pc, MAC/STATUS/CLIP/R/Q/P/I, all VI/VF/ACC, VU data memory
hash). The fast path equals the exact interpreter on all 300 dumped mission programs
(logs/vu1dump2 + logs/vu1dump3: 287k cycles, 274k pairs, 118 programs with packets) in every
field, including cycle counts. Timing with `--repeat 100` (`--prof` samples the host pc): exact
92 ns/cycle (same tool; the tool now runs programs from PS2Memory's VU1 buffers so the decoded
cache applies), fast 21.4 ns/cycle. In the mission (logs/run_20260909_021205.log, run
vu1fast_1, sheet logs/parity/vu1fast_1_sheet.png): `[vu1-stats]` 34-37 M cycles/s at 17.7-19.1
ns/cycle, 21-23k programs/s, vs 6.5-8.2 M cycles/s at 93-103 ns/cycle, 6.5-8.7k programs/s in the
last stats run (run_20260908_171207). The host still spends ~650 ms/s in VU1: the game is VU1-
bound and simply runs ~3x more frames (programs/s), so the next speed step is still VU1 (a
block recompiler to host; the interpreter's remaining cost is the per-pair dispatch, the
Windows-ABI xmm save/restore of execUpper and the ready-cycle scan). Screens: title labels clean
(s05/s06), mission loads, the intro cinematics play (s21-s27, no giant polygons), and for the
first time the 420 s run reaches gameplay with the HUD (s34-s37, "RENDEZVOUS WITH MALLARD",
squad status, help popup); same 16 pre-existing guest faults as before; no hang with the VIF1
i-bit stall (16af5ad).

**Not done / caveats.** ps2x_tests does not link on this toolchain (pre-existing: bad
`--stack` link option, then unresolved runner symbols ps2HostProfStart, ps2_stubs::sceVibGetProfile,
socom2_RsaGenerateKeyPair, scePad2GetState), so the VU unit tests were not run; the 300-dump
golden and the FMAC check stand in. The fast path is VU1 only (VU0 micro programs keep the exact
scheduler; they are tiny). The exact path's behaviour of reading the previous I register in an
I-bit pair's upper instruction is preserved (not re-examined). No frame counter exists in the
log; frame rate is inferred from programs/s (~3x) — add a flips/s line to PS2X_VU_STATS next.

## 2026-09-09 02:15 (local) — TITLE LABELS FIXED: VIF1 i-bit stall + prompt IRQ delivery; the console never stops the menu movie (that lead was built on the wrong savestate)
The garbled LOAD GAME / NEW GAME / ONLINE labels are gone: logs/parity/title_stall5_sheet.png
holds 24 main-menu captures over 2+ minutes, all clean (before: logs/parity/title_trace7_sheet.png,
garbled from s10 on). Root cause, established with a PCSX2 GS dump of the real main menu
(savestate slot 21; slot 6 — the "title" image every 03:20 conclusion was built on — is the
SELECT RANK dialog, so "the console has no movie set at the title" was never a valid comparison;
the user confirmed the menu movie is correct and must stay):
- Console per-frame GS order (tools_py/gsdump_timeline.py on tools/pcsx2/snaps/*.gs, captured by
  tools_py/parity/gsdump_capture.py --slot 21): 512x256 background upload -> background sprite ->
  the 11 label textures (set [11], 0x3107..0x3387) -> label draws. Ours (tools_py/gif_submit_timeline.py
  on a PS2X_GIF_TRACE run, which now also prints TEX0 binds): set [11] flush -> background upload
  (to 0x2bc0 every other frame, overlapping the label pages) -> label draws. One step out of phase,
  so the labels were drawn from the background's pixels every other frame.
- The game sequences texture-set uploads against its draw stream with a marker protocol: each
  set flush appends an entry to the render queue at 0x4887c0 (FUN_0033bf30/be70/bd90) and emits
  [FLUSH][DIRECT 1qw][FLUSHA][NOP with the VIF i-bit] into the VIF1 MFIFO ring. VIF1 stalls at the
  i-bit code and raises INTC5; the handler FUN_0033c010 kicks the GIF chain of entry[index++]
  (PATH3 upload), re-bases sets (FUN_00355de0) and writes FBRST.STC to release VIF1. FUN_00339de0
  (frame begin) resets the index. Two runtime defects broke the mapping between markers and entries:
  1. VIF1 never stalled on an i-bit VIFcode (it raised INTC5 and carried on), so the next segment's
     draws ran before the handler kicked their uploads. Fixed: ps2_vif1_interpreter.cpp holds the rest
     of the stream after an i-bit code (STAT.VIS|INT) until FBRST.STC (ps2xVif1StallCancel resumes it);
     PS2X_VIF1_NO_IRQ_STALL=1 restores the old behaviour for A/B.
  2. The 7th (last) marker of a frame is committed to the ring by FUN_00350ab0 with a BYTE store to
     D8_CHCR (0x1000d001); only PS2Runtime::Store32 drained pending INTC causes, so that interrupt
     was delivered at the next 32-bit MMIO store — inside FUN_00339de0, after it had reset the index —
     and every chain of the new frame was kicked one marker early (the label set before the
     background instead of after it). Fixed: Store8/16/64/128 drain completed DMAC/INTC causes too.
  Evidence: tools_py/marker_timeline.py merges FrameBegin/AppendFlush/Vif1Irq call traces, stalls,
  STC, GIF kicks and submissions (run logs/run_20260909_020018.log = before, 020640 = after).
- Also landed: scripts/parity/title_menu.txt reaches the main menu by screen state
  (drive.py `untilref(<png>)` presses CROSS until the frame matches ref_main_menu_ours.png, then
  holds) — boot drift made fixed press counts land on SELECT RANK in 2 of 3 runs.
Not re-verified in this step (the VU1 agent's mission run is next and covers it): the mission
load and online screens with the i-bit stall. If a run ever hangs with VIF1 stalled, the game
did not STC — A/B with PS2X_VIF1_NO_IRQ_STALL=1 and report.

## 2026-09-09 03:20 (local) — title labels (user report 01:50): the label VRAM pages are overwritten by a 512x256 upload from the menu-movie texture set; the console never runs that set at the title
The garbled LOAD GAME / NEW GAME / ONLINE labels are NOT a rounding or GS-decode fault any
more: the label images the EE uploads (128x32 CT32 at blocks 0x3207/0x3247/0x3287 = pages
0x190/0x192/0x194, texture set [11] base 0x2fcc) decode cleanly (PS2X_GS_DUMP_TEX). New
diagnostics `PS2X_GS_TRACE_PAGES=0x190:6` (every upload/copy/refresh/download/draw/decode on
those pages) and `PS2X_GIF_TRACE` (each GIF submission with path, PATH3 mask, GIFtag and
BITBLTBUF) show a PATH3 upload of a 512x256 CT32 image to block 0x2bc0 (pages 0x15e..0x19d,
covering the label pages) every third frame; the label textures are decoded right after it
and hold background pixels until the next label upload. The packet is built by the
texture-set flusher FUN_00356e90 -> FUN_00356d20 (CNT 6 qwords + IMAGE 0x7fff + REF) for a
set object (class vtable 0x6f0330) with base 0x2bc0 / limit 0x33d8 living at 0x7abcc0 on
ours; its image source is the 512x256 double buffer 0x15493b0/0x15c93b0 (stale logo bitmap in
it). PCSX2's title memory (new savestate slot 6 = title; `tools_py/parity/p2s_extract.py`
pulls eeMemory/Scratchpad out of a .p2s) has the same 16 texture-set managers as ours (all
equal, labels in set [11] at the same addresses) but NO set with base 0x2bc0/limit 0x33d8 and
no packet uploading to 0x2bc0 anywhere (main RAM or scratchpad), and its title background is
static for 90 s (captures 6 s apart differ only in the roller box). Both sides hold the dlgMenu
element with `run/movies/common/menuloop.pss`; on ours a live movie element exists (object at
0x7ab940.., "ui/assetlib/uisk..") streaming MENULOOP (sceCdStRead every frame) and pushing
frames through that overlapping set — the set is meant to be used only while the shell set
[11] is not (they overlap in VRAM by design). The CPU backend renders the labels clean only
because the timing of the interleaved uploads differs (title_cpu4); GL runs with extra render
work (title_gl4, texture dumps) were clean for the same reason. In progress (title_trace5):
PS2X_MPEG_TRACE/PIC_TRACE lifecycle at the title to see why our menu movie starts when the
console's does not (candidates: sceMpegIsEnd/GetPicture semantics after the intro skip, or the
attract-mode idle timer). Fix direction: make the menu movie behave like the console (not
running at the title) — not a GS/arbiter change.

## 2026-09-09 01:30 (local) — ground height: the collision probe is IDENTICAL to PCSX2's; the actor rests at a different height above the same hit
With the new tracer (`PS2X_CALL_TRACE_DUMP="GroundQuery:a1:16,GroundQuery:a1+0x48*:16"`,
run mission_s19) every GroundQuery (FUN_002d49c0) prints its ray and hit records. The player's
vertical probe at (939.24, 832.6) returns ONE hit at y = -146.371, normal (0.070, 0.997, 0.021)
— exactly PCSX2's (polled live over PINE at savestate 8 with the new
tools_py/parity/probe_poll.py: -146.37, (0.0698, 0.9973, 0.0212)). So terrain, collision grid
and the probe math agree; the 5.5-unit difference is how far the actor rests ABOVE the hit:
PCSX2 20.11 (y = -126.264), ours 14.69 (y = -131.68). At spawn ours is placed at -125.97 (the
console value), drops to -135.9 and settles at -131.7 (s16 peek rows), PCSX2 never drops.
Structures: the player actor (class vtable 0x6691a0, PCSX2 spawn image 0x1713ce0) points at
+0xc0 to its mover (vtable 0x6694b0, 0x170d510) whose +0x90 is the position; the static records
0x416050/0x4160b0/0x416110/0x416170 are four horizontal segment probes cast from that position
(FUN_0029bf70) and never hit on PCSX2 — they do not set the height. The per-frame vertical
GroundQuery via FUN_0031dfd0 only feeds the surface material (+0x2c0 of the actor's +0xb4
object). The height therefore comes from the mover's own gravity/step logic or an animation
root offset. In progress: run mission_s21 dumps RDRAM at rest (400 s and at GroundQuery #350)
to diff the mover object against PCSX2's (candidate fields: +0x88/+0xf8 = 25.0, +0xf0 = 60,
+0x54.. = (4, 3, 6.33)). Gotcha: the camera's follow pointer (*0x488de8+0xbc) is null in the
spawn images; find the actor through the vtable scan instead. spawn_ours3.rdram (s18, 318 s)
was taken before the spawn (boot drift) and holds the post-load position (935.6, -120.0, 834.4),
identical to PCSX2's post-load record.
Update 02:10: mission_s21's 400 s image (logs/parity/rest_ours.rdram) holds the player at rest
(939.24, -131.73, 831.95); the player's actor is the one whose mover has vtable 0x6694b0 (AI
actors' movers use 0x6693f0). Diff against PCSX2's spawn image (scratch moverdiff.py: actor
0x1a5e4b0/mover 0x1785ee0 vs 0x1713ce0/0x170d510): mover +0x5c = 4.0 (PCSX2 6.3338, with
+0x54/+0x58 = 4.0/3.0 on both), +0x70..+0x7c = (-12.43, -39.13, -10.48, -14.29) vs (-11.86,
-41.58, -5.99, -12.96); actor +0x10 state word 0x00080502 vs 0x2, actor +0x24/+0xb8 = 856.39 vs
857.07 (a second position copy with y = 856?), actor +0x2bc..+0x2c4 = (939.24, -145.875, 856.39)
on ours vs zeros on PCSX2 (a cached ground point: -145.875 vs the probe's -146.371). No
constant 6.3338 in the decomp (computed). Parked here: the next step is the mover's update
method (writer of mover+0x90 y / reader of +0x5c) — trace it with PS2X_CALL_TRACE_DUMP on
the mover object — but the title-screen labels come first (user report 01:50).

## 2026-09-09 00:10 (local) — ROOT CAUSE of the giant sky polygons: VU0 macro-mode ops never set the MAC/STATUS flags, so the EE's frustum test called every object "fully inside" and sent it through the no-clip VU1 path
The object at the camera (STATUS 23:10) was the terrain/road strip the camera stands next to
(a 2x5 vertex grid at 90-unit spacing, world space; the transform's eye solves to the camera
position (938.6, -124.4, 832.5), which is also VU constant 30 — not a "player" test). Its VU1
command list [0x68, 6, 0x64, 8, 0x10, 0x28, 0x30] is built by `FUN_003b5f20`: word 8 (0xdf8,
transform without clipping) when the global `DAT_004b4eb0` is nonzero, word 2 (0x1f70 -> the
CLIPw subroutine at 0x3618 + edge clipping at 0x3a90/0x3ad0) when it is zero. The flag is the
third argument of `FUN_003b6b20` and comes from `FUN_00290c30`, the camera-frustum test of the
mesh's bounding box (FUN_003374c0 <- FUN_00338480 path; 2 = culled, 1 = fully inside, 0 =
intersects). That test is VU0 macro code: `FUN_00294ac0` multiplies the 8 corners by the
view-projection, runs VCLIPw and reads the CLIP flag register with CFC2; when a corner is
outside, `FUN_00294a30` does the fine test with two VSUBs and reads the STATUS register's sticky
sign/zero bits (CFC2 vi16 & 0xC0). Our recompiler never updated `vu0_status`/`vu0_mac_flags`
from any VU0 arithmetic (only CTC2 wrote them), so the fine test always returned "no corner
outside" and the near strip went out unclipped with q < 0 vertices. Also found: the macro-mode
VCLIP had the +/- bits swapped (bit0 must be x > +|w|) and compared against w instead of |w|.
Fix (recompiler): `VuTranslator::appendFmacFlags` appends `ps2_vu0_fmac_flags(ctx, res, dest)`
to every FMAC-class emission (ADD/SUB/MUL/MADD/MSUB/OPMULA/OPMSUB, broadcast/i/q/A forms; MAX,
MINI, FTOI/ITOF, MOVE, ABS untouched as on hardware); the helper in ps2_runtime_macros.h
rewrites the MAC flags (Z/S/O per lane) and STATUS (Z/S/O + sticky bits 6-9 ORed until CTC2).
VCLIP fixed to the manual's bit order with |w|. VERIFIED (logs/parity/runs/mission_s16,
logs/parity/mission_s16_sheet.png): the mission intro now renders every shot like the golden
run — helicopter over the valley, the car on the dirt road, the river/bridge scene, the forest —
with no sky-coloured polygons; the title screen (s05) is unchanged. The run ends in the forest
fly-by because the frame rate is still a few fps (item 3 below). CONFIRMED by the dump run
(logs/vu1dump3, mission_s17): 0 of 3164 kicked vertices have q < 0 (was 108 of 1878) and six
of the 150 programs now run the clipping list (word 2) that never appeared before. Gotcha: `PS2X_VU1_DUMP` does not
create its directory — mkdir it first or the run dumps nothing (silent fopen failure).
Remaining in order: ground height (-131.7 vs PCSX2 -126.3 at 0x416054), frame rate (VU1 fast
path / recompiler), then the mission parity report.

## 2026-09-08 23:10 (local) — the behind-camera triangles come from a no-clip object path; player stands 6.6 units lower than on the console
Offline replay of 150 dumped VU1 runs at the gameplay camera (logs/vu1dump2, `dist/vu1_replay.exe`
+ tools_py/gif_packets.py): 108 of 1878 kicked vertices have q < 0, all from four consecutive
frames of ONE object rendered through the 0x1b50 command-list entry (8 triangles, two texture
passes, tbp0 0x3621/0x3661 psm 8-bit, positioned at the player). Its command list is
b20 (vertex decompress: ITOF4 xyz + offset, ITOF15/ITOF12 normals/uv, ITOF0 colour) ->
0x1638 (per-triangle BACKFACE test: FMAND 0x10 on dot(cam - v, n), bit0 of the triangle record)
-> 0x4a8 -> 0xdf8 (transform, DIV Q = 1/w, NO near-plane clipping) -> 0xf90 (lighting) ->
0x1780 (emit: draws when bit0 && (bit1 || global word 39)) -> 0x22a0. The other 27 invocations
of 0x1b50 (a 60-vertex object every frame) and all 119 pc=0 runs are clean. The MAC-flag path
works as the manual says (traced with `PS2X_TRACE_VU_FLAGS=1`: the FMAND four instructions after
the FMAC sees that FMAC's flags). So the microcode is not clipping by design and the console must
never feed it this object in this state: the EE either culls it or gives it other data. Related
EE-side divergence found in the same run: the player stands at y = -132.9 (PCSX2: -126.26) with
x/z equal — the ground height from the collision grid differs by 6.6 units, and this object
(at the player) straddles the near plane. Next: find the EE submitter of the 0x1b50 list with
commands [52,3,50,4,8,20,24,...] (the JR table at 0x1ba0 indexes 340(vi14) words) and its
bounding/visibility test, and chase the ground-height difference (collision query FUN_002d49c0 /
FUN_002d2890 vs PCSX2's spawn image logs/parity/spawn_pcsx2.rdram).

## 2026-09-08 22:30 (local) — title-screen labels: the EE FPU chops; the game thread now rounds toward zero
The garbled LOAD GAME / NEW GAME / ONLINE labels (user report ~21:00) are 128x32 CT32 images the
EE composes and uploads (host->local to dbp 0x3207/0x3247/0x3287/... dbw=2), so the GS was drawing
what it was given; the CPU rasterizer garbles them in every run, the GL backend only when its
texture cache happens to re-decode (the cache made earlier runs look clean). The 8x8 blocks in the
logo's colours are glyph cells fetched from the wrong source: an index computed from a float.
The game writes FCR31 = 0 at entry (`ctc1 $zero`), PCSX2 truncates CVT.W regardless and runs the
EE FPU and VU in "Chop/Zero" rounding, and our host math rounded to nearest — the old
round-to-nearest cvt.w had masked the difference; today's hardware-correct truncating cvt.w
exposed it. Test: `PS2X_EE_ROUND=chop` (host rounding toward zero on the game thread) on the CPU
backend renders the labels correctly (logs/parity/runs/title_chop). Now the default in
ps2_runtime.cpp (game thread `fesetround(FE_TOWARDZERO)`; `PS2X_EE_ROUND=nearest` restores the
old mode). Expect other small parity shifts from this: every EE/VU0 float result now truncates.

## 2026-09-08 21:40 (local) — object geometry appears (XGKICK copied at kick time); behind-camera triangles and a title-screen regression remain
**Root cause of the missing objects.** With `PS2X_GS_TRACE_CMDS` armed at the gameplay camera
(new `PS2X_TRIGGER=lo:hi` on the first PS2X_PEEK word, `trig` mode of the GS/VIF traces), every
object triangle (1700 per frame, one texture, trees/bushes/characters) reached the GS as three
identical vertices at the GS origin with z=0xFFFF: the VU1 program re-templates its output buffer
right after XGKICK, and the per-cycle PATH1 model (one qword per two cycles while the program
runs on) still had the transfer in flight. Copying the packet at the kick (PCSX2's default; commit
089516b, `PS2X_VU1_XGKICK_CYCLE_EXACT=1` restores the old model) brings the objects back: trees
with foliage, and mission_s13's last frame is the road-through-trees scene of the golden run.

**Still wrong in-mission:** ~1/3 of the world triangles have q < 0 (vertices behind the near
plane, z wrapped to ~0xFFxxxx) and straddle the screen as giant sky-coloured polygons. The
microprogram (dumped with `PS2X_VU1_DUMP=<dir>[:count]`, disassembled with tools_py/vu1dis.py)
clips against the near plane geometrically: it forms per-vertex w sums with MULAx/MADDAy/MADDz,
reads the MAC sign flags four instructions later (`FMAND vi, 0x20` = z lane, `0x10` = w lane) and
branches into an edge-clipping path (DIV Q, vf26w, vf25w). Our MAC flag layout and the 4-cycle
flag latency match the manual on inspection, so the offline replay is the next step:
`dist/vu1_replay.exe <dump> --out p.pk` runs a dumped program through the runtime's interpreter
(registers restored from the dump), `tools_py/gif_packets.py p.pk` lists the kicked vertices and
their q sign. The three programs dumped so far (entries 0x0 / 0x1b50 / 0x33c8 of one 16 KB
microprogram) produced no negative q; a 150-program dump run is queued.

**Title-screen regression (reported by the user 21:0x):** since the XGKICK change the main menu's
LOAD GAME / NEW GAME / ONLINE labels render as teal/white noise (mission_s12..s14 s05/s06;
mission_s9, same copy mode via the env var, was clean once). Suspected the GIF arbiter's
priority sort (vendored: stable-sorts all queued packets PATH1 < PATH2 < PATH3 at drain, so a
PATH1 packet overtakes PATH3 uploads queued by the same DMA chain); it now processes packets in
submission order (`PS2X_GIF_PRIORITY_SORT=1` restores the sort) — the text is still garbled, so
that was not it. A/B run with `PS2X_VU1_XGKICK_CYCLE_EXACT=1` on scripts/parity/title_only.txt
in progress. Harness: drive.py `until(x0,y0,x1,y1)+<delay>:BTN` presses until the box shows the
briefing's highlight tint (G-R > 25), on settled screens only, and `long` waits up to 150 s.

## 2026-09-08 17:30 (local) — game state matches PCSX2 in-mission; the render does not (downstream of the EE)
With the SQRT.S fix the whole mission intro replays PCSX2's path: fly-by camera at (-3787,-109,..)
with the same rotation rows, spawn camera (939.4, 3.4, -843.6) / player (939.4, -131.7, 833.3) vs
PCSX2 (939.8, 8.3, -841.3) / (939.4, -126.3, 832.2), second fly-by, hold at (-3328, 282), then the
gameplay camera. The camera object's derived matrices (+0x2f0 world matrix, +0x330 view-projection,
+0x370 projection, +0x3b0 screen: `PS2X_PEEK="*0x488de8+0x2f0:64"`) equal PCSX2's to four
decimals. The picture at that camera is still a few giant flat polygons and sky (mission_s5/s6)
and the *pre-change* run of this morning (mission_z2, 06:54) shows the same frames, while the
online-match urban map rendered correctly on 2026-09-07 (logs/parity/online/match/A_18_hold05.png)
— so this is not a regression of today's float work but a mission-map rendering fault
downstream of the EE: VIF1 unpack, VU1 program or GS. Suspects in order: VIF unpack formats the
urban map does not use (STROW/STMASK/mode offsets for terrain chunks), a VU1 micro path, GS depth.
Discriminators prepared: `PS2X_GS_TRACE_CMDS=t<sec>` (per-batch vertex count + XYZ extents at
host time), `PS2X_TRACE_VIF=t<sec>` (UNPACK format/mode/mask/row histogram), and a
`PS2X_GS_BACKEND=cpu` mission run (GL vs reference rasterizer).

**VU1 interpreter: 158 -> 111 ns/cycle (commit 4960120).** A mission-only host profile
(diff of two PS2X_HOST_PROF dumps, logs/hostprof_mission.txt) put calculatePairReadyCycle at
20%, commitReadyPipelines at 20%, run() 8%, long-double FMAC rounding ~6%, and 15% in DLLs
outside the exe (unsymbolized). The commit scan now early-outs on an "earliest pending cycle",
the readiness scan on a "latest ready cycle", VI reads walk a bit mask, decoded pairs are served
by reference and XGKICK copies a qword at a time. Still ~700 ms of every host second in VU1 at
5 M cycles/s: the next step for frame rate is the fast (non-cycle-exact) path or a recompiler.

## 2026-09-08 16:15 (local) — ROOT CAUSE of the exploding actors: SQRT.S read the wrong register
The recompiler emitted SQRT.S with the *fs* field as its source. On the EE, `sqrt.s fd, ft` reads
**ft** (fs is zero in the encoding) and `rsqrt.s fd, fs, ft` is fs / sqrt(ft). Every square root
in the game therefore computed sqrt($f0) — usually 0.0 — e.g. the axis-angle length in the
quaternion builder FUN_003067b0 (`sqrt.s $f21, $f1` -> sqrt($f0) = 0), so sin(0)/0 saturated to
FLT_MAX and the actor orientations became (2^64, 2^64, ...). Found by the float traps
(`PS2X_FPU_TRAP`): the site divided 0 by 0 right after a `length == 0` guard that could not have
been skipped, and the generated code showed `FPU_SQRT_S(ctx->f[0])` for an instruction the
disassembler had printed as an unknown `c1 0x10544`. Fixed in ps2xRecomp/src/lib/fpu_translator.cpp
(SQRT uses ft; RSQRT takes fs and ft) and FPU_RSQRT_S became two-argument. VERIFIED 16:30
(logs/run_20260908_162132.log, screens logs/parity/runs/mission_s3): the teammate quaternion
node 0x1a83cb0 now holds unit-quaternion values (1.0, 0.707, 0.706) instead of +/-FLT_MAX, the
0x306854 trap site is gone, the collision free list stays non-empty (0xdf3538) and the player
holds y = -120 on the terrain instead of falling. The camera follows the mission intro fly-by at
(-3787, -109, ...) exactly where PCSX2's trace has it at t=202-207 s. The fly-by had not finished
by the end of the 320 s run because the game still runs at a few frames per second (VU1
interpreter); the gameplay camera (939, 8.3, ...) needs a longer run.
Along the way the FPU comparisons now flush denormals (hardware behaviour; not the cause here).

## 2026-09-08 13:30 (local) — the fall through the floor: collision grid collapse traced to exploding actor orientations
Guest-memory comparison against a PCSX2 savestate (`tools/pcsx2` + PINE work locally; the state
file's eeMemory.bin is zstd inside a zip, `logs/parity/spawn_pcsx2.rdram`) versus our
`PS2X_RDRAM_DUMP` images:
- After the level load our collision grid (world+0x684: 36x25 cells, 8192-node pool, cells at
  +0x30, free list at +0x38) is identical to PCSX2's: 3566 nodes, 1262 objects.
- At ~182 s the four squad-member collision nodes get rotation rows saturated to +/-FLT_MAX
  (translation sane), so `FUN_002d7580` inserts each into all 900 cells; the pool drains, the next
  insert links a null node and cuts the cell chain; the terrain leaves the grid, the ground probes
  return nothing and the player sinks (PCSX2 holds the player at y=-126.26, ours rests at -131.4).
  The camera runaway during the intro shots is the same objects (the camera follows them).
- The node matrix is copied from the actor's own matrix (`FUN_00315820`, called from
  `FUN_005483d0` at ra 0x549910); the actor's orientation quaternions (object+0x54/+0x5c and
  +0x74/+0x7c, class vtable 0x6691a0) jump from (-0.383, -0.924) to exactly 2^64 in every
  component. 2^64 == sqrt(FLT_MAX): a saturated maximum went through a square root, i.e. a
  division by zero happened on ours and not on the console.
- Census of saturated words: ours 798 at load / 1306 at rest, PCSX2 18. 33 heap objects of
  class 0x408330 (scene/bone nodes) hold 24 saturated matrix words each already at load.
- The EE FPU trap (`PS2X_FPU_TRAP=1`: divisions by zero, square roots of a saturated operand,
  with the guest pc) fired zero times in a full run, so the overflow originates in VU0 macro-mode
  math or a VU microprogram; traps for those are in the build being tested.
Tools added on the way (commit 91e7588): pointer-chain `PS2X_PEEK`, `PS2X_WATCH` word poller,
`PS2X_WATCH_HUGE` range scanner, `PS2X_HOST_PROF` sampling profiler, `PS2X_VU_STATS`,
`tools_py/parity/cam_poll.py` (PINE chains).

## 2026-09-08 10:30 (local) — intro movie seam fixed; in-mission camera diverges because the VU1 interpreter caps the game at 3 flips/s
**Movie seam (commit df9f8fe).** Render-target downloads wrote all 1024 texture columns back into
VRAM; past FBW*64 the page arithmetic lands in the *next* page row's first columns, so the black GPU
rows 64..96 of the movie staging buffer (FBW 10) overwrote frame rows 96..128 of page columns 0-5
after every upload — the x=384 seam on every intro-movie frame. Downloads now stop at FBW*64.
Found with a per-command shadow-VRAM probe (PS2X_GS_TRACE_PRESENT=-1 arms it from the first
seam-like decode; negative values count from the first movie block upload).

**EE FPU / VU float semantics (uncommitted, needs `./build.sh recomp`).** The generated code used
IEEE math; the EE FPU and the VUs have no infinities or NaNs (overflow saturates to +/-FLT_MAX, x/0
gives +/-FLT_MAX, denormals flush to 0, SQRT takes |x|). FPU_* macros, the DIV/RSQRT emitters, the
PS2_V* macros and the VDIV/VSQRT/VRSQRT emitters now saturate (VRSQRT also ignored its numerator
register before). The archived menu camera showed the effect: fog coefficient
`255 - near * (-255 / (far - near))` with far == near is 255 on the PS2 and NaN under IEEE.

**In-mission picture: camera, not renderer.** PCSX2 (tools/pcsx2, PINE port 28011) runs the
mission script fine — `tools_py/parity/cam_poll.py` reads the camera object (`*(0x488de8)`, static
scene 0x4887c0 + 0x628) over PINE while `drive --target pcsx2` runs; ours uses
`PS2X_PEEK="*0x488de8+0x320:3"` (peek now dereferences pointers). Fog block, frustum, view matrix
and spawn position match PCSX2 word for word at spawn. Then ours lets the camera height decay
(8.8 -> 3.1 in one second; PCSX2 holds 8.35) and the position grows exponentially to +/-FLT_MAX for
~22 s (the scripted shots), returns to spawn, and the later scripted move happens on both sides.
The sky-dome-from-below frames are that runaway camera.

**Root cause of the divergence: frame time.** `FUN_003aff30` (flip) reads T0 as the frame time and
resets it; the camera update `FUN_002998f0` integrates with it. Per-second flip counts (call trace
on 0x3aff30) are 2-16 in the mission (PCSX2: 60). A host-level sampling profiler
(`PS2X_HOST_PROF=<ms>` + `tools_py/hostprof_symbolize.py`) puts ~80% of the game thread in the
VU1 interpreter's cycle-exact bookkeeping (`calculatePairReadyCycle`, `commitReadyPipelines`,
long-double FMAC rounding); `PS2X_VU_STATS=1` measures 4-7 M VU1 cycles/s at 120 ns/cycle,
i.e. ~1 M VU1 cycles per game frame, 0.5-0.8 s of host time per second. Ruled out on the way: the
scratchpad slow store path (fast path added anyway), the GS command queue (no backpressure),
guest-clock overhead. A 60 fps mission needs ~16 ns/VU1 cycle: a VU1 recompiler/JIT, not
interpreter tuning (2-3x at best from mask-based hazard checks and an early-out commit).

**Interim fix in progress:** guest time must exclude the host time spent in the VU1 interpreter
(`ps2GuestClockExcludedNs`, subtracted in `EeScheduler::accountCycles`), so the game sees ~1/60 s
per frame and runs in slow motion instead of integrating a 300 ms step (a per-gap cap did nothing:
the interpreter runs in ~1000-cycle slices). Result: see the next entry.

## 2026-09-08 (local) — our exe completes the SCERT handshake with Horizon; menu movie merged
Two fronts landed since the 22:40 entry.

**Menu background movie (merged to develop, commits 8c01711/1f15173/db44f62).** The runtime already
had an FFmpeg-backed sceMpeg HLE; two protocol gaps (sceMpegCreate not zeroing the libmpeg work
buffer, and GetPicture parking the only feeder thread) stopped every movie. Fixed in
Kernel/Stubs/MPEG.cpp. Main-menu parity 81.0 -> 98.8; the Sony/intro/cinematic movies play too.
Boot now has two more screens than before, so the online script uses five boot presses.

**Exe online netstack (uncommitted until this entry's commit).** From black-screen after the network
IRX loads to a completed SCERT TCP handshake with the real MUIS (10071). Layers:
- SIF sreg handshake echo (socom2_SifSendCmd) and msifrpc init/bind/call/unbind HLE.
- eznetcnf/eznetctl IOP service (ps2xIOP/src/modules/eznetcnf.cpp): one "Setting 1" combination,
  interface always up. DNAS tick (FUN_002cc670) reports done.
- libnetb (socom2_libnetb.cpp): the simple RPCs (sceInetCreate/Open/Recv/Send/Name2Address/poll/
  interface events) and the libnetb_ex ring path (FUN_002472c8/74f8/7738/7d30/7fe8/79b8/7bd8)
  replaced by host Winsock (socom2_hostnet.cpp). Contract: docs/research/10-libnetb-rpc.md.
- rt_crypt on the host (socom2_crypto.cpp): 512-bit RSA modexp (FUN_0062b948), SHA-1 prefix
  (FUN_0062eec0) and the RC4 variant (FUN_0062a638/5a8/720/7c8). The fixed client keypair
  (socom2_rsa_key.h) was regenerated as a FULL 512-bit modulus: a 511-bit N let the server's
  512-bit RC4 session key exceed N and broke the CONNECT_TCP decrypt.
Result: the exe resolves the retail hostnames to PS2X_SOCOM2_SERVER (default 127.0.0.1), connects
TCP to MUIS, the server accepts CONNECT_TCP and sends CONNECT_ACCEPT + CONNECT_COMPLETE, the
client sends the LobbyExt/0x03 universe query and shows SELECT UNIVERSE with the Horizon universe
and its news (2026-09-08). Later the same night the exe logs in (MAS), reaches the lobby (MLS),
joins Channel 1 and hosts a game: GAME LOBBY with a live DME world (TCP + aux UDP), driven by
`tools_py/parity/online_login_ours.py --existing --host`; parity 98-99 vs the PCSX2 golden set.
**02:40 — a full online match between two instances of our exe** (`online_match_ours.py`: A hosts,
B joins and switches team, both READY → VIGILANCE/SUPPRESSION → in mission; Horizon world
WorldStaging → WorldActive). The second instance uses PS2X_WINDOW_TITLE / PS2X_MC_DIR /
PS2X_SOCOM2_UDP_SHIFT. M5 (online lobby + match against our own server) is reached. The earlier stall was the frozen COP0 Count: `mfc0 Count` reads
ctx->cop0_count, which nothing advanced, so SCE-RT's clock stayed at 0 and the connected-state
send gate (30 ms since the last flush) never opened; the runtime now refreshes cop0_count from the
host steady clock at 294.912 MHz on every syscall and scheduler switch-in.
Driver: `python -m tools_py.parity.drive --target ours --script scripts/parity/launch_to_online_ours.txt`
with the Horizon stack up (no dns_stub needed; the exe resolves internally).

Reference: tools/reference/reCOM (git-ignored) and docs/research/11-recom-applicability.md map
~70 of our FUN_ addresses to SOCOM 1 / GameZ names.

## 2026-09-07 22:40 (local) — our exe reaches LOGIN TO SOCOM II ONLINE (netstack bring-up started)
ONLINE on our exe used to go black after loading the network IRX set. Three layers were missing:
- SIF sreg handshake: msifrpc's init sends SETSREG (0x80000001) to the IOP and spins on the EE
  sreg table until the IOP module echoes it. `socom2_SifSendCmd` mirrors the write (sreg table
  at 0x1da6c0). `sceSifGetSreg` is not stubbed — it is the game's own code reading that table.
- msifrpc (multi-SIF RPC, SCE-RT's transport for libnetb, service 0x80001201): init/bind/call/
  unbind (FUN_001bcd80/1bd050/1bd320/1bd200) are replaced by host handlers; the call is answered
  synchronously by `socom2LibnetbCall` (for now every fno logs and returns -1). EE ABI: args 5-8
  in t0-t3.
- eznetcnf/eznetctl (0x75499128/0x75488909) are a new ps2xIOP service
  (ps2xIOP/src/modules/eznetcnf.cpp): one "Setting 1" combination, interface always connected.
- DNAS: FUN_002cc670 bound to ret0 (the pnach's `jr ra` equivalent).
The login screen appears; it still says "No Network Adaptor detected" because libnetb fno 8
(interface list) / fno 9 (interface control) return -1. Reverse-engineering of the libnetb RPC
contract (LIBNETB.IRX decompiled to game/analysis/LIBNETB.IRX.decomp.c, spec going to
docs/research/10-libnetb-rpc.md) is in progress; the socket layer (Winsock) comes next.
Driver: `python -m tools_py.parity.drive --target ours --script scripts/parity/launch_to_online_ours.txt`.
Reference: tools/reference/reCOM (git-ignored clone of NotEnoughPhotons/reCOM, a SOCOM 1/2 +
GameZ decomp with demo-disc symbol names) for naming engine functions.

## 2026-09-07 21:10 (local) — ONLINE MATCH: two PCSX2 clients play VIGILANCE on the local Horizon stack
`python -m tools_py.parity.online_match` logs two retail clients in (socom / socomb), A creates a
game (Medley play list), B joins it, B switches team, both press READY and the match launches:
both screens show VIGILANCE / SUPPRESSION in-game with the round timer (logs/parity/online/match/,
A_18_hold05 and B_20_hold05). DME world with two clients, TCP + aux UDP, broadcasts flowing.

Fixes since the 18:45 entry (commits a2fdc45, 1ce3047, and the match commit):
- Lobby/0xEC channel list request + 0x70-byte 0xED entries (briefing rooms).
- CreateGameRequest1: Attributes optional (1.50 sends 0xD0 bytes).
- Game.OnWorldReport(MediusWorldReport0) copies GameStats — the 1.50 client keeps map/rounds
  there; without it the joiner shows "unknown" and refuses to join.
Second client plumbing (tools/pcsx2_b, git-ignored; templates in scripts/parity/pcsx2/):
- robocopy of tools/pcsx2 with PINESlot 28012, Slot2 memory card disabled.
- Its own savestate 5 of the LOGIN screen made by booting it (main menu → ONLINE): a state copied
  from the other install re-probes the card on load and drops the network configuration.
- Its card already holds A's persona, so the persona list needs Up, Cross, Down, Cross.
- Two guests on one host adapter both bind host UDP 3658/3659 (PCSX2 Sockets mode) and DME replies
  went to the wrong socket; a B-only pnach changes `li a0,0xE4A` at 0x620678 to 3660. (The
  host-only adapter alternative fails: Windows strong-host routing, no admin for weakhost.)
Still unhandled by Horizon and harmless so far: Lobby 0x86, 0xB2, 0xCE, 0xEF, LobbyExt 0x08.

Next: our exe. The PS2 side is now fully characterised (every request/reply the 1.50 client needs
is in server/logs); bring the recomp's inet/netcnf HLE up (Winsock) so socom2.exe reaches the
same screens, scored by the harness against these PCSX2 captures.

## 2026-09-07 18:45 (local) — online: a PCSX2 client logs into Horizon and reaches the SOCOM II ONLINE lobby
Priority is online play (user, 21:30 entry in HANDOFF). Result tonight: the retail client running in
PCSX2 goes LOGIN → LOCATING UNIVERSES → SELECT UNIVERSE ("SOCOM II Local", news text) → CONNECT TO
SOCOM II (persona/password typed on the on-screen keyboard) → ACCOUNT LOGIN → USER AGREEMENT →
SOCOM II ONLINE lobby with the SERVER NEWS popup from Horizon. Screens: logs/parity/online/login/.

Plumbing (all under tools/pcsx2, git-ignored; templates in scripts/parity/pcsx2/):
- DEV9 Sockets on the Realtek adapter, InterceptDHCP, manual DNS = 192.168.2.10 (host LAN IP).
  PCSX2's [DEV9/Eth/Hosts] table was not honoured, so `tools_py/parity/dns_stub.py` answers the
  game's hostnames (socom2-prod[.muis].pdonline.scea.com, gate1.*.dnas.playstation.org) on UDP 53.
- DNAS bypass pnach (unconditional; labelled groups are opt-in and were skipped).
- Memory card recreated with mymcplus (the original was unformatted) and a saved network config.
- Horizon configs advertise 192.168.2.10, not 127.0.0.1 (the guest cannot reach loopback).
- Savestate 9 = the LOGIN TO SOCOM II ONLINE screen. Only this state is usable: states saved after
  any network traffic restore with a stuck SMAP transmit ring (BD_TX storm) or dead input.

Protocol fixes in Horizon (commit e990033), found by reading the 1.50 client library in the decomp:
- Universe query is LobbyExt/0x03 → ExtraInfo list LobbyExt/0x04 (0x338 bytes) **and** a
  UniverseNews reply (Lobby/0xC9); completion needs InfoType == accumulated bits (DAT_006561b0).
- AccountLoginResponse must be exactly 0xC4 bytes: NetConnectionInfo's 2-byte alignment pad is
  now unconditional (the PS2 client sends no CLIENT_HELLO, so Horizon assumed version 108).
- The client's VersionServer request (Lobby/0x86) can stay unanswered: no game callback.

Method that worked: handler ids are assigned sequentially per class by FUN_0063c8a0, so id N of
class 1 is the N-th registration after line 564046 of the decomp; the handler returns the expected
byte count. Reading the slot table over PINE (e.g. 0x686f14) gives the live ids.

Unhandled by Horizon so far (client still proceeds): Lobby 0xB2 FileListFiles (WeapProfile_1.dat),
0xEC ChannelList_ExtraInfo0 (lobby room list — needed next), 0xEF LadderList_ExtraInfo0,
LobbyExt/0x08 GetBuddyInvitations, Lobby 0x86 VersionServer.

Next: close server news → BRIEFING ROOMS (channel list) → create/join a room; then a second
PCSX2 instance (separate ini/memcard/PINE port; the "never two instances" rule is about our exe
sharing logs, but two PCSX2 processes also need distinct DEV9 MACs) and a match through DME.

## 2026-09-07 20:00 — roller renders; mission renders textured; report ours_e
After un-stubbing libvu0 (commit fb97a7b): the main menu shows the 3D roller with LOAD GAME /
NEW GAME / ONLINE (menu 79 → 81; the MENULOOP.PSS movie background is still black), popup 99.6,
select rank 99.0, briefing 96.4, and the mission frame is now textured (rock walls, timber) instead
of flat grey — the same wrong-order matrix maths had been feeding the mission's transforms.
`scripts/parity/align.json` shifted by one step (our side now captures an extra early frame).
Still open on the shell: the menu movie background; the controller-configuration screens (our
step after Select Rank is a black frame where the original shows two screens with 3D controller
models). Mission: camera/HUD/movement not yet looked at.

## 2026-09-07 19:30 — main menu roller: culled by a wrong clip matrix from the libvu0 HLE
Chain of evidence (all at the real main menu, two presses; the earlier "menu" numbers in this file
were taken one press too late, on Select Rank): the roller model loads (23 mesh parts under a
type-2 node with 12 leaf children, bbox ±13.7), is added to the scene (`FUN_0031f240`) and is handed
to the node draw `FUN_0033b110` every frame — identical node/scene state to PCSX2 read over PINE.
The children traversal `FUN_003389c0` then asks the frustum test `FUN_00290c30` and gets 2
("fully outside") every frame, so no leaf part is ever submitted (`xgkick=0` at the menu). The
camera object (static path `0x4887c0+0x628`) matches PCSX2 word for word except the clip matrix at
+0x330: rows 0-1 equal, ours rows 2-3 = `[-320 0 319 1] / [0 0 0.40 0]` vs PCSX2
`[0 0 -1.004 -1] / [-457 0 320.9 320]`. `FUN_00294070` builds it as
`sceVu0MulMatrix(clip, proj, viewInv)` and PCSX2's result is viewInv·proj, so the HLE stub in
`Kernel/Stubs/VU.cpp` multiplies in the wrong operand order (its "ViewScreenMatrix" and friends are
guesses too). Fix: stop hand-emulating libvu0 — the 29 `sceVu0*` stubs are removed from
`recomp/socom2.toml` and the uncovered entry points forced in `recomp/extra_functions.txt`, so
Sony's own VU0-macro code runs (safe now that vf00 writes are ignored). Recomp rebuild pending
verification: popup placement must stay, the roller and the controller-config models should appear.
Side note: camera +0x130 holds NaN on ours vs 255 on PCSX2 (a clamp/lerp path), unexplained.

## 2026-09-07 18:10 — mission thread no longer dies (merged Ghidra range)
With `recomp/merge_ranges.txt` folding 0x510970-0x5109a8 (the while-loop whose body Ghidra had
left in a gap between a "thunk" row and the loop condition), the 400 s mission run shows
`MissionTick` #1560 at 305 s and zero `[guest-branch:missing-target]` (it used to halt ~30 s into
the mission, around tick 660). Geometry keeps flowing (`xgkick` 1.5M by frame 2685) and the frame
stays a flat-shaded blue-grey world from a fixed camera: no textures, no HUD, no visible camera
motion yet — those are the next mission items once the shell screens are scored ≥90.
`tools_py/find_escaping_branches.py` found only two functions with this split-loop shape; the
other (0x534c4c) is a real multi-entry function and is left alone.
Caveat: two 400 s runs of this build overlapped by accident (a background wait loop launched
one 13 s before the hand-started one: `run_20260907_154947.log` and `_155000.log`). Both show
zero `missing-target` and ticks continuing to the end (#1800 / #1560), which is a control-flow
result and holds; their frame-rate and counter values are skewed and should not be quoted.

## 2026-09-07 17:00 — the shell looks like the original (text, placement, palettes fixed)
Parity report `ours_d` (docs/parity/REPORT.md): memory-card popup 99.6, select rank 99.2,
mission briefing 96.2 (all text, tabs, fireteam loadout, typewriter effect), main menu 79.1
(soldier background art and the roller captions still missing), warning screen 78 (animated;
capture timing). Four fixes, each verified with the popup screenshot and then the full run:
1. **vf00 writes** (recompiler, `instruction_translator.cpp`): the game's `qmtc2.i $a0,$vf0` /
   `vaddx vf0,vf0,vf0x` / `lqc2 $vf0` idioms are no-ops on hardware; we executed them and every
   `vmaddw … vf0w` translation term went to garbage — all 2D elements sat at the origin.
2. **Face culling** (`gs_gl_backend.cpp` setupDrawState): raylib's rlglInit enables GL_CULL_FACE
   and the GS backend never disabled it; glyph sprites (second vertex above the first) have the
   opposite winding and were culled. Diagnosed with the new `PS2X_GS_GL_DEBUG_PSM=<psm>` print
   (state, bound texture texel, region readback before/after the draw: "0 of 216 pixels changed").
3. **CSM1 CLUT swizzle** (GL): 4-bit palettes are 8x2 blocks, address bits 3/4 swapped; the GL
   resolver read a linear strip, so the bright half of every 4-bit palette was wrong (dim text).
   The CPU rasterizer already had `swizzleClutIndexCSM1`.
4. **CPU sprites** swap texcoords with corners (text was flipped on the reference rasterizer).
Also: `recomp/merge_ranges.txt` (+ `fix_ghidra_csv.py`) folds the split loop 0x510970-0x5109a8
that killed the mission thread; recomp rebuild pending verification.
Remaining shell gaps (next by score): main menu background art + roller captions; the
controller-configuration screens (our s04 is black where the original shows two screens — likely
the same class as the menu art); the text-only title cards flash past on our side (not captured);
glyphs render slightly heavier than the original (shadow pass alpha?).

## 2026-09-07 — mission draws; parity harness is the grade; two systemic UI bugs found

**Mission (M4):** the "renderer submits nothing" blocker was thread starvation, not rendering.
Thread 2 is the priority-4 auto-exposure thread (`FUN_003b1dd0`) which, once a mission is up, reads
~176 framebuffer pixels per pass with `FUN_003b24c0` (GS local→host through the VIF1 reverse FIFO).
The runtime has no reverse-FIFO path, so each read spun to its 16M-iteration timeout (~0.3 s) and
the main thread got one tick per minute. `FUN_003b24c0` is stubbed at recompile time
(`socom2_LumReadPixel@0x003B24C0`, mid-grey pixel). Result: `MissionTick` ~20/s after the load,
geometry counters climb (xgkick 4k → 700k), flat-shaded world polygons and a night sky on screen —
the first in-mission frames. ~30 s in, the main thread dies at 0x510978: a list-search loop whose
head Ghidra split into an 8-byte "thunk" row, so the backward branch becomes an unwind to an
address no function owns (`[guest-branch:missing-target]`). `tools_py/find_escaping_branches.py`
lists every such branch (35k in 1.1k functions, mostly harmless case chunks); the fix is to merge
rows whose branch target is not another row's entry. Queued behind the shell parity work.

**Parity harness (the new grade, see HANDOFF "The grade"):** `tools_py/parity/` — `winshot.py`
(PrintWindow capture, no focus), `keys.py` (posted keys to PCSX2's Qt window or our raylib window,
both accept them without focus), `drive.py` (one step script for both sides, `next` = wait for a
new settled screen, screens labelled by step index), `compare.py` (score + side-by-side diff +
`docs/parity/REPORT.md`), `pine.py`/`addresses.py` (PCSX2 PINE memory reads, escalation aid),
`montage.py`. PCSX2 2.8.1 in `tools/pcsx2` with PINE on 28011; its card was formatted offline with
`mymcplus` so the save prompts do not loop. First report (`ours_a`): 6 of 20 golden screens have a
matching screen on our side; our sequence skips the loading screen, the "No SOCOM data" notice and
the three text-only title cards (all black), draws the main menu as logo-only, and reaches the
briefing. `scripts/parity/align.json` maps golden steps to ours by content until the sequences
converge.

**What the first side-by-side proved (GS command trace at the memory-card popup):**
1. **Text is submitted, not missing.** Glyphs are tiny textured sprites (4-bit PSMT4 font page
   512x128 at tbp 0x3bf7, CLUT at 0x3bf3) drawn with the second vertex *above* the first. The CPU
   rasterizer drew them vertically flipped because `DrawSprite` swapped the corner coordinates
   without swapping the texture coordinates — fixed (text now upright with `PS2X_GS_BACKEND=cpu`).
   The GL backend still draws nothing for them (decode of the 4-bit page is correct — verified with
   `PS2X_GS_DUMP_TEX`; the difference from the 8-bit box that does draw is not yet understood).
2. **Every 2D element is drawn at the origin.** The popup box is submitted at (0,0)-(340,100) and
   both slot buttons at (0,0); the element drawer (`FUN_003643b0`) transforms its local rect through
   the node matrix with `FUN_00308640`, whose translation term is `vmaddw.xyz vf9, vf7, vf0w`. The
   recompiled game *writes vf00*: `qmtc2.i $a0,$vf0` (an interlock idiom, e.g. 0x30702c/0x3076b4
   right next to the transform helper), `vaddx vf0,vf0,vf0x` and `lqc2 $vf0,…($k1)`. On hardware
   vf00 is the read-only constant (0,0,0,1); we clobbered it, so every translation multiplied by
   garbage. Fix in `instruction_translator.cpp`: writes to vf00 are emitted as comments (recomp
   rebuild in progress at the time of writing — verify with the popup: box centred, logo centred).

**Docs/process:** HANDOFF gained "The grade" (parity loop, rules, escalation triggers) and gotchas
7-9; spec `docs/superpowers/specs/2026-09-07-parity-harness-design.md`, plan
`docs/superpowers/plans/2026-09-07-parity-harness.md` (with the design simplification amendment).


## Milestone board (from the design spec)
| # | Milestone | State |
|---|---|---|
| M1 | Fork + toolchain: merged ELF recompiles, runtime links, `socom2.exe` runs crt0→main | **done** |
| M2 | Loader → game entry → engine init without unimplemented-instruction faults | **done** — engine runs its main loop; audio init + DBCMAN reached |
| M3 | Legal/intro screens + main menu render, pad works, UI sounds | **done for navigation** — first boot runs to the main menu at 60 fps, input drives every shell screen; button captions and the 3D roller still do not draw |
| M4 | Single-player mission playable | **in progress** — the Albania 5-1 mission loads from the briefing screen and its engine, AI and mission scripts run at 60 fps; the in-mission renderer submits no geometry |
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

## 2026-09-06 02:15 — the first single-player mission loads and runs (M4 opened)

Driving the pad script `8:CROSS,12:CROSS,16:CROSS,20:CROSS,24:CROSS,30:DOWN,32:DOWN,34:DOWN,
36:DOWN,38:DOWN,41:CROSS` now walks the whole single-player entry: first boot → main menu →
NEW GAME → dlgSelectRank → dlgControllerPresetsNewGame → dlgControllerPresetsRG →
dlgAlbaniaCinematic → **dlg_Brief_Alb51** (the Albania 5-1 briefing, which draws its real
photo panels) → five DOWN presses move the briefing selection from `overview_button` to
`deploy_button` → CROSS fires `OnDeployActivate` → `LoadMission` → `LOAD_SCREEN` → the mission's
own systems register (`CClutterAnimManager`, `diTick`, `Mission`, `ParticleTick`, `UnitTick`,
`ai_pre_tick`, `entity_pre_tick`, `weapon_pre_tick`) and the level's AI scripts start
(`Supply1-4_start`, `Informant_start`, `Sniper1/2_start`, `Alarm1-4_start`, `PatrolWatch_start`,
`set_iris`, `otc_init`). Zero `[guest-branch:missing-target]`, and the engine holds 60 fps.

Four fixes got there, in order:

1. **The EE dispatcher mistook a scheduler unwind for a return** (commit 2acef9c).
   `dispatchGuestBranch` decided "the callee returned" by comparing `ctx->pc` with the entry pc it
   dispatched to. A callee that leaves through a scheduler checkpoint while its pc still equals its
   own entry address is indistinguishable that way, so the caller resumed with the *callee's*
   registers. That is what killed the EE thread when dlgMenu loaded: the 2D-node lookup
   `FUN_00315a80` called from `Add2dNode` (`FUN_0036ab20`) came back with s1 = 1 and the caller
   dereferenced `screen+0x60` through `0x1` → `missing-target target=0x14 ra=0x36abc0`. The runtime
   now carries an explicit unwind flag (`markDispatchUnwind` / `clearDispatchUnwind`) that
   `eeCheckpointDue`, the non-call path and the missing-target path set and the scheduler clears
   before every dispatch. 5 of 5 runs reach dlgMenu with all 17 of its controls created.

2. **Interrupt handlers ran on the interrupted thread's stack** (commit 3eb4285).
   `AddIntcHandler`/`AddDmacHandler`, `SetAlarm` and `sceGsSyncVCallback` registered the *caller's*
   sp as the handler's sp, so a handler firing later trampled live frames of whatever that thread
   was doing. They now pass sp = 0, which makes the scheduler allocate its per-(thread, depth)
   invocation stack — the same stack every other invocation kind already uses. This reduced the
   dlgMenu crash rate but was not its root cause (that was item 1); it is still a real bug fixed.

3. **136 function bodies Ghidra never listed** (commit 1754184). `tools_py/find_gap_functions.py`
   walks the gaps between CSV function ranges and reports every gap whose body contains `jr $ra`,
   skipping anything `socom2.toml` stubs. A register-dispatched call into one of these found no
   recompiled target and silently did nothing (gotcha 1). The 4-instruction leaf at 0x346300 was
   hit during "new game" and ended the run. Same commit: `ControlFlowEmitter::emitStaticJump` was
   emitting `goto label_X` for a JAL whose target is one of the function's own entry points, so a
   self-recursive call ran in the caller's host frame and its `jr $ra` returned out of the host
   function — 97k scheduler unwinds in a single 24 s menu run, all from the rdr tree search
   `FUN_0032f0e0`. A JAL is now always emitted as a call.

4. **Six merged Ghidra ranges whose second function is called by pointer** (commit 316dafd).
   `tools_py/find_interior_functions.py` looks inside every CSV range for a `jr $ra` + delay slot
   followed by more code, and keeps the boundary only when that address is actually referenced — as
   a JAL target, as a 32-bit word in the image, or as an address built by a `lui`/`addiu` pair.
   That reference test is what separates a real second function from a second return point: 362 raw
   boundaries reduce to 6 referenced ones. `fix_ghidra_csv.py` now truncates the parent range at a
   forced entry inside it so the two do not overlap. The one that mattered: the static-array
   construct helper at 0x181fb4 calls the element constructor 0x5550c0, which lived inside
   `FUN_005550b0`'s range and blocked the mission load.

**Correction to the previous handoff:** "all UI positions resolve to (0,0)" is wrong. Dumping guest
RAM at the moment dlgMenu's CONTROLS list loads (`PS2X_RDRAM_DUMP_AT`, then `tools_py/rdr_tree.py`)
shows the parsed tree carries the real values — `new_game_button` XPOS 256 YPOS 330, `SplashLogo`
70/45 — the 17 design records built from it hold the same numbers, and the 2D nodes created from
those records have them at +0x30/+0x34 as floats. The SOCOM II logo does draw at its correct
position. What is actually missing on the menu is the button *captions* (their rdr CAPTION is a
single space; the text comes from elsewhere) and the 3D roller.

**Where it stops now:** in the mission, `FUN_001ebed0` (the in-mission tick — the previous handoff
said it is never called, which was true only before the mission could load) runs, but the frame
counters freeze at the values they had in the shell (`vif1codes=399073`, `mscal=22426`,
`xgkick=4421`, `nonBlack=0`), so the in-mission renderer submits no new geometry. The EE main
thread (1) goes dormant when the mission starts and the mission runs on thread 2; sampling shows
that thread spending essentially all its time at the resume point 0x2716e0 inside `FUN_00271650`,
a recursive scene-graph walk, with a *constant* guest sp (so it is not runaway recursion).

New diagnostics this session: `PS2X_JALR_TRACE="0xSRC,..."` (resolved target of the indirect calls
issued from those pcs), `[ret-clobber]`/`[ret-unwound]` lines from the `PS2X_CALL_TRACE` thunk (a
traced function returning with a callee-saved register changed / leaving through a scheduler
unwind, in which case its `[ret] v0` is not its result), `PS2X_RDRAM_DUMP="<path>:<seconds>"` and
`PS2X_RDRAM_DUMP_AT="<path>:<TracedName>#<n>"` (32 MB guest RAM to a file), and
`tools_py/rdr_tree.py` to print a parsed .rdr tree out of such a dump.

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
queries card info. **Presentation bug (reported by the user as a smaller frame, black squares and flicker on the GPU
path; fixed 2026-09-05 17:55):** the runner was told the presented texture was 640x448 while the
render target texture is 640x1024, so raylib squeezed the whole target into the display rectangle
(picture squashed into the lower part, unused black rows visible, alternating targets flickering).
`HostFrameTexture` now reports the texture's full size and the runner draws only the top-left
presented rectangle. Depth textures are also cleared to 0 on creation now (were undefined).

The gate is in the shell's UI layer: every UI input site uses the pad only when the current
screen object's +0x114 (local player index) is 0 (`FUN_00592ac0`). Next step and lldb recipe in
HANDOFF. The pad state machine itself (`FUN_002d9ff0`: states 0/1/2/3 + timers) is verified to
work with the HLE input. Pad sockets: only the newest socket reports connected (the boot-time
controller-check socket is deleted by the game; the HLE never sees the delete).

## Where the guest is now (2026-09-05 18:40) — main menu reached, "new game" hand-off stalls
The "+0x114 player-index gate" theory above is dead: the presses work. What the shell shows after
START is the **main menu screen** (`dlgMenu.rdr` in `game/disc/RUN/UI/READERC.ZAR`: buttons
new_game/load_game/multiplayer/options/extras/LAN, the `SavedGames` list box with the
`popup_load.tif` panel, the SplashLogo, a 3D `mainmenu_roller` model). We only see the load-game
panel and the logo; the buttons and the roller are not drawn (open rendering question, see below).
The user confirms that panel is not what the real game shows there.

How it was found (all new diagnostics, env-gated, zero cost when unset):
- `PS2X_CALL_TRACE="0xADDR[:name],..."` (game_overrides_socom2.cpp): logs every call of the
  listed guest functions — time, a0-a3, f12-f14, ra, any argument that points at text — and the
  return value (`[ret] name #n v0=… f0=…`). Works through the dense function table, so direct
  JALs are caught. 320 slots. Traced set that decoded the shell: the **script binding table** at
  ELF 0x3dd4d4..0x3de1c4 (207 `{name, fn, 0, id}` rows, 16 bytes each — SetMission, SwitchMenu,
  SetMenuState, ReadyToLoad, LoadSavedGame, ListSavedGames, GetNumSavedGames, IsMemCardInserted,
  SuspendMenuInput, PlayMPEG, …; dump: `tools_py` one-liner in the 18:40 session, list saved in
  the scratchpad as script_bindings.txt) plus the **animation-sequence command table** registered
  by `FUN_0026a8e0(0x414bb0, "NAME", 0, create, execute, 0)` at decomp lines 106865-106930
  (OBJECT_OPACITY_FROM_TO exec 0x25f880, CALL_ANIMATION 0x25d550, ui::UI_COMMAND 0x2745a0 = the
  dispatcher for the binding table, OBJECT_ACTIVE_STATE 0x263aa0, IF 0x25e7a0 / ELSE 0x25e6d0 /
  ENDIF 0x25e6a0, CALL_SEQUENCE 0x25d270, …). `FUN_0034e6b0(delay, queue 0x49ea50, "event",
  node, arg)` schedules a named script event ("goto_menu", "UiprepMission1" …).
- `PS2X_CD_TRACE=1`: `[cd] SearchFile`/`[cd] Read`/`[fio] open` on stdout (the RUNTIME_LOG
  versions are compiled out). `PS2X_MC_TRACE=1` now prints GetInfo/Sync on stdout.
- `PS2X_PEEK="0xADDR[:words],..."` dumps guest words (hex + float) with every PC-sampler line.
- `PS2X_FRAME_DUMP` pixels were **stale** on the GPU path (the same frame re-reported forever) —
  do not trust the PPMs/`nonBlack` for "what is on screen"; `PS2X_HOST_SCREENSHOT=<dir>[:<s>]`
  saves what the window shows. Display-off presents (PMODE EN1=EN2=0) now blank the dump.

Shell flow observed (call trace, `8:START,16:CROSS`): boot → `do_onstart`, `intro_onstart`,
`load_initial_config`, SwitchMenu → START → `goto_menu` → SwitchMenu(5) → `menu_fade_up`,
`PulseArrows`, `UiStopAttract`, `SetMenuValve`, `has_memcard_changed`, `CleanupMissionMemory`,
`Ensure_MC_Dirs_Fast` (sceMcGetDir root, sceMcChdir, sceMcGetDir "BASCUS-97275SOCOMII" → 0),
GetNumSavedGames (sceMcGetDir SaveGame0..9 → none), `IF GotSaveGames > …` → then a 1.5 s
`has_memcard_changed` poll loop. CROSS = the **new_game_button** → event `UiprepMission1`:
SOUND, `SuspendMenuInput 0.75` (writes shell+0x900, decremented per frame in `FUN_003654c0`),
OBJECT_ACTIVE_STATE ×3 (menu objects → INACTIVE: this is why the screen goes black), then the
sequence engine stops ticking. The engine's main tick `FUN_001ebed0(dt, app)` then runs its
fade-to-mission countdown branch (`app+0xc8 -= dt; f = app+0xc8 * app+0xc4; f < 0 →
FUN_002a9a70(0x4364e0)` → push mission state 0x4086a0 via `FUN_002cf380(0x4084c0, …)`), but
`FUN_002a9a70` never fires (traced, 6 s). Current step: peek app+0xb8..+0xc8 and dt to see why
the countdown does not complete (app object address = a1 of the traced `FUN_001ebed0`).

Other facts: memory card HLE reports a formatted 8 MB card with no `BASCUS-97275SOCOMII` dir;
the game does not try to create it (Mkdir never called) — fine for now. After CROSS no disc
reads or fio opens happen. VU1 keeps running programs (mscal rises) but XGKICKs stop: the UI
packets carry the "no setup kick" flag (header.w bit 1 clear at microcode 0x30) and no vertices.

## 2026-09-05 19:35 — first-boot flow runs end to end; main menu reached (commit 60fe75c)
After the full recomp with 0x353d00/0x2a98a0 forced, `PS2X_SOCOM2_INPUT_SCRIPT="8:CROSS,12:CROSS,
16:CROSS"` drives: memory-card slot popup → "loading" warning → "no SOCOM data found" →
StoreOptions → Sony logo (SONY448.PSS) → intro (INTRO_2.PSS) → `goto_menu` → dlgMenu over
MENULOOP.PSS, VU1 kicking, 60 fps. (The pre-fix flow had skipped the whole valve-guarded
memory-card path, which is why it went straight to the menu with a load-game panel.)
Also fixed: the GL present drew the frame with alpha blending, and the menu frame's alpha is 0,
so the window was black while the RT was fine — the present is now drawn opaque
(`rlDisableColorBlend`), plus a full colour mask before the present blit.
Open (see HANDOFF next task): UI positions all at (0,0) (buttons invisible, popups top-left),
an intermittent null-vtable crash in `FUN_0036ab20` when dlgMenu loads, VU1 packets with no
vertices (no 3D roller). Locale archives do load (`LoadLocale "UIMn"` ok), so captions exist.

## 2026-09-05 19:10 — root cause of the stalled "new game": an unrecompiled trampoline
Runner R2 of the `UiprepMission1` animation (three runners: button anim → SOUND, motion,
`SuspendMenuInput`; fade → OBJECT_OPACITY_FROM_TO + OBJECT_ACTIVE_STATE×3; then a sequence of
14 `VALVE` nodes) stays in state 4 with its current node pointer on the first VALVE node
forever. VALVE is registered by `FUN_0026a8e0(0x414bb0, "VALVE", parse=0x3535d0, 0,
exec=0x353d00, 0)` (decomp line 252352) and **0x353d00 is not a function in the Ghidra CSV**: it is
the two-instruction thunk `j 0x353fd0; addiu $a0,$a0,4`. The dispatcher's table call into it
had no recompiled target and returned without doing anything, so the runner never advanced
(`PS2X_CALL_TRACE=0x353d00:VALVE` prints `[call-trace] no function at 0x353d00`).

Scan for the same class (thunks outside every CSV function range) found exactly two: 0x353d00
and 0x2a98a0 (event-completion callback passed to `FUN_0034e6b0`). Both added to
`recomp/extra_functions.txt`; full recomp started 19:05. Also noticed: 0x38e890/0x3b7cf0 were
listed there since 17:00 but the EXE still reported `missing-target 0x38e890` — the forced list
only takes effect with `./build.sh recomp`.

Scan snippet (Python, from `socom_pc/`): parse the ELF program headers, for every executable
segment word `w` with `w>>26 == 2` (j) whose next word is `addiu $a0,$a0,imm` (`>>16 == 0x2484`)
or nop, compute `target = ((w & 0x3ffffff) << 2) | (addr & 0xf0000000)`, and report `addr` when
it is neither a CSV `Start` nor inside any `[Start, End)` range (bisect over the sorted starts).

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
