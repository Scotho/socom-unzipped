"""motion_pack_check: is the motion pack (run/motion_p.zar -> DAT_00415e08) intact in an RDRAM image?

research/25 §8-§10: during the single-player mission load our sceGsExecLoadImage/StoreImage HLE (x8 block pointer)
smears the pack's 0x40000-byte chunks as [6,5,6,5,6,5,6,7] -- chunks 0..4 hold file chunks 6,5,6,5,6. The console and
our title-time image are the identity. The tool reports the chunk map and the count of chunks not holding their own
bytes, so the block-pointer fix can be verified 48 -> 0 style without a run (plan Task 0b Step 6).

Relocated pointers inside the pack differ from the file uniformly by the buffer delta, so a chunk is matched by the
fraction of equal bytes at the same in-chunk offset (>= 0.5 wins; the pack is mostly key data, not pointers)."""
import os
import struct
import unittest

from tools_py.parity import motion_pack_check as mpc

ZAR = "game/disc/RUN/MOTION_P.ZAR"
CHUNK = 0x40000


def _synthetic_pack(nchunks=4):
    """A fake file body of nchunks x CHUNK bytes where every word encodes (chunk, offset)."""
    body = bytearray()
    for c in range(nchunks):
        for off in range(0, CHUNK, 4):
            body += struct.pack("<I", (c << 24) | off)
    return bytes(body)


class ChunkMap(unittest.TestCase):
    def test_identity_pack_maps_to_itself(self):
        body = _synthetic_pack(4)
        self.assertEqual(mpc.chunk_map(body, body), [0, 1, 2, 3])

    def test_smeared_pack_reports_the_source_chunks(self):
        body = _synthetic_pack(4)
        chunks = [body[i * CHUNK:(i + 1) * CHUNK] for i in range(4)]
        smeared = chunks[2] + chunks[3] + chunks[2] + chunks[3]       # [2,3,2,3]: chunks 0 and 1 overwritten
        self.assertEqual(mpc.chunk_map(smeared, body), [2, 3, 2, 3])
        self.assertEqual(mpc.corrupt_chunks([2, 3, 2, 3]), 2)

    def test_relocated_pointers_do_not_break_the_match(self):
        body = bytearray(_synthetic_pack(2))
        buf = bytearray(body)
        for off in range(0, len(buf), 64):                            # every 16th word "relocated" by -0x2d00
            w = struct.unpack_from("<I", buf, off)[0]
            struct.pack_into("<I", buf, off, (w - 0x2D00) & 0xFFFFFFFF)
        self.assertEqual(mpc.chunk_map(bytes(buf), bytes(body)), [0, 1])


@unittest.skipUnless(os.path.exists(ZAR) and os.path.exists("logs/parity/spawn_ours_vf0.rdram")
                     and os.path.exists("logs/parity/title_ours.rdram"), "needs the disc file and the RDRAM dumps")
class RealImages(unittest.TestCase):
    """The numbers research/25 §10 verified by hand: smear on our SP spawn, identity at the title."""

    def test_pre_fix_spawn_dump_shows_the_smear(self):
        r = mpc.check_image("logs/parity/spawn_ours_vf0.rdram", ZAR)
        self.assertEqual(r["chunk_map"][:7], [6, 5, 6, 5, 6, 5, 6], r)
        self.assertEqual(r["corrupt_chunks"], 5, r)

    def test_title_dump_is_intact(self):
        r = mpc.check_image("logs/parity/title_ours.rdram", ZAR)
        self.assertEqual(r["chunk_map"], list(range(len(r["chunk_map"]))), r)
        self.assertEqual(r["corrupt_chunks"], 0, r)


if __name__ == "__main__":
    unittest.main()
