import { Color, Fog, type Scene } from 'three';

/**
 * SOCOM II's fog, as the game computes it.
 *
 * The EE builds a scale and an offset from the level's near and far
 * (`sub_00294070`, guest `0x294730`-`0x294784`):
 *
 * ```
 *   scale  = -255 / (far - near)
 *   offset = 255 - near * scale        // = 255 * far / (far - near)
 * ```
 *
 * and uploads them to VU1 data qwords 28/29. Per vertex the coefficient is
 *
 * ```
 *   F = clamp(w * scale + offset, 0, 255)
 * ```
 *
 * where `w` is the **clip-space w — view depth along the camera axis**, not radial distance from the
 * eye. (`sub_002948D0`, `0x294924`-`0x294970`, computes the radial form, but that is the EE's own
 * mirror for CPU-side object fades; the per-vertex fog that shades world geometry is VU1 handlers
 * `0xf90` and `0x1108`, which read data qwords 28/29 and use `w`.) three's linear `Fog` measures
 * `-mvPosition.z`, which is the same quantity, so the two agree.
 *
 * The GS then blends `C = (F*C)>>8 + ((255-F)*FOGCOL)>>8`, i.e. `mix(FOGCOL, C, F/255)`: `F = 255` at
 * `near` is unfogged, `F = 0` at `far` is the fog colour outright. A vertex that never reaches the fog
 * command keeps the transform kernel's default `F = 254`, not 255 — a hair of fog on everything.
 *
 * The altitude term, `alt = clamp(dot(P - ref, scl), 0, 1)` with `F = base * alt`, is off on all three
 * extracted maps (six of the twenty-two use it) and multiplies by 1 when disabled.
 *
 * `FOGCOL` is not written by any EE instruction: it sits in a static 16-qword GS-state packet at
 * guest `0x003E0880` (value word at `0x003E08B0`) that the flip DMAs every frame, and the level
 * loader patches that qword per map. The ELF default in the slot is `0x00646464`.
 *
 * **Departures from the hardware.** `far == near` divides by zero on the hardware path too, and the
 * game's own note records the NaN; a zero or inverted span is refused here rather than propagated. The
 * altitude band is not applied — no VU1 dump exists from a map that enables it, so its encoding is the
 * one inferred piece of the model and the six maps that use it would be guesswork.
 */
export interface FogSettings {
  enabled: boolean;
  /** Distance at which fog starts, in game units — the geometry's own scale. */
  near: number;
  /** Distance at which fog is total. */
  far: number;
  /** `FOGCOL`, 0..255 per channel, as the GS register holds it. */
  color: [number, number, number];
}

/** The ELF's own default in the FOGCOL slot at `0x003E08B0`: grey 100,100,100. */
export const ELF_DEFAULT_FOGCOL: [number, number, number] = [0x64, 0x64, 0x64];

/**
 * A starting near/far for a map whose own numbers have not been read off the disc yet, derived from
 * how big the map is. Stated as a fraction of the world diagonal so it is at least the right order
 * of magnitude on a 100 m map and on a 400 m one.
 */
export function fogForExtent(diagonal: number): { near: number; far: number } {
  return { near: Math.round(diagonal * 0.35), far: Math.round(diagonal * 0.95) };
}

/**
 * The GS's `F` at a distance, for a test or a readout. Returns 0..255, 255 being unfogged.
 * Mirrors `sub_002948D0` including its clamp.
 */
export function fogCoefficient(dist: number, near: number, far: number): number {
  if (!(far > near)) return 255;                       // the hardware's NaN case, refused
  const scale = -255 / (far - near);
  const offset = 255 - near * scale;
  return Math.min(255, Math.max(0, offset + scale * dist));
}

/**
 * Puts the settings on the scene. The colour is set through `setRGB` on the working space rather than
 * `setHex`, which would apply an sRGB decode the GS never did — `FOGCOL` is a raw register value and
 * the viewer's default pipeline is the GS's own space.
 */
export function applyFog(scene: Scene, fog: FogSettings): void {
  if (!fog.enabled || !(fog.far > fog.near)) {
    scene.fog = null;
    return;
  }
  const [r, g, b] = fog.color;
  const colour = new Color().setRGB(r / 255, g / 255, b / 255);
  if (scene.fog instanceof Fog) {
    scene.fog.color.copy(colour);
    scene.fog.near = fog.near;
    scene.fog.far = fog.far;
  } else {
    scene.fog = new Fog(colour, fog.near, fog.far);
  }
}
