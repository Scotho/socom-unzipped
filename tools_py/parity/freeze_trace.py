"""Sprint 6 Task 3 Step 1 (lock-free) -- freeze_trace: where and for how long an instance's guest round clock stood
still, with the main thread's sampled PC and the NetIdle idle-ms logged inside each stall.

KNOWN.md section 4, "Online instances freeze for 3-17 s under host load" (launch 8c): the round clock stops, the main
thread parks at 0x3b00a4, memory is flat; the OTHER side's NetIdle then alarms (peaks 8217 / 10338 ms). This module
turns one run log into the list of those stalls so the reproduction is a number, not a recollection.

PURE: `windows(lines)` takes an iterable of log lines and returns dicts; the CLI does the IO.

Row conventions (the exe's own formats, see verdict_core / sp_death_probe):
  * `[peek] @<addr>: <hex8>(<float>) ...`  -- one row per PS2X_PC_SAMPLER period, NOT host-timestamped. The guest
    round clock is the float DAT_004365c0 (verdict_core.ROUND_TIME_ADDR; counts up from 0 at round start); the round
    clock STRING is the ASCII at 0x408f10 (two words). The float is used when peeked, else the string.
  * `[pc-sampler] live pc=0x.. ra=.. sp=.. running=<id> threads: [<id> pc=0x.. ra=.. sp=.. st=<s> wait=<r>/<id>] ...`
    -- printed just before each peek row by the same sampler thread; thread 1 is the main guest thread (its sp is the
    initial stack), so `main_pc` is thread 1's pc. `running` is the running thread id (0 = none: the guest is idle).
  * `[call] <t>s <Name> #<n> ...` / `[ret] <Name> #<n> v0=0x<hex> ...` -- PS2X_CALL_TRACE. `NetIdle` (0x30cd80) returns
    the idle milliseconds in v0 (research/18 3.12); its peak inside a window is `netidle_peak_ms`. Every stamped
    `[call]` anchors host time for the rows around it (verdict_core._make_clock), so a stall's seconds follow the real
    sampler period, which drifts under load (KNOWN.md "The peek sampler's period is not constant under load").
  * A line can be torn: two threads print at once and a `[call]` lands on the tail of a `[pc-sampler]` line (8c A has
    one). Lines are split at every tag boundary before reading.

A WINDOW is a maximal run of consecutive rows whose clock value is bit-identical, whose host span (last row's time
minus first row's) is >= `min_stall_s`. No merging across a single advancing row (verdict_core.clock_pauses does
that for the harness's freeze definition); no round-boundary exclusion -- the lobby (clock 0.0 before the first
round) and the ~5.5 s round boundaries are listed too, and marked in the CLI. Blind: a stall that begins between two
rows is measured from the first still row, so a window under-reads the true stall by up to one period.

Measured reproduction (launch 8c, 2026-09-15, this module at Sprint 6 Task 3 Step 1), the commands:

    python -m tools_py.parity.freeze_trace logs/run_A_20260913_132843.log --peer logs/run_B_20260913_132843.log
    python -m tools_py.parity.freeze_trace logs/run_B_20260913_132843.log --peer logs/run_A_20260913_132843.log

(min_stall_s 2.0; host s on each instance's own epoch; "main PC" = thread 1's most common sampled pc with its share
of the window's samples, and thread 1's state; "NetIdle peak" = the largest NetIdle v0 logged INSIDE the window on
the same instance; "peer peak" = the other log's largest NetIdle over [t_start, t_end + 10 s] on the peer's epoch)

  side  start row  rows  host s           stall    clock (held -> next)  main PC                                NetIdle peak  peer peak
  A        0       1669  1.43-418.88      417.45s  0.000 -> 0.150        0x3b00a4 (45 pct, st=2 wait=4, idle 86 pct)  184 ms    1341 ms   lobby / pre-round
  A     1994         21  500.71-505.63      4.92s  54.402 -> 55.487      0x3b00a4 (100 pct, st=2 wait=4, idle 100 pct)  -       7145 ms   KNOWN.md's 8c freeze (first half)
  A     2016         32  506.13-514.07      7.94s  55.587 -> 55.703      0x3b00a4 (100 pct, st=2 wait=4, idle 100 pct)  0 ms    7145 ms   ... second half (one advancing row between)
  A     2182         41  547.90-557.83      9.93s  78.381 -> 78.431      0x1a3b68 (100 pct, st=0 RUNNING; live pc 0x350d90 ra 0x33aa1c on all 41 samples)  0 ms  10338 ms
  A     3118         23  783.34-788.88      5.54s  212.454 -> 212.604    0x3aff80 (43 pct) / 0x3b00a4 (35 pct), idle 83 pct  72 ms     1052 ms   round boundary (5.54 s, KNOWN.md)
  B        0       1646  1.68-413.07      411.40s  0.000 -> 0.183        0x3b00a4 (46 pct, st=2 wait=4, idle 87 pct)  0 ms      1502 ms   lobby / pre-round
  B     1974         19  495.66-500.13      4.46s  57.882 -> 57.932      0x635898 (100 pct, st=0 RUNNING; live pc 0x33aab0 on all 19)  746 ms  99 ms
  B     2450         14  615.17-618.47      3.30s  136.655 -> 140.089    0x1a3b68 (93 pct, st=0 RUNNING; live pc 0x350d90 on all 14)  -    2715 ms   clock jumps 3.4 s after: guest ran, rows stale
  B     2473         69  621.01-638.27     17.26s  141.603 -> 141.653    0x3b00a4 (100 pct, st=2 wait=4, idle 100 pct)  -       8217 ms   KNOWN.md's worst (17.3 s)
  B     3095         23  777.52-782.92      5.40s  225.809 -> 225.959    0x3b00a4 (48 pct, st=2 wait=4, idle 91 pct)  -       862 ms    round boundary
  summary: A windows=5 longest=417.45s stalled_rows=1786; B windows=5 longest=411.40s stalled_rows=1771

Read-out. (1) The two KNOWN.md freezes reproduce to the row: A 500.71-505.63 + 506.13-514.07 (research/21's "one freeze
with one advancing row"), B 621.01-638.27 = 17.26 s; both with thread 1 at 0x3b00a4 st=2 wait=4 and running=0 on every
sample, and the peer's NetIdle climbing to 7145 / 8217 ms. (2) The 10338 ms peer peak belongs to A's 547.90-557.83 window,
which is a DIFFERENT shape: thread 1 is RUNNING (st=0) and the live pc reads 0x350d90 (ra 0x33aa1c) on all 41 samples --
the guest was executing, not waiting, and its clock did not move for 9.9 s; B's 615.17 window is the same shape and the
clock then jumps 3.4 s, so at least that one is the sampler reading stale rows while the guest ran. (3) NetIdle inside a
frozen instance's own window is 0 or absent -- the frozen side does not call it; the alarm is always the peer's.
(4) The lobby and the ~5.5 s round boundaries appear as windows by construction (no round-step exclusion here).
"""
import bisect
import collections
import re
import struct
import sys

