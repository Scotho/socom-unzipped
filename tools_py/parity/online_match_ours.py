"""Two instances of OUR exe play a match on the local Horizon stack: A logs in and hosts a game
(Medley), B logs in, joins it and switches team, both press READY -> the match launches
(mirrors online_match.py, the PCSX2 two-client reference). Screens land in --out as A_*/B_*.

Instance B runs with its own window title, memory card dir (game/disc/mc0_b) and UDP port shift
(see online_login_ours.INSTANCES). Personas: A = --name-a (default socomc, saved on mc0),
B = --name-b (default socome; created on first use unless --existing-b).

Gameplay phases: --play / --probe / --sweep drive open-loop bursts. --calibrate and --walk-to-b
are CLOSED loop: each instance's run log is tailed live (RunLogTail), so the driver reads the
`[peek] @416054` position rows and the `MoveScale` f12 rows while the match is running and can
measure what an injected hold actually did.

Usage: python -m tools_py.parity.online_match_ours [--hold 120] [--out logs/parity/ours_match]
"""
import argparse
import json
import math
import os
import re
import struct
import subprocess
import threading
import time

import numpy as np

from . import online_login_ours as L

# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------
# `PS2X_PEEK=0x416054:3` + `PS2X_PC_SAMPLER=<s>` prints the local player's ORBITING CAMERA record
# (x, y, z) every sample; the camera sits CAMERA_ORBIT_RADIUS units behind the player along its
# facing (STATUS 2026-09-10 20:10), so the player is at camera + R * facing. The rows are the only
# trustworthy movement signal this harness has: screenshots go stale and are written whether or not
# the match ever launched (research/18 §3.5, §3.10).
POSITION_ADDR = 0x416054
# `PS2X_CALL_TRACE="0x553dc0:MoveScale"` logs FUN_00553dc0's f12 -- the multiplayer movement scale
# actor+0x1368. It is 1.0 while the network has been active within 5500 ms and decays to 0.0 at
# 6500 ms of idle (research/18 §3.12). A hold measured while it is not 1.0 measures the lag freeze,
# not the controls, so every calibration hold is discarded unless the scale held at 1.0 across it.
MOVE_SCALE_TRACE_NAME = "MoveScale"
MOVE_SCALE_LIVE = 1.0

# ---------------------------------------------------------------------------
# Stick keys (online_login_ours.PAD_AXIS). The game runs the Precision Shooter preset, so the
# right stick looks (and the body follows the look) and the left stick translates.
# ---------------------------------------------------------------------------
LOOK_RIGHT_KEY, LOOK_LEFT_KEY = "L", "J"        # right stick right / left  (rx)
LOOK_UP_KEY, LOOK_DOWN_KEY = "I", "K"           # right stick up / down     (ry) -- PITCH. Which of
                                                # the two raises the muzzle is NOT established, so
                                                # the engagement sweeps both ways rather than
                                                # assuming a sign. Pitch is the one look axis the
                                                # movement-scale bug never touched (research/18
                                                # §3.12: it is not among the three scaled axes)
LATERAL_RIGHT_KEY, LATERAL_LEFT_KEY = "D", "A"  # left stick right / left   (lx)
WALK_FORWARD_KEY, WALK_BACK_KEY = "W", "S"      # left stick up / down      (ly)

# ---------------------------------------------------------------------------
# MEASURED CONSTANTS -- docs/research/18-online-round-start.md §3.13 has the method, the three
# repeats and the spread. Measured on logs/parity/ours_task7_cal3 (map mp51, the default Medley
# first round, A's SEAL spawn); every hold below held the movement scale at 1.0.
#
# Angles are in the (x, z) ground plane with the sign of atan2(dz, dx). Both hold responses are
# AFFINE, not proportional: a hold delivers rate * (seconds - lead), because the record is the
# camera TRAILING the player and it takes that long to take up the slack. Measured from the three
# 2 s repeats against the one 4 s hold; the lead is what makes a short corrective hold land at all.
# ---------------------------------------------------------------------------
LOOK_DEG_PER_S = 104.9           # steady-state deg/s of a look hold. Least squares over the 19
                                 # clean turn holds of ours_task7_cal3 + ours_task7_wtb1 (0.71 s to
                                 # 4.0 s): |sweep| = 104.86*t - 46.45, RMS 18.1 deg. A proportional
                                 # fit is worse (80.4 deg/s, RMS 26.5). The RMS is why the loop
                                 # re-measures the sweep it actually got instead of trusting this.
TURN_HOLD_LEAD_S = 0.44          # dead time of a look hold before the facing moves (46.45/104.86)
LOOK_RIGHT_SIGN = 1.0            # MEASURED: LOOK_RIGHT_KEY sweeps POSITIVE (L +171/+155/+168 deg
                                 # over 2 s, LOOK_LEFT_KEY -173 over 2 s: symmetric)
# NOT a speed, and deliberately named so nobody can use it as one: the three 2 s forward repeats
# came out 8.01 / 27.55 / 29.14 units/s (ptp 21.1 on a mean of 21.6) because the record is the
# trailing camera and two of the three holds ran into something. Kept only so the failure is on the
# record next to the number that replaced it. No call site reads it. See research/18 §3.13.
WALK_2S_HOLD_OBSERVED_NOT_A_SPEED = 21.6
WALK_UNITS_PER_S_LONG = 40.0     # units/s of the 4 s forward hold, corroborated by 20 unobstructed
                                 # bursts in the proving runs at 33..46. THIS is the forward rate:
                                 # burst sizing and the progress test both use it
WALK_BACK_UNITS_PER_S = 25.3     # units/s of a 2 s backward hold (25.0..25.6 -- tight)
LATERAL_UNITS_PER_S = 42.5       # units/s of a 2 s strafe hold (39.6..45.6). MEASURED: the left
                                 # stick STRAFES on this preset, it does not turn -- the three A
                                 # holds all travelled at facing-90 deg with the facing unchanged
CAMERA_ORBIT_RADIUS = 24.9       # units from the 0x416054 record to the player. The three circle
                                 # fits with a zero residual (pure rotation) all give 24.91; fits
                                 # with translation mixed in bias it down to 22.2

# ---------------------------------------------------------------------------
# Calibration schedule
# ---------------------------------------------------------------------------
CAL_REPEATS = 3                  # the brief asks for three repeats and their spread
CAL_TURN_HOLD_S = 2.0
CAL_LONG_HOLD_S = 4.0            # one longer hold per key: linearity check
CAL_WALK_HOLD_S = 2.0
CAL_HEADING_PROBE_S = 1.5        # forward tap whose displacement direction IS the facing
CAL_RETURN_HOLD_S = 3.0          # walk back so the repeats start from roughly one place
HOLD_SETTLE_S = 1.5              # the record keeps moving briefly after release (research/18 §3.5)
HOLD_REST_S = 0.8
PEEK_LEAD_S = 0.25               # a peek row is written up to one sample after the state it reports
ROTATION_MAX_RADIUS = 250.0      # a fitted circle bigger than this is a straight line, not a turn
ROTATION_MAX_RESIDUAL = 6.0      # mean |r_i - r| of the fit, in units
MIN_ROTATION_POINTS = 4

# ---------------------------------------------------------------------------
# --walk-to-b
# ---------------------------------------------------------------------------
ARRIVE_UNITS = 120.0             # "within a set distance": ~5x the camera orbit radius, and under
                                 # 8% of the 1526-unit gap between the two spawns on this map
WALK_STEP_MIN_S = 0.8
WALK_STEP_MAX_S = 6.0            # an unobstructed 6 s burst covers ~230 units; a blocked one only
                                 # costs the difference, and ours_task7_wtb2 ran out of clock, not
                                 # of steps -- 25 steps at ~12 s each covered 55% of the gap
WALK_STEP_FRACTION = 0.8         # aim each burst at 80% of the remaining gap: undershooting costs
                                 # a step, overshooting makes the loop oscillate around B
