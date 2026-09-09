"""Drive OUR exe from boot through ONLINE -> LOGIN -> universe -> persona/password (on-screen
keyboard) -> CONNECT -> EULA -> lobby -> briefing room -> CREATE GAME / JOIN GAME against the local
Horizon stack, mirroring online_login.py / online_match.py (the PCSX2 reference). Every screen
transition is detected against title crops in scripts/parity/refs (refs.json) instead of fixed
waits: the shell eats presses that land during a transition, and transition times vary per run.

Usage: python -m tools_py.parity.online_login_ours [--existing] [--name socomc] [--password socom]
       [--out logs/parity/ours_host] [--seconds 500] [--host] [--then cross:3,...] [--hold 30]
       [--instance B]   (second exe instance: own window title, memory card dir and UDP ports)
"""
import argparse
import json
import os
import subprocess
import time

import numpy as np
from PIL import Image

from . import drive, keys, winshot
from .compare import score
from .online_login import osk_type

T = "ours"
REFS = os.path.join("scripts", "parity", "refs")
OSK_ACCENT_BOX = (20, 396, 96, 428)   # accent-toggle key: accented "aei" in normal mode, "abc" in accent mode

# Per-instance environment: window title tag (the harness finds windows by title substring),
# memory-card directory and the UDP port shift (two clients on one host must not both bind the
# game's fixed 3658/3659, like PCSX2 client B's 0F6FC6CF.clientB.pnach).
INSTANCES = {
    "A": {"PS2X_WINDOW_TITLE": "SOCOM-A"},
    "B": {"PS2X_WINDOW_TITLE": "SOCOM-B", "PS2X_MC_DIR": os.path.abspath("game/disc/mc0_b"), "PS2X_SOCOM2_UDP_SHIFT": "2"},
}