from tools_py.parity import verdict_core as vc

# BOTH r0001 SCALARS, on purpose (Task 19, review F7): this watcher is the ladder's, the ladder runs on
# the r0001 build, and the clock is matched by an address RANGE here rather than by membership -- an
# r0004 log read through it comes back empty, never wrong. `verdict_core.ROUND_TIME_ADDRS` /
# `CLOCK_STRING_ADDRS` are what it would take.
ROUND_TIME_ADDR = vc.ROUND_TIME_ADDR         # 0x4365c0 float
CLOCK_STRING_ADDR = vc.CLOCK_STRING_ADDR     # 0x408f10 ascii
MAIN_THREAD_ID = 1
DEFAULT_MIN_STALL_S = 2.0

_TAGS = ("peek", "pc-sampler", "call", "ret")
_SPLIT = re.compile(r"(?=\[(?:%s)\] )" % "|".join(re.escape(t) for t in _TAGS))
_SAMPLER = re.compile(r"^\[pc-sampler\] live pc=0x([0-9a-fA-F]+).*? running=(-?\d+) threads:(.*)$")
# Sprint 7 Task 2e (research/29 section 4 items 1-8): the freeze fields the sampler gained, all optional so a log
# from before the change still parses. `t`/`ee` are seconds, `dpc` hex, `net_wait` is "<0|1>/<cumulative ms>".
# #34 (Sprint 13 V7) added `net_park` = "<threads parked in a libnetb recv>/<cumulative ms>".
_FIELD_FLOAT = ("t", "ee")
_FIELD_INT = ("vsync", "seq", "idle", "bp_pending", "bp_waiters", "bp_wait_ms")
_FIELDS = re.compile(r"\b(t|vsync|ee|seq|dpc|idle|bp_pending|bp_waiters|bp_wait_ms|net_wait|net_park)="
                     r"(0x[0-9a-fA-F]+|\d+/\d+|-?\d+(?:\.\d+)?)")
