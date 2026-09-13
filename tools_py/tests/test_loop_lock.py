"""scripts/loop_lock.sh and scripts/run_detached.sh, driven through bash with fakes.

No game, no build, and never the real lock: every test points LOOP_LOCK_PATH at a temp dir and
LOOP_LOCK_PS_CMD at a fake process list (a file the test writes), and back-dates heartbeats by writing
the record directly.

The real-scale renewal test (`run -- sleep 130`, 60 s renew, heartbeat < 70 s throughout) costs ~135 s;
test_run_renews_heartbeat_scaled is the same property at a 2 s interval.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCK_SH = os.path.join(ROOT, "scripts", "loop_lock.sh").replace("\\", "/")
DETACHED_SH = os.path.join(ROOT, "scripts", "run_detached.sh").replace("\\", "/")
KILL_PS1 = os.path.join(ROOT, "scripts", "kill_stale_drivers.ps1")

IDLE = ["explorer.exe|C:\\Windows\\explorer.exe", "bash.exe|bash"]


def find_bash():
    # On Windows, a bare "bash" can resolve to WSL's System32\bash.exe; prefer Git Bash.
    for cand in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.exists(cand):
            return cand
    return shutil.which("bash")


BASH = find_bash()


def _read(path):
    with open(path) as f:
        return f.read()


def fwd(path):
    return path.replace("\\", "/")


@unittest.skipUnless(BASH, "bash not found")
class LockTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="loop_lock_test_")
        self.lock = os.path.join(self.tmp, "lk")
        self.procs = os.path.join(self.tmp, "procs.txt")
        self.set_procs(IDLE)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def set_procs(self, lines):
        with open(self.procs, "w", newline="\n") as f:
            f.write("\n".join(lines) + "\n")

    def env(self, **extra):
        env = dict(os.environ)
        env.pop("LOOP_LOCK_HELD", None)     # this suite may itself run under `loop_lock.sh run`
        env["LOOP_LOCK_PATH"] = fwd(self.lock)
        env["LOOP_LOCK_PS_CMD"] = "cat '%s'" % fwd(self.procs)
        env.update({k: str(v) for k, v in extra.items()})
        return env

    def sh(self, *args, env=None, timeout=60):
        p = subprocess.run([BASH, LOCK_SH] + list(args), capture_output=True, text=True,
                           env=env or self.env(), timeout=timeout)
        return p.returncode, p.stdout + p.stderr

    def write_record(self, owner, epoch_age_s, hb_age_s=None, purpose="", with_dir=True, legacy=False):
        now = int(time.time())
        if with_dir:
            os.makedirs(self.lock + ".d", exist_ok=True)
        with open(self.lock, "w", newline="\n") as f:
            if legacy:
                f.write("%s %d\n" % (owner, now - epoch_age_s))
            else:
                f.write("%s %d %d %s\n" % (owner, now - epoch_age_s, now - (hb_age_s if hb_age_s is not None else epoch_age_s), purpose))

    def record(self):
        with open(self.lock) as f:
            return f.read().split()

    def history(self):
        path = os.path.join(self.tmp, ".loop_lock_history")
        return _read(path) if os.path.exists(path) else ""


class TestTakeReapBreak(LockTestBase):
    def test_free_take_writes_four_field_record(self):
        rc, out = self.sh("take", "alice", "--purpose", "two words")
        self.assertEqual(rc, 0, out)
        self.assertIn("TAKEN by alice", out)
        rec = self.record()
        self.assertEqual(rec[0], "alice")
        self.assertEqual(rec[1], rec[2])
        self.assertEqual(rec[3:], ["two", "words"])
        self.assertTrue(os.path.isdir(self.lock + ".d"))

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
            "ld.lld.exe|ld.lld",
            "pcsx2-qt.exe|pcsx2-qt.exe",
            "ps2_recomp.exe|ps2_recomp.exe cfg",
            "ps2x_tests.exe|ps2x_tests.exe",
            "socom2_b.exe|socom2_b.exe",
        ]
        for line in busy_cases:
            with self.subTest(proc=line):
                self.write_record("worker", 3600, hb_age_s=20 * 60)
                self.set_procs(IDLE + [line])
                rc, out = self.sh("take", "bob")
                self.assertEqual(rc, 1, out)
                self.assertIn("BUSY", out)
                self.assertIn("not reaped", out)
                self.assertEqual(self.record()[0], "worker")
        self.assertEqual(self.history(), "")

    def test_python_without_parity_or_unittest_is_not_busy(self):
        self.write_record("ghost", 3600, hb_age_s=20 * 60)
        self.set_procs(IDLE + ["python.exe|python -m http.server"])
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 0, out)

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
        self.set_procs(IDLE + ["socom2.exe|dist\\socom2.exe"])
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 1, out)
        self.assertIn("stale break REFUSED", out)
        self.assertIn("socom2.exe", out)
        self.assertEqual(self.record()[0], "worker")

    def test_old_two_field_record_is_read(self):
        # Pre-Sprint-5 record, no claim dir: heartbeat = epoch, purpose empty.
        self.write_record("old", 5 * 60, with_dir=False, legacy=True)
        rc, out = self.sh("check")
        self.assertIn("HELD: old", out)
        self.assertIn("heartbeat 5 min", out)
        self.assertEqual(self.sh("take", "bob")[0], 1)
        self.assertTrue(os.path.exists(self.lock))
        self.assertFalse(os.path.isdir(self.lock + ".d"), "a BUSY take must not leave a claim dir")
        rc, out = self.sh("renew", "old")
        self.assertEqual(rc, 0, out)
        rec = self.record()
        self.assertEqual(len(rec), 3)
        self.assertLessEqual(int(time.time()) - int(rec[2]), 5)
        self.assertEqual(self.sh("release", "old")[0], 0)
        self.assertEqual(self.sh("check")[1].strip(), "FREE")

    def test_old_two_field_stale_record_is_reaped(self):
        self.write_record("old", 20 * 60, with_dir=False, legacy=True)
        rc, out = self.sh("take", "bob")
        self.assertEqual(rc, 0, out)
        self.assertIn("REAPED old", out)

    def test_non_holder_release_exits_1(self):
        self.assertEqual(self.sh("take", "alice")[0], 0)
        rc, out = self.sh("release", "mallory")
        self.assertEqual(rc, 1, out)
        self.assertIn("not held by mallory", out)
        self.assertEqual(self.record()[0], "alice")
        rc, _ = self.sh("release", "alice")
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(self.lock))
        self.assertFalse(os.path.exists(self.lock + ".d"))
        self.assertEqual(self.sh("release", "alice")[0], 1)

    def test_renew_by_non_holder_fails(self):
        self.write_record("alice", 600, hb_age_s=600)
        rc, out = self.sh("renew", "bob")
        self.assertEqual(rc, 1, out)

    def test_wait_times_out_then_succeeds(self):
        self.write_record("worker", 60, hb_age_s=0)
        rc, out = self.sh("wait", "bob", "2", env=self.env(LOOP_LOCK_WAIT_SEC=1))
        self.assertEqual(rc, 1, out)
        self.assertIn("TIMEOUT", out)
        self.sh("release", "worker")
        rc, out = self.sh("wait", "bob", "2", env=self.env(LOOP_LOCK_WAIT_SEC=1))
        self.assertEqual(rc, 0, out)


class TestRaces(LockTestBase):
    def _race(self, n=2):
        procs = [subprocess.Popen([BASH, LOCK_SH, "take", "racer%d" % i], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, env=self.env()) for i in range(n)]
        return [p.communicate(timeout=60)[0] for p in procs]

    def test_two_racing_takes_one_wins(self):
        for _ in range(6):
            outs = self._race()
            self.assertEqual(sum("TAKEN" in o for o in outs), 1, outs)
            self.sh("release", self.record()[0])

    def test_two_racing_reapers_one_wins(self):
        for _ in range(4):
            self.write_record("ghost", 3600, hb_age_s=30 * 60)
            outs = self._race()
            self.assertEqual(sum("TAKEN" in o for o in outs), 1, outs)
            self.sh("release", self.record()[0])


class TestRun(LockTestBase):
    def test_run_false_releases_and_exits_1(self):
        rc, out = self.sh("run", "runner", "--", "false")
        self.assertEqual(rc, 1, out)
        self.assertIn("TAKEN by runner", out)
        self.assertIn("RELEASED", out)
        self.assertEqual(self.sh("check")[1].strip(), "FREE")

    def test_run_returns_command_exit_code(self):
        rc, out = self.sh("run", "runner", "--purpose", "rc test", "--", "bash", "-c", "exit 7")
        self.assertEqual(rc, 7, out)
        self.assertEqual(self.sh("check")[1].strip(), "FREE")

    def test_run_on_busy_lock_does_not_run_command(self):
        self.write_record("worker", 60, hb_age_s=0)
        marker = fwd(os.path.join(self.tmp, "ran"))
        rc, out = self.sh("run", "runner", "--", "touch", marker)
        self.assertEqual(rc, 75, out)
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(self.record()[0], "worker")

    def test_nested_take_and_release_under_run(self):
        # gate.py takes and releases the lock itself; inside `run` that must not be BUSY.
        inner = "bash '%s' take gate && bash '%s' release gate && cat \"$LOOP_LOCK_PATH\"" % (LOCK_SH, LOCK_SH)
        rc, out = self.sh("run", "outer", "--", "bash", "-c", inner)
        self.assertEqual(rc, 0, out)
        self.assertIn("NESTED under outer", out)
        self.assertIn("outer keeps the lock", out)
        self.assertEqual(self.sh("check")[1].strip(), "FREE")

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
        while not os.path.exists(self.lock) and time.time() < deadline:
            time.sleep(0.1)
        while p.poll() is None:
            try:
                with open(self.lock) as f:
                    rec = f.read().split()
                if len(rec) >= 3:
                    ages.append(time.time() - int(rec[2]))
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        out = p.communicate()[0]
        return p.returncode, out, ages

    def test_run_renews_heartbeat_scaled(self):
        # The real-scale property (60 s renew, sleep 130, < 70 s) at 1/30 scale: 2 s renew, sleep 8, < 3.5 s.
        rc, out, ages = self._run_and_sample(8, 2)
        self.assertEqual(rc, 0, out)
        self.assertGreater(len(ages), 8, out)
        self.assertLess(max(ages), 3.5, ages)
        self.assertEqual(self.sh("check")[1].strip(), "FREE")

    def test_run_sleep_130_real_scale(self):
        rc, out, ages = self._run_and_sample(130, 60)
        self.assertEqual(rc, 0, out)
        self.assertGreater(len(ages), 100, out)
        self.assertGreater(max(ages), 55, "the sampler never saw a heartbeat age near the interval")
        self.assertLess(max(ages), 70, max(ages))
        self.assertEqual(self.sh("check")[1].strip(), "FREE")


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
        epoch = int(self.record()[1])
        time.sleep(4.5)
        rec = self.record()
        self.assertEqual(rec[0], "det")
        self.assertGreater(int(rec[2]), epoch, "heartbeat not renewed while the job ran")
        self.assertEqual(self._wait_marker(marker).strip(), "exit=4")
        self.assertEqual(self.sh("check")[1].strip(), "FREE")
        log = _read(marker + ".log")
        self.assertIn("NESTED under det", log)

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


@unittest.skipUnless(os.name == "nt" and (shutil.which("powershell.exe") or shutil.which("powershell")),
                     "Windows PowerShell not available")
class TestKillStaleDrivers(unittest.TestCase):
    def test_kills_only_the_marked_decoy(self):
        marker = "s5t0_kill_decoy_%d" % os.getpid()
        decoy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", marker])
        bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", "bystander"])
        try:
            time.sleep(1.0)
            ps = shutil.which("powershell.exe") or shutil.which("powershell")
            dry = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", KILL_PS1, "-DryRun",
                                  "-CommandLineMarker", marker, "-ExeNamePattern", "no_such_exe_*.exe"],
                                 capture_output=True, text=True, timeout=60)
            self.assertIn("WOULD KILL", dry.stdout)
            self.assertIsNone(decoy.poll())
            real = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", KILL_PS1,
                                   "-CommandLineMarker", marker, "-ExeNamePattern", "no_such_exe_*.exe"],
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(real.returncode, 0, real.stdout)
            self.assertIn("KILLED", real.stdout)
            decoy.wait(timeout=10)
            self.assertIsNone(bystander.poll(), "killed a process without the marker")
        finally:
            for p in (decoy, bystander):
                if p.poll() is None:
                    p.kill()
                p.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
