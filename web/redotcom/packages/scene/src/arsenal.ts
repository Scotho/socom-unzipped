import { Zar, parseRdr, rdrGet, parseZdb, zdbMember, type RdrNode } from '@s2u/archive';
import { UNITS_PER_METRE, weaponRecord, type WeaponRecord } from './weapons';
import { throwableRecord, type ThrowableRecord } from './projectile';

/**
 * The arsenal (web sprint 4, M2; research 94 part 1): every item a multiplayer SEAL or Terrorist may carry, what each
 * side may pick on a map, the character types' kits, and the in-game weapon select's rules -- one module the page, the
 * page's own match (`net/loopback.ts`) and the match server read, built from the disc at run time (no game table is
 * baked here: the constants below are the game's *code*, each with its function and line).
 *
 * - **An item** is a `zweapon.rdr` `ZWEAPON` record; its `ID` is the item id (`EQUIP_ITEM`, record `+0x7c`, parser
 *   `FUN_003cda30` L322435). Its **class is its id range** (`FUN_003d1a60` L324331-324352), not a key (R94.6); its
 *   **slot kind** follows: primary = SMG, rifle, shotgun, MG, sniper, grenade launcher (`FUN_003d1d10` L324404),
 *   secondary = pistol (`FUN_003d1ce0` L324392), equipment = everything else, the LAW and RPG-7 included.
 * - **Each side's arsenal** is the map's `READERM.ZAR/mission.rdr` `Valves`: `Enable_<x>` with a mask, **1 SEALs, 8
 *   Terrorists**, read through the game's own id-to-valve map `FUN_003cf1f0` (L322760-322968, `VALVE_OF_ITEM`) by an
 *   exact, case-sensitive name (`FUN_00351ef0` L250997: `strcmp`); no valve, not selectable (§A2, §A3). **16 / 32 lock
 *   C4** in a SEAL's / a Terrorist's kit (`FUN_0023e910` L88527-88545; R94.5).
 * - **The kit** is five slots -- primary, secondary, equipment 1-3 -- the character type's `default_weapons`
 *   (`character.rdr`, resolved through its `name : base` inheritance), given at the spawn as the game gives it, never
 *   checked against the valves (R94.7; MP6 SEAL 4 carries the Terrorist-only 226).
 * - **A pick** follows the in-game menu's code: `selectable` is `FUN_0023c390` (L87358-87487), `slotLocked`
 *   `FUN_0023e910`, `pick` `FUN_0023fef0` (L89138-89323) with `FUN_0023eca0` (L88610-89136) undoing what the old item
 *   brought; `applyPicks` is the server's replay of the menu's picks through the same rules (W4.R6).
 *
 * The one divergence, named: the game's launcher-ammo refill (`FUN_0023b9b0`/`FUN_0023bc50`) tests the side inverted
 * (`player_team == 0 -> 8`, the MIPS at 0x23bbdc); this module refills from the player's own side, as the list itself
 * does -- `INGAME_AUTOFILL_SIDE_READING` (research 94 §A5.4, R94.4).
 */

/** An empty slot (`EQUIP_NONE`, id 255) and the second slot a cost-2 item fills (`FULL_SLOT`, id 254). */
export const EMPTY_ITEM = 255;
export const FULL_SLOT = 254;
/** The items the rules name by id (research 94 §A1). */
export const ITEM = {
  M203: 141, MGL: 142, M79: 143, LAW: 145, RPG7: 146, C4: 151, SATCHEL: 152, CLAYMORE: 153, PMN: 158, BACKBLAST: 159,
  M203_FRAG: 175, GL_FRAG: 179, F2000_FRAG: 183, LAW_HEAT: 185, RPG_ROUND: 186,
  DETONATOR: 193, DOUBLE_AMMO: 194, THERMAL: 195, M16_203: 52, M4_203: 61, F2000: 63,
} as const;

/**
 * `FUN_003cf1f0` (L322760-322968): an item id to the name of the valve that enables it. 68 cases, 67 names (the RPG-7
 * and its round share `Enable_RPG`); 124 `Enable_phos` and 172 `Enable_203ILL` name no record. The names are the code's
 * strings, read from the retail ELF (research 94 §A2).
 */
