"""Pure online verdict scorers: is a side controllable, is its move path alive, is it network-starved,
is a valve read trustworthy, and how many contact rows occurred -- decided from log rows.

Sprint 5 Task 3 Step 0. PURE: the parse functions take lines/strings, the scorers take rows, and
nothing here opens a file, reads a clock or imports the live harness. Only `main()` (the CLI) does IO:

    python -m tools_py.parity.verdict_core score-control|move-path|contact|starvation <logs...>

Every scorer counts what it read and answers `NO-DATA` -- never "healthy" -- when the rows it needs
are missing. Each threshold below is a named constant with the measurement behind it and the class
of failure it does NOT separate ("blind").

Row conventions (the exe's own log formats; see research/18 §3.10-§3.12 and the plan's instrument
notes):
  * `[peek] @<addr>: <hex8>(<float>) ...` -- one line per PS2X_PC_SAMPLER period, NOT timestamped.
    PS2X_PEEK SKIPS an item whose pointer chain does not resolve, so items are identified by
    content (actor block: word 0 == vtable 0x006691A0; valve: word 0 == its name pointer; CZNetGame
    block: word 70 == 50.0f), never by index.
  * `[call] <t>s <Name> #<n> ... f12=<v> ...` -- t is seconds since the process's call-trace start.
    The first 300 calls of a slot are logged, then 1 in PS2X_CALL_TRACE_EVERY: count calls from
    `#n`, never from line counts. `[ret] <Name> #<n> v0=0x...` carries no time; it takes its call's.
  * `[socom2-input] state buttons=XXXX rx=XX ry=XX lx=XX ly=XX` -- written to stderr on every change
    of the pad state the game read. Another stream's write can tear it in two (2 of 150 state lines on
    ours_task8_kill3 B); the tail is recovered from the next line and the tear counted.

Time: a peek row's time is interpolated along its index between `[call]` stamps at least
CLOCK_ANCHOR_MIN_SPACING_S apart, and extrapolated at the sampler period outside them. A pad event
sits between two peek rows and takes the midpoint. Blind: the pad event's time is known only to
within half a sampler period (~0.125 s at 4 Hz, ~5 units of walking at 40 u/s); with no stamps at
all (frost1 after its 0.6 s of MoveScale calls) the nominal period is used, and kill2 B's real
period was 0.278 s, so a "10 s" window there may really be ~11 s.
"""
import argparse
import bisect
import math
import os
import re
import struct
import sys
from collections import namedtuple
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------------------------
# verdict words
# ---------------------------------------------------------------------------------------------
NO_DATA = "NO-DATA"
CONTROLLABLE = "CONTROLLABLE"
NO_CONTROL = "NO-CONTROL"

# ---------------------------------------------------------------------------------------------
# instruments (the exe's formats and the addresses they carry)
# ---------------------------------------------------------------------------------------------
SAMPLER_PERIOD_S = 0.25            # PS2X_PC_SAMPLER=0.25 in every Sprint 4 launch script
CLOCK_ANCHOR_MIN_SPACING_S = 5.0   # [call] stamps have 0.1 s resolution and arrive ~2/s: anchors this
                                   # far apart give a local period good to ~2 %, where adjacent stamps
                                   # would give a jittering one
ACTOR_VTABLE = 0x006691A0          # word 0 of the player actor block (*0x408c58)
ACTOR_POS_WORDS = (7, 8, 9)        # actor +0x1c/+0x20/+0x24 = x, y, z
CAMERA_RECORD_ADDR = 0x416054      # the camera-orbit record; NOT the player (research/18 §4.1)
MOVE_SCALE_NAME = "MoveScale"      # PS2X_CALL_TRACE="0x553dc0:MoveScale"
NET_IDLE_NAME = "NetIdleMs"        # PS2X_CALL_TRACE="0x30cd80:NetIdleMs" (the thunk, research/18 §3.12a)
CLOCK_STRING_ADDR = 0x408F10       # round clock string (research/19 F2)
NG_FINGERPRINT_WORD = 0x118 // 4   # CZNetGame +0x118 = 50.0f (reCOM m_pos_smooth), in all ten images
NG_FINGERPRINT_VALUE = 0x42480000  # (research/19 F2) -- identifies the *0x437ce8:84 block by content
NG_LAG_FLAG_OFFSET = 0xDE          # set to 1 by FUN_00594cf0 at idle >= 4501 ms (research/19 F2)
PAD_NEUTRAL = 0x80

# ---------------------------------------------------------------------------------------------
# control bar -- the spec's (§5 "Goal 1 -- movement bar"), one bar for the precondition and Task 1
# ---------------------------------------------------------------------------------------------
# Net ground-plane displacement from hold start to release + 1.5 s. Measured against: the 40 u/s
# forward calibration (online_match_ours WALK_UNITS_PER_S_LONG, research/18 §3.13) and 28-38 units
# per 1 s sample during a hold (§3.12) -- a 2 s hold covers ~60-80, a live 1.5 s facing probe
# covered 60.35 (kill2 A) and 64.01 (kill2 B) on actor rows. Blind: a half-decayed scale that still
# covers 40; motion in the wrong direction (this is a distance, not a heading).
CONTROL_NET_MIN_UNITS = 40.0
CONTROL_NET_AFTER_RELEASE_S = 1.5
# Position at release + 2 s within 10 of the position at release. Measured against: the record keeps
# moving about one sample after release (§3.12: "stops one sample after release"), 1.18 / 0.72 units on
# kill2's probes (release reference one row after release). Blind: a correction (snap-back) arriving later than 2 s.
CONTROL_SNAPBACK_MAX_UNITS = 10.0
CONTROL_SNAPBACK_AFTER_RELEASE_S = 2.0
# Net drift over the preceding 10 s neutral window <= 5. Measured against: 1.3-1.4 units per sample of
# camera jitter at neutral (§3.12), and 0.00 / 0.00 units of actor drift before kill2's probes (window ending at
# the last row before the press).
# Blind: a frozen player passes it trivially -- it only means something alongside the 40.
CONTROL_DRIFT_MAX_UNITS = 5.0
CONTROL_DRIFT_WINDOW_S = 10.0
# Scoring domain, not a bar: holds shorter than this are not scored. The shortest scored hold is the
# 1.5 s facing probe (measured 1.46-1.51 s from pad events, i.e. within +-1/2 sample); an 0.8 s engage step at
# 40 u/s cannot cover 40 units and would read as NO-CONTROL. Blind: none added -- a skipped hold is
# absent from the verdict, and a side with no scored hold is NO-DATA.
FORWARD_HOLD_MIN_S = 1.25
FORWARD_LY_MAX = 0x40              # "forward": LY deflected at least half way up; LX/RX neutral
# A position is interpolated only between rows at most this far apart; beyond it the window is
# NO-DATA. Two missed 4 Hz samples. Blind: motion that starts and reverses inside a 1 s gap.
ROW_MAX_GAP_S = 1.0
PRECONDITION_MAX_HOLDS = 4         # the precondition's up-to-4 two-second holds (task-3 brief)

