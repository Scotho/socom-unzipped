# What we know, what we believe, and what we got wrong

A living list, audited after every task. Entries are **promoted** (believed → proven) when an
artefact settles them, **retired** when they stop mattering, and **retracted** loudly when they
turn out false. Every proven entry names the artefact that proves it; every believed entry names
the experiment that would settle it. If an entry cannot do that, it does not belong here.

Maintained by whoever is running the loop. Last audited: 2026-09-17 (`docs/AUDIT-2026-09-17.md`) -- rows settled or superseded that day are marked in place.

---

## 1. Proven — with the artefact

| What | Artefact |
|---|---|
| **FIXED 2026-09-16 (research/34): the online round that never started on the day's build — every map, Frostfire included — was the GL texture cache exploding on CLUT snapshot serials.** `3d37abc` minted a serial for every palette load whose bytes differed from the previous one and put it in the texture key; SOCOM II alternates palettes on consecutive draws (HUD, skins), so an online round reached 55,483 cache entries and 64k uploads a second, the render thread 2 fps, and the guest clock (timer T0, host-paced minus the render back-pressure wait) 0.04 s per wall second: the STARTING ROUND / OBJECTIVE messages never expired and nobody moved while the network round clock ran. Ids are keyed by palette content now. | Bisect over four launches (`ours_control_frostfire_{regress,bisect1,bisect3}`: only the tree without `3d37abc`/`545b85a` passed); mechanism on `ours_control_frostfire_headstats` (`[gs-gl stats]` textures 414 → 55,483, `[clock]` 2.5 s guest per 42 s host); fix verified `ours_control_frostfire_clutfix` (CONTROL-ROUND exit 0, cache steady at 292, 43–45 fps, guest clock 0.74 s/s); `ps2_gs_tests` 'a CLUT re-loaded with the same bytes re-uses its snapshot id'. |
| **THE ACCEPTANCE TEST PASSED — an automated two-instance online match reached a kill** (Sprint 5 ladder launch 2, Frostfire, pinned harness `171290b`, frozen exe `234b4772cd0a8bf8`): rounds 1–3 KILL on both KillWatch (actor fields) and `verdict_replay` (valves). Round 1: victim B `+0x1044` 1.0 → 0.298 → **0.0** with word 0 `0x6691a0` intact; `+0xF7A` 1 → **2** on the death row (→ 3 at +3.7 s); killer A's single R1 burst 0.59 s before, 27.9–29.2 units 3-D, dy 0; `total_mp_kills` 0→1 **on the killer's instance only**; the victim team's `aiteam_08` 1→0 on A at +0.02 s and on B at +0.25 s; both screens "socomc fragged socome with M4A1" ≤ 0.33 s after. Route v2 arrived all 4 rounds (77–89 s); round 4 missed at −4.1° aim error with 111 bursts. The death readout is now proven online (settles the §2 row and Goal 2) | `logs/parity/s5_t5_ladder2`, `logs/run_[AB]_20260913_230442.log`, `docs/research/22-kill-readout.md` §Ladder launch 2, `docs/research/assets/22-first-kill.png`; independent clause-by-clause re-derivation; evidence archived to `D:/socom_archive/acceptance/s5_ladder2/` (run logs sha256 A `af8b92618dd75f47…`, B `b57e1b26912f5b5b…`, full list in `SHA256SUMS` and tracked manifest `docs/research/assets/22-first-kill-evidence.txt`); pinned by `test_verdict_replay.TestLadderLaunch2Round1Kill` (`d9b5f33`) |
| **The kill REPEATS on the block-pointer exe** (2026-09-15 evening, `s6_ladder8`, harness `d6e417f`, exe `1cfef9af028a90fc…`, host quiet): **4 of 4 rounds KILL on KillWatch** (health `+0x1044` → 0.0 on B's intact actor, t = T+75.2 / 206.6 / 324.4 / 440.5 s), rungs 3,3,1,3, the route arrived every round; **round 2 used the new lead correction** (`lead=+1.5 steps=1 hits=3`: three misses inside tolerance, one lead step, then the kill). `verdict_replay --per-round` (the valve scorer): **rounds 1 and 2 KILL**, round 3 `NO-KILL unattributed` (the fatal burst was fired from 68.2 units 3-D against the pre-registered ≤ 60 bar — the bar stands, the round is not doubly attributed), round 4 `NO-DATA` (the run stops at the last kill before the valve window's rows arrive — harness tail to add). Against Sprint 5's one launch (3 of 4, round 4 never corrected): the aim loop now corrects, and the lobby reached gameplay once every press was verified | `logs/parity/s6_ladder8`, `logs/run_[AB]_20260915_232317.log`, `drive_s6_ladder8.txt`; second launch `s6_ladder9` pending for the plan's 2-of-2 bar |
| **Spawns are deterministic per map, and a clock round end resets both players to them with the actor block kept**: Frostfire A (796, 100, 614) / B (536, 143, 1254), 2-D gap 691, dy 42, two discrete floors (y ≈ 100 / 142); Vigilance A (540, 160, 1456) / B (1130, 65, 96), gap ~1485, dy 95, continuous terrain. On 3c the two movers swapped floors (A climbed at ~(686, 938), B descended at ~(652, 1230)). Round 1 → 2 on 8c kept B's actor at `0x17935c0` | Broad review `spawns.py`, `ys.py`, `floors.py`, `r2.py` over 5 Frostfire + 4 Vigilance launches and 8c |
| **Mutual standing does not starve either side online**: 3c both pads neutral ~48 s at round start with MoveScale f12 = 1.0 on 384/384 and 310/310 rows, NetIdle peak 1547/1386 ms; kill2 39.6 s; every NetIdle alarm on record falls inside a peer freeze (8c) or a pinned-mover window (Sprint 4 `wtb2`) | Broad review `neutral.py`; Task 3 review |
| **The actor-matrix yaw settles within one 4 Hz row of an `rx` release online** (62/62 holds on 3c, change from release +0.25 s to +2.5 s = 0.00°); the "≈ 2.5 s" caveat is the *walk direction* lagging, not the matrix | Broad review `yawsettle.py` |
| **A clock round end is readable from the valves, and it steps no kill counter** (Task 1 Step 5b, launch 8c, map **VIGILANCE** — also kill2's map): both sides controllable after the vf0 fix (A 84.19/1.52/0.00, B 82.98/1.88/0.00); A's clock string reached `00:00`, then `mp_round_count` 0→1 and `mp_major_game_state` 2→4 on both instances at one aligned moment; `total_mp_kills` 0, `aiteam_00/08` 1, `+0x1044` 1.0, `+0xF7A` 1 throughout and after; no R1 bit in either log. Task 6's negative-control fixture | `logs/run_[AB]_20260913_132843.log`, `control_round.json`; review re-derived |
| **The VU0 vf0 fix restores Frostfire online control** (~~one usable run; a second Frostfire sample and the Medley bar still owed before "fixed"~~ **fixed: Medley/Vigilance bar on 8c, second Frostfire sample on ladder launch 2's precondition, 2026-09-13**): the local ground probe hits from its first call (ProbeEval 1332/1332 A, 1428/1428 B, candidates 1–3), `actor+0x420` tracks the clock within 0.05 s on every row, `+0x1061` bit 0x04 never sets, MoveScale runs at f12 = 1.0 for the whole ~302 s round; movement bar A 51.78/1.65/0.00, B 54.57/3.79/0.00; every Frostfire model gridded by world bounds; starvation peaks 1547/1441 ms. First online valve reads: `aiteam_00/08` 0→1 at round start, `mp_round_count`/`total_mp_kills`/`mp_game_over` 0, clock string counts down | Launch 3c, `logs/run_[AB]_20260913_115809.log`, `logs/parity/frost{A,B}_probe600_vf0.rdram`; review re-derived all with independent scripts |
| **The actor's facing lives in its own transform**: quaternion `actor+0x70` → `FUN_005483d0`/`FUN_00307170` → 4×4 at `+0x80..+0xbc` (row vectors; quaternion angle = −θ of the matrix; row 3 copied from `+0xf54`, not `+0x1c`). Walk direction = (−m[+0xa0], −m[+0xa8]): p90 **1.57°** over 17 live SP forward holds (13 at the spawn heading with a ~1.4° walk bias, 4 elsewhere at 0.0–1.0°), 1.43° over 11 online holds offline. Not valid within ~2.5 s of an `rx` hold | Sprint 5 Task 2, `e685b82`; review re-derived with an independent parser (589/589 quaternion–matrix rows) |
| PCSX2 plays a full online round against **our own** Horizon server, advancing to round 2 | `research/18` §1 + tracked contact sheet `docs/research/assets/18-s0-evidence.png` |
| A playing match and a frozen one produce **byte-identical** DME TCP profiles (11 BROADCAST / 30 SINGLE / 7 TOSERVER / 2 aux-UDP, same opcode histograms) | `research/18` §1; recounted from the raw log by review |
| The peer channel carries **zero** application data all match — every datagram decoded | `research/18` §3 |
| The advertised-port and shared-RSA divergences were real, and their fixes reached the wire | `acb603e`; wire bytes `4C-0E` both slots, distinct keys verified by `(m^17)^d mod N == m` |
| Neither of those fixes moved the symptom | Same runs; 3 hypotheses now falsified by measurement |
| **The client runs on Linux: the runner built from the same tree and generated code boots the disc under X and draws the same frame** -- the VM's exported boot frame vs the Windows export of the same screen at 640x448: mean abs diff 0.008 grey levels (bar 3), the GL backend on Mesa 4.1 with the probe passing (clip control absent, noted) | `logs/parity/vm/latest_frame.png` vs `logs/parity/s7_scale_1x.png`, `logs/parity/vm/run.log`, 2026-09-18 13:05, VM `socom-linux`; Sprint 8 Goal 1 Task 8 |
| **The VirtualBox Ubuntu machine gives OpenGL 4.1 core through the VMSVGA driver** (Mesa 25.2, `SVGA3D; build: RELEASE; LLVM`, a bare Xorg + openbox session at 1280x800 started over SSH once `Xwrapper.config` allows non-console users), above the GL probe's 3.3 floor -- the Linux port's GL path is testable in the VM, not only the CPU fallback | `logs/vm_x_start.sh` inside `socom-linux`, 2026-09-18 12:40: `glxinfo -B`. Whether dual-source blending is exposed is the probe's own answer on the first boot (Sprint 8 Task 8). |
| **`sceSifInitRpc` reset the whole IOP model on every call, not only the first** -- loaded 989snd banks, `lastBank`, the VAG-streaming state, all wiped whenever the game re-initialised RPC (it does so as other libraries come up mid-mission); the console's call only sets up the EE's packet queues. This was the owner's "unknown bank" rejects (bank 0xa30000 loaded at log 6688, `sceSifInitRpc` again, `snd_InitVAGStreamingEx` succeeding a SECOND time at 6751 -- only possible on a wiped model -- then 0 entries at the reject) and half of the slot leak. | The test 'a loaded bank survives a second sceSifInitRpc' (RED with the log's exact signature, 0 entries); `RPC.cpp` resets only under the first-init guard. Second-pass commit of Task 12. Any other mid-game oddity that looked like state vanishing is worth re-checking against this. |
| **A VAG stream that plays to its natural end never freed its model slot** (only `snd_StopSound` did, and that only after b3e3797): the game polls `snd_SoundIsStillPlaying` and reuses the slot on "done", so the model now frees the slot with that answer and reaps ended streams before every allocation, asking the mixer per handle. | The test 'a VAG stream that plays to its end is reported done and its slot is reusable'. Residual: in the first-pass run the mixer itself reported two handles playing for the whole mission (7 of 4440 polls said done) -- long-lived streams hold slots by design; whether those two should have ended is a stream-length question, open. |
| **Two instances on one PC with the SAME RSA key reach the lobby and play a control round** (Sprint 7 Task 2b): key sharing between two clients of one account is not what keeps a second machine out | `s7_samekey` 2026-09-17, `PS2X_SOCOM2_RSA_KEY_B` unset: `RESULT CONTROL-ROUND` on Frostfire; `logs/parity/drive_s7_samekey.txt` |
| **Equal-priority time slicing was an ours-only semantic; removed** (`EeScheduler` now expires the slice only for a strictly higher-priority ready thread, as the PS2 kernel does) | `39cd17f`, the test 'two equal-priority threads do not interleave'; with it in: gate 3/3 (`s7_gl_gate2`), 7 of 7 driven control rounds that reached the lobby played to the clock (2026-09-17) |
| **`sceCdRead` moved the CD stream cursor; fixed** (a plain read while a stream was open fed the demux from after that file: the RED test delivered sector 44 where 11 was due) | `5a1b6a8`; `s7_audio_title`: the title loop correlates at 1.000 with the disc PCM, constant offset, no step |
| **The lobby rate on a pinned harness: 6/10 on 2026-09-17, then 10/10 on 2026-09-18 with the injected press latched** (6b7a2b3). Every miss of the first ten was one class, the on-screen keyboard at login typing extra glyphs: the drive's 90 ms wall-clock press fell between two polls of a login screen running at 12-30 fps (dropped, never repeated; the cursor then desynchronised). The latch delivers every press to at least one poll. | `logs/parity/lobby_rate_2026-09-17/` (6/10, `login:keyboard-typing=4`); `logs/parity/lobby_rate_summary.txt` 2026-09-18 02:33 (10/10, harness `9ee5b0c`-era, exe `s7_ring_build`); `lobby_report --bar 0.8`: `RATE 10/10 PASS`. The login screen's slowness stays its own §2 row. |
| **The 3-17 s online freeze (launch 8c) did not reproduce in a quiet or a loaded (four spinning cores) Frostfire control round with the freeze fields in** -- no stall window between 3 and 17 s on either side in either round; the two windows the tracer prints are the pre-round clock at 0 and the 5 s round end | `s7_freeze_quiet` (run logs 215259), `s7_freeze_loaded` (220545), `freeze_trace --peer` both directions; research/29 §0 |
| The player's **feet** are at the right height (−145.875 vs console −145.8672); the defect is the **camera** | `research/17` §0.1, derived from `STATUS.md`'s 2026-09-09 01:30 entry's own camera y values |
| The skeleton root node decays 11.4845 → 0 while its saved copy freezes at the console's 5.50391 | `research/17` §4.1, raw trace `run_20260912_121304.log:3962-6975` |
| `rand()` returned 15 bits over a `_rand_next` frozen at 41 (host CRT's first draw) | `ede2096`; `_rand_next = 0x29` in four of our RDRAM images, live in all three PCSX2 images |
| The disputed mover field could not exceed 4.0000458 under the old mask; console reads 6.3338 | `research/17` §6; two samples a side |
| Five soft-double stubs were bound with the wrong ABI, and were **identity** at 19 of 22 sites (the 3 garbage sites are unreachable) | `db7a992`; delay-slot analysis of every call site |
| The intro-movie macroblocks were a cross-thread race on `m_currentTransfer`, not a byte-accumulator bug | `4a701f1`; deficit 3,748 → 0, MISSING 9 → 0 |
| `--vram-diff` catches a uniform ±1 px shift again after the seam budget (8/15 x, 6/15 y) | `6c017c2`, measured on real renders |
| **One player walking to the other cannot finish inside a round** *(qualified 2026-09-13: measured on Vigilance over 1382 units with the camera-steered loop at ~15 s/step; it does not bound a waypoint route on Frostfire's 691-unit gap — broad review)*. Measured closure efficiency is 39 % (758 units gained for 1961 walked) at ~15 s/step, so 1382 units needs ~450 s against a ~360 s round. Two movers is ~700 units each, ~180 s | Task 7 run `wtb2`, `logs/run_A_20260912_211009.log`; arithmetic checked by review |
| ~~**The two-instance approach closes faster than one:** 1359 units in 127 s against Task 7's 758 in 300 s~~ **SUPERSEDED — derived from the camera+facing reconstruction that was later proven wrong by up to 50 units. Use the actor-row generation below (1485.5 → 50.0 in ~127 s).** The rifle facts stand: 96 R1 injections, ammo 30/30 → 0/30, impacts on the wall ahead of the muzzle | Task 8 run `ours_task8_kill2` |
| ~~**They fought at ~90 units** (median 93, min 34.9, 3 % inside 45)~~ **SUPERSEDED by the actor-row generation below (min 50.0, median 67.9, 0 % inside 45).** Same conclusion, better instrument | Review of `9c28fe0`; superseded once `true_pos()` read the actor's own coordinates |
| **Player health is `actor+0x1044`** (float; 1.0 full, <= 0 dead) and **`actor+0xF7A` is the alive byte** (1 = alive), on SCUS_972.75 **r0001** | `research/19` (two community memory tools agree, one matched to our ELF by patch bytes); decomp compares `+0x1044 <= 0.0` for three teammates in a row, then `< 0.2` and `< 0.5`; every image reads 1.0 and 1, the console's included. **~~Not yet read live in an online match~~ read live online at 1.0 / 1 on launch 3c (976/973 reads); ~~the `<= 0` half is still unread~~ the `<= 0` half read live at three kills on ladder launch 2 (§1 top row)** |
| **The multiplayer round-state object is `*0x437ce8`**: `total_mp_kills`, `mp_round_count`, `mp_game_over`, rounds won and alive per team (each value a short 4 bytes into its record), and the major/minor/"my" round-state bytes at `+0x113..+0x115` | `research/19`; decomp references `DAT_00437ce8` in the round code. Separates a kill from a round ending on its clock without a screenshot |
| **Open-loop aim resolution is floored at ~20-40° by the HARNESS, not the runtime.** The harness's `PAD_AXIS` sends only full deflection (0/255); the shortest usable hold already sweeps 35-40°, against a body that subtends 15-20° at contact range. **The pad file itself accepts 0-255 per axis**, so partial-stick aim is available for the cost of one re-calibration | Task 7 §3.13 (19 timed holds, repeat scatter 99.5 vs 80.8 at one hold length); pad-file range confirmed by the Sprint 5 planning pass |
| **The local player's actor is reachable from a STATIC: `*0x408c58`** (also `0x40d744`, `0x440c38`, and `*0x415ff0+0xbc`). Full chain: `@408c58` word0 = `017941d0`; `@17941d0` word0 = `006691a0` (actor vtable); `*(actor+0xc0)` = mover `006694b0`. The `*0x488de8+0xbc` route is **not** it — that route is recorded in `STATUS`'s 2026-09-09 01:30 entry, not HANDOFF, and `0x488de8` is the *camera* | Offline scan of five of our RDRAM images **and the PCSX2 console image** for vtable `0x6691a0` keeping the actor whose mover is `0x6694b0`; live in an online match (`logs/run_A_20260912_230022.log`, actor `0x17941d0`, 804 rows); `*0x488de8+0xbc` resolved 24 times in 1162 rows and to `0xd9d9d9d9`. `research/18` §4.1; route written into `HANDOFF.md` "Open items" item 0 |
| **Two movers close the map four and a half times faster than one**: `ours_task8_kill2` closed the true 3-D gap **1485.5 → 50.0 units in ~127 s** (11.3 units/s) against Task 7's 757.8 in 300 s (2.5 units/s), both players walking — the first time two online players have been in the same place | `ours_task8_kill2`, `logs/run_A_20260912_231341.log` / `run_B_…` (1172 / 1055 in-game rows). Team-closed over team-walked **61.0 %** vs `wtb2`'s 38.6 %; `kill1` was **36.5 %**, i.e. no better than one mover. Per-side efficiencies double-count the same gap and must not be quoted |
| **The bursts hit nothing because the players were never in range at all, in three dimensions**: on the ACTOR rows the minimum true 3-D separation for the whole run was **50.0 units**, the last 400 rows had a median of **67.9** and a median elevation of **43.3°**, and **0 %** of them were inside 45 units in 3-D, inside 25, or within 10 of each other's height. Range and elevation are co-equal causes; the 77° figure is the single worst row | Same run, actor positions (words 7/8/9). ~~`actor+0x204`/`+0x208` unchanged, so no damage was dealt~~ **Whether damage was dealt is UNKNOWN** — those were not the health field (`research/19`); the geometry conclusion stands on its own |
| **The loop's own distance was wrong by tens of units**, because it reconstructed each player as `camera + 24.9 * facing`: a facing wrong by tens of degrees misplaces a player by up to two orbit radii (~50 units), and placing the OTHER player needed the other side's facing | Reproduced in a **flat** simulated world: reported-best vs ground truth was 40.3/64.3, 23.4/30.7 and 157.6/204.7 before the fix, and **18.1/18.1** after `true_pos()` read the actor's own x/y/z. `research/18` §4.11 |
| **The camera record orbits the actor at ground radius 20.65 (sd 5.17), 19.73 above it** — i.e. the camera looks down on the player from ~44°, which is a free pitch readout | 1172 paired rows of `ours_task8_kill2`; the actor's own position is at `actor+0x1c/+0x20/+0x24` |
| **The rifles DID fire** — this is a geometry failure, not an input one | `buttons=0800` (bit 11, R1) injected **96 times** in `logs/run_A_20260912_231341.log`; HUD ammo `A_fight04.png` 30/30 → `A_fight07.png` **0/30** with bullet impacts on the stone wall in front of the muzzle, `B_final.png` 13/30 1 MAG (~47 rounds fired) |
| **The online movement blocker was `sceInetInterfaceControl(0x200)` returning a constant** — `msSinceNetActivity` never reset, so the movement scale clamped to 0.0 on frame one. Pitch is not among the three scaled axes, which is why RY survived | `abf35bb`; `DAT_0045a1ca` measured 1 (killing the rival candidate), `MoveScale f12 = 1.0` on all 332/331 calls, instance A ~~73 distinct x (539.7→337.9)~~ **65** distinct x (first→last 539.68→471.01; the struck figures were a miscount and min/max) against 1 before, B **80** (1145.28→981.87) — `research/18` §3.12 "Verified" holds the numbers to quote. **Same-binary A/B** (`5ed29ca`, one match, both legs a frame apart): fix ON f12 = 1.0 on 330/330, idle max 1490 ms, activity globals 192/192 distinct, 89 distinct x; fix OFF f12 = 0.0 on 339/339, idle 504,210 ms, globals never written, **0.46 units** of travel. Movement tracks the stick — 1.3 units at neutral vs 28-38 per hold, starting on the hold frame, axes orthogonal. Review verified every figure to 3 dp |

## 2. Believed, unconfirmed — with the experiment that would settle it

| What | What would settle it |
|---|---|
| ~~**Requiem: the joiner fails the control bar on both passes**~~ **SETTLED 2026-09-17:** on the wall-time guest clock (research/34 §6) `ours_control_requiem_clock` is CONTROL-ROUND exit 0, B's hold 0 net 128 u (was 13). It was the slow clock. | Done. |
| ~~**Foxhunt: the control round's negative control fails on fall damage**~~ **SETTLED 2026-09-17:** the driver's fall guard (a 30-unit height drop: pad neutral 1 s, the side's legs turn back; a health drop within 3 s scored apart as fall damage) -- `ours_control_foxhunt_guard`: B dropped 35 u at T+130 s, turned back, the round ran to its clock, health 1.0/1.0, no counter step, exit 0. Twenty of twenty maps play their control round. | Done. |
| ~~**The guest clock runs at 0.5–0.85 of wall time even when a round plays**~~ **FIXED 2026-09-17 (research/34 §6):** ~195 ms of VU1 and ~290 ms of render back-pressure per second were subtracted from the guest clock by the 2026-09-08 exclusion; the scheduler counts wall time by default now (`PS2X_CLOCK_EXCLUDE=1` for an A/B, 100 ms per-gap cap), both online sides read 1.00 s/s (`ours_control_frostfire_clockoff`), gate title/mission PASS. The transition floor was recalibrated (5 → 3) for the now 4 s black screen. | Done; Requiem (row below) is expected to pass on re-run. |
| **21k texture uploads a second in an online round even with stable CLUT ids** (45 ms/s of render time; was 64k/s with the cache exploding). Textures whose pages take a shadow-generation bump every frame are re-decoded — the palette rewrites likely share a page with a texture.  **Re-measured 2026-09-17/18 (Sprint 7 Task 3): gameplay uploads ~10k/s at 20-28 ms/s in two online rounds' stats lines; the MENUS are the expensive screens at 7-11k/s and 80-133 ms/s; the boot loads reach 35-46k/s. The page-marking cause below (§2) was refuted by its trace.** | `PS2X_GS_STATS=1` plus the `[gs-pages]` trace on the HUD/skin texture pages; the cache key's page span. |
| **Second, separate GS defect on the streamed full-screen image path** (`FUN_001c6570`, decomp 45100/45108): the guest advances DBP by writing the halfword at **packet offset 0x14** each iteration, but our `sceGsSetDefLoadImage` stub writes a 12-byte `GsImageMem` at offset 0 and `sceGsExecLoadImage` re-reads only those 12 bytes — so every strip of a streamed loading-screen image goes to the same DBP. **Not** fixed by the ×8 correction | research/25 §9 verification. Settle: read the packet's DBP halfword at exec time, then compare a loading screen against the console |
| **FIXED 2026-09-15 (`a81eb74`), promoted to proven:** the ×8 dropped (`vram_addr & 0x3FFF` is the DBP/SBP field); a seven-region round trip in `ps2_gs_tests.cpp` failed on the old code with every block pointer off by 8 and passes now (455/455); gate PASS 3/3 `s6_blockptr` with the mission stage passing the mission-failure detector after the 3 s turn that ended `s6_depth_m5` in MISSION FAILURE; `motion_pack_check` on the 255 s RAM dump reads `corrupt_chunks=0 of 8` against 5 of 8 on every pre-fix spawn image and identity on the console. Still owed: a live `rx`-hold teleport count from the guest-value probe (`s6_probe`). Row kept as written: ~~**Our `sceGsExecLoadImage`/`sceGsExecStoreImage` HLE multiplies the BITBLTBUF block pointer by 8**~~ (`Kernel/Stubs/GS.cpp` ~:641 and ~:706 computed `vram_addr * 2048 / 256`). At the single-player mission load the game parks 1.75 MB of VRAM in the motion-pack buffer as seven 0x40000 pieces (`FUN_003b1990(0x2400, …, 0x1c0000)` / `FUN_003b18d0`, `vram_addr += 0x400`); with the ×8 the seven block pointers mask to 0x2000/0/0x2000/0…, so the restore writes [6,5,6,5,6] over chunks 0–4 — the motion smear, and so the turn teleport. A block scan of our RDRAM images reproduces the pattern; the stray 0x40000 copy at ~`0x1d2b000` is the load stub's freed `guestMalloc` packet. **Independently CONFIRMED 2026-09-14** (re-derived from the decomp, the runtime source and the dumps): the game's own libgraph writes DBP/SBP unscaled (`FUN_001a2520`/`FUN_001a2708`), so `vram_addr` **is** the block field (256-byte blocks, 14 bits, 0x4000 blocks = 4 MiB) and the ×8 is wrong by exactly 8; 0x2400·256 + 7·0x40000 = 0x400000 exactly; the game hand-patches DBP by +0x280 per 0x28000 bytes (decomp 45108), which fixes both unit and width. Observed smear `[6,5,6,5,6,5,6,7]` on three of our spawn dumps, identity on the console and on `title_ours`; our buffer chunks {0,2,4,6} are byte-identical to each other and {1,3,5} likewise — the two-VRAM-block signature; chunk 0 vs the console's chunk 6 differs only by the −0x2d00 pointer relocation. **Smoking gun:** the leftover load packet in `spawn_ours_vf0_t200` decodes as `BITBLTBUF DBP=0x2000` for the piece whose correct DBP is 0x3C00. Refinements: the **load** parks and the **store** restores (research/25 §9.1 has the direction backwards); chunk 6 is correct by luck always, chunk 5 usually — the odd pieces alias to VRAM block 0, the live framebuffer front, and one run shows 16 KiB drawn over it | research/25 §9. Settle: the paused verification (units at the three sibling call sites, the alias table, dumps vs console), then the two-line fix + a seven-region round-trip test in `ps2_gs_tests.cpp` (the existing single-region test is lossless either way), full gate for blast radius (the same stubs carry loading screens, movies, textures), and an offline descriptor-by-name check vs console, 48 → 0 |
| ~~**The Seeding Chaos grey shards come from the `0x34` env-map pass' geometry or its texture/CLUT** (TBP0 0x38a8 PSMT8, CBP 0x3852 CT16) — what is left after the depth theory died. The footprint is right and the console shows continuous brown water at the same camera, so something inside the correct silhouette is drawing wrong~~ **SUPERSEDED 2026-09-16/17:** the shards were VU1 chunk truncation, fixed by the VIF wait plus the brighten/exposure HLEs (research/31 §15–17, commits `3d37abc`, `545b85a`, `c63729d`); what remains is the VU0 macro-mode flag latency (research/31 §17), which is a recompiler item, Sprint 8. | Done (see research/31 §15–17). |
| ~~**Health `+0x1044` and alive `+0xF7A` at a death are still unread live.**~~ **Settled 2026-09-13 by ladder launch 2 (§1): `+0x1044` → 0.0, `+0xF7A` 1 → 2 → 3, word 0 intact online.** Kept as written: SP (Task 2, 3 usable runs): `+0x1044` 1.0 → 0.978 → 0.721 and 1.0 → 0.392, each after a teleport landing; `+0xF7A` 1 on every live row; no death. At run 3's MISSION FAILURE the actor was destroyed (word 0 → base vtable `0x4061c0` from destructor `FUN_0029ed30`, then heap data); KillWatch reads only vtable-intact blocks and did not fire (replays 1588/0, 589/0, 1454/0). Armed as harness defaults | The first online death (Task 5 rung 3) |
| **Frostfire's lost control is the online snap-back fed by a ground probe that never hits.** *(Cause fixed by `b625291`; online restoration proven in §1 — this row keeps the mechanism for the record.)* `FUN_00594cf0` (`0x594ec4`) suppresses MoveScale when `0x45a0c1 && 0.6 < clock(0x4365c0) − actor+0x420`. `actor+0x420` is the last ground-hit time, stamped per frame only by `FUN_005b0420`'s hit branch (actor `vtbl[0x20]` `FUN_005506a0` queues via `FUN_005b0840`; `vtbl[0x24]` `FUN_00550570` → `FUN_005b0800` batch → `FUN_005b0420` → `FUN_005b5d40` eval). On launch 1 `+0x420` was never written (A 0x0, B uninitialised 0x102, every row) and `+0x1061` bit 0x04 (the miss branch) was set from the first frames on both sides; MoveScale stopped between clock 0.383/0.616 (A) and 0.550/0.783 (B). Single-player images of ours and PCSX2 stamp `+0x420` = clock; on kill2's map it tracked the clock. R6 firing: **verified, bracketed**; probe miss: **inference, strong**; why it misses: ~~open — leading candidate: the collision grid is exhausted and its cell chains cut~~ **exhausted grid RETRACTED for Frostfire** (launch 2, `logs/run_[AB]_20260913_100624.log`, `logs/parity/frost{A,B}_probe600.rdram`, review re-derived: 503 nodes + 7689 free = 8192, free head never 0 over 1988/1964 rows; still stands for `spawn_ours2`'s chain class). **Probe miss PROVEN:** ProbeEval returns 0 with candidate count 0 on 1450/1450 local records while GridQuery returns 1 — the ground is not in the queried cell. The ground models carry T = (960, 0, 800) in their own matrix (e.g. `0x11a4e20`, world quad under A at y 100) but are linked in cells (0,0)/(0,2) — their untranslated bounds — instead of (4,3)/(3,7). The load-time insert (`FUN_0031d6f0` → `FUN_002d7580`) ran on **StartThread thread 7** (`FUN_001ebda0`, pc-sampler). **Cause VERIFIED offline** (`b625291`, M51 census on `logs/parity/spawn_ours_vf0.rdram`: all 48 translated props now by world bounds, e.g. T (3827.66,…) in (21,19) as on `spawn_pcsx2`, 0 by raw; "inserted before placement" excluded); the online chain awaits Frostfire launch 3. Mechanism: the bounds transform `FUN_003085c0` does `vmaddw.xyz vf9, vf7, vf0w` (`0x308608`) and our StartThread contexts have VU0 **vf0.w = 0**; the same signature shows on M51 (48 translated props at (0,0) on ours, by world bounds on the console) | Fix `R5900Context()` vf0 = (0,0,0,1), then the post-fix M51 census (all 48 translated props by world bounds) and Frostfire launch 3 (ProbeEval count ≥ 1, `+0x420` stamped, MoveScale continuing) | Frostfire launch with traces `ProbeQueue 0x5b0840`, `ProbeBatch 0x5b0800`, `ProbeEval 0x5b5d40` (`[ret] v0 == 0` = miss), `ProbeTake 0x5b0420` and dump `ProbeEval:a1:19,ProbeEval:a1+0x48*:16`: candidate count 0 → collision absent/not loaded; > 0 → the candidate filter rejects them |
| ~~Which of `I`/`K` (right stick up/down) raises the muzzle~~ *(believed settled 2026-09-13 by camera-orbit inference: `ry=0` (I) raises the muzzle — research/22 §3.2; damage is the ground truth)* | One timed pitch hold measured against the elevation of a target of known height difference. The engagement sweeps both ways precisely because this is unknown |
| ~~**Frostfire's lost control may be UNINITIALISED MEMORY, not a movement defect.**~~ **CAUSAL HALF RETRACTED 2026-09-13 (launch 1, `logs/run_[AB]_20260913_073548.log`, review re-derived):** `ng+0xd2` went 0xAF→0 around `FUN_001f6660` `#0` (A ln11143/11160, B ln10856/10867) 1.7 s **before** `FUN_002b7d60` read it; `FUN_00543d50` had 0 calls (all callers `jal`, hooks live); `+0x174` never 8. The chain is reachable and did **not** fire; the 0xAF-vs-0 byte difference stands but is not the cause. Kept as written: Bytes the game never initialises in the round-state object read `0xAF` on ours and `0x00` on the console — among them `+0xd2`, the flag behind "You are a ghost. You will play the next round as a real player", tested by five online routines. The object is allocated per map from our replacement heap, so the garbage can differ by map, which would explain Medley working and Frostfire not. The difference is verified; the causation is inference, and new-round code does clear the flag. **Reproduced by tool** (Sprint 5 Task 4 leg 0, `ad32088`, review re-read the bytes): `object_diff.py --static 0x437ce8:0x14c` over `title_ours`/`spawn_ours3` vs `title_pcsx2`/`spawn_pcsx2` finds the block at `0x869360`/`0xc496b0` and flags `+0xd2..+0xd4`. research/19 F3's range list is **wrong in three places**: `+0x6C..+0x7B` is real differing data (only `+0x7C..+0x83` is fill); `+0x100..+0x103` is zero on both sides; `+0x38`, `+0x3A..+0x3C`, `+0x3E..+0x3F`, `+0x14B` are flagged and unlisted. The flag rule needs one constant across *all* of ours' images, so its counts are a lower bound. **Mechanism now verified in the decomp and ELF bytes** (Sprint 5 Task 1 Step 1 review, 2026-09-13): once per player creation `FUN_001f5e70` → `FUN_002b7a90` → `FUN_002b7d60` reads `ng+0xd2`; when not JoinAsSpectator and `+0xd2 != 0` it calls `FUN_00543d50(local actor)`, which zeroes `+0x1044` and calls actor `vtbl[0x90](8)` = `FUN_0058a6b0` → **`actor+0x174 = 8`**, so the `FUN_00551ec0` guard dispatches `FUN_00592560` instead of `FUN_00594cf0` and MoveScale stops. The chain is verified; that it **fires on Frostfire** (and why not on Medley) is still inference. `CZNetGame` is allocated `FUN_002ad290` → `FUN_00180e10(0x14c)` → `FUN_00181b40` → **bound `malloc@0x00194C30`** → `guestMalloc` (no pool carving), so `PS2X_GUEST_MALLOC_ZERO` (`03d3aa6`, default off) does reach `+0xd2` | Launch 1: peek `*0x408c58+0x174:1`, trace `0x543d50:SpawnDead` (its `ra` `0x2b7ea0`/`0x2b7eb0` = the ghost branch) and `*0x437ce8:64`; SpawnDead from the ghost branch + `+0x174 == 8` + `ng+0xd2 != 0` → the zero-fill A/B |
| **On Frostfire the local move path ran for 0.6 s at round start and never ticked again** — 18 calls (`#0`-`#17`) between t=371.4 and t=372.0 s while 2634 peek rows kept arriving (Medley's kill2 runs ~5560 calls over 293.6 s = 18.9/s), with the pad reaching the guest, the movement scale at 1.0 and the round clock running. Reads as control never being handed over, not as a slow map. **Two leads from the same logs:** both actors read `+0xd0/+0xd4` = **1/1** and `+0x20c` = **0** for the whole run, where every Medley actor reads 8/5 and 4/7 — a *state* difference; ~~and in `FUN_00594cf0` the move-scale call sits inside `if (cVar7 == 0)`, so the multiplayer snap-back — **excluded only on Medley** — would produce exactly this picture.~~ *(2026-09-13, first note: "host wall clock, a coincidence" — itself **retracted the same day by launch 1**: the snap-back did fire at guest clock 0.6 s; frost1's 0.6/0.5 s host windows were that threshold seen at 0.1 s resolution. See the ground-probe row above.)* reCOM names the likely state: `mp_major_game_state`, `late_joiner` (`research/11`). Frostfire spawns are 692 units apart (Medley 1485) with a 42-unit height difference. **One run; §3.12's movement fix is proven on Medley only** | A zero-launch pass mapping reCOM's round-state names onto the round-start path, then one relaunch with `PS2X_CALL_TRACE_EVERY=1`, a trace on the **caller** of `0x553dc0`, the snap-back timestamp pair, and the `0x200` idle counter |
| **Valve name pointers are registry-allocated and platform-specific**: ours are identical in all 15 of our RDRAM images (e.g. `mp_round_count` 0x006b7f30), the console's differ non-uniformly (+0x20/+0x30/+0x40). Identify a valve by its name bytes (`**:3` peek), never by a pointer copied across platforms. Proven for single-player/menu images; **online too** — launches 1c, 3c and 8c identified all nine valves by name bytes on both instances | First online peek of `*0x437ce8+0x0c**:3` on ours |
| ~~**`sceGsSetDefDBuff` reads its trailing args from the stack; the guest passes them in `$t0`–`$t2`**~~ **Fixed `07ffc0a`** (args via `decodeGsTrailingArgs3`, both clear packets seeded in context 1, byte-exact vs `title_pcsx2` in a unit test; gate 3/3, run-vs-run min 99.8, vram-diff 15/15). What remains believed: (both callers, 15/15 of our images vs PCSX2's 3/3), and never seeds the clear packet. The ZBUF/TEST/clear bytes look never sent, so the visible effect is believed nil; the consumed display environment (`disp[1].display`: MAGH 0 vs 3, DW 639 vs 2559, DY ~18 lines, PMODE) and zbp (0x118 vs 0x8c) also differ from the console (research/20 §4, review re-derived) | Task 4 Step 5 fix + unit test against `title_pcsx2` bytes + vram-diff; display env and zbp: a Sprint 6 A/B against a console image |
| **The mixed match (ours hosting, PCSX2 joining) can be driven end to end from the PCSX2 controller's macros** (research/18 §1's click path with its timings). 2026-09-17 leg 1: ours hosted and waited; PCSX2's cold boot was faster than the recipe's 90 s, the four CROSS presses walked into NEW GAME, no joiner. | The macro pressing on what the screen shows: PCSX2's 640x480 frame resized to 640x448 and read with the harness's title-band detectors, then leg 1 again (`scripts/parity/mixed_match.sh`). |
| **The `0x408F10` round clock is per client and starts when that client enters the round**, so a clock skew read between two machines measures entry-time difference plus drift, not server time (Sprint 7 Task 5's readout on `ours_control_foxhunt_guard`: +6.0 s skew, B entered ~5 s before A; the two spans agree to 0.05 s over 374 s). | The two-machine match (Task 5): anchor each side's clock on its own entry line; a residual over ~1 s is drift worth a row of its own. |
| Whether a parked opponent starving the mover matches **console** behaviour, or is an artefact of feeding the counter from RX bytes only (the game's own source may be richer) | A PCSX2 pair with one player parked and the other walking, same `actor+0x1368` measurement |
| ~~Which of the two skeleton candidates is real — a lerp dropping its `a·w` term, or a second writer~~ **SETTLED 2026-09-15 — the root node no longer decays**: the gate's guest-value probe read `actor+0x2e8→+0x04` at **5.5039** (console 5.50391) as the settled value over 309 rows of `s6_probe` on the block-pointer exe. The lerp `FUN_001c0768` is a vf0 w-term site, so `b625291` (vf0.w = 1) is the likely fix; which of the two candidates it was is not separated and no longer matters. Promoted to §1 by the probe being scored (R80) | `logs/parity/gate/s6_probe/summary.txt`, `PROBE root_node_y PASS ours=5.5039` |
| The transition residual strip (~1 in 5 runs) is a `refreshDirtyRows`/`executeClear` ordering artefact | No isolation test has been run; the *pre-existing on both binaries* half is measured |
| The intro-cinematic freeze (seen once, Sprint 1) is a real defect | Not reproduced since |
| The DME aux-UDP channel carries nothing at round start | Rate bound only; `PS2X_SOCOM2_NET_TRACE_ALL` now closes it |
| `sin`/`cos` have no live call sites | Direct-`jal` count only; `0x001D55B8`/`0x001D55BC` hold their addresses in a probable dispatch table |
| **The login screen runs at 12-30 fps under GL back-pressure in 4 of 10 launches** (`bp_pending=4 bp_waiters=1`, `bp_wait_ms` growing 5-52 s over the screen, the guest clock 2.8 s behind wall, one >250 ms frame; the other 6 launches sit at 59-60 fps with `bp_wait_ms` growing 130-233 ms over 25 s). A 2D menu should never wait on the GL thread; whatever the GL thread is doing there is slow on this machine and will be slower on a stranger's. The driven lobby misses are its symptom (the drive's 90 ms wall-clock press falls between two 80 ms frames). | `logs/run_A_20260917_225536.log` 269-280 s vs `run_A_20260917_222858.log` 215-225 s (pc-sampler lines). Experiment: `PS2X_GS_STATS=1` over the login screen of a slow launch, the stats line's textures=/decodes and pending frames per second against a fast one; then Task 3's page trace on the login screen's pages. Sprint 7 Task 2f latches the injected press (the harness half). Measured lead (2026-09-18, the two online freeze rounds' stats lines): the menus upload 7-11k 1 KB tiles a second at 80-133 ms/s of render time, four to six times gameplay's 20-28 ms/s -- see the decodes row. |
| **The 21k texture decodes a second: the page-marking hypothesis is falsified by its own trace, and the figure is stale** (Sprint 7 Task 3 Step 1, stop rule). `PS2X_GS_TRACE_PAGES=0x0c0:8` over an online login stage and an offline mission stage: the online log has zero decodes and zero `download gpu->cpu` on the HUD pages in 180 s; in the offline log 80% of decode frames have no preceding download and 92% of downloads FOLLOW a decode (a `gpu-dirty` source forcing a readback -- the arrow runs decode -> download, the reverse of the hypothesis). Re-measured from the stats line of two online rounds that reached gameplay (`run_A_20260917_215259`, `_220545`): gameplay uploads ~10k/s at 20-28 ms/s (not 21k at 45), submits 110-150k/s; the MENUS (login, universe, lobby, t=146-350 s) upload 7-11k/s at **80-133 ms/s**, and the boot loads 35-46k/s at 30 ms/s. | Uploads are 16x16 1 KB tiles (`upload dbp ... 16x16 psm=00 bytes=1024`, 100% of the traced uploads). Experiment for the menus' 80-133 ms/s: `PS2X_GS_TRACE_PAGES` over the login screen's own pages (find them from `resolveTexture`'s log for the menu atlas) and a per-upload cost breakdown (is it the 1 KB tile path's per-call overhead -- 10 us a tile -- rather than the byte count); the fix is then tile batching, not cache marking. Sprint 8. |
| **What the game asks the headset module for, in order, and whether serving it `HostMic` PCM is bounded** (Sprint 7 Task 9c spike, decomp + 790 run logs, no launch). Bind `'BLIP'` 0x50494c42 (`FUN_00243840`), then **0x10 `lgAudInit`** (send 0x20 / recv 0x30; the EE halts unless reply[2] == 0x108 and allocates `(reply[8] + 0x3f & ~0x3f) + 0x40` = 0x840 from reply[8] = 0x800), then **0x01 `lgAudEnumerate`** (send 0x20 / recv 0x170) and **0x0f `lgAudEnumHint`/`lgAudAEnumHint`** (send 0x20 / recv 0x20, async, EE end-function 0x245568) -- and in a real run **nothing else ever**: `grep lgaud:stub logs/run_*.log` is 3,749 x rpc=0x1 and 5,316 x rpc=0xf against 1,155 `lgAudInit` lines, the two polled forever because our stub answers 0x80000001 = 'no device'. The rest of the client table, from the decomp's `sceSifCallRpc` sites (`FUN_001a6c78(0x414980, <fn>, <async>, ...)`) named by each caller's own error string: 0x02 `lgAudOpen` (send 0x30, checks `openparam->Mode`), 0x03 `lgAudClose`, 0x04 `lgAudStartRecording`, **0x05 unknown** (shares StartRecording's message -- probably StopRecording, not proven), 0x06 `lgAudStartPlayback`, 0x07 `lgAudStopPlayback`, 0x08 `lgAudRead` / `lgAudARead`, 0x09 `lgAudWrite` / `lgAudAWrite`, 0x0b `lgAudGetMixer`, 0x0c `lgAudSetMixer`, **0x0d and 0x0e unknown** (both share StopPlayback's message), 0x11 `lgAudResumePlayback`, 0x12 `lgAudGetAvailableRecordingBytes`, 0x13 `lgAudGetRemainingPlaybackBytes`, 0x14 `lgAudPrepareForReboot`, 0x15 `lgAudWriteVag` / `lgAudAWriteVag`. **Believed bounded for Sprint 8:** the capture side is pull-shaped -- enumerate, open, then 0x12 (bytes available) / 0x08 (read) against `DAT_003dcfb4`, the one 0x840-byte buffer the EE sized from the number our own stub already advertises, so `HostMic::read` fills it and the IOP side pushes nothing on a thread of its own; the async variants carry an **EE**-side end function, not an IOP callback. What keeps it out of Proven: nothing in the tree has ever reached 0x02, so the openparam block's fields -- the rate, the channel count and `Mode` -- are undecoded, and `host_mic.h`'s 16 kHz mono s16 is still the FORMAT ASSUMPTION its header names. | Answer 0x01 `lgAudEnumerate` with one device and let 0x02 `lgAudOpen` succeed, behind `PS2X_MIC_DEVICE` so the gate is untouched, and log every following function number plus the 0x30-byte `lgAudOpen` send block and the 0x20-byte 0x12 replies. Bounded is confirmed if the EE then settles into 0x12/0x08 polling against the 0x840 buffer and the send block decodes to a rate our capture device can produce; unbounded if it expects a push or a rate miniaudio cannot resample to. |

## 3. Retracted — believed, then killed by measurement

- **"The PCSX2 golden match is the same frozen state"** (`HANDOFF.md` "Open items" item 0). False. That golden was two
  stills of a match with **no input ever sent**. Weeks of server- and protocol-directed reasoning
  were aimed at the wrong body of code. *Retracted in the tree 2026-09-13 (Task 9a): `HANDOFF.md`
  item 0 and `STATUS.md` 2026-09-10 20:10.*
- **"The grey water shards in Seeding Chaos are caused by GL depth quantisation"** (research/26 condition sentence; KNOWN §2 2026-09-14). The **arithmetic is still true** — `gs_gl_backend.cpp:2630` `z/2^32` with the shader's `aPos.z*2-1` in float32 does quantise GS z to multiples of 128, and that is worth fixing on its own — but it is **not** this defect's mechanism: a mission run with `PS2X_GS_NO_ZTEST=1` shows the *identical* shards, and a disabled depth test cannot cause a depth-test artefact. The theory had "Against: none found" written against it, which is what a single disconfirming run is for. *Retracted 2026-09-14, same hour as the run; research/26 §4 candidate 1 and this list.*
- **"The actor rests 14.7 above the ground vs the console's 20.1"** (`HANDOFF.md` "Open items" item 2; `STATUS.md` 2026-09-09 01:30).
  Both numbers are camera-eye minus collision-hit. The player's feet are right to 0.008.
  *Retracted in the tree 2026-09-13 (Task 9a): `HANDOFF.md` item 2 and `STATUS.md` 2026-09-09 01:30,
  which prints the two camera y values it was differencing.*
- **The player actor at `*0x488de8+0xbc`.** Wrong; it is `*0x408c58`, verified across
  six images including the console's. Retracted in place 2026-09-13 (Task 9a): the correct chain is
  now in `HANDOFF.md` item 0 and the misreading is marked at `STATUS.md`'s 2026-09-09 01:30 entry.
  **Attribution correction:** this was never written in `HANDOFF.md`. `0x488de8` is the *camera*
  singleton; `STATUS.md` 2026-09-09 01:30 said `+0xbc` is "the camera's follow pointer … null in
  the spawn images", and later work read a warning as a route. HANDOFF's own peeks use
  `*0x488de8+0x320`, the camera position, which is correct and stays.
- **`actor+0x204`/`+0x208` are the player's health and max health.** Wrong — health is `+0x1044`
  with an alive byte at `+0xF7A` (`research/19`). The candidates were never confirmed (zero kills to
  confirm across), which is exactly why they were kept disarmed; the one row that leaned on them
  ("no damage was dealt") is withdrawn.
- **"Frozen at STARTING ROUND 1 OF 11, waiting for a go"** (spec §1 and several STATUS entries).
  The banner is transient on ours too and the round timer runs. The true sentence is *the round
  runs and the local player cannot move* — and that is fixed (`abf35bb`, `5ed29ca`).
  *Retracted in the tree 2026-09-13 (Task 9a): `HANDOFF.md` item 0, `STATUS.md` 2026-09-10 20:10,
  and the Sprint 4 spec's own §1 bullet.* The entry that recorded the symptom also recorded "the HUD
  timer runs regardless" and that RY worked while RX/LX/LY did not — a transport failure cannot
  deliver pitch and withhold yaw. Both refutations sat in the same paragraph as the claim.
- **The `cVar7 == 0` axis-clearing arm is the movement gate** (`4114ad4`'s commit message). Rejected:
  the routine is a generic axis setter, its guard cannot fire because our own IOP module hardcodes
  link-up, and the arm returns before all four axes are written — so pitch would have died too.
  Three calls matching three dead axes was a coincidence.
- **The mover's `4.0` vs `6.3338` is a capsule radius.** It was the 15-bit `rand`.
- **`PS2X_GS_SCALE=2` will sharpen the HUD** (Sprint 3 spec DoD). It cannot: HUD, menus and title
  are textured quads at native texel density. The design doc said so before anyone measured it.

> Cite **item names and dated entries, never `file:NN`** — line numbers rot the moment anyone
> edits above them, and a dangling citation is how the actor-pointer mis-attribution happened.
>
> Retract **on discovery**, not at close-out. All of §3's first three were still false in the tree
> hours after being disproved — and in the end they were retracted **at close-out anyway**
> (2026-09-13, Task 9a), which is the outcome this note exists to prevent. The elapsed time between
> "a reviewer proved this sentence false" and "the sentence stopped being read by fresh sessions"
> was about a day for the first three and two weeks for the freeze description. The rule is in
> `docs/process-audit.md`: a review finding that a committed sentence is false produces a same-hour
> edit, and close-out *verifies* retractions rather than performing them.

## 4. Standing hazards — things that will bite again

- **A long-lived `tools_py.parity` helper blocks the loop lock's reap.** The busy list counts every python process whose command line carries `tools_py.parity` (the DNS stub for the mixed match, `dns_stub --bind ... --answer ...`, ran for two days); a stale lock (a killed agent's `build.sh test`, heartbeat 18 min old) then reads `not reaped, busy list running: <pid> python ... dns_stub` and nothing lock-bound can start. Seen 2026-09-18 02:20. Kill the helper (`taskkill //F //PID <pid>`) or start it under a name the busy rule ignores; the mixed match must restart it first (`scripts/parity/mixed_match.sh` checks port 53).

- ~~**The 989snd PCM ring lives at EE address 0x900000, inside the game's own memory**~~ **Closed 2026-09-17 (research/32 §7.1):** the ring is at 0x000A0000 now — below the ELF, above the runtime's kernel mirror, under the EE's 24-bit mask. The title music's scratch, chased through this row, was the sceMpeg HLE: callbacks out of order (the EE dispatcher stacked queued invocations last-in first-out), late (after the demux call instead of inside it), and a packet the callback refused for lack of room consumed anyway (the one-byte shift). Stopping the demux at a refusal then starved the game (it drops what a call did not consume and polls with nothing): the demux now consumes everything and sets refused audio aside. Measured: the mix correlates with the disc's PCM at 0.99 through the intro movie and the title loop. Residual: the first ten seconds after a stream starts fill short while the pipeline settles.
- **A render-thread stall does not show as a low frame rate to the guest — it stops the guest's clock** (research/34). The EE timers follow the host clock minus the GL back-pressure wait and VU1 time, so a GL backlog reads as 'the game runs but nothing moves and no timed message expires' while the network round clock keeps counting. Two of us read that as a network or round-start gate for an evening. First check on any freeze with a running HUD clock: `PS2X_GS_STATS=1` (`textures=`, `wait_ms=`) and `PS2X_CLOCK_TRACE=1` (`eeCycle` against `host`), and the guest clock peek `0x4365c0:1`.
- **The parity pipeline cannot see a defect that is present in every run** (owner question, 2026-09-14): title and
  mission scoring compare our runs to our own earlier runs, and the mission stage checks only that gameplay is live.
  So the grey water shards in Seeding Chaos (cause still open — the depth-precision theory was refuted
  2026-09-14 — visible in every gameplay gate frame since Sprint 3, reviewed repeatedly without being flagged) and a gate run that ends in MISSION FAILURE 39 s in (the
  known single-player turn teleport walking the player out of the mission area) both passed. The only console
  reference for that spot was a PCSX2 slot-8 screenshot that nothing compared against. Fix planned in ROADMAP §6
  item 5: console-vs-ours image comparison at fixed gameplay moments, and a mission-failure screen fails the stage.
  Until then, **look at the frames against a console image** before calling a render or gameplay path correct.

- **The gate mission stage can land its holds on an in-game HELP pop-up** ("You must MEET WITH MALLARD… PRESS X TO
  CONTINUE"), which pauses gameplay behind a lit HUD: `s5_head_1x` mission FAIL had 6/6 gameplay-band holds, diffs
  0.00–0.03, 1503 frame exports after gameplay start and no STALE FRAME — presentation live, game paused. The liveness
  scorer is right to fail it; the mission-only rerun `s5_head_1x_b` passed (4 live pairs). This is **not** the GS backlog
  stall (exports collapse) nor host load. Fix belongs in the mission script: detect the prompt
  (`sp_death_probe.screen_state`) and press CROSS before each hold (Sprint 6). **Fix written 2026-09-15**
  (`drive.py` `ifpopup` step before every hold of `gameplay_probe.txt`, unit-tested; reproduced first on `s6_depth_m2`,
  6/6 gameplay-band holds at diffs 0.01–0.05) — **its mission gate is owed** (`s6_depth_m3` was killed for host
  contention: a 176 s stale frame file, itself a reminder that gates on a busy host are not evidence).

- **Ladder launch contract after close-out** (`c04f9e1`, `2858774`): `ladder_frostfire.sh` pins by default (`--live` opts
  out); exit 4 = LOBBY-FAIL, 5 = CRASH (never read a crash as NO-KILL), 7 = pin failed; poll `logs/<name>.detached` and
  `logs/<name>.done`. Swapped spawns are accepted and recorded (`spawns=swapped`) but that round is NO-DATA until the route
  is mirrored. The default lock tests are a ~10 s smoke; **any `loop_lock.sh` change needs `LOOP_LOCK_SLOW_TESTS=1`
  (~16 min) before commit** — the race tests live only there.

- **Round-state facts measured at real kills** (ladder launch 2): `mp_round_count` steps **32.9–34.7 s** after a kill (spec
  §5.1.1 R60 anticipated ~5 s — no bar depends on it); the guest clock then freezes ~5.3 s; `total_mp_kills` steps only on the
  killer's instance and **resets to 0** ~5.2 s after each round step (with `aiteam_*` going 0→1 on the same row); over the
  kill windows the guest clock ran 0.70–0.91 guest s per host s (above §5.1.1's 0.57–0.72 note). Harness defects found, not
  verdict-affecting — ~~`damage=NO-DATA` for a steady-health round; RESULT `contact=False` from the retired `approach()`
  flag; frame ages not recorded~~ **fixed `98f6417`** (round slice seeded with the last value; contact from `verdict_core`;
  `screen_age_s=`/`screen_clock=` recorded, ±1 frame rewrite ~150 ms).
- ~~**The kill is not repeatable yet on demand**: 3 of 4 rounds killed in the one usable launch; round 4 fired 111 bursts at a −4.1° aim error that sat inside the angular tolerance (never corrected). Sprint 7's repeatability item needs a tighter aim tolerance or a burst-to-burst correction.~~ **SETTLED 2026-09-17:** `ebf13be`'s burst-to-burst aim correction; `s6_ladder8` 4/4 KILL, `s6_ladder12` 3/4 (round 3 a harness teleport guard, not a miss).

- **The gate's memory card is shared state, and a saved controller configuration changes the boot flow** (2026-09-16,
  three full gates lost: `s6_gamepad`, `s6_gamepad2`, `s6_gamepad3`): the owner's free-play session ran on the default card
  `game/disc/mc0` and saved the controller configuration (`BASCUS-97275SOCOMII` 4784 → 6160 B, `SCRATCHPAD.DAT`, both
  00:24), after which every boot skipped the PRECISION SHOOTER CONFIGURATION screens and the "save to memory card?" dialog —
  and the transition stage, which keys its burst on that dialog, reported "no transition burst fired". The controller
  itself was not the cause (`PS2X_HOST_GAMEPAD=0` made no difference; the knob stays, so a harness run never depends on
  what is plugged in). Fix: `gate.py` boots every stage from a fresh copy of the 2026-09-08 card `game/disc/mc0_parity`
  in the stamp directory (`PRISTINE_CARD`; an operator's `PS2X_MC_DIR` wins), and free play uses its own copy
  `game/disc/mc0_owner`. The online ladder keeps `mc0`/`mc0_b` (their personas); its boot loop adapts to either flow.
  **That card did not bring the dialog back** (`s6_fade`: the boot went main menu → rank → briefing in 45 s, no
  configuration screen), and a step-pinned fallback burst could not catch the fade either -- it happens during the rank
  press's own settle wait, at a step index that drifts with the boot (s05 there, s07 nominal). So the transition stage
  is now **scored by content** when no burst fired: `gate.score_fade` orders every capture by mtime, finds the first
  frame whose header band matches `scripts/parity/ref_briefing_ours.png`, skips the briefing's own ≤ 2 s fade-in and
  counts the contiguous black run behind it, from 5 fps wait captures (`--wait-period 0.2`). `s6_fade` and
  `s6_gamepad3` re-score PASS at exactly the 5-frame floor on their old 1 Hz captures. The boot's black screens sit
  behind the main menu and cannot join the run, which is what the burst step was enforcing.
- **FIXED 2026-09-16 (evening): the terrain holes were VU1 chunks lost to a VIF that did not wait for the VU** (research/31
  section 17): the VIF1 MSCAL/MSCNT callbacks ran every VU1 program under a 65536-cycle budget; a chunk that needed
  more was left mid-way and the next MSCNT continued it from inside the clipper with the next buffer's TOP. The VIF
  entry points now finish a pending program before the next one (`VU1Interpreter::executeProgram` /
  `continueProgram`, test-first). Measured: 96 terrain triangles per frame like the console (was 70), the stream bed
  continuous (`s6_vifwait1`). The same class explains the flat hill patch (form 2) and the run-to-run variation.
- **Open: VU0 macro-mode flag latency** (research/31 section 17): the recompiler lands MAC/STATUS flags immediately,
  hardware four cycles later; the game's 'needs clipping' test (`FUN_00294a30`) depends on it, so objects inside the
  guard band take the unclipped VU1 family on ours. Small visible effect after the VIF fix; the fix is a latency
  model in the CTC2/CFC2 translation.
- **Every gameplay frame drew 1.73x too dark, and the water shards were its symptom** (2026-09-16, research/31 §11-13): the
  game's post-process copies the frame at half size into the depth-buffer pages and draws it back with `ALPHA 0x5d00000069`
  -- A=Cd, B=0, C=FIX=93, D=Cd, i.e. Cd x 1.73 -- a brighten the GL backend mapped to an identity (no destination factor above
  one in GL; the source term now carries Cd x C: the fragment shader emits C, blend `GL_DST_COLOR, GL_ONE`). The factor itself
  comes from the guest's auto-exposure thread, which reads a 1x4 column of frame pixels through a libgraph store-image
  packet it inspects (PSM at byte 0x23, TRXREG at 0x40/0x44), patches (TRXPOS at 0x30) and DMAs through the VIF1 reverse
  FIFO: our `sceGsSetDefStoreImage` HLE wrote a private 12-byte struct there (the guest computed a zero-sized transfer)
  and `socom2_LumReadPixel` answered a constant grey pixel (the exposure saw a mid-grey scene and asked for FIX 0). Both
  HLEs now write libgraph's packet layouts (`writeGsLoadImagePacket` / `writeGsStoreImagePacket`, parsed back by
  `readGsImage`) and the readback reads the pixels out of GS memory (`socom2_lum_readback.h`). Found with the offline
  oracle: the console's own GS dump replayed through both backends (`ps2_gs_tests` 'console GS dump replays ...',
  `PS2X_CONSOLE_REPLAY_DIR` / `_GL` / `_STOP`), bisected to the packet.
- **The GS on-chip CLUT was not modelled** (2026-09-16, research/31 §9): a TEX0/TEX2 write with CLD != 0 copies the palette
  into the GS's CLUT buffer at that moment and draws sample the copy; our frontend parsed CLD and both backends read the
  palette slot's bytes at decode time. SOCOM II rewrites block 0x3852 in CT16 (the water) and CT32 (another texture) form
  every frame and the CT32 write overlaps the 0x3854 palette, so any texture whose slot was re-purposed between its TEX0
  write and its decode read the other texture's bytes as its palette. Fixed test-first (`GSClutLoad`: the frontend
  snapshots 2 KiB from the palette block at every loading TEX0/TEX2 write, contexts carry the snapshot id, both backends
  decode through it; CSM2 palettes keep the live path). **It did not move the water shards** (`s6_clut` flat 0.504), and
  neither did the VU1 interpreter (`s6_vu1interp` 0.507): the shards are on the GS side, not in the vertex data.
- **Every blind press in the online harness now costs a launch** (2026-09-15 evening, seven ladder launches on the block-pointer exe, 2 reached gameplay): each launch failed on a different press that had no read-back -- the OSK's first character (`ocom`), a DOWN before CONNECT (CROSS landed on GENDER), an ENTER-walk step, the main menu's ONLINE CROSS (`s6_ladder7`: menu still up, ONLINE lit), the map-list walk pressing through a mid-scroll frame, and a READY search that pressed UP into the started match (B spawned zoomed 3.0x; research/30). The drop rate is about one press in twenty at 59 fps, on the pad-file path as well as posted keys. Sprint 5's launches on the frozen exe hit the same class at a lower rate (R47's two re-sends). Rule: a press without a verification of the screen it should produce is a bug, not a step; the lobby now verifies every stage (`[lobby]`, `[login]`, `[osk]` lines) and `lobby_report.py` counts re-sends per launch.
- **The OSK password typing drops characters at a low guest frame rate, and the keyboard now opens in accent mode on both instances** (2026-09-15 evening, `s6_ladder2` and the Sprint 5 harness bisect `s6_ladder_oldharness`, both instances, 0/3 launches reached gameplay): B's password reached the server as `ocom` (first character lost), A connected with an empty password, the old harness typed `xmfû`; the guest ran 32 fps in the OSK window against 60 in Sprint 5 and the pad walk is dead-reckoned at 0.09 s holds with no read-back. Fix in flight: read the typed length back from the OSK text row and retype slower (research/28 §6). ~~Until it lands, every online launch on the block-pointer exe fails at login.~~ **SUPERSEDED 2026-09-16/17:** the lobby hardening (`b8d2410`..`c669185`, research/28); the twenty-map sweep reached the lobby on 22 of 24 attempts (research/33). The rate is still not a pre-registered measurement (ruling R85; Sprint 7).
- **A two-instance launch can start with a starved runtime** (`s6_ladder1`, the first double launch of the freshly built exe): 34 present windows in 490 s, the guest parked at VSync, presses received but never processed, `LOBBY-FAIL pre-login` after 9 blind boot presses; the next launch on the same harness and exe booted normally. Cause not identified (research/28 §6). Read a boot failure's `[gs-gl stats]` cadence before blaming the harness.
- **The lobby now verifies two dropped-press classes and fails fast** (`74f221c`, `a0bca51`, R47/R69): map CROSS
  (SELECTED MAPS panel diff 0.00 dropped vs 8.95 taken) and READY (label edge 48 vs 82) are re-sent up to 3 times on
  fresh frames; **READY is a toggle**, so it is re-sent only when two frames ~1 s apart both read not-ready. Every lobby
  stage times out at 180 s → `RESULT LOBBY-FAIL <class>`, exit 4. Unobserved: what a second map CROSS does on an
  already-selected map; pre-login failures (window, main menu) still exit 1 without a class.

- **The acceptance scorer `verdict_replay.py` is pinned to pre-registered bars** (spec §5.1 + §5.1.1, R50–R63, `faa7a8c`):
  two adversarial reviews found 11 false-KILL/false-FAIL holes before any ladder match (stale kill steps, cross-round
  windows, fragmented freezes, an alive byte never read as 1, a destroyed killer, and — the one that would have
  failed the only kill it exists for — a round-ending 1v1 kill scored NO-DATA). 107 tests, 68 mutations caught.
  The guest clock `0x4365c0` runs 0.57–0.72 guest s per host s and freezes from each `mp_round_count` step to the
  clock restart. Do not move a bar after a kill is seen.

- ~~**The runtime is frozen at `92d30f0` for the online ladder** (R45, R61)~~ **SUPERSEDED 2026-09-15:** the freeze lifted with Task 0; the ladder runs on the current exe (`s6_ladder8`, `s6_ladder12`). Kept for the mechanisms it records: GS back-pressure (N=3, 2 s cap, heartbeat
  latch), VBlank debt dropped on both clocks, idle guest sleeps to the later of host/cycle deadline. Known residuals,
  not fixed before the freeze: (1) a stale `m_eeCycle` can oversleep one frame after a blocking `sceInetRecv` with a
  timeout (one late frame, no drift); (2) a timer IRQ candidate is compared on the host clock only and can be up to one
  period late while the host chain lags (latent — no game log registers timer causes 9–12); (3)
  `PS2X_CYCLE_CLOCK=guest` is not an A/B of the pre-R54 path; (4) the exact-one-VBlank scheduler test can flake under
  CPU load. ~~Back-pressure waits are excluded from guest time, so each instance's guest clock trails wall clock by its own wait total — record `waits=` per instance on every online launch.~~ **SUPERSEDED 2026-09-17 (research/34 §6, ruling R81):** the guest clock counts wall time by default; `PS2X_CLOCK_EXCLUDE=1` restores the exclusion for an A/B.

- **Launch hygiene is now tooling, and it has two traps** (`5cfa5bf`, `38d1f80`): `run_detached.sh --purpose launch…`
  writes `logs/.quiet` (Windows pid — an MSYS pid made the guard a no-op until `38d1f80`) and a 1 s CPU sampler;
  `build.sh test` refuses while it is live (`FORCE_QUIET=1` overrides). **Pinned harness runs need
  `PYTHONSAFEPATH=1`** alongside `PYTHONPATH=<snapshot>`, or Python imports the live tree instead of the snapshot
  (`scripts/pin_harness.sh`). A SIGKILLed wrapper leaks the marker (bounded by its 2 h / dead-pid check) and the
  sampler (unbounded).
- **Gates are now host-load sensitive** (back-pressure excludes wait time from guest time, R41): under a heavy
  host process (Valheim 4 GB) the title's attract timing shifts ~12 s (s19 phase) and the mission press schedule,
  which runs on wall clock, lands on cinematic frames (`s5_hygiene` mission FAIL, inconclusive — same exe passed
  `s5_gsbp2c`). Run binding gates on a quiet host.

- **Online instances freeze for 3–17 s under host load** (launch 8c: round clock stops, main thread parked at
  `0x3b00a4`, memory flat ~200 MB — not the GS backlog): the other side's NetIdle then alarms (peaks 8217/10338
  ms) and MoveScale falls to ~11.5 calls/s; the live 10 s move-path rule fired three times and would end an
  `--until-kill` match. Launch 3c on the same exe had none. Keep other heavy work off the host during launches.
  **2026-09-18 (Sprint 7 Task 2e):** with research/29 §4's fields on the sampler line, a quiet and a four-core-loaded Frostfire control round both played to the clock with no 3-17 s window on either side (`s7_freeze_quiet`, `s7_freeze_loaded`); the hazard stands as written for launches that share the host with a build or a suite, which those two did not.

