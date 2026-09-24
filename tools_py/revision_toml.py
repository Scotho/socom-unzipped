"""Carry a PS2Recomp configuration from one build's addresses onto another build's (Sprint 11 Task 19).

    python -m tools_py.revision_toml recomp/socom2.toml game/r0004/match.json \\
        --set-input ../game/overlays_r0004/socom2_game_r0004.elf \\
        --set-output ./output_r0004/ --set-ghidra-output socom2_ghidra_r0004.csv \\
        --out recomp/socom2_r0004.toml

`scripts/build_revision.sh` step 3 used to make a revision's config by copying r0001's and rewriting three
paths. Everything else in that file is an r0001 GUEST ADDRESS -- the stub selectors ps2_recomp binds by
start address, the instruction patches, the jump-table sites, the [mmio] annotations -- and in a build that
was relinked from changed source those addresses point at whatever the new build happens to have put there.
A config that silently keeps them is not conservative; it is confidently wrong. This tool translates them,
and says which ones it could not.

How each address is decided, in this order:

  loader region   an address in a region that is BYTE-IDENTICAL in both images does not move. Untouched,
                  and uncommented, so the diff shows only what really changed. (The regions come from the
                  two ELFs' PT_LOADs, or from --fixed.)
  function start  an address the match report places directly: the matcher's own `exact`, `hash+callees`
                  or `seed+delta` decision for that function.
  body interior   an address inside a matched function's body: the body moved as a block, so the address
                  moves by that function's delta. Marked `(weak)` when the function was placed by
                  `seed+delta`, because the seed pass proves the function's fingerprint and length at the
                  new address -- not that the bytes inside it kept their offsets.
  unresolved      the matcher could not place the address, or the function containing it, or no function
                  contains it at all. The r0001 number is KEPT AS IT WAS and listed in
                  `[revision.unresolved]`, so the config states what it does not know instead of dressing
                  a guess up as a fact.

Every rewritten line carries, in a comment, the r0001 address it came from and the method that moved it.

What this tool does NOT touch: `[performance] critical`, whose entries are names rather than addresses and
which `ps2xRecomp/src/lib/config_manager.cpp` never reads; and the right-hand side of an `[mmio]` pair,
which is a hardware register address and belongs to the machine, not to the build. The LEFT-hand side of
that pair is translated like everything else: `config_manager.cpp` reads it as `instAddr` and
`ps2_recompiler.cpp` looks the decoding instruction's own address up in it, so an `[mmio]` key is an
instruction address exactly like an instruction patch -- and an instruction address carried over from
another build annotates whatever this build happens to have put there.

THE DATA-REFERENCE PASS. A jump table's base is a rodata address, not a function start, so the function
matcher never has an opinion about it -- that is why all 24 of r0001's overlay bases came back unresolved.
But the base is not loose in the file: the function that switches through the table LOADS it, with a
`lui`/`lo` pair, a few instructions before the `jr`. So the base can be read out of the other build
instead of guessed, in three steps, and the same instrument places an instruction patch whose function
the matcher lost:

  the use site     the one `lui`+`lo` pair in the A image that forms this base, and the A function
                   holding it (the Ghidra table says which).
  the same site    in the B image, by the function match when there is one (the body moved as a block),
                   otherwise by ANCHORING: the window of instructions around the site, with every
                   address immediate masked out, is looked up in the B image; one hit places it. When a
                   window occurs N times in each image -- duplicated code -- the Nth A site takes the
                   Nth B site, which is the only order-preserving reading.
  the table        read at the base the B site's `lui`/`lo` form: every entry must be a word-aligned
                   address inside the B image and near that site. How many there are is the switch's
                   OWN `sltiu rX, rY, N` bound when it has one -- the code will not index past N -- and
                   otherwise the run of words that still read as targets. Either way a switch that grew
                   a case is written with the cases it has now, not with r0001's count.
  the leftovers    a table whose site cannot be anchored is tried once more against every `lui/lw/jr`
                   switch site in the B image, keeping only bases that fall between the two neighbouring
                   tables' resolved bases AND whose entries repeat r0001's pattern of equal targets.
                   One survivor is an answer; none or several is left unresolved and said so.

Nothing here reads r0001's number for a resolved table: base, entry count and every target come from the
B image. This needs BOTH images (`--elf-a`/`--elf-b`, or the paths the match report names); without them
the pass does not run and the bases stay unresolved, exactly as before. `--no-data-refs` turns it off.

THE [mmio] KEYS. A key is an instruction address in a function the matcher usually lost, so the same
anchor places it: the function match when there is one, the masked window otherwise, and nothing at all
when neither answers. What a key has that a patch does not is its own claim to check -- the hardware
register it says that instruction touches. Most of these accesses spell the register out, `lui rX,
%hi(reg)` a few instructions above and the key's own `lw`/`sw ..., %lo(reg)(rX)`; both of those
immediates are masked out of the window, so the register is INDEPENDENT evidence about where the window
landed. Where the A image spells it out, the address this tool writes must spell out the same register or
the key is left unresolved -- including when it was the function matcher, not the anchor, that placed it.
"""
import argparse
import bisect
import csv
import json
import os
import re
import sys
import tomllib
from collections import OrderedDict
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

Region = Tuple[int, int]
Body = Tuple[int, int, str]                       # (start, end, name) -- the Ghidra table's own shape
Match = Tuple[Optional[int], str]                 # (b address or None, how)

