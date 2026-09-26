"""Sprint 10 Q7 item 1: tools_py/gsdump_extract.py turns a PCSX2 GS dump (.gs, the new 0xFFFFFFFF format) into the
console-replay fixture ps2x_tests' 'console GS dump replays ...' case reads: packets.bin ([u32 path][u32 size][bytes]
for the transfers of the first N frames), vram_initial.bin (the 4 MiB of GS memory inside the state blob) and
reference.ppm (PCSX2's own screenshot from the dump header). research/31 section 11 did this once by hand ("found in
the state blob by its swizzled palettes at file offset 0x12c1df") and the result was lost (docs/HAZARDS.md git); this is
the same arithmetic as a script, against a synthetic dump built here, so the fixture can be regenerated from the
captures under tools/pcsx2/snaps/ without a launch."""
import os
import struct
import tempfile
import unittest

from tools_py import gsdump_extract

VRAM_SIZE = 4 * 1024 * 1024


def synthetic_dump(frames, state_version=9, vram=None, screenshot=(2, 2)):
    """A new-format .gs: magic, header size, header, serial, screenshot, state (regs + VRAM + tail), 8 KiB registers,
    records; the header's offsets count from byte 8.
    `frames` is a list of frames; each frame is a list of (path, payload) transfers, closed by a vsync."""
    w, h = screenshot
    shot = bytes((x % 256, (x * 3) % 256, (x * 7) % 256, 0xFF)[i] for x in range(w * h) for i in range(4))
    serial = b"SCUS-97275"
    vram = vram if vram is not None else bytes((i * 31) & 0xFF for i in range(VRAM_SIZE))
    state = (bytes(i & 0xFF for i in range(gsdump_extract.STATE_REGS_BEFORE_VRAM[state_version])) + vram
             + b"\xEE" * gsdump_extract.STATE_TAIL_AFTER_VRAM[state_version])
    header_size = 36 + len(serial) + len(shot)
    hdr = struct.pack("<10I", header_size, state_version, len(state), 36, len(serial), 0x0F6FC6CF, w, h,
                      36 + len(serial), len(shot))
    body = b"\xFF\xFF\xFF\xFF" + hdr + serial + shot + state + b"\x11" * 8192
    records = b""
    for field, frame in enumerate(frames):
        for path, payload in frame:
            records += b"\x00" + bytes([path]) + struct.pack("<I", len(payload)) + payload
        records += b"\x02" + struct.pack("<I", 16)            # a ReadFIFO record: not a transfer
        records += b"\x01" + bytes([field & 1])               # vsync closes the frame
    records += b"\x03" + b"\x22" * 8192                        # a register record after the last frame
    return body + records, vram, shot


FRAMES = [
    [(3, b"\x01" * 16), (1, b"\x02" * 32)],
    [(2, b"\x03" * 48)],
    [(3, b"\x04" * 16)],
]


class ExtractTest(unittest.TestCase):
    def _extract(self, data, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = os.path.join(tmp.name, "dump.gs")
        with open(src, "wb") as fh:
            fh.write(data)
        out = os.path.join(tmp.name, "console_replay")
        return gsdump_extract.extract(src, out, **kw), out

    def test_packets_bin_holds_the_transfers_of_the_first_two_frames_in_the_test_binary_shape(self):
        data, _, _ = synthetic_dump(FRAMES)
        info, out = self._extract(data)
        with open(os.path.join(out, "packets.bin"), "rb") as fh:
            got = fh.read()
        want = b""
        for path, payload in FRAMES[0] + FRAMES[1]:
            want += struct.pack("<II", path, len(payload)) + payload
        self.assertEqual(got, want)
        self.assertEqual((info["packets"], info["frames"], info["state_version"]), (3, 2, 9))

    def test_frames_picks_how_many_frames_and_stops_at_the_end_of_the_stream(self):
        data, _, _ = synthetic_dump(FRAMES)
        info, out = self._extract(data, frames=1)
        self.assertEqual(info["packets"], 2)
        info, out = self._extract(data, frames=10)
        self.assertEqual((info["packets"], info["frames"]), (4, 3))

    def test_vram_initial_is_the_four_mebibytes_inside_the_state_blob(self):
        data, vram, _ = synthetic_dump(FRAMES)
        _, out = self._extract(data)
        with open(os.path.join(out, "vram_initial.bin"), "rb") as fh:
            self.assertEqual(fh.read(), vram)

    def test_reference_ppm_is_the_headers_screenshot_without_its_alpha(self):
        data, _, shot = synthetic_dump(FRAMES, screenshot=(3, 2))
        _, out = self._extract(data)
        with open(os.path.join(out, "reference.ppm"), "rb") as fh:
            got = fh.read()
        rgb = b"".join(shot[i:i + 3] for i in range(0, len(shot), 4))
        self.assertEqual(got, b"P6\n3 2\n255\n" + rgb)

    def test_an_unknown_state_version_is_refused_not_guessed(self):
        data, _, _ = synthetic_dump(FRAMES, state_version=9)
        data = data[:8] + struct.pack("<I", 12) + data[12:]
        with self.assertRaises(gsdump_extract.DumpFormatError):
            self._extract(data)

    def test_an_old_format_dump_is_refused(self):
        with self.assertRaises(gsdump_extract.DumpFormatError):
            self._extract(b"\x00\x00\x00\x00" + b"\x00" * 64)

    def test_a_state_blob_of_the_wrong_size_is_refused(self):
        data, _, _ = synthetic_dump(FRAMES)
        hdr = list(struct.unpack_from("<10I", data, 4))
        hdr[2] += 1
        data = data[:4] + struct.pack("<10I", *hdr) + data[44:]
        with self.assertRaises(gsdump_extract.DumpFormatError):
            self._extract(data)


if __name__ == "__main__":
    unittest.main()
