"""Sprint 7 Task 1c: one capture of the game at a non-default window size.

    python -m tools_py.parity.scale_shot --size 1280x896 --seconds 40 --out logs/parity/s7_scale_2x.png

Launches the exe with PS2X_WINDOW_SIZE set, waits for its window to appear, lets the title loop
settle for `--seconds`, captures the CLIENT area with winshot.capture_by_title, and kills the tree.
The capture is then scored against the 640x448 gate frame by tools_py.parity.scale_compare.

It rides alongside a gate launch rather than taking a launch of its own (plan Task 1c Step 8), so
it keeps no drive harness and no pad: a title-screen frame is all the comparison needs.

Exit 1 when no window ever appeared -- a capture that silently did not happen would be scored as a
missing file later, far from the cause.
"""
import argparse
import os
import subprocess
import sys
import time

from tools_py.parity import keys, winshot

DEFAULT_EXE = os.path.join("dist", "socom2.exe")
DEFAULT_ELF = os.path.join("game", "disc", "socom2_game.elf")
WINDOW_WAIT_S = 60.0     # how long to wait for the window to appear before giving up


def parse_size(text):
    """'1280x896' -> (1280, 896). Raises ValueError on anything else."""
    parts = text.lower().split("x")
    if len(parts) != 2:
        raise ValueError("size must be <w>x<h>, got %r" % (text,))
    w, h = int(parts[0]), int(parts[1])
    if w <= 0 or h <= 0:
        raise ValueError("size must be positive, got %r" % (text,))
    return w, h


def wait_for_window(title, deadline_s=WINDOW_WAIT_S):
    """Poll for a visible top-level window whose title contains `title`; hwnd, or None on timeout."""
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        hwnd = winshot.find_window(title)
        if hwnd:
            return hwnd
        time.sleep(0.5)
    return None


def kill_exe(exe):
    """Kill the whole tree by image name. Git Bash mangles '/F', so taskkill goes through cmd
    (drive.py:265 learned this the hard way)."""
    subprocess.run(["cmd", "/c", "taskkill /F /IM " + os.path.basename(exe)], capture_output=True)


def shoot(out, size="1280x896", seconds=40, exe=DEFAULT_EXE, elf=DEFAULT_ELF,
          title=keys.WINDOW_TITLES["ours"]):
    """Launch `exe` at `size`, wait `seconds`, capture its client area to `out`; 0 or 1.

    exe and title are parameters, not constants, so this is importable and testable without a
    game: nothing here launches anything until it is called."""
    width, height = parse_size(size)
    out_dir = os.path.dirname(os.path.abspath(out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    env = dict(os.environ, PS2X_WINDOW_SIZE="%dx%d" % (width, height))
    # The frame file is the gate's capture path; this one wants the WINDOW, at its real size, so
    # the readback export must not stand in for PrintWindow here.
    env.pop("PS2X_HOST_SCREENSHOT_LATEST", None)
    proc = subprocess.Popen([exe, elf], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        hwnd = wait_for_window(title)
        if not hwnd:
            print("no window matching '%s' appeared within %gs" % (title, WINDOW_WAIT_S), flush=True)
            return 1
        winshot.keep_on_top(hwnd)
        time.sleep(seconds)
        winshot.capture_by_title(title, out)
        client = winshot.client_size(hwnd)
        print("captured %s client %s" % (out, "%dx%d" % client if client else "?"), flush=True)
        return 0
    finally:
        if proc.poll() is None:
            proc.kill()
        kill_exe(exe)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--size", default="1280x896", help="client size as <w>x<h> (PS2X_WINDOW_SIZE)")
    ap.add_argument("--seconds", type=int, default=40, help="settle time before the capture")
    ap.add_argument("--out", required=True, help="PNG to write")
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--elf", default=DEFAULT_ELF)
    ap.add_argument("--title", default=keys.WINDOW_TITLES["ours"])
    a = ap.parse_args(argv)
    return shoot(a.out, a.size, a.seconds, a.exe, a.elf, a.title)


if __name__ == "__main__":
    sys.exit(main())
