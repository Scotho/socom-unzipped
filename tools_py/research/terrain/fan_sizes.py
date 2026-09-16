"""Per stream: for tex0 0x36b1, every GIF packet whose tag has PRE=1 and PRIM type 5 (fan): (packet index, NLOOP)
plus the first vertex's screen xy, for the first frame. Frame boundary: a FRAME_1 write with fbp 0 or 0x8c."""
import struct, sys, collections
def scan(path, maxbytes=None, stop=None):
    b = open(path, "rb").read(maxbytes) if maxbytes else open(path, "rb").read()
    p = 0; tex0 = None; n = 0; fans = []; frame = 0; lists = collections.Counter()
    while p + 8 <= len(b):
        pth, sz = struct.unpack_from("<II", b, p); p += 8
        pkt = b[p:p + sz]; p += sz; n += 1
        if stop and n > stop: break
        q = 0
        while q + 16 <= len(pkt):
            lo, hi = struct.unpack_from("<QQ", pkt, q); q += 16
            nloop = lo & 0x7FFF; flg = (lo >> 58) & 3; nreg = (lo >> 60) & 0xF or 16
            pre = (lo >> 46) & 1; prim = (lo >> 47) & 0x7FF
            rl = [(hi >> (4 * k)) & 0xF for k in range(nreg)]
            if flg == 0:
                first = None
                for _ in range(nloop):
                    for r in rl:
                        if q + 16 > len(pkt): break
                        vlo, vhi = struct.unpack_from("<QQ", pkt, q); q += 16
                        if r == 0xE:
                            reg = vhi & 0xFF
                            if reg == 0x06: tex0 = vlo & 0x3FFF
                            elif reg == 0x4C and (vlo & 0x1FF) in (0, 0x8c): frame += 1
                        elif r in (4, 5, 0xC, 0xD) and first is None:
                            first = ((vlo & 0xFFFF) / 16.0 - 1728, ((vlo >> 32) & 0xFFFF) / 16.0 - 1824)
                if pre and tex0 == 0x36b1 and 4 in rl:
                    if (prim & 7) == 5: fans.append((frame, n, nloop, first))
                    else: lists[(frame, prim & 7, nloop)] += 1
            elif flg == 1:
                cnt = nloop * nreg; q += 8 * cnt + (8 if cnt & 1 else 0)
            else:
                q += nloop * 16
    return fans, lists
for name, path, mb, stop in (("OURS", sys.argv[1], 60_000_000, 12900), ("CONSOLE", sys.argv[2], None, 1400)):
    fans, lists = scan(path, mb, stop)
    byframe = collections.defaultdict(list)
    for fr, n, nl, first in fans: byframe[fr].append((nl, first))
    print("==", name)
    for fr in sorted(byframe)[:3]:
        L = byframe[fr]
        print("  frame %d: %d fans, %d tris, nloop histogram %s" % (fr, len(L), sum(nl - 2 for nl, _ in L), sorted(collections.Counter(nl for nl, _ in L).items())))
        print("     first-vertex xy:", [(round(f[0]), round(f[1])) for _, f in L][:40])
    print("  list prims (frame, type, nloop) -> count:", sorted(lists.items())[:8])
