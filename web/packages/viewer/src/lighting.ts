/** Everything the lighting needs: the material colours and, if they survived, the normals. */
export interface Lightable {
  colors: Float32Array;
  normals: Float32Array | null;
}

/**
 * The VU1's own lighting, as the hand-translated dispatcher states it.
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
 * So the final vertex colour is the **material** colour on disc (`record2`, what `MeshData.colors`
 * carries, averaging 0.15 of full and never above 0.50) multiplied by a `lit` built from three axis
 * lights and an ambient, driven by the vertex
 * normal after a 3x3 transform and a componentwise clamp to zero. `record0.w`, `record1.z` and
 * `record1.w` are exactly the three lanes SEMANTICS §4 calls the normal, which `mesh` already decodes
 * and `loadMap` already rotates into world space — the viewer simply threw them away until now.
 *
 * **What is real and what is a stand-in.** The formula is real. The *values* — the normal/light
 * matrix in vf5-vf7 and the colour block in vf9-vf12 — are uploaded by the EE at VU1 entry 0
 * (SEMANTICS §9); they are game state, not map data, so they are nowhere on the disc for a viewer to
 * read. The matrix is taken as identity here, which makes `light[0..2]` the +x, +y and +z axis
 * lights, and the four colours are the sliders. That is the same shape as the hardware, with the
 * numbers left to the eye until someone extracts the EE's own.
 */
export interface Lighting {
  /** `light[3]`: reaches every surface, whichever way it faces. */
  ambient: number;
  /** `light[0..2]`: the +x, +y and +z axis lights. A face pointing -y takes nothing from `y`. */
  x: number;
  y: number;
  z: number;
  /** An exposure on the whole result, since the EE's `params.y`/`params.z` scales are unknown too. */
  gain: number;
}

export const DEFAULT_LIGHTING: Lighting = { ambient: 0.55, x: 0.35, y: 1, z: 0.35, gain: 2 };

/**
 * `record2 * lit` for one part, into `out` (rgba, 4 floats a vertex).
 *
 * RGB is left unclamped: the GS clamps the product of texel and vertex, not the vertex, so a lit
 * colour above 1 legitimately overbrightens and the framebuffer is where it stops. Alpha is copied
 * through — the VU takes the w lane from the staging quad rather than from `lit`, so lighting never
 * changes how transparent a surface is.
 */
export function applyLighting(part: Lightable, light: Lighting, out: Float32Array): void {
  const material = part.colors;
  const normals = part.normals;
  const count = material.length / 4;
  const { ambient, x, y, z, gain } = light;

  // A merge can lose the normals (`mergeMeshes` drops them when a part has none). Without a normal
  // there is no axis term to pick, so the surface takes the ambient plus the mean of the three --
  // the average a normal would collect, rather than a black hole.
  const flat = (ambient + (x + y + z) / 3) * gain;

  for (let i = 0; i < count; i++) {
    let lit = flat;
    if (normals) {
      const nx = normals[i * 3]!, ny = normals[i * 3 + 1]!, nz = normals[i * 3 + 2]!;
      // `max(..., 0)` componentwise, exactly as the microcode clamps the transformed normal.
      lit = (ambient
        + (nx > 0 ? nx * x : 0)
        + (ny > 0 ? ny * y : 0)
        + (nz > 0 ? nz * z : 0)) * gain;
    }
    out[i * 4] = material[i * 4]! * lit;
    out[i * 4 + 1] = material[i * 4 + 1]! * lit;
    out[i * 4 + 2] = material[i * 4 + 2]! * lit;
    out[i * 4 + 3] = material[i * 4 + 3]!;            // alpha is not lit
  }
}
