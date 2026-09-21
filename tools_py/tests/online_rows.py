"""Row builders shared by the Sprint 5 Task 5 harness tests (not a test module: unittest discovery loads test_*.py only).

`peek()` writes one `[peek]` line in the exe's format with the items those tests need -- the actor block (vtable,
x/y/z, optionally the matrix at +0x80..+0xbc), the alive byte, mp_round_count / mp_game_over by name bytes, the
clock string, the round clock 0x4365c0, the CZNetGame block split as launch 1 peeked it (ng+0xde) -- and `Clock`
is a simulated clock whose wait() runs hooks on the 0.25 s peek grid, in lockstep across the threads that share it.
"""
import math
import os
import struct
import tempfile
import threading
import time

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
         health=None, actor=ACTOR, round_count=0):
    block = [M.ACTOR_VTABLE] + [0] * 63
    block[7], block[8], block[9] = f2w(x), f2w(y), f2w(z)
    if facing is not None:
        block[32:48] = matrix_words(facing)
    parts = ["[peek]", item(0x416054, [f2w(x - 20.0), f2w(y + 20.0), f2w(z)]), item(actor, block),
             item(actor + 0xF78, [(alive & 0xFF) << 16])]
    if health is not None:
        parts.append(item(actor + 0x1044, [f2w(health)]))
    for name, ptr, value, addr in (("mp_round_count", 0x006B7F30, round_count, 0x694C48),
                                   ("mp_game_over", 0x006B7F20, 0, 0x694C20)):
        parts.append(item(addr, [ptr, 0x00010000 | (value & 0xFFFF)]))
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


class ClockStall(AssertionError):
    """A thread on the clock stopped taking part without ending: the simulation cannot move (see Clock)."""


class Clock:
    """Simulated time. wait() advances to now + seconds, running the hooks at every 0.25 s grid point crossed (a wait
    shorter than 0.25 s still ticks when it crosses one).

    Threads (Sprint 10, the CI flake KNOWN §4 records): the clock is shared by every thread born after it, plus the
    one that made it (the endgames start their stander / victim loop as a daemon thread; the shooter runs on the
    caller's or a second thread). Simulated time cannot be advanced by whichever thread the OS happens to schedule --
    that let a victim walk 23 legs before the shooter's first loop check on a loaded runner, so the outcome depended
    on scheduler luck. Instead the clock runs in LOCKSTEP: a wait() blocks until EVERY other thread on the clock is
    itself in a wait() (or has ended), the earliest deadline advances time (ties in the order the waits were
    entered), and that sleeper alone runs until it waits again. One thread runs at a time and the OS never chooses
    who, so the interleaving is a function of the simulated deadlines only. A thread on the clock that blocks
    somewhere else (a native join, an Event) would freeze the simulation -- every wait is on it -- so a wait that has
    seen no progress for `stall_s` real seconds raises ClockStall naming the thread that is neither waiting nor
    ended, rather than hanging the run or passing by luck. The endgames join their side threads through the injected
    wait (M.join_in) for that reason.
    """

    STALL_S = 120.0                  # real seconds with a thread neither waiting nor ended: a deadlock, not load
    POLL_S = 0.005                   # a thread's end is not a clock event: the sleepers look for it this often

    def __init__(self, t=1000.0, stall_s=STALL_S):
        self.t = t
        self.hooks = []
        self.stall_s = stall_s
        self.stalled = None          # the first ClockStall's message: every later wait() raises it again
        self._cv = threading.Condition()
        self._sleepers = {}          # thread -> (deadline, order entered)
        self._entered = 0
        self._progress = 0           # bumped at every change of the sleeper set / time: the stall detector's pulse
        me = threading.current_thread()
        self._outside = {th for th in threading.enumerate() if th is not me}  # older than the clock: not on it

    def __call__(self):
        return self.t

    def threads(self):
        """The live threads on the clock: the maker and every thread born after it."""
        return [th for th in threading.enumerate() if th not in self._outside]

    def wait(self, seconds):
        me = threading.current_thread()
        with self._cv:
            if self.stalled:
                raise ClockStall(self.stalled)
            self._entered += 1
            self._sleepers[me] = (self.t + seconds, self._entered)
            self._progress += 1
            self._cv.notify_all()
            idle, seen = 0.0, None
            while True:
                running = [th for th in self.threads() if th not in self._sleepers]
                first = min(self._sleepers, key=self._sleepers.get)
                if not running and first is me:
                    break
                if (self._progress, len(running)) != seen:      # a wait entered, time moved or a thread ended
                    idle, seen = 0.0, (self._progress, len(running))
                t0 = time.monotonic()
                self._cv.wait(self.POLL_S)
                idle += time.monotonic() - t0
                if idle >= self.stall_s:
                    self.stalled = (
                        f"clock stalled {self.stall_s:g}s at t={self.t:.2f}: {', '.join(th.name for th in running)} "
                        f"neither waiting on the clock nor ended (blocked outside it?) while "
                        f"{', '.join(th.name for th in self._sleepers)} wait")
                    del self._sleepers[me]
                    self._progress += 1
                    self._cv.notify_all()
                    raise ClockStall(self.stalled)
            deadline, _ = self._sleepers.pop(me)
            self._advance(deadline)
            self._progress += 1
            self._cv.notify_all()

    def _advance(self, end):
        nxt = (math.floor(self.t / 0.25 + 1e-9) + 1) * 0.25
        while nxt <= end + 1e-9:
            self.t = round(nxt, 6)
            for h in self.hooks:
                h(self.t)
            nxt += 0.25
        self.t = end


def tail(clock, tag="A"):
    return M.RunLogTail(os.path.join(tempfile.gettempdir(), f"no_such_{tag}.log"), clock=clock)
