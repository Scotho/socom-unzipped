import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

from tools_py.parity import black_rows, drive, gate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "gate")   # committed: runs on a fresh clone
TITLE_FIXTURE_RUN = os.path.join(FIXTURES, "title")
TRANSITION_FIXTURE_RUN = os.path.join(FIXTURES, "transition")
GOOD_MISSION_FIXTURE = os.path.join(FIXTURES, "mission", "good.drive.txt")
BAD_MISSION_FIXTURE = os.path.join(FIXTURES, "mission", "bad.drive.txt")

# git-ignored real-run logs, kept locally: extra coverage when present, but never required.
GOOD_TITLE_RUN = os.path.join(ROOT, "logs", "parity", "runs", "vr_title")               # known clean (STATUS 2026-09-10 17:40)
# drive.py stdout (not the game's own run log) is what carries `matched=True`; this run reached the HUD.
GOOD_MISSION_LOG = os.path.join(ROOT, "logs", "parity", "drive_gameplay_probe5.txt")    # known reached HUD (STATUS 2026-09-09 13:30)
BAD_MISSION_LOG = os.path.join(ROOT, "logs", "parity", "vr_gameplay.drive.log")         # known FAIL: HUD never matched
CLEAN_TRANSITION_RUN = os.path.join(ROOT, "logs", "parity", "gate", "first", "transition")  # 6 black-screen frames, all black
NATIVE_ON_TRANSITION = os.path.join(ROOT, "logs", "parity", "gate", "native_on", "transition")  # 4 black-screen frames, all black


class WaitCaptures(unittest.TestCase):
    """drive.wait_capturer is what puts the mid-wait frames on disk for black_rows.py to score
    (gate.TRANSITION_MIN_FRAMES); check the cadence and the names without a game window."""

    def _run(self, elapsed_values, period=1.0):
        grabs = []
        real_grab = drive.winshot.grab
        drive.winshot.grab = lambda hwnd: Image.new("RGB", (640, 448), (0, 0, 0))
        try:
            with tempfile.TemporaryDirectory() as out:
                on_frame = drive.wait_capturer(out, hwnd=None, step=3, period=period)
                for e in elapsed_values:
                    on_frame(e)
                grabs = sorted(os.listdir(out))
        finally:
            drive.winshot.grab = real_grab
        return grabs

    def test_one_capture_per_period(self):
        """Polls land every 0.25 s; one frame per second of the wait, named w<step>_<k>.png."""
        self.assertEqual(self._run([0.25, 0.5, 0.75, 1.0, 1.25, 2.1, 2.4]),
                         ["w03_000.png", "w03_001.png", "w03_002.png"])

    def test_short_wait_still_captures_once(self):
        self.assertEqual(self._run([0.25]), ["w03_000.png"])

    def test_failed_grab_does_not_raise(self):
        """A capture is a diagnostic: a grab that fails must not take a 170 s gate run down."""
        real_grab = drive.winshot.grab

        def boom(hwnd):
            raise RuntimeError("window gone")

        drive.winshot.grab = boom
        try:
            with tempfile.TemporaryDirectory() as out:
                on_frame = drive.wait_capturer(out, hwnd=None, step=0)
                on_frame(0.25)
                on_frame(1.5)
                self.assertEqual(os.listdir(out), [])
        finally:
            drive.winshot.grab = real_grab


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

    def test_wait_frames_are_not_title_captures(self):
        """drive.py also writes w<NN>_<kkk>.png during its settle waits (Task 8). Those are
        mid-wait frames, not the settled screen a step captures, so the title scorer must keep
        globbing s[0-9][0-9]_*.png only: a black w00_000.png dropped into a clean run must not
        appear in the score list nor change the verdict."""
        with tempfile.TemporaryDirectory() as tmp:
            run = os.path.join(tmp, "title")
            shutil.copytree(TITLE_FIXTURE_RUN, run)
            before_ok, before_detail = gate.score_title(run)
            Image.new("RGB", (640, 448), (0, 0, 0)).save(os.path.join(run, "w00_000.png"))
            after_ok, after_detail = gate.score_title(run)
        self.assertNotIn("w00", after_detail)
        self.assertEqual(before_detail, after_detail)
        self.assertEqual(before_ok, after_ok)


