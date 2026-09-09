# Project status — updated 2026-09-08 23:10

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
