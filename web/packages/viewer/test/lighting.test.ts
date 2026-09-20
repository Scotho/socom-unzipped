import { describe, expect, it } from 'vitest';
import { applyLighting, DEFAULT_LIGHTING, FALLBACK_RIG, LIT_SCALE, type Lightable, type Lighting } from '../src/lighting';
import type { GlobalLighting } from '@s2u/scene';

/**
 * The VU's `lit` (dispatcher command `0x18` -> `0x1440`), with the matrix read as what a live capture
 * says it is -- three light directions in the *columns* of `vf5`-`vf7`:
 *
 *   lit         = C0*max(dot(D0,N),0) + C1*max(dot(D1,N),0) + C2*max(dot(D2,N),0) + ambient
 *   staging + 1 = record2 * lit
 *
 * with the w lane taken from the staging quad rather than from `lit` -- so alpha passes through.
 */

/** A rig whose three lights are the axes, so the arithmetic below can be read off by eye. */
const AXES: GlobalLighting = {
  directions: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  colours: [[0.25, 0.25, 0.25], [1, 1, 1], [0.125, 0.125, 0.125]],
  ambient: [0.5, 0.5, 0.5],
};
const LIGHT: Lighting = { rig: AXES, ambient: 0, gain: 2 };

/** One vertex: a material colour and a normal. */
const one = (rgba: number[], n: number[] | null): Lightable => ({
  colors: Float32Array.from(rgba),
  normals: n ? Float32Array.from(n) : null,
});

const lit = (part: Lightable, light: Lighting = LIGHT): number[] => {
  const out = new Float32Array(part.colors.length);
  applyLighting(part, light, out);
  return [...out];
};

describe('applyLighting', () => {
  it('multiplies the material by ambient plus each light it faces, times the exposure', () => {
    // Straight up: ambient + the y light, doubled. 0.5 * (0.5 + 1) * 2 = 1.5.
    expect(lit(one([0.5, 0.5, 0.5, 1], [0, 1, 0]))).toEqual([1.5, 1.5, 1.5, 1]);
    // Straight along +x: ambient + the x light. 0.5 * (0.5 + 0.25) * 2 = 0.75.
    expect(lit(one([0.5, 0.5, 0.5, 1], [1, 0, 0]))).toEqual([0.75, 0.75, 0.75, 1]);
  });

  it('clamps each light at zero, so a face turned away from one takes nothing from it', () => {
    // -y faces away from the y light: 0.5 * 0.5 * 2 = 0.5.
    expect(lit(one([0.5, 0.5, 0.5, 1], [0, -1, 0]))).toEqual([0.5, 0.5, 0.5, 1]);
    // The clamp is per light, not on the sum: a normal facing away from y still collects x.
    expect(lit(one([0.5, 0.5, 0.5, 1], [1, -1, 0]))).toEqual([0.75, 0.75, 0.75, 1]);
  });

  it('is a dot product, so a light at an angle contributes its cosine', () => {
    const half = Math.SQRT1_2;
    // 45 degrees between +x and +y: each of those two lights gives its colour times 0.7071.
    const [r] = lit(one([1, 1, 1, 1], [half, half, 0]));
    expect(r).toBeCloseTo((0.5 + 0.25 * half + 1 * half) * 2, 6);
  });

  it('lights each channel by its own light colour, not by a single scalar', () => {
    const tinted: Lighting = {
      rig: { directions: [[0, 1, 0], [0, 0, 0], [0, 0, 0]], colours: [[1, 0.5, 0], [0, 0, 0], [0, 0, 0]], ambient: [0, 0, 0] },
      ambient: 0, gain: 1,
    };
    expect(lit(one([1, 1, 1, 1], [0, 1, 0]), tinted)).toEqual([1, 0.5, 0, 1]);
  });

  it('does not clamp the product: the GS clamps at the framebuffer, not here', () => {
    // Unity material, straight up: (0.5 + 1) * 2 = 3, and 3 is what comes out.
    expect(lit(one([1, 1, 1, 1], [0, 1, 0]))).toEqual([3, 3, 3, 1]);
  });

  it('passes alpha through untouched, however bright the light', () => {
    for (const a of [0, 0.25, 0.5, 1]) {
      expect(lit(one([0.5, 0.5, 0.5, a], [0, 1, 0]))[3]).toBe(a);
    }
  });

  it('lights each channel by its own material value', () => {
    expect(lit(one([1, 0.5, 0, 1], [0, 1, 0]))).toEqual([3, 1.5, 0, 1]);
  });

  it('falls back to half of every light when a merge lost the normals', () => {
    // The mean of max(dot(d, n), 0) over a sphere is a half, so that is what a normal-less part takes.
    const expected = 0.5 * (0.5 + (0.25 + 1 + 0.125) / 2) * 2;
    const [r] = lit(one([0.5, 0.5, 0.5, 1], null));
    expect(r).toBeCloseTo(expected, 6);
  });

  it('handles several vertices in one pass, each by its own normal', () => {
    const part = one(
      [0.5, 0.5, 0.5, 1, 0.5, 0.5, 0.5, 0.25],
      [0, 1, 0, 0, -1, 0],
    );
    expect(lit(part)).toEqual([1.5, 1.5, 1.5, 1, 0.5, 0.5, 0.5, 0.25]);
  });

  it('a zero normal takes the ambient alone, not the flat fallback', () => {
    // The `normals` array exists, so the per-vertex path runs: no light's dot product is positive.
    expect(lit(one([0.5, 0.5, 0.5, 1], [0, 0, 0]))).toEqual([0.5, 0.5, 0.5, 1]);
  });

  it('the ambient slider is a trim added to the map\'s own ambient, not a replacement', () => {
    const trimmed: Lighting = { rig: AXES, ambient: 0.25, gain: 1 };
    // 0.5 * (0.5 + 0.25) with no light facing: the map's 0.5 plus the trim's 0.25.
    expect(lit(one([0.5, 0.5, 0.5, 1], [0, -1, 0]), trimmed)).toEqual([0.375, 0.375, 0.375, 1]);
  });

  it('lights with a stand-in rig, not with nothing, when a map has no GlobalLighting record', () => {
    const none: Lighting = { ...DEFAULT_LIGHTING, rig: null };
    const up = lit(one([0.5, 0.5, 0.5, 1], [0, 1, 0]), none)[0]!;
    const down = lit(one([0.5, 0.5, 0.5, 1], [0, -1, 0]), none)[0]!;
    expect(up).toBeCloseTo(0.5 * (FALLBACK_RIG.ambient[0] + FALLBACK_RIG.colours[0]![0]) * LIT_SCALE, 6);
    expect(down).toBeCloseTo(0.5 * FALLBACK_RIG.ambient[0] * LIT_SCALE, 6);
    expect(up).toBeGreaterThan(down);
  });

  it('the shipped defaults add no trim, and carry the measured scale as the exposure', () => {
    expect(DEFAULT_LIGHTING.ambient).toBe(0);
    expect(DEFAULT_LIGHTING.gain).toBe(LIT_SCALE);
    expect(LIT_SCALE).toBe(8);
  });
});
