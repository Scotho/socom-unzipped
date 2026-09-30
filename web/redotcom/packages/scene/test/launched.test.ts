import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Zar, parseRdr, type RdrNode } from '@s2u/archive';
import {
  DUD_SPEED, LOFT, M67, backblastLaunch, launchGrenade, loftAim, stepGrenade, throwableRecord,
  type HullCast, type ThrowableRecord, type V3,
} from '../src/projectile';

/**
 * The launched rounds (web sprint 4, M7; research 94 §C4): the rockets' acceleration without a fall, the arming
 * distance's dud, the grenade launcher's loft onto the aimed point, the backblast.
 */

const round = (over: Partial<ThrowableRecord>): ThrowableRecord => ({ ...M67, impact: true, fuse: 10, removal: 10.1, muzzleVelocity: 1, ...over });
const floor = (y: number): HullCast => (a, b) => {
  if ((a[1] - y) * (b[1] - y) > 0) return [];
  const t = (a[1] - y) / (a[1] - b[1]);
  return [{ point: [a[0] + (b[0] - a[0]) * t, y, a[2] + (b[2] - a[2]) * t], normal: [0, 1, 0], t,
    material: { name: 'STONE', opacity: 1, penetration: 0, ricochet: 0, elasticity: 0.5, impactRadiusMod: 1, volumetric: false, liquid: false, underwater: false } }];
};
const wall = (x: number): HullCast => (a, b) => {
  if ((a[0] - x) * (b[0] - x) > 0) return [];
  const t = (a[0] - x) / (a[0] - b[0]);
  return [{ point: [x, a[1] + (b[1] - a[1]) * t, a[2]], normal: [-1, 0, 0], t,
    material: { name: 'STONE', opacity: 1, penetration: 0, ricochet: 0, elasticity: 0.5, impactRadiusMod: 1, volumetric: false, liquid: false, underwater: false } }];
};

describe('launched rounds', () => {
  it('a rocket accelerates along its velocity and does not fall (FUN_003ca5a0)', () => {
    const r = launchGrenade([0, 100, 0], [200, 0, 0], round({ acceleration: 980 }));
    for (let i = 0; i < 60; i++) stepGrenade(r, 1 / 60, () => []);
    expect(r.vel[1]).toBe(0);
    expect(r.pos[1]).toBe(100);
    expect(r.vel[0]).toBeCloseTo(200 + 980, 6);
  });

  it('a launcher round falls at 98 u/s^2', () => {
    const r = launchGrenade([0, 100, 0], [270, 0, 0], round({}));
    for (let i = 0; i < 60; i++) stepGrenade(r, 1 / 60, () => []);
    expect(r.vel[1]).toBeCloseTo(-98, 6);
  });

  it('inside the arming distance it is a dud: half its speed, no fuse, a bounce (FUN_003c8920)', () => {
    const r = launchGrenade([0, 10, 0], [270, 0, 0], round({ armingDistance: 100 }));
    const events = stepGrenade(r, 0.2, wall(50));
    expect(events.map((e) => e.kind)).toEqual(['dud', 'bounce']);
    expect(r.dud).toBe(true);
    expect(r.fuse).toBeGreaterThan(1e6);
    expect(Math.abs(r.vel[0])).toBeLessThan(270 * DUD_SPEED);
    expect(r.state).toBe('flight');
  });

  it('past the arming distance it goes off where it hits', () => {
    const r = launchGrenade([0, 10, 0], [270, 0, 0], round({ armingDistance: 100 }));
    const events = stepGrenade(r, 1, wall(150));
    expect(events.map((e) => e.kind)).toEqual(['explode']);
    expect(r.pos[0]).toBeCloseTo(150, 6);
  });

  it('the loft raises the aim in 0.025 steps until the arc passes the aimed point (FUN_005bf8a0)', () => {
    const muzzle: V3 = [0, 0, 0], target: V3 = [400, 0, 0];
    const dir = loftAim([1, 0, 0], 270, muzzle, target);
    expect(Math.hypot(...dir)).toBeCloseTo(1, 6);
    expect(dir[1]).toBeGreaterThan(0);
    // The arc with that aim clears or meets the target within the band.
    const h = Math.hypot(dir[0], dir[2]) * 270, t = 400 / h;
    expect(t * 270 * dir[1] - LOFT.gravity * t * t / 2).toBeGreaterThanOrEqual(-LOFT.band);
    // At most 12 steps; the first always taken.
    const far = loftAim([1, 0, 0], 270, muzzle, [5000, 0, 0]);
    expect(far[1]).toBeCloseTo(LOFT.step * LOFT.steps, 6);
    expect(loftAim([1, 0, 0], 270, muzzle, [10, -50, 0])[1]).toBeCloseTo(LOFT.step, 6);
  });

  it('the backblast leaves the muzzle backwards', () => {
    expect(backblastLaunch([1, 2, 3], [0, 0, 1])).toEqual({ pos: [1, 2, 3], dir: [-0, -0, -1] });
  });

  it('a hand grenade has none of it: no arming, no acceleration', () => {
    expect(M67.armingDistance).toBeUndefined();
    const g = launchGrenade([0, 10, 0], [0, 0, 0]);
    stepGrenade(g, 1 / 60, floor(-100));
    expect(g.dud).toBe(false);
  });
});

const web = resolve(import.meta.dirname, '../../..');
const ZWEAPON = [resolve(web, 'public/maps/RUN/ZWEAPON.ZAR'), ...(process.env.SOCOM_DISC ? [resolve(process.env.SOCOM_DISC, 'RUN/ZWEAPON.ZAR')] : [])]
  .find((p) => existsSync(p));

describe.skipIf(!ZWEAPON)('the launched rounds off zweapon.rdr', () => {
  const script = (): RdrNode => {
    const zar = Zar.parse(new Uint8Array(readFileSync(ZWEAPON as string)));
    return parseRdr(zar.data(zar.root.children[0] as NonNullable<(typeof zar.root.children)[0]>));
  };

  it('LAW HEAT and the RPG round: 980 u/s^2, armed at 100 u, a backblast, going off on impact', () => {
    for (const name of ['LAW HEAT', 'RPG']) {
      const r = throwableRecord(script(), name);
      expect(r).toMatchObject({ acceleration: 980, armingDistance: 100, hasBackblast: true, impact: true });
    }
  });

  it('the 40 mm rounds: armed at 100 u, falling at 98, no acceleration; the smoke rounds bounce', () => {
    const frag = throwableRecord(script(), 'M203 FRAG');
    expect(frag).toMatchObject({ armingDistance: 100, gravity: 98, impact: true, muzzleVelocity: 270 });
    expect(frag.acceleration).toBeUndefined();
    expect(throwableRecord(script(), 'M203 SMOKE').impact).toBe(false);
    expect(throwableRecord(script(), 'M67')).toEqual(M67);
  });
});
