import type { RdrNode } from '@s2u/archive';

/**
 * The map's level-of-detail table, `READERM.ZAR/lod.rdr`, read for the one thing a viewer needs: which
 * models are the *far* copies.
 *
 * The record is two lists. `LOD_Definititions` (sic) names bands, each with a `nearFade` and a
 * `farFade` pair of distances; `LOD_Connection` puts model names into a band through an
 * `ObjectList`. Frostfire: `railings_high` fades in at 0 and out at 100-120, `railings_low` fades in
 * at 100-120 and out at 420-440, and the graph places *both* sets of railings at the same spot. The
 * engine (`CVisual::DrawLOD`) shows one or the other by camera range; drawn together they z-fight.
 *
 * A model in a band whose `nearFade` starts above zero is a far copy and is what this returns. A
 * band that starts at zero is the near copy, and a model in no band is always drawn.
 */
export function farLodModels(rdr: RdrNode): Set<string> {
  const far = new Set<string>();
  const nearFadeOf = new Map<string, number>();
  const list = (node: RdrNode, key: string): RdrNode[] => {
    if (!Array.isArray(node)) return [];
    const at = node.indexOf(key);
    const value = at >= 0 ? node[at + 1] : undefined;
    return Array.isArray(value) ? value : [];
  };
  const root = Array.isArray(rdr) && rdr.length === 1 && Array.isArray(rdr[0]) ? rdr[0] : rdr;
  for (const band of list(root, 'LOD_Definititions')) {
    if (!Array.isArray(band) || typeof band[0] !== 'string') continue;
    const near = list(band, 'nearFade');
    const start = typeof near[0] === 'string' ? Number(near[0]) : 0;
    nearFadeOf.set(band[0], Number.isFinite(start) ? start : 0);
  }
  for (const link of list(root, 'LOD_Connection')) {
    if (!Array.isArray(link)) continue;
    // `["LODTYPE1", "<band>", "ObjectList", [...names]]`: the band is the string before `ObjectList`.
    const at = link.indexOf('ObjectList');
    const band = at >= 1 ? link[at - 1] : undefined;
    if (typeof band !== 'string' || (nearFadeOf.get(band) ?? 0) <= 0) continue;
    for (const name of list(link, 'ObjectList')) if (typeof name === 'string') far.add(name);
  }
  return far;
}
