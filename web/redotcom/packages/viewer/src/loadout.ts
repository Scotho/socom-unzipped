import type { AssetSource } from '@s2u/archive';
import {
  DEFAULT_SIDEARM, DEFAULT_WEAPON, DOUBLED_CLASSES, EMPTY_ITEM, HE, HELD_RIFLE, HELD_SIDEARM, ITEM, itemClass, M67, readKitTable,
  readMapArsenal, type KitTable, type Loadout, type MapArsenal, type Pick, type Side, type WeaponRecord,
} from '@s2u/scene';
import { magazinesCarried } from './magazines';

/**
 * The runtime kit (web sprint 4, M3/M4; spec §4's goal, W4.R2, W4.R6): what a SEAL or a Terrorist carries is a
 * `Loadout` -- five item ids, slot order primary, secondary, equipment 1-3 (`@s2u/scene` `arsenal.ts`) -- and every
 * per-weapon thing the page, the page's own match (`./net/loopback`) and the match server do follows it. One module,
 * headless (the shared sim: `./sim`), so the three read a slot the same way.
 *
 * - **The spawn kit** is the character type's `default_weapons` (`character.rdr` through `chartype.rdr`, research 91
 *   §14; R94.7: given as the game gives it, never checked against the valves). Which type a player is is the game's
 *   own open question -- `DEFAULT_CHARTYPE_PLACEHOLDER` (research 91): the side's first, `mp2_seal1` on Frostfire, as
 *   the body (`./body`) and the hit volumes (`./simMap`) already take it.
 * - **A pick** is written to the player's character type and applied at the next rebuild of the body -- in classic, the
 *   next round (`FUN_0023e5e0` L88381-88405 writes the type's kit; `FUN_00599b60` -> `FUN_00599f00` L455715-455836
 *   rebuilds it at the spawn; research 94 §A6, R94.3). So a pick is kept per side (each side's type is its own) and a
 *   new map, a new match, starts from the types' own kits (`PlayerLoadout`).
 * - **The two firearm slots** are the game's own: slot 0 the primary, which L1 takes up (`FUN_00594cf0`, the
 *   controller's `+0x224` = 0.0), and slot 1 the secondary, L2's (`+0x228` = 1.0; `./kit`'s `rifle` and `pistol`). The
 *   record behind each is the loadout's item's (`KitTable.records`; the MGL's and the M79's as carriers, M4); a slot
 *   whose item has no firearm record -- none on the disc's kits; the Designator or an empty slot in a later pick --
 *   keeps the baked record of that slot (`NO_FIREARM_RECORD_PLACEHOLDER`).
 * - **2X** (Double Ammo Load, id 194) anywhere in the kit doubles `NumMags` of every pistol, SMG, rifle, shotgun, MG and
 *   sniper it holds, at most the ring's ten, the extra magazines full (`FUN_005c75f0` L480207-480270, called by the
 *   kit's finaliser at every spawn; research 94 §A7, R94.13); `Ammo_Capacity` is unchanged. The ring (`./magazines`)
 *   fills `mags` magazines, so the record handed on carries the doubled count.
 *
 * Without `ZWEAPON.ZAR` (a test with no fixtures) the kit is the baked pair the viewer held before this sprint:
 * `BAKED_LOADOUT`, the M4A1 SD and the Mark 23 (`@s2u/scene` `weapons.ts`, each proven against the file).
 */

/** A firearm slot: 0 the primary (L1, `./kit`'s `rifle`), 1 the secondary (L2, `pistol`). */
export type FirearmSlot = 0 | 1;

/** The kit without the disc's tables: the baked M4A1 SD and Mark 23, the M67 and the HE (the viewer's kit to web sprint 3). */
export const BAKED_LOADOUT: Loadout = [HELD_RIFLE.id, HELD_SIDEARM.id, M67.id, HE.id, EMPTY_ITEM];
const BAKED_RECORDS: readonly [WeaponRecord, WeaponRecord] = [HELD_RIFLE, HELD_SIDEARM];
/**
 * NO_FIREARM_RECORD_PLACEHOLDER: what a firearm slot fires when its item has no firearm record -- the Designator (11),
 * the M203 item (141) or an empty slot a later pick leaves -- the baked record of that slot. No default kit on the disc
 * holds such a slot (research 94 §A4). Web sprint 4 M4 retired it for the MGL and the M79: the kit table reads them as
 * carriers (`@s2u/scene` `kitTableOf`), which fire their rounds as fire modes (R94.8, `./firearms`).
 */
const NO_FIREARM_RECORD_PLACEHOLDER = BAKED_RECORDS;
/** The baked pair's held models (`@s2u/scene` `weapon.ts`: the M4A1 SD's `m4Acarbine_sd`, the Mark 23's `a_mark23`). */
const BAKED_MODELS: readonly [string, string] = [DEFAULT_WEAPON, DEFAULT_SIDEARM];
/**
 * The baked pair's HUD icons, as the HUD drew them before the kit was read (`./hudAssets`' two firearm icons): the
 * M4's `m4carbine_icon.tif` (the HUD's own default, `./hud`) and the Mark 23's `mark23_icon.tif`.
 */
