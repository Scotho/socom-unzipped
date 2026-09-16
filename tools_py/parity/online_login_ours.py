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
import contextlib
import functools
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

# The keyboard's text row, for reading back what a type() actually put there (2026-09-15 evening, s6_ladder2 and
# s6_ladder_oldharness: at ~32 fps -- two instances on one host -- the password came out as 'ocom', '' and 'xmfû'
# and nothing in the drive log said so; research/28 §5 item 4). Measured on the 640x448 captures: each typed glyph
# is a run of light-grey columns (max 100-200, 3-11 px wide: ';' to 'm') separated by 2-3 dark columns, starting at
# col 31; the cursor block after the text is white (max > 200, 5 px) and BLINKS (absent in 7 of the 12 per-key
# captures of ours_login / ours_match), and the font is proportional ("test;p" ends 20 px short of 6 x 11.3), so
# the count is the number of glyph runs, not the cursor position. Exact on 15 of 15 labelled captures (the 12
# per-key ones, 'xmfû', "test;p", and an empty field with its cursor on).
OSK_TEXT_ROWS = (228, 250)
OSK_TEXT_COLS = (20, 470)
OSK_INK_MIN = 60                 # column max above this is ink (glyph or cursor); the field's ground stays below
OSK_CURSOR_MIN = 200             # column max above this is the cursor block, not counted; glyphs stay below it
OSK_GLYPH_MIN_WIDTH = 2          # a narrower run is a cursor edge, not a glyph (';', the narrowest, is 3 px)
OSK_TYPE_ATTEMPTS = 3            # one type + two retypes before login:keyboard-typing
OSK_SLOW_HOLD_S, OSK_SLOW_WAIT_S = 0.18, 0.5   # retype pacing: 0.09 s / 0.35 s doubled (5-6 frames at 32 fps)
OSK_CROSS_WAIT_S = 0.6                          # after a key's CROSS, both pacings (the keyboard redraws the field)

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
          "PS2X_SOCOM2_NET_STATS": os.environ.get("PS2X_SOCOM2_NET_STATS_B", ""),
          # PS2X_GUEST_MALLOC_ZERO_B=1 zero-fills fresh guest heap blocks for instance B only; unset
          # leaves B off even when PS2X_GUEST_MALLOC_ZERO=1 is exported for instance A, so one run on
          # one binary carries both legs of the zero-fill A/B (Sprint 5 Task 1).
          "PS2X_GUEST_MALLOC_ZERO": os.environ.get("PS2X_GUEST_MALLOC_ZERO_B", "")},
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


PAD_AXIS_NAMES = ("rx", "ry", "lx", "ly")


def pad_axes(sticks=(), axes=None):
    """{axis: 0..255} for a pad write: stick keys (PAD_AXIS, full deflection 0/255) first, then explicit
    `axes` -- PARTIAL deflection, the only way to aim finer than the ~35-40 deg a full-deflection hold
    sweeps (KNOWN §1: the pad file accepts 0-255 per axis) -- overriding a stick on the same axis.
    Anything but an int in 0..255 on rx/ry/lx/ly is refused: a bad axis silently clamped by the exe
    would aim somewhere nobody asked for."""
    out = {}
    for k in sticks:
        name, value = PAD_AXIS[k.upper()]
        out[name] = value
    for name, value in (axes or {}).items():
        if name not in PAD_AXIS_NAMES:
            raise ValueError(f"pad axis {name!r} is not one of {PAD_AXIS_NAMES}")
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
            raise ValueError(f"pad axis {name}={value!r} must be an int in 0..255")
        out[name] = value
    return out


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


# ---------------------------------------------------------------------------
# Lobby failure classes, per-stage timeouts, verified re-send (Sprint 5 R47, plan Amendment A6)
# ---------------------------------------------------------------------------
# A lobby failure is not an engagement result: it prints `RESULT LOBBY-FAIL <class>` and one
# `LOBBY class=<class>` line, and exits LOBBY_FAIL_EXIT (online_match_ours uses 0 go, 1 FAIL,
# 2 NO-DATA, 3 NO-CONTROL). A launch that reaches gameplay prints `LOBBY class=ok`.
LOBBY_STAGES = ("login", "host", "join", "map_select", "ready", "launch")
LOBBY_STAGE_TIMEOUT_S = 180.0   # kill5 and 8a spent 390-800 s waiting on a lobby that had already failed
LOBBY_FAIL_EXIT = 4
LOBBY_RESEND_MAX = 3
# Frame age for a signature check. Both checked presses wait >= 3 s first, so a frame file younger
# than this was rendered after the press (the runtime rewrites it every ~150 ms).
LOBBY_FRAME_MAX_AGE_S = 1.0
CLASS_OK, CLASS_MAP_CROSS, CLASS_READY = "ok", "map-cross-dropped", "ready-dropped"
CLASS_JOIN, CLASS_HOST = "join-not-reached", "host-not-reached"
CLASS_MAP_SEARCH, CLASS_KEYBOARD = "map-list-search", "login-keyboard"
# Sprint 6 Task 2 (research/28 §4): a window that never reaches the main menu, or never shows the LOGIN
# screen after it (wtb4, 3b), used to exit 1 without a class 120-180 s downstream. A `wait_for` timeout
# anywhere else is `screen:<name>`; a verified fixed press that never lands is `create-game:<step>` or
# `join:<step>` (LOBBY_PRESS_STEPS below), each printed as one `[lobby] <step> press=<btn> verified=<bool>
# attempt=<n>` line per press so the next taxonomy is a grep.
CLASS_PRE_LOGIN = "pre-login"
CLASS_OSK_TYPING = "login:keyboard-typing"   # the keyboard read back the wrong character count three times

