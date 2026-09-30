import { describe, expect, it } from 'vitest';
import {
  CLAYMORE, DEFAULT_RIFLE, HELD_SIDEARM, M67, arsenalOf, type CollisionOwner, type GridParams, type Loadout, type SpawnSlot,
  type ThrowableRecord, type WorldPoly,
} from '@s2u/scene';
import {
  encodeCommands, EYE_HEIGHT, groundGrid, packGround, PROTOCOL_VERSION, TICK_HZ, type Command, type ServerEvent, type SimKits, type SimMap,
} from '../../viewer/src/sim';
import { Room, type Conn } from '../src/room';

/**
 * The equipment in the match (web sprint 4, M7; research 94 §C4-§C5, research 85 §9): the room flies the rockets and
 * deals both their blasts, sets the placed charges down and off -- the claymore by its Detonator, the PMN by an actor
 * once armed, C4 at its timer on a C4 target only -- and takes the pouch from the loadout. On a synthetic floor and a
 * hand-built kit table, as `roomBlast.test.ts`.
 */

const PARAMS: GridParams = { atomCount: 8192, posts: 16, cellDim: 200, cellsX: 10, cellsZ: 10, originX: -1000, originZ: -1000 };
const FLOOR: WorldPoly = {
  modelName: 'worldmodel', path: 'worldmodel/floor', region: 0, ditype: 3, material: 25, ptcount: 4, cameratype: 0,
  points: Float32Array.from([-1000, 0, -1000, 1000, 0, -1000, 1000, 0, 1000, -1000, 0, 1000]),
};
/** The flat map, a wall across x = 600 (the rockets' stop), and one C4 target at (0, 0, 300). */
function map(): SimMap {
  const polys: WorldPoly[] = [FLOOR, { ...FLOOR, path: 'worldmodel/wall', ditype: 2, points: Float32Array.from([600, 0, -400, 600, 0, 400, 600, 200, 400, 600, 200, -400]) }];
  const owners: CollisionOwner[] = [
    { modelName: 'worldmodel', path: 'worldmodel/floor0', first: 0, count: 1 }, { modelName: 'worldmodel', path: 'worldmodel/wall0', first: 1, count: 1 },
  ];
  const ground = packGround(PARAMS, polys, owners);
  const slot = (side: 0 | 1, index: number, x: number, z: number): SpawnSlot => ({
    side, index, position: [x, 0, z], onFloor: true, step: side === 0 ? 2 : 6, facing: side === 0 ? [1, 0] : [-1, 0], loc: { map: 0, x: 0, z: 0 },
  });
  const slots = [0, 1, 2, 3].flatMap((i) => [slot(0, i, -400, -200 + i * 50), slot(1, i, 400, -200 + i * 50)]);
  return {
    stem: 'MP99', name: 'FLAT', ground, grid: groundGrid(ground), spawns: null, slots, respawns: [], notes: [],
    c4Targets: [{ node: 'access_action1', at: [0, 0, 300], range: 32 }],
  };
}

const kit = (...ids: number[]): Loadout => ids as unknown as Loadout;
/** The records as `kitTableOf` reads them off the disc (research 94 §C11); the room reads them by id. */
const round = (over: Partial<ThrowableRecord>): ThrowableRecord => ({ ...M67, ...over });
const HEAT = round({ name: 'LAW HEAT', id: 185, muzzleVelocity: 200, acceleration: 980, armingDistance: 100, impact: true, hasBackblast: true, fuse: 20, removal: 20.1, capacity: 1, explosionDamage: 20, explosionRadius: 150 });
const RPG = round({ ...HEAT, name: 'RPG', id: 186, muzzleVelocity: 400 });
const BACKBLAST = round({ name: 'Backblast', id: 159, muzzleVelocity: 0, fuse: 0, removal: 0.1, capacity: 1, explosionDamage: 6, explosionRadius: 70 });
const PMN = round({ ...CLAYMORE, name: 'PMN Mine', id: 158, fuse: 8, removal: 10, explosionDamage: 6.5, explosionRadius: 40, proximity: 10 });
const C4 = round({ ...CLAYMORE, name: 'C4', id: 151, fuse: 6, removal: 0.1, explosionDamage: 18, explosionRadius: 50 });
const item = (name: string, id: number, extra: unknown[] = []): unknown[] => ['InternalName', [name], 'ID', [String(id)], 'Ammo_Capacity', ['1'], 'NumMags', ['1'], 'AMMO_TYPES', [[]], ...extra];
const arsenal = arsenalOf(['ZAMMO', [], 'ZWEAPON', [
  item('LAW', 145, ['SlotCost', ['2']]), item('LAW HEAT', 185), item('RPG LAUNCHER', 146, ['SlotCost', ['2']]), item('RPG', 186),
  item('C4', 151), item('Claymore', 153), item('PMN Mine', 158), item('Backblast', 159), item('M67', 121), item('Detonator', 193),
] as never]);
function kits(terrorist: Loadout, seal: Loadout): SimKits {
  const r = (x: ThrowableRecord) => ({ record: x, piercing: 0, fireWait: 3, reloadAfterShot: true, reloadDelayAfterShot: 1, icon: null });
  return {
    table: {
      arsenal, records: new Map([DEFAULT_RIFLE, HELD_SIDEARM].map((x) => [x.id, x])),
      rounds: new Map([[185, r(HEAT)], [186, r(RPG)]]),
      throwables: new Map([M67, CLAYMORE, PMN, C4, BACKBLAST].map((x) => [x.id, { record: x, piercing: x.id === 121 ? 4 : 0 }])),
    },
    map: {
      valves: new Map(), selectable: { seal: [], terrorist: [] },
      kits: { seal: [{ type: 'S', character: 's', loadout: seal }], terrorist: [{ type: 'T', character: 't', loadout: terrorist }] },
    },
  };
}

