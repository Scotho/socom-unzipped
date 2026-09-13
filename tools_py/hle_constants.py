"""HLE stub consumer census -- Sprint 5 Task 4 Step 2 (static, zero game runs).

For every stub bound in `recomp/socom2.toml` (`stubs = [ "name@0xADDR", ... ]`), scan the ELF's
PT_LOAD bytes for MIPS `jal ADDR` (direct call) and `j ADDR` (tail call) and, for each direct call,
follow the return value (`$v0`, or `$f0` with `--float NAME`) forward from the return point and
classify what the guest does with it (research/19 F7, after prosper's `nid_gate_scan`):

    ignored        v0 is overwritten (or clobbered by another call) before any read
    zero-test      beqz/bnez/bltz/bgez/blez/bgtz, sltiu 1 / slti 0,1, slt(u) against $zero, or the
                   condition of a movz/movn
    const-compare  slti/sltiu with another constant, or beq/bne/slt against a register loaded with one
    var-compare    slt/sltu/beq/bne against a register NOT known to be a constant
    arithmetic     any other computation (addu/subu/mult/div/addiu imm != 0, mtc1, FPU math)
    stored         written to memory (sw/sd/sh/sb, swc1)
    deref          used as a base address (load or store through it)
    unresolved     the value reaches a register copy, a conditional branch, a call, `jr ra` or the walk budget
                   before a consumer; the reason and (for copies) the copy's own first use in the
                   same linear block are printed as a HINT, never promoted to a class

An unconditional `b` is followed (it is not a decision); the walk budget counts instructions.
Masks and sign/zero-extends (`andi imm`, `sll/sra` by a constant) are followed transparently: the
masked value is still the return value. The strongest use in the linear block wins, in the order
arithmetic > var-compare > stored > deref > const-compare > zero-test.

Tail calls (`j ADDR`) have no consumer here: the consumer is the caller's caller. They are printed
as `tail -- consumer upstream`. Sites inside another bound stub's own body are marked DEAD (that
body is never executed; its address is bound to C++). Address-taken references (a data word equal
to the stub address) are counted, because a `jalr` through them is invisible to this scan.

    python -m tools_py.hle_constants [--toml recomp/socom2.toml] [--elf game/overlays/socom2_game.elf]
        [--csv recomp/socom2_ghidra.csv] [--stub NAME ...] [--float NAME ...] [--extra NAME@0xADDR ...]
        [--summary]

The classification is a first pass for a human to check against the MIPS; research/20 records
the checked result. Exit 2 when the toml yields no stubs or the ELF yields no loadable bytes.
"""
import argparse
import bisect
import csv
import os
import re
import struct
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

WALK_BUDGET = 12
V0, SP, RA, ZERO = 2, 29, 31, 0
RISK_ORDER = ["arithmetic", "var-compare", "stored", "deref", "const-compare", "zero-test"]
CLASSES = RISK_ORDER + ["ignored", "unresolved"]

# Routines whose result the guest ABI returns in $f0 (single float), not $v0.
DEFAULT_FLOAT_RETURNS = ("__kernel_cosf", "__kernel_sinf")


# ----------------------------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------------------------

STUB_RE = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)@0x([0-9A-Fa-f]+)"')


def parse_stubs(toml_text: str) -> List[Tuple[str, int]]:
    """The `stubs = [ ... ]` list only (not `untracked_stubs`)."""
    m = re.search(r'^stubs\s*=\s*\[(.*?)^\]', toml_text, re.S | re.M)
    if not m:
        return []
    return [(n, int(a, 16)) for n, a in STUB_RE.findall(m.group(1))]


def load_segments(elf: bytes) -> List[Tuple[int, bytes]]:
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


def load_functions(csv_path: Optional[str]) -> List[Tuple[int, int, str]]:
    if not csv_path or not os.path.exists(csv_path):
        return []
    out = []
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            out.append((int(row["Start"], 16), int(row["End"], 16), row["Name"]))
    out.sort()
    return out


class FunctionIndex:
    def __init__(self, funcs: Sequence[Tuple[int, int, str]]):
        self.funcs = list(funcs)
        self.starts = [f[0] for f in self.funcs]

    def find(self, addr: int) -> Optional[Tuple[int, int, str]]:
        i = bisect.bisect_right(self.starts, addr) - 1
        if i >= 0 and self.funcs[i][0] <= addr < self.funcs[i][1]:
            return self.funcs[i]
        return None


# ----------------------------------------------------------------------------------------------
# Minimal R5900 decode: what an instruction reads and writes
# ----------------------------------------------------------------------------------------------

