"""Sprint 11 Task 10 (milestone R): match one game build's functions onto another's.

Every guest address the runtime knows -- the override sites in game_overrides_socom2.cpp, the overlay
constructor tables, the version string -- is an r0001 address. A second revision (r0004) is the same game
relinked: the code is byte-for-byte the same routine at a different address, with the address immediates
moved. This fills `socom2_addresses.h`'s second column without a second reverse-engineering pass.

    python -m tools_py.address_matcher <elf_a> <csv_a> <elf_b> <csv_b> \\
        --seed 0x408c58=0x435618 --out matches.json

`<csv>` is the Ghidra function table (Name,Start,End,Size -- recomp/socom2_ghidra.csv, see
tools_py/fix_ghidra_csv.py); `<elf>` is the image those addresses live in. The run prints the resolution
rate and writes every decision, with how it was reached, to --out.

How a function is placed, in order, each pass taking only what it can prove:

  exact         its fingerprint (tools_py/fingerprint.py) occurs once in each image.
  hash+callees  its fingerprint occurs more than once, but of the candidates that share it exactly one
                agrees with it on the functions it calls -- the `jal` targets that earlier passes already
                placed. The call target is zeroed out of the hash, so this is independent evidence.
  relinked-body the same instruction stream relinked. The fingerprint keeps load/store displacements on
                purpose -- a struct offset is part of the code -- but the EE compiler reaches a GLOBAL as
                `lui $at, hi` + `lw rt, lo($at)`, so for a global that displacement is half an address
                and it moves with the link. This pass masks those away too (and a `$gp`-relative one),
                hashes the masked stream, and takes a body whose masked hash is unique on both sides at
                the same length. Masked equality means every differing word is the same opcode with the
                same register fields differing only in an immediate -- i.e. every difference is a
                relocation. Where several candidates share the hash the tie is broken by the callees the
                earlier passes already placed, then by a string anchor (a `lui`/low-half pair forming
                the address of a string, compared by the string's own bytes); a tie neither breaks is
                left unresolved. The mask is a COARSENING of the fingerprint, so this pass can never
                contradict `exact` -- it only sees what `exact` could not.
  seed+delta    a seed pair (an address known in both builds by other means: a string, a static, a
                symbol) gives a constant offset, and this function's address plus that offset is a
                function start in the other image WHOSE FINGERPRINT AND LENGTH STILL AGREE. One seed
                places a whole relinked segment; a wrong one places nothing, which is the point.
  unresolved    none of the above -- including a row whose bytes are not in the image at all. The table
                keeps the row so the count is honest.
"""
import argparse
import csv
import json
import os
import struct
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from tools_py.fingerprint import fingerprint

Func = Tuple[int, int, str]                       # (start, end, name), the CSV's own shape
Segment = Tuple[int, bytes]                       # (vaddr, bytes), load_segments()'s shape
Match = Tuple[Optional[int], str]                 # (b_addr or None, how)

HOWS = ("exact", "hash+callees", "relinked-body", "seed+delta", "unresolved")
JAL = 0x03

# ---- the relink mask -----------------------------------------------------------------------
#
# fingerprint.py already zeroes what obviously carries an address: a `lui` half, an `addiu`/`ori`
# immediate, a `j`/`jal` target, a branch displacement. What it deliberately keeps is a load or store
# displacement, because for a struct field that is the shape of the code. For a GLOBAL it is not: the
# compiler emits `lui $at, hi(g)` + `lw rt, lo(g)($at)`, and the low half of the address lives in the
# load. This mask zeroes exactly those -- a memory access based on a register a `lui` (or a `lui` pair)
# put an address in, or based on `$gp` -- and nothing else.
LUI_OP = 0x0F
JUMP_OPS = (0x02, 0x03)
LO_OPS = (0x08, 0x09, 0x0D)               # addi, addiu, ori -- the low half of an address
IMM_RT_OPS = (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F)
# Loads that write a GENERAL register, and loads that write a coprocessor one. The distinction is not
# pedantry: `lwc1 $f1, x($at)` has rt = 1, and reading that as "$at was written" throws away the `lui`
# that is still live -- which is exactly how a float store to a global (`swc1 $f2, lo($at)`) kept an
# address half in its displacement and cost two real matches.
GPR_LOAD_OPS = frozenset((0x1A, 0x1B, 0x1E, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x30, 0x37))
COP_LOAD_OPS = frozenset((0x31, 0x33, 0x35, 0x36))          # lwc1, pref, ldc1, lqc2
LOAD_OPS = GPR_LOAD_OPS | COP_LOAD_OPS
STORE_OPS = frozenset((0x1F, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x38, 0x39, 0x3A, 0x3D,
                       0x3E, 0x3F))
