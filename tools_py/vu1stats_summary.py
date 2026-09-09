#!/usr/bin/env python
"""Summarize the [vu1-stats] lines of a run log (PS2X_VU_STATS=1): per-30 s phases and the last
60 s (the mission), plus the [vu1-bail] pcs (PS2X_VU1_BAILHIST=1) and images without generated code.

Usage: python tools_py/vu1stats_summary.py [logs/run_....log]   (default: newest logs/run_*.log)
"""
import glob
import os
import re
import statistics as st
import sys


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else max(glob.glob(os.path.join("logs", "run_*.log")), key=os.path.getmtime)
    pat = re.compile(r"programs/s=(\d+) cycles/s=(\d+) host=(\d+) ms/s \(([\d.]+) ns/cycle\) flips/s=([\d.]+) syncv/s=([\d.]+)"
                     r"(?: thread=(\d+) ms/s proc=(\d+) ms/s)?(?: interp-programs/s=(\d+))?(?: handbacks/s=(\d+))?")
    vals = []
    bails = {}
    unknown = []
    for line in open(path, errors="replace"):
        m = pat.search(line)
        if m:
            vals.append(tuple(float(x) if x is not None else 0.0 for x in m.groups()))
            continue
        b = re.search(r"\[vu1-bail\] pc=(0x[0-9a-f]+) count=(\d+)", line)
        if b:
            bails[b.group(1)] = int(b.group(2))
        if "has no generated code" in line:
            unknown.append(line.strip())
    print(path, f"{len(vals)} stats lines")

    def row(tag, b):
        if not b:
            return
        print(f"{tag}: syncv/s={st.mean(v[5] for v in b):5.1f} cycles/s={st.mean(v[1] for v in b) / 1e6:5.1f}M "
              f"ns/cycle={st.mean(v[3] for v in b):5.1f} vu1host={st.mean(v[2] for v in b):4.0f} ms/s "
              f"thread={st.mean(v[6] for v in b):4.0f} proc={st.mean(v[7] for v in b):4.0f} "
              f"interp={st.mean(v[8] for v in b):5.0f}/s handbacks={st.mean(v[9] for v in b):5.0f}/s "
              f"cycles/frame={st.mean(v[1] for v in b) / max(0.1, st.mean(v[5] for v in b)) / 1e6:5.2f}M")

    for i in range(0, len(vals), 30):
        row(f"t={i:3d}-{i + 30:3d}s", vals[i:i + 30])
    row("last 60 s   ", vals[-60:])
    if bails:
        print("hand-back pcs:", " ".join(f"{k}:{v}" for k, v in sorted(bails.items(), key=lambda kv: -kv[1])))
    for u in unknown:
        print(u)


if __name__ == "__main__":
    main()
