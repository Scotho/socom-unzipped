import { describe, it, expect } from 'vitest';
import { parseZdb, zdbMember, Zar } from '@s2u/archive';
import { bounds, interpretChain, mergeMeshes, walkChain, type MeshData } from '@s2u/mesh';
import { fixture, FIXTURES_ABSENT } from '../../archive/test/fixtures';
import {
  countInstances, expectedChunks, flattenScene, loadModelLibrary, multiply, parseSceneGraph,
  parseWorldRoot, placeCollision, placeInstances, toColumnMajor, transformPoint, IDENTITY,
  NODE_INSTANCE, type SceneNode,
} from '../src/index';

/** Frostfire's two measured spawns (36 section 6), in game units, feet on the floor. */
const SPAWN_A: [number, number, number] = [796, 100, 614];
const SPAWN_B: [number, number, number] = [536, 143, 1254];

const mp2 = fixture('RUN/MP2.ZDB');
const archives = (bytes: Uint8Array) => {
  const toc = parseZdb(bytes);
  const zar = (suffix: string) => Zar.parse(zdbMember(bytes, toc, suffix));
  return {
    root: zar('MP2.ZED'), geo: zar('MP2_GEO.ZED'), worl: zar('WORL_MDL.ZED'),
    mdl: zar('MP2_MDL.ZED'), flib: zar('FLIB_MDL.ZED'), clib: zar('CLIB_MDL.ZED'),
  };
};

/** Every node of the forest, depth first, the roots included. */
function everyNode(nodes: SceneNode[]): SceneNode[] {
  const out: SceneNode[] = [];
  const rec = (n: SceneNode) => { out.push(n); for (const c of n.children) rec(c); };
  for (const n of nodes) rec(n);
  return out;
}

describe('matrices (24 section 1.1: row-vector, world = local x parent)', () => {
  it('multiplies in row-vector order: translating then scaling scales the translation', () => {
    const translate = Float32Array.from([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, 0, 0, 1]);
    const scale = Float32Array.from([2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1]);
    // A point at the origin, moved by the local translate and then by the parent scale, lands at 20.
    expect(transformPoint(multiply(translate, scale), 0, 0, 0)).toEqual([20, 0, 0]);
    // The other order is the one the engine does not use: the scale happens first, so the point lands at 10.
    expect(transformPoint(multiply(scale, translate), 0, 0, 0)).toEqual([10, 0, 0]);
  });

  it('hands three.js the stored floats unchanged: the transpose and the layout flip cancel', () => {
    const m = Float32Array.from([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]);
    expect([...toColumnMajor(m)]).toEqual([...m]);
    expect(toColumnMajor(m)).not.toBe(m);                     // a copy, so the caller can keep both
    // The translation is three.js's elements 12..14, which is also the engine's fourth row.
    const t = Float32Array.from([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 960, 0, 800, 1]);
    expect([...toColumnMajor(t).slice(12, 15)]).toEqual([960, 0, 800]);
    // What a three.js Matrix4 then does with a point is what the engine's row-vector product does.
    const yaw = Float32Array.from([0, 0, -1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 5, 0, 0, 1]);
    const e = toColumnMajor(yaw);
    const times = (x: number, y: number, z: number): [number, number, number] => [
      e[0]! * x + e[4]! * y + e[8]! * z + e[12]!,
      e[1]! * x + e[5]! * y + e[9]! * z + e[13]!,
      e[2]! * x + e[6]! * y + e[10]! * z + e[14]!,
    ];
    expect(times(1, 0, 0)).toEqual(transformPoint(yaw, 1, 0, 0));
  });
});

