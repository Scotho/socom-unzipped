import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Zar, parseRdr, rdrGet, type RdrNode } from '@s2u/archive';
import {
  BULLET_MARK, DEFAULT_RIFLE, HELD_RIFLE, HELD_SIDEARM, UNITS_PER_METRE, kitWeapons, decalEntry, defaultPrimary, kitPrimaries, readBulletMark,
  readDefaultRifle, readWeapon, weaponRecord,
  type DecalEntry, type WeaponRecord,
} from '../src/weapons';

/**
 * The weapon table (web sprint 2, W2.5): `RUN/ZWEAPON.ZAR/zweapon.rdr`'s records, the SEAL's default primary out of
 * `READERC.ZAR/character.rdr`, and the bullet mark out of `READERC.ZAR/decals.rdr`. The synthetic scripts below are
 * `parseRdr`'s shape (a key string, then the list of its values), spelled the way the game's files spell them.
 */

/** A `key (value)` pair list the way `parseRdr` hands a record back. */
const rec = (...pairs: [string, RdrNode][]): RdrNode[] => pairs.flatMap(([k, v]) => [k, Array.isArray(v) ? v : [v]]);

const stance = rec(['ReticuleKnock', '12'], ['ReticuleKnockReturn', '70'], ['ReticuleKnockMax', '45'], ['TargetMin', '1']);
/** WEAPON: the standing record with its rifle kick, as the game's file spells the four keys. */
const standing = [...stance, ...rec(
  ['FireRifleKickRate', '0.5'], ['FireRifleKickReturnRate', '0.18'], ['FireRifleKickBaseDist', '0.09'], ['FireRifleKickRandomDist', '0.015'],
)];
const m4 = rec(
  ['InternalName', 'M4A1'], ['DisplayName', 'M4A1'],
  ['Reticule_Modifiers', rec(['STANCE_STAND', standing], ['STANCE_CROUCH', stance])],
  ['FireWait', '0.12'], ['Maximum_Range', '1000'], ['ID', '54'], ['NumMags', '3'],
  ['AMMO_TYPES', [rec(['NAME', '5.56 x 45mm'])]], ['Ammo_Capacity', '30'], ['DecalSet', 'BULLET_MARK_SMALL'],
  ['FireAnimName', 'muzzle_m4'], ['FireSoundClose', '.M4A1'],
);
const m16 = rec(['InternalName', 'M16A2'], ['FireWait', '0.1'], ['ID', '51']);
const zweapon: RdrNode = [
  'WEAPON_GLOBAL', rec(['SoundDistanceClose', '0']),
  'ZAMMO', [rec(['InternalName', '9x19P'], ['ID', '1']), rec(['InternalName', '5.56 x 45mm'], ['ID', '8'])],
  'ZWEAPON', [m16, m4],
];