export const BAKED_ICONS: readonly [string, string] = ['m4carbine_icon.tif', 'mark23_icon.tif'];

/** Whether the kit holds the Double Ammo Load (`FUN_005c75f0`: any kit item 194). */
export function holdsDoubleAmmo(loadout: Loadout): boolean {
  return loadout.includes(ITEM.DOUBLE_AMMO);
}

/** A firearm's record as the kit carries it: `NumMags` doubled (at most ten) when 2X is in the kit and its class is doubled. */
export function withDoubleAmmo(record: WeaponRecord, loadout: Loadout): WeaponRecord {
  if (!holdsDoubleAmmo(loadout) || !DOUBLED_CLASSES.has(itemClass(record.id))) return record;
  return { ...record, mags: magazinesCarried(record.mags, true) };
}

/** The record a firearm slot holds: the loadout item's (2X applied), else the baked record of that slot. */
export function slotRecord(table: KitTable | null, loadout: Loadout, slot: FirearmSlot): WeaponRecord {
  return withDoubleAmmo(table?.records.get(loadout[slot]) ?? NO_FIREARM_RECORD_PLACEHOLDER[slot], loadout);
}

/** Both firearm slots' records, slot order (the room's and the page's `[rifle, pistol]`). */
export function kitRecords(table: KitTable | null, loadout: Loadout): readonly [WeaponRecord, WeaponRecord] {
  return [slotRecord(table, loadout, 0), slotRecord(table, loadout, 1)];
}

/** The held model of a firearm slot: the item's `ModelName`; null for none (an empty slot); the baked pair's without the tables. */
export function slotModel(table: KitTable | null, loadout: Loadout, slot: FirearmSlot): string | null {
  if (!table) return BAKED_MODELS[slot];
  return table.arsenal.items.get(loadout[slot])?.model ?? null;
}

/** The HUD weapon box's icon of a firearm slot: the item's `IconTextureName` (research 94 §C9), lower case as the HUD keys it. */
export function slotIcon(table: KitTable | null, loadout: Loadout, slot: FirearmSlot): string | null {
  if (!table) return BAKED_ICONS[slot];
  return table.arsenal.items.get(loadout[slot])?.icon?.toLowerCase() ?? null;
}

/** A side's spawn kit on a map: its first character type's (`DEFAULT_CHARTYPE_PLACEHOLDER`), or null without the map's table. */
export function typeLoadout(map: MapArsenal | null, side: Side): Loadout | null {
  return map?.kits[side][0]?.loadout ?? null;
}

/**
 * The developer's kit, `&kit=<id>,<id>,...` (up to five item ids, slot order; the rest empty): what a test that pins
 * a weapon spawns with (the page honours it only with `?devmode`, `./main`). Null when absent or not five ids 0-255.
 */
export function kitParam(search: string): Loadout | null {
  let raw: string | null;
  try { raw = new URLSearchParams(search).get('kit'); } catch { return null; }
  if (!raw) return null;
  const parts = raw.split(',');
  if (parts.length > 5 || !parts.every((p) => /^\d{1,3}$/.test(p) && Number(p) <= 255)) return null;
  const ids = parts.map(Number);
  while (ids.length < 5) ids.push(EMPTY_ITEM);
  return ids as unknown as Loadout;
}

/** Five item ids 0-255 off the wire (a `spawn`'s or a `loadout` answer's `kit`) as a loadout, or null. */
export function wireLoadout(ids: readonly unknown[] | null | undefined): Loadout | null {
  if (!Array.isArray(ids) || ids.length !== 5 || !ids.every((v) => Number.isInteger(v) && (v as number) >= 0 && (v as number) <= 255)) return null;
  return [...ids] as unknown as Loadout;
}

/**
 * The player's kit on the page: the loadout on the body, each side's pick waiting on its type, and the developer's
 * `&kit=`. `spawn` is the rebuild (`FUN_00599f00`): the side's pick, else the type's own kit, else the baked one.
 *
 * Protocol 7 (web sprint 4, M9): in a match the room owns the kit (W4.R6). Each confirm of the weapon select is kept
 * here, per side, in order since the map's match began (`confirm`, `picks`): the list the page sends as its `loadout`
 * request and the room replays from the type's own kit (`base`) -- the whole list each time, so a reconnect's new seat
 * is sent it again and lands on the same kit. The room's answer is the side's next kit (`answer` -> `pending`), and a
 * match's spawn carries the kit the room gave the body (`spawn`'s `kit`), which the page takes as it is.
 */
export class PlayerLoadout {
  private table: KitTable | null = null;
  private map: MapArsenal | null = null;
  private current: Loadout = BAKED_LOADOUT;
  private readonly next: Record<Side, Loadout | null> = { seal: null, terrorist: null };
  private readonly confirmed: Record<Side, Pick[]> = { seal: [], terrorist: [] };
  private dev: Loadout | null = null;

  /** A new map (a new match): its tables, and the types' own kits -- the picks of the last map's types go. */
  setMap(table: KitTable | null, map: MapArsenal | null): void {
    this.table = table;
    this.map = map;
    this.next.seal = this.next.terrorist = null;
    this.confirmed.seal = [];
    this.confirmed.terrorist = [];
  }