describe.skipIf(mp2 === null)('Frostfire scene graph', () => {
  const { root, geo, worl, mdl, flib, clib } = archives(mp2 ?? new Uint8Array());
  const models = parseSceneGraph(geo);
  const library = loadModelLibrary([worl, mdl, flib]);

  it('reads the world root (36 section 2)', () => {
    const world = parseWorldRoot(root);
    expect(world.metersPerUnit).toBeCloseTo(0.1, 6);
    expect(world.defaultMaterial).toBe('METAL_THICK');
    expect(world.nightMission).toBe(false);
    expect(world.shadowVector.map((v) => Number(v.toFixed(3)))).toEqual([-0.811, -0.2, 0.55]);
  });

  it('yields 46 prototypes, 206 instance nodes and 2,756 collision polygons (36 section 2)', () => {
    expect(models.length).toBe(46);
    const all = everyNode(models);
    expect(all.filter((n) => n.modelName !== null).length).toBe(206);
    expect(all.filter((n) => n.modelName !== null).every((n) => n.type === NODE_INSTANCE)).toBe(true);
    expect(all.reduce((n, node) => n + node.visuals, 0)).toBe(177);
    const polys = all.flatMap((n) => n.collision);
    expect(polys.length).toBe(2756);
    // 36 section 6: the decoded ptcount is the point count, in every polygon.
    expect(polys.every((p) => p.points.length / 3 === p.ptcount)).toBe(true);
    // 36 section 6 says `m_refcount` is 0x2d "in every sample read"; over all 2,756 it is not -- the
    // samples were narrow. What does hold is the region word: 2,477 polygons in region 0, 279 in 34.
    expect(new Set(polys.map((p) => p.region))).toEqual(new Set([0, 34]));
    expect(polys.filter((p) => p.region === 0).length).toBe(2477);
    // 36 section 6's Frostfire histogram of (ditype, ptcount), top to bottom.
    const shape = new Map<string, number>();
    for (const p of polys) shape.set(`${p.ditype},${p.ptcount}`, (shape.get(`${p.ditype},${p.ptcount}`) ?? 0) + 1);
    expect([...shape].sort((a, b) => b[1] - a[1]).slice(0, 6))
      .toEqual([['2,4', 1743], ['3,4', 736], ['2,3', 184], ['3,3', 43], ['3,6', 22], ['3,5', 15]]);
  });

  it('resolves every instance name in the model library, with nothing missing', () => {
    const wanted = new Set(everyNode(models).map((n) => n.modelName).filter((n): n is string => n !== null));
    expect([...wanted].filter((n) => library.get(n) === undefined)).toEqual([]);
    expect(library.skipped).toEqual([]);
    // 36 section 2: character models are a MESH_ chain form and are not part of a map's scene graph.
    expect(loadModelLibrary([clib]).names()).toEqual([]);
  });

  it('numbers the 194 worldmodel children the way SEMANTICS section 8 counted them', () => {
    const children = models.find((m) => m.name === 'worldmodel')!.children;
    expect(children.length).toBe(194);
    expect(new Set(children.map((c) => [...c.matrix].join(','))).size).toBe(70);
    const translations = children.map((c) => [...c.matrix.slice(12, 15)].join(','));
    expect(translations.filter((t) => t === '960,0,800').length).toBe(118);
    // SEMANTICS section 8: where the world nodes carry that translation they are pure translations.
    const pure = children.filter((c) => [...c.matrix.slice(12, 15)].join(',') === '960,0,800');
    expect(pure.every((c) => [...c.matrix.slice(0, 12)].join(',') === '1,0,0,0,0,1,0,0,0,0,1,0')).toBe(true);
  });
});

