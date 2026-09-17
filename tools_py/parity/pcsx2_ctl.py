"""Stepwise control of the two PCSX2 SOCOM II instances (Sprint 4 Task 5's logs/s4_ctl.py, promoted for Sprint 6
Task 7's mixed match). One command per invocation, so a screen can be looked at before the next press, plus two
macros that play research/18 section 1's click path with its timings:

  python -m tools_py.parity.pcsx2_ctl launch A [--state N]
  python -m tools_py.parity.pcsx2_ctl shot   A <label>
  python -m tools_py.parity.pcsx2_ctl press  A cross[,down,...] [--wait 2.0] [--hold 0.15]
  python -m tools_py.parity.pcsx2_ctl hold   A W 3.0
  python -m tools_py.parity.pcsx2_ctl type   A socomb
  python -m tools_py.parity.pcsx2_ctl watch  A <label> <count> <interval>
  python -m tools_py.parity.pcsx2_ctl join   B --name socomq [--game test]      # boot -> login -> join the game -> READY
  python -m tools_py.parity.pcsx2_ctl host   A --name socomp [--game test]      # boot -> login -> create the game
  python -m tools_py.parity.pcsx2_ctl ready  A                                  # READY in the lobby (the host, once the joiner is in)
  python -m tools_py.parity.pcsx2_ctl kill

Instances: A = tools/pcsx2 (PINE 28011, retail pnach), B = tools/pcsx2_b (PINE 28012, clientB pnach with the
3658->3660 UDP shift). Windows are pinned topmost and placed side by side so PrintWindow's desktop fallback never
grabs the other one. The macros need the DNS stub (`tools_py.parity.dns_stub`, which binds and answers
SOCOM_SERVER_IP -- see scripts/parity/env.sh), the Horizon stack, and a card carrying a network configuration
(research/18 section 1 c).
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time

from tools_py.parity import keys, winshot
from tools_py.parity.online_login import osk_type

user32 = ctypes.windll.user32 if os.name == "nt" else None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ISO = os.path.join(ROOT, "game", "SOCOM II - U.S. Navy SEALs (USA).iso")
OUT = os.path.join(ROOT, "logs", "parity", "s4_pcsx2")
STATE = os.path.join(ROOT, "logs", "s4_instances.json")
INSTANCES = {
    "A": {"exe": os.path.join(ROOT, "tools", "pcsx2", "pcsx2-qt.exe"), "pos": (0, 0)},
    "B": {"exe": os.path.join(ROOT, "tools", "pcsx2_b", "pcsx2-qt.exe"), "pos": (700, 0)},
}
# PCSX2 [Pad1] binds the analog sticks too; keys.py's pcsx2 map only carries the digital buttons.
keys.MAPS["pcsx2"].update({
    "LUP": 0x57, "LDOWN": 0x53, "LLEFT": 0x41, "LRIGHT": 0x44,      # left stick  W S A D
    "RUP": 0x54, "RDOWN": 0x47, "RLEFT": 0x46, "RRIGHT": 0x48,      # right stick T G F H
    "L3": 0x32, "R3": 0x34,
})

# research/18 section 1 e, the click path, as (kind, arg, wait_s) steps. `press` = a button; `type` = the
# on-screen keyboard; `shot` = a capture with that label; `wait` = seconds.
BOOT_TO_LOGIN = [
    ("wait", None, 90.0),                                   # cold boot to the first menu
    ("press", "cross", 5.0), ("press", "cross", 5.0), ("press", "cross", 5.0), ("press", "cross", 5.0),
    ("shot", "01_main_menu", 0.0),
    ("press", "down", 2.0), ("press", "cross", 6.0),         # LOGIN TO SOCOM II ONLINE, "Setting 1"
    ("shot", "02_login", 0.0),
]


def login_steps(name):
    return [
        ("press", "cross", 30.0),                            # SELECT UNIVERSE "SOCOM II Local"
        ("press", "cross", 25.0),                            # CONNECT TO SOCOM II
        ("press", "cross", 4.0),                             # persona list
        ("press", "cross", 4.0),                             # <New Persona>
        ("type", name, 3.0),
        ("press", "down", 1.5), ("press", "cross", 3.0),
        ("type", name, 3.0),                                 # password = name
        ("press", "down", 1.0), ("press", "down", 1.0), ("press", "down", 1.0), ("press", "down", 1.0),
        ("press", "cross", 12.0),                            # CONNECT
        ("press", "cross", 4.0),                             # write-your-name notice
        ("press", "right", 1.5), ("press", "cross", 4.0),    # save to card: NO
        ("press", "cross", 12.0),                            # ACCEPT the user agreement -> lobby
        ("shot", "03_lobby", 0.0),
        ("press", "cross", 4.0),                             # close SERVER NEWS
        ("press", "down", 1.5), ("press", "cross", 8.0),     # BRIEFING ROOMS
        ("press", "cross", 12.0),                            # join Channel 1
        ("shot", "04_briefing_room", 0.0),
    ]


def host_steps(game):
    return [
        ("press", "up", 1.5), ("press", "cross", 4.0),       # CREATE GAME
        ("press", "cross", 3.0), ("type", game, 3.0),
        ("press", "up", 1.5), ("press", "cross", 4.0),       # CHOOSE GAMES
        ("press", "cross", 3.0),                             # the first map
        ("press", "square", 5.0),                            # ACCEPT PLAY LIST
        ("press", "square", 30.0),                           # CREATE GAME
        ("press", "cross", 4.0),                             # CONTINUE on the 30 s notice
        ("shot", "05_game_lobby", 0.0),
    ]


JOIN_STEPS = [
    ("press", "cross", 3.0),                                 # activate the games list
    ("press", "cross", 30.0),                                # join the first game
    ("shot", "05_game_lobby", 0.0),
]

READY_STEPS = [
    ("press", "down", 1.5), ("press", "down", 1.5),          # ARMORY -> SWITCH TEAMS -> READY
    ("press", "cross", 3.0),
    ("shot", "06_ready", 0.0),
]


def plan(macro, name="socomq", game="test"):
    """The step list a macro plays. `join`: boot, log in as `name`, join the first game in the briefing room,
    READY. `host`: boot, log in, create `game`. `ready`: READY in the lobby."""
    if macro == "join":
        return BOOT_TO_LOGIN + login_steps(name) + JOIN_STEPS + READY_STEPS
    if macro == "host":
        return BOOT_TO_LOGIN + login_steps(name) + host_steps(game)
    if macro == "ready":
        return READY_STEPS
    raise ValueError(macro)


def _load():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def _save(d):
    json.dump(d, open(STATE, "w"))


def _hwnd(tag):
    d = _load()
    if tag not in d:
        raise SystemExit(f"{tag}: not launched (no entry in {STATE})")
    hwnd = winshot.find_window(keys.WINDOW_TITLES["pcsx2"], pid=d[tag]["pid"])
    if hwnd is None:
        raise SystemExit(f"{tag}: no window for pid {d[tag]['pid']}")
    return hwnd


def _place(hwnd, pos):
    outer = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(outer))
    user32.MoveWindow(hwnd, pos[0], pos[1], outer.right - outer.left, outer.bottom - outer.top, True)
    winshot.keep_on_top(hwnd)


def cmd_launch(a):
    inst = INSTANCES[a.tag]
    argv = [inst["exe"], "-batch", "-nogui", "-fastboot"]
    if a.state:
        argv += ["-state", a.state]
    argv.append(ISO)
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    hwnd, t0 = None, time.time()
    while hwnd is None and time.time() - t0 < 120:
        hwnd = winshot.find_window(keys.WINDOW_TITLES["pcsx2"], pid=proc.pid)
        time.sleep(1)
    if hwnd is None:
        raise SystemExit(f"{a.tag}: no window after 120 s")
    d = _load()
    d[a.tag] = {"pid": proc.pid, "t0": time.time()}
    _save(d)
    time.sleep(6)
    _place(hwnd, inst["pos"])
    client = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client))
    print(f"{a.tag}: pid {proc.pid} hwnd {hwnd} client {client.right}x{client.bottom}", flush=True)


def _shot(tag, label, out=None):
    out = out or OUT
    os.makedirs(out, exist_ok=True)
    hwnd = _hwnd(tag)
    winshot.keep_on_top(hwnd)
    path = os.path.join(out, f"{tag}_{label}.png")
    winshot.capture(hwnd).save(path)
    print(path, flush=True)
    return path


def cmd_shot(a):
    _shot(a.tag, a.label, a.out)


def cmd_press(a):
    hwnd = _hwnd(a.tag)
    for b in a.buttons.split(","):
        keys.press(hwnd, b.strip(), "pcsx2", hold_s=a.hold)
        time.sleep(a.wait)
    print(f"{a.tag}: pressed {a.buttons} (hold {a.hold}s, wait {a.wait}s each)", flush=True)


def cmd_hold(a):
    hwnd = _hwnd(a.tag)
    keys.press(hwnd, a.button, "pcsx2", hold_s=a.secs)
    print(f"{a.tag}: held {a.button} for {a.secs}s", flush=True)


def cmd_type(a):
    hwnd = _hwnd(a.tag)
    osk_type(hwnd, a.text, target="pcsx2")
    print(f"{a.tag}: typed {a.text}", flush=True)


def cmd_watch(a):
    for i in range(a.count):
        _shot(a.tag, f"{a.label}{i:02d}", a.out)
        time.sleep(a.interval)


def run_steps(tag, steps, out=None, log=print):
    """Play a macro's steps on an instance, one screenshot per `shot` step."""
    for kind, arg, wait_s in steps:
        if kind == "press":
            keys.press(_hwnd(tag), arg, "pcsx2", hold_s=0.15)
            log(f"{tag}: {arg} (then {wait_s:g}s)")
        elif kind == "type":
            osk_type(_hwnd(tag), arg, target="pcsx2")
            log(f"{tag}: typed {arg}")
        elif kind == "shot":
            _shot(tag, arg, out)
        elif kind == "wait":
            log(f"{tag}: wait {wait_s:g}s")
        if wait_s:
            time.sleep(wait_s)


