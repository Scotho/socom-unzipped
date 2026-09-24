# 43. What SOCOM II r0004 changes against r0001, read out of the two images

Date: 2026-09-24. Sprint 11, after Task 19's 3/3 gate. Read-only: two ELFs, two Ghidra tables, one match
report, one decoded capsule stack. No game was run and no server was contacted. Companion to
`43-r0004-capsule.md` (what *PSRewired's* capsule does — a different artefact with the same number; this
note is about the retail rebuild).

**Every row below is tied to an address, a string or a count.** Where the evidence stops, the row says
`unknown` rather than guessing. The one-line answer: **r0004 is a full 13-month-later rebuild of the two
overlays with the boot loader untouched; its largest single addition is 106 KB of per-map, per-object
level fixup code that r0001 has no trace of; the rest is an enlarged patch-download and memory-card
package path, five new online dialogs, a bumped Medius/Rtime middleware, a version token, and one new
word in the actor.**

## 1. The shape, measured

| fact | value | evidence |
|---|---|---|
| r0001 / r0004 image | 4,835,072 B / 5,016,016 B | `game/disc/socom2_game.elf`, `game/disc_r0004/socom2_game.elf` |
| boot loader `PT_LOAD0` 0x00100000–0x001D5000 | **byte-identical**, 872,448 B | sha256 `df44c69dd848…` both sides |
| `PT_LOAD1` 0x001D5000, 1,536 B | **byte-identical** | sha256 `fdb95ccb3278…` both sides |
| FTSCore `PT_LOAD2` @0x001E7000 | 2,233,472 → 2,416,008 B (**+182,536**) | ELF program headers |
| ZSealEtc `PT_LOAD3` @0x004C5380 | 1,723,520 → 1,721,912 B (**−1,608**) | ELF program headers |
| Ghidra rows | 14,879 → 16,423 | `recomp/socom2_ghidra*.csv` |
| matcher placements | 12,071 of 14,879 (81.1 %) | `game/r0004/match.json` |
| of those: byte-identical / relocation-only / length changed | 5,105 / 6,810 / 156 | recomputed here from the two images |
| object-relative displacements that moved | **331 functions, 654 sites** | reproduced exactly (Task 19 `task-19-node-report.md` §4b) |
| r0001 rows with no placement / r0004 rows never used as a target | 2,808 / 4,351 | `match.json` + the r0004 CSV |
| build banner | `SOCOM 2 r0001 17:22:21 Oct 11 2003` @0x003E17E0 → `SOCOM 2 r0004 10:14:38 Nov  3 2004` @0x0040CC60 | the strings themselves |
| NUL-terminated printable strings (≥5) | 5,066 → 5,231; 359 r0004-only, 194 r0001-only | most of both sets are binary coincidences; the named ones below are all of the meaningful ones |

**The loader being byte-identical is the load-bearing fact of this note.** Everything r0004 changes is in
the two overlays, which is exactly what our recompilation consumes.

## 2. Network, DNAS and anti-cheat

