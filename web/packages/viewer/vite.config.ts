import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const here = fileURLToPath(new URL('.', import.meta.url));

/**
 * The viewer is its own Vite root inside the workspace. `publicDir` points at `web/public`, so the
 * extracted disc tree served at `/maps/` is the app's default `AssetSource` without a copy.
 */
export default defineConfig({
  root: here,
  publicDir: fileURLToPath(new URL('../../public', import.meta.url)),
  server: { port: 5173, strictPort: true },
  build: { outDir: fileURLToPath(new URL('../../dist/viewer', import.meta.url)), emptyOutDir: true },
  worker: { format: 'es' },
});
