# 29 — Online freeze: what the 8c samples say about the two stall shapes (zero-run analysis)

Sprint 6 Task 3 Step 1½. Read-only: no launch was made for this note. Inputs: `tools_py/parity/freeze_trace.py`
(its docstring carries the measured 8c table), `logs/run_[AB]_20260913_132843.log`, the Ghidra decomp
`game/analysis/socom2_game.elf.decomp.c`, `recomp/output/*.cpp`, and the runtime under
`third_party/ps2recomp/ps2xRuntime/`. Every claim is `[verified]` (file:line or the grep that shows it) or
`[inference]`. KNOWN.md §4 "Online instances freeze for 3–17 s under host load" is the defect.

## 0. Condition sentences (both [inference] until Task 3 Step 2's two launches settle them)

- **Shape 1 (thread 1 parked at 0x3b00a4, st=2 wait=4, running=0; A 500.7–514.1 s, B 621.0–638.3 s):** the EE
  executor is idle with the main thread inside `sceGsSyncV`'s VSync wait, and the VBlankStart it needs is not
  delivered for 5–17 s. The runtime path that can hold a VBlankStart that long is `GuestFrameBoundary()` — the GS
  back-pressure wait, whose cap bounds only time *without* GL-thread progress, so a GL thread that is alive but
  slow under host load keeps the guest waiting indefinitely. The 8c logs cannot confirm or refute this (no
  `PS2X_GS_STATS`); `[gs-gl stats] … waits= wait_ms= pending=` (and a `bp_waiters` field, §4) over the window decide
  between "back-pressure" (host load, working as designed) and "scheduler oversleep" (a runtime wait to fix).
- **Shape 2 (thread 1 st=0 RUNNING, live pc pinned at 0x350d90 ra 0x33aa1c; A 547.9–557.8 s, B 615.2–618.5 s):**
  the main thread is not spinning in guest code; it is inside a **host-blocking libnetb stub** (the
  `waitReadable` poll/sleep loop, 10 s cap for `timeout < 0`) called from the network library's semaphore
  wrapper, so no guest instruction runs, the guest clock stands, and both the thread table and the "live pc" are
  stale by construction. A's 9.93 s ≈ the 10 s cap; B's 3.3 s ended when data arrived. This is the KNOWN.md
  residual (1) ("blocking `sceInetRecv` with a timeout"), but the residual is 3–10 s, not one frame.

## 1. Shape 1 — what `st=2 wait=4` is, where 0x3b00a4 is, what it waits on

- `st` is `EeThreadStatus` (0 Running, 1 Ready, **2 Waiting**, 3 WaitingSuspended, 4 Suspended, 5 Dormant);
  `wait` is `EeWaitReason` (0 None, 1 Sleep, 2 Semaphore, 3 EventFlag, **4 VSync**, 5 External, 6 Mpeg); the
  `/<id>` after it is `waitObjectId`, which is 0 for every reason but Semaphore/EventFlag — so `wait=4/0` carries
  no object id [verified: `include/runtime/ee_scheduler.h:25-44`; `Kernel/EeScheduler.cpp` `waitObjectId`
  (`default: return 0`); the print at `game_overrides_socom2.cpp:650-651`].
- **0x3b00a4 is the return address of `jal 0x1a2110` (`sceGsSyncV`) inside `FUN_003aff30`, the frame-flip
  routine** [verified: `recomp/output/FUN_003aff30_0x3aff30.cpp:406-421` (`0x3b009c: jal func_1A2110`, `0x3b00a4:
  sltu $v1,$zero,$v0`); decomp line 304735 `FUN_003aff30`: reads `REG_RCNT0_COUNT` for the frame dt, `lVar1 =
  FUN_001a2110(0)`, then sets DISPFB/PMODE and kicks the VIF1 flip]. `sceGsSyncV@0x001A2110` is bound to the
  runtime stub [verified: `recomp/socom2.toml:120`, also `VSync@0x001A3FB0`/`VSync2@0x001A4040`, the INTC_STAT
  poll loops the decomp shows at lines 23889/`FUN_001a4040`]. The stub is
  `sceGsSyncV → ps2_syscalls::WaitVSyncTick → EeScheduler::waitVSync(currentVSyncTick(), …)` [verified:
  `Kernel/Stubs/GS.cpp:1303-1310`, `Kernel/Syscalls/Interrupt.cpp:91-95`, `EeScheduler.cpp` `waitVSync` →
  `blockCurrent(EeWaitState{EeWaitReason::VSync, …})`]. So thread 1's pc reads the post-call address because the
  syscall unwinds to the scheduler with the return pc saved; it is **not** a semaphore and **not** a sceInet call.
