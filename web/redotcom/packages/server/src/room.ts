import {
  AN_M8, BOUNCE_LIFT, CLAYMORE, CLAYMORE_RULES, claymoreCone, gridCast, HE, ITEM, itemClass, launchGrenade, M67, MARK141, proximityTripped,
  segmentHit, SOILS, stepGrenade, UNITS_PER_METRE,
  type Grenade, type HullCast, type HullHit, type KitTable, type Loadout, type SpawnSlot, type ThrowableRecord, type WeaponRecord,
} from '@s2u/scene';
import {
  applyFall, applyHit, bodyOf, bulletDamage, fragmentCount, fragmentDamage, fragmentPart, decodeCommands, encodeSnapshot, freshHealth, groundPolygons, isDead, Lobby,
  DoorSet, doorInReach, MoverSim, overall, ringFor, roundPath, shortTurn, Traversal, Walker, wrapYaw, type MagazineRing,
  Button, MAX_REWIND_MS, PROTOCOL_VERSION, SNAPSHOT_HZ, TICK_HZ,
  ELIMINATED_HOLD_S, eliminationWinner, isMatchOver, MAX_ROUNDS, ROUND_WATCH_S, type Rules,
  EYE_HEIGHT, PROBE_LIFT, fireInterval, reloadLockSeconds, reloadMoving, reloadSeconds, ShotCone, targetHeight,
  BAKED_LOADOUT, kitRecords, typeLoadout, type SimKits,
  afterShotLock, isCarrier, KitRounds, pelletDamage, pelletsOf, reloadDelayOf, reloadFamily, roundFits, shotgunPellets,
  backblastReaches, c4Plant, equipmentKind, EQUIPMENT_SLOTS, pouchOf, rocketRoundOf,
  type BodyState, type ClientEvent, type Command, type ExtraSurface, type Health, type KillHow, type LobbyChange,
  type PlaySnapshot, type ScoreRow, type ServerEvent, type SimClips, type SimMap, type SimSkeleton, type Team,
} from '../../viewer/src/sim';
import { bodyVolumes, rayBody, stanceVolumes, BODY_REACH, BODY_TOP, type StanceVolumes, type V3 } from '../../viewer/src/net/hitVolumes';
import { deathClip } from '../../viewer/src/net/deaths';
import { applyKnock, BLAST_RING_SECONDS, BLAST_RING_VOLUME, resolveBlast } from '../../viewer/src/net/blast';

/**
 * One map's match (web sprint 3, M3/M6; rulings W3.R8-R13): the lobby, every player's mover run from its command
 * stream at the game's 60 Hz, the rounds on the original's clock, the game's damage, deaths, respawns, kills and
 * scores, and a snapshot to each client at 30 Hz. It knows nothing of sockets: a `Conn` sends frames, and the server
 * (`./server`) feeds it what arrives, so the tests drive it tick by tick.
 */

export interface Conn { send(frame: Uint8Array | string): void; close(code: number, reason: string): void }

export interface RoomOptions {
  /** Milliseconds now (the idle kick's clock). */
  now: () => number;
  random: () => number;
  /** W3.R13: the idle kick, held to 3-5 minutes. */
  idleKickMs: number;
  /** W3.R11: the round and the match (the create-game defaults: 6 minutes, 11 rounds). */
  roundSeconds: number;
  /**
   * `mp_max_rounds` (the create-game default 11, `../../viewer/src/net/rules` `MAX_ROUNDS`): classic's match, and the
   * round-start banner's count under both rules (a respawn match is one round whatever it says: `isMatchOver`).
   */
  maxRounds: number;
  /** The room's rules: `respawn` (W3.R11) or `classic` (respawn off, the create-game default). */
  rules: Rules;
  /**
   * The page's single-player match (`../../viewer/src/net/loopback`, offline): the one player is the host, a SEAL
   * (`FUN_002c5450` L166238-166262); no idle kick; classic's round starts with one side seated and runs to its clock,
   * a side with nobody on it never eliminated (SOLO_ROUND_PLACEHOLDER: the game launches only with both sides seated,
   * `FUN_002c3cf0` L165325-165352, so it has no one-player round of its own).
   */
  solo?: boolean;
  /**
   * The page's own room only (`solo`): the kit the page's player spawns with when the developer asked for one (`&kit=`,
   * `../../viewer/src/loadout` `PlayerLoadout.pending`), else null for the type's own. A network room never reads it:
   * its kits are its own (W4.R6; the request and its validation are M9's `loadout`).
   */
  soloKit?: () => Loadout | null;
}

export const DEFAULT_OPTIONS: RoomOptions = {
  // W3.R11: with RESPAWN on the original's match is one round (research 91 section 18), whatever `mp_max_rounds` says.
  now: () => Date.now(), random: Math.random, idleKickMs: 4 * 60_000, roundSeconds: 6 * 60, maxRounds: MAX_ROUNDS, rules: 'respawn',
};

/** W3.R13: the idle kick's bounds (the owner's "3-5 minute kick timer"). */
export const IDLE_KICK_MIN_MS = 3 * 60_000, IDLE_KICK_MAX_MS = 5 * 60_000;

/** Research 91 section 4.1: the respawn press counts from 5 s dead, once the body has faded (1 -> 0 at 0.1/s: 10 s). */
export const RESPAWN_PRESS_S = 5, RESPAWN_FADE_S = 10;
/** Research 91 section 4.2: the respawn record is lifted a unit above its cell (`FUN_002b8100` L158793). */
const SPAWN_LIFT = 1;
/**
 * The end of a round (research 91 section 18, the maps' `mission_timer2` / `success2` and the MPZANIM screens): at
 * 00:00 "TIME EXPIRED" and 15 s more play; the result 1 s after; the engine reads it 3 s later; then ROUND COMPLETE's
 * countdown (5 s) before the next round, or FINAL ROUND (10 s) and GAME COMPLETE (10 s, the host's wait) after a match.
 */
/** VOTE_BAN_SCOPE_PLACEHOLDER (see `Room.banned`). */
export const VOTE_BAN_MS = 10 * 60_000;
export const EXPIRED_PLAY_S = 15, RESULT_S = 1, ENGINE_READ_S = 3, ROUND_COMPLETE_S = 5, FINAL_ROUND_S = 10, GAME_COMPLETE_S = 10;
/**
 * A client's commands are run as its credit allows: a tick's worth each server tick, or the wall time's when the loop
 * stalled and dropped ticks (a GC pause, a busy host), so a stall's backlog is run once the server is back rather than
 * left in the queue for good; never more than a second's worth saved up (the speed guard: no client runs faster than
 * real time, past a one-second burst).
 */
const CREDIT_MAX = 60;
/** Ticks a gap in the command numbers is waited on before the queue goes on without the missing one (100 ms). */
const GAP_WAIT = 6;
/** A command's stick past this, a button, or a turn counts as input for the idle kick. */
const ACTIVE_STICK = 0.05;
/** How far a round may leave from the shooter's eye as the server holds it (the client's muzzle and lean). */
const MUZZLE_SLACK = 40;
/** Ticks of history kept for the rewind: MAX_REWIND_MS and a margin. */
const HISTORY = Math.ceil((MAX_REWIND_MS / 1000) * TICK_HZ) + 12;
/**
 * The most commands a batch may carry (PL-9/PL-16 of the launch review): the client repeats its last
 * `COMMAND_REDUNDANCY` (3) in each; the rest is room for a batch after a lost frame. A longer batch is dropped whole, so a
 * frame costs at most this many inserts.
 */
export const MAX_BATCH = 16;
/** The commands a player's queue holds at most (10 s): a flood past it is dropped, not queued. */
const QUEUE_MAX = 600;
/**
 * The timed events (a round, a reload) waiting for their command to be run, at most; and how long one waits for it (the
 * queue's 10 s). A round is decided at its own command -- the mover, the cone and the clocks as they were then -- once
 * the command after it has run too (the page's look runs up to a tick ahead of the command it names).
 */
const PENDING_MAX = 32, PENDING_TICKS = QUEUE_MAX;
/** A name's longest before the lobby's own cut (the lobby trims to the game's; this refuses a flood first). */
const NAME_MAX = 256;

/** The kit a player is seated with, before its first spawn gives it its type's (a ghost's: it fires nothing). */
const SEATED_RECORDS = kitRecords(null, BAKED_LOADOUT);

/**
 * The throwables and charges without the disc's kit table (a test, a disc without `ZWEAPON.ZAR`): `@s2u/scene`'s
 * transcriptions and their rounds' `Piercing` (research 91 section 5, zweapon.rdr: the M67 4, the HE 1; the smoke,
 * the flash and the claymore 0). With the table, every record is the disc's (`KitTable.throwables`). What a player
 * carries of them is its loadout's pouch (`pouchOf`, web sprint 4 M7: POUCH_PLACEHOLDER and CLAYMORE_PLACEHOLDER
 * retired -- the claymore is in the match, placed by a `throw` of it and set off by its Detonator's).
 */
const BAKED_THROWN: ReadonlyMap<string, { record: ThrowableRecord; piercing: number }> = new Map([
  ['M67', { record: M67, piercing: 4 }], ['HE', { record: HE, piercing: 1 }], ['AN-M8', { record: AN_M8, piercing: 0 }],
  ['Mark141', { record: MARK141, piercing: 0 }], ['Claymore', { record: CLAYMORE, piercing: 0 }],
]);
/** The flashbang (`Mark141`, 123): a blast of no damage whose reach whites the screen out (`resolveBlast`'s `flash`). */
const FLASHBANG_ID = 123;
/** The fastest a throw leaves the hand (`throwVelocity`'s range at the most power, with slack), units a second. */
const THROW_SPEED_MAX = 400;
/**
 * M4: how far a launched round's speed may stand off its `Muzzle_Velocity` (`FUN_003cb1a0` L320727-320731: `MV x dir`,
 * the owner's inherited velocity aside), a fraction: the float of the page's direction times the speed (a server
 * tolerance, no game source).
 */
const ROUND_SPEED_SLACK_PLACEHOLDER = 0.01;
/** The dead's stick: at rest (the dead take no stick, `FUN_00592560`). */
const DEAD_STICK = { forward: 0, right: 0, boost: false } as const;
/** The head over the feet by posture, for the blast's line of sight to the head node (research 91 section 5). */
const HEAD_OVER: Readonly<Record<'stand' | 'crouch' | 'prone', number>> = { stand: 18.3, crouch: 11.1, prone: 1.7 };

/**
 * A projectile the room flies: its owner, its kind (the record's name on the wire) and its state; `facing` is a placed
 * claymore's front (its cone's axis, `claymoreCone`) or a backblast's axis (backwards from the launcher).
 */
interface Flying { owner: number; kind: string; g: Grenade; facing?: V3 }

interface Past { tick: number; feet: V3; yaw: number; posture: 'stand' | 'crouch' | 'prone'; alive: boolean }

