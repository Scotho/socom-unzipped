"""Replay kill verdict from two stored run logs -- the VALVE-primary scorer (Sprint 5 Task 6 Step 1).

    python -m tools_py.parity.verdict_replay <run_A.log> <run_B.log> [--shooter A|B]
                                             [--offset-b S] [--grenade-mask 0xNNNN]

Prints exactly one verdict line, then one line per spec §5.1 clause with its measured values:
  KILL killer=<A|B> victim=<A|B> t=<victim guest clock>     exit 0
  NO-KILL <no-death|fall|self|unattributed|team|round-ended-first>   exit 1
  KILL-SEMANTICS <valve>                                    exit 1
  NO-DATA <item>                                            exit 2

This is the SECOND, independent scorer: `online_match_ours.KillWatch` is primary on the actor fields,
this one is primary on the round-state valves (`total_mp_kills`, `aiteam_*`), corroborated by the
actor fields. It deliberately imports neither `verdict_core` nor `online_match_ours` (a test asserts
the import set) and has its own parser; the tests run both parsers over the same raw fixtures so a
parser divergence shows up as a test disagreement.

The bars are spec §5.1 (Amendment A, pre-registered 2026-09-13, binding over §5 Goal 6). They are
named constants below, each asserted verbatim by the tests; they may not be loosened after a kill
is seen.

Row formats (the exe's own; research/21 §8-§9, research/18 §3.10-§3.12):
  * `[peek] @<addr>: <hex8>(<float>) ...` one row per PS2X_PC_SAMPLER period, not timestamped. Items
    are identified by content: the actor block by word 0 == vtable 0x006691a0 (health +0x1044, alive
    byte +0xF7A, team word +0xC8 read from whichever item covers that address), a valve by the item
    that spells its name bytes and the 2-word item whose word 0 points at it, the guest clock by the
    static 0x4365c0, the clock string by 0x408f10.
  * `[call] <t>s <Name> #<n> ...` seconds since that process's call-trace start: the host clock.
  * `[socom2-input] state buttons=XXXX rx=XX ry=XX lx=XX ly=XX` on every change of the pad state
    (torn lines: the tail is recovered from the next line, as the harness writes them).

Clocks. Host time of a peek row: interpolated along the row index between `[call]` stamps at least
5 s apart (0.25 s/row outside them). The two processes' host clocks are aligned by each instance's
MoveScale #0 (round start) unless --offset-b is given. Guest time: the float at 0x4365c0 per row;
it stops during a freeze, and on launches 3c/8c it ran at ~0.6-0.7 guest s per host s and did NOT
reset at a round change (8c B: 225.81 at `00:09` -> 225.96 at the next round's `05:59`).
"""
import argparse
import bisect
import math
import os
import re
import struct
import sys
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------------------------
# verdict words
# ---------------------------------------------------------------------------------------------
KILL = "KILL"
NO_KILL = "NO-KILL"
KILL_SEMANTICS = "KILL-SEMANTICS"
NO_DATA = "NO-DATA"
EXIT = {KILL: 0, NO_KILL: 1, KILL_SEMANTICS: 1, NO_DATA: 2}

R_NO_DEATH = "no-death"
R_FALL = "fall"
R_SELF = "self"
R_UNATTRIBUTED = "unattributed"
R_TEAM = "team"
R_ROUND_ENDED = "round-ended-first"

# ---------------------------------------------------------------------------------------------
# spec §5.1 bars -- pre-registered, asserted verbatim by the tests
# ---------------------------------------------------------------------------------------------
# Goal 6 attribution window: the killer's R1 (or grenade) injected within 3 s of the KILLER
# instance's own guest clock before the death, with |dy| <= 10 and 3-D <= 60 throughout.
# Blind: an unrelated damage source during a burst from 60 units.
ATTRIBUTION_WINDOW_S = 3.0
ATTRIBUTION_DY_MAX = 10.0
ATTRIBUTION_3D_MAX = 60.0
# Valve timing: within each instance, a step within 3 s of THAT instance's guest clock of its own
# death/kill row; across instances consistent ordering and <= 20 s host wall clock; a freeze
# overlapping a window -> NO-DATA.
VALVE_WINDOW_GUEST_S = 3.0
CROSS_INSTANCE_MAX_S = 20.0
# Unchanged from Goal 6: no victim y drop > 20 in the 2 s before; no grenade on the victim's own pad
# in the 10 s before. Both windows are read on the victim's guest clock (a freeze inside them is a
# NO-DATA, so host vs guest cannot hide a fall or a throw).
FALL_WINDOW_S = 2.0
FALL_DROP_MAX = 20.0
SELF_GRENADE_WINDOW_S = 10.0
# total_mp_kills steps by one on at least one instance (both reported).
KILLS_STEP = 1
AITEAM_DROP = 1

