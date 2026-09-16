"""Scan the "detail t=... comp=... flags=... dist=... near=... count=... table=... n=... [thr:c8,ca]... ret=r" lines of a
PS2X_CULL_TRACE log: per frame the components whose triangle count was cut by the distance table, with the distance
against the thresholds, and the distribution of distances for components with a table."""
import re, sys, collections
rx = re.compile(r"detail t=([\d.]+) comp=(\w+) flags=(\w+) dist=([^ ]+) near=(\d+) count=(\d+) table=(\w+) n=(\d+)((?: \[[^\]]*\])*) ret=(\d+)")
rows = []
for line in open(sys.argv[1]):
    m = rx.match(line)
    if not m: continue
    t, comp, flags, dist, near, count, table, n, ents, ret = m.groups()
    entries = re.findall(r"\[([^:]+):(\d+),(\d+)\]", ents)
    rows.append((float(t), comp, int(flags, 16), float(dist), int(near), int(count), table, int(n), [(float(a), int(b), int(c)) for a, b, c in entries], int(ret)))
print("detail calls:", len(rows))
frames = []; cur = []
for r in rows:
    if cur and r[0] - cur[-1][0] > 0.010: frames.append(cur); cur = []
    cur.append(r)
if cur: frames.append(cur)
for f in frames[:6]:
    withtab = [r for r in f if r[7]]
    print("frame t=%.2f comps=%d with-table=%d near=%d ret1=%d" % (f[0][0], len(f), len(withtab), sum(r[4] for r in f), sum(r[9] for r in f)))
    for r in withtab[:14]:
        print("   comp=%s flags=%08x dist=%.0f near=%d count=%d ret=%d table=%s" % (r[1], r[2], r[3], r[4], r[5], r[9], r[8][:4]))
