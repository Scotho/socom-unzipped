import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { RdrNode } from '@s2u/archive';
import {
  EMPTY_ITEM, FULL_SLOT, ITEM, VALVE_OF_ITEM, applyPicks, arsenalOf, autoFill, characterWeapons, itemClass, kitTableOf, mapArsenal,
  menuValves, missionValves, pick, readArsenal, readKitTable, readMapArsenal, selectable, slotKindOf, slotLocked, valveAllows,
  type Arsenal, type Loadout,
} from '../src/arsenal';
import { DEFAULT_RIFLE, HELD_RIFLE, HELD_SIDEARM } from '../src/weapons';

/**
 * The arsenal (web sprint 4, M2; research 94 part 1). The synthetic twin is `parseRdr`'s shape, spelled the way the
 * game's files spell it; the disc-backed half reads every MP map's `READERM.ZAR` and holds each side's list against
 * research 94 §A4's table (the note is the reading, the test the proof that the code agrees with it).
 */

const rec = (...pairs: [string, RdrNode][]): RdrNode[] => pairs.flatMap(([k, v]) => [k, Array.isArray(v) ? v : [v]]);
const weapon = (name: string, id: number, extra: [string, RdrNode][] = [], ammo = '5.56 x 45mm'): RdrNode[] => rec(
  ['InternalName', name], ['DisplayName', name.toUpperCase()], ['ID', String(id)], ['NumMags', '3'], ['Ammo_Capacity', '30'],
  ['AMMO_TYPES', ammo ? [rec(['NAME', ammo])] : []], ['ModelName', name.toLowerCase()], ['IconTextureName', `${name}_icon.tif`], ...extra,
);
const zweapon: RdrNode = [
  'ZAMMO', [rec(['InternalName', '5.56 x 45mm'], ['ID', '8']), rec(['InternalName', '12 Gauge'], ['ID', '27'], ['NumProjectilesFired', '4']),
    rec(['InternalName', 'RPG Ammo'], ['ID', '42'], ['AccelerationFactor', '98'])],
  'ZWEAPON', [
    weapon('M4A1', 54), weapon('M4A1-M203', 61), weapon('AK-47', 58), weapon('M40A1', 102, [['ReloadAfterShot', []], ['ReloadDelayAfterShot', '0.5']]),
    weapon('870', 84, [['ReloadAfterShot', []], ['ReloadAfterShotDelay', '0.8']], '12 Gauge'), weapon('Mark 23', 15), weapon('M9', 5),
    weapon('M67', 121, [['Timer1', '3']]), weapon('HE', 126), weapon('Claymore', 153), weapon('PMN Mine', 158), weapon('C4', 151, [['Timer1', '6']]),
    rec(['InternalName', 'M203'], ['ID', '141'], ['AMMO_TYPES', []], ['ModelName', 'NONE']), weapon('M203 FRAG', 175, [['ArmingDistance', '10']]), weapon('M203 HE', 171),
    weapon('RPG LAUNCHER', 146, [['SlotCost', '2']], ''), weapon('RPG', 186, [['HasBackblast', []]], 'RPG Ammo'),
    weapon('Double Ammo Load', 194), weapon('Thermal Scope', 195),
  ],
];
const arsenal: Arsenal = arsenalOf(zweapon);
const valves = new Map([
  ['Enable_m4Acarbine', 1], ['Enable_m4Acarbine_203', 1], ['Enable_ak47', 8], ['Enable_remington700', 9], ['Enable_870', 1],
  ['Enable_Mark23', 1], ['Enable_beretta_m9', 8], ['Enable_frag', 9], ['Enable_HEgren', 9], ['Enable_claymore', 1],
  ['Enable_pmn', 8], ['Enable_c4', 16], ['Enable_203FRAG', 0], ['Enable_203HE', 0], ['Enable_RPG', 8], ['Enable_2xammo', 9],
  ['Enable_ThermScope', 9],
]);
const kit = (...ids: number[]): Loadout => ids as unknown as Loadout;

