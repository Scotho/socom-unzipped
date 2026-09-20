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
