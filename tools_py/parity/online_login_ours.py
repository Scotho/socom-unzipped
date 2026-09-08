"""Drive OUR exe from boot through ONLINE -> LOGIN -> universe -> persona/password (on-screen
keyboard) -> CONNECT -> EULA -> lobby -> briefing room -> CREATE GAME against the local Horizon
stack, mirroring online_login.py / online_match.py (the PCSX2 reference). Every screen transition
is detected against scripts/parity/refs/*.png (our own captures, or the PCSX2 golden screens for
screens we had not reached yet) instead of fixed waits: the shell eats presses that land during
a transition, and the transitions' durations vary run to run.

Usage: python -m tools_py.parity.online_login_ours [--existing] [--name socomc] [--password socom]
       [--out logs/parity/ours_host] [--seconds 500] [--host] [--then cross:3,...] [--hold 30]
"""
import argparse
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
OSK_ACCENT_BOX = (20, 396, 96, 428)   # accent-toggle key: "aei" with accents in normal mode, "abc" in accent mode


class Shell:
    def __init__(self, hwnd, out, t0):
        self.hwnd, self.out, self.t0 = hwnd, out, t0
        # Title-crop references (scripts/parity/refs/refs.json: crop box at 320x224 + threshold on
        # the mean absolute grey difference); the main menu is matched on the whole frame instead.
        import json
        self.meta = json.load(open(os.path.join(REFS, "refs.json")))
        self.refs = {n: np.asarray(Image.open(os.path.join(REFS, n + ".png")).convert("L"), dtype=float) for n in self.meta}
        self.menu = Image.open(os.path.join(REFS, "main_menu.png"))

    def log(self, m):
        print(f"{time.time() - self.t0:6.1f}s {m}", flush=True)

    def shot(self, label):
        winshot.capture(self.hwnd).save(os.path.join(self.out, f"{label}.png"))

    def press(self, b, wait=1.0):
        keys.press(self.hwnd, b, T)
        time.sleep(wait)

    def diff(self, name, im=None):
        im = (im or winshot.capture(self.hwnd)).convert("L").resize((320, 224)).crop(tuple(self.meta[name]["box"]))
        return float(abs(np.asarray(im, dtype=float) - self.refs[name]).mean())

    def is_screen(self, name, thresh=None):
        if name == "main_menu":
            return score(self.menu, winshot.capture(self.hwnd))["score"] >= (thresh or 90.0)
        return self.diff(name) <= (thresh or self.meta[name]["thresh"])

    def wait_for(self, name, timeout, thresh=None):
        t = time.time()
        while time.time() - t < timeout:
            if self.is_screen(name, thresh):
                self.log(f"screen {name} after {time.time() - t:.1f}s (diff {self.diff(name):.1f})" if name != "main_menu" else f"screen {name}")
                return True
            time.sleep(0.5)
        self.log(f"TIMEOUT waiting for {name}")
        self.shot(f"timeout_{name}")
        return False

    def press_until_gone(self, b, name, tries=8, wait=3.0, thresh=None):
        for i in range(tries):
            if not self.is_screen(name, thresh):
                self.log(f"{name} gone after {i} {b}")
                return True
            self.press(b, wait)
        return False

    def osk_normal_mode(self):
        crop = lambda im: np.asarray(im.crop(OSK_ACCENT_BOX).convert("L"), dtype=float)
        normal = np.asarray(Image.open(os.path.join("scripts", "parity", "ref_osk_normal.png")).convert("L"), dtype=float)
        accent = np.asarray(Image.open(os.path.join("scripts", "parity", "ref_osk_accent.png")).convert("L"), dtype=float)
        cur = crop(winshot.capture(self.hwnd))
        if abs(cur - accent).mean() < abs(cur - normal).mean():
            self.log("keyboard in accent mode -> toggling")
            self.press("cross", 0.8)

    def type(self, text, shots=None, tag=""):
        self.osk_normal_mode()
        osk_type(self.hwnd, text, shots, tag, target=T)
        time.sleep(3.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="socomc")
    ap.add_argument("--password", default="socom")
    ap.add_argument("--out", default="logs/parity/ours_host")
    ap.add_argument("--seconds", type=int, default=500)
    ap.add_argument("--hold", type=int, default=30)
    ap.add_argument("--existing", action="store_true", help="the persona is already on the memory card")
    ap.add_argument("--host", action="store_true", help="after the briefing room: CREATE GAME (Medley)")
    ap.add_argument("--then", default="", help="extra presses after the lobby, e.g. cross:3,type:test")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower().count("socom2.exe"):
        raise SystemExit("socom2.exe is already running; refusing to start a second game instance")
    proc = drive.launch(T, a.seconds)
    t0 = time.time()
    hwnd = None
    while hwnd is None and time.time() - t0 < 60:
        hwnd = winshot.find_window(keys.WINDOW_TITLES[T])
        time.sleep(0.5)
    if hwnd is None:
        proc.terminate()
        raise SystemExit("game window not found")
    last = None
    while last is None and time.time() - t0 < 60:
        try:
            last = drive.frame(hwnd)
        except RuntimeError:
            time.sleep(0.5)
    sh = Shell(hwnd, a.out, t0)
    try:
        # Boot: CROSS through the boot screens until the main menu (five or six presses).
        for i in range(9):
            drive.wait_stable(hwnd, 1.5, 40.0, changed_from=last)
            time.sleep(1.0)
            if sh.is_screen("main_menu", 90.0):
                sh.log(f"main menu after {i} presses")
                break
            last = drive.frame(hwnd)
            sh.press("cross")
            sh.log(f"boot press {i}")
            for _ in range(12):
                time.sleep(1.0)
                if sh.is_screen("main_menu", 90.0):
                    break
        else:
            raise SystemExit("main menu not reached")
        time.sleep(3.0)
        sh.press("down", 1.5)
        sh.press("cross", 3.0)                                   # ONLINE
        sh.wait_for("login", 40)
        sh.shot("00_login")
        sh.press_until_gone("cross", "login")                    # LOGIN
        sh.wait_for("universe", 60)
        sh.shot("01_universe")
        sh.press_until_gone("cross", "universe")                 # connect to the universe
        sh.wait_for("persona", 60)
        sh.shot("02_persona")
        sh.press("cross", 4.0)                                   # persona list
        if a.existing:
            sh.press("cross", 4.0)                               # saved persona -> password keyboard opens
            sh.shot("03_name")
            sh.shot("04_pw_kbd")
        else:
            sh.press("cross", 4.0)                               # <New Persona> -> name keyboard
            sh.type(a.name, a.out, "name")
            sh.shot("03_name")
            sh.press("down", 1.0)
            sh.press("cross", 4.0)
            sh.shot("04_pw_kbd")
        sh.type(a.password)
        sh.shot("05_password")
        for _ in range(4):                                       # SAVE PASSWORD, HOMETOWN, GENDER, CONNECT
            sh.press("down", 0.8)
        sh.shot("06_connect_focus")
        sh.press("cross", 5.0)
        sh.shot("07_after_connect")
        # Prompts between CONNECT and the EULA vary (write-down notice, save to card?, slot,
        # overwrite?): answer whichever is on screen until the EULA shows.
        t = time.time(); seen = set(); quiet = 0
        while time.time() - t < 120 and not sh.is_screen("eula"):
            for name, presses in (("write_down", ["cross"]), ("save_card", ["cross"]), ("card_slot", ["cross"])):
                if sh.is_screen(name):
                    sh.log(f"prompt {name}"); sh.shot(f"07_{name}"); seen.add(name); quiet = 0
                    for b in presses:
                        sh.press(b, 3.0)
                    break
            else:
                quiet += 1
                if "card_slot" in seen and quiet == 8:          # an unrecognised prompt (overwrite?): YES
                    sh.log("unrecognised prompt after the slot -> LEFT, CROSS"); sh.shot("07_unknown_prompt")
                    sh.press("left", 0.8); sh.press("cross", 3.0); quiet = 0
                time.sleep(1.0)
        sh.wait_for("eula", 30)
        sh.shot("08_eula")
        sh.press_until_gone("cross", "eula")                     # ACCEPT
        sh.wait_for("lobby_news", 60)
        sh.shot("09_lobby")
        sh.press_until_gone("cross", "lobby_news")               # close SERVER NEWS
        time.sleep(2.0)
        sh.shot("09_lobby_no_news")
        if a.host:
            sh.press("down", 2.0)
            sh.press("cross", 3.0)                               # BRIEFING ROOMS
            sh.wait_for("rooms", 30)
            sh.shot("10_rooms")
            sh.press_until_gone("cross", "rooms", wait=5.0)      # join Channel 1
            sh.wait_for("briefing_room", 40)
            sh.shot("11_briefing_room")
            sh.press("up", 2.0)
            sh.press("cross", 6.0)                               # CREATE GAME
            sh.shot("12_create_game")
            sh.press("cross", 5.0)                               # game name keyboard
            sh.type("test")
            sh.shot("13_game_name")
            sh.press("up", 2.5)
            sh.press("cross", 6.0)                               # CHOOSE GAMES
            sh.shot("14_choose_games")
            sh.press("cross", 4.0)                               # Medley
            sh.press("square", 5.0)                              # ACCEPT PLAY LIST
            sh.shot("15_play_list")
            sh.press("square", 25.0)                             # CREATE GAME (DME world)
            sh.shot("16_game_lobby")
            sh.press("cross", 4.0)                               # CONTINUE on the 30 s notice
            sh.shot("17_game_lobby_ok")
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
