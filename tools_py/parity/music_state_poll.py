#!/usr/bin/env python
"""Poll the game's EE-side MUSIC MANAGER on either machine and log every change of what it DECIDED
(state transitions, cue-queue entries, the handle words), so two driven runs compare by decisions
and not only by sound (sprint-10 music round four, validation item 3).

The manager (research/36 "The music manager", decomp `socom2_game.elf.decomp.c`):

  DAT_0049e150  byte   the music ROUTE: 0 = not initialised (FUN_0034b8c0 :246983), 1 = the
                       989DSTRM headset extension (FUN_0034bb80 :247109), 2 = the plain 0x2c speaker
                       path (:247104; FUN_0034b410 :246844 falls back to it). FUN_0034b3b0
                       (:246813-246817) picks the state machine by it: 2 -> FUN_0034afd0.
  DAT_0049e158  word   POINTER to the manager, a 0x40-byte heap object (FUN_0034bc60 :247129-247134:
                       FUN_00180e10(0x40) then the constructor FUN_0034b910 :246990-247023).
  manager +0x09 byte   state: 4 reset (-> zero the handle words, 3; :246701-246706), 3 idle,
                       1 playing (:246707-246725), 0 / 2 the extension route's own states.
  manager +0x0a byte   interrupt flag: set by FUN_0034aac0 (:246598) when a type-1/2 cue arrives over
                       the playing one; consumed at :246718-246723 (StopSound, free, state 3).
  manager +0x0b byte   enable: 1 from the constructor (:247015), cleared by FUN_0034aa70 (:246545); a
                       popped cue with enable 0 is dropped (:246745-246749) and FUN_0034b6c0 queues a cue
                       only when enable != 0 or the cue is type 3 / flagged (:246921-246922).
  manager +0x0c word   the current cue's id (FUN_0034b510 pops it here :246895 / :246727).
  manager +0x10 word   the current cue's sound definition pointer (:246896; its +0x1c/+0x1d are the
                       flag bytes, +0x20 the name pointer :246781).
  manager +0x14 word   the current cue's volume, vol << 10 (:246897; :242114 `iVar7 << 10`).
  manager +0x18/+0x1c/+0x20  the CUE QUEUE, a vector<int> of slot indices (capacity, SIZE, data):
                       FUN_0034b6c0 pushes at the back (:246932), FUN_0034b510 pops the front (:246898),
                       both iterate data[0..size) (:246871-246873). Occupancy = word +0x1c.
  manager +0x24/+0x28/+0x2c  the FREE-SLOT vector: 20 slots pushed by the constructor (:247008-247012),
                       popped from the back (:246923-246928). Word +0x28 = free slots = 20 - queued.
  manager +0x30 word   the slot array, 20 x {id, def, vol} (0xf0 bytes, :247006).
  manager +0x34 word   [word 0xd] the sound-entry HANDLE of the playing stem (FUN_00347960 :246752-246753;
                       freed by FUN_00347810 :246713 / :246720 / :246758); 0 = none.
  manager +0x38 word   [word 0xe] the resumable stem's definition pointer (:246769-246771, cleared by
                       FUN_0034b890 :246956); 0 = none.
  manager +0x3c word   [word 0xf] that stem's cue id (:246772 = +0xc); 0xffffffff = none (:246704, :246766).

Two targets, one log format:

  --target pcsx2   reads the words over PINE at ~20 Hz (cam_poll's pointer-chain resolver).
  --target ours    reads the exe's own `[pc-sampler]` + `[peek]` rows (PS2X_PC_SAMPLER=0.05 and the
                   PS2X_PEEK spec below, exported before the capture; drive.py passes the environment
                   through) from a run log, live (--follow) or after the fact.

One line per CHANGE: `wall=<epoch s> t=<s since the poll started> [vsync=<ours' frame counter>]
[clock=MM:SS] <all fields> | <what changed>`.

`compare` takes two such logs and each run's HUD anchor (a run directory: the drive.stdout's
`untilref(...ref_hud...)` match, timed by the next step's PNG; or an epoch; or `t:<s>` in that log's
own clock) and prints the two timelines side by side, aligned on the HUD.

Usage:
  python -m tools_py.parity.music_state_poll --target pcsx2 --port 28011 --out logs/parity/X/music_state.txt --seconds 600
  python -m tools_py.parity.music_state_poll --target ours --log logs/parity/X/game.log --out logs/parity/X/music_state.txt
  python -m tools_py.parity.music_state_poll --target ours --log latest --follow --out ... --seconds 600
  python -m tools_py.parity.music_state_poll compare A/music_state.txt B/music_state.txt --hud-a A --hud-b B
"""
import argparse
import glob
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools_py.parity.cam_poll import pine_port, resolve  # noqa: E402

