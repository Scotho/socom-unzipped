"""Sprint 10 Goal 3: the PCSX2 shell inherits the verified lobby flow and only changes what the window needs."""
import tempfile
import unittest
from unittest import mock

from tools_py.parity import online_login_ours as L
from tools_py.parity import pcsx2_shell


class Pcsx2ShellTest(unittest.TestCase):
    def test_the_shell_names_its_target_and_the_console_press_hold(self):
        self.assertEqual(L.Shell.target, "ours")
        self.assertEqual(pcsx2_shell.Pcsx2Shell.target, "pcsx2")
        self.assertEqual(pcsx2_shell.Pcsx2Shell.press_hold_s, 0.15)
        self.assertTrue(issubclass(pcsx2_shell.Pcsx2Shell, L.Shell), "every staged step of ours' flow applies")

    def test_a_press_goes_to_the_pcsx2_keys_map_with_the_console_hold(self):
        sh = pcsx2_shell.Pcsx2Shell.__new__(pcsx2_shell.Pcsx2Shell)   # no window, no references
        sh.hwnd, sh.out, sh.t0, sh.tag, sh.pad_file, sh.stages = 0, tempfile.gettempdir(), 0.0, "B_", None, ()
        sh.stage_sleep = lambda seconds: None
        with mock.patch.object(L.keys, "press") as press, mock.patch.object(L.winshot, "ensure_client_size", return_value=False):
            sh.press("cross", 0.0)
        press.assert_called_once_with(0, "cross", "pcsx2", hold_s=0.15)

    def test_a_pad_press_without_a_pad_file_is_a_posted_key(self):
        # choose_map walks the map list through pad_press; the console shell has no injected pad (leg 2c crashed
        # on `None + ".tmp"`), so the press is posted like every other press of that shell.
        sh = pcsx2_shell.Pcsx2Shell.__new__(pcsx2_shell.Pcsx2Shell)
        sh.hwnd, sh.out, sh.t0, sh.tag, sh.pad_file, sh.stages = 0, tempfile.gettempdir(), 0.0, "A_", None, ()
        sh.stage_sleep = lambda seconds: None
        with mock.patch.object(L.keys, "press") as press, mock.patch.object(L.winshot, "ensure_client_size", return_value=False):
            sh.pad_press("DOWN", wait=0.0)
        press.assert_called_once_with(0, "DOWN", "pcsx2", hold_s=0.15)

    def test_run_attaches_to_the_launched_instance_and_plays_the_staged_steps(self):
        calls = []
        with mock.patch.object(pcsx2_shell.pcsx2_ctl, "_hwnd", return_value=7), \
             mock.patch.object(pcsx2_shell.winshot, "keep_on_top"), \
             mock.patch.object(pcsx2_shell.winshot, "ensure_client_size", return_value=False), \
             mock.patch.object(L, "ready", lambda sh: calls.append(("ready", type(sh).__name__, sh.tag))), \
             mock.patch.object(pcsx2_shell.Pcsx2Shell, "shot", lambda self, label, max_age=None: calls.append(("shot", label))), \
             mock.patch.object(pcsx2_shell.Pcsx2Shell, "log", lambda self, m: calls.append(("log", m))):
            with tempfile.TemporaryDirectory() as d:
                rc = pcsx2_shell.run("ready", "B", d, "socomq", "socomq", False, "test", "frostfire")
        self.assertEqual(rc, 0)
        self.assertEqual(calls[0], ("ready", "Pcsx2Shell", "B_"))
        self.assertIn(("log", "LOBBY class=ok"), calls)
        self.assertEqual(calls[-1], ("shot", "final"))

    def test_a_lobby_failure_exits_with_the_ladder_contracts_code(self):
        with mock.patch.object(pcsx2_shell, "run", side_effect=L.LobbyFail("screen:login", "not there")):
            self.assertEqual(pcsx2_shell.main(["login", "B", "--out", tempfile.gettempdir()]), L.LOBBY_FAIL_EXIT)


if __name__ == "__main__":
    unittest.main()