WALK_SETTLE_S = 0.6              # the loop settles less than the calibration: it re-measures anyway
WALK_REST_S = 0.3                # ... and rests less between holds, for the same reason
TURN_SETTLE_S = 1.0
WALK_TO_B_MAX_STEPS = 40         # HARD cap: a mis-calibration cannot run the match forever
WALK_TO_B_MAX_SECONDS = 290.0    # HARD cap: a round is ~6 minutes and respawns at the end of it
TURN_DEADBAND_DEG = 12.0         # inside this the bearing error is not worth a turn hold
TURN_MAX_HOLD_S = 4.0            # a single turn hold never exceeds this
FACING_PROBE_S = 1.5
FACING_MIN_UNITS = 4.0           # below this a forward tap did not move: the heading is unusable
# MEASURED in ours_task8_kill3: instance B entered the approach while its player was still not
# controllable -- 161 in-game rows, the movement scale at 1.0, and the record moving EXACTLY 0.00
# units across a 1.5 s forward hold, a 1.3 s turn and another 1.5 s hold. Two probes in ten seconds
# was not enough patience and the whole side aborted, which cost the run: A walked alone and
# stopped 587 units short. The liveness rule counts non-zero rows, not DISTINCT ones, so it cannot
# catch this; the probe has to.
FACING_PROBE_TRIES = 6
FACING_PROBE_REST_S = 4.0
# A burst's heading is believed only when the burst actually went somewhere, in a straight line.
# ours_task7_wtb1 failed exactly here: bursts that slid along the spawn wall reported headings up to
# 86 deg off the direction the player was pointed, the loop adopted them, and every bearing after
# that was nonsense. A blocked burst now leaves the dead-reckoned facing alone.
WALK_PROGRESS_FRACTION = 0.25    # of the distance the measured rate predicts for that hold length
WALK_STRAIGHT_MIN = 0.70         # net displacement / path length along the sampled rows
DETOUR_DEG = 65.0                # on a block, aim this far off the bearing to get round whatever
DETOUR_STEPS = 2                 # ... and hold that offset for this many steps (wall following)
UNSTICK_LATERAL_UNITS = 40.0     # how far to sidestep out of whatever the burst walked into
UNSTICK_BACK_S = 0.6


# ---------------------------------------------------------------------------
# Task 8 (S3) -- two movers, a mined corridor, and the kill readout
# ---------------------------------------------------------------------------
# ONE player walking to the other cannot finish inside a round: ours_task7_wtb2 closed 757.8 units
# for 1960.7 walked (38.6 %) at ~12 s a step, so the 1382-unit gap needs ~450 s against a ~360 s
# round (KNOWN.md, research/18 §3.13). BOTH players moving halves each side's share to ~700 units
# -- and it also removes the starvation trap, because the movement scale is fed by RECEIVED bytes
# and a parked opponent sends nothing.
MP51_SEAL_SPAWN = (542.3, 1479.9)      # A's spawn, camera record (x, z)
MP51_TERROR_SPAWN = (1144.8, 77.5)     # B's spawn, camera record (x, z)

# MINED, NOT PLANNED. Every point below is a place instance A's camera record actually WAS during
# ours_task7_wtb2 (logs/run_A_20260912_211009.log, 1441 in-game rows), so the corridor is
# proven-walkable rather than a guess at the map. Kept when a row is >= 70 units from the last kept
# point AND closer to MP51_TERROR_SPAWN than any row before it, which makes the chain
# progress-monotone: 1167.5 units of path to close 851.4 units of gap (73 %), against the 38.6 %
# the straight-line-plus-detour policy managed over the same ground. The y of these rows falls
# 184.8 -> -4.5, i.e. the route is a descent, which is why a straight line out of the SEAL spawn
# does not work. Re-mine with the same rule if the map or the spawn ever changes.
MP51_SEAL_ROUTE = [
    (542.16, 1479.83), (529.78, 1407.15), (619.33, 1378.23), (693.20, 1348.87),
    (748.09, 1297.83), (795.44, 1232.73), (737.63, 1192.23), (746.69, 1119.70),
    (742.73, 1044.52), (720.58, 977.14), (755.66, 912.12), (843.41, 903.91),
    (911.55, 879.02), (950.25, 814.12), (1033.83, 800.50), (1096.40, 750.61),
]
WAYPOINT_ARRIVE = 90.0           # a waypoint is "reached" this close; it is a corridor, not a rail
WAYPOINT_DROP_UNITS = 420.0      # once the other player is this close, chase the player, not the
                                 # corridor -- the corridor only exists to leave the spawn bowl

# The efficiency fix, and it is a fix to THIS loop rather than to the map. Over ours_task7_wtb2's
# 24 step transitions 10 lost ground, and the four biggest losses were 150-185 unit bursts at
# straightness 0.93-0.97 -- clean open-ground walking in the wrong direction, because the loop
# committed a FULL burst to a facing it had just dead-reckoned through an open-loop turn. Turns are
# the unreliable part (research/18 §3.13: RMS 18 deg, and wtb2's step 15 commanded -72 deg and
# delivered -16), so a burst that follows a turn is now a SHORT PROBE whose only job is to measure
# the facing; a full-length burst is spent only when the facing was measured by a believed burst
# and the bearing error is already inside the deadband.
WALK_PROBE_S = 2.0               # ~62 units: enough rows to measure a heading, cheap to throw away
TURN_GAIN_MIN, TURN_GAIN_MAX = 0.35, 2.5
TURN_GAIN_ALPHA = 0.3            # EMA over delivered/commanded, per side, measured turn by turn.
                                 # 0.5 chased the noise in kill1: the gain swung 0.88 -> 1.63 ->
                                 # 1.24 -> 0.57 -> 1.45 in nine steps and the loop turned past the
                                 # bearing every other step
TURN_GAIN_MIN_CMD = 25.0         # below this a turn is too small to estimate a gain from
# The approach deadband is NOT the 12 deg the calibration used to classify a hold as a rotation.
# No single open-loop aim is better than about +-20 deg (research/18 §3.13), so insisting on 12 deg
# means every step turns, every step that turns walks a probe, and a full burst is never spent:
# kill1 took 14 steps and 80 s to close 190 of 1392 units for exactly that reason. Walking 30 deg
# off the bearing still closes cos(30) = 87 % of the distance, which beats turning again.
APPROACH_DEADBAND_DEG = 30.0

# Contact range. PAD_AXIS injects only full stick deflection, so the shortest usable turn hold
# already sweeps 35-40 deg and no single open-loop aim is better than about +-20 deg (research/18
# §3.13). A body subtends 20 deg only at about 15 units, so the engagement has to start at contact
# range and the sweep has to cover the angle space rather than aim at it.
ENGAGE_UNITS = 45.0
ENGAGE_SWEEP_HOLD_S = 0.55       # the shortest hold that turns at all
ENGAGE_FIRE_S = 0.45
ENGAGE_STEP_FORWARD_S = 0.8
# MEASURED in ours_task8_kill2, and it is the reason that run's 24 bursts hit nothing: the two
# players closed to **10.1 units horizontally** and stayed **35-55 units apart VERTICALLY** for the
# whole engagement (mean dy -44.8 over the last 400 rows, minimum 3-D camera-to-camera separation
# 34.9). At 10 units of ground range a 45-unit height difference is 77 deg of elevation, and the
# engagement only swept yaw. So the sweep now covers pitch as well -- both ways, because which of
# I/K raises the muzzle has never been measured.
ENGAGE_PITCH_HOLD_S = 0.5
ENGAGE_PITCH_STEPS = 2           # how far up and down the sweep goes, in holds

# Kill / round-end readout.
TELEPORT_UNITS = 250.0           # a jump this big between consecutive 4 Hz position rows is not
                                 # walking (a 0.25 s sample at 40 units/s moves 10 units): it is a
                                 # respawn, which on a one-life round means the round ENDED
RESPAWN_RADIUS = 60.0            # ... and landing this close to the spawn it left says so twice
MOVED_AWAY_UNITS = 250.0         # only after the player got this far from its spawn in the first
                                 # place, so the first steps out of the spawn cannot fire it
SERVER_LOG = os.path.join("server", "logs", "console-Medius.log")
SERVER_ROUND_MARK = "MediusPlayerReport"
# The player actor's class vtable. PS2X_PEEK SKIPS an item whose pointer chain does not resolve,
# so the items after it shift DOWN by one and an index alone names the wrong block: in kill1's log
# item 1 was the raw `0x408c58:4` static for 1698 rows and the actor block for 804. Word 0 of the
# actor block is the vtable, so the health watch checks it before reading anything.
ACTOR_VTABLE = 0x006691A0


