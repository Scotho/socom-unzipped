# 21 — Frostfire control handover (Sprint 5 Task 1)

**Status: draft, Step 1 only (zero-run preparation, 2026-09-13).** No build, no launch. Launch 1
(Step 3) is read against §3. Every claim is marked **[verified]** (read from the decomp, the ELF bytes,
an RDRAM image or a log in this task) or **[inference]**.

Sources: `game/analysis/socom2_game.elf.decomp.c`; `game/disc/socom2_game.elf` (vtables and
instructions read from bytes); `logs/parity/*.rdram` (15 ours images, 3 console images);
`frost1` = `logs/run_[AB]_20260913_004754.log`; `kill2` = `logs/run_[AB]_20260912_231341.log`.
Background: spec §1 and §1.1; research/19 F1–F5; research/18 §3.9, §3.12, §4.12; research/11
§1 "zNetwork"; Task 4 Step 1's object diff (`ad32088`).

---

## 1. The valve map, re-checked

One-line re-checks of Task 0's preflight (decomp read again this task):

| claim | re-check | mark |
|---|---|---|
| `FUN_002a76d0` builds the valves | `FUN_003520d0(0x3f10a0)`→`[8]` (+0x20), `0x3f10c0`→`[9]` (+0x24), `0x3f0f88`→`[4]` (+0x10), `0x3f11b0`→`[3]` (+0x0c), `0x3f11d8`→`[0x16]` (+0x58), `0x3f11e8`→`[0x17]` (+0x5c), `0x3f1268`→`[0x1c]` (+0x70); `FUN_00351ff0(0x3f10e8)`→`[5]` (+0x14), `0x3f10f8`→`[0xb]` (+0x2c) | [verified] |
| the argument addresses are the names | ELF strings: `0x3f10a0` mp_major_game_state, `0x3f10c0` mp_minor_game_state, `0x3f0f88` mp_game_over, `0x3f11b0` mp_round_count, `0x3f11d8` aiteam_00, `0x3f11e8` aiteam_08, `0x3f1268` total_mp_kills, `0x3f10e8` player_team, `0x3f10f8` late_joiner | [verified] |
| `FUN_003857c0` builds only the lists | its five calls take `0x3f1040..0x3f1080` = `BSEALLISTVAR`, `BTERRLISTVAR`, `BSPECLISTVAR`, `BNONELISTVAR`, `BCHATLISTVAR` into `[0x21..0x25]` | [verified] |
| setters | `FUN_002a7420` writes `+0x114` and `*(+0x20)+4`; `FUN_002a73b0` writes `+0x115` and `*(+0x24)+4`; `FUN_002a7490` writes `+0x113` only | [verified] |
| `FUN_003520d0` is find-or-create | looks the name up with `FUN_00351ef0` first, creates only on a miss, so a valve persists for the boot | [verified] |
| controller vtables | `0x6694b0` and `0x4062d0`: `+0xc`=0x594cf0, `+0x14`=0x592560, `+0x18`=0x5979a0, `+0x8c`=0x566940 (ELF bytes) | [verified] |
| the `FUN_00551ec0` guard | `lh 0x174(s2)==8` / `lbu 0x1061` bit `0x20` / `lbu 0x45a0c1` then `lbu 0xfcf`; true arm `vtbl[0x14]`, else `vtbl[0xc]`. **The state is the short at `actor+0x174`, not `actor+0xc0`** (`+0xc0` is the controller pointer) | [verified] |
| `ng+0xde` | set to 1 iff `idle-1500 >= 3001`, i.e. idle >= 4501 ms, only on frames that reach the MoveScale code | [verified] |
| `ng+0xd2` writers | `FUN_001f5e70` (=1), `FUN_001f6660` (=0), `FUN_002232a0` (=0), `FUN_002b7d60` (**spawn-dead + clear**: reads `+0xd2` and spawns the local player dead in state 8; clears it only when `ng+0xdc != 0`, see §3.3) | [verified] |

## 2. Name pointers — the self-identifying valve peek

### 2.1 Result: the name pointers are **not** ELF string addresses

