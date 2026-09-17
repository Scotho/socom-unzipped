"""Sprint 6 Task 8: drive.capture_step fails loudly when the window's client area is not 640x448 at a capture."""
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

from tools_py.parity import drive, winshot


class ClientRectTest(unittest.TestCase):
    def _capture(self, size):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s00.png")
            with mock.patch.object(winshot, "client_size", lambda hwnd: size), \
                 mock.patch.object(winshot, "grab", lambda hwnd, max_age=None: Image.new("RGB", (640, 448))):
                drive.capture_step(1234, path, hold=False)
            return os.path.exists(path)

    def test_the_game_frame_is_captured(self):
        self.assertTrue(self._capture((640, 448)))

    def test_a_fake_handle_is_captured(self):
        self.assertTrue(self._capture(None))   # tests attach shells to fake handles

    def test_a_resized_window_fails_loudly_and_saves_nothing(self):
        with self.assertRaises(winshot.ClientRectError) as cm:
            self._capture((983, 630))
        self.assertIn("983x630", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
