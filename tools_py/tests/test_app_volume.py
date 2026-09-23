"""The per-app session volume hold decides from names, volumes and mute flags alone (pycaw stays out of the tests)."""
import unittest

from tools_py.parity import app_volume


class Fake:
    def __init__(self, name, volume, mute=False):
        self.name, self.volume, self.mute = name, volume, mute


class PlanChangesTest(unittest.TestCase):
    def test_only_the_named_exe_is_touched_and_only_when_off(self):
        sessions = [Fake("steam.exe", 0.3), Fake("socom2.exe", 1.0), Fake("SOCOM2.EXE", 0.03), Fake("(system)", 0.12)]
        plan = app_volume.plan_changes(sessions, "socom2.exe")
        self.assertEqual([(s.name, v, u) for s, v, u in plan], [("SOCOM2.EXE", 1.0, False)])

    def test_a_muted_session_at_full_volume_is_unmuted_only(self):
        plan = app_volume.plan_changes([Fake("pcsx2-qt.exe", 1.0, mute=True)], "pcsx2-qt.exe")
        self.assertEqual([(v, u) for _s, v, u in plan], [(None, True)])

    def test_a_target_volume_below_full_is_honoured(self):
        plan = app_volume.plan_changes([Fake("socom2.exe", 1.0)], "socom2.exe", volume=0.5)
        self.assertEqual([(v, u) for _s, v, u in plan], [(0.5, False)])

    def test_hold_logs_the_first_reading_and_fixes_it(self):
        seen = {"n": 0}

        class S(Fake):
            def set_volume(self, v):
                self.volume = v

            def unmute(self):
                self.mute = False

        s = S("socom2.exe", 0.03, mute=True)
        orig = app_volume.live_sessions
        app_volume.live_sessions = lambda: [s]
        try:
            lines = []
            n = app_volume.cmd_hold("socom2.exe", seconds=0.3, volume=1.0, poll_s=0.1, log=lines.append)
        finally:
            app_volume.live_sessions = orig
        self.assertEqual(n, 1)
        self.assertEqual((s.volume, s.mute), (1.0, False))
        self.assertTrue(any("first seen: vol 0.03 mute 1" in ln for ln in lines), lines)
        self.assertTrue(lines[-1].startswith("hold done: 1 change(s), session seen"), lines[-1])


if __name__ == "__main__":
    unittest.main()


class SessionMonitorTest(unittest.TestCase):
    """Fix round 1, I5: a session LIST cannot prove contamination (pycaw returns inactive and expired sessions too);
    a timeline of state and peak level per session can. The pure half: rows in, the foreign sessions that were
    actually rendering out."""

    CSV = (
        "t_s,name,pid,state,peak\n"
        "0.0,socom2.exe,4100,1,0.2100\n"
        "0.0,chrome.exe,880,1,0.0000\n"
        "0.0,LEDKeeper2.exe,300,0,0.0000\n"
        "0.0,python3.13.exe,7777,1,0.2100\n"     # the recorder: its loopback session reads the endpoint's mix
        "5.0,socom2.exe,4100,1,0.1900\n"
        "5.0,chrome.exe,880,1,0.0800\n"
        "5.0,python3.13.exe,7777,1,0.2600\n"
        "10.0,socom2.exe,4100,1,0.2200\n"
        "10.0,chrome.exe,880,1,0.0700\n"
        "10.0,python3.13.exe,7777,1,0.2800\n"
        "15.0,socom2.exe,4100,1,0.2000\n"
        "15.0,chrome.exe,880,2,0.0000\n"
        "15.0,python3.13.exe,7777,1,0.2000\n"
    )
    ALLOWED = ("socom2.exe", "LEDKeeper2.exe", "(system)")

    def test_a_foreign_session_counts_only_while_active_with_a_peak_above_the_floor(self):
        rows = app_volume.parse_samples(self.CSV)
        self.assertEqual(len(rows), 13)
        foreign = app_volume.contamination(rows, allowed=self.ALLOWED, ignore_pids=(7777,))
        self.assertEqual([(f.name, f.first_s, f.last_s, f.samples) for f in foreign], [("chrome.exe", 5.0, 10.0, 2)],
                         "chrome rendered from 5 to 10 s; silent at 0, expired at 15; LEDKeeper2 is allowed and idle anyway")

    def test_the_recorder_is_excluded_by_pid_never_by_name(self):
        rows = app_volume.parse_samples(self.CSV)
        by_name = app_volume.contamination(rows, allowed=self.ALLOWED)
        self.assertEqual(sorted(f.name for f in by_name), ["chrome.exe", "python3.13.exe"],
                         "without the pid the recorder's loopback session reads as a source, at the endpoint's own level")
        other_python = app_volume.contamination(rows, allowed=self.ALLOWED, ignore_pids=(7778,))
        self.assertEqual(sorted(f.name for f in other_python), ["chrome.exe", "python3.13.exe"], "a different python is not excused")

    def test_a_clean_timeline_has_no_foreign_session(self):
        rows = app_volume.parse_samples("t_s,name,pid,state,peak\n0.0,socom2.exe,1,1,0.2\n5.0,(system),0,0,0.0\n")
        self.assertEqual(app_volume.contamination(rows, allowed=("socom2.exe", "(system)")), [])

    def test_the_old_four_column_form_still_reads_with_pid_zero(self):
        rows = app_volume.parse_samples("t_s,name,state,peak\n0.0,socom2.exe,1,0.2\n")
        self.assertEqual((rows[0].name, rows[0].pid, rows[0].state, rows[0].peak), ("socom2.exe", 0, 1, 0.2))

    def test_a_sample_line_is_one_row_per_session(self):
        class S:
            def __init__(self, name, pid, state, peak):
                self.name, self.pid, self.state, self.peak = name, pid, state, peak
        lines = app_volume.format_samples(12.5, [S("socom2.exe", 4100, 1, 0.21), S("chrome.exe", 880, 2, 0.0)])
        self.assertEqual(lines, ["12.5,socom2.exe,4100,1,0.2100", "12.5,chrome.exe,880,2,0.0000"])