class Client implements Conn {
  readonly events: ServerEvent[] = [];
  send(frame: Uint8Array | string): void { if (typeof frame === 'string') this.events.push(JSON.parse(frame) as ServerEvent); }
  close(): void { /* not used */ }
  of<T extends ServerEvent['type']>(type: T): Extract<ServerEvent, { type: T }>[] {
    return this.events.filter((e) => e.type === type) as Extract<ServerEvent, { type: T }>[];
  }
}

type V3 = [number, number, number];
/** Player 1 (a Terrorist) and player 2 (a SEAL) on the floor at `t` and `s`, each with its side's kit. */
function setup(terrorist: Loadout, seal: Loadout, t: V3, s: V3) {
  let seed = 1;
  const random = (): number => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const room = new Room(map(), null, { now: () => 0, random }, null, kits(terrorist, seal));
  const join = (id: number): Client => {
    const c = new Client();
    room.hello(id, c, { type: 'hello', version: PROTOCOL_VERSION, name: `P${id}`, map: 'MP99' }, `10.0.0.${id}`);
    return c;
  };
  const a = join(1), b = join(2);
  room.step();
  room.player(1)!.sim.walker.place(t[0], t[1] + 20, t[2]);
  room.player(2)!.sim.walker.place(s[0], s[1] + 20, s[2]);
  for (let i = 0; i < 30; i++) room.step();
  const eye = (id: number): V3 => { const w = room.player(id)!.sim.walker.state; return [w.x, w.y + EYE_HEIGHT, w.z]; };
  const feet = (id: number): V3 => { const w = room.player(id)!.sim.walker.state; return [w.x, w.y, w.z]; };
  const send = (id: number, kind: string, from: V3, velocity: V3): void => room.text(id, { type: 'throw', seq: room.player(id)!.sim.seq, kind, from, velocity });
  const run = (seconds: number): void => { for (let i = 0; i < Math.round(seconds * TICK_HZ); i++) room.step(); };
  /** `seconds` of player `id`'s commands, standing still: its own clock (`Player.ran`), which the kit's rate counts on. */
  const drive = (id: number, seconds: number): void => {
    for (let i = 0; i < Math.round(seconds * TICK_HZ); i++) {
      const p = room.player(id)!;
      const cmd: Command = { seq: p.sim.seq + 1, forward: 0, right: 0, yaw: p.sim.walker.state.yaw, pitch: 0, turn: 0, buttons: 0, stance: 0, weapon: 0 };
      room.binary(id, encodeCommands({ viewTick: room.tick, commands: [cmd] }));
      room.step();
    }
  };
  return { room, a, b, eye, feet, send, run, drive };
}