# ---------------------------------------------------------------------------
# Live log tail
# ---------------------------------------------------------------------------
class RunLogTail(threading.Thread):
    """Follow one instance's run log and host-timestamp the rows the driver has to act on.

    The exe prints `[peek]` with std::endl (flushed per line) and does not timestamp it, so the
    arrival time recorded here is the clock the driver uses; it lags the guest state by at most one
    sampler period plus the poll interval.
    """

    _ITEM = re.compile(r"@([0-9a-fA-F]+):((?:\s+[0-9a-fA-F]{8}\([^)]*\))+)")
    _WORD = re.compile(r"([0-9a-fA-F]{8})\(")
    _SCALE = re.compile(r"\[call\]\s+[\d.]+s\s+" + MOVE_SCALE_TRACE_NAME + r"\s.*?\sf12=(-?[\d.eE+]+)")

    POLL_S = 0.05

    def __init__(self, path, addr=POSITION_ADDR):
        super().__init__(daemon=True)
        self.path, self.addr = path, addr
        self.rows = []          # (t, x, y, z) -- every peek row, all-zero pre-gameplay rows included
        self.scales = []        # (t, f12)
        self.lines = 0
        # Task 8: every OTHER PS2X_PEEK item of the same row, by its index in the PS2X_PEEK spec.
        # `items[i] = (t, addr, [word, ...])` is the most recent block; `item_rows` counts them so
        # "the chain never resolved" is distinguishable from "the chain resolved and nothing moved"
        # -- an item whose pointer chain is bad is SKIPPED by the exe, not printed as zeros.
        self.items = {}
        self.item_rows = {}
        self.watch = None       # (item_index, word_index) of a confirmed health word, or None
        self.watch_vtable = None  # (item_index, expected word 0) proving that item IS the actor
        self.watch_hist = []    # (t, value) of that word, appended only when it changes
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # -- reading -------------------------------------------------------------
    def run(self):
        f, buf = None, ""
        while not self._stop.is_set():
            if f is None:
                try:
                    f = open(self.path, "r", errors="replace")
                except OSError:
                    time.sleep(0.2)
                    continue
            chunk = f.read(65536)
            if not chunk:
                time.sleep(self.POLL_S)
                continue
            buf += chunk
            while True:
                nl = buf.find("\n")
                if nl < 0:
                    break
                self._line(buf[:nl])
                buf = buf[nl + 1:]
        if f:
            f.close()

    def _line(self, line):
        self.lines += 1
        t = time.time()
        if line.startswith("[peek]"):
            for idx, (addr, words) in enumerate(self._ITEM.findall(line)):
                raw = [int(w, 16) for w in self._WORD.findall(words)]
                if int(addr, 16) == self.addr:
                    vals = [struct.unpack("<f", struct.pack("<I", w))[0] for w in raw[:3]]
                    if len(vals) >= 3:
                        with self._lock:
                            self.rows.append((t, vals[0], vals[1], vals[2]))
                    continue
                with self._lock:
                    self.items[idx] = (t, int(addr, 16), raw)
                    self.item_rows[idx] = self.item_rows.get(idx, 0) + 1
                    if (self.watch and self.watch[0] == idx and self.watch[1] < len(raw)
                            and (self.watch_vtable is None
                                 or self.items.get(self.watch_vtable[0], (0, 0, [0]))[2][0]
                                 == self.watch_vtable[1])):
                        v = raw[self.watch[1]]
                        if not self.watch_hist or self.watch_hist[-1][1] != v:
                            self.watch_hist.append((t, v))
            return
        if MOVE_SCALE_TRACE_NAME in line:
            m = self._SCALE.search(line)
            if m:
                with self._lock:
                    self.scales.append((t, float(m.group(1))))

    def stop(self):
        self._stop.set()

    # -- queries -------------------------------------------------------------
    def _snapshot(self):
        with self._lock:
            return list(self.rows)

    def ingame(self):
        """Rows that are not the all-zero pre-gameplay record (research/18 §3.10 step 0)."""
        return [r for r in self._snapshot() if r[1] or r[2] or r[3]]

    def latest(self, max_age=4.0):
        rows = self.ingame()
        if rows and time.time() - rows[-1][0] <= max_age:
            return rows[-1]
        return None

    def last_before(self, t):
        rows = [r for r in self.ingame() if r[0] <= t]
        return rows[-1] if rows else None

    def window(self, t0, t1):
        return [r for r in self.ingame() if t0 <= r[0] <= t1]

    def scale_window(self, t0, t1):
        with self._lock:
            return [s for s in self.scales if t0 <= s[0] <= t1]

    def scale_ok(self, t0, t1, pad=2.5):
        """(ok, n, lo, hi) for the movement scale across a hold. No samples at all is NOT ok --
        an instrument that emits zero rows is a failed measurement, not a quiet one (§3.10 rule 3).
        """
        s = [v for _, v in self.scale_window(t0 - pad, t1 + pad)]
        if not s:
            return False, 0, None, None
        return (min(s) == MOVE_SCALE_LIVE == max(s)), len(s), min(s), max(s)


# ---------------------------------------------------------------------------
# Geometry, all in the (x, z) ground plane
# ---------------------------------------------------------------------------
def circle_fit(pts):
    """Algebraic (Kasa) circle fit; returns (cx, cz, r, mean residual)."""
    P = np.asarray(pts, dtype=float)
    if len(P) < 3:
        return None
    A = np.column_stack([2.0 * P[:, 0], 2.0 * P[:, 1], np.ones(len(P))])
    b = (P ** 2).sum(axis=1)
    try:
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx, cz, c = (float(v) for v in sol)
    rr = c + cx * cx + cz * cz
    if not (rr > 0.0) or not np.isfinite(rr):
        return None
    r = math.sqrt(rr)
    resid = float(np.mean(np.abs(np.hypot(P[:, 0] - cx, P[:, 1] - cz) - r)))
    return cx, cz, r, resid


def sweep_deg(pts, cx, cz):
    """Signed angle swept about (cx, cz), accumulated so a sweep past +-180 deg still adds up."""
    total, prev = 0.0, None
    for x, z in pts:
        a = math.degrees(math.atan2(z - cz, x - cx))
        if prev is not None:
            total += (a - prev + 180.0) % 360.0 - 180.0
        prev = a
    return total


def wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def spread(values):
    """(n, mean, min, max, peak-to-peak, stdev) -- a calibration without its spread is not one."""
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0}
    m = sum(v) / len(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / len(v)) if len(v) > 1 else 0.0
    return {"n": len(v), "mean": m, "min": min(v), "max": max(v), "ptp": max(v) - min(v), "sd": sd}


# ---------------------------------------------------------------------------
# One measured hold
# ---------------------------------------------------------------------------
def measure_hold(sh, tail, key, seconds, settle=HOLD_SETTLE_S, rest=HOLD_REST_S, label=""):
    """Inject one stick hold and measure what the 0x416054 record did over hold + settle.

    Returns both readings, because which one is meaningful depends on the key: a look hold rotates
    the record about the player (fit a circle, take the swept angle) and a walk/strafe hold
    translates it (take the displacement). `kind` says which the data supports.
    """
    t0 = time.time()
    sh.pad(seconds, sticks=[key])
    t1 = time.time()
    time.sleep(settle)
    t2 = time.time()
    time.sleep(rest)

    before = tail.last_before(t0 + PEEK_LEAD_S)
    pts = tail.window(t0, t2 + PEEK_LEAD_S)
    ok, n_scale, lo, hi = tail.scale_ok(t0, t2)
    out = {"label": label, "key": key, "hold_s": round(t1 - t0, 3), "rows": len(pts),
           "scale_ok": ok, "scale_n": n_scale, "scale_lo": lo, "scale_hi": hi,
           "kind": "no-data", "dist": None, "heading": None, "rate_units_s": None,
           "sweep_deg": None, "rate_deg_s": None, "radius": None, "residual": None,
           "centre": None, "start": None, "end": None, "path": None, "straight": None}
    if before is None or not pts:
        return out
    end = pts[-1]
    out["start"] = [before[1], before[2], before[3]]
    out["end"] = [end[1], end[2], end[3]]
    dx, dz = end[1] - before[1], end[3] - before[3]
    out["dist"] = math.hypot(dx, dz)
    out["rate_units_s"] = out["dist"] / max(out["hold_s"], 1e-6)
    if out["dist"] > 1e-6:
        out["heading"] = math.degrees(math.atan2(dz, dx))

    track = [(before[1], before[3])] + [(r[1], r[3]) for r in pts]
    # Path length along the sampled rows: net/path is 1.0 for a straight line and falls away as the
    # record curves -- which is what sliding along a wall looks like from these rows.
    out["path"] = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(track, track[1:]))
    out["straight"] = out["dist"] / out["path"] if out["path"] > 1e-6 else 0.0
    fit = circle_fit(track)
    if fit:
        cx, cz, r, resid = fit
        sw = sweep_deg(track, cx, cz)
        out.update(radius=r, residual=resid, centre=[cx, cz], sweep_deg=sw,
                   rate_deg_s=sw / max(out["hold_s"], 1e-6))
        if (len(track) >= MIN_ROTATION_POINTS and r <= ROTATION_MAX_RADIUS
                and resid <= ROTATION_MAX_RESIDUAL and abs(sw) >= TURN_DEADBAND_DEG):
            out["kind"] = "rotation"
        else:
            out["kind"] = "translation"
    else:
        out["kind"] = "translation"
    return out


