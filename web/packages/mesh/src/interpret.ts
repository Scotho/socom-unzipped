import type { Chain } from './dma';
import { unpackVif, type VuPacket } from './vif';
import type { MeshData } from './meshData';

/**
 * Turns an unpacked VU1 packet into triangles without running VU1.
 *
 * Every rule and every constant below comes from `SEMANTICS.md` in this package (Task 11's decode of the
 * VU1 microprogram's own translation, cross-checked against Frostfire's 416 drawn packets); the section and
 * table row is cited at each one. The short version, SEMANTICS §1:
 *
 * - position = `int16 xyz / 16 + header[3].xyz`, y up, model space;
 * - the primitive is an **indexed triangle list**, three byte offsets per tail entry, `index = byte / 3`;
 * - UV = `int16 / 4096`, normalised;
 * - the per-vertex normal is `(a.w, b.z, b.w) / 32768`, the per-face normal the tail's `V3-16` quadword.
 */

/** VU data memory is 1024 quadwords of four lanes; `VuPacket.mem` is that memory flattened. */
const VU_QUADWORDS = 1024;
const LANES = 4;
const X = 0, Y = 1, Z = 2, W = 3;

/** SEMANTICS §2/§3: `TOP+0 … TOP+3` are two GIFtag templates, the counts and the position bias. */
const HEADER_QUADWORDS = 4;
/** SEMANTICS §3 `TOP+2`: .x the index-list quadword offset, .z the vertex count, .w the triangle count. */
const COUNTS_QW = 2;
/** SEMANTICS §3 `TOP+3`: .xyz the float position bias, added after the `ITOF4`. */
const BIAS_QW = 3;
/** SEMANTICS §2: the vertex block starts at `TOP+4`, three quadwords a vertex. */
const VERTEX_BASE = 4;
const VERTEX_QUADWORDS = 3;
/** SEMANTICS §5: two quadwords a triangle, the index entry then the face normal. */
const TAIL_QUADWORDS = 2;

/** SEMANTICS §4 quadword a x,y,z: `ITOF4`, so the stored int16 is sixteenths of a unit. */
const POSITION_SCALE = 16;
/** SEMANTICS §4 quadword b x,y: `ITOF12`, normalised texture coordinates (§7 — TW/TH do not enter). */
const UV_SCALE = 4096;
/** SEMANTICS §4 (a.w, b.z, b.w) and §5 entry [1]: `ITOF15`, 1.15 fixed point. */
const NORMAL_SCALE = 32768;
/** SEMANTICS §5 entry [0]: a vertex is named by its quadword offset from `TOP+4`, stride 3. */
const INDEX_STRIDE = 3;
/**
 * SEMANTICS §4 quadword c: the PS2 writes vertex colour with 128, not 255, as full — alpha 128 is opaque and
 * rgb 128 is full brightness. A browser reads 255, so both are rescaled here, once, and `MeshData.colors` is
 * plain 0..255 RGBA for every consumer (the viewer's attribute, the glTF exporter's `COLOR_0`).
 */
const PS2_FULL = 128;
const BYTE_MAX = 255;

/** A packet whose lanes do not hold what SEMANTICS says a map geometry packet holds. */
export class MeshError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'MeshError';
  }
}

/**
 * The index a tail lane names. SEMANTICS §5: the byte is a quadword offset from `TOP+4` at a stride of three
 * quadwords, so it is a multiple of 3 — true of every one of Frostfire's 8,765 triples.
 */
function vertexIndex(offset: number, vertexCount: number, lane: string): number {
  if (offset % INDEX_STRIDE !== 0) throw new MeshError(`index byte ${offset} (${lane}) is not a multiple of 3, so it names no vertex triple`);
  const index = offset / INDEX_STRIDE;
  if (index >= vertexCount) throw new MeshError(`index byte ${offset} (${lane}) names vertex ${index} of ${vertexCount}`);
  return index;
}

