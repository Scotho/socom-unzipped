import { describe, expect, it } from 'vitest';
import type { RdrNode } from '@s2u/archive';
import { arsenalOf, EMPTY_ITEM, ITEM, type Loadout } from '@s2u/scene';
import { FONT_TEXT_01 } from '../src/hudFont';
import { closedMenu, step, type MenuContext, type MenuInput, type MenuState } from '../src/weaponSelectState';
import {
  drawWeaponSelect, EMPTY_SLOT_NAME_READING, menuFade, menuInputOfKey, menuInputOfPad, promptLines, weaponSelectLayout, WEAPON_SELECT_KEY_READING,
  WEAPON_SELECT_MENU_KEYS_READING, type WeaponSelectItem, type WsSprite, type WsText,
} from '../src/weaponSelect';

/**
 * WEAPON EXCHANGE drawn (research 94 §B5) over a hand-built arsenal -- `weaponSelectState.test.ts`'s, with each record's
 * `DisplayName` and `IconTextureName` -- the layout per state, the pulses and fades on the clock, the prompt's `%c` per
 * input device, the key and pad maps, and the thin draw to the HUD's quads.
 */

const rec = (...pairs: [string, RdrNode][]): RdrNode[] => pairs.flatMap(([k, v]) => [k, Array.isArray(v) ? v : [v]]);
const item = (name: string, id: number, display = name): RdrNode[] =>
  rec(['InternalName', name], ['ID', String(id)], ['DisplayName', display], ['IconTextureName', `${name.replace(/\W/g, '')}_Icon.tif`],
    ['AMMO_TYPES', []]);
const arsenal = arsenalOf(['ZAMMO', [], 'ZWEAPON', [
  item('Mark 23', 15, 'Mk23 Mod 0'), item('M9', 5), item('226', 6), item('HK5', 31), item('M4A1', 54, 'M4A1 Carbine'),
  item('M4A1-M203', 61, 'M4A1 w/M203'), item('AK-47', 58), item('870', 84), item('M40A1', 102), item('M67', 121, 'M67 Frag'),
  item('AN-M8', 122), item('HE', 126, 'HE Grenade'), item('M203', 141), item('M203 HE', 171), item('M203 FRAG', 175),
  item('Claymore', 153), item('C4', 151, 'C4 Explosive'), item('PMN Mine', 158), item('Double Ammo Load', 194, '2X Ammo'),
  item('Thermal Scope', 195),
]] as RdrNode);
const valves = new Map([
  ['Enable_Mark23', 1], ['Enable_beretta_m9', 8], ['Enable_Sig226', 8], ['Enable_mp5', 1], ['Enable_m4Acarbine', 1],
  ['Enable_m4Acarbine_203', 1], ['Enable_ak47', 8], ['Enable_870', 1], ['Enable_remington700', 9], ['Enable_frag', 9],
  ['Enable_smoke', 9], ['Enable_HEgren', 9], ['Enable_203HE', 0], ['Enable_203FRAG', 0], ['Enable_claymore', 1],
  ['Enable_c4', 16], ['Enable_pmn', 8], ['Enable_2xammo', 9], ['Enable_ThermScope', 9],
]);
const seal: MenuContext = { arsenal, valves, side: 'seal' };
const kit = (...ids: number[]): Loadout => ids as unknown as Loadout;
const drive = (s: MenuState, ...inputs: MenuInput[]): MenuState => inputs.reduce((st, i) => step(seal, st, i).state, s);

const texts = (items: WeaponSelectItem[], part: string): WsText[] =>
  items.filter((i): i is WsText => i.kind === 'text' && i.part === part);
const sprites = (items: WeaponSelectItem[], part: string): WsSprite[] =>
  items.filter((i): i is WsSprite => i.kind === 'sprite' && i.part === part);
const one = <T>(xs: T[]): T => { expect(xs).toHaveLength(1); return xs[0]!; };

const OPEN = 1;   // a second after opening: the fades are full (0.25 s)