| what | evidence | confidence |
|---|---|---|
| **The client-side join filter now advertises and demands `r0004`.** `FUN_002FD6E0` (r0001) ↔ `FUN_0031AA80` (r0004), 244 B both, `relinked-body`/`unique`; instruction for instruction the same walk over 0x3D8-byte records. Its *only* semantic difference is the token it `strcmp`s at record+0x338: 0x003F5DD8 `"r0001"` → 0x00421998 `"r0004"`. | both bodies disassembled; `match.json` row `0x002fd6e0` | high |
| **The Medius/Rtime middleware was rebuilt.** `rt_udp` 01.02.0048→**01.02.0053**, `rt_msg_client` 1.08.0204→**1.08.0210**, `rt_audio` 1.08.0009→**1.08.0012**, `rt_crypt` 1.01.0023→**1.01.0024**, `dme` 1.32.0070→**1.32.SJ84**; stamps `Oct  3 2003`/`Oct  9 2003` → `May 27 2004`; `$Header:` CVS revisions bumped (`rt_udp.c` version 1.59 → version 1.61.12.1, a branch revision). | strings at 0x00663760–0x00667CB8, 0x0064F968, 0x006547D0 | high |
| **…and rebuilt from a tree literally called `SOCOM2_PATCH`.** The `rt_crypt` build path in the retail image changes from `/public/work/dev/rt_crypt/src/{RSA,LargeInt}.c` to a developer home directory — `…/rprakash/SOCOM2_PATCH/rt_crypt/src/{RSA,LargeInt}.c` (the vendor's own path, baked into the shipped binary, not ours). | 0x00664FE0/0x006640A0 → 0x00665030/0x006640F0 | high |
| **One new Medius call: a game-liveness poll before joining.** `MediusGetGameInfo:cbIsGameAlive` (0x00420690) and `_1067_MEDIUS_DISCONNECTED_GAME_MSG` (0x004206B0), both r0004-only, both reached only by `FUN_0030C620`. `MP_MEDIUS_ERROR` referrers 13 → 19. | string-referrer scan over both images | high (strings); medium (purpose) |
| **The patch downloader is the same sceHTTP code, moved and roughly doubled.** All twelve `sceHTTP*` error strings are in both images, unchanged. The block moves 0x002CA340–0x002CC560 (r0001) → 0x002CD660–0x002CF210 (r0004); overlay referrers of `APACHE00.ZDB` 2 → 8, of `PATCHFILE.DAT` 2 → 5. New entry point `StartPatchDownload` (0x0041A700), reached only by `FUN_0027F2A0`, which also forms `APACHE00.ZDB`, `PATCHFILE.DAT` and `memcard_error_code`. | referrer scan; `Bad URI`/`Get %s`/`Cannot create patch archive` each move one-for-one | high |
| **The developer download error string is replaced by player-facing copy.** `Download Error: %s (%d)` (r0001 0x003F3030, 8 referrers) is **gone**; r0004 has `There was a problem downloading the update`, `Downloading {patch,update} information from server.`, `Please wait while you are connected to the {patch,update} server.` | string diff both ways | high |
| **No measurable anti-cheat change.** Zero occurrences of `checksum`/`Checksum`/`CRC`/`cheat`/`hack` in **either** image. `dnasCheck` is the same body (`relinked-body+string "DNAS_ERROR_CODE"`, 0x002CC670 → 0x002CF330); libdnas2 moved wholesale by +0x7AC0 with four of six entry points byte-identical; libnetb_ex's ten entry points **did not move at all**. | `socom2_addresses.h` r0004 column; string search | high for "nothing visible"; the absence of a string is not proof there is no new check — see §7 |
| `General Protection Fault` (r0001 0x003F2480, referenced by `FUN_002B9150` and `FUN_002BAF30`) is **removed**. | string diff | high (fact); unknown (why) |

## 3. UI and dialogs

| what | evidence | confidence |
|---|---|---|
| **Five new `.rdr` dialogs** (53 → 58; none removed): `dlgNetConnect.rdr` 0x00424ED0, `dlgGameLobby.rdr` 0x00424F00, `dlgWorldOfSOCOM.rdr` 0x0041D950, `dlgWorldOfSocom.rdr` 0x00425F10, `dlg_equipment_mp.rdr` 0x0041DBC0 and 0x00424F40. | `.rdr` string diff | high |
| **`dlgNetConnect.rdr` gains an `OnNetError` handler**, with the patch/update progress lines and `do_team_button_up`, all in one function `FUN_0038BD20` (r0004-only body, 11 strings, only 2 shared with its nearest r0001 relative). | 0x00424ED0/0x00424EE8/0x00424F20 referrers | high |
| **New failure dialogs and handlers**: `Game Join Error` 0x0041DB80 and `Game join error` 0x0041D770, `Team Switch Error! \| Continue` 0x0041DBE0, `OnRandomGameFailure` 0x00425F50, `Glswitchteams` 0x0041A0B8, `abort_join`/`join_game` 0x00418328/0x00418318, `create_game` 0x0041A728, `invite_player` 0x0041A188, `force_new_db` 0x0041A0A8, `GoneToArmory` 0x0041A718, `PLAYLISTVAR` 0x0041A738, `ConfirmationListVar` 0x00419F60. | referrer scan, all r0004-only | high |
| **A support phone number was added to the error screen**: `Please write down the error code number, and contact SCEA at 1-866-466-5333 or via SCEA's website, www.us.playstation.com.` 0x0041E988. | string diff | high |
| **The scoreboard column head changed from `SCORE:` to `RATING:`** — same function, `FUN_002F0020` (r0001, 0x003F4CE8) ↔ `FUN_0030D160` (r0004, 0x00420898), which share 43 of their 44 strings. `Unaffiliated` (0x003F4298, clan label, two referrers) is **removed**. | string diff + per-function string-set pairing | high |
| **Three new on-screen-keyboard contexts and two chat field names**: `ChatSkb2`/`PlayerChatSkb2`/`ClanSkb2` 0x00426C88/98/A8 (all in `FUN_003AD570`), `CHATTEXT`/`CHATMESSAGE` 0x00427798/0x004277A8 (`FUN_003BA150`), `MPPLAYERNAME`/`MPPLAYERNAME2` 0x00427470/80 (`FUN_003B6840`). | referrer scan, all r0004-only | high |
| **One new UI class: `MCPopMessage`**, derived from `CPlainBmp`, 26-slot vtable @0x00433808, descriptor @0x004248D0 — a memory-card popup. | class descriptor record read out of the image | high |

## 4. Gameplay objects and rules

| what | evidence | confidence |
|---|---|---|
| **The actor gained a word at `+0x1334`**, pushing every field above it up by four (MoveScale `+0x1368`→`+0x136c`). | `task-19-move-report.md`: 6↔6 use sites, 146 of 149 displacements agree in the twin | high (established) |
| **What that word is for**: r0004 has **12** access sites at `+0x1334` (r0001 has one, an unrelated `sh` in `FUN_00581430`). Seven are `sw $zero` resets; the writer `FUN_005B8920` stores **0x96 (150)** at 0x005B8F58/0x005B8F98 in the same breath as `+0x1328=1`, `+0x132C`, `+0x1330=1`, `+0x1331`; four readers (`FUN_00583490` 0x005835F0, `FUN_0058A100` 0x0058A140, `FUN_00599B40` 0x00599C8C, `FUN_00599CD0` 0x00599DA0) all do `lw $v0,0x1334(obj); blez $v0, <normal>` and take a **refuse/zero-return** path while it is positive. **Every one of the twelve sits behind the same global byte** (r0004 0x0045D481 / r0001 0x0045A281, the pairing unanimous across 183 twinned read sites). | scan of both images for displacement 0x1334; disassembly of all twelve | high for the shape; **unknown** for the name — see §7 |
| **Six `CIO`-family classes each gained one virtual, at vptr+0x1C**, shifting every slot from there up by four. `CFileIO` 0x00408188→0x00434AB8, `CBufferIO` 0x00408138→0x00434A68, `CRdrIO` 0x00406A58→0x004332E8, `CSoundBufferIO` 0x00406B08→0x004333A8 all inherit the base body `0x0034CC50` (`jr $ra; lw $v0,0x10($a0)`); `CLobbyFileIO` 0x00406768→0x00432FF8 overrides with `0x002CB590` (`return 0`); `CMemCardIO` 0x004081F8→0x00434B28 overrides with `0x003C0400` (`return 8`). | all 254 vtable runs on each side paired by their class-descriptor name string; alignment through `match.json` | high |
| That shift **is** the `+0x20→+0x24` / `+0x24→+0x28` seen in `packTrace` and in the three `CButtonSpec::Clone` call sites. | `task-19-node-report.md` §4b and §A.3 | high |
| **One new `CIO` subclass: `CZArchive`** — descriptor @0x00427F38 (parent `CIO`), 16-slot vtable @0x00434B88, 21 new functions at 0x003C79F0–0x003C9270 (6,304 B) reaching `.ZDB`, `.CDB`, `BASCUS-97275`, `RUN/`, `1.1.4`, `dlgNetError.rdr`. `*.zdb` became `*.ZDB`. This is the reader for the downloaded package on the card. | class descriptor + vtable + per-function string sets | high |
| **The multiplayer game-state block was rewritten**: r0001 0x002A6AD0–0x002A7D40 (15 functions, 5,644 B) ↔ r0004 0x002A7FD0–0x002A94F0 (16 functions, 6,388 B); **all 46 of its strings exist in r0001** (`mp_team_unbalance`, `mp_teams_too_big`, `mp_penalty`, `late_joiner`, `mp_spectator`, `BSPECLISTVAR`, `mp_half_rounds`, …) — same vocabulary, new code. | unmatched-run scan + per-block string sets | high (it changed); unknown (what rule) |
| **New weapon/ammo and equipment names**: `C4 Ammo` 0x00418310 and `MPBOMB Ammo` 0x004182E8 (with `damage_point`, in `FUN_0025D2F0`), the option label `NO BOMBS` 0x0041F750, `SetMPCharWeaponValves` 0x0041D0A0, `set_respawn_valve` 0x004251A0. `Enable_203*/F2000*/GL*` grenade valves and the `VOTE …` strings exist in **both**. | string diff + referrers | high |
| 19 new functions at 0x002CB960–0x002CCB10 carrying `:: Player "%s" is unavailable` (a string r0001 also has). | unmatched-run scan | medium |

## 5. Maps and assets — the largest single change in r0004

| what | evidence | confidence |
|---|---|---|
| **21 map-id strings exist in r0004 and in no form in r0001**: `mp1 mp2 mp5 mp6 mp7 mp8 mp9 mp10 mp11 mp12 mp51 mp52 mp61 mp62 mp64 mp71 mp72 mp73 mp81 mp82 mp83`, packed at 0x0041EC08–0x0041ECB8. | string diff both ways (0 in r0001, 21 in r0004) | high |
| **A contiguous block of 111 new functions, 0x002D1450–0x002EB270, 106,568 bytes** — 58 % of FTSCore's entire growth — with no matched neighbour anywhere inside it, bracketed by matched functions on both ends (0x002EB710 ↔ r0001 0x002CE800). | `match.json` + the r0004 CSV; every one of the 111 passes a MIPS-prologue/`jr $ra` check | high |
| **What it does**: `FUN_002D4C20` fetches the current level name, then `strcmp`s it (via `FUN_00199A10`) against the 21 map ids in turn and calls a per-map routine — `mp11`→`FUN_002D98F0`, `mp10`→`FUN_002E5D80`, `mp12`→`FUN_002D8D60`, `mp1`→`FUN_002DCDC0` (only when a mode word `$s0 == 3`), `mp51`→`FUN_002D5CB0` + four more, and so on. | disassembled 0x002D4C20–0x002D4F20 | high |
| **What the per-map routines name**: 55 individual pieces of level geometry, at 0x0041EC70–0x0041EFE0, **76 of the block's 93 strings being r0004-only** — `di_roof22`, `di_wall_wc09`, `ground_wc06/14`, `ballroom_wall`, `garage_wall`, `wall_breaker`, `hall_down`, `climber1`, `walkable_terrain_2314`, `invis25`, `invis29`, `di_perimeter`, `door_outhouse1/2`, `alaska4d_outhouse_door`, `congo_tree1`, `congo2_tree3`, `crate_bananas_stacked4`, `basket_open_up`, `sandbag_turret`, `wood_barrel`, `land18/43/49/58/59`, `wc06/11/12/12A/12C/13/22A/24`, `crates01.tif`… | referrer scan over 0x0041EC08–0x0041EFE8 (93 r0004 functions reach it) | high |
| **Read as intent**: a per-map, per-object table of geometry the patch reaches in and alters. The object names are walls, terrain, doors, crates, invisible collision (`invis25`, `walkable_terrain_2314`, `wall_breaker`, `climber1`) — the vocabulary of out-of-bounds and wall-clip fixes, which is what the public record says the March 2004 update was for (§6). | the names themselves | **medium** — no name in the image says "exploit"; this reading rests on the vocabulary plus §6 |
| **No HDD map names** (`After Hours`, `Last Bastion`, `Liberation`) appear in either image, and no `hdd` string count changed (3 in both). | string search | high |

## 6. The community record — attributed, and separate from the images

Not evidence about the images; the public claims, for cross-reference only.

- **PSRewired's own guide**: "SOCOM II r0004 contains support for 3 additional maps for online play via the
  HDD"; the update is downloaded on first connect; "the version for socom will say 'r0001' at the bottom of
  the main menu … once you go online and download the update it will change to 'r0004'."
  ([psrewired.com/guides/socom2](https://psrewired.com/guides/socom2))
- **Slashdot, 11 March 2004**: SCEA and Zipper began a mandatory memory-card update on 10 March 2004 that
  "incorporated a number of online tweaks and fixed many exploits used by players"; the article states
  there was **no official changelog**, only "a list of perceived changes on the official SOCOM II boards."
  ([games.slashdot.org](https://games.slashdot.org/story/04/03/11/0033252/sonys-socom-ii-gets-cheat-patches))
- The image we hold is stamped **Nov 3 2004**, eight months after that March update — so the March 2004
  patch is very likely an *earlier* revision than this one, and "r0004 = the March exploit patch" is an
  assumption, not something the banner supports.
- No official Zipper/SCEA changelog for r0004 was found; `socomlan.com/SOCOM2PatchNotes.php` (a community
  patch-notes page) could not be fetched — its TLS certificate has expired.

**Where the record and the images agree**: exploit fixes (the §5 block) and an enlarged download path.
**Where they do not**: the images contain no HDD-map support that r0001 lacks, and no new map names — so
the "3 additional maps" claim is not visible in the executable and must live in the package's data.

## 7. Infrastructure and build

| what | evidence | confidence |
|---|---|---|
| **FTSCore runs 126 static constructors to r0001's 125**; the inserted entry is index 57 = 0x0042E3D0. ZSealEtc's 16 are unchanged. | ctor-table runs 0x00404D10/0x004315A0, bounds from `socom2_addresses.h` | high (count); medium (which entry) |
| **Why ZSealEtc shrank: three function runs moved out of it into FTSCore**, byte counts matching exactly — 30 fns/4,788 B (r0001 0x00645710 → r0004 0x003F7AE8), 24 fns/4,028 B (0x00648678 → 0x003FAA50), ~20 fns/2,908 B (0x0064A918 → 0x003FCCF0). The `../../SaseEncVad/source/{CalcCost,EncSC,libquan}.c` paths move with them. | unmatched-run scan on both sides; identical byte totals | high (the move); medium (that it is all of SaseEncVad) |
| **r0004 carries an embedded IOP module that r0001 does not**: an IRX ELF (`e_type` 0xFF80) at 0x00654880, ~1,260 B, named **`rt_ac`**, importing `sysmem`/`modload`/`thbase`. `.iopmod`, `modload`, `sysmem`, `thbase`, `rt_ac` occur in r0004 and nowhere in r0001. | ELF magic + section-name strings at 0x0065490E–0x00654B84 | high (it is there); unknown (whether it is ever loaded) |
| Title casing: `SOCOM II: U.S. Navy SEALS` → `SOCOM II: U.S. NAVY SEALs` (0x003FBCA0 → 0x00427C00); `BASCUS-97275` and `RUN/` appear for the first time. | string diff | high |

## 8. What this means for the port

**Absorbed for free by recompiling the r0004 image** — because every byte that changed is in the two
overlays, and the loader below 0x001D5600 is identical:

- the 111-function map-fixup block and everything it calls;
- the enlarged patch-download path, `CZArchive`, `MCPopMessage`, the rewritten MP state block;
- the new actor word at `+0x1334` and its guard, the new `CIO` virtual and the vtable shift, the five new
  dialogs, the `RATING:` scoreboard, the bumped middleware.

**Needs the runtime to follow, one row at a time** — anything of ours that writes down an r0001 number:

- `socom2_addresses.h`'s r0004 column (done, Task 19) and `tools_py/parity/guest_addresses.py`'s
  per-revision *displacements* (done: actor MoveScale `+0x1368`→`+0x136c`). The rule from §4 is that a
  **vtable slot index is per revision too**: `CIO`-derived objects shift from vptr+0x1C up by four. Task
  19 §A.1/A.3 already checked every installed override against this and found only `packTrace` and
  `defer` affected, both trace-only. That audit must be re-run whenever a new override is bound.
- **Untested surface**: the r0004 build has only ever run on the r0001 disc's assets. The §5 block runs
  per map, and nothing has exercised it. `CZArchive` reads `BASCUS-97275` and `RUN/` off the card — our
  memory-card HLE has never been asked for those paths. The `rt_ac` IRX is unknown territory: if the game
  `modload`s it, the IOP side must answer, and nothing in the runtime mentions it.
- The sceHTTP downloader has **no** HLE in `ps2xRuntime` (`grep sceHTTP` → nothing). It is bigger in r0004
  and it is the path that produces `APACHE00.ZDB`.

**Goal F's, i.e. server-side and the owner's Discord answer:**

- the join filter now compares `"r0004"` (§2) — a hosted lobby's game records have to advertise the
  revision the client is running, and PSRewired's capsule leaves its players on `r0001`;
- `MediusGetGameInfo:cbIsGameAlive` — a new Medius request the server must answer;
- the patch/update server itself (`StartPatchDownload`, `PATCHFILE.DAT`, `APACHE00.ZDB`);
- the capsule's r0004-layout stub table at 0x002CF330, which our image never received (already open in
  `docs/KNOWN.md` §2).

## 9. What this note could not determine

1. **What the actor's new `+0x1334` word means.** The shape is nailed down (set to 150, four readers
   refuse while it is > 0, seven reset sites, all behind one global). **No decrement site exists** at that
   displacement anywhere in r0004, so whether it is a countdown ticked elsewhere through a pointer, or a
   stamp compared against something, is unresolved — and the global that gates it (0x0045D481 / r0001
   0x0045A281) is read at 292 sites in r0004 and **written at none**, so its name is unknown too.
2. **Which individual functions are genuinely new versus recompiled.** The honest counts are the ones in
   §1. A masked-body test says ~2,100 r0004 and ~1,900 r0001 bodies have no byte-equal counterpart, but a
   13-month rebuild changes bodies for reasons that are not features, so that number does **not** mean
   "2,100 new functions". Only the contiguous, string-anchored blocks in §4 and §5 are safe to call new.
3. **Whether r0004 adds anti-cheat.** Nothing in the strings or in the DNAS/crypto entry points shows it,
   but a check that costs no string would not appear in this method.
4. **The three HDD maps.** Publicly attributed to r0004, invisible in the executable; whatever supports
   them is in the package's data, which we have never read.
