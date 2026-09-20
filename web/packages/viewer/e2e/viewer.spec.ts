import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from '@playwright/test';

/** Screenshots are evidence, not fixtures: `web/test-fixtures/` is git-ignored. */
const SCREENS = fileURLToPath(new URL('../../../test-fixtures/screens', import.meta.url));

/** The shape `src/main.ts` puts on `window`; repeated here because the page's types do not cross over. */
interface ViewerStats { triangles: number; backend: string; diagnostics: string[]; loadMs: number; map: string | null }
interface ViewerHook {
  setCamera(pose: { x?: number; y?: number; z?: number; yaw?: number; pitch?: number }): void;
  stats(): ViewerStats;
}
declare global {
  interface Window { __viewer: ViewerHook }
}

/** Frostfire's two spawns (36, measured): the midpoint is the middle of the playable ground. */
const SPAWN_A = { x: 796, y: 100, z: 614 };
const SPAWN_B = { x: 536, y: 143, z: 1254 };

test('Frostfire renders from the served archive', async ({ page }) => {
  mkdirSync(SCREENS, { recursive: true });
  const problems: string[] = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`); });

  await page.goto('/');
  const maps = page.locator('#maps');
  await expect(maps.locator('option', { hasText: 'FROSTFIRE' })).toHaveCount(1);
  await maps.selectOption({ label: 'FROSTFIRE (MP2)' });

  const status = page.locator('#status');
  await expect(status).toContainText('triangles');

  const stats = await page.evaluate(() => window.__viewer.stats());
  test.info().annotations.push({ type: 'backend', description: stats.backend });
  test.info().annotations.push({ type: 'triangles', description: String(stats.triangles) });
  test.info().annotations.push({ type: 'loadMs', description: String(stats.loadMs) });
  console.log(`FROSTFIRE: backend ${stats.backend}, ${stats.triangles} triangles, ${stats.loadMs} ms load`);
  expect(stats.map).toBe('FROSTFIRE');
  expect(stats.triangles).toBeGreaterThan(2000);
  expect(stats.diagnostics).toEqual([]);

  // A frame has to have been drawn with the new world in it before the canvas is worth photographing.
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))));
  await page.screenshot({ path: join(SCREENS, 'frostfire-spawnA.png') });

  // Straight down over the middle of the map, below the sky chunk at y = 1442.7 so the ground is what
  // the picture shows.
  await page.evaluate(([a, b]) => window.__viewer.setCamera({
    x: (a!.x + b!.x) / 2, y: 1400, z: (a!.z + b!.z) / 2, yaw: 0, pitch: -90,
  }), [SPAWN_A, SPAWN_B]);
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))));
  await page.screenshot({ path: join(SCREENS, 'frostfire-top.png') });

  expect(problems).toEqual([]);
});
