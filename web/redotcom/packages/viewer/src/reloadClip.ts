import type { MotionClip } from '@s2u/scene';
import type { MotionTable } from './motionTable';

/**
 * The reload's clip and its length, one table for the page and the match server (MJ-1 of the launch review; the
 * shared sim boundary, `./sim`): the page's `WeaponPose` plays and times the reload from here, and the server's room
 * locks the weapon for the same seconds, so the two clocks cannot drift.
 *
 * - **The lock is the clip.** The game has no reload timer: `FUN_005c2a90` (decomp 477395-477399) refuses a reload
 *   while `FUN_005a7d10` / `FUN_005a7ab0` / `FUN_005a78d0` answer, and the fire gate `FUN_005a7de0` tests the reload's
 *   animation state through `FUN_005a7ab0` -- the reload lasts as long as its clip plays. The M4A1's record carries no
 *   `ReloadTime` (research 79 s1.2; research 84 s18). So the length is the clip's `motion.rdr` `playback` [data]:
 *   `seal_reload` 1.6, `seal_crouch_reload` 1.9, `seal_prone_reload` 1.7, `seal_mv_reload` 1.2 (the pistol's four
 *   from the same table).
 * - **The clip.** `FUN_005a82e0` (decomp 462786-462930) picks it: prone the prone reload; otherwise the moving
 *   overlay when the mover's speed squared is over 400.0 (`bVar3`, 462821-462823: `vx^2 + vy^2 + vz^2 <= 400.0` is
 *   still -- hard-coded; `dynamics.rdr`'s `min_running_reload_speed` is loaded but never read), else the stance's.
 *   The item (`m_item`) picks the rifle's set or the pistol's (animset.rdr's "Rifle reload" / "Pistol reload" family).
 * - `RELOAD_SECONDS_PLACEHOLDER` (named; research 84 s11): the length when the clip or the table is missing (a
 *   source without `MOTION_P.ZAR`, a server started without the clips) -- the viewer's old estimate, 2 s, with no
 *   source. It is a fallback only; every retail disc carries the clips.
 */

/** The stance the reload picks its clip by (`Walker.posture`: the body in use). */
export type ReloadStance = 'stand' | 'crouch' | 'prone';
/**
 * The clip family a reload plays (web sprint 4 M4: `FUN_005a82e0`'s choice, research 94 §C1.2): the firearm in use
 * (`m_item`: `rifle` or `pistol`), the shotgun reload, the pump (the shotgun class's after-shot), and the launcher's
 * round mode's `Rifle m203 reload`.
 */
export type ReloadItem = 'rifle' | 'pistol' | 'shotgun' | 'pump' | 'm203';

/** The rifle's reload clips by stance, and the moving one (animset.rdr's "Rifle reload" family). */
export const RELOAD_CLIPS = {
  stand: 'seal_reload', crouch: 'seal_crouch_reload', prone: 'seal_prone_reload', moving: 'seal_mv_reload',
} as const;

/** The pistol's (animset.rdr's "Pistol reload", "Pistol crouch reload", "Pistol prone reload", "Moving pistol reload"). */
export const PISTOL_RELOAD_CLIPS = {
  stand: 'seal_p_reload', crouch: 'seal_p_crouch_reload', prone: 'seal_p_prone_reload', moving: 'seal_p_mv_reload',
} as const;

/**
 * The shotgun reload (animset.rdr "Shotgun reload", "Shotgun crouch reload", "Shotgun prone reload", "Moving shotgun
 * reload": `DAT_003df098`/`0a0`/`0a8`/`0b0`, named at L495399-495402 from 0x6623b0-0x662400): the 870 (84) and the
 * M82A1A, M40A1, M87ELR (101-103; `FUN_005a82e0`'s `bVar5`, class 0x65 with `id - 0x68 > 2`).
 */
export const SHOTGUN_RELOAD_CLIPS = {
  stand: 'seal_reload_shotgun', crouch: 'seal_crouch_reload_shotgun', prone: 'seal_prone_reload_shotgun', moving: 'seal_mv_reload_shotgun',
} as const;

/**
 * The pump (animset.rdr "Shotgun pump", "Shotgun crouch pump", "Shotgun prone pump", "Moving shotgun pump":
 * `DAT_003df0b8`/`0c0`/`0c8`/`0d0`, L495403-495406): the after-shot clip (`param_2` 1) of the shotgun class (0x51).
 */
export const PUMP_CLIPS = {
  stand: 'seal_pump_shotgun', crouch: 'seal_crouch_pump_shotgun', prone: 'seal_prone_pump_shotgun', moving: 'seal_mv_pump_shotgun',
} as const;

/**
 * A launcher round mode's reload (`bVar4`: `FUN_005bda00` or `FUN_005bd6d0`, the kit firing a carrier's round): still,
 * in every stance, "Rifle m203 reload" (`DAT_003debf8`, named at L495238 from 0x661840); moving, "Moving rifle reload"
 * (`DAT_003deb70`, 0x6616a0) -- `FUN_005a82e0` L462836-462846.
 */
export const M203_RELOAD_CLIPS = {
  stand: 'seal_reload_m203', crouch: 'seal_reload_m203', prone: 'seal_reload_m203', moving: 'seal_mv_reload',
} as const;

