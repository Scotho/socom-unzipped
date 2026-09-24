#!/usr/bin/env python
"""Find entry points that no branch in the image names, so no branch-based scan can see them.

Two populations, both of which the r0004 gate has been dying on one address per round:

1. **data-referenced entries** -- a 32-bit word held in data (a vtable, a dispatch table, a thread
   descriptor, a callback registered with the kernel) whose value is a code address. Nothing
   branches or jumps there; the game loads the word and `jalr`s it. `find_imm_targets.py` catches
   the `lui`/`addiu` form of the same thing and explicitly does not catch this one.

2. **continuation entries** -- the pc a recompiled function *publishes* and then returns with: a
   call's return address (`jal`/`jalr` + 8), a conditional branch's fallthrough (branch + 8), a
   syscall's resume point (syscall + 4). The recompiler already registers these as resume entry
   points (`control_flow_analyzer.cpp`, `queueResumeEntryTarget`), but only when the address lies
   **inside the same function row** as the instruction that produces it
   (`resumeAddr >= function.start && resumeAddr < function.end`). When the map's row boundary falls
   between the two -- which it does whenever Ghidra started a row on a delay slot -- nobody
   registers the address, `hasFunction()` says no, and the EE scheduler reports
   `[guest-branch:missing-target] ... op=EE scheduler` with source == target == pc.

Neither population is reachable from `find_escaping_branches.py`, `find_gap_functions.py`,
`find_interior_functions.py` or `find_imm_targets.py`.

Usage:
    python tools_py/find_data_entries.py <elf> <ghidra.csv> [options]

      --extras FILE     addresses already forced (filtered out of the report)
      --scan data,resume   which scans to run (default: both)
      --append FILE     append the new addresses to FILE in one write
      --header TEXT     the single header line written above the appended block
      --quiet           counts only
"""
import argparse
import bisect
import csv
import struct
import sys

# --- EE opcode groups -------------------------------------------------------------------------

OP_SPECIAL = 0x00
OP_REGIMM = 0x01
OP_J = 0x02
OP_JAL = 0x03
COND_BRANCH_OPS = {0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17}
COP_OPS = {0x10, 0x11, 0x12, 0x13}
SPECIAL_JR = 0x08
SPECIAL_JALR = 0x09
SPECIAL_SYSCALL = 0x0C
JR_RA = 0x03E00008

# every primary opcode the R5900 defines; anything else means the word is not an instruction
DECODABLE_OPS = (
    {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
     0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
     0x10, 0x11, 0x12, 0x14, 0x15, 0x16, 0x17,
     0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1E, 0x1F}
    | set(range(0x20, 0x2F + 1))
    | {0x31, 0x33, 0x36, 0x37, 0x39, 0x3E, 0x3F}
)

# a memory op's displacement is aligned to its access width in compiler output; a word decoded out
# of a string table or a compressed blob almost never is. lwl/lwr/swl/swr/ldl/ldr are the
# deliberately unaligned ones and carry no requirement.
ACCESS_ALIGNMENT = {
    0x21: 2, 0x25: 2, 0x29: 2,                                    # lh, lhu, sh
    0x23: 4, 0x27: 4, 0x2B: 4, 0x31: 4, 0x39: 4,                  # lw, lwu, sw, lwc1, swc1
    0x37: 8, 0x3F: 8,                                             # ld, sd
    0x1E: 16, 0x1F: 16, 0x36: 16, 0x3E: 16,                       # lq, sq, lqc2, sqc2
}

VALID_SPECIAL = (
    set(range(0x00, 0x08)) - {0x01, 0x05}                          # shifts
    | {0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0F}                   # jr/jalr/movz/movn/syscall/break/sync
    | set(range(0x10, 0x1C))                                       # mfhi..divu1-ish
    | set(range(0x20, 0x2C))                                       # add..sltu, dadd..
    | {0x2D, 0x2F}                                                 # daddu, dsubu
    | set(range(0x30, 0x35))                                       # tge..tne
    | {0x36, 0x38, 0x3A, 0x3B, 0x3C, 0x3E, 0x3F}                   # dsll..dsra32
)

VALID_REGIMM = {0x00, 0x01, 0x02, 0x03, 0x08, 0x09, 0x0A, 0x0B,
                0x0C, 0x0E, 0x10, 0x11, 0x12, 0x13, 0x18, 0x19}

