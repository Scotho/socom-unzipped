"""Sprint 7 Task 5 (spec Goal 5): the readout the owner runs after the first TWO-MACHINE match.

Every online result in this tree so far is two instances on one PC (audit 2026-09-17 gap G5). When a
second machine finally plays, the only artefacts that come back are the two run logs -- one per
machine. This turns that pair into the four things the spec's bar asks for:

    python -m tools_py.parity.two_machine_readout <log_A> <log_B> [<shared harness log>...]
    bash scripts/parity/two_machine_readout.sh   <log_A> <log_B> [<shared harness log>...]

  * the LOBBY CLASS, per side and overall -- `lobby_report.summarise`, so a miss is named with the
    same vocabulary the ten-launch table uses (`login:keyboard-enter`, `map-list-search`, ...);
  * WHETHER EACH SIDE SAW THE OTHER MOVE, from the position peek;
  * the CLOCK SKEW between the two round clocks, from the `0x408F10` clock string;
  * the failure CLASS of each side.

PURE except `read()` and `main()`: `read_lines` takes lines, opens nothing and reads no clock.

WHAT "saw the other move" CAN AND CANNOT MEAN HERE (controller's choice, Task 5 -- re-rule if wrong).
`scripts/parity/env.sh`'s PS2X_PEEK follows `*0x408c58`, which is the LOCAL player's actor and only
it: no remote player's actor block is peeked on either machine, so no log can be asked what the other
guy's body did on THIS machine's screen. What two logs CAN settle is whether the other guy's body
moved at all: `saw_peer_move["A"]` is read from log B's position peek -- did A's peer actually walk
more than PEER_MOVE_MIN_UNITS during the round. Together with a lobby reached on both sides and the
clock skew, that is the strongest statement this pair of files supports.
  BLIND, and it is the whole of the difference: whether A's SCREEN reproduced B's motion. A frozen
  or never-spawned peer avatar on A passes this every time. The instrument that does separate them is
  a screenshot diff of the other machine's window (`tools_py/parity/motion_diff.py`, Sprint 6 Task 7);
  the owner's own eyes are the other one, and `docs/HUMAN_TASKS.md` asks for them.

LINES IN, AND WHY A THIRD FILE IS ALLOWED (controller's choice). A machine's run log carries the
`[peek]`/`[call]` rows but no `RESULT`/`LOBBY` lines -- those are written by the driver, into
`logs/parity/drive_<name>.txt`, tagged `A_`/`B_`. So each side's lines are taken from its own log
(untagged lines are tagged with that side's letter) and, when extra logs are given, from their lines
already tagged for that side. Passing only the two run logs works and simply reports no lobby class;
passing the drive log alongside them fills it in. The same drive log may be given twice, or once --
a line tagged for the other side is ignored, never double-counted.

CLOCK SKEW, AND THE ORIGIN IT CANNOT SEE. A peek row's time is `verdict_core.parse_log`'s clock:
seconds since THAT PROCESS's call-trace start (see its module docstring). Rows are paired across the
two logs by that time, nearest within CLOCK_PAIR_MAX_GAP_S, and the skew is the median of
`seconds(clock A) - seconds(clock B)` over the pairs, positive when A's clock reads later.
  BLIND: the two logs have no common origin. Whatever separates the two processes' call-trace starts
  -- different machines, different boot times, a launcher started by hand -- lands in the skew in
  full. `--offset-a/--offset-b` shift a side's times when the owner knows the real offset, and
  `round_span_s` (first clock row to last, per side) is the origin-free companion: it says whether
  the two clocks RAN together even when it cannot say whether they READ the same.
"""
import argparse
import bisect
import math
import os
import statistics
import sys

from tools_py.parity import lobby_report
from tools_py.parity import verdict_core as vc

SIDES = ("A", "B")
PEER = {"A": "B", "B": "A"}

# The movement bar. Deliberately verdict_core.CONTROL_NET_MIN_UNITS: the same 40 units that says a
# side is controllable at all (the 40 u/s forward calibration, research/18 section 3.13), so "the
# peer moved" and "this side could move" are never two different numbers.
PEER_MOVE_MIN_UNITS = 40.0
# Two rows are "the same moment" within this. A bit over one 4 Hz sampler period (0.25 s), so a row
# finds its counterpart even when the two grids are offset; measured on the calibration pair, it
# paired 1472 of A's 1492 clock rows. Blind: skew smaller than the 1 s resolution of the clock
# STRING -- it counts whole seconds, so a sub-second skew reads as 0 or 1.
CLOCK_PAIR_MAX_GAP_S = 0.3


