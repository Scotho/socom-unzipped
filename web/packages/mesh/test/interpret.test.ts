import { describe, it, expect } from 'vitest';
import { interpretPacket, interpretChain, mergeMeshes, bounds, MeshError, type MeshData } from '../src';
import { walkModel, modelNodes, type Chain } from '../src/dma';
import { unpackVif, unpackVifStream } from '../src/vif';
import { parseZdb, zdbMember, Zar, Reader } from '@s2u/archive';
import { fixture } from '../../archive/test/fixtures';

/** A VIF stream from literal 32-bit code words, little-endian as the DMAC delivers them. */
function words(...w: number[]): Uint8Array {
  const out = new Uint8Array(w.length * 4);
  const dv = new DataView(out.buffer);
  w.forEach((x, i) => dv.setUint32(i * 4, x >>> 0, true));
  return out;
}
const stcycl = (cl: number, wl: number) => 0x01000000 | (wl << 8) | cl;
const unpack = (vn: number, vl: number, num: number, addr: number, usn = false) =>
  (0x60 | (vn << 2) | vl) * 0x1000000 + (num << 16) + (0x8000 | (usn ? 0x4000 : 0) | addr);
const MSCNT = 0x17000000;
/** Concatenates stream parts, padding each unpack's data to the 4-byte boundary VIF1 re-aligns to. */
const bytes = (...parts: ArrayBufferView[]) => {
  const chunks = parts.map((p) => {
    const raw = new Uint8Array(p.buffer, p.byteOffset, p.byteLength);
    if (raw.byteLength % 4 === 0) return raw;
    const padded = new Uint8Array((raw.byteLength + 3) & ~3);
    padded.set(raw);
    return padded;
  });
  const out = new Uint8Array(chunks.reduce((n, c) => n + c.byteLength, 0));
  let at = 0;
  for (const c of chunks) { out.set(c, at); at += c.byteLength; }
  return out;
};

/**
 * One synthetic MSCNT packet in exactly the shape SEMANTICS §2 lays out: a V4-32 header at TOP+0, `V`
 * vertex triples from TOP+4 (V4-16 positions/UV/normal at CL=3 WL=2, V4-8 USN colours at CL=3 WL=1), and
 * `P` two-quadword tail entries at TOP+4+3V (V4-8 USN indices, V3-16 face normals, both CL=2 WL=1).
 */
function packet(o: {
  bias: [number, number, number];
  verts: { a: [number, number, number, number]; b: [number, number, number, number]; c: [number, number, number, number] }[];
  tris: { e0: [number, number, number, number]; fn: [number, number, number] }[];
  /** The counts the header states, when they are to differ from the blocks actually written. */
  counts?: [indexBase: number, vertices: number, triangles: number];
}): Uint8Array {
  const V = o.verts.length, P = o.tris.length, indexBase = 4 + 3 * V;
  const head = new ArrayBuffer(64);
  const hi = new Int32Array(head), hf = new Float32Array(head);
  const [statedBase, statedV, statedP] = o.counts ?? [indexBase, V, P];
  hi[2 * 4 + 0] = statedBase; hi[2 * 4 + 2] = statedV; hi[2 * 4 + 3] = statedP;   // TOP+2 .x .z .w (SEMANTICS §3)
  hf[3 * 4 + 0] = o.bias[0]; hf[3 * 4 + 1] = o.bias[1]; hf[3 * 4 + 2] = o.bias[2];
  const ab = new Int16Array(o.verts.flatMap((v) => [...v.a, ...v.b]));
  const col = new Uint8Array(o.verts.flatMap((v) => v.c));
  const idx = new Uint8Array(o.tris.flatMap((t) => t.e0));
  const fn = new Int16Array(o.tris.flatMap((t) => t.fn));
  return bytes(
    words(stcycl(1, 1), unpack(3, 0, 4, 0)), new Uint8Array(head),
    words(stcycl(3, 2), unpack(3, 1, 2 * V, 4)), ab,
    words(stcycl(3, 1), unpack(3, 2, V, 6, true)), col,
    words(stcycl(2, 1), unpack(3, 2, P, indexBase, true)), idx,
    words(stcycl(2, 1), unpack(2, 1, P, indexBase + 1)), fn,
    words(MSCNT),
  );
}

/** The synthetic stream wrapped as a chain, so `interpretChain` sees the texture a chain would name. */
function chainOf(vif: Uint8Array, textureName: string | null): Chain {
  const tags = textureName === null ? [] : [{ qwc: 0, reloc: 6, id: 1, addr: 0, vif0: 0, vif1: 0, tagOffset: 0, vifOffset: 0 }];
  return { nodeName: 'N000_000', headerOffset: 0, tags, textureName, textureNames: textureName === null ? [] : [textureName], vif };
}

