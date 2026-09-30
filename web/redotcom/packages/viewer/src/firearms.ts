import { ITEM, type KitRound, type KitTable, type Loadout, type WeaponRecord } from '@s2u/scene';
import { MagazineRing } from './magazines';

/**
 * Each firearm class's own behaviour (web sprint 4, M4; research 94 part 3, §C1-§C4), the rules the page's `Fire`
 * (`./fire`) and the match server's room (`packages/server/src/room.ts`) share -- headless, through the sim's boundary
 * (`./sim`). What sets a class apart is a handful of `zweapon.rdr` keys (`@s2u/scene` `WeaponRecord`'s class keys, read
 * only when present) and the id ranges; the rules are the kit's (`CZKit`, body `+0x5e0`):
 *
 * - **The reload's delay** (`ReloadDelay`, `+0x5c`, default 0.01): the kit's lock timer `kit+0x820` (flag 0) before a
 *   reload lands -- the button's (`FUN_002c64e0(6)` -> `FUN_005c32b0(-1.0, kit, 0)`, L453459-453463) and the last
 *   round's (`FUN_005c5340` L479317-479320); `FUN_005c0fd0` (L476549-476561) runs it down and, at 0, reloads
 *   (`FUN_005c2a90`). No round leaves while it runs (the fire tick `FUN_005c1970` is not called).
 * - **The bolt and the pump** (`ReloadAfterShot` + `ReloadDelayAfterShot`, `+0x58`/`+0x60`, default 0.01): after a round
 *   with another left, the same timer (flag 1) -- then `FUN_005c3000` (L477551-477650) plays the after-shot clip
 *   (`FUN_005a82e0(body, 1)`: the `Shotgun pump` family on the shotgun class, the shotgun reload on a bolt, `./reloadClip`)
 *   and the held weapon's `ReloadAfterShotSound` (`.SHOTGUN_COCK`, the 870 only). The clip is a reload action, so it
 *   holds the fire as a reload does (`FUN_005a7ab0` L462527-462540 lists `Shotgun pump`, its crouched and prone
 *   copies, the shotgun reloads and `Rifle m203 reload`): `PUMP_BLOCKS_FIRE_READING`, resolved so.
 * - **The shotgun's pellets** (the round's `NumProjectilesFired`, the 12 gauge's 4, R94.10): a pull fires that many rays,
 *   each its own cone draw (`FUN_005be9a0` L475580-475677, the controller's `+0x74` per pellet), one shell off the
 *   magazine (L475608-475615: the shotgun class, pellet 0 only). The victim's side is `./net/damage`'s `shotgunPellets`.
 * - **The 40 mm launchers' rounds are fire modes** of the carrier (R94.8, §C4.2): a slot mode over 3 is the item id of a
 *   round the kit holds in another slot (`FUN_005c6600` L479603-479660 redirects the fire, the reload and the HUD to
 *   it); the switch (`./accuracy` `nextFireMode`) runs on from the rifle's modes into each round type held
 *   (`FUN_005c4480`, `FUN_005c3ee0` with `roundFits`). `KitRounds` keeps each round slot's count.
 */

/** `ReloadDelay`'s default (`FUN_003cda30` L322543-322547, `FUN_003d2c30`). */
export const RELOAD_DELAY_DEFAULT = 0.01;
/** `ReloadDelayAfterShot`'s default (L322548-322552, `FUN_003d2c10`): the 870's lock (R94.12). */
export const AFTER_SHOT_DEFAULT = 0.01;

/** The lock before a reload lands, seconds: the record's `ReloadDelay`, else the default. */
export function reloadDelayOf(r: Pick<WeaponRecord, 'reloadDelay'>): number {
  return r.reloadDelay ?? RELOAD_DELAY_DEFAULT;
}

/** The rays a pull fires: the round's `NumProjectilesFired`, else 1 (`FUN_003d44e0`). */
export function pelletsOf(r: Pick<WeaponRecord, 'pellets'>): number {
  return Math.max(1, Math.floor(r.pellets ?? 1));
}

/**
 * The held items that never arm the kit's lock after a round (`FUN_005c5340` L479305-479313: `EQUIP_NONE` 255,
 * `FULL_SLOT` 254, the thermal scope 195, 2X 194, the LAW 145, the M203 141, the RPG-7 146, the Designator 11, the
 * Detonator 193, 190).
 */
export const LOCK_EXEMPT: ReadonlySet<number> = new Set([255, 254, 195, 194, 145, 141, 146, 11, 193, 190]);

/** What a fired record says of the lock after it (`WeaponRecord`'s class keys; a round's `KitRound`). */
export interface AfterShotKeys { reloadAfterShot?: boolean; reloadDelayAfterShot?: number }

/**
 * The lock after a round leaves (`FUN_005c5340` L479321-479343), seconds, or null for none: the held item (the kit's
 * selected slot) not `LOCK_EXEMPT`, a round left in the magazine (the last one reloads instead, L479317-479320), the
 * fired record -- the weapon's, or in a round mode the round's (`lVar15`) -- a `ReloadAfterShot` one, and the firing
 * carrier not the MGL (L479325: `lVar13->ID != 0x8e`). The lock is its `ReloadDelayAfterShot`, else the default.
 * (The RPG's round arms it even on its last round, to feed the next: the rockets are M7's, not modelled here.)
 */
