import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Group, Mesh } from 'three';
import { parseZdb, Zar, zdbMember } from '@s2u/archive';
import { FsAssetSource } from '@s2u/archive/node';
import { DEFAULT_RIFLE, EMPTY_ITEM, itemClass, readKitTable, weaponLibrary, type Loadout } from '@s2u/scene';
import { parseBankFile, weaponScriptFromArchive, weaponSounds } from '@s2u/sound';
import { defaultFireMode } from '../src/accuracy';
import { effectsFromDisc } from '../src/effectData';
import { LENS_ANIMS, lensRow, scaleColorRows, ZANIM_SCALE_COLOR } from '../src/lensFx';
import { lensColour, lensColours, nightVisionRow, setLensRows, setNightVision } from '../src/nightVision';
import { armingColour, reticleGameColour, reticleType } from '../src/reticle';
import {
  scopeBitmaps, scopeLens, scopeLevels, scopeNodeVisible, showScopeNodes, thermalFitted, THERMAL_LENS, THERMAL_SCOPE_NODE,
} from '../src/sights';
import { soundFromDisc } from '../src/soundData';
import { Zoom } from '../src/zoom';

/**
 * The sights, the sounds and the effects per weapon (web sprint 4 M5/M6; research 94 §C1.4, §C1.5, §C1.11, §C6, §C7,
 * research 84 §7-§9). The synthetic twin runs everywhere; the disc half walks every in-scope firearm of research 94
 * §C11's table through the reader and the served Frostfire (skipped without the served tree).
 */

const kit = (...ids: number[]): Loadout => {
  const l = [...ids];
  while (l.length < 5) l.push(EMPTY_ITEM);
  return l as unknown as Loadout;
};

describe('the zoom per record (research 84 section 7, research 94 section C1.4)', () => {
  it('each record\'s scope levels are ZoomMode1.. (ZoomMode0 is never a magnification) and the zoom walks them, no wrap', () => {
    const rows: { zoom: number[]; levels: number[]; walk: number[]; mags: number[] }[] = [
      { zoom: [1.5], levels: [], walk: [4, 4], mags: [9, 9] },                     // one mode: the 9x view
      { zoom: [1.5, 2.5], levels: [2.5], walk: [5, 5], mags: [2.5, 2.5] },         // the M4A1
      { zoom: [1.5, 8], levels: [8], walk: [5, 5], mags: [8, 8] },                 // the SR-25, the Dragunov
      { zoom: [1.5, 6, 12], levels: [6, 12], walk: [5, 6, 6], mags: [6, 12, 12] }, // the M40A1
      { zoom: [1.5, 8, 16], levels: [8, 16], walk: [5, 6, 6], mags: [8, 16, 16] }, // the M82A1A, the M87ELR
    ];
    for (const r of rows) {
      const record = { ...DEFAULT_RIFLE, zoomModes: r.zoom };
      expect(scopeLevels(record)).toEqual(r.levels);
      const z = new Zoom(record);
      const walk: number[] = [], mags: number[] = [];
      for (let i = 0; i < r.walk.length; i++) { walk.push(z.zoomIn()); mags.push(z.target()); }
      expect([r.zoom, walk, mags]).toEqual([r.zoom, r.walk, r.mags]);
      for (let i = r.levels.length; i > 1; i--) expect(z.zoomOut()).toBe(3 + i);   // one level down at a time
      expect(z.zoomOut()).toBe(0);
    }
  });
});