/** A unit square in the y plane: raw positions 0/16 apart, so `/16` lands them one unit apart. */
const QUAD = {
  bias: [100, 5, -20] as [number, number, number],
  verts: [
    { a: [0, 0, 0, 0] as const, b: [0, 0, 0, 32767] as const, c: [255, 128, 0, 128] as const },
    { a: [16, 0, 0, 0] as const, b: [2048, 4096, 0, 32767] as const, c: [10, 20, 30, 64] as const },
    { a: [0, 0, 16, 0] as const, b: [-4096, 8192, 0, 32767] as const, c: [1, 2, 3, 255] as const },
    { a: [16, 0, 16, 16384] as const, b: [0, 0, -16384, 0] as const, c: [4, 5, 6, 0] as const },
  ].map((v) => ({ a: [...v.a] as [number, number, number, number], b: [...v.b] as [number, number, number, number], c: [...v.c] as [number, number, number, number] })),
  tris: [
    { e0: [0, 6, 3, 3] as [number, number, number, number], fn: [0, 32767, 0] as [number, number, number] },
    { e0: [3, 6, 9, 3] as [number, number, number, number], fn: [0, -32767, 0] as [number, number, number] },
  ],
};

const only = (vif: Uint8Array): MeshData => interpretPacket(unpackVifStream(vif)[0]!);

describe('interpretPacket', () => {
  it('converts every lane the way SEMANTICS names it', () => {
    const m = only(packet(QUAD));
    // §4 quadword a: position = int16/16 + bias
    expect(Array.from(m.positions)).toEqual([100, 5, -20, 101, 5, -20, 100, 5, -19, 101, 5, -19]);
    // §4 quadword b x,y: UV = int16/4096, normalised, no flip
    expect(Array.from(m.uvs)).toEqual([0, 0, 0.5, 1, -1, 2, 0, 0]);
    // §4 normal = (a.w, b.z, b.w)/32768
    expect(Array.from(m.normals!).map((v) => +v.toFixed(5)))
      .toEqual([0, 0, 0.99997, 0, 0, 0.99997, 0, 0, 0.99997, 0.5, -0.5, 0]);
    // §4 quadword c: 128 is full on every lane, so RGB is min(2c, 255) and alpha min(a/128,1)*255 --
    // the 0..255 scale the browser reads, rescaled here rather than in each consumer.
    expect(Array.from(m.colors)).toEqual([255, 255, 0, 255, 20, 40, 60, 128, 2, 4, 6, 255, 8, 10, 12, 0]);
    // §5/§6: one triangle per tail pair, index = byte/3, emitted in stored order
    expect(Array.from(m.indices)).toEqual([0, 2, 1, 1, 2, 3]);
    expect(Array.from(m.faceNormals!).map((v) => +v.toFixed(5))).toEqual([0, 0.99997, 0, 0, -0.99997, 0]);
    expect(m.textureName).toBe(null);
  });

  it('drops a degenerate triangle and keeps its face normal out of the mesh (§6)', () => {
    const m = only(packet({ ...QUAD, tris: [QUAD.tris[0]!, { e0: [3, 6, 3, 3], fn: [0, 0, 0] }, QUAD.tris[1]!] }));
    expect(Array.from(m.indices)).toEqual([0, 2, 1, 1, 2, 3]);
    expect(m.faceNormals!.length).toBe(6);
  });

  it('rejects an index that is not a multiple of 3', () => {
    const bad = () => only(packet({ ...QUAD, tris: [{ e0: [0, 4, 6, 3], fn: [0, 32767, 0] }] }));
    expect(bad).toThrow(MeshError);
    expect(bad).toThrow(/multiple of 3/);
  });

  it('rejects an index past the vertex count', () => {
    expect(() => only(packet({ ...QUAD, tris: [{ e0: [0, 3, 12, 3], fn: [0, 32767, 0] }] }))).toThrow(/vertex 4 of 4/);
  });

  it('rejects a count no VU memory could hold, before allocating for it', () => {
    expect(() => only(packet({ ...QUAD, counts: [16, 1000, 2] }))).toThrow(/past the 1024 quadwords/);
    expect(() => only(packet({ ...QUAD, counts: [16, 4, 600] }))).toThrow(/past the 1024 quadwords/);
  });

  it('rejects a packet whose header was never unpacked', () => {
    const vif = bytes(words(stcycl(1, 1), unpack(3, 1, 2, 4)), new Int16Array(8), words(MSCNT));
    expect(() => only(vif)).toThrow(/TOP\+0/);
  });
});

