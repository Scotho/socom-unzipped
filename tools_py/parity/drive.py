#!/usr/bin/env python
"""Drive one side (PCSX2 or our exe) through the shared step script and capture each screen.

Script lines: `<mode>+<delay>:<BTN>[+<BTN>]` with mode `stable` (wait until the frame has been
stable for --settle seconds, at most --maxwait, then wait <delay>), `long` (as `stable` with a
150 s cap, for screens behind a slow cinematic), `next` (first wait for the screen to change
since the previous press, then as `stable`), `idle` (press only if the screen stays unchanged for
<delay> s), `until(x0,y0,x1,y1)` (press until that box is highlighted) or `wait` (just wait <delay>);
BTN `NONE` presses nothing. A screenshot `sNN_<btn>.png` is taken right before each press, and a
`wNN_<k>.png` every second of every wait within step NN (so a fade that never settles is still
captured); `manifest.json` records the step, wall time since launch, stability wait and whether the frame
was stable. Screens on both sides align by step index.

Usage: python -m tools_py.parity.drive --target pcsx2|ours --script <file> --out <dir>
"""
import argparse
import json
import os
import subprocess
import time

import numpy as np
from PIL import Image

from tools_py.parity import keys, winshot

ISO = os.path.abspath("game/SOCOM II - U.S. Navy SEALs (USA).iso")
PCSX2 = os.path.abspath("tools/pcsx2/pcsx2-qt.exe")


