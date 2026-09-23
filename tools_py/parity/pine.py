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

    def save_state(self, slot):
        self._call(0x9, struct.pack("<B", slot))

    def load_state(self, slot):
        self._call(0xA, struct.pack("<B", slot))

    def cstring(self, a, max=64):
        out = bytearray()
        for i in range(max):
            b = self.read8(a + i)
            if b == 0:
                break
            out.append(b)
        return out.decode("ascii", "replace")

    # ---- batched reads ---------------------------------------------------------------------
    # One PINE message may carry several commands back to back; the reply carries their results
    # in the same order behind one length+status word. Reading a megabyte of EE RAM eight bytes
    # at a time is 130,000 round trips, which is minutes on loopback; a batch of a few hundred
    # turns it into seconds. The batch size is bounded because PCSX2's read buffer is finite
    # (MAX_IPC_SIZE): 1,024 read64 commands is 9 KB out and 8 KB back, well inside it.
    BATCH = 1024

    def _batch_read64(self, addrs):
        msg = b"".join(struct.pack("<BI", OP_READ64, a) for a in addrs)
        self.s.sendall(struct.pack("<I", 4 + len(msg)) + msg)   # the length word covers itself
        total, res = struct.unpack("<IB", self._recv(5))
        data = self._recv(total - 5) if total > 5 else b""
        if res != 0:
            raise RuntimeError("PINE batch read failed")
        if len(data) != 8 * len(addrs):
            raise RuntimeError(f"PINE batch read returned {len(data)} bytes for {len(addrs)} reads")
        return data

    def read_block(self, addr, size, progress=None):
        """`size` bytes of guest memory from `addr`, as bytes. Reads in 8-byte units, so a
        request that is not a multiple of 8 is rounded up and trimmed."""
        words = (size + 7) // 8
        out = bytearray()
        for i in range(0, words, self.BATCH):
            chunk = [addr + 8 * j for j in range(i, min(i + self.BATCH, words))]
            out += self._batch_read64(chunk)
            if progress:
                progress(min(len(out), size), size)
        return bytes(out[:size])
