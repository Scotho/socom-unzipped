import socket
import struct
import pytest
from tools_py.parity.pine import Pine


def pcsx2_up():
    try:
        socket.create_connection(("127.0.0.1", 28011), timeout=0.5).close()
        return True
    except OSError:
        return False


def elf_word(path, addr):
    d = open(path, "rb").read()
    phoff = struct.unpack_from("<I", d, 0x1c)[0]
    phnum = struct.unpack_from("<H", d, 0x2c)[0]
    for i in range(phnum):
        t, off, va, _pa, fsz, _m, _fl, _al = struct.unpack_from("<IIIIIIII", d, phoff + i * 32)
        if t == 1 and va <= addr < va + fsz:
            return struct.unpack_from("<I", d, off + addr - va)[0]
    return None


@pytest.mark.skipif(not pcsx2_up(), reason="PCSX2 with PINE not running")
def test_status_title_and_memory():
    p = Pine()
    assert p.status() in (0, 1, 2)
    assert "SOCOM" in p.title().upper()
    assert p.version().startswith("PCSX2")
    # FTSCore main (0x1e7040) holds the same word in PCSX2's RAM as in our merged ELF
    assert p.read32(0x001e7040) == elf_word("game/disc/socom2_game.elf", 0x001e7040)