describe('the reticle set per class (FUN_005be300 L474894-474950, research 94 section C6)', () => {
  it('the view first, then a carrier in a round mode, then the id ranges', () => {
    // [weapon id, view state, magnification, the slot's fire mode, set]
    const rows: [number, number, number, number, number][] = [
      [15, 0, 1, 1, 0], [5, 0, 1, 1, 0],                         // pistols: ret_sidearm
      [31, 0, 1, 3, 1], [62, 0, 1, 2, 1], [58, 0, 1, 3, 1],      // SMG, rifles: ret_rifle
      [84, 0, 1, 1, 2], [81, 0, 1, 1, 2],                        // shotguns: ret_shotgun
      [91, 0, 1, 3, 1], [102, 0, 1, 1, 1],                       // MG, sniper unscoped: ret_rifle
      [102, 5, 6, 1, 5], [62, 5, 3, 1, 5], [102, 6, 12, 1, 5],   // any magnification over 1.01: the scope, set 5
      [58, 4, 9, 1, 7],                                          // the 9x view: ret_binocs
      [52, 0, 1, 2, 1], [61, 0, 1, 3, 1], [61, 0, 1, 4, 1],      // an M203 rifle in a rifle mode (< 5): ret_rifle
      [52, 0, 1, 175, 3], [61, 0, 1, 171, 3],                    // ... in a round mode: ret_rocket
      [63, 0, 1, 1, 1], [63, 0, 1, 183, 3],                      // the F2000 the same
      [142, 0, 1, 0, 3], [143, 0, 1, 0, 3], [145, 0, 1, 0, 3], [146, 0, 1, 0, 3],   // MGL, M79, LAW, RPG-7 always
      [52, 5, 3, 175, 5],                                        // the magnification still wins
      [121, 0, 1, 1, 4], [175, 0, 1, 1, 4], [153, 0, 1, 1, 4],   // grenades, rounds, placed: ret_grenade
      [151, 0, 1, 1, -1], [152, 0, 1, 1, -1], [141, 0, 1, 1, -1], // C4, satchel, the M203 item: none
      [195, 0, 1, 1, 0], [194, 0, 1, 1, 0], [11, 0, 1, 1, 9],    // gear 0, the designator 9
    ];
    for (const [id, state, mag, mode, want] of rows) expect([id, state, mode, reticleType(id, state, mag, mode)]).toEqual([id, state, mode, want]);
  });

  it('the grey reticle: (130, 130, 130) while the aimed point is inside the round\'s arming distance (R94.16, L70235-70257)', () => {
    // [aimed distance, arming distance (units; null: no round with one), colour]
    const rows: [number | null, number | null, string][] = [
      [50, 100, 'range'], [99.9, 100, 'range'], [100, 100, 'rest'], [400, 100, 'rest'],
      [50, null, 'rest'], [50, 0, 'rest'], [null, 100, 'rest'],
    ];
    for (const [d, arming, want] of rows) expect([d, arming, armingColour('rest', d, arming)]).toEqual([d, arming, want]);
    expect(armingColour('hostile', 50, 100)).toBe('range');       // the test overrides the target's colour (L70254)
    expect(armingColour('hostile', 500, 100)).toBe('hostile');
    expect(reticleGameColour('range')).toEqual([130, 130, 130]);
    expect(reticleGameColour('rest')).toEqual([200, 200, 24]);
  });

  it('the scope overlay: set 5\'s two bitmaps for every scoped weapon, the F2000 without ret_scope_02 (ChangeReticule)', () => {
    for (const id of [54, 62, 57, 67, 64, 66, 68, 101, 102, 103, 104, 105, 106]) expect(scopeBitmaps(id)).toEqual(['ret_scope_01.tif', 'ret_scope_02.tif']);
    expect(scopeBitmaps(63)).toEqual(['ret_scope_01.tif']);
  });
});

