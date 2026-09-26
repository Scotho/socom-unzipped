"""Sprint 10 -- the simulated Clock runs its threads in lockstep (docs/HAZARDS.md harness: "A threaded Python simulation test can
redden CI on a push that did not touch Python").

The endgames run their stander / victim as a daemon thread beside the shooter, and the tests inject one fake Clock
into both. The clock was fake but the INTERLEAVING was the OS's: whichever thread the scheduler ran advanced the
shared time, so on a loaded runner the victim walked 23 legs before the shooter's first loop check and `bursts=0`
failed the test (runs 35483582765 and 35559659458). Under contention (25 parallel processes, four GIL-burning
threads each, a 10 us switch interval) that was 50 failures in 100 runs of test_freeze_contact_fire.

The contract now: a wait() returns only when every other thread on the clock (the maker and every thread born
after it) is itself waiting or has ended; the earliest deadline advances time; one thread runs at a time. A thread
that blocks OUTSIDE the clock (a native join, an Event) is named by ClockStall after `stall_s` real seconds instead
of hanging the run. The endgames' joins on their side threads go through the injected wait (M.join_in) so the
side thread ends in simulated time.

unittest only; simulated time.
"""
import threading
import time
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.tests.online_rows import Clock, ClockStall


def spin(seconds):
    """Burn real time in Python (bytecode, so the GIL is handed around): the window the scheduler used to use."""
    end = time.monotonic() + seconds
    x = 0
    while time.monotonic() < end:
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF
    return x


class Burners:
    """GIL contention for a test: pure-Python threads started BEFORE the clock (so they are not on it)."""

    def __init__(self, n=2):
        self.stop = threading.Event()
        self.threads = [threading.Thread(target=self.burn, daemon=True, name=f"burner{i}") for i in range(n)]
        for th in self.threads:
            th.start()

    def burn(self):
        x = 0
        while not self.stop.is_set():
            x = (x * 1103515245 + 12345) & 0xFFFFFFFF

    def close(self):
        self.stop.set()
        for th in self.threads:
            th.join()


