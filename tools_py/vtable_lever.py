"""Sprint 12 Task 4 (Task 7c): the `vtable-slot` lever -- name a virtual function by its slot.

Task 7 (`ghidra_symbol_match`) names what is byte-identical between the SOCOM 1 demo and our SOCOM II
r0001 image; 7b (`symbol_levers`) names by link order between those anchors. Both need a body that
survived. A C++ virtual function has a second identity that survives an edit: its SLOT, the index
of its pointer in its class's vtable. Metrowerks 2.4.1 lays a vtable out as

    [RTTI object*, 0 | -this offset, slot 0*, slot 1*, ...]      a 0 slot word is a pure virtual
    RTTI object = [name string*, base list*];  base list = [base RTTI*, offset]... 0

and the name string is the QUALIFIED class name (`zdb::CNode`, `std::ctype<char>`), present in both
builds (docs/research/51 section 0). So a demo class's own RTTI string finds its retail vtable with no
body evidence at all, and the demo's slot i names our slot i wherever the two vtables line up.

The rule is `VTABLE_RULE`, the spec's Goal 3 as amended by S12-R16 (research/51's measurement):

  1. `resolve_classes`: the key is the demo's own RTTI string (from the demo's `__RTTI__` object, or
     the mangling where the demo's RTTI word is 0); `"\\0name\\0"` in retail -> the aligned words
     pointing at it (RTTI objects) -> the aligned words pointing at those, kept only when they are a
     vtable HEAD by the layout: word 1 zero (primary) or a negative offset (secondary), then csv
     function starts (>= 2, or 1 inside the span the >= 2 vtables occupy). A word inside a derived
     class's base list also points at an RTTI object; the layout drops it. Exactly one primary per
     class, else refused; the demo's one secondary pairs with retail's one secondary by the header.
  2. `align_slots`: fixed points are the vtable START plus every slot whose demo target and our
     target are a PROVED Task 7 pair (a strictly increasing chain). A run between two fixed points,
     or after the last, is named by position only when it has the same length on both sides; so an
     equal-count vtable with no body-matched fixed point is named whole.
  3. `propose`: the hurdles (a refusal count each): one name per row and one row per name; our csv
     row still a placeholder (`name_provenance.is_placeholder`); a target already in Task 7's or 7b's
     file is skipped and its agreement counted; a target that is a Task 7 pair under ANOTHER name is
     refused and printed as a finding; a shared body (one of our addresses in >= 2 retail vtables)
     only when >= 2 vtables name it and name it alike; body >= 64 B and size ratio >= 0.50
     (`symbol_levers.MIN_BODY`/`SIZE_RATIO`); a unique legal identifier (`c_identifier`), against
     this file, Task 7's and 7b's `Proposed` and the csv's own non-placeholder names.
  4. `holdout`: leave-one-out over the fixed points (research/45 section 3's shape, research/51's
     method): drop one, re-derive it by position from the rest, count right / wrong / not reached.

Constructors are NOT proposed (S12-R16 withdrew Goal 3 rule 4: as written it picks destructors).
research/51's variant C is ~150 lines of MIPS scanning with its own open recall question; it is not
repeated here -- `python tools_py/research/symbols/vtable_coverage.py` section 7 prints it.

    python -m tools_py.vtable_lever game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf \\
        recomp/socom2_ghidra.csv game/demo_symbol_matches.json \\
        --out game/demo_symbol_renames_7c.csv [--holdout] [--data-rows]

Reads only; writes the one proposals file. Names, addresses and counts are printed, never bytes.
docs/research/60-vtable-slots.md holds the real run.
"""
import argparse
import collections
import csv
import json
import os
import re
import struct
import textwrap
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from tools_py import address_matcher as am
from tools_py.elf_symbols import read_elf
from tools_py.ghidra_symbol_match import c_identifier
from tools_py.name_provenance import is_placeholder
from tools_py.symbol_levers import MIN_BODY, SIZE_RATIO, anchor_composition, anchors_from_details, \
    proved_anchors

HOW = "vtable-slot"
SCORE = 0.75
READINGS = ("strict", "start", "whole")
# One per demo class; `res.buckets` also carries "secondary paired" / "secondary refused ..." counts.
CLASS_BUCKETS = ("one", "primary + secondary", "several primaries", "secondary only",
                 "absent: no string", "absent: string, no vtable by the layout")
NEG_OFFSET = 0xFFFF0000            # a secondary header's this-offset: a small negative word
REGION_MARGIN = 0x100              # a 1-slot vtable counts only this near the >= 2-slot ones
REGION_GAP = 0x10000               # >= 2-slot vtables closer than this form one span
NAME_RE = re.compile(r"^[A-Za-z_@][A-Za-z0-9_@:<>, *&\-.\[\]()]*$")

