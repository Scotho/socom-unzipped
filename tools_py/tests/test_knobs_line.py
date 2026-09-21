"""Sprint 9 Goal 3: what a stranger's environment can do to the runner -- nothing -- and how the log says so.
Sub-second bare runs that stop at exit 68 before a window opens (as test_runner_exit_codes does); they obey the
quiet gate like every suite. Skipped where there is no runner build."""
import glob
import os
import subprocess
import tempfile
import unittest

from tools_py.parity import hostplatform

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXE = os.path.join(ROOT, hostplatform.runtime_exe())


@unittest.skipUnless(os.path.isfile(EXE), "no runner build at " + EXE)
class KnobsLineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self._tmp.name, "outer", "home")
        os.makedirs(self.home)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("PS2X_")}

    def tearDown(self):
        self._tmp.cleanup()

    def _knobs_line(self, *args, **extra):
        subprocess.run([EXE, *args, "--home", self.home], capture_output=True, text=True, errors="replace",
                       timeout=60, env=dict(self.env, **extra), cwd=self.home)
        logs = sorted(glob.glob(os.path.join(self.home, "logs", "run_*.log")))
        self.assertTrue(logs, "the bare run writes logs/run_<stamp>.log")
        with open(logs[-1], "r", errors="replace") as fh:
            lines = [line.rstrip("\r\n") for line in fh if line.startswith("[knobs]")]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def test_a_stranger_with_a_forgotten_probe_is_told_it_was_ignored(self):
        line = self._knobs_line(PS2X_GS_BACKEND="cpu", PS2X_GS_NO_ZTEST="1")
        self.assertTrue(line.startswith("[knobs] dev=0 set:"), line)
        self.assertIn("| ignored without --dev: PS2X_GS_BACKEND PS2X_GS_NO_ZTEST", line)
        self.assertNotIn("PS2X_GS_BACKEND=cpu", line)

    def test_the_dev_flag_opens_them_and_may_stand_before_home(self):
        line = self._knobs_line("--dev", PS2X_GS_BACKEND="cpu")
        self.assertTrue(line.startswith("[knobs] dev=1 set:"), line)
        self.assertIn("PS2X_GS_BACKEND=cpu", line)
        self.assertNotIn("ignored", line)

    def test_the_variable_is_the_same_switch(self):
        line = self._knobs_line(PS2X_DEV="1", PS2X_GS_BACKEND="cpu")
        self.assertIn("dev=1", line)
        self.assertIn("PS2X_DEV=1", line)
        self.assertIn("PS2X_GS_BACKEND=cpu", line)

    def test_a_shipping_setting_needs_no_switch_and_a_default_is_not_news(self):
        line = self._knobs_line(PS2X_GS_SCALE="2", PS2X_AUDIO_VOLUME="100")
        self.assertIn("PS2X_GS_SCALE=2", line)
        self.assertNotIn("PS2X_AUDIO_VOLUME", line)
        self.assertNotIn("ignored", line)


if __name__ == "__main__":
    unittest.main()
