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
| `*0x43668c*:3` (corrected after launch 1: `*0x43668c` already lands on the valve, so `**` dereferences the name's first word) | `7373696d` | `5f6e6f69` | `726f6261` |

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
| R6 | multiplayer snap-back: `0x45a0c1 && DAT_004365c0 - A+0x420 > 0.6` | **same peek row**: `0x4365c0:1` against `*0x408c58+0x400:12` word 8 (`+0x420`) | difference > 0.6 | **no ground-probe hit for 0.6 s** (corrected after launch 1 review). `+0x400..+0x41c` is the last ground hit and `+0x420` its clock time, stamped each frame by `FUN_005b0420` (store at 0x5b05d0) when `FUN_005b5d40` hits. The only other stores are `FUN_00579220` (0x579490, drag-link release) and `FUN_005794d0` (0x579640, reached only via `FUN_00592d50` = controller `vtbl[0x78]`, the use/drag handler). Neither is a network position update, so the earlier label "position-apply (`FUN_005794d0`)" was wrong, and research/18 §3.9 carries the same mislabel. On a snap the position is re-set to `+0x400..+0x408` every frame | **yes, from the peek**. Do **not** pair the `a0+0x4*+0x400:9` dump with a clock row: research/18 §3.9 measured that artifact at 0–0.68 s, larger than the threshold |

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

### 3.4 frost1's 0.6 s window is the R6 threshold (corrected after launch 1)

**Not a coincidence.** Two things start together at round start:
- the stamp `+0x420`, at about 0;
- the guest clock `DAT_004365c0`, at 0. It is mission object `0x4364e0+0xe0`, accumulated by `FUN_002aa490` and zeroed by `FUN_002ac060`.

So MoveScale runs exactly until the clock passes 0.6 s. frost1's host-clock windows (A `#0` 371.4 s →
`#17` 372.0 s = 0.6 s; B 365.7 → 366.2 s = 0.5 s) are that threshold seen at 0.1 s host resolution.
Launch 1 confirmed it (§6.4). [verified, bracketed]

The first draft called the window a coincidence because host time is not guest time. That missed that both
clocks start at round start.

MoveScale is reached only when `0x45a0c1 != 0`:
- R2a (via §3.3), R2b and R2c give a silent MoveScale with PlayerUpd itself absent;
- R3, R4, R5 and R6 give it with PlayerUpd still running.

On kill2's map, research/18's `run_20260912_154530` (same spawn coordinates as kill2) shows `+0x420`
tracking the clock from dump #2 to #6960, so R6 stays false there [verified by review]. kill2's map name
is still unconfirmed.

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

## 6. Launch 1 (Step 3–4 reading, draft, 2026-09-13)

**Draft, uncommitted (the controller commits).** Marks as in §1–§5: **[verified]** = read from this run's
logs or the decomp in this step; **[inference]** otherwise.

### 6.1 Launches and the command

| # | per-instance logs | out dir | result |
|---|---|---|---|
| 1a | `logs/run_[AB]_20260913_072321.log` | `logs/parity/s5_t1_launch1` | **lobby failure**: `B_JOIN GAME did not reach the GAME LOBBY (game_lobby band distance 0.577, threshold 0.45)`. B's capture still shows the games list with `test` (FROSTFIRE, 1/16) |
| 1b | `logs/run_[AB]_20260913_072922.log` | `logs/parity/s5_t1_launch1b` | **lobby failure, same class and same distance 0.577**. Server side, Medius answered B's `MediusJoinGameRequest` with `MediusSuccess`, and DME sent B `CONNECT_COMPLETE` and A `CONNECT_NOTIFY`. The transport joined, but B's UI never left the games list inside `join_game`'s fixed 25 s + 3 s presses |
| 1c | **`logs/run_[AB]_20260913_073548.log`** | `logs/parity/s5_t1_launch1c` | **usable**: both instances reached Frostfire gameplay (`A_liveness OK: 163 in-game peek rows`, `B_liveness OK: 163`). No kill (`RESULT FAIL … closest_3d=692.07`) |

