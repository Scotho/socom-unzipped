"""Tiny UDP DNS responder for the PCSX2 guest: answers the SOCOM II / DNAS hostnames with the
Horizon host address and NXDOMAIN for everything else. Run as Administrator (binds UDP 53 on the
LAN address). Usage: python -m tools_py.parity.dns_stub [--bind 192.168.2.10] [--answer 192.168.2.10]
"""
import argparse
import socket
import struct

NAMES = {
    "socom2-prod.pdonline.scea.com",
    "socom2-prod.muis.pdonline.scea.com",
    "gate1.us.dnas.playstation.org",
    "gate1.jp.dnas.playstation.org",
    "gate1.eu.dnas.playstation.org",
    "www.playstation.org",
}


def parse_name(data, off):
    labels = []
    while True:
        n = data[off]
        off += 1
        if n == 0:
            break
        labels.append(data[off:off + n].decode("ascii", "replace"))
        off += n
    return ".".join(labels), off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="192.168.2.10")
    ap.add_argument("--answer", default="192.168.2.10")
    ap.add_argument("--port", type=int, default=53)
    ap.add_argument("--all", action="store_true", help="answer every name with --answer")
    a = ap.parse_args()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((a.bind, a.port))
    print(f"dns_stub listening on {a.bind}:{a.port}, answering {a.answer}", flush=True)
    ip = bytes(int(x) for x in a.answer.split("."))
    while True:
        data, addr = s.recvfrom(512)
        if len(data) < 12:
            continue
        tid = data[:2]
        qd = struct.unpack(">H", data[4:6])[0]
        name, off = parse_name(data, 12)
        qtype, qclass = struct.unpack(">HH", data[off:off + 4])
        question = data[12:off + 4]
        known = a.all or name.lower() in NAMES
        if known and qtype == 1:
            flags = 0x8180
            ans = b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4) + ip
            resp = tid + struct.pack(">HHHHH", flags, 1, 1, 0, 0) + question + ans
        else:
            flags = 0x8183  # NXDOMAIN
            resp = tid + struct.pack(">HHHHH", flags, 1, 0, 0, 0) + question
        s.sendto(resp, addr)
        print(f"{addr[0]} {name} type={qtype} -> {'A ' + a.answer if known and qtype == 1 else 'NXDOMAIN'}", flush=True)


if __name__ == "__main__":
    main()