describe('the weapon record reader over a hand-built zweapon.rdr', () => {
  it('reads the M4A1: FireWait as the interval and the rate, the magazine, the mags, the ammo by name to its ID', () => {
    expect(weaponRecord(zweapon, 'M4A1')).toMatchObject<Partial<WeaponRecord>>({
      name: 'M4A1', id: 54, fireWait: 0.12, roundsPerMinute: 500, magazine: 30, mags: 3,
      ammo: '5.56 x 45mm', ammoId: 8, piercing: 0, maximumRange: 1000, effectiveRange: 0, decalSet: 'BULLET_MARK_SMALL',
      knock: { knock: 12, knockReturn: 70, knockMax: 45 },
      // STANCE_CROUCH has no kick keys and STANCE_PRONE no node: the parser copies the stance before (0x3cda30).
      rifleKick: {
        stand: { rate: 0.5, returnRate: 0.18, baseDist: 0.09, randomDist: 0.015 },
        crouch: { rate: 0.5, returnRate: 0.18, baseDist: 0.09, randomDist: 0.015 },
        prone: { rate: 0.5, returnRate: 0.18, baseDist: 0.09, randomDist: 0.015 },
      },
      fireAnim: 'muzzle_m4',
      sounds: { close: '.M4A1', med: null, far: null, reload: null },
    });
  });

  it('reads the stances as the parser does: each starts as a copy of the one before, the constructor defaults under all', () => {
    const r = weaponRecord(zweapon, 'M4A1');
    // STANCE_STAND sets eight keys; the rest are FUN_003c59c0's: 0, Mult 1, KnockCount 3, KnockEntryStrength 1.
    expect(r.stances.stand).toMatchObject({ knock: 12, knockReturn: 70, knockMax: 45, targetMin: 1, targetMax: 0,
      dilateMoveMult: 1, knockCount: 3, knockEntry: 1, kickRate: 0.5, kickBase: 0.09, constrict: 0 });
    // STANCE_CROUCH sets the first four again over a copy of the stand; STANCE_PRONE is absent, so it is the crouch.
    expect(r.stances.crouch).toEqual(r.stances.stand);
    expect(r.stances.prone).toEqual(r.stances.crouch);
    const prone = rec(['ReticuleKnock', '8'], ['TargetDilateUponMovementMult', '63']);
    const script: RdrNode = ['ZAMMO', [rec(['InternalName', 'r'], ['ID', '1']), rec(['InternalName', 's'], ['ID', '2'])], 'ZWEAPON', [rec(
      ['InternalName', 'G'], ['FireWait', '0.1'], ['ID', '1'], ['NumMags', '1'], ['Ammo_Capacity', '1'], ['Maximum_Range', '1'],
      ['DecalSet', 'X'], ['AMMO_TYPES', [rec(['NAME', 'r'])]],
      ['Reticule_Modifiers', rec(['STANCE_STAND', stance], ['STANCE_PRONE', prone])]), m16]];
    const g = weaponRecord(script, 'G');
    expect(g.stances.prone).toMatchObject({ knock: 8, dilateMoveMult: 63, knockReturn: 70, targetMin: 1 });
  });

  it('reads the zoom table, the burst accuracy, and the fire modes MaxFireMode and the mode keys enable', () => {
    const r = weaponRecord(zweapon, 'M4A1');
    expect(r.zoomModes).toEqual([]);
    expect(r.maxFireMode).toBe(0);
    expect(r.fireModes).toEqual([]);
    const script: RdrNode = ['ZAMMO', [rec(['InternalName', 'r'], ['ID', '1']), rec(['InternalName', 's'], ['ID', '2'])], 'ZWEAPON', [rec(
      ['InternalName', 'G'], ['FireWait', '0.1'], ['ID', '1'], ['NumMags', '1'], ['Ammo_Capacity', '1'], ['Maximum_Range', '1'],
      ['DecalSet', 'X'], ['AMMO_TYPES', [rec(['NAME', 'r'])]], ['Reticule_Modifiers', rec(['STANCE_STAND', stance])],
      ['NumZoomModes', '3'], ['ZoomMode0', '1.5'], ['ZoomMode2', '12'], ['AccBurstCnt_Min', '4'], ['AccScalar_Max', '0.03'],
      ['SingleMode', []], ['AutoMode', []]), m16]];
    const g = weaponRecord(script, 'G');
    expect(g.zoomModes).toEqual([1.5, -1, 12]);      // a missing ZoomMode%d is the parser's -1
    expect(g.accuracyBurst).toEqual({ countMin: 4, countMax: 0, scalarMin: 0, scalarMax: 0.03 });
    expect(g.maxFireMode).toBe(3);                    // no MaxFireMode: 0, raised to 3 by AutoMode
    expect(g.fireModes).toEqual([1, 3]);              // the M14's pattern: single and automatic, no burst
  });

  it('refuses a weapon the table does not hold, and a record without a key, naming them', () => {
    expect(() => weaponRecord(zweapon, 'AK-47')).toThrow('AK-47');
    expect(() => weaponRecord(zweapon, 'M16A2')).toThrow(/M16A2 has no \w+/);
  });

  it('reads the default primary: the first wep_name of the first record of that name under characters', () => {
    const character: RdrNode = ['characters', [
      // The inheritance line comes first in the game's file: `mp_seal1 : mp_seal (sounds ...)`.
      'mp_seal1', ':', 'mp_seal', rec(['sounds', rec(['CHRSND_DEATH', 'x'])]),
      'basic_seal', rec(['default_weapons', [rec(['wep_name', 'M4A1-M203'])]]),
      'mp_seal1', rec(['texture_asset', 'artcseal'], ['default_weapons', [rec(['wep_name', 'M4A1']), rec(['wep_name', 'Mark 23'])]]),
      'mp_seal1', rec(['default_weapons', [rec(['wep_name', 'HK5'])]]),
    ]];
    expect(defaultPrimary(character)).toBe('M4A1');
    expect(kitPrimaries(character)).toEqual(['M4A1', 'HK5']);
    expect(() => defaultPrimary(character, 'mp_seal9')).toThrow('mp_seal9');
  });

  it('reads a decal set\'s entry for one material out of decals.rdr', () => {
    const decals: RdrNode = ['TEMP_DECAL_POOL_SIZE', ['198'], 'DECAL_SETS', [
      [rec(['SETNAME', 'GRENADE_BLAST']), rec(['MATERIALNAME', 'STONE'], ['TEXTURENAME', 'grenade_mark.tif'])],
      [rec(['SETNAME', 'BULLET_MARK_SMALL']),
        rec(['MATERIALNAME', 'SAND'], ['TEXTURENAME', 'bullet_mark_sand.tif'], ['MIN_SIZE', '1'], ['MAX_SIZE', '1.5']),
        rec(['MATERIALNAME', 'STONE'], ['TEXTURENAME', 'bullet_mark_stone.tif'], ['MIN_SIZE', '1'], ['MAX_SIZE', '1.8'])],
    ]];
    expect(decalEntry(decals, 'BULLET_MARK_SMALL', 'STONE')).toEqual<DecalEntry>(
      { set: 'BULLET_MARK_SMALL', material: 'STONE', texture: 'bullet_mark_stone.tif', minSize: 1, maxSize: 1.8 });
    expect(() => decalEntry(decals, 'BULLET_MARK_SMALL', 'GLASS')).toThrow('GLASS');
    expect(() => decalEntry(decals, 'BULLET_MARK_LARGE', 'STONE')).toThrow('BULLET_MARK_LARGE');
  });
});