# ---------------------------------------------------------------------------------------------
# instruments -- not bars; each with what it does not separate
# ---------------------------------------------------------------------------------------------
R1_MASK = 1 << 11                  # pad id R1 = 11 (online_login_ours PAD_BUTTON); 96 `buttons=0800` on kill2
# The grenade button is NOT calibrated yet (plan A7: "one throw-distance calibration"). Until
# --grenade-mask names it: the KILLER's grenade does not attribute (no false PASS from a button that
# may not be a grenade), and ANY non-R1 button on the VICTIM's pad in the 10 s window counts as a
# possible self-grenade (no false PASS from a throw on an unknown button). Blind: a victim that
# presses a harmless button in the window scores NO-KILL self -- the default engagement has the
# victim standing with a neutral pad (A3), so that costs a round, never a false PASS.
ALL_BUTTONS = 0xFFFF
SAMPLER_PERIOD_S = 0.25
CLOCK_ANCHOR_MIN_SPACING_S = 5.0
ACTOR_VTABLE = 0x006691A0
ACTOR_POS_WORDS = (7, 8, 9)
HEALTH_OFFSET = 0x1044             # float, <= 0 dead (research/19 F1)
ALIVE_OFFSET = 0xF7A               # byte, 1 = alive
TEAM_WORD_OFFSET = 0xC8            # word, meaning OPEN (research/21 §9.6): reported, never gated
GUEST_CLOCK_ADDR = 0x4365C0
CLOCK_STRING_ADDR = 0x408F10
MOVE_SCALE_NAME = "MoveScale"
REQUIRED_VALVES = ("mp_round_count", "player_team", "aiteam_00", "aiteam_08", "total_mp_kills")
TEAM_VALVE = {0: "aiteam_00", 8: "aiteam_08"}   # player_team 0 SEALS / 8 TERRORISTS (research/21 §9.6)
# A guest-clock freeze: consecutive rows over >= 1.0 s of host time on which the guest clock advanced
# by less than a quarter of the host time. Measured against: 0.58-0.67 guest s per host s in normal
# play (3c, 8c), 8c's stalls of 3.3-17.3 s. Blind: a stall shorter than 1 s; a guest at < 1/4 speed
# that still advances is NOT a freeze.
FREEZE_MIN_HOST_S = 1.0
FREEZE_RATE_MAX = 0.25
# Rows further apart than this do not cover a window (verdict_core's CONTACT_ROW_MAX_GAP_S value,
# kill2 B's worst healthy 1.08 s). Blind: motion inside a 1.25 s gap.
ROW_MAX_GAP_S = 1.25
# Pairing a row with the other instance's nearest row (two 4 Hz samples). Blind: 0.5 s at 40 u/s
# is 20 units of misplacement.
PAIR_MAX_S = 0.5
# The killer's +0x1044 is read on its rows within this much of the (aligned) death. A killer dying
# on the same half-second is a trade (mutual death), not a kill. Blind: host alignment error.
KILLER_ALIVE_S = 0.5


# ---------------------------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------------------------
@dataclass
class ActorRead:
    addr: int
    intact: bool                   # word 0 == ACTOR_VTABLE
    x: float = None
    y: float = None
    z: float = None
    pos_nonzero: bool = False
    hp: float = None
    alive: int = None
    team_word: int = None


@dataclass
class Row:
    t: float
    guest: float = None
    clock_string: str = None
    valves: dict = field(default_factory=dict)
    actor: ActorRead = None


@dataclass
class Run:
    rows: list = field(default_factory=list)
    pads: list = field(default_factory=list)         # [(t, buttons | None)]
    pad_unrecovered: list = field(default_factory=list)
    move_scale_0: float = None
    lines: int = 0


_ITEM = re.compile(r"@([0-9a-fA-F]+):((?:\s+[0-9a-fA-F]{8}\([^)]*\))+)")
_WORD = re.compile(r"([0-9a-fA-F]{8})\(")
_CALL = re.compile(r"^\[call\] ([\d.]+)s (\S+) #(\d+)")
_PAD_FULL = re.compile(r"buttons=([0-9a-fA-F]{4}) rx=[0-9a-fA-F]{2} ry=[0-9a-fA-F]{2} "
                       r"lx=[0-9a-fA-F]{2} ly=[0-9a-fA-F]{2}\s*$")
_PAD_TAIL = re.compile(r"(?:^|=)([0-9a-fA-F]{4})?\s?rx=[0-9a-fA-F]{2} ry=[0-9a-fA-F]{2} "
                       r"lx=[0-9a-fA-F]{2} ly=[0-9a-fA-F]{2}\s*$")


def _f32(w):
    return struct.unpack("<f", struct.pack("<I", w & 0xFFFFFFFF))[0]


def _spells(words, name):
    if len(words) < 3:
        return False
    raw = struct.pack("<3I", *(w & 0xFFFFFFFF for w in words[:3]))
    want = (name.encode("ascii") + b"\0")[:12]
    return raw[:len(want)] == want


def _valve(items, name):
    for n_addr, n_words in items:
        if not _spells(n_words, name):
            continue
        for _, words in items:
            if len(words) == 2 and words[0] == n_addr:
                v = words[1] & 0xFFFF
                return v - 0x10000 if v & 0x8000 else v
    return None


