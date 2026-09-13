# 19 — Community, engine and recomp resources (2026-09-13)

Scope: outside resources that bear on the four open problems in `ROADMAP.md` §6 / `KNOWN.md`:
(1) control never handed over on Frostfire, (2) kill / death / round-end readout, (3) HLE stubs
returning constants or wrong-shaped values, (4) validating against the console. Research only: no
build, no run, no loop lock. Every address below is for **SCUS_972.75 r0001**, our binary, unless
stated otherwise.

Tags: **[verified]** = I read the primary source *and* checked it against our ELF, our decomp
(`game/analysis/socom2_game.elf.decomp.c`) or our RDRAM images (`logs/parity/*.rdram`, read-only);
**[pointer]** = secondary source, not yet confirmed here; **[inference]** = my reasoning.

The offline checks used seven existing images: `spawn_ours{,2,3}`, `postload_ours`, `rest_ours{,_gq}`,
`s4rand_ours` (ours) and `spawn_pcsx2`, `postload_pcsx2`, `title_pcsx2` (console). All are
single-player Albania or shell images. **No online image exists**, so everything online-specific
below is [verified] as a structure and still has to be read live in a match.

---

## 0. Headline

1. **Health is `seal+0x1044` (float, 1.0 = full, `<= 0.0` = dead) and life state is `seal+0xF7A`
   (byte, `1` = alive).** Two independent community tools agree, one of them explicitly r0001.
   Our own decomp tests `+0x1044 <= 0.0` and `< 0.2 / 0.5 / 1.0`, and has a setter for `+0xF7A`.
   Both read `1.0` / `1` on every actor image, ours and console. **`+0x204`/`+0x208` are not health.**
2. **The multiplayer round state lives in a `CZNetGame` object at `*0x437ce8`**, and its valves
   include **`total_mp_kills`**, `mp_round_count`, `mp_game_over`, `mp_score00`/`mp_score08` (rounds
   won per team) and `aiteam_00`/`aiteam_08` (living players per team). A valve's value is the `short`
   at `valve+4`. This is a readout for kills and round end that needs no screenshot and no health offset.
3. **On our build, that object's uninitialised fields hold `0xAF`; on the console they hold `0x00`.**
   One of them is `+0xd2`, the flag that selects the **"You are a ghost. You will play the next round
   as a real player"** HUD, and which five online-only gameplay routines test. This matches
   `KNOWN.md` §4's own signature for the HLE defect class (the same value in all of ours, a different
   one on the console), with a new cause: memory the game never initialised, not a stub's return value.
   It is the best lead I found for problem 1. It is **not** proven to be the cause.
4. **Our valve pool sits 0x20 bytes lower than the console's**, uniformly. Community absolute
   addresses in `0x69xxxx` are right for the console and wrong for us. Always resolve through
   `*0x437ce8`.
5. reCOM has **not moved** since the clone assessed in `research/11` (upstream HEAD is still
   2026-06-30, "gamez: Remove all PC dependent stuff"). What it offers is in the local clone already.
   Its `znet.h` enums are still useful for reading the state bytes in item 2.

---

## 1. Findings, ranked by value to the open problems

### F1 — Health and life state: `seal+0x1044` and `seal+0xF7A` — problem 2 — **[verified]**

**Sources**
- NightFyre / bismofunyuns, *SOCOM-ARCHIVES*, `SOCOM II/Aimbot/r0001/Helper.h` (header comment
  "Game: SOCOM 2 patch.r0001"):
  https://github.com/NightFyre/SOCOM-ARCHIVES/blob/main/SOCOM%20II/Aimbot/r0001/Helper.h
  It gives `PlayerObjectPTR = 0x20440C38`, `playerPOS` (Vector3) at `+0x1C`, `teamID` at `+0xC8`,
  `playerHEALTH` (float) at `+0x1044`, and `playerNAME` (pointer) at `+0x14`.
- Zero1UP (with Harry62), *Socom2StreamData*, `Socom2StreamData/Helpers/GameHelper.cs`, built for
  PS Rewired's r0004 client:
  https://github.com/Zero1UP/Socom2StreamData/blob/master/Socom2StreamData/Helpers/GameHelper.cs
  It gives `PLAYER_HEALTH_OFFSET = 0x1044` (read as a float and multiplied by 100 for display) and
  `PLAYER_ALIVE_OFFSET = 0xF7A` (`frm_Main.cs`: `livingStatus == 1` → "ALIVE", anything else →
  "DEAD"). It also gives `PLAYER_TEAMID_OFFSET = 0xC8` (online `40000001` = SEALS, `80000100` =
  TERRORISTS, `00010000` = SPECTATOR), `PLAYER_HASMPBOMB_OFFSET = 0x87C`,
  `PLAYER_ROUNDS_SHOTS_FIRED_OFFSET = 0x594`, `PLAYER_CURRENT_WEAPON_INDEX = 0xE04`, and weapon
  pointers at `0x6C4..0x6D8`.

