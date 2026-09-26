"""Scan a PS2X_CULL_TRACE log that also carries the scene-node lines ("node t=... obj=..."): pair each cull call with
the node entered just before it (the traversal calls the cull from inside FUN_00338480), find the node whose box
held the given world point in the first frames, and print that node's gate fields in every later frame.

Run: python -m tools_py.research.terrain.node_trace_scan <PS2X_CULL_TRACE log> [x,y,z]"""
import re, sys, collections
path = sys.argv[1]
pt = tuple(float(v) for v in sys.argv[2].split(",")) if len(sys.argv) > 2 else (947.0, -139.0, 969.0)
rxc = re.compile(r"t=([\d.]+) cam=(\w+) occl=(\d+) result=(\d+) guestMask=(\w+) planeMask=(\w+) ieee=(\w+)(?: lod=[^ ]+)? box=\(([^)]*)\)-\(([^)]*)\)")
rxn = re.compile(r"node t=([\d.]+) (?:via=(\w+) )?obj=(\w+) f5c=(\w+) f9c=([^ ]+) c88=(\w+) comp=(\w+) kind=(\d+) a1=(\w+) scene=(\w+) (?:parent|arg2)=(\w+)")
events = []
for line in open(path):
    m = rxn.match(line)
    if m:
        t, via, obj, f5c, f9c, c88, comp, kind, a1, scene, parent = m.groups()
        events.append(("node", float(t), obj, int(f5c, 16), float(f9c), c88, comp, int(kind), int(a1, 16), (via or "scene") + ":" + parent)); continue
    m = rxc.match(line)
    if m:
        t, cam, occl, res, gm, pm, ieee, lo, hi = m.groups()
        events.append(("cull", float(t), int(res), tuple(float(v) for v in lo.split(",")), tuple(float(v) for v in hi.split(","))))
print("events:", len(events), "nodes:", sum(1 for e in events if e[0] == "node"), "culls:", sum(1 for e in events if e[0] == "cull"))
# frames by time gap
frames = []; cur = []
for e in events:
    if cur and e[1] - cur[-1][1] > 0.010: frames.append(cur); cur = []
    cur.append(e)
if cur: frames.append(cur)
print("frames:", len(frames), [("%.2f" % f[0][1], sum(1 for e in f if e[0] == "node"), sum(1 for e in f if e[0] == "cull")) for f in frames[:16]])
# pair: a cull belongs to the most recent node event
def pairs(frame):
    out = []; last = None
    for e in frame:
        if e[0] == "node": last = e
        elif last is not None: out.append((last, e))
    return out
def holds(c):
    return all(c[3][a] - 5 <= pt[a] <= c[4][a] + 5 for a in range(3)) and (c[4][0] - c[3][0]) < 200
targets = collections.OrderedDict()
for f in frames:
    for n, c in pairs(f):
        if holds(c): targets.setdefault(n[2], (f[0][1], c[3], c[4]))
print("nodes whose (small) box held the point:", {k: ("t=%.2f" % v[0], v[1], v[2]) for k, v in targets.items()})
for obj in targets:
    print("== node", obj, "per frame:")
    for f in frames:
        ns = [e for e in f if e[0] == "node" and e[2] == obj]
        cs = [c for n, c in pairs(f) if n[2] == obj]
        print("   t=%.3f entered=%d %s culls=%s" % (f[0][1], len(ns), ["f5c=%08x f9c=%g c88=%s kind=%d a1=%02x parent=%s" % (n[3], n[4], n[5], n[7], n[8], n[9]) for n in ns[:1]], [(c[2], c[3], c[4]) for c in cs[:1]]))
# per frame node counts and f9c / kind stats
for f in frames[:8]:
    ns = [e for e in f if e[0] == "node"]
    print("frame t=%.2f nodes=%d kinds=%s f9c<1/128: %d parents=%d" % (f[0][1], len(ns), dict(collections.Counter(n[7] for n in ns)), sum(1 for n in ns if n[4] < 0.0078125), len(set(n[9] for n in ns))))