A valve's word 0 is **not** the static string that `FUN_002a76d0` passed (`0x3f11b0` and so on). It
points into the valve registry's own string storage (`0x6b7xxx`, `0x6ccxxx`, `0x694xxx`
inline after the record). **It differs between our build and the console by a non-uniform amount**
(+0x20, +0x30 or +0x40). The brief expected "identical on the console". That expectation is wrong,
and this is a finding. [verified]

| `ng+` | valve (string read at the pointer) | ours name ptr | console name ptr | Δ |
|---|---|---|---|---|
| `0x0c` | mp_round_count | **`0x006b7f30`** | `0x006b7f60` | +0x30 |
| `0x10` | mp_game_over | **`0x006b7f20`** | `0x006b7f50` | +0x30 |
| `0x14` | player_team | **`0x006cc9fc`** | `0x006cca3c` | +0x40 |
| `0x20` | mp_major_game_state | **`0x00694ae0`** | `0x00694b00` | +0x20 |
| `0x24` | mp_minor_game_state | **`0x00694b08`** | `0x00694b28` | +0x20 |
| `0x2c` | late_joiner | **`0x006cca14`** | `0x006cca54` | +0x40 |
| `0x58` | aiteam_00 | **`0x006ccad4`** | `0x006ccb14` | +0x40 |
| `0x5c` | aiteam_08 | **`0x006ccaec`** | `0x006ccb2c` | +0x40 |
| `0x70` | total_mp_kills | **`0x006b7f70`** | `0x006b7fa0` | +0x30 |
| `*0x43668c` | **mission_abort** | **`0x006b7fb0`** | `0x006b7fe0` | +0x30 |

- Every string matched its expected name, on both sides. [verified]
- **The valve behind `DAT_0043668c` is `mission_abort`**, valve at `0x694d88` on ours and `0x694da8` on
  the console. It is created by `FUN_002abd40` (`FUN_003520d0(0x3f18e0)` into `mission+0x1ac`), zeroed
  at mission start by `FUN_002a7d40`, and set to 1 or 2 only by `FUN_002041e0` (the pause-menu
  abort flow). [verified]
- **Stability on ours.** The ours values are identical in all 15 ours images: menu, menu2–4, menuC,
  rank, rank27, title, postload, rest, rest_gq, spawn, spawn2, spawn3 and s4rand, from Sep 7 to
  Sep 12 across several builds. `*0x437ce8` = `0x869360` in every one of them. The console values
  are identical in all 3 console images. [verified]
- **Caveat.** Every image is single-player or menu (`0x45a0c1` = 0 in all 18). No online image
  exists. The block and all nine valves are present and carry the constructor fingerprint
  (`+0x118 = 0x42480000`). Because the registry is find-or-create (§1), I expect the pointers to
  hold online on the same build. That is [inference] until launch 1 reads them.