- **Frostfire has two floors, y ≈ 100 and y ≈ 142** *(route found 2026-09-13, research/24: the spawns connect on the lower floor through an underpass under the walkway (x 705–735, z 975–1000, headroom 41.25) and up B's ramp; launch 3c's A was stuck against the walkway railing at z ≈ 1000, not a wall between spawns; `routes/frostfire_v2.json`, min clearance 11.1/10.2; wall blocking is inferred from polygons + 3c stand-off, the movement-collision routine is not decompiled; three `door_slab` models were closed in 3c)* (bimodal in both actors' positions, launch 3c): the
  closest 3-D approach was 52.42 at dy 42 — different floors — and the same-floor minimum 168.78. An approach
  that ignores level times out without same-floor contact.
- **The harness's own `closest_3d` is not the run minimum**: `Duel.best_dist()` (`online_match_ours.py`) takes
  the minimum of each side's *latest* distance, and the pre-engagement `near` gate reads it (launch 3c printed
  166.76 against a true 52.42). Quote `verdict_core contact` instead, until Task 5 fixes it.
- **Heading from the actor matrix during walking holds is much worse than at rest** (launch 3c: p90 ~54° A /
  ~32° B on pure-forward holds with no `rx` in the prior 2.5 s, vs 1.57° SP at rest); straightness and turn
  filters explain only part of it (wall deflection believed). Aim from the matrix while stationary.

