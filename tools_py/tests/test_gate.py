import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
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
CLEAN_TRANSITION_RUN = os.path.join(ROOT, "logs", "parity", "gate", "tfix3", "transition")   # 18 frames at/after the burst step
# Pre-fix run: the probe stalled on the "save to memory card?" dialog, so it has black frames
# from the boot and none at/after its burst step (gate.py TRANSITION_MIN_FRAMES).
STALLED_TRANSITION_RUN = os.path.join(ROOT, "logs", "parity", "gate", "wcap2", "transition")


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
        (logs/parity/gate/tfix4/transition -- four of the 5 fps burst frames of the fade into the
        briefing and one wait capture after it, all peak 0). Every name is s11_*/w13_*, at or
        after the probe's burst step, so the scorer examines all five; five is exactly
        gate.TRANSITION_MIN_FRAMES, so this also pins the floor."""
        ok, detail = gate.score_transition(TRANSITION_FIXTURE_RUN)
        self.assertTrue(ok, detail)
        self.assertIn("5 black-screen frames examined", detail)
        self.assertIn("at/after the burst step", detail)

    @unittest.skipUnless(os.path.isdir(CLEAN_TRANSITION_RUN), "needs logs/parity/gate/tfix3/transition")
    def test_known_clean_run_passes(self):
        ok, detail = gate.score_transition(CLEAN_TRANSITION_RUN)
        self.assertTrue(ok, detail)
        self.assertIn("18 black-screen frames examined", detail)

    def test_wait_frames_count_toward_transition(self):
        """Task 8: drive.py captures a frame every 1.0 s of every settle wait as
        w<NN>_<kkk>.png, so the ~1 s fade can no longer fall between two step captures.
        black_rows.py must examine those alongside the s*.png step captures -- three wait
        frames plus two step frames is five examined, enough for TRANSITION_MIN_FRAMES = 5.
        The names are s11/w13 because the scorer only examines frames at/after the probe's
        burst step."""
        with tempfile.TemporaryDirectory() as run:
            for name in ("w13_000.png", "w13_001.png", "w13_002.png",
                         "s11_burst_000.png", "s12_none.png"):
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

    def test_black_frames_before_the_burst_step_do_not_pass_the_gate(self):
        """The bug this whole enforcement exists for, at the scorer level: twenty black
        frames from the boot (s00..s09, w00..w09) are not a transition. Before --from-step they
        were twenty "black-screen frames examined" and a green gate; now they are zero."""
        with tempfile.TemporaryDirectory() as run:
            for i in range(10):
                Image.new("RGB", (640, 448), (0, 0, 0)).save(os.path.join(run, "s%02d_CROSS.png" % i))
                Image.new("RGB", (640, 448), (0, 0, 0)).save(os.path.join(run, "w%02d_000.png" % i))
            ok, detail = gate.score_transition(run)
        self.assertFalse(ok, detail)
        self.assertIn("0 black-screen frames examined", detail)

    @unittest.skipUnless(os.path.isdir(STALLED_TRANSITION_RUN), "needs logs/parity/gate/wcap2/transition")
    def test_stalled_pre_fix_run_now_fails(self):
        """The real article: logs/parity/gate/wcap2 passed this gate on 2026-09-11 with 13
        black-screen frames, every one of them from the boot -- the probe stalled on the
        "save to memory card?" dialog and never reached the briefing. Under the enforced scorer
        it FAILs with 0. Same for famb, famc, hostdraw_on and hostdraw_fix (see gate.py)."""
        ok, detail = gate.score_transition(STALLED_TRANSITION_RUN)
        self.assertFalse(ok, detail)
        self.assertIn("0 black-screen frames examined", detail)


class BurstStepFiltering(unittest.TestCase):
    """The transition frame count has to be able to say which frames are the transition and
    which are the boot: black_rows.py --from-step drops the boot ones, and gate.first_burst_step
    reads the step index to drop them from off the probe script rather than a hard-coded number."""

    def test_first_burst_step_of_the_transition_probe(self):
        """transition_probe.txt: nine `next` steps (s00..s08, the boot screens through the rank
        screen), the two ifref guards for the "save to memory card?" dialog (s09/s10), then the
        burst that starts on the NO press and captures the fade. Captures from it on are named
        s11_*; the gate examines those and nothing earlier."""
        self.assertEqual(gate.first_burst_step(), 11)

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

    def test_first_burst_step_accepts_ifburst(self):
        """The transition probe's transition burst is an `ifburst` (one after every "save to
        memory card?" guard pair, only the answered pair's fires). The static fallback has to
        recognise that form, or it would skip past all three and point at the briefing burst."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("next+1.0:CROSS\nifburst+12.0:NONE\nburst+8.0:NONE\n")
            self.assertEqual(gate.first_burst_step(path), 1)

    def test_step_index_of_capture_names(self):
        self.assertEqual(black_rows.step_index("s09_burst_003.png"), 9)
        self.assertEqual(black_rows.step_index("w10_001.png"), 10)
        self.assertEqual(black_rows.step_index("s00_none.png"), 0)
        self.assertEqual(black_rows.step_index("final.png"), -1)   # not a step capture

    def test_frames_before_the_burst_step_do_not_count(self):
        """The point of --from-step, at the black_rows.py level: eight black frames from the
        boot (s00..s07) plus two from the burst step is ten frames of which only two can be the
        transition. Unrestricted, black_rows.py examines all ten; --from-step 8 examines the two."""
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