// The game's own files: the served copies first (`tools/extract-maps.ts` puts them beside the maps, W2.R5), then the
// disc tree (`SOCOM_DISC`, the repository's `game/disc`, this host's main tree).
const web = resolve(import.meta.dirname, '../../..');
const onDisc = (name: string): string | undefined => [
  resolve(web, `public/maps/RUN/${name}`),
  ...(process.env.SOCOM_DISC ? [resolve(process.env.SOCOM_DISC, `RUN/${name}`)] : []),
  resolve(web, `../../game/disc/RUN/${name}`),
  `C:/projects/socom_pc/game/disc/RUN/${name}`,
].find((p) => existsSync(p));
const ZWEAPON = onDisc('ZWEAPON.ZAR'), READERC = onDisc('READERC.ZAR');
const bytes = (p: string): Uint8Array => new Uint8Array(readFileSync(p));

describe.skipIf(!ZWEAPON || !READERC)('the default rifle off the game\'s ZWEAPON.ZAR and READERC.ZAR', () => {
  it('ZWEAPON.ZAR holds one script, zweapon.rdr', () => {
    expect(Zar.parse(bytes(ZWEAPON!)).root.children.map((k) => k.name)).toEqual(['zweapon.rdr']);
  });

  it('the multiplayer SEAL\'s first kit (character.rdr mp_seal1) is the M4A1: 0.12 s a round, 30 a magazine, 3 magazines', () => {
    const rifle = readDefaultRifle(bytes(ZWEAPON!), bytes(READERC!));
    expect(rifle.name).toBe('M4A1');
    expect(rifle.fireWait).toBe(0.12);
    expect(rifle.roundsPerMinute).toBe(500);
    expect(rifle.magazine).toBe(30);
    expect(rifle.mags).toBe(3);
    expect(rifle.ammo).toBe('5.56 x 45mm');
    expect(rifle.ammoId).toBe(8);
    expect(rifle.id).toBe(54);
    // Every theatre's mp_seal1 (arctic, scuba, jungle, desert ...) hands the same rifle first.
    const zar = Zar.parse(bytes(READERC!));
    const character = parseRdr(zar.data(zar.root.children.find((k) => k.name === 'character.rdr')!));
    const kits = kitPrimaries(character);
    expect(kits.length).toBeGreaterThanOrEqual(4);
    expect(new Set(kits)).toEqual(new Set(['M4A1']));
  });

  it('is the transcription: DEFAULT_RIFLE, HELD_RIFLE and BULLET_MARK are the files\', proven each run that has them', () => {
    expect(readDefaultRifle(bytes(ZWEAPON!), bytes(READERC!))).toEqual(DEFAULT_RIFLE);
    expect(readWeapon(bytes(ZWEAPON!), 'M4A1 SD')).toEqual(HELD_RIFLE);
    expect(readBulletMark(bytes(READERC!), DEFAULT_RIFLE.decalSet)).toEqual(BULLET_MARK);
  });

  it('is the transcription: HELD_SIDEARM is the file Mark 23, the second weapon of the mp_seal1 kit', () => {
    expect(readWeapon(bytes(ZWEAPON!), 'Mark 23')).toEqual(HELD_SIDEARM);
    const zar = Zar.parse(bytes(READERC!));
    const character = parseRdr(zar.data(zar.root.children.find((k) => k.name === 'character.rdr')!));
    expect(kitWeapons(character)).toEqual(['M4A1', 'Mark 23', 'M67', 'HE', 'Double Ammo Load']);
    expect(kitWeapons(character, 'mp2_seal1')[1]).toBe(HELD_SIDEARM.name);
  });

  it('is the transcription: HELD_RIFLE is the file M4A1 SD, the rifle the SEAL holds', () => {
    const zar = Zar.parse(bytes(ZWEAPON!));
    const script = parseRdr(zar.data(zar.root.children.find((k) => k.name.toLowerCase() === 'zweapon.rdr')!));
    expect(weaponRecord(script, 'M4A1 SD')).toEqual(HELD_RIFLE);
  });

  it('the M16A2 beside it reads its own numbers (the reader is not the transcription)', () => {
    const script = parseRdr(Zar.parse(bytes(ZWEAPON!)).data(Zar.parse(bytes(ZWEAPON!)).root.children[0]!));
    expect(weaponRecord(script, 'M16A2')).toMatchObject({ fireWait: 0.1, magazine: 30, mags: 4, ammoId: 8, id: 51 });
  });

  it('the M4A1 SD zooms to 3; every weapon has ZoomMode0 1.5; the ranges are metres, 10 units each', () => {
    const sd = readWeapon(bytes(ZWEAPON!), 'M4A1 SD');
    expect(sd.zoomModes).toEqual([1.5, 3]);
    expect(sd.stances.crouch.targetMin).toBe(0.75);
    expect(sd.maximumRange * UNITS_PER_METRE).toBe(8000);   // DAT_003dfe10: 10 units a metre
    const zar = Zar.parse(bytes(ZWEAPON!));
    const script = parseRdr(zar.data(zar.root.children[0]!)) as RdrNode[];
    const list = script[script.indexOf('ZWEAPON') + 1] as RdrNode[][];
    for (const r of list) {
      const name = (r[r.indexOf('InternalName') + 1] as string[])[0]!;
      expect(rdrGet(r, 'ZoomMode0'), name).toBe('1.5');
    }
  });

  it('the kit sidearm, the Mark 23 (ID 15, the sidearm reticle): one fire mode, one zoom mode, no kick, prone inherits', () => {
    const m23 = readWeapon(bytes(ZWEAPON!), 'Mark 23');
    expect(m23).toMatchObject({ id: 15, fireWait: 0.2, magazine: 12, ammo: '45 ACP', piercing: 4, maximumRange: 125,
      zoomModes: [1.5], maxFireMode: 1, fireModes: [1], rifleKick: { stand: null, crouch: null, prone: null } });
    expect(m23.stances.stand).toMatchObject({ knock: 20, knockReturn: 60, knockMax: 40, dilateFire: 20, dilateMove: 0.75,
      constrict: 75, targetMin: 10, targetMax: 30, knockCount: 1, knockEntry: 1 });
    expect(m23.stances.prone).toMatchObject({ knock: 20, targetMin: 14, targetMax: 34, dilateMoveMult: 60 });
  });
});