- ~~**The gate's mission stage has scored the intro cinematic since 2026-09-12 14:33**~~ **Fixed `69e2a9d`/`d2eb932`** (HUD wait requires lit bands; the scorer requires ≥ 2 moving gameplay hold pairs, mean diff ≥ 3.0, and capture count = logged holds; hold steps log `STALE FRAME`). Saved runs re-scored: s3a, famb, native_on, s3d_2x_host PASS; mission4, s5_gatefix, s5_gatefix2, s5_task1_vf0, s5_task4_dbuff FAIL. **The gate mission stage now FAILS on the current tree**: the single-player game nearly stops presenting after gameplay start (33–43 frame exports vs ~1400 live; all holds stale; working set ~15 GB reported by hand, not captured) — cause found (stall investigation, run `stall_gsstats`, `PS2X_GS_STATS=1` + memory sampler): **`GSGlBackend::record`/`Present` append to `m_pending` without bound**; after the mission loads the GL thread replays ~14 frames/s against 60/s recorded, so private bytes go 275 MB → 13 GB in 4 min and host frames arrive one per 5–25 s. **The "live" gate runs (s3a, famb, vf0, dbuff) never held on real gameplay** — only the cinematic or a HELP pop-up. Not caused by CROSS presses, runtime commits or paging (pagefile on D:). Fix in progress (R35, bounded backpressure). Kept for the record: (Task 2 review, confirmed on
  `s5_task4_dbuff`): `drive.py`'s `untilref(ref_hud_ours.png, 92,112,125,160,40,30)` compares after
  `crop_to_content` strips the letterbox bars, so the letterboxed cinematic matches (distance 23–29 < 30) with 0
  presses, and the hold captures (s30…) are the cinematic. **"PASS mission" proves the mission loaded and the
  script ran, not gameplay.** The reference image itself shows a HELP pop-up. Gameplay = lit letterbox bands on
  the uncropped frame (`sp_death_probe.screen_state`).
