import { describe, expect, it } from 'vitest';
import { CLAYMORE, EMPTY_ITEM, HE, ITEM, M67, type KitTable, type Loadout, type ThrowableRecord, type V3 } from '@s2u/scene';
import {
  ACTION_RANGE_DEFAULT, EQUIPMENT_SLOTS, backblastReaches, c4Plant, c4Targets, equipmentKind, pouchOf, rocketLaunch, rocketRoundOf,
  slotSelectable, throwableOf,
} from '../src/equipment';
import type { MapAction } from '../src/mapActions';

/**
 * The equipment's shared rules (web sprint 4, M7; `../src/equipment`): the slots, `FUN_005bdc30`'s gate, the pouch the
 * loadout carries, C4's targets and plant, the rockets' launch and the backblast's cone.
 */

const kit = (...ids: number[]): Loadout => ids as unknown as Loadout;
const ctx = (over: Partial<{ chargesDown: number; rounds: number }> = {}) => ({
  chargesDown: over.chargesDown ?? 0, roundsFor: () => over.rounds ?? 0,
});

describe('the equipment slots (W4.R5) and FUN_005bdc30\'s gate', () => {
  it('are the kit\'s slots 2-4, in kit order', () => {
    expect([...EQUIPMENT_SLOTS]).toEqual([2, 3, 4]);
  });

  it.each([
    // item, its kind, selectable with nothing down / no rounds, and with a charge down and a round held
    ['M67', 121, 'throwable', true, true],
    ['AN-M8', 122, 'throwable', true, true],
    ['Claymore', 153, 'placed', true, true],
    ['PMN Mine', 158, 'placed', true, true],
    ['C4 (planted by Action)', 151, 'c4', false, false],
    ['LAW', 145, 'launcher', false, true],
    ['RPG-7', 146, 'launcher', false, true],
    ['LAW HEAT (a round)', 185, 'round', false, false],
    ['M203 FRAG (a round)', 175, 'round', false, false],
    ['Detonator', 193, 'detonator', false, true],
    ['2X (0xc2)', 194, 'gear', false, false],
    ['thermal scope (0xc3)', 195, 'gear', false, false],
    ['an empty slot', EMPTY_ITEM, 'none', false, false],
  ] as const)('%s', (_what, id, kind, bare, armed) => {
    expect(equipmentKind(id)).toBe(kind);
    expect(slotSelectable(id, ctx())).toBe(bare);
    expect(slotSelectable(id, ctx({ chargesDown: 1, rounds: 1 }))).toBe(armed);
  });

  it('the rockets\' rounds: the LAW its LAW HEAT, the RPG-7 its RPG', () => {
    expect([rocketRoundOf(ITEM.LAW), rocketRoundOf(ITEM.RPG7), rocketRoundOf(ITEM.M79)]).toEqual([ITEM.LAW_HEAT, ITEM.RPG_ROUND, null]);
  });
});

describe('the pouch follows the loadout (retires POUCH_PLACEHOLDER)', () => {
  const pmn: ThrowableRecord = { ...CLAYMORE, name: 'PMN Mine', id: 158, fuse: 8, proximity: 10 };
  const table = { throwables: new Map([[158, { record: pmn, piercing: 0 }]]) } as unknown as KitTable;

  it.each([
    ['mp_seal1: M67, HE, 2X', kit(54, 15, 121, 126, 194), null, { M67: 3, HE: 3 }],
    ['two M67 slots: six', kit(54, 15, 121, 121, 255), null, { M67: 6 }],
    ['the claymore\'s four', kit(106, 15, 121, 153, 255), null, { M67: 3, Claymore: 4 }],
    ['a PMN off the kit table', kit(81, 7, 121, 122, 158), table, { M67: 3, 'AN-M8': 3, 'PMN Mine': 4 }],
    ['a LAW and its round carry no pouch', kit(54, 15, 145, 185, 121), null, { M67: 3 }],
  ] as const)('%s', (_what, loadout, t, want) => {
    expect(pouchOf(loadout, t)).toEqual(want);
  });

  it('a record is the kit table\'s, else the baked one', () => {
    expect(throwableOf(null, 121)).toBe(M67);
    expect(throwableOf(null, 126)).toBe(HE);
    expect(throwableOf(table, 158)).toBe(pmn);
    expect(throwableOf(null, 158)).toBeNull();
  });
});

describe('C4 (research 94 §C5.1): a timed charge planted at a target the SEAL stands at, still', () => {
  const action = (node: string, type: string, at: V3, range = 0): MapAction => ({ node, type, range, bitmap: '', at });
  const actions = [
    action('door_ft1', 'DOOR', [0, 0, 0], 30), action('terrorist_tent', 'MPBOMB', [0, 0, 0], 15),
    action('access_action1', '', [100, 0, 0]), action('rtower_action', '', [500, 0, 0], 20),
  ];

  it('the targets are actions.rdr\'s type-less actions (C4_TARGET_READING), at the default reach 32 (FUN_002b49f0)', () => {
    expect(c4Targets(actions)).toEqual([
      { node: 'access_action1', at: [100, 0, 0], range: ACTION_RANGE_DEFAULT },
      { node: 'rtower_action', at: [500, 0, 0], range: 20 },
    ]);
    expect(ACTION_RANGE_DEFAULT).toBe(32);
  });

  it.each([
    ['at the target, still', [110, 0, 0], 0, 'access_action1'],
    ['away from any target: refused', [200, 0, 0], 0, null],
    ['at the door (no C4 target): refused', [0, 0, 0], 0, null],
    ['at the target, moving: refused', [110, 0, 0], 20, null],
  ] as const)('%s', (_what, feet, speed, want) => {
    expect(c4Plant(c4Targets(actions), feet, speed)?.node ?? null).toBe(want);
  });
});

describe('the rockets (research 94 §C4.3-§C4.4)', () => {
  const heat: ThrowableRecord = { ...M67, name: 'LAW HEAT', id: 185, muzzleVelocity: 200, acceleration: 980, armingDistance: 100, impact: true, hasBackblast: true, explosionRadius: 150 };

  it('leave straight at the aimed point at the round\'s Muzzle_Velocity (no loft), the backblast backwards from the muzzle', () => {
    const out = rocketLaunch(heat, [0, 20, 0], [1000, 20, 0]);
    expect(out.dir).toEqual([1, 0, 0]);
    expect(out.velocity).toEqual([200, 0, 0]);
    expect(out.backblast).toEqual({ pos: [0, 20, 0], dir: [-1, -0, -0] });
  });

  it.each([
    ['behind the shooter, 3 m', [-30, 20, 0], true],
    ['behind, 20 degrees off', [-30, 20 + 30 * Math.tan(0.35), 0], true],
    ['beside the shooter (90 degrees)', [0, 20, 30], false],
    ['in front of the shooter', [30, 20, 0], false],
    ['behind past 7 m', [-71, 20, 0], false],
  ] as const)('the backblast\'s cone (6 in 7 m, 45 degrees): %s', (_what, point, reaches) => {
    const { backblast } = rocketLaunch(heat, [0, 20, 0], [1000, 20, 0]);
    expect(backblastReaches(backblast.pos, backblast.dir, point, 70)).toBe(reaches);
  });
});