describe('weaponSelectLayout: S2, the slot list (research 94 §B4, §B5)', () => {
  const list = drive(closedMenu(kit(54, 15, 121, 126, ITEM.C4)), 'inventory');

  it('draws the title panel, "WEAPON EXCHANGE" centred on 75 at baseline 129, and the body panel', () => {
    const { items } = weaponSelectLayout(list, seal, OPEN);
    expect(one(sprites(items, 'titlePanel'))).toMatchObject({ texture: 'newweapnbkrnd.tif', x: -10, y: 105, w: 170, h: 35, rgb: [80, 80, 80], alpha: 100 });
    expect(one(texts(items, 'title'))).toMatchObject({ text: 'WEAPON EXCHANGE', x: 75, y: 129, scale: 1, align: 'centre', rgb: [128, 128, 64], alpha: 100 });
    expect(one(sprites(items, 'body'))).toMatchObject({ x: -10, y: 140, w: 170, h: 110, rgb: [128, 128, 128] });
  });

  it('writes the five rows upper-cased at (12, 161 + 20 i), scale 0.9; the locked C4 row in (40, 40, 40)', () => {
    const rows = texts(weaponSelectLayout(list, seal, OPEN).items, 'row');
    expect(rows.map((r) => r.text)).toEqual(['M4A1 CARBINE', 'MK23 MOD 0', 'M67 FRAG', 'HE GRENADE', 'C4 EXPLOSIVE']);
    expect(rows.map((r) => [r.x, r.y, r.scale, r.align])).toEqual([0, 1, 2, 3, 4].map((i) => [12, 161 + 20 * i, 0.9, 'left']));
    expect(rows.map((r) => r.rgb)).toEqual([[128, 128, 128], [128, 128, 128], [128, 128, 128], [128, 128, 128], [40, 40, 40]]);
    const empty = drive(closedMenu(kit(54, 15, 121, EMPTY_ITEM, EMPTY_ITEM)), 'inventory');
    expect(texts(weaponSelectLayout(empty, seal, OPEN).items, 'row').map((r) => r.text)).toEqual(
      ['M4A1 CARBINE', 'MK23 MOD 0', 'M67 FRAG', EMPTY_SLOT_NAME_READING, EMPTY_SLOT_NAME_READING]);
  });

  it('puts the highlight bar on the current row (146 + 20 i, 18 high) and pulses it (80,120,120) <-> (160,250,250) at 4/s', () => {
    const down = drive(list, 'down', 'down');
    const at = (t: number): WsSprite => one(sprites(weaponSelectLayout(down, seal, t).items, 'bar'));
    expect(at(OPEN)).toMatchObject({ x: -10, y: 186, w: 170, h: 18 });
    expect(at(0.5).rgb).toEqual([80, 120, 120]);                 // the triangle's foot: a period is 0.5 s
    expect(at(0.625).rgb).toEqual([120, 185, 185]);              // half-way up
    expect(at(0.75).rgb).toEqual([160, 250, 250]);               // the peak
    expect(at(0.875).rgb).toEqual([120, 185, 185]);              // on the way down
  });

  it('previews the picker for the highlighted slot: its category, three cards, grey arrows, no card highlight', () => {
    const { items } = weaponSelectLayout(list, seal, OPEN);
    expect(one(texts(items, 'pickerHeader'))).toMatchObject({ text: 'ASSAULT RIFLES', x: 252, y: 129, scale: 1, align: 'centre', rgb: [128, 128, 64] });
    expect(one(sprites(items, 'pickerPanel'))).toMatchObject({ x: 170, y: 105, w: 170, h: 35, rgb: [80, 80, 80] });
    expect(one(sprites(items, 'pickerBody'))).toMatchObject({ x: 170, y: 140, w: 170, h: 225, rgb: [128, 128, 128] });
    expect(texts(items, 'cardName').map((c) => c.text)).toEqual(['M4A1 W/M203', 'M4A1 CARBINE', 'M4A1 W/M203']);
    const arrows = [...sprites(items, 'categoryArrow'), ...sprites(items, 'itemArrow')];
    expect(arrows).toHaveLength(4);
    for (const a of arrows) expect(a).toMatchObject({ texture: 'hud_arrow_off2.tif', rgb: [100, 100, 100] });
    expect(sprites(items, 'cardHighlight')).toEqual([]);
    const pistol = weaponSelectLayout(drive(list, 'down'), seal, OPEN).items;
    expect(one(texts(pistol, 'pickerHeader')).text).toBe('PISTOLS');
  });
});