MEM_OPS = LOAD_OPS | STORE_OPS
COP_OPS = (0x10, 0x11, 0x12)                                # COP0 / COP1 / COP2
COP_TO_GPR_RS = (0x00, 0x01, 0x02)                          # mfc, qmfc2, cfc -- these do write rt
GP_REG = 28
NO_WRITE_FUNCT = (0x08, 0x0C, 0x0D, 0x0F)  # jr, syscall, break, sync -- R-type that writes no rd


def _dest_reg(word: int) -> Optional[int]:
    """The GENERAL register this instruction writes, as far as the mask needs to know.

    R-type writes `rd`; a general load and an immediate ALU op write `rt`; a coprocessor move to a
    general register writes `rt`; everything else is treated as writing nothing. What is left out is
    the safe direction: a register whose write the mask misses stays marked as holding an address, so
    at worst a displacement is masked that did not have to be -- which costs uniqueness, never a wrong
    pairing.
    """
    op = word >> 26
    if op == 0:
        if (word & 0x3F) in NO_WRITE_FUNCT:
            return None
        return (word >> 11) & 0x1F
    if op in IMM_RT_OPS or op in GPR_LOAD_OPS:
        return (word >> 16) & 0x1F
    if op in COP_OPS and ((word >> 21) & 0x1F) in COP_TO_GPR_RS:
        return (word >> 16) & 0x1F
    return None


def mask_address_operands(code: bytes) -> bytes:
    """`code` with every ADDRESS-FORMING load/store displacement zeroed, the rest byte for byte.

    A register is "holding an address" from the `lui` that loaded its high half until the next
    instruction that writes it; an `addiu`/`ori` off such a register carries that on to its own
    destination. `$sp`- and `$zero`-based accesses are frame and absolute-low accesses and are never
    masked; `$gp`-based ones always are, because that is how a small global is named.
    """
    out = bytearray(code)
    holds: set = set()
    for i in range(0, len(code) - 3, 4):
        w = int.from_bytes(code[i:i + 4], "little")
        op = w >> 26
        rs, rt = (w >> 21) & 0x1F, (w >> 16) & 0x1F
        if op == LUI_OP:
            holds.add(rt)
            holds.discard(0)
            continue
        if op in LO_OPS and rs in holds:
            holds.add(rt)
            holds.discard(0)
            continue
        if op in MEM_OPS and (rs in holds or rs == GP_REG):
            out[i:i + 4] = (w & 0xFFFF0000).to_bytes(4, "little")
        dest = _dest_reg(w)
        if dest is not None:
            holds.discard(dest)
    return bytes(out)


def relinked_fingerprint(code: bytes) -> Optional[str]:
    """The fingerprint of the masked stream -- None for a body with no bytes, as `fingerprint` is."""
    if not code:
        return None
    return fingerprint(mask_address_operands(code))


def formed_addresses(code: bytes) -> List[int]:
    """Every guest address a body materialises with a `lui` and a low half, in order.

    The low half may be an `addiu`/`addi` (sign-extended), an `ori` (zero-extended), or the
    displacement of the load or store that uses the address straight away.
    """
    out: List[int] = []
    hi: Dict[int, int] = {}
    for i in range(0, len(code) - 3, 4):
        w = int.from_bytes(code[i:i + 4], "little")
        op = w >> 26
        rs, rt, imm = (w >> 21) & 0x1F, (w >> 16) & 0x1F, w & 0xFFFF
        if op == LUI_OP:
            hi[rt] = imm
            hi.pop(0, None)
            continue
        if rs in hi and (op in LO_OPS or op in MEM_OPS):
            low = imm if op == 0x0D else (imm - 0x10000 if imm >= 0x8000 else imm)
            out.append(((hi[rs] << 16) + low) & 0xFFFFFFFF)
            if op in LO_OPS:
                hi.pop(rt, None)                   # rt now holds the whole address, not a half
                hi.pop(0, None)
                continue
        dest = _dest_reg(w)
        if dest is not None:
            hi.pop(dest, None)
    return out


