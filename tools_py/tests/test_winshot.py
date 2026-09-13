"""winshot.find_window / winshot.capture against a real Tk window (Windows with a desktop only).

Moved from tools_py/parity/test_winshot.py (Sprint 5 Task 0): it was pytest-style and had never run.
"""
import os
import tempfile
import time
import unittest


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

    def test_no_max_age_keeps_the_old_behaviour(self):
        self.age(60.0)
        self.winshot.grab(self.HWND)

if __name__ == "__main__":
    unittest.main()
