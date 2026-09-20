import { MathUtils, PerspectiveCamera, Vector3 } from 'three';

/** A camera pose in the game's world frame: position in game units, yaw and pitch in degrees. */
export interface Pose { x: number; y: number; z: number; yaw: number; pitch: number }

/** Metres a second at a walk; the fly speed is this divided by `MetersPerUnit` to get game units. */
const METRES_PER_SECOND = 12;
/** Shift multiplies it: crossing a 100 m map end to end takes about two seconds. */
const SPRINT = 5;
/** Radians of look per pixel of drag. */
const LOOK = 0.0028;
/** Straight up and straight down are singular for a yaw/pitch camera, so stop just short. */
const PITCH_LIMIT = MathUtils.degToRad(89.9);

/**
 * A fly camera in the game's world frame (y up, right-handed, SEMANTICS section 8): WASD along the view,
 * Q and E straight down and up, shift for speed, drag to look. Yaw and pitch are kept here rather than
 * read back off the camera's quaternion, so the debug hook can set an exact pose.
 */
export class FlyCamera {
  readonly camera: PerspectiveCamera;
  private yaw = 0;
  private pitch = 0;
  private readonly keys = new Set<string>();
  private dragging: number | null = null;
  private lastX = 0;
  private lastY = 0;
  /** Game units a second at the map's scale; `setScale` adjusts it when a map states its own. */
  private speed = METRES_PER_SECOND / 0.1;

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.camera = new PerspectiveCamera(65, 1, 1, 40000);
    this.camera.rotation.order = 'YXZ';       // yaw about y, then pitch about the new x
    canvas.addEventListener('pointerdown', this.onPointerDown);
    canvas.addEventListener('pointermove', this.onPointerMove);
    canvas.addEventListener('pointerup', this.onPointerUp);
    canvas.addEventListener('pointercancel', this.onPointerUp);
    globalThis.addEventListener('keydown', this.onKeyDown);
    globalThis.addEventListener('keyup', this.onKeyUp);
    globalThis.addEventListener('blur', this.onBlur);
  }

  /** `MetersPerUnit` from the map: the fly speed is a walking pace in metres, whatever the unit is. */
  setScale(metersPerUnit: number): void {
    this.speed = METRES_PER_SECOND / (metersPerUnit > 0 ? metersPerUnit : 0.1);
  }

  setAspect(aspect: number): void {
    this.camera.aspect = aspect;
    this.camera.updateProjectionMatrix();
  }

  /** Stand at `from` (game units) and face `to`. */
  lookFrom(from: readonly [number, number, number], to: readonly [number, number, number]): void {
    const [dx, dy, dz] = [to[0] - from[0], to[1] - from[1], to[2] - from[2]];
    const flat = Math.hypot(dx, dz);
    this.setPose({
      x: from[0], y: from[1], z: from[2],
      yaw: MathUtils.radToDeg(Math.atan2(-dx, -dz)),   // the camera looks down its own -z
      pitch: MathUtils.radToDeg(Math.atan2(dy, flat)),
    });
  }

  setPose(pose: Partial<Pose>): void {
    const now = this.pose();
    this.camera.position.set(pose.x ?? now.x, pose.y ?? now.y, pose.z ?? now.z);
    this.yaw = MathUtils.degToRad(pose.yaw ?? now.yaw);
    this.pitch = MathUtils.clamp(MathUtils.degToRad(pose.pitch ?? now.pitch), -PITCH_LIMIT, PITCH_LIMIT);
    this.apply();
  }

  pose(): Pose {
    const p = this.camera.position;
    return { x: p.x, y: p.y, z: p.z, yaw: MathUtils.radToDeg(this.yaw), pitch: MathUtils.radToDeg(this.pitch) };
  }

  /** One frame of movement. `dt` is seconds, so held keys move the same distance on any refresh rate. */
  update(dt: number): void {
    const forward = new Vector3(0, 0, -1).applyEuler(this.camera.rotation);
    const right = new Vector3().crossVectors(forward, new Vector3(0, 1, 0)).normalize();
    const move = new Vector3();
    if (this.keys.has('keyw')) move.add(forward);
    if (this.keys.has('keys')) move.sub(forward);
    if (this.keys.has('keyd')) move.add(right);
    if (this.keys.has('keya')) move.sub(right);
    if (this.keys.has('keye')) move.y += 1;
    if (this.keys.has('keyq')) move.y -= 1;
    if (move.lengthSq() === 0) return;
    const fast = this.keys.has('shiftleft') || this.keys.has('shiftright') ? SPRINT : 1;
    this.camera.position.addScaledVector(move.normalize(), this.speed * fast * dt);
  }

  private apply(): void {
    this.camera.rotation.set(this.pitch, this.yaw, 0, 'YXZ');
  }

  private readonly onPointerDown = (e: PointerEvent): void => {
    if (this.dragging !== null) return;
    this.dragging = e.pointerId;
    this.lastX = e.clientX;
    this.lastY = e.clientY;
    this.canvas.setPointerCapture(e.pointerId);
  };

  private readonly onPointerMove = (e: PointerEvent): void => {
    if (this.dragging !== e.pointerId) return;
    this.yaw -= (e.clientX - this.lastX) * LOOK;
    this.pitch = MathUtils.clamp(this.pitch - (e.clientY - this.lastY) * LOOK, -PITCH_LIMIT, PITCH_LIMIT);
    this.lastX = e.clientX;
    this.lastY = e.clientY;
    this.apply();
  };

  private readonly onPointerUp = (e: PointerEvent): void => {
    if (this.dragging !== e.pointerId) return;
    this.dragging = null;
    if (this.canvas.hasPointerCapture(e.pointerId)) this.canvas.releasePointerCapture(e.pointerId);
  };

  /** `code`, not `key`: WASD stays where it is on an AZERTY keyboard, and shift does not rename letters. */
  private readonly onKeyDown = (e: KeyboardEvent): void => {
    if (e.target instanceof HTMLElement && (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT')) return;
    this.keys.add(e.code.toLowerCase());
  };

  private readonly onKeyUp = (e: KeyboardEvent): void => {
    this.keys.delete(e.code.toLowerCase());
  };

  /** A key held while the page loses focus never sends its keyup, and the camera would drift forever. */
  private readonly onBlur = (): void => {
    this.keys.clear();
  };
}
