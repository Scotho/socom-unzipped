import { describe, expect, it } from 'vitest';
import { Hud } from '../src/hud';
import { NetPage, type NetPageDeps } from '../src/netPage';
import type { WebSocketLike } from '../src/net/client';
import type { Rules, ServerEvent } from '../src/net/protocol';
import type { RemotePlayers } from '../src/remotePlayers';
import type { WalkMode } from '../src/walk';
import { HELD_RIFLE, HELD_SIDEARM } from '@s2u/scene';

/**
 * The page in a match, by its rules: the round-start banner driven from the server's round (`FUN_001fb420`), the
 * classic round's messages and the dead's follow camera. A fake socket stands in for the server.
 */

function page(rules: Rules, solo = false, extra: Partial<NetPageDeps> = {}) {
  const sent: string[] = [];
  let socket: WebSocketLike | null = null;
  const hud = new Hud();
  hud.setVisible(true);
  const modes: string[] = [];
  const poses: ({ x: number } | null)[] = [];
  const walk = {
    setNetTap: () => undefined, setLocked: () => undefined, respawn: () => true, nudge: () => undefined,
    setTrigger: () => undefined, setDeathPose: () => undefined, setDeathKiller: () => undefined, setMode: (m: string) => { modes.push(m); return true; },
    mode: () => 'walk',
  } as unknown as WalkMode;
  const bodies: { id: number; flags: number; feet: [number, number, number]; yaw: number }[] = [];
  const kits = new Map<number, number[]>();
  const remote = {
    setTeam: () => undefined, forget: () => undefined, died: () => undefined, clear: () => undefined, frame: () => undefined,
    setKit: (id: number, kit: number[]) => { kits.set(id, kit); },
  } as unknown as RemotePlayers;
  const respawns: number[] = [];
  const kitsSpawned: (readonly number[] | null)[] = [];
  const deps: NetPageDeps = {
    walk, remote, hud, clips: () => null, remoteGrenade: () => undefined, spectate: (p) => { poses.push(p); },
    respawned: (kit) => { respawns.push(respawns.length + 1); kitsSpawned.push(kit ?? null); },
    roundEffects: () => undefined, weapons: () => [HELD_RIFLE, HELD_SIDEARM],
    socket: () => {
      socket = { binaryType: '', readyState: 1, send: (d: string | Uint8Array) => { if (typeof d === 'string') sent.push(d); }, close: () => undefined } as unknown as WebSocketLike;
      return socket;
    },
  };
  const net = new NetPage({ ...deps, ...(solo ? { solo } : {}), ...extra }, 'ws://test/ws', 'MP2', 'Tester', undefined, false, rules);
  socket!.onopen?.({} as Event);
  const server = (ev: ServerEvent): void => { socket!.onmessage?.({ data: JSON.stringify(ev) } as MessageEvent); };
  // The client reads the bodies from its snapshots; the tests hand them in directly.
  (net.client as unknown as { bodies: () => unknown[] }).bodies = () => bodies;
  const banner = (): string[] => hud.state().model.banner.map((b) => b.lines.map((l) => l.text).join('/'));
  const welcome = (over: Partial<Extract<ServerEvent, { type: 'welcome' }>> = {}): void => server({
    type: 'welcome', id: 1, version: 4, map: 'MP2', tick: 0, role: 'player', team: 'seal', queue: 0, name: 'Tester',
    players: [], rules, round: 1, rounds: 11, ghost: false, ...over,
  });
  const requests = (): unknown[] => sent.map((d) => JSON.parse(d) as { type: string }).filter((e) => e.type === 'loadout');
  return { net, hud, sent, server, banner, welcome, bodies, modes, poses, respawns, kitsSpawned, kits, requests };
}