class LockstepTest(unittest.TestCase):
    def setUp(self):
        # the loaded runner, in-process: two pure-Python burners contending for the GIL for the test's duration (the
        # reproduction's 10 us switch interval is left alone here: it crashed CPython 3.13 in importlib under load)
        self.burners = Burners()
        self.addCleanup(self.burners.close)

    def test_a_running_thread_holds_the_clock_still(self):
        # the victim of the CI flake: a side thread whose every leg is a 0.4 s wait, free-running under the old clock
        c = Clock(0.0)
        legs = []

        def victim():
            for _ in range(5):
                c.wait(0.4)
                legs.append(c())
        th = threading.Thread(target=victim, daemon=True, name="victim")
        th.start()
        seen = set()
        for _ in range(20):                                  # the shooter computing: 20 real ms, no wait
            spin(0.001)
            seen.add(c())
        self.assertEqual(seen, {0.0}, "time moved while the running thread never waited")
        self.assertEqual(legs, [])
        c.wait(0.1)                                          # the shooter's first check: 0.1 s in, no leg yet
        self.assertEqual(c(), 0.1)
        self.assertEqual(legs, [])
        c.wait(0.5)                                          # crosses the victim's 0.4: exactly one leg, before us
        self.assertEqual(c(), 0.6)
        self.assertEqual(legs, [0.4])
        c.wait(10.0)
        self.assertEqual([round(t, 6) for t in legs], [0.4, 0.8, 1.2, 1.6, 2.0])
        th.join(5.0)
        self.assertFalse(th.is_alive())
        self.assertEqual(c.threads(), [threading.current_thread()])

    def test_wakeups_follow_the_deadlines_one_thread_at_a_time(self):
        c = Clock(0.0)
        wakes, inside, most = [], [0], [0]
        lock = threading.Lock()

        def runner(name, period, n):
            for _ in range(n):
                c.wait(period)
                with lock:
                    inside[0] += 1
                    most[0] = max(most[0], inside[0])
                wakes.append((c(), name))
                spin(0.002)                                  # a real window for a second thread to be running in
                with lock:
                    inside[0] -= 1
        specs = (("a", 0.3, 6), ("b", 0.5, 4), ("c", 0.7, 3))
        ths = [threading.Thread(target=runner, args=s, daemon=True, name=s[0]) for s in specs]
        for th in ths:
            th.start()
        c.wait(3.0)                                          # the maker is on the clock too: this is 3 s of lockstep
        for th in ths:
            th.join(5.0)
            self.assertFalse(th.is_alive())
        # a tie (a's 5th and b's 3rd wake, both at 1.5) goes to the wait entered first: b's, entered at its 1.0 wake
        expect = sorted(((round(p * k, 6), round(p * (k - 1), 6)), nm) for nm, p, n in specs for k in range(1, n + 1))
        self.assertEqual([(round(t, 6), nm) for t, nm in wakes], [(t, nm) for (t, _), nm in expect])
        self.assertEqual(most[0], 1, "two threads were awake at once")

    def test_a_thread_that_blocks_outside_the_clock_is_named(self):
        c = Clock(0.0, stall_s=0.3)
        gate = threading.Event()
        th = threading.Thread(target=gate.wait, daemon=True, name="joiner-outside")
        th.start()
        self.addCleanup(gate.set)
        with self.assertRaises(ClockStall) as cm:
            c.wait(1.0)
        self.assertIn("joiner-outside", str(cm.exception))
        self.assertIn("neither waiting on the clock nor ended", str(cm.exception))
        self.assertEqual(c(), 0.0)                           # nothing moved
        with self.assertRaises(ClockStall):                  # a stalled clock stays stalled: no later luck
            c.wait(0.1)

    def test_threads_older_than_the_clock_are_not_on_it(self):
        gate = threading.Event()
        th = threading.Thread(target=gate.wait, daemon=True, name="older")
        th.start()
        self.addCleanup(gate.set)
        c = Clock(0.0, stall_s=0.3)
        self.assertNotIn(th, c.threads())
        c.wait(1.0)
        self.assertEqual(c(), 1.0)

    def test_a_single_thread_ticks_the_grid_as_before(self):
        c = Clock(0.0)
        ticks = []
        c.hooks.append(ticks.append)
        c.wait(0.1)
        c.wait(0.3)
        c.wait(1.0)
        self.assertEqual(ticks, [0.25, 0.5, 0.75, 1.0, 1.25])
        self.assertEqual(c(), 1.4)


class JoinInTest(unittest.TestCase):
    """M.join_in: the endgames' join on a side thread, taken through the injected wait."""

    def test_joins_a_thread_that_ends_in_simulated_time(self):
        c = Clock(0.0)
        th = threading.Thread(target=lambda: c.wait(0.3), daemon=True, name="side")
        th.start()
        self.assertTrue(M.join_in(th, None, c, c.wait))
        self.assertFalse(th.is_alive())
        self.assertAlmostEqual(c(), 0.3, delta=M.SIDE_JOIN_POLL_S + 1e-6)

    def test_a_timeout_returns_false_and_leaves_the_thread(self):
        c = Clock(0.0)
        th = threading.Thread(target=lambda: c.wait(0.3), daemon=True, name="side")
        th.start()
        self.assertFalse(M.join_in(th, 0.1, c, c.wait))
        self.assertTrue(th.is_alive())
        self.assertAlmostEqual(c(), 0.1, delta=1e-6)
        self.assertTrue(M.join_in(th, None, c, c.wait))     # and the second join sees it out

    def test_live_time_is_a_poll(self):
        th = threading.Thread(target=lambda: time.sleep(0.05), daemon=True)
        th.start()
        self.assertTrue(M.join_in(th, 5.0, time.time, time.sleep))


if __name__ == "__main__":
    unittest.main()
