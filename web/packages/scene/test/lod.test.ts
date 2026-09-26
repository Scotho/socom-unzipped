import { describe, expect, it } from 'vitest';
import { farLodModels } from '../src/lod';
import type { RdrNode } from '@s2u/archive';

/**
 * `lod.rdr` as Frostfire ships it (`READERM.ZAR`), trimmed: bands with fade ranges, and lists of the
 * models in each. The near copies start at 0; the far copies start further out and are the ones the
 * viewer hides, because the graph places both at the same spot.
 */
const FROSTFIRE: RdrNode = [[
  'LOD_Definititions', [
    ['midgrate', 'nearFade', ['0', '0'], 'farFade', ['360', '360']],
    ['lowgrate', 'nearFade', ['260', '260'], 'farFade', ['500', '500']],
    ['railings_high', 'nearFade', ['0', '0'], 'farFade', ['100', '120']],
    ['railings_low', 'nearFade', ['100', '120'], 'farFade', ['420', '440']],
    ['furniture', 'nearFade', ['0', '0'], 'farFade', ['250', '260']],
  ],
  'LOD_Connection', [
    ['LODTYPE1', 'midgrate', 'ObjectList', ['grate_midlod']],
    ['LODTYPE1', 'lowgrate', 'ObjectList', ['grate_lowlod']],
    ['LODTYPE1', 'railings_high', 'ObjectList', ['railstraithi1', 'railcornerhi1']],
    ['LODTYPE1', 'railings_low', 'ObjectList', ['railstraitlo1', 'railcornerlo1', 'tankrailbarslo']],
    ['LODTYPE1', 'furniture', 'ObjectList', ['chair_office']],
  ],
]];

describe('farLodModels', () => {
  it('names the models in a band that fades in above zero, and none from a band that starts at zero', () => {
    expect([...farLodModels(FROSTFIRE)].sort()).toEqual(['grate_lowlod', 'railcornerlo1', 'railstraitlo1', 'tankrailbarslo']);
  });

  it('is empty for a record with no LOD lists, and for one that is not a record at all', () => {
    expect(farLodModels([['LOD_Definititions', []]]).size).toBe(0);
    expect(farLodModels('nothing').size).toBe(0);
    expect(farLodModels([]).size).toBe(0);
  });

  it('ignores a connection whose band was never defined', () => {
    const rdr: RdrNode = [['LOD_Definititions', [], 'LOD_Connection', [['LODTYPE1', 'ghost', 'ObjectList', ['x']]]]];
    expect(farLodModels(rdr).size).toBe(0);
  });
});
