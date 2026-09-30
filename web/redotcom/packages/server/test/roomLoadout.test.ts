import { describe, expect, it } from 'vitest';
import type { RdrNode } from '@s2u/archive';
import {
  arsenalOf, DEFAULT_RIFLE, HELD_RIFLE, HELD_SIDEARM, type CollisionOwner, type GridParams, type KitTable, type Loadout,
  type MapArsenal, type SpawnSlot, type WeaponRecord, type WorldPoly,
} from '@s2u/scene';
import {
  cameraLook, centreClaim, decodeSnapshot, encodeCommands, EYE_HEIGHT, faceToward, groundGrid, packGround, PROTOCOL_VERSION,
  type ClientEvent, type Command, type ServerEvent, type SimKits, type SimMap,
} from '../../viewer/src/sim';
import { Room, type Conn } from '../src/room';

/**
 * Protocol 7 (web sprint 4, M9; W4.R6): the weapon select's `loadout` request. The room replays the page's picks from
 * the character type's own kit through the menu's rules (`@s2u/scene` `applyPicks`), keeps the result as the player's
 * next round's kit (classic: applied at the next round's spawn, R94.3) and answers with the kit it holds or the
 * refusal; the fire path reads the kit on the room's body, never the page's claim; a `spawn` carries the kit, a `shot`
 * the item, a `kill` the record's `DisplayName` (research 91 §10). A synthetic map and a hand-built arsenal (the
 * repository's convention: no disc).
 */

type V3 = [number, number, number];

function flatMap(): SimMap {
  const params: GridParams = { atomCount: 8192, posts: 16, cellDim: 200, cellsX: 10, cellsZ: 10, originX: -1000, originZ: -1000 };
  const floor: WorldPoly = {
    modelName: 'worldmodel', path: 'worldmodel/floor', region: 0, ditype: 3, material: 25, ptcount: 4, cameratype: 0,
    points: Float32Array.from([-1000, 0, -1000, 1000, 0, -1000, 1000, 0, 1000, -1000, 0, 1000]),
  };
  const owners: CollisionOwner[] = [{ modelName: 'worldmodel', path: 'worldmodel/floor0', first: 0, count: 1 }];
  const ground = packGround(params, [floor], owners);
  const slot = (side: 0 | 1, index: number, x: number, z: number): SpawnSlot => ({
    side, index, position: [x, 0, z], onFloor: true, step: side === 0 ? 2 : 6, facing: side === 0 ? [1, 0] : [-1, 0], loc: { map: 0, x: 0, z: 0 },
  });
  const slots = [0, 1, 2, 3].flatMap((i) => [slot(0, i, -400, -200 + i * 50), slot(1, i, 400, -200 + i * 50)]);
  return { stem: 'MP99', name: 'FLAT', ground, grid: groundGrid(ground), spawns: null, slots, respawns: [], notes: [] };
}

// ---- a hand-built arsenal: `zweapon.rdr`'s shape, as `scene/test/arsenal.test.ts` spells it ----------------------------

