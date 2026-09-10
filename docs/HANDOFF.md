>>> The 2026-09-08 data-loss incident is RESOLVED (game/ and tools/ restored, see STATUS). The
>>> section below is the current pick-up; everything under "The vision" is background.

# Handoff — SOCOM II PC recompilation (2026-09-09 03:40)

## START HERE (2026-09-10 17:45) — goal 1 in gameplay on our exe; the section below is the previous pick-up (recipes still current)

**State (all on `develop`, last 841a6fc/7bf0160; STATUS 2026-09-10 17:40):**
- Build: VU1 register-file work landed (841a6fc). Gates on it: title clean (vr_title), main menu
  59 syncv/s. gameplay_probe.txt now survives the controller-config "save to memory card?" prompt
  (ifref step, 7bf0160) — re-run it once for the mission gate on this build.
- **Two instances of our exe are in an online match in gameplay** (logs/parity/ours_match_play5:
  HUD, round timer, compass, A fires, B moves; 19-21 syncv/s each with both running). Recipe:
  Horizon up (`server/start-servers.ps1`), then a detached script like logs/run_match_play5.sh
  (PowerShell `Start-Process bash.exe <script>` — the harness kills long background shells) and
  wait for its `.done` marker; the driver's stdout is block-buffered until exit.
- Known: A's "walk forward" bursts walk it into a wall (identical A_play frames); B moves. The
  driver's "B_TIMEOUT waiting for persona" line was spurious (B continued).

**Open items, in order, each with its first step:**
0. **THE ONLINE MATCH IS FROZEN AT ROUND START (STATUS 2026-09-10 20:10).** Both instances sit at
   "STARTING ROUND 1 OF 11": only camera pitch (RY), fire and stance respond; RX/LX/LY do nothing.
   Peer UDP (A 3658 <-> B 3660) is one 22/32-byte packet per second each way = a handshake that
   never completes; a running match streams tens of packets/s. Evidence tools: run with
   `PS2X_SOCOM2_NET_TRACE=1` (udp send/recv counters, `udp peer send/recv` hex of the first 16
   peer packets), `PS2X_SOCOM2_INPUT_FILE` pad injection (drivers write logs/pad_A.txt/pad_B.txt),
   `PS2X_SOCOM2_SERVER=192.168.2.10` (else the exe advertises 127.0.0.1 as its own address).
   **Decoded 20:35 (STATUS):** the peer packets are the game's own 22-byte reliable channel
   (`00 01 0a 00 | 0 | 0 | T 00 02 00 | S 00 Q 00 | P 00`, T 0x81/0x82/0x89, S sender index,
   Q sequence, P payload 0x0a/0x05/0x0c), acked both ways at 1/s: the transport is alive, no
   SCERT framing, no crypto -> the freeze is game logic above it (round "go" / local control
   enable never reached). First step now: trace the guest callers of the libnetb_ex UDP
   send/recv (FUN_00247fe8 / exUdpRecv) with PS2X_CALL_TRACE(+_DUMP) on BOTH instances to read
   the P2P state machine; then the actor/controller flag that ignores LX/LY/RX online (the pad
   floats at pad+0x210.. are fine: RY works). Superseded hypotheses, kept for the record:
   (1) both instances share the fixed RSA keypair (socom2_rsa_key.h,
   recomp stub socom2_RsaGenerateKeyPair) and the peer SCERT handshake fails with identical keys
   -> give B a second key (env-selected) and rerun; (2) the peer connect packet carries an
   address/port the receiver checks against the DME NetAddress list (exUdpRecv addrOut/portOut
   layout); (3) a libnetb feature on UDP sockets (poll/available/flags) answered wrongly. Decode
   the hex with the SCERT ids (CLIENT_CONNECT_AUX_UDP 0x16, SERVER_CONNECT_ACCEPT_AUX_UDP 0x19,
   CLIENT_HELLO 0x24, SERVER_HELLO 0x25, UDP_APP 0x0c, ECHO 0x05) from RT.Common/Types.cs.
   The PCSX2 golden match is the same frozen state (movement never verified there; tools/pcsx2_b
   is gone). A run = `logs/run_match_probe10.sh` pattern (detached, ~12 min, `.done` marker).
