import tkinter as tk
from tools_py.parity import winshot


def test_capture_tk_window():
    root = tk.Tk()
    root.title("winshot-test-window")
    root.geometry("300x200")
    root.configure(bg="red")
    root.update()
    hwnd = winshot.find_window("winshot-test-window")
    assert hwnd
    img = winshot.capture(hwnd)
    root.destroy()
    assert img.size[0] >= 290 and img.size[1] >= 190
    assert img.getpixel((10, 10))[0] > 200
