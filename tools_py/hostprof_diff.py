#!/usr/bin/env python
"""Symbolize the difference of two PS2X_HOST_PROF histograms (end minus start): the samples taken
between the two snapshots, e.g. the mission phase of a run when the file was copied at load time.

Run: python -m tools_py.hostprof_diff logs/hostprof_pre.txt logs/hostprof_end.txt [--top 40]
       [--exe dist/socom2.exe] [--by-file]  (--by-file groups generated EE functions by source file
       prefix "FUN_" vs runtime)
"""
import argparse
import bisect
import collections
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hostprof_symbolize import image_base, symbols, demangle  # noqa: E402


def load(path):
    counts = {}
    ext = {}
    with open(path) as f:
        f.readline()
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            rva = int(parts[0], 16)
            n = int(parts[1])
            if len(parts) > 2 and parts[2] == "ext":
                ext[rva] = n
            else:
                counts[rva] = n
    return counts, ext


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("start")
    ap.add_argument("end")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--exe", default=os.path.join("dist", "socom2.exe"))
    a = ap.parse_args()
    c0, e0 = load(a.start)
    c1, e1 = load(a.end)
    base = image_base(a.exe)
    syms = symbols(a.exe)
    addrs = [s[0] for s in syms]
    per_fn = collections.Counter()
    total = 0
    for rva, n in c1.items():
        d = n - c0.get(rva, 0)
        if d <= 0:
            continue
        total += d
        i = bisect.bisect_right(addrs, base + rva) - 1
        per_fn[syms[i][1] if i >= 0 else f"<{rva:#x}>"] += d
    extd = sum(max(0, n - e0.get(r, 0)) for r, n in e1.items())
    total += extd
    per_fn["<other module (system DLL / GL driver)>"] += extd
    names = [k for k, _ in per_fn.most_common(a.top)]
    dm = demangle(names)
    gen = sum(n for k, n in per_fn.items() if k.startswith("FUN_") or k.startswith("_FUN_"))
    print(f"samples in phase {total} (other modules {extd}, generated EE functions {gen})")
    for name, n in per_fn.most_common(a.top):
        print(f"{100.0 * n / max(1, total):6.2f}%  {n:7d}  {dm.get(name, name)}")


if __name__ == "__main__":
    main()
