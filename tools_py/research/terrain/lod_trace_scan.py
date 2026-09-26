"""Scan the "lod t=... comp=... dist=... entry=... near=a/b/c far=d/e/f flags=... fade=x->y result=r" lines of a
PS2X_CULL_TRACE log: per frame how many components the LOD band test rejected, with the rejected ones' distance
against their band, so a mis-scaled distance (camera + 0x2c8) shows as rejections far outside plausible bands.

Run: python -m tools_py.research.terrain.lod_trace_scan <PS2X_CULL_TRACE log>"""
import re, sys, collections
rx = re.compile(r"lod t=([\d.]+) comp=(\w+) dist=([^ ]+) entry=(\w+) near=([^/]+)/([^/]+)/([^ ]+) far=([^/]+)/([^/]+)/([^ ]+) flags=(\w+) fade=([^-]+)->([^ ]+) result=(\d+)")
rows = []
for line in open(sys.argv[1]):
    m = rx.match(line)
    if m:
        g = m.groups(); rows.append((float(g[0]), g[1], float(g[2]), g[3], [float(x) for x in g[4:10]], g[10], float(g[11]), float(g[12]), int(g[13])))
print("lod calls:", len(rows))
frames = []; cur = []
for r in rows:
    if cur and r[0] - cur[-1][0] > 0.010: frames.append(cur); cur = []
    cur.append(r)
if cur: frames.append(cur)
for f in frames[:10]:
    rej = [r for r in f if r[8] == 0]
    print("frame t=%.2f calls=%d rejected=%d" % (f[0][0], len(f), len(rej)))
    for r in rej[:12]:
        e = r[4]; why = "too near" if r[2] <= e[0] else ("too far" if r[2] >= e[4] else "?")
        print("   comp=%s dist=%.0f band=[%.0f..%.0f] fade %.3g->%.3g %s" % (r[1], r[2], e[0], e[4], r[6], r[7], why))
ent = collections.Counter(r[3] for r in rows)
print("distinct LOD entries:", len(ent))
for e, n in ent.most_common(8):
    r = next(x for x in rows if x[3] == e); print("   entry %s x%d near=%s far=%s flags=%s" % (e, n, r[4][:3], r[4][3:], r[5]))
