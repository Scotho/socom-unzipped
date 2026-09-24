"""How far do today's body-matched pairs get a vtable-slot matcher? (Task 7c groundwork, socom-pc-6c)

Run from the repo root:  python <this file>

Reads the SOCOM 1 demo's __vt__* OBJECT symbols and their slot words, maps the slots through Task 7's
987 pairs (prefix passes excluded), and tries to locate each vtable in our r0001 image from those
anchors alone: the first anchored slot's address must occur as an aligned word in our image, and at
least one other anchored slot must sit at the same slot spacing from it. Then counts the retail
slots of each uniquely located vtable (consecutive words that are function starts in our CSV).

Metrowerks vtable layout, checked on __vt__10CZSealBody: [pointer to the class's __RTTI__ object,
0, slot0, slot1, ...]. Slot indices here are word indices within the OBJECT, so index 2 is slot 0.
"""
import collections
import csv
import json
import os
import struct
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py.elf_symbols import read_elf  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
OURS_ELF = "game/disc/socom2_game.elf"
OURS_CSV = "recomp/socom2_ghidra.csv"
MATCHES = "game/demo_symbol_matches.json"


def make_reader(elf):
    segs = [(va, data) for va, data in elf.segments]

    def rd(addr, n):
        for va, data in segs:
            if va <= addr and addr + n <= va + len(data):
                return data[addr - va:addr - va + n]
        return None
    return rd, segs


def function_slots(rd, vaddr, size, fnset):
    """(word index, target) for every word of the OBJECT that is a function start."""
    blob = rd(vaddr, size)
    if not blob:
        return []
    words = struct.unpack("<%dI" % (len(blob) // 4), blob[:len(blob) // 4 * 4])
    return [(i, w) for i, w in enumerate(words) if w in fnset]


def main() -> None:
    demo = read_elf(DEMO)
    rd_demo, _ = make_reader(demo)
    demo_fn = set(s for s, _e, _n in demo.functions)
    vtables = [(name, start, end - start) for start, end, name in demo.objects
               if name.startswith("__vt__")]
    with_slots = [(n, v, s, function_slots(rd_demo, v, s, demo_fn)) for n, v, s in vtables]
    with_slots = [x for x in with_slots if len(x[3]) >= 2]
    print(f"demo __vt__ objects {len(vtables)}; with >= 2 function slots {len(with_slots)}; "
          f"slots in those {sum(len(x[3]) for x in with_slots)}")

    by_name = collections.defaultdict(list)
    for s, _e, n in demo.functions:
        by_name[n].append(s)
    pairs = json.load(open(MATCHES))["pairs"]
    demo_to_ours = {by_name[p["name"]][0]: int(p["addr"], 16) for p in pairs
                    if len(by_name[p["name"]]) == 1 and not p["how"].startswith("prefix")}

    ours = read_elf(OURS_ELF)
    rd_ours, our_segs = make_reader(ours)
    our_fn = set(int(r["Start"], 16) for r in csv.DictReader(open(OURS_CSV)))
    positions = collections.defaultdict(list)  # our function start -> aligned words holding it
    for va, data in our_segs:
        for i in range(0, len(data) - 3, 4):
            w = struct.unpack_from("<I", data, i)[0]
            if w in our_fn:
                positions[w].append(va + i)

    anchored = located = ambiguous = retail_slots = 0
    examples = []
    for name, _v, _s, slots in with_slots:
        anchors = [(i, demo_to_ours[w]) for i, w in slots if w in demo_to_ours]
        if len(anchors) < 2:
            continue
        anchored += 1
        i0, a0 = anchors[0]
        candidates = []
        for p in positions.get(a0, []):
            base = p - i0 * 4
            agree = sum(1 for i, a in anchors[1:] if (base + i * 4) in positions.get(a, []))
            if agree >= 1:
                candidates.append(base)
        if len(candidates) == 1:
            base, k = candidates[0], 0
            while True:
                b = rd_ours(base + k * 4, 4)
                if not b or struct.unpack("<I", b)[0] not in our_fn:
                    break
                k += 1
            located += 1
            retail_slots += k
            examples.append((name, len(slots), k, len(anchors), hex(base)))
        elif len(candidates) > 1:
            ambiguous += 1
    print(f"vtables with >= 2 anchored slots {anchored}; located uniquely {located}; "
          f"ambiguous {ambiguous}; retail slots in the located ones {retail_slots}")
    print("(name, demo function slots, retail slots counted from the anchored base, anchors, base):")
    for ex in examples:
        print("  ", ex)
    print("The base printed is the first ANCHORED word's slot-0 position, which can sit one word off "
          "the true vtable start; vtable_rtti.py finds the true start from the RTTI pointer.")


if __name__ == "__main__":
    main()
