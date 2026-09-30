import { describe, expect, it } from 'vitest';
import type { RdrNode } from '@s2u/archive';
import { arsenalOf, ITEM, type Loadout } from '@s2u/scene';
import {
  CATEGORY_RING, canOpen, cards, categoryName, closedMenu, reset, step, type MenuContext, type MenuInput, type MenuState,
} from '../src/weaponSelectState';

/**
 * WEAPON EXCHANGE's states (research 94 §B4, S0-S8) over a hand-built arsenal: `parseRdr`'s shape, the game's ids
 * (the class is the id range), the valves as a map's `mission.rdr` spells them.
 */

const rec = (...pairs: [string, RdrNode][]): RdrNode[] => pairs.flatMap(([k, v]) => [k, Array.isArray(v) ? v : [v]]);
const item = (name: string, id: number, extra: [string, RdrNode][] = []): RdrNode[] =>
  rec(['InternalName', name], ['ID', String(id)], ['AMMO_TYPES', []], ...extra);
const arsenal = arsenalOf(['ZAMMO', [], 'ZWEAPON', [
  item('Mark 23', 15), item('M9', 5), item('226', 6), item('HK5', 31), item('M4A1', 54), item('M4A1-M203', 61), item('AK-47', 58),
  item('870', 84), item('M40A1', 102), item('M67', 121), item('AN-M8', 122), item('HE', 126), item('M203', 141),
  item('M203 HE', 171), item('M203 FRAG', 175), item('Claymore', 153), item('C4', 151), item('PMN Mine', 158),
  item('Double Ammo Load', 194), item('Thermal Scope', 195),
]] as RdrNode);
const valves = new Map([
  ['Enable_Mark23', 1], ['Enable_beretta_m9', 8], ['Enable_Sig226', 8], ['Enable_mp5', 1], ['Enable_m4Acarbine', 1],
  ['Enable_m4Acarbine_203', 1], ['Enable_ak47', 8], ['Enable_870', 1], ['Enable_remington700', 9], ['Enable_frag', 9],
  ['Enable_smoke', 9], ['Enable_HEgren', 9], ['Enable_203HE', 0], ['Enable_203FRAG', 0], ['Enable_claymore', 1],
  ['Enable_c4', 16], ['Enable_pmn', 8], ['Enable_2xammo', 9], ['Enable_ThermScope', 9],
]);
const seal: MenuContext = { arsenal, valves, side: 'seal' };
const kit = (...ids: number[]): Loadout => ids as unknown as Loadout;
const drive = (ctx: MenuContext, s: MenuState, ...inputs: MenuInput[]): MenuState =>
  inputs.reduce((st, i) => step(ctx, st, i).state, s);

