import {
  EMPTY_ITEM, itemClass, menuValves, pick as pickItem, selectable, slotKind, slotLocked,
  type Arsenal, type ItemClass, type Loadout, type Pick, type Side, type SlotKind,
} from '@s2u/scene';

/**
 * The in-game weapon select, its states and rules without a pixel (web sprint 4, M8; research 94 part 2). SOCOM II's
 * `CInGameWeaponSel` is dead code (R94.1): the menu a dead player opens is the HUD's "WEAPON EXCHANGE" block at
 * `CHUD+0x38e0` -- Init `FUN_00240e60` (L89585), tick `FUN_00240600` (L89343), the slot list `FUN_0023ebc0` (L88581),
 * the picker `FUN_0023d1b0` (L87851) over `FUN_0023d060` / `FUN_0023c6f0` / `FUN_0023c840`. This module is that tick's
 * logic, driven by the pad's just-pressed edges (no auto-repeat, §B3); `./weaponSelect` draws it.
 *
 * - **When** (§B2, `FUN_001f7ff0` L56648-56661, tick L89369-89374): in the match, dead, the camera on oneself, not a
 *   spectator: `Inventory` (R2) opens the slot list. Alive, the same button is the in-hand inventory, never this menu;
 *   the menu is never offered before the round or at a spawn. The late joiner's ghost opens it the same way.
 * - **The slot list** (S2): five rows, primary, sidearm, equipment 1-3; Up/Down step to the previous/next slot that is
 *   not locked (`slotLocked`, `FUN_0023e910`), wrapping; Action opens the picker on that slot; Triangle, Start or
 *   `Inventory` close.
 * - **The picker** (S3): a category ring per slot kind (`FUN_0023c840`), a category with nothing listable skipped, the
 *   launcher rounds' `LAUNCHED` only while a launcher is carried (`FUN_0023d060` L87825-87830); Up/Down step through the
 *   whole item list, wrapping, skipping what the side and slot refuse (`FUN_0023c6f0` over `selectable`); Left/Right the
 *   previous/next category, landing on the first listable item after the list's head (`FUN_0023c6f0(forward, 0)`);
 *   Action confirms (S4: `FUN_0023fef0` then the whole kit written to the type, `FUN_0023e5e0`), Triangle or Start
 *   cancels back to the list with no change.
 * - **When the pick applies** (§B6, S8): the kit written on confirm is the next round's (classic): the caller stores it
 *   and the spawn takes it. The round's reset closes the menu; an unconfirmed pick is lost.
 */

/** The pad's inputs the menu reads (§B3's slots): the d-pad, `Action` (X), Triangle / Start, and `Inventory` (R2). */
export type MenuInput = 'up' | 'down' | 'left' | 'right' | 'action' | 'back' | 'inventory';

/** A category of the picker: an item class, or all of the slot kind's (`0xff`, "ALL PRIMARY" ...). */
export type Category = ItemClass | 'all';

/** The rings per slot kind (`FUN_0023c840` L87532-87660; research 94 §B6 "Categories"). */
export const CATEGORY_RING: Readonly<Record<SlotKind, readonly Category[]>> = {
  primary: ['all', 'smg', 'rifle', 'shotgun', 'mg', 'sniper', 'grenadeLauncher'],
  secondary: ['pistol'],
  equipment: ['all', 'grenade', 'rocketLauncher', 'explosive', 'launcherRound', 'rocketRound', 'gear'],
};

/** The header each category draws (`FUN_003d17d0`, the ALL headers 0x3e6c58-0x3e6c88; research 94 §B5). */
export const CATEGORY_NAME: Readonly<Record<string, string>> = {
  pistol: 'PISTOLS', smg: 'SMGS', rifle: 'ASSAULT RIFLES', shotgun: 'SHOTGUNS', mg: 'MACHINE GUNS', sniper: 'SNIPER RIFLES',
  grenadeLauncher: 'HEAVY WEAPONS', grenade: 'GRENADES', rocketLauncher: 'LAUNCHERS', explosive: 'EXPLOSIVES',
  launcherRound: 'LAUNCHED', rocketRound: 'MISSILE', gear: 'MISC EQUIP',
  'all:primary': 'ALL PRIMARY', 'all:secondary': 'ALL SECONDARY', 'all:equipment': 'ALL EQUIP',
};

