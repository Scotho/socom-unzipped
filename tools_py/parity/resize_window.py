"""Give the running game window a CLIENT area of <w>x<h>, then exit.

    python -m tools_py.parity.resize_window 1818 1132

Why this exists: the host window is created at 640x448 -- exactly the presented PS2 frame -- so
the present path's aspect-fit scale is 1.0 and `PS2X_PRESENT_FILTER` (linear|integer|point) cannot
change a pixel. Measuring the presentation stretch at all means running at a non-1:1 window, and
this is how Sprint 3 Task 1 got its stretched captures: start the run, run this alongside it, and
the capture files become window-sized.

Caveat, and it is the reason this is a helper and not part of the gate: **the title gate cannot
score a pillarboxed window.** drive.py's `untilref`/`ifref` reference images are 640x448 frames
compared at 160x112, and an aspect-fit frame inside a wider window carries black bars, so no
reference ever matches, every guarded step stalls and the run sits on the controller-configuration
"select memory card slot" dialog. Runs made with this helper are captures to look at, not gate
results. (Teaching drive.py to crop to the non-black rectangle before the 160x112 resize would
lift that; it is a follow-up against drive.py, not something to work around here.)

Waits up to two minutes for the window to appear, then nudges it until GetClientRect matches.
"""
import ctypes
import sys
import time

from tools_py.parity import keys, winshot

# Windows-only tool, importable everywhere (Sprint 8 Goal 1 Task 9): the Linux window manager is
# x11shot's business (winshot.ensure_client_size's twin), and main() below raises off Windows.
if sys.platform == "win32":
    import ctypes.wintypes as wt
    user32 = ctypes.windll.user32
else:
    wt = user32 = None


def resize(hwnd, w, h, tries=10):
    """MoveWindow by the client-area shortfall until GetClientRect is exactly w x h."""
    client = wt.RECT()
    for _ in range(tries):
        user32.GetClientRect(hwnd, ctypes.byref(client))
        cw, ch = client.right - client.left, client.bottom - client.top
        if (cw, ch) == (w, h):
            return True
        outer = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(outer))
        user32.MoveWindow(hwnd, outer.left, outer.top,
                          (outer.right - outer.left) + (w - cw),
                          (outer.bottom - outer.top) + (h - ch), True)
        time.sleep(0.3)
    return False


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2])
        return 2
    w, h = int(argv[1]), int(argv[2])
    deadline = time.time() + 120.0
    while time.time() < deadline:
        hwnd = winshot.find_window(keys.WINDOW_TITLES["ours"])
        if hwnd:
            ok = resize(hwnd, w, h)
            client = wt.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(client))
            print("client %dx%d" % (client.right - client.left, client.bottom - client.top),
                  flush=True)
            return 0 if ok else 1
        time.sleep(0.5)
    print("window never appeared", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
