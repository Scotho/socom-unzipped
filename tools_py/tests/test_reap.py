"""The SessionEnd/Stop reaper (Sprint 14 G3): tools_py/hooks/reap.py.

On 2026-09-25 the host carried 213 orphaned tail/grep watchers left by dead monitors, the oldest from 09-17, and
every bash start took seconds (the autonomy review's note 02 section 4.5; the memory rule "kill orphans only, never
bash.exe"). The reaper kills an orphaned watcher and nothing else; these tests plant the table and assert the list.
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tools_py.hooks import reap

# The plan's planted table: twelve rows. Pids 100/101/102 are the three live bashes; 900-904 are dead parents.
PLANTED = [
    # five orphaned watchers (their parent shell is gone) -- the kill list
    (201, 900, "tail -F logs/run_a.log"),
    (202, 901, "grep --line-buffered FAIL"),
    (203, 902, "/usr/bin/tail -F logs/run_b.log"),
    (204, 903, "/usr/bin/grep --line-buffered -E ERROR|WARN"),
    (205, 1, "tail -F logs/run_c.log"),
    # two live watchers under a live bash -- kept
    (301, 101, "tail -F logs/live.log"),
    (302, 101, "grep --line-buffered done"),
    # three live bashes -- kept
    (100, 1, "/usr/bin/bash"),
    (101, 100, "/usr/bin/bash"),
    (102, 1, "bash -c scripts/loop_lock.sh run chain"),
    # one orphaned bash -- kept (never a shell)
    (401, 904, "/usr/bin/bash"),
    # one orphaned python -- kept (never a python)
    (402, 904, "python -m tools_py.parity.drive_menu"),
]

# Captured from this host with `ps -ef` on 2026-09-26 (Git Bash, MSYS ps), trimmed to nine rows and scrubbed: the
# UID column and the user's home directory are replaced. Note what MSYS ps prints: UID PID PPID TTY STIME COMMAND --
# no PGID/WINPID columns, the COMMAND is the executable's path WITHOUT its arguments, and STIME is two tokens
# ("Sep 21") for a process started before today.
PS_SAMPLE = """\
     UID     PID    PPID  TTY        STIME COMMAND
    user   12479   12373 ?        15:24:35 /usr/bin/tail
    user   51481   51475 ?        10:13:57 /usr/bin/grep
    user   13474       1 ?        02:35:49 /usr/bin/bash
    user      55   65534 ?        18:35:07 /usr/bin/grep
    user   51475       1 ?        10:13:57 /usr/bin/bash
    user    9710    9708 ?          Sep 21 /usr/bin/tail
    user   46457   46449 ?          Sep 23 /usr/bin/tail
    user   20001   13474 pty0     16:02:11 /c/Users/user/AppData/Local/Programs/Python/Python313/python
    user   20002   13474 ?        16:02:12 /c/Program Files/Git/usr/bin/sleep