class MovedDialog(unittest.TestCase):
    """The 2026-09-12 defect: the "save to memory card?" dialog lands on a step index that moves
    with how many controller-configuration screens the boot shows, so a burst pinned to a fixed
    index stops being the transition. logs/parity/gate/s4_mb matched the dialog at steps 13/14
    instead of 9/10; the step-11 burst captured a configuration screen and the scorer was left
    four 1 Hz wait frames ("4 black-screen frames examined, need 5"), three runs in a row."""

    @staticmethod
    def _black(path):
        Image.new("RGB", (640, 448), (0, 0, 0)).save(path)

    def _late_dialog_run(self, tmp):
        """A run shaped like s4_mb under the fixed probe: boot black screens through step 10, the
        first guard pair not matching (so its ifburst fires nothing), the dialog answered at
        steps 13/14, and the burst firing at step 15 on the fade."""
        run = os.path.join(tmp, "transition")
        os.makedirs(run)
        for i in range(11):                       # boot: black, but not the transition
            self._black(os.path.join(run, "s%02d_CROSS.png" % i))
            self._black(os.path.join(run, "w%02d_000.png" % i))
        for name in ("s12_CROSS.png", "s13_RIGHT.png", "s14_CROSS.png"):
            Image.new("RGB", (640, 448), (200, 200, 200)).save(os.path.join(run, name))
        for k in range(4):                        # the burst that actually fired, on the NO press
            self._black(os.path.join(run, "s15_burst_%03d.png" % k))
        self._black(os.path.join(run, "w16_000.png"))
        return run

    def test_observed_burst_step_reads_the_burst_that_fired(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._late_dialog_run(tmp)
            self.assertEqual(gate.observed_burst_step(run), 15)
        # ... and the script's static answer, which the old scorer used, is the wrong one.
        self.assertEqual(gate.first_burst_step(), 11)

    def test_observed_burst_step_is_none_without_burst_captures(self):
        with tempfile.TemporaryDirectory() as run:
            self._black(os.path.join(run, "s00_CROSS.png"))
            self.assertIsNone(gate.observed_burst_step(run))
        self.assertIsNone(gate.observed_burst_step(os.path.join(ROOT, "logs", "no_such_run")))

    def test_observed_burst_step_takes_the_first_burst_not_the_briefing_one(self):
        """The probe ends with a second, unconditional burst on the settled briefing. The scorer
        must count from the transition burst, not from that one."""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._late_dialog_run(tmp)
            self._black(os.path.join(run, "s22_burst_000.png"))
            self.assertEqual(gate.observed_burst_step(run), 15)

    def test_late_dialog_run_is_scored_from_the_no_press(self):
        """The property the fix has to hold: the frames counted are the frames after the NO
        press, wherever it landed. Twenty-two boot black frames sit in this run and none of them
        count; the five frames from the fired burst on do, which is exactly the floor."""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._late_dialog_run(tmp)
            ok, detail = gate.score_transition(run)
        self.assertTrue(ok, detail)
        self.assertIn("5 black-screen frames examined", detail)
        self.assertIn("(s15, fired)", detail)

    def test_late_dialog_run_would_have_failed_on_the_fixed_index(self):
        """Same run, scored the old way (from the script's fixed burst step): the fade is at
        s15/w16 and the three configuration screens at s12..s14 are not black, so a from-step-11
        count sees only the five real frames -- but with the burst firing at 11 instead, as it
        did on s4_mb, those five would have been four 1 Hz wait captures. Pin the difference the
        cheap way: the fixed index and the observed one are not the same number."""
        with tempfile.TemporaryDirectory() as tmp:
            run = self._late_dialog_run(tmp)
            self.assertNotEqual(gate.observed_burst_step(run), gate.first_burst_step())

    def test_run_that_fired_no_burst_still_fails(self):
        """Falling back to the script must not become a way to pass: a run whose probe never
        answered the dialog has no burst captures, falls back to the static step, and counts
        nothing at or after it."""
        with tempfile.TemporaryDirectory() as run:
            for i in range(11):
                self._black(os.path.join(run, "s%02d_CROSS.png" % i))
            ok, detail = gate.score_transition(run)
        self.assertFalse(ok, detail)
        self.assertIn("0 black-screen frames examined", detail)
        self.assertIn("no burst fired; script", detail)

    def test_probe_pairs_an_ifburst_with_every_guard_pair(self):
        """Structural guard on scripts/parity/transition_probe.txt: every `ifref` guard pair that
        can answer the dialog is immediately followed by an `ifburst`, so whichever pair matches,
        the burst is on its NO press. A pinned `burst` after only the first pair is the defect."""
        path = os.path.join(ROOT, "scripts", "parity", "transition_probe.txt")
        with open(path, encoding="utf-8") as f:
            modes = [ln.split("#", 1)[0].strip().split("+", 1)[0]
                     for ln in f if ln.split("#", 1)[0].strip()]
        pairs = [i for i in range(len(modes) - 1)
                 if modes[i].startswith("ifref(") and modes[i + 1].startswith("ifref(")]
        self.assertEqual(len(pairs), 3, modes)
        for i in pairs:
            self.assertEqual(modes[i + 2], "ifburst", "no ifburst after the pair at step %d" % i)
        self.assertNotIn("burst", modes[:max(pairs) + 2])   # no unconditional burst before them


class ConditionalBurst(unittest.TestCase):
    """drive.py `ifburst`: a burst that fires only when the ifref step above it matched. Driven
    without a game window by stubbing the frame grab, the settle wait and the key presses."""

    REF = "scripts/parity/ref_save_prompt_ours.png"   # relative: drive.parse splits the line on ':'

    def _run(self, script):
        saved = (drive.frame, drive.wait_stable, drive.winshot.grab, drive.keys.press)
        drive.frame = lambda hwnd: np.zeros((112, 160), dtype=np.float32)
        drive.wait_stable = lambda *a, **k: (True, 0.0)
        drive.winshot.grab = lambda hwnd: Image.new("RGB", (64, 64), (0, 0, 0))
        drive.keys.press = lambda *a, **k: None
        try:
            with tempfile.TemporaryDirectory() as out:
                a = argparse.Namespace(out=out, settle=1.5, maxwait=40.0, target="ours", tail=0.0)
                drive.run_steps(a, drive.parse(script), None, None, 0.0, None, [])
                return sorted(os.listdir(out))
        finally:
            drive.frame, drive.wait_stable, drive.winshot.grab, drive.keys.press = saved

    def _script(self, thresh_first, thresh_second):
        # A huge threshold always matches the stubbed all-zero frame, a zero threshold never does.
        return ("ifref(%s,47,62,36,125,%s)+0.0:CROSS\nifburst+0.4:NONE\n"
                "ifref(%s,47,62,36,125,%s)+0.0:CROSS\nifburst+0.4:NONE\n"
                "burst+0.4:NONE\n" % (self.REF, thresh_first, self.REF, thresh_second))

    def test_ifburst_fires_only_after_the_matching_pair(self):
        """First ifref does not match, second does: the burst that fires is the second one, at
        the step index the dialog actually landed on -- which is the whole fix."""
        names = self._run(self._script("0", "100000"))
        self.assertFalse([n for n in names if n.startswith("s01_burst_")], names)
        self.assertTrue([n for n in names if n.startswith("s03_burst_")], names)

    def test_ifburst_fires_on_the_first_pair_when_that_is_where_the_dialog_is(self):
        names = self._run(self._script("100000", "0"))
        self.assertTrue([n for n in names if n.startswith("s01_burst_")], names)
        self.assertFalse([n for n in names if n.startswith("s03_burst_")], names)

    def test_plain_burst_is_unconditional(self):
        """The briefing burst at the end of the probe must keep firing regardless of the guards."""
        names = self._run(self._script("0", "0"))
        self.assertFalse([n for n in names if "_burst_" in n and not n.startswith("s04_")], names)
        self.assertTrue([n for n in names if n.startswith("s04_burst_")], names)


if __name__ == "__main__":
    unittest.main()