# Title band of the four screens the CREATE GAME / JOIN GAME presses move between (full-res 640x448:
# x 20-360, y 18-58), compared as a text mask (map_mask_distance's measure) against
# scripts/parity/refs/lobby/title_<name>.png, cut from launch 8c by
# tools_py/tests/fixtures/lobby/make_screen_fixtures.py. Over the 128 stage captures of the 30 launches
# in research/28 §1 the right screen scores 0.000-0.011, the nearest wrong one 0.385 (CREATE GAME vs
# CREATE GAME PLAY LIST, whose title extends the other's) and every other pair >= 0.658.
LOBBY_TITLE = (slice(18, 58), slice(20, 360))
LOBBY_TITLES = ("briefing_room", "create_game", "play_list", "game_lobby")
LOBBY_TITLE_MAX_DIST = 0.15     # 14x the worst true match, under half the nearest wrong pair
LOBBY_REF_DIR = os.path.join(REFS, "lobby")
# Menu rows the fixed UP presses must light before the CROSS that follows (y0, y1, x0, x1). A lit row is
# a teal fill: its median luminance is 62-68 on every capture, an unlit row's <= 34 (even with the
# game-name keyboard drawn over the menu, cal1). The games-list row is a fainter fill: 36 when JOIN
# GAME activated a list with a game in it (8c, launch1), 15-18 with "There are no games to join."
LOBBY_ROWS = {"create_game": (106, 128, 18, 135),     # BRIEFING ROOM menu row 0
              "choose_games": (386, 406, 18, 170),    # CREATE GAME menu's last row
              "games_list": (262, 280, 150, 620)}     # first row of the briefing room's games list
LOBBY_ROW_LIT_MEDIAN = {"create_game": 50.0, "choose_games": 50.0, "games_list": 27.0}
# The "READY button will be available in 30 seconds ... CONTINUE" panel: region mean 54 while it is
# up (every *_16_game_lobby capture), 27-28 once CONTINUE dismissed it (*_17_game_lobby_ok).
LOBBY_NOTICE = (slice(152, 265), slice(150, 490))
LOBBY_NOTICE_MIN_MEAN = 40.0

# Map CROSS signature: the SELECTED MAPS panel (x 335-625, y 110-380) is byte-identical when the
# CROSS did not register. 8b's dropped press: mean |diff| 0.00 (A_14b vs A_15, 9 s and a SQUARE
# apart). 8c's live check 4 s after a taken CROSS alone: 3.52 (8.95 once the SQUARE had followed).
# The 8c driver retried below 3.0; 1.0 keeps "byte-identical" and leaves 3.5x margin to that read.
MAP_PANEL = (slice(110, 380), slice(335, 625))
MAP_CROSS_DROPPED_MAX_DIFF = 1.0
# READY signature: the row-2 label's text right edge (luminance > 110, x 22-165, y 158-180) is
# col 48 while it still reads READY and col 82-83 once NOT READY shows (8a A/B). No text at all
# (8c: the match launched inside 3 s) or any other edge is NOT retried: a second CROSS on NOT
# READY would un-ready.
READY_LABEL = (slice(158, 180), slice(22, 165))
READY_LABEL_LUMA = 110
READY_EDGE_DROPPED_MAX = 55
READY_CONFIRM_GAP_S = 1.0       # R69: the two frames a READY re-send needs are this far apart


class LobbyFail(SystemExit):
    """A classified lobby failure; a SystemExit so every existing caller exits LOBBY_FAIL_EXIT."""

    def __init__(self, cls, detail=""):
        super().__init__(LOBBY_FAIL_EXIT)
        self.cls, self.detail = cls, detail

    def __str__(self):
        return f"LOBBY-FAIL {self.cls}" + (f" -- {self.detail}" if self.detail else "")


def lobby_fail(sh, cls, detail=""):
    """Log the RESULT and class lines, capture the screen when possible; returns the exception to raise."""
    sh.log(f"RESULT LOBBY-FAIL {cls}" + (f" -- {detail}" if detail else ""))
    sh.log(f"LOBBY class={cls}")
    sh.stages = ()                        # the failure is decided: nothing after this re-enters the timeout
    try:
        sh.shot(f"lobby_fail_{cls.replace(':', '_')}")
    except (RuntimeError, OSError) as e:  # a stale or missing frame must not hide the classification
        sh.log(f"(no lobby-fail capture: {e})")
    return LobbyFail(cls, detail)


@contextlib.contextmanager
def lobby_stage(sh, name, timeout=LOBBY_STAGE_TIMEOUT_S):
    """Run a lobby stage under a deadline. Shell.press / pad_press / is_screen / osk_refs check it, so
    an overrun ends as `timeout:<stage>` within one step. A nested stage keeps the outer deadline
    running; the outermost expired stage is the one reported."""
    if name not in LOBBY_STAGES:
        raise ValueError(f"unknown lobby stage {name!r}")
    prev = sh.stages
    sh.stages = tuple(prev) + ((name, sh.clock() + timeout),)
    try:
        yield
    finally:
        sh.stages = prev


def staged(name):
    """Decorator: the lobby function (first argument a Shell) runs as stage `name`."""
    def deco(fn):
        @functools.wraps(fn)
        def run(sh, *a, **k):
            with lobby_stage(sh, name):
                return fn(sh, *a, **k)
        run.lobby_stage = name
        return run
    return deco


def lobby_launch_budget(t_start, clock=time.time):
    """Seconds left of the launch stage (READY -> gameplay rows), which both instances share."""
    return max(1.0, LOBBY_STAGE_TIMEOUT_S - (clock() - t_start))


