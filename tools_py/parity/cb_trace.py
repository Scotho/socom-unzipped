"""The host audio callback trace (PS2X_AUDIO_CB_TRACE, runtime/audio_cb_trace.h): where a 50 ms hole at the
endpoint went.

    python -m tools_py.parity.cb_trace <cb_trace.csv> [--dips dips.txt --recorder-start <epoch s>] [--tolerance 0.25]

KNOWN §2 (2026-09-23): the mission music loses 50 ms holes, 10-20 dB deep, present in the endpoint loopback and
absent from the mixer's dump at the aligned time, on any endpoint. The dump is written from the callback, so the
loss happens after the callback returns; the dump's frame clock cannot see a late callback, the endpoint can. The
trace records every callback's wall-clock entry and exit (microseconds since a t0 whose wall-clock epoch is in the
header), so:

  * a HOLE is a gap between two callback entries longer than the device buffer less one period (the header's
    hole_us: 60 ms for 20 ms x 4) -- the engine ran out of what we had queued and played silence for about
    gap - period;
  * with `--dips` (audio_dips' report) and `--recorder-start` (the loopback recorder's own start_epoch line), each
    DEVICE dip's wall clock (recorder start + endpoint time) is laid against the holes: a dip with a hole within
    `--tolerance` is that late callback; a dip with none is NOT a late callback -- the engine's, the recorder's or
    the scorer's, but not the device thread's.

Everything here is pure text in, text out; the test drives it on synthetic rows.
"""
import argparse
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class Row:
    seq: int
    entry_us: int
    exit_us: int
    frames: int
    out_frame: int
    gap_us: int
    render_us: int


@dataclass
class Hole:
    seq: int
    entry_us: int
    gap_us: int
    silence_us: int      # gap - period: what the engine had nothing for
    out_frame: int


def parse(text: str) -> Tuple[Dict[str, int], List[Row]]:
    """The header's key=value pairs and the rows. A row that does not parse is skipped (a flush cut short)."""
    header: Dict[str, int] = {}
    rows: List[Row] = []
    for line in text.splitlines():
        if line.startswith("#"):
            for key, value in re.findall(r"(\w+)=(-?\d+)", line):
                header[key] = int(value)
            continue
        if not line or line.startswith("seq,"):
            continue
        parts = line.split(",")
        if len(parts) != 7:
            continue
        try:
            rows.append(Row(*(int(p) for p in parts)))
        except ValueError:
            continue
    return header, rows


def holes(rows: List[Row], hole_us: int, period_us: int) -> List[Hole]:
    return [Hole(r.seq, r.entry_us, r.gap_us, r.gap_us - period_us, r.out_frame) for r in rows if r.gap_us > hole_us]


# "   46.20    0.05    11.5  vag g1+vag g2  DEVICE   in the endpoint, not in the dump at 40.22 s (offset 5.98 s)":
# the route carries spaces ("vag g1+vag g2"), the columns are two or more spaces apart, and a DEVICE row names
# the dump time the scorer aligned the dip to -- the mixer's own output-frame clock, which the trace records.
DIP_LINE = re.compile(r"^\s*(\d+\.\d+)\s+(\d+\.\d+)\s+(-?\d+\.\d+)\s+(.+?)\s{2,}(DEVICE|STARVATION|COMMAND|UNEXPLAINED)\b")
DUMP_TIME = re.compile(r"not in the dump at (\d+\.\d+) s")


@dataclass
class DeviceDip:
    start_s: float
    dur_s: float
    depth_db: float
    route: str
    dump_s: Optional[float] = None   # the scorer's aligned dump time, when the row carries one


def parse_dips(text: str) -> List[DeviceDip]:
    """audio_dips' report lines, DEVICE rows only."""
    out = []
    for line in text.splitlines():
        m = DIP_LINE.match(line)
        if m and m.group(5) == "DEVICE":
            t = DUMP_TIME.search(line)
            out.append(DeviceDip(float(m.group(1)), float(m.group(2)), float(m.group(3)), m.group(4),
                                 float(t.group(1)) if t else None))
    return out


def callback_at_out_frame(rows: List[Row], out_frame: int) -> Optional[Row]:
    """The callback whose render produced `out_frame`: the first row whose out_frame (the clock AFTER it) is past it."""
    for r in rows:
        if r.out_frame > out_frame:
            return r
    return None