1. **First kill / round end (the user's acceptance test)** — after item 0. Running/next: `python -m
   tools_py.parity.online_match_ours --existing-b --same-team --hold 40 --sweep 24` with
   `PS2X_PC_SAMPLER=1 PS2X_PEEK=0x416054:3` on both instances (logs/run_match_sweep1.sh, output
   logs/parity/ours_match_sweep1, drive log drive_match_sweep1.txt). B stays on SEALs so both
   spawn together; A turns in place firing a burst per step. Read: the two `[peek] @416054`
   position rows (one per second per instance, newest two logs/run_*.log), A_sweep*/B_sweep*
   frames (B's death/respawn screen), and the DME log slice from the `dme0=` line count. If no
   kill: aim needs the relative bearing — compute it from the two positions and turn A by
   timed L/J holds (calibrate degrees per second of `hold L` from the compass in the frames);
   if the round cannot start with one team only, fall back to `--play` with position-driven
   steering toward B.
2. Frame rate with two instances (19-21 each; 36-42 single): the two game threads + two GL
   threads share the host. Profile one instance with `PS2X_HOST_PROF=1 PS2X_HOST_PROF_STACKS=1`
   during a match; next levers are in STATUS 2026-09-09 13:30 (sceMpegDemuxPssRing, guest malloc).
3. **Black squares on the opening cutscene** (user report 2026-09-10 18:45, STATUS 18:45): 16x16
   blocks at the frame edges of the intro movie / location cinematic and the title's movie
   background. Start from the MPEG/IPU decode or the 16x16-block upload (STATUS 2026-09-09 12:10);
   compare a PS2X_GS_DUMP_DISPLAY dump with a PCSX2 burst capture of the same seconds.
4. Mission gate on this build (gameplay_probe.txt) and the items below (ground height, parity
   report).

## START HERE (2026-09-09 03:40) — state after the overnight loop; the section below it is the previous pick-up and still describes the run recipes

**Landed tonight (all on `develop`, last 0a154aa; read STATUS 2026-09-09 entries top-down):**
- 47ffc73 **VU0 macro-mode FMAC ops now set the MAC/STATUS flags** (they never did; only CTC2
  wrote them) and VCLIP uses the manual's bit order against |w|. The EE's camera-frustum box
  test (FUN_00290c30) read those flags, called everything "fully inside" and sent near objects
  through the no-clip VU1 list (word 8 of FUN_003b5f20's command list instead of word 2). The
  giant sky polygons are gone; the mission intro renders like the golden run (mission_s16,
  dump run s17: 0/3164 vertices with q<0, was 108/1878). Lesson: when the EE chooses a render
  path, check the VU0 flag registers (CFC2 of STATUS/MAC/CLIP) before the VU1 side.
- 48e285d/dc99469 diagnostics: `PS2X_CALL_TRACE_DUMP="Name:a1[+off][*]:words"` prints guest
  words behind a traced call's argument after it returns; `PS2X_GS_TRACE_PAGES=0xPAGE:count`
  logs every VRAM-page event in the GL backend; `PS2X_GIF_TRACE=<n>` logs GIF submissions;
  `tools_py/parity/probe_poll.py` and `state_poll.py` poll PCSX2 memory at a savestate over
  PINE; `tools_py/parity/p2s_extract.py` pulls eeMemory.bin/Scratchpad.bin out of a .p2s.
  New PCSX2 savestate slot 6 = the title screen (logs/parity/title_pcsx2.rdram is its EE
  memory); slot 8 = spawn, slot 7 = post-load.

**Open items, in order, each with its first step:**
1. **DONE 2026-09-09 02:15 — title labels** (STATUS 02:15): VIF1 now stalls on i-bit VIFcodes until
   FBRST.STC and every MMIO store width drains pending IRQs; the texture-set marker protocol
   (0x4887c0 render queue, FUN_0033c010 handler) is in sync with the console. Verify the title
   (s00..s22 of a `scripts/parity/title_menu.txt` run) after any VIF/DMA/scheduler change. The
   console reference for GS ordering is a PCSX2 GS dump (`tools_py/parity/gsdump_capture.py
   --slot 21`, `tools_py/gsdump_timeline.py`); PCSX2 savestate 6 is SELECT RANK, 21 is the main
   menu, 22 the online login. Do not trust the 03:20 "console has no movie set" conclusions.
0. **PLAYABLE FIRST MISSION reached 2026-09-09 13:30** (STATUS 13:30): scripts/parity/gameplay_probe.txt
   walks, fires and turns in Albania 5-1 at 36-42 frames/s with the game reacting. NEXT for the
   user's acceptance test (two-instance online match ended by a shot or grenade): (a) add the
   hold/burst steps to tools_py/parity/online_match_ours.py (A hosts, B joins; both spawn; A walks
   to B and fires until B's death registers), (b) read the kill/round state: the Horizon DME world
   log on the server side (server/logs) or guest memory — find the per-player health/kills record
   near the player actor (vtable 0x6691a0; STATUS 01:30 lists the mover fields), (c) capture the
   round-end screens on both instances. Use PS2X_SOCOM2_INPUT_TRACE=1 to prove the inputs.
1a. **DONE 2026-09-09 12:10 — menu-video strip before the briefing** (STATUS 12:10): the GL
   backend re-reads only the exact uploaded rectangle from the shadow VRAM (dirty rects + band
   mask). Any future "stale content reappears" report: look at refreshRenderTargetsFromShadow /
   refreshDirtyRows first; tools are PS2X_GS_TRACE_DIRTY, PS2X_GS_PROBE, PS2X_GS_DUMP_DISPLAY.
1b. **Frame rate (STATUS 13:30): mission gameplay 30-42 frames/s, menus/lobby 59.** Landed today:
   VU1 fast path + microcode recompiler (900-dump golden, `PS2X_VU1_GEN=0` / `PS2X_VU1_FAST=0` /
   `PS2X_VU0_FAST=0` revert layers), scheduler clock batching and idle fast paths, GS row-span
   uploads/decodes, copy-free arbiter, GL command-buffer pooling, render targets sampled directly
   (`PS2X_GS_RT_TEXTURE=0` reverts). Measure: `PS2X_VU_STATS=1 PS2X_VU1_BAILHIST=1` +
   `python tools_py/vu1stats_summary.py` (syncv/s = frames/s; compare phases by VU1 cycles/frame).
   Profile: `PS2X_HOST_PROF=1 PS2X_HOST_PROF_STACKS=1` (+ `_MAIN=1` for the GL thread) and
   `tools_py/hostprof_stacks.py`. Gates after any GS change: title_menu.txt (labels + movie),
   transition_probe.txt + `tools_py/parity/black_rows.py` (rows 396-447 black), mission diag sheet
   (HUD crisp). Next levers: VU1 register file in host registers (VU1 ~20% of the game thread at
   ~7 ns/cycle), sceMpegDemuxPssRing on the game thread (~5% in the mission), guest malloc
   emulation (unordered_map, ~2%).
2. **Ground height** (STATUS 01:30/02:10): the vertical collision probe is identical to PCSX2's
   (hit y=-146.371, same normal); the actor rests 14.7 above it on ours vs 20.1 on the console.
   Diff of the player's mover object (vtable 0x6694b0; actor vtable 0x6691a0 +0xc0) vs PCSX2's:
   mover +0x5c = 4.0 vs 6.3338, +0x70..+0x7c differ, actor +0x10 state 0x00080502 vs 0x2,
   actor +0x2bc.. holds a cached ground point on ours. Next: trace the mover's update method
   (writer of mover+0x90.y) with PS2X_CALL_TRACE_DUMP on the mover object; the s16 peek rows
   show the actor placed at the console height (-125.97) then dropping to -135.9 and settling
   at -131.7, i.e. a gravity/step overshoot, not a placement error.
3. **Frame rate**: see 1b (VU1 fast path landed; recompiler next).
4. Then the mission parity report (`tools_py/parity/compare`) against pcsx2_mission_g.

**Run hygiene learned tonight:** `PS2X_VU1_DUMP` and `PS2X_RDRAM_DUMP` do not create
directories; the poller scripts leave pcsx2-qt.exe running if killed early (drive.py then
refuses to start — `taskkill /F /IM pcsx2-qt.exe`); timed RDRAM dumps miss the spawn when the
boot drifts — prefer `PS2X_RDRAM_DUMP_AT=<path>:<TracedName>#<n>` or a late fixed time (400 s).

## Previous pick-up (written 2026-09-08 23:30) — run recipes below are still current

**Mandate.** The user is away and wants in-game visual parity with PCSX2 for the single-player
mission ("lots of menus, little actual game"), worked autonomously in bounded steps: one hypothesis
-> one build -> one run -> read the evidence -> commit -> STATUS entry. Online play (M5) is the
long-term priority but is already reached; do not regress it. The user watches the TITLE SCREEN
closely: every run passes it, so look at s05/s06 of each run sheet before trusting a build.

**Where it stands (all committed on `develop`, last 692100e).**
- EE side now matches PCSX2 in the mission: actors, collision grid, camera path and the camera
  object's world / view-projection / projection / screen matrices (`*(0x488de8)` +0x2f0 / +0x330 /
  +0x370 / +0x3b0) equal PCSX2's to 4 decimals. Fixes behind that: SQRT.S source register
  (c9da469), EE/VU0 saturation (75dcadd), game thread rounds toward zero like the EE FPU (c57dccc).
- Object geometry renders (trees, bushes, road) since XGKICK packets are copied at kick time
  (089516b). mission_s13's last frame is the golden run's road-through-trees scene.
- The picture is still mostly covered by giant sky-coloured polygons. They are ONE object at the
  player's position (8 triangles, two 8-bit texture passes, tbp0 0x3621/0x3661), drawn through
  the VU1 command-list entry 0x1b50 with commands b20 -> 1638 (backface test on MAC flags) -> 4a8
  -> df8 (transform, DIV Q=1/w, NO near-plane clipping) -> f90 -> 1780 (emit) -> 22a0. Verified by
  offline replay of 150 dumped programs: 108/1878 kicked vertices have q<0, all from that object
  (4 consecutive frames); the 119 pc=0 world programs and the other 0x1b50 object are clean. The
  VU1 flag pipeline behaves per the manual. So the console must not feed this object in this
  state: the EE either culls it (bounding test) or gives it other data.