describe('the arsenal over a hand-built zweapon.rdr', () => {
  it('classes an item by its id range (FUN_003d1a60) and puts it in its slot kind', () => {
    expect([4, 30, 31, 51, 81, 91, 101, 121, 141, 145, 151, 171, 185, 190, 201, 205, 229, 230, 253, 254, 255].map(itemClass)).toEqual([
      'pistol', 'pistol', 'smg', 'rifle', 'shotgun', 'mg', 'sniper', 'grenade', 'grenadeLauncher', 'rocketLauncher',
      'explosive', 'launcherRound', 'rocketRound', 'gear', 'armour', 'turret', 'turret', 'turret2', 'turret2', 'internal', 'internal',
    ]);
    expect([54, 143, 15, 146, 145, 121, 195].map(slotKindOf)).toEqual(['primary', 'primary', 'secondary', 'equipment', 'equipment', 'equipment', 'equipment']);
  });

  it('reads the rare keys with the parser\'s defaults: the bolt, the misspelt pump, pellets, arming, backblast, cost', () => {
    const m40 = arsenal.byName.get('M40A1')!, r870 = arsenal.byName.get('870')!, m4 = arsenal.byName.get('M4A1')!;
    expect([m40.reloadAfterShot, m40.reloadDelayAfterShot]).toEqual([true, 0.5]);
    expect([r870.reloadAfterShot, r870.reloadDelayAfterShot, r870.projectiles]).toEqual([true, 0.01, 4]);  // R94.12, R94.10
    expect([m4.reloadAfterShot, m4.reloadDelay, m4.gravity, m4.timer1, m4.slotCost, m4.projectiles]).toEqual([false, 0.01, 98, 9999999, 1, 1]);
    expect([m4.fireWait, m40.fireWait]).toEqual([0.1, 0.1]);                    // no FireWait key: the parser's 0.1
    expect(arsenal.items.get(ITEM.M203_FRAG)!.armingDistance).toBe(100);
    expect(arsenal.items.get(ITEM.RPG_ROUND)!).toMatchObject({ hasBackblast: true, acceleration: 980 });
    expect(arsenal.items.get(ITEM.RPG7)!).toMatchObject({ slotCost: 2, ammo: null, ammoId: null });
    expect(arsenal.items.get(ITEM.M203)!.model).toBeNull();
    expect(arsenal.items.get(54)!.displayName).toBe('M4A1');
  });

  it('holds FUN_003cf1f0\'s 68 cases, the RPG-7 and its round sharing one valve', () => {
    expect(VALVE_OF_ITEM.size).toBe(68);
    expect(new Set(VALVE_OF_ITEM.values()).size).toBe(67);
    expect([VALVE_OF_ITEM.get(146), VALVE_OF_ITEM.get(186)]).toEqual(['Enable_RPG', 'Enable_RPG']);
    expect(VALVE_OF_ITEM.get(57)).toBe('Enablesig_commando');
  });

  it('gives each side its own bit: 1 the SEALs, 8 the Terrorists, 9 both; a case-different or missing valve refuses', () => {
    expect(valveAllows(valves, 'seal', 54)).toBe(true);
    expect(valveAllows(valves, 'terrorist', 54)).toBe(false);
    expect(valveAllows(valves, 'terrorist', 58)).toBe(true);
    expect(valveAllows(valves, 'seal', 102) && valveAllows(valves, 'terrorist', 102)).toBe(true);
    expect(valveAllows(new Map([['Enable_C4', 9]]), 'seal', ITEM.C4)).toBe(false);          // MP81's capital C4
    expect(valveAllows(valves, 'seal', 104)).toBe(false);                                     // no valve on the map
  });

  it('refuses the wrong slot kind, the other side\'s item, a second single item, a thermal scope without a sniper', () => {
    const k = kit(54, 15, 121, 126, 194);
    expect(selectable(valves, 'seal', k, 0, 58)).toBe(false);          // the AK-47 is the Terrorists'
    expect(selectable(valves, 'seal', k, 2, 54)).toBe(false);          // a second primary in an equipment slot
    expect(selectable(valves, 'seal', k, 1, 54)).toBe(false);          // a rifle as the sidearm
    expect(selectable(valves, 'seal', k, 3, 194)).toBe(false);         // 2X twice
    expect(selectable(valves, 'seal', k, 3, 121)).toBe(true);          // grenades may repeat
    expect(selectable(valves, 'seal', k, 3, 195)).toBe(false);         // thermal, no sniper
    expect(selectable(valves, 'seal', kit(102, 15, 121, 126, 194), 3, 195)).toBe(true);
    expect(selectable(valves, 'terrorist', kit(58, 5, 121, 126, 194), 2, 158)).toBe(true);
    expect(selectable(valves, 'seal', k, 2, 158)).toBe(false);         // the PMN is the Terrorists'
  });

  it('locks the M203, FULL_SLOT, a lone launcher round, and C4 by the side\'s 16/32 bit', () => {
    expect(slotLocked(valves, 'seal', kit(61, 15, ITEM.M203, 175, 121), 2)).toBe(true);
    expect(slotLocked(valves, 'seal', kit(54, 15, 152, FULL_SLOT, 121), 3)).toBe(true);
    expect(slotLocked(valves, 'terrorist', kit(58, 5, 146, 186, 121), 3)).toBe(true);
    expect(slotLocked(valves, 'terrorist', kit(58, 5, 186, 146, 186), 2)).toBe(false);
    expect(slotLocked(valves, 'seal', kit(54, 15, 121, 126, ITEM.C4), 4)).toBe(true);        // Enable_c4 = 16 (BREACH)
    expect(slotLocked(valves, 'terrorist', kit(58, 5, 121, 126, ITEM.C4), 4)).toBe(false);
    expect(slotLocked(valves, 'seal', kit(54, 15, 121, 126, 194), 4)).toBe(false);
  });

  it('rewrites the launcher-round valves from the primary, as the menu does on opening', () => {
    const seen = menuValves(valves, 61);
    expect([seen.get('Enable_203FRAG'), seen.get('Enable_GLFRAG'), seen.get('Enable_F2000HE')]).toEqual([9, 0, 0]);
    expect(menuValves(valves, 54).get('Enable_203FRAG')).toBe(0);
    expect(menuValves(valves, 143).get('Enable_GLHE')).toBe(9);
  });

  it('a pick: the M203 rifle brings the M203 and a FRAG; leaving, its rounds are refilled from the side\'s own items', () => {
    const on = pick(arsenal, valves, 'seal', kit(54, 15, 121, 126, 194), 0, 61);
    expect(on.loadout).toEqual([61, 15, ITEM.M203, ITEM.M203_FRAG, 194]);
    expect(on.valves.get('Enable_203HE')).toBe(9);
    const off = pick(arsenal, valves, 'seal', on.loadout, 0, 54);
    expect(off.loadout[0]).toBe(54);
    expect([off.loadout[2], off.loadout[3]].every((id) => id === EMPTY_ITEM || valveAllows(valves, 'seal', id))).toBe(true);
    expect(off.loadout.slice(2)).not.toContain(ITEM.M203);
    expect(off.valves.get('Enable_203HE')).toBe(0);
  });

  it('a cost-2 pick fills the next equipment slot with its round, 4 wrapping to 2', () => {
    expect(pick(arsenal, valves, 'terrorist', kit(58, 5, 121, 126, 194), 3, ITEM.RPG7).loadout).toEqual([58, 5, 121, ITEM.RPG7, ITEM.RPG_ROUND]);
    expect(pick(arsenal, valves, 'terrorist', kit(58, 5, 121, 126, 158), 4, ITEM.RPG7).loadout).toEqual([58, 5, ITEM.RPG_ROUND, 126, ITEM.RPG7]);
  });

  it('refills from the player\'s own side (INGAME_AUTOFILL_SIDE_READING), never the id just removed', () => {
    const id = autoFill(arsenal, valves, 'seal', kit(54, 15, EMPTY_ITEM, 126, 194), ITEM.M203_FRAG, ITEM.M203_FRAG);
    expect(id).not.toBe(ITEM.M203_FRAG);
    expect(valveAllows(valves, 'seal', id)).toBe(true);
    expect(id).not.toBe(ITEM.PMN);
  });

  it('the server replays the picks: the kit it computes, and the first refused step', () => {
    const current = kit(54, 15, 121, 126, 194);
    expect(applyPicks(arsenal, valves, 'seal', current, [])).toEqual({ loadout: current });
    expect(applyPicks(arsenal, valves, 'seal', current, [{ slot: 0, id: 102 }, { slot: 3, id: 195 }]))
      .toEqual({ loadout: [102, 15, 121, 195, 194] });
    expect(applyPicks(arsenal, valves, 'seal', current, [{ slot: 0, id: 58 }])).toEqual({ refused: 'refused', at: 0 });
    expect(applyPicks(arsenal, valves, 'seal', current, [{ slot: 2, id: 54 }])).toEqual({ refused: 'refused', at: 0 });
    expect(applyPicks(arsenal, valves, 'seal', current, [{ slot: 2, id: 999 }])).toEqual({ refused: 'unknown', at: 0 });
    expect(applyPicks(arsenal, valves, 'seal', current, [{ slot: 5, id: 121 }])).toEqual({ refused: 'slot', at: 0 });
    expect(applyPicks(arsenal, valves, 'seal', kit(54, 15, 121, 126, ITEM.C4), [{ slot: 4, id: 121 }])).toEqual({ refused: 'locked', at: 0 });
    expect(applyPicks(arsenal, valves, 'seal', current, [{ slot: 2, id: 194 }])).toEqual({ refused: 'refused', at: 0 });
  });

  it('reads the valves (first of a repeated name) and a kit through its inheritance', () => {
    const mission: RdrNode = ['Valves', [rec(['NAME', 'Enable_ak47'], ['VALUE', '8']), rec(['NAME', 'Enable_ak47'], ['VALUE', '1']), rec(['NAME', 'Enable_M16'], ['VALUE', '9'])]];
    expect([...missionValves(mission)]).toEqual([['Enable_ak47', 8], ['Enable_M16', 9]]);
    const w = (n: string): RdrNode[] => rec(['wep_name', n]);
    const character: RdrNode = ['characters', [
      'mp_seal', [...rec(['health', '50'])],
      'mp2_seal1', ':', 'mp_seal', rec(['default_weapons', [w('M4A1'), w('Mark 23'), w('M67'), w('HE'), w('Double Ammo Load')]]),
      'mp2_seal9', ':', 'mp2_seal1', rec(['health', '50']),
    ]];
    expect(characterWeapons(character, 'mp2_seal1')).toEqual(['M4A1', 'Mark 23', 'M67', 'HE', 'Double Ammo Load']);
    expect(characterWeapons(character, 'mp2_seal9')).toEqual(['M4A1', 'Mark 23', 'M67', 'HE', 'Double Ammo Load']);
    const chartype: RdrNode = ['navyseals', [rec(['name', 'Assault'], ['character', 'mp2_seal1'])], 'terrorists', []];
    const map = mapArsenal(arsenal, mission, chartype, character);
    expect(map.kits.seal).toEqual([{ type: 'Assault', character: 'mp2_seal1', loadout: [54, 15, 121, 126, 194] }]);
    expect(map.selectable.terrorist).toEqual([58]);
  });

  it('the kit table: a record for each firearm weaponRecord reads, none for equipment or a launcher with no round', () => {
    // A firearm as `weaponRecord` needs it: the rate, the range, the mark, a stance; the rest defaults.
    const firearm = (name: string, id: number): RdrNode[] => [...weapon(name, id), ...rec(
      ['FireWait', '0.12'], ['Maximum_Range', '1000'], ['DecalSet', 'BULLET_MARK_SMALL'],
      ['Reticule_Modifiers', rec(['STANCE_STAND', rec(['ReticuleKnock', '12'], ['ReticuleKnockReturn', '70'], ['ReticuleKnockMax', '45'])])],
    )];
    const script: RdrNode = ['ZAMMO', zweapon[1]!, 'ZWEAPON', [
      firearm('M4A1', 54), firearm('Mark 23', 15), weapon('M67', 121),
      rec(['InternalName', 'M203'], ['ID', '141'], ['AMMO_TYPES', []], ['ModelName', 'NONE']),
    ]];
    const table = kitTableOf(script);
    expect([...table.records.keys()]).toEqual([54, 15]);
    expect(table.records.get(54)).toMatchObject({ name: 'M4A1', id: 54, fireWait: 0.12, magazine: 30, mags: 3, ammoId: 8 });
    expect(table.arsenal.items.size).toBe(4);
    expect(table.rounds.size).toBe(0);
  });

  it('the kit table (M4): a grenade launcher carrier has its record, no round; each launched round its projectile record', () => {
    const firearm = (name: string, id: number, ammo = '5.56 x 45mm', extra: [string, RdrNode][] = []): RdrNode[] => [...weapon(name, id, extra, ammo), ...rec(
      ['FireWait', '0.25'], ['Maximum_Range', '1200'], ['DecalSet', 'BULLET_MARK_SMALL'],
      ['Reticule_Modifiers', rec(['STANCE_STAND', rec(['ReticuleKnock', '13'], ['ReticuleKnockReturn', '60'], ['ReticuleKnockMax', '70'])])],
    )];
    // A launched round as `throwableRecord` reads it (zweapon.rdr's M203 FRAG: MV 27, Arming 10, `M203 FRAG Ammo`).
    const round = (name: string, id: number, ammo: string, arming: boolean): RdrNode[] => [...weapon(name, id, [
      ['FireWait', '1'], ['Muzzle_Velocity', '27'], ['ImpactRadius', '40'], ['Effective_Range', '350'], ['Maximum_Range', '10000'],
      ['Sound_Radius', '200'], ['FireAnimName', 'm203he_start'], ['HitAnimName', 'NONE'], ['DefaultSpecialAnimName', 'frag_grenade'],
      ['SpecialMaterialAnimName', 'frag_grenade'], ['DecalSet', 'BULLET_MARK_SMALL'], ['Timer1', '10'], ['Timer2', '10.1'],
      ['ReloadAfterShot', []], ['ReloadDelayAfterShot', '0.5'], ...(arming ? [['ArmingDistance', '10'] as [string, RdrNode]] : []),
    ], ammo)];
    const script: RdrNode = [
      'ZAMMO', [...(zweapon[1] as RdrNode[]),
        rec(['InternalName', 'M203 FRAG Ammo'], ['ID', '28'], ['Piercing', '0'], ['Explosion_Damage', '10'], ['Explosion_Radius', '15']),
        rec(['InternalName', 'M203 HE Ammo'], ['ID', '20'], ['Piercing', '2'], ['Explosion_Damage', '10'], ['Explosion_Radius', '10'])],
      'ZWEAPON', [
        firearm('M4A1-M203', 61), firearm('MGL', 142, '', [['MaxFireMode', '0']]),
        rec(['InternalName', 'M203'], ['ID', '141'], ['AMMO_TYPES', []], ['ModelName', 'NONE']),
        round('M203 FRAG', 175, 'M203 FRAG Ammo', true), round('M203 HE', 171, 'M203 HE Ammo', true),
      ]];
    const table = kitTableOf(script);
    expect([...table.records.keys()]).toEqual([61, 142]);            // the MGL a carrier, the M203 (141) none
    expect(table.records.get(142)).toMatchObject({ id: 142, ammo: '', ammoId: -1, magazine: 30, mags: 3, fireModes: [], maxFireMode: 0 });
    expect([...table.rounds.keys()]).toEqual([175, 171]);
    expect(table.rounds.get(175)).toMatchObject({ piercing: 0, record: { name: 'M203 FRAG', id: 175, muzzleVelocity: 270, armingDistance: 100, impact: true, fuse: 10 } });
    expect(table.rounds.get(171)!.piercing).toBe(2);
  });
});