/** A round or a reload waiting for its command (`PENDING_MAX`): the event and the tick it came. */
type Timed = { ev: Extract<ClientEvent, { type: 'fire' | 'reload' }>; at: number };

class Player {
  sim: MoverSim;
  readonly queue: Command[] = [];
  /** The command numbers in `queue` (PL-9: a batch's duplicates found at once, not by a walk of the queue). */
  readonly queued = new Set<number>();
  /** The tick a gap in the command numbers was first seen, or -1. */
  gapSince = -1;
  credit = CREDIT_MAX;
  /**
   * Commands run: the player's own clock, one a 60 Hz tick of its mover (the credit holds it to real time). The fire
   * rate and the reload lock count on it -- the game's wait is a clock timer (`kit+0x8b8 -= dt`, `FUN_005c0fd0`
   * 476545-476547), not a number the client sends.
   */
  ran = 0;
  lastActive: number;
  alive = false;
  health: Health = freshHealth();
  diedAt = -1;
  kills = 0; deaths = 0; score = 0;
  /** The round's score (the +5 and +1 bonuses and the side's total read it). */
  roundScore = 0;
  readonly history: Past[] = [];
  viewTick = 0;
  ping = 0;
  /**
   * The kit on the body (web sprint 4, M3/M4; `../../viewer/src/loadout`): five item ids, the character type's
   * `default_weapons` at each spawn (R94.7) -- and the records its two firearm slots hold, 2X applied, which every
   * per-weapon table below is read from: the rate, the reload's lock, the cone, the damage and its falloff.
   */
  loadout: Loadout = BAKED_LOADOUT;
  records: readonly [WeaponRecord, WeaponRecord] = SEATED_RECORDS;
  /**
   * The magazines, per weapon: the game's ring (`magazines.ts`, research 84 §18) -- the page's `Fire` counts with the
   * same, so a reload here takes the magazine the page's did; the command count each last fired at (`ran`).
   */
  mags: [MagazineRing, MagazineRing] = [ringFor(SEATED_RECORDS[0]), ringFor(SEATED_RECORDS[1])];
  lastFire: [number, number] = [-1e9, -1e9];
  /**
   * Per weapon, the command count its lock ends at (MJ-1; cleared by a swap) -- M4: the kit's **one** timer
   * (`kit+0x820`, `FUN_005c32b0` L477653-477680: a reload's `ReloadDelay` or the bolt's/pump's after-shot lock, one
   * flag between them) and then the clip it starts (a reload action: `FUN_005a7ab0` holds the fire while it plays).
   * `lockTimer` is where the timer part ends (the clip begins), `lockKind` which kind set it: a reload asked during an
   * after-shot timer replaces it (`FUN_005c32b0` rewrites `kit+0x820`), as the page's `Fire.reload` does.
   */
  reloadUntil: [number, number] = [-1, -1];
  lockTimer: [number, number] = [-1, -1];
  lockKind: [LockKind, LockKind] = [null, null];
  /** The weapon in hand as last seen (a change is a swap: the lock goes, the cone takes the record). */
  weapon: 0 | 1 = 0;
  /** The accuracy cone, run from the commands (OWNER-3, `ShotCone`). */
  cone = new ShotCone(SEATED_RECORDS[0]);
  /** Rounds and reloads waiting for their command. */
  readonly pending: Timed[] = [];
  trigger = false; aiming = false; boost = false;
  lastYaw = 0; lastPitch = 0;
  lastLanding: unknown = null;
  /** The pouch: the throwables and charges left, by name -- the loadout's (`pouchOf`), reset at a spawn. */
  grenades: Record<string, number> = pouchOf(BAKED_LOADOUT, null);
  /**
   * M7: the command count the kit's rate lets the next rocket go (`kit+0x8b8` with the round's `FireWait`, 3 s; the RPG's
   * after-shot lock, `ReloadDelayAfterShot` 1 s, feeds the next round inside it: `FUN_005c3000`, research 94 §C1.1).
   */
  rocketWaitUntil = -1;
  /**
   * M4 (`../../viewer/src/firearms`): the kit's launcher-round slots, each its own ring (the page's `KitRounds`); the
   * command count the last round left at, and the count the round's lock and its after-shot clip end at.
   */
  rounds = new KitRounds(null, BAKED_LOADOUT);
  /**
   * M4: the command count the primary's rate lets the next shot go after a launched round -- the kit's one rate timer
   * (`kit+0x8b8`, `FUN_005c09f0` with the redirected round's `FireWait`), shared by the carrier's rifle and its rounds.
   */
  roundWaitUntil = -1;
  /** M4: the shotgun's pull in progress (its weapon, command count, rays so far, and the victims it has hit once). */
  volley: { w: 0 | 1; count: number; rays: number; hit: Set<number> } | null = null;

  constructor(readonly id: number, public team: Team, sim: MoverSim, now: number) {
    this.sim = sim;
    this.lastActive = now;
  }
}

type RoundState =
  /**
   * Classic, before the match: a side has no player. The original launches only with players on both teams ("There must
   * be players on both teams to launch", `FUN_002c3cf0` L165325-165352, UIMnLOC 350/356); a dedicated room has no lobby,
   * so its players walk and respawn as in a respawn room until both sides are seated (CLASSIC_WAITING_PLACEHOLDER).
   */
  | { phase: 'waiting' }
  | { phase: 'play'; startedAt: number; endsAt: number }
  /** "TIME EXPIRED": the world plays on until `resultAt`. */
  | { phase: 'expired'; resultAt: number }
  /** Classic: a side eliminated; the world plays on until `resultAt` (`ELIMINATED_HOLD_S`), the clock still running. */
  | { phase: 'decided'; resultAt: number; winner: Team; endsAt: number }
  | { phase: 'over'; nextAt: number; matchOver: boolean };

export class Room {
  tick = 0;
  readonly lobby = new Lobby();
  private readonly conns = new Map<number, Conn>();
  private readonly players = new Map<number, Player>();
  private readonly opts: RoomOptions;
  round = 1;
  readonly wins = { seal: 0, terrorist: 0 };
  private state: RoundState;
  private readonly polys;
  private creditStep = 1;
  private lastStepAt: number | null = null;
  /** The rows changed (a join, a leave, a rename): one score event goes out at the next tick. */
  private scoreDirty = false;

  /**
   * The hit volumes (research 91 section 1.3): the SEAL skeleton's capsules at each posture's idle, built once here; one
   * skeleton serves both teams (the Terrorist models carry the same bones). Null: the placeholder capsules.
   */
  private readonly volumes: StanceVolumes | null;
  /**
   * DOORS (web/redotcom/docs/research/92-doors.md): the map's doors, run here -- a client's `door` event asks, the reach is
   * checked, the swing turns the leaf's polygons in the hull every mover reads -- and sent in every snapshot.
   */
  readonly doors: DoorSet;

  /**
   * The kit tables (web sprint 4; `../../viewer/src/loadout` `SimKits`): the disc's `ZWEAPON.ZAR` read at the server's
   * start and the map's kits; null (a test, a disc without them) seats everyone with the baked pair (`BAKED_LOADOUT`).
   */
  constructor(readonly map: SimMap, readonly clips: SimClips | null, opts: Partial<RoomOptions> = {}, body: SimSkeleton | null = null,
    private readonly kits: SimKits | null = null) {
    this.volumes = body ? stanceVolumes(body) : null;
    this.doors = new DoorSet(map.doors ?? [], map.ground);
    this.opts = { ...DEFAULT_OPTIONS, ...opts };
    this.opts.idleKickMs = Math.min(IDLE_KICK_MAX_MS, Math.max(IDLE_KICK_MIN_MS, this.opts.idleKickMs));
    this.polys = groundPolygons(map.ground);
    this.state = this.opts.rules === 'classic' ? { phase: 'waiting' } : { phase: 'play', startedAt: 0, endsAt: this.opts.roundSeconds * TICK_HZ };
  }

  get rules(): Rules { return this.opts.rules; }

  /**
   * Classic: a player seated while a round is in play is a ghost until the next ("You are a ghost.  You will play the
   * next round as a real player.", 0x3e31c0/0x3e31f0, `FUN_001f97b0` L57047-57097; UIMnLOC 352-353: late joiners
   * "appear as a ghost ... wait until the next round"): not alive, not placed, not counted a living player.
   */
  private seatsGhosts(): boolean {
    return this.opts.rules === 'classic' && this.state.phase !== 'waiting';
  }

  // ---- the sessions ----

  /** A client's hello: welcomed as a player or a spectator, or refused. Returns the id it was given, or null. */
  hello(id: number, conn: Conn, ev: Extract<ClientEvent, { type: 'hello' }>, address = ''): boolean {
    if (address && (this.banned.get(address) ?? -Infinity) > this.opts.now()) { this.refuse(conn, 'You have been banned from that game. Please choose another.'); return false; }
    if (ev.version !== PROTOCOL_VERSION) { this.refuse(conn, `protocol ${ev.version}, this server speaks ${PROTOCOL_VERSION}`); return false; }
    const joined = this.lobby.join(id, ev.name, this.opts.random, ev.watch === true, this.opts.solo ? 'seal' : undefined);
    if (!joined) { this.refuse(conn, 'The game is full.'); return false; }
    this.conns.set(id, conn);
    if (address) this.addresses.set(id, address);
    const m = joined.member;
    this.send(id, {
      type: 'welcome', id, version: PROTOCOL_VERSION, map: this.map.stem, tick: this.tick, role: m.role, team: m.team,
      queue: this.lobby.queuePosition(id), name: m.name,
      players: this.lobby.players().filter((p) => p.id !== id).map((p) => ({ id: p.id, name: p.name, team: p.team! })),
      rules: this.opts.rules, round: this.round, rounds: this.opts.maxRounds, ghost: m.role === 'player' && this.seatsGhosts(),
    });
    if (m.role === 'player') this.addPlayer(id, m.team!);
    this.broadcastChanges(joined.changes, id);
    this.send(id, this.scoreEvent());                          // the rows and the clock, for the joiner's HUD
    return true;
  }

  private refuse(conn: Conn, reason: string): void {
    conn.send(JSON.stringify({ type: 'refused', reason } satisfies ServerEvent));
    conn.close(4000, reason);
  }

  /** A client gone: its slot to the queue's head. */
  leave(id: number): void {
    if (!this.conns.delete(id)) return;
    this.players.delete(id);
    this.addresses.delete(id);
    // A voter's votes go with it; a target's with it too.
    this.votes.delete(id);
    for (const set of this.votes.values()) set.delete(id);
    this.broadcastChanges(this.lobby.leave(id));
  }

  private addPlayer(id: number, team: Team): void {
    const p = new Player(id, team, this.newSim(), this.opts.now());
    this.players.set(id, p);
    if (this.seatsGhosts()) { this.scoreDirty = true; return; }   // a ghost until the next round
    this.spawn(p, 'start');
  }

