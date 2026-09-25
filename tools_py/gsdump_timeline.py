#!/usr/bin/env python
"""Timeline of a PCSX2 GS dump (.gs, uncompressed): per frame, every GIF transfer by path with
its uploads (BITBLTBUF/TRXREG/TRXDIR + IMAGE bytes), texture binds (TEX0) and vertex kicks, so
the console's ordering of texture uploads vs draws can be compared with our [gs-pages] trace.

Run: python -m tools_py.gsdump_timeline <dump.gs> [--pages 0x15e:64] [--frames 0-7] [--all]
  --pages P:N   only print events touching VRAM pages P..P+N-1 (uploads by dbp, binds by tbp0)
  --all         print every packet (default: only uploads, binds and kicks)
"""
import argparse
import struct
import sys

PATH_NAMES = {0: "P1", 1: "P2", 2: "P3", 3: "P1"}
BPP = {0x00: 32, 0x01: 24, 0x02: 16, 0x0A: 16, 0x13: 8, 0x14: 4, 0x1B: 8, 0x24: 4, 0x2C: 4,
       0x30: 32, 0x31: 24, 0x32: 16, 0x3A: 16}


def page_span(psm, bw, height):
    """Pages covered by a `bw` (64-px units) wide, `height` rows tall region: page = 8 KB."""
    bpp = BPP.get(psm, 32)
    page_h = {32: 32, 24: 32, 16: 64, 8: 64, 4: 128}[bpp]
    page_w = {32: 64, 24: 64, 16: 64, 8: 128, 4: 128}[bpp]
    rows = (height + page_h - 1) // page_h
    cols = max(1, (bw * 64 + page_w - 1) // page_w)
    return rows * cols


def find_packets(d):
    n = len(d)

    def parse(off):
        p = off
        pk = []
        while p < n:
            i = d[p]
            if i == 0:
                if p + 6 > n:
                    return None
                path = d[p + 1]
                size = struct.unpack_from("<I", d, p + 2)[0]
                if path > 3 or size == 0 or p + 6 + size > n:
                    return None
                pk.append(("T", path, p + 6, size))
                p += 6 + size
            elif i == 1:
                pk.append(("V", d[p + 1]))
                p += 2
            elif i == 2:
                pk.append(("F", struct.unpack_from("<I", d, p + 1)[0]))
                p += 5
            elif i == 3:
                pk.append(("R", p + 1))
                p += 1 + 8192
            else:
                return None
        return pk

    magic = struct.unpack_from("<I", d, 0)[0]
    if magic != 0xFFFFFFFF:
        state_size = struct.unpack_from("<I", d, 4)[0]
        pk = parse(8 + state_size + 8192)
        if pk:
            return pk
        raise SystemExit("old-format dump: could not locate packets")
    hdr = struct.unpack_from("<10I", d, 4)
    guess = 0x38 + hdr[9] + hdr[2]  # screenshot end + state size (approximate)
    for cand in range(max(0, guess - 0x100), guess + 0x4000):
        pk = parse(cand)
        if pk and len(pk) > 4:
            return pk
    raise SystemExit("could not locate the packet stream")


class GifState:
    def __init__(self):
        self.tex0 = [None, None]
        self.bitblt = None
        self.trxreg = None
        self.trxdir = None
        self.pending_image = 0
        self.image_dst = None

    def reg_write(self, reg, val, events):
        if reg in (0x06, 0x16):
            ctx = 0 if reg == 0x06 else 1
            tbp0 = val & 0x3FFF
            tbw = (val >> 14) & 0x3F
            psm = (val >> 20) & 0x3F
            tw = (val >> 26) & 0xF
            th = (val >> 30) & 0xF
            t = (tbp0, tbw, psm, tw, th)
            if self.tex0[ctx] != t:
                self.tex0[ctx] = t
                events.append(("bind", ctx, tbp0, tbw, psm, 1 << tw, 1 << th))
        elif reg == 0x50:
            self.bitblt = val
        elif reg == 0x52:
            self.trxreg = val
        elif reg == 0x53:
            self.trxdir = val & 3
            if self.bitblt is not None and self.trxreg is not None:
                dbp = (self.bitblt >> 32) & 0x3FFF
                dbw = (self.bitblt >> 48) & 0x3F
                dpsm = (self.bitblt >> 56) & 0x3F
                sbp = self.bitblt & 0x3FFF
                rrw = self.trxreg & 0xFFF
                rrh = (self.trxreg >> 32) & 0xFFF
                if self.trxdir == 0:
                    self.image_dst = (dbp, dbw, dpsm, rrw, rrh)
                    self.pending_image = (rrw * rrh * BPP.get(dpsm, 32) + 7) // 8
                    events.append(("trx", dbp, dbw, dpsm, rrw, rrh))
                elif self.trxdir == 2:
                    events.append(("copy", sbp, dbp, dbw, dpsm, rrw, rrh))
        elif reg in (0x04, 0x05, 0x0C, 0x0D):
            events.append(("kick",))


def decode_gif(d, off, size, st, events):
    """Walk GIF packets in [off, off+size); append events. Returns bytes consumed."""
    p = off
    end = off + size
    image_bytes = 0
    while p + 16 <= end:
        lo, hi = struct.unpack_from("<QQ", d, p)
        p += 16
        nloop = lo & 0x7FFF
        eop = (lo >> 15) & 1
        flg = (lo >> 58) & 3
        nreg = (lo >> 60) & 0xF or 16
        regs = [(hi >> (4 * i)) & 0xF for i in range(nreg)]
        if flg == 0:  # PACKED
            for _ in range(nloop):
                for r in regs:
                    if p + 16 > end:
                        return p - off, image_bytes
                    vlo, vhi = struct.unpack_from("<QQ", d, p)
                    p += 16
                    if r == 0xE:
                        st.reg_write(vhi & 0xFF, vlo, events)
                    elif r in (0x04, 0x05, 0x0C, 0x0D):
                        events.append(("kick",))
                    elif r == 0x06:
                        st.reg_write(0x06, vlo, events)
                    elif r == 0x07:
                        st.reg_write(0x16, vlo, events)
        elif flg == 1:  # REGLIST
            cnt = nloop * nreg
            for i in range(cnt):
                if p + 8 > end:
                    return p - off, image_bytes
                v = struct.unpack_from("<Q", d, p)[0]
                p += 8
                r = regs[i % nreg]
                if r in (0x04, 0x05, 0x0C, 0x0D):
                    events.append(("kick",))
                elif r in (0x06, 0x07):
                    st.reg_write(0x06 if r == 0x06 else 0x16, v, events)
            if cnt & 1:
                p += 8
        else:  # IMAGE / disabled
            bytes_ = nloop * 16
            take = min(bytes_, end - p)
            image_bytes += take
            events.append(("image", take, st.image_dst))
            p += take
        if eop and flg != 2:
            pass
    return p - off, image_bytes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--pages", default=None)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    d = open(a.dump, "rb").read()
    pk = find_packets(d)
    pfilter = None
    if a.pages:
        ps, pn = a.pages.split(":")
        pfilter = (int(ps, 0), int(pn, 0))

    def hit(bp, bw, psm, h):
        if pfilter is None:
            return True
        p0 = bp >> 5
        p1 = p0 + page_span(psm, bw, h)
        return p1 > pfilter[0] and p0 < pfilter[0] + pfilter[1]

    st = GifState()
    frame = 0
    kicks_by_tex = {}
    print(f"{len(pk)} packets")
    for item in pk:
        if item[0] == "V":
            for (ctx, t), n in kicks_by_tex.items():
                pass
            print(f"---- vsync field={item[1]} (end of frame {frame})")
            frame += 1
            continue
        if item[0] != "T":
            continue
        _, path, off, size = item
        events = []
        decode_gif(d, off, size, st, events)
        kicks = sum(1 for e in events if e[0] == "kick")
        binds = [e for e in events if e[0] == "bind"]
        trx = [e for e in events if e[0] in ("trx", "copy")]
        imgs = [e for e in events if e[0] == "image"]
        show = a.all
        line = []
        for e in trx:
            if e[0] == "trx" and hit(e[1], e[2], e[3], e[5]):
                line.append(f"upload dbp={e[1]:05x} dbw={e[2]} psm={e[3]:02x} {e[4]}x{e[5]}")
                show = True
            elif e[0] == "copy" and (hit(e[2], e[3], e[4], e[6]) or hit(e[1], e[3], e[4], e[6])):
                line.append(f"copy sbp={e[1]:05x}->dbp={e[2]:05x} {e[5]}x{e[6]}")
                show = True
        for e in imgs:
            if e[2] and hit(e[2][0], e[2][1], e[2][2], e[2][4]):
                line.append(f"image {e[1]} bytes -> dbp={e[2][0]:05x}")
                show = True
        for e in binds:
            if hit(e[2], e[3], e[4], e[6]):
                line.append(f"bind ctx{e[1]} tbp0={e[2]:05x} tbw={e[3]} psm={e[4]:02x} {e[5]}x{e[6]}")
                show = True
        cur = st.tex0[0]
        if kicks and cur and hit(cur[0], cur[1], cur[2], 1 << cur[4]):
            line.append(f"kicks={kicks} using tbp0={cur[0]:05x}")
            show = True
        if show:
            print(f"f{frame} {PATH_NAMES[path]} {size:7d}B " + "; ".join(line))


if __name__ == "__main__":
    main()
