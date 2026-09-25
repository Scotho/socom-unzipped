"""Vtable coverage after 7c: the classes the bare-name RTTI walk cannot open, and what opens them.
(Sprint 12 research wave, question 6; research/51)

Run from the repo root:  python tools_py/research/symbols/vtable_coverage.py [--r0004] [--list]

Read-only. Inputs: the SOCOM 1 demo ELF, our r0001 image, recomp/socom2_ghidra.csv,
game/demo_symbol_matches.json (Task 7's 987 pairs), the two proposals files under game/ (for the
"already named" refusal), and with --r0004 the r0004 image and csv. Writes nothing.

It prints, section by section (the section numbers are research/51's):

  0  the reproduction of vtable_rtti.py's five buckets (111 / 54 / 66 / 14 / 3), computed the same way;
  1  the retail vtable census by the layout itself -- an aligned word pointing at an RTTI object whose
     first word points at a NUL-preceded class-name string, then a zero word (primary) or a small
     negative this-offset (secondary), then >= 2 words that are csv function starts -- and how many
     of those the demo's 248 could map to by the demo's own RTTI string; the retail classes with no
     demo counterpart, largest first;
  2  the 54 "several": what the words pointing at each RTTI object actually are (vtables, secondary
     vtables, base-class lists of derived classes' RTTI objects, other), and how each splits;
  3  the 14 templates: the full RTTI string vs the bare template name, and whether body-matched slots
     tell the instantiations apart;
  4  the 66 absent: the qualified RTTI string, the anchor route, r0004's strings, Task 7 pairs per class;
  5  the 3 "string but no RTTI pointer": what references the bare string instead;
  6  fixed points and the positional rule (Goal 3 rules 2 and 3) over the 111 in four readings -- strict
     (as written), start (the vtable start is an implicit fixed point), whole (plus equal-count vtables
     with no fixed point), whole+shared (plus shared bodies two vtables name alike) -- with a leave-one-out
     holdout on the fixed points and a check against Task 7's own names; then lever by lever, cumulative;
  7  constructors: lui + addiu/ori forming a located vtable address, then a sw of that register; variant A
     is Goal 3 rule 4 as written (offset 0, within 8, exactly one function), B and C are refinements;
     each is scored on the demo against its own __ct__/__dt__ symbols, and on ours against Task 7 pairs;
  T  the closing table: lever / classes opened / marginal slots named under each reading.

--list adds the per-class lists behind each count. --r0004 repeats section 1 on r0004.
Addresses, names, counts and mnemonics only; no bytes are printed.
"""
import collections
import csv
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py.elf_symbols import read_elf  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
OURS_ELF = "game/disc/socom2_game.elf"
OURS_CSV = "recomp/socom2_ghidra.csv"
R4_ELF = "game/overlays_r0004/socom2_game_r0004.elf"
R4_CSV = "recomp/socom2_ghidra_r0004.csv"
MATCHES = "game/demo_symbol_matches.json"
PROPOSALS = ["game/demo_symbol_renames.csv", "game/demo_symbol_renames_7b.csv"]
NAME_RE = re.compile(r"^[A-Za-z_@][A-Za-z0-9_@:<>, *&\-.\[\]()]*$")
REGION_MARGIN = 0x100   # a 1-slot vtable counts only near the >=2-slot ones (see census_regions)
SIZE_RATIO, MIN_BYTES = 0.50, 64   # Goal 3 rule 3 (7b's tier B cuts)
WINDOW = 8                          # Goal 3 rule 4: the store within 8 instructions
OWN_CT = "one: the class's own __ct__"


# ----------------------------------------------------------------------------------------- images
class Img:
    def __init__(self, elf, fn_ranges):
        self.segs = [(va, data) for va, data in elf.segments]
        self.fn = set(s for s, _e in fn_ranges)
        self.words = []  # (va, tuple of words) per segment
        for va, data in self.segs:
            n = len(data) // 4
            self.words.append((va, struct.unpack_from("<%dI" % n, data, 0)))

    def rd(self, a, n):
        for va, data in self.segs:
            if va <= a and a + n <= va + len(data):
                return data[a - va:a - va + n]
        return None

    def w(self, a):
        b = self.rd(a, 4)
        return struct.unpack("<I", b)[0] if b else None

    def cstr(self, a, limit=300):
        for va, data in self.segs:
            if va <= a < va + len(data):
                end = data.find(b"\0", a - va, a - va + limit)
                if end < 0:
                    return None
                return data[a - va:end].decode("latin1")
        return None

    def find_all(self, needle):
        out = []
        for va, data in self.segs:
            i = data.find(needle)
            while i >= 0:
                out.append(va + i)
                i = data.find(needle, i + 1)
        return out

    def words_pointing(self, target):
        return [a for a in self.find_all(struct.pack("<I", target)) if a % 4 == 0]

    def slots(self, vt):
        """Consecutive function-start words after the two-word header (vtable_rtti.slot_count)."""
        out = []
        while True:
            x = self.w(vt + 8 + 4 * len(out))
            if x is None or x not in self.fn:
                return out
            out.append(x)


def census(img, min_slots):
    """Every (addr, rtti, name, offset, slots) matching the layout: [RTTI*, 0 | -off, fn, fn, ...]."""
    out = []
    for va, words in img.words:
        n = len(words)
        for i in range(n - 2):
            r = words[i]
            if r == 0 or r % 4:
                continue
            off = words[i + 1]
            if off != 0 and off < 0xFFFF0000:
                continue
            k = 0
            while i + 2 + k < n and words[i + 2 + k] in img.fn:
                k += 1
            if k < min_slots:
                continue
            s = img.w(r)
            if not s:
                continue
            name = img.cstr(s)
            if not name or not NAME_RE.match(name) or img.rd(s - 1, 1) != b"\0":
                continue
            out.append(dict(addr=va + 4 * i, rtti=r, name=name, off=off,
                            slots=list(words[i + 2:i + 2 + k])))
    return out


