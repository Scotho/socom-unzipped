#!/usr/bin/env python
"""Capture a multi-frame PCSX2 GS dump at a savestate: launch PCSX2, load the state over PINE,
press the GS-dump hotkey twice (start / stop) and report the newest dump file.

The hotkey is rebound for the run to a plain key (PostMessage cannot hold Shift): the script
rewrites [Hotkeys] GSDumpMultiFrame in tools/pcsx2/inis/PCSX2.ini to Keyboard/F7 and restores
the original binding on exit. GSDumpCompression is forced to 0 (uncompressed) for the run.

Usage: python -m tools_py.parity.gsdump_capture --slot 6 --frames 6 [--boot 25]
"""
import argparse
import ctypes
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools_py.parity import keys, winshot  # noqa: E402
from tools_py.parity.pine import Pine  # noqa: E402
from tools_py.parity.cam_poll import pine_port  # noqa: E402
from tools_py.parity.drive import PCSX2, ISO  # noqa: E402
from tools_py.parity import pcsx2_keys  # noqa: E402

INI = os.path.join("tools", "pcsx2", "inis", "PCSX2.ini")
VK_F7 = 0x76


def patch_ini():
    text = open(INI, encoding="utf-8").read()
    orig = text
    text = re.sub(r"^GSDumpMultiFrame = .*$", "GSDumpMultiFrame = Keyboard/F7", text, flags=re.M)
    text = re.sub(r"^GSDumpCompression = .*$", "GSDumpCompression = 0", text, flags=re.M)
    open(INI, "w", encoding="utf-8").write(text)
    return orig


def press_f7(hwnd):
    user32 = ctypes.windll.user32
    scan = user32.MapVirtualKeyW(VK_F7, 0)
    for h in pcsx2_keys.targets(hwnd):
        user32.PostMessageW(h, pcsx2_keys.WM_KEYDOWN, VK_F7, (scan << 16) | 1)
    time.sleep(0.08)
    for h in pcsx2_keys.targets(hwnd):
        user32.PostMessageW(h, pcsx2_keys.WM_KEYUP, VK_F7, (scan << 16) | 0xC0000001)


def newest_dump(dump_dir, after):
    best = None
    for root, _, files in os.walk(dump_dir):
        for f in files:
            p = os.path.join(root, f)
            if os.path.getmtime(p) >= after and (best is None or os.path.getmtime(p) > os.path.getmtime(best)):
                best = p
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=int, default=6)
    ap.add_argument("--frames", type=int, default=6, help="approximate frames to record (60 fps)")
    ap.add_argument("--boot", type=float, default=25.0)
    ap.add_argument("--settle", type=float, default=6.0, help="seconds after the state load before recording")
    a = ap.parse_args()
    orig = patch_ini()
    dump_dir = os.path.abspath(os.path.join("tools", "pcsx2", "snaps"))
    os.makedirs(dump_dir, exist_ok=True)
    t_start = time.time()
    proc = subprocess.Popen([PCSX2, "-batch", "-nogui", "-fastboot", ISO])
    try:
        port = pine_port()
        p = None
        t0 = time.time()
        while p is None and time.time() - t0 < 120:
            try:
                p = Pine(port=port)
            except OSError:
                time.sleep(1.0)
        if p is None:
            raise SystemExit("no PINE")
        time.sleep(a.boot)
        p.load_state(a.slot)
        time.sleep(a.settle)
        hwnd = winshot.find_window(keys.WINDOW_TITLES["pcsx2"])
        if not hwnd:
            raise SystemExit("no PCSX2 window")
        press_f7(hwnd)
        time.sleep(max(0.05, a.frames / 60.0))
        press_f7(hwnd)
        time.sleep(4.0)
        f = newest_dump(dump_dir, t_start)
        print("dump:", f, os.path.getsize(f) if f else None)
    finally:
        proc.kill()
        open(INI, "w", encoding="utf-8").write(orig)


if __name__ == "__main__":
    main()
