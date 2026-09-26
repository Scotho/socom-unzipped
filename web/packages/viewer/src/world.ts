import {
  Box3, BufferAttribute, BufferGeometry, ClampToEdgeWrapping, CustomBlending, DataTexture, DoubleSide, DstColorFactor,
  FrontSide, Group, type Object3D, InstancedMesh, LinearFilter, LinearMipmapLinearFilter, LineSegments, Matrix4, Mesh,
  NearestFilter, NoBlending, NoColorSpace, OneFactor, OneMinusSrcAlphaFactor, RGBAFormat, RepeatWrapping, SrcAlphaFactor,
  SRGBColorSpace, Texture, Vector3, ZeroFactor,
} from 'three';
import type { Camera } from 'three';
import { LineBasicNodeMaterial, MeshBasicNodeMaterial, type Node } from 'three/webgpu';
import { materialReference, uniform, vec4, vertexColor } from 'three/tsl';
import { drawState, materialSpec, type Factor, type MaterialSpec, type TextureFlags } from './materialSpec';
import type { Rgba } from '@s2u/gs';
import type { MeshData } from '@s2u/mesh';
import { applyLighting, brightenOf, DEFAULT_LIGHTING, type Lightable, type Lighting } from './lighting';
import type { LoadedMap, LoadedMesh } from './loadMap';

/**
 * `gs` decodes a texture's rows bottom-up, which is also what GL calls V = 0, so the data goes to the GPU
 * as it comes out of the decoder and the UVs go up unchanged. `DataTexture` defaults to this; the constant
 * is here so the one thing to change, if a screenshot ever comes out mirrored top to bottom, is visible.
 */
const FLIP_Y = false;

/** A drawn map: the placed group, what it cost, and the extent the camera can frame. */
export interface WorldView {
  /**
   * The group, **empty** when `buildWorld` returns. Every drawn object is waiting in one of the two
   * reveal queues below, because the expensive part of showing a map is not building it -- it is the
   * first frame that draws it, when three uploads each texture and geometry and compiles each program.
   */
  group: Group;
  /** The world's own meshes, one task each. What the first paint of a new map waits for. */
  revealWorld: (() => void)[];
  /** The props, the flares and the line strips. These arrive behind the world, over further frames. */
  revealProps: (() => void)[];
  triangles: number;
  /** The extent of everything queued, accumulated as it was built rather than read off the group. */
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
   * Defaults to **off**, the GS's own space.
   */
  setLinearLight(on: boolean): void;
  /**
   * Whether a texture whose alpha is a *ramp* is blended with the equation its bind packet asks for
   * rather than punched out at a threshold (`./materialSpec`). On by default; off restores the cutout,
   * which sorts perfectly and looks wrong.
   */
  setBlendGraded(on: boolean): void;
  /**
   * Whether every draw goes out in the order the engine walked the scene graph, writing depth as it
   * goes -- the console's own state -- or blended draws are handed to three to sort back to front by
   * object centre with no depth written under them (`drawState` in `./materialSpec`). On by default.
   */
  setDiscOrder(on: boolean): void;
  /**
   * Whether the GS `LINE_STRIP` geometry is drawn (SEMANTICS section 12). On by default: a strip is
   * drawn one pixel wide with the packet's texture running along it, which is what the hardware did.
   */
  setLineStrips(on: boolean): void;
  /**
   * Turns every flare quad to face the camera. Called once a frame, before the render.
   *
   * A flare on disc is a single quad on a single plane -- `lightcage`'s `lightrays.tif` node is 4
   * vertices and 2 triangles, normal (0, 0.96, -0.24) -- so a fixed quad that nearly faces the sky is
   * edge-on from a standing player. The hardware turns them; so does this.
   */
  faceCamera(camera: Camera): void;
  /** Whether the flares are turned at all, for seeing the pose the disc actually holds. */
  setBillboards(on: boolean): void;
  /** Where the flares are, in world space -- for aiming a camera at one. */
  flarePositions(): [number, number, number][];
  /** Each line-strip group's texture and world-space extent -- for aiming a camera at a rope. */
  lineGroups(): { texture: string | null; min: [number, number, number]; max: [number, number, number] }[];
  /**
   * The lighting. The brighten is a uniform on every material and costs nothing to move; a change of
   * rig, or of whether the rig is applied everywhere, re-runs the VU's lighting over every vertex
   * (`record2 * lit`, see `./lighting`), about a millisecond on the largest map.
   */
  setLighting(light: Lighting): void;
  dispose(): void;
}