describe('the rockets on the server (research 94 §C4, R94.6/R94.9)', () => {
  const LAW_KIT = kit(62, 15, 145, 185, 255);

  it('the LAW\'s rocket: taken as a throw of its round, flown straight at 980 u/s^2 with no fall, gone off at the wall, one shot', () => {
    const s = setup(kit(62, 15, 121, 126, 255), LAW_KIT, [560, 0, 0], [0, 0, 0]);
    const from = s.eye(2);
    s.send(2, 'LAW HEAT', from, [200, 0, 0]);
    expect(s.a.of('grenade')).toEqual([expect.objectContaining({ id: 2, kind: 'LAW HEAT' })]);
    const r = s.room.player(2)!;
    expect(r.rounds.ring(185)!.rounds()).toBe(0);                          // the LAW HEAT one shot
    const f = (s.room as unknown as { flying: { g: { pos: V3; vel: V3 } }[] }).flying.find((x) => x.g.vel[0] > 0)!;
    s.run(0.25);
    expect(f.g.pos[1]).toBeCloseTo(from[1], 6);                             // no fall
    expect(f.g.vel[0]).toBeCloseTo(200 + 980 * 0.25, 0);                    // AccelerationFactor x10 along the flight
    s.run(1.5);
    expect(s.a.of('hurt').length).toBeGreaterThan(0);                       // 20 in 15 m at the wall, player 1 40 off it
    s.send(2, 'LAW HEAT', s.eye(2), [200, 0, 0]);
    expect(s.a.of('grenade')).toHaveLength(1);                              // none left
  });

  it.each([
    ['a kit with no LAW', kit(62, 15, 121, 185, 255), 'LAW HEAT', 200],
    ['the RPG\'s round from a LAW', LAW_KIT, 'RPG', 400],
    ['a rocket leaving faster than its Muzzle_Velocity', LAW_KIT, 'LAW HEAT', 400],
  ] as const)('refuses %s', (_what, loadout, kind, speed) => {
    const s = setup(kit(62, 15, 121, 126, 255), loadout, [560, 0, 0], [0, 0, 0]);
    s.send(2, kind, s.eye(2), [speed, 0, 0]);
    expect(s.a.of('grenade')).toHaveLength(0);
  });

  it('the RPG-7 is fed one round at a time: FireWait 3 s between rockets (two RPG slots, two rockets)', () => {
    const s = setup(kit(62, 15, 121, 126, 255), kit(62, 15, 146, 186, 186), [0, 0, 500], [0, 0, 0]);
    s.send(2, 'RPG', s.eye(2), [400, 0, 0]);                                // east, at the wall: away from everyone
    s.drive(2, 1);
    s.send(2, 'RPG', s.eye(2), [400, 0, 0]);
    expect(s.a.of('grenade')).toHaveLength(1);
    s.drive(2, 2.1);
    s.send(2, 'RPG', s.eye(2), [400, 0, 0]);
    expect(s.a.of('grenade')).toHaveLength(2);
  });

  it.each([
    // where player 1 stands (the SEAL fires east from the origin, up the sky so the rocket's own blast reaches no one)
    ['behind the shooter, 3 m: the backblast hurts (6 in 7 m, 45 degrees)', [-30, 0, 0], true],
    ['beside the shooter, 3 m: outside its cone', [0, 0, 30], false],
    ['behind, 8 m: past its radius', [-80, 0, 0], false],
  ] as const)('%s', (_what, at, hurt) => {
    const s = setup(kit(62, 15, 121, 126, 255), LAW_KIT, at as unknown as V3, [0, 0, 0]);
    s.send(2, 'LAW HEAT', s.eye(2), [200 * Math.cos(0.3), 200 * Math.sin(0.3), 0]);
    s.run(0.2);
    expect(s.a.of('blast').length > 0).toBe(hurt);
    expect(s.b.of('blast')).toHaveLength(0);                                // the shooter is under its cone, not in it
  });
});

