"""Per-app audio session volume on the render endpoint: list it, or hold one exe's session at full volume and
unmuted while it runs.

Why: the WASAPI loopback that `audio_parity` records sits AFTER the per-app session volume Windows remembers for
each exe on each endpoint, so a capture of ours or of PCSX2 inherits whatever that slider was last left at (music
round four, 2026-09-20: ours read ~31 dB under PCSX2 across the whole capture, menu clicks included, with the JBL
endpoint's per-app sliders moved). `hold` pins the launched game's session to 1.0 / unmuted the moment its session
appears and logs what it found first, so a level difference between two captures is the game's, not the mixer's.

    python -m tools_py.parity.app_volume list
    python -m tools_py.parity.app_volume hold socom2.exe --seconds 600 [--volume 1.0]

pycaw (COM) is imported lazily: the pure decision `plan_changes` is testable anywhere."""
import argparse
import sys
import time


def plan_changes(sessions, exe, volume=1.0):
    """Which of `sessions` (objects with .name, .volume, .mute) belonging to `exe` need a change -> list of
    (session, set_volume or None, unmute: bool). Names compare case-insensitively; nothing for other apps."""
    out = []
    want = exe.lower()
    for s in sessions:
        if (s.name or "").lower() != want:
            continue
        set_vol = volume if abs(float(s.volume) - float(volume)) > 0.005 else None
        unmute = bool(s.mute)
        if set_vol is not None or unmute:
            out.append((s, set_vol, unmute))
    return out


class _Session:
    """A thin view over a pycaw session: name, volume, mute, and setters."""

    def __init__(self, raw):
        self.raw = raw
        self.name = raw.Process.name() if raw.Process else "(system)"
        self.simple = raw.SimpleAudioVolume

    @property
    def volume(self):
        return float(self.simple.GetMasterVolume())

    @property
    def mute(self):
        return bool(self.simple.GetMute())

    def set_volume(self, v):
        self.simple.SetMasterVolume(float(v), None)

    def unmute(self):
        self.simple.SetMute(False, None)


def live_sessions():
    from pycaw.pycaw import AudioUtilities   # COM, Windows only
    return [_Session(s) for s in AudioUtilities.GetAllSessions()]


def cmd_list():
    for s in live_sessions():
        print(f"{s.name:24s} vol {s.volume:.2f} mute {int(s.mute)}")
    return 0


def cmd_hold(exe, seconds, volume, poll_s=0.5, log=print):
    """Poll for `seconds`; each time exe's session is seen off `volume` or muted, fix it. Logs the FIRST reading
    (the evidence) and every change. Returns the number of changes made."""
    t0 = time.time()
    seen_first = False
    changes = 0
    while time.time() - t0 < seconds:
        try:
            sessions = live_sessions()
        except Exception as e:   # COM hiccup while the app starts or exits: try again
            log(f"t+{time.time()-t0:5.1f}s sessions unreadable: {e}")
            time.sleep(poll_s)
            continue
        mine = [s for s in sessions if (s.name or "").lower() == exe.lower()]
        if mine and not seen_first:
            seen_first = True
            for s in mine:
                log(f"t+{time.time()-t0:5.1f}s {exe} session first seen: vol {s.volume:.2f} mute {int(s.mute)}")
        for s, set_vol, unmute in plan_changes(sessions, exe, volume):
            if set_vol is not None:
                s.set_volume(set_vol)
            if unmute:
                s.unmute()
            changes += 1
            log(f"t+{time.time()-t0:5.1f}s {exe} session set: vol {set_vol if set_vol is not None else 'kept'} "
                f"unmute {int(unmute)}")
        time.sleep(poll_s)
    log(f"hold done: {changes} change(s), session {'seen' if seen_first else 'NEVER seen'}")
    return changes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    h = sub.add_parser("hold")
    h.add_argument("exe")
    h.add_argument("--seconds", type=float, default=600.0)
    h.add_argument("--volume", type=float, default=1.0)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        return cmd_list()
    cmd_hold(a.exe, a.seconds, a.volume, log=lambda m: print(m, flush=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