Three launches against Step 6's cap of 8; one usable Frostfire match.

**Preconditions checked:**
- Horizon stack already running: `Server.NAT`, `Server.UniverseInformation` (10071), `Server.Dme` (10073) and `Server.Medius` (10075/10078). It was not restarted.
- Persona B present in `game/disc/mc0_b/BASCUS-97275SOCOMII`.
- LAN address from `ipconfig` is `192.168.2.10`.
- Exe `dist/socom2.exe` carries both `PS2X_HLE_STATS` and `PS2X_GUEST_MALLOC_ZERO`.
- No runtime change since `03d3aa6`.
- **Disk: only 5 GB free on C:.** Each log in this run is 15 MB, so this is not a problem yet.

**Command.** Each launch ran `bash scripts/run_detached.sh --owner s5t1-launch1 --purpose "…" logs/s5_t1_launch1.sh logs/s5_t1_launch1{,b,c}.done [logs/parity/s5_t1_launch1{b,c}]`. The job script (`logs/s5_t1_launch1.sh`, git-ignored) runs these steps:
1. It runs `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/kill_stale_drivers.ps1` inside the lock (`0 killed`).
2. It unsets `PS2X_GUEST_MALLOC_ZERO` and `PS2X_GUEST_MALLOC_ZERO_B`, so the knob is off on both instances.
3. It exports the environment below.
4. It runs `python -m tools_py.parity.online_match_ours --existing-b --hold 30 --until-kill --map frostfire --engage 22 --engage-dy 10 --max-steps 60 --max-walk-seconds 240 --fight-seconds 200 --kill-timeout 470 --out "$OUT" --seconds 1200 > logs/parity/drive_${NAME}.txt`.

```
PS2X_SOCOM2_SERVER=192.168.2.10
PS2X_SOCOM2_RSA_KEY_B=b
PS2X_SOCOM2_INPUT_TRACE=1
PS2X_PC_SAMPLER=0.25
PS2X_HLE_STATS=1
PS2X_CALL_TRACE_EVERY=10
PS2X_CALL_TRACE=0x553dc0:MoveScale,0x594cf0:PlayerUpd,0x592560:CtlAlt14,0x5979a0:CtlSpec18,0x551ec0:ActorUpd,0x30cd80:NetIdle,0x2a7420:SetMajor,0x2a73b0:SetMinor,0x2a7490:SetMyMajor,0x1f5e70:GhostSet,0x1f6660:GhostClr,0x2232a0:GhostClr2,0x2b7d60:SpawnGhost,0x544210:SetLife,0x543d50:SpawnDead,0x543b90:GhostRevive,0x598840:InputEnable
PS2X_CALL_TRACE_DUMP=PlayerUpd:a0+0x170:1,PlayerUpd:a0+0x4*+0x400:9
PS2X_PEEK=0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,*0x437ce8+0x0c*:2,*0x437ce8+0x10*:2,*0x437ce8+0x14*:2,*0x437ce8+0x20*:2,*0x437ce8+0x24*:2,*0x437ce8+0x2c*:2,*0x437ce8+0x58*:2,*0x437ce8+0x5c*:2,*0x437ce8+0x70*:2,*0x43668c:2,0x4365c0:1,0x45a0c0:1,0x3df1b0:1,0x45a1c8:1,*0x44fa90:2,0x4413d8:1,*0x437ce8+0x0c**:3,*0x437ce8+0x10**:3,*0x437ce8+0x14**:3,*0x437ce8+0x20**:3,*0x437ce8+0x24**:3,*0x437ce8+0x2c**:3,*0x437ce8+0x58**:3,*0x437ce8+0x5c**:3,*0x437ce8+0x70**:3,*0x43668c**:3,0x408f10:2,0x408c58:4
```