@dataclass
class Ins:
    word: int
    kind: str                      # "copy" "mask" "arith" "cmpimm" "cmpreg" "store" "load" "branch"
                                   # "call" "jump" "jr" "fcopy" "farith" "fstore" "mtc1" "other"
    reads: Tuple[int, ...] = ()    # GPRs read (values)
    base: Optional[int] = None     # GPR used as an address
    writes: Tuple[int, ...] = ()   # GPRs written
    freads: Tuple[int, ...] = ()
    fwrites: Tuple[int, ...] = ()
    zero_branch: bool = False      # branch compares one register against zero
    const: Optional[int] = None    # loaded immediate for "li" forms
    target: Optional[int] = None


def decode(word: int, pc: int) -> Ins:
    op = word >> 26
    rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    sa, funct = (word >> 6) & 31, word & 63
    imm = word & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    if op == 0:
        if funct in (8,):
            return Ins(word, "jr", reads=(rs,))
        if funct == 9:
            return Ins(word, "call", reads=(rs,), writes=(rd,))
        if funct in (0, 2, 3, 56, 58, 59, 60, 62, 63):          # shifts by constant
            if word == 0:
                return Ins(word, "other")
            return Ins(word, "mask", reads=(rt,), writes=(rd,))
        if funct in (33, 37, 38, 45) and (rs == 0 or rt == 0):    # addu/or/xor/daddu with $zero
            src = rt if rs == 0 else rs
            return Ins(word, "copy", reads=(src,), writes=(rd,))
        if funct in (42, 43):
            if rs == 0 or rt == 0:                                # slt/sltu against $zero: a sign/zero test
                return Ins(word, "cmpzero", reads=(rs or rt,), writes=(rd,))
            return Ins(word, "cmpreg", reads=(rs, rt), writes=(rd,))
        if funct in (24, 25, 26, 27):
            return Ins(word, "arith", reads=(rs, rt))
        if funct in (16, 18):                                     # mfhi/mflo
            return Ins(word, "arith", writes=(rd,))
        if funct in (10, 11):                                     # movz/movn: rt is the condition
            return Ins(word, "movcond", reads=(rs, rt), writes=(rd,))
        if funct in (12, 13):
            return Ins(word, "other")
        return Ins(word, "arith", reads=(rs, rt), writes=(rd,))
    if op == 1:
        return Ins(word, "branch", reads=(rs,), zero_branch=True,
                   target=(pc + 4 + (simm << 2)) & 0xFFFFFFFF)
    if op in (2, 3):
        tgt = ((pc + 4) & 0xF0000000) | ((word & 0x3FFFFFF) << 2)
        return Ins(word, "call" if op == 3 else "jump", writes=(RA,) if op == 3 else (), target=tgt)
    if op in (4, 5, 20, 21):
        if rt == 0 or rs == 0:
            return Ins(word, "branch", reads=(rs or rt,), zero_branch=True,
                       target=(pc + 4 + (simm << 2)) & 0xFFFFFFFF)
        return Ins(word, "branch", reads=(rs, rt), target=(pc + 4 + (simm << 2)) & 0xFFFFFFFF)
    if op in (6, 7, 22, 23):
        return Ins(word, "branch", reads=(rs,), zero_branch=True,
                   target=(pc + 4 + (simm << 2)) & 0xFFFFFFFF)
    if op in (9, 25, 8, 24):                                      # addiu/daddiu/addi/daddi
        if rs == 0:
            return Ins(word, "li", writes=(rt,), const=simm)
        if simm == 0:
            return Ins(word, "copy", reads=(rs,), writes=(rt,))
        return Ins(word, "arith", reads=(rs,), writes=(rt,))
    if op in (10, 11):
        if simm in (0, 1):                                        # slti 0/1, sltiu 1: sign/zero tests
            return Ins(word, "cmpzero", reads=(rs,), writes=(rt,))
        return Ins(word, "cmpimm", reads=(rs,), writes=(rt,))
    if op == 12:
        return Ins(word, "mask", reads=(rs,), writes=(rt,))
    if op in (13, 14):
        if rs == 0:
            return Ins(word, "li", writes=(rt,), const=imm)
        return Ins(word, "arith", reads=(rs,), writes=(rt,))
    if op == 15:
        return Ins(word, "li", writes=(rt,), const=(simm << 16))
    if op == 28:                                                  # MMI
        return Ins(word, "arith", reads=(rs, rt), writes=(rd,))
    if op in (32, 33, 35, 36, 37, 39, 55, 26, 27, 30):            # loads (ldl/ldr, EE lq)
        return Ins(word, "load", base=rs, writes=(rt,))
    if op in (40, 41, 43, 63, 44, 45, 46, 31):                    # stores (sdl/sdr/swl/swr, EE sq)
        return Ins(word, "store", reads=(rt,), base=rs)
    if op == 49:                                                  # lwc1
        return Ins(word, "load", base=rs, fwrites=(rt,))
    if op == 57:                                                  # swc1
        return Ins(word, "fstore", freads=(rt,), base=rs)
    if op == 17:
        fs, ft, fd = rd, rt, sa
        if rs == 0:                                               # mfc1
            return Ins(word, "farith", freads=(fs,), writes=(rt,))
        if rs == 4:                                               # mtc1
            return Ins(word, "mtc1", reads=(rt,), fwrites=(fs,))
        if rs in (2, 6):
            return Ins(word, "other", writes=(rt,) if rs == 2 else ())
        if rs == 8:                                               # bc1f/bc1t
            return Ins(word, "branch", target=(pc + 4 + (simm << 2)) & 0xFFFFFFFF)
        if rs in (16, 20):
            if funct == 6:
                return Ins(word, "fcopy", freads=(fs,), fwrites=(fd,))
            if funct >= 48:
                return Ins(word, "fcmp", freads=(fs, ft))
            if funct in (4, 5, 7, 36, 32):
                return Ins(word, "farith", freads=(fs,), fwrites=(fd,))
            return Ins(word, "farith", freads=(fs, ft), fwrites=(fd,))
        return Ins(word, "other")
    return Ins(word, "other")


