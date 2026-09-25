"""PINE client against a live PCSX2 (skipped unless PCSX2 with PINE listens on 127.0.0.1:28011),
plus the batched block read, which runs against a fake socket and needs no emulator.

Moved from tools_py/parity/test_pine.py (Sprint 5 Task 0): it imported pytest and had never run.
"""
import os
import socket
import struct
import unittest
from unittest import mock

from tools_py.parity.pine import OP_READ64, Pine

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GAME_ELF = os.path.join(ROOT, "game", "disc", "socom2_game.elf")


def pcsx2_up():
    try:
        socket.create_connection(("127.0.0.1", 28011), timeout=0.5).close()
        return True
    except OSError:
        return False


def elf_word(path, addr):
    with open(path, "rb") as f:
        d = f.read()
    phoff = struct.unpack_from("<I", d, 0x1c)[0]
    phnum = struct.unpack_from("<H", d, 0x2c)[0]
    for i in range(phnum):
        t, off, va, _pa, fsz, _m, _fl, _al = struct.unpack_from("<IIIIIIII", d, phoff + i * 32)
        if t == 1 and va <= addr < va + fsz:
            return struct.unpack_from("<I", d, off + addr - va)[0]
    return None


class TestPine(unittest.TestCase):
    @unittest.skipUnless(pcsx2_up(), "PCSX2 with PINE not running")
    @unittest.skipUnless(os.path.exists(GAME_ELF), "game/disc/socom2_game.elf not present")
    def test_status_title_and_memory(self):
        p = Pine()
        self.assertIn(p.status(), (0, 1, 2))
        self.assertIn("SOCOM", p.title().upper())
        self.assertTrue(p.version().startswith("PCSX2"))
        # FTSCore main (0x1e7040) holds the same word in PCSX2's RAM as in our merged ELF
        self.assertEqual(p.read32(0x001e7040), elf_word(GAME_ELF, 0x001e7040))


class FakePineSocket:
    """A PCSX2 that answers read64 batches out of a flat memory image."""

    def __init__(self, base, image):
        self.base = base
        self.image = image
        self.out = b""
        self.packets = []

    def sendall(self, data):
        self.packets.append(data)
        total = struct.unpack_from("<I", data, 0)[0]
        assert total == len(data), "the length word must cover the whole message"
        body = b""
        off = 4
        while off < len(data):
            op = data[off]
            assert op == OP_READ64, f"unexpected opcode {op}"
            addr = struct.unpack_from("<I", data, off + 1)[0]
            i = addr - self.base
            body += self.image[i:i + 8]
            off += 5
        self.out += struct.pack("<IB", 5 + len(body), 0) + body

    def recv(self, n):
        chunk, self.out = self.out[:n], self.out[n:]
        return chunk

    def close(self):
        pass


class ReadBlockTest(unittest.TestCase):
    BASE = 0x001E7000

    def _client(self, image, batch=None):
        sock = FakePineSocket(self.BASE, image)
        with mock.patch("socket.create_connection", return_value=sock):
            p = Pine()
        if batch:
            p.BATCH = batch
        return p, sock

    def test_a_block_comes_back_whole_and_in_order(self):
        image = bytes((i * 7 + 3) & 0xff for i in range(8 * 1000))
        p, _ = self._client(image)
        self.assertEqual(p.read_block(self.BASE, len(image)), image)

    def test_a_long_block_is_split_into_batches(self):
        image = bytes((i * 11) & 0xff for i in range(8 * 500))
        p, sock = self._client(image, batch=64)
        self.assertEqual(p.read_block(self.BASE, len(image)), image)
        self.assertEqual(len(sock.packets), 500 // 64 + 1)

    def test_a_size_that_is_not_a_multiple_of_eight_is_trimmed(self):
        image = bytes(range(64))
        p, _ = self._client(image)
        self.assertEqual(p.read_block(self.BASE, 21), image[:21])

    def test_progress_is_reported_and_never_overruns_the_request(self):
        image = bytes(8 * 300)
        seen = []
        p, _ = self._client(image, batch=100)
        p.read_block(self.BASE, len(image), progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen, [(800, 2400), (1600, 2400), (2400, 2400)])


if __name__ == "__main__":
    unittest.main()
