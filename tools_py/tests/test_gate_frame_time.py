"""Sprint 13 Task V4: the mission stage's FRAME line and the informational frame-time pin (S13-R3).

The gate's mission stage sets PS2X_PC_SAMPLER=1, so its game log carries a `[pc-sampler]` row a second with
`t=` (host seconds) and `vsync=` (the guest VBlank count, paced by the GL back-pressure). tools_py/parity/
frame_time.py reads host ms per guest VBlank over the HUD-reached stretch; the gate prints it as
`FRAME mean=<ms> worst=<ms> n=<frames>` on the summary and records it in the run's pins.json as an
informational pin that is never compared (S13-R3: no refusal until three gates agree on its spread).

The fixture is s13_proof4_gate's (2026-09-25, 3/3 PINS MATCH on f90eeec0...): its mission.game.log's sampler
rows from t=310 s (the HUD step is at 320.7 s) and the two drive-log lines that name the HUD step, saved as
.txt because *.log is git-ignored. Over the whole stamp the reader gives the same numbers as over the fixture.
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tools_py.parity import frame_time, gate, pins
from tools_py.tests.test_gate_pins import _LaunchCase

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "gate", "frame_s13_proof4")
DRIVE = os.path.join(FIXTURE, "mission.drive.txt")
GAME = os.path.join(FIXTURE, "mission.game.txt")


class Reader(unittest.TestCase):
    def test_the_saved_stamps_numbers(self):
        ft, why = frame_time.read(DRIVE, GAME)
        self.assertIsNone(why)
        self.assertAlmostEqual(ft.mean_ms, 28.37, places=2)
        self.assertAlmostEqual(ft.worst_ms, 41.67, places=2)
        self.assertEqual(ft.n, 5609)
        self.assertEqual(ft.windows, 159)
        self.assertAlmostEqual(ft.start_t, 321.2, places=1, msg="the first row at or after the HUD step's 320.7 s")

    def test_the_hud_ref_is_the_gates(self):
        self.assertEqual(frame_time.HUD_REF_NAME, gate.HUD_REF_NAME)

    def test_a_window_with_no_vblank_is_folded_into_the_next_one(self):
        ft = frame_time.measure([(0.0, 0), (1.0, 60), (2.0, 60), (3.0, 61)], 0.0)
        self.assertEqual(ft.n, 61)
        self.assertAlmostEqual(ft.worst_ms, 2000.0)
        self.assertAlmostEqual(ft.mean_ms, 3000.0 / 61)

    def test_rows_before_the_hud_are_not_counted(self):
        ft = frame_time.measure([(0.0, 0), (1.0, 10), (2.0, 70), (3.0, 130)], 1.5)
        self.assertEqual((ft.n, round(ft.mean_ms, 2)), (60, 16.67))

    def test_no_hud_is_no_data(self):
        tmp = tempfile.mkdtemp()
        try:
            drive = os.path.join(tmp, "d.txt")
            with open(drive, "w") as f:
                f.write("untilref(scripts/parity/ref_hud_ours.png): 9 presses, dist=40.0 matched=False\n")
            ft, why = frame_time.read(drive, GAME)
            self.assertIsNone(ft)
            self.assertEqual(frame_time.line(ft, why), "FRAME NO-DATA (HUD not reached in the drive log)")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class GateFrameLine(_LaunchCase):
    """main() with the mission stage mocked: it leaves the fixture's logs where run_gate leaves a live run's."""

    def _stage(self, game=GAME):
        def stage(name, out_root):
            shutil.copyfile(DRIVE, os.path.join(out_root, "mission.drive.log"))
            shutil.copyfile(game, os.path.join(out_root, "mission.game.log"))
            return True, "ok mission"
        return stage

    def _run(self, game=GAME):
        out = io.StringIO()
        with mock.patch.object(gate, "run_gate", side_effect=self._stage(game)), contextlib.redirect_stdout(out):
            rc = gate.main(["--stamp", self.stamp, "--only", "mission"])
        return rc, out.getvalue()

    def _record(self):
        with open(os.path.join(self.out_root, pins.RECORD_NAME)) as f:
            return json.load(f)

    def test_the_mission_summary_carries_the_frame_line_and_the_informational_pin(self):
        rc, out = self._run()
        self.assertEqual(rc, 0, out)
        summary = self._summary()
        self.assertIn("\nFRAME mean=28.37 worst=41.67 n=5609 (", summary)
        self.assertIn("PIN frame mean_ms=28.37 worst_ms=41.67 n=5609 recorded (informational, S13-R3", summary)
        self.assertIn("FRAME mean=28.37 worst=41.67 n=5609", out)
        info = self._record()["informational"]
        self.assertEqual((info["frame_mean_ms"], info["frame_worst_ms"], info["frame_n"]), (28.37, 41.67, 5609))
        self.assertNotIn("frame", self._record()["pins"], "the frame numbers are not a pin the standard can hold")

    def test_a_differing_frame_time_does_not_fail_the_gate(self):
        rc, out = self._run()
        self.assertEqual(rc, 0, out)
        # A second run whose frame time differs: only the rows after the HUD's first 40 seconds.
        slow = os.path.join(self.tmp, "slow.txt")
        with open(GAME) as src, open(slow, "w") as dst:
            dst.writelines(l for l in src if float(l.split(" t=", 1)[1].split()[0]) >= 360.0)
        # ... and a standard that somehow names the frame pin: still never compared.
        with open(self.expected) as f:
            doc = json.load(f)
        doc["pins"]["frame"] = "28.37"
        with open(self.expected, "w") as f:
            json.dump(doc, f)
        rc, out = self._run(slow)
        self.assertEqual(rc, 0, out)
        summary = self._summary()
        self.assertNotIn("FRAME mean=28.37 ", summary)
        self.assertIn("recorded (informational, S13-R3", summary)
        self.assertIn("PINS MATCH", summary)
        self.assertEqual(self._record()["drifted"], [])

    def test_a_mission_with_no_sampler_rows_is_recorded_as_no_data_and_passes(self):
        empty = os.path.join(self.tmp, "empty.txt")
        open(empty, "w").close()
        rc, out = self._run(empty)
        self.assertEqual(rc, 0, out)
        summary = self._summary()
        self.assertIn("FRAME NO-DATA (no [pc-sampler] rows in the game log)", summary)
        self.assertIn("PIN frame absent (informational, S13-R3", summary)

    def test_a_stage_list_without_the_mission_prints_no_frame_line(self):
        rc, out, _ = self._main([])
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FRAME", self._summary())


class BaselineFrameLine(_LaunchCase):
    def test_a_re_score_prints_the_saved_stamps_frame_line(self):
        os.makedirs(self.out_root)
        shutil.copyfile(DRIVE, os.path.join(self.out_root, "mission.drive.log"))
        shutil.copyfile(GAME, os.path.join(self.out_root, "mission.game.log"))
        out = io.StringIO()
        with mock.patch.object(gate, "score_mission_log", return_value=(True, "m")), contextlib.redirect_stdout(out):
            rc = gate.main(["--baseline", self.out_root, "--revision", "r0001"])
        self.assertEqual(rc, 0, out.getvalue())
        self.assertIn("FRAME mean=28.37 worst=41.67 n=5609", out.getvalue())


if __name__ == "__main__":
    unittest.main()