"""


class KillListTest(unittest.TestCase):
    def test_planted_table_kills_exactly_the_five_orphaned_watchers(self):
        self.assertEqual(sorted(reap.kill_list(PLANTED, self_pids=())), [201, 202, 203, 204, 205])

    def test_empty_table(self):
        self.assertEqual(reap.kill_list([], self_pids=()), [])

    def test_every_watcher_live(self):
        table = [(10, 1, "bash"), (11, 10, "tail -F x"), (12, 10, "grep --line-buffered y"), (13, 10, "sleep 5")]
        self.assertEqual(reap.kill_list(table, self_pids=()), [])

    def test_never_a_shell_python_or_git_even_orphaned(self):
        table = [(10, 999, "bash"), (11, 999, "/usr/bin/sh"), (12, 999, "python3 x.py"), (13, 999, "git.exe"),
                 (14, 1, "/usr/bin/bash.exe")]
        self.assertEqual(reap.kill_list(table, self_pids=()), [])

    def test_all_four_watcher_names_and_exe_suffix(self):
        table = [(10, 999, "tail"), (11, 999, "grep.exe"), (12, 999, "/usr/bin/sleep 300"), (13, 999, "inotifywait")]
        self.assertEqual(sorted(reap.kill_list(table, self_pids=())), [10, 11, 12, 13])

    def test_a_live_lock_holders_watcher_is_kept(self):
        # A chain run by loop_lock.sh: its watcher's parent is in the table, so it is not orphaned in the first
        # place -- the protect set is belt and braces, and it also keeps a watcher whose holder shell is missing
        # from this snapshot (a race between the record and ps).
        table = [(500, 1, "/usr/bin/bash"), (501, 500, "tail -F logs/chain.log")]
        self.assertEqual(reap.kill_list(table, protect=(500,), self_pids=()), [])
        raced = [(501, 500, "tail -F logs/chain.log"), (502, 500, "grep --line-buffered x")]
        self.assertEqual(reap.kill_list(raced, protect=(500,), self_pids=()), [])
        self.assertEqual(sorted(reap.kill_list(raced, self_pids=())), [501, 502])

    def test_never_pid_one_or_our_own_pids(self):
        table = [(1, 0, "sleep"), (77, 999, "sleep 300"), (78, 999, "sleep 300")]
        self.assertEqual(reap.kill_list(table, self_pids=(77,)), [78])


class LockHolderTest(unittest.TestCase):
    def test_reads_the_pid_from_the_records_take_id(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            lock = os.path.join(d, ".loop_lock")
            with mock.patch.dict(os.environ, {"LOOP_LOCK_PATH": lock}):
                self.assertEqual(reap.lock_holder_pids(), ())  # no record: nothing protected, no error
                os.mkdir(lock + ".d")
                with open(os.path.join(lock + ".d", "record"), "w") as f:
                    f.write("s14-chain 1790000000-4242x1234 1790000100 night chain\n")
                self.assertEqual(reap.lock_holder_pids(), (4242,))


class ParsePsTest(unittest.TestCase):
    def test_parses_the_captured_sample(self):
        table = reap.parse_ps(PS_SAMPLE)
        self.assertEqual(len(table), 9)
        self.assertEqual(table[0], (12479, 12373, "/usr/bin/tail"))
        self.assertEqual(table[5], (9710, 9708, "/usr/bin/tail"))
        self.assertEqual(table[7][2], "/c/Users/user/AppData/Local/Programs/Python/Python313/python")
        self.assertEqual(table[8], (20002, 13474, "/c/Program Files/Git/usr/bin/sleep"))

    def test_the_sample_through_kill_list(self):
        # 12479, 51481 (parent 51475 is present -- live), 55, 9710, 46457: the orphans are the four watchers whose
        # parent is absent; the sleep under a live bash stays (its path has a space: the basename still reads).
        self.assertEqual(sorted(reap.kill_list(reap.parse_ps(PS_SAMPLE), self_pids=())), [55, 9710, 12479, 46457])

    def test_garbage_lines_are_skipped(self):
        self.assertEqual(reap.parse_ps("nonsense\n\n  x y z\n"), [])


class MainTest(unittest.TestCase):
    def run_main(self, **kw):
        out = io.StringIO()
        with redirect_stdout(out):
            code = reap.main(**kw)
        return code, out.getvalue()

    def test_kills_and_prints_one_line(self):
        killed = []
        code, out = self.run_main(read_table=lambda: PLANTED, kill=lambda pids: killed.extend(pids) or list(pids),
                                  protect=lambda: ())
        self.assertEqual(code, 0)
        self.assertEqual(out, "reap: killed 5 watchers (pids 201 202 203 204 205)\n")
        self.assertEqual(killed, [201, 202, 203, 204, 205])

    def test_nothing_to_kill(self):
        def no_kill(pids):
            raise AssertionError("kill called with nothing to kill")
        code, out = self.run_main(read_table=lambda: PLANTED[5:], kill=no_kill, protect=lambda: ())
        self.assertEqual((code, out), (0, "reap: nothing to kill\n"))

    def test_any_exception_is_one_skipped_line_and_exit_0(self):
        def boom():
            raise OSError("ps not found")
        code, out = self.run_main(read_table=boom, kill=lambda p: p, protect=lambda: ())
        self.assertEqual((code, out), (0, "reap: skipped: ps not found\n"))

    def test_default_seams_are_patchable(self):
        with mock.patch.object(reap, "read_table", return_value=[(9, 999, "tail -F x")]), \
             mock.patch.object(reap, "kill_pids", return_value=[9]) as k, \
             mock.patch.object(reap, "lock_holder_pids", return_value=()):
            code, out = self.run_main()
        self.assertEqual((code, out), (0, "reap: killed 1 watchers (pids 9)\n"))
        k.assert_called_once_with([9])


if __name__ == "__main__":
    unittest.main()
