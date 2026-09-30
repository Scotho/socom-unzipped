# Web sprint 4 — "the arsenal" — implementation plan

> Spec: `../specs/2026-09-30-web-sprint-4-arsenal-design.md` (§3 the rulings W4.R1-R8, §4 the bar, §5 the batch, §8
> the owner's rows). Written 2026-09-30 against `claude/web-viewer-playtest-fixes` at 5c88ed5c (redotcom vitest 2004
> passed / 4 skipped at the last green, e2e 49+ at the last full run). Branch **`web-sprint-4-arsenal`**. Executed by
> one long-running cloud agent with a **$250 budget**. The Log at the foot is the live state, newest first.

**Goal:** every weapon and item a multiplayer SEAL or Terrorist may carry, each side's own arsenal per map, built to
the M4A1 SD / Mark 23 standard from the game's own data and code, and the game's in-game weapon select (`CInGameWeaponSel`)
drawn and driven 1:1, with the server owning the kit.

**Architecture:** one data module in `@s2u/scene` (`arsenal.ts`: the records, the per-map per-side arsenal, the kits,
validation) read from the disc at run time and shared by the page, the offline `Room` (loopback) and the server; the
viewer's weapon path generalised from two baked records to any record (`kit.ts`, `heldItem.ts`, `fire.ts`,
`accuracy.ts`, `zoom.ts`, `reticle.ts`, `magazines.ts`, `reloadClip.ts`, `audio.ts`, `effects.ts`, `grenade.ts`); a new
`weaponSelect.ts` (+ its pure state machine) on the HUD's bitmap/font path; the server's per-weapon tables keyed by
item id; protocol 7 with a `loadout` message.

## The agent, its model and its strategy

**Main agent: Claude Opus 5.5 (`claude-opus-5-5`), effort `high`.** **Subagents: Opus 5.5 too** — the owner's
standing rule (every dispatched agent is Opus; pass `model: "opus"` explicitly, a Workflow `agent()` call inherits
otherwise). Price per MTok, input/output: Opus 5.5 $4 / $20.
- The hard parts are reading: `CInGameWeaponSel` and its list builders in the decomp, forty-odd weapon records'
  special keys, the equipment's code paths. A wrong reading is expensive to unwind; Opus reads, Opus implements.
- **Parallelism:** at most **3 subagents at once**, each in its own git worktree off `web-sprint-4-arsenal`, each with
  a bounded file set and a brief that names the research 94 sections it implements; the main agent merges them back
  with `npm run typecheck && npm test` green before and after each merge. Good splits: M3/M4/M5 by weapon class
  (pistols+SMGs, rifles+MGs, shotguns+snipers), M7 by item family, M8 (the menu) alone.
- **Effort:** `high` for the main loop, research and the menu; `medium` for mechanical per-class passes once the first
  weapon of a class is done and reviewed.

**Budget ($250), planned split, tracked in the Log at every milestone:**

| Phase | Work | Model mix | Budget |
|---|---|---|---|
| M0 | bring-up, baseline | Opus main | $8 |
| M1 | research 94: the arsenal, the valves, the menu, per-class behaviours | Opus main + 3 Opus readers | $35 |
| M2 | the data layer (`arsenal.ts`), tests over 22 maps | Opus main (+1 Opus) | $20 |
| M3 | held models, grips, clips, holsters | Opus main + 2 Opus (by class) | $25 |
| M4 | fire and ballistics per weapon, magazines, HUD box, server tables | Opus main + 3 Opus (by class) | $30 |
| M5 | sights, zoom, scope overlays, reticles, kick, sway | Opus main + 1 Opus | $20 |
| M6 | sounds and effects per weapon | 1 Opus | $12 |
| M7 | the equipment: slots, 2X, PMN, C4, launchers, LAW/RPG, thermal, claymore | Opus main + 2 Opus | $25 |
| M8 | the in-game select menu 1:1 | Opus main + 1 Opus | $30 |
| M9 | multiplayer kits, protocol 7, server authority, remote weapons | Opus main + 1 Opus | $20 |
| M10 | polish, the derive-from-source review, README, PR | Opus main + 1 Opus reviewer | $12 |
| Reserve | debugging, the owner's feedback | — | $13 |
| **Total** | | | **$250** |

**Cost discipline:** keep the main agent's context stable (append-only notes; the plan's Log and the spec's §7 are the
memory); read the 15 MB decomp and the recompilation's `.cpp` only by `grep -n` and line ranges — never paste them
into the conversation; delegate reading-heavy work to subagents with narrow briefs; run the full e2e only at merges;
one table-driven test per concern rather than one file per weapon.

**If a phase overruns its line by 30%:** stop, write the Log, and cut scope in this order (each cut is recorded in
research 94 as not built, with its sources, so a later sprint starts from the reading):
1. The launchers and their rounds (M203 family, M79, MGL, RPG-7, LAW) — keep their records in the data layer, not the
   use.