def lobby_gray_of(im):
    return np.asarray(im.convert("L"), dtype=np.float32)


def lobby_gray(sh):
    """A frame rendered after the press. A StaleFrameError (an instance stall) is waited out under the
    stage deadline, never read as a dropped press."""
    while True:
        try:
            return lobby_gray_of(winshot.grab(sh.hwnd, max_age=LOBBY_FRAME_MAX_AGE_S))
        except winshot.StaleFrameError as e:
            sh.log(f"lobby check: {e} -- waiting for a fresh frame")
            sh.check_stage()


def map_panel_diff(pre, post):
    return float(np.abs(post[MAP_PANEL] - pre[MAP_PANEL]).mean())


def map_cross_dropped(pre, post):
    return map_panel_diff(pre, post) < MAP_CROSS_DROPPED_MAX_DIFF


def ready_label_edge(gray):
    cols = np.where((gray[READY_LABEL] > READY_LABEL_LUMA).any(axis=0))[0]
    return int(cols.max()) if len(cols) else None


def ready_dropped(gray):
    edge = ready_label_edge(gray)
    return edge is not None and edge <= READY_EDGE_DROPPED_MAX


def lobby_resend(sh, btn, wait):
    """A re-sent press goes through the injected pad file when there is one (never dropped)."""
    if sh.pad_file:
        sh.pad_press(btn.upper(), wait=wait)
    else:
        sh.press(btn, wait)


def lobby_resend_cross(sh, wait):
    lobby_resend(sh, "cross", wait)


def verify_resend(sh, cls, dropped, resend):
    """Check the press; re-send up to LOBBY_RESEND_MAX times; LobbyFail(cls) if it never registers.
    Returns the number of re-sends it took."""
    for attempt in range(1, LOBBY_RESEND_MAX + 1):
        if not dropped():
            return attempt - 1
        sh.log(f"LOBBY RESEND {cls} attempt={attempt}")
        resend()
    if not dropped():
        return LOBBY_RESEND_MAX
    raise lobby_fail(sh, cls, f"still not registered after {LOBBY_RESEND_MAX} re-sends")


def press_map_cross_verified(sh, wait=4.0):
    """The CROSS that moves the highlighted map into SELECTED MAPS, verified on that panel."""
    pre = lobby_gray(sh)
    sh.press("cross", wait)

    def dropped():
        d = map_panel_diff(pre, lobby_gray(sh))
        sh.log(f"map CROSS check: SELECTED MAPS panel mean |diff| {d:.2f}")
        return d < MAP_CROSS_DROPPED_MAX_DIFF

    return verify_resend(sh, CLASS_MAP_CROSS, dropped, lambda: lobby_resend_cross(sh, wait))


# ---------------------------------------------------------------------------
# Verified fixed presses (Sprint 6 Task 2, research/28 §4 ranks 1-3)
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=None)
def lobby_title_ref(name):
    return np.asarray(Image.open(os.path.join(LOBBY_REF_DIR, f"title_{name}.png")).convert("L"), dtype=np.float32)


def lobby_title_dist(gray, name):
    """Text-mask distance of the frame's title band to the `name` reference (0 = the same title)."""
    return map_mask_distance(gray[LOBBY_TITLE], lobby_title_ref(name))


def lobby_title_is(gray, name):
    return lobby_title_dist(gray, name) <= LOBBY_TITLE_MAX_DIST


def lobby_row_lit(gray, row):
    y0, y1, x0, x1 = LOBBY_ROWS[row]
    return float(np.median(gray[y0:y1, x0:x1])) > LOBBY_ROW_LIT_MEDIAN[row]


def lobby_notice_up(gray):
    return float(gray[LOBBY_NOTICE].mean()) > LOBBY_NOTICE_MIN_MEAN


def press_verified(sh, step, btn, wait, check, what):
    """Press `btn`, wait, and verify `check(gray)` on a fresh frame; re-send through the pad up to
    LOBBY_RESEND_MAX times; LobbyFail(step) if the expected screen never appears. One log line per press:
    `[lobby] <step> press=<btn> verified=<bool> attempt=<n>`. Returns the number of re-sends it took.

    The whole CREATE GAME / JOIN GAME flow used to be blind fixed presses, and one eaten press derailed
    the rest silently: wtb3 and kill6 lost the CROSS into CREATE GAME and typed the game name into the
    briefing room; kill4, kill7 and 8b lost the ACCEPT and created nothing; launch1/1b's JOIN never
    entered the lobby -- each classified at the end of the stage (or 500 s later on liveness) with no
    press named. research/28 §4 puts these first at 9 of 16 failures."""
    n = [0]

    def send():
        n[0] += 1
        if n[0] == 1:
            sh.press(btn, wait)
        else:
            lobby_resend(sh, btn, wait)

    def dropped():
        ok = bool(check(lobby_gray(sh)))
        sh.log(f"[lobby] {step} press={btn} verified={ok} attempt={n[0]}")
        return not ok

    send()
    try:
        return verify_resend(sh, step, dropped, send)
    except LobbyFail as e:
        e.detail = f"{what} never showed after {btn.upper()} and {LOBBY_RESEND_MAX} re-sends -- see the capture"
        raise