describe('the thermal scope (R94.15, research 94 section C7)', () => {
  it('fitted when the kit holds item 195 (FUN_005c86f0)', () => {
    expect(thermalFitted(kit(102, 15, 121, 195, 194))).toBe(true);
    expect(thermalFitted(kit(102, 15, 121, 194))).toBe(false);
  });

  it('the sniper\'s scope node swapped for thermal_scope (FUN_005b82e0 L471451-471530)', () => {
    // [loadout, held id, node, visible]
    const withIt = kit(102, 15, 195), without = kit(102, 15, 121);
    const rows: [Loadout, number, string, boolean | null][] = [
      [withIt, 102, 'scope', false], [withIt, 102, THERMAL_SCOPE_NODE, true],
      [without, 102, 'scope', true], [without, 102, THERMAL_SCOPE_NODE, false],
      [withIt, 101, 'scope', false], [withIt, 105, THERMAL_SCOPE_NODE, true],
      [kit(62, 15, 195), 62, 'scope', true], [kit(62, 15, 195), 62, THERMAL_SCOPE_NODE, false],   // no sniper: no swap
      [withIt, 102, 'remington700_high', null],                  // not a scope node: left alone
    ];
    for (const [l, id, node, want] of rows) expect([l, id, node, scopeNodeVisible(node, l, id)]).toEqual([l, id, node, want]);
    const gun = new Group();
    for (const node of ['remington700_high', 'scope', THERMAL_SCOPE_NODE]) { const m = new Mesh(); m.userData.node = node; gun.add(m); }
    showScopeNodes(gun, withIt, 102);
    expect(gun.children.map((m) => m.visible)).toEqual([true, false, true]);
    showScopeNodes(gun, without, 102);
    expect(gun.children.map((m) => m.visible)).toEqual([true, true, false]);
  });

  it('the lens a scoped view plays (FUN_001f0750 L53084-53160): thermal, else starlight at night, else the scope\'s', () => {
    const rows: [number, boolean, boolean, string | null][] = [
      [0, true, false, null], [3, true, true, null], [4, true, false, null],
      [5, true, false, THERMAL_LENS], [6, true, true, THERMAL_LENS], [12, true, false, THERMAL_LENS],
      [5, false, true, 'to_starlight_scope_lens_fx'], [5, false, false, 'to_scope_lens_fx'],
    ];
    for (const [state, thermal, night, want] of rows) expect([state, thermal, night, scopeLens(state, thermal, night)]).toEqual([state, thermal, night, want]);
  });

  it('SCALE_COLOR (zAnim command 35, FUN_00264580): a colour per flagged row, flag 0x10 all four; FUN_003b76b0 scales it', () => {
    const cmd = (flags: number, rgba: number[], seconds = 0): Uint8Array => {
      const b = new Uint8Array(28), v = new DataView(b.buffer);
      v.setUint16(0, 0, true); v.setUint32(4, flags, true);
      rgba.forEach((x, i) => v.setFloat32(8 + 4 * i, x, true));
      v.setFloat32(0x18, seconds, true);
      return b;
    };
    const blocks = [cmd(1, [0.1, 0.33, 0.7, 0]), cmd(2, [0, 0, 0, 0]), cmd(4, [0.5, 0.3, 0, 128]), cmd(8, [0.9, 0.65, 0, 50])];
    const commands = blocks.map((_, i) => ({ set: 0, cmd: ZANIM_SCALE_COLOR, offset: i * 28, size: 28 }));
    const all = new Uint8Array(28 * 4);
    blocks.forEach((b, i) => all.set(b, i * 28));
    const lens = scaleColorRows([{ commands }], (offset, length) => all.subarray(offset, offset + length));
    expect(lens.rows.map((r) => r && r.map((x) => Math.round(x * 1000) / 1000))).toEqual([[0.1, 0.33, 0.7, 0], [0, 0, 0, 0], [0.5, 0.3, 0, 128], [0.9, 0.65, 0, 50]]);
    expect(lens.seconds).toBe(0);
    const every = scaleColorRows([{ commands: [{ set: 0, cmd: ZANIM_SCALE_COLOR, offset: 0, size: 28 }] }], () => cmd(0x10, [0.2, 0.898, 0.2, 0.24]));
    expect(every.rows.every((r) => r !== null && Math.abs(r[1] - 0.898) < 1e-6)).toBe(true);
    // FUN_003b76b0: rgb x 0.33, a x 3.030303 -- the same row the night vision builds.
    expect(lensRow([0.5, 0.3, 0, 128]).map((x) => Math.round(x * 1e4) / 1e4)).toEqual([0.165, 0.099, 0, 387.8788]);
    // Command 0x5c with the draw's row (`+0x5a & 3`, FUN_003b6870): the world's row 0 cold blue, a body's row 2 bright.
    const rows = lens.rows as [number, number, number, number][];
    const world = lensColour([1, 1, 1, 1], rows, 0), body = lensColour([1, 1, 1, 1], rows, 2);
    expect(world[2]).toBeGreaterThan(world[0]);
    expect(body[0]).toBeGreaterThan(0.9);
    expect(body[0]).toBeGreaterThan(world[0] * 5);
  });

  it('the rows on the frame: the thermal\'s in, the plain scope\'s four neutral rows off (FUN_003b7170), the goggles\' all alike', () => {
    const thermal = [[0.1, 0.33, 0.7, 0], [0, 0, 0, 0], [0.5, 0.3, 0, 128], [0.9, 0.65, 0, 50]];
    setLensRows(thermal);
    expect(lensColours()).toEqual(thermal);
    expect(nightVisionRow()![2]).toBeCloseTo(0.7 * 0.33, 6);          // row 0, the world's
    setLensRows([[1, 1, 1, 0], [1, 1, 1, 0], [1, 1, 1, 0], [1, 1, 1, 0]]);   // to_scope_lens_fx's SCALE_COLOR
    expect(lensColours()).toBeNull();
    setLensRows([null, null, null, null]);                              // a lens with no SCALE_COLOR (starlight)
    expect(nightVisionRow()).toBeNull();
    setNightVision([0.2, 0.898, 0.2, 0.24]);
    expect(new Set(lensColours()!.map((c) => c.join()))).toEqual(new Set(['0.2,0.898,0.2,0.24']));
    setLensRows(null);
    expect(nightVisionRow()).toBeNull();
  });
});