  /** The developer's `&kit=`: each side's pick on every map, until a pick replaces it. */
  setDevKit(loadout: Loadout | null): void {
    this.dev = loadout;
  }

  /** The developer's kit, or null: in the page's own room it stands in for the type's own (`RoomOptions.soloKit`). */
  devKit(): Loadout | null {
    return this.dev;
  }

  /** A pick written to the side's type as it is (the hook's `setLoadout`, a developer's), applied at its next spawn. */
  setLoadout(loadout: Loadout, side: Side): void {
    this.next[side] = [...loadout] as unknown as Loadout;
  }

  /** What the side's next spawn will take if nothing changes: its pick, or the developer's kit; null for the type's own. */
  pending(side: Side): Loadout | null {
    return this.next[side] ?? this.dev;
  }

  /** The kit the side's picks are replayed from: the developer's kit, else the type's own, else the baked one. */
  base(side: Side): Loadout {
    return this.dev ?? typeLoadout(this.map, side) ?? BAKED_LOADOUT;
  }

  /** The side's confirmed picks since the map's match began, in order: the `loadout` request's list. */
  picks(side: Side): readonly Pick[] {
    return this.confirmed[side];
  }

  /**
   * A confirm of the weapon select (`FUN_0023e5e0`: the kit written to the type): the pick added to the side's list;
   * the list to send. `compact`, when given, may replace the list with a shorter one that reaches the same kit.
   */
  confirm(side: Side, pick: Pick, compact?: (picks: readonly Pick[]) => Pick[]): readonly Pick[] {
    const list = [...this.confirmed[side], { slot: pick.slot, id: pick.id }];
    this.confirmed[side] = compact ? compact(list) : list;
    return this.confirmed[side];
  }

  /**
   * The room refused the side's list at pick `at` (its answer's `refused.at`): that pick and the ones after it are
   * dropped, so the list the page sends next is the one the room holds, not one it will refuse again.
   */
  refused(side: Side, at: number): void {
    if (Number.isInteger(at) && at >= 0 && at < this.confirmed[side].length) this.confirmed[side] = this.confirmed[side].slice(0, at);
  }

  /** The room's answer to a `loadout` request: the kit it holds for the side's next round (five ids; anything else is ignored). */
  answer(side: Side, kit: readonly number[]): void {
    const l = wireLoadout(kit);
    if (l) this.next[side] = l;
  }

  /**
   * The rebuild at a spawn: the loadout the body now carries. `kit`: a match's spawn names the kit the room gave the
   * body (protocol 7), which is taken as it is. `network` without a kit: the type's kit, as a network room gives it.
   */
  spawn(side: Side, opts: { network?: boolean; kit?: readonly number[] | null } = {}): Loadout {
    const given = wireLoadout(opts.kit);
    const pick = given ?? (opts.network ? null : this.pending(side));
    this.current = pick ?? typeLoadout(this.map, side) ?? BAKED_LOADOUT;
    return this.current;
  }

  /** The loadout on the body. */
  loadout(): Loadout { return this.current; }
  tables(): KitTable | null { return this.table; }
  records(): readonly [WeaponRecord, WeaponRecord] { return kitRecords(this.table, this.current); }
  model(slot: FirearmSlot): string | null { return slotModel(this.table, this.current, slot); }
  icon(slot: FirearmSlot): string | null { return slotIcon(this.table, this.current, slot); }
}

/** The kit's tables as the room holds them: the disc's and the map's (null without its `READERM.ZAR`). */
export interface SimKits { table: KitTable; map: MapArsenal | null }

/** What a source's kit tables are read from once: `ZWEAPON.ZAR`'s table and `READERC.ZAR`'s bytes (the kits' characters). */
export interface KitSource { table: KitTable; readerc: Uint8Array }

const kitSources = new WeakMap<AssetSource, Promise<KitSource | null>>();

/**
 * `RUN/ZWEAPON.ZAR` and `RUN/READERC.ZAR` off a source (the served tree, the disc image, the server's `SOCOM_DISC`),
 * read once per source; null when either is not there or will not read -- the baked kit then.
 */
export function loadKitSource(source: AssetSource): Promise<KitSource | null> {
  let pending = kitSources.get(source);
  if (!pending) {
    pending = (async (): Promise<KitSource | null> => {
      try {
        const [zweapon, readerc] = await Promise.all([source.read('RUN/ZWEAPON.ZAR'), source.read('RUN/READERC.ZAR')]);
        return { table: readKitTable(zweapon), readerc };
      } catch {
        return null;
      }
    })();
    kitSources.set(source, pending);
  }
  return pending;
}

/** A map's kits: its `READERM.ZAR` through the source's tables; the map's part null when it will not read. */
export function simKitsFromBytes(kits: KitSource, mapBytes: Uint8Array): SimKits {
  let map: MapArsenal | null = null;
  try { map = readMapArsenal(kits.table.arsenal, mapBytes, kits.readerc); } catch { map = null; }
  return { table: kits.table, map };
}