describe('the round-start banner online (FUN_001fb420 L57633-57648)', () => {
  it('the hello names the rules', () => {
    const { sent } = page('classic');
    expect(JSON.parse(sent[0]!)).toMatchObject({ type: 'hello', version: 7, map: 'MP2', rules: 'classic' });
  });

  it('respawn keeps the original\'s quirk: STARTING ROUND 1 OF 11 for its one round, at the join and at each match', () => {
    const { hud, server, banner, welcome } = page('respawn');
    hud.step(20);
    welcome();
    hud.step(1);
    expect(banner()).toEqual(['STARTING ROUND 1 OF 11']);
    hud.step(20);
    server({ type: 'roundStart', round: 1, seconds: 360, wins: { seal: 0, terrorist: 0 }, rounds: 11 });
    hud.step(6);
    expect(banner()).toEqual(['STARTING ROUND 1 OF 11', 'OBJECTIVE:/ELIMINATE THE TERRORISTS']);
  });

  it('classic shows the true round of 11, then PLAYING TIEBREAKER ROUND; the objective by side', () => {
    const { hud, server, banner, welcome } = page('classic');
    welcome({ team: 'terrorist' });
    hud.step(20);
    server({ type: 'roundStart', round: 3, seconds: 360, wins: { seal: 1, terrorist: 1 }, rounds: 11 });
    hud.step(6);
    expect(banner()).toEqual(['STARTING ROUND 3 OF 11', 'OBJECTIVE:/ELIMINATE THE SEALS']);
    hud.step(20);
    server({ type: 'roundStart', round: 12, seconds: 360, wins: { seal: 5, terrorist: 5 }, rounds: 11 });
    hud.step(1);
    expect(banner()).toEqual(['PLAYING TIEBREAKER ROUND']);
  });

  it('a ghost gets no banner at the join, and the game\'s ghost lines as WEAPON EXCHANGE\'s prompt (not the message window)', () => {
    const { net, hud, banner, welcome } = page('classic');
    hud.step(20);
    welcome({ ghost: true });
    hud.step(1);
    expect(banner()).toEqual([]);
    expect(net.prompt()).toMatchObject({ ghost: true });
    expect(net.gate()).toEqual({ inMatch: true, alive: false, cameraOnSelf: true, spectator: false });
  });
});

describe('the classic round on the page', () => {
  it('posts the elimination lines', () => {
    const { hud, server, banner, welcome } = page('classic');
    welcome();
    hud.step(20);
    server({ type: 'eliminated', winner: 'seal' });
    hud.step(0.5);
    expect(banner()).toEqual(['ALL TERRORISTS ELIMINATED/SEALS VICTORIOUS!']);
  });

  it('dead: the game\'s lines, never the respawn prompt; Space follows the living teammates only', () => {
    const { net, hud, server, banner, welcome, bodies, modes, poses } = page('classic');
    welcome();
    server({ type: 'joined', id: 2, name: 'Mate', team: 'seal' });
    server({ type: 'joined', id: 3, name: 'Foe', team: 'terrorist' });
    server({ type: 'joined', id: 4, name: 'Down', team: 'seal' });
    bodies.push({ id: 2, flags: 64, feet: [100, 0, 0], yaw: 0 }, { id: 3, flags: 64, feet: [300, 0, 0], yaw: 0 }, { id: 4, flags: 0, feet: [500, 0, 0], yaw: 0 });
    hud.step(20);
    server({ type: 'kill', killer: 3, victim: 1, weapon: '552', how: 'weapon', clip: null });
    hud.step(6);
    const lines = banner();
    // The dead's lines are WEAPON EXCHANGE's prompt (`promptLines`, drawn by the page's overlay), never posted as well.
    expect(lines.some((l) => l.includes('You have died'))).toBe(false);
    expect(net.prompt()).toMatchObject({ ghost: false });
    expect(net.gate()).toEqual({ inMatch: true, alive: false, cameraOnSelf: true, spectator: false });
    expect(lines.some((l) => l.includes('respawn'))).toBe(false);
    globalThis.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space' }));
    net.frame(0.016, {} as never, false);
    expect(modes).toContain('fly');
    expect(poses.at(-1)!.x).toBeCloseTo(100, 0);                // the living teammate, not the foe nor the dead one
    expect(net.prompt()).toBeNull();                           // the camera off oneself: no prompt, no menu (S6)
    expect(net.gate().cameraOnSelf).toBe(false);
    net.close();
  });

  it('DEAD_CYCLE_WHILE_MENU_READING: with WEAPON EXCHANGE open (HUD mode 1) Space cycles no teammate', () => {
    let open = true;
    const { net, server, welcome, bodies, modes } = page('classic', false, { menuOpen: () => open });
    welcome();
    server({ type: 'joined', id: 2, name: 'Mate', team: 'seal' });
    bodies.push({ id: 2, flags: 64, feet: [100, 0, 0], yaw: 0 });
    server({ type: 'kill', killer: 3, victim: 1, weapon: '552', how: 'weapon', clip: null });
    globalThis.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space' }));
    expect(modes).not.toContain('fly');
    open = false;
    globalThis.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space' }));
    expect(modes).toContain('fly');
    net.close();
  });
});

