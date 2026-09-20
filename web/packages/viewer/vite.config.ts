import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const here = fileURLToPath(new URL('.', import.meta.url));

/**
 * The viewer is its own Vite root inside the workspace. `publicDir` points at `web/public`, so the
 * extracted disc tree served at `/maps/` is the app's default `AssetSource` without a copy.
 */
/**
 * `VIEWER_BASE` is the path the built site is served under (`/map-viewer/` on s2u.scotho.com); the dev server
 * and the default build use `/`. The extracted maps are never copied into the build: on a server they are a
 * separate directory mounted beside the site (see sites/s2u in the scotho repository), in dev Vite serves
 * `web/public` itself.
 */
export default defineConfig({
  root: here,
  base: process.env.VIEWER_BASE ?? '/',
  publicDir: fileURLToPath(new URL('../../public', import.meta.url)),
  server: { port: 5173, strictPort: true },
  build: { outDir: fileURLToPath(new URL('../../dist/viewer', import.meta.url)), emptyOutDir: true, copyPublicDir: false },
  worker: { format: 'es' },
});