// The disc: the served copies (tools/extract-maps.ts), else SOCOM_DISC.
const web = resolve(import.meta.dirname, '../../..');
const onDisc = (name: string): string | undefined => [
  resolve(web, `public/maps/RUN/${name}`),
  ...(process.env.SOCOM_DISC ? [resolve(process.env.SOCOM_DISC, `RUN/${name}`)] : []),
].find((p) => existsSync(p));
const ZWEAPON = onDisc('ZWEAPON.ZAR'), READERC = onDisc('READERC.ZAR');
const MAPS = [1, 2, 5, 6, 7, 8, 9, 10, 11, 12, 51, 52, 53, 61, 62, 64, 71, 72, 73, 81, 82, 83];
const bytes = (p: string): Uint8Array => new Uint8Array(readFileSync(p));

/** Research 94 §A4's table: map number -> each side's ids. */
function noteTable(): Map<number, { seal: number[]; terrorist: number[] }> {
  const note = readFileSync(resolve(web, 'docs/research/94-the-arsenal.md'), 'utf8');
  const out = new Map<number, { seal: number[]; terrorist: number[] }>();
  for (const line of note.split('\n')) {
    const m = /^\| MP(\d+) [^|]*\| (\d+) \| ([\d ]+) \| (\d+) \| ([\d ]+) \|$/.exec(line);
    if (!m) continue;
    const ids = (s: string): number[] => s.trim().split(/\s+/).map(Number);
    const seal = ids(m[3]!), terrorist = ids(m[5]!);
    expect([seal.length, terrorist.length]).toEqual([Number(m[2]), Number(m[4])]);
    out.set(Number(m[1]), { seal, terrorist });
  }
  return out;
}

