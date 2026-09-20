import { describe, it, expect } from 'vitest';
import { walkChain, walkModel, modelNodes } from '../src/dma';
import { parseZdb, zdbMember, Zar } from '@s2u/archive';
import { fixture } from '../../archive/test/fixtures';

/** A model buffer holding one chain at `headerOffset`, built from 16-byte quadwords. */
function chainBuffer(quadwords: number[][], headerOffset: number, size: number): Uint8Array {
  const buf = new Uint8Array(size);
  const view = new DataView(buf.buffer);
  quadwords.forEach((qw, i) => qw.forEach((w, j) => view.setUint32(headerOffset + 16 * i + 4 * j, w, true)));
  return buf;
}
const tagWord = (id: number, reloc: number, qwc: number) => (id << 28) | (reloc << 16) | qwc;

describe('walkChain', () => {
  it('assembles the tag-transfer codes and the quadwords each tag transfers', () => {
    // A 3-tag chain: a texture citation, a ref to data at 0x10, and a cnt whose data follows the tag.
    const buf = chainBuffer([
      [3, 0, 0, 0],                                      // count quadword: 3 tags
      [tagWord(1, 6, 0), 0x10, 0, 0],                    // cnt/reloc 6: the texture name at 0x10
      [tagWord(3, 2, 1), 0x30, 0xaaaaaaaa, 0xbbbbbbbb],  // ref: 1 quadword at 0x30
      [tagWord(1, 2, 1), 0, 0xcccccccc, 0xdddddddd],     // cnt: 1 quadword following the tag
      [0x11111111, 0x22222222, 0x33333333, 0x44444444],  // ... which is this one
    ], 0x40, 0x100);
    buf.set(new TextEncoder().encode('cuba1a_sky01.tif\0'), 0x10);
    buf.fill(0x5a, 0x30, 0x40);

    const chain = walkChain(buf, 0x40, 'N000_000');
    expect(chain.nodeName).toBe('N000_000');
    expect(chain.tags.map((t) => [t.id, t.reloc, t.qwc, t.addr, t.tagOffset]))
      .toEqual([[1, 6, 0, 0x10, 0x50], [3, 2, 1, 0x30, 0x60], [1, 2, 1, 0, 0x70]]);
    expect(chain.textureName).toBe('cuba1a_sky01.tif');
    expect(chain.textureNames).toEqual(['cuba1a_sky01.tif']);
    // 8 bytes of codes + the ref quadword, then 8 more bytes of codes + the cnt quadword. No bytes for the
    // texture tag, and the quadword the cnt transferred is not walked as a tag.
    expect([...chain.vif]).toEqual([
      0xaa, 0xaa, 0xaa, 0xaa, 0xbb, 0xbb, 0xbb, 0xbb, ...new Array(16).fill(0x5a),
      0xcc, 0xcc, 0xcc, 0xcc, 0xdd, 0xdd, 0xdd, 0xdd, 0x11, 0x11, 0x11, 0x11,
      0x22, 0x22, 0x22, 0x22, 0x33, 0x33, 0x33, 0x33, 0x44, 0x44, 0x44, 0x44,
    ]);
  });

  it('throws naming the id and the tag offset on a DMA id no model chain uses', () => {
    const buf = chainBuffer([[1, 0, 0, 0], [tagWord(2, 2, 0), 0, 0, 0]], 0, 0x40);
    expect(() => walkChain(buf, 0, 'N000_000')).toThrow(/DMA id 2 \(next\)/);
    expect(() => walkChain(buf, 0, 'N000_000')).toThrow(/tag at 0x10/);
  });

  it('throws when a ref address runs past the model buffer', () => {
    const buf = chainBuffer([[1, 0, 0, 0], [tagWord(3, 2, 4), 0x30, 0, 0]], 0, 0x40);
    expect(() => walkChain(buf, 0, 'N000_000')).toThrow(/outside the 64-byte model buffer/);
  });
});

describe('walkModel', () => {
  const mp2 = fixture('RUN/MP2.ZDB');
  it.skipIf(!mp2)('Frostfire worldmodel: 123 chains, 1,450 tags, reloc types {2,3,4,6}, 37 distinct texture names, first chunk cites cuba1a_sky01.tif', () => {
    const toc = parseZdb(mp2!);
    const worl = Zar.parse(zdbMember(mp2!, toc, 'WORL_MDL.ZED'));
    const world = worl.find('worldmodel')!;
    const chains = walkModel(worl.data(world), modelNodes(worl, world));
    expect(chains.length).toBe(123);
    expect(chains.reduce((n, c) => n + c.tags.length, 0)).toBe(1450);
    const relocs = new Set(chains.flatMap((c) => c.tags.map((t) => t.reloc)));
    expect([...relocs].sort()).toEqual([2, 3, 4, 6]);
    expect(chains[0]!.textureName).toBe('cuba1a_sky01.tif');
    // A chunk cites one texture per sub-packet, not one per chain: 309 citations over the 123 chunks, 37
    // distinct names (36 §3). Only 13 chunks differ in their *first* texture, so the 37 are the union.
    expect(chains.reduce((n, c) => n + c.textureNames.length, 0)).toBe(309);
    expect(new Set(chains.flatMap((c) => c.textureNames)).size).toBe(37);
    for (const c of chains) expect(c.vif.byteLength % 4).toBe(0);
  });
});
