import { describe, expect, it } from 'vitest';
import { Fog, Scene } from 'three';
import { applyFog, fogCoefficient, fogForExtent, type FogSettings } from '../src/fog';

/**
 * The coefficient is pinned against the game's own arithmetic: `scale = -255/(far-near)`,
 * `offset = 255 - near*scale`, `F = clamp(offset + scale*dist, 0, 255)`. M51's 600/875 are the one
 * pair read off a live VU1 dump, so they are the fixture.
 */
describe('fogCoefficient', () => {
  const NEAR = 600, FAR = 875;

  it('is unfogged at and inside the near plane', () => {
    expect(fogCoefficient(NEAR, NEAR, FAR)).toBeCloseTo(255, 6);
    expect(fogCoefficient(0, NEAR, FAR)).toBe(255);
    expect(fogCoefficient(-50, NEAR, FAR)).toBe(255);      // behind the camera still clamps
  });

  it('is fully fogged at and beyond the far plane', () => {
    expect(fogCoefficient(FAR, NEAR, FAR)).toBeCloseTo(0, 6);
    expect(fogCoefficient(FAR * 10, NEAR, FAR)).toBe(0);
  });

  it('falls linearly between them', () => {
    const mid = fogCoefficient((NEAR + FAR) / 2, NEAR, FAR);
    expect(mid).toBeCloseTo(127.5, 6);
    // Equal steps in distance are equal steps in F.
    const a = fogCoefficient(650, NEAR, FAR);
    const b = fogCoefficient(700, NEAR, FAR);
    const c = fogCoefficient(750, NEAR, FAR);
    expect(a - b).toBeCloseTo(b - c, 6);
  });

  it('matches the EE offset/scale form exactly', () => {
    const scale = -255 / (FAR - NEAR);
    const offset = 255 - NEAR * scale;
    for (const d of [600, 640, 700, 800, 874]) {
      expect(fogCoefficient(d, NEAR, FAR)).toBeCloseTo(offset + scale * d, 9);
    }
    // The documented identity: offset is 255*far/(far-near).
    expect(offset).toBeCloseTo(255 * FAR / (FAR - NEAR), 9);
  });

  it('refuses a zero or inverted span rather than returning the hardware NaN', () => {
    expect(fogCoefficient(100, 500, 500)).toBe(255);
    expect(fogCoefficient(100, 900, 500)).toBe(255);
    expect(Number.isNaN(fogCoefficient(100, 500, 500))).toBe(false);
  });
});

describe('applyFog', () => {
  const base: FogSettings = { enabled: true, near: 600, far: 875, color: [74, 74, 72] };

  it('puts a linear fog on the scene with the register colour undecoded', () => {
    const scene = new Scene();
    applyFog(scene, base);
    const fog = scene.fog as Fog;
    expect(fog).toBeInstanceOf(Fog);
    expect(fog.near).toBe(600);
    expect(fog.far).toBe(875);
    // FOGCOL is a raw register value: 74/255 must survive as 74/255, not be sRGB-decoded.
    expect(fog.color.r).toBeCloseTo(74 / 255, 6);
    expect(fog.color.b).toBeCloseTo(72 / 255, 6);
  });

  it('updates in place rather than replacing, so a slider does not churn the scene', () => {
    const scene = new Scene();
    applyFog(scene, base);
    const first = scene.fog;
    applyFog(scene, { ...base, far: 1200 });
    expect(scene.fog).toBe(first);
    expect((scene.fog as Fog).far).toBe(1200);
  });

  it('clears the fog when it is switched off or the span is degenerate', () => {
    const scene = new Scene();
    applyFog(scene, base);
    applyFog(scene, { ...base, enabled: false });
    expect(scene.fog).toBe(null);

    applyFog(scene, base);
    applyFog(scene, { ...base, near: 900, far: 900 });
    expect(scene.fog).toBe(null);
  });
});

describe('fogForExtent', () => {
  it('scales with the map and keeps near under far', () => {
    for (const d of [500, 1500, 4000]) {
      const { near, far } = fogForExtent(d);
      expect(near).toBeLessThan(far);
      expect(far).toBeLessThanOrEqual(d);
      expect(near).toBeGreaterThan(0);
    }
  });
});
