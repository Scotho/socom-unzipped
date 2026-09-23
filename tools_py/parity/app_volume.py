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
from dataclasses import dataclass
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


# ---- the session monitor (Sprint 11 audio-out, fix round 1 I5) --------------------------------------------------
#
# `list` cannot prove or disprove that another application contaminated an endpoint capture: pycaw's
# GetAllSessions returns inactive and expired sessions too, so a name in the list means only that a session object
# exists. What proves rendering is the session STATE (1 = active) together with its PEAK METER (IAudioMeterInformation,
# the level the engine saw from that session in the last period), sampled through the capture rather than at its two
# ends. `monitor` writes that timeline as CSV (t_s,name,state,peak); `contamination` reads it back.

PEAK_FLOOR = 0.001   # a peak under this is digital silence for the purpose of "was it rendering"

# The meter is per session, but the loopback RECORDER is a session too: its capture stream on the render endpoint
# reports the endpoint's own mix as its peak (verified 2026-09-23: the recorder's python session read exactly
# chrome.exe's peak while the game was silent, and chrome + the game once it played). So the recorder is excluded
# from the verdict by its process id -- loopback_record.py prints `pid=` for that -- never by its name, which would
# also excuse any other python that rendered.


@dataclass
class Sample:
    t_s: float
    name: str
    pid: int
    state: int
    peak: float


@dataclass
class Foreign:
    name: str
    first_s: float
    last_s: float
    samples: int
    peak: float


def format_samples(t_s, sessions):
    """One CSV row per session: t_s,name,pid,state,peak."""
    return [f"{t_s:.1f},{s.name},{int(getattr(s, 'pid', 0))},{int(s.state)},{float(s.peak):.4f}" for s in sessions]


def parse_samples(text):
    """Rows of a monitor CSV; the four-column form (before the pid column) is read with pid 0."""
    rows = []
    for line in text.splitlines():
        if not line or line.startswith("t_s,") or line.startswith("#"):
            continue
        parts = line.split(",")
        try:
            if len(parts) == 5:
                rows.append(Sample(float(parts[0]), parts[1], int(parts[2]), int(parts[3]), float(parts[4])))
            elif len(parts) == 4:
                rows.append(Sample(float(parts[0]), parts[1], 0, int(parts[2]), float(parts[3])))
        except ValueError:
            continue
    return rows


def contamination(rows, allowed, peak_floor=PEAK_FLOOR, ignore_pids=()):
    """The sessions outside `allowed` (case-insensitive) and outside `ignore_pids` (the recorder's own process)
    that were ACTIVE with a peak above the floor in at least one sample: name, first and last such sample time,
    how many, and the loudest peak. Empty means the timeline shows nothing but the allowed sessions rendering --
    which is what a device measurement needs."""
    allowed_l = {a.lower() for a in allowed}
    ignored = {int(p) for p in ignore_pids}
    found = {}
    for r in rows:
        if r.name.lower() in allowed_l or r.pid in ignored or r.state != 1 or r.peak <= peak_floor:
            continue
        f = found.get(r.name)
        if f is None:
            found[r.name] = Foreign(r.name, r.t_s, r.t_s, 1, r.peak)
        else:
            f.last_s = max(f.last_s, r.t_s)
            f.samples += 1
            f.peak = max(f.peak, r.peak)
    return sorted(found.values(), key=lambda f: f.first_s)


def _session_state_and_peak(raw):
    """(state, peak) for a pycaw session; peak 0.0 when the meter interface is unavailable."""
    state = -1
    try:
        state = int(raw.State)
    except Exception:
        pass
    peak = 0.0
    try:
        from pycaw.pycaw import IAudioMeterInformation
        meter = raw._ctl.QueryInterface(IAudioMeterInformation)
        peak = float(meter.GetPeakValue())
    except Exception:
        pass
    return state, peak


def cmd_monitor(seconds, interval_s, out, log=print):
    """Sample every session's state and peak every `interval_s` for `seconds`, appending CSV rows to `out`."""
    from pycaw.pycaw import AudioUtilities   # COM, Windows only

    class S:
        def __init__(self, name, pid, state, peak):
            self.name, self.pid, self.state, self.peak = name, pid, state, peak

    t0 = time.time()
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("t_s,name,pid,state,peak\n")
        while time.time() - t0 < seconds:
            t = time.time() - t0
            try:
                sessions = []
                for raw in AudioUtilities.GetAllSessions():
                    name = raw.Process.name() if raw.Process else "(system)"
                    try:
                        pid = int(raw.ProcessId)
                    except Exception:
                        pid = 0
                    state, peak = _session_state_and_peak(raw)
                    sessions.append(S(name, pid, state, peak))
                for line in format_samples(t, sessions):
                    fh.write(line + "\n")
                fh.flush()
            except Exception as exc:   # COM hiccups must not end the timeline
                fh.write(f"# {t:.1f} error {exc}\n")
                fh.flush()
            time.sleep(interval_s)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    h = sub.add_parser("hold")
    h.add_argument("exe")
    h.add_argument("--seconds", type=float, default=600.0)
    h.add_argument("--volume", type=float, default=1.0)
    m = sub.add_parser("monitor", help="sample every session's state and peak level into a CSV for the capture's length")
    m.add_argument("out")
    m.add_argument("--seconds", type=float, default=600.0)
    m.add_argument("--interval", type=float, default=5.0)
    c = sub.add_parser("contamination", help="read a monitor CSV back: which sessions outside the allowed ones rendered, and when")
    c.add_argument("csv")
    c.add_argument("--allowed", default="socom2.exe", help="comma-separated exe names that may render (the game); "
                   "LEDKeeper2.exe and (system) are always allowed, they render nothing")
    c.add_argument("--ignore-pid", type=int, action="append", default=[],
                   help="a process whose session is not a source (the loopback recorder: its capture stream reads as the endpoint's mix)")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        return cmd_list()
    if a.cmd == "monitor":
        return cmd_monitor(a.seconds, a.interval, a.out, log=lambda m: print(m, flush=True))
    if a.cmd == "contamination":
        with open(a.csv, "r", encoding="utf-8", errors="replace") as fh:
            rows = parse_samples(fh.read())
        allowed = tuple(x.strip() for x in a.allowed.split(",") if x.strip()) + ("LEDKeeper2.exe", "(system)")
        foreign = contamination(rows, allowed, ignore_pids=a.ignore_pid)
        samples = len({r.t_s for r in rows})
        if not rows:
            print("no samples: the monitor wrote nothing (COM unavailable, or it never ran)")
            return 2
        if not foreign:
            print(f"clean: {samples} samples, nothing but {', '.join(allowed)} rendered")
            return 0
        print(f"CONTAMINATED: {samples} samples; sessions outside {', '.join(allowed)} rendered:")
        for f in foreign:
            print(f"  {f.name:24s} active from {f.first_s:7.1f} s to {f.last_s:7.1f} s ({f.samples} samples, peak {f.peak:.3f})")
        return 1
    cmd_hold(a.exe, a.seconds, a.volume, log=lambda m: print(m, flush=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