class MissionScoring(unittest.TestCase):
    def test_fixture_good_log_passes(self):
        """tests/fixtures/gate/mission/good.drive.txt: the untilref(...matched=True) line and
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
        """tests/fixtures/gate/transition/: five near-black 320x224 frames from a real run
        (logs/parity/gate/wcap2/transition -- one step capture and four wait captures, all
        peak 0). Five is exactly gate.TRANSITION_MIN_FRAMES, so this also pins the floor."""
        ok, detail = gate.score_transition(TRANSITION_FIXTURE_RUN)
        self.assertTrue(ok, detail)
        self.assertIn("5 black-screen frames examined", detail)

    @unittest.skipUnless(os.path.isdir(CLEAN_TRANSITION_RUN), "needs logs/parity/gate/first/transition")
    def test_known_clean_run_passes(self):
        ok, detail = gate.score_transition(CLEAN_TRANSITION_RUN)
        self.assertTrue(ok, detail)

    def test_wait_frames_count_toward_transition(self):
        """Task 8: drive.py captures a frame every 1.0 s of every settle wait as
        w<NN>_<kkk>.png, so the ~1 s fade can no longer fall between two step captures.
        black_rows.py must examine those alongside the s*.png step captures -- three wait
        frames plus two step frames is five examined, enough for TRANSITION_MIN_FRAMES = 5."""
        with tempfile.TemporaryDirectory() as run:
            for name in ("w00_000.png", "w00_001.png", "w00_002.png",
                         "s00_none.png", "s01_none.png"):
                Image.new("RGB", (640, 448), (0, 0, 0)).save(os.path.join(run, name))
            ok, detail = gate.score_transition(run)
        self.assertTrue(ok, detail)
        self.assertIn("5 black-screen frames examined", detail)

    def test_bright_pixel_in_the_band_fails(self):
        """The regression the band exists to catch (STATUS 2026-09-09 12:10: a strip of the
        main-menu video at rows 396-447 of the black screen before the briefing). Copy the passing
        fixture run, light one pixel inside the band of one frame -- scaled by h/448, the fixtures
        are 320x224 -- and the gate must go red with the NOT BLACK reason, not merely count five
        frames and pass. Without this, every transition assertion in this file is a positive."""
        with tempfile.TemporaryDirectory() as tmp:
            run = os.path.join(tmp, "transition")
            shutil.copytree(TRANSITION_FIXTURE_RUN, run)
            self.assertTrue(gate.score_transition(run)[0])
            victim = sorted(f for f in os.listdir(run) if f.endswith(".png"))[0]
            path = os.path.join(run, victim)
            with Image.open(path) as im:
                im = im.convert("RGB")
                w, h = im.size
                y = (396 * h // 448 + 447 * h // 448) // 2   # mid-band, in this frame's scale
                im.putpixel((w // 2, y), (255, 255, 255))
                im.save(path)
            ok, detail = gate.score_transition(run)
        self.assertFalse(ok, detail)
        self.assertIn("NOT BLACK", detail)
        self.assertIn(victim, detail)

    @unittest.skipUnless(os.path.isdir(NATIVE_ON_TRANSITION), "needs logs/parity/gate/native_on/transition")
    def test_pre_wait_capture_run_is_below_the_floor(self):
        """Negative control for the 2026-09-11 recalibration. This run predates the wait
        captures: its only black frames are the four burst frames that happened to overlap the
        fade, so it is short of the restored floor of 5. Every frame in it is black (peak 0) --
        it fails on evidence, not on rendering, which is what the floor is there to catch."""
        ok, detail = gate.score_transition(NATIVE_ON_TRANSITION)
        self.assertFalse(ok, detail)
        self.assertIn("4 black-screen frames examined", detail)


class BurstStepFiltering(unittest.TestCase):
    """The transition frame count has to be able to say which frames are the transition and
    which are the boot: black_rows.py --from-step drops the boot ones, and gate.first_burst_step
    reads the step index to drop them from off the probe script rather than a hard-coded number."""

    def test_first_burst_step_of_the_transition_probe(self):
        """transition_probe.txt: nine `next` steps (s00..s08, the boot screens through the rank
        screen) and then the first `burst`. Captures from that step on are named s09_*/w09_*."""
        self.assertEqual(gate.first_burst_step(), 9)

    def test_first_burst_step_ignores_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("# a comment\n\nnext+1.0:CROSS   # step 0\nwait+1.0:NONE\n"
                        "burst+5.0:NONE  # step 2\nburst+1.0:NONE\n")
            self.assertEqual(gate.first_burst_step(path), 2)

    def test_script_without_a_burst_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("next+1.0:CROSS\nwait+1.0:NONE\n")
            self.assertIsNone(gate.first_burst_step(path))
            self.assertIsNone(gate.first_burst_step(os.path.join(tmp, "no_such_script.txt")))

    def test_step_index_of_capture_names(self):
        self.assertEqual(black_rows.step_index("s09_burst_003.png"), 9)
        self.assertEqual(black_rows.step_index("w10_001.png"), 10)
        self.assertEqual(black_rows.step_index("s00_none.png"), 0)
        self.assertEqual(black_rows.step_index("final.png"), -1)   # not a step capture

    def test_frames_before_the_burst_step_do_not_count(self):
        """The point of --from-step: eight black frames from the boot (s00..s07) plus two from
        the burst step is ten frames of which only two can be the transition. Unrestricted,
        black_rows.py examines all ten; --from-step 8 examines the two."""
        with tempfile.TemporaryDirectory() as run:
            names = ["s%02d_CROSS.png" % i for i in range(8)] + ["s08_burst_000.png", "w08_000.png"]
            for name in names:
                Image.new("RGB", (640, 448), (0, 0, 0)).save(os.path.join(run, name))

            def examined(*extra):
                r = subprocess.run([sys.executable, "tools_py/parity/black_rows.py", run] + list(extra),
                                   capture_output=True, text=True, cwd=ROOT)
                return [ln.split()[0] for ln in r.stdout.splitlines() if "black screen, rows " in ln]

            self.assertEqual(len(examined()), 10)
            self.assertEqual(sorted(examined("--from-step", "8")),
                             ["s08_burst_000.png", "w08_000.png"])
            self.assertEqual(examined("--from-step", "9"), [])


if __name__ == "__main__":
    unittest.main()
