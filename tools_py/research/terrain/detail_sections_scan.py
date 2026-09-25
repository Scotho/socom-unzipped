"""Per frame, every component FUN_003b6e10 sized: the main-pass count, the detail groups it will draw (entries up to
the extra-section offset), the extra section, the variant header and the variant-index stack top; and the sum of
primitives the object renderer will send, to set against the console's fan count.

Run: python -m tools_py.research.terrain.detail_sections_scan <PS2X_CULL_TRACE log>"""
import re, sys, collections
rx = re.compile(r"detail t=([\d.]+) comp=(\w+) flags=(\w+) dist=([^ ]+) near=(\d+) count=(\d+) table=(\w+) n=(\d+)((?: \[[^\]]*\])*) extra=(\w+)/(\d+) off=(\d+) near2=(\d+) geom=(\w+)(?: hdr=([\d,]+))? vstack=(\w+),(\w+),(\w+),(\w+) ret=(\d+)")
rows = []
for line in open(sys.argv[1]):
    m = rx.match(line)
    if not m: continue
    g = m.groups()
    entries = [(float(a), int(b), int(c)) for a, b, c in re.findall(r"\[([^:]+):(\d+),(\d+)\]", g[8])]
    hdr = [int(x) for x in g[14].split(",")] if g[14] else []
    rows.append(dict(t=float(g[0]), comp=g[1], flags=int(g[2], 16), dist=float(g[3]), near=int(g[4]), count=int(g[5]), entries=entries,
                     ec0=int(g[9], 16), ec8=int(g[10]), ed0=int(g[11]), ret=int(g[19]), geom=g[13], hdr=hdr, vstack=g[15:19]))
print("rows:", len(rows))
frames = []; cur = []
for r in rows:
    if cur and r["t"] - cur[-1]["t"] > 0.010: frames.append(cur); cur = []
    cur.append(r)
if cur: frames.append(cur)
def drawn(r):
    n = r["count"]
    if r["ret"] and r["entries"]:
        for thr, c8, ca in r["entries"]:
            if r["ec0"] and r["ed0"] <= c8: break
            n += ca
    n += r["ec8"]
    return n
for f in frames[:5]:
    tot = sum(drawn(r) for r in f); full = sum(r["hdr"][0] for r in f if r["hdr"])
    print("frame t=%.2f comps=%d drawn prims=%d header totals=%d vstack=%s" % (f[0]["t"], len(f), tot, full, f[0]["vstack"]))
    for r in f:
        if r["entries"] or r["ec8"]:
            print("   comp=%s dist=%.0f near=%d main=%d groups=%s extra=%08x/%d off=%d hdr=%s -> drawn %d" % (r["comp"], r["dist"], r["near"], r["count"], [(c8, ca) for _, c8, ca in r["entries"]], r["ec0"], r["ec8"], r["ed0"], r["hdr"], drawn(r)))