def launch(target, seconds):
    if target == "pcsx2":
        return subprocess.Popen([PCSX2, "-batch", "-nogui", "-fastboot", ISO],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # The exe rewrites its current frame to this file; grab() reads it instead of PrintWindow.
    os.environ.setdefault("PS2X_HOST_SCREENSHOT_LATEST", os.path.abspath(os.path.join("logs", "parity", "latest_frame.png")))
    env = dict(os.environ, PS2X_SOCOM2_PAD="1")
    return subprocess.Popen(["bash", "./run.sh", str(seconds)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def parse(text):
    steps = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        head, rest = line.split(":", 1)
        mode, delay = head.split("+", 1)
        buttons = [b.strip().upper() for b in rest.split("+") if b.strip() and b.strip().upper() != "NONE"]
        steps.append((mode, float(delay), buttons))
    return steps


def highlighted(hwnd, box):
    """True when the menu box (x0,y0,x1,y1 in the 640x448 frame) shows the selection tint: SOCOM II's
    briefing highlights an item in green-teal, which lifts G at least 25 above R (normal: <= 16)."""
    im = np.asarray(winshot.grab(hwnd).convert("RGB"), dtype=np.float32)
    x0, y0, x1, y1 = box
    reg = im[y0:y1, x0:x1]
    mean = reg.mean(axis=(0, 1))
    return float(mean[1] - mean[0]) > 25.0


def frame(hwnd):
    return np.asarray(winshot.grab(hwnd).convert("L").resize((160, 112)), dtype=np.float32)


def wait_stable(hwnd, settle, maxwait, thresh=1.0, changed_from=None, change_thresh=0.3,
                on_frame=None):
    """Wait until the frame has been stable for `settle` s (at most `maxwait`). With `changed_from`
    (a reference frame), first wait until the frame differs from it, so a press is only issued on
    a *new* screen (a stable loading screen does not count). `on_frame(elapsed)`, when given, is
    called on every poll (every 0.25 s) with the seconds waited so far, so a caller can record
    what the screen is doing *during* the wait and not only once it settles."""
    t0 = time.time()
    prev = frame(hwnd)
    stable_since = None
    changed = changed_from is None
    while time.time() - t0 < maxwait:
        time.sleep(0.25)
        cur = frame(hwnd)
        if on_frame is not None:
            on_frame(time.time() - t0)
        if not changed:
            if float(np.abs(cur - changed_from).mean()) > change_thresh:
                changed = True
            prev = cur
            continue
        if float(np.abs(cur - prev).mean()) < thresh:
            stable_since = stable_since or time.time()
            if time.time() - stable_since >= settle:
                return True, time.time() - t0
        else:
            stable_since = None
        prev = cur
    return False, time.time() - t0


def wait_capturer(out_dir, hwnd, step, period=1.0):
    """Build an `on_frame` callback for wait_stable that saves a full-resolution capture every
    `period` seconds of the wait as `w<step>_<k>.png`.

    The per-step `s<step>_<btn>.png` captures are of the *settled* screen, so anything that only
    happens while a screen is still changing -- above all the ~1 s fade to black on the way into
    the briefing -- lived entirely inside a settle wait and was captured only when drive.py's
    burst step happened to overlap it (gate.py TRANSITION_MIN_FRAMES). These frames are picked up
    by black_rows.py; the title scorer globs `s[0-9][0-9]_*.png` and so ignores them, and they are
    not recorded in manifest.json (which stays one entry per step).

    Capturing must never take a run down: a failed grab is reported and the wait continues."""
    state = {"k": 0, "next": 0.0, "warned": False}

    def on_frame(elapsed):
        if elapsed < state["next"]:
            return
        try:
            winshot.grab(hwnd).save(os.path.join(out_dir, f"w{step:02d}_{state['k']:03d}.png"))
        except Exception as e:                                  # noqa: BLE001 - diagnostic only
            if not state["warned"]:
                state["warned"] = True
                print(f"w{step:02d}: wait capture failed ({e}); continuing", flush=True)
        else:
            state["k"] += 1
        state["next"] = elapsed + period

    return on_frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=("pcsx2", "ours"), required=True)
    ap.add_argument("--script", default="scripts/parity/launch_to_mission.txt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--settle", type=float, default=1.5)
    ap.add_argument("--maxwait", type=float, default=40.0)
    ap.add_argument("--seconds", type=int, default=400, help="our run length (run.sh)")
    ap.add_argument("--tail", type=float, default=8.0, help="seconds to keep capturing after the last step")
    a = ap.parse_args()
    for exe in ("socom2.exe", "pcsx2-qt.exe"):
        if exe in subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower():
            raise SystemExit(f"{exe} is already running; refusing to start a second game instance")
    os.makedirs(a.out, exist_ok=True)
    steps = parse(open(a.script).read())
    proc = launch(a.target, a.seconds)
    t0 = time.time()
    hwnd = None
    while hwnd is None and time.time() - t0 < 60:
        hwnd = winshot.find_window(keys.WINDOW_TITLES[a.target])
        time.sleep(0.5)
    if hwnd is None:
        proc.terminate()
        raise SystemExit("game window not found")
    winshot.keep_on_top(hwnd)
    manifest = []
    # The window can be found while it is still being created (empty client area); wait it out.
    last = None
    while last is None and time.time() - t0 < 60:
        try:
            last = frame(hwnd)
        except RuntimeError:
            time.sleep(0.5)
            hwnd = winshot.find_window(keys.WINDOW_TITLES[a.target]) or hwnd
    if last is None:
        proc.terminate()
        raise SystemExit("game window never showed a client area")
    try:
        run_steps(a, steps, proc, hwnd, t0, last, manifest)
    finally:
        # Always take the game down, even when a step raises: a stray instance blocks every
        # later drive.py run ("already running"). Git Bash mangles "/F": call taskkill via cmd.
        proc.terminate()
        subprocess.run(["cmd", "/c", "taskkill /F /IM " + ("pcsx2-qt.exe" if a.target == "pcsx2" else "socom2.exe")],
                       capture_output=True)


def run_steps(a, steps, proc, hwnd, t0, last, manifest):
    for i, (mode, delay, buttons) in enumerate(steps):
        stable, waited = (True, 0.0)
        held = "none"
        # One counter per step, shared by every wait the step performs (the until*/ifref modes
        # wait more than once), so the w<step>_<k>.png names never collide.
        cap = wait_capturer(a.out, hwnd, i)
        if mode == "stable":
            stable, waited = wait_stable(hwnd, a.settle, a.maxwait, on_frame=cap)
        elif mode == "long":
            # Like `stable` with a 150 s cap: for a screen reached only after a cinematic whose
            # length depends on the frame rate (our exe plays the location intro at a few fps).
            stable, waited = wait_stable(hwnd, a.settle, 150.0, on_frame=cap)
        elif mode == "next":
            stable, waited = wait_stable(hwnd, a.settle, a.maxwait, changed_from=last, on_frame=cap)
        elif mode.startswith("until("):
            # until(x0,y0,x1,y1)+<delay>:BTN — press BTN every <delay> s (at most 10 times) until the
            # box is highlighted; makes menu navigation independent of how many presses the boot
            # flow consumed (the briefing's typed text and the optional location cinematic vary).
            box = tuple(int(v) for v in mode[6:-1].split(","))
            presses = 0
            while not highlighted(hwnd, box) and presses < 10:
                # The briefing ignores DOWN while its text is typing: press only on a settled screen.
                wait_stable(hwnd, 2.0, 25.0, on_frame=cap)
                for b in buttons:
                    keys.press(hwnd, b, a.target)
                presses += 1
                time.sleep(delay)
            print(f"until{box}: {presses} presses, highlighted={highlighted(hwnd, box)}", flush=True)
            buttons = []
            delay = 0.5
        elif mode.startswith("untilref("):
            # untilref(<png>)+<delay>:BTN — press BTN on each settled screen (at most 12 times)
            # until the top band of the frame (rows 8..62 of the 160x112 thumbnail: the logo /
            # dialog title) matches the reference image; then hold. Makes "reach the main menu"
            # independent of how many boot screens this run happens to show.
            # untilref(<png>,<y0>,<y1>[,<loops>]) compares thumbnail rows y0..y1 instead (e.g. the
            # HUD band 88..112) and loops up to <loops> times (default 12).
            # Full form: untilref(<png>,<y0>,<y1>,<x0>,<x1>,<loops>,<thresh>) on the 160x112 thumbnail.
            parts = mode[9:-1].split(",")
            ref_path = parts[0]
            nums = [float(v) for v in parts[1:]]
            r0, r1 = (int(nums[0]), int(nums[1])) if len(nums) >= 2 else (8, 62)
            c0, c1 = (int(nums[2]), int(nums[3])) if len(nums) >= 4 else (0, 160)
            max_loops = int(nums[4]) if len(nums) >= 5 else 12
            thresh = nums[5] if len(nums) >= 6 else 14.0
            ref_im = np.asarray(Image.open(ref_path).convert("L").resize((160, 112)), dtype=np.float32)

            def at_ref():
                return float(np.abs(frame(hwnd)[r0:r1, c0:c1] - ref_im[r0:r1, c0:c1]).mean()) < thresh

            presses = 0
            while not at_ref() and presses < max_loops:
                wait_stable(hwnd, 1.5, 20.0, on_frame=cap)
                if at_ref():
                    break
                for b in buttons:
                    keys.press(hwnd, b, a.target)
                presses += 1
                time.sleep(delay)
            print(f"untilref({ref_path}): {presses} presses, matched={at_ref()}", flush=True)
            buttons = []
            delay = 0.5
        elif mode.startswith("ifref("):
            # ifref(<png>[,<y0>,<y1>,<x0>,<x1>,<thresh>])+<delay>:BTN — press BTN once, only if the
            # settled screen matches the reference in that thumbnail region; otherwise skip the
            # press. For dialogs the boot flow shows only sometimes (the controller-configuration
            # "save to memory card?" prompt: a blind CROSS answers YES and loops through
            # slot-select / overwrite? / NO; RIGHT+CROSS answers NO and continues).
            parts = mode[6:-1].split(",")
            nums = [float(v) for v in parts[1:]]
            r0, r1 = (int(nums[0]), int(nums[1])) if len(nums) >= 2 else (8, 62)
            c0, c1 = (int(nums[2]), int(nums[3])) if len(nums) >= 4 else (0, 160)
            thresh = nums[4] if len(nums) >= 5 else 14.0
            ref_im = np.asarray(Image.open(parts[0]).convert("L").resize((160, 112)), dtype=np.float32)
            wait_stable(hwnd, 1.5, 20.0, on_frame=cap)
            dist = float(np.abs(frame(hwnd)[r0:r1, c0:c1] - ref_im[r0:r1, c0:c1]).mean())
            matched = dist < thresh
            print(f"ifref({parts[0]}): dist={dist:.1f} matched={matched}", flush=True)
            if not matched:
                buttons = []
        elif mode == "burst":
            # burst+<seconds>:NONE � capture a frame every 0.2 s for <seconds> (transition flashes
            # that a single per-step capture misses), saved as sNN_burst_<k>.png.
            t_b = time.time()
            k = 0
            while time.time() - t_b < delay:
                winshot.grab(hwnd).save(os.path.join(a.out, f"s{i:02d}_burst_{k:03d}.png"))
                k += 1
                time.sleep(0.2)
            delay = 0.0
        elif mode == "hold":
            # hold+<seconds>:BTN � hold the key(s) down for <seconds> (stick directions W/A/S/D,
            # I/J/K/L on ours; fire R1), then capture. For gameplay probes.
            for b in buttons:
                keys.press(hwnd, b, a.target, hold_s=delay)
            held = "+".join(f"hold{b}" for b in buttons)
            buttons = []
            delay = 0.5
        elif mode == "idle":
            # Press only if the screen stays unchanged for <delay> seconds (a menu waiting for
            # input); skip the press when it changes (a movie/loading screen already moving on).
            # Makes the boot sequence robust to a movie that sometimes plays to its end.
            t_idle = time.time()
            ref = frame(hwnd)
            skip = False
            while time.time() - t_idle < delay:
                time.sleep(0.5)
                if float(np.abs(frame(hwnd) - ref).mean()) > 1.0:
                    skip = True
                    break
            if skip:
                buttons = []
            delay = 0.5
        time.sleep(delay)
        label = f"s{i:02d}_{'+'.join(buttons) or (held if mode == 'hold' else 'none')}"
        path = os.path.join(a.out, label + ".png")
        winshot.grab(hwnd).save(path)
        last = frame(hwnd)
        for b in buttons:
            keys.press(hwnd, b, a.target)
        manifest.append({"step": i, "label": label, "t": round(time.time() - t0, 1), "stable": stable,
                         "waited": round(waited, 1), "buttons": buttons})
        print(f"{label:24s} t={time.time()-t0:6.1f}s stable={stable} waited={waited:.1f}s", flush=True)
    time.sleep(a.tail)
    winshot.grab(hwnd).save(os.path.join(a.out, "final.png"))
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
