"""Fit the world->screen projective map from dump 237's vertices (world) and the no-clip replay (screen x,y,z), then
unproject the console's ABSENT fans' vertices to world space and report which cell they fall in."""
import struct, sys, numpy as np, collections
D = "vu1dump_spawn/vu1_prog_237.bin"; PK = "cls_noclip/vu1_prog_237.pk"
b = open(D, "rb").read(); top = struct.unpack_from("<I", b, 4)[0]; data = b[16 + 0x4000: 16 + 0x8000]
def qi(q): return struct.unpack_from("<4i", data, q * 16)
h = qi(top + 2); ix, vz, vw = h[0], h[2], h[3]
V = [tuple(qi(top + 4 + 3 * k)[a] / 16.0 for a in range(3)) for k in range(vz)]
tris = [tuple(qi(top + ix + 2 * i)[a] // 3 for a in range(3)) for i in range(vw)]
# screen verts per fan from the pk (tex0 0x36b1 fans only, in prim order)
pkb = open(PK, "rb").read(); p = 0; fans = []; tex0 = None
while p + 4 <= len(pkb):
    n = struct.unpack_from("<I", pkb, p)[0]; p += 4; pkt = pkb[p:p + n]; p += n; q = 0
    while q + 16 <= len(pkt):
        lo, hi = struct.unpack_from("<QQ", pkt, q); q += 16
        nloop = lo & 0x7FFF; flg = (lo >> 58) & 3; nreg = (lo >> 60) & 0xF or 16
        rl = [(hi >> (4 * k)) & 0xF for k in range(nreg)]; isfan = (lo >> 46) & 1 and ((lo >> 47) & 7) == 5 and 4 in rl; verts = []
        if flg == 0:
            for _ in range(nloop):
                for r in rl:
                    if q + 16 > len(pkt): break
                    vlo, vhi = struct.unpack_from("<QQ", pkt, q); q += 16
                    if r == 0xE and (vhi & 0xFF) == 0x06: tex0 = vlo & 0x3FFF
                    elif r == 4: verts.append(((vlo & 0xFFFF) / 16.0 - 1728, ((vlo >> 32) & 0xFFFF) / 16.0 - 1824, (vhi >> 4) & 0xFFFFFF))
            if isfan and tex0 == 0x36b1: fans.append(verts)
        elif flg == 1: cnt = nloop * nreg; q += 8 * cnt + (8 if cnt & 1 else 0)
        else: q += nloop * 16
print("prims", vw, "noclip fans", len(fans))
pairs = []
for tri, fan in zip(tris, fans):
    if len(fan) != 3: continue
    for k, s in zip(tri, fan):
        if -200 < s[0] < 900 and -200 < s[1] < 700 and 0 < s[2] < 0xF00000: pairs.append((V[k], s))
print("pairs", len(pairs))

# DLT on x,y only, world centred at the eye for conditioning
eye = np.array(struct.unpack_from("<4f", data, 30 * 16)[:3])
A = []; y = []
for (X, Y, Z), (sx, sy, sz) in pairs:
    W = list(np.array([X, Y, Z]) - eye) + [1]
    for row, s_ in ((0, sx), (1, sy)):
        r = [0.0] * 11; r[row * 4: row * 4 + 4] = W; r[8:11] = [-s_ * W[0], -s_ * W[1], -s_ * W[2]]
        A.append(r); y.append(s_)
A = np.array(A); y = np.array(y); sol = np.linalg.lstsq(A, y, rcond=None)[0]
P = np.vstack([sol[0:4], sol[4:8], np.array([sol[8], sol[9], sol[10], 1.0])])
errs = []; ws = []
for (X, Y, Z), (sx, sy, sz) in pairs:
    W = np.array(list(np.array([X, Y, Z]) - eye) + [1.0]); v = P @ W
    errs.append(max(abs(v[0] / v[2] - sx), abs(v[1] / v[2] - sy))); ws.append((v[2], sz))
print("xy fit: max err px %.2f over %d pairs" % (max(errs), len(errs)))
# z model: sz = a + b / w  (fit)
Wm = np.array([[1.0, 1.0 / w] for w, _ in ws]); zs = np.array([z for _, z in ws]); ab = np.linalg.lstsq(Wm, zs, rcond=None)[0]
print("z model sz = %.1f + %.1f/w, max err %.0f" % (ab[0], ab[1], max(abs(Wm @ ab - zs))))
def unproject(sx, sy, sz):
    w = ab[1] / (sz - ab[0])
    M = np.array([P[0] - sx * P[2], P[1] - sy * P[2], P[2]]); rhs = np.array([0.0, 0.0, w])
    # rows: (P0 - sx P2).W = 0 ; (P1 - sy P2).W = 0 ; P2.W = w ; W = (X,Y,Z,1)
    Xc = np.linalg.solve(M[:, :3], rhs - M[:, 3])
    return Xc + eye
# console absent fans (from classify output, with z from fan_detail's scan)
exec(open("fan_detail.py").read().split("name, path, mb")[0])
cf = scan("console_replay/packets.bin", None, 1400)
byframe = collections.defaultdict(list)
for f in cf: byframe[f[0]].append(f)
fr = max(byframe, key=lambda k: len(byframe[k]))
absent = {6, 8, 34, 43, 44, 45, 46, 48, 49, 50, 51, 52, 53, 55, 56, 57, 58, 59, 60, 61, 62, 64, 65, 66, 67, 76, 77}
for i, f in enumerate(byframe[fr]):
    if i not in absent: continue
    ws = [unproject(*s) for s in f[8]]
    print("c%02d" % i, " ".join("(%.0f,%.0f,%.0f)" % tuple(w) for w in ws))
for i in (0, 1, 2, 3):
    f = byframe[fr][i]; print("kept c%02d" % i, " ".join("(%.0f,%.0f,%.0f)" % tuple(unproject(*s)) for s in f[8]))