ROUTE_ADDR = 0x49e150            # DAT_0049e150, byte 0 of the word
MGR_PTR_ADDR = 0x49e158          # DAT_0049e158 -> the manager
MGR_WORDS = 16                   # 0x40 bytes
CLOCK_ADDR = 0x408f10            # the HUD timer string "MM:SS" (research/19 :217)
GUEST_CLOCK_ADDR = 0x4365c0      # the guest clock, float seconds (KNOWN.md, freeze detection)
QUEUE_SLOTS = 20                 # the constructor's 0x14 free slots

# What ours must be launched with: the same words the PINE poll reads, the pointer word included so the
# manager block is found by ADDRESS (PS2X_PEEK drops unresolved items; an index is not stable).
OURS_PEEK_SPEC = (f"{ROUTE_ADDR:#x}:1,{MGR_PTR_ADDR:#x}:1,*{MGR_PTR_ADDR:#x}:{MGR_WORDS},"
                  f"{CLOCK_ADDR:#x}:2,{GUEST_CLOCK_ADDR:#x}:1")
OURS_SAMPLER_S = "0.05"

FIELDS = ("mode", "state", "irq", "en", "cue", "def", "vol", "q", "free", "h34", "h38", "h3c")
STATE_NAMES = {4: "reset", 3: "idle", 1: "playing", 0: "ext-started", 2: "ext-pending"}


def decode(route_word, mgr_words):
    """The manager's fields out of the DAT_0049e150 word and the 16 manager words (None = no manager)."""
    f = {"mode": route_word & 0xff}
    if mgr_words is None:
        for k in FIELDS[1:]:
            f[k] = None
        return f
    w2 = mgr_words[2]
    f["state"] = (w2 >> 8) & 0xff
    f["irq"] = (w2 >> 16) & 0xff
    f["en"] = (w2 >> 24) & 0xff
    f["cue"] = mgr_words[3]
    f["def"] = mgr_words[4]
    f["vol"] = mgr_words[5]
    f["q"] = mgr_words[7]
    f["free"] = mgr_words[10]
    f["h34"] = mgr_words[13]
    f["h38"] = mgr_words[14]
    f["h3c"] = mgr_words[15]
    return f


def clock_string(words):
    """'MM:SS' out of the two words at 0x408f10, or None when the string is not set."""
    if not words or len(words) < 2:
        return None
    raw = b"".join(w.to_bytes(4, "little") for w in words[:2]).split(b"\0", 1)[0]
    s = raw.decode("ascii", "replace")
    return s if re.fullmatch(r"\d\d:\d\d", s) else None


def guest_clock(word):
    import struct
    if word is None:
        return None
    v = struct.unpack("<f", struct.pack("<I", word))[0]
    return v if v == v and abs(v) < 1e7 else None


def fmt_field(k, v):
    if v is None:
        return "-"
    if k in ("cue", "def", "vol", "h34", "h38", "h3c"):
        return f"{v:#x}" if v != 0xffffffff else "-1"
    return str(v)


def format_fields(f):
    return " ".join(f"{k}={fmt_field(k, f[k])}" for k in FIELDS)


def diff_fields(prev, cur):
    """[(field, old, new)] for the fields that differ (prev None = everything is new)."""
    if prev is None:
        return [(k, None, cur[k]) for k in FIELDS]
    return [(k, prev[k], cur[k]) for k in FIELDS if prev[k] != cur[k]]


def format_change_line(wall, t, f, changes, vsync=None, clock=None, gclock=None):
    head = f"wall={wall:.3f} t={t:.3f}"
    if vsync is not None:
        head += f" vsync={vsync}"
    if clock is not None:
        head += f" clock={clock}"
    if gclock is not None:
        head += f" gclock={gclock:.2f}"
    what = " ".join(f"{k} {fmt_field(k, o)}->{fmt_field(k, n)}" for k, o, n in changes)
    return f"{head} {format_fields(f)} | {what}"