def fmt_hold(m):
    scale = "1.0" if m["scale_ok"] else "BAD"
    rng = "" if m["scale_lo"] is None else f",{m['scale_lo']}..{m['scale_hi']}"
    s = (f"[cal] {m['label']:<22} key={m['key']} hold={m['hold_s']:.2f}s rows={m['rows']:2d} "
         f"kind={m['kind']:<11} scale={scale}({m['scale_n']}{rng})")
    if m["dist"] is not None:
        s += f" d={m['dist']:7.2f} ({m['rate_units_s']:6.2f} u/s) str={m['straight']:4.2f}"
    if m["heading"] is not None:
        s += f" hdg={m['heading']:7.2f}"
    if m["sweep_deg"] is not None:
        s += (f" sweep={m['sweep_deg']:8.2f} ({m['rate_deg_s']:7.2f} deg/s)"
              f" r={m['radius']:7.2f} res={m['residual']:5.2f}")
    return s


def wait_ingame(tail, sh, timeout=180.0, need=8):
    """research/18 §3.10 step 0, enforced in-process: no gameplay rows, no measurement."""
    t = time.time()
    while time.time() - t < timeout:
        if len(tail.ingame()) >= need:
            sh.log(f"liveness OK: {len(tail.ingame())} in-game peek rows, {tail.lines} log lines")
            return True
        time.sleep(1.0)
    sh.log(f"LIVENESS FAILED: {len(tail.ingame())} in-game peek rows of {len(tail.rows)} "
           f"({tail.lines} log lines) -- this run never reached gameplay")
    return False


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
def calibrate(sh, tail, out_dir, shots=True):
    """Measure look deg/s, lateral units/s, walk units/s and the camera orbit radius.

    Every turn repeat is bracketed by a short forward tap, so the rotation is measured twice by
    independent means: the circle fit through the camera arc, and the change in the direction the
    player actually walks. The second is what --walk-to-b consumes.
    """
    res = {"look": [], "lateral": [], "walk": [], "back": [], "heading_delta": [],
           "radius": [], "long": [], "left": [], "orbit_check": []}
    sh.log("calibration start")

    # --- look (right stick), bracketed by heading probes -------------------
    for rep in range(CAL_REPEATS):
        w0 = measure_hold(sh, tail, WALK_FORWARD_KEY, CAL_HEADING_PROBE_S, label=f"look{rep}_hdg_before")
        sh.log(fmt_hold(w0))
        t = measure_hold(sh, tail, LOOK_RIGHT_KEY, CAL_TURN_HOLD_S, label=f"look{rep}_turn")
        sh.log(fmt_hold(t))
        w1 = measure_hold(sh, tail, WALK_FORWARD_KEY, CAL_HEADING_PROBE_S, label=f"look{rep}_hdg_after")
        sh.log(fmt_hold(w1))
        if t["scale_ok"] and t["kind"] == "rotation":
            res["look"].append(t["rate_deg_s"])
            res["radius"].append(t["radius"])
        if (w0["heading"] is not None and w1["heading"] is not None and t["scale_ok"]
                and w0["dist"] > FACING_MIN_UNITS and w1["dist"] > FACING_MIN_UNITS):
            d = wrap_deg(w1["heading"] - w0["heading"])
            res["heading_delta"].append(d / max(t["hold_s"], 1e-6))
            sh.log(f"[cal] look{rep}_walk_heading_delta {d:.2f} deg over {t['hold_s']:.2f}s "
                   f"= {d / t['hold_s']:.2f} deg/s (circle fit said {t['rate_deg_s']})")
        # The camera sits behind the player: the direction from the record to the fitted circle
        # centre should be the walk heading, and the radius the offset. Check both.
        if t["kind"] == "rotation" and w1["heading"] is not None and t["centre"]:
            cx, cz = t["centre"]
            ex, ez = t["end"][0], t["end"][2]
            to_centre = math.degrees(math.atan2(cz - ez, cx - ex))
            res["orbit_check"].append(wrap_deg(to_centre - w1["heading"]))
            sh.log(f"[cal] look{rep}_orbit_check record->centre {to_centre:.2f} vs walk heading "
                   f"{w1['heading']:.2f} (delta {wrap_deg(to_centre - w1['heading']):.2f}), "
                   f"r={t['radius']:.2f}")
        b = measure_hold(sh, tail, WALK_BACK_KEY, CAL_RETURN_HOLD_S, label=f"look{rep}_return")
        sh.log(fmt_hold(b))
        if shots:
            sh.shot(f"cal_look{rep}")

    lng = measure_hold(sh, tail, LOOK_RIGHT_KEY, CAL_LONG_HOLD_S, label="look_long")
    sh.log(fmt_hold(lng))
    res["long"].append({"key": LOOK_RIGHT_KEY, "hold_s": lng["hold_s"], "rate_deg_s": lng["rate_deg_s"],
                        "kind": lng["kind"], "scale_ok": lng["scale_ok"]})
    lft = measure_hold(sh, tail, LOOK_LEFT_KEY, CAL_TURN_HOLD_S, label="look_left")
    sh.log(fmt_hold(lft))
    if lft["scale_ok"] and lft["kind"] == "rotation":
        res["left"].append(lft["rate_deg_s"])

    # --- lateral (left stick left/right) -----------------------------------
    for rep in range(CAL_REPEATS):
        r = measure_hold(sh, tail, LATERAL_RIGHT_KEY, CAL_TURN_HOLD_S, label=f"lateral{rep}_right")
        sh.log(fmt_hold(r))
        if r["scale_ok"]:
            res["lateral"].append({"rate_units_s": r["rate_units_s"], "rate_deg_s": r["rate_deg_s"],
                                   "kind": r["kind"], "dist": r["dist"]})
        lt = measure_hold(sh, tail, LATERAL_LEFT_KEY, CAL_TURN_HOLD_S, label=f"lateral{rep}_left")
        sh.log(fmt_hold(lt))
        if shots:
            sh.shot(f"cal_lateral{rep}")

    # --- walk --------------------------------------------------------------
    for rep in range(CAL_REPEATS):
        f = measure_hold(sh, tail, WALK_FORWARD_KEY, CAL_WALK_HOLD_S, label=f"walk{rep}_fwd")
        sh.log(fmt_hold(f))
        if f["scale_ok"]:
            res["walk"].append(f["rate_units_s"])
        b = measure_hold(sh, tail, WALK_BACK_KEY, CAL_WALK_HOLD_S, label=f"walk{rep}_back")
        sh.log(fmt_hold(b))
        if b["scale_ok"]:
            res["back"].append(b["rate_units_s"])
        if shots:
            sh.shot(f"cal_walk{rep}")
    wl = measure_hold(sh, tail, WALK_FORWARD_KEY, CAL_LONG_HOLD_S, label="walk_long")
    sh.log(fmt_hold(wl))
    res["long"].append({"key": WALK_FORWARD_KEY, "hold_s": wl["hold_s"], "rate_units_s": wl["rate_units_s"],
                        "kind": wl["kind"], "scale_ok": wl["scale_ok"]})
    sh.log(fmt_hold(measure_hold(sh, tail, WALK_BACK_KEY, CAL_LONG_HOLD_S, label="walk_long_return")))

    summary = {
        "look_deg_per_s": spread(res["look"]),
        "look_deg_per_s_from_walk_heading": spread(res["heading_delta"]),
        "look_left_deg_per_s": spread(res["left"]),
        "camera_orbit_radius": spread(res["radius"]),
        "orbit_direction_error_deg": spread(res["orbit_check"]),
        "walk_units_per_s": spread(res["walk"]),
        "walk_back_units_per_s": spread(res["back"]),
        "lateral": res["lateral"],
        "linearity": res["long"],
    }
    sh.log("[cal] SUMMARY " + json.dumps(summary, default=float))
    if out_dir:
        with open(os.path.join(out_dir, f"calibration_{sh.tag or 'A'}.json"), "w") as fh:
            json.dump({"raw": res, "summary": summary}, fh, indent=1, default=float)
    return summary


# ---------------------------------------------------------------------------
# --walk-to-b
# ---------------------------------------------------------------------------
def player_pos(record, heading_deg):
    """The player, from its orbiting-camera record: the camera is CAMERA_ORBIT_RADIUS behind."""
    h = math.radians(heading_deg)
    return record[1] + CAMERA_ORBIT_RADIUS * math.cos(h), record[3] + CAMERA_ORBIT_RADIUS * math.sin(h)


def turn_hold_seconds(error_deg):
    """Hold length for a turn of |error_deg|, from the affine response: the first TURN_HOLD_LEAD_S
    of a hold delivers nothing, so a short correction that ignores the lead delivers nothing."""
    return min(abs(error_deg) / LOOK_DEG_PER_S + TURN_HOLD_LEAD_S, TURN_MAX_HOLD_S)


