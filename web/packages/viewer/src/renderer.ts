import type { Camera, Scene } from 'three';
import { Color, LinearSRGBColorSpace, SRGBColorSpace } from 'three';
import { WebGPURenderer } from 'three/webgpu';

/** Which GPU API the pictures actually came out of, for the status line and the screenshot record. */
export type Backend = 'webgpu' | 'webgl2';

export interface ViewerRenderer {
  renderer: WebGPURenderer;
  backend: Backend;
  render(scene: Scene, camera: Camera): void;
  resize(width: number, height: number): void;
  /**
   * Whether the frame is converted on the way out. The GS wrote its 8-bit result straight to the
   * framebuffer, so matching it means the shader's product goes out unconverted; a linear-light
   * pipeline wants the sRGB encode instead. Pairs with `WorldView.setLinearLight`, which decides
   * whether the texel was decoded on the way in -- the two have to agree or the frame is converted
   * once and not twice, or twice and not once.
   */
  setLinearLight(on: boolean): void;
  /**
   * The background. reCOM clears to the fog colour (`zrndr_pipe.cpp:157`,
   * `zVid_ClearColor(camera->m_fog_color.xyz)`), so the horizon a map fades into is the same colour it
   * fades with; there is no separate sky colour, the sky is a textured dome.
   */
  setClearColor(rgb: [number, number, number]): void;
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
  renderer.outputColorSpace = LinearSRGBColorSpace;   // the GS space, matching the default in `world`
  renderer.setClearColor(BACKGROUND, 1);
  const backend: Backend = (renderer.backend as BackendFlags).isWebGPUBackend === true ? 'webgpu' : 'webgl2';
  return {
    renderer,
    backend,
    render: (scene, camera) => renderer.render(scene, camera),
    resize: (width, height) => renderer.setSize(width, height, false),
    setClearColor: ([r, g, b]) => {
      // setRGB on the working space, not setHex: FOGCOL is a raw register value and must not be decoded.
      renderer.setClearColor(new Color().setRGB(r / 255, g / 255, b / 255), 1);
    },
    setLinearLight: (on) => {
      renderer.outputColorSpace = on ? SRGBColorSpace : LinearSRGBColorSpace;
    },
  };
}