def clock_seconds(text):
    """'MM:SS' (the 0x408F10 string) -> seconds, or None when it is not a clock."""
    parts = text.strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    return int(parts[0]) * 60 + int(parts[1])


def _ground(p, q):
    """Ground-plane (x, z) distance -- verdict_core's convention, its y is up."""
    return math.hypot(p[0] - q[0], p[1] - q[1])


def side_lines(side, own_lines, shared_lines=()):
    """The lines that belong to `side`, tagged for `lobby_report.summarise`.

    An untagged line of the side's own log is that side's (it came off that machine); a line already
    tagged is kept only when the tag is this side's. Shared logs contribute their tagged lines only."""
    out = []
    for raw in own_lines:
        tag, msg = lobby_report.split_line(raw)
        if tag is None:
            out.append("%s_%s" % (side, msg))
        elif tag == side:
            out.append("%s_%s" % (side, msg))
    for raw in shared_lines:
        tag, msg = lobby_report.split_line(raw)
        if tag == side:
            out.append("%s_%s" % (side, msg))
    return out


def _side_rows(lines, offset=0.0):
    """The parsed rows of one machine's log: peek/actor/clock rows on that process's clock + offset."""
    parsed = vc.parse_log(lines)
    clocks = [(t + offset, s) for t, s in vc.clock_rows(parsed.peek_rows)]
    actors = [(t + offset, x, z) for t, x, _y, z, _a in
              ((r[0], r[1], r[2], r[3], r[4]) for r in parsed.actor_rows)]
    return {"lines": parsed.lines, "peek": len(parsed.peek_rows), "actor": actors, "clock": clocks}


def moved_units(rows):
    """Peak ground-plane excursion from the first actor row IN THE ROUND, or None with no rows.

    The round is the window the clock string covers (first clock row to last); with no clock rows at
    all every actor row counts. Peak, not net: a side that walks out and comes back still moved.
    Blind: motion entirely between two 4 Hz rows; a side whose actor block never resolved reads as
    None (no data), which is NOT the same as "did not move" and is printed differently."""
    actors, clocks = rows["actor"], rows["clock"]
    if clocks:
        t0, t1 = clocks[0][0], clocks[-1][0]
        actors = [r for r in actors if t0 <= r[0] <= t1]
    if not actors:
        return None
    first = (actors[0][1], actors[0][2])
    return max(_ground(first, (t[1], t[2])) for t in actors)


def clock_skew(rows_a, rows_b, max_gap_s=CLOCK_PAIR_MAX_GAP_S):
    """(median skew in seconds, pairs, (min, max)) over rows paired by time, or (None, 0, None)."""
    a, b = rows_a["clock"], rows_b["clock"]
    if not a or not b:
        return None, 0, None
    bt = [t for t, _ in b]
    diffs = []
    for t, sa in a:
        va = clock_seconds(sa)
        if va is None:
            continue
        i = bisect.bisect_left(bt, t)
        best = None
        for j in (i - 1, i, i + 1):
            if 0 <= j < len(bt) and (best is None or abs(bt[j] - t) < abs(bt[best] - t)):
                best = j
        if best is None or abs(bt[best] - t) > max_gap_s:
            continue
        vb = clock_seconds(b[best][1])
        if vb is not None:
            diffs.append(float(va - vb))
    if not diffs:
        return None, 0, None
    return statistics.median(diffs), len(diffs), (min(diffs), max(diffs))


def span_s(rows):
    c = rows["clock"]
    return (c[-1][0] - c[0][0]) if len(c) >= 2 else None


def read_lines(a_lines, b_lines, shared_lines=(), offsets=None):
    """The readout over two machines' log lines. See the module docstring for every choice here."""
    a_lines, b_lines, shared_lines = list(a_lines), list(b_lines), list(shared_lines)
    offsets = offsets or {}
    own = {"A": a_lines, "B": b_lines}
    rows = {s: _side_rows(own[s], float(offsets.get(s, 0.0))) for s in SIDES}
    tagged = {s: side_lines(s, own[s], shared_lines) for s in SIDES}
    per_side = {s: lobby_report.summarise(tagged[s]) for s in SIDES}
    both = lobby_report.summarise(tagged["A"] + tagged["B"])

    units = {s: moved_units(rows[s]) for s in SIDES}
    skew, pairs, rng = clock_skew(rows["A"], rows["B"])
    saw = {s: bool(units[PEER[s]] is not None and units[PEER[s]] > PEER_MOVE_MIN_UNITS) for s in SIDES}
    out = {
        "lobby_class": both["cls"],
        "lobby_outcome": both["outcome"],
        "classes": {s: per_side[s]["cls"] for s in SIDES},
        "outcomes": {s: per_side[s]["outcome"] for s in SIDES},
        "ended_stage": {s: per_side[s]["ended_stage"] for s in SIDES},
        "saw_peer_move": saw,
        # peer_move_units[s] is the PEER's distance -- what side s had to see.
        "peer_move_units": {s: units[PEER[s]] for s in SIDES},
        "clock_skew_s": skew,
        "clock_pairs": pairs,
        "clock_skew_range_s": rng,
        "round_span_s": {s: span_s(rows[s]) for s in SIDES},
        "rows": {s: {"lines": rows[s]["lines"], "peek": rows[s]["peek"],
                     "actor": len(rows[s]["actor"]), "clock": len(rows[s]["clock"])} for s in SIDES},
    }
    out["bar"] = bool(both["outcome"] == lobby_report.OUTCOME_GAMEPLAY and saw["A"] and saw["B"])
    return out