_LINE_RE = re.compile(r"^wall=(?P<wall>[-\d.]+) t=(?P<t>[-\d.]+)(?: vsync=(?P<vsync>\d+))?(?: clock=(?P<clock>\d\d:\d\d))?"
                      r"(?: gclock=(?P<gclock>[-\d.]+))? (?P<fields>.*?) \| (?P<what>.*)$")


def parse_change_line(line):
    """A change line -> dict(wall, t, vsync, clock, fields, what) or None for headers / other lines."""
    m = _LINE_RE.match(line.strip())
    if not m:
        return None
    fields = {}
    for tok in m.group("fields").split():
        k, v = tok.split("=", 1)
        if v == "-":
            fields[k] = None
        elif v == "-1":
            fields[k] = 0xffffffff
        else:
            fields[k] = int(v, 0)
    return {"wall": float(m.group("wall")), "t": float(m.group("t")),
            "vsync": int(m.group("vsync")) if m.group("vsync") else None,
            "clock": m.group("clock"), "gclock": float(m.group("gclock")) if m.group("gclock") else None,
            "fields": fields, "what": m.group("what")}


class Tracker:
    """Feeds samples in, yields the change lines out (the first sample is a change of everything)."""

    def __init__(self, out, t0=None):
        self.out = out
        self.t0 = t0
        self.prev = None
        self.changes = 0
        self.samples = 0

    def feed(self, wall, fields, vsync=None, clock=None, gclock=None, t=None):
        if self.t0 is None:
            self.t0 = wall
        self.samples += 1
        changes = diff_fields(self.prev, fields)
        if not changes:
            return None
        self.prev = dict(fields)
        self.changes += 1
        line = format_change_line(wall, wall - self.t0 if t is None else t, fields, changes, vsync, clock, gclock)
        self.out.write(line + "\n")
        self.out.flush()
        return line


# ---- ours: the exe's [pc-sampler] + [peek] rows -------------------------------------------------

_SAMPLER_RE = re.compile(r"\[pc-sampler\].*?\bt=(?P<t>[\d.]+)\b.*?\bvsync=(?P<vsync>\d+)")
_PEEK_ITEM_RE = re.compile(r"@([0-9a-fA-F]+):((?: [0-9a-fA-F]{8}\([^)]*\))+)")


def parse_peek_row(line):
    """A `[peek]` row -> {addr: [words]} (the exe's `@addr: 00000000(0) ...` layout)."""
    items = {}
    for m in _PEEK_ITEM_RE.finditer(line):
        addr = int(m.group(1), 16)
        items[addr] = [int(w, 16) for w in re.findall(r"([0-9a-fA-F]{8})\(", m.group(2))]
    return items


def sample_from_peek(items):
    """(route word, manager words or None, clock words, guest clock word) out of a peek row's items.
    The manager block is the item at the address the 0x49e158 word holds (never an index)."""
    route = items.get(ROUTE_ADDR, [0])[0]
    ptr = items.get(MGR_PTR_ADDR, [0])[0]
    mgr = items.get(ptr) if ptr else None
    if mgr is not None and len(mgr) < MGR_WORDS:
        mgr = None
    clk = items.get(CLOCK_ADDR)
    gclk = items.get(GUEST_CLOCK_ADDR, [None])[0]
    return route, mgr, clk, gclk


def log_start_epoch(path):
    """The launch second out of `run_[A_|B_]YYYYmmdd_HHMMSS.log` (local time), else the file's mtime."""
    m = re.search(r"(\d{8})_(\d{6})", os.path.basename(path))
    if m:
        return time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))
    return os.path.getmtime(path)


def feed_ours_lines(lines, tracker, base_epoch=None, now=None):
    """Feed a run log's lines: each `[peek]` row is stamped with the preceding `[pc-sampler]`'s t= and
    vsync=; wall = now() when following live, else base_epoch + t."""
    t = vsync = None
    for line in lines:
        if line.startswith("[pc-sampler]"):
            m = _SAMPLER_RE.search(line)
            if m:
                t, vsync = float(m.group("t")), int(m.group("vsync"))
            continue
        if not line.startswith("[peek]"):
            continue
        items = parse_peek_row(line)
        if ROUTE_ADDR not in items and MGR_PTR_ADDR not in items:
            continue
        route, mgr, clk, gclk = sample_from_peek(items)
        wall = now() if now else (base_epoch or 0.0) + (t or 0.0)
        tracker.feed(wall, decode(route, mgr), vsync=vsync, clock=clock_string(clk),
                     gclock=guest_clock(gclk), t=t)


