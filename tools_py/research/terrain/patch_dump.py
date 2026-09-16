import struct, sys
b = open(sys.argv[1], "rb").read(); pc, top, itop, cs = struct.unpack_from("<4I", b, 0); data = b[16 + 0x4000: 16 + 0x8000]
def qi(q): return struct.unpack_from("<4i", data, q * 16)
def qf(q): return struct.unpack_from("<4f", data, q * 16)
h = qi(top + 2); ix, vz, vw = h[0], h[2], h[3]; bias = qf(top + 3); eye = qf(30)
print("top=%d hdr=%s verts=%d prims=%d bias=%s eye=%s" % (top, h, vz, vw, bias[:3], eye[:3]))
print("TOP+0..1:", ["%08x" % (x & 0xffffffff) for x in qi(top)], ["%08x" % (x & 0xffffffff) for x in qi(top + 1)])
V = []
for k in range(vz):
    x, y, z, w = qi(top + 4 + 3 * k); u, v, _, _ = qi(top + 5 + 3 * k); c = qi(top + 6 + 3 * k)
    V.append((x / 16.0 + bias[0], y / 16.0 + bias[1], z / 16.0 + bias[2]))
    print("  v%2d pos=(%8.1f %8.1f %8.1f) w=%d uv=(%.3f %.3f) col=%s" % (k, V[-1][0], V[-1][1], V[-1][2], w, u / 4096.0, v / 4096.0, c))
for i in range(vw):
    v0, v1, v2, fl = qi(top + ix + 2 * i); n = qi(top + ix + 2 * i + 1)
    a, bb, c = V[v0 // 3], V[v1 // 3], V[v2 // 3]
    nn = [x / 32768.0 for x in n[:3]]
    d = sum((eye[k] - a[k]) * nn[k] for k in range(3))
    # geometric normal
    e1 = [bb[k] - a[k] for k in range(3)]; e2 = [c[k] - a[k] for k in range(3)]
    g = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
    gd = sum((eye[k] - a[k]) * g[k] for k in range(3))
    print("  p%2d tri=(%2d,%2d,%2d) flags=%d n=(%.3f %.3f %.3f) n.w=%d dot=%.1f geomdot=%.0f" % (i, v0 // 3, v1 // 3, v2 // 3, fl, nn[0], nn[1], nn[2], n[3], d, gd))
