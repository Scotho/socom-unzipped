"""winshot's Linux half: capture a window, size it, raise it, and inject keys, under X11.

Sprint 8 Goal 1 Task 9. Same public names and same signatures as `winshot` (a test in
tools_py/tests/test_hostplatform.py asserts both by introspection), so a caller that reaches the
module through `hostplatform.shot_module()` needs no branch of its own. `hwnd` keeps its name: on
X11 it is the window id `xdotool` prints.

Two external tools, both of them in the VM's bare X session: `xdotool` (search, geometry, raise,
resize, pid, keydown/keyup) and ImageMagick's `import` (the screen grab). Neither is touched at
import time, so this module imports on the Windows host for the mirror test.

Capture, as on Windows, prefers the runtime's exported frame file (PS2X_HOST_SCREENSHOT_LATEST or
a per-window registration): it is the same GL readback on both platforms, so the gate's detectors
read identical pixels, and it is immune to a window overlapping ours.
"""
import os
import re
import subprocess
import tempfile
import time

from PIL import Image

# Names this module adds on top of winshot's surface: the Linux twin of keys.press.
KEY_INJECTION_NAMES = ("press", "vk_to_xdotool")

# socom2_host_input.cpp's keyboard map (arrows/WASD/IJKL, Enter=START, Backspace=SELECT,
# ZXCV=Square/Cross/Circle/Triangle, QE=L1/R1, 13=L2/R2, 24=L3/R3) and PCSX2's [Pad1] bindings,
# as keys.py's MAPS hold them: Windows VK code -> X keysym name for `xdotool keydown/keyup`.
# Letters are lowercase keysyms: xdotool would press shift for "A", and the game reads the
# physical key. Arrows are the extended keys winshot flags with (1 << 24).
_VK_TO_XDOTOOL = {
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x0D: "Return", 0x08: "BackSpace", 0x20: "space",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
}
_VK_TO_XDOTOOL.update({0x41 + i: chr(ord("a") + i) for i in range(26)})   # VK_A..VK_Z


def vk_to_xdotool(vk):
    """The X keysym name for a harness VK code. KeyError for anything the harness does not bind:
    a silent miss would press nothing and the drive would blame the game."""
    return _VK_TO_XDOTOOL[vk]


def _run(argv, check=False):
    return subprocess.run(argv, capture_output=True, text=True, check=check)


def _out(argv):
    """stdout of an xdotool call, or None when it fails (no window, no X, no xdotool)."""
    try:
        p = _run(argv)
    except OSError:
        return None
    return p.stdout if p.returncode == 0 else None


def window_pid(hwnd):
    out = _out(["xdotool", "getwindowpid", str(hwnd)])
    return int(out.strip()) if out and out.strip().isdigit() else 0


def find_window(title_substring, pid=None):
    """First visible top-level window whose title contains the substring; `pid` restricts the
    search to one process (two instances share a title)."""
    out = _out(["xdotool", "search", "--onlyvisible", "--name", "(?i)" + re.escape(title_substring)])
    for line in (out or "").split():
        if not line.strip().isdigit():
            continue
        hwnd = int(line.strip())
        if pid is None or window_pid(hwnd) == pid:
            return hwnd
    return None


def window_title(hwnd):
    out = _out(["xdotool", "getwindowname", str(hwnd)])
    return (out or "").strip()


_frame_files = {}   # hwnd -> frame file (per instance; see register_frame_file)


def register_frame_file(hwnd, path):
    """Route grab(hwnd) to the exe instance's own frame file (two instances, two files)."""
    _frame_files[hwnd] = path


class ClientRectError(RuntimeError):
    """The window's client area is not the game's 640x448 at a capture: every fixed-box detector
    would read garbage, so the drive fails loudly instead of scoring a stretched frame."""


def _geometry(hwnd):
    out = _out(["xdotool", "getwindowgeometry", "--shell", str(hwnd)])
    if not out:
        return None
    d = dict(kv.split("=", 1) for kv in out.split() if "=" in kv)
    try:
        return int(d["WIDTH"]), int(d["HEIGHT"])
    except (KeyError, ValueError):
        return None


