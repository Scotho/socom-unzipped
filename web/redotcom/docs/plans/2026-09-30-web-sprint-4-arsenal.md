# Web sprint 4 — "the arsenal" — implementation plan

> Spec: `../specs/2026-09-30-web-sprint-4-arsenal-design.md` (§3 the rulings W4.R1-R8, §4 the bar, §5 the batch, §8
> the owner's rows). Written 2026-09-30 against `claude/web-viewer-playtest-fixes` at e5406330 (redotcom vitest 2004
> passed / 4 skipped at 5c88ed5c's last green, plus 1b1ae687's `test/multiplayer.test.ts` -- M0 records the count; e2e
> 49+ at the last full run). The site's build ships multiplayer off (`VITE_S2U_MULTIPLAYER=off`; spec §1). Branch **`web-sprint-4-arsenal`**. Executed by
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

**Meter the spend, per milestone.** The split above rests on the work's shape alone: sprint 3's Log could record its
spend only as "not metered", so no line here is calibrated. This sprint meters it: at every milestone's end the Log
records the main agent's and each subagent's tokens in/out and the dollars they come to (from the session's usage or
cost report where the harness gives one; otherwise from the token counts at the prices above, marked *estimated*),
the milestone's total against its line, and the running total against $250. Two lines are the tightest -- **M4** ($30
for ~41 firearms' fire, ballistics, magazines, HUD box and server tables) and **M8** ($30 for a 56-method class read
from the decomp with no console frame of it): check the meter after M4's first weapon class and after M8's state
machine, and re-plan then rather than at the 30% stop. The cuts below free only ~$40, since the never-cut list holds
the bulk; an early overrun is met by trimming a class's pass to its shared behaviour, not by dropping a never-cut item.

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
the game opens it (the prompt with the right glyph; the pad button per the controller config; the PC key and the touch
control are `WEAPON_SELECT_KEY_READING` / `WEAPON_SELECT_TOUCH_READING` in research 94's ledger, spec W4.R3),
drawn on the HUD path (`newweapnbkrnd.tif`, the icons, the font) at the 640x448 frame, driven by keys, pad and touch,
confirming into a `loadout` request that applies at the spawn the game applies it. Unit tests per state; e2e: die in
the offline match, open, pick, confirm, next round with the pick; the other side lists its own.

### M9 — Multiplayer kits and server authority
Protocol 7: `loadout` request/answer (validated per W4.R2/R6), the body's weapon as an item id (the codec's bytes
re-measured), the kill line's `DisplayName`; the room stores each player's kit and applies it at the spawn; remote
players draw each other's weapon, clips, sounds, muzzle. Tests: refusals, a pick surviving a reconnect, two pages of
opposite sides; `tools/mp-bots.ts` 16 + 8 still at 60 Hz with mixed kits. **Behind the multiplayer switch** (spec §1):
the site's build (`VITE_S2U_MULTIPLAYER=off`) keeps the menu and the `loadout` through the loopback `Room` only -- no
Online control, no `/rooms`, no socket; `test/multiplayer.test.ts` stays green and gains a case that the off build's
loadout opens no connection. The README's protocol lines say the site's page stays single player until the owner flips
the deploy flag (O-S4-4).

