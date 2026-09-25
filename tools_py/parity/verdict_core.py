"""Pure online verdict scorers: is a side controllable, is its move path alive, is it network-starved,
is a valve read trustworthy, and how many contact rows occurred -- decided from log rows.

Sprint 5 Task 3 Step 0 (Steps 1-5 added the row readers the live harness shares: valves by name bytes,
actor fields, the R6 stall context). PURE: the parse functions take lines/strings, the scorers take rows, and
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

from tools_py.parity import guest_addresses as ga

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
# These three, and sp_death_probe's ACTOR_STATIC, are the r0001 column of guest_addresses.PROBE_ADDRESSES
# -- read from it, not repeated here (Task 19 review F6: this module, sp_death_probe and guest_probe each
# held their own copy of the same four numbers, and nothing would have noticed them drifting apart). The
# ladder these constants serve runs on the r0001 build, so it takes the r0001 column by name; guest_probe,
# which has to read an r0004 run, takes a revision.
ACTOR_VTABLE = ga.address("actor_vtable", "r0001")     # 0x6691a0, word 0 of the player actor block
# actor +0x1c/+0x20/+0x24 = x, y, z, as WORD INDICES into a peeked block. Layout, so it comes from
# guest_addresses.PROBE_OFFSETS' r0001 column like move_scale and root_node do -- one home for
# displacements as well as addresses (Task 19 review F6 + the move lane's concern 2).
ACTOR_POS_WORDS = tuple(ga.offset("actor_pos", "r0001") // 4 + i for i in range(3))
CAMERA_RECORD_ADDR = ga.address("camera_record", "r0001")   # 0x416054, the camera-orbit record; NOT the player (research/18 §4.1)
MOVE_SCALE_NAME = "MoveScale"      # PS2X_CALL_TRACE="0x553dc0:MoveScale"
NET_IDLE_NAME = "NetIdleMs"        # PS2X_CALL_TRACE="0x30cd80:NetIdleMs" (the thunk, research/18 §3.12a)
NET_IDLE_NAMES = ("NetIdle", NET_IDLE_NAME)   # launch 1 (research/21 §6.1) and Task 5 name the slot NetIdle
CLOCK_STRING_ADDR = ga.address("clock_string", "r0001")   # 0x408f10, round clock string (research/19 F2)

# ... and the same four as the set of EVERY revision's value, for the readers that identify a row's
# contents rather than build a launch (Sprint 11 Task 19, the r0004 online lane). A `[peek]` row carries
# exactly one revision's numbers, so "is this item the round clock" can be asked without plumbing a
# revision through a LEAF module that has none to plumb. The scalars above stay r0001 and stay what every
# existing caller gets; these are for the row readers.
#
# WHAT IS PROVEN, EXACTLY (review F5). For the four ADDRESS sets the argument is disjointness: no name's
# r0004 address is any name's r0001 address, held in both directions by
# `test_online_instruments.test_neither_render_carries_one_address_of_the_other_column`, so an item
# address can only be matched by its own column. ACTOR_VTABLES is different in kind: it is a VALUE read
# out of word 0, not an item address, and 0x00668B20 is -0x680 from 0x006691A0 -- inside r0001's own
# vtable region, so nothing in the table rules out some OTHER r0001 object carrying it. Two things
# protect it and neither is disjointness: `next()` takes the FIRST matching item and the canonical spec
# puts the actor block at item 1, and the archive says it does not happen -- over 4781 r0001 [peek] rows
# the only vtable-region word 0 seen is 0x6691a0 (308 times) and 0x668b20 never occurs
# (`test_online_instruments.test_no_archived_r0001_row_carries_the_r0004_vtable` holds that on a
# checked-in fixture). If a future revision's vtable ever collides, this is the comment that says why
# the fix is to pass the revision in, not to widen the set.
ACTOR_VTABLES = frozenset(ga.address("actor_vtable", r) for r in ga.REVISIONS)
CAMERA_RECORD_ADDRS = frozenset(ga.address("camera_record", r) for r in ga.REVISIONS)
ROUND_TIME_ADDRS = frozenset(ga.address("guest_clock", r) for r in ga.REVISIONS)
CLOCK_STRING_ADDRS = frozenset(ga.address("clock_string", r) for r in ga.REVISIONS)
MP_FLAG_WORD_ADDRS = frozenset(ga.address("mp_flag_word", r) for r in ga.REVISIONS)
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
# Snap-back <= 10: the peak ground-plane excursion from the hold-start row over rows in [release,
# release + 2 s], minus the excursion at release + 2 s (controller ruling, fix round 2; score_control).
# Measured against: the record keeps moving about one sample after release (§3.12: "stops one sample
# after release"), which raises peak and final together. Blind: a correction arriving later than 2 s;
# a correction that begins and ends entirely between two rows.
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
# An alive read older than this at `now` no longer describes the actor (fix round 1, M-1): after a
# death the actor block can stop being identified, and a last read of 1 would keep the watch armed
# into a false stall. 8 rows at 4 Hz; ~3 at kill2 B's 0.6 s/row under load. Blind: a sampler slower
# than 2 s/row reads as NO-DATA, not stalled.
ALIVE_MAX_AGE_S = 2.0
# NetIdle [ret] v0 (ms): alarm at 4000, bar <= 5000. Measured against: the scale holds 1.0 until idle
# > 5500 ms (§3.12 "timing, corrected"), the game's own lag flag at >= 4501 ms, Sprint 4's healthy
# worst gap 2.7 s and idle capped at 1490 ms in the fixed A/B (§3.12a). Blind: peaks between ~0.5 s
# samples; ng+0xde is stale when the move path is silent (then NO-DATA).
NETIDLE_ALARM_MS = 4000
NETIDLE_BAR_MS = 5000
# Contact (spec §5.1, Amendment A -- registered pre-match, REPLACING Goal 5(a)'s 3-D <= 22 and >= 20 consecutive rows):
# the engagement band is the same floor |dy| <= 10 and 3-D <= 45; contact is >= 5.0 s of qualifying time over >= 10
# rows with row gaps <= 1.25 s, a guest-clock freeze inside the window pausing the count; the sampler period is
# reported beside it. Blind: shots through a wall on the same floor; line of sight; aiming away.
CONTACT_3D_MAX_UNITS = 45.0
CONTACT_DY_MAX_UNITS = 10.0
CONTACT_MIN_S = 5.0
CONTACT_MIN_ROWS = 10
CONTACT_SCALE_MIN = 0.99           # both sides' latest f12; closes the starved-pair-in-the-gate class
# Pairing: B's row nearest A's within two 4 Hz samples. Blind: a 0.5 s misalignment at 40 u/s is 20
# units -- the two process clocks must be aligned by the caller first (see main's --offset-b).
CONTACT_PAIR_MAX_S = 0.5
# A row counts only if its own side's previous row is at most this far back, on BOTH sides: a stalled
# sampler must not stretch one position over several rows of the other side. Measured against kill2 B,
# whose sampler slowed to ~0.6 s/row in the fight: worst gap 1.06 s (review's clock) / 1.08 s (this
# parser's clock) at t ~ 704 s, and 0.92 s inside the closest-approach window 658-688 s -- so a slow
# but healthy sampler still counts. The hung-instance class is guarded by the clock-changing and
# #n-advancing clauses, not by this. Blind: a stall of <= 1.25 s is bridged (controller ruling,
# fix round 2).
CONTACT_ROW_MAX_GAP_S = 1.25
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
    contact_rows: int                   # qualifying rows in the best run (the run with the most qualifying time)
    total_rows: int                     # qualifying rows, not necessarily consecutive
    rows_read: int
    status: str                         # ok | NO-DATA
    reason: str = ""
    closest_3d: object = None
    closest_dy: object = None
    contact_s: float = 0.0              # qualifying host seconds of the best run, paused spans excluded
    sampler_period_s: object = None     # median gap between A's actor rows
    paused_rows: int = 0                # A rows inside a guest-clock pause of either instance (neither break nor count)
    ok: bool = False                    # contact_s >= CONTACT_MIN_S and contact_rows >= CONTACT_MIN_ROWS


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
        actor = next(((a, w) for a, w in items if w and w[0] in ACTOR_VTABLES), None)
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

    # Pad events carry +-1/2 sampler period of timing error (parse_log puts them midway between two
    # rows), so no position is interpolated AT an event time: the hold's start reference is the last
    # row at or before the start event (sampled before the game saw the press), and the drift window
    # is the 10 s ending at that row.
    #
    # Snap-back is measured from the PEAK excursion, independent of the row period:
    #   snapback = max(0, max_{rows t in [release, release+2s]} |p(t) - p_start| - |p(release+2s) - p_start|)
    # Coasting forward after release raises the peak and the final displacement together, so it does
    # not count; a correction counts as soon as any row saw the pre-correction position. Blind: a
    # correction that begins and ends entirely between two rows is unobservable (at 0.6 s/row, one
    # shorter than ~0.6 s that no row straddles).
    k_s = bisect.bisect_right(times, s) - 1
    t_s0 = times[k_s] if k_s >= 0 else None
    if t_s0 is not None:
        t_drift = t_s0 - CONTROL_DRIFT_WINDOW_S

    torn_inside = [u for u in unrecovered_pad_times if t_drift <= u <= t_snap]
    if torn_inside:
        return ControlVerdict(False, None, None, None, NO_DATA,
                              f"unrecovered torn pad line at {torn_inside[0]:.2f}", hold)

    after = [e for e in pad_events if r < e.t <= t_snap and not _sticks_neutral(e)]
    net = snap = drift = None
    window_rows = [row for row in rows if r <= row[0] <= t_snap]
    if after:
        reasons.append(f"stick input {after[0].t - r:+.2f}s after release")
    elif t_s0 is None or not window_rows:
        reasons.append("no row before the hold or none in release..release+2s")
    elif _window_ok(rows, times, t_s0, t_snap):
        p_s, p_n, p_2 = (_pos_at(rows, times, t) for t in (t_s0, t_net, t_snap))
        if None not in (p_s, p_n, p_2):
            net = _ground(p_s, p_n)
            peak = max(_ground(p_s, (row[1], row[3])) for row in window_rows)
            snap = max(0.0, peak - _ground(p_s, p_2))
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
    if now - last_alive[0] > ALIVE_MAX_AGE_S:
        return MovePathVerdict(NO_DATA, t_adv, stall + f"; +0xF7A read stale ({now - last_alive[0]:.1f}s old "
                                                       f"> {ALIVE_MAX_AGE_S:g}s) -- death not excluded")
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
    if not lagflag_rows and not idle_eps:
        # Ruling R23: ng+0xde is the PRIMARY signal (spec §5(c)). Without it a quiet NetIdle is not
        # "healthy" -- launch 1c read 0 lag rows through a parser defect and this said ok. A NetIdle
        # alarm is positive evidence and still alarms (below).
        return StarvationVerdict(NO_DATA, side, None, None, peak, bar_ok, [], "ng+0xde never read; " + detail)
    if cands:
        since, signal = min(cands)
        return StarvationVerdict("alarm", side, since, signal, peak, bar_ok,
                                 [("ng+0xde",) + e for e in lag_eps] + [("NetIdle",) + e for e in idle_eps], detail)
    return StarvationVerdict("ok", side, None, None, peak, bar_ok, [], detail)


# ---------------------------------------------------------------------------------------------
# guest-clock pauses: freezes and round boundaries (spec §5.1.1 "Freeze detection", R53/R60)
# ---------------------------------------------------------------------------------------------
# DAT_004365c0 advances 0.57-0.72 guest s per host s over whole rounds and changes on every 4 Hz row while the guest
# runs. A FREEZE is any stall >= 1.0 s after merging stalls separated by at most one advancing row (launch 8c A: 54.402
# still 500.71-505.63, ONE row at 55.487, 55.587 still 506.13-514.07 is one freeze), or a window whose clock advance is
# below 25 % of its host span. The pause from an mp_round_count step to the clock restart (8c: 5.54 s, starting on the
# step's own row) is the ROUND BOUNDARY, not a freeze. Blind: a guest that runs its clock but not its world.
FREEZE_STALL_S = 1.0
FREEZE_RATE_MIN = 0.25
FREEZE_RATE_WINDOW_S = 4.0         # the rate clause's window (a 1 s stall inside 4 s of normal rate stays >= 25 %)
FREEZE_MERGE_ROWS = 2              # stalls whose rows are at most this many indices apart merge (one advancing row)
# R63 (registered pre-match, instrument parameters): a round boundary is the mp_round_count step +-0.5 s host to the
# clock restart + 1.25 s, at most 10 s long; a stall inside that span is the boundary, not a freeze. Blind: a genuine
# freeze that begins exactly on a round step reads as the boundary.
ROUND_BOUNDARY_MATCH_S = 0.5       # a pause starting within this of an mp_round_count step is that step's boundary
ROUND_BOUNDARY_TAIL_S = 1.25       # ... and so is a stall starting within this after the boundary's clock restart
ROUND_BOUNDARY_MAX_S = 10.0        # ... for at most this long (8c: 5.54 s); the rest of a longer pause is a freeze


def round_steps(round_rows):
    """[(t, mp_round_count)] -> the times at which the value changed (the row carrying the new value)."""
    out, prev = [], None
    for t, v in sorted(round_rows, key=lambda r: r[0]):
        if prev is not None and v != prev:
            out.append(t)
        prev = v
    return out


def _union(spans):
    out = []
    for a, b, g in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b), out[-1][2] or g)
        else:
            out.append((a, b, g))
    return out


def clock_pauses(rows, round_steps=(), stall_s=FREEZE_STALL_S):
    """rows: [(t, guest clock)] -> [(t_first, t_last, ongoing, kind)] sorted, kind 'freeze' | 'round'. `ongoing`: the
    newest row is inside the pause (the clock has not moved since). No rows -> []."""
    rows = sorted(rows, key=lambda r: r[0])
    n = len(rows)
    if n < 2:
        return []
    stalls, i = [], 0
    while i < n:
        j = i
        while j + 1 < n and rows[j + 1][1] == rows[i][1]:
            j += 1
        if j > i:
            if stalls and i - stalls[-1][1] <= FREEZE_MERGE_ROWS:
                stalls[-1][1] = j
            else:
                stalls.append([i, j])
        i = j + 1
    steps = sorted(round_steps)
    pauses, span = [], None                           # span: (boundary start, latest end) of the current round boundary
    for a, b in stalls:
        t0, t1, ongoing = rows[a][0], rows[b][0], b == n - 1
        if t1 - t0 < stall_s:
            continue
        step = next((s for s in steps if t0 - ROUND_BOUNDARY_MATCH_S <= s <= t0 + ROUND_BOUNDARY_MATCH_S), None)
        if step is not None:
            span = (min(t0, step), t1)
        elif span is not None and t0 <= span[1] + ROUND_BOUNDARY_TAIL_S and t0 < span[0] + ROUND_BOUNDARY_MAX_S:
            span = (span[0], t1)                        # a stall just after the restart is still the boundary
        else:
            span = None
            pauses.append((t0, t1, ongoing, "freeze"))
            continue
        end = span[0] + ROUND_BOUNDARY_MAX_S
        if t1 <= end:
            pauses.append((t0, t1, ongoing, "round"))
        else:
            pauses.append((t0, end, False, "round"))
            pauses.append((end, t1, ongoing, "freeze"))
    rounds = [p for p in pauses if p[3] == "round"]
    # the rate clause adds only windows no stall pause already explains (a window reaching into a stall would
    # stretch that stall's edges by up to FREEZE_RATE_WINDOW_S)
    slow, j = [], 0
    for i in range(n):
        while j < n and rows[j][0] - rows[i][0] < FREEZE_RATE_WINDOW_S:
            j += 1
        if j >= n:
            break
        span, adv = rows[j][0] - rows[i][0], rows[j][1] - rows[i][1]
        if 0.0 <= adv < FREEZE_RATE_MIN * span and not any(p[0] <= rows[j][0] and p[1] >= rows[i][0] for p in pauses):
            slow.append((rows[i][0], rows[j][0], j == n - 1))
    freezes = _union([p[:3] for p in pauses if p[3] == "freeze"] + slow)
    return sorted(rounds + [(a, b, g, "freeze") for a, b, g in freezes])


# ---------------------------------------------------------------------------------------------
# valves, the CZNetGame block, the clock string
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Valve:
    name: str
    value_item: str          # PS2X_PEEK item carrying (name pointer, value)
    name_item: str           # PS2X_PEEK item printed AT the name pointer: the name's first 12 bytes
    ours_name_ptr: int       # research/21 §2.1, ours only -- NEVER a PCSX2 run's (+0x20/+0x30/+0x40 there)


# research/21 §2.1-§2.2. Identity is the NAME BYTES (platform- and heap-independent); the pointer
# column is kept only for the pointer-mode read and the CLI's --round-name-ptr. mission_abort's
# name item is `*<mission_abort_valve>*:3`: `*<mission_abort_valve>` already lands on the valve, and
# launch 1c's `**:3` form dereferenced the name bytes themselves (@7373696d on every row, research/21 §6.2).
#
# Every guest number here is READ FROM guest_addresses by name (Sprint 13 Task H6, audit harness-tools
# H22). The chains are rendered in r0001's addresses, spelled `"%#x"` exactly as `chain_for` expects, and
# `chain_for` re-renders them per revision. The NAME POINTERS are r0001-only: they are heap addresses
# (above every PT_LOAD segment of the image), `data_via_twin` cannot place them, and the table leaves their
# r0004 cells absent with that reason (guest_addresses.UNPLACED). So the pointer mode --
# `valve_rows` and move-path's --round-name-ptr -- is r0001-only, and the CLI refuses it on a log that
# is not r0001's (`pointer_mode_refusal`); everything that scores identifies a valve by its name bytes.
_NET_GAME = "%#x" % ga.address("net_game", "r0001")
_ABORT_VALVE = "%#x" % ga.address("mission_abort_valve", "r0001")
_VALVE_OFFSETS = (("mp_round_count", 0x0c), ("mp_game_over", 0x10), ("player_team", 0x14),
                  ("mp_major_game_state", 0x20), ("mp_minor_game_state", 0x24), ("late_joiner", 0x2c),
                  ("aiteam_00", 0x58), ("aiteam_08", 0x5c), ("total_mp_kills", 0x70))
VALVES = {v.name: v for v in (
    [Valve(name, f"*{_NET_GAME}+{off:#04x}*:2", f"*{_NET_GAME}+{off:#04x}**:3",
           ga.address("valve_name." + name, "r0001")) for name, off in _VALVE_OFFSETS]
    + [Valve("mission_abort", f"*{_ABORT_VALVE}:2", f"*{_ABORT_VALVE}*:3",
             ga.address("valve_name.mission_abort", "r0001"))]
)}
ROUND_VALVES = ("mp_round_count", "mp_game_over", "aiteam_00", "aiteam_08")
NAME_BYTES = 12                        # three words; aiteam_00/_08 differ only in byte 8


def name_bytes_match(words, name):
    """The first 12 bytes at the name pointer spell `name` (through its NUL when it is shorter).
    Bytes after the NUL are not compared: they are whatever follows the string in the registry."""
    if len(words) < NAME_BYTES // 4:
        return False
    raw = b"".join(struct.pack("<I", w & 0xFFFFFFFF) for w in words[:NAME_BYTES // 4])
    want = (name.encode("ascii") + b"\0")[:NAME_BYTES]
    return raw[:len(want)] == want


def _short(words):
    v = words[1] & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def read_valve(peek_item, expected_name_ptr, name_item=None, expected_name=None):
    """peek_item: (addr, words) of `*0x437ce8+<off>*:2`. Word 0 is the name pointer; the value is the
    signed short at +4 (low 16 bits of word 1).

    Two identities:
      * by POINTER (expected_name_ptr): word 0 must equal it. Platform-specific (research/21 §2.1).
      * by NAME BYTES (expected_name + name_item, the `**:3` item): the name item must spell the
        name AND be printed at the address word 0 points to. Heap-, build- and platform-independent.
    Anything that does not hold -> NoData."""
    if peek_item is None:
        return NoData("valve item missing")
    _, words = peek_item
    if len(words) < 2:
        return NoData(f"valve item has {len(words)} word(s), need 2")
    if expected_name is not None:
        if name_item is None:
            return NoData(f"no name-bytes item for {expected_name}")
        n_addr, n_words = name_item
        if not name_bytes_match(n_words, expected_name):
            return NoData(f"name bytes at {n_addr:08x} do not spell {expected_name}")
        if words[0] != n_addr:
            return NoData(f"name pointer {words[0]:08x} != name item address {n_addr:08x}")
        if expected_name_ptr is not None and words[0] != expected_name_ptr:
            return NoData(f"name pointer {words[0]:08x} != {expected_name_ptr:08x}")
        return _short(words)
    if words[0] != expected_name_ptr:
        return NoData(f"name pointer {words[0]:08x} != {expected_name_ptr:08x}")
    return _short(words)


def row_valve(items, name):
    """One peek row's value of the valve called `name`, identified by its name bytes (never by
    position or pointer): the 3-word item that spells the name, then the 2-word item whose word 0 is
    that item's address. NoData with the reason otherwise."""
    names = [it for it in items if len(it[1]) >= 3 and name_bytes_match(it[1], name)]
    if not names:
        return NoData(f"no name-bytes item spells {name}")
    for n_item in names:
        for it in items:
            if len(it[1]) == 2 and it[1][0] == n_item[0]:
                return read_valve(it, None, name_item=n_item, expected_name=name)
    return NoData(f"no value item points at the {name} name bytes ({names[0][0]:08x})")


