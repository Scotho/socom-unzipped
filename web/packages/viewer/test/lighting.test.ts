import { describe, expect, it } from 'vitest';
import { applyLighting, DEFAULT_LIGHTING, type Lightable, type Lighting } from '../src/lighting';

/**
 * The VU's `lit` (dispatcher command `0x18` -> `0x1440`):
 *
 *   lit         = light[0]*n.x + light[1]*n.y + light[2]*n.z + light[3]   (normal clamped >= 0)
 *   staging + 1 = record2 * lit
 *
 * with the w lane taken from the staging quad rather than from `lit` -- so alpha passes through.
 */
const LIGHT: Lighting = { ambient: 0.5, x: 0.25, y: 1, z: 0.125, gain: 2 };

/** One vertex: a material colour and a normal. */
const one = (rgba: number[], n: number[] | null): Lightable => ({
  colors: Float32Array.from(rgba),
  normals: n ? Float32Array.from(n) : null,
});

const lit = (part: Lightable): number[] => {
  const out = new Float32Array(part.colors.length);
  applyLighting(part, LIGHT, out);
  return [...out];
};

describe('applyLighting', () => {
  it('multiplies the material by ambient plus the axis terms, times the gain', () => {
    // Straight up: ambient + y, doubled. 0.5 * (0.5 + 1) * 2 = 1.5.
    expect(lit(one([0.5, 0.5, 0.5, 1], [0, 1, 0]))).toEqual([1.5, 1.5, 1.5, 1]);
    // Straight along +x: ambient + x. 0.5 * (0.5 + 0.25) * 2 = 0.75.
    expect(lit(one([0.5, 0.5, 0.5, 1], [1, 0, 0]))).toEqual([0.75, 0.75, 0.75, 1]);
  });

  it('clamps each normal component at zero, so a face pointing away takes only the ambient', () => {
    // -y gets nothing from the +y light: 0.5 * 0.5 * 2 = 0.5.
    expect(lit(one([0.5, 0.5, 0.5, 1], [0, -1, 0]))).toEqual([0.5, 0.5, 0.5, 1]);
    // And the clamp is per component, not per vector: -y still collects +x.
    expect(lit(one([0.5, 0.5, 0.5, 1], [1, -1, 0]))).toEqual([0.75, 0.75, 0.75, 1]);
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

  it('falls back to the mean of the three axes when a merge lost the normals', () => {
    // (0.5 + (0.25 + 1 + 0.125)/3) * 2 = 1.9166..., times 0.5.
    const expected = 0.5 * (0.5 + (0.25 + 1 + 0.125) / 3) * 2;
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
    // The `normals` array exists, so the per-vertex path runs: no axis term is positive.
    expect(lit(one([0.5, 0.5, 0.5, 1], [0, 0, 0]))).toEqual([0.5, 0.5, 0.5, 1]);
  });

  it('the shipped defaults put a night map in a sane range', () => {
    const material = 0.29;                              // the measured mean, in units of the PS2's unity
    const at = (n: number[]): number => {
      const out = new Float32Array(4);
      applyLighting(one([material, material, material, 1], n), DEFAULT_LIGHTING, out);
      return out[0]!;
    };
    const up = at([0, 1, 0]), side = at([1, 0, 0]), under = at([0, -1, 0]);
    expect(up).toBeGreaterThan(side);
    expect(side).toBeGreaterThan(under);
    expect(up).toBeLessThan(1);                         // a lit surface is bright, not blown out
    expect(under).toBeGreaterThan(0.05);                // and an underside is dim, not black
  });
});
