import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { RdrNode } from '@s2u/archive';
import { FsAssetSource } from '@s2u/archive/node';
import {
  arsenalOf, DEFAULT_RIFLE, DEFAULT_SIDEARM, DEFAULT_WEAPON, EMPTY_ITEM, HE, HELD_RIFLE, HELD_SIDEARM, M67,
  type KitTable, type Loadout, type MapArsenal, type WeaponRecord,
} from '@s2u/scene';
import {
  BAKED_ICONS, BAKED_LOADOUT, kitParam, kitRecords, loadKitSource, PlayerLoadout, simKitsFromBytes, slotIcon, slotModel, slotRecord,
  typeLoadout,
} from '../src/loadout';

/**
 * The runtime kit (web sprint 4, M3/M4): a `Loadout` of five ids is the kit's state; the two firearm slots' records,
 * held models and HUD icons follow it, 2X doubles the firearms' magazines (research 94 §A7), and a pick waits for the
 * next spawn (R94.3). The synthetic twin runs always; the disc half reads Frostfire's kits.
 */

const rec = (...pairs: [string, RdrNode][]): RdrNode[] => pairs.flatMap(([k, v]) => [k, Array.isArray(v) ? v : [v]]);
const item = (name: string, id: number, model: string | null, icon: string | null): RdrNode[] => rec(
  ['InternalName', name], ['ID', String(id)], ['NumMags', '3'], ['Ammo_Capacity', '30'], ['AMMO_TYPES', []],
  ...(model ? [['ModelName', model] as [string, RdrNode]] : []), ...(icon ? [['IconTextureName', icon] as [string, RdrNode]] : []),
);
const arsenal = arsenalOf(['ZAMMO', [], 'ZWEAPON', [
  item('M4A1', 54, 'm4Acarbine', 'm4carbine_icon.tif'), item('M4A1 SD', 62, 'm4Acarbine_sd', 'm4carbineSD_icon.tif'),
  item('Mark 23', 15, 'a_mark23', 'mark23_icon.tif'), item('MP5K', 38, 'hk5k', 'hk5k_icon.tif'), item('M9', 5, 'baretta_m9', 'gun_baretta_9mm_icon.tif'),
  item('552', 57, 'sig_commando', 'sigcommando_icon.tif'), item('MGL', 142, 'mglmk1', 'mglmk1_icon.tif'), item('M67', 121, 'grenade', 'grenade_frag_icon.tif'),
  item('HE', 126, 'HEgrenade', 'grenade_he_icon.tif'), item('Double Ammo Load', 194, null, 'double_ammo_icon.tif'),
]]);
const mp5k: WeaponRecord = { ...DEFAULT_RIFLE, name: 'MP5K', id: 38, mags: 6 };
const m9: WeaponRecord = { ...HELD_SIDEARM, name: 'M9', id: 5 };
const r552: WeaponRecord = { ...DEFAULT_RIFLE, name: '552', id: 57 };
const table: KitTable = { arsenal, records: new Map([[54, DEFAULT_RIFLE], [62, HELD_RIFLE], [15, HELD_SIDEARM], [38, mp5k], [5, m9], [57, r552]]), rounds: new Map() };
const kit = (...ids: number[]): Loadout => ids as unknown as Loadout;
const map: MapArsenal = {
  valves: new Map(), selectable: { seal: [], terrorist: [] },
  kits: {
    seal: [{ type: 'Seal1', character: 'mp2_seal1', loadout: kit(54, 15, 121, 126, 194) }, { type: 'Seal2', character: 'mp2_seal2', loadout: kit(38, 15, 121, 126, 255) }],
    terrorist: [{ type: 'Terrorist1', character: 'mp2_terror1', loadout: kit(57, 5, 121, 126, 194) }],
  },
};