### M10 — Polish and the close
A derive-from-source review: an Opus reviewer (Fable-style brief: every new number traced to its cited source,
every placeholder in the ledger, every "1:1" claim checked against the decomp or a frame) over the diff and research 94;
fix what it finds. README (the menu, the keys, the arsenal), `docs/DATA_SOURCES.md` rows, the spec's §7, the Log's
close entry with the spend, the PR to `main` (the owner merges; the server redeploy is the owner's, spec §8 O-S4-4).

## Log

*(newest first)*

- **2026-09-30 — M10, the close** (the cloud agent). All of M2-M9 merged, each implementer's branch reviewed by a fresh
  Opus reviewer before its merge (every FAIL or medium finding fixed and re-reviewed first): M4 the classes' fire
  (the bolt/pump lock, reload timing, 4 pellets a pull, the 40 mm rounds as fire modes; `firearms.ts`, page and server
  sharing it), M5/M6 sights (zoom per record, the scope set, the thermal scope's node and the map's own lens rows),
  reticle sets, the arming grey, per-weapon sounds and effects, M7 the equipment (keys 3/4/5; the LAW/RPG rockets and
  backblast; C4 timed on a target; the claymore and its detonator; the PMN; the pouch retired: every use checked
  against the server's kit), M8/M9 WEAPON EXCHANGE in the match (I / R2 / INV while dead), the `loadout` request
  replayed by the room (`applyPicks`: a living player refused, rate-limited, next round), protocol 7 (the body's item
  id, kits on spawn and welcome, `DisplayName` kill lines; the off build opens no socket). The derive-from-source
  review (an Opus reviewer over the whole diff, 40 citations checked against the decomp and `.data`): PASS WITH
  FINDINGS -- the Detonator's `FireWait` was typed in the room (now read per item), the turrets' two id classes, three
  ledger rows; fixed with two leftover lows of the protocol review (an address's stale picks, the answers' pairing
  after a dropped request) and the stance button's press-frame bug that the full e2e surfaced (walk.spec:70).
  **Counts:** `npm run typecheck` clean; `npm test` redotcom **2494 passed / 2 skipped** (188 files; baseline 2123 /
  4), landing 262, shared 219; `npm run build` and the `VITE_S2U_MULTIPLAYER=off` build exit 0; feel parity 61 rows,
  59 within tolerance, 0 divergent. e2e on a quiet host before the last fixes: **92 passed, 10 failed** -- the
  baseline's nine host failures and walk.spec:70 (fixed after: walk, touch, pad, weaponExchange, weaponExchangeMp and
  equipment then 20/20); the new specs (launcher, sights, equipment, weaponExchange, weaponExchangeMp) pass. `mp-bots`
  16 + 8 with kits: 60.0 ticks/s, 30 Hz snapshots, 0 corrections.
  **Spend, metered by tokens** (the harness reports each subagent's tokens, no dollars; the main agent's own turns are
  not reported): subagents **4.94M tokens** -- M1 readers 1.08M; the runtime kit 0.56M + its review 0.11M; the menu's
  drawing 0.20M + 0.08M; M5/M6 0.44M + 0.10M; M4 0.65M + 0.12M; M8/M9 0.58M + 0.10M; M7 0.70M + 0.10M; the M10 audit
  0.14M -- ~ $28 *estimated* at the plan's prices with a 90/10 input/output split and no cache discount; the main
  agent ~ $35 *estimated*. **Total ~ $63 of $250** (every line under its budget: M4 and M8, the two tightest, took
  0.77M ~ $4 and 0.96M ~ $5 of subagent tokens). No cut from the cut order was needed: every item of §5 was built. For the owner:
  O-S4-3 (the key I, the INV touch button, the in-menu keys, key 5, the refill side `INGAME_AUTOFILL_SIDE_READING`),
  O-S4-4 (the server redeploy for protocol 7; the site stays single player until the deploy flag flips), O-S4-2 (the
  frames still wanted: WEAPON EXCHANGE, each scope, a Terrorist's menu).

- **2026-09-30 — the runtime kit merged (M3/M4 core), WEAPON EXCHANGE drawn (M8), launched rounds (M7 physics)**
  (the cloud agent). Two Opus implementers in worktrees, each reviewed by a fresh Opus reviewer before the merge
  (PASS WITH FINDINGS both; the kit's one medium finding -- a devmode pick applied online while the server ruled the
  type's kit -- fixed in a round). The kit is data now: the page, its loopback room and the server read `ZWEAPON.ZAR`
  at run time; every player spawns with the character type's `default_weapons` (so Frostfire's SEAL 1 holds the
  M4A1, not W2.R4's M4A1 SD: `&kit=62,15,121,126,255` in devmode pins the SD for the specs that test it); records,
  held models (any of the library's, case-insensitive: the SA-80's `IW80A2`, `MODEL_NAME_CASE_READING`), icons,
  2X and the server's per-weapon tables all follow the `Loadout`; `KIT_PLACEHOLDER` retired. **2X and the frames:**
  the kit now shows 5 MAGS for the M4A1 with 2X (`NumMags` 3 doubled, research 94 §A7); `s4_pcsx2/A_60_select.png`
  (an M4A1 in a live Vigilance round) shows 27/30 5 MAGS -- six magazines, so the doubling is the console's;
  research 84 §18's `console_spawn_slot8.png` (2 MAGS) is a spawn of an unknown kit. The menu's layout, prompt lines
  and key/pad maps (`weaponSelect.ts`, 20 tests) follow §B5; the prompt's colour is the code's (100,100,20)/100
  (research 94 §B4 corrected); the pad glyphs are drawn as words (`PAD_GLYPH_PLACEHOLDER`: the HUD font has none).
  Launched rounds in `projectile.ts`: rockets accelerate without a fall, a hit inside `ArmingDistance` is a dud, the
  loft onto the aimed point (`LOFT_TOLERANCE_READING` resolved from `.data`), the backblast. Suite: redotcom 2213
  passed / 2 skipped; build green. Wave 2 dispatched: (A) the classes' fire behaviour and the 40 mm rounds as fire
  modes, (B) sights/thermal/reticles/sounds/effects, (C) the menu in the match and protocol 7.
  **Spend check (after M4's first work, as the plan asks)** -- *estimated*, the harness reports tokens per subagent
  but no dollars: subagents so far 1.97M tokens (M1 readers 1.08M, the kit 0.51M, the menu's drawing 0.20M, two
  reviews 0.19M) ~ $11 at the plan's prices with a 90/10 input/output split; the main agent's own turns are not
  metered by the harness and are estimated at ~ $20 with prompt caching. Running total ~ $42 of $250 against M0-M3's
  $88 of lines plus part of M4 and M8: under the line; no re-plan.

- **2026-09-30 — M2, the data layer** (the cloud agent). `packages/scene/src/arsenal.ts`: every `ZWEAPON` record as an
  `ArsenalItem` (class by id range, slot kind, model, icon, round, and the rare keys with the parser's defaults:
  `SlotCost`, `ReloadTime`, `ReloadDelay`, the bolt/pump lock, `ArmingDistance`, `HasBackblast`, gravity, muzzle
  velocity, `Timer1/2`, pellets, the rockets' acceleration); `FUN_003cf1f0`'s id-to-valve map; each map's valves,
  per-side selectable list and 4+4 character kits (`readMapArsenal`); the menu's rules -- `selectable`
  (`FUN_0023c390`), `slotLocked` (`FUN_0023e910`), `menuValves` (the launcher-round rewrite), `pick` with the
  dependants and the refill (`FUN_0023fef0`/`FUN_0023eca0`/`FUN_0023b9b0`, the refill from the player's own side:
  `INGAME_AUTOFILL_SIDE_READING` now in code) -- and **`applyPicks`, the server's authority: the menu's picks replayed
  through the same rules**, so the kit is computed by the room, never taken from the page (W4.R6; this replaces the
  plan's `validateLoadout(side, map, type, pick)` shape). Tests (`scene/test/arsenal.test.ts`, 15): a synthetic twin of
  every rule, and off the disc all 22 maps' per-side lists equal to research 94 §A4's table (read from the note), the
  BREACH SEALs' locked C4, MP6's SEAL 226. The page, `net/loopback.ts` and the server take it up in M4/M8/M9, where
  their kit code changes. Suite: redotcom 2140 passed / 2 skipped.

- **2026-09-30 — M1 closed: research 94** (the cloud agent). Three Opus readers (the arsenal; the menu; per-class
  behaviour) wrote parts 1-3, merged as `docs/research/94-the-arsenal.md` with a §0 of rulings R94.1-R94.17 the later
  tasks build on. Headline: **`CInGameWeaponSel` is dead code** -- the dead player's menu is the HUD's "WEAPON
  EXCHANGE" (`CHUD+0x38e0`), online only, opened on `Inventory` while dead, silent, applied at the next round; the side
  filter is `FUN_0023c390` (1 SEAL / 8 Terrorist), 16/32 lock C4 on the BREACH maps; a class is its id range; launcher
  rounds are fire modes of their carrier; bullets are rays that ignore `Muzzle_Velocity`; C4 is timed, not remote;
  `SendWeaponPUMessage` is the dropped-weapon pick-up. 63 of 86 records in scope; the 176 kits equal research 91 §14.
  Research 84 §9's grey reticle corrected (R94.16). The placeholder ledger is green (research-only readings marked
  *note only* until code names them). **One ruling for the owner:** the game's launcher-ammo refill tests the side
  inverted (`INGAME_AUTOFILL_SIDE_READING`); the build refills from the player's own side (W4.R2).
  **Spend, M1** (*estimated*: the harness gives no cost report inside the session; tokens are the subagents' reported
  totals, split 90/10 input/output as an assumption, at $4/$20 per MTok, before any cache discount): readers a 338k,
  b 376k, c 364k tokens = 1.08M ~ $6.1; the main agent's merge and review ~ $3 (not metered: estimated from its context
  size). **M1 ~ $9 of $35.**
- **2026-09-30 — M0 closed: bring-up and baseline** (the cloud agent). The handoff (a tar, 1.2 GB) laid out outside the
  repository; `MANIFEST.sha256` verified (every file OK); both recompilation archives unpacked; `extract-maps` indexed
  all 22 maps. Baseline on `web-sprint-4-arsenal` at 4b1349ed: `npm run typecheck` clean; `npm test` redotcom **2123
  passed / 4 skipped** (175 files), landing 262, shared 219; `npm run build` and `VITE_S2U_MULTIPLAYER=off npm run build
  -w @s2u/redotcom` both exit 0 (the landing's sfx step logs a missing `ffmpeg` on this host and carries on). Feel parity
  headless: 61 rows, 59 within tolerance, 0 divergent in the mover/camera. e2e (Playwright 1.63 needs
  `PW_CHROMIUM=/opt/pw-browsers/chromium` on this host -- its own headless shell is not installed): **84 passed, 9
  failed**, each for a host cause: doors (the leaf's timing), effects (the frag light's sample), flyLock (a 180 s click
  timeout), grenade (the fuse's timing), hud (`scripts/parity/refs/console_spawn_slot8.png` is not in the checkout),
  presentation x2 (WebGPU on SwiftShader: the world coverage 0.07-0.08 under its bar), settingsPanel (the focus ring
  under headless), viewer fonts (the woff2 content type). Held from here: the same green, nothing new red.
  **Spend, M0** *estimated* ~ $2 of $8 (the main agent only).

- **2026-09-30 — revised after the Fable review** (the local controller): the prep rebased onto the integration head
  e5406330 (1b1ae687's `VITE_S2U_MULTIPLAYER` switch; the site's build ships multiplayer off, spec §1, and M9's network
  side sits behind it); the menu's PC key and touch control are readings in the ledger (W4.R3); the spend is metered
  per milestone (above); the handoff's research 44/50/55 path named.
- **2026-09-30 — opened** by the local controller: spec and plan written on `agent/web-s4prep` (to be cut as
  `web-sprint-4-arsenal` from the integration head); the inventory's headline in the spec's §2 and §7; the handoff zip
  built (see its `HANDOFF.md`).
