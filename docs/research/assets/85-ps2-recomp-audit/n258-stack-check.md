# #258 check: our invocation stacks against SOCOM II's main stack (LATER row 82)

Read-only, 2026-10-03, branch sprint-17 at 61800eb5. Nothing was built or run. Paths are relative to
`third_party/ps2recomp/ps2xRuntime/` unless they say otherwise. Harry62 material was not read.

## Verdict
**No overlap today: #258's bug does not reproduce in SOCOM.** Upstream's crash happens because the main thread's
sp is 0x01FFFFF0, inside the first invocation stack. Our SetupThread puts SOCOM's main sp at 0x01F80000, which is
the bottom edge of the band the invocation stacks are carved from, and the main stack grows down away from it.
The logs on disk agree: the main thread's sp stays between 0x01F7C7E0 and 0x01F7FFxx, and the invocation stacks
never reached below 0x01FE8000. Two adjacent findings are real, though (sections 5 and 6).

## 1. Where the invocation stacks live
- Size and carve: `kInvocationStackSize = 0x4000u`, and each stack is `m_runtime.reserveAsyncCallbackStack(...)`
  [verified: src/lib/Kernel/EeScheduler.cpp:1374-1375]. The stack is memoised per (thread id, invocation depth)
  key [verified: EeScheduler.cpp:1366-1380]. A key that is used again gets the same stack, and stacks are never
  freed.
- Pool bounds: `m_asyncCallbackStackFloor = 0x01F00000u; m_asyncCallbackStackTop = PS2_RAM_SIZE;`
  [verified: include/ps2_runtime.h:571-572]. `PS2_RAM_SIZE = 32 MB = 0x02000000`
  [verified: include/runtime/ps2_memory.h:26]. When an ELF loads, the floor is reset to
  `max(kGuestHeapHardLimit = 0x01F00000, suggestedHeapBase)` and the top to `PS2_RAM_SIZE`
  [verified: src/lib/ps2_runtime.cpp:2013-2015, :167; also :588-589 at reset].
- The carve: `base = top - allocSize`, aligned; it is refused if `base < floor`. Then `m_asyncCallbackStackTop = base;
  return top - 0x10u;` [verified: ps2_runtime.cpp:2219-2240].
- So stack n (n = 1, 2, ...) spans [0x02000000 - n*0x4000, 0x02000000 - (n-1)*0x4000), and its initial sp is
  0x02000000 - (n-1)*0x4000 - 0x10. Stack 1 starts at 0x01FFFFF0, as the note says. The pool has room for at most
  64 stacks (0x100000 / 0x4000), and the lowest address any stack can reach is 0x01F00000 [inferred from the lines
  above].
- In the logs, invocation-band sp values occur only at 0x1FFFFF0, 0x1FFFFxx, 0x1FFBxxx, 0x1FF3FF0, 0x1FEFFF0 and
  0x1FEBFF0, so at most 5 stacks were carved and the lowest top was 0x01FEC000 [verified: grep over logs/, ~20k
  lines]. The guest has at most 5 threads in the sampler lines [verified: logs/parity/gate/s17_b4b/mission.game.log,
  logs/run_20260928_125710.log].

## 2. Where SOCOM's main thread stack lives
- (a) Initial sp: before the entry runs, `prepareGuestBoot` sets `r[29] = PS2_RAM_SIZE - 0x10` = 0x01FFFFF0
  [verified: ps2_runtime.cpp:2697]. That value is the "top of RAM" statement. It also explains the
  `[pc-sampler] live pc=0x180008 ... sp=0x1fffff0` header in every run log: that header prints the runtime's
  untouched boot context, not a live thread [verified: e.g. logs/parity/s11_r0004_cross1/game_A.log:90].
  research/63 #216/#217 only says the pools sit "below the main stack"
  [verified: docs/research/63-upstream-triage-2026-09-25.md:187]. It gives no address and no evidence, and the
  logs show it is wrong for SOCOM: the main stack is BELOW 0x01F80000 (see (b)).
- (b) The crt0 does not keep that sp. The entry loads `$a1 = 0 + -1` (stack = -1) and `$a2 = 0x80000` (stack_size),
  then makes syscall 0x3C SetupThread and runs `move $sp, $v0` [verified: recomp/output/entry_0x180008.cpp:292-331,
  insns 0x18014c-0x18017c]. Our SetupThread, for `stack == 0xFFFFFFFF`, returns
  `sp = PS2_RAM_SIZE - requestedSize` = 0x02000000 - 0x80000 = **0x01F80000**
  [verified: src/lib/Kernel/Syscalls/System.cpp:540-569, return at :592]. It records initialStack = that sp
  [verified: System.cpp:570-579]. This code arrived with the upstream vendor commit 87367599, so upstream has the
  same rule [verified: git log -S]. The retail kernel places sp near the TOP of the region (memsize - small frame).
  So our layout differs from the console's, and that difference is exactly what keeps the main stack clear of the
  invocation stacks [inferred: from kernel knowledge, not checked against a BIOS].
- (c) The logs: the main thread (id 1) runs at sp 0x01F7C7E0..0x01F7FEC0 (thousands of samples: 0x1f7eb50,
  0x1f7fe00, 0x1f7efe0 and so on). The lowest value seen is 0x1F7C7E0, about 14 KB deep [verified: grep over logs/].
  `[ee] SetAlarm ... caller sp=0x1f7efe0 (handler runs on a dedicated stack)` [verified:
  logs/parity/s11_r0004_cross1/game_A.log:110]. The main thread's own invocation runs on stack 1:
  `[1 pc=0x355e98 ... sp=0x1ffff90 st=0]` [verified: pc-sampler lines in run logs].
