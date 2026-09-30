import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';
import type {} from '../src/hook';

/**
 * The sights per weapon (web sprint 4 M5; research 94 §C6, §C7, R94.15): the M40A1 with the thermal scope on Frostfire
 * -- `&kit=102,15,121,195,194` (the M40A1, the Mark 23, the M67, the thermal scope, 2X) -- zoomed to its 6x and then
 * 12x levels (`ZoomMode1/2`), the scope's overlay drawn with the black beside it on the wide frame (the owner's
 * ruling), the sniper's `thermal_scope` node shown for its `scope`, and `to_thermal_lens_fx`'s rows on the lit colours
 * (the world's row 0 a cold blue). Screenshots go to `web/redotcom/test-fixtures/screens/sights` (git-ignored).
 */

const SCREENS = fileURLToPath(new URL('../../../test-fixtures/screens/sights', import.meta.url));
const SPAWN_A: [number, number, number] = [796, 100, 614];

const settle = (page: Page, frames = 2): Promise<void> => page.evaluate((n) => new Promise<void>((done) => {
  let left = n;
  const step = (): void => { if (--left <= 0) done(); else requestAnimationFrame(step); };
  requestAnimationFrame(step);
}), frames);

/** The canvas as composited: the mean colour of a box (fractions of the frame), and of a strip at the left edge. */
async function probe(page: Page): Promise<{ centre: number[]; side: number[]; width: number; height: number }> {
  const png = (await page.locator('#view').screenshot()).toString('base64');
  return page.evaluate(async (data) => {
    const img = new Image();
    img.src = `data:image/png;base64,${data}`;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const g = c.getContext('2d')!;
    g.drawImage(img, 0, 0);
    const mean = (x0: number, y0: number, x1: number, y1: number): number[] => {
      const d = g.getImageData(Math.floor(x0), Math.floor(y0), Math.max(1, Math.floor(x1 - x0)), Math.max(1, Math.floor(y1 - y0))).data;
      const s: [number, number, number] = [0, 0, 0];
      for (let k = 0; k < d.length; k += 4) { s[0] += d[k]!; s[1] += d[k + 1]!; s[2] += d[k + 2]!; }
      const n = d.length / 4;
      return s.map((v) => v / n);
    };
    const w = img.width, h = img.height;
    // Inside the tube (a radius of 202 of the frame's 448, research 84 section 9) off the cross; the side past its square.
    // The right edge (the panel stands over the left one), between the compass and the ammo box.
    return { centre: mean(w / 2 - h * 0.2, h / 2 - h * 0.2, w / 2 - h * 0.05, h / 2 - h * 0.05), side: mean(w * 0.96, h * 0.35, w, h * 0.8), width: w, height: h };
  }, png);
}

test('the M40A1 with the thermal scope: 6x, 12x, the overlay with its black sides, thermal_scope, the thermal rows', async ({ page }) => {
  mkdirSync(SCREENS, { recursive: true });
  const problems: string[] = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  await page.setViewportSize({ width: 1280, height: 720 });            // 16:9: the scope's square leaves black sides
  await page.goto('/?mode=play&fly&devmode&kit=102,15,121,195,194');
  const status = page.locator('#status');
  await expect(status).toContainText('triangles');
  await page.locator('#maps').selectOption('RUN/MP2.ZDB');
  await expect(status).toContainText('FROSTFIRE (MP2)');
  await expect(status).toContainText('triangles');
  expect(await page.evaluate(() => window.__viewer.setMode('walk'))).toBe(true);
  await page.evaluate(([x, y, z]) => window.__viewer.setCamera({ x, y: y + 15.4, z, yaw: 0, pitch: 0 }), SPAWN_A);
  // The effect data (the lens's rows) arrives after the map: wait for it before the scope.
  await expect.poll(async () => (await page.evaluate(() => window.__viewer.stats())).lens.node, { timeout: 30_000 }).toBe('thermal_scope');
  await settle(page, 30);

  // Third person: no lens; the M40A1's thermal_scope node shown for its scope (FUN_005b82e0).
  const rest = await page.evaluate(() => ({ z: window.__viewer.zoom(), lens: window.__viewer.stats().lens, r: window.__viewer.reticle() }));
  expect(rest.z.state).toBe(0);
  expect(rest.lens.effect).toBeNull();
  expect(rest.lens.rows).toBeNull();
  expect(rest.r.type).toBe(1);                                          // the sniper unscoped: ret_rifle (FUN_005be300)
  const before = await probe(page);
  await page.screenshot({ path: join(SCREENS, '1-third.png') });

  // ZoomMode1: 6x, the scope's overlay, the thermal lens.
  expect(await page.evaluate(() => window.__viewer.zoomIn())).toBe(5);
  await settle(page, 30);
  const six = await page.evaluate(() => ({ z: window.__viewer.zoom(), lens: window.__viewer.stats().lens, r: window.__viewer.reticle(), hud: window.__viewer.hud() }));
  expect(six.z.magnification).toBe(6);
  expect(six.r.mode).toBe('scope');                                     // set 5 (its arms-less draw: `type` keeps the rifle's)
  expect(six.lens.effect).toBe('to_thermal_lens_fx');
  expect(six.lens.rows!.map((r) => r.map((x) => Math.round(x * 100) / 100))).toEqual([[0.1, 0.33, 0.7, 0], [0, 0, 0, 0], [0.5, 0.3, 0, 128], [0.9, 0.65, 0, 50]]);
  expect(six.hud.model.zoom).toBe(6);                                   // "ZOOM: 6.0x" (research 87 section 13)
  await page.screenshot({ path: join(SCREENS, '2-thermal-6x.png') });

  // ZoomMode2: 12x, the last level (no wrap); the lens stays.
  expect(await page.evaluate(() => window.__viewer.zoomIn())).toBe(6);
  expect(await page.evaluate(() => window.__viewer.zoomIn())).toBe(6);
  await settle(page, 40);
  const twelve = await page.evaluate(() => ({ z: window.__viewer.zoom(), lens: window.__viewer.stats().lens, r: window.__viewer.reticle() }));
  expect(twelve.z.magnification).toBe(12);
  expect(twelve.r.mode).toBe('scope');
  expect(twelve.lens.effect).toBe('to_thermal_lens_fx');
  const scoped = await probe(page);
  await page.screenshot({ path: join(SCREENS, '3-thermal-12x.png') });
  // The picture: the scope's black beside its square on the wide frame; inside the tube the world through row 0 --
  // blue over red -- where third person's snow and steel were not.
  expect(scoped.width / scoped.height).toBeGreaterThan(1.5);
  expect(Math.max(...scoped.side)).toBeLessThan(8);
  expect(scoped.centre[2]!).toBeGreaterThan(scoped.centre[0]! * 1.5);
  expect(scoped.centre[2]! - scoped.centre[0]!).toBeGreaterThan(before.centre[2]! - before.centre[0]! + 10);

  // Out: 12x -> 6x -> third person, the lens off.
  expect(await page.evaluate(() => window.__viewer.zoomOut())).toBe(5);
  expect(await page.evaluate(() => window.__viewer.zoomOut())).toBe(0);
  await settle(page, 10);
  expect((await page.evaluate(() => window.__viewer.stats())).lens).toMatchObject({ effect: null, rows: null, node: 'thermal_scope' });
  expect(problems).toEqual([]);
});