def turn_by(sh, tail, error_deg):
    """Turn the facing by `error_deg` with one timed hold at the measured look rate."""
    key = LOOK_RIGHT_KEY if error_deg * LOOK_RIGHT_SIGN >= 0 else LOOK_LEFT_KEY
    secs = turn_hold_seconds(error_deg)
    m = measure_hold(sh, tail, key, secs, settle=TURN_SETTLE_S, rest=WALK_REST_S,
                     label=f"turn{error_deg:+.0f}")
    sh.log(fmt_hold(m))
    return m


def facing_probe(sh, tail, seconds=FACING_PROBE_S, label="facing"):
    """A short forward tap; the direction the record travels IS the player's facing."""
    m = measure_hold(sh, tail, WALK_FORWARD_KEY, seconds, label=label)
    sh.log(fmt_hold(m))
    if m["heading"] is None or m["dist"] < FACING_MIN_UNITS or not m["scale_ok"]:
        return None, m
    return m["heading"], m


def walk_to_b(A, B, tailA, tailB, arrive, max_steps, max_seconds, shots=True):
    """Task 7's one-directional approach: A walks to a PARKED B, capped by steps and wall clock.

    It is now the single-mover entry point into the one loop -- `approach()` with no corridor, no
    engagement and a partner that is not walking back. Task 8 generalised the loop rather than
    forking it, so `sim_walk_to_b.py` exercises the code the match actually runs.

    A parked opponent starves a STUCK mover (the movement scale is fed by received bytes, KNOWN.md),
    so this mode is the calibration/proving one: --converge is what a match should use.
    """
    duel = Duel()
    me, other = Side("A", A.sh, tailA), Side("B", B.sh, tailB)
    fb, _ = facing_probe(B.sh, tailB, label="B_facing")
    if fb is None:
        A.sh.log("walk-to-b: B's facing probe moved nothing -- falling back to the raw record "
                 "(B is then known only to within the orbit radius)")
    else:
        duel.set_facing("B", fb)
    r = approach(me, other, duel, arrive, max_steps, max_seconds, shots=shots, shot_every=1,
                 engage=-1.0)
    return r


# ---------------------------------------------------------------------------
# Task 8 (S3): two movers converging, and the kill / round-end readout
# ---------------------------------------------------------------------------
class Duel:
    """What the two approach threads have to agree on: each side's measured facing, each side's
    view of the gap, and a single contact flag, so that when one side reaches contact the other
    stops walking instead of running past it."""

    def __init__(self):
        self._lock = threading.Lock()
        self.facing = {}
        self.dist = {}
        self.contact = threading.Event()
        self.stop = threading.Event()

    def set_facing(self, tag, f):
        with self._lock:
            self.facing[tag] = f

    def get_facing(self, tag):
        with self._lock:
            return self.facing.get(tag)

    def set_dist(self, tag, d):
        with self._lock:
            self.dist[tag] = d

    def best_dist(self):
        with self._lock:
            v = [d for d in self.dist.values() if d is not None]
        return min(v) if v else None


class Side:
    """One instance as the approach loop sees it."""

    def __init__(self, tag, sh, tail, route=None):
        self.tag, self.sh, self.tail, self.route = tag, sh, tail, route
        self.turn_gain = 1.0
        self.spawn = None
        self.result = None


def other_player_pos(tail, facing):
    """The other side's player position from its camera record. Without its facing the record is
    only good to within CAMERA_ORBIT_RADIUS, which is why both sides publish theirs."""
    r = tail.latest()
    if r is None:
        return None, None
    if facing is None:
        return (r[1], r[3]), r
    return player_pos(r, facing), r


