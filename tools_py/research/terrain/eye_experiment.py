"""Which of our VU1 dumps kicks the under-water terrain fan (tex0 0x36b1), and does the kicked triangle count depend
on the cull's eye position (data qword 30)? Replay the dump with the eye nudged and count kicks per variant."""
import glob, os, struct, subprocess, sys, collections, shutil
D = sys.argv[1]
EXE = r"C:\projects\socom_pc\dist\vu1_replay.exe"
T = struct.pack("<Q", 0x20162d45dd30b6b1)

def kicks_by_tex0(pk):
    b = open(pk, "rb").read(); p = 0; tex0 = None; prim = None; nv = 0; tris = collections.Counter(); verts = collections.Counter()
    while p + 4 <= len(b):
        n = struct.unpack_from("<I", b, p)[0]; p += 4; pkt = b[p:p + n]; p += n; q = 0
        while q + 16 <= len(pkt):
            lo, hi = struct.unpack_from("<QQ", pkt, q); q += 16
            nloop = lo & 0x7FFF; flg = (lo >> 58) & 3; nreg = (lo >> 60) & 0xF or 16
            if (lo >> 46) & 1: prim = (lo >> 47) & 0x7FF
            rl = [(hi >> (4 * k)) & 0xF for k in range(nreg)]
            if flg == 0:
                for _ in range(nloop):
                    for r in rl:
                        if q + 16 > len(pkt): break
                        vlo, vhi = struct.unpack_from("<QQ", pkt, q); q += 16
                        if r == 0xE and (vhi & 0xFF) == 0x06: tex0 = vlo & 0x3FFF
                        elif r == 0xE and (vhi & 0xFF) == 0x00: prim = vlo & 0x7FF
                        elif r in (4, 0xC): verts[tex0] += 1
            elif flg == 1: cnt = nloop * nreg; q += 8 * cnt + (8 if cnt & 1 else 0)
            else: q += nloop * 16
    return verts

hits = [f for f in glob.glob(os.path.join(D, "vu1_prog_*.bin")) if T in open(f, "rb").read()[16 + 0x4000: 16 + 0x8000]]
hits.sort(key=lambda p: int(p.split("_")[-1].split(".")[0]))
out = os.path.join(D, "eye_exp"); shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
# find dumps whose replay kicks tex0 0x36b1 vertices
subprocess.run([EXE, "--batch", out] + hits[:60], capture_output=True)
terrain = []
for f in hits[:60]:
    pk = os.path.join(out, os.path.basename(f).replace(".bin", ".pk"))
    if os.path.exists(pk):
        v = kicks_by_tex0(pk)
        if v.get(0x36b1, 0): terrain.append((f, v[0x36b1]))
print("dumps kicking tex0 036b1 vertices:", [(os.path.basename(f), n) for f, n in terrain[:8]])
if not terrain: sys.exit(0)
f, base = terrain[0][0], terrain[0][1]
b = bytearray(open(f, "rb").read())
off = 16 + 0x4000 + 30 * 16
eye = struct.unpack_from("<4f", b, off)
print("eye qword 30 =", eye)
for name, dx, dy, dz in (("base", 0, 0, 0), ("y+2", 0, 2, 0), ("y-2", 0, -2, 0), ("y+8", 0, 8, 0), ("y-8", 0, -8, 0), ("x+8", 8, 0, 0), ("z+8", 0, 0, 8)):
    bb = bytearray(b); struct.pack_into("<3f", bb, off, eye[0] + dx, eye[1] + dy, eye[2] + dz)
    vf = os.path.join(out, "var.bin"); open(vf, "wb").write(bb)
    vo = os.path.join(out, "var_out"); shutil.rmtree(vo, ignore_errors=True); os.makedirs(vo)
    subprocess.run([EXE, "--batch", vo, vf], capture_output=True)
    pk = os.path.join(vo, "var.pk")
    v = kicks_by_tex0(pk) if os.path.exists(pk) else {}
    print("  %-5s eye=(%.1f,%.1f,%.1f): 036b1 kicked verts %d, all kicks %d" % (name, eye[0] + dx, eye[1] + dy, eye[2] + dz, v.get(0x36b1, 0), sum(v.values())))
