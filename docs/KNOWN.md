# What we know, what we believe, and what we got wrong

A living list, audited after every task. Entries are **promoted** (believed → proven) when an
artefact settles them, **retired** when they stop mattering, and **retracted** loudly when they
turn out false. Every proven entry names the artefact that proves it; every believed entry names
the experiment that would settle it. If an entry cannot do that, it does not belong here.

Maintained by whoever is running the loop. Last audited: 2026-09-13, after the Sprint 4 whole-branch review.

---

## 1. Proven — with the artefact

| What | Artefact |
|---|---|
| **The VU0 vf0 fix restores Frostfire online control** (one usable run; a second Frostfire sample and the Medley bar still owed before "fixed"): the local ground probe hits from its first call (ProbeEval 1332/1332 A, 1428/1428 B, candidates 1–3), `actor+0x420` tracks the clock within 0.05 s on every row, `+0x1061` bit 0x04 never sets, MoveScale runs at f12 = 1.0 for the whole ~302 s round; movement bar A 51.78/1.65/0.00, B 54.57/3.79/0.00; every Frostfire model gridded by world bounds; starvation peaks 1547/1441 ms. First online valve reads: `aiteam_00/08` 0→1 at round start, `mp_round_count`/`total_mp_kills`/`mp_game_over` 0, clock string counts down | Launch 3c, `logs/run_[AB]_20260913_115809.log`, `logs/parity/frost{A,B}_probe600_vf0.rdram`; review re-derived all with independent scripts |
| **The actor's facing lives in its own transform**: quaternion `actor+0x70` → `FUN_005483d0`/`FUN_00307170` → 4×4 at `+0x80..+0xbc` (row vectors; quaternion angle = −θ of the matrix; row 3 copied from `+0xf54`, not `+0x1c`). Walk direction = (−m[+0xa0], −m[+0xa8]): p90 **1.57°** over 17 live SP forward holds (13 at the spawn heading with a ~1.4° walk bias, 4 elsewhere at 0.0–1.0°), 1.43° over 11 online holds offline. Not valid within ~2.5 s of an `rx` hold | Sprint 5 Task 2, `e685b82`; review re-derived with an independent parser (589/589 quaternion–matrix rows) |
| PCSX2 plays a full online round against **our own** Horizon server, advancing to round 2 | `research/18` §1 + tracked contact sheet `docs/research/assets/18-s0-evidence.png` |
| A playing match and a frozen one produce **byte-identical** DME TCP profiles (11 BROADCAST / 30 SINGLE / 7 TOSERVER / 2 aux-UDP, same opcode histograms) | `research/18` §1; recounted from the raw log by review |
| The peer channel carries **zero** application data all match — every datagram decoded | `research/18` §3 |
| The advertised-port and shared-RSA divergences were real, and their fixes reached the wire | `acb603e`; wire bytes `4C-0E` both slots, distinct keys verified by `(m^17)^d mod N == m` |
| Neither of those fixes moved the symptom | Same runs; 3 hypotheses now falsified by measurement |
| The player's **feet** are at the right height (−145.875 vs console −145.8672); the defect is the **camera** | `research/17` §0.1, derived from `STATUS.md`'s 2026-09-09 01:30 entry's own camera y values |
| The skeleton root node decays 11.4845 → 0 while its saved copy freezes at the console's 5.50391 | `research/17` §4.1, raw trace `run_20260912_121304.log:3962-6975` |
| `rand()` returned 15 bits over a `_rand_next` frozen at 41 (host CRT's first draw) | `ede2096`; `_rand_next = 0x29` in four of our RDRAM images, live in all three PCSX2 images |
| The disputed mover field could not exceed 4.0000458 under the old mask; console reads 6.3338 | `research/17` §6; two samples a side |
| Five soft-double stubs were bound with the wrong ABI, and were **identity** at 19 of 22 sites (the 3 garbage sites are unreachable) | `db7a992`; delay-slot analysis of every call site |
| The intro-movie macroblocks were a cross-thread race on `m_currentTransfer`, not a byte-accumulator bug | `4a701f1`; deficit 3,748 → 0, MISSING 9 → 0 |
| `--vram-diff` catches a uniform ±1 px shift again after the seam budget (8/15 x, 6/15 y) | `6c017c2`, measured on real renders |
| **One player walking to the other cannot finish inside a round.** Measured closure efficiency is 39 % (758 units gained for 1961 walked) at ~15 s/step, so 1382 units needs ~450 s against a ~360 s round. Two movers is ~700 units each, ~180 s | Task 7 run `wtb2`, `logs/run_A_20260912_211009.log`; arithmetic checked by review |
| ~~**The two-instance approach closes faster than one:** 1359 units in 127 s against Task 7's 758 in 300 s~~ **SUPERSEDED — derived from the camera+facing reconstruction that was later proven wrong by up to 50 units. Use the actor-row generation below (1485.5 → 50.0 in ~127 s).** The rifle facts stand: 96 R1 injections, ammo 30/30 → 0/30, impacts on the wall ahead of the muzzle | Task 8 run `ours_task8_kill2` |
| ~~**They fought at ~90 units** (median 93, min 34.9, 3 % inside 45)~~ **SUPERSEDED by the actor-row generation below (min 50.0, median 67.9, 0 % inside 45).** Same conclusion, better instrument | Review of `9c28fe0`; superseded once `true_pos()` read the actor's own coordinates |
| **Player health is `actor+0x1044`** (float; 1.0 full, <= 0 dead) and **`actor+0xF7A` is the alive byte** (1 = alive), on SCUS_972.75 **r0001** | `research/19` (two community memory tools agree, one matched to our ELF by patch bytes); decomp compares `+0x1044 <= 0.0` for three teammates in a row, then `< 0.2` and `< 0.5`; every image reads 1.0 and 1, the console's included. **Not yet read live in an online match** |
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
| **Health `+0x1044` and alive `+0xF7A` at a death are still unread live.** SP (Task 2, 3 usable runs): `+0x1044` 1.0 → 0.978 → 0.721 and 1.0 → 0.392, each after a teleport landing; `+0xF7A` 1 on every live row; no death. At run 3's MISSION FAILURE the actor was destroyed (word 0 → base vtable `0x4061c0` from destructor `FUN_0029ed30`, then heap data); KillWatch reads only vtable-intact blocks and did not fire (replays 1588/0, 589/0, 1454/0). Armed as harness defaults | The first online death (Task 5 rung 3) |
| **Frostfire's lost control is the online snap-back fed by a ground probe that never hits.** *(Cause fixed by `b625291`; online restoration proven in §1 — this row keeps the mechanism for the record.)* `FUN_00594cf0` (`0x594ec4`) suppresses MoveScale when `0x45a0c1 && 0.6 < clock(0x4365c0) − actor+0x420`. `actor+0x420` is the last ground-hit time, stamped per frame only by `FUN_005b0420`'s hit branch (actor `vtbl[0x20]` `FUN_005506a0` queues via `FUN_005b0840`; `vtbl[0x24]` `FUN_00550570` → `FUN_005b0800` batch → `FUN_005b0420` → `FUN_005b5d40` eval). On launch 1 `+0x420` was never written (A 0x0, B uninitialised 0x102, every row) and `+0x1061` bit 0x04 (the miss branch) was set from the first frames on both sides; MoveScale stopped between clock 0.383/0.616 (A) and 0.550/0.783 (B). Single-player images of ours and PCSX2 stamp `+0x420` = clock; on kill2's map it tracked the clock. R6 firing: **verified, bracketed**; probe miss: **inference, strong**; why it misses: ~~open — leading candidate: the collision grid is exhausted and its cell chains cut~~ **exhausted grid RETRACTED for Frostfire** (launch 2, `logs/run_[AB]_20260913_100624.log`, `logs/parity/frost{A,B}_probe600.rdram`, review re-derived: 503 nodes + 7689 free = 8192, free head never 0 over 1988/1964 rows; still stands for `spawn_ours2`'s chain class). **Probe miss PROVEN:** ProbeEval returns 0 with candidate count 0 on 1450/1450 local records while GridQuery returns 1 — the ground is not in the queried cell. The ground models carry T = (960, 0, 800) in their own matrix (e.g. `0x11a4e20`, world quad under A at y 100) but are linked in cells (0,0)/(0,2) — their untranslated bounds — instead of (4,3)/(3,7). The load-time insert (`FUN_0031d6f0` → `FUN_002d7580`) ran on **StartThread thread 7** (`FUN_001ebda0`, pc-sampler). **Cause VERIFIED offline** (`b625291`, M51 census on `logs/parity/spawn_ours_vf0.rdram`: all 48 translated props now by world bounds, e.g. T (3827.66,…) in (21,19) as on `spawn_pcsx2`, 0 by raw; "inserted before placement" excluded); the online chain awaits Frostfire launch 3. Mechanism: the bounds transform `FUN_003085c0` does `vmaddw.xyz vf9, vf7, vf0w` (`0x308608`) and our StartThread contexts have VU0 **vf0.w = 0**; the same signature shows on M51 (48 translated props at (0,0) on ours, by world bounds on the console) | Fix `R5900Context()` vf0 = (0,0,0,1), then the post-fix M51 census (all 48 translated props by world bounds) and Frostfire launch 3 (ProbeEval count ≥ 1, `+0x420` stamped, MoveScale continuing) | Frostfire launch with traces `ProbeQueue 0x5b0840`, `ProbeBatch 0x5b0800`, `ProbeEval 0x5b5d40` (`[ret] v0 == 0` = miss), `ProbeTake 0x5b0420` and dump `ProbeEval:a1:19,ProbeEval:a1+0x48*:16`: candidate count 0 → collision absent/not loaded; > 0 → the candidate filter rejects them |
| Which of `I`/`K` (right stick up/down) raises the muzzle | One timed pitch hold measured against the elevation of a target of known height difference. The engagement sweeps both ways precisely because this is unknown |
| ~~**Frostfire's lost control may be UNINITIALISED MEMORY, not a movement defect.**~~ **CAUSAL HALF RETRACTED 2026-09-13 (launch 1, `logs/run_[AB]_20260913_073548.log`, review re-derived):** `ng+0xd2` went 0xAF→0 around `FUN_001f6660` `#0` (A ln11143/11160, B ln10856/10867) 1.7 s **before** `FUN_002b7d60` read it; `FUN_00543d50` had 0 calls (all callers `jal`, hooks live); `+0x174` never 8. The chain is reachable and did **not** fire; the 0xAF-vs-0 byte difference stands but is not the cause. Kept as written: Bytes the game never initialises in the round-state object read `0xAF` on ours and `0x00` on the console — among them `+0xd2`, the flag behind "You are a ghost. You will play the next round as a real player", tested by five online routines. The object is allocated per map from our replacement heap, so the garbage can differ by map, which would explain Medley working and Frostfire not. The difference is verified; the causation is inference, and new-round code does clear the flag. **Reproduced by tool** (Sprint 5 Task 4 leg 0, `ad32088`, review re-read the bytes): `object_diff.py --static 0x437ce8:0x14c` over `title_ours`/`spawn_ours3` vs `title_pcsx2`/`spawn_pcsx2` finds the block at `0x869360`/`0xc496b0` and flags `+0xd2..+0xd4`. research/19 F3's range list is **wrong in three places**: `+0x6C..+0x7B` is real differing data (only `+0x7C..+0x83` is fill); `+0x100..+0x103` is zero on both sides; `+0x38`, `+0x3A..+0x3C`, `+0x3E..+0x3F`, `+0x14B` are flagged and unlisted. The flag rule needs one constant across *all* of ours' images, so its counts are a lower bound. **Mechanism now verified in the decomp and ELF bytes** (Sprint 5 Task 1 Step 1 review, 2026-09-13): once per player creation `FUN_001f5e70` → `FUN_002b7a90` → `FUN_002b7d60` reads `ng+0xd2`; when not JoinAsSpectator and `+0xd2 != 0` it calls `FUN_00543d50(local actor)`, which zeroes `+0x1044` and calls actor `vtbl[0x90](8)` = `FUN_0058a6b0` → **`actor+0x174 = 8`**, so the `FUN_00551ec0` guard dispatches `FUN_00592560` instead of `FUN_00594cf0` and MoveScale stops. The chain is verified; that it **fires on Frostfire** (and why not on Medley) is still inference. `CZNetGame` is allocated `FUN_002ad290` → `FUN_00180e10(0x14c)` → `FUN_00181b40` → **bound `malloc@0x00194C30`** → `guestMalloc` (no pool carving), so `PS2X_GUEST_MALLOC_ZERO` (`03d3aa6`, default off) does reach `+0xd2` | Launch 1: peek `*0x408c58+0x174:1`, trace `0x543d50:SpawnDead` (its `ra` `0x2b7ea0`/`0x2b7eb0` = the ghost branch) and `*0x437ce8:64`; SpawnDead from the ghost branch + `+0x174 == 8` + `ng+0xd2 != 0` → the zero-fill A/B |
| **On Frostfire the local move path ran for 0.6 s at round start and never ticked again** — 18 calls (`#0`-`#17`) between t=371.4 and t=372.0 s while 2634 peek rows kept arriving (Medley's kill2 runs ~5560 calls over 293.6 s = 18.9/s), with the pad reaching the guest, the movement scale at 1.0 and the round clock running. Reads as control never being handed over, not as a slow map. **Two leads from the same logs:** both actors read `+0xd0/+0xd4` = **1/1** and `+0x20c` = **0** for the whole run, where every Medley actor reads 8/5 and 4/7 — a *state* difference; ~~and in `FUN_00594cf0` the move-scale call sits inside `if (cVar7 == 0)`, so the multiplayer snap-back — **excluded only on Medley** — would produce exactly this picture.~~ *(2026-09-13, first note: "host wall clock, a coincidence" — itself **retracted the same day by launch 1**: the snap-back did fire at guest clock 0.6 s; frost1's 0.6/0.5 s host windows were that threshold seen at 0.1 s resolution. See the ground-probe row above.)* reCOM names the likely state: `mp_major_game_state`, `late_joiner` (`research/11`). Frostfire spawns are 692 units apart (Medley 1485) with a 42-unit height difference. **One run; §3.12's movement fix is proven on Medley only** | A zero-launch pass mapping reCOM's round-state names onto the round-start path, then one relaunch with `PS2X_CALL_TRACE_EVERY=1`, a trace on the **caller** of `0x553dc0`, the snap-back timestamp pair, and the `0x200` idle counter |
| **Valve name pointers are registry-allocated and platform-specific**: ours are identical in all 15 of our RDRAM images (e.g. `mp_round_count` 0x006b7f30), the console's differ non-uniformly (+0x20/+0x30/+0x40). Identify a valve by its name bytes (`**:3` peek), never by a pointer copied across platforms. Proven for single-player/menu images | First online peek of `*0x437ce8+0x0c**:3` on ours |
| ~~**`sceGsSetDefDBuff` reads its trailing args from the stack; the guest passes them in `$t0`–`$t2`**~~ **Fixed `07ffc0a`** (args via `decodeGsTrailingArgs3`, both clear packets seeded in context 1, byte-exact vs `title_pcsx2` in a unit test; gate 3/3, run-vs-run min 99.8, vram-diff 15/15). What remains believed: (both callers, 15/15 of our images vs PCSX2's 3/3), and never seeds the clear packet. The ZBUF/TEST/clear bytes look never sent, so the visible effect is believed nil; the consumed display environment (`disp[1].display`: MAGH 0 vs 3, DW 639 vs 2559, DY ~18 lines, PMODE) and zbp (0x118 vs 0x8c) also differ from the console (research/20 §4, review re-derived) | Task 4 Step 5 fix + unit test against `title_pcsx2` bytes + vram-diff; display env and zbp: a Sprint 6 A/B against a console image |
| Whether a parked opponent starving the mover matches **console** behaviour, or is an artefact of feeding the counter from RX bytes only (the game's own source may be richer) | A PCSX2 pair with one player parked and the other walking, same `actor+0x1368` measurement |
| Which of the two skeleton candidates is real — a lerp dropping its `a·w` term, or a second writer | `research/17` §4.3: read the node on return from the blend and again later in the same frame |
| The transition residual strip (~1 in 5 runs) is a `refreshDirtyRows`/`executeClear` ordering artefact | No isolation test has been run; the *pre-existing on both binaries* half is measured |
| The intro-cinematic freeze (seen once, Sprint 1) is a real defect | Not reproduced since |
| The DME aux-UDP channel carries nothing at round start | Rate bound only; `PS2X_SOCOM2_NET_TRACE_ALL` now closes it |
| `sin`/`cos` have no live call sites | Direct-`jal` count only; `0x001D55B8`/`0x001D55BC` hold their addresses in a probable dispatch table |

## 3. Retracted — believed, then killed by measurement

- **"The PCSX2 golden match is the same frozen state"** (`HANDOFF.md` "Open items" item 0). False. That golden was two
  stills of a match with **no input ever sent**. Weeks of server- and protocol-directed reasoning
  were aimed at the wrong body of code. *Retracted in the tree 2026-09-13 (Task 9a): `HANDOFF.md`
  item 0 and `STATUS.md` 2026-09-10 20:10.*
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

- **Frostfire has two floors, y ≈ 100 and y ≈ 142** (bimodal in both actors' positions, launch 3c): the
  closest 3-D approach was 52.42 at dy 42 — different floors — and the same-floor minimum 168.78. An approach
  that ignores level times out without same-floor contact.
- **The harness's own `closest_3d` is not the run minimum**: `Duel.best_dist()` (`online_match_ours.py`) takes
  the minimum of each side's *latest* distance, and the pre-engagement `near` gate reads it (launch 3c printed
  166.76 against a true 52.42). Quote `verdict_core contact` instead, until Task 5 fixes it.
- **Heading from the actor matrix during walking holds is much worse than at rest** (launch 3c: p90 ~54° A /
  ~32° B on pure-forward holds with no `rx` in the prior 2.5 s, vs 1.57° SP at rest); straightness and turn
  filters explain only part of it (wall deflection believed). Aim from the matrix while stationary.

- ~~**The gate's mission stage has scored the intro cinematic since 2026-09-12 14:33**~~ **Fixed `69e2a9d`/`d2eb932`** (HUD wait requires lit bands; the scorer requires ≥ 2 moving gameplay hold pairs, mean diff ≥ 3.0, and capture count = logged holds; hold steps log `STALE FRAME`). Saved runs re-scored: s3a, famb, native_on, s3d_2x_host PASS; mission4, s5_gatefix, s5_gatefix2, s5_task1_vf0, s5_task4_dbuff FAIL. **The gate mission stage now FAILS on the current tree**: the single-player game nearly stops presenting after gameplay start (33–43 frame exports vs ~1400 live; all holds stale; working set ~15 GB reported by hand, not captured) — under investigation. Kept for the record: (Task 2 review, confirmed on
  `s5_task4_dbuff`): `drive.py`'s `untilref(ref_hud_ours.png, 92,112,125,160,40,30)` compares after
  `crop_to_content` strips the letterbox bars, so the letterboxed cinematic matches (distance 23–29 < 30) with 0
  presses, and the hold captures (s30…) are the cinematic. **"PASS mission" proves the mission loaded and the
  script ran, not gameplay.** The reference image itself shows a HELP pop-up. Gameplay = lit letterbox bands on
  the uncropped frame (`sp_death_probe.screen_state`).
- **Real actor teleports in single player** (Task 2, `e685b82`, review re-derived): 45 of 47 row steps > 30
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
- **The online lobby flow reaches gameplay about 4 times in 10.** Task 7 fixed four harness
  defects and left `host_game`/`join_game` fixed-press navigation untouched. Budget for it.
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