describe('the kit\'s two firearm slots follow the loadout', () => {
  it.each([
    // [what, table, loadout, slot 0's name and mags, slot 1's name and mags]
    ['no ZWEAPON.ZAR: the baked pair', null, BAKED_LOADOUT, ['M4A1 SD', 3], ['Mark 23', 3]],
    ['the type\'s kit with 2X: both firearms doubled (FUN_005c75f0)', table, kit(54, 15, 121, 126, 194), ['M4A1', 6], ['Mark 23', 6]],
    ['without 2X: NumMags as read', table, kit(54, 15, 121, 126, EMPTY_ITEM), ['M4A1', 3], ['Mark 23', 3]],
    ['2X in any equipment slot', table, kit(62, 5, 194, 121, 126), ['M4A1 SD', 6], ['M9', 6]],
    ['2X caps at the ring\'s ten magazines', table, kit(38, 15, 194, EMPTY_ITEM, EMPTY_ITEM), ['MP5K', 10], ['Mark 23', 6]],
    ['a slot with no firearm record keeps the baked one', table, kit(142, EMPTY_ITEM, 121, 126, EMPTY_ITEM), ['M4A1 SD', 3], ['Mark 23', 3]],
  ] as const)('%s', (_what, t, loadout, primary, secondary) => {
    const [rifle, pistol] = kitRecords(t, loadout);
    expect([rifle.name, rifle.mags]).toEqual(primary);
    expect([pistol.name, pistol.mags]).toEqual(secondary);
    expect(slotRecord(t, loadout, 0)).toEqual(rifle);
  });

  it('keeps the record\'s own numbers but the magazines, and never touches the table\'s copy', () => {
    const [rifle] = kitRecords(table, kit(54, 15, 121, 126, 194));
    expect({ ...rifle, mags: 3 }).toEqual(DEFAULT_RIFLE);
    expect(DEFAULT_RIFLE.mags).toBe(3);
  });

  it.each([
    // [what, table, loadout, slot 0's model and icon, slot 1's model and icon]
    ['the baked pair', null, BAKED_LOADOUT, [DEFAULT_WEAPON, BAKED_ICONS[0]], [DEFAULT_SIDEARM, BAKED_ICONS[1]]],
    ['the records\' ModelName and IconTextureName', table, kit(57, 5, 121, 126, 194), ['sig_commando', 'sigcommando_icon.tif'], ['baretta_m9', 'gun_baretta_9mm_icon.tif']],
    ['a launcher holds its own model; an empty slot holds nothing', table, kit(142, EMPTY_ITEM, 121, 126, 194), ['mglmk1', 'mglmk1_icon.tif'], [null, null]],
  ] as const)('models and icons: %s', (_what, t, loadout, primary, secondary) => {
    expect([slotModel(t, loadout, 0), slotIcon(t, loadout, 0)]).toEqual(primary);
    expect([slotModel(t, loadout, 1), slotIcon(t, loadout, 1)]).toEqual(secondary);
  });

  it('the baked loadout is the baked records\' and the throwables\' own ids', () => {
    expect(BAKED_LOADOUT).toEqual([HELD_RIFLE.id, HELD_SIDEARM.id, M67.id, HE.id, EMPTY_ITEM]);
  });
});

