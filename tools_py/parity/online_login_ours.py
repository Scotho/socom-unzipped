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
from .online_login import OSK_START, osk_moves, osk_pos, osk_type

T = "ours"
REFS = os.path.join("scripts", "parity", "refs")
OSK_ACCENT_BOX = (20, 396, 96, 428)   # accent-toggle key: accented "aei" in normal mode, "abc" in accent mode

# Per-instance environment: window title tag (the harness finds windows by title substring),
# memory-card directory and the UDP port shift (two clients on one host must not both bind the
# game's fixed 3658/3659, like PCSX2 client B's 0F6FC6CF.clientB.pnach).
INSTANCES = {
    "A": {"PS2X_WINDOW_TITLE": "SOCOM-A", "PS2X_SOCOM2_INPUT_FILE": os.path.abspath("logs/pad_A.txt")},
    "B": {"PS2X_WINDOW_TITLE": "SOCOM-B", "PS2X_MC_DIR": os.path.abspath("game/disc/mc0_b"), "PS2X_SOCOM2_UDP_SHIFT": "2",
          "PS2X_SOCOM2_INPUT_FILE": os.path.abspath("logs/pad_B.txt"),
          # PS2X_SOCOM2_RSA_KEY: instance B may carry the second precomputed key pair so the two
          # clients do not publish the same RSA public key in their DME 0x18 records (PCSX2's two
          # clients publish distinct random keys). Set PS2X_SOCOM2_RSA_KEY_B=b in the environment
          # to turn it on for a run; unset keeps the historical behaviour.
          "PS2X_SOCOM2_RSA_KEY": os.environ.get("PS2X_SOCOM2_RSA_KEY_B", ""),
          # PS2X_SOCOM2_NET_STATS_B=0 turns the interface-statistics fix OFF for instance B only,
          # so one run carries both legs of the A/B on a single binary: A moves, B is pinned.
          "PS2X_SOCOM2_NET_STATS": os.environ.get("PS2X_SOCOM2_NET_STATS_B", "")},
}


def launch(seconds, instance=None):
    """Start the exe; returns (proc, title substring to find its window)."""
    env = dict(os.environ, PS2X_SOCOM2_PAD="1")
    title = keys.WINDOW_TITLES[T]
    latest = os.path.abspath(os.path.join("logs", "parity", f"latest_frame_{instance or 'A'}.png"))
    env["PS2X_HOST_SCREENSHOT_LATEST"] = latest
    if instance:
        env.update(INSTANCES[instance])
        write_pad_file(INSTANCES[instance]["PS2X_SOCOM2_INPUT_FILE"])   # neutral before the exe starts
        title = INSTANCES[instance]["PS2X_WINDOW_TITLE"]
        os.makedirs(env.get("PS2X_MC_DIR", "game/disc/mc0"), exist_ok=True)
    proc = subprocess.Popen(["bash", "./run.sh", str(seconds)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.latest_frame = latest
    return proc, title


# Pad-state injection (PS2X_SOCOM2_INPUT_FILE, socom2_host_input.cpp): the exe reads this file on
# every pad poll, so holds are exact and never dropped (posted keyboard messages were). Button ids
# are the pad ids (kPad*): SELECT 0, L3 1, R3 2, START 3, UP 4, RIGHT 5, DOWN 6, LEFT 7, L2 8,
# R2 9, L1 10, R1 11, TRIANGLE 12, CIRCLE 13, CROSS 14, SQUARE 15. Axes 0..255, 0x80 = neutral.
PAD_BUTTON = {"SELECT": 0, "L3": 1, "R3": 2, "START": 3, "UP": 4, "RIGHT": 5, "DOWN": 6, "LEFT": 7,
              "L2": 8, "R2": 9, "L1": 10, "R1": 11, "TRIANGLE": 12, "CIRCLE": 13, "CROSS": 14, "SQUARE": 15}
PAD_AXIS = {"J": ("rx", 0), "L": ("rx", 255), "I": ("ry", 0), "K": ("ry", 255),
            "A": ("lx", 0), "D": ("lx", 255), "W": ("ly", 0), "S": ("ly", 255)}


def write_pad_file(path, buttons=(), axes=None):
    """Write the injected pad state atomically (tmp + replace); buttons by name, axes {rx,ry,lx,ly}."""
    a = {"rx": 0x80, "ry": 0x80, "lx": 0x80, "ly": 0x80}
    a.update(axes or {})
    mask = 0
    for b in buttons:
        mask |= 1 << PAD_BUTTON[b.upper()]
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"b={mask:04x} rx={a['rx']} ry={a['ry']} lx={a['lx']} ly={a['ly']}" + chr(10))
    # The exe opens this file on every pad poll (60 Hz), and a Windows rename over a file another
    # process has open fails with WinError 5. Rare for a hold (two writes a second or two apart),
    # routine for a keyboard walk (two writes every 0.09 s) -- which crashed a whole run. Retry.
    for attempt in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.005)
    os.replace(tmp, path)


