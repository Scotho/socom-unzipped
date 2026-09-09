#!/usr/bin/env python
"""Poll the collision query object on PCSX2 at a savestate: launch PCSX2, load the state over
PINE and sample the persistent query (world = *(0x45c380), query = *(world+0x14c): ray start +4,
end +0x10, hit count +0x34, hits *(+0x48) as 0x20-byte records) plus the player position, many
times per second, so the vertical ground probes (start.y == +50000) of every actor get caught.

Usage: python -m tools_py.parity.probe_poll --slot 8 --out logs/parity/probe_pcsx2.txt [--seconds 60]
Then: python -m tools_py.parity.probe_poll --filter logs/parity/probe_pcsx2.txt --x 939.4 --z 832.2
"""
import argparse
import os
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools_py.parity.pine import Pine  # noqa: E402
from tools_py.parity.cam_poll import pine_port  # noqa: E402
from tools_py.parity.drive import PCSX2, ISO  # noqa: E402


def f(v):
    return struct.unpack("<f", struct.pack("<I", v))[0]


def poll(a):
    proc = subprocess.Popen([PCSX2, "-batch", "-nogui", "-fastboot", ISO])
    port = pine_port()
    t0 = time.time()
    p = None
    while p is None and time.time() - t0 < 120:
        try:
            p = Pine(port=port)
        except OSError:
            time.sleep(1.0)
    if p is None:
        proc.kill()
        raise SystemExit("no PINE")
    time.sleep(a.boot)
    p.load_state(a.slot)
    time.sleep(4.0)
    world = p.read32(0x45c380)
    q = p.read32(world + 0x14c)
    hits = p.read32(q + 0x48)
    n = 0
    with open(a.out, "w") as out:
        out.write(f"# world={world:#x} query={q:#x} hits={hits:#x}\n")
        t1 = time.time()
        while time.time() - t1 < a.seconds:
            try:
                start = [f(p.read32(q + 4 + 4 * i)) for i in range(3)]
                if start[1] != 50000.0:
                    continue
                cnt = p.read32(q + 0x34)
                rec = []
                for i in range(min(cnt, 4)):
                    h = hits + 0x20 * i
                    rec.append([f(p.read32(h + 4 * j)) for j in range(3)] + [p.read32(h + 0xc)] +
                               [f(p.read32(h + 0x10 + 4 * j)) for j in range(3)] + [p.read32(h + 0x1c)])
                ply = [f(p.read32(0x416054 + 4 * i)) for i in range(3)]
                out.write(f"t={time.time() - t1:6.2f} player={ply} start={start} count={cnt} hits={rec}\n")
                n += 1
            except Exception as e:  # noqa: BLE001
                out.write(f"error {e}\n")
                time.sleep(0.5)
    print(f"{n} vertical probes sampled -> {a.out}")
    proc.kill()


def filt(a):
    seen = {}
    for line in open(a.filter):
        if not line.startswith("t="):
            continue
        start = eval(line.split("start=")[1].split(" count=")[0])  # noqa: S307 - our own file
        if abs(start[0] - a.x) < a.tol and abs(start[2] - a.z) < a.tol:
            key = line.split("hits=")[1].strip()
            seen[key] = seen.get(key, 0) + 1
            if seen[key] == 1:
                print(line.strip())
    print({k[:60]: v for k, v in seen.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=int, default=8)
    ap.add_argument("--out")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--boot", type=float, default=25.0, help="seconds to wait before loading the state")
    ap.add_argument("--filter", help="filter an existing poll file for probes at --x/--z")
    ap.add_argument("--x", type=float, default=939.4)
    ap.add_argument("--z", type=float, default=832.2)
    ap.add_argument("--tol", type=float, default=1.5)
    a = ap.parse_args()
    if a.filter:
        filt(a)
    else:
        poll(a)


if __name__ == "__main__":
    main()