def valve_rows_by_name(peek_rows, name):
    """[(t, value)] for the rows where `row_valve` identified the valve."""
    out = []
    for t, items in peek_rows:
        v = row_valve(items, name)
        if not isinstance(v, NoData):
            out.append((t, v))
    return out


def row_clock_string(items, addr=None):
    """The round-clock string out of one row. `addr` names the item; None (the default) means "under
    whichever revision's number it was peeked at" -- CLOCK_STRING_ADDRS, the disjoint pair (Task 19)."""
    addrs = CLOCK_STRING_ADDRS if addr is None else {addr}
    for a, words in items:
        if a in addrs and words:
            raw = b"".join(struct.pack("<I", w) for w in words).split(b"\0", 1)[0]
            if raw and all(0x20 <= c < 0x7F for c in raw):
                return raw.decode("ascii")
            return NoData(f"clock string at {a:#x} is not printable")
    return NoData("no clock-string item (%s)" % " or ".join("%#x" % a for a in sorted(addrs)))


def row_round_state(items):
    """{valve: value | NoData} over ROUND_VALVES, plus 'clock': the round clock string | NoData."""
    st = {name: row_valve(items, name) for name in ROUND_VALVES}
    st["clock"] = row_clock_string(items)
    return st


# ---------------------------------------------------------------------------------------------
# actor fields (offsets from the actor base, found through the block whose word 0 is the vtable)
# ---------------------------------------------------------------------------------------------
ACTOR_ALIVE_OFFSET = 0xF7A         # byte, 1 = alive (research/19 F1); byte 2 of the word at +0xF78
ACTOR_STAMP_OFFSET = 0x420         # float, the position-apply timestamp R6 compares (research/21 §6.4)
ROUND_TIME_ADDR = ga.address("guest_clock", "r0001")   # 0x4365c0, float DAT_004365c0: round time, counts up from 0 at round start
MP_FLAG_WORD_ADDR = ga.address("mp_flag_word", "r0001")  # 0x45a0c0, the word holding DAT_0045a0c1 as its byte 1
R6_GAP_S = 0.6                     # FUN_00594cf0's snap-back: 0x45a0c1 && clock - actor+0x420 > 0.6


