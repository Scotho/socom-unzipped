"""Minimal PCSX2 PINE client (TCP on Windows; port = PINESlot in tools/pcsx2/inis/PCSX2.ini).

Request: u32 total_len, u8 opcode, args. Reply: u32 total_len, u8 result (0 ok), data.
"""
import socket
import struct

OP_READ8, OP_READ16, OP_READ32, OP_READ64 = 0, 1, 2, 3
OP_WRITE8, OP_WRITE16, OP_WRITE32, OP_WRITE64 = 4, 5, 6, 7
OP_VERSION, OP_TITLE, OP_STATUS = 8, 0xB, 0xF


class Pine:
    def __init__(self, port=28011, host="127.0.0.1", timeout=5):
        self.s = socket.create_connection((host, port), timeout=timeout)

    def close(self):
        self.s.close()

    def _recv(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("PINE closed")
            buf += chunk
        return buf

    def _call(self, op, payload=b""):
        self.s.sendall(struct.pack("<IB", 5 + len(payload), op) + payload)
        total, res = struct.unpack("<IB", self._recv(5))
        data = self._recv(total - 5) if total > 5 else b""
        if res != 0:
            raise RuntimeError(f"PINE op {op:#x} failed")
        return data

    def read8(self, a):
        return self._call(OP_READ8, struct.pack("<I", a))[0]

    def read16(self, a):
        return struct.unpack("<H", self._call(OP_READ16, struct.pack("<I", a)))[0]

    def read32(self, a):
        return struct.unpack("<I", self._call(OP_READ32, struct.pack("<I", a)))[0]

    def read64(self, a):
        return struct.unpack("<Q", self._call(OP_READ64, struct.pack("<I", a)))[0]

    def write8(self, a, v):
        self._call(OP_WRITE8, struct.pack("<IB", a, v & 0xff))

    def write32(self, a, v):
        self._call(OP_WRITE32, struct.pack("<II", a, v & 0xffffffff))

    @staticmethod
    def _string(data):
        # string replies carry a u32 length prefix
        return data[4:].rstrip(b"\0").decode("utf-8", "replace") if len(data) >= 4 else ""

    def version(self):
        return self._string(self._call(OP_VERSION))

    def title(self):
        return self._string(self._call(OP_TITLE))

    def status(self):
        return struct.unpack("<I", self._call(OP_STATUS))[0]

    def cstring(self, a, max=64):
        out = bytearray()
        for i in range(max):
            b = self.read8(a + i)
            if b == 0:
                break
            out.append(b)
        return out.decode("ascii", "replace")
