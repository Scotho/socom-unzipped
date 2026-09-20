import {
  parseRdr, parseZdb, rdrGet, Reader, Zar, zdbMember,
  type AssetSource, type ZarKey, type ZdbEntry,
} from '@s2u/archive';
import { decodeTexture, parseTextureRecord, PaletteTable, type Rgba } from '@s2u/gs';
import { interpretChain, mergeMeshes, modelNodes, walkModel, type MeshData } from '@s2u/mesh';

/**
 * One map, decoded far enough to draw: the world's triangles grouped one mesh per texture, the textures
 * those meshes name, and everything that went wrong on the way.
 *
 * Positions are MODEL space (`mesh/SEMANTICS.md` section 4); `origin` is where the world sits (section 8),
 * applied by the viewer as the scene group's position rather than by rewriting 15,071 vertices.
 */
export interface LoadedMap {
  archive: string;
  path: string;
  name: string;
  world: MeshData[];
  textures: Record<string, Rgba>;
  textureFlags: Record<string, { bilinear: boolean; transparent: boolean }>;
  metersPerUnit: number;
  origin: [number, number, number];
  diagnostics: string[];
  loadMs: number;
}

/** SEMANTICS section 8 / 36 section 2: `nparams` is a 64-byte row-major 4x4 then a 32-byte bbox. */
const NPARAMS_SIZE = 96;
/** Row-vector convention: the translation is the matrix's fourth row, floats 12, 13, 14. */
const TRANSLATION_AT = 12 * 4;
/** `MP*.ZED/MetersPerUnit` is one float; Frostfire reads 0.1, and every map so far agrees. */
const DEFAULT_METERS_PER_UNIT = 0.1;

