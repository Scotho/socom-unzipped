"""Sprint 14 E2: the gate's fourth leg, on planted run directories (no build, no game, no lock).

The leg is named only in tools_py/parity/gate.py (the isolation test beside this module), so this module builds
the name from parts. Two halves:

  capture   gate --capture-<leg> <run_dir>: from a green 3/3 gate stamp, copy the twelve step captures the three
            stages already take (R280: title s03 s09 s15, transition s06 s08, mission s06 s08 s10 s12 s16 s20 s24 --
            drive.py writes one s<NN>_<buttons>.png per step) into the leg's reference directory as
            <stage>_s<NN>.png, and pin them in its pins.json (the shape of scripts/parity/pins.json). Refuses
            (gate.REFUSE_CAPTURE) when the directory exists, the run is not green 3/3, or a stamp is missing.
  score     gate --leg <leg> <run_dir>: each stamp against its reference with the title scorer's own comparison
            (compare.score, gate._score_value) at the title scorer's own bar (gate.TITLE_MIN_SCORE); `<LEG> n/12`,
            exit 0 only at 12/12, and the summary line written into the run's summary.txt.

The planted images are 64x48 patterns: a capture byte-identical to its reference scores 100.0, its negative ~0.
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from tools_py.parity import gate, pins

LEG = "held" + "out"
STAMPS = [("title", 3, "none"), ("title", 9, "none"), ("title", 15, "none"),
          ("transition", 6, "CROSS"), ("transition", 8, "CROSS"),
          ("mission", 6, "CROSS"), ("mission", 8, "CROSS"), ("mission", 10, "none"), ("mission", 12, "none"),
          ("mission", 16, "none"), ("mission", 20, "none"), ("mission", 24, "none")]
GREEN = ["PASS title (19/23 menu captures >= 90.0)", "PASS transition (5 black-screen frames examined)",
         "PASS mission (HUD reached)", "EXE dist/socom2.exe bytes=1 sha256=00", "TREE abc1234 dirty=0",
         "PINS MATCH scripts/parity/pins.json (12 compared)"]


def _pattern(seed):
    rng = np.random.RandomState(seed)
    return Image.fromarray(rng.randint(0, 256, (48, 64, 3)).astype("uint8"), "RGB")


def _negative(im):
    return Image.fromarray(255 - np.asarray(im), "RGB")


def plant_run(root, summary=GREEN, skip=(), negate=(), seed_offset=0):
    """A gate stamp: title/ transition/ mission/ with one capture per step (the twelve stamps and a neighbour
    each), a transition burst frame at a stamp's index (which must never be taken), and summary.txt."""
    for stage, step, btn in STAMPS:
        d = os.path.join(root, stage)
        os.makedirs(d, exist_ok=True)
        if (stage, step) in skip:
            continue
        im = _pattern(step * 7 + len(stage) + seed_offset)
        (_negative(im) if (stage, step) in negate else im).save(os.path.join(d, "s%02d_%s.png" % (step, btn)))
        _pattern(999).save(os.path.join(d, "s%02d_none.png" % (step + 1)))     # the step after: never taken
    _pattern(555).save(os.path.join(root, "transition", "s06_burst_000.png"))
    with open(os.path.join(root, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("".join(l + "\n" for l in summary))
    return root


def _run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = gate.main(argv)
    return rc, out.getvalue()


class LegCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.refs = os.path.join(self.tmp, "refs", LEG)
        p = mock.patch.object(gate, "LEG_REFS_DIR", self.refs)
        p.start()
        self.addCleanup(p.stop)

    def capture(self, run_dir):
        return _run(["--capture-" + LEG, run_dir])

    def leg(self, run_dir):
        return _run(["--leg", LEG, run_dir])


class Capture(LegCase):
    def test_a_green_run_writes_twelve_references_and_their_pins(self):
        run = plant_run(os.path.join(self.tmp, "green"))
        rc, out = self.capture(run)
        self.assertEqual(rc, 0, out)
        names = sorted(n for n in os.listdir(self.refs) if n.endswith(".png"))
        self.assertEqual(names, sorted("%s_s%02d.png" % (s, n) for s, n, _ in STAMPS))
        # the step's own capture, not the burst frame that shares its index
        with open(os.path.join(run, "transition", "s06_CROSS.png"), "rb") as a, \
                open(os.path.join(self.refs, "transition_s06.png"), "rb") as b:
            self.assertEqual(a.read(), b.read())
        with open(os.path.join(self.refs, pins.RECORD_NAME), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(set(doc), {"_about", "accepted", "pins"})
        expected = pins.load_expected(os.path.join(self.refs, pins.RECORD_NAME))
        self.assertEqual(len(expected), 12)
        for name, sha in expected.items():
            self.assertEqual(pins.file_sha256(os.path.join(gate.ROOT, name)), sha)
        self.assertIn("12 references", out)

    def test_an_existing_directory_is_never_overwritten(self):
        os.makedirs(self.refs)
        rc, out = self.capture(plant_run(os.path.join(self.tmp, "green")))
        self.assertEqual(rc, gate.REFUSE_CAPTURE)
        self.assertIn("already exists", out)
        self.assertEqual(os.listdir(self.refs), [])

    def test_a_run_that_is_not_green_three_of_three_is_refused(self):
        cases = {
            "failed": [l.replace("PASS mission", "FAIL mission") for l in GREEN],
            "two_stages": [l for l in GREEN if not l.startswith("PASS transition")],
            "drifted": [l for l in GREEN if not l.startswith("PINS")] + ["PINS DRIFTED: env -- refused to score"],
            "stale": GREEN + ["gate: STALE exe accepted (--stale-ok)"],
            "no_summary": None,
        }
        for label, summary in cases.items():
            run = plant_run(os.path.join(self.tmp, label), summary=summary or [])
            if summary is None:
                os.remove(os.path.join(run, "summary.txt"))
            rc, out = self.capture(run)
            self.assertEqual(rc, gate.REFUSE_CAPTURE, (label, out))
            self.assertIn("not a green 3/3", out, label)
            self.assertFalse(os.path.exists(self.refs), label)

    def test_a_missing_stamp_is_refused_and_leaves_nothing(self):
        run = plant_run(os.path.join(self.tmp, "gap"), skip=[("mission", 16)])
        rc, out = self.capture(run)
        self.assertEqual(rc, gate.REFUSE_CAPTURE)
        self.assertIn("mission s16", out)
        self.assertFalse(os.path.exists(self.refs))


class Score(LegCase):
    def setUp(self):
        super().setUp()
        rc, out = self.capture(plant_run(os.path.join(self.tmp, "reference")))
        self.assertEqual(rc, 0, out)

    def test_twelve_of_twelve_passes_and_lands_in_the_summary(self):
        run = plant_run(os.path.join(self.tmp, "same"))
        rc, out = self.leg(run)
        self.assertEqual(rc, 0, out)
        self.assertIn("%s 12/12 PASS" % LEG.upper(), out)
        self.assertEqual(out.count(" PASS 100.0"), 12, out)
        with open(os.path.join(run, "summary.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith(GREEN[0]), "the stage lines are kept")
        self.assertEqual([l for l in text.splitlines() if l.startswith(LEG.upper())][0][:len(LEG) + 11],
                         "%s 12/12 PASS" % LEG.upper())

    def test_a_rescore_replaces_its_line_rather_than_adding_one(self):
        run = plant_run(os.path.join(self.tmp, "twice"))
        self.leg(run)
        self.leg(run)
        with open(os.path.join(run, "summary.txt"), encoding="utf-8") as f:
            self.assertEqual(sum(1 for l in f if l.startswith(LEG.upper() + " ")), 1)

    def test_rejected_and_missing_stamps_count_against_it(self):
        run = plant_run(os.path.join(self.tmp, "worse"), negate=[("title", 9), ("mission", 20)],
                        skip=[("transition", 8)])
        rc, out = self.leg(run)
        self.assertEqual(rc, 1, out)
        self.assertIn("%s 9/12 FAIL" % LEG.upper(), out)
        self.assertRegex(out, r"title_s09 FAIL \d+\.\d")
        self.assertRegex(out, r"mission_s20 FAIL \d+\.\d")
        self.assertIn("transition_s08 MISSING", out)

    def test_the_bar_is_the_title_scorers_bar(self):
        run = plant_run(os.path.join(self.tmp, "bar"))
        with mock.patch.object(gate, "TITLE_MIN_SCORE", 100.1):
            rc, out = self.leg(run)
        self.assertEqual(rc, 1, out)
        self.assertIn("%s 0/12 FAIL" % LEG.upper(), out)

    def test_a_reference_that_moved_off_its_pin_refuses(self):
        _pattern(4242).save(os.path.join(self.refs, "mission_s06.png"))
        rc, out = self.leg(plant_run(os.path.join(self.tmp, "any")))
        self.assertEqual(rc, 7, out)
        self.assertIn("mission_s06.png", out)

    def test_no_run_directory_is_nothing_to_score(self):
        rc, out = self.leg(os.path.join(self.tmp, "nowhere"))
        self.assertEqual(rc, 4, out)

    def test_the_leg_never_launches_or_locks(self):
        run = plant_run(os.path.join(self.tmp, "quiet"))
        with mock.patch.object(gate, "_lock") as lock, mock.patch.object(gate, "run_gate") as launch, \
                mock.patch.object(gate, "free_gb") as disk:
            rc, _ = self.leg(run)
            self.capture(run)
        self.assertEqual(rc, 0)
        lock.assert_not_called()
        launch.assert_not_called()
        disk.assert_not_called()

    def test_an_unknown_leg_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            _run(["--leg", "sideways", self.tmp])


class TheExitCodesAreDistinct(unittest.TestCase):
    def test_no_refs_and_capture_refusals_collide_with_nothing(self):
        taken = {0, 1, 2, 3, 4, gate.REFUSE_STALE, 7, gate.REFUSE_REVISION}
        self.assertNotIn(gate.REFUSE_NO_REFS, taken)
        self.assertNotIn(gate.REFUSE_CAPTURE, taken)
        self.assertNotEqual(gate.REFUSE_NO_REFS, gate.REFUSE_CAPTURE)


if __name__ == "__main__":
    unittest.main()