SHIFT_IMMEDIATE = {0x00, 0x02, 0x03, 0x38, 0x3A, 0x3B, 0x3C, 0x3E, 0x3F}
SHIFT_VARIABLE = {0x04, 0x06, 0x07, 0x14, 0x16, 0x17}


def is_sane_instruction(word):
    """Decodable *and* shaped like something a compiler emitted.

    The r0004 image is one read/write/execute PT_LOAD per overlay, so string tables and packed
    blobs sit in the same segment as the text and decode into "instructions" happily. Three cheap
    invariants throw nearly all of that out: a real primary opcode, an access displacement aligned
    to its width, and the reserved fields of `jr`/`jalr` actually being zero.
    """
    op = word >> 26
    if op not in DECODABLE_OPS:
        return False
    alignment = ACCESS_ALIGNMENT.get(op)
    if alignment is not None and (word & 0xFFFF) % alignment:
        return False
    if op == OP_SPECIAL:
        fn = word & 0x3F
        if fn not in VALID_SPECIAL:
            return False
        rt = (word >> 16) & 0x1F
        rs = (word >> 21) & 0x1F
        if fn == SPECIAL_JR and (rt or ((word >> 11) & 0x1F) or rs == 0):
            return False
        if fn == SPECIAL_JALR and (rt or rs == 0):
            return False                                   # nobody calls through $zero
        if fn == SPECIAL_SYSCALL and ((word >> 6) & 0xFFFFF):
            return False                                   # the EE emits `syscall` with code 0
        if fn in SHIFT_IMMEDIATE and rs != 0:
            return False                                   # sll/srl/sra/dsll.. have no rs field
        if fn in SHIFT_VARIABLE and ((word >> 6) & 0x1F) != 0:
            return False                                   # sllv/srlv/srav/dsllv.. have no sa
    elif op == OP_REGIMM:
        if ((word >> 16) & 0x1F) not in VALID_REGIMM:
            return False
        if ((word >> 21) & 0x1F) == 0:
            return False                                   # `bltz zero` and friends are not code
    return True


def is_unconditional_branch(word):
    """`b`/`bl` -- assembled as beq/beql zero,zero. Nothing falls through one."""
    op = word >> 26
    return op in (0x04, 0x14) and ((word >> 21) & 0x1F) == 0 and ((word >> 16) & 0x1F) == 0


def is_delay_slot_producer(word):
    """True when `word` is a branch or jump, so the word after it is a delay slot."""
    op = word >> 26
    if op in (OP_J, OP_JAL) or op in COND_BRANCH_OPS or op == OP_REGIMM:
        return True
    if op == OP_SPECIAL and (word & 0x3F) in (SPECIAL_JR, SPECIAL_JALR):
        return True
    if op in COP_OPS and ((word >> 21) & 0x1F) == 8:     # BCzF/BCzT
        return True
    return False


def is_call(word):
    op = word >> 26
    return op == OP_JAL or (op == OP_SPECIAL and (word & 0x3F) == SPECIAL_JALR)


def falls_through(word):
    """True when execution can reach `word`'s address + 8 (a call or a conditional branch)."""
    op = word >> 26
    if is_call(word):
        return True
    if is_unconditional_branch(word):
        return False
    if op in COND_BRANCH_OPS:
        return True
    if op == OP_REGIMM and ((word >> 16) & 0x1F) in (0x00, 0x01, 0x02, 0x03, 0x10, 0x11, 0x12, 0x13):
        return True
    if op in COP_OPS and ((word >> 21) & 0x1F) == 8:
        return True
    return False


def is_syscall(word):
    return (word >> 26) == OP_SPECIAL and (word & 0x3F) == SPECIAL_SYSCALL


def looks_like_entry(word, in_a_gap=True):
    """The prologue shapes a real function starts with, plus the bare leaf.

    `addiu/daddiu sp,sp,-N`, a store of `ra` (`sq`/`sd`/`sw`), `lui gp` (a PIC-ish entry that
    reloads the small-data pointer), or `jr ra` for a leaf that does nothing but return.

    The leaf only counts where the map has nothing: a bare `jr ra` *inside* a mapped function is
    that function's return, and a data word equal to its address is a coincidence, not an entry.
    Nine of the fourteen r0004 data hits were exactly that before this clause.
    """
    if word == JR_RA:
        return in_a_gap
    op = word >> 26
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    imm = word & 0xFFFF
    signed = imm - 0x10000 if imm & 0x8000 else imm
    if op in (0x09, 0x19) and rs == 29 and rt == 29 and signed < 0:      # addiu/daddiu sp,sp,-N
        return True
    if op in (0x2B, 0x3F, 0x1F) and rt == 31:                            # sw/sd/sq ra,N(rX)
        return True
    if op == 0x0F and rt == 28:                                          # lui gp,hi
        return True
    return False