export const VALVE_OF_ITEM: ReadonlyMap<number, string> = new Map([
  [4, 'Enable_fiveseven'], [5, 'Enable_beretta_m9'], [6, 'Enable_Sig226'], [7, 'Enable_desert_eagle'], [8, 'Enable_HkP9s'],
  [12, 'Enable_P228'], [13, 'Enable_SR1_Gyurza'], [14, 'Enable_glock18'], [15, 'Enable_Mark23'], [16, 'Enable_mark23sd'],
  [31, 'Enable_mp5'], [33, 'Enable_mp5sd'], [34, 'Enable_FNP'], [37, 'Enable_uzi'], [38, 'Enable_MP5K'],
  [51, 'Enable_M16'], [52, 'Enable_M16203'], [54, 'Enable_m4Acarbine'], [57, 'Enablesig_commando'], [58, 'Enable_ak47'],
  [59, 'Enable_aks74'], [60, 'Enable_m14_gun'], [61, 'Enable_m4Acarbine_203'], [62, 'Enable_M4A1_SD'], [63, 'Enable_F2000'],
  [64, 'Enable_SA-80'], [65, 'Enable_AK105'], [66, 'Enable_OC14'], [67, 'Enable_552SD'], [68, 'Enable_STEYR'],
  [81, 'Enable_spas'], [83, 'Enable_jack'], [84, 'Enable_870'], [91, 'Enable_m60e'], [92, 'Enable_m63a'],
  [101, 'Enable_barret_lightm82A1'], [102, 'Enable_remington700'], [103, 'Enable_EquipmcmillanM87'], [104, 'Enable_Dragonov'],
  [105, 'Enable_stoner_sr25_SD'], [106, 'Enable_stoner_sr25'], [121, 'Enable_frag'], [122, 'Enable_smoke'], [123, 'Enable_flash'],
  [124, 'Enable_phos'], [126, 'Enable_HEgren'], [127, 'Enable_red_smoke'], [142, 'Enable_mglmk1'], [143, 'Enable_m79'],
  [145, 'Enable_LAW'], [146, 'Enable_RPG'], [151, 'Enable_c4'], [152, 'Enable_satchel'], [153, 'Enable_claymore'],
  [158, 'Enable_pmn'], [171, 'Enable_203HE'], [172, 'Enable_203ILL'], [173, 'Enable_203SMK'], [175, 'Enable_203FRAG'],
  [176, 'Enable_GLHE'], [178, 'Enable_GLSMK'], [179, 'Enable_GLFRAG'], [181, 'Enable_F2000HE'], [182, 'Enable_F2000SMK'],
  [183, 'Enable_F2000FRAG'], [186, 'Enable_RPG'], [194, 'Enable_2xammo'], [195, 'Enable_ThermScope'],
]);

/** The launcher-round valve groups the menu rewrites (`FUN_00240e60` L89585, `FUN_0023fef0` L89205-89300). */
const ROUND_VALVES = {
  m203: ['Enable_203HE', 'Enable_203SMK', 'Enable_203FRAG'],
  gl: ['Enable_GLHE', 'Enable_GLSMK', 'Enable_GLFRAG'],
  f2000: ['Enable_F2000HE', 'Enable_F2000SMK', 'Enable_F2000FRAG'],
} as const;

export type ItemClass =
  | 'pistol' | 'smg' | 'rifle' | 'shotgun' | 'mg' | 'sniper' | 'grenade' | 'grenadeLauncher' | 'rocketLauncher'
  | 'explosive' | 'launcherRound' | 'rocketRound' | 'gear' | 'armour' | 'turret' | 'turret2' | 'internal';

/** `FUN_003d1a60` (L324331-324352): the id ranges, first id of each class to its last. */
const CLASS_RANGES: readonly (readonly [number, number, ItemClass])[] = [
  [4, 30, 'pistol'], [31, 50, 'smg'], [51, 80, 'rifle'], [81, 90, 'shotgun'], [91, 100, 'mg'], [101, 120, 'sniper'],
  [121, 140, 'grenade'], [141, 144, 'grenadeLauncher'], [145, 150, 'rocketLauncher'], [151, 170, 'explosive'],
  [171, 184, 'launcherRound'], [185, 189, 'rocketRound'], [190, 200, 'gear'], [201, 204, 'armour'], [205, 229, 'turret'], [230, 253, 'turret2'],
];

/** An item's class by its id range (`FUN_003d1a60`); anything else is internal (0xfe). */
export function itemClass(id: number): ItemClass {
  for (const [lo, hi, c] of CLASS_RANGES) if (id >= lo && id <= hi) return c;
  return 'internal';
}

export type SlotKind = 'primary' | 'secondary' | 'equipment';
const PRIMARY_CLASSES: ReadonlySet<ItemClass> = new Set(['smg', 'rifle', 'shotgun', 'mg', 'sniper', 'grenadeLauncher']);

/** The slot an item goes in: `FUN_003d1d10` primary, `FUN_003d1ce0` secondary, else equipment (L87372-87389). */
export function slotKindOf(id: number): SlotKind {
  const c = itemClass(id);
  return PRIMARY_CLASSES.has(c) ? 'primary' : c === 'pistol' ? 'secondary' : 'equipment';
}

/** The kind of each of the five kit slots (the menu's slot 0 primary, 1 secondary, 2-4 equipment). */
export function slotKind(slot: number): SlotKind {
  return slot === 0 ? 'primary' : slot === 1 ? 'secondary' : 'equipment';
}

/** The classes 2X doubles (`FUN_005c75f0` L480215-480250; research 94 §A7). */
export const DOUBLED_CLASSES: ReadonlySet<ItemClass> = new Set(['pistol', 'smg', 'rifle', 'shotgun', 'mg', 'sniper']);