class Shell:
    stages = ()                  # active lobby stages ((name, deadline), ...), outermost first
    clock = staticmethod(time.time)

    def check_stage(self):
        now = self.clock() if self.stages else None
        for name, deadline in self.stages:
            if now >= deadline:
                raise lobby_fail(self, f"timeout:{name}", f"stage {name} exceeded {LOBBY_STAGE_TIMEOUT_S:.0f}s")

    def stage_sleep(self, seconds):
        """time.sleep, cut at the active stage deadline (the check then raises)."""
        if self.stages:
            seconds = max(0.0, min(seconds, min(d for _, d in self.stages) - self.clock()))
        time.sleep(seconds)
        self.check_stage()

    def __init__(self, hwnd, out, t0, tag="", pad_file=None):
        self.hwnd, self.out, self.t0, self.tag = hwnd, out, t0, tag
        self.pad_file = pad_file
        self.meta = json.load(open(os.path.join(REFS, "refs.json")))
        self.refs = {n: np.asarray(Image.open(os.path.join(REFS, n + ".png")).convert("L"), dtype=float) for n in self.meta}
        self.menu = Image.open(os.path.join(REFS, "main_menu.png"))
        self.last = None

    def log(self, m):
        print(f"{time.time() - self.t0:6.1f}s {self.tag}{m}", flush=True)

    def shot(self, label, max_age=None):
        """Save the current frame. max_age (s): refuse a frame file older than that --
        winshot.StaleFrameError, which evidence screens (kill, final) use; menus pass none."""
        winshot.grab(self.hwnd, max_age=max_age).save(os.path.join(self.out, f"{self.tag}{label}.png"))

    def press(self, b, wait=1.0):
        # 0.08 s = 5 frames at the shell's 60 fps: long enough to register, short enough not to
        # trip the UI's held-button repeat (a 0.15 s CROSS closed the SERVER NEWS popup and the
        # repeat reopened it, eight times in a row, 2026-09-09 play4).
        self.check_stage()
        keys.press(self.hwnd, b, T, hold_s=0.08)
        self.stage_sleep(wait)

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
        self.check_stage()
        write_pad_file(self.pad_file, [b])
        try:
            self.stage_sleep(hold_s)
        finally:
            write_pad_file(self.pad_file)          # a deadline inside the hold must not leave the button down
        self.stage_sleep(wait)

    def pad(self, seconds, buttons=(), sticks=(), axes=None, abort=None):
        """Inject buttons (names), stick directions (W/A/S/D, I/J/K/L, full deflection) and explicit
        0-255 `axes` ({rx, ry, lx, ly}: partial deflection, overriding a stick on the same axis)
        together for `seconds`, then write neutral.

        `abort` (a threading.Event) releases the pad the moment it is set instead of at the end of
        the hold. The two-mover approach passes the duel's contact flag: a player still walking
        after the OTHER side has called contact overshoots the engagement, which is the geometry
        problem the whole of Task 8 was fighting."""
        axes = pad_axes(sticks, axes)
        write_pad_file(self.pad_file, buttons, axes)
        try:
            if abort is None:
                time.sleep(seconds)
            else:
                abort.wait(seconds)
        finally:
            write_pad_file(self.pad_file)        # an interrupted hold must not leave a stick held (slice (b) review)

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
        self.check_stage()
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

    def wait_for(self, name, timeout, thresh=None, cls=None, required=True):
        """Wait for screen `name`. A timeout is a classified lobby failure (`cls`, default
        `screen:<name>`): research/28 §4 rank 2 -- it used to log `TIMEOUT waiting for <name>` and return
        False, and every caller pressed on into whatever was on screen (wtb4, 3b, ladder1), so the class
        finally raised named a screen 120-180 s downstream of the miss. `required=False` keeps the old
        log-and-return for the one screen whose reference is known to miss on good runs."""
        t = self.clock()
        while self.clock() - t < timeout:
            if self.is_screen(name, thresh):
                self.log(f"screen {name} after {self.clock() - t:.1f}s")
                return True
            time.sleep(0.5)
        self.log(f"TIMEOUT waiting for {name}")
        self.shot(f"timeout_{name}")
        if not required:
            return False
        raise lobby_fail(self, cls or f"screen:{name}", f"{name} not on screen within {timeout:.0f}s")

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
        self.check_stage()
        return osk_ref_dists(lobby_gray_of(winshot.grab(self.hwnd)))

    # Measured on logs/parity/ours_task7_cal1 (keyboard up: 39.0/43.1 and 6.3/0.0) against the
    # screens behind it (keyboard gone: 59.9 and 74.1). Only used to LOG whether a type() left the
    # keyboard open, so a run that flakes says so in its own drive log instead of silently
    # spending twelve minutes driving a keyboard.
    OSK_OPEN_MAX = 50.0

    def osk_open(self):
        return min(self.osk_refs()) < self.OSK_OPEN_MAX

    OSK_MODE_TOGGLES = 2

    def osk_normal_mode(self):
        """Toggle the keyboard out of accent mode, and READ THE MODE BACK on a fresh frame after each toggle:
        the 2026-09-15 old-harness run toggled once, blind, and typed 'xmfû' for 'socom'. At most two toggles
        (a third would be a dropped press or a mode the references do not know); the mode is logged each read."""
        dn, da = self.osk_refs()
        for toggle in range(self.OSK_MODE_TOGGLES + 1):
            if dn <= da:
                self.log(f"[osk] mode normal ({dn:.1f} vs {da:.1f})")
                return
            if toggle == self.OSK_MODE_TOGGLES:
                self.log(f"[osk] mode accent ({dn:.1f} vs {da:.1f}) after {toggle} toggles -- typing anyway")
                return
            self.log(f"[osk] mode accent ({dn:.1f} vs {da:.1f}) -> toggling" + (" again" if toggle else ""))
            if self.pad_file:
                self.pad_press("CROSS", 0.8)
            else:
                self.press("cross", 0.8)
            dn, da = osk_ref_dists(lobby_gray(self))          # a frame rendered after the press

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
            stage = self.stages[-1][0] if self.stages else "none"
            raise lobby_fail(self, CLASS_KEYBOARD, f"on-screen keyboard never opened for {text!r} (stage {stage}): "
                                                   f"refusing to type into whatever menu is on screen")
        self.osk_normal_mode()
        if self.pad_file:
            self.osk_type_pad_verified(text, shots, tag)
        else:
            osk_type(self.hwnd, text, shots, tag, target=T)
        time.sleep(3.0)
        if self.osk_open():
            self.log(f"WARNING: the on-screen keyboard is still up after typing {text!r} "
                     f"(accent-box distance {self.osk_refs()}) -- the presses after this one go to "
                     f"the keyboard, not to the menu")

    @staticmethod
    def osk_pacing(slow):
        """(hold, d-pad wait, CROSS wait) of a pad keyboard press: the 0.09 s / 0.35 s / 0.6 s of pad_press, or
        the doubled OSK_SLOW_* for a retype (the same 5-6 frames at the 32 fps two instances on one host run at);
        the CROSS wait stays 0.6 s, already the longer of the two."""
        return (OSK_SLOW_HOLD_S, OSK_SLOW_WAIT_S, OSK_CROSS_WAIT_S) if slow else (0.09, 0.35, OSK_CROSS_WAIT_S)

    def osk_type_pad(self, text, shots=None, tag="", cur=OSK_START, enter=True, slow=False):
        """Type on the on-screen keyboard through the injected pad file rather than posted keys:
        the cursor walk is dead-reckoned from `cur` (the key the cursor is on), so a single dropped
        press mistypes every character after it and, on the last one, presses the key next to ENTER
        instead of ENTER. `enter=False` leaves the field open (the verified typer reads it back first);
        `slow` uses the OSK_SLOW_* pacing for a retype. Returns the key the cursor is on."""
        hold, wait, cross_wait = self.osk_pacing(slow)
        for n, ch in enumerate(list(text) + (["ENTER"] if enter else [])):
            dst = osk_pos(ch)
            for m in osk_moves(cur, dst):
                self.pad_press(m.upper(), wait, hold)
            cur = dst
            self.pad_press("CROSS", cross_wait, hold)
            if shots and ch != "ENTER":
                winshot.grab(self.hwnd).save(os.path.join(shots, f"{tag}_key{n}_{ch}.png"))
        return cur

    def osk_typed(self):
        """Characters in the keyboard's text row, read from a frame rendered after the last press."""
        return osk_typed_count(lobby_gray(self))

    def osk_type_pad_verified(self, text, shots=None, tag=""):
        """Type `text` through the pad WITHOUT the final ENTER, read back how many characters the keyboard
        shows, and only press ENTER when the count matches. A short count (a CROSS dropped at 32 fps: 'ocom',
        an empty field on 2026-09-15) is cleared with one BCKSPC per counted character and retyped at the
        slow pacing; after OSK_TYPE_ATTEMPTS the run fails as login:keyboard-typing with the count in the
        detail, instead of pressing CONNECT with a wrong password and timing out 120 s later on the login
        stage. The cursor stays dead-reckoned between attempts (there is no cursor read-back); the count
        cannot tell a wrong glyph of the right length ('xmfû' is accent mode, which osk_normal_mode guards)."""
        cur, slow = OSK_START, False
        for attempt in range(1, OSK_TYPE_ATTEMPTS + 1):
            cur = self.osk_type_pad(text, shots, tag, cur=cur, enter=False, slow=slow)
            n = self.osk_typed()
            if n == len(text):
                self.log(f"[osk] typed {n} of {len(text)} (attempt {attempt})")
                break
            if attempt == OSK_TYPE_ATTEMPTS:
                self.log(f"[osk] typed {n} of {len(text)} (attempt {attempt})")
                raise lobby_fail(self, CLASS_OSK_TYPING, f"{n} of {len(text)} characters after {attempt} attempts")
            self.log(f"[osk] typed {n} of {len(text)} -> retype (attempt {attempt})")
            slow = True
            cur = self.osk_clear(cur, n, len(text), slow=slow)
        self.osk_type_pad("", None, "", cur=cur, enter=True, slow=slow)          # the walk to ENTER and its CROSS

    def osk_clear(self, cur, n, total, slow=True):
        """Walk to BCKSPC (top row, right end) and press it once per counted character, then read the field
        back: a count still above 0 gets that many more presses, once (a dropped BCKSPC); characters left
        after that fail the run as login:keyboard-typing. Returns the key the cursor is on (BCKSPC)."""
        hold, wait, cross_wait = self.osk_pacing(slow)
        dst = osk_pos("BCKSPC")
        for m in osk_moves(cur, dst):
            self.pad_press(m.upper(), wait, hold)
        for extra in (False, True):
            for _ in range(n):
                self.pad_press("CROSS", cross_wait, hold)
            left = self.osk_typed()
            if left == 0:
                self.log(f"[osk] cleared: 0 of {total} left")
                return dst
            if extra:
                raise lobby_fail(self, CLASS_OSK_TYPING, f"{left} of {total} characters still in the field after clearing")
            self.log(f"[osk] cleared: {left} of {total} left -> {left} more BCKSPC")
            n = left
        return dst


