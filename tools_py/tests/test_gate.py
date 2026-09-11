import os
import tempfile
import unittest

from tools_py.parity import gate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "gate")   # committed: runs on a fresh clone
TITLE_FIXTURE_RUN = os.path.join(FIXTURES, "title")
TRANSITION_FIXTURE_RUN = os.path.join(FIXTURES, "transition")
GOOD_MISSION_FIXTURE = os.path.join(FIXTURES, "mission", "good.drive.log")
BAD_MISSION_FIXTURE = os.path.join(FIXTURES, "mission", "bad.drive.log")

# git-ignored real-run logs, kept locally: extra coverage when present, but never required.
GOOD_TITLE_RUN = os.path.join(ROOT, "logs", "parity", "runs", "vr_title")               # known clean (STATUS 2026-09-10 17:40)
# drive.py stdout (not the game's own run log) is what carries `matched=True`; this run reached the HUD.
GOOD_MISSION_LOG = os.path.join(ROOT, "logs", "parity", "drive_gameplay_probe5.txt")    # known reached HUD (STATUS 2026-09-09 13:30)
BAD_MISSION_LOG = os.path.join(ROOT, "logs", "parity", "vr_gameplay.drive.log")         # known FAIL: HUD never matched
CLEAN_TRANSITION_RUN = os.path.join(ROOT, "logs", "parity", "gate", "first", "transition")  # 6 black-screen frames, all black
NATIVE_ON_TRANSITION = os.path.join(ROOT, "logs", "parity", "gate", "native_on", "transition")  # 4 black-screen frames, all black


class TitleScoring(unittest.TestCase):
    def test_fixture_run_passes(self):
        """tests/fixtures/gate/title/: s00..s15 of the known-clean vr_title run, 320x224
        (256-colour palette PNGs; see tools_py/parity/make_gate_fixtures.py). All 16 must score
        >= TITLE_MIN_SCORE for this to hit the >= 16 floor."""
        ok, detail = gate.score_title(TITLE_FIXTURE_RUN)
        self.assertTrue(ok, detail)

    def test_empty_dir_fails(self):
        ok, detail = gate.score_title(os.path.join(ROOT, "logs"))
        self.assertFalse(ok)

    @unittest.skipUnless(os.path.isdir(GOOD_TITLE_RUN), "needs logs/parity/runs/vr_title")
    def test_known_clean_run_passes(self):
        ok, detail = gate.score_title(GOOD_TITLE_RUN)
        self.assertTrue(ok, detail)


class MissionScoring(unittest.TestCase):
    def test_fixture_good_log_passes(self):
        """tests/fixtures/gate/mission/good.drive.log: the untilref(...matched=True) line and
        the >= 3 sNN_hold lines score_mission_log reads, trimmed from drive_gameplay_probe5.txt."""
        ok, detail = gate.score_mission_log(GOOD_MISSION_FIXTURE)
        self.assertTrue(ok, detail)

    def test_fixture_bad_log_fails(self):
        ok, detail = gate.score_mission_log(BAD_MISSION_FIXTURE)
        self.assertFalse(ok)

    @unittest.skipUnless(os.path.isfile(GOOD_MISSION_LOG), "needs logs/parity/drive_gameplay_probe5.txt")
    def test_known_good_log_passes(self):
        ok, detail = gate.score_mission_log(GOOD_MISSION_LOG)
        self.assertTrue(ok, detail)

    @unittest.skipUnless(os.path.isfile(BAD_MISSION_LOG), "needs logs/parity/vr_gameplay.drive.log")
    def test_missing_hud_fails(self):
        ok, detail = gate.score_mission_log(BAD_MISSION_LOG)
        self.assertFalse(ok)


class TransitionScoring(unittest.TestCase):
    def test_empty_dir_fails(self):
        """black_rows.py exits 0 when it examines nothing, so an empty run must not score PASS."""
        with tempfile.TemporaryDirectory() as empty:
            ok, detail = gate.score_transition(empty)
        self.assertFalse(ok, detail)

    def test_missing_dir_fails(self):
        ok, detail = gate.score_transition(os.path.join(ROOT, "logs", "parity", "no_such_run"))
        self.assertFalse(ok, detail)

    def test_fixture_run_passes(self):
        """tests/fixtures/gate/transition/: two near-black 320x224 frames from a real run
        (logs/parity/gate/first/transition, s04_CROSS and s09_burst_003 -- both peak 0)."""
        ok, detail = gate.score_transition(TRANSITION_FIXTURE_RUN)
        self.assertTrue(ok, detail)

    @unittest.skipUnless(os.path.isdir(CLEAN_TRANSITION_RUN), "needs logs/parity/gate/first/transition")
    def test_known_clean_run_passes(self):
        ok, detail = gate.score_transition(CLEAN_TRANSITION_RUN)
        self.assertTrue(ok, detail)

    @unittest.skipUnless(os.path.isdir(NATIVE_ON_TRANSITION), "needs logs/parity/gate/native_on/transition")
    def test_short_but_clean_run_passes(self):
        """How many frames a run yields is drive.py burst timing, not rendering: 4 is a pass."""
        ok, detail = gate.score_transition(NATIVE_ON_TRANSITION)
        self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
