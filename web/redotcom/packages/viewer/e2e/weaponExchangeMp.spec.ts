import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test, type Browser, type Page } from '@playwright/test';
import type {} from '../src/hook';

/**
 * WEAPON EXCHANGE against a match server (web sprint 4, M9; protocol 7): two pages on Frostfire, a Terrorist and a SEAL.
 * The Terrorist dies, picks a new primary in the menu -- its side's own list -- and the room answers; at the next round the
 * room spawns it with the pick, and the SEAL's page draws the Terrorist holding that item (the body's weapon by id,
 * `BodyState.weapon`). The server is started here on its own port (`WX_MP_PORT`, 8801 by default), from `SOCOM_DISC` or
 * the fixtures.
 */

const WEB = fileURLToPath(new URL('../../..', import.meta.url));
const FIXTURES = join(WEB, 'test-fixtures');
const DISC = process.env['SOCOM_DISC'] || FIXTURES;
const HAVE = existsSync(join(DISC, 'RUN', 'MP2.ZDB')) && existsSync(join(DISC, 'RUN', 'ZWEAPON.ZAR'));
const PORT = Number(process.env['WX_MP_PORT'] || 8801);

let server: ChildProcess | null = null;

test.beforeAll(async () => {
  if (!HAVE) return;
  server = spawn(process.execPath, ['--import', 'tsx', 'packages/server/src/main.ts'], {
    cwd: WEB, env: { ...process.env, SOCOM_DISC: DISC, PORT: String(PORT), HOST: '127.0.0.1', MAPS: 'MP2' }, stdio: 'pipe',
    detached: process.platform !== 'win32',
  });
  await new Promise<void>((ok, fail) => {
    const timer = setTimeout(() => fail(new Error('the match server did not start')), 60_000);
    server!.stdout!.on('data', (d: Buffer) => { if (d.toString().includes('"listening"')) { clearTimeout(timer); ok(); } });
    server!.on('exit', (code) => fail(new Error(`the match server exited ${code}`)));
  });
});

test.afterAll(() => {
  if (!server?.pid) return;
  try { if (process.platform === 'win32') server.kill(); else process.kill(-server.pid, 'SIGTERM'); } catch { /* gone */ }
});

async function joinPage(browser: Browser, name: string): Promise<Page> {
  const context = await browser.newContext({ viewport: { width: 960, height: 600 } });
  await context.addInitScript((n) => { localStorage.setItem('s2u.mp.name', n); }, name);
  const page = await context.newPage();
  await page.goto(`/?mode=play&mp&server=ws://127.0.0.1:${PORT}/ws&map=MP2&devmode`);
  await expect.poll(() => page.evaluate(() => window.__viewer?.net?.()?.feet ?? null), { timeout: 120_000 }).not.toBeNull();
  await expect.poll(() => page.evaluate(() => window.__viewer.net?.()?.team ?? null), { timeout: 30_000 }).not.toBeNull();
  return page;
}

test.skip(!HAVE, 'needs the fixtures or SOCOM_DISC with ZWEAPON.ZAR');

test('two pages: a Terrorist\'s pick is the room\'s next-round kit, and the SEAL\'s page draws it in the Terrorist\'s hand', async ({ browser }) => {
  test.setTimeout(300_000);
  const a = await joinPage(browser, 'ALPHA');
  const b = await joinPage(browser, 'BRAVO');
  const na = await a.evaluate(() => window.__viewer.net!()!);
  expect(na).toMatchObject({ state: 'open', role: 'player', team: 'terrorist' });
  expect(await b.evaluate(() => window.__viewer.net!()!.team)).toBe('seal');
  const banner = (p: Page): Promise<string[]> => p.evaluate(() => window.__viewer.hud().model.banner.map((m) => m.lines.map((l) => l.text).join('/')));
  await expect.poll(() => banner(a), { timeout: 30_000 }).toContain('STARTING ROUND 1 OF 11');
  // The Terrorists' type's kit (mp2_terror1: the 552 and the M9), and the SEAL sees the 552 in the Terrorist's hand.
  const before = await a.evaluate(() => window.__viewer.loadout().loadout);
  expect(before[0]).toBe(57);
  await expect.poll(async () => (await b.evaluate(() => window.__viewer.net!()!.bodies.find((x) => x.alive)?.weapon ?? null)), { timeout: 30_000 }).toBe(57);

  // The Terrorist dies by its own grenade; dead, I opens WEAPON EXCHANGE on its type's kit.
  const menu = (p: Page) => p.evaluate(() => window.__viewer.weaponSelect());
  for (let i = 0; i < 4 && (await menu(a)).gate.alive; i++) {
    await a.evaluate(() => window.__viewer.throwGrenade(0, true));
    await expect.poll(async () => (await menu(a)).gate.alive, { timeout: 8_000 }).toBe(false).catch(() => undefined);
  }
  expect((await menu(a)).gate).toMatchObject({ inMatch: true, alive: false, cameraOnSelf: true, spectator: false });
  await a.keyboard.press('KeyI');
  await expect.poll(async () => (await menu(a)).screen).toBe('list');
  await a.keyboard.press('KeyX');
  // The picker lists the Terrorists' own: step until an item other than the 552, then confirm.
  await a.keyboard.press('KeyS');
  const pick = (await menu(a)).item;
  expect(pick).not.toBe(57);
  await a.keyboard.press('Enter');
  // The room answered: the kit it will spawn the Terrorist with (the page's pending kit is the answer's).
  await expect.poll(async () => a.evaluate(() => window.__viewer.loadout().pending?.[0] ?? null), { timeout: 10_000 }).toBe(pick);
  expect((await menu(a)).loadout[0]).toBe(pick);
  await a.keyboard.press('KeyI');

  // The Terrorists eliminated, the next round: the room's spawn carries the pick, and the SEAL's page draws it.
  await expect.poll(async () => (await a.evaluate(() => window.__viewer.loadout().loadout))[0], { timeout: 150_000, intervals: [1000] }).toBe(pick);
  const aid = na.id;
  await expect.poll(async () => b.evaluate((id) => window.__viewer.net!()!.bodies.find((x) => x.id === id)?.weapon ?? null, aid), { timeout: 30_000 }).toBe(pick);
  expect(await b.evaluate((id) => window.__viewer.net!()!.bodies.find((x) => x.id === id)?.slot ?? null, aid)).toBe(0);
  await a.context().close();
  await b.context().close();
});