def approach(me, other, duel, arrive, max_steps, max_seconds, shots=True, shot_every=3,
             engage=ENGAGE_UNITS):
    """Walk `me` toward `other` until the gap closes, following `me.route` out of the spawn while
    the other player is still far away.

    Generalised from Task 7's one-directional --walk-to-b: it runs on either instance, both at
    once, and the other player is READ LIVE rather than assumed parked.
    """
    sh, tail = me.sh, me.tail
    t_start = time.time()
    sh.log(f"approach[{me.tag}]: arrive<={arrive} engage<={engage} <={max_steps} steps, "
           f"<={max_seconds}s, route={len(me.route or [])} waypoints")
    facing = None
    for attempt in range(FACING_PROBE_TRIES):
        facing, _ = facing_probe(sh, tail, label=f"{me.tag}_facing{attempt}")
        if facing is not None:
            break
        sh.log(f"approach[{me.tag}]: facing probe {attempt} moved nothing -- the player may not be "
               f"controllable yet; turning 90 deg, waiting {FACING_PROBE_REST_S}s and retrying")
        turn_by(sh, tail, 90.0)
        time.sleep(FACING_PROBE_REST_S)
    if facing is None:
        # NOT an abort. A side that cannot measure its heading can still walk: every burst is
        # scored and a believed one replaces the facing, so the loop finds it within a step or two.
        # Aborting here cost ours_task8_kill3 its second mover and, with it, the whole run.
        facing, confident0 = 0.0, False
        sh.log(f"approach[{me.tag}]: no heading after {FACING_PROBE_TRIES} probes -- starting at "
               f"0 deg with the facing UNTRUSTED; the first believed burst will measure it")
    else:
        confident0 = True
    duel.set_facing(me.tag, facing)
    r0 = tail.latest()
    if r0 is not None and me.spawn is None:
        me.spawn = (r0[1], r0[3])

    best, track = None, []
    wp, detour_left, detour_sign, blocks, confident = 0, 0, 1.0, 0, confident0
    pending_turn = None              # (facing before the turn, commanded degrees)
    for step in range(max_steps):
        if duel.contact.is_set():
            sh.log(f"[app {me.tag}] STOP -- the other side reached contact after {step} steps")
            return {"ok": True, "reason": "contact-other", "steps": step, "best": best,
                    "track": track}
        if duel.stop.is_set():
            sh.log(f"[app {me.tag}] STOP -- the run was ended (kill signal or timeout) after "
                   f"{step} steps")
            return {"ok": False, "reason": "run-ended", "steps": step, "best": best,
                    "track": track}
        if time.time() - t_start > max_seconds:
            sh.log(f"[app {me.tag}] STOP -- wall-clock cap {max_seconds}s")
            return {"ok": False, "reason": "time-cap", "steps": step, "best": best, "track": track}
        rme = tail.latest()
        opos, _ = other_player_pos(other.tail, duel.get_facing(other.tag))
        if rme is None or opos is None:
            sh.log(f"[app {me.tag}] STOP -- stale position rows "
                   f"(me={rme is not None} other={opos is not None})")
            return {"ok": False, "reason": "stale-rows", "steps": step, "best": best,
                    "track": track}
        mx, mz = player_pos(rme, facing)
        dist = math.hypot(opos[0] - mx, opos[1] - mz)
        best = dist if best is None else min(best, dist)
        duel.set_dist(me.tag, dist)
        # The corridor exists to leave the spawn bowl, not to reach the player: as soon as the
        # other side is within WAYPOINT_DROP_UNITS the chain is dropped and the target is the
        # player itself.
        target, tname = opos, "player"
        if me.route and dist > WAYPOINT_DROP_UNITS:
            while wp < len(me.route) and math.hypot(me.route[wp][0] - mx,
                                                    me.route[wp][1] - mz) <= WAYPOINT_ARRIVE:
                wp += 1
            # ... and skip ahead whenever the NEXT point is already the nearer one, so a waypoint
            # the player cannot quite reach cannot pin the chain. The corridor is monotone in path
            # length, so the nearest point is the local one and this only ever advances.
            while (wp + 1 < len(me.route)
                   and math.hypot(me.route[wp + 1][0] - mx, me.route[wp + 1][1] - mz)
                   < math.hypot(me.route[wp][0] - mx, me.route[wp][1] - mz)):
                wp += 1
            if wp < len(me.route):
                target, tname = me.route[wp], f"wp{wp}"
        bearing = math.degrees(math.atan2(target[1] - mz, target[0] - mx))
        aim = wrap_deg(bearing + detour_sign * DETOUR_DEG) if detour_left > 0 else bearing
        err = wrap_deg(aim - facing)
        track.append({"step": step, "tag": me.tag, "me": [rme[1], rme[2], rme[3]],
                      "player_me": [mx, mz], "player_other": list(opos), "dist": dist,
                      "target": list(target), "target_name": tname, "facing": facing,
                      "bearing": bearing, "aim": aim, "err": err, "detour": detour_left,
                      "confident": confident, "turn_gain": me.turn_gain, "t": time.time()})
        sh.log(f"[app {me.tag}] step {step:2d} me=({mx:8.2f},{mz:8.2f}) other=({opos[0]:8.2f},"
               f"{opos[1]:8.2f}) dist={dist:8.2f} tgt={tname:>6} face={facing:7.2f} "
               f"bear={bearing:7.2f} err={err:+7.2f} det={detour_left} conf={int(confident)} "
               f"gain={me.turn_gain:4.2f}")
        if shots and (step % shot_every == 0):
            sh.shot(f"app{step:02d}")
        if dist <= engage:
            sh.log(f"[app {me.tag}] CONTACT: {dist:.2f} <= {engage} units after {step} steps")
            duel.contact.set()
            return {"ok": True, "reason": "contact", "steps": step, "dist": dist,
                    "best": best, "track": track}
        if dist <= arrive:
            sh.log(f"[app {me.tag}] ARRIVED: {dist:.2f} <= {arrive} units after {step} steps")
            return {"ok": True, "reason": "arrived", "steps": step, "dist": dist,
                    "best": best, "track": track}
        if abs(err) > APPROACH_DEADBAND_DEG:
            # The open-loop turn is the unreliable link (research/18 3.13: RMS 18 deg, and wtb2's
            # step 15 asked -72 and delivered -16). Ask for err/gain and let the next believed
            # burst say what was actually delivered.
            cmd = max(-179.0, min(179.0, err / max(me.turn_gain, 0.2)))
            mt = turn_by(sh, tail, cmd)
            applied = (mt["sweep_deg"] if (mt["kind"] == "rotation" and mt["sweep_deg"] is not None)
                       else cmd)
            pending_turn = (facing, err)
            facing = wrap_deg(facing + applied)
            confident = False
            track[-1]["turn_cmd"] = cmd
            track[-1]["turn_applied"] = applied
        # A FULL burst is spent only on a facing that was measured by a believed burst and already
        # points at the target; everything else gets a probe whose only job is to measure the
        # facing again. This is the fix for wtb2's 38.6 % efficiency: its four biggest losses were
        # 150-185 unit bursts at straightness 0.93-0.97 walked on a dead-reckoned facing.
        if confident and abs(err) <= APPROACH_DEADBAND_DEG and detour_left == 0:
            want = (math.hypot(target[0] - mx, target[1] - mz)
                    * WALK_STEP_FRACTION / WALK_UNITS_PER_S_LONG)
            secs = max(WALK_STEP_MIN_S, min(WALK_STEP_MAX_S, want))
            probe = False
        else:
            secs, probe = WALK_PROBE_S, True
        m = measure_hold(sh, tail, WALK_FORWARD_KEY, secs, settle=WALK_SETTLE_S,
                         rest=WALK_REST_S, label=f"{me.tag}app{step:02d}_walk")
        sh.log(fmt_hold(m))
        expect = WALK_UNITS_PER_S_LONG * max(m["hold_s"] - TURN_HOLD_LEAD_S, 0.0)
        good = (m["scale_ok"] and m["heading"] is not None
                and m["dist"] >= WALK_PROGRESS_FRACTION * expect
                and m["straight"] >= WALK_STRAIGHT_MIN)
        track[-1]["walk"] = {"hold_s": m["hold_s"], "dist": m["dist"], "straight": m["straight"],
                             "expect": expect, "scale_ok": m["scale_ok"], "believed": good,
                             "probe": probe}
        if good:
            if pending_turn is not None:
                f0, cmd_deg = pending_turn
                delivered = wrap_deg(m["heading"] - f0)
                if abs(cmd_deg) >= TURN_GAIN_MIN_CMD and delivered * cmd_deg > 0:
                    g = min(TURN_GAIN_MAX, max(TURN_GAIN_MIN, abs(delivered) / abs(cmd_deg)))
                    me.turn_gain = (1.0 - TURN_GAIN_ALPHA) * me.turn_gain + TURN_GAIN_ALPHA * g
                    sh.log(f"[app {me.tag}] turn gain: asked {cmd_deg:+.1f} deg, delivered "
                           f"{delivered:+.1f} -> gain {me.turn_gain:.2f}")
                pending_turn = None
            facing = m["heading"]                        # measured truth beats dead reckoning
            duel.set_facing(me.tag, facing)
            confident = True
            detour_left = 0                              # a believed burst ENDS the detour; wtb2
            blocks = 0                                   # decremented it and kept walking off-line
        else:
            why = ("scale" if not m["scale_ok"] else
                   "short" if m["dist"] is not None and m["dist"] < WALK_PROGRESS_FRACTION * expect
                   else "curved")
            sh.log(f"[app {me.tag}] step {step} burst not believed ({why}): moved {m['dist']} of "
                   f"{expect:.0f}, straightness {m['straight']} -- facing kept, detouring")
            confident = False
            blocks += 1
            if blocks % (DETOUR_STEPS + 1) == 0:
                detour_sign = -detour_sign
                sh.log(f"[app {me.tag}] {blocks} blocked bursts in a row -- detour the other way")
            detour_left = DETOUR_STEPS
            measure_hold(sh, tail, WALK_BACK_KEY, UNSTICK_BACK_S, settle=WALK_SETTLE_S,
                         rest=WALK_REST_S, label=f"{me.tag}app{step:02d}_unstick_back")
            side = LATERAL_RIGHT_KEY if detour_sign > 0 else LATERAL_LEFT_KEY
            measure_hold(sh, tail, side, UNSTICK_LATERAL_UNITS / LATERAL_UNITS_PER_S,
                         settle=WALK_SETTLE_S, rest=WALK_REST_S,
                         label=f"{me.tag}app{step:02d}_unstick_side")
        if detour_left > 0 and not good:
            detour_left -= 1
    sh.log(f"[app {me.tag}] STOP -- step cap {max_steps} reached, best distance {best}")
    return {"ok": False, "reason": "step-cap", "steps": max_steps, "best": best, "track": track}


def engage_fight(me, other, duel, seconds, shots=True):
    """Contact range: face the other player and sweep-fire.

    No open-loop aim is better than about +-20 deg and the shortest usable turn hold already
    sweeps 35-40 deg (research/18 3.13), so this COVERS the angle space with the shortest holds
    that turn at all rather than aiming at the target, and closes a little every cycle.
    """
    sh, tail = me.sh, me.tail
    t0 = time.time()
    cycle = 0
    while time.time() - t0 < seconds and not duel.stop.is_set():
        rme, facing = tail.latest(), duel.get_facing(me.tag)
        opos, _ = other_player_pos(other.tail, duel.get_facing(other.tag))
        if rme is not None and facing is not None and opos is not None:
            mx, mz = player_pos(rme, facing)
            dist = math.hypot(opos[0] - mx, opos[1] - mz)
            bearing = math.degrees(math.atan2(opos[1] - mz, opos[0] - mx))
            err = wrap_deg(bearing - facing)
            duel.set_dist(me.tag, dist)
            rother = other.tail.latest()
            dy = (rother[2] - rme[2]) if rother else float("nan")
            elev = math.degrees(math.atan2(dy, max(dist, 1e-6)))
            sh.log(f"[fight {me.tag}] cycle {cycle:2d} dist={dist:8.2f} dy={dy:+7.2f} "
                   f"elev={elev:+6.1f}deg face={facing:7.2f} bear={bearing:7.2f} err={err:+7.2f}")
            if abs(err) > TURN_DEADBAND_DEG:
                mt = turn_by(sh, tail, err / max(me.turn_gain, 0.2))
                if mt["kind"] == "rotation" and mt["sweep_deg"] is not None:
                    duel.set_facing(me.tag, wrap_deg(facing + mt["sweep_deg"]))
        # Cover the angle space in BOTH axes. Yaw: the bearing and one shortest-hold step either
        # side. Pitch: level, then ENGAGE_PITCH_STEPS holds one way and the same number back plus
        # the same again the other way, so neither the sign of I/K nor the sign of the height
        # difference has to be known. Every position gets two bursts.
        pitch_plan = ([(None, 0)]
                      + [(LOOK_UP_KEY, 1)] * ENGAGE_PITCH_STEPS
                      + [(LOOK_DOWN_KEY, -1)] * (2 * ENGAGE_PITCH_STEPS))
        pitch_at = 0
        for pkey, pstep in pitch_plan:
            if duel.stop.is_set():
                break
            if pkey:
                sh.pad(ENGAGE_PITCH_HOLD_S, sticks=[pkey])
                pitch_at += pstep
                time.sleep(0.15)
            for key in (None, LOOK_RIGHT_KEY, LOOK_LEFT_KEY):
                if duel.stop.is_set():
                    break
                if key:
                    sh.pad(ENGAGE_SWEEP_HOLD_S, sticks=[key])
                    time.sleep(0.15)
                for _ in range(2):
                    sh.pad(ENGAGE_FIRE_S, buttons=["R1"])
                    time.sleep(0.12)
            # the yaw sweep above nets one step left; put it back before the next pitch position
            sh.pad(ENGAGE_SWEEP_HOLD_S, sticks=[LOOK_RIGHT_KEY])
            time.sleep(0.15)
        # ... and level the pitch again, or the forward tap below measures a heading through a
        # camera that is looking at the sky.
        while pitch_at and not duel.stop.is_set():
            sh.pad(ENGAGE_PITCH_HOLD_S,
                   sticks=[LOOK_DOWN_KEY if pitch_at > 0 else LOOK_UP_KEY])
            pitch_at += -1 if pitch_at > 0 else 1
            time.sleep(0.15)
        if shots:
            sh.shot(f"fight{cycle:02d}")
        # Re-measure the facing (the sweep moved it) and close a little.
        f, _ = facing_probe(sh, tail, seconds=ENGAGE_STEP_FORWARD_S, label=f"{me.tag}_fight_face")
        if f is not None:
            duel.set_facing(me.tag, f)
        cycle += 1
    return {"cycles": cycle}