- **Real actor teleports in single player** — **FIXED 2026-09-15 (`a81eb74`, the GS block pointer; see §1's promoted row): the gate's mission stage on the fixed exe stays in the mission through the 3 s right-stick turn (`s6_blockptr`), where the previous exe reached MISSION FAILURE (`s6_depth_m5`); the probe's teleport count on a live run is still owed.** Kept as written: **cause located 2026-09-14** (research/25 §7–§8, traced run `logs/run_sp_20260914_122711.log`, independently re-derived by clip name): the animation pack `run/motion_p.zar`/`motion.rdr` (buffer `*0x415e08`, ours `[0x86d840, 0x9ad840)`) has its first 0x140000 bytes **overwritten during the single-player mission load** (repeats offsets 0x140000..0x1bffff at period 0x80000); 48 of 99 clips get corrupt keys descriptors (console 0), e.g. `seal_crouch_step` (#64) loses its no-root-motion flag and samples a rotation track as root translation → up to ~1875 u/s. Intact at title/menus/online; smeared in every SP spawn dump. Not water-specific. ~~**The overwriter is not yet identified** (prime suspect: our 989snd `StreamSafeCdRead` emulation).~~ **SETTLED (research/25, `a81eb74`):** the GS block pointer was the cause; `StreamSafeCdRead` writes only to the guest-supplied address. Original entry (Task 2, `e685b82`, review re-derived): 45 of 47 row steps > 30
  units fell inside `rx` holds with |Δ| ≥ 64 (up to 380 units per 4 Hz row, velocity words to −2462), also 86
  units without `rx` on the vf0 build; the camera and matrix row 3 follow, so the motion is real. Online kill2's
  full-deflection turns moved ≤ 4.7 units with velocity words at 0 — a different path, so online
  partial deflection is **untested**. Candidate: root-motion accumulate `FUN_0028c250`.

- ~~**VU0 `vf0` is (0,0,0,0) on every guest context except the main thread's**~~ **Fixed `b625291`** (`R5900Context()` sets (0,0,0,1); gate 3/3, title run-vs-run min 99.8, mission frames ≥ 99.0, vram-diff 15/15). Kept for the class: (verified in source, launch 2
  review): `R5900Context()` memsets it; `EeScheduler::startThread`, `GuestThread` and `GuestInvocation` contexts
  (threads, interrupt handlers, alarms, HLE invocations) start there; only `ps2_runtime.cpp`'s main context and a
  completed VU0 microprogram set (0,0,0,1). On hardware vf0 is the constant (0,0,0,1). Every `…w` op with ft =
  vf0 on those threads loses its w-term: point transforms `FUN_003085c0`/`FUN_00308640`, normalize
  `FUN_001bfcc0`, lerp `FUN_001c0768`, `vdiv Q, vf0w` sites. Writes to vf0 are already compiled out (`ea026de`).

