"""Sudden level dips in a capture, aligned to the mixer's own dump and classified against the game log.

research/36 item 9 (2026-09-20): the owner hears 100-450 ms dips on every STREAMED route (the title/options PCM
ring, the briefing and mission VAG stems, the contact cue) and none on sounds held in memory. The window score
cannot tell a device drop-out from a starved ring from a volume the game asked for; this does, per dip:

    DEVICE       -- in the endpoint (loopback) capture but not in the mixer's dump at the aligned time: lost
                    between render() and the speaker (the device thread missing a deadline).
    STARVATION   -- in the dump, with a buffer-empty event on the same output-frame clock within `window_s`:
                    "[audio] 989snd pcm UNDERRUN frame=.. silent=.." (the ring's stale run), a VAG stream's
                    "UNDERRUN", or an occupancy line with (nearly) nothing ahead of the read head.
    COMMAND      -- in the dump, with a level command on that route within the window: "[audio] 989snd cmd 0xNN
                    frame=.. [args]" (0x09 master volume, 0x13/0x14 pause/continue, 0x15/0x2f/0x34 stops, 0x1b/0x21
                    vol/pan, 0x22 AutoVol, 0x3c/0x3d PCM stop) or a stream's "done" (the cue ending / stopped).
    UNEXPLAINED  -- in the dump with nothing in the log near it.

The dump is written on the mixer's output-frame clock (48 kHz, PS2X_AUDIO_DUMP), the same clock every [audio]
event carries, so a dip at dump time t sits at frame t * 48000. The endpoint capture starts at its own moment;
`align` finds the offset by cross-correlating the two envelopes and reports it. Every threshold is a parameter.

    python -m tools_py.parity.audio_dips <endpoint.wav> [--dump mix.wav] [--log game.log] [--start s] [--end s]
"""
import argparse
import math
import re
import sys
import wave
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

MIXER_RATE = 48000
DEFAULT_HOP_S = 0.05
DEFAULT_REF_S = 1.0
DEFAULT_DROP_DB = 10.0
DEFAULT_FLOOR_DB = -60.0
DEFAULT_WINDOW_S = 0.1
LEVEL_COMMANDS = {0x09, 0x13, 0x14, 0x15, 0x18, 0x1B, 0x21, 0x22, 0x2D, 0x2E, 0x2F, 0x34, 0x3C, 0x3D}
COMMAND_NAMES = {0x09: "SetMasterVolume", 0x13: "PauseSound", 0x14: "ContinueSound", 0x15: "StopSound",
                 0x18: "StopAllSounds", 0x1B: "SetSoundVolPan", 0x21: "SetSoundParams", 0x22: "AutoVol",
                 0x2D: "PauseVAGStream", 0x2E: "ContinueVAGStream", 0x2F: "StopVAGStream", 0x34: "StopAllVAGStreams",
                 0x3C: "PcmStreamClose", 0x3D: "PcmStreamStop"}


# ---- wavs ------------------------------------------------------------------------------------------------