export type Side = 'seal' | 'terrorist';
/** The side bits of a valve (`FUN_0023c390` L87468-87476) and the C4 lock bits (`FUN_0023e910` L88527-88545). */
export const SIDE_BIT: Readonly<Record<Side, number>> = { seal: 1, terrorist: 8 };
export const LOCK_BIT: Readonly<Record<Side, number>> = { seal: 16, terrorist: 32 };

/** A kit: five item ids, slot order; `EMPTY_ITEM` for none. */
export type Loadout = readonly [number, number, number, number, number];

/**
 * An item as the arsenal needs it: the record's names, class, model and icon, and the rare keys research 94 part 3
 * reads in code (their members and defaults: the parser `FUN_003cda30` L322377-322620). Ranges and speeds are in world
 * units (x `UNITS_PER_METRE`, `DAT_003dfe10`), times in seconds.
 */
export interface ArsenalItem {
  id: number;
  /** `InternalName` -- the key `character.rdr` kits and `weaponRecord` use. */
  name: string;
  /** `DisplayName` -- what the menu and the kill line show (research 91 §10). */
  displayName: string;
  cls: ItemClass;
  kind: SlotKind;
  /** `ModelName` (`NONE`/absent -> null: 2X, the M203, the thermal scope have none). */
  model: string | null;
  icon: string | null;
  /** The first `AMMO_TYPES` round, by name and `ZAMMO` id (null: the LAW, the RPG-7 -- their round is an item). */
  ammo: string | null;
  ammoId: number | null;
  magazine: number;
  mags: number;
  /** `FireWait` (`+0x50`, default 0.1: research 84 §1's key table): the seconds between uses (the Detonator's 0.1). */
  fireWait: number;
  /** `SlotCost` (`+0x27c`, default 1): 2 takes a second equipment slot (LAW, RPG-7, Satchel). */
  slotCost: number;
  /** `ReloadTime` (`+0x54`, default 0): the standing reload clip is stretched to it (`FUN_005a82e0`). */
  reloadTime: number;
  /** `ReloadDelay` (`+0x5c`, default 0.01): the lock before a reload lands (`FUN_005c32b0`). */
  reloadDelay: number;
  /** `ReloadAfterShot` (`+0x58`): a bolt or pump -- the lock after each round (`FUN_005c5340` L479329-479343). */
  reloadAfterShot: boolean;
  /** `ReloadDelayAfterShot` (`+0x60`, default 0.01): that lock (the 870's key is misspelt on the disc: 0.01, R94.12). */
  reloadDelayAfterShot: number;
  /** `ArmingDistance` (`+0x68`) x10: a launched round hitting nearer its launch point is a dud (`FUN_003c8920`). */
  armingDistance: number;
  /** `HasBackblast` (`+0xd5`): each shot also fires the `Backblast` record backwards (`FUN_003d2d70`). */
  hasBackblast: boolean;
  /** `Gravity_Acceleration` (`+0x48`) x10, default 9.8 -> 98 u/s^2. */
  gravity: number;
  /** `Muzzle_Velocity` (`+0x44`) x10 -- used by thrown and launched rounds only; a bullet is a ray (R94.9). */
  muzzleVelocity: number;
  /** `Timer1`/`Timer2` (`+0xd8`/`+0xdc`, default 9999999): the fuse and the lingering state's life. */
  timer1: number;
  timer2: number;
  /** The round's `NumProjectilesFired` (the 12 gauge's 4 rays a pull, R94.10), default 1. */
  projectiles: number;
  /** The round's `AccelerationFactor` x10 (the rockets' 980 u/s^2, no fall; R94.9), 0 for none. */
  acceleration: number;
}

/** The disc's item table: every record, by id and by name, in the file's order (the menu steps in it: `FUN_003c4b00`). */
export interface Arsenal {
  items: ReadonlyMap<number, ArsenalItem>;
  byName: ReadonlyMap<string, ArsenalItem>;
  order: readonly number[];
}

/** A map's arsenal: its valves, each side's selectable items, and its character types' kits. */
export interface MapArsenal {
  valves: ReadonlyMap<string, number>;
  selectable: Readonly<Record<Side, readonly number[]>>;
  kits: Readonly<Record<Side, readonly CharacterKit[]>>;
}

/** A character type a map offers (`chartype.rdr`), with its kit resolved through `character.rdr`. */
export interface CharacterKit {
  /** The type's `name` in `chartype.rdr`. */
  type: string;
  /** The `character.rdr` record it names (`mp2_seal1`). */
  character: string;
  /** The kit, five ids (`default_weapons` in slot order; `EMPTY_ITEM` past its end). */
  loadout: Loadout;
}

// ---------------------------------------------------------------------------------------------------------------------
// Reading.

const str = (n: RdrNode | undefined): string | undefined =>
  typeof n === 'string' ? n : Array.isArray(n) && typeof n[0] === 'string' ? n[0] : undefined;