# ---------------------------------------------------------------------------------------------
# move path, starvation, contact
# ---------------------------------------------------------------------------------------------
# MoveScale #n must advance within 10 s. Measured against: 18.9 / 17.0 / 27.4 calls/s live (kill2 A,
# kill2 B, kill3 B), i.e. >= 1 logged line per ~1 s at EVERY <= 20; frost1 logged 18 calls in 0.6 s
# and never again. Blind: a stall shorter than 10 s; a path that ticks but ignores the stick
# (kill3's camera record froze while MoveScale ran at 27/s -- movement is score_control's job).
MOVE_STALL_S = 10.0
# Disarmed within 15 s of an mp_round_count step and while +0xF7A != 1. Blind: the move path is
# legitimately silent on death and round change -- a real stall inside those windows is not reported.
ROUND_STEP_DISARM_S = 15.0
ALIVE_VALUE = 1
# NetIdle [ret] v0 (ms): alarm at 4000, bar <= 5000. Measured against: the scale holds 1.0 until idle
# > 5500 ms (§3.12 "timing, corrected"), the game's own lag flag at >= 4501 ms, Sprint 4's healthy
# worst gap 2.7 s and idle capped at 1490 ms in the fixed A/B (§3.12a). Blind: peaks between ~0.5 s
# samples; ng+0xde is stale when the move path is silent (then NO-DATA).
NETIDLE_ALARM_MS = 4000
NETIDLE_BAR_MS = 5000
# Contact gate (spec §5 Goal 5a): 3-D <= 22 and |dy| <= 10.
CONTACT_3D_MAX_UNITS = 22.0
CONTACT_DY_MAX_UNITS = 10.0
CONTACT_SCALE_MIN = 0.99           # both sides' latest f12; closes the starved-pair-in-the-gate class
# Pairing: B's row nearest A's within two 4 Hz samples. Blind: a 0.5 s misalignment at 40 u/s is 20
# units -- the two process clocks must be aligned by the caller first (see main's --offset-b).
CONTACT_PAIR_MAX_S = 0.5
# A row counts only if its own side's previous row is at most this far back, on BOTH sides: a slow or
# stalled sampler must not stretch one position over several rows of the other side. Three 4 Hz
# samples. Blind: kill2 B's fight stretch ran at ~0.6 s/row (max 1.08 s) -- rows after its longer
# gaps do not count, so a slow-but-healthy sampler under-counts contact (conservative).
CONTACT_ROW_MAX_GAP_S = 0.75
# "#n advancing" at a contact row: a logged call with a higher #n inside the last 3 s. At EVERY <= 20
# and ~17-27 calls/s that is >= 2 lines expected. Blind: a stall shorter than ~3 s.
CONTACT_ADVANCE_WINDOW_S = 3.0
# "clock changing": the clock string (ticks each 1 s) took two values inside the last 2.5 s. Blind: a
# guest that runs its clock but not its world; a hung renderer (the clock is guest memory).
CONTACT_CLOCK_WINDOW_S = 2.5
CONTACT_SCALE_MAX_AGE_S = 3.0      # an f12 older than this is not "latest"


# ---------------------------------------------------------------------------------------------
# small types
# ---------------------------------------------------------------------------------------------
PadEvent = namedtuple("PadEvent", "t buttons rx ry lx ly")   # buttons None when a tear lost them
Hold = namedtuple("Hold", "start release")


@dataclass(frozen=True)
class NoData:
    """A read that could not be made. Falsy, and never equal to a value."""
    reason: str
    status: str = NO_DATA

    def __bool__(self):
        return False

    def __str__(self):
        return f"{NO_DATA} ({self.reason})"


@dataclass
class ParsedLog:
    lines: int = 0
    peek_rows: list = field(default_factory=list)      # [(t, [(addr, [word, ...]), ...])]
    actor_rows: list = field(default_factory=list)     # [(t, x, y, z, actor_addr)]  (all-zero rows kept out)
    pad_events: list = field(default_factory=list)     # [PadEvent]
    calls: dict = field(default_factory=dict)          # name -> [(t, n, f12, ra)]
    rets: dict = field(default_factory=dict)           # name -> [(t, n, v0)]
    torn_pad_lines: int = 0
    unrecovered_pad_lines: int = 0
    unrecovered_pad_times: list = field(default_factory=list)
    clock_anchors: int = 0


@dataclass
class ControlVerdict:
    ok: bool
    net_units: object
    snapback_units: object
    drift_units: object
    status: str = NO_DATA               # PASS | FAIL | NO-DATA
    reason: str = ""
    hold: object = None


