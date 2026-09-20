import { Reader, type Zar } from '@s2u/archive';

/**
 * `MP*.ZED`, the world root: the handful of scalars a viewer needs out of the 33 keys `CSaveLoad::Load`
 * reads (`research/recom/src/gamez/zNode/node_saveload.cpp:236-341`, 36 section 2).
 */
export interface WorldRoot {
  /** `MetersPerUnit`, one f32; 0.1 on every map read so far (36 section 2). */
  metersPerUnit: number;
  /** `ShadowVector`, three f32. */
  shadowVector: [number, number, number];
  /** `NightMission`, one u32 used as a flag. */
  nightMission: boolean;
  /** `DefaultMaterial`, a NUL-terminated string; `METAL_THICK` on Frostfire. */
  defaultMaterial: string;
}

/** 36 section 2: the map's own `.ZED`, which every MP archive carries beside its `_GEO`. */
const DEFAULT_METERS_PER_UNIT = 0.1;

export function parseWorldRoot(zar: Zar): WorldRoot {
  const f32 = (name: string, at = 0): number | null => {
    const key = zar.find(name);
    return key && key.size >= at + 4 ? new Reader(zar.data(key)).f32(at) : null;
  };
  const shadow = zar.find('ShadowVector');
  const night = zar.find('NightMission');
  const material = zar.find('DefaultMaterial');
  const r = shadow && shadow.size >= 12 ? new Reader(zar.data(shadow)) : null;
  return {
    metersPerUnit: f32('MetersPerUnit') ?? DEFAULT_METERS_PER_UNIT,
    shadowVector: r ? [r.f32(0), r.f32(4), r.f32(8)] : [0, -1, 0],
    nightMission: night !== undefined && night.size >= 4 && new Reader(zar.data(night)).u32(0) !== 0,
    defaultMaterial: material ? new Reader(zar.data(material)).cstr(0, material.size) : '',
  };
}
