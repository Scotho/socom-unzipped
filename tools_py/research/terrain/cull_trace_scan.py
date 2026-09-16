"""Scan a PS2X_CULL_TRACE log (research/31 section 16): per call the guest's result / mask against the IEEE
recomputation, and the boxes that contain a given world point (default: console fan c46's triangle, which our
draw list lacks in the spawn view)."""
import re, sys, collections
path = sys.argv[1]
pt = tuple(float(v) for v in sys.argv[2].split(",")) if len(sys.argv) > 2 else (947.0, -139.0, 969.0)
rows = []
rx = re.compile(r"t=([\d.]+) cam=(\w+) occl=(\d+) result=(\d+) guestMask=(\w+) planeMask=(\w+) ieee=(\w+)(?: lod=[^ ]+)? box=\(([^)]*)\)-\(([^)]*)\)")
for line in open(path):
    m = rx.match(line)
    if not m: continue
    t, cam, occl, res, gm, pm, ieee, lo, hi = m.groups()
    lo = tuple(float(v) for v in lo.split(",")); hi = tuple(float(v) for v in hi.split(","))
    rows.append((float(t), cam, int(occl), int(res), int(gm, 16), int(pm, 16), int(ieee, 16), lo, hi, line.rstrip()))
print("calls:", len(rows), "time span %.2f..%.2f s" % (rows[0][0], rows[-1][0]) if rows else "")
res = collections.Counter(r[3] for r in rows); print("results (2 culled, 1 visible, 0 partial):", dict(res))
mism = [r for r in rows if (r[4] & 0x3F3F) != (r[6] & 0x3F3F)]
print("guest mask != ieee mask:", len(mism))
for r in mism[:8]: print("   ", r[9][:200])
# frames: a burst of calls with the same t within ~30 ms
inside = [r for r in rows if all(r[7][a] - 5 <= pt[a] <= r[8][a] + 5 for a in range(3))]
print("boxes containing", pt, ":", len(inside))
for r in inside[:30]:
    print("   t=%.3f res=%d guest=%06x ieee=%06x plane=%06x box=%s-%s" % (r[0], r[3], r[4], r[6], r[5], r[7], r[8]))
# how many calls per ~frame: cluster by time gaps > 10 ms
frames = []; cur = []
for r in rows:
    if cur and r[0] - cur[-1][0] > 0.010: frames.append(cur); cur = []
    cur.append(r)
if cur: frames.append(cur)
print("call clusters (frames):", len(frames), "sizes:", [len(f) for f in frames[:12]])
