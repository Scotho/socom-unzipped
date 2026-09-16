"""Both terrain program families of the spawn frame, replayed with the clip planes AND the backface-cull normals zeroed,
so every primitive the EE sent is kicked at its true screen position; then each console fan is matched (>= 2 shared
vertices within TOL) against those kicked polygons: KICKED (matched in the as-is replay), SENT-BUT-DROPPED (only in
the no-clip/no-cull replay), ABSENT (never sent)."""
import glob, os, struct, sys, shutil, subprocess, collections
EXE = r"C:\projects\socom_pc\dist\vu1_replay.exe"
D, CONS, LIMIT = sys.argv[1], sys.argv[2], int(sys.argv[3])
T = struct.pack("<Q", 0x20162d45dd30b6b1); TOL = 30

def polys_of_pk(pk):
    b = open(pk, "rb").read(); p = 0; out = []; tex0 = None
    while p + 4 <= len(b):
        n = struct.unpack_from("<I", b, p)[0]; p += 4; pkt = b[p:p + n]; p += n; q = 0
        while q + 16 <= len(pkt):
            lo, hi = struct.unpack_from("<QQ", pkt, q); q += 16
            nloop = lo & 0x7FFF; flg = (lo >> 58) & 3; nreg = (lo >> 60) & 0xF or 16
            rl = [(hi >> (4 * k)) & 0xF for k in range(nreg)]
            pre = (lo >> 46) & 1; ptype = (lo >> 47) & 7; verts = []
            if flg == 0:
                for _ in range(nloop):
                    for r in rl:
                        if q + 16 > len(pkt): break
                        vlo, vhi = struct.unpack_from("<QQ", pkt, q); q += 16
                        if r == 0xE and (vhi & 0xFF) == 0x06: tex0 = vlo & 0x3FFF
                        elif r == 4: verts.append((round((vlo & 0xFFFF) / 16.0 - 1728), round(((vlo >> 32) & 0xFFFF) / 16.0 - 1824)))
                if pre and tex0 == 0x36b1 and 4 in rl and verts:
                    if ptype == 5: out.append(verts)
                    elif ptype == 3:
                        for k in range(0, len(verts) - 2, 3): out.append(verts[k:k + 3])
            elif flg == 1: cnt = nloop * nreg; q += 8 * cnt + (8 if cnt & 1 else 0)
            else: q += nloop * 16
    return out

def replay(files, out, nuke):
    shutil.rmtree(out, ignore_errors=True); os.makedirs(out); srcs = []
    for f in files:
        b = bytearray(open(f, "rb").read())
        if nuke:
            for q in range(32, 37): struct.pack_into("<4f", b, 16 + 0x4000 + q * 16, 0, 0, 0, 0)
            top = struct.unpack_from("<I", b, 4)[0]; d0 = 16 + 0x4000
            ix, _, vz, vw = struct.unpack_from("<4i", b, d0 + (top + 2) * 16)
            if 0 <= ix < 1024 and 0 < vw <= 512 and (top + ix + 2 * vw) * 16 < 0x4000:
              for i in range(vw): struct.pack_into("<4i", b, d0 + (top + ix + 2 * i + 1) * 16, 0, 0, 0, 0)
        nf = os.path.join(out, os.path.basename(f)); open(nf, "wb").write(b); srcs.append(nf)
    subprocess.run([EXE, "--batch", out, "--no-native"] + srcs, capture_output=True)
    return {os.path.basename(f): polys_of_pk(f.replace(".bin", ".pk")) for f in srcs if os.path.exists(f.replace(".bin", ".pk"))}

hits = []
for f in glob.glob(os.path.join(D, "vu1_prog_*.bin")):
    n = int(f.split("_")[-1].split(".")[0])
    if n > LIMIT: continue
    b = open(f, "rb").read()
    if len(b) < 16 + 0x8000 or T not in b[16 + 0x4000: 16 + 0x8000]: continue
    hits.append(f)
hits.sort(key=lambda p: int(p.split("_")[-1].split(".")[0]))
asis = {os.path.basename(f): polys_of_pk("cls2_asis/" + os.path.basename(f).replace(".bin", ".pk")) for f in hits if os.path.exists("cls2_asis/" + os.path.basename(f).replace(".bin", ".pk"))}
nuked = {os.path.basename(f): polys_of_pk("cls2_nuked/" + os.path.basename(f).replace(".bin", ".pk")) for f in hits if os.path.exists("cls2_nuked/" + os.path.basename(f).replace(".bin", ".pk"))}
for h in hits:
    n = os.path.basename(h); print("  %s as-is %d polys, no-clip/no-cull %d polys" % (n, len(asis.get(n, [])), len(nuked.get(n, []))))
exec(open("fan_detail.py").read().split("name, path, mb")[0])
cf = scan(CONS, None, 1400)
byframe = collections.defaultdict(list)
for f in cf: byframe[f[0]].append(f)
fr = max(byframe, key=lambda k: len(byframe[k]))
def near(a, b): return abs(a[0] - b[0]) <= TOL and abs(a[1] - b[1]) <= TOL
def shared(cv, poly): return sum(1 for c in cv if any(near(s, c) for s in poly))
def find(cv, dct): return [(n, i) for n, L in dct.items() for i, poly in enumerate(L) if shared(cv, poly) >= (3 if len(cv) <= 3 else 3) and shared(poly, cv) >= 3]
cls = collections.Counter()
for i, f in enumerate(byframe[fr]):
    cv = [(x, y) for x, y, z in f[8]]
    a = find(cv, asis); k = find(cv, nuked)
    c = "KICKED" if a else ("SENT-BUT-DROPPED" if k else "ABSENT"); cls[c] += 1
    if c != "KICKED": print("c%02d %-16s n=%d %s -> %s" % (i, c, len(cv), cv[:3], k[:3]))
print("classification:", dict(cls))
