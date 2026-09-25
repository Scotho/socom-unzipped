"""Sprint 5 Task 2 Step 1 -- validate the at-rest facing estimate offline (zero game runs).

Task 5 will need to know which way a standing-still player faces. The candidate estimate is
`atan2(actor - camera)` in the ground plane (x, z; y is up -- verified below against the decompiled
layout), taken from the last actor and camera peek rows at or before a forward probe's start event.
This checks that estimate against Sprint 4's own logs: each forward probe's start->release
displacement is ground truth for the facing the player must have had to walk that way.

    python -m tools_py.parity.facing_check [--runs kill1,kill2,kill3] [--root .]

Reuses `tools_py.parity.verdict_core`'s `parse_log` and `forward_holds` (imported, not
reimplemented); does not modify that module. Everything else here (camera extraction, the rest/
staleness gates, the bearing arithmetic) is new to this check.

Row layout, verified against `run_A_20260912_231341.log:9259`: the actor block (word 0 ==
`ACTOR_VTABLE`) has x/y/z at words 7/8/9 (`+0x1c/+0x20/+0x24`) -- `4406d542(539.332)
431f3900(159.223) 44b5f47f(1455.64)`; the camera item at the fixed address `0x416054` on the same
line is `44077315(541.798) 4338b3e2(184.703) 44b8f69f(1479.71)`. Ground-plane separation there is
~24.2 with a ~25.5 height gap -- the same shape as research/18 4.11's kill2 mean (ground radius
20.65 sd 5.17, height 19.73), so x/z is the ground plane and y is up, as the brief says to verify.

Blind class: the samples are Medley-only (READERC.ZAR names "Medley" a playlist, not this map --
do not assert the map name) and from open ground; camera collision near walls is unsampled.
"""
import argparse
import bisect
import math
import os
import statistics
import sys
from dataclasses import dataclass, field

# THIS MODULE READS THE r0001 COLUMN ONLY (Sprint 11 Task 19, review F7). `CAMERA_RECORD_ADDR` is the
# r0001 scalar, and the actor is located by an exact match on it, so an r0004 log re-read here comes
# back empty rather than wrong. It is a hand tool -- no script under scripts/ invokes it -- so the fix
# when somebody wants it on r0004 is `verdict_core.CAMERA_RECORD_ADDRS`, the same membership the round
# readers use.
from tools_py.parity.verdict_core import (
    CAMERA_RECORD_ADDR,
    FORWARD_HOLD_MIN_S,
    ROW_MAX_GAP_S,
    f32,
    forward_holds,
    parse_log,
)

# ---------------------------------------------------------------------------------------------
# constants -- each with the measurement or the rule behind it
# ---------------------------------------------------------------------------------------------
# A hold shorter than this is not a scoreable forward probe -- verdict_core's own bar
# (FORWARD_HOLD_MIN_S): the shortest hold it scores on kill2 measured 1.46-1.51s from pad events.
MIN_HOLD_S = FORWARD_HOLD_MIN_S

# "At rest" before the probe: net ground-plane actor displacement over the REST_WINDOW_S before
# hold start must be below REST_MAX_DRIFT_UNITS. Reuses verdict_core's own drift window/bar
# (CONTROL_DRIFT_WINDOW_S / CONTROL_DRIFT_MAX_UNITS = 10s / 5 units) rather than inventing a new
# number for the same idea.
REST_WINDOW_S = 10.0
REST_MAX_DRIFT_UNITS = 5.0

# Camera staleness (KNOWN.md, 2026-09-13 retraction, kill3 B): the camera record can freeze --
# bit-exact, not jitter -- while the actor keeps moving. Over the REST_WINDOW_S before hold start:
# if every camera row is within STALE_CAMERA_EPS of the first (a bit-exact freeze) while the
# actor's own path length (sum of consecutive displacements, NOT net -- net can cancel a
# back-and-forth) is at least STALE_ACTOR_PATH_MIN_UNITS, the sample is excluded as stale. The bar
# is set low on purpose (this checks for the failure mode, not for how big the kill3 episode was --
# that one ran 24.25s and ~65/~39 units either side of it).
STALE_CAMERA_EPS = 1e-6
STALE_ACTOR_PATH_MIN_UNITS = 1.0