- Side findings from the same dump [verified]: ours `ng+0x38/+0x3c` hold `0x89a0000d`/`0x22680021`
  where the console has zero. Task 4 Step 1 already flagged this. `DAT_003df1b0` reads **0** in
  `spawn_ours3` and `rest_ours` and 1 everywhere else. Its ELF initial value is 1, and the image
  clock (16.7 s against the console's 53.1 s) suggests an intro-cinematic capture. That timing reason
  is [inference], and it is not a divergence claim.

### 2.2 Recommended identification: by content, not by address

The peek parser follows `*` in any position (`game_overrides_socom2.cpp`, `PS2X_PEEK` pointer
chains), so `*0x437ce8+0x0c**:3` prints the first 12 bytes of the name itself. That check is
independent of heap layout, build and platform. Expected words (little-endian ASCII) [verified from
`spawn_ours3`]:

| item | word 0 | word 1 | word 2 |
|---|---|---|---|
| `*0x437ce8+0x0c**:3` | `725f706d` | `646e756f` | `756f635f` |
| `*0x437ce8+0x10**:3` | `675f706d` | `5f656d61` | `7265766f` |
| `*0x437ce8+0x14**:3` | `79616c70` | `745f7265` | `006d6165` |
| `*0x437ce8+0x20**:3` | `6d5f706d` | `726f6a61` | `6d61675f` |
| `*0x437ce8+0x24**:3` | `6d5f706d` | `726f6e69` | `6d61675f` |
| `*0x437ce8+0x2c**:3` | `6574616c` | `696f6a5f` | `0072656e` |
| `*0x437ce8+0x58**:3` | `65746961` | `305f6d61` | `00000030` |
| `*0x437ce8+0x5c**:3` | `65746961` | `305f6d61` | `00000038` |
| `*0x437ce8+0x70**:3` | `61746f74` | `706d5f6c` | `6c696b5f` |
| `*0x43668c**:3` | `7373696d` | `5f6e6f69` | `726f6261` |

Three words are needed. `aiteam_00` and `aiteam_08` differ only in byte 8. The pointer values in
§2.1 still serve `verdict_core`'s `--round-name-ptr` (`0x006b7f30` on ours). **Never reuse them for
a PCSX2 run.**

## 3. The branch table — every way the move path can stop

**Blind class for the whole table: reachability, not firing.** A row says a branch exists and what
would show it taken. It does not say the branch was taken. `PS2X_CALL_TRACE_EVERY=10` thins every
slot after 300 calls. Peek rows and `[ret-dump]`s come from different moments.

Abbreviations: `A` = `*0x408c58` (the local actor; in frost1 and kill2 MoveScale's `a0` equals it on
both sides [verified]). `C` = `A+0xc0` (its controller). `ng` = `*0x437ce8`. Filter `ActorUpd` by
`a0 == A`, and `PlayerUpd`/`CtlAlt14`/`CtlSpec18` by `a0 == C`: remote avatars run the same code.

Condition source [verified from the decomp unless marked]: `FUN_00551ec0`, `FUN_00594cf0` (returns 0
**only** on its two early-outs; every other path returns 1), `FUN_00592560`, `FUN_005979a0`,
`FUN_00566940`.

### 3.1 Rows that stop MoveScale

| # | branch | row that shows it | value meaning "this stopped it" | implicates | launch-1 spec distinguishes? |
|---|---|---|---|---|---|
| R0 | `FUN_00551ec0` not run for the local actor | `ActorUpd [call]` with `a0 == A` | none for `A` while sampler rows continue | actor update scheduling, upstream of everything | **yes** |
| R1 | controller null (`A+0xc0 == 0`, `beqz s1` skips both arms) | `*0x408c58:64` word `0x30` | `0` | controller detached | **yes** (frost1: `C` vtable `0x6694b0`, pointer stable for 1154/1153 rows [verified]) |
| R2a | dispatch to `FUN_00592560` (CtlAlt14) instead of `FUN_00594cf0`, disjunct 1: `(short)A+0x174 == 8` | `CtlAlt14 [call] a0==C`, `PlayerUpd` absent; `A+0x174` | low 16 bits = `8` | actor state 8, written by `A->vtbl[0x90](A, 8)` (`0x6691a0+0x90` = `FUN_0058a6b0` → `FUN_0028dfb0(A+0x170, 8)`). Callers: `FUN_00543f70` (online death path) and **`FUN_00543d50` (spawn-dead), reached from `FUN_002b7d60` when `ng+0xd2 != 0`** — the F3 chain, §3.3 [verified] | **no** — `+0x174` is outside `*0x408c58:64` (words 0..63 = `+0x00..+0xfc`) |
| R2b | dispatch, disjunct 2: `A+0x1061 & 0x20` | as R2a; `A+0x1061` | bit `0x20` set | the only setter found is `FUN_00543f70` (online, life `+0xF7A != 1`, dead-timer `A+0xF7C > 20 s` → death handler, life 3, bit set). `FUN_00551ec0` never clears `0x20`; `FUN_00553ea0` clears it. An uninitialised `0xAF` byte would also have `0x20` set [inference]; Task 4 did not flag `+0x1061` on spawn images | **no** — `+0x1061` not peeked |
| R2c | dispatch, disjunct 3: `0x45a0c1 && A+0xfcf`. **This is the "online respawn gate" at `0x55205C`**: that instruction is `beqz v0` on `0x45a0c1`, and noping it lets `+0xfcf` alone select the true arm offline. It is disjunct 3, not a separate branch [verified, ELF bytes] | as R2a; `0x45a0c0:1` (byte 1) and `A+0xfcf` | `0x45a0c1 != 0` **and** `+0xfcf != 0` | respawn latch. Setters: `FUN_00544210` (SetLife 2/3→1) **only if `C->vtbl[0x34]` is non-zero, and for `0x6694b0` that slot is `0x544200 = jr ra; move v0,zero` → SetLife cannot set it for our player** [verified]; `FUN_0056ee80`; `FUN_00592560` itself (health 0 plus button). Cleared by `FUN_002bef60` (network `'S'` record), `FUN_00553ea0`, `FUN_00598b90`, `FUN_005994a0` | **half** — the online byte is peeked; `+0xfcf` is not |
| R3 | `FUN_00594cf0` early-out: `mission_abort` ∈ {1,2} | `PlayerUpd [ret] v0=0x0`; `*0x43668c:2` word 1 | `v0=0` and low16 ∈ {1,2} | the pause-menu abort flow `FUN_002041e0` | **yes** (word 0 = `0x006b7fb0` identifies the valve) |
| R4 | `FUN_00594cf0` early-out: `DAT_003df1b0 == 0` | `PlayerUpd [ret] v0=0x0`; `0x3df1b0:1` | `v0=0` and low byte `0` | "player input enabled". The only writer in the decomp is `FUN_00598840`; its callers found are the cinematic begin/end pair `FUN_00228ee0` (0) / `FUN_00229520` (1) and by **`FUN_005cf800` = the `ai::STOPALL` mission-script handler** (registered by name at `0x6601b8`). A map script can take control away [inference: fits "Frostfire only"] | **value yes, writer no** |
| R5 | `C->vtbl[0x8c]` = `FUN_00566940` (auto-move) returns non-zero | `PlayerUpd [ret] v0=1`, MoveScale absent, R6 false; dump `a0+0x170:1` | `C+0x170 & 0x03 != 0` (entry test) | scripted auto-move consumed the frame | **partial** — the return value is not traced, and the dump is post-return and 1-in-10 |
| R6 | multiplayer snap-back: `0x45a0c1 && DAT_004365c0 - A+0x420 > 0.6` | **same peek row**: `0x4365c0:1` against `*0x408c58+0x400:12` word 8 (`+0x420`) | difference > 0.6 | position-apply (`FUN_005794d0` stamps `+0x420` from the clock) stopped for the local actor, so the position is re-set to `+0x400..+0x408` every frame | **yes, from the peek**. Do **not** pair the `a0+0x4*+0x400:9` dump with a clock row: research/18 §3.9 measured that artifact at 0–0.68 s, larger than the threshold |

### 3.2 Rows where MoveScale still fires but the stick is still dead

These rows do not match frost1's shape (MoveScale silent), but launch 1 can land on them.

| # | branch | row | value | implicates | spec distinguishes? |
|---|---|---|---|---|---|
| R7 | `FUN_00594cf0`, online, `DAT_0045a1ca == 0` → axes set to 0, return 1 before `FUN_005966a0` | MoveScale fires; `0x45a1ca` | `0` | cable monitor (research/18 §3.11: measured 1 online) | **no** — not peeked |
| R8 | `FUN_00594cf0`, `ng+0xdc && !ng+0xd2 && A+0xfd3` → return 1 before `FUN_005966a0` | MoveScale fires; `*0x437ce8:64` and `A+0xfd3` | all three true | respawn-mode health-regen branch | **half** — ng is covered, `+0xfd3` is not |
| R9 | MoveScale `f12 == 0` (the §3.12 lag scale) | `MoveScale [call] f12`; `NetIdle [ret] v0` | `f12 < 1`, idle > 5500 ms | network idle | **yes** |
| R10 | `FUN_00551ec0` else arm zeroes `A[0x8f..0x91]` when `A+0xF7C > 4.0` (online dead-timer; accumulates in `FUN_00543f70` while `+0xF7A != 1`), or state 5/6/9/10, and so on | MoveScale fires; `A+0xF7C`, `A+0xF7A` | `+0xF7C > 4`; `+0xF7A != 1` | life byte never reached 1 | **half** — `+0xF78:1` gives `+0xF7A`, not `+0xF7C` |

### 3.3 The ghost flag reaches R2a: the spawn-dead chain

**Correction (2026-09-13, after independent review):** the first draft of this section said
`ng+0xd2` reached no stopping condition. That was wrong; the bounded search missed this chain.
**The chain is [verified]** (decomp plus ELF bytes, re-derived by the review and re-read here). That it
**fires on Frostfire is [inference]** until launch 1.

1. `FUN_001f5e70` (online load flow) → `FUN_002b7a90` → **`FUN_002b7d60`**, once per player creation
   (`FUN_005442c0` sets `DAT_0044ce50 = 1`). Online only (`0x45a0c1 != 0`).
2. `FUN_002b7d60` takes the local actor from `FUN_002b3580()` (= `DAT_00440c38`, equal to `*0x408c58` in
   the images) and reads `ng+0xd2` (`0x2b7e80: lbu v0,0xd2(s1)`):
   - `FUN_002c2fa0()` (JoinAsSpectator: `FUN_002f6d00` on the valve `"JoinAsSpectator"` (`0x3f5730`) `!= 0`,
     or `DAT_004413d8`) true → `FUN_00543d50(actor)`;
   - else if `ng+0xd2 != 0` and `ng+0xdc == 0` → `FUN_00543d50(actor)` (the flag stays set);
   - else if `ng+0xd2 != 0` and `ng+0xdc != 0` → `FUN_00543d50(actor)`, then `ng+0xd2 = 0`.
3. **`FUN_00543d50` spawns the actor dead:** if health `+0x1044 != 0` it zeroes it, and either sets
   `+0xfb0 = 6` and calls actor `vtbl[0x58]` (death, when `+0xe1 & 0x10`) or calls `C->vtbl[0x54]`.
   It then **always** calls `A->vtbl[0x90](A, 8)` and zeroes the health holder's `+0x9c`.
4. `vtbl[0x90]` = `FUN_0058a6b0` → `FUN_0028dfb0(A+0x170, 8)` writes **`A+0x174 = 8`**.
5. `FUN_00551ec0`'s guard disjunct 1 is now true (R2a). `FUN_00592560` runs instead of `FUN_00594cf0`,
   and MoveScale stops.

So a non-spectator local player whose `ng+0xd2` is non-zero at first spawn is spawned dead in state 8.
**All our images read `0xAF` at `ng+0xd2`; the console reads `0`** (research/19 F3; Task 4 Step 1).

**`ra` of the `FUN_00543d50` call names the arm** [verified]: `0x2b7e74` = JoinAsSpectator;
`0x2b7ea0` = ghost with respawn-game on (flag then cleared); `0x2b7eb0` = ghost with respawn-game off;
`0x599dfc` = the unrelated caller `FUN_00599b60`.

**The spectator branch.** `FUN_005979a0` (`C->vtbl[0x18]`, CtlSpec18) has one real call site,
`0x29e8d4` in `FUN_0029e8b0`. That function is called from `FUN_00547af0` (actor `vtbl[0x58]`, pointer at
`0x6691f8`) and sits in the base actor vtables' `+0x58` slots. **Actor `vtbl[0x58]` has three
callers:** `FUN_00543f70` (online dead-timer > 20 s), `FUN_005477a0` (health <= 0) and `FUN_00543d50`
(spawn-dead, step 3). Online, `ng+0xdc == 0 || ng+0xd2 != 0` selects the spectator object
(`FUN_005ef2f0(0x18)`, message `0x22`); otherwise `FUN_00552780` (respawn) runs. [verified]
Row: `CtlSpec18 [call] a0==C` plus `*0x437ce8:64` bytes `+0xdc`/`+0xd2`. Spec distinguishes: yes.

**`ng+0xdc` is "respawn game":** `FUN_002a7560` sets it to `mp_allow_respawn` (valve `ng+0x64`) `!= 0
&& ng+0x111 == 5`. `ng+0x111` is uninitialised (F3), but online `FUN_001f5e70` writes it from
`FUN_002c8a00(0x441650, …)` just before computing `+0xdc`. [verified]

Spec §1.1's "a ghost silences the move path upstream (dispatch to `FUN_00592560`)" therefore
**stands**, through R2a. **Open question:** why does Medley move? Either `FUN_002232a0` or
`FUN_001f6660` clears the flag earlier there, or the recycled byte differs per allocation. Launch 1's
Medley control (Step 5b) answers it.

### 3.4 frost1's 0.6 s window is a coincidence

frost1's MoveScale timestamps are **host wall clock** (`steady_clock` since trace start, 0.1 s
resolution), not guest time. A ran `#0` 371.4 s → `#17` 372.0 s = 0.6 s; **B ran 365.7 s → 366.2 s =
0.5 s**. The window has nothing to do with R6's guest-clock 0.6 s threshold. [verified] R6 remains
excluded on Medley only (research/18 §3.9) and is read from the peek. MoveScale is reached only when
`0x45a0c1 != 0`. R2a (via §3.3), R2b and R2c give a silent MoveScale with PlayerUpd itself absent. R3,
R4 and R5 give it with PlayerUpd still running.

