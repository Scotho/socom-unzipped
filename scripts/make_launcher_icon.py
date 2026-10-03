#!/usr/bin/env python3
"""Sprint 18 T9: the launcher's Windows icon (socom_unzipped.ico) from the project's own crest PNG.

    python scripts/make_launcher_icon.py third_party/ps2recomp/ps2xLauncher/assets/logo/socom_unzipped_icon.png \
        --out third_party/ps2recomp/ps2xLauncher/assets/logo/socom_unzipped.ico

One square RGBA source; one entry per size in --sizes (default 16 24 32 48 64), each a LANCZOS downscale of the
source. A size larger than the source is refused, never upscaled (the crest is 64x64; the wide logo is not square,
so the .ico stops at 64). The entries are uncompressed 32-bit DIBs with their AND mask (set where alpha is 0), so
the output depends on Pillow's resampler alone -- no zlib -- and is byte-for-byte reproducible:
tools_py/tests/test_launcher_icon.py regenerates it and compares it to the tracked file.
The .ico is linked into socom_unzipped_launcher.exe by ps2xLauncher/launcher.rc.
"""
import argparse
import struct
import sys

from PIL import Image

DEFAULT_SIZES = [16, 24, 32, 48, 64]


def dib_entry(img):
    """A 32-bit BITMAPINFOHEADER DIB of an RGBA image, bottom-up BGRA, then the 1-bit AND mask."""
    w, h = img.size
    px = img.tobytes()   # RGBA, top-down
    xor = bytearray()
    for y in range(h - 1, -1, -1):
        row = px[y * w * 4:(y + 1) * w * 4]
        for x in range(w):
            r, g, b, a = row[x * 4:x * 4 + 4]
            xor += bytes((b, g, r, a))
    stride = ((w + 31) // 32) * 4
    mask = bytearray()
    for y in range(h - 1, -1, -1):
        bits = bytearray(stride)
        for x in range(w):
            if px[(y * w + x) * 4 + 3] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        mask += bits
    header = struct.pack("<IiiHHIIiiII", 40, w, 2 * h, 1, 32, 0, len(xor) + len(mask), 0, 0, 0, 0)
    return header + bytes(xor) + bytes(mask)


def make_ico(src, sizes):
    img = Image.open(src)
    img.load()
    img = img.convert("RGBA")
    if img.width != img.height:
        raise ValueError("%s is %dx%d: the icon source must be square" % (src, img.width, img.height))
    entries = []
    for s in sorted(set(sizes)):
        if s > img.width:
            raise ValueError("size %d is larger than the %dx%d source: not upscaled" % (s, img.width, img.height))
        if s > 256:
            raise ValueError("size %d: an .ico entry is at most 256" % s)
        frame = img if s == img.width else img.resize((s, s), Image.Resampling.LANCZOS)
        entries.append((s, dib_entry(frame)))
    out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    offset = 6 + 16 * len(entries)
    for s, blob in entries:
        dim = 0 if s == 256 else s
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    for _s, blob in entries:
        out += blob
    return bytes(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", help="the square RGBA PNG (ps2xLauncher/assets/logo/socom_unzipped_icon.png)")
    ap.add_argument("--out", required=True, help="the .ico to write")
    ap.add_argument("--sizes", type=int, nargs="+", default=DEFAULT_SIZES, help="entry sizes in pixels")
    args = ap.parse_args(argv)
    try:
        data = make_ico(args.source, args.sizes)
    except ValueError as e:
        sys.stderr.write("make_launcher_icon: %s\n" % e)
        return 2
    with open(args.out, "wb") as f:
        f.write(data)
    sys.stderr.write("make_launcher_icon: %s -> %s (%d bytes, sizes %s)\n"
                     % (args.source, args.out, len(data), " ".join(str(s) for s in sorted(set(args.sizes)))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
