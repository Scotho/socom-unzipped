"""The host audio callback trace (PS2X_AUDIO_CB_TRACE, runtime/audio_cb_trace.h): where a 50 ms hole at the
endpoint went, and where the trace cannot say.

    python -m tools_py.parity.cb_trace <cb_trace.csv> [--dips dips.txt] [--recorder-first-packet <epoch s>]
                                       [--tolerance s] [--rate 48000]

KNOWN §2 (2026-09-23): the mission music loses 50 ms holes, 10-20 dB deep, present in the endpoint loopback and
absent from the mixer's dump at the aligned time, on any endpoint. The dump is written from the callback, so the
loss happens after the callback returns; the dump's frame clock cannot see a late callback, the endpoint can. The
trace records every callback's wall-clock entry and exit (microseconds since a t0 whose wall-clock epoch is in the
header) and the mixer's output-frame clock after it. Read back:

  * a LATE callback came more than late_us after the one before (the buffer less one period: 60 ms at 20 ms x 4)
    -- the device thread was in trouble, though the engine still had one period queued;
  * a DRY callback came more than dry_us after (the whole buffer: 80 ms) -- the engine ran out, and the endpoint
    got about gap - dry_us of silence. Only dry callbacks put silence in the endpoint; a late one is a warning.

Two ways to lay a DEVICE dip of audio_dips' report against the callbacks, each honest about its limits:

  * by dump time (default with --dips): the scorer's "not in the dump at X s" is on the mixer's output-frame
    clock, which the trace records as out_frame, so X names the callback that rendered it exactly. But X itself
    is the endpoint time minus a cross-correlation offset (global, refined per dip within +-3 s); its confidence
    is the report's "envelope correlation", carried here and flagged under `min_corr`. A dip whose X is before the
    trace's first callback, past its last, or missing is UNATTRIBUTABLE and counted as such -- never "cleared".
  * by the recorder's clock (--recorder-first-packet): loopback_record's first_packet_epoch is when its first
    1024-frame read returned, so the file's frame 0 is that stamp less 1024/rate; endpoint time t is then a wall
    clock, laid against the callbacks' entries. Independent of the scorer's alignment, dependent on the recorder's.

The trace is not a ring: it drops on full and the flusher writes "# dropped=N recorded=M" on every pass, so a
saturated or dropping trace is said loudly here. Everything is pure text in, text out; the test drives it on
synthetic rows.
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
    """A late callback: its gap to the previous entry; dry when the whole buffer ran out, with the silence that
    reached the endpoint (0 for a late-but-covered callback)."""
    seq: int
    entry_us: int
    gap_us: int
    dry: bool
    silence_us: int
    out_frame: int


def parse(text: str) -> Tuple[Dict[str, int], List[Row], int]:
    """The header's and status lines' key=value pairs (later lines win: "# dropped=N recorded=M" is written on
    every flush), the rows, and how many non-empty lines were neither -- a killed process leaves a cut-short row,
    and a CSV half-eaten by something else should not read as a clean short trace."""
    header: Dict[str, int] = {}
    rows: List[Row] = []
    skipped = 0
    for line in text.splitlines():
        if line.startswith("#"):
            for key, value in re.findall(r"(\w+)=(-?\d+)", line):
                header[key] = int(value)
            continue
        if not line.strip() or line.startswith("seq,"):
            continue
        parts = line.split(",")
        if len(parts) != 7:
            skipped += 1
            continue
        try:
            rows.append(Row(*(int(p) for p in parts)))
        except ValueError:
            skipped += 1
    return header, rows, skipped


def late_callbacks(rows: List[Row], late_us: int, dry_us: int, period_us: int) -> List[Hole]:
    out = []
    for r in rows:
        if r.gap_us > late_us:
            dry = r.gap_us > dry_us
            out.append(Hole(r.seq, r.entry_us, r.gap_us, dry, max(0, r.gap_us - dry_us) if dry else 0, r.out_frame))
    return out


# "   46.20    0.05    11.5  vag g1+vag g2  DEVICE   in the endpoint, not in the dump at 40.22 s (offset 5.98 s)":
# the route carries spaces ("vag g1+vag g2"), the columns are two or more spaces apart, and a DEVICE row names the
# dump time the scorer aligned the dip to and the per-dip offset it used. The report's first line carries the
# global alignment and its envelope correlation.
DIP_LINE = re.compile(r"^\s*(\d+\.\d+)\s+(\d+\.\d+)\s+(-?\d+\.\d+)\s+(.+?)\s{2,}(DEVICE|STARVATION|COMMAND|UNEXPLAINED|NODUMP)\b")
DUMP_TIME = re.compile(r"not in the dump at (-?\d+\.\d+) s")
DIP_OFFSET = re.compile(r"\(offset (-?\d+\.\d+) s\)")
ALIGNMENT = re.compile(r"alignment: endpoint = dump \+ (-?\d+\.\d+) s \(envelope correlation (-?\d+\.\d+)\)")


@dataclass
class DeviceDip:
    start_s: float
    dur_s: float
    depth_db: float
    route: str
    dump_s: Optional[float] = None     # the scorer's aligned dump time, when the row carries one
    offset_s: Optional[float] = None   # the per-dip offset the scorer used for it


def parse_dips(text: str) -> Tuple[List[DeviceDip], Optional[Tuple[float, float]]]:
    """audio_dips' report: the DEVICE rows, and the global alignment (offset, envelope correlation) if stated."""
    out = []
    alignment = None
    for line in text.splitlines():
        a = ALIGNMENT.search(line)
        if a:
            alignment = (float(a.group(1)), float(a.group(2)))
            continue
        m = DIP_LINE.match(line)
        if m and m.group(5) == "DEVICE":
            t = DUMP_TIME.search(line)
            o = DIP_OFFSET.search(line)
            out.append(DeviceDip(float(m.group(1)), float(m.group(2)), float(m.group(3)), m.group(4),
                                 float(t.group(1)) if t else None, float(o.group(1)) if o else None))
    return out, alignment


