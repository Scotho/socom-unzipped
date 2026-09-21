"""scripts/loop_lock.sh, scripts/run_detached.sh and scripts/kill_stale_drivers.ps1, with fakes.

No game, no build, and never the real lock: every test points LOOP_LOCK_PATH at a temp dir and
LOOP_LOCK_PS_CMD at a fake process list (a file the test writes, "pid|ppid|created|name|cmdline" per line),
and back-dates heartbeats by writing the record directly.

The DEFAULT suite is a <= ~30 s smoke (SMOKE; the Sprint 5 close-out wave, R14 revisited, amended by Rulings R73
and R77; measured 23.5-27.2 s under host load on 2026-09-14):
claim, renew, release, one reap, one quiet-marker check, and -- because mutual exclusion is the lock's whole job --
one reaper race (4 takers x 2 rounds on a stale ghost, 0-0.3 s of process-list latency) and one stale-mutex
double-entry check (3 takers through the critical-section detector). Every other test -- the longer races, the
interleavings, run/run_detached, the hammer, the real-scale renewal (`run -- sleep 130`, ~135 s) -- runs only with
LOOP_LOCK_SLOW_TESTS=1, which runs them all (~16 min).
R73's hygiene test (TestSlowSuiteStamp, always on outside the slow run) fails when scripts/loop_lock.sh's git blob
differs from fixtures/loop_lock_slow_green.txt: an edit to the lock script needs a green slow run, and only then a
new stamp (`git hash-object scripts/loop_lock.sh`).
LOOP_LOCK_TEST_SCRIPTS=<dir> points the suite at another copy of the scripts (used to show a test is
red against the previous version).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.environ.get("LOOP_LOCK_TEST_SCRIPTS") or os.path.join(ROOT, "scripts")
LOCK_SH = os.path.join(SCRIPTS, "loop_lock.sh").replace("\\", "/")
DETACHED_SH = os.path.join(SCRIPTS, "run_detached.sh").replace("\\", "/")
QUIET_GATE_SH = os.path.join(SCRIPTS, "check_quiet_gate.sh").replace("\\", "/")
KILL_PS1 = os.path.join(SCRIPTS, "kill_stale_drivers.ps1")
POWERSHELL = (shutil.which("powershell.exe") or shutil.which("powershell")) if os.name == "nt" else None
SLOW = os.environ.get("LOOP_LOCK_SLOW_TESTS") == "1"
SMOKE = {
    "test_free_take_writes_four_field_record_inside_the_claim_dir",     # claim
    "test_smoke_holder_renew_refreshes_the_heartbeat",                  # renew
    "test_non_holder_release_exits_1",                                  # release
    "test_stale_heartbeat_with_empty_busy_list_is_reaped",              # one reap
    "test_quiet_flag_writes_marker_even_for_a_non_launch_purpose",      # one quiet-marker check
    "test_smoke_racing_reapers_with_process_list_latency_one_wins",     # R73: one reaper race
    "test_smoke_stale_mutex_takers_never_double_enter",                 # R73: one mutex double-entry check
}


def smoke_or_slow(test):
    if not SLOW and test._testMethodName not in SMOKE:
        test.skipTest("slow lock suite: set LOOP_LOCK_SLOW_TESTS=1")

IDLE = ["4|0||System|", "900|4||explorer.exe|C:\\Windows\\explorer.exe", "901|900||bash.exe|bash"]


# the Git Bash finder that used to live here is tools_py/tests/shell.py, shared by every script-driving test


def _read(path):
    with open(path) as f:
        return f.read()


def fwd(path):
    return path.replace("\\", "/")


def processes_with(marker):
    """Windows processes whose command line contains marker (excluding the query itself)."""
    q = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*%s*' -and "
         "$_.Name -notlike 'powershell*' } | ForEach-Object { $_.ProcessId }" % marker)
    out = subprocess.run([POWERSHELL, "-NoProfile", "-Command", q], capture_output=True, text=True, timeout=60)
    return [l for l in out.stdout.split() if l.strip()]


@unittest.skipUnless(BASH, "bash not found")
class LockTestBase(unittest.TestCase):
    def setUp(self):
        smoke_or_slow(self)
        self.tmp = tempfile.mkdtemp(prefix="loop_lock_test_")
        self.lock = os.path.join(self.tmp, "lk")
        self.lockd = self.lock + ".d"
        self.rec = os.path.join(self.lockd, "record")
        self.procs = os.path.join(self.tmp, "procs.txt")
        self.set_procs(IDLE)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def set_procs(self, lines):
        with open(self.procs, "w", newline="\n") as f:
            f.write("\n".join(lines) + "\n")

    def env(self, **extra):
        env = dict(os.environ)
        for k in ("LOOP_LOCK_HELD", "LOOP_LOCK_SELF_WINPID"):
            env.pop(k, None)     # this suite may itself run under `loop_lock.sh run`
        env["LOOP_LOCK_PATH"] = fwd(self.lock)
        env["LOOP_LOCK_PS_CMD"] = "cat '%s'" % fwd(self.procs)
        env.update({k: str(v) for k, v in extra.items()})
        return env

    def sh(self, *args, env=None, timeout=60):
        p = subprocess.run([BASH, LOCK_SH] + list(args), capture_output=True, text=True,
                           env=env or self.env(), timeout=timeout)
        return p.returncode, p.stdout + p.stderr

    def write_record(self, owner, epoch_age_s, hb_age_s=None, purpose="", legacy=False):
        now = int(time.time())
        hb = now - (hb_age_s if hb_age_s is not None else epoch_age_s)
        if legacy:
            with open(self.lock, "w", newline="\n") as f:
                f.write("%s %d\n" % (owner, now - epoch_age_s))
            return
        os.makedirs(self.lockd, exist_ok=True)
        with open(self.rec, "w", newline="\n") as f:
            f.write("%s %d %d %s\n" % (owner, now - epoch_age_s, hb, purpose))

    def record(self):
        return _read(self.rec).split()

    def history(self):
        path = os.path.join(self.tmp, ".loop_lock_history")
        return _read(path) if os.path.exists(path) else ""

    def is_free(self):
        return self.sh("check")[1].strip() == "FREE"

    def strays(self):
        """Graves, half-built claims or a leftover mutex beside the lock."""
        return sorted(n for n in os.listdir(self.tmp) if n.startswith("lk.") and n != "lk.d")

    def pause_env(self, point, **extra):
        return self.env(LOOP_LOCK_TEST_PAUSE_AT=point, LOOP_LOCK_TEST_PAUSE_DIR=fwd(self.tmp), **extra)

    def wait_paused(self, point, proc, seconds=60):
        flag = os.path.join(self.tmp, point + ".paused")
        deadline = time.time() + seconds
        while not os.path.exists(flag):
            if proc.poll() is not None:
                self.fail("%s exited before pausing at %s: %s" % (proc.args, point, proc.communicate()[0]))
            if time.time() > deadline:
                self.fail("never paused at " + point)
            time.sleep(0.1)

    def go(self, point):
        open(os.path.join(self.tmp, point + ".go"), "w").close()

    def popen(self, *args, env):
        return subprocess.Popen([BASH, LOCK_SH] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, env=env)


class TestTakeReapBreak(LockTestBase):
    def test_free_take_writes_four_field_record_inside_the_claim_dir(self):
        rc, out = self.sh("take", "alice", "--purpose", "two words")
        self.assertEqual(rc, 0, out)
        self.assertIn("TAKEN by alice", out)
        rec = self.record()
        self.assertEqual(rec[0], "alice")
        self.assertEqual(rec[1].split("-")[0], rec[2])
        self.assertEqual(rec[3:], ["two", "words"])
        self.assertFalse(os.path.exists(self.lock), "the record lives inside the claim dir")
        self.assertEqual(self.sh("id")[1].strip(), "alice " + rec[1])

    def test_smoke_holder_renew_refreshes_the_heartbeat(self):
        self.write_record("alice", 600, hb_age_s=600, purpose="p")
        take_id = self.record()[1]
        rc, out = self.sh("renew", "alice")
        self.assertEqual(rc, 0, out)
        self.assertIn("RENEWED by alice", out)
        rec = self.record()
        self.assertEqual(rec[:2], ["alice", take_id])
        self.assertLessEqual(abs(int(rec[2]) - time.time()), 5)

    def test_held_lock_is_busy_even_for_its_owner(self):
        self.assertEqual(self.sh("take", "alice")[0], 0)
        rc, out = self.sh("take", "alice")
        self.assertEqual(rc, 1, out)
        self.assertIn("BUSY", out)

    def test_stale_heartbeat_with_empty_busy_list_is_reaped(self):
        self.write_record("ghost", 3600, hb_age_s=16 * 60, purpose="died")
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 0, out)
        self.assertIn("REAPED ghost", out)
        self.assertEqual(self.record()[0], "bob")
        self.assertIn('REAPED "ghost', self.history())

    def test_stale_heartbeat_with_busy_process_is_busy(self):
        busy_cases = [
            "ninja.exe|ninja -C build",
            "vu1_replay.exe|dist\\vu1_replay.exe --verify",
            "python.exe|python -m unittest discover -s tools_py/tests",
            "python3.13.exe|python -m tools_py.parity.drive --target ours",
            "cmake.exe|cmake --build",
            "clang++.exe|clang++ -c x.cpp",
            "ld.exe|ld",
            "ld.lld.exe|ld.lld",
            "lld-link.exe|lld-link",
            "pcsx2-qt.exe|pcsx2-qt.exe",
            "ps2_recomp.exe|ps2_recomp.exe cfg",
            "ps2x_tests.exe|ps2x_tests.exe",
            "socom2_b.exe|socom2_b.exe",
        ]
        for i, line in enumerate(busy_cases):
            with self.subTest(proc=line):
                self.write_record("worker", 3600, hb_age_s=20 * 60)
                self.set_procs(IDLE + ["%d|901||%s" % (5000 + i, line)])
                rc, out = self.sh("take", "bob")
                self.assertEqual(rc, 1, out)
                self.assertIn("not reaped", out)
                self.assertEqual(self.record()[0], "worker")
        self.assertEqual(self.history(), "")

    def test_names_merely_starting_with_ld_are_not_busy(self):
        for name in ("ldap_helper.exe", "ldconfig.exe"):
            with self.subTest(name=name):
                self.write_record("ghost", 3600, hb_age_s=20 * 60)
                self.set_procs(IDLE + ["5000|901||%s|%s" % (name, name)])
                rc, out = self.sh("take", "bob")
                self.assertEqual(rc, 0, out)
                self.sh("release", "bob")

    def test_python_without_parity_or_unittest_is_not_busy(self):
        self.write_record("ghost", 3600, hb_age_s=20 * 60)
        self.set_procs(IDLE + ["5000|901||python.exe|python -m http.server"])
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 0, out)

    def test_caller_ancestor_is_not_busy_against_itself(self):
        # gate.py (python -m tools_py.parity.gate) takes the lock: it and `python -m unittest` above it are
        # the caller's own ancestors and must not block its reap.
        self.write_record("ghost", 3600, hb_age_s=50 * 60)
        chain = IDLE + ["6000|901|100|python.exe|python -m unittest discover",
                        "6001|6000|200|python3.13.exe|python -m tools_py.parity.gate --stamp x",
                        "6002|6001|300|bash.exe|bash scripts/loop_lock.sh take gate",
                        "6003|6002|400|powershell.exe|powershell -Command Get-CimInstance"]
        self.set_procs(chain)
        rc, out = self.sh("take", "gate", env=self.env(LOOP_LOCK_SELF_WINPID=6003))
        self.assertEqual(rc, 0, out)
        self.assertIn("REAPED ghost", out)

    def test_non_ancestor_with_the_same_command_line_still_counts(self):
        self.write_record("ghost", 3600, hb_age_s=50 * 60)
        chain = IDLE + ["6000|901|100|python.exe|python -m unittest discover",
                        "6001|6000|200|python3.13.exe|python -m tools_py.parity.gate --stamp x",
                        "6002|6001|300|bash.exe|bash scripts/loop_lock.sh take gate",
                        "6003|6002|400|powershell.exe|powershell -Command Get-CimInstance",
                        "7001|900|250|python3.13.exe|python -m tools_py.parity.gate --stamp x"]
        self.set_procs(chain)
        rc, out = self.sh("take", "gate", env=self.env(LOOP_LOCK_SELF_WINPID=6003))
        self.assertEqual(rc, 1, out)
        self.assertIn("stale break REFUSED", out)
        self.assertIn("7001", out)
        self.assertNotIn("6001", out)

    @unittest.skipUnless(POWERSHELL, "Windows PowerShell not available")
    def test_real_process_list_excludes_this_python(self):
        # This process runs under `python -m unittest` (a busy-list command line); through the real CIM query
        # the busy list it sees must not contain itself.
        env = self.env()
        env.pop("LOOP_LOCK_PS_CMD")
        marker = "s5t0_busy_sibling_%d" % os.getpid()
        sibling = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "unittest", marker])
        try:
            time.sleep(1.0)
            code = ("import subprocess,sys; r=subprocess.run(sys.argv[2:], capture_output=True, text=True); "
                    "print(r.stdout)")
            p = subprocess.run([sys.executable, "-c", code, "unittest_ancestor_" + marker, BASH, LOCK_SH, "busy"],
                               capture_output=True, text=True, env=env, timeout=90)
            self.assertIn(marker, p.stdout, "the non-ancestor sibling must be listed")
            self.assertNotIn("unittest_ancestor_" + marker, p.stdout, "the caller's own ancestor was listed")
        finally:
            sibling.kill()
            sibling.wait(timeout=10)

    def test_unreadable_process_list_counts_as_busy(self):
        self.write_record("ghost", 3600, hb_age_s=20 * 60)
        self.set_procs([])
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 1, out)
        self.assertIn("process list unavailable", out)

    def test_fresh_heartbeat_with_nothing_running_is_busy(self):
        # Taken an hour ago but renewed a minute ago: the clock is the heartbeat, not take-time.
        self.write_record("worker", 3600, hb_age_s=60)
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 1, out)
        self.assertIn("BUSY", out)
        self.assertEqual(self.record()[0], "worker")

    def test_stale_break_refused_while_game_runs(self):
        self.write_record("worker", 3600, hb_age_s=50 * 60)
        self.set_procs(IDLE + ["5000|900||socom2.exe|dist\\socom2.exe"])
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 1, out)
        self.assertIn("stale break REFUSED", out)
        self.assertIn("socom2.exe", out)
        self.assertEqual(self.record()[0], "worker")

    def test_old_two_field_record_is_read(self):
        # Pre-Sprint-5 lock: the plain file with "<owner> <epoch>", no claim dir. heartbeat = epoch.
        self.write_record("old", 5 * 60, legacy=True)
        rc, out = self.sh("check")
        self.assertIn("HELD: old", out)
        self.assertIn("heartbeat 5 min", out)
        self.assertEqual(self.sh("take", "bob")[0], 1)
        self.assertTrue(os.path.exists(self.lock))
        self.assertFalse(os.path.isdir(self.lockd), "a BUSY take must not leave a claim dir")
        rc, out = self.sh("renew", "old")
        self.assertEqual(rc, 0, out)
        rec = _read(self.lock).split()
        self.assertLessEqual(int(time.time()) - int(rec[2]), 5)
        self.assertEqual(self.sh("release", "old")[0], 0)
        self.assertTrue(self.is_free())

    def test_old_two_field_stale_record_is_reaped(self):
        self.write_record("old", 20 * 60, legacy=True)
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 0, out)
        self.assertIn("REAPED old", out)
        self.assertFalse(os.path.exists(self.lock))

    def test_non_holder_release_exits_1(self):
        self.assertEqual(self.sh("take", "alice")[0], 0)
        rc, out = self.sh("release", "mallory")
        self.assertEqual(rc, 1, out)
        self.assertIn("not held by mallory", out)
        self.assertEqual(self.record()[0], "alice")
        rc, _ = self.sh("release", "alice")
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(self.lock))
        self.assertFalse(os.path.exists(self.lockd))
        self.assertEqual(self.sh("release", "alice")[0], 1)

    def test_release_with_stale_held_id_refuses(self):
        # Minor 2: the lock was reaped and retaken under the same owner name; a release carrying the old
        # id must not remove the new holder's lock.
        self.write_record("worker", 60, hb_age_s=0)
        epoch = self.record()[1]
        rc, out = self.sh("release", "worker", env=self.env(LOOP_LOCK_HELD="worker 12345"))
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.record()[1], epoch)

    def test_renew_by_non_holder_fails(self):
        self.write_record("alice", 600, hb_age_s=600)
        rc, out = self.sh("renew", "bob")
        self.assertEqual(rc, 1, out)

    def test_renew_never_creates_the_claim_dir(self):
        # Minor 3: a renew racing a reap must not re-create the dir the reaper just moved away. The legacy
        # file with a matching id and no dir is the state a renewer saw mid-reap in the old layout.
        now = int(time.time())
        with open(self.lock, "w", newline="\n") as f:
            f.write("w %d %d p\n" % (now - 60, now - 60))
        rc, out = self.sh("renew", "w", env=self.env(LOOP_LOCK_HELD="w %d" % (now - 60)))
        self.assertFalse(os.path.isdir(self.lockd), out)

    def test_wait_times_out_then_succeeds(self):
        self.write_record("worker", 60, hb_age_s=0)
        rc, out = self.sh("wait", "bob", "2", env=self.env(LOOP_LOCK_WAIT_SEC=1))
        self.assertEqual(rc, 1, out)
        self.assertIn("TIMEOUT", out)
        self.sh("release", "worker")
        rc, out = self.sh("wait", "bob", "2", env=self.env(LOOP_LOCK_WAIT_SEC=1))
        self.assertEqual(rc, 0, out)


class TestRaces(LockTestBase):
    def _race(self, n, env):
        procs = [subprocess.Popen([BASH, LOCK_SH, "take", "racer%d" % i], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, env=env) for i in range(n)]
        return [p.communicate(timeout=120)[0] for p in procs]

    def _holder(self):
        return self.sh("id")[1].split()[0]

    def test_two_racing_takes_one_wins(self):
        for _ in range(6 if SLOW else 3):
            outs = self._race(2, self.env())
            self.assertEqual(sum("TAKEN" in o for o in outs), 1, outs)
            self.sh("release", self._holder())

    def test_racing_reapers_with_slow_process_list_one_wins(self):
        # Critical 1: a stale ghost, 4 concurrent reapers, and a process list with 0-2 s of latency (what
        # PowerShell costs). Exactly one TAKEN per round and exactly one history line per ghost.
        env = self.env(LOOP_LOCK_PS_CMD="sleep $((RANDOM %% 3)); cat '%s'" % fwd(self.procs))
        self.counts = []
        for rnd in range(6 if SLOW else 3):
            ghost = "ghost%d" % rnd
            self.write_record(ghost, 3600, hb_age_s=30 * 60)
            outs = self._race(4, env)
            taken = sum("TAKEN" in o for o in outs)
            reaps = len(re.findall(r'REAPED "%s ' % ghost, self.history()))
            self.counts.append((taken, reaps))
            self.assertEqual(taken, 1, outs)
            self.assertEqual(reaps, 1, self.history())
            self.assertNotIn("DISPLACED", self.history())
            self.assertEqual([l for l in self.history().splitlines() if "REAPED" not in l], [], self.history())
            self.assertEqual(self.strays(), [])
            self.assertEqual(self.sh("release", self._holder())[0], 0)
            self.assertTrue(self.is_free())
        print("\n[race] per-round (TAKEN, history lines):", self.counts, file=sys.stderr)

    def test_smoke_racing_reapers_with_process_list_latency_one_wins(self):
        # R73, always on: the reap race above at smoke scale -- a stale ghost, 4 concurrent reapers, 2 rounds, a
        # process list with 0-0.3 s of random latency so the reapers' busy checks interleave. Exactly one TAKEN
        # and exactly one REAPED history line per round, nothing stranded beside the lock. (One bash per taker
        # plus one release per round; the slow race above keeps the 0-2 s latency, 6 rounds and the extra checks.)
        # Cost, measured 2026-09-14 at ~71 % host CPU: ~4-4.5 s per round, almost all of it loop_lock.sh's own
        # forks under 4-way contention (one uncontended take ~1.25 s; the latency adds < 0.5 s) -- so ~8-9 s.
        # Ruling R77: the always-on lock tests may take up to ~30 s in total; measured 23.5-27.2 s (race 8.1-16.5 s at
        # the heaviest load seen) on 2026-09-14. R73's floor of 4 takers x 2 rounds stays.
        env = self.env(LOOP_LOCK_PS_CMD="sleep 0.$((RANDOM %% 4)); cat '%s'" % fwd(self.procs))
        for rnd in range(2):
            ghost = "sghost%d" % rnd
            self.write_record(ghost, 3600, hb_age_s=30 * 60)
            outs = self._race(4, env)
            winners = [re.search(r"TAKEN by (\S+)", o).group(1) for o in outs if "TAKEN" in o]
            self.assertEqual(len(winners), 1, (rnd, outs))
            self.assertEqual(len(re.findall(r'REAPED "%s ' % ghost, self.history())), 1, (rnd, self.history()))
            self.assertNotIn("DISPLACED", self.history())
            self.assertEqual(self.strays(), [], rnd)
            self.assertEqual(self.record()[0], winners[0])
            rc, out = self.sh("release", winners[0])
            self.assertEqual(rc, 0, out)
            self.assertFalse(os.path.exists(self.lockd), out)

    def test_hammer_three_takers_one_holder_per_round(self):
        # 3 takers x 10 rounds (100 with LOOP_LOCK_SLOW_TESTS=1), no latency; odd rounds start free, even
        # rounds on a stale ghost.
        tally = {}
        for rnd in range(100 if SLOW else 10):
            ghost = rnd % 2 == 0
            if ghost:
                self.write_record("ghost%d" % rnd, 3600, hb_age_s=30 * 60)
            outs = self._race(3, self.env())
            taken = sum(o.startswith("TAKEN") for o in outs)
            key = (taken, self.history().count('REAPED "ghost%d ' % rnd) if ghost else None)
            tally[key] = tally.get(key, 0) + 1
            self.assertEqual(taken, 1, (rnd, outs))
            if ghost:
                self.assertEqual(key[1], 1, (rnd, self.history()))
            self.assertEqual(self.sh("release", self._holder())[0], 0)
            self.assertTrue(self.is_free())
            self.assertEqual(self.strays(), [], rnd)
        print("\n[hammer] (TAKEN, REAPED-lines-for-the-ghost or None on free rounds): %s" % tally, file=sys.stderr)

    def test_release_never_shows_a_recordless_lock(self):
        # Minor 4: while a holder takes and releases in a loop, a concurrent observer must never see a
        # claim dir without its record ("<no record>").
        stop = os.path.join(self.tmp, "stop")
        obs_script = ("while [ ! -f '%s' ]; do bash '%s' check; done" % (fwd(stop), LOCK_SH))
        observer = subprocess.Popen([BASH, "-c", obs_script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, env=self.env())
        try:
            for _ in range(25 if SLOW else 8):
                self.sh("take", "cycler")
                self.sh("renew", "cycler")          # M-2: a record replace must not look record-less either
                self.sh("renew", "cycler")
                self.sh("release", "cycler")
        finally:
            open(stop, "w").close()
        out = observer.communicate(timeout=60)[0]
        self.assertNotIn("<no record>", out)


class TestInterleavings(LockTestBase):
    """Round 2: every transition under the mutex; pauses injected with LOOP_LOCK_TEST_PAUSE_AT."""

    def test_late_renew_after_reap_and_reclaim_reports_not_held(self):
        # A wrapper waking after 15+ min: its renew is paused past its first read while a reaper reaps the
        # ghost and a new holder claims. The new record must survive; the late renew must say not held.
        self.write_record("ghost", 3600, hb_age_s=50 * 60, purpose="gp")
        ghost_id = " ".join(self.record()[:2])
        g = self.popen("renew", "ghost", env=self.pause_env("renew_before_mutex", LOOP_LOCK_HELD=ghost_id))
        self.wait_paused("renew_before_mutex", g)
        rc, out = self.sh("take", "T", "--purpose", "tjob")
        self.assertEqual(rc, 0, out)
        t_record = _read(self.rec)
        self.go("renew_before_mutex")
        gout = g.communicate(timeout=60)[0]
        self.assertNotEqual(g.returncode, 0, gout)
        self.assertIn("not held", gout)
        self.assertEqual(_read(self.rec), t_record, "the late renew rewrote the new holder's record")
        self.assertEqual(self.sh("renew", "T")[0], 0)

    def test_reaper_whose_ghost_was_reaped_meanwhile_reports_the_new_holder(self):
        # disp/disp.sh: B judges the ghost and pauses; A reaps and claims; C tries; B resumes.
        self.write_record("ghost", 3600, hb_age_s=50 * 60, purpose="p")
        b = self.popen("take", "tB", env=self.pause_env("reap_before_mutex"))
        self.wait_paused("reap_before_mutex", b)
        rc, a_out = self.sh("take", "tA")
        self.assertEqual(rc, 0, a_out)
        self.assertIn("REAPED ghost", a_out)
        rc, c_out = self.sh("take", "tC")
        self.assertEqual(rc, 1, c_out)
        self.go("reap_before_mutex")
        b_out = b.communicate(timeout=60)[0]
        self.assertEqual(b.returncode, 1, b_out)
        self.assertIn("tA", b_out)
        self.assertEqual(self.record()[0], "tA")
        self.assertEqual(self.history().count("REAPED"), 1, self.history())
        self.assertNotIn("DISPLACED", self.history())
        self.assertEqual(self.strays(), [])
        self.assertEqual(self.sh("renew", "tA")[0], 0)
        self.assertEqual(self.sh("take", "tD")[0], 1)

    def test_reaper_whose_ghost_was_released_meanwhile_takes_the_free_lock(self):
        # Minor 2: the lock is FREE by the time the paused reaper gets the mutex -> TAKEN, not BUSY.
        self.write_record("ghost", 3600, hb_age_s=50 * 60)
        b = self.popen("take", "tB", env=self.pause_env("reap_before_mutex"))
        self.wait_paused("reap_before_mutex", b)
        self.assertEqual(self.sh("take", "tA")[0], 0)
        self.assertEqual(self.sh("release", "tA")[0], 0)
        self.go("reap_before_mutex")
        b_out = b.communicate(timeout=60)[0]
        self.assertEqual(b.returncode, 0, b_out)
        self.assertEqual(self.record()[0], "tB")

    def test_late_release_by_name_does_not_release_a_newer_holding(self):
        # disp/rel.sh: a manual `release main` pauses; run-cleanup releases holding X; Y takes as main;
        # the paused release resumes. Y must still hold; nothing stranded.
        rc, out = self.sh("take", "main", "--purpose", "X", "--print-id")
        x_id = re.search(r"ID: (.*)", out).group(1).strip()
        r = self.popen("release", "main", env=self.pause_env("release_before_mutex"))
        self.wait_paused("release_before_mutex", r)
        self.assertEqual(self.sh("_release_id", x_id)[0], 0)
        rc, out = self.sh("take", "main", "--purpose", "Y", "--print-id")
        self.assertEqual(rc, 0, out)
        y_id = re.search(r"ID: (.*)", out).group(1).strip()
        self.assertNotEqual(x_id, y_id, "two holdings in the same second must have distinct ids")
        self.go("release_before_mutex")
        r_out = r.communicate(timeout=60)[0]
        self.assertEqual(r.returncode, 1, r_out)
        self.assertEqual(self.sh("id")[1].strip(), y_id)
        self.assertEqual(self.strays(), [])

    def make_mutex(self, token_age_s, dir_age_s=0, token=True):
        mx = self.lock + ".mx"
        os.makedirs(mx)
        if token:
            open(os.path.join(mx, "t.%d.999.1" % (int(time.time()) - token_age_s)), "w").close()
        if dir_age_s:
            old = time.time() - dir_age_s
            os.utime(mx, (old, old))
        return mx

    def test_stale_mutex_is_broken_with_a_history_line(self):
        mx = self.make_mutex(token_age_s=60)
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.history().count("MUTEX-BROKEN"), 1, self.history())
        self.assertFalse(os.path.exists(mx))
        self.assertEqual(self.strays(), [])

    def test_stale_token_named_mutex_is_broken_exactly_once_by_three_takers(self):
        self.make_mutex(token_age_s=60)
        procs = [self.popen("take", "t%d" % i, env=self.env()) for i in range(3)]
        outs = [p.communicate(timeout=120)[0] for p in procs]
        self.assertEqual(sum(o.startswith("TAKEN") for o in outs), 1, outs)
        self.assertEqual(self.history().count("MUTEX-BROKEN"), 1, self.history())
        self.assertEqual(self.strays(), [])

    def test_fresh_token_in_an_old_dir_is_not_stale(self):
        # Staleness comes from the token's name, never from the dir's mtime.
        mx = self.make_mutex(token_age_s=0, dir_age_s=600)
        rc, out = self.sh("take", "bob", env=self.env(LOOP_LOCK_MUTEX_WAIT_SEC=2))
        self.assertEqual(rc, 1, out)
        self.assertIn("mutex", out)
        self.assertTrue(os.path.exists(mx))
        self.assertEqual(self.history(), "")

    def test_tokenless_stale_mutex_is_broken_after_two_readings(self):
        mx = self.make_mutex(token_age_s=0, dir_age_s=60, token=False)
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 0, out)
        self.assertIn("MUTEX-BROKEN <no token>", self.history())
        self.assertFalse(os.path.exists(mx))

    def test_release_that_cannot_get_the_mutex_says_so(self):
        # M-5: a mutex that stays held must not be reported as "the lock no longer carries <id>".
        rc, out = self.sh("take", "bob")
        self.make_mutex(token_age_s=0)
        rc, out = self.sh("release", "bob", env=self.env(LOOP_LOCK_RELEASE_WAIT_SEC=2))
        self.assertEqual(rc, 1, out)
        self.assertIn("release failed: mutex busy; the lock stays held until reaped", out)
        self.assertEqual(self.record()[0], "bob")

    def test_renew_whose_mutex_is_broken_while_stalled_writes_nothing(self):
        # I-2: a renew stalls inside the mutex after its id check; its mutex is broken (token deleted, as a
        # breaker would) and a new holder takes over. Resumed, it must not write.
        self.write_record("ghost", 3600, hb_age_s=50 * 60, purpose="gp")
        ghost_id = " ".join(self.record()[:2])
        g = self.popen("renew", "ghost", env=self.pause_env("renew_inside_mutex", LOOP_LOCK_HELD=ghost_id))
        self.wait_paused("renew_inside_mutex", g)
        mx = self.lock + ".mx"
        shutil.rmtree(mx)                                 # the break
        rc, out = self.sh("take", "T", "--purpose", "tjob")
        self.assertEqual(rc, 0, out)
        t_record = _read(self.rec)
        self.go("renew_inside_mutex")
        gout = g.communicate(timeout=60)[0]
        self.assertNotEqual(g.returncode, 0, gout)
        self.assertNotIn("RENEWED", gout)
        self.assertEqual(_read(self.rec), t_record, "the stalled renew wrote over the new holder's record")
        self.assertEqual(self.strays(), [])

    def test_reaper_whose_mutex_is_broken_while_stalled_leaves_the_new_claim(self):
        # I-2 (reap): a reaper stalls inside the mutex after its compare matched; its mutex is broken and a
        # second reaper reaps and claims. Resumed, the first must report BUSY and not move the new claim.
        self.write_record("ghost", 3600, hb_age_s=50 * 60)
        r1 = self.popen("take", "R1", env=self.pause_env("reap_inside_mutex"))
        self.wait_paused("reap_inside_mutex", r1)
        shutil.rmtree(self.lock + ".mx")
        rc, out = self.sh("take", "R2")
        self.assertEqual(rc, 0, out)
        r2_record = _read(self.rec)
        self.go("reap_inside_mutex")
        r1_out = r1.communicate(timeout=60)[0]
        self.assertEqual(r1.returncode, 1, r1_out)
        self.assertIn("BUSY", r1_out)
        self.assertEqual(_read(self.rec), r2_record)
        self.assertEqual(self.strays(), [])
        self.assertEqual(self.sh("renew", "R2")[0], 0)

    @unittest.skipUnless(SLOW, "set LOOP_LOCK_SLOW_TESTS=1")
    def test_slow_stale_mutex_rounds_never_admit_two(self):
        # e2b: a stale token-named mutex + a stale ghost + 3 concurrent takers, 40 rounds; a critical-section
        # marker detects two processes inside the mutex at once.
        cs = os.path.join(self.tmp, "cs")
        tally = {}
        for rnd in range(40):
            for n in os.listdir(self.tmp):
                if n.startswith("lk") or n == ".loop_lock_history":
                    shutil.rmtree(os.path.join(self.tmp, n), ignore_errors=True)
                    if os.path.exists(os.path.join(self.tmp, n)):
                        os.remove(os.path.join(self.tmp, n))
            shutil.rmtree(cs, ignore_errors=True)
            os.makedirs(cs)
            self.write_record("ghost", 3600, hb_age_s=50 * 60)
            self.make_mutex(token_age_s=60)
            env = self.env(LOOP_LOCK_TEST_CS_DIR=fwd(cs), LOOP_LOCK_TEST_CS_HOLD="0.2")
            procs = [self.popen("take", "t%d" % i, env=env) for i in range(3)]
            outs = [p.communicate(timeout=180)[0] for p in procs]
            taken = sum(o.startswith("TAKEN") for o in outs)
            doubles = _read(os.path.join(cs, "double.log")) if os.path.exists(os.path.join(cs, "double.log")) else ""
            key = (taken, self.history().count("MUTEX-BROKEN"), self.history().count("REAPED"), len(doubles.splitlines()))
            tally[key] = tally.get(key, 0) + 1
            self.assertEqual(doubles, "", (rnd, outs))
            self.assertEqual(taken, 1, (rnd, outs))
            self.assertEqual(key[1:3], (1, 1), (rnd, self.history()))
        print("\n[e2b] (TAKEN, MUTEX-BROKEN, REAPED, double entries): %s" % tally, file=sys.stderr)

    def test_smoke_stale_mutex_takers_never_double_enter(self):
        # R73, always on: one round of e2b above -- a stale token-named mutex, a stale ghost and 3 concurrent takers
        # through the critical-section detector (LOOP_LOCK_TEST_CS_DIR): nobody else inside the mutex while one
        # holds it, one break, one reap, one TAKEN.
        cs = os.path.join(self.tmp, "cs")
        os.makedirs(cs)
        self.write_record("ghost", 3600, hb_age_s=50 * 60)
        self.make_mutex(token_age_s=60)
        env = self.env(LOOP_LOCK_TEST_CS_DIR=fwd(cs), LOOP_LOCK_TEST_CS_HOLD="0.2")
        procs = [self.popen("take", "t%d" % i, env=env) for i in range(3)]
        outs = [p.communicate(timeout=120)[0] for p in procs]
        double = os.path.join(cs, "double.log")
        self.assertEqual(_read(double) if os.path.exists(double) else "", "", outs)
        self.assertEqual(sum(o.startswith("TAKEN") for o in outs), 1, outs)
        self.assertEqual((self.history().count("MUTEX-BROKEN"), self.history().count("REAPED")), (1, 1), self.history())
        self.assertEqual(self.strays(), [])

    def test_old_graves_are_cleaned_on_take(self):
        grave = self.lock + ".d.reaped.1.2"
        os.makedirs(grave)
        old = time.time() - 2 * 3600
        os.utime(grave, (old, old))
        fresh = self.lock + ".d.reaped.3.4"
        os.makedirs(fresh)
        self.assertEqual(self.sh("take", "bob")[0], 0)
        self.assertFalse(os.path.exists(grave))
        self.assertTrue(os.path.exists(fresh), "a grave younger than 1 h is left alone")

    def test_reused_pid_parent_ends_the_ancestor_walk(self):
        # Minor 1: 6002's recorded parent 6001 was created AFTER 6002 -> a reused PID, not an ancestor.
        self.write_record("ghost", 3600, hb_age_s=50 * 60)
        self.set_procs(IDLE + ["6001|900|500|python3.13.exe|python -m tools_py.parity.gate --stamp x",
                               "6002|6001|300|bash.exe|bash scripts/loop_lock.sh take gate",
                               "6003|6002|400|powershell.exe|powershell"])
        rc, out = self.sh("take", "gate", env=self.env(LOOP_LOCK_SELF_WINPID=6003))
        self.assertEqual(rc, 1, out)
        self.assertIn("6001", out)


class TestRun(LockTestBase):
    def test_run_reports_lock_lost_and_does_not_release_the_new_holder(self):
        p = subprocess.Popen([BASH, LOCK_SH, "run", "runner", "--", "sleep", "4"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=self.env(LOOP_LOCK_RENEW_SEC=1))
        deadline = time.time() + 30
        while not os.path.exists(self.rec) and time.time() < deadline:
            time.sleep(0.1)
        runner_id = self.sh("id")[1].strip()
        self.assertEqual(self.sh("_release_id", runner_id)[0], 0)
        self.assertEqual(self.sh("take", "thief")[0], 0)
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, out + err)
        self.assertIn("LOCK LOST", err)
        self.assertIn("not released", out)
        self.assertEqual(self.record()[0], "thief")

    def test_run_false_releases_and_exits_1(self):
        rc, out = self.sh("run", "runner", "--", "false")
        self.assertEqual(rc, 1, out)
        self.assertIn("TAKEN by runner", out)
        self.assertIn("RELEASED", out)
        self.assertTrue(self.is_free())

    def test_run_returns_command_exit_code(self):
        rc, out = self.sh("run", "runner", "--purpose", "rc test", "--", "bash", "-c", "exit 7")
        self.assertEqual(rc, 7, out)
        self.assertTrue(self.is_free())

    def test_run_on_busy_lock_does_not_run_command(self):
        self.write_record("worker", 60, hb_age_s=0)
        marker = fwd(os.path.join(self.tmp, "ran"))
        rc, out = self.sh("run", "runner", "--", "touch", marker)
        self.assertEqual(rc, 75, out)
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(self.record()[0], "worker")

    def test_nested_take_and_release_under_run(self):
        # gate.py takes and releases the lock itself; inside `run` that must not be BUSY.
        inner = "bash '%s' take gate && bash '%s' release gate && bash '%s' check" % (LOCK_SH, LOCK_SH, LOCK_SH)
        rc, out = self.sh("run", "outer", "--", "bash", "-c", inner)
        self.assertEqual(rc, 0, out)
        self.assertIn("NESTED under outer", out)
        self.assertIn("outer keeps the lock", out)
        self.assertIn("HELD: outer", out)
        self.assertTrue(self.is_free())

    def test_stale_held_env_is_not_nested(self):
        self.write_record("outer", 60, hb_age_s=0)
        rc, out = self.sh("take", "gate", env=self.env(LOOP_LOCK_HELD="outer 12345"))
        self.assertEqual(rc, 1, out)

    def _run_and_sample(self, sleep_s, renew_s):
        p = subprocess.Popen([BASH, LOCK_SH, "run", "sampler", "--", "sleep", str(sleep_s)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             env=self.env(LOOP_LOCK_RENEW_SEC=renew_s))
        ages = []
        deadline = time.time() + 30
        while not os.path.exists(self.rec) and time.time() < deadline:
            time.sleep(0.1)
        while p.poll() is None:
            try:
                rec = _read(self.rec).split()
                if len(rec) >= 3:
                    ages.append(time.time() - int(rec[2]))
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        out = p.communicate()[0]
        return p.returncode, out, ages

    def test_run_renews_heartbeat_scaled(self):
        # The real-scale property (60 s renew, sleep 130, < 70 s) at 1/30 scale: 2 s renew, sleep 6 (the plan wrote 8).
        # Ruling R36: the bound is < 4.5 s (2.25x the 2 s renew). The heartbeat is whole seconds and the
        # sampler polls every 0.5 s, so a healthy renew already peaks ~3.1-3.6 s, and under full-suite
        # load (build.sh test) it read 3.55 and 3.58 against the old 3.5. One missed renewal peaks
        # around 4 s; a BROKEN renew never refreshes and approaches the whole 6 s sleep, which
        # 4.5 still fails.
        rc, out, ages = self._run_and_sample(6, 2)
        self.assertEqual(rc, 0, out)
        self.assertGreater(len(ages), 6, out)
        self.assertLess(max(ages), 4.5, ages)
        self.assertTrue(self.is_free())

    @unittest.skipUnless(SLOW, "set LOOP_LOCK_SLOW_TESTS=1 (~135 s)")
    def test_run_sleep_130_real_scale(self):
        rc, out, ages = self._run_and_sample(130, 60)
        self.assertEqual(rc, 0, out)
        self.assertGreater(len(ages), 100, out)
        self.assertGreater(max(ages), 55, "the sampler never saw a heartbeat age near the interval")
        self.assertLess(max(ages), 70, max(ages))
        self.assertTrue(self.is_free())


class TestRunDetached(LockTestBase):
    def _wait_marker(self, marker, seconds=60):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if os.path.exists(marker):
                return _read(marker)
            time.sleep(0.25)
        self.fail("marker %s never appeared" % marker)

    def test_detached_renews_releases_and_writes_exit_code(self):
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("bash '%s' take gate\nsleep 6\nbash '%s' release gate\nexit 4\n" % (LOCK_SH, LOCK_SH))
        marker = os.path.join(self.tmp, "job.done")
        p = subprocess.run([BASH, DETACHED_SH, "--owner", "det", fwd(job), fwd(marker)],
                           capture_output=True, text=True, env=self.env(LOOP_LOCK_DETACHED_RENEW_SEC=2),
                           timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("DETACHED", p.stdout)
        epoch = int(self.record()[2])
        time.sleep(4.5)
        rec = self.record()
        self.assertEqual(rec[0], "det")
        self.assertGreater(int(rec[2]), epoch, "heartbeat not renewed while the job ran")
        self.assertEqual(self._wait_marker(marker).strip(), "exit=4")
        self.assertTrue(self.is_free())
        self.assertIn("NESTED under det", _read(marker + ".log"))

    def test_detached_reports_lock_lost_loudly(self):
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("sleep 5\nexit 0\n")
        marker = os.path.join(self.tmp, "job.done")
        p = subprocess.run([BASH, DETACHED_SH, "--owner", "det", fwd(job), fwd(marker)],
                           capture_output=True, text=True, env=self.env(LOOP_LOCK_DETACHED_RENEW_SEC=1), timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        det_id = self.sh("id")[1].strip()
        self.assertEqual(self.sh("_release_id", det_id)[0], 0)
        self.assertEqual(self.sh("take", "thief")[0], 0)
        self.assertEqual(self._wait_marker(marker).strip(), "exit=0 LOCK_LOST")
        self.assertIn("LOCK LOST", _read(marker + ".LOCK_LOST"))
        self.assertIn("LOCK LOST", _read(marker + ".log"))
        self.assertEqual(self.record()[0], "thief")

    def test_detached_on_busy_lock_writes_marker_and_does_not_launch(self):
        self.write_record("worker", 60, hb_age_s=0)
        ran = os.path.join(self.tmp, "ran")
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("touch '%s'\n" % fwd(ran))
        marker = os.path.join(self.tmp, "job.done")
        p = subprocess.run([BASH, DETACHED_SH, fwd(job), fwd(marker)], capture_output=True, text=True,
                           env=self.env(), timeout=30)
        self.assertEqual(p.returncode, 75, p.stdout)
        self.assertTrue(_read(marker).startswith("exit=75 BUSY"))
        time.sleep(1)
        self.assertFalse(os.path.exists(ran))

    @unittest.skipUnless(POWERSHELL, "Windows PowerShell not available")
    def test_signal_kills_the_job_tree_then_releases(self):
        # Minor 1: TERM to the detached wrapper must take the job's children with it, not just its bash.
        marker_word = "s5t0_detached_grandchild_%d" % os.getpid()
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("'%s' -c 'import time; time.sleep(120)' %s\n" % (fwd(sys.executable), marker_word))
        marker = os.path.join(self.tmp, "job.done")
        p = subprocess.run([BASH, DETACHED_SH, "--owner", "sig", fwd(job), fwd(marker)],
                           capture_output=True, text=True, env=self.env(), timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        pid = re.search(r"DETACHED pid=(\d+)", p.stdout).group(1)
        try:
            deadline = time.time() + 30
            while not processes_with(marker_word) and time.time() < deadline:
                time.sleep(0.5)
            self.assertTrue(processes_with(marker_word), "the job never started")
            subprocess.run([BASH, "-c", "kill -TERM %s" % pid], timeout=30)
            self.assertEqual(self._wait_marker(marker, 60).strip(), "exit=143")
            time.sleep(1.0)
            self.assertEqual(processes_with(marker_word), [], "the job's child survived the signal")
            self.assertTrue(self.is_free())
        finally:
            for wp in processes_with(marker_word):
                subprocess.run(["taskkill", "/F", "/PID", wp], capture_output=True)

    # -- Sprint 5 R46/A5: disk refusal, quiet marker, host CPU sampler --------------------------

    def test_disk_refusal_below_threshold_does_not_launch(self):
        job = os.path.join(self.tmp, "job.sh")
        ran = os.path.join(self.tmp, "ran")
        with open(job, "w", newline="\n") as f:
            f.write("touch '%s'\nexit 0\n" % fwd(ran))
        marker = os.path.join(self.tmp, "job.done")
        env = self.env(RUN_FREE_GB_CMD="echo 1.0", RUN_MIN_FREE_GB=4)
        p = subprocess.run([BASH, DETACHED_SH, fwd(job), fwd(marker)], capture_output=True, text=True,
                           env=env, timeout=30)
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("REFUSED", p.stdout)
        self.assertIn("1.0", p.stdout)
        self.assertTrue(_read(marker).startswith("exit=3"), _read(marker))
        time.sleep(0.5)
        self.assertFalse(os.path.exists(ran), "the job must not launch below the free-space floor")
        self.assertTrue(self.is_free(), "a refused run must never take the lock")

    def test_disk_refusal_threshold_moves_with_run_min_free_gb(self):
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("exit 0\n")
        marker = os.path.join(self.tmp, "job.done")
        env = self.env(RUN_FREE_GB_CMD="echo 9.0", RUN_MIN_FREE_GB=20)
        p = subprocess.run([BASH, DETACHED_SH, fwd(job), fwd(marker)], capture_output=True, text=True,
                           env=env, timeout=30)
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)

    def test_enough_free_space_launches_normally(self):
        job = os.path.join(self.tmp, "job.sh")
        ran = os.path.join(self.tmp, "ran")
        with open(job, "w", newline="\n") as f:
            f.write("touch '%s'\nexit 0\n" % fwd(ran))
        marker = os.path.join(self.tmp, "job.done")
        env = self.env(RUN_FREE_GB_CMD="echo 500", RUN_MIN_FREE_GB=4)
        p = subprocess.run([BASH, DETACHED_SH, fwd(job), fwd(marker)], capture_output=True, text=True,
                           env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self._wait_marker(marker).strip(), "exit=0")
        self.assertTrue(os.path.exists(ran))

    def _quiet_env(self, quiet_marker, **extra):
        return self.env(RUN_FREE_GB_CMD="echo 500", RUN_QUIET_MARKER=fwd(quiet_marker),
                        RUN_CPU_SAMPLER=0, **extra)

    def test_quiet_marker_written_for_launch_purpose_and_removed_on_exit(self):
        quiet = os.path.join(self.tmp, "quiet_marker")
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("sleep 3\nexit 0\n")
        marker = os.path.join(self.tmp, "job.done")
        env = self._quiet_env(quiet)
        p = subprocess.run([BASH, DETACHED_SH, "--owner", "launcher", "--purpose", "launch1_frostfire",
                            fwd(job), fwd(marker)], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        deadline = time.time() + 10
        while not os.path.exists(quiet) and time.time() < deadline:
            time.sleep(0.1)
        self.assertTrue(os.path.exists(quiet), "logs/.quiet (or its override) was never written")
        fields = _read(quiet).split()
        self.assertEqual(fields[0], "launcher")
        self.assertTrue(fields[1].isdigit(), fields)
        self.assertTrue(fields[2].isdigit(), fields)
        self.assertAlmostEqual(int(fields[2]), int(time.time()), delta=15)
        self._wait_marker(marker)
        time.sleep(0.5)
        self.assertFalse(os.path.exists(quiet), "the quiet marker must be removed on exit")

    def test_quiet_flag_writes_marker_even_for_a_non_launch_purpose(self):
        quiet = os.path.join(self.tmp, "quiet_marker")
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("sleep 1\nexit 0\n")
        marker = os.path.join(self.tmp, "job.done")
        env = self._quiet_env(quiet)
        p = subprocess.run([BASH, DETACHED_SH, "--purpose", "some other work", "--quiet",
                            fwd(job), fwd(marker)], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        deadline = time.time() + 10
        while not os.path.exists(quiet) and time.time() < deadline:
            time.sleep(0.1)
        self.assertTrue(os.path.exists(quiet))
        self._wait_marker(marker)

    def test_no_quiet_marker_for_an_ordinary_purpose(self):
        quiet = os.path.join(self.tmp, "quiet_marker")
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("sleep 1\nexit 0\n")
        marker = os.path.join(self.tmp, "job.done")
        env = self._quiet_env(quiet)
        p = subprocess.run([BASH, DETACHED_SH, "--purpose", "a build", fwd(job), fwd(marker)],
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self._wait_marker(marker)
        self.assertFalse(os.path.exists(quiet))

    def test_quiet_marker_removed_on_signal(self):
        quiet = os.path.join(self.tmp, "quiet_marker")
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("sleep 30\nexit 0\n")
        marker = os.path.join(self.tmp, "job.done")
        env = self._quiet_env(quiet)
        p = subprocess.run([BASH, DETACHED_SH, "--owner", "sig2", "--purpose", "launch_sig", fwd(job),
                            fwd(marker)], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        pid = re.search(r"DETACHED pid=(\d+)", p.stdout).group(1)
        deadline = time.time() + 10
        while not os.path.exists(quiet) and time.time() < deadline:
            time.sleep(0.1)
        self.assertTrue(os.path.exists(quiet))
        subprocess.run([BASH, "-c", "kill -TERM %s" % pid], timeout=30)
        self.assertEqual(self._wait_marker(marker, 60).strip(), "exit=143")
        time.sleep(0.5)
        self.assertFalse(os.path.exists(quiet), "signalled exit must also remove the quiet marker")

    @unittest.skipUnless(POWERSHELL, "Windows PowerShell not available")
    def test_quiet_marker_pid_is_real_and_check_quiet_gate_refuses_against_it_no_mocks(self):
        # Review round 1 Critical, 2026-09-13: run_detached.sh wrote the MSYS bash pid ($job) into
        # the .quiet marker, but check_quiet_gate.sh (and any real host tool) probes Windows pids
        # via tasklist -- those are different numbers, so the gate never found the job and always
        # proceeded, silently disabling R46/A8 while a launch ran. No env fakes here: a real job,
        # the script's own default RUN_QUIET_MARKER-overridden-to-temp-file, and the REAL
        # tasklist.exe (no QUIET_GATE_TASKLIST_CMD override).
        quiet = os.path.join(self.tmp, "quiet_marker")
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("sleep 6\nexit 0\n")
        marker = os.path.join(self.tmp, "job.done")
        env = self.env(RUN_FREE_GB_CMD="echo 500", RUN_QUIET_MARKER=fwd(quiet), RUN_CPU_SAMPLER=0)
        p = subprocess.run([BASH, DETACHED_SH, "--owner", "integ", "--purpose", "launch_integ",
                            fwd(job), fwd(marker)], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        deadline = time.time() + 10
        while not os.path.exists(quiet) and time.time() < deadline:
            time.sleep(0.1)
        self.assertTrue(os.path.exists(quiet), "quiet marker never appeared")

        # No QUIET_GATE_TASKLIST_CMD: this hits the real tasklist.exe against the real marker pid.
        check_env = dict(os.environ)
        check_env.pop("QUIET_GATE_TASKLIST_CMD", None)
        while_alive = subprocess.run([BASH, QUIET_GATE_SH, fwd(quiet)], capture_output=True, text=True,
                                     env=check_env, timeout=30)
        self.assertEqual(while_alive.returncode, 3, "check_quiet_gate did not refuse against a "
                         "running launch (real tasklist output follows): " +
                         while_alive.stdout + while_alive.stderr)

        self._wait_marker(marker, 20)
        time.sleep(0.5)
        after_exit = subprocess.run([BASH, QUIET_GATE_SH, fwd(quiet)], capture_output=True, text=True,
                                    env=check_env, timeout=30)
        self.assertEqual(after_exit.returncode, 0, after_exit.stdout + after_exit.stderr)

    def test_cpu_sampler_disabled_by_env_writes_no_csv(self):
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("sleep 2\nexit 0\n")
        marker = os.path.join(self.tmp, "job.done")
        env = self.env(RUN_FREE_GB_CMD="echo 500", RUN_CPU_SAMPLER=0)
        p = subprocess.run([BASH, DETACHED_SH, fwd(job), fwd(marker)], capture_output=True, text=True,
                           env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self._wait_marker(marker)
        self.assertFalse(os.path.exists(marker + ".cpu.csv"))

    @unittest.skipUnless(POWERSHELL, "Windows PowerShell not available")
    def test_cpu_sampler_writes_rows_and_is_killed_on_exit(self):
        job = os.path.join(self.tmp, "job.sh")
        with open(job, "w", newline="\n") as f:
            f.write("sleep 4\nexit 0\n")
        marker = os.path.join(self.tmp, "job.done")
        env = self.env(RUN_FREE_GB_CMD="echo 500")
        p = subprocess.run([BASH, DETACHED_SH, fwd(job), fwd(marker)], capture_output=True, text=True,
                           env=env, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self._wait_marker(marker)
        csv = marker + ".cpu.csv"
        deadline = time.time() + 10
        while not os.path.exists(csv) and time.time() < deadline:
            time.sleep(0.2)
        self.assertTrue(os.path.exists(csv), "no CPU sampler csv was written")
        rows = [l for l in _read(csv).splitlines() if l.strip()]
        self.assertGreaterEqual(len(rows), 1, rows)
        self.assertGreaterEqual(rows[0].count(","), 1, rows[0])
        # It must not still be running (and thus growing) well after the job ended.
        n = len(rows)
        time.sleep(2.5)
        rows_after = [l for l in _read(csv).splitlines() if l.strip()]
        self.assertLessEqual(len(rows_after), n + 1, "sampler kept appending after the job exited")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell not available")
class TestKillStaleDrivers(unittest.TestCase):
    def setUp(self):
        smoke_or_slow(self)

    def ps(self, *args):
        return [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", KILL_PS1] + list(args)

    def test_kills_drivers_spares_scorers_and_its_own_ancestors(self):
        marker = "s5t0_kill_decoy_%d" % os.getpid()
        sleep = "import time; time.sleep(120)"
        driver = subprocess.Popen([sys.executable, "-c", sleep, "-m", "tools_py.parity.drive", marker])
        scorer = subprocess.Popen([sys.executable, "-c", sleep, "-m", "tools_py.parity.verdict_core", marker])
        bystander = subprocess.Popen([sys.executable, "-c", sleep, "-m", "tools_py.parity.drive", "bystander"])
        try:
            time.sleep(1.5)
            dry = subprocess.run(self.ps("-DryRun", "-OnlyCommandLineContaining", marker,
                                         "-ExeNamePattern", "no_such_exe_*.exe"),
                                 capture_output=True, text=True, timeout=60)
            self.assertIn("WOULD KILL", dry.stdout)
            self.assertIsNone(driver.poll())
            # The killer runs as a child of a python that itself looks like a driver (a gate calling it):
            # that ancestor must survive.
            code = ("import subprocess,sys; r=subprocess.run(sys.argv[4:], capture_output=True, text=True); "
                    "print(r.stdout); sys.exit(r.returncode)")
            real = subprocess.run([sys.executable, "-c", code, "-m", "tools_py.parity.gate", marker]
                                  + self.ps("-OnlyCommandLineContaining", marker, "-ExeNamePattern", "no_such_exe_*.exe"),
                                  capture_output=True, text=True, timeout=90)
            self.assertEqual(real.returncode, 0, real.stdout + real.stderr)
            self.assertRegex(real.stdout, r"KILLED .*tools_py\.parity\.drive")
            self.assertRegex(real.stdout, r"SKIPPED .*verdict_core.*\(not a driver module\)")
            self.assertRegex(real.stdout, r"SKIPPED .*tools_py\.parity\.gate.*\(ancestor of this script\)")
            driver.wait(timeout=10)
            self.assertIsNone(scorer.poll(), "killed a lock-free scorer")
            self.assertIsNone(bystander.poll(), "killed a process outside the test's marker")
        finally:
            for p in (driver, scorer, bystander):
                if p.poll() is None:
                    p.kill()
                p.wait(timeout=10)


class TestSlowSuiteStamp(unittest.TestCase):
    """Ruling R73: the slow suite is opt-in, so an edit to scripts/loop_lock.sh must not ship on the smoke alone.
    fixtures/loop_lock_slow_green.txt records the script's git blob at the last GREEN
    `LOOP_LOCK_SLOW_TESTS=1 python -m unittest tools_py.tests.test_loop_lock`; any other blob fails here."""

    STAMP = os.path.join(ROOT, "tools_py", "tests", "fixtures", "loop_lock_slow_green.txt")

    def test_loop_lock_sh_blob_matches_the_last_green_slow_run(self):
        if SLOW:
            self.skipTest("this is the slow run itself: write the stamp only after it is green")
        if os.environ.get("LOOP_LOCK_TEST_SCRIPTS"):
            self.skipTest("LOOP_LOCK_TEST_SCRIPTS points at another copy of the scripts")
        git = shutil.which("git")
        if not git:
            self.skipTest("git not found")
        p = subprocess.run([git, "hash-object", "scripts/loop_lock.sh"], cwd=ROOT, capture_output=True, text=True,
                           timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        blob = p.stdout.strip()
        self.assertTrue(os.path.exists(self.STAMP), "no stamp: run the slow suite, then record %s" % self.STAMP)
        stamped = [l.split()[1] for l in _read(self.STAMP).splitlines() if l.startswith("blob ")]
        self.assertEqual(stamped, [blob],
                         "scripts/loop_lock.sh (blob %s) differs from the last green slow run's %s: run "
                         "LOOP_LOCK_SLOW_TESTS=1 python -m unittest tools_py.tests.test_loop_lock and, only if it "
                         "is green, update %s" % (blob, stamped, self.STAMP))


if __name__ == "__main__":
    unittest.main()