class Shell:
    def __init__(self, hwnd, out, t0, tag="", pad_file=None):
        self.hwnd, self.out, self.t0, self.tag = hwnd, out, t0, tag
        self.pad_file = pad_file
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
        """Hold a key (stick directions W/A/S/D, I/J/K/L; R1 fire) for `seconds`. With a pad file the
        state is injected (exact, never dropped); otherwise a posted keyboard hold."""
        if self.pad_file:
            self.pad(seconds, [b] if b.upper() in PAD_BUTTON else (), [b] if b.upper() in PAD_AXIS else ())
        else:
            keys.press(self.hwnd, b, T, hold_s=seconds)
        time.sleep(wait)

    def pad_press(self, b, wait=0.35, hold_s=0.09):
        """One button press through the INJECTED pad file. Posted WM_KEY messages reach raylib only
        when the window thread pumps, so a press in a long scripted burst can be dropped (STATUS
        2026-09-10 20:10) -- which is how a game-name ended up as "eq4P--" in one run and as "test;"
        with the keyboard left open in another, both of which cost a whole 12-minute match.

        0.09 s is ~5-6 frames at the shell's 60 fps: long enough for the pad poll to see it, short
        enough to stay under the keyboard's auto-repeat (0.15 s / 9 frames overshoots the cursor).
        """
        write_pad_file(self.pad_file, [b])
        time.sleep(hold_s)
        write_pad_file(self.pad_file)
        time.sleep(wait)

    def pad(self, seconds, buttons=(), sticks=()):
        """Inject buttons (names) and stick directions (W/A/S/D, I/J/K/L) together for `seconds`."""
        axes = {}
        for k in sticks:
            name, value = PAD_AXIS[k.upper()]
            axes[name] = value
        write_pad_file(self.pad_file, buttons, axes)
        time.sleep(seconds)
        write_pad_file(self.pad_file)

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

    def osk_refs(self):
        """Distance of the accent-toggle key to the two references: which mode the on-screen
        keyboard is in, and (by both distances being large) whether it is on screen at all."""
        normal = np.asarray(Image.open(os.path.join("scripts", "parity", "ref_osk_normal.png")).convert("L"), dtype=float)
        accent = np.asarray(Image.open(os.path.join("scripts", "parity", "ref_osk_accent.png")).convert("L"), dtype=float)
        cur = np.asarray(winshot.grab(self.hwnd).crop(OSK_ACCENT_BOX).convert("L"), dtype=float)
        return float(abs(cur - normal).mean()), float(abs(cur - accent).mean())

    # Measured on logs/parity/ours_task7_cal1 (keyboard up: 39.0/43.1 and 6.3/0.0) against the
    # screens behind it (keyboard gone: 59.9 and 74.1). Only used to LOG whether a type() left the
    # keyboard open, so a run that flakes says so in its own drive log instead of silently
    # spending twelve minutes driving a keyboard.
    OSK_OPEN_MAX = 50.0

    def osk_open(self):
        return min(self.osk_refs()) < self.OSK_OPEN_MAX

    def osk_normal_mode(self):
        dn, da = self.osk_refs()
        if da < dn:
            self.log("keyboard in accent mode -> toggling")
            if self.pad_file:
                self.pad_press("CROSS", 0.8)
            else:
                self.press("cross", 0.8)

    def wait_osk(self, timeout=12.0, reopen=True):
        """Wait for the on-screen keyboard to actually be on screen before typing into it.

        Without this the harness types blind: in ours_task7_wtb3 the CROSS that enters CREATE GAME
        landed a screen late, so the CROSS meant to open the game-name keyboard entered CREATE GAME
        instead, and `type("test")` then hammered the CREATE GAME menu -- it changed ROUND COUNT to
        1 and ROUND TIME to 20 minutes, left GAME NAME empty, and the lobby refused to create the
        game ("You must create a playlist before game creation can occur"). Twelve minutes, and
        nothing in any log said what had happened.
        """
        def tap(b, wait):
            if self.pad_file:
                self.pad_press(b.upper(), wait)
            else:
                self.press(b, wait)

        # Escalate in bounded steps: one more CROSS (the press that should have opened it was
        # eaten by a transition), then BACK + CROSS (an unexpected screen is in the way -- in
        # ours_task7_wtb4 a "SELECT A CONTROLLER CONFIGURATION" screen appeared mid-login and
        # swallowed both persona presses). Then give up, loudly, with a screenshot.
        for attempt, recovery in enumerate(([], ["cross"], ["triangle", "cross"])[:1 + (2 if reopen else 0)]):
            for b in recovery:
                tap(b, 2.0)
            if recovery:
                self.log(f"on-screen keyboard not up -> tried {'+'.join(recovery).upper()}")
            t = time.time()
            while time.time() - t < timeout:
                if self.osk_open():
                    if attempt:
                        self.log(f"on-screen keyboard up after recovery {attempt}")
                    return True
                time.sleep(0.5)
            self.log(f"on-screen keyboard still not up after {timeout:.0f}s "
                     f"(accent-box distance {self.osk_refs()})")
        return False

    def type(self, text, shots=None, tag=""):
        if not self.wait_osk():
            self.shot("osk_never_opened")
            raise SystemExit(f"{self.tag}on-screen keyboard never opened for {text!r}: refusing to "
                             f"type into whatever menu is on screen")
        self.osk_normal_mode()
        if self.pad_file:
            self.osk_type_pad(text, shots, tag)
        else:
            osk_type(self.hwnd, text, shots, tag, target=T)
        time.sleep(3.0)
        if self.osk_open():
            self.log(f"WARNING: the on-screen keyboard is still up after typing {text!r} "
                     f"(accent-box distance {self.osk_refs()}) -- the presses after this one go to "
                     f"the keyboard, not to the menu")

    def osk_type_pad(self, text, shots=None, tag=""):
        """Type on the on-screen keyboard through the injected pad file rather than posted keys:
        the cursor walk is dead-reckoned from OSK_START, so a single dropped press mistypes every
        character after it and, on the last one, presses the key next to ENTER instead of ENTER."""
        cur = OSK_START
        for n, ch in enumerate(list(text) + ["ENTER"]):
            dst = osk_pos(ch)
            for m in osk_moves(cur, dst):
                self.pad_press(m.upper())
            cur = dst
            self.pad_press("CROSS", 0.6)
            if shots and ch != "ENTER":
                winshot.grab(self.hwnd).save(os.path.join(shots, f"{tag}_key{n}_{ch}.png"))


