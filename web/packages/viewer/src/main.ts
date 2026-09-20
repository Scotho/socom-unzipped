import { Clock, Scene } from 'three';
import type { MapInfo } from '@s2u/archive';
import { spawnsFor, type Spawns } from '@s2u/scene';
import { FlyCamera, type Pose } from './camera';
import type { ViewerHook } from './hook';
import type { LoadedMap } from './loadMap';
import { Overlays } from './overlays';
import { createRenderer, type Backend } from './renderer';
import { applyFog, ELF_DEFAULT_FOGCOL, fogForExtent, type FogSettings } from './fog';
import { DEFAULT_LIGHTING, type Lighting } from './lighting';
import { Ui, type SliderName, type ToggleName } from './ui';
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
const fly = new FlyCamera(canvas, {
  onSpeedChange: (m) => ui.setCameraHint(m, fly.isLocked()),
  onLockChange: (locked) => ui.setCameraHint(fly.multiplier(), locked),
});
const overlays = new Overlays(scene);
const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });

let view: WorldView | null = null;
let loaded: LoadedMap | null = null;
let backend: Backend = 'webgl2';
/** The renderer's half of the colour-space switch, once `boot` has one. */
let setLinearLight: ((on: boolean) => void) | null = null;

/** The panel's lighting, accumulated as the sliders move and handed to the world as one set. */
const lighting: Lighting = { ...DEFAULT_LIGHTING };

/** The panel's fog. Replaced wholesale when a map states its own, then nudged by the sliders. */
const fog: FogSettings = {
  enabled: true, ...fogForExtent(1200), color: [...ELF_DEFAULT_FOGCOL],
};
/** The renderer's clear colour, once `boot` has one: the background follows the fog. */
let setClearColor: ((rgb: [number, number, number]) => void) | null = null;

/**
 * False while the fog on screen is the map's own, true once a slider has been dragged. It stops the
 * step-snapped value in the range input from being read back over the decoded one on every map load.
 */
let fogIsMine = false;

/** Puts the current fog on the scene and behind it. */
function refreshFog(): void {
  applyFog(scene, fog);
  setClearColor?.(fog.enabled ? fog.color : ELF_DEFAULT_FOGCOL);
}

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
ui.onChromeToggle();
ui.onSlider((name, value) => {
  if (name === 'fognear' || name === 'fogfar') fogIsMine = true;
  applySlider(name, value);
});
ui.applySliders(applySlider);

/** One switch for all six overlays: the world's materials, and the things drawn beside the world. */
function applySlider(name: SliderName, value: number): void {
  if (name === 'ambient') lighting.ambient = value;
  else if (name === 'lightx') lighting.x = value;
  else if (name === 'lighty') lighting.y = value;
  else if (name === 'lightz') lighting.z = value;
  else if (name === 'lightgain') lighting.gain = value;
  // A slider only owns the fog once the player has moved it: `applySliders` is also called on every
  // map load, and the range input has snapped the decoded value to its step by then.
  else if (name === 'fognear') { if (fogIsMine) { fog.near = value; refreshFog(); } return; }
  else if (name === 'fogfar') { if (fogIsMine) { fog.far = value; refreshFog(); } return; }
  view?.setLighting(lighting);
}

function applyToggle(name: ToggleName, on: boolean): void {
  if (name === 'grid') overlays.setGrid(on);
  else if (name === 'collision') overlays.setCollision(on);
  else if (name === 'spawns') overlays.setSpawns(on);
  else if (name === 'wireframe') view?.setWireframe(on);
  else if (name === 'fog') { fog.enabled = on; refreshFog(); }
  else if (name === 'blendgraded') view?.setBlendGraded(on);
  else if (name === 'linestrips') view?.setLineStrips(on);
  else if (name === 'billboards') view?.setBillboards(on);
  else if (name === 'untextured') view?.setUntexturedHighlight(on);
  else { view?.setLinearLight(on); setLinearLight?.(on); }
}

void boot();

/** Brings the renderer up, starts the frame loop, then asks the worker for the map list. */
async function boot(): Promise<void> {
  const created = await createRenderer(canvas!);
  const { render, resize, backend: chosen } = created;
  setLinearLight = created.setLinearLight;
  setClearColor = created.setClearColor;
  ui.onFogColour((rgb) => { fog.color = rgb; refreshFog(); });
  refreshFog();
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
  // A frame time smoothed over about half a second: the raw number flickers too much to read, and the
  // point of the counter is to notice a map that costs 30 ms, not to watch it jitter.
  let smoothedMs = 16.7;
  let lastShown = 0;
  const frame = (): void => {
    const dt = Math.min(clock.getDelta(), 0.1);     // a backgrounded tab must not teleport the camera
    fly.update(dt);
    view?.faceCamera(fly.camera);   // the flares turn before the frame is drawn, not after
    render(scene, fly.camera);

    if (dt > 0) {
      smoothedMs += (dt * 1000 - smoothedMs) * 0.08;
      const now = performance.now();
      if (now - lastShown > 200) {                  // redrawing text every frame is itself a cost
        lastShown = now;
        ui.setFps(1000 / smoothedMs, smoothedMs);
      }
    }
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
  // The map's own fog, before the world is built: `cameras/camera` in its `MP*.ZED` carries the
  // colour, the range and the enable bit the level was authored with. Two of the twenty-two ship
  // with it off, so the bit is honoured rather than the range being used as a proxy for it.
  if (map.camera) {
    fog.enabled = map.camera.fogEnabled;
    fog.near = map.camera.fogNear;
    fog.far = map.camera.fogFar;
    fog.color = [...map.camera.fogColor];
    fogIsMine = false;                          // the new map's own fog, until a slider says otherwise
    ui.setFog(fog.near, fog.far, fog.color);
    ui.setFogEnabled(fog.enabled);
  }
  view = buildWorld(map);
  scene.add(view.group);
  // A map with no `cameras/camera` key takes a range off its own size rather than the last map's.
  if (!map.camera) {
    Object.assign(fog, fogForExtent(view.box.min.distanceTo(view.box.max)));
    fogIsMine = false;                          // the fallback is the map's too, until a slider moves
    ui.setFog(fog.near, fog.far, fog.color);
  }
  overlays.place(view.box);
  overlays.placeCollision(map.collision);
  // 36 section 6: spawns are not on the disc. `@s2u/scene` holds the measured table, keyed by the name
  // `mission.rdr` shows, which is the name this map was just loaded under.
  const spawn: Spawns | undefined = spawnsFor(map.name);
  overlays.placeSpawns(spawn ?? null);
  // A new world starts in whatever state the panel is showing, not in the state it was built in.
  ui.apply(applyToggle);
  ui.applySliders(applySlider);   // a freshly built world starts at the panel's settings, not the defaults
  refreshFog();
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
  chromeHidden: () => ui.chromeHidden(),
  sliders: () => ui.sliderValues(),
} satisfies ViewerHook;