- Related EE divergence: our player stands at y=-132.9 at spawn, PCSX2 at -126.26 (x/z equal):
  ground height from the collision grid differs by 6.6 units.
- Frame rate: VU1 interpreter 158 -> 111 ns/cycle (4960120) but still ~0.7 s host per second at
  ~5 M cycles/s; the game runs at a few frames per second in the mission (`PS2X_VU_STATS=1`).

**Next tasks, in order, each with its first step.**
1. Identify the no-clip object and why the console does not draw it like this.
   a. Find the EE code that builds that command list: the VU reads command words at `340(vi14)`
      and jumps through the table at 0x1ba0 (index = word; b20 is entry 52, 1638 is 3, 4a8 is 50,
      df8 is 4, f90 is 8, 1780 is 20, 22a0 is 24, end is 33). Search the recompiled/decomp code
      (`game/analysis/socom2_game.elf.decomp.c`, `recomp/output`) for a packet builder that
      stores that sequence of small integers into a VIF packet, or watch it: `PS2X_WATCH` on the
      RDRAM source of the VIF1 DMA that carries it (`PS2X_TRACE_VIF=trig` prints the UNPACKs; the
      command words land at VU address TOP+2.. per `ILW.x vi5, 340(vi14)`).
   b. Read the submitter's visibility/bounding test (a float compare, now chop-rounded) and what
      it uses as "camera position": VU constant qword 30 = (938.56, -124.37, 832.51) is the
      player position, i.e. the object is back-face tested against the player, not the camera.
   c. Cheap experiment while reading: skip drawing that object (env-gated, by tbp0 0x3621/0x3661
      in the GL backend) to see the rest of the scene and re-grade the mission screens against
      `logs/parity/runs/pcsx2_mission_g` (`tools_py/parity/compare`). Do not ship the skip.
2. Ground height: compare the collision query for the spawn point (`FUN_002d49c0`, `FUN_002d2890`;
   grid at world+0x684, 36x25 cells, scale 1/180) between ours and PCSX2's post-load image
   `logs/parity/spawn_pcsx2.rdram` (PINE savestate slot 8). Suspects: chop rounding in the
   height interpolation, or a terrain triangle missing from the grid.
3. Frame rate: a non-cycle-exact VU1 fast path (immediate VF/VI writes, 4-deep MAC/status/clip
   flag ring, Q/P by instruction count) or a VU1 recompiler. Profile first with
   `PS2X_HOST_PROF=1`, copy logs/hostprof.txt before the mission and diff (STATUS 17:30).
4. Then the parity report for the mission path, worst screen first (see "The grade").

**The run you will repeat.** One game instance at a time (drive.py refuses otherwise); never build
during a run; delete `logs/parity/latest_frame.png(.tmp)` before a run.
```
PS2X_MC_DIR=game/disc/mc0_parity PS2X_PC_SAMPLER=1 PS2X_PEEK="*0x488de8+0x320:3,0x416054:3" \
PS2X_TRIGGER=938.5:940.5 PS2X_VU1_DUMP=logs/vu1dump2:150 PS2X_GS_TRACE_CMDS=trig \
python -m tools_py.parity.drive --target ours --script scripts/parity/launch_to_mission_diag.txt \
  --out logs/parity/runs/<stamp> --seconds 480 --tail 170 > logs/parity/drive_<stamp>.txt
```
The trigger arms when the camera x (first peeked word) reaches the gameplay value; the log is the
newest `logs/run_*.log` (`[trigger]`, `[vu1-dump]`, `[gs-cmd]`, `[peek]` one row per second, no
timestamps). Offline: `dist/vu1_replay.exe logs/vu1dump2/vu1_prog_N.bin --out p.pk [--trace]`
(`PS2X_TRACE_VU_FLAGS=1`, `PS2X_TRACE_VU_STEPS=40000`), `python tools_py/gif_packets.py p.pk
--verts`, `python tools_py/vu1dis.py <dump>`. Title-only A/B: `scripts/parity/title_only.txt`
(frames every 6 s after the movie skip; the title is s06). CPU reference rasterizer:
`PS2X_GS_BACKEND=cpu` — use it to tell GS-input bugs from GL texture-cache effects.

**Build.** `./build.sh runtime` (3 min; a header change forces the 500-batch generated-code
rebuild, ~10 min, and editing a header mid-build breaks the PCH — rebuild from scratch). Replay
tool: `cmake --build third_party/ps2recomp/build-clang --target vu1_replay` then copy the exe
into dist/ (it needs the DLLs there). `./build.sh all` after any recompiler change.

