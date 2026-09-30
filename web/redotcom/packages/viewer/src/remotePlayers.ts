import type { Matrix4, Object3D, PerspectiveCamera, Scene } from 'three';
import type { WeaponPoint } from '@s2u/scene';
import type { LoadedBody } from './body';
import { buildBody, type BodyView } from './bodyView';
import type { Lighting } from './lighting';
import type { LoadedMap } from './loadMap';
import { snapshotOf } from './net/body';
import { BODY_FADE_S } from './net/deaths';
import type { TraversalPose } from './animator';
import type { PlaySnapshot, SwapProgress } from './mover';
import { SEAL_ANIMS } from './locomotion';
import type { BodyState, Team } from './net/protocol';
import { Play, type PlayClips } from './play';
import type { Mount } from './heldItem';
import { handedAt, handOffOf, type Firearm } from './kit';

/**
 * The other player's weapons by the replicated weapon (`BodyState.weapon`: 0 the primary, 1 the secondary), where the
 * local kit leaves them once its swap has ended (`./kit`: `FUN_005a60d0(seal, 2, 0)` carries the rifle while the pistol
 * is in the hand; `FUN_005a75d0` holsters the pistol).
 */
export function remoteKit(weapon: 0 | 1): { item: Firearm; mounts: { rifle: Mount; pistol: Mount } } {
  return weapon === 1 ? { item: 'pistol', mounts: { rifle: 'carry', pistol: 'hand' } } : { item: 'rifle', mounts: { rifle: 'hand', pistol: 'holster' } };
}

/**
 * The swap clip a replicated body is playing -- the standing, crouched or prone swap action, or the moving overlay, as
 * `Walker.swapProgress` reads them -- its direction (the clip backwards is the pistol back to the rifle) and its
 * progress 0..1 on the snapshot's own clock; null when none plays.
 */
export function remoteSwap(snap: PlaySnapshot): { to: Firearm; action: SwapProgress['action']; overlay: boolean; progress: number } | null {
  const a = snap.action;
  if (a && (a.name === 'swapStand' || a.name === 'swapCrouch' || a.name === 'swapProne') && a.seconds) {
    return { to: a.reversed ? 'rifle' : 'pistol', action: a.name, overlay: false, progress: Math.min(1, a.t / a.seconds) };
  }
  const o = snap.overlay;
  if (o && o.clip === SEAL_ANIMS.swapMoving && o.seconds > 0) {
    return { to: o.reversed ? 'rifle' : 'pistol', action: null, overlay: true, progress: Math.min(1, o.t / o.seconds) };
  }
  return null;
}

/**
 * The other player's weapons from its snapshot, hand-off included: while a swap clip plays they hang as the local
 * `Kit` hangs them on the same clip and progress (the multiplayer merge review's hole 3) -- the rifle on the `swap`
 * mount posed by the clip, `m_item` the pistol from the start going out (`FUN_005a7260`) and until the end coming back
 * (`FUN_005a70f0`), the pistol into the hand (`FUN_005a7730`) or the holster (`FUN_005a75d0`) as the clip passes its
 * `HAND_OFF` phase -- so the hand-off is drawn mid-clip, not when the replicated weapon changes at the swap's start.
 * No new field on the wire: the clip, its clock and its direction already ride the body (`BodyState.action*`,
 * `overlay*`, `ActionReversed` / `OverlayReversed`). Before the hand-off the pistol is where the settled kit keeps it
 * (the holster; the local kit's spawn mount on the hips is not replicated).
 */
export function remoteKitOf(snap: PlaySnapshot & { weapon: 0 | 1 }): ReturnType<typeof remoteKit> {
  const swap = remoteSwap(snap);
  if (!swap || swap.progress >= 1) return remoteKit(swap ? (swap.to === 'pistol' ? 1 : 0) : snap.weapon);
  const handed = handedAt(swap.to, swap.progress, handOffOf(swap));
  const pistol: Mount = swap.to === 'pistol' ? (handed ? 'hand' : 'holster') : (handed ? 'holster' : 'hand');
  return { item: 'pistol', mounts: { rifle: 'swap', pistol } };
}

