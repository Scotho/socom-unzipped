#!/usr/bin/env python
"""Extract a member (default eeMemory.bin) from a PCSX2 .p2s savestate: a zip whose entries use
compression method 93 (zstd), which Python's zipfile cannot open on its own.

Usage: python -m tools_py.parity.p2s_extract <state.p2s> <out.bin> [member]
"""
import struct
import sys
import zipfile

import zstandard


def main():
    path, out = sys.argv[1], sys.argv[2]
    member = sys.argv[3] if len(sys.argv) > 3 else "eeMemory.bin"
    z = zipfile.ZipFile(path)
    info = z.getinfo(member)
    with open(path, "rb") as f:
        f.seek(info.header_offset)
        hdr = f.read(30)
        sig, _, _, method, _, _, _, csize, usize, nlen, elen = struct.unpack("<IHHHHHIIIHH", hdr)
        assert sig == 0x04034B50
        f.seek(info.header_offset + 30 + nlen + elen)
        raw = f.read(info.compress_size)
    if info.compress_type == 93:
        data = zstandard.ZstdDecompressor().decompressobj().decompress(raw)
    elif info.compress_type == 0:
        data = raw
    else:
        data = z.read(member)
    open(out, "wb").write(data)
    print(f"{member}: {len(data)} bytes -> {out}")


if __name__ == "__main__":
    main()
