import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';
// `src/hook.ts` is types only; its `declare global` is what makes `window.__viewer` exist inside `page.evaluate`.
import type {} from '../src/hook';

/**
 * The equipment on Frostfire (web sprint 4 M7; spec W4.R5; research 94 §C4-§C5, research 85 §9.7), one family a test,
 * each with its own developer kit (`&kit=`, devmode): the LAW (AT-4) raised from its slot and fired down the open dock
 * -- the rocket straight, accelerating, gone off where it lands, the backblast behind; the claymore placed and set off
 * by its Detonator; the PMN placed, stood on while unarmed, and set off by the SEAL on it once its 8 s have run.
 */

const SCREENS = fileURLToPath(new URL('../../../test-fixtures/screens/equipment', import.meta.url));
const SPAWN_A: [number, number, number] = [796, 100, 614];
const EYE = 15.4;
const REST_PITCH = -9.167;

const settle = (page: Page): Promise<void> => page.evaluate(
  () => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))),
);

async function open(page: Page, kit: string, problems: string[]): Promise<void> {
  mkdirSync(SCREENS, { recursive: true });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  await page.goto(`/?mode=play&fly&devmode&kit=${kit}`);
  const status = page.locator('#status');
  await expect(status).toContainText('triangles');
  await page.locator('#maps').selectOption('RUN/MP2.ZDB');
  await expect(status).toContainText('FROSTFIRE (MP2)');
  await expect(status).toContainText('triangles');
  expect((await page.evaluate(() => window.__viewer.stats())).diagnostics).toEqual([]);
}

/** Walking at `at` (spawn A unless told), facing `yaw`, the aim at `pitch`. */
async function stand(page: Page, yaw: number, pitch: number, at: readonly number[] = SPAWN_A): Promise<void> {
  expect(await page.evaluate(() => window.__viewer.setMode('walk'))).toBe(true);
  await page.evaluate(([x, y, z, eye, yaw, pitch]) => window.__viewer.setCamera({ x, y: y + eye, z, yaw, pitch }), [at[0]!, at[1]!, at[2]!, EYE, yaw, pitch] as const);
  await page.evaluate(() => window.__viewer.walkFor(0.3, { forward: 0 }));
}

const pull = (page: Page): Promise<void> => page.evaluate(() => { window.__viewer.trigger(true); window.__viewer.trigger(false); });

test('the LAW: raised from its slot, the rocket flies straight and goes off down the dock, the backblast behind', async ({ page }) => {
  const problems: string[] = [];
  await open(page, '62,15,145,185,121', problems);           // M4A1 SD, Mark 23, LAW, LAW HEAT, M67
  await stand(page, 240, 2);
  await page.waitForTimeout(1000);
  const kit = await page.evaluate(() => window.__viewer.equipment());
  expect(kit.slots.map((s) => s.name)).toEqual(['LAW', 'LAW HEAT', 'M67']);
  expect(await page.evaluate(() => window.__viewer.selectEquipment(2))).toBe(false);   // the round: a fire mode, never taken up
  expect(await page.evaluate(() => window.__viewer.selectEquipment(1))).toBe(true);
  await settle(page);
  const up = await page.evaluate(() => window.__viewer.equipment());
  expect(up).toMatchObject({ held: 'LAW', icon: 'at4_icon.tif', count: 1, roundIcon: 'firemode_at4.tif' });
  expect((await page.evaluate(() => window.__viewer.hud())).model).toMatchObject({ weaponIcon: 'at4_icon.tif', fireModeIcon: 'firemode_at4.tif', rounds: 1 });

  await pull(page);
  await expect.poll(() => page.evaluate(() => window.__viewer.equipment().rocket.launched)).toBe(1);
  const fired = (await page.evaluate(() => window.__viewer.equipment())).rocket;
  const v = fired.lastLaunch!.velocity, speed = Math.hypot(...v);
  expect(speed).toBeCloseTo(200, 3);                          // the LAW HEAT's Muzzle_Velocity (ROCKET_LAUNCH_SPEED_READING)
  expect(fired.backblasts).toBe(1);
  const back = fired.lastBackblast!;
  expect(back.pos).toEqual(fired.lastLaunch!.from);           // from the muzzle (BACKBLAST_ORIGIN_READING) ...
  for (let i = 0; i < 3; i++) expect(back.dir[i]!).toBeCloseTo(-v[i]! / speed, 6);   // ... backwards
  expect(fired.rounds).toBe(0);                               // the LAW HEAT's one shot

  // In flight: the direction held (no fall), the speed rising at 980 u/s^2.
  const flying = async (): Promise<{ pos: number[]; vel: number[] } | null> =>
    (await page.evaluate(() => window.__viewer.grenade().live.find((l) => l.state === 'flight') ?? null));
  const a = await flying();
  await page.waitForTimeout(100);
  const b = await flying();
  if (a && b) {
    const sa = Math.hypot(...a.vel), sb = Math.hypot(...b.vel);
    expect(sb).toBeGreaterThanOrEqual(sa);
    for (let i = 0; i < 3; i++) expect(b.vel[i]! / sb).toBeCloseTo(a.vel[i]! / sa, 3);
  }
  await expect.poll(() => page.evaluate(() => window.__viewer.grenade().explosions.length), { timeout: 15_000 }).toBe(1);
  const boom = (await page.evaluate(() => window.__viewer.grenade())).explosions[0]!;
  expect(boom).toMatchObject({ item: 'LAW HEAT', detonation: 'blast', radius: 150 });
  expect(Math.hypot(boom.pos[0] - SPAWN_A[0], boom.pos[2] - SPAWN_A[2])).toBeGreaterThan(100);   // past its 10 m arming
  await page.locator('#view').screenshot({ path: join(SCREENS, 'frostfire-law-blast.png') });
  await page.waitForTimeout(3500);
  await pull(page);
  expect((await page.evaluate(() => window.__viewer.equipment())).rocket.launched).toBe(1);   // none left
  expect(problems).toEqual([]);
});