VTABLE_RULE = (
    "vtable-slot: a demo __vt__ class resolves through its OWN qualified RTTI string (the demo's "
    "__RTTI__ object's name, or the mangling when that word is 0) to retail's \\0name\\0 string, the "
    "RTTI objects pointing at it, and the words pointing at those that are a vtable head by the "
    "layout -- word 1 zero (primary) or a negative this-offset (secondary), then csv function starts "
    "(>= 2, or 1 inside the span the >= 2 vtables occupy); base-list words fall out. Exactly one "
    "retail primary per class, else refused; the demo's one secondary pairs with retail's one "
    "secondary by the header word. Slots stop at the first word that is not a csv function start "
    "(a 0 word is a pure virtual). Fixed points: the vtable START and every slot whose demo and "
    "retail targets are a PROVED (non-prefix) Task 7 pair, as a strictly increasing chain. A run "
    "between fixed points or after the last is named by position only when it has equal length on "
    "both sides, so an equal-count vtable with no body-matched fixed point is named whole. Hurdles: "
    "one name per row and one row per name; our csv row still a placeholder; a row in Task 7's or "
    "7b's file skipped (its agreement counted); a Task 7 pair under another name refused; a shared "
    "body (one of our rows in >= 2 retail vtables) only when >= 2 vtables name it, alike; body >= %d "
    "bytes and size ratio >= %.2f (symbol_levers' cuts); a unique legal C identifier (c_identifier) "
    "against this file, Task 7's and 7b's Proposed and the csv's own names. Constructors are not "
    "proposed (S12-R16). Score %.2f. docs/research/51-vtable-coverage.md, "
    "docs/research/60-vtable-slots.md."
) % (MIN_BODY, SIZE_RATIO, SCORE)

PROPOSAL_COLUMNS_7C = ["Address", "Current", "Proposed", "Mangled", "Score", "How", "Size",
                       "Class", "Slot", "FixedPoints", "DemoAddr", "DemoSize", "OurSize", "Ratio"]


# ---- images ----------------------------------------------------------------------------------

