# Web sprint 4 — "the arsenal": every weapon, each team's own, and the in-game weapon select (design)

> Written 2026-09-30 by the local controller for a long-running cloud agent. Base: `claude/web-viewer-playtest-fixes`
> at e5406330 (the walk, the classic match on and offline, web sprint 3's server, the launch fixes, and 1b1ae687's
> `VITE_S2U_MULTIPLAYER` build switch -- the site's build ships multiplayer off, §1; the tree is
> `web/redotcom` + `web/landing` + `web/shared`). The sprint branch is **`web-sprint-4-arsenal`**, cut from it. The plan
> is `../plans/2026-09-30-web-sprint-4-arsenal.md`; its `## Log` is the live state. What the agent needs and cannot get
> from git is in the handoff zip (`HANDOFF.md` inside it says how to lay it out).

## 1. What was asked, and how it is read

The owner (Craig), 2026-09-30, verbatim in substance:

- **Build out the full in-game weapon-select menu** — "the original game's UI that opens a weapon-selection menu to
  swap weapons and equipment".
- **Implement EVERY weapon and its unique characteristics**, following the project's rigid method: reverse-engineer
  from the decompilation, reCOM and our own recompilation's output, **to the implementation standard of the existing
  two weapons (M4A1 SD, Mark 23)**, integrated in the game **exactly as the original does it, 1:1**.
- **All information derived from source material**, or stated plainly and recorded where that is impossible.
- **Each team has its own unique set of weapons, as SOCOM II does** — not every weapon is available to each team.
- A $250 budget, one cloud agent, as web sprint 3 ran.

Read against the repository's standing rules (`web/redotcom/README.md`, `docs/DATA_SOURCES.md`, the sprint 1-3 specs,
research 77-93):

- **"Every weapon"** is every item the game lets a multiplayer player carry: the union of the 22 MP maps' per-side
  enable lists and the character types' default kits (§2). Items no MP map ever enables (the F2000/OICW and its
  rounds, the red smoke, the blue chem light, the satchel) and the engine's internal rows (turrets, `FULL_SLOT`,
  `EQUIP_NONE`, `MPBOMB`, explosions, the artillery shell, the missile, `Backblast`) are **out**, recorded in research 94
  with the reason.
- **"The implementation standard of the existing two"** is what the M4A1 SD and the Mark 23 have today: the record
  read from `zweapon.rdr` (not baked), the model from the map's `WEAP_GEO`/`WEAP_MDL` on the right hand's held node at
  its own grip, the game's raise/aim/fire/reload/swap clips, the round (`round.ts`) with penetration and marks, the
  bloom/knock/cone (`accuracy.ts`), the rifle kick, the zoom levels and scope overlay, the reticle, the magazines and
  the reload lock, the HUD weapon box (icon, rounds, mags), the fire/reload sounds (close/med/far), the muzzle and
  shell effects, the damage and falloff on the server, remote players drawing it, and tests pinning each value to its
  source (research 84 §10 lists the call sites).
- **"1:1 as the original"** covers the menu's opening conditions, its prompt, its screens and every state, its input,
  its art, its sounds, and when a pick takes effect.

**The site's build ships multiplayer off** (owner, 2026-09-30, 1b1ae687; `packages/viewer/src/multiplayer.ts`, the
README's **Multiplayer off**). `VITE_S2U_MULTIPLAYER=off`, which `web/shared/deploy/site/deploy.sh` passes for the
site's release build, removes the settings' Online section, the PLAYERS ONLINE count and the `/rooms` poll, ignores and
strips `online=`/`mp`/`server=`, and never joins a match server; the offline match (the `Room` run in the page,
`net/loopback.ts`) stays. `npm run dev` and a plain build keep multiplayer on. So in this sprint: the arsenal, the menu
(M8) and the `loadout` request work in **both** builds through the loopback `Room` -- on the site they are single
player; everything that reaches a network server -- protocol 7 on the wire, remote players' kits, the server's refusals
over a socket (M9) -- sits behind the same switch the Online section does (`multiplayerEnabled`, the `MULTIPLAYER` gate
in `main.ts`). Nothing new may bring back an Online control, a `/rooms` request or a server connection in the off build;
`test/multiplayer.test.ts` stays green, and M9 adds a case that the off build's loadout path opens no socket.

## 2. Where it stands (the inventory; the full one is research 94's first task)