# --- the image and the map --------------------------------------------------------------------

class Image(object):
    """The PT_LOADs of an EE ELF, with a word accessor over guest addresses."""

    def __init__(self, path):
        with open(path, "rb") as f:
            self.raw = f.read()
        phoff = struct.unpack_from("<I", self.raw, 0x1C)[0]
        phnum = struct.unpack_from("<H", self.raw, 0x2C)[0]
        self.segments = []          # (vaddr, offset, filesz, flags)
        for i in range(phnum):
            p_type, off, vaddr, _pa, filesz, _memsz, flags, _al = struct.unpack_from(
                "<IIIIIIII", self.raw, phoff + i * 32)
            if p_type == 1 and filesz:
                self.segments.append((vaddr, off, filesz, flags))
        self.segments.sort()

    def word(self, addr):
        if addr & 3:
            return None
        for vaddr, off, size, _flags in self.segments:
            if vaddr <= addr < vaddr + size - 3:
                return struct.unpack_from("<I", self.raw, off + addr - vaddr)[0]
        return None

    def in_exec(self, addr):
        return any(v <= addr < v + s for v, _o, s, f in self.segments if f & 1)

    def words(self, vaddr, off, size):
        count = size // 4
        return vaddr, struct.unpack_from("<%dI" % count, self.raw, off)


class Rows(object):
    """The revision's function map: sorted, non-overlapping-enough ranges with a start set."""

    def __init__(self, ranges):
        self.ranges = sorted(ranges)
        self.starts = [r[0] for r in self.ranges]
        self.start_set = set(self.starts)
        # rows overlap in the folded map, so "is X covered" is not a neighbour test. The running
        # maximum of `end` over the rows sorted by `start` answers both questions this tool asks
        # in one bisect: a row covers X iff some row with start <= X reaches past X.
        self.reach = []
        furthest = 0
        for start, end, _name in self.ranges:
            furthest = max(furthest, end)
            self.reach.append(furthest)

    def __len__(self):
        return len(self.ranges)

    def reaches_past(self, addr, limit):
        """Some row starts at or before `addr` and ends after `limit`."""
        i = bisect.bisect_right(self.starts, addr) - 1
        return i >= 0 and self.reach[i] > limit

    def covers(self, addr):
        return self.reaches_past(addr, addr)

    def spans(self, addr, other):
        """One row covers `addr` and `other` both (`other` > `addr`)."""
        return self.reaches_past(addr, other)

    def is_start(self, addr):
        return addr in self.start_set


def load_rows(path):
    ranges = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 3:
                continue
            try:
                ranges.append((int(row[1], 16), int(row[2], 16), row[0]))
            except ValueError:
                continue
    return Rows(ranges)


def load_known(path):
    known = set()
    if not path:
        return known
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            text = line.split("#", 1)[0].strip()
            if not text:
                continue
            try:
                known.add(int(text, 16))
            except ValueError:
                continue
    return known


# --- the two scans ------------------------------------------------------------------------------

class Hit(object):
    __slots__ = ("address", "scan", "kind", "referenced_from", "source")

    def __init__(self, address, scan, kind, referenced_from=None, source=None):
        self.address = address
        self.scan = scan
        self.kind = kind
        self.referenced_from = referenced_from
        self.source = source

    def comment(self):
        if self.scan == "data":
            return "data word at 0x%x" % self.referenced_from
        return "%s of 0x%x" % (self.kind, self.source)


def code_like(image, addr, words=8):
    """Every one of the next `words` instructions decodes sanely: the address is inside real text."""
    for i in range(words):
        word = image.word(addr + 4 * i)
        if word is None or not is_sane_instruction(word):
            return False
    return True


