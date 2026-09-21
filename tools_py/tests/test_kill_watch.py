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
from tools_py.tests.shell import BASH

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


def actor_line(actor_addr, health, alive):
    """A row shaped like the Task 2 peek: the actor block (vtable), the word at +0xF78 (alive byte =
    byte 2) and the float at +0x1044 -- three items, found by address off the vtable block."""
    words = [0] * 16
    words[0] = M.ACTOR_VTABLE
    blk = " ".join(f"{w:08x}(.)" for w in words)
    return (f"[peek] @{actor_addr:x}: {blk} @{actor_addr + 0xF78:x}: {alive << 16:08x}(.) "
            f"@{actor_addr + 0x1044:x}: {f2raw(health):08x}(.)")


class KillWatchArmedDefaults(unittest.TestCase):
    """Sprint 5 Task 2 Step 6: health +0x1044 and alive +0xF7A are the harness defaults."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tail = M.RunLogTail(os.path.join(self.tmp.name, "run.log"))
        self.tail.watch_offset = M.DEFAULT_HEALTH_OFFSET
        self.watch = M.KillWatch({"A": self.tail}, {}, server_log=os.path.join(self.tmp.name, "none.log"),
                                 health=M.DEFAULT_HEALTH_OFFSET, alive=M.DEFAULT_ALIVE_OFFSET)

    def feed(self, *reads):
        for addr, health, alive in reads:
            self.tail._line(actor_line(addr, health, alive))    # noqa: SLF001
            self.watch._check_health()                            # noqa: SLF001
            self.watch._check_alive()                             # noqa: SLF001

    def kinds(self):
        return [(e["kind"], e["firing"]) for e in self.watch.events]

    def test_defaults_are_the_sourced_offsets(self):
        self.assertEqual(M.DEFAULT_HEALTH_OFFSET, 0x1044)
        self.assertEqual(M.DEFAULT_ALIVE_OFFSET, 0xF7A)

    def test_death_fires_health_and_records_alive_without_firing(self):
        self.feed((0x1F00000, 1.0, 1), (0x1F00000, 0.5, 1), (0x1F00000, 0.0, 1), (0x1F00000, 0.0, 2))
        self.assertEqual(self.kinds(), [("health", True), ("alive", False)])
        self.assertEqual(self.watch.fired["kind"], "health")
        self.assertEqual(self.tail.watch_reads, 4)
        self.assertEqual(self.tail.watch_misses, 0)

    def test_alive_leaving_1_alone_never_fires(self):
        self.feed((0x1F00000, 1.0, 1), (0x1F00000, 1.0, 3))
        self.assertEqual(self.kinds(), [("alive", False)])
        self.assertIsNone(self.watch.fired)

    def test_alive_first_read_not_1_is_not_an_observation(self):
        self.feed((0x1F00000, 1.0, 2), (0x1F00000, 1.0, 3))
        self.assertEqual(self.kinds(), [])

    def test_alive_on_another_actor_is_not_an_observation(self):
        self.feed((0x1F00000, 1.0, 1), (0x1F20000, 1.0, 2))
        self.assertEqual(self.kinds(), [])


class ArmingCli(unittest.TestCase):
    def test_parse_offset(self):
        self.assertIsNone(M.parse_offset("none"))
        self.assertIsNone(M.parse_offset("OFF"))
        self.assertEqual(M.parse_offset("0"), 0)
        self.assertEqual(M.parse_offset("0x1044"), 0x1044)

    def test_health_peek_coverage(self):
        self.assertEqual(M.health_peek_problems("*0x408c58+0x1044:1", 0x1044), [])
        self.assertEqual(M.health_peek_problems("*0x408c58+0x1040:4", 0x1044), [])
        self.assertEqual(M.health_peek_problems("*0x408c58:64,*0x408c58+0xF78:1", None), [])
        self.assertTrue(M.health_peek_problems("*0x408c58:64,*0x408c58+0xF78:1", 0x1044))
        self.assertEqual(M.health_peek_problems("*0x408c58+0x1000:128", 0x1044), [])
        self.assertTrue(M.health_peek_problems("*0x408c58+0xF00:128", 0x1044))   # 64-word cap: ends at +0x1000


class LaunchRefusalLabels(unittest.TestCase):
    """Fix round 1: a health-coverage refusal is labelled as the health watch's, not the move path's."""

    def test_health_refusal_has_its_own_label(self):
        env = {"PS2X_PEEK": "*0x408c58:64,*0x408c58+0xF78:1", "PS2X_CALL_TRACE": "0x553dc0:MoveScale",
               "PS2X_CALL_TRACE_EVERY": "10"}
        lines, code = M.launch_refusal_lines(env, alive_offset=0xF7A, health_offset=0x1044)
        self.assertEqual(code, 2)
        health = [l for l in lines if "0x1044" in l]
        self.assertTrue(health)
        self.assertTrue(all(l.startswith("HEALTH WATCH REFUSES:") for l in health), health)
        self.assertIn("RESULT NO-DATA health watch (not launched)", lines)
        self.assertFalse(any(l.startswith("MOVE-PATH WATCH REFUSES:") and "0x1044" in l for l in lines))

    def test_disarmed_health_adds_no_health_refusal(self):
        env = {"PS2X_PEEK": "*0x408c58+0x1044:1", "PS2X_CALL_TRACE": "", "PS2X_CALL_TRACE_EVERY": "10"}
        lines, code = M.launch_refusal_lines(env, alive_offset=0xF7A, health_offset=None)
        self.assertEqual(code, 2)                        # the move path still refuses (no MoveScale slot): only its label may appear
        self.assertFalse(any("HEALTH" in l for l in lines))


class FrostfireScriptLaunches(unittest.TestCase):
    """Fix round 1: the committed scripts/parity/online_match_frostfire.sh must pass the harness's own
    pre-launch refusal with the default (armed) offsets. Its exports are read from the file, not copied."""

    def exports(self):
        # The exports a launch gets: scripts/parity/env.sh (the shared instruments, sourced by every online script)
        # plus the script's own -- evaluated by bash on a clean environment, exactly as a launch evaluates them.
        import subprocess
        script = ("unset PS2X_PEEK PS2X_CALL_TRACE PS2X_CALL_TRACE_EVERY PS2X_SOCOM2_SERVER PS2X_GS_STATS; "
                  ". scripts/parity/env.sh; export PS2X_SOCOM2_RSA_KEY_B=b; env | grep '^PS2X_'")
        p = subprocess.run([BASH, "-c", script], capture_output=True, text=True, cwd=os.getcwd())
        return dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)

    def test_committed_script_is_not_refused(self):
        env = self.exports()
        lines, code = M.launch_refusal_lines(env, M.DEFAULT_ALIVE_OFFSET, M.DEFAULT_HEALTH_OFFSET)
        self.assertEqual((lines, code), ([], 0))
        self.assertEqual(M.peek_spec_problems(env["PS2X_PEEK"]), [])


if __name__ == "__main__":
    unittest.main()
