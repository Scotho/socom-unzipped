"""Two PCSX2 SOCOM II clients on the local Horizon stack: A hosts a game, B joins it, both go
READY, and the run captures both windows while the match launches.

Instances: tools/pcsx2 (PINE 28011) and tools/pcsx2_b (PINE 28012, a robocopy of the first with
its own inis/memcards/sstates). Both start from savestate 9 (LOGIN TO SOCOM II ONLINE). See
online_login.py for the per-screen flow and the on-screen keyboard model.

Usage: python -m tools_py.parity.online_match [--hold 120] [--out logs/parity/online/match]
"""
import argparse
import os
import subprocess
import threading
import time

from . import drive, keys, winshot
from .online_login import osk_type

ISO = drive.ISO
# state: the instance's own savestate of the LOGIN TO SOCOM II ONLINE screen (a state copied from
# another install re-probes the memory card on load and loses the network configuration).
# persona_row: rows below the first entry of the persona list where <New Persona> sits (B's card
# already holds A's "socom" persona).
INSTANCES = {
    "A": {"exe": os.path.abspath("tools/pcsx2/pcsx2-qt.exe"), "name": "socom", "state": "9", "persona_row": 0},
    "B": {"exe": os.path.abspath("tools/pcsx2_b/pcsx2-qt.exe"), "name": "socomb", "state": "5", "persona_row": 1},
}


class Client:
    def __init__(self, tag, out):
        self.tag = tag
        self.exe = INSTANCES[tag]["exe"]
        self.name = INSTANCES[tag]["name"]
        self.state = INSTANCES[tag]["state"]
        self.persona_row = INSTANCES[tag]["persona_row"]
        self.out = out
        self.proc = None
        self.hwnd = None
        self.n = 0

    def launch(self):
        self.proc = subprocess.Popen([self.exe, "-batch", "-nogui", "-fastboot", "-state", self.state, ISO],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.time()
        while self.hwnd is None and time.time() - t0 < 90:
            self.hwnd = winshot.find_window(keys.WINDOW_TITLES["pcsx2"], pid=self.proc.pid)
            time.sleep(1)
        if self.hwnd is None:
            raise RuntimeError(f"{self.tag}: no window")
        time.sleep(12)

    def shot(self, label):
        self.n += 1
        winshot.capture(self.hwnd).save(os.path.join(self.out, f"{self.tag}_{self.n:02d}_{label}.png"))

    def press(self, b, wait=1.0):
        keys.press(self.hwnd, b, "pcsx2")
        time.sleep(wait)

    def login(self):
        """LOGIN screen -> universe -> persona (new) -> account login -> EULA -> lobby."""
        self.press("cross", 40); self.shot("universe")
        self.press("cross", 30); self.shot("persona")
        if self.persona_row:
            # a saved persona is pre-filled and the cursor sits on PASSWORD: go back up to the name
            self.press("up", 1)
        self.press("cross", 4)                       # persona list
        for _ in range(self.persona_row):
            self.press("down", 1)
        self.press("cross", 4)                       # <New Persona> -> name keyboard
        osk_type(self.hwnd, self.name); time.sleep(3); self.shot("name")
        self.press("down", 1); self.press("cross", 4)
        osk_type(self.hwnd, self.name); time.sleep(3); self.shot("password")
        for _ in range(4):
            self.press("down", 0.8)
        self.press("cross", 5); self.shot("write_down")
        self.press("cross", 4)                       # CONTINUE
        self.press("cross", 4)                       # save to card: YES
        self.press("cross", 4)                       # slot 1
        self.press("left", 0.8); self.press("cross", 30); self.shot("eula")
        self.press("cross", 20); self.shot("lobby")  # ACCEPT EULA -> lobby (server news popup)
        self.press("cross", 3)                       # close server news
        self.press("down", 1.5); self.press("cross", 8); self.shot("rooms")
        self.press("cross", 15); self.shot("briefing_room")   # join Channel 1

    def host_game(self):
        self.press("up", 1.5); self.press("cross", 5)          # CREATE GAME
        self.press("cross", 4); osk_type(self.hwnd, "test"); time.sleep(3)
        self.press("up", 2); self.press("cross", 5)            # CHOOSE GAMES
        self.press("cross", 3); self.press("square", 4)        # Medley, ACCEPT PLAY LIST
        self.press("square", 25); self.shot("game_lobby")      # CREATE GAME
        self.press("cross", 3); self.shot("game_lobby_ok")     # CONTINUE on the 30 s notice

    def join_game(self):
        self.press("cross", 8); self.shot("games_list")        # JOIN GAME activates the list
        self.press("cross", 25); self.shot("game_lobby")       # first game
        self.press("cross", 3); self.shot("game_lobby_ok")     # CONTINUE
        self.press("down", 1); self.press("cross", 4); self.shot("switched")   # SWITCH TEAMS

    def ready(self):
        # menu: ARMORY, SWITCH TEAMS, READY
        self.press("down", 1); self.press("down", 1); self.press("cross", 3); self.shot("ready")

    def kill(self):
        if self.proc:
            self.proc.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=int, default=120)
    ap.add_argument("--out", default="logs/parity/online/match")
    ap.add_argument("--only", default="", help="A or B: run one client's login only (setup check)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.only:
        c = Client(a.only, a.out)
        try:
            c.launch(); c.login(); c.shot("done")
        finally:
            c.kill()
        return
    A, B = Client("A", a.out), Client("B", a.out)
    try:
        A.launch(); B.launch()
        tA = threading.Thread(target=A.login); tB = threading.Thread(target=B.login)
        tA.start(); time.sleep(5); tB.start(); tA.join(); tB.join()
        A.host_game()
        B.join_game()
        time.sleep(35)                                          # READY becomes available
        A.ready(); B.ready()
        for i in range(a.hold // 10):
            time.sleep(10); A.shot(f"hold{i:02d}"); B.shot(f"hold{i:02d}")
    finally:
        A.kill(); B.kill()


if __name__ == "__main__":
    main()