- **Code.** `@s2u/scene` `weapons.ts` already reads any `zweapon.rdr` record into `WeaponRecord` (`weaponRecord`,
  `readWeapon`), the kits (`kitWeapons`, `kitPrimaries`, `defaultPrimary`), and `weapon.ts` decodes any of the 59 weapon
  models with their named points (`firepoint`, `firepoint_shell`, `aimpoint`, `scope`, `thermal_scope`). The viewer's
  kit is fixed at `rifle, pistol, M67, HE` (`kit.ts`), the held pair baked (`HELD_RIFLE`, `HELD_SIDEARM`); the server's
  `room.ts` gives everyone that pair (`KIT_PLACEHOLDER`, `CLAYMORE_PLACEHOLDER`, `RELOAD_SECONDS_PLACEHOLDER`); the
  protocol (6) carries a weapon as 0/1 (rifle/sidearm), no kit, no character type.
- **The records.** `RUN/ZWEAPON.ZAR/zweapon.rdr`: 86 `ZWEAPON` records, 39 `ZAMMO` rounds. Every record has its range,
  velocity, magazine, mags, zoom modes, model, icon, reticle modifiers and sounds; the rarer keys say what makes a
  weapon unique: `ReloadAfterShot`/`ReloadDelayAfterShot` (bolt and pump actions), `AutoMode`/`SingleMode`,
  `MaxFireMode`, `ZoomMode1/2`, `ReloadTime`, `ArmingDistance`, `HasBackblast`, `SlotCost`, `Gravity_Acceleration`,
  `Timer1/2`.
- **Each team's arsenal is data.** Every MP map's `READERM.ZAR/mission.rdr` `Valves` holds `Enable_<x>` with a mask:
  1 the SEALs, 8 the Terrorists, 9 both, 0 neither; 16 appears only on `c4` (MP61, MP62, MP73) and is to be read.
  Frostfire: SEALs 29 items, Terrorists 28; Blizzard: 34 and 30. The decomp maps an item id to its valve
  (`FUN_003cf1f0`, L322760: id 54 -> `Enable_m4Acarbine`), called from the in-game HUD range (`FUN_0023b9b0`,
  `FUN_0023bc50`, `FUN_0023c390`) and the front-end armory (`FUN_002815d0`, `FUN_00281950`, `FUN_00283b50`,
  `FUN_00283e60`). The four SEAL and four Terrorist character types per map carry their default kits
  (`character.rdr`; research 91 §14).
- **The menu.** The in-game select is the class `CInGameWeaponSel` (`Init` at 0x227ad0; 0x1160 bytes, 45 members, 56
  methods in the SOCOM 1 demo's DWARF, research 50/55); its background `newweapnbkrnd.tif` is loaded in seven HUD
  functions; the prompt "You have died.  %c Select new weapons." (0x3e32e0, `FUN_001f97b0` L56980) and the ghost's
  "... %c Select new weapons. Press the %c button to respawn." Research 91 §4.3: the kit may be re-chosen while dead and
  is applied at the rebuild (`FUN_00599b60`, `FUN_00599f00`). The lobby's ARMORY (`UIInitializeOnlineArmory`
  0x27d8c0, `UICanCharactersSelectUIWeapon` 0x280d60, `UIChooseEquip1..3`, `dlg_equipment_mp.rdr`, `RUN/UI/WSSP_*`) is
  the front end's; the viewer has no lobby (§5).
- **Our recompilation.** Retail `recomp/output` (14,882 `.cpp`, 1,771 named) and the r0004 build's output (16,425,
  named from `recomp/socom2_names_r0004.csv`). **r0004's addresses equal retail's only below ~0x269000**; above it
  they shift (`CCharacterWeap_SetupCharacterWeapon` retail 0x53eee0 = r0004 0x543930). The zip's
  `recomp/retail-to-r0004.tsv` (from `game/r0004/match.json`, 12,071 of 14,879 functions) maps one to the other; the
  names CSVs (in git) give each name's retail address. Always cite retail addresses and decomp lines.
- **Parity frames.** None exists of the in-game select, the armory, any scope but the M4A1 SD's, or any weapon but
  the M4A1 in hand (the owner's row, §8). The sprint-3 set (`s4_pcsx2`, `s11_r0004_round1`) is in the zip again.

## 3. Rulings

- **W4.R1 — the game is the reference; derived from source, or recorded.** Every value — a record's key, a menu's
  position, a state, a timing, a sound — comes from, in this order: the disc's tables (`zweapon.rdr`, `character.rdr`,
  `mission.rdr`, `hud.rdr`, the UI scripts), the retail decompilation (cited `FUN_<addr>` + line), the retail ELF's
  `.data` (in the zip this time: `DAT_` constants research 91 could not read), our recompilation's output (retail
  addresses cited; r0004 files mapped through the tsv), the SOCOM 1 demo's DWARF (member names and layouts), reCOM
  (`research/recom` paths with lines). A value no source gives is a **named placeholder** (`*_PLACEHOLDER`, or a
  `*_READING` for a choice among sourced readings) listed in research 94's placeholder section — the placeholder
  ledger test (`tools/test/placeholderLedger.test.ts`) refuses anything else. "Stated plainly" means the note says
  what was searched and what was not found.