class Image:
    """Word and string access to a segment list by guest address; `fn` is the function-start set."""

    def __init__(self, segments, fn_starts: Iterable[int]):
        self.segs = sorted((int(v), bytes(d)) for v, d in segments)
        self.fn = set(fn_starts)
        self.words = [(va, struct.unpack_from("<%dI" % (len(d) // 4), d, 0)) for va, d in self.segs]

    def word(self, a: int) -> Optional[int]:
        for va, data in self.segs:
            if va <= a and a + 4 <= va + len(data):
                return struct.unpack_from("<I", data, a - va)[0]
        return None

    def byte_before(self, a: int) -> Optional[int]:
        for va, data in self.segs:
            if va < a <= va + len(data):
                return data[a - va - 1]
        return None

    def cstr(self, a: int, limit: int = 300) -> Optional[str]:
        for va, data in self.segs:
            if va <= a < va + len(data):
                end = data.find(b"\0", a - va, a - va + limit)
                return data[a - va:end].decode("latin1") if end >= 0 else None
        return None

    def find_all(self, needle: bytes) -> List[int]:
        out = []
        for va, data in self.segs:
            i = data.find(needle)
            while i >= 0:
                out.append(va + i)
                i = data.find(needle, i + 1)
        return out

    def words_pointing(self, target: int) -> List[int]:
        return [a for a in self.find_all(struct.pack("<I", target)) if a % 4 == 0]

    def slots(self, vt: int, limit: Optional[int] = None) -> Tuple[int, ...]:
        """The consecutive function-start words after the two-word header at `vt` (to `limit`)."""
        out = []
        a = vt + 8
        while limit is None or a < limit:
            x = self.word(a)
            if x is None or x not in self.fn:
                break
            out.append(x)
            a += 4
        return tuple(out)


class Vtable(NamedTuple):
    addr: int
    rtti: int
    name: str
    off: int
    slots: Tuple[int, ...]


def layout_census(img: Image, min_slots: int = 1) -> List[Vtable]:
    """Every vtable head in `img` by the layout alone: [RTTI*, 0 | -off, fn, ...], the RTTI object's
    first word pointing at a NUL-preceded class-name string (research/51 section 1)."""
    out = []
    for va, words in img.words:
        n = len(words)
        for i in range(n - 2):
            r = words[i]
            if r == 0 or r % 4:
                continue
            off = words[i + 1]
            if off != 0 and off < NEG_OFFSET:
                continue
            k = 0
            while i + 2 + k < n and words[i + 2 + k] in img.fn:
                k += 1
            if k < min_slots:
                continue
            s = img.word(r)
            if not s:
                continue
            name = img.cstr(s)
            if not name or not NAME_RE.match(name) or img.byte_before(s) != 0:
                continue
            out.append(Vtable(va + 4 * i, r, name, off, tuple(words[i + 2:i + 2 + k])))
    return out


def vtable_regions(census: Sequence[Vtable]) -> List[Tuple[int, int]]:
    """The spans the >= 2-slot vtables occupy (clusters closer than REGION_GAP), +/- REGION_MARGIN."""
    spans: List[List[int]] = []
    for a in sorted(v.addr for v in census if len(v.slots) >= 2):
        if spans and a - spans[-1][1] < REGION_GAP:
            spans[-1][1] = a
        else:
            spans.append([a, a])
    return [(lo - REGION_MARGIN, hi + REGION_MARGIN) for lo, hi in spans]


def in_regions(a: int, regions) -> bool:
    return any(lo <= a < hi for lo, hi in regions)


def _comps(mangled: str) -> List[str]:
    rest = mangled[len("__vt__"):]
    q = re.match(r"Q(\d)", rest)
    pos, out = (q.end() if q else 0), []
    while True:
        m = re.match(r"(\d+)", rest[pos:])
        if not m:
            return out
        pos += m.end()
        out.append(rest[pos:pos + int(m.group(1))])
        pos += int(m.group(1))


class DemoClass(NamedTuple):
    mangled: str                   # the __vt__ symbol
    start: int
    name: str                      # the qualified RTTI string
    parts: Tuple[Tuple[int, Tuple[int, ...]], ...]   # (header offset word, slots) per header


def demo_classes(demo_img: Image, objects) -> List[DemoClass]:
    """Every demo `__vt__` OBJECT, its qualified name, and its primary + secondary parts.

    A part is a header inside the object -- word 0, or the class's own RTTI word followed by a
    negative offset -- and its slots, bounded by the object's end."""
    out = []
    for s, e, n in objects:
        if not n.startswith("__vt__"):
            continue
        r = demo_img.word(s)
        qual = demo_img.cstr(demo_img.word(r)) if r and demo_img.word(r) else None
        words = [demo_img.word(a) for a in range(s, e, 4)]
        parts = []
        for i in range(len(words) - 1):
            if i == 0 or (r and words[i] == r and words[i + 1] >= NEG_OFFSET):
                parts.append((words[i + 1], demo_img.slots(s + 4 * i, limit=e)))
        out.append(DemoClass(n, s, qual or "::".join(_comps(n)), tuple(parts)))
    return out


class ResolvedVtable(NamedTuple):
    cls: str
    part: str                      # "primary" / "secondary"
    demo_vt: int
    demo_slots: Tuple[int, ...]
    our_vt: int
    our_slots: Tuple[int, ...]
    mangled: str


class Resolution(NamedTuple):
    vtables: List[ResolvedVtable]
    buckets: collections.Counter   # per demo class
    pointing: Dict[str, int]       # class -> aligned words pointing at its retail RTTI objects
    retail: List[Vtable]           # every retail vtable by the layout (>= 2, or 1 in a region)
    regions: List[Tuple[int, int]]
    classes: Dict[str, str]        # class -> its bucket


def resolve_classes(demo, ours, our_csv_starts) -> Resolution:
    """Rule 1. `demo` has `.segments`, `.functions`, `.objects` (an `elf_symbols.Elf`); `ours` is our
    segment list; `our_csv_starts` our csv's function starts.

    Buckets, one per demo class: `one` (one retail primary, no secondary), `primary + secondary`
    (the primary kept; the secondary paired only when both sides hold exactly one), `several
    primaries` (refused), `secondary only` (refused), `absent: no string`, `absent: string, no
    vtable by the layout` (refused)."""
    dimg = Image(demo.segments, [s for s, _e, _n in demo.functions])
    oimg = Image(ours.segments if hasattr(ours, "segments") else ours, our_csv_starts)
    census = layout_census(oimg, 1)
    regions = vtable_regions(census)
    retail = [v for v in census if len(v.slots) >= 2 or in_regions(v.addr, regions)]
    head = {v.addr: v for v in retail}

    buckets: collections.Counter = collections.Counter()
    pointing: Dict[str, int] = {}
    classes: Dict[str, str] = {}
    out: List[ResolvedVtable] = []
    for dc in demo_classes(dimg, demo.objects):
        hits = oimg.find_all(b"\0" + dc.name.encode("latin1") + b"\0")
        rttis = sorted({x for h in hits for x in oimg.words_pointing(h + 1)})
        words = sorted({x for r in rttis for x in oimg.words_pointing(r)})
        pointing[dc.name] = len(words)
        vts = [head[w] for w in words if w in head]
        prim = [v for v in vts if v.off == 0]
        sec = [v for v in vts if v.off != 0]
        if not hits:
            bucket = "absent: no string"
        elif not vts:
            bucket = "absent: string, no vtable by the layout"
        elif len(prim) > 1:
            bucket = "several primaries"
        elif not prim:
            bucket = "secondary only"
        elif not sec:
            bucket = "one"
        else:
            bucket = "primary + secondary"
        buckets[bucket] += 1
        classes[dc.name] = bucket
        if bucket not in ("one", "primary + secondary"):
            continue
        out.append(ResolvedVtable(dc.name, "primary", dc.start, dc.parts[0][1], prim[0].addr,
                                  prim[0].slots, dc.mangled))
        if sec:
            dsec = dc.parts[1:]
            if len(dsec) == 1 and len(sec) == 1:
                out.append(ResolvedVtable(dc.name, "secondary", dc.start, dsec[0][1], sec[0].addr,
                                          sec[0].slots, dc.mangled))
                buckets["secondary paired"] += 1
            else:
                buckets["secondary refused (not one on each side)"] += 1
    return Resolution(out, buckets, pointing, retail, regions, classes)


# ---- rule 2: alignment ----------------------------------------------------------------------

class SlotPair(NamedTuple):
    di: int
    rj: int
    demo: int                      # the demo slot's target
    ours: int                      # our slot's target
    fixed: str                     # the fixed points the run rests on: "start..1:1", "1:1..end"


class Alignment(NamedTuple):
    chain: List[Tuple[int, int]]
    conflicts: int
    slots: List[SlotPair]
    equal_slots: int
    unequal_slots: int


def fixed_points(demo_slots, our_slots, pairs) -> Tuple[List[Tuple[int, int]], int]:
    """(chain, conflicts): (demo index, our index) of every slot whose demo target is paired to a
    target occurring once among our slots, kept as a strictly increasing chain in demo order."""
    chain, conflicts = [], 0
    for i, d in enumerate(demo_slots):
        o = pairs.get(d)
        if o is None:
            continue
        js = [j for j, r in enumerate(our_slots) if r == o]
        if len(js) != 1:
            continue
        if chain and js[0] <= chain[-1][1]:
            conflicts += 1
            continue
        chain.append((i, js[0]))
    return chain, conflicts


def _label(fp) -> str:
    return "start" if fp == (-1, -1) else "%d:%d" % fp


def align_slots(demo_slots, our_slots, pairs, reading: str = "whole") -> Alignment:
    """Rule 2. `pairs` is {demo address: our address} over PROVED Task 7 pairs.

    `reading` is research/51's: "strict" (between fixed points and after the last), "start" (the
    vtable start is a fixed point when there is at least one other), "whole" (the start is always a
    fixed point, so an equal-count vtable with no body-matched fixed point is named whole) -- the
    reading that ships."""
    if reading not in READINGS:
        raise ValueError("reading is one of %s, not %r" % (READINGS, reading))
    chain, conflicts = fixed_points(demo_slots, our_slots, pairs)
    anchors = list(chain)
    if reading == "whole" or (reading == "start" and chain):
        anchors = [(-1, -1)] + anchors
    nd, nr = len(demo_slots), len(our_slots)
    bounds = list(zip(anchors, anchors[1:] + [(nd, nr)]))
    out, eq, uneq = [], 0, 0
    for (a, b), (c, d) in bounds:
        ld, lr = c - a - 1, d - b - 1
        if ld != lr:
            uneq += max(ld, 0)
            continue
        eq += ld
        hi = "end" if (c, d) == (nd, nr) else _label((c, d))
        for k in range(ld):
            out.append(SlotPair(a + 1 + k, b + 1 + k, demo_slots[a + 1 + k], our_slots[b + 1 + k],
                                "%s..%s" % (_label((a, b)), hi)))
    return Alignment(chain, conflicts, out, eq, uneq)


def predict(i: int, chain, nd: int, nr: int, start_anchor: bool) -> Optional[int]:
    """Where rule 2 puts demo slot i given the other fixed points `chain`, or None."""
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


def drop_held(pairs, held) -> Dict[int, int]:
    """`pairs` without any pair whose demo or our address is held (S12-R20: a held address is no
    anchor for any lever)."""
    return {d: o for d, o in pairs.items() if d not in held and o not in held}


def read_holds(path: str) -> set:
    """The addresses of `recomp/socom2_name_holds.csv` (Address, Proposed, Reason, Source); an
    absent file is no holds."""
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as fh:
        return {int(r["Address"], 16) for r in csv.DictReader(fh)}


def holdout(vtables: Sequence[ResolvedVtable], pairs, reading: str = "whole",
            detail: Optional[list] = None, held=frozenset()) -> collections.Counter:
    """Rule 2's error rate on known answers: leave each fixed point out, re-derive it by position
    from the others, compare. {fixed points, reached, right, wrong, not reached}."""
    pairs = drop_held(pairs, held)
    got: collections.Counter = collections.Counter()
    for vt in vtables:
        chain, _c = fixed_points(vt.demo_slots, vt.our_slots, pairs)
        for x, (i, j) in enumerate(chain):
            rest = chain[:x] + chain[x + 1:]
            p = predict(i, rest, len(vt.demo_slots), len(vt.our_slots), reading != "strict")
            got["fixed points"] += 1
            if p is None:
                got["not reached"] += 1
                continue
            got["reached"] += 1
            got["right" if p == j else "wrong"] += 1
            if detail is not None:
                detail.append((vt.cls, vt.part, i, j, p))
    for k in ("fixed points", "reached", "right", "wrong", "not reached"):
        got[k] += 0
    return got


# ---- rule 3: the hurdles ---------------------------------------------------------------------

class Proposals(NamedTuple):
    rows: List[Dict]
    refused: collections.Counter
    checks: collections.Counter
    findings: List[str]
    census: collections.Counter
    per_class: collections.Counter
    notes: List[str]               # refusals worth reading by name (not disagreements)


def propose(res: Resolution, demo_functions, our_rows, pairs, reading: str = "whole",
            shared_ok: bool = True, named_files: Optional[Dict[int, str]] = None,
            task7: Optional[Dict[int, Tuple[str, str]]] = None, taken: Iterable[str] = (),
            held=frozenset()) -> Proposals:
    """Rules 2 and 3 over every resolved vtable: the rows of `game/demo_symbol_renames_7c.csv`.

    `pairs` {demo addr: our addr} (proved Task 7 pairs: the fixed points); `named_files` {our addr:
    mangled name} for every row of Task 7's and 7b's proposals files; `task7` {our addr: (demo name,
    how)} for every Task 7 pair; `taken` the identifiers already spent elsewhere; `held` the
    addresses of the holds file: a pair touching one is no fixed point, a held target is refused."""
    named_files, task7 = named_files or {}, task7 or {}
    pairs = drop_held(pairs, held)
    demo_name = {s: n for s, _e, n in demo_functions}
    demo_size = {s: e - s for s, e, _n in demo_functions}
    our_name = {s: n for s, _e, n in our_rows}
    our_size = {s: e - s for s, e, _n in our_rows}
    shared_retail = collections.Counter(t for v in res.retail for t in set(v.slots))

    census: collections.Counter = collections.Counter()
    votes: Dict[int, List[Tuple[ResolvedVtable, SlotPair]]] = collections.defaultdict(list)
    rows_of_name: Dict[str, set] = collections.defaultdict(set)
    for vt in res.vtables:
        a = align_slots(vt.demo_slots, vt.our_slots, pairs, reading)
        census["vtables"] += 1
        census["demo slots"] += len(vt.demo_slots)
        census["retail slots"] += len(vt.our_slots)
        census["fixed points"] += len(a.chain)
        census["conflicting fixed points"] += a.conflicts
        census["vtables with a fixed point"] += bool(a.chain)
        census["slots in equal runs"] += a.equal_slots
        census["slots in unequal runs"] += a.unequal_slots
        census["named whole (no fixed point)"] += (not a.chain and bool(a.slots))
        for sp in a.slots:
            votes[sp.ours].append((vt, sp))
            rows_of_name[demo_name[sp.demo]].add(sp.ours)
    census["distinct rows proposed"] = len(votes)

    refused: collections.Counter = collections.Counter()
    checks: collections.Counter = collections.Counter()
    findings: List[str] = []
    notes: List[str] = []
    kept = []
    for r in sorted(votes):
        vs = votes[r]
        if r in held:
            refused["held"] += 1
            continue
        names = sorted({demo_name[sp.demo] for _vt, sp in vs})
        vts = {(vt.cls, vt.part) for vt, _sp in vs}
        if len(names) > 1:
            refused["shared body named differently" if len(vts) > 1 else "two names, one row"] += 1
            notes.append("0x%08x refused, named differently: %s" % (r, "; ".join(
                "%s slot %d -> %s" % (vt.cls, sp.rj, demo_name[sp.demo]) for vt, sp in vs)))
            continue
        name = names[0]
        if len(rows_of_name[name]) > 1:
            refused["demo name on two of our rows"] += 1
            continue
        if not is_placeholder(our_name.get(r, "")):
            refused["our row already named (csv)"] += 1
            continue
        if r in named_files:
            refused["already named (Task 7 / 7b file)"] += 1
            same = named_files[r] == name
            checks["Task 7 / 7b file: %s" % ("same name" if same else "OTHER name")] += 1
            if not same:
                findings.append("0x%08x: the file names it %s, slot %s of %s names it %s"
                                % (r, named_files[r], vs[0][1].rj, vs[0][0].cls, name))
            continue
        if r in task7:
            t7name, t7how = task7[r]
            if t7name != name:
                refused["contradicts a Task 7 pair"] += 1
                findings.append("0x%08x: Task 7 (%s) pairs it with %s, slot %s of %s names it %s"
                                % (r, t7how, t7name, vs[0][1].rj, vs[0][0].cls, name))
                continue
            confirms = "prefix" if t7how.startswith("prefix") else "proved"
            checks["Task 7 pair not in the files, same name (%s)" % confirms] += 1
        else:
            confirms = None
        if shared_retail[r] > 1 and not (shared_ok and len(vts) >= 2):
            refused["shared body, one vtable names it"] += 1
            continue
        d = vs[0][1].demo
        ds, os_ = demo_size.get(d, 0), our_size.get(r, 0)
        why = None
        if min(ds, os_) < MIN_BODY:
            why = "body under %d bytes" % MIN_BODY
        elif min(ds, os_) / max(ds, os_) < SIZE_RATIO:
            why = "size ratio under %.2f" % SIZE_RATIO
        if why:
            refused[why] += 1
            if confirms:
                notes.append("0x%08x %s: agrees with Task 7's %s pair, refused (%s; demo %d B, ours %d B)"
                             % (r, name, task7[r][1], why, ds, os_))
            continue
        kept.append((r, name, d, ds, os_, vs, confirms))

    spelling = collections.Counter(c_identifier(name) for _r, name, *_x in kept)
    spelling.update(set(taken))
    rows: List[Dict] = []
    per_class: collections.Counter = collections.Counter()
    for r, name, d, ds, os_, vs, confirms in kept:
        ident = c_identifier(name)
        if spelling[ident] > 1:
            refused["identifier already spent or collides"] += 1
            continue
        if shared_retail[r] > 1:
            checks["written: a shared body (>= 2 vtables, one name)"] += 1
        if confirms:
            checks["written: confirms a Task 7 %s pair (S12-R3)" % confirms] += 1
        vs = sorted(vs, key=lambda v: (v[0].cls, v[0].part, v[1].rj))
        for vt, _sp in vs:
            per_class[vt.cls] += 1
        rows.append({"Address": "0x%08x" % r, "Current": our_name.get(r, ""), "Proposed": ident,
                     "Mangled": name, "Score": "%.2f" % SCORE, "How": HOW, "Size": ds,
                     "Class": "|".join(vt.cls + (" (secondary)" if vt.part == "secondary" else "")
                                       for vt, _sp in vs),
                     "Slot": "|".join(str(sp.rj) for _vt, sp in vs),
                     "FixedPoints": "|".join(sp.fixed for _vt, sp in vs),
                     "DemoAddr": "0x%08x" % d, "DemoSize": ds, "OurSize": os_,
                     "Ratio": "%.2f" % (min(ds, os_) / max(ds, os_))})
    return Proposals(rows, refused, checks, findings, census, per_class, notes)


def write_proposals_7c(path: str, rows: Sequence[Dict], header: Sequence[str]) -> None:
    """The proposals file: `VTABLE_RULE` then `header` in `#` lines, then the columns.

    The rule is written by this function, not by its caller, so no file of this shape can omit it.
    A missing directory is a ValueError (the CLI makes it one NO-DATA line)."""
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise ValueError("cannot write %s: %s is not a directory" % (path, directory))
    lines = textwrap.wrap(VTABLE_RULE, 100) + [""]
    for h in header:
        lines += textwrap.wrap(h, 100) if h else [""]
    with open(path, "w", newline="") as fh:
        for line in lines:
            fh.write("# %s\n" % line if line else "#\n")
        w = csv.DictWriter(fh, fieldnames=PROPOSAL_COLUMNS_7C)
        w.writeheader()
        for row in rows:
            w.writerow(row)


# ---- the CLI ----------------------------------------------------------------------------------

def _read_proposals(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(line for line in fh if not line.startswith("#")))


def load_pairs(matches_path: str, demo_functions):
    """(details, task7) from Task 7's match JSON.

    `details` is `ghidra_symbol_match.match`'s out-parameter shape, {(name, our addr): {how, size,
    demo_addr}}, rebuilt from the JSON by the demo NAME -- so a name on two demo addresses (a C
    `static` in two translation units) cannot be placed and is left out, counted in `dropped`.
    `task7` is {our addr: (demo name, how)} over every pair."""
    by_name = collections.defaultdict(list)
    for s, _e, n in demo_functions:
        by_name[n].append(s)
    details, task7, dropped = {}, {}, 0
    for p in json.load(open(matches_path))["pairs"]:
        a = int(p["addr"], 16)
        task7[a] = (p["name"], p["how"])
        if len(by_name[p["name"]]) != 1:
            dropped += 1
            continue
        details[(p["name"], a)] = {"how": p["how"], "size": p["size"],
                                   "demo_addr": by_name[p["name"]][0]}
    return details, task7, dropped


def data_rows(our_rows, res: Resolution):
    """[(start, name, size, vtable class or '')] -- csv rows starting inside a vtable span (data the
    csv calls code, research/51 section 1); the class is given when the row starts on a vtable's own
    words (header or slots)."""
    owner = {}
    for v in res.retail:
        for a in range(v.addr, v.addr + 8 + 4 * len(v.slots), 4):
            owner[a] = v.name + (" (secondary)" if v.off else "")
    return [(s, n, e - s, owner.get(s, "")) for s, e, n in our_rows if in_regions(s, res.regions)]


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Task 7c: name virtual functions by their vtable slot")
    ap.add_argument("demo_elf")
    ap.add_argument("our_elf")
    ap.add_argument("our_csv")
    ap.add_argument("matches", help="Task 7's match JSON (game/demo_symbol_matches.json)")
    ap.add_argument("--out", help="CSV: the vtable-slot proposals (never applied here)")
    ap.add_argument("--renames", default="game/demo_symbol_renames.csv",
                    help="Task 7's proposals file: its rows are 'already named'")
    ap.add_argument("--renames-7b", dest="renames_7b", default="game/demo_symbol_renames_7b.csv",
                    help="Task 7b's proposals file: its rows are 'already named'")
    ap.add_argument("--holdout", action="store_true",
                    help="print every held-out fixed point and where the rule re-derives it")
    ap.add_argument("--data-rows", dest="data_rows", action="store_true",
                    help="list the csv rows that start inside vtable data")
    ap.add_argument("--holds", default="recomp/socom2_name_holds.csv",
                    help="the holds file (S12-R20): held addresses are no fixed point and no target")
    ap.add_argument("--top", type=int, default=20, help="classes by slots named (default 20)")
    ap.add_argument("--primary-only", dest="primary_only", action="store_true",
                    help="refuse every secondary vtable (name primaries only); prints what that costs")
    args = ap.parse_args(list(argv) if argv is not None else None)

    missing = [p for p in (args.demo_elf, args.our_elf, args.our_csv, args.matches)
               if not os.path.exists(p)]
    if missing:
        for p in missing:
            print("NO-DATA: missing %s" % p)
        print("NO-DATA: the demo ELF, the disc image and Task 7's outputs are git-ignored; "
              "see docs/research/44-demo-symbols.md section 1")
        return 2

    demo = read_elf(args.demo_elf)
    our_segments = read_elf(args.our_elf).segments
    our_rows = am.load_functions(args.our_csv)
    res = resolve_classes(demo, our_segments, {s for s, _e, _n in our_rows})
    if args.primary_only:
        print("--primary-only: %d secondary vtables refused"
              % sum(1 for v in res.vtables if v.part == "secondary"))
        res = res._replace(vtables=[v for v in res.vtables if v.part == "primary"])
    details, task7, dropped = load_pairs(args.matches, demo.functions)
    anchors = anchors_from_details(details)
    proved = proved_anchors(anchors)
    pairs = {d: o for d, o, _h in anchors if d in proved}
    held = read_holds(args.holds)
    n_before = len(pairs)
    pairs = drop_held(pairs, held)
    comp = anchor_composition(anchors)
    anchor_note = ("fixed-point anchors: %d proved Task 7 pairs of %d in the JSON (%s; %d dropped: "
                   "the demo name sits on several demo addresses; %d held by %s, %d dropped)"
                   % (len(pairs), len(task7), ", ".join("%s %d" % kv for kv in sorted(comp.items())),
                      dropped, len(held), args.holds, n_before - len(pairs)))

    t7_rows, t7b_rows = _read_proposals(args.renames), _read_proposals(args.renames_7b)
    named_files = {int(r["Address"], 16): r["Mangled"] for r in t7_rows + t7b_rows}
    taken = [r["Proposed"] for r in t7_rows + t7b_rows]
    taken += [n for _s, _e, n in our_rows if not is_placeholder(n)]

    b = res.buckets
    print("demo __vt__ classes %d: %s" % (sum(b[k] for k in CLASS_BUCKETS),
                                          ", ".join("%s %d" % kv for kv in sorted(b.items()))))
    print("  classes resolved %d; vtables %d (%d primary, %d secondary); retail vtables by the "
          "layout %d over %d class names"
          % (b["one"] + b["primary + secondary"], len(res.vtables),
             sum(1 for v in res.vtables if v.part == "primary"),
             sum(1 for v in res.vtables if v.part == "secondary"),
             len(res.retail), len({v.name for v in res.retail})))
    print("  " + anchor_note)
    print("  Task 7 / 7b files: %d + %d rows (%d identifiers spent with the csv's own names)"
          % (len(t7_rows), len(t7b_rows), len(set(taken))))

    print("\nthe readings (research/51 section 6), rows named after every hurdle:")
    for reading, shared in (("strict", False), ("start", False), ("whole", False), ("whole", True)):
        p = propose(res, demo.functions, our_rows, pairs, reading, shared, named_files, task7, taken,
                    held)
        h = holdout(res.vtables, pairs, reading, held=held)
        print("  %-6s%-8s proposed %3d named %3d  holdout %d fixed points: reached %d right %d "
              "wrong %d" % (reading, " +shared" if shared else "", p.census["distinct rows proposed"],
                            len(p.rows), h["fixed points"], h["reached"], h["right"], h["wrong"]))

    out = propose(res, demo.functions, our_rows, pairs, "whole", True, named_files, task7, taken,
                  held)
    detail: list = []
    ho = holdout(res.vtables, pairs, "whole", detail, held)
    print("\nshipped reading: whole + shared")
    print("  " + ", ".join("%s %d" % kv for kv in sorted(out.census.items())))
    print("  refused: " + ", ".join("%s %d" % kv for kv in sorted(out.refused.items())))
    print("  checks:  " + ", ".join("%s %d" % kv for kv in sorted(out.checks.items())))
    for f in out.findings:
        print("  FINDING: " + f)
    for row in out.rows:
        a = int(row["Address"], 16)
        if a in task7:
            print("  CONFIRMS Task 7 %s pair: %s %s (slot %s of %s; fixed points %s)"
                  % (task7[a][1], row["Address"], row["Mangled"], row["Slot"], row["Class"],
                     row["FixedPoints"]))
    for n in out.notes:
        print("  NOTE: " + n)
    shape = collections.Counter()
    for row in out.rows:
        for f in row["FixedPoints"].split("|"):
            shape["whole vtable, no fixed point" if f == "start..end" else
                  ("before the first fixed point" if f.startswith("start..") else
                   "after a fixed point")] += 1
    print("  PROPOSED %d slots (rows); what they rest on, per naming vtable: %s"
          % (len(out.rows), ", ".join("%s %d" % kv for kv in sorted(shape.items()))))
    print("  holdout (leave-one-out over the fixed points): %d fixed points, reached %d, right %d, "
          "wrong %d, not reached %d" % (ho["fixed points"], ho["reached"], ho["right"], ho["wrong"],
                                        ho["not reached"]))
    if args.holdout:
        for cls, part, i, j, p in detail:
            print("    %s %s: demo slot %d -> ours %d, re-derived %d %s"
                  % (cls, part, i, j, p, "right" if p == j else "WRONG"))
    print("\ntop %d classes by slots named:" % args.top)
    for cls, n in sorted(out.per_class.items(), key=lambda kv: (-kv[1], kv[0]))[:args.top]:
        print("  %3d  %s" % (n, cls))
    print("constructors: not proposed (S12-R16); research/51's variant C is printed by "
          "tools_py/research/symbols/vtable_coverage.py section 7, not repeated here")

    rows_in_data = data_rows(our_rows, res)
    print("\ncsv rows starting inside vtable data: %d (%d on a vtable's own header or slot words)"
          % (len(rows_in_data), sum(1 for x in rows_in_data if x[3])))
    if args.data_rows:
        for s, n, size, owner in rows_in_data:
            print("  0x%08x  %-14s %6d  %s" % (s, n, size, owner or "-"))

    if args.out:
        header = [
            "%s -- Sprint 12 Task 4 (7c) proposals, pass %s. PROPOSALS ONLY: nothing is applied "
            "here; Task 3's applier writes recomp/socom2_names.csv." % (args.out, HOW),
            "Names come from the SOCOM 1 demo's .symtab; addresses are OURS (r0001). Size is the "
            "demo body (Task 7's column); DemoSize/OurSize/Ratio carry both. Class/Slot/FixedPoints "
            "are |-joined when >= 2 vtables name one shared body alike.",
            "",
            "Reading: 'whole + shared' (research/51 section 6, the fourth row; S12-R16): the vtable "
            "start is a fixed point, equal-count vtables are named whole, a shared body is admitted "
            "when >= 2 vtables name it alike. %s"
            % ("Secondaries refused (--primary-only)." if args.primary_only else
               "Secondaries pair by the header word when each side holds exactly one."),
            anchor_note + ".",
            "Holdout (leave-one-out over the fixed points, research/45 section 3's shape): %d fixed "
            "points, %d re-derived, %d right, %d wrong, %d not reached. Like 7b's, it is an upper "
            "bound: a fixed point is a body Task 7 could match."
            % (ho["fixed points"], ho["reached"], ho["right"], ho["wrong"], ho["not reached"]),
            "Census: classes resolved %d, vtables %d, rows proposed before the hurdles %d, written %d; "
            "refused %s; checks %s."
            % (b["one"] + b["primary + secondary"], len(res.vtables),
               out.census["distinct rows proposed"], len(out.rows),
               ", ".join("%s %d" % kv for kv in sorted(out.refused.items())) or "none",
               ", ".join("%s %d" % kv for kv in sorted(out.checks.items())) or "none"),
        ]
        try:
            write_proposals_7c(args.out, out.rows, header)
        except (ValueError, OSError) as exc:
            print("NO-DATA: %s" % exc)
            return 2
        print("\nwrote %s: %d rows (proposals only)" % (args.out, len(out.rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
