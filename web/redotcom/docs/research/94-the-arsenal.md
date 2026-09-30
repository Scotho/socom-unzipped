# 94 -- The arsenal: every weapon, each side's own, and the weapon select (web sprint 4, M1)

Written 2026-09-30 for web sprint 4 (spec `web/redotcom/docs/specs/2026-09-30-web-sprint-4-arsenal-design.md`, rulings
W4.R1-R8; plan `../plans/2026-09-30-web-sprint-4-arsenal.md`, task M1). Read-only research by three readers in parallel,
merged by the sprint's main agent: part 1 the arsenal and its rules (the scope table, the id-to-valve map, the mask, each
map's per-side lists and kits, the slot rules, a pick's way to the body, 2X), part 2 the in-game weapon select (the menu
the game actually runs, its states, layout, input and timing), part 3 the per-class behaviour (every rare key of
`zweapon.rdr` from the parser outward, the shotguns, bolts, launchers, explosives, thermal scope, holsters, the HUD box).
Sources: the retail decompilation `analysis/socom2_game.elf.decomp.c` (`Lnnn` = its line; every address **retail**), the
retail ELF `analysis/elf/socom2_game.elf` (`.data`/`.rodata` read by virtual address through its `PT_LOAD` headers; the
file has no section table), our recompilation `recomp/retail/output` and `recomp/r0004/output` (r0004 files mapped
through `recomp/retail-to-r0004.tsv`), the SOCOM 1 demo's DWARF (`analysis/demo/SCUS_972.05`, dumped with ccc
`stdump` at c025ca9), reCOM `recom/`, and the disc (`disc/RUN/...`) read with the repository's own `@s2u/archive` and
`@s2u/scene` readers. Paths are relative to the handoff archive's root (`socom-web-sprint-4-arsenal/`); the probes the
readers ran lived outside the repository and are named in each part (no game bytes in git: names, ids and numbers
only). Each part keeps its own section letters (A, B, C) so the later tasks can cite `research 94 §A5.2`, `§B4`, `§C2.1`.

## 0. What M1 changed, and the rulings the later tasks build on

The readers overturned three of the prep's assumptions; the rest of the plan stands. Each line below is the main agent's
ruling for M2-M9, with the part that proves it.

| # | finding | ruling for the build | part |
|---|---|---|---|
| R94.1 | **`CInGameWeaponSel` is dead code in SOCOM II** (its vtable overrides only the destructor, its tick is an empty `jr ra`, its textures are not on the disc). The dead player's menu is the unnamed HUD block at `CHUD+0x38e0`, titled **"WEAPON EXCHANGE"**, built from `SlotList` / `CWeaponSlot` / `SelectedSlot` / `CategorySlot` (Init `FUN_00240e60` L89585, tick `FUN_00240600` L89343) | M8 builds WEAPON EXCHANGE, state for state (§B4's S0-S8); `weaponSelect.ts` keeps its planned name | §B0, §B1 |
| R94.2 | The menu exists **online only**, opens only while **dead** (or a late-joining ghost) on the **`Inventory`** button (R2; the prompt's `%c` is 0xbe, 0xbd for the "Goldeneye" config's R1), never before the round or at a spawn; alive, the same button opens the in-hand inventory `CWeaponSel` | the viewer's match -- offline through the page's own `Room` (loopback) or on a server -- is the online classic match, so the menu opens there when dead; `&nomatch` (the free walk) has no menu. The pad opens it on R2; the PC key and touch control are `WEAPON_SELECT_KEY_READING` (proposed `I`, after the game's `Inventory`) and `WEAPON_SELECT_TOUCH_READING`, for the owner (O-S4-3) | §B2, §B3 |
| R94.3 | A pick is written to the player's character-type kit on confirm and **applied at the next round's rebuild** (classic); the menu plays **no sound**, draws no description or stats, and offers no character type | M8/M9: the `loadout` is stored on confirm and applied at the next round's spawn; the menu is silent; `DEFAULT_CHARTYPE_PLACEHOLDER` stays | §B4 S4/S8, §B6 |
| R94.4 | The side filter is `FUN_0023c390` (L87356-87487): an item is listed when its valve's mask has **1 (SEAL) / 8 (Terrorist)** for the player's side, its class fits the slot, and it is no refused duplicate. The launcher-ammo refill helpers `FUN_0023b9b0`/`FUN_0023bc50` test the side the other way round (`player_team == 0 -> 8`, confirmed in the MIPS at 0x23bbdc) | W4.R2 follows the filter: each side only ever gets its own items; the refills use the player's own side (`INGAME_AUTOFILL_SIDE_READING`, reading (b)), recorded as a divergence for the owner | §A3, §A5.2, §B6 |
| R94.5 | The mask's **16 / 32 bits lock C4 in a SEAL's / a Terrorist's kit** (`FUN_0023e910` L88527); `Enable_c4` = 16 on the BREACH maps MP61, MP62, MP73: the SEALs spawn with C4 they cannot swap, and nobody may pick it. MP81's `Enable_C4` (capital) is no valve the code reads: C4 is off there | M2's arsenal carries per-slot locks; the server refuses a change to a locked slot | §A3, §A4 |
| R94.6 | A record's class is its **id range** (`FUN_003d1a60` L324331), not a key; the LAW and RPG-7 are **equipment** (SlotCost 2: they take a second equipment slot holding their round) | M2 classes records by id range; M7 treats the rockets as equipment | §A0, §A5.4, §C1.7 |
| R94.7 | The default kits are **not** checked against the valves: MP6 SEAL 4 and MP7 SEAL 2 spawn with the Terrorist-only 226 | the spawn kit is the type's `default_weapons` as the game gives it; only a *pick* is validated | §A4 |
| R94.8 | **Launcher rounds are fire modes of their carrier** (a slot mode > 3 is the id of a round held in another kit slot; L3 cycles the rifle's modes, then each round type held); the M203 rifles fire from `firepoint_203` and the player's rounds are auto-lofted onto the aimed point | M4/M7: the fire-mode switch cycles into the rounds; the launcher is no separate item in the hand | §C4 |
| R94.9 | **Bullets ignore `Muzzle_Velocity`**: a ray of `Maximum_Range` x 1.1, no drop. Grenades and launcher rounds fall at 98 u/s^2; rockets accelerate at 980 u/s^2 and do not fall | M4 keeps the hitscan round; M7's projectiles take the two laws | §C1.12 |
| R94.10 | The shotguns fire **4 cone rays a pull** (`NumProjectilesFired 4`), one shell; the victim's side re-counts pellets by range; one hit per victim per volley | M4's shotgun class | §C2.1 |
| R94.11 | **C4 is timed, not remote**: planted on a C4 target object only, 6 s fuse; the Detonator comes only with a claymore and sets off only claymores. The PMN arms after 8 s and triggers within 1 m | M7 builds C4 as a timed charge on the map's C4 targets (`C4_TARGET_READING`), the claymore with its detonator | §C5 |
| R94.12 | The 870's pump key is misspelt on the disc (`ReloadAfterShotDelay`), so its lock is the parser's default 0.01 s; `TracerTextureName` and `Encumbrance` have no reader; `Sound_Radius` only feeds the bots' hearing | reproduced as the game runs: 0.01 s, no tracer texture, no encumbrance on the mover, `Sound_Radius` unused (no bots) | §C1, §C2.2 |
| R94.13 | 2X doubles `NumMags` (cap 10) for pistol-sniper classes, the extra magazines full; launchers, rockets and throwables are not doubled | M4/M7 | §A7 |
| R94.14 | `SendWeaponPUMessage` (0x2ba660) is the **pick-up of a dropped weapon**, not the loadout; the kit rides in the 0x90-byte character message (up to 8 x {id and round, rounds, magazines}); how the confirmed pick reaches the others is not traced | M9's `loadout` message is the viewer's own (`PICK_WIRE_READING`); the body's kit on the wire mirrors the character message's entries | §A6, §B6 |
| R94.15 | The thermal scope is equipment with no model: selectable only beside a sniper rifle; it swaps the sniper's `scope` node for `thermal_scope` and plays the thermal lens effect in the scoped views; zoom unchanged | M5/M7 | §C7 |
| R94.16 | Research 84 §9 is corrected: the grey reticle (130,130,130) marks an aimed point **inside** a launcher round's arming distance (10 m), not past its range | M5 draws it so; research 84 keeps a pointer here | §C1.5 |
| R94.17 | The demo DWARF has 31 functions of `CInGameWeaponSel`, not the 56 the prep quoted (research 55 agrees) | none (the class is dead) | §B1.1 |

**The placeholder ledger.** Each part's "Placeholders" section lists its readings; a name the code does not hold yet is
marked *note only* until the task that builds it names it in the source. One name is merged: part 2's
`PLAYER_TEAM_MASK_READING` is the same question as part 1's `INGAME_AUTOFILL_SIDE_READING` and was replaced by it.

**What no frame shows.** No console frame exists of WEAPON EXCHANGE, the armory, any scope but the M4A1 SD's, or any
weapon but the M4A1 in hand (spec §8 O-S4-2): part 2's layout is read from the code alone.

## 1. The arsenal and its rules (reader a)

Written 2026-09-30, read-only research for web sprint 4 (spec `web/redotcom/docs/specs/2026-09-30-web-sprint-4-arsenal-design.md`,
rulings W4.R1, W4.R2, W4.R5, W4.R6). Paths under `analysis/`, `recom/`, `recomp/`, `disc/` are relative to the handoff
archive root (`socom-web-sprint-4-arsenal/`). `Lnnn` = a line of `analysis/socom2_game.elf.decomp.c`; every address is
**retail** (the r0004 twin, where `recomp/retail-to-r0004.tsv` has one, is given once in A6). Strings and `.data` were
read from `analysis/elf/socom2_game.elf` by virtual address through its four `PT_LOAD` program headers (the file has no
section table) with `probe/elfread.py str|word|float <addr>`. Disc values come from the probes below, run
with the repository's own `@s2u/archive` readers (`parseZdb`, `zdbMember`, `Zar`, `parseRdr`, `rdrGet`) from
`web/redotcom` with `npx tsx`. No game bytes are quoted: names, ids and numbers only.

Probes (all under `probe/`):

| file | what | output |
|---|---|---|
| `elfread.py` | reads a C string / words / floats at a retail virtual address | stdout |
| `arsenal.ts` | every `ZWEAPON` record; each MP map's `mission.rdr` `Valves`; per map and side the selectable ids through `FUN_003cf1f0`'s table (A2) and `FUN_003d1a60`'s classes (A5); each map's 4+4 `chartype.rdr` types resolved through `character.rdr`'s inheritance to `default_weapons` | `arsenal-out.txt` |
| `scope.py` | the scope table (A1) and the per-map selectable table (A4) from `arsenal-out.txt` | `scope-out.md` |
| `kits.py` | the per-map kit table (A4) | `kits-out.md` |
| `cmp91.py` | compares research 91 section 14's 176 kits with `arsenal-out.txt` | stdout: `diffs 0` |
| `uidlg.ts` | which names the front-end armory's `RUN/UI/READERC.ZAR` `dlg_equipment_mp.rdr` references | stdout |
| `peek.ts` | first look at `mission.rdr` / `chartype.rdr` / `character.rdr` / `valves.rdr` shapes | stdout |

Vocabulary. **Item id** = a `ZWEAPON` record's `ID`, held as a byte at record `+0x7c` (parser `FUN_003cda30` L322435:
`*(char *)(rec + 0x7c) = ID`); `EQUIP_ITEM` in the demo's names. **Valve** = a named `ushort` in the global valve list
(list head `0x49e804`/`0x49e808`, pool `0x49e820`; value at valve `+4`). **Kit vector** = a character type's list of
12-byte `CCharacterWeap` entries at type `+0x2e8` (count `+0x2ec`, data `+0x2f0`): `+0` item id, `+1` round (ZAMMO) id,
`+4` rounds a magazine, `+8` magazines (A6). **Menu object** = the in-game select's object with five slot records at
`+0x11b0 + 0xb8 x slot` (slot 0 primary, 1 secondary, 2-4 equipment), the edited slot at `+0x1194`, the saved ids
`+0x1530/+0x1531` and the launcher flags `+0x1532` (M203/MGL), `+0x1533` (F2000), `+0x1534` (M79); its layout is
reader (b)'s. **Side** = team id 0 SEALs, 8 Terrorists (research 91 vocabulary; `FUN_002c3330` L164814 writes it into
the `player_team` valve, A3).

### A0. Answers in one table

| question | answer | source |
|---|---|---|
| records | 86 `ZWEAPON` (ids 4-255) and 39 `ZAMMO`; **63 in scope**: 60 enabled through a valve on some MP map for some side or carried in an MP kit, plus 3 that only ever arrive as dependents (M203 141 with an M203 rifle, LAW HEAT 185 with the LAW, Detonator 193 with a placed claymore); 23 out | `arsenal-out.txt`; A1 |
| class of a record | **by its id range**, not a key: `FUN_003d1a60` (L324331): 4-30 pistol, 31-50 SMG, 51-80 rifle, 81-90 shotgun, 91-100 MG, 101-120 sniper, 121-140 grenade, 141-144 grenade launcher, 145-150 rocket launcher, 151-170 explosive, 171-184 launcher round, 185-189 rocket round, 190-200 gear, 201-204 armour, 205-229 / 230-253 turrets, else 0xfe | L324336-324352 |
| slot class | primary = SMG, rifle, shotgun, MG, sniper, grenade launcher (`FUN_003d1d10` L324404); secondary = pistol (`FUN_003d1ce0` L324392); equipment = everything else, **including the LAW and RPG-7** (`FUN_0023c390` L87375-87378 excludes only primary and pistol from an equipment slot) | L324411, L324398, L87369-87389 |
| id -> valve | `FUN_003cf1f0` (L322760-322968): 68 cases, 67 names (RPG launcher 146 and RPG round 186 share `Enable_RPG`); no valve for 11 Designator, 93 .PKM, 128 chem light, 141 M203, 185 LAW HEAT, 190, 193, 201, 202, the internals; two dead cases (124 `Enable_phos`, 172 `Enable_203ILL`: no such record, no such map valve) | A2 |
| valve lookup | `FUN_00351ef0` (L250997): walks the valve list, `strcmp` (`FUN_00198f18` L15767, byte-exact, **case-sensitive**); not found -> NULL | L251006-251014 |
| missing valve | NULL -> mask 0 -> **not selectable** (`FUN_0023c390` L87468-87478), not auto-picked (L87164-87176), not locked (`FUN_0023e910` L88529-88539; armory `FUN_00281950` L128090) | A2 |
| quirks on the disc | `Enablesig_commando` is the code's own spelling (matches every map); MP81 has `Enable_C4` not `Enable_c4` -> C4 unselectable and unlockable there; `Enable_RPG_ammo` (21 maps) / `Enable_RPG_Ammo` (MP73) / `Enable_blue_chem` (MP1) are read by nothing; `Spas 12` is not an MP valve (all 22 say `Enable_spas`) | A2 |
| mask bits | 1 = selectable by SEALs, 8 = by Terrorists (in-game `FUN_0023c390` L87468-87476: `mask = is-Terrorist ? 8 : 1`, `FUN_002c30b0` L164664); **16 = locked in a SEAL's kit, 32 = locked in a Terrorist's** (in-game `FUN_0023e910` L88527-88545, `Enable_c4` only); the armory locks on `0x30` for any item's valve (`FUN_00281950` L128090, `FUN_002815d0` L128006) | A3 |
| 16 on the disc | `Enable_c4` = 16 on MP61 Sujo, MP62 Enowapi, MP73 Sandstorm (the BREACH maps): every SEAL type carries C4 in kit slot 4 and cannot remove it; nobody can pick C4 there (bits 1 and 8 clear) | A3, A4 |
| launcher rounds | the round valves are **rewritten by the menu**: on opening (`FUN_00240e60` L89585) and on each pick (`FUN_0023fef0` L89138 / `FUN_0023eca0` L88610) the M203/MGL, M79 and F2000 round valves become 9 when the primary carries that launcher, else 0; the map's own value only matters before the menu first opens | A3, A5 |
| per map per side | 22 maps: SEALs 28-35 items, Terrorists 27-37 (A4 table); Frostfire 29/28, Blizzard 34/30 (matches the prep) | `scope-out.md` |
| kits | 176 types (22 maps x 8) resolved through `character.rdr`; **identical to research 91 section 14** (`cmp91.py`: 0 diffs). Kits are not checked against the valves: MP6 SEAL 4 and MP7 SEAL 2 spawn with the 226 (Terrorist-only on those maps); BREACH SEALs spawn with the locked C4 | A4 |
| duplicates | in-game: 2X, thermal scope, PMN, claymore, LAW, RPG-7, LAW HEAT may sit in only one slot; grenades, C4, launcher rounds and the RPG round may repeat | `FUN_0023c390` L87444-87466 |
| SlotCost | 2 on LAW (145), RPG-7 (146), Satchel (152); default 1 (parser L322610-322614, record `+0x27c`). A cost-2 pick fills a second equipment slot with LAW HEAT 185 / RPG round 186 / FULL_SLOT 254 | `FUN_0023fef0` L89160-89200 |
| launcher side effects | an M203 rifle puts M203 (141, locked) in kit slot 2 and M203 FRAG (175) in slot 3; M79 -> GL FRAG (179) in slot 2; MGL -> M203 FRAG (175) in slot 2; F2000 -> F2000 FRAG (183) in slot 2; the displaced ids are kept in `+0x1530/+0x1531` and restored when the launcher goes | `FUN_0023fef0` L89200-89320; `FUN_0023eca0` L88610-89136 |
| thermal scope | selectable only while a sniper rifle sits in another slot; dropping the sniper replaces it (in-game); armory: only with a sniper primary | L87400-87414; L88823-88840; `FUN_00280e90` L127740-127748 (A5) |
| locked slots (armory) | `UIDoAllSelCharsHaveLockedEquip1/2/3` = `j FUN_002815d0` with 0/1/2 (kit slots 2/3/4); a slot is locked if it holds M203 141, LAW HEAT 185, FULL_SLOT 254, an RPG round with no second one, or an item whose valve has 16 or 32 | recomp `UIDoAllSelCharsHaveLockedEquip*_0x28103*.cpp`; L128000-128010 |
| default equipment | `UIChooseDefaultEquipmentOnly` (`FUN_00281be0` L128148): keeps the chosen primary and secondary, resets the kit to the type's `default_weapons`, re-applies the two | L128170-128192 |
| pick -> body | in-game confirm: `FUN_0023fef0(slot, record)` then `FUN_0023e5e0` (L88381) writes the five ids into the player's type kit vector with `CCharacterWeap_SetupCharacterWeapon` (0x53eee0, L407443); the next spawn's `CZSealBody_PostCreateSeal` (0x599f00, L455790-455836) fills `CZKit` (+0x5e0) from it; `FUN_005c7840` (L480332) finalises (armour, 2X, C4) | A6 |
| online | the kit rides in the 0x90-byte character message (`FUN_002bd640` L161852; kit by `FUN_0053ed50` L407397: up to 8 x {u16 `id<<8 | round`, u16 rounds, u16 mags}); unpacked by `FUN_0053ec60` (L407354). `SendWeaponPUMessage` (0x2ba660) is **the weapon pick-UP** (a dropped gun), not the loadout | A6 |
| 2X AMMO | if the kit holds id 194, every firearm of class pistol/SMG/rifle/shotgun/MG/sniper gets `NumMags x 2` magazines (capped at 10), the extra ones full; grenade launchers, rockets and throwables are not doubled; `Ammo_Capacity` unchanged | `FUN_005c75f0` L480207-480270; `FUN_005ba3d0` L472725-472745; `FUN_005ba5b0` L472803-472812 |
| surprise | the in-game auto-fill helpers `FUN_0023b9b0`/`FUN_0023bc50` test `player_team == 0 -> mask 8` -- the inverse of the armory's `FUN_00283b50`/`FUN_00283e60` and of what `FUN_002c3330` writes (0 = SEALs). Verified in the MIPS (`movz $a0,$v1,$s2`, 0x23bbdc) | A5; `INGAME_AUTOFILL_SIDE_READING` |

### A1. The scope table

Every `ZWEAPON` record, sorted by id (`arsenal-out.txt`, `scope-out.md`). **class** = `FUN_003d1a60`'s class head;
**slot** = the slot kind the in-game menu gives it (A5; `rocket` = a rocket launcher, chosen in an equipment slot);
**valve** = `FUN_003cf1f0`'s name; **SEAL / Terrorist maps** = the MP maps (numbers) whose `Valves` give that side's bit
(`all 22` or a list); **in a kit** = sides whose character types carry it in `default_weapons` (and how many of the 176
types). **scope** IN = enabled for some side on some MP map or in some MP kit.

