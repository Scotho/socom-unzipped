import { describe, expect, it } from 'vitest';
import { materialSpec, type TextureFlags } from '../src/materialSpec';
import type { GsState } from '@s2u/gs';

/**
 * How a texture's disc state becomes a three material. Pure, so the whole table is pinned here
 * without a renderer: the blend, the alpha test, the depth write, the wrap, the mipmaps and the fog.
 */
const gs = (over: Partial<GsState> = {}): GsState => ({
  blend: 'source', alphaTest: null, depthTest: true, bilinear: true, mipmaps: false, levels: 0,
  wrapS: 'repeat', wrapT: 'repeat', ...over,
});
const flags = (over: Partial<TextureFlags> = {}): TextureFlags => ({
  bilinear: true, transparent: false, graded: false, opaque: true, gs: gs(), ...over,
});

describe('materialSpec, honouring the disc', () => {
  it('a solid wall is opaque, culled, repeating, bilinear, fogged', () => {
    expect(materialSpec(flags(), true, true)).toEqual({
      transparent: false, blending: 'normal', alphaTest: 0, depthWrite: true, cull: true,
      wrapS: 'repeat', wrapT: 'repeat', bilinear: true, mipmaps: false, fog: true,
    });
  });

  it('a packet whose FGE is clear is not fogged', () => {
    expect(materialSpec(flags(), false, true).fog).toBe(false);
  });

  it('a cutout with the alpha test on the disc tests at the reference the disc gives', () => {
    const spec = materialSpec(flags({ transparent: true, opaque: false, gs: gs({ blend: 'none', alphaTest: 0.5 }) }), true, true);
    expect(spec).toMatchObject({ transparent: false, alphaTest: 0.5, depthWrite: true, cull: false });
  });

  it('a one-bit texture drawn with a blend and no test is still a cutout: blending a switch is a cutout', () => {
    const spec = materialSpec(flags({ transparent: true, opaque: false }), true, true);
    expect(spec).toMatchObject({ transparent: false, alphaTest: 0.5, depthWrite: true });
  });

  it('a graded texture blends with the source-alpha equation and writes no depth', () => {
    const spec = materialSpec(flags({ transparent: true, graded: true, opaque: false }), true, true);
    expect(spec).toMatchObject({ transparent: true, blending: 'normal', alphaTest: 0, depthWrite: false });
  });

  it('a graded texture whose ALPHA is (Cs - 0) * As + Cd adds', () => {
    const spec = materialSpec(flags({ transparent: true, graded: true, opaque: false, gs: gs({ blend: 'additive' }) }), true, true);
    expect(spec).toMatchObject({ transparent: true, blending: 'additive', depthWrite: false });
  });

  it('the destination brighten and the fixed factor are drawn as additive, the nearest fixed-function blend', () => {
    for (const blend of ['destination', 'fixed'] as const) {
      const spec = materialSpec(flags({ transparent: true, graded: true, opaque: false, gs: gs({ blend }) }), true, true);
      expect(spec.blending, blend).toBe('additive');
    }
  });

  it('takes the wrap modes and the mipmap request off the disc', () => {
    const spec = materialSpec(flags({ gs: gs({ wrapS: 'clamp', wrapT: 'repeat', mipmaps: true, levels: 1 }) }), true, true);
    expect(spec).toMatchObject({ wrapS: 'clamp', wrapT: 'repeat', mipmaps: true });
  });

  it('falls back to the pixel heuristics when a record has no state block', () => {
    const graded = materialSpec(flags({ transparent: true, graded: true, opaque: false, gs: null }), true, true);
    expect(graded).toMatchObject({ transparent: true, blending: 'normal', wrapS: 'clamp', wrapT: 'clamp', mipmaps: false });
    const wall = materialSpec(flags({ gs: null }), true, true);
    expect(wall).toMatchObject({ transparent: false, wrapS: 'repeat', wrapT: 'repeat' });
  });
});

describe('materialSpec with the disc blend switched off', () => {
  it('punches every texture with alpha out at half, as the viewer always did', () => {
    const spec = materialSpec(flags({ transparent: true, graded: true, opaque: false, gs: gs({ blend: 'additive' }) }), true, false);
    expect(spec).toMatchObject({ transparent: false, blending: 'normal', alphaTest: 0.5, depthWrite: true });
  });
});