# ----------------------------------------------------------------------------------------------
# The walk
# ----------------------------------------------------------------------------------------------

@dataclass
class Site:
    stub: str
    addr: int
    kind: str                         # "direct" or "tail"
    func: Optional[str] = None
    dead: bool = False
    cls: str = ""
    uses: List[str] = field(default_factory=list)
    hint: str = ""


def _strongest(uses: Sequence[str]) -> Optional[str]:
    for c in RISK_ORDER:
        if c in uses:
            return c
    return None


def classify(read_word, pc: int, is_float: bool = False, budget: int = WALK_BUDGET):
    """Classify the consumer of a call at `pc`. `read_word(addr)` -> int or None.
    Returns (class, uses, hint)."""
    tracked = {V0} if not is_float else set()
    ftracked = {0} if is_float else set()
    consts: Dict[int, int] = {ZERO: 0}
    uses: List[str] = []
    copies: Dict[int, str] = {}       # copy reg -> "" until its first use is seen
    retired: List[Tuple[int, str]] = []  # copies overwritten after their first use
    hint = ""

    def note_use(kind: str, via_copy: Optional[int]):
        if via_copy is None:
            uses.append(kind)
        elif not copies.get(via_copy):
            copies[via_copy] = kind

    def origin(regs) -> Optional[int]:
        """None if the direct return register is among regs, else the copy register it is."""
        hit = [r for r in regs if r in tracked]
        if not hit:
            return -1
        return None if any(r not in copies for r in hit) else hit[0]

    def step(ins: Ins) -> None:
        # uses
        if ins.kind in ("store",):
            if ins.reads and ins.reads[0] in tracked:
                note_use("stored", origin(ins.reads))
            if ins.base in tracked:
                note_use("deref", origin((ins.base,)))
        elif ins.kind == "load" and ins.base in tracked:
            note_use("deref", origin((ins.base,)))
        elif ins.kind == "fstore" and ins.freads[0] in ftracked:
            uses.append("stored")
        elif ins.kind == "fstore" and ins.base in tracked:
            note_use("deref", origin((ins.base,)))
        elif ins.kind in ("farith", "fcmp") and any(f in ftracked for f in ins.freads):
            uses.append("arithmetic" if ins.kind == "farith" else "var-compare")
        elif ins.kind == "fcopy" and ins.freads[0] in ftracked:
            pass
        elif ins.kind == "cmpzero" and ins.reads[0] in tracked:
            note_use("zero-test", origin(ins.reads))
        elif ins.kind == "movcond" and ins.reads[1] in tracked:
            note_use("zero-test", origin((ins.reads[1],)))
        elif ins.kind == "cmpimm" and ins.reads[0] in tracked:
            note_use("const-compare", origin(ins.reads))
        elif ins.kind == "cmpreg" and any(r in tracked for r in ins.reads):
            other = [r for r in ins.reads if r not in tracked]
            kind = "const-compare" if (not other or other[0] in consts) else "var-compare"
            note_use(kind, origin(ins.reads))
        elif ins.kind in ("arith", "mtc1") and any(r in tracked for r in ins.reads):
            note_use("arithmetic", origin(ins.reads))
        # writes
        if ins.kind == "copy" and ins.reads[0] in tracked:
            tracked.add(ins.writes[0])
            if ins.writes[0] != ins.reads[0]:
                copies.setdefault(ins.writes[0], "")
            return
        if ins.kind == "movcond" and ins.reads[0] in tracked:   # conditionally selected: a copy
            tracked.add(ins.writes[0])
            copies.setdefault(ins.writes[0], "")
            return
        if ins.kind == "mask" and ins.reads[0] in tracked:
            tracked.add(ins.writes[0])
            return
        if ins.kind == "fcopy" and ins.freads[0] in ftracked:
            ftracked.add(ins.fwrites[0])
            return
        for w in ins.writes:
            if w in tracked:
                tracked.discard(w)
                if copies.get(w):
                    retired.append((w, copies[w]))
                copies.pop(w, None)
            if ins.kind == "li":
                consts[w] = ins.const
            else:
                consts.pop(w, None)
        for f in ins.fwrites:
            ftracked.discard(f)

    def finish(reason: str):
        cls = _strongest(uses)
        copy_hints = ["%s->%s" % (REG_NAMES[r], k) for r, k in retired]
        copy_hints += ["%s->%s" % (REG_NAMES[r], k or "?") for r, k in copies.items() if r in tracked or k]
        h = "" if cls else reason
        if copy_hints:
            h = (h + "; " if h else "") + "copy " + ", ".join(copy_hints)
        if cls:
            return cls, uses, h
        if reason == "clobbered":
            if copy_hints:
                return "unresolved", uses, h
            return "ignored", uses, ""
        return "unresolved", uses, h

    addr = pc + 8
    for _ in range(budget):
        w = read_word(addr)
        if w is None:
            return finish("end-of-image")
        ins = decode(w, addr)
        if (w >> 16) == 0x1000:                 # `b` (beq $zero,$zero): unconditional, so follow it
            ds = read_word(addr + 4)
            if ds is not None:
                step(decode(ds, addr + 4))
            if not tracked and not ftracked:
                return finish("clobbered")
            addr = ins.target
            continue
        if ins.kind in ("branch", "jump", "jr", "call"):
            reads_ret = [r for r in ins.reads if r in tracked]
            if ins.kind == "branch" and reads_ret:
                if ins.zero_branch:
                    note_use("zero-test", origin(reads_ret))
                else:
                    other = [r for r in ins.reads if r not in tracked]
                    kind = "const-compare" if (not other or other[0] in consts) else "var-compare"
                    note_use(kind, origin(ins.reads))
            if ins.kind == "call" and reads_ret:
                note_use("arithmetic", None)   # jalr through the return value
            ds = read_word(addr + 4)
            if ds is not None:
                step(decode(ds, addr + 4))
            if ins.kind == "branch":
                return finish("branch" if (tracked or ftracked) else "clobbered")
            if ins.kind == "jr" and ins.reads == (RA,):
                if V0 in tracked or 0 in ftracked:
                    return finish("returned -- consumer upstream")
                return finish("clobbered")
            if ins.kind == "call":
                survivors = [r for r in tracked if 16 <= r <= 23 or r == 30]
                args = [r for r in tracked if 4 <= r <= 11]
                if args:
                    return finish("forwarded as argument to call")
                if survivors or (ftracked - {0} and any(20 <= f <= 31 for f in ftracked)):
                    return finish("copy survives call")
                tracked.clear()
                ftracked.clear()
                return finish("clobbered")
            return finish("jump")
        step(ins)
        if not tracked and not ftracked:
            return finish("clobbered")
        addr += 4
    return finish("walk budget")