  private newSim(): MoverSim {
    const w = new Walker(this.map.grid);
    if (this.clips) w.actionRoots = this.clips.roots;
    const moves = new Traversal(this.map.grid, this.polys);
    if (this.clips) moves.setClips(this.clips.clips, this.clips.table);
    return new MoverSim(w, moves);
  }

  private broadcastChanges(changes: LobbyChange[], except?: number): void {
    if (changes.length) this.scoreDirty = true;
    for (const c of changes) {
      if (c.kind === 'joined') {
        const m = this.lobby.member(c.id)!;
        if (c.role === 'player') this.broadcast({ type: 'joined', id: c.id, name: m.name, team: c.team! }, except);
      } else if (c.kind === 'left') this.broadcast({ type: 'left', id: c.id });
      else if (c.kind === 'renamed') this.broadcast({ type: 'renamed', id: c.id, name: c.name });
      else if (c.kind === 'queue') this.send(c.id, { type: 'queue', position: c.position });
      else if (c.kind === 'promoted') {
        this.players.delete(c.id);
        // PL-8: a classic round in play seats it as a ghost (`addPlayer`), and it is told so, as the welcome tells a
        // late joiner (research 91 section 12, `FUN_001f97b0` L57047-57097).
        const ghost = this.seatsGhosts();
        this.addPlayer(c.id, c.team);
        this.send(c.id, { type: 'promoted', team: c.team, ghost });
        this.broadcast({ type: 'joined', id: c.id, name: this.lobby.member(c.id)!.name, team: c.team }, c.id);
      }
    }
    // A demoted player (W3.R13) is a spectator now: its mover goes.
    for (const id of [...this.players.keys()]) if (this.lobby.member(id)?.role !== 'player') { this.players.delete(id); this.broadcast({ type: 'left', id }); }
  }

  // ---- what arrives ----

  /** A binary frame: a command batch. */
  binary(id: number, bytes: Uint8Array): void {
    const p = this.players.get(id);
    if (!p) return;
    let batch;
    try { batch = decodeCommands(bytes); } catch { return; }
    if (batch.commands.length > MAX_BATCH) return;               // PL-9: a batch past the cap is dropped whole
    p.viewTick = Math.max(p.viewTick, batch.viewTick);
    // Frames can arrive out of order (the jitter): every command not yet run and not yet queued goes in, in order.
    for (const c of batch.commands) {
      if (c.seq <= p.sim.seq || p.queued.has(c.seq)) continue;
      let at = p.queue.length;
      while (at > 0 && p.queue[at - 1]!.seq > c.seq) at--;
      p.queue.splice(at, 0, c);
      p.queued.add(c.seq);
    }
    if (p.queue.length > QUEUE_MAX) {                            // a flood (10 s) is dropped, not queued
      for (const c of p.queue.splice(0, p.queue.length - QUEUE_MAX)) p.queued.delete(c.seq);
    }
  }

  /**
   * A text frame: a JSON event. Its fields are the client's, so each is shape-checked before anything reads it (BL-2 of
   * the launch review: one `{"type":"fire"}` read `from[0]` of nothing and threw out of the socket's handler, taking the
   * process down): a malformed event is dropped, never thrown.
   */
  text(id: number, raw: ClientEvent): void {
    const ev = raw as unknown as Record<string, unknown> | null;
    if (!ev || typeof ev !== 'object') return;
    switch (ev.type) {
      case 'ping':
        if (isNum(ev.t)) this.send(id, { type: 'pong', t: ev.t, tick: this.tick });
        return;
      case 'name':
        if (typeof ev.name === 'string' && ev.name.length <= NAME_MAX) this.broadcastChanges(this.lobby.rename(id, ev.name, this.opts.random));
        return;
      case 'score': this.send(id, this.scoreEvent()); return;
      case 'fire':
        if (isInt(ev.seq) && isInt(ev.viewTick) && isV3(ev.from) && isV3(ev.dir) && isV3(ev.eye) && isV3(ev.aim)) this.timed(id, raw as Timed['ev']);
        return;
      case 'reload':
        if (isInt(ev.seq)) this.timed(id, raw as Timed['ev']);
        return;
      case 'vote':
        if (isInt(ev.target) && typeof ev.remove === 'boolean') this.vote(id, ev.target, ev.remove);
        return;
      case 'throw':
        if (typeof ev.kind === 'string' && isInt(ev.seq) && isV3(ev.from) && isV3(ev.velocity)) {
          // M7: the throw message carries every equipment use, by the item's name (no new wire message: protocol.ts is
          // untouched) -- a throwable's throw, a charge set down (`velocity` its facing), the Detonator's fire, a
          // launcher's round or a rocket (`velocity` its launch).
          const e = raw as Extract<ClientEvent, { type: 'throw' }>;
          const kind = this.kindOf(ev.kind);
          if (kind === 'throwable') this.throwGrenade(id, e);
          else if (kind === 'placed' || kind === 'c4') this.placeCharge(id, e);
          else if (kind === 'detonator') this.detonate(id);
          else if (kind === 'round') this.launchRound(id, e);
        }
        return;
      case 'door':
        if (isInt(ev.door)) this.useDoor(id, ev.door);
        return;
      default: return;
    }
  }

  /**
   * A round or a reload: decided at its command (`seq`), once the command after it has run -- at once when it has, else
   * when it does (`run`). Kept in order; at most `PENDING_MAX` wait, each at most `PENDING_TICKS`.
   */
  private timed(id: number, ev: Timed['ev']): void {
    const p = this.players.get(id);
    if (!p) return;
    if (!p.pending.length && p.sim.seq > ev.seq) { this.decide(p, ev); return; }
    if (p.pending.length >= PENDING_MAX) return;
    p.pending.push({ ev, at: this.tick });
  }

  /** The waiting rounds and reloads whose command and the next have run, in order; the long-waiting ones dropped. */
  private settle(p: Player): void {
    while (p.pending.length) {
      const head = p.pending[0]!;
      if (p.sim.seq > head.ev.seq) { p.pending.shift(); this.decide(p, head.ev); continue; }
      if (this.tick - head.at > PENDING_TICKS) { p.pending.shift(); continue; }
      break;
    }
  }

  private decide(p: Player, ev: Timed['ev']): void {
    if (ev.type === 'fire') this.fire(p, ev); else this.reload(p, ev.seq);
  }

  // ---- the tick ----

  /** One 60 Hz step of the match. */
  step(): void {
    this.tick++;
    const now = this.opts.now();
    // The credit this step: a tick, or the wall time since the last step when that is more (a stall's dropped ticks).
    this.creditStep = this.lastStepAt === null ? 1 : Math.max(1, ((now - this.lastStepAt) / 1000) * TICK_HZ);
    this.lastStepAt = now;
    for (const p of this.players.values()) this.run(p, now);
    for (const p of this.players.values()) this.corpse(p);
    for (const p of this.players.values()) this.remember(p);
    this.doors.step(1 / TICK_HZ);
    this.flyGrenades();
    this.clock();
    if (!this.opts.solo) this.idle(now);
    if (this.scoreDirty) { this.scoreDirty = false; this.broadcast(this.scoreEvent()); }
    if (this.tick % Math.round(TICK_HZ / SNAPSHOT_HZ) === 0) this.snapshots();
  }

  /**
   * A dead SEAL's body, a tick on the room's clock: it goes on falling and playing its death (a thrown corpse lands, and
   * `Land forward` / `Land backwards` hold: `Walker.dead`) with the stick at rest and the facing it died with -- the
   * other screens draw it from the snapshots, and the page's locked walk ticks its own the same (`WalkMode.frame`).
   */
  private corpse(p: Player): void {
    if (p.alive || !p.sim.walker.dead) return;
    p.sim.walker.turn = 0;
    p.sim.walker.tick(DEAD_STICK);
  }

  /** A player's commands, in order, as far as its credit goes. */
  private run(p: Player, now: number): void {
    p.credit = Math.min(CREDIT_MAX, p.credit + this.creditStep);
    while (p.queue.length && p.credit >= 1) {
      // A gap (a command lost past the redundancy, or still on its way): wait for it a while, then go on without it.
      if (p.queue[0]!.seq > p.sim.seq + 1 && p.gapSince + GAP_WAIT > this.tick) { if (p.gapSince < 0) p.gapSince = this.tick; break; }
      p.gapSince = -1;
      const cmd = p.queue.shift()!;
      p.queued.delete(cmd.seq);
      p.credit--;
      p.ran++;
      const active = Math.abs(cmd.forward) > ACTIVE_STICK || Math.abs(cmd.right) > ACTIVE_STICK || (cmd.buttons & ~Button.Boost) !== 0
        || Math.abs(shortTurn(p.lastYaw, cmd.yaw)) > 0.5 || Math.abs(cmd.pitch - p.lastPitch) > 0.5;
      if (active) p.lastActive = now;
      p.lastYaw = cmd.yaw; p.lastPitch = cmd.pitch;
      if (!p.alive) {
        p.sim.seq = cmd.seq;
        // The dead's controller (`FUN_00592560` L451642-451730) reads the respawn press alone: no stick, no look.
        if ((cmd.buttons & Button.Action) && this.respawnReady(p)) this.spawn(p, 'respawn');
        this.settle(p);
        continue;
      }
      p.trigger = (cmd.buttons & Button.Trigger) !== 0;
      p.aiming = (cmd.buttons & Button.Aim) !== 0;
      p.boost = (cmd.buttons & Button.Boost) !== 0;
      p.sim.apply(cmd);
      this.aim(p, cmd);
      const landing = p.sim.walker.landing;
      if (landing && landing !== p.lastLanding) {
        p.lastLanding = landing;
        if (applyFall(p.health, landing.speed)) this.kill(p, null, null, 'fall');
      }
      this.settle(p);
    }
  }

  /**
   * After a command: a swap on the server's mover (`MoverSim.weapon`) takes the other record into the cone and clears
   * the reload locks (the page's `setWeapon` cancels its reload, `fire.ts`); then one tick of the cone (OWNER-3).
   */
  private aim(p: Player, cmd: Command): void {
    const w = p.sim.weapon;
    if (w !== p.weapon) {
      p.weapon = w;
      p.cone.setWeapon(p.records[w]);
      p.reloadUntil = [-1, -1];
      p.lockTimer = [-1, -1];
      p.lockKind = [null, null];
    }
    const walker = p.sim.walker, s = walker.state, moves = p.sim.moves;
    p.cone.tick(cmd, {
      feet: [s.x, s.y, s.z], velocity: [s.vx, s.vy, s.vz], airborne: walker.airborne, posture: walker.posture,
      moveRoot: moves?.rootY() ?? null, peek: moves?.peek() ?? 0, weapon: w,
    }, p.ran);
  }

  private remember(p: Player): void {
    const s = p.sim.walker.state;
    p.history.push({ tick: this.tick, feet: [s.x, s.y, s.z], yaw: s.yaw, posture: p.sim.walker.posture, alive: p.alive });
    if (p.history.length > HISTORY) p.history.shift();
  }

