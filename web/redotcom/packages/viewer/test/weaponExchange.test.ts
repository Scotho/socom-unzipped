import { describe, expect, it } from 'vitest';
import type { RdrNode } from '@s2u/archive';
import { applyPicks, arsenalOf, type Loadout, type Pick } from '@s2u/scene';
import type { MenuContext } from '../src/weaponSelectState';
import {
  compactPicks, frameOfPoint, menuTap, padButtonsDown, WeaponExchange, type MatchGate,
} from '../src/weaponExchange';
import { WEAPON_SELECT_ELEMENT } from '../src/weaponSelect';

/**
 * WEAPON EXCHANGE in the match (web sprint 4, M8's wiring; research 94 §B2-§B4): the menu's gate -- the pad's R2, the
 * PC's `I` (`WEAPON_SELECT_KEY_READING`) and the touch button open it only dead, in the match, on oneself, not a
 * spectator -- the keys and the pad inside it taken from the game while open (HUD mode 1), each confirm handed on as
 * the `loadout` request's pick, the room's answer shown, the round's reset (S8) closing it, a tap's place on the
 * 640x448 frame read as the menu's inputs.
 */

const rec = (...pairs: [string, RdrNode][]): RdrNode[] => pairs.flatMap(([k, v]) => [k, Array.isArray(v) ? v : [v]]);
const item = (name: string, id: number): RdrNode[] => rec(['InternalName', name], ['DisplayName', name.toUpperCase()], ['ID', String(id)], ['AMMO_TYPES', []], ['IconTextureName', `${name}_icon.tif`]);
const arsenal = arsenalOf(['ZAMMO', [], 'ZWEAPON', [
  item('Mark 23', 15), item('M9', 5), item('M4A1', 54), item('M4A1 SD', 62), item('AK-47', 58), item('552', 57),
  item('M67', 121), item('AN-M8', 122), item('HE', 126), item('C4', 151), item('Double Ammo Load', 194),
]] as RdrNode);
const valves = new Map([
  ['Enable_Mark23', 1], ['Enable_beretta_m9', 8], ['Enable_m4Acarbine', 1], ['Enable_M4A1_SD', 1], ['Enable_ak47', 8],
  ['Enablesig_commando', 8], ['Enable_frag', 9], ['Enable_smoke', 9], ['Enable_HEgren', 9], ['Enable_c4', 17], ['Enable_2xammo', 9],
]);
const seal: MenuContext = { arsenal, valves, side: 'seal' };
const terrorist: MenuContext = { arsenal, valves, side: 'terrorist' };
const kit = (...ids: number[]): Loadout => ids as unknown as Loadout;
const SEAL_KIT = kit(54, 15, 121, 151, 194);
const DEAD: MatchGate = { inMatch: true, alive: false, cameraOnSelf: true, spectator: false };

function exchange(ctx: MenuContext = seal, opensOn: Loadout = SEAL_KIT) {
  let now = 0;
  const confirmed: Pick[] = [];
  const x = new WeaponExchange({ clock: () => now, opensOn: () => opensOn, confirm: (p) => confirmed.push(p) });
  x.setContext(ctx);
  return { x, confirmed, advance: (s: number) => { now += s; } };
}

describe('the gate: what opens the menu in the match (FUN_001f7ff0 L56648-56661)', () => {
  it.each([
    // [what, the gate, opens]
    ['dead, in the match, on oneself', DEAD, true],
    ['alive (R2 is the in-hand inventory then)', { ...DEAD, alive: true }, false],
    ['following a teammate (the camera off oneself)', { ...DEAD, cameraOnSelf: false }, false],
    ['a spectator', { ...DEAD, spectator: true }, false],
    ['no match (&nomatch, the free walk)', { ...DEAD, inMatch: false }, false],
  ] as const)('%s: the pad\'s R2, the key I and the touch button', (_what, gate, opens) => {
    for (const how of ['pad', 'key', 'touch'] as const) {
      const { x } = exchange();
      const taken = how === 'pad' ? x.pad(new Set(['R2']), gate) : how === 'key' ? x.key('KeyI', gate) : x.touchButton(gate);
      expect(x.isOpen(), how).toBe(opens);
      expect(taken, how).toBe(opens);
    }
  });

  it('closed, no other key or button is the menu\'s: the game keeps W, X, Space, the d-pad and Cross', () => {
    const { x } = exchange();
    for (const code of ['KeyW', 'KeyX', 'Space', 'Enter', 'Backspace']) expect(x.key(code, DEAD), code).toBe(false);
    expect(x.pad(new Set(['Up', 'Cross', 'Triangle', 'Start']), DEAD)).toBe(false);
    expect(x.isOpen()).toBe(false);
  });

  it('without the arsenal (no ZWEAPON.ZAR) there is nothing to open', () => {
    const { x } = exchange();
    x.setContext(null);
    expect(x.key('KeyI', DEAD)).toBe(false);
    expect(x.isOpen()).toBe(false);
  });
});