const num = (node: RdrNode, key: string, fallback: number): number => {
  const v = str(rdrGet(node, key));
  if (v === undefined) return fallback;
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`zweapon.rdr ${str(rdrGet(node, 'InternalName'))}: ${key} ${v} is no number`);
  return n;
};
/** A flag key: present (its value list empty, `ReloadAfterShot ()`) or absent. */
const flag = (node: RdrNode, key: string): boolean => rdrGet(node, key) !== undefined;
const named = (v: string | undefined): string | null => (v === undefined || v === 'NONE' || v === '(null)' || v === 'NOT FOUND' ? null : v);

function list(script: RdrNode, key: string): RdrNode[][] {
  const v = rdrGet(script, key);
  if (!Array.isArray(v)) throw new Error(`zweapon.rdr has no ${key}`);
  return v.filter((r): r is RdrNode[] => Array.isArray(r));
}

/** `zweapon.rdr`, parsed -> the arsenal (every `ZWEAPON` record, its round from `ZAMMO`). */
export function arsenalOf(script: RdrNode): Arsenal {
  const rounds = new Map(list(script, 'ZAMMO').map((r) => [str(rdrGet(r, 'InternalName')) ?? '', r] as const));
  const items = new Map<number, ArsenalItem>(), byName = new Map<string, ArsenalItem>(), order: number[] = [];
  for (const r of list(script, 'ZWEAPON')) {
    const name = str(rdrGet(r, 'InternalName'));
    if (name === undefined) continue;
    const id = num(r, 'ID', -1);
    const types = rdrGet(r, 'AMMO_TYPES');
    const ammo = Array.isArray(types) && types.length ? str(rdrGet(types, 'NAME')) ?? null : null;
    const round = ammo === null ? undefined : rounds.get(ammo);
    const item: ArsenalItem = {
      id, name, displayName: str(rdrGet(r, 'DisplayName')) ?? name, cls: itemClass(id), kind: slotKindOf(id),
      model: named(str(rdrGet(r, 'ModelName'))), icon: named(str(rdrGet(r, 'IconTextureName'))),
      ammo, ammoId: round === undefined ? null : num(round, 'ID', -1),
      magazine: num(r, 'Ammo_Capacity', 0), mags: num(r, 'NumMags', 0), fireWait: num(r, 'FireWait', 0.1),
      slotCost: num(r, 'SlotCost', 1), reloadTime: num(r, 'ReloadTime', 0), reloadDelay: num(r, 'ReloadDelay', 0.01),
      reloadAfterShot: flag(r, 'ReloadAfterShot'), reloadDelayAfterShot: num(r, 'ReloadDelayAfterShot', 0.01),
      armingDistance: num(r, 'ArmingDistance', 0) * UNITS_PER_METRE, hasBackblast: flag(r, 'HasBackblast'),
      gravity: num(r, 'Gravity_Acceleration', 9.8) * UNITS_PER_METRE, muzzleVelocity: num(r, 'Muzzle_Velocity', 0) * UNITS_PER_METRE,
      timer1: num(r, 'Timer1', 9999999), timer2: num(r, 'Timer2', 9999999),
      projectiles: round === undefined ? 1 : num(round, 'NumProjectilesFired', 1),
      acceleration: round === undefined ? 0 : num(round, 'AccelerationFactor', 0) * UNITS_PER_METRE,
    };
    items.set(id, item);
    byName.set(name, item);
    order.push(id);
  }
  return { items, byName, order };
}

/** `mission.rdr` -> its valves, name to value (the first of a repeated name, as the valve list's lookup finds it). */
export function missionValves(mission: RdrNode): Map<string, number> {
  const out = new Map<string, number>();
  const valves = rdrGet(mission, 'Valves');
  if (!Array.isArray(valves)) return out;
  for (const v of valves) {
    const name = str(rdrGet(v, 'NAME')), value = Number(str(rdrGet(v, 'VALUE')));
    if (name !== undefined && Number.isFinite(value) && !out.has(name)) out.set(name, value);
  }
  return out;
}

/**
 * `character.rdr` -> a character's `default_weapons`, names in slot order, through its inheritance (`name : base
 * (...)`): the first record up the chain that has a kit (research 94 §A4, the probe that matched research 91 §14's 176).
 */
export function characterWeapons(character: RdrNode, who: string): string[] {
  const chars = rdrGet(character, 'characters');
  if (!Array.isArray(chars)) throw new Error('character.rdr has no characters');
  const defs = new Map<string, { base?: string; rec: RdrNode }>();
  for (let i = 0; i < chars.length; i++) {
    const n = chars[i];
    if (typeof n !== 'string') continue;
    if (chars[i + 1] === ':') {
      if (!defs.has(n)) defs.set(n, { base: str(chars[i + 2]), rec: chars[i + 3]! });
      i += 3;
    } else if (Array.isArray(chars[i + 1])) {
      if (!defs.has(n)) defs.set(n, { rec: chars[i + 1]! });
      i += 1;
    }
  }
  let cur: string | undefined = who;
  for (let depth = 0; cur !== undefined && depth < 16; depth++) {
    const def = defs.get(cur);
    if (!def) break;
    const w = rdrGet(def.rec, 'default_weapons');
    if (Array.isArray(w) && w.length) {
      const entries = (typeof w[0] === 'string' ? [w] : w) as RdrNode[];
      return entries.map((e) => str(rdrGet(e, 'wep_name'))).filter((n): n is string => n !== undefined);
    }
    cur = def.base;
  }
  return [];
}