- **W4.R2 — each team its own arsenal, per map, as the game decides it.** What a side may select on a map is the
  map's `Valves` mask read through the game's own id-to-valve mapping (`FUN_003cf1f0`) and whatever other rule the
  decomp's list builders apply (slot class, `SlotCost`, the character type's locked slots —
  `UIDoAllSelCharsHaveLockedEquip1..3` — the 16 bit); what a player spawns with before choosing is the character
  type's `default_weapons`. A SEAL never sees a Terrorist-only weapon and the reverse; one data table (in
  `@s2u/scene`, built from the disc at run time, never baked from game data into git) feeds the page, the offline
  `Room` and the server.
- **W4.R3 — the in-game select menu, 1:1.** `CInGameWeaponSel` as the game has it: **when** it may open (read it:
  dead in classic, as a ghost, before the round starts, at a spawn?), **how** (the prompt's `%c` button per controller
  config, read from the decomp; the pad keeps that button), **every screen and state** (the slot list, the per-slot item list,
  locked/unavailable items, the highlight, the item's name/icon/description/stats if drawn, confirm, cancel, the
  default-kit choice, what the rest of the HUD does meanwhile), its art (`newweapnbkrnd.tif`, the icons, the font), its
  sounds (`UIVOICE`/`HUDUI` names the decomp calls), and **when a pick applies** (research 91 §4.3: at the next spawn;
  in classic, the next round). The menu is drawn with the viewer's HUD bitmap and font path (`hudBitmaps.ts`,
  `hudFont.ts`) on the game's 640x448 frame, the same as the scoreboard. If the in-game menu also offers the character
  type, it is built; if it does not, the type stays the server's (`DEFAULT_CHARTYPE_PLACEHOLDER`).
  **The PC key and the touch control that open it are not the game's** (the game draws a pad glyph; the owner has named
  no key). Each is a reading: `WEAPON_SELECT_KEY_READING` (one key, free of every key `controlsList.ts` already binds --
  `1`-`5`, `B`, `X`, `Q`, `E`, `Tab`, `M`, `F`, `G` and the rest listed there) and `WEAPON_SELECT_TOUCH_READING` (an
  on-screen button shown only while the prompt is), each listed in research 94's Placeholders section with the
  reason, shown in the prompt in place of the pad glyph when the keyboard or touch is the input, in both Controls
  lists and the README, and named in the close PR so the owner confirms or overturns them (O-S4-3). The agent does not
  pick one silently.