def follow(path, seconds, poll_s=0.05):
    """Yield a file's lines as they arrive, for `seconds` (a stopped writer ends it after 30 s of nothing)."""
    t0 = time.time()
    while not os.path.exists(path) and time.time() - t0 < seconds:
        time.sleep(0.5)
    if not os.path.exists(path):
        return
    with open(path, "r", errors="replace") as f:
        last = time.time()
        while time.time() - t0 < seconds:
            line = f.readline()
            if line:
                last = time.time()
                if line.endswith("\n"):
                    yield line
                continue
            if time.time() - last > 30.0:
                return
            time.sleep(poll_s)


def newest_run_log():
    logs = sorted(glob.glob(os.path.join("logs", "run_*.log")), key=os.path.getmtime)
    return logs[-1] if logs else None


# ---- pcsx2: PINE -----------------------------------------------------------------------------------

def sample_from_pine(read32):
    """(route word, manager words or None, clock words, guest clock word) read through `read32`."""
    route = read32(ROUTE_ADDR)
    addr, _ = resolve(read32, f"*{MGR_PTR_ADDR:#x}:{MGR_WORDS}")
    mgr = [read32(addr + 4 * i) for i in range(MGR_WORDS)] if addr else None
    clk = [read32(CLOCK_ADDR), read32(CLOCK_ADDR + 4)]
    return route, mgr, clk, read32(GUEST_CLOCK_ADDR)


def poll_pcsx2(port, out, seconds, hz):
    from tools_py.parity.pine import Pine
    t0 = time.time()
    p = None
    while p is None and time.time() - t0 < 120:
        try:
            p = Pine(port=port)
        except OSError:
            time.sleep(1.0)
    if p is None:
        raise SystemExit(f"no PINE on port {port}")
    tr = Tracker(out, t0=time.time())
    period = 1.0 / hz
    while time.time() - t0 < seconds:
        tick = time.time()
        try:
            route, mgr, clk, gclk = sample_from_pine(p.read32)
            tr.feed(tick, decode(route, mgr), clock=clock_string(clk), gclock=guest_clock(gclk))
        except Exception as e:  # noqa: BLE001 - PCSX2 may be between states
            out.write(f"# t={tick - t0:.3f} error {e}\n")
            out.flush()
            try:
                p.close()
            except Exception:  # noqa: BLE001
                pass
            p = None
            while p is None and time.time() - t0 < seconds:
                try:
                    p = Pine(port=port)
                except OSError:
                    time.sleep(1.0)
            if p is None:
                break
        rest = period - (time.time() - tick)
        if rest > 0:
            time.sleep(rest)
    return tr


# ---- compare ---------------------------------------------------------------------------------------

def read_log(path):
    """[change dicts] of a poll log, plus its header's started= epoch (None when absent)."""
    events, started = [], None
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith("#"):
                m = re.search(r"started=([\d.]+)", line)
                if m:
                    started = float(m.group(1))
                continue
            ev = parse_change_line(line)
            if ev:
                events.append(ev)
    return events, started


_STEP_RE = re.compile(r"^(s\d+_\S+)\s+t=\s*([\d.]+)s")


def hud_anchor_from_drive(run_dir):
    """The epoch of the HUD reference match in a drive run: the first `untilref(...ref_hud...)` line
    with matched=True, timed by the mtime of the NEXT step's PNG (drive.py prints the step line right
    after saving it). Returns (epoch, note) or raises."""
    stdout = os.path.join(run_dir, "drive.stdout")
    lines = open(stdout, "r", errors="replace").read().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("untilref(") and "ref_hud" in line and "matched=True" in line:
            for nxt in lines[i + 1:]:
                m = _STEP_RE.match(nxt)
                if m:
                    png = os.path.join(run_dir, m.group(1) + ".png")
                    if not os.path.exists(png):
                        raise SystemExit(f"{png}: the step after the HUD match has no PNG")
                    return os.path.getmtime(png), f"{os.path.basename(run_dir)}: HUD matched, {m.group(1)} at t={m.group(2)}s"
            raise SystemExit(f"{stdout}: no step line after the HUD match")
    raise SystemExit(f"{stdout}: no `untilref(...ref_hud...)` matched=True line")


