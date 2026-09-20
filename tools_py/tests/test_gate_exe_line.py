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


if __name__ == "__main__":
    unittest.main()
