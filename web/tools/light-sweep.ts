/**
 * Renders one map from a spawn under several lighting settings, so the defaults can be chosen by
 * looking rather than by arithmetic.
 *
 *   npx tsx tools/light-sweep.ts [MAPNAME] [yaw]
 *
 * Writes test-fixtures/screens/sweep-<n>.png, one per row of SETTINGS, each captioned in the console.
 */
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const MAP = process.argv[2] ?? 'FROSTFIRE';
const YAW = Number(process.argv[3] ?? 40);
const OUT = fileURLToPath(new URL('../test-fixtures/screens', import.meta.url));
const URL_BASE = process.env.VIEWER_URL ?? 'http://localhost:5173/';
const EYE = 20;

/** ambient, x, y, z, gain — the four `lit` terms and the exposure. */
const SETTINGS: [string, number, number, number, number, number][] = [
  ['current',        0.55, 0.35, 1.00, 0.35, 2.00],
  ['dimmer',         0.40, 0.30, 0.90, 0.30, 1.60],
  ['night contrast', 0.28, 0.28, 1.00, 0.28, 1.45],
  ['night deep',     0.18, 0.25, 1.00, 0.25, 1.30],
  ['flat low',       0.55, 0.20, 0.55, 0.20, 1.30],
];

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1152, height: 720 } });
page.on('pageerror', (e) => console.log('PAGEERROR:', e.message));
await page.goto(URL_BASE);
await page.waitForFunction(() => document.querySelector('#status')?.textContent?.includes('triangles'));

if (MAP !== 'FROSTFIRE') {
  const option = page.locator('#maps option', { hasText: MAP }).first();
  await page.selectOption('#maps', { value: await option.getAttribute('value') ?? '' });
  await page.waitForFunction((m) => document.querySelector('#status')?.textContent?.includes(m), MAP);
}

// Stand at spawn A, eye height, looking along `yaw` -- a player's view, not an orbit.
await page.evaluate(({ eye, yaw }) => {
  const w = window as unknown as {
    __viewer: { stats(): { spawns: { a: [number, number, number] } | null }; setCamera(p: Record<string, number>): void };
  };
  const a = w.__viewer.stats().spawns?.a;
  if (a) w.__viewer.setCamera({ x: a[0], y: a[1] + eye, z: a[2], yaw, pitch: -4 });
}, { eye: EYE, yaw: YAW });

const settle = (): Promise<void> => page.evaluate(
  () => new Promise<void>((d) => requestAnimationFrame(() => requestAnimationFrame(() => d()))),
);

for (let i = 0; i < SETTINGS.length; i++) {
  const [label, ambient, x, y, z, gain] = SETTINGS[i]!;
  // No nested named function: tsx's esbuild transform injects a `__name` helper that does not exist
  // inside the page, and page.evaluate would throw ReferenceError.
  await page.evaluate((v) => {
    for (const [id, value] of Object.entries(v)) {
      const el = document.getElementById(id) as HTMLInputElement | null;
      if (!el) continue;
      el.value = String(value);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }, { ambient, lightx: x, lighty: y, lightz: z, lightgain: gain });
  await settle();
  await settle();
  const file = join(OUT, `sweep-${i}.png`);
  await page.screenshot({ path: file });
  console.log(`${String(i).padEnd(2)} ${label.padEnd(15)} amb ${ambient} x ${x} y ${y} z ${z} gain ${gain} -> ${file}`);
}

await browser.close();
