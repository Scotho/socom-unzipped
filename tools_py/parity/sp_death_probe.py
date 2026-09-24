"""Sprint 5 Task 2 Steps 2-5: one single-player run that confirms the kill readout, with the aim
calibrations riding along.

    python -m tools_py.parity.sp_death_probe --out logs/parity/s5_t2_death          # live (needs the lock)
    python -m tools_py.parity.sp_death_probe --analyze <run_log> [--timeline <json>] # offline
    python -m tools_py.parity.sp_death_probe --replay <run_log>                      # KillWatch replay

LIVE. Launches `drive.py --script scripts/parity/gameplay_death.txt` with `PS2X_SOCOM2_INPUT_FILE`,
waits for drive.py to report the HUD and for the ACTOR block (vtable 0x6691a0, reached through the
static 0x408c58) to give non-zero rows -- never the camera record 0x416054, which can freeze -- then:

  1. yaw: rx = 0x80 +/- {16, 32, 48, 64, 96, 127}, 1.0 s each from rest, both directions; after each
     positive hold a 1.5 s forward hold (so the heading field is validated at six headings) and a 1.5 s
     back hold along the same line (run 2 walked out of the mission area), and two more after full turns;
  2. pitch: one 1.0 s ry=0 and one ry=255;
  3. walks into the level (forward holds with an R1 tap after each) and stands in the open until the
     player dies, capped at --cap seconds from the first walk hold (`FAIL NO-DEATH` at the cap).

All timing is the probe's own: every pad-file write and every `[peek]` row the probe reads is
host-timestamped into <out>/timeline.json, so the offline analysis runs on one clock. The exe does
not stamp `[peek]` rows; their host arrival time lags the guest state by at most one sampler period
plus the 0.05 s poll (blind class: a row delivered late under load reads as later than it was).

ANALYSIS (Step 5). From the run log (+ timeline): the Goal 2 death table (spec §5: `+0x1044` takes a
value strictly inside (0, 1) and then `<= 0`; `+0xF7A` leaves 1 within 2 s; word 0 still 0x6691a0 at
the death row), the yaw table (sweep and deg/s per level from the actor heading field; dead zone;
strictly increasing above it), the pitch sign (camera-minus-actor elevation), and the heading-field
validation (facing at rest vs forward-hold displacement direction, p90 over the holds).

THE HEADING FIELD (decomp, `game/analysis/socom2_game.elf.decomp.c`). `FUN_00551ec0` copies the
mover's three stick axes into actor+0x23c/+0x240/+0x244 and multiplies them by the movement scale
actor+0x1368 (pitch is not among them). `FUN_00550ef0` then sets the actor's angular velocity
`actor+0x48 = DAT_0044c290 * actor+0x23c` (DAT_0044c290 = 2.0 in every image, so full stick is
2 rad/s), while `FUN_0057a330` turns +0x244/+0x240 into the linear velocity at +0x2c/+0x34 --
so +0x23c is the TURN axis. The integrated orientation is the actor's rigid transform inside the
first 64 words: a unit quaternion (x, y, z, w) at +0x70..+0x7c and a 4x4 matrix at +0x80..+0xbc
whose last row is the position (+0xb0/+0xb4/+0xb8, the same x/y/z as +0x1c/+0x20/+0x24). For a
yaw-only rotation by theta about +y: m[+0x80] = cos, m[+0x88] = sin, m[+0xa0] = -sin, m[+0xa8] = cos.
The player walks along -row2, i.e. ground direction (-m[+0xa0], -m[+0xa8]) in (x, z). Offline on
Sprint 4's kill1-3 logs this matched the forward-hold displacement to p90 1.43 deg (n = 11 straight
holds with no rx in the 3 s before); this run re-measures it live, from rest, at chosen headings.
"""
import argparse
import bisect
import json
import math
import os
import shutil
import statistics
import struct
import subprocess
import sys
import threading
import time
from collections import namedtuple

from tools_py.parity import verdict_core as vc
from tools_py.parity.screen_bands import band_fraction

# ---------------------------------------------------------------------------------------------
# instruments
# ---------------------------------------------------------------------------------------------
# The r0001 column of guest_addresses.PROBE_ADDRESSES, read from it rather than repeated (Task 19
# review F6): this module is the ladder's instrument and the ladder runs on the r0001 build.
ACTOR_STATIC = vc.ga.address("player_actor", "r0001")     # 0x408c58
ACTOR_VTABLE = vc.ACTOR_VTABLE
CAMERA_ADDR = vc.CAMERA_RECORD_ADDR
HEALTH_OFFSET = 0x1044                 # float, 1.0 full, <= 0 dead (research/19 F1)
ALIVE_OFFSET = 0xF7A                   # byte, 1 = alive (research/19 F1); byte 2 of the word at +0xF78
DEATH_TIME_OFFSET = 0xFB4              # float, believed time-of-death (research/19 F1 "nearby", inference)
MOVE_SCALE_OFFSET = vc.ga.offset("move_scale", "r0001")   # 0x1368; FUN_00553dc0, multiplies +0x23c/+0x240/+0x244
# The other actor field offsets below stay r0001 literals: only the ladder reads them, the ladder runs
# on r0001, and no r0004 value for any of them has been measured -- a column filled by assumption is
# the defect guest_addresses exists to stop. They join PROBE_OFFSETS when somebody measures them, the
# way move_scale was measured (Task 19, the move lane).
ANGVEL_OFFSET = 0x48                   # actor angular velocity (rad/s): FUN_00550ef0 = 2.0 * turn axis
TURN_AXIS_OFFSET = 0x23C               # FUN_00551ec0: scaled turn axis
QUAT_OFFSET = 0x70                     # x, y, z, w
MATRIX_OFFSET = 0x80                   # 4x4, rows at +0x80/+0x90/+0xa0/+0xb0

# The plan's Step 2 peek, widened for the heading search. Every item <= 64 words (the exe caps an item
# at 64 silently -- KNOWN.md). +0x200:64 covers the stick axes at +0x23c..+0x244; +0x100 and +0x300
# are the brief's wider actor windows.
# The two guest addresses and the MoveScale offset come from guest_addresses' r0001 column, not from
# literals in these strings (Task 19 re-review N4): a literal 0x1368 four lines under a derived
# MOVE_SCALE_OFFSET is the drift F6 removed, written back in as text. The rest of the displacements are
# this module's own ladder fields (HEALTH_OFFSET and friends below), which stay r0001 -- see the note there.
PEEK_SPEC = ",".join([
    "%#x:3" % CAMERA_ADDR,
    "*%#x:64" % ACTOR_STATIC,
    "*%#x+0xF78:1" % ACTOR_STATIC,
    "*%#x+%#x:1" % (ACTOR_STATIC, HEALTH_OFFSET),
    "*%#x+0xc0*:32" % ACTOR_STATIC,
    "%#x:4" % ACTOR_STATIC,
    "*%#x+0x100:64" % ACTOR_STATIC,
    "*%#x+0x200:64" % ACTOR_STATIC,
    "*%#x+0x300:64" % ACTOR_STATIC,
    "*%#x+%#x:1" % (ACTOR_STATIC, DEATH_TIME_OFFSET),
    "*%#x+%#x:1" % (ACTOR_STATIC, MOVE_SCALE_OFFSET),
])

