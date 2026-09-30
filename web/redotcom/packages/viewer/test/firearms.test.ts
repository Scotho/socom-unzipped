import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { RdrNode } from '@s2u/archive';
import { DEFAULT_RIFLE, EMPTY_ITEM, HELD_SIDEARM, ITEM, kitTableOf, readKitTable, type KitTable, type Loadout, type WeaponRecord } from '@s2u/scene';
import {
  AFTER_SHOT_DEFAULT, afterShotLock, insideArming, KitRounds, pelletsOf, RELOAD_DELAY_DEFAULT, reloadDelayOf, roundArmingOf, roundFits,
} from '../src/firearms';
import { WalkSounds } from '../src/walkSounds';
import type { GameAudio } from '../src/audio';
import { defaultFireMode, nextFireMode, roundsPerPull } from '../src/accuracy';
import { reloadClip, reloadFamily, reloadLockSeconds, reloadSeconds } from '../src/reloadClip';
import { fragmentPart, shotgunPellets } from '../src/net/damage';

/**
 * Each firearm class's own behaviour (web sprint 4 M4; research 94 §C1-§C4): the bolt and the pump's lock, the reload's
 * delay and time, the shotgun's pellets, and the 40 mm launchers' rounds as fire modes -- the shared rules the page's
 * `Fire` and the match server's room both run. One table per concern: a synthetic twin always, the disc's records
 * when the served tree has them.
 */

const kit = (...ids: number[]): Loadout => ids as unknown as Loadout;
const record = (over: Partial<WeaponRecord>): WeaponRecord => ({ ...DEFAULT_RIFLE, ...over });

const m40 = record({ name: 'M40A1', id: 102, fireWait: 0.5, magazine: 25, mags: 1, fireModes: [1], maxFireMode: 1, reloadAfterShot: true, reloadDelayAfterShot: 0.5 });
const r870 = record({ name: '870', id: 84, fireWait: 0.75, magazine: 8, mags: 5, fireModes: [1], maxFireMode: 1, reloadAfterShot: true, reloadDelay: 1, afterShotSound: '.SHOTGUN_COCK', pellets: 4 });
const spas = record({ name: 'Spas 12', id: 81, fireWait: 0.45, magazine: 12, mags: 3, fireModes: [1], maxFireMode: 1, reloadTime: 2, reloadDelay: 0.5, pellets: 4 });
const m60 = record({ name: 'M60E3', id: 91, fireModes: [3], maxFireMode: 3, magazine: 100, mags: 2, reloadTime: 3 });
const m4203 = record({ name: 'M4A1-M203', id: ITEM.M4_203, fireModes: [1, 2, 3], maxFireMode: 3 });
const mgl = record({ name: 'MGL', id: ITEM.MGL, fireWait: 0.25, magazine: 6, mags: 2, fireModes: [], maxFireMode: 0, ammo: '', ammoId: -1 });
const frag = { name: 'M203 FRAG', id: 175, reloadAfterShot: true, reloadDelayAfterShot: 0.5 };

describe('the class keys with the parser\'s defaults (research 94 §C0 row 2)', () => {
  it.each([
    // record, ReloadDelay, after-shot lock (null: none), pellets
    [m40, RELOAD_DELAY_DEFAULT, 0.5, 1],
    [r870, 1, AFTER_SHOT_DEFAULT, 4],        // R94.12: the misspelt key leaves the 0.01 default
    [spas, 0.5, null, 4],
    [m60, RELOAD_DELAY_DEFAULT, null, 1],
    [DEFAULT_RIFLE, RELOAD_DELAY_DEFAULT, null, 1],
  ] as const)('%#: ReloadDelay %s, after-shot %s, pellets %s', (r, delay, afterShot, pellets) => {
    expect([reloadDelayOf(r), afterShotLock(r.id, r, 3, null), pelletsOf(r)]).toEqual([delay, afterShot, pellets]);
  });
});

