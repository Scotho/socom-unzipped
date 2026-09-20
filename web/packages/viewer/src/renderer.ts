import type { Camera, Scene } from 'three';
import { WebGPURenderer } from 'three/webgpu';

/** Which GPU API the pictures actually came out of, for the status line and the screenshot record. */
export type Backend = 'webgpu' | 'webgl2';

export interface ViewerRenderer {
  renderer: WebGPURenderer;
  backend: Backend;
  render(scene: Scene, camera: Camera): void;
  resize(width: number, height: number): void;
}

/** three's own backend flag. The base `Backend` type does not carry it, so it is read through this shape. */
interface BackendFlags { isWebGPUBackend?: boolean }

const BACKGROUND = 0x14161a;

/**
 * three's `WebGPURenderer`, which picks WebGPU when the browser offers an adapter and falls back to WebGL2
 * on its own otherwise -- headless Chromium usually lands on WebGL2 through SwiftShader. The viewer asks
 * for nothing WebGPU-specific, so the two paths draw the same scene; only the reported backend differs.
 */
export async function createRenderer(canvas: HTMLCanvasElement): Promise<ViewerRenderer> {
  const renderer = new WebGPURenderer({ canvas, antialias: true, forceWebGL: false });
  await renderer.init();
  renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio, 2));
  renderer.setClearColor(BACKGROUND, 1);
  const backend: Backend = (renderer.backend as BackendFlags).isWebGPUBackend === true ? 'webgpu' : 'webgl2';
  return {
    renderer,
    backend,
    render: (scene, camera) => renderer.render(scene, camera),
    resize: (width, height) => renderer.setSize(width, height, false),
  };
}