describe('weaponSelectLayout: S3, the picker', () => {
  const picker = drive(closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'action');

  it('lays the three cards at y0 = 182 + 64 i: icon top-left (174, y0 + 2) at native size, name pen (174, y0 - 2)', () => {
    const { items } = weaponSelectLayout(picker, seal, OPEN);
    const icons = sprites(items, 'cardIcon'), names = texts(items, 'cardName');
    expect(icons.map((i) => [i.texture, i.x, i.y, i.w, i.h])).toEqual([
      ['m4a1m203_icon.tif', 174, 184, null, null], ['m4a1_icon.tif', 174, 248, null, null], ['m4a1m203_icon.tif', 174, 312, null, null],
    ]);
    expect(names.map((n) => [n.text, n.x, n.y, n.scale, n.rgb])).toEqual([
      ['M4A1 W/M203', 174, 180, 0.9, [128, 128, 128]], ['M4A1 CARBINE', 174, 244, 0.9, [128, 128, 128]],
      ['M4A1 W/M203', 174, 308, 0.9, [128, 128, 128]],
    ]);
  });

  it('blanks the side cards when the category holds one item (L88180-88184)', () => {
    const pistol = drive(closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'down', 'action');
    const { items } = weaponSelectLayout(pistol, seal, OPEN);
    expect(texts(items, 'cardName').map((n) => [n.text, n.index])).toEqual([['MK23 MOD 0', 1]]);
    expect(sprites(items, 'cardIcon').map((n) => n.index)).toEqual([1]);
  });

  it('shows the middle-card highlight (170..340, 226..290) pulsing at 4/s and holds the slot bar at (160, 250, 250)', () => {
    const at = (t: number): WeaponSelectItem[] => weaponSelectLayout(picker, seal, t).items;
    expect(one(sprites(at(OPEN), 'cardHighlight'))).toMatchObject({ texture: 'newweapnbkrnd.tif', x: 170, y: 226, w: 170, h: 64 });
    expect(one(sprites(at(1.125), 'cardHighlight')).rgb).toEqual([120, 185, 185]);
    expect(one(sprites(at(1.25), 'cardHighlight')).rgb).toEqual([160, 250, 250]);
    expect(one(sprites(at(1.125), 'bar')).rgb).toEqual([160, 250, 250]);
  });

  it('pulses the four arrows (80,80,80) -> (255,255,128) at 2/s, each pointing out of its side', () => {
    const arrows = (t: number): WsSprite[] => {
      const items = weaponSelectLayout(picker, seal, t).items;
      return [...sprites(items, 'categoryArrow'), ...sprites(items, 'itemArrow')];
    };
    for (const a of arrows(1)) expect(a.rgb).toEqual([80, 80, 80]);
    for (const a of arrows(1.25)) expect(a.rgb).toEqual([167.5, 167.5, 104]);
    for (const a of arrows(1.5)) expect(a.rgb).toEqual([255, 255, 128]);
    const [left, right, up, down] = arrows(1);
    expect([left!.x, left!.y, left!.w, left!.h, left!.turn]).toEqual([168, 105, null, null, -Math.PI / 2]);
    expect([right!.x, right!.y, right!.turn]).toEqual([305, 105, Math.PI / 2]);
    expect([up!.x, up!.y, up!.w, up!.h, up!.flipV]).toEqual([200, 140, 100, 20, false]);
    expect([down!.x, down!.y, down!.w, down!.h, down!.flipV]).toEqual([200, 344, 100, 20, true]);
  });
});

describe('the fades: 0 <-> 100 at 400/s (DAT_003dce78/80, 98/a0)', () => {
  const list = drive(closedMenu(kit(54, 15, 121, 126, 194)), 'inventory');

  it('fades in over 0.25 s after opening, everything of the menu together', () => {
    expect(menuFade('list', 0)).toBe(0);
    expect(menuFade('list', 0.125)).toBe(50);
    expect(menuFade('picker', 0.3)).toBe(100);
    const { items } = weaponSelectLayout(list, seal, 0.125);
    for (const i of items) expect(i.alpha).toBe(50);
  });

  it('fades out over 0.25 s after closing, from where it had reached; nothing when never opened', () => {
    const closed = step(seal, list, 'back').state;
    expect(menuFade('closed', 2, 0.125)).toBe(50);
    expect(menuFade('closed', 0.1, 0.05)).toBe(0);                // open 0.05 s: 20 reached, 20 gone after 0.05 s
    const fading = weaponSelectLayout(closed, seal, 2, { closedFor: 0.125 }).items;
    expect(one(texts(fading, 'title')).alpha).toBe(50);
    expect(one(sprites(fading, 'bar')).rgb).toEqual([160, 250, 250]);   // state 0: the bar's solid branch (L89431)
    expect(weaponSelectLayout(closed, seal, 2, { closedFor: 0.3 }).items).toEqual([]);
    expect(weaponSelectLayout(closedMenu(kit(54, 15, 121, 126, 194)), seal, 5).items).toEqual([]);
  });
});