export function afterShotLock(held: number, fired: AfterShotKeys, roundsLeft: number, carrier: number | null): number | null {
  if (LOCK_EXEMPT.has(held) || roundsLeft <= 0 || !fired.reloadAfterShot || carrier === ITEM.MGL) return null;
  return fired.reloadDelayAfterShot ?? AFTER_SHOT_DEFAULT;
}

/**
 * `FUN_003c5b20` (L317165-317200) with the carrier its caller `FUN_005c3ee0` (L478297-478480) passes: which rounds a
 * carrier's modes run on into -- the M79 (0x8f) its GL rounds 176-179, the MGL (0x8e) and the M203 rifles (52, 61:
 * `FUN_003c5e40`) the 203 rounds 171-175, the F2000 (0x3f) its own 181-183, the LAW 185 and the RPG-7 186.
 */
export function roundFits(carrier: number, round: number): boolean {
  if (carrier === ITEM.M79) return round >= 176 && round <= 179;
  if (carrier === ITEM.MGL || carrier === ITEM.M16_203 || carrier === ITEM.M4_203) return round >= 171 && round <= 175;
  if (carrier === ITEM.F2000) return round >= 181 && round <= 183;
  if (carrier === ITEM.LAW) return round === ITEM.LAW_HEAT;
  if (carrier === ITEM.RPG7) return round === ITEM.RPG_ROUND;
  return false;
}

/** Whether an item is a carrier whose modes run on into rounds (`FUN_003c5d80` L317277-317300, the launchers of M4). */
export function isCarrier(id: number): boolean {
  return id === ITEM.M16_203 || id === ITEM.M4_203 || id === ITEM.F2000 || id === ITEM.MGL || id === ITEM.M79;
}

/** One kit slot as the switch walks it: its item and whether its ring holds rounds (`kit+0x1d4 + slot x 0x28`, any > 0). */
export interface HeldRound { slot: number; id: number; rounds: number }

/**
 * The kit's round slots (web sprint 4, M4): each equipment slot holding a launcher round or a rocket keeps its own ring
 * of `Ammo_Capacity` x `NumMags` (the kit's set-up, `FUN_005bdfb0`/`FUN_005bde20`, research 94 §A6: the M203 FRAG's
 * 6 x 1), never doubled by 2X (R94.13). The carrier's own record (the MGL's 6 x 2) keeps its ring in `Fire`; its
 * rounds come off these (`FUN_005be9a0` L475640-475670, the round slot's decrement).
 */
export class KitRounds {
  private readonly rings: (MagazineRing | null)[];

  constructor(private readonly table: KitTable | null, private readonly loadout: Loadout) {
    this.rings = loadout.map((id, slot) => {
      const item = slot >= 2 ? table?.arsenal.items.get(id) : undefined;
      return item && (item.cls === 'launcherRound' || item.cls === 'rocketRound') ? new MagazineRing(item.magazine, Math.max(1, item.mags)) : null;
    });
  }

  /** Every kit slot, in order, with its rounds (0 for a slot that is no round's). */
  held(): HeldRound[] {
    return this.loadout.map((id, slot) => ({ slot, id, rounds: this.rings[slot]?.total() ?? 0 }));
  }

  /** `FUN_005c6600`'s redirect: the first slot holding round `id` with rounds, else the first holding it at all; null for none. */
  ring(id: number): MagazineRing | null {
    let any: MagazineRing | null = null;
    for (let s = 0; s < this.loadout.length; s++) {
      const r = this.rings[s];
      if (!r || this.loadout[s] !== id) continue;
      if (r.total() > 0) return r;
      any ??= r;
    }
    return any;
  }

  /** The round's projectile and fire keys (`KitTable.rounds`), null without the tables. */
  round(id: number): KitRound | null {
    return this.table?.rounds.get(id) ?? null;
  }

  /** A spawn's fresh kit: every round slot full again (`FUN_00599f00`, research 91 §4.3). */
  fill(): void {
    for (const r of this.rings) r?.fill();
  }
}

/**
 * R94.16 (research 94 §C1.5; the HUD L70235-70257): the reticle turns grey (130, 130, 130: `DAT_003dc588/90/98`) while
 * the aimed point is **inside** the fired round's `ArmingDistance` of the launch point -- a round landing there is a
 * dud. False for a round with none (the smoke rounds) or no round mode. For the reticle's drawing (`./reticle`).
 */
export function insideArming(round: { armingDistance?: number } | null, from: readonly number[], aimed: readonly number[]): boolean {
  const d = round?.armingDistance ?? 0;
  if (!(d > 0)) return false;
  return Math.hypot(aimed[0]! - from[0]!, aimed[1]! - from[1]!, aimed[2]! - from[2]!) < d;
}