  // ---- spawns (research 91 section 4.2) ----

  private sideOf(team: Team): 0 | 1 {
    // Team words 0x40000001 (SEALs) take side 0 while the sides are not swapped (research 91 section 4.2, 7).
    return team === 'seal' ? 0 : 1;
  }

  /**
   * `FUN_002b7ee0`: of the side's respawn records, the one whose nearest living enemy is farthest; with no enemy, one
   * at random. At a round's start the side's slots (key 0/2), at random (a respawn game, L158760-158787).
   * RESPAWN_BLOCK_PLACEHOLDER: the game searches the player slot's block of `count/24` records; the slot's link to the
   * lobby is not traced (research 91 section 4.2), so the whole side's records are searched.
   */
  private pick(p: Player, kind: 'start' | 'respawn'): SpawnSlot | null {
    const side = this.sideOf(p.team);
    const pool = (kind === 'respawn' ? this.map.respawns : this.map.slots).filter((s) => s.side === side);
    const list = pool.length ? pool : this.map.slots.filter((s) => s.side === side);
    if (!list.length) return null;
    if (kind === 'start' && this.opts.rules === 'classic' && this.state.phase !== 'waiting') {
      // A non-respawn game's round start takes the player slot's own record (`+0xfc8`, L158760-158787), not one at
      // random. START_SLOT_LINK_PLACEHOLDER: the player slot's link to the lobby is not traced (research 91 section
      // 4.2), so the player's place among its side's players (by id) stands in for it.
      const k = [...this.players.values()].filter((q) => q.team === p.team).map((q) => q.id).sort((a, b) => a - b).indexOf(p.id);
      const ordered = [...list].sort((a, b) => a.index - b.index);
      return ordered.find((s) => s.index === k) ?? ordered[Math.max(0, k) % ordered.length]!;
    }
    const enemies = [...this.players.values()].filter((q) => q !== p && q.alive && q.team !== p.team);
    if (kind === 'start' || !enemies.length) return list[Math.floor(this.opts.random() * list.length)]!;
    let best = list[0]!, bestD = -1;
    for (const s of list) {
      let near = Infinity;
      for (const e of enemies) {
        const st = e.sim.walker.state;
        near = Math.min(near, (st.x - s.position[0]) ** 2 + (st.y - s.position[1]) ** 2 + (st.z - s.position[2]) ** 2);
      }
      if (near > bestD) { bestD = near; best = s; }
    }
    return best;
  }

  private spawn(p: Player, kind: 'start' | 'respawn'): void {
    const slot = this.pick(p, kind);
    const after = p.sim.seq;
    const sim = this.newSim();
    sim.seq = after;
    const at: V3 = slot ? [slot.position[0], slot.position[1] + SPAWN_LIFT, slot.position[2]] : [0, 0, 0];
    // The facing: step k points along (sin 45k, -cos 45k); `Pose.yaw` faces (-sin yaw, -cos yaw).
    const yaw = slot ? wrapYaw(-slot.step * 45) : 0;
    // PL-2: the floor is picked as the walking tick picks it -- the probe from the feet + `PROBE_LIFT` (`FUN_005b0420` ->
    // `FUN_005b5d40` L470230-470240: the highest hit at or under origin + 1; research 86 s6.3) -- on the record lifted a
    // unit (`FUN_002b8100` L158793). From the eye (feet + 16.4) it stood four Frostfire records on an object 12 up.
    // The page's respawn (`walk.ts` `respawn`) places from the same origin.
    sim.walker.place(at[0], at[1] + PROBE_LIFT, at[2]);
    sim.walker.state.yaw = yaw;
    p.sim = sim;
    p.alive = true;
    p.health = freshHealth();
    // A full kit at every spawn, a round's start included: `FUN_00598b90(p, 0)` (the round's reload, `FUN_00223680`
    // L75931) rebuilds the actor through `FUN_00599b60` (L455158), whose `FUN_00599f00` (L455674) gives the type's
    // `default_weapons` at `Ammo_Capacity` x `NumMags` (research 91 section 4.3): the type's kit (R94.7; the side's
    // first type, DEFAULT_CHARTYPE_PLACEHOLDER), or in the page's own room the page's developer kit.
    p.loadout = (this.opts.solo ? this.opts.soloKit?.() : null) ?? typeLoadout(this.kits?.map ?? null, p.team) ?? BAKED_LOADOUT;
    p.records = kitRecords(this.kits?.table ?? null, p.loadout);
    p.mags = [ringFor(p.records[0]), ringFor(p.records[1])];
    // The new body's kit is at rest: no reload playing, the rifle in hand, the cone at its floor (`Accuracy.reset`).
    p.reloadUntil = [-1, -1];
    p.lastFire = [-1e9, -1e9];
    p.weapon = 0;
    p.cone = new ShotCone(p.records[0]);
    p.lastLanding = null;
    p.grenades = pouchOf(p.loadout, this.kits?.table ?? null);        // M7: the loadout's pouch (POUCH_PLACEHOLDER retired)
    p.rounds = new KitRounds(this.kits?.table ?? null, p.loadout);   // M4: every round slot full
    p.rocketWaitUntil = -1;
    p.roundWaitUntil = -1;
    p.lockTimer = [-1, -1];
    p.lockKind = [null, null];
    p.volley = null;
    p.history.length = 0;
    const s = sim.walker.state;
    this.broadcast({ type: 'spawn', id: p.id, at: [s.x, s.y, s.z], yaw, after });
  }

  private respawnReady(p: Player): boolean {
    // Classic: no respawn -- the respawn option is off (`FUN_002a7560` L149405-149431); the dead spectate until the next
    // round (`FUN_005979a0` L454484-454489). Only the waiting room (CLASSIC_WAITING_PLACEHOLDER) lets one up.
    if (this.opts.rules === 'classic' && this.state.phase !== 'waiting') return false;
    return this.state.phase !== 'over' && p.diedAt >= 0 && (this.tick - p.diedAt) / TICK_HZ >= Math.max(RESPAWN_PRESS_S, RESPAWN_FADE_S);
  }

  // ---- fire (W3.R4) ----

  /**
   * A round (W3.R4), decided at its command (`timed`): the weapon is the server's mover's (the kit's selected slot
   * `+0x824`, set only by the swap: `FUN_005c0fd0` 476592-476625, `FUN_005bd030` 474178), never the event's; its rate
   * and its reload's lock count on the player's own command clock (`Player.ran`); the round must leave from the body,
   * not through a wall; its eye and aim must be the page's camera's and inside the cone the server's own run of the
   * accuracy allows (`ShotCone`, OWNER-3).
   */
  private fire(p: Player, ev: Extract<ClientEvent, { type: 'fire' }>): void {
    const id = p.id;
    if (!p.alive || this.state.phase === 'over') return;
    const frame = p.cone.frame(ev.seq);
    if (!frame) return;                                        // not a command this body ran
    const w = frame.weapon;
    const record = p.records[w];
    // BL-1: the rate is the weapon's fastest enabled mode -- `FUN_005c09f0` (476313-476335): `FireWait` in mode 1,
    // `FireWait` x 0.8 in burst and automatic (research 84 s6) -- less a tick for the page's frame-quantised clock. The
    // server does not know the page's mode; a slower mode only fires slower.
    const fastest = Math.min(...record.fireModes.filter((m) => m > 0).map((m) => fireInterval(record.fireWait, m)), record.fireWait);
    // M4: a shotgun's pull is `NumProjectilesFired` rays at one command, one shell (`FUN_005be9a0` L475580-475677):
    // the rays after the first ride the volley the first opened -- no rate, no second shell.
    const pellets = pelletsOf(record);
    const v = p.volley;
    const ofVolley = pellets > 1 && v !== null && v.w === w && v.count === frame.count && v.rays < pellets;
    if (!ofVolley) {
      if (frame.count - p.lastFire[w] < fastest * TICK_HZ - 1) return;
      if (frame.count < p.reloadUntil[w] || p.mags[w].rounds() <= 0) return;
      if (w === 0 && frame.count < p.roundWaitUntil) return;       // M4: a launched round's FireWait, the same timer
    }
    const from = ev.from;
    const [fx, fy, fz] = frame.feet;
    if (Math.hypot(from[0] - fx, from[1] - (fy + EYE_HEIGHT), from[2] - fz) > MUZZLE_SLACK) return;
    // BL-3: the muzzle is on the near side of every wall from the body (the look-at target's point, `targetHeight`).
    if (segmentHit(this.map.grid, [fx, fy + targetHeight(frame.posture, frame.moveRoot), fz], from)) return;
    const d = ev.dir;
    const len = Math.hypot(d[0], d[1], d[2]);
    if (!(len > 0.5 && len < 1.5)) return;
    const dir: V3 = [d[0] / len, d[1] / len, d[2] / len];
    // OWNER-3: the eye, the aim inside the cone, and the round down the eye's ray.
    if (p.cone.check(ev.seq, { eye: ev.eye, aim: ev.aim, from, dir }) !== null) return;
    if (ofVolley) v!.rays++;
    else {
      p.lastFire[w] = frame.count;
      p.mags[w].fire();
      p.volley = pellets > 1 ? { w, count: frame.count, rays: 1, hit: new Set() } : null;
      // M4: the bolt's or the pump's lock (`FUN_005c5340` L479321-479343) and then its after-shot clip, which holds the
      // fire as a reload does (`FUN_005a7ab0`): the weapon's lock runs on to their end, on the command clock.
      const lock = afterShotLock(record.id, record, p.mags[w].rounds(), record.id);
      if (lock !== null) {
        const family = reloadFamily({ item: w ? 'pistol' : 'rifle', id: record.id, afterShot: true });
        const clip = this.clips ? reloadSeconds(this.clips.clips, this.clips.table, frame.posture, reloadMoving(...frame.velocity), family, record.reloadTime ?? 0) ?? 0 : 0;
        setLock(p, w, frame.count, lock, clip, 'afterShot');
      }
    }
    p.cone.round(ev.seq);
    const reach = record.maximumRange * UNITS_PER_METRE;
    // The rewind: the others where the shooter saw them, at most MAX_REWIND_MS back.
    const earliest = this.tick - Math.round((MAX_REWIND_MS / 1000) * TICK_HZ);
    const at = Math.max(earliest, Math.min(this.tick, ev.viewTick));
    const extra: ExtraSurface[] = [];
    for (const q of this.players.values()) {
      if (q === p || !q.alive) continue;
      const past = this.past(q, at);
      if (!past || !past.alive) continue;
      // Skip a body the ray passes nowhere near (the cylinder round its feet).
      if (!nearRay(from, dir, reach, past.feet)) continue;
      const hit = rayBody(from, dir, reach, bodyVolumes(past.feet, past.yaw, past.posture, this.volumes));
      if (!hit) continue;
      const point: V3 = [from[0] + dir[0] * hit.t, from[1] + dir[1] * hit.t, from[2] + dir[2] * hit.t];
      // A body stops the round (PENETRATION 0: flesh is not in the materials' table; research 91 section 1.3).
      extra.push({ distance: hit.t, penetration: 0, point, normal: [-dir[0], -dir[1], -dir[2]], tag: { id: q.id, part: hit.part } });
    }
    const path = roundPath(this.map.grid, [...from], dir, reach, () => 0.5, record.piercing, extra);
    const struck = path.struck.find((s2) => s2.tag !== undefined);
    const end = path.hit ? path.hit.point : path.end;
    this.broadcast({
      type: 'shot', id, weapon: w, from: [...from], to: [...end],
      normal: path.hit && path.hit.tag === undefined ? path.hit.normal : null, material: path.hit?.material ?? null,
    }, id);
    if (!struck) return;
    const { id: victimId, part } = struck.tag as { id: number; part: number };
    const victim = this.players.get(victimId);
    if (!victim || !victim.alive) return;
    if (victim.team === p.team) return;                        // friendly fire off (W3.R11, the create-game default)
    if (pellets > 1) { this.volleyHit(p, victim, record, struck.distance, from); return; }
    const dmg = bulletDamage(record, struck.distance);
    if (dmg === null) return;
    const died = applyHit(victim.health, part, dmg, record.piercing);
    this.send(victimId, { type: 'hurt', health: [...victim.health.hp], from: [...from], part });
    if (died) this.kill(victim, p, record.name, 'weapon', deathClip('bullet', part, victim.sim.walker.posture, this.opts.random));
    void overall;
  }

