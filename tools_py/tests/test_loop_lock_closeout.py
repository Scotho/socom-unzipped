"""Sprint 5 close-out fix wave, slice (c) -- the loop lock minors parked by Task 0's round-3 review, and R14's test time:

   8. a record read that fails (a sharing violation on Windows) leaks nothing to stderr: the renewer captures 2>&1, so
      a leaked line delayed LOCK LOST one interval;
   9. a renew/release whose "not held" miss cannot be confirmed because the mutex is busy reports a TRANSIENT result,
      never "not held" (a renewer must not declare LOCK LOST on a busy mutex);
  10. after writing its mutex token a process requires exactly one entry in the mutex dir, else removes its own token
      and retries (the X3 double-entry guard);
  11. the default suite is a smoke (claim, renew, release, one reap, one quiet-marker check); the rest runs with
      LOOP_LOCK_SLOW_TESTS=1.
"""
import ctypes
import os
import subprocess
import time
import unittest

from tools_py.tests import test_loop_lock as TL


class TestCloseoutLockMinors(TL.LockTestBase):
    def mutex_with_fresh_token(self):
        mx = self.lock + ".mx"
        os.makedirs(mx)
        open(os.path.join(mx, "t.%d.999.1" % int(time.time())), "w").close()
        return mx

    @unittest.skipUnless(os.name == "nt", "a sharing violation needs Windows")
    def test_an_unreadable_record_leaks_nothing_to_stderr(self):
        from ctypes import wintypes
        self.write_record("alice", 60, hb_age_s=0)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateFileW.restype = wintypes.HANDLE
        h = k.CreateFileW(self.rec, 0x80000000, 0, None, 3, 0x80, None)   # GENERIC_READ, share none
        self.assertNotEqual(h, wintypes.HANDLE(-1).value)
        try:
            p = subprocess.run([TL.BASH, TL.LOCK_SH, "check"], capture_output=True, text=True, env=self.env(),
                               timeout=60)
        finally:
            k.CloseHandle(h)
        self.assertEqual(p.stderr, "")
        self.assertIn("HELD", p.stdout)

    def test_the_record_reads_are_braced(self):
        with open(TL.LOCK_SH) as f:
            src = f.read()
        self.assertNotIn('read -r line < "$1/record" 2>/dev/null', src)
        self.assertNotIn('read -r line < "$LOCK" 2>/dev/null', src)
        self.assertIn('{ IFS= read -r line < "$1/record"; } 2>/dev/null', src)

    def test_a_renew_miss_under_a_busy_mutex_is_transient(self):
        self.write_record("alice", 60, hb_age_s=0)
        self.mutex_with_fresh_token()
        rc, out = self.sh("renew", "bob", env=self.env(LOOP_LOCK_MUTEX_WAIT_SEC=1))
        self.assertNotEqual(rc, 0, out)
        self.assertFalse(out.startswith("not held"), out)
        self.assertIn("mutex", out)
        rc, out = self.sh("release", "bob", env=self.env(LOOP_LOCK_MUTEX_WAIT_SEC=1))
        self.assertNotEqual(rc, 0, out)
        self.assertFalse(out.startswith("not held"), out)
        os.remove(os.path.join(self.lock + ".mx", os.listdir(self.lock + ".mx")[0]))
        os.rmdir(self.lock + ".mx")
        rc, out = self.sh("renew", "bob")
        self.assertEqual((rc, out.strip()), (1, "not held by bob"))

    def test_a_second_token_in_the_mutex_is_not_entered(self):
        env = self.pause_env("mutex_after_token", LOOP_LOCK_MUTEX_WAIT_SEC=2)
        p = self.popen("take", "bob", env=env)
        self.wait_paused("mutex_after_token", p)
        mx = self.lock + ".mx"
        foreign = os.path.join(mx, "t.%d.4242.7" % int(time.time()))
        open(foreign, "w").close()
        self.go("mutex_after_token")
        out = p.communicate(timeout=60)[0]
        self.assertEqual(p.returncode, 1, out)
        self.assertIn("BUSY", out)
        self.assertEqual(os.listdir(mx), [os.path.basename(foreign)], "its own token removed, the other left")
        self.assertTrue(self.is_free())


class TestSmokeSelection(unittest.TestCase):
    def test_the_default_suite_is_the_smoke(self):
        self.assertEqual(TL.SMOKE, {
            "test_free_take_writes_four_field_record_inside_the_claim_dir",
            "test_smoke_holder_renew_refreshes_the_heartbeat",
            "test_non_holder_release_exits_1",
            "test_stale_heartbeat_with_empty_busy_list_is_reaped",
            "test_quiet_flag_writes_marker_even_for_a_non_launch_purpose",
            # Ruling R73 (Sprint 5 final review I2): mutual exclusion stays always on
            "test_smoke_racing_reapers_with_process_list_latency_one_wins",
            "test_smoke_stale_mutex_takers_never_double_enter",
            # Sprint 13 H2 (issue #36): the queue's grant -- a take never barges past a live ticket -- stays always on
            "test_smoke_a_take_is_refused_behind_a_live_ticket_and_a_stale_ticket_is_dropped",
            # Sprint 14 G5: run_detached's memory guard refuses below RUN_MIN_FREE_MEM_GB -- the refusal stays always
            # on (the reaper dropped queued jobs under memory pressure on 2026-09-25); the pass cases are slow-only
            "test_memory_refusal_below_threshold_does_not_launch"})
        with open(TL.__file__) as f:
            src = f.read()
        self.assertIn('test.skipTest("slow lock suite: set LOOP_LOCK_SLOW_TESTS=1")', src)


if __name__ == "__main__":
    unittest.main()