**Checked against ours**
- **Version.** Helper.h's patch-restore bytes match our ELF byte for byte. `0x5BF6A0` holds
  `2463ffff`, which is `decAmmoCount`'s "\xFF\xFF\x63\x24", and `0x5AB368` holds `0c0a40dc`, which
  is `TargetLockDistance`'s "\xDC\x40\x0A\x0C". It really is r0001. Its player static `0x440C38` is one
  of the four statics `KNOWN.md` already proved, and its `+0x1C` position matches `KNOWN.md`'s
  words 7/8/9.
- **Decomp, `+0x1044`.** There are 17 sites. HUD code `FUN_001f27c0` compares it `<= 0.0` for three
  squad members and `< 0.2` / `< 0.5` for the health-bar colour bands. `FUN_00562c80` tests `< 0.25`,
  and `FUN_005a33b0` tests `< 1.0 && DAT_0045a0c1 == 0`. The weapon-tick `FUN_005af930` refuses to act when
  `+0x1044 <= 0.0`.
- **Decomp, `+0xF7A`.** There are 17 sites. The setter is **`FUN_00544210(seal, state)`**, which writes the
  byte and notifies the mover (`*(seal+0xc0)` vtable `+0x34`). The constructor path writes `1`,
  and other paths write `2` and `3`. `FUN_00544210` also treats a `2/3 → 1` transition specially,
  which reads as a revive or respawn.
- **Images.** `seal+0x1044 = 1.0000` and `seal+0xF7A = 1` on all eight actor images, **including
  both PCSX2 images**. `seal+0xC8 = 84000006` in single player.

**What else sits nearby [inference]**
- `seal+0xFB4` is a float time. The HUD computes `DAT_004365c0 - seal+0xFB4 > 5.0` before offering
  "press to respawn" (`FUN_001f97b0`), so it is most likely time-of-death.
- `seal+0xFCF` is written `1` by the r0001 "Auto Respawn" code in the same archive
  (`SOCOM II/Auto Respawn Offline/Auto Respawn.txt`: `sb v0,0xfcf(s0)` after `jal 0x2B3580`, our
  `GetPlayer`). That makes it most likely `m_needs_respawn`.
- The HUD tick `FUN_001f7ff0` branches on **bit 4 of `seal+0xE1`** into normal HUD, "you have died" or
  spectator text. It is a second life flag worth watching. It reads `1c/1d` on ours and `dc` on the
  console, so the upper bits differ. That difference may be innocent, but it is the §4 signature again.

**Confidence.** High for `+0x1044` and `+0xF7A`: two sources, one of them explicitly r0001, our own
decomp, and eight images. The r0004 tool's struct offsets agree with r0001, so the seal layout did
not change between revisions.

**What it would take.** Set `--health-offset 0x1044` for the float, and add a byte watch at `0xF7A`.
The test has to watch the **remote** player's actor: B's own `*0x408c58` on instance B. The
harness already finds the actor by vtable, and the offset lies inside the same block, so the peek
spec needs `*0x408c58+0xF7A:1` and `*0x408c58+0x1044:1`. One kill confirms it; `KNOWN.md`'s rule
asks for two.

### F2 — The round-state object `CZNetGame` at `*0x437ce8`, and its valves — problems 1 and 2 — **[verified]** structure, **[inference]** semantics

**Sources**
- reCOM `src/gamez/zNetwork/znet.h` and `zNetGame.cpp` (local clone
  `tools/reference/reCOM`, identical to upstream HEAD): `CZNetGame` layout, `MP_MAJOR_GAME_STATE`
  {UNKNOWN, MENUS, LOADING, INPLAY, ROUNDOVER, NEWROUND, GAMEOVER, PLAY, GAMELOBBY, **GHOST**},
  `MP_MINOR_GAME_STATE` {UNKNOWN, NOTREADY, READY}, `MP_NET_READY` {UNKNOWN, WAITING, PLAY, MENUS},
  and the fields `m_ready_to_play`, `m_ghost_ok`, `m_am_a_ghost`, `m_was_late_joiner` and `m_countdown`.
  https://github.com/NotEnoughPhotons/reCOM/blob/main/src/gamez/zNetwork/znet.h
- Socom2StreamData `GameHelper.cs` again. Its `0x69xxxx` addresses turn out to be valve value
  slots; see below.

**Checked against ours**
- `FUN_002a76d0` (`CZNetGame::Initialize`, already [verified] in `research/11`) runs on a 0x14c-byte
  block that `CMission::Init` (`FUN_002ad290`) allocates and stores at `mission+0x1808`. **The static
  `0x437ce8` holds it.** Callers pass `DAT_00437ce8` straight into the state setters, and the block
  in all ten images carries the constructor's fingerprints: `+0x118 = 0x42480000` (50.0, reCOM's
  `m_pos_smooth = 50.0f`), `+0xF5 = 1`, `+0x112 = 1`, and valve pointers at `+0x04..+0x70`.