def attach(proc, title, out, tag="", pad_file=None):
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
    sh = Shell(hwnd, out, t0, tag, pad_file)
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


def require_game_lobby(sh, what):
    """Fail here, in four minutes, rather than after twelve.

    host_game/join_game navigate by fixed presses, and a press that lands a screen late derails the
    rest silently: in ours_task7_wtb5 the CROSS meant to open CHOOSE GAMES was eaten, the play list
    stayed empty, and the lobby answered "You must create a playlist before game creation can
    occur" -- but the driver pressed on, READY did nothing, and the run died on the liveness check
    eight minutes later. The game_lobby reference separates the two outcomes exactly: it scores
    0.287 on every run that launched a match (task6_ab, task7 cal3/wtb1/wtb2) and 0.506-0.509 on
    every run that did not (task7 cal1/wtb3/wtb5).
    """
    if sh.is_screen("game_lobby"):
        return
    sh.shot("17_game_lobby_FAILED")
    raise SystemExit(f"{sh.tag}{what} did not reach the GAME LOBBY (game_lobby band distance "
                     f"{sh.diff('game_lobby'):.3f}, threshold 0.45) -- see the capture; the match "
                     f"would never have launched")


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
    require_game_lobby(sh, "CREATE GAME")


def lobby_cursor(sh):
    """Index of the highlighted GAME LOBBY menu row (0 ARMORY, 1 SWITCH TEAMS, 2 NOT READY/READY),
    -1 when nothing is highlighted (a fresh lobby shows no cursor until the first press). The
    highlighted row is a teal fill (mean ~70 vs ~30)."""
    im = np.asarray(winshot.grab(sh.hwnd).convert("L"), dtype=np.float32)
    means = [float(im[y0:y1, 22:165].mean()) for y0, y1 in ((98, 120), (128, 150), (158, 180))]
    i = int(np.argmax(means))
    return i if means[i] > 50 else -1


