import os
import unittest

from tools_py.parity import gate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOOD_TITLE_RUN = os.path.join(ROOT, "logs", "parity", "runs", "vr_title")               # known clean (STATUS 2026-09-10 17:40)
# drive.py stdout (not the game's own run log) is what carries `matched=True`; this run reached the HUD.
GOOD_MISSION_LOG = os.path.join(ROOT, "logs", "parity", "drive_gameplay_probe5.txt")    # known reached HUD (STATUS 2026-09-09 13:30)
BAD_MISSION_LOG = os.path.join(ROOT, "logs", "parity", "vr_gameplay.drive.log")         # known FAIL: HUD never matched


@unittest.skipUnless(os.path.isdir(GOOD_TITLE_RUN), "needs logs/parity/runs/vr_title")
class TitleScoring(unittest.TestCase):
    def test_known_clean_run_passes(self):
        ok, detail = gate.score_title(GOOD_TITLE_RUN)
        self.assertTrue(ok, detail)

    def test_empty_dir_fails(self):
        ok, detail = gate.score_title(os.path.join(ROOT, "logs"))
        self.assertFalse(ok)


@unittest.skipUnless(os.path.isfile(GOOD_MISSION_LOG), "needs logs/parity/drive_gameplay_probe5.txt")
class MissionScoring(unittest.TestCase):
    def test_known_good_log_passes(self):
        ok, detail = gate.score_mission_log(GOOD_MISSION_LOG)
        self.assertTrue(ok, detail)

    @unittest.skipUnless(os.path.isfile(BAD_MISSION_LOG), "needs logs/parity/vr_gameplay.drive.log")
    def test_missing_hud_fails(self):
        ok, detail = gate.score_mission_log(BAD_MISSION_LOG)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