@functools.lru_cache(maxsize=None)
def osk_mode_refs():
    normal = np.asarray(Image.open(os.path.join("scripts", "parity", "ref_osk_normal.png")).convert("L"), dtype=np.float32)
    accent = np.asarray(Image.open(os.path.join("scripts", "parity", "ref_osk_accent.png")).convert("L"), dtype=np.float32)
    return normal, accent


def osk_ref_dists(gray):
    """(distance to the normal-mode key, distance to the accent-mode key) of a full frame's accent box."""
    x0, y0, x1, y1 = OSK_ACCENT_BOX
    cur = gray[y0:y1, x0:x1]
    normal, accent = osk_mode_refs()
    return float(np.abs(cur - normal).mean()), float(np.abs(cur - accent).mean())


def osk_open_of(gray):
    return min(osk_ref_dists(gray)) < Shell.OSK_OPEN_MAX


def osk_typed_count(gray):
    """Characters in the on-screen keyboard's text row of a full 640x448 grey frame: the number of runs of
    glyph columns (max between OSK_INK_MIN and OSK_CURSOR_MIN, at least OSK_GLYPH_MIN_WIDTH wide, separated by
    a column with no ink). The blinking white cursor block is not a glyph, so an empty field reads 0 whether
    or not its cursor is on. A space has no ink and is not counted (no harness text carries one)."""
    y0, y1 = OSK_TEXT_ROWS
    x0, x1 = OSK_TEXT_COLS
    colmax = np.asarray(gray, dtype=np.float32)[y0:y1, x0:x1].max(axis=0)
    ink, glyph = colmax > OSK_INK_MIN, (colmax > OSK_INK_MIN) & (colmax <= OSK_CURSOR_MIN)
    count, x = 0, 0
    while x < len(ink):
        if not ink[x]:
            x += 1
            continue
        start = x
        while x < len(ink) and ink[x]:
            x += 1
        run = glyph[start:x]
        if run.all() and x - start >= OSK_GLYPH_MIN_WIDTH:      # a run touching a white column is the cursor
            count += 1
    return count


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
        # research/28 §2: exit 1 with no class was the one failure the taxonomy could not count
        raise lobby_fail(sh, CLASS_PRE_LOGIN, "main menu not reached after 9 boot presses")
    time.sleep(3.0)
    sh.press("down", 1.5)
    sh.press("cross", 3.0)                                       # ONLINE
    # wtb4 and 3b (both instances at once) never showed the LOGIN screen here; the old harness pressed on
    # and classified the run as login-keyboard 120-180 s later.
    sh.wait_for("login", 40, cls=CLASS_PRE_LOGIN)
    sh.shot("00_login")