def callback_at_out_frame(rows: List[Row], out_frame: int) -> Optional[Row]:
    """The callback whose render produced `out_frame`: the first row whose out_frame (the clock AFTER it) is past
    it. None for a frame before the trace's first render or at/after its last clock -- never a guess."""
    if not rows or out_frame < 0 or out_frame < rows[0].out_frame - rows[0].frames:
        return None
    for r in rows:
        if r.out_frame > out_frame:
            return r
    return None


@dataclass
class Attribution:
    dip: DeviceDip
    wall_s: float                 # the dip's time on the trace's clock (0 when unattributable)
    hole: Optional[Hole]          # the late callback it lies on, if any
    delta_s: float                # dip - hole entry, seconds (0 when none)
    state: str                    # "late" | "cleared" | "unattributable"
    reason: str = ""              # for unattributable: "before the trace" | "past the trace" | "no dump time"


def _nearest(late: List[Hole], wall_s: float, tolerance_s: float) -> Tuple[Optional[Hole], float]:
    best, best_delta = None, 0.0
    for h in late:
        delta = wall_s - h.entry_us / 1e6
        if abs(delta) <= tolerance_s and (best is None or abs(delta) < abs(best_delta)):
            best, best_delta = h, delta
    return best, best_delta


def attribute_by_dump(dips: List[DeviceDip], rows: List[Row], late: List[Hole], period_us: int,
                      sample_rate: int = 48000, tolerance_s: Optional[float] = None) -> List[Attribution]:
    """Each DEVICE dip through its dump-aligned time: the output frame at that time names the callback that
    rendered it (exact), and a late callback whose entry lies within `tolerance_s` (default three periods -- the
    mapping is frame-exact, so a quarter of a second would let twelve callbacks claim a dip) is the one. A dump
    time before the trace, past it, or absent is UNATTRIBUTABLE with that reason."""
    tol = tolerance_s if tolerance_s is not None else 3 * period_us / 1e6
    out = []
    for d in dips:
        if d.dump_s is None:
            out.append(Attribution(d, 0.0, None, 0.0, "unattributable", "no dump time"))
            continue
        frame = int(round(d.dump_s * sample_rate))
        r = callback_at_out_frame(rows, frame)
        if r is None:
            reason = "before the trace" if (frame < 0 or (rows and frame < rows[0].out_frame - rows[0].frames)) else "past the trace"
            out.append(Attribution(d, 0.0, None, 0.0, "unattributable", reason))
            continue
        wall_s = r.entry_us / 1e6
        hole, delta = _nearest(late, wall_s, tol)
        out.append(Attribution(d, wall_s, hole, delta, "late" if hole else "cleared"))
    return out