- State setters: **`FUN_002a7420(ng, s)`** writes `ng+0x114` and the `mp_major_game_state` valve.
  `FUN_002a73b0(ng, s)` writes `ng+0x115` and `mp_minor_game_state`. **`FUN_002a7490(ng, s)`**
  writes `ng+0x113` only, which is most likely reCOM's `m_my_major_game_state`. The per-frame
  reconciler (`FUN_002c3cf0`, decomp ~165357) promotes `+0x113` into `+0x114` under minor state 2.
  It is the round state machine, and it is short.
- Valve layout: `{char* name @+0, short value @+4, short type @+6 (=1), …, next @+0xC}`. The names
  were read back out of both images. Pointers in the block (`ng+off` → valve):

  | `ng+` | valve | `ng+` | valve |
  |---|---|---|---|
  | `0x04` | `mp_half_rounds` | `0x44` | `player_join_count` |
  | `0x0C` | **`mp_round_count`** | `0x48` | `player_ready_count` |
  | `0x10` | **`mp_game_over`** | `0x58` | **`aiteam_00`** (SEALs alive, per Socom2StreamData) |
  | `0x14` | `player_team` | `0x5C` | **`aiteam_08`** (terrorists alive) |
  | `0x20` | **`mp_major_game_state`** | `0x68` | `mp_spectator` |
  | `0x24` | **`mp_minor_game_state`** | `0x70` | **`total_mp_kills`** |
  | `0x2C` | **`late_joiner`** | `0x00/0x08/0x64/0x74/0x78` | `mp_max_rounds` / `mp_max_round_time` / `mp_allow_respawn` / `seals_team_score` / `terrs_team_score`, looked up by name, **null in single player** |

  Further valves outside the block, found by name: `mp_score00`, `mp_score08` (rounds won) and
  `JoinAsSpectator`.
- **Socom2StreamData's r0004 addresses are these valves' `+4` slots, at the console's addresses.**
  `GAME_ENDED 0x694C44` = `mp_game_over`+4, `TOTAL_ROUNDS 0x694C6C` = `mp_round_count`+4,
  `CURRENT_SEALS_ALIVE 0x694CA8` = `aiteam_00`+4, `CURRENT_TERRORISTS_ALIVE 0x694CBC` =
  `aiteam_08`+4, `SEAL_WIN 0x695388` = `mp_score00`+4, `TERRORIST_WIN 0x69539C` = `mp_score08`+4,
  `IS_SPECTATOR 0x6954A0` = `JoinAsSpectator`+4. Every name was read from `spawn_pcsx2.rdram`.
  **On `spawn_ours3.rdram` every one of them sits exactly 0x20 lower** (`mp_game_over` at `0x694C20`,
  and so on). See F4.

**Semantics [inference].** The byte values in SOCOM II are not confirmed to follow SOCOM 1's enum.
The reconciler's arms test `+0x113 ∈ {1,2,3,6}` and push `6` straight through, which fits
`GAMEOVER = 6`. Read the bytes live before naming them.

**What it would take.** Peek
`*0x437ce8:84` (the whole 0x14c block, 83 words) on both instances from lobby to first round end.
From the same rows, derive `+0x113/+0x114/+0x115` and `+0xCC..+0xDF`, and follow the valve pointers
at `+0x20/+0x24/+0x0C/+0x10/+0x58/+0x5C/+0x70` to their `+4` shorts. A kill should step
`total_mp_kills` and drop `aiteam_00` or `aiteam_08`. A round end should step `mp_round_count` and
`mp_score00`/`mp_score08`. A match that never hands over control should show which state byte
stalls. It all comes out of one run the harness already does.

### F3 — The ghost flag `CZNetGame+0xd2` is uninitialised, `0xAF` on ours and `0x00` on the console — problem 1 (and 3) — **[verified]** divergence, **[inference]** consequence

**Evidence.** Hex of the 0x14c block, `title_ours` / `spawn_ours3` against `title_pcsx2` / `spawn_pcsx2`.
The two images on each side are identical. Every byte the constructor does not write is `0xAF` on
ours and `0x00` on the console: `+0x6C..+0x83`, `+0xA9..+0xAF`, `+0xB4..+0xBB`, **`+0xCD`, `+0xD2`,
`+0xD3`, `+0xD4`, `+0xD7`, `+0xDB`, `+0xDF`**, `+0xF6/F7`, `+0xFC..+0x10F`, `+0x111`, `+0x116/117`,
`+0x120..+0x12B`. The block itself sits at `0x869360` on ours and `0xC496B0` on the console.
Allocation placement differs because `malloc`/`free`/`calloc` are stubbed onto the runtime's own
heap (`PS2Runtime::guestMalloc` in `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp`)
instead of newlib's `_malloc_r`. `0xAF` is not an allocator fill in the game code; the game only uses
`memset(…, 0xAF, …)` for ZAR padding (`FUN_00257590`, `FUN_0025a120`). So ours hands out recycled
memory, and the console's layout happened to hand out zero pages. [The cause chain is inference.
The divergence is measured.]

