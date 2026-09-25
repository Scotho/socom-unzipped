"""Per frame: the deferred-list enqueues ("defer" lines) and flushes ("flush" lines) of a PS2X_CULL_TRACE log, and
whether the named components (default: the three flat terrain patches of research/31 section 16) were enqueued.

Run: python -m tools_py.research.terrain.deferred_trace_scan <PS2X_CULL_TRACE log> [comp,comp,...]"""
import re, sys, collections
watch = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else {"014babc0", "014bacf0", "012e1550"}
rxd = re.compile(r"defer t=([\d.]+) obj=(\w+) list=(\w+) base=(\w+) bump=(\w+)->(\w+) used=(\d+) comp=(\w+) cflags=(\w+) cull=(\d+)")
rxf = re.compile(r"flush t=([\d.]+) list=(\w+) entries=(\d+) field0c=(\w+) used=(\d+)")
ev = []
for line in open(sys.argv[1]):
    m = rxd.match(line)
    if m: ev.append(("defer", float(m.group(1)), m.group(8), int(m.group(9), 16), int(m.group(7)), int(m.group(10)))); continue
    m = rxf.match(line)
    if m: ev.append(("flush", float(m.group(1)), int(m.group(3)), int(m.group(4), 16), int(m.group(5))))
print("defer events:", sum(1 for e in ev if e[0] == "defer"), "flush events:", sum(1 for e in ev if e[0] == "flush"))
frames = []; cur = []
for e in ev:
    if cur and e[1] - cur[-1][1] > 0.010: frames.append(cur); cur = []
    cur.append(e)
if cur: frames.append(cur)
for f in frames[:8]:
    d = [e for e in f if e[0] == "defer"]; fl = [e for e in f if e[0] == "flush"]
    hit = [e for e in d if e[2] in watch]
    print("frame t=%.2f defers=%d (last used=%s) flushes=%s watched=%s" % (f[0][1], len(d), d[-1][4] if d else None, [(e[2], "0x%x" % e[3], e[4]) for e in fl], [(e[2], "%08x" % e[3], e[5]) for e in hit]))
