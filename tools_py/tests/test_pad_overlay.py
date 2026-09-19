"""Sprint 8 Goal 3 Task 4 Step B: the PTT probe's schedule arithmetic and its OR into the pad file.

The probe's one unacceptable failure is a silent one -- an overlay that pressed nothing would read as
"no button starts recording", which is a conclusion about the GAME. So the parser refuses a malformed
spec loudly, the schedule is a pure function of the clock, and with the knob unset the bytes written are
byte for byte what they were before this goal.
"""
import os
import time
import tempfile
import unittest

from tools_py.parity import online_login_ours as L


SPEC = "start=+10;hold=3.0;gap=2.0;buttons=L3:0x0002,R3:0x0004,L1:0x0400"


class PadOverlayScheduleTest(unittest.TestCase):
    def setUp(self):
        self.schedule = L.parse_pad_overlay(SPEC)
        self.schedule["epoch"] = 1000.0

    def test_parses_the_spec(self):
        self.assertEqual(self.schedule["hold"], 3.0)
        self.assertEqual(self.schedule["gap"], 2.0)
        self.assertTrue(self.schedule["relative"])
        self.assertEqual(self.schedule["start"], 10.0)
        self.assertEqual(self.schedule["buttons"],
                         [("L3", 0x0002), ("R3", 0x0004), ("L1", 0x0400)])

    def test_nothing_before_the_start(self):
        for t in (0.0, 999.0, 1009.9):
            self.assertEqual(L.pad_overlay_mask(t, self.schedule), (0, None), t)

    def test_each_button_in_its_own_window(self):
        # begin = 1010; step = 5 s (3 held, 2 idle).
        self.assertEqual(L.pad_overlay_mask(1010.0, self.schedule), (0x0002, "L3"))
        self.assertEqual(L.pad_overlay_mask(1012.9, self.schedule), (0x0002, "L3"))
        self.assertEqual(L.pad_overlay_mask(1015.0, self.schedule), (0x0004, "R3"))
        self.assertEqual(L.pad_overlay_mask(1020.0, self.schedule), (0x0400, "L1"))

    def test_nothing_during_the_gaps(self):
        for t in (1013.0, 1014.9, 1018.0, 1023.5):
            self.assertEqual(L.pad_overlay_mask(t, self.schedule), (0, None), t)

    def test_nothing_after_the_list_ends(self):
        for t in (1025.0, 1030.0, 2000.0):
            self.assertEqual(L.pad_overlay_mask(t, self.schedule), (0, None), t)

    def test_no_schedule_and_no_epoch_press_nothing(self):
        self.assertEqual(L.pad_overlay_mask(1010.0, None), (0, None))
        unarmed = L.parse_pad_overlay(SPEC)
        self.assertIsNone(unarmed["epoch"])
        self.assertEqual(L.pad_overlay_mask(1010.0, unarmed), (0, None))

    def test_an_absolute_start_is_a_unix_time(self):
        absolute = L.parse_pad_overlay("start=1500;hold=1;gap=1;buttons=R1:0x0800")
        absolute["epoch"] = 0.0
        self.assertEqual(L.pad_overlay_mask(1500.5, absolute), (0x0800, "R1"))
        self.assertEqual(L.pad_overlay_mask(1499.5, absolute), (0, None))


class PadOverlayParserTest(unittest.TestCase):
    def test_empty_is_no_overlay(self):
        self.assertIsNone(L.parse_pad_overlay(""))
        self.assertIsNone(L.parse_pad_overlay("   "))
        self.assertIsNone(L.parse_pad_overlay(None))

    def test_a_malformed_spec_is_refused_loudly(self):
        for bad in ("buttons", "hold=3", "buttons=L3", "buttons="):
            with self.assertRaises(ValueError, msg=bad):
                L.parse_pad_overlay(bad)

    def test_the_bit_masks_match_the_pad_the_runtime_parses(self):
        # socom2_host_input.h:38-41 and PAD_BUTTON here must agree, or the probe holds the wrong button
        # and the whole experiment answers the wrong question.
        for name, bit in L.PAD_BUTTON.items():
            spec = L.parse_pad_overlay(f"buttons={name}:0x{1 << bit:04x}")
            self.assertEqual(spec["buttons"][0][1], 1 << bit, name)


class PadFileWriteTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.saved = L._OVERLAY
        self.addCleanup(self._restore)

    def _restore(self):
        L._OVERLAY = self.saved
        L._OVERLAY_LAST[0] = None

    def _write(self, name, buttons=()):
        path = os.path.join(self.dir, name)
        L.write_pad_file(path, buttons=buttons)
        with open(path) as handle:
            return handle.read()

    def test_with_the_knob_unset_the_bytes_are_unchanged(self):
        L._OVERLAY = None
        self.assertEqual(self._write("pad_A.txt"), "b=0000 rx=128 ry=128 lx=128 ly=128\n")
        self.assertEqual(self._write("pad_A.txt", buttons=("CROSS",)),
                         "b=4000 rx=128 ry=128 lx=128 ly=128\n")

    def test_the_overlay_is_ored_into_the_drivers_own_mask(self):
        L._OVERLAY = L.parse_pad_overlay("start=+0;hold=3600;gap=1;buttons=L3:0x0002")
        L._OVERLAY["epoch"] = time.time()          # only the round-start hook arms it
        L._OVERLAY_LAST[0] = None
        self.assertEqual(self._write("pad_A.txt", buttons=("CROSS",)),
                         "b=4002 rx=128 ry=128 lx=128 ly=128\n")

    def test_only_instance_a_gets_the_overlay(self):
        L._OVERLAY = L.parse_pad_overlay("start=+0;hold=3600;gap=1;buttons=L3:0x0002")
        L._OVERLAY["epoch"] = time.time()          # only the round-start hook arms it
        L._OVERLAY_LAST[0] = None
        self.assertEqual(self._write("pad_A.txt"), "b=0002 rx=128 ry=128 lx=128 ly=128\n")
        self.assertEqual(self._write("pad_B.txt"), "b=0000 rx=128 ry=128 lx=128 ly=128\n")



class PadOverlayArmingTest(unittest.TestCase):
    """Regression for s8_voice_round2: the probe used to arm itself on the first pad write, which is during
    the login keyboard, and held a button through the typing -- the round died at LOBBY-FAIL before gameplay.
    An unarmed overlay presses nothing, for ever, however many times the pad is written."""

    def setUp(self):
        self.saved = L._OVERLAY
        self.dir = tempfile.mkdtemp()
        self.addCleanup(self._restore)

    def _restore(self):
        L._OVERLAY = self.saved
        L._OVERLAY_LAST[0] = None

    def test_an_unarmed_overlay_never_presses_anything(self):
        L._OVERLAY = L.parse_pad_overlay("start=+0;hold=3600;gap=1;buttons=L3:0x0002")
        L._OVERLAY_LAST[0] = None
        path = os.path.join(self.dir, "pad_A.txt")
        for _ in range(5):
            L.write_pad_file(path, buttons=("CROSS",))
            with open(path) as handle:
                self.assertEqual(handle.read(), "b=4000 rx=128 ry=128 lx=128 ly=128" + chr(10))
        self.assertIsNone(L._OVERLAY["epoch"], "writing the pad must not arm the probe")

if __name__ == "__main__":
    unittest.main()