- **`build.sh test` now needs working loopback UDP** (`socom2_libnetb_tests.cpp`, `3899b1e`): MiniTest has no skip,
  so a sandbox or firewall that blocks loopback sockets fails the suite outright.

- **The online harness now refuses to spend a match proving nothing** (Sprint 5 Task 3, `24db942`/`42b1dd8`):
  a control precondition (up to 4 two-second holds after 11.5 s neutral; exit 3 `NO-CONTROL`), a
  move-path watch that refuses to start without MoveScale traced at `EVERY ≤ 20`, valves identified by name
  bytes, `NO-DATA` wherever rows are missing. Consequence: a Frostfire run now **ends ~70 s after liveness**
  — a diagnostic launch that needs the rest of the round must say so. Mutual standing is safe on kill2's map
  (39.6 s both neutral, MoveScale f12 = 1.0 throughout).

- **Guest VU memory outside `[0x11004000, 0x1100C000)` aliases into RDRAM.** `Ps2IsPhysicalSpecialAddress`
  leaves out VU0 micro memory 0x11000000–0x11003FFF and VU1 data 0x1100C000–0x1100FFFF, so recompiled
  accesses there, and every libc stub (`memcpy` via `getMemPtr`), hit `rdram[addr & 0x1FFFFFF]`. Latent in
  SOCOM II: the only such callers (the Nellymoser VU0 voice codec `FUN_00252150`/`FUN_00252098`) sit behind a
  mode whose setter is unreferenced (research/23 review). Fixing it changes every recompiled hardware access.