  /**
   * M4 (research 94 §C2.1, R94.10; research 91 §1.1): a shotgun's ray on a victim -- honoured **once a volley** (the
   * victim's `+0x1048` guard, `FUN_005abbc0` L464704-464737), whatever part it met: the receiver re-counts the pellets by
   * the range (`shotgunPellets`, `FUN_005a1620`), each to a part by the fragments' table (`fragmentPart`, `DAT_00650900`
   * / `DAT_006508f8`) at `pelletDamage` (`SHOTGUN_MP_PELLET_DAMAGE_SCALE_READING`), the ammo's piercing; the last
   * pellet's part names the death. The push it sets (`FUN_0057ed10`) has no traced reader: `BLOWBACK_CONSUMER_READING`.
   */
  private volleyHit(p: Player, victim: Player, record: WeaponRecord, distance: number, from: V3): void {
    const volley = p.volley;
    if (!volley || volley.hit.has(victim.id)) return;
    volley.hit.add(victim.id);
    const dmg = pelletDamage(record, distance);
    if (dmg === null) return;
    const n = shotgunPellets(distance, this.opts.random);
    let part = -1, died = false;
    for (let i = 0; i < n && !died; i++) {
      part = fragmentPart(this.opts.random);
      died = applyHit(victim.health, part, dmg, record.piercing);
    }
    if (part < 0) return;
    this.send(victim.id, { type: 'hurt', health: [...victim.health.hp], from: [...from], part });
    if (died) this.kill(victim, p, record.name, 'weapon', deathClip('bullet', part, victim.sim.walker.posture, this.opts.random));
  }

  // ---- doors (web/redotcom/docs/research/92-doors.md) ----

  /**
   * A client's action on the door under its reticle: taken from a living player within the door's reach of its leaf
   * (the client picked it as the game does, `pickDoor`; the server, which does not see the view, checks the reach);
   * `DoorSet.use` refuses it mid-swing, as `FUN_002b44e0` does.
   */
  private useDoor(id: number, door: number): void {
    const p = this.players.get(id);
    if (!p || !p.alive || !Number.isInteger(door) || door < 0 || door >= this.doors.count) return;
    const s = p.sim.walker.state;
    if (!doorInReach(this.doors, door, [s.x, s.y, s.z])) return;
    this.doors.use(door, [s.x, s.y, s.z]);
  }

  // ---- grenades (research 85, 91 section 5) and the equipment (web sprint 4 M7, research 94 §C4-§C5) ----

  private readonly flying: Flying[] = [];
  private cast: HullCast | null = null;

  /** An item's record by its name: the kit table's, else the baked transcriptions' (`BAKED_THROWN`); null for none. */
  private itemByName(name: string): { id: number } | null {
    const item = this.kits?.table.arsenal.byName.get(name);
    if (item) return item;
    const baked = BAKED_THROWN.get(name);
    return baked ? { id: baked.record.id } : name === 'Detonator' ? { id: ITEM.DETONATOR } : null;
  }

  /** What a `throw` of `name` is (`../../viewer/src/equipment` `equipmentKind`), 'none' for a name no record has. */
  private kindOf(name: string): ReturnType<typeof equipmentKind> {
    const item = this.itemByName(name);
    return item ? equipmentKind(item.id) : 'none';
  }

  /** A throwable's or a charge's record and piercing by name: the disc's (`KitTable.throwables`), else the baked. */
  private throwable(name: string): { record: ThrowableRecord; piercing: number } | null {
    const item = this.kits?.table.arsenal.byName.get(name);
    const t = item ? this.kits?.table.throwables?.get(item.id) : undefined;
    return t ?? BAKED_THROWN.get(name) ?? null;
  }

  private throwGrenade(id: number, ev: Extract<ClientEvent, { type: 'throw' }>): void {
    const p = this.players.get(id), t = this.throwable(ev.kind);
    if (!p || !p.alive || !t || this.state.phase === 'over' || !((p.grenades[ev.kind] ?? 0) > 0)) return;
    const s = p.sim.walker.state;
    if (Math.hypot(ev.from[0] - s.x, ev.from[1] - (s.y + EYE_HEIGHT), ev.from[2] - s.z) > MUZZLE_SLACK) return;
    // BL-3: the hand is on the body's side of the walls, as the muzzle is.
    const look = targetHeight(p.sim.walker.posture, p.sim.moves?.rootY() ?? null);
    if (segmentHit(this.map.grid, [s.x, s.y + look, s.z], ev.from)) return;
    if (!(Math.hypot(...ev.velocity) <= THROW_SPEED_MAX)) return;
    p.grenades[ev.kind]!--;
    this.flying.push({ owner: id, kind: ev.kind, g: launchGrenade([...ev.from], [...ev.velocity], t.record) });
    this.broadcast({ type: 'grenade', id, kind: ev.kind, from: [...ev.from], velocity: [...ev.velocity] }, id);
  }

  /** The charges a player has down (`FUN_003cc1f0` over the placed list 0x4b5220, by owner). */
  private chargesDown(id: number): number {
    return this.flying.filter((f) => f.owner === id && f.facing !== undefined && f.g.state === 'rest' && f.kind !== 'Backblast').length;
  }

  /**
   * M7 (research 94 §C5, research 85 §9.7): a charge set down -- the page's `throw` of the claymore, the PMN or C4 at the
   * point its placing found (`FUN_005c2430`), `velocity` the SEAL's facing (a unit vector: the claymore's cone). From a
   * living player whose pouch holds one, at its hand's reach (`MUZZLE_SLACK` of the eye) on the body's side of the walls,
   * not moving (`CLAYMORE_RULES.maxSpeed`, `FUN_005be9a0` L475306-475337); the claymore and the PMN refused once
   * `maxPlaced` are down, C4 only at a C4 target, still (`c4Plant`: `C4_TARGET_READING`, `C4_STILL_READING`). Laid at
   * rest: C4's `Timer1` (6 s) runs from here; the claymore's and the PMN's are held (`holdsFuse`).
   */
  private placeCharge(id: number, ev: Extract<ClientEvent, { type: 'throw' }>): void {
    const p = this.players.get(id), t = this.throwable(ev.kind);
    if (!p || !p.alive || !t || this.state.phase === 'over' || !((p.grenades[ev.kind] ?? 0) > 0)) return;
    const facing = ev.velocity, l = Math.hypot(...facing);
    if (!(Math.abs(l - 1) <= 0.01)) return;
    const s = p.sim.walker.state, speed = Math.hypot(s.vx, s.vz);
    if (Math.hypot(ev.from[0] - s.x, ev.from[1] - (s.y + EYE_HEIGHT), ev.from[2] - s.z) > MUZZLE_SLACK) return;
    const look = targetHeight(p.sim.walker.posture, p.sim.moves?.rootY() ?? null);
    if (segmentHit(this.map.grid, [s.x, s.y + look, s.z], ev.from)) return;
    if (t.record.id === ITEM.C4) {
      if (!c4Plant(this.map.c4Targets ?? [], [s.x, s.y, s.z], speed)) return;
    } else if (speed > CLAYMORE_RULES.maxSpeed || this.chargesDown(id) >= CLAYMORE_RULES.maxPlaced) return;
    p.grenades[ev.kind]!--;
    const g = launchGrenade([...ev.from], [0, 0, 0], t.record);
    g.state = 'rest';
    this.flying.push({ owner: id, kind: ev.kind, g, facing: [facing[0] / l, facing[1] / l, facing[2] / l] });
    this.broadcast({ type: 'grenade', id, kind: ev.kind, from: [...ev.from], velocity: [...ev.velocity] }, id);
  }

  /**
   * M7 (research 85 §9.7.1): the Detonator's fire -- `CZKit_DetonateRemoteExplosives` (0x5c0130) sets off every claymore
   * of this player's (`+0xc5`: never a PMN or C4) within `CLAYMORE_RULES.detonateRange` of the player (`+0x1c`), the
   * next tick (`trigger`, `+0xc4`). The others are told (a `grenade` of the Detonator from the player's feet), so their
   * pages set off their copies of his claymores within the same reach (`GrenadeThrower.launchRemote`).
   */
  private detonate(id: number): void {
    const p = this.players.get(id);
    if (!p || !p.alive || this.state.phase === 'over') return;
    const s = p.sim.walker.state;
    for (const f of this.flying) {
      if (f.owner !== id || f.g.record.id !== CLAYMORE.id || f.g.state !== 'rest') continue;
      if (Math.hypot(f.g.pos[0] - s.x, f.g.pos[1] - s.y, f.g.pos[2] - s.z) <= CLAYMORE_RULES.detonateRange) f.g.trigger = true;
    }
    this.broadcast({ type: 'grenade', id, kind: 'Detonator', from: [s.x, s.y, s.z], velocity: [0, 0, 0] }, id);
  }

