# Handoff — SOCOM II PC recompilation

Read this first, then `docs/STATUS.md`. This is the fast on-ramp for a new agent. Work in
**bounded steps**: one hypothesis → one build → one run → read counters → commit. Do not open more
than one deep subsystem at a time.

## The goal (unchanged)
A native SOCOM II EXE for modern PCs with controller + online play to a self-hosted server, built
by static recompilation (no emulator). Stop only once we've booted, reached a mission or an online
lobby we host. This is copyrighted-game work confined to `socom_pc/`; game assets are gitignored.

## One-paragraph state
The engine boots and runs its shell/main loop. The **render pipeline is proven working** (GS, VU1,
XGKICK all function) — the game is simply idle, feeding empty display lists because it hasn't
reached an interactive screen. The gate to visible content is **game-state progression**, and the
next concrete lever is the **controller path**: with the pad reported connected (`PS2X_SOCOM2_PAD=1`)
the game runs Sony's proprietary libdbc/DBCMAN DualShock2 configuration and wedges on
`rpc=0x8000131a` (sceDbcReceiveData) at guest 0x32f174. Full evidence in `docs/research/07`
(§Resolution) and `docs/research/08`.

## Immediate next task
Implement the DBCMAN DS2 config handshake in `third_party/ps2recomp/ps2xIOP/src/modules/dbcman.cpp`
so the game leaves configuration and reaches the shell menu.

- The client wrappers and their RPC numbers + reply-buffer offsets (in the 0x1d62c0 buffer) are
  decoded in `docs/research/08-controller-and-dbcman.md`. Key ones: 0x1301 CreateSocket (result at
  buffer+0x24), 0x1303 GetDepNumber (+0x04), 0x1317 GetDeviceStatus (+0x04), 0x131a ReceiveData
  (status +0x20c, count +0x08, data +0x0c).
- **Start cheap:** make each RPC write a *benign success* reply (valid socket, one device, ready
  status, 0 bytes received) and see whether the config loop completes. The DBCMAN stub already
  logs unknown RPCs — extend `handleRpc` to write the fields above.
- If the game keeps looping (needs a real DS2 command/response handshake), reverse it further; the
  authoritative source is `game/disc/RUN/IRX/DBCMAN.IRX` (not yet decompiled).
- Verify: `PS2X_SOCOM2_PAD=1 PS2X_FRAME_DUMP=logs/frames PS2X_PC_SAMPLER=4 ./run.sh 40`. Success =
  the main thread leaves 0x32f174 AND the `[frame-dump]` line shows `xgkick`/`nbWrites` rising
  (content is drawing).

## Parallel/secondary
The game is idle even with the pad off, so the controller may not be the *only* gate. Trace
`FUN_00339de0`'s screen selector `DAT_0049e888[state]` to find what else (memory-card check, a
timer, an intro trigger) keeps it on the idle screen. Only chase this if the DBCMAN work stalls.

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