// ---- off the disc: every in-scope firearm (research 94 section C11), Frostfire's banks and effects -------------------

const web = resolve(import.meta.dirname, '../../..');
const served = resolve(web, 'public/maps');
const ZWEAPON = resolve(served, 'RUN/ZWEAPON.ZAR'), MP2 = resolve(served, 'RUN/MP2.ZDB');
const onDisc = existsSync(ZWEAPON) && existsSync(MP2) && existsSync(resolve(served, 'RUN/SOUNDS/BNKSTORE.ZAR'));

/** Research 94 §C11's firearm rows (ID 4-120): id -> the note's Zoom1 and Zoom2 cells. */
function noteFirearms(): Map<number, { name: string; levels: number[] }> {
  const note = readFileSync(resolve(web, 'docs/research/94-the-arsenal.md'), 'utf8');
  const out = new Map<number, { name: string; levels: number[] }>();
  let inside = false;
  for (const line of note.split('\n')) {
    if (/^### /.test(line)) inside = line.startsWith('### C11');
    const cells = inside && line.startsWith('| ') ? line.split('|').slice(1, -1).map((c) => c.trim()) : null;
    if (!cells || !/^\d+$/.test(cells[1] ?? '') || Number(cells[1]) > 120) continue;
    out.set(Number(cells[1]), { name: cells[0]!, levels: [cells[7]!, cells[8]!].filter((c) => c !== '·').map(Number) });
  }
  return out;
}

/** The reticle set research 94 §C6 gives a class, unscoped. */
const CLASS_SET: Record<string, number> = { pistol: 0, smg: 1, rifle: 1, shotgun: 2, mg: 1, sniper: 1 };

describe.skipIf(!onDisc)('every in-scope firearm off the disc (research 94 section C11; served Frostfire)', () => {
  const bytes = (p: string): Uint8Array => new Uint8Array(readFileSync(p));
  const table = () => readKitTable(bytes(ZWEAPON));

  it('41 firearms; each resolves its zoom levels (the note\'s Zoom1/Zoom2) and its reticle set, scoped and not', () => {
    const note = noteFirearms(), t = table();
    expect(note.size).toBe(41);
    for (const [id, { name, levels }] of note) {
      const r = t.records.get(id);
      expect([id, r?.name]).toEqual([id, name]);
      expect([name, scopeLevels(r!)]).toEqual([name, levels]);
      expect([name, reticleType(id, 0, 1, defaultFireMode(r!))]).toEqual([name, CLASS_SET[itemClass(id)]]);
      if (levels.length > 0) expect([name, reticleType(id, 5, levels[0]!, defaultFireMode(r!))]).toEqual([name, 5]);
      expect([name, scopeBitmaps(id).length]).toEqual([name, 2]);
    }
  });

  it('each one\'s fire, reload (and the 870\'s after-shot) sounds are in Frostfire\'s banks; the suppressed keep no med/far', async () => {
    const note = noteFirearms(), t = table();
    const data = await soundFromDisc(new FsAssetSource(served), 'RUN/MP2.ZDB', 'MP2');
    const have = new Set<string>();
    for (const b of data.banks) for (const n of parseBankFile(b.bytes).names.keys()) if (!b.only || b.only.includes(n.trim())) have.add(n.trim());
    const script = weaponScriptFromArchive(bytes(ZWEAPON));
    for (const id of note.keys()) {
      const r = t.records.get(id)!;
      const s = weaponSounds(script, r.name)!;
      expect([r.name, data.weapons.some((w) => w.name === r.name)]).toEqual([r.name, true]);
      for (const n of [s.fireClose, s.fireMed, s.fireFar, s.reload, s.afterShot]) if (n) expect([r.name, n, have.has(n)]).toEqual([r.name, n, true]);
      expect([r.name, s.fireClose !== null, s.reload !== null]).toEqual([r.name, true, true]);
    }
    expect(weaponSounds(script, '870')!.afterShot).toBe('.SHOTGUN_COCK');
    expect(weaponSounds(script, 'M40A1')!.afterShot).toBeNull();
    for (const n of ['M4A1 SD', 'Mark 23SD', 'HK5SD', '552SD', 'SR-25 SD', '9mm Pistol']) {
      expect([n, weaponSounds(script, n)!.fireMed, weaponSounds(script, n)!.fireFar]).toEqual([n, null, null]);
    }
  }, 60_000);

  it('each one\'s FireAnimName (and its _zoom) is a Frostfire effect, its HitAnimName read; the thermal lens\'s rows read', async () => {
    const note = noteFirearms(), t = table();
    const fx = await effectsFromDisc(new FsAssetSource(served), 'RUN/MP2.ZDB', 'MP2');
    const programs = new Set(fx.programs.map((p) => p.name.toLowerCase()));
    for (const id of note.keys()) {
      const r = t.records.get(id)!;
      expect([r.name, programs.has(r.fireAnim!.toLowerCase()), programs.has(`${r.fireAnim}_zoom`.toLowerCase())]).toEqual([r.name, true, true]);
      expect([r.name, fx.hitAnims.find(([w]) => w === r.name)?.[1]]).toEqual([r.name, 'bullet_hit']);
    }
    const thermal = (fx.lenses ?? []).find(([n]) => n === THERMAL_LENS)?.[1];
    expect(LENS_ANIMS).toContain(THERMAL_LENS);
    expect(thermal!.rows.map((r) => r && r.map((x) => Math.round(x * 1000) / 1000))).toEqual([[0.1, 0.33, 0.7, 0], [0, 0, 0, 0], [0.5, 0.3, 0, 128], [0.9, 0.65, 0, 50]]);
    expect(thermal!.seconds).toBe(0);
  }, 60_000);

  it('the scope and thermal_scope nodes: on the M82A1A, M40A1, M87ELR and both SR-25s; none on the Dragunov', () => {
    const b = bytes(MP2), zdb = parseZdb(b);
    const lib = weaponLibrary(Zar.parse(zdbMember(b, zdb, 'WEAP_GEO.ZED')), Zar.parse(zdbMember(b, zdb, 'WEAP_MDL.ZED')));
    const t = table();
    const nodes = (id: number): string[] => {
      const model = t.arsenal.items.get(id)!.model!;
      return lib.decode(model, 'all').parts.map((p) => p.node).filter((n) => n === 'scope' || n === THERMAL_SCOPE_NODE).sort();
    };
    for (const id of [101, 102, 103, 105, 106]) expect([id, nodes(id)]).toEqual([id, ['scope', THERMAL_SCOPE_NODE]]);
    expect(nodes(104)).toEqual([]);
  });
});