const rec = (...pairs: [string, RdrNode][]): RdrNode[] => pairs.flatMap(([k, v]) => [k, Array.isArray(v) ? v : [v]]);
const weapon = (name: string, id: number, display = name.toUpperCase()): RdrNode[] => rec(
  ['InternalName', name], ['DisplayName', display], ['ID', String(id)], ['NumMags', '3'], ['Ammo_Capacity', '30'],
  ['AMMO_TYPES', [rec(['NAME', '5.56 x 45mm'])]], ['ModelName', name.toLowerCase()], ['IconTextureName', `${name}_icon.tif`],
);
const zweapon: RdrNode = [
  'ZAMMO', [rec(['InternalName', '5.56 x 45mm'], ['ID', '8'])],
  'ZWEAPON', [
    weapon('M4A1', 54), weapon('M4A1 SD', 62), weapon('552', 57, '552 COMMANDO'), weapon('AK-47', 58), weapon('Mark 23', 15),
    weapon('M9', 5), weapon('M67', 121), weapon('AN-M8', 122), weapon('HE', 126), weapon('C4', 151), weapon('Double Ammo Load', 194, '2X AMMO'),
  ],
];
const rifle = (name: string, id: number): WeaponRecord => ({ ...DEFAULT_RIFLE, name, id });
const table: KitTable = {
  arsenal: arsenalOf(zweapon),
  records: new Map([[54, rifle('M4A1', 54)], [62, HELD_RIFLE], [57, rifle('552', 57)], [58, rifle('AK-47', 58)], [15, HELD_SIDEARM], [5, { ...HELD_SIDEARM, name: 'M9', id: 5 }]]),
  rounds: new Map(),
};
const kit = (...ids: number[]): Loadout => ids as unknown as Loadout;
/** The valves: the M4s and the Mark 23 the SEALs', the 552, the AK and the M9 the Terrorists', the throwables both; C4 locked in a SEAL's kit (16). */
const valves = new Map([
  ['Enable_m4Acarbine', 1], ['Enable_M4A1_SD', 1], ['Enablesig_commando', 8], ['Enable_ak47', 8], ['Enable_Mark23', 1],
  ['Enable_beretta_m9', 8], ['Enable_frag', 9], ['Enable_smoke', 9], ['Enable_HEgren', 9], ['Enable_c4', 16 | 1], ['Enable_2xammo', 9],
]);
const SEAL_KIT = kit(54, 15, 121, 151, 194);
const TERRORIST_KIT = kit(57, 5, 121, 126, 255);
const map: MapArsenal = {
  valves, selectable: { seal: [], terrorist: [] },
  kits: {
    seal: [{ type: 'Seal1', character: 'mp99_seal1', loadout: SEAL_KIT }],
    terrorist: [{ type: 'Terrorist1', character: 'mp99_terror1', loadout: TERRORIST_KIT }],
  },
};
const kits: SimKits = { table, map };

// ---- the room, driven as room.test.ts drives it -------------------------------------------------------------------

class Client implements Conn {
  readonly events: ServerEvent[] = [];
  readonly frames: Uint8Array[] = [];
  closed: { code: number; reason: string } | null = null;
  send(frame: Uint8Array | string): void {
    if (typeof frame === 'string') this.events.push(JSON.parse(frame) as ServerEvent);
    else this.frames.push(frame);
  }
  close(code: number, reason: string): void { this.closed = { code, reason }; }
  of<T extends ServerEvent['type']>(type: T): Extract<ServerEvent, { type: T }>[] {
    return this.events.filter((e) => e.type === type) as Extract<ServerEvent, { type: T }>[];
  }
}

function setup(opts: ConstructorParameters<typeof Room>[2] = {}, withKits: SimKits | null = kits) {
  let seed = 1;
  const room = new Room(flatMap(), null, { now: () => 0, random: () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }, rules: 'classic', ...opts }, null, withKits);
  const seqs = new Map<number, number>();
  const join = (id: number, version = PROTOCOL_VERSION): Client => {
    const c = new Client();
    room.hello(id, c, { type: 'hello', version, name: `P${id}`, map: 'MP99' }, `10.0.0.${id}`);
    return c;
  };
  const cmd = (id: number, over: Partial<Command> = {}): Command => {
    const seq = (seqs.get(id) ?? room.player(id)?.sim.seq ?? 0) + 1;
    seqs.set(id, seq);
    const p = room.player(id)!;
    return { seq, forward: 0, right: 0, yaw: p.sim.walker.state.yaw, pitch: 0, turn: 0, buttons: 0, stance: 0, weapon: 0, ...over };
  };
  const send = (id: number, commands: Command[]): void => room.binary(id, encodeCommands({ viewTick: room.tick, commands }));
  const loadout = (id: number, picks: unknown): void => room.text(id, { type: 'loadout', picks } as unknown as ClientEvent);
  return { room, join, cmd, send, loadout, forget: (id: number) => seqs.delete(id) };
}
type Setup = ReturnType<typeof setup>;

