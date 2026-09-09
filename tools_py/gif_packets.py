#!/usr/bin/env python
"""Parse the packet file written by vu1_replay (records of uint32 length + GIF packet bytes) and list
the vertices it kicks: PACKED-mode XYZ2/XYZF2 with the current RGBAQ/ST state, ADC flag and the
sign of q. Summarises per packet and overall (vertices, kicked, q<0, degenerate triangles).

Usage: python tools_py/gif_packets.py vu1_packets.bin [--verts] [--limit N]
"""
import argparse
import struct
import sys


def parse_packet(data):
    """Yield (regname, fields) for a PACKED/REGLIST GIF packet; IMAGE data is skipped."""
    pos = 0
    n = len(data)
    while pos + 16 <= n:
        lo, hi = struct.unpack_from("<QQ", data, pos)
        pos += 16
        nloop = lo & 0x7FFF
        eop = (lo >> 15) & 1
        pre = (lo >> 46) & 1
        prim = (lo >> 47) & 0x7FF
        flg = (lo >> 58) & 3
        nreg = (lo >> 60) & 0xF or 16
        regs = [(hi >> (4 * i)) & 0xF for i in range(nreg)]
        yield ("TAG", {"nloop": nloop, "eop": eop, "pre": pre, "prim": prim, "flg": flg, "regs": regs})
        if flg == 0:  # PACKED
            for _ in range(nloop):
                for r in regs:
                    if pos + 16 > n:
                        return
                    a, b = struct.unpack_from("<QQ", data, pos)
                    pos += 16
                    if r == 0x0:
                        yield ("PRIM", {"prim": a & 0x7FF})
                    elif r == 0x1:
                        yield ("RGBAQ", {"r": a & 0xFF, "g": (a >> 32) & 0xFF, "b": b & 0xFF, "a": (b >> 32) & 0xFF})
                    elif r == 0x2:
                        s, t, q = struct.unpack("<fff", struct.pack("<III", a & 0xFFFFFFFF, (a >> 32) & 0xFFFFFFFF, b & 0xFFFFFFFF))
                        yield ("ST", {"s": s, "t": t, "q": q})
                    elif r == 0x3:
                        yield ("UV", {"u": a & 0x3FFF, "v": (a >> 32) & 0x3FFF})
                    elif r == 0x4:
                        yield ("XYZF2", {"x": a & 0xFFFF, "y": (a >> 32) & 0xFFFF, "z": (b >> 4) & 0xFFFFFF, "f": (b >> 36) & 0xFF, "adc": (b >> 47) & 1})
                    elif r == 0x5:
                        yield ("XYZ2", {"x": a & 0xFFFF, "y": (a >> 32) & 0xFFFF, "z": b & 0xFFFFFFFF, "adc": (b >> 47) & 1})
                    elif r == 0xA:
                        yield ("FOG", {"f": (b >> 36) & 0xFF})
                    elif r == 0xE:
                        yield ("AD", {"addr": b & 0xFF, "data": a})
                    else:
                        yield ("REG%x" % r, {"lo": a, "hi": b})
        elif flg == 1:  # REGLIST
            count = nloop * nreg
            qwords = (count + 1) // 2
            pos += qwords * 16
            yield ("REGLIST", {"count": count})
        else:  # IMAGE
            pos += nloop * 16
            yield ("IMAGE", {"qwords": nloop})
        if eop:
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--verts", action="store_true", help="print every vertex")
    ap.add_argument("--limit", type=int, default=0, help="stop after N packets")
    a = ap.parse_args()
    blob = open(a.file, "rb").read()
    pos = 0
    pk = 0
    tot = {"verts": 0, "kick": 0, "qneg": 0, "adc": 0, "tris": 0, "degen": 0}
    while pos + 4 <= len(blob):
        (ln,) = struct.unpack_from("<I", blob, pos)
        pos += 4
        data = blob[pos:pos + ln]
        pos += ln
        pk += 1
        q = 1.0
        prim = None
        verts = 0
        kicked = 0
        qneg = 0
        adc = 0
        kicked_list = []
        for name, f in parse_packet(data):
            if name == "TAG" and f["pre"]:
                prim = f["prim"] & 7
            elif name == "PRIM":
                prim = f["prim"] & 7
            elif name == "ST":
                q = f["q"]
            elif name in ("XYZ2", "XYZF2"):
                verts += 1
                if f["adc"]:
                    adc += 1
                else:
                    kicked += 1
                    kicked_list.append((f["x"] / 16.0, f["y"] / 16.0, f["z"], q))
                if q < 0:
                    qneg += 1
                if a.verts:
                    print(f"  pk{pk} {name} x={f['x']/16:.1f} y={f['y']/16:.1f} z={f['z']} q={q:.5f} adc={f['adc']}")
        tris = 0
        degen = 0
        if prim in (3, 4, 5):  # triangle list / strip / fan: count kicked triples for lists
            step = 3 if prim == 3 else 1
            for i in range(0, len(kicked_list) - 2, step) if prim == 3 else range(len(kicked_list) - 2):
                v = kicked_list[i:i + 3]
                tris += 1
                if v[0][:2] == v[1][:2] == v[2][:2]:
                    degen += 1
        tot["verts"] += verts; tot["kick"] += kicked; tot["qneg"] += qneg; tot["adc"] += adc; tot["tris"] += tris; tot["degen"] += degen
        print(f"pk{pk}: {ln} bytes prim={prim} verts={verts} kicked={kicked} adc={adc} q<0={qneg} tris={tris} degenerate={degen}")
        if a.limit and pk >= a.limit:
            break
    print("total:", tot)


if __name__ == "__main__":
    main()