def client_size(hwnd):
    """(width, height) of the window, or None for a handle that is not a window (tests attach
    shells to fake handles). X11 has no separate client rect: the game window is undecorated
    content, so the geometry IS the client area."""
    if not hwnd:
        return None
    return _geometry(hwnd)


class StaleFrameError(RuntimeError):
    """The exe's frame file is older than the caller allows: the renderer stopped writing it (a
    hung or closed instance), so a capture would be a picture of the past."""

    def __init__(self, path, age, max_age):
        super().__init__(f"frame file {path} is {age:.1f}s old (max {max_age:g}s)")
        self.path, self.age, self.max_age = path, age, max_age


FRAME_RETRY_S = 3.0      # how long grab() waits for a readable (and, with max_age, fresh) frame file


def grab(hwnd, max_age=None):
    """The harness's capture: the exe's own frame file when one is registered for the window or
    PS2X_HOST_SCREENSHOT_LATEST is set, else an X capture of the window. Same contract, same
    retries and the same StaleFrameError as winshot.grab."""
    path = _frame_files.get(hwnd) or os.environ.get("PS2X_HOST_SCREENSHOT_LATEST")
    if not path:
        return capture(hwnd)
    deadline = time.time() + FRAME_RETRY_S
    last_err = stale_err = None
    while True:
        try:
            age = time.time() - os.path.getmtime(path)
            if max_age is not None and age > max_age:
                last_err = stale_err = StaleFrameError(path, age, max_age)
            else:
                with open(path, "rb") as fp:
                    im = Image.open(fp)
                    im.load()
                    return im.convert("RGB")
        except Exception as e:  # noqa: BLE001 - mid-rename / not yet written
            last_err = e
        if time.time() >= deadline:
            break
        time.sleep(0.05)
    if stale_err is not None:
        # a transient error on a later retry (mid-rename) does not un-stale the frame file
        raise stale_err
    raise RuntimeError(f"no frame file at {path}: {last_err}")


def ensure_client_size(hwnd, width=640, height=448):
    """Restore the window to width x height; True when it had to. The runtime exports the frame at
    the window size, so a window resized between launches makes every fixed-box detector read
    garbage (s6_ladder10/11)."""
    if not hwnd:
        return False
    size = _geometry(hwnd)
    if size is None or size == (width, height):
        return False
    _run(["xdotool", "windowsize", str(hwnd), str(width), str(height)])
    return True


def keep_on_top(hwnd):
    """Raise the window above the others. Best effort: a bare X session with no window manager has
    no _NET_WM_STATE_ABOVE, and a raise is all `import` needs to see the real pixels."""
    try:
        _run(["xdotool", "windowraise", str(hwnd)])
    except OSError:
        pass


def capture(hwnd):
    """ImageMagick `import -window <id>`: the live window, no focus change."""
    size = _geometry(hwnd)
    if size and (size[0] <= 0 or size[1] <= 0):
        raise RuntimeError("window has an empty client area (minimised?)")
    fd, png = tempfile.mkstemp(suffix=".png", prefix="x11shot_")
    os.close(fd)
    try:
        p = _run(["import", "-window", str(hwnd), png])
        if p.returncode != 0 or not os.path.getsize(png):
            raise RuntimeError(f"import -window {hwnd} failed: {p.stderr.strip()}")
        with open(png, "rb") as fp:
            im = Image.open(fp)
            im.load()
            return im.convert("RGB")
    finally:
        try:
            os.remove(png)
        except OSError:
            pass


def capture_by_title(title_substring, path):
    hwnd = find_window(title_substring)
    if not hwnd:
        raise RuntimeError(f"no window matching '{title_substring}'")
    capture(hwnd).save(path)
    return path


def press(main_hwnd, button, target, hold_s=0.15, run=None):
    """keys.press's Linux twin: `xdotool keydown/keyup --window <id>` sends to the window without
    taking focus, as PostMessage does on Windows. `run` is injectable so the mapping is tested
    without an X server."""
    from tools_py.parity import keys
    send = run or _run
    key = vk_to_xdotool(keys.MAPS[target][button.upper()])
    send(["xdotool", "keydown", "--window", str(main_hwnd), key])
    time.sleep(hold_s)
    send(["xdotool", "keyup", "--window", str(main_hwnd), key])