/** The next round in a classic room: its clock run out (6 minutes), the round's end held, the next round's spawns. */
function nextRound(s: Setup): void {
  const start = s.room.round;
  for (let i = 0; i < 60 * 60 * 10 && s.room.round === start; i++) s.room.step();
}

/** A player that faces a point and fires as the page does (room.test.ts' `gunner`, trimmed). */
function gunner(s: Setup, id: number) {
  let look = { yaw: s.room.player(id)!.sim.walker.state.yaw, pitch: 0 };
  let point: V3 | null = null;
  const run = (n = 1): void => { for (let i = 0; i < n; i++) { s.send(id, [s.cmd(id, look)]); s.room.step(); } };
  const feet = (): V3 => { const st = s.room.player(id)!.sim.walker.state; return [st.x, st.y, st.z]; };
  const face = (at: V3): void => { look = faceToward({ feet: feet(), posture: s.room.player(id)!.sim.walker.posture }, at); point = at; run(2); };
  const shoot = (weaponClaim = 0): void => {
    const seq = s.room.player(id)!.sim.seq;
    const f = s.room.player(id)!.cone.frame(seq)!;
    const from: V3 = [f.feet[0], f.feet[1] + EYE_HEIGHT, f.feet[2]];
    const { eye } = cameraLook(f);
    const t = point ? Math.hypot(point[0] - eye[0], point[1] - eye[1], point[2] - eye[2]) : 200;
    const c = centreClaim(f, from, t);
    s.room.text(id, { type: 'fire', seq, from: c.from, dir: c.dir, eye: c.eye, aim: c.aim, weapon: weaponClaim, viewTick: s.room.tick });
  };
  return { run, face, shoot };
}

/** A SEAL (id 2) and a Terrorist (id 1) seated: the classic round launched. */
function match(opts: ConstructorParameters<typeof Room>[2] = {}) {
  const s = setup(opts);
  const t = s.join(1), seal = s.join(2);
  s.room.step();
  return { ...s, t, seal };
}

