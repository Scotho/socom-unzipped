#!/usr/bin/env python
"""Poll SOCOM II's camera object over PINE while PCSX2 runs (tools_py.parity.drive --target pcsx2
in another shell): every --every seconds read the camera pointer at CAMERA_SLOT (static scene
object 0x4887c0 + 0x628) and dump --words words from CAMERA_BASE_OFFSET as hex + float, one line
per sample with the wall time since the poller started. Same layout as our exe's
PS2X_PEEK="*0x488de8+0x120:96" lines, so the two sides can be diffed field by field.

Usage: python -m tools_py.parity.cam_poll --out logs/parity/cam_pcsx2.txt [--seconds 330]
"""
import argparse
import configparser
import os
import struct
import time

from tools_py.parity.pine import Pine

CAMERA_SLOT = 0x488DE8
CAMERA_BASE_OFFSET = 0x120


def pine_port():
    ini = os.path.join("tools", "pcsx2", "inis", "PCSX2.ini")
    cp = configparser.ConfigParser(strict=False)
    cp.read(ini)
    for sec in cp.sections():
        for k, v in cp.items(sec):
            if k.lower() == "pineslot":
                return int(v)
    return 28011


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=330.0)
    ap.add_argument("--every", type=float, default=5.0)
    ap.add_argument("--words", type=int, default=96)
    a = ap.parse_args()
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
        f.write(f"# PINE port {port}; camera slot {CAMERA_SLOT:#x} +{CAMERA_BASE_OFFSET:#x}, {a.words} words\n")
        while time.time() - t0 < a.seconds:
            try:
                cam = p.read32(CAMERA_SLOT)
                line = f"t={time.time() - t0:6.1f} cam={cam:08x}"
                if 0x100000 <= cam < 0x2000000:
                    words = []
                    for w in range(a.words):
                        v = p.read32(cam + CAMERA_BASE_OFFSET + w * 4)
                        fv = struct.unpack("<f", struct.pack("<I", v))[0]
                        words.append(f"{v:08x}({fv:g})")
                    line += " " + " ".join(words)
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
