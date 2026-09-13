"""PINE client against a live PCSX2 (skipped unless PCSX2 with PINE listens on 127.0.0.1:28011).

Moved from tools_py/parity/test_pine.py (Sprint 5 Task 0): it imported pytest and had never run.
"""
import os
import socket
import struct
import unittest

from tools_py.parity.pine import Pine

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


if __name__ == "__main__":
    unittest.main()
