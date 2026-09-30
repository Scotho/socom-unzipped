import { Vector4 } from 'three';
import type { Node } from 'three/webgpu';
import { float, select, uniform, vec4 } from 'three/tsl';
import { lensRow, ROW_A, ROW_RGB, type LensColour } from './lensFx';

/**
 * The night vision's colour as the engine applies it (research 84 section 14; web/redotcom/docs/research/82, round 4),
 * and the thermal scope's, which is the same machinery with other rows (research 94 §C7, `./lensFx`).
 *
 * Going into the goggles (`FUN_005c1800`, zoom state 3) the game calls `FUN_003b78d0(0, LensFX_NVG)`: four rows at
 * `0x4b4c70`, each `(0.33 r, 0.33 g, 0.33 b, 3.0303 a)` of the map's lens -- `(0.2, 0.898, 0.2, 0.24)` on every map --
 * and the flag `0x4b4a68`. While the flag is up every world and character packet (`FUN_003b41d0`, `FUN_003b5f20`) puts
 * VU1 command `0x5c` (`0x5e`/`0x60` for the other colour buffers) after the lighting (`0x18`, or the flat `0x54`) and
 * before the output (`0x28`), with the draw's row in its header (qword 13, `FUN_003b6870`, stored to VU `328`). The
 * command (`0x4d8`) rewrites each lit vertex colour in place:
 *
 *   `ACC = row * c.x; ACC += row * c.y; ACC += row * c.z; c.xyz = ACC + row * row.w`
 *
 * i.e. `c' = row.rgb * (R + G + B + row.a)`, alpha kept, in the lane's 0..255 units (128 the GS's unity) -- a lens-green
 * monochrome of the lit colour at about its brightness, which the textures then modulate. The fog's colour becomes the
 * lens's times its own (`cam+0xd0`). Leaving, `FUN_003b78d0(0.25, (1, 1, 1, 0))` sets the neutral rows, which drop the
 * flag (`FUN_003b7170`, once a frame: every row `(0.33, 0.33, 0.33, 0)`).
 *
 * **Which row a draw takes** (`FUN_003b6870` L308209-308249): its node's byte `+0x5a & 3` -- 0 for the world, 2 for a
 * character's model and gear (`FUN_00313240(model, 2)`, L406210/L406227). The goggles set all four alike, so one row
 * did; the thermal lens (`to_thermal_lens_fx`'s `SCALE_COLOR`s) sets them apart: the world's graphs take row 0
 * (`nightLit(lit)`), the bodies' row 2 (`nightLit(lit, 2)`). [The goggles' own rows 2-3 also fade toward row 0 from
 * 500 to 800 units off (L308224-308248, only while the goggles are on, `hud+0x4100`); all four are equal there, so the
 * fade changes nothing.]
 *
 * The viewer's lit colours are in units of the GS's unity (1 = 128), so the row's `a` term is divided by 128.
 */

export { ROW_A, ROW_RGB };
/** The lane's unity: the row's constant term is in 0..255 units, the viewer's colours in units of 128. */
const UNITY = 128;

/** 1 while a lens's rows are in (the flag `0x4b4a68`). */
const on = uniform(0);
/** Row 0 (the world's) and row 2 (the characters'): `0.33 x colour.rgb`, and the constant `3.03 x a` in the viewer's units. */
const row = uniform(new Vector4(ROW_RGB, ROW_RGB, ROW_RGB, 0));
const hot = uniform(new Vector4(ROW_RGB, ROW_RGB, ROW_RGB, 0));
/** The rows in use, as the commands gave them (null: off), for the page's stats. */
let current: LensColour[] | null = null;

/** The row `FUN_003b78d0` builds from a lens (the constant still in the lane's 0..255 units). */
export function nightRow(lens: readonly [number, number, number, number]): [number, number, number, number] {
  return lensRow(lens);
}

/** Command `0x5c` on one lit colour (RGBA, 1 = the GS's unity), for tests and the CPU side. */
export function nightColour(c: readonly [number, number, number, number], lens: readonly [number, number, number, number]): [number, number, number, number] {
  return lensColour(c, [lens, lens, lens, lens], 0);
}

/** Command `0x5c` with the draw's row `heat` of a lens's four colours (`SCALE_COLOR`'s, `./lensFx`). */
export function lensColour(
  c: readonly [number, number, number, number], colours: readonly (readonly number[])[], heat: number,
): [number, number, number, number] {
  const r = lensRow(colours[heat] ?? NEUTRAL);
  const sum = c[0] + c[1] + c[2] + r[3] / UNITY;
  return [r[0] * sum, r[1] * sum, r[2] * sum, c[3]];
}

/** The neutral colour (`FUN_003b78d0(0.25, (1, 1, 1, 0))`): its row `(0.33, 0.33, 0.33, 0)` drops the flag. */
const NEUTRAL: LensColour = [1, 1, 1, 0];

/** A colour whose row is the neutral `(0.33, 0.33, 0.33, 0)` (`FUN_003b7170`'s test, L308533/308543). */
function neutral(c: readonly number[] | null): boolean {
  if (!c) return true;
  const r = lensRow(c);
  return r[0] === ROW_RGB && r[1] === ROW_RGB && r[2] === ROW_RGB && r[3] === 0;
}

/**
 * A lens's four row colours in (`SCALE_COLOR`, `FUN_003b76b0`: a row it does not set stays neutral), or off (null).
 * Four neutral rows are off too: `FUN_003b7170` drops the flag when every row is `(0.33, 0.33, 0.33, 0)` -- the plain
 * scope's `to_scope_lens_fx` sets exactly that. The world's graphs take row 0, the bodies' row 2.
 */
export function setLensRows(colours: readonly (readonly number[] | null)[] | null): void {
  if (!colours || colours.every(neutral)) { on.value = 0; current = null; return; }
  current = [0, 1, 2, 3].map((i) => [...(colours[i] ?? NEUTRAL)] as LensColour);
  on.value = 1;
  const r0 = lensRow(current[0]!), r2 = lensRow(current[2]!);
  row.value.set(r0[0], r0[1], r0[2], r0[3] / UNITY);
  hot.value.set(r2[0], r2[1], r2[2], r2[3] / UNITY);
}

/** The goggles on (`lens`, the map's `LensFX_NVG`, all four rows) or off (null). */
export function setNightVision(lens: readonly [number, number, number, number] | null): void {
  setLensRows(lens ? [lens, lens, lens, lens] : null);
}

/** Row 0 in use (the world's, the row the goggles set on all four), or null with no lens on (the page's stats). */
export function nightVisionRow(): [number, number, number, number] | null {
  if (on.value === 0) return null;
  const v = row.value;
  return [v.x, v.y, v.z, v.w * UNITY];
}

/** The four row colours in use as the lens commands gave them, or null (the page's stats). */
export function lensColours(): LensColour[] | null {
  return current ? current.map((c) => [...c] as LensColour) : null;
}

/**
 * A lit colour through command `0x5c` while a lens is on, unchanged otherwise: the world's graphs (row 0) and the
 * characters' (`heat` 2: `FUN_00313240(model, 2)`).
 */
export function nightLit(lit: Node<'vec4'>, heat: 0 | 2 = 0): Node<'vec4'> {
  const r = heat === 2 ? hot : row;
  const sum = lit.r.add(lit.g).add(lit.b).add(r.w);
  const tinted = vec4(r.xyz.mul(sum), lit.a);
  return select(on.greaterThan(float(0.5)), tinted, lit) as unknown as Node<'vec4'>;
}