2. The thermal scope's rendering (keep the item and its slot; draw it as the plain scope with a named placeholder).
3. The holstered models on the body (keep the held model).
4. Per-weapon remote clips beyond the class's shared set.
5. Tracers and per-weapon shell effects beyond the class's shared one.
Never cut: each side's arsenal and its server validation (W4.R2, R6), the menu (W4.R3), every enabled firearm's
record-driven fire/damage/magazine/zoom (W4.R4), the tests pinning sourced values.

## Global constraints

- **Setup:** the handoff's `HANDOFF.md`. The disc subset goes outside the repo; `SOCOM_DISC=<that dir> npm run
  extract-maps` from `web/` fills the git-ignored `web/redotcom/public/maps/` and `web/redotcom/test-fixtures/`. Play
  with `?map=MP2&mode=play&devmode` (the served assets); the offline match runs the server's `Room` in the page.
- **Tests first; every task:** `npm run typecheck && npm test && npm run build` from `web/`; the e2e suite
  (`E2E_PORT=5199 npx playwright test` from `web/redotcom`) at merges. New server tests run in Node; the multi-client
  e2e drives two pages against a local server the agent starts itself.
- **Commits:** conventional, explicit paths (`git add -- <paths>`), never `-A`/`-u`/`.`, never `--no-verify`; the
  session's co-author trailer. Push to `web-sprint-4-arsenal` only.
- **Citations:** `FUN_<retail addr>` with decomp line numbers; `DAT_<addr>` read from the retail ELF with the method;
  recompilation files by retail address (map r0004 files through `recomp/retail-to-r0004.tsv`); reCOM paths with lines;
  the demo DWARF by class and member. Placeholders named `*_PLACEHOLDER` / `*_READING` and listed in research 94's
  "Placeholders" section (the ledger test).
- **No game data, no credentials in git.** No connection to any server the agent did not start itself.
- **Keep the walk's parity:** `tools/feel-parity.ts` and `tools/playtest.ts` (research 88/90) at M3, M4 and M10.

## Tasks

### M0 — Bring-up and baseline
1. Lay out the handoff (`HANDOFF.md`), verify the manifest, `npm install`, `extract-maps`, typecheck, test, build,
   e2e; feel parity headless; unpack the recompilation archives outside the repo.
2. Log the baseline (counts, versions, failures with cause — sprint 3's cloud saw 8 timing-bound e2e failures under
   SwiftShader; record which, and hold "the same green, nothing new red").

### M1 — Research 94, the arsenal (`web/redotcom/docs/research/94-the-arsenal.md`)
Three Opus readers in parallel, one merge:
- **(a) The arsenal and its rules.** The scope table: every record, class, round, the maps and sides that enable it
  (mission.rdr `Valves`), the kits (character.rdr). `FUN_003cf1f0` (L322760): the full id-to-valve map. The mask's
  bits (1/8/9, and 16 on `c4`). The list builders `FUN_0023b9b0`/`0023bc50`/`0023c390` (in-game) and
  `FUN_002815d0`/`00281950`/`00283b50`/`00283e60` (armory): slot classes, `SlotCost`, locked slots
  (`UIDoAllSelCharsHaveLockedEquip1..3` 0x281030-50), duplicates, the default-equipment rule
  (`UIChooseDefaultEquipmentOnly` 0x281be0). How a pick reaches the body: `CCharacterWeap_SetupCharacterWeapon`
  0x53eee0, `CZSealBody_AddWeapon` 0x553290, `CZKit_Init` 0x5c7e00, the rebuild `FUN_00599b60`/`FUN_00599f00`.
- **(b) The menu.** `CInGameWeaponSel`: its methods (the demo DWARF's 56 and their SOCOM II addresses — start at
  `Init` 0x227ad0 and the vtable), its members, the seven `newweapnbkrnd.tif` loaders (`FUN_001fa360` L57229,
  `FUN_00205e00`, `FUN_0021cd40`, `FUN_00221070`, `FUN_0022ac30`, `FUN_0022ae90`, `FUN_0022cc10`), the prompts
  (`FUN_001f97b0` L56980, the ghost lines 0x3e31c0.., the state switch L56575-56600), the button glyphs 0xbd/0xbe per
  controller config (`FUN_002c6430`), the input, every state, the layout (positions, sizes, colours, the font), the
  sounds, the timing, and when a pick applies. Output: a state table with a row per state and its source.
- **(c) Per-class behaviour.** From the parser `0x3cda30` (L322125-322640) outward: what each rare key does in code
  (`ReloadAfterShot`, `ReloadDelayAfterShot`, `AutoMode`, `SingleMode`, `ZoomMode1/2`, `ReloadTime`, `ReloadDelay`,
  `ArmingDistance`, `HasBackblast`, `SlotCost`, `Gravity_Acceleration`, `Timer1/2`, `Encumbrance`, `Sound_Radius`,
  `TracerTextureName`); the shotgun's pellets; 2X ammo; the thermal scope; C4 and the detonator; the PMN; the
  launchers' flight; the scope overlays per weapon (`BitmapReticule_*` 0x213e20-0x2178c0, research 84 §9); the holster
  nodes (research 78 §5); the HUD box per weapon.
Every value cited; every unknown a named placeholder with what was searched. The Log records the note's headline.

### M2 — The data layer
`packages/scene/src/arsenal.ts`: `readArsenal(zweapon, readerc, mission)` -> every in-scope `WeaponRecord` (extend the
interface with the rare keys M1 found), each side's selectable set per map, the character types' kits, the slot rules,
`validateLoadout(side, map, type, pick)`. The page, `net/loopback.ts` and `packages/server` all read it. Tests: every
record's sourced numbers pinned (table-driven, fixture-backed + a synthetic twin); all 22 maps' sets equal the valves
through the id map; the validation's refusals.

### M3 — Held models, grips, clips, holsters
Generalise `heldItem.ts`/`weaponPose.ts`/`weaponRaise.ts`/`loadMap.ts` from the two baked models to any record's
`ModelName` (LOD pairs, the `0x70` form, research 79 §2): the grip on the hand node, the points, the class's raise /
aim / fire / reload / swap clips (`animset.rdr`, `motion.rdr`, MOTION_P), the pump and bolt cycles, the holstered long
gun and sidearm on the body's gear nodes. Remote players (`remotePlayers.ts`) draw the same.

### M4 — Fire and ballistics per weapon
`fire.ts`/`round.ts`/`accuracy.ts`/`rifleKick.ts`/`magazines.ts`/`reloadClip.ts` driven by the held record: rate, fire
modes and the switch, the bolt/pump lock, pellets, damage and falloff, penetration, the magazine ring and 2X, reload
times and clips, the HUD weapon box (icon, rounds, mags) per weapon. The server's per-weapon tables (`room.ts`,
`net/damage.ts`, `net/shotCone.ts`) keyed by item id; `RELOAD_SECONDS_PLACEHOLDER` and `KIT_PLACEHOLDER` retired.

### M5 — Sights, zoom, reticles
`zoom.ts`/`reticle.ts`/`nightVision.ts`: each weapon's zoom levels and the view states, each scope's overlay (its
bitmap and the 16:9 black sides), the thermal scope, each weapon's reticle and knock, the scoped kick, drop and sway
(research 84 §8/§15/§17), the zoom readout (research 87 §13). No pistol scope, no first person (the owner's).

### M6 — Sounds and effects
`audio.ts`/`effects.ts`: each weapon's close/med/far fire, reload, pump/bolt sounds from the banks, each
`FireAnimName` (muzzle, shell), `HitAnimName`, tracers where the record has a texture; remote players' too.

### M7 — The equipment
`kit.ts`/`grenade.ts`/`@s2u/scene projectile.ts`: three equipment slots in kit order (keys 3, 4, 5 — W4.R5), each
enabled item to the grenade standard: M67, HE, AN-M8, Mark141 (done — re-check against M1), the claymore in the match
(`CLAYMORE_PLACEHOLDER` retired), the PMN mine, C4 and its detonator (and the 16 bit), 2X ammo, the thermal scope, the
M203/M79/MGL rounds (arming distance), the RPG-7, the LAW (backblast). Server-side: placement, triggers, blasts.

### M8 — The in-game select menu, 1:1
`packages/viewer/src/weaponSelect.ts` + a pure `weaponSelectState.ts`: every state of research 94's table, opened when
the game opens it (the prompt with the right glyph; the PC key and the pad button mapped per the controller config),
drawn on the HUD path (`newweapnbkrnd.tif`, the icons, the font) at the 640x448 frame, driven by keys, pad and touch,
confirming into a `loadout` request that applies at the spawn the game applies it. Unit tests per state; e2e: die in
the offline match, open, pick, confirm, next round with the pick; the other side lists its own.

### M9 — Multiplayer kits and server authority
Protocol 7: `loadout` request/answer (validated per W4.R2/R6), the body's weapon as an item id (the codec's bytes
re-measured), the kill line's `DisplayName`; the room stores each player's kit and applies it at the spawn; remote
players draw each other's weapon, clips, sounds, muzzle. Tests: refusals, a pick surviving a reconnect, two pages of
opposite sides; `tools/mp-bots.ts` 16 + 8 still at 60 Hz with mixed kits.

### M10 — Polish and the close
A derive-from-source review: an Opus reviewer (Fable-style brief: every new number traced to its cited source,
every placeholder in the ledger, every "1:1" claim checked against the decomp or a frame) over the diff and research 94;
fix what it finds. README (the menu, the keys, the arsenal), `docs/DATA_SOURCES.md` rows, the spec's §7, the Log's
close entry with the spend, the PR to `main` (the owner merges; the server redeploy is the owner's, spec §8 O-S4-4).

## Log

*(newest first)*

- **2026-09-30 — opened** by the local controller: spec and plan written on `agent/web-s4prep` (to be cut as
  `web-sprint-4-arsenal` from the integration head); the inventory's headline in the spec's §2 and §7; the handoff zip
  built (see its `HANDOFF.md`).
