"""Capture the game's window at a fixed rate for a while -- the instrument for an animation the step-by-step
captures cannot see (Sprint 9 Q0b: the blue arrow that flies over the first mission's opening to mark the first
enemies; drive.py samples every 8 s, and the arrow lives between samples).

    python -m tools_py.parity.frame_burst <pcsx2|ours> <out_dir> <start_after_s> <count> <interval_s>

Waits for the target's window, then sleeps `start_after_s` from its own start, then writes count PNGs
`burst_NNNN_<t>.png` (t = seconds since the burst began) at `interval_s`. Runs beside drive.py; touches nothing
but the screen. A capture that fails (the window mid-resize) is skipped, not fatal.
"""
import os
import sys
import time

from tools_py.parity import keys, winshot


def main(argv):
    if len(argv) != 6:
        print(__doc__.strip().splitlines()[4]); return 2
    target, out, start_after, count, interval = argv[1], argv[2], float(argv[3]), int(argv[4]), float(argv[5])
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    hwnd = None
    while time.time() - t0 < 180.0 and not hwnd:
        hwnd = winshot.find_window(keys.WINDOW_TITLES[target])
        if not hwnd:
            time.sleep(1.0)
    if not hwnd:
        print("no window for", target, flush=True); return 1
    remaining = start_after - (time.time() - t0)
    if remaining > 0:
        time.sleep(remaining)
    burst0 = time.time()
    written = 0
    for i in range(count):
        t = time.time() - burst0
        path = os.path.join(out, f"burst_{i:04d}_{t:06.2f}.png")
        try:
            hwnd = winshot.find_window(keys.WINDOW_TITLES[target]) or hwnd
            winshot.capture(hwnd).save(path)
            written += 1
        except Exception as e:  # noqa: BLE001 -- a missed frame is a missed frame, the burst goes on
            print(f"frame {i}: {e}", flush=True)
        due = burst0 + (i + 1) * interval
        while time.time() < due:
            time.sleep(0.01)
    print(f"burst: {written}/{count} frames at {interval}s into {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