describe('WEAPON EXCHANGE, state by state (research 94 §B4)', () => {
  it('S0/S1: opens only dead, in the match, on oneself, not a spectator (FUN_001f7ff0)', () => {
    expect(canOpen({ inMatch: true, alive: false, cameraOnSelf: true, spectator: false })).toBe(true);
    expect(canOpen({ inMatch: true, alive: true, cameraOnSelf: true, spectator: false })).toBe(false);
    expect(canOpen({ inMatch: true, alive: false, cameraOnSelf: false, spectator: false })).toBe(false);
    expect(canOpen({ inMatch: true, alive: false, cameraOnSelf: true, spectator: true })).toBe(false);
    expect(canOpen({ inMatch: false, alive: false, cameraOnSelf: true, spectator: false })).toBe(false);
    const closed = closedMenu(kit(54, 15, 121, 126, 194));
    expect(step(seal, closed, 'inventory', false).state.screen).toBe('closed');
    for (const i of ['up', 'action', 'back'] as const) expect(step(seal, closed, i).state).toBe(closed);
  });

  it('S2: Inventory opens the slot list on slot 0; Up/Down wrap; Triangle, Start or Inventory close', () => {
    const { state, event } = step(seal, closedMenu(kit(54, 15, 121, 126, 194)), 'inventory');
    expect([state.screen, state.slot, event]).toEqual(['list', 0, { kind: 'opened' }]);
    expect(drive(seal, state, 'up').slot).toBe(4);
    expect(drive(seal, state, 'down', 'down').slot).toBe(2);
    expect(step(seal, state, 'back')).toMatchObject({ state: { screen: 'closed' }, event: { kind: 'closed' } });
    expect(step(seal, state, 'inventory').state.screen).toBe('closed');
    expect(drive(seal, state, 'left', 'right')).toBe(state);                 // no category on the list
  });

  it('S5: a locked slot is skipped by the cursor -- the BREACH C4 (16), the M203 under its rifle', () => {
    const s = drive(seal, closedMenu(kit(54, 15, 121, 126, ITEM.C4)), 'inventory');
    expect(drive(seal, s, 'up').slot).toBe(3);                               // 0 -> (4 locked) -> 3
    const m203 = drive(seal, closedMenu(kit(61, 15, ITEM.M203, 175, 194)), 'inventory', 'down');
    expect(m203.slot).toBe(1);
    expect(drive(seal, m203, 'down').slot).toBe(3);                          // 2 holds the locked M203
  });

  it('S3: Action opens the picker on the slot\'s item and its category; Up/Down skip the other side\'s items', () => {
    const s = drive(seal, closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'action');
    expect([s.screen, s.category, s.item]).toEqual(['picker', 'rifle', 54]);
    expect(categoryName(s.category, 'primary')).toBe('ASSAULT RIFLES');
    const down = drive(seal, s, 'down');
    expect(down.item).toBe(61);                                              // the AK-47 (58) is the Terrorists'
    expect(drive(seal, down, 'down').item).toBe(54);                         // wraps inside the category
    const side = drive(seal, closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'down', 'action');
    expect([side.category, side.item, drive(seal, side, 'down').item]).toEqual(['pistol', 15, 15]);  // M9, 226 refused
  });

  it('S3: Left/Right walk the ring, skipping empty categories and LAUNCHED without a launcher', () => {
    const s = drive(seal, closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'action');
    const right = drive(seal, s, 'right');
    expect([right.category, right.item]).toEqual(['shotgun', 84]);          // rifle -> (shotgun) the 870
    expect(drive(seal, right, 'right').category).toBe('sniper');            // mg: nothing for the SEALs here
    expect(drive(seal, s, 'left', 'left').category).toBe('all');
    expect(CATEGORY_RING.secondary).toEqual(['pistol']);
    const eq = drive(seal, closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'down', 'down', 'action');
    expect(eq.category).toBe('grenade');
    const ring = [eq.category];
    let cur = eq;
    for (let i = 0; i < 6; i++) { cur = drive(seal, cur, 'right'); ring.push(cur.category); }
    expect(ring).not.toContain('launcherRound');
    const launcher = drive(seal, closedMenu(kit(61, 15, ITEM.M203, 175, 194)), 'inventory', 'down', 'down', 'action');
    let c2 = launcher; const ring2 = [c2.category];
    for (let i = 0; i < 6; i++) { c2 = drive(seal, c2, 'right'); ring2.push(c2.category); }
    expect(ring2).toContain('launcherRound');
  });

  it('S3: the three cards, a side card blank when the category holds one item', () => {
    const s = drive(seal, closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'action');
    expect(cards(seal, s)).toEqual([61, 54, 61]);
    const pistol = drive(seal, closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'down', 'action');
    expect(cards(seal, pistol)).toEqual([null, 15, null]);
  });

  it('S4: Action confirms -- the slot set, a launcher\'s fill, the pick recorded -- and back to the list', () => {
    const s = drive(seal, closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'action', 'down');
    const { state, event } = step(seal, s, 'action');
    expect(state.screen).toBe('list');
    expect(state.loadout).toEqual([61, 15, ITEM.M203, 175, 194]);
    expect(event).toEqual({ kind: 'confirmed', loadout: [61, 15, ITEM.M203, 175, 194], pick: { slot: 0, id: 61 } });
    expect(state.picks).toEqual([{ slot: 0, id: 61 }]);
  });

  it('S3 cancel: Triangle / Start back to the list with no change; confirming the slot\'s own item changes nothing', () => {
    const s = drive(seal, closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'action', 'down', 'back');
    expect([s.screen, s.loadout, s.picks]).toEqual(['list', [54, 15, 121, 126, 194], []]);
    const same = step(seal, drive(seal, closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'action'), 'action');
    expect([same.state.screen, same.event]).toEqual(['list', null]);
  });

  it('the other side lists its own: a Terrorist\'s sidearm picker holds the M9 and the 226, never the Mark 23', () => {
    const terr: MenuContext = { arsenal, valves, side: 'terrorist' };
    const s = drive(terr, closedMenu(kit(58, 5, 121, 126, 194)), 'inventory', 'down', 'action');
    expect([s.item, drive(terr, s, 'down').item, drive(terr, s, 'down', 'down').item]).toEqual([5, 6, 5]);
    const eq = drive(terr, closedMenu(kit(58, 5, 121, 126, 194)), 'inventory', 'down', 'down', 'down', 'action', 'right');
    expect(eq.category).toBe('explosive');
    expect(eq.item).toBe(ITEM.PMN);                                          // no claymore, no C4 (16 is a SEAL lock)
  });

  it('S8: the round\'s reset closes the menu over the kit the spawn took', () => {
    const s = reset(kit(102, 15, 121, 195, 194));
    expect([s.screen, s.loadout, s.picks]).toEqual(['closed', [102, 15, 121, 195, 194], []]);
  });
});