| ID | InternalName | DisplayName | class (FUN_003d1a60) | slot | ModelName | AMMO_TYPES | valve (FUN_003cf1f0) | SEAL maps | Terrorist maps | in a kit | scope |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4 | F57 | F57 | pistol | secondary | fiveseven | 5.7 x 28mm | Enable_fiveseven | - | all 22 | T (19 types) | IN |
| 5 | M9 | M9 | pistol | secondary | baretta_m9 | 9x19P | Enable_beretta_m9 | - | all 22 | T (22 types) | IN |
| 6 | 226 | 226 | pistol | secondary | sig226 | 9x19P | Enable_Sig226 | 62 | all 22 | S (2 types) | IN |
| 7 | DE .50 | DE .50 | pistol | secondary | desert_eagle | 50 AE | Enable_desert_eagle | - | all 22 | T (19 types) | IN |
| 8 | 9mm Pistol | 9mm Pistol | pistol | secondary | hkp9s | 9x19P | Enable_HkP9s | all 22 | - | - | IN |
| 11 | Designator | Designator | pistol | secondary | laser_designator | - | - | - | - | - | OUT |
| 12 | P228 | M11 | pistol | secondary | M11_p228 | 9x19P | Enable_P228 | all 22 | - | S (6 types) | IN |
| 13 | SR-1 Gyurza | SP-10 | pistol | secondary | sig226 | 9x21mm | Enable_SR1_Gyurza | all 22 | - | S (3 types) | IN |
| 14 | Model 18 | Model 18 | pistol | secondary | glock18 | 9x19P | Enable_glock18 | - | all 22 | T (19 types) | IN |
| 15 | Mark 23 | Mark 23 | pistol | secondary | a_mark23 | 45 ACP | Enable_Mark23 | all 22 | - | S (22 types) | IN |
| 16 | Mark 23SD | Mark 23SD | pistol | secondary | a_mark23sd | 45 ACP | Enable_mark23sd | all 22 | - | - | IN |
| 31 | HK5 | HK5 | SMG | primary | mp5 | 9x19P | Enable_mp5 | all 22 | - | S (19 types) | IN |
| 33 | HK5SD | HK5SD | SMG | primary | mp5sd | 9x19P | Enable_mp5sd | all 22 | - | - | IN |
| 34 | F90 | F90 | SMG | primary | fnp90 | 5.7 x 28mm | Enable_FNP | - | all 22 | T (22 types) | IN |
| 37 | 9mm Sub | 9mm Sub | SMG | primary | uzi | 9x19P | Enable_uzi | - | all 22 | - | IN |
| 38 | MP5K | HK5K | SMG | primary | hk5k | 9x19P | Enable_MP5K | all 22 | - | S (3 types) | IN |
| 51 | M16A2 | M16A2 | rifle | primary | m16a2 | 5.56 x 45mm | Enable_M16 | all 22 | all 22 | - | IN |
| 52 | M16A2-M203 | M16A2-M203 | rifle | primary | m16_M203 | 5.56 x 45mm | Enable_M16203 | 1 5 10 12 52 53 64 72 82 83 | - | - | IN |
| 54 | M4A1 | M4A1 | rifle | primary | m4Acarbine | 5.56 x 45mm | Enable_m4Acarbine | all 22 | - | S (22 types) | IN |
| 57 | 552 | 552 | rifle | primary | sig_commando | 5.56 x 45mm | Enablesig_commando | - | all 22 | T (21 types) | IN |
| 58 | AK-47 | AK-47 | rifle | primary | ak47 | 7.62 x 39mm M1943 | Enable_ak47 | - | all 22 | T (3 types) | IN |
| 59 | AKS-74 | AKS-74 | rifle | primary | aks74 | 5.45 x 39mm Soviet | Enable_aks74 | - | all 22 | - | IN |
| 60 | M14 | M14 | rifle | primary | m14_gun | 7.62 x 51mm | Enable_m14_gun | all 22 | all 22 | - | IN |
| 61 | M4A1-M203 | M4A1-M203 | rifle | primary | m4Acarbine_203 | 5.56 x 45mm | Enable_m4Acarbine_203 | 1 5 10 12 52 53 64 72 82 83 | - | - | IN |
| 62 | M4A1 SD | M4A1 SD | rifle | primary | m4Acarbine_sd | 5.56 x 45mm | Enable_M4A1_SD | all 22 | - | - | IN |
| 63 | F2000 | OICW | rifle | primary | BMMG_f2k | 5.56 x 45mm | Enable_F2000 | - | - | - | OUT |
| 64 | SA-80 A2 | IW-80 A2 | rifle | primary | IW80A2 | 5.56 x 45mm | Enable_SA-80 | all 22 | - | S (3 types) | IN |
| 65 | AK-105 | AK-105 | rifle | primary | ak105 | 5.45 x 39mm Soviet | Enable_AK105 | all 22 | - | S (3 types) | IN |
| 66 | KBP OTs-14 Groza | RA-14 | rifle | primary | RA14_groza | 7.62 x 39mm M1943 | Enable_OC14 | all 22 | - | S (3 types) | IN |
| 67 | 552SD | 552SD | rifle | primary | sig_commando | 5.56 x 45mm | Enable_552SD | - | all 22 | T (3 types) | IN |
| 68 | Steyr Aug | STG 77 | rifle | primary | steyr_aug9 | 5.56 x 45mm | Enable_STEYR | - | all 22 | T (6 types) | IN |
| 81 | Spas 12 | TA 12 GAUGE | shotgun | primary | spas12 | 12 Gauge | Enable_spas | - | all 22 | T (22 types) | IN |
| 83 | JACKHAMMER | M3 12 GAUGE | shotgun | primary | jackhammer | 12 Gauge | Enable_jack | - | all 22 | - | IN |
| 84 | 870 | 12 GAUGE PUMP | shotgun | primary | remington870 | 12 Gauge | Enable_870 | all 22 | - | S (22 types) | IN |
| 91 | M60E3 | M60E3 | MG | primary | m60e | 7.62 x 51mm | Enable_m60e | all 22 | all 22 | - | IN |
| 92 | M63A | M63A | MG | primary | stoner_m63a | 5.56 x 45mm | Enable_m63a | all 22 | all 22 | S (3 types) | IN |
| 93 | .PKM | PKM | MG | primary | stoner_m63a | 7.62 x 54 R | - | - | - | - | OUT |
| 101 | M82A1A | M82A1A | sniper | primary | barretm82A1 | .50 Cal | Enable_barret_lightm82A1 | - | all 22 | T (11 types) | IN |
| 102 | M40A1 | M40A1 | sniper | primary | remington700 | 7.62 x 51mm | Enable_remington700 | all 22 | all 22 | - | IN |
| 103 | M87ELR | M87ELR | sniper | primary | mcmillanM87 | .50 Cal | Enable_EquipmcmillanM87 | all 22 | - | - | IN |
| 104 | Dragunov | SASR | sniper | primary | Dragunov | 7.62 x 54 R | Enable_Dragonov | - | all 22 | - | IN |
| 105 | SR-25 SD | SR-25 SD | sniper | primary | stoner_sr25 | 7.62 x 51mm | Enable_stoner_sr25_SD | all 22 | - | - | IN |
| 106 | SR-25 | SR-25 | sniper | primary | stoner_sr25 | 7.62 x 51mm | Enable_stoner_sr25 | all 22 | - | S (10 types) | IN |
| 121 | M67 | M67 | grenade | equipment | grenade | M67 Ammo | Enable_frag | all 22 | all 22 | S, T (44 types) | IN |
| 122 | AN-M8 | AN-M8 | grenade | equipment | a_smoke_grenade | AN-M8 Ammo | Enable_smoke | all 22 | all 22 | S, T (31 types) | IN |
| 123 | Mark141 | Mark141 | grenade | equipment | flashbang | Mark141 Ammo | Enable_flash | all 22 | all 22 | - | IN |
| 126 | HE | HE | grenade | equipment | HEgrenade | HE Grenade Ammo | Enable_HEgren | all 22 | all 22 | S, T (43 types) | IN |
| 127 | RED SMOKE GRENADE | RED SMOKE  | grenade | equipment | a_smoke_grenade | RED SMOKE Ammo | Enable_red_smoke | - | - | - | OUT |
| 128 | BLUE CHEM LIGHT | CHEM LIGHT | grenade | equipment | bleu_chem | BLUE CHEM LIGHT Ammo | - | - | - | - | OUT |
| 141 | M203 | M203 | grenade launcher | primary | (null) | - | - | - | - | - | IN (dependent) |
| 142 | MGL | MGL | grenade launcher | primary | mglmk1 | - | Enable_mglmk1 | - | 7 8 10 64 83 | - | IN |
| 143 | M79 | M79 | grenade launcher | primary | m79 | - | Enable_m79 | - | 7 8 10 64 83 | - | IN |
| 145 | LAW | AT-4 | rocket launcher | rocket | AT4 | - | Enable_LAW | 7 8 11 51 81 | - | - | IN |
| 146 | RPG LAUNCHER | RPG-7 | rocket launcher | rocket | RPG7 | - | Enable_RPG | - | 1 5 11 12 51 61 72 73 81 | - | IN |
| 151 | C4 | C4 | explosive | equipment | c4 | C4 Ammo | Enable_c4 | 6 11 51 71 82 83 | 51 83 | S, T (11 types) | IN |
| 152 | Satchel | Satchel | explosive | equipment | Satchel | Satchel Charge Ammo | Enable_satchel | - | - | - | OUT |
| 153 | Claymore | Claymore | explosive | equipment | claymore | Claymore Ammo | Enable_claymore | all 22 | - | S (19 types) | IN |
| 154 | MPBOMB | MPBOMB | explosive | equipment | NONE | MPBOMB Ammo | - | - | - | - | OUT |
| 155 | air_to_ground_missile | air_to_ground_missile | explosive | equipment | grenade | ag_missile | - | - | - | - | OUT |
| 156 | exploding_fuel | Explosion | explosive | equipment | null | explosive_stuff | - | - | - | - | OUT |
| 157 | Satchel Explosion | Satchel Explosion | explosive | equipment | Satchel | Satchel Charge Ammo | - | - | - | - | OUT |
| 158 | PMN Mine | PMN Mine | explosive | equipment | PMN_mine | PMN Ammo | Enable_pmn | - | all 22 | T (22 types) | IN |
| 159 | Backblast | Backblast | explosive | equipment | NULL | Backblast Ammo | - | - | - | - | OUT |
| 171 | M203 HE | M203 HE | launcher round | equipment | M203 | M203 HE Ammo | Enable_203HE | 1 5 10 12 52 53 64 72 82 83 | 7 8 10 64 83 | - | IN |
| 173 | M203 SMOKE | M203 SMOKE | launcher round | equipment | M203 | M203 SMOKE Ammo | Enable_203SMK | 1 5 10 12 52 53 64 72 82 83 | 7 8 10 64 83 | - | IN |
| 175 | M203 FRAG | M203 FRAG | launcher round | equipment | M203 | M203 FRAG Ammo | Enable_203FRAG | 1 5 10 12 52 53 64 72 82 83 | 7 8 10 64 83 | - | IN |
| 176 | GL HE | M79 HE | launcher round | equipment | M203 | GL HE Ammo | Enable_GLHE | - | 7 8 10 64 83 | - | IN |
| 178 | GL SMOKE | M79 SMOKE | launcher round | equipment | M203 | GL Smoke Ammo | Enable_GLSMK | - | 7 8 10 64 83 | - | IN |
| 179 | GL FRAG | M79 FRAG | launcher round | equipment | M203 | GL Frag Ammo | Enable_GLFRAG | - | 7 8 10 64 83 | - | IN |
| 180 | ARTILLERY SHELL | ARTILLERY SHELL | launcher round | equipment | artillery_shell | ARTILLERY SHELL AMMO | - | - | - | - | OUT |
| 181 | F2000 HE | OICW HE | launcher round | equipment | M203 | F2000 HE Ammo | Enable_F2000HE | - | - | - | OUT |
| 182 | F2000 SMOKE | OICW SMOKE | launcher round | equipment | M203 | F2000 SMOKE Ammo | Enable_F2000SMK | - | - | - | OUT |
| 183 | F2000 FRAG | OICW FRAG | launcher round | equipment | M203 | M203 FRAG Ammo | Enable_F2000FRAG | - | - | - | OUT |
| 185 | LAW HEAT | AT-4 HEAT | rocket round | equipment | AT4_Heat | LAW HEAT Ammo | - | - | - | - | IN (dependent) |
| 186 | RPG | RPG ROUND | rocket round | equipment | RPGrenade | RPG Ammo | Enable_RPG | - | 1 5 11 12 51 61 72 73 81 | - | IN |
| 190 | Binoculars | Binoculars | gear | equipment | placeholder | - | - | - | - | - | OUT |
| 193 | Detonator | Detonator | gear | equipment | detonator | - | - | - | - | - | IN (dependent) |
| 194 | Double Ammo Load | 2X AMMO | gear | equipment | (null) | - | Enable_2xammo | all 22 | all 22 | S, T (44 types) | IN |
| 195 | Thermal Scope | THERMAL SCOPE | gear | equipment | detonator | - | Enable_ThermScope | 1 2 5 7 8 11 52 61 62 64 73 83 | 1 2 5 7 8 11 52 61 62 64 73 83 | - | IN |
| 201 | Kevlar Armor | Kevlar Armor | armour | equipment | (null) | - | - | - | - | - | OUT |
| 202 | Kevlar Armor with inserts | Kevlar Armor with inserts | armour | equipment | (null) | - | - | - | - | - | OUT |
| 205 | PKM TURRET | RMG | turret | equipment | stoner_m63a | 7.62 x 54 R | - | - | - | - | OUT |
| 207 | LMG TURRET | LMG | turret | equipment | stoner_m63a | 7.62 x 54 R | - | - | - | - | OUT |
| 230 | MGL FRAG TURRET | 30 mm MGL | turret2 | equipment | M203 | M203 FRAG Ammo | - | - | - | - | OUT |
| 254 | FULL_SLOT | ------- | internal | equipment | detonator | - | - | - | - | - | OUT |
| 255 | EQUIP_NONE | <NONE> | internal | equipment | detonator | - | - | - | - | - | OUT |

**Out of scope, with the reason** (the 23 OUT rows):

| id | record | reason |
|---|---|---|
| 11 | Designator | no valve in `FUN_003cf1f0` (so never selectable, L87468-87478), in no kit; SOCOM 1 armory UI still names `EquipLasDes` (`uidlg.ts`) |
| 63 | F2000 "OICW" | `Enable_F2000` = 0 on all 22 maps; in no kit |
| 93 | .PKM | no valve in `FUN_003cf1f0`; in no kit (the prep's list missed it: it is an MG record, id 93, model `stoner_m63a`) |
| 127 | RED SMOKE GRENADE | `Enable_red_smoke` = 0 on all 22 |
| 128 | BLUE CHEM LIGHT | no valve in the code (`Enable_blue_chem`, MP1 only, value 0, is read by nothing) |
| 152 | Satchel | `Enable_satchel` = 0 on all 22 (SlotCost 2; its partner slot would be FULL_SLOT) |
| 154 | MPBOMB | no valve; the DEMOLITION objective's bomb (engine row) |
| 155-157, 159 | air_to_ground_missile, exploding_fuel, Satchel Explosion, Backblast | engine rows (explosion / effect carriers), no valve |
| 180 | ARTILLERY SHELL | engine row, no valve |
| 181-183 | F2000 HE/SMOKE/FRAG | their valves exist but are 0 on every map and the menu only sets them to 9 with an F2000 primary, which no map enables |
| 190 | Binoculars | no valve, no kit (also a `wep_name` special: `NVG` -> 0xbf, `BINOCULARS` -> 0xbe, `FUN_003d19e0` L324303) |
| 201, 202 | Kevlar Armor (+ inserts) | no valve, no MP kit; the kit finaliser still honours them (`FUN_005c7840` L480332-480370: 202 / 201 pick the armour set) |
| 205, 207, 230 | turrets | vehicle/emplacement rows, no valve |
| 254, 255 | FULL_SLOT, EQUIP_NONE | internal slot markers (FULL_SLOT = the second slot of a cost-2 item; EQUIP_NONE = empty) |

**In scope only as dependents** (no valve of their own): **141 M203** -- the M203 rifles' launcher, placed locked in
kit slot 2 (A5); **185 LAW HEAT** -- placed in the LAW's partner slot (SlotCost 2, A5); **193 Detonator** -- added to the
kit when the owner has a claymore out (`FUN_005c74e0` L480154-480200: owner list `+0x6c4` holds a 153 and the kit
has no 193 -> `FUN_005bdfb0(kit, n, 0xc1)`; `FUN_005bc730` L474128-474130 selects it after a claymore is placed).
Their behaviour is reader (c)'s.

### A2. The id -> valve map (`FUN_003cf1f0`, L322760-322968)

`undefined8 FUN_003cf1f0(char id)`: an if-chain on the **signed** byte, each arm `return FUN_00351ef0(<string>)`
(the valve object or NULL); anything unlisted returns 0. The strings were read from the ELF (`elfread.py str`). Listed
in the code's order (id decoded to unsigned; line = the arm's `if`):

| line | id | record | valve string (addr) | on the 22 MP maps |
|---|---|---|---|---|
| 322766 | 127 | RED SMOKE GRENADE | `Enable_red_smoke` (0x3fd2e0) | 22 x 0 |
| 322769 | 181 | F2000 HE | `Enable_F2000HE` (0x3fd2d0) | 20 maps x 0; absent MP2, MP11 |
| 322772 | 182 | F2000 SMOKE | `Enable_F2000SMK` (0x3fd2c0) | as above |
| 322775 | 183 | F2000 FRAG | `Enable_F2000FRAG` (0x3fd2a0) | as above |
| 322778 | 145 | LAW | `Enable_LAW` (0x3fd290) | 22 |
| 322781 | 146 **and** 186 | RPG LAUNCHER and RPG round | `Enable_RPG` (0x3fd280) | 22 |
| 322784 | 176 | GL HE | `Enable_GLHE` (0x3fd270) | 22 |
| 322787 | 178 | GL SMOKE | `Enable_GLSMK` (0x3fd260) | 22 |
| 322790 | 179 | GL FRAG | `Enable_GLFRAG` (0x3fd250) | 22 |
| 322793 | 126 | HE | `Enable_HEgren` (0x3fd240) | 22 |
| 322796 | 172 | (no record) | `Enable_203ILL` (0x3fd230) | on no map (dead arm) |
| 322799 | 175 | M203 FRAG | `Enable_203FRAG` (0x3fd220) | 22 |
| 322802 | 173 | M203 SMOKE | `Enable_203SMK` (0x3fd210) | 22 |
| 322805 | 171 | M203 HE | `Enable_203HE` (0x3fd200) | 22 |
| 322808 | 151 | C4 | `Enable_c4` (0x3fd1f0) | 21 (MP81 spells it `Enable_C4`) |
| 322811 | 158 | PMN Mine | `Enable_pmn` (0x3fd1e0) | 22 |
| 322814 | 153 | Claymore | `Enable_claymore` (0x3fd1d0) | 22 |
| 322817 | 152 | Satchel | `Enable_satchel` (0x3fd1b8) | 22 |
| 322820 | 124 | (no record) | `Enable_phos` (0x3fd1a8) | on no map (dead arm) |
| 322823 | 123 | Mark141 | `Enable_flash` (0x3fd198) | 22 |
| 322826 | 122 | AN-M8 | `Enable_smoke` (0x3fd188) | 22 |
| 322829 | 121 | M67 | `Enable_frag` (0x3fd178) | 22 |
| 322832 | 195 | Thermal Scope | `Enable_ThermScope` (0x3fd160) | 22 |
| 322835 | 194 | Double Ammo Load | `Enable_2xammo` (0x3fd148) | 22 |
| 322838 | 38 | MP5K "HK5K" | `Enable_MP5K` (0x3fd138) | 22 |
| 322841 | 12 | P228 "M11" | `Enable_P228` (0x3fd128) | 22 |
| 322844 | 13 | SR-1 Gyurza "SP-10" | `Enable_SR1_Gyurza` (0x3fd110) | 22 |
| 322847 | 7 | DE .50 | `Enable_desert_eagle` (0x3fd0f0) | 22 |
| 322850 | 5 | M9 | `Enable_beretta_m9` (0x3fd0d0) | 22 |
| 322853 | 4 | F57 | `Enable_fiveseven` (0x3fd0b0) | 22 |
| 322856 | 14 | Model 18 | `Enable_glock18` (0x3fd0a0) | 22 |
| 322859 | 8 | 9mm Pistol | `Enable_HkP9s` (0x3fd090) | 22 |
| 322862 | 6 | 226 | `Enable_Sig226` (0x3fd080) | 22 |
| 322865 | 16 | Mark 23SD | `Enable_mark23sd` (0x3fd070) | 22 |
| 322868 | 15 | Mark 23 | `Enable_Mark23` (0x3fd060) | 22 |
| 322871 | 66 | KBP OTs-14 Groza "RA-14" | `Enable_OC14` (0x3fd050) | 22 |
| 322874 | 65 | AK-105 | `Enable_AK105` (0x3fd040) | 22 |
| 322877 | 64 | SA-80 A2 "IW-80 A2" | `Enable_SA-80` (0x3fd030) | 22 |
| 322880 | 104 | Dragunov "SASR" | `Enable_Dragonov` (0x3fd020) | 22 |
| 322883 | 67 | 552SD | `Enable_552SD` (0x3fd008) | 22 |
| 322886 | 63 | F2000 "OICW" | `Enable_F2000` (0x3fcff8) | 22 |
| 322889 | 143 | M79 | `Enable_m79` (0x3fcfe8) | 22 |
| 322892 | 142 | MGL | `Enable_mglmk1` (0x3fcfd8) | 22 |
| 322895 | 68 | Steyr Aug "STG 77" | `Enable_STEYR` (0x3fcfc8) | 22 |
| 322898 | 105 | SR-25 SD | `Enable_stoner_sr25_SD` (0x3fcfb0) | 22 |
| 322901 | 62 | M4A1 SD | `Enable_M4A1_SD` (0x3fcf98) | 22 |
| 322904 | 54 | M4A1 | `Enable_m4Acarbine` (0x3fcf80) | 22 |
| 322907 | 103 | M87ELR | `Enable_EquipmcmillanM87` (0x3fcf60) | 22 |
| 322910 | 84 | 870 "12 GAUGE PUMP" | `Enable_870` (0x3fcf50) | 22 |
| 322913 | 101 | M82A1A | `Enable_barret_lightm82A1` (0x3fcf30) | 22 |
| 322916 | 106 | SR-25 | `Enable_stoner_sr25` (0x3fcf10) | 22 |
| 322919 | 92 | M63A | `Enable_m63a` (0x3fcef8) | 22 |
| 322922 | 91 | M60E3 | `Enable_m60e` (0x3fcee8) | 22 |
| 322925 | 102 | M40A1 | `Enable_remington700` (0x3fced0) | 22 |
| 322928 | 37 | 9mm Sub | `Enable_uzi` (0x3fceb8) | 22 |
| 322931 | 57 | 552 | `Enablesig_commando` (0x3fcea0) | 22 (same spelling on disc) |
| 322934 | 60 | M14 | `Enable_m14_gun` (0x3fce88) | 22 |
| 322937 | 81 | Spas 12 "TA 12 GAUGE" | `Enable_spas` (0x3fce78) | 22 |
| 322940 | 83 | JACKHAMMER "M3 12 GAUGE" | `Enable_jack` (0x3fce68) | 22 |
| 322943 | 59 | AKS-74 | `Enable_aks74` (0x3fce58) | 22 |
| 322946 | 58 | AK-47 | `Enable_ak47` (0x3fce48) | 22 |
| 322949 | 31 | HK5 | `Enable_mp5` (0x3fce38) | 22 |
| 322952 | 33 | HK5SD | `Enable_mp5sd` (0x3fce28) | 22 |
| 322955 | 52 | M16A2-M203 | `Enable_M16203` (0x3fce18) | 22 |
| 322958 | 61 | M4A1-M203 | `Enable_m4Acarbine_203` (0x3fce00) | 22 |
| 322961 | 51 | M16A2 | `Enable_M16` (0x3fcde8) | 22 |
| 322964 | 34 | F90 | `Enable_FNP` (0x3fcdd8) | 22 |

**How the valve is found.** `FUN_00351ef0(name)` (L250997-251016) walks the global valve list from `DAT_0049e808`
to the sentinel `&DAT_0049e804` and returns the first valve whose name (`*valve`) compares equal with `FUN_00198f18`
(L15767: newlib's word-at-a-time `strcmp`, falling back to a byte compare that returns `a - b`, L15849-15859; no case
folding -- the library's case-folding compare is the separate `FUN_00198b80` L15553, used for `NVG`/`BINOCULARS`).
**Case-sensitive, exact.** The map's valves enter that list at load: `FUN_002acc10` L152384-152420 reads
`mission.rdr` `Valves` (`NAME` string 0x3f0ab0, `PERM` 0x3f1a08 / `PERSIST` 0x3f1a10 flags, `VALUE` 0x3f1a18) into
`FUN_003520d0(name, value, type)`, the value a `ushort` at valve `+4`. reCOM does the same (`recom/src/gamez/zFTS/fts_mission.cpp:281-299`)
with `strcmp` (`recom/src/gamez/zValve/valve_main.cpp:151`).

**A missing valve** (NULL) means: not selectable in the in-game list (`FUN_0023c390` L87468-87478: `uVar5 = 0` unless
the valve exists), skipped by the auto-fill (`FUN_0023b9b0` L87164-87176), never locked (`FUN_0023e910` L88535-88539;
armory `FUN_00281950` L128090-128091). So an item with no `FUN_003cf1f0` arm, or whose valve is misspelt on the map,
can only be carried if a kit or a dependency puts it there.

**The disc's spellings against the code** (`arsenal-out.txt`, "valves not in code map" / "code valves absent"):
- `Enablesig_commando` -- the code's string is the same (0x3fcea0), so the 552 works on all 22 maps.
- `Enable_C4` on **MP81 Chain Reaction** (value 0) instead of `Enable_c4`: `Enable_c4` is absent there, so C4 is not
  selectable on MP81 (it would be 0 anyway) and no kit there carries C4.
- `Enable_RPG_ammo` (21 maps) and `Enable_RPG_Ammo` (MP73, beside no `Enable_RPG_ammo`): **read by nothing** -- the
  RPG round 186 is keyed to `Enable_RPG` (L322781). MP73's odd capital changes nothing.
- `Enable_blue_chem` (MP1 only, 0): no code arm (128 has none).
- `Spas 12`: every MP map says `Enable_spas`; the space-spelt valve the prep saw is in single-player M61, which is not in
  this archive (`SPAS_SP_VALVE_PLACEHOLDER`, note only). Kits name the record `Spas 12` by `wep_name`, looked up
  case-sensitively against `InternalName` (`FUN_003d19e0` L324303 -> `FUN_003c4c10` -> `FUN_003c4c40` L316497-316514, `strcmp`).
- `Enable_phos`, `Enable_203ILL`: code arms with no map valve and no record.

Every other non-`Enable_` valve in the maps' `Valves` (`uiEquipReturnScreen`, `InWhichAOP`, ...) is outside the arsenal.

### A3. The mask

**Selectable (bits 1 and 8).** The in-game list's test (`FUN_0023c390` L87468-87478):
`valve = FUN_003cf1f0(id); m = FUN_002c30b0(FUN_001fcd70()) ? 8 : 1; ok = valve && (m & valve->value)` --
`FUN_001fcd70()` the local player, `FUN_002c30b0` (L164664) "is a Terrorist" (the team flag equal to 0x40000001 or
0x80000100 by the side-swap byte `DAT_004412d8`; `FUN_002c31d0` L164725 is the SEAL twin). So **1 = SEALs, 8 =
Terrorists, 9 = both, 0 = neither**. The front-end armory's auto-fill uses the `player_team` valve instead
(`FUN_00283b50` L129165-129197, `FUN_00283e60` L129249-129285: `player_team == 0 ? 1 : 8`), and `player_team` is
written by `FUN_002c3330` (L164814-164872): 0 for the SEAL flag, 8 for the Terrorist flag, 0x10 for a spectator.

**Locked (bits 16 and 32).** `FUN_0023e910(menu, slot)` (L88478-88545) answers "may this slot be changed":
false for the M203 (141) and FULL_SLOT (254); for a LAW HEAT or an RPG round, false unless another equipment slot
holds the same id; and for **C4 only**: `valve = FUN_00351ef0("Enable_c4")` (0x3e6c98), `m = is-Terrorist ? 0x20 :
0x10`, `if (valve->value & m) locked`. So **16 = C4 is locked in a SEAL's kit, 32 = in a Terrorist's** (no map uses 32).
The armory's lock (`FUN_00281950` L128065-128095, per selected character and kit slot; `FUN_002815d0` L127929-128060 =
`UIDoAllSelCharsHaveLockedEquip1..3`) is broader: **any** item whose valve has `0x30`, regardless of side, plus 141,
185, 254 and an RPG round with no second one (`FUN_00282eb0` L128794: the index of another slot with that id, or -1).
On the disc, 16 appears only as `Enable_c4 = 16` on MP61 Sujo, MP62 Enowapi and MP73 Sandstorm (BREACH), where all
four SEAL types carry C4 as their fifth item (`kits-out.md`): the SEAL keeps the C4 and cannot swap it, and nobody can
select C4 there. `FUN_002815d0` also writes the per-character locked bits into the `UiCharLocked` valve (0x3ef698) for
the UI script.

**Rewritten valves.** The menu overwrites the launcher-round valves: `FUN_00240e60` (menu open, L89585; called L57439)
reads the player's current primary (`FUN_005c8980` on the kit) and sets `Enable_GLFRAG/GLSMK/GLHE` = 9 for the M79,
`Enable_F2000FRAG/SMK/HE` = 9 for the F2000, `Enable_203FRAG/SMK/HE` = 9 for an M203 rifle (`FUN_003c5e10` L317306:
id 52 or 61) or the MGL (142), every other group 0; `FUN_0023fef0` (L89205-89300) sets them on a launcher pick and
`FUN_0023eca0` (L88660-88870) clears them when the launcher leaves. So in game a launcher round is selectable by
**whichever side holds its launcher** (9 has both bits), whatever the map's own round value; the map value applies
only before the menu first opens (and in the armory, which checks the pairing directly, `FUN_00280e90` A5).

### A4. Per map, per side

**Selectable** = ids whose valve gives the side's bit on that map (the raw map value; the launcher rounds then follow
A3's rewrite, and the menu's extra rules in A5 apply on top). Produced by `arsenal.ts` + `scope.py`:

