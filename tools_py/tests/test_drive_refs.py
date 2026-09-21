"""untilref's reference may have a per-target sibling: one step script drives ours and the console, and a band
that separates the lit main-menu row needs each machine's own rendering (music round four, 2026-09-20)."""
import os
import tempfile
import unittest

from tools_py.parity import drive


class RefForTargetTest(unittest.TestCase):
    def test_the_sibling_is_used_when_it_exists(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "ref_main_menu_ours.png")
            sibling = os.path.join(d, "ref_main_menu_ours.pcsx2.png")
            for p in (base, sibling):
                open(p, "wb").close()
            self.assertEqual(drive.ref_for_target(base, "pcsx2"), sibling)
            self.assertEqual(drive.ref_for_target(base, "ours"), base)

    def test_without_a_sibling_the_named_reference_stands(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "ref_hud_ours.png")
            open(base, "wb").close()
            self.assertEqual(drive.ref_for_target(base, "pcsx2"), base)
            self.assertEqual(drive.ref_for_target(base, None), base)

    def test_the_checked_in_main_menu_reference_has_its_console_sibling(self):
        base = os.path.join("scripts", "parity", "ref_main_menu_ours.png")
        self.assertTrue(drive.ref_for_target(base, "pcsx2").endswith(".pcsx2.png"))


if __name__ == "__main__":
    unittest.main()