def launch(seconds, instance=None):
    """Start the exe; returns (proc, title substring to find its window)."""
    env = dict(os.environ, PS2X_SOCOM2_PAD="1")
    title = keys.WINDOW_TITLES[T]
    latest = os.path.abspath(os.path.join("logs", "parity", f"latest_frame_{instance or 'A'}.png"))
    env["PS2X_HOST_SCREENSHOT_LATEST"] = latest
    if instance:
        env.update(INSTANCES[instance])
        title = INSTANCES[instance]["PS2X_WINDOW_TITLE"]
        os.makedirs(env.get("PS2X_MC_DIR", "game/disc/mc0"), exist_ok=True)
    proc = subprocess.Popen(["bash", "./run.sh", str(seconds)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.latest_frame = latest
    return proc, title


class Shell:
    def __init__(self, hwnd, out, t0, tag=""):
        self.hwnd, self.out, self.t0, self.tag = hwnd, out, t0, tag
        self.meta = json.load(open(os.path.join(REFS, "refs.json")))
        self.refs = {n: np.asarray(Image.open(os.path.join(REFS, n + ".png")).convert("L"), dtype=float) for n in self.meta}
        self.menu = Image.open(os.path.join(REFS, "main_menu.png"))
        self.last = None

    def log(self, m):
        print(f"{time.time() - self.t0:6.1f}s {self.tag}{m}", flush=True)

    def shot(self, label):
        winshot.grab(self.hwnd).save(os.path.join(self.out, f"{self.tag}{label}.png"))

    def press(self, b, wait=1.0):
        # 0.08 s = 5 frames at the shell's 60 fps: long enough to register, short enough not to
        # trip the UI's held-button repeat (a 0.15 s CROSS closed the SERVER NEWS popup and the
        # repeat reopened it, eight times in a row, 2026-09-09 play4).
        keys.press(self.hwnd, b, T, hold_s=0.08)
        time.sleep(wait)

    def hold(self, b, seconds, wait=0.3):
        """Hold a key (stick directions W/A/S/D, I/J/K/L; R1 fire) for `seconds`."""
        keys.press(self.hwnd, b, T, hold_s=seconds)
        time.sleep(wait)

    def diff(self, name, im=None, arr=None):
        """Normalised, shift-tolerant distance of the screen's reference band: both crops are
        brightness/contrast-normalised (the 2026-09-09 renderer draws the UI a little darker and
        ~8 px left of the references, which put the raw score at 22 against an 8 threshold), and
        the best offset within +-12 px horizontally / +-3 px vertically counts. Correct screens
        score 0.37-0.44, wrong ones 0.45+ (measured on logs/parity/ours_match_play1)."""
        if arr is None:
            full = (im or winshot.grab(self.hwnd)).convert("L").resize((320, 224))
            arr = np.asarray(full, dtype=float)
        x0, y0, x1, y1 = self.meta[name]["box"]
        best = 1e9
        # The prompt notices are also drawn a few percent narrower than the references: try a
        # few horizontal scales of the reference band (0.61 -> 0.44 on the write-down notice).
        for ref in self.ref_scales(name):
            rn = (ref - ref.mean()) / (ref.std() + 1e-6)
            for dy in range(-6, 7):
                for dx in range(-20, 21):
                    ax0, ay0 = x0 + dx, y0 + dy
                    if ax0 < 0 or ay0 < 0 or ax0 + ref.shape[1] > arr.shape[1] or ay0 + ref.shape[0] > arr.shape[0]:
                        continue
                    c = arr[ay0:ay0 + ref.shape[0], ax0:ax0 + ref.shape[1]]
                    if c.std() < 2.0:
                        continue
                    d = float(abs((c - c.mean()) / (c.std() + 1e-6) - rn).mean())
                    if d < best:
                        best = d
        return best

    def ref_scales(self, name):
        if not hasattr(self, "_scaled"):
            self._scaled = {}
        if name not in self._scaled:
            im = Image.open(os.path.join(REFS, name + ".png")).convert("L")
            out = []
            for sc in (0.90, 0.93, 0.96, 1.0, 1.04):
                w = max(4, int(round(im.size[0] * sc)))
                out.append(np.asarray(im.resize((w, im.size[1])), dtype=float))
            self._scaled[name] = out
        return self._scaled[name]

    PROMPT_THRESH = {"write_down": 0.5, "save_card": 0.5, "card_slot": 0.5}

    def is_screen(self, name, thresh=None):
        if name == "main_menu":
            return score(self.menu, winshot.grab(self.hwnd))["score"] >= (thresh or 90.0)
        arr = np.asarray(winshot.grab(self.hwnd).convert("L").resize((320, 224)), dtype=float)
        d = self.diff(name, arr=arr)
        if d > self.PROMPT_THRESH.get(name, 0.45):
            return False
        # Among the references sharing this band, this screen must also be the best match.
        box = tuple(self.meta[name]["box"])
        for other in self.meta:
            if other != name and tuple(self.meta[other]["box"]) == box and self.diff(other, arr=arr) < d:
                return False
        return True

    def wait_for(self, name, timeout, thresh=None):
        t = time.time()
        while time.time() - t < timeout:
            if self.is_screen(name, thresh):
                self.log(f"screen {name} after {time.time() - t:.1f}s")
                return True
            time.sleep(0.5)
        self.log(f"TIMEOUT waiting for {name}")
        self.shot(f"timeout_{name}")
        return False

    def press_until_gone(self, b, name, tries=8, wait=3.0, thresh=None):
        """Press `b` until `name` is no longer on screen. "Gone" needs two checks 0.6 s apart:
        a single frame can miss (a fade or a transient overlay), which skipped the press that
        connects to the universe on instance B (2026-09-09, play4)."""
        for i in range(tries):
            if not self.is_screen(name, thresh):
                time.sleep(0.6)
                if not self.is_screen(name, thresh):
                    self.log(f"{name} gone after {i} {b}")
                    return True
            self.press(b, wait)
        return False

    def osk_normal_mode(self):
        crop = lambda im: np.asarray(im.crop(OSK_ACCENT_BOX).convert("L"), dtype=float)
        normal = np.asarray(Image.open(os.path.join("scripts", "parity", "ref_osk_normal.png")).convert("L"), dtype=float)
        accent = np.asarray(Image.open(os.path.join("scripts", "parity", "ref_osk_accent.png")).convert("L"), dtype=float)
        cur = crop(winshot.grab(self.hwnd))
        if abs(cur - accent).mean() < abs(cur - normal).mean():
            self.log("keyboard in accent mode -> toggling")
            self.press("cross", 0.8)

    def type(self, text, shots=None, tag=""):
        self.osk_normal_mode()
        osk_type(self.hwnd, text, shots, tag, target=T)
        time.sleep(3.0)


def attach(proc, title, out, tag=""):
    """Find the instance's window (by title substring) and wait for its first frame."""
    t0 = time.time()
    hwnd = None
    while hwnd is None and time.time() - t0 < 90:
        hwnd = winshot.find_window(title)
        time.sleep(0.5)
    if hwnd is None:
        proc.terminate()
        raise SystemExit(f"{tag}game window not found")
    winshot.keep_on_top(hwnd)
    if getattr(proc, "latest_frame", None):
        winshot.register_frame_file(hwnd, proc.latest_frame)
    last = None
    while last is None and time.time() - t0 < 60:
        try:
            last = drive.frame(hwnd)
        except RuntimeError:
            time.sleep(0.5)
    sh = Shell(hwnd, out, t0, tag)
    sh.latest_frame = getattr(proc, "latest_frame", None)
    sh.last = last
    return sh


def boot_to_online(sh):
    """CROSS through the boot screens until the main menu (five or six presses), then ONLINE."""
    for i in range(9):
        drive.wait_stable(sh.hwnd, 1.5, 40.0, changed_from=sh.last)
        time.sleep(1.0)
        if sh.is_screen("main_menu", 90.0):
            sh.log(f"main menu after {i} presses")
            break
        sh.last = drive.frame(sh.hwnd)
        sh.press("cross")
        sh.log(f"boot press {i}")
        for _ in range(12):
            time.sleep(1.0)
            if sh.is_screen("main_menu", 90.0):
                break
    else:
        raise SystemExit(f"{sh.tag}main menu not reached")
    time.sleep(3.0)
    sh.press("down", 1.5)
    sh.press("cross", 3.0)                                       # ONLINE
    sh.wait_for("login", 40)
    sh.shot("00_login")


def login(sh, name, password, existing):
    """LOGIN -> universe -> persona -> password -> CONNECT -> prompts -> EULA -> lobby (news closed)."""
    sh.press_until_gone("cross", "login")                        # LOGIN
    sh.wait_for("universe", 60)
    sh.shot("01_universe")
    sh.press_until_gone("cross", "universe")                     # connect to the universe
    sh.wait_for("persona", 60)
    sh.shot("02_persona")
    sh.press("cross", 4.0)                                       # persona list
    if existing:
        sh.press("cross", 4.0)                                   # saved persona -> password keyboard opens
        sh.shot("03_name")
        sh.shot("04_pw_kbd")
    else:
        sh.press("cross", 4.0)                                   # <New Persona> -> name keyboard
        sh.type(name, sh.out, sh.tag + "name")
        sh.shot("03_name")
        sh.press("down", 1.0)
        sh.press("cross", 4.0)
        sh.shot("04_pw_kbd")
    sh.type(password)
    sh.shot("05_password")
    for _ in range(4):                                           # SAVE PASSWORD, HOMETOWN, GENDER, CONNECT
        sh.press("down", 0.8)
    sh.shot("06_connect_focus")
    sh.press("cross", 5.0)
    sh.shot("07_after_connect")
    # Prompts between CONNECT and the EULA vary (write-down notice, save to card?, slot,
    # overwrite?): answer whichever is on screen until the EULA shows.
    t = time.time()
    seen = set()
    quiet = 0
    while time.time() - t < 120 and not sh.is_screen("eula"):
        for pname in ("write_down", "save_card", "card_slot"):
            if sh.is_screen(pname):
                sh.log(f"prompt {pname}")
                sh.shot(f"07_{pname}")
                seen.add(pname)
                quiet = 0
                sh.press("cross", 3.0)
                break
        else:
            quiet += 1
            if "card_slot" in seen and quiet == 8:               # an unrecognised prompt (overwrite?): YES
                sh.log("unrecognised prompt after the slot -> LEFT, CROSS")
                sh.shot("07_unknown_prompt")
                sh.press("left", 0.8)
                sh.press("cross", 3.0)
                quiet = 0
            time.sleep(1.0)
    sh.wait_for("eula", 30)
    sh.shot("08_eula")
    sh.press_until_gone("cross", "eula")                         # ACCEPT
    sh.wait_for("lobby_news", 60)
    sh.shot("09_lobby")
    sh.press_until_gone("cross", "lobby_news")                   # close SERVER NEWS
    time.sleep(2.0)
    sh.shot("09_lobby_no_news")


def to_briefing_room(sh):
    sh.press("down", 2.0)
    sh.press("cross", 3.0)                                       # BRIEFING ROOMS
    sh.wait_for("rooms", 30)
    sh.shot("10_rooms")
    sh.press_until_gone("cross", "rooms", wait=5.0)              # join Channel 1
    sh.wait_for("briefing_room", 40)
    sh.shot("11_briefing_room")


def host_game(sh, game_name="test"):
    sh.press("up", 2.0)
    sh.press("cross", 6.0)                                       # CREATE GAME
    sh.shot("12_create_game")
    sh.press("cross", 5.0)                                       # game name keyboard
    sh.type(game_name)
    sh.shot("13_game_name")
    sh.press("up", 2.5)
    sh.press("cross", 6.0)                                       # CHOOSE GAMES
    sh.shot("14_choose_games")
    sh.press("cross", 4.0)                                       # Medley
    sh.press("square", 5.0)                                      # ACCEPT PLAY LIST
    sh.shot("15_play_list")
    sh.press("square", 25.0)                                     # CREATE GAME (DME world)
    sh.shot("16_game_lobby")
    sh.press("cross", 4.0)                                       # CONTINUE on the 30 s notice
    sh.shot("17_game_lobby_ok")


def join_game(sh):
    sh.press("cross", 8.0)                                       # JOIN GAME activates the list
    sh.shot("12_games_list")
    sh.press("cross", 25.0)                                      # first game
    sh.shot("16_game_lobby")
    sh.press("cross", 3.0)                                       # CONTINUE
    sh.shot("17_game_lobby_ok")
    sh.press("down", 1.0)
    sh.press("cross", 4.0)                                       # SWITCH TEAMS
    sh.shot("18_switched")


def ready(sh):
    sh.press("down", 1.0)                                        # menu: ARMORY, SWITCH TEAMS, READY
    sh.press("down", 1.0)
    sh.press("cross", 3.0)
    sh.shot("19_ready")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="socomc")
    ap.add_argument("--password", default="socom")
    ap.add_argument("--out", default="logs/parity/ours_host")
    ap.add_argument("--seconds", type=int, default=500)
    ap.add_argument("--hold", type=int, default=30)
    ap.add_argument("--existing", action="store_true", help="the persona is already on the memory card")
    ap.add_argument("--host", action="store_true", help="after the briefing room: CREATE GAME (Medley)")
    ap.add_argument("--instance", default="", help="A or B: window title, memory card dir and UDP ports of that instance")
    ap.add_argument("--then", default="", help="extra presses after the lobby, e.g. cross:3,type:test")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if not a.instance and subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower().count("socom2.exe"):
        raise SystemExit("socom2.exe is already running; refusing to start a second game instance")
    proc, title = launch(a.seconds, a.instance or None)
    try:
        sh = attach(proc, title, a.out)
        boot_to_online(sh)
        login(sh, a.name, a.password, a.existing)
        if a.host:
            to_briefing_room(sh)
            host_game(sh)
        for n, step in enumerate(a.then.split(",") if a.then else []):
            b, w = (step.split(":") + ["2"])[:2]
            if b == "type":
                sh.type(w)
                sh.shot(f"20_then_{n:02d}_typed")
                continue
            sh.press(b, float(w))
            sh.shot(f"20_then_{n:02d}_{b}")
        for i in range(a.hold // 5):
            time.sleep(5)
            sh.shot(f"30_hold_{i:02d}")
        sh.shot("final")
    finally:
        proc.terminate()
        subprocess.run(["taskkill", "/F", "/IM", "socom2.exe"], capture_output=True)


if __name__ == "__main__":
    main()