**Gotchas learned today.** Boot flow drifts run to run (intro/location cinematics may or may not
play): scripts navigate by screen state (`long`, `idle`, `until(x0,y0,x1,y1)` modes in drive.py),
never by press counts. C++ patches: Edit tool or a Python script written with the Write tool
(bash heredocs mangle backslashes; a failed assert writes nothing). Python subprocess needs
os.path.join paths for exes. `PS2X_PEEK` needs `PS2X_PC_SAMPLER=1`. Commit from the repo
root (own repo, remote github.com/Scotho/socom-unzipped), never `git add -A`; leave `server/config/simulated.db`
unstaged; trailers `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and
`Claude-Session: <session url>`. Update docs/STATUS.md (newest entry on top) and the memory
file after each milestone.


Read this first, then `docs/STATUS.md` (newest sections at the top of each day). This file is
written so a fresh agent can continue **autonomously** toward the project vision without asking.

## The vision (unchanged, this is what you are working toward)
A native SOCOM II EXE for modern PCs with controller + online play to a self-hosted server, built
by static recompilation of the PS2 game (no emulator). Milestones
(`docs/superpowers/plans/2026-09-04-implementation-plan.md`):
M1 toolchain ✅ · M2 boot-to-engine ✅ · M3 menu render + pad ✅ (navigation works end to end) ·
**M4 load and play a single-player mission (the mission now loads and its engine runs — you are
here, and the blocker is that nothing is drawn)** · M5 online lobby against our Horizon server
(already stood up, app id 10472) · M6 portable package. Stop only when a mission plays or an online lobby
we host is reached. Copyrighted-game work stays inside `socom_pc/`; game assets are gitignored.

## Priority (set by the user 2026-09-07 21:30): online play first, home-screen movie second
1. **Online play (M5)**: host the Horizon private server (`server/`), connect PCSX2 clients to it
   over DEV9 (docs/research/02 "PCSX2 networking") and validate login → lobby → room → match with two
   clients. PCSX2 is both the reference and the first working client: capture the online screens as
   golden (dlgNetLogin, dlgNetConnect, lobby, room) with the parity harness, then bring our exe's
   network stack (inet/netcnf HLE → Winsock, DNAS bypass) to the same screens and score them.
2. **Home-screen background**: MENULOOP.PSS must play behind the menu — needs the IPU/MPEG decode
   path (Kernel/Stubs/IPU.cpp and the 17 sceMpeg/sceIpu stubs are placeholders). Plan it as its own
   sub-project (FFmpeg-decoded PSS video → the frames the game expects in its IPU output buffer).
3. Missions are third; shell parity stays the grade for every screen touched.
Open, lower priority: the controller-configuration dialogs are skipped on ours (memory-card flow
variables are identical to PCSX2 — MemcardAlreadyHasData=1 on both — so the cause is elsewhere,
probably a pad/DBCMAN-derived UI variable read by the rank-confirm script).

## The grade (added 2026-09-07): visual parity with the original, per screen
`docs/parity/REPORT.md` is the project's grade. It scores our screens against a golden set
captured from PCSX2 running the same ISO with the same posted-key script
(`scripts/parity/launch_to_mission.txt`, aligned by `scripts/parity/align.json`). The loop is:

```
python -m tools_py.parity.drive --target pcsx2 --out logs/parity/golden      # once, or after a script change
python -m tools_py.parity.drive --target ours  --out logs/parity/runs/<stamp> --seconds 300
python - <<'EOF'
import json; from tools_py.parity import compare
align={k:v for k,v in json.load(open("scripts/parity/align.json")).items() if not k.startswith("_")}
compare.report("logs/parity/golden","logs/parity/runs/<stamp>","docs/parity/REPORT.md",prev_md="docs/parity/REPORT.md",stamp="<stamp>",align=align)
EOF
python -m tools_py.parity.montage logs/parity/runs/<stamp> logs/parity/<stamp>_sheet.png   # then Read the sheet
```

Rules: a session's last act is a fresh report; the next task is the worst screen on the launch →
mission path unless a hard blocker (thread death, no frame) stops the path earlier; a change that
lowers any screen's score is a regression to fix before moving on; shell screens first, then the
mission. The metric flatters dark screens — read the `.diff.png` (golden | ours | heat) before
trusting a number. Screenshots stay under `logs/parity/` (not in git); the report is committed.
Escalate only on these triggers: `tools_py/parity/probe.py`-style memory comparison over PINE
(`pine.py`, `addresses.py`) when a diff image does not explain a low score; a PCSX2 GS dump
against `PS2X_GS_TRACE_CMDS` only when the same primitives land differently (renderer bug).
The two systemic causes found by the first report: 2D elements ignore their parent/dialog
offset (everything drawn at the top-left), and text never draws. Fix those before anything
screen-specific.

## How to work (the loop that has been productive)
Bounded steps: one hypothesis → one build → one run → read the log/screenshot → commit → update
STATUS. Never open more than one deep subsystem at a time. Prefer runtime evidence
(`PS2X_CALL_TRACE`, `PS2X_PEEK`, screenshots) over static reading; the decomp is huge and
Ghidra's function list is incomplete. Commit as you go with specific messages and the co-author
line (below). If the user is away, keep going: every open item below has a concrete first step.

## Where the game is now
One pad script walks the whole single-player entry end to end:

```
PS2X_SOCOM2_PAD=1 PS2X_SOCOM2_INPUT_SCRIPT="8:CROSS,12:CROSS,16:CROSS,20:CROSS,24:CROSS,30:DOWN,32:DOWN,34:DOWN,36:DOWN,38:DOWN,41:CROSS" ./run.sh 90
```

first boot (memory-card popup → warnings → Sony logo → intro movie) → **main menu** → NEW GAME →
dlgSelectRank → dlgControllerPresetsNewGame → dlgControllerPresetsRG → dlgAlbaniaCinematic →
**dlg_Brief_Alb51** (the Albania 5-1 briefing; it draws its real photo panels) → the five DOWN
presses move the briefing selection from `overview_button` to `deploy_button` → CROSS fires
`OnDeployActivate` → `LoadMission` → `LOAD_SCREEN` → **the mission loads**: its systems register
(`CClutterAnimManager`, `diTick`, `Mission`, `ParticleTick`, `UnitTick`, `ai_pre_tick`,
`weapon_pre_tick`) and the level's AI scripts start (`Supply1-4_start`, `Sniper1/2_start`,
`Alarm1-4_start`, `PatrolWatch_start`, `set_iris`, `otc_init`). No `missing-target` lines, 60 fps
throughout. Details and the four fixes that got there are in STATUS 2026-09-06 02:15.

The briefing's six buttons are, in order: `overview_button`, `mission_details_button`,
`objective_button`, `map_button`, `equipment_button`, `deploy_button` (the last runs `LoadMission`).

What is **not** working: nothing is drawn once the mission starts (see task 1), and the menu's
button captions and 3D roller do not draw (task 3).

**Correction (2026-09-07):** the main thread does *not* go dormant by design and thread 2 is *not*
"the mission". Thread 2 is the game's auto-exposure thread (`FUN_003b1dd0`, priority 4, created by
`FUN_003b2450`, woken from the vsync path `FUN_0033c010` once a mission is up). Each pass samples a
grid of ~176 framebuffer pixels with `FUN_003b24c0`, a one-pixel GS local→host readback through the
VIF1 FIFO in reverse mode (BUSDIR=1, `VIF1_STAT` FQC). The runtime has no reverse-FIFO path, so
every wait in that function ran to its 16M-iteration timeout (~0.3 s per cell) and, being higher
priority, starved the main thread to one mission tick per minute — which is why the frame counters
froze and `FUN_001ebed0` was seen twice in 30 s. `FUN_00271650` (the old "scene-graph walk") is a
bounded script-runner reset and was never the hotspot. `FUN_003b24c0` is stubbed at recompile time
(`socom2_LumReadPixel`, mid-grey pixel) until the readback is implemented (secondary list).

## Next tasks, in order (each with a starting recipe)

### 0b. (2026-09-08 22:30) In-mission parity — objects render; what is left and how to pick it up
Read the 2026-09-08 entries at the top of docs/STATUS.md (16:15 -> 22:30) first. Landed today:
SQRT.S read the wrong register (c9da469: actors/collision/camera now match PCSX2), XGKICK
packets are copied at kick time (089516b: trees/bushes/road render), the EE game thread runs
with host rounding toward zero (the EE FPU chops; the title labels were garbled without it —
`PS2X_EE_ROUND=nearest` restores the old mode), VU1 interpreter 158 -> 111 ns/cycle.
Open, in order:
1. **Behind-camera triangles in the mission** — traced (STATUS 23:10) to ONE object drawn through
   the 0x1b50 command-list path without near-plane clipping (backface test only); the console must
   cull it or place it elsewhere (our player stands 6.6 units lower than PCSX2's: ground height).
   Find the EE submitter of that command list and its visibility test; fix the ground height.
   Recipe for the VU side (already done once): run the mission with `PS2X_PC_SAMPLER=1
   PS2X_PEEK="*0x488de8+0x320:3" PS2X_TRIGGER=938.5:940.5 PS2X_VU1_DUMP=logs/vu1dump2:150`
   (drive.py + scripts/parity/launch_to_mission_diag.txt, --seconds 480 --tail 170), replay every
   dump offline (`dist/vu1_replay.exe <dump> --out p.pk; python tools_py/gif_packets.py p.pk`),
   pick one whose packets have q < 0, disassemble it (`tools_py/vu1dis.py <dump>`), then step the
   clipper with `--trace` (PS2X_TRACE_VU path) and compare the MAC flags the program reads with
   what the FMAC four cycles earlier produced (ps2_vu1_core.cpp updateFmacFlags / commit).
2. **Frame rate**: VU1 interpreter still ~0.7 s host per second (PS2X_VU_STATS=1). A non-cycle-exact
   fast path (immediate VF/VI writes, a 4-deep MAC/status/clip flag ring, Q/P by instruction count)
   or a VU1 recompiler.
3. Re-grade the in-mission screens against logs/parity/runs/pcsx2_mission_g once 1 is fixed.
Boot-flow drift is real (the intro/location cinematics play or not): scripts navigate by screen
state (`long`, `idle`, `until(x0,y0,x1,y1)` modes in drive.py), never by press counts.

### 0a. (2026-09-08 14:30) In-mission parity — where the "player falls through the floor" chain stands
Read the 2026-09-08 entries at the top of docs/STATUS.md first. Facts established with guest-memory
diffs against PCSX2 (PINE works; `tools_py/parity/cam_poll.py --spec` polls chains, a savestate's
eeMemory.bin is the console image; ours via `PS2X_RDRAM_DUMP="C:/projects/socom_pc/logs/x.rdram:<s>"`
with a Windows path, a POSIX path fails silently):
- After the level load the collision grid matches PCSX2 exactly. At ~182 s the four squad members'
  collision-node rotation rows go to +/-FLT_MAX; each then occupies all 900 grid cells, the
  8192-node pool drains, chains get cut, the terrain leaves the grid, the player sinks; the camera
  runaway during the intro shots is the same objects. The node matrix comes from the actor's own
  matrix (`FUN_00315820` <- `FUN_005483d0` ra 0x549910; actor vtable 0x6691a0, matrix at +0x80,
  orientation quaternions at +0x54/+0x5c/+0x74/+0x7c) which jump to exactly 2^64 == sqrt(FLT_MAX).
- Traps (`PS2X_FPU_TRAP=<seconds>`; EE div by zero / sqrt of a saturated value, VU0 macro results
  that overflowed, VU micro DIV by zero; with host time and a per-site cap of 5): the mission-phase
  overflows sit in the quaternion library (`FUN_003070c0` q*q via the cross product
  `FUN_001bfc78`, `FUN_003072e0` normalize -> sqrt(MAX)) and in `FUN_005df930` (bone transform),
  called from actor code (`FUN_005a3070`). Their inputs are already ~1e37, i.e. the first bad
  number is produced without an overflow — a wrong value from data or from an integer/MMI path
  (keyframe decompression is the prime suspect), not from float arithmetic.
- Benign sites the console also hits: fog `FUN_00294070` (far == near at load), flip 1/0
  (`FUN_003aff30`), normalize of a zero vector (`FUN_001bfcc0`), HUD progress step `FUN_003719e0`.
Next recipe: run with `PS2X_FPU_TRAP=115` and read the first trap after the load in time order;
peek the actor quaternions (`PS2X_PEEK="0x1a89254:1,0x1a8925c:1"`, heap addresses are
deterministic for this script) at 0.1 s to catch the first frame they change; then read the
writer of the actor's +0x54 (class 0x6691a0 update methods: vtable at 0x6691a0). Compare the
same actor in the PCSX2 post-load image (`logs/parity/postload_pcsx2.rdram`, slot 7 state) by
finding it through the static player-position records (0x416054 probes, 0x4884d0) rather than
by heap address. Do not trust object layouts guessed from a vtable word: the render-mesh node
(0x408330) has a variable child-pointer array before its matrix.
The 3 flips/s (cycle-exact VU1 interpreter, `PS2X_VU_STATS=1`) is a separate, larger item: a VU1
recompiler. Until then `PS2X_CYCLE_CLOCK=guest` gives the game a constant 33 ms step.

### 0. (2026-09-07 20:00) Shell parity by score — current state
Done today: placement (vf00), text (culling + CLUT), roller (libvu0 un-stubbed: never re-add
`sceVu0*` HLE stubs; Sony's code runs correctly now), mission thread halt (range merge). The
mission renders textured geometry. Next by score: **main menu 81** — the MENULOOP.PSS movie should
play behind the roller (find how the menu state feeds movie frames to a texture / the movie
player's target while the shell is up); **controller configuration** (black on ours after Select
Rank, golden s09/s10: 3D controller models + text); then the text-only title cards' capture
timing. Then mission camera/HUD. Old notes below this line predate the fixes.
Evidence 20:20: (1) at the menu the GS trace shows no frame-sized uploads at all (largest are
512x128 font/UI pages) and the only large textured quads are the 500x195 panels — the movie
decoder never produces frames: `Kernel/Stubs/IPU.cpp` is a stub, so MENULOOP.PSS (and the intro
movies) need a real IPU/MPEG decode path (plan M3 item 7) before the menu background can appear.
Golden vs ours on the menu is otherwise the roller + captions, both present now.
(2) the controller-configuration screens are *skipped* in our flow, not black: Select Rank goes
straight to the cinematic fade (screenshots every second, `logs/parity/exp_ctrl`). The original
inserts dlgControllerPresetsNewGame/RG; find the script/UIVAR condition that skips them
(trace ui::UI_COMMAND args around the rank confirm, compare with a PINE read of the same UIVAR
on PCSX2).

The shell now renders text and layout like the original (STATUS 17:00). By report score the next
screens are: **main menu** (79) and the **controller configuration** screens (black on ours;
golden s09/s10). Evidence gathered 17:40 (`tools_py/iso_lbn.py … log <run.log>` on a
`PS2X_CD_TRACE=1` run): the menu's "soldier art" background is the looping movie
`RUN/MOVIES/COMMON/MENULOOP.PSS` (read ×16) and the roller is `RUN/UI/UI_GEO.ZED` /
`UI_MDL.ZED` (+ UI_TXR/UI_PAL), all of which *are* read from disc. At the menu the frame dump
shows `mscal` rising but `xgkick=0`, `hdrKick=0/N`: VU1 programs run, none kicks geometry.
`PS2X_TRACE_VU=2000` at the menu dumps the program (`logs/vu1_code.bin`, first XGKICK at 0x50)
and its input: the header at 0 is `[43e480f2 0 0 0]` (w = 0, the "setup kick" flag clear) and
the buffer at TOP holds a matrix whose rows are one lane rotated ((0,0,0,1),(1,0,0,0),(0,1,0,0),
(0,0,1,0)) followed by position/viewport rows and zeros where vertices should be. So the EE-side
packet builder for UI 3D objects never marks/loads vertices — start there: find who writes the
header word 3 (bit 1) and the vertex count for `mainmenu_roller` (UI_MDL) and check the movie
texture (MENULOOP frames → GS upload) reaches the same object. The controller screens are 3D
controller models on the same path. Then verify the merged range
0x510970-0x5109a8 (`recomp/merge_ranges.txt`) stops the mission-thread halt: run the mission script
10 min, expect no `[guest-branch:missing-target]` and the tick to keep running; then the next
`missing-target`, if any, via `tools_py/find_escaping_branches.py` (only 2 functions have the
split-loop pattern; 0x534c4c is a real multi-entry function, leave it).

### 1. In-mission renderer submits no geometry (the M4 blocker)
Once the mission is running, `PS2X_FRAME_DUMP` counters freeze at their shell values
(`vif1codes=399073`, `mscal=22426`, `xgkick=4421`, `nonBlack=0/286720`) — the EE is not sending new
display lists. The in-mission tick `FUN_001ebed0` *is* running (the old handoff's "never called"
was true only before a mission could load). Sampling at 1 s shows the mission thread almost always
at 0x2716e0 — the resume point after the `jal` at 0x2716dc inside `FUN_00271650`, a recursive
scene-graph walk — with a **constant** guest sp, so it is not runaway recursion.
- Recipe: `PS2X_CALL_TRACE="0x1ebed0:MissionTick,0x271650:GraphWalk,0x26f210:GraphNode,0x339de0:Render,0x350ab0:FifoKick"
  PS2X_CALL_TRACE_EVERY=1` with the script above and `./run.sh 90`; `MissionTick` was seen only
  twice in 30 s, so measure how long one call takes and which callee owns the time. `FUN_001ebed0`
  calls `FUN_00339de0(0x4887c0, app+0xa0)` at 0x1ec148 (return 0x1ec150) and the
  `FUN_0033bf30`/`FUN_0033be70`/`FUN_001fba70` triples after it — those are the render submissions.
- **Superseded 2026-09-07** by the exposure-thread finding above; the recipe stays valid for
  measuring the tick. The JAL-as-call cost question is closed (the walk is bounded, ~1.5k calls per
  run). Verify with the stubbed build: `MissionTick` should now run every frame after the load
  (the load itself is ~13 s of synchronous work inside the first tick), and the `PS2X_FRAME_DUMP`
  counters (`vif1codes`, `xgkick`, `mscal`) should move. If they still do not, the next suspects are
  the render submissions `FUN_0033bf30`/`FUN_0033be70`/`FUN_001fba70` after `FUN_00339de0` in
  `FUN_001ebed0` — trace them with `PS2X_JALR_TRACE` on their call sites.
- 16 `[guest-fault] load16` with garbage addresses (0xfd9302aa, pc=0x289c5c ra=0x28c2b8) appear
  during the mission load. `FUN_00289bb0` is an animation keyframe interpolator reading
  `*param_1 + index*6` with an unset keyframe pointer. Non-fatal; resolve once something draws.

### 2. Keep the mission running long enough to see it (M4)
After task 1, drive past the load: watch for the mission camera/HUD, then try movement on the left
stick (`PS2X_SOCOM2_MOUSE=1` maps the mouse to the right stick). `PS2X_HOST_SCREENSHOT=<dir>:<s>`
is the truth for what is displayed; `PS2X_FRAME_DUMP` pixels are stale on the GPU path.

### 3. Menu button captions and the 3D roller do not draw
Positions are **not** the problem (the previous handoff's claim that everything resolves to (0,0)
is disproved — see STATUS 2026-09-06). Every dlgMenu control has its real XPOS/YPOS in the parsed
tree, in the 17 design records and in the 2D nodes at +0x30/+0x34, and the SOCOM II logo draws in
the right place. The six buttons carry `CAPTION " "` (a single space) in the rdr, so their text
must come from a UI variable or locale lookup at draw time.
- Recipe: dump RAM at the menu with `PS2X_RDRAM_DUMP_AT="<path>:LoadList#6"` and print the tree
  with `python tools_py/rdr_tree.py <dump> <root> 6` (the root is the `a1` of that traced call);
  compare a button's SPEC with what the text renderer receives. `FUN_0026ecb0(DAT_00414be8, name)`
  resolves a caption id; `FUN_00351ff0(name, type)` reads a UI variable.
- The 3D roller is the same VU1 "no vertices" symptom as before (`hdrKick=0/N`); re-check it after
  the in-mission renderer works, since both go through the same path.

### 4. Online (M5) — NOW THE TOP TASK; state as of 2026-09-08 local
Two working clients now exist end to end:
- **PCSX2** logs in and two clients play a match on the local Horizon stack (STATUS 21:10).
- **Our exe** brings up SOCOM's SCE-RT network layer on the host and completes the Medius SCERT
  transport handshake against the real MUIS (STATUS 2026-09-08): it resolves the retail hostnames
  to PS2X_SOCOM2_SERVER (default 127.0.0.1), TCP-connects to 10071, exchanges CRYPTKEY_PUBLIC/PEER
  and CONNECT_TCP, the server sends CONNECT_ACCEPT + CONNECT_COMPLETE, the client sends the
  LobbyExt/0x03 universe query, gets the universe list + UniverseNews and shows **SELECT UNIVERSE**
  (2026-09-08; parity vs the PCSX2 golden `logs/parity/online/login/01_universe.png` 98.5).

Recipe for the exe path:
1. Start Horizon: `powershell -NoProfile -Command ".\start-servers.ps1"` in `server/` (delete
   server/pids.json if the script trips on a reused pid). No dns_stub is needed — the exe resolves
   the hostnames itself (socom2_hostnet.cpp; override with PS2X_SOCOM2_SERVER / PS2X_SOCOM2_HOSTS).
2. `python -m tools_py.parity.drive --target ours --script scripts/parity/launch_to_online_ours.txt
   --out logs/parity/ours_online --seconds 150`. Add `PS2X_SOCOM2_NET_TRACE=1` for the socket log.
3. Slice `server/logs/console-MUIS.log` from the line count taken before the run.

Next, in order:
- (a) DONE 2026-09-08. The "closes the socket" diagnosis was wrong: the queued universe query
  never left the SCERT send ring because `mfc0 Count` (ctx->cop0_count) never advanced in the
  runtime, so the SCE-RT clock (FUN_0063db68 → sec/usec at 0x676430) stayed at 0 and the
  connected-state send gate ("30 ms since the last flush", FUN_00634dd8) never opened. Fix:
  PS2Runtime::refreshCop0Count derives Count from the host steady clock at 294.912 MHz and is
  applied at every syscall and scheduler switch-in (ps2_runtime.cpp / EeScheduler.cpp).
- (b) DONE 2026-09-08 01:50: `python -m tools_py.parity.online_login_ours --existing --host` takes
  the exe boot → ONLINE → LOGIN → universe → persona "socomc" (password on the OSK) → CONNECT →
  EULA → lobby (SERVER NEWS closed) → BRIEFING ROOMS → Channel 1 → CREATE GAME "test" (Medley) →
  **GAME LOBBY** (VIGILANCE, socomc on SEALS). Server side: MAS AccountLogin, MLS lobby sequence,
  JoinChannel, CreateGameRequest1 → DME world, JoinGame, DME TCP + aux UDP CONNECT_COMPLETE,
  broadcasts + ECHO keepalives — the same trace as PCSX2 client A. Parity vs the PCSX2 golden
  (`logs/parity/online/{login,match}/`): 98–99 on every matching screen. Every transition is
  detected against title crops in `scripts/parity/refs/` (fixed waits lose presses: the shell eats
  input during transitions, the boot press count varies, the OSK sometimes opens in accent mode,
  the news popup appears seconds after the lobby). Horizon fix: the RC4 session key is clamped
  below 2^511 (`PS2CipherFactory.CreateSym`) — a random 512-bit key ≥ the client's modulus broke
  ~8% of handshakes ("Unable to decrypt RT_MSG_CLIENT_CONNECT_TCP").
- (c) DONE 2026-09-08 02:40 — **two instances of our exe play an online match on our Horizon
  server**: `python -m tools_py.parity.online_match_ours` (A hosts "test"/Medley as socomc, B logs
  in as socome, joins, switches to TERRORISTS, both READY → VIGILANCE / SUPPRESSION briefing → in
  mission; Horizon WorldStatus WorldStaging → WorldActive, DME relays APP_SINGLE/BROADCAST between
  the two clients). The second instance is plain env: `PS2X_WINDOW_TITLE` (window tag),
  `PS2X_MC_DIR` (its own memory card dir, game/disc/mc0_b), `PS2X_SOCOM2_UDP_SHIFT=2` (the game's
  fixed UDP 3658/3659 → 3660/3661, like PCSX2 client B's pnach). Screens: `logs/parity/ours_match/`.
- (d) NEXT: grade the in-mission screens (`match/A_18_hold05.png` is the PCSX2 golden; ours show
  the map from the spawn — compare the diff images, not the number), then gameplay parity in the
  mission (movement, HUD, round timer) and the M6 portable package.
- (c) capture the exe's online screens as a golden set and score them against PCSX2.

Layers already HLE'd (all in third_party/ps2recomp/ps2xRuntime/src/lib/socom2_*.cpp and
ps2xIOP/src/modules/eznetcnf.cpp; see docs/research/10-libnetb-rpc.md): msifrpc, libnetb (simple +
ex ring), eznetcnf/eznetctl, DNAS bypass, rt_crypt (RSA/SHA1/RC4), fixed 512-bit client keypair.
Rules: never savestate after network traffic (PCSX2 side); the exe needs no savestates.

### Secondary / cleanup
- **GS local→host readback** so the exposure stub can go: `FUN_003b24c0` sends a 7-qword VIF1
  packet (BITBLTBUF/TRXPOS/TRXREG/TRXDIR=1), waits for `GS_CSR` FINISH (bit 1), sets `GS_BUSDIR=1`
  and `VIF1_STAT` FDR (0x800000), then DMAs `DAT_004a45a8` qwords *from* VIF1 (`CHCR=0x100`) and
  reads the remainder from `VIF1_FIFO` while `VIF1_STAT & 0x1f000000` (FQC) is non-zero. The CPU
  backend already has `PerformLocalToHostTransfer`/`ConsumeLocalToHostBytes`; the GL backend defers
  to it, and the VIF1 reverse DMA/FIFO consumer is what is missing. The stub answers 0x80 grey.
- GPU plan stage 3-5 (`docs/superpowers/plans/2026-09-05-gpu-gs-backend.md`): AFAIL modes,
  DATE, 16-bit targets, readback paths, resolution scaling.
- Make `PS2X_SOCOM2_PAD` default-on; `sceDmaSendI` should set TIE as well as TTE.
- `PS2X_FRAME_DUMP` pixels are stale on the GPU path (only counters are reliable); fix or document.
- Re-run both coverage scanners after any Ghidra CSV change:
  `python tools_py/find_gap_functions.py game/disc/socom2_game.elf recomp/socom2_ghidra.csv` and
  `python tools_py/find_interior_functions.py ...` (add `--emit` to append to
  `recomp/extra_functions.txt`), then a full `./build.sh recomp && ./build.sh runtime`.

## How the shell works (decoded; details in STATUS 18:40 / 19:10)
- Top loop `FUN_001e7040`: `for(;;) stateMgr(0x4084c0)->tick(dt)` (`FUN_002ce9e0`, a message
  queue for push/pop/set state). Shell state 0x408538 update = `FUN_001f4640` → `FUN_003654c0`
  (input timer +0x900, script-event queue tick `FUN_0034e070(dt, 0x49ea50)`, UI messages →
  `FUN_00365a00(shell, "LOAD_SCREEN" | "POP_TO_MENU_STATE" | "MENU_SCREEN" | "SHUTDOWN" |
  "REBOOT")` → states 0x4085ac (load screen) / 0x408538 / 0x408758). `FUN_001ebed0` is the
  *in-mission* tick: never called while the shell is up, called once the mission state is pushed.
- UI = `game/disc/RUN/UI/READERC.ZAR` (111 `.rdr` dialogs; `dlgMenu.rdr` = main menu; locale
  text in `RUN/LOCALE/STATES/UIMNLOC.ZAR`, loaded fine). Scripts are animation sequences: node =
  `{u16 type, u16 size<<2, …}`; runner header 0x1c bytes (`+5` state: 1 idle, 2 start, 4 running,
  5 done; `+8` current node; `+0xc` length). Command ids = registration order of
  `FUN_0026a8e0(0x414bb0, "NAME", parse, create, exec, post)`: IF=2, OBJECT_ACTIVE_STATE=0x11,
  OBJECT_OPACITY_FROM_TO=0x19, SOUND=0x1e, CALL_ANIMATION=0x2d, TIMER=0x38, VALVE=0x3d
  (exec 0x353d00), VBIT=0x3e (0x353260), VWATCH=0x3f (0x353030), ui::UI_COMMAND=0x101
  (`FUN_002745a0` → script binding table), ai::*=0x2xx. Dispatcher `FUN_0026a6e0`; runner step
  `FUN_00269da0`; animation update `FUN_00270220`; named events via
  `FUN_0034e6b0(delay, 0x49ea50, "name", node, arg)`.
- Script binding table at ELF 0x3dd4d4: 207 `{name, fn, 0, id}` rows (16 bytes). Useful ones:
  SetMission 0x27eb50, SwitchMenu 0x27e720, SetMenuState 0x27c9f0, ReadyToLoad 0x27caf0,
  PopUpDialog 0x27eb10, SuspendMenuInput 0x277220, GetNumSavedGames 0x27dea0, LoadSavedGame
  0x27fa40, IsMemCardInserted 0x27e1b0, PlayMPEG 0x27ab30, SetScreenOrigin 0x27bf10. Dump the
  whole table with a 10-line Python ELF reader (pairs at 0x3dd4d4 + 16·i).
- Pad: HLE in `game_overrides_socom2.cpp` (scePad2*), game reader `FUN_002da930` →
  `FUN_002d9ff0` (states 0/1/2/3 per button at DAT_0044f108+1+idx). Works.

## Build / run
- `./build.sh runtime` (3-10 min) for runtime/IOP changes; **run from `socom_pc/`**. Editing
  `gs_backend.h`/`gs_frontend.h` also recompiles generated code (~15 min).
- `./build.sh recomp && ./build.sh runtime` (15-20 min) after touching `recomp/socom2.toml`,
  `PS2_STUB_LIST`, or `recomp/extra_functions.txt` — the forced-function list only takes
  effect through a recomp build.
- Run: `./run.sh <seconds>` (writes `logs/run_<stamp>.log`; newest = `ls -t logs/run_*.log | head -1`).
- Never run two game instances at once (they skew each other's timing); never rebuild while a
  run is active (the link overwrites `dist/socom2.exe`).

## Diagnostics (env-gated, zero cost when unset)
- `PS2X_CALL_TRACE="0xADDR[:name],..."` — every call of the listed guest functions: time,
  a0-a3, f12-f14, ra, any argument that points at text, and `[ret] v0/f0`. 320 slots.
  `PS2X_CALL_TRACE_EVERY=k` (after the first 300 calls log every k-th; 1 = all). Prints
  `no function at 0x…` for unrecompiled targets — that itself is a finding.
- `PS2X_PEEK="0xADDR[:words],..."` with `PS2X_PC_SAMPLER=<s>` — guest words (hex+float) every s.
- `PS2X_CD_TRACE=1` (`[cd] Read lbn`, `[fio] open`), `PS2X_MC_TRACE=1` (`[MC] GetInfo/Sync`).
- `PS2X_HOST_SCREENSHOT=<dir>[:<s>]` — PNG of the window every s seconds (the truth for
  "what is displayed"). `PS2X_GS_TRACE_PRESENT=<skip>` — per-present state incl. copy pixel.
- `PS2X_FRAME_DUMP=<dir>` — per-present counters (`xgkick`, `hdrKick`, `gsSubmits`, `mscal`…).
- `PS2X_GS_TRACE_CMDS=<skip presents>` — 4000 replayed GS commands (submits with coords/rgba,
  uploads, transfers, presents). `PS2X_GS_STATS=1`, `PS2X_GS_DUMP_TEX=<dir>`,
  `PS2X_GS_BACKEND=cpu` (reference rasterizer).
- `PS2X_TRACE_VU=<skip>` (VU1 program path + data dumps; `tools_py/vu1dis.py`),
  `PS2X_TRACE_VIF=<skip>`, `PS2X_TRACE_FIFO=1`.
- `PS2X_SOCOM2_PAD=1` (+ `PS2X_SOCOM2_PAD_TRACE=1`, `PS2X_SOCOM2_MOUSE=1`,
  `PS2X_SOCOM2_INPUT_SCRIPT="t:BTN[+BTN][:hold],..."`).
- `PS2X_JALR_TRACE="0xSRC,..."` — the resolved target of every indirect call/jump issued from
  those pcs (which function a vtable slot or function pointer actually reached).
- `PS2X_RDRAM_DUMP="<path>:<seconds>"` and `PS2X_RDRAM_DUMP_AT="<path>:<TracedName>#<n>"` — write
  the 32 MB guest RAM to a file (the second fires on the n-th call of a `PS2X_CALL_TRACE` name);
  read `.rdr` trees out of it with `python tools_py/rdr_tree.py <dump> <hex node addr> [depth]`.
- `[ret-clobber]` / `[ret-unwound]` lines from the call tracer: a traced function returned with a
  callee-saved register changed, or left through a scheduler unwind (then its `[ret] v0` is not
  the function's result).
- `[guest-fault]` (first 16, always on) and `[guest-branch:missing-target]` lines: silent
  guest failures. lldb recipe in `docs/research/08` (host frames are named after guest functions;
  `rcx` = rdram, `rdx` = R5900Context at a `sub_*` entry). Batch-mode breakpoints proved slow
  and flaky; prefer `PS2X_CALL_TRACE`.

## Gotchas (respect these)
1. **Code the recompiler never saw fails silently.** Ghidra misses 2-instruction trampolines
   (`j target; addiu $a0,$a0,imm`) and some callback targets; table-dispatched calls into them do
   nothing. Scan (Python over the ELF text segments): every `j` word (`w>>26 == 2`) followed by
   `addiu $a0,$a0,imm` (`>>16 == 0x2484`) or nop whose address is neither a CSV `Start` nor inside
   any `[Start,End)` → add to `recomp/extra_functions.txt` → full recomp. Two were found and
   fixed (0x353d00, 0x2a98a0); rerun the scan when new symptoms of "call does nothing" appear.
2. Shell heredocs mangle backslashes: never write C string escapes (`\n`) through a bash
   heredoc; use the Edit tool (or Python with `newline='\n'`, checking the result).
3. Git root is `C:\projects\socom_pc` (own repo since 2026-09-10, remote
   github.com/Scotho/socom-unzipped): **never `git add -A`**, stage explicit paths and push.
   Shell/py files stay LF.
4. Don't steal desktop focus or screenshot the desktop; the raylib window screenshot
   (`PS2X_HOST_SCREENSHOT`) is fine. Pause if the user says the machine is under load.
5. Commit trailer: the `Co-Authored-By:` line names the model you are, and `Claude-Session:` is
   this session's URL — both are given to you at the start of the session; do not copy old ones.
6. If running via cron, re-arm a one-shot ~4 h ahead when you start and point its prompt at the
   *current* blocker.
7. **Read the sampler's thread table before chasing a "slow" function.** `[pc-sampler] live pc`
   is the main context; `running=N` names the scheduled thread and `[N pc=… st=…]` its saved state.
   A live pc frozen at a function *entry* with constant sp while `running` is another thread means
   the main thread is preempted and starved (PS2 threads are strict priority), not that the function
   is slow. Then trace the running thread's function with `PS2X_CALL_TRACE` and read its `[ret]`
   cadence — the exposure thread was found this way in two 90 s runs.
8. Bounded spin loops on MMIO (`while (REG & bit) if (++n > 0x1000000) fail`) are the engine's
   way of waiting for hardware; an unimplemented path shows up as a ~0.3 s stall per call, not a
   hang. Grep the decomp for `0x1000000 <` to find them.
9. Background shell commands are capped at 10 min; a full `./build.sh recomp && ./build.sh runtime`
   is longer. Launch it detached (`nohup bash -c '… > logs/build_x.log 2>&1; echo done > logs/build_x.done' &`)
   and poll for the marker file. `python -` through a heredoc mangles backslashes exactly like
   bash does — use the Edit tool for C/C++ macro lines.

## Landmarks
- Recompiler: `recomp/socom2.toml` (stubs/mmio/patches), `recomp/extra_functions.txt`,
  `recomp/socom2_ghidra.csv` (name,Start,End,Size), generated code `recomp/output/`
  (MIPS listing in comments — use it when the decomp lacks a function).
- Decomp/strings: `game/analysis/socom2_game.elf.decomp.c` / `.strings.txt`; overlay decomps
  (`DNAS.*`, `SCUS_972.75`) alongside. Disc tree: `game/disc/` (ISO in `game/`).
- Runtime: `third_party/ps2recomp/ps2xRuntime/src/lib/` — `ps2_runtime.cpp` (runner, present),
  `gs/gs_gl_backend.cpp` (OpenGL GS), `gs/gs_cpu_backend.cpp`, `game_overrides_socom2.cpp`
  (pad HLE, call tracer, peek, PC sampler), `Kernel/Stubs/{CD,MemoryCard,FileIO}.cpp`,
  `src/lib/socom2_host_input.cpp` (keyboard/mouse/script). IOP: `ps2xIOP/src/modules/`
  (dbcman, mcserv, snd989…).
- Research: `docs/research/05` (code package/DNAS/MFIFO), `06` (989snd), `07` (render
  pipeline), `08` (controller/DBCMAN). GPU plan: `docs/superpowers/plans/2026-09-05-gpu-gs-backend.md`.