// ---- web sprint 4, M4: each firearm class's own keys (research 94 §C1.1, §C1.2, §C2.1, §C4) ---------------------------

/** A firearm record with the class keys a test adds (the parser's names: `FUN_003cda30` L322538-322556). */
const classRecord = (name: string, id: number, extra: [string, RdrNode][] = [], ammo = '5.56 x 45mm'): RdrNode[] => rec(
  ['InternalName', name], ['FireWait', '0.5'], ['ID', String(id)], ['NumMags', '3'], ['Ammo_Capacity', '8'], ['Maximum_Range', '84'],
  ['DecalSet', 'BULLET_MARK_SMALL'], ['AMMO_TYPES', ammo ? [rec(['NAME', ammo])] : []], ['Reticule_Modifiers', rec(['STANCE_STAND', stance])],
  ...extra,
);
const classes: RdrNode = [
  'ZAMMO', [rec(['InternalName', '5.56 x 45mm'], ['ID', '8']), rec(['InternalName', '12 Gauge'], ['ID', '27'], ['NumProjectilesFired', '4'])],
  'ZWEAPON', [
    classRecord('M40A1', 102, [['ReloadAfterShot', []], ['ReloadDelayAfterShot', '0.5']]),
    // The 870's own spelling: `ReloadAfterShotDelay`, a key the parser has no string for (R94.12).
    classRecord('870', 84, [['ReloadAfterShot', []], ['ReloadAfterShotDelay', '0.8'], ['ReloadDelay', '1'], ['ReloadAfterShotSound', '.SHOTGUN_COCK']], '12 Gauge'),
    classRecord('Spas 12', 81, [['ReloadTime', '2'], ['ReloadDelay', '0.5']], '12 Gauge'),
    classRecord('M60E3', 91, [['ReloadTime', '3'], ['AutoMode', []]]),
    classRecord('MGL', 142, [['MaxFireMode', '0']], ''),
    m4,
  ],
];