def hud_anchor(spec, log_started):
    """`spec` = a run directory (or its drive.stdout), `t:<seconds in the poll log's clock>`, or an epoch."""
    if spec.startswith("t:"):
        if log_started is None:
            raise SystemExit("t:<s> needs the poll log's `started=` header")
        return log_started + float(spec[2:]), f"t={spec[2:]}s of the poll log"
    if os.path.isdir(spec):
        return hud_anchor_from_drive(spec)
    if os.path.isfile(spec) and os.path.basename(spec) == "drive.stdout":
        return hud_anchor_from_drive(os.path.dirname(spec))
    return float(spec), "epoch given"


def state_name(v):
    """4 -> 'reset' etc.; accepts the change line's text form ('3', '-')."""
    if v is None or v == "-":
        return "-"
    try:
        return STATE_NAMES.get(int(str(v), 0), str(v))
    except ValueError:
        return str(v)


def event_summary(ev):
    """The short form of an event for the side-by-side listing."""
    f = ev["fields"]
    parts = []
    for k, o, n in _parse_what(ev["what"]):
        if k == "state":
            parts.append(f"state {state_name(o)}->{state_name(n)}")
        elif k in ("q", "free", "mode", "irq", "en"):
            parts.append(f"{k} {o}->{n}")
        else:
            parts.append(f"{k} {o}->{n}")
    extra = ""
    if ev["clock"]:
        extra = f" [{ev['clock']}]"
    if ev["vsync"] is not None:
        extra += f" [f{ev['vsync']}]"
    return ", ".join(parts) + extra + (f"  (cue {fmt_field('cue', f.get('cue'))} q={f.get('q')})" if "state" in ev["what"] else "")


def _parse_what(what):
    out = []
    for tok in re.findall(r"(\w+) (\S+)->(\S+)", what):
        out.append(tok)
    return out


def transitions(events):
    """[(hud_rel, old, new)] of the state field."""
    out = []
    for ev in events:
        for k, o, n in _parse_what(ev["what"]):
            if k == "state" and o != "-":
                out.append((ev["rel"], o, n))
    return out


def compare(log_a, log_b, hud_a, hud_b, out=sys.stdout, width=58, window=None):
    ev_a, st_a = read_log(log_a)
    ev_b, st_b = read_log(log_b)
    ep_a, note_a = hud_anchor(hud_a, st_a)
    ep_b, note_b = hud_anchor(hud_b, st_b)
    for evs, ep in ((ev_a, ep_a), (ev_b, ep_b)):
        for ev in evs:
            ev["rel"] = ev["wall"] - ep
    out.write(f"A: {log_a} ({len(ev_a)} changes) HUD anchor {note_a}\n")
    out.write(f"B: {log_b} ({len(ev_b)} changes) HUD anchor {note_b}\n")
    out.write(f"{'A (s from HUD)':<{width}} | B (s from HUD)\n")
    out.write("-" * (2 * width + 3) + "\n")
    merged = [(ev["rel"], 0, ev) for ev in ev_a] + [(ev["rel"], 1, ev) for ev in ev_b]
    merged.sort(key=lambda x: (x[0], x[1]))
    for rel, side, ev in merged:
        if window is not None and not (window[0] <= rel <= window[1]):
            continue
        cell = f"{rel:+8.2f} {event_summary(ev)}"
        if len(cell) > width:
            cell = cell[:width - 1] + "~"
        if side == 0:
            out.write(f"{cell:<{width}} |\n")
        else:
            out.write(f"{'':<{width}} | {cell}\n")
    ta, tb = transitions(ev_a), transitions(ev_b)
    out.write("\nstate transitions after the HUD (s from HUD):\n")
    for name, tr in (("A", ta), ("B", tb)):
        post = [x for x in tr if x[0] >= 0]
        out.write(f"  {name}: {len(post)} -- " + ", ".join(f"{o}->{n}@{r:+.1f}" for r, o, n in post[:40])
                  + (" ..." if len(post) > 40 else "") + "\n")
    pa = [x for x in ta if x[0] >= 0 and x[2] == "1"]
    pb = [x for x in tb if x[0] >= 0 and x[2] == "1"]
    out.write(f"  plays (->1) after the HUD: A {len(pa)}, B {len(pb)}; first at A {pa[0][0]:+.1f}s B {pb[0][0]:+.1f}s\n"
              if pa and pb else f"  plays (->1) after the HUD: A {len(pa)}, B {len(pb)}\n")
    for k, (x, y) in enumerate(zip(pa, pb)):
        if k >= 20:
            break
        out.write(f"    play {k + 1}: A {x[0]:+7.1f}  B {y[0]:+7.1f}  d={y[0] - x[0]:+.1f}s\n")
    qa = sum(1 for ev in ev_a if ev["rel"] >= 0 and any(k == "q" and int(n) > int(o) for k, o, n in _parse_what(ev["what"]) if o != "-"))
    qb = sum(1 for ev in ev_b if ev["rel"] >= 0 and any(k == "q" and int(n) > int(o) for k, o, n in _parse_what(ev["what"]) if o != "-"))
    out.write(f"  cue-queue pushes seen after the HUD: A {qa}, B {qb} (a push and its pop inside one sample period are invisible)\n")


