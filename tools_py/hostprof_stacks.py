#!/usr/bin/env python
"""Fold and symbolize the call stacks of a PS2X_HOST_PROF_STACKS=1 histogram (logs/hostprof.txt
"stack <count> leaf;caller;..." lines, raw addresses).

Usage: python tools_py/hostprof_stacks.py [logs/hostprof.txt] [--exe dist/socom2.exe] [--top 30]
Prints: inclusive samples per exe function (the function appears anywhere in the stack), the exe
callers of samples whose leaf is in another module (where the DLL time comes from), and the top
folded stacks.
"""
import argparse
import bisect
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hostprof_symbolize import image_base, symbols, demangle  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hist", nargs="?", default=os.path.join("logs", "hostprof.txt"))
    ap.add_argument("--exe", default=os.path.join("dist", "socom2.exe"))
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--depth", type=int, default=6)
    a = ap.parse_args()
    linkBase = image_base(a.exe)
    syms = symbols(a.exe)
    addrs = [s[0] for s in syms]
    stacks = []
    loadBase = 0
    with open(a.hist) as f:
        header = f.readline().split()
        loadBase = int(header[1], 16)
        for line in f:
            if not line.startswith("stack "):
                continue
            parts = line.split()
            n = int(parts[1])
            frames = [int(x, 16) for x in parts[2].split(";")]
            stacks.append((n, frames))
    total = sum(n for n, _ in stacks)
    cache = {}

    def sym(va):
        if va in cache:
            return cache[va]
        if loadBase <= va < loadBase + 0x10000000:
            i = bisect.bisect_right(addrs, linkBase + (va - loadBase)) - 1
            name = syms[i][1] if i >= 0 else f"<{va - loadBase:#x}>"
        else:
            name = "<ext>"
        cache[va] = name
        return name

    inclusive = collections.Counter()
    extCallers = collections.Counter()
    folded = collections.Counter()
    for n, frames in stacks:
        names = [sym(v) for v in frames]
        seen = set()
        for nm in names:
            if nm not in seen:
                seen.add(nm)
                inclusive[nm] += n
        if names[0] == "<ext>":
            caller = next((nm for nm in names if nm != "<ext>"), "<ext only>")
            extCallers[caller] += n
        folded[";".join(names[:a.depth])] += n
    allNames = set(inclusive) | set(extCallers)
    for k in folded:
        allNames.update(k.split(";"))
    dm = demangle([x for x in allNames if x.startswith("_Z")])

    def d(nm):
        return dm.get(nm, nm)

    print(f"stack samples {total}")
    print("--- inclusive (function anywhere in the stack)")
    for nm, n in inclusive.most_common(a.top):
        print(f"{100.0 * n / max(1, total):6.2f}%  {n:7d}  {d(nm)[:150]}")
    print("--- exe callers of samples whose leaf is in another module")
    for nm, n in extCallers.most_common(a.top):
        print(f"{100.0 * n / max(1, total):6.2f}%  {n:7d}  {d(nm)[:150]}")
    print("--- top folded stacks (leaf first)")
    for k, n in folded.most_common(a.top):
        print(f"{100.0 * n / max(1, total):6.2f}%  {n:7d}  " + " <- ".join(d(x)[:60] for x in k.split(";")))


if __name__ == "__main__":
    main()