/** Five names -> a loadout of ids (an unknown name is an error: the disc's kits all resolve, research 94 §A4). */
export function loadoutOf(arsenal: Arsenal, names: readonly string[]): Loadout {
  const ids = names.slice(0, 5).map((n) => {
    const item = arsenal.byName.get(n);
    if (!item) throw new Error(`zweapon.rdr has no item ${n}`);
    return item.id;
  });
  while (ids.length < 5) ids.push(EMPTY_ITEM);
  return ids as unknown as Loadout;
}

/** `chartype.rdr` + `character.rdr` -> each side's types with their kits, in the map's order. */
export function mapKits(arsenal: Arsenal, chartype: RdrNode, character: RdrNode): Record<Side, CharacterKit[]> {
  const side = (team: string): CharacterKit[] => {
    const value = rdrGet(chartype, team);
    if (!Array.isArray(value) || !value.length) return [];
    // One entry reads back unwrapped (a flat key/value list), several as a list of them.
    const entries = (typeof value[0] === 'string' ? [value] : value) as RdrNode[];
    return entries.flatMap((e) => {
      const c = str(rdrGet(e, 'character'));
      if (c === undefined) return [];
      return [{ type: str(rdrGet(e, 'name')) ?? c, character: c, loadout: loadoutOf(arsenal, characterWeapons(character, c)) }];
    });
  };
  return { seal: side('navyseals'), terrorist: side('terrorists') };
}

/** Every item a side may pick on a map at the round's start (before the menu rewrites the round valves). */
export function selectableItems(arsenal: Arsenal, valves: ReadonlyMap<string, number>, side: Side): number[] {
  return arsenal.order.filter((id) => valveAllows(valves, side, id));
}

/** Whether an item's valve carries the side's bit (`FUN_0023c390` L87468-87478); no valve, refused. */
export function valveAllows(valves: ReadonlyMap<string, number>, side: Side, id: number): boolean {
  const name = VALVE_OF_ITEM.get(id);
  const value = name === undefined ? undefined : valves.get(name);
  return value !== undefined && (value & SIDE_BIT[side]) !== 0;
}

/** A map's arsenal from its parsed scripts. */
export function mapArsenal(arsenal: Arsenal, mission: RdrNode, chartype: RdrNode, character: RdrNode): MapArsenal {
  const valves = missionValves(mission);
  return {
    valves,
    selectable: { seal: selectableItems(arsenal, valves, 'seal'), terrorist: selectableItems(arsenal, valves, 'terrorist') },
    kits: mapKits(arsenal, chartype, character),
  };
}

function script(zar: Zar, where: string, name: string): RdrNode {
  const key = zar.root.children.find((k) => k.name.toLowerCase() === name);
  if (!key) throw new Error(`${where} has no ${name}`);
  return parseRdr(zar.data(key));
}

/** `ZWEAPON.ZAR` -> the arsenal. */
export function readArsenal(zweapon: Uint8Array): Arsenal {
  return arsenalOf(script(Zar.parse(zweapon), 'ZWEAPON.ZAR', 'zweapon.rdr'));
}

/**
 * The kit's tables (web sprint 4, M3/M4): the arsenal and, by item id, the `WeaponRecord` of every firearm it holds --
 * the primaries and the secondaries (`slotKindOf`), read by `weaponRecord` as the M4A1 SD's and the Mark 23's always
 * were. One read of `ZWEAPON.ZAR` feeds the page, the page's own match (`net/loopback.ts`) and the match server, so a
 * slot's rate, cone, magazines, damage and falloff are the same numbers on all three (W4.R2, W4.R6).
 */
export interface KitTable {
  arsenal: Arsenal;
  /** Every firearm's record by item id; an item with no readable firearm record (below) is absent. */
  records: ReadonlyMap<number, WeaponRecord>;
  /**
   * Every launched round's projectile by item id (web sprint 4 M4; research 94 §C4): the grenade launchers' rounds
   * (171-184) and the rockets (185-189), each `throwableRecord`'s read of it and its round's `Piercing` (the blast's
   * armour bypass, research 91 §5). A round the reader refuses is absent.
   */
  rounds: ReadonlyMap<number, KitRound>;
  /**
   * Web sprint 4 M7 (research 94 §C5, research 85): every hand grenade (121-140) and placed charge (151-170, the
   * `Backblast` 159 among them) by item id -- `throwableRecord`'s read of it (the timers, the radius, the damage, the
   * PMN's proximity) and its round's `Piercing` -- so the page's pouch and the room's blasts take the disc's numbers.
   * Optional: a hand-built table (a test) may leave it out; a record the reader refuses is absent.
   */
  throwables?: ReadonlyMap<number, KitThrowable>;
}