- The wait completes only in `processEvent(VBlankStart) → completeVSync(m_vsyncTick)` [verified:
  `EeScheduler.cpp:2030-2050`, `completeVSync` at 1427-1449]. A VBlankStart is *due* only when both cycle-due
  (`deadlineCycle <= m_eeCycle`) and host-due (`hostDeadline <= now`) [verified: `processDueDeadlines`,
  `EeScheduler.cpp:1902-1950`], and before it is processed the executor calls
  `m_runtime.gs().guestFrameBoundary()` and excludes that time from the guest clock [verified:
  `EeScheduler.cpp:1976-2011`, R35/R41/R54 comment]. With `running=0` on every sample the executor is in one of:
  (a) `GuestFrameBoundary()` — `GsFrameBackpressure::frameRecorded()` waits while `> N` (default 3) frames are
  recorded but not replayed; the 2 s cap bounds time **without consumer progress**; `consumerProgress()` is
  bumped per replayed command chunk, so "a live GL thread replaying a big batch keeps the recorder waiting past
  the cap" [verified: `include/runtime/gs/gs_frame_backpressure.h:16-24`, `gs_frame_backpressure.cpp:69-71`,
  heartbeats at `gs_gl_backend.cpp:1040,1172,1185`]; (b) `waitForEvent()` — sleeps to the *later* of the host
  deadline and `now + (deadlineCycle − m_eeCycle)` [verified: `EeScheduler.cpp:2160-2217`]; (c) the pacing wait in
  `processDueDeadlines` [verified: 1931]; (d) starvation of the executor thread by the host. (b)/(c) are bounded
  by one VBlank period unless `deadlineCycle − m_eeCycle` is large, which the code does not let happen on the
  processed chain [inference from 1902-1950]; only (a) is unbounded by design. Hence the §0 sentence.
- **What the 8c log can already distinguish: nothing about (a).** Both logs have 0 `[gs-gl stats]` lines and 0
  `[gs-gl] back-pressure:` cap-hit lines (`grep -c` on each; the only `[gs-gl]` lines are the three init lines at
  2, 3, 59) — 8c was launched by `scripts/parity/online_match_frostfire.sh:41`, whose env has no `PS2X_GS_STATS`
  (`ladder_frostfire.sh:143` has it) [verified]. The absence of a cap-hit line only says the GL thread was never
  silent for 2 s — consistent with both "alive-but-slow" and "no wait at all". What the log does carry:
  `[hle-stats]` tables every 30 s with the cumulative `sceGsSyncV` call count — in the rounds both instances run
  ~11–12 frames/s (A: 480 s→22975, 510 s→23300, 540 s→23655; B: 600 s→24310, 630 s→24545, 660 s→24806), against
  ~59/s in the lobby [verified: awk over `0x001a2110 sceGsSyncV` rows]. ~12 guest frames/s is the replay rate R35
  measured for the GL thread in gameplay ("~14 frames/s"), which is the signature of the guest being paced by
  replay rather than by its own cost [inference]. Memory flat (KNOWN §4) is what a *bounded* backlog looks like,
  not evidence against back-pressure [inference].

## 2. Shape 2 — 0x350d90, 0x33aa1c, and why "pinned" is not "spinning"