# A start->release displacement below this is too small to carry a bearing -- excluded as
# degenerate rather than folded into the error distribution as noise.
MIN_TRUTH_DISPLACEMENT_UNITS = 3.0

# Task 5's adoption bar (task-2-brief.md Step 1).
P90_ADOPT_DEG = 5.0

BLIND_CLASS = (
    "Medley-only, open ground; camera collision near walls is unsampled. (\"Medley\" is READERC.ZAR's "
    "playlist label, not an asserted map name.)"
)

REASON_HOLD_TOO_SHORT = "hold too short"
REASON_NO_ROW_AT_START = "no camera/actor row at/before hold start"
REASON_NO_ROW_AT_RELEASE = "no actor row at/before release"
REASON_STALE_CAMERA = "camera stale before hold start"
REASON_REPOINTED = "actor block re-pointed during rest window"
REASON_INSUFFICIENT_REST_ROWS = "insufficient actor rows to confirm rest"
REASON_NOT_AT_REST = "not at rest"
REASON_DEGENERATE = "displacement too small (degenerate)"

DEFAULT_RUNS = [
    ("kill1", "logs/run_A_20260912_230022.log", "logs/run_B_20260912_230022.log"),
    ("kill2", "logs/run_A_20260912_231341.log", "logs/run_B_20260912_231341.log"),
    ("kill3", "logs/run_A_20260912_232834.log", "logs/run_B_20260912_232834.log"),
]


@dataclass
class Sample:
    run: str
    side: str
    t: float                     # hold start time
    used: bool = False
    reason: str = ""
    detail: str = ""
    stale: object = None         # True / False / None (not enough rows in the window to tell)
    estimate_deg: object = None
    truth_deg: object = None
    error_deg: object = None     # signed, wrapped to +-180
    camera_radius: object = None


# ---------------------------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------------------------
def wrap_deg(a):
    return (a + 180.0) % 360.0 - 180.0


def last_at_or_before(rows, t):
    """rows: sorted [(t, ...)]. The row at/before t, or None."""
    times = [r[0] for r in rows]
    k = bisect.bisect_right(times, t) - 1
    return rows[k] if k >= 0 else None


def rows_in_window(rows, t0, t1):
    times = [r[0] for r in rows]
    lo = bisect.bisect_left(times, t0)
    hi = bisect.bisect_right(times, t1)
    return rows[lo:hi]


def camera_series_from_peek(peek_rows):
    """[(t, x, y, z)] for the fixed camera-record address. Content-identified the same way
    parse_log identifies the actor: the item at CAMERA_RECORD_ADDR, skipping all-zero (not yet
    populated) rows -- the same convention parse_log itself uses for actor_rows."""
    out = []
    for t, items in peek_rows:
        item = next((w for a, w in items if a == CAMERA_RECORD_ADDR), None)
        if item and len(item) >= 3:
            x, y, z = f32(item[0]), f32(item[1]), f32(item[2])
            if x or y or z:
                out.append((t, x, y, z))
    return out


def path_length(rows):
    """Sum of consecutive 3-D displacements -- catches back-and-forth motion that nets near zero."""
    return sum(math.dist(a[1:4], b[1:4]) for a, b in zip(rows, rows[1:]))


def camera_frozen(rows):
    """True if every row's (x, y, z) is within STALE_CAMERA_EPS of the first row -- a bit-exact
    freeze, not a jitter tolerance. None when there are fewer than 2 rows to compare."""
    if len(rows) < 2:
        return None
    x0, y0, z0 = rows[0][1], rows[0][2], rows[0][3]
    return all(
        abs(x - x0) <= STALE_CAMERA_EPS and abs(y - y0) <= STALE_CAMERA_EPS and abs(z - z0) <= STALE_CAMERA_EPS
        for _, x, y, z in rows
    )


def check_stale(camera_series, actor_series, t0, t1):
    """(stale, detail) over the window [t0, t1]. stale is True / False / None (not enough rows to
    tell either way, in which case it does NOT count as an exclusion by itself)."""
    cam = rows_in_window(camera_series, t0, t1)
    act = rows_in_window(actor_series, t0, t1)
    frozen = camera_frozen(cam)
    if frozen is None or len(act) < 2:
        return None, f"cam_rows={len(cam)} actor_rows={len(act)} (insufficient to tell)"
    moved = path_length(act)
    stale = bool(frozen and moved >= STALE_ACTOR_PATH_MIN_UNITS)
    return stale, f"cam_rows={len(cam)} frozen={frozen} actor_path={moved:.2f}"