/** Turns one drawn (`MSCNT`) packet into a mesh. Throws `MeshError` on anything SEMANTICS does not describe. */
export function interpretPacket(packet: VuPacket): MeshData {
  const { mem, f32, written } = packet;
  /** Where a quadword's lanes start in `mem`, once this packet is known to have unpacked it. */
  const lanesOf = (qw: number, what: string): number => {
    if (written[qw] !== 1) throw new MeshError(`${what} at TOP+${qw} was never unpacked, so this is not a drawn geometry packet`);
    return qw * LANES;
  };

  for (let q = 0; q < HEADER_QUADWORDS; q++) lanesOf(q, 'the header quadword');
  const counts = COUNTS_QW * LANES;
  const indexBase = mem[counts + X]! >>> 0;
  const vertexCount = mem[counts + Z]! >>> 0;
  const triangleCount = mem[counts + W]! >>> 0;
  const bias = [f32[BIAS_QW * LANES + X]!, f32[BIAS_QW * LANES + Y]!, f32[BIAS_QW * LANES + Z]!];
  // A count that cannot fit VU memory is not a count, and must not become an allocation.
  const fits = (last: number, what: string) => {
    if (last > VU_QUADWORDS) throw new MeshError(`the header claims ${what} reaching TOP+${last}, past the ${VU_QUADWORDS} quadwords of VU data memory`);
  };
  fits(VERTEX_BASE + VERTEX_QUADWORDS * vertexCount, `${vertexCount} vertices`);
  fits(indexBase + TAIL_QUADWORDS * triangleCount, `${triangleCount} triangles from TOP+${indexBase}`);

  const positions = new Float32Array(vertexCount * 3);
  const uvs = new Float32Array(vertexCount * 2);
  const colors = new Uint8Array(vertexCount * 4);
  const normals = new Float32Array(vertexCount * 3);
  for (let k = 0; k < vertexCount; k++) {
    const base = VERTEX_BASE + VERTEX_QUADWORDS * k;
    const a = lanesOf(base, `vertex ${k}'s position quadword`);          // V4-16, signed
    const b = lanesOf(base + 1, `vertex ${k}'s UV quadword`);            // V4-16, signed
    const c = lanesOf(base + 2, `vertex ${k}'s colour quadword`);        // V4-8 USN, unsigned bytes
    positions[k * 3 + X] = mem[a + X]! / POSITION_SCALE + bias[X]!;
    positions[k * 3 + Y] = mem[a + Y]! / POSITION_SCALE + bias[Y]!;
    positions[k * 3 + Z] = mem[a + Z]! / POSITION_SCALE + bias[Z]!;
    normals[k * 3 + X] = mem[a + W]! / NORMAL_SCALE;
    normals[k * 3 + Y] = mem[b + Z]! / NORMAL_SCALE;
    normals[k * 3 + Z] = mem[b + W]! / NORMAL_SCALE;
    uvs[k * 2 + X] = mem[b + X]! / UV_SCALE;
    uvs[k * 2 + Y] = mem[b + Y]! / UV_SCALE;
    // Doubled and clamped: a few vertices are written brighter than full on purpose, and they stay at white.
    colors[k * 4 + X] = Math.min(mem[c + X]! * 2, BYTE_MAX);
    colors[k * 4 + Y] = Math.min(mem[c + Y]! * 2, BYTE_MAX);
    colors[k * 4 + Z] = Math.min(mem[c + Z]! * 2, BYTE_MAX);
    colors[k * 4 + W] = Math.round(Math.min(mem[c + W]! / PS2_FULL, 1) * BYTE_MAX);
  }

  // SEMANTICS §6: one triangle per tail pair, in index order, CCW front-facing. Entry [0].w is the runtime
  // cull result the VU rewrites every frame, not a hint on disc, so it is read by nothing here.
  const indices = new Uint32Array(triangleCount * 3);
  const faceNormals = new Float32Array(triangleCount * 3);
  let kept = 0;
  for (let t = 0; t < triangleCount; t++) {
    const entry = indexBase + TAIL_QUADWORDS * t;
    const e0 = lanesOf(entry, `triangle ${t}'s index quadword`);         // V4-8 USN, unsigned bytes
    const e1 = lanesOf(entry + 1, `triangle ${t}'s face normal`);        // V3-16, signed; lane w is stale
    const i0 = vertexIndex(mem[e0 + X]!, vertexCount, `triangle ${t} x`);
    const i1 = vertexIndex(mem[e0 + Y]!, vertexCount, `triangle ${t} y`);
    const i2 = vertexIndex(mem[e0 + Z]!, vertexCount, `triangle ${t} z`);
    if (isDegenerate(positions, i0, i1, i2)) continue;                   // SEMANTICS §6: they exist, drop them
    indices[kept * 3 + 0] = i0;
    indices[kept * 3 + 1] = i1;
    indices[kept * 3 + 2] = i2;
    faceNormals[kept * 3 + X] = mem[e1 + X]! / NORMAL_SCALE;
    faceNormals[kept * 3 + Y] = mem[e1 + Y]! / NORMAL_SCALE;
    faceNormals[kept * 3 + Z] = mem[e1 + Z]! / NORMAL_SCALE;
    kept++;
  }

  return {
    positions, uvs, colors, normals,
    // `slice`, not `subarray`: a dropped triangle must not leave a consumer a buffer longer than the mesh.
    faceNormals: kept === triangleCount ? faceNormals : faceNormals.slice(0, kept * 3),
    indices: kept === triangleCount ? indices : indices.slice(0, kept * 3),
    textureName: packet.textureName,
  };
}

/** Zero area: the two edges are parallel, so the triangle covers no pixels and has no usable normal. */
function isDegenerate(positions: Float32Array, i0: number, i1: number, i2: number): boolean {
  const ax = positions[i0 * 3]!, ay = positions[i0 * 3 + 1]!, az = positions[i0 * 3 + 2]!;
  const ux = positions[i1 * 3]! - ax, uy = positions[i1 * 3 + 1]! - ay, uz = positions[i1 * 3 + 2]! - az;
  const vx = positions[i2 * 3]! - ax, vy = positions[i2 * 3 + 1]! - ay, vz = positions[i2 * 3 + 2]! - az;
  return uy * vz - uz * vy === 0 && uz * vx - ux * vz === 0 && ux * vy - uy * vx === 0;
}

/**
 * Every mesh one chunk draws: one per `MSCNT` packet, each with the texture the chain cited for it. The
 * `MSCAL 0` packets carry the two parameter quadwords VU1 entry 0 reads (SEMANTICS §9) and no geometry, so
 * they contribute nothing.
 */
export function interpretChain(chain: Chain): MeshData[] {
  const meshes: MeshData[] = [];
  const packets = unpackVif(chain);
  for (let i = 0; i < packets.length; i++) {
    const packet = packets[i]!;
    if (packet.kind !== 'mscnt') continue;
    try {
      meshes.push(interpretPacket(packet));
    } catch (e) {
      if (!(e instanceof MeshError)) throw e;
      throw new MeshError(`chunk ${chain.nodeName} packet ${i}: ${e.message}`);
    }
  }
  return meshes;
}