- `FUN_00350d90` is a ten-instruction leaf: it flips the scratchpad double-buffer index and returns
  `0x70000000 + idx*0x1f30` — no loop, no memory wait [verified: decomp line 250176; recomp
  `FUN_00350d90_0x350d90.cpp:23-166`, straight-line to `jr $ra`]. `0x33aa1c` is the return of the 5th
  `jal func_350D90` in `sub_00339DE0` (`0x33aa14`), the frame's render-submit routine: it allocates SPR packets
  via `FUN_00350d90` and kicks them with `FUN_00350ab0(…,3)` ten times per pass [verified:
  `sub_00339DE0_0x339de0.cpp:3416`; decomp lines 236802-237221]. B's 495.66 window (`live pc 0x33aab0`) is a
  branch target in the same routine [verified: `sub_00339DE0_0x339de0.cpp:3557`]. Nothing here can spin for 10 s.
- **The "live pc" is not live.** `runtime.cpu()` returns `m_cpuContext` [verified: `include/ps2_runtime.h:443`],
  which the scheduler refreshes only by `copyMainContextToRuntime()` every `kDebugPublishDispatchInterval = 4096`
  dispatch iterations of the run loop [verified: `EeScheduler.cpp:41`, run loop 225-234, `copyMainContextToRuntime`
  = `m_runtime.m_cpuContext = main->context`]. A pinned value means the executor did not come back through the
  dispatch loop 4096 times in 10 s — i.e. it was not executing guest code.
- **The thread table is stale for the same reason.** `publishSnapshot()` returns early unless `m_eeCycle` advanced
  ≥ 50 ms of *guest* time since the last publish [verified: `EeScheduler.cpp:1580-1587`]; the guest cycle clock
  advances only from host gaps measured in `accountCycles`, which runs from executing guest code
  [verified: 415-482]. When no guest instruction runs, neither the table nor the live pc can change.
- **Where thread 1 actually is.** In every shape-2 row thread 1 reads `pc=0x1a3b68 ra=0x639480 sp=0x1f7fc00
  st=0` (A rows 2181-2223, B rows 2463-2464) [verified: log lines 34129-34248, 42257-42293]. `0x1a3b68` is
  `WaitSema+8` (`recomp/output/WaitSema_0x1a3b60.cpp`) and `0x639480` is the return inside `FUN_00639468`, the
  network library's mutex wrapper (`WaitSema(*(p+0xc))`; siblings `FUN_00639498` PollSema, `FUN_00639500`
  SignalSema, `FUN_00639530` GetThreadId; `FUN_00635898` classifies sceInet error codes) [verified: decomp
  549596-549660, 546812]. So the last published state was "main thread just woke from the libnetb lock" — and then
  it entered a stub that blocks the executor thread: `socom2_libnetb::call` `case 4 sceInetRecv` / `case 0xd
  sceInetRecvFrom` call `waitReadable(c, timeout)` when `timeout != 0`, a `poll(fd,0)` + `sleep_for(2 ms)` loop up to
  `timeoutMs`, **10 000 ms when `timeout < 0`**; `doOpen` has the same 10 s cap [verified:
  `socom2_libnetb.cpp:258-284, 302-317, 348-364, 426-436`; dispatched from `game_overrides_socom2.cpp:147`]. This
  loop adds nothing to `ps2GuestClockExcludedNs()` (grep -a: no hit in `socom2_libnetb.cpp`/`socom2_hostnet.cpp`)
  [verified]. Thread 2 is asleep (`wait=1`), thread 4 is the SIF/CD RPC pump waiting on semaphore 11
  (`FUN_0030c8e0`: `WaitSema; FUN_0030c910` — sceSif calls) [verified: decomp 209487; log rows], so neither is
  the net thread; the net work runs on the main thread.
