import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Zar, parseRdr, type RdrNode } from '@s2u/archive';
import {
  BACKBLAST_CONE, CLAYMORE, CLAYMORE_CONE, claymoreCone, holdsFuse, inCone, launchGrenade, proximityTripped, stepGrenade,
  throwableRecord, type HullCast, type ThrowableRecord, type V3,
} from '../src/projectile';
import { ITEM, kitTableOf, readKitTable } from '../src/arsenal';

/**
 * The equipment to the grenade's standard (web sprint 4, M7; research 94 §C4, §C5, R94.6/R94.9/R94.11): every placed
 * charge's and rocket's numbers read off its record at run time -- the timers, the radii, the damage, the arming, the
 * acceleration, the proximity, the cost -- and the rules the flight applies to them (the claymore's and the PMN's held
 * fuse, the PMN's arming and trip, C4's timer, the backblast's cone).
 */

const rec = (...pairs: [string, RdrNode][]): RdrNode[] => pairs.flatMap(([k, v]) => [k, Array.isArray(v) ? v : [v]]);
/** A `ZWEAPON` record in `parseRdr`'s shape with every key `throwableRecord` asks for. */
const weapon = (name: string, id: number, ammo: string, extra: [string, RdrNode][] = []): RdrNode[] => rec(
  ...extra, ['InternalName', name], ['ID', String(id)], ['Muzzle_Velocity', '0'], ['ImpactRadius', '40'], ['Effective_Range', '0'],
  ['Maximum_Range', '0'], ['Ammo_Capacity', '4'], ['NumMags', '1'], ['Sound_Radius', '800'], ['ModelName', name.toLowerCase()],
  ['FireAnimName', 'c4_start'], ['HitAnimName', 'NOT FOUND'], ['DefaultSpecialAnimName', 'x'], ['SpecialMaterialAnimName', 'NOT FOUND'],
  ['DecalSet', 'BULLET_MARK_SMALL'], ['IconTextureName', `${name}.tif`], ['AMMO_TYPES', [rec(['NAME', ammo])]],
);  // the extras first: `rdrGet` answers a key's first value
const ammo = (name: string, id: number, damage: string, radius: string, extra: [string, RdrNode][] = []): RdrNode[] =>
  rec(['InternalName', name], ['ID', String(id)], ['Piercing', '0'], ['Explosion_Damage', damage], ['Explosion_Radius', radius], ...extra);
const synthetic: RdrNode = [
  'ZAMMO', [ammo('PMN Ammo', 44, '6.5', '4', [['ProximityDistance', '1']]), ammo('C4 Ammo', 18, '18', '5'), ammo('Backblast Ammo', 46, '6', '7'),
    ammo('LAW HEAT Ammo', 39, '20', '15', [['AccelerationFactor', '98']])],
  'ZWEAPON', [
    weapon('PMN Mine', 158, 'PMN Ammo', [['Timer1', '8'], ['Timer2', '10']]),
    weapon('C4', 151, 'C4 Ammo', [['Timer1', '6'], ['Timer2', '0.1']]),
    weapon('Backblast', 159, 'Backblast Ammo', [['Timer1', '0'], ['Timer2', '0.1']]),
    weapon('LAW', 145, '', [['SlotCost', '2']]),
    weapon('LAW HEAT', 185, 'LAW HEAT Ammo', [['Timer1', '20'], ['Timer2', '20.1'], ['Muzzle_Velocity', '20'], ['ArmingDistance', '10'], ['HasBackblast', []], ['FireWait', '3']]),
  ],
];

/** What each item's record must say (research 94 §C4.1, §C5, §C11): units x10, seconds as written. */
type Row = [string, Partial<ThrowableRecord>];
const ROWS: Row[] = [
  ['Claymore', { id: 153, fuse: 9999999, removal: 10, explosionDamage: 16, explosionRadius: 250, muzzleVelocity: 0, capacity: 4, impact: false }],
  ['PMN Mine', { id: 158, fuse: 8, removal: 10, explosionDamage: 6.5, explosionRadius: 40, proximity: 10, muzzleVelocity: 0, capacity: 4, impact: false }],
  ['C4', { id: 151, fuse: 6, removal: 0.1, explosionDamage: 18, explosionRadius: 50, muzzleVelocity: 0, capacity: 4, impact: false }],
  ['LAW HEAT', { id: 185, fuse: 20, removal: 20.1, explosionDamage: 20, explosionRadius: 150, armingDistance: 100, acceleration: 980, hasBackblast: true, muzzleVelocity: 200, capacity: 1, impact: true }],
  ['RPG', { id: 186, fuse: 20, removal: 20.1, explosionDamage: 20, explosionRadius: 150, armingDistance: 100, acceleration: 980, hasBackblast: true, muzzleVelocity: 400, capacity: 1, impact: true }],
  ['Backblast', { id: 159, fuse: 0, removal: 0.1, explosionDamage: 6, explosionRadius: 70, muzzleVelocity: 0 }],
];

