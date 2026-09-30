import {
  AN_M8, BACKBLAST_CONE, CLAYMORE, CLAYMORE_RULES, EMPTY_ITEM, FULL_SLOT, HE, ITEM, M67, MARK141, ROCKET_LAUNCH_SPEED_READING,
  backblastLaunch, inCone, itemClass, type KitTable, type Loadout, type ThrowableRecord, type V3,
} from '@s2u/scene';
import type { MapAction } from './mapActions';
import { ACTION_SECONDS } from './mover';

/**
 * The equipment slots and what each item does in the match (web sprint 4, M7; spec W4.R5; research 94 §C4, §C5, §C7,
 * research 85 §9) -- headless, the rules the page (`./grenade`, `./rocket`, `main.ts`) and the match server's room
 * (`packages/server/src/room.ts`) share through the sim's boundary (`./sim`):
 *
 * - **The three equipment slots** are the kit's slots 2-4, in kit order (`EQUIPMENT_SLOTS`; research 91 §14,
 *   `UIChooseEquip1..3`). The PC takes them up with `3`, `4` and `5` (W4.R5; `5` is the sprint's ruling for the owner to
 *   confirm); the pad keeps the game's own ways -- R2's Inventory, and L1/L2 on the slots it assigns (research 85 §9.1).
 * - **Which slot may be taken up** is `FUN_005bdc30` (L474604-474660): not the rounds (the launcher and rocket rounds
 *   are fire modes of their carrier), a rocket launcher only while it holds a round it fires, never the M203 item, an
 *   empty slot, C4 (its plant is the Action button at a target), `FULL_SLOT`, the thermal scope, 2X, the Satchel, 154,
 *   armour and up; the Detonator only while one of the SEAL's charges is down (`slotSelectable`).
 * - **The pouch** is what the loadout's equipment slots hold, each slot its record's `Ammo_Capacity` x `NumMags` (the
 *   kit's set-up, `FUN_00599f00` L455790-455836; research 94 §A6): two M67 slots carry six. This retires the room's
 *   `POUCH_PLACEHOLDER` (every throwable at its capacity whatever the kit held).
 * - **C4** is timed, not remote, and planted only on a C4 target the SEAL stands at, still (`FUN_005be9a0` L475378-475470;
 *   the Action path L452025-452060 `FUN_005c0020(1.0, 0.2, kit, 0x97)`): `c4Targets`, `c4TargetInReach`.
 * - **The rockets** (LAW, RPG-7) leave straight along the aim at their round's `Muzzle_Velocity`
 *   (`ROCKET_LAUNCH_SPEED_READING`) -- no loft: `FUN_005bf8a0` lofts only the grenade launchers' rounds (`FUN_005bd6d0`:
 *   carriers 52, 61, 63, 142, 143) -- and each shot fires the `Backblast` (159) backwards from the muzzle, whose damage
 *   reaches only inside its 45-degree cone (`backblastReaches`).
 */

/** The kit's equipment slots, in kit order (slot 0 the primary, 1 the secondary). */
export const EQUIPMENT_SLOTS = [2, 3, 4] as const;

/** What an equipment item is to the kit's use of it. */
export type EquipmentKind = 'throwable' | 'placed' | 'c4' | 'launcher' | 'round' | 'detonator' | 'gear' | 'none';

/** An item's kind by its id (`FUN_003d1a60`'s classes, research 94 §A0; the charges by their type bytes). */
export function equipmentKind(id: number): EquipmentKind {
  const c = itemClass(id);
  if (c === 'grenade') return 'throwable';
  if (id === ITEM.C4) return 'c4';
  if (id === ITEM.CLAYMORE || id === ITEM.PMN) return 'placed';
  if (c === 'rocketLauncher') return 'launcher';
  if (c === 'launcherRound' || c === 'rocketRound') return 'round';
  if (id === ITEM.DETONATOR) return 'detonator';
  if (c === 'gear') return 'gear';
  return 'none';
}

/** What `FUN_005bdc30` asks of the kit beside the slot's item. */
export interface SlotContext {
  /** The SEAL's charges down (`FUN_003cc1f0(0x4b5220, owner)`). */
  chargesDown: number;
  /** The rounds the kit holds for a rocket launcher (`FUN_005c45c0`: `FUN_005c3ee0` finds a round id > 3). */
  roundsFor(launcher: number): number;
}

/**
 * `FUN_005bdc30` (L474604-474660): whether a kit slot holding `id` may be taken up -- the number keys', R2's and L1/L2's
 * common gate. The thermal scope (0xc3) and 2X (0xc2) are refused here, so their slots hold nothing in the hand and are
 * never selected (R94.13, R94.15: they act from the kit); C4 (0x97) is refused too, planted by the Action button.
 * (`FUN_005857e0(body)`, the rocket launcher's second test, is not read: `LAUNCHER_BODY_READING`, taken as true.)
 */
