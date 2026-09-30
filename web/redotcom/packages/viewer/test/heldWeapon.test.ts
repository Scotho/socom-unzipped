import { describe, expect, it } from 'vitest';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Mesh } from 'three';
import type { MeshBasicNodeMaterial } from 'three/webgpu';
import { FsAssetSource } from '@s2u/archive/node';
import { DEFAULT_GRID_PARAMS } from '@s2u/scene';
import { fixture } from '../../archive/test/fixtures';
import { loadMap, transferables, type HeldWeapon, type LoadedMap, type LoadedMesh } from '../src/loadMap';
import { buildWorld } from '../src/world';

/**
 * The held weapons (W2.4 step 2; web/redotcom/docs/research/79 §2; web sprint 4 M3): decoded in the worker beside the
 * map -- every firearm model the arsenal names, the library parsed once -- their textures from the map's own
 * asset-library chain (`WEAP_TXR`/`WEAP_PAL`), built by `buildWorld` on demand on the world's own GS path.
 */

const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), '../../../test-fixtures');
const MP2 = fixture('RUN/MP2.ZDB');

describe('loadMap: the held weapon', () => {
  it.skipIf(!MP2)('decodes the M4A1 SD\'s high LOD on Frostfire with its textures and nodes, and no diagnostic', async () => {
    const map = await loadMap(new FsAssetSource(FIXTURES), 'RUN/MP2.ZDB');
    const weapon = map.weapons!['m4Acarbine_sd']!;
    expect(weapon.name).toBe('m4Acarbine_sd');
    expect(weapon.parts).toHaveLength(11);                               // m4_high's 11 packets
    expect(weapon.parts.reduce((n, p) => n + p.indices.length / 3, 0)).toBe(395);
    expect([...new Set(weapon.parts.map((p) => p.textureName))].sort()).toEqual(['m4.tif', 'mark03.tif']);
    expect(map.textures['m4.tif']).toBeDefined();
    expect(map.textures['mark03.tif']).toBeDefined();
    expect(weapon.points.find((p) => p.name === 'firepoint')?.at[0]).toBeCloseTo(7.7854, 4);
    expect(map.diagnostics.filter((d) => /weapon|m4Acarbine/i.test(d))).toEqual([]);
    const buffers = transferables(map);
    expect(buffers).toContain(weapon.parts[0]!.positions.buffer);
  });

  it.skipIf(!MP2)('decodes every firearm of the arsenal the library holds, both sides\' kits among them, and the kits\' icons', async () => {
    const map = await loadMap(new FsAssetSource(FIXTURES), 'RUN/MP2.ZDB');
    const models = Object.keys(map.weapons!);
    // Research 94 §A4: Frostfire's four SEAL and four Terrorist kits' primaries and secondaries.
    for (const m of ['m4Acarbine', 'remington870', 'mp5', 'stoner_sr25', 'a_mark23', 'sig_commando', 'spas12', 'fnp90', 'barretm82A1',
      'baretta_m9', 'desert_eagle', 'fiveseven', 'glock18']) expect(models).toContain(m);
    // The SA-80's `ModelName IW80A2` is the library's `iw80a2`: found by the name, case aside (MODEL_NAME_CASE_READING).
    expect(map.weapons!['IW80A2']!.parts.length).toBeGreaterThan(0);
    for (const m of models) for (const p of map.weapons![m]!.parts) if (p.textureName) expect(map.textures[p.textureName]).toBeDefined();
    expect(map.arsenal!.map!.kits.seal[0]!.loadout).toEqual([54, 15, 121, 126, 194]);
    for (const icon of ['m4carbine_icon.tif', 'sigcommando_icon.tif', 'gun_baretta_9mm_icon.tif', 'barrettm82a.tif']) expect(map.hud![icon]).toBeDefined();
    expect(map.diagnostics).toEqual([]);
  });
});

const part = (textureName: string | null): LoadedMesh => ({
  positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), uvs: new Float32Array(6),
  colors: new Float32Array(12).fill(1), normals: null, faceNormals: null, indices: new Uint32Array([0, 1, 2]),
  textureName, fog: true, lit: false, order: 0, orderEnd: 0, cull: true, alternate: false, scroll: null,
});
const map = (weapon?: HeldWeapon): LoadedMap => ({
  archive: 'SYN', camera: null, path: 'SYN.ZDB', name: 'synthetic', world: [], lines: null, props: [],
  textures: { 'm4.tif': { data: new Uint8ClampedArray(16).fill(255), width: 2, height: 2 } },
  textureFlags: { 'm4.tif': { bilinear: true, transparent: false, graded: false, opaque: true, gs: null } },
  metersPerUnit: 0.1, lightRig: null, origin: [0, 0, 0], detail: {}, grid: DEFAULT_GRID_PARAMS,
  collision: { positions: new Float32Array(0), colors: new Uint8Array(0), polygons: 0 },
  slots: [], diagnostics: [], loadMs: 0, timings: { fetch: 0, decode: 0, postedAt: 0 },
  ...(weapon ? { weapons: { [weapon.name]: weapon } } : {}),
} as LoadedMap);

describe('buildWorld: the held weapon', () => {
  it('builds it as its own group on first ask, outside the world\'s, textured through the world\'s materials; one a model', () => {
    const view = buildWorld(map({ name: 'm4Acarbine_sd', parts: [part('m4.tif'), part(null)], points: [] }));
    const weapon = view.held('m4Acarbine_sd')!;
    expect(view.held('m4Acarbine_sd')).toBe(weapon);
    expect(weapon.name).toBe('m4Acarbine_sd');
    const meshes = weapon.children.filter((c): c is Mesh => c instanceof Mesh);
    expect(meshes).toHaveLength(2);
    expect((meshes[0]!.material as MeshBasicNodeMaterial).map).not.toBeNull();
    expect((meshes[1]!.material as MeshBasicNodeMaterial).map).toBeNull();
    for (const task of [...view.revealWorld, ...view.revealProps]) task();
    expect(view.group.getObjectByName('m4Acarbine_sd')).toBeUndefined();
    expect(view.triangles).toBe(0);                                      // the map's count, not the hand's
  });

  it('has none on a map that decoded none', () => {
    expect(buildWorld(map(undefined)).held('m4Acarbine_sd')).toBeNull();
    expect(buildWorld(map({ name: 'a_mark23', parts: [part(null)], points: [] })).held('m4Acarbine_sd')).toBeNull();
  });
});