- **`PS2X_HLE_STATS` and `PS2X_CALL_TRACE` miss tail calls.** Recompiled `J` to a stub becomes a direct C++
  call that skips the dispatch table (e.g. `sub_00243298` → `sub_00194C30`); ~50 sites over 19 stubs (memcpy 10,
  iWakeupThread 7, free 5, memset 5, …). Their counts undercount and a "zero-call" row can be false (Task 1
  Step 2 review, `03d3aa6`). Nine `socom2.toml` stubs (`sceCdInitEeCB`, `sceDmaGetEnv`, `fclose`,
  `sceDeci2ExReqSend`, `sceSifRegisterRpc`, `sceSifLoadElf`, `sceMpegAddBs`, `sceMpegGetDecodeMode`,
  `sceVpu0Reset`) are declared but never registered and have no static callers.
- **Title s14 has a pre-existing two-way run-vs-run split** (98.8 across groups, ≥ 99.7 within) seen since
  `s4_rand2`/`s4_rand3`; a single s14 at 98.8 is not a regression.

- **The camera does not tell you which way the player faces.** `atan2(actor − camera 0x416054)` taken just
  before a forward hold has p90 error **23.85°** over 9 clean at-rest holds (kill1–3, both sides), and
  **~55°** over 117–132 holds with a looser rest gate; the big errors follow an `rx` turn 1.2–2.5 s earlier,
  i.e. the camera is still settling (Sprint 5 Task 2 Step 1, `d0f4ccb`, review reproduced). Aim from an
  actor-side heading or a measured displacement, never from the camera.