describe.skipIf(!ZWEAPON || !READERC || !MAPS.every((m) => onDisc(`MP${m}.ZDB`)))('the arsenal off the disc, all 22 MP maps', () => {
  const disc = ZWEAPON ? readArsenal(bytes(ZWEAPON)) : null;

  it('reads 86 records, 63 in scope, and every in-scope one has a class and a name', () => {
    expect(disc!.items.size).toBe(86);
    for (const id of VALVE_OF_ITEM.keys()) if (disc!.items.has(id)) expect(disc!.items.get(id)!.displayName.length).toBeGreaterThan(0);
    expect(disc!.byName.get('870')!.reloadDelayAfterShot).toBe(0.01);               // R94.12: the misspelt key
    expect(disc!.byName.get('M40A1')!.reloadDelayAfterShot).toBe(0.5);
    expect(disc!.byName.get('870')!.projectiles).toBe(4);
  });

  it('each side\'s list on each map equals research 94 §A4 (the valves through FUN_003cf1f0)', () => {
    const table = noteTable();
    expect(table.size).toBe(22);
    const readerc = bytes(READERC!);
    for (const m of MAPS) {
      const map = readMapArsenal(disc!, bytes(onDisc(`MP${m}.ZDB`)!), readerc);
      const want = table.get(m)!;
      expect([m, [...map.selectable.seal].sort((a, b) => a - b)]).toEqual([m, want.seal]);
      expect([m, [...map.selectable.terrorist].sort((a, b) => a - b)]).toEqual([m, want.terrorist]);
      expect(map.kits.seal.length).toBe(4);
      expect(map.kits.terrorist.length).toBe(4);
    }
  });

  it('Frostfire\'s kits are research 91 §14\'s; the BREACH SEALs carry the locked C4; MP6 SEAL 4 the Terrorists\' 226', () => {
    const readerc = bytes(READERC!);
    const mp2 = readMapArsenal(disc!, bytes(onDisc('MP2.ZDB')!), readerc);
    const names = (l: readonly number[]): string[] => l.filter((id) => id !== EMPTY_ITEM).map((id) => disc!.items.get(id)!.name);
    expect(names(mp2.kits.seal[0]!.loadout)).toEqual(['M4A1', 'Mark 23', 'M67', 'HE', 'Double Ammo Load']);
    expect(names(mp2.kits.terrorist[3]!.loadout)).toEqual(['M82A1A', 'Model 18', 'M67', 'PMN Mine', 'HE']);
    for (const m of [61, 62, 73]) {
      const map = readMapArsenal(disc!, bytes(onDisc(`MP${m}.ZDB`)!), readerc);
      for (const k of map.kits.seal) {
        const slot = k.loadout.indexOf(ITEM.C4);
        expect(slot).toBeGreaterThanOrEqual(2);
        expect(slotLocked(map.valves, 'seal', k.loadout, slot)).toBe(true);
      }
      expect(map.selectable.seal).not.toContain(ITEM.C4);
    }
    const mp6 = readMapArsenal(disc!, bytes(onDisc('MP6.ZDB')!), readerc);
    expect(mp6.kits.seal[3]!.loadout[1]).toBe(6);
    expect(valveAllows(mp6.valves, 'seal', 6)).toBe(false);
  });

  it('the kit table: every firearm of every kit has its record; the baked three are the file\'s; the launchers have none', () => {
    const table = readKitTable(bytes(ZWEAPON!));
    // The pistols to the snipers, less the Designator (11): 10 pistols, 5 SMGs, 15 rifles, 3 shotguns, 3 MGs, 6 snipers
    // -- and the two grenade launcher carriers read as such (M4: the MGL, the M79; R94.8), never the M203 item.
    expect(table.records.size).toBe(44);
    expect([11, ITEM.M203].some((id) => table.records.has(id))).toBe(false);
    expect(table.records.get(ITEM.MGL)).toMatchObject({ ammoId: -1, magazine: 6, mags: 2, fireModes: [] });
    expect(table.records.get(ITEM.M79)).toMatchObject({ ammoId: -1, magazine: 8, mags: 1, fireModes: [] });
    // The launched rounds (research 94 §C4.1): M203 rounds at 27 m/s, GL rounds at 40, each armed at 10 m but the smoke.
    for (const [id, mv, arming] of [[171, 270, 100], [175, 270, 100], [173, 270, undefined], [176, 400, 100], [179, 400, 100], [178, 400, undefined]] as const) {
      expect([id, table.rounds.get(id)?.record.muzzleVelocity, table.rounds.get(id)?.record.armingDistance]).toEqual([id, mv, arming]);
    }
    expect(table.records.get(62)).toEqual(HELD_RIFLE);
    expect(table.records.get(15)).toEqual(HELD_SIDEARM);
    expect(table.records.get(54)).toEqual(DEFAULT_RIFLE);
    const readerc = bytes(READERC!);
    for (const m of MAPS) {
      const map = readMapArsenal(table.arsenal, bytes(onDisc(`MP${m}.ZDB`)!), readerc);
      for (const k of [...map.kits.seal, ...map.kits.terrorist]) {
        expect([m, k.type, table.records.has(k.loadout[0]), table.records.has(k.loadout[1])]).toEqual([m, k.type, true, true]);
      }
    }
  });
});
