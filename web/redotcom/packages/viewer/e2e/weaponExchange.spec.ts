import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';
import type {} from '../src/hook';

/**
 * WEAPON EXCHANGE in the offline match (web sprint 4, M8/M9; research 94 part 2): the page's own room (`../src/net/
 * loopback`), the SEAL killed by its own grenade, the dead's prompt with the PC key's `[I]`; `I` opens the menu, the keys
 * change the primary and an equipment slot, each confirm is answered by the room, and the next round spawns the SEAL
 * with the kit the room answered (classic: the pick lands at the next round's rebuild, R94.3).
 */

const FIXTURES = join(fileURLToPath(new URL('../../..', import.meta.url)), 'test-fixtures');
const HAVE = existsSync(join(FIXTURES, 'RUN', 'MP2.ZDB'));

/** The menu's state through the hook. */
const menu = (page: Page) => page.evaluate(() => window.__viewer.weaponSelect());

test('offline: dead, the prompt, I opens WEAPON EXCHANGE; the primary and an equipment slot picked; the next round carries them', async ({ page }) => {
  test.skip(!HAVE, 'needs the fixtures (npm run extract-maps)');
  test.setTimeout(240_000);
  const problems: string[] = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));

  // The developer's kit stands in for the type's (the M4A1 SD, the Mark 23, the M67, the HE, no 2X): the base the
  // room replays the picks from.
  await page.goto('/?map=MP2&mode=play&devmode&kit=62,15,121,126,255');
  await expect(page.locator('#status')).toContainText('FROSTFIRE (MP2)', { timeout: 60_000 });
  await expect.poll(async () => page.evaluate(() => window.__viewer.net?.()?.state ?? null), { timeout: 30_000 }).toBe('open');
  await expect.poll(async () => page.evaluate(() => window.__viewer.feet()), { timeout: 30_000 }).not.toBeNull();
  expect(await page.evaluate(() => window.__viewer.loadout().loadout)).toEqual([62, 15, 121, 126, 255]);

  // Alive: I is not the menu's (the gate: dead only), and no prompt is drawn.
  expect(await page.evaluate(() => window.__viewer.weaponSelectKey('KeyI'))).toBe(false);
  expect((await menu(page)).prompt).toBeNull();

  // Dead by a grenade at the feet (the room's blast reaches the thrower); again if the first only hurt.
  for (let i = 0; i < 4 && (await page.evaluate(() => window.__viewer.hud().model.health)) > 0; i++) {
    await page.evaluate(() => window.__viewer.throwGrenade(0, true));
    await expect.poll(async () => (await menu(page)).gate.alive, { timeout: 8_000 }).toBe(false).catch(() => undefined);
  }
  await expect.poll(async () => (await menu(page)).gate, { timeout: 10_000 }).toMatchObject({ inMatch: true, alive: false, cameraOnSelf: true });
  // The dead's prompt (S1, FUN_001f97b0): the PC key's cap in the %c, drawn over the HUD, not posted as a message.
  await expect.poll(async () => (await menu(page)).prompt?.[0] ?? null).toBe('You have died.  [I] Select new weapons.');
  const posted = await page.evaluate(() => window.__viewer.hud().model.banner.map((b) => b.lines.map((l) => l.text).join('/')));
  expect(posted.some((l) => l.includes('You have died'))).toBe(false);

  // I opens the slot list on the kit the type holds (S2).
  await page.keyboard.press('KeyI');
  await expect.poll(async () => (await menu(page)).screen).toBe('list');
  expect((await menu(page)).loadout).toEqual([62, 15, 121, 126, 255]);

  // The primary: X the picker on it (S3), S the next item the SEALs may carry, Enter confirms (S4).
  await page.keyboard.press('KeyX');
  expect((await menu(page)).screen).toBe('picker');
  await page.keyboard.press('KeyS');
  const primary = (await menu(page)).item;
  expect(primary).not.toBe(62);
  await page.keyboard.press('Enter');
  await expect.poll(async () => (await menu(page)).sent).toEqual([{ slot: 0, id: primary }]);
  await expect.poll(async () => (await menu(page)).loadout[0]).toBe(primary);

  // Equipment slot 1 (the third row; the list skips a locked row): S S to it, X, S, Enter.
  await page.keyboard.press('KeyS');
  await page.keyboard.press('KeyS');
  expect((await menu(page)).slot).toBe(2);
  await page.keyboard.press('KeyX');
  await page.keyboard.press('KeyS');
  const equipment = (await menu(page)).item;
  expect(equipment).not.toBe(121);
  await page.keyboard.press('Enter');
  await expect.poll(async () => (await menu(page)).sent.length).toBe(2);
  const answered = (await menu(page)).loadout;
  expect(answered[0]).toBe(primary);
  expect(answered[2]).toBe(equipment);
  // The body keeps its kit this round (R94.3); the pick waits.
  expect(await page.evaluate(() => window.__viewer.loadout().loadout)).toEqual([62, 15, 121, 126, 255]);
  expect(await page.evaluate(() => window.__viewer.loadout().pending)).toEqual(answered);
  // I closes the list; the game's keys are the game's again.
  await page.keyboard.press('KeyI');
  expect((await menu(page)).screen).toBe('closed');

  // The lone SEAL's death ends the round (the elimination, 23 s, then ROUND COMPLETE): the next round's spawn carries
  // the room's kit, and the round's reset leaves the menu closed over it (S8).
  await expect.poll(async () => page.evaluate(() => window.__viewer.loadout().loadout), { timeout: 150_000, intervals: [1000] }).toEqual(answered);
  expect((await menu(page)).screen).toBe('closed');
  expect((await menu(page)).gate.alive).toBe(true);
  expect(problems).toEqual([]);
});