describe('the equipment\'s records, a hand-built zweapon.rdr (the synthetic twin)', () => {
  it('reads the PMN\'s ProximityDistance x10 off its round, and none elsewhere', () => {
    expect(throwableRecord(synthetic, 'PMN Mine')).toMatchObject({ id: 158, fuse: 8, proximity: 10, explosionRadius: 40 });
    expect(throwableRecord(synthetic, 'C4').proximity).toBeUndefined();
    expect(throwableRecord(synthetic, 'LAW HEAT')).toMatchObject({ acceleration: 980, armingDistance: 100, hasBackblast: true, muzzleVelocity: 200 });
  });

  it('the kit table carries every throwable and charge with its round\'s piercing (grenades, explosives, the Backblast)', () => {
    const table = kitTableOf(synthetic);
    expect([...(table.throwables?.keys() ?? [])].sort()).toEqual([151, 158, 159]);
    expect(table.throwables?.get(ITEM.PMN)?.record.proximity).toBe(10);
    expect(table.rounds.get(ITEM.LAW_HEAT)?.fireWait).toBe(3);
    expect(table.arsenal.items.get(ITEM.LAW)?.slotCost).toBe(2);
  });
});

describe('the charges in flight: the held fuse, the PMN\'s arming and trip, the C4\'s timer (research 94 §C5)', () => {
  const pmn = throwableRecord(synthetic, 'PMN Mine'), c4 = throwableRecord(synthetic, 'C4');
  const none: HullCast = () => [];
  const placed = (r: ThrowableRecord): ReturnType<typeof launchGrenade> => {
    const g = launchGrenade([0, 0, 0], [0, 0, 0], r);
    g.state = 'rest';
    return g;
  };

  it.each([
    // the charge, whether its Timer1 is held (`+0xc5` claymore / `+0xc6` proximity: the tick 0x3c5310, L316893-316905)
    ['the claymore (remote, type 0x99)', CLAYMORE, true],
    ['the PMN (a proximity)', pmn, true],
    ['the C4 (timed)', c4, false],
  ] as const)('%s: held %s', (_what, r, held) => {
    expect(holdsFuse(r)).toBe(held);
  });

  it('the PMN does not go off at its Timer1: it arms, then an actor inside ProximityDistance trips it (FUN_00543930)', () => {
    const g = placed(pmn);
    const at: V3 = [0, 0, 0], near: V3 = [9, 0, 0], far: V3 = [11, 0, 0];
    for (let i = 0; i < 7.9 * 60; i++) stepGrenade(g, 1 / 60, none);
    expect(proximityTripped(g, [near])).toBe(false);                     // not armed before 8 s
    for (let i = 0; i < 0.2 * 60; i++) expect(stepGrenade(g, 1 / 60, none)).toEqual([]);
    expect(g.state).toBe('rest');                                        // armed, not gone off
    expect(proximityTripped(g, [far])).toBe(false);                      // 1 m = 10 u: 11 u is outside
    expect(proximityTripped(g, [at, near])).toBe(true);
    expect(stepGrenade(g, 1 / 60, none).map((e) => e.kind)).toEqual(['explode']);
  });

  it('the C4 goes off at its Timer1, 6 s from placing; a claymore only on its trigger', () => {
    const g = placed(c4);
    let t = 0;
    while (g.state === 'rest' && t < 10) { stepGrenade(g, 1 / 60, none); t += 1 / 60; }   // gone off (and removed: Timer2 0.1)
    expect(t).toBeCloseTo(6, 1);
    const cl = placed(CLAYMORE);
    for (let i = 0; i < 60; i++) stepGrenade(cl, 1, none);
    expect(cl.state).toBe('rest');
    cl.trigger = true;                                                   // `+0xc4` (FUN_003c5730): the next tick
    expect(stepGrenade(cl, 1 / 60, none).map((e) => e.kind)[0]).toBe('explode');
  });
});

