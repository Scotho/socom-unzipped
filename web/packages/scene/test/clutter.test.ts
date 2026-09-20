import { describe, expect, it } from 'vitest';
import { isAffineRowVector } from '../src/clutter';

/**
 * The guard that decides whether a clutter record's 96 bytes are the affine matrix the format
 * describes. It exists because Abandoned's records are something else in the same bytes, and composing
 * one as a matrix drew basis rows thousands of units long across the map while reporting nothing.
 *
 * The fixtures are real records, read off the disc with `web/tools/probe-clutter.ts`.
 */

/** Row-major, row-vector: rows 0-2 are basis vectors with a zero fourth lane, row 3 the translation. */
const m = (...v: number[]): Float32Array => Float32Array.from(v);

/** MP6 Desert Glory, `afghan2r_clutter_rocksmall`, instance 0. Places correctly. */
const DESERT_GLORY_ROCK = m(
  1.047, 0, -0.245, 0,
  0, 1.075, 0, 0,
  0.245, 0, 1.047, 0,
  1536.068, 0, 1771.973, 1,
);

/** MP5 Abandoned, `bamboo5`, instance 0: a unit quaternion in row 0 and a position in row 2. */
const ABANDONED_BAMBOO = m(
  0.067, 0.135, 0.051, 0.987,
  0, 0, 0, 1,
  1072, 56.339, 2205.6, 1,
  0.251, 0, 0, 1,
);

const IDENTITY = m(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1);

describe('isAffineRowVector', () => {
  it('accepts a real record that places correctly', () => {
    expect(isAffineRowVector(DESERT_GLORY_ROCK)).toBe(true);
    expect(isAffineRowVector(IDENTITY)).toBe(true);
  });

  it('rejects the record shape that drew Abandoned\'s streaks', () => {
    expect(isAffineRowVector(ABANDONED_BAMBOO)).toBe(false);
  });

  it('rejects a non-zero last column, which is what gives the quaternion form away', () => {
    for (const lane of [3, 7, 11]) {
      const bad = Float32Array.from(DESERT_GLORY_ROCK);
      bad[lane] = 0.987;
      expect(isAffineRowVector(bad), `lane ${lane}`).toBe(false);
    }
  });

  it('requires the homogeneous one', () => {
    const bad = Float32Array.from(DESERT_GLORY_ROCK);
    bad[15] = 0;
    expect(isAffineRowVector(bad)).toBe(false);
  });

  it('rejects a basis row that is degenerate or enormous', () => {
    const flat = Float32Array.from(DESERT_GLORY_ROCK);
    flat[4] = 0; flat[5] = 0; flat[6] = 0;              // row 1 collapsed
    expect(isAffineRowVector(flat)).toBe(false);

    const huge = Float32Array.from(DESERT_GLORY_ROCK);
    huge[8] = 2452.96;                                  // the scale the composed streaks showed
    expect(isAffineRowVector(huge)).toBe(false);
  });

  it('rejects anything non-finite', () => {
    for (const v of [NaN, Infinity, -Infinity]) {
      const bad = Float32Array.from(DESERT_GLORY_ROCK);
      bad[0] = v;
      expect(isAffineRowVector(bad), String(v)).toBe(false);
    }
  });

  it('tolerates the float noise a real record carries', () => {
    // The stored floats are not exact: a zero lane can read 1e-8 and the one can read 0.9999999.
    const noisy = Float32Array.from(DESERT_GLORY_ROCK);
    noisy[3] = 1e-8; noisy[7] = -2e-8; noisy[11] = 5e-9; noisy[15] = 0.99999994;
    expect(isAffineRowVector(noisy)).toBe(true);
  });

  it('accepts the full range of uniform scales the maps actually use', () => {
    // Desert Glory's scale_inverse runs about 0.93..1.08, so the basis rows run about 0.92..1.08.
    for (const s of [0.5, 0.93, 1, 1.075, 4, 49]) {
      const scaled = m(s, 0, 0, 0, 0, s, 0, 0, 0, 0, s, 0, 100, 200, 300, 1);
      expect(isAffineRowVector(scaled), `scale ${s}`).toBe(true);
    }
    // ... but not the thousands the malformed records compose into.
    const absurd = m(51, 0, 0, 0, 0, 51, 0, 0, 0, 0, 51, 0, 0, 0, 0, 1);
    expect(isAffineRowVector(absurd)).toBe(false);
  });
});
