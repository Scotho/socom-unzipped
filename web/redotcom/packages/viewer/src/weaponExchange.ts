import { applyPicks, EMPTY_ITEM, menuValves, pick as pickItem, selectable, slotLocked, type Loadout, type Pick } from '@s2u/scene';
import type { HudQuad, HudTri } from './hud';
import { PAD_BUTTON, PAD_PRESS, type GamepadLike, type PadButton } from './gamepad';
import {
  drawWeaponSelect, LIST_LAYOUT, menuInputOfKey, menuInputOfPad, PICKER_LAYOUT, promptLines, WEAPON_SELECT_KEY_READING, weaponSelectLayout,
  type PromptInfo, type WeaponSelectLayout,
} from './weaponSelect';
import {
  canOpen, closedMenu, reset, step, stepSlot, type MenuContext, type MenuInput, type MenuState,
} from './weaponSelectState';

/**
 * WEAPON EXCHANGE in the match (web sprint 4, M8's wiring; research 94 part 2): the pure menu (`./weaponSelectState`)
 * and its drawing (`./weaponSelect`) held for the page -- the gate, the three ways in, the keys and the pad inside, the
 * taps, the confirms handed on, the room's answer shown, the round's reset.
 *
 * - **The gate** (§B2, `FUN_001f7ff0` L56648-56661, tick L89369-89374): the menu opens only in the match (the page's own
 *   room or a server: `&nomatch`'s free walk has none), dead (a ghost too), the camera on oneself, not a spectator
 *   (`canOpen`). The ways in are the pad's R2 (`Inventory`, the Default config), the PC key `I`
 *   (`WEAPON_SELECT_KEY_READING`) and the touch button shown while the prompt is (`WEAPON_SELECT_TOUCH_READING`).
 * - **Inside** (§B3): the keys per `menuInputOfKey` (`WEAPON_SELECT_MENU_KEYS_READING`), the pad per `menuInputOfPad`,
 *   each a just-pressed edge. While the menu is open the controller's HUD mode is 1 (`FUN_00597740(ctrl, 1, 0)`
 *   L88370): the respawn press and the spectator camera's buttons do nothing (`FUN_00592560` L451673-451675,
 *   `FUN_00295260` L139475), and so the page takes every key and button from the game while it is open -- the dead's
 *   teammate cycle included (`DEAD_CYCLE_WHILE_MENU_READING`, `./netPage`).
 * - **A confirm** (S4, `FUN_0023e5e0`): the pick is handed to the page (`confirm`), which sends the side's list as the
 *   `loadout` request (protocol 7; `./netPage`, `./loadout`); the room's answer -- the kit it will spawn the player
 *   with -- is what the menu then shows (`answer`).
 * - **The round's reset** (S8, `FUN_002a7d40` -> `FUN_001fb790` -> `FUN_00240d50`): the menu closes over the kit the
 *   spawn took (`reset`); an unconfirmed pick is lost.
 * - The menu is silent (R94.3, `WEAPON_SELECT_SOUND_READING`).
 */

/** Where the page stands for the gate (`canOpen`'s four answers). */
export interface MatchGate { inMatch: boolean; alive: boolean; cameraOnSelf: boolean; spectator: boolean }

export interface WeaponExchangeDeps {
  /** Seconds, the menu's own clock (its fades and pulses). */
  clock: () => number;
  /** The kit the menu opens on: the type's as it stands (`FUN_0023e370` reads `character+0x540`) -- the pick held, else its own. */
  opensOn: () => Loadout;
  /** A confirm (S4): the slot and the item put in it. */
  confirm: (pick: Pick) => void;
}

/** A pad's standard buttons that are down (the Gamepad API's `pressed`, or a value past `PAD_PRESS`), by the PS2 pad's names. */
export function padButtonsDown(pad: GamepadLike | null | undefined): Set<PadButton> {
  const out = new Set<PadButton>();
  if (!pad) return out;
  for (const [name, index] of Object.entries(PAD_BUTTON) as [PadButton, number][]) {
    const b = pad.buttons[index];
    if (b && (b.pressed || b.value >= PAD_PRESS)) out.add(name);
  }
  return out;
}

export class WeaponExchange {
  private ctx: MenuContext | null = null;
  private menu: MenuState;
  private openedAt = -Infinity;
  private closedAt: number | null = null;

