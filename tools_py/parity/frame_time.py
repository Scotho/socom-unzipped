"""The mission stage's frame time, read from the `[pc-sampler]` rows of its game log (Sprint 13 Task V4).

What "a frame" is here. The sampler (PS2X_PC_SAMPLER=1, which the gate's mission stage sets) prints one row a
second with the FreezeFields (socom2_freeze_fields.h): `t=` is host seconds since the sampler's epoch and
`vsync=` is the guest VBlank count (EeScheduler::currentVSyncTick). The guest's VBlank is paced by the host:
when the GL replay falls behind, the GS back-pressure holds the EE at its sync and `vsync=` slows while
`bp_wait_ms=` climbs (research/34; KNOWN §1's two-instance clock row reads the same two fields). So one guest
VBlank is one frame the port delivered, and the frame time of a sampler window is

    host ms per guest VBlank = (t[i+1] - t[i]) * 1000 / (vsync[i+1] - vsync[i])

which is 16.67 at the console's 60. Not used: `ee=` (the EE clock follows the host minus the back-pressure
wait and reads ~1.00x even while the frame rate halves), `seq=` (the kernel snapshot's sequence, a staleness
marker, not a frame count), the `[gs-gl present]` lines (every 600th frame, no timestamp) and `[vu1-stats]`
syncv/s (the game's own draw rate; the gate does not set PS2X_VU1_STATS).

The stretch is the HUD-reached one: sampler rows with `t=` at or after the drive log's step that follows the
HUD untilref match (s28 in gameplay_probe.txt), to the log's last row -- the drive's scripted walk and the
stage's tail after it. The drive's `t=` counts from just after the launch and the sampler's from after the
runtime's start, so a drive time used as a sampler time lands at or a little after the HUD, never before it.

    mean  = total host ms over the stretch / total VBlanks over it
    worst = the slowest sampler window's host ms per VBlank; a window in which vsync did not move is folded
            into the next one that did, so a stall reads as the long frame it was (the cadence is one
            second: a single frame shorter than that is not resolved -- this is the worst one-second mean)
    n     = VBlanks over the stretch

    python -m tools_py.parity.frame_time <stamp dir> [<stamp dir> ...]
"""
import os
import re
import sys
from collections import namedtuple

HUD_REF_NAME = "ref_hud_ours.png"        # gate.HUD_REF_NAME; a test holds the two equal
SAMPLER_RE = re.compile(r"\[pc-sampler\].*?\bt=([0-9]+(?:\.[0-9]+)?) vsync=([0-9]+)\b")
STEP_RE = re.compile(r"^s\d\d_\S+\s+t=\s*([0-9]+(?:\.[0-9]+)?)s", re.M)

FrameTime = namedtuple("FrameTime", "mean_ms worst_ms n windows start_t")


def hud_start(drive_text, hud_ref=HUD_REF_NAME):
    """The drive `t=` of the first step after the HUD untilref matched, or None (never matched, or no step
    after it)."""
    m = re.search(r"untilref\([^)]*%s[^)]*\):.*matched=True" % re.escape(hud_ref), drive_text)
    if not m:
        return None
    step = STEP_RE.search(drive_text, m.end())
    return float(step.group(1)) if step else None


def samples(lines):
    """[(t, vsync)] from the `[pc-sampler]` rows, in log order."""
    out = []
    for line in lines:
        m = SAMPLER_RE.search(line)
        if m:
            out.append((float(m.group(1)), int(m.group(2))))
    return out


def measure(rows, start_t):
    """FrameTime over the rows at or after `start_t`, or None when fewer than two rows or no VBlank."""
    rows = [(t, v) for t, v in rows if t >= start_t]
    if len(rows) < 2:
        return None
    n = rows[-1][1] - rows[0][1]
    if n <= 0:
        return None
    mean = (rows[-1][0] - rows[0][0]) * 1000.0 / n
    worst, held, windows = 0.0, 0.0, 0
    for (t0, v0), (t1, v1) in zip(rows, rows[1:]):
        held += t1 - t0
        if v1 > v0:
            worst = max(worst, held * 1000.0 / (v1 - v0))
            held = 0.0
            windows += 1
    if held > 0.0:                      # the stretch ended in a stall: at least that long a frame
        worst = max(worst, held * 1000.0)
    return FrameTime(mean, worst, n, windows, rows[0][0])


def read(drive_log, game_log):
    """(FrameTime, None) or (None, why) for a mission stage's drive log and game log."""
    try:
        with open(drive_log, encoding="utf-8", errors="replace") as f:
            start = hud_start(f.read())
    except (OSError, TypeError) as e:
        return None, "no drive log (%s)" % e
    if start is None:
        return None, "HUD not reached in the drive log"
    try:
        with open(game_log, encoding="utf-8", errors="replace") as f:
            rows = samples(f)
    except (OSError, TypeError) as e:
        return None, "no game log (%s)" % e
    if not rows:
        return None, "no [pc-sampler] rows in the game log"
    ft = measure(rows, start)
    if ft is None:
        return None, "fewer than two moving [pc-sampler] rows after the HUD (t >= %.1f s)" % start
    return ft, None


def read_stamp(stamp_dir):
    """read() over a gate stamp's mission.drive.log and mission.game.log."""
    return read(os.path.join(stamp_dir, "mission.drive.log"), os.path.join(stamp_dir, "mission.game.log"))


def line(ft, why=None):
    """The summary's FRAME line."""
    if ft is None:
        return "FRAME NO-DATA (%s)" % why
    return ("FRAME mean=%.2f worst=%.2f n=%d (host ms per guest VBlank, [pc-sampler] t=/vsync= from t=%.1f s "
            "after the HUD, %d windows)" % (ft.mean_ms, ft.worst_ms, ft.n, ft.start_t, ft.windows))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m tools_py.parity.frame_time <stamp dir> [<stamp dir> ...]")
        return 2
    rc = 0
    for stamp in argv:
        ft, why = read_stamp(stamp)
        print("%s %s" % (os.path.basename(os.path.normpath(stamp)), line(ft, why)))
        rc |= 0 if ft else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
