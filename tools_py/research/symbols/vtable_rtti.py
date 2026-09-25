"""Locate retail vtables from the class-name string alone: string -> __RTTI__ object -> vtable(s).
(Task 7c groundwork, socom-pc-6c)

Run from the repo root:  python <this file> [ClassName ...]

With no argument it walks every demo __vt__ class, derives the class name from the mangled
symbol (the last <len><Name> component, so Q23zdb5CNode -> CNode), looks for "\\0Name\\0" in our
r0001 image, then for aligned words pointing at that string (the RTTI object), then for aligned
words pointing at the RTTI object (the vtables: Metrowerks lays a vtable out as [RTTI pointer, 0,
slot0, slot1, ...]). It prints how many demo classes resolve to exactly one, several or no retail
vtable, and the retail slot counts against the demo's. With class names as arguments it prints
the chain for each.

Class-name matching is by the bare name; a nested class (zdb::CNode) and a template
instantiation share bare names with others, which is one reason for the 'several' bucket.
"""
import collections
import os
import re
import struct
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py.elf_symbols import read_elf  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
OURS_ELF = "game/disc/socom2_game.elf"


def make_reader(elf):
    segs = [(va, data) for va, data in elf.segments]

    def rd(addr, n):
        for va, data in segs:
            if va <= addr and addr + n <= va + len(data):
                return data[addr - va:addr - va + n]
        return None
    return rd, segs


def find_all(segs, needle):
    out = []
    for va, data in segs:
        i = data.find(needle)
        while i >= 0:
            out.append(va + i)
            i = data.find(needle, i + 1)
    return out


def words_pointing(segs, target):
    return [a for a in find_all(segs, struct.pack("<I", target)) if a % 4 == 0]


def bare_class(mangled_vt):
    """'__vt__Q23zdb5CNode' -> 'CNode'; '__vt__10CZSealBody' -> 'CZSealBody'; templates -> None."""
    rest = mangled_vt[len("__vt__"):]
    if "<" in rest:
        return None
    comps = []
    q = re.match(r"Q(\d)", rest)
    pos = q.end() if q else 0
    while True:
        n = re.match(r"(\d+)", rest[pos:])
        if not n:
            break
        length = int(n.group(1))
        pos += n.end()
        comps.append(rest[pos:pos + length])
        pos += length
    return comps[-1] if comps else None


def slot_count(rd, vt, fnset):
    """Slots after the two-word header that are function starts, stopping at the first that is not."""
    k = 0
    while True:
        b = rd(vt + 8 + k * 4, 4)
        if not b or struct.unpack("<I", b)[0] not in fnset:
            return k
        k += 1


def resolve(segs, name):
    hits = find_all(segs, b"\x00" + name.encode() + b"\x00")
    rtti = [w for h in hits for w in words_pointing(segs, h + 1)]
    vts = [w for r in rtti for w in words_pointing(segs, r)]
    return hits, rtti, vts


def main() -> None:
    demo = read_elf(DEMO)
    rd_demo, _ = make_reader(demo)
    demo_fn = set(s for s, _e, _n in demo.functions)
    ours = read_elf(OURS_ELF)
    rd_ours, our_segs = make_reader(ours)
    import csv
    our_fn = set(int(r["Start"], 16) for r in csv.DictReader(open("recomp/socom2_ghidra.csv")))

    if len(sys.argv) > 1:
        for name in sys.argv[1:]:
            hits, rtti, vts = resolve(our_segs, name)
            print(f"{name}: string at {[hex(h + 1) for h in hits]}, RTTI object at "
                  f"{[hex(r) for r in rtti]}, vtables at {[hex(v) for v in vts]}, "
                  f"retail slots {[slot_count(rd_ours, v, our_fn) for v in vts]}")
        return

    vtables = [(name, start, end - start) for start, end, name in demo.objects
               if name.startswith("__vt__")]
    buckets = collections.Counter()
    demo_slots = retail_slots = 0
    rows = []
    for mangled, start, size in vtables:
        name = bare_class(mangled)
        if not name:
            buckets["template (skipped)"] += 1
            continue
        d = slot_count(rd_demo, start, demo_fn)
        hits, rtti, vts = resolve(our_segs, name)
        if not hits:
            buckets["name absent in retail"] += 1
        elif not rtti:
            buckets["string but no RTTI pointer"] += 1
        elif len(vts) == 1:
            buckets["one retail vtable"] += 1
            r = slot_count(rd_ours, vts[0], our_fn)
            demo_slots += d
            retail_slots += r
            rows.append((name, d, r, hex(vts[0])))
        elif len(vts) > 1:
            buckets["several retail vtables"] += 1
        else:
            buckets["RTTI but no vtable pointer"] += 1
    print(f"demo __vt__ classes {len(vtables)}:", dict(buckets))
    print(f"classes with exactly one retail vtable: demo slots {demo_slots}, retail slots {retail_slots}")
    same = sum(1 for _n, d, r, _v in rows if d == r)
    print(f"  of those, slot count equal in both builds: {same} of {len(rows)} "
          f"(equal-count vtables can be named slot for slot subject to the fixed-point check)")
    print("  largest (name, demo slots, retail slots, retail vtable):")
    for row in sorted(rows, key=lambda r: -r[2])[:15]:
        print("   ", row)


if __name__ == "__main__":
    main()