describe('the bolt / pump lock after a round (FUN_005c5340 L479291-479343)', () => {
  it.each([
    // what, held item, the fired record, rounds left, the carrier, the lock
    ['a bolt with rounds left', 102, m40, 4, null, 0.5],
    ['the last round: the reload instead', 102, m40, 0, null, null],
    ['the pump', 84, r870, 7, null, 0.01],
    ['a rifle has none', 54, DEFAULT_RIFLE, 20, null, null],
    ['the M4A1-M203 firing a FRAG: the round\'s 0.5', ITEM.M4_203, frag, 5, ITEM.M4_203, 0.5],
    ['the MGL is excluded (L479325)', ITEM.MGL, frag, 5, ITEM.MGL, null],
    ['the M203 item in the hand is exempt (L479305-479313)', ITEM.M203, frag, 5, ITEM.M4_203, null],
  ] as const)('%s', (_what, held, fired, left, carrier, lock) => {
    expect(afterShotLock(held, fired, left, carrier)).toBe(lock);
  });
});

describe('the launcher rounds a carrier fires (FUN_003c5b20 through FUN_005c3ee0)', () => {
  it.each([
    [ITEM.M4_203, [171, 172, 173, 174, 175], [176, 179, 183, 185]],
    [ITEM.M16_203, [171, 175], [178]],
    [ITEM.MGL, [171, 173, 175], [176, 179]],
    [ITEM.M79, [176, 177, 178, 179], [171, 175]],
    [ITEM.F2000, [181, 182, 183], [175]],
    [54, [], [171, 175, 179]],
  ] as const)('carrier %i', (carrier, fits, not) => {
    for (const r of fits) expect([carrier, r, roundFits(carrier, r)]).toEqual([carrier, r, true]);
    for (const r of not) expect([carrier, r, roundFits(carrier, r)]).toEqual([carrier, r, false]);
  });
});

/** The rounds a kit holds, slot order, as the switch sees them: every kit slot with its id and whether it has rounds. */
const held = (loadout: Loadout, empty: number[] = []) => loadout.map((id, slot) => ({ slot, id, rounds: empty.includes(slot) ? 0 : 6 }));

describe('the fire-mode switch runs on into the rounds (FUN_005c4600, FUN_005c4480, FUN_005c3ee0; R94.8)', () => {
  it.each([
    // what, weapon, kit, the modes from the spawn's, one press at a time
    ['the M4A1-M203 with the FRAG the select gives', m4203, kit(61, 15, 141, 175, 194), [2, 3, 175, 1, 2, 3, 175]],
    ['three round types, in kit slot order', m4203, kit(61, 15, 171, 173, 175), [2, 3, 171, 173, 175, 1, 2]],
    // The walk restarts from the first slot of the current round and passes over only that id (FUN_005c4480 +
    // FUN_005c3ee0's `param_4`): with a type held twice around another, the game's switch never gets back to the rifle.
    ['a type held twice around another: the game\'s own loop', m4203, kit(61, 15, 175, 173, 175), [2, 3, 175, 173, 175, 173]],
    ['a round slot run dry is passed over', m4203, kit(61, 15, 171, 173, 175), [2, 3, 173, 175, 1]],
    ['the MGL comes up on its round and stays there', mgl, kit(142, 15, 175, 121, 126), [175, 175, 175]],
    ['the MGL between two round types', mgl, kit(142, 15, 175, 171, 126), [175, 171, 175]],
    ['a rifle: its own modes only', DEFAULT_RIFLE, kit(54, 15, 175, 121, 126), [2, 3, 1, 2]],
  ] as const)('%s', (what, weapon, loadout, modes) => {
    const rounds = held(loadout, what.includes('dry') ? [2] : []);
    let m = defaultFireMode(weapon, rounds);
    const seen = [m];
    for (let i = 1; i < modes.length; i++) seen.push(m = nextFireMode(weapon, m, false, rounds));
    expect(seen).toEqual(modes);
  });

  it('refused while magnified (FUN_005c4600 L478570-478575); a round mode fires one round a pull (FUN_005c0940 L476297)', () => {
    expect(nextFireMode(m4203, 3, true, held(kit(61, 15, 141, 175, 194)))).toBe(3);
    expect(roundsPerPull(175)).toBe(1);
  });
});