/**
 * The other players, drawn 1:1 (web sprint 3, M5): each is the map's own character -- the first SEAL type for the
 * SEALs, the first Terrorist type for the Terrorists (`LoadedMap.terrorist`, research 91 section 14,
 * DEFAULT_CHARTYPE_PLACEHOLDER) -- in its own gear, with its own `Play` running the game's clips from the replicated
 * mover (`./net/body` `snapshotOf`), its type's primary in its hand raised by the replicated aim and trigger and its
 * secondary on its mount (`SideKit`). A body the snapshots stop naming is taken away.
 *
 * A death plays the clip the server chose from `damanim.rdr`'s lists (`./net/deaths`, research 91 section 3) and the
 * body goes when the game's fade would have taken it (0.1 a second: 10 s). BODY_FADE_PLACEHOLDER: the body is drawn
 * whole until then and hidden at once -- the skinned material has no opacity yet.
 */

/** A held weapon to hang: the map's built model (`WorldView.held`, cloned for each body) and its named points. */
export interface HeldRef { object: Object3D; points: readonly WeaponPoint[] }
/**
 * The two firearms a player carries (web sprint 4, M3/M9): the loadout's primary and secondary models (`./loadout`) --
 * the player's own kit when the room has named it (`kit`, protocol 7), else its side's first type's
 * (DEFAULT_CHARTYPE_PLACEHOLDER), as the local player spawns with.
 */
export type SideKit = (team: Team, kit: readonly number[] | null) => { rifle: HeldRef | null; pistol: HeldRef | null };

/** No item (`EMPTY_ITEM`): a body whose kit is not known says so in `BodyState.weapon`. */
const NO_ITEM = 255;

/**
 * REMOTE_KIT_APPLY_PLACEHOLDER: when another console's body takes up a received kit (`FUN_0053ec60` L407354-407378,
 * called at L455079 and L455445) is not traced (research 94 §A6). The page takes a player's kit at its `spawn` (protocol
 * 7: the room names it, the rebuild's moment, `FUN_00599f00`) and the welcome's list, and hangs the item a snapshot
 * says is in the hand (`BodyState.weapon`, by id) at once when it differs -- the room owns the kit (W4.R6), so the two
 * never disagree but across a join.
 */
export const REMOTE_KIT_APPLY_PLACEHOLDER = 'spawn' as const;

interface Remote {
  id: number; team: Team; view: BodyView; play: Play; weapon: Object3D | null; sidearm: Object3D | null; item: Firearm; snap: ReturnType<typeof snapshotOf> | null;
  /** The kit the weapons were hung from (five item ids), or null for the side's type's. */
  kit: number[] | null;
  deadFor: number; deathClip: string | null;
  /** The weapons' named points (the muzzle's `firepoint`), rifle and pistol. */
  points: { rifle: readonly WeaponPoint[]; pistol: readonly WeaponPoint[] };
}

/**
 * A death clip at `seconds` into it, as the animator's one-node play (the traversal seam, `./animator`): its key from
 * its `motion.rdr` playback (the clip's own seconds), held on the last key once played.
 */
export function deathPose(clip: string, seconds: number, clips: PlayClips | null): TraversalPose | null {
  const c = clips?.clips.find((k) => k.name === clip);
  if (!c) return null;
  const entry = clips?.table?.find(([name]) => name === clip)?.[1];
  const playback = entry?.playback ?? c.frameCount / 30;
  const frame = Math.min(c.frameCount - 1, (seconds / playback) * (c.frameCount - 1));
  return { clip, frame, loop: false, rootY: null };
}

export class RemotePlayers {
  private readonly remotes = new Map<number, Remote>();
  private map: LoadedMap | null = null;
  private lighting: Lighting | null = null;
  private clips: PlayClips | null = null;
  private kitOf: SideKit | null = null;
  private readonly teams = new Map<number, Team>();
  /** Protocol 7: each player's kit as the room named it (a `spawn`, the welcome's players). */
  private readonly kits = new Map<number, number[]>();
  private typeKit: ((team: Team) => readonly number[]) | null = null;