Everything below reads **launch 1c**. `A` = `*0x408c58` (instance A `0x1583f60`, B `0x1586eb0`; vtable
`0x6691a0`). `C` = `A+0xc0` (A `0x1566a40`, B `0x1568000`; vtable `0x6694b0` on both). `ng` = `0x869360`
on both. Log line numbers are `ln` in the named instance's log. Peek rows carry no time of their own:
"t" is the host time of the last `[call]` before the row.

### 6.2 Zero-rows check [verified]

**Peek items, rows per instance (A / B).** Total rows 2667 / 2643; actor items resolve from round start.
- `0x416054:3`, `0x4365c0`, `0x45a0c0`, `0x3df1b0`, `0x45a1c8`, `0x4413d8`, `0x408f10:2` and `0x408c58:4`: **2667 / 2643**.
- All six `*0x408c58…` items (`:64`, `+0xc0*:32`, `+0x400:12`, `+0x174:1`, `+0xF78:24`, `+0x1044:8`): **1154 / 1153**.
- `*0x437ce8:64`, `+0x100:21`, the nine `*0x437ce8+<off>*:2` valves and `*0x43668c:2`: **2656 / 2632**.
- `*0x44fa90:2` (JoinAsSpectator, lazy): **1958 / 1956**.
- Alignment check: my parser matched every printed segment to its spec item on every row (0 unaligned rows), so no chain failed mid-row after the actor existed.

**Name bytes.** All nine `*0x437ce8+<off>**:3` items match §2.2 on **every** row, both sides (2656 / 2632, 0
mismatches). The online name pointers equal §2.1's single-player values (`0x006b7f30`, `0x006b7f20`,
`0x006cc9fc`, `0x00694ae0`, `0x00694b08`, `0x006cca14`, `0x006ccad4`, `0x006ccaec`, `0x006b7f70`,
`mission_abort` `0x006b7fb0`), which settles §2.1's caveat for online on this build.

**Failed item: `*0x43668c**:3` is a spec defect.** It mismatches on 2656 / 2632 rows. `*0x43668c` already
lands on the valve (the value `DAT_0043668c` holds the valve address), so `*0x43668c*` is the name and
`**` dereferences the first four name bytes. The row prints `@7373696d:` ("miss", little-endian) and
then unrelated memory. By Step 4's rule this item's reading fails. The valve is still identified by its
`*0x43668c:2` word 0 = `0x006b7fb0` (§2.1), and the resolved address `0x7373696d` is itself the first
name word. **Fix for later launches: `*0x43668c*:3`**, and §2.2's last table row has the same error.
The JoinAsSpectator valve has no name-bytes item; its pointer reads `0x006b8130` (value 0) on both sides, unverified by name.