describe('the kit\'s round slots (the ring each round slot keeps; FUN_005c6600\'s redirect)', () => {
  const zweapon: RdrNode = ['ZAMMO', [], 'ZWEAPON', [
    ['InternalName', ['M203 FRAG'], 'ID', ['175'], 'Ammo_Capacity', ['6'], 'NumMags', ['1'], 'AMMO_TYPES', [[]]],
    ['InternalName', ['M203 HE'], 'ID', ['171'], 'Ammo_Capacity', ['6'], 'NumMags', ['1'], 'AMMO_TYPES', [[]]],
  ]];
  const table: KitTable = kitTableOf(zweapon);

  it('holds a ring per round slot at the record\'s Ammo_Capacity x NumMags (2X doubles none of them, R94.13)', () => {
    const r = new KitRounds(table, kit(61, 15, 141, 175, 194));
    expect(r.held()).toEqual([{ slot: 0, id: 61, rounds: 0 }, { slot: 1, id: 15, rounds: 0 }, { slot: 2, id: 141, rounds: 0 },
      { slot: 3, id: 175, rounds: 6 }, { slot: 4, id: 194, rounds: 0 }]);
    expect(r.ring(175)!.rounds()).toBe(6);
    expect(r.ring(171)).toBeNull();
    for (let i = 0; i < 6; i++) r.ring(175)!.fire();
    expect(r.held()[3]!.rounds).toBe(0);
    r.fill();
    expect(r.ring(175)!.rounds()).toBe(6);
  });

  it('redirects to the first slot of that round with rounds left', () => {
    const r = new KitRounds(table, kit(61, 15, 175, 171, 175));
    const first = r.ring(175)!;
    for (let i = 0; i < 6; i++) first.fire();
    expect(r.ring(175)).not.toBe(first);
    expect(r.ring(175)!.rounds()).toBe(6);
    expect(new KitRounds(null, kit(61, 15, 175, EMPTY_ITEM, EMPTY_ITEM)).held().every((h) => h.rounds === 0)).toBe(true);
  });

  it('the reticle goes grey while the aimed point is inside the round\'s arming distance (R94.16)', () => {
    expect(insideArming({ armingDistance: 100 }, [0, 0, 0], [0, 0, -99])).toBe(true);
    expect(insideArming({ armingDistance: 100 }, [0, 0, 0], [0, 0, -101])).toBe(false);
    expect(insideArming({}, [0, 0, 0], [0, 0, -1])).toBe(false);          // the smoke rounds have none
    expect(insideArming(null, [0, 0, 0], [0, 0, -1])).toBe(false);
  });
});