- **W4.R4 — every weapon's behaviour is its record's.** Rate (`FireWait`), fire modes (`MaxFireMode`, `AutoMode`,
  `SingleMode`, the mode switch), damage (`ImpactDamage` of its round + `Damage_Modifier`, x14, the falloff past
  `Effective_Range` to `Maximum_Range`), penetration (`Piercing`), pellets for the shotguns (read how the 12 gauge
  splits), muzzle velocity and drop where the game uses them, accuracy (the three stances' `Reticule_Modifiers`,
  bloom, `AccBurst*`/`AccScalar*`), the reticle knock and the rifle kick, the scope sway, `RecoilPct`, zoom
  (`NumZoomModes`, `ZoomMode0..2`, the overlay per scope), the magazine (`Ammo_Capacity`, `NumMags`, the ring, the
  reload clip, `ReloadTime`, `ReloadAfterShot` + `ReloadDelayAfterShot` for the bolt and pump actions), the held model
  (its grip, `firepoint`, `firepoint_shell`, `aimpoint`, the scope node), the holster (where a carried long gun and
  sidearm hang — research 78 §5's gear), the sounds (close/med/far, reload, the dry fire if any), the muzzle and shell
  effects (`FireAnimName`, `HitAnimName`, tracers if `TracerTextureName` is set), the reticle bitmap
  (`BitmapReticule_ChangeReticule`), `Encumbrance` if the mover reads it, and `Sound_Radius`. No per-weapon number is
  hand-typed; the tests pin the reader's output against the fixture.
- **W4.R5 — the equipment slots.** A kit is the game's: primary, secondary, three equipment slots (research 91 §14,
  `UIChooseEquip1..3`). The equipment the MP maps enable: M67, HE, AN-M8 smoke, Mark141 flash, claymore, PMN mine, C4
  (+ its detonator), Double Ammo Load (2X: the magazines doubled — read how), the thermal scope, the M203 / M79 / MGL
  rounds, the RPG-7 and its round, the LAW. Each is built to the grenade code's standard (research 85): its record, its
  model, its use clip, its flight or placement, its trigger, its effect and damage on the server. The PC keys stay the
  owner's (1 primary, 2 sidearm, 3 and 4 the equipment slots in kit order); the third equipment slot's key is **5**
  (a new ruling the owner may overturn; the pad keeps the game's cycling).
- **W4.R6 — the server owns the kit.** The loadout is a request; the server validates it against W4.R2 for the
  player's side, map and character type, stores it, and applies it at the spawn the game applies it; a page cannot
  fire, reload or throw anything its server-side kit does not hold. The per-weapon tables (rate, reload lock, cone,
  damage, falloff, penetration, pellets, blast) extend from two weapons to all, keyed by the item id (`ID`), in one
  module the page and the room share (the sim boundary). The protocol goes to 7: a `loadout` request/answer, the body's
  weapon as an item id, the kill line's weapon as the record's `DisplayName` (research 91 §10). Remote players draw
  each other's weapon model, clips, sounds and muzzle.
- **W4.R7 — classic only.** The match is classic (the launch's rule; the respawn ruleset stays switched off,
  `RESPAWN_RULES_ENABLED`). The menu's respawn-only states are researched and recorded in research 94, not wired.
- **W4.R8 — the owner's boundaries and standing rulings.** No game data in git (archives, decoded bitmaps, icons,
  sounds, dumps; tests skip without fixtures and have a synthetic twin). No credentials. No deploy, no DNS, no spend;
  the agent never connects to the owner's Lightsail server or any server not started in its own session. Play mode is
  `mode=play` (`?redotcom` is its alias); the served assets are read only with `&devmode`; offline the page runs the
  match's own `Room` (loopback) — the cloud has no host to join and needs none. Standing rulings (local handoff §3):
  third person or scoped only, no first person; no pistol scope; a rifle scope's black covers the sides at 16:9; the
  swap's 0.4 s ease reading stays; the scoreboard/HUD geometry of research 87 stays.

## 4. Goal and bar

**Goal:** on any MP map, a player in `mode=play` spawns with their character type's default kit, carries and uses
every weapon and item that kit or a later pick holds exactly as the game does, and, when the game allows it, opens the
game's own in-game weapon select, sees only their side's arsenal for that map, picks a primary, a secondary and three
equipment items, and gets that kit at the spawn the game gives it — offline and on the shared server alike, the server
refusing any pick the game would refuse.

**The bar:**
1. **Sourced.** Research 94 (the arsenal) cites every value; its placeholder section lists every stand-in; the
   ledger test is green.
2. **Pinned.** A table-driven test runs every in-scope record through the reader and pins its sourced numbers (skips
   without fixtures; a synthetic twin always runs); per weapon class, tests pin the unique behaviour (the shotgun's
   pellets, the bolt action's lock, the burst, the zoom levels, the launchers' flight and arming distance).
3. **Per team.** A test over all 22 maps: each side's selectable set equals the valves' mask through the id-to-valve
   map; a server test refuses the other side's weapon, an unknown id, a locked slot, a second primary.
4. **The menu.** Every state of research 94's state table has a unit test; e2e specs (written; run where the host
   allows): die in the offline match, see the prompt, open the menu, change each slot, confirm, spawn next round with
   the pick; the other side's menu lists its own items.
5. **The standard.** Each in-scope firearm reaches the M4A1 SD's checklist (§1); each equipment item the grenade's.
   The walk's feel parity (research 88) and the playtest stay green; the existing suite stays green
   (`npm run typecheck && npm test && npm run build`, the e2e at merges).