def _units(v):
    return "no actor rows" if v is None else "%.1f u" % v


def format_block(out, names=None):
    """The block the owner pastes back. One fact a line, every miss named."""
    names = names or {}
    lines = ["TWO-MACHINE READOUT (Sprint 7 Task 5, spec Goal 5)"]
    for s in SIDES:
        lines.append("  %s log      %s" % (s, names.get(s, "(lines)")))
    lines.append("  lobby      class=%s outcome=%s | A=%s B=%s"
                 % (out["lobby_class"] or "-", out["lobby_outcome"],
                    out["classes"]["A"] or "-", out["classes"]["B"] or "-"))
    for s in SIDES:
        stage = out["ended_stage"][s]
        lines.append("    %s        outcome=%s class=%s ended=%s"
                     % (s, out["outcomes"][s], out["classes"][s] or "-", stage or "-"))
    for s in SIDES:
        lines.append("  saw_peer_move %s=%s  (%s's actor moved %s over the round, bar %.1f u)"
                     % (s, out["saw_peer_move"][s], PEER[s], _units(out["peer_move_units"][s]),
                        PEER_MOVE_MIN_UNITS))
    if out["clock_skew_s"] is None:
        lines.append("  clock      skew=NO-DATA (no paired 0x408F10 clock rows)")
    else:
        lo, hi = out["clock_skew_range_s"]
        lines.append("  clock      skew=%+.1f s (A - B, median of %d paired rows, range %+.0f..%+.0f s)"
                     % (out["clock_skew_s"], out["clock_pairs"], lo, hi))
    lines.append("  clock      round span A=%s B=%s  (origin-free: did the two clocks RUN together)"
                 % tuple("-" if out["round_span_s"][s] is None else "%.2f s" % out["round_span_s"][s]
                         for s in SIDES))
    for s in SIDES:
        r = out["rows"][s]
        lines.append("  rows       %s lines=%d peek=%d actor=%d clock=%d"
                     % (s, r["lines"], r["peek"], r["actor"], r["clock"]))
    lines.append("  BAR        lobby reached and both players seen moving: %s"
                 % ("PASS" if out["bar"] else "MISS"))
    lines.append("  BLIND      the peer's motion is read from the peer's OWN log: this cannot say the")
    lines.append("             other player was drawn moving on this machine's screen (module docstring).")
    return lines


def _lines_of(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def read(log_a, log_b, *shared, **kwargs):
    """`read_lines` over the files at those paths; extra paths are shared (tagged) harness logs."""
    shared_lines = []
    for p in shared:
        shared_lines.extend(_lines_of(p))
    return read_lines(_lines_of(log_a), _lines_of(log_b), shared_lines, kwargs.get("offsets"))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m tools_py.parity.two_machine_readout",
        description="The two-machine match readout: lobby class, peer movement, clock skew.")
    ap.add_argument("log_a", help="machine A's run log")
    ap.add_argument("log_b", help="machine B's run log")
    ap.add_argument("shared", nargs="*", help="harness/drive logs whose A_/B_ tagged lines belong to both")
    ap.add_argument("--offset-a", type=float, default=0.0, help="seconds to add to A's row times")
    ap.add_argument("--offset-b", type=float, default=0.0, help="seconds to add to B's row times")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    out = read(args.log_a, args.log_b, *args.shared,
               offsets={"A": args.offset_a, "B": args.offset_b})
    names = {"A": os.path.basename(args.log_a), "B": os.path.basename(args.log_b)}
    for line in format_block(out, names):
        print(line)
    return 0 if out["bar"] else 1


if __name__ == "__main__":
    sys.exit(main())