describe('protocol 7: the loadout request, replayed by the room from the type\'s kit (applyPicks, W4.R6)', () => {
  it('a protocol-6 page is refused at the hello, as any other version is', () => {
    const s = setup();
    const c = s.join(1, 6);
    expect(c.of('refused')[0]!.reason).toMatch(/protocol 6, this server speaks 7/);
    expect(c.closed?.code).toBe(4000);
    expect(s.room.player(1)).toBeUndefined();
  });

  it('answers with the kit it computed and holds it for the next round; this round\'s body keeps its kit (R94.3)', () => {
    const s = match();
    expect(s.room.player(2)!.loadout).toEqual(SEAL_KIT);
    s.loadout(2, [{ slot: 0, id: 62 }, { slot: 2, id: 122 }]);
    const answer = s.seal.of('loadout').at(-1)!;
    expect(answer).toEqual({ type: 'loadout', kit: [62, 15, 122, 151, 194], refused: null });
    expect(s.room.player(2)!.loadout).toEqual(SEAL_KIT);                  // not before the next round's rebuild
    expect(s.room.player(2)!.records[0].name).toBe('M4A1');
    nextRound(s);
    expect(s.room.player(2)!.loadout).toEqual([62, 15, 122, 151, 194]);
    expect(s.room.player(2)!.records[0].name).toBe('M4A1 SD');
    // The spawn names the kit, to the page and to the others (their holsters and hands).
    expect(s.seal.of('spawn').filter((e) => e.id === 2).at(-1)!.kit).toEqual([62, 15, 122, 151, 194]);
    expect(s.t.of('spawn').filter((e) => e.id === 2).at(-1)!.kit).toEqual([62, 15, 122, 151, 194]);
    // And the round after keeps it: the pick is written to the type, not spent (FUN_0023e5e0 -> type +0x2f0).
    nextRound(s);
    expect(s.room.player(2)!.loadout).toEqual([62, 15, 122, 151, 194]);
  });

  it('is idempotent: the whole list each time lands on the same kit, repeated or extended', () => {
    const s = match();
    const picks = [{ slot: 0, id: 62 }];
    s.loadout(2, picks); s.loadout(2, picks);
    expect(s.seal.of('loadout').map((a) => a.kit)).toEqual([[62, 15, 121, 151, 194], [62, 15, 121, 151, 194]]);
    s.loadout(2, [...picks, { slot: 0, id: 54 }]);
    expect(s.seal.of('loadout').at(-1)!.kit).toEqual(SEAL_KIT);
    s.loadout(2, []);                                                    // no picks: the type's own kit
    expect(s.seal.of('loadout').at(-1)!.kit).toEqual(SEAL_KIT);
  });

  it.each([
    // [what, the picks, the refusal, at]
    ['the other side\'s weapon (the Terrorists\' AK-47 for a SEAL)', [{ slot: 0, id: 58 }], 'refused', 0],
    ['an unknown id', [{ slot: 2, id: 250 }], 'unknown', 0],
    ['a locked slot (C4 while Enable_c4 carries 16, FUN_0023e910)', [{ slot: 3, id: 121 }], 'locked', 0],
    ['a second primary (the M4A1 in an equipment slot)', [{ slot: 2, id: 54 }], 'refused', 0],
    ['a sidearm in the primary slot', [{ slot: 0, id: 15 }], 'refused', 0],
    ['a slot past 4', [{ slot: 5, id: 121 }], 'slot', 0],
    ['a good pick, then a bad one: the whole request refused, at the second', [{ slot: 0, id: 62 }, { slot: 1, id: 5 }], 'refused', 1],
  ] as const)('refuses %s, and keeps the kit it held', (_what, picks, reason, at) => {
    const s = match();
    s.loadout(2, [{ slot: 2, id: 126 }]);                                // a kit held before
    s.loadout(2, picks);
    expect(s.seal.of('loadout').at(-1)).toEqual({ type: 'loadout', kit: [54, 15, 126, 151, 194], refused: { reason, at } });
    nextRound(s);
    expect(s.room.player(2)!.loadout).toEqual([54, 15, 126, 151, 194]);
  });

  it.each([
    ['not a list', { slot: 0, id: 62 }],
    ['a pick without an id', [{ slot: 0 }]],
    ['a fractional slot', [{ slot: 0.5, id: 62 }]],
    ['past MAX_LOADOUT_PICKS', Array.from({ length: 65 }, () => ({ slot: 0, id: 62 }))],
  ])('a malformed request (%s) is answered with the slot refusal, never thrown (BL-2)', (_what, picks) => {
    const s = match();
    expect(() => s.loadout(2, picks)).not.toThrow();
    expect(s.seal.of('loadout').at(-1)!.refused!.reason).toBe('slot');
  });

  it('a Terrorist\'s picks are the Terrorists\' own: the AK-47 taken, the M4A1 SD refused', () => {
    const s = match();
    s.loadout(1, [{ slot: 0, id: 58 }]);
    expect(s.t.of('loadout').at(-1)).toEqual({ type: 'loadout', kit: [58, 5, 121, 126, 255], refused: null });
    s.loadout(1, [{ slot: 0, id: 62 }]);
    expect(s.t.of('loadout').at(-1)!.refused).toEqual({ reason: 'refused', at: 0 });
  });

  it('a pick survives a reconnect: the rejoiner\'s page sends its list again and the new seat holds the same kit', () => {
    const s = match();
    const picks = [{ slot: 0, id: 62 }, { slot: 2, id: 122 }];
    s.loadout(2, picks);
    s.room.leave(2);
    const again = s.join(3);                                            // the rejoiner's new place, a SEAL again
    expect(s.room.player(3)!.team).toBe('seal');
    s.loadout(3, picks);                                                // `LoadoutSync` resends on the welcome
    expect(again.of('loadout').at(-1)!.kit).toEqual([62, 15, 122, 151, 194]);
    nextRound(s);
    expect(s.room.player(3)!.loadout).toEqual([62, 15, 122, 151, 194]);
  });

  it('a room without the arsenal refuses every pick as unknown and holds the baked kit', () => {
    const s = setup({}, null);
    const c = s.join(1);
    s.loadout(1, [{ slot: 0, id: 62 }]);
    expect(c.of('loadout').at(-1)!.refused).toEqual({ reason: 'unknown', at: 0 });
    s.loadout(1, []);
    expect(c.of('loadout').at(-1)!.refused).toBeNull();
  });

  it('the page\'s own room replays from the page\'s developer kit (soloKit), the type\'s record it stands in for', () => {
    const s = setup({ solo: true, soloKit: () => kit(62, 15, 121, 126, 255) });
    const c = s.join(1);
    expect(s.room.player(1)!.loadout).toEqual([62, 15, 121, 126, 255]);
    s.loadout(1, [{ slot: 3, id: 122 }]);
    expect(c.of('loadout').at(-1)!.kit).toEqual([62, 15, 121, 122, 255]);
  });

  it('the welcome lists each player\'s kit as its body carries it', () => {
    const s = match();
    const late = s.join(4);
    const seen = new Map(late.of('welcome')[0]!.players.map((p) => [p.id, p.kit]));
    expect(seen.get(1)).toEqual([...TERRORIST_KIT]);
    expect(seen.get(2)).toEqual([...SEAL_KIT]);
  });
});