FREEZE_FIELDS = _FIELD_FLOAT + _FIELD_INT + ("dpc", "net_wait", "net_wait_ms", "net_park", "net_park_ms")
# Sprint 7 Task 2a put a prio= field between st= and wait= in the thread table; a log from before it has none,
# so the field is optional here and BOTH shapes of log read the same (without this the table parses as empty).
_THREAD = re.compile(r"\[(\d+) pc=0x([0-9a-fA-F]+) ra=0x[0-9a-fA-F]+ sp=0x[0-9a-fA-F]+ st=(\d+)"
                     r"(?: prio=-?\d+)? wait=(\d+)/(\d+)\]")


def _segments(raw):
    """A log line split at every tag boundary (torn lines carry two records)."""
    line = raw.rstrip("\r\n")
    return [s for s in _SPLIT.split(line) if s]


def _row_clock(items):
    """(value, source) of the guest round clock on one row: the float at 0x4365c0, else the string at 0x408f10."""
    w = None
    for a, words in items:                        # sp_death_probe.word_at: whichever item covers the address
        if a <= ROUND_TIME_ADDR < a + 4 * len(words) and (ROUND_TIME_ADDR - a) % 4 == 0:
            w = words[(ROUND_TIME_ADDR - a) // 4]
            break
    if w is not None:
        return vc.f32(w), "float@0x4365c0"
    s = vc.row_clock_string(items, CLOCK_STRING_ADDR)
    if isinstance(s, str):
        return s, "string@0x408f10"
    return None, None


def _sampler_fields(seg):
    """The freeze fields of one [pc-sampler] segment; every key is present, None when the line predates them."""
    out = {k: None for k in FREEZE_FIELDS}
    for key, raw in _FIELDS.findall(seg):
        if key == "dpc":
            out["dpc"] = int(raw, 16)
        elif key in ("net_wait", "net_park"):
            flag, _, ms = raw.partition("/")
            out[key] = int(flag)
            out[key + "_ms"] = int(ms)
        elif key in _FIELD_FLOAT:
            out[key] = float(raw)
        else:
            out[key] = int(raw)
    return out


def parse(lines):
    """-> [row] for every [pc-sampler] line, in order: live_pc, running, threads {tid: (pc, st, wait)} and the
    Sprint 7 freeze fields (t, vsync, ee, seq, dpc, idle, bp_pending, bp_waiters, bp_wait_ms, net_wait,
    net_wait_ms) and #34's net_park, net_park_ms, each None on a log written before the sampler printed them. classify() reads these rows."""
    rows = []
    for raw in lines:
        for seg in _segments(raw):
            if not seg.startswith("[pc-sampler] "):
                continue
            m = _SAMPLER.match(seg)
            if not m:
                continue
            row = {"live_pc": int(m.group(1), 16), "running": int(m.group(2)),
                   "threads": {int(tid): (int(pc, 16), int(st), int(wr))
                               for tid, pc, st, wr, _ in _THREAD.findall(m.group(3))}}
            row.update(_sampler_fields(seg))
            rows.append(row)
    return rows


def _flat(rows, key):
    """True when every row carries `key` and they are all equal (>= 2 rows)."""
    vals = [r.get(key) for r in rows]
    return len(vals) >= 2 and all(v is not None and v == vals[0] for v in vals)


def _climbing(rows, key):
    vals = [r.get(key) for r in rows if r.get(key) is not None]
    return len(vals) >= 2 and vals[-1] > vals[0]


def classify(rows):
    """Which of research/29's two freeze shapes a window of sampler rows is, from the fields alone:
      "net-wait"          -- seq frozen, dpc frozen, net_wait=1: the guest is inside the blocking libnetb
                             waitReadable poll (shape 2); no guest instruction runs, the thread table is stale.
      "net-park"          -- net_park >= 1 on every row with vsync and seq climbing: since #34 a guest thread is
                             parked in a libnetb recv on a quiet peer while the executor runs (shape 2 bounded).
      "host-load"         -- vsync flat, a producer inside the GS back-pressure wait (bp_waiters >= 1) and
                             bp_wait_ms climbing: the GL thread is starved by the host (shape 1, by design).
      "runtime-oversleep" -- vsync flat, nobody in the back-pressure wait, idle climbing: the EE executor is
                             sitting in waitForEvent (shape 1, a runtime wait to fix).
      "unknown"           -- fewer than two rows, no freeze fields (a log from before Task 2e), or no match."""
    rows = [r for r in rows if isinstance(r, dict)]
    if len(rows) < 2:
        return "unknown"
    if all(r.get("net_wait") == 1 for r in rows) and _flat(rows, "seq") and _flat(rows, "dpc"):
        return "net-wait"
    if all((r.get("net_park") or 0) >= 1 for r in rows) and _climbing(rows, "vsync") and _climbing(rows, "seq"):
        return "net-park"
    if _flat(rows, "vsync"):
        if any((r.get("bp_waiters") or 0) >= 1 for r in rows) and _climbing(rows, "bp_wait_ms"):
            return "host-load"
        if all(r.get("bp_waiters") == 0 for r in rows) and _climbing(rows, "idle"):
            return "runtime-oversleep"
    return "unknown"


def parse_log(lines):
    """-> dict(rows=[(index, items)], samplers=[(row index, live_pc, running, {tid: (pc, st, wait)})],
    netidle=[(frac index, n, ms)], anchors=[(frac index, host t)], calls={name: [(frac index, t, n)]}).
    A sampler line is attributed to the peek row that FOLLOWS it (the sampler prints its pc line, then the row);
    a call/ret between rows i-1 and i sits at index i - 0.5."""
    rows, samplers, anchors, calls = [], [], [], {}
    rets = {}
    pi = 0
    for raw in lines:
        for seg in _segments(raw):
            if seg.startswith("[peek] "):
                items = [(int(a, 16), [int(w, 16) for w in vc._WORD.findall(ws)]) for a, ws in vc._ITEM.findall(seg)]
                rows.append((pi, items))
                pi += 1
            elif seg.startswith("[pc-sampler] "):
                m = _SAMPLER.match(seg)
                if m:
                    threads = {int(tid): (int(pc, 16), int(st), int(wr)) for tid, pc, st, wr, _ in _THREAD.findall(m.group(3))}
                    row = {"live_pc": int(m.group(1), 16), "running": int(m.group(2)), "threads": threads}
                    row.update(_sampler_fields(seg))
                    samplers.append((pi, int(m.group(1), 16), int(m.group(2)), threads, row))
            elif seg.startswith("[call] "):
                m = vc._CALL.match(seg)
                if m:
                    t, name, n = float(m.group(1)), m.group(2), int(m.group(3))
                    here = pi - 0.5
                    calls.setdefault(name, []).append((here, t, n))
                    if not anchors or t - anchors[-1][1] >= vc.CLOCK_ANCHOR_MIN_SPACING_S:
                        anchors.append((here, t))
            elif seg.startswith("[ret] "):
                m = vc._RET.match(seg)
                if m:
                    rets.setdefault(m.group(1), []).append((pi - 0.5, int(m.group(2)), int(m.group(3), 16)))
    return {"rows": rows, "samplers": samplers, "anchors": anchors, "calls": calls,
            "netidle": rets.get("NetIdle", []), "rets": rets}


def _stalls(clocks):
    """[(start_row, end_row)] maximal runs of >= 2 rows with a bit-identical clock; rows without a clock break runs."""
    out, i, n = [], 0, len(clocks)
    while i < n:
        if clocks[i] is None:
            i += 1
            continue
        j = i
        while j + 1 < n and clocks[j + 1] is not None and clocks[j + 1] == clocks[i]:
            j += 1
        if j > i:
            out.append((i, j))
        i = j + 1
    return out


def _mode(values):
    if not values:
        return None, 0
    (v, c), = collections.Counter(values).most_common(1)
    return v, c


def windows(lines, min_stall_s=DEFAULT_MIN_STALL_S, sampler_period=vc.SAMPLER_PERIOD_S):
    """Every window where the guest round clock did not advance across >= min_stall_s of rows. -> [dict] in row order:
      start_row, end_row (inclusive), rows, t_start, t_end (host s, [call]-anchored), stall_s,
      guest_clock_before (the value the clock held through the stall), guest_clock_after (the first value after it,
      None when the log ends in the stall), clock_source, main_pc (thread 1's most common sampled pc in the window),
      main_pc_share (its fraction of the window's samples), live_pc (the most common live pc), samples,
      shape (classify() over the window's sampler rows: "net-wait" / "host-load" / "runtime-oversleep" /
      "unknown"), idle_share (fraction of samples with running=0), netidle_peak_ms (largest NetIdle v0 logged in the window,
      None if none), netidle_calls, movescale_calls."""
    p = parse_log(lines)
    rows = p["rows"]
    if len(rows) < 2:
        return []
    clock = vc._make_clock(p["anchors"], sampler_period)
    vals, srcs = zip(*(_row_clock(items) for _, items in rows))
    by_row = collections.defaultdict(list)
    for ri, live, running, threads, row in p["samplers"]:
        by_row[ri].append((live, running, threads, row))
    idle_idx = sorted(p["netidle"])
    idle_pos = [r[0] for r in idle_idx]
    ms_idx = sorted(p["calls"].get("MoveScale", []))
    ms_pos = [r[0] for r in ms_idx]
    out = []
    for a, b in _stalls(list(vals)):
        t0, t1 = clock(a), clock(b)
        if t1 - t0 < min_stall_s:
            continue
        samples = [s for r in range(a, b + 1) for s in by_row.get(r, [])]
        main_pc, main_n = _mode([th[MAIN_THREAD_ID][0] for _, _, th, _ in samples if MAIN_THREAD_ID in th])
        live_pc, _ = _mode([live for live, _, _, _ in samples])
        idle = sum(1 for _, running, _, _ in samples if running == 0)
        lo, hi = a - 0.5, b + 0.5
        idle_here = idle_idx[bisect.bisect_left(idle_pos, lo):bisect.bisect_right(idle_pos, hi)]
        ms_here = ms_idx[bisect.bisect_left(ms_pos, lo):bisect.bisect_right(ms_pos, hi)]
        out.append({
            "start_row": a, "end_row": b, "rows": b - a + 1,
            "t_start": t0, "t_end": t1, "stall_s": t1 - t0,
            "guest_clock_before": vals[a],
            "guest_clock_after": vals[b + 1] if b + 1 < len(vals) else None,
            "clock_source": srcs[a],
            "main_pc": main_pc, "main_pc_share": (main_n / len(samples)) if samples else None,
            "live_pc": live_pc, "samples": len(samples),
            "idle_share": (idle / len(samples)) if samples else None,
            "shape": classify([row for _, _, _, row in samples]),
            "netidle_peak_ms": max((ms for _, _, ms in idle_here), default=None),
            "netidle_calls": len(idle_here),
            "movescale_calls": len(ms_here),
        })
    return out


PEER_SLACK_S = 10.0     # 8c: the peer's NetIdle peak lands up to ~6 s after the frozen side's clock restarts (A's 8217
                        # at 644.0 s against B's stall end 638.27 s); the idle counter reports elapsed idle, so it
                        # keeps climbing until the first packet after the restart. Epochs are per process (both exes
                        # start within ~1 s of each other in a paired launch) -- the peer column is approximate.


def peer_netidle(peer_lines):
    """[(host t, n, ms)] of the peer log's NetIdle returns, stamped with their own [call] time (peer's epoch)."""
    p = parse_log(peer_lines)
    t_of = {n: t for _, t, n in p["calls"].get("NetIdle", [])}
    return sorted((t_of[n], n, ms) for _, n, ms in p["netidle"] if n in t_of)


def peer_netidle_peak(peer_rets, t0, t1, slack_s=PEER_SLACK_S):
    """The largest peer NetIdle ms whose call stamp lies in [t0, t1 + slack_s], or None."""
    return max((ms for t, _, ms in peer_rets if t0 <= t <= t1 + slack_s), default=None)


def _fmt_clock(v):
    if v is None:
        return "-"
    return ("%.3f" % v) if isinstance(v, float) else str(v)


def _fmt_pc(v):
    return "-" if v is None else "0x%x" % v


def format_window(w):
    kind = ""
    if isinstance(w["guest_clock_before"], float) and w["guest_clock_before"] == 0.0:
        kind = " [clock 0.0: lobby / pre-round]"
    share = "" if w["main_pc_share"] is None else " (%d%% of %d samples, idle %d%%)" % (
        round(100 * w["main_pc_share"]), w["samples"], round(100 * (w["idle_share"] or 0)))
    peak = "-" if w["netidle_peak_ms"] is None else "%d ms" % w["netidle_peak_ms"]
    peer = ""
    if "peer_netidle_peak_ms" in w:
        peer = " peer_netidle_peak=%s" % ("-" if w["peer_netidle_peak_ms"] is None else "%d ms" % w["peer_netidle_peak_ms"])
    shape = "" if w.get("shape", "unknown") == "unknown" else " shape=%s" % w["shape"]
    return ("window rows %d..%d (%d rows) host %.2f-%.2f s stall=%.2fs clock %s -> %s [%s] main_pc=%s%s "
            "netidle_peak=%s netidle_calls=%d movescale_calls=%d%s%s%s"
            % (w["start_row"], w["end_row"], w["rows"], w["t_start"], w["t_end"], w["stall_s"],
               _fmt_clock(w["guest_clock_before"]), _fmt_clock(w["guest_clock_after"]), w["clock_source"],
               _fmt_pc(w["main_pc"]), share, peak, w["netidle_calls"], w["movescale_calls"], shape, peer, kind))


def summary(ws):
    longest = max((w["stall_s"] for w in ws), default=0.0)
    return "summary windows=%d longest=%.2fs stalled_rows=%d" % (len(ws), longest, sum(w["rows"] for w in ws))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="guest round-clock stall windows of one run log")
    ap.add_argument("log")
    ap.add_argument("--min-stall-s", type=float, default=DEFAULT_MIN_STALL_S)
    ap.add_argument("--period", type=float, default=vc.SAMPLER_PERIOD_S,
                    help="nominal sampler period outside the [call] anchors (default %.2f)" % vc.SAMPLER_PERIOD_S)
    ap.add_argument("--peer", help="the other instance's log: its NetIdle peak over each window (+%.0f s slack, "
                                   "peer's own epoch)" % PEER_SLACK_S)
    args = ap.parse_args(argv)
    with open(args.log, "r", encoding="utf-8", errors="replace") as f:
        ws = windows(f, min_stall_s=args.min_stall_s, sampler_period=args.period)
    if args.peer:
        with open(args.peer, "r", encoding="utf-8", errors="replace") as f:
            rets = peer_netidle(f)
        for w in ws:
            w["peer_netidle_peak_ms"] = peer_netidle_peak(rets, w["t_start"], w["t_end"])
    for w in ws:
        print(format_window(w))
    print(summary(ws))
    return 0


if __name__ == "__main__":
    sys.exit(main())
