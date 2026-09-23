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
which is a hardware register address and belongs to the machine, not to the build.
"""
import argparse
import bisect
import csv
import json
import os
import re
import sys
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
TARGET_RE = re.compile(r'target\s*=\s*"(0[xX][0-9A-Fa-f]+)"')
PATCH_RE = re.compile(r'address\s*=\s*"(0[xX][0-9A-Fa-f]+)"')
TABLE_ADDR_RE = re.compile(r'^\s*address\s*=\s*"(0[xX][0-9A-Fa-f]+)"')
SETTABLE_RE = re.compile(r'^(\s*)(input|output|ghidra_output)(\s*=\s*)"([^"]*)"(.*)$')

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
    if d.interior:
        return "r0001 0x%08x, body+0x%x of 0x%08x %s%s" % (
            a_addr, a_addr - (d.via or 0), d.via or 0, d.method, " (weak)" if d.weak else "")
    return "r0001 0x%08x %s" % (a_addr, d.method)


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


def rewrite(text: str, tr: Translator, sets: Optional[Dict[str, str]] = None) -> Tuple[List[str], List[Site]]:
    """The source config with every overlay address translated. Returns (lines, one Site per address)."""
    sets = sets or {}
    lines = text.splitlines()
    out: List[str] = []
    sites: List[Site] = []
    section, array = "", ""
    for n, line in enumerate(lines, 1):
        if array:
            if ARRAY_CLOSE_RE.match(line):
                array = ""
                out.append(line)
                continue
        else:
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


def revision_block(sites: Sequence[Site], source: str, match: str) -> List[str]:
    """The `[revision]` table: the counts, and every address this config still carries from r0001."""
    kinds = {"translated": 0, "unchanged": 0, "unresolved": 0}
    interior = weak = 0
    unresolved: "OrderedDict[int, List[str]]" = OrderedDict()
    for s in sites:
        kinds[s.decision.kind] = kinds.get(s.decision.kind, 0) + 1
        if s.decision.kind == "translated" and s.decision.interior:
            interior += 1
            weak += 1 if s.decision.weak else 0
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
        "# Addresses in a region that is byte-identical in both images do not move: untouched, uncommented.",
        "[revision]",
        'source = "%s"' % source.replace("\\", "/"),
        'match = "%s"' % match.replace("\\", "/"),
        "translated = %d" % kinds.get("translated", 0),
        "translated_interior = %d" % interior,
        "weak = %d" % weak,
        "unchanged = %d" % kinds.get("unchanged", 0),
        "unresolved_count = %d" % len(unresolved),
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
    ap.add_argument("--set-input", help="[general] input")
    ap.add_argument("--set-output", help="[general] output")
    ap.add_argument("--set-ghidra-output", help="[general] ghidra_output")
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

    if args.fixed:
        try:
            fixed = [parse_region(f) for f in args.fixed]
        except ValueError as e:
            print("bad --fixed:", e)
            return 2
    else:
        elf_a = args.elf_a or (doc.get("a") or {}).get("elf")
        elf_b = args.elf_b or (doc.get("b") or {}).get("elf")
        if not (elf_a and elf_b and os.path.exists(elf_a) and os.path.exists(elf_b)):
            print("NO-DATA: the regions that do not move need both images (--elf-a/--elf-b, or --fixed); "
                  "the report names %r and %r" % (elf_a, elf_b))
            return 2
        from tools_py.address_matcher import load_segments
        with open(elf_a, "rb") as fh:
            segs_a = load_segments(fh.read())
        with open(elf_b, "rb") as fh:
            segs_b = load_segments(fh.read())
        fixed = fixed_regions(segs_a, segs_b)
        print("# regions byte-identical in both images (they do not move): %s"
              % ", ".join("0x%08x-0x%08x" % r for r in fixed))

    tr = Translator(load_matches(doc), load_bodies(csv_a), fixed)
    with open(args.source_toml, encoding="utf-8") as fh:
        text = fh.read()
    sets = {k: v for k, v in (("input", args.set_input), ("output", args.set_output),
                              ("ghidra_output", args.set_ghidra_output)) if v is not None}
    lines, sites = rewrite(text, tr, sets)

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
    lines = lines + revision_block(sites, args.source_toml, args.match_json)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