- **Stale rows vs real spin, per instance.** A 547.90–557.83 s: 9.93 s with no clock movement, then +0.05 —
  matches one `waitReadable` at the 10 s cap returning `kErrTimeout` [inference]. B 615.17–618.47 s: 3.30 s, then
  the guest clock jumps +3.4 s — matches data arriving after 3.3 s and the un-excluded host gap being converted
  to guest cycles in one lump on the next `accountCycles` (`ns − excluded → elapsed cycles`, no cap unless
  `PS2X_CLOCK_CAP_MS`) so T0 and the game's dt jump [verified mechanism `EeScheduler.cpp:438-455`; the fit is
  inference]. Why A's clock did not also jump ~10 s is open (a game-side dt clamp, or the round clock not being
  T0-driven) — `PS2X_CLOCK_TRACE` (§3) shows whether `eeCycle` jumped. Both fit "stale rows while the executor
  is blocked in host code"; neither fits a guest spin. B's row 2450 (615.17 s) shows the hand-over: thread table
  still "VSync wait, running=0" with the live pc already 0x350d90 [verified: log line 42231].

## 3. What exists today to separate host load from a runtime wait in ONE launch

| Knob / instrument | What it prints, where | Limits |
|---|---|---|
| `PS2X_PC_SAMPLER=<s>` | `[pc-sampler] live pc/ra/sp running= threads:[id pc ra sp st wait/id]` then `[peek]` [`game_overrides_socom2.cpp:635-652`] | no host stamp; "live" = 4096-dispatch copy; table rate-limited by guest cycles (§2) |
| `PS2X_GS_STATS=1` | `[gs-gl stats] elapsed=…(fps)`, `… backpressure N= guest_frames= waits= wait_ms= timeouts= skipped= unlatched= pending=` every 60 host presents, stderr (captured in the run log — the `[gs-gl] initialised` line is there) [`gs_gl_backend.cpp:1322-1341`] | cadence is presents, so a frozen GL thread prints nothing — the gap is itself the signal; `takeStats()` clears |
| `[gs-gl] back-pressure: replay made no progress within 2000 ms …` | printed on a cap hit, ≤ 1/10 s, always on [`gs_gl_backend.cpp:1016-1027`] | absent in 8c = no 2 s silence, not "no wait" |
| `PS2X_CLOCK_TRACE=1` | `[clock] host=… eeCycle=… T0= mode= nextDeadline= vsyncTick= checkpoints=` once per host second from `accountCycles` [`EeScheduler.cpp:457-475`] | only while guest code runs — a hole in it = shape 2; `eeCycle` jump after = the lump |
| `PS2X_SOCOM2_NET_TRACE=1` | `[socom2/libnetb] …` per call [`socom2_libnetb.cpp:73,181-184`] | verbose; check it stamps the fno/timeout you need before relying on it |
| `PS2X_HLE_STATS=1` (on in 8c) | cumulative stub calls every 30 s (`sceGsSyncV` = frames) | 30 s grain; libnetb calls are not in the table (0 rows match `Inet|libnetb`) |
| `run_detached.sh` CPU sampler | `<marker>.cpu.csv`: ISO timestamp, total %, `socom2*=pct` per process, 1 row/s [`scripts/run_detached.sh:66-88`] | joins to the run log only through `[call]` host anchors (`freeze_trace` does this) |
| `PS2X_GS_MAX_PENDING_FRAMES=0` | unbounded backlog (pre-R35) [`gs_gl_backend.cpp:611`] | an A/B knob for shape 1, not an instrument; memory grows |
| `PS2X_CLOCK_CAP_MS=<ms>` | caps one accounting gap [`EeScheduler.cpp:441-448`] | mitigation for the lump, not for the block |

**Exact env for Task 3 Step 2's two launches** (same exe sha; the base block is `online_match_frostfire.sh:41`,
or use `ladder_frostfire.sh`, which already carries `PS2X_GS_STATS=1`; extra `export`s before the script inherit):

```
export PS2X_PC_SAMPLER=0.25 PS2X_GS_STATS=1 PS2X_CLOCK_TRACE=1 PS2X_HLE_STATS=1 \
       PS2X_CALL_TRACE_EVERY=10 PS2X_CALL_TRACE="0x553dc0:MoveScale,0x30cd80:NetIdle" \
       PS2X_PEEK="0x416054:3,…(the script's spec, unchanged)…"     # + PS2X_SOCOM2_NET_TRACE=1 on the B side only
# launch 1 (quiet host), launch 2 with the plan's load generator started after the lobby forms:
#   powershell -c "1..4 | % { Start-Job { while($true){} } }"   … stopped with Get-Job | Remove-Job -Force
# both through scripts/run_detached.sh --purpose "launch: freeze A/B" so <marker>.cpu.csv exists (RUN_CPU_SAMPLER=1).
```