**Why `+0xd2` matters.**
- It selects the HUD text **"You are a ghost. You will play the next round as a real player."**
  (string `0x3e31c0`; `FUN_001f97b0` and `FUN_001f9f20` test `*(0x437ce8)+0xd2 != 0`).
- It is written `1` in the online load flow for a late joiner (`FUN_001f5e70`, gated on
  `ng+0xCC` = `late_joiner` and `!FUN_002c2fa0()`). It is cleared to `0` on new round
  (`FUN_001f6660`), on a state exit that then calls `FUN_00543b90(GetPlayer())` (`FUN_002232a0`),
  and in `FUN_002b7d60`.
- **Online-only gameplay code branches on it:** `FUN_00592560`, `FUN_00594cf0`, `FUN_005979a0`
  (`if (ng+0xdc == 0 || ng+0xd2 != 0)` → spectator-style path), `FUN_00597f50`, and `FUN_005e6e40`
  (`FUN_002c2c20(3)`, a camera or mode switch, when `+0xd2 != 0`). `+0xCD` is also uninitialised and
  gates the loading-screen hand-off in `FUN_001f5e70`.

**Why it fits the Frostfire symptom [inference].** The object is allocated per mission, so its
garbage depends on what the recycled heap held **for that map**. That is a mechanism by which "works
on mp51, not on Frostfire" needs no map-specific movement bug. A ghost moves nothing and the round
clock keeps running, which is the observed shape. Against it: `FUN_001f6660` clears `+0xd2` at new
round, so the flag may never survive to gameplay. **One peek settles it.**

**What it would take.**
- (a) Peek `*0x437ce8+0xCC:5` across round start on both instances, on Frostfire and on mp51.
- (b) If `+0xd2` is non-zero at the moment the move path stops, run a same-binary A/B with guest
  allocations zero-filled: make `guestMalloc` behave like `guestCalloc`. The knob is one line in
  `LibC.cpp`/`ps2_runtime.cpp`. That also tests the whole uninitialised-field class at once.
- (c) Either way, add "uninitialised heap memory" to the audit in F7. It is the fourth member of
  `KNOWN.md` §4's class, and the one the existing image-diff test catches for free.

### F4 — Our valve pool is shifted −0x20 against the console — problems 2 and 4 — **[verified]**

Every valve pointer in the `CZNetGame` block is exactly `0x20` lower on ours (table in F2; 27 of 27).
The shift is uniform, so something allocated before the first valve (a string or a record in the
`0x69xxxx` pool) is 32 bytes smaller on ours, or one record is missing. The shift is harmless while
code follows pointers. It does mean **every community absolute address in `0x69xxxx` is off by 0x20
on our build**, and any absolute-address cheat or peek aimed there silently reads the wrong valve.
What it would take: always resolve valves through `*0x437ce8+off` or by name. Optionally, find the
first diverging record by walking the pool from its start in both images. That is an offline job.

### F5 — r0001 ↔ r0004 address map for the `ftscore` statics — problem 2 tooling — **[verified]** for four addresses

Socom2StreamData's r0004 statics equal ours **plus `0x2C9C0`**:

| r0004 (tool) | r0001 (ours) | confirmed by |
|---|---|---|
| `PLAYER_POINTER 0x435618` | `0x408c58` | `KNOWN.md` player static |
| `CURRENT_ROUND_TIMER 0x4358D0` (5-char string) | `0x408f10` | our decomp: `sprintf(0x408f10, "%02d:%02d", t/60, t%60)` at ~56002, string present in both images |
| `CURRENT_MAP 0x4417C0` | `0x414e00` | reads `"m51"` in `spawn_ours3` and `spawn_pcsx2` |
| `CAMERA_POINTER 0x4429B0` (tool writes `+0xBC`/`+0xC0` to spectate a player) | `0x415ff0` | `KNOWN.md`: `*0x415ff0+0xbc` is the actor |

The tool's own comment "R0004 Offset B620" does **not** fit these; `0x435618 + 0xB620 = 0x440C38`
is a coincidence of two statics that hold the same pointer. The HUD and FPS statics
(`0x407560`, `0x40C638`) do not map with `0x2C9C0` and are unconfirmed. The **round timer string at
`0x408f10`** is directly useful: it lets a run tell "the clock is at 00:00" (round end on time) apart from a
kill. What it would take: add `0x408f10:2` to the peek spec.

### F6 — reCOM status and what its seal header adds — problems 1 and 2 — **[verified]** (no change), **[pointer]** (S1 layouts)

- Upstream `NotEnoughPhotons/reCOM`: `pushed_at 2026-06-30`, latest commit 2026-06-30 by adamd3v.
  GitHub's `updated_at 2026-09-06` is metadata only. The local clone at HEAD `5b05af1` is current,
  so `research/11` needs no revision. https://github.com/NotEnoughPhotons/reCOM/commits/main