SAMPLER_PERIOD_S = 0.25
DEAD_AFTER_ALIVE_MAX_S = 2.0           # spec §5 Goal 2: +0xF7A leaves 1 within 2 s of the death row
YAW_LEVELS = (16, 32, 48, 64, 96, 127)
PAD_NEUTRAL = 0x80
FORWARD_LY = 0x00
BACK_LY = 0xFF
REST_S = 2.5                           # neutral before and after every calibration hold
YAW_HOLD_S = 1.0
PITCH_HOLD_S = 1.0
FWD_HOLD_S = 1.5
SETTLE_S = 1.5                         # after release: the heading is read this long after the hold
DEAD_ZONE_SWEEP_DEG = 1.0              # a hold that turns less than this is inside the dead zone
FWD_MIN_NET_UNITS = 10.0               # a forward hold that moved less carries no bearing
FWD_MIN_STRAIGHTNESS = 0.8             # net / path: below this the walk was deflected (a wall). 4 Hz rows
                                       # through the walk's start and stop read 0.83-0.89 on straight
                                       # 30-unit holds (runs 2-4), so 0.9 excluded every short hold
HEADING_BAR_P90_DEG = 5.0              # the at-rest facing bar Step 1 used, kept for the heading field

Hold = namedtuple("Hold", "kind value start release")      # kind: rx | ry | fwd | other

# Screen state, measured on the 640x448 frame (Task 2 runs 1-2, 2026-09-13). drive.py's HUD `untilref`
# (thresh 40 on the thumbnail's bottom-right) MATCHES THE LETTERBOXED INTRO CINEMATIC -- it did in the
# mission gate's own runs too -- so "HUD reached" is not taken from it. Gameplay: the letterbox bands are
# lit (> 50 % of pixels above 12: 0.71-1.0 on HUD frames, 0.0-0.04 through the cinematic). A HELP pop-up
# ("PRESS X TO CONTINUE") holds the game -- run 2 lost its stand to one -- and is recognised by its prompt
# line; squad-plate colour, text brightness and the window frame were tried first and each misfired
# (plates turn red when a squad member is down; sky and dust read as text; the frame's edge contrast
# depends on what is behind it).
BAND_MIN = 0.5
HUD_REF = os.path.join("scripts", "parity", "ref_hud_ours.png")
# The "PRESS (X) TO CONTINUE" template source: a frame that carries the HELP pop-up at PROMPT_REF_Y (the 2026-09-11
# HUD reference did; the lit-look reference of 2026-09-16 does not, and cutting the template out of it made every
# gameplay frame read as a pop-up -- s6_lum7).
PROMPT_REF = os.path.join("scripts", "parity", "ref_popup_prompt_ours.png")
PROMPT_REF_Y, PROMPT_H, PROMPT_X, PROMPT_LEVEL = 227, 18, (250, 420), 110
PROMPT_Y_RANGE = (140, 420)          # run 4: an eight-line pop-up put the prompt at y=340
PROMPT_MAX_DIST = 0.06               # pop-ups measured 0.000-0.006; cinematic and mission-gate frames >= 0.218
BTN_CROSS = 1 << 14
BTN_R1 = 1 << 11


def f32(w):
    return struct.unpack("<f", struct.pack("<I", w & 0xFFFFFFFF))[0]


def wrap(deg):
    return (deg + 180.0) % 360.0 - 180.0


