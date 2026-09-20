import { Reader, type Zar, type ZarKey } from '@s2u/archive';
import { multiply } from './sceneGraph';
import { placeInstances, type PlacedModel } from './buildScene';
import type { SceneNode } from './sceneGraph';

/**
 * `CLUTTER.ZAR`, the scattered small props: rocks and grass strewn over the ground, placed outside the
 * scene graph (36 section 2).
 *
 * The layout is `Clutter -> <model name> -> a_clutter -> { params 96 B, scale_inverse f32 }`, one
 * `a_clutter` child per instance -- the children share a name, so they are read positionally rather than
 * by lookup. Frostfire and Crossroads have none (a 192-byte stub with an empty `Clutter` key); Desert
 * Glory has 6 models and 110 instances.
 *
 * `params` is the same 96-byte `tag_NODE_PARAMS` a graph node carries (`zNode/znode.h:73-105`): a
 * row-major 4x4 first, and only that is used here -- the tail is a bbox the placement does not need.
 *
 * The models are ordinary ones: they live in the map's own `MDL` archive and are named by the scene
 * graph as prototypes, but *nothing instances them from the root*, so `placeInstances` never reaches
 * them. `CLUTTER.ZAR` is their only placement, which is why a viewer that ignores it draws a Desert
 * Glory with bare ground.
 */

/** 36 section 2: `params` is a 96-byte `tag_NODE_PARAMS`, whose first 64 bytes are the matrix. */
const PARAMS_SIZE = 96;
const MATRIX_FLOATS = 16;

/** One scattered instance: which model, where, and the reciprocal of the scale baked into the matrix. */
export interface ClutterInstance {
  modelName: string;
  /** 16 floats, row-major, row-vector: the same convention as a node's matrix (24 section 1.1). */
  matrix: Float32Array;
  /**
   * `scale_inverse`: 1 / the uniform scale in `matrix`, stored rather than derived. The engine wants it
   * to unscale normals without a square root per instance; a viewer only needs it to notice when the two
   * disagree, which on Desert Glory they never do.
   */
  scaleInverse: number;
}

/** Every clutter instance of one map, in archive order (model by model). */
export function parseClutter(zar: Zar): ClutterInstance[] {
  const clutter = zar.find('Clutter');
  if (!clutter) throw new Error('CLUTTER.ZAR has no Clutter key');
  const out: ClutterInstance[] = [];
  for (const model of clutter.children) {
    model.children.forEach((instance, i) => out.push(readInstance(zar, model.name, instance, i)));
  }
  return out;
}

function readInstance(zar: Zar, modelName: string, key: ZarKey, index: number): ClutterInstance {
  const params = zar.child(key, 'params');
  const scale = zar.child(key, 'scale_inverse');
  if (!params || params.size !== PARAMS_SIZE) {
    throw new Error(`clutter ${modelName}[${index}]: params is ${params ? `${params.size} bytes` : 'absent'}, expected ${PARAMS_SIZE}`);
  }
  if (!scale || scale.size !== 4) {
    throw new Error(`clutter ${modelName}[${index}]: scale_inverse is ${scale ? `${scale.size} bytes` : 'absent'}, expected 4`);
  }
  const r = new Reader(zar.data(params));
  const matrix = new Float32Array(MATRIX_FLOATS);
  for (let i = 0; i < MATRIX_FLOATS; i++) matrix[i] = r.f32(i * 4);
  return { modelName, matrix, scaleInverse: new Reader(zar.data(scale)).f32(0) };
}

/** What `placeClutter` found, and the models it could not place. */
export interface PlacedClutter {
  /** One per (instance, visual-bearing node of its model): the same shape a prop placement has. */
  placed: PlacedModel[];
  /** Models named by `CLUTTER.ZAR` that the scene graph does not hold, each named once. */
  missing: string[];
}

/**
 * Places the clutter the way the props are placed: a model's own subtree is realised once, by
 * `placeInstances` rooted at that model, and each instance's matrix is composed on top of it. Doing it
 * through `placeInstances` rather than by hand is what gets the chunk keys right -- a clutter model may
 * carry instance contexts (`N000_I000_V00`) or none (`N000_000`), and the naming rule already knows
 * which from the graph.
 *
 * A model the graph does not hold costs one entry in `missing`, however many instances name it.
 */
export function placeClutter(models: SceneNode[], instances: ClutterInstance[]): PlacedClutter {
  const prototypes = new Map<string, PlacedModel[] | null>();
  const placed: PlacedModel[] = [];
  const missing: string[] = [];
  for (const instance of instances) {
    let local = prototypes.get(instance.modelName);
    if (local === undefined) {
      try {
        local = placeInstances(models, instance.modelName);
      } catch {
        local = null;                                  // the graph has no such model; said once, below
        missing.push(instance.modelName);
      }
      prototypes.set(instance.modelName, local);
    }
    if (local === null) continue;
    for (const part of local) {
      const rowMajor = multiply(part.rowMajor, instance.matrix);
      placed.push({
        ...part,
        path: `clutter/${instance.modelName}`,
        world: Float32Array.from(rowMajor),            // the stored floats are three.js's elements (24 section 1.1)
        rowMajor,
      });
    }
  }
  return { placed, missing };
}
