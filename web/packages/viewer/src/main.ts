import { Clock, Scene } from 'three';
import type { MapInfo } from '@s2u/archive';
import { spawnsFor, type Spawns } from '@s2u/scene';
import { FlyCamera, type Pose } from './camera';
import type { ViewerHook } from './hook';
import type { LoadedMap } from './loadMap';
import { Overlays } from './overlays';
import { createRenderer, type Backend } from './renderer';
import { Ui, type ToggleName } from './ui';
import { buildWorld, centre, type WorldView } from './world';
import type { ViewerRequest, ViewerResponse } from './worker';

/** The served disc tree: `web/public/maps/`, with its own `index.json` beside it. */
const MAPS = '/maps';
/** The map the viewer opens on, and the one the screenshot test asks for by name. */
const DEFAULT_ARCHIVE = 'MP2';
/** Eye height above a spawn's feet: a standing player, not a floating one. */
const EYE = 20;

const canvas = document.getElementById('view') as HTMLCanvasElement | null;
if (!canvas) throw new Error('the page has no #view canvas');

const ui = new Ui();
const scene = new Scene();
const fly = new FlyCamera(canvas);
const overlays = new Overlays(scene);
const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });

let view: WorldView | null = null;
let loaded: LoadedMap | null = null;
let backend: Backend = 'webgl2';

/**
 * Which request the page is still waiting for, one per kind. Loads overlap -- the boot auto-load is
 * already running when the player picks a map, and a small archive can overtake a large one -- so an
 * answer whose id is no longer the wanted one is dropped rather than drawn over the newer map.
 */
let requests = 0;
let wantedIndex = -1;
let wantedMap = -1;
const ask = (request: ViewerRequest): void => worker.postMessage(request);
const load = (path: string): void => {
  wantedMap = ++requests;
  ask({ kind: 'load', id: wantedMap, baseUrl: MAPS, path });
};

worker.addEventListener('message', (event: MessageEvent<ViewerResponse>) => {
  const message = event.data;
  if (message.kind === 'error') {
    if (message.id !== wantedIndex && message.id !== wantedMap) return;
    ui.setStatus(`failed while ${message.doing}: ${message.message}`, 'error');
    return;
  }
  if (message.kind === 'index') {
    if (message.id !== wantedIndex) return;
    showMaps(message.maps);
    return;
  }
  if (message.id !== wantedMap) return;
  show(message.map);
});

ui.onMapChange((path) => {
  if (!path) return;
  ui.setStatus(`loading ${path} ...`);
  load(path);
});
ui.onToggle(applyToggle);
ui.apply(applyToggle);

/** One switch for all six overlays: the world's materials, and the things drawn beside the world. */
function applyToggle(name: ToggleName, on: boolean): void {
  if (name === 'grid') overlays.setGrid(on);
  else if (name === 'axes') overlays.setAxes(on);
  else if (name === 'collision') overlays.setCollision(on);
  else if (name === 'spawns') overlays.setSpawns(on);
  else if (name === 'wireframe') view?.setWireframe(on);
  else view?.setUntexturedHighlight(on);
}

void boot();

/** Brings the renderer up, starts the frame loop, then asks the worker for the map list. */
async function boot(): Promise<void> {
  const { render, resize, backend: chosen } = await createRenderer(canvas!);
  backend = chosen;

  const fit = (): void => {
    const width = Math.max(1, canvas!.clientWidth);
    const height = Math.max(1, canvas!.clientHeight);
    resize(width, height);
    fly.setAspect(width / height);
  };
  fit();
  globalThis.addEventListener('resize', fit);

  const clock = new Clock();
  const frame = (): void => {
    fly.update(Math.min(clock.getDelta(), 0.1));    // a backgrounded tab must not teleport the camera
    render(scene, fly.camera);
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  if (await served()) {
    ui.setStatus(`${backend}: indexing the archives ...`);
    wantedIndex = ++requests;
    ask({ kind: 'index', id: wantedIndex, baseUrl: MAPS });
  } else {
    ui.setStatus(`no maps served at ${MAPS}/index.json -- run the extractor, or open an ISO (milestone M5)`, 'error');
  }
}

/** The served source answers only when the disc tree has been extracted; the ISO source is M5. */
async function served(): Promise<boolean> {
  try {
    return (await fetch(`${MAPS}/index.json`)).ok;
  } catch {
    return false;
  }
}

function showMaps(maps: MapInfo[]): void {
  const first = maps.find((m) => m.archive === DEFAULT_ARCHIVE) ?? maps[0];
  ui.setMaps(maps, first?.path ?? null);
  if (!first) {
    ui.setStatus('the served index lists no MP archives', 'error');
    return;
  }
  ui.setStatus(`loading ${first.name} ...`);
  load(first.path);
}

function show(map: LoadedMap): void {
  if (view) {
    scene.remove(view.group);
    view.dispose();
  }
  loaded = map;
  view = buildWorld(map);
  scene.add(view.group);
  overlays.place(view.box);
  overlays.placeCollision(map.collision);
  // 36 section 6: spawns are not on the disc. `@s2u/scene` holds the measured table, keyed by the name
  // `mission.rdr` shows, which is the name this map was just loaded under.
  const spawn: Spawns | undefined = spawnsFor(map.name);
  overlays.placeSpawns(spawn ?? null);
  // A new world starts in whatever state the panel is showing, not in the state it was built in.
  ui.apply(applyToggle);
  fly.setScale(map.metersPerUnit);

  if (spawn) {
    fly.lookFrom([spawn.a[0], spawn.a[1] + EYE, spawn.a[2]], spawn.b);
  } else {
    // No measured spawns for this map yet: stand off its own extent and look at the middle of it.
    const [cx, cy, cz] = centre(view.box);
    const reach = Math.max(view.box.max.x - view.box.min.x, view.box.max.z - view.box.min.z) || 1000;
    fly.lookFrom([cx, cy + reach * 0.4, cz + reach * 0.6], [cx, cy, cz]);
  }

  ui.select(map.path);
  ui.setDiagnostics(map.diagnostics);
  ui.setStatus([
    `${map.name} (${map.archive})`,
    backend,
    `${view.triangles.toLocaleString('en-GB')} triangles`,
    // Every child of the group is one draw: a world mesh per texture, and an `InstancedMesh` (or a plain
    // one, for a prop placed once) per prop model-node. `map.world.length` counted only the world's.
    `${view.group.children.length} draws`,
    `${map.collision.polygons.toLocaleString('en-GB')} collision polys`,
    `${map.loadMs} ms load`,
  ].join('  |  '));
}

/**
 * The debug hook Playwright drives. `./hook` declares its shape and widens `Window` to hold it, so this is
 * a checked assignment to a real property rather than a cast of the global object.
 */
window.__viewer = {
  setCamera: (pose: Partial<Pose>) => fly.setPose(pose),
  pose: () => fly.pose(),
  stats: () => ({
    triangles: view?.triangles ?? 0,
    backend,
    diagnostics: loaded?.diagnostics ?? [],
    loadMs: loaded?.loadMs ?? 0,
    map: loaded?.name ?? null,
    collisionPolys: loaded?.collision.polygons ?? 0,
    untexturedDraws: view?.untextured ?? 0,
    spawns: (loaded && spawnsFor(loaded.name)) ?? null,
  }),
  toggles: () => ui.toggles(),
} satisfies ViewerHook;