- **The peek sampler's period is not constant under load** (Sprint 5 Task 3 Step 0, `736193c`/`afe98da`,
  measured on `run_B_20260912_231341.log`): kill2 B ran 0.25 s/row until ~620 s, then ~0.6 s/row with
  gaps to 1.08 s around the closest approach. Any row-count bar (contact ≥ 20 rows) means a different
  duration under load — report the period beside it; `verdict_core` bridges gaps ≤ 1.25 s.
- **Offline A/B clock alignment is a method, not a fact**: kill2's closest approach reads 50.0 on the
  Sprint 4 alignment and 45.9 (dy 43.9) aligned on MoveScale `#0`. Quote the alignment with the number.

- **The gate proves regression only.** It was blind to the 15-bit `rand`, the skeleton decay and the
  soft-double chain. A green gate means "no worse than the reference", never "correct".
- **Our HLE returning a constant where the guest expects a live value** — three for three this
  sprint (`rand` over a frozen seed; `0x200` never advancing; stale-register math returns). Presume
  remaining gameplay wrongness is this shape until shown otherwise. **Widened by `research/19`:**
  the same class includes memory the game never initialises and our replacement heap fills
  differently from the console's (`0xAF` against `0x00`) — a stub need not be called at all to hand
  the guest a wrong value. The cheap test that caught all
  three costs no run: dump the suspect word from several of our RDRAM images **and** the PCSX2
  console image — identical across all of ours and different on the console's is the signature.
  Written up in full at `STATUS.md` 2026-09-13, with the per-defect detail in `research/17` §5.1
  (soft doubles) and §6.1 (`rand`).
- **The title gate passes at 16 of 23.** A pillarboxed run scores 18 — a pass with margin. The crop
  fixed silent score degradation and left the geometry itself unchecked. Assert the client rect.
- **The online harness can produce complete, convincing evidence of nothing.** One run drove sixteen
  stick probes and wrote sixteen screenshots against a lobby keyboard. **Verify `peek @416054` is
  non-zero before believing any movement claim from it.** Three of six runs were unusable.
