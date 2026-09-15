"""Is the motion pack (run/motion_p.zar -> DAT_00415e08) intact in an RDRAM image? An offline check, no run.

research/25 §8-§10: during the single-player mission load our sceGsExecLoadImage/StoreImage HLE multiplied the
libgraph block pointer by 8, so the game's seven-piece VRAM park/restore through the pack buffer aliased seven VRAM
regions onto two and wrote file chunks [6,5,6,5,6,5,6] over buffer chunks 0..6 (chunk 7, the 0x26a0-byte tail, lies
outside the 0x1c0000 the game moves). 48 of 87 clip descriptors then read garbage -> the single-player turn teleport.
The console image and our title-time image hold the identity map.

Usage:
    python -m tools_py.parity.motion_pack_check <image.rdram> [game/disc/RUN/MOTION_P.ZAR]
prints `chunk_map=[...] corrupt_chunks=<n> of <m>` and exits 1 when any chunk holds another chunk's bytes.

Method: the pack buffer is `*0x415e08` (size at 0x415e0c, 0x1c26a0 = file size - TOC 0x2d60); the file body is
MOTION_P.ZAR[0x2d60:]. Each 0x40000 buffer chunk is matched to the file chunk with the largest fraction of equal
bytes at the same in-chunk offset. Relocated pointers differ from the file uniformly by the buffer delta, so an intact
chunk still matches at well above the 0.5 floor (measured: > 0.9); a smeared chunk matches its source at the same
level and its own index near 0 (the key data are unrelated)."""
import struct
import sys

import numpy as np

CHUNK = 0x40000
PACK_PTR = 0x415E08          # DAT_00415e08: the pack's data buffer (guest address)
PACK_SIZE = 0x415E0C         # +0xcc of the pack object copy at 0x415d40: buffer size
TOC_BYTES = 0x2D60           # MOTION_P.ZAR: the TOC precedes the data section
MATCH_FLOOR = 0.5


def _chunks(data):
    return [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]


def chunk_map(buf, body):
    """For each CHUNK of `buf`, the index of the `body` chunk it matches best (-1 when nothing reaches MATCH_FLOOR)."""
    ours = _chunks(buf)
    theirs = _chunks(body)
    out = []
    for mine in ours:
        a = np.frombuffer(mine, dtype=np.uint8)
        best, best_score = -1, 0.0
        for j, ref in enumerate(theirs):
            n = min(len(a), len(ref))
            if n == 0:
                continue
            score = float((a[:n] == np.frombuffer(ref[:n], dtype=np.uint8)).mean())
            if score > best_score:
                best, best_score = j, score
        out.append(best if best_score >= MATCH_FLOOR else -1)
    return out


def corrupt_chunks(cmap):
    return sum(1 for i, j in enumerate(cmap) if j != i)


def check_image(rdram_path, zar_path):
    with open(rdram_path, "rb") as f:
        rdram = f.read()
    base = struct.unpack_from("<I", rdram, PACK_PTR)[0] & 0x1FFFFFF
    size = struct.unpack_from("<I", rdram, PACK_SIZE)[0]
    with open(zar_path, "rb") as f:
        body = f.read()[TOC_BYTES:]
    if size != len(body):
        raise ValueError(f"pack size {size:#x} at {PACK_SIZE:#x} != file body {len(body):#x}; wrong image or file")
    buf = rdram[base:base + size]
    cmap = chunk_map(buf, body)
    return {"image": rdram_path, "base": base, "size": size, "chunk_map": cmap,
            "corrupt_chunks": corrupt_chunks(cmap), "chunks": len(cmap)}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    zar = argv[1] if len(argv) > 1 else "game/disc/RUN/MOTION_P.ZAR"
    r = check_image(argv[0], zar)
    print(f"{r['image']}: base={r['base']:#x} size={r['size']:#x} chunk_map={r['chunk_map']} "
          f"corrupt_chunks={r['corrupt_chunks']} of {r['chunks']}")
    return 1 if r["corrupt_chunks"] else 0


if __name__ == "__main__":
    sys.exit(main())
