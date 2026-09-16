"""Terrain (tex0 0x36b1) VU1 dumps: per dump the header counts (TOP+2.x index offset, .z vertices, .w primitives),
the command list at data qword 340, and the fans the batch replay emitted for it."""
import glob, os, struct, sys, collections
exec(open("eye_experiment.py").read().split("hits = [")[0].split("def kicks_by_tex0")[0])  # imports + T
exec("def kicks_by_tex0" + open("eye_experiment.py").read().split("def kicks_by_tex0")[1].split("hits = [")[0])
D = sys.argv[1]; PK = sys.argv[2]
rows = []
for pk in sorted(glob.glob(os.path.join(PK, "vu1_prog_*.pk")), key=lambda p: int(p.split("_")[-1].split(".")[0])):
    v = kicks_by_tex0(pk)
    if not v.get(0x36b1): continue
    f = os.path.join(D, os.path.basename(pk).replace(".pk", ".bin")); b = open(f, "rb").read()
    pc, top, itop, codeSize = struct.unpack_from("<4I", b, 0)
    data = b[16 + 0x4000: 16 + 0x8000]
    def w(q, k): return struct.unpack_from("<i", data, q * 16 + k * 4)[0]
    ix, vz, vw = w(top + 2, 0), w(top + 2, 2), w(top + 2, 3)
    cmds = []
    q = 340
    for _ in range(12):
        c = w(q, 0) & 0xFF; cmds.append("%02x" % c); q += 1
        if c == 0x42: break
    flags = collections.Counter(w(top + ix + 2 * i, 3) & 3 for i in range(max(0, min(vw, 512))))
    # fans emitted: count PRE prim-5 tags in the .pk with nloop
    fans = 0; b2 = open(pk, "rb").read(); p = 0
    while p + 4 <= len(b2):
        n = struct.unpack_from("<I", b2, p)[0]; p += 4; pkt = b2[p:p + n]; p += n
        lo = struct.unpack_from("<Q", pkt, 0)[0] if len(pkt) >= 8 else 0
        if (lo >> 46) & 1 and ((lo >> 47) & 7) == 5: fans += 1
    rows.append((os.path.basename(f), top, ix, vz, vw, " ".join(cmds), dict(flags), fans, v[0x36b1]))
for r in rows[:40]: print("%s top=%d idx=%d verts=%d prims=%d cmds=[%s] flags=%s fans=%d kickedVerts=%d" % r)
print("dumps:", len(rows), "sum prims:", sum(r[4] for r in rows), "sum fans:", sum(r[7] for r in rows))
