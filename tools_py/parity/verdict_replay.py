"""Replay kill verdict from two stored run logs -- the VALVE-primary scorer (Sprint 5 Task 6 Step 1).

    python -m tools_py.parity.verdict_replay <run_A.log> <run_B.log> [--shooter A|B] [--per-round]
                                             [--offset-b S] [--grenade-mask 0xNNNN]

Prints one verdict line (with --per-round: one per round), each followed by one line per spec §5.1 /
§5.1.1 clause with its measured values:
  KILL killer=<A|B> victim=<A|B> t=<victim guest clock> round=<n>                          exit 0
  NO-KILL <no-death|fall|self|unattributed|team|round-ended-first|timing> [round=<n>]      exit 1
  KILL-SEMANTICS <valve>[,<valve>...] round=<n>                                           exit 1
  NO-DATA <item> [round=<n>]                                                              exit 2
`round` is 1-based: mp_round_count + 1 on the victim instance at the death ("ROUND 1 OF 11" reads
mp_round_count 0). With several lines the exit code is the best verdict's.

This is the SECOND, independent scorer: `online_match_ours.KillWatch` is primary on the actor fields,
this one is primary on the round-state valves (`total_mp_kills`, `aiteam_*`), corroborated by the
actor fields. It deliberately imports neither `verdict_core` nor `online_match_ours` (a test asserts
the import set) and has its own parser; the tests run both parsers over the same raw fixtures so a
parser divergence shows up as a test disagreement.

The bars are spec §5.1 (Amendment A) and its §5.1.1 clarifications (R53, amended R56), pre-registered
2026-09-13 before any ladder match. They are named constants below, each asserted verbatim by the
tests; they may not be loosened after a kill is seen.

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
MoveScale #0 (round start) unless --offset-b is given. Guest time: the float at 0x4365c0 per row --
mission time, 0.57-0.72 guest s per host s over whole rounds (3c, 8c), frozen from an mp_round_count
step to the clock restart, not reset between rounds (§5.1.1). Every "N s" window of the bars is in
guest seconds unless it says host.
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
R_TIMING = "timing"
S_ACTOR_DESTROYED = "actor-destroyed"

# ---------------------------------------------------------------------------------------------
# spec §5.1 / §5.1.1 bars -- pre-registered, asserted verbatim by the tests
# ---------------------------------------------------------------------------------------------
# Goal 6 attribution window: the killer's R1 (or grenade) injected within 3 guest s of the KILLER
# instance's own guest clock before the death, with |dy| <= 10 and 3-D <= 60 throughout; clipped to
# the death's round. Blind: an unrelated damage source during a burst from 60 units.
ATTRIBUTION_WINDOW_S = 3.0
ATTRIBUTION_DY_MAX = 10.0
ATTRIBUTION_3D_MAX = 60.0
# Valve timing: within each instance, a step within 3 guest s of that instance's own reference row
# (victim: its death row; killer: its kill row). The killer's kill row is its first kill-valve step
# in [death - 3 host s, death + 20 host s], same round on both instances, each step paired with at
# most one death; a candidate only after death + 20 s -> NO-KILL timing (§5.1.1 R56).
VALVE_WINDOW_GUEST_S = 3.0
CROSS_INSTANCE_MAX_S = 20.0
KILL_STEP_BEFORE_DEATH_S = 3.0
# No victim y drop > 20 in the 2 guest s before; no grenade on the victim's own pad in the 10 guest s
# before; both clipped to the round.
FALL_WINDOW_S = 2.0
FALL_DROP_MAX = 20.0
SELF_GRENADE_WINDOW_S = 10.0
# total_mp_kills steps by exactly one on at least one instance; the victim team's aiteam_* drops by
# exactly one on both.
KILLS_STEP = 1
AITEAM_DROP = 1
# Instantaneous clauses (§5.1.1, amended R58): the killer's +0x1044 > 0 on EVERY intact killer row
# within +-0.5 s host of the victim's death row (a killer at <= 0 anywhere in that half-second is a
# trade); the victim's +0xF7A passes when an INTACT victim row reads != 1 within [death row, death row
# + 2 s host] -- Goal 2's "leaves 1 within 2 s", so a one-row lag behind +0x1044 is not a surprise.
# +0xF7A still 1 on every intact row through that window -> KILL-SEMANTICS +0xF7A. Blind: a byte that
# leaves 1 for a reason other than the death inside those 2 s.
INSTANT_S = 0.5
ALIVE_LEAVE_S = 2.0
# Actor destroyed at death (§5.1.1): word 0 leaves the vtable within 2 s after an intact row whose
# +0x1044 < 1.0, kill valves stepping, no intact row reading <= 0 -> KILL-SEMANTICS actor-destroyed.
ACTOR_DESTROYED_S = 2.0
# Freeze (§5.1.1): a window whose guest-clock advance is below 25 % of its host span, or any stall
# >= 1.0 s after merging stalls separated by <= one advancing row pair -> NO-DATA. A "stall" is a row
# pair on which the guest clock advanced by less than 25 % of the host time between the rows.
# Measured against: 0.57-0.72 guest s per host s in play; 8c's fragmented stalls (500.71-505.63 and
# 506.13-514.07, split by one pair). Blind: a stall under 1 s that stands alone in a window whose
# overall rate stays >= 25 %.
FREEZE_RATE_MAX = 0.25
FREEZE_MIN_HOST_S = 1.0
# A kill that ends the round (§5.1.1 R60): the guest clock freezes from each mp_round_count step to the
# clock restart (8c: 783.34-788.88 / 783.32-788.72, restart ~5.6 s after the step). That stall is the
# round boundary, not a freeze; forward windows end at the death round's own step; kill-valve steps up
# to that step, or within 20 s host after the death even if after it, still belong to the death's round.
# A stall is a boundary when it starts within BOUNDARY_TOL_S of an mp_round_count step on that instance
# and ends by the next clock restart (either instance) + ROW_MAX_GAP_S, at most ROUND_BOUNDARY_MAX_S
# after the step (instruments, not bars). Blind: a real freeze that starts with the round step and ends
# before the restart is read as the boundary.
BOUNDARY_TOL_S = 0.5
ROUND_BOUNDARY_MAX_S = 10.0
# Freeze overlap is strict (R60): a stall that only touches a window's edge does not overlap it.
# --shooter defaults to the host (§5.1.1); a kill by B scores only with --shooter B.
DEFAULT_SHOOTER = "A"
# Pad bits (online_login_ours PAD_BUTTON): R1 = 11. The grenade button is NOT calibrated (plan A7):
# the victim's possible self-grenade is ANY non-R1 face/shoulder press -- L2 8, R2 9, L1 10, TRIANGLE
# 12, CIRCLE 13, CROSS 14, SQUARE 15 (§5.1.1); the killer's grenade counts as a kill input only when
# --grenade-mask names it. Blind: a victim pressing a harmless face button in the window costs a
# round (NO-KILL self), never a false PASS.
R1_MASK = 1 << 11
SELF_GRENADE_MASK = 0xF700

# ---------------------------------------------------------------------------------------------
# instruments -- not bars; each with what it does not separate
# ---------------------------------------------------------------------------------------------
SAMPLER_PERIOD_S = 0.25
CLOCK_ANCHOR_MIN_SPACING_S = 5.0
ACTOR_VTABLE = 0x006691A0               # r0001; the number printed in messages
# ... and the set a row is IDENTIFIED against. Every one of this module's guest numbers has a value per
# revision (r0004 relinked them all) and a `[peek]` row carries exactly one column's worth, so membership
# replays an r0004 run's rows too. LITERALS on purpose: this module imports nothing but the standard
# library (test_verdict_replay's TestImportSet) so that it is an independently written second scorer,
# sharing no code -- and so no bug -- with verdict_core/online_match_ours, and so that a pinned harness
# can replay a log with no tools_py around it. Their home is tools_py/parity/guest_addresses.py, and
# test_verdict_replay checks EVERY one of these three pairs against it rather than trusting this copy.
ACTOR_VTABLES = frozenset({0x006691A0, 0x00668B20})
ACTOR_POS_WORDS = (7, 8, 9)
HEALTH_OFFSET = 0x1044             # float, <= 0 dead (research/19 F1)
ALIVE_OFFSET = 0xF7A               # byte, 1 = alive
TEAM_WORD_OFFSET = 0xC8            # word, meaning OPEN (research/21 §9.6): reported, never gated
# The clock, both ways of reading it, finished the same way as the vtable above (review F6: the actor was
# revision-agnostic and these were not, so an r0004 replay parsed the actor, health, alive byte and team
# word and then had no time base at all -- a PARTIAL read where a clean total NO-DATA was the honest
# answer). The scalars stay r0001, because that is what every message prints; the SETS are what a row is
# matched against.
GUEST_CLOCK_ADDR = 0x4365C0        # r0001 guest_clock -- the float that is the time base of every window
GUEST_CLOCK_ADDRS = frozenset({0x004365C0, 0x00442FD0})
CLOCK_STRING_ADDR = 0x408F10       # r0001 clock_string -- the HUD "MM:SS"
CLOCK_STRING_ADDRS = frozenset({0x00408F10, 0x004358D0})
MOVE_SCALE_NAME = "MoveScale"
REQUIRED_VALVES = ("mp_round_count", "player_team", "aiteam_00", "aiteam_08", "total_mp_kills")
TEAM_VALVE = {0: "aiteam_00", 8: "aiteam_08"}   # player_team 0 SEALS / 8 TERRORISTS (research/21 §9.6)
# Rows further apart than this do not cover a window (verdict_core's CONTACT_ROW_MAX_GAP_S value,
# kill2 B's worst healthy 1.08 s). Blind: motion inside a 1.25 s gap.
ROW_MAX_GAP_S = 1.25
# Pairing a row with the other instance's nearest row (two 4 Hz samples). Blind: 0.5 s at 40 u/s
# is 20 units of misplacement.
PAIR_MAX_S = 0.5


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
    addr = next((a for a, w in items if w and w[0] in ACTOR_VTABLES), None)
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
        if a in CLOCK_STRING_ADDRS and words:
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
        g = next((w[0] for a, w in items if a in GUEST_CLOCK_ADDRS and w), None)
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
        self.g_t = [x for x, _ in self.g_rows]
        self.stalls = self._stalls()
        self.boundaries = []                                   # [(round step t, latest stall end)], set by score_runs

    def _stalls(self):
        """Merged stalls (§5.1.1): runs of stalled row pairs, merged across <= one advancing pair,
        kept when they span >= FREEZE_MIN_HOST_S of host time. [(t0, t1)]"""
        pairs = [(t0, t1, (g1 - g0) < FREEZE_RATE_MAX * (t1 - t0))
                 for (t0, g0), (t1, g1) in zip(self.g_rows, self.g_rows[1:]) if t1 > t0]
        runs, i = [], 0
        while i < len(pairs):
            if pairs[i][2]:
                j = i
                while j + 1 < len(pairs) and pairs[j + 1][2]:
                    j += 1
                runs.append([i, j])
                i = j + 1
            else:
                i += 1
        merged = []
        for r in runs:
            if merged and r[0] - merged[-1][1] <= 2:          # exactly one advancing pair between
                merged[-1][1] = r[1]
            else:
                merged.append(r)
        return [(pairs[a][0], pairs[b][1]) for a, b in merged if pairs[b][1] - pairs[a][0] >= FREEZE_MIN_HOST_S]

    def is_boundary(self, st):
        a, b = st
        return any(abs(a - t) <= BOUNDARY_TOL_S and b <= end_max for t, end_max in self.boundaries)

    def freeze(self, t0, t1):
        """A description of the freeze overlapping [t0, t1], or None (§5.1.1: a merged stall strictly
        overlapping the window, or the window's own guest-clock rate below FREEZE_RATE_MAX). Round-boundary
        stalls (R60) are neither: they are left out of both tests."""
        real = [st for st in self.stalls if not self.is_boundary(st)]
        st = next(((a, b) for a, b in real if a < t1 and b > t0), None)
        if st is not None:
            return "stall-%.1f-%.1f" % st
        span = (t1 - t0) - sum(max(0.0, min(b, t1) - max(a, t0)) for a, b in self.stalls if self.is_boundary((a, b)))
        if span >= FREEZE_MIN_HOST_S:
            g0, g1 = self.guest_at(t0), self.guest_at(t1)
            if g0 is None or g1 is None:
                return "guest-clock-unreadable-%.1f-%.1f" % (t0, t1)
            if g1 - g0 < FREEZE_RATE_MAX * span:
                return "rate-%.2f-over-%.1f-%.1f" % ((g1 - g0) / span, t0, t1)
        return None

    def guest_at(self, t):
        ts = self.g_t
        if not ts:
            return None
        k = bisect.bisect_right(ts, t)
        if k == 0:
            return None
        if k == len(ts):
            return self.g_rows[-1][1] if t - ts[-1] <= 1e-9 else None
        (a, ga), (b, gb) = self.g_rows[k - 1], self.g_rows[k]
        if b - a > ROW_MAX_GAP_S:
            return None
        return ga + (gb - ga) * (t - a) / (b - a)

    def shared_of_guest(self, g, anchor_t, forward=False):
        """Shared time at which the guest clock read `g`, searching from anchor_t backwards (or
        forwards). None when the rows end first."""
        k = bisect.bisect_right(self.g_t, anchor_t) - 1
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
        k = bisect.bisect_right(self.t, t + 1e-9) - 1
        for i in range(k, -1, -1):
            if pred(self.rows[i]):
                return i
        return None

    def rows_between(self, t0, t1, pred=lambda r: True):
        k0, k1 = bisect.bisect_left(self.t, t0 - 1e-9), bisect.bisect_right(self.t, t1 + 1e-9)
        return [i for i in range(k0, k1) if pred(self.rows[i])]

    def covered(self, t0, t1, pred):
        """Rows satisfying pred cover [t0, t1] with no gap > ROW_MAX_GAP_S (edges included)."""
        ts = [self.t[i] for i in range(len(self.rows)) if pred(self.rows[i])]
        k0 = bisect.bisect_right(ts, t0 + 1e-9) - 1
        k1 = bisect.bisect_left(ts, t1 - 1e-9)
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

    def torn_in(self, t0, t1):
        return any(t0 <= t + self.shift <= t1 for t in self.run.pad_unrecovered)

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
    round: int = None                                  # 1-based: mp_round_count + 1 at the death
    clauses: list = field(default_factory=list)       # [(name, ok True|False|None, text)]
    facts: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    @property
    def exit_code(self):
        return EXIT[self.word]

    def headline(self):
        if self.word == KILL:
            h = "KILL killer=%s victim=%s t=%.2f" % (self.killer, self.victim, self.t)
        else:
            h = "%s %s" % (self.word, self.reason)
        return h + (" round=%d" % self.round if self.round is not None else "")

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


def _press_in(pads, t0, t1, mask, count_held=True):
    """A press of `mask` inside [t0, t1], or (count_held) held when the window opened. A window
    clipped to its round start does not count a press made before the round (count_held=False)."""
    held = None
    for t, b in pads:
        if t < t0:
            held = b
            continue
        if t > t1:
            break
        if b is not None and b & mask:
            return t
    if count_held and held is not None and held & mask:
        return t0
    return None


def _fmt(v, nd=2):
    return "n/a" if v is None else ("%.*f" % (nd, v))


def _events(X):
    """Candidate deaths on one instance: [(row index, kind)], kind
      'intact'    -- an intact row reads +0x1044 <= 0 after a read > 0;
      'destroyed' -- §5.1.1: the block stops being identified within ACTOR_DESTROYED_S after an intact
                     row whose +0x1044 is in (0, 1.0);
      'untrusted' -- a <= 0 read only from a block whose word 0 already left the vtable."""
    out, prev_hp, last_intact, destroyed_open = [], {}, None, False
    for i, r in enumerate(X.rows):
        a = r.actor
        if a is not None and a.intact:
            if a.hp is not None:
                p = prev_hp.get(a.addr)
                if p is not None and p > 0 and a.hp <= 0:
                    out.append((i, "intact"))
                prev_hp[a.addr] = a.hp
                last_intact = (i, a.hp)
            destroyed_open = False
            continue
        if destroyed_open:
            continue
        if last_intact is not None and 0 < last_intact[1] < 1.0 and X.t[i] - X.t[last_intact[0]] <= ACTOR_DESTROYED_S:
            out.append((i, "destroyed"))
            destroyed_open = True
            continue
        if a is not None and a.hp is not None:
            p = prev_hp.get(a.addr)
            if p is not None and p > 0 and a.hp <= 0:
                out.append((i, "untrusted"))
            prev_hp[a.addr] = a.hp
    return out


def _intact(r):
    return r.actor is not None and r.actor.intact


def _pos(r):
    return _intact(r) and r.actor.pos_nonzero


def _score_event(V, K, di, kind, ctx, clauses, out):
    """One candidate death (victim instance V, its row index di). Raises _Decided, or returns the
    victim guest clock of a KILL. Clauses are appended as they are measured; the first decisive clause
    decides. `out` receives the round index as soon as it is read. The kill-valve steps this death
    pairs with are selected and CONSUMED before any clause is judged (§5.1.1 R60)."""
    vt, kt = V.tag, K.tag
    drow = V.rows[di]
    d_sh = V.t[di]
    r = V.valve_at("mp_round_count", d_sh)
    if r is None:
        raise _Decided(NO_DATA, "%s:mp_round_count-at-death" % vt)
    out["round"] = r + 1
    if kind == "untrusted":
        clauses.append(("victim-death", None, "%s +0x1044=%s read only from a block whose word 0 left the vtable"
                        % (vt, _fmt(drow.actor.hp, 3))))
        raise _Decided(NO_DATA, "%s:actor-word0-at-death" % vt)
    if kind == "intact":
        prior = [t for t, rr in ctx["intact_deaths"][vt] if rr == r
                 and not any(t < st <= d_sh for st, _, _ in V.steps("mp_round_count"))]
        ctx["intact_deaths"][vt].append((d_sh, r))
        if prior:
            clauses.append(("victim-death", False, "%s second intact death in round %d (first at %.2f, no round step between)"
                            % (vt, r + 1, prior[-1])))
            raise _Decided(NO_DATA, "double-death")
    gV = drow.guest
    if gV is None:
        raise _Decided(NO_DATA, "%s:guest-clock-at-death" % vt)
    li = V.last_row_at(d_sh, _pos) if kind == "destroyed" else di
    if li is None:
        raise _Decided(NO_DATA, "%s:actor-rows-before-death" % vt)
    d_pos = V.t[li]
    if kind == "destroyed":
        lh = V.rows[V.last_row_at(d_sh, lambda x: _intact(x) and x.actor.hp is not None)].actor.hp
        clauses.append(("victim-death", None, "%s actor destroyed at shared %.2f guest %.2f: last intact +0x1044=%.3f "
                        "(< 1.0), no intact row <= 0 (§5.1.1)" % (vt, d_sh, gV, lh)))
    else:
        clauses.append(("victim-death", True, "%s +0x1044=%.3f word0=%08x at shared %.2f guest %.2f"
                        % (vt, drow.actor.hp, ACTOR_VTABLE, d_sh, gV)))

    # --- round: start, the death round's own step on each instance ----------------------------
    rK = K.valve_at("mp_round_count", d_sh)
    if rK is None:
        raise _Decided(NO_DATA, "%s:mp_round_count-at-death" % kt)
    into = [t for X in (V, K) for t, b, aft in X.steps("mp_round_count") if aft == r and t <= d_sh]
    step_t = max(into, default=-math.inf)
    restarts = [t for X in (V, K) for t in X.round_starts() if step_t <= t <= d_sh]
    rs = max(restarts, default=step_t)
    # R60: every forward window ends at the death round's own mp_round_count step on that instance
    end_of = {X.tag: min([t for t, b, aft in X.steps("mp_round_count") if b == r and t > d_sh], default=math.inf)
              for X in (V, K)}

    # --- team and the pairing selection (consumed here, whatever the verdict) --------------------
    v_team = V.valve_at("player_team", d_sh)
    k_team = K.valve_at("player_team", d_sh)
    if v_team is None or k_team is None:
        raise _Decided(NO_DATA, "%s:player_team-at-death" % (vt if v_team is None else kt))
    if v_team not in TEAM_VALVE:
        raise _Decided(NO_DATA, "%s:player_team-value-%d" % (vt, v_team))
    team_valve = TEAM_VALVE[v_team]
    other_valve = next(n for tm, n in TEAM_VALVE.items() if tm != v_team)
    k_lo, k_hi = d_sh - KILL_STEP_BEFORE_DEATH_S, d_sh + CROSS_INSTANCE_MAX_S
    used = ctx["consumed"]

    def member(X, t):
        # R60: a kill step belongs to the death's round up to that round's step, or within 20 s host
        # after the death even if after the step
        val = X.valve_at("mp_round_count", t)
        return val == r or (val == r + 1 and d_sh < t <= k_hi)

    def kill_steps(X, lo, hi):
        return sorted([(t, "total_mp_kills", b, aft) for t, b, aft in X.steps("total_mp_kills") if aft > b and lo <= t <= hi] +
                      [(t, team_valve, b, aft) for t, b, aft in X.steps(team_valve) if aft < b and lo <= t <= hi])

    k_cands = [c for c in kill_steps(K, k_lo, k_hi) if member(K, c[0]) and (kt, c[1], c[0]) not in used]
    k_late = [c for c in kill_steps(K, k_hi + 1e-6, math.inf)
              if K.valve_at("mp_round_count", c[0]) == r and (kt, c[1], c[0]) not in used]
    k_sel = {}
    for c in k_cands:
        k_sel.setdefault(c[1], c)
    kill_t = k_cands[0][0] if k_cands else None
    v_sel, v_unreadable = {}, []
    lo_v = rs if rs > -math.inf else -math.inf
    for c in kill_steps(V, lo_v, k_hi):
        if c[1] in v_sel or not member(V, c[0]) or (vt, c[1], c[0]) in used:
            continue
        g = V.guest_at(c[0])
        if g is None:
            v_unreadable.append(c)
            continue
        if abs(g - gV) <= VALVE_WINDOW_GUEST_S:
            v_sel[c[1]] = c + (g - gV,)
    for tag, sel in ((kt, k_sel), (vt, v_sel)):
        for c in sel.values():
            used.add((tag, c[1], c[0]))

    # --- round-end signals before the death ----------------------------------------------------
    ended = []
    if rK != r:
        ended.append("%s mp_round_count %d at the death, %s %d" % (kt, rK, vt, r))
    for X in (V, K):
        for i in X.rows_between(rs + 1e-6 if rs > -math.inf else -1e18, d_sh, lambda x: x.clock_string == "00:00"):
            ended.append("%s clock 00:00 at %.2f" % (X.tag, X.t[i]))
            break
        for t, b, aft in X.steps("mp_game_over"):
            if rs < t <= d_sh:
                ended.append("%s mp_game_over %d->%d at %.2f" % (X.tag, b, aft, t))
    ci = {X.tag: X.last_row_at(d_sh, lambda x: x.clock_string is not None) for X in (V, K)}
    clock_txt = "; ".join("%s clock %s" % (X.tag, X.rows[ci[X.tag]].clock_string if ci[X.tag] is not None else "absent")
                          for X in (V, K))
    clauses.append(("round-state", not ended, "round %d (mp_round_count %d on both needed) start %s, ends %s; %s; %s"
                    % (r + 1, r, _fmt(rs if rs > -math.inf else None),
                       ", ".join("%s %s" % (tg, _fmt(e if e < math.inf else None)) for tg, e in sorted(end_of.items())),
                       "; ".join(ended) or "no step, no 00:00, no game over", clock_txt)))
    if ended:
        raise _Decided(NO_KILL, R_ROUND_ENDED)

    # --- windows (shared host time), clipped to the round; freezes --------------------------------
    gK = K.guest_at(d_sh)
    if gK is None:
        raise _Decided(NO_DATA, "%s:guest-clock-at-death" % kt)

    def clip(t, name):
        if t is None:
            if rs > -math.inf:
                return rs, True
            raise _Decided(NO_DATA, name)
        return (rs, True) if t < rs else (t, False)

    c_self, cl_self = clip(V.shared_of_guest(gV - SELF_GRENADE_WINDOW_S, d_sh), "%s:rows-before-self-window" % vt)
    c_fall, cl_fall = clip(V.shared_of_guest(gV - FALL_WINDOW_S, d_sh), "%s:rows-before-fall-window" % vt)
    v1 = V.shared_of_guest(gV + VALVE_WINDOW_GUEST_S, d_sh, forward=True)
    v1 = min(v1 if v1 is not None else math.inf, end_of[vt])
    if v1 == math.inf:
        raise _Decided(NO_DATA, "%s:rows-after-valve-window" % vt)
    c_attr, cl_attr = clip(K.shared_of_guest(gK - ATTRIBUTION_WINDOW_S, d_sh), "%s:rows-before-attribution-window" % kt)
    fz_v = V.freeze(c_self, v1)
    fz_k = K.freeze(c_attr, d_sh)
    clauses.append(("freeze", not (fz_v or fz_k), "%s window %.2f..%.2f %s; %s window %.2f..%.2f %s"
                    % (vt, c_self, v1, fz_v or "none", kt, c_attr, d_sh, fz_k or "none")))
    if fz_v:
        raise _Decided(NO_DATA, "%s:guest-clock-freeze-%s" % (vt, fz_v))
    if fz_k:
        raise _Decided(NO_DATA, "%s:guest-clock-freeze-%s" % (kt, fz_k))

    # --- fall ----------------------------------------------------------------------------------
    if not V.covered(c_fall, d_pos, _pos):
        raise _Decided(NO_DATA, "%s:actor-rows-in-fall-window" % vt)
    ys = [V.rows[i].actor.y for i in V.rows_between(c_fall, d_pos, _pos)]
    drop, top = 0.0, -math.inf
    for y in ys:
        top = max(top, y)
        drop = max(drop, top - y)
    clauses.append(("no-fall", drop <= FALL_DROP_MAX, "%s max y drop %.2f over %.2f..%.2f%s (bar <= %g in %g guest s)"
                    % (vt, drop, c_fall, d_pos, " clipped to round" if cl_fall else "", FALL_DROP_MAX, FALL_WINDOW_S)))
    if drop > FALL_DROP_MAX:
        raise _Decided(NO_KILL, R_FALL)

    # --- self grenade --------------------------------------------------------------------------
    if V.torn_in(c_self, d_sh):
        raise _Decided(NO_DATA, "%s:torn-pad-line-in-self-window" % vt)
    self_mask = ctx["grenade_mask"] or SELF_GRENADE_MASK
    sp = _press_in(V.pads_shared(), c_self, d_sh, self_mask, count_held=not cl_self)
    clauses.append(("no-self-grenade", sp is None, "%s pad mask %04x over %.2f..%.2f%s: %s"
                    % (vt, self_mask, c_self, d_sh, " clipped to round" if cl_self else "",
                       "press at %.2f" % sp if sp is not None else "none")))
    if sp is not None:
        raise _Decided(NO_KILL, R_SELF)

    # --- killer ------------------------------------------------------------------------------
    if ctx["shooter"] != kt:
        clauses.append(("killer", False, "%s is not the shooter (--shooter %s)" % (kt, ctx["shooter"])))
        raise _Decided(NO_KILL, R_UNATTRIBUTED)
    k_gone = [t for t in ctx["destroyed"][kt] if d_sh - INSTANT_S <= t <= d_sh + INSTANT_S]
    if k_gone:
        clauses.append(("killer-alive", False, "%s actor block destroyed at %.2f after an intact +0x1044 < 1.0 (R60)"
                        % (kt, k_gone[0])))
        raise _Decided(NO_KILL, R_UNATTRIBUTED)
    k_hp_row = lambda x: _intact(x) and x.actor.hp is not None
    if not K.covered(d_sh - INSTANT_S, d_sh + INSTANT_S, k_hp_row):
        raise _Decided(NO_DATA, "%s:intact-rows-not-covering-the-death" % kt)
    near = K.rows_between(d_sh - INSTANT_S, d_sh + INSTANT_S, k_hp_row)
    if not near:
        raise _Decided(NO_DATA, "%s:actor-rows-at-death" % kt)
    k_hp = min(K.rows[i].actor.hp for i in near)
    clauses.append(("killer-alive", k_hp > 0, "%s min +0x1044 %.3f over %d row(s) within %.1f s of the death"
                    % (kt, k_hp, len(near), INSTANT_S)))
    if not k_hp > 0:
        raise _Decided(NO_KILL, R_UNATTRIBUTED)

    # --- attribution ---------------------------------------------------------------------------
    if K.torn_in(c_attr, d_sh):
        raise _Decided(NO_DATA, "%s:torn-pad-line-in-attribution-window" % kt)
    fire_mask = R1_MASK | (ctx["grenade_mask"] or 0)
    fp = _press_in(K.pads_shared(), c_attr, d_sh, fire_mask, count_held=not cl_attr)
    a_end = min(d_sh, d_pos)
    if not (K.covered(c_attr, a_end, _pos) and V.covered(c_attr, a_end, _pos)):
        raise _Decided(NO_DATA, "actor-rows-in-attribution-window")
    worst_dy, worst_3d = 0.0, 0.0
    for X, Y in ((K, V), (V, K)):
        yi = [i for i in range(len(Y.rows)) if _pos(Y.rows[i])]
        yt = [Y.t[i] for i in yi]
        for i in X.rows_between(c_attr, a_end, _pos):
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
                    "%s fire mask %04x over %s guest %.2f..%.2f (shared %.2f..%.2f%s): %s; max |dy| %.2f (<= %g), max 3-D %.2f (<= %g)"
                    % (kt, fire_mask, kt, gK - ATTRIBUTION_WINDOW_S, gK, c_attr, d_sh, " clipped to round" if cl_attr else "",
                       "press at %.2f" % fp if fp is not None else "none", worst_dy, ATTRIBUTION_DY_MAX,
                       worst_3d, ATTRIBUTION_3D_MAX)))
    if fp is None or not band:
        raise _Decided(NO_KILL, R_UNATTRIBUTED)

    # --- team: symmetric -- the other team's aiteam_* must not drop on EITHER instance in [d-3, d+20] --
    tw = drow.actor.team_word if drow.actor is not None else None
    clauses.append(("victim-team", k_team != v_team,
                    "%s player_team %d -> %s; %s player_team %d; %s +0xC8 %s (cross-check only, meaning open)"
                    % (vt, v_team, team_valve, kt, k_team, vt, "%08x" % tw if tw is not None else "not peeked")))
    if k_team == v_team:
        raise _Decided(NO_KILL, R_TEAM)
    other = [(X.tag, t, b, aft) for X in (V, K) for t, b, aft in X.steps(other_valve) if aft < b and k_lo <= t <= k_hi]
    if other:
        clauses.append(("team-valve", False, "%s dropped: %s" % (other_valve, other)))
        raise _Decided(NO_KILL, R_TEAM)

    # --- valves: timing, semantics -------------------------------------------------------------
    if kind == "destroyed" and not k_cands and not v_sel:
        clauses.append(("kill-valves", False, "actor block lost with no kill-valve step: not a death"))
        raise _Decided(NO_KILL, R_NO_DEATH)
    if not k_cands and k_late:
        clauses.append(("cross-instance", False, "%s first kill-valve step %+.2f s host after the death (bar <= %g)"
                        % (kt, k_late[0][0] - d_sh, CROSS_INSTANCE_MAX_S)))
        raise _Decided(NO_KILL, R_TIMING)

    nodata, semantics = [], []
    if kind == "destroyed":
        semantics.append(S_ACTOR_DESTROYED)
    for c in v_unreadable:
        nodata.append("%s:guest-clock-at-%s-step" % (vt, c[1]))
    k_steps = {}
    if k_cands:
        g_kill = K.guest_at(kill_t)
        if g_kill is None:
            nodata.append("%s:guest-clock-at-kill-row" % kt)
        else:
            k0 = K.shared_of_guest(g_kill - VALVE_WINDOW_GUEST_S, kill_t)
            k1 = K.shared_of_guest(g_kill + VALVE_WINDOW_GUEST_S, kill_t, forward=True)
            k1 = min(k1 if k1 is not None else math.inf, max(end_of[kt], kill_t))
            if k0 is None or k1 == math.inf:
                nodata.append("%s:rows-around-kill-row" % kt)
            else:
                fz = K.freeze(max(k0, rs), k1)
                if fz:
                    nodata.append("%s:guest-clock-freeze-%s" % (kt, fz))
            for name, (t, _, b, aft) in k_sel.items():
                g = K.guest_at(t)
                if g is None:
                    nodata.append("%s:guest-clock-at-%s-step" % (kt, name))
                    continue
                k_steps[name] = (t, b, aft, g - g_kill)
        clauses.append(("cross-instance", True,
                        "%s kill row at %.2f = death %+.2f s host (window [-%g, +%g]), round %d on both"
                        % (kt, kill_t, kill_t - d_sh, KILL_STEP_BEFORE_DEATH_S, CROSS_INSTANCE_MAX_S, r + 1)))
    elif K.t[-1] < k_hi and K.valve_at("mp_round_count", K.t[-1]) == r:
        nodata.append("%s:rows-end-before-the-%gs-pairing-window" % (kt, CROSS_INSTANCE_MAX_S))
    v_steps = {name: (c[0], c[2], c[3], c[4]) for name, c in v_sel.items()}

    def desc(d, name):
        s = d.get(name)
        return "%s %d->%d at %.2f (guest %+.2f)" % (name, s[1], s[2], s[0], s[3]) if s else "none"

    kills_ok = any(d.get("total_mp_kills") is not None and d["total_mp_kills"][2] - d["total_mp_kills"][1] == KILLS_STEP
                   and abs(d["total_mp_kills"][3]) <= VALVE_WINDOW_GUEST_S for d in (v_steps, k_steps))
    clauses.append(("total_mp_kills", kills_ok, "steps by %d on >= 1 instance: %s: %s; %s: %s"
                    % (KILLS_STEP, vt, desc(v_steps, "total_mp_kills"), kt, desc(k_steps, "total_mp_kills"))))
    v_team_ok = team_valve in v_steps and v_steps[team_valve][1] - v_steps[team_valve][2] == AITEAM_DROP
    k_team_ok = (team_valve in k_steps and k_steps[team_valve][1] - k_steps[team_valve][2] == AITEAM_DROP
                 and abs(k_steps[team_valve][3]) <= VALVE_WINDOW_GUEST_S)
    clauses.append((team_valve, v_team_ok and k_team_ok, "drops by %d on both: %s: %s; %s: %s"
                    % (AITEAM_DROP, vt, desc(v_steps, team_valve), kt, desc(k_steps, team_valve))))
    if not kills_ok:
        semantics.append("total_mp_kills")
    if not (v_team_ok and k_team_ok):
        semantics.append(team_valve)
    clauses.append(("valve-timing", kills_ok and v_team_ok and k_team_ok,
                    "within each instance <= %g guest s of its own reference row: %s death guest %.2f; %s kill row guest %s"
                    % (VALVE_WINDOW_GUEST_S, vt, gV, kt, _fmt(K.guest_at(kill_t)) if kill_t is not None else "n/a")))
    # the alive byte (R58 + R60): an intact row reading exactly 1 in the 2 s before the death row, and an
    # intact row reading != 1 within [death row, death row + 2 s host], that window ending at the round step
    if kind == "intact":
        before = V.rows_between(d_sh - ALIVE_LEAVE_S, d_sh - 1e-6, lambda x: _intact(x) and x.actor.alive == 1)
        a_end = min(d_sh + ALIVE_LEAVE_S, end_of[vt])
        ai = V.rows_between(d_sh, a_end, lambda x: _intact(x) and x.actor.alive is not None)
        left = next((i for i in ai if V.rows[i].actor.alive != 1), None)
        ok = bool(before) and left is not None
        clauses.append(("+0xF7A", ok, "%s alive byte: %d intact row(s) reading 1 in the %g s before; over %d intact row(s) in %.2f..%.2f: %s"
                        % (vt, len(before), ALIVE_LEAVE_S, len(ai), d_sh, a_end,
                           "%d at %+.2f s" % (V.rows[left].actor.alive, V.t[left] - d_sh) if left is not None else "never != 1")))
        if not ok:
            semantics.append("+0xF7A")
    else:
        clauses.append(("+0xF7A", None, "%s block destroyed: not read" % vt))
    if nodata:
        raise _Decided(NO_DATA, nodata[0])
    if semantics:
        raise _Decided(KILL_SEMANTICS, ",".join(semantics))
    return gV


def _facts(X, val=None):
    """Facts over the rows of one round value (val) or the whole run."""
    idx = [i for i, r in enumerate(X.rows) if val is None or r.valves.get("mp_round_count") == val]
    rows = [X.rows[i] for i in idx]

    def steps(name):
        out, prev = [], None
        for i in idx:
            v = X.rows[i].valves.get(name)
            if v is None:
                continue
            if prev is not None and v != prev:
                out.append((X.t[i], prev, v))
            prev = v
        return out
    hp = [r.actor.hp for r in rows if _intact(r) and r.actor.hp is not None]
    strings = [r.clock_string for r in rows if r.clock_string is not None]
    st = {n: steps(n) for n in REQUIRED_VALVES}
    return {"steps": {n: [(b, aft) for _, b, aft in st[n]] for n in REQUIRED_VALVES},
            "step_times": {n: [round(t, 2) for t, _, _ in st[n]] for n in REQUIRED_VALVES},
            "kill_steps": [(X.tag, n, round(t, 2)) for n, up in (("total_mp_kills", True), ("aiteam_00", False), ("aiteam_08", False))
                           for t, b, aft in st[n] if (aft > b) == up],
            "valve_rows": {n: sum(1 for r in rows if r.valves.get(n) is not None) for n in REQUIRED_VALVES},
            "hp_rows": len(hp),
            "hp_values": sorted(set(round(h, 6) for h in hp)),
            "clock_strings": (strings[0], strings[-1]) if strings else None,
            "stalls": [(round(a, 2), round(b, 2)) for a, b in X.stalls if val is None]}


RANK = {KILL: 0, KILL_SEMANTICS: 1, NO_DATA: 2, NO_KILL: 3}


def _no_death(base, facts, A, B, rnd=None):
    f_of = {X.tag: (facts[X.tag] if rnd is None else _facts(X, rnd - 1)) for X in (A, B)}
    lines = []
    for X in (A, B):
        f = f_of[X.tag]
        lines.append(("no-death", True, "%s%s +0x1044 values %s over %d rows; total_mp_kills %s; aiteam_00 %s; aiteam_08 %s; "
                      "mp_round_count %s at %s; clock %s"
                      % (X.tag, "" if rnd is None else " round %d" % rnd, f["hp_values"], f["hp_rows"],
                         f["steps"]["total_mp_kills"] or "unchanged",
                         f["steps"]["aiteam_00"] or "unchanged", f["steps"]["aiteam_08"] or "unchanged",
                         f["steps"]["mp_round_count"] or "unchanged", f["step_times"]["mp_round_count"],
                         f["clock_strings"] or "absent")))
    v = Verdict(NO_KILL, R_NO_DEATH, round=rnd, clauses=base + lines,
                facts=facts if rnd is None else dict(facts, **{t: f for t, f in f_of.items()}))
    orphan = f_of["A"]["kill_steps"] + f_of["B"]["kill_steps"]
    if orphan:
        v.notes.append("kill-valve steps with no actor death: %s" % orphan)
    return v


def score_runs(run_a, run_b, shooter=DEFAULT_SHOOTER, offset_b=None, grenade_mask=0, per_round=False):
    """Two parsed runs (A = host, B = joiner) -> Verdict (per_round: [Verdict], one per round)."""
    shooter = shooter or DEFAULT_SHOOTER
    if offset_b is not None:
        off, how = offset_b, "--offset-b"
    elif run_a.move_scale_0 is not None and run_b.move_scale_0 is not None:
        off, how = run_a.move_scale_0 - run_b.move_scale_0, "MoveScale #0 on both (round start)"
    else:
        off, how = None, "none"
    A = Series("A", run_a, 0.0)
    B = Series("B", run_b, off if off is not None else 0.0)
    restarts = sorted(A.round_starts() + B.round_starts())
    for X in (A, B):
        for t, _, _ in X.steps("mp_round_count"):
            nxt = next((s for s in restarts if s > t), None)
            end_max = t + ROUND_BOUNDARY_MAX_S if nxt is None else min(nxt + ROW_MAX_GAP_S, t + ROUND_BOUNDARY_MAX_S)
            X.boundaries.append((t, end_max))
    facts = {"A": _facts(A), "B": _facts(B), "alignment": (off, how)}
    base = [("alignment", off is not None, "B + %s s (%s); blind: round-start delivery can differ by instance"
             % (_fmt(off), how)),
            ("shooter", None, "%s (default %s; a kill by the other side scores only with --shooter)" % (shooter, DEFAULT_SHOOTER))]
    wrap = (lambda v: [v]) if per_round else (lambda v: v)

    for X in (A, B):
        c = row_counts(X.run)
        for it in ("peek", "actor", "health", "guest_clock") + REQUIRED_VALVES:
            if c[it] == 0:
                return wrap(Verdict(NO_DATA, "%s:%s" % (X.tag, it), clauses=base + [
                    ("rows-read", False, "%s: %s" % (X.tag, " ".join("%s=%d" % kv for kv in c.items())))], facts=facts))
        base.append(("rows-read", True, "%s: %s stalls>=%gs=%d (round boundaries %d)"
                     % (X.tag, " ".join("%s=%d" % kv for kv in c.items()), FREEZE_MIN_HOST_S,
                        len(X.stalls), sum(1 for s in X.stalls if X.is_boundary(s)))))

    ev = {"A": _events(A), "B": _events(B)}
    events = sorted([(A.t[i], A, B, i, k) for i, k in ev["A"]] + [(B.t[i], B, A, i, k) for i, k in ev["B"]],
                    key=lambda e: e[0])
    results = []
    if events and off is None:
        return wrap(Verdict(NO_DATA, "alignment", clauses=base, facts=facts))
    ctx = {"shooter": shooter, "grenade_mask": grenade_mask, "consumed": set(),
           "intact_deaths": {"A": [], "B": []},
           "destroyed": {X.tag: [X.t[i] for i, k in ev[X.tag] if k == "destroyed"] for X in (A, B)}}
    for _, V, K, di, kind in events:
        clauses, out = [], {}
        try:
            g = _score_event(V, K, di, kind, ctx, clauses, out)
            v = Verdict(KILL, killer=K.tag, victim=V.tag, t=g)
        except _Decided as d:
            v = Verdict(d.word, d.reason, killer=K.tag, victim=V.tag)
        v.round = out.get("round")
        v.clauses = base + [("event", None, "candidate victim %s (%s) at shared %.2f" % (V.tag, kind, V.t[di]))] + clauses
        v.facts = facts
        results.append(v)

    def best_of(rs):
        b = min(rs, key=lambda v: RANK[v.word])
        if len(rs) > 1:
            b.notes.append("%d candidate deaths: %s" % (len(rs), "; ".join(x.headline() for x in rs)))
        return b

    if not per_round:
        return best_of(results) if results else _no_death(base, facts, A, B)
    values = sorted({r.valves["mp_round_count"] for X in (A, B) for r in X.rows if r.valves.get("mp_round_count") is not None})
    lines = []
    for val in values:
        here = [v for v in results if v.round == val + 1]
        lines.append(best_of(here) if here else _no_death(base, facts, A, B, rnd=val + 1))
    unrounded = [v for v in results if v.round is None]
    if unrounded:
        lines.append(best_of(unrounded))
    return lines


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
    ap.add_argument("--shooter", choices=("A", "B"), default=DEFAULT_SHOOTER, help="the killer (default A, the host)")
    ap.add_argument("--per-round", action="store_true", help="one verdict per round (mp_round_count value)")
    ap.add_argument("--offset-b", type=float, default=None, help="seconds added to B's host clock (default: MoveScale #0)")
    ap.add_argument("--grenade-mask", type=lambda s: int(s, 0), default=0,
                    help="pad button mask of the killer's grenade throw (uncalibrated by default, plan A7)")
    args = ap.parse_args(argv)
    try:
        la, lb = _read(args.log_a), _read(args.log_b)
    except OSError as e:
        print("%s cannot-read (%s)" % (NO_DATA, e))
        return 2
    res = score_logs(la, lb, shooter=args.shooter, offset_b=args.offset_b, grenade_mask=args.grenade_mask,
                     per_round=args.per_round)
    if args.per_round:
        print("\n".join(v.text() for v in res))
        return min((v for v in res), key=lambda v: RANK[v.word]).exit_code
    print(res.text())
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())