/** The two material kinds the world is drawn with, which share every property this file sets. */
type Basic = MeshBasicNodeMaterial | LineBasicNodeMaterial;
/** A TSL node that yields a colour: what `colorNode` takes. */
type ColorNode = NonNullable<MeshBasicNodeMaterial['colorNode']>;

/** A material together with what it was built from, so a switch can rebuild it from the disc's state. */
interface Built {
  material: Basic;
  flags: TextureFlags | undefined;
  fog: boolean;
  textured: boolean;
}

const FACTOR = {
  zero: ZeroFactor, one: OneFactor, srcAlpha: SrcAlphaFactor, oneMinusSrcAlpha: OneMinusSrcAlphaFactor, dstColor: DstColorFactor,
} as const satisfies Record<Factor, number>;

/**
 * Builds the scene objects for one decoded map: one `Mesh` per texture run for the world, whose vertices
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
  // The map's own rig, from its `GlobalLighting` record; the panel's trims arrive with `setLighting`.
  let lighting: Lighting = { ...DEFAULT_LIGHTING, rig: map.lightRig };
  let lastRig = lighting.rig;
  let lastEverywhere = lighting.rigEverywhere;
  const lineObjects: LineSegments[] = [];
  const billboards: Mesh[] = [];
  let billboardsOn = true;
  let blendGraded = false;
  let discOrder = false;
  let highlight = false;
  let lineStripsOn = true;
  const built: Built[] = [];
  /** Every drawn object beside its place in the scene walk, for `setDiscOrder`. */
  const ordered: { object: Object3D; order: number }[] = [];
  // Every drawn part beside the buffer its lit colours go into, so a rig change can rewrite them in place.
  const lit: { part: Lightable; attribute: BufferAttribute }[] = [];
  /** How many drawn objects have no texture: the number the status line reports. */
  let untexturedDraws = 0;
  let triangles = 0;

  /**
   * The shading, as the GS does it, in four node graphs shared by every material (a shared graph is one
   * compiled program, not one per texture):
   *
   * - **MODULATE, then clamp, then brighten.** `(texel * vertex) >> 7`, the product clamped to 255 by
   *   `COLCLAMP` before the fog is mixed in -- so the clamp is here, ahead of the fog three applies to
   *   the output, and the post-process's `1 + FIX/128` comes after it as a uniform. Alpha is the same
   *   product, clamped, and is not brightened.
   * - The untextured variant of the same: the vertex colour alone.
   * - **The destination brighten**, `(Cd - 0) * As + Cd`: the source colour is never read, so the shader
   *   emits `As` in every channel for the `Cs * Cd + Cd` blend to multiply with (`./materialSpec`).
   * - **Magenta**, flat, for the untextured highlight.
   */
  const brighten = uniform(brightenOf(lighting));
  // The typings do not know a material reference to a texture is a vec4, which is what the sampler yields.
  const texel = materialReference('map', 'texture') as unknown as Node<'vec4'>;
  const modulated = vec4(texel.mul(vertexColor())).clamp(0, 1);
  const plain = vec4(vertexColor()).clamp(0, 1);
  const SHADED: ColorNode = vec4(modulated.rgb.mul(brighten), modulated.a);
  const SHADED_PLAIN: ColorNode = vec4(plain.rgb.mul(brighten), plain.a);
  const CARRIER: ColorNode = vec4(modulated.a, modulated.a, modulated.a, modulated.a);
  const CARRIER_PLAIN: ColorNode = vec4(plain.a, plain.a, plain.a, plain.a);
  /** The colour an untextured mesh takes when the highlight is on: nothing in the game is this. */
  const MAGENTA: ColorNode = vec4(1, 0, 1, 1);

  /** Puts a spec on a material: the shading graph, the blend, the test, the depth write, the cull and the fog. */
  const apply = (b: Built): void => {
    const spec = materialSpec(b.flags, b.fog, blendGraded);
    const state = drawState(spec, discOrder);
    const { material } = b;
    const carrier = spec.blend === 'destination';
    material.colorNode = highlight && !b.textured ? MAGENTA
      : carrier ? (b.textured ? CARRIER : CARRIER_PLAIN)
      : (b.textured ? SHADED : SHADED_PLAIN);
    material.transparent = state.transparent;
    material.depthWrite = state.depthWrite;
    if (state.factors) {
      material.blending = CustomBlending;
      material.blendSrc = FACTOR[state.factors.src];
      material.blendDst = FACTOR[state.factors.dst];
      material.blendSrcAlpha = null;
      material.blendDstAlpha = null;
    } else {
      material.blending = NoBlending;
    }
    material.alphaTest = spec.alphaTest;
    material.side = spec.cull ? FrontSide : DoubleSide;
    // A destination brighten reads only `As`, which the GS does not fog; fogging the carrier would fog it.
    material.fog = spec.fog && !carrier;
    material.needsUpdate = true;
  };

  /**
   * One material per (texture, fog, kind). The texture's own state block -- blend, alpha test, wrap,
   * filtering (`./materialSpec`) -- is the same for every draw of it; what varies per packet is the
   * `PRIM.FGE` fog bit, so a sky texture drawn fogged in one chunk and clear in another gets two.
   */
  const materialCache = new Map<string, Basic>();
  const materialFor = (name: string | null, fog: boolean, kind: 'mesh' | 'line'): Basic => {
    const cacheKey = `${kind}|${name ?? ''}|${fog ? 1 : 0}`;
    const cached = materialCache.get(cacheKey);
    if (cached) return cached;
    const rgba = name === null ? undefined : map.textures[name];
    const flags = name === null ? undefined : map.textureFlags[name];
    const spec = materialSpec(flags, fog, blendGraded);
    let texture = name === null ? undefined : textures.get(name);
    if (!texture && name !== null && rgba) {
      texture = makeTexture(rgba, spec, linearLight);
      textures.set(name, texture);
    }
    // Backface culling, and why it is not simply on or off.
    //
    // SEMANTICS section 6: the right-handed cross product of a triangle's edges in index order *is*
    // the stored face normal, on all 8,764 non-degenerate Frostfire triangles, and VU1's cull handler
    // (`0x06`, research/13 section 4.2) keeps a triangle when the eye is on that side. So
    // counter-clockwise is front, which is three.js's default, and `FrontSide` is what the hardware
    // does -- for the objects whose command list contains the cull. Which ones those are is not on the
    // disc: the command list is built by the EE per draw, and a no-cull variant of the world-object
    // program exists (research/12, program 11).
    //
    // The data settles it anyway. Crossroads' awning is *two coincident single-sided sheets* -- the
    // same five quads twice, opposite normals, the top baked at mean colour 0.6 and the underside at
    // 0.2 -- which is a thing an artist only draws when the hardware culls. Drawn double-sided the two
    // sheets z-fight and the canvas comes out as a red-and-green plaid (spec section 9, 2026-09-20).
    // Cutout sheets are the opposite case: one leaf card, one frond, one chain-link panel, meant to be
    // seen from behind, and culling those empties the canopies of Bitter Jungle.
    //
    // So: cull where the texture is solid, keep both faces where it is not (`spec.cull`). That is the
    // split the models themselves draw, and it is the one fact about a draw the state block does not hold.
    const material: Basic = kind === 'mesh' ? new MeshBasicNodeMaterial() : new LineBasicNodeMaterial();
    material.map = texture ?? null;
    material.vertexColors = false;                     // the shading graph reads the attribute itself
    const entry: Built = { material, flags, fog, textured: !!texture };
    apply(entry);
    built.push(entry);
    materialCache.set(cacheKey, material);
    return material;
  };

  /**
   * Building an object is cheap; *drawing it the first time* is not, because that is when three uploads
   * its texture and geometry and compiles its program. So nothing is added to the group here. Each
   * object becomes a one-line task, and `main.ts` runs those across frames (`./scheduler`), which turns
   * one 1,700 ms frame into a few dozen short ones. The world's tasks come first and are what the first
   * paint waits for; the props follow behind it.
   */
  const revealWorld: (() => void)[] = [];
  const revealProps: (() => void)[] = [];
  const box = new Box3();
  /** Queues an object at its place in the walk, and grows the map's extent by it. */
  const later = (queue: (() => void)[], object: Object3D, order: number): void => {
    object.updateWorldMatrix(false, false);
    box.expandByObject(object);
    ordered.push({ object, order });
    object.renderOrder = discOrder ? order : 0;
    queue.push(() => group.add(object));
  };

  for (const part of map.world) {
    const mesh = new Mesh(geometryOf(part, lighting, lit), materialFor(part.textureName, part.fog, 'mesh'));
    mesh.name = part.textureName ?? 'untextured';
    if (!part.textureName) untexturedDraws++;
    mesh.frustumCulled = false;                           // one mesh spans the whole map; culling it hides it
    later(revealWorld, mesh, part.order);
    triangles += part.indices.length / 3;
  }

  for (const prop of map.props) {
    const count = prop.matrices.length / 16;
    // A world chunk's normals are rotated into world space by `loadMap` before they are lit; a prop's
    // are not, because the rotation lives in the placement matrix instead. Lighting them unrotated
    // would light a turned prop as though it faced the way it was modelled, so they are rotated here
    // by the first placement. A prop drawn in several placements that do not share a rotation is still
    // lit by the first one's: one `InstancedMesh` has one set of vertex colours, and splitting it into
    // a mesh per placement would cost 26 draws to fix a shading error of a few degrees.
    const rotation = new Matrix4().fromArray(prop.matrices, 0);
    for (const part of prop.parts) {
      const partFlags = part.textureName === null ? undefined : map.textureFlags[part.textureName];
      if (isBillboard(part, partFlags)) {
        // A lamp flare is one quad on one plane, and the hardware turns it to face the camera: left
        // where it was modelled it is edge-on from most of the map and a flat card from the rest. Each
        // placement becomes its own mesh, centred on the quad so a spin about that centre keeps it
        // where it belongs, and `faceCamera` turns them every frame.
        const flareMaterial = materialFor(part.textureName, part.fog, 'mesh');
        if (!part.textureName) untexturedDraws += count;
        for (let i = 0; i < count; i++) {
          const m = new Matrix4().fromArray(prop.matrices, i * 16);
          const { geometry: flat, centre: at } = centredQuad(rotateNormals(part, m), lighting, lit);
          const mesh = new Mesh(flat, flareMaterial);
          mesh.name = `${prop.modelName} (flare)`;
          mesh.position.copy(at.applyMatrix4(m));
          billboards.push(mesh);
          later(revealProps, mesh, part.order);
        }
        triangles += (part.indices.length / 3) * count;
        continue;
      }
      const geometry = geometryOf(rotateNormals(part, rotation), lighting, lit);
      const material = materialFor(part.textureName, part.fog, 'mesh');
      if (!part.textureName) untexturedDraws++;
      if (count === 1) {
        const mesh = new Mesh(geometry, material);
        mesh.name = prop.modelName;
        mesh.applyMatrix4(new Matrix4().fromArray(prop.matrices, 0));
        later(revealProps, mesh, part.order);
      } else {
        const mesh = new InstancedMesh(geometry, material, count);
        mesh.name = prop.modelName;
        for (let i = 0; i < count; i++) mesh.setMatrixAt(i, new Matrix4().fromArray(prop.matrices, i * 16));
        mesh.instanceMatrix.needsUpdate = true;
        later(revealProps, mesh, part.order);
      }
      triangles += (part.indices.length / 3) * count;
    }
  }

  // The GS LINE_STRIP geometry (SEMANTICS section 12): power lines, lamp brackets, guy ropes, light
  // filaments. The hardware draws these one pixel wide at any distance, textured (`TME`) along the
  // strip with uvs that run well outside 0..1, gouraud, fogged and blended -- `PRIM = IIP|TME|FGE|ABE`
  // on all 194 packets. A `LineSegments` per (texture, fog) with the same shading graph the meshes use
  // draws exactly that: the texture repeats along the rope, and the vertex colour shades it.
  for (const strip of map.lines ?? []) {
    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(strip.positions, 3));
    geometry.setAttribute('uv', new BufferAttribute(strip.uvs, 2));
    const colors = new Float32Array(strip.colors.length);
    const part: Lightable = { colors: strip.colors, normals: strip.normals, lit: false };
    applyLighting(part, lighting, colors);
    const attribute = new BufferAttribute(colors, 4);
    geometry.setAttribute('color', attribute);
    lit.push({ part, attribute });
    const segments = new LineSegments(geometry, materialFor(strip.textureName, strip.fog, 'line'));
    segments.name = `line strips (${strip.textureName ?? 'untextured'})`;
    segments.frustumCulled = false;
    if (!strip.textureName) untexturedDraws++;
    lineObjects.push(segments);
    later(revealProps, segments, strip.order);
  }

  return {
    group,
    revealWorld,
    revealProps,
    triangles,
    box,
    untextured: untexturedDraws,
    setWireframe: (on) => {
      // `needsUpdate` as well as the flag: three's WebGPU renderer builds a geometry's wireframe index
      // the first time a render object is refreshed in full, and a bare flag change is not a refresh.
      // Without it the index is never uploaded, every wireframe draw goes out with no index type, and
      // the frame is the clear colour and nothing else until the page is reloaded.
      for (const { material } of built) {
        if (material instanceof MeshBasicNodeMaterial) { material.wireframe = on; material.needsUpdate = true; }
      }
      // A line has no faces to show through, so it simply steps aside while the topology is on view.
      for (const line of lineObjects) line.visible = !on && lineStripsOn;
    },
    setUntexturedHighlight: (on) => {
      if (on === highlight) return;
      highlight = on;
      for (const b of built) if (!b.textured) apply(b);
    },
    setLighting: (next) => {
      brighten.value = brightenOf(next);
      const rigChanged = next.rig !== lastRig || next.rigEverywhere !== lastEverywhere;
      lighting = next;
      lastRig = next.rig;
      lastEverywhere = next.rigEverywhere;
      if (!rigChanged) return;
      for (const { part, attribute } of lit) {
        applyLighting(part, lighting, attribute.array as Float32Array);
        attribute.needsUpdate = true;
      }
    },
    faceCamera: (camera) => {
      if (!billboardsOn) return;
      for (const mesh of billboards) mesh.quaternion.copy(camera.quaternion);
    },
    flarePositions: () => billboards.map((m) => [m.position.x, m.position.y, m.position.z]),
    lineGroups: () => lineObjects.map((line) => {
      const b = new Box3().setFromBufferAttribute(line.geometry.getAttribute('position') as BufferAttribute);
      return { texture: line.name, min: [b.min.x, b.min.y, b.min.z], max: [b.max.x, b.max.y, b.max.z] };
    }),
    setBillboards: (on) => {
      billboardsOn = on;
      if (!on) for (const mesh of billboards) mesh.quaternion.identity();   // back to the pose on disc
    },
    setLineStrips: (on) => {
      lineStripsOn = on;
      for (const line of lineObjects) line.visible = on;
    },
    setBlendGraded: (on) => {
      if (on === blendGraded) return;
      blendGraded = on;
      for (const b of built) apply(b);
    },
    setDiscOrder: (on) => {
      if (on === discOrder) return;
      discOrder = on;
      for (const b of built) apply(b);
      for (const { object, order } of ordered) object.renderOrder = on ? order : 0;
    },
    setLinearLight: (on) => {
      if (on === linearLight) return;
      linearLight = on;
      for (const texture of textures.values()) {
        texture.colorSpace = on ? SRGBColorSpace : NoColorSpace;
        texture.needsUpdate = true;
      }
      for (const { material } of built) material.needsUpdate = true;
    },
    dispose: () => {
      for (const child of group.children) {
        if (!(child instanceof Mesh) && !(child instanceof LineSegments)) continue;   // an InstancedMesh is a Mesh too
        child.geometry.dispose();
        if (child instanceof InstancedMesh) child.dispose();
      }
      for (const { material } of built) material.dispose();
      for (const texture of textures.values()) texture.dispose();
    },
  };
}