/** A throwable or a charge as the kit table holds it: its projectile record and its round's `Piercing` (`ZAMMO` `+0x14`). */
export interface KitThrowable { record: ThrowableRecord; piercing: number }

/**
 * A launched round: its projectile record (the flight, the arming, the blast), its ammo's `Piercing` (`ZAMMO` `+0x14`),
 * and what the carrier's fire takes from the round's own record in a round mode (`FUN_005c3780`, the redirected
 * record): its `FireWait` (`FUN_005c09f0` L476313-476340; reCOM's default 0.1, `zwep_weapon.cpp:53`), its bolt-like
 * lock (`ReloadAfterShot` + `ReloadDelayAfterShot`, research 94 §C1.1) and its `IconTextureName` -- the HUD's fire-mode
 * cell in that mode (`firemode_203_frag.tif`, `FUN_00237b40` L85254-85300, §C9).
 */
export interface KitRound {
  record: ThrowableRecord; piercing: number; fireWait: number; reloadAfterShot: boolean; reloadDelayAfterShot: number; icon: string | null;
}

/**
 * The carriers (`FUN_003c5cd0` L317260-317275: 0x34, 0x3d, 0x3f, 0x8e, 0x8f): the M16A2-M203, the M4A1-M203, the F2000,
 * the MGL and the M79 -- a primary whose fire modes run on into the rounds the kit holds (R94.8, research 94 §C4.2).
 */
export const GRENADE_CARRIERS: ReadonlySet<number> = new Set([ITEM.M16_203, ITEM.M4_203, ITEM.F2000, ITEM.MGL, ITEM.M79]);

/**
 * `zweapon.rdr`, parsed -> the kit's tables. A primary or secondary whose record `weaponRecord` cannot read is left out:
 * on the disc the M203 item (141: `AMMO_TYPES` empty; the select forces it into an equipment slot) and the Designator
 * (11, a pistol-class item with no round). The MGL and the M79, whose `AMMO_TYPES` is empty too, are carriers
 * (`GRENADE_CARRIERS`): read as such (`weaponRecord`'s `carrier`), since they fire their rounds as fire modes (R94.8).
 * The caller decides what a slot without a record holds (`viewer/src/loadout.ts`).
 */
export function kitTableOf(zweapon: RdrNode): KitTable {
  const arsenal = arsenalOf(zweapon);
  const records = new Map<number, WeaponRecord>();
  const rounds = new Map<number, KitRound>();
  const throwables = new Map<number, KitThrowable>();
  const ammo = new Map(list(zweapon, 'ZAMMO').map((r) => [str(rdrGet(r, 'InternalName')) ?? '', r] as const));
  const nodes = new Map(list(zweapon, 'ZWEAPON').map((r) => [str(rdrGet(r, 'InternalName')) ?? '', r] as const));
  for (const item of arsenal.items.values()) {
    if (item.cls === 'grenade' || item.cls === 'explosive') {
      try {
        const round = item.ammo === null ? undefined : ammo.get(item.ammo);
        throwables.set(item.id, { record: throwableRecord(zweapon, item.name), piercing: round === undefined ? 0 : num(round, 'Piercing', 0) });
      } catch { /* no projectile record (the Satchel's round-less twin, a key missing): none */ }
      continue;
    }
    if (item.cls === 'launcherRound' || item.cls === 'rocketRound') {
      try {
        const round = item.ammo === null ? undefined : ammo.get(item.ammo);
        rounds.set(item.id, {
          record: throwableRecord(zweapon, item.name), piercing: round === undefined ? 0 : num(round, 'Piercing', 0),
          fireWait: item.fireWait, reloadAfterShot: item.reloadAfterShot,
          reloadDelayAfterShot: item.reloadDelayAfterShot, icon: item.icon?.toLowerCase() ?? null,
        });
      } catch { /* a round the projectile reader refuses: none */ }
      continue;
    }
    if (item.kind === 'equipment') continue;
    try {
      records.set(item.id, weaponRecord(zweapon, item.name, { carrier: GRENADE_CARRIERS.has(item.id) }));
    } catch { /* no firearm record: see above */ }
  }
  return { arsenal, records, rounds, throwables };
}

/** `ZWEAPON.ZAR` -> the kit's tables. */
export function readKitTable(zweapon: Uint8Array): KitTable {
  return kitTableOf(script(Zar.parse(zweapon), 'ZWEAPON.ZAR', 'zweapon.rdr'));
}

/** A map's `.ZDB` and `READERC.ZAR` -> its arsenal (`READERM.ZAR`'s `mission.rdr` and `chartype.rdr`). */
export function readMapArsenal(arsenal: Arsenal, zdb: Uint8Array, readerc: Uint8Array): MapArsenal {
  const readerm = Zar.parse(zdbMember(zdb, parseZdb(zdb), 'READERM.ZAR'));
  const character = script(Zar.parse(readerc), 'READERC.ZAR', 'character.rdr');
  return mapArsenal(arsenal, script(readerm, 'READERM.ZAR', 'mission.rdr'), script(readerm, 'READERM.ZAR', 'chartype.rdr'), character);
}

