import type { Object3D } from 'three';
import { ITEM, itemClass, type WeaponRecord } from '@s2u/scene';

/**
 * Each weapon's sights (web sprint 4 M5; research 94 §C1.4, §C6, §C7, R94.15; research 84 §7-§9): the pure rules the
 * page reads per record and per kit. The view states themselves are `./zoom`'s, the reticle's sets and colours
 * `./reticle`'s, the lens's rows `./lensFx` and `./nightVision`.
 *
 * - **The zoom levels** are the record's `ZoomMode1..NumZoomModes-1` (`FUN_005448a0`: state s >= 5 magnifies by
 *   `ZoomMode[s - 4]`; `ZoomMode0`, 1.5 on every record, is never a magnification): the M4A1 2.5, the M4A1 SD, 552,
 *   552SD and Groza 3, the SA-80 A2 4, the Steyr Aug 2.5, the SR-25s and the Dragunov 8, the M40A1 6 and 12, the
 *   M82A1A and the M87ELR 8 and 16 (research 94 §C1.4, pinned against the disc by `test/sights.test.ts`).
 * - **The scope overlay** is one set for every scoped weapon: a magnification over 1.01 draws set 5 (`FUN_005be300`
 *   L474922), `ret_scope_01` and `ret_scope_02` as four mirrored quads each, with black beside them on a wide frame
 *   (`./reticle` `scopeLayout`); only the F2000 (63) skips `ret_scope_02` (`ChangeReticule`, research 84 §9).
 * - **The thermal scope** (item 195, equipment with no model): the kit holding it (`FUN_005c86f0`) swaps a sniper's
 *   (class 101-120) `scope` node for its `thermal_scope` (`FUN_005b82e0` L471451-471530: the node names 0x65f818 /
 *   0x65f820) and makes every scoped view (states 5-12) play `to_thermal_lens_fx` in place of the scope's lens
 *   (`FUN_001f0750` L53084-53160); the zoom is unchanged.
 */

/** The scope's magnifications of a record, state 5 up: `ZoomMode1..` (empty: no scope; the zoom goes to the 9x view). */
export function scopeLevels(record: Pick<WeaponRecord, 'zoomModes'>): number[] {
  return record.zoomModes.slice(1);
}

/** `ret_scope_01` and `ret_scope_02`, set 5's two bitmaps (`BitmapReticule_Init` 0x2178c0). */
export const SCOPE_BITMAPS: readonly string[] = ['ret_scope_01.tif', 'ret_scope_02.tif'];

/** The scope's bitmaps for a weapon: both, but the F2000's tube alone (`ChangeReticule` type 5, research 84 §9). */
export function scopeBitmaps(weaponId: number): string[] {
  return (weaponId & 0xff) === ITEM.F2000 ? [SCOPE_BITMAPS[0]!] : [...SCOPE_BITMAPS];
}

/** The model's node the thermal scope shows (0x65f820); the plain one is `scope` (0x65f818). */
export const THERMAL_SCOPE_NODE = 'thermal_scope';
export const SCOPE_NODE = 'scope';

/** The kit holds the thermal scope (`FUN_005c86f0` with 0xc3: any kit slot). */
export function thermalFitted(loadout: readonly number[]): boolean {
  return loadout.includes(ITEM.THERMAL);
}

/**
 * Whether a held model's node `node` shows (`FUN_005b82e0`): with the thermal scope in the kit and a sniper in the
 * hand, `scope` hidden and `thermal_scope` shown; otherwise the reverse. Null for any other node (left as it is).
 */
export function scopeNodeVisible(node: string, loadout: readonly number[], weaponId: number): boolean | null {
  if (node !== SCOPE_NODE && node !== THERMAL_SCOPE_NODE) return null;
  const thermal = thermalFitted(loadout) && itemClass(weaponId & 0xff) === 'sniper';
  return node === THERMAL_SCOPE_NODE ? thermal : !thermal;
}

/** `scopeNodeVisible` on a held model's meshes (each carries its node's name in `userData.node`, `./world` `held`). */
export function showScopeNodes(object: Object3D, loadout: readonly number[], weaponId: number): void {
  object.traverse((o) => {
    const node = o.userData?.node;
    if (typeof node !== 'string') return;
    const v = scopeNodeVisible(node, loadout, weaponId);
    if (v !== null) o.visible = v;
  });
}

/** The scope node a held model shows (`scope` or `thermal_scope`), or null when it has neither (the page's stats). */
export function shownScopeNode(object: Object3D | null): string | null {
  let shown: string | null = null;
  object?.traverse((o) => {
    const node = o.userData?.node;
    if (o.visible && (node === SCOPE_NODE || node === THERMAL_SCOPE_NODE)) shown = node;
  });
  return shown;
}

/** The thermal scope's lens zAnim (0x3e28b0, loaded by name at L52689). */
export const THERMAL_LENS = 'to_thermal_lens_fx';
export type ScopeLens = 'to_thermal_lens_fx' | 'to_starlight_scope_lens_fx' | 'to_scope_lens_fx';

/**
 * The lens a view state plays (`FUN_001f0750` L53084-53160, states 5-12): `to_thermal_lens_fx` (lens mode 2) when
 * the kit holds the thermal scope (`FUN_005433c0(body, 0)`), else `to_starlight_scope_lens_fx` (mode 4) on a night
 * map, else `to_scope_lens_fx` (mode 5); null below the scope (the 9x view and the goggles have their own).
 */
export function scopeLens(zoomState: number, thermal: boolean, night: boolean): ScopeLens | null {
  if (zoomState < 5 || zoomState > 12) return null;
  if (thermal) return THERMAL_LENS;
  return night ? 'to_starlight_scope_lens_fx' : 'to_scope_lens_fx';
}
