/**
 * Where the viewer's archive bytes come from. Paths are archive-relative and always use forward slashes
 * ("RUN/MP2.ZDB"), so the same index code runs over a served directory in the browser and over the disc
 * tree copied into `public/maps` in node.
 */
export interface AssetSource {
  list(): Promise<string[]>;
  read(path: string): Promise<Uint8Array>;
}
