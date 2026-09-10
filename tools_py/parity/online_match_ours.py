"""Two instances of OUR exe play a match on the local Horizon stack: A logs in and hosts a game
(Medley), B logs in, joins it and switches team, both press READY -> the match launches
(mirrors online_match.py, the PCSX2 two-client reference). Screens land in --out as A_*/B_*.

Instance B runs with its own window title, memory card dir (game/disc/mc0_b) and UDP port shift
(see online_login_ours.INSTANCES). Personas: A = --name-a (default socomc, saved on mc0),
B = --name-b (default socome; created on first use unless --existing-b).

Usage: python -m tools_py.parity.online_match_ours [--hold 120] [--out logs/parity/ours_match]
"""
import argparse
import os
import subprocess
import threading
import time

from . import online_login_ours as L


class Client:
    def __init__(self, tag, out, name, existing, seconds):
        self.tag, self.out, self.name, self.existing, self.seconds = tag, out, name, existing, seconds
        self.proc = self.sh = None
        self.error = None

    def launch(self):
        self.proc, self.title = L.launch(self.seconds, self.tag)

    def login(self):
        try:
            self.sh = L.attach(self.proc, self.title, self.out, self.tag + "_", L.INSTANCES[self.tag]["PS2X_SOCOM2_INPUT_FILE"])
            L.boot_to_online(self.sh)
            L.login(self.sh, self.name, "socom", self.existing)
            L.to_briefing_room(self.sh)
        except BaseException as e:      # noqa: BLE001 - surfaced by the caller
            self.error = e

    def kill(self):
        if self.proc:
            self.proc.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=int, default=120)
    ap.add_argument("--out", default="logs/parity/ours_match")
    ap.add_argument("--seconds", type=int, default=700)
    ap.add_argument("--name-a", default="socomc")
    ap.add_argument("--name-b", default="socome")
    ap.add_argument("--existing-b", action="store_true")
    ap.add_argument("--only", default="", help="A or B: run one instance's login only (setup check)")
    ap.add_argument("--play", type=int, default=0, help="gameplay bursts after the hold (A walks + fires, B turns)")
    ap.add_argument("--same-team", action="store_true", help="B switches to SEALs (the joiner is auto-assigned to TERRORISTS); teammates spawn together")
    ap.add_argument("--sweep", type=int, default=0, help="gameplay: A turns in place in <N> steps of --sweep-hold s firing a burst at each; B stands")
    ap.add_argument("--sweep-hold", type=float, default=0.5)
    ap.add_argument("--host-switch", action="store_true", help="A (host) switches team after B joined (the joiner is auto-assigned opposite the host; the joiner's lobby cursor does not move)")
    ap.add_argument("--probe", action="store_true", help="gameplay: A tries every stick direction and the stance buttons with screens after each (input probe)")
    ap.add_argument("--turn-key", default="L", help="L = right stick right (Precision Shooter look), D = left stick right (Sure Shot turn)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower().count("socom2.exe"):
        raise SystemExit("socom2.exe is already running")
    A = Client("A", a.out, a.name_a, True, a.seconds)
    B = Client("B", a.out, a.name_b, a.existing_b, a.seconds)
    if a.only:
        c = A if a.only == "A" else B
        try:
            c.launch()
            c.login()
            if c.error:
                raise c.error
            c.sh.shot("done")
        finally:
            c.kill()
        return
    try:
        A.launch()
        time.sleep(6)
        B.launch()
        tA = threading.Thread(target=A.login)
        tB = threading.Thread(target=B.login)
        tA.start()
        time.sleep(5)
        tB.start()
        tA.join()
        tB.join()
        for c in (A, B):
            if c.error:
                raise c.error
        L.host_game(A.sh)
        L.join_game(B.sh, switch=a.same_team and not a.host_switch)   # the joiner is auto-assigned to the other team
        if a.host_switch:
            A.sh.log(f"teams before host switch {L.lobby_teams(A.sh)}")
            L.lobby_select(A.sh, 1, "SWITCH TEAMS")
            A.sh.press("cross", 4.0)
            A.sh.shot("18_host_switched")
            A.sh.log(f"teams after host switch {L.lobby_teams(A.sh)}")
        time.sleep(35)                                           # READY becomes available
        L.ready(A.sh)
        L.ready(B.sh)
        for i in range(a.hold // 10):
            time.sleep(10)
            A.sh.shot(f"hold{i:02d}")
            B.sh.shot(f"hold{i:02d}")
        if a.play:
            # Gameplay phase (the user's acceptance test): A hunts, B stands. A walks forward in
            # bursts and fires; B turns slowly so both sides render each other. Screens every
            # burst on both sides; the kill/round end is read from the HUD captures and the DME log.
            for i in range(a.play):
                A.sh.hold("W", 3.0)
                A.sh.hold("R1", 0.3)
                A.sh.hold("R1", 0.3)
                B.sh.hold("L", 0.6)
                A.sh.shot(f"play{i:02d}")
                B.sh.shot(f"play{i:02d}")
        if a.probe:
            # Each stick direction for 3 s with 2 s of rest, twice (posted keys are sometimes
            # dropped); the position rows ([peek] @416054, 1/s) give the displacement per key.
            for i, (key, secs) in enumerate([("K", 3.0), ("I", 3.0), ("J", 3.0), ("L", 3.0), ("W", 3.0), ("S", 3.0), ("A", 3.0), ("D", 3.0)] * 2):
                A.sh.hold(key, secs)
                A.sh.log(f"probe {i:02d} {key} {secs}s")
                time.sleep(2.0)
                A.sh.shot(f"probe{i:02d}_{key}")
                B.sh.shot(f"probe{i:02d}")
        if a.sweep:
            # Same-team kill probe: A rotates in place (right stick) and fires a burst at every
            # step; B stands where it spawned (a few metres from A when both are SEALs).
            for i in range(a.sweep):
                A.sh.hold(a.turn_key, a.sweep_hold)
                A.sh.hold("R1", 0.4)
                A.sh.hold("R1", 0.4)
                A.sh.shot(f"sweep{i:02d}")
                B.sh.shot(f"sweep{i:02d}")
    finally:
        A.kill()
        B.kill()
        subprocess.run(["taskkill", "/F", "/IM", "socom2.exe"], capture_output=True)


if __name__ == "__main__":
    main()
