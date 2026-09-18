"""winshot.find_window / winshot.capture against a real Tk window (Windows with a desktop only).

Moved from tools_py/parity/test_winshot.py (Sprint 5 Task 0): it was pytest-style and had never run.
"""
import os
import tempfile
import time
import unittest
from unittest import mock

from tools_py.parity import winshot


def display_available():
    if os.name != "nt":
        return False
    try:
        import tkinter as tk
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


@unittest.skipUnless(display_available(), "needs Windows with a desktop (tkinter window)")
class TestWinshot(unittest.TestCase):
    def test_capture_tk_window(self):
        import tkinter as tk
        from tools_py.parity import winshot

        root = tk.Tk()
        try:
            root.title("winshot-test-window")
            root.geometry("300x200")
            root.configure(bg="red")
            # One update() returns before the first paint (the pytest original read 98 red at (10, 10)
            # when first executed on 2026-09-13); pump the event loop for ~0.5 s.
            for _ in range(5):
                root.update()
                time.sleep(0.1)
            hwnd = winshot.find_window("winshot-test-window")
            self.assertTrue(hwnd)
            img = winshot.capture(hwnd)
        finally:
            root.destroy()
        self.assertGreaterEqual(img.size[0], 290)
        self.assertGreaterEqual(img.size[1], 190)
        self.assertGreater(img.getpixel((10, 10))[0], 200)



@unittest.skipUnless(os.name == "nt", "winshot imports ctypes.windll")
class FrameFreshnessTest(unittest.TestCase):
    """Sprint 5 Task 3: `grab(hwnd, max_age=2.0)` refuses a frame file older than 2 s.
    Blind: a hung renderer that keeps writing new files (the file is fresh, the picture is not)."""

    HWND = 0x7FFF0001        # never a real window: the registered frame file is read, not PrintWindow

    def setUp(self):
        from unittest import mock
        from PIL import Image
        from tools_py.parity import winshot
        self.winshot = winshot
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "latest_frame_T.png")
        Image.new("RGB", (8, 8), (200, 10, 10)).save(self.path)
        winshot.register_frame_file(self.HWND, self.path)
        self.addCleanup(winshot._frame_files.pop, self.HWND, None)
        patcher = mock.patch.object(winshot, "FRAME_RETRY_S", 0.2)   # do not wait 3 s for a fresh file
        patcher.start()
        self.addCleanup(patcher.stop)

    def age(self, seconds):
        t = time.time() - seconds
        os.utime(self.path, (t, t))

    def test_back_dated_frame_file_raises(self):
        self.age(10.0)
        with self.assertRaises(self.winshot.StaleFrameError) as cm:
            self.winshot.grab(self.HWND, max_age=2.0)
        self.assertGreater(cm.exception.age, 9.0)
        self.assertIsInstance(cm.exception, RuntimeError)       # login's frame loops catch RuntimeError

    def test_negative_control_fresh_frame_is_returned(self):
        self.age(0.0)
        im = self.winshot.grab(self.HWND, max_age=2.0)
        self.assertEqual(im.getpixel((1, 1)), (200, 10, 10))

    def test_boundary(self):
        self.age(1.5)
        self.winshot.grab(self.HWND, max_age=2.0)
        self.age(2.6)
        with self.assertRaises(self.winshot.StaleFrameError):
            self.winshot.grab(self.HWND, max_age=2.0)

    def test_transient_error_on_the_last_retry_does_not_mask_a_stale_frame(self):
        from unittest import mock
        old = time.time() - 10.0
        calls = {"n": 0}

        def mtime(path):
            calls["n"] += 1
            if calls["n"] == 1:
                return old
            raise OSError("mid-rename")

        with mock.patch("os.path.getmtime", side_effect=mtime):
            with self.assertRaises(self.winshot.StaleFrameError):
                self.winshot.grab(self.HWND, max_age=2.0)
        self.assertGreater(calls["n"], 1)

    def test_no_max_age_keeps_the_old_behaviour(self):
        self.age(60.0)
        self.winshot.grab(self.HWND)

if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.name == "nt", "Windows capture API (winshot.wt.RECT / user32 SetWindowPos)")
class EnsureClientSize(unittest.TestCase):
    """s6_ladder10/11 (2026-09-16): instance A's window had been resized (983x630, then 729x462 client) and every
    fixed-box detector on it read garbage ('ONLINE not lit ... new game 18, online 14, lan 13'). The harness
    restores the 640x448 client area itself, keeping the window where it is and never activating it."""

    def _fake_user32(self, client, outer):
        import ctypes
        calls = []

        class U:
            def IsWindow(self, hwnd):
                return 1

            def GetClientRect(self, hwnd, prect):
                r = ctypes.cast(prect, ctypes.POINTER(winshot.wt.RECT)).contents
                r.left, r.top, r.right, r.bottom = 0, 0, client[0], client[1]
                return 1

            def GetWindowRect(self, hwnd, prect):
                r = ctypes.cast(prect, ctypes.POINTER(winshot.wt.RECT)).contents
                r.left, r.top, r.right, r.bottom = 100, 50, 100 + outer[0], 50 + outer[1]
                return 1

            def SetWindowPos(self, hwnd, after, x, y, w, h, flags):
                calls.append((w, h, flags))
                return 1
        return U(), calls

    def test_a_resized_client_is_restored_by_the_outer_difference(self):
        fake, calls = self._fake_user32(client=(729, 462), outer=(745, 501))
        with mock.patch.object(winshot, "user32", fake):
            self.assertTrue(winshot.ensure_client_size(1234, 640, 448))
        self.assertEqual(len(calls), 1)
        w, h, flags = calls[0]
        self.assertEqual((w, h), (745 - (729 - 640), 501 - (462 - 448)))
        self.assertTrue(flags & winshot.SWP_NOMOVE and flags & winshot.SWP_NOACTIVATE and flags & winshot.SWP_NOZORDER)

    def test_the_right_size_is_left_alone(self):
        fake, calls = self._fake_user32(client=(640, 448), outer=(656, 487))
        with mock.patch.object(winshot, "user32", fake):
            self.assertFalse(winshot.ensure_client_size(1234, 640, 448))
        self.assertEqual(calls, [])