@staged("login")
def login(sh, name, password, existing):
    """LOGIN -> universe -> persona -> password -> CONNECT -> prompts -> EULA -> lobby (news closed)."""
    sh.press_until_gone("cross", "login")                        # LOGIN
    sh.wait_for("universe", 60)
    sh.shot("01_universe")
    sh.press_until_gone("cross", "universe")                     # connect to the universe
    # required=False: `TIMEOUT waiting for persona` was logged by 11 launches that reached gameplay
    # (kill1/2, wtb2/6, frost1, launch2/3c, 8c, ladder2 -- `grep -l "liveness OK" logs/parity/drive_*.txt |
    # xargs grep "TIMEOUT waiting for persona"`): the persona reference misses the screen on good runs, so
    # this one timeout stays a log line. Every other screen's timeout occurred only in failed launches.
    sh.wait_for("persona", 60, required=False)
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


@staged("login")
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
    raise lobby_fail(sh, CLASS_JOIN if what.startswith("JOIN") else CLASS_HOST,
                     f"{what} did not reach the GAME LOBBY (game_lobby band distance "
                     f"{sh.diff('game_lobby'):.3f}, threshold 0.45) -- see the capture; the match "
                     f"would never have launched")


# ---------------------------------------------------------------------------
# CHOOSE GAMES -- the map list
# ---------------------------------------------------------------------------
# The AVAILABLE MAPS box holds six visible rows and SCROLLS, so the entry a fixed number of presses
# lands on is not knowable from one screen and the old blind `sh.press("cross", 4.0)  # Medley`
# accepted whatever happened to be highlighted. Geometry and thresholds below are MEASURED off the
# 27 captures of logs/parity/ours_task8_mapscan (640x448): text rows start at y=117 with a pitch of
# 20 and a height of 12, x 78..292.
MAP_ROW_TOP, MAP_ROW_PITCH, MAP_ROW_H = 117, 20, 12
MAP_ROW_X0, MAP_ROW_X1 = 78, 292
MAP_ROWS = 6
# The highlighted row is gold-on-teal and its PEAK luminance is 123-125 in all 27 captures; an
# ordinary row's pale text peaks at 168-174 and an empty row at 99-110. A single absolute band
# separates all three with a margin of more than 40 either way, which is why this needs no
# reference image and no assumption about where the cursor starts.
MAP_HILITE_LO, MAP_HILITE_HI = 116.0, 140.0
# Text-mask distance: binarise the row and take (symmetric difference / union) over +-3 px of
# shift. Measured across the same 27 captures against the FROSTFIRE reference: the true row scores
# 0.000 and the nearest other map (ENOWAPI) 0.510, so 0.30 has a margin of 0.21. The
# contrast-normalised band distance `Shell.diff` uses was NOT good enough here -- it put ENOWAPI at
# 0.317 against a 0.42 threshold, i.e. it would have accepted the wrong map.
# The MEDLEY reference (map_medley.png) was cut the same way, from the highlighted row 0 of
# A_mapscan_00 in that scan (2026-09-13, offline, no launch). Against the highlighted row of all 28
# CHOOSE GAMES captures it scores 0.000 on the two Medley frames (A_mapscan_00, A_14_choose_games)
# and >= 0.673 on every other map (Random 0.673, ENOWAPI 0.674, Frostfire 0.777, the last entry
# THE RUINS 0.771). Caveat: an UNhighlighted Medley row scores 0.046 against it -- harmless, because
# choose_map only ever compares the highlighted row, which map_cursor finds by luminance.
MAP_MATCH_THRESH = 0.30
MAP_REF_DIR = REFS