describe.skipIf(mp2 === null)('Frostfire placement', () => {
  const { geo, worl, mdl, flib } = archives(mp2 ?? new Uint8Array());
  const models = parseSceneGraph(geo);
  const library = loadModelLibrary([worl, mdl, flib]);
  const placed = placeInstances(models);

  it('gives every world chunk its own node matrix, so all 123 are placed and none is left over', () => {
    const world = placed.filter((p) => p.modelName === 'worldmodel');
    expect(world.length).toBe(101);                               // visual-bearing nodes, vis_main.cpp:88-105
    const chunks = world.flatMap((p) => p.chunks);
    expect(chunks.length).toBe(123);
    expect(new Set(chunks).size).toBe(123);
    expect(new Set(library.get('worldmodel')!.nodes.map((n) => n.name))).toEqual(new Set(chunks));
    // The mapping is not the stopgap: the chunks do not all share one matrix.
    expect(new Set(world.map((p) => [...p.world].join(','))).size).toBeGreaterThan(1);
  });

  it('places every prop chunk against a chain the library actually holds', () => {
    const props = placed.filter((p) => p.modelName !== 'worldmodel');
    expect(props.length).toBeGreaterThan(200);
    for (const p of props) {
      const names = new Set(library.get(p.modelName)!.nodes.map((n) => n.name));
      for (const chunk of p.chunks) expect(names.has(chunk)).toBe(true);
    }
  });

  it('counts the instance contexts the exporter wrote keys for (vis_main.cpp:77-111)', () => {
    const counts = countInstances(models);
    // The six models whose key count only comes out right once nested instancing is expanded.
    expect(counts.get('tankrailsupport')).toBe(28);
    expect(counts.get('tankrailbarslo')).toBe(18);
    expect(counts.get('railstraithi1')).toBe(15);
    expect(counts.get('railpostfiller')).toBe(14);
    expect(counts.get('grate_midlod')).toBe(26);
    expect(counts.get('worldmodel')).toBe(0);
    // Every model's key set is exactly what the naming rule predicts from its nodes and its contexts.
    for (const model of models) {
      const entry = library.get(model.name);
      if (!entry) continue;
      expect(new Set(entry.nodes.map((n) => n.name)))
        .toEqual(new Set(expectedChunks(model, counts.get(model.name) ?? 0)));
    }
  });

  it('puts a collision polygon under both spawns, at their measured heights (36 section 6)', () => {
    const polys = placeCollision(models);
    expect(polys.length).toBeGreaterThan(2756);       // an instanced model contributes its polys per instance
    for (const [spawn, expected] of [[SPAWN_A, 100], [SPAWN_B, 142]] as [[number, number, number], number][]) {
      const hits = polys
        .map((p) => ({
          distance: horizontalDistance(p.points, spawn[0], spawn[2]),
          height: planeHeight(p.points, spawn[0], spawn[2]),
        }))
        .filter((h) => h.distance <= 40 && h.height !== null && h.height - spawn[1] >= -5 && h.height - spawn[1] <= 5)
        .sort((a, b) => a.distance - b.distance);
      expect(hits.length).toBeGreaterThan(0);
      expect(hits[0]!.distance).toBe(0);
      expect(hits[0]!.height).toBeCloseTo(expected, 3);
    }
  });

  it('still has a world floor under each spawn once the chunks are placed one by one (task 12)', () => {
    const entry = library.get('worldmodel')!;
    const offsets = new Map(entry.nodes.map((n) => [n.name, n.offset]));
    const world = placed.filter((q) => q.modelName === 'worldmodel');
    const floors: ({ y: number; chunk: string; texture: string | null } | null)[] = [];
    for (const spawn of [SPAWN_A, SPAWN_B]) {
      let best: { y: number; chunk: string; texture: string | null } | null = null;
      for (const p of world) {
        for (const chunk of p.chunks) {
          for (const mesh of interpretChain(walkChain(entry.buffer, offsets.get(chunk)!, chunk))) {
            const y = highestFloorUnder(mesh, p.rowMajor, spawn);
            if (y !== null && (best === null || y > best.y)) best = { y, chunk, texture: mesh.textureName };
          }
        }
      }
      floors.push(best);
    }
    // SEMANTICS section 8 named both chunks and both textures with the modal translation; the per-node
    // placement has to reproduce them exactly, or it has moved the world.
    expect(floors[0]).toEqual({ y: 100, chunk: 'N013_000', texture: 'floor_oilgrime.tif' });
    expect(floors[1]).toEqual({ y: 142, chunk: 'N038_000', texture: 'floor_oilgrime.tif' });
  });

  it('keeps every placed prop over the deck, which only the row-vector order does', () => {
    // The world's own collision polygons are the tight extent to test against -- the drawn world also
    // holds the sky chunk at y = 1442 and a skirt biased to +-2000, which would let anything through.
    const deck = extentOf(placeCollision(models).filter((p) => p.modelName === 'worldmodel').map((p) => p.points));
    expect(deck.min.map((v) => Math.round(v))).toEqual([120, 40, 323]);
    expect(deck.max.map((v) => Math.round(v))).toEqual([1200, 241, 1280]);

    let props = 0;
    const strayed: string[] = [];
    for (const p of placed) {
      if (p.modelName === 'worldmodel') continue;
      const entry = library.get(p.modelName)!;
      const where = new Map(entry.nodes.map((n) => [n.name, n.offset]));
      const parts: MeshData[] = [];
      for (const chunk of p.chunks) parts.push(...interpretChain(walkChain(entry.buffer, where.get(chunk)!, chunk)));
      if (parts.length === 0) continue;
      props++;
      const b = bounds(mergeMeshes(parts));
      const c = transformPoint(p.rowMajor, (b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, (b.min[2] + b.max[2]) / 2);
      // Horizontally over the deck, and vertically between it and the top of the drill tower.
      const over = c[0] >= deck.min[0]! && c[0] <= deck.max[0]! && c[2] >= deck.min[2]! && c[2] <= deck.max[2]!
        && c[1] >= deck.min[1]! - 10 && c[1] <= deck.max[1]! + 120;
      if (!over) strayed.push(`${p.modelName} ${p.path} at ${c.map((v) => v.toFixed(1)).join(',')}`);
    }
    expect(props).toBe(347);
    // The falsification: composing parent x local instead sends 153 of these 347 off the deck, the worst
    // of them 2,105 units away, so this assertion is what holds the convention in place.
    expect(strayed).toEqual([]);
  });

  it('realises the scene as a forest rooted at worldmodel, with the instance matrices accumulated', () => {
    const flat = flattenScene(models, 'worldmodel');
    // The root's world matrix is its own: nothing above it to multiply by but the identity.
    expect([...flat[0]!.world]).toEqual([...multiply(models.find((m) => m.name === 'worldmodel')!.matrix, IDENTITY)]);
    // 26 grates, each a separate realisation of one prototype.
    expect(flat.filter((f) => f.modelName === 'grate_midlod' && f.node.visuals > 0).length).toBe(26);
    expect(new Set(flat.map((f) => f.modelName)).size).toBeGreaterThan(30);
  });
});

/** The height of a polygon's plane over (x, z), or null when the polygon is vertical there. */
function planeHeight(points: Float32Array, x: number, z: number): number | null {
  const n = points.length / 3;
  let nx = 0, ny = 0, nz = 0;                                 // Newell's normal: works for any convex polygon
  for (let i = 0; i < n; i++) {
    const a = i * 3, b = ((i + 1) % n) * 3;
    nx += (points[a + 1]! - points[b + 1]!) * (points[a + 2]! + points[b + 2]!);
    ny += (points[a + 2]! - points[b + 2]!) * (points[a]! + points[b]!);
    nz += (points[a]! - points[b]!) * (points[a + 1]! + points[b + 1]!);
  }
  if (Math.abs(ny) < 1e-6) return null;
  const d = nx * points[0]! + ny * points[1]! + nz * points[2]!;
  return (d - nx * x - nz * z) / ny;
}

/** How far (x, z) is from the polygon's footprint: 0 inside it, the nearest edge distance outside. */
function horizontalDistance(points: Float32Array, x: number, z: number): number {
  const n = points.length / 3;
  let inside = false;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const a = i * 3, b = j * 3;
    if ((points[a + 2]! > z) !== (points[b + 2]! > z) &&
        x < (points[b]! - points[a]!) * (z - points[a + 2]!) / (points[b + 2]! - points[a + 2]!) + points[a]!) inside = !inside;
  }
  if (inside) return 0;
  let best = Infinity;
  for (let i = 0; i < n; i++) {
    const a = i * 3, b = ((i + 1) % n) * 3;
    const dx = points[b]! - points[a]!, dz = points[b + 2]! - points[a + 2]!;
    const len = dx * dx + dz * dz;
    const t = len > 0 ? Math.max(0, Math.min(1, ((x - points[a]!) * dx + (z - points[a + 2]!) * dz) / len)) : 0;
    best = Math.min(best, Math.hypot(x - (points[a]! + t * dx), z - (points[a + 2]! + t * dz)));
  }
  return best;
}