# ---- images and tables ---------------------------------------------------------------------

def load_segments(elf: bytes) -> List[Segment]:
    """(vaddr, file bytes) for every PT_LOAD segment of a little-endian ELF32."""
    if elf[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    phoff = struct.unpack_from("<I", elf, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", elf, 42)
    segs = []
    for i in range(phnum):
        p_type, off, vaddr, _pa, filesz = struct.unpack_from("<5I", elf, phoff + i * phentsize)
        if p_type == 1 and filesz:
            segs.append((vaddr, elf[off:off + filesz]))
    return segs


def load_functions(csv_path: str) -> List[Func]:
    """The Ghidra table as (start, end, name), sorted. [Start, End) is the body (fix_ghidra_csv.py)."""
    out = []
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            out.append((int(row["Start"], 16), int(row["End"], 16), row["Name"]))
    out.sort()
    return out


class Image:
    """Random access to an image's bytes by guest address."""

    def __init__(self, segments):
        if isinstance(segments, (bytes, bytearray)):
            raise TypeError("pass [(vaddr, bytes)] segments, or use Image.flat()")
        self.segments = sorted((int(v), bytes(d)) for v, d in segments)

    @classmethod
    def of(cls, segments, funcs: Sequence[Func]) -> "Image":
        """Accept either segments or one flat blob (based at the lowest function start, for tests)."""
        if isinstance(segments, (bytes, bytearray)):
            base = min((f[0] for f in funcs), default=0)
            return cls([(base, bytes(segments))])
        return cls(segments)

    def code(self, start: int, end: int) -> bytes:
        for vaddr, data in self.segments:
            if vaddr <= start and end <= vaddr + len(data):
                return data[start - vaddr:end - vaddr]
        # A body that straddles segments, or lies outside every one, has no bytes to hash.
        return b""

    def cstring(self, addr: int, limit: int = 128, minimum: int = 4) -> Optional[bytes]:
        """The NUL-terminated printable string at `addr`, or None when there is not one there.

        `minimum` keeps the empty and one-byte runs out: a single stray NUL inside a table of pointers
        would otherwise read as a string and make an anchor out of nothing.
        """
        for vaddr, data in self.segments:
            if vaddr <= addr < vaddr + len(data):
                chunk = data[addr - vaddr:addr - vaddr + limit]
                end = chunk.find(b"\x00")
                if end < minimum:                  # no terminator in range, or too short to mean much
                    return None
                text = chunk[:end]
                if all(32 <= c < 127 or c in (9, 10, 13) for c in text):
                    return text
                return None
        return None


def call_targets(code: bytes, start: int) -> List[int]:
    """The `jal` targets in a body, in order (duplicates kept: the count is part of the evidence)."""
    out = []
    for i in range(0, len(code) - 3, 4):
        w = int.from_bytes(code[i:i + 4], "little")
        if (w >> 26) == JAL:
            pc = start + i
            out.append(((pc + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2))
    return out


class _Side:
    """One image's functions with everything the passes read off them."""

    def __init__(self, funcs: Sequence[Func], segments):
        self.funcs = sorted(funcs)
        self.image = Image.of(segments, self.funcs)
        self.starts = set()
        self.name = {}
        self.fp = {}
        self.size = {}
        self.calls = {}
        self.by_fp = {}
        self.body = {}
        self._relfp = {}
        self._anchors = {}
        for start, end, name in self.funcs:
            if start in self.starts:
                continue                                    # a duplicated row: the first one wins
            body = self.image.code(start, end)
            self.starts.add(start)
            self.name[start] = name
            self.size[start] = len(body)
            self.body[start] = body
            self.calls[start] = call_targets(body, start)
            # A row whose bytes are not in the image (a CSV entry outside every PT_LOAD, a body that
            # straddles two segments) has NO evidence. It is not fingerprinted and never indexed:
            # fingerprint(b"") is the FNV basis, so hashing it would file every unreadable row under one
            # value, and the single-occurrence rule would then marry two of them as `exact` on nothing at
            # all. fp is None for these, and every pass skips them, so they end `unresolved` -- which is
            # the truth about them. The real r0001 table has 51 such rows.
            self.fp[start] = fingerprint(body) if body else None
            if self.fp[start] is not None:
                self.by_fp.setdefault(self.fp[start], []).append(start)

    # The two below are computed on demand: only the functions the first two passes left over ever
    # reach the relinked-body pass, and on the real pair that is a third of the table.

    def relfp(self, start: int) -> Optional[str]:
        """This body's fingerprint with the address-forming displacements masked away too."""
        if start not in self._relfp:
            self._relfp[start] = relinked_fingerprint(self.body.get(start, b""))
        return self._relfp[start]

    def anchors(self, start: int) -> Tuple[bytes, ...]:
        """The distinct strings this body forms the address of, sorted -- its string anchors.

        A string is evidence a relink cannot fake: the bytes are the same in both images even though
        the address is not, so two candidate bodies that reach different strings are different code.
        """
        if start not in self._anchors:
            found = set()
            for addr in formed_addresses(self.body.get(start, b"")):
                text = self.image.cstring(addr)
                if text:
                    found.add(text)
            self._anchors[start] = tuple(sorted(found))
        return self._anchors[start]


# ---- the matcher ---------------------------------------------------------------------------

def match(a_funcs: Sequence[Func], a_bytes, b_funcs: Sequence[Func], b_bytes,
          seeds: Optional[Dict[int, int]] = None,
          ties: Optional[Dict[int, str]] = None) -> Dict[int, Match]:
    """{a_addr: (b_addr, how)} for every function in a_funcs; `how` is one of HOWS.

    a_bytes/b_bytes are (vaddr, bytes) segments -- or one flat blob, based at the lowest function start.
    seeds are {a_addr: b_addr} pairs known by other means; each contributes its delta.

    `ties`, when given, is filled with {a_addr: tie_breaker} for the decisions that needed one -- today
    only `relinked-body`, as "unique", "callees" or "string". It is an out-parameter rather than a third
    element of the tuple so that every existing caller of `match` keeps reading the same shape.
    """
    a, b = _Side(a_funcs, a_bytes), _Side(b_funcs, b_bytes)
    out: Dict[int, Match] = {}
    taken: set = set()
    tie_of: Dict[int, str] = ties if ties is not None else {}

    def take(a_addr: int, b_addr: int, how: str, tie: Optional[str] = None) -> None:
        out[a_addr] = (b_addr, how)
        taken.add(b_addr)
        if tie:
            tie_of[a_addr] = tie

    def by_callees(a_addr: int, cands: Sequence[int]) -> Optional[int]:
        """The one candidate that agrees best with the calls already placed, or None on a tie."""
        want = [out[t][0] for t in a.calls[a_addr] if t in out and out[t][0] is not None]
        if not want:
            return None
        scored = []
        for cand in cands:
            have = list(b.calls[cand])
            hit = 0
            for t in want:
                if t in have:
                    have.remove(t)
                    hit += 1
            scored.append((hit, cand))
        scored.sort(reverse=True)
        if scored[0][0] == 0 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
            return None
        return scored[0][1]

    # Pass 1 -- exact: one occurrence of the fingerprint on each side.
    for fp_val, a_addrs in a.by_fp.items():
        b_addrs = b.by_fp.get(fp_val, ())
        if len(a_addrs) == 1 and len(b_addrs) == 1:
            take(a_addrs[0], b_addrs[0], "exact")

    # Pass 2 -- hash+callees: among the candidates sharing the fingerprint, the one whose calls agree
    # with the calls already placed. Repeat while it keeps resolving: each round feeds the next.
    while True:
        progress = False
        for a_addr in sorted(a.starts):
            if a_addr in out or a.fp[a_addr] is None:
                continue
            cands = [x for x in b.by_fp.get(a.fp[a_addr], ()) if x not in taken]
            if not cands:
                continue
            rivals = [x for x in a.by_fp[a.fp[a_addr]] if x not in out]
            if len(cands) == 1 and len(rivals) == 1:
                # The last pair sharing this hash. Pass 1 already took every globally unique one, so
                # what narrowed this group was the callee evidence below, on some earlier round.
                take(a_addr, cands[0], "hash+callees")
                progress = True
                continue
            want = [out[t][0] for t in a.calls[a_addr] if t in out and out[t][0] is not None]
            if not want:
                continue
            scored = []
            for cand in cands:
                have = list(b.calls[cand])
                hit = 0
                for t in want:
                    if t in have:
                        have.remove(t)
                        hit += 1
                scored.append((hit, cand))
            scored.sort(reverse=True)
            if scored[0][0] == 0:
                continue
            if len(scored) > 1 and scored[1][0] == scored[0][0]:
                continue                                      # a tie proves nothing
            take(a_addr, scored[0][1], "hash+callees")
            progress = True
        if not progress:
            break

    # Pass 3 -- relinked-body: the same instruction stream, relinked. The fingerprint keeps load/store
    # displacements because a struct offset is part of the code; for a global the displacement is half
    # an address and moves with the link, so any routine that touches a global fingerprints differently
    # in the two builds however unchanged it is. This pass masks those away too. Masked equality at the
    # same length already means every differing word is the same opcode with the same register fields
    # differing only in an immediate -- every difference is a relocation -- so the only thing left to
    # prove is WHICH body, and that is what uniqueness and the two tie-breakers are for.
    while True:
        progress = False
        a_left = [x for x in sorted(a.starts) if x not in out and a.fp[x] is not None]
        if not a_left:
            break
        b_groups: Dict[str, List[int]] = {}
        for x in sorted(b.starts):
            if x in taken or b.fp[x] is None:
                continue
            h = b.relfp(x)
            if h is not None:
                b_groups.setdefault(h, []).append(x)
        a_groups: Dict[str, List[int]] = {}
        for x in a_left:
            h = a.relfp(x)
            if h is not None:
                a_groups.setdefault(h, []).append(x)
        for h, a_addrs in sorted(a_groups.items()):
            for size in sorted({a.size[x] for x in a_addrs}):
                rivals = [x for x in a_addrs if a.size[x] == size]
                pool = [c for c in b_groups.get(h, ()) if c not in taken and b.size[c] == size]
                if not pool:
                    continue
                if len(rivals) == 1 and len(pool) == 1:
                    take(rivals[0], pool[0], "relinked-body", "unique")
                    progress = True
                    continue
                # More than one body wears this masked hash at this length. Each pairing has to be
                # bought with evidence the hash does not carry, and the last pair left over is
                # reported as narrowed by whatever bought the others -- never as "unique", which is
                # reserved for a hash that was on its own in both images.
                narrowed_by: Optional[str] = None
                for a_addr in rivals:
                    if a_addr in out:
                        continue
                    cands = [c for c in pool if c not in taken]
                    left = [x for x in rivals if x not in out]
                    if not cands:
                        break
                    if len(cands) == 1 and len(left) == 1 and narrowed_by:
                        take(a_addr, cands[0], "relinked-body", narrowed_by)
                        progress = True
                        continue
                    pick, tie = by_callees(a_addr, cands), "callees"
                    if pick is None:
                        anchors = a.anchors(a_addr)
                        if anchors:
                            hits = [c for c in cands if b.anchors(c) == anchors]
                            if len(hits) == 1:
                                pick, tie = hits[0], "string"
                    if pick is None:
                        continue                              # a tie neither breaker settles
                    take(a_addr, pick, "relinked-body", tie)
                    narrowed_by = tie
                    progress = True
        if not progress:
            break

    # Pass 4 -- seed+delta: a seed pair's offset, applied to the address itself. The delta says WHERE to
    # look; it is never on its own a reason to match. The candidate has to be the same function by the
    # same test the other passes use -- same fingerprint, same body length -- or one mistyped seed turns
    # the whole report into confident nonsense: unrelated functions paired at "rate 1.0, all seed+delta".
    deltas = []
    for a_addr, b_addr in (seeds or {}).items():
        d = int(b_addr) - int(a_addr)
        if d not in deltas:
            deltas.append(d)
    if deltas:
        for a_addr in sorted(a.starts):
            if a_addr in out or a.fp[a_addr] is None:
                continue
            for d in deltas:
                cand = a_addr + d
                if cand not in b.starts or cand in taken:
                    continue
                if b.fp.get(cand) != a.fp[a_addr] or b.size.get(cand) != a.size[a_addr]:
                    continue                                  # the delta landed on a different function
                take(a_addr, cand, "seed+delta")
                break

    for a_addr in sorted(a.starts):
        out.setdefault(a_addr, (None, "unresolved"))
    return out


def summary(matches: Dict[int, Match]) -> Dict[str, object]:
    """Counts per `how`, plus total/resolved/unresolved and the resolution rate."""
    stats: Dict[str, object] = {h: 0 for h in HOWS}
    for _b_addr, how in matches.values():
        stats[how] = int(stats.get(how, 0)) + 1
    total = len(matches)
    unresolved = int(stats["unresolved"])
    stats["total"] = total
    stats["resolved"] = total - unresolved
    stats["unresolved"] = unresolved
    stats["rate"] = round((total - unresolved) / total, 6) if total else 0.0
    return stats


# ---- the CLI -------------------------------------------------------------------------------

def parse_seed(text: str) -> Tuple[int, int]:
    lhs, _sep, rhs = text.partition("=")
    if not _sep:
        raise ValueError("a seed is 0xA=0xB, not %r" % text)
    return int(lhs, 16), int(rhs, 16)


def _read_side(elf_path: str, csv_path: str):
    with open(elf_path, "rb") as fh:
        segs = load_segments(fh.read())
    return load_functions(csv_path), segs


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("elf_a")
    ap.add_argument("csv_a")
    ap.add_argument("elf_b")
    ap.add_argument("csv_b")
    ap.add_argument("--seed", action="append", default=[], metavar="0xA=0xB",
                    help="an address pair known in both builds; its delta places relinked neighbours")
    ap.add_argument("--out", help="write every decision here as JSON")
    args = ap.parse_args(argv)

    for path in (args.elf_a, args.csv_a, args.elf_b, args.csv_b):
        if not os.path.exists(path):
            print("NO-DATA: missing", path)
            return 2
    try:
        seeds = dict(parse_seed(s) for s in args.seed)
    except ValueError as e:
        print("bad --seed:", e)
        return 2

    a_funcs, a_segs = _read_side(args.elf_a, args.csv_a)
    b_funcs, b_segs = _read_side(args.elf_b, args.csv_b)
    if not a_funcs or not b_funcs:
        print("NO-DATA: an empty function table")
        return 2

    ties: Dict[int, str] = {}
    matches = match(a_funcs, a_segs, b_funcs, b_segs, seeds=seeds, ties=ties)
    stats = summary(matches)
    names = {s: n for s, _e, n in a_funcs}
    print("# a %s: %d functions; b %s: %d functions; %d seeds"
          % (args.csv_a, len(a_funcs), args.csv_b, len(b_funcs), len(seeds)))
    print("resolved %d/%d = %.2f%%  (%s)"
          % (stats["resolved"], stats["total"], 100.0 * float(stats["rate"]),
             " ".join("%s=%d" % (h, stats[h]) for h in HOWS)))

    if args.out:
        doc = {
            "a": {"elf": args.elf_a, "csv": args.csv_a},
            "b": {"elf": args.elf_b, "csv": args.csv_b},
            "seeds": {"0x%08x" % k: "0x%08x" % v for k, v in sorted(seeds.items())},
            "summary": stats,
            "matches": {"0x%08x" % a_addr: {"name": names.get(a_addr, ""),
                                            "b": None if b_addr is None else "0x%08x" % b_addr,
                                            "how": how,
                                            "tie": ties.get(a_addr)}
                        for a_addr, (b_addr, how) in sorted(matches.items())},
        }
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
