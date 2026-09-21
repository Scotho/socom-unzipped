"""Sprint 10 Goal 3: the console side of the mixed match pressing on what its screen shows.

The first leg (2026-09-17) drove PCSX2 with fixed timings (`pcsx2_ctl`'s macros) and lost its place at boot: the
cold boot was faster than the recipe's 90 s and four blind CROSS presses walked into NEW GAME (KNOWN section 2).
Ours had long stopped pressing blind -- `online_login_ours` reads every screen back through a `Shell` and re-sends
what was dropped. This is that Shell over a PCSX2 window: the same staged steps (boot_to_online, login,
to_briefing_room, host_game / join_game, ready), the same detectors, the same failure classes; only the keys map
(PCSX2's [Pad1] keyboard bindings), the press hold and the window differ. The client area is pinned to 640x448 --
PCSX2's frame is then the game's frame at the harness's geometry (the parity gate has driven PCSX2 that way since
Sprint 4), so every fixed-box detector reads the console's screens exactly as it reads ours.

    python -m tools_py.parity.pcsx2_shell login B --name socomq --out logs/parity/mixed2/pcsx2     # boot -> login -> briefing room
    python -m tools_py.parity.pcsx2_shell host  A --name socomp --game test --out ...              # ... -> CREATE GAME (Frostfire) -> lobby
    python -m tools_py.parity.pcsx2_shell join  B --name socomq --out ...                           # ... -> JOIN GAME -> lobby (switch teams)
    python -m tools_py.parity.pcsx2_shell ready B --out ...                                         # READY in the lobby (an attached instance)

The instance must have been launched by `pcsx2_ctl launch <A|B>` (the pnach, the card with a network configuration,
the DNS stub and the Horizon stack are research/18 section 1's; `scripts/parity/mixed_match.sh` sets them up).
`--existing` says the persona is already on the card, as for ours. Every step logs
`[lobby] <step> press=<btn> verified=<bool> attempt=<n>` and a miss ends in `RESULT LOBBY-FAIL <class>`, exit 4,
exactly as ours' harness does -- one taxonomy for both sides of the match.
"""
import argparse
import os
import sys
import time

from tools_py.parity import online_login_ours as L
from tools_py.parity import pcsx2_ctl, winshot


class Pcsx2Shell(L.Shell):
    target = "pcsx2"
    press_hold_s = 0.15          # pcsx2_ctl's press: the console shell reads a 9-frame hold as one press

    def __init__(self, hwnd, out, t0, tag=""):
        super().__init__(hwnd, out, t0, tag, pad_file=None)


def attach(tag, out, t0=None):
    """The shell over the PCSX2 window `pcsx2_ctl launch <tag>` opened: topmost, client 640x448, the first frame read."""
    hwnd = pcsx2_ctl._hwnd(tag)
    winshot.keep_on_top(hwnd)
    winshot.ensure_client_size(hwnd)
    sh = Pcsx2Shell(hwnd, out, t0 or time.time(), f"{tag}_")
    sh.last = None
    return sh


def run(macro, tag, out, name, password, existing, game, game_map):
    os.makedirs(out, exist_ok=True)
    sh = attach(tag, out)
    if macro in ("login", "host", "join"):
        L.boot_to_online(sh)
        L.login(sh, name, password, existing)
        L.to_briefing_room(sh)
        if macro == "host":
            L.host_game(sh, game, game_map)
        elif macro == "join":
            L.join_game(sh)
    elif macro == "ready":
        L.ready(sh)
    else:
        raise SystemExit(f"unknown macro {macro!r}")
    sh.log(f"LOBBY class={L.CLASS_OK}")
    sh.shot("final")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("macro", choices=("login", "host", "join", "ready"))
    ap.add_argument("tag", choices=("A", "B"))
    ap.add_argument("--name", default="socomq")
    ap.add_argument("--password", default="")
    ap.add_argument("--out", default="logs/parity/pcsx2_shell")
    ap.add_argument("--existing", action="store_true", help="the persona is already on the memory card")
    ap.add_argument("--game", default="test")
    ap.add_argument("--map", default="frostfire")
    a = ap.parse_args(argv)
    try:
        return run(a.macro, a.tag, a.out, a.name, a.password or a.name, a.existing, a.game, a.map)
    except L.LobbyFail as e:
        return e.code        # the RESULT and class lines were logged where it was raised (lobby_fail)


if __name__ == "__main__":
    sys.exit(main())