def cmd_macro(a):
    run_steps(a.tag, plan(a.cmd, name=a.name, game=a.game), a.out)
    print(f"{a.tag}: {a.cmd} done", flush=True)


def cmd_kill(a):
    subprocess.run(["taskkill", "/F", "/IM", "pcsx2-qt.exe"], capture_output=True)
    if os.path.exists(STATE):
        os.remove(STATE)
    print("killed all pcsx2-qt.exe", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("launch"); p.add_argument("tag", choices=("A", "B")); p.add_argument("--state")
    p.set_defaults(fn=cmd_launch)
    p = sub.add_parser("shot"); p.add_argument("tag"); p.add_argument("label"); p.add_argument("--out"); p.set_defaults(fn=cmd_shot)
    p = sub.add_parser("press"); p.add_argument("tag"); p.add_argument("buttons")
    p.add_argument("--wait", type=float, default=2.0); p.add_argument("--hold", type=float, default=0.15); p.set_defaults(fn=cmd_press)
    p = sub.add_parser("hold"); p.add_argument("tag"); p.add_argument("button"); p.add_argument("secs", type=float); p.set_defaults(fn=cmd_hold)
    p = sub.add_parser("type"); p.add_argument("tag"); p.add_argument("text"); p.set_defaults(fn=cmd_type)
    p = sub.add_parser("watch"); p.add_argument("tag"); p.add_argument("label"); p.add_argument("count", type=int)
    p.add_argument("interval", type=float); p.add_argument("--out"); p.set_defaults(fn=cmd_watch)
    for macro in ("join", "host", "ready"):
        p = sub.add_parser(macro); p.add_argument("tag", choices=("A", "B")); p.add_argument("--name", default="socomq")
        p.add_argument("--game", default="test"); p.add_argument("--out"); p.set_defaults(fn=cmd_macro)
    p = sub.add_parser("kill"); p.set_defaults(fn=cmd_kill)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