describe('the cones (FUN_003c7280 from GetDamage 0x3c7600): the claymore\'s and the backblast\'s', () => {
  it.each([
    // rel, axis, half-angle, radius, inside
    ['straight down the axis', [30, 0, 0], [1, 0, 0], BACKBLAST_CONE, 70, true],
    ['40 degrees off', [30 * Math.cos(0.698), 30 * Math.sin(0.698), 0], [1, 0, 0], BACKBLAST_CONE, 70, true],
    ['50 degrees off', [30 * Math.cos(0.873), 30 * Math.sin(0.873), 0], [1, 0, 0], BACKBLAST_CONE, 70, false],
    ['behind the axis', [-30, 0, 0], [1, 0, 0], BACKBLAST_CONE, 70, false],
    ['past the radius', [71, 0, 0], [1, 0, 0], BACKBLAST_CONE, 70, false],
    ['the claymore\'s 84 degrees', [30, 250 * 0, 200], [1, 0, 0], CLAYMORE_CONE, 250, true],
  ] as const)('%s', (_what, rel, axis, half, radius, inside) => {
    expect(inCone(rel as unknown as V3, axis as unknown as V3, half, radius)).toBe(inside);
  });

  it('0x3f490fdb is pi/4 and claymoreCone is the cone at 0x3fbc7edd', () => {
    expect(BACKBLAST_CONE).toBeCloseTo(Math.PI / 4, 6);
    expect(claymoreCone([30, 0, 200], [1, 0, 0])).toBe(inCone([30, 0, 200], [1, 0, 0], CLAYMORE_CONE, CLAYMORE.explosionRadius));
  });
});

// The disc: the served copies (tools/extract-maps.ts), else SOCOM_DISC (as `arsenal.test.ts`).
const web = resolve(import.meta.dirname, '../../..');
const onDisc = (name: string): string | undefined => [
  resolve(web, `public/maps/RUN/${name}`),
  ...(process.env.SOCOM_DISC ? [resolve(process.env.SOCOM_DISC, `RUN/${name}`)] : []),
].find((p) => existsSync(p));
const ZWEAPON = onDisc('ZWEAPON.ZAR');

describe.skipIf(!ZWEAPON)('the equipment off zweapon.rdr (research 94 §C11): table-driven over the disc\'s records', () => {
  const script = (): RdrNode => {
    const zar = Zar.parse(new Uint8Array(readFileSync(ZWEAPON!)));
    return parseRdr(zar.data(zar.root.children.find((k) => k.name.toLowerCase() === 'zweapon.rdr')!));
  };

  it.each(ROWS)('%s', (name, want) => {
    const r = throwableRecord(script(), name);
    expect(r).toMatchObject(want);
    if (!('proximity' in want)) expect(r.proximity).toBeUndefined();
    if (!('acceleration' in want)) expect(r.acceleration).toBeUndefined();
  });

  it.each([
    // item, SlotCost (`+0x27c`, default 1; research 94 §A5.4)
    ['LAW', 2], ['RPG LAUNCHER', 2], ['C4', 1], ['Claymore', 1], ['PMN Mine', 1], ['Detonator', 1], ['Thermal Scope', 1], ['Double Ammo Load', 1],
  ] as const)('%s: SlotCost %d', (name, cost) => {
    const table = readKitTable(new Uint8Array(readFileSync(ZWEAPON!)));
    expect(table.arsenal.byName.get(name)?.slotCost).toBe(cost);
  });

  it('the kit table holds the charges, the throwables and the Backblast; the rockets as rounds', () => {
    const table = readKitTable(new Uint8Array(readFileSync(ZWEAPON!)));
    for (const id of [121, 122, 123, 126, 151, 153, 158, 159]) expect(table.throwables?.has(id), String(id)).toBe(true);
    expect(table.rounds.get(185)).toMatchObject({ fireWait: 3, reloadAfterShot: true, reloadDelayAfterShot: 1 });
    expect(table.rounds.get(186)).toMatchObject({ fireWait: 3, reloadAfterShot: true, reloadDelayAfterShot: 1 });
  });
});
