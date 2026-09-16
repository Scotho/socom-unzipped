"""Set our guest RAM at the spawn view (PS2X_RDRAM_DUMP) against the PCSX2 slot-8 savestate's eeMemory.bin:
the mesh variant headers by shape, the detail-table thresholds, the object renderer's globals, and -- for a
detail table given as (c8,ca) pairs -- the component records holding it in each image, with their flags.
Usage: ee_compare.py OURS.bin CONSOLE.bin [c8,ca;c8,ca...]"""
import struct, sys, collections, re
A = open(sys.argv[1], "rb").read(); B = open(sys.argv[2], "rb").read()
want = [tuple(int(x) for x in p.split(",")) for p in sys.argv[3].split(";")] if len(sys.argv) > 3 else [(0, 4), (4, 4)]

def headers(m):
    cnt = collections.Counter()
    for mm in re.finditer(rb"\x01\x00\x00\x00\x00\x00", m):
        i = mm.start() - 2
        if i < 0 or i % 2: continue
        h = struct.unpack_from("<8H", m, i)
        if 1 <= h[0] <= 64 and h[6] + h[7] <= h[0]:
            cnt[(h[0], h[6], h[7])] += 1
    return cnt

def globals_(m, name):
    u32 = lambda a: struct.unpack_from("<I", m, a)[0]; f32 = lambda a: struct.unpack_from("<f", m, a)[0]
    print("%s: 4b4a98=%g 4b4a88=%d 4b4ad0=%d 4b4ec0=%08x 4b4ec8=%d 4b4ed0=%d 4b4ed8=%d 3e1478=%g 3e1470=%d 3e1468=%d 3e1458=%d 3de208=%d"
          % (name, f32(0x4b4a98), m[0x4b4a88], u32(0x4b4ad0), u32(0x4b4ec0), u32(0x4b4ec8), u32(0x4b4ed0), m[0x4b4ed8], f32(0x3e1478), m[0x3e1470], m[0x3e1468], m[0x3e1458], m[0x3de208]))
    holder = u32(0x415ff0); cam = u32(holder + 0xb4) if 0 < holder < len(m) - 0x100 else 0
    if 0 < cam < len(m) - 0x600:
        print("   camera=%08x +2c8=%g +2cc=%g +13c=%g +140=%g +144=%g +148=%g +564(planeMask)=%08x +2a8(layers)=%08x +711=%d +712=%d +713=%d +714=%d +715=%d"
              % (cam, f32(cam+0x2c8), f32(cam+0x2cc), f32(cam+0x13c), f32(cam+0x140), f32(cam+0x144), f32(cam+0x148), u32(cam+0x564), u32(cam+0x2a8), m[cam+0x711], m[cam+0x712], m[cam+0x713], m[cam+0x714], m[cam+0x715]))

def find_table(m, pairs):
    thr = struct.pack("<f", 2002500.0); hits = []
    i = m.find(thr)
    while i >= 0:
        ok = True
        for k, (c8, ca) in enumerate(pairs):
            e = i + k * 16
            if m[e:e+4] != thr or struct.unpack_from("<HH", m, e + 8) != (c8, ca): ok = False; break
        if ok: hits.append(i)
        i = m.find(thr, i + 1)
    return hits

def comps_with_table(m, addr):
    p = struct.pack("<I", addr); out = []
    i = m.find(p)
    while i >= 0:
        c = i - 0x18 * 4
        if c >= 0:
            out.append((c, struct.unpack_from("<I", m, c)[0], m[c+5], struct.unpack_from("<I", m, c + 0x19*4)[0]))
        i = m.find(p, i + 1)
    return out

ha, hb = headers(A), headers(B)
print("variant headers: ours %d, console %d" % (sum(ha.values()), sum(hb.values())))
diff = [(k, ha[k], hb[k]) for k in set(ha) | set(hb) if ha[k] != hb[k]]
print("header shapes that differ (shape, ours, console):", sorted(diff, key=lambda x: -abs(x[1]-x[2]))[:20])
print("2002500 thresholds: ours %d console %d" % (A.count(struct.pack("<f", 2002500.0)), B.count(struct.pack("<f", 2002500.0))))
globals_(A, "OURS"); globals_(B, "CONSOLE")
for name, m in (("OURS", A), ("CONSOLE", B)):
    t = find_table(m, want)
    print("%s: tables matching %s: %d" % (name, want, len(t)))
    for addr in t[:4]:
        cs = comps_with_table(m, addr)
        print("   table @%08x -> components %s" % (addr, ["%08x flags=%08x lod=%d n=%d" % c for c in cs]))
