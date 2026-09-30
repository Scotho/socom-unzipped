/**
 * The scope's lens effects, read off the map's zAnims (web sprint 4 M5; research 94 §C7, R94.15).
 *
 * A scoped view (states 5-12) starts one of three zAnims of the map's `MZANIM.ZAR` mission set (`FUN_001f0750`
 * L53084-53160, started by name through `FUN_002734b0`): `to_thermal_lens_fx` when the kit holds the thermal scope
 * (item 195), else `to_starlight_scope_lens_fx` on a night map, else `to_scope_lens_fx`. The zAnim command set
 * (`FUN_0025bc20` L106862-106925, one registration a command in index order after `Reserved`; the names read from the
 * retail ELF's `.rodata`) gives their commands' names: 28 `CAMERA` (0x3eceb0), 33 `BLUR3D` (0x3ecf08), 34
 * `IRIS_EFFECT` (0x3ecf10), **35 `SCALE_COLOR`** (0x3ecf20), 36 `TRUE_COLOR_SCALE` (0x3ecf30).
 *
 * `to_thermal_lens_fx`'s own sequence is two stops, **four `SCALE_COLOR`s**, a `VALVE` (the `lensfx` valve), an
 * `IRIS_EFFECT` and a `CAMERA`. `SCALE_COLOR`'s tick (`FUN_00264580` L111710-111728) hands its colour (the f32 quad at
 * `+8`) and its time (`+0x18`, seconds) to the lit-colour matrix: with flag 0x10 to all four rows at once
 * (`FUN_003b78d0` -- the night vision's call), else to each row whose bit (1, 2, 4, 8) is set (`FUN_003b76b0`
 * L308637-308696), which stores `(0.33 r, 0.33 g, 0.33 b, 3.030303 a)` and eases to it over the time (0: at once). A
 * draw takes the row of its node's byte `+0x5a & 3` (`FUN_003b6870` L308178-308261): the world's nodes keep 0, the
 * character's model and its gear are set to 2 (`FUN_00313240(model, 2)`, L406210 and L406227), the kit's weapon models
 * too (L480099). So on Frostfire's disc the thermal rows are row 0 (0.1, 0.33, 0.7, 0) -- the world a cold blue at
 * its brightness -- row 1 black, row 2 (0.5, 0.3, 0, 128) -- a body a bright orange whatever its light -- and row 3
 * (0.9, 0.65, 0, 50), unused by the retail code. `./nightVision` applies the rows (VU1 command 0x5c).
 *
 * `THERMAL_LENS_FX_READING` (research 94 "Placeholders (reader C)"): the `SCALE_COLOR` rows are ported, read at run
 * time; the thermal zAnim's `IRIS_EFFECT` (`FUN_00264610`: the exposure iris's mode, rates and colour) and `CAMERA`
 * (`FUN_00265f20`/`FUN_00266320`, 132 bytes of camera keys) are not decoded, nor the `restore_lensfx` sequence's
 * `CAMERA_PARAMS`/`BLUR3D`/`TRUE_COLOR_SCALE`; the viewer's held weapon keeps the world's row 0 (its materials are the
 * world's, `./world` `held`) where the game gives the kit's weapon row 2.
 */

/** The zAnim command `SCALE_COLOR` (set 0, command 35; `FUN_0025bc20` L106899, string 0x3ecf20). */
export const ZANIM_SCALE_COLOR = 35;
/** The lens zAnims a scoped view starts (`FUN_001f0750`), read with the map's effects (`./effectData`). */
export const LENS_ANIMS: readonly string[] = ['to_thermal_lens_fx', 'to_starlight_scope_lens_fx', 'to_scope_lens_fx'];

/** One lit-colour row as a command gives it: r, g, b and the constant a (in the VU lane's 0..255 units). */
export type LensColour = [number, number, number, number];

/** A lens zAnim's `SCALE_COLOR`s: each of the four rows' colour (null: not set by it), and the ease's seconds. */
export interface LensRows { rows: (LensColour | null)[]; seconds: number }

/** `FUN_003b76b0` / `FUN_003b78d0`'s scale of a command's colour into a row: rgb x 0.33, the constant x 3.030303. */
export const ROW_RGB = 0.33;
export const ROW_A = 3.030303;
export function lensRow(c: readonly number[]): LensColour {
  return [c[0]! * ROW_RGB, c[1]! * ROW_RGB, c[2]! * ROW_RGB, c[3]! * ROW_A];
}

/** The shape of a zAnim animation this reads (`@s2u/scene` `parseAnimSets`: its sequences' commands). */
export interface LensAnimLike { commands: { set: number; cmd: number; offset: number; size?: number }[] }

/**
 * A lens zAnim's `SCALE_COLOR` commands, in command order (a later one over an earlier): `sequences` the animation's,
 * `payload(offset, length)` a command's bytes out of its `Seq_Data`.
 */
export function scaleColorRows(sequences: readonly LensAnimLike[], payload: (offset: number, length: number) => Uint8Array | null): LensRows {
  const out: LensRows = { rows: [null, null, null, null], seconds: 0 };
  for (const q of sequences) {
    for (const c of q.commands) {
      if (c.set !== 0 || c.cmd !== ZANIM_SCALE_COLOR) continue;
      const b = payload(c.offset, c.size ?? 28);
      if (!b || b.length < 28) continue;
      const v = new DataView(b.buffer, b.byteOffset, b.byteLength);
      const flags = v.getUint32(4, true);
      const colour: LensColour = [v.getFloat32(8, true), v.getFloat32(12, true), v.getFloat32(16, true), v.getFloat32(20, true)];
      out.seconds = v.getFloat32(0x18, true);
      for (let row = 0; row < 4; row++) if (flags & 0x10 || flags & (1 << row)) out.rows[row] = [...colour];
    }
  }
  return out;
}
