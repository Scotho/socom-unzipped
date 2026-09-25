"""Sprint 9 Goal 2: a gate record says which executable it scored -- the release build is gated as itself."""
import hashlib
import os
import tempfile
import unittest

from tools_py.parity import gate


class GateExeLineTest(unittest.TestCase):
    def test_names_the_runner_its_size_and_its_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "socom2.exe" if os.name == "nt" else "socom2")
            with open(exe, "wb") as fh:
                fh.write(b"not really a runner")
            line = gate.exe_line(env={"SOCOM_EXE": exe})
            self.assertEqual(line, "EXE %s bytes=19 sha256=%s"
                             % (exe, hashlib.sha256(b"not really a runner").hexdigest()))

    def test_a_missing_runner_is_said_not_raised(self):
        name = "socom2.exe" if os.name == "nt" else "socom2"
        line = gate.exe_line(env={"SOCOM_EXE": os.path.join("no", "such", "folder", name)})
        self.assertTrue(line.startswith("EXE "), line)
        self.assertIn("UNREADABLE", line)


class GateElfLineTest(unittest.TestCase):
    """Sprint 11 Task 19: ... and which GAME IMAGE it loaded. The EXE line names the recompiled runtime;
    it does not name the pressing of the game that runtime ran, and since r0004 those are two independent
    choices ($SOCOM_EXE and $SOCOM_GAME_ELF). A 3/3 record that does not name the image and its revision
    proves nothing about which build was gated."""

    BANNER = b"\x7fELF" + b"\0" * 64 + b"SOCOM 2 r0004 10:14:38 Nov  3 2004\0" + b"\0" * 64

    def test_names_the_image_its_size_its_sha256_and_its_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            elf = os.path.join(tmp, "socom2_game.elf")
            with open(elf, "wb") as fh:
                fh.write(self.BANNER)
            line = gate.elf_line(env={"SOCOM_GAME_ELF": elf})
            self.assertIn("bytes=%d" % len(self.BANNER), line)
            self.assertIn("sha256=%s" % hashlib.sha256(self.BANNER).hexdigest(), line)
            self.assertTrue(line.endswith(" r0004"), line)

    def test_an_image_with_no_banner_says_so_rather_than_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            elf = os.path.join(tmp, "socom2_game.elf")
            with open(elf, "wb") as fh:
                fh.write(b"\x7fELF" + b"\0" * 128)
            self.assertIn("NO BANNER", gate.elf_line(env={"SOCOM_GAME_ELF": elf}))

    def test_a_missing_image_is_said_not_raised(self):
        line = gate.elf_line(env={"SOCOM_GAME_ELF": os.path.join("no", "such", "image.elf")})
        self.assertTrue(line.startswith("ELF "), line)
        self.assertIn("UNREADABLE", line)


if __name__ == "__main__":
    unittest.main()