describe('inside: the keys and the pad per the menu\'s maps, the game\'s input taken (HUD mode 1)', () => {
  it('opens on the kit the type holds, steps with the keys, confirms into a pick, and takes every mapped key', () => {
    const { x, confirmed } = exchange();
    x.key('KeyI', DEAD);
    expect(x.state()).toMatchObject({ screen: 'list', slot: 0, loadout: [...SEAL_KIT] });
    expect(x.key('KeyX', DEAD)).toBe(true);                          // Action: the picker on the primary
    expect(x.state()).toMatchObject({ screen: 'picker', item: 54 });
    x.key('KeyS', DEAD);                                              // Down: the next listable primary, the M4A1 SD
    expect(x.state().item).toBe(62);
    x.key('Enter', DEAD);                                             // confirm (S4)
    expect(confirmed).toEqual([{ slot: 0, id: 62 }]);
    expect(x.state()).toMatchObject({ screen: 'list', loadout: [62, 15, 121, 151, 194] });
    expect(x.key('KeyQ', DEAD)).toBe(true);                           // open, every key is the menu's: the game's are blocked
    expect(x.key('KeyI', DEAD)).toBe(true);                           // Inventory closes the list
    expect(x.isOpen()).toBe(false);
  });

  it('the pad: the d-pad, Cross to confirm, Triangle or Start back, R2 closes the list; the locked C4 row skipped', () => {
    const { x, confirmed } = exchange();
    x.pad(new Set(['R2']), DEAD);
    x.pad(new Set(['Down']), DEAD); x.pad(new Set(['Down']), DEAD); x.pad(new Set(['Down']), DEAD);
    expect(x.state().slot).toBe(4);                                   // 0 -> 1 -> 2 -> 4: slot 3's C4 is locked (Enable_c4 16)
    x.pad(new Set(['Up']), DEAD);
    expect(x.state().slot).toBe(2);
    x.pad(new Set(['Cross']), DEAD);
    x.pad(new Set(['Down']), DEAD);
    x.pad(new Set(['Triangle']), DEAD);                               // back: no change
    expect(confirmed).toEqual([]);
    expect(x.state().screen).toBe('list');
    x.pad(new Set(['Start']), DEAD);
    expect(x.isOpen()).toBe(false);
  });

  it('the room\'s answer is what the menu shows; a refusal\'s kit replaces the menu\'s own', () => {
    const { x } = exchange();
    x.key('KeyI', DEAD);
    x.answer(kit(62, 15, 122, 151, 194));
    expect(x.state().loadout).toEqual([62, 15, 122, 151, 194]);
  });

  it('S8: the round\'s reset closes the menu over the kit the spawn took; an unconfirmed pick is lost', () => {
    const { x, confirmed } = exchange();
    x.key('KeyI', DEAD); x.key('KeyX', DEAD); x.key('KeyS', DEAD);
    x.reset(kit(62, 15, 121, 151, 194));
    expect(x.state()).toMatchObject({ screen: 'closed', loadout: [62, 15, 121, 151, 194] });
    expect(confirmed).toEqual([]);
  });

  it('a Terrorist\'s menu lists the Terrorists\' own items: the 552 and the AK-47, never an M4', () => {
    const { x } = exchange(terrorist, kit(57, 5, 121, 126, 255));
    x.key('KeyI', DEAD); x.key('KeyX', DEAD);
    const seen = new Set<number>();
    for (let i = 0; i < 6; i++) { seen.add(x.state().item); x.key('KeyS', DEAD); }
    expect([...seen].sort()).toEqual([57, 58]);
  });

  it('draws on its own HUD element, the prompt with it; closed and faded, only the prompt', () => {
    const { x, advance } = exchange();
    const sizes = { 'newweapnbkrnd.tif': { width: 128, height: 64 }, 'font_text_01.tif': { width: 256, height: 256 } };
    const prompt = { ghost: false, device: 'keyboard' as const, sinceDeath: 1 };
    x.key('KeyI', DEAD);
    advance(1);
    const open = x.draw({ width: 640, height: 448 }, sizes, prompt);
    expect(open.quads.length).toBeGreaterThan(0);
    expect(new Set(open.quads.map((q) => q.element))).toEqual(new Set([WEAPON_SELECT_ELEMENT]));
    expect(WEAPON_SELECT_ELEMENT).toBe('weaponSelect');
    expect(x.layout(prompt).items.filter((i) => i.part === 'title')).toHaveLength(1);
    x.key('KeyI', DEAD);
    advance(1);
    expect(x.layout(prompt).items.every((i) => i.part === 'prompt')).toBe(true);
    expect(x.layout(null).items).toEqual([]);
  });
});