class KillWatch(threading.Thread):
    """Decide, live, whether a death or a round end has happened -- and say WHICH signal fired.

    Three independent signals, because no single one of them is trustworthy on its own:

    1. `health` -- a word of the peeked player-actor block crossing into a range. Armed only when
       --health-item/--health-word name an offset confirmed across two kills; the brief forbids
       believing a candidate before that, so by default this signal is OFF and says so.
    2. `respawn` -- the position record of either instance TELEPORTING (a jump no walk can make
       between two 4 Hz samples), or landing back within RESPAWN_RADIUS of the spawn it left. On a
       one-life round that is the round ending, which is what a kill causes.
    3. `server` -- a new MediusPlayerReport in the Horizon Medius log. This one is recorded and
       NEVER fires, and the reason is measured rather than assumed: in `ours_task8_kill1` exactly
       one MediusPlayerReport arrived, at T+156.7 s, with the two players 603 units apart, both
       still walking, and no respawn in either position record. It is a periodic client stats
       report, not a round boundary. Firing on it made that run print PASS for a round that had
       not ended -- which is the flattering positive this sprint keeps warning about. The DME TCP
       log is worse still: research/18 §1 measured a playing match and a frozen one as
       byte-identical there.

    The first FIRING signal wins and is named in the result; the observations keep being
    collected, so the run can say whether they agreed.
    """

    #: signals that may end a run. `server` is deliberately not among them (see above).
    FIRING = ("health", "respawn")

    POLL_S = 0.25

    def __init__(self, tails, spawns, server_log=SERVER_LOG, health=None,
                 health_range=(-0.5, 0.5)):
        super().__init__(daemon=True)
        self.tails, self.spawns = tails, spawns
        self.server_log, self.health, self.health_range = server_log, health, health_range
        self.events = []
        self.fired = None
        self._stop = threading.Event()
        self._seen = {t: 0 for t in tails}
        self._away = {t: False for t in tails}
        try:
            self._server_pos = os.path.getsize(server_log)
        except OSError:
            self._server_pos = None

    def stop(self):
        self._stop.set()

    def _add(self, kind, tag, detail):
        ev = {"kind": kind, "tag": tag, "t": time.time(), "detail": detail,
              "firing": kind in self.FIRING}
        self.events.append(ev)
        if self.fired is None and ev["firing"]:
            self.fired = ev
        return ev

    def _check_positions(self):
        for tag, tail in self.tails.items():
            rows = tail.ingame()
            spawn = self.spawns.get(tag)
            i = self._seen[tag]
            for j in range(max(i, 1), len(rows)):
                a, b = rows[j - 1], rows[j]
                d = math.hypot(b[1] - a[1], b[3] - a[3])
                far = (spawn is not None
                       and math.hypot(b[1] - spawn[0], b[3] - spawn[1]) > MOVED_AWAY_UNITS)
                if far:
                    self._away[tag] = True
                if d >= TELEPORT_UNITS:
                    self._add("respawn", tag, {"jump": d, "from": [a[1], a[3]],
                                               "to": [b[1], b[3]]})
                elif (self._away[tag] and spawn is not None
                      and math.hypot(b[1] - spawn[0], b[3] - spawn[1]) <= RESPAWN_RADIUS):
                    self._away[tag] = False
                    self._add("respawn", tag, {"back_at_spawn": [b[1], b[3]],
                                               "spawn": list(spawn)})
            self._seen[tag] = len(rows)

    def _check_health(self):
        if not self.health:
            return
        lo, hi = self.health_range
        for tag, tail in self.tails.items():
            hist = list(tail.watch_hist)
            for t, raw in hist:
                v = struct.unpack("<f", struct.pack("<I", raw))[0]
                if lo <= v <= hi:
                    self._add("health", tag, {"raw": raw, "value": v, "at": t,
                                              "offset": self.health})
                    tail.watch_hist = []
                    break

    def _check_server(self):
        if self._server_pos is None:
            return
        try:
            size = os.path.getsize(self.server_log)
        except OSError:
            return
        if size <= self._server_pos:
            self._server_pos = min(self._server_pos, size)
            return
        with open(self.server_log, "r", errors="replace") as f:
            f.seek(self._server_pos)
            chunk = f.read(size - self._server_pos)
        self._server_pos = size
        n = chunk.count(SERVER_ROUND_MARK)
        if n:
            self._add("server", "-", {"marks": n, "mark": SERVER_ROUND_MARK})

    def run(self):
        while not self._stop.is_set():
            try:
                self._check_health()
                self._check_positions()
                self._check_server()
            except Exception as e:              # noqa: BLE001 - a watcher must not kill the run
                self.events.append({"kind": "watch-error", "tag": "-", "t": time.time(),
                                    "detail": repr(e)})
            self._stop.wait(self.POLL_S)


