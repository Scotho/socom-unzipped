"""Focus-free capture of a top-level window's client area (PrintWindow, PW_RENDERFULLCONTENT)."""
import ctypes
import ctypes.wintypes as wt
from PIL import Image

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
PW_CLIENTONLY = 1
PW_RENDERFULLCONTENT = 2


def window_pid(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def find_window(title_substring, pid=None):
    """First visible top-level window whose title contains the substring; `pid` restricts the
    search to one process (two PCSX2 instances share a title)."""
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and (pid is None or window_pid(hwnd) == pid):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if title_substring.lower() in buf.value.lower():
                    found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def window_title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


class _BMI(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


_frame_files = {}   # hwnd -> frame file (per instance; see register_frame_file)


def register_frame_file(hwnd, path):
    """Route grab(hwnd) to the exe instance's own frame file (two instances, two files)."""
    _frame_files[hwnd] = path


def grab(hwnd):
    """The harness's capture: the exe's own frame file when one is registered for the window or
    PS2X_HOST_SCREENSHOT_LATEST is set (a GL readback the runtime rewrites every ~150 ms — immune
    to windows overlapping ours), else PrintWindow. The file is renamed into place atomically;
    retry while it is being replaced."""
    import os
    import time
    path = _frame_files.get(hwnd) or os.environ.get("PS2X_HOST_SCREENSHOT_LATEST")
    if not path:
        return capture(hwnd)
    deadline = time.time() + 3.0
    last_err = None
    while time.time() < deadline:
        try:
            with open(path, "rb") as fp:
                im = Image.open(fp)
                im.load()
                return im.convert("RGB")
        except Exception as e:  # noqa: BLE001 - mid-rename / not yet written
            last_err = e
            time.sleep(0.05)
    raise RuntimeError(f"no frame file at {path}: {last_err}")


def keep_on_top(hwnd):
    """Pin a window above the others without activating it. PrintWindow hands back a white bitmap
    for a GL window that another window overlaps (DWM keeps no composed copy), and the desktop
    BitBlt fallback then captures the overlapping window instead — a stray Settings window or a
    firewall prompt made every screen 'unstable' for whole runs."""
    HWND_TOPMOST = -1
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)


def capture(hwnd):
    rect = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise RuntimeError("window has an empty client area (minimised?)")
    hdc = user32.GetDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT | PW_CLIENTONLY)
    bmi = _BMI(ctypes.sizeof(_BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    if buf.raw.count(b"\xff") >= len(buf.raw) - w * h:
        # PrintWindow intermittently hands back an all-white bitmap for the GL window (DWM has
        # no composed copy at that instant). Fall back to a desktop BitBlt of the client rect,
        # which is right whenever the window is on top (the drive harness keeps it focused).
        origin = wt.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        sdc = user32.GetDC(None)
        gdi32.BitBlt(mdc, 0, 0, w, h, sdc, origin.x, origin.y, 0x00CC0020)  # SRCCOPY
        user32.ReleaseDC(None, sdc)
        gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1)


def capture_by_title(title_substring, path):
    hwnd = find_window(title_substring)
    if not hwnd:
        raise RuntimeError(f"no window matching '{title_substring}'")
    capture(hwnd).save(path)
    return path