  constructor(private readonly scene: Scene) {}

  /**
   * A new map (its bodies, textures, and each side's two firearms): every remote is rebuilt from it on its next snapshot.
   * `typeKit`: each side's type's kit by id (`./loadout` `typeLoadout`), the kit a body is drawn with until its own is named.
   */
  setMap(map: LoadedMap | null, lighting: Lighting, kitOf: SideKit | null, typeKit: ((team: Team) => readonly number[]) | null = null): void {
    this.clear();
    this.kits.clear();
    this.typeKit = typeKit;
    this.map = map;
    this.lighting = lighting;
    this.kitOf = kitOf;
  }

  setClips(clips: PlayClips | null): void {
    this.clips = clips;
    for (const r of this.remotes.values()) r.play.setClips(clips);
  }

  /** A player's team, from the server's `welcome` / `joined` / `promoted`. */
  setTeam(id: number, team: Team): void {
    this.teams.set(id, team);
    const r = this.remotes.get(id);
    if (r && r.team !== team) this.remove(id);
  }

  forget(id: number): void {
    this.teams.delete(id);
    this.kits.delete(id);
    this.remove(id);
  }

  /**
   * A player's kit (protocol 7: its `spawn`, the welcome's players): five item ids; a drawn body whose kit changed has
   * its two firearms hung again (REMOTE_KIT_APPLY_PLACEHOLDER).
   */
  setKit(id: number, kit: readonly number[]): void {
    if (kit.length !== 5) return;
    this.kits.set(id, [...kit]);
    const r = this.remotes.get(id);
    if (r && !sameKit(r.kit, kit)) this.hang(r, [...kit]);
  }

  /** A player's kit as the page knows it, or null (its side's type's then). */
  playerKit(id: number): readonly number[] | null {
    return this.kits.get(id) ?? null;
  }

  /** One frame: every body at its interpolated state, in its clip. */
  frame(dt: number, bodies: readonly BodyState[], camera: PerspectiveCamera): void {
    const seen = new Set<number>();
    for (const b of bodies) {
      seen.add(b.id);
      const r = this.remotes.get(b.id) ?? this.add(b.id);
      if (!r) continue;
      r.snap = snapshotOf(b);
      if (r.snap.alive) { r.deadFor = 0; r.deathClip = null; } else r.deadFor += dt;
      const shown = r.snap.alive || r.deadFor < BODY_FADE_S;
      r.view.group.visible = shown;
      if (!shown) continue;
      if (!r.snap.alive && r.deathClip) r.snap.traversal = deathPose(r.deathClip, r.deadFor, this.clips);
      // Protocol 7: the item in the hand by id; one the kit does not hold in that slot is hung at once.
      const held = r.snap.item, known = r.kit ?? this.typeKit?.(r.team) ?? null;
      if (held !== NO_ITEM && known?.[r.snap.weapon] !== held) {
        const next = [...(known ?? [NO_ITEM, NO_ITEM, NO_ITEM, NO_ITEM, NO_ITEM])];
        next[r.snap.weapon] = held;
        this.kits.set(r.id, next);
        this.hang(r, next);
      }
      const kit = remoteKitOf(r.snap);                     // WEAPON: the replicated primary or sidearm in the hand
      if (kit.item !== r.item) { r.item = kit.item; r.play.setItem(kit.item); }
      r.play.setMounts(kit.mounts);
      r.play.frame(dt, { snapshot: () => r.snap, view: () => 'third' }, camera);
      r.view.group.visible = true;
    }
    for (const id of [...this.remotes.keys()]) if (!seen.has(id)) this.remove(id);
  }

  /** Where each body's muzzle is (the shots' tracers and flashes start there), or null. */
  muzzle(id: number): [number, number, number] | null {
    return this.remotes.get(id)?.play.muzzle() ?? null;
  }

