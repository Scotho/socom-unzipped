"""--accept-pins must not DROP a pin while it accepts another one -- and (issue #45) must not write at all
until the run has completed.

History (2026-09-25, before #45's fix): found by the r0004 rebuild (logs/parity/gate/s11_r0004_rebuild1). The
launch path THEN wrote the standard twice: once BEFORE the lock and the launch, from the pins it can measure then, and once after the run, but
only when the late-joining `mapping` pin drifted. `mapping` is only knowable after a stage has run and the
runtime has printed its line, so at the early write it is absent -- and a rewrite built from the measured
set alone drops it. A run that drifts on `env` ALONE therefore rewrote the standard with `mapping` gone
(the second write never fired: `mapping` had not drifted against the standard held in memory), while the
same summary printed `PIN mapping sha256=c393b87b99732a1f ok`. The NEXT gate on that revision then saw an
unpinned input and was REFUSED (exit 7) -- a standard that silently lost a pin, which is the failure this
whole mechanism exists to make impossible.

The fix is the shape that cannot drop: the write carries every pin the previous standard held for names the
run could not measure, and replaces only the ones it did measure. `gate --pins --accept-pins` shows why it
has to be the carry rather than merely "one write at the end": that path never launches, so its `mapping` is
absent at EVERY moment it could write.

Since #45 (Sprint 13 H3) there is one write, after a run whose every wanted stage PASSed (S13-R5): a gate the
lock refuses, whose stage raises after the lock, or whose stage FAILs, leaves the standard byte-identical. The carry above still
matters for `gate --pins --accept-pins`, which never measures `mapping`.

Sibling module of test_gate_pins.py (kept separate on purpose: another agent holds that file).
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools_py.parity import gate, pins

MAPPING_A = "ab" * 32
MAPPING_B = "cd" * 32
# A stand-in game image carrying only a build banner, which is all guest_addresses.launch_revision reads,
# and the real r0001 image's own banner character for character. Every case here is a LAUNCH, and since
# Task 19 a launch that cannot say which revision it is refuses (exit 8) rather than read r0001's probe
# addresses on an r0004 build -- so each case names its image instead of leaving it to whatever
# `game/disc` happens to hold. Same fixture and same reason as test_gate_pins._LaunchCase.
BANNER_STAND_IN = b"\x7fELF" + b"\0" * 64 + b"SOCOM 2 %s\0" + b"\0" * 64
R0001_BANNER = b"r0001 17:22:21 Oct 11 2003"


def stage_printing(mapping):
    """A run_gate stand-in that writes the runtime's mapping line into <stage>.game.log, as a real stage
    does, so the late pin joins."""
    def stage(name, out_root):
        with open(os.path.join(out_root, name + ".game.log"), "w") as f:
            f.write("[socom2] input mapping sha256=%s\n" % mapping)
        return True, "ok " + name
    return stage


class AcceptPinsKeepsEveryPin(unittest.TestCase):
    """main() with the launch mocked out: no lock, no drive, no game. The standard and the stamp are per
    test; the card is a temp directory named through PS2X_MC_DIR."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.card = os.path.join(self.tmp, "card")
        os.makedirs(self.card)
        with open(os.path.join(self.card, "SCRATCHPAD.DAT"), "wb") as f:
            f.write(b"pristine")
        # The image this "launch" would run. game/ is git-ignored, so on a bare clone -- every CI runner --
        # there is none at the default path, and gate.main's launch path refuses (exit 8) rather than
        # guess. The rule is right; what these cases owe it is a stated revision, not a softer rule.
        self.game_elf = os.path.join(self.tmp, "r0001_stand_in.elf")
        with open(self.game_elf, "wb") as f:
            f.write(BANNER_STAND_IN % R0001_BANNER)
        self.expected = os.path.join(self.tmp, "pins.json")
        self.stamp = "s11_accept_pins_test_%d" % os.getpid()
        self.out_root = os.path.join("logs", "parity", "gate", self.stamp)
        shutil.rmtree(self.out_root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.out_root, True)
        self.env = mock.patch.dict(os.environ, {"PS2X_MC_DIR": self.card,
                                                "SOCOM_GAME_ELF": self.game_elf}, clear=False)
        self.env.start()
        # addCleanup, not tearDown: tearDown does not run when setUp raises, and the rest of setUp is
        # assertions. When the revision refusal broke the line below, the `exe_line` patch stayed live
        # for the whole process and failed two cases in test_gate_exe_line -- a module that has nothing
        # to do with this one and passes on its own. One failure must not become six.
        self.addCleanup(self.env.stop)
        for k in [k for k in os.environ if k.startswith("PS2X_") and k != "PS2X_MC_DIR"]:
            del os.environ[k]
        self.patches = [
            mock.patch.object(pins, "EXPECTED", self.expected),
            mock.patch.object(gate, "free_gb", return_value=99.0),
            mock.patch.object(gate, "exe_line", return_value="EXE dist/socom2.exe bytes=1 sha256=" + "00" * 32),
            mock.patch.object(gate, "_lock", return_value=subprocess.CompletedProcess(["x"], 0, "", "")),
            # the exe freshness refusal (S14 E4) is test_gate_fresh's; here no source is ever newer
            mock.patch.object(gate, "freshness_roots", return_value=[]),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        pins.write_expected(gate.collect_pins(), self.expected, note="test standard")
        # A standard that already holds a mapping pin, set the only way one is ever set: an accepted run.
        rc, out, _ = self._main(["--accept-pins"], stage=stage_printing(MAPPING_A))
        self.assertEqual(rc, 0, out)
        self.assertEqual(pins.load_expected(self.expected)["mapping"], MAPPING_A)

    def _main(self, argv, stage=None):
        stage = stage or (lambda name, out_root: (True, "ok " + name))
        out = io.StringIO()
        with mock.patch.object(gate, "run_gate", side_effect=stage) as run, contextlib.redirect_stdout(out):
            rc = gate.main(["--stamp", self.stamp, "--only", "title"] + argv)
        return rc, out.getvalue(), run

    def _summary(self):
        with open(os.path.join(self.out_root, "summary.txt"), encoding="utf-8") as f:
            return f.read()

    def _drift_env(self):
        """An operator variable the standard's env pin does not hold -- `env` drifts, nothing else does."""
        os.environ["PS2X_GS_STATS"] = "1"

    def test_a_drift_on_env_alone_keeps_the_mapping_pin_the_standard_held(self):
        """The s11_r0004_rebuild1 defect, reproduced: env drifts, mapping does not. The early write happens
        before any stage has printed the mapping line, so a rewrite from the measured set alone loses it,
        and the late write does not fire to put it back."""
        self._drift_env()
        rc, out, _ = self._main(["--accept-pins"], stage=stage_printing(MAPPING_A))
        self.assertEqual(rc, 0, out)
        summary = self._summary()
        self.assertIn("PIN mapping sha256=%s ok; from title.game.log\n" % MAPPING_A, summary)
        self.assertIn("PINS ACCEPTED: env -> ", summary)
        standard = pins.load_expected(self.expected)
        self.assertEqual(standard["mapping"], MAPPING_A,
                         "the standard must still carry the mapping pin the summary called ok")
        self.assertEqual(standard["env"], gate.collect_pins()["env"].sha256, "and the drifted pin is the new one")
        with open(self.expected, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["detail"].get("mapping"), "from title.game.log",
                             "a carried pin keeps the detail that describes it")
        # The whole point: the next gate on this revision is not refused for an unpinned mapping.
        rc, out, _ = self._main([], stage=stage_printing(MAPPING_A))
        self.assertEqual(rc, 0, out)
        self.assertIn("PINS MATCH", self._summary())

    def test_both_drifting_leaves_both_measured_values_in_the_standard(self):
        self._drift_env()
        rc, out, _ = self._main(["--accept-pins"], stage=stage_printing(MAPPING_B))
        self.assertEqual(rc, 0, out)
        standard = pins.load_expected(self.expected)
        self.assertEqual(standard["mapping"], MAPPING_B, "the late pin's measured value wins over the carried one")
        self.assertEqual(standard["env"], gate.collect_pins()["env"].sha256)
        self.assertIn("PIN mapping sha256=%s accepted (was %s); from title.game.log\n" % (MAPPING_B, MAPPING_A),
                      self._summary())
        rc, out, _ = self._main([], stage=stage_printing(MAPPING_B))
        self.assertEqual(rc, 0, out)
        self.assertIn("PINS MATCH", self._summary())

    def _standard_bytes(self):
        with open(self.expected, "rb") as f:
            return f.read()

    def test_nothing_drifting_writes_nothing(self):
        before = self._standard_bytes()
        rc, out, _ = self._main(["--accept-pins"], stage=stage_printing(MAPPING_A))
        self.assertEqual(rc, 0, out)
        self.assertIn("PINS MATCH", self._summary())
        self.assertEqual(self._standard_bytes(), before,
                         "a matching run leaves the standard byte for byte as it found it")

    def test_a_gate_queued_then_refused_by_the_lock_leaves_the_standard_byte_identical(self):
        """Issue #45: `--accept-pins` rewrote the standard at START-UP, before the lock wait, so a gate
        queued and then cancelled had already rewritten it (s11_r0004_node1, 2026-09-24; s11_r0004_rebuild1
        with a stray PS2X_AUDIO_VOLUME=0, 2026-09-25). The lock refusing is the cancellation: nothing ran,
        so nothing may be accepted -- the standard is written once, after the run, or not at all."""
        before = self._standard_bytes()
        self._drift_env()
        busy = subprocess.CompletedProcess(["x"], 1, "BUSY: another owner\n", "")
        with mock.patch.object(gate, "_lock", return_value=busy):
            rc, out, run = self._main(["--accept-pins"], stage=stage_printing(MAPPING_B))
        self.assertEqual(rc, 2, out)
        self.assertEqual(run.call_count, 0, "a refused lock launches nothing")
        self.assertEqual(self._standard_bytes(), before,
                         "a gate that never got the lock must leave the standard byte for byte as it found it")
        self.assertIn("standard unchanged", out)

    def test_a_stage_that_raises_after_the_lock_leaves_the_standard_byte_identical(self):
        """The other cancellation #45 names: the lock was taken, then the run died (a stage exception, a
        Ctrl-C). The accepted write used to sit in the `finally` and fired anyway."""
        before = self._standard_bytes()
        self._drift_env()

        def stage(name, out_root):
            raise KeyboardInterrupt("cancelled after the lock")

        out = io.StringIO()
        with mock.patch.object(gate, "run_gate", side_effect=stage), contextlib.redirect_stdout(out):
            with self.assertRaises(KeyboardInterrupt):
                gate.main(["--stamp", self.stamp, "--only", "title", "--accept-pins"])
        self.assertEqual(self._standard_bytes(), before,
                         "a run that did not complete must leave the standard byte for byte as it found it")
        self.assertIn("PINS NOT ACCEPTED: the run did not complete", out.getvalue())
        self.assertIn("PINS DRIFTED: env", self._summary())

    def test_a_run_whose_stage_fails_leaves_the_standard_byte_identical(self):
        """S13-R5 (2026-09-25): a standard is the measured input set of a run that PASSED. A FAILed run says
        nothing about whether its inputs are right -- the mirror of #45's second instance, a good run with a
        stray knob -- so it may not set one, and the drift it carried stays refused."""
        before = self._standard_bytes()
        self._drift_env()

        def stage(name, out_root):
            stage_printing(MAPPING_A)(name, out_root)
            return False, "scored badly"

        rc, out, _ = self._main(["--accept-pins"], stage=stage)
        self.assertEqual(self._standard_bytes(), before,
                         "a run whose stage FAILed must leave the standard byte for byte as it found it")
        self.assertIn("PINS NOT ACCEPTED: 1 of 1 stages FAILed -- ", out)
        self.assertEqual(rc, 7, out)
        self.assertIn("PINS DRIFTED: env", self._summary())

    def test_the_accepted_standard_is_written_after_the_run_and_the_summary_says_so(self):
        """The write happens once the stages have run: a run_gate stand-in that reads the standard sees the
        one the gate started with, and the summary's verdict names when it was written."""
        before = self._standard_bytes()
        self._drift_env()
        seen = []

        def stage(name, out_root):
            seen.append(self._standard_bytes())
            return stage_printing(MAPPING_A)(name, out_root)

        rc, out, _ = self._main(["--accept-pins"], stage=stage)
        self.assertEqual(rc, 0, out)
        self.assertEqual(seen, [before], "the standard must not be rewritten before (or during) the run")
        self.assertNotEqual(self._standard_bytes(), before)
        self.assertIn("PINS ACCEPTED: env -> %s rewritten after the run\n" % self.expected, self._summary())

    def test_a_dry_accept_pins_cannot_drop_the_mapping_it_never_measures(self):
        """--pins --accept-pins launches nothing, so `mapping` is absent at every moment that path could
        write: this is why the fix is the carry and not simply a later write."""
        self._drift_env()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = gate.main(["--pins", "--accept-pins"])
        self.assertEqual(rc, 0, out.getvalue())
        self.assertEqual(pins.load_expected(self.expected)["mapping"], MAPPING_A,
                         "a check that cannot measure the mapping pin must not delete it")


if __name__ == "__main__":
    unittest.main()