class Client:
    def __init__(self, tag, out, name, existing, seconds):
        self.tag, self.out, self.name, self.existing, self.seconds = tag, out, name, existing, seconds
        self.proc = self.sh = None
        self.error = None
        self.run_log = os.path.abspath(os.path.join(
            "logs", f"run_{tag}_{time.strftime('%Y%m%d_%H%M%S')}.log"))
        self.tail = None

    def launch(self):
        # run.sh honours PS2X_RUN_LOG, so the driver knows which file carries this instance's
        # [peek] rows and can follow them live instead of guessing by modification time.
        os.environ["PS2X_RUN_LOG"] = self.run_log
        self.proc, self.title = L.launch(self.seconds, self.tag)
        self.tail = RunLogTail(self.run_log)
        self.tail.start()

    def login(self):
        try:
            self.sh = L.attach(self.proc, self.title, self.out, self.tag + "_", L.INSTANCES[self.tag]["PS2X_SOCOM2_INPUT_FILE"])
            L.boot_to_online(self.sh)
            L.login(self.sh, self.name, "socom", self.existing)
            L.to_briefing_room(self.sh)
        except BaseException as e:      # noqa: BLE001 - surfaced by the caller
            self.error = e

    def kill(self):
        if self.tail:
            self.tail.stop()
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
    ap.add_argument("--probe-both", action="store_true", help="with --probe: drive the same stick sequence on B as well, so local control is proven on both sides")
    ap.add_argument("--turn-key", default="L", help="L = right stick right, the only key that turns on this preset. D (left stick right) was believed to be a 'Sure Shot turn' but MEASURES as a strafe: constant world bearing, facing unchanged (research/18 §3.13)")
    ap.add_argument("--calibrate", action="store_true", help="gameplay: measure look deg/s, lateral units/s, walk units/s and the camera orbit radius on A (three repeats each, with the spread)")
    ap.add_argument("--walk-to-b", action="store_true", help="gameplay: A reads both positions, turns toward B and walks until within --arrive units")
    ap.add_argument("--arrive", type=float, default=ARRIVE_UNITS)
    ap.add_argument("--max-steps", type=int, default=WALK_TO_B_MAX_STEPS)
    ap.add_argument("--max-walk-seconds", type=float, default=WALK_TO_B_MAX_SECONDS)
    # -- Task 8 (S3) --------------------------------------------------------
    ap.add_argument("--converge", action="store_true",
                    help="gameplay: BOTH instances walk toward each other (one mover cannot close "
                         "1382 units inside a round -- 38.6%% measured closure efficiency needs "
                         "~450 s against a ~360 s round), A following the mined mp51 corridor")
    ap.add_argument("--until-kill", action="store_true",
                    help="implies --converge: run until a death or round end is observed, capture "
                         "both screens at that moment and print which signal fired; exit 1 on the "
                         "timeout so a failed match is a clean FAIL rather than a hang")
    ap.add_argument("--engage", type=float, default=ENGAGE_UNITS,
                    help="gap at which the approach stops and the sweep-fire engagement starts")
    ap.add_argument("--fight-seconds", type=float, default=150.0)
    ap.add_argument("--kill-timeout", type=float, default=420.0,
                    help="wall-clock budget from the liveness check to the kill; on expiry the run "
                         "ends FAIL with both screens captured")
    ap.add_argument("--no-route", action="store_true",
                    help="ignore the mined corridor and walk the straight line (the Task 7 policy)")
    ap.add_argument("--health-item", type=int, default=None,
                    help="index of the PS2X_PEEK item holding the player actor block, and "
                         "--health-word the word in it. ONLY pass these once the offset has been "
                         "confirmed across two separate kills (task-8 brief); unset, the health "
                         "signal is off and the run says so instead of guessing")
    ap.add_argument("--health-word", type=int, default=None)
    ap.add_argument("--health-range", default="-0.5:0.5",
                    help="lo:hi -- the float range that counts as dead for --health-word")
    a = ap.parse_args()
    if a.until_kill:
        a.converge = True
    os.makedirs(a.out, exist_ok=True)
    if subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower().count("socom2.exe"):
        raise SystemExit("socom2.exe is already running")
    A = Client("A", a.out, a.name_a, True, a.seconds)
    B = Client("B", a.out, a.name_b, a.existing_b, a.seconds)
    failed = False
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
                if a.probe_both:
                    B.sh.hold(key, secs)
                A.sh.log(f"probe {i:02d} {key} {secs}s")
                time.sleep(2.0)
                A.sh.shot(f"probe{i:02d}_{key}")
                B.sh.shot(f"probe{i:02d}_{key}")
        if a.calibrate or a.walk_to_b or a.converge:
            # research/18 §3.10 step 0, in-process: no gameplay rows, no measurement. Four of
            # eleven runs in the previous task never reached gameplay and their screenshots did
            # not say so.
            liveA = wait_ingame(A.tail, A.sh)
            liveB = wait_ingame(B.tail, B.sh)
            A.sh.log(f"in-game peek rows A={len(A.tail.ingame())} B={len(B.tail.ingame())} "
                     f"(log lines A={A.tail.lines} B={B.tail.lines})")
            if not (liveA and liveB):
                raise SystemExit("liveness check failed: the run never reached gameplay -- discard it")
        if a.calibrate:
            calibrate(A.sh, A.tail, a.out)
        if a.walk_to_b:
            r = walk_to_b(A, B, A.tail, B.tail, a.arrive, a.max_steps, a.max_walk_seconds)
            with open(os.path.join(a.out, "walk_to_b.json"), "w") as fh:
                json.dump(r, fh, indent=1, default=float)
            A.sh.log(f"[wtb] result {r['ok']} {r['reason']} steps={r['steps']} best={r.get('best')}")
            A.sh.shot("wtb_final")
            B.sh.shot("wtb_final")
        if a.converge:
            # Task 8 (S3): BOTH sides close, then fight, and a KillWatch decides when it is over.
            duel = Duel()
            route = None if a.no_route else MP51_SEAL_ROUTE
            sideA = Side("A", A.sh, A.tail, route=route)
            sideB = Side("B", B.sh, B.tail, route=None)   # B's half of the map has no mined track
            spawns = {}
            for tag, c in (("A", A), ("B", B)):
                rows = c.tail.ingame()
                if rows:
                    spawns[tag] = (rows[0][1], rows[0][3])
            health = None
            if a.health_item is not None and a.health_word is not None:
                health = (a.health_item, a.health_word)
                for c in (A, B):
                    c.tail.watch = health
                    c.tail.watch_vtable = (a.health_item, ACTOR_VTABLE)
                A.sh.log(f"kill readout: health word armed at PS2X_PEEK item {a.health_item} "
                         f"word {a.health_word} (actor +0x{a.health_word * 4:x}), dead range "
                         f"{a.health_range}")
            else:
                A.sh.log("kill readout: health word NOT armed (no confirmed offset) -- the run "
                         "reads the round end from the position records and the Medius log, and "
                         "the actor block is logged for offline confirmation")
            lo, hi = (float(v) for v in a.health_range.split(":"))
            watch = KillWatch({"A": A.tail, "B": B.tail}, spawns, health=health,
                              health_range=(lo, hi))
            watch.start()
            t_gameplay = time.time()
            kill_shots = {"done": False}

            def monitor():
                while not duel.stop.is_set():
                    if watch.fired:
                        ev = watch.fired
                        A.sh.log(f"KILL/ROUND-END SIGNAL {ev['kind']} on {ev['tag']} at "
                                 f"T+{ev['t'] - t_gameplay:.1f}s {json.dumps(ev['detail'], default=float)}")
                        if not kill_shots["done"]:
                            kill_shots["done"] = True
                            for c in (A, B):
                                try:
                                    c.sh.shot("kill")
                                except Exception as e:          # noqa: BLE001
                                    A.sh.log(f"kill screenshot failed on {c.tag}: {e!r}")
                        duel.stop.set()
                        return
                    if time.time() - t_gameplay > a.kill_timeout:
                        A.sh.log(f"kill timeout: {a.kill_timeout}s elapsed with no signal")
                        duel.stop.set()
                        return
                    time.sleep(0.25)

            mon = threading.Thread(target=monitor, daemon=True)
            mon.start()
            threads = []
            for me, oth in ((sideA, sideB), (sideB, sideA)):
                # arrive == engage in this mode: two separate thresholds would let both sides
                # stop at `arrive` without ever setting contact, and then nobody would shoot.
                t = threading.Thread(
                    target=lambda m=me, o=oth: setattr(
                        m, "result", approach(m, o, duel, a.engage, a.max_steps,
                                              a.max_walk_seconds, engage=a.engage)))
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
            A.sh.log(f"approach done: A={sideA.result and sideA.result.get('reason')} "
                     f"best={sideA.result and sideA.result.get('best')} "
                     f"B={sideB.result and sideB.result.get('reason')} "
                     f"best={sideB.result and sideB.result.get('best')}")
            fights = {}
            closest_now = duel.best_dist()
            near = closest_now is not None and closest_now <= a.engage * 2.5
            if (duel.contact.is_set() or near) and not duel.stop.is_set():
                ft = []
                for me, oth in ((sideA, sideB), (sideB, sideA)):
                    t = threading.Thread(
                        target=lambda m=me, o=oth: fights.__setitem__(
                            m.tag, engage_fight(m, o, duel, a.fight_seconds)))
                    t.start()
                    ft.append(t)
                for t in ft:
                    t.join()
            else:
                A.sh.log(f"no contact (closest {closest_now}): the engagement phase is skipped "
                         f"-- there is nothing in front of either player to shoot at")
            duel.stop.set()
            mon.join(timeout=5.0)
            watch.stop()
            A.sh.shot("final")
            B.sh.shot("final")
            closest = duel.best_dist()
            ra, rb = A.tail.latest(max_age=1e9), B.tail.latest(max_age=1e9)
            summary = {
                "contact": duel.contact.is_set(),
                "closest_units": closest,
                "final_records": {"A": ra, "B": rb},
                "final_dy": (rb[2] - ra[2]) if (ra and rb) else None,
                "approach_A": sideA.result, "approach_B": sideB.result,
                "fight": fights,
                "fired": watch.fired,
                "events": watch.events,
                "t_gameplay": t_gameplay,
                "peek_item_rows": {t: dict(c.tail.item_rows) for t, c in (("A", A), ("B", B))},
                "ingame_rows": {"A": len(A.tail.ingame()), "B": len(B.tail.ingame())},
            }
            with open(os.path.join(a.out, "converge.json"), "w") as fh:
                json.dump(summary, fh, indent=1, default=float)
            # One line, and it names the signal. research/18 §3.10: an instrument that emits zero
            # rows is a failed run, so the row counts are on the same line.
            if watch.fired:
                ev = watch.fired
                A.sh.log(f"RESULT PASS signal={ev['kind']} on={ev['tag']} "
                         f"t=T+{ev['t'] - t_gameplay:.1f}s closest={closest} "
                         f"detail={json.dumps(ev['detail'], default=float)} "
                         f"rows A={len(A.tail.ingame())} B={len(B.tail.ingame())}")
            else:
                obs = [e["kind"] for e in watch.events if not e.get("firing")]
                if obs:
                    A.sh.log(f"non-firing observations only: {obs} -- a MediusPlayerReport is a "
                             f"periodic client stats report, not a round boundary")
                A.sh.log(f"RESULT FAIL no kill or round-end signal in {a.kill_timeout}s; "
                         f"closest={closest} contact={duel.contact.is_set()} "
                         f"rows A={len(A.tail.ingame())} B={len(B.tail.ingame())}")
                if a.until_kill:
                    failed = True
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
    if failed:
        raise SystemExit("--until-kill: no kill or round-end signal was observed -- FAIL")


if __name__ == "__main__":
    main()