| map | SEAL n | SEAL selectable (ids) | Terrorist n | Terrorist selectable (ids) |
|---|---|---|---|---|
| MP1 Blizzard | 34 | 8 12 13 15 16 31 33 38 51 52 54 60 61 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 171 173 175 194 195 | 30 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 146 158 186 194 195 |
| MP2 Frostfire | 29 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 194 195 | 28 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 158 194 195 |
| MP5 Abandoned | 34 | 8 12 13 15 16 31 33 38 51 52 54 60 61 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 171 173 175 194 195 | 30 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 146 158 186 194 195 |
| MP6 Desert Glory | 29 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 151 153 194 | 27 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 158 194 |
| MP7 Night Stalker | 30 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 145 153 194 195 | 36 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 142 143 158 171 173 175 176 178 179 194 195 |
| MP8 Rat'S Nest | 30 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 145 153 194 195 | 36 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 142 143 158 171 173 175 176 178 179 194 195 |
| MP9 Bitter Jungle | 28 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 194 | 27 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 158 194 |
| MP10 Blood Lake | 33 | 8 12 13 15 16 31 33 38 51 52 54 60 61 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 171 173 175 194 | 35 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 142 143 158 171 173 175 176 178 179 194 |
| MP11 Death Trap | 31 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 145 151 153 194 195 | 30 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 146 158 186 194 195 |
| MP12 The Ruins | 33 | 8 12 13 15 16 31 33 38 51 52 54 60 61 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 171 173 175 194 | 29 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 146 158 186 194 |
| MP51 Vigilance | 30 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 145 151 153 194 | 30 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 146 151 158 186 194 |
| MP52 The Mixer | 34 | 8 12 13 15 16 31 33 38 51 52 54 60 61 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 171 173 175 194 195 | 28 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 158 194 195 |
| MP53 Foxhunt | 33 | 8 12 13 15 16 31 33 38 51 52 54 60 61 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 171 173 175 194 | 27 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 158 194 |
| MP61 Sujo | 29 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 194 195 | 30 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 146 158 186 194 195 |
| MP62 Enowapi | 30 | 6 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 194 195 | 28 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 158 194 195 |
| MP64 Shadow Falls | 34 | 8 12 13 15 16 31 33 38 51 52 54 60 61 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 171 173 175 194 195 | 36 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 142 143 158 171 173 175 176 178 179 194 195 |
| MP71 Fish Hook | 29 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 151 153 194 | 27 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 158 194 |
| MP72 Crossroads | 33 | 8 12 13 15 16 31 33 38 51 52 54 60 61 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 171 173 175 194 | 29 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 146 158 186 194 |
| MP73 Sandstorm | 29 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 153 194 195 | 30 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 146 158 186 194 195 |
| MP81 Chain Reaction | 29 | 8 12 13 15 16 31 33 38 51 54 60 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 145 153 194 | 29 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 146 158 186 194 |
| MP82 Guidance | 34 | 8 12 13 15 16 31 33 38 51 52 54 60 61 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 151 153 171 173 175 194 | 27 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 158 194 |
| MP83 Requiem | 35 | 8 12 13 15 16 31 33 38 51 52 54 60 61 62 64 65 66 84 91 92 102 103 105 106 121 122 123 126 151 153 171 173 175 194 195 | 37 | 4 5 6 7 14 34 37 51 57 58 59 60 67 68 81 83 91 92 101 102 104 121 122 123 126 142 143 151 158 171 173 175 176 178 179 194 195 |

Items every map gives both sides: M16A2 (51), M14 (60), M60E3 (91), M63A (92), M40A1 (102), M67, AN-M8, Mark141, HE
(121-126), 2X (194). SEAL-only everywhere: the 9mm Pistol, P228, SR-1, Mark 23, Mark 23SD, HK5, HK5SD, MP5K, M4A1, M4A1
SD, SA-80, AK-105, Groza, 870, M87ELR, SR-25, SR-25 SD, Claymore. Terrorist-only everywhere: F57, M9, 226 (except MP62,
where it is both), DE .50, Model 18, F90, 9mm Sub, 552, AK-47, AKS-74, 552SD, Steyr Aug, Spas 12, JACKHAMMER, M82A1A,
Dragunov, PMN. Per-map deltas: the M203 rifles and their rounds (SEAL: MP1, 5, 10, 12, 52, 53, 64, 72, 82, 83), the
M79 and MGL with the GL and M203 rounds (Terrorist: MP7, 8, 10, 64, 83), the LAW (SEAL: MP7, 8, 11, 51, 81), the RPG-7
and its round (Terrorist: MP1, 5, 11, 12, 51, 61, 72, 73, 81), C4 (SEAL MP6, 11, 71, 82; both MP51, 83; locked MP61, 62,
73), the thermal scope (both: MP1, 2, 5, 7, 8, 11, 52, 61, 62, 64, 73, 83).