def lobby_teams(sh):
    """Bright text pixels in the SEALS and TERRORISTS name columns (rows 240..300): who is where."""
    im = np.asarray(winshot.grab(sh.hwnd).convert("L"), dtype=np.float32)
    return int((im[240:300, 180:390] > 140).sum()), int((im[240:300, 405:615] > 140).sum())


def lobby_select(sh, row, label):
    """Move the lobby cursor to `row` by reading the highlight (no assumption about wrap-around or
    where the cursor starts: the old fixed 'down, cross' for SWITCH TEAMS landed on NOT READY)."""
    prev, key = None, None
    for _ in range(8):
        cur = lobby_cursor(sh)
        if cur == row:
            break
        # Prefer the short way; if the last press did not move the cursor (sweep2: UP from
        # NOT READY did nothing), go the other way round (the menu wraps on DOWN).
        want = "down" if cur < row else "up"
        if cur == prev and key is not None:
            want = "down" if key == "up" else "up"
        sh.press(want, 1.0)
        sh.log(f"lobby cursor {cur} -> {want}")
        prev, key = cur, want
    sh.log(f"lobby cursor {lobby_cursor(sh)} for {label}")


def join_game(sh, switch=True):
    sh.press("cross", 8.0)                                       # JOIN GAME activates the list
    sh.shot("12_games_list")
    sh.press("cross", 25.0)                                      # first game
    sh.shot("16_game_lobby")
    sh.press("cross", 3.0)                                       # CONTINUE
    sh.shot("17_game_lobby_ok")
    require_game_lobby(sh, "JOIN GAME")
    sh.log(f"teams (seals, terrorists text px) {lobby_teams(sh)}")
    if switch:                                                   # a joiner is auto-assigned to the other team
        lobby_select(sh, 1, "SWITCH TEAMS")
        sh.press("cross", 4.0)
        sh.shot("18_switched")
        sh.log(f"teams after switch {lobby_teams(sh)}")


def ready(sh):
    lobby_select(sh, 2, "READY")                                 # menu: ARMORY, SWITCH TEAMS, READY
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