const FAMILIES: Readonly<Record<ReloadItem, { stand: string; crouch: string; prone: string; moving: string }>> = {
  rifle: RELOAD_CLIPS, pistol: PISTOL_RELOAD_CLIPS, shotgun: SHOTGUN_RELOAD_CLIPS, pump: PUMP_CLIPS, m203: M203_RELOAD_CLIPS,
};

/** Every reload and after-shot clip: what the sim's clip set (`./simMap` `SIM_CLIPS`) carries so the server can time them. */
export const ALL_RELOAD_CLIPS: readonly string[] = Object.freeze([...new Set(Object.values(FAMILIES).flatMap((f) => Object.values(f)))]);

/**
 * `FUN_005a82e0`'s family (L462812-462900): a round mode `m203`; the pistol in hand (`+0xf79 != 1`) `pistol`; the
 * after-shot (`param_2` 1) of the shotgun class (81-90) `pump`; the 870 (84) and the bolt-class snipers 101-103
 * `shotgun`; everything else `rifle` (the Spas 12 and the JACKHAMMER among them).
 */
export function reloadFamily(how: { item: 'rifle' | 'pistol'; id: number; afterShot?: boolean; roundMode?: boolean }): ReloadItem {
  if (how.roundMode) return 'm203';
  if (how.item === 'pistol') return 'pistol';
  if (how.afterShot && how.id >= 81 && how.id <= 90) return 'pump';
  if (how.id === 84 || (how.id >= 101 && how.id <= 103)) return 'shotgun';
  return 'rifle';
}

/**
 * `FUN_005a82e0`'s still test for the reload (decomp 462821-462823): the mover's speed squared at most 400.0 (20 units
 * a second) is still. Faster, standing or crouched, the moving reload; prone always the prone one.
 */
export const RELOAD_STILL_SPEED = 20;

/** PLACEHOLDER (named; research 84 s11): the reload's seconds when its clip or the table is missing. No source. */
export const RELOAD_SECONDS_PLACEHOLDER = 2;

/** `FUN_005a82e0`'s `bVar3` negated: the mover's velocity (units a second) is over 20 -- the moving reload. */
export function reloadMoving(vx: number, vy: number, vz: number): boolean {
  return vx * vx + vy * vy + vz * vz > RELOAD_STILL_SPEED * RELOAD_STILL_SPEED;
}

/** `FUN_005a82e0`'s choice: prone the prone reload; else moving the overlay, still the stance's; the item's set. */
export function reloadClip(stance: ReloadStance, moving: boolean, item: ReloadItem = 'rifle'): string {
  const set = FAMILIES[item];
  return stance === 'prone' ? set.prone : moving ? set.moving : set[stance];
}

/** The reload's length: the clip's `playback` seconds, else its keys at its own rate; null without the clip. */
export function reloadLength(clip: MotionClip | undefined, table: MotionTable | null): number | null {
  if (!clip) return null;
  const playback = table?.get(clip.name)?.playback;
  return playback !== null && playback !== undefined && playback > 0 ? playback : clip.frameCount / clip.rate;
}

/** The clips by name, from a map (the page's) or the list the sim loads (`SimClips.clips`, the server's). */
export type ReloadClipSource = ReadonlyMap<string, MotionClip> | readonly MotionClip[];

const clipNamed = (clips: ReloadClipSource, name: string): MotionClip | undefined =>
  Array.isArray(clips) ? (clips as readonly MotionClip[]).find((c) => c.name === name) : (clips as ReadonlyMap<string, MotionClip>).get(name);

/**
 * The reload's length in a stance, moving or not, for a family: the record's `ReloadTime` when the body is still and it
 * has one -- `FUN_005a82e0` L462940-462945 sets the clip's rate to its length / `ReloadTime` when `bVar3` (the speed
 * squared at most 400, any stance), so the clip lasts `ReloadTime` (Spas 12 and JACKHAMMER 2, M60E3 3, M63A 2.5) --
 * else the chosen clip's (`reloadLength`), null without it.
 */
export function reloadSeconds(clips: ReloadClipSource, table: MotionTable | null, stance: ReloadStance, moving: boolean,
  item: ReloadItem = 'rifle', reloadTime = 0): number | null {
  if (!moving && reloadTime > 0) return reloadTime;
  return reloadLength(clipNamed(clips, reloadClip(stance, moving, item)), table);
}

/**
 * The weapon's lock for a reload or an after-shot clip: `reloadSeconds` (the record's `ReloadTime`, still, needs no
 * clip), else `RELOAD_SECONDS_PLACEHOLDER` -- only a source without the clips (a server started without `MOTION_P.ZAR`).
 */
export function reloadLockSeconds(clips: ReloadClipSource | null, table: MotionTable | null, stance: ReloadStance, moving: boolean,
  item: ReloadItem = 'rifle', reloadTime = 0): number {
  if (!moving && reloadTime > 0) return reloadTime;
  return (clips ? reloadSeconds(clips, table, stance, moving, item) : null) ?? RELOAD_SECONDS_PLACEHOLDER;
}