export const LAUNCHER_BODY_READING = true;
export function slotSelectable(id: number, ctx: SlotContext): boolean {
  if (id === EMPTY_ITEM || id === FULL_SLOT || id >= 0xca) return false;
  const kind = equipmentKind(id);
  if (kind === 'round') return false;                                            // FUN_003c5d20: 0xab, 0xb9
  if (kind === 'launcher') return ctx.roundsFor(id) > 0 && LAUNCHER_BODY_READING;  // FUN_005c45c0, FUN_005857e0
  if (id === ITEM.DETONATOR) return ctx.chargesDown > 0;
  return ![ITEM.M203, ITEM.C4, ITEM.THERMAL, ITEM.SATCHEL, 0x9a, ITEM.DOUBLE_AMMO].includes(id as never);
}

/**
 * LAUNCHER_RAISE_READING: how long a rocket launcher takes to come up (or go back for the firearm) before the other may
 * fire. The kit's switch (`FUN_005c4b10`) changes the category (`FUN_005c50b0`) and starts the swap through
 * `FUN_005c1660` -> `FUN_005a64c0`, whose clip for a launcher was not traced; read as the firearms' standing swap
 * (`Rifle -> Pistol`, `ACTION_SECONDS.swapStand`, the room's and the page's one sourced swap length).
 */
export const LAUNCHER_RAISE_READING = ACTION_SECONDS.swapStand;

/** The launcher's round (`roundFits` for the rockets: the LAW its LAW HEAT, the RPG-7 its RPG), null for none. */
export function rocketRoundOf(launcher: number): number | null {
  return launcher === ITEM.LAW ? ITEM.LAW_HEAT : launcher === ITEM.RPG7 ? ITEM.RPG_ROUND : null;
}

/** The throwables the viewer carries without the disc's tables, by id (`@s2u/scene`'s transcriptions, proven against the file). */
const BAKED: ReadonlyMap<number, ThrowableRecord> = new Map([M67, HE, AN_M8, MARK141, CLAYMORE].map((r) => [r.id, r]));

/** A throwable's or a charge's record: the kit table's (the disc's), else the baked transcription; null for none. */
export function throwableOf(table: KitTable | null, id: number): ThrowableRecord | null {
  return table?.throwables?.get(id)?.record ?? BAKED.get(id) ?? null;
}

/**
 * The pouch a loadout carries (the kit's set-up `FUN_00599f00`, research 94 §A6): each equipment slot holding a
 * throwable or a charge gives its record's `Ammo_Capacity` x `NumMags`, summed by the record's name (two M67 slots,
 * six M67s); 2X doubles none of them (R94.13). Names in kit order.
 */
export function pouchOf(loadout: Loadout, table: KitTable | null): Record<string, number> {
  const out: Record<string, number> = {};
  for (const s of EQUIPMENT_SLOTS) {
    const id = loadout[s]!, kind = equipmentKind(id);
    if (kind !== 'throwable' && kind !== 'placed' && kind !== 'c4') continue;
    const r = throwableOf(table, id);
    if (!r) continue;
    out[r.name] = (out[r.name] ?? 0) + r.capacity * Math.max(1, r.mags);
  }
  return out;
}

// ---- C4 -----------------------------------------------------------------------------------------------------------

/**
 * The action object's default reach (`FUN_002b49f0` L157032-157066: `+0x1c` = 0x42000000, 32 units) when `actions.rdr`
 * gives no `range` (`FUN_0032ea80(..., "range", ...)` L157290 keeps the default).
 */
export const ACTION_RANGE_DEFAULT = 32;

/** A C4 target: its node, where it stands, and the reach an actor plants from. */
export interface C4Target { node: string; at: V3; range: number }