def percentile(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    f = math.floor(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


# ---------------------------------------------------------------------------------------------
# row reading (pure)
# ---------------------------------------------------------------------------------------------
def parse_peek_line(line):
    """[(addr, [words])] from one `[peek]` line."""
    return [(int(a, 16), [int(w, 16) for w in vc._WORD.findall(ws)]) for a, ws in vc._ITEM.findall(line)]


def read_log(lines):
    """-> (peek_rows [(index, items)], pad_log [(frac_index, (buttons, rx, ry, lx, ly))]).
    A pad state line sits between two peek rows and takes index - 0.5; torn lines are skipped
    (the probe's own timeline carries the exact pad writes)."""
    rows, pads, i = [], [], 0
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line.startswith("[peek]"):
            rows.append((i, parse_peek_line(line)))
            i += 1
        elif line.startswith(vc._PAD_HEAD):
            m = vc._PAD_FULL.search(line)
            if m:
                pads.append((i - 0.5, tuple(int(g, 16) for g in m.groups())))
    return rows, pads


def item_at(items, addr):
    return next((w for a, w in items if a == addr), None)


def word_at(items, addr):
    """The word at guest address `addr` from whichever item covers it, else None."""
    for a, w in items:
        if a <= addr < a + 4 * len(w) and (addr - a) % 4 == 0:
            return w[(addr - a) // 4]
    return None


def byte_at(items, addr):
    base = addr & ~3
    w = word_at(items, base)
    return None if w is None else (w >> (8 * (addr - base))) & 0xFF


def actor_addr(items, static=None, vtable=None):
    """The actor base: the static 0x408c58's word 0 (robust when the block's own word 0 changes at death),
    else the item whose word 0 is the vtable.

    `static`/`vtable` default to the r0001 pair this module has always used. guest_probe passes the pair
    for the revision it is reading, instead of keeping its own copy of this selection (Task 19 review
    F11): the rule is one rule, and only the two numbers it is applied to vary."""
    static = ACTOR_STATIC if static is None else static
    vtable = ACTOR_VTABLE if vtable is None else vtable
    s = item_at(items, static)
    if s and s[0]:
        return s[0]
    return next((a for a, w in items if w and w[0] == vtable), None)


class Row:
    """One peek row read against the actor it names."""
    __slots__ = ("t", "items", "actor", "word0", "pos", "cam", "health", "alive", "matrix", "quat",
                 "angvel", "turn_axis", "scale", "death_t")

    def __init__(self, t, items):
        self.t, self.items = t, items
        self.actor = actor_addr(items)
        a = self.actor
        self.word0 = word_at(items, a) if a else None
        blk = item_at(items, a) if a else None
        self.pos = None
        self.matrix = self.quat = None
        if blk and blk[0] == ACTOR_VTABLE and len(blk) >= 48:
            x, y, z = (f32(blk[k]) for k in vc.ACTOR_POS_WORDS)
            if x or y or z:
                self.pos = (x, y, z)
            self.quat = tuple(f32(blk[(QUAT_OFFSET >> 2) + k]) for k in range(4))
            self.matrix = tuple(f32(blk[(MATRIX_OFFSET >> 2) + k]) for k in range(16))
        cam = item_at(items, CAMERA_ADDR)
        self.cam = tuple(f32(v) for v in cam[:3]) if cam and len(cam) >= 3 and any(cam[:3]) else None

        def fl(off):
            w = word_at(items, a + off) if a else None
            return None if w is None else f32(w)

        self.health = fl(HEALTH_OFFSET)
        self.alive = byte_at(items, a + ALIVE_OFFSET) if a else None
        self.angvel = fl(ANGVEL_OFFSET)
        self.turn_axis = fl(TURN_AXIS_OFFSET)
        self.scale = fl(MOVE_SCALE_OFFSET)
        self.death_t = fl(DEATH_TIME_OFFSET)


def yaw_deg(row):
    """theta of the actor's yaw rotation about +y, from the matrix (m[+0x80] = cos, m[+0x88] = sin)."""
    if row is None or row.matrix is None:
        return None
    m = row.matrix
    if abs(m[5] - 1.0) > 0.05 or math.hypot(m[0], m[2]) < 0.5:     # not a yaw-only transform
        return None
    return math.degrees(math.atan2(m[2], m[0]))


def facing_deg(row):
    """Ground direction the actor walks along, in the (x, z) atan2(dz, dx) convention: -row2 of the
    matrix, i.e. (-m[+0xa0], -m[+0xa8])."""
    if row is None or row.matrix is None:
        return None
    m = row.matrix
    if math.hypot(m[8], m[10]) < 0.5:
        return None
    return math.degrees(math.atan2(-m[10], -m[8]))


# ---------------------------------------------------------------------------------------------
# holds (pure)
# ---------------------------------------------------------------------------------------------
def holds_from_pads(pads):
    """pads: [(t, buttons, rx, ry, lx, ly)] in time order (a state holds until the next one).
    -> [Hold]: a maximal run of one constant non-neutral stick state. rx alone -> rx; ry alone -> ry;
    ly <= 0x40 with lx/rx/ry neutral -> fwd; anything else non-neutral -> other."""
    out = []
    cur = None
    for t, _b, rx, ry, lx, ly in pads:
        key = None
        sticks = (rx, ry, lx, ly)
        if sticks != (PAD_NEUTRAL,) * 4:
            if rx != PAD_NEUTRAL and (ry, lx, ly) == (PAD_NEUTRAL,) * 3:
                key = ("rx", rx)
            elif ry != PAD_NEUTRAL and (rx, lx, ly) == (PAD_NEUTRAL,) * 3:
                key = ("ry", ry)
            elif ly <= vc.FORWARD_LY_MAX and (rx, ry, lx) == (PAD_NEUTRAL,) * 3:
                key = ("fwd", ly)
            else:
                key = ("other", sticks)
        if cur is not None and key != cur[0]:
            out.append(Hold(cur[0][0], cur[0][1], cur[1], t))
            cur = None
        if key is not None and cur is None:
            cur = (key, t)
    return out


def _at_or_before(rows, times, t, pred=lambda r: True):
    i = bisect.bisect_right(times, t) - 1
    while i >= 0:
        if pred(rows[i]):
            return rows[i]
        i -= 1
    return None


def _at_or_after(rows, times, t, pred=lambda r: True):
    i = bisect.bisect_left(times, t)
    while i < len(rows):
        if pred(rows[i]):
            return rows[i]
        i += 1
    return None


def _unwrapped_sweep(rows, times, t0, t1, fn):
    """Sum of wrapped successive differences of fn(row) over rows in [t0, t1] (handles > 180 deg)."""
    i0 = bisect.bisect_left(times, t0)
    i1 = bisect.bisect_right(times, t1)
    vals = [fn(r) for r in rows[max(0, i0 - 1):i1]]
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return None
    return sum(wrap(b - a) for a, b in zip(vals, vals[1:]))


# ---------------------------------------------------------------------------------------------
# Step 3: yaw, pitch, heading
# ---------------------------------------------------------------------------------------------
def yaw_table(rows, holds, settle=SETTLE_S):
    times = [r.t for r in rows]
    out = []
    for h in holds:
        if h.kind != "rx":
            continue
        dur = h.release - h.start
        sweep = _unwrapped_sweep(rows, times, h.start, h.release + settle, yaw_deg)
        cam_sweep = _unwrapped_sweep(rows, times, h.start, h.release + settle, _camera_bearing)
        in_hold = rows[bisect.bisect_left(times, h.start):bisect.bisect_right(times, h.release + 0.25)]
        omegas = [abs(r.angvel) for r in in_hold if r.angvel is not None and math.isfinite(r.angvel)]
        axes = [r.turn_axis for r in in_hold if r.turn_axis is not None and math.isfinite(r.turn_axis)]
        scales = [r.scale for r in in_hold if r.scale is not None]
        out.append({
            "rx": h.value, "delta": h.value - PAD_NEUTRAL, "level": abs(h.value - PAD_NEUTRAL),
            "start": h.start, "hold_s": dur, "sweep_deg": sweep,
            "rate_deg_s": (sweep / dur) if (sweep is not None and dur > 0) else None,
            "cam_sweep_deg": cam_sweep,
            "peak_angvel_deg_s": math.degrees(max(omegas)) if omegas else None,
            "peak_turn_axis": max(axes, key=abs) if axes else None,
            "min_scale": min(scales) if scales else None,
            "rows": len(in_hold),
        })
    return out


def yaw_verdict(table):
    """Per direction: the dead zone (largest level whose |sweep| < DEAD_ZONE_SWEEP_DEG) and whether |rate|
    is strictly increasing over the levels above it."""
    res = {}
    for sign, name in ((1, "positive"), (-1, "negative")):
        rows = sorted((r for r in table if (r["delta"] > 0) == (sign > 0) and r["sweep_deg"] is not None),
                      key=lambda r: r["level"])
        if not rows:
            res[name] = {"status": vc.NO_DATA}
            continue
        dead = [r["level"] for r in rows if abs(r["sweep_deg"]) < DEAD_ZONE_SWEEP_DEG]
        dead_zone = max(dead) if dead else 0
        above = [r for r in rows if r["level"] > dead_zone]
        rates = [abs(r["rate_deg_s"]) for r in above]
        mono = len(rates) >= 2 and all(b > a for a, b in zip(rates, rates[1:]))
        signs = {math.copysign(1, r["sweep_deg"]) for r in above if abs(r["sweep_deg"]) >= DEAD_ZONE_SWEEP_DEG}
        res[name] = {"dead_zone_level": dead_zone, "levels_above": [r["level"] for r in above],
                     "rates_deg_s": rates, "strictly_increasing": mono,
                     "sweep_sign": (signs.pop() if len(signs) == 1 else "mixed") if signs else None}
    return res


def _camera_bearing(row):
    if row.cam is None or row.pos is None:
        return None
    return math.degrees(math.atan2(row.pos[2] - row.cam[2], row.pos[0] - row.cam[0]))


def camera_elevation_deg(row):
    """Elevation of the camera above the actor, seen from the actor (KNOWN: ~44 deg at rest)."""
    if row is None or row.cam is None or row.pos is None:
        return None
    dx, dy, dz = (row.cam[k] - row.pos[k] for k in range(3))
    g = math.hypot(dx, dz)
    if g == 0 and dy == 0:
        return None
    return math.degrees(math.atan2(dy, g))


def pitch_table(rows, holds, settle=SETTLE_S):
    times = [r.t for r in rows]
    out = []
    for h in holds:
        if h.kind != "ry":
            continue
        has = lambda r: camera_elevation_deg(r) is not None
        before = _at_or_before(rows, times, h.start, has)
        after = _at_or_after(rows, times, h.release + settle, has)
        e0, e1 = camera_elevation_deg(before), camera_elevation_deg(after)
        cam_frozen = before is not None and after is not None and before.cam == after.cam
        dur = h.release - h.start
        d = (e1 - e0) if (e0 is not None and e1 is not None) else None
        out.append({"ry": h.value, "start": h.start, "hold_s": dur, "elev_before_deg": e0,
                    "elev_after_deg": e1, "delta_elev_deg": d,
                    "rate_deg_s": (d / dur) if (d is not None and dur > 0) else None,
                    "camera_frozen": cam_frozen})
    return out


def heading_validation(rows, holds, after=0.5):
    """Facing (matrix -row2) at the last row at or before each forward hold's start, against the
    start->release+after displacement direction."""
    times = [r.t for r in rows]
    out = []
    for h in holds:
        if h.kind != "fwd":
            continue
        has_pos = lambda r: r.pos is not None
        s = _at_or_before(rows, times, h.start, has_pos)
        e = _at_or_after(rows, times, h.release + after, has_pos)
        rec = {"start": h.start, "hold_s": h.release - h.start, "used": False}
        if s is None or e is None or s.actor != e.actor:
            rec["reason"] = "no rows / actor changed"
            out.append(rec)
            continue
        seg = [r for r in rows[bisect.bisect_left(times, h.start):bisect.bisect_right(times, e.t)] if r.pos]
        pts = [s.pos] + [r.pos for r in seg] + [e.pos]
        path = sum(math.dist((a[0], a[2]), (b[0], b[2])) for a, b in zip(pts, pts[1:]))
        dx, dz = e.pos[0] - s.pos[0], e.pos[2] - s.pos[2]
        net = math.hypot(dx, dz)
        est = facing_deg(s)
        rec.update({"net_units": net, "straightness": (net / path) if path else 0.0, "estimate_deg": est})
        if net < FWD_MIN_NET_UNITS:
            rec["reason"] = f"net {net:.1f} < {FWD_MIN_NET_UNITS}"
        elif rec["straightness"] < FWD_MIN_STRAIGHTNESS:
            rec["reason"] = f"straightness {rec['straightness']:.2f} < {FWD_MIN_STRAIGHTNESS} (deflected)"
        elif est is None:
            rec["reason"] = "no matrix at start"
        else:
            truth = math.degrees(math.atan2(dz, dx))
            rec.update({"truth_deg": truth, "error_deg": wrap(est - truth), "used": True})
        out.append(rec)
    used = [abs(r["error_deg"]) for r in out if r["used"]]
    summary = {"n_holds": len(out), "n_used": len(used),
               "median_abs_deg": statistics.median(used) if used else None,
               "p90_abs_deg": percentile(used, 0.9), "max_abs_deg": max(used) if used else None}
    summary["meets_bar"] = bool(used) and len(used) >= 6 and summary["p90_abs_deg"] <= HEADING_BAR_P90_DEG
    return out, summary


# ---------------------------------------------------------------------------------------------
# Step 5: the death table
# ---------------------------------------------------------------------------------------------
def death_table(rows):
    """Goal 2, from rows in time order. The death row is the first row whose health is <= 0 after an
    alive read (0 < h <= 1) on the SAME actor address."""
    res = {"rows": len(rows), "health_reads": 0, "alive_reads": 0}
    last_alive_row = {}
    intermediates = []
    death = None
    for r in rows:
        if r.health is not None:
            res["health_reads"] += 1
        if r.alive is not None:
            res["alive_reads"] += 1
        if r.actor is None or r.health is None or not math.isfinite(r.health):
            continue
        if 0.0 < r.health <= 1.0:
            last_alive_row[r.actor] = r
            if r.health < 1.0 and (not intermediates or intermediates[-1][1] != r.health):
                intermediates.append((r.t, r.health))
        elif r.health <= 0.0 and r.actor in last_alive_row and death is None:
            death = r
            break
    res["intermediates"] = intermediates
    res["first_health"] = next((r.health for r in rows if r.health is not None), None)
    if death is None:
        res["death"] = None
        return res
    times = [r.t for r in rows]
    di = rows.index(death)
    prior = last_alive_row[death.actor]
    alive_before = next((r for r in reversed(rows[:di + 1]) if r.alive == 1 and r.actor == death.actor), None)
    leave = next((r for r in rows[bisect.bisect_left(times, alive_before.t if alive_before else death.t):]
                  if r.actor == death.actor and r.alive is not None and r.alive != 1), None)
    after = rows[di:bisect.bisect_right(times, death.t + 10.0)]
    res["death"] = {
        "t": death.t, "health": death.health, "actor": death.actor, "word0": death.word0,
        "word0_is_vtable": death.word0 == ACTOR_VTABLE, "alive_at_death_row": death.alive,
        "last_alive_health": prior.health, "last_alive_t": prior.t,
        "intermediate_before_death": any(0.0 < v < 1.0 for _, v in intermediates),
        "alive_leaves_1_t": leave.t if leave else None,
        "alive_leaves_1_value": leave.alive if leave else None,
        "alive_leaves_1_dt_s": (leave.t - death.t) if leave else None,
        "death_time_field": death.death_t,
        "health_after_10s": sorted({round(r.health, 6) for r in after if r.health is not None}),
        "alive_after_10s": sorted({r.alive for r in after if r.alive is not None}),
    }
    d = res["death"]
    d["goal2_pass"] = bool(d["intermediate_before_death"] and d["word0_is_vtable"]
                           and d["alive_leaves_1_dt_s"] is not None
                           and abs(d["alive_leaves_1_dt_s"]) <= DEAD_AFTER_ALIVE_MAX_S)
    return res


def live_death_row(rows):
    """The live stand's death detector: the first row whose health is <= 0 after an alive read
    (0 < h <= 1) on the same actor address, else None. Only rows whose block head is still the actor
    vtable count: at run 3's mission failure the actor was destroyed (word 0 -> base vtable 0x4061c0,
    FUN_0029ed30) and +0x1044 read heap data, which must never be called a death."""
    alive_actor = None
    for r in rows:
        if r.health is None or r.actor is None or not math.isfinite(r.health) or r.word0 != ACTOR_VTABLE:
            continue
        if 0.0 < r.health <= 1.0:
            alive_actor = r.actor
        elif r.health <= 0.0 and alive_actor == r.actor:
            return r
    return None


# ---------------------------------------------------------------------------------------------
# heading search: which actor-relative words move with rx and are constant at rest
# ---------------------------------------------------------------------------------------------
def actor_words(row):
    """{label: word} for every word of every item that is actor-relative (actor+off) or in the mover
    (*(actor+0xc0)+off)."""
    out = {}
    a = row.actor
    if not a:
        return out
    blk = item_at(row.items, a)
    mover = blk[0x30] if blk and len(blk) > 0x30 else None
    for addr, words in row.items:
        if a <= addr < a + 0x2000:
            base = "actor"
            off0 = addr - a
        elif mover and mover <= addr < mover + 0x400:
            base = "mover"
            off0 = addr - mover
        else:
            continue
        for k, w in enumerate(words):
            out[f"{base}+{off0 + 4 * k:#05x}"] = w
    return out


def field_search(rows, holds, min_level=48, eps=1e-4):
    """For each word: in how many rx holds (level >= min_level) it changed between the row before the
    hold and the row SETTLE_S after release, in how many ry / fwd holds, and in how many rest gaps
    (>= 2 s of neutral between holds) it changed. Returns candidates sorted best-first."""
    times = [r.t for r in rows]

    def changed(t0, t1):
        a = _at_or_before(rows, times, t0)
        b = _at_or_after(rows, times, t1)
        if a is None or b is None:
            return None
        wa, wb = actor_words(a), actor_words(b)
        out = set()
        for k in wa.keys() & wb.keys():
            if wa[k] != wb[k] and abs(f32(wa[k]) - f32(wb[k])) > eps:
                out.add(k)
        return out

    counts = {}
    n = {"rx": 0, "ry": 0, "fwd": 0, "rest": 0}
    stick = [h for h in holds if h.kind in ("rx", "ry", "fwd", "other")]
    for h in stick:
        kind = h.kind
        if kind == "rx" and abs(h.value - PAD_NEUTRAL) < min_level:
            continue
        if kind == "other":
            continue
        c = changed(h.start, h.release + SETTLE_S)
        if c is None:
            continue
        n[kind] += 1
        for k in c:
            counts.setdefault(k, {"rx": 0, "ry": 0, "fwd": 0, "rest": 0})[kind] += 1
    for h0, h1 in zip(stick, stick[1:]):
        t0, t1 = h0.release + SETTLE_S, h1.start - 0.25
        if t1 - t0 < 1.0:
            continue
        c = changed(t0, t1)
        if c is None:
            continue
        n["rest"] += 1
        for k in c:
            counts.setdefault(k, {"rx": 0, "ry": 0, "fwd": 0, "rest": 0})["rest"] += 1
    cands = []
    for k, c in counts.items():
        if n["rx"] and c["rx"] >= 0.8 * n["rx"] and c["rest"] == 0:
            cands.append((k, c))
    cands.sort(key=lambda kc: (-kc[1]["rx"], kc[1]["fwd"], kc[1]["ry"], kc[0]))
    return {"windows": n, "candidates": [{"field": k, **c} for k, c in cands]}


# ---------------------------------------------------------------------------------------------
# analysis driver (reads files)
# ---------------------------------------------------------------------------------------------
def build_rows(log_path, timeline=None):
    with open(log_path, errors="replace") as fh:
        peek, pads_log = read_log(fh)
    peek_t = (timeline or {}).get("peek_t") or []
    use_host = len(peek_t) >= len(peek) * 0.95 and peek_t

    def clock(idx):
        if use_host:
            i = int(math.floor(idx))
            if i < 0:
                return peek_t[0] - SAMPLER_PERIOD_S * (-idx)
            if i >= len(peek_t) - 1:
                return peek_t[-1] + SAMPLER_PERIOD_S * (idx - (len(peek_t) - 1))
            return peek_t[i] + (peek_t[i + 1] - peek_t[i]) * (idx - i)
        return idx * SAMPLER_PERIOD_S

    rows = [Row(clock(i), items) for i, items in peek]
    if timeline and timeline.get("pad_writes"):
        pads = [(p["t"], 0, p["rx"], p["ry"], p["lx"], p["ly"]) for p in timeline["pad_writes"]]
    else:
        pads = [(clock(i), b, rx, ry, lx, ly) for i, (b, rx, ry, lx, ly) in pads_log]
    return rows, pads, {"peek_rows": len(peek), "pad_log_lines": len(pads_log),
                        "clock": "host timeline" if use_host else f"index x {SAMPLER_PERIOD_S}s"}


def analyze(log_path, timeline=None):
    rows, pads, meta = build_rows(log_path, timeline)
    holds = holds_from_pads(pads)
    yt = yaw_table(rows, holds)
    hv, hs = heading_validation(rows, holds)
    return {
        "meta": meta,
        "holds": {k: sum(1 for h in holds if h.kind == k) for k in ("rx", "ry", "fwd", "other")},
        "death": death_table(rows),
        "yaw": yt, "yaw_verdict": yaw_verdict(yt),
        "pitch": pitch_table(rows, holds),
        "heading": hv, "heading_summary": hs,
        "field_search": field_search(rows, holds),
    }


def format_report(res):
    L = []
    m = res["meta"]
    L.append(f"rows={m['peek_rows']} pad_lines={m['pad_log_lines']} clock={m['clock']} holds={res['holds']}")
    d = res["death"]
    L.append(f"DEATH TABLE health_reads={d['health_reads']} alive_reads={d['alive_reads']} "
             f"first_health={d['first_health']} intermediates={[(round(t, 2), round(v, 4)) for t, v in d['intermediates']]}")
    if d["death"]:
        x = d["death"]
        L.append("  death row: " + " ".join(f"{k}={(hex(v) if k in ('actor', 'word0') and isinstance(v, int) else v)}"
                                           for k, v in x.items()))
    else:
        L.append("  no death row (health never went <= 0 after an alive read on one actor)")
    L.append("YAW (deg from the actor matrix; rate = sweep / hold)")
    L.append("  rx   lvl  hold_s  sweep   deg/s   cam_sweep  peak_omega  turn_axis  scale")
    for r in sorted(res["yaw"], key=lambda r: (r["delta"] < 0, r["level"])):
        fmt = lambda v, s="{:8.2f}": (s.format(v) if isinstance(v, (int, float)) else f"{str(v):>8}")
        L.append(f"  {r['rx']:3d} {r['delta']:+4d} {r['hold_s']:6.2f} {fmt(r['sweep_deg'])} {fmt(r['rate_deg_s'])} "
                 f"{fmt(r['cam_sweep_deg'])} {fmt(r['peak_angvel_deg_s'])} {fmt(r['peak_turn_axis'], '{:8.3f}')} "
                 f"{fmt(r['min_scale'], '{:6.3f}')}")
    L.append(f"  verdict: {json.dumps(res['yaw_verdict'])}")
    L.append("PITCH (camera elevation above the actor)")
    for p in res["pitch"]:
        L.append("  " + " ".join(f"{k}={(round(v, 3) if isinstance(v, float) else v)}" for k, v in p.items()))
    L.append("HEADING (matrix -row2 at the start of each forward hold vs displacement)")
    for h in res["heading"]:
        L.append("  " + " ".join(f"{k}={(round(v, 2) if isinstance(v, float) else v)}" for k, v in h.items()))
    L.append(f"  summary: {res['heading_summary']}")
    fs = res["field_search"]
    L.append(f"FIELD SEARCH windows={fs['windows']} candidates (changed in >= 80% of rx holds, never at rest):")
    for c in fs["candidates"][:40]:
        L.append(f"  {c['field']} rx={c['rx']} ry={c['ry']} fwd={c['fwd']} rest={c['rest']}")
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------
# Step 6: replay a run log through the online harness's own KillWatch
# ---------------------------------------------------------------------------------------------
def replay_watch(log_path, health_offset=HEALTH_OFFSET, alive_offset=ALIVE_OFFSET):
    """Feed every line through online_match_ours.RunLogTail._line and poll KillWatch after each row, as
    the live harness would, with a clock that is the peek row index x the sampler period."""
    import tempfile
    from tools_py.parity import online_match_ours as M

    state = {"i": 0}
    clock = lambda: state["i"] * SAMPLER_PERIOD_S
    tail = M.RunLogTail(log_path, clock=clock)
    tail.watch_offset = health_offset
    if hasattr(tail, "alive_offset") and alive_offset is not None:
        tail.alive_offset = alive_offset
    kw = {"health": health_offset, "clock": clock}
    try:
        import inspect
        if "alive" in inspect.signature(M.KillWatch.__init__).parameters:
            kw["alive"] = alive_offset
    except (TypeError, ValueError):
        pass
    with tempfile.TemporaryDirectory() as tmp:
        watch = M.KillWatch({"SP": tail}, {}, server_log=os.path.join(tmp, "none.log"), **kw)
        with open(log_path, errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\r\n")
                tail._line(line)                                   # noqa: SLF001 - the real parser
                if line.startswith("[peek]"):
                    watch._check_health()                          # noqa: SLF001 - the real check
                    if hasattr(watch, "_check_alive"):
                        watch._check_alive()                       # noqa: SLF001
                    state["i"] += 1
    return {"rows": state["i"], "reads": tail.watch_reads, "misses": tail.watch_misses,
            "changes": len(tail.watch_hist), "events": watch.events, "fired": watch.fired}


# ---------------------------------------------------------------------------------------------
# live
# ---------------------------------------------------------------------------------------------
_PROMPT_TEMPLATE = {}


def prompt_template():
    """The binarised "PRESS (X) TO CONTINUE" line out of the committed scripts/parity/ref_popup_prompt_ours.png (PROMPT_REF)."""
    if "t" not in _PROMPT_TEMPLATE:
        import numpy as np
        from PIL import Image
        with Image.open(PROMPT_REF) as im:
            g = np.asarray(im.convert("L")).astype(np.float32)
        y, (x0, x1) = PROMPT_REF_Y, PROMPT_X
        _PROMPT_TEMPLATE["t"] = g[y:y + PROMPT_H, x0:x1] > PROMPT_LEVEL
    return _PROMPT_TEMPLATE["t"]


def screen_state(rgb):
    """rgb: HxWx3 array of the 640x448 frame -> (gameplay, popup, band_fraction, prompt_distance).

    gameplay: both letterbox bands (rows 2-95 and 340-446) have > BAND_MIN of pixels above 12 -- the intro
    cinematic keeps them black. popup: the binarised "PRESS (X) TO CONTINUE" line (the prompt is centred,
    so only its row varies with the text above it) matches the reference's within PROMPT_MAX_DIST at some
    row in PROMPT_Y_RANGE."""
    import numpy as np
    a = np.asarray(rgb).astype(np.float32)
    g = a.mean(axis=2)
    band = band_fraction(g, 12)          # screen_bands.py: the shared letterbox-band test (rows scale with height)
    tpl = prompt_template()
    x0, x1 = PROMPT_X
    dist = min(float(np.abs((g[y:y + PROMPT_H, x0:x1] > PROMPT_LEVEL) ^ tpl).mean())
               for y in range(PROMPT_Y_RANGE[0], PROMPT_Y_RANGE[1] - PROMPT_H))
    gameplay = band > BAND_MIN
    return gameplay, gameplay and dist < PROMPT_MAX_DIST, band, dist


def write_pad(path, rx=PAD_NEUTRAL, ry=PAD_NEUTRAL, lx=PAD_NEUTRAL, ly=PAD_NEUTRAL, buttons=0):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(f"b={buttons:04x} rx={rx} ry={ry} lx={lx} ly={ly}\n")
    for _ in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:          # the exe has the file open for its 60 Hz read
            time.sleep(0.005)
    os.replace(tmp, path)


class LiveTail(threading.Thread):
    """Follow the run log; host-timestamp every [peek] row and keep them as Rows."""

    def __init__(self, path):
        super().__init__(daemon=True)
        self.path = path
        self.peek_t = []
        self.rows = []
        self.lock = threading.Lock()
        self.stop_ev = threading.Event()

    def run(self):
        f, buf = None, ""
        while not self.stop_ev.is_set():
            if f is None:
                try:
                    f = open(self.path, "r", errors="replace")
                except OSError:
                    time.sleep(0.2)
                    continue
            chunk = f.read(65536)
            if not chunk:
                time.sleep(0.05)
                continue
            buf += chunk
            while True:
                nl = buf.find("\n")
                if nl < 0:
                    break
                line, buf = buf[:nl], buf[nl + 1:]
                if line.startswith("[peek]"):
                    t = time.time()
                    row = Row(t, parse_peek_line(line))
                    with self.lock:
                        self.peek_t.append(t)
                        self.rows.append(row)
        if f:
            f.close()

    def snapshot(self):
        with self.lock:
            return list(self.rows)


class Probe:
    def __init__(self, a):
        self.a = a
        self.out = os.path.abspath(a.out)
        os.makedirs(self.out, exist_ok=True)
        self.pad_file = os.path.join(self.out, "pad.txt")
        self.run_log = os.path.abspath(os.path.join("logs", f"run_sp_{time.strftime('%Y%m%d_%H%M%S')}.log"))
        self.latest = os.path.join(self.out, "latest_frame.png")
        self.pad_writes = []
        self.events = []
        self.t0 = time.time()
        self.proc = None
        self.tail = None
        self.death_seen = None

    def log(self, msg):
        line = f"{time.time() - self.t0:7.1f}s {msg}"
        print(line, flush=True)

    def event(self, kind, **kw):
        self.events.append({"t": time.time(), "kind": kind, **kw})

    def pad(self, rx=PAD_NEUTRAL, ry=PAD_NEUTRAL, lx=PAD_NEUTRAL, ly=PAD_NEUTRAL, buttons=0):
        write_pad(self.pad_file, rx, ry, lx, ly, buttons)
        self.pad_writes.append({"t": time.time(), "rx": rx, "ry": ry, "lx": lx, "ly": ly, "b": buttons})

    def sleep(self, s):
        """Sleep, but keep an eye on the game (drive.py alive) and on a death."""
        end = time.time() + s
        while time.time() < end:
            if self.proc.poll() is not None:
                raise RuntimeError(f"drive.py exited early (code {self.proc.returncode})")
            self.check_death()
            time.sleep(min(0.05, max(0.0, end - time.time())))

    def hold(self, label, seconds, **axes):
        self.clear_popups()
        self.event("hold", label=label, seconds=seconds, **axes)
        self.pad(**axes)
        self.sleep(seconds)
        self.pad()

    def shot(self, label):
        try:
            shutil.copyfile(self.latest, os.path.join(self.out, f"{label}.png"))
        except OSError as e:
            self.log(f"screenshot {label} failed: {e}")

    def screen(self, max_age=3.0):
        """screen_state(...) = (gameplay, popup, band_fraction, prompt_distance) of the newest frame file,
        or None when it is missing or stale."""
        try:
            if time.time() - os.path.getmtime(self.latest) > max_age:
                return None
            from PIL import Image
            with Image.open(self.latest) as im:
                return screen_state(im.convert("RGB"))
        except (OSError, ValueError):
            return None

    def press_cross(self, label):
        self.event("press", label=label, button="CROSS")
        self.pad(buttons=BTN_CROSS)
        self.sleep(0.12)
        self.pad()

    def clear_popups(self, max_presses=6):
        """Dismiss HELP pop-ups (they hold the game) before a calibration hold; logged as events."""
        for _ in range(max_presses):
            st = self.screen()
            if st is None or not st[1]:
                return
            self.log(f"HELP pop-up on screen (letterbox band {st[2]:.3f}, prompt distance {st[3]:.3f}) -- CROSS")
            self.shot(f"popup_{int(time.time() - self.t0)}s")
            self.press_cross("popup")
            self.sleep(1.5)

    def check_death(self):
        if self.death_seen is not None or self.tail is None:
            return
        r = live_death_row(self.tail.snapshot()[-400:])
        if r is None:
            return
        self.death_seen = r
        self.event("death", health=r.health, actor=r.actor, alive=r.alive)
        self.log(f"DEATH ROW health={r.health} alive={r.alive} actor={r.actor:#x} word0={r.word0:#x}")
        self.shot("death")

    # -- phases ----------------------------------------------------------------------------------
    def launch(self):
        self.pad()
        env = dict(os.environ)
        env.update({"PS2X_SOCOM2_INPUT_FILE": self.pad_file, "PS2X_PEEK": PEEK_SPEC, "PS2X_PC_SAMPLER": "0.25",
                    "PS2X_SOCOM2_INPUT_TRACE": "1", "PS2X_RUN_LOG": self.run_log,
                    "PS2X_HOST_SCREENSHOT_LATEST": self.latest})
        drive_out = os.path.join(self.out, "drive")
        self.drive_log = os.path.join(self.out, "drive.log")
        self.log(f"launch drive.py -> {drive_out}; run log {self.run_log}")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "tools_py.parity.drive", "--target", "ours", "--script", self.a.script,
             "--out", drive_out, "--seconds", str(self.a.seconds), "--tail", "1"],
            env=env, stdout=open(self.drive_log, "w"), stderr=subprocess.STDOUT)
        self.tail = LiveTail(self.run_log)
        self.tail.start()

    def wait_hud(self):
        deadline = time.time() + self.a.hud_timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                return f"drive.py exited (code {self.proc.returncode}) before the HUD"
            try:
                text = open(self.drive_log, errors="replace").read()
            except OSError:
                text = ""
            for line in text.splitlines():
                if line.startswith("untilref(scripts/parity/ref_hud_ours.png)"):
                    self.log(line)
                    if "matched=True" in line:
                        return None
                    return "the HUD reference never matched"
            time.sleep(1.0)
        return f"no HUD line within {self.a.hud_timeout}s"

    def wait_actor(self, timeout=420.0):
        """Into controllable gameplay. Needs non-zero ACTOR rows (vtable, via the static), the HUD squad
        panel on screen, and a 1.0 s forward hold that moves the actor >= 3 units. Until then: CROSS
        through the cinematic (only while the squad panel is absent) and through HELP pop-ups."""
        deadline = time.time() + timeout
        attempts = 0
        last_cross = 0.0
        while time.time() < deadline:
            rows = [r for r in self.tail.snapshot() if r.pos is not None and r.word0 == ACTOR_VTABLE]
            st = self.screen()
            if st is not None and st[1]:
                self.clear_popups()
                continue
            if st is None or not st[0]:
                if time.time() - last_cross > 4.0:
                    self.log(f"not in gameplay yet (gameplay/popup/band/prompt-distance {st}) -- CROSS")
                    self.press_cross("skip-cinematic")
                    last_cross = time.time()
                self.sleep(1.0)
                continue
            if len(rows) < 8:
                self.sleep(0.5)
                continue
            self.sleep(2.0)
            if (self.screen() or (False, False))[1]:
                continue
            p0 = [r for r in self.tail.snapshot() if r.pos is not None][-1].pos
            attempts += 1
            self.hold(f"liveness-fwd{attempts}", 1.0, ly=FORWARD_LY)
            self.sleep(1.0)
            p1 = [r for r in self.tail.snapshot() if r.pos is not None][-1].pos
            moved = math.hypot(p1[0] - p0[0], p1[2] - p0[2])
            r = rows[-1]
            self.log(f"liveness forward hold {attempts} moved {moved:.2f} units (actor rows={len(rows)} "
                     f"health={r.health} alive={r.alive} scale={r.scale})")
            if moved >= 3.0:
                self.shot("gameplay")
                return None
            self.sleep(2.0)
        return f"no controllable gameplay within {timeout:.0f}s ({attempts} liveness holds)"

    def calibrate(self):
        self.sleep(REST_S)
        if self.a.no_yaw:
            # Run 3 (2026-09-13): in single player a partial rx hold (|delta| >= 64) put 250-2460 u/s into
            # the actor's velocity words and moved it up to 380 units in one row -- out of the mission area,
            # with fall damage. Without rx the heading is validated at the spawn heading only.
            self.log("CALIBRATION heading only (--no-yaw): forward/back pairs at the spawn heading")
            for k in range(6):
                self.hold(f"fwd{k}", FWD_HOLD_S, ly=FORWARD_LY)
                self.sleep(REST_S)
                self.hold(f"back{k}", FWD_HOLD_S, ly=BACK_LY)
                self.sleep(REST_S)
            self.log("CALIBRATION pitch")
            self.hold("pitch-ry0", PITCH_HOLD_S, ry=0)
            self.sleep(REST_S)
            self.hold("pitch-ry255", PITCH_HOLD_S, ry=255)
            self.sleep(REST_S)
            self.shot("after_calibration")
            return
        self.log("CALIBRATION yaw + heading")
        for level in YAW_LEVELS:
            self.hold(f"yaw+{level}", YAW_HOLD_S, rx=PAD_NEUTRAL + min(level, 127))
            self.sleep(REST_S)
            self.hold(f"fwd-after-yaw+{level}", FWD_HOLD_S, ly=FORWARD_LY)
            self.sleep(REST_S)
            # walk back along the same line: run 2 wandered out of the mission area during calibration
            self.hold(f"back-after-yaw+{level}", FWD_HOLD_S, ly=BACK_LY)
            self.sleep(REST_S)
            self.hold(f"yaw-{level}", YAW_HOLD_S, rx=PAD_NEUTRAL - level)
            self.sleep(REST_S)
        for k in range(2):
            self.hold(f"turn{k}", YAW_HOLD_S, rx=255)
            self.sleep(REST_S)
            self.hold(f"fwd-extra{k}", FWD_HOLD_S, ly=FORWARD_LY)
            self.sleep(REST_S)
            self.hold(f"back-extra{k}", FWD_HOLD_S, ly=BACK_LY)
            self.sleep(REST_S)
        self.log("CALIBRATION pitch")
        self.hold("pitch-ry0", PITCH_HOLD_S, ry=0)
        self.sleep(REST_S)
        self.hold("pitch-ry255", PITCH_HOLD_S, ry=255)
        self.sleep(REST_S)
        self.shot("after_calibration")

    def walk_and_stand(self):
        self.log(f"WALK {self.a.walk_holds} x {self.a.walk_s}s, then stand; cap {self.a.cap}s")
        t_start = time.time()
        for k in range(self.a.walk_holds):
            if self.death_seen:
                break
            self.hold(f"walk{k}", self.a.walk_s, ly=FORWARD_LY)
            self.sleep(0.5)
            self.hold(f"fire{k}", 0.3, buttons=BTN_R1)
            self.sleep(1.5)
        self.shot("stand_start")
        k = 0
        last_fire = time.time()
        gone_since = None
        while self.death_seen is None and time.time() - t_start < self.a.cap:
            self.clear_popups()                  # a HELP pop-up holds the game: nobody can shoot the player
            self.sleep(1.0)
            if self.a.fire_every and time.time() - last_fire >= self.a.fire_every:
                self.hold("stand-fire", 0.3, buttons=BTN_R1)
                last_fire = time.time()
            rows = self.tail.snapshot()
            if rows and rows[-1].word0 != ACTOR_VTABLE:
                gone_since = gone_since or time.time()
                if time.time() - gone_since > 8.0:
                    r = rows[-1]
                    self.log(f"MISSION-END: the actor block's word 0 has read {r.word0} for 8 s "
                             f"(health {r.health}) -- not a death row; stopping the stand")
                    self.shot("mission_end")
                    break
            else:
                gone_since = None
            if int(time.time() - t_start) // 10 > k:
                k = int(time.time() - t_start) // 10
                self.shot(f"stand_{k * 10:03d}s")
                rows = self.tail.snapshot()
                if rows:
                    r = rows[-1]
                    self.log(f"standing t={time.time() - t_start:.0f}s health={r.health} alive={r.alive} pos={r.pos}")
        if self.death_seen is None:
            return False
        for at, gap in ((1, 1.0), (3, 2.0), (6, 3.0), (10, 4.0)):
            self.sleep(gap)
            self.shot(f"death_plus{at}s")
        return True

    def stop(self):
        if self.tail:
            self.tail.stop_ev.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        subprocess.run(["cmd", "/c", "taskkill /F /IM socom2.exe"], capture_output=True)
        try:
            write_pad(self.pad_file)
        except OSError:
            pass

    def save(self):
        with open(os.path.join(self.out, "timeline.json"), "w") as fh:
            json.dump({"run_log": self.run_log, "peek_t": self.tail.peek_t if self.tail else [],
                       "pad_writes": self.pad_writes, "events": self.events}, fh)

    def run(self):
        result = "FAIL UNKNOWN"
        try:
            self.launch()
            err = self.wait_hud()
            if err:
                result = f"FAIL NO-HUD ({err})"
                return result
            err = self.wait_actor()
            if err:
                result = f"FAIL NO-ACTOR ({err})"
                return result
            self.calibrate()
            died = self.walk_and_stand()
            result = "DEATH" if died else f"FAIL NO-DEATH (no death row within {self.a.cap}s)"
            return result
        except RuntimeError as e:
            result = f"FAIL {e}"
            return result
        finally:
            self.stop()
            time.sleep(1.0)
            self.save()
            self.log(f"RESULT {result} run_log={self.run_log} rows={len(self.tail.peek_t) if self.tail else 0}")
            try:
                res = analyze(self.run_log, {"peek_t": self.tail.peek_t, "pad_writes": self.pad_writes})
                report = format_report(res)
                with open(os.path.join(self.out, "analysis.txt"), "w") as fh:
                    fh.write(report + "\n")
                with open(os.path.join(self.out, "analysis.json"), "w") as fh:
                    json.dump(res, fh, indent=1, default=str)
                print(report, flush=True)
            except Exception as e:                            # noqa: BLE001 - the run is already over
                self.log(f"analysis failed: {e!r}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default="logs/parity/s5_t2_death")
    ap.add_argument("--script", default="scripts/parity/gameplay_death.txt")
    ap.add_argument("--seconds", type=int, default=1500, help="run.sh cap for the game")
    ap.add_argument("--hud-timeout", type=float, default=700.0)
    ap.add_argument("--walk-holds", type=int, default=2)
    ap.add_argument("--walk-s", type=float, default=3.0)
    ap.add_argument("--cap", type=float, default=240.0, help="seconds from the first walk hold to FAIL NO-DEATH")
    ap.add_argument("--no-yaw", action="store_true", help="skip the rx calibration (see calibrate)")
    ap.add_argument("--fire-every", type=float, default=0.0, help="R1 tap every N s while standing (0 = never)")
    ap.add_argument("--analyze", metavar="RUN_LOG")
    ap.add_argument("--timeline", metavar="JSON")
    ap.add_argument("--replay", metavar="RUN_LOG")
    a = ap.parse_args(argv)
    if a.replay:
        r = replay_watch(a.replay)
        print(f"REPLAY rows={r['rows']} reads={r['reads']} misses={r['misses']} changes={r['changes']}")
        for e in r["events"]:
            print(f"  event {e['kind']} firing={e['firing']} t={e['t']:.2f} (row {e['t'] / SAMPLER_PERIOD_S:.0f}) "
                  f"{json.dumps(e['detail'], default=str)}")
        print(f"FIRED {json.dumps(r['fired'], default=str)}")
        return 0 if r["fired"] else 1
    if a.analyze:
        tl = json.load(open(a.timeline)) if a.timeline else None
        print(format_report(analyze(a.analyze, tl)))
        return 0
    if "socom2.exe" in subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower():
        raise SystemExit("socom2.exe is already running")
    probe = Probe(a)
    result = probe.run()
    return 0 if result == "DEATH" else 1


if __name__ == "__main__":
    sys.exit(main())
