import struct, sys, collections
def scan(path, maxbytes=None, stop=None):
    b = open(path, "rb").read(maxbytes) if maxbytes else open(path, "rb").read()
    p = 0; tex0 = None; n = 0; out = []; frame = 0
    while p + 8 <= len(b):
        pth, sz = struct.unpack_from("<II", b, p); p += 8
        pkt = b[p:p + sz]; p += sz; n += 1
        if stop and n > stop: break
        q = 0; ad = []
        while q + 16 <= len(pkt):
            lo, hi = struct.unpack_from("<QQ", pkt, q); q += 16
            nloop = lo & 0x7FFF; flg = (lo >> 58) & 3; nreg = (lo >> 60) & 0xF or 16
            pre = (lo >> 46) & 1; prim = (lo >> 47) & 0x7FF
            rl = [(hi >> (4 * k)) & 0xF for k in range(nreg)]
            if flg == 0:
                verts = []
                for _ in range(nloop):
                    for r in rl:
                        if q + 16 > len(pkt): break
                        vlo, vhi = struct.unpack_from("<QQ", pkt, q); q += 16
                        if r == 0xE:
                            reg = vhi & 0xFF; ad.append((reg, vlo))
                            if reg == 0x06: tex0 = vlo & 0x3FFF
                            elif reg == 0x4C and (vlo & 0x1FF) in (0, 0x8c): frame += 1
                        elif r in (4, 5, 0xC, 0xD):
                            verts.append((round((vlo & 0xFFFF) / 16.0 - 1728), round(((vlo >> 32) & 0xFFFF) / 16.0 - 1824), (vhi >> 4) & 0xFFFFFF))
                if pre and tex0 == 0x36b1 and 4 in rl and (prim & 7) == 5:
                    out.append((frame, n, pth, sz, nloop, prim, nreg, "".join("%x" % r for r in rl), verts, list(ad)))
            elif flg == 1:
                cnt = nloop * nreg; q += 8 * cnt + (8 if cnt & 1 else 0)
            else: q += nloop * 16
    return out
name, path, mb, stop, lo_, hi_ = sys.argv[1], sys.argv[2], int(sys.argv[3]) or None, int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
fans = scan(path, mb, stop); fr = min(f[0] for f in fans); fans = [f for f in fans if f[0] == fr]
for i, (frame, n, pth, sz, nloop, prim, nreg, regs, verts, ad) in enumerate(fans[lo_:hi_], lo_):
    print("%s f%02d pkt=%d path=%d size=%d nloop=%d prim=%03x regs=%s verts=%s ad=%s" % (name, i, n, pth, sz, nloop, prim, regs, verts, ["%02x=%x" % (r, v) for r, v in ad][:6]))
