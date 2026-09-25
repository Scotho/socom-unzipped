"""R242: the two-instance "speed freeze" re-measured from the ladder streak's existing logs (Sprint 13 H3, 2026-09-25).

The number docs/KNOWN.md section 1 cites in its row "Two instances hold the guest clock at real time through a whole
ladder round set". R242 (plans/2026-09-22-sprint-10-close.md) asked for the speed-freeze half of Goal 4 to be
re-measured from existing logs, with no new run.

Inputs: the fourteen game run logs of the seven streak ladder runs (docs/LADDER.md), both instances, in the data
root's logs/ (git-ignored; the build machine holds them):

    logs/run_{A,B}_<run>.log   for <run> in RUNS below (ladder_20260920_101741 .. ladder_20260923_005745)

Per instance, from READY (the sampler's `t=` >= T0, default 330 s) to the end, dropping the last 30 stats
intervals (the teardown):
  * guest VBlank/s   -- sum of `[gs-gl stats] backpressure ... guest_frames=` over the sum of the stats intervals'
                        `elapsed=` (one guest frame boundary per VBlank, EeScheduler's guestFrameBoundary), with
                        the 5th percentile of the per-interval rate;
  * presents/s       -- the `present=<ms>/<count>` counts over the same time;
  * bp-wait          -- `wait_ms=` as a share of wall time;
  * sampler vsync/s and ee/wall -- `[pc-sampler]`'s `vsync=` and `ee=` against its `t=`, first to last row.
None of these is the game's own frame rate: that is `[vu1-stats]` syncv/s, and no line of it is in any of the
fourteen logs (the ladder sets PS2X_GS_STATS=1 only); the script counts them to say so.

    python tools_py/research/ladder/r242_speed_freeze.py [--root <data root; default $SOCOM_DATA_ROOT or .>] [--t0 330]
"""
import argparse
import os
import re
import statistics

RUNS = ["20260920_101750", "20260921_010154", "20260921_025459", "20260921_041622",
        "20260922_234446", "20260923_001226", "20260923_005755"]
T_RE = re.compile(r"\[pc-sampler\] .*? t=([0-9.]+) vsync=(\d+) ee=([0-9.]+)")
EL_RE = re.compile(r"\[gs-gl stats\] elapsed=(\d+)ms")
PR_RE = re.compile(r"present=[0-9.]+/(\d+)")
BP_RE = re.compile(r"backpressure N=\d+ guest_frames=(\d+) waits=(\d+) wait_ms=([0-9.]+)")
TEARDOWN_INTERVALS = 30


def measure(path, t0):
    t = el = pres = None
    vu1 = 0
    rows = []   # (elapsed_ms, presents, guest_frames, wait_ms)
    first = last = None
    with open(path, "rb") as f:
        for raw in f:
            if b"vu1-stats" in raw:
                vu1 += 1
            if not raw.startswith(b"["):
                continue
            line = raw.decode("utf-8", "replace")
            m = T_RE.search(line)
            if m:
                t = float(m.group(1))
                if t >= t0:
                    row = (t, int(m.group(2)), float(m.group(3)))
                    first = first or row
                    last = row
                continue
            m = EL_RE.search(line)
            if m:
                el = int(m.group(1))
                continue
            m = PR_RE.search(line)
            if m and "calls=" in line:
                pres = int(m.group(1))
                continue
            m = BP_RE.search(line)
            if m and t is not None and t >= t0 and el:
                rows.append((el, pres or 0, int(m.group(1)), float(m.group(3))))
    if len(rows) > 2 * TEARDOWN_INTERVALS:
        rows = rows[:-TEARDOWN_INTERVALS]
    tot_ms = sum(r[0] for r in rows)
    per = sorted(r[2] / (r[0] / 1000.0) for r in rows)
    span = (last[0] - first[0]) if first and last and last[0] > first[0] else 0
    return {
        "vu1": vu1, "window_s": tot_ms / 1000.0,
        "vblank": sum(r[2] for r in rows) / (tot_ms / 1000.0),
        "vblank_p5": per[len(per) // 20] if per else 0.0,
        "presents": sum(r[1] for r in rows) / (tot_ms / 1000.0),
        "wait_pct": sum(r[3] for r in rows) / tot_ms * 100.0,
        "vsync_rate": (last[1] - first[1]) / span if span else 0.0,
        "ee_ratio": (last[2] - first[2]) / span if span else 0.0,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=os.environ.get("SOCOM_DATA_ROOT", "."), help="the tree whose logs/ holds the run logs")
    ap.add_argument("--t0", type=float, default=330.0, help="the sampler time READY is past (s)")
    a = ap.parse_args(argv)
    vb, pr, wt = [], [], []
    for run in RUNS:
        for side in "AB":
            path = os.path.join(a.root, "logs", "run_%s_%s.log" % (side, run))
            if not os.path.exists(path):
                print(run, side, "MISSING", path)
                continue
            m = measure(path, a.t0)
            vb.append(m["vblank"]); pr.append(m["presents"]); wt.append(m["wait_pct"])
            print("%s %s vu1-stats=%d window=%.0fs  guest VBlank/s=%.1f (p5 %.1f)  presents/s=%.1f  bp-wait=%.1f%%  "
                  "sampler vsync/s=%.2f  ee/wall=%.3f" % (run, side, m["vu1"], m["window_s"], m["vblank"], m["vblank_p5"],
                                                          m["presents"], m["wait_pct"], m["vsync_rate"], m["ee_ratio"]))
    if vb:
        print("ALL (%d logs): guest VBlank/s median %.1f min %.1f max %.1f; presents/s median %.1f min %.1f max %.1f; "
              "bp-wait median %.1f%% max %.1f%%" % (len(vb), statistics.median(vb), min(vb), max(vb),
                                                  statistics.median(pr), min(pr), max(pr), statistics.median(wt), max(wt)))
    return 0 if vb else 1


if __name__ == "__main__":
    raise SystemExit(main())
