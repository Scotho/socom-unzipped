"""Carry one build's forced entry points onto another build's addresses (Sprint 11 Task 19).

    python -m tools_py.translate_extras recomp/extra_functions.txt game/r0004/match.json \\
        recomp/extra_functions_r0004.txt --append

`recomp/extra_functions.txt` is three weeks of forced entry points found on the r0001 image: thread
resume points the scheduler unwinds to, callbacks materialised as `lui`/`addiu` immediates, interior
starts Ghidra merged into a neighbour's row. Each one is a claim that CODE STARTS HERE, and the
recompiler emits a body for it; without it the dispatcher reports `[guest-branch:missing-target]` and
the thread silently dies. Every one of those numbers is an r0001 GUEST ADDRESS, so on a build that was
relinked from changed source it names whatever that build happens to have put there.

The match report knows where each r0001 FUNCTION went. So:

  function start  the forced entry IS a function the matcher placed: `exact`, `hash+callees`,
                  `relinked-body` or `seed+delta` answers directly.
  body interior   the forced entry sits inside a matched function's body: the body moved as a block,
                  so the address moves by that function's delta. Marked `weak` when the function was
                  placed by `seed+delta`, because the seed pass proves the function's fingerprint and
                  length at the new address -- not that the bytes inside it kept their offsets.
  loader region   an address in a region that is BYTE-IDENTICAL in both images does not move.
  anchored        (`--anchor`) the matcher placed neither the address nor a function holding it, but
                  the WINDOW of instructions around it -- every address immediate masked out -- occurs
                  exactly once in the B image. That one hit is the same code in the same company in
                  the other build. This matters here more than anywhere else in the project: r0001's
                  own forced entries are folded into its function table as rows, and a row three
                  words long has no fingerprint to match, so the matcher loses most of them by
                  construction. `revision_toml.instruction_decision` is that escalation, unchanged.
  left out        none of the above. A guess here is worse than a gap: a forced entry point that is
                  not really a function start makes `fix_ghidra_csv.py` TRUNCATE whatever the new
                  build really has there. Those are dropped and counted by reason.

All of that is `tools_py.revision_toml.Translator` and its anchor, which already move instruction
patches and [mmio] keys by exactly these rules; this module reuses them rather than restating them.

THEN EVERY SURVIVOR IS CHECKED AGAINST THE B IMAGE ITSELF, because a delta is arithmetic and the
image is evidence:

  in the text     the address is inside an executable PT_LOAD of the B ELF. Off the image, the entry
                  is meaningless.
  aligned         MIPS instructions are 4-byte aligned; an unaligned "function start" is arithmetic
                  that landed inside an instruction.
  not a delay slot  the word BEFORE it is not a branch or a jump. A delay slot belongs to the branch
                  above it, and a function cannot start there. (A previous word outside the image is
                  no evidence of a branch, so it passes.)

`--discovered <file>` merges finds from the discovery tools (`0xADDR <tool>` per line) into the same
run: they ride the same verification and the same single append, tagged by the tool that found them.

THE APPEND IS ONE WRITE. The target file is also being appended to, live, by the harvest loop that
feeds the runtime's missing targets back in. This tool therefore reads the file, builds the whole
block in memory, and writes it with a single `O_APPEND` write under one header line -- so a
concurrent append lands before or after this block, never inside it. With no `--append` nothing is
written at all.
"""
import argparse
import json
import os
import re
import struct
import sys
from collections import OrderedDict
from typing import Dict, List, Optional, Sequence, Tuple

from tools_py.revision_toml import (Anchor, CodeImage, Translator, fixed_regions, instruction_decision,
                                    load_bodies, load_matches, parse_region)

ADDR_RE = re.compile(r"^\s*(0[xX][0-9A-Fa-f]+)")

# Why a translated address can still be refused. These are the buckets the report counts.
OUTSIDE = "outside the image text"
UNALIGNED = "not on a 4-byte boundary"
DELAY_SLOT = "in a branch or jump delay slot"

# Why a source address never got a translation at all.
NO_MATCH = "the matcher could not place this function"
HOLDER_LOST = "inside a function the matcher could not place"
NO_BODY = "no function body holds it"