describe('interpretChain', () => {
  it('returns one mesh per MSCNT packet, carrying the texture in force (ruling b)', () => {
    const meshes = interpretChain(chainOf(packet(QUAD), 'floor_oilgrime.tif'));
    expect(meshes.length).toBe(1);
    expect(meshes[0]!.textureName).toBe('floor_oilgrime.tif');
  });

  it('names the chunk and packet when a packet does not decode', () => {
    const vif = bytes(words(stcycl(1, 1), unpack(3, 1, 2, 4)), new Int16Array(8), words(MSCNT));
    expect(() => interpretChain(chainOf(vif, null))).toThrow(/chunk N000_000 packet 0/);
  });
});

describe('mergeMeshes and bounds', () => {
  const a = only(packet(QUAD));
  it('concatenates and re-bases indices', () => {
    const m = mergeMeshes([a, a]);
    expect(m.positions.length).toBe(24);
    expect(Array.from(m.indices)).toEqual([0, 2, 1, 1, 2, 3, 4, 6, 5, 5, 6, 7]);
    expect(m.uvs.length).toBe(16);
    expect(m.colors.length).toBe(32);
    expect(m.normals!.length).toBe(24);
    expect(m.faceNormals!.length).toBe(12);
    expect(m.textureName).toBe(null);
  });

  it('keeps a texture every part shares and drops one they do not', () => {
    const tex = (name: string | null): MeshData => ({ ...a, textureName: name });
    expect(mergeMeshes([tex('x.tif'), tex('x.tif')]).textureName).toBe('x.tif');
    expect(mergeMeshes([tex('x.tif'), tex('y.tif')]).textureName).toBe(null);
  });

  it('drops the normals when a part has none', () => {
    expect(mergeMeshes([a, { ...a, normals: null }]).normals).toBe(null);
  });

  it('measures the extent, and an empty mesh has none', () => {
    expect(bounds(a)).toEqual({ min: [100, 5, -20], max: [101, 5, -19] });
    expect(bounds(mergeMeshes([]))).toEqual({ min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity] });
  });
});

/** SEMANTICS §8: a node's `nparams` is 96 B = a 64-byte 4x4 matrix + a 32-byte bbox (36 §2). */
const NPARAMS_SIZE = 96;
/** Row-vector convention: the translation is the matrix's fourth row, floats 12, 13, 14 (ruling a). */
const TRANSLATION_AT = 12 * 4;

/**
 * Where Frostfire's world sits. `interpretChain` stays in model space by design (no `MP*_GEO.ZED` knowledge
 * in this package), so the test does the placement: it reads every direct child of `MP2_GEO.ZED`'s
 * `models/worldmodel/children` key, takes each one's `nparams` translation, and returns them by frequency.
 */
function worldTranslations(mp2: Uint8Array): { translation: [number, number, number]; nodes: number }[] {
  const geo = Zar.parse(zdbMember(mp2, parseZdb(mp2), 'MP2_GEO.ZED'));
  const children = geo.find('models/worldmodel/children');
  if (!children) throw new Error('MP2_GEO.ZED has no models/worldmodel/children key');
  const counts = new Map<string, { translation: [number, number, number]; nodes: number }>();
  for (const node of children.children) {
    const nparams = geo.child(node, 'nparams');
    if (!nparams || nparams.size !== NPARAMS_SIZE) continue;
    const r = new Reader(geo.data(nparams));
    const translation: [number, number, number] = [r.f32(TRANSLATION_AT), r.f32(TRANSLATION_AT + 4), r.f32(TRANSLATION_AT + 8)];
    const key = translation.join(',');
    const seen = counts.get(key) ?? { translation, nodes: 0 };
    seen.nodes++;
    counts.set(key, seen);
  }
  return [...counts.values()].sort((x, y) => y.nodes - x.nodes);
}

const translate = (m: MeshData, t: [number, number, number]): MeshData => {
  const positions = new Float32Array(m.positions);
  for (let i = 0; i < positions.length; i += 3) { positions[i]! += t[0]; positions[i + 1]! += t[1]; positions[i + 2]! += t[2]; }
  return { ...m, positions };
};

