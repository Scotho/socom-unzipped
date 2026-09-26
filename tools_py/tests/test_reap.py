"""The SessionEnd/Stop reaper (Sprint 14 G3): tools_py/hooks/reap.py.

On 2026-09-25 the host carried 213 orphaned tail/grep watchers left by dead monitors, the oldest from 09-17, and
every bash start took seconds (the autonomy review's note 02 section 4.5; the memory rule "kill orphans only, never
bash.exe"). The reaper kills an orphaned watcher and nothing else; these tests plant the table and assert the list.

Rows are (pid, ppid, pgid, command) from `ps -W` in Git Bash.
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tools_py.hooks import reap

# The plan's planted table: twelve rows. Pids 100/101/102 are the three live bashes; 900-904 are dead parents.
PLANTED = [
    # five orphaned watchers (their parent shell is gone) -- the kill list
    (201, 900, 900, "/usr/bin/tail -F logs/run_a.log"),
    (202, 901, 901, "/usr/bin/grep --line-buffered FAIL"),
    (203, 902, 902, "/usr/bin/tail -F logs/run_b.log"),
    (204, 903, 903, "/usr/bin/grep --line-buffered -E ERROR|WARN"),
    (205, 1, 880, "/usr/bin/tail -F logs/run_c.log"),  # a bash that exited normally: ppid 1, the dead shell's group
    # two live watchers under a live bash -- kept
    (301, 101, 100, "/usr/bin/tail -F logs/live.log"),
    (302, 101, 100, "/usr/bin/grep --line-buffered done"),
    # three live bashes -- kept
    (100, 1, 100, "/usr/bin/bash"),
    (101, 100, 100, "/usr/bin/bash"),
    (102, 1, 102, "/usr/bin/bash -c scripts/loop_lock.sh run chain"),
    # one orphaned bash -- kept (never a shell)
    (401, 904, 904, "/usr/bin/bash"),
    # one orphaned python -- kept (never a python)
    (402, 904, 904, "/c/Users/user/AppData/Local/Programs/Python/Python313/python -m tools_py.parity.drive_menu"),
]

# Captured from this host with `ps -W` on 2026-09-26 (Git Bash, MSYS ps), trimmed and scrubbed (the user's home
# directory replaced). MSYS `ps -W` prints PID PPID PGID WINPID TTY UID STIME COMMAND; it lists native Windows
# processes too (a C:\ path, ppid 0); the COMMAND is the executable's path WITHOUT its arguments; STIME is two
# tokens ("Sep 15") for a process started before today. Row 54854 is a `tail` orphaned by a `bash -c '... & disown'`
# (ppid 1, the dead shell's group 54832); row 54861 is a `sleep.exe` started by PowerShell's Start-Process (ppid 1,
# its own group leader, TTY cons0).
PS_SAMPLE = """\
      PID    PPID    PGID     WINPID   TTY         UID    STIME COMMAND
    65540       0       0          4  ?              0   Sep 15 System
    66816       0       0       1280  ?              0   Sep 15 C:\\Windows\\System32\\smss.exe
    51475       1   51386      67288  ?         197609 10:13:57 /usr/bin/bash
    51478   51475   51386      28548  ?         197609 10:13:57 /usr/bin/tail
    51481   51475   51386       5468  ?         197609 10:13:57 /usr/bin/grep
    54602   54576   54576      58364  ?         197609 03:42:20 /c/Users/user/AppData/Local/Microsoft/WindowsApps/python
    54854       1   54832      25568  ?         197609 03:42:46 /usr/bin/tail
    54861       1   54861      13416  cons0     197609 03:42:47 /usr/bin/sleep
