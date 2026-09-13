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
            for addr, words in self._ITEM.findall(line):
                if int(addr, 16) != self.addr:
                    continue
                vals = [struct.unpack("<f", struct.pack("<I", int(w, 16)))[0]
                        for w in self._WORD.findall(words)]
                if len(vals) >= 3:
                    with self._lock:
                        self.rows.append((t, vals[0], vals[1], vals[2]))
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
    """A reads both players' positions, turns toward B by a timed hold and walks until within
    `arrive` units. Hard-capped by `max_steps` AND `max_seconds` so a mis-calibration cannot run
    the match forever."""
    t_start = time.time()
    A.sh.log(f"walk-to-b: arrive<={arrive} units, <={max_steps} steps, <={max_seconds}s, "
             f"look={LOOK_DEG_PER_S}deg/s walk={WALK_UNITS_PER_S_LONG}u/s R={CAMERA_ORBIT_RADIUS}")
    facing_b, mb = facing_probe(B.sh, tailB, label="B_facing")
    if facing_b is None:
        A.sh.log("walk-to-b: B's facing probe moved nothing -- falling back to the raw record "
                 "(B is then known only to within the orbit radius)")
    facing_a, _ = facing_probe(A.sh, tailA, label="A_facing")
    if facing_a is None:
        A.sh.log("walk-to-b: A's facing probe moved nothing; turning and retrying once")
        turn_by(A.sh, tailA, 90.0)
        facing_a, _ = facing_probe(A.sh, tailA, label="A_facing_retry")
    if facing_a is None:
        A.sh.log("walk-to-b: ABORT -- A never produced a usable heading")
        return {"ok": False, "reason": "no-heading", "steps": 0, "track": []}

    best, track = None, []
    detour_left, detour_sign, blocks = 0, 1.0, 0
    for step in range(max_steps):
        if time.time() - t_start > max_seconds:
            A.sh.log(f"[wtb] STOP -- wall-clock cap {max_seconds}s")
            return {"ok": False, "reason": "time-cap", "steps": step, "best": best, "track": track}
        ra, rb = tailA.latest(), tailB.latest()
        if ra is None or rb is None:
            A.sh.log(f"[wtb] STOP -- stale position rows (A={ra is not None} B={rb is not None})")
            return {"ok": False, "reason": "stale-rows", "steps": step, "best": best, "track": track}
        ax, az = player_pos(ra, facing_a)
        bx, bz = player_pos(rb, facing_b) if facing_b is not None else (rb[1], rb[3])
        dist = math.hypot(bx - ax, bz - az)
        cam_dist = math.hypot(rb[1] - ra[1], rb[3] - ra[3])
        bearing = math.degrees(math.atan2(bz - az, bx - ax))
        # While detouring, aim off the bearing: a straight-line policy cannot leave a spawn that is
        # walled off in B's direction, which is what ours_task7_wtb1 spent 300 s failing to do.
        aim = wrap_deg(bearing + detour_sign * DETOUR_DEG) if detour_left > 0 else bearing
        err = wrap_deg(aim - facing_a)
        best = dist if best is None else min(best, dist)
        track.append({"step": step, "A": [ra[1], ra[2], ra[3]], "B": [rb[1], rb[2], rb[3]],
                      "player_A": [ax, az], "player_B": [bx, bz], "dist": dist,
                      "camera_dist": cam_dist, "facing": facing_a, "bearing": bearing,
                      "aim": aim, "err": err, "detour": detour_left})
        A.sh.log(f"[wtb] step {step:2d} A=({ax:8.2f},{az:8.2f}) B=({bx:8.2f},{bz:8.2f}) "
                 f"dist={dist:8.2f} (cam {cam_dist:8.2f}) facing={facing_a:7.2f} "
                 f"bearing={bearing:7.2f} aim={aim:7.2f} err={err:+7.2f} detour={detour_left}")
        if shots:
            A.sh.shot(f"wtb{step:02d}")
            B.sh.shot(f"wtb{step:02d}")
        if dist <= arrive:
            A.sh.log(f"[wtb] ARRIVED: {dist:.2f} <= {arrive} units after {step} steps")
            return {"ok": True, "reason": "arrived", "steps": step, "dist": dist,
                    "best": best, "track": track}
        # One step = at most one timed turn plus one walk burst. The turn's own arc is a
        # measurement, so no separate re-facing probe is needed: take the fitted sweep when the
        # hold read as a rotation, and the commanded angle when it did not.
        if abs(err) > TURN_DEADBAND_DEG:
            mt = turn_by(A.sh, tailA, err)
            applied = mt["sweep_deg"] if (mt["kind"] == "rotation" and mt["sweep_deg"] is not None) else err
            facing_a = wrap_deg(facing_a + applied)
            track[-1]["turn_applied"] = applied
        want = dist * WALK_STEP_FRACTION / WALK_UNITS_PER_S_LONG
        secs = max(WALK_STEP_MIN_S, min(WALK_STEP_MAX_S, want))
        m = measure_hold(A.sh, tailA, WALK_FORWARD_KEY, secs, settle=WALK_SETTLE_S,
                         rest=WALK_REST_S, label=f"wtb{step:02d}_walk")
        A.sh.log(fmt_hold(m))
        expect = WALK_UNITS_PER_S_LONG * max(m["hold_s"] - TURN_HOLD_LEAD_S, 0.0)
        good = (m["scale_ok"] and m["heading"] is not None
                and m["dist"] >= WALK_PROGRESS_FRACTION * expect
                and m["straight"] >= WALK_STRAIGHT_MIN)
        track[-1]["walk"] = {"dist": m["dist"], "straight": m["straight"], "expect": expect,
                             "scale_ok": m["scale_ok"], "believed": good}
        if good:
            facing_a = m["heading"]                      # measured truth beats dead reckoning
            detour_left = max(0, detour_left - 1)
            blocks = 0
        else:
            # Blocked, or measured through a lag freeze. Either way the heading this burst reports
            # is not the direction the player is pointed, so KEEP the dead-reckoned facing.
            why = ("scale" if not m["scale_ok"] else
                   "short" if m["dist"] is not None and m["dist"] < WALK_PROGRESS_FRACTION * expect
                   else "curved")
            A.sh.log(f"[wtb] step {step} burst not believed ({why}): moved {m['dist']} of "
                     f"{expect:.0f} expected, straightness {m['straight']} -- heading kept at "
                     f"{facing_a:.2f}, detouring")
            blocks += 1
            if blocks % (DETOUR_STEPS + 1) == 0:
                detour_sign = -detour_sign                # that side stayed blocked: try the other
                A.sh.log(f"[wtb] {blocks} blocked bursts in a row -- detouring the other way")
            detour_left = DETOUR_STEPS
            measure_hold(A.sh, tailA, WALK_BACK_KEY, UNSTICK_BACK_S, settle=WALK_SETTLE_S,
                         rest=WALK_REST_S, label=f"wtb{step:02d}_unstick_back")
            side = LATERAL_RIGHT_KEY if detour_sign > 0 else LATERAL_LEFT_KEY
            measure_hold(A.sh, tailA, side, UNSTICK_LATERAL_UNITS / LATERAL_UNITS_PER_S,
                         settle=WALK_SETTLE_S, rest=WALK_REST_S,
                         label=f"wtb{step:02d}_unstick_side")
    A.sh.log(f"[wtb] STOP -- step cap {max_steps} reached, best distance {best}")
    return {"ok": False, "reason": "step-cap", "steps": max_steps, "best": best, "track": track}


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
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower().count("socom2.exe"):
        raise SystemExit("socom2.exe is already running")
    A = Client("A", a.out, a.name_a, True, a.seconds)
    B = Client("B", a.out, a.name_b, a.existing_b, a.seconds)
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
        if a.calibrate or a.walk_to_b:
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


if __name__ == "__main__":
    main()