def exec_segments(elf_bytes: bytes) -> List[Tuple[int, bytes]]:
    """(vaddr, bytes) for every executable PT_LOAD -- the image's text, and nothing else.

    `address_matcher.load_segments` takes every PT_LOAD; a forced entry point has to be in code, so
    this reads the flags as the discovery tools (`find_imm_targets.py` and friends) do."""
    if elf_bytes[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    phoff = struct.unpack_from("<I", elf_bytes, 0x1C)[0]
    phentsize, phnum = struct.unpack_from("<HH", elf_bytes, 0x2A)
    out = []
    for i in range(phnum):
        p_type, off, vaddr, _pa, filesz, _memsz, flags = struct.unpack_from(
            "<7I", elf_bytes, phoff + i * phentsize)
        if p_type == 1 and filesz and (flags & 1):
            out.append((vaddr, elf_bytes[off:off + filesz]))
    return sorted(out)


class Text:
    """The B image's executable bytes, by guest address."""

    def __init__(self, segments: Sequence[Tuple[int, bytes]]):
        self.segs = sorted((int(v), bytes(d)) for v, d in segments)

    def holds(self, addr: int) -> bool:
        return any(v <= addr < v + len(d) for v, d in self.segs)

    def word(self, addr: int) -> Optional[int]:
        for v, d in self.segs:
            if v <= addr <= v + len(d) - 4:
                return struct.unpack_from("<I", d, addr - v)[0]
        return None


def is_branch(word: Optional[int]) -> bool:
    """Does this instruction have a delay slot after it?

    j/jal, the conditional branches and their likely forms, REGIMM's bltz/bgez family, jr/jalr, and
    the coprocessor branches. A word that could not be read is not evidence of a branch."""
    if word is None:
        return False
    op = word >> 26
    if op in (0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17):
        return True
    if op == 0x01:                                   # REGIMM: bltz/bgez/bltzal/bgezal (+ likely)
        return ((word >> 16) & 0x1F) in (0, 1, 2, 3, 0x10, 0x11, 0x12, 0x13)
    if op == 0x00:                                   # SPECIAL: jr, jalr
        return (word & 0x3F) in (0x08, 0x09)
    if op in (0x10, 0x11, 0x12, 0x13):               # COP0/1/2/3: bc?f / bc?t
        return ((word >> 21) & 0x1F) == 0x08
    return False


def verify(text: Text, addr: int) -> Optional[str]:
    """None when `addr` is a plausible entry point in the B image, else why it is not."""
    if addr & 3:
        return UNALIGNED
    if not text.holds(addr):
        return OUTSIDE
    if is_branch(text.word(addr - 4)):
        return DELAY_SLOT
    return None


def read_list(path: str) -> List[int]:
    """Every address in an extra_functions-shaped file, comments and blank lines ignored."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = ADDR_RE.match(line)
            if m:
                out.append(int(m.group(1), 16))
    return out


def read_discovered(path: str) -> List[Tuple[int, str]]:
    """`0xADDR <tool>` per line: what a discovery tool found, and which tool found it."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#")[0].strip()
            if not line:
                continue
            parts = line.split()
            out.append((int(parts[0], 16), parts[1] if len(parts) > 1 else "discovery"))
    return out


def reason_bucket(reason: str) -> str:
    """The Translator's reason, with the address it names folded away so reasons can be counted."""
    reason = reason.split(";")[0]                 # the anchor's own "and no window recurs" tail
    if reason.startswith("inside 0x"):
        return HOLDER_LOST
    return reason or NO_MATCH


def method_of(decision) -> str:
    """How this address moved, written for the comment: method, whether it rode a body, how solid."""
    if decision.method == "loader":
        return "loader"
    method = decision.method or "?"
    if decision.interior:
        method += " body"
        if decision.weak:
            method += " weak"
    return method


def name_for(addr: int, decision, tr: Translator, names: Dict[int, str]) -> str:
    """Which r0001 function this address came out of, for the comment's provenance."""
    holder = decision.via if decision.via is not None else addr
    if holder in names:
        return names[holder]
    for start, _end, name in tr.containing(addr):
        if name:
            return name
    return "-"


def translate(source: Sequence[int], tr: Translator, names: Dict[int, str],
              anchor: Optional[Anchor] = None) -> Tuple[List[dict], "OrderedDict[str, int]", int]:
    """Every source address that can be carried over, a count of the ones that cannot, and how many
    of the carried ones the window anchor -- not the function matcher -- placed."""
    carried: List[dict] = []
    lost: "OrderedDict[str, int]" = OrderedDict()
    anchored = 0
    for a in source:
        d = tr.translate(a)
        if d.kind == "unresolved" and anchor is not None:
            escalated = instruction_decision(anchor, a, d)
            if escalated.kind == "translated":
                d, anchored = escalated, anchored + 1
        if d.kind == "unresolved":
            bucket = reason_bucket(d.reason)
            lost[bucket] = lost.get(bucket, 0) + 1
            continue
        carried.append({"a": a, "b": d.addr, "method": method_of(d),
                        "name": name_for(a, d, tr, names)})
    return carried, lost, anchored


