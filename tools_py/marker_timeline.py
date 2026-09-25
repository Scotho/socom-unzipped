#!/usr/bin/env python
"""Merge a run log's game-thread events into one ordered stream for the texture-set marker
protocol: FrameBegin / AppendFlush / AppendRebase / AppendMarker / Vif1Irq call-trace lines
(PS2X_CALL_TRACE), VIF1 i-bit stalls and STC resumes (PS2X_TRACE_FIFO), GIF/SPR DMA kicks, and
the [gif-submit] events that matter (marker DIRECT packets, set flushes, background uploads,
label / background texture binds; PS2X_GIF_TRACE).

Run: python -m tools_py.marker_timeline logs/run_X.log [--from-frame N] [--frames M]
"""
import argparse
import re

RE_CALL = re.compile(r"\[call\] +([0-9.]+)s (\w+) #(\d+) a0=(0x[0-9a-f]+) a1=(0x[0-9a-f]+)")
RE_SUB = re.compile(r"\[gif-submit\] path(\d) bytes=(\d+) .*?tag nloop=(\d+) eop=(\d+)")
RE_BLT = re.compile(r"bitblt dbp=([0-9a-f]+) dbw=(\d+) trx=(\d+)x(\d+)")
RE_TEX = re.compile(r"tex0 tbp0=([0-9a-f]+)")
LABELS = {0x3207, 0x3247, 0x3287, 0x3107, 0x3147, 0x3187, 0x31c7, 0x32c7, 0x3307, 0x3347, 0x3387}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--from-frame", type=int, default=0)
    ap.add_argument("--frames", type=int, default=3)
    a = ap.parse_args()
    frame = -1
    out = []
    for line in open(a.log, errors="replace"):
        ev = None
        if line.startswith("[call]"):
            m = RE_CALL.search(line)
            if not m:
                continue
            t, name, n, a0, a1 = m.groups()
            if name == "FrameBegin":
                frame += 1
                ev = f"===== FrameBegin #{n} t={t}s"
            elif name == "Vif1Irq":
                ev = f"  HANDLER Vif1Irq cause={int(a0, 16)}"
            else:
                ev = f"  {name} set={a1}"
        elif line.startswith("[fifo] VIF1 interrupt"):
            ev = "    vif1: i-bit code " + line.split("VIFcode")[1].strip()
        elif line.startswith("[fifo] VIF1 i-bit stall"):
            ev = "    vif1: STALL"
        elif line.startswith("[fifo] VIF1 STC"):
            ev = "    vif1: STC resume"
        elif line.startswith("[fifo] CHCR w ch=1000a000"):
            mm = re.search(r"tadr=([0-9a-f]+)", line); ev = "    KICK GIF chain " + (mm.group(1) if mm else "?")
        elif line.startswith("[gif-submit]"):
            m = RE_SUB.search(line)
            if not m:
                continue
            path, size, nloop, eop = m.groups()
            mb = RE_BLT.search(line)
            mt = RE_TEX.search(line)
            if path == "2" and size == "16" and nloop == "0":
                ev = "    -- marker (PATH2 empty DIRECT) --"
            elif mb:
                dbp = int(mb.group(1), 16)
                w, h = mb.group(3), mb.group(4)
                if dbp == 0x2fcc and int(size) > 100000:
                    ev = "    P3 upload SET11 (labels)"
                elif w == "512" and h == "256":
                    ev = f"    P3 upload BG 512x256 -> {mb.group(1)}{' OVERLAPS LABELS' if dbp == 0x2bc0 else ''}"
            if mt:
                t0 = int(mt.group(1), 16)
                if t0 in LABELS:
                    ev = (ev + "; " if ev else "    ") + f"P{path} bind label {mt.group(1)}"
                elif t0 in (0x2bc0, 0x33d9):
                    ev = (ev + "; " if ev else "    ") + f"P{path} bind BG {mt.group(1)}"
        if ev is None:
            continue
        if frame < a.from_frame:
            continue
        if frame >= a.from_frame + a.frames:
            break
        out.append(ev)
    print("\n".join(out))


if __name__ == "__main__":
    main()