def attribute_by_recorder(dips: List[DeviceDip], late: List[Hole], t0_epoch_us: int, first_packet_epoch_s: float,
                          rate: int = 48000, read_frames: int = 1024, tolerance_s: float = 0.25) -> List[Attribution]:
    """Each DEVICE dip by the recorder's clock: the file's frame 0 is the first packet's stamp less the read that
    produced it, so endpoint time t is wall first_packet - read + t, laid against the callbacks' entries. Any dip
    off the trace's span is UNATTRIBUTABLE."""
    file_start_s = first_packet_epoch_s - read_frames / rate - t0_epoch_us / 1e6
    out = []
    for d in dips:
        wall_s = file_start_s + d.start_s
        if wall_s < 0:
            out.append(Attribution(d, wall_s, None, 0.0, "unattributable", "before the trace"))
            continue
        hole, delta = _nearest(late, wall_s, tolerance_s)
        out.append(Attribution(d, wall_s, hole, delta, "late" if hole else "cleared"))
    return out


def report(header: Dict[str, int], rows: List[Row], skipped: int, late: List[Hole],
           attributions: Optional[List[Attribution]], alignment: Optional[Tuple[float, float]] = None,
           min_corr: float = 0.5) -> str:
    period = header.get("period_us", 0)
    lines = []
    span_s = (rows[-1].entry_us - rows[0].entry_us) / 1e6 if len(rows) > 1 else 0.0
    max_gap = max((r.gap_us for r in rows), default=0)
    max_render = max((r.render_us for r in rows), default=0)
    lines.append(f"callbacks {len(rows)} over {span_s:.1f} s, period {period / 1000:.0f} ms, late over "
                 f"{header.get('late_us', 0) / 1000:.0f} ms, dry over {header.get('dry_us', 0) / 1000:.0f} ms; "
                 f"max gap {max_gap / 1000:.1f} ms, max render {max_render / 1000:.2f} ms")
    if skipped:
        lines.append(f"WARNING: {skipped} line(s) of the trace were not rows (a cut-short flush, or something else wrote here)")
    dropped = header.get("dropped", 0)
    if dropped:
        lines.append(f"WARNING: the trace dropped {dropped} callbacks -- its capacity was used up; the tail is missing")
    capacity = header.get("capacity")
    if capacity and len(rows) >= capacity:
        lines.append(f"WARNING: the trace is full ({len(rows)} of {capacity} records); anything after it is missing")
    dry = [h for h in late if h.dry]
    per_min = span_s / 60.0 if span_s > 0 else 0.0
    lines.append(f"late {len(late)} ({len(dry)} dry), silence {sum(h.silence_us for h in late) / 1000:.0f} ms in all"
                 + (f"; {len(late) / per_min:.1f} late per minute" if per_min else ""))
    for h in late:
        lines.append(f"  {'DRY ' if h.dry else 'late'} seq={h.seq} at {h.entry_us / 1e6:9.3f} s  gap {h.gap_us / 1000:6.1f} ms"
                     f"  silence {h.silence_us / 1000:5.1f} ms  out_frame {h.out_frame}")
    if attributions is not None:
        if alignment is not None and alignment[1] < min_corr:
            lines.append(f"LOW CONFIDENCE: envelope correlation {alignment[1]:.2f} is under {min_corr:.2f} -- the scorer's "
                         f"dump times may be off by up to its search span; every attribution below inherits that")
        n_late = sum(1 for a in attributions if a.state == "late")
        n_clear = sum(1 for a in attributions if a.state == "cleared")
        un = [a for a in attributions if a.state == "unattributable"]
        before = sum(1 for a in un if a.reason == "before the trace")
        past = sum(1 for a in un if a.reason == "past the trace")
        nodump = sum(1 for a in un if a.reason == "no dump time")
        detail = f" ({before} before the trace, {past} past it" + (f", {nodump} without a dump time" if nodump else "") + ")" if un else ""
        lines.append(f"DEVICE dips {len(attributions)}: {n_late} late, {n_clear} cleared, {len(un)} unattributable{detail}")
        for a in attributions:
            d = a.dip
            head = f"  dip {d.start_s:8.2f} s ({d.dur_s:.2f} s, {d.depth_db:.1f} dB, {d.route})"
            off = f" (offset {d.offset_s:.2f} s)" if d.offset_s is not None else ""
            if a.state == "late":
                lines.append(f"{head}{off}  LATE CALLBACK seq={a.hole.seq} gap {a.hole.gap_us / 1000:.1f} ms"
                             f"{' DRY' if a.hole.dry else ''}, {a.delta_s * 1000:+.0f} ms from it")
            elif a.state == "cleared":
                lines.append(f"{head}{off}  cleared: no late callback within the tolerance")
            else:
                lines.append(f"{head}{off}  UNATTRIBUTABLE ({a.reason})")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("trace")
    ap.add_argument("--dips", help="audio_dips' report (dips.txt) for the same capture")
    ap.add_argument("--recorder-first-packet", type=float, dest="first_packet",
                    help="loopback_record's first_packet_epoch (seconds): attribute by the recorder's clock instead of the dump's")
    ap.add_argument("--recorder-start", type=float, dest="recorder_start",
                    help="deprecated: the recorder's start_epoch is earlier than the file's first frame; pass --recorder-first-packet")
    ap.add_argument("--tolerance", type=float, default=None,
                    help="seconds either side of a dip to look for a late callback (dump mode: three periods; recorder mode: 0.25)")
    ap.add_argument("--rate", type=int, default=48000, help="the endpoint/dump sample rate")
    ap.add_argument("--min-corr", type=float, default=0.5, help="envelope correlation under which attributions are flagged")
    a = ap.parse_args(argv)
    with open(a.trace, "r", encoding="utf-8", errors="replace") as fh:
        header, rows, skipped = parse(fh.read())
    if not rows:
        print("no callback rows in", a.trace)
        return 1
    period = header.get("period_us", 20000)
    late = late_callbacks(rows, header.get("late_us", 60000), header.get("dry_us", 80000), period)
    attributions = None
    alignment = None
    if a.dips:
        with open(a.dips, "r", encoding="utf-8", errors="replace") as fh:
            dips, alignment = parse_dips(fh.read())
        if a.first_packet is not None:
            attributions = attribute_by_recorder(dips, late, header.get("t0_epoch_us", 0), a.first_packet, a.rate,
                                                 tolerance_s=a.tolerance if a.tolerance is not None else 0.25)
        elif a.recorder_start is not None:
            print("WARNING: --recorder-start is the recorder's start, not the file's first frame; using it anyway "
                  "(pass --recorder-first-packet from loopback.log for the file's own clock)")
            attributions = attribute_by_recorder(dips, late, header.get("t0_epoch_us", 0), a.recorder_start + 1024 / a.rate,
                                                 a.rate, tolerance_s=a.tolerance if a.tolerance is not None else 0.25)
        else:
            attributions = attribute_by_dump(dips, rows, late, period, a.rate, a.tolerance)
    print(report(header, rows, skipped, late, attributions, alignment=alignment, min_corr=a.min_corr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