describe('the reload\'s clip family and length (FUN_005a82e0 L462786-462945)', () => {
  it.each([
    // what, the family's inputs, stand still, crouch still, prone, stand moving
    ['a rifle', { item: 'rifle' as const, id: 54 }, 'seal_reload', 'seal_crouch_reload', 'seal_prone_reload', 'seal_mv_reload'],
    ['a pistol', { item: 'pistol' as const, id: 15 }, 'seal_p_reload', 'seal_p_crouch_reload', 'seal_p_prone_reload', 'seal_p_mv_reload'],
    ['the 870\'s reload', { item: 'rifle' as const, id: 84 }, 'seal_reload_shotgun', 'seal_crouch_reload_shotgun', 'seal_prone_reload_shotgun', 'seal_mv_reload_shotgun'],
    ['the Spas 12\'s: the rifle\'s', { item: 'rifle' as const, id: 81 }, 'seal_reload', 'seal_crouch_reload', 'seal_prone_reload', 'seal_mv_reload'],
    ['the 870\'s after-shot: the pump', { item: 'rifle' as const, id: 84, afterShot: true }, 'seal_pump_shotgun', 'seal_crouch_pump_shotgun', 'seal_prone_pump_shotgun', 'seal_mv_pump_shotgun'],
    ['a bolt\'s after-shot: the shotgun reload', { item: 'rifle' as const, id: 102, afterShot: true }, 'seal_reload_shotgun', 'seal_crouch_reload_shotgun', 'seal_prone_reload_shotgun', 'seal_mv_reload_shotgun'],
    ['the M82A1A (101): the shotgun reload', { item: 'rifle' as const, id: 101 }, 'seal_reload_shotgun', 'seal_crouch_reload_shotgun', 'seal_prone_reload_shotgun', 'seal_mv_reload_shotgun'],
    ['the SR-25 (106): the rifle\'s', { item: 'rifle' as const, id: 106 }, 'seal_reload', 'seal_crouch_reload', 'seal_prone_reload', 'seal_mv_reload'],
    ['a round mode: Rifle m203 reload (DAT_003debf8)', { item: 'rifle' as const, id: 61, roundMode: true }, 'seal_reload_m203', 'seal_reload_m203', 'seal_reload_m203', 'seal_mv_reload'],
  ] as const)('%s', (_what, how, stand, crouch, prone, moving) => {
    const f = reloadFamily(how);
    expect([reloadClip('stand', false, f), reloadClip('crouch', false, f), reloadClip('prone', false, f), reloadClip('stand', true, f)])
      .toEqual([stand, crouch, prone, moving]);
  });

  it('ReloadTime stretches the still clip to it, not the moving one (L462940-462945: bVar3); without the clip, the placeholder', () => {
    const clips = [{ name: 'seal_reload', frameCount: 48, rate: 30 }, { name: 'seal_mv_reload', frameCount: 36, rate: 30 }] as never;
    expect(reloadSeconds(clips, null, 'stand', false, 'rifle')).toBe(1.6);
    expect(reloadSeconds(clips, null, 'stand', false, 'rifle', 2)).toBe(2);        // Spas 12 / JACKHAMMER
    expect(reloadSeconds(clips, null, 'stand', false, 'rifle', 3)).toBe(3);        // M60E3
    expect(reloadSeconds(clips, null, 'stand', true, 'rifle', 3)).toBe(1.2);       // moving: the clip's own rate
    expect(reloadLockSeconds(null, null, 'stand', false, 'rifle', 3)).toBe(3);     // the record's ReloadTime needs no clip
  });
});

describe('the 12 gauge\'s pellets on the victim (FUN_005a1620 L459317-459389, MP)', () => {
  const fixed = (...rolls: number[]): (() => number) => { let i = 0; return () => rolls[i++ % rolls.length]!; };
  it.each([
    // distance (units), the rolls, pellets: 8 inside 80 u, 4 inside 150 u, else 0; plus 1/2/4/5/6/7; thinned past 80
    [50, [0.01], 9], [50, [0.3], 12], [79, [0.99], 15],
    [100, [0.3, 0.99], Math.floor(8 * 6400 / 10000)], [100, [0.3, 0], Math.floor(8 * 6400 / 10000) + 1],
    [200, [0.6, 0.99], Math.floor(5 * 6400 / 40000)],
  ] as const)('at %i units, rolls %o: %i pellets', (d, rolls, n) => {
    expect(shotgunPellets(d, fixed(...rolls))).toBe(n);
  });

  it('each pellet strikes a part by the receiver\'s table (DAT_00650900 / DAT_006508f8: the fragments\' own)', () => {
    expect([0.1, 0.5, 0.65, 0.75, 0.85, 0.95].map((r) => fragmentPart(() => r))).toEqual([0, 3, 2, 1, 5, 4]);
  });
});