  /**
   * M4 (research 94 §C4.2-§C4.3, R94.8): a launcher's round, the page's `throw` of it by name -- taken from a living
   * player whose primary is a carrier (`isCarrier`) in hand, the round one it fires (`roundFits`) with rounds left in a
   * kit slot (`KitRounds`, the redirect `FUN_005c6600`), leaving from the body's side of the walls at the round's
   * `Muzzle_Velocity` (the page lofts the direction, not the speed); the round's `FireWait` apart and past its lock and
   * after-shot clip (`afterShotLock`: the M203 rounds' 0.5 s then `Rifle m203 reload`; none on the MGL). One off its
   * slot; flown here as the grenades are (`launchGrenade`/`stepGrenade`: the fall, the arming dud, the impact) and its
   * blast dealt as theirs (`blast`). M7: a rocket's round goes to `launchRocket`.
   */
  private launchRound(id: number, ev: Extract<ClientEvent, { type: 'throw' }>): void {
    const p = this.players.get(id), item = this.kits?.table.arsenal.byName.get(ev.kind);
    if (item && itemClass(item.id) === 'rocketRound') { this.launchRocket(id, ev, item.id); return; }
    if (!p || !p.alive || !item || this.state.phase === 'over' || p.sim.weapon !== 0) return;
    const carrier = p.loadout[0];
    if (!isCarrier(carrier) || !roundFits(carrier, item.id)) return;
    const round = p.rounds.round(item.id), ring = p.rounds.ring(item.id);
    if (!round || !ring || ring.rounds() <= 0) return;
    const s = p.sim.walker.state;
    if (Math.hypot(ev.from[0] - s.x, ev.from[1] - (s.y + EYE_HEIGHT), ev.from[2] - s.z) > MUZZLE_SLACK) return;
    const look = targetHeight(p.sim.walker.posture, p.sim.moves?.rootY() ?? null);
    if (segmentHit(this.map.grid, [s.x, s.y + look, s.z], ev.from)) return;
    const mv = round.record.muzzleVelocity, speed = Math.hypot(...ev.velocity);
    if (!(mv > 0) || !(Math.abs(speed - mv) <= mv * ROUND_SPEED_SLACK_PLACEHOLDER)) return;
    const count = p.ran;
    // M4: the kit's one lock (`kit+0x820`: a rifle reload, a round's after-shot) and its one rate timer (`kit+0x8b8`: the
    // rifle's last round at its fastest mode's wait, as `fire` rates it), shared with the carrier's rifle.
    const rifle = p.records[0];
    const fastest = Math.min(...rifle.fireModes.filter((m) => m > 0).map((m) => fireInterval(rifle.fireWait, m)), rifle.fireWait);
    if (count < p.reloadUntil[0] || count < p.roundWaitUntil || count - p.lastFire[0] < fastest * TICK_HZ - 1) return;
    ring.fire();
    p.roundWaitUntil = count + Math.round(round.fireWait * TICK_HZ) - 1;
    const lock = afterShotLock(carrier, round, ring.rounds(), carrier);
    if (lock !== null) {
      const v = [s.vx, s.vy, s.vz] as const;
      const clip = this.clips ? reloadSeconds(this.clips.clips, this.clips.table, p.sim.walker.posture, reloadMoving(...v), reloadFamily({ item: 'rifle', id: carrier, afterShot: true, roundMode: true })) ?? 0 : 0;
      setLock(p, 0, count, lock, clip, 'afterShot');
    }
    const dir: V3 = [ev.velocity[0] / mv, ev.velocity[1] / mv, ev.velocity[2] / mv];   // `launchGrenade` scales by MV
    this.flying.push({ owner: id, kind: ev.kind, g: launchGrenade([...ev.from], dir, round.record) });
    this.broadcast({ type: 'grenade', id, kind: ev.kind, from: [...ev.from], velocity: [...ev.velocity] }, id);
  }

  /**
   * M7 (research 94 §C4, R94.6/R94.9): a rocket -- the page's `throw` of the LAW HEAT or the RPG round. Taken from a
   * living player whose kit holds the launcher that fires it in an equipment slot (`rocketRoundOf`: the rockets are
   * equipment, SlotCost 2, the paired slot its round) with a round left (`KitRounds`: the LAW HEAT's one; the RPG's
   * slots fed one at a time, `FUN_005c3000`), from the eye's reach on the body's side of the walls, at the round's
   * `Muzzle_Velocity` (`ROCKET_LAUNCH_SPEED_READING`); the round's `FireWait` (3 s, `kit+0x8b8`) apart, which covers its
   * after-shot feed (`ReloadDelayAfterShot` 1 s). Flown here -- `AccelerationFactor` along the flight, no fall, the arming
   * dud inside 100 u, the impact blast (20 in 15 m) -- and its backblast fired at once from the muzzle backwards
   * (`FUN_003d2d70`: the `Backblast` record, 6 in 7 m, reaching only inside its cone: `blast`).
   */
  private launchRocket(id: number, ev: Extract<ClientEvent, { type: 'throw' }>, roundId: number): void {
    const p = this.players.get(id);
    if (!p || !p.alive || this.state.phase === 'over') return;
    if (!EQUIPMENT_SLOTS.some((i) => rocketRoundOf(p.loadout[i]!) === roundId)) return;
    const round = p.rounds.round(roundId), ring = p.rounds.ring(roundId);
    if (!round || !ring || ring.rounds() <= 0) return;
    const s = p.sim.walker.state;
    if (Math.hypot(ev.from[0] - s.x, ev.from[1] - (s.y + EYE_HEIGHT), ev.from[2] - s.z) > MUZZLE_SLACK) return;
    const look = targetHeight(p.sim.walker.posture, p.sim.moves?.rootY() ?? null);
    if (segmentHit(this.map.grid, [s.x, s.y + look, s.z], ev.from)) return;
    const mv = round.record.muzzleVelocity, speed = Math.hypot(...ev.velocity);
    if (!(mv > 0) || !(Math.abs(speed - mv) <= mv * ROUND_SPEED_SLACK_PLACEHOLDER)) return;
    if (p.ran < p.rocketWaitUntil) return;
    ring.fire();
    p.rocketWaitUntil = p.ran + Math.round(Math.max(round.fireWait, round.reloadAfterShot ? round.reloadDelayAfterShot : 0) * TICK_HZ) - 1;
    const dir: V3 = [ev.velocity[0] / mv, ev.velocity[1] / mv, ev.velocity[2] / mv];
    this.flying.push({ owner: id, kind: ev.kind, g: launchGrenade([...ev.from], dir, round.record) });
    this.broadcast({ type: 'grenade', id, kind: ev.kind, from: [...ev.from], velocity: [...ev.velocity] }, id);
    const back = round.record.hasBackblast ? this.backblastRecord() : null;
    if (back) {
      // BACKBLAST_ORIGIN_READING (`backblastLaunch`): the muzzle, backwards; MV 0 and Timer1 0 -- it goes off where it
      // leaves, on the next tick.
      const axis: V3 = [-dir[0], -dir[1], -dir[2]];
      this.flying.push({ owner: id, kind: back.name, g: launchGrenade([...ev.from], [0, 0, 0], back), facing: axis });
    }
  }

  /** The `Backblast` record (159) of the kit table, null without it. */
  private backblastRecord(): ThrowableRecord | null {
    return this.kits?.table.throwables?.get(ITEM.BACKBLAST)?.record ?? null;
  }

  /** What a flying `kind` goes off as: a throwable or charge (the kit table's, else baked), or a launcher round or rocket. */
  private thrown(kind: string): { record: ThrowableRecord; piercing: number; fragments: boolean } | null {
    const t = this.throwable(kind);
    if (t) return { ...t, fragments: t.record.explosionDamage > 0 };
    const item = this.kits?.table.arsenal.byName.get(kind);
    const round = item ? this.kits?.table.rounds.get(item.id) : undefined;
    return round ? { record: round.record, piercing: round.piercing, fragments: round.record.explosionDamage > 0 } : null;
  }

  /**
   * Every grenade in the air one tick on (the page's own `FLIGHT_TICK` is the game's 60 Hz too); a blast's damage. M7:
   * an armed PMN is tripped by any living actor inside its `ProximityDistance` first (`proximityTripped`,
   * `FUN_00543930`; `PMN_FRIENDLY_READING`: its owner and his team too), and a round that goes off on impact meets the
   * bodies as well as the hull (`bodyCast`).
   */
  private flyGrenades(): void {
    if (!this.flying.length) return;
    this.cast ??= gridCast(this.map.grid);
    const origins = [...this.players.values()].filter((q) => q.alive).map((q) => { const w = q.sim.walker.state; return [w.x, w.y, w.z] as const; });
    for (const f of this.flying) {
      if (f.g.record.proximity !== undefined) proximityTripped(f.g, origins);
      const cast = f.g.record.impact && f.g.state === 'flight' ? this.bodyCast(this.cast, f.owner) : this.cast;
      for (const e of stepGrenade(f.g, 1 / TICK_HZ, cast)) if (e.kind === 'explode') this.blast(f, e.point);
    }
    for (let i = this.flying.length - 1; i >= 0; i--) if (this.flying[i]!.g.state === 'removed') this.flying.splice(i, 1);
  }

