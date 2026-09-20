import {
  Box3, BufferAttribute, BufferGeometry, DataTexture, DoubleSide, Group, InstancedMesh, LinearFilter,
  LineBasicMaterial, LineSegments, Matrix4, Mesh, MeshBasicMaterial, NearestFilter, NoColorSpace,
  RGBAFormat, RepeatWrapping,
  SRGBColorSpace, Texture,
  Vector3,
} from 'three';
import type { Rgba } from '@s2u/gs';
import type { MeshData } from '@s2u/mesh';
import { applyLighting, DEFAULT_LIGHTING, type Lightable, type Lighting } from './lighting';
import type { LoadedMap } from './loadMap';

/**
 * `gs` decodes a texture's rows bottom-up, which is also what GL calls V = 0, so the data goes to the GPU
 * as it comes out of the decoder and the UVs go up unchanged. `DataTexture` defaults to this; the constant
 * is here so the one thing to change, if a screenshot ever comes out mirrored top to bottom, is visible.
 */
const FLIP_Y = false;

/** The colour an untextured mesh takes when the highlight is on: nothing in the game is this. */
const UNTEXTURED = 0xff00ff;

/** A drawn map: the placed group, what it cost, and the extent the camera can frame. */
export interface WorldView {
  group: Group;
  triangles: number;
  box: Box3;
  /** How many of the group's draws are drawing without a texture: the highlight's subject, counted. */
  untextured: number;
  /** Every material at once, for seeing the topology through the skin. */
  setWireframe(on: boolean): void;
  /**
   * Paints the meshes that are drawing without a texture magenta -- the ones whose name was not in the
   * map's `TXR` archive, and the ones whose packets cited no name at all. Both are invisible faults
   * otherwise: an untextured mesh in vertex colour alone looks like dim geometry, not like a diagnostic.
   */
  setUntexturedHighlight(on: boolean): void;
  /**
   * Whether the texture is multiplied by the vertex colour in the GS's space or in a linear one.
   *
   * The PS2 has no notion of linear light: in MODULATE it computes `(texel * vertex) >> 7` on the stored
   * 8-bit values and clamps, so a vertex written at half brightness halves the pixel you see. Treating
   * the texture as sRGB decodes it to linear first, and re-encoding afterwards turns that same half into
   * about 0.73 of the pixel -- every shaded surface renders far brighter than the artists set it, which
   * reads as flat and washed out. Off, the texel is taken at face value and the product goes to the
   * framebuffer unconverted, which is the hardware's own arithmetic.
   *
   * Defaults to **off**, the GS's own space, which is only safe now that the other half of the fix is in:
   * `mesh` hands colour over unclamped, so the overbright that lifts the sky and the light pools survives
   * to the fragment. With the vertex colour still clamped at full, as it was, this space crushed the
   * picture -- Frostfire's sky went black and its snow went grey. The pair only works as a pair.
   */
  setLinearLight(on: boolean): void;
  /**
   * Re-runs the VU's lighting over every vertex: `record2 * lit`, the material colour on disc times a
   * `lit` built from the vertex normal and four colours (see `./lighting`). Cheap enough to call from a
   * slider -- it is one pass over the vertex arrays, about a millisecond on the largest map.
   */
  setLighting(light: Lighting): void;
  dispose(): void;
}

/**
 * Builds the scene objects for one decoded map: one `Mesh` per texture for the world, whose vertices
 * `loadMap` has already placed, and one `InstancedMesh` per prop model-node -- a prop model is drawn in
 * up to 26 places, so it is uploaded once and instanced by the matrices `scene` produced.
 *
 * `map.origin` is zero whenever the scene graph could be read; it is only non-zero for the fallback,
 * where the whole group still shifts together the way it did before per-node placement.
 */
