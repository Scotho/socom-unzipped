import type { AssetSource } from './assetSource';
import { mapArchiveId, type MapInfo } from './mapIndex';

/**
 * An `AssetSource` over a served directory: the disc tree under `baseUrl`, with an `index.json`
 * beside it listing every archive that was extracted. The trailing slash on `baseUrl` is optional.
 *
 * `index.json` is an array of `MapInfo` — `{ archive, path, name }` — written by `tools/extract-maps.ts`,
 * which reads each `mission.rdr` once at extraction time. That is the whole reason the name is in there:
 * naming the 22 maps from the archives themselves costs 224 MB of fetches, which is not a menu. An older
 * index that is a plain array of paths still loads; those entries carry no name, so the archive id stands in.
 */
export class HttpAssetSource implements AssetSource {
  private readonly base: string;

  constructor(baseUrl: string) {
    this.base = baseUrl.replace(/\/+$/, '');
  }

  async list(): Promise<string[]> {
    return (await this.maps()).map((m) => m.path);
  }

  /** Every map the served index names, ready for a picker. No archive is read. */
  async maps(): Promise<MapInfo[]> {
    const entries = (await (await this.get('index.json')).json()) as (string | MapInfo)[];
    return entries.map((entry) => {
      if (typeof entry !== 'string') return entry;
      const archive = mapArchiveId(entry) ?? entry;
      return { archive, path: entry, name: archive };
    });
  }

  async read(path: string): Promise<Uint8Array> {
    return new Uint8Array(await (await this.get(path)).arrayBuffer());
  }

  private async get(path: string): Promise<Response> {
    const response = await fetch(`${this.base}/${path}`);
    if (!response.ok) throw new Error(`HTTP ${response.status} ${path}`);
    return response;
  }
}