  /**
   * M7: the hull and the living bodies along a segment, nearest first -- a body met as the `PERSON` material (SOILS:
   * PENETRATION 0.97, a hit `HandleImpact` 0x3c8920 sets an explosive round off at, research 85 §5), through the same
   * capsules a round meets (`bodyVolumes`, `rayBody`). Only a round that goes off on impact asks it: the hand grenades
   * keep the hull (their bounce off a body, `DAT_003e14f8`, is not modelled here). The owner's own body is passed
   * over, as a bullet leaves its shooter's (`fire`: `q === p` skipped).
   */
  private bodyCast(hull: HullCast, owner: number): HullCast {
    const person = SOILS.find((m) => m.name === 'PERSON')!;
    return (a, b) => {
      const hits: HullHit[] = hull(a, b);
      const d: V3 = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], reach = Math.hypot(...d);
      if (!(reach > 0)) return hits;
      const dir: V3 = [d[0] / reach, d[1] / reach, d[2] / reach];
      for (const q of this.players.values()) {
        if (!q.alive || q.id === owner) continue;
        const w = q.sim.walker.state, feet: V3 = [w.x, w.y, w.z];
        if (!nearRay(a, dir, reach, feet)) continue;
        const hit = rayBody(a, dir, reach, bodyVolumes(feet, w.yaw, q.sim.walker.posture, this.volumes));
        if (hit) hits.push({ point: [a[0] + dir[0] * hit.t, a[1] + dir[1] * hit.t, a[2] + dir[2] * hit.t], normal: [-dir[0], -dir[1], -dir[2]], material: person, t: hit.t / reach });
      }
      return hits.sort((x, y) => x.t - y.t);
    };
  }

  /**
   * A blast (`../../viewer/src/net/blast` `resolveBlast`; research 85 section 7, 91 section 5): each living SEAL it
   * reaches -- the thrower too; friendly fire off spares the thrower's team -- rings, takes its fragments, and is knocked
   * (its mover here, and the page's prediction by the `blast` event). A SEAL killed by it is thrown too, as the game
   * throws the dead (`FUN_0057e770` L440981, state 8 at L441001; `blastKnock` with `died`): the knock is laid and sent
   * before the `kill`, so the page's own prediction lays it while still alive and then holds the landing down (`Walker.
   * dead`); prone, the corpse plays the BODY list's prone clip instead (L441013-441015, `deathClip('blast', ...)`).
   * M7 (`GetDamage` 0x3c7600 L318770-318826): a claymore's damage is a 32nd outside its cone (`claymoreCone` about its
   * facing); a backblast's is none outside its cone (`backblastReaches`, online).
   */
  private blast(f: Flying, at: readonly number[]): void {
    const t = this.thrown(f.kind);
    if (!t) return;
    const thrower = this.players.get(f.owner) ?? null;
    const point: V3 = [at[0]!, at[1]!, at[2]!];
    for (const q of [...this.players.values()]) {
      if (!q.alive) continue;
      if (thrower && q !== thrower && q.team === thrower.team) continue;
      const s = q.sim.walker.state, posture = q.sim.walker.posture;
      const feet: V3 = [s.x, s.y, s.z];
      let record = t.record;
      if (f.facing && record.id === ITEM.BACKBLAST && !backblastReaches(point, f.facing, feet, record.explosionRadius)) continue;
      if (f.facing && record.id === CLAYMORE.id && !claymoreCone([feet[0] - point[0], feet[1] - point[1], feet[2] - point[2]], f.facing, record.explosionRadius)) {
        record = { ...record, explosionDamage: record.explosionDamage / 32 };
      }
      const kind = { record, piercing: t.piercing, fragments: t.fragments, flash: record.id === FLASHBANG_ID };
      const head: V3 = [s.x, s.y + HEAD_OVER[posture], s.z];
      const seen = !segmentHit(this.map.grid, sightFrom(point, head), head);        // the line to the head (FUN_005ac070)
      const out = resolveBlast(q.health, { feet, posture, yaw: s.yaw }, point, kind, this.opts.random, seen);
      if (!out) continue;
      const k = out.knock && applyKnock(q.sim.walker, q.sim.moves, out.knock) ? out.knock : null;
      this.send(q.id, {
        type: 'blast', ring: out.ring ? { seconds: BLAST_RING_SECONDS, volume: BLAST_RING_VOLUME } : null,
        knock: k ? { velocity: [k.velocity[0], k.velocity[1], k.velocity[2]], fall: k.fall } : null, after: q.sim.seq,
      });
      if (out.fragments > 0) this.send(q.id, { type: 'hurt', health: [...q.health.hp], from: point, part: out.part });
      if (out.died) this.kill(q, thrower, t.record.name, q === thrower ? 'suicide' : 'weapon', deathClip('blast', out.part, posture, this.opts.random));
    }
  }

  /**
   * A reload, at its command. Refused while this weapon's reload still plays (`FUN_005c2a90` 477398: `FUN_005a7ab0`, true
   * while the reload's clip plays, 462527-462540). MJ-2: no fullness gate -- the game walks from `m_currentmag + 1` for
   * the first slot with rounds (477462-477483), so a full magazine reloads whenever another slot holds rounds. The lock
   * is the clip's length (MJ-1, `reloadLockSeconds`: `FUN_005a82e0`'s clip for the posture, moving or still, and the
   * item; `RELOAD_SECONDS_PLACEHOLDER` without the clips), per weapon, on the command clock, less a tick as the rate's.
   */
  private reload(p: Player, seq: number): void {
    if (!p.alive) return;
    const frame = p.cone.frame(seq);
    const w = frame?.weapon ?? p.sim.weapon;
    const count = frame?.count ?? p.ran;
    // M4: refused while a reload's timer or clip, or an after-shot clip, holds the weapon (`FUN_005a7ab0`, 477398); a
    // bolt's or pump's lock still in its timer is replaced by the reload's (`FUN_005c32b0`), as the page does.
    const replacing = p.lockKind[w] === 'afterShot' && count < p.lockTimer[w];
    if (count < p.reloadUntil[w] && !replacing) return;
    if (!p.mags[w].reload()) return;
    const posture = frame?.posture ?? p.sim.walker.posture;
    const v = frame?.velocity ?? [p.sim.walker.state.vx, p.sim.walker.state.vy, p.sim.walker.state.vz];
    // M4 (research 94 §C1.1-§C1.2): the record's `ReloadDelay` before it lands (`FUN_005c32b0`), then its class's clip
    // (`reloadFamily`: the shotgun reload for the 870 and the bolts), over its `ReloadTime` still (`FUN_005a82e0`).
    const record = p.records[w];
    const family = reloadFamily({ item: w ? 'pistol' : 'rifle', id: record.id });
    const seconds = reloadLockSeconds(this.clips?.clips ?? null, this.clips?.table ?? null, posture, reloadMoving(v[0], v[1], v[2]), family, record.reloadTime ?? 0);
    setLock(p, w, count, reloadDelayOf(record), seconds, 'reload');
  }

  private past(q: Player, tick: number): Past | null {
    const h = q.history;
    if (!h.length) return null;
    for (let i = h.length - 1; i >= 0; i--) {
      if (h[i]!.tick <= tick) {
        const a = h[i]!, b = h[i + 1];
        if (!b) return a;
        const t = (tick - a.tick) / (b.tick - a.tick);
        return { ...a, feet: [a.feet[0] + (b.feet[0] - a.feet[0]) * t, a.feet[1] + (b.feet[1] - a.feet[1]) * t, a.feet[2] + (b.feet[2] - a.feet[2]) * t] };
      }
    }
    return h[0]!;
  }

  // ---- deaths and score (research 91 sections 3, 8) ----

  private kill(victim: Player, killer: Player | null, weapon: string | null, how: KillHow, clip: string | null = null): void {
    victim.alive = false;
    victim.diedAt = this.tick;
    victim.sim.walker.dead = true;                             // the body stays down: no get-up (`Walker.dead`)
    victim.deaths++;
    let line: KillHow = how;
    if (!killer || killer === victim) {
      victim.score -= 2; victim.roundScore -= 2;                  // suicide or fall: -2
    } else if (killer.team === victim.team) {
      killer.score -= 2; killer.roundScore -= 2; line = 'teamkill';
    } else {
      killer.kills++; killer.score += 2; killer.roundScore += 2;
    }
    this.broadcast({ type: 'kill', killer: killer?.id ?? null, victim: victim.id, weapon, how: line, clip });
    this.broadcast(this.scoreEvent());                         // the rows change: the scoreboard follows (research 91 §11)
  }

  // ---- the clock (W3.R11; classic: the maps' `objectives` script, research 91 section 18) ----

  private clock(): void {
    const st = this.state;
    const classic = this.opts.rules === 'classic';
    if (st.phase === 'waiting') {
      if (this.sidesSeated()) this.startRound(true);
    } else if (st.phase === 'play') {
      if (!classic) {
        if (this.tick < st.endsAt) return;
        this.state = { phase: 'expired', resultAt: this.tick + (EXPIRED_PLAY_S + RESULT_S) * TICK_HZ };
        this.broadcast({ type: 'timeExpired' });
        return;
      }
      // `start` (WAIT 5, WAIT 10) and `mission_timer` (WAIT 15) watch nothing in the round's first 15 s.
      if (this.tick < st.startedAt + ROUND_WATCH_S * TICK_HZ) return;
      const winner = eliminationWinner(this.living(), this.opts.solo ? this.seated() : undefined);
      if (winner) {
        // `mp_score00` / `mp_score08` += 1 and `mp_winner` at once, `mission_timer` stopped, the two lines posted.
        this.wins[winner]++;
        this.state = { phase: 'decided', resultAt: this.tick + ELIMINATED_HOLD_S * TICK_HZ, winner, endsAt: st.endsAt };
        this.broadcast({ type: 'eliminated', winner });
        return;
      }
      // `mission_timer` at 00:00 calls `abort`: `round_count` += 1, `mp_winner` = 99 -- a draw, no message, no hold.
      if (this.tick >= st.endsAt) this.endRound(null);
    } else if (st.phase === 'expired') {
      if (this.tick >= st.resultAt) this.endRound();
    } else if (st.phase === 'decided') {
      if (this.tick >= st.resultAt) this.endRound(st.winner);
    } else if (this.tick >= st.nextAt) {
      if (classic && !this.sidesSeated()) {
        // A side emptied: the original abandons the game (`FUN_002bc530` L161130-161140, `dlgNetAbandoned`); the room
        // waits for both sides again (CLASSIC_WAITING_PLACEHOLDER).
        this.resetMatch();
        this.state = { phase: 'waiting' };
        for (const p of this.players.values()) { p.diedAt = -1; this.spawn(p, 'start'); }
        this.broadcast(this.scoreEvent());
        return;
      }
      this.startRound(st.matchOver);
    }
  }

  /** Both sides have a player (dead or alive, ghosts included). */
  private sidesSeated(): boolean {
    if (this.opts.solo) return this.players.size > 0;
    let seal = 0, terrorist = 0;
    for (const p of this.players.values()) { if (p.team === 'seal') seal++; else terrorist++; }
    return seal > 0 && terrorist > 0;
  }

  /** Each side's players, dead or alive (the solo match's elimination test). */
  private seated(): { seal: number; terrorist: number } {
    const n = { seal: 0, terrorist: 0 };
    for (const p of this.players.values()) n[p.team]++;
    return n;
  }

  /** `aiteam_00` / `aiteam_08`: each side's living players. */
  private living(): { seal: number; terrorist: number } {
    const n = { seal: 0, terrorist: 0 };
    for (const p of this.players.values()) if (p.alive) n[p.team]++;
    return n;
  }

  private resetMatch(): void {
    this.round = 0; this.wins.seal = 0; this.wins.terrorist = 0;
    for (const p of this.players.values()) { p.kills = 0; p.deaths = 0; p.score = 0; }
  }

  /** A round begins: the next, or a new match's first; everyone (the ghosts too) at a round-start slot with a full kit. */
  private startRound(newMatch: boolean): void {
    if (newMatch) this.resetMatch();
    this.round++;
    this.state = { phase: 'play', startedAt: this.tick, endsAt: this.tick + this.opts.roundSeconds * TICK_HZ };
    for (const p of this.players.values()) { p.roundScore = 0; p.diedAt = -1; this.spawn(p, 'start'); }
    this.broadcast({ type: 'roundStart', round: this.round, seconds: this.opts.roundSeconds, wins: { ...this.wins }, rounds: this.opts.maxRounds });
    this.broadcast(this.scoreEvent());
  }

  /**
   * A round's result. Respawn (`decided` absent): the side with more round points wins, level is a draw (`success2`).
   * Classic: the elimination's winner (its round win already counted), or null for the clock's draw. Then the bonuses
   * of the MP exit state, the same under both rules (`FUN_00223970` L76146-76165 tests no respawn flag): +5 to each
   * player of `mp_winner`'s side (none on a draw), +1 to each living player.
   */
  private endRound(decided?: Team | null): void {
    const side = { seal: 0, terrorist: 0 };
    for (const p of this.players.values()) {
      if (p.alive) { p.score += 1; p.roundScore += 1; }         // +1 alive at the round's end
      side[p.team] += p.roundScore;
    }
    let winner: Team | null;
    if (decided === undefined) {
      winner = side.seal > side.terrorist ? 'seal' : side.terrorist > side.seal ? 'terrorist' : null;
      if (winner) this.wins[winner]++;
    } else winner = decided;
    if (winner) for (const p of this.players.values()) if (p.team === winner) p.score += 5;   // +5 each on the winning side
    const matchOver = isMatchOver(this.opts.rules, this.round, this.opts.maxRounds, this.wins);
    const screens = matchOver
      ? [{ screen: 'finalRound' as const, seconds: FINAL_ROUND_S }, { screen: 'gameComplete' as const, seconds: GAME_COMPLETE_S }]
      : [{ screen: 'roundComplete' as const, seconds: ROUND_COMPLETE_S }];
    const hold = ENGINE_READ_S + screens.reduce((a, b) => a + b.seconds, 0);
    this.state = { phase: 'over', nextAt: this.tick + hold * TICK_HZ, matchOver };
    this.broadcast({ type: 'roundOver', round: this.round, winner, wins: { ...this.wins }, matchOver, screens });
    this.broadcast(this.scoreEvent());
    this.applyVotes(matchOver);
  }

  // ---- the vote to remove (W3.R13, research 91 section 17) ----

  /** Voter -> the teammates it votes to remove. */
  private readonly votes = new Map<number, Set<number>>();
  /**
   * Addresses refused a rejoin, until when (ms). The original refuses a rejoin to "that game" (research 91 section 17);
   * a dedicated room is never over, so VOTE_BAN_SCOPE_PLACEHOLDER: 10 minutes, two of the original's matches.
   */
  private readonly banned = new Map<string, number>();
  private readonly addresses = new Map<number, string>();

  private vote(id: number, target: number, remove: boolean): void {
    const p = this.players.get(id), t = this.players.get(target);
    if (!p || !t || p === t || p.team !== t.team || !p.alive) return;   // a living player, on a teammate (`FUN_0022f3c0`)
    const mine = this.votes.get(id) ?? new Set<number>();
    if (remove) mine.add(target); else mine.delete(target);
    this.votes.set(id, mine);
    this.send(target, { type: 'votes', count: this.votesAgainst(target) });
  }

  private votesAgainst(target: number): number {
    const t = this.players.get(target);
    if (!t) return 0;
    let n = 0;
    for (const [voter, set] of this.votes) if (set.has(target) && this.players.get(voter)?.team === t.team) n++;
    return n;
  }

  /** `FUN_002c3550` L164913: passed when the votes exceed half the target's team, the target counted. */
  private votePasses(target: number): boolean {
    const t = this.players.get(target);
    if (!t) return false;
    const team = [...this.players.values()].filter((q) => q.team === t.team).length;
    return this.votesAgainst(target) > team / 2;
  }

  /** At a round's end the passed votes remove their targets (research 91 section 17, inferred from SOCOM 1's script). */
  private applyVotes(matchOver: boolean): void {
    const out = [...this.players.keys()].filter((id) => this.votePasses(id));
    for (const id of out) {
      const address = this.addresses.get(id);
      if (address) this.banned.set(address, this.opts.now() + VOTE_BAN_MS);
      this.send(id, { type: 'kicked', reason: 'vote' });
      const conn = this.conns.get(id);
      this.leave(id);
      conn?.close(4002, 'YOU HAVE BEEN KICKED FROM THIS GAME');
    }
    void matchOver;
  }

  /** Seconds left in the round, or null between rounds (and in a classic room waiting for its match). */
  timeLeft(): number | null {
    const st = this.state;
    return st.phase === 'play' || st.phase === 'decided' ? Math.max(0, (st.endsAt - this.tick) / TICK_HZ) : null;
  }

  scoreEvent(): ServerEvent {
    const rows: ScoreRow[] = [...this.players.values()].map((p) => ({
      id: p.id, name: this.lobby.member(p.id)?.name ?? '', team: p.team, kills: p.kills, deaths: p.deaths, score: p.score,
      alive: p.alive, ping: p.ping,
    }));
    return {
      type: 'score', rows, timeLeft: this.timeLeft(), spectators: this.lobby.spectators().map((m) => m.name), wins: { ...this.wins },
    };
  }

  // ---- the idle kick (W3.R13) ----

  private idle(now: number): void {
    for (const p of [...this.players.values()]) {
      // Classic: the dead and the ghosts can only watch until the next round, so their idle clock waits.
      if (!p.alive && this.seatsGhosts()) { p.lastActive = now; continue; }
      if (now - p.lastActive < this.opts.idleKickMs) continue;
      const changes = this.lobby.demote(p.id);
      if (changes) {
        // PL-8: moved out to the back of the queue (W3.R13) -- a spectator now, told so (`demoted`, which its page turns
        // into the spectator's view and its client into a spectator's role); the others drop its body.
        this.players.delete(p.id);
        this.broadcastChanges(changes.filter((c) => !(c.kind === 'queue' && c.id === p.id)));
        this.send(p.id, { type: 'demoted', position: this.lobby.queuePosition(p.id) });
        this.broadcast({ type: 'left', id: p.id }, p.id);
        continue;
      }
      this.send(p.id, { type: 'kicked', reason: 'idle' });
      const conn = this.conns.get(p.id);
      this.leave(p.id);
      conn?.close(4001, 'Kicked for inactivity.');
    }
  }

  // ---- out ----

  private snapshots(): void {
    const bodies = new Map<number, BodyState>();
    for (const p of this.players.values()) bodies.set(p.id, this.body(p));
    const list = [...bodies.values()];
    const doors = this.doors.count ? this.doors.wire() : undefined;
    for (const [id, conn] of this.conns) {
      const p = this.players.get(id);
      const own = p && p.alive ? (() => {
        const s = p.sim.walker.state;
        return { ack: p.sim.seq, x: s.x, y: s.y, z: s.z, vx: s.vx, vy: s.vy, vz: s.vz };
      })() : null;
      conn.send(encodeSnapshot({ tick: this.tick, own, bodies: p ? list.filter((b) => b.id !== id) : list, doors }));
    }
  }

  private body(p: Player): BodyState {
    const s: PlaySnapshot = p.sim.body();
    return bodyOf(p.id, s, { alive: p.alive, weapon: p.sim.weapon, aiming: p.aiming, trigger: p.trigger, boost: p.boost });
  }

  private send(id: number, ev: ServerEvent): void {
    this.conns.get(id)?.send(JSON.stringify(ev));
  }

  private broadcast(ev: ServerEvent, except?: number): void {
    const text = JSON.stringify(ev);
    for (const [id, conn] of this.conns) if (id !== except) conn.send(text);
  }

  /** For `/metrics`. */
  stats(): { players: number; spectators: number; tick: number; round: number; rules: Rules } {
    return { players: this.players.size, spectators: this.lobby.spectators().length, tick: this.tick, round: this.round, rules: this.opts.rules };
  }

  /** For the tests: a player's mover and state. */
  player(id: number): {
    sim: MoverSim; alive: boolean; health: Health; team: Team; score: number; kills: number; deaths: number;
    readonly mags: readonly [MagazineRing, MagazineRing]; readonly cone: ShotCone; readonly reloadUntil: readonly [number, number];
    readonly lockKind: readonly [LockKind, LockKind];
    readonly loadout: Loadout; readonly records: readonly [WeaponRecord, WeaponRecord];
    readonly queue: readonly Command[]; readonly queued: ReadonlySet<number>; readonly grenades: Readonly<Record<string, number>>;
    readonly ran: number; readonly pending: readonly unknown[]; readonly rounds: KitRounds;
  } | undefined {
    return this.players.get(id);
  }
}

