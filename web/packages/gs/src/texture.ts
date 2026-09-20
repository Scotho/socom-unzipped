import { Reader } from '@s2u/archive';
import { decodeTex0, TEXTURE_PSM, type Tex0 } from './tex0';

/** One `textures/<name>.tif/texdat` key, read exactly as `CTexture::Read` reads it (36 §5). */
export interface TextureRecord {
  name: string;
  width: number; height: number;
  size: number;                 // pixel bytes; always w * height * bpp / 8
  gsaddr: number;               // GS TBP0 in 64-word blocks, assigned by the exporter
  bpp: number;                  // m_texelBitSize
  selectQwc: number; palOffset: number;
  transparent: boolean; palettized: boolean; isMipChild: boolean; bumpmap: boolean;
  bilinear: boolean; transp1bit: boolean; dynamic: boolean; context: boolean;
  pixels: Uint8Array;
  tex0: Tex0 | null;            // recovered from the record's own bind packet; null when it holds none
}

const HEADER = 16;              // 36 §5: TEXTURE_PARAMS is 16 bytes
const BIND_QWC = 9;             // 36 §5: a 144-byte, 9-quadword prebuilt bind packet follows the pixels

/**
 * TEXTURE_PARAMS then the pixels then the bind packet (36 §5):
 * `u16 w; u16 h; u32 size; u32 gsaddr; u32 { texelBitSize:8, selectQwc:8, pal_offset:8, 8x 1-bit flags }`.
 */
export function parseTextureRecord(name: string, texdat: Uint8Array): TextureRecord {
  const r = new Reader(texdat);
  const width = r.u16(0);       // 36 §5
  const height = r.u16(2);      // 36 §5
  const size = r.u32(4);        // 36 §5
  const gsaddr = r.u32(8);      // 36 §5
  const flags = r.u32(12);      // 36 §5
  const bpp = flags & 0xff;                       // 36 §5: m_texelBitSize, bits 0-7
  const selectQwc = (flags >>> 8) & 0xff;         // 36 §5: m_selectQwc, bits 8-15
  const palOffset = (flags >>> 16) & 0xff;        // 36 §5: m_pal_offset, bits 16-23
  const bit = (n: number): boolean => ((flags >>> (24 + n)) & 1) === 1;  // 36 §5: eight 1-bit flags from bit 24
  return {
    name, width, height, size, gsaddr, bpp, selectQwc, palOffset,
    transparent: bit(0), palettized: bit(1), isMipChild: bit(2), bumpmap: bit(3),
    bilinear: bit(4), transp1bit: bit(5), dynamic: bit(6), context: bit(7),
    pixels: r.slice(HEADER, size),                // 36 §5: pixels follow the header immediately
    tex0: findTex0(r, HEADER + size, gsaddr, width, height),
  };
}

/**
 * The bind packet's words are VU1 parameters and one GS TEX0 register value. The TEX0 word is the one
 * whose PSM names a texture format, whose TBP0 is this texture's own gsaddr, and whose TW and TH are the
 * log2 of this texture's own width and height (36 §5). The size agreement is what keeps a small VU1
 * parameter word out: `0x...000e` alone reads as PSMCT32 at TBP0 14, and three Frostfire textures sit at
 * exactly those addresses.
 */
function findTex0(r: Reader, at: number, gsaddr: number, width: number, height: number): Tex0 | null {
  const end = Math.min(at + BIND_QWC * 16, r.length);
  for (let o = at; o + 8 <= end; o += 8) {        // each quadword's low u64 then its high u64
    const t = decodeTex0(r.u64(o));
    if (TEXTURE_PSM.has(t.psm) && t.tbp0 === gsaddr && 1 << t.tw === width && 1 << t.th === height) return t;
  }
  return null;
}