- Already in the clone and not quoted by `research/11`: `zseal.h` gives `SEAL_DEATH_TYPE` {NONE,
  KNIFE_KILL, CQB, HEADSHOT, GRENADE, BULLET, **GHOST**, FALLING}, `SEAL_VALVE` {HOLDFIRE, SHOTAT,
  **ALIVE**, AWARE}, and `CSealStats` {headshots, headhits, hits, shots, **kills**, washit, **deaths**,
  …}, held twice per seal (`m_mp_stats`, `m_stats`). Also `m_health`, `m_deathType`,
  `m_time_of_death`, `m_killer_index`, `m_needs_respawn`, and six limb health/max pairs. These are
  **SOCOM 1 orderings**; the S2 offsets differ (`m_health` is at `+0x1044` with time-of-death most
  likely at `+0xFB4`, *before* it). Use the names, not the order.
- `zNetGame.cpp`'s `Initialize` confirms F2's valve list in S1 order. S2 adds `mp_half_rounds`,
  `total_mp_kills`, `mp_spectator`, `mp_allow_respawn`, `aiteam_00/08`, `skip_effects`,
  `mp_team_unbalance`, `mp_teams_too_big` and the team-score valves.
- Sibling repositories: `xCENTx/reCOM` is a 2025 fork with no later work. `xCENTx/PS2-NativeHooks`
  (pushed 2026-09-11) reconstructs structs for **SOCOM 1 retail SCUS_971.34**, not ours; F9 covers
  its technique. `xCENTx/SOCOM-External` is also SOCOM 1.

### F7 — Stub-contract auditing, as another HLE project does it — problem 3 — **[verified]** (their method), **[inference]** (fit)

**prosper** (mattias800/prosper, a PS5 compatibility layer, very active) has hit *exactly* our defect
class, and has built instruments for it:
- PR #2021, "sceSysmoduleIsLoaded must answer from prosper's own load history, **not a constant**".
  A state query sharing a generic `return 0` stub made the guest skip initialisation, and the fault
  surfaced minutes later as an unrelated-looking content defect. The PR sets out a rule: *the answer
  that can silently remove behaviour is the dangerous one; prefer the honest answer and make the
  first unusual answer print one line.*
  https://github.com/mattias800/prosper/pull/2021
- PR #488: "rand() was a constant 0". It is our 15-bit `rand` in a different shape.
  https://github.com/mattias800/prosper/pull/488
- PR #2579 / #2637: **`nid_gate_scan`**, a static census of **what each call site does with a stub's
  return value** (`ignored` / `nonzero` gate / `const` compare / `forward` into another call /
  `gate-open` = unresolved). It follows both arms of every branch the value survives and reports
  "unresolved" rather than "cleared" when its budget runs out. Its stated principle: *the guest's own
  compare is the primary evidence for the contract.*
  https://github.com/mattias800/prosper/pull/2637
- Issue #2654 is a useful warning: a census number quoted in a test comment stopped reproducing once
  the tool improved. That is the "stale number" hazard `KNOWN.md` already names.

**How it maps onto ours [inference].** Our three defects all had consumers that did **arithmetic or
comparison against a moving value**: `rand() % n`, `now - lastActivity`, and a `double` feeding
`exp`. A MIPS version of that census (per `jal <stub>`: follow `$v0`/`$f0` through the delay slot,
then classify ignored / zero-test / const-compare / arithmetic / stored-to-memory) ranks constant or
degenerate stubs by risk, with **"arithmetic" and "stored and later differenced" at the top**. It is
Sprint 5 Task 7's "static census" with a concrete classification scheme and a known failure mode
(stopping at the first branch) to avoid.

**Catalogues of contracts [verified exists]:**
- **ps2autotests** (unknownbrackets, **ISC**): test programs run on a real PS2 with recorded expected
  output. `tests/kernel` (100 files: threads, semaphores, alarms, vsync, …), `tests/cpu`,
  `tests/vu`, `tests/dma`. It covers kernel syscalls, not libc or `sceInet*`. It is a ready oracle
  for the EE-kernel half of the stub surface. https://github.com/unknownbrackets/ps2autotests
- **sce-symbol-scanner** (LostTemplarRH): detects SCE SDK functions in PS2 ELFs, with a CLI and a Ghidra
  plugin, and is integrated upstream in PS2Recomp PR #130. Use it to confirm that each `name@addr`
  binding in `recomp/socom2.toml` really is that SDK function and version. A stub bound to the
  wrong function is the soft-double ABI shape. https://github.com/LostTemplarRH/sce-symbol-scanner
- **ps2sdk** (ps2dev) for the homebrew re-implementations of the same APIs; `research/01` already
  cites it.
- **PS2Recomp upstream:** no commits after our pin `14b1e5c` (2026-08-18). The open items bear on
  problem 3. **Issue #196** reports that the tree reads trailing arguments under two contradictory
  conventions: 8-register EABI with the stack at `0(sp)` in `sceGifPkRefLoadImage`, against
  `$sp+0x10` in `Ps2VarArgCursor`/`readStackU32`, `SifRegisterRpc`. That is the soft-double ABI class
  again. Our copy's `Support.h` still has `readStackU32(…, 16)`.
  https://github.com/ran-j/PS2Recomp/issues/196