@dataclass
class SideControl:
    status: str                         # CONTROLLABLE | NO-CONTROL | NO-DATA
    holds: list                         # [ControlVerdict] actually scored, in order


@dataclass
class MovePathVerdict:
    status: str                         # ok | stalled | disarmed | NO-DATA
    since: object
    detail: str


@dataclass
class StarvationVerdict:
    status: str                         # ok | alarm | NO-DATA
    side: str
    since: object = None
    signal: object = None               # "ng+0xde" | "NetIdle"
    peak_ms: object = None
    bar_ok: object = None
    episodes: list = field(default_factory=list)
    detail: str = ""


@dataclass
class ContactResult:
    contact_rows: int                   # longest run of consecutive qualifying rows
    total_rows: int                     # qualifying rows, not necessarily consecutive
    rows_read: int
    status: str                         # ok | NO-DATA
    reason: str = ""
    closest_3d: object = None
    closest_dy: object = None


def f32(word):
    return struct.unpack("<f", struct.pack("<I", word & 0xFFFFFFFF))[0]


# ---------------------------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------------------------
_ITEM = re.compile(r"@([0-9a-fA-F]+):((?:\s+[0-9a-fA-F]{8}\([^)]*\))+)")
_WORD = re.compile(r"([0-9a-fA-F]{8})\(")
_CALL = re.compile(r"^\[call\] ([\d.]+)s (\S+) #(\d+)(.*)$")
_RET = re.compile(r"^\[ret\] (\S+) #(\d+) v0=0x([0-9a-fA-F]+)")
_F12 = re.compile(r"\sf12=(-?[\d.eE+-]+|nan|-?inf)")
_RA = re.compile(r"\sra=0x([0-9a-fA-F]+)")
_PAD_FULL = re.compile(r"buttons=([0-9a-fA-F]{4}) rx=([0-9a-fA-F]{2}) ry=([0-9a-fA-F]{2}) "
                       r"lx=([0-9a-fA-F]{2}) ly=([0-9a-fA-F]{2})\s*$")
_PAD_TAIL = re.compile(r"(?:^|=)([0-9a-fA-F]{4})?\s?rx=([0-9a-fA-F]{2}) ry=([0-9a-fA-F]{2}) "
                       r"lx=([0-9a-fA-F]{2}) ly=([0-9a-fA-F]{2})\s*$")
_PAD_HEAD = "[socom2-input] state"


