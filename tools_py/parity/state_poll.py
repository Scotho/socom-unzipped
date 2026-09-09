#!/usr/bin/env python
"""Launch PCSX2, load a savestate over PINE and sample pointer-chain specs (PS2X_PEEK syntax) as
fast as PINE allows. One line per sample in the [peek] layout of our exe.

Usage: python -m tools_py.parity.state_poll --slot 8 --out logs/parity/x.txt --seconds 60
           --spec "0x416050:20" --spec "*0x416098:16"
"""
import argparse
import os
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools_py.parity.pine import Pine  # noqa: E402
from tools_py.parity.cam_poll import pine_port, resolve  # noqa: E402
from tools_py.parity.drive import PCSX2, ISO  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=int, default=8)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--boot", type=float, default=25.0)
    ap.add_argument("--spec", action="append", required=True)
    a = ap.parse_args()
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
    n = 0
    with open(a.out, "w") as out:
        t1 = time.time()
        while time.time() - t1 < a.seconds:
            try:
                line = f"t={time.time() - t1:7.3f}"
                for spec in a.spec:
                    addr, words = resolve(p.read32, spec)
                    if addr is None:
                        continue
                    line += f" @{addr:x}:"
                    for w in range(words):
                        v = p.read32(addr + w * 4)
                        fv = struct.unpack("<f", struct.pack("<I", v))[0]
                        line += f" {v:08x}({fv:g})"
                out.write(line + "\n")
                n += 1
            except Exception as e:  # noqa: BLE001
                out.write(f"error {e}\n")
                time.sleep(0.5)
    print(f"{n} samples -> {a.out}")
    proc.kill()


if __name__ == "__main__":
    main()