### F8 — Validation methods used by other projects — problem 4 — **[verified]** (their claims), **[inference]** (fit)

- **Way of the Samurai PS2Recomp findings** (InitialDad, **CC0**): "parallel-scan" verification of
  a recomp's guest memory against a live PCSX2 reference. Evidence tiers include `snapshot_diff` =
  byte-identical. **Dead ends are recorded as first-class data** (36 of them), and a "Claims
  previously published here that were wrong" section heads the README. Their worked example 3 is our
  `KNOWN.md` lesson in another game: a guard installed on a wrong claim was what starved the renderer.
  So is their rule "never accept an error counter going to zero as proof a fix works".
  https://github.com/InitialDad/PS2Recomp-WoS-Findings (README, FINDINGS.md)
  *Fit:* our RDRAM-image method is this, done by address. F3/F4 show that **address-keyed diffs
  miss heap objects**: the `CZNetGame` block sits at `0x869360` against `0xC496B0`. Key the diff by object
  identity (static pointer → block → field), as this note did by hand.
- **XenonRecomp / XenonTests** (hedge-dev): recompiles Xenia's PPC instruction tests and compares
  results against expected values, a per-instruction oracle apart from the game.
  https://github.com/hedge-dev/XenonRecomp. *Fit:* the soft-double chain (`litodp → dpmul → dpdiv
  → exp → dptofp`) is exactly a unit that wants a host-`double` differential test. `ROADMAP.md`
  Sprint 6 already plans that. There is no need to wait for the game to exercise it.
- **N64Recomp** relies on a separately written runtime (N64ModernRuntime) that re-implements libultra, and
  its README reports testing mostly against old MIPS compilers. It publishes no systematic
  equivalence test. https://github.com/N64Recomp/N64Recomp. *Takeaway:* the well-known recomps do not
  have a validation method to borrow beyond instruction tests. The parity harness against PCSX2 is already
  ahead of them, and the gap is **object-keyed** state diffing (F3).
- **PS2Recomp PR #157** (open, smmathews): opt-in guest-memory watches **with writer-PC capture**,
  riding `ps2TraceGuestWrite`. Our pin has that hook as a no-op marked for deletion, and our
  `PS2X_WATCH` polls without a writer. Writer-PC is precisely what F3 needs next: *who* writes
  `ng+0xd2` or `ng+0x113..0x115` on our build.
  https://github.com/ran-j/PS2Recomp/pull/157 [pointer: whether every fast-path store reaches the
  hook in our generated code is unverified.]

### F9 — Instrumenting the console reference symmetrically — problem 4 — **[pointer]**

`xCENTx/PS2-NativeHooks` compiles C to R5900 code, links it into a code cave, and hooks game functions
through PCSX2 pnach patches, including calls to native game functions and struct traversal.
https://github.com/xCENTx/PS2-NativeHooks. *Fit [inference]:* the same `CZNetGame`/seal probes could
run **inside PCSX2** and log into a RAM ring buffer read over PINE. That would give a console trace
with the same rows as ours, not stills. It is heavier than F2's peeks, so hold it back until a
divergence needs a per-frame console trace.

### F10 — Community codes that are *not* for our build — **[verified]** negative

- The Glitchkill "CodeMajic" SOCOM II list (e.g. "Infinite Health `205A7660 03E00008`", "One Shot
  One Kill `205B1A60`", "Infinite Ammo `205C6288 00000000`"):
  https://glitchkill.proboards.com/thread/381/socom-ii-codemajic-codes. **These are not r0001.** Our
  `0x5A7660` holds `a0a20042`, mid-function in `FUN_005a75d0`, and `0x5C6288` is already `00000000`.
  They are most likely r0004, loaded from the memory-card patch. Do not use them.
- The CodeBreaker list at almarsguides is encrypted (CB v1–5/v6+ masters) and version-unstated.
  https://almarsguides.com/retro/walkthroughs/ps2/games/socomiiusnavyseals/codebreaker/
- The r0001 codes that **do** fit (NightFyre archive, instruction bytes matched): `Enable Respawn Offline
  2055205C 00000000`. That nops `beq v0,zero,+0x1e` inside **`FUN_00551ec0`**, the movement consumer
  `ROADMAP.md` names, so that routine carries an online-only respawn gate. Also the Auto Respawn
  hook at `0x2CED04` (`jr ra` at the tail of `FUN_002ce9e0`). Reference only; do not patch the game.
- `forum.gamehacking.org` threads (SCUS_972.75 codes; "[PCSX2] SOCOM 2 External Trainer – SOURCE")
  and `gamehacking.org/game/104978` returned 403 to the fetcher: **[pointer]**, unread.

---

## 2. Contradictions with `KNOWN.md`

1. **§2 "`actor+0x204` (1.0) and `actor+0x208` (100000.0) are the player's health and max health —
   weakly believed".** **Contradicted.** Health is `actor+0x1044` (F1): two community sources, one
   explicitly r0001, 17 decomp sites comparing it against `0.0`/`0.2`/`0.5`/`1.0`, and `1.0` in eight
   images. The retraction `KNOWN.md` hedged toward is right: `+0x204/+0x208` are not health.
2. **§1 row "The bursts hit nothing … `actor+0x204`/`+0x208` unchanged on both instances throughout,
   so no damage was dealt either way".** The **"so no damage was dealt"** clause rests on the wrong
   offsets and is unsupported. The geometry conclusion (never inside 45 units in 3-D) stands on its
   own and is unaffected. Damage, or its absence, in `ours_task8_kill2` is **unknown**.
3. **§2 "`--until-kill --health-offset 0x208` arms the watch once confirmed".** Should become `0x1044`
   (float), plus the life byte at `0xF7A`. `research/18` §4.2 and §4.10 item 2 carry the same `0x208`.
4. **§4 "Our HLE returning a constant where the guest expects a live value — three for three".** Not
   contradicted, but **incomplete**. F3 is a fourth divergence of the same "our surface, not the game"
   kind: memory the game never initialised, served by our replacement heap. It already shows the
   signature that entry prescribes (identical in all of ours, different on the console). The entry
   should widen to cover it.
5. **§1 row "The local player's actor is reachable from a STATIC `*0x408c58` (also `0x40d744`,
   `0x440c38`, `*0x415ff0+0xbc`)".** **Corroborated independently**: NightFyre r0001 uses `0x440C38`,
   Socom2StreamData r0004 `0x435618` = `0x408c58 + 0x2C9C0`, and its spectate feature writes
   `*0x4429B0+0xBC` = `*0x415ff0+0xbc` (F5). Recording because corroboration by outside sources is rare
   here.
6. `research/11` §4 item 7 says "its upstream is active (commit 2026-06-29)". There have been no
   commits since; this is minor.

---

## 3. Recommendations for the sprint plan

In order. Each names its finding and payoff.

1. **First: rebuild the kill and round-end readout on sourced offsets (F1, F2, F5) before the next
   match launch.** Change the peek spec to add `*0x408c58+0x1044:1`, `*0x408c58+0xF7A:1` (life
   byte), `*0x437ce8:84` (the whole `CZNetGame`) and `0x408f10:2` (round clock string). Drop
   `+0x204/+0x208`. Derive `total_mp_kills`, `aiteam_00/08`, `mp_round_count`, `mp_score00/08`,
   `mp_game_over` and the three state bytes offline from the dumped block. `PASS` = the target's
   `+0x1044 <= 0` **and** `+0xF7A != 1`, corroborated by `total_mp_kills` stepping. That separates a
   kill from a timed round end with no screenshot.
   *Payoff:* Sprint 5 Task 4 shrinks from "find the record" (1–2 days plus a single-player death hunt)
   to "confirm across two kills". `--until-kill` can print `PASS` for the first time. **Drop Task 4a's
   single-player search**; keep one single-player death only as a cheap confirmation if a match is
   expensive.
2. **Fold F3's peek into the Frostfire re-run that §4.10 item 1 already schedules.** The same run with
   `*0x437ce8:84` on both instances answers two questions: whether `+0xd2`/`+0xCD` are non-zero when the move
   path stops, and which of `+0x113/+0x114/+0x115` stalls. If `+0xd2` is set, the next task is the
   zero-fill A/B (one knob, same binary), **not** a movement investigation. Run the identical peek
   on an mp51 match for the control case.
   *Payoff:* either a named mechanism for "control never handed over", or one whole class eliminated,
   from a run the plan already contains.
3. **Add "uninitialised guest memory" to the HLE audit (Task 7) as leg zero**, and give the audit
   prosper's consumer classification (F7). Offline, for every constructor the decomp can see (starting
   with the objects at statics `0x437ce8`, `0x408c58`, `0x415ff0`), diff *object-keyed* blocks across
   ours and the PCSX2 images, and list fields that are `0xAF`/non-zero on ours and zero on the
   console. Separately, classify each stub's call sites (ignored / zero-test / const-compare /
   arithmetic / stored) and rank "arithmetic or stored" constant stubs first.
   *Payoff:* it turns "presume remaining wrongness is this shape" into a list, and costs no runs.
4. **Treat community absolute addresses as console-only (F4, F10).** Resolve every valve through
   `*0x437ce8`, and reject any r0004 or version-unstated code without checking its original
   instruction bytes against our ELF first. That check is a three-line Python read of
   `game/overlays/socom2_game.elf`.
   *Payoff:* avoids a silent wrong-valve read, the "instrument that attests to nothing" hazard.
5. **Add object-keyed state diffs to the parity harness (F8).** "Same address, same bytes" is blind
   to heap objects. "Same static pointer → same object → same fields" is what found F3.
   *Payoff:* the first correctness leg for the gate that `ROADMAP.md` Sprint 6 wants ("gameplay-state
   probe"), with a worked example already in hand.
6. **For Sprint 6's soft-double chain, write host-`double` differential unit tests first (F8,
   XenonTests pattern)** rather than tracing the game. Consider ps2autotests' kernel expectations as
   fixtures for the EE-kernel stubs.
7. **Do not spend on:** reCOM re-surveys (no upstream change); PS2Recomp upstream merges for this
   problem (nothing after our pin); the CodeMajic/CodeBreaker lists; PS2-NativeHooks (SOCOM 1
   structs; the technique is worth holding, not doing now).

---

## 4. Licensing and provenance

| Resource | Licence / terms | How the project may use it |
|---|---|---|
| reCOM (NotEnoughPhotons) | **No licence file**; README reserves rights to Zipper/SCEA and ships no assets. The code reconstructs copyrighted game code | Names and enums as a reference only; cite by path; **copy no code** (as `research/11` §3) |
| Socom2StreamData (Zero1UP) | **No licence** → all rights reserved | Offsets are facts: cite and re-derive; copy no code |
| SOCOM-ARCHIVES (NightFyre) | No licence; README "© 11/29/21 bismofunyuns" | Offsets and instruction bytes as facts; copy no code or patches |
| xCENTx/PS2-NativeHooks, SOCOM-External, exSOCOM-MultiMenu | No licence | Technique reference only |
| prosper (mattias800) | No licence detected by the GitHub API | Method reference only |
| PS2Recomp-WoS-Findings (InitialDad) | **CC0 1.0** | Free to reuse, method and schema included |
| ps2autotests (unknownbrackets) | **ISC** | Test expectations may be vendored with the notice |
| sce-symbol-scanner (LostTemplarRH) | No licence listed on GitHub | Running it locally as a tool is fine; check before vendoring |
| PS2Recomp (ran-j) | **GPL-3.0** (known; `research/04`) | Already the base; distribution obligations unchanged |
| XenonRecomp / N64Recomp | Upstream licences not re-checked here | Method only |
| Horizon server | MIT (`research/02`) | Unchanged |
| Glitchkill / CodeMajic / CodeBreaker lists | Forum posts, no terms | Not for our build (F10); no use |

**Leaked or proprietary material, flagged and not accessed.** `research/02` already records an
archive.org "PS2 SDKs" item containing **SCE-RT.rar** and **LibDNAS.7z**. Those are Sony proprietary
SDKs. Do not download them, and do not let anything derived from them into the tree. The **SOCOM 1
demo with debug symbols** (Hidden Palace prototype, reCOM's basis) is copyrighted game code. reCOM
consumed it; this project should keep consuming reCOM's *names*, not the disc. Nothing in this
note was obtained from either.

---

## 5. Sources

- reCOM: https://github.com/NotEnoughPhotons/reCOM (commits: /commits/main)
- Socom2StreamData: https://github.com/Zero1UP/Socom2StreamData (`Helpers/GameHelper.cs`, `frm_Main.cs`, `Helpers/ByteConverstionHelper.cs`)
- SOCOM-ARCHIVES: https://github.com/NightFyre/SOCOM-ARCHIVES (`SOCOM II/Aimbot/r0001/Helper.h`, `SOCOM II/Auto Respawn Offline/Auto Respawn.txt`)
- PCSX2-SOCOM-ASM (r0004 `PLAYEROBJECT 0x2044D648`): https://github.com/xCENTx/PCSX2-SOCOM-ASM
- PS2-NativeHooks: https://github.com/xCENTx/PS2-NativeHooks
- prosper: https://github.com/mattias800/prosper/pull/2021, /pull/488, /pull/2579, /pull/2637, /issues/2654
- PS2Recomp: https://github.com/ran-j/PS2Recomp (commits to `14b1e5c`), /issues/196, /pull/157, /issues/172, /pull/130
- WoS findings: https://github.com/InitialDad/PS2Recomp-WoS-Findings
- ps2autotests: https://github.com/unknownbrackets/ps2autotests
- sce-symbol-scanner: https://github.com/LostTemplarRH/sce-symbol-scanner
- XenonRecomp: https://github.com/hedge-dev/XenonRecomp
- N64Recomp: https://github.com/N64Recomp/N64Recomp
- CodeMajic list: https://glitchkill.proboards.com/thread/381/socom-ii-codemajic-codes
- CodeBreaker list: https://almarsguides.com/retro/walkthroughs/ps2/games/socomiiusnavyseals/codebreaker/
- PCSX2 patches (widescreen only for SCUS-97275): https://github.com/PCSX2/pcsx2_patches/blob/main/patches/SCUS-97275_0F6FC6CF.pnach
- Unread (403): https://forum.gamehacking.org/forum/video-game-hacking-and-development/retro-hacking/11926-ps2-scus_972-75-socom-ii-codes, https://forum.gamehacking.org/forum/video-game-hacking-and-development/retro-hacking/215035-pcsx2-socom-2-external-trainer-source
