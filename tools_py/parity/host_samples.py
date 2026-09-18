"""Read run_detached.sh's host sampler CSV (marker.cpu.csv).

Sprint 7 Task 1b: the sampler writes one row per second,

    <ISO timestamp>,<total CPU %>,<per-process CPU %>,<per-process working set MB>

where the last two fields are ';'-joined "name=value" lists and the fourth field is new with this
task (rows written before it, and rows written while no game process was running, have three fields
or an empty fourth). working_set_rise_mb is the bar the bounded command queue is measured against:
how far the game's working set rose above where it started during a 30 s title-bar drag.

Run it over a marker's CSV:

    python -m tools_py.parity.host_samples logs/s7_drag.marker.cpu.csv --max-rise-mb 200
"""

import argparse
import sys

DEFAULT_PREFIX = "socom2"


def _pairs(field):
    """'a=1.0;b=2' -> {'a': 1.0, 'b': 2.0}; unparsable entries are skipped."""
    out = {}
    for entry in field.split(";"):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, _, value = entry.partition("=")
        # The sampler writes plain numbers, but a PowerShell format string under another culture can
        # still emit a thousands separator: strip it rather than lose the row.
        value = value.replace(",", "").replace(" ", "").strip()
        try:
            out[name.strip()] = float(value)
        except ValueError:
            continue
    return out


def parse_text(text):
    """CSV text -> [{'t': str, 'cpu_pct': float|None, 'cpu_proc': {name: pct}, 'ws_mb': {name: MB}}]."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # At most four fields: anything after the third comma belongs to the working-set list.
        parts = line.split(",", 3)
        if len(parts) < 2:
            continue
        try:
            cpu_pct = float(parts[1])
        except ValueError:
            cpu_pct = None
        rows.append({
            "t": parts[0],
            "cpu_pct": cpu_pct,
            "cpu_proc": _pairs(parts[2]) if len(parts) > 2 else {},
            "ws_mb": _pairs(parts[3]) if len(parts) > 3 else {},
        })
    return rows


def parse(csv_path):
    with open(csv_path, "r", encoding="utf-8", errors="replace") as handle:
        return parse_text(handle.read())


def _totals(rows, prefix):
    return [sum(mb for name, mb in row["ws_mb"].items() if name.startswith(prefix)) for row in rows]


def working_set_rise_mb(rows, prefix=DEFAULT_PREFIX):
    """Peak total working set of the matching processes minus the first row's, in MB (0.0 with no rows)."""
    totals = _totals(rows, prefix)
    if not totals:
        return 0.0
    return float(max(totals) - totals[0])


def peak_working_set_mb(rows, prefix=DEFAULT_PREFIX):
    totals = _totals(rows, prefix)
    return float(max(totals)) if totals else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser(description="working-set rise from a run_detached.sh sampler CSV")
    ap.add_argument("csv")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX, help="process name prefix (default socom2)")
    ap.add_argument("--max-rise-mb", type=float, default=None, help="exit 1 above this rise")
    args = ap.parse_args(argv)
    rows = parse(args.csv)
    rise = working_set_rise_mb(rows, args.prefix)
    peak = peak_working_set_mb(rows, args.prefix)
    print(f"rise_mb={rise:.1f} peak_mb={peak:.1f} rows={len(rows)}")
    if args.max_rise_mb is not None and rise > args.max_rise_mb:
        print(f"host_samples: rise {rise:.1f} MB is over the {args.max_rise_mb:.1f} MB bar")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