def parse_log(lines, sampler_period=SAMPLER_PERIOD_S):
    """Rows out of one instance's run log (an iterable of lines). No IO."""
    p = ParsedLog()
    peek_idx = []            # (peek index, items)
    anchors = []             # (fractional peek index, t)
    calls_raw = {}           # name -> [(frac idx, t, n, f12, ra)]
    rets_raw = {}            # name -> [(n, v0)]
    pads_raw = []            # (frac idx, PadEvent without t)
    unrecovered_idx = []
    pi = 0
    pending_tear = False
    for raw in lines:
        line = raw.rstrip("\r\n")
        p.lines += 1
        if not line:
            continue
        if line.startswith("[peek]"):
            items = [(int(a, 16), [int(w, 16) for w in _WORD.findall(ws)]) for a, ws in _ITEM.findall(line)]
            peek_idx.append((pi, items))
            pi += 1
            if pending_tear:
                pending_tear = False
                p.unrecovered_pad_lines += 1
                unrecovered_idx.append(pi - 1.5)
            continue
        here = pi - 0.5
        if line.startswith(_PAD_HEAD):
            if pending_tear:                 # two heads in a row: the first tail never came
                p.unrecovered_pad_lines += 1
                unrecovered_idx.append(here)
            m = _PAD_FULL.search(line)
            if m:
                pending_tear = False
                pads_raw.append((here, tuple(int(g, 16) for g in m.groups())))
            else:
                p.torn_pad_lines += 1
                pending_tear = True
            continue
        if pending_tear:
            pending_tear = False
            m = _PAD_TAIL.search(line)
            if m:
                b = int(m.group(1), 16) if m.group(1) else None
                pads_raw.append((here, (b,) + tuple(int(g, 16) for g in m.groups()[1:])))
                continue
            p.unrecovered_pad_lines += 1       # the tail never came; this line is its own line
            unrecovered_idx.append(here)
        if line.startswith("[call]"):
            m = _CALL.match(line)
            if m:
                t, name, n, rest = float(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
                fm, rm = _F12.search(rest), _RA.search(rest)
                f12 = float(fm.group(1)) if fm else None
                ra = int(rm.group(1), 16) if rm else None
                calls_raw.setdefault(name, []).append((here, t, n, f12, ra))
                if not anchors or t - anchors[-1][1] >= CLOCK_ANCHOR_MIN_SPACING_S:
                    anchors.append((here, t))
            continue
        if line.startswith("[ret]"):
            m = _RET.match(line)
            if m:
                rets_raw.setdefault(m.group(1), []).append((int(m.group(2)), int(m.group(3), 16)))
    if pending_tear:
        p.unrecovered_pad_lines += 1
        unrecovered_idx.append(pi - 0.5)

    clock = _make_clock(anchors, sampler_period)
    p.clock_anchors = len(anchors)
    for i, items in peek_idx:
        t = clock(i)
        p.peek_rows.append((t, items))
        actor = next(((a, w) for a, w in items if w and w[0] == ACTOR_VTABLE), None)
        if actor is not None and len(actor[1]) > max(ACTOR_POS_WORDS):
            x, y, z = (f32(actor[1][k]) for k in ACTOR_POS_WORDS)
            if x or y or z:
                p.actor_rows.append((t, x, y, z, actor[0]))
    p.pad_events = [PadEvent(clock(i), *v) for i, v in pads_raw]
    p.unrecovered_pad_times = [clock(i) for i in unrecovered_idx]
    for name, rows in calls_raw.items():
        p.calls[name] = [(t, n, f12, ra) for _, t, n, f12, ra in rows]
    for name, rows in rets_raw.items():
        t_of = {n: t for t, n, _, _ in p.calls.get(name, [])}
        p.rets[name] = [(t_of[n], n, v0) for n, v0 in rows if n in t_of]
    return p


def _make_clock(anchors, period):
    if not anchors:
        return lambda i: i * period
    idx = [a[0] for a in anchors]

    def clock(i):
        if i <= idx[0]:
            return anchors[0][1] - (idx[0] - i) * period
        if i >= idx[-1]:
            return anchors[-1][1] + (i - idx[-1]) * period
        k = bisect.bisect_right(idx, i)
        (i0, t0), (i1, t1) = anchors[k - 1], anchors[k]
        return t0 + (t1 - t0) * (i - i0) / (i1 - i0)
    return clock


def _sticks_neutral(e):
    return e.rx == PAD_NEUTRAL and e.ry == PAD_NEUTRAL and e.lx == PAD_NEUTRAL and e.ly == PAD_NEUTRAL


def _fully_neutral(e):
    return _sticks_neutral(e) and e.buttons == 0


def forward_holds(pad_events):
    """Pure forward holds (LY up, LX and RX neutral throughout), released. Unreleased and mixed
    holds are not holds."""
    holds, start, mixed = [], None, False
    for e in pad_events:
        fwd = e.ly <= FORWARD_LY_MAX
        if start is None:
            if fwd:
                start, mixed = e.t, (e.lx != PAD_NEUTRAL or e.rx != PAD_NEUTRAL)
            continue
        if fwd:
            mixed = mixed or e.lx != PAD_NEUTRAL or e.rx != PAD_NEUTRAL
            continue
        if not mixed:
            holds.append(Hold(start, e.t))
        start, mixed = None, False
    return holds


# ---------------------------------------------------------------------------------------------
# control
# ---------------------------------------------------------------------------------------------
def _pos_at(rows, times, t):
    """(x, z, addr) linearly interpolated at t, or None when t is outside the rows or between two rows
    further apart than ROW_MAX_GAP_S, or when the actor block was re-pointed between them."""
    k = bisect.bisect_left(times, t)
    if k < len(times) and times[k] == t:
        r = rows[k]
        return r[1], r[3], _addr(r)
    if k == 0 or k >= len(times):
        return None
    a, b = rows[k - 1], rows[k]
    if b[0] - a[0] > ROW_MAX_GAP_S or _addr(a) != _addr(b):
        return None
    f = (t - a[0]) / (b[0] - a[0])
    return a[1] + f * (b[1] - a[1]), a[3] + f * (b[3] - a[3]), _addr(a)


def _addr(row):
    return row[4] if len(row) > 4 else None


def _ground(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _window_ok(rows, times, t0, t1):
    """Rows cover [t0, t1] with no gap > ROW_MAX_GAP_S and one actor address throughout."""
    k0 = bisect.bisect_right(times, t0) - 1
    k1 = bisect.bisect_left(times, t1)
    if k0 < 0 or k1 >= len(times):
        return False
    seg = rows[k0:k1 + 1]
    if any(b[0] - a[0] > ROW_MAX_GAP_S for a, b in zip(seg, seg[1:])):
        return False
    return len({_addr(r) for r in seg}) == 1


def _pad_state_before(pad_events, t):
    """The pad state in force just before t (None = no event yet: neutral from boot)."""
    last = None
    for e in pad_events:
        if e.t < t:
            last = e
        else:
            break
    return last


def score_control(rows, pad_events, hold, unrecovered_pad_times=()):
    """Score one forward hold against the spec's bar. rows: actor rows (t, x, y, z[, addr])."""
    rows = sorted(rows, key=lambda r: r[0])
    times = [r[0] for r in rows]
    s, r = hold.start, hold.release
    t_net, t_snap = r + CONTROL_NET_AFTER_RELEASE_S, r + CONTROL_SNAPBACK_AFTER_RELEASE_S
    t_drift = s - CONTROL_DRIFT_WINDOW_S
    reasons = []

    if not rows:
        return ControlVerdict(False, None, None, None, NO_DATA, "no actor rows", hold)

    torn_inside = [u for u in unrecovered_pad_times if t_drift <= u <= t_snap]
    if torn_inside:
        return ControlVerdict(False, None, None, None, NO_DATA,
                              f"unrecovered torn pad line at {torn_inside[0]:.2f}", hold)

    # Pad events carry +-1/2 sampler period of timing error (parse_log puts them midway between two
    # rows), so no position is interpolated AT an event time: the hold's start reference is the last
    # row at or before the start event (sampled before the game saw the press), and the release
    # reference is the first row at or after release + one row period (so one sample of legitimate
    # coast after release is not read as a snap-back). Blind: a snap-back that completes inside that
    # one row after release still fails the net clause only if it undoes the displacement.
    k_s = bisect.bisect_right(times, s) - 1
    k_after = bisect.bisect_right(times, r)
    t_s0 = times[k_s] if k_s >= 0 else None
    k_r = k_after + 1 if k_after + 1 < len(times) else None
    t_ref = times[k_r] if k_r is not None else None
    if t_s0 is not None:
        t_drift = t_s0 - CONTROL_DRIFT_WINDOW_S

    after = [e for e in pad_events if r < e.t <= t_snap and not _sticks_neutral(e)]
    net = snap = drift = None
    if after:
        reasons.append(f"stick input {after[0].t - r:+.2f}s after release")
    elif t_s0 is None or t_ref is None or t_ref > t_snap:
        reasons.append("no row before the hold or after release + one row period")
    elif _window_ok(rows, times, t_s0, t_snap):
        p_s, p_r, p_n, p_2 = (_pos_at(rows, times, t) for t in (t_s0, t_ref, t_net, t_snap))
        if None not in (p_s, p_r, p_n, p_2):
            net, snap = _ground(p_s, p_n), _ground(p_r, p_2)
    else:
        reasons.append("rows do not cover hold..release+2s")

    before = [e for e in pad_events if t_drift <= e.t < s]
    state = _pad_state_before(pad_events, t_drift)
    if any(not _fully_neutral(e) for e in before) or (state is not None and not _fully_neutral(state)):
        reasons.append("pad not neutral over the 10 s before the hold")
    elif t_s0 is not None and _window_ok(rows, times, t_drift, t_s0):
        p_d, p_s = _pos_at(rows, times, t_drift), _pos_at(rows, times, t_s0)
        if p_d is not None and p_s is not None:
            drift = _ground(p_d, p_s)
    else:
        reasons.append("rows do not cover the 10 s before the hold")

    fails = []
    if net is not None and net < CONTROL_NET_MIN_UNITS:
        fails.append(f"net {net:.1f} < {CONTROL_NET_MIN_UNITS:g}")
    if snap is not None and snap > CONTROL_SNAPBACK_MAX_UNITS:
        fails.append(f"snap-back {snap:.1f} > {CONTROL_SNAPBACK_MAX_UNITS:g}")
    if drift is not None and drift > CONTROL_DRIFT_MAX_UNITS:
        fails.append(f"drift {drift:.1f} > {CONTROL_DRIFT_MAX_UNITS:g}")
    if fails:
        return ControlVerdict(False, net, snap, drift, "FAIL", "; ".join(fails + reasons), hold)
    if None in (net, snap, drift):
        return ControlVerdict(False, net, snap, drift, NO_DATA, "; ".join(reasons) or "unmeasured", hold)
    return ControlVerdict(True, net, snap, drift, "PASS", "", hold)


def score_control_side(rows, pad_events, max_holds=PRECONDITION_MAX_HOLDS, unrecovered_pad_times=()):
    """Up to `max_holds` decisive (PASS/FAIL) forward holds, in order; the first PASS makes the side
    CONTROLLABLE. NO-DATA holds are kept in `holds` but do not count toward the cap."""
    scored, decisive = [], 0
    for h in forward_holds(pad_events):
        if h.release - h.start < FORWARD_HOLD_MIN_S:
            continue
        v = score_control(rows, pad_events, h, unrecovered_pad_times)
        scored.append(v)
        if v.status == "PASS":
            return SideControl(CONTROLLABLE, scored)
        if v.status == "FAIL":
            decisive += 1
            if decisive >= max_holds:
                break
    if decisive:
        return SideControl(NO_CONTROL, scored)
    return SideControl(NO_DATA, scored)


def control_result(sides):
    """{tag: SideControl} -> CONTROLLABLE | NO-CONTROL | NO-CONTROL side=<X> | NO-DATA.

    Any side NO-DATA makes the pair NO-DATA -- including NO-CONTROL on one side plus NO-DATA on the
    other: the side that was not measured cannot be called controllable, so the pair has no verdict."""
    if not sides:
        return NO_DATA
    if any(s.status == NO_DATA for s in sides.values()):
        return NO_DATA
    bad = sorted(tag for tag, s in sides.items() if s.status == NO_CONTROL)
    if not bad:
        return CONTROLLABLE
    if len(bad) == len(sides):
        return NO_CONTROL
    return f"{NO_CONTROL} side={','.join(bad)}"


# ---------------------------------------------------------------------------------------------
# move path
# ---------------------------------------------------------------------------------------------
def _latest(rows, t):
    best = None
    for r in rows:
        if r[0] <= t:
            best = r
        else:
            break
    return best


def score_move_path(call_indices_by_time, alive_rows, round_rows, now):
    """MoveScale liveness. call_indices_by_time: [(t, n)]; alive_rows: [(t, +0xF7A byte)];
    round_rows: [(t, mp_round_count)]; now: the time of the evaluation."""
    calls = sorted(call_indices_by_time)
    if not calls:
        return MovePathVerdict(NO_DATA, None, "the slot never logged a line")
    t_adv, top = None, None
    for t, n in calls:
        if t > now:
            break
        if top is None or n > top:
            top, t_adv = n, t
    if t_adv is None:
        return MovePathVerdict(NO_DATA, None, "no line at or before now")
    if now - t_adv < MOVE_STALL_S:
        return MovePathVerdict("ok", t_adv, f"#{top} at {t_adv:.1f}")

    alive = sorted(alive_rows)
    rounds = sorted(round_rows)
    stall = f"stall of {now - t_adv:.1f}s since #{top} at {t_adv:.1f}"
    if not alive:
        return MovePathVerdict(NO_DATA, t_adv, stall + "; +0xF7A never read -- death not excluded")
    if not rounds:
        return MovePathVerdict(NO_DATA, t_adv, stall + "; mp_round_count never read -- round change not excluded")

    last_alive = _latest(alive, now)
    if last_alive is None:
        return MovePathVerdict(NO_DATA, t_adv, stall + "; no +0xF7A read at or before now")
    if last_alive[1] != ALIVE_VALUE:
        return MovePathVerdict("disarmed", t_adv, stall + "; +0xF7A != 1")
    start = t_adv
    # the stall clock restarts when the actor comes back alive...
    prev = None
    for t, v in alive:
        if t > now:
            break
        if v == ALIVE_VALUE and prev is not None and prev != ALIVE_VALUE:
            start = max(start, t)
        prev = v
    # ...and is disarmed for 15 s after each round step
    last_step = None
    for (ta, va), (tb, vb) in zip(rounds, rounds[1:]):
        if tb <= now and vb != va:
            last_step = tb
    if last_step is not None and now - last_step < ROUND_STEP_DISARM_S:
        return MovePathVerdict("disarmed", t_adv, stall + f"; mp_round_count stepped at {last_step:.1f}")
    if last_step is not None:
        start = max(start, last_step + ROUND_STEP_DISARM_S)   # the stall clock starts when the disarm ends
    if now - start < MOVE_STALL_S:
        return MovePathVerdict("disarmed", t_adv, stall + f"; re-armed at {start:.1f}")
    return MovePathVerdict("stalled", start, stall)


# ---------------------------------------------------------------------------------------------
# starvation
# ---------------------------------------------------------------------------------------------
def _episodes(rows, pred):
    eps, cur = [], None
    for t, v in sorted(rows):
        if pred(v):
            if cur is None:
                cur = [t, t]
            cur[1] = t
        elif cur is not None:
            eps.append(tuple(cur))
            cur = None
    if cur is not None:
        eps.append(tuple(cur))
    return eps


def score_starvation(netidle_rows, lagflag_rows, side="?", move_path=None):
    """netidle_rows: [(t, ms)] from NetIdleMs [ret] v0; lagflag_rows: [(t, ng+0xde byte)];
    move_path: this side's MovePathVerdict, when known."""
    if not netidle_rows:
        return StarvationVerdict(NO_DATA, side, detail="no NetIdle rows (NetIdle stops with the move path)")
    if move_path is not None and move_path.status != "ok":
        return StarvationVerdict(NO_DATA, side, detail=f"move path {move_path.status}: ng+0xde and NetIdle are stale")
    peak = max(v for _, v in netidle_rows)
    lag_eps = _episodes(lagflag_rows, lambda v: v == 1)
    idle_eps = _episodes(netidle_rows, lambda v: v >= NETIDLE_ALARM_MS)
    bar_ok = peak <= NETIDLE_BAR_MS
    cands = [(e[0], "ng+0xde") for e in lag_eps[:1]] + [(e[0], "NetIdle") for e in idle_eps[:1]]
    detail = f"netidle rows={len(netidle_rows)} peak={peak}ms lagflag rows={len(lagflag_rows)}"
    if cands:
        since, signal = min(cands)
        return StarvationVerdict("alarm", side, since, signal, peak, bar_ok,
                                 [("ng+0xde",) + e for e in lag_eps] + [("NetIdle",) + e for e in idle_eps], detail)
    return StarvationVerdict("ok", side, None, None, peak, bar_ok, [], detail)


# ---------------------------------------------------------------------------------------------
# valves, the CZNetGame block, the clock string
# ---------------------------------------------------------------------------------------------
def read_valve(peek_item, expected_name_ptr):
    """peek_item: (addr, words) of `*0x437ce8+<off>*:2`. Word 0 is the name pointer; the value is the
    signed short at +4 (low 16 bits of word 1). Wrong/missing name pointer -> NoData."""
    if peek_item is None:
        return NoData("valve item missing")
    _, words = peek_item
    if len(words) < 2:
        return NoData(f"valve item has {len(words)} word(s), need 2")
    if words[0] != expected_name_ptr:
        return NoData(f"name pointer {words[0]:08x} != {expected_name_ptr:08x}")
    v = words[1] & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def valve_rows(peek_rows, expected_name_ptr):
    """[(t, value)] for the valve whose name pointer matches, found in each row by content."""
    out = []
    for t, items in peek_rows:
        for item in items:
            if len(item[1]) == 2 and item[1][0] == expected_name_ptr:
                v = read_valve(item, expected_name_ptr)
                if not isinstance(v, NoData):
                    out.append((t, v))
                break
    return out


def ng_lagflag_rows(peek_rows):
    """[(t, ng+0xde byte)] from the CZNetGame block, identified by +0x118 == 50.0f."""
    wi, shift = NG_LAG_FLAG_OFFSET // 4, 8 * (NG_LAG_FLAG_OFFSET % 4)
    out = []
    for t, items in peek_rows:
        for _, words in items:
            if len(words) > max(NG_FINGERPRINT_WORD, wi) and words[NG_FINGERPRINT_WORD] == NG_FINGERPRINT_VALUE:
                out.append((t, (words[wi] >> shift) & 0xFF))
                break
    return out


def clock_rows(peek_rows, addr=CLOCK_STRING_ADDR):
    """[(t, string)] from a `0x408f10:<n>` item: words little-endian, up to the first NUL, printable."""
    out = []
    for t, items in peek_rows:
        for a, words in items:
            if a == addr and words:
                raw = b"".join(struct.pack("<I", w) for w in words).split(b"\0", 1)[0]
                if raw and all(0x20 <= c < 0x7F for c in raw):
                    out.append((t, raw.decode("ascii")))
                break
    return out


# ---------------------------------------------------------------------------------------------
# contact
# ---------------------------------------------------------------------------------------------
def _advancing(calls, times, t):
    """A logged call in (t - window, t] whose #n beats every #n logged before the window."""
    k1 = bisect.bisect_right(times, t)
    k0 = bisect.bisect_right(times, t - CONTACT_ADVANCE_WINDOW_S)
    if k1 <= k0:
        return False
    before = max((n for _, n in calls[:k0]), default=-1)
    return max(n for _, n in calls[k0:k1]) > before


def score_contact(rowsA, rowsB, callsA, callsB, clock_rows, scale_rows):
    """rowsA/rowsB: actor rows (t, x, y, z, ...) on ONE clock; callsA/callsB: MoveScale [(t, n)];
    clock_rows: [(t, string)]; scale_rows: ([(t, f12)] for A, [(t, f12)] for B).

    Pairing: A's rows are the reference; each A row is paired with B's row nearest in time, if within
    CONTACT_PAIR_MAX_S (so one B row may serve up to two A rows). A row qualifies only if A's previous
    row and the paired B row's previous row are each within CONTACT_ROW_MAX_GAP_S, plus the gate,
    move-path, clock and scale clauses. contact_rows is the longest consecutive run of qualifying A
    rows. No pair formed at all (e.g. misaligned clocks) is NO-DATA, not zero contact."""
    rowsA, rowsB = sorted(rowsA), sorted(rowsB)
    rows_read = len(rowsA) + len(rowsB)
    missing = [name for name, rows in (("A rows", rowsA), ("B rows", rowsB), ("A MoveScale", callsA),
                                       ("B MoveScale", callsB), ("clock", clock_rows),
                                       ("A f12", scale_rows[0]), ("B f12", scale_rows[1])) if not rows]
    tb = [r[0] for r in rowsB]
    ca, cb = sorted(callsA), sorted(callsB)
    ta_c, tb_c = [c[0] for c in ca], [c[0] for c in cb]
    clock = sorted(clock_rows)
    tc = [c[0] for c in clock]
    sa, sb = sorted(scale_rows[0]), sorted(scale_rows[1])
    tsa, tsb = [s[0] for s in sa], [s[0] for s in sb]

    closest, closest_dy = None, None
    run = best = total = pairs = 0
    for ia, a in enumerate(rowsA):
        t = a[0]
        k = bisect.bisect_left(tb, t)
        cand = [j for j in (k - 1, k) if 0 <= j < len(rowsB) and abs(rowsB[j][0] - t) <= CONTACT_PAIR_MAX_S]
        ok = False
        if cand:
            pairs += 1
            jb = min(cand, key=lambda j: abs(rowsB[j][0] - t))
            b = rowsB[jb]
            gaps_ok = ((ia == 0 or t - rowsA[ia - 1][0] <= CONTACT_ROW_MAX_GAP_S)
                       and (jb == 0 or b[0] - rowsB[jb - 1][0] <= CONTACT_ROW_MAX_GAP_S))
            d3 = math.dist(a[1:4], b[1:4])
            dy = abs(a[2] - b[2])
            if closest is None or d3 < closest:
                closest, closest_dy = d3, dy
            ok = (d3 <= CONTACT_3D_MAX_UNITS and dy <= CONTACT_DY_MAX_UNITS
                  and gaps_ok and not missing
                  and _advancing(ca, ta_c, t) and _advancing(cb, tb_c, t)
                  and _clock_changing(clock, tc, t)
                  and _scale_live(sa, tsa, t) and _scale_live(sb, tsb, t))
        if ok:
            run += 1
            total += 1
            best = max(best, run)
        else:
            run = 0
    if missing:
        return ContactResult(0, 0, rows_read, NO_DATA, "no " + ", no ".join(missing), closest, closest_dy)
    if pairs == 0:
        return ContactResult(0, 0, rows_read, NO_DATA,
                             f"no A row had a B row within {CONTACT_PAIR_MAX_S:g}s (clocks misaligned?)")
    return ContactResult(best, total, rows_read, "ok", "", closest, closest_dy)


def _clock_changing(clock, tc, t):
    k1 = bisect.bisect_right(tc, t)
    k0 = bisect.bisect_left(tc, t - CONTACT_CLOCK_WINDOW_S)
    return len({s for _, s in clock[max(0, k0):k1]}) >= 2


def _scale_live(scales, ts, t):
    k = bisect.bisect_right(ts, t) - 1
    return k >= 0 and t - scales[k][0] <= CONTACT_SCALE_MAX_AGE_S and scales[k][1] >= CONTACT_SCALE_MIN


# ---------------------------------------------------------------------------------------------
# CLI -- the only IO in this module
# ---------------------------------------------------------------------------------------------
_SIDE_RE = re.compile(r"(?:^|[_\-.])([AB])(?=[_\-.]|$)")


def side_tag(path, fallback):
    m = _SIDE_RE.search(os.path.basename(path))
    return m.group(1) if m else fallback


def _read(path):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read().split("\n")
    except OSError as e:
        print(f"cannot read {path}: {e}")
        return []


def _rows_read(tag, path, p):
    print(f"[{tag}] {path}")
    print(f"[{tag}] rows read: lines={p.lines} peek={len(p.peek_rows)} actor={len(p.actor_rows)} "
          f"pad={len(p.pad_events)} pad_torn={p.torn_pad_lines} pad_unrecovered={p.unrecovered_pad_lines} "
          f"clock_anchors={p.clock_anchors} "
          + " ".join(f"call[{k}]={len(v)}" for k, v in sorted(p.calls.items()))
          + (" " if p.rets else "") + " ".join(f"ret[{k}]={len(v)}" for k, v in sorted(p.rets.items())))


def _fmt(v):
    return "  n/a" if v is None else f"{v:6.2f}"


def _load_all(paths):
    out = []
    for i, path in enumerate(paths):
        tag = side_tag(path, "AB"[i] if i < 2 else str(i))
        out.append((tag, path, parse_log(_read(path))))
    return out


def _cmd_control(args):
    sides, zero = {}, False
    for tag, path, p in _load_all(args.logs):
        _rows_read(tag, path, p)
        if not p.actor_rows:
            zero = True
        side = score_control_side(p.actor_rows, p.pad_events, unrecovered_pad_times=p.unrecovered_pad_times)
        for v in side.holds:
            h = v.hold
            print(f"[{tag}] hold {h.start:8.2f}..{h.release:8.2f} ({h.release - h.start:4.2f}s) "
                  f"net={_fmt(v.net_units)} snap={_fmt(v.snapback_units)} drift={_fmt(v.drift_units)} "
                  f"-> {v.status}{' (' + v.reason + ')' if v.reason else ''}")
        print(f"[{tag}] side {side.status} ({len(side.holds)} hold(s) scored)")
        sides[tag] = side
    res = control_result(sides)
    if zero:
        res = NO_DATA
    print(f"RESULT {res}")
    return 0 if res == CONTROLLABLE else (2 if res == NO_DATA else 3)


def _cmd_move_path(args):
    worst = 0
    for tag, path, p in _load_all(args.logs):
        _rows_read(tag, path, p)
        calls = [(t, n) for t, n, *_ in p.calls.get(args.name, [])]
        now = p.peek_rows[-1][0] if p.peek_rows else (calls[-1][0] if calls else 0.0)
        alive = []   # +0xF7A: not in any Sprint 4 PEEK spec; Step 1 wires the read
        rounds = valve_rows(p.peek_rows, args.round_name_ptr) if args.round_name_ptr is not None else []
        v = score_move_path(calls, alive, rounds, now)
        lines = len(calls)
        span = f"#{calls[0][1]}..#{calls[-1][1]} over {calls[0][0]:.1f}..{calls[-1][0]:.1f}s" if calls else "none"
        print(f"[{tag}] {args.name} lines={lines} ({span}) alive rows={len(alive)} round rows={len(rounds)} now={now:.1f}")
        print(f"[{tag}] MOVE-PATH {v.status} since={v.since} -- {v.detail}")
        code = {"ok": 0, "disarmed": 0, "stalled": 1}.get(v.status, 2)
        if not p.peek_rows and not calls:
            code = 2
        worst = max(worst, code)
    return worst


def _cmd_starvation(args):
    worst = 0
    for tag, path, p in _load_all(args.logs):
        _rows_read(tag, path, p)
        idle = [(t, v) for t, _, v in p.rets.get(args.name, [])]
        lag = ng_lagflag_rows(p.peek_rows)
        calls = [(t, n) for t, n, *_ in p.calls.get(MOVE_SCALE_NAME, [])]
        now = p.peek_rows[-1][0] if p.peek_rows else 0.0
        mp = score_move_path(calls, [], [], now) if calls else None   # a stall -> NO-DATA -> starvation NO-DATA
        v = score_starvation(idle, lag, side=tag, move_path=mp)
        print(f"[{tag}] {args.name} rows={len(idle)} ng+0xde rows={len(lag)}")
        print(f"[{tag}] STARVATION {v.status} since={v.since} signal={v.signal} peak_ms={v.peak_ms} "
              f"bar_ok={v.bar_ok} -- {v.detail}")
        worst = max(worst, {"ok": 0, "alarm": 1}.get(v.status, 2))
    return worst


def _cmd_contact(args):
    loaded = _load_all(args.logs)
    if len(loaded) != 2:
        print("contact needs exactly two logs (A then B)")
        return 2
    (ta, pa_path, pa), (tb, pb_path, pb) = loaded
    _rows_read(ta, pa_path, pa)
    _rows_read(tb, pb_path, pb)
    if args.offset_b is not None:
        off, how = args.offset_b, "--offset-b"
    else:
        ca0 = [t for t, n, *_ in pa.calls.get(MOVE_SCALE_NAME, []) if n == 0]
        cb0 = [t for t, n, *_ in pb.calls.get(MOVE_SCALE_NAME, []) if n == 0]
        if ca0 and cb0:
            off, how = ca0[0] - cb0[0], "MoveScale #0 on both (round start)"
        elif pa.actor_rows and pb.actor_rows:
            off, how = pa.actor_rows[0][0] - pb.actor_rows[0][0], "first actor row on both"
        else:
            off, how = 0.0, "none"
    print(f"clock alignment: B + {off:.2f}s ({how}); blind: round-start delivery can differ by instance")
    sh = lambda rows: [(r[0] + off,) + tuple(r[1:]) for r in rows]
    rows_b = sh(pb.actor_rows)
    calls_a = [(t, n) for t, n, *_ in pa.calls.get(MOVE_SCALE_NAME, [])]
    calls_b = [(t + off, n) for t, n, *_ in pb.calls.get(MOVE_SCALE_NAME, [])]
    scales_a = [(t, f) for t, n, f, *_ in pa.calls.get(MOVE_SCALE_NAME, []) if f is not None]
    scales_b = [(t + off, f) for t, n, f, *_ in pb.calls.get(MOVE_SCALE_NAME, []) if f is not None]
    clock = clock_rows(pa.peek_rows) or sh(clock_rows(pb.peek_rows))
    r = score_contact(pa.actor_rows, rows_b, calls_a, calls_b, clock, (scales_a, scales_b))
    print(f"clock rows={len(clock)} closest_3d={_fmt(r.closest_3d)} dy_at_closest={_fmt(r.closest_dy)} "
          f"qualifying={r.total_rows} status={r.status}{' (' + r.reason + ')' if r.reason else ''}")
    print(f"LADDER contact_rows={r.contact_rows} rows_read={r.rows_read}")
    return 2 if (r.status == NO_DATA or r.rows_read == 0) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tools_py.parity.verdict_core",
                                 description="Pure online verdicts over run logs. Exit 2 = NO-DATA.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("score-control", help="the spec's movement bar per side (exit 0 / 3 NO-CONTROL / 2)")
    c.add_argument("logs", nargs="+")
    m = sub.add_parser("move-path", help="MoveScale #n liveness (exit 0 ok|disarmed / 1 stalled / 2)")
    m.add_argument("logs", nargs="+")
    m.add_argument("--name", default=MOVE_SCALE_NAME)
    m.add_argument("--round-name-ptr", type=lambda s: int(s, 0), default=None,
                   help="name pointer of the mp_round_count valve (identifies its peek item)")
    s = sub.add_parser("starvation", help="ng+0xde / NetIdle (exit 0 ok / 1 alarm / 2)")
    s.add_argument("logs", nargs="+")
    s.add_argument("--name", default=NET_IDLE_NAME)
    k = sub.add_parser("contact", help="contact rows between A and B (exit 0 / 2)")
    k.add_argument("logs", nargs="+")
    k.add_argument("--offset-b", type=float, default=None, help="seconds added to B's clock")
    args = ap.parse_args(argv)
    return {"score-control": _cmd_control, "move-path": _cmd_move_path,
            "starvation": _cmd_starvation, "contact": _cmd_contact}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
