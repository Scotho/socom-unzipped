#!/usr/bin/env python
"""Poll guest memory over PINE while PCSX2 runs (tools_py.parity.drive --target pcsx2 in another
shell). Each --spec is a pointer chain in the exe's PS2X_PEEK syntax: "*0xADDR+0xOFF*+0xOFF2:words"
('*' follows the pointer at the current address, "+0x.." adds an offset, in the order written).
One line per sample: wall time since start, then per spec "@addr: hex(float) ...", the same layout
as our exe's [peek] lines, so the two sides diff field by field.

Default spec: the mission camera object (static scene 0x4887c0 + 0x628 -> pointer), 96 words from
+0x120.

Usage: python -m tools_py.parity.cam_poll --out logs/parity/cam_pcsx2.txt [--seconds 330]
           [--every 5] [--spec "*0x488de8+0x120:96"] [--spec "*0x488de8+0xbc*+0x1070:64"]
"""
import argparse
import configparser
import os
import struct
import time

from tools_py.parity.pine import Pine

DEFAULT_SPEC = "*0x488de8+0x120:96"


def pine_port():
    ini = os.path.join("tools", "pcsx2", "inis", "PCSX2.ini")
    cp = configparser.ConfigParser(strict=False)
    cp.read(ini)
    for sec in cp.sections():
        for k, v in cp.items(sec):
            if k.lower() == "pineslot":
                return int(v)
    return 28011


def resolve(read32, spec):
    """Walk a pointer chain; returns (addr, words) or (None, words) when a pointer is null."""
    words = 1
    if ":" in spec:
        spec, w = spec.rsplit(":", 1)
        words = int(w, 0)
    addr = 0
    i = 0
    have_base = False

    def number_at(j):
        k = j
        while k < len(spec) and spec[k] not in "*+":
            k += 1
        return int(spec[j:k], 0), k

    while i < len(spec):
        ch = spec[i]
        if ch == "*":
            if not have_base:
                addr, i = number_at(i + 1)
                have_base = True
            else:
                i += 1
            if not (0x100000 <= addr < 0x2000000):
                return None, words
            addr = read32(addr)
            if addr == 0:
                return None, words
        elif ch == "+":
            off, i = number_at(i + 1)
            addr += off
        else:
            addr, i = number_at(i)
            have_base = True
    return addr, words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=330.0)
    ap.add_argument("--every", type=float, default=5.0)
    ap.add_argument("--spec", action="append", default=None)
    a = ap.parse_args()
    specs = a.spec or [DEFAULT_SPEC]
    port = pine_port()
    t0 = time.time()
    p = None
    while p is None and time.time() - t0 < 120:
        try:
            p = Pine(port=port)
        except OSError:
            time.sleep(1.0)
    if p is None:
        raise SystemExit(f"no PINE on port {port}")
    with open(a.out, "w") as f:
        f.write(f"# PINE port {port}; specs {specs}\n")
        while time.time() - t0 < a.seconds:
            try:
                line = f"t={time.time() - t0:6.1f}"
                for spec in specs:
                    addr, words = resolve(p.read32, spec)
                    if addr is None:
                        continue
                    line += f" @{addr:x}:"
                    for w in range(words):
                        v = p.read32(addr + w * 4)
                        fv = struct.unpack("<f", struct.pack("<I", v))[0]
                        line += f" {v:08x}({fv:g})"
                f.write(line + "\n")
                f.flush()
            except Exception as e:  # noqa: BLE001 - PCSX2 may be between states
                f.write(f"t={time.time() - t0:6.1f} error {e}\n")
                f.flush()
                try:
                    p.close()
                except Exception:  # noqa: BLE001
                    pass
                p = None
                while p is None and time.time() - t0 < a.seconds:
                    try:
                        p = Pine(port=port)
                    except OSError:
                        time.sleep(1.0)
                if p is None:
                    break
            time.sleep(a.every)


if __name__ == "__main__":
    main()
