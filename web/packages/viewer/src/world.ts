import {
  Box3, BufferAttribute, BufferGeometry, DataTexture, DoubleSide, Group, LinearFilter, Mesh,
  MeshBasicMaterial, NearestFilter, RGBAFormat, RepeatWrapping, SRGBColorSpace, Texture, Vector3,
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

/** A drawn map: the placed group, what it cost, and the extent the camera can frame. */
export interface WorldView {
  group: Group;
  triangles: number;
  box: Box3;
  dispose(): void;
}

/**
 * Builds the scene objects for one decoded map. One `Mesh` per texture, placed as a whole by the map's
 * world origin -- geometry stays in model space, as `mesh` hands it over.
 */
export function buildWorld(map: LoadedMap): WorldView {
  const group = new Group();
  group.name = `${map.archive} worldmodel`;
  group.position.set(map.origin[0], map.origin[1], map.origin[2]);

  const textures = new Map<string, Texture>();
  let triangles = 0;
  for (const part of map.world) {
    const name = part.textureName;
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
    const mesh = new Mesh(geometryOf(part), material);
    mesh.name = name ?? 'untextured';
    mesh.frustumCulled = false;                           // one mesh spans the whole map; culling it hides it
    group.add(mesh);
    triangles += part.indices.length / 3;
  }

  const box = new Box3().setFromObject(group);
  return {
    group,
    triangles,
    box,
    dispose: () => {
      for (const child of group.children) {
        if (!(child instanceof Mesh)) continue;
        child.geometry.dispose();
        const material = child.material;
        if (!Array.isArray(material)) material.dispose();
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