  constructor(private readonly deps: WeaponExchangeDeps) {
    // Closed over nothing until it opens: the kit it opens on is asked then (the page's side may not be known yet).
    this.menu = closedMenu([EMPTY_ITEM, EMPTY_ITEM, EMPTY_ITEM, EMPTY_ITEM, EMPTY_ITEM]);
  }

  /** The arsenal, the map's valves and the player's side; null (no `ZWEAPON.ZAR`, no match) closes the menu for good. */
  setContext(ctx: MenuContext | null): void {
    this.ctx = ctx;
    if (!ctx && this.isOpen()) this.close();
  }

  context(): MenuContext | null { return this.ctx; }
  state(): MenuState { return this.menu; }
  isOpen(): boolean { return this.menu.screen !== 'closed'; }

  /**
   * One just-pressed input, through the gate while closed. Returns whether the menu took it -- open, it takes every
   * input (HUD mode 1); closed, only the one that opened it.
   */
  input(input: MenuInput | null, gate: MatchGate): boolean {
    const ctx = this.ctx;
    if (!ctx) return false;
    const wasOpen = this.isOpen();
    if (!wasOpen) {
      if (input !== 'inventory' || !canOpen(gate)) return false;
      // The lists open on the kit the type holds (`FUN_0023e370` L88306): the room's answer, else its own.
      this.menu = closedMenu(this.deps.opensOn());
    }
    if (input === null) return wasOpen;
    const { state, event } = step(ctx, this.menu, input, canOpen(gate));
    this.menu = state;
    if (event?.kind === 'opened') { this.openedAt = this.deps.clock(); this.closedAt = null; }
    if (event?.kind === 'closed') this.closedAt = this.deps.clock();
    if (event?.kind === 'confirmed') this.deps.confirm(event.pick);
    return true;
  }

  /** A key's `code` (`KeyboardEvent.code`): closed, only `I` is the menu's; open, `menuInputOfKey`'s map, every key taken. */
  key(code: string, gate: MatchGate): boolean {
    if (!this.isOpen()) return code === WEAPON_SELECT_KEY_READING.code && this.input('inventory', gate);
    return this.input(menuInputOfKey(code), gate);
  }

  /** The pad's buttons pressed this frame: closed, R2 opens; open, `menuInputOfPad`'s map, one step a press. */
  pad(pressed: ReadonlySet<PadButton>, gate: MatchGate): boolean {
    let taken = false;
    for (const b of pressed) {
      const input = menuInputOfPad(b);
      if (!this.isOpen() && input !== 'inventory') continue;
      taken = this.input(input, gate) || taken;
    }
    return taken || this.isOpen();
  }

  /** The touch button (`WEAPON_SELECT_TOUCH_READING`): `Inventory`, as R2 -- opens, or closes the list. */
  touchButton(gate: MatchGate): boolean {
    return this.input('inventory', gate);
  }

  /** A tap on the frame (640x448 coordinates) while the menu is open: the inputs `menuTap` reads there. */
  tap(fx: number, fy: number, gate: MatchGate): boolean {
    if (!this.ctx || !this.isOpen()) return false;
    for (const i of menuTap(this.ctx, this.menu, fx, fy)) this.input(i, gate);
    return true;
  }

  /** The room's answer (protocol 7): the kit it holds for the next round, which the menu's rows now show. */
  answer(kit: Loadout): void {
    this.menu = { ...this.menu, loadout: kit };
  }

  /** S8: the round's reset closes the menu over the kit the spawn took. */
  reset(kit: Loadout): void {
    if (this.isOpen()) this.closedAt = this.deps.clock();
    this.menu = reset(kit);
  }

  private close(): void {
    this.closedAt = this.deps.clock();
    this.menu = { ...this.menu, screen: 'closed' };
  }

  /** The menu and the prompt on the frame now (`weaponSelectLayout`); null prompt: none (alive, following, a spectator). */
  layout(prompt: PromptInfo | null): WeaponSelectLayout {
    const now = this.deps.clock();
    const ctx = this.ctx;
    const opts = { ...(prompt ? { prompt } : {}), ...(this.closedAt !== null ? { closedFor: now - this.closedAt } : {}) };
    if (!ctx) return { items: prompt ? promptLines(prompt) : [] };
    return weaponSelectLayout(this.menu, ctx, now - this.openedAt, opts);
  }