def census_regions(full):
    """The address spans the >=2-slot vtables occupy (per 64 KB-gap cluster), plus a margin."""
    addrs = sorted(v["addr"] for v in full if len(v["slots"]) >= 2)
    spans = []
    for a in addrs:
        if spans and a - spans[-1][1] < 0x10000:
            spans[-1][1] = a
        else:
            spans.append([a, a])
    return [(lo - REGION_MARGIN, hi + REGION_MARGIN) for lo, hi in spans]


def in_regions(a, regions):
    return any(lo <= a < hi for lo, hi in regions)


def comps(mangled):
    rest = mangled[len("__vt__"):]
    q = re.match(r"Q(\d)", rest)
    pos, out = (q.end() if q else 0), []
    while True:
        n = re.match(r"(\d+)", rest[pos:])
        if not n:
            return out
        length = int(n.group(1))
        pos += n.end()
        out.append(rest[pos:pos + length])
        pos += length


def bare_class(mangled):
    if "<" in mangled[len("__vt__"):]:
        return None
    c = comps(mangled)
    return c[-1] if c else None


def load_csv(path):
    rows = list(csv.DictReader(open(path)))
    return [(int(r["Start"], 16), int(r["End"], 16), r["Name"]) for r in rows]


# ------------------------------------------------------------------------------------- MIPS scan
def vt_events(img, ranges, targets, window=32):
    """{function start: ([(index, vtable, store offset, through this, distance)], [jal targets])}.

    A vtable address formed by lui + addiu/ori (the pair at most 8 instructions apart), then the first sw
    of the formed register within `window` instructions while the register is not overwritten. `through
    this` is True when the store's base register is a0 or a register a0 was copied into (move / addiu 0).
    """
    out = {}
    for start, end in ranges:
        blob = img.rd(start, end - start) if end > start else None
        if not blob:
            continue
        ins = struct.unpack_from("<%dI" % (len(blob) // 4), blob, 0)
        lui, events, jals, this = {}, [], [], {4}
        for i, x in enumerate(ins):
            op, rs, rt, imm = x >> 26, (x >> 21) & 31, (x >> 16) & 31, x & 0xFFFF
            if op == 0x03:
                jals.append(((x & 0x3FFFFFF) << 2) | (start & 0xF0000000))
            if op == 0 and (x & 0x3F) in (0x21, 0x25, 0x2D):          # addu / or / daddu: a move?
                rd = (x >> 11) & 31
                if (rs in this and rt == 0) or (rt in this and rs == 0):
                    this.add(rd)
                elif rd in this:
                    this.discard(rd)
            if op == 0x09 and imm == 0 and rs in this:
                this.add(rt)
            if op == 0x0F:
                lui[rt] = (imm, i)
                continue
            if op in (0x09, 0x0D) and rs in lui and i - lui[rs][1] <= 8:
                hi = lui[rs][0]
                val = (((hi << 16) + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF if op == 0x09
                       else (hi << 16) | imm)
                if val in targets:
                    for k in range(i + 1, min(i + 1 + window, len(ins))):
                        y = ins[k]
                        if y >> 26 == 0x2B and (y >> 16) & 31 == rt and (y >> 21) & 31 != rt:
                            off = y & 0xFFFF
                            events.append((k, val, off - 0x10000 if off & 0x8000 else off,
                                           (y >> 21) & 31 in this, k - i))
                            break
                        if (y >> 26) in (0x09, 0x0D, 0x0F, 0x23, 0x0C) and (y >> 16) & 31 == rt:
                            break
                        if y >> 26 == 0 and (y >> 11) & 31 == rt and (y & 0x3F) not in (0x08, 0x09):
                            break
            if op in (0x09, 0x0D, 0x0C, 0x0A, 0x0B, 0x0E, 0x23, 0x37, 0x20, 0x21, 0x24, 0x25):
                lui.pop(rt, None)
            elif op == 0:
                lui.pop((x >> 11) & 31, None)
        if events or jals:
            out[start] = (events, jals)
    return out


# ------------------------------------------------------------------------------------ alignment
def align(dslots, rslots, d2o):
    """Goal 3 rule 2. Returns (fixed points [(i, j)], conflicts, runs [(di, rj, len, equal, where)])."""
    fps = []
    for i, d in enumerate(dslots):
        o = d2o.get(d)
        if o is None:
            continue
        js = [j for j, r in enumerate(rslots) if r == o]
        if len(js) == 1:
            fps.append((i, js[0]))
    chain, conflicts = [], 0
    for i, j in fps:            # keep the strictly increasing chain in demo order
        if chain and j <= chain[-1][1]:
            conflicts += 1
            continue
        chain.append((i, j))
    runs = []
    if chain:
        i0, j0 = chain[0]
        runs.append((0, 0, (i0, j0), i0 == j0, "before first"))
        for (a, b), (c, d) in zip(chain, chain[1:]):
            runs.append((a + 1, b + 1, (c - a - 1, d - b - 1), c - a == d - b, "between"))
        a, b = chain[-1]
        runs.append((a + 1, b + 1, (len(dslots) - a - 1, len(rslots) - b - 1),
                     len(dslots) - a == len(rslots) - b, "after last"))
    return chain, conflicts, runs


def main() -> None:
    argv = sys.argv[1:]
    show = "--list" in argv

    demo_elf = read_elf(DEMO)
    demo_fns = demo_elf.functions
    demo = Img(demo_elf, [(s, e) for s, e, _n in demo_fns])
    demo_name = {s: n for s, _e, n in demo_fns}
    demo_size = {s: e - s for s, e, _n in demo_fns}
    demo_objs = demo_elf.objects

    our_elf = read_elf(OURS_ELF)
    our_rows = load_csv(OURS_CSV)
    ours = Img(our_elf, [(s, e) for s, e, _n in our_rows])
    our_name = {s: n for s, _e, n in our_rows}
    our_size = {s: e - s for s, e, _n in our_rows}

    by_name = collections.defaultdict(list)
    for s, _e, n in demo_fns:
        by_name[n].append(s)
    pairs = json.load(open(MATCHES))["pairs"]
    d2o_all, d2o = {}, {}
    for p in pairs:
        if len(by_name[p["name"]]) != 1:
            continue
        d2o_all[by_name[p["name"]][0]] = int(p["addr"], 16)
        if not p["how"].startswith("prefix"):
            d2o[by_name[p["name"]][0]] = int(p["addr"], 16)
    paired_ours = set(int(p["addr"], 16) for p in pairs)
    o2name = {int(p["addr"], 16): p["name"] for p in pairs}
    proposed = set()
    for path in PROPOSALS:
        if os.path.exists(path):
            for r in csv.DictReader(line for line in open(path) if not line.startswith("#")):
                proposed.add(int(r["Address"], 16))
    hand = set(s for s, n in our_name.items() if not (n.startswith("FUN_") or n.startswith("thunk_FUN_")))

    # ---- 0: the five buckets, as vtable_rtti.py computes them
    demo_vts = []
    for s, e, n in demo_objs:
        if not n.startswith("__vt__"):
            continue
        r = demo.w(s)
        qual = demo.cstr(demo.w(r)) if r else None
        words = [demo.w(s + 4 * i) for i in range((e - s) // 4)]
        parts = []  # (word index of header, offset, slot targets)
        for i in range(len(words) - 1):
            if i == 0 or (r and words[i] == r and words[i + 1] >= 0xFFFF0000):
                k = []
                while i + 2 + len(k) < len(words) and words[i + 2 + len(k)] in demo.fn:
                    k.append(words[i + 2 + len(k)])
                parts.append((i, words[i + 1], k))
        full = qual or "::".join(comps(n))
        b = bare_class(n)
        if not b:
            bucket, bare_vts = "template", []
        else:
            hits = ours.find_all(b"\x00" + b.encode() + b"\x00")
            rtti = [x for h in hits for x in ours.words_pointing(h + 1)]
            bare_vts = [x for r2 in rtti for x in ours.words_pointing(r2)]
            if not hits:
                bucket = "absent"
            elif not rtti:
                bucket = "string-no-rtti"
            elif len(bare_vts) == 1:
                bucket = "one"
            elif bare_vts:
                bucket = "several"
            else:
                bucket = "rtti-no-vt"
        demo_vts.append(dict(mangled=n, start=s, end=e, rtti=r, qual=qual, full=full, bare=b, bucket=bucket,
                             bare_vts=bare_vts, parts=parts, dslots=demo.slots(s)))
    buckets = collections.Counter(d["bucket"] for d in demo_vts)
    print("== 0. vtable_rtti.py's buckets, reproduced")
    print(f"demo __vt__ objects {len(demo_vts)}: {dict(buckets)}")
    one = [d for d in demo_vts if d["bucket"] == "one"]
    print(f"  'one': demo slots {sum(len(d['dslots']) for d in one)}, retail slots "
          f"{sum(len(ours.slots(d['bare_vts'][0])) for d in one)}; equal counts "
          f"{sum(1 for d in one if len(d['dslots']) == len(ours.slots(d['bare_vts'][0])))}")
    print(f"  demo vtables whose RTTI word is 0 (no RTTI object; name from the mangling): "
          f"{sum(1 for d in demo_vts if not d['rtti'])}")

    # ---- 1: the census
    full_census = census(ours, 1)
    regions = census_regions(full_census)
    retail = [v for v in full_census if len(v["slots"]) >= 2 or in_regions(v["addr"], regions)]
    two = [v for v in full_census if len(v["slots"]) >= 2]
    one_slot_out = [v for v in full_census if len(v["slots"]) == 1 and not in_regions(v["addr"], regions)]
    print("\n== 1. the retail vtable census, by the layout")
    print(f">=2 function slots: {len(two)} vtables ({sum(1 for v in two if v['off'] == 0)} primary, "
          f"{sum(1 for v in two if v['off'])} secondary), {len(set(v['name'] for v in two))} class names, "
          f"{len(set(v['rtti'] for v in two))} RTTI objects, {sum(len(v['slots']) for v in two)} slots")
    print(f"vtable regions (from the >=2 set, +/-0x{REGION_MARGIN:x}): "
          + ", ".join(f"0x{lo:x}-0x{hi:x}" for lo, hi in regions))
    print(f"1-slot matches inside those regions (real 1-slot vtables): "
          f"{len(retail) - len(two)}; 1-slot matches outside them (code-segment data, not vtables): "
          f"{len(one_slot_out)} ({len(set(v['name'] for v in one_slot_out))} names)")
    print(f"all retail vtables (>=2, or 1 inside a region): {len(retail)} "
          f"({sum(1 for v in retail if v['off'] == 0)} primary, {sum(1 for v in retail if v['off'])} secondary), "
          f"{len(set(v['name'] for v in retail))} class names")
    bogus_rows = sum(1 for s, _e, _n in our_rows if in_regions(s, regions))
    print(f"csv rows whose Start lies inside a vtable region (data taken for code): {bogus_rows}")
    slot_into_region = sum(1 for v in retail for t in v["slots"] if in_regions(t, regions))
    print(f"retail slot words pointing into a vtable region: {slot_into_region}")

    # demo side of the same census, as the pattern's check
    dcen = census(demo, 1)
    dvt_starts = set(d["start"] for d in demo_vts)
    dprim = [v for v in dcen if v["off"] == 0]
    print(f"the same pattern on the demo (>=1 slot): {len(dcen)} ({len(dprim)} primary, "
          f"{len(dcen) - len(dprim)} secondary); primaries at a __vt__ symbol {sum(1 for v in dprim if v['addr'] in dvt_starts)} "
          f"of {len(demo_vts)}; the {len(demo_vts) - sum(1 for v in dprim if v['addr'] in dvt_starts)} missed have "
          f"RTTI word 0, or no function in the first slot")

    rv_by_name = collections.defaultdict(list)
    for v in retail:
        rv_by_name[v["name"]].append(v)
    demo_names = set(d["full"] for d in demo_vts)
    mapped = [v for v in retail if v["name"] in demo_names]
    print(f"retail vtables whose RTTI string is a demo __vt__ class's own RTTI string: {len(mapped)} "
          f"({sum(1 for v in mapped if v['off'] == 0)} primary) over {len(set(v['name'] for v in mapped))} classes; "
          f"(>=2-slot only: {sum(1 for v in two if v['name'] in demo_names)})")
    demo_rtti_names = set(demo.cstr(demo.w(s)) for s, _e, n in demo_objs if n.startswith("__RTTI__"))
    new = collections.defaultdict(list)
    for v in retail:
        if v["name"] not in demo_names and v["name"] not in demo_rtti_names:
            new[v["name"]].append(v)
    lastcomp = lambda nm: nm.split("::")[-1]
    demo_last = collections.Counter(lastcomp(n) for n in demo_names)
    renamed = sorted(n for n in new if demo_last.get(lastcomp(n)))
    print(f"retail class names with no demo counterpart (not a demo __vt__ or __RTTI__ string): {len(new)} "
          f"classes, {sum(len(v) for v in new.values())} vtables, {sum(len(x['slots']) for v in new.values() for x in v)} slots; "
          f"of them {len(renamed)} share a last component with a demo class: {renamed}")
    if show:
        print(f"  every retail vtable class name ({len(rv_by_name)}): {sorted(rv_by_name)}")
    print("  largest by slot count (name, slots over its vtables, vtables):")
    for nm, vs in sorted(new.items(), key=lambda kv: -sum(len(x["slots"]) for x in kv[1]))[:25]:
        print(f"    {nm}  {sum(len(x['slots']) for x in vs)}  {len(vs)}")
    if "--r0004" in argv and os.path.exists(R4_ELF):
        r4_rows = load_csv(R4_CSV)
        r4 = Img(read_elf(R4_ELF), [(s, e) for s, e, _n in r4_rows])
        c4 = census(r4, 2)
        n1, n4 = set(v["name"] for v in two), set(v["name"] for v in c4)
        print(f"r0004, the same census (>=2 slots): {len(c4)} vtables ({sum(1 for v in c4 if v['off'] == 0)} primary), "
              f"{len(n4)} names; names only in r0001 {sorted(n1 - n4)}, only in r0004 {sorted(n4 - n1)}")

    # exact resolution for every demo class: its own RTTI string -> retail vtables by layout
    def exact(d):
        vs = rv_by_name.get(d["full"], [])
        return [v for v in vs if v["off"] == 0], [v for v in vs if v["off"]]

    # base lists: every word inside an RTTI object's base-class list
    rtti_objs = set(v["rtti"] for v in full_census)
    while True:
        more = set()
        for r in rtti_objs:
            bl = ours.w(r + 4)
            a = bl
            while bl and a < bl + 64 * 8:
                x = ours.w(a)
                if not x:
                    break
                more.add(x)
                a += 8
        if more <= rtti_objs:
            break
        rtti_objs |= more
    baselist = set()
    for r in rtti_objs:
        bl = ours.w(r + 4)
        a = bl
        while bl and a < bl + 64 * 8:
            if not ours.w(a):
                break
            baselist.add(a)
            a += 8
    vt_at = {v["addr"]: v for v in full_census}

    def kind(a):
        if a in vt_at:
            v = vt_at[a]
            if len(v["slots"]) < 2 and not in_regions(a, regions):
                return "1-slot match outside regions"
            if v["off"]:
                return "secondary vtable"
            return "primary vtable" if len(v["slots"]) >= 2 else "1-slot primary vtable"
        if a in baselist:
            return "base-class list word"
        return "other"

    # ---- 2: the 54
    print("\n== 2. the 54 'several retail vtables'")
    sev = [d for d in demo_vts if d["bucket"] == "several"]
    kinds = collections.Counter()
    split = collections.defaultdict(list)
    for d in sev:
        ks = collections.Counter(kind(a) for a in d["bare_vts"])
        kinds.update(ks)
        prim, sec = exact(d)
        qualified = d["mangled"][6:7] == "Q"
        demo_pair = len(d["parts"]) > 1
        if qualified and not prim and not sec:
            k = "qualified demo name, retail string differs"
        elif len(prim) == 1 and not sec:
            k = "layout filter alone: one primary"
        elif len(prim) == 1 and sec:
            k = "primary+secondary pair, demo has the pair" if demo_pair else \
                "primary+secondary pair, demo has primary only"
        elif not prim and sec:
            k = "secondary only (the primary has no slot of its own)"
        elif not prim and not sec:
            k = "no vtable by the layout (all slots pure-virtual zeros, or only base lists point at the RTTI)"
        else:
            k = "several primaries"
        split[k].append(d["full"])
    print(f"words pointing at the 54 classes' RTTI objects: {sum(kinds.values())}: {dict(kinds)}")
    print(f"qualified (Q) demo names among the 54: {sum(1 for d in sev if d['mangled'][6:7] == 'Q')}")
    for k, v in sorted(split.items(), key=lambda kv: -len(kv[1])):
        print(f"  {k}: {len(v)}" + (f"  {v}" if show or len(v) <= 6 else ""))
    # the pair: which vtable the body-matched slots fall in
    pair_ok = pair_bad = pair_none = 0
    for d in sev:
        prim, sec = exact(d)
        if len(prim) != 1 or not sec:
            continue
        for part_i, (hdr, off, ds) in enumerate(d["parts"]):
            anchors = [d2o[x] for x in ds if x in d2o]
            where = collections.Counter()
            for a in anchors:
                where["primary" if a in prim[0]["slots"] else
                      ("secondary" if any(a in s["slots"] for s in sec) else "neither")] += 1
            want = "primary" if part_i == 0 else "secondary"
            if not anchors:
                pair_none += 1
            elif where[want] and not any(where[k] for k in where if k != want):
                pair_ok += 1
            else:
                pair_bad += 1
                print(f"    pair check, {d['full']} demo part {part_i}: {dict(where)}")
    print(f"  pair check, per demo part (primary / secondary): body-matched slots all in the same-shape retail "
          f"vtable {pair_ok}, elsewhere {pair_bad}, no body-matched slot {pair_none}")

    # ---- 3: templates
    print("\n== 3. the 14 templates")
    tpl = [d for d in demo_vts if d["bucket"] == "template"]
    opened_t = 0
    for d in tpl:
        prim, sec = exact(d)
        stem = d["full"].split("<")[0]
        bare = stem.split("::")[-1]
        bare_str = bool(ours.find_all(b"\x00" + bare.encode() + b"\x00"))
        family = sorted(set(v["name"] for v in retail if v["name"].split("<")[0] == stem))
        fam_prim = [v for v in retail if v["name"].split("<")[0] == stem and v["off"] == 0]
        anchors = [d2o[x] for x in d["dslots"] if x in d2o]
        inside = [v["name"] for v in fam_prim if any(a in v["slots"] for a in anchors)]
        told = len(set(inside)) == 1 and inside[0] == d["full"]
        opened_t += len(prim) == 1
        print(f"  {d['full']}: full string -> {len(prim)} primary + {len(sec)} secondary; bare '{bare}' as a "
              f"string {'yes' if bare_str else 'no'}; '{stem}<' names {len(family)} retail classes, "
              f"{len(fam_prim)} primary vtables; body-matched slots {len(anchors)}, "
              f"in {len(set(inside))} of the family{' (tells the instantiation)' if told else ''}")
    print(f"templates opened by the full RTTI string: {opened_t} of {len(tpl)}")

    # ---- 4: the 66 absent
    print("\n== 4. the 66 'absent'")
    ab = [d for d in demo_vts if d["bucket"] == "absent"]
    by_q = [d for d in ab if len(exact(d)[0]) == 1]
    amb = [d for d in ab if len(exact(d)[0]) > 1]
    rest = [d for d in ab if not exact(d)[0] and not exact(d)[1]]
    print(f"resolved by the demo's qualified RTTI string to one primary: {len(by_q)} "
          f"(of them Q-qualified {sum(1 for d in by_q if d['mangled'][6:7] == 'Q')}); "
          f"to several primaries: {len(amb)} {[d['full'] for d in amb]}; still absent: {len(rest)}")
    if show:
        print("  by qualified string:", [d["full"] for d in by_q])
    for d in amb:
        for v in exact(d)[0]:
            print(f"    {d['full']}: primary 0x{v['addr']:x} (RTTI 0x{v['rtti']:x}), {len(v['slots'])} slots, "
                  f"body-matched slots {sum(1 for x in d['dslots'] if d2o.get(x) in v['slots'])}")
    # anchors route, r0004 strings, pairs per class
    positions = collections.defaultdict(list)
    for va, words in ours.words:
        for i, x in enumerate(words):
            if x in ours.fn:
                positions[x].append(va + 4 * i)
    r4seg = None
    if os.path.exists(R4_ELF):
        r4seg = Img(read_elf(R4_ELF), [])
    stats = collections.Counter()
    for d in rest:
        fn_slots = [(i, x) for i, x in enumerate([demo.w(a) for a in range(d["start"], d["end"], 4)]) if x in demo.fn]
        anchors = [(i, d2o[x]) for i, x in fn_slots if x in d2o]
        located = None
        if len(anchors) >= 2:
            i0, a0 = anchors[0]
            cands = [p - i0 * 4 for p in positions.get(a0, [])
                     if any((p - i0 * 4 + i * 4) in positions.get(a, []) for i, a in anchors[1:])]
            located = cands[0] if len(cands) == 1 else ("ambiguous" if cands else None)
        name = d["full"]
        in_r4 = bool(r4seg and r4seg.find_all(b"\x00" + name.encode() + b"\x00"))
        pat = re.compile(r"__%d%s(?:F|C|$)" % (len(name), re.escape(name)))
        methods = [s for s, _e, n in demo_fns if pat.search(n)]
        with_pair = [m for m in methods if m in d2o_all]
        stats["anchors >= 2"] += len(anchors) >= 2
        stats["located by anchors"] += isinstance(located, int)
        stats["string in r0004"] += in_r4
        stats["methods with no Task 7 pair"] += bool(methods) and not with_pair
        stats["methods with >= 1 pair"] += bool(with_pair)
        stats["no demo method by name"] += not methods
        if show or with_pair or len(anchors) >= 2 or in_r4:
            print(f"    {name}: demo methods {len(methods)}, paired {len(with_pair)}, slot anchors {len(anchors)}, "
                  f"located {located if not isinstance(located, int) else hex(located)}, r0004 string {in_r4}")
    print(f"  of the {len(rest)} still absent: {dict(stats)}")
    if show:
        print("  still absent:", [d["full"] for d in rest])

    # ---- 5: the 3 string-no-rtti
    print("\n== 5. the 3 'string but no RTTI pointer'")
    code_ranges = [(s, e) for s, e, _n in our_rows if not in_regions(s, regions) and e > s]
    for d in [d for d in demo_vts if d["bucket"] == "string-no-rtti"]:
        hits = ours.find_all(b"\x00" + d["bare"].encode() + b"\x00")
        refs = []
        for h in hits:
            s = h + 1
            data_refs = ours.words_pointing(s)
            code = vt_stores_like(ours, code_ranges, s)
            refs.append((s, data_refs, code))
        prim, _sec = exact(d)
        for s, data_refs, code in refs:
            print(f"  '{d['bare']}' at 0x{s:x}: aligned data words pointing at it {len(data_refs)}"
                  f"{' ' + str([hex(x) for x in data_refs]) if data_refs else ''}; lui+addiu forming it in "
                  f"{len(code)} function(s) {[(hex(c), o2name.get(c, 'no Task 7 pair')) for c in code][:4]}; "
                  f"the class's own RTTI string '{d['full']}' -> {len(prim)} primary vtable")

    # ---- 6: fixed points and the rule
    print("\n== 6. fixed points and Goal 3's rule 2-3")
    shared_retail = collections.Counter(t for v in retail for t in set(v["slots"]))
    shared_demo = collections.Counter()
    for d in demo_vts:
        for _h, _o, ds in d["parts"]:
            shared_demo.update(set(ds))
    named_rows = hand | paired_ours | proposed

    def evaluate(cls, label, mode="strict", shared_ok=False, quiet=False):
        """cls: [(class, demo slots, retail slots)]. mode: 'strict' (Goal 3 rule 2 as written), 'start' (the
        vtable start is an implicit fixed point), 'whole' ('start' plus an equal-count vtable with no fixed
        point named whole). shared_ok: a shared body is kept when >= 2 vtables propose it, all one name."""
        c = collections.Counter()
        props = collections.defaultdict(set)    # retail addr -> demo names
        voters = collections.Counter()          # retail addr -> vtables proposing it
        rev = collections.defaultdict(set)      # demo name -> retail addrs
        holdout = collections.Counter()
        for _nm, ds, rs in cls:
            chain, conflicts, runs = align(ds, rs, d2o)
            c["vtables"] += 1
            c["conflicting fixed points"] += conflicts
            c["fp=0"] += len(chain) == 0
            c["fp>=1"] += len(chain) >= 1
            c["fp>=2"] += len(chain) >= 2
            c["fixed points"] += len(chain)
            c["demo slots"] += len(ds)
            c["retail slots"] += len(rs)
            if not chain and mode == "whole" and len(ds) == len(rs):
                runs = [(0, 0, (len(ds), len(rs)), True, "whole")]
                c["equal-count, no fixed point, named whole"] += 1
            for (di, rj, (ld, _lr), eq, where) in runs:
                if where == "before first" and mode == "strict":
                    continue
                if not eq:
                    c["slots in unequal runs"] += ld
                    continue
                c["slots in equal runs"] += ld
                for k in range(ld):
                    d, r = ds[di + k], rs[rj + k]
                    props[r].add(demo_name[d])
                    voters[r] += 1
                    rev[demo_name[d]].add(r)
            for x in range(len(chain)):   # leave one fixed point out, re-derive it, compare
                i, j = chain[x]
                got = predict(i, chain[:x] + chain[x + 1:], len(ds), len(rs), mode != "strict")
                if got is None and mode == "whole" and len(chain) == 1 and len(ds) == len(rs):
                    got = i
                holdout["reached" if got is not None else "not reached"] += 1
                if got is not None:
                    holdout["right" if got == j else "wrong"] += 1
        c["distinct retail rows proposed"] = len(props)
        refused = collections.Counter()
        named = 0
        for r, names in props.items():
            d_addr = by_name[next(iter(names))][0]
            if len(names) > 1 or any(len(rev[n]) > 1 for n in names):
                refused["name collision (one name, two rows, or two names, one row)"] += 1
            elif r in hand:
                refused["already named: hand-named csv row"] += 1
            elif r in paired_ours or r in proposed:
                refused["already named: a Task 7 / 7b row"] += 1
                if r in o2name:
                    c["check: Task 7 row, same name" if o2name[r] in names else "check: Task 7 row, OTHER name"] += 1
            elif shared_retail[r] > 1 and not (shared_ok and voters[r] >= 2):
                refused["shared base body (in >= 2 retail vtables)"] += 1
            elif min(our_size.get(r, 0), demo_size[d_addr]) < MIN_BYTES:
                refused["body under 64 bytes"] += 1
            elif min(our_size[r], demo_size[d_addr]) / max(our_size[r], demo_size[d_addr]) < SIZE_RATIO:
                refused["size ratio under 0.50"] += 1
            else:
                named += 1
                c["named, demo target inherited (shared in the demo)"] += shared_demo[d_addr] > 1
                c["named, shared in retail (shared_ok)"] += shared_retail[r] > 1
        if not quiet:
            print(f"  {label}: {dict(c)}")
            print(f"    refused {dict(refused)}; NAMED {named}; holdout on fixed points {dict(holdout)}")
        return c, named, refused, holdout

    one_rows = [(d["full"], d["dslots"], ours.slots(d["bare_vts"][0])) for d in one]
    eqc = [x for x in one_rows if len(x[1]) == len(x[2])]
    eq_fp = [len(align(ds, rs, d2o)[0]) for _n, ds, rs in eqc]
    print(f"the 111's equal-count classes: {len(eqc)}; with >= 1 fixed point {sum(1 for n in eq_fp if n)}, "
          f"with none {sum(1 for n in eq_fp if not n)}; fixed points in them at the same index both sides "
          f"{sum(1 for _n, ds, rs in eqc for i, j in align(ds, rs, d2o)[0] if i == j)} of {sum(eq_fp)}")
    all_r = [t for _n, _d, rs in one_rows for t in rs]
    all_d = [t for _n, ds, _r in one_rows for t in ds]
    print(f"the 111's {len(all_r)} retail slot words: shared body (target in >= 2 retail vtables) "
          f"{sum(1 for t in all_r if shared_retail[t] > 1)}, already-named row "
          f"{sum(1 for t in all_r if t in named_rows)}; distinct targets {len(set(all_r))}")
    print(f"the 111's {len(all_d)} demo slot words: target in >= 2 demo vtables {sum(1 for t in all_d if shared_demo[t] > 1)}, "
          f"paired by Task 7 (non-prefix) {sum(1 for t in all_d if t in d2o)}, with prefix {sum(1 for t in all_d if t in d2o_all)}")
    print("the 111:")
    evaluate(one_rows, "strict (rule 2 as written: between fixed points and after the last)")
    evaluate(one_rows, "start (the vtable start is an implicit fixed point)", mode="start")
    evaluate(one_rows, "whole (start, plus equal-count vtables with no fixed point)", mode="whole")
    evaluate(one_rows, "whole + shared bodies two vtables agree on", mode="whole", shared_ok=True)

    def rows_for(ds):
        out = []
        for d in ds:
            prim, sec = exact(d)
            if len(prim) != 1:
                continue
            out.append((d["full"], d["dslots"], prim[0]["slots"]))
            dsec = d["parts"][1:]
            if len(dsec) == 1 and len(sec) == 1:
                out.append((d["full"] + " (secondary)", dsec[0][2], sec[0]["slots"]))
        return out
    levers = [
        ("bare-name RTTI walk (the 111)", one, one_rows),
        ("layout filter on the 'several' (one primary)",
         [d for d in sev if len(exact(d)[0]) == 1 and not exact(d)[1]], None),
        ("primary/secondary pair by shape", [d for d in sev if len(exact(d)[0]) == 1 and exact(d)[1]], None),
        ("the demo's qualified RTTI string (absent)", by_q, None),
        ("the qualified string for the 3 'no RTTI'", [d for d in demo_vts if d["bucket"] == "string-no-rtti"], None),
        ("the full template RTTI string", tpl, None),
    ]
    print("cumulative, lever by lever (classes / vtables / strict NAMED / start NAMED / whole NAMED / whole+shared NAMED):")
    acc, table = [], []
    prev = [0, 0, 0, 0]
    for label, ds, rows in levers:
        rows = rows if rows is not None else rows_for(ds)
        acc += rows
        got = [evaluate(acc, label, mode=m, shared_ok=so, quiet=True)[1]
               for m, so in (("strict", False), ("start", False), ("whole", False), ("whole", True))]
        fp1 = sum(1 for _n, dsl, rsl in rows if align(dsl, rsl, d2o)[0])
        print(f"  + {label}: {len(ds)} classes / {len(rows)} vtables ({fp1} with a fixed point) -> cumulative "
              f"{got[0]} / {got[1]} / {got[2]} / {got[3]}; marginal "
              f"{got[0] - prev[0]} / {got[1] - prev[1]} / {got[2] - prev[2]} / {got[3] - prev[3]}")
        table.append((label, len(ds), [g - p for g, p in zip(got, prev)]))
        prev = got
    eq_all = [(ds, rs) for _n, ds, rs in acc if len(ds) == len(rs)]
    fp_eq = [(i, j) for ds, rs in eq_all for i, j in align(ds, rs, d2o)[0]]
    print(f"all opened: equal-count vtables {len(eq_all)} of {len(acc)}; with >= 1 fixed point "
          f"{sum(1 for ds, rs in eq_all if align(ds, rs, d2o)[0])}; their fixed points at the same index "
          f"{sum(1 for i, j in fp_eq if i == j)} of {len(fp_eq)}")
    print("all opened vtables together:")
    for m, so, lab in (("strict", False, "strict"), ("start", False, "start"), ("whole", False, "whole"),
                       ("whole", True, "whole + shared")):
        evaluate(acc, lab, mode=m, shared_ok=so)

    # ---- 7: constructors
    print("\n== 7. constructors: lui + addiu/ori forming a vtable address, then a sw of that register")
    resolved = [(d, exact(d)[0][0]) for d in demo_vts if len(exact(d)[0]) == 1]
    targets = set(v["addr"] for v in retail)
    ev_ours = vt_events(ours, code_ranges, targets)
    ev_demo = vt_events(demo, [(s, e) for s, e, _n in demo_fns], set(d["start"] for d in demo_vts))

    def top_callee(ev):
        storing = [f for f, (e, _j) in ev.items() if e]
        cnt = collections.Counter(t for f in storing for t in set(ev[f][1]))
        return len(storing), cnt.most_common(2)
    ns, tc = top_callee(ev_demo)
    dl_demo = tc[0][0]
    print(f"  demo: {ns} functions store a vtable; their most frequent callee {demo_name.get(tc[0][0])} "
          f"({tc[0][1]}), then {demo_name.get(tc[1][0])} ({tc[1][1]})")
    ns, tc = top_callee(ev_ours)
    dl_ours = tc[0][0]
    print(f"  ours: {ns} functions store a vtable; their most frequent callee 0x{tc[0][0]:x} "
          f"{our_name.get(tc[0][0])} ({tc[0][1]}; taken as operator delete by that analogy, not by a pair), "
          f"then 0x{tc[1][0]:x} ({tc[1][1]})")

    def owners(ev, variant, dl):
        own = collections.defaultdict(set)
        for f, (events, jals) in ev.items():
            if variant == "A":   # Goal 3 rule 4 as written: offset 0, within 8
                for _k, vt, off, _this, dist in events:
                    if off == 0 and dist <= WINDOW:
                        own[vt].add(f)
                continue
            if dl in jals:
                continue          # a destructor: it calls operator delete
            es = [e for e in events if (variant == "B" or e[3])]
            if es:
                own[es[-1][1]].add(f)
        return own

    variants = [("A", "rule 4 as written (sw to offset 0 within 8, exactly one function)"),
                ("B", "within 32, any offset, operator-delete callers dropped, the LAST vtable stored is the owner"),
                ("C", "B, counting only stores through the this register (a0 or a copy of it)")]
    one_ids = set(id(d) for d in one)
    ctor_counts = {}
    for key, text in variants:
        od, oo = owners(ev_demo, key, dl_demo), owners(ev_ours, key, dl_ours)
        for label, group in (("the 111", [(d, v) for d, v in resolved if id(d) in one_ids]),
                             (f"all {len(resolved)} resolved", resolved)):
            dc, oc = collections.Counter(), collections.Counter()
            for d, v in group:
                fs = od.get(d["start"], set())
                cls = d["mangled"][len("__vt__"):]
                if len(fs) == 1:
                    n = demo_name[next(iter(fs))]
                    k = OWN_CT if n.startswith("__ct__" + cls + "F") else (
                        "one: a __dt__" if "__dt__" in n else "one: something else")
                    dc[k] += 1
                    if show and k != OWN_CT:
                        print(f"      {key} {label}: {d['full']} -> {n}")
                else:
                    dc["several" if fs else "none"] += 1
                gs = oo.get(v["addr"], set())
                oc["exactly one" if len(gs) == 1 else ("several" if gs else "none")] += 1
                if len(gs) == 1 and next(iter(gs)) in o2name:   # the only retail truth: a Task 7 pair
                    pn = o2name[next(iter(gs))]
                    oc["exactly one is a Task 7 row: own __ct__" if pn.startswith("__ct__" + cls + "F")
                       else "exactly one is a Task 7 row: " + ("a __dt__" if "__dt__" in pn else "other")] += 1
            ctor_counts[(key, label)] = (dc, oc)
            print(f"  {key} {text}, {label}: demo {dict(dc)}; ours {dict(oc)}")
    dct_all = sum(1 for _s, _e, n in demo_fns if n.startswith("__ct__"))
    print(f"  (demo __ct__ symbols in all: {dct_all})")
    offs = collections.Counter(off for e, _j in ev_demo.values() for _k, _v, off, _t, _d in e)
    print(f"  demo vtable stores by offset (pattern within 32, any offset): {offs.most_common(5)} of {sum(offs.values())}")
    for label, group in (("the 111", [d for d in one]), ("all resolved", [d for d, _v in resolved])):
        n_ct = hit8 = hit32 = 0
        for d in group:
            cls = d["mangled"][len("__vt__"):]
            for f, _e, n in demo_fns:
                if not n.startswith("__ct__" + cls + "F"):
                    continue
                n_ct += 1
                es = ev_demo.get(f, ([], []))[0]
                hit8 += any(v == d["start"] and off == 0 and dist <= WINDOW for _k, v, off, _t, dist in es)
                hit32 += any(v == d["start"] for _k, v, _o, _t, _d in es)
        print(f"  demo __ct__ symbols of {label}: {n_ct}; containing rule 4's pattern for their own vtable "
              f"(offset 0, within 8) {hit8}; containing any store of it (within 32, any offset) {hit32}")

    # ---- T
    print("\n== T. what opens what (lever / classes / marginal NAMED slots: strict, start, whole, whole+shared)")
    for label, ncls, gains in table:
        print(f"  {label}: {ncls} / {gains[0]} / {gains[1]} / {gains[2]} / {gains[3]}")
    for key, _t in variants:
        dc, oc = ctor_counts[(key, f"all {len(resolved)} resolved")]
        print(f"  constructors, variant {key}: ours exactly one {oc['exactly one']} of {len(resolved)}; "
              f"demo precision {dc[OWN_CT]} own ctor of "
              f"{sum(v for k, v in dc.items() if k.startswith('one'))} unique")


def predict(i, chain, nd, nr, start_anchor):
    """Where the positional rule would put demo slot i given the other fixed points, or None."""
    before = [(a, b) for a, b in chain if a < i]
    after = [(a, b) for a, b in chain if a > i]
    if before:
        a, b = before[-1]
    elif start_anchor:
        a, b = -1, -1
    else:
        return None
    if after:
        c, d = after[0]
        if c - a != d - b:
            return None
    elif nd - a != nr - b:
        return None
    return b + (i - a)


def vt_stores_like(img, ranges, target):
    """Functions forming `target` with lui + addiu/ori (no store required)."""
    out = []
    hi_a = ((target + 0x8000) >> 16) & 0xFFFF
    hi_o = (target >> 16) & 0xFFFF
    lo = target & 0xFFFF
    for start, end in ranges:
        blob = img.rd(start, end - start)
        if not blob:
            continue
        ins = struct.unpack_from("<%dI" % (len(blob) // 4), blob, 0)
        luis = {}
        for i, x in enumerate(ins):
            op, rs, rt, imm = x >> 26, (x >> 21) & 31, (x >> 16) & 31, x & 0xFFFF
            if op == 0x0F:
                luis[rt] = (imm, i)
            elif op in (0x09, 0x0D) and imm == lo and rs in luis and i - luis[rs][1] <= WINDOW:
                if (op == 0x09 and luis[rs][0] == hi_a) or (op == 0x0D and luis[rs][0] == hi_o):
                    out.append(start)
                    break
    return out


if __name__ == "__main__":
    main()
