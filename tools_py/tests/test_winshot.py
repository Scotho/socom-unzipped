"""winshot.find_window / winshot.capture against a real Tk window (Windows with a desktop only).

Moved from tools_py/parity/test_winshot.py (Sprint 5 Task 0): it was pytest-style and had never run.
"""
import os
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


if __name__ == "__main__":
    unittest.main()