describe('the wiring to the sights and the sounds (M5/M6 hooks)', () => {
  it('the reticle\'s arming distance is the round mode\'s (R94.16), none without a round or for a smoke round', () => {
    expect([roundArmingOf({ armingDistance: 100 }), roundArmingOf({ armingDistance: 0 }), roundArmingOf(null)]).toEqual([100, null, null]);
  });

  it('the after-shot event plays the weapon\'s ReloadAfterShotSound; a volley\'s later pellets are no second report', () => {
    const calls: string[] = [];
    const audio = {
      onFire: (w: string) => { calls.push(`fire ${w}`); return null; },
      onReload: (w: string) => { calls.push(`reload ${w}`); return null; },
      onReloadAfterShot: (w: string, at: unknown) => { calls.push(`afterShot ${w} ${JSON.stringify(at)}`); return null; },
    } as unknown as GameAudio;
    const sounds = new WalkSounds(audio, { walking: () => true, feet: () => [1, 2, 3], stance: () => 'stand', wish: () => ({ forward: 0, right: 0 }), grid: () => null } as never);
    const weapon = { name: '870', id: 84, fireAnim: null, sounds: { close: null, med: null, far: null, reload: null } };
    for (let i = 0; i < 4; i++) sounds.fireEvent({ type: 'round', weapon, from: [0, 0, 0], to: [0, 0, -1], hit: false, rounds: 7, pellet: i, pellets: 4 });
    sounds.fireEvent({ type: 'afterShot', weapon, sound: '.SHOTGUN_COCK', family: 'pump', seconds: 0.8 });
    expect(calls).toEqual(['fire 870', 'afterShot 870 [1,2,3]']);
  });
});

// The disc's records (research 94 §C11), when the served tree has them.
const web = resolve(import.meta.dirname, '../../..');
const ZWEAPON = [resolve(web, 'public/maps/RUN/ZWEAPON.ZAR'), ...(process.env.SOCOM_DISC ? [resolve(process.env.SOCOM_DISC, 'RUN/ZWEAPON.ZAR')] : [])]
  .find((p) => existsSync(p));

describe.skipIf(!ZWEAPON)('each class off the disc\'s records', () => {
  const table = (): KitTable => readKitTable(new Uint8Array(readFileSync(ZWEAPON!)));

  it.each([
    // item, ReloadDelay, the after-shot lock (rounds left), pellets, ReloadTime
    [102, 0.01, 0.5, 1, undefined],     // M40A1: the bolt, 0.5 s
    [103, 0.01, 0.5, 1, undefined],     // M87ELR
    [84, 1, 0.01, 4, undefined],        // 870: the misspelt pump key's default, 4 pellets
    [81, 0.5, null, 4, 2],              // Spas 12: ReloadTime 2, ReloadDelay 0.5
    [83, 0.5, null, 4, 2],              // JACKHAMMER
    [91, 0.01, null, 1, 3],             // M60E3: ReloadTime 3
    [92, 0.01, null, 1, 2.5],           // M63A
    [101, 0.01, null, 1, undefined],    // M82A1A: no after-shot
  ] as const)('item %i', (id, delay, lock, pellets, reloadTime) => {
    const r = table().records.get(id)!;
    expect([reloadDelayOf(r), afterShotLock(id, r, 3, null), pelletsOf(r), r.reloadTime]).toEqual([delay, lock, pellets, reloadTime]);
  });

  it('the M4A1-M203\'s ring as the select fills it (61, 15, 141, 175, 194), and the MGL\'s first mode', () => {
    const t = table();
    const m4 = t.records.get(ITEM.M4_203)!, launcher = t.records.get(ITEM.MGL)!;
    const r = new KitRounds(t, kit(61, 15, 141, 175, 194));
    let m = defaultFireMode(m4, r.held());
    const seen = [m];
    for (let i = 0; i < 4; i++) seen.push(m = nextFireMode(m4, m, false, r.held()));
    expect(seen).toEqual([2, 3, 175, 1, 2]);
    expect(defaultFireMode(launcher, new KitRounds(t, kit(142, 15, 175, 121, 126)).held())).toBe(175);
    expect(r.round(175)!.record).toMatchObject({ name: 'M203 FRAG', muzzleVelocity: 270, armingDistance: 100 });
    expect(r.ring(175)!.rounds()).toBe(6);
    expect(afterShotLock(ITEM.M4_203, t.records.get(ITEM.M4_203)!, 3, null)).toBeNull();
    void HELD_SIDEARM;
  });
});