/**
 * The part with its normals turned by a placement's 3x3, so the lighting sees where it really faces.
 *
 * Renormalised afterwards: a placement matrix is not always a pure rotation. Clutter carries a uniform
 * scale -- Desert Glory's rocks come through at about 0.93 -- and a scaled normal would dim every
 * surface of that prop by the same factor, which reads as the prop being in shadow rather than smaller.
 * A zero normal (SEMANTICS section 4 allows them, 16 of Frostfire's are exactly zero) stays zero.
 */
function rotateNormals(part: LoadedMesh, m: Matrix4): LoadedMesh {
  if (!part.normals) return part;
  const e = m.elements;                                 // column-major, as three stores it
  const out = new Float32Array(part.normals.length);
  for (let i = 0; i < out.length; i += 3) {
    const [x, y, z] = [part.normals[i]!, part.normals[i + 1]!, part.normals[i + 2]!];
    const nx = x * e[0]! + y * e[4]! + z * e[8]!;
    const ny = x * e[1]! + y * e[5]! + z * e[9]!;
    const nz = x * e[2]! + y * e[6]! + z * e[10]!;
    const len = Math.hypot(nx, ny, nz);
    const k = len > 1e-6 ? 1 / len : 0;
    out[i] = nx * k;
    out[i + 1] = ny * k;
    out[i + 2] = nz * k;
  }
  return { ...part, normals: out };
}