- ~~**`build.sh test` runs zero Python tests.**~~ **Fixed Sprint 5 Task 0 (`2b7c425`):** `build.sh test`
  runs `python -m unittest discover -s tools_py/tests -t .` first (233 tests at `b3ac62b`); the three
  pytest-style files moved to `tools_py/tests/`; `test_test_hygiene.py` fails on a test discovery would miss.
  **New hazard it creates:** discovery runs every `tools_py/tests/test_*.py` in the shared tree, tracked or
  not — another agent's red TDD file fails everyone's `build.sh test`. Read a red run's failures before
  blaming your change.
- ~~**Nothing reaps the loop lock**, and `take` is non-atomic.~~ **Fixed Sprint 5 Task 0** (`2b7c425`,
  `7955c10`, `884ee63`, `b3ac62b`; three review rounds each reproducing two-holder races): `mkdir` claim,
  record inside the claim dir, every transition under a token-named mutex, heartbeat reap at 15 min with an
  empty busy list (caller's ancestors excluded), `run`/`run_detached.sh` renew and print `LOCK LOST`.
  **Residual, accepted:** two holders remain reachable only when a reaper stalls ≥ 30 s at a one-command
  window (a sleeping machine), which any lease lock without kernel locking has; the loser's renew reports
  `LOCK LOST` within one interval. Blind: a hung job whose wrapper keeps renewing is never reaped.
- **`PS2X_PEEK` caps every item at 64 words, silently** (`game_overrides_socom2.cpp` peek loop, Task 0
  preflight). Split longer items; an item whose chain does not resolve is skipped, so count rows.
- **`git add X && git commit` commits the whole index, not X.** With several agents sharing one
  working tree, that sweeps another agent's staged files under your message — it happened to
  `872d8d6`, which carries five of Task 8's files under a `docs(known)` subject. Always commit
  with an explicit pathspec (`git commit -- <paths>`), never a bare commit after an add.
- **Task reports live in gitignored `.superpowers/sdd/`** and die with the workspace. Anything
  durable must be copied into a tracked doc before close-out. *Sprint 4's carry was done
  2026-09-13 (Task 9a):* the HLE hazard and the Tasks 6-8 harness rules → `STATUS.md` 2026-09-13;
  Task 4c → `research/17` §5.1; Task 4b → `research/17` §6.1; Task 1's `movie_blocks.py` limits →
  `research/16` §9.1.1. Everything else in those reports is accepted as lost.
- **`movie_blocks.py` is wired into nothing** — not `build.sh`, not the gate, not any committed
  script — so four review rounds of hard-won properties (monotonicity, arrangement-invariance,
  per-screen furniture) are held in place by no automation at all, and its `--furniture-baseline`
  guard, the only thing that catches corruption being learned as furniture, is opt-in with no
  saved baseline in the repo. `research/16` §9.1.1.
- **This harness costs about two runs per result.** Four of Task 6's runs failed to reach gameplay,
  three of them consecutively; each had written a full set of convincing screenshots first. Budget
  for it when planning, and never skip the liveness check.
- **An instrument that emits zero rows is a failed run, not a quiet one.** Task 6's idle-ms trace
  logged nothing for a whole session because it pointed at `0x30be80` while the guest calls the
  thunk at `0x30cd80` — inside the very task that wrote the warning about checks attesting to
  nothing.
- **A parked opponent starves a *stuck* mover.** The movement scale is fed by received bytes, so
  when A is pinned on geometry and B is parked, A's own scale decays to 0.0 — 19 of 821 rows,
  all inside two windows where A moved 2.5 units. It forbids "stall against geometry while the
  target is parked", not long approaches as first written. Keeping both players moving removes it
  under either causal reading.
- **`respawn` is a ROUND END, not a kill, and an acceptance test must not call it PASS.** A round
  ends on its clock too, so a timeout longer than the round turns "the round ended" into a pass for
  a test whose acceptance is a kill — the same defect as the `MediusPlayerReport` one, one level
  down. `PASS` is now reserved for `health`; a bare `respawn` prints
  `ROUND-END (unattributed -- NOT a kill)` and exits non-zero.
- **An index into `PS2X_PEEK` is not a stable address.** The first health-arming path guarded on
  word 0 of the *health* item, so `--health-item 2 --health-word 2` checked `0000ff00` against the
  actor vtable, could never be true, and would have reported "health never moved" from an
  instrument that never read. Find the actor block by its **vtable**, then resolve offsets against
  that block's own address.
- **A `MediusPlayerReport` in the Medius log is NOT a round end.** It is a periodic client stats
  report: in `ours_task8_kill1` exactly one arrived, at T+156.7 s, with the two players 603 units
  apart, both still walking and no respawn in either position record — and the harness printed
  `RESULT PASS signal=server` for it. `KillWatch` now records it and never fires on it.
- **A finished `drive.py` kills the NEXT run's game.** Its cleanup runs
  `taskkill /F /IM socom2.exe`, so an earlier driver reaching its own end takes down whatever is
  running now: `run_t8probe2` died 66 s in, the log froze at 127 sampler rows, and `drive.py` went
  on screenshotting a dead game for another four minutes. Kill the previous driver, not just the
  game, before starting anything.
- **The liveness rule counts non-zero position rows, not DISTINCT ones.** ~~`ours_task8_kill3` lost
  its second mover exactly there: 161 in-game rows, movement scale 1.0, and the record moving
  **0.00** units across a forward hold, a turn and a second forward hold.~~ **Retracted 2026-09-13
  (Sprint 5 Task 3 Step 0, `736193c`; review re-derived from `run_B_20260912_232834.log`):** B was
  controllable. The 0.00 was the **camera record `0x416054`, which froze** at (1137.72, 80.82, 84.51)
  from 441.5 s to 465.75 s while the **actor** (vtable `0x6691a0`, words 7/8/9) walked ~65 units on
  the first hold and ~39 on the second. Lesson that stands: **the camera record is not a liveness or
  movement signal — score control from actor rows only.**
- ~~**The approach loop's distance is 2-D by construction**~~ **Superseded by `d75ff33`**, which reads
  the actor's own x/y/z and gates contact on 3-D range AND `|dy|`. Kept for the lesson it carried:
  "contact at 33 units" once meant a 45-unit height difference and no line of sight at all.
- ~~**The online lobby flow reaches gameplay about 4 times in 10.** Task 7 fixed four harness defects and left `host_game`/`join_game` fixed-press navigation untouched. Budget for it.~~ **SUPERSEDED 2026-09-16/17:** the lobby hardening (`b8d2410`..`c669185`, research/28); the twenty-map sweep reached the lobby on 22 of 24 attempts (research/33). The rate is still not a pre-registered measurement (ruling R85; Sprint 7).
- **Closure efficiency quoted per side double-counts the same gap** — kill2 recomputes to 107.6 %
  and 119.2 %, impossible for one mover. Use team-closed over team-walked (kill2 ≈ 58 %,
  kill1 ≈ 33 %). A mined corridor's path efficiency is an idealised upper bound, not a closure.
- **Camera+facing reconstruction under-reports separation by 25-47 units, consistently.** Measured
  on the committed sim, whose world has **no vertical dimension at all**, so the error is purely
  the orbit reconstruction: reported-best vs ground truth `converge` 40.3 vs 64.3, `route` 23.4 vs
  30.7, `caps` 157.6 vs 204.7 — the same failure the live match showed (believed 33, true 45-93 in
  3-D), reproduced offline. The actor's own x/y/z are at actor words 7/8/9 and are already peeked.
- **`sim_walk_to_b.py` is wall-clock-timed, so its per-scenario numbers vary run to run.** One
  reviewer run gave `maze` 29 steps/206 s against a report's 14/102, and `route` 30.7/58.2 %
  against 40.9/65.1 %. Read those tables as illustrative; do not tune against them as constants
  or a slow machine reads as a regression.
- **A stale number is more dangerous than a false sentence.** A false claim reads as something a
  reader can challenge; a superseded measurement carries no visible sign at all. This sprint's own
  retraction task quoted a retracted figure into a tracked document, and this list carried two
  contradictory generations of the same measurement for hours.
- **Striking a claim's headline leaves its consequences standing** — and the consequences are the
  half a skimming reader acts on. `HANDOFF`'s ground-height item had three live restatements of a
  frame whose headline had already been struck.
- **`PS2X_CALL_TRACE` logs the first 300 calls unconditionally, then 1-in-`EVERY`**
  (`callTraceShouldLog`: `n < 300u || (n % every) == 0u`). A short
  trace never reaches the sampling regime, so dividing its line count by `EVERY` over-states the
  rate — it made an 18-call, 0.6-second burst read as "about one a second for six minutes".
- **Existing research notes go unread unless they are put in the dispatch.** `research/11`
  (2026-09-07) named reCOM's `MP_MAJOR_GAME_STATE` and `CZNetGame` round valves — plausibly the
  round-state machine behind Frostfire and the structures behind a kill readout — and sat unused
  for six days while four agents worked the round-start blocker. Name the relevant notes in every
  dispatch, not only the obvious ones.
- **An ARMED instrument that reads nothing is not a quiet one.** The health watch fills only when
  some peeked block covers `actor+offset`, so a too-narrow `PS2X_PEEK` makes "health never moved"
  indistinguishable from "never read". The run now counts reads/misses per instance, prints them on
  the RESULT line, and fails when an armed watch read zero.
- **A test harness can manufacture a regression.** Twice in one hour the simulator failed in a way
  indistinguishable from a bug in the loop under test: two suites interleaved into one fixed-name
  temp log (`pkill` is a no-op in Git Bash, hidden by `2>/dev/null`), and the simulated world let
  back-steps and strafes pass through walls. Name temp files per process, and check the harness
  before the code under test.
- **Community absolute addresses are for PCSX2's memory layout, not ours.** Our counter table sits
  exactly 0x20 lower than the console's, so an address like `0x69xxxx` from a cheat or trainer is
  right in PCSX2 and wrong for us. Always resolve through a pointer (`*0x437ce8`, `*0x408c58`), and
  record which game build and region an address was found for.
- **A green run of a timing-dependent test is a sample, not a verdict.** The acceptance harness's
  simulator was reported passing and then failed 2 of 2 for the next person to run it. After the
  race fix it passes 4 of 5 full suites, with two genuine residual loop defects (players circling
  just outside contact range; an oscillation when the only same-height ground lies away from the
  target), parked into Sprint 5's engagement ladder. Report pass counts over repeated solo runs.
- **A default threshold can manufacture a pass — and fixing the default was not the fix.**
  `--health-range` defaulted to `-0.5:0.5`, counting a player on 40 % health as dead. Changing it to
  `-1e9:0.0` did **not** close the false PASS: the check still fired on the *first* value read, so
  an uninitialised read of `0.0` or of heap fill `0xAFAFAFAF` (≈ −3.2e-10) counted as a death. The
  real fix (`42447e5`) counts a death only as an alive-then-dead **transition** on the same actor
  address, locked by `tools_py/tests/test_kill_watch.py`, which fails against the pre-fix code.
  **Residual, parked into Sprint 5:** an actor freed back to heap fill after a genuine alive read
  still looks like a death on this one signal — which is why Sprint 5's acceptance requires three
  signals from different objects and processes. Audit the defaults *and* the first-read behaviour
  of any instrument that can declare success.
  **Two further residuals, also parked into Sprint 5**, both erring toward a false FAIL rather than a
  false PASS: a read that is neither alive nor dead (NaN, 5000.0) between a real alive read and a
  real death clears the alive state and suppresses that kill; and a respawn that re-points the actor
  address at the moment of death also misses it.
- **A count that matches is not a mechanism.** Three-calls/three-axes, and the `+8 px` bar that
  never tested ±1 px, both looked like evidence and were not.