Read-out per window with today's fields: `[gs-gl stats] waits/wait_ms/pending` rising while the clock stands →
shape 1 is back-pressure (host load); `pending ≤ 3` and no waits with thread 1 in VSync → a scheduler oversleep;
a hole in `[clock]` lines with thread 1 at `ra=0x639480` → shape 2 (libnetb block).

## 4. What the sampler must additionally print (plan Task 3 Step 2), and where each value lives

All in the sampler thread at `game_overrides_socom2.cpp:640-652`, appended to the `[pc-sampler]` line:

1. **Host time** `t=<s>`: `std::chrono::steady_clock::now()` minus a sampler epoch — lets `freeze_trace` drop
   the `[call]`-anchor interpolation.
2. **`vsync=`**: `runtime.eeScheduler().currentVSyncTick()` [`ee_scheduler.h:333`, public, used by
   `Interrupt.cpp:94`]. Flat across samples = no VBlankStart delivered (shape 1); rising = frames are flowing.
3. **`ee=<guest s>`** and **`seq=`**: `snap.eeCycle / kEeClockHz` and `snap.sequence` from the `EeKernelSnapshot`
   the sampler already takes [`ee_scheduler.h:216-225`]. A repeated `seq` marks the thread table as stale, so
   shape-2 rows stop reading as "RUNNING at 0x350d90".
4. **`dpc=`**: `m_debugPc` (stored on every dispatch iteration, `EeScheduler.cpp:232`; a `PS2Runtime` member) —
   the per-dispatch pc, to replace the 4096-dispatch `m_cpuContext.pc`. Needs an accessor on `PS2Runtime`.
5. **`idle=`**: `runtime.eeScheduler().idleWaitCount()` [`ee_scheduler.h:335`] — climbing with `vsync` flat =
   the executor is in `waitForEvent`; flat with `vsync` flat = it is blocked elsewhere (`GuestFrameBoundary` or a stub).
6. **`bp_pending=` / `bp_waiters=`**: `GsFrameBackpressure::pendingFrames()` and `waiters()`
   [`gs_frame_backpressure.h:72-73`]. `m_backpressure` is private to `GSGlBackend` [`gs_gl_backend.h:274`], so
   add `virtual uint64_t PendingGuestFrames() const { return 0; }` / `virtual uint32_t BackpressureWaiters() const`
   on `GSBackend` [`gs_backend.h:43`] and passthroughs on `GSFrontend` [`gs_frontend.h:159`]. `bp_waiters=1`
   during a shape-1 window is the direct answer.
7. **`bp_wait_ms=` cumulative**: `Stats::waitMs` is only reachable through `takeStats()`, which clears and is
   owned by the 60-present printer [`gs_gl_backend.cpp:1337`]; a sampler reading it would race that printer. Add a
   non-clearing `std::atomic<uint64_t> m_waitNsTotal` incremented beside `m_stats.waitMs`
   [`gs_frame_backpressure.cpp:94`] with an accessor, and print it cumulative (delta per sample = wait in the sample).
8. **`net_wait=`**: a `std::atomic<int>` "inside waitReadable/doOpen" flag plus cumulative ms in
   `socom2_libnetb.cpp:258-317`, exported like `testResetKnobs()`; also worth adding the wait's own host time to
   `ps2GuestClockExcludedNs()` there once the A/B says the lump is harmful — that is the fix candidate for shape 2,
   not part of the instrument.

With 1–8, one line per sample answers both §0 sentences without a second launch: shape 1 = `vsync` flat,
`bp_waiters=1`, `bp_wait_ms` climbing (host load) versus `bp_waiters=0`, `idle` climbing (runtime oversleep);
shape 2 = `seq` frozen, `dpc` frozen, `net_wait=1`.