/** The header of `category` in a slot of kind `kind`. */
export function categoryName(category: Category, kind: SlotKind): string {
  return CATEGORY_NAME[category === 'all' ? `all:${kind}` : category] ?? 'UNKNOWN';
}

/** Whether the kit carries a launcher host -- the menu's `+0x1532..+0x1534` flags (M203 rifles and MGL, F2000, M79). */
export function carriesLauncher(loadout: Loadout): boolean {
  return [52, 61, 142, 63, 143].includes(loadout[0]);
}

/** What the menu sees of the world: the arsenal, the map's valves, the player's side, the kit it opens on. */
export interface MenuContext {
  arsenal: Arsenal;
  valves: ReadonlyMap<string, number>;
  side: Side;
}

/** The menu's state (the block's `+0xf20..+0xf24` and the slot list's cursor), plain data. */
export interface MenuState {
  /** S0-S1 closed, S2 the slot list, S3 the picker (`FUN_00240b90`'s 0 / 2 / 3). */
  screen: 'closed' | 'list' | 'picker';
  /** The slot the list's cursor is on, 0-4. */
  slot: number;
  /** The picker's category (`+0xf20`). */
  category: Category;
  /** The picker's current (middle card) item id (`+0xf24`'s record). */
  item: number;
  /** The kit as the menu has it: written on each confirm. */
  loadout: Loadout;
  /** The confirmed picks since the menu opened, in order (what the server replays: `applyPicks`). */
  picks: readonly Pick[];
}

/** The closed menu over a kit. */
export function closedMenu(loadout: Loadout): MenuState {
  return { screen: 'closed', slot: 0, category: 'all', item: loadout[0], loadout, picks: [] };
}

/** Whether `Inventory` opens the menu now (`FUN_001f7ff0` L56648-56661): dead, the camera on oneself, no spectator. */
export function canOpen(p: { inMatch: boolean; alive: boolean; cameraOnSelf: boolean; spectator: boolean }): boolean {
  return p.inMatch && !p.alive && p.cameraOnSelf && !p.spectator;
}

/** Whether an item is listed in the picker for this slot and category (`FUN_0023c390` with the category filter). */
export function listable(ctx: MenuContext, s: MenuState, category: Category, id: number): boolean {
  if (category !== 'all' && itemClass(id) !== category) return false;
  return selectable(menuValves(ctx.valves, s.loadout[0]), ctx.side, s.loadout, s.slot, id);
}

/**
 * `FUN_0023c6f0` (L87491-87523): from `from`, the next (`dir` +1) or previous (-1) listable item through the whole
 * list in the file's order, wrapping; `from` itself when nothing else is listable.
 */
export function stepItem(ctx: MenuContext, s: MenuState, category: Category, from: number, dir: 1 | -1): number {
  const order = ctx.arsenal.order, n = order.length;
  const at = order.indexOf(from);
  for (let k = 1; k <= n; k++) {
    const id = order[((at < 0 ? (dir > 0 ? -1 : 0) : at) + dir * k + n * n) % n]!;
    if (listable(ctx, s, category, id)) return id;
  }
  return from;
}

/** Whether a category has anything listable (`FUN_0023cb90` L87663). */
function categoryHas(ctx: MenuContext, s: MenuState, category: Category): boolean {
  return ctx.arsenal.order.some((id) => listable(ctx, s, category, id));
}

/**
 * `FUN_0023c840` + `FUN_0023d060` (L87811-87838): the previous/next category of the slot's ring with something
 * listable, `LAUNCHED` skipped unless a launcher is carried.
 */
export function stepCategory(ctx: MenuContext, s: MenuState, dir: 1 | -1): Category {
  const ring = CATEGORY_RING[slotKind(s.slot)];
  const at = Math.max(0, ring.indexOf(s.category));
  for (let k = 1; k <= ring.length; k++) {
    const c = ring[(at + dir * k + ring.length * 4) % ring.length]!;
    if (c === 'launcherRound' && !carriesLauncher(s.loadout)) continue;
    if (categoryHas(ctx, s, c)) return c;
  }
  return s.category;
}

/** The slot list's cursor step (`FUN_0023eae0` L88591): the previous/next slot not locked, wrapping 4 <-> 0. */
export function stepSlot(ctx: MenuContext, s: MenuState, dir: 1 | -1): number {
  const valves = menuValves(ctx.valves, s.loadout[0]);
  for (let k = 1; k <= 5; k++) {
    const slot = (s.slot + dir * k + 10) % 5;
    if (!slotLocked(valves, ctx.side, s.loadout, slot)) return slot;
  }
  return s.slot;
}