# ---- main ------------------------------------------------------------------------------------------

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "compare":
        ap = argparse.ArgumentParser(prog="music_state_poll compare")
        ap.add_argument("log_a")
        ap.add_argument("log_b")
        ap.add_argument("--hud-a", required=True, help="run dir (drive.stdout + PNGs), epoch, or t:<s>")
        ap.add_argument("--hud-b", required=True)
        ap.add_argument("--window", default=None, help="lo:hi seconds from the HUD to list")
        a = ap.parse_args(argv[1:])
        win = tuple(float(v) for v in a.window.split(":")) if a.window else None
        compare(a.log_a, a.log_b, a.hud_a, a.hud_b, window=win)
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=("pcsx2", "ours"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=600.0)
    ap.add_argument("--hz", type=float, default=20.0)
    ap.add_argument("--port", type=int, default=0, help="PINE port (default: PINESlot from PCSX2.ini)")
    ap.add_argument("--log", default="latest", help="ours: the run log (`latest` = newest logs/run_*.log)")
    ap.add_argument("--follow", action="store_true", help="ours: tail the log live (wall = now)")
    ap.add_argument("--log-start", type=float, default=None, help="ours, offline: the log's launch epoch")
    a = ap.parse_args(argv)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as out:
        started = time.time()
        if a.target == "pcsx2":
            port = a.port or pine_port()
            out.write(f"# music_state_poll target=pcsx2 port={port} hz={a.hz} started={started:.3f} "
                      f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started))}\n")
            tr = poll_pcsx2(port, out, a.seconds, a.hz)
        else:
            path = a.log
            if path == "latest":
                t0 = time.time()
                path = newest_run_log()
                while a.follow and (path is None or os.path.getmtime(path) < started - 5) and time.time() - t0 < 120:
                    time.sleep(1.0)
                    path = newest_run_log()
                if path is None:
                    raise SystemExit("no logs/run_*.log")
            base = a.log_start if a.log_start is not None else log_start_epoch(path)
            out.write(f"# music_state_poll target=ours log={path} follow={a.follow} started={started:.3f} "
                      f"log_start={base:.3f} peek={OURS_PEEK_SPEC}\n")
            tr = Tracker(out, t0=started if a.follow else base)
            if a.follow:
                feed_ours_lines(follow(path, a.seconds), tr, now=time.time)
            else:
                with open(path, "r", errors="replace") as f:
                    feed_ours_lines(f, tr, base_epoch=base)
        out.write(f"# done samples={tr.samples} changes={tr.changes}\n")
    print(f"{tr.samples} samples, {tr.changes} changes -> {a.out}")
    if a.target == "ours" and tr.samples == 0:
        print(f"no manager rows: launch ours with PS2X_PC_SAMPLER={OURS_SAMPLER_S} PS2X_PEEK=\"{OURS_PEEK_SPEC}\"")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