describe('the class keys a firearm record carries (web sprint 4 M4; research 94 §C1, §C2.1)', () => {
  it.each([
    // name, ReloadTime, ReloadDelay, ReloadAfterShot, ReloadDelayAfterShot, the after-shot sound, pellets
    ['M40A1', undefined, undefined, true, 0.5, undefined, undefined],
    ['870', undefined, 1, true, undefined, '.SHOTGUN_COCK', 4],
    ['Spas 12', 2, 0.5, undefined, undefined, undefined, 4],
    ['M60E3', 3, undefined, undefined, undefined, undefined, undefined],
    ['M4A1', undefined, undefined, undefined, undefined, undefined, undefined],
  ] as const)('%s: ReloadTime %s, ReloadDelay %s, the bolt/pump %s after %s, sound %s, pellets %s -- only the keys it has',
    (name, reloadTime, reloadDelay, reloadAfterShot, reloadDelayAfterShot, afterShotSound, pellets) => {
      const r = weaponRecord(classes, name);
      expect([r.reloadTime, r.reloadDelay, r.reloadAfterShot, r.reloadDelayAfterShot, r.afterShotSound, r.pellets])
        .toEqual([reloadTime, reloadDelay, reloadAfterShot, reloadDelayAfterShot, afterShotSound, pellets]);
      // An absent key is absent, not a default: the baked records (DEFAULT_RIFLE ...) stay the file's, deep-equal.
      for (const k of ['reloadTime', 'reloadDelay', 'reloadAfterShot', 'reloadDelayAfterShot', 'afterShotSound', 'pellets'] as const) {
        if (r[k] === undefined) expect(Object.hasOwn(r, k), `${name} ${k}`).toBe(false);
      }
    });

  it('a grenade launcher (no AMMO_TYPES round) is read only when asked for as a carrier: no round, no firearm mode', () => {
    expect(() => weaponRecord(classes, 'MGL')).toThrow('AMMO_TYPES');
    const mgl = weaponRecord(classes, 'MGL', { carrier: true });
    expect(mgl).toMatchObject({ name: 'MGL', id: 142, ammo: '', ammoId: -1, magazine: 8, mags: 3, maxFireMode: 0, fireModes: [] });
  });
});

describe.skipIf(!ZWEAPON)('the class keys off the disc (research 94 §C11)', () => {
  it.each([
    ['M40A1', { reloadAfterShot: true, reloadDelayAfterShot: 0.5 }],
    ['M87ELR', { reloadAfterShot: true, reloadDelayAfterShot: 0.5 }],
    ['870', { reloadAfterShot: true, reloadDelay: 1, afterShotSound: '.SHOTGUN_COCK', pellets: 4 }],
    ['Spas 12', { reloadTime: 2, reloadDelay: 0.5, pellets: 4 }],
    ['JACKHAMMER', { reloadTime: 2, reloadDelay: 0.5, pellets: 4 }],
    ['M60E3', { reloadTime: 3 }],
    ['M63A', { reloadTime: 2.5 }],
  ] as const)('%s reads %o', (name, keys) => {
    expect(readWeapon(bytes(ZWEAPON!), name)).toMatchObject(keys);
  });

  it('the 870 keeps the parser\'s after-shot default: its ReloadAfterShotDelay is no key the game reads (R94.12)', () => {
    expect(readWeapon(bytes(ZWEAPON!), '870').reloadDelayAfterShot).toBeUndefined();
  });

  it('the MGL and the M79 read as carriers: the record\'s magazine, no firearm mode', () => {
    const zar = Zar.parse(bytes(ZWEAPON!));
    const script = parseRdr(zar.data(zar.root.children[0]!));
    expect(weaponRecord(script, 'MGL', { carrier: true })).toMatchObject({ id: 142, magazine: 6, mags: 2, fireWait: 0.25, fireModes: [] });
    expect(weaponRecord(script, 'M79', { carrier: true })).toMatchObject({ id: 143, magazine: 8, mags: 1, fireWait: 1.5, fireModes: [] });
  });
});
