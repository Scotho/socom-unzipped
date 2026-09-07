"""Post keyboard messages to PCSX2's window (no focus change), using its [Pad1] keyboard bindings
from tools/pcsx2/inis/PCSX2.ini: arrows, Cross=K, Circle=L, Square=J, Triangle=I, Start=Return,
Select=Backspace, L1=Q, R1=E, L2=1, R2=3."""
import ctypes
import time
from ctypes import wintypes as wt

user32 = ctypes.windll.user32
VK = {"UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27, "CROSS": 0x4B, "CIRCLE": 0x4C,
      "SQUARE": 0x4A, "TRIANGLE": 0x49, "START": 0x0D, "SELECT": 0x08, "L1": 0x51, "R1": 0x45,
      "L2": 0x31, "R2": 0x33}
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101


def child_windows(main_hwnd):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        out.append(h)
        return True

    user32.EnumChildWindows(main_hwnd, cb, 0)
    return out


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def targets(main_hwnd):
    """Main window plus every child (Qt hosts the render surface in a child widget)."""
    return [main_hwnd] + child_windows(main_hwnd)


def press(main_hwnd, button, hold_s=0.1, post=None):
    vk = VK[button.upper()]
    scan = user32.MapVirtualKeyW(vk, 0)
    fn = post or user32.PostMessageW
    for h in targets(main_hwnd):
        fn(h, WM_KEYDOWN, vk, (scan << 16) | 1)
    time.sleep(hold_s)
    for h in targets(main_hwnd):
        fn(h, WM_KEYUP, vk, (scan << 16) | 0xC0000001)
