#!/usr/bin/env python
"""Turn a PCSX2 GS dump (.gs, the new 0xFFFFFFFF format) into the console-replay fixture that ps2x_tests'
'console GS dump replays ...' case reads (research/31 sections 11-12):

  <out>/packets.bin       [u32 path][u32 size][bytes] for every transfer of the first N frames (default 2)
  <out>/vram_initial.bin  the 4 MiB of GS memory inside the state blob
  <out>/reference.ppm     PCSX2's own screenshot from the dump header (P6, the alpha dropped)

Usage: python tools_py/gsdump_extract.py <dump.gs> <out dir> [--frames N]

The dump: magic 0xFFFFFFFF; u32 header size; nine u32 (state version, state size, serial offset, serial size, crc,
screenshot width, height, offset, size -- the offsets and the header size count from byte 8, after the magic and
the size); serial; screenshot as RGBA8; the GSState freeze (a fixed run of registers, the VRAM, a fixed tail);
8 KiB of privileged registers; then records: 0 = transfer (u8 path, u32 size, bytes), 1 = vsync (u8 field),
2 = FIFO read (u32 size), 3 = registers (8 KiB). The VRAM's place in the freeze is per state version and is
checked against the state size rather than searched for; the research note's "file offset 0x12c1df" is
8 + 0x12c02e + 0x1a9. An unknown version stops the script instead of guessing: a fixture cut at the wrong
offset would replay as garbage that still 'passes'.
"""
import argparse
import os
import struct
import sys

VRAM_SIZE = 4 * 1024 * 1024
STATE_REGS_BEFORE_VRAM = {9: 0x1a9}     # GSState::Freeze v9: 0x1a9 bytes of registers, m_vm8, an 0x54-byte tail
STATE_TAIL_AFTER_VRAM = {9: 0x54}
HEADER_BASE = 8                          # the header's offsets count from after the magic and the header size
REGISTERS_SIZE = 8192


class DumpFormatError(Exception):
    pass


def _records(data, off, frames):
    """Transfers of the first `frames` frames as (path, payload), and how many frames were closed by a vsync."""
    out, seen = [], 0
    n = len(data)
    while off < n and seen < frames:
        kind = data[off]
        if kind == 0:
            path = data[off + 1]
            size = struct.unpack_from("<I", data, off + 2)[0]
            if off + 6 + size > n:
                raise DumpFormatError("truncated transfer record at %#x" % off)
            out.append((path, data[off + 6:off + 6 + size]))
            off += 6 + size
        elif kind == 1:
            seen += 1
            off += 2
        elif kind == 2:
            off += 5
        elif kind == 3:
            off += 1 + REGISTERS_SIZE
        else:
            raise DumpFormatError("unknown record kind %d at %#x" % (kind, off))
    return out, seen


def extract(src, out, frames=2):
    with open(src, "rb") as fh:
        data = fh.read()
    if len(data) < 44 or struct.unpack_from("<I", data, 0)[0] != 0xFFFFFFFF:
        raise DumpFormatError("%s: not a new-format PCSX2 GS dump (magic)" % src)
    (header_size, version, state_size, _serial_off, _serial_size, _crc,
     shot_w, shot_h, shot_off, shot_size) = struct.unpack_from("<10I", data, 4)
    if version not in STATE_REGS_BEFORE_VRAM:
        raise DumpFormatError("%s: GS state version %d is not one this script knows (%s)"
                              % (src, version, ", ".join(str(v) for v in sorted(STATE_REGS_BEFORE_VRAM))))
    before, tail = STATE_REGS_BEFORE_VRAM[version], STATE_TAIL_AFTER_VRAM[version]
    if state_size != before + VRAM_SIZE + tail:
        raise DumpFormatError("%s: state size %#x is not %#x (version %d)"
                              % (src, state_size, before + VRAM_SIZE + tail, version))
    if shot_size != shot_w * shot_h * 4:
        raise DumpFormatError("%s: screenshot %ux%u does not fill %u bytes" % (src, shot_w, shot_h, shot_size))
    state_start = HEADER_BASE + header_size
    vram_start = state_start + before
    records_start = state_start + state_size + REGISTERS_SIZE
    if records_start > len(data):
        raise DumpFormatError("%s: shorter than its header says" % src)
    packets, seen = _records(data, records_start, frames)
    shot = data[HEADER_BASE + shot_off:HEADER_BASE + shot_off + shot_size]

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "vram_initial.bin"), "wb") as fh:
        fh.write(data[vram_start:vram_start + VRAM_SIZE])
    with open(os.path.join(out, "packets.bin"), "wb") as fh:
        for path, payload in packets:
            fh.write(struct.pack("<II", path, len(payload)))
            fh.write(payload)
    with open(os.path.join(out, "reference.ppm"), "wb") as fh:
        fh.write(b"P6\n%d %d\n255\n" % (shot_w, shot_h))
        fh.write(b"".join(shot[i:i + 3] for i in range(0, len(shot), 4)))
    return {"packets": len(packets), "frames": seen, "state_version": version,
            "bytes": sum(len(p) for _, p in packets), "screenshot": (shot_w, shot_h)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dump")
    ap.add_argument("out")
    ap.add_argument("--frames", type=int, default=2, help="frames of transfers to keep (default 2)")
    a = ap.parse_args(argv)
    try:
        info = extract(a.dump, a.out, frames=a.frames)
    except DumpFormatError as e:
        print("gsdump_extract: %s" % e, file=sys.stderr)
        return 2
    print("gsdump_extract: %d packets (%d bytes) of %d frame(s), state v%d, screenshot %dx%d -> %s"
          % (info["packets"], info["bytes"], info["frames"], info["state_version"], info["screenshot"][0],
             info["screenshot"][1], a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
