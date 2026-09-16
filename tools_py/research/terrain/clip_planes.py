"""For a family-B terrain dump: the plane qwords 30-36, and per primitive the signed distances of its three vertices
to the five clip planes (stage order 1..5), so the stage that drops it and the margin are visible."""
import struct, sys
b = open(sys.argv[1], "rb").read(); pc, top, itop, cs = struct.unpack_from("<4I", b, 0); data = b[16 + 0x4000: 16 + 0x8000]
def qi(q): return struct.unpack_from("<4i", data, q * 16)
def qf(q): return struct.unpack_from("<4f", data, q * 16)
ix, vz, vw = qi(top + 2)[0], qi(top + 2)[2], qi(top + 2)[3]
bias = qf(top + 3)
print("top=%d verts=%d prims=%d bias=%s" % (top, vz, vw, bias[:3]))
for q in range(30, 37): print("  q%d = %s" % (q, ["%.4f" % v for v in qf(q)]))
planes = [(31, 32), (30, 33), (30, 34), (30, 35), (30, 36)]
def vpos(k):
    x, y, z, w = qi(top + 4 + k)
    return (x / 16.0 + bias[0], y / 16.0 + bias[1], z / 16.0 + bias[2])
for i in range(vw):
    v0, v1, v2, fl = qi(top + ix + 2 * i)
    V = [vpos(v0), vpos(v1), vpos(v2)]
    row = []
    drop = None
    for s, (pq, nq) in enumerate(planes, 1):
        P = qf(pq); N = qf(nq)
        d = [sum((v[a] - P[a]) * N[a] for a in range(3)) for v in V]
        row.append("s%d:%s" % (s, "/".join("%+.0f" % x for x in d)))
        if drop is None and all(x < 0 for x in d): drop = s
    print("prim %2d drop@%s  %s" % (i, drop, "  ".join(row)))