def attribute_by_dump(dips: List[DeviceDip], rows: List[Row], found: List[Hole], sample_rate: int = 48000,
                      tolerance_s: float = 0.25) -> List["Attribution"]:
    """Each DEVICE dip through its dump-aligned time: the output frame at that time names the callback that
    rendered it, and a hole whose entry lies within `tolerance_s` of that callback's entry is the late callback.
    Needs no recorder clock at all: the dump and the trace share the mixer's frame clock."""
    out = []
    for d in dips:
        if d.dump_s is None:
            out.append(Attribution(d, 0.0, None, 0.0))
            continue
        r = callback_at_out_frame(rows, int(d.dump_s * sample_rate))
        if r is None:
            out.append(Attribution(d, 0.0, None, 0.0))
            continue
        wall_s = r.entry_us / 1e6
        best, best_delta = None, 0.0
        for h in found:
            delta = wall_s - h.entry_us / 1e6
            if abs(delta) <= tolerance_s and (best is None or abs(delta) < abs(best_delta)):
                best, best_delta = h, delta
        out.append(Attribution(d, wall_s, best, best_delta))
    return out


@dataclass
class Attribution:
    dip: DeviceDip
    wall_s: float                 # the dip's wall clock, seconds since the trace's t0
    hole: Optional[Hole]
    delta_s: float                # dip wall - hole wall (0 when no hole)


def attribute(dips: List[DeviceDip], found: List[Hole], t0_epoch_us: int, recorder_start_epoch_s: float,
              tolerance_s: float = 0.25) -> List[Attribution]:
    """Each DEVICE dip against the nearest hole in wall-clock time; None when none lies within the tolerance."""
    out = []
    for d in dips:
        wall_s = recorder_start_epoch_s + d.start_s - t0_epoch_us / 1e6
        best, best_delta = None, 0.0
        for h in found:
            delta = wall_s - h.entry_us / 1e6
            if abs(delta) <= tolerance_s and (best is None or abs(delta) < abs(best_delta)):
                best, best_delta = h, delta
        out.append(Attribution(d, wall_s, best, best_delta))
    return out


def report(header: Dict[str, int], rows: List[Row], found: List[Hole], attributions: Optional[List[Attribution]]) -> str:
    period = header.get("period_us", 0)
    lines = []
    span_s = (rows[-1].entry_us - rows[0].entry_us) / 1e6 if len(rows) > 1 else 0.0
    max_gap = max((r.gap_us for r in rows), default=0)
    max_render = max((r.render_us for r in rows), default=0)
    lines.append(f"callbacks {len(rows)} over {span_s:.1f} s, period {period / 1000:.0f} ms, hole threshold "
                 f"{header.get('hole_us', 0) / 1000:.0f} ms; max gap {max_gap / 1000:.1f} ms, max render {max_render / 1000:.2f} ms")
    per_min = span_s / 60.0 if span_s > 0 else 0.0
    lines.append(f"holes {len(found)}" + (f" ({len(found) / per_min:.1f} per minute)" if per_min else "")
                 + f", silence {sum(h.silence_us for h in found) / 1000:.0f} ms in all")
    for h in found:
        lines.append(f"  hole seq={h.seq} at {h.entry_us / 1e6:9.3f} s  gap {h.gap_us / 1000:6.1f} ms  silence ~{h.silence_us / 1000:5.1f} ms  out_frame {h.out_frame}")
    if attributions is not None:
        matched = sum(1 for a in attributions if a.hole is not None)
        lines.append(f"DEVICE dips {len(attributions)}: {matched} on a late callback, {len(attributions) - matched} on none")
        for a in attributions:
            if a.hole is not None:
                lines.append(f"  dip {a.dip.start_s:8.2f} s ({a.dip.dur_s:.2f} s, {a.dip.depth_db:.1f} dB, {a.dip.route})  LATE CALLBACK seq={a.hole.seq} "
                             f"gap {a.hole.gap_us / 1000:.1f} ms, {a.delta_s * 1000:+.0f} ms from it")
            else:
                lines.append(f"  dip {a.dip.start_s:8.2f} s ({a.dip.dur_s:.2f} s, {a.dip.depth_db:.1f} dB, {a.dip.route})  NO LATE CALLBACK within the tolerance")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("trace")
    ap.add_argument("--dips", help="audio_dips' report (dips.txt) for the same capture")
    ap.add_argument("--recorder-start", type=float, help="the loopback recorder's start_epoch (seconds)")
    ap.add_argument("--tolerance", type=float, default=0.25, help="seconds either side of a dip to look for a hole")
    a = ap.parse_args(argv)
    with open(a.trace, "r", encoding="utf-8", errors="replace") as fh:
        header, rows = parse(fh.read())
    if not rows:
        print("no callback rows in", a.trace)
        return 1
    found = holes(rows, header.get("hole_us", 60000), header.get("period_us", 20000))
    attributions = None
    if a.dips:
        with open(a.dips, "r", encoding="utf-8", errors="replace") as fh:
            dips = parse_dips(fh.read())
        if a.recorder_start is not None:
            attributions = attribute(dips, found, header.get("t0_epoch_us", 0), a.recorder_start, a.tolerance)
        else:
            # The scorer's dump-aligned time and the trace's out_frame share the mixer's clock: no recorder clock needed.
            attributions = attribute_by_dump(dips, rows, found, tolerance_s=a.tolerance)
    print(report(header, rows, found, attributions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