describe('the prompt lines (§B2, S1 / S1g; FUN_001f97b0 L56978)', () => {
  it('writes the dead player\'s three lines centred on x 324 at baselines 380 + 18 i, scale 0.9, the %c the pad\'s R2 (0xbe)', () => {
    const lines = promptLines({ ghost: false, device: 'pad', sinceDeath: 1 });
    expect(lines.map((l) => l.text)).toEqual([
      'You have died.  R2 Select new weapons.', 'Use the UP and DOWN directional buttons', 'to cycle through living teammates',
    ]);
    expect(lines.map((l) => [l.x, l.y, l.scale, l.align, l.rgb, l.alpha])).toEqual(
      [0, 1, 2].map((i) => [324, 380 + 18 * i, 0.9, 'centre', [100, 100, 20], 100]));
    expect(lines[0]!.glyphs).toEqual([0xbe]);
    expect(lines[1]!.glyphs).toEqual([0xa3, 0xaf]);
    expect(promptLines({ ghost: false, device: 'pad', sinceDeath: 1, inventoryButton: 'R1' })[0]).toMatchObject({
      text: 'You have died.  R1 Select new weapons.', glyphs: [0xbd],
    });
  });

  it('renders the %c as the PC key and the touch button on those devices', () => {
    expect(promptLines({ ghost: false, device: 'keyboard', sinceDeath: 1 })[0]!.text).toBe(`You have died.  ${WEAPON_SELECT_KEY_READING.label} Select new weapons.`);
    expect(WEAPON_SELECT_KEY_READING.code).toBe('KeyI');
    expect(promptLines({ ghost: false, device: 'touch', sinceDeath: 1 })[0]!.text).toBe('You have died.  [INV] Select new weapons.');
  });

  it('writes the ghost\'s four lines with the same %c', () => {
    expect(promptLines({ ghost: true, device: 'keyboard', sinceDeath: 1 }).map((l) => [l.text, l.y])).toEqual([
      ['You are a ghost.  You will play the next', 380], ['round as a real player.  [I] Select new', 398],
      ['weapons. Use the UP and DOWN directional', 416], ['buttons to cycle through living teammates.', 434],
    ]);
  });

  it('holds 10 s, then fades to nothing over 0.5 s (L56544-56561)', () => {
    const alpha = (s: number): number[] => promptLines({ ghost: false, device: 'pad', sinceDeath: s }).map((l) => l.alpha);
    expect(alpha(10)).toEqual([100, 100, 100]);
    expect(alpha(10.25)).toEqual([50, 50, 50]);
    expect(alpha(10.5)).toEqual([]);
  });

  it('is drawn with the menu closed (S1) and stays up while it is open', () => {
    const prompt = { ghost: false, device: 'pad' as const, sinceDeath: 2 };
    const s1 = weaponSelectLayout(closedMenu(kit(54, 15, 121, 126, 194)), seal, 0, { prompt }).items;
    expect(s1.map((i) => i.part)).toEqual(['prompt', 'prompt', 'prompt']);
    const open = drive(closedMenu(kit(54, 15, 121, 126, 194)), 'inventory');
    expect(texts(weaponSelectLayout(open, seal, OPEN, { prompt }).items, 'prompt')).toHaveLength(3);
  });
});