const stemOf = (path: string): string => path.replace(/^.*\//, '').replace(/\.ZDB$/i, '').toUpperCase();
const textureKey = (name: string): string => name.toLowerCase();
const say = (e: unknown): string => (e instanceof Error ? e.message : String(e));

/**
 * Loads a map archive and decodes its `worldmodel` and the textures that model cites.
 *
 * The sequence mirrors `web/tools/dump-textures.ts` for the texture half and the mesh package's Frostfire
 * tests for the geometry half: ZDB table of contents, `WORL_MDL.ZED` -> `worldmodel` -> DMA chains ->
 * VIF packets -> `MeshData`, and `MP*_TXR.ZED` + `MP*_PAL.ZED` -> `TextureRecord` -> RGBA.
 *
 * Nothing here throws for bad map data if it can help it: a chunk that fails to interpret, or a texture
 * that is missing or complains, becomes a diagnostic string and the rest of the map still draws.
 */
export async function loadMap(source: AssetSource, path: string): Promise<LoadedMap> {
  const started = Date.now();
  const diagnostics: string[] = [];
  const bytes = await source.read(path);
  const toc = parseZdb(bytes);
  const stem = stemOf(path);

  // The geometry: every chunk of the world model, one mesh per drawn VU1 packet.
  const worl = Zar.parse(zdbMember(bytes, toc, 'WORL_MDL.ZED'));
  const worldKey = worl.find('worldmodel');
  if (!worldKey) throw new Error(`${path}: WORL_MDL.ZED has no worldmodel key`);
  const buffer = worl.data(worldKey);
  const parts: MeshData[] = [];
  for (const chain of walkModel(buffer, modelNodes(worl, worldKey))) {
    try {
      parts.push(...interpretChain(chain));
    } catch (e) {
      diagnostics.push(`chunk ${chain.nodeName}: ${say(e)}`);
    }
  }

  // One draw call per texture: Frostfire's 416 packets cite 37 names, and merging by name turns 416 draws
  // into 37 without touching a vertex.
  const byTexture = new Map<string, MeshData[]>();
  for (const part of parts) {
    const key = part.textureName === null ? '' : textureKey(part.textureName);
    const group = byTexture.get(key);
    if (group) group.push(part);
    else byTexture.set(key, [part]);
  }
  const world = [...byTexture.entries()].map(([key, group]) => ({
    ...mergeMeshes(group),
    // `mergeMeshes` drops the name when parts disagree; here they agree by construction, and the empty
    // key means the packets cited no texture at all.
    textureName: key === '' ? null : key,
  }));

  // The textures those meshes name, and only those: a map's TXR holds every texture the mission uses.
  const textures: Record<string, Rgba> = {};
  const textureFlags: Record<string, { bilinear: boolean; transparent: boolean }> = {};
  const txr = Zar.parse(zdbMember(bytes, toc, `${stem}_TXR.ZED`));
  const palettes = PaletteTable.fromZars([Zar.parse(zdbMember(bytes, toc, `${stem}_PAL.ZED`))]);
  const keys = new Map<string, ZarKey>();
  for (const key of txr.find('textures')?.children ?? []) keys.set(textureKey(key.name), key);
  for (const mesh of world) {
    const name = mesh.textureName;
    if (name === null || name in textures) continue;
    const key = keys.get(name);
    if (!key) {
      diagnostics.push(`texture ${name}: not in ${stem}_TXR.ZED`);
      continue;
    }
    const texdat = txr.child(key, 'texdat');
    if (!texdat) {
      diagnostics.push(`texture ${name}: no texdat key`);
      continue;
    }
    try {
      const record = parseTextureRecord(key.name, txr.data(texdat));
      const decoded = decodeTexture(record, palettes);
      for (const d of decoded.diagnostics) diagnostics.push(`texture ${name}: ${d}`);
      textures[name] = decoded.rgba;
      textureFlags[name] = { bilinear: record.bilinear, transparent: record.transparent };
    } catch (e) {
      diagnostics.push(`texture ${name}: ${say(e)}`);
    }
  }

  return {
    archive: stem,
    path,
    name: missionName(bytes, toc, diagnostics) ?? stem,
    world,
    textures,
    textureFlags,
    metersPerUnit: metersPerUnit(bytes, toc, stem, diagnostics),
    origin: worldOrigin(bytes, toc, stem, diagnostics),
    diagnostics,
    loadMs: Date.now() - started,
  };
}

/** Every typed array in a `LoadedMap`, for the worker's transfer list: no copies cross the boundary. */
export function transferables(map: LoadedMap): Transferable[] {
  const out: Transferable[] = [];
  for (const mesh of map.world) {
    out.push(mesh.positions.buffer, mesh.uvs.buffer, mesh.colors.buffer, mesh.indices.buffer);
    if (mesh.normals) out.push(mesh.normals.buffer);
    if (mesh.faceNormals) out.push(mesh.faceNormals.buffer);
  }
  for (const rgba of Object.values(map.textures)) out.push(rgba.data.buffer);
  return out;
}

/** 36 section 6: the shown name is `READERM.ZAR/mission.rdr`'s `description`, as `listMaps` reads it. */
function missionName(bytes: Uint8Array, toc: ZdbEntry[], diagnostics: string[]): string | null {
  try {
    const readerm = Zar.parse(zdbMember(bytes, toc, 'READERM.ZAR'));
    const mission = readerm.root.children.find((k) => k.name.toLowerCase() === 'mission.rdr');
    if (!mission) return null;
    const name = rdrGet(parseRdr(readerm.data(mission)), 'description');
    return typeof name === 'string' ? name : null;
  } catch (e) {
    diagnostics.push(`mission name: ${say(e)}`);
    return null;
  }
}

/** `MP*.ZED/MetersPerUnit`, the scale the research tables quote positions in. */
function metersPerUnit(bytes: Uint8Array, toc: ZdbEntry[], stem: string, diagnostics: string[]): number {
  try {
    const zed = Zar.parse(zdbMember(bytes, toc, `${stem}.ZED`));
    const key = zed.find('MetersPerUnit');
    if (key && key.size === 4) return new Reader(zed.data(key)).f32(0);
    diagnostics.push(`${stem}.ZED: no MetersPerUnit key, assuming ${DEFAULT_METERS_PER_UNIT}`);
  } catch (e) {
    diagnostics.push(`MetersPerUnit: ${say(e)}`);
  }
  return DEFAULT_METERS_PER_UNIT;
}

/**
 * Where the world model sits, SEMANTICS section 8: the translation shared by the `worldmodel` subtree's
 * direct children in `MP*_GEO.ZED` -- (960, 0, 800) on Frostfire, where it puts the decoded floors exactly
 * under the measured spawn heights. Tonight the whole world takes the modal one; a later task places
 * chunk by chunk.
 */
function worldOrigin(bytes: Uint8Array, toc: ZdbEntry[], stem: string, diagnostics: string[]): [number, number, number] {
  try {
    const geo = Zar.parse(zdbMember(bytes, toc, `${stem}_GEO.ZED`));
    const children = geo.find('models/worldmodel/children');
    if (!children) throw new Error(`${stem}_GEO.ZED has no models/worldmodel/children key`);
    const counts = new Map<string, { translation: [number, number, number]; nodes: number }>();
    for (const node of children.children) {
      const nparams = geo.child(node, 'nparams');
      if (!nparams || nparams.size !== NPARAMS_SIZE) continue;
      const r = new Reader(geo.data(nparams));
      const translation: [number, number, number] = [r.f32(TRANSLATION_AT), r.f32(TRANSLATION_AT + 4), r.f32(TRANSLATION_AT + 8)];
      const id = translation.join(',');
      const seen = counts.get(id) ?? { translation, nodes: 0 };
      seen.nodes++;
      counts.set(id, seen);
    }
    const modal = [...counts.values()].sort((a, b) => b.nodes - a.nodes)[0];
    if (!modal) throw new Error(`${stem}_GEO.ZED: no worldmodel child carries a 96-byte nparams`);
    const total = [...counts.values()].reduce((n, c) => n + c.nodes, 0);
    if (modal.nodes * 2 <= total) {
      diagnostics.push(`world placement: the modal node translation covers only ${modal.nodes} of ${total} chunks; chunk-exact placement is a later task`);
    }
    return modal.translation;
  } catch (e) {
    diagnostics.push(`world placement: ${say(e)}`);
    return [0, 0, 0];
  }
}
