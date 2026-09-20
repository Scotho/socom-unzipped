import { HttpAssetSource, listMaps, type AssetSource, type MapInfo } from '@s2u/archive';
import { loadMap, transferables, type LoadedMap } from './loadMap';

/**
 * The decode thread. A 12 MB archive, 416 VIF packets and 37 palettised textures are a few hundred
 * milliseconds of tight loops; done here the page keeps rendering and the camera keeps moving while a map
 * comes in. Everything it sends back travels in the transfer list, so nothing is copied.
 */

/** What the page asks of this worker. */
export type ViewerRequest =
  | { kind: 'index'; baseUrl: string }
  | { kind: 'load'; baseUrl: string; path: string };

/** What comes back. `error` carries the request that failed so the page can say what it was doing. */
export type ViewerResponse =
  | { kind: 'index'; maps: MapInfo[] }
  | { kind: 'map'; map: LoadedMap }
  | { kind: 'error'; doing: string; message: string };

/** Worker globals without pulling the WebWorker lib in beside the DOM one (they collide on `self`). */
const ctx = self as unknown as {
  postMessage(message: ViewerResponse, transfer?: Transferable[]): void;
  addEventListener(type: 'message', handler: (event: MessageEvent<ViewerRequest>) => void): void;
};

const sources = new Map<string, AssetSource>();
const sourceFor = (baseUrl: string): AssetSource => {
  const known = sources.get(baseUrl);
  if (known) return known;
  const made = new HttpAssetSource(baseUrl);
  sources.set(baseUrl, made);
  return made;
};

ctx.addEventListener('message', (event: MessageEvent<ViewerRequest>) => {
  const request = event.data;
  void (async () => {
    try {
      if (request.kind === 'index') {
        ctx.postMessage({ kind: 'index', maps: await listMaps(sourceFor(request.baseUrl)) });
      } else {
        const map = await loadMap(sourceFor(request.baseUrl), request.path);
        ctx.postMessage({ kind: 'map', map }, transferables(map));
      }
    } catch (e) {
      const doing = request.kind === 'index' ? 'listing the maps' : `loading ${request.path}`;
      ctx.postMessage({ kind: 'error', doing, message: e instanceof Error ? e.message : String(e) });
    }
  })();
});