// ---------------------------------------------------------------------------------------------------------------------
// The in-game select's rules.

/**
 * The valves as the menu sees them: the launcher-round groups rewritten from the primary -- 9 for the group the
 * primary fires, 0 for the others (`FUN_00240e60` L89585 at opening, `FUN_0023fef0`/`FUN_0023eca0` on each pick;
 * research 94 §A3 "Rewritten valves"). The M203 rifles (`FUN_003c5e10` L317306: 52, 61) and the MGL fire the 203
 * rounds, the M79 the GL rounds, the F2000 its own.
 */
export function menuValves(valves: ReadonlyMap<string, number>, primary: number): Map<string, number> {
  const out = new Map(valves);
  const group = primary === ITEM.M16_203 || primary === ITEM.M4_203 || primary === ITEM.MGL ? 'm203'
    : primary === ITEM.M79 ? 'gl' : primary === ITEM.F2000 ? 'f2000' : null;
  for (const [g, names] of Object.entries(ROUND_VALVES)) for (const n of names) out.set(n, g === group ? 9 : 0);
  return out;
}

/** Items that may sit in one slot only (`FUN_0023c390` L87443-87466). */
const SINGLE: ReadonlySet<number> = new Set([ITEM.DOUBLE_AMMO, ITEM.THERMAL, ITEM.PMN, ITEM.CLAYMORE, ITEM.LAW_HEAT, ITEM.LAW, ITEM.RPG7]);

/**
 * `FUN_0023c390` (L87358-87487): may item `id` go in `slot` of `loadout`, for `side`, under `valves` (already the
 * menu's: `menuValves`). In order: the slot's kind (equipment refuses primaries and pistols, the rockets allowed); the
 * thermal scope only beside a sniper in another slot; the RPG round only when another slot holds one, never in the
 * RPG-7's slot; no second copy of a single item; the side's bit.
 */
export function selectable(valves: ReadonlyMap<string, number>, side: Side, loadout: Loadout, slot: number, id: number): boolean {
  if (slotKindOf(id) !== slotKind(slot)) return false;
  const others = loadout.filter((_, i) => i !== slot);
  if (id === ITEM.THERMAL && !others.some((o) => itemClass(o) === 'sniper')) return false;
  if (id === ITEM.RPG_ROUND && (!others.includes(ITEM.RPG_ROUND) || loadout[slot] === ITEM.RPG7)) return false;
  if (SINGLE.has(id) && others.includes(id)) return false;
  return valveAllows(valves, side, id);
}

/**
 * `FUN_0023e910` (L88478-88545): whether a slot may **not** be changed -- the M203 (141) and `FULL_SLOT`; a LAW HEAT or
 * an RPG round unless another equipment slot holds the same; C4 while `Enable_c4` carries the side's lock bit.
 */
export function slotLocked(valves: ReadonlyMap<string, number>, side: Side, loadout: Loadout, slot: number): boolean {
  const id = loadout[slot]!;
  if (id === ITEM.M203 || id === FULL_SLOT) return true;
  if (id === ITEM.LAW_HEAT || id === ITEM.RPG_ROUND) {
    return ![2, 3, 4].some((i) => i !== slot && loadout[i] === id);
  }
  if (id === ITEM.C4) return ((valves.get('Enable_c4') ?? 0) & LOCK_BIT[side]) !== 0;
  return false;
}

/** The ids a launcher primary brings, by slot (`FUN_0023fef0` L89205-89320). */
function launcherFill(primary: number): readonly (readonly [number, number])[] {
  if (primary === ITEM.M16_203 || primary === ITEM.M4_203) return [[2, ITEM.M203], [3, ITEM.M203_FRAG]];
  if (primary === ITEM.M79) return [[2, ITEM.GL_FRAG]];
  if (primary === ITEM.MGL) return [[2, ITEM.M203_FRAG]];
  if (primary === ITEM.F2000) return [[2, ITEM.F2000_FRAG]];
  return [];
}

/** Whether an item is something a launcher or a cost-2 item brought (refilled when its source leaves). */
function dependentOf(id: number, source: number): boolean {
  const c = itemClass(id);
  if (source === ITEM.M16_203 || source === ITEM.M4_203 || source === ITEM.MGL) return id === ITEM.M203 || (c === 'launcherRound' && id >= 171 && id <= 175);
  if (source === ITEM.M79) return c === 'launcherRound' && id >= 176 && id <= 180;
  if (source === ITEM.F2000) return c === 'launcherRound' && id >= 181 && id <= 184;
  if (source === ITEM.LAW) return id === ITEM.LAW_HEAT;
  if (source === ITEM.RPG7) return id === ITEM.RPG_ROUND;
  if (itemClass(source) === 'sniper') return id === ITEM.THERMAL;
  return id === FULL_SLOT;
}

