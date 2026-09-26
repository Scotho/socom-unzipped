import type { GsState } from '@s2u/gs';

/**
 * What the viewer knows about one texture: the two record flags it always read, the two facts it reads
 * off the decoded pixels, and -- since the audit of 2026-09-26 -- the GS state the record's own bind
 * packet sets (`@s2u/gs`'s `GsState`), which is what the pixel facts used to stand in for.
 */
export interface TextureFlags {
  bilinear: boolean;
  transparent: boolean;
  /** The alpha is a ramp (a glow, a corona) rather than a switch (a leaf, a grating). */
  graded: boolean;
  /** Every sampled texel is solid. Decides backface culling: a solid skin is closed, a sheet is not. */
  opaque: boolean;
  gs: GsState | null;
}

export type Blending = 'normal' | 'additive';

/** A three material, described without three: what `world.ts` sets on a `MeshBasicMaterial` and its texture. */
export interface MaterialSpec {
  transparent: boolean;
  blending: Blending;
  /** 0 for none; otherwise the threshold in 0..1. */
  alphaTest: number;
  depthWrite: boolean;
  /** Backface culling on: the texture is fully solid, so the surface is a closed skin (spec 2026-09-20 §9). */
  cull: boolean;
  wrapS: 'repeat' | 'clamp';
  wrapT: 'repeat' | 'clamp';
  bilinear: boolean;
  mipmaps: boolean;
  /** `PRIM.FGE` of the packet that draws it: off for skies, water and self-lit surfaces. */
  fog: boolean;
}

/**
 * The disc's state, read into a material.
 *
 * Three kinds of alpha, and the disc distinguishes two of them:
 *
 * - **A cutout** -- `TEST.ATE = 1` -- is punched through at the reference the register gives (`AREF /
 *   128`, 0.5 on every one in the corpus) and blends nothing. It writes depth and needs no sorting.
 * - **A switch drawn with a blend** -- `ATE = 0` but the alpha is only ever 0 or full -- blends to the
 *   same picture a cutout gives, because `(Cs - Cd) * As + Cd` at `As` in {0, 1} *is* a cutout; the
 *   hardware wrote depth under its clear texels and lived with it, and a cutout is the better copy.
 * - **A ramp** -- a glow, a flare, a soft decal -- is blended with the equation the disc asks for:
 *   source alpha, or additive for `(Cs - 0) * As + Cd`. The destination-brighten `(Cd - 0) * As + Cd`
 *   and the EE-animated `FIX` factor have no fixed-function equivalent in a browser and are drawn
 *   additive, the nearest thing. A blended draw writes no depth, or the ones drawn first would cut
 *   holes in the ones behind.
 *
 * `honourDisc` off is the escape hatch the panel's toggle offers: every texture with alpha becomes a
 * cutout at half, which sorts perfectly and looks wrong, and is what the viewer drew before the
 * blend modes were read.
 *
 * Wrap and filtering come off `CLAMP` and `TEX1`. A record with no state block (none in the corpus,
 * kept for a damaged one) falls back to the old pixel rules: a ramp clamps, everything else repeats.
 */
export function materialSpec(flags: TextureFlags | undefined, fog: boolean, honourDisc: boolean): MaterialSpec {
  const gs = flags?.gs ?? null;
  const graded = flags?.graded ?? false;
  const hasAlpha = flags ? !flags.opaque : false;
  const wrap = gs
    ? { wrapS: gs.wrapS, wrapT: gs.wrapT }
    : { wrapS: graded ? 'clamp' as const : 'repeat' as const, wrapT: graded ? 'clamp' as const : 'repeat' as const };
  const base = {
    cull: flags?.opaque ?? false,
    ...wrap,
    bilinear: gs?.bilinear ?? flags?.bilinear ?? true,
    mipmaps: gs?.mipmaps ?? false,
    fog,
  };
  if (!hasAlpha) return { ...base, transparent: false, blending: 'normal', alphaTest: 0, depthWrite: true };

  const cutout = (at: number): MaterialSpec => ({ ...base, transparent: false, blending: 'normal', alphaTest: at, depthWrite: true });
  if (!honourDisc) return cutout(flags?.transparent ? 0.5 : 0);
  if (gs?.alphaTest !== null && gs?.alphaTest !== undefined) return cutout(gs.alphaTest);
  if (!graded) return cutout(0.5);
  const blend = gs?.blend ?? 'source';
  if (blend === 'none') return cutout(0.5);
  return {
    ...base, transparent: true, alphaTest: 0, depthWrite: false,
    blending: blend === 'source' ? 'normal' : 'additive',
  };
}