describe('protocol 7: the room\'s authority over the weapon in the hand (W4.R6)', () => {
  /** The Terrorist (1) at the origin facing the SEAL (2) 100 units east. */
  function duel() {
    const s = match();
    const pt = s.room.player(1)!, ps = s.room.player(2)!;
    pt.sim.walker.place(0, 20, 0); ps.sim.walker.place(100, 20, 0);
    const g = gunner(s, 1);
    for (let i = 0; i < 20; i++) s.room.step();
    g.face([100, 12, 0]);
    return { ...s, g, pt, ps };
  }

  it('a round is the room\'s kit\'s: the shot names the 552 by id whatever slot the page claims, the body carries its id', () => {
    const { seal, g, pt } = duel();
    g.shoot(1); g.run(1);                                                // the page claims the sidearm: the room's hand is the rifle
    expect(seal.of('shot').at(-1)).toMatchObject({ id: 1, weapon: 57 });
    expect(pt.mags[0].rounds()).toBe(29);
    expect(pt.mags[1].rounds()).toBe(pt.records[1].magazine);              // the sidearm untouched
    g.run(2);                                                            // a snapshot goes out every second tick
    const body = decodeSnapshot(seal.frames.at(-1)!).bodies.find((b) => b.id === 1)!;
    expect([body.weapon, body.slot]).toEqual([57, 0]);
  });

  it('a pick waiting for the next round fires nothing now: the 552 until the rebuild, then the AK-47', () => {
    const { seal, t, g, loadout } = duel();
    loadout(1, [{ slot: 0, id: 58 }]);
    expect(t.of('loadout').at(-1)!.refused).toBeNull();
    g.shoot(); g.run(1);
    expect(seal.of('shot').at(-1)!.weapon).toBe(57);
  });

  it('the kill line names the weapon by its DisplayName (research 91 §10: FUN_003d19a0 -> record +8)', () => {
    const { seal, g, ps } = duel();
    for (let k = 0; k < 12 && ps.alive; k++) { g.shoot(); g.run(9); }
    expect(ps.alive).toBe(false);
    expect(seal.of('kill')[0]).toMatchObject({ killer: 1, victim: 2, how: 'weapon', weapon: '552 COMMANDO' });
  });
});