/** The picker opened on a slot (`FUN_0023d540` L87972): its item's category and the item; an empty slot, ALL at 0x79. */
export function pickerOn(s: MenuState): Pick & { category: Category } {
  const id = s.loadout[s.slot]!;
  if (id === EMPTY_ITEM) return { slot: s.slot, id: 0x79, category: 'all' };
  return { slot: s.slot, id, category: itemClass(id) };
}

/** The picker's three cards: previous, current, next; a side card equal to the current one is blank (L88180-88184). */
export function cards(ctx: MenuContext, s: MenuState): [number | null, number, number | null] {
  const prev = stepItem(ctx, s, s.category, s.item, -1), next = stepItem(ctx, s, s.category, s.item, 1);
  return [prev === s.item ? null : prev, s.item, next === s.item ? null : next];
}

/** The first slot the list's cursor may rest on (the list opens on slot 0, stepped past a locked one). */
function firstOpenSlot(ctx: MenuContext, s: MenuState): number {
  const valves = menuValves(ctx.valves, s.loadout[0]);
  return slotLocked(valves, ctx.side, s.loadout, s.slot) ? stepSlot(ctx, s, 1) : s.slot;
}

/** What a step did, for the caller: the kit confirmed (`FUN_0023e5e0`), or the menu opened or closed. */
export type MenuEvent = { kind: 'opened' } | { kind: 'closed' } | { kind: 'confirmed'; loadout: Loadout; pick: Pick };

/**
 * One just-pressed input (`FUN_00240600`'s tick: the list's `FUN_0023ebc0`, the picker's `FUN_0023d1b0`). `open`
 * gates `Inventory` from the closed menu (`canOpen`). Returns the new state and what happened.
 */
export function step(ctx: MenuContext, s: MenuState, input: MenuInput, open = true): { state: MenuState; event: MenuEvent | null } {
  switch (s.screen) {
    case 'closed': {
      if (input !== 'inventory' || !open) return { state: s, event: null };
      const opened: MenuState = { ...s, screen: 'list', slot: 0, picks: [] };
      return { state: { ...opened, slot: firstOpenSlot(ctx, opened) }, event: { kind: 'opened' } };
    }
    case 'list': {
      if (input === 'up') return { state: { ...s, slot: stepSlot(ctx, s, -1) }, event: null };
      if (input === 'down') return { state: { ...s, slot: stepSlot(ctx, s, 1) }, event: null };
      if (input === 'action') {
        const at = pickerOn(s);
        return { state: { ...s, screen: 'picker', category: at.category, item: at.id }, event: null };
      }
      if (input === 'back' || input === 'inventory') return { state: { ...s, screen: 'closed' }, event: { kind: 'closed' } };
      return { state: s, event: null };
    }
    case 'picker': {
      if (input === 'up') return { state: { ...s, item: stepItem(ctx, s, s.category, s.item, -1) }, event: null };
      if (input === 'down') return { state: { ...s, item: stepItem(ctx, s, s.category, s.item, 1) }, event: null };
      if (input === 'left' || input === 'right') {
        const category = stepCategory(ctx, s, input === 'left' ? -1 : 1);
        if (category === s.category) return { state: s, event: null };
        const head = ctx.arsenal.order[0] ?? s.item;
        return { state: { ...s, category, item: stepItem(ctx, s, category, head, 1) }, event: null };
      }
      if (input === 'back') return { state: { ...s, screen: 'list' }, event: null };
      if (input === 'action') {
        // S4: confirm only what the list offers (the middle card may be the slot's own, unlisted item: no change).
        if (s.item === s.loadout[s.slot] || !listable(ctx, s, s.category, s.item)) return { state: { ...s, screen: 'list' }, event: null };
        const choice: Pick = { slot: s.slot, id: s.item };
        const loadout = pickItem(ctx.arsenal, ctx.valves, ctx.side, s.loadout, s.slot, s.item).loadout;
        return { state: { ...s, screen: 'list', loadout, picks: [...s.picks, choice] }, event: { kind: 'confirmed', loadout, pick: choice } };
      }
      return { state: s, event: null };
    }
  }
}

/** The round's reset (S8, `FUN_002a7d40` -> `FUN_00240d50`): the menu closes over the kit the spawn took. */
export function reset(loadout: Loadout): MenuState {
  return closedMenu(loadout);
}