def row_actor_field(items, offset, kind="u8"):
    """actor+offset from one peek row: 'u8' a byte, 'f32' a float (offset % 4 == 0). The actor is
    the item whose word 0 is the class vtable -- ACTOR_VTABLES, any revision's (Task 19: r0004 relinked
    it, and `s11_r0004_round2b` read `health=NO-DATA (no actor block (vtable) in the row)` on a round
    whose every other instrument was live). The field is read from whichever item covers that actor's
    address + offset -- never another actor's block, never by index."""
    actor = next((a for a, w in items if w and w[0] in ACTOR_VTABLES), None)
    if actor is None:
        return NoData("no actor block (vtable) in the row")
    want = actor + offset
    for a, words in items:
        if a <= want < a + 4 * len(words):
            rel = want - a                         # items need not be word-aligned with the field
            w, shift = words[rel // 4], 8 * (rel % 4)
            if kind == "u8":
                return (w >> shift) & 0xFF
            if kind == "f32" and shift == 0:
                return f32(w)
            return NoData(f"cannot read {kind} at actor+{offset:#x} from the item at {a:08x}")
    return NoData(f"no peek item covers actor+{offset:#x}")


def actor_field_rows(peek_rows, offset, kind="u8"):
    out = []
    for t, items in peek_rows:
        v = row_actor_field(items, offset, kind)
        if not isinstance(v, NoData):
            out.append((t, v))
    return out


def row_static(items, addr):
    """One static's first word from a row, by EXACT address. The row readers use `row_static_any` below
    (a static has an address per revision); this stays for a caller that has one specific number, and for
    the fixtures and tests that build rows (review F9)."""
    for a, words in items:
        if a == addr and words:
            return words[0]
    return None


def chain_for(chain, revision):
    """A PS2X_PEEK chain string written in r0001's addresses, re-rendered in `revision`'s (Task 19).

    The valve chains in VALVES and the actor base the pre-launch checks build their messages from are
    r0001 text. They are not READ from a row -- they are COMPARED against the spec a launch is about to
    use -- so on an r0004 launch they have to be the r0004 chains or the check refuses a correct spec.
    That is what `s11_r0004_round2` refused on: a correct r0004 PS2X_PEEK, against r0001's expectations.
    Only the three bases a chain can start from are substituted, and only as whole rendered addresses.

    STRUCTURAL DEBT, named (review F10): this is a SECOND place that knows a chain is built on
    player_actor / net_game / mission_abort_valve, and it is textual -- it works only because `VALVES`
    spells those bases lowercase in exactly `"%#x"` form. A spelling change on either side would make
    `str.replace` a silent no-op and the r0004 checks would then refuse a correct spec.
    `test_online_instruments.test_the_valve_chains_spell_their_bases_the_way_chain_for_expects` holds
    that coupling directly; the way out is to express `Valve.value_item`/`name_item` as templates over
    the names and render them through `guest_addresses`, which would retire this function."""
    if revision == "r0001":
        return chain
    for name in ("player_actor", "net_game", "mission_abort_valve"):
        chain = chain.replace("%#x" % ga.address(name, "r0001"), "%#x" % ga.address(name, revision))
    return chain


def row_static_any(items, addrs):
    """`row_static` over a SET of addresses -- the same static under whichever revision's number this
    row was peeked at (Task 19). The columns are disjoint, so at most one of them can be present."""
    for a, words in items:
        if a in addrs and words:
            return words[0]
    return None


def _row_static_hit(items, addrs):
    """(address, first word) of the item at one of `addrs`, or (None, None): `row_static_any`, saying
    WHICH column's address the row carried, so a message prints the row's own number."""
    for a, words in items:
        if a in addrs and words:
            return a, words[0]
    return None, None


def stall_context(items):
    """The R6 snap-back inputs from one (the latest) peek row, for a move-path stall line:
    actor+0x420, the round clock DAT_004365c0, their gap and DAT_0045a0c1. Items absent -> said.
    Addresses print as the row carried them (either revision's column)."""
    parts = []
    stamp = row_actor_field(items, ACTOR_STAMP_OFFSET, "f32")
    clock_a, clock_w = _row_static_hit(items, ROUND_TIME_ADDRS)
    flag_a, flag_w = _row_static_hit(items, MP_FLAG_WORD_ADDRS)
    if not isinstance(stamp, NoData):
        parts.append(f"actor+0x420={stamp:.3f}")
    if clock_w is not None:
        parts.append(f"clock@{clock_a:#x}={f32(clock_w):.3f}")
    if not isinstance(stamp, NoData) and clock_w is not None:
        gap = f32(clock_w) - stamp
        parts.append(f"gap={gap:.3f}{' > ' if gap > R6_GAP_S else ' <= '}{R6_GAP_S:g}")
    if flag_w is not None:
        parts.append(f"{flag_a + 1:#x}={(flag_w >> 8) & 0xFF}")
    if not parts:
        return (f"R6 inputs not peeked (*{ga.address('player_actor', 'r0001'):#x}+0x400:12, "
                f"{ROUND_TIME_ADDR:#x}:1, {MP_FLAG_WORD_ADDR:#x}:1)")
    return "R6 " + " ".join(parts)


def pointer_mode_refusal(lines, peek_rows):
    """None when a log may be read in the pointer mode (`valve_rows` with an r0001 name pointer), else the
    sentence that refuses it. The mode is r0001-only (see VALVES). The log's own address-table line decides,
    else its rows: the log is a column's when its items sit at that column's addresses and at no other's.
    A log that shows neither is REFUSED, not assumed r0001 -- the same rule music_state_poll keeps."""
    try:
        revision = ga.log_revision(lines)[0]
    except ValueError:
        by_addr = {ga.address(n, r): r for n in ga.all_names() if n != "actor_vtable" for r in ga.REVISIONS}
        seen = {by_addr[a] for _t, items in peek_rows for a, _w in items if a in by_addr}
        if len(seen) != 1:
            return ("--round-name-ptr needs to know the log is r0001's, and this one does not say: no "
                    "'[socom2] address table: ...' line, and its rows carry %s. Drop the flag -- without it "
                    "the valve is found by its NAME BYTES, which read every revision."
                    % ("no table address" if not seen else "addresses of " + " and ".join(sorted(seen))))
        revision = seen.pop()
    if revision == "r0001":
        return None
    return (f"--round-name-ptr is r0001-only and this log is {revision}'s: a valve's name pointer is a heap "
            f"address guest_addresses has no {revision} column for (data_via_twin cannot place it). Drop "
            f"the flag -- without it the valve is found by its NAME BYTES, which read every revision.")


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
    fp_off = NG_FINGERPRINT_WORD * 4
    out = []
    for t, items in peek_rows:
        by_addr = {a: w for a, w in items}
        for a, words in items:
            if len(words) <= wi:
                continue
            # the fingerprint may sit in this item, or -- PS2X_PEEK caps items at 64 words, so launch
            # 1 split the block as *0x437ce8:64 + *0x437ce8+0x100:21 -- in the item that starts
            # exactly where the fingerprint's address falls, found by address, never by index
            fp = None
            if len(words) > NG_FINGERPRINT_WORD:
                fp = words[NG_FINGERPRINT_WORD]
            else:
                for b, bw in by_addr.items():
                    rel = a + fp_off - b
                    if 0 < b - a <= fp_off and rel % 4 == 0 and rel // 4 < len(bw):
                        fp = bw[rel // 4]
                        break
            if fp == NG_FINGERPRINT_VALUE:
                out.append((t, (words[wi] >> shift) & 0xFF))
                break
    return out


def clock_rows(peek_rows, addr=None):
    """[(t, string)] from the clock-string item (r0001 `0x408f10:<n>`, r0004 `0x4358d0:<n>`): words
    little-endian, up to the first NUL, printable."""
    out = []
    for t, items in peek_rows:
        s = row_clock_string(items, addr)
        if not isinstance(s, NoData):
            out.append((t, s))
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


def _paused(pauses, t):
    return any(p[0] <= t <= p[1] for p in pauses)


def _pause_overlap(pauses, t0, t1):
    return sum(max(0.0, min(t1, p[1]) - max(t0, p[0])) for p in pauses)


def score_contact(rowsA, rowsB, callsA, callsB, clock_rows, scale_rows, round_time_rows=None, round_steps=None):
    """rowsA/rowsB: actor rows (t, x, y, z, ...) on ONE clock; callsA/callsB: MoveScale [(t, n)];
    clock_rows: [(t, string)]; scale_rows: ([(t, f12)] for A, [(t, f12)] for B); round_time_rows: optional
    ([(t, 0x4365c0)] for A, for B) and round_steps ([t] for A, for B) on the same clock.

    Pairing: A's rows are the reference; each A row is paired with B's row nearest in time, if within
    CONTACT_PAIR_MAX_S (so one B row may serve up to two A rows). A row qualifies only if A's previous
    row and the paired B row's previous row are each within CONTACT_ROW_MAX_GAP_S, plus the band (spec §5.1),
    move-path, clock and scale clauses. An A row inside a guest-clock FREEZE of EITHER instance (clock_pauses; A's and
    B's merged) is paused: it neither breaks a run nor adds to it, and the paused span is not counted as time; after the
    freeze each liveness clause (MoveScale advancing on both sides, the clock string changing, f12's age) is granted its
    own window from the freeze end (launch 8c: the string moves 0.25 s after the clock, MoveScale 0.18-2.3 s after). A
    row inside a ROUND BOUNDARY breaks the run: contact never bridges two rounds. A run's qualifying
    time is the sum of the gaps between its consecutive qualifying rows, less paused spans; the best run is the one
    with the most time, `ok` when it has >= CONTACT_MIN_S over >= CONTACT_MIN_ROWS rows. No pair formed at all (e.g.
    misaligned clocks) is NO-DATA, not zero contact."""
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

    freezes, boundaries = [], []
    if round_time_rows is not None:
        steps = round_steps or ((), ())
        for rt, st in zip(round_time_rows, steps):
            for p in clock_pauses(rt or [], st or ()):
                (freezes if p[3] == "freeze" else boundaries).append(p[:3])
    pauses = _union(freezes)                           # A's and B's freezes merged: an overlap is subtracted once
    pause_ends = sorted(p[1] for p in pauses)
    gaps = sorted(q[0] - p[0] for p, q in zip(rowsA, rowsA[1:]))
    period = gaps[len(gaps) // 2] if gaps else None
    closest, closest_dy = None, None
    run = total = pairs = paused_rows = 0
    run_s, last_t, best, best_s = 0.0, None, 0, 0.0
    for ia, a in enumerate(rowsA):
        t = a[0]
        if boundaries and _paused(boundaries, t):
            run, run_s, last_t = 0, 0.0, None           # a round boundary BREAKS the run: contact never bridges rounds
            continue
        if pauses and _paused(pauses, t):
            paused_rows += 1
            continue
        # I5 (fix round): after a freeze each liveness clause is granted its own window from the pause end (8c: the
        # string changes 0.25 s after the clock runs, MoveScale resumes 0.18-2.3 s later)
        ke = bisect.bisect_left(pause_ends, t) - 1
        since = t - pause_ends[ke] if ke >= 0 else math.inf
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
                  and (since <= CONTACT_ADVANCE_WINDOW_S or (_advancing(ca, ta_c, t) and _advancing(cb, tb_c, t)))
                  and (since <= CONTACT_CLOCK_WINDOW_S or _clock_changing(clock, tc, t))
                  and _scale_live(sa, tsa, t, since <= CONTACT_SCALE_MAX_AGE_S)
                  and _scale_live(sb, tsb, t, since <= CONTACT_SCALE_MAX_AGE_S))
        if ok:
            if run and last_t is not None:
                run_s += max(0.0, t - last_t - _pause_overlap(pauses, last_t, t))
            run += 1
            total += 1
            last_t = t
            if (run_s, run) > (best_s, best):
                best, best_s = run, run_s
        else:
            run, run_s, last_t = 0, 0.0, None
    if missing:
        return ContactResult(0, 0, rows_read, NO_DATA, "no " + ", no ".join(missing), closest, closest_dy,
                             sampler_period_s=period)
    if pairs == 0:
        return ContactResult(0, 0, rows_read, NO_DATA,
                             f"no A row had a B row within {CONTACT_PAIR_MAX_S:g}s (clocks misaligned?)",
                             sampler_period_s=period)
    return ContactResult(best, total, rows_read, "ok", "", closest, closest_dy, contact_s=best_s,
                         sampler_period_s=period, paused_rows=paused_rows,
                         ok=best_s >= CONTACT_MIN_S - 1e-9 and best >= CONTACT_MIN_ROWS)


def _clock_changing(clock, tc, t):
    k1 = bisect.bisect_right(tc, t)
    k0 = bisect.bisect_left(tc, t - CONTACT_CLOCK_WINDOW_S)
    return len({s for _, s in clock[max(0, k0):k1]}) >= 2


def _scale_live(scales, ts, t, grace=False):
    """The newest f12 at `t` is >= CONTACT_SCALE_MIN and no older than CONTACT_SCALE_MAX_AGE_S (`grace`: its age is not
    judged -- inside that window after a freeze)."""
    k = bisect.bisect_right(ts, t) - 1
    return k >= 0 and (grace or t - scales[k][0] <= CONTACT_SCALE_MAX_AGE_S) and scales[k][1] >= CONTACT_SCALE_MIN


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
        alive = actor_field_rows(p.peek_rows, ACTOR_ALIVE_OFFSET, "u8")
        if args.round_name_ptr is not None:
            refusal = pointer_mode_refusal(_read(path), p.peek_rows)
            if refusal:
                print(f"[{tag}] MOVE-PATH refused -- {refusal}")
                worst = max(worst, 2)
                continue
            rounds = valve_rows(p.peek_rows, args.round_name_ptr)
        else:
            rounds = valve_rows_by_name(p.peek_rows, "mp_round_count")
        v = score_move_path(calls, alive, rounds, now)
        lines = len(calls)
        span = f"#{calls[0][1]}..#{calls[-1][1]} over {calls[0][0]:.1f}..{calls[-1][0]:.1f}s" if calls else "none"
        print(f"[{tag}] {args.name} lines={lines} ({span}) alive rows={len(alive)} round rows={len(rounds)} now={now:.1f}")
        ctx = f"; {stall_context(p.peek_rows[-1][1])}" if (v.status == "stalled" and p.peek_rows) else ""
        print(f"[{tag}] MOVE-PATH {v.status} since={v.since} -- {v.detail}{ctx}")
        code = {"ok": 0, "disarmed": 0, "stalled": 1}.get(v.status, 2)
        if not p.peek_rows and not calls:
            code = 2
        worst = max(worst, code)
    return worst


def _cmd_starvation(args):
    worst = 0
    for tag, path, p in _load_all(args.logs):
        _rows_read(tag, path, p)
        # the slot name is the launch script's choice: research/18 wrote NetIdleMs, launch 1 NetIdle
        name = args.name or next((n for n in NET_IDLE_NAMES if p.rets.get(n)), NET_IDLE_NAMES[0])
        idle = [(t, v) for t, _, v in p.rets.get(name, [])]
        lag = ng_lagflag_rows(p.peek_rows)
        calls = [(t, n) for t, n, *_ in p.calls.get(MOVE_SCALE_NAME, [])]
        now = p.peek_rows[-1][0] if p.peek_rows else 0.0
        mp = (score_move_path(calls, actor_field_rows(p.peek_rows, ACTOR_ALIVE_OFFSET, "u8"),
                              valve_rows_by_name(p.peek_rows, "mp_round_count"), now)
              if calls else None)                  # a stall or NO-DATA -> starvation NO-DATA
        v = score_starvation(idle, lag, side=tag, move_path=mp)
        print(f"[{tag}] {name} rows={len(idle)} ng+0xde rows={len(lag)}")
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

    def guest(p, off):
        rt = [(t + off, f32(w)) for t, items in p.peek_rows
              for w in [row_static_any(items, ROUND_TIME_ADDRS)] if w is not None]
        steps = round_steps([(t + off, v) for t, v in valve_rows_by_name(p.peek_rows, "mp_round_count")])
        return rt, steps
    (rta, sta), (rtb, stb) = guest(pa, 0.0), guest(pb, off)
    r = score_contact(pa.actor_rows, rows_b, calls_a, calls_b, clock, (scales_a, scales_b),
                      round_time_rows=(rta, rtb), round_steps=(sta, stb))
    print(f"clock rows={len(clock)} guest clock rows A={len(rta)} B={len(rtb)} closest_3d={_fmt(r.closest_3d)} "
          f"dy_at_closest={_fmt(r.closest_dy)} qualifying={r.total_rows} paused={r.paused_rows} status={r.status}"
          f"{' (' + r.reason + ')' if r.reason else ''}")
    print(f"LADDER contact={'yes' if r.ok else 'no'} contact_s={r.contact_s:.2f} contact_rows={r.contact_rows} "
          f"sampler_s={_fmt(r.sampler_period_s)} rows_read={r.rows_read} "
          f"(band |dy|<={CONTACT_DY_MAX_UNITS:g}, 3-D<={CONTACT_3D_MAX_UNITS:g}; >= {CONTACT_MIN_S:g} s over >= "
          f"{CONTACT_MIN_ROWS} rows)")
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
                   help="name pointer of the mp_round_count valve (identifies its peek item). r0001 logs "
                        "only: refused on any other revision's (the pointer is a heap address)")
    s = sub.add_parser("starvation", help="ng+0xde / NetIdle (exit 0 ok / 1 alarm / 2)")
    s.add_argument("logs", nargs="+")
    s.add_argument("--name", default=None, help="NetIdle slot name (default: whichever of %s logged)"
                   % "/".join(NET_IDLE_NAMES))
    k = sub.add_parser("contact", help="contact rows between A and B (exit 0 / 2)")
    k.add_argument("logs", nargs="+")
    k.add_argument("--offset-b", type=float, default=None, help="seconds added to B's clock")
    args = ap.parse_args(argv)
    return {"score-control": _cmd_control, "move-path": _cmd_move_path,
            "starvation": _cmd_starvation, "contact": _cmd_contact}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