describe('the keys and the pad inside the menu (§B3)', () => {
  it('maps every key WEAPON_SELECT_MENU_KEYS_READING names, and nothing else', () => {
    const expected: Record<string, MenuInput> = {
      KeyW: 'up', ArrowUp: 'up', KeyS: 'down', ArrowDown: 'down', KeyA: 'left', ArrowLeft: 'left', KeyD: 'right',
      ArrowRight: 'right', KeyX: 'action', Enter: 'action', Backspace: 'back', KeyI: 'inventory',
    };
    for (const [code, input] of Object.entries(expected)) expect(menuInputOfKey(code), code).toBe(input);
    expect(Object.keys(WEAPON_SELECT_MENU_KEYS_READING).sort()).toEqual(Object.keys(expected).sort());
    for (const code of ['Escape', 'Space', 'KeyQ', 'KeyE', 'Tab', 'KeyR', 'Digit1', 'KeyM', 'constructor']) expect(menuInputOfKey(code), code).toBeNull();
  });

  it('keeps the game\'s buttons on the pad: R2 Inventory, Cross Action, Triangle / Start back, the d-pad; Circle is no cancel', () => {
    expect(menuInputOfPad('R2')).toBe('inventory');
    expect(menuInputOfPad('Cross')).toBe('action');
    expect(menuInputOfPad('Triangle')).toBe('back');
    expect(menuInputOfPad('Start')).toBe('back');
    expect(['Up', 'Down', 'Left', 'Right'].map((b) => menuInputOfPad(b as 'Up'))).toEqual(['up', 'down', 'left', 'right']);
    for (const b of ['Circle', 'Square', 'R1', 'L1', 'L2', 'Select', 'L3', 'R3'] as const) expect(menuInputOfPad(b), b).toBeNull();
  });
});

describe('drawWeaponSelect: the layout as the HUD pass\'s quads (layer 1), as the scoreboard draws', () => {
  const SIZES: Record<string, { width: number; height: number }> = {
    'newweapnbkrnd.tif': { width: 128, height: 64 }, 'hud_arrow_off2.tif': { width: 32, height: 32 },
    'font_text_01.tif': { width: 512, height: 128 }, 'm4a1_icon.tif': { width: 128, height: 32 }, 'm4a1m203_icon.tif': { width: 128, height: 32 },
  };
  const picker = drive(closedMenu(kit(54, 15, 121, 126, 194)), 'inventory', 'action');

  it('places the panels on a 640x448 frame as laid out, stretched whole, tinted on the 0-128 scale', () => {
    const { quads } = drawWeaponSelect({ width: 640, height: 448 }, weaponSelectLayout(picker, seal, OPEN), SIZES);
    expect(quads.every((q) => q.layer === 1)).toBe(true);
    const title = quads.find((q) => q.texture === 'newweapnbkrnd.tif')!;
    expect([title.x - title.w / 2, title.y - title.h / 2, title.w, title.h]).toEqual([-10, 105, 170, 35]);
    expect([title.u0, title.v0, title.u1, title.v1]).toEqual([0, 0, 128, 64]);
    expect(title.rgba).toEqual([80 / 128, 80 / 128, 80 / 128, 100 / 128]);
  });

  it('draws an icon at its native size, the arrows turned or flipped, and scales with the frame about its centre', () => {
    const { quads } = drawWeaponSelect({ width: 1280, height: 896 }, weaponSelectLayout(picker, seal, OPEN), SIZES);
    const icon = quads.find((q) => q.texture === 'm4a1_icon.tif')!;
    expect([icon.x - icon.w / 2, icon.y - icon.h / 2, icon.w, icon.h]).toEqual([640 + (174 - 320) * 2, 248 * 2, 256, 64]);
    const arrows = quads.filter((q) => q.texture === 'hud_arrow_off2.tif');
    expect(arrows.map((a) => a.turn)).toEqual([-Math.PI / 2, Math.PI / 2, 0, 0]);
    expect([arrows[3]!.v0, arrows[3]!.v1]).toEqual([32, 0]);
    const text = quads.filter((q) => q.texture === FONT_TEXT_01.texture);
    expect(text.length).toBeGreaterThan(0);
  });

  it('skips what it has no bitmap for and what is faded out', () => {
    const { quads } = drawWeaponSelect({ width: 640, height: 448 }, weaponSelectLayout(picker, seal, OPEN), {});
    expect(quads).toEqual([]);
    const faded = drawWeaponSelect({ width: 640, height: 448 }, weaponSelectLayout(picker, seal, 0), SIZES);
    expect(faded.quads).toEqual([]);
  });
});