def static_target(addr, word):
    """Where `word` transfers control, when that is knowable from the word alone."""
    op = word >> 26
    if op in (OP_J, OP_JAL):
        return ((addr + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
    if op in COND_BRANCH_OPS or op == OP_REGIMM or (op in COP_OPS and ((word >> 21) & 0x1F) == 8):
        imm = word & 0xFFFF
        return (addr + 4 + ((imm - 0x10000 if imm & 0x8000 else imm) << 2)) & 0xFFFFFFFF
    return None


def data_entries(image, rows):
    """Code addresses held as 32-bit words in data.

    "Data" is every loaded word that no map row covers: r0004 lays .rodata and .data inside the
    same read/write/execute PT_LOADs as the text, so a segment's flags cannot separate them, but
    the function map can.
    """
    hits = {}
    for vaddr, off, size, _flags in image.segments:
        base, words = image.words(vaddr, off, size)
        for i, value in enumerate(words):
            here = base + i * 4
            if rows.covers(here):
                continue                                   # inside a function: that word is code
            if value & 3 or not image.in_exec(value):
                continue
            if rows.is_start(value):
                continue
            target = image.word(value)
            if target is None or not is_sane_instruction(target):
                continue
            previous = image.word(value - 4)
            if previous is not None and is_delay_slot_producer(previous):
                continue                                   # a delay slot is never an entry
            if not looks_like_entry(target, in_a_gap=not rows.covers(value)):
                continue
            if not code_like(image, value):
                continue
            if value not in hits:
                hits[value] = Hit(value, "data", "data-pointer", referenced_from=here)
    return hits


def resume_entries(image, rows):
    """Continuation pcs the recompiler cannot register: they leave the row that produces them.

    For every call, branch-with-fallthrough and syscall inside a row, the address execution
    continues at (+8, or +4 for a syscall) is an entry the EE scheduler may resume a thread on.
    The recompiler registers it only when it stays inside the same row, so those are skipped here;
    what is left is exactly the blind spot.
    """
    hits = {}
    for start, end, _name in rows.ranges:
        for addr in range(start, end, 4):
            word = image.word(addr)
            if word is None or not is_sane_instruction(word):
                continue                                   # this word is data, not code
            elsewhere = static_target(addr, word)
            if elsewhere is not None and (not image.in_exec(elsewhere) or elsewhere == addr + 4):
                continue                                   # a "branch" decoded out of a table
            if is_syscall(word):
                cont, kind = addr + 4, "syscall-return"
            elif is_call(word):
                cont, kind = addr + 8, "call-return"
            elif falls_through(word):
                cont, kind = addr + 8, "branch-fallthrough"
            else:
                continue
            if rows.spans(addr, cont):
                continue                                   # the recompiler already resumes here
            if rows.is_start(cont) or not image.in_exec(cont):
                continue
            if not code_like(image, cont, words=4):
                continue
            if cont not in hits:
                hits[cont] = Hit(cont, "resume", kind, source=addr)
    return hits


def new_addresses(hits, known):
    return sorted(a for a in hits if a not in known)


# --- cli ----------------------------------------------------------------------------------------

def scan(elf_path, csv_path, which=("data", "resume")):
    image = Image(elf_path)
    rows = load_rows(csv_path)
    hits = {}
    if "data" in which:
        hits.update(data_entries(image, rows))
    if "resume" in which:
        for addr, hit in resume_entries(image, rows).items():
            hits.setdefault(addr, hit)
    return image, rows, hits


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("elf")
    parser.add_argument("csv")
    parser.add_argument("--extras", default=None)
    parser.add_argument("--scan", default="data,resume")
    parser.add_argument("--append", default=None)
    parser.add_argument("--header", default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    which = tuple(s.strip() for s in args.scan.split(",") if s.strip())
    unknown = [s for s in which if s not in ("data", "resume")]
    if unknown:
        parser.error("unknown scan(s): %s" % ", ".join(unknown))

    image, rows, hits = scan(args.elf, args.csv, which)
    known = load_known(args.extras)
    fresh = new_addresses(hits, known)

    by_scan = {}
    for hit in hits.values():
        by_scan[hit.scan] = by_scan.get(hit.scan, 0) + 1
    print("find_data_entries: %d row(s) in the map, %d hit(s) (%s), %d not already listed"
          % (len(rows), len(hits),
             ", ".join("%s=%d" % kv for kv in sorted(by_scan.items())) or "none",
             len(fresh)))

    if not args.quiet:
        for addr in fresh:
            print("0x%08x  # %s" % (addr, hits[addr].comment()))

    if args.append and fresh:
        block = ""
        if args.header:
            block += args.header.rstrip("\n") + "\n"
        for addr in fresh:
            block += "0x%08x  # %s\n" % (addr, hits[addr].comment())
        with open(args.append, "a", encoding="utf-8", newline="\n") as f:
            f.write(block)
        print("appended %d address(es) to %s" % (len(fresh), args.append))
    return 0


if __name__ == "__main__":
    sys.exit(main())