**Trace slots: call lines, last `#n`, and `[ret]` lines (A / B).**
- MoveScale: 16 (#15) / 18 (#17); rets 16 / 18.
- PlayerUpd: 1032 (#7620) / 1094 (#8230).
- ActorUpd: 1795 (#15240) / 1918 (#16470).
- NetIdle: 16 (#15) / 18 (#17).
- SetMajor: 3 / 3. SetMinor: 4 / 4. SetMyMajor: 3 / 4.
- GhostSet: 57 / 61. GhostClr: 1 / 1. SpawnGhost: 1 / 1. SetLife: 1 / 1.
- `[ret-dump]` PlayerUpd: 2066 / 2188.
- **Empty on both sides: CtlAlt14, CtlSpec18, GhostClr2, SpawnDead, GhostRevive and InputEnable.**

These six are the negatives the branch table predicts. The hooks cannot be proven live from an empty slot, but the relevant callers are all `jal`/`jalr`, which the hook sees:
- the `ra` values in §3.3 are return addresses, so those calls are `jal`;
- `FUN_00551ec0` reaches `vtbl[0x14]` through `jalr`;
- the same mechanism logged MoveScale from its `jal` at `0x595024`.

KNOWN §4's tail-call blind spot (a `J`) remains the blind class for these six rows.

### 6.3 score-control [verified]

`python -m tools_py.parity.verdict_core score-control logs/run_A_20260913_073548.log logs/run_B_20260913_073548.log`, exit 3:

```
[A] logs/run_A_20260913_073548.log
[A] rows read: lines=35256 peek=2667 actor=1154 pad=434 pad_torn=1 pad_unrecovered=1 clock_anchors=60 call[ActorUpd]=1795 call[GhostClr]=1 call[GhostSet]=57 call[MoveScale]=16 call[NetIdle]=16 call[PlayerUpd]=1032 call[SetLife]=1 call[SetMajor]=3 call[SetMinor]=4 call[SetMyMajor]=3 call[SpawnGhost]=1 ret[ActorUpd]=1794 ret[GhostClr]=1 ret[GhostSet]=18 ret[MoveScale]=16 ret[NetIdle]=16 ret[PlayerUpd]=1032 ret[SetLife]=1 ret[SetMajor]=3 ret[SetMinor]=4 ret[SetMyMajor]=3 ret[SpawnGhost]=1
[A] hold   420.80..  422.32 (1.52s) net=  0.00 snap=  0.00 drift=  0.00 -> FAIL (net 0.0 < 40)
[A] hold   431.40..  432.93 (1.53s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[A] hold   441.60..  443.10 (1.50s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[A] hold   452.20..  453.70 (1.50s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[A] side NO-CONTROL (4 hold(s) scored)
[B] logs/run_B_20260913_073548.log
[B] rows read: lines=36116 peek=2643 actor=1153 pad=346 pad_torn=0 pad_unrecovered=0 clock_anchors=60 call[ActorUpd]=1918 call[GhostClr]=1 call[GhostSet]=61 call[MoveScale]=18 call[NetIdle]=18 call[PlayerUpd]=1094 call[SetLife]=1 call[SetMajor]=3 call[SetMinor]=4 call[SetMyMajor]=4 call[SpawnGhost]=1 ret[ActorUpd]=1918 ret[GhostClr]=1 ret[GhostSet]=18 ret[MoveScale]=18 ret[NetIdle]=18 ret[PlayerUpd]=1094 ret[SetLife]=1 ret[SetMajor]=3 ret[SetMinor]=4 ret[SetMyMajor]=4 ret[SpawnGhost]=1
[B] hold   414.79..  416.32 (1.53s) net=  0.00 snap=  0.00 drift=  0.00 -> FAIL (net 0.0 < 40)
[B] hold   425.26..  426.77 (1.52s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[B] hold   435.70..  437.23 (1.53s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[B] hold   446.15..  447.69 (1.53s) net=  0.00 snap=  0.00 drift=  n/a -> FAIL (net 0.0 < 40; pad not neutral over the 10 s before the hold)
[B] side NO-CONTROL (4 hold(s) scored)
RESULT NO-CONTROL
```

**The failure reproduces on both sides.** The actor position (words 7/8/9) has **one value for the
whole run** on each side: A (795.7, 101.0, 613.6) and B (535.7, 142.9, 1253.6), which are the spawn
positions. The CLI still does not print the three blind classes (§5).

### 6.4 The branch table, filled [verified unless marked]

Filters: ActorUpd `a0 == A` 1645 / 1768 (the other 150 / 150 are the remote avatar); PlayerUpd
`a0 == C` 1032 / 1094; MoveScale `a0 == A` on every call.

| row | observed A | observed B | stopped it? |
|---|---|---|---|
| **F3 chain, step 1–2** (`SpawnGhost` reads `ng+0xd2`) | `ng+0xd2` = `0xAF` from the first peek row (ln154, before any map) → **`0` at ln11160 (t 377.5)**, right after `GhostClr` = `FUN_001f6660` `#0` (ln11143, t 377.4, `ra 0x2cec24`). `SpawnGhost #0` came later (ln11258, t 379.1, `ra 0x2b7ac0`) | `0xAF` → **`0` at ln10867 (t 371.5)** after `GhostClr #0` (ln10856, t 371.4, `ra 0x2cec24`); `SpawnGhost #0` ln10971 (t 373.1) | **no** — the flag is already clear when it is read |
| **F3 chain, step 3** (`SpawnDead` and its `ra`) | **0 calls** | **0 calls** | **no** |
| R2a `A+0x174` low 16 | `0` (ln11326) → `1` (ln11399, t 380.0), then 1 all run | `1` all run (ln11083 on) | **no** (never 8) |
| R2b `A+0x1061 & 0x20` | bit 0x20 clear all run; **the byte is `0x04`** (1145 rows), `0x05` (8), `0x00` (1, first row) | bit 0x20 clear; byte `0x04` (1142), `0x05` (11) | no (bit 0x04 is R6's evidence, below) |
| R2c `0x45a0c1` / `A+0xFCF` | 1 / 0 | 1 / 0 | no |
| R0/R1 ActorUpd for `A`, `C` non-null | 1645 lines, `#15240`; `C` stable | 1768, `#16470`; `C` stable | no |
| dispatch arm | `PlayerUpd` runs all run (`#7620`), `CtlAlt14` 0, `CtlSpec18` 0 | `#8230`, 0, 0 | **the normal arm runs** |
| R3 `mission_abort` | 0 all run (name ptr `0x006b7fb0`) | 0 all run | no |
| R4 `0x3df1b0` / `InputEnable` | 1 all run; 0 calls | 1 all run; 0 calls | **no** (the STOPALL candidate is excluded) |
| R5 `C+0x170 & 3` (PlayerUpd dump) | `0x800` on 1032 dumps, `0x810` on `#0` → `&3 = 0` | `0x800` on 1093 dumps, `0x810` on 1 | no (post-return and 1-in-10, per §3.1) |
| **R6 snap-back** `0x45a0c1 && DAT_004365c0 − A+0x420 > 0.6` | **`A+0x420` raw word `0x00000000` on all 1154 actor rows**, never written. `DAT_004365c0` counts up from 0 at round start: 0.000 (ln11326), 0.183 (ln11399), **0.383 (ln11501, false)**, **0.616 (ln11611, true)**, 68.42 by t 458 | **`A+0x420` raw word `0x00000102` on all 1153 rows** (uninitialised, never written; ≈3.6e-43 as a float); 0.067 (ln11083), **0.550 (ln11337, false)**, **0.783 (ln11419, true)**, 77.66 by t 456 | **YES** [verified, bracketed] — see below |
| R7 `0x45a1ca` | 1 | 1 | no |
| R8 `ng+0xdc` | 0 | 0 | no (needs `+0xdc`) |
| R9 MoveScale `f12` / NetIdle `v0` | f12 = 1.0 on all 16; NetIdle `v0` ≤ `0x12b` (299 ms) | f12 = 1.0 on 18; `v0` ≤ `0x11a` | no |
| R10 `+0xF7A` / `+0xF7C` | 1 / 0.0 all run | 1 / 0.0 all run | no |
| `ng+0x113/+0x114/+0x115` | (1,1,1) t 273.7 → (2,2,2) t 375.9 → (2,2,1) t 377.5 → (2,2,2) t 379.3 → **(3,2,2) t 380.0**, then stable | (1,0,0) t 310.9 → … → **(3,2,2) t 374.3**, then stable | they do not stall; they settle at "my major 3, major 2, minor 2" as the move path starts |
| MoveScale first / last | `#0` ln11333 t 379.9 → `#15` ln11588 t 380.5 | `#0` ln11051 t 374.0 → `#17` ln11342 t 374.6 | — |

**The row that stopped the move path is R6, the multiplayer snap-back inside `FUN_00594cf0`, on both
instances.**
- MoveScale's last call falls between the last peek row with `DAT_004365c0 − A+0x420 ≤ 0.6` and the
  first row with `> 0.6`. On A that is rows ln11501 and ln11611, with MoveScale `#15` at ln11588. On B it
  is rows ln11337 and ln11419, with `#17` at ln11342.
- `PlayerUpd` keeps running on the same `C`, and `NetIdle` stops with MoveScale, because it is only
  called on the `cVar7 == 0` branch.
- `A+0x400..+0x408` equals the actor position on every row, as expected if the position is re-set from
  `+0x400` every frame.

**Blind class:** the peek is 0.25 s and host-timed, so the 0.6 crossing is bracketed, not pinned. The
test's instruction bytes are at `0x594eac–0x594ed8` [verified by review].

**Retraction.** §3.4's "frost1's 0.6 s window is a coincidence" was wrong; it is corrected in place.

**What `+0x420` is.** Decomp, re-derived by the launch-1 review.

Only three functions store to actor `+0x420`:
- `FUN_005b0420` (0x5b05d0);
- `FUN_00579220` (0x579490);
- `FUN_005794d0` (0x579640).

`FUN_00550570` and `FUN_00592d50` are callers, not writers.

**The per-frame stamper is the ground probe.**
1. Actor `vtbl[0x20]` = `FUN_005506a0`. When `+0xf40 != 0` it calls `FUN_005b0840`, which queues a probe
   and sets `+0x2cc` (-999 when nothing is queued).
2. Actor `vtbl[0x24]` = `FUN_00550570`. It calls `FUN_005b0800` (the batch query), then `FUN_005b0420`.
3. `FUN_005b0420` evaluates the probe with `FUN_005b5d40`:
   - on a **hit** it copies into `+0x400..+0x41c` and sets `+0x420` = clock;
   - on a **miss** with `DAT_003df1c8 != 0` it sets `+0x1061` bit 0x04 and writes no stamp.

The other two writers are not network position updates:
- `FUN_005794d0` is reached only via `FUN_00592d50` = controller `vtbl[0x78]`, the use/action-button
  drag/carry handler (actor states 9/10);
- `FUN_00579220` releases the `+0xeac` drag link.

R6 therefore means: **online, no ground hit for 0.6 s → snap back.**

**RDRAM images show the per-frame stamp** [verified by review]:

| image | clock `DAT_004365c0` | `+0x420` | other fields |
|---|---|---|---|
| `spawn_pcsx2` | 53.138 | 53.138 | |
| `s4rand_ours` | 80.710 | 80.710 | |
| `spawn_ours` | 22.830 | 22.830 | |
| `rest_ours_gq` | 22.154 | 22.154 | |
| `rest_ours`, `spawn_ours3` | | stale | `+0x2cc` = -999, `+0xf40` = 0 (physics off) |
| `spawn_ours2` | | stale | `+0x1061` = 0x04 (probe miss) |

**On Frostfire the probe missed at the spawn point, on both sides.** `+0x1061` (byte 1 of word 7 of
`*0x408c58+0x1044:8`) is `0x04`, sometimes `0x05`:
- A: from ln11399 (clock 0.183), after one `0x00` row;
- B: from the first actor row (ln11083).

The only other setter of bit 0x04, `FUN_0059ad30`, is called only from the hit branch. Spawn points are
A (795.7, 101.0, 613.6) and B (535.7, 142.9, 1253.6). **Why the probe misses is unmeasured.** Zero-fill
cannot fix this row: B's `+0x420` was uninitialised (`0x102`) and still never stamped.

**Condition sentence (Step 5 form).** *The Frostfire local player's ground probe (`FUN_005b5d40`,
evaluated in `FUN_005b0420` each frame) never hits at the spawn point, so `actor+0x420` is never stamped
and the online snap-back in `FUN_00594cf0` suppresses MoveScale from clock 0.6 s; why the probe misses is
open.*
- R6 firing: **[verified, bracketed]**.
- Probe miss: **[inference, strong]**. Bit 0x04 is the direct evidence. Neither `FUN_005b5d40`'s return
  nor `+0x2cc`, `+0xf40` or `DAT_003df1c8` was traced or peeked.

### 6.5 Decision (Step 4, as amended)

The A/B precondition fails on all three counts, on both sides:
- `SpawnDead` never ran;
- `A+0x174` low 16 bits is 1, not 8;
- `ng+0xd2` was 0 when `SpawnGhost` read it.

Ghost-flag detail, re-derived by review:
- Word 0x34 is little-endian `d0 d1 d2 d3`. It reads `afaf0000`, then `af000000` after `GhostClr #0`.
  - A: `GhostClr` ln11143, word changes ln11160, SpawnGhost ln11258.
  - B: last `afaf0000` row ln10853, `GhostClr` ln10856, word changes ln10867, SpawnGhost ln10971.
- `+0xd3` stays `0xAF`.
- `GhostSet` ran 57 (A) and 61 (B) times after the clear without re-setting.
- All 17 hooks were live, and every caller of `0x543d50` is a `jal`.

**Launch 2 is therefore not the zero-fill A/B.** The result "reproduces otherwise", at level R6, with the
probe-miss condition sentence above. The uninitialised ghost flag is **not** the cause on this run.

**Proposed next launch: Frostfire first, then the Medley control (Step 5b) with the same set.** Keep
launch 1's full spec and add the following.
- **Traces:**
  - `0x5b0840:ProbeQueue`;
  - `0x5b0800:ProbeBatch`;
  - `0x5b5d40:ProbeEval` (`[ret] v0==0` = miss);
  - `0x5b0420:ProbeTake`.
- **Dumps:** `ProbeEval:a1:19,ProbeEval:a1+0x48*:16`, covering the probe origin `+4..+0xc`, the candidate
  count `+0x34` and the first candidate.
- **Peeks:**
  - `*0x408c58+0x2c0:4` (`+0x2cc`);
  - `*0x408c58+0xf40:1`;
  - `0x3df1c8:1`;
  - `0x44d588:5`;
  - `0x44f354:2`;
  - `*0x43668c*:3` in place of `*0x43668c**:3`.
- **Optional:** `PS2X_RDRAM_DUMP_AT` on `PlayerUpd#2000`, with a distinct path per instance, for offline
  replay.
- **Log budget:** ProbeEval and ProbeTake may run every frame for every actor. Check the 200 MB bound at
  liveness.

### 6.6 First live reads (Frostfire, online) [verified]

**Health and life.**
- `+0x1044` health = **1.0** on every row, both sides.
- `+0xF7A` alive = **1**; `+0xF7C` = 0.0; `+0xFB0` = `0x00080500` on A and `0x3f800000` on B, never 6.
- `+0xFCF` = 0; `+0xFD3` = 0.

**Team `A+0xC8`.** A = `0x40000001`, B = `0x80000100`, constant.

**Valves (values; name pointers as in §6.2).**
- `mp_round_count`, `mp_game_over`, `late_joiner`, `total_mp_kills` and `mission_abort`: 0 all run, both sides.
- `player_team`: **A 0 all run; B 0 → 8** (before the map loads).
- `mp_major_game_state`: 0 → 1 → 2 (A t 273.7 / 375.9; B 314.4 / 370.0).
- `mp_minor_game_state`: 0 → 1 → 2 → **1** → 2 (dip at A t 377.5 / B 371.5, alongside `GhostClr`).
- `aiteam_00` / `aiteam_08`: 0 → 1 at round start (A both t 379.3; B 373.3 / 374.3).
- JoinAsSpectator: 0.
- `0x4413d8`: 0. `0x45a0c1`: 1. `0x45a1ca`: 1. `0x3df1b0`: 1.

**`ng` bytes.**
- `ng+0x111` goes `0xAF` → **5** at map load (B passes through 7 at t 310.9).
- `ng+0xdc` = 0 all run, so respawn-game is off despite `+0x111 == 5`, because `mp_allow_respawn` is 0 [inference].
- **`CZNetGame` is at `0x869360` from the first peek row of the boot**, the same address as every
  single-player image. It is allocated at boot, not per map.

**Clock string `0x408f10`.** `05:59` at round start (A ln11399, B ln11221), counting down one per second to
`01:10` at A t 668.6 (289 s of host time for 4:49 of clock). The round clock runs at real time.

**`ng+0xde` sampling period.** No period can be measured: `ng+0xde` is 0 on every row, both sides. It is
written only on frames that reach MoveScale, and those stopped after 0.6 s. The peek period is
0.25 s/row (1154 actor rows over 379.6 → 669.5 s on A).

**NetIdle `[ret]` row rate.** 16 / 18 rows, all inside the 0.6 s MoveScale burst (the unconditional first-300
regime), and **0 afterwards**. The steady-state rate stays unmeasured on Frostfire, because NetIdle is
reached only on the MoveScale branch. `v0` values: 0 ×4, then 0x105 / 0x12b ms (A) and 0x12 / 0x11a ms (B).

**PlayerUpd `[ret] v0`.**
- A: `0x1` ×1017, `0x41a00000` ×15, `0x0` ×1 (`#0`, ln11336).
- B: `0x1` ×1076, `0x41a00000` ×17, `0x544688` ×1.

The non-boolean values coincide with the MoveScale frames, so `v0` is not a clean return on every
path, and one `v0=0` is not evidence of R3/R4 [inference].

### 6.7 HLE stats (last periodic table, t = 660 s, both sides)

`stubs=223 called=100 zero-call=123 unbound=9`, identical on A and B. **58 stubs have calls > 0 and one
distinct return.** The list is identical across sides:
- **Pad:** `scePad2Init` 1, `scePad2GetState` 1 (18192 calls), `scePad2Read` 0x20, `scePad2GetButtonProfile` 5, `sceVibGetProfile` 0.
- **CD:** `sceCdSync` 0, `sceCdInit` 1, `sceCdDiskReady` 2, `sceCdRead` 1, `sceCdGetDiskType` 0x14, `sceCdGetError` 0, `sceCdMmode` 1, `sceCdReadClock` 1, `sceCdStInit`/`StStart`/`StStop` 1.
- **DMA/GS:** `sceDmaReset`/`Send`/`SendN`/`Sync` 0, `sceGsResetGraph`/`ResetPath`/`SetDefDBuff`/`SyncPath`/`SetDefLoadImage`/`SetDefStoreImage`/`ExecLoadImage` 0.
- **libc:** `memchr` 0 (5 calls), `strncat` 0x1e60d0 (30), **`strrchr` 0 (136 calls, never found)**.
- **Kernel/SIF/FS/IOP:** `_sceSDC`/`_sceIDC` 0, `InitThread` 1, `sceSifAddCmdHandler`/`InitRpc`/`BindRpc`/`CallRpc` 0, **`sceSifCheckStatRpc` 0 (29631 calls)**, `sceFsReset` 0, `sceClose` 0, `sceRead` 0x28000 (9), `sceSifInitIopHeap` 0, `sceSifLoadFileReset` 0, `sceSifSyncIop`/`RebootIop` 1, `InitAlarm` 0.
- **Memory card:** `sceMcInit`/`End`/`Open`/`Close`/`Read`/`GetInfo`/`GetDir`/`Chdir` 0.
- **MPEG:** `sceMpegAddStrCallback`/`Init`/`GetPicture`/`Reset` 0.

None of them is on the move path's inputs as mapped in §3. `strrchr` never finding its character is the
one entry worth a look [inference]. KNOWN §4's tail-call blind spot applies: the counts are lower bounds
and zero-call rows can be false.