Side notes from the review [verified]: "Medley" in `READERC.ZAR` is a playlist, not a map, so which map
kill2 loaded is unconfirmed. The map ZDBs (`game/disc/RUN/MP*.ZDB`, MP2 = FROSTFIRE) contain no literal
`ai::STOPALL`, and the format stays opaque without extraction (R4's script route is unconfirmed, not
excluded).

## 4. Launch-1 spec coverage and proposed additions

What the current spec covers [verified against the peek/dump parser]: `*0x408c58:64` = `A+0x00..+0xfc`
(the controller pointer and the `+0xC8` team). `*0x408c58+0x400:12` = `+0x400..+0x42c`, which
includes `+0x420`. `*0x408c58+0xF78:1` = `+0xF78..+0xF7B` (life `+0xF7A` only).
`*0x408c58+0x1044:1` = health only. `*0x437ce8:64` + `+0x100:21` = the whole 0x14c block.
`0x45a0c0:1` includes `0x45a0c1`. **Not covered:** `A+0x174`, `+0xF7C`, `+0xFCF`, `+0xFD3`, `+0x105C`,
`+0x1061`, `0x45a1ca`, the return value of `FUN_00566940`, and the writer of `0x3df1b0`.

Rows the spec as written cannot distinguish: **R2a (the F3 chain's end state), R2b, R2c (the `+0xfcf`
half, which is also the `0x55205C` gate), R5 (partial)**. Supplementary R7, R8 and R10 are also blind.
It also cannot see **which `FUN_00543d50` arm fired** (§3.3).