/**
 * C4_TARGET_READING (research 94 §C5.1): which map objects take C4. The plant asks the body's current action object
 * (`body+0x3dc`) for the object hung on its node (`+0x94`) and that object's `vtable+0x10` with the charge's
 * `Explosion_Damage` (`kit+0x8a0`, `FUN_005c77b0` L480274-480290). `actions.rdr`'s own actions (`FUN_002b49f0`, vtable
 * 0x406390) answer 0 there (`FUN_00216760`: `jr ra; v0 = 0`); the one that can answer 1 is the zAnim destructible
 * `FUN_002740e0` hangs on a node (vtable 0x406090, `+0x10` = `FUN_002739b0`: its hit points `+0x1c` > 0 and its damage
 * threshold `+0x10` <= the charge's damage), built from a zAnim's damage block of kind 3 (`FUN_002713f0` L119312-119335)
 * -- a block not decoded here. What the map data does mark: `actions.rdr`'s entries with no `type` (the parser's
 * default 8, "UNKNOWN", L157331-157365) whose `anim` destroys the object and whose `valve` sets it -- `access_action1`
 * .. with `set_access1` / `destroy_access1` and `points 2` on the BREACH maps, MP73's `rtower_action` and the access
 * actions under `action_place_c4.tif`. Read so: every type-less action is a C4 target, planted from its `range`
 * (else `ACTION_RANGE_DEFAULT`).
 */
export function c4Targets(actions: readonly MapAction[]): C4Target[] {
  const C4_TARGET_READING = actions.filter((a) => a.type === '');
  return C4_TARGET_READING.map((a) => ({ node: a.node, at: [a.at[0], a.at[1], a.at[2]], range: a.range > 0 ? a.range : ACTION_RANGE_DEFAULT }));
}

/**
 * The plant's other tests (`FUN_00594cf0` L452027-452040 and `FUN_005be9a0` L475400-475404): `body+0x208 < 396`
 * (`C4_REACH_READING`, not read: the target's own reach stands for it) and the SEAL still (`FUN_005be990(kit) == 0`,
 * `+0xe84 == 0`) -- `C4_STILL_READING`: the claymore's own "not moving" speed (`CLAYMORE_RULES.maxSpeed`, 3.2 u/s,
 * `+0xf88`), the kit's one sourced threshold. `C4_PLANT_TIME_READING`: the plant's action (0x3e) runs its callback
 * `LAB_005bfe40` at rate 0.45 from `kit+0x87c` = 99 (L475440-475452), not read; the charge goes down after the
 * claymore's own `placeSeconds` (1.3 s) as the stand-in.
 */
export const C4_STILL_READING = CLAYMORE_RULES.maxSpeed;
export const C4_PLANT_TIME_READING = CLAYMORE_RULES.placeSeconds;

/** The C4 target in reach of the feet (the nearest within its range), or null. */
export function c4TargetInReach(targets: readonly C4Target[], feet: readonly number[]): C4Target | null {
  let best: C4Target | null = null, bestD = Infinity;
  for (const t of targets) {
    const d = Math.hypot(t.at[0] - feet[0]!, t.at[1] - feet[1]!, t.at[2] - feet[2]!);
    if (d <= t.range && d < bestD) { best = t; bestD = d; }
  }
  return best;
}

/** Whether C4 may be planted now: a target in reach and the SEAL still (`C4_STILL_READING`); the target, else null. */
export function c4Plant(targets: readonly C4Target[], feet: readonly number[], speed: number): C4Target | null {
  if (!(speed <= C4_STILL_READING)) return null;
  return c4TargetInReach(targets, feet);
}

// ---- the rockets ----------------------------------------------------------------------------------------------------

/**
 * A rocket's launch (`FUN_003cb1a0` L320723-320731, `FUN_003d2d70`): straight from the muzzle toward the aimed point, at
 * the round's `Muzzle_Velocity` (`ROCKET_LAUNCH_SPEED_READING`: the muzzle velocity, not at rest), then its
 * `AccelerationFactor` along the flight (`stepGrenade`). The backblast leaves the same muzzle backwards.
 */
export function rocketLaunch(record: ThrowableRecord, from: V3, target: V3): { dir: V3; velocity: V3; backblast: { pos: V3; dir: V3 } } {
  const d: V3 = [target[0] - from[0], target[1] - from[1], target[2] - from[2]];
  const l = Math.hypot(...d) || 1;
  const dir: V3 = [d[0] / l, d[1] / l, d[2] / l];
  const speed = ROCKET_LAUNCH_SPEED_READING === 'muzzle' ? record.muzzleVelocity : 0;
  return { dir, velocity: [dir[0] * speed, dir[1] * speed, dir[2] * speed], backblast: backblastLaunch(from, dir) };
}

/**
 * Whether the backblast from `origin` along `axis` (unit: the launcher's aim reversed) reaches `point` (`GetDamage`
 * 0x3c7600 for 0x9f, online): inside its `Explosion_Radius` and its 45-degree cone (`BACKBLAST_CONE`).
 */
export function backblastReaches(origin: readonly number[], axis: V3, point: readonly number[], radius: number): boolean {
  return inCone([point[0]! - origin[0]!, point[1]! - origin[1]!, point[2]! - origin[2]!], axis, BACKBLAST_CONE, radius);
}