describe('the spawn kit: the character type\'s default_weapons, a pick at the next spawn', () => {
  it('spawns each side with its first type\'s kit (DEFAULT_CHARTYPE_PLACEHOLDER), or the baked one', () => {
    expect(typeLoadout(map, 'seal')).toEqual([54, 15, 121, 126, 194]);
    expect(typeLoadout(map, 'terrorist')).toEqual([57, 5, 121, 126, 194]);
    expect(typeLoadout(null, 'seal')).toBeNull();
    const l = new PlayerLoadout();
    expect(l.spawn('seal')).toEqual(BAKED_LOADOUT);
    l.setMap(table, map);
    expect(l.spawn('seal')).toEqual([54, 15, 121, 126, 194]);
    expect(l.spawn('terrorist')).toEqual([57, 5, 121, 126, 194]);
    expect(l.records().map((r) => r.name)).toEqual(['552', 'M9']);
  });

  it('a pick waits for the next spawn, is the side\'s own, and stays until changed (R94.3)', () => {
    const l = new PlayerLoadout();
    l.setMap(table, map);
    l.spawn('seal');
    l.setLoadout(kit(38, 15, 121, 126, 255), 'seal');
    expect(l.loadout()).toEqual([54, 15, 121, 126, 194]);                 // not before the spawn
    expect(l.pending('seal')).toEqual([38, 15, 121, 126, 255]);
    expect(l.spawn('seal')).toEqual([38, 15, 121, 126, 255]);
    expect(l.spawn('seal')).toEqual([38, 15, 121, 126, 255]);             // kept on the type
    expect(l.spawn('terrorist')).toEqual([57, 5, 121, 126, 194]);         // the other side's type has its own
    l.setMap(table, map);                                                // a new map: a new match, the types' own kits
    expect(l.spawn('seal')).toEqual([54, 15, 121, 126, 194]);
  });

  it('the developer\'s kit (&kit=) is every side\'s pick on every map until a pick replaces it', () => {
    const l = new PlayerLoadout();
    l.setDevKit(kit(62, 15, 121, 126, 255));
    l.setMap(table, map);
    expect(l.spawn('seal')).toEqual([62, 15, 121, 126, 255]);
    expect(l.spawn('terrorist')).toEqual([62, 15, 121, 126, 255]);
    expect(l.pending('seal')).toEqual([62, 15, 121, 126, 255]);
    l.setLoadout(kit(54, 15, 121, 126, 255), 'seal');
    expect(l.spawn('seal')).toEqual([54, 15, 121, 126, 255]);
    l.setMap(table, map);
    expect(l.spawn('seal')).toEqual([62, 15, 121, 126, 255]);
  });

  it('against a network server the pick waits: the type\'s kit, as the room gives it, until M9 carries a request', () => {
    const l = new PlayerLoadout();
    l.setDevKit(kit(62, 15, 121, 126, 255));
    l.setMap(table, map);
    l.setLoadout(kit(38, 15, 121, 126, 255), 'seal');
    expect(l.spawn('seal', { network: true })).toEqual([54, 15, 121, 126, 194]);
    expect(l.spawn('terrorist', { network: true })).toEqual([57, 5, 121, 126, 194]);
    expect(l.pending('seal')).toEqual([38, 15, 121, 126, 255]);          // kept for the page's own match
    expect(l.spawn('seal')).toEqual([38, 15, 121, 126, 255]);
  });

  it('protocol 7: a match\'s spawn carries the room\'s kit, which the page takes whatever it holds', () => {
    const l = new PlayerLoadout();
    l.setMap(table, map);
    l.setLoadout(kit(38, 15, 121, 126, 255), 'seal');
    expect(l.spawn('seal', { network: true, kit: [62, 5, 121, 126, 194] })).toEqual([62, 5, 121, 126, 194]);
    expect(l.records().map((r) => [r.name, r.mags])).toEqual([['M4A1 SD', 6], ['M9', 6]]);
    expect(l.spawn('seal', { network: true, kit: [1, 2, 3] })).toEqual([54, 15, 121, 126, 194]);   // not five ids: the type's own
  });

  it.each([
    ['?kit=62,15,121,126,255', [62, 15, 121, 126, 255]],
    ['?map=MP2&kit=62,15&devmode', [62, 15, EMPTY_ITEM, EMPTY_ITEM, EMPTY_ITEM]],
    ['?kit=', null], ['?kit=62,x', null], ['?kit=62,300', null], ['?kit=1,2,3,4,5,6', null], ['?map=MP2', null], ['?kit=-1', null],
  ] as const)('reads the developer\'s &kit= %s', (search, want) => {
    expect(kitParam(search)).toEqual(want);
  });
});

