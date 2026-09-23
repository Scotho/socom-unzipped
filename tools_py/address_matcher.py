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

HOWS = ("exact", "hash+callees", "seed+delta", "unresolved")
JAL = 0x03


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
        for start, end, name in self.funcs:
            if start in self.starts:
                continue                                    # a duplicated row: the first one wins
            body = self.image.code(start, end)
            self.starts.add(start)
            self.name[start] = name
            self.size[start] = len(body)
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


# ---- the matcher ---------------------------------------------------------------------------

def match(a_funcs: Sequence[Func], a_bytes, b_funcs: Sequence[Func], b_bytes,
          seeds: Optional[Dict[int, int]] = None) -> Dict[int, Match]:
    """{a_addr: (b_addr, how)} for every function in a_funcs; `how` is one of HOWS.

    a_bytes/b_bytes are (vaddr, bytes) segments -- or one flat blob, based at the lowest function start.
    seeds are {a_addr: b_addr} pairs known by other means; each contributes its delta.
    """
    a, b = _Side(a_funcs, a_bytes), _Side(b_funcs, b_bytes)
    out: Dict[int, Match] = {}
    taken: set = set()

    def take(a_addr: int, b_addr: int, how: str) -> None:
        out[a_addr] = (b_addr, how)
        taken.add(b_addr)

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

    # Pass 3 -- seed+delta: a seed pair's offset, applied to the address itself. The delta says WHERE to
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

    matches = match(a_funcs, a_segs, b_funcs, b_segs, seeds=seeds)
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
                                            "how": how}
                        for a_addr, (b_addr, how) in sorted(matches.items())},
        }
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