def build_sample(run, side, actor_series, camera_series, hold):
    s = Sample(run=run, side=side, t=hold.start)

    cam = last_at_or_before(camera_series, hold.start)
    act_start = last_at_or_before(actor_series, hold.start)
    if cam is None or act_start is None:
        s.reason = REASON_NO_ROW_AT_START
        s.detail = "no row at all"
        return s
    if hold.start - act_start[0] > ROW_MAX_GAP_S or hold.start - cam[0] > ROW_MAX_GAP_S:
        s.reason = REASON_NO_ROW_AT_START
        s.detail = f"nearest row {max(hold.start - act_start[0], hold.start - cam[0]):.2f}s before start"
        return s

    act_release = last_at_or_before(actor_series, hold.release)
    if act_release is None:
        s.reason = REASON_NO_ROW_AT_RELEASE
        s.detail = "no row at all"
        return s
    if hold.release - act_release[0] > ROW_MAX_GAP_S:
        s.reason = REASON_NO_ROW_AT_RELEASE
        s.detail = f"nearest row {hold.release - act_release[0]:.2f}s before release"
        return s

    stale, detail = check_stale(camera_series, actor_series, hold.start - REST_WINDOW_S, hold.start)
    s.stale = stale
    if stale:
        s.reason = REASON_STALE_CAMERA
        s.detail = detail
        return s

    win = rows_in_window(actor_series, hold.start - REST_WINDOW_S, hold.start)
    if len(win) < 2:
        s.reason = REASON_INSUFFICIENT_REST_ROWS
        s.detail = f"rows={len(win)}"
        return s
    addrs = {r[4] for r in win if len(r) > 4 and r[4] is not None}
    if len(addrs) > 1:
        s.reason = REASON_REPOINTED
        s.detail = f"addrs={[hex(a) for a in sorted(addrs)]}"
        return s
    drift = math.hypot(win[-1][1] - win[0][1], win[-1][3] - win[0][3])
    if drift > REST_MAX_DRIFT_UNITS:
        s.reason = REASON_NOT_AT_REST
        s.detail = f"drift={drift:.2f} > {REST_MAX_DRIFT_UNITS:g}"
        return s

    dx_t, dz_t = act_release[1] - act_start[1], act_release[3] - act_start[3]
    truth_mag = math.hypot(dx_t, dz_t)
    if truth_mag < MIN_TRUTH_DISPLACEMENT_UNITS:
        s.reason = REASON_DEGENERATE
        s.detail = f"disp={truth_mag:.2f} < {MIN_TRUTH_DISPLACEMENT_UNITS:g}"
        return s

    cx, cz = cam[1], cam[3]
    ax, az = act_start[1], act_start[3]
    estimate = math.degrees(math.atan2(az - cz, ax - cx))
    truth = math.degrees(math.atan2(dz_t, dx_t))

    s.estimate_deg = estimate
    s.truth_deg = truth
    s.error_deg = wrap_deg(estimate - truth)
    s.camera_radius = math.hypot(ax - cx, az - cz)
    s.used = True
    return s


def analyze_log(lines, run, side):
    """[Sample, ...] for every forward hold in one instance's run log."""
    p = parse_log(lines)
    actor_series = p.actor_rows
    camera_series = camera_series_from_peek(p.peek_rows)
    samples = []
    for h in forward_holds(p.pad_events):
        if h.release - h.start < MIN_HOLD_S:
            samples.append(
                Sample(
                    run=run, side=side, t=h.start, reason=REASON_HOLD_TOO_SHORT,
                    detail=f"{h.release - h.start:.2f}s < {MIN_HOLD_S:g}s",
                )
            )
            continue
        samples.append(build_sample(run, side, actor_series, camera_series, h))
    return samples


