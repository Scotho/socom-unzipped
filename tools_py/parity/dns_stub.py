"""Tiny UDP DNS responder for the PCSX2 guest: answers the SOCOM II / DNAS hostnames with the
Horizon host address and NXDOMAIN for everything else. Run as Administrator (binds UDP 53 on the
LAN address). Usage: python -m tools_py.parity.dns_stub [--bind IP] [--answer IP]

--bind/--answer default to the SOCOM_SERVER_IP environment variable (scripts/parity/env.sh, the one knob
that points the harness at another server). There is no LAN default (Sprint 13 Task H6): unset, or set to a
NAME -- env.sh's default is the hosted box's, socom.scotho.com -- the stub refuses with the sentence, because
it has to bind the address and put it in an A record, and a hostname can be neither.
"""
import argparse
import os
import re
import socket
import struct
import sys

DEFAULT_IP = os.environ.get("SOCOM_SERVER_IP")
_IPV4 = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")


def ipv4_problem(flag, value):
    """None when `value` is a dotted IPv4 address, else the sentence that refuses it."""
    if value and _IPV4.fullmatch(value) and all(int(x) <= 255 for x in value.split(".")):
        return None
    return ("dns_stub: %s is %r -- set SOCOM_SERVER_IP to the LAN IP the DNS stub serves (or pass %s "
            "an IPv4 address): the stub binds it and answers the console with it, so a hostname such as "
            "the hosted socom.scotho.com cannot stand in" % (flag, value or "<unset>", flag))

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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default=DEFAULT_IP)
    ap.add_argument("--answer", default=DEFAULT_IP)
    ap.add_argument("--port", type=int, default=53)
    ap.add_argument("--all", action="store_true", help="answer every name with --answer")
    a = ap.parse_args(argv)
    problems = [p for p in (ipv4_problem("--bind", a.bind), ipv4_problem("--answer", a.answer)) if p]
    if problems:
        sys.stderr.write("\n".join(problems) + "\n")
        return 2
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
    sys.exit(main())
