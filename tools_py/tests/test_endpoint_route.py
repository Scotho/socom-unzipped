"""Fix wave A (2026-09-22): the endpoint A/B's tool, tools_py/parity/endpoint_route.py. The registry and the audio
policy interface are not touched here; these are the selection and the refusal, which are what decide whether a
capture is scored as one leg of the A/B at all."""
import os
import subprocess
import sys
import unittest

from tools_py.parity import endpoint_route as er

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JBL_LINE = "[audio] 989snd mix stream open (48000 Hz stereo, device Speakers (JBL Flip 6), period 20 ms x 4, engine 48000 Hz)\n"
WIRED_LINE = "[audio] 989snd mix stream open (48000 Hz stereo, device Haut-parleurs (HyperX QuadCast S), period 20 ms x 4, engine 48000 Hz, dump C:\\x.wav)\n"


class TheRefusal(unittest.TestCase):
    def test_the_device_is_read_off_the_runs_own_line(self):
        self.assertEqual(er.mix_open_device("boot\n" + JBL_LINE + "more\n"), "Speakers (JBL Flip 6)")
        self.assertEqual(er.mix_open_device(WIRED_LINE), "Haut-parleurs (HyperX QuadCast S)")
        self.assertIsNone(er.mix_open_device("no audio line at all\n"))

    def test_a_run_on_the_wrong_device_is_refused(self):
        ok, msg = er.check_device(JBL_LINE, "HyperX")
        self.assertFalse(ok)
        self.assertIn("JBL Flip 6", msg)
        self.assertIn("not scored", msg)

    def test_a_run_with_no_line_is_refused_as_unknown(self):
        ok, msg = er.check_device("nothing\n", "HyperX")
        self.assertFalse(ok)
        self.assertIn("unknown", msg)

    def test_the_right_device_passes_case_insensitively(self):
        ok, msg = er.check_device(WIRED_LINE, "hyperx")
        self.assertTrue(ok, msg)

    def test_check_is_a_command_with_exit_5(self):
        log = os.path.join(ROOT, "logs", "parity", "test_endpoint_route_check.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "w", encoding="utf-8") as f:
            f.write(JBL_LINE)
        try:
            p = subprocess.run([sys.executable, "-m", "tools_py.parity.endpoint_route", "check", log, "--expect", "HyperX"],
                               cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 5, p.stdout + p.stderr)
            self.assertIn("REFUSED", p.stdout)
            p = subprocess.run([sys.executable, "-m", "tools_py.parity.endpoint_route", "check", log, "--expect", "JBL"],
                               cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        finally:
            os.remove(log)


class TheSelection(unittest.TestCase):
    ENTRIES = {
        "2130659e_0": r"{2}.\\?\bthenum#x\src/00010001|\Device\HarddiskVolume3\Projects\socom_pc\dist\socom2.exe%b{0}",
        "40efcb24_0": r"{2}.\\?\bthenum#x\src/00010001|\Device\HarddiskVolume3\Projects\socom_pc\third_party\ps2recomp\build-clang\ps2xRuntime\ps2EntryRunner.exe%b{0}",
        "6aafc465_0": r"{2}.\\?\hdaudio#y\rtspdiftopo/00010001|\Device\HarddiskVolume3\Projects\socom_pc\dist\socom2.exe%b{0}",
        "ea4c56d4_0": r"{2}.\\?\bthenum#x\src/00010001|\Device\HarddiskVolume3\Projects\wt-menu-movie\socom_pc\dist\socom2.exe%b{0}",
        "aaaa0000_0": r"{2}.\\?\bthenum#x\src/00010001|\Device\HarddiskVolume3\Users\U\Downloads\socom2-portable\socom2\socom2.exe%b{0}",
        "bbbb0000_0": r"{2}.\\?\bthenum#x\src/00010001|\Device\HarddiskVolume3\Projects\socom_pc\tools\pcsx2\pcsx2-qt.exe%b{0}",
    }

    def test_only_the_entries_for_the_exes_the_harness_launches_are_chosen(self):
        # every device's entry for dist\socom2.exe and the runner's; not a worktree's copy, not the owner's
        # Downloads copy, not PCSX2 (KNOWN section 4: the PCSX2 A entry was removed once already, and restored)
        self.assertEqual(er.entries_for_our_exes(self.ENTRIES), ["2130659e_0", "40efcb24_0", "6aafc465_0"])

    def test_the_device_must_match_exactly_one_active_render_endpoint(self):
        devices = [("id-jbl", "Speakers (JBL Flip 6)", "Active"),
                   ("id-hx", "Haut-parleurs (HyperX QuadCast S)", "Active"),
                   ("id-old", "Haut-parleurs (Realtek(R) Audio)", "NotPresent"),
                   ("id-hdmi", "Odyssey G91F (NVIDIA High Definition Audio)", "Active")]
        self.assertEqual(er.pick_device(devices, "hyperx"), ("id-hx", "Haut-parleurs (HyperX QuadCast S)"))
        with self.assertRaises(SystemExit):
            er.pick_device(devices, "Haut-parleurs (Realtek")           # not present: never a target
        with self.assertRaises(SystemExit):
            er.pick_device(devices, "e")                                # several

    def test_status_set_restore_check_are_the_commands(self):
        p = subprocess.run([sys.executable, "-m", "tools_py.parity.endpoint_route", "--help"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        for c in ("status", "set", "restore", "check"):
            self.assertIn(c, p.stdout)


if __name__ == "__main__":
    unittest.main()