# ---------------------------------------------------------------------------------------------
# aggregation and reporting
# ---------------------------------------------------------------------------------------------
def _percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def summarize(samples):
    used = [s for s in samples if s.used]
    excluded = [s for s in samples if not s.used]
    reasons = {}
    for s in excluded:
        reasons[s.reason] = reasons.get(s.reason, 0) + 1
    errs = sorted(abs(s.error_deg) for s in used)
    return {
        "n_used": len(used),
        "n_excluded": len(excluded),
        "reasons": reasons,
        "mean": statistics.mean(errs) if errs else None,
        "median": statistics.median(errs) if errs else None,
        "p90": _percentile(errs, 0.90),
        "max": max(errs) if errs else None,
    }


def sign_convention_report(used):
    if not used:
        return "sign convention: no used samples to judge"
    near0 = [s for s in used if abs(s.error_deg) <= 90.0]
    near180 = [s for s in used if abs(s.error_deg) > 90.0]
    if not near180:
        return f"sign convention: consistent, near 0 deg ({len(near0)}/{len(used)} within +-90 deg)"
    if not near0:
        spread = statistics.mean(180.0 - abs(s.error_deg) for s in near180)
        return (
            f"sign convention: consistent constant ~180 deg offset (mirrored: use atan2(camera - actor) "
            f"instead) -- all {len(near180)}/{len(used)} samples beyond +-90 deg, mean |180 - |error|| "
            f"= {spread:.1f} deg"
        )
    return (
        f"sign convention: NOT a constant offset -- {len(near0)}/{len(used)} near 0 deg, "
        f"{len(near180)}/{len(used)} near 180 deg (mirrors by sample, not by a fixed convention)"
    )


def format_sample(s):
    head = f"[{s.run}/{s.side}] t={s.t:8.2f}s"
    if s.used:
        return (
            f"{head}  estimate={s.estimate_deg:7.2f}  truth={s.truth_deg:7.2f}  "
            f"error={s.error_deg:+7.2f}  camR={s.camera_radius:6.2f}  stale={s.stale}"
        )
    detail = f" ({s.detail})" if s.detail else ""
    return f"{head}  EXCLUDED: {s.reason}{detail}  stale={s.stale}"


def read_lines(path):
    with open(path, "r", errors="replace") as f:
        return f.read().split("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m tools_py.parity.facing_check",
        description="Sprint 5 Task 2 Step 1: at-rest facing estimate vs forward-probe displacement, offline.",
    )
    ap.add_argument("--runs", default="kill1,kill2,kill3", help="comma list of run labels to include")
    ap.add_argument("--root", default=".", help="directory the default log paths are relative to")
    args = ap.parse_args(argv)
    labels = set(args.runs.split(","))

    all_samples = []
    for run, pa, pb in DEFAULT_RUNS:
        if run not in labels:
            continue
        for side, path in (("A", pa), ("B", pb)):
            full = os.path.join(args.root, path)
            try:
                lines = read_lines(full)
            except OSError as e:
                print(f"cannot read {full}: {e}")
                continue
            all_samples.extend(analyze_log(lines, run, side))

    for s in all_samples:
        print(format_sample(s))

    stats = summarize(all_samples)
    used = [s for s in all_samples if s.used]
    print()
    print(f"n used = {stats['n_used']}   n excluded = {stats['n_excluded']}")
    for reason, n in sorted(stats["reasons"].items()):
        print(f"  excluded: {reason}: {n}")
    if stats["n_used"]:
        print(f"mean |error|   = {stats['mean']:.2f} deg")
        print(f"median |error| = {stats['median']:.2f} deg")
        print(f"p90 |error|    = {stats['p90']:.2f} deg")
        print(f"max |error|    = {stats['max']:.2f} deg")
        print(sign_convention_report(used))
        adopt = stats["p90"] <= P90_ADOPT_DEG
        cmp_sym = "<=" if adopt else ">"
        print(f"VERDICT: {'ADOPT' if adopt else 'DO NOT ADOPT'} (p90 {stats['p90']:.2f} deg {cmp_sym} {P90_ADOPT_DEG:g} deg bar)")
    else:
        adopt = False
        print("VERDICT: NO-DATA (no usable samples)")
    print(f"blind class: {BLIND_CLASS}")
    return 0 if (stats["n_used"] and adopt) else 1


if __name__ == "__main__":
    sys.exit(main())