Proposed additions (each fits the 64-word cap; item start addresses are unchanged, so address-keyed
parsers keep working):

Peeks:
1. **`*0x408c58+0x174:1` — top priority** → R2a and the F3 chain (low 16 bits == 8).
2. Grow `*0x408c58+0xF78:1` to **`*0x408c58+0xF78:24`** (`+0xF78..+0xFD7`) → life `+0xF7A`, dead-timer
   `+0xF7C` (R10), **`+0xFB0`** (6 = spawn-dead's death), spawn time `+0xFB4`, `+0xFCD/+0xFCE/+0xFCF`
   (R2c), `+0xFD3` (R8).
3. Grow `*0x408c58+0x1044:1` to **`*0x408c58+0x1044:8`** (`+0x1044..+0x1063`) → health, `+0x105C` bit
   `0x40`, `+0x1061` bit `0x20` (R2b).
4. `0x45a1c8:1` → `0x45a1ca` (R7).
5. Valve self-check: add `*0x437ce8+<off>**:3` for the nine valves and `*0x43668c**:3`; check them
   against §2.2. Keep the `*:2` items: they carry the value.
6. **`*0x44fa90:2` and `0x4413d8:1`** → the JoinAsSpectator valve (name ptr, value) and flag.
   `*0x44fa90` is filled lazily, so an early empty item is not a failure.

Traces:
7. **`0x598840:InputEnable`** → R4's writer (`a0` = new value, `ra` = cinematic or `ai::STOPALL`).
8. **`0x543d50:SpawnDead`** → the F3 chain; `ra` names the arm (`0x2b7e74` / `0x2b7ea0` / `0x2b7eb0` /
   `0x599dfc`). Rare, so every call is logged.
9. **`0x543b90:GhostRevive`** → the clear-and-revive path in `FUN_002232a0`.
10. `0x566940:AutoMove` → R5's `[ret] v0`, **only if the line budget allows** (~4 lines/s per instance
    at EVERY=10).