describe('the touch control inside the menu (WEAPON_SELECT_TOUCH_READING: rows and cards tappable)', () => {
  it.each([
    // [what, screen, the frame point, the inputs]
    ['a row in the list: stepped to, then opened', 'list', [40, 195], ['down', 'down', 'action']],
    ['the locked row: nothing', 'list', [40, 215], []],
    ['the picker\'s middle card: confirm', 'picker', [250, 250], ['action']],
    ['the picker\'s top card: up', 'picker', [250, 190], ['up']],
    ['the picker\'s bottom card: down', 'picker', [250, 320], ['down']],
    ['the right category arrow', 'picker', [320, 120], ['right']],
    ['the left category arrow', 'picker', [180, 120], ['left']],
    ['outside the panels in the picker: back', 'picker', [500, 100], ['back']],
    ['the picker from the list: opened on the slot', 'list', [250, 250], ['action']],
  ] as const)('%s', (_what, screen, [fx, fy], inputs) => {
    const { x } = exchange();
    x.key('KeyI', DEAD);
    if (screen === 'picker') x.key('KeyX', DEAD);
    expect(menuTap(seal, x.state(), fx, fy)).toEqual(inputs);
  });

  it('a canvas point to the frame: centred, scaled by the height (drawWeaponSelect\'s inverse)', () => {
    for (const [px, py, w, h] of [[640, 224, 1280, 448], [480, 300, 960, 600]] as const) {
      const [fx, fy] = frameOfPoint(px, py, { width: w, height: h });
      expect(fx).toBeCloseTo(320, 9);
      expect(fy).toBeCloseTo(224, 9);
    }
  });
});

describe('the pad\'s buttons, and the list the room replays', () => {
  it('reads a pad\'s standard buttons down by the Gamepad API\'s pressed or value', () => {
    const buttons = Array.from({ length: 16 }, () => ({ pressed: false, value: 0 }));
    buttons[7] = { pressed: false, value: 0.9 };                        // R2, an analogue trigger
    buttons[0] = { pressed: true, value: 1 };                           // Cross
    expect([...padButtonsDown({ axes: [], buttons })].sort()).toEqual(['Cross', 'R2']);
    expect(padButtonsDown(null).size).toBe(0);
  });

  it('compacts a long list into one that reaches the same kit, or keeps it', () => {
    const base = SEAL_KIT;
    const long: Pick[] = [{ slot: 0, id: 62 }, { slot: 0, id: 54 }, { slot: 0, id: 62 }, { slot: 2, id: 122 }, { slot: 2, id: 126 }];
    const short = compactPicks(seal, base, long);
    expect(short.length).toBeLessThan(long.length);
    const reach = (p: readonly Pick[]) => applyPicks(arsenal, valves, 'seal', base, p);
    expect(reach(short)).toEqual(reach(long));
    expect(compactPicks(seal, base, [{ slot: 0, id: 62 }])).toEqual([{ slot: 0, id: 62 }]);
    // A list whose whole can't be replayed slot by slot (the C4 row is locked) still shortens by its prefix: 60 swaps
    // of the primary, then the list's own tail.
    const churn: Pick[] = Array.from({ length: 60 }, (_, i) => ({ slot: 0, id: i % 2 ? 54 : 62 }));
    const tail: Pick[] = [{ slot: 2, id: 122 }];
    const short2 = compactPicks(seal, base, [...churn, ...tail]);
    expect(short2.length).toBeLessThanOrEqual(3);
    expect(reach(short2)).toEqual(reach([...churn, ...tail]));
  });
});