def map_row_box(i):
    y0 = MAP_ROW_TOP + MAP_ROW_PITCH * i
    return MAP_ROW_X0, y0, MAP_ROW_X1, y0 + MAP_ROW_H


def map_rows(im):
    a = np.asarray(im.convert("L"), dtype=np.float32)
    out = []
    for i in range(MAP_ROWS):
        x0, y0, x1, y1 = map_row_box(i)
        out.append(a[y0:y1, x0:x1])
    return out


def map_cursor(sh, im=None):
    """Index of the highlighted row in AVAILABLE MAPS, or -1. No reference image needed."""
    rows = map_rows(im or winshot.grab(sh.hwnd))
    cand = [i for i, b in enumerate(rows) if MAP_HILITE_LO <= float(b.max()) <= MAP_HILITE_HI]
    if not cand:
        return -1
    return max(cand, key=lambda i: float(rows[i].std()))


def map_text_mask(band):
    lo, hi = float(band.min()), float(band.max())
    return band > (lo + 0.55 * (hi - lo))


def map_mask_distance(cur, ref):
    """Symmetric difference over union of the two text masks, best over +-3 px of shift."""
    if cur.shape != ref.shape:
        return 1e9
    a, b = map_text_mask(cur), map_text_mask(ref)
    best = 1.0
    for dx in range(-3, 4):
        c = np.roll(a, dx, axis=1)
        u = int((c | b).sum())
        if u:
            best = min(best, float((c ^ b).sum()) / float(u))
    return best


def map_scan(sh, presses=26, tag="mapscan"):
    """Walk AVAILABLE MAPS one DOWN at a time, capturing every screen.

    Costs one single-instance login and NO match launch, and it is what makes a verified map
    selection possible: the reference crop for a map is cut from this scan's own captures.
    The list as scanned on 2026-09-13, in order: Medley, Random, VIGILANCE, THE MIXER, FOXHUNT,
    SUJO, ENOWAPI, SHADOW FALLS, FISH HOOK, CROSSROADS, SANDSTORM, CHAIN REACTION, GUIDANCE,
    REQUIEM, BLIZZARD, **FROSTFIRE**, ABANDONED, DESERT GLORY, NIGHT STALKER, RAT'S NEST,
    BITTER JUNGLE, BLOOD LAKE, DEATH TRAP, THE RUINS.
    """
    seen = []
    for k in range(presses + 1):
        im = winshot.grab(sh.hwnd)
        im.save(os.path.join(sh.out, f"{sh.tag}{tag}_{k:02d}.png"))
        cur = map_cursor(sh, im)
        seen.append(cur)
        sh.log(f"map scan {k:02d}: highlighted row {cur}")
        if k < presses:
            sh.pad_press("down", wait=0.5)
    return seen


def map_ref_path(name):
    return os.path.join(MAP_REF_DIR, f"map_{name.lower()}.png")


@staged("map_select")
def choose_map(sh, name, presses=30):
    """Select `name` in AVAILABLE MAPS, VERIFYING the highlighted row before pressing CROSS.

    A blind index that silently lands on the wrong map produces a whole class of runs whose
    position rows mean nothing -- and the mined waypoint corridor is map-specific, so the harness
    has to KNOW which map it is on rather than assume. Returns the row index it accepted; raises
    SystemExit with a capture if the map is never highlighted.
    """
    ref_path = map_ref_path(name)
    if not os.path.exists(ref_path):
        raise SystemExit(f"{sh.tag}no reference for map '{name}' at {ref_path} -- run the map scan "
                         f"(--only A --map-scan 26) once and cut the highlighted row from its "
                         f"captures; accepting whatever is highlighted is not an option")
    ref = np.asarray(Image.open(ref_path).convert("L"), dtype=np.float32)
    for k in range(presses + 1):
        im = winshot.grab(sh.hwnd)
        cur = map_cursor(sh, im)
        if cur >= 0:
            d = map_mask_distance(map_rows(im)[cur], ref)
            if d <= MAP_MATCH_THRESH:
                sh.log(f"map '{name}' highlighted at row {cur} after {k} DOWN (text-mask distance "
                       f"{d:.3f} <= {MAP_MATCH_THRESH}) -- accepting")
                sh.shot(f"14b_map_{name.lower()}")
                press_map_cross_verified(sh, 4.0)                # R47: re-sent while SELECTED MAPS does not move
                return cur
            if k % 5 == 0:
                sh.log(f"map search {k:02d}: row {cur} is not '{name}' (distance {d:.3f})")
        else:
            sh.log(f"map search {k:02d}: no highlighted row -- pressing on")
        sh.pad_press("down", wait=0.45)
    sh.shot(f"14_map_{name.lower()}_NOT_FOUND")
    raise lobby_fail(sh, CLASS_MAP_SEARCH, f"map '{name}' was never highlighted in {presses} presses of DOWN -- "
                     f"see the capture. Accepting whatever is highlighted would put the run on an "
                     f"unknown map, and the whole point of this check is that it cannot.")


