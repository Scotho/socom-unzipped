"""Post keyboard messages to a game window without changing focus.

Two key maps: PCSX2's [Pad1] keyboard bindings (tools/pcsx2/inis/PCSX2.ini) and our runner's
socom2_host_input keyboard map (arrows, Enter=START, Backspace=SELECT, Z/X/C/V = Square/Cross/
Circle/Triangle, Q/E = L1/R1, 1/3 = L2/R2)."""
import ctypes
import time
from ctypes import wintypes as wt

user32 = ctypes.windll.user32
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
_ARROWS = {"UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27}
MAPS = {
    "pcsx2": {**_ARROWS, "CROSS": 0x4B, "CIRCLE": 0x4C, "SQUARE": 0x4A, "TRIANGLE": 0x49,
              "START": 0x0D, "SELECT": 0x08, "L1": 0x51, "R1": 0x45, "L2": 0x31, "R2": 0x33},
    "ours": {**_ARROWS, "CROSS": 0x58, "CIRCLE": 0x43, "SQUARE": 0x5A, "TRIANGLE": 0x56,
             "START": 0x0D, "SELECT": 0x08, "L1": 0x51, "R1": 0x45, "L2": 0x31, "R2": 0x33,
             # left stick (W/A/S/D) and right stick (I/J/K/L) in socom2_host_input.cpp keyboard mode
             "W": 0x57, "A": 0x41, "S": 0x53, "D": 0x44, "I": 0x49, "J": 0x4A, "K": 0x4B, "L": 0x4C},
}
WINDOW_TITLES = {"pcsx2": "SOCOM II - U.S. Navy SEALs", "ours": "PS2-Recomp"}


def child_windows(main_hwnd):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        out.append(h)
        return True

    user32.EnumChildWindows(main_hwnd, cb, 0)
    return out


def press(main_hwnd, button, target, hold_s=0.15):
    vk = MAPS[target][button.upper()]
    scan = user32.MapVirtualKeyW(vk, 0)
    ext = (1 << 24) if vk in _ARROWS.values() else 0   # arrows are extended keys
    for h in [main_hwnd] + child_windows(main_hwnd):
        user32.PostMessageW(h, WM_KEYDOWN, vk, (scan << 16) | ext | 1)
    time.sleep(hold_s)
    for h in [main_hwnd] + child_windows(main_hwnd):
        user32.PostMessageW(h, WM_KEYUP, vk, (scan << 16) | ext | 0xC0000001)
