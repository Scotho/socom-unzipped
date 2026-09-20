import { AxesHelper, Box3, GridHelper, Scene, Vector3 } from 'three';

/** Frostfire's playable floor is y = 100; the grid sits there so heights read against something known. */
const GRID_Y = 100;
/** Game units: 100 units is 10 m at `MetersPerUnit` 0.1, so a square is a room. */
const GRID_STEP = 100;
const AXES_LENGTH = 300;

/**
 * The two reference objects the viewer draws on top of a map: a grid at the floor height and the world
 * axes at the origin. Both are off the critical path -- nothing here reads map data.
 */
export class Overlays {
  private grid: GridHelper | null = null;
  private readonly axes = new AxesHelper(AXES_LENGTH);

  constructor(private readonly scene: Scene) {
    this.axes.visible = true;
    scene.add(this.axes);
  }

  /** Re-sizes the grid to the map that is now loaded and centres it on that map. */
  place(box: Box3): void {
    const visible = this.grid?.visible ?? false;
    if (this.grid) {
      this.scene.remove(this.grid);
      this.grid.geometry.dispose();
    }
    const size = box.isEmpty() ? 2000 : Math.max(box.max.x - box.min.x, box.max.z - box.min.z);
    const span = Math.ceil(size / GRID_STEP) * GRID_STEP;
    const centre = box.isEmpty() ? new Vector3() : box.getCenter(new Vector3());
    this.grid = new GridHelper(span, Math.max(1, span / GRID_STEP), 0x5a6472, 0x323a45);
    this.grid.position.set(centre.x, GRID_Y, centre.z);
    this.grid.visible = visible;
    this.scene.add(this.grid);
  }

  setGrid(visible: boolean): void {
    if (this.grid) this.grid.visible = visible;
  }

  setAxes(visible: boolean): void {
    this.axes.visible = visible;
  }
}