REG_NAMES = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5",
             "t6", "t7", "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1",
             "gp", "sp", "fp", "ra"]


# ----------------------------------------------------------------------------------------------
# Census
# ----------------------------------------------------------------------------------------------

class Image:
    def __init__(self, segments: Sequence[Tuple[int, bytes]]):
        self.segments = list(segments)

    def read_word(self, addr: int) -> Optional[int]:
        for base, data in self.segments:
            off = addr - base
            if 0 <= off <= len(data) - 4:
                return struct.unpack_from("<I", data, off)[0]
        return None

    def words(self):
        for base, data in self.segments:
            n = len(data) // 4
            for i, w in enumerate(struct.unpack_from("<%dI" % n, data, 0)):
                yield base + 4 * i, w


def census(image: Image, stubs: Sequence[Tuple[str, int]], funcs: FunctionIndex,
           float_returns: Sequence[str] = DEFAULT_FLOAT_RETURNS):
    by_target = {a: n for n, a in stubs}
    # A bound stub's body runs from its address to the next known function start or stub address;
    # sites inside it are DEAD (the body is replaced by C++). The next-start rule covers stubs the
    # function map lacks (e.g. fclose, sceSifLoadElf).
    starts = sorted(set(funcs.starts) | set(by_target))
    stub_ranges = []
    for _n, a in stubs:
        i = bisect.bisect_right(starts, a)
        stub_ranges.append((a, starts[i] if i < len(starts) else a + 4))
    sites: Dict[str, List[Site]] = {n: [] for n, _ in stubs}
    addr_taken: Dict[str, int] = {n: 0 for n, _ in stubs}
    for pc, w in image.words():
        if w in by_target:
            addr_taken[by_target[w]] += 1
        op = w >> 26
        if op not in (2, 3):
            continue
        tgt = ((pc + 4) & 0xF0000000) | ((w & 0x3FFFFFF) << 2)
        name = by_target.get(tgt)
        if name is None:
            continue
        f = funcs.find(pc)
        s = Site(name, pc, "direct" if op == 3 else "tail", func=f[2] if f else None)
        s.dead = any(lo <= pc < hi for lo, hi in stub_ranges)
        if op == 3:
            s.cls, s.uses, s.hint = classify(image.read_word, pc, name in float_returns)
        else:
            s.cls, s.hint = "tail", "consumer upstream"
        sites[name].append(s)
    return sites, addr_taken