/** The highest triangle of a placed mesh that is under the spawn's feet, or null when none is. */
function highestFloorUnder(mesh: MeshData, world: Float32Array, spawn: [number, number, number]): number | null {
  let best: number | null = null;
  for (let t = 0; t < mesh.indices.length; t += 3) {
    const p = [0, 1, 2].map((j) => {
      const i = mesh.indices[t + j]!;
      return transformPoint(world, mesh.positions[i * 3]!, mesh.positions[i * 3 + 1]!, mesh.positions[i * 3 + 2]!);
    });
    const a = p[0]!, b = p[1]!, c = p[2]!;
    const s1 = (spawn[0] - b[0]!) * (a[2]! - b[2]!) - (a[0]! - b[0]!) * (spawn[2] - b[2]!);
    const s2 = (spawn[0] - c[0]!) * (b[2]! - c[2]!) - (b[0]! - c[0]!) * (spawn[2] - c[2]!);
    const s3 = (spawn[0] - a[0]!) * (c[2]! - a[2]!) - (c[0]! - a[0]!) * (spawn[2] - a[2]!);
    if (((s1 < 0) || (s2 < 0) || (s3 < 0)) && ((s1 > 0) || (s2 > 0) || (s3 > 0))) continue;
    const ux = b[0]! - a[0]!, uy = b[1]! - a[1]!, uz = b[2]! - a[2]!;
    const vx = c[0]! - a[0]!, vy = c[1]! - a[1]!, vz = c[2]! - a[2]!;
    const ny = uz * vx - ux * vz;
    if (Math.abs(ny) < 1e-9) continue;
    const y = a[1]! + ((uy * vz - uz * vy) * (a[0]! - spawn[0]) + (ux * vy - uy * vx) * (a[2]! - spawn[2])) / ny;
    if (y <= spawn[1] + 1 && (best === null || y > best)) best = y;
  }
  return best;
}

/** The axis-aligned extent of a pile of xyz triples. */
function extentOf(pieces: Float32Array[]): { min: number[]; max: number[] } {
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const piece of pieces) {
    for (let i = 0; i < piece.length; i += 3) {
      for (let a = 0; a < 3; a++) {
        const v = piece[i + a]!;
        if (v < min[a]!) min[a] = v;
        if (v > max[a]!) max[a] = v;
      }
    }
  }
  return { min, max };
}
