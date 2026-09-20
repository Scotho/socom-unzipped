import {
  parseRdr, parseZdb, rdrGet, Reader, Zar, zdbMember,
  type AssetSource, type ZarKey, type ZdbEntry,
} from '@s2u/archive';
import { decodeTexture, parseTextureRecord, PaletteTable, type Rgba } from '@s2u/gs';
import { interpretChain, mergeMeshes, walkChain, type MeshData } from '@s2u/mesh';
import {
  IDENTITY, loadModelLibrary, parseSceneGraph, placeInstances, transformPoint,
  type ModelLibrary, type PlacedModel,
} from '@s2u/scene';

/**
 * One map, decoded far enough to draw: the world's triangles grouped one mesh per texture, the textures
 * those meshes name, and everything that went wrong on the way.
 *
 * The world's positions are WORLD space: `scene` gives every chunk the matrix of the `MP*_GEO.ZED` node
 * it hangs off (`hookupVisuals`, `zVisual/vis_main.cpp:88-105`), so the chunks are baked into place here
 * rather than shifted together by `origin`, which is left at zero for a map whose graph could be read.
 *
 * The props stay in MODEL space (`mesh/SEMANTICS.md` section 4): one prop model is drawn in up to 26
 * places, so it is decoded once and each placement travels as a matrix for an `InstancedMesh`.
 */