def summarize(sites: List[Site]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for s in sites:
        if s.dead:
            key = "dead"
        else:
            key = s.cls
        counts[key] = counts.get(key, 0) + 1
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--toml", default="recomp/socom2.toml")
    ap.add_argument("--elf", default="game/overlays/socom2_game.elf")
    ap.add_argument("--csv", default="recomp/socom2_ghidra.csv")
    ap.add_argument("--stub", action="append", default=[], help="restrict to these names")
    ap.add_argument("--float", action="append", default=[], dest="floats",
                    help="extra routines returning in $f0")
    ap.add_argument("--extra", action="append", default=[], metavar="NAME@0xADDR",
                    help="also census a binding that is not in the toml (e.g. a runtime replaceFunction)")
    ap.add_argument("--summary", action="store_true", help="one line per stub")
    args = ap.parse_args(argv)

    with open(args.toml, encoding="utf-8") as fh:
        stubs = parse_stubs(fh.read())
    extras = [(n, int(a, 16)) for n, a in STUB_RE.findall(" ".join('"%s"' % e for e in args.extra))]
    if len(extras) != len(args.extra):
        print("bad --extra, want NAME@0xADDR:", args.extra)
        return 2
    stubs = stubs + extras
    if not stubs:
        print("NO-DATA: no stubs parsed from", args.toml)
        return 2
    with open(args.elf, "rb") as fh:
        segs = load_segments(fh.read())
    if not segs or not sum(len(d) for _, d in segs):
        print("NO-DATA: no loadable bytes in", args.elf)
        return 2
    funcs = FunctionIndex(load_functions(args.csv))
    image = Image(segs)
    floats = tuple(DEFAULT_FLOAT_RETURNS) + tuple(args.floats)
    sites, taken = census(image, stubs, funcs, floats)
    print("# toml %s: %d stubs; elf %s: %d segments, %d bytes; functions %d"
          % (args.toml, len(stubs), args.elf, len(segs), sum(len(d) for _, d in segs),
             len(funcs.funcs)))
    wanted = set(args.stub)
    for name, addr in stubs:
        if wanted and name not in wanted:
            continue
        ss = sites[name]
        direct = sum(1 for s in ss if s.kind == "direct" and not s.dead)
        tail = sum(1 for s in ss if s.kind == "tail" and not s.dead)
        dead = sum(1 for s in ss if s.dead)
        counts = summarize(ss)
        cstr = " ".join("%s=%d" % (k, counts[k]) for k in CLASSES + ["tail", "dead"] if counts.get(k))
        print("%-26s 0x%08X direct=%d tail=%d dead=%d addr-taken=%d  %s"
              % (name, addr, direct, tail, dead, taken[name], cstr))
        if args.summary:
            continue
        for s in ss:
            print("    0x%08X %-6s %-28s %-13s%s%s" % (
                s.addr, s.kind, s.func or "?", ("DEAD " if s.dead else "") + s.cls,
                (" uses=" + ",".join(s.uses)) if s.uses else "",
                (" [" + s.hint + "]") if s.hint else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