- Game threads: thread 2 sp=0x4b4560 and thread 3 sp=0x45a09x (the ELF's bss/data). Others are at 0xC4xxxx,
  0xDDxxxx and 0x1714A20 (heap). None is near 0x01F00000 [verified: log sp histogram]. I did not trace the
  CreateThread stack arguments in the decompilation; the runtime logs none [inferred: these sp values are the
  stacks].

## 3. Overlap?
- Invocation band: [0x01F00000, 0x02000000), filled downward from the top. Used to date: [0x01FE8000, 0x02000000).
  Main stack: grows down from 0x01F80000, declared size 0x80000, so the floor is 0x01F00000.
- They meet only when the 33rd distinct (thread, depth) key carves a stack whose base is below 0x01F80000
  (0x02000000 - 33*0x4000 = 0x01F7C000). That stack would cover the main stack's top 16 KB, where every main-thread
  sp seen in the logs sits. The logs show 5 keys, and 5 threads would need nesting depth 7 or more to get there
  [inferred]. **Today the margin is 27 stacks. Overlap is possible in principle, but nothing on disk shows it.**
- Upstream separates them by pure luck of the stack == -1 rule. If anyone ever made SetupThread kernel-accurate
  (sp near 0x01FFFxxx), #258 would appear at once: main sp would equal stack 1's top [inferred].

## 4. KNOWN rows and issues; a test
- docs/KNOWN.md and docs/HAZARDS.md have no row on clobbered registers, stack corruption or a bad `$ra`
  [verified: grep]. The open issues have no stack/clobber/corrupt/callback title. The nearest is #34 (online freeze,
  paused console peer) [verified: gh issue list].
- Existing coverage: ps2xTest/src/ps2_gs_tests.cpp:5498-5502 checks only that a callback sp is `>= 0x01F00000` and
  `!= caller sp`. ps2_runtime_kernel_tests.cpp:1584-1624 checks SetupThread alignment and metadata.
  [verified]
- A test that settles it with no game run (in ps2_runtime_kernel_tests.cpp): call SetupThread(gp, -1, 0x80000)
  (SOCOM's arguments from entry_0x180008.cpp), take sp = v0, then carve invocation stacks until
  reserveAsyncCallbackStack returns 0. Assert that every returned [top-0x4000+0x10, top] lies in
  [sp, 0x02000000), or that the carve stops at sp. Today that assertion fails from the 33rd stack on: it pins the
  latent overlap, and the fix is to raise the floor to SetupThread's sp. A second assertion, that stack 1's top is
  not the main sp, pins #258 itself. Also add a log line (or replay) when the stack count passes, say, 16.

## 5. Adjacent finding A: the main stack already overflows its 0x80000 into the heap and the runtime pools
- FUN_001c6570 (the loading-screen image path; callers LoadGameCodeFromMemcard (at 0x1c5b30), sub_001C4CC0,
  FUN_001c6390) opens a frame of 0xA00D0 bytes (`lui $at,0xFFF5; ori 0xFF30; addu $sp,$sp,$at`). It hands
  `sp+0x70` to func_1A8300(a2=0x28000) and to func_1A2848 as an image buffer, with a GIF packet at sp+0xA0070
  [verified: recomp/output_r0004/FUN_001c6570_0x1c6570.cpp insns 0x1c6570-0x1c66d4; recomp/output has the same
  function]. The log shows it: `threads: [1 pc=0x1c6730 ... sp=0x1edfe00]` in the first 0.75 s of boot
  [verified: logs/parity/s11_r0004_cross1/game_A.log:90-107; also s17_b4b/mission.game.log and the
  persona_card_proof logs].
- So the main thread's frame spans 0x01EDFE00..0x01F7FED0. That range covers the guest heap's top 128 KB (the heap
  ends at 0x01F00000, System.cpp:693) and every runtime pool: kRpcPacketPoolBase 0x01F00000, kRpcServerPoolBase
  0x01F10000, kTlsPoolBase 0x01F20000, kBootModePoolBase 0x01F30000
  [verified: src/lib/Kernel/Syscalls/Helpers/State.h:277-290]. Whether the image buffer is written over a live
  pool entry (an RPC bound during boot, for example) is unproven [inferred risk]. On the console, a top-placed
  stack would put the same frame at about 0x01F5Fxxx, above the pools [inferred]. This is a stronger candidate than
  #258 itself.

## 6. Adjacent finding B: the memo is not cleared on a guest restart
- `m_invocationStackTops` is touched only at EeScheduler.cpp:1369-1380. `EeScheduler::reset` (:94-160) clears
  threads, handlers and events but not this map, while an ELF reload resets the carve top to 0x02000000
  (ps2_runtime.cpp:2015) [verified]. After a Sprint 17 Q2 LoadExecPS2 restart, a new (thread, depth) key re-carves
  0x01FFFFF0, which is already cached for an old key. Two contexts can then share one 16 KB stack, and a nested
  pair on two threads would clobber each other [inferred]. The fix is one line (clear the map in reset). A unit
  test: reset, carve key A, reset again, carve key B != A, and assert that the tops differ.