def block(carried: Sequence[dict], finds: Sequence[Tuple[int, str]], header: str) -> List[str]:
    lines = [header]
    for item in carried:
        lines.append("0x%08x  # from r0001 0x%08x via %s (%s)"
                     % (item["b"], item["a"], item["method"], item["name"]))
    for addr, tool in finds:
        lines.append("0x%08x  # new find: %s" % (addr, tool))
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source_list", help="the forced entry points to carry over (recomp/extra_functions.txt)")
    ap.add_argument("match_json", help="tools_py.address_matcher --out for this revision")
    ap.add_argument("target_list", help="the revision's own list (recomp/extra_functions_<rev>.txt)")
    ap.add_argument("--append", action="store_true", help="write the block; without it nothing is written")
    ap.add_argument("--discovered", help="`0xADDR <tool>` per line: what the discovery tools found now")
    ap.add_argument("--csv-a", help="the A build's function table (default: the match report's own a.csv)")
    ap.add_argument("--elf-a", help="the A image (default: the match report's own a.elf)")
    ap.add_argument("--elf-b", help="the B image (default: the match report's own b.elf)")
    ap.add_argument("--fixed", action="append", default=[], metavar="0xLO-0xHI",
                    help="a region that does not move, instead of deriving it from the two ELFs")
    ap.add_argument("--anchor", action="store_true",
                    help="place what the matcher lost by the window of code around it (needs both images)")
    ap.add_argument("--header", default="# --- translated from r0001 ---",
                    help="the one comment line the appended block sits under")
    ap.add_argument("--json", action="store_true", help="print the counts as JSON as well")
    args = ap.parse_args(argv)

    for path in (args.source_list, args.match_json, args.target_list):
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
    if not elf_b or not os.path.exists(elf_b):
        print("NO-DATA: the B image is what every appended address is checked against (--elf-b)")
        return 2
    with open(elf_b, "rb") as fh:
        text = Text(exec_segments(fh.read()))

    have_a = bool(elf_a and os.path.exists(elf_a))
    segs_a = segs_b = None
    if have_a:
        from tools_py.address_matcher import load_segments
        with open(elf_a, "rb") as fh:
            segs_a = load_segments(fh.read())
        with open(elf_b, "rb") as fh:
            segs_b = load_segments(fh.read())

    if args.fixed:
        fixed = [parse_region(f) for f in args.fixed]
    elif have_a:
        fixed = fixed_regions(segs_a, segs_b)
    else:
        print("NO-DATA: the regions that do not move need both images (--elf-a/--elf-b, or --fixed)")
        return 2

    anchor = None
    if args.anchor:
        if not have_a:
            print("NO-DATA: the window anchor needs the A image too (--elf-a)")
            return 2
        anchor = Anchor(CodeImage(segs_a), CodeImage(segs_b))

    bodies = load_bodies(csv_a)
    names = {}
    for start, _end, name in bodies:
        names.setdefault(start, name)
    for a_addr, m in (doc.get("matches") or {}).items():
        if m.get("name"):
            names.setdefault(int(a_addr, 16), m["name"])

    tr = Translator(load_matches(doc), bodies, fixed)
    carried, lost, anchored = translate(read_list(args.source_list), tr, names, anchor)

    known = set(read_list(args.target_list))
    rejected: "OrderedDict[str, int]" = OrderedDict()
    already = 0

    def take(addr: int) -> bool:
        nonlocal already
        why = verify(text, addr)
        if why:
            rejected[why] = rejected.get(why, 0) + 1
            return False
        if addr in known:
            already += 1
            return False
        known.add(addr)
        return True

    keep = [item for item in carried if take(item["b"])]
    finds: List[Tuple[int, str]] = []
    per_tool: "OrderedDict[str, int]" = OrderedDict()
    if args.discovered:
        for addr, tool in read_discovered(args.discovered):
            if take(addr):
                finds.append((addr, tool))
                per_tool[tool] = per_tool.get(tool, 0) + 1

    lines = block(keep, finds, args.header)
    stats = OrderedDict([
        ("source", len(read_list(args.source_list))),
        ("translated", len(carried)),
        ("anchored", anchored),
        ("appended", len(keep) + len(finds)),
        ("from_r0001", len(keep)),
        ("already_listed", already),
        ("untranslatable", dict(lost)),
        ("rejected", dict(rejected)),
        ("discovered", dict(per_tool)),
    ])

    print("# %d source entries, %d translated (%d of them anchored), %d appended (%d carried, "
          "%d new finds), %d already listed, %d untranslatable, %d rejected"
          % (stats["source"], stats["translated"], anchored, stats["appended"], len(keep), len(finds),
             already, sum(lost.values()), sum(rejected.values())))
    for label, counts in (("untranslatable", lost), ("rejected", rejected), ("found now", per_tool)):
        for why, n in counts.items():
            print("#   %-14s %-46s %d" % (label, why, n))

    if args.append and stats["appended"]:
        # ONE write, with O_APPEND: a concurrent harvest append cannot land inside this block.
        with open(args.target_list, "a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        print("appended %d addresses to %s" % (stats["appended"], args.target_list))
    elif args.append:
        print("nothing to append to", args.target_list)
    else:
        print("dry run: %s not written" % args.target_list)
    if args.json:
        print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
