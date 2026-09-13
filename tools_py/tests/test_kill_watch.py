"""KillWatch's health signal must count a death only as a TRANSITION on one actor.

The kill check is the one place this harness prints `RESULT PASS`, so a false positive there is the
most expensive defect it can have. Before this test existed, the health guard fired on the FIRST
value it read inside the dead range -- raw 0x00000000, the uninitialised-heap fills 0xAFAFAFAF /
0xD9D9D9D9 (research/19), a read taken before the actor was set up -- with no prior alive read and
no idea which actor the word belonged to.

These tests drive the REAL code path end to end: `[peek]` lines go through `RunLogTail._line` (the
parser that finds the actor block by vtable and reads the word at actor+offset), and the resulting
history is judged by `KillWatch._check_health`. Nothing here re-implements the comparison.
"""
import os
import struct
import tempfile
import unittest

from tools_py.parity import online_match_ours as M

HEALTH_OFFSET = 0x40          # actor-relative; inside the single peeked block below
BLOCK_WORDS = 0x48 // 4       # covers ACTOR_POS_WORDS and HEALTH_OFFSET


def f2raw(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def peek_line(actor_addr, health_raw):
    words = [0] * BLOCK_WORDS
    words[0] = M.ACTOR_VTABLE
    words[HEALTH_OFFSET // 4] = health_raw
    body = " ".join(f"{w:08x}(.)" for w in words)
    return f"[peek] @{actor_addr:x}: {body}"


class KillWatchHealthTransition(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Neither thread is started: lines are fed and checks are run synchronously.
        self.tail = M.RunLogTail(os.path.join(self.tmp.name, "run.log"))
        self.tail.watch_offset = HEALTH_OFFSET
        self.watch = M.KillWatch({"A": self.tail}, {}, server_log=os.path.join(self.tmp.name, "none.log"),
                                 health=HEALTH_OFFSET)

    def feed(self, *reads):
        """Each read is (actor_addr, raw word); the watch is polled after every one, as it would be
        live (it polls far faster than the sampler writes rows)."""
        for addr, raw in reads:
            self.tail._line(peek_line(addr, raw))      # noqa: SLF001 - the real parser
            self.watch._check_health()                  # noqa: SLF001 - the real check

    def health_events(self):
        return [e for e in self.watch.events if e["kind"] == "health"]

    def test_first_read_alive_does_not_fire(self):
        self.feed((0x1F00000, f2raw(0.4)))
        self.assertEqual(self.health_events(), [])
        self.assertIsNone(self.watch.fired)

    def test_first_read_zero_does_not_fire(self):
        self.feed((0x1F00000, 0x00000000))
        self.assertEqual(self.health_events(), [])
        self.assertIsNone(self.watch.fired)

    def test_first_read_heap_fill_afafafaf_does_not_fire(self):
        self.feed((0x1F00000, 0xAFAFAFAF))
        self.assertEqual(self.health_events(), [])

    def test_first_read_heap_fill_d9d9d9d9_does_not_fire(self):
        # 0xD9D9D9D9 is ~ -7.7e15 as a float: below the default range's -1e9 floor, so it is also
        # checked with a range wide enough to contain it -- a fill must not fire on range luck.
        for rng in ((-1e9, 0.0), (-1e30, 0.0)):
            with self.subTest(health_range=rng):
                self.setUp()
                self.watch.health_range = rng
                self.feed((0x1F00000, 0xD9D9D9D9))
                self.assertEqual(self.health_events(), [])

    def test_garbage_then_zero_does_not_fire(self):
        # A non-finite or wildly out-of-range word is never an alive read.
        for garbage in (0x7F800000, 0x7FC00000, f2raw(5000.0), 0xAFAFAFAF):
            with self.subTest(garbage=hex(garbage)):
                self.setUp()
                self.feed((0x1F00000, garbage), (0x1F00000, 0x00000000))
                self.assertEqual(self.health_events(), [])

    def test_alive_then_dead_same_actor_fires(self):
        self.feed((0x1F00000, f2raw(1.0)), (0x1F00000, 0x00000000))
        ev = self.health_events()
        self.assertEqual(len(ev), 1)
        self.assertIs(self.watch.fired, ev[0])
        self.assertEqual(ev[0]["tag"], "A")
        self.assertEqual(ev[0]["detail"]["actor"], 0x1F00000)

    def test_alive_then_partial_damage_then_dead_fires(self):
        self.feed((0x1F00000, f2raw(1.0)), (0x1F00000, f2raw(0.4)), (0x1F00000, f2raw(-0.25)))
        self.assertEqual(len(self.health_events()), 1)

    def test_alive_then_garbage_then_zero_does_not_fire(self):
        self.feed((0x1F00000, f2raw(1.0)), (0x1F00000, 0x7FC00000), (0x1F00000, 0x00000000))
        self.assertEqual(self.health_events(), [])

    def test_alive_on_one_actor_dead_on_another_does_not_fire(self):
        self.feed((0x1F00000, f2raw(1.0)), (0x1F20000, 0x00000000))
        self.assertEqual(self.health_events(), [])
        self.assertIsNone(self.watch.fired)

    def test_actor_change_resets_alive_state(self):
        # A -> B -> back to A: the earlier alive read on A must not survive the switch.
        self.feed((0x1F00000, f2raw(1.0)), (0x1F20000, f2raw(1.0)), (0x1F00000, 0x00000000))
        self.assertEqual(self.health_events(), [])


if __name__ == "__main__":
    unittest.main()