/**
 * Whether a part is a flare: one quad, one plane, and a texture whose alpha is a ramp rather than a
 * switch. The three together separate a lamp's glow from a window or a ceiling panel, which are also
 * single quads but whose textures are not graded, and from a graded floor decal, which is not a quad.
 */
function isBillboard(part: MeshData, flags: TextureFlags | undefined): boolean {
  return (flags?.graded ?? false)
    && part.positions.length === 4 * 3
    && part.indices.length === 2 * 3;
}

/** A quad moved so its centre is the origin, with that centre, so a mesh can be spun about it. */
function centredQuad(
  part: LoadedMesh,
  light: Lighting,
  lit: { part: Lightable; attribute: BufferAttribute }[],
): { geometry: BufferGeometry; centre: Vector3 } {
  const centre = new Vector3();
  for (let i = 0; i < part.positions.length; i += 3) {
    centre.x += part.positions[i]!; centre.y += part.positions[i + 1]!; centre.z += part.positions[i + 2]!;
  }
  centre.divideScalar(part.positions.length / 3);
  const positions = new Float32Array(part.positions.length);
  for (let i = 0; i < positions.length; i += 3) {
    positions[i] = part.positions[i]! - centre.x;
    positions[i + 1] = part.positions[i + 1]! - centre.y;
    positions[i + 2] = part.positions[i + 2]! - centre.z;
  }
  return { geometry: geometryOf({ ...part, positions }, light, lit), centre };
}