/** A finite number. */
function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

/**
 * IMPACT_SIGHT_READING (M4, research 94 §C4.3): where a blast's line to a head (`FUN_005ac070`) starts. A launched
 * round goes off where it struck (`HandleImpact` 0x3c8920: the hit point, on the surface), so a line from there finds
 * that surface at once and no one would be reached; the line starts `BOUNCE_LIFT` (0.1, the lift a bounce leaves a
 * projectile at, 0x3c8f50) toward the head. A grenade at rest, already 0.1 off its floor, is not changed in effect.
 */
const IMPACT_SIGHT_READING = BOUNCE_LIFT;
function sightFrom(point: V3, head: V3): V3 {
  const d: V3 = [head[0] - point[0], head[1] - point[1], head[2] - point[2]], l = Math.hypot(...d);
  if (!(l > IMPACT_SIGHT_READING)) return point;
  const k = IMPACT_SIGHT_READING / l;
  return [point[0] + d[0] * k, point[1] + d[1] * k, point[2] + d[2] * k];
}

/**
 * M4: a weapon's lock on the command clock -- the kit's timer (`ReloadDelay`, or the bolt's or pump's lock: whole ticks
 * the page's frames can have run it out by, rounded down) and then the clip that plays (its ticks), less a tick as the
 * rate's (the page's frame-quantised clock).
 */
function lockTicks(timer: number, clip: number): number {
  return Math.floor(timer * TICK_HZ + 1e-9) + Math.round(clip * TICK_HZ) - 1;
}

/** Which kind set a weapon's lock (the kit timer's flag bit, `kit+2 & 2`: after-shot or reload). */
type LockKind = 'reload' | 'afterShot' | null;

/** Sets a weapon's one lock (`kit+0x820` then its clip): its timer part and its end, on the command clock. */
function setLock(p: Player, w: 0 | 1, count: number, timer: number, clip: number, kind: Exclude<LockKind, null>): void {
  p.lockTimer[w] = count + Math.floor(timer * TICK_HZ + 1e-9);
  p.reloadUntil[w] = count + lockTicks(timer, clip);
  p.lockKind[w] = kind;
}

/** A whole number (a command number, a tick, an id). */
function isInt(v: unknown): v is number {
  return Number.isInteger(v);
}

/** Three finite numbers: a point or a direction off the wire. */
function isV3(v: unknown): v is V3 {
  return Array.isArray(v) && v.length === 3 && v.every(isNum);
}

/** Whether a ray passes within `BODY_REACH` of the vertical line over `feet` (a cheap cull before the capsules). */
function nearRay(o: readonly number[], d: V3, reach: number, feet: V3): boolean {
  const mid: V3 = [feet[0], feet[1] + BODY_TOP / 2, feet[2]];
  const t = Math.max(0, Math.min(reach, (mid[0] - o[0]!) * d[0] + (mid[1] - o[1]!) * d[1] + (mid[2] - o[2]!) * d[2]));
  const px = o[0]! + d[0] * t - mid[0], py = o[1]! + d[1] * t - mid[1], pz = o[2]! + d[2] * t - mid[2];
  return px * px + pz * pz <= BODY_REACH * BODY_REACH && Math.abs(py) <= BODY_TOP;
}

/** A dead body's `isDead` for the tests. */
export { isDead };