describe('protocol 7 on the page: the loadout request, its answer, the kits the spawns carry, the shots by id', () => {
  it('sends the side\'s picks, takes the answer; after a reconnect\'s welcome the list goes again (a pick survives it)', () => {
    const picks = [{ slot: 0, id: 62 }];
    const answers: unknown[] = [];
    const { net, server, welcome, requests } = page('classic', false, {
      picks: () => picks, loadoutAnswer: (kit, refused, list) => { answers.push({ kit, refused, list }); },
    });
    welcome();                                                  // a (re)join as a player: the list is sent again
    expect(requests()).toEqual([{ type: 'loadout', picks }]);
    net.requestLoadout([...picks, { slot: 2, id: 122 }]);
    expect(requests().at(-1)).toEqual({ type: 'loadout', picks: [...picks, { slot: 2, id: 122 }] });
    server({ type: 'loadout', kit: [62, 15, 122, 126, 194], refused: null });
    server({ type: 'loadout', kit: [62, 15, 122, 126, 194], refused: { reason: 'refused', at: 1 } });
    // Each answer is handed the list it answers (in order): the welcome's re-send, then the confirm's.
    expect(answers).toEqual([
      { kit: [62, 15, 122, 126, 194], refused: null, list: picks },
      { kit: [62, 15, 122, 126, 194], refused: { reason: 'refused', at: 1 }, list: [...picks, { slot: 2, id: 122 }] },
    ]);
    net.close();
  });

  it('no picks yet: the welcome sends nothing; a spectator never asks', () => {
    const { net, welcome, requests } = page('classic', false, { picks: () => [] });
    welcome();
    expect(requests()).toEqual([]);
    const s = page('classic', false, { picks: () => [{ slot: 0, id: 62 }] });
    s.welcome({ role: 'spectator', team: null });
    s.net.requestLoadout([{ slot: 0, id: 62 }]);
    expect(s.requests()).toEqual([]);
    net.close(); s.net.close();
  });

  it('its own spawn hands on the room\'s kit; another\'s is that body\'s kit, as the welcome\'s players are', () => {
    const { net, server, welcome, kitsSpawned, kits } = page('classic');
    welcome({ players: [{ id: 2, name: 'Foe', team: 'terrorist', kit: [57, 5, 121, 126, 255] }] });
    expect(kits.get(2)).toEqual([57, 5, 121, 126, 255]);
    server({ type: 'spawn', id: 1, at: [0, 0, 0], yaw: 0, after: 0, kit: [62, 15, 122, 126, 194] });
    expect(kitsSpawned).toEqual([[62, 15, 122, 126, 194]]);
    server({ type: 'spawn', id: 2, at: [0, 0, 0], yaw: 0, after: 0, kit: [58, 5, 121, 126, 255] });
    expect(kits.get(2)).toEqual([58, 5, 121, 126, 255]);
    net.close();
  });

  it('another player\'s shot is drawn and heard by the record of the item it names', () => {
    const effects: string[] = [];
    const r552 = { ...HELD_RIFLE, name: '552', id: 57 };
    const { net, server, welcome } = page('classic', false, {
      roundEffects: (e) => { effects.push(e.weapon.name); },
      recordOf: (id) => (id === 57 ? r552 : null),
    });
    welcome();
    server({ type: 'joined', id: 2, name: 'Foe', team: 'terrorist' });
    server({ type: 'shot', id: 2, weapon: 57, from: [0, 0, 0], to: [1, 0, 0], normal: null, material: null });
    server({ type: 'shot', id: 2, weapon: 15, from: [0, 0, 0], to: [1, 0, 0], normal: null, material: null });
    expect(effects).toEqual(['552', HELD_SIDEARM.name]);       // an item without a record here: the side's slot that holds it
    net.close();
  });
});

describe('the kit of the page at a spawn (research 91 §4.3: FUN_00598b90 -> FUN_00599b60 -> FUN_00599f00)', () => {
  it('its own spawn refreshes the kit as the server does; another player spawn never; each round spawn again', () => {
    const { net, server, welcome, respawns } = page('classic');
    welcome();
    server({ type: 'kill', killer: 3, victim: 1, weapon: '552', how: 'weapon', clip: null });
    expect(respawns).toHaveLength(0);
    server({ type: 'spawn', id: 1, at: [0, 0, 0], yaw: 0, after: 0 });
    expect(respawns).toHaveLength(1);
    server({ type: 'spawn', id: 2, at: [10, 0, 0], yaw: 0, after: 0 });
    expect(respawns).toHaveLength(1);                           // another player's spawn is theirs
    server({ type: 'roundStart', round: 2, seconds: 360, wins: { seal: 1, terrorist: 0 }, rounds: 11 });
    server({ type: 'spawn', id: 1, at: [0, 0, 0], yaw: 0, after: 0 });
    expect(respawns).toHaveLength(2);                           // a classic round's start is a spawn too
    net.close();
  });
});

describe('the Online line while the offline match runs (wave-3 carry-over: it read "single player: no server")', () => {
  it('the offline match (`./net/loopback`) reports offline, not off; a server match reports its connection', () => {
    expect(page('respawn', true).net.status().state).toBe('offline');
    expect(page('respawn').net.status().state).not.toMatch(/^off/);
  });
});