def _covering(items, addr):
    for a, words in items:
        if a <= addr < a + 4 * len(words):
            rel = addr - a
            return words[rel // 4], 8 * (rel % 4)
    return None


def _actor(items, last_addr):
    addr = next((a for a, w in items if w and w[0] == ACTOR_VTABLE), None)
    intact = addr is not None
    if addr is None:
        # word 0 no longer the vtable: the block at the last known address, if it is still printed
        if last_addr is None or not any(a == last_addr for a, _ in items):
            return None
        addr = last_addr
    words = next(w for a, w in items if a == addr)
    r = ActorRead(addr=addr, intact=intact)
    if len(words) > max(ACTOR_POS_WORDS):
        r.x, r.y, r.z = (_f32(words[k]) for k in ACTOR_POS_WORDS)
        r.pos_nonzero = bool(r.x or r.y or r.z)
    c = _covering(items, addr + HEALTH_OFFSET)
    if c is not None and c[1] == 0:
        r.hp = _f32(c[0])
    c = _covering(items, addr + ALIVE_OFFSET)
    if c is not None:
        r.alive = (c[0] >> c[1]) & 0xFF
    c = _covering(items, addr + TEAM_WORD_OFFSET)
    if c is not None and c[1] == 0:
        r.team_word = c[0]
    return r


def _clock_string(items):
    for a, words in items:
        if a == CLOCK_STRING_ADDR and words:
            raw = struct.pack("<%dI" % len(words), *words).split(b"\0", 1)[0]
            if raw and all(0x20 <= c < 0x7F for c in raw):
                return raw.decode("ascii")
            return None
    return None


def parse_log(lines):
    """One instance's run log (iterable of lines) -> Run. No IO."""
    run = Run()
    peeks, anchors, pads_raw, unrec = [], [], [], []
    pi, torn = 0, False
    for raw in lines:
        line = raw.rstrip("\r\n")
        run.lines += 1
        if not line:
            continue
        if line.startswith("[peek]"):
            peeks.append([(int(a, 16), [int(w, 16) for w in _WORD.findall(ws)]) for a, ws in _ITEM.findall(line)])
            pi += 1
            if torn:
                torn = False
                unrec.append(pi - 1.5)
            continue
        here = pi - 0.5
        if line.startswith("[socom2-input] state"):
            if torn:
                unrec.append(here)
            m = _PAD_FULL.search(line)
            torn = m is None
            if m:
                pads_raw.append((here, int(m.group(1), 16)))
            continue
        if torn:
            torn = False
            m = _PAD_TAIL.search(line)
            if m:
                pads_raw.append((here, int(m.group(1), 16) if m.group(1) else None))
                continue
            unrec.append(here)
        if line.startswith("[call]"):
            m = _CALL.match(line)
            if m:
                t = float(m.group(1))
                if not anchors or t - anchors[-1][1] >= CLOCK_ANCHOR_MIN_SPACING_S:
                    anchors.append((here, t))
                if m.group(2) == MOVE_SCALE_NAME and m.group(3) == "0" and run.move_scale_0 is None:
                    run.move_scale_0 = t
    if torn:
        unrec.append(pi - 0.5)
    clock = _index_clock(anchors)
    last_addr = None
    for i, items in enumerate(peeks):
        row = Row(t=clock(i))
        g = next((w[0] for a, w in items if a == GUEST_CLOCK_ADDR and w), None)
        row.guest = _f32(g) if g is not None else None
        row.clock_string = _clock_string(items)
        for name in REQUIRED_VALVES + ("mp_game_over",):
            v = _valve(items, name)
            if v is not None:
                row.valves[name] = v
        row.actor = _actor(items, last_addr)
        if row.actor is not None and row.actor.intact:
            last_addr = row.actor.addr
        run.rows.append(row)
    run.pads = [(clock(i), b) for i, b in pads_raw]
    run.pad_unrecovered = [clock(i) for i in unrec]
    return run


def _index_clock(anchors):
    if not anchors:
        return lambda i: i * SAMPLER_PERIOD_S
    idx = [a[0] for a in anchors]

    def clock(i):
        if i <= idx[0]:
            return anchors[0][1] - (idx[0] - i) * SAMPLER_PERIOD_S
        if i >= idx[-1]:
            return anchors[-1][1] + (i - idx[-1]) * SAMPLER_PERIOD_S
        k = bisect.bisect_right(idx, i)
        (i0, t0), (i1, t1) = anchors[k - 1], anchors[k]
        return t0 + (t1 - t0) * (i - i0) / (i1 - i0)
    return clock


def row_counts(run):
    """What was read, counted the way the other scorer counts its rows (the parity test)."""
    rows = run.rows
    out = {"peek": len(rows),
           "actor": sum(1 for r in rows if r.actor and r.actor.intact and r.actor.pos_nonzero),
           "health": sum(1 for r in rows if r.actor and r.actor.intact and r.actor.hp is not None),
           "alive": sum(1 for r in rows if r.actor and r.actor.intact and r.actor.alive is not None),
           "clock_string": sum(1 for r in rows if r.clock_string is not None),
           "guest_clock": sum(1 for r in rows if r.guest is not None),
           "pad": len(run.pads)}
    for v in REQUIRED_VALVES:
        out[v] = sum(1 for r in rows if r.valves.get(v) is not None)
    return out


# ---------------------------------------------------------------------------------------------
# one instance's series
# ---------------------------------------------------------------------------------------------
class Series:
    def __init__(self, tag, run, shift):
        self.tag, self.run, self.shift = tag, run, shift       # shared time = host t + shift
        self.rows = run.rows
        self.t = [r.t + shift for r in self.rows]
        self.g_rows = [(self.t[i], r.guest) for i, r in enumerate(self.rows) if r.guest is not None]
        self.freezes = self._freezes()

    def _freezes(self):
        out, start = [], None
        for (t0, g0), (t1, g1) in zip(self.g_rows, self.g_rows[1:]):
            stalled = t1 > t0 and (g1 - g0) < FREEZE_RATE_MAX * (t1 - t0)
            if stalled and start is None:
                start = t0
            if not stalled and start is not None:
                if t0 - start >= FREEZE_MIN_HOST_S:
                    out.append((start, t0))
                start = None
        if start is not None and self.g_rows[-1][0] - start >= FREEZE_MIN_HOST_S:
            out.append((start, self.g_rows[-1][0]))
        return out

    def freeze_in(self, t0, t1):
        return next(((a, b) for a, b in self.freezes if a <= t1 and b >= t0), None)

    def guest_at(self, t):
        ts = [x for x, _ in self.g_rows]
        k = bisect.bisect_right(ts, t)
        if k == 0 or not self.g_rows:
            return None
        if k == len(ts):
            return self.g_rows[-1][1] if t - ts[-1] <= ROW_MAX_GAP_S else None
        (a, ga), (b, gb) = self.g_rows[k - 1], self.g_rows[k]
        if b - a > ROW_MAX_GAP_S:
            return None
        return ga + (gb - ga) * (t - a) / (b - a)

    def shared_of_guest(self, g, anchor_t, forward=False):
        """Shared time at which the guest clock read `g`, searching from anchor_t backwards (or
        forwards). None when the rows end first."""
        ts = [x for x, _ in self.g_rows]
        k = bisect.bisect_right(ts, anchor_t) - 1
        if k < 0:
            return None
        if not forward:
            for i in range(k, -1, -1):
                if self.g_rows[i][1] <= g:
                    if i == k:
                        return self.g_rows[i][0]
                    (a, ga), (b, gb) = self.g_rows[i], self.g_rows[i + 1]
                    return a if gb == ga else a + (b - a) * (g - ga) / (gb - ga)
            return None
        for i in range(k, len(self.g_rows)):
            if self.g_rows[i][1] >= g:
                if i == k:
                    return self.g_rows[i][0]
                (a, ga), (b, gb) = self.g_rows[i - 1], self.g_rows[i]
                return b if gb == ga else a + (b - a) * (g - ga) / (gb - ga)
        return None

    def last_row_at(self, t, pred):
        k = bisect.bisect_right(self.t, t) - 1
        for i in range(k, -1, -1):
            if pred(self.rows[i]):
                return i
        return None

    def rows_between(self, t0, t1, pred=lambda r: True):
        k0, k1 = bisect.bisect_left(self.t, t0), bisect.bisect_right(self.t, t1)
        return [i for i in range(k0, k1) if pred(self.rows[i])]

    def covered(self, t0, t1, pred):
        """Rows satisfying pred cover [t0, t1] with no gap > ROW_MAX_GAP_S (edges included)."""
        idx = [i for i in range(len(self.rows)) if pred(self.rows[i])]
        ts = [self.t[i] for i in idx]
        k0 = bisect.bisect_right(ts, t0) - 1
        k1 = bisect.bisect_left(ts, t1)
        if k0 < 0 or k1 >= len(ts):
            return False
        seg = ts[k0:k1 + 1]
        return all(b - a <= ROW_MAX_GAP_S for a, b in zip(seg, seg[1:]))

    def steps(self, name):
        """[(shared t, before, after)] where the valve read changed (unread rows skipped)."""
        out, prev = [], None
        for i, r in enumerate(self.rows):
            v = r.valves.get(name)
            if v is None:
                continue
            if prev is not None and v != prev:
                out.append((self.t[i], prev, v))
            prev = v
        return out

    def valve_at(self, name, t):
        i = self.last_row_at(t, lambda r: r.valves.get(name) is not None)
        return None if i is None else self.rows[i].valves[name]

    def pads_shared(self):
        return [(t + self.shift, b) for t, b in self.run.pads]

    def round_starts(self):
        """Shared times at which the clock string started a countdown (it went up, or appeared)."""
        out, prev = [], None
        for i, r in enumerate(self.rows):
            s = _mmss(r.clock_string)
            if s is None:
                continue
            if prev is None or s > prev + 1:
                out.append(self.t[i])
            prev = s
        return out


def _mmss(s):
    m = re.match(r"^(\d\d):(\d\d)$", s or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


# ---------------------------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------------------------
@dataclass
class Verdict:
    word: str
    reason: str = ""
    killer: str = None
    victim: str = None
    t: float = None
    clauses: list = field(default_factory=list)       # [(name, ok True|False|None, text)]
    facts: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    @property
    def exit_code(self):
        return EXIT[self.word]

    def headline(self):
        if self.word == KILL:
            return "KILL killer=%s victim=%s t=%.2f" % (self.killer, self.victim, self.t)
        return "%s %s" % (self.word, self.reason)

    def text(self):
        out = [self.headline()]
        for name, ok, txt in self.clauses:
            mark = {True: "ok  ", False: "FAIL", None: "n/a "}[ok]
            out.append("  [%s] %-18s %s" % (mark, name, txt))
        out.extend("  note: " + n for n in self.notes)
        return "\n".join(out)


class _Decided(Exception):
    def __init__(self, word, reason):
        super().__init__(reason)
        self.word, self.reason = word, reason


def _press_in(pads, t0, t1, mask):
    """A press of `mask` inside [t0, t1], or held when the window opened. Returns its time or None."""
    held = None
    for t, b in pads:
        if t < t0:
            held = b
            continue
        if t > t1:
            break
        if b is not None and b & mask:
            return t
    if held is not None and held & mask:
        return t0
    return None


def _fmt(v, nd=2):
    return "n/a" if v is None else ("%.*f" % (nd, v))


def _score_event(S, V, K, di, shooter, grenade_mask, clauses, notes):
    """One candidate death (victim instance V, its row index di). Raises _Decided, or returns the
    KILL values. Clauses are appended as they are measured; the first decisive clause decides."""
    vt, kt = V.tag, K.tag
    drow = V.rows[di]
    d_sh = V.t[di]
    a = drow.actor
    if not a.intact:
        clauses.append(("victim-death", None, "%s +0x1044=%s but word 0 is not the vtable at the death row" % (vt, _fmt(a.hp, 3))))
        raise _Decided(NO_DATA, "%s:actor-word0-at-death" % vt)
    gV = drow.guest
    if gV is None:
        raise _Decided(NO_DATA, "%s:guest-clock-at-death" % vt)
    clauses.append(("victim-death", True, "%s +0x1044=%.3f word0=%08x at shared %.2f guest %.2f"
                    % (vt, a.hp, ACTOR_VTABLE, d_sh, gV)))

    gK = K.guest_at(d_sh)
    if gK is None:
        raise _Decided(NO_DATA, "%s:guest-clock-at-death" % kt)

    # --- windows (shared host time), freezes -------------------------------------------------
    v_self0 = V.shared_of_guest(gV - SELF_GRENADE_WINDOW_S, d_sh)
    v_fall0 = V.shared_of_guest(gV - FALL_WINDOW_S, d_sh)
    v_valve0 = V.shared_of_guest(gV - VALVE_WINDOW_GUEST_S, d_sh)
    v_valve1 = V.shared_of_guest(gV + VALVE_WINDOW_GUEST_S, d_sh, forward=True)
    k_attr0 = K.shared_of_guest(gK - ATTRIBUTION_WINDOW_S, d_sh)
    for nm, v in (("%s:rows-before-self-window" % vt, v_self0), ("%s:rows-before-fall-window" % vt, v_fall0),
                  ("%s:rows-around-valve-window" % vt, v_valve0), ("%s:rows-after-valve-window" % vt, v_valve1),
                  ("%s:rows-before-attribution-window" % kt, k_attr0)):
        if v is None:
            raise _Decided(NO_DATA, nm)
    fz_v = V.freeze_in(v_self0, v_valve1)
    fz_k = K.freeze_in(k_attr0, d_sh)
    clauses.append(("freeze", not (fz_v or fz_k),
                    "%s window %.2f..%.2f %s; %s window %.2f..%.2f %s"
                    % (vt, v_self0, v_valve1, "freeze %.2f..%.2f" % fz_v if fz_v else "none",
                       kt, k_attr0, d_sh, "freeze %.2f..%.2f" % fz_k if fz_k else "none")))
    if fz_v:
        raise _Decided(NO_DATA, "%s:guest-clock-freeze-%.1f-%.1f-overlaps-timing-window" % ((vt,) + fz_v))
    if fz_k:
        raise _Decided(NO_DATA, "%s:guest-clock-freeze-%.1f-%.1f-overlaps-timing-window" % ((kt,) + fz_k))

    # --- round state ---------------------------------------------------------------------------
    starts = sorted(V.round_starts() + K.round_starts())
    seg0 = max([s for s in starts if s <= d_sh], default=-math.inf)
    ended = []
    for X in (V, K):
        for t, b, aft in X.steps("mp_round_count"):
            if seg0 < t <= d_sh:
                ended.append("%s mp_round_count %d->%d at %.2f" % (X.tag, b, aft, t))
        for i in X.rows_between(seg0 if seg0 > -math.inf else -1e18, d_sh, lambda r: r.clock_string == "00:00"):
            ended.append("%s clock 00:00 at %.2f" % (X.tag, X.t[i]))
            break
        for t, b, aft in X.steps("mp_game_over"):
            if seg0 < t <= d_sh:
                ended.append("%s mp_game_over %d->%d at %.2f" % (X.tag, b, aft, t))
    clock_txt = "; ".join("%s clock %s" % (X.tag, (X.rows[X.last_row_at(d_sh, lambda r: r.clock_string is not None)].clock_string
                                                    if X.last_row_at(d_sh, lambda r: r.clock_string is not None) is not None
                                                    else "absent")) for X in (V, K))
    clauses.append(("round-state", not ended, "round start %s; %s; %s"
                    % (_fmt(seg0 if seg0 > -math.inf else None), "; ".join(ended) or "no step, no 00:00", clock_txt)))
    if ended:
        raise _Decided(NO_KILL, R_ROUND_ENDED)

    # --- fall ----------------------------------------------------------------------------------
    pos = lambda r: r.actor is not None and r.actor.intact and r.actor.pos_nonzero
    if not V.covered(v_fall0, d_sh, pos):
        raise _Decided(NO_DATA, "%s:actor-rows-in-fall-window" % vt)
    ys = [V.rows[i].actor.y for i in V.rows_between(v_fall0 - PAIR_MAX_S, d_sh, pos)]
    drop, top = 0.0, -math.inf
    for y in ys:
        top = max(top, y)
        drop = max(drop, top - y)
    clauses.append(("no-fall", drop <= FALL_DROP_MAX, "%s max y drop %.2f over guest %.2f..%.2f (bar <= %g)"
                    % (vt, drop, gV - FALL_WINDOW_S, gV, FALL_DROP_MAX)))
    if drop > FALL_DROP_MAX:
        raise _Decided(NO_KILL, R_FALL)

    # --- self grenade --------------------------------------------------------------------------
    self_mask = grenade_mask if grenade_mask else (ALL_BUTTONS & ~R1_MASK)
    if any(v_self0 <= t + V.shift <= d_sh for t in V.run.pad_unrecovered):
        raise _Decided(NO_DATA, "%s:torn-pad-line-in-self-window" % vt)
    sp = _press_in(V.pads_shared(), v_self0, d_sh, self_mask)
    clauses.append(("no-self-grenade", sp is None, "%s pad mask %04x over guest %.2f..%.2f: %s"
                    % (vt, self_mask, gV - SELF_GRENADE_WINDOW_S, gV, "press at %.2f" % sp if sp is not None else "none")))
    if sp is not None:
        raise _Decided(NO_KILL, R_SELF)

    # --- killer ------------------------------------------------------------------------------
    if shooter is not None and shooter != kt:
        clauses.append(("killer", False, "--shooter %s died; %s is not the shooter" % (shooter, kt)))
        raise _Decided(NO_KILL, R_UNATTRIBUTED)
    hp_ok = lambda r: r.actor is not None and r.actor.intact and r.actor.hp is not None
    near = K.rows_between(d_sh - KILLER_ALIVE_S, d_sh + KILLER_ALIVE_S, hp_ok)
    if not near:
        raise _Decided(NO_DATA, "%s:actor-rows-at-death" % kt)
    k_hp = min(K.rows[i].actor.hp for i in near)
    clauses.append(("killer-alive", k_hp > 0, "%s min +0x1044 %.3f within %.1f s of the death" % (kt, k_hp, KILLER_ALIVE_S)))
    if k_hp <= 0:
        raise _Decided(NO_KILL, R_UNATTRIBUTED)

    # --- attribution ---------------------------------------------------------------------------
    if any(k_attr0 <= t + K.shift <= d_sh for t in K.run.pad_unrecovered):
        raise _Decided(NO_DATA, "%s:torn-pad-line-in-attribution-window" % kt)
    fire_mask = R1_MASK | (grenade_mask or 0)
    fp = _press_in(K.pads_shared(), k_attr0, d_sh, fire_mask)
    if not (K.covered(k_attr0, d_sh, pos) and V.covered(k_attr0, d_sh, pos)):
        raise _Decided(NO_DATA, "actor-rows-in-attribution-window")
    worst_dy, worst_3d = 0.0, 0.0
    for X, Y in ((K, V), (V, K)):
        yt = [Y.t[i] for i in range(len(Y.rows)) if pos(Y.rows[i])]
        yi = [i for i in range(len(Y.rows)) if pos(Y.rows[i])]
        for i in X.rows_between(k_attr0, d_sh, pos):
            k = bisect.bisect_left(yt, X.t[i])
            cand = [j for j in (k - 1, k) if 0 <= j < len(yt) and abs(yt[j] - X.t[i]) <= PAIR_MAX_S]
            if not cand:
                raise _Decided(NO_DATA, "pair-rows-in-attribution-window")
            j = min(cand, key=lambda j: abs(yt[j] - X.t[i]))
            p, q = X.rows[i].actor, Y.rows[yi[j]].actor
            worst_dy = max(worst_dy, abs(p.y - q.y))
            worst_3d = max(worst_3d, math.sqrt((p.x - q.x) ** 2 + (p.y - q.y) ** 2 + (p.z - q.z) ** 2))
    band = worst_dy <= ATTRIBUTION_DY_MAX and worst_3d <= ATTRIBUTION_3D_MAX
    clauses.append(("attribution", fp is not None and band,
                    "%s fire mask %04x over %s guest %.2f..%.2f: %s; max |dy| %.2f (<= %g), max 3-D %.2f (<= %g)"
                    % (kt, fire_mask, kt, gK - ATTRIBUTION_WINDOW_S, gK,
                       "press at %.2f" % fp if fp is not None else "none", worst_dy, ATTRIBUTION_DY_MAX,
                       worst_3d, ATTRIBUTION_3D_MAX)))
    if fp is None or not band:
        raise _Decided(NO_KILL, R_UNATTRIBUTED)

    # --- team --------------------------------------------------------------------------------
    v_team = V.valve_at("player_team", d_sh)
    k_team = K.valve_at("player_team", d_sh)
    if v_team is None or k_team is None:
        raise _Decided(NO_DATA, "%s:player_team-at-death" % (vt if v_team is None else kt))
    if v_team not in TEAM_VALVE:
        raise _Decided(NO_DATA, "%s:player_team-value-%d" % (vt, v_team))
    team_valve = TEAM_VALVE[v_team]
    other_valve = next(n for tm, n in TEAM_VALVE.items() if tm != v_team)
    tw = a.team_word
    clauses.append(("victim-team", k_team != v_team,
                    "%s player_team %d -> %s; %s player_team %d; %s +0xC8 %s (cross-check only, meaning open)"
                    % (vt, v_team, team_valve, kt, k_team, vt, "%08x" % tw if tw is not None else "not peeked")))
    near_drop = lambda X, name, t0, t1: [(t, b, aft) for t, b, aft in X.steps(name) if t0 <= t <= t1 and aft < b]
    other = near_drop(V, other_valve, v_valve0, v_valve1) + near_drop(K, other_valve, d_sh - CROSS_INSTANCE_MAX_S, d_sh + CROSS_INSTANCE_MAX_S)
    own_any = near_drop(V, team_valve, v_valve0, v_valve1) + near_drop(K, team_valve, d_sh - CROSS_INSTANCE_MAX_S, d_sh + CROSS_INSTANCE_MAX_S)
    if k_team == v_team:
        raise _Decided(NO_KILL, R_TEAM)
    if other:
        clauses.append(("team-valve", False, "%s dropped: %s; %s: %s"
                        % (other_valve, other, team_valve, own_any or "no drop")))
        raise _Decided(NO_KILL, R_TEAM)

    # --- valves: semantics and timing ------------------------------------------------------------
    semantics, nodata = [], []
    # K's kill row: its first kill-valve step within 20 s of the death, in the same round
    k_round_steps = [t for t, _, _ in K.steps("mp_round_count") if t > d_sh]
    k_round_end = min(k_round_steps, default=math.inf)
    k_candidates = sorted([(t, "total_mp_kills", b, aft) for t, b, aft in K.steps("total_mp_kills") if aft > b and seg0 < t < k_round_end] +
                          [(t, team_valve, b, aft) for t, b, aft in K.steps(team_valve) if aft < b and seg0 < t < k_round_end])
    k_in = [c for c in k_candidates if abs(c[0] - d_sh) <= CROSS_INSTANCE_MAX_S]
    k_late = [c for c in k_candidates if c[0] - d_sh > CROSS_INSTANCE_MAX_S]
    k_steps = {}
    if k_in:
        kill_t = k_in[0][0]
        g_kill = K.guest_at(kill_t)
        k0 = K.shared_of_guest(g_kill - VALVE_WINDOW_GUEST_S, kill_t) if g_kill is not None else None
        k1 = K.shared_of_guest(g_kill + VALVE_WINDOW_GUEST_S, kill_t, forward=True) if g_kill is not None else None
        if k0 is None or k1 is None:
            nodata.append("%s:rows-around-kill-row" % kt)
        else:
            fz = K.freeze_in(k0, k1)
            if fz:
                nodata.append("%s:guest-clock-freeze-%.1f-%.1f-overlaps-valve-window" % ((kt,) + fz))
            for t, name, b, aft in k_in:
                if name not in k_steps:
                    k_steps[name] = (t, b, aft, K.guest_at(t) - g_kill if K.guest_at(t) is not None else None)
        cross = kill_t - d_sh
        clauses.append(("cross-instance", abs(cross) <= CROSS_INSTANCE_MAX_S,
                        "%s kill row at %.2f = death %+.2f s host (bar <= %g), same round on both (no mp_round_count step between)"
                        % (kt, kill_t, cross, CROSS_INSTANCE_MAX_S)))
    elif k_late:
        clauses.append(("cross-instance", False, "%s first kill-valve step %+.2f s host after the death (bar <= %g)"
                        % (kt, k_late[0][0] - d_sh, CROSS_INSTANCE_MAX_S)))
        nodata.append("%s:valve-step-%.1fs-after-death-past-%gs" % (kt, k_late[0][0] - d_sh, CROSS_INSTANCE_MAX_S))
    elif K.t[-1] < d_sh + CROSS_INSTANCE_MAX_S and k_round_end == math.inf:
        nodata.append("%s:rows-end-before-the-%gs-pairing-window" % (kt, CROSS_INSTANCE_MAX_S))

    v_steps = {}
    for name, up in (("total_mp_kills", True), (team_valve, False)):
        for t, b, aft in V.steps(name):
            if v_valve0 <= t <= v_valve1 and ((aft > b) if up else (aft < b)):
                v_steps[name] = (t, b, aft, V.guest_at(t) - gV if V.guest_at(t) is not None else None)
                break
    # a V step outside its 3 s guest window but inside the round and 20 s: timing unlike the belief
    v_late = {}
    for name, up in (("total_mp_kills", True), (team_valve, False)):
        if name in v_steps:
            continue
        for t, b, aft in V.steps(name):
            if seg0 < t and abs(t - d_sh) <= CROSS_INSTANCE_MAX_S and ((aft > b) if up else (aft < b)):
                v_late[name] = (t, b, aft)
                break

    def desc(d):
        return ", ".join("%s %d->%d at %.2f (guest %+.2f)" % (n, s[1], s[2], s[0], s[3] if s[3] is not None else float("nan"))
                         for n, s in sorted(d.items())) or "none"

    kills_ok = any(n == "total_mp_kills" and s[2] - s[1] == KILLS_STEP and (s[3] is None or abs(s[3]) <= VALVE_WINDOW_GUEST_S)
                   for d in (v_steps, k_steps) for n, s in d.items())
    clauses.append(("total_mp_kills", kills_ok, "steps by %d on >= 1 instance: %s: %s; %s: %s"
                    % (KILLS_STEP, vt, desc({n: s for n, s in v_steps.items() if n == "total_mp_kills"}),
                       kt, desc({n: s for n, s in k_steps.items() if n == "total_mp_kills"}))))
    if not kills_ok:
        semantics.append("total_mp_kills")
    v_team_ok = team_valve in v_steps and v_steps[team_valve][1] - v_steps[team_valve][2] == AITEAM_DROP
    k_team_ok = (team_valve in k_steps and k_steps[team_valve][1] - k_steps[team_valve][2] == AITEAM_DROP
                 and (k_steps[team_valve][3] is None or abs(k_steps[team_valve][3]) <= VALVE_WINDOW_GUEST_S))
    clauses.append((team_valve, (False if not v_team_ok else None) if (nodata and not k_team_ok) else (v_team_ok and k_team_ok),
                    "drops by %d on both: %s: %s%s; %s: %s"
                    % (AITEAM_DROP, vt, desc({n: s for n, s in v_steps.items() if n == team_valve}),
                       " (late: %s)" % (v_late[team_valve],) if team_valve in v_late else "",
                       kt, desc({n: s for n, s in k_steps.items() if n == team_valve}))))
    if not v_team_ok or (not k_team_ok and not nodata):
        semantics.append(team_valve)
    clauses.append(("valve-timing", None if nodata else (kills_ok and v_team_ok and k_team_ok),
                    "within each instance <= %g s guest of its own death/kill row: %s death guest %.2f; %s kill row guest %s"
                    % (VALVE_WINDOW_GUEST_S, vt, gV, kt, _fmt(K.guest_at(k_in[0][0])) if k_in else "n/a")))
    # alive byte
    al = [V.rows[i].actor.alive for i in V.rows_between(d_sh, v_valve1, lambda r: r.actor is not None and r.actor.alive is not None)]
    if not al:
        nodata.append("%s:alive-byte-after-death" % vt)
    else:
        left = any(x != 1 for x in al)
        clauses.append(("+0xF7A", left, "%s alive byte over guest %.2f..%.2f: %s" % (vt, gV, gV + VALVE_WINDOW_GUEST_S, sorted(set(al)))))
        if not left:
            semantics.append("+0xF7A")
    if nodata:
        raise _Decided(NO_DATA, nodata[0])
    if semantics:
        raise _Decided(KILL_SEMANTICS, ",".join(semantics))
    return gV


def _facts(X):
    hp = [r.actor.hp for r in X.rows if r.actor is not None and r.actor.intact and r.actor.hp is not None]
    strings = [r.clock_string for r in X.rows if r.clock_string is not None]
    return {"steps": {n: [(b, aft) for _, b, aft in X.steps(n)] for n in REQUIRED_VALVES},
            "step_times": {n: [round(t, 2) for t, _, _ in X.steps(n)] for n in REQUIRED_VALVES},
            "valve_rows": {n: sum(1 for r in X.rows if r.valves.get(n) is not None) for n in REQUIRED_VALVES},
            "hp_rows": len(hp),
            "hp_values": sorted(set(round(h, 6) for h in hp)),
            "clock_strings": (strings[0], strings[-1]) if strings else None,
            "freezes": [(round(a, 2), round(b, 2)) for a, b in X.freezes]}


def _deaths(X):
    out, prev = [], {}
    for i, r in enumerate(X.rows):
        a = r.actor
        if a is None or a.hp is None:
            continue
        p = prev.get(a.addr)
        if p is not None and p > 0 and a.hp <= 0:
            out.append(i)
        prev[a.addr] = a.hp
    return out


RANK = {KILL: 0, KILL_SEMANTICS: 1, NO_DATA: 2, NO_KILL: 3}


def score_runs(run_a, run_b, shooter=None, offset_b=None, grenade_mask=0):
    """Two parsed runs (A = host, B = joiner) -> Verdict."""
    if offset_b is not None:
        off, how = offset_b, "--offset-b"
    elif run_a.move_scale_0 is not None and run_b.move_scale_0 is not None:
        off, how = run_a.move_scale_0 - run_b.move_scale_0, "MoveScale #0 on both (round start)"
    else:
        off, how = None, "none"
    A = Series("A", run_a, 0.0)
    B = Series("B", run_b, off if off is not None else 0.0)
    facts = {"A": _facts(A), "B": _facts(B), "alignment": (off, how)}
    base = [("alignment", off is not None, "B + %s s (%s); blind: round-start delivery can differ by instance"
             % (_fmt(off), how))]

    for X in (A, B):
        c = row_counts(X.run)
        for item in ("peek", "actor", "health", "guest_clock") + REQUIRED_VALVES:
            if c[item] == 0:
                v = Verdict(NO_DATA, "%s:%s" % (X.tag, item), clauses=base + [
                    ("rows-read", False, "%s: %s" % (X.tag, " ".join("%s=%d" % kv for kv in c.items())))], facts=facts)
                return v
        base.append(("rows-read", True, "%s: %s" % (X.tag, " ".join("%s=%d" % kv for kv in c.items()))))

    events = sorted([(A.t[i], A, B, i) for i in _deaths(A)] + [(B.t[i], B, A, i) for i in _deaths(B)], key=lambda e: e[0])
    if not events:
        lines = []
        for X in (A, B):
            f = facts[X.tag]
            lines.append(("no-death", True, "%s +0x1044 values %s over %d rows; total_mp_kills %s; aiteam_00 %s; aiteam_08 %s; "
                          "mp_round_count %s at %s; clock %s"
                          % (X.tag, f["hp_values"], f["hp_rows"], f["steps"]["total_mp_kills"] or "unchanged",
                             f["steps"]["aiteam_00"] or "unchanged", f["steps"]["aiteam_08"] or "unchanged",
                             f["steps"]["mp_round_count"] or "unchanged", f["step_times"]["mp_round_count"],
                             f["clock_strings"] or "absent")))
        # kill-direction steps only: total_mp_kills up, aiteam_* down (aiteam_* 0 -> 1 is round start)
        orphan = [(X.tag, n, round(t, 2)) for X in (A, B) for n, up in (("total_mp_kills", True), ("aiteam_00", False), ("aiteam_08", False))
                  for t, b, aft in X.steps(n) if (aft > b) == up]
        v = Verdict(NO_KILL, R_NO_DEATH, clauses=base + lines, facts=facts)
        if orphan:
            v.notes.append("kill-valve steps with no actor death: %s" % orphan)
        return v
    if off is None:
        return Verdict(NO_DATA, "alignment", clauses=base, facts=facts)

    results = []
    for _, V, K, di in events:
        clauses, notes = [], []
        try:
            g = _score_event(None, V, K, di, shooter, grenade_mask, clauses, notes)
            v = Verdict(KILL, killer=K.tag, victim=V.tag, t=g)
        except _Decided as d:
            v = Verdict(d.word, d.reason, killer=K.tag, victim=V.tag)
        v.clauses = base + [("event", None, "candidate victim %s at shared %.2f" % (V.tag, V.t[di]))] + clauses
        v.notes = notes
        v.facts = facts
        results.append(v)
    best = min(results, key=lambda v: RANK[v.word])
    if len(results) > 1:
        best.notes.append("%d candidate deaths: %s" % (len(results), "; ".join(r.headline() for r in results)))
    return best


def score_logs(lines_a, lines_b, **kw):
    return score_runs(parse_log(lines_a), parse_log(lines_b), **kw)


def _read(path):
    with open(path, "r", errors="replace") as f:
        return f.read().split("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tools_py.parity.verdict_replay",
                                 description="Valve-primary kill verdict over two run logs (exit 0 KILL / 1 NO-KILL or KILL-SEMANTICS / 2 NO-DATA).")
    ap.add_argument("log_a", help="instance A (host) run log")
    ap.add_argument("log_b", help="instance B (joiner) run log")
    ap.add_argument("--shooter", choices=("A", "B"), default=None)
    ap.add_argument("--offset-b", type=float, default=None, help="seconds added to B's host clock (default: MoveScale #0)")
    ap.add_argument("--grenade-mask", type=lambda s: int(s, 0), default=0,
                    help="pad button mask of the grenade throw (uncalibrated by default; see GRENADE notes)")
    args = ap.parse_args(argv)
    try:
        la, lb = _read(args.log_a), _read(args.log_b)
    except OSError as e:
        print("%s cannot-read (%s)" % (NO_DATA, e))
        return 2
    v = score_logs(la, lb, shooter=args.shooter, offset_b=args.offset_b, grenade_mask=args.grenade_mask)
    print(v.text())
    return v.exit_code


if __name__ == "__main__":
    sys.exit(main())