def open_choose_games(sh, game_name="test"):
    """Briefing room -> CREATE GAME -> game name -> CHOOSE GAMES. Split out of `host_game` so the
    map scan can reach the list without creating a world.

    Every press is verified on a fresh frame and re-sent (press_verified); the class names the press.
    research/28 §3: wtb3 and kill6 lost the CROSS into CREATE GAME (12_create_game still BRIEFING ROOM),
    wtb3's cursor then drifted to RANK RESTRICTIONS, cal1 typed the up/down/cross presses into the
    name keyboard."""
    press_verified(sh, "create-game:select", "up", 2.0,
                   lambda g: lobby_row_lit(g, "create_game"), "the CREATE GAME row lit")
    press_verified(sh, "create-game:enter", "cross", 6.0,
                   lambda g: lobby_title_is(g, "create_game"), "the CREATE GAME screen")
    sh.shot("12_create_game")
    press_verified(sh, "create-game:name-keyboard", "cross", 5.0, osk_open_of, "the game-name keyboard")
    sh.type(game_name)
    sh.shot("13_game_name")
    press_verified(sh, "create-game:choose-games-select", "up", 2.5,
                   lambda g: lobby_row_lit(g, "choose_games"), "the CHOOSE GAMES row lit")
    press_verified(sh, "create-game:choose-games", "cross", 6.0,
                   lambda g: lobby_title_is(g, "play_list"), "the CREATE GAME PLAY LIST screen")
    sh.shot("14_choose_games")


@staged("host")
def host_game(sh, game_name="test", game_map="frostfire"):
    # The default is the owner's default map and matches online_match_ours --map. Both Frostfire
    # and Medley have a committed reference (scripts/parity/refs/map_<name>.png); any other map
    # aborts in choose_map until one is cut from a map scan.
    open_choose_games(sh, game_name)
    row = choose_map(sh, game_map)                               # VERIFIED, not a blind CROSS
    sh.log(f"map list: accepted '{game_map}' at row {row}")
    # kill4, kill7 and 8b: 15_play_list still showed the play list (the ACCEPT was eaten), so the CREATE
    # SQUARE landed on a menu with an empty PLAY LIST and the lobby never appeared (band distance 0.521).
    press_verified(sh, "create-game:accept", "square", 5.0,
                   lambda g: lobby_title_is(g, "create_game"), "CREATE GAME with the play list accepted")
    sh.shot("15_play_list")
    press_verified(sh, "create-game:create", "square", 25.0,
                   lambda g: lobby_title_is(g, "game_lobby"), "the GAME LOBBY")
    sh.shot("16_game_lobby")
    press_verified(sh, "create-game:continue", "cross", 4.0,
                   lambda g: not lobby_notice_up(g), "the 30 s notice dismissed")
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


@staged("join")
def join_game(sh, switch=True):
    # join:list -- JOIN GAME activates the games list and highlights the host's game; "There are no games
    # to join." (wtb3/wtb5's B, whose host never created the world) leaves the row dark, and the re-sends
    # give the host up to 3 x 8 s more. join:enter -- launch1/1b's CROSS on the game left the list on
    # screen (band distance 0.577) although Medius had answered the join (research/21 §6.1).
    press_verified(sh, "join:list", "cross", 8.0,
                   lambda g: lobby_row_lit(g, "games_list"), "a game highlighted in the games list")
    sh.shot("12_games_list")
    press_verified(sh, "join:enter", "cross", 25.0,
                   lambda g: lobby_title_is(g, "game_lobby"), "the GAME LOBBY")
    sh.shot("16_game_lobby")
    press_verified(sh, "join:continue", "cross", 3.0,
                   lambda g: not lobby_notice_up(g), "the 30 s notice dismissed")
    sh.shot("17_game_lobby_ok")
    require_game_lobby(sh, "JOIN GAME")
    sh.log(f"teams (seals, terrorists text px) {lobby_teams(sh)}")
    if switch:                                                   # a joiner is auto-assigned to the other team
        lobby_select(sh, 1, "SWITCH TEAMS")
        sh.press("cross", 4.0)
        sh.shot("18_switched")
        sh.log(f"teams after switch {lobby_teams(sh)}")


@staged("ready")
def ready(sh):
    lobby_select(sh, 2, "READY")                                 # menu: ARMORY, SWITCH TEAMS, READY
    sh.press("cross", 3.0)

    def pair():
        """Two fresh frames READY_CONFIRM_GAP_S apart -> 'dropped' (both READY), 'taken' (neither), 'unsure'."""
        edges = []
        for k in range(2):
            if k:
                sh.stage_sleep(READY_CONFIRM_GAP_S)
            edges.append(ready_label_edge(lobby_gray(sh)))
        sh.log(f"READY check: row-2 label right edges {edges} (READY ~48, NOT READY ~82)")
        flags = [e is not None and e <= READY_EDGE_DROPPED_MAX for e in edges]
        return "dropped" if all(flags) else "taken" if not any(flags) else "unsure"

    def dropped():
        # R69: READY is a toggle row, so a re-send on a late registration un-readies it. Press only when
        # both frames still read READY; on disagreement wait and re-check once, never press.
        state = pair()
        if state == "unsure":
            sh.stage_sleep(READY_CONFIRM_GAP_S)
            state = pair()
        if state == "unsure":
            raise lobby_fail(sh, CLASS_READY, "READY label frames disagree twice -- not pressing a toggle blind")
        return state == "dropped"

    def resend():
        lobby_select(sh, 2, "READY")
        lobby_resend_cross(sh, 3.0)

    verify_resend(sh, CLASS_READY, dropped, resend)             # R47: re-sent while READY still shows
    sh.shot("19_ready")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="socomc")
    ap.add_argument("--password", default="socom")
    ap.add_argument("--out", default="logs/parity/ours_host")
    ap.add_argument("--seconds", type=int, default=500)
    ap.add_argument("--hold", type=int, default=30)
    ap.add_argument("--existing", action="store_true", help="the persona is already on the memory card")
    ap.add_argument("--host", action="store_true", help="after the briefing room: CREATE GAME (Frostfire, verified)")
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
        sh.log(f"LOBBY class={CLASS_OK}")
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