/** The centre of a box, for framing a map whose spawns are not known. */
export function centre(box: Box3): [number, number, number] {
  const v = box.getCenter(new Vector3());
  return [v.x, v.y, v.z];
}

function geometryOf(
  part: LoadedMesh,
  light: Lighting,
  lit: { part: Lightable; attribute: BufferAttribute }[],
): BufferGeometry {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(part.positions, 3));
  geometry.setAttribute('uv', new BufferAttribute(part.uvs, 2));
  // The attribute is the *lit* colour, not the material colour on disc: `record2 * lit`, computed here
  // the way the VU computes it (see `./lighting`). Float rather than a normalised byte, because a lit
  // colour goes above 1 and the GS clamps the modulate, not the vertex.
  const colors = new Float32Array(part.colors.length);
  applyLighting(part, light, colors);
  const attribute = new BufferAttribute(colors, 4);
  geometry.setAttribute('color', attribute);
  lit.push({ part, attribute });
  geometry.setIndex(new BufferAttribute(part.indices, 1));
  geometry.computeBoundingSphere();
  return geometry;
}

function makeTexture(rgba: Rgba, spec: MaterialSpec, linearLight: boolean): DataTexture {
  const texture = new DataTexture(new Uint8Array(rgba.data.buffer, rgba.data.byteOffset, rgba.data.length), rgba.width, rgba.height, RGBAFormat);
  texture.flipY = FLIP_Y;
  // NoColorSpace is the GS's own reading: the stored byte *is* the value, and the modulate happens on it.
  texture.colorSpace = linearLight ? SRGBColorSpace : NoColorSpace;
  // `TEX1` off the disc: bilinear on every texture in the corpus, and a mipmap chain on the ground and
  // detail textures that ask for one (`MMIN = LINEAR_MIPMAP_LINEAR`). The hardware was given one or
  // two levels; three generates the whole chain, which is the same picture near and a calmer one far.
  texture.magFilter = spec.bilinear ? LinearFilter : NearestFilter;
  texture.minFilter = spec.mipmaps ? LinearMipmapLinearFilter : spec.bilinear ? LinearFilter : NearestFilter;
  texture.generateMipmaps = spec.mipmaps;
  // `CLAMP` off the disc, per axis. A glow's quad clamps so the bilinear tap at u = 1 cannot fetch
  // u = 0 and draw the quad's outline; a tiling wall repeats.
  texture.wrapS = spec.wrapS === 'clamp' ? ClampToEdgeWrapping : RepeatWrapping;
  texture.wrapT = spec.wrapT === 'clamp' ? ClampToEdgeWrapping : RepeatWrapping;
  texture.needsUpdate = true;
  return texture;
}
