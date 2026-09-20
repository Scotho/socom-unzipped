import { describe, it, expect } from 'vitest';
import { parseZdb, zdbMember } from '../src/zdb';
import { fixture, FIXTURES_ABSENT } from './fixtures';

function syntheticZdb(): Uint8Array {
  // 36 §1: 0xA0 header, count @0x98, entrySize=0x5C @0x9C, 92-byte entries from 0xA0, data 2048-aligned.
  const entries = [{ name: 'RUN\MP\MP2\A.ZED', data: [1, 2, 3] }, { name: 'RUN\COMMON\B.ZAR', data: [9] }];
  const dataStart = 2048;
  const out = new Uint8Array(dataStart + 2048 * entries.length);
  const dv = new DataView(out.buffer);
  dv.setUint32(0x98, entries.length, true);
  dv.setUint32(0x9c, 0x5c, true);
  entries.forEach((e, i) => {
    const o = 0xa0 + i * 0x5c;
    dv.setUint32(o, 0x5c, true);
    for (let k = 0; k < e.name.length; k++) out[o + 4 + k] = e.name.charCodeAt(k);
    dv.setUint32(o + 68, dataStart + i * 2048, true);
    dv.setUint32(o + 72, e.data.length, true);
    out.set(e.data, dataStart + i * 2048);
  });
  return out;
}

describe('parseZdb', () => {
  it('reads the TOC of a synthetic archive', () => {
    const z = parseZdb(syntheticZdb());
    expect(z).toEqual([
      { name: 'RUN\MP\MP2\A.ZED', offset: 2048, size: 3 },
      { name: 'RUN\COMMON\B.ZAR', offset: 4096, size: 1 },
    ]);
    expect(Array.from(zdbMember(syntheticZdb(), z, 'a.zed'))).toEqual([1, 2, 3]);
    expect(() => zdbMember(syntheticZdb(), z, 'nope')).toThrow(/nope/);
  });
  it('rejects a header without the 0x5C entry size', () => {
    const bad = syntheticZdb(); new DataView(bad.buffer).setUint32(0x9c, 0x60, true);
    expect(() => parseZdb(bad)).toThrow(/entrySize/);
  });
  const mp2 = fixture('RUN/MP2.ZDB');
  it.skipIf(!mp2)('Frostfire has 53 members, all 2048-aligned, and MP2_GEO.ZED is 445,856 bytes', () => {
    const z = parseZdb(mp2!);
    expect(z.length).toBe(53);
    for (const e of z) expect(e.offset % 2048).toBe(0);
    expect(zdbMember(mp2!, z, 'MP2_GEO.ZED').byteLength).toBe(445_856);
  });
});
