"""Sprint 7 Task 1c: one screen of the game, captured at 640x448 and at 1280x896, from the runtime.

    python -m tools_py.parity.scale_shot --both --seconds 40 --out logs/parity/s7_scale

Launches the exe with PS2X_WINDOW_SIZE set and reads the frame the runtime *exports*
(PS2X_HOST_SCREENSHOT_LATEST: a GL readback of the framebuffer, written every ~150 ms as
<path>.tmp.png and renamed onto <path>). The export is taken before the debug UI draws
(ps2_runtime.cpp:2762-2782, the block above the m_debugUiDrawCallback call), so the exported frame
carries no debugger overlay -- unlike a window capture -- and it is a readback of the whole
framebuffer (raylib LoadImageFromScreen), so it follows the window: 1280x896 in, 1280x896 out.

Why the rewrite (2026-09-17): Step 8's first comparison failed for a reason that had nothing to do
with scaling. The 2x shot was this tool's *own* launch photographed through the window 40 s in --
the "analog controller not detected" prompt with the runtime debugger drawn over it -- while the 1x
side was a menu the gate's drive had pressed its way to. Two different screens score like a moved
vertex. The comparison has to be the SAME screen at both sizes, from the same procedure, read from
the export. --both does exactly that: the same `seconds` of the same deterministic boot at each
size, one launch at a time. The controller prompt is a fine subject -- it is a real rendered screen
with text on it.

mode="window" keeps the old PrintWindow path for the cases that genuinely want the window.

Exit 1 when no window ever appeared -- a capture that silently did not happen would be scored as a
missing file later, far from the cause -- or, for --both, when the mean |diff| misses the bar.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

from tools_py.parity import keys, scale_compare, winshot

DEFAULT_EXE = os.path.join("dist", "socom2.exe")
DEFAULT_ELF = os.path.join("game", "disc", "socom2_game.elf")
WINDOW_WAIT_S = 60.0     # how long to wait for the window to appear before giving up
FRAME_WAIT_S = 10.0      # how long to keep trying for a readable exported frame after the wait
SCALE_BAR = 3.0          # spec Goal 1c: mean |grey diff| below this is "a presentation scale"


def parse_size(text):
    """'1280x896' -> (1280, 896). Raises ValueError on anything else."""
    parts = text.lower().split("x")
    if len(parts) != 2:
        raise ValueError("size must be <w>x<h>, got %r" % (text,))
    w, h = int(parts[0]), int(parts[1])
    if w <= 0 or h <= 0:
        raise ValueError("size must be positive, got %r" % (text,))
    return w, h


def child_env(size, latest=None, base=None):
    """The environment the launched exe gets. Pure: it launches nothing.

    PS2X_WINDOW_SIZE is always set, to the validated size. PS2X_HOST_SCREENSHOT_LATEST is set to
    `latest` (absolute -- the child's working directory is not ours to assume) in export mode, and
    *removed* when latest is None: in window mode the readback export must not stand in for
    PrintWindow, and an inherited value from a gate run would do exactly that."""
    width, height = parse_size(size)
    env = dict(os.environ if base is None else base)
    env["PS2X_WINDOW_SIZE"] = "%dx%d" % (width, height)
    env.setdefault("PS2X_DEV", "1")   # the exported frame is a Dev knob (Sprint 9 Goal 3)
    if latest:
        env["PS2X_HOST_SCREENSHOT_LATEST"] = os.path.abspath(latest)
    else:
        env.pop("PS2X_HOST_SCREENSHOT_LATEST", None)
    return env


def newest_frame(latest_path):
    """The exported frame to copy: the newest *final* .png beside `latest_path`, or None.

    The runtime writes <path>.tmp.png and renames it onto <path>, so the .tmp.png is excluded by
    name -- it is the frame still being written, and a copy of it is a torn picture. The rest of
    the directory is scanned by mtime rather than trusting the one name, so a run that also left
    older frames there still yields the latest one."""
    directory = os.path.dirname(os.path.abspath(latest_path)) or "."
    if not os.path.isdir(directory):
        return None
    names = [n for n in os.listdir(directory)
             if n.lower().endswith(".png") and not n.lower().endswith(".tmp.png")]
    paths = [p for p in (os.path.join(directory, n) for n in names) if os.path.isfile(p)]
    if not paths:
        return None
    return max(paths, key=os.path.getmtime)


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


def copy_frame(latest_path, out, wait_s=FRAME_WAIT_S):
    """Copy the newest exported frame to `out`; True on success.

    Retries while the runtime is mid-rename, and re-reads the picked file after the copy to be sure
    it decodes -- a PNG that opens is a whole frame, a truncated one raises and we try again."""
    from PIL import Image
    deadline = time.time() + wait_s
    while True:
        src = newest_frame(latest_path)
        if src:
            try:
                shutil.copyfile(src, out)
                with Image.open(out) as im:
                    im.load()
                return True
            except Exception:       # noqa: BLE001 - mid-rename / half-written; retry
                pass
        if time.time() >= deadline:
            return False
        time.sleep(0.1)


def shoot(out, size="1280x896", seconds=40, exe=DEFAULT_EXE, elf=DEFAULT_ELF,
          title=keys.WINDOW_TITLES["ours"], mode="export"):
    """Launch `exe` at `size`, wait `seconds`, write one frame to `out`; 0 or 1.

    mode="export" (the default) reads the runtime's exported frame -- no overlay, and the frame is
    the framebuffer, so it is the window's size. The wait is counted from the launch, not from the
    window appearing, so two sizes of the same boot land on the same screen.

    mode="window" is the old PrintWindow capture of the client area.

    exe and title are parameters, not constants, so this is importable and testable without a
    game: nothing here launches anything until it is called."""
    if mode not in ("export", "window"):
        raise ValueError("mode must be 'export' or 'window', got %r" % (mode,))
    parse_size(size)                                    # refuse a bad size before launching
    out = os.path.abspath(out)
    out_dir = os.path.dirname(out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix="scale_shot_")    # this run's own export dir, so "newest" is ours
    latest = os.path.join(tmp_dir, "latest_frame.png") if mode == "export" else None
    env = child_env(size, latest)
    started = time.time()
    proc = subprocess.Popen([exe, elf], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        hwnd = wait_for_window(title)
        if not hwnd:
            print("no window matching '%s' appeared within %gs" % (title, WINDOW_WAIT_S), flush=True)
            return 1
        if mode == "window":
            winshot.keep_on_top(hwnd)
            time.sleep(seconds)
            winshot.capture_by_title(title, out)
        else:
            remaining = started + seconds - time.time()
            if remaining > 0:
                time.sleep(remaining)
            if not copy_frame(latest, out):
                print("no exported frame at %s after %gs -- is PS2X_HOST_SCREENSHOT_LATEST honoured?"
                      % (latest, FRAME_WAIT_S), flush=True)
                return 1
        client = winshot.client_size(hwnd)
        print("captured %s (%s mode) client %s" % (out, mode, "%dx%d" % client if client else "?"),
              flush=True)
        return 0
    finally:
        if proc.poll() is None:
            proc.kill()
        kill_exe(exe)
        try:
            proc.wait(timeout=15)      # the next size must not race a dying window
        except Exception:              # noqa: BLE001
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)


def both(out, seconds=40, exe=DEFAULT_EXE, elf=DEFAULT_ELF,
         title=keys.WINDOW_TITLES["ours"], mode="export", bar=SCALE_BAR):
    """640x448 then 1280x896, one launch at a time, then score the pair; 0 when it clears `bar`.

    The same `seconds` for both, so the deterministic boot is at the same screen in each -- which is
    the whole point: the 2026-09-17 comparison failed on two different screens, not on geometry."""
    base = out[:-4] if out.lower().endswith(".png") else out
    one, two = base + "_1x.png", base + "_2x.png"
    for path, size in ((one, "640x448"), (two, "1280x896")):
        rc = shoot(path, size, seconds, exe, elf, title, mode)
        if rc:
            print("capture at %s failed; no comparison" % size, flush=True)
            return rc
    diff = scale_compare.mean_abs_diff(two, one, 2)
    print("mean_abs_diff(2x, 1x, 2) = %.4f (bar %.1f)" % (diff, bar), flush=True)
    return 0 if diff < bar else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--size", default="1280x896", help="client size as <w>x<h> (PS2X_WINDOW_SIZE)")
    ap.add_argument("--seconds", type=int, default=40, help="settle time before the capture")
    ap.add_argument("--out", required=True,
                    help="PNG to write; with --both, the stem for <out>_1x.png and <out>_2x.png")
    ap.add_argument("--both", action="store_true",
                    help="capture 640x448 then 1280x896 back to back and score the pair")
    ap.add_argument("--mode", default="export", choices=("export", "window"),
                    help="export: the runtime's frame file (no overlay); window: PrintWindow")
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--elf", default=DEFAULT_ELF)
    ap.add_argument("--title", default=keys.WINDOW_TITLES["ours"])
    a = ap.parse_args(argv)
    if a.both:
        return both(a.out, a.seconds, a.exe, a.elf, a.title, a.mode)
    return shoot(a.out, a.size, a.seconds, a.exe, a.elf, a.title, a.mode)


if __name__ == "__main__":
    sys.exit(main())