  /** A kill: the victim's death clip (the server's choice), played from now. */
  died(id: number, clip: string | null): void {
    const r = this.remotes.get(id);
    if (r) { r.deathClip = clip; r.deadFor = 0; } else if (clip) this.pendingDeaths.set(id, clip);
  }
  private readonly pendingDeaths = new Map<number, string>();

  /** A body's weapon node in the world and its `firepoint` (the muzzle animation's frame, research 89 section 4), or null. */
  weaponFrame(id: number): { matrix: Matrix4; muzzle: [number, number, number] | null } | null {
    const r = this.remotes.get(id);
    const pistol = r?.item === 'pistol';
    const object = pistol ? r?.sidearm : r?.weapon;
    if (!r || !object || !r.view.group.visible) return null;
    object.updateWorldMatrix(true, false);
    const p = r.points[pistol ? 'pistol' : 'rifle'].find((q) => q.name === 'firepoint' || q.name === 'firepont');
    return { matrix: object.matrixWorld.clone(), muzzle: p ? [p.at[0], p.at[1], p.at[2]] : null };
  }

  /** Each body's feet, for the positional sounds. */
  feet(id: number): [number, number, number] | null {
    const s = this.remotes.get(id)?.snap;
    return s ? [s.feet[0], s.feet[1], s.feet[2]] : null;
  }

  count(): number {
    return this.remotes.size;
  }

  private add(id: number): Remote | null {
    const map = this.map, lighting = this.lighting;
    if (!map || !lighting) return null;
    const team = this.teams.get(id) ?? 'seal';
    const loaded: LoadedBody | undefined = (team === 'terrorist' ? (map.terrorist ?? map.body) : map.body) ?? undefined;
    if (!loaded) return null;
    const view = buildBody(loaded, map, lighting);
    this.scene.add(view.group);
    const play = new Play();
    play.setBody(view, loaded);
    play.setFlyToggle(true);
    play.setClips(this.clips);
    const r: Remote = {
      id, team, view, play, weapon: null, sidearm: null, item: 'rifle', snap: null, deadFor: 0, deathClip: this.pendingDeaths.get(id) ?? null,
      points: { rifle: [], pistol: [] }, kit: null,
    };
    // WEAPON (web sprint 4, M3/M9): the player's two firearms -- its own kit when named, else its side's type's -- each its
    // own model at its own grip, as the local kit hangs them.
    this.hang(r, this.kits.get(id) ?? null);
    this.pendingDeaths.delete(id);
    play.setWeaponInput(() => ({ trigger: r.snap?.trigger ?? false, aiming: r.snap?.aiming ?? false }));
    this.remotes.set(id, r);
    return r;
  }

  /** A body's two firearms hung from a kit (null: its side's type's): the old models off, clones of the kit's on. */
  private hang(r: Remote, kit: number[] | null): void {
    const refs = this.kitOf?.(r.team, kit) ?? { rifle: null, pistol: null };
    r.play.setWeapon(null, []);
    r.play.setSidearm(null, []);
    r.weapon = refs.rifle ? refs.rifle.object.clone(true) : null;
    if (r.weapon && refs.rifle) r.play.setWeapon(r.weapon, refs.rifle.points);
    r.sidearm = refs.pistol ? refs.pistol.object.clone(true) : null;
    if (r.sidearm && refs.pistol) r.play.setSidearm(r.sidearm, refs.pistol.points);
    r.points = { rifle: refs.rifle?.points ?? [], pistol: refs.pistol?.points ?? [] };
    r.kit = kit;
  }

  private remove(id: number): void {
    const r = this.remotes.get(id);
    if (!r) return;
    this.scene.remove(r.view.group);
    r.play.setWeapon(null, []);
    r.play.setSidearm(null, []);
    r.view.dispose();
    this.remotes.delete(id);
  }

  clear(): void {
    for (const id of [...this.remotes.keys()]) this.remove(id);
  }
}

function sameKit(a: readonly number[] | null, b: readonly number[]): boolean {
  return a !== null && a.length === b.length && a.every((v, i) => v === b[i]);
}