// The disc: the served copies (tools/extract-maps.ts), else SOCOM_DISC.
const web = resolve(import.meta.dirname, '../../..');
const onDisc = (name: string): string | undefined => [
  resolve(web, `public/maps/RUN/${name}`),
  ...(process.env.SOCOM_DISC ? [resolve(process.env.SOCOM_DISC, `RUN/${name}`)] : []),
].find((p) => existsSync(p));
const root = onDisc('ZWEAPON.ZAR') && onDisc('READERC.ZAR') && onDisc('MP2.ZDB') ? resolve(onDisc('ZWEAPON.ZAR')!, '../..') : undefined;

describe.skipIf(!root)('the runtime kit off the disc: Frostfire', () => {
  it('reads the tables once a source, and each side spawns with its type\'s kit, 2X doubling the firearms', async () => {
    const source = new FsAssetSource(root!);
    const kits = await loadKitSource(source);
    expect(kits).not.toBeNull();
    expect(await loadKitSource(source)).toBe(kits);                        // one read a source
    const sim = simKitsFromBytes(kits!, new Uint8Array(readFileSync(onDisc('MP2.ZDB')!)));
    const seal = typeLoadout(sim.map, 'seal')!, terrorist = typeLoadout(sim.map, 'terrorist')!;
    expect(kitRecords(sim.table, seal).map((r) => [r.name, r.mags])).toEqual([['M4A1', 6], ['Mark 23', 6]]);
    expect(kitRecords(sim.table, terrorist).map((r) => [r.name, r.mags])).toEqual([['552', 6], ['M9', 6]]);
    expect([slotModel(sim.table, seal, 0), slotIcon(sim.table, seal, 0)]).toEqual(['m4Acarbine', 'm4carbine_icon.tif']);
    expect([slotModel(sim.table, terrorist, 1), slotIcon(sim.table, terrorist, 1)]).toEqual(['baretta_m9', 'gun_baretta_9mm_icon.tif']);
  });
});

describe('protocol 7: the side\'s confirmed picks, the list the room replays (M9)', () => {
  it('keeps each side\'s picks since the map, in order, from the type\'s kit (or the developer\'s); a new map clears them', () => {
    const l = new PlayerLoadout();
    l.setMap(table, map);
    expect(l.base('seal')).toEqual([54, 15, 121, 126, 194]);
    expect(l.picks('seal')).toEqual([]);
    expect(l.confirm('seal', { slot: 0, id: 38 })).toEqual([{ slot: 0, id: 38 }]);
    expect(l.confirm('seal', { slot: 1, id: 5 })).toEqual([{ slot: 0, id: 38 }, { slot: 1, id: 5 }]);
    expect(l.picks('terrorist')).toEqual([]);
    l.setDevKit(kit(62, 15, 121, 126, 255));
    expect(l.base('terrorist')).toEqual([62, 15, 121, 126, 255]);
    expect(l.devKit()).toEqual([62, 15, 121, 126, 255]);
    l.setMap(table, map);
    expect(l.picks('seal')).toEqual([]);
  });

  it('the room\'s answer is the side\'s next kit (pending), shown by the menu, taken at the next spawn', () => {
    const l = new PlayerLoadout();
    l.setMap(table, map);
    l.answer('seal', [38, 15, 121, 126, 194]);
    expect(l.pending('seal')).toEqual([38, 15, 121, 126, 194]);
    expect(l.spawn('seal')).toEqual([38, 15, 121, 126, 194]);
    l.answer('seal', [1, 2]);                                             // not a kit: nothing changes
    expect(l.pending('seal')).toEqual([38, 15, 121, 126, 194]);
  });

  it('a refusal drops the refused pick and those after it, so the next request is not refused again', () => {
    const l = new PlayerLoadout();
    l.setMap(table, map);
    l.confirm('seal', { slot: 0, id: 38 });
    l.confirm('seal', { slot: 1, id: 5 });
    l.confirm('seal', { slot: 2, id: 126 });
    l.refused('seal', 1);
    expect(l.picks('seal')).toEqual([{ slot: 0, id: 38 }]);
    l.refused('seal', 5);                                                 // past the list: nothing to drop
    expect(l.picks('seal')).toEqual([{ slot: 0, id: 38 }]);
  });
});
