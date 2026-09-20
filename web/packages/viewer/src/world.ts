import {
  Box3, BufferAttribute, BufferGeometry, DataTexture, DoubleSide, Group, InstancedMesh, LinearFilter,
  Matrix4, Mesh, MeshBasicMaterial, NearestFilter, RGBAFormat, RepeatWrapping, SRGBColorSpace, Texture,
  Vector3,
} from 'three';
import type { Rgba } from '@s2u/gs';
import type { MeshData } from '@s2u/mesh';
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
  const materials: MeshBasicMaterial[] = [];
  const untextured: MeshBasicMaterial[] = [];
  let triangles = 0;
  const materialFor = (name: string | null): MeshBasicMaterial => {
    const rgba = name === null ? undefined : map.textures[name];
    let texture = name === null ? undefined : textures.get(name);
    if (!texture && name !== null && rgba) {
      texture = makeTexture(rgba, map.textureFlags[name]?.bilinear ?? true);
      textures.set(name, texture);
    }
    const material = new MeshBasicMaterial({
      map: texture ?? null,
      vertexColors: true,
      side: DoubleSide,                                   // the map's inward faces are walls too
      // A keyed texture is punched through rather than blended: sorting 37 blended draws by depth is a
      // problem M3 does not need, and the PS2 alpha test is what the game itself used.
      alphaTest: name !== null && (map.textureFlags[name]?.transparent ?? false) ? 0.5 : 0,
    });
    materials.push(material);
    if (!texture) untextured.push(material);
    return material;
  };

  for (const part of map.world) {
    const mesh = new Mesh(geometryOf(part), materialFor(part.textureName));
    mesh.name = part.textureName ?? 'untextured';
    mesh.frustumCulled = false;                           // one mesh spans the whole map; culling it hides it
    group.add(mesh);
    triangles += part.indices.length / 3;
  }

  for (const prop of map.props) {
    const count = prop.matrices.length / 16;
    for (const part of prop.parts) {
      const geometry = geometryOf(part);
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

  const box = new Box3().setFromObject(group);
  return {
    group,
    triangles,
    box,
    untextured: untextured.length,
    setWireframe: (on) => {
      for (const material of materials) material.wireframe = on;
    },
    setUntexturedHighlight: (on) => {
      for (const material of untextured) {
        material.color.setHex(on ? UNTEXTURED : 0xffffff);
        // Flat magenta, not magenta times the baked lighting: the point is to be unmistakable.
        material.vertexColors = !on;
        material.needsUpdate = true;
      }
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
    },
  };
}

/** The centre of a box, for framing a map whose spawns are not known. */
export function centre(box: Box3): [number, number, number] {
  const v = box.getCenter(new Vector3());
  return [v.x, v.y, v.z];
}

function geometryOf(part: MeshData): BufferGeometry {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(part.positions, 3));
  geometry.setAttribute('uv', new BufferAttribute(part.uvs, 2));
  geometry.setAttribute('color', new BufferAttribute(vertexColors(part.colors), 4, true));
  geometry.setIndex(new BufferAttribute(part.indices, 1));
  geometry.computeBoundingSphere();
  return geometry;
}

/**
 * The PS2 writes vertex colour with 128, not 255, as full brightness (the same convention `mesh` already
 * undid for alpha, SEMANTICS section 4). A normalised three.js byte attribute reads 128 as 0.5, so the
 * whole map would render at half light; doubling the three colour bytes puts it back, clamped because a
 * few vertices are written brighter than full on purpose.
 */
function vertexColors(colors: Uint8Array): Uint8Array {
  const out = new Uint8Array(colors.length);
  for (let i = 0; i < colors.length; i += 4) {
    out[i] = Math.min(255, colors[i]! * 2);
    out[i + 1] = Math.min(255, colors[i + 1]! * 2);
    out[i + 2] = Math.min(255, colors[i + 2]! * 2);
    out[i + 3] = colors[i + 3]!;                          // alpha is already 0..255
  }
  return out;
}

function makeTexture(rgba: Rgba, bilinear: boolean): DataTexture {
  const texture = new DataTexture(new Uint8Array(rgba.data.buffer, rgba.data.byteOffset, rgba.data.length), rgba.width, rgba.height, RGBAFormat);
  texture.flipY = FLIP_Y;
  texture.colorSpace = SRGBColorSpace;
  texture.magFilter = bilinear ? LinearFilter : NearestFilter;
  texture.minFilter = bilinear ? LinearFilter : NearestFilter;   // no mipmaps tonight: nothing generates them
  texture.wrapS = RepeatWrapping;
  texture.wrapT = RepeatWrapping;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}