11. Rename the existing trace name **`GhostClr3` → `SpawnGhost`** for `0x2b7d60`. It spawns dead and
    only sometimes clears.

**Step 4 A/B precondition (proposed):** a `SpawnDead` call with `ra` `0x2b7eb0` or `0x2b7ea0`, **and**
`A+0x174` low 16 bits `== 8`, **and** `ng+0xd2 != 0`, all on the reproducing side.

**Open question for launch 1's Medley control:** why Medley moves (§3.3).

## 5. `score-control` over the old logs (Step 1 item 4)

`python -m tools_py.parity.verdict_core score-control logs/run_A_20260913_004754.log logs/run_B_20260913_004754.log`
(frost1), exit 3:

```
[A] logs/run_A_20260913_004754.log
[A] rows read: lines=22154 peek=2634 actor=1154 pad=434 pad_torn=0 pad_unrecovered=0 clock_anchors=1 call[MoveScale]=18 ret[MoveScale]=18
[A] hold   412.15..  413.65 (1.50s) net=  0.00 snap=  0.00 drift=  0.00 -> FAIL (net 0.0 < 40)
[A] hold   422.65..  424.15 (1.50s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[A] hold   432.90..  434.40 (1.50s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[A] hold   443.40..  444.90 (1.50s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[A] side NO-CONTROL (4 hold(s) scored)
[B] logs/run_B_20260913_004754.log
[B] rows read: lines=22431 peek=2611 actor=1153 pad=344 pad_torn=0 pad_unrecovered=0 clock_anchors=1 call[MoveScale]=18 ret[MoveScale]=18
[B] hold   406.20..  407.70 (1.50s) net=  0.00 snap=  0.00 drift=  0.00 -> FAIL (net 0.0 < 40)
[B] hold   416.70..  418.20 (1.50s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[B] hold   426.95..  428.45 (1.50s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[B] hold   437.45..  438.95 (1.50s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[B] side NO-CONTROL (4 hold(s) scored)
RESULT NO-CONTROL
```

