import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';
// `src/hook.ts` is types only; its `declare global` is what makes `window.__viewer` exist inside `page.evaluate`.
import type {} from '../src/hook';

/**
 * The M4A1-M203's launcher as a fire mode on Frostfire (web sprint 4 M4; research 94 §C4, R94.8): the kit the select
 * gives the carrier -- the M4A1-M203, the Mark 23, the M203, one M203 FRAG slot, 2X (`&kit=61,15,141,175,194`) -- comes
 * up on burst; the switch runs 3 then the FRAG round (175); a pull launches the round from the rifle, one off its slot,
 * the HUD's first fire-mode cell its icon. Fired at the container 37 units west of spawn A it is a dud (inside its
 * 100-unit arming distance: no blast); fired down the open dock west-south-west it flies and goes off.
 */

const SCREENS = fileURLToPath(new URL('../../../test-fixtures/screens/launcher', import.meta.url));
const SPAWN_A: [number, number, number] = [796, 100, 614];
const EYE = 15.4;
const REST_PITCH = -9.167;

const settle = (page: Page): Promise<void> => page.evaluate(
  () => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))),
);

test('Frostfire: the M4A1-M203 switches to its FRAG round, a dud inside 10 m, a blast down the dock', async ({ page }) => {
  mkdirSync(SCREENS, { recursive: true });
  const problems: string[] = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));

  await page.goto('/?mode=play&fly&devmode&kit=61,15,141,175,194');
  const status = page.locator('#status');
  await expect(status).toContainText('triangles');
  await page.locator('#maps').selectOption('RUN/MP2.ZDB');
  await expect(status).toContainText('FROSTFIRE (MP2)');
  await expect(status).toContainText('triangles');
  expect((await page.evaluate(() => window.__viewer.stats())).diagnostics).toEqual([]);

  const stand = async (yaw: number, pitch: number): Promise<void> => {
    expect(await page.evaluate(() => window.__viewer.setMode('walk'))).toBe(true);
    await page.evaluate(([x, y, z, eye, yaw, pitch]) => window.__viewer.setCamera({ x, y: y + eye, z, yaw, pitch }), [...SPAWN_A, EYE, yaw, pitch] as const);
    await page.evaluate(() => window.__viewer.walkFor(0.3, { forward: 0 }));
  };
  await stand(90, REST_PITCH);
  await page.waitForTimeout(1500);
  await settle(page);

  // The carrier comes up on burst (FUN_005c0250); the switch: automatic, then the round the kit holds (FUN_005c4600).
  expect(await page.evaluate(() => window.__viewer.fireMode())).toBe('BURST');
  expect(await page.evaluate(() => window.__viewer.fireRound())).toBeNull();
  expect(await page.evaluate(() => window.__viewer.switchFireMode())).toBe('AUTO');
  expect(await page.evaluate(() => window.__viewer.switchFireMode())).toBe('175');
  expect(await page.evaluate(() => window.__viewer.fireRound())).toEqual({ id: 175, name: 'M203 FRAG', armingDistance: 100, icon: 'firemode_203_frag.tif' });
  await settle(page);
  // The box through the redirect: the FRAG slot's 6 x 1; the fire-mode cell the round's icon (FUN_00237b40).
  const hud = (await page.evaluate(() => window.__viewer.hud())).model;
  expect(hud).toMatchObject({ rounds: 6, capacity: 6, spare: 0, fireModeIcon: 'firemode_203_frag.tif' });

  // At the container 37 units west: inside the arming distance, a dud (FUN_003c8920 L319439-319462).
  const dud = await page.evaluate(() => window.__viewer.shoot());
  expect(dud).not.toBeNull();
  expect(dud!.hit).toBeNull();
  await expect.poll(() => page.evaluate(() => window.__viewer.grenade().live.length), { timeout: 5_000 }).toBe(1);
  await page.waitForTimeout(1500);
  const lying = await page.evaluate(() => window.__viewer.grenade());
  expect(lying.explosions).toHaveLength(0);
  expect(lying.live[0]!.fuse).toBeGreaterThan(1000);           // the dud's fuse: 9999999
  expect((await page.evaluate(() => window.__viewer.fire())).magazine.rounds).toBe(5);

  // Down the open dock (grenade.spec's heading): past 10 m it goes off where it lands.
  await stand(240, 2);
  await settle(page);
  // The round's lock (0.5 s), its `Rifle m203 reload` and the FireWait (1 s) run out before the next pull.
  await expect.poll(() => page.evaluate(() => window.__viewer.shoot() !== null), { timeout: 15_000 }).toBe(true);
  expect((await page.evaluate(() => window.__viewer.fire())).magazine.rounds).toBe(4);
  await expect.poll(() => page.evaluate(() => window.__viewer.grenade().explosions.length), { timeout: 15_000 }).toBe(1);
  const blast = (await page.evaluate(() => window.__viewer.grenade())).explosions[0]!;
  expect(blast.item).toBe('M203 FRAG');
  expect(blast.detonation).toBe('blast');
  expect(Math.hypot(blast.pos[0] - SPAWN_A[0], blast.pos[2] - SPAWN_A[2])).toBeGreaterThan(100);
  await page.locator('#view').screenshot({ path: join(SCREENS, 'frostfire-m203-frag-blast.png') });
  expect(problems).toEqual([]);
});
