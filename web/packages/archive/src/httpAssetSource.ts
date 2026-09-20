import type { AssetSource } from './assetSource';

/**
 * An `AssetSource` over a served directory: the disc tree under `baseUrl`, with an `index.json`
 * beside it listing every archive-relative path. The trailing slash on `baseUrl` is optional.
 */
export class HttpAssetSource implements AssetSource {
  private readonly base: string;

  constructor(baseUrl: string) {
    this.base = baseUrl.replace(/\/+$/, '');
  }

  async list(): Promise<string[]> {
    return (await this.get('index.json')).json() as Promise<string[]>;
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