SECTION_RE = re.compile(r"^\s*\[\[?\s*([^\]\s]+)\s*\]\]?\s*$")
ARRAY_OPEN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*\[\s*(?:#.*)?$")
ARRAY_CLOSE_RE = re.compile(r"^\s*\]\s*,?\s*(?:#.*)?$")

SELECTOR_RE = re.compile(r'"[^"@]*@(0[xX][0-9A-Fa-f]+)"')
MMIO_KEY_RE = re.compile(r'^\s*"(0[xX][0-9A-Fa-f]+)"\s*=')
MMIO_REG_RE = re.compile(r'^\s*"0[xX][0-9A-Fa-f]+"\s*=\s*"?(0[xX][0-9A-Fa-f]+)"?')
TARGET_RE = re.compile(r'target\s*=\s*"(0[xX][0-9A-Fa-f]+)"')
PATCH_RE = re.compile(r'address\s*=\s*"(0[xX][0-9A-Fa-f]+)"')
TABLE_ADDR_RE = re.compile(r'^\s*address\s*=\s*"(0[xX][0-9A-Fa-f]+)"')
SETTABLE_RE = re.compile(r'^(\s*)(input|output|ghidra_output|names)(\s*=\s*)"([^"]*)"(.*)$')

SELECTOR_ARRAYS = ("stubs", "untracked_stubs", "skip")


class Decision(NamedTuple):
    """What the tool decided about one address, and why."""
    kind: str                     # "unchanged" | "translated" | "unresolved"
    addr: int                     # the address to write (the input itself when not translated)
    method: str                   # "loader" | "exact" | "hash+callees" | "seed+delta" | ""
    via: Optional[int]            # the function start whose delta moved it, when interior
    interior: bool
    weak: bool
    reason: str                   # why it is unresolved
    note: str = ""                # a confirmation to carry into the comment, beyond the method


class Site(NamedTuple):
    """One address found in the source config."""
    line_no: int
    role: str                     # "stubs", "mmio", "patches", "jump_tables", ...
    label: str                    # whatever the line already says it is (a name, or its own comment)
    a_addr: int
    decision: Decision


# ---- regions --------------------------------------------------------------------------------

def fixed_regions(a_segments: Sequence[Tuple[int, bytes]],
                  b_segments: Sequence[Tuple[int, bytes]]) -> List[Region]:
    """[lo, hi) for every loaded region that is byte-identical in both images.

    That is the honest test for "this does not move": the loader is unchanged by construction in this
    project, but nothing here assumes which segment the loader is. Same base and same bytes in both
    builds is the evidence; adjacent regions are merged so a two-segment loader reads as one range."""
    b_map = {int(v): bytes(d) for v, d in b_segments}
    out: List[Region] = []
    for vaddr, data in sorted((int(v), bytes(d)) for v, d in a_segments):
        if b_map.get(vaddr) == data:
            out.append((vaddr, vaddr + len(data)))
    merged: List[Region] = []
    for lo, hi in out:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def parse_region(text: str) -> Region:
    lo, _sep, hi = text.partition("-")
    if not _sep:
        raise ValueError("a region is 0xLO-0xHI, not %r" % text)
    return int(lo, 16), int(hi, 16)


# ---- the translation ------------------------------------------------------------------------

class Translator:
    """Every address question this tool can ask, answered from the match report and the A-side table."""

    def __init__(self, matches: Dict[int, Match], bodies: Iterable[Body], fixed: Sequence[Region]):
        self.matches = dict(matches)
        self.bodies = sorted(bodies)
        self.starts = [b[0] for b in self.bodies]
        self.span = max((e - s for s, e, _n in self.bodies), default=0)
        self.fixed = sorted(fixed)

    def is_fixed(self, addr: int) -> bool:
        return any(lo <= addr < hi for lo, hi in self.fixed)

    def containing(self, addr: int) -> List[Body]:
        """Every function body holding `addr`, innermost (greatest start) first.

        r0001's map has overlapping rows -- three weeks of forced entry points ending at "the next known
        function start" -- so this is a list, not a lookup, and the nearest preceding start is tried
        before any row that merely swallows it."""
        i = bisect.bisect_right(self.starts, addr) - 1
        out = []
        while i >= 0 and self.starts[i] >= addr - self.span:
            s, e, n = self.bodies[i]
            if s <= addr < e:
                out.append((s, e, n))
            i -= 1
        return out

    def translate(self, addr: int) -> Decision:
        if self.is_fixed(addr):
            return Decision("unchanged", addr, "loader", None, False, False, "")
        if addr in self.matches:
            b_addr, how = self.matches[addr]
            if b_addr is not None:
                return Decision("translated", b_addr, how, None, False, False, "")
            return Decision("unresolved", addr, "", None, False, False,
                            "the matcher could not place this function")
        holders = self.containing(addr)
        for start, _end, _name in holders:
            b_addr, how = self.matches.get(start, (None, ""))
            if b_addr is None:
                continue
            return Decision("translated", b_addr + (addr - start), how, start, True, how == "seed+delta", "")
        if holders:
            return Decision("unresolved", addr, "", holders[0][0], True, False,
                            "inside 0x%08x, which the matcher could not place" % holders[0][0])
        return Decision("unresolved", addr, "", None, False, False, "no function body holds it")


# ---- the data-reference pass ----------------------------------------------------------------

LUI_OP = 0x0F
JUMP_OPS = (0x02, 0x03)                              # j, jal: the target is an address
LOAD_STORE_OPS = frozenset((0x20, 0x21, 0x23, 0x24, 0x25, 0x27, 0x28, 0x29, 0x2B,
                            0x2F, 0x31, 0x35, 0x37, 0x39, 0x3D, 0x3F))
IMMEDIATE_OPS = frozenset((0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x18, 0x19))
STORE_OPS = frozenset((0x28, 0x29, 0x2A, 0x2B, 0x2E, 0x39, 0x3D, 0x3F))
LO_OPS = LOAD_STORE_OPS | frozenset((0x09, 0x0D))    # what can carry a lui's low half
# A jump table is READ, never written: a `sw` whose base register and immediate happen to add up to a
# table's address is a store into somebody's struct, not a use of that table. Leaving stores in made two
# of r0001's 24 bases look like they had two use sites apiece, which is the difference between "this
# pass cannot say" and an answer.
BASE_OPS = LO_OPS - STORE_OPS
SHAPES = ((10, 6), (6, 4), (4, 2))                   # the anchor's windows, widest first
SITE_SPAN = 0x20000                                  # how far a table's entries may sit from its site
GROW_SPREAD = 0x400                                  # how far past the known entries a grown table may reach
GROW_LIMIT = 64
MMIO_REACH = 12                                      # how far above an access its register's `lui` may sit
ACCESS_OPS = LOAD_STORE_OPS | STORE_OPS              # what an [mmio] key can be annotating
# What writes a register, for walking back from an access to the `lui` that set its base. Anything
# not listed reads as "writes nothing", which can only make the walk find a `lui` that is not really
# the source -- and that is caught, because the register it forms is then compared with the one the
# config annotates before anything is believed.
WRITES_RT_OPS = (IMMEDIATE_OPS | LOAD_STORE_OPS | frozenset((LUI_OP,))) - STORE_OPS


def normalize(word: int) -> int:
    """One instruction with its ADDRESSES removed, so two builds of the same code compare equal.

    A `lui`'s immediate is half an address; a `j`/`jal` target is an address; a load or an immediate
    op based on anything but `sp` or `zero` is usually reaching into data. All of those move between
    builds. Everything else -- opcodes, register numbers, shift amounts, branch displacements, stack
    offsets, small constants -- is the shape of the code, and that is what the anchor matches on."""
    op = word >> 26
    if op == LUI_OP:
        return word & 0xFFFF0000
    if op in JUMP_OPS:
        return word & 0xFC000000
    if op in LOAD_STORE_OPS or op in IMMEDIATE_OPS:
        if ((word >> 21) & 0x1F) in (29, 0):         # sp-relative, or a constant: not an address
            return word
        return word & 0xFFFF0000
    return word


def form_address(hi_word: int, lo_word: int) -> Optional[int]:
    """The address a `lui` and its low half form, with `addiu`/`lw`'s sign extension carried."""
    if (hi_word >> 26) != LUI_OP:
        return None
    op = lo_word >> 26
    if op not in LO_OPS:
        return None
    hi, lo = hi_word & 0xFFFF, lo_word & 0xFFFF
    if op == 0x0D:                                    # ori zero-extends
        return ((hi << 16) | lo) & 0xFFFFFFFF
    return ((hi << 16) + (lo - 0x10000 if lo >= 0x8000 else lo)) & 0xFFFFFFFF


def table_shape(values: Sequence[int]) -> List[int]:
    """Which entries are equal to which, and in what order -- a table's pattern with its addresses
    taken out. Two builds of one switch keep it even when the whole function moved."""
    seen: Dict[int, int] = {}
    return [seen.setdefault(v, len(seen)) for v in values]


class CodeImage:
    """An image's instruction words by guest address, and the searches this pass needs over them."""

    def __init__(self, segments: Sequence[Tuple[int, bytes]]):
        self.segs = []
        for vaddr, data in sorted((int(v), bytes(d)) for v, d in segments):
            self.segs.append((vaddr, [int.from_bytes(data[i:i + 4], "little")
                                      for i in range(0, len(data) - 3, 4)]))
        self._index: Dict[int, Dict[int, List[int]]] = {}
        self._switches: Optional[List[Tuple[int, int]]] = None

    def word(self, addr: int) -> Optional[int]:
        if addr % 4:
            return None
        for vaddr, words in self.segs:
            if vaddr <= addr < vaddr + 4 * len(words):
                return words[(addr - vaddr) // 4]
        return None

    def window(self, addr: int, before: int, after: int) -> Optional[List[int]]:
        """The instructions around `addr`, or None when the segment does not hold that many."""
        if addr % 4:
            return None
        for vaddr, words in self.segs:
            i = (addr - vaddr) // 4
            if vaddr <= addr < vaddr + 4 * len(words) and i >= before and i + after < len(words):
                return words[i - before:i + after + 1]
        return None

    def _keyed(self, before: int, after: int) -> Dict[int, List[int]]:
        """address -> window, hashed. The key itself is not kept: a hash bucket is re-checked."""
        span = before + 1 + after
        idx = self._index.get(span)
        if idx is None:
            idx = {}
            for vaddr, words in self.segs:
                shaped = [normalize(w) for w in words]
                for i in range(len(shaped) - span + 1):
                    idx.setdefault(hash(tuple(shaped[i:i + span])), []).append(vaddr + (i + before) * 4)
            self._index[span] = idx
        return idx

    def occurrences(self, key: Tuple[int, ...], before: int, after: int) -> List[int]:
        """Every address whose surrounding window has exactly this shape, in address order."""
        out = []
        for addr in self._keyed(before, after).get(hash(key), []):
            win = self.window(addr, before, after)
            if win and tuple(normalize(w) for w in win) == key:
                out.append(addr)
        return sorted(out)

    def lui_sites_for(self, base: int, reach: int = 16) -> List[Tuple[int, int]]:
        """(lui, lo) for every pair in this image that forms `base`."""
        lo = base & 0xFFFF
        hi = ((base >> 16) + (1 if lo >= 0x8000 else 0)) & 0xFFFF
        out = []
        for vaddr, words in self.segs:
            for i, w in enumerate(words):
                if (w >> 26) != LUI_OP or (w & 0xFFFF) != hi:
                    continue
                rt = (w >> 16) & 0x1F
                for j in range(i + 1, min(i + 1 + reach, len(words))):
                    w2 = words[j]
                    if (w2 >> 26) in BASE_OPS and ((w2 >> 21) & 0x1F) == rt \
                            and form_address(w, w2) == base:
                        out.append((vaddr + i * 4, vaddr + j * 4))
        return out

    def formed_register(self, addr: int, reach: int = MMIO_REACH) -> Optional[int]:
        """The address the load or store at `addr` forms, when a `lui` nearby sets its base register.

        An `[mmio]` key claims that the instruction AT this address touches THAT hardware register.
        Most of these accesses spell the register out in the code -- `lui at, %hi(reg)` a few
        instructions above, the key's own `lw`/`sw ..., %lo(reg)(at)` at the key itself -- so the
        claim is checkable against the image rather than merely carried over. None means "not
        checkable here": the base came from an argument, from a struct, or from further back than
        the reach. That is not the same as false, and nothing is refused on it."""
        w = self.word(addr)
        if w is None or (w >> 26) not in ACCESS_OPS:
            return None
        rs = (w >> 21) & 0x1F
        for k in range(1, reach + 1):
            prev = self.word(addr - 4 * k)
            if prev is None:
                return None
            op = prev >> 26
            if op == LUI_OP and ((prev >> 16) & 0x1F) == rs:
                return form_address(prev, w)
            if op in WRITES_RT_OPS and ((prev >> 16) & 0x1F) == rs:
                return None                               # something else set the base in between
            if op == 0 and ((prev >> 11) & 0x1F) == rs:
                return None
            if op == 0x03 and rs == 31:                   # jal, which writes ra
                return None
        return None

    def switch_sites(self) -> List[Tuple[int, int]]:
        """(lui, base) for every `lui … lw rX,imm(rY) ; jr rX` in the image: a switch, and its table."""
        if self._switches is None:
            out = []
            for vaddr, words in self.segs:
                for i, w in enumerate(words):
                    if (w >> 26) != LUI_OP:
                        continue
                    rt = (w >> 16) & 0x1F
                    for j in range(i + 1, min(i + 5, len(words) - 1)):
                        x = words[j]
                        if (x >> 26) != 0x23 or ((x >> 21) & 0x1F) != rt:
                            continue
                        dst = (x >> 16) & 0x1F
                        nxt = words[j + 1]
                        if (nxt & 0xFC1FFFFF) != 0x08 or ((nxt >> 21) & 0x1F) != dst:
                            continue                  # not `jr dst`
                        base = form_address(w, x)
                        if base is not None:
                            out.append((vaddr + i * 4, base))
                        break
            self._switches = out
        return self._switches

    def switch_bound(self, lui: int, back: int = 8) -> Optional[int]:
        """How many cases the switch just before `lui` admits -- its own `sltiu rX, rY, N`.

        This is the count as a FACT rather than as a guess: the code will not index past N, so the
        table has N entries whatever the words after it look like."""
        for k in range(1, back + 1):
            w = self.word(lui - 4 * k)
            if w is None:
                break
            if (w >> 26) == 0x0B:                         # sltiu
                n = w & 0xFFFF
                return n if 0 < n <= 4096 else None
        return None

    def read_table(self, base: int, count: int, near: int, grow: bool = True) -> Optional[List[int]]:
        """`count` entries at `base`, plus however many more this build's switch grew.

        Every entry must be a word-aligned address this image actually holds, and must sit near the
        switch that reads it -- a table of plausible targets, not a run of arbitrary words."""
        out: List[int] = []
        for i in range(count):
            w = self.word(base + 4 * i)
            if w is None or w % 4 or self.word(w) is None or abs(w - near) > SITE_SPAN:
                return None
            out.append(w)
        if not out:
            return None
        while grow and len(out) - count < GROW_LIMIT:
            w = self.word(base + 4 * len(out))
            if w is None or w % 4 or self.word(w) is None or abs(w - near) > SITE_SPAN:
                break
            if not (min(out) - GROW_SPREAD <= w <= max(out) + GROW_SPREAD):
                break
            out.append(w)
        return out


class Anchor:
    """Where an A-build address landed in the B build, read off the code around it."""

    def __init__(self, a: CodeImage, b: CodeImage, shapes: Sequence[Tuple[int, int]] = SHAPES):
        self.a, self.b, self.shapes = a, b, shapes

    def place(self, addr: int) -> Optional[Tuple[int, str]]:
        for before, after in self.shapes:
            win = self.a.window(addr, before, after)
            if win is None:
                continue
            key = tuple(normalize(w) for w in win)
            hits = self.b.occurrences(key, before, after)
            if len(hits) == 1:
                return hits[0], "window %d/%d" % (before, after)
            if len(hits) > 1:
                mine = self.a.occurrences(key, before, after)
                if len(mine) == len(hits) and addr in mine:
                    rank = mine.index(addr)
                    return hits[rank], "window %d/%d, copy %d of %d" % (before, after, rank + 1, len(hits))
        return None


def instruction_decision(anchor: Anchor, a_addr: int, d: Decision,
                         register: Optional[int] = None) -> Decision:
    """A patch's or an `[mmio]` key's decision, re-asked of the two images.

    Both are INSTRUCTION addresses, which is what the window anchor is for: the window's centre is the
    annotated instruction itself, so a hit is the same instruction, in the same company, in the other
    build. An `[mmio]` key carries one more thing -- the hardware register it says that instruction
    touches -- and where the A image spells that register out in the code, the address this tool is
    about to write has to spell out the same one, or it is not the same access and the tool does not
    know where that access went. That check runs on a key the MATCHER placed too: a function's delta is
    a claim about the whole body, and here is a place where the body itself can answer."""
    if d.kind == "unresolved":
        hit = anchor.place(a_addr)
        if hit is None:
            return d._replace(reason=d.reason + "; and no window of the code around it recurs in this "
                                                "build")
        d = Decision("translated", hit[0], "anchor %s" % hit[1], None, False, False, "")
    if d.kind != "translated" or register is None:
        return d
    want = anchor.a.formed_register(a_addr)
    if want != register:
        return d                    # this build does not spell the register out here: nothing to check
    got = anchor.b.formed_register(d.addr)
    if got == want:
        return d._replace(note="register 0x%08x confirmed" % register)
    return Decision("unresolved", a_addr, "", d.via, d.interior, False,
                    "0x%08x, where %s puts it, forms %s and not the 0x%08x this key annotates"
                    % (d.addr, d.method, "0x%08x" % got if got is not None else "no register", register))


class TableFix(NamedTuple):
    """One jump table, answered from the B image."""
    base: int
    entries: List[int]
    note: str


def counted_table(img: CodeImage, base: int, r0001_count: int, site: int) -> Tuple[Optional[List[int]], str]:
    """A table and how its length was settled: the switch's own bound first, the run of targets after.

    The bound is the better answer -- it is what the code will index -- but it is only taken when that
    many entries actually read as a table, so a `sltiu` that guards something else cannot lengthen a
    table by itself."""
    bound = img.switch_bound(site)
    if bound:
        read = img.read_table(base, bound, site, grow=False)
        if read is not None:
            return read, ", count from the switch's own sltiu bound"
    return img.read_table(base, r0001_count, site), ", count from the run of targets"


def source_tables(doc: dict) -> List[Tuple[int, List[int]]]:
    """(base, targets) for every `[[jump_tables.table]]` in the source config, in file order."""
    out = []
    for t in ((doc.get("jump_tables") or {}).get("table") or []):
        addr = t.get("address")
        if not isinstance(addr, str):
            continue
        out.append((int(addr, 16), [int(e["target"], 16) for e in (t.get("entries") or [])
                                    if isinstance(e.get("target"), str)]))
    return out


def resolve_tables(tables: Sequence[Tuple[int, List[int]]], tr: Translator, anchor: Anchor,
                   ) -> Tuple[Dict[int, TableFix], Dict[int, str]]:
    """Every overlay jump table, placed by its use site; the leftovers by order and pattern."""
    fixes: Dict[int, TableFix] = {}
    why: Dict[int, str] = {}
    entries_of = OrderedDict((base, ents) for base, ents in tables)
    for base, ents in entries_of.items():
        if base in fixes or base in why or tr.is_fixed(base) or not ents:
            continue
        sites = anchor.a.lui_sites_for(base)
        if len(sites) != 1:
            why[base] = ("%d lui/lo pairs in r0001 form this base, so which code reads it is not "
                         "a fact this pass can state" % len(sites))
            continue
        lui_a, lo_a = sites[0]
        holder = tr.containing(lui_a)
        named = holder[0][2] if holder else "no named function"
        placed = None
        moved = tr.translate(lui_a)
        if moved.kind == "translated":
            w = anchor.b.word(moved.addr)
            mine = anchor.a.word(lui_a)
            if w is not None and (w >> 26) == LUI_OP and ((w >> 16) & 0x1F) == ((mine >> 16) & 0x1F):
                placed = (moved.addr, "the %s match of %s" % (moved.method, named))
        if placed is None:
            placed = anchor.place(lui_a)
        if placed is None:
            why[base] = ("its use site 0x%08x, in %s, is in neither a matched function nor a window "
                         "this build repeats" % (lui_a, named))
            continue
        lui_b, how = placed
        new = form_address(anchor.b.word(lui_b) or 0, anchor.b.word(lui_b + (lo_a - lui_a)) or 0)
        read, counted = counted_table(anchor.b, new, len(ents), lui_b) if new is not None else (None, "")
        if read is None:
            why[base] = ("its use site placed at 0x%08x forms 0x%s, which does not read as a table of "
                         "%d targets" % (lui_b, "%08x" % new if new is not None else "?", len(ents)))
            continue
        fixes[base] = TableFix(new, read, "r0001 0x%08x, %d entries%s%s, use site 0x%08x -> 0x%08x in %s (%s)"
                               % (base, len(read),
                                  " (%d in r0001)" % len(ents) if len(read) != len(ents) else "",
                                  counted, lui_a, lui_b, named, how))

    order = list(entries_of)
    for i, base in enumerate(order):
        if base not in why:
            continue
        prev = next((fixes[b].base for b in reversed(order[:i]) if b in fixes), None)
        nxt = next((fixes[b].base for b in order[i + 1:] if b in fixes), None)
        if prev is None or nxt is None or not (prev < nxt):
            continue
        want = table_shape(entries_of[base])
        found = []
        for site, cand in anchor.b.switch_sites():
            if not (prev < cand < nxt) or any(c == cand for _s, c in found):
                continue
            read = anchor.b.read_table(cand, len(want), site)
            if read and table_shape(read[:len(want)]) == want:
                found.append((site, cand))
        if len(found) != 1:
            continue
        site, cand = found[0]
        read, counted = counted_table(anchor.b, cand, len(want), site)
        holder = tr.containing(anchor.a.lui_sites_for(base)[0][0])
        fixes[base] = TableFix(cand, read,
                               "r0001 0x%08x, %d entries%s%s, base between 0x%08x and 0x%08x with r0001's "
                               "own pattern of equal targets, read by 0x%08x (%s)"
                               % (base, len(read), " (%d in r0001)" % len(want) if len(read) != len(want) else "",
                                  counted, prev, nxt, site, holder[0][2] if holder else "no named function"))
        del why[base]
    return fixes, why


# ---- reading the inputs ---------------------------------------------------------------------

def load_matches(doc: dict) -> Dict[int, Match]:
    out: Dict[int, Match] = {}
    for a_addr, m in (doc.get("matches") or {}).items():
        b = m.get("b")
        out[int(a_addr, 16)] = (None if b in (None, "") else int(b, 16), m.get("how") or "")
    return out


def load_bodies(csv_path: str) -> List[Body]:
    out: List[Body] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append((int(row["Start"], 16), int(row["End"], 16), row.get("Name") or ""))
    out.sort()
    return out


# ---- rewriting the file ---------------------------------------------------------------------

def format_like(original: str, value: int) -> str:
    """`value` written the way `original` was -- same 0x prefix, same width, same case."""
    digits = original[2:]
    body = "%x" % value
    if any(c in "ABCDEF" for c in digits):
        body = body.upper()
    if len(body) < len(digits):
        body = "0" * (len(digits) - len(body)) + body
    return original[:2] + body


def split_comment(line: str) -> Tuple[str, str]:
    """(code, comment) -- the first `#` outside a double-quoted string starts the comment."""
    in_str = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\" and in_str:
            i += 2
            continue
        if c == '"':
            in_str = not in_str
        elif c == "#" and not in_str:
            return line[:i], line[i:]
        i += 1
    return line, ""


def add_note(line: str, note: str) -> str:
    """Append `note` to the line's comment, keeping whatever the line already said."""
    code, comment = split_comment(line.rstrip("\n"))
    if comment:
        return "%s%s  (%s)" % (code, comment.rstrip(), note)
    return "%s  # %s" % (code.rstrip(), note)


def note_for(a_addr: int, d: Decision) -> str:
    if d.kind == "unresolved":
        return "UNRESOLVED: r0001 0x%08x kept -- %s" % (a_addr, d.reason)
    tail = ", %s" % d.note if d.note else ""
    if d.interior:
        return "r0001 0x%08x, body+0x%x of 0x%08x %s%s%s" % (
            a_addr, a_addr - (d.via or 0), d.via or 0, d.method,
            " (weak)" if d.weak else "", tail)
    return "r0001 0x%08x %s%s" % (a_addr, d.method, tail)


def _hits(line: str, section: str, array: str) -> List[Tuple[re.Match, str]]:
    """The (match, role) pairs on this line whose group 1 is a guest address."""
    if array in SELECTOR_ARRAYS:
        return [(m, array) for m in SELECTOR_RE.finditer(line)]
    if array == "entries" and section.endswith("jump_tables.table"):
        return [(m, "jump_table_entries") for m in TARGET_RE.finditer(line)]
    if array == "instructions" and section.endswith("patches"):
        return [(m, "patches") for m in PATCH_RE.finditer(line)]
    if array:
        return []                                       # [performance] critical and anything else: names
    if section == "mmio":
        m = MMIO_KEY_RE.match(line)                     # the KEY only; the value is a hardware register
        return [(m, "mmio")] if m else []
    if section.endswith("jump_tables.table"):
        m = TABLE_ADDR_RE.match(line)
        return [(m, "jump_tables")] if m else []
    return []


def _label(line: str, role: str) -> str:
    """Whatever the line already says this address is -- the toml's own words, for the unresolved table."""
    if role in SELECTOR_ARRAYS:
        m = re.search(r'"([^"@]*)@0[xX][0-9A-Fa-f]+"', line)
        if m:
            return m.group(1)
    _code, comment = split_comment(line)
    return comment.lstrip("# ").strip()


def grown_entry(template: str, index: int, target: int) -> str:
    """One more entry line, written the way this table's own lines are written."""
    line = re.sub(r"(index\s*=\s*)\d+", lambda m: "%s%d" % (m.group(1), index), template, count=1)
    line = TARGET_RE.sub(lambda m: m.group(0).replace(m.group(1), format_like(m.group(1), target)),
                         split_comment(line)[0].rstrip(), count=1)
    return line + "  # grown: this build's switch has a case r0001 did not"


def rewrite(text: str, tr: Translator, sets: Optional[Dict[str, str]] = None,
            tables: Optional[Dict[int, TableFix]] = None, table_why: Optional[Dict[int, str]] = None,
            anchor: Optional[Anchor] = None) -> Tuple[List[str], List[Site]]:
    """The source config with every overlay address translated. Returns (lines, one Site per address)."""
    sets = sets or {}
    tables, table_why = tables or {}, table_why or {}
    lines = text.splitlines()
    out: List[str] = []
    sites: List[Site] = []
    section, array = "", ""
    fix: Optional[TableFix] = None
    entry_i, entry_template = 0, ""
    for n, line in enumerate(lines, 1):
        if array:
            if ARRAY_CLOSE_RE.match(line):
                if array == "entries" and fix is not None and entry_template:
                    while entry_i < len(fix.entries):
                        out.append(grown_entry(entry_template, entry_i, fix.entries[entry_i]))
                        sites.append(Site(n, "jump_table_entries", "grown", fix.entries[entry_i],
                                          Decision("translated", fix.entries[entry_i], "table (grown)",
                                                   None, False, False, "")))
                        entry_i += 1
                array = ""
                out.append(line)
                continue
            if array == "entries" and fix is not None and entry_i < len(fix.entries):
                m = TARGET_RE.search(line)
                if m:
                    a_addr = int(m.group(1), 16)
                    new = fix.entries[entry_i]
                    out.append(line[:m.start(1)] + format_like(m.group(1), new) + line[m.end(1):])
                    sites.append(Site(n, "jump_table_entries", "", a_addr,
                                      Decision("translated", new, "table", None, False, False, "")))
                    entry_i, entry_template = entry_i + 1, line
                    continue
        else:
            if section.endswith("jump_tables.table"):
                m = TABLE_ADDR_RE.match(line)
                if m:
                    a_addr = int(m.group(1), 16)
                    fix, entry_i, entry_template = tables.get(a_addr), 0, ""
                    if fix is not None:
                        d = Decision("translated", fix.base, "data-ref", None, False, False, "")
                        sites.append(Site(n, "jump_tables", _label(line, "jump_tables"), a_addr, d))
                        out.append(add_note(line[:m.start(1)] + format_like(m.group(1), fix.base)
                                            + line[m.end(1):], fix.note))
                        continue
                    if a_addr in table_why:
                        d = Decision("unresolved", a_addr, "", None, False, False, table_why[a_addr])
                        sites.append(Site(n, "jump_tables", _label(line, "jump_tables"), a_addr, d))
                        out.append(add_note(line, note_for(a_addr, d)))
                        continue
            m = SECTION_RE.match(line)
            if m:
                section, array = m.group(1), ""
                out.append(line)
                continue
            m = ARRAY_OPEN_RE.match(line)
            if m:
                array = m.group(1)
                out.append(line)
                continue
            m = SETTABLE_RE.match(line)
            if m and section == "general" and m.group(2) in sets:
                out.append("%s%s%s\"%s\"%s" % (m.group(1), m.group(2), m.group(3), sets[m.group(2)], m.group(5)))
                continue

        hits = _hits(line, section, array)
        if not hits:
            out.append(line)
            continue
        label = _label(line, hits[0][1])
        notes, new_line, shift = [], line, 0
        for m, role in hits:
            a_addr = int(m.group(1), 16)
            d = tr.translate(a_addr)
            if anchor is not None and d.kind != "unchanged" and role in ("patches", "mmio"):
                # A patch and an [mmio] key are both INSTRUCTION addresses, so the code around them is
                # evidence even when the matcher lost the function -- and an [mmio] key's hardware
                # register is evidence about wherever that code turns out to be.
                register = None
                if role == "mmio":
                    rm = MMIO_REG_RE.match(line)
                    register = int(rm.group(1), 16) if rm else None
                d = instruction_decision(anchor, a_addr, d, register)
            sites.append(Site(n, role, label, a_addr, d))
            if d.kind == "unchanged":
                continue
            notes.append(note_for(a_addr, d))
            if d.kind == "translated":
                lo, hi = m.start(1) + shift, m.end(1) + shift
                replacement = format_like(m.group(1), d.addr)
                new_line = new_line[:lo] + replacement + new_line[hi:]
                shift += len(replacement) - (hi - lo)
        for note in notes:
            new_line = add_note(new_line, note)
        out.append(new_line)
    return out, sites


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_relative(path: str) -> str:
    """A provenance path as it goes into the generated config: relative to the repository root, forward
    slashes, no drive letter.

    `scripts/build_revision.sh` hands this tool absolute paths (it resolves every input before step 1), and
    `recomp/socom2_<rev>.toml` is TRACKED and rewritten by step 3 on every build. Writing the caller's
    absolute paths into it meant the file said `C:/projects/socom_pc/recomp/socom2.toml` -- true on one
    machine, and a modification in `git status` for everyone else who builds that revision. The provenance
    is about files in this repository, so it names them the way the repository does. A path outside the
    repository is left as it came, forward-slashed: it is still true, and there is nothing to relativise it
    against.
    """
    absolute = os.path.abspath(path)
    try:
        inside = os.path.commonpath([absolute, _ROOT]) == _ROOT
    except ValueError:      # different drives on Windows
        inside = False
    if inside:
        return os.path.relpath(absolute, _ROOT).replace("\\", "/")
    return path.replace("\\", "/")


def revision_block(sites: Sequence[Site], source: str, match: str,
                   tables: Optional[Dict[int, TableFix]] = None,
                   table_why: Optional[Dict[int, str]] = None) -> List[str]:
    """The `[revision]` table: the counts, and every address this config still carries from r0001."""
    source, match = repo_relative(source), repo_relative(match)
    kinds = {"translated": 0, "unchanged": 0, "unresolved": 0}
    interior = weak = anchored = confirmed = 0
    unresolved: "OrderedDict[int, List[str]]" = OrderedDict()
    for s in sites:
        kinds[s.decision.kind] = kinds.get(s.decision.kind, 0) + 1
        if s.decision.kind == "translated" and s.decision.interior:
            interior += 1
            weak += 1 if s.decision.weak else 0
        if s.decision.kind == "translated" and s.decision.method.startswith("anchor"):
            anchored += 1
        if s.decision.kind == "translated" and s.decision.note.startswith("register"):
            confirmed += 1
        if s.decision.kind == "unresolved":
            what = "%s%s -- %s" % (s.role, (" " + s.label) if s.label else "", s.decision.reason)
            unresolved.setdefault(s.a_addr, [])
            if what not in unresolved[s.a_addr]:
                unresolved[s.a_addr].append(what)
    lines = [
        "",
        "# ---- what this revision's config knows, and what it does not -------------------------------",
        "# Written by tools_py/revision_toml.py from %s and %s." % (source, match),
        "# Every address above that moved carries, in its comment, the r0001 address it came from and the",
        "# method that moved it:",
        "#   exact / hash+callees / seed+delta   the matcher's own decision for that function;",
        "#   body+0xN of 0xSTART                 the address is INSIDE that function and rode its delta;",
        "#   (weak)                              that body match was seed+delta -- the seed pass proved",
        "#                                       the function's fingerprint and length at the new address,",
        "#                                       not that the bytes inside it kept their offsets.",
        "#   use site / window / base between     the data-reference pass: the address was READ OUT of",
        "#                                       this build's image, at the code that loads it. A table",
        "#                                       whose line says so has its base, its entry count and",
        "#                                       every one of its targets from this build -- not one",
        "#                                       number in it is r0001's.",
        "#   anchor window N/M                   an INSTRUCTION address -- a patch, an [mmio] key --",
        "#                                       placed by the shape of the code around it, with every",
        "#                                       address immediate masked out.",
        "#   register 0xR confirmed              and the [mmio] key's own claim still holds there: the",
        "#                                       code at the new address forms that same hardware",
        "#                                       register. Where it does not, the key is UNRESOLVED.",
        "# Addresses in a region that is byte-identical in both images do not move: untouched, uncommented.",
        "[revision]",
        'source = "%s"' % source,
        'match = "%s"' % match,
        "translated = %d" % kinds.get("translated", 0),
        "translated_interior = %d" % interior,
        "weak = %d" % weak,
        "anchored = %d" % anchored,
        "mmio_registers_confirmed = %d" % confirmed,
        "unchanged = %d" % kinds.get("unchanged", 0),
        "unresolved_count = %d" % len(unresolved),
        "jump_tables_resolved = %d" % len(tables or {}),
        "jump_tables_unresolved = %d" % len(table_why or {}),
        "",
        "# The addresses this config still carries from r0001, because the matcher could not place them.",
        "# They are r0001 numbers in another build's config: wrong until someone resolves them by hand.",
        "# Nothing below is a guess -- that is the point of listing them.",
        "[revision.unresolved]",
    ]
    for addr, what in unresolved.items():
        lines.append('"0x%08x" = "%s"' % (addr, "; ".join(what).replace("\\", "/").replace('"', "'")))
    return lines


def report(sites: Sequence[Site]) -> List[str]:
    """Role x method, the counts a reader of the run wants."""
    roles: "OrderedDict[str, OrderedDict[str, int]]" = OrderedDict()
    for s in sites:
        key = s.decision.method if s.decision.kind != "unresolved" else "unresolved"
        if s.decision.kind == "translated" and s.decision.interior:
            key += " (body)" + (" weak" if s.decision.weak else "")
        roles.setdefault(s.role, OrderedDict()).setdefault(key, 0)
        roles[s.role][key] += 1
    out = []
    for role, counts in roles.items():
        total = sum(counts.values())
        moved = sum(v for k, v in counts.items() if k not in ("loader", "unresolved"))
        out.append("%-13s %4d addresses: %d translated, %d unchanged (loader), %d unresolved   [%s]"
                   % (role, total, moved, counts.get("loader", 0), counts.get("unresolved", 0),
                      ", ".join("%s=%d" % (k, v) for k, v in sorted(counts.items()))))
    return out


# ---- the CLI --------------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source_toml", help="the config to carry over (recomp/socom2.toml)")
    ap.add_argument("match_json", help="tools_py.address_matcher --out for this revision")
    ap.add_argument("--out", help="where to write the revision's config")
    ap.add_argument("--dry-run", action="store_true", help="print the translation table and write nothing")
    ap.add_argument("--csv-a", help="the A build's function table (default: the match report's own a.csv)")
    ap.add_argument("--elf-a", help="the A image (default: the match report's own a.elf)")
    ap.add_argument("--elf-b", help="the B image (default: the match report's own b.elf)")
    ap.add_argument("--fixed", action="append", default=[], metavar="0xLO-0xHI",
                    help="a region that does not move, instead of deriving it from the two ELFs")
    ap.add_argument("--no-data-refs", action="store_true",
                    help="do not read jump-table bases and stray patches out of the two images")
    ap.add_argument("--set-input", help="[general] input")
    ap.add_argument("--set-output", help="[general] output")
    ap.add_argument("--set-ghidra-output", help="[general] ghidra_output")
    ap.add_argument("--set-names", help="[general] names (the display-name sidecar)")
    args = ap.parse_args(argv)

    for path in (args.source_toml, args.match_json):
        if not os.path.exists(path):
            print("NO-DATA: missing", path)
            return 2
    with open(args.match_json, encoding="utf-8") as fh:
        doc = json.load(fh)

    csv_a = args.csv_a or (doc.get("a") or {}).get("csv")
    if not csv_a or not os.path.exists(csv_a):
        print("NO-DATA: no A-side function table (--csv-a; the report names %r)" % csv_a)
        return 2

    elf_a = args.elf_a or (doc.get("a") or {}).get("elf")
    elf_b = args.elf_b or (doc.get("b") or {}).get("elf")
    have_both = bool(elf_a and elf_b and os.path.exists(elf_a) and os.path.exists(elf_b))
    segs_a = segs_b = None
    if have_both:
        from tools_py.address_matcher import load_segments
        with open(elf_a, "rb") as fh:
            segs_a = load_segments(fh.read())
        with open(elf_b, "rb") as fh:
            segs_b = load_segments(fh.read())

    if args.fixed:
        try:
            fixed = [parse_region(f) for f in args.fixed]
        except ValueError as e:
            print("bad --fixed:", e)
            return 2
    else:
        if not have_both:
            print("NO-DATA: the regions that do not move need both images (--elf-a/--elf-b, or --fixed); "
                  "the report names %r and %r" % (elf_a, elf_b))
            return 2
        fixed = fixed_regions(segs_a, segs_b)
        print("# regions byte-identical in both images (they do not move): %s"
              % ", ".join("0x%08x-0x%08x" % r for r in fixed))

    tr = Translator(load_matches(doc), load_bodies(csv_a), fixed)
    with open(args.source_toml, encoding="utf-8") as fh:
        text = fh.read()

    anchor, fixes, why = None, {}, {}
    if have_both and not args.no_data_refs:
        anchor = Anchor(CodeImage(segs_a), CodeImage(segs_b))
        fixes, why = resolve_tables(source_tables(tomllib.loads(text)), tr, anchor)
        print("# jump tables read out of the B image: %d placed, %d left unresolved" % (len(fixes), len(why)))
    elif not have_both:
        print("# no data-reference pass: it needs both images (--elf-a/--elf-b); jump-table bases and "
              "patches in unmatched functions stay unresolved")

    sets = {k: v for k, v in (("input", args.set_input), ("output", args.set_output),
                              ("ghidra_output", args.set_ghidra_output),
                              ("names", args.set_names)) if v is not None}
    lines, sites = rewrite(text, tr, sets, fixes, why, anchor)

    if args.dry_run:
        print("# the translation table: role, r0001 -> this revision, method")
        for s in sorted(sites, key=lambda s: (s.a_addr, s.role)):
            d = s.decision
            if d.kind == "unchanged":
                continue
            where = ("0x%08x -> 0x%08x" % (s.a_addr, d.addr)) if d.kind == "translated" \
                else ("0x%08x    (kept)" % s.a_addr)
            print("  %-13s %-26s %s" % (s.role, where, note_for(s.a_addr, d)))
    for line in report(sites):
        print(line)

    if args.dry_run:
        print("dry run: %s not written" % (args.out or "<no --out>"))
        return 0
    if not args.out:
        print("nothing written: pass --out <path> (or --dry-run)")
        return 2
    lines = lines + revision_block(sites, args.source_toml, args.match_json, fixes, why)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