def read_mono(path: str) -> Tuple[np.ndarray, int]:
    """A 16-bit PCM wav as a mono float array in -1..1 and its rate (channels averaged)."""
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        x = x[: (len(x) // ch) * ch].reshape(-1, ch).mean(axis=1)
    return x, rate


def rms_db(mono: np.ndarray, rate: int, hop_s: float = DEFAULT_HOP_S) -> np.ndarray:
    """RMS in dBFS per `hop_s` hop (the last partial hop dropped)."""
    hop = max(1, int(round(rate * hop_s)))
    n = len(mono) // hop
    if n == 0:
        return np.zeros(0)
    frames = mono[: n * hop].reshape(n, hop)
    r = np.sqrt(np.mean(frames * frames, axis=1))
    return 20.0 * np.log10(np.maximum(r, 1e-6))


# ---- dips ------------------------------------------------------------------------------------------------

@dataclass
class Dip:
    start_s: float
    dur_s: float
    ref_db: float      # the median level of the preceding `ref_s`
    low_db: float      # the lowest hop inside the dip

    @property
    def depth_db(self) -> float:
        return self.ref_db - self.low_db

    @property
    def end_s(self) -> float:
        return self.start_s + self.dur_s


def find_dips(mono: np.ndarray, rate: int, hop_s: float = DEFAULT_HOP_S, ref_s: float = DEFAULT_REF_S,
              drop_db: float = DEFAULT_DROP_DB, floor_db: float = DEFAULT_FLOOR_DB, t0_s: float = 0.0) -> List[Dip]:
    """Every stretch of hops at least `drop_db` under the median of the preceding `ref_s` (which must itself be
    above `floor_db`: silence dipping is not a dip). A dip runs until a hop climbs back within `drop_db` of that
    reference; the scan resumes after it, so the dip's own hops never lower the next reference."""
    db = rms_db(mono, rate, hop_s)
    ref_hops = max(1, int(round(ref_s / hop_s)))
    out: List[Dip] = []
    n = len(db)
    in_dip = np.zeros(n, dtype=bool)   # hops inside a dip never enter a later dip's reference
    i = ref_hops
    while i < n:
        window = db[i - ref_hops:i]
        clean = window[~in_dip[i - ref_hops:i]]
        if len(clean) < 3:
            i += 1
            continue
        ref = float(np.median(clean))
        if ref > floor_db and db[i] <= ref - drop_db:
            j = i
            while j < n and db[j] <= ref - drop_db:
                j += 1
            in_dip[i:j] = True
            out.append(Dip(t0_s + i * hop_s, (j - i) * hop_s, ref, float(db[i:j].min())))
            i = j
        else:
            i += 1
    return out


# ---- alignment -------------------------------------------------------------------------------------------

def envelope(mono: np.ndarray, rate: int, hop_s: float) -> np.ndarray:
    e = rms_db(mono, rate, hop_s)
    return e - np.median(e) if len(e) else e


def align(endpoint: np.ndarray, endpoint_rate: int, dump: np.ndarray, dump_rate: int, hop_s: float = 0.01,
          max_lag_s: float = 90.0) -> Tuple[float, float]:
    """(offset_s, correlation): endpoint time = dump time + offset. Cross-correlation of the two log envelopes at
    `hop_s` over lags up to `max_lag_s` either way; the correlation is Pearson's at the best lag."""
    a = envelope(endpoint, endpoint_rate, hop_s)
    b = envelope(dump, dump_rate, hop_s)
    if len(a) < 2 or len(b) < 2:
        return 0.0, 0.0
    max_lag = int(max_lag_s / hop_s)
    best_lag, best = 0, -2.0
    for lag in range(-max_lag, max_lag + 1):
        # endpoint index = dump index + lag
        if lag >= 0:
            x, y = a[lag:], b[: len(a) - lag]
        else:
            x, y = a[: len(a) + lag], b[-lag:]
        m = min(len(x), len(y))
        if m < int(2.0 / hop_s):
            continue
        x, y = x[:m], y[:m]
        sx, sy = x.std(), y.std()
        if sx < 1e-9 or sy < 1e-9:
            continue
        c = float(np.mean((x - x.mean()) * (y - y.mean())) / (sx * sy))
        if c > best:
            best, best_lag = c, lag
    return best_lag * hop_s, best


# ---- the log ---------------------------------------------------------------------------------------------

@dataclass
class Events:
    stream_start: Dict[str, int] = field(default_factory=dict)       # handle -> frame
    stream_done: Dict[str, int] = field(default_factory=dict)        # handle -> frame
    stream_group: Dict[str, int] = field(default_factory=dict)       # handle -> group (from the IOP's 0x2c line)
    stream_underrun: List[Tuple[str, int, int]] = field(default_factory=list)   # (handle, frame, silent)
    stream_occupancy: List[Tuple[str, int, int]] = field(default_factory=list)  # (handle, frame, ahead)
    pcm_underrun: List[Tuple[int, int]] = field(default_factory=list)          # (start frame, silent frames)
    pcm_occupancy: List[Tuple[int, int, int]] = field(default_factory=list)    # (frame, blocks ahead, written)
    commands: List[Tuple[int, int, List[int]]] = field(default_factory=list)   # (fno, frame, args)


_RE_PLAY = re.compile(r"fno 0x0000002c\) \[0x([0-9a-f]+), 0x[0-9a-f]+, 0x[0-9a-f]+, 0x[0-9a-f]+, 0x([0-9a-f]+), [^\]]*\] -> 0x([0-9a-f]+)")
_RE_STREAM = re.compile(r"\[audio\] 989snd stream ([0-9a-f]+) (start|done|UNDERRUN) frame=(\d+) (?:detail|silent)=(\d+)")
_RE_OCC = re.compile(r"\[audio\] 989snd stream ([0-9a-f]+) occupancy frame=(\d+) ahead=(\d+)")
_RE_PCM_UNDER = re.compile(r"\[audio\] 989snd pcm UNDERRUN frame=(\d+) silent=(\d+)")
_RE_PCM_OCC = re.compile(r"\[audio\] 989snd pcm occupancy frame=(\d+) ahead=(\d+) blocks=\d+ pos=\d+ written=(\d+)")
_RE_CMD = re.compile(r"\[audio\] 989snd cmd 0x([0-9a-f]+) frame=(\d+) \[([^\]]*)\]")


def read_events(text: str) -> Events:
    ev = Events()
    for line in text.splitlines():
        m = _RE_STREAM.search(line)
        if m:
            handle = m.group(1).lower().zfill(8)
            frame = int(m.group(3))
            if m.group(2) == "start":
                ev.stream_start[handle] = frame
            elif m.group(2) == "done":
                ev.stream_done[handle] = frame
            else:
                ev.stream_underrun.append((handle, frame, int(m.group(4))))
            continue
        m = _RE_OCC.search(line)
        if m:
            ev.stream_occupancy.append((m.group(1).lower().zfill(8), int(m.group(2)), int(m.group(3))))
            continue
        m = _RE_PCM_UNDER.search(line)
        if m:
            ev.pcm_underrun.append((int(m.group(1)), int(m.group(2))))
            continue
        m = _RE_PCM_OCC.search(line)
        if m:
            ev.pcm_occupancy.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
            continue
        m = _RE_CMD.search(line)
        if m:
            args = [int(a.strip(), 16) for a in m.group(3).split(",") if a.strip()]
            ev.commands.append((int(m.group(1), 16), int(m.group(2)), args))
            continue
        m = _RE_PLAY.search(line)
        if m:
            ev.stream_group[m.group(3).lower().zfill(8)] = int(m.group(2), 16)
    return ev


# ---- classification --------------------------------------------------------------------------------------

@dataclass
class Row:
    start_s: float        # endpoint time when the dip is in the endpoint, else dump time + offset
    dur_s: float
    depth_db: float
    route: str            # "pcm", "vag g1", "vag g1+pcm", "none", ...
    label: str
    reason: str


def _routes_live(ev: Events, frame: int, slack: int) -> List[str]:
    routes = []
    for handle, start in ev.stream_start.items():
        done = ev.stream_done.get(handle, 1 << 62)
        if start - slack <= frame <= done + slack:
            g = ev.stream_group.get(handle)
            routes.append("vag" if g is None else "vag g%d" % g)
    if any(abs(f - frame) <= MIXER_RATE for f, _, _ in ev.pcm_occupancy) or any(s - slack <= frame <= s + n + slack for s, n in ev.pcm_underrun):
        routes.append("pcm")
    return sorted(set(routes))


def _starvation(ev: Events, f0: int, f1: int, slack: int) -> Optional[str]:
    for s, n in ev.pcm_underrun:
        if s - slack <= f1 and s + n + slack >= f0:
            return "pcm ring stale run at frame %d (%d frames silent)" % (s, n)
    for handle, f, silent in ev.stream_underrun:
        if f0 - slack <= f <= f1 + slack:
            return "stream %s UNDERRUN at frame %d (%d silent)" % (handle, f, silent)
    for handle, f, ahead in ev.stream_occupancy:
        if f0 - slack <= f <= f1 + slack and ahead < MIXER_RATE // 20:
            return "stream %s had %d frames ahead at frame %d" % (handle, ahead, f)
    for f, blocks, _ in ev.pcm_occupancy:
        if f0 - slack <= f <= f1 + slack and blocks == 0:
            return "pcm ring had no fresh block ahead at frame %d" % f
    return None


def _command(ev: Events, f0: int, f1: int, slack: int, live_handles: List[str]) -> Optional[str]:
    for fno, f, args in ev.commands:
        if fno not in LEVEL_COMMANDS or not (f0 - slack <= f <= f1 + slack):
            continue
        target = "0x%08x" % args[0] if args else ""
        handle = ("%08x" % args[0]) if args else ""
        if fno in (0x09, 0x18, 0x34, 0x3C, 0x3D) or handle in live_handles or not live_handles:
            return "%s (0x%02x) %s at frame %d" % (COMMAND_NAMES.get(fno, "cmd"), fno, target, f)
    for handle, f in ev.stream_done.items():
        if f0 - slack <= f <= f1 + slack:
            return "stream %s done at frame %d" % (handle, f)
    return None


def classify(endpoint_dips: List[Dip], dump_dips: Optional[List[Dip]], offset_s: float, ev: Events,
             window_s: float = DEFAULT_WINDOW_S, match_s: float = 0.25) -> List[Row]:
    """One row per dip. An endpoint dip with no dump dip within `match_s` at the aligned time is DEVICE; a dip in
    the dump is STARVATION, COMMAND or UNEXPLAINED by the log within `window_s`. Dump dips with no endpoint
    counterpart are listed too (label suffixed "(dump only)")."""
    slack = int(window_s * MIXER_RATE)
    rows: List[Row] = []
    used = set()

    def explain(d: Dip, t_dump: float, suffix: str = "") -> Row:
        f0 = int(t_dump * MIXER_RATE)
        f1 = int((t_dump + d.dur_s) * MIXER_RATE)
        routes = _routes_live(ev, f0, slack)
        live = [h for h, s in ev.stream_start.items() if s - slack <= f0 <= ev.stream_done.get(h, 1 << 62) + slack]
        why = _starvation(ev, f0, f1, slack)
        if why:
            return Row(t_dump + offset_s, d.dur_s, d.depth_db, "+".join(routes) or "none", "STARVATION" + suffix, why)
        why = _command(ev, f0, f1, slack, live)
        if why:
            return Row(t_dump + offset_s, d.dur_s, d.depth_db, "+".join(routes) or "none", "COMMAND" + suffix, why)
        return Row(t_dump + offset_s, d.dur_s, d.depth_db, "+".join(routes) or "none", "UNEXPLAINED" + suffix, "nothing in the log within %.0f ms" % (window_s * 1000))

    if dump_dips is None:
        # No dump: every dip is read against the log at its aligned time (no DEVICE verdict is possible).
        for d in endpoint_dips:
            rows.append(explain(d, d.start_s - offset_s))
        rows.sort(key=lambda r: r.start_s)
        return rows
    for d in endpoint_dips:
        t_dump = d.start_s - offset_s
        match = None
        for k, dd in enumerate(dump_dips):
            if k not in used and abs(dd.start_s - t_dump) <= match_s:
                match = (k, dd)
                break
        if match is None:
            f0 = int(t_dump * MIXER_RATE)
            rows.append(Row(d.start_s, d.dur_s, d.depth_db, "+".join(_routes_live(ev, f0, slack)) or "none", "DEVICE",
                            "in the endpoint, not in the dump at %.2f s" % t_dump))
        else:
            used.add(match[0])
            rows.append(explain(match[1], match[1].start_s))
    for k, dd in enumerate(dump_dips):
        if k not in used:
            rows.append(explain(dd, dd.start_s, " (dump only)"))
    rows.sort(key=lambda r: r.start_s)
    return rows


def report(rows: List[Row], offset_s: Optional[float] = None, corr: Optional[float] = None) -> str:
    lines = []
    if offset_s is not None:
        lines.append("alignment: endpoint = dump + %.3f s (envelope correlation %.2f)" % (offset_s, corr or 0.0))
    lines.append("%9s %7s %7s  %-14s %-22s %s" % ("t(s)", "dur(s)", "dB", "route", "label", "reason"))
    for r in rows:
        lines.append("%9.2f %7.2f %7.1f  %-14s %-22s %s" % (r.start_s, r.dur_s, r.depth_db, r.route, r.label, r.reason))
    counts: Dict[Tuple[str, str], int] = {}
    for r in rows:
        key = (r.label.split(" ")[0], r.route)
        counts[key] = counts.get(key, 0) + 1
    lines.append("summary (label x route):")
    for (label, route), n in sorted(counts.items()):
        lines.append("  %-12s %-14s %d" % (label, route, n))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("endpoint", help="the loopback capture (endpoint.wav)")
    ap.add_argument("--dump", help="the mixer's own output (PS2X_AUDIO_DUMP)")
    ap.add_argument("--log", help="the game log with the [audio] events")
    ap.add_argument("--offset", type=float, help="endpoint = dump + offset seconds (skips the alignment)")
    ap.add_argument("--start", type=float, default=0.0, help="analyse from this endpoint time")
    ap.add_argument("--end", type=float, help="analyse to this endpoint time")
    ap.add_argument("--drop-db", type=float, default=DEFAULT_DROP_DB)
    ap.add_argument("--hop", type=float, default=DEFAULT_HOP_S)
    args = ap.parse_args(argv)
    ep, ep_rate = read_mono(args.endpoint)
    ev = read_events(open(args.log, encoding="utf-8", errors="replace").read()) if args.log else Events()
    offset, corr = 0.0, None
    dump_dips: Optional[List[Dip]] = None
    if args.dump:
        dump, dump_rate = read_mono(args.dump)
        if args.offset is None:
            offset, corr = align(ep, ep_rate, dump, dump_rate)
        else:
            offset = args.offset
        d0 = max(0.0, args.start - offset)
        d1 = (args.end - offset) if args.end else len(dump) / dump_rate
        seg = dump[int(d0 * dump_rate): int(d1 * dump_rate)]
        dump_dips = find_dips(seg, dump_rate, hop_s=args.hop, drop_db=args.drop_db, t0_s=d0)
    e0 = args.start
    e1 = args.end if args.end else len(ep) / ep_rate
    seg = ep[int(e0 * ep_rate): int(e1 * ep_rate)]
    ep_dips = find_dips(seg, ep_rate, hop_s=args.hop, drop_db=args.drop_db, t0_s=e0)
    rows = classify(ep_dips, dump_dips, offset, ev)
    print(report(rows, offset if args.dump else None, corr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