  /** The HUD overlay's quads (`hud.setOverlay`): the menu, fading, and the prompt, on its own element. */
  draw(frame: { width: number; height: number }, sizes: Record<string, { width: number; height: number }>, prompt: PromptInfo | null): { quads: HudQuad[]; tris: HudTri[] } {
    return drawWeaponSelect(frame, this.layout(prompt), sizes);
  }
}

/** A point on the canvas (its CSS pixels, `width` x `height`) on the 640x448 frame: `drawWeaponSelect`'s mapping undone. */
export function frameOfPoint(px: number, py: number, canvas: { width: number; height: number }): [number, number] {
  const s = canvas.height / 448;
  return [(px - canvas.width / 2) / s + 320, py / s];
}

const inside = (x: number, y: number, r: { x: number; y: number; w: number; h: number }): boolean =>
  x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;

/**
 * WEAPON_SELECT_TOUCH_READING's "rows and cards tappable once open": a tap's place on the frame (§B5's rectangles) as
 * the pad presses that reach it. The list: a row -- the cursor stepped to it (Down, as `stepSlot` walks, a locked row
 * never reached) and Action; the picker panel -- Action. The picker: the category arrows Left / Right, the item arrows
 * Up / Down, the top and bottom cards Up / Down, the middle card Action (confirm), anywhere else Triangle (back).
 */
export function menuTap(ctx: MenuContext, s: MenuState, fx: number, fy: number): MenuInput[] {
  const L = LIST_LAYOUT, P = PICKER_LAYOUT;
  const picker = { x: P.panel.x, y: P.panel.y, w: P.panel.w, h: P.body.y + P.body.h - P.panel.y };
  if (s.screen === 'list') {
    for (let i = 0; i < 5; i++) {
      if (!inside(fx, fy, { ...L.bar, y: L.bar.y + L.bar.pitch * i })) continue;
      const steps: MenuInput[] = [];
      let at = s;
      for (let k = 0; k < 5 && at.slot !== i; k++) { at = { ...at, slot: stepSlot(ctx, at, 1) }; steps.push('down'); }
      return at.slot === i ? [...steps, 'action'] : [];
    }
    return inside(fx, fy, picker) ? ['action'] : [];
  }
  if (s.screen !== 'picker') return [];
  const [left, right] = P.categoryArrows;
  const size = 32;                                      // `hud_arrow_off2.tif`, 32x32 at native size (§B5)
  if (inside(fx, fy, { x: left.x, y: left.y, w: size, h: size })) return ['left'];
  if (inside(fx, fy, { x: right.x, y: right.y, w: size, h: size })) return ['right'];
  const [up, down] = P.itemArrows;
  if (inside(fx, fy, up)) return ['up'];
  if (inside(fx, fy, down)) return ['down'];
  // Card i runs from its name's line (y0 - 20) to the next card's: the middle one is the highlight's 226..290.
  for (let i = 0; i < 3; i++) {
    const y0 = P.cards.y + P.cards.pitch * i;
    if (inside(fx, fy, { x: P.cards.x, y: y0 + P.highlight.y - P.cards.y - P.cards.pitch, w: P.highlight.w, h: P.cards.pitch })) {
      return [i === 0 ? 'up' : i === 2 ? 'down' : 'action'];
    }
  }
  return ['back'];
}

/**
 * The `loadout` request's list kept short: every confirm is kept (the room replays them all from the type's kit, so a
 * reconnect lands on the same kit), and a list that would grow past the useful is replaced by one pick a changed slot
 * -- primary first, as the menu would make them -- when that reaches the very kit the long list does (`applyPicks`
 * through the same rules); otherwise the long list stands.
 */
export function compactPicks(ctx: MenuContext, base: Loadout, picks: readonly Pick[]): Pick[] {
  const want = applyPicks(ctx.arsenal, ctx.valves, ctx.side, base, picks);
  if ('refused' in want) return [...picks];
  const out: Pick[] = [];
  let kit = base;
  for (let slot = 0; slot < 5; slot++) {
    const id = want.loadout[slot]!;
    if (kit[slot] === id) continue;
    const seen = menuValves(ctx.valves, kit[0]);
    if (slotLocked(seen, ctx.side, kit, slot) || !selectable(seen, ctx.side, kit, slot, id)) return [...picks];
    kit = pickItem(ctx.arsenal, ctx.valves, ctx.side, kit, slot, id).loadout;
    out.push({ slot, id });
  }
  const same = kit.every((id, i) => id === want.loadout[i]);
  return same && out.length < picks.length ? out : [...picks];
}