export interface LoadedMap {
  archive: string;
  path: string;
  name: string;
  world: MeshData[];
  /** One entry per prop model-node: its geometry once, and a column-major 4x4 per placement. */
  props: { modelName: string; parts: MeshData[]; matrices: Float32Array }[];
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
/** 36 section 2: the one model key of `WORL_MDL.ZED`, and the root of `MP*_GEO.ZED`'s placement. */
const WORLD_MODEL = 'worldmodel';
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
 * Nothing here throws for bad map data if it can help it, and that promise is kept one chunk at a time:
 * the DMA walk and the VIF interpretation of a chunk both happen inside `decoder`'s per-chunk `try`, so a
 * malformed tag costs that chunk and nothing else. The same holds a level up -- a model archive, the
 * scene graph, the texture archive, a single texture: each failure is a diagnostic string, and whatever
 * else decoded still draws. Only a ZDB whose table of contents will not parse ends the load.
 */
export async function loadMap(source: AssetSource, path: string): Promise<LoadedMap> {
  const started = Date.now();
  const diagnostics: string[] = [];
  const bytes = await source.read(path);
  const toc = parseZdb(bytes);
  const stem = stemOf(path);

  // The geometry. `scene` reads MP*_GEO.ZED's node tree and says which chain of which model buffer each
  // node draws and where; everything below is decoding what it points at.
  const library = loadModelLibrary(mdlArchives(bytes, toc, stem, diagnostics));
  const chunksOf = decoder(library, diagnostics);
  const placement = place(library, bytes, toc, stem, diagnostics);
  const parts: MeshData[] = [];
  for (const p of placement.world) {
    for (const mesh of chunksOf(p)) parts.push(placeMesh(mesh, p.rowMajor));
  }

  // The props: one entry per model-node, its geometry decoded once and a matrix per placement.
  const props: LoadedMap['props'] = [];
  for (const group of placement.props) {
    const first = group[0]!;
    // Lower-cased here for the same reason the world's names are: `map.textures` is keyed that way, and
    // one Frostfire prop cites `lightDark.tif` with a capital in it.
    const geometry = chunksOf(first).map((mesh) => ({
      ...mesh, textureName: mesh.textureName === null ? null : textureKey(mesh.textureName),
    }));
    if (geometry.length === 0) continue;
    const matrices = new Float32Array(group.length * 16);
    group.forEach((p, i) => matrices.set(p.world, i * 16));
    props.push({ modelName: first.modelName, parts: geometry, matrices });
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
  // A TXR or PAL member that will not parse at all costs one diagnostic and the untextured map, not the
  // load: vertex colours alone still show the geometry, which is what a diagnosing eye is here for.
  const textures: Record<string, Rgba> = {};
  const textureFlags: Record<string, { bilinear: boolean; transparent: boolean }> = {};
  const texlib = textureLibrary(bytes, toc, stem, diagnostics);
  if (texlib) {
    const { txr, palettes, keys } = texlib;
    for (const mesh of [...world, ...props.flatMap((p) => p.parts)]) {
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
  }

  return {
    archive: stem,
    path,
    name: missionName(bytes, toc, diagnostics) ?? stem,
    world,
    props,
    textures,
    textureFlags,
    metersPerUnit: metersPerUnit(bytes, toc, stem, diagnostics),
    origin: placement.origin,
    diagnostics,
    loadMs: Date.now() - started,
  };
}

/** Every typed array in a `LoadedMap`, for the worker's transfer list: no copies cross the boundary. */
export function transferables(map: LoadedMap): Transferable[] {
  const out: Transferable[] = [];
  for (const mesh of [...map.world, ...map.props.flatMap((p) => p.parts)]) {
    out.push(mesh.positions.buffer, mesh.uvs.buffer, mesh.colors.buffer, mesh.indices.buffer);
    if (mesh.normals) out.push(mesh.normals.buffer);
    if (mesh.faceNormals) out.push(mesh.faceNormals.buffer);
  }
  for (const prop of map.props) out.push(prop.matrices.buffer);
  for (const rgba of Object.values(map.textures)) out.push(rgba.data.buffer);
  return out;
}

/**
 * The map's texture archive and its palettes, keyed lower-case the way the meshes name them, or null and
 * one diagnostic if either member is unreadable.
 */
function textureLibrary(bytes: Uint8Array, toc: ZdbEntry[], stem: string, diagnostics: string[]):
{ txr: Zar; palettes: PaletteTable; keys: Map<string, ZarKey> } | null {
  try {
    const txr = Zar.parse(zdbMember(bytes, toc, `${stem}_TXR.ZED`));
    const palettes = PaletteTable.fromZars([Zar.parse(zdbMember(bytes, toc, `${stem}_PAL.ZED`))]);
    const keys = new Map<string, ZarKey>();
    for (const key of txr.find('textures')?.children ?? []) keys.set(textureKey(key.name), key);
    return { txr, palettes, keys };
  } catch (e) {
    diagnostics.push(`textures: ${say(e)} -- the map draws in vertex colour alone`);
    return null;
  }
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
 * 36 section 2: the model buffers a map draws from. None of the three is required: a map missing its
 * world buffer still draws its props, and one missing a prop library still draws its world, each absence
 * costing one diagnostic. `decoder` names whatever the scene graph then asks for and cannot find.
 *
 * `CLIB_MDL.ZED` is deliberately absent, its models being the `MESH_` form the scene graph never names.
 */
function mdlArchives(bytes: Uint8Array, toc: ZdbEntry[], stem: string, diagnostics: string[]): Zar[] {
  const out: Zar[] = [];
  for (const member of ['WORL_MDL.ZED', `${stem}_MDL.ZED`, 'FLIB_MDL.ZED']) {
    try {
      out.push(Zar.parse(zdbMember(bytes, toc, member)));
    } catch (e) {
      diagnostics.push(`${member}: ${say(e)}`);
    }
  }
  return out;
}

/** What gets drawn where: the world's chunks one placement each, and the props grouped by model-node. */
interface Placement {
  world: PlacedModel[];
  /** One group per (model, node); every member draws the same geometry at a different matrix. */
  props: PlacedModel[][];
  /** Zero once the graph has been read: the matrices are already in the positions. */
  origin: [number, number, number];
}

function place(library: ModelLibrary, bytes: Uint8Array, toc: ZdbEntry[], stem: string, diagnostics: string[]): Placement {
  try {
    const geo = Zar.parse(zdbMember(bytes, toc, `${stem}_GEO.ZED`));
    const placed = placeInstances(parseSceneGraph(geo), WORLD_MODEL);
    const world = placed.filter((p) => p.modelName === WORLD_MODEL);
    if (world.length === 0) throw new Error(`no ${WORLD_MODEL} node carries visuals`);
    const groups = new Map<string, PlacedModel[]>();
    for (const p of placed) {
      if (p.modelName === WORLD_MODEL) continue;
      const key = `${p.modelName}#${p.nodeIndex}`;
      const group = groups.get(key);
      if (group) group.push(p);
      else groups.set(key, [p]);
    }
    return { world, props: [...groups.values()], origin: [0, 0, 0] };
  } catch (e) {
    diagnostics.push(`scene graph: ${say(e)} -- falling back to the modal node translation, props omitted`);
    const entry = library.get(WORLD_MODEL);
    const every: PlacedModel = {
      modelName: WORLD_MODEL, path: WORLD_MODEL, nodeIndex: -1, instanceIndex: null,
      chunks: entry ? entry.nodes.map((n) => n.name) : [],
      world: Float32Array.from(IDENTITY), rowMajor: Float32Array.from(IDENTITY),
    };
    return { world: [every], props: [], origin: worldOrigin(bytes, toc, stem, diagnostics) };
  }
}

/**
 * Decodes the chains one placement draws. A chunk that will not interpret becomes a diagnostic and the
 * rest of the map still draws, as it did before the scene graph existed.
 */
function decoder(library: ModelLibrary, diagnostics: string[]): (p: PlacedModel) => MeshData[] {
  const offsets = new Map<string, Map<string, number>>();
  return (p) => {
    const entry = library.get(p.modelName);
    if (!entry) {
      diagnostics.push(`model ${p.modelName}: in the scene graph but not in any MDL archive`);
      return [];
    }
    let where = offsets.get(p.modelName);
    if (!where) offsets.set(p.modelName, where = new Map(entry.nodes.map((n) => [n.name, n.offset])));
    const out: MeshData[] = [];
    for (const chunk of p.chunks) {
      const at = where.get(chunk);
      if (at === undefined) {
        diagnostics.push(`chunk ${p.modelName}/${chunk}: no such chain in the model buffer`);
        continue;
      }
      try {
        out.push(...interpretChain(walkChain(entry.buffer, at, chunk)));
      } catch (e) {
        diagnostics.push(`chunk ${p.modelName}/${chunk}: ${say(e)}`);
      }
    }
    return out;
  };
}

/**
 * Carries a decoded chunk from model space into the world, positions and both sets of normals. Rotating
 * the normals matters even though Frostfire's six world matrices are pure translations: other maps'
 * need not be, and an unrotated normal is a lighting bug nobody would trace back to here.
 */
function placeMesh(mesh: MeshData, m: Float32Array): MeshData {
  if (IDENTITY.every((v, i) => v === m[i])) return mesh;
  const positions = new Float32Array(mesh.positions.length);
  for (let i = 0; i < positions.length; i += 3) {
    const p = transformPoint(m, mesh.positions[i]!, mesh.positions[i + 1]!, mesh.positions[i + 2]!);
    positions[i] = p[0]; positions[i + 1] = p[1]; positions[i + 2] = p[2];
  }
  const rotate = (n: Float32Array | null): Float32Array | null => {
    if (!n) return null;
    const out = new Float32Array(n.length);
    for (let i = 0; i < n.length; i += 3) {
      // The 3x3 alone: a direction has no translation. Row-vector, so the rows multiply the components.
      out[i] = n[i]! * m[0]! + n[i + 1]! * m[4]! + n[i + 2]! * m[8]!;
      out[i + 1] = n[i]! * m[1]! + n[i + 1]! * m[5]! + n[i + 2]! * m[9]!;
      out[i + 2] = n[i]! * m[2]! + n[i + 1]! * m[6]! + n[i + 2]! * m[10]!;
    }
    return out;
  };
  return { ...mesh, positions, normals: rotate(mesh.normals), faceNormals: rotate(mesh.faceNormals) };
}

/**
 * The fallback for a map whose scene graph would not read: SEMANTICS section 8's modal translation, the
 * one shared by most of the `worldmodel` subtree's direct children -- (960, 0, 800) on Frostfire. It
 * misplaces the chunks whose node carries a different matrix, which is why it is no longer the first
 * choice; `place` only reaches for it when `MP*_GEO.ZED` cannot be parsed at all.
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
