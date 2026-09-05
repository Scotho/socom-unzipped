# Handoff — SOCOM II PC recompilation

Read this first, then `docs/STATUS.md`. This is the fast on-ramp for a new agent. Work in
**bounded steps**: one hypothesis → one build → one run → read counters → commit. Do not open more
than one deep subsystem at a time.

## The goal (unchanged)
A native SOCOM II EXE for modern PCs with controller + online play to a self-hosted server, built
by static recompilation (no emulator). Stop only once we've booted, reached a mission or an online
lobby we host. This is copyrighted-game work confined to `socom_pc/`; game assets are gitignored.

## One-paragraph state
The engine boots, the render pipeline works, and **with the pad enabled (`PS2X_SOCOM2_PAD=1`) the
game plays its intro video with sound banks loading** (2026-09-05, commit db51455). The former
"wedge at 0x32f174" was heap corruption from an unanswered `sceDbcReceiveData` (DBCMAN now answers
every libdbc RPC). The libpad2 surface the game touches is fully HLE'd (`scePad2*` + `sceVib*` stubs
in `game_overrides_socom2.cpp`, shared state `g_socom2Pad`, neutral input). Full story in
`docs/STATUS.md` (13:00 section) and `docs/research/08 §Resolution`.

## Immediate next task
Get from the intro to a **navigable main menu with real input**.

- Confirm the pad state machine advances: `FUN_002da930` goes state 0→1 once `scePad2GetButtonProfile`
  and `sceVibGetProfile` return ≥ 0 (both HLE'd now). With `PS2X_PC_SAMPLER=4` the main thread should
  cycle through the shell render dispatch, and `[DBCMAN]` traffic should stop after boot.
- Wire host input into `g_socom2Pad` (keyboard first: START/X/O/d-pad; the runner uses raylib, so
  poll `IsKeyDown` on the present path) and set the corresponding `button[]`/`axis[]` entries. The
  HLE `scePad2Read` report and `scePad2GetButtonInfo` already read that state.
- Skip/complete the intro: find the intro-movie state in `FUN_00339de0`'s selector
  `DAT_0049e888[state]` and see whether START ends it.
- Verify: `PS2X_SOCOM2_PAD=1 PS2X_FRAME_DUMP=logs/frames PS2X_PC_SAMPLER=4 ./run.sh 60` — no
  `[guest-fault]` lines, `nonBlack` stays high, and the guest reaches the menu screen.

## Parallel/secondary
- Make `PS2X_SOCOM2_PAD` default-on once the menu is reachable (the flag only exists because the
  pad path used to wedge).
- The `.ppm` from `PS2X_FRAME_DUMP` came out black for a frame the counters say was 85% non-black
  (dispFbp changed to 0x140 around then): the dump probably reads the wrong buffer when the game
  double-buffers at a non-zero FBP. Low priority; the counters are trustworthy.

## Build / run
- Runtime-only change: `./build.sh runtime` (~6-10 min). Run: `./run.sh <seconds>` or
  `dist/socom2.exe game/disc/socom2_game.elf` (put `tools/llvm-mingw/bin` on PATH).
- Changed the TOML stub list / `PS2_STUB_LIST` / recompile-time stubs → full
  `./build.sh recomp && ./build.sh runtime` (~15-20 min) because the recompiler embeds the list.
- IOP module change (dbcman.cpp) is runtime-only.

## Diagnostics already built (all env-gated, zero cost when unset)
- `PS2X_PC_SAMPLER=<s>` — live guest PC + thread table every s seconds.
- `PS2X_FRAME_DUMP=<dir>` — per-present pipeline counters (vif1/mscal/vuInsn/xgkick/gsSubmits/
  pixels/nbWrites…) + a PPM every 60 frames. This is the primary "is it drawing?" signal.
- `PS2X_TRACE_VU=1` — VU1 program execution trace + input-header dump.
- `PS2X_TRACE_FIFO=1` — VIF/GIF/DMA channel trace.
- `PS2X_SOCOM2_PAD=1` — report a connected DualShock2 (default off; needed to exercise the pad path).
- `[guest-fault]` lines (always on, first 16): a guest load/store hit a TLB miss or unaligned
  address; shows op, vaddr, pc/ra/sp, a0-a3, s0-s1, v0. The same line repeating = the scheduler is
  re-dispatching a faulting function forever (that is what the old "grind at 0x32f174" was).
- **lldb** (`tools/llvm-mingw/bin/lldb.exe`) gives real guest call chains: host frames are named
  `sub_XXXXXXXX_0xXXXXXX` / `FUN_xxxxxxxx_0xxxxxxx`, `rcx` = rdram and `rdx` = R5900Context at a
  `sub_*` entry (GPR n = `*(unsigned int*)($rdx+16*n)`), so `memory read -f x '$rcx + 0x45c3c0'`
  peeks guest memory and `watchpoint set expression -s 4 -w write -- $rcx+0xADDR` catches a guest
  writer. Batch recipe: `lldb.exe --batch -s cmds.lldb -- dist/socom2.exe game/disc/socom2_game.elf`
  with `breakpoint set -r runtime_error::runtime_error` / `run` / `bt 30` (see research 08).

## Gotchas (respect these)
- The git repo root is the parent monorepo `C:\projects`. **Never `git add -A`** — stage explicit
  `socom_pc/...` paths only. Unrelated untracked siblings exist.
- Shell/py scripts stay **LF** (`.gitattributes`); when writing files from Python use
  `newline='\n'`.
- Don't steal desktop focus or screenshot repeatedly — the user's machine is often gaming. Prefer
  logs. Pause if asked (machine under load).
- Commit as you go with specific messages; keep `docs/STATUS.md` current. Co-author line:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- If running via cron, re-arm a one-shot cron ~4 h ahead when you start, and correct its prompt to
  point at the *current* blocker (prompts go stale fast).

## Milestone map (docs/superpowers/plans/2026-09-04-implementation-plan.md)
M1 toolchain ✅ · M2 boot-to-engine ✅ · **M3 menu render + pad ← you are here** · M4 mission ·
M5 online (Horizon server already stood up, app id 10472) · M6 portable package.

## Landmarks
- Recompiler config: `recomp/socom2.toml` (stubs, mmio, patches). Generated code: `recomp/output/`.
- Game decomp/strings: `game/analysis/socom2_game.elf.decomp.c` / `.strings.txt`.
- Controller HLE: `third_party/ps2recomp/ps2xRuntime/src/lib/game_overrides_socom2.cpp`
  (`namespace ps2_stubs`, scePad2*). DBCMAN: `ps2xIOP/src/modules/dbcman.cpp`.
- Research: `docs/research/05` (code package/DNAS/MFIFO), `06` (989snd), `07` (render pipeline +
  resolution), `08` (controller/DBCMAN).