export function buildWorld(map: LoadedMap): WorldView {
  const group = new Group();
  group.name = `${map.archive} worldmodel`;
  group.position.set(map.origin[0], map.origin[1], map.origin[2]);

  const textures = new Map<string, Texture>();
  let linearLight = false;
  let lighting = DEFAULT_LIGHTING;
  let highlighting = false;
  let lineMaterial: LineBasicMaterial | null = null;
  // Every drawn part beside the buffer its lit colours go into, so a slider can rewrite them in place.
  const lit: { part: Lightable; attribute: BufferAttribute }[] = [];
  const materials: MeshBasicMaterial[] = [];
  const untextured: MeshBasicMaterial[] = [];
  let triangles = 0;
  const materialFor = (name: string | null): MeshBasicMaterial => {
    const rgba = name === null ? undefined : map.textures[name];
    let texture = name === null ? undefined : textures.get(name);
    if (!texture && name !== null && rgba) {
      texture = makeTexture(rgba, map.textureFlags[name]?.bilinear ?? true, linearLight);
      textures.set(name, texture);
    }
    const flags = name === null ? undefined : map.textureFlags[name];
    // Every texture's GS bind packet asks for `ALPHA_1 = 0x44` -- `(Cs - Cd) * As + Cd`, source-alpha
    // blending -- with the alpha test off. A texture whose alpha is a *ramp* (a corona, a glow) has to
    // be blended or it draws as a flat disc on an opaque black square; one whose alpha is a *switch*
    // (a cutout leaf, a grating) is punched through instead, which needs no depth sorting and is what
    // the game's own draw order relied on.
    const graded = flags?.graded ?? false;
    const material = new MeshBasicMaterial({
      map: texture ?? null,
      vertexColors: true,
      side: DoubleSide,                                   // the map's inward faces are walls too
      transparent: graded,
      // Blended draws do not write depth, or the ones drawn first would cut holes in the ones behind.
      depthWrite: !graded,
      alphaTest: graded ? 0.004 : (flags?.transparent ?? false) ? 0.5 : 0,
    });
    materials.push(material);
    if (!texture) untextured.push(material);
    return material;
  };

  for (const part of map.world) {
    const mesh = new Mesh(geometryOf(part, lighting, lit), materialFor(part.textureName));
    mesh.name = part.textureName ?? 'untextured';
    mesh.frustumCulled = false;                           // one mesh spans the whole map; culling it hides it
    group.add(mesh);
    triangles += part.indices.length / 3;
  }

  for (const prop of map.props) {
    const count = prop.matrices.length / 16;
    for (const part of prop.parts) {
      const geometry = geometryOf(part, lighting, lit);
      const material = materialFor(part.textureName);
      if (count === 1) {
        const mesh = new Mesh(geometry, material);
        mesh.name = prop.modelName;
        mesh.applyMatrix4(new Matrix4().fromArray(prop.matrices, 0));
        group.add(mesh);
      } else {
        const mesh = new InstancedMesh(geometry, material, count);
        mesh.name = prop.modelName;
        for (let i = 0; i < count; i++) mesh.setMatrixAt(i, new Matrix4().fromArray(prop.matrices, i * 16));
        mesh.instanceMatrix.needsUpdate = true;
        group.add(mesh);
      }
      triangles += (part.indices.length / 3) * count;
    }
  }

  // The GS LINE_STRIP geometry (SEMANTICS section 12): power lines, lamp brackets, guy ropes, light
  // filaments. The hardware draws these one pixel wide at any distance, which is what a plain
  // `LineSegments` does too, so no width has to be invented.
  if (map.lines) {
    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(map.lines.positions, 3));
    const colors = new Float32Array(map.lines.colors.length);
    applyLighting(map.lines, lighting, colors);
    const attribute = new BufferAttribute(colors, 4);
    geometry.setAttribute('color', attribute);
    lit.push({ part: map.lines, attribute });
    const material = new LineBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false });
    lineMaterial = material;
    const segments = new LineSegments(geometry, material);
    segments.name = 'line strips';
    segments.frustumCulled = false;
    group.add(segments);
  }

  const box = new Box3().setFromObject(group);
  return {
    group,
    triangles,
    box,
    untextured: untextured.length,
    setWireframe: (on) => {
      for (const material of materials) material.wireframe = on;
      // A line has no faces to show through, so it simply steps aside while the topology is on view.
      if (lineMaterial) lineMaterial.visible = !on;
    },
    setUntexturedHighlight: (on) => {
      highlighting = on;
      for (const material of untextured) {
        material.color.setHex(on ? UNTEXTURED : 0xffffff);
        // Flat magenta, not magenta times the baked lighting: the point is to be unmistakable.
        material.vertexColors = !on;
        material.needsUpdate = true;
      }
    },
    setLighting: (next) => {
      lighting = next;
      for (const { part, attribute } of lit) {
        applyLighting(part, lighting, attribute.array as Float32Array);
        attribute.needsUpdate = true;
      }
    },
    setLinearLight: (on) => {
      if (on === linearLight) return;
      linearLight = on;
      for (const texture of textures.values()) {
        texture.colorSpace = on ? SRGBColorSpace : NoColorSpace;
        texture.needsUpdate = true;
      }
      for (const material of materials) material.needsUpdate = true;
    },
    dispose: () => {
      for (const child of group.children) {
        if (!(child instanceof Mesh)) continue;               // an InstancedMesh is one too
        child.geometry.dispose();
        const material = child.material;
        if (!Array.isArray(material)) material.dispose();
        if (child instanceof InstancedMesh) child.dispose();
      }
      for (const texture of textures.values()) texture.dispose();
      lineMaterial?.dispose();
    },
  };
}

/** The centre of a box, for framing a map whose spawns are not known. */
export function centre(box: Box3): [number, number, number] {
  const v = box.getCenter(new Vector3());
  return [v.x, v.y, v.z];
}

function geometryOf(
  part: MeshData,
  light: Lighting,
  lit: { part: Lightable; attribute: BufferAttribute }[],
): BufferGeometry {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(part.positions, 3));
  geometry.setAttribute('uv', new BufferAttribute(part.uvs, 2));
  // The attribute is the *lit* colour, not the material colour on disc: `record2 * lit`, computed here
  // the way the VU computes it (see `./lighting`). Float rather than a normalised byte, because a lit
  // colour goes above 1 and the GS clamps the product at the framebuffer, not the vertex.
  const colors = new Float32Array(part.colors.length);
  applyLighting(part, light, colors);
  const attribute = new BufferAttribute(colors, 4);
  geometry.setAttribute('color', attribute);
  lit.push({ part, attribute });
  geometry.setIndex(new BufferAttribute(part.indices, 1));
  geometry.computeBoundingSphere();
  return geometry;
}

function makeTexture(rgba: Rgba, bilinear: boolean, linearLight: boolean): DataTexture {
  const texture = new DataTexture(new Uint8Array(rgba.data.buffer, rgba.data.byteOffset, rgba.data.length), rgba.width, rgba.height, RGBAFormat);
  texture.flipY = FLIP_Y;
  // NoColorSpace is the GS's own reading: the stored byte *is* the value, and the modulate happens on it.
  texture.colorSpace = linearLight ? SRGBColorSpace : NoColorSpace;
  texture.magFilter = bilinear ? LinearFilter : NearestFilter;
  texture.minFilter = bilinear ? LinearFilter : NearestFilter;   // no mipmaps tonight: nothing generates them
  texture.wrapS = RepeatWrapping;
  texture.wrapT = RepeatWrapping;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}
