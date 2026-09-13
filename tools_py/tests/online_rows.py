"""Row builders shared by the Sprint 5 Task 5 harness tests (not a test module: unittest discovery loads test_*.py only).

`peek()` writes one `[peek]` line in the exe's format with the items those tests need -- the actor block (vtable,
x/y/z, optionally the matrix at +0x80..+0xbc), the alive byte, mp_round_count / mp_game_over by name bytes, the
clock string, the round clock 0x4365c0, the CZNetGame block split as launch 1 peeked it (ng+0xde) -- and `Clock`
is a simulated clock whose wait() runs hooks on the 0.25 s peek grid.
"""
import math
import os
import struct
import tempfile

from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc

ACTOR = 0x1583F60
NG = 0x869360


def f2w(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def tok(w):
    return f"{w:08x}(.)"


def item(addr, words):
    return f"@{addr:x}: " + " ".join(tok(w) for w in words)


def name_words(text):
    return list(struct.unpack("<III", (text.encode("ascii") + b"\0" * 12)[:12]))


def matrix_words(facing_deg):
    """actor +0x80..+0xbc (words 32..47) for a walk facing (atan2(dz, dx) degrees): theta = facing + 90."""
    th = math.radians(facing_deg + 90.0)
    w = [0] * 16
    w[0], w[2] = f2w(math.cos(th)), f2w(math.sin(th))
    w[5] = f2w(1.0)
    w[8], w[10] = f2w(-math.sin(th)), f2w(math.cos(th))
    w[15] = f2w(1.0)
    return w


def peek(x=100.0, y=50.0, z=200.0, facing=None, alive=1, clock="05:00", round_time=None, lag=None,
         health=None, actor=ACTOR):
    block = [M.ACTOR_VTABLE] + [0] * 63
    block[7], block[8], block[9] = f2w(x), f2w(y), f2w(z)
    if facing is not None:
        block[32:48] = matrix_words(facing)
    parts = ["[peek]", item(0x416054, [f2w(x - 20.0), f2w(y + 20.0), f2w(z)]), item(actor, block),
             item(actor + 0xF78, [(alive & 0xFF) << 16])]
    if health is not None:
        parts.append(item(actor + 0x1044, [f2w(health)]))
    for name, ptr, value, addr in (("mp_round_count", 0x006B7F30, 0, 0x694C48),
                                   ("mp_game_over", 0x006B7F20, 0, 0x694C20)):
        parts.append(item(addr, [ptr, 0x00010000]))
        parts.append(item(ptr, name_words(name)))
    if clock is not None:
        parts.append(item(0x408F10, list(struct.unpack("<II", (clock.encode() + b"\0" * 8)[:8]))))
    if round_time is not None:
        parts.append(item(0x4365C0, [f2w(round_time)]))
    if lag is not None:
        ng = [0] * 64
        ng[vc.NG_LAG_FLAG_OFFSET // 4] = (lag & 0xFF) << (8 * (vc.NG_LAG_FLAG_OFFSET % 4))
        tail = [0] * 21
        tail[(0x118 - 0x100) // 4] = vc.NG_FINGERPRINT_VALUE
        parts.append(item(NG, ng))
        parts.append(item(NG + 0x100, tail))
    return " ".join(parts)


class Clock:
    def __init__(self, t=1000.0):
        self.t = t
        self.hooks = []

    def __call__(self):
        return self.t

    def wait(self, seconds):
        """Advance to now + seconds, running the hooks at every 0.25 s grid point crossed (a wait shorter than
        0.25 s still ticks when it crosses one)."""
        end = self.t + seconds
        nxt = (math.floor(self.t / 0.25 + 1e-9) + 1) * 0.25
        while nxt <= end + 1e-9:
            self.t = round(nxt, 6)
            for h in self.hooks:
                h(self.t)
            nxt += 0.25
        self.t = end


def tail(clock, tag="A"):
    return M.RunLogTail(os.path.join(tempfile.gettempdir(), f"no_such_{tag}.log"), clock=clock)