describe('Frostfire (MP2) worldmodel', () => {
  const mp2 = fixture('RUN/MP2.ZDB');
  const worldChains = () => {
    const toc = parseZdb(mp2!);
    const worl = Zar.parse(zdbMember(mp2!, toc, 'WORL_MDL.ZED'));
    const world = worl.find('worldmodel')!;
    return walkModel(worl.data(world), modelNodes(worl, world));
  };
  const decoded = () => worldChains().flatMap(interpretChain);

  it.skipIf(!mp2)('decodes all 416 drawn packets: 15,071 vertices, 8,765 triangles less the one degenerate (§10)', () => {
    const chains = worldChains();
    const meshes = chains.flatMap(interpretChain);
    expect(meshes.length).toBe(416);
    const stated = chains.flatMap(unpackVif).filter((p) => p.kind === 'mscnt')
      .reduce((n, p) => n + (p.mem[2 * 4 + 3]! >>> 0), 0);    // TOP+2.w, the packet's own triangle count
    expect(stated).toBe(8765);
    const world = mergeMeshes(meshes);
    expect(world.positions.length / 3).toBe(15071);
    expect(world.indices.length / 3).toBe(8764);
    expect(world.uvs.length / 2).toBe(15071);
    expect(world.colors.length / 4).toBe(15071);
    expect(world.normals!.length / 3).toBe(15071);
    expect(world.faceNormals!.length / 3).toBe(8764);
    for (const v of world.positions) expect(Number.isFinite(v)).toBe(true);
    for (const i of world.indices) expect(i).toBeLessThan(world.positions.length / 3);
  });

  it.skipIf(!mp2)('every vertex normal is unit length or exactly zero, and the stored face normal is the CCW cross product (§4, §6)', () => {
    const world = mergeMeshes(decoded());
    let zero = 0, unit = 0;
    for (let i = 0; i < world.normals!.length; i += 3) {
      const n = world.normals!.subarray(i, i + 3);
      const len = Math.hypot(n[0]!, n[1]!, n[2]!);
      if (len === 0) zero++; else { expect(len).toBeCloseTo(1, 3); unit++; }
    }
    expect(zero).toBe(16);
    expect(unit).toBe(15071 - 16);
    let worst = 1;
    for (let t = 0; t < world.indices.length / 3; t++) {
      const [i0, i1, i2] = [world.indices[3 * t]!, world.indices[3 * t + 1]!, world.indices[3 * t + 2]!];
      const p = (i: number) => world.positions.subarray(3 * i, 3 * i + 3);
      const [a, b, c] = [p(i0), p(i1), p(i2)];
      const e1 = [b[0]! - a[0]!, b[1]! - a[1]!, b[2]! - a[2]!], e2 = [c[0]! - a[0]!, c[1]! - a[1]!, c[2]! - a[2]!];
      const cr = [e1[1]! * e2[2]! - e1[2]! * e2[1]!, e1[2]! * e2[0]! - e1[0]! * e2[2]!, e1[0]! * e2[1]! - e1[1]! * e2[0]!];
      const len = Math.hypot(cr[0]!, cr[1]!, cr[2]!);
      const f = world.faceNormals!.subarray(3 * t, 3 * t + 3);
      const flen = Math.hypot(f[0]!, f[1]!, f[2]!);
      if (len === 0 || flen === 0) continue;
      worst = Math.min(worst, (cr[0]! * f[0]! + cr[1]! * f[1]! + cr[2]! * f[2]!) / (len * flen));
    }
    expect(worst).toBeGreaterThan(0.99);      // §6: the RH cross product in index order IS the face normal
  });

  it.skipIf(!mp2)('the worldmodel nodes share one placement, a pure translation of (960, 0, 800) (§8)', () => {
    const [first, ...rest] = worldTranslations(mp2!);
    expect(first!.translation).toEqual([960, 0, 800]);
    expect(first!.nodes).toBeGreaterThan(rest.reduce((n, r) => n + r.nodes, 0) / 2);
  });

  it.skipIf(!mp2)('placed by that node translation the world encloses both measured spawns and its floors sit under their feet', () => {
    const world = translate(mergeMeshes(decoded()), worldTranslations(mp2!)[0]!.translation);
    const b = bounds(world);
    for (const [x, y, z] of [[796, 100, 614], [536, 143, 1254]] as const) {
      expect(x).toBeGreaterThan(b.min[0]); expect(x).toBeLessThan(b.max[0]);
      expect(z).toBeGreaterThan(b.min[2]); expect(z).toBeLessThan(b.max[2]);
      // a triangle vertex within 40 units horizontally and 30 units below the spawn's feet: the floor it stands on
      let found = false;
      for (let i = 0; i < world.positions.length; i += 3) {
        const dx = world.positions[i]! - x, dz = world.positions[i + 2]! - z, dy = y - world.positions[i + 1]!;
        if (dx * dx + dz * dz < 40 * 40 && dy >= -5 && dy <= 30) { found = true; break; }
      }
      expect(found).toBe(true);
    }
    expect(world.indices.length / 3).toBeGreaterThan(2000);
  });
});