`python -m tools_py.parity.verdict_core score-control logs/run_A_20260912_231341.log logs/run_B_20260912_231341.log`
(kill2), exit 0:

```
[A] logs/run_A_20260912_231341.log
[A] rows read: lines=20845 peek=2840 actor=1173 pad=579 pad_torn=0 pad_unrecovered=0 clock_anchors=57 call[MoveScale]=826 ret[MoveScale]=826
[A] hold   458.90..  460.41 (1.51s) net= 60.35 snap=  1.50 drift=  0.00 -> PASS
[A] side CONTROLLABLE (1 hold(s) scored)
[B] logs/run_B_20260912_231341.log
[B] rows read: lines=256867 peek=2700 actor=1056 pad=497 pad_torn=0 pad_unrecovered=0 clock_anchors=57 call[MoveScale]=770 ret[MoveScale]=770
[B] hold   453.07..  454.56 (1.49s) net= 64.01 snap=  1.74 drift=  0.00 -> PASS
[B] side CONTROLLABLE (1 hold(s) scored)
RESULT CONTROLLABLE
```

Both reproduce the expected verdicts. [verified] The CLI does **not** print the three blind classes
beside the verdict, although Step 4 expects it to; they exist only as code comments in
`verdict_core.py`. [verified]

**Zero-run `ng` read:** frost1 and kill2 did not peek `*0x437ce8` (their spec was
`0x416054:3,*0x408c58:64,*0x408c58+0x200:32,*0x408c58+0xc0*:32,0x408c58:4`), so `ng+0xd2/+0xdc/+0xde`
cannot be read from them. [verified]