"""


class KillListTest(unittest.TestCase):
    def test_planted_table_kills_exactly_the_five_orphaned_watchers(self):
        self.assertEqual(sorted(reap.kill_list(PLANTED, self_pids=())), [201, 202, 203, 204, 205])

    def test_empty_table(self):
        self.assertEqual(reap.kill_list([], self_pids=()), [])

    def test_every_watcher_live(self):
        table = [(10, 1, 10, "/usr/bin/bash"), (11, 10, 10, "/usr/bin/tail -F x"),
                 (12, 10, 10, "/usr/bin/grep --line-buffered y"), (13, 10, 10, "/usr/bin/sleep 5")]
        self.assertEqual(reap.kill_list(table, self_pids=()), [])

    def test_never_a_shell_python_or_git_even_orphaned(self):
        table = [(10, 999, 999, "/usr/bin/bash"), (11, 999, 999, "/usr/bin/sh"), (12, 999, 999, "/usr/bin/python3"),
                 (13, 999, 999, "/mingw64/bin/git"), (14, 1, 900, "/usr/bin/bash.exe")]
        self.assertEqual(reap.kill_list(table, self_pids=()), [])

    def test_all_four_watcher_names_and_exe_suffix(self):
        table = [(10, 999, 999, "/usr/bin/tail"), (11, 999, 999, "/usr/bin/grep.exe"),
                 (12, 999, 999, "/c/Program Files/Git/usr/bin/sleep"), (13, 999, 999, "/usr/bin/inotifywait")]
        self.assertEqual(sorted(reap.kill_list(table, self_pids=())), [10, 11, 12, 13])

    def test_a_watcher_started_by_a_windows_program_is_kept(self):
        # PowerShell's `Start-Process sleep.exe 96` (reviewer, 2026-09-26): ppid 1 like a bash orphan, but it leads
        # its own process group. A bash orphan keeps the dead shell's group.
        windows_started = (54861, 1, 54861, "/usr/bin/sleep")
        bash_orphan = (54854, 1, 54832, "/usr/bin/tail")
        self.assertEqual(reap.kill_list([windows_started], self_pids=()), [])
        self.assertEqual(reap.kill_list([bash_orphan], self_pids=()), [54854])

    def test_a_native_windows_process_is_never_a_watcher(self):
        # `ps -W` lists native processes with a C:\ path and ppid 0 (never in the table): not ours, never killed.
        table = [(70000, 0, 0, "C:\\tools\\tail.exe"), (70001, 0, 0, "C:\\Windows\\System32\\sleep.exe"),
                 (70002, 0, 0, "grep")]
        self.assertEqual(reap.kill_list(table, self_pids=()), [])

    def test_never_pid_one_or_our_own_pids(self):
        table = [(1, 0, 0, "/usr/bin/sleep"), (77, 999, 999, "/usr/bin/sleep"), (78, 999, 999, "/usr/bin/sleep")]
        self.assertEqual(reap.kill_list(table, self_pids=(77,)), [78])


class ParsePsTest(unittest.TestCase):
    def test_parses_the_captured_sample(self):
        table = reap.parse_ps(PS_SAMPLE)
        self.assertEqual(len(table), 8)
        self.assertEqual(table[0], (65540, 0, 0, "System"))
        self.assertEqual(table[1][3], "C:\\Windows\\System32\\smss.exe")
        self.assertEqual(table[3], (51478, 51475, 51386, "/usr/bin/tail"))
        self.assertEqual(table[5][3], "/c/Users/user/AppData/Local/Microsoft/WindowsApps/python")
        self.assertEqual(table[7], (54861, 1, 54861, "/usr/bin/sleep"))

    def test_a_path_with_a_space_and_a_status_letter(self):
        row = "I   20002   13474   13474      41136  pty0      197609   Sep 21 /c/Program Files/Git/usr/bin/sleep\n"
        self.assertEqual(reap.parse_ps(row), [(20002, 13474, 13474, "/c/Program Files/Git/usr/bin/sleep")])

    def test_the_sample_through_kill_list(self):
        # the bash orphan (54854) goes; the Start-Process sleep (54861), the live tail/grep under 51475, the
        # python, and the native System/smss rows (ppid 0, absent) all stay.
        self.assertEqual(reap.kill_list(reap.parse_ps(PS_SAMPLE), self_pids=()), [54854])

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
        code, out = self.run_main(read_table=lambda: PLANTED, kill=lambda pids: killed.extend(pids) or list(pids))
        self.assertEqual(code, 0)
        self.assertEqual(out, "reap: killed 5 watchers (pids 201 202 203 204 205)\n")
        self.assertEqual(killed, [201, 202, 203, 204, 205])

    def test_nothing_to_kill(self):
        def no_kill(pids):
            raise AssertionError("kill called with nothing to kill")
        code, out = self.run_main(read_table=lambda: PLANTED[5:], kill=no_kill)
        self.assertEqual((code, out), (0, "reap: nothing to kill\n"))

    def test_any_exception_is_one_skipped_line_and_exit_0(self):
        def boom():
            raise OSError("ps not found")
        code, out = self.run_main(read_table=boom, kill=lambda p: p)
        self.assertEqual((code, out), (0, "reap: skipped: ps not found\n"))

    def test_default_seams_are_patchable(self):
        with mock.patch.object(reap, "read_table", return_value=[(9, 999, 999, "/usr/bin/tail")]), \
             mock.patch.object(reap, "kill_pids", return_value=[9]) as k:
            code, out = self.run_main()
        self.assertEqual((code, out), (0, "reap: killed 1 watchers (pids 9)\n"))
        k.assert_called_once_with([9])


if __name__ == "__main__":
    unittest.main()