6. **Parity.** Where a console frame exists the page is compared against it (few do; the owner's row asks for more);
   where none does, the note says so.

## 5. The batch (the plan orders and budgets it)

- **M0 — Bring-up and baseline.** Lay out the zip, `extract-maps`, the suite, feel parity; the Log's baseline.
- **M1 — Research 94, the arsenal** (no code): the scope table (every in-scope item, its class, both sides' maps), the
  valves' mask and the id-to-valve map, the list builders' rules, `CInGameWeaponSel` (members, states, input, art,
  sounds, timing), the per-class behaviours (pellets, bolt/pump, burst, launchers, 2X, thermal, C4/detonator, PMN), the
  holster, the HUD box per weapon; every unknown a named placeholder.
- **M2 — The data layer:** `@s2u/scene` `arsenal.ts`: every record, each side's arsenal per map, the kits, the
  id-to-valve table, validation — one module for page, loopback and server.
- **M3 — Held models, grips, clips:** every firearm on the hand at its grip, its raise/aim/fire/reload/swap clips per
  class (rifle, pistol, shotgun pump, bolt, MG, launcher), the holstered pair on the body.
- **M4 — Fire and ballistics per weapon:** rate, modes, damage/falloff, penetration, pellets, the bolt/pump lock, the
  magazines and reloads, the HUD weapon box, the server's tables.
- **M5 — Sights, zoom, reticles:** each weapon's zoom levels, scope overlays (and the thermal scope), reticle bitmaps,
  knock, kick, sway.
- **M6 — Sounds and effects:** fire close/med/far, reload, the muzzle and shell animations, tracers, hit effects.
- **M7 — The equipment:** the three slots, 2X ammo, PMN, C4 and detonator, the launchers and their rounds, the LAW and
  RPG, the thermal scope; the claymore into the match.
- **M8 — The select menu, 1:1:** `CInGameWeaponSel` drawn and driven, its prompt, every state, keys/pad/touch.
- **M9 — Multiplayer kits and server authority:** protocol 7, loadout validation, the spawn's kit, remote players'
  weapons, the kill lines' names, load test unchanged; the network side behind the `VITE_S2U_MULTIPLAYER` switch (§1).
- **M10 — Polish and the close:** a derive-from-source review of every new value (a Fable-style self-review pass run
  by Opus against research 94), the README, the Log, the PR.

## 6. What is not in this sprint

The front-end lobby and its ARMORY (the viewer has no lobby; the in-game menu is the entry), weapon unlocks
(`dlg_WeapUnlock.rdr`, the single-player's), the respawn ruleset, the items no MP map enables (§1), vehicles and
turrets, single-player missions, new game modes.

## 7. Findings recorded during the sprint

*(dated, newest last — the agent appends here as earlier sprints did)*

- **2026-09-30 — the prep's inventory** (the local controller): each MP map's `Valves` carry a per-side mask (1/8/9/0,
  16 on `c4`); 60 valve names are enabled on some MP map, 7 on none; all 22 MP and 12 single-player maps hold the same
  59 weapon models; r0004's function addresses equal retail's only below ~0x269000 (the zip's tsv maps them).

## 8. What the owner does (HUMAN_TASKS-style rows)

- **O-S4-1 — hand over the zip.** `C:/Projects/handoff/socom-web-sprint-4-arsenal.zip` (a tar despite the name) to the
  cloud agent privately; push `web-sprint-4-arsenal` (cut from the integration head) so the agent can clone it.
- **O-S4-2 — capture the missing console frames** on PCSX2 (retail or r0004, any MP map, classic): the in-game weapon
  select in every state (the prompt when dead, the menu open on each slot, an item highlighted, a locked/unavailable
  item if shown, confirm), one frame per scope (SR-25, M82A1A, M40A1, M87ELR, Dragunov, the 2-zoom rifles), the HUD's
  weapon box with each firearm, a Terrorist's menu, and the front-end ARMORY for reference; drop them in a folder the
  agent is told about (or a second zip). Without them the menu is built from the decomp alone and the note says so.
- **O-S4-3 — play test and rule.** At the close: play a side on two maps, open the menu, try each class; overturn any
  W4 ruling by number (e.g. W4.R5's key 5); confirm or replace the menu's PC key and touch control
  (`WEAPON_SELECT_KEY_READING`, `WEAPON_SELECT_TOUCH_READING`, W4.R3).
- **O-S4-4 — merge and deploy.** Review the PR to `main`. The server redeploy carries protocol 7 (a protocol-6 page and
  a protocol-7 server refuse each other, so a page with multiplayer on and the server move together; the existing
  deploy's `deploy.sh`). The served page's multiplayer stays **off** (`VITE_S2U_MULTIPLAYER=off` in the site's
  `deploy.sh`, §1): on the site the arsenal and the menu play in the offline match only, unless the owner flips that
  deploy flag.