/**
 * The auto-fill (`FUN_0023b9b0` L87106-87180): the first equipment item after `after` in the file's order that the
 * side may pick, is no rocket launcher, is not `not`, and is no single item already carried -- from the player's own
 * side (`INGAME_AUTOFILL_SIDE_READING`: the game's helper tests the side inverted). `EMPTY_ITEM` when none.
 */
export function autoFill(arsenal: Arsenal, valves: ReadonlyMap<string, number>, side: Side, loadout: Loadout, after: number, not: number): number {
  const INGAME_AUTOFILL_SIDE_READING = side;
  const order = arsenal.order, start = Math.max(0, order.indexOf(after) + 1);
  for (let k = 0; k < order.length; k++) {
    const id = order[(start + k) % order.length]!;
    if (id === not || slotKindOf(id) !== 'equipment' || itemClass(id) === 'rocketLauncher') continue;
    if (SINGLE.has(id) || id === ITEM.M203 || id === FULL_SLOT || id === ITEM.C4 || id === ITEM.SATCHEL
      || id === ITEM.DETONATOR || id === EMPTY_ITEM) {
      if (loadout.slice(2).includes(id)) continue;
    }
    if (id === ITEM.THERMAL || id === ITEM.RPG_ROUND || id === ITEM.LAW_HEAT || id === ITEM.M203) continue;
    if (valveAllows(valves, INGAME_AUTOFILL_SIDE_READING, id)) return id;
  }
  return EMPTY_ITEM;
}

/**
 * `FUN_0023fef0` (L89138-89323) with `FUN_0023eca0` (L88610-89136): put `id` in `slot`. What the old item brought
 * leaves with it (a launcher's rounds and the M203, a cost-2 item's partner, a sniper's thermal scope), refilled by the
 * auto-fill; a cost-2 item fills the next equipment slot (4 wraps to 2) with its round or `FULL_SLOT`; a launcher
 * primary fills slots 2 (and 3). Returns the new loadout and the valves as the menu now sees them. The caller checks
 * `selectable` and `slotLocked` first, as the menu does.
 */
export function pick(arsenal: Arsenal, valves: ReadonlyMap<string, number>, side: Side, loadout: Loadout, slot: number, id: number): { loadout: Loadout; valves: Map<string, number> } {
  const kit = [...loadout];
  const old = kit[slot]!;
  kit[slot] = id;
  // The old item's dependants leave (FUN_0023eca0): refilled from the auto-fill, never the id just removed.
  let seen = menuValves(valves, kit[0]!);
  if (old !== id && old !== EMPTY_ITEM) {
    for (let i = 2; i <= 4; i++) {
      if (i !== slot && dependentOf(kit[i]!, old)) {
        kit[i] = EMPTY_ITEM;
        kit[i] = autoFill(arsenal, seen, side, kit as unknown as Loadout, old, old);
      }
    }
  }
  // A cost-2 item's partner slot: the next equipment slot, 4 wrapping to 2.
  const item = arsenal.items.get(id);
  if (item && item.slotCost === 2 && slot >= 2) {
    const partner = slot === 4 ? 2 : slot + 1;
    kit[partner] = id === ITEM.LAW ? ITEM.LAW_HEAT : id === ITEM.RPG7 ? ITEM.RPG_ROUND : FULL_SLOT;
  }
  // A launcher primary fills its slots.
  if (slot === 0) for (const [s, fill] of launcherFill(id)) kit[s] = fill;
  seen = menuValves(valves, kit[0]!);
  return { loadout: kit as unknown as Loadout, valves: seen };
}

/** One step of the menu: the item put in a slot (`FUN_0023fef0`'s arguments). */
export interface Pick { slot: number; id: number }

/** Why a requested pick is refused (the server's answer; the menu never offers one of these). */
export type PickRefusal = 'slot' | 'unknown' | 'locked' | 'refused';

/**
 * The server's authority over the kit (W4.R6): the picks the menu made, replayed in order through the menu's own rules
 * -- each slot 0-4, each item known, the slot not locked (`slotLocked`), the item one the side may put there
 * (`selectable` under the menu's valves) -- each applied with `pick`, so the kit that results is computed here, never
 * taken from the page. An empty list keeps the kit. The first refused step refuses the request.
 */
export function applyPicks(arsenal: Arsenal, valves: ReadonlyMap<string, number>, side: Side, current: Loadout, picks: readonly Pick[]):
  { loadout: Loadout } | { refused: PickRefusal; at: number } {
  let kit = current;
  for (let at = 0; at < picks.length; at++) {
    const { slot, id } = picks[at]!;
    if (!Number.isInteger(slot) || slot < 0 || slot > 4) return { refused: 'slot', at };
    if (!arsenal.items.has(id)) return { refused: 'unknown', at };
    const seen = menuValves(valves, kit[0]!);
    if (slotLocked(seen, side, kit, slot)) return { refused: 'locked', at };
    if (!selectable(seen, side, kit, slot, id)) return { refused: 'refused', at };
    kit = pick(arsenal, valves, side, kit, slot, id).loadout;
  }
  return { loadout: kit };
}
