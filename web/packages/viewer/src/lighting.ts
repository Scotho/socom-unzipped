import type { GlobalLighting } from '@s2u/scene';

/** Everything the lighting needs: the material colours and, if they survived, the normals. */
export interface Lightable {
  colors: Float32Array;
  normals: Float32Array | null;
}

/**
 * The VU1's own lighting, with the map's own numbers in it.
 *
 * `socom2_dispatch_0x1b50.cpp` (SEMANTICS calls it NAT) documents command `0x18` -> `0x1440` as:
 *
 * ```
 *   light[0..2] = vf9/vf10/vf11 * params.y,  light[3] = vf12 * params.z
 *   normal      = max(vf5 * record0.w + vf6 * record1.z + vf7 * record1.w, 0) on xyz
 *   lit         = light[0]*normal.x + light[1]*normal.y + light[2]*normal.z + light[3]
 *   staging + 1 = record2 * lit
 * ```
 *
 * So the drawn vertex colour is the **material** colour on disc (`record2`, what `MeshData.colors`
 * carries) times a `lit` built from the vertex normal. `record0.w`, `record1.z` and `record1.w` are
 * the three lanes SEMANTICS section 4 calls the normal, which `mesh` decodes and `loadMap` rotates
 * into world space.
 *
 * **The matrix is not the identity, and the lights are not axis lights.** Read against a live VU1
 * capture, `vf5`-`vf7` hold three unit light directions as their *columns*, not their rows: the VU
 * computes `normal.x = vf5.x*n.x + vf6.x*n.y + vf7.x*n.z`, which is `dot(column0, n)`. So
 *
 * ```
 *   lit = C0*max(dot(D0,N),0) + C1*max(dot(D1,N),0) + C2*max(dot(D2,N),0) + ambient
 * ```
 *
 * -- three directional lights with arbitrary world directions plus an ambient. And the numbers are
 * **on the disc after all**: `MP*.ZED` carries a 112-byte `GlobalLighting` record on all 34 maps, and
 * `-normalize(dir[k])` with the colours verbatim reproduces the captured VU1 quadwords 16 to 23
 * bit-exactly, sign of zero included. `@s2u/scene`'s `parseGlobalLighting` reads it; see the spec,
 * "The lighting values are on the disc".
 *
 * `params.y`/`params.z` are only ever 0.0 or 1.0 across 900 captured dumps -- a lighting enable, not a
 * scale -- so there is no hardware gain. The two sliders that remain are trims for looking at a dark
 * map, and both are neutral by default.
 */
export interface Lighting {
  /** The map's own rig, or null before a map is loaded (then only the trims light anything). */
  rig: GlobalLighting | null;
  /** A trim added to the map's ambient. 0 is the hardware. */
  ambient: number;
  /** An exposure on the whole result. 1 is the bare model; see `LIT_SCALE` for why the default is 8. */
  gain: number;
}

/**
 * **The one number here that is not measured: the exposure.**
 *
 * The rig is exact -- `-normalize(dir[k])` and the colours verbatim reproduce the captured VU1
 * quadwords bit for bit -- and its *shape* is confirmed against the PS2 capture of Frostfire. That
 * capture is what the old sliders were fitted to, and the fit could never make a vertical wall
 * brighter than the ground, which is what the capture shows (ground 67.8, right wall 95.9). The rig
 * does it on the first try: at the sweep pose, ours reads ground 7.0 and wall 12.1, a ratio of 1.73
 * against the capture's 1.41, where the fitted sliders gave 0.29.
 *
 * What it does not give is the magnitude. Everything is a factor of about 9 too dark. Rendered at
 * this exposure the same two patches read 54.9 and 96.7 against the capture's 67.8 and 95.9 -- the
 * wall within 1 percent, the ground 19 percent low -- and the two surfaces bracket the true figure
 * between 8 and 10. Eight is taken because it is a power of two, which is what a missing shift looks
 * like, and because it is the only candidate with a mechanical explanation rather than a fitted one.
 *
 * Where the shift might be is **not** established. The obvious suspect, the normal's `ITOF15`, is
 * ruled out: SEMANTICS section 4 cites it to the microcode and 15,054 of 15,071 Frostfire normals
 * come out unit length at `/32768`. Set the slider to 1.00 to see the model with nothing added.
 */
export const LIT_SCALE = 8;

/** No trim, and the exposure at the measured scale: what the viewer opens with. */
export const DEFAULT_LIGHTING: Lighting = { rig: null, ambient: 0, gain: LIT_SCALE };

/**
 * The rig a map with no `GlobalLighting` key falls back to: one white light from above and a little
 * ambient. Nothing on the disc reads this -- all 34 maps carry the key -- it exists so that a broken
 * archive draws something shaded rather than black.
 */
export const FALLBACK_RIG: GlobalLighting = {
  directions: [[0, 1, 0], [0, 0, 0], [0, 0, 0]],
  colours: [[0.7, 0.7, 0.7], [0, 0, 0], [0, 0, 0]],
  ambient: [0.3, 0.3, 0.3],
};

/**
 * `record2 * lit` for one part, into `out` (rgba, 4 floats a vertex).
 *
 * RGB is left unclamped: the GS clamps the product of texel and vertex, not the vertex, so a lit
 * colour above 1 legitimately overbrightens and the framebuffer is where it stops. Alpha is copied
 * through -- the VU takes the w lane from the staging quad rather than from `lit`, so lighting never
 * changes how transparent a surface is.
 */
export function applyLighting(part: Lightable, light: Lighting, out: Float32Array): void {
  const material = part.colors;
  const normals = part.normals;
  const count = material.length / 4;
  const rig = light.rig ?? FALLBACK_RIG;
  const { gain } = light;
  const ambient = light.ambient;

  // A merge can lose the normals (`mergeMeshes` drops them when a part has none). Without a normal
  // there is no direction to dot against, so the surface takes the ambient plus half of each light --
  // the mean of `max(dot(d, n), 0)` over a sphere is a half -- rather than a black hole.
  const flatR = rig.ambient[0] + ambient + rig.colours.reduce((s, c) => s + c[0] / 2, 0);
  const flatG = rig.ambient[1] + ambient + rig.colours.reduce((s, c) => s + c[1] / 2, 0);
  const flatB = rig.ambient[2] + ambient + rig.colours.reduce((s, c) => s + c[2] / 2, 0);

  for (let i = 0; i < count; i++) {
    let r = flatR, g = flatG, b = flatB;
    if (normals) {
      const nx = normals[i * 3]!, ny = normals[i * 3 + 1]!, nz = normals[i * 3 + 2]!;
      r = rig.ambient[0] + ambient; g = rig.ambient[1] + ambient; b = rig.ambient[2] + ambient;
      for (let k = 0; k < 3; k++) {
        const d = rig.directions[k]!;
        // `max(..., 0)`, exactly as the microcode clamps the transformed normal before it is used.
        const t = d[0] * nx + d[1] * ny + d[2] * nz;
        if (t <= 0) continue;
        const c = rig.colours[k]!;
        r += c[0] * t; g += c[1] * t; b += c[2] * t;
      }
    }
    out[i * 4] = material[i * 4]! * r * gain;
    out[i * 4 + 1] = material[i * 4 + 1]! * g * gain;
    out[i * 4 + 2] = material[i * 4 + 2]! * b * gain;
    out[i * 4 + 3] = material[i * 4 + 3]!;            // alpha is not lit
  }
}