**Default kits** (`character.rdr` `default_weapons`, slot order primary / secondary / equipment x3, each map's
`chartype.rdr` `navyseals` then `terrorists`, resolved through the `name : base` chain -- every type carries its own list,
none inherits one). The kit table is `kits-out.md`; **it equals research 91 section 14 for all 176 types**
(`cmp91.py`: `diffs 0`), so it is not repeated here. Kit entries have only `wep_name` (no `ammo_name`, `ammo_count`,
`mag_count` -- the parser's optional keys, `CCharacterType_Parse` `FUN_0053ce00` L406362-406395), so the spawn takes the
record's `Ammo_Capacity`/`NumMags` (A6). **Kits are not filtered by the valves**: `CZSealBody_PostCreateSeal` adds each
entry with `FUN_005bdfb0` (no `FUN_003cf1f0` call on that path). The kits' items against their own side's mask
(`arsenal.ts` "!!"):

| type | item | map value | meaning |
|---|---|---|---|
| mp6_seal4 (MP6 SEAL 4) | 226 | 8 | a Terrorist-only pistol in a SEAL's default kit: carried, but not re-selectable once changed |
| mp7_seal2 (MP7 SEAL 2) | 226 | 8 | as above |
| mp61/62/73_seal1-4 (12 types) | C4 | 16 | the locked C4 (A3) |

Everything else in all 176 kits is selectable by its own side on its own map.

### A5. The list builders and the slot rules

#### A5.1 Which function does what

| function (retail) | name / role | reads |
|---|---|---|
| `FUN_0023c390` L87358 | **in-game: is record R selectable in the edited slot** (param 3 a class filter or -1, param 4 the slot kind 0 primary / 1 secondary / 2 equipment / 3 any) | A5.2 |
| `FUN_0023c6f0` L87491 | in-game: step the item list forward/back (`DAT_004b5210` = the record count, `FUN_003c4b00` = the n-th record in parse order), skipping what `FUN_0023c390` refuses | recursion L87520-87523 |
| `FUN_0023c840` L87534 | in-game: step the **class tab** (primary: SMG 0x1f -> rifle 0x33 -> shotgun 0x51 -> MG 0x5b -> sniper 0x65 -> grenade launcher 0x8d; secondary: pistol 4 only; equipment: grenade 0x79 -> rocket launcher 0x91 -> explosive 0x97 -> launcher round 0xab -> rocket round 0xb9 -> gear 0xbe), skipping a class with no selectable member (`FUN_0023cb90` L87663 walks ids of the class, `FUN_0023c390(..., class, 3)` L87648); `FUN_0023d060` L87811-87838 also skips the launcher-round tab unless a launcher flag (`+0x1532/3/4`) is set | L87540-87660 |
| `FUN_0023d540` L87972 | in-game: open the list on a slot -- slot kind from the item already there (`FUN_003d1d10` primary -> 0, `FUN_003d1ce0` pistol -> 1, else 2; an empty slot -> equipment, grenade tab) | L87984-88007 |
| `FUN_0023b9b0` L87106 | in-game **auto-fill**: the next equipment record after the current (not primary, not pistol, not rocket launcher, not param 4, valve bit set), re-run while the result is a "single" item already in an equipment slot (193, 141, 255, 151, 254, 195, 152, 154, 194) | L87132-87180 |
| `FUN_0023bc50` L87188 | in-game auto-fill for a **dependent** item already in a slot (rounds 171-183, M79/MGL 142/143, and the singles above): replace it the same way | L87205-87267 |
| `FUN_0023fef0` L89138 | in-game **set slot = record** (A5.4) | |
| `FUN_0023eca0` L88610 | in-game **item leaves a slot**: undo its dependents (A5.4) | |
| `FUN_0023e910` L88478 | in-game: may this slot be changed (A3's lock) | |
| `FUN_00240e60` L89585 | in-game menu open: reset, rewrite the round valves from the current primary (A3) | |
| `FUN_0023e5e0` L88381 / `FUN_00227560` L77567 | in-game: commit the five slots to the player's type kit vector (A6) | |
| `FUN_002815d0` L127929 | armory `UIDoAllSelCharsHaveLockedEquip1..3` (0x281050/40/30 = `j FUN_002815d0` with `a0` 0/1/2, recomp `UIDoAllSelCharsHaveLockedEquip*_0x28103*.cpp`/`0x281040`/`0x281050` lines 20-32) | A3 |
| `FUN_00281950` L128065 | armory: is kit slot N of this character locked | A3 |
| `FUN_00283b50` L129131 / `FUN_00283e60` L129214 | armory twins of `FUN_0023b9b0` / `FUN_0023bc50`; `FUN_00283b50` also never auto-picks the thermal scope (L129189); `FUN_00283e60` also asks `FUN_00280e90` | |
| `FUN_00280e90` L127740 | armory: may this character carry item X with its primary (A5.3) | |
| `FUN_00280d60` L127689 (`UICanCharactersSelectUIWeapon`) | armory: the `UiWeapon` valve (0x3ef688) holds a UI index (`FUN_003d3230` L325704 maps id -> index); true if every selected character (`UiCharSet` 0x3ee878 bits) passes `FUN_00280e90` | |
| `FUN_00284120` L129300 | armory: enough free equipment slots for the pick (A5.3) | |
| `FUN_00281be0` L128148 | armory `UIChooseDefaultEquipmentOnly` (A5.5) | |

#### A5.2 The in-game selectable rule (`FUN_0023c390` L87358-87487)

For record R and the edited slot `cur` (`menu +0x1194`), in order:

1. **Slot kind** (L87372-87389): kind 2 (equipment) refuses primaries and pistols -- rocket launchers are allowed; kind 1
   takes only pistols; kind 0 only primaries. The class is **the id range** (`FUN_003d1a60`), not a key.
2. **Class filter** (L87391): param 3 = -1 or R's class (the tab).
3. **Thermal scope 195** (L87394-87414): only if some slot other than `cur` holds a sniper-class record (class 0x65).
4. **RPG round 186** (L87415-87430): only if some other slot already holds the same round record (the one the RPG-7
   placed), and (L87431-87442) never into the slot that holds the RPG-7.
5. **No duplicates of** 194 2X, 195 thermal, 158 PMN, 153 claymore, 185 LAW HEAT, 145 LAW, 146 RPG-7 (L87443-87466):
   refused when another slot holds the same record. Grenades, C4, launcher rounds and the RPG round may repeat.
6. **Side mask** (L87468-87478): `valve & (is-Terrorist ? 8 : 1)`; no valve -> refused.

#### A5.3 The armory's extra rules (front end; the viewer has no lobby, recorded for completeness)

`FUN_00280e90` (L127740-127800), per selected character, against its kit slot 0 (the primary): thermal scope 195 only
with a sniper primary; RPG round 186 only if the kit holds an RPG-7; a second RPG-7 or LAW refused; M203 rounds
171/173/175 only with an M203 rifle (52, 61) or the MGL (142); GL rounds 176/178/179 only with the M79 (143); F2000
rounds 181-183 only with the F2000 (63). `FUN_00284120` (L129300-129357): the pick needs free equipment slots --
satchel, RPG-7, LAW 2; M79, MGL, F2000 1; an M203 rifle 2 -- against 3 minus the locked slots (A3), plus what the
replaced item frees; refused if short. The armory's per-item side filter for its list is not in the code read here
(the UI script `dlg_equipment_mp.rdr` names `Equip<x>` buttons, no `Enable_` valve -- `uidlg.ts`):
`ARMORY_LIST_FILTER_PLACEHOLDER` (note only).

#### A5.4 SlotCost, launchers and dependents (`FUN_0023fef0` L89138-89323, `FUN_0023eca0` L88610-89136)

- `SlotCost` is parsed at L322610-322614 (key string 0x3fcc80; missing -> 1) into record `+0x27c` (`FUN_003c5960`
  L317023; read by `FUN_003c5970`, and `FUN_003d3750` L325936 returns it by id, 1 for an unknown id). On the disc: LAW 2,
  RPG LAUNCHER 2, Satchel 2 (`arsenal-out.txt`).
- **Cost 2** (L89160-89200): the partner slot is the next equipment slot (4 wraps to 2), or an empty (255) one if any;
  it receives **185 LAW HEAT** for the LAW, **186 RPG** for the RPG-7, else **254 FULL_SLOT** (the satchel); its old id
  is kept in `+0x1530`. Removing the launcher (`FUN_0023eca0` L89080-89131) replaces those rounds with auto-fill
  picks (`FUN_0023b9b0`), never the id just removed.
- **M203 rifle** (52, 61; L89285-89320): valves `Enable_203*` = 9, kit slot 2 <- **141 M203** (locked, A3), slot 3 <-
  **175 M203 FRAG**; the two displaced ids kept in `+0x1530/+0x1531`.
- **M79** (143; L89205-89231): `Enable_GL*` = 9, slot 2 <- **179 GL FRAG**. **MGL** (142; L89232-89258): `Enable_203*`
  = 9, slot 2 <- **175 M203 FRAG** (the MGL fires the M203 rounds). **F2000** (63; L89259-89284): `Enable_F2000*` = 9,
  slot 2 <- **183**.
- **Leaving** (`FUN_0023eca0`): the valves go back to 0 and every slot holding that launcher's rounds (and the M203) is
  refilled -- the first from the saved `+0x1530`/`+0x1531`, the rest by auto-fill (L88640-88870). A sniper leaving
  takes the thermal scope with it (L88823-88840).
- The auto-fill's side test is inverted (`INGAME_AUTOFILL_SIDE_READING`): `FUN_0023b9b0` and `FUN_0023bc50` compute
  `mask = (player_team valve == 0) ? 8 : 1` (L87139-87170, L87226-87260; MIPS 0x23bbd0-0x23bbe8 in recomp
  `FUN_0023b9b0_0x23b9b0.cpp`: `addiu $a0,$zero,8` / `movz $a0,$v1,$s2` with `$s2` = "value is 0"), while
  `FUN_002c3330` writes 0 for the SEALs. As shipped, a SEAL's refilled slot is drawn from items with the Terrorist bit.

#### A5.5 The default-equipment rule (`UIChooseDefaultEquipmentOnly`, `FUN_00281be0` L128148-128196)

For each selected character (`UiCharSet` bits, `FUN_002744f0` iterates, up to 32): remember kit slots 0 and 1; find
the character type by name (`FUN_002af760`, `FUN_0053e170` L406914 -- a `strcmp` over the type list `DAT_0044cd50`);
copy the type's default kit vector (`+0x2e8`) over the character's (`FUN_00284720`); re-apply the remembered primary and
secondary with `CCharacterWeap_SetupCharacterWeapon`; refresh the description (`FUN_002af190` L153579). So: **the
equipment goes back to the type's `default_weapons`, the chosen primary and secondary stay.** The in-game menu has no
such command in the code read (reader (b) owns the menu's screens).

#### A5.6 In-game against armory

| rule | in-game | armory |
|---|---|---|
| side of the list | `FUN_002c30b0` (the player's team flag) | `player_team` valve |
| side of the auto-fill | `player_team == 0 -> 8` (inverted) | `player_team == 0 -> 1` |
| launcher rounds | valves rewritten to 9/0 by the primary | `FUN_00280e90` pairs round and primary directly |
| thermal scope | needs a sniper in another slot | needs a sniper primary |
| lock | C4 only, by side (16 SEAL / 32 Terrorist) + 141/254 + a lone 185/186 | any item with 16 or 32, any side + 141/185/254 + a lone 186 |
| free-slot check | none; the launcher overwrites slots 2/3 and saves them | `FUN_00284120` refuses when short |
| scope | the viewer's menu (W4.R3) | not built (spec section 6) |

### A6. From a pick to the body

- **The kit entry.** `CCharacterWeap_SetupCharacterWeapon` (0x53eee0, L407443-407461; r0004 0x543930):
  `entry[0] = id; rec = CZWeaponList_GetWeapon(id)` (0x3c4b40); `entry+4 = rec+0x28` (**Ammo_Capacity**, parser
  L322469-322473 via `FUN_003d2a20` L325336); `entry+8 = rec+0x2c` (**NumMags**, L322436-322440 via `FUN_003d2a10`
  L325326); `entry[1] = ` the first `AMMO_TYPES` round's id (`FUN_003d1ea0` L324490: ZAMMO `+0x30`).
- **The commit.** Confirm in the menu (`FUN_00240600` L89343, state 3, L89386-89395): `FUN_0023fef0(menu, cur,
  highlighted)` then `FUN_0023e5e0` (L88381-88405): for slot 0..4, `SetupCharacterWeapon(type.kit[i], slot[i].id)`,
  growing the vector with `FUN_0053b3a0` when short. The type is the player's `+0x540` (`FUN_00599810` L455467), i.e. the
  **character type object**, so the pick persists on the type until changed. `FUN_00227560` (L77567-77590) is the same
  write from a byte array (`+0x11a4`, near `CInGameWeaponSel_Init` 0x227ad0).
- **The body.** At the next spawn `CZSealBody_ReCreate` (`FUN_00599b60`, L455602; unresolved in the tsv) calls
  `CZSealBody_PostCreateSeal` (`FUN_00599f00`, L455715; r0004 0x59fa20), which clears the kit (`FUN_005c72c0`) and, for
  each 12-byte entry of `type +0x2e8` (L455790-455836), adds the item (`FUN_005bdfb0(kit, i, id)`), then loads its
  rounds: `ammo_count x mag_count == 0` -> `FUN_005bde20(kit, i, round)` (the record's defaults), else
  `FUN_005bdec0(kit, i, round, count, mags)`. The kit is `CZKit` at character `+0x5e0`. Then `FUN_005c7840`
  (L480332; L455675 on a respawn, L419394 at creation) finalises: armour by 202/201 (`FUN_005a0da0` / `FUN_005a0cd0`,
  else `FUN_005a0c00`), `FUN_005c74e0` (the claymore's detonator, A1), **`FUN_005c75f0` (2X, A7)**, `FUN_005c77b0`
  (L480274: with C4 in the kit, `kit +0x8a0` from `FUN_005c6920`/`FUN_003d4510` -- reader (c)).
  `CZKit_Init` (0x5c7e00, L480556-480681; r0004 0x5cf510) only resets the kit's state (the thermal/scope camera object
  at `+0x884`, counters); it does not choose items.
- **The held models.** `CZSealBody_AddWeapon(SEAL_ITEM)` (0x553290, L419021-419061; r0004 0x5585b0) makes the attach node
  for held item kind 1/2/3 on the skeleton nodes named `rifle` (0x65c498), `pistol` (0x65c4a0), `grenade` (0x65c4a8),
  stored at body `+0x388 + kind x 8`; kind 1 and 2 swap to `+0x300` when `+0xf79` says that hand holds it. Called for
  kinds 1 and 2 at body setup (L419663-419664).
- **Online: the kit.** Each console sends its players' state in a 0x90-byte message (`FUN_002bd640` L161852-162070,
  r0004 0x2bf280; sent with `FUN_00195800` to the peer, L162068): the type name (`FUN_0053b420`), the current item
  (`FUN_005c89d0`), and at `auStack_bc` the kit from `FUN_0053ee10` -> `FUN_0053ed50` (L407397-407410): **up to 8 x
  {u16 `id << 8 | round id` (`FUN_003d1c70` L324360), u16 rounds a magazine, u16 magazines}**. The receiver rebuilds the
  type's kit with `FUN_0053ec60` (L407354-407378; stops at id 0), called at L455079 and L455445
  (`REMOTE_KIT_APPLY_PLACEHOLDER`: which object and when not traced). `FUN_0053ee10` takes the type named at
  `DAT_00437ce8 + 300`.
- **`SendWeaponPUMessage` (0x2ba660, L160013-160054; r0004 0x2bc270) is the weapon *pick-up* message**, not the pick:
  its only caller `FUN_00541700` (L408866-408905) sends it for a pick-up object of kind 8 (online only). Fields
  (0x18 bytes): `+0x00` u32 object key (`obj[4] << 16 | u16 obj+0xe`); `+0x04` u32 rotation, three euler angles each
  `clamp((a + pi) / 2pi, 0, 1) x 1023` packed x<<20 | y<<10 | z (`FUN_00307070` quat -> euler); `+0x08..+0x10` position
  x, y, z (f32); `+0x14` u16 item id (record `+0x7c`). Sent by `FUN_0030cef0(0x45a0c0, 0x40, DAT_0045a1b4, -1,
  DAT_00440e48, 0x18, &msg, 0)`; `DAT_0045a1b4` and `DAT_00440e48` are `.bss` (zero in the file, set at run time):
  `NET_PICKUP_MSG_TYPE_PLACEHOLDER`. The mangled name `SendWeaponPUMessage__FUsUsP6CPnt3DP5CQuat` (names CSV) agrees:
  (ushort id, ushort key, CPnt3D*, CQuat*).

### A7. Double Ammo Load (2X, id 194)

- **Where.** `FUN_005c75f0` (L480207-480270; r0004 0x5ced00), called by the kit finaliser `FUN_005c7840` (L480393) at
  every spawn and respawn, after the rounds are loaded.
- **What.** If any kit item (`kit +0xe4[i]`, count `+0x82c`) is 194, then for every kit item whose class
  (`FUN_003d1e10` -> `FUN_003d1a60`) is **pistol 4, SMG 0x1f, rifle 0x33, shotgun 0x51, MG 0x5b or sniper 0x65**:
  `n = NumMags` (`FUN_003d2800` = record `+0x2c`); magazines `n .. 2n-1` (each below 10) are set to magazine 0's
  count (`kit +0x1d4 + item x 0x28 + m x 4`: 10 magazine counters an item, reCOM's `m_reloads[30][10]`,
  `recom/src/gamez/zSeal/zseal.h:233-237`), and magazines `2n .. 9` to 0. So **NumMags doubles, capped at 10, the
  extra magazines full; `Ammo_Capacity` is unchanged**. Grenade launchers (0x8d), rockets, grenades, explosives and
  rounds are not doubled.
- **Refill and the HUD count agree.** `FUN_005ba3d0` (L472706-472775: add rounds to an item's magazines) and
  `FUN_005ba5b0` (L472779-472835: "has a magazine with room") both use `NumMags x 2` (capped 10) for the same classes
  when 194 is in the kit.
- On the disc every MP map enables 2X for both sides, and 44 of the 176 kits carry it.

### Placeholders (reader A)

Named stand-ins for what this reader could not source, or a choice among sourced readings. None is yet a constant in
code; M2/M9 take the names as they are.

| name | stands for | searched / readings | status |
|---|---|---|---|
| `INGAME_AUTOFILL_SIDE_READING` (in code: M2/M7) | the side mask the in-game auto-fill (`FUN_0023b9b0`, `FUN_0023bc50`) uses when a launcher, a cost-2 item or a sniper leaves and its dependents are refilled | read: decomp L87139-87170 / L87226-87260 and the MIPS at 0x23bbd0-0x23bbe8 (`player_team == 0 -> 8`); `player_team` writer `FUN_002c3330` L164814-164872 (SEAL -> 0); armory twins `FUN_00283b50`/`FUN_00283e60` use `0 -> 1`. Readings: (a) as shipped -- a SEAL's refill is drawn from Terrorist-bit items (a PMN could land in a SEAL's slot); (b) the player's own side, as the list itself (`FUN_0023c390`) and the armory do. Not observed on a console | open -- owner or a PCSX2 frame (drop an M4A1-M203 as a SEAL on MP1 and look at slots 2-3) |
| `ARMORY_LIST_FILTER_PLACEHOLDER` (*note only*) | how the front-end armory hides the other side's items in its list | `dlg_equipment_mp.rdr` names only `Equip<x>` buttons (`uidlg.ts`); code: `FUN_00280d60`, `FUN_00280e90`, `FUN_00284120`, `FUN_00282c20` (no `FUN_003cf1f0` call); `UIZANIM.ZAR` anim scripts not searched | open; the lobby is out of this sprint (spec section 6) |
| `REMOTE_KIT_APPLY_PLACEHOLDER` | which object a received kit (`FUN_0053ec60`) rebuilds and when the remote body picks it up | callers L455079 (inside `FUN_00598b90`'s range) and L455445; not traced further. Web sprint 4 M9: the page takes each player's kit at its `spawn` (protocol 7 names it) and the welcome's list, and hangs at once the item a snapshot says is in the hand (`packages/viewer/src/remotePlayers.ts`) | open; the viewer's server owns the kit (W4.R6), so it is only needed for 1:1 remote timing |
| `NET_PICKUP_MSG_TYPE_PLACEHOLDER` (*note only*) | `DAT_00440e48` (message type) and `DAT_0045a1b4` passed to `FUN_0030cef0` by `SendWeaponPUMessage` | both `.bss` in the retail ELF (`elfread.py word` -> bss), set at run time | open; dropped-weapon pick-ups are not in this sprint's scope |
| `SPAS_SP_VALVE_PLACEHOLDER` (*note only*) | the prep's `Spas 12` valve spelling | all 22 MP maps say `Enable_spas`; single-player `M61.ZDB` is not in the archive | not needed for MP |
| `POUCH_PLACEHOLDER` (`room.ts` `THROWN`) | the throwables a player carries in a match: the viewer's pouch (M67, HE, AN-M8, Mark141, each at its record's `capacity`) whatever the loadout's equipment slots hold; replaces research 91's `KIT_PLACEHOLDER` for the throwables once the firearms follow the loadout (M3/M4) | the kit's equipment slots are read (`Loadout` slots 2-4, research 91 §14); the grenade code (`viewer/src/grenade.ts`, research 85) is not yet driven by them | open -- web sprint 4 M7 (the equipment) |

Settled here that earlier notes left open: the id-to-valve map (all 68 arms, A2); bit 16 (C4 locked in a SEAL kit,
32 the Terrorist twin, A3); lookup case-sensitive (A2); `SlotCost` (A5.4); 2X (A7); research 91 section 14's kits
verified (A4). `DEFAULT_CHARTYPE_PLACEHOLDER` (research 91) is untouched by this reader: no code read here picks a
type for a player who never chose one.

## 2. The in-game weapon select, "WEAPON EXCHANGE" (reader b)

Reader (b), web sprint 4 M1. Read-only. Sources, all relative to the archive root the handoff archive root:
`analysis/socom2_game.elf.decomp.c` (retail Ghidra, cited `L<line>`), `analysis/elf/socom2_game.elf` (retail ELF: `.data`/`.rodata`
read by a Python walk of the ELF's PT_LOAD headers -- the third segment maps vaddr `0x1e7000` to file offset `0xd6600`; words and
floats little-endian; strings NUL-terminated), `recomp/retail/output/*.cpp` (the MIPS comments; used for the undecompiled stubs and
the BSS static initializer), `analysis/demo/SCUS_972.05` (DWARF1 through ccc `stdump symbols --section .debug dwarf`, ccc
c025ca9 built with CMake in `tools/ccc`, 116,691 DIEs, and `readelf -s` on its `.symtab`), `recom/src/Apps/FTS/hud/hud.h`
(reCOM, declarations only), the disc `disc/RUN/READERC.ZAR` (`controller.rdr`, `HudCLOC.rdr`) and `disc/RUN/MP2.ZDB`
(`COMMON/HUD2_TXR.ZED`, `COMMON/HUDW_TXR.ZED`) through the repository's `packages/archive` reader (probes
`probe/b-menu.ts`, `probe/b-tex.ts`, run with `npx tsx` from `web/redotcom`). Only names, numbers,
offsets and ids are quoted; the short UI strings are the ones the brief and research 91 already quote.

**Headline.** `CInGameWeaponSel` is **dead code in SOCOM II**. It is constructed, `Init`ed (its textures and sounds loaded) and
`UnInit`ed with the HUD, but its vtable's tick is an empty `jr ra`, nothing ever sets its open state, and its textures are not
on the disc. The dead player's "Select new weapons" menu is a different, unnamed HUD block at `CHUD+0x38e0`, built from the RTTI
classes **`SlotList`, `CWeaponSlot`, `SelectedSlot` and `CategorySlot`**. Its title is **"WEAPON EXCHANGE"** (0x3e6cb0). It
exists **online only**, opens on the **`Inventory`** button (R2 in the Default config), and has **two screens**: a 5-row slot
list and a category/item picker. It writes the pick into the player's character-type loadout, and **the next round's
rebuild** applies it. It plays **no sound**. It draws no description, stats or ammo, and it does not offer the character
type. The seven `newweapnbkrnd.tif` loaders in the brief are all *other* HUD parts. The menu loads its own copy of the name
(0x3e6c40) in `FUN_0023cd20` and `FUN_00240e60`.

---

### B0. Answers in one table

| question | answer | source |
|---|---|---|
| Is `CInGameWeaponSel` the menu? | **No.** Vestigial in SOCOM II: vtable 0x405150 overrides only the dtor; its +0x34 tick is `FUN_001fe320` = `jr ra`; open state `+0x1128` is written only by ctor/Init (0) and UnInit (6, 7 inside `if (+0x1128 != 0)`); its textures `weapon_selection.tif`, `hud_weapon_selected_on.tif`, `reticuletex.tif`, `hud_arrow_off.tif` are absent from MP2's HUD libraries | vtable read from ELF 0x405150; `recomp/retail/output/FUN_001fe320_0x1fe320.cpp`; `FUN_00227960` L77704; `FUN_00227ad0` L77747; probe `b-tex.ts` |
| What is the menu? | The block at `CHUD+0x38e0`: ctor `FUN_00241a90` L89842, Init `FUN_00240e60` L89585 (online only, called L57439), tick `FUN_00240600` L89343, state change `FUN_00240b90` L89503, UnInit `FUN_00240d50` L89553; sub-objects `SlotList` (vtbl 0x405e80), `SelectedSlot` (0x405d00, base `CWeaponSlot` 0x405e00), `CategorySlot` (0x405d80) | RTTI names read through vtable word 0 -> RTTI -> name (ELF) |
| Its title | "WEAPON EXCHANGE" (0x3e6cb0) | `FUN_0023e030` L88293 |
| When it opens | Online match, local player **not alive** (`+0xe1` bit 4 clear), camera on **himself** (`DAT_00415ff0+0xbc` == local), not a spectator (`FUN_002c2fa0()==0`), HUD mode `controller+0x221` < 2, a local pad (`DAT_0044f108`), press of `Inventory` | `FUN_001f7ff0` L56648-56661; `FUN_00240600` L89369-89374 |
| Classic vs respawn | Classic (respawn off): prompt "You have died.  %c Select new weapons." + the teammate-cycle lines. Late joiner (ghost, game `+0xd2`): the ghost lines with the same `%c`. Respawn (game `+0xdc`): adds "Press the %c button to respawn" after 5 s -- **respawn-only, not wired (W4.R7)** | `FUN_001f97b0` L56978-57138 |
| Before the round / at a spawn? | **No.** Alive, the same button opens `CWeaponSel` (the in-hand inventory, `CHUD+0x1a50`) instead; the menu is never offered pre-round or at a spawn | `FUN_001f7ff0` L56655-56661; `FUN_00219c80` L71600 |
| `%c` glyph | `FUN_002c6430(4)` = the config's button slot for result 4 `Inventory`; slot 11 (R2) -> **0xbe**, else **0xbd** (R1 in the "Goldeneye" config, the only one not on R2) | L56997-57001, L57050-57055; `controller.rdr` probe |
| Pad inside | Up/Down move; Left/Right change category (picker); **Action** (X; Circle in Goldeneye) = select/confirm; **Triangle** or **Start** = back/close; `Inventory` (R2) also closes the slot list. **Circle is not cancel.** One step per press, no auto-repeat | `FUN_0023ebc0` L88581; `FUN_0023d1b0` L87851; pad slot map `L179820-179862` |
| Screens | S-list (5 rows: primary, sidearm, equip 1-3) and S-picker (category header, 3 item cards prev/current/next) side by side at x -10..340, y 105..365 | §B4, §B5 |
| Locked / unavailable | A slot whose item may not be swapped is drawn (40,40,40) and skipped by the cursor (`FUN_0023e910`); items the side/slot rules refuse are never listed (`FUN_0023c390`) -- no padlock, no greyed item | L88476, L87356 |
| Per item drawn | DisplayName (upper-cased) and the `IconTextureName` icon at native size; **no** description, stats, ammo type or counts | `FUN_0023c0d0` L87289; `FUN_0023bf60` (recomp) |
| Character type offered? | **No** (nothing in the module reads or writes a type); the type stays the server's (`DEFAULT_CHARTYPE_PLACEHOLDER`) | module L86857-90043 |
| Default-kit choice | None in-round; the lists open on the kit you have (`character+0x540` weapons). `UIChooseDefaultEquipmentOnly` is the lobby armory's | `FUN_0023e370` L88306 |
| Sounds | **None**: no sound call in the module. (`CInGameWeaponSel_Init` loads `.TCM_SELECT`/`.TCM_SLIDE` but never plays them) | grep of L86283-90450; L78001-78006 |
| Timings | fade in/out 0 <-> 100 at 400/s (0.25 s); slot highlight pulse 4/s; card highlight pulse 4/s; picker arrows pulse 2/s; prompt lines hold 10 s then fade 0.5 s | `DAT_003dce78/98`=400, `DAT_003dce80/a0`=100, `DAT_003dce70/90`=4, `DAT_003dcea8`=2; L56544-56561 |
| When the pick applies | Confirm writes all 5 slots into the player's character-type record at once (`character+0x540` -> `+0x2f0`, `FUN_0053eee0`); in classic the next round's `FUN_00223680` L75931 -> `FUN_00598b90` -> `FUN_00599b60` -> `FUN_00599f00` L455674 rebuilds the kit from it; the round reset then closes the menu (`FUN_002a7d40` -> `FUN_001fb790` -> `FUN_00240d50`) | `FUN_0023e5e0` L88379; L75931, L149757 |
| How it is sent online | **Not by the menu.** `SendWeaponPUMessage` 0x2ba660 is the dropped-weapon pick-up (message 0x40, caller `FUN_00541700` L408904), not the loadout. No net code calls `FUN_0053eee0`/`FUN_0053b3a0`; the path to the other consoles is `PICK_WIRE_READING` | L160011, L408904; caller list of `FUN_0053eee0` |
| Validation | Per item `FUN_0023c390` (slot class + category + no duplicates + side mask: valve `& (FUN_002c30b0(me) ? 8 : 1)` via `FUN_003cf1f0`); `FUN_0023b9b0`/`FUN_0023bc50` are "next enabled item" finders used to refill launcher-ammo slots, not list builders | L87356-87487; L87104-87272 |
| PC key / touch | Not the game's. Proposed `I`, for the owner to decide: `WEAPON_SELECT_KEY_READING` / `WEAPON_SELECT_TOUCH_READING` | §B3 |

---

### B1. The classes: methods, vtables, members

#### B1.1 `CInGameWeaponSel` (demo DWARF) and where each method went in SOCOM II

The demo's `.symtab` (`readelf -s`) has **31** functions of the class (29 named member-function DIEs in `.debug`, plus
`__ct__` and `__dt__`; research 55 counts 31 too). The "56 methods" in research 50's table was not reproduced: `grep -o
'name="[^"]*16CInGameWeaponSel[^"]*"'` over the whole DIE dump gives each name once, and the vtable and RTTI twice. Demo vtable
`__vt__16CInGameWeaponSel` 0x474280 (92 bytes), class size 0x1160, 45 members.

| demo method (address, bytes) | SOCOM II retail | how |
|---|---|---|
| `Init(CWorld*, C2DFont*)` 0x3fc5c0, 2660 | **0x227ad0** `FUN_00227ad0` L77749, 2524 | names CSV (string-set 0.80); layout match below |
| `__ct__` 0x3fd030, 760 | **0x2284c0** `FUN_002284c0` L78019 | sets vtbl 0x405150; called `CHUD` ctor L58374 |
| `__dt__` 0x3bcd40, 324 | **0x1fd8c0** L58681 | vtable +0x08 (research 44 matched the same address) |
| `UnInit` 0x3fc450, 368 | **0x227960** `FUN_00227960` L77706, 368 | same size; called from `CHUD` UnInit `FUN_001fb790` L57682 |
| `Clear` 0x3fc360, 232 | 0x227880 `FUN_00227880` L77674, 224 [inferred by size and role: vtbl+0x8c on every text] | called only by 0x227960 |
| `AfterClose` 0x3fa610, 332 | 0x227730 `FUN_00227730` L77628, 336 [inferred: hides all, controller mode 0, `+0x1128`=0] | called only by 0x227960 |
| `SwitchOffText` 0x3f8eb0, 232 | 0x227650 `FUN_00227650` L77596, 224 [inferred: hides the texts] | called only by 0x227960 |
| `UpdateCharacter` 0x3f8000, 184 (or `RePackEquipment`) | 0x227560 `FUN_00227560` L77567, 232 [inferred: writes `m_selected_item_index` +0x11a4 into the kit via `FUN_0053eee0`] | called only by 0x227960 |
| `HudTick`, `HandleOpenState`, `HandleScrollUp/DownState`, `OnOpen`, `OnScrollUp/Down`, `AfterOpenFirst/Second`, `AfterScrollUp/Down`, `AfterCloseFirst`, `SelectWeapon`, `SelectEquipment`, `CanSelectWeapon`, `IsSelected`, `GetNextItem`, `GetPrevItem`, `PlaceWeaponText`, `SetItemPos`, `Increment`, `PulseSelectionArrows`, `RePackEquipment` | **absent** | 0x227560..0x2284c0 hold only the six above; the neighbours are other classes (0x227340 inits `CHUD+0x17580` L57287; 0x228660 is vtbl 0x405840's dtor) |

The retail vtable, 0x405150 (read from the ELF): word 0 RTTI 0x3e3760 -> name 0x3e3720 "CInGameWeaponSel". It has 26 slots,
all inherited except +0x08, the dtor 0x1fd8c0. +0x0c is 0x364e70 and +0x34 is `FUN_001fe320`, an empty `jr ra`. The rest
are the HUD base stubs 0x1fe1b0-0x1fe330 and 0x364xxx.

The retail layout is the demo layout +0x58 from `m_weaponselbkrndtex` on. The Init and ctor writes line up: `m_weaponselbkrndtex`
+0x10f8 = `weapon_selection.tif` (0x3e5570), `m_weapontex[4]` +0x10fc = `reticuletex.tif`, `m_selectionbacktex[4]`
+0x110c = `hud_weapon_selected_on.tif`, `m_arrowtex` +0x111c = `hud_arrow_off.tif`, `m_myfont` +0x1120, `m_current_item`
+0x1124, `m_openstate` +0x1128, `m_iconoffsetx/y` +0x1134/+0x1138 = 4.0, `m_menuposx[1]` +0x1148 = 30, `m_menuposy[1]` +0x1158 = 200,
`m_curcolor` +0x1184 = 1.0, `m_arrowcolor` +0x118c = 50, `m_selectsound` +0x1194 = `.TCM_SELECT`, `m_scrollup/downsound`
+0x1198/+0x119c = `.TCM_SLIDE`, `m_cursound` +0x11a0 = -1, and `m_selected_item_index[5]` +0x11a4 (bytes). The text slots
"3", "2", "1", "4testing" (0x3e55c8-0x3e55e0) are SOCOM 1 leftovers. The four textures are absent from `MP2.ZDB`'s
`HUD2_TXR`/`HUDW_TXR`/`WSMP_TXR` (probe `b-tex.ts`).

**`CWeaponSel`** (RTTI 0x3e4aa8, vtable 0x405610; `CHUD+0x1a50`, Init `FUN_0021cd40` L72977, tick `FUN_00219c80` L71600) is the
**alive** R2 inventory, research 85 §9.1. Its tick runs when the local player is alive and viewing himself, and it closes at death
(L56633-56636). The INVENTORY's "front end has `CWeaponSel`" is wrong: the class sits in the HUD.

#### B1.2 The weapon-exchange block (`CHUD+0x38e0`), members as far as they matter

Offsets are from the block (ctor `FUN_00241a90` L89842, Init L89585); "P" marks the picker sub-block at +0x220 (Init
`FUN_0023cd20` L87734).

| offset | what | evidence |
|---|---|---|
| +0x0 (byte) | **menu state**: 0 closed, 2 slot list, 3 picker | `FUN_00240b90` L89503 writes it; tick switch L89368-89397 |
| +0x4 | title text (C2DString; +0x69 of it = centred) | `FUN_0023e030` L88293-88300 |
| +0xa0 / +0x120 | title panel / body panel sprites (`newweapnbkrnd.tif`) | L89609-89614, L88258-88265 |
| +0x1a0 | slot highlight sprite (`newweapnbkrnd.tif`) | L89615, L88266-88270 |
| +0x220 (P+0x0) | picker header text (category name) | `FUN_0023d860` L88111-88139 |
| P+0xa0 / P+0x120 | picker header panel / body panel | L87761-87766 |
| P+0x1a0, +0x390, +0x580, +0x770 | 4 arrow quads (`hud_arrow_off2.tif`), stride 0x1f0 | L88147-88160 |
| P+0x960 | `SlotList` of 4 `CategorySlot` pointers (+0x980..+0x98c -> cards at P+0x9a0, +0xae0, +0xc20, +0xd60, 0x140 each) | L87797-87800 |
| P+0xea0 (= +0x10c0) | middle-card highlight sprite | L87767, L88203-88205 |
| P+0xf20 / +0xf21 / +0xf22 / +0xf24 | category id (0xff = ALL) / slot class (0 primary, 1 sidearm, 2 equipment) / picker sub-state (3 active, 1 confirm, 2 cancel) / current index in the weapon list | `FUN_0023d540` L87972; `FUN_0023d1b0` L87851 |
| P+0xf28 / +0xf2c | arrow pulse t / direction | `FUN_0023d2b0` L87887 |
| +0x1154 / +0x1158 | card highlight pulse direction / t | L89468-89487 |
| +0x1160 | `SlotList` of the 5 rows (+0x1180..+0x1190 -> rows) | L89598-89603 |
| +0x1194 | current slot index 0..4 | `FUN_0023eae0` L88551 |
| +0x1198 + 0xb8 i | 5 `SelectedSlot` rows; row +0x18 (= +0x11b0) the item record | `FUN_0023e370` L88306 |
| +0x1530/+0x1531 | remembered equipment ids (the launcher-ammo unwind) | `FUN_0023fef0` L89138; `FUN_0023eca0` L88610 |
| +0x1532/+0x1533/+0x1534 | a launcher host is carried: M203 family / id 0x3f family / id 0x8f family (gates the `LAUNCHED` category and the `Enable_203*`, `Enable_F2000*`, `Enable_GL*` valves, set to 9) | L89613-89835; L87825 `FUN_0023d060` |
| +0x1538/+0x153c | slot highlight pulse direction / t | L89401-89414 |

---

### B2. When it opens

The HUD tick `FUN_001f7ff0` (L56515) decides per frame. `iVar4` is the local player (`FUN_002b3580` = `DAT_00440c38`),
`iVar2` the camera's target (`DAT_00415ff0+0xbc`), and `bVar1` the controller's HUD mode `+0x221`:

- **Help lines** (the state switch L56563-56600, as research 91 §318 reads it). Local alive and viewing self: hidden. Viewing
  someone else: `FUN_001f9f20` ("You have died.  Use the <glyph> and <glyph> ..." + "living teammates", 0x3e3430/0x3e3450/0x3e3410).
  Dead offline: `FUN_001f93c0`. Dead online, not a spectator, viewing self: **`FUN_001f97b0`**. A spectator: `FUN_001f9160`.
- **Menus** (L56648-56661). If `pad` exists, `bVar1 < 2`, and the game is offline or the local player is not a spectator:
  alive and viewing self runs `FUN_00219c80` (`CWeaponSel`). Otherwise, **online and viewing self** runs `FUN_00240600`
  (**the exchange menu**).
- **Death edge** (L56630-56645). When the target's alive bit falls, `CWeaponSel` is closed (`FUN_0021b3e0`, `FUN_0021b0a0`,
  `FUN_0021aaa0`, `FUN_0021a510`) and the help-line timer `CHUD+0x1a0e8` is zeroed. The lines then hold 10.0 s and fade
  out over 0.5 s (L56544-56561).

`FUN_001f97b0` (L56978), the dead player's prompt, in its branches:

| game flag | lines (the 6 help lines, x 324, baseline 380 + 18 i) | wired? |
|---|---|---|
| `+0xd2` = 0, `+0xdc` = 0 (**classic**) | L1 "You have died.  %c Select new weapons." (0x3e32e0, `%c` = 0xbe/0xbd); L2 0x3e3350 (the two d-pad glyphs 0xa3/0xaf); L3 "to cycle through living teammates" (0x3e3380) | **classic: yes** |
| `+0xd2` != 0 (**ghost**, a late joiner; research 91 L240) | L1 0x3e31c0 "You are a ghost.  You will play the next"; L2 0x3e31f0 "round as a real player.  %c Select new" (same glyph); L3 0x3e3280 "weapons. Use the <a3> and <af> directional"; L4 0x3e32b0 "buttons to cycle through living teammates." | classic: yes (the page already posts ghost lines, research 91 L882) |
| `+0xdc` != 0 (**respawn**) | L2 becomes "Press the <0xa6 / 0xb7> button to respawn." (0x3e3310 / 0x3e3330) once 5.0 s have passed since death, the body has faded (`+0x9c` == 0), and the player is not a spectator; else blank. The ghost variant uses 0x3e3220/0x3e3240 | **respawn-only, record, not wired (W4.R7)** |

With `param_2` (the HUD mode) != 3, `FUN_001f97b0` calls `FUN_001f7a90` (L57112): the HUD is shown and, if the menu is open,
`FUN_0023e800` re-shows and redraws it every frame (L56401). Mode 3 hides everything (`FUN_001f77c0`, which calls
`FUN_0023e700` L88413).

**Not offered:**

- **Alive:** before the round, in the round, or at a spawn. `Inventory` opens `CWeaponSel` instead.
- **Offline:** `FUN_00240e60` runs only `if (DAT_0045a0c1 != 0)` (L57438-57440), and the tick sits behind the same flag.
  The page's offline match stands in for an online one, so it offers the menu there.
- **Spectators:** `FUN_002c2fa0() != 0`.
- **Following a teammate:** the camera target is not self, so the tick stops. `FUN_001f9f20` -> `FUN_001f77c0` hides the
  menu's parts but keeps its state, and returning to self shows it again.

HudCLOC's unused id 60488 (`_60488_YOU_HAVE_DIED_LINE_3_MSG`, "...R2 button to select weapons for the next round") states the
intent. No code references 0xec48, and 60486 (0xec46) is only the lines' initial text (L57297).

---

### B3. How: the button, the glyph, the input

**The pad's button slots** (`FUN_002c6670` L167009 names them; `L179820-179862` fills them from libpad2's digital/pressure
indices). The pad state byte for slot n sits at `pad+1+n`: 0 up, **1 just pressed**, 2 held, 3 just released (`FUN_002d9ff0`
L179130).

| slot | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| button | Start ("Pause") | Select | Right | Left | Up | Down | Triangle | Circle | Square | X | R1 | R2 | L1 | L2 | R3 | L3 |
| pad byte | +1 | +2 | +3 | +4 | +5 | +6 | +7 | +8 | +9 | +10 | +11 | +12 | +13 | +14 | +15 | +16 |

Slots 2-6 are paired with the pressure indices 0x14-0x18 in libpad2's order (Right, Left, Up, Down, Triangle). The named
slots 7-15 match `FUN_002c6670`'s names exactly. This also settles research 91's `SPECTATOR_PAD_PLACEHOLDER` bytes: +5 Up,
+6 Down, +7 Triangle, +10 X.

**The open button.** The result is 4, `Inventory`: `FUN_002c64e0(4, pad) == 1` (L89371), the config's `+0x12+4` byte picking
the slot. `controller.rdr` (probe `b-menu.ts ctl`): `Default`, `Reverse` and `Config4` bind **R2** to `Inventory` and X to
`Action`; `Goldeneye` binds **R1** to `Inventory` and **Circle** to `Action`.

**The glyph.** `FUN_002c6430(4)` (L166868) reads `DAT_004415b0+0x12+4`: 11 (R2) gives 0xbe, anything else 0xbd (L56997-57001).
So in the font 0xbe = R2 and 0xbd = R1 [inferred from the configs]. By the same test the respawn line's 0xa6 is X and 0xb7 is
Circle, since Goldeneye's `Action` is Circle; research 91 had 0xb7 as "Sure Shot". Research 91 reads 0xa3/0xaf as the
d-pad glyphs [inferred: Up/Down, the teammate-cycle bytes +5/+6].

**Input inside the menu.** Every step fires on `== 1` (just pressed): **no auto-repeat and no repeat timer**.

| state | Up (+5) | Down (+6) | Left (+4) | Right (+3) | Action (result 0: X; Circle in Goldeneye) | Triangle (+7) / Start (+1) | Inventory (result 4) |
|---|---|---|---|---|---|---|---|
| closed (0) | -- | -- | -- | -- | -- | -- | **open** -> 2 (`FUN_00240b90(,2)` -> `FUN_0023e370`) L89371-89373 |
| slot list (2) | previous selectable slot (wraps 4 -> 0) `FUN_0023eae0(-2)` L88591 | next selectable slot | -- | -- | **picker** -> 3 L88599 | **close** -> 0 L88603 | **close** -> 0 L88602 |
| picker (3) | previous item in the category (wraps) `FUN_0023d060(-2)` L87862 | next item L87865 | previous non-empty category L87868 | next non-empty category L87871 | **confirm**: sub-state 1 -> apply -> 2 L87879, L89390-89395 | **cancel**: sub-state 2 -> 2, no change L87874 | -- (ignored) |

While the menu is open the controller's HUD mode `+0x221` is 1: `FUN_00597740(ctrl, 1, 0)` at open (L88370), 0 at close
(L89516). Mode != 0 blocks the respawn press (`FUN_00592560` L451673-451675) and the spectator camera's buttons (`FUN_00295260`
L139475). The dead player's teammate cycle under mode 1 was not traced: `DEAD_CYCLE_WHILE_MENU_READING`.

**The PC key and touch control (for the owner; not the game's).**

- `WEAPON_SELECT_KEY_READING`: propose **`I`**. The game's own name for the button is `Inventory` (`controller.rdr` result 4).
  `I` is bound nowhere in `packages/viewer/src`: every `code === '...'`/`'Key.'` binding was grepped, and the page binds W A S D,
  Space, Shift, R, B, C, X, Q, E, 1-5, Tab, M, Esc, G, F, backtick, K (the vote menu, `netPage.ts:169`), V (spectate follow,
  `netPage.ts:186`), the arrows and Home/End. `I` is also away from the movement keys.
- `WEAPON_SELECT_TOUCH_READING`: an on-screen button shown only while the prompt line is, labelled like the prompt, with the
  rows and cards tappable once open.
- The keys inside the menu are a third reading, `WEAPON_SELECT_MENU_KEYS_READING`: W/S or ArrowUp/Down for Up/Down, A/D or
  ArrowLeft/Right for Left/Right, **X** or Enter for Action (the page's X is already "action"), and Backspace for Triangle,
  with `I` closing the list as `Inventory` does. Esc is left alone because it releases the mouse.
- On the pad the viewer keeps the game's buttons: R2 opens, Cross confirms, Triangle or Start backs out. R2 alive stays the
  viewer's inventory step.

---

### B4. Every screen and state -- the STATE TABLE

(Coordinates on the 640x448 HUD frame; details and sources for each drawn element in §B5.)

| # | state | entry condition | what is drawn | inputs -> transitions | exit | source |
|---|---|---|---|---|---|---|
| S0 | **alive** | local `+0xe1` bit 4 set | normal HUD; `Inventory` opens `CWeaponSel` (not this menu) | -- | death edge closes `CWeaponSel`, starts the 10 s prompt timer | L56630-56661 |
| S1 | **dead, prompt** (menu state 0) | online; local dead; camera on self; not a spectator; mode < 2 | the HUD (`FUN_001f7a90`); help lines L1-L3 (classic) or ghost L1-L4, x 324, baselines 380/398/416/434, scale 0.9, (100,100,20) alpha 100 (L57301-57303, L56546; `PROMPT_COLOUR_READING`), fading after 10 s | `Inventory` -> S2; Up/Down (teammate cycle) -> S6 | round reset (S8); camera leaves self (S6) | `FUN_001f97b0` L56978; tick L89368-89374 |
| S1g | ghost prompt | as S1 with game `+0xd2` != 0 | ghost lines (0x3e31c0, 0x3e31f0, 0x3e3280, 0x3e32b0) | as S1 | as S1 | L57047-57062 |
| S1r | respawn prompt | as S1 with game `+0xdc` != 0 | + "Press the %c button to respawn." after 5 s | Action -> respawn (not wired) | respawn | L57008-57030, L57064-57096 -- **respawn-only, not wired (W4.R7)** |
| S2 | **slot list** (state 2) | from S1 by `Inventory`; from S3 by confirm or cancel | title panel + "WEAPON EXCHANGE"; body panel; 5 rows (DisplayName) at x 12, baselines 161/181/201/221/241; row colour (128,128,128), or (40,40,40) if the slot is locked; highlight bar on the current row pulsing (80,120,120)<->(160,250,250) at 4/s. **The picker panel is drawn too** (redrawn every frame by `FUN_0023e800`) as a preview of the highlighted slot's category and items, arrows grey (100,100,100), no card highlight. Fade-in 0 -> 100 at 400/s | Up/Down: slot -/+1, skipping locked slots, wrapping 0..4 (the picker re-seeds to that slot's item: `FUN_0023d540`); Action -> S3; Triangle / Start / `Inventory` -> S1 | `FUN_00240b90(,0)`: card highlight hidden, mode 0; parts fade 100 -> 0 at 400/s then hidden (L89439-89452) | `FUN_0023ebc0` L88581; `FUN_0023e030` L88247; `FUN_0023e370` L88306 |
| S3 | **picker** (state 3, sub-state 3) | from S2 by Action | as S2, plus: picker parts shown; the middle-card highlight x 170..340, y 226..290 pulsing (80,120,120)<->(160,250,250) at 4/s; arrows pulsing (80,80,80)<->(255,255,128) at 2/s; the slot bar solid (160,250,250). Header = the category name or "ALL ..."; 3 cards: previous, **current** (middle), next | Up/Down: item -/+1 within the category (wraps through the whole weapon list, skipping refused items); Left/Right: category -/+1 (skips empty ones; `LAUNCHED` only with a launcher host); Action -> S4; Triangle / Start -> S2 (no change) | S4 or S2 | `FUN_0023d1b0` L87851; `FUN_0023d860` L88080; `FUN_00240b90(,3)` L89525-89540 |
| S4 | **confirm** (transient) | S3 + Action | -- | `FUN_0023fef0(menu, slot, middle card's item)`: unwind the old item's dependants (`FUN_0023eca0`), set the slot, a 2-slot item (`record+0x27c == 2`) fills the next equipment slot with the placeholder item (0xfe; 0xb9 for 0x91, 0xba for 0x92), a launcher host auto-fills its ammo into equipment slot 2 (and 3). Then `FUN_0023e5e0` writes **all 5** into `character+0x540` -> `+0x2f0` (`FUN_0053eee0`) | -> S2 | L89389-89395; L89138; L88379 |
| S5 | **locked slot** (row attribute) | the slot's item is 0x8d or 0xfe; 0xb9/0xba without a second slot of the same; or 0x97 while `Enable_c4`'s value & (0x10 SEAL / 0x20 Terrorist) | row in (40,40,40) | skipped by Up/Down | -- | `FUN_0023e910` L88476 |
| S6 | **hidden** (state kept) | the camera leaves self (teammate cycle) or HUD mode 3 | menu parts hidden (`FUN_001f77c0` -> `FUN_0023e700`); the lines change to `FUN_001f9f20`'s | no menu input (tick not called) | back on self: shown again (`FUN_0023e800`) | L56573-56590; L88413 |
| S7 | **spectator** | `FUN_002c2fd0(me)` | spectator lines (0x3e30f0..0x3e3180) | no menu | -- | `FUN_001f9160` L56861 |
| S8 | **round reset** | the round ends (game state 3/5) | -- | every player without `+0xfd1` is rebuilt from `+0x540` (the pick lands here, classic); then HUD UnInit -> `FUN_00240d50` -> state 0, mode 0 | next round, alive: S0 | `FUN_00223680` L75920-75936; `FUN_002a7d40` L149757; L89553-89580 |

---

### B5. Layout on the 640x448 frame

**The texture and colour calls, and the BSS table.**

- **Panels.** Every panel is `newweapnbkrnd.tif` (`COMMON/HUD2_TXR.ZED`, 128x64, in every MP map) stretched whole:
  `FUN_003646d0(x0, y0, x1, y1, sprite, tex)`, then `FUN_00364830(0, 1, 1, 0)` for the UVs.
- **Tint.** `FUN_00364930(r, g, b)` sets the tint on the PS2's 0-128 scale.
- **Where the positions and colours live.** They sit in BSS globals that the static initializer `FUN_003ff7f0` writes at boot.
  Its instructions were read from `recomp/retail/output/FUN_003ff7f0_0x3ff7f0.cpp` (`lui` immediates and `.rodata` loads at
  0x3dcd88-0x3dcdb0):

| global | value | global | value |
|---|---|---|---|
| 0x4146c0/c4/c8 | 80, 80, 80 (header panels) | 0x4146d0/d4/d8 | 128, 128, 128 (body panels) |
| 0x414710/14/18 | 128, 128, 64 (picker header text) | 0x414780/84/88 | 128, 128, 64 (title text) |
| 0x414730/34/38 | 11, 45, 64 (slot bar at draw; the tick overrides it) | 0x414758/5c/60 | 11, 45, 64 (unused here) |
| 0x414790/94/98 | 80, 120, 120 (pulse low) | 0x4147a0/a4/a8 | 160, 250, 250 (pulse high) |
| 0x414770 | -10 (slot-list x) | 0x414768 | -10 (bar x) |
| 0x414700/28/50 | 170 (widths) | 0x4146e0/f0/0x414708/40 | 170 (picker x) |
| 0x4146e8 | 140 | 0x4146f8 | 168 (cards' base y) |
| 0x414720 | 64 (card highlight h) | 0x414748 | 226 (card highlight y) |

The `.rodata` constants (0x3dcd80-0x3dcef0, floats in 8-byte slots):

| constant | value | constant | value |
|---|---|---|---|
| `DAT_003dcd80` | 110 | `DAT_003dcd88` | 170 |
| `DAT_003dcd90` | -10 | `DAT_003dcd98` | 140 |
| `DAT_003dcda8` | 14 | `DAT_003dcdb0` | 64 |
| `DAT_003dcdb8` | 225 | `DAT_003dcdc0` | 105 |
| `DAT_003dcdc8` | 35 | `DAT_003dcdd0` | 1.0 |
| `DAT_003dcdd8` | 129 | `DAT_003dcde0` | 18 |
| `DAT_003dcde8` | 146 | `DAT_003dcdf0` | 105 |
| `DAT_003dcdf8` | 129 | `DAT_003dce00` | 35 |
| `DAT_003dce08` | 1.0 | `DAT_003dce10` | 20 |
| `DAT_003dce18` | 10 | `DAT_003dce20` | 159 |
| `DAT_003dce28` | 0.9 | `DAT_003dce30/38` | 168 / 105 |
| `DAT_003dce40/48` | 305 / 105 | `DAT_003dce50/58` | 200 / 344 |
| `DAT_003dce60/68` | 200 / 140 | `DAT_003dce70` | 4 |
| `DAT_003dce78` | 400 | `DAT_003dce80` | 100 |
| `DAT_003dce88` | 167 | `DAT_003dce90` | 4 |
| `DAT_003dce98` | 400 | `DAT_003dcea0` | 100 |
| `DAT_003dcea8` | 2 | `DAT_003dceb8/c0` | 4 / 2 |
| `DAT_003dcec8/d0` | 2 / 2 | | |

| element | texture / string | rect or pen (x, y) | tint / scale / font | alpha | source |
|---|---|---|---|---|---|
| title panel | `newweapnbkrnd.tif` | x -10..160, y 105..140 | (80,80,80) | fade | `FUN_00240e60` L89609; `FUN_0023e030` L88258 |
| title | "WEAPON EXCHANGE" (0x3e6cb0) | centred on x 75 (= -10 + 170/2), baseline 129 | (128,128,64), scale 1.0, HUD font (`CHUD+0x498`: `font_text_01`, fallback `arialblack`, L57267-57276) | fade | L88293-88300 (`+0x69` centred, research 87 L263) |
| slot body | `newweapnbkrnd.tif` | x -10..160, y 140..250 | (128,128,128) | fade | L89612; L88262 |
| slot bar | `newweapnbkrnd.tif` | x -10..160, y 146 + 20 i .. 164 + 20 i | S2 pulse (80,120,120) + (80,130,130) t, t 0..1..0 at 4/s; S3 (160,250,250) | fade | L88266-88270; L89398-89429 |
| 5 rows | the slot item's DisplayName (`record+8`), upper-cased (`FUN_001fcd00` -> `FUN_0019afd0` per char [inferred toupper]) | left-aligned, pen (12, 161 + 20 i), i 0 primary, 1 sidearm, 2-4 equipment | (128,128,128), or (40,40,40) locked; scale 0.9 | fade | `FUN_0023e030` L88271-88288; `FUN_0023bf20`/`FUN_0023bf60` (recomp, +2/+2 from `DAT_003dcec8/d0`) |
| picker header panel | `newweapnbkrnd.tif` | x 170..340, y 105..140 | (80,80,80) | picker fade | `FUN_0023cd20` L87761; `FUN_0023d860` L88106 |
| picker header | category (`FUN_003d17d0`: PISTOLS, SMGS, ASSAULT RIFLES, SHOTGUNS, MACHINE GUNS, SNIPER RIFLES, HEAVY WEAPONS, GRENADES, LAUNCHERS, EXPLOSIVES, LAUNCHED, MISSILE, MISC EQUIP, also ARMOR, TURRETED WEAPONS/LAUNCHERS, UNKNOWN) or ALL PRIMARY / ALL SECONDARY / ALL EQUIP / ALL UNKNOWN (0x3e6c58-0x3e6c88) | centred on x 252 (167 + 85), baseline 129 | (128,128,64), scale 1.0 | picker fade | L88111-88146; L324225 |
| picker body | `newweapnbkrnd.tif` | x 170..340, y 140..365 | (128,128,128) | picker fade | L87764; L88109 |
| category arrows | `hud_arrow_off2.tif` (HUD2, 32x32) | (168..200, 105..137) with UV swaps `FUN_00358cc0` + `FUN_00358e20`; (305..337, 105..137) with `FUN_00358cc0` | S3 pulse (80,80,80) -> (255,255,128) at 2/s; S2 (100,100,100) | picker fade | L88147-88156; `FUN_0023d2b0` L87887; `FUN_0023d460` L87939 |
| item arrows | `hud_arrow_off2.tif` stretched | (200..300, 140..160) and (200..300, 344..364, `FUN_00358e20`) | as above | picker fade | L88157-88162 |
| 3 cards | icon: the record's `IconTextureName` (`record+0x14` -> texture `+0xbc`, `FUN_003c4700` L316303-316312; all in `COMMON/HUDW_TXR.ZED`, 52 icons of 128x32, 64x32 or 32x32); name: DisplayName upper-cased | card i (0 prev, 1 current, 2 next) at x 170, y0 = 182 + 64 i; icon top-left (174, y0 + 2) at native size; name pen (174, y0 - 2) | name (128,128,128) scale 0.9 | picker fade | `FUN_0023d860` L88170-88200; `FUN_0023c2b0` L87345; `FUN_0023c0d0` L87289 |
| card highlight | `newweapnbkrnd.tif` | x 170..340, y 226..290 (the middle card) | pulse (80,120,120) -> (160,250,250) at 4/s | shown in S3 only | L88203-88205; L89468-89495 |
| blank cards | -- | the prev/next card is emptied when it equals the current one (1-2 items in the category) | -- | -- | L88180-88184 |

**The seven loaders of the brief, and the four it missed.** `newweapnbkrnd.tif` has 7 string copies in the ELF: 0x3e3030,
0x3e3ea0, 0x3e6690, 0x3e6730, 0x3e6c40, 0x3e6e20, 0x3f2320.

| loader | line | what it is |
|---|---|---|
| `FUN_001fa360` | L57282 | `CHUD` Init: a load whose result is overwritten at L57299 (a preload) |
| `FUN_00205e00` | L62554 (0x3e3ea0) | the single-player tactical map / objectives screen ("TACTICAL MAP", "OBJECTIVES" at 0x3e3eb8/0x3e3ed8) |
| `FUN_0021cd40` | L73047 | `CWeaponSel`, the alive R2 inventory (`CHUD+0x1a50`) |
| `FUN_00221070` | L74780 | `CTeamNames` (research 87 §1.19, single player) |
| `FUN_0022ac30` | L79198 | the scoreboard's GAME DETAILS panel (research 87) |
| `FUN_0022ae90` | L79243-79269 | the scoreboard's nine-slice (research 87) |
| `FUN_0022cc10` | L80005 | the scoreboard builder on Select (research 87 L253, 91 L309) |
| not in the brief | -- | `FUN_00237fc0` L85413 = the ammo box (research 87 §1.1); `FUN_002388a0` L85634 = `CHUD+0x17b70` (online) [inferred: the info box strip]; `FUN_002b6fc0` L158242 = the message windows; `FUN_00242bb0` L90396 = `CSpectatorInfo` |
| **the menu's own** | L87759, L89608 (0x3e6c40) | `FUN_0023cd20` and `FUN_00240e60` |

**Strings.** The menu's own text is hard-coded English in the ELF: the title, the ALL-headers, the category names at
0x3fd420-0x3fd518, and the DisplayNames from the weapon records. It uses no HudCLOC/UIMnLOC id. The HudCLOC ids around it are
unused by the code: 60485 `_60485_SELECTED_WEAPONS_MSG`, 60486-60488 `YOU_HAVE_DIED_LINE_1..3`, and 60510 `_60510_R2_BUTTON_MSG`
(probe `b-menu.ts grep`). The prompts are hard-coded too (0x3e31c0-0x3e3450).

**The rest of the HUD meanwhile.** It stays up: `FUN_001f7a90` runs each frame through `FUN_001f97b0`. The help lines keep
their 10 s hold and 0.5 s fade. The lines sit at x 324+ and y 362+, the menu at x -10..340 and y 105..365, so they touch only
at the corner near (324..340, 362..365). With the mode at 1, `FUN_002360d0` (called only for mode 0 or 2, L56690-56692) does
not run.

---

### B6. Sounds, timings, when the pick applies, how it is validated and sent

**Sounds.** None. The whole module (L86283-90450) makes no call to a sound loader or player; the only `FUN_0034ec30` calls are the
voice-recognition loader `FUN_0023b540`. The dead `CInGameWeaponSel` loads `.TCM_SELECT` (0x3e55f0) and `.TCM_SLIDE` (0x3e5600)
into `+0x1194..+0x119c` (L78001-78006) and never plays them. Rebuilding 1:1 means silence: `WEAPON_SELECT_SOUND_READING`.

**Timings.**

| what | rate or duration | source |
|---|---|---|
| menu fade (title, bodies, bar, title text, row list) | `DAT_004147b0` +/- dt x 400, clamped 0..100: 0.25 s | L89439-89452 |
| picker fade | `DAT_004147b8` +/- dt x 400, clamped 0..100 | `FUN_0023d610` L88028-88040 |
| pulses | slot bar and card highlight dt x 4, triangle 0..1..0 (0.5 s period); picker arrows dt x 2 (1 s period) | L89401, L89468; L87910-87918 |
| help lines | hold 10.0 s, fade (1 - (t - 10)/0.5) x 100 | L56544-56561 |
| input | edge-triggered, no repeat | `FUN_002d9ff0` L179130 |

**When the pick applies.** At confirm, `FUN_0023e5e0` (L88379) calls `FUN_0053eee0` (`CCharacterWeap_SetupCharacterWeapon`
0x53eee0) on `character+0x540` (`FUN_00599810`) `+0x2f0 + 0xc i` for each of the 5 slots, and `FUN_0053b3a0` (`+0x2e8`) to add
entries past the record's count. `+0x540` is the record the spawn rebuild reads: `FUN_00599f00` L455782-455800 iterates
`+0x540 -> +0x2f0/+0x2ec`, and research 91 §4.3 has "inventory = the type's default_weapons".

- **Classic.** The round's end `FUN_00223680` (L75920-75936) rebuilds every player without `+0xfd1` through `FUN_00598b90`
  (L75931) -> `FUN_00599b60` (L455158) -> `FUN_00599f00` (L455674), so **the pick is the next round's kit**. A pick left
  unconfirmed in S3 is lost when the round reset closes the menu (L149757 -> `FUN_001fb790` L57684 -> `FUN_00240d50`).
- **Respawn.** The rebuild at a respawn (`FUN_005994a0` L455369/455385 -> `FUN_00599b60`) would use it at the next spawn. Not
  wired.
- **The picker opens on** the slot's current item: `FUN_0023d540` L87972 sets the category to the item's category and the
  index to the item. An empty slot (id 0xff) opens on "ALL EQUIP" at item 0x79.

**How the list is validated** (reader (a) owns the ids; this is what the menu calls).

- **The item filter, `FUN_0023c390` (L87356).** An item is listed only if all of these hold:
  1. **The slot class fits.** Class 0 takes primary categories only: 0x1f, 0x33, 0x51, 0x5b, 0x65, 0x8d (`FUN_003d1d10`).
     Class 1 takes category 4 only (`FUN_003d1ce0`). Class 2 takes neither.
  2. **The category matches**, or the category is 0xff.
  3. **Two special ids.** 0xc3 needs a category-0x65 item (SNIPER RIFLES) in another slot [inferred: the thermal scope].
     0xba needs its own record in another slot and is refused while the current slot holds 0x92.
  4. **No duplicates**, except ids 0xc2, 0xc3, 0x9e, 0x99, 0xb9, 0x91 and 0x92.
  5. **The side's valve admits it.** `FUN_003cf1f0(id)`'s valve value `& 8` for a Terrorist (`FUN_002c30b0(me)`), else `& 1`.
- **Categories, `FUN_0023c840` (L87532) + `FUN_0023cb90` (L87667).** They form a ring per slot class, and a category with no
  listable item is skipped (recursion).
  - Primary: ALL <-> SMGS 0x1f <-> ASSAULT RIFLES 0x33 <-> SHOTGUNS 0x51 <-> MACHINE GUNS 0x5b <-> SNIPER RIFLES 0x65 <->
    HEAVY WEAPONS 0x8d <-> ALL.
  - Sidearm: PISTOLS 4 only.
  - Equipment: ALL <-> GRENADES 0x79 <-> LAUNCHERS 0x91 <-> EXPLOSIVES 0x97 <-> LAUNCHED 0xab <-> MISSILE 0xb9 <-> MISC EQUIP
    0xbe <-> ALL. `LAUNCHED` is skipped unless a launcher host is carried (+0x1532..+0x1534, `FUN_0023d060` L87825-87830).
- **Items.** `FUN_0023c6f0` (L87489) steps +/-1 through the whole weapon list `0x4b5210` (count `DAT_004b5210`), wrapping and
  skipping refused items.
- **Refills.** `FUN_0023b9b0` (L87104) and `FUN_0023bc50` (L87186) walk forward from an item to the next equipment item that is
  not primary, sidearm or launcher and that the side's valve admits. That valve mask comes from the `player_team` value
  (0x3e6c30): **0 -> mask 8, else 1**, see `PLAYER_TEAM_MASK_READING`. `FUN_0023eca0` (L88610) calls them to refill the
  equipment slots when a launcher host is swapped out and its ammo must go. They are **not** list builders.
- **Launcher valves.** `Enable_203FRAG/SMK/HE`, `Enable_GLFRAG/SMK/HE` and `Enable_F2000FRAG/SMK/HE` (0x3e6cc0-0x3e6d50) are set
  to 9 (both sides) or 0 according to the carried host, at Init (L89613-89835) and at confirm (L89190-89300).

**How it is sent online.** Not from the menu. `SendWeaponPUMessage` 0x2ba660 (L160011) packs an item id, a position and a
10-bit rotation into net message 0x40. Its only caller is `FUN_00541700` L408904, the dropped-weapon pick-up. No network function
calls `FUN_0053eee0` or `FUN_0053b3a0` (their 18 callers are this menu, `CInGameWeaponSel` and the lobby armory
0x281be0-0x284360). How a remote console learns the new kit (a spawn/character message carrying `+0x540`'s weapons) was not
traced: `PICK_WIRE_READING`. For the page, M9's `loadout` request stands in and the server validates it with the same rules
(W4.R2/R6).

---

### Placeholders (reader B)

| name | what is unknown | reading / proposal | searched |
|---|---|---|---|
| `WEAPON_SELECT_KEY_READING` | the PC key that opens the menu (the game draws a pad glyph) | **`I`** (`KeyI`; the prompt's `%c` drawn `[I]`, `packages/viewer/src/weaponSelect.ts`), after the game's own `Inventory` result; free in `controlsList.ts` and all of `packages/viewer/src` -- **for the owner (O-S4-3)** | `grep` of every `e.code`/`'Key.'` binding in `packages/viewer/src`; `controller.rdr` |
| `WEAPON_SELECT_TOUCH_READING` | the touch control that opens it | an on-screen button shown only while the prompt line is, labelled `INV` (the prompt's `%c` drawn `[INV]`, `packages/viewer/src/weaponSelect.ts`); rows and cards tappable -- **for the owner** | the game has no touch |
| `WEAPON_SELECT_MENU_KEYS_READING` | the keys inside the menu | W/S or Up/Down arrows = Up/Down, A/D or Left/Right arrows = Left/Right, X or Enter = Action, Backspace = Triangle, `I` closes the list (`menuInputOfKey`, `packages/viewer/src/weaponSelect.ts`) -- **for the owner** | the game's pad map (§B3) |
| `WEAPON_SELECT_SOUND_READING` | whether the rebuild plays anything | silent (1:1: no sound call in L86283-90450; `packages/viewer/src/weaponSelect.ts` plays nothing); the alternative would be the unused `.TCM_SELECT`/`.TCM_SLIDE` | module grep for `FUN_0034*`, sound strings |
| `PICK_WIRE_READING` | how the confirmed kit reaches the other consoles and server | the spawn/character message carries `character+0x540`'s weapons [not traced]; the page uses M9's `loadout` request (protocol 7: the side's picks since the match began, replayed by the room from the type's kit with `applyPicks`, answered with the kit held; a `spawn` carries the kit, a body its held item's id -- `packages/viewer/src/net/protocol.ts`, `packages/server/src/room.ts`) | callers of `FUN_0053eee0`/`FUN_0053b3a0`, `FUN_002ba660` |
| `PLAYER_TEAM_MASK_READING` | replaced by `INGAME_AUTOFILL_SIDE_READING` (§A-placeholders; the same question): `FUN_0023b9b0`/`0023bc50` take mask 8 when the `player_team` valve is 0, while `FUN_0023c390` takes 8 for a Terrorist | the refills use the same side as the list [inferred]; the `player_team` value per side not read | L87139-87142, L87226-87229, L87466-87471 |
| `ARROW_ORIENT_READING` | which way each `hud_arrow_off2.tif` quad points after `FUN_00358cc0`/`FUN_00358e20`'s UV-corner swaps | left arrow at 168 and right at 305, up at y 140 and down at y 344 by position [inferred]; drawn with the bitmap pointing up (as `tacMap.ts`'s edge arrows): the category arrows turned -90 / +90 degrees, the lower item arrow mirrored top to bottom (`packages/viewer/src/weaponSelect.ts`); the bitmap's own direction not decoded | L88147-88162; L254802, L254860 |
| `EMPTY_SLOT_NAME_READING` | what an empty slot's row shows | the DisplayName of the record for id 0xff (`FUN_003c4b40(list, 0xff)`) [not read]; the arsenal has no such record, so the row (and a 0xfe row) is blank `''` unless one exists (`packages/viewer/src/weaponSelect.ts`) | `FUN_0023e370` L88329-88336 |
| `CARD_TEXT_OFFSET_READING` | the text objects' `+0x7c/+0x80` offsets added to the card name's pen | 0 [inferred]; pen (174, y0 - 2) (`packages/viewer/src/weaponSelect.ts`) | `FUN_0023c0d0` L87313-87318 |
| `DEAD_CYCLE_WHILE_MENU_READING` | whether Up/Down also cycle teammates while the menu is open (HUD mode 1) | blocked like the respawn press and spectator camera (both gated on mode 0) [inferred]; the page takes every key and button from the game while the menu is open, the teammate cycle included (`packages/viewer/src/netPage.ts`, `packages/viewer/src/weaponExchange.ts`) | `FUN_005979a0` L454440-454500 (no input read there); `FUN_00295260` L139475 |
| `CIGWS_METHOD_MAP_READING` (*note only*) | the names of 0x227560/0x227650/0x227730/0x227880 | UpdateCharacter / SwitchOffText / AfterClose / Clear by size and role [inferred]; the class is dead, so it does not matter for the rebuild | demo `.symtab` sizes vs `functions.txt` |
| `GLYPH_READING` | the glyph codes' buttons: 0xa3/0xaf, 0xac (drawn by name: `PAD_GLYPH_PLACEHOLDER`) | 0xa3/0xaf = d-pad Up/Down, 0xac = Triangle [inferred from the spectator lines' bytes +5/+6/+7]; 0xbe R2, 0xbd R1, 0xa6 X, 0xb7 Circle from the config test | `font_special_01` glyphs not decoded |
| `DEFAULT_CHARTYPE_PLACEHOLDER` (existing) | the character type | unchanged: the menu offers no type | module grep |
| `PAD_GLYPH_PLACEHOLDER` | the pad glyphs' faces (`font_special_01`, not transcribed in `hudFont.ts`) | each drawn as its button's name: 0xbe `R2`, 0xbd `R1`, 0xa3 `UP`, 0xaf `DOWN` (`packages/viewer/src/weaponSelect.ts`; the page's own `netPage.ts` lines already write `R2`) | `hudFont.ts`; `GLYPH_READING` |
| `PROMPT_COLOUR_READING` | the help lines' colour, alpha and alignment | the code's: colour (100, 100, 20) (`CHUD` Init writes it into each line's colour words `+0x48..+0x50`, L57301-57303 -- the words the title's (128,128,64) goes to, L88296), alpha 100 in the hold (L56546), **centred** on x 324 (`+0x69` = `+0x19dc1` set at L57122); §B4's S1 row says (128,128,128) alpha 80, not found in the code (`packages/viewer/src/weaponSelect.ts`) | L57289-57305, L56540-56561, L57120-57126 |
| `PULSE_PHASE_READING` | the pulses' phase when the menu opens | each pulse is a persistent accumulator starting 0 rising at construction (ctor `FUN_00241a90`: `+0x1154` 1, `+0x1158` 0, `+0x1538` 1, `+0x153c` 0; picker Init `+0xf28` 0, `+0xf2c` 1), the slot bar's advancing only in state 2; the viewer starts each at 0 rising when the menu opens (`packages/viewer/src/weaponSelect.ts`) | L89868-89881; L87746-87747; L89400 |
| `ARROW_TINT_SCALE_READING` | the scale of the arrows' colours (`FUN_003590e0` -> `FUN_00361200`, a polygon's vertex colour, not `FUN_00364930`'s sprite tint) | the GS 0-128 MODULATE scale like the tints [inferred]: the pulse's (255,255,128) brightens up to twice, saturating (`packages/viewer/src/weaponSelect.ts`) | L254953; L87927-87931 |
| `DRAW_ORDER_READING` | the order the menu's sprites and strings are drawn in (`FUN_001f6e10` registers each part) | panels, the bar and the card highlight, then the arrows and icons, then the strings [inferred] (`packages/viewer/src/weaponSelect.ts`) | L89585-89640 |

## 3. Per-class behaviour (reader c)

Research reader (c) for web sprint 4 "the arsenal", 2026-09-30. Read-only. Sources, as cited: the retail decomp
`analysis/socom2_game.elf.decomp.c` (cited `L<line>` and the retail address), the retail ELF
`analysis/elf/socom2_game.elf` (`.data`/`.rodata` read with a Python reader over its four `PT_LOAD` segments --
file offset = vaddr - seg.vaddr + seg.offset; floats little-endian IEEE-754, strings NUL-terminated), the retail
recompilation `recomp/retail/output/*.cpp` (MIPS comments; used for load-instruction searches), reCOM `recom/src/...`,
and the disc's `disc/RUN/ZWEAPON.ZAR/zweapon.rdr` read with the repo's own `@s2u/archive` reader through the probe
`probe/c-rare.ts` (`npx tsx` from `web/redotcom`; modes `rare`, `rec <names>`, `ammo`). All paths are
relative to the archive root the handoff archive root unless they start `web/`. No game bytes
quoted beyond names and numbers. Units: the parser multiplies speeds, accelerations, radii and ranges by
`DAT_003dfe10` = 10 (research 84 §1), so "x10 units" below; timers are seconds, unscaled.

### C0. Answers in one table

| # | question | answer | source |
|---|---|---|---|
| 1 | Member map of the rare keys | `+0x24` MaxFireMode, `+0x28` Ammo_Capacity, `+0x2c` NumMags, `+0x30`/`+0x34` Sound_Radius x10 and its square, `+0x38` Encumbrance (byte), `+0x3c` Maximum_Range, `+0x40` Effective_Range, `+0x44` Muzzle_Velocity, `+0x48` Gravity_Acceleration, `+0x4c` ImpactRadius, `+0x50` FireWait, `+0x54` ReloadTime, `+0x58` ReloadAfterShot (byte), `+0x5c` ReloadDelay, `+0x60` ReloadDelayAfterShot, `+0x64` Damage_Modifier, `+0x68` ArmingDistance x10, `+0x6c` RecoilPct, `+0x7c` ID, `+0xa4`->`+0xa0` ReloadAfterShotSound, `+0xd0..` mode flags, `+0xd5` HasBackblast, `+0xd8`/`+0xdc` Timer1/Timer2, `+0x27c` SlotCost | parser `FUN_003cda30` L322377-322620; setters L324568-325475 (§C1) |
| 2 | Defaults when absent | ReloadTime 0, ReloadDelay **0.01**, ReloadDelayAfterShot **0.01**, Timer1/2 **9999999**, Gravity **9.8** (x10 = 98 u/s^2), ArmingDistance 0, SlotCost **1**, Encumbrance 0, Damage_Modifier 0, Sound_Radius 0 | L322410-322414, 322538-322552, 322577-322586, 322610-322614 |
| 3 | Keys the ELF never reads | `TracerTextureName` (no string in either ELF), `ReloadAfterShotDelay` (the 870's spelling -- no string in either ELF), the per-stance `AccuracyBurst*`/`AccuracyScalar*` (research 84 §1) | `grep -ac` over both ELFs = 0 |
| 4 | Encumbrance | parsed to byte `+0x38`; **no reader found** (no `lb`/`lbu ...,0x38(` on a weapon in the 14,880 retail `.cpp`) -- the mover does not read it | §C1.9; `ENCUMBRANCE_READER_NOT_FOUND` |
| 5 | ReloadAfterShot + ReloadDelayAfterShot (bolt/pump) | after a round, if the weapon has `ReloadAfterShot`, a round remains, and it is not the MGL's round: the kit's lock timer `kit+0x820` = `ReloadDelayAfterShot` (flag "after-shot"); no fire while it runs; at 0 `FUN_005c3000` plays the after-shot clip (`Shotgun pump` family for the shotgun class) and `ReloadAfterShotSound` (`.SHOTGUN_COCK`, 870 only) | `FUN_005c5340` L479329-479343; `FUN_005c0fd0` L476549-476561; `FUN_005c3000` L477551-477650 |
| 6 | The 870's pump | its file spells `ReloadAfterShotDelay 0.8`, which the parser does not read: its lock is the default **0.01 s**; its cadence is `FireWait` 0.75 | §C2.2 |
| 7 | ReloadDelay | the lock before a reload lands (R, or automatic on the last round): `kit+0x820` = ReloadDelay (0.01 default; Spas/Jackhammer 0.5, 870 1, LAW HEAT/RPG 1) | `FUN_005c32b0` L477653-477680; L453459-453463; L479317-479320 |
| 8 | ReloadTime | only rescales the **standing** reload clip (speed^2 <= 400) to last ReloadTime s: rate = clip length / ReloadTime (Spas 12 2, JACKHAMMER 2, M60E3 3, M63A 2.5) | `FUN_005a82e0` L462821-462945 |
| 9 | Fire modes, burst | `MaxFireMode n` enables 0..n; `SingleMode`/`AutoMode` enable 1/3 and raise the max; no record has `BurstMode`. Mode 2 = 3 rounds a pull at FireWait x0.8; mode >= 4 is a **launcher round's item ID**: 1 round a pull at the round record's FireWait | L322496-322512; `FUN_005c0940` L476281-476307, `FUN_005c09f0` L476313-476340 |
| 10 | Shotgun pellets | `12 Gauge` `NumProjectilesFired 4`: the fire loop calls the round's leaving 4 times, each with its **own** cone draw (the player controller's vtable +0x74 = `FUN_00592260`), one shell off the magazine per pull. On the victim the class-'Q' hit is re-counted: 8 base inside 5 m (SP) / 8 m (MP), else 4 inside 15 m (MP), plus 1/2/4/5/6/7 at 5/10/35/35/10/5 %, thinned past the base radius; each to HEAD/BODY 30 % each, arms/legs 10 % each; a victim is hit once per volley, not once per pellet | `FUN_005be9a0` L475580-475677 (one shell: L475608); `FUN_005a1620` L459317-459389; `FUN_005abbc0` L464704-464737; tables `DAT_006508b8..d0/e0/f8`, research 91 §1.1 |
| 11 | Shotgun blowback | `Blowback_Falloff 1` / `Blowback_End 4` (m): a hit sets a push on the victim of damage x (1 inside 10 u, linear to 0 at 40 u), strength 100 | `FUN_003d4450` L326567; L464780-464796, L459580-459592; `FUN_0057ed10` |
| 12 | Muzzle_Velocity / drop | **bullets do not use it**: a bullet-class projectile is a ray of `Maximum_Range x 1.1` from the muzzle, no gravity. Grenades, launcher rounds and the backblast fall at `Gravity_Acceleration` (98 u/s^2); rocket rounds (185-189) instead accelerate along their velocity at the ammo's `AccelerationFactor` (98 -> 980 u/s^2) | `FUN_003ca5a0` L320303-320398; `FUN_003cb1a0` L320657-320790 |
| 13 | Launcher selection | a **fire mode** of the carrier: M16A2-M203 (52), M4A1-M203 (61), F2000 (63), MGL (142), M79 (143), LAW/RPG (145-150) are "carriers"; a slot mode > 3 is the ID of a round item in another kit slot, which `FUN_005c6600` redirects the fire to; L3 cycles rifle modes then each round type held | `FUN_003c5d80` L317277; `FUN_005c6600` L479603-479660; `FUN_005c4600` L478555-478650; `FUN_005c4480` L478488 |
| 14 | Launcher kit shape (the in-game select) | M203 rifle -> slot 2 = `M203` (141), slot 3 = `M203 FRAG` (175), 203 valves set to 9; M79 -> slot 2 = `GL FRAG` (179), GL valves 9; MGL -> slot 2 = `M203 FRAG` (175); LAW/RPG (`SlotCost 2`) -> the paired slot = `LAW HEAT` (185) / `RPG` (186); any other SlotCost-2 item pairs with `FULL_SLOT` (254) | `FUN_0023fef0` L89138-89330 |
| 15 | Grenade-launcher aim | in round mode the carrier fires from `firepoint_203` and, for the player, **lofts the direction** (+0.025 in y, up to 12 steps) until a round at the round's Muzzle_Velocity under 98 u/s^2 reaches the aimed point | L475520-475531, L475566-475575; `FUN_005bf8a0` L475688-475740; `DAT_00650958` 98.0, `DAT_00650960` 12, `DAT_00650968` 0.025 (`.data`) |
| 16 | ArmingDistance | the launched round hitting within ArmingDistance x10 (100 u for every round that has it) of its launch point does not explode: velocity x0.5, fuse set to 9999999, bounce; the reticle turns grey (130,130,130) while the aimed point is **inside** the arming distance (correcting research 84 §9 "past a launcher's range") | `FUN_003c8920` L319439-319462 (`DAT_003e1510` = 0.5); HUD L70235-70257 (`DAT_003dc588/90/98` = 130.0) |
| 17 | HasBackblast | on `LAW HEAT` (185) and `RPG` (186): each shot also fires the `Backblast` record (159) from the launch point with the direction reversed; it has MV 0, Timer1 0/Timer2 0.1, `Backblast Ammo` 6 damage in 7 m | `FUN_003d2d70` L325541-325600 |
| 18 | SlotCost | 2 on LAW, RPG LAUNCHER, Satchel: the item takes a second equipment slot (2..4, wrapping) | `FUN_003c5970` callers L89164, L472945, L473286 |
| 19 | Timer1 / Timer2 | projectile `+0x8c` (fuse: counts down; at 0 goes off unless claymore or proximity) / `+0x90` (lifetime of the lingering state 6, e.g. smoke). Satchel's Timer1 is a global (`DAT_00437d44`) | `FUN_003cb1a0` L320738-320741; tick L316883-316905; `FUN_003d2220` L324706 |
| 20 | Sound_Radius | the fire posts an AI stimulus at the muzzle with radius^2 = (Sound_Radius x10)^2, 0.1 s, when > 1 unit | `FUN_003d2d70` L325585-325596 |
| 21 | C4 (151) | **timed, not remote**: placed only on a C4 target object the SEAL is at (body `+0x3dc`), standing still; `Timer1` 6 s fuse; 18 dmg in 5 m, `IgnoreExplosionDI`. The Detonator is added only for a claymore and sets off only claymores | `FUN_005be9a0` L475378-475470; `FUN_005c1970` L476880-476960; `FUN_005c74e0` L480154-480200; `FUN_005c0130` |
| 22 | PMN (158) | placed like the claymore; **arms after `Timer1` 8 s**; then any actor within `ProximityDistance` 1 m (10 u) sets it off; 6.5 dmg in 4 m | L410270-410310 (`FUN_00543930`); L316893-316905; research 85 §9.7.1 |
| 23 | Thermal scope (195) | an equipment item, no model of its own; selectable only with a sniper-class weapon in the kit; holding it swaps the sniper model's `scope` node for `thermal_scope`, and every scoped view (states 5-12) plays the lens effect `to_thermal_lens_fx` instead of the scope/starlight one; zoom levels unchanged | `FUN_005b82e0` L471451-471530; `FUN_001f0750` L53084-53160; `FUN_0023c390` L87400-87411 |
| 24 | 2X ammo (194) | brief (reader (a) owns): NumMags x2, capped at 10, for pistol/SMG/rifle/shotgun/MG/sniper classes; the extra slots filled full | `FUN_005ba3d0` L472718-472745; `FUN_005c75f0` L480215-480250 |
| 25 | Scope overlay per weapon | one set for every scoped weapon (magnification > 1.01 -> reticle set 5, `ret_scope_01/02`); only the F2000 skips `ret_scope_02`; state 4 binoculars set 7; carriers in round mode set 3 (`ret_rocket`) -- the M203 rifles/F2000 only for round modes >= 5 | `FUN_005be300` L474894-474950; research 84 §9 |
| 26 | Holsters | the carried long gun's node `rifle` hangs on **spinelo**, the sidearm's `pistol` on **hips**, both on **rhand** when in hand; `grenade` always rhand; `launcher` node on **spinehi**; their local pose comes from the clips' `rifle`/`pistol`/`launcher`/`rifle_out` tracks | `CZSealBody_AddWeapon` 0x553290 L419019-419060; bones L419600-419640; L419672-419687; research 77 §4 |
| 27 | HUD box | icon = the item's `IconTextureName`; `%d/%d` and `%d MAG%c` as research 84 §18; the fire-mode row draws 1/3/4 rounds for modes 1/2/3 and, for a round mode (> 3), **the round's icon** (`firemode_203_he.tif`, `firemode_AT4.tif`, `firemode_RPG.tif` ...) in the first cell | `FUN_00237b40` L85254-85300; caller L85213-85226 |

### C1. The rare keys, from the parser outward

#### C1.1 ReloadAfterShot, ReloadDelayAfterShot, ReloadDelay, ReloadAfterShotSound

- **Parse.** `ReloadDelay` (0x3fcb88) -> `+0x5c`, default 0.01 (L322543-322547, `FUN_003d2c30`); `ReloadDelayAfterShot`
  (0x3fcba0) -> `+0x60`, default 0.01 (L322548-322552, `FUN_003d2c10`); `ReloadAfterShot` (0x3fcbc0) is a
  presence flag -> byte `+0x58` = 1 (L322553-322556); `ReloadAfterShotSound` (0x3fcb60) -> `+0xa4`, resolved to a
  sound handle at `+0xa0` by `FUN_003c4700` (L316283-316290). Getters `FUN_003d2c40` (+0x5c), `FUN_003d2c20` (+0x60).
- **The lock** is one kit timer, `kit+0x820`, with a flag bit `kit+2 & 2` ("after-shot") -- `FUN_005c32b0`
  (L477653-477680): `delay == -1` means "the current weapon's ReloadDelay (flag 0) or ReloadDelayAfterShot (flag 1)".
  The kit's frame (`FUN_005c0fd0` L476549-476561) runs it down; **while it is non-zero the fire tick `FUN_005c1970` is
  not called** (no shot, no throw); at <= 0 it calls `FUN_005c3000` (flag 1) or the reload `FUN_005c2a90` (flag 0).
- **Who arms it** (`FUN_005c5340`, the round's leaving, L479291-479343): the weapon must not be one of 255, 254, 195,
  194, 145, 141, 146, 11, 193, 190 (L479305-479313). Then
  1. **the last round** (`FUN_005c38a0` rounds in the magazine == 1 before the decrement) -> `FUN_005c32b0(ReloadDelay,
     kit, 0)`: the automatic reload (research 84 §18);
  2. else, if `+0x58` (ReloadAfterShot) and the firing carrier is not the MGL (`lVar13->ID != 0x8e`), and (rounds > 1
     and the timer idle) **or the round is the RPG's (0xba)** -> `FUN_005c32b0(ReloadDelayAfterShot, kit, 1)`.
  The reload button arms it too: `FUN_002c64e0(6)` -> `FUN_005c32b0(-1.0, kit, 0)` (L453459-453463).
- **At the end of an after-shot lock** (`FUN_005c3000` L477551-477650): for the RPG launcher (146) it walks to the next
  kit slot holding RPG rounds (the launcher is fed one round at a time); then it plays `FUN_005a82e0(body, 1)` -- the
  after-shot clip -- and the weapon's `+0xa0` sound (`.SHOTGUN_COCK` on the 870; no other record has one) at the body.
- **Values:** bolt snipers M40A1 and M87ELR 0.5 s; M203/F2000/GL rounds 0.5 s; LAW HEAT and RPG 1 s; the 870 has the
  flag but its delay key is misspelt (`ReloadAfterShotDelay 0.8`, no such string in either ELF) -> **0.01 s**.
- **reCOM** has `m_reloadAfterShot` (`recom/src/gamez/zWeapon/zweapon.h:530`) and `m_reloadtime` (`:529`), default 0
  (`zwep_weapon.cpp:64-66`) -- the same members, no behaviour.

#### C1.2 ReloadTime (`+0x54`)

Read only in the reload-clip start `FUN_005a82e0` (L462786-462949): `bVar3` = the body's speed^2 `<= 400` (L462821-
462823: standing); for the standing clip `if (ReloadTime > 0) clip.rate = clip.length / ReloadTime` (L462940-462945).
The moving clip plays at its own rate. Which clip (action names read from `.rodata`, set at L495218-495225,
L495399-495407):

| case | clip family (stand / crouch / prone / moving) |
|---|---|
| pistol in hand (`+0xf79 != 1`) or the sidearm classes | `Pistol reload` / `Pistol crouch reload` / `Pistol prone reload` / `Moving pistol reload` |
| 870 (ID 84) or M82A1A/M40A1/M87ELR (class 101, IDs 101-103) | `Shotgun reload` / `Shotgun crouch reload` / `Shotgun prone reload` / `Moving shotgun reload` |
| after-shot (`param_2` 1) on the shotgun class | `Shotgun pump` / `Shotgun crouch pump` / `Shotgun prone pump` / `Moving shotgun pump` |
| everything else (Spas 12, JACKHAMMER, rifles, SMGs, MGs, SR-25s, Dragunov) | `Rifle reload` / `Rifle crouch reload` / `Rifle prone reload` / `Moving rifle reload` |
| `body+0x528 == DAT_0044d408` | `launcher_reload` (`LAUNCHER_RELOAD_CONDITION_READING`) |
| a launcher round mode (`bVar4`: `FUN_005bda00` or `FUN_005bd6d0`; M4's reading of L462836-462846) | `Rifle m203 reload` (`DAT_003debf8`, named at L495238 from 0x661840: `seal_reload_m203`) in every stance still / `Moving rifle reload` moving |

So a bolt sniper's after-shot plays the `Shotgun reload` family (the class-'Q' test fails for class 'e').

#### C1.3 AutoMode, SingleMode, MaxFireMode (burst)

Parser L322491-322512: `MaxFireMode` (default 0) -> `FUN_003d2a80` enables flags `+0xd0..+0xd0+n`; then `BurstMode`,
`SingleMode`, `AutoMode` (presence flags) -> `FUN_003d2a30(2|1|3)`: flag on, `+0x24 = max(+0x24, mode)`. The switch
`FUN_005c4600` (research 84 §6) skips disabled modes. From the disc:

- **semi only** (MaxFireMode 1): every pistol but the Model 18, the 870, Spas 12, all snipers.
- **semi + burst** (MaxFireMode 2): M16A2 and M16A2-M203.
- **semi/burst/auto** (MaxFireMode 3): M4A1, M4A1 SD, M4A1-M203, 552, 552SD, AK-47, AKS-74, AK-105, Groza, HK5, HK5SD,
  F90, 9mm Sub, MP5K.
- **semi + auto, no burst**: Model 18 (MaxFireMode 1 + SingleMode + AutoMode), M14 (SingleMode + AutoMode, no
  MaxFireMode), JACKHAMMER, SA-80 A2, Steyr Aug (MaxFireMode 1 + AutoMode).
- **auto only**: M60E3, M63A, .PKM (AutoMode, no MaxFireMode).
- **no firearm mode** (MaxFireMode 0): MGL, M79, LAW, RPG LAUNCHER -- they fire only through a round mode (C4.2).
- The burst: mode 2 = 3 rounds a pull, `FireWait x 0.8`; the pull's count resets on release (research 84 §6).
- Round modes (> 3): 1 round a pull (`FUN_005c0940` L476297), wait = the **round record's** FireWait (M203/F2000 rounds
  1 s, GL rounds 0.1 s, LAW HEAT/RPG 3 s), `FUN_005c09f0` L476313-476340 with `FUN_005c3780` = the redirected record.

#### C1.4 ZoomMode1/2, NumZoomModes

Research 84 §7 owns the view states; the per-record values are in C-table below. Scoped records (NumZoomModes >= 2):
M4A1 2.5, M4A1 SD 3, 552 3, 552SD 3, SA-80 A2 4, Groza 3, Steyr Aug 2.5, SR-25 8, SR-25 SD 8, Dragunov 8 (one
level each); M40A1 6/12, M82A1A 8/16, M87ELR 8/16 (two). Everything else has one mode (no scope; a sidearm zooms into
the 9x view). The fire-mode switch is refused while magnified (`FUN_005c4600` L478570-478575).

#### C1.5 ArmingDistance (`+0x68`, x10)

Getter `FUN_003d2030`; three readers: the projectile hit `FUN_003c8920` L319439-319462 (C4.3) and the reticle colour
(L70235-70257, C6). Every record that has it: 10 m (M203 HE/FRAG, F2000 HE/FRAG, GL HE/FRAG, LAW HEAT, RPG, MGL FRAG
TURRET); smoke rounds none.

#### C1.6 HasBackblast (`+0xd5`)

A presence flag -> `FUN_003d2020(w, 1)` (L322615-322618); read only by `FUN_003d2d70` (the weapon's fire, L325541):
see C4.4.

#### C1.7 SlotCost (`+0x27c`, default 1)

Getter `FUN_003c5970`. Readers: the in-game select's slot setter `FUN_0023fef0` (L89164-89196) and the kit's add-item
paths `FUN_005ba770` (L472945) / `FUN_005bb000` (L473286). With 2 the item claims the next equipment slot (index
`param+1`, past 4 wrapping to 2, or the first empty one) and fills it with `LAW HEAT` (0xb9) for the LAW, `RPG`
(0xba) for the RPG launcher, else `FULL_SLOT` (0xfe) (L89180-89196). On the disc: LAW 2, RPG LAUNCHER 2, Satchel 2.

#### C1.8 Gravity_Acceleration (`+0x48`, x10, default 9.8)

Getter `FUN_003d27b0`, read only in the projectile tick `FUN_003ca5a0` (L320349-320353): for a non-bullet projectile
in flight (state 1 or 6, `+9 == 0`) that is not a rocket round, `v.y -= g dt`, `p += v dt`. Only `MGL FRAG TURRET`
sets it (3.9); everything else falls at 98 u/s^2. The AI/launcher loft uses its own 98 (`DAT_00650958`), not the key.

#### C1.9 Encumbrance (`+0x38`, byte)

Setter `FUN_003d29f0` (L322491-322495). No getter exists beside the other setters (L324300-325700 scanned), and no
load of byte `0x38` from a weapon was found: `grep` for `lbu|lb $r, 0x38(` over all 14,880 `recomp/retail/output/*.cpp`
hits only UI/sound/other structs (`FUN_0023b190`, `FUN_002707c0`, `CCounterSpec_*`, `sub_0026*`, stack loads).
**The mover does not read it** in the retail build. reCOM names the values (`zweapon.h:21-28`: 0 light, 1 medium, 2
heavy, 3 very heavy, 4 not encumbered) and a `m_encumbmod` on the seal (`zSeal/zseal.h:685`) with no user. Disc:
pistols and equipment 4, rifles/SMGs/shotguns/snipers 1, M203 rifles/F2000/MGL/M79/LAW/RPG 2, MGs and M82A1A 3.

#### C1.10 Sound_Radius (`+0x30`, x10; square at `+0x34`)

`FUN_003d2a00` (L325313). Read by the weapon's fire `FUN_003d2d70` (L325585-325596): for a firearm-class or rocket
weapon with `+0x30 > 1.0`, a stimulus `FUN_0050ef30`/`FUN_0050ee30` (the AI perception broadcast, L381078-381140) at the
muzzle with radius^2 = `+0x30^2`, 0.1 s, kind 0xe. The impact posts its own (ImpactRadius x the surface factor,
L319424-319436). So Sound_Radius is how far bots hear a shot (M4A1 SD 100 u, M4A1 1000 u, M82A1A 1350 u); in a
players-only match it has no effect (`SOUND_RADIUS_MP_USE_READING`).

#### C1.11 TracerTextureName

**Never read**: no `TracerTextureName` string in the retail or r0004 ELF (the parser's key list 0x3fc638-0x3fcca0 ends
at `RecoilPct`). All 84 records say `(null)` anyway. The tracer is a class rule: the projectile's `+4 & 0x20` is set
for classes SMG, rifle, MG, launcher (141-144) and turret when the weapon is not suppressed (`FUN_003c5ac0`: 67, 33,
105, 62, 16) (`FUN_003cb1a0` L320681-320692); every fourth round draws it with the `tracer`/`tracer_enemy`/`tracer_ally`
textures (strings 0x3fd5c0-0x3fd5d8, loaded L327322-327334) -- research 89 §4.

#### C1.12 Muzzle_Velocity (`+0x44`, x10) -- drop?

Getter `FUN_003d27c0`. Readers:
- `FUN_003cb1a0` (L320727-320731), the projectile's launch: `v = MV x dir + inherited velocity`.
- The tick `FUN_003ca5a0`: a **bullet** (`+9 == 1`, set for every class `FUN_003d1e20` accepts -- all but grenades,
  launcher rounds, rocket rounds, placed explosives, gear, the MGL turret; L320771-320773) is cast as one segment of
  `Maximum_Range x 1.1` along its direction (L320383-320398): **no travel time from MV and no drop**.
- `FUN_005bf8a0` (the launcher loft, C4.2) and `FUN_0055ecc0` L424959 (the AI's lead of a moving target).
So MV matters for grenades (0.1 = the throw's speed passes unchanged, research 85 §1), launcher rounds (M203/F2000
rounds 27 m/s = 270 u/s, GL rounds 40 = 400 u/s) and rockets.

#### C1.13 Timer1 / Timer2 (`+0xd8`/`+0xdc`, default 9999999)

`FUN_003d2220(w, i)` returns them, except the Satchel (ID 0x98) whose Timer1 is the global `DAT_00437d44` (L324706-
324718). The projectile copies them to `+0x8c`/`+0x90` at launch (L320738-320741). The tick (L316883-316905): state 6
(lingering: smoke, flash) counts `+0x90` down and ends at 0; otherwise `+0x8c` counts down (online only on the owner's
machine) and at <= 0 sets `+0xc4` ("go off") **unless** `+0xc5` (claymore) or `+0xc6` (has a proximity) -- so Timer1 is
the fuse of grenades, launcher rounds' self-destruct, C4's delay, and the PMN's arming delay (C5.3).

### C2. The shotguns

#### C2.1 The 12 gauge's pellets

- **Ammo:** `12 Gauge` (ID 27): `ImpactDamage 2.5`, `Piercing 6`, `NumProjectilesFired 4`, `Blowback_Falloff 1`,
  `Blowback_End 4` (disc). Parser `FUN_003cedb0` L322629-322735: `NumProjectilesFired` -> ammo `+0x20` (default 1,
  getter `FUN_003d44e0`); the blowback pair -> `+0x34/+0x38` as squares of x10 (`FUN_003d44c0`).
- **At the shooter** (`FUN_005be9a0`, L475580-475677): `n = NumProjectilesFired` of the loaded round; the loop calls the
  controller's vtable `+0x74` (the player's = `FUN_00592260`, vtable at 0x6694b0 read from `.data`) **per pellet** --
  a fresh `u|u|` draw inside the reticle's cone (research 84 §5) -- then `FUN_005c5340` (a whole round leaving: marks,
  tracer rule, sound). The magazine is decremented **once** for the shotgun class (`cVar3 == 'Q'` and pellet 0 only,
  L475608-475615). So a pull puts 4 rays in the cone, one shell used.
- **Spread** = the shotgun's reticle size (its `Reticule_Modifiers`): no separate pellet cone.
- **At the victim** the hit path re-counts (research 91 §1.1, re-read here): `FUN_005abbc0` L464704-464737 -- a class-'Q'
  projectile is honoured **once per victim per volley** (the victim's `+0x1048` "last projectile" guard skips a 'Q' hit
  while the last one recorded was also 'Q'; `SHOTGUN_HIT_GUARD_RESET_READING`: where `+0x1048` is cleared -- only writes at
  L464602/464737/464743/464757 seen); offline it applies `FUN_005a1620` pellets, each `FUN_003c7600` damage to a random part;
  online `FUN_005a5a80(body, 3, proj)` sends it and the receiver (L160838 -> `FUN_005a1b80` L459540-459570) applies the
  same count with `FUN_003d4530` (raw ImpactDamage) per pellet (`SHOTGUN_MP_PELLET_DAMAGE_SCALE_READING`: whether the x14
  and falloff apply on that path -- research 91 owns damage).
- **The count** `FUN_005a1620`: d^2 from the shooter; base 8 if d^2 < 2500 (SP, `DAT_006508b8`) / 6400 (MP,
  `DAT_006508c0`), else 4 if MP and d^2 < 22500 (`DAT_006508c8`); plus 1/2/4/5/6/7 with p 0.05/0.10/0.35/0.35/0.10/0.05;
  past the base radius x `r^2/d^2` with a random round-up. Parts: tables `DAT_006508d0`/`DAT_006508f8` = (0 HEAD, 3 BODY,
  2 LARM, 1 RARM, 5 LLEG, 4 RLEG) at cumulative 0.3/0.6/0.7/0.8/0.9/1.0 (read from `.data`).
- **Blowback**: the same hit sets `body+0x1314..0x1324` (`FUN_0057ed10`: source, damage x `FUN_003d4450(d^2)`, 100.0) --
  a push, full inside 1 m, 0 at 4 m (`BLOWBACK_CONSUMER_READING`: which motion reads `+0x1320`).

#### C2.2 The pump and the box shotguns

| | 870 (84) | Spas 12 (81) | JACKHAMMER (83) |
|---|---|---|---|
| FireWait / modes | 0.75 / semi | 0.45 / semi | 0.3 / semi + auto |
| magazine | 8 x 5 | 12 x 3 | 12 x 3 |
| after-shot | `ReloadAfterShot`, delay **0.01** (misspelt key), `Shotgun pump` clip, `.SHOTGUN_COCK` | -- | -- |
| ReloadDelay / ReloadTime | 1 / -- | 0.5 / 2 | 0.5 / 2 |
| reload clip family | `Shotgun reload` | `Rifle reload` (stretched to 2 s standing) | same |

`PUMP_BLOCKS_FIRE_READING`: whether the `Shotgun pump` action (a body action, `FUN_00588bc0`) refuses fire while it
plays -- the kit's own lock ends before the clip starts.

### C3. The bolt, and the burst

- **Bolt** (M40A1 102, M87ELR 103): `ReloadAfterShot` + `ReloadDelayAfterShot 0.5`; FireWait 0.5 / 0.7; after a round
  with another left the kit is locked 0.5 s, then the after-shot clip (`Shotgun reload` family, C1.2) plays; no sound
  key. The M82A1A (101) has no after-shot (semi, FireWait 2.1) but shares the `Shotgun reload` clip family.
- **Burst**: C1.3. Only the mode flags make a burst; no record carries `BurstMode`.

### C4. The launchers

#### C4.1 The records

| item | ID | role | kit | rounds / fire | key numbers |
|---|---|---|---|---|---|
| M16A2-M203 / M4A1-M203 | 52 / 61 | carrier (rifle + launcher) | primary | 5.56 in modes 1-2 / 1-3; round modes = 171/173/175 | Encumbrance 2 |
| M203 | 141 | the attached launcher item, forced into slot 2 by the select | equipment | none (Cap 0, `AMMO_TYPES` empty) | MV 921 (unused) |
| M203 HE / FRAG / SMOKE | 171 / 175 / 173 | rounds, one kit slot each | equipment | 6 x 1 each; FireWait 1 | MV 27 (270 u/s), Arming 10 m (not SMOKE), RAS + 0.5, Timer1 10 / 10.1 (SMOKE 3 / 40) |
| MGL | 142 | carrier | primary | fires `M203 FRAG` (175) via the select's slot 2; its own 6 x 2 | FireWait 0.25, MaxFireMode 0, excluded from the after-shot lock (L479325) |
| M79 | 143 | carrier | primary | GL HE/FRAG/SMOKE (176/179/178), GL FRAG forced into slot 2 | 8 x 1, FireWait 1.5 |
| GL HE / FRAG / SMOKE | 176 / 179 / 178 | rounds | equipment | 8 x 1; FireWait 0.1 | MV 40 (400 u/s), Arming 10 m (not SMOKE), RAS + 0.5, Timer1 10 |
| LAW ("AT-4") | 145 | rocket carrier | equipment, SlotCost 2 | pair slot = `LAW HEAT` (185) | Cap 1 x 1, MaxFireMode 0 |
| LAW HEAT ("AT-4 HEAT") | 185 | rocket round | the pair slot | 1 x 1; FireWait 3 | MV 20 (200 u/s), `AccelerationFactor` 98 (980 u/s^2), Arming 10 m, Backblast, RAS + 1 s, ReloadDelay 1, Timer1 20 / 20.1, impact 20 + blast 20 in 15 m |
| RPG LAUNCHER | 146 | rocket carrier | equipment, SlotCost 2 | pair slot = `RPG` (186) | Cap 1 x 2 |
| RPG | 186 | rocket round | the pair slot | 1 x 1; FireWait 3 | MV 40 (400 u/s), AccelerationFactor 98, Arming 10 m, Backblast, RAS + 1 s (feeds the next round, C1.1), Timer1 20 / 20.1, 20 + 20 in 15 m |

The terrorist valves `m79`, `mglmk1`, `glfrag/glsmk/glhe`, `rpg`, `rpg_ammo`; the SEAL valves `m4acarbine_203`, `m16203`,
`203he/203smk/203frag`, `law` (INVENTORY §G). `SLOT_OF_LAUNCHER_READING`: whether LAW/RPG/M79/MGL sit in the primary or an
equipment slot of the default kits -- no default kit on the 22 maps carries one (research 91 §14).

#### C4.2 Selecting the round: a fire mode

`kit+0x6fc[slot]` is the slot's mode byte. `FUN_005c6600(kit, slot, mode)` (L479603-479660): if the slot holds a carrier
(`FUN_003c5d80`: IDs 52, 61, 63, 142, 143, or class 145-150) and the mode is > 3, the slot **redirects** to the kit slot
whose item ID equals the mode and still holds rounds. Everything that fires, reloads or draws the HUD goes through it
(`FUN_005c3740`, `FUN_005c3780`, `FUN_005c6920`). The switch (`FUN_005c4600` L478555-478650): mode + 1; past
`MaxFireMode` on a carrier `FUN_005c4480`/`FUN_005c3ee0` pick the next round ID the kit holds (0 when none -> wrap to
the rifle modes); refused while magnified. At spawn a mode 0 is cycled up (research 84 §6), so the MGL/M79/LAW/RPG come
up on their first round. `FUN_005c67d0` finds the carrier back from a round (the launcher for class 171, the rocket
carrier for class 185). Firing a grenade launcher round (`FUN_005bd6d0`: carrier in `FUN_003c5cd0` = 52, 61, 63, 142,
143 and mode >= 4) takes the muzzle point from the model node `firepoint_203` (0x65f8b8, L475528-475531) and, for the
player (controller vtable +0x2c = `FUN_005431f0` returns 1), `FUN_005bf8a0(MV of the round, ...)` lofts the aim:
`dir.y += 0.025` up to 12 times until `v t y - 49 t^2 >= dy` at the aimed point (L475566-475575) -- **the round is
aimed at the reticle's target, not flat**. `LOFT_TOLERANCE_READING`: `FUN_0052eb60(&h, 0x650970, 0x650978)`'s bounds.

#### C4.3 Flight, arming, impact

- Launch `FUN_003cb1a0`: rocket rounds (class 185) launched with the owner flags clear and a visual take `v = 0 x dir`,
  else `MV x dir` (L320723-320730) -- `ROCKET_LAUNCH_SPEED_READING` (which branch the player's LAW/RPG takes).
- Flight `FUN_003ca5a0`: grenade rounds fall at 98 u/s^2 (C1.8); rockets (class 185, `+0x7c == 0`) add
  `AccelerationFactor x dt` along their normalised velocity each tick (L320303-320346) and do not fall.
- Hit `FUN_003c8920` (L319439-319462): if the fired record's ArmingDistance > 0 and the hit is closer than it to the launch
  point (`+0x3c`), the round is a dud: velocity x `DAT_003e1510` (0.5), fuse `+0x8c` = 9999999, flag bit 0, and it
  bounces (`FUN_003c8f50`, research 85 §5.2). Otherwise it goes off (`EXPLODE_ON_IMPACT_READING`: the branch past
  L319462 not read line by line).
- Timer1 (10 s rounds, 20 s rockets) self-destructs a round still flying.

#### C4.4 The backblast

`FUN_003d2d70` (L325541-325560) when `+0xd5`: builds `-dir`, `-vel` and a point 9 u (0x41100000) along `dir` from the
muzzle, gets record 0x9f (`Backblast`, 159) and fires it with the muzzle position, `-dir`, `-vel`
(`BACKBLAST_ORIGIN_READING`: the 9-u point is computed but the call passes the muzzle). `Backblast`: MV 0, Timer1 0,
Timer2 0.1, ammo `Backblast Ammo` 6 damage in 7 m (70 u), Sound_Radius 800. So standing behind (or beside) a firing
LAW/RPG within 7 m is hurt.

### C5. Explosives

#### C5.1 C4 (151)

- **Placing** (`FUN_005be9a0`, class -0x69, L475378-475470): the body's current action object (`body+0x3dc`) must expose
  an interface (`+0x94`) that accepts the kit (`vtable +0x10(kit+0x8a0)`) -- a **C4 target** (`C4_TARGET_READING`: which
  map objects -- the `c4` valve's 16 on MP61/62/73 suggests the Breach objectives); a ray from the head node
  (`+0x2e8`) must land (`FUN_005aa6d0`), `body+0x208 < 396` and `+0xe84 == 0` (not moving) (`C4_REACH_READING`: what
  `+0x208` measures). Then the action 0x3e plays, `kit+0x87c` = 99.0 driven by the action's callback (`LAB_005bfe40`,
  rate 0.45) -- `C4_PLANT_TIME_READING`. Otherwise the kit switches back to the previous slot.
- **Setting** (`FUN_005c1970` L476900-476960): at the end the charge is put at the ray's point on the target
  (`FUN_005bc730(..., target, target)` attaches it to the target's frame, L473981-473987), refused on an
  `INVISIBLE_DI` surface (string 0x65f8c8; `C4_SURFACE_READING`: `FUN_00198f18`'s sense).
- **Going off**: not the Detonator. `FUN_005c74e0` (L480154-480200) adds the Detonator (0xc1) only when the kit holds a
  **claymore** (-0x67); `CZKit_DetonateRemoteExplosives` 0x5c0130 sets off only charges with `+0xc5` (claymore,
  `FUN_003c51b0`) within 500 u. C4 has neither `+0xc5` nor a proximity, so its `Timer1` **6 s** fuse runs from placing
  (C1.13). Blast: `C4 Ammo` 18 in 5 m (50 u), `IgnoreExplosionDI` (ammo `+0x28 & 2` -> projectile `+5 & 2`,
  L320755-320756; `IGNORE_EXPLOSION_DI_READING`: its effect), Timer2 0.1, Sound_Radius 600.

#### C5.2 Claymore (153) and the Detonator (193)

Research 85 §9.7 / §9.7.1 hold it (placed 1.3 s into `seal_place_claymore`, max 4, Detonator within 500 u). Record:
MaxFireMode 3, 4 x 1, no Timer1 (9999999), Timer2 10, `Claymore Ammo` 16 in 25 m, `Volitile` (ammo `+0x28 & 1`,
read at L320625 by `FUN_003d4400`: `VOLATILE_READING` -- set off by other blasts?).

#### C5.3 PMN mine (158)

Placed as the claymore (the `0x98-0x9a, 0x9e` branch, L476887-476889 and L476960-476975). `FUN_005bc730` adds type 0x9e to
the proximity list 0x4b5238 (research 85 §9.7.1). **Arming:** the actor tick `FUN_00543930` (L410270-410310) tests a mine
only when its `+0x8c` (Timer1, **8 s**) has run to <= 0; then an actor whose origin is within `ProximityDistance` (1 m ->
square 100 u^2, 10 u) sets it off (`FUN_003c5730`). Any actor -- the owner and teammates included
(`PMN_FRIENDLY_READING`: no team test seen in that loop). Timer2 10; `PMN Ammo` 6.5 in 4 m, `Volitile`; Sound_Radius 800.

### C6. The reticle and the scope overlay per weapon

`FUN_005be300` (L474894-474950), kept at `kit+0x54`, sent to `BitmapReticule_ChangeReticule` 0x213e20 (research 84 §9):

| weapon | unscoped set | scoped |
|---|---|---|
| state 4 (the 9x/binocular view) | 7 `ret_binocs` | -- |
| any weapon at magnification > 1.01 | -- | 5 `ret_scope_01` + `ret_scope_02` (the F2000 skips `_02`) -- one overlay for every scope |
| carrier in a round mode: MGL, M79, LAW, RPG always; M203 rifles/F2000 when the mode >= 5 | 3 `ret_rocket` | -- |
| M203 rifles/F2000 in rifle modes | 1 `ret_rifle` | 5 |
| pistols 4-30 | 0 `ret_sidearm` | (9x view: 7) |
| SMG 31-50, rifles 51-80, MG 91-100, snipers 101-120 | 1 `ret_rifle` | 5 |
| shotguns 81-90 | 2 `ret_shotgun` | -- |
| grenades 121-140, explosives/rounds 153-189 | 4 `ret_grenade` | -- |
| C4 151, Satchel 152 | none | -- |
| gear 190-253 (thermal, 2X, detonator, binoculars) | 0 | -- |
| designator 11 | 9 | -- |

The M203 item (141) itself falls through to none. Colour grey (130,130,130) while the aimed point is inside the
fired round's ArmingDistance (L70235-70257: `if (arming^2 <= d^2) normal colours`). The "range" readout and ZOOM line:
research 84 §9. The thermal scope changes no bitmap, only the lens effect (C7).

### C7. The thermal scope (195) and 2X

- **Record**: `Thermal Scope`, no ammo, `ModelName detonator` placeholder, `IconTextureName thermal_icon.tif`, Encumbrance 4.
- **Selectable** in the in-game select only when another slot holds a sniper-class (101-120) weapon (`FUN_0023c390`
  L87400-87411), and never twice (the unique list 194, 195, 158, 153, 185-189, 145, 146, L87443-87447).
- **The model**: `FUN_005b82e0` (L471451-471530): with 195 in the kit and a class-'e' weapon, the sniper's
  `scope` node (0x65f818) is hidden and `thermal_scope` (0x65f820) shown; without it, the reverse. Research 79 §2: the
  `scope`/`thermal_scope` nodes exist on four sniper models.
- **The view**: `FUN_001f0750` (L53084-53160), view states 5-12 (scoped): `FUN_005433c0(body, 0)` = "the kit holds
  0xc3" (`FUN_005c86f0`) -> lens mode 2, the zAnim `to_thermal_lens_fx` (loaded by name at L52689 from string 0x3e28b0);
  otherwise `to_starlight_scope_lens_fx` (mode 4, night map) or `to_scope_lens_fx` (mode 5). The zAnims are in the map
  archives (`to_thermal_lens_fx` found in MP2, MP6, MP9, MP11, MP52, MP53, MP61, MP71, MP73, MP81 `.ZDB` by byte
  search). **Zoom unchanged** (the magnification is still the weapon's `ZoomMode`). `THERMAL_LENS_FX_READING`: what the
  zAnim does (colour matrix / render mode) -- not decoded here; research 89's command set would read it.
  **Read in M5 (2026-09-30):** its own sequence is two stops, four `SCALE_COLOR` (command 35, `FUN_00264580`), a
  `VALVE`, an `IRIS_EFFECT` (34) and a `CAMERA` (28) (the names: `FUN_0025bc20`'s registrations L106891-106900, strings
  0x3eceb0-0x3ecf30). `SCALE_COLOR` sets rows of the lit-colour matrix the night vision uses (`FUN_003b76b0`: `0.33
  rgb, 3.03 a`); a draw takes the row of its node's `+0x5a & 3` (`FUN_003b6870` L308209-308249) -- the world 0, a
  character's model and gear 2 (`FUN_00313240(model, 2)` L406210/406227), the kit's weapons 2 (L480099). The thermal
  rows: 0 (0.1, 0.33, 0.7, 0) a cold blue at the lit brightness, 1 black, 2 (0.5, 0.3, 0, 128) a bright orange, 3
  (0.9, 0.65, 0, 50) (no retail setter). The plain scope's `to_scope_lens_fx` sets the neutral (1, 1, 1, 0) on all
  four, which `FUN_003b7170` treats as off; the starlight's has no `SCALE_COLOR`. `viewer/src/lensFx.ts` and
  `nightVision.ts` port the rows; the two other commands stay the reading. The `scope`/`thermal_scope` nodes are on the
  M82A1A, M40A1, M87ELR and both SR-25s (`stoner_sr25`), not on the Dragunov (`test/sights.test.ts`, MP2).
- **2X** (194): C0 row 24. `magazinesCarried` in the viewer already models it (research 84 §18).

### C8. Holsters: where the carried weapons hang

`CZSealBody_AddWeapon` 0x553290 (L419019-419060) makes a holder node per kind and parents it to a bone
(`FUN_0028ebe0`): `rifle` (1) on `body+0x300` **rhand** when `+0xf79 == 1` (rifle in hand) else `+0x2fc` **spinelo**;
`pistol` (2) on rhand when `+0xf79 == 2` else `+0x304` **hips**; `grenade` (3) always rhand. The bone slots are named
at L419600-419640 (strings 0x65c4e0-0x65c510 read from the ELF: `lhand` +0x2f8, `spinelo` +0x2fc, `rhand` +0x300,
`hips` +0x304, `head`, `neck`, `spinehi` +0x310). The body's set-up (L419672-419687) adds a `launcher` node on
**spinehi** (`param_1[0xc4]`), a `weapon` node, and registers `rifle_out` as an animated node (`FUN_0058b630`). The
motion pack animates `rifle`, `pistol`, `launcher`, `back`, `rifle_out` (research 77 §4), so the slung pose is the
clip's track for that node relative to its bone -- `HOLSTER_TRACK_READING` (the tracks' values in the idle/run clips
not probed). The visible thigh holster is gear (`seal_holster` -> `gear_holster` on rthigh, research 78 §5.2), not the
pistol's parent.

### C9. The HUD weapon box per class

Research 87 §1 and 84 §18 own the layout. Per class:
- **Icon** (`FUN_005be050(kit)` -> the current effective item's `IconTextureName`, L85226-85230): e.g. `m4carbine203_icon.tif`,
  `mglmk1_icon.tif`, `m79_icon.tif`, `AT4_icon.tif`, `RPG_icon.tif`, `c4.tif`, `PMN_mine_icon.tif`, `claymore_icon.tif`,
  `detonator_icon.tif`, `thermal_icon.tif`, `double_ammo_icon.tif` (C-table).
- **Fire-mode row** `FUN_00237b40` (L85254-85300): the four cells' vtable `+0x1c` shows, `+0x18` hides; mode 3 shows
  all four `firemode.tif` cells, 2 three, 1 one; **mode > 3 hides all four and shows the first cell with the round's icon**
  (`FUN_005c6530(kit, id)` -> `FUN_005be1d0` = that slot's icon, L85218-85224): `firemode_203_he.tif`,
  `firemode_203_frag.tif`, `firemode_203_smoke.tif` (M203 and GL rounds), `firemode_AT4.tif`, `firemode_RPG.tif`.
- **Rounds / MAGs**: through the redirected slot, so a launcher in round mode shows that round slot's count
  (`HUD_ROUND_MODE_COUNT_READING`: not traced through `FUN_005c3890` with a round mode).

### C10. Per-class summary

| class (ID range, `FUN_003d1a60` L324329) | keys that distinguish it | behaviour | source |
|---|---|---|---|
| pistol 4-30 | MaxFireMode 1 (Model 18 + SingleMode/AutoMode), NumZoomModes 1, Encumbrance 4 | semi (Model 18 semi/auto); zoom goes to the 9x view; reticle set 0; `pistol` node on hips; `Pistol reload` clips | C1.3, C6, C8, C1.2 |
| SMG 31-50 | MaxFireMode 3 | semi/burst/auto; tracer every 4th unless suppressed (HK5SD 33); reticle 1 | C1.3, C1.11 |
| rifle 51-80 | M16A2s MaxFireMode 2; M14/SA-80/Steyr Aug (68) semi+auto; 552/552SD/M4A1s/SA-80/Groza scopes; 52/61 carriers | burst = 3 rounds at FireWait x0.8; M203 rifles carry launcher round modes | C1.3, C4.2 |
| shotgun 81-90 | `12 Gauge` NumProjectilesFired 4, Blowback 1/4 m; Spas/Jackhammer ReloadTime 2 + ReloadDelay 0.5; 870 ReloadAfterShot + `.SHOTGUN_COCK` | 4 cone rays, one shell a pull; victim-side pellet count; blowback push; 870 pump lock 0.01 s (misspelt key) + `Shotgun pump` clip | C2 |
| MG 91-100 | AutoMode only; M60E3 ReloadTime 3, M63A 2.5; Encumbrance 3; 75-100 rounds x 2 | auto only; standing reload stretched | C1.2, C1.3 |
| sniper 101-120 | NumZoomModes 2-3; M40A1/M87ELR ReloadAfterShot + 0.5 | bolt lock 0.5 s; 101-103 `Shotgun reload` clips; thermal node swap; scope set 5 | C3, C7 |
| grenade 121-140 | Timer1/2, MV 0.1 | research 85 | research 85 |
| launcher 141-144 | M203 item Cap 0; MGL 6x2 MaxFireMode 0; M79 8x1 | fire through round modes; `firepoint_203`; auto-loft; set 3 | C4 |
| rocket 145-150 | SlotCost 2, MaxFireMode 0 | pair slot holds the round; `launcher` node on spinehi | C1.7, C4 |
| placed 151-170 | C4 Timer1 6; claymore Timer2 10 + Detonator; PMN Timer1 8 + ProximityDistance 1 | C4 timed on a target; claymore remote; PMN proximity after 8 s arming | C5 |
| launcher rounds 171-184 | ArmingDistance 10, ReloadAfterShot + 0.5, MV 27/40, Timer1 10 | 98 u/s^2 fall; dud inside 10 m; 0.5 s lock | C4.3 |
| rocket rounds 185-189 | HasBackblast, AccelerationFactor 98, Arming 10, RAS + 1, Timer1 20 | accelerate, no fall; backblast 6 dmg in 7 m; RPG fed one round at a time | C4 |
| gear 190-200 | 195 thermal, 194 2X, 193 Detonator | thermal lens + node; mags x2; claymore trigger | C5.2, C7 |

### C11. The rare keys of every in-scope record (disc probe)

`probe/c-rare.ts rare` over `disc/RUN/ZWEAPON.ZAR/zweapon.rdr`, values as in the file (metres, seconds);
`flag` = a key present without a value (the parser's presence test), `·` = absent (the default of C0 row 2 applies).
`TracerTextureName` is `(null)` on every row and unread (C1.11), so its column is dropped. Left out (never enabled in
MP, INVENTORY §G, or internal): F2000 and its three rounds, RED SMOKE GRENADE, BLUE CHEM LIGHT, Satchel, MPBOMB,
FULL_SLOT, EQUIP_NONE, Designator, Binoculars, both Kevlars, air_to_ground_missile, exploding_fuel, Satchel Explosion,
ARTILLERY SHELL and the three turrets (their notable values: `MGL FRAG TURRET` is the only `Gravity_Acceleration` 3.9;
PKM/LMG TURRET ReloadDelay 0.5; `F2000 FRAG` fires `M203 FRAG Ammo`). Abbreviations: MaxFM MaxFireMode, NZoom
NumZoomModes, Cap Ammo_Capacity, RelTime ReloadTime, RelDelay ReloadDelay, RAS ReloadAfterShot, RDAS
ReloadDelayAfterShot, Arming ArmingDistance, Backblast HasBackblast, Encumb Encumbrance, SoundR Sound_Radius, MuzzleV
Muzzle_Velocity.

| record | ID | FireWait | MaxFM | Single | Auto | NZoom | Zoom1 | Zoom2 | Cap | Mags | RelTime | RelDelay | RAS | RDAS | Arming | Backblast | SlotCost | Gravity | Timer1 | Timer2 | Encumb | SoundR | MuzzleV |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Model 18 | 14 | 0.06 | 1 | flag | flag | 1 | · | · | 17 | 3 | · | · | · | · | · | · | · | · | · | · | 4 | 70 | 340 |
| Mark 23 | 15 | 0.2 | 1 | · | · | 1 | · | · | 12 | 3 | · | · | · | · | · | · | · | · | · | · | 4 | 60 | 270 |
| F57 | 4 | 0.2 | 1 | · | · | 1 | · | · | 20 | 3 | · | · | · | · | · | · | · | · | · | · | 4 | 60 | 650 |
| DE .50 | 7 | 0.3 | 1 | · | · | 1 | · | · | 7 | 3 | · | · | · | · | · | · | · | · | · | · | 4 | 80 | 436 |
| M9 | 5 | 0.18 | 1 | · | · | 1 | · | · | 13 | 3 | · | · | · | · | · | · | · | · | · | · | 4 | 60 | 390 |
| 226 | 6 | 0.18 | 1 | · | · | 1 | · | · | 15 | 4 | · | · | · | · | · | · | · | · | · | · | 4 | 45 | 340 |
| Mark 23SD | 16 | 0.2 | 1 | · | · | 1 | · | · | 12 | 3 | · | · | · | · | · | · | · | · | · | · | 4 | 4.5 | 270 |
| 9mm Pistol | 8 | 0.18 | 1 | · | · | 1 | · | · | 13 | 5 | · | · | · | · | · | · | · | · | · | · | 4 | 4 | 351 |
| P228 | 12 | 0.18 | 1 | · | · | 1 | · | · | 15 | 4 | · | · | · | · | · | · | · | · | · | · | 4 | 50 | 340 |
| SR-1 Gyurza | 13 | 0.18 | 1 | · | · | 1 | · | · | 18 | 4 | · | · | · | · | · | · | · | · | · | · | 1 | 60 | 340 |
| Spas 12 | 81 | 0.45 | 1 | · | · | 1 | · | · | 12 | 3 | 2 | 0.5 | · | · | · | · | · | · | · | · | 1 | 65 | 393 |
| JACKHAMMER | 83 | 0.3 | 1 | · | flag | 1 | · | · | 12 | 3 | 2 | 0.5 | · | · | · | · | · | · | · | · | 1 | 65 | 393 |
| 870 | 84 | 0.75 | 1 | · | · | 1 | · | · | 8 | 5 | · | 1 | flag | · (file has `ReloadAfterShotDelay 0.8`: unread) | · | · | · | · | · | · | 1 | 65 | 393 |
| M16A2 | 51 | 0.1 | 2 | · | · | 1 | · | · | 30 | 4 | · | · | · | · | · | · | · | · | · | · | 1 | 60 | 948 |
| M16A2-M203 | 52 | 0.1 | 2 | · | · | 1 | · | · | 30 | 4 | · | · | · | · | · | · | · | · | · | · | 2 | 60 | 991 |
| M4A1 | 54 | 0.12 | 3 | · | · | 2 | 2.5 | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 100 | 921 |
| M4A1 SD | 62 | 0.14 | 3 | · | · | 2 | 3 | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 10 | 900 |
| M4A1-M203 | 61 | 0.14 | 3 | · | · | 1 | · | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 2 | 65 | 921 |
| 552 | 57 | 0.15 | 3 | · | · | 2 | 3 | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 65 | 725 |
| 552SD | 67 | 0.15 | 3 | · | · | 2 | 3 | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 40 | 725 |
| AK-47 | 58 | 0.16 | 3 | · | · | 1 | · | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 100 | 710 |
| AKS-74 | 59 | 0.13 | 3 | · | · | 1 | · | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 155 | 900 |
| M14 | 60 | 0.12 | · | flag | flag | 1 | · | · | 20 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 150 | 858 |
| SA-80 A2 | 64 | 0.1 | 1 | · | flag | 2 | 4 | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 60 | 940 |
| AK-105 | 65 | 0.13 | 3 | · | · | 1 | · | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 100 | 900 |
| KBP OTs-14 Groza | 66 | 0.11 | 3 | · | · | 2 | 3 | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 125 | 900 |
| M60E3 | 91 | 0.14 | · | · | flag | 1 | · | · | 100 | 2 | 3 | · | · | · | · | · | · | · | · | · | 3 | 110 | 853 |
| M63A | 92 | 0.12 | · | · | flag | 1 | · | · | 75 | 2 | 2.5 | · | · | · | · | · | · | · | · | · | 3 | 500 | 990 |
| .PKM | 93 | 0.12 | · | · | flag | 1 | · | · | 75 | 2 | · | · | · | · | · | · | · | · | · | · | 3 | 500 | 990 |
| HK5 | 31 | 0.1 | 3 | · | · | 1 | · | · | 30 | 4 | · | · | · | · | · | · | · | · | · | · | 1 | 70 | 375 |
| HK5SD | 33 | 0.12 | 3 | · | · | 1 | · | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 5 | 285 |
| F90 | 34 | 0.09 | 3 | · | · | 1 | · | · | 50 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 70 | 375 |
| 9mm Sub | 37 | 0.075 | 3 | · | · | 1 | · | · | 60 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 70 | 375 |
| Steyr Aug | 68 | 0.09 | 1 | · | flag | 2 | 2.5 | · | 30 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 70 | 375 |
| MP5K | 38 | 0.075 | 3 | · | · | 1 | · | · | 30 | 6 | · | · | · | · | · | · | · | · | · | · | 1 | 70 | 375 |
| M82A1A | 101 | 2.1 | 1 | · | · | 3 | 8 | 16 | 10 | 3 | · | · | · | · | · | · | · | · | · | · | 3 | 135 | 843 |
| M40A1 | 102 | 0.5 | 1 | · | · | 3 | 6 | 12 | 25 | 1 | · | · | flag | 0.5 | · | · | · | · | · | · | 1 | 170 | 777 |
| M87ELR | 103 | 0.7 | 1 | · | · | 3 | 8 | 16 | 10 | 3 | · | · | flag | 0.5 | · | · | · | · | · | · | 1 | 175 | 853 |
| SR-25 SD | 105 | 0.15 | 1 | · | · | 2 | 8 | · | 20 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 10 | 853 |
| SR-25 | 106 | 0.15 | 1 | · | · | 2 | 8 | · | 20 | 3 | · | · | · | · | · | · | · | · | · | · | 1 | 130 | 853 |
| Dragunov | 104 | 0.15 | 1 | · | · | 2 | 8 | · | 10 | 4 | · | · | · | · | · | · | · | · | · | · | 1 | 160 | 777 |
| Detonator | 193 | 0.1 | 1 | · | · | 1 | · | · | 0 | 0 | · | · | · | · | · | · | · | · | · | · | 4 | 0 | 0 |
| Thermal Scope | 195 | 0.1 | 1 | · | · | 1 | · | · | 0 | 0 | · | · | · | · | · | · | · | · | · | · | 4 | 0 | 0 |
| M67 | 121 | 0.1 | 1 | · | · | 1 | · | · | 3 | 1 | · | · | · | · | · | · | · | · | 3 | 3.1 | 4 | 700 | 0.1 |
| HE | 126 | 0.1 | 1 | · | · | 1 | · | · | 3 | 1 | · | · | · | · | · | · | · | · | 3 | 3.1 | 4 | 650 | 0.1 |
| AN-M8 | 122 | 0.1 | 1 | · | · | 1 | · | · | 3 | 1 | · | · | · | · | · | · | · | · | 3 | 40 | 4 | 3 | 0.1 |
| Mark141 | 123 | 0.1 | 1 | · | · | 1 | · | · | 6 | 1 | · | · | · | · | · | · | · | · | 1.5 | 1.6 | 4 | 10 | 0.1 |
| Claymore | 153 | 0.1 | 3 | · | · | 1 | · | · | 4 | 1 | · | · | · | · | · | · | · | · | · | 10 | 4 | 800 | 0 |
| PMN Mine | 158 | 0.1 | 3 | · | · | 1 | · | · | 4 | 1 | · | · | · | · | · | · | · | · | 8 | 10 | 4 | 800 | 0 |
| C4 | 151 | 0.1 | 1 | · | · | 1 | · | · | 4 | 1 | · | · | · | · | · | · | · | · | 6 | 0.1 | 4 | 600 | 0 |
| M203 | 141 | 2 | 1 | · | · | 1 | · | · | 0 | 0 | · | · | · | · | · | · | · | · | · | · | 4 | 3 | 921 |
| M203 HE | 171 | 1 | 1 | · | · | 1 | · | · | 6 | 1 | · | · | flag | 0.5 | 10 | · | · | · | 10 | 10.1 | 4 | 200 | 27 |
| M203 FRAG | 175 | 1 | 1 | · | · | 1 | · | · | 6 | 1 | · | · | flag | 0.5 | 10 | · | · | · | 10 | 10.1 | 4 | 200 | 27 |
| M203 SMOKE | 173 | 1 | 1 | · | · | 1 | · | · | 3 | 1 | · | · | flag | 0.5 | · | · | · | · | 3 | 40 | 4 | 3 | 27 |
| MGL | 142 | 0.25 | 0 | · | · | 1 | · | · | 6 | 2 | · | · | · | · | · | · | · | · | 0 | 0 | 2 | 3 | 921 |
| M79 | 143 | 1.5 | 0 | · | · | 1 | · | · | 8 | 1 | · | · | · | · | · | · | · | · | 10 | 10.1 | 2 | 3 | 921 |
| GL HE | 176 | 0.1 | 1 | · | · | 1 | · | · | 8 | 1 | · | · | flag | 0.5 | 10 | · | · | · | 10 | 10.1 | 4 | 200 | 40 |
| GL FRAG | 179 | 0.1 | 1 | · | · | 1 | · | · | 8 | 1 | · | · | flag | 0.5 | 10 | · | · | · | 10 | 10.1 | 4 | 200 | 40 |
| GL SMOKE | 178 | 0.1 | 1 | · | · | 1 | · | · | 3 | 1 | · | · | flag | 0.5 | · | · | · | · | 3 | 40 | 4 | 3 | 40 |
| LAW | 145 | 0.25 | 0 | · | · | 1 | · | · | 1 | 1 | · | · | · | · | · | · | 2 | · | · | · | 2 | 3 | 101 |
| LAW HEAT | 185 | 3 | 1 | · | · | 1 | · | · | 1 | 1 | · | 1 | flag | 1 | 10 | flag | · | · | 20 | 20.1 | 4 | 200 | 20 |
| RPG LAUNCHER | 146 | 0.25 | 0 | · | · | 1 | · | · | 1 | 2 | · | · | · | · | · | · | 2 | · | · | · | 2 | 3 | 921 |
| RPG | 186 | 3 | 1 | · | · | 1 | · | · | 1 | 1 | · | 1 | flag | 1 | 10 | flag | · | · | 20 | 20.1 | 4 | 200 | 40 |
| Backblast | 159 | 0.1 | 3 | · | · | 1 | · | · | 1 | 1 | · | · | · | · | · | · | · | · | 0 | 0.1 | 4 | 800 | 0 |
| Double Ammo Load | 194 | 0.1 | 1 | · | · | 1 | · | · | 0 | 0 | · | · | · | · | · | · | · | · | · | · | 4 | 0 | 40 |

Ammo keys that change behaviour (`ZAMMO`, `FUN_003cedb0` L322629-322735): `12 Gauge` NumProjectilesFired 4,
Blowback_Falloff 1, Blowback_End 4; `PMN Ammo` ProximityDistance 1, Volitile; `Claymore Ammo` Volitile; `C4 Ammo`
IgnoreExplosionDI; `LAW HEAT Ammo` and `RPG Ammo` AccelerationFactor 98 (default 1 x10 = 10).

### Placeholders (reader C)

| name | what is unknown | searched |
|---|---|---|
| `ENCUMBRANCE_READER_NOT_FOUND` | any reader of weapon `+0x38` (Encumbrance) | getters L324300-325700; `lb`/`lbu ...,0x38(` over all 14,880 `recomp/retail/output/*.cpp`; reCOM `m_encumbmod` (no user) |
| `SOUND_RADIUS_MP_USE_READING` (*note only*) | whether anything but the AI perception broadcast consumes the fire stimulus in MP | `FUN_003d2d70` L325585-325596; `FUN_0050ee30` listeners list 0x66a08c not walked |
| `LAUNCHER_RELOAD_CONDITION_READING` (*note only*) | what `body+0x528 == DAT_0044d408` means (selects `launcher_reload`) | `FUN_005a82e0` L462833; writes of `+0x528` not traced |
| `PUMP_BLOCKS_FIRE_READING` (resolved 2026-09-30, M4: yes -- `FUN_005a7ab0` L462527-462540, the fire gate's reload test, lists `Shotgun pump`/`crouch`/`prone pump` (`DAT_003df0b8/c0/c8`), the shotgun reloads and `Rifle m203 reload` (`DAT_003debf8`); `viewer/src/firearms.ts`, `fire.ts` hold the fire for the after-shot clip) | whether the after-shot clip (`Shotgun pump`, bolt) itself refuses fire after the kit lock ends | `FUN_005c3000` L477643; `FUN_00588bc0` action flags not read; `motion.rdr` `NoFire` on those clips not probed |
| `HOLSTER_TRACK_READING` (*note only*) | the local pose of the `rifle`/`pistol`/`launcher`/`rifle_out` nodes in the idle/walk clips (where the slung gun sits) | `CZSealBody_AddWeapon` L419019-419060; research 77 §4 (the tracks exist); the MOTION_P clips' values not probed |
| `SHOTGUN_MP_PELLET_DAMAGE_SCALE_READING` (in code, M4: `viewer/src/net/damage.ts` `pelletDamage`; reading: research 91 §1.1's, each pellet a full round's damage with the falloff and x14 -- the raw 2.5 would not pass the MP armour) | on the online receive path the pellet damage is `FUN_003d4530` (raw ImpactDamage); whether x14/falloff apply there | L459540-459570, L160838; research 91 §1.1 |
| `SHOTGUN_HIT_GUARD_RESET_READING` (*note only*) | where the victim's `+0x1048` (last projectile) is cleared, i.e. whether two volleys in quick succession both hit | writes L464602, 464737, 464743, 464757; read L434384 |
| `BLOWBACK_CONSUMER_READING` (*note only*; M4 builds no push: with its consumer untraced the room's knock path, the blast's, is not given a shotgun push) | what reads `body+0x1314..0x1324` (the shotgun push) | `FUN_0057ed10`; readers of `+0x1320` not traced |
| `LOFT_TOLERANCE_READING` (resolved 2026-09-30, M7: `FUN_0052eb60(&f, 0x650970, 0x650978)` = `abs(f - 0.0) <= 5.0`, read from the ELF's `.data`; `projectile.ts` `LOFT.band`) | the bounds `FUN_0052eb60(&h, 0x650970, 0x650978)` accepts in the launcher loft | `FUN_005bf8a0` L475688-475740; the two `.data` pairs not decoded |
| `ROCKET_LAUNCH_SPEED_READING` (in code: M2/M7) | whether the player's LAW/RPG round starts at `MV x dir` (200 / 400 u/s) or 0 and only accelerates | `FUN_003cb1a0` L320723-320730: the `+4` bits 2/4 and `param_2` of that call |
| `EXPLODE_ON_IMPACT_READING` (*note only*) | the branch after the arming test in `FUN_003c8920` (impact detonation of rounds past 10 m) read line by line | L319462-319560 skimmed only |
| `BACKBLAST_ORIGIN_READING` (in code: M2/M7) | whether the backblast spawns at the muzzle or the 9-u point `FUN_003d2d70` computes | L325560-325575 (the computed point is not in the call's arguments as decompiled) |
| `C4_TARGET_READING` | which map objects are C4 targets (`body+0x3dc` with a `+0x94` interface accepting the kit) | L475379-475388; the `c4` valve value 16 (INVENTORY) not resolved; writers of `+0x3dc` not traced |
| `C4_REACH_READING` (*note only*) | what `body+0x208 < 396` measures in the C4 plant test | L475402-475404 |
| `C4_PLANT_TIME_READING` (*note only*) | how long the plant takes (`kit+0x87c` = 99.0 driven by the action callback `LAB_005bfe40`, rate 0.45) | L475440-475452; `LAB_005bfe40` not read; the action 0x3e's clip not probed |
| `C4_SURFACE_READING` (*note only*) | the sense of `FUN_00198f18(material, "INVISIBLE_DI")` in the C4 set-down (refuse on, or require) | L476946-476950 |
| `IGNORE_EXPLOSION_DI_READING` (*note only*) | what projectile `+5 & 2` (C4's IgnoreExplosionDI) changes in the blast | set L320755-320756; readers not traced |
| `VOLATILE_READING` (*note only*) | what `Volitile` (claymore, PMN) does -- set off by another blast? | `FUN_003d4400` read at L320625 only |
| `PMN_FRIENDLY_READING` (*note only*) | whether a teammate/owner sets off a PMN | `FUN_00543930` L410270-410310 shows no team test |
| `THERMAL_LENS_FX_READING` (`viewer/src/lensFx.ts`; narrowed 2026-09-30, M5) | what the rest of `to_thermal_lens_fx` does: its `IRIS_EFFECT` (34, `FUN_00264610`) and `CAMERA` (28, `FUN_00265f20`/`FUN_00266320`) commands and its `restore_lensfx` sequence (`CAMERA_PARAMS`, `BLUR3D`, `TRUE_COLOR_SCALE`); and the held weapon's row (the game gives the kit's weapon models row 2, L480099; the viewer's held weapon keeps the world's materials, row 0). **Ported:** its four `SCALE_COLOR` (35, `FUN_00264580`) rows, read from the map's `MZANIM.ZAR` at run time -- Frostfire's (0.1, 0.33, 0.7, 0), (0, 0, 0, 0), (0.5, 0.3, 0, 128), (0.9, 0.65, 0, 50) -- on the lit colours by each draw's `+0x5a & 3` row (`FUN_003b6870`): the world row 0, the characters row 2 (L406210/406227) | strings 0x3e28b0; `FUN_001f0750` L53084-53160; the command names `FUN_0025bc20` L106891-106900 with strings 0x3eceb0-0x3ecf30 read from the ELF; the two commands' payloads dumped (`IRIS_EFFECT` flags 0x10008fff, `CAMERA` flags 0x1008000), their effect on the frame not read |
| `SLOT_OF_LAUNCHER_READING` (*note only*) | in which kit slot MGL/M79/LAW/RPG sit when picked (primary vs equipment) | `FUN_0023fef0` handles them via SlotCost/pairing; no default kit carries one (research 91 §14); menu reader (b) owns the list build |
| `NO_FIREARM_RECORD_PLACEHOLDER` (`viewer/src/loadout.ts`) | what a firearm slot fires when its item has no firearm record: the grenade launchers 141-143 (`AMMO_TYPES` names no round; their rounds are fire modes of the carrier, C4.2), the Designator (11, a pistol-class item with no round, absent from the kit table) or an empty slot; the slot's model and HUD icon stay its own record's (`ModelName`, `IconTextureName`) | `kitTableOf` reads every primary and secondary through `weaponRecord`; no default kit holds such a slot (A4) -- the slot keeps the baked record of its kind (M4A1 SD / Mark 23) | retired for the MGL (142) and the M79 (143) in M4 (read as carriers, `weaponRecord`'s `carrier`; they fire their rounds, C4.2); open for the Designator, the M203 item and an empty slot |
| `MODEL_NAME_CASE_READING` (`viewer/src/loadMap.ts` `heldWeapons`) | whether the game finds a weapon's `ModelName` in `WEAP_GEO` case aside: the SA-80 A2 (64) names `IW80A2`, every MP map's library holds `iw80a2` (all 22 probed, 2026-09-30), and the retail SA-80 draws | the model-by-name lookup's compare was not traced in the decomp; reading: case-insensitive (the other names match exactly, so only the SA-80 depends on it) |
| `HUD_ROUND_MODE_COUNT_READING` (in code, M4: `viewer/src/fire.ts`; reading: the redirected round slot's ring, as the fire takes its round -- the M203 FRAG's `6/6`, no MAGS) | the `%d/%d` and MAG counts shown while a round mode is selected | `FUN_00237760` L85128-85230 via `FUN_005c3890`/`FUN_005c49b0` with the redirect; not traced |
| `IMPACT_SIGHT_READING` (M4, `server/src/room.ts` `sightFrom`) | where the blast's line to a head (`FUN_005ac070`) starts for a round that went off where it struck (`HandleImpact` 0x3c8920 leaves it on the surface, which the line would meet at once) | the blast's queue `FUN_005ac070` not read for a lift; research 91 §5 | reading: 0.1 (`BOUNCE_LIFT`, a bounce's lift off a surface) toward the head |
| `ROUND_SPEED_SLACK_PLACEHOLDER` (M4, `server/src/room.ts`) | how far a launched round's speed on the wire may stand off its `Muzzle_Velocity` (`FUN_003cb1a0` L320727-320731, `MV x dir`) | a server tolerance: the game has no server | open (1 %, the float of the page's direction x speed) |
| `FIREPOINT_203_READING` (M4, `viewer/src/fire.ts`) | where a round mode's round leaves when the held model names no `firepoint_203` (0x65f8b8, `FUN_005bd6d0` L475528-475531) | the models decoded off Frostfire's `WEAP_GEO` (2026-09-30): `m4Acarbine_203`, `m16_M203`, `mglmk1`, `m79` name `firepoint`, `firepoint_shell`, `aimpoint`, `Gun_box` only (the weapon reader's points) | reading: the model's `firepoint`; `firepoint_203` taken first where a model has it (`heldItem.ts` `launchPoint`) |