describe('the placed charges on the server (research 94 §C5, research 85 §9.7)', () => {
  it('the claymore: set down by the throw of it, gone off only by its Detonator, its cone full in front and a 32nd behind', () => {
    const s = setup(kit(62, 15, 121, 126, 255), kit(62, 15, 121, 153, 255), [150, 0, 0], [0, 0, 0]);
    s.send(2, 'Claymore', [8, 0.1, 0], [1, 0, 0]);                         // facing east, at the SEAL's hand
    expect(s.a.of('grenade')).toEqual([expect.objectContaining({ id: 2, kind: 'Claymore' })]);
    expect(s.room.player(2)!.grenades.Claymore).toBe(3);
    s.run(30);
    expect(s.a.of('blast')).toHaveLength(0);                                // no fuse: Timer1 held (+0xc5)
    s.room.player(2)!.sim.walker.place(-100, 20, 0);                        // back off behind it, then fire the Detonator
    s.run(0.5);
    s.send(2, 'Detonator', s.eye(2), [0, 0, 0]);
    // The others hear the Detonator's fire (a `grenade` of it, from the SEAL's feet): their copies of the claymore go too.
    expect(s.a.of('grenade').at(-1)).toMatchObject({ id: 2, kind: 'Detonator', velocity: [0, 0, 0] });
    s.run(0.1);
    expect(s.a.of('blast')).toHaveLength(1);
    expect(s.a.of('hurt').length).toBeGreaterThan(0);                       // 16 in 25 m, player 1 in its cone
  });

  it('the Detonator sets off only the SEAL\'s own claymores, within 500 u, never a PMN', () => {
    const s = setup(kit(62, 15, 153, 158, 255), kit(62, 15, 121, 153, 255), [60, 0, 60], [0, 0, 0]);
    s.send(1, 'PMN Mine', [60, 0.1, 40], [0, 0, 1]);                         // the Terrorist's mine, 20 u from him
    s.send(2, 'Detonator', s.eye(2), [0, 0, 0]);                             // the SEAL has no claymore down
    s.run(0.2);
    s.send(1, 'Detonator', s.eye(1), [0, 0, 0]);                             // the Terrorist's Detonator: the PMN is no claymore
    s.run(0.2);
    expect(s.b.of('blast')).toHaveLength(0);
    expect(s.a.of('blast')).toHaveLength(0);
  });

  it('the PMN: unarmed for its Timer1 (8 s), then an actor inside ProximityDistance (10 u) sets it off', () => {
    const s = setup(kit(62, 15, 153, 158, 255), kit(62, 15, 121, 126, 255), [0, 0, 0], [300, 0, 0]);
    s.send(1, 'PMN Mine', [8, 0.1, 0], [1, 0, 0]);
    s.room.player(1)!.sim.walker.place(-300, 20, 0);                         // the Terrorist walks off
    s.room.player(2)!.sim.walker.place(8, 20, 0);                            // the SEAL stands on it at once
    s.run(7.5);
    expect(s.b.of('blast')).toHaveLength(0);                                // not armed yet
    s.run(1);
    expect(s.b.of('blast')).toHaveLength(1);                                // armed at 8 s: tripped
    expect(s.b.of('hurt').length).toBeGreaterThan(0);                       // 6.5 in 4 m
  });

  it('PMN_FRIENDLY_READING: its owner trips his own mine too (no team test in FUN_00543930)', () => {
    const s = setup(kit(62, 15, 153, 158, 255), kit(62, 15, 121, 126, 255), [0, 0, 0], [300, 0, 0]);
    s.send(1, 'PMN Mine', [8, 0.1, 0], [1, 0, 0]);
    s.run(8.5);
    expect(s.a.of('blast')).toHaveLength(1);
  });

  it('C4: refused away from a C4 target; at one, still, set down and gone off at its Timer1 (6 s), 18 in 5 m', () => {
    const away = setup(kit(62, 15, 121, 126, 255), kit(62, 15, 121, 126, 151), [0, 0, 0], [0, 0, -300]);
    away.send(2, 'C4', [0, 0.1, -290], [0, 0, 1]);
    expect(away.a.of('grenade')).toHaveLength(0);
    expect(away.room.player(2)!.grenades.C4).toBe(4);
    const at = setup(kit(62, 15, 121, 126, 255), kit(62, 15, 121, 126, 151), [30, 0, 300], [0, 0, 290]);
    at.send(2, 'C4', [0, 0.1, 298], [0, 0, 1]);
    expect(at.a.of('grenade')).toHaveLength(1);
    expect(at.room.player(2)!.grenades.C4).toBe(3);
    at.room.player(2)!.sim.walker.place(0, 20, -300);                        // the SEAL gets clear
    at.run(5.8);
    expect(at.a.of('blast')).toHaveLength(0);
    at.run(0.4);
    expect(at.a.of('blast')).toHaveLength(1);                               // player 1, 30 u off: inside 50
  });

  it('the pouch follows the loadout (POUCH_PLACEHOLDER retired): the throw of an item the kit does not hold is refused', () => {
    const s = setup(kit(62, 15, 121, 126, 255), kit(62, 15, 121, 153, 158), [300, 0, 0], [0, 0, 0]);
    expect(s.room.player(2)!.grenades).toEqual({ M67: 3, Claymore: 4, 'PMN Mine': 4 });
    expect(s.room.player(1)!.grenades).toEqual({ M67: 3, HE: 3 });
    s.send(1, 'Claymore', [300, 0.1, 8], [1, 0, 0]);
    expect(s.b.of('grenade')).toHaveLength(0);
  });
});