test('the claymore: placed from its slot, the Detonator up, set off only by the Detonator', async ({ page }) => {
  const problems: string[] = [];
  await open(page, '62,15,121,153,255', problems);           // M4A1 SD, Mark 23, M67, Claymore, empty
  await stand(page, 90, REST_PITCH);
  await page.waitForTimeout(1000);
  expect(await page.evaluate(() => window.__viewer.selectEquipment(3))).toBe(false);   // the empty slot
  expect(await page.evaluate(() => window.__viewer.selectEquipment(2))).toBe(true);
  expect(await page.evaluate(() => window.__viewer.selectItem('Detonator'))).toBe(false);   // none down yet
  await pull(page);
  await expect.poll(() => page.evaluate(() => window.__viewer.grenade().leftByItem.Claymore), { timeout: 5_000 }).toBe(3);
  const set = await page.evaluate(() => window.__viewer.grenade());
  expect(set).toMatchObject({ held: 'Detonator', placed: 1 });
  await expect.poll(() => page.evaluate(() => window.__viewer.hud().model.weaponIcon)).toBe('detonator_icon.tif');
  await expect.poll(() => page.evaluate(() => window.__viewer.grenade().phase), { timeout: 5_000 }).toBe('ready');
  await page.waitForTimeout(2000);
  expect((await page.evaluate(() => window.__viewer.grenade())).explosions).toHaveLength(0);   // no fuse: it waits
  await pull(page);                                          // the Detonator (CZKit_DetonateRemoteExplosives)
  await expect.poll(() => page.evaluate(() => window.__viewer.grenade().explosions.length), { timeout: 3_000 }).toBe(1);
  expect((await page.evaluate(() => window.__viewer.grenade())).explosions[0]).toMatchObject({ item: 'Claymore', radius: 250 });
  expect((await page.evaluate(() => window.__viewer.grenade())).held).toBe('Claymore');   // the claymore back up
  await page.locator('#view').screenshot({ path: join(SCREENS, 'frostfire-claymore-detonated.png') });
  expect(problems).toEqual([]);
});

test('the PMN: placed from its slot, harmless for its 8 s, then the SEAL standing on it sets it off', async ({ page }) => {
  const problems: string[] = [];
  await open(page, '62,15,121,158,194', problems);           // M4A1 SD, Mark 23, M67, PMN Mine, 2X
  await stand(page, 90, REST_PITCH);
  await page.waitForTimeout(1000);
  expect(await page.evaluate(() => window.__viewer.selectEquipment(3))).toBe(false);   // 2X holds nothing in the hand
  expect(await page.evaluate(() => window.__viewer.equipment().held)).toBeNull();
  expect(await page.evaluate(() => window.__viewer.selectEquipment(2))).toBe(true);
  expect(await page.evaluate(() => window.__viewer.equipment().held)).toBe('PMN Mine');
  await pull(page);
  await expect.poll(() => page.evaluate(() => window.__viewer.grenade().leftByItem['PMN Mine']), { timeout: 5_000 }).toBe(3);
  const down = await page.evaluate(() => window.__viewer.grenade());
  expect(down.held).toBe('PMN Mine');                          // no Detonator after a PMN
  const mine = down.live.find((l) => l.state === 'rest')!.pos;
  await expect.poll(() => page.evaluate(() => window.__viewer.grenade().phase), { timeout: 5_000 }).toBe('ready');
  await stand(page, 90, REST_PITCH, [mine[0]!, mine[1]!, mine[2]!]);   // onto it, before its Timer1 has run
  await page.waitForTimeout(2500);
  expect((await page.evaluate(() => window.__viewer.grenade())).explosions).toHaveLength(0);
  await expect.poll(() => page.evaluate(() => window.__viewer.grenade().explosions.length), { timeout: 12_000 }).toBe(1);
  expect((await page.evaluate(() => window.__viewer.grenade())).explosions[0]).toMatchObject({ item: 'PMN Mine', radius: 40 });
  await page.locator('#view').screenshot({ path: join(SCREENS, 'frostfire-pmn-tripped.png') });
  expect(problems).toEqual([]);
});
