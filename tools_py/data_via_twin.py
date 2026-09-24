"""Where did an r0001 DATA address go in r0004? (Sprint 11 Task 19, review F5.)

`tools_py/address_matcher.py` places FUNCTIONS. A data address is not a function, so
`tools_py/addresses_from_match.py` can only take one on trust: `--override cameraHolder=0x4429b0:hand,
data-via-twin`. *hand*, by the header's own admission -- and a hand number is one nobody else can re-run.
This is that procedure as a tool:

    take every r0001 function that MATERIALISES the address with a lui/lo pair;
    keep the ones whose r0004 twin `game/r0004/match.json` places BY EVIDENCE;
    read the SAME two instruction offsets in the twin's body, and see what address the pair forms there.

Every twin that reaches the address votes. Unanimity over many independent referrers is the claim; a
split vote is reported as a split vote and fills nothing.

    python -m tools_py.data_via_twin 0x416054 0x408c58            # per-address votes
    python -m tools_py.data_via_twin --control                    # cameraHolder, the reproduction
    python -m tools_py.data_via_twin --column                     # the four guest_addresses values
    python -m tools_py.data_via_twin --vtable 0x6691a0            # a vtable, placed by its CONTENTS

THE CONTROL. `cameraHolder 0x415ff0` is a DATA field the committed
`runtime/socom2_addresses.h` already carries an r0004 value for (`0x4429b0`), established by hand before
this tool existed. Run unchanged, this reproduces it from 60 unanimous twinned referrers -- which is what
makes the four numbers in `tools_py/parity/guest_addresses.py` worth anything.
`tools_py/tests/test_data_via_twin.py` runs it as a test.

A VTABLE is not a referenced address but a VALUE stored in an object's word 0, so no lui/lo pair forms
it and the twin scan is silent. `--vtable` places it by its CONTENTS instead: read its function-pointer
slots, translate each through `match.json`, and find the place in the r0004 image that holds the
translated pointers at the same offsets. One hit in the whole image is the answer; more than one is a
refusal.
"""
import argparse
import bisect
import csv
import json
import os
import struct
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A_ELF = os.path.join(ROOT, "game", "disc", "socom2_game.elf")
B_ELF = os.path.join(ROOT, "game", "disc_r0004", "socom2_game.elf")
A_CSV = os.path.join(ROOT, "recomp", "socom2_ghidra.csv")
MATCH = os.path.join(ROOT, "game", "r0004", "match.json")

# What the matcher is allowed to establish a twin with -- the same list addresses_from_match.ACCEPT
# carries, and for the same reason: `seed+delta` says where to look, not what was found.
ACCEPT = ("identity", "exact", "hash+callees", "relinked-body")

# The lui/lo forms the EE compiler reaches a global with. `ori` takes the low half unsigned; everything
# else sign-extends it.
LOADSTORE = {0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu", 0x25: "lhu", 0x28: "sb", 0x29: "sh",
             0x2B: "sw", 0x31: "lwc1", 0x37: "ld", 0x39: "swc1", 0x3F: "sd"}
FORMS = dict(LOADSTORE)
FORMS[0x09] = "addiu"
FORMS[0x0D] = "ori"
LUI = 0x0F
MAX_PAIR_GAP = 8        # instructions between the lui and the instruction that uses it
VTABLE_SLOTS = 12       # how many words of a vtable --vtable reads


def op(w):
    return (w >> 26) & 0x3F


def rs(w):
    return (w >> 21) & 0x1F


def rt(w):
    return (w >> 16) & 0x1F


def imm_s(w):
    v = w & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class Image:
    """An ELF's PT_LOAD segments, addressed by guest address."""

    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.d = f.read()
        d = self.d
        e_phoff = struct.unpack_from("<I", d, 0x1C)[0]
        e_phnum = struct.unpack_from("<H", d, 0x2C)[0]
        self.segs = []
        for i in range(e_phnum):
            p_type, p_off, p_vaddr, _, p_filesz, _p_memsz, p_flags = struct.unpack_from(
                "<IIIIIII", d, e_phoff + i * 32)
            if p_type == 1 and p_filesz:
                self.segs.append((p_vaddr, p_filesz, p_off, p_flags))

    def word(self, a):
        for v, sz, off, _fl in self.segs:
            if v <= a <= v + sz - 4:
                return struct.unpack_from("<I", self.d, off + (a - v))[0]
        return None

    def exec_ranges(self):
        return [(v, sz) for v, sz, _off, fl in self.segs if fl & 1]


def load_match(path=MATCH):
    with open(path) as f:
        return json.load(f)["matches"]


def load_functions(path=A_CSV):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append((int(r["Start"], 16), int(r["End"], 16), r["Name"]))
    rows.sort()
    return rows


def formed(img, hi_pc, lo_pc):
    """(address, form) the lui/lo pair at these two pcs materialises in `img`, or None."""
    hi, lo = img.word(hi_pc), img.word(lo_pc)
    if hi is None or lo is None or op(hi) != LUI:
        return None
    o = op(lo)
    if o not in FORMS:
        return None
    high = (hi & 0xFFFF) << 16
    low = (lo & 0xFFFF) if o == 0x0D else imm_s(lo)
    return (high + low) & 0xFFFFFFFF, FORMS[o]


def sites(img, target):
    """Every (hi_pc, lo_pc, form) in the image's executable segments that materialises `target`."""
    out = []
    for base, size in img.exec_ranges():
        for pc in range(base, base + size - 4, 4):
            w = img.word(pc)
            if w is None or op(w) != LUI:
                continue
            reg = rt(w)
            if reg == 0 or abs(((w & 0xFFFF)) - (target >> 16)) > 1:
                continue
            for k in range(1, MAX_PAIR_GAP + 1):
                w2 = img.word(pc + 4 * k)
                if w2 is None:
                    break
                o = op(w2)
                if o in FORMS and rs(w2) == reg:
                    got = formed(img, pc, pc + 4 * k)
                    if got and got[0] == target:
                        out.append((pc, pc + 4 * k, got[1]))
                    if o in (0x09, 0x0D) and rt(w2) == reg:
                        break       # the register now holds the formed address, not the high half
                    continue
                if o in (LUI, 0x09, 0x0D) and rt(w2) == reg:
                    break           # the register was reloaded
    return out


class Vote:
    """One r0001 referrer's answer."""

    def __init__(self, func, how, hi_pc, b_addr):
        self.func, self.how, self.hi_pc, self.b_addr = func, how, hi_pc, b_addr


def twin_votes(target, a=None, b=None, match=None, funcs=None):
    """(votes, n_sites) for one r0001 data address: what each evidence-twinned referrer says it became."""
    a = a or Image(A_ELF)
    b = b or Image(B_ELF)
    match = match if match is not None else load_match()
    funcs = funcs if funcs is not None else load_functions()
    starts = [f[0] for f in funcs]
    votes, found = [], sites(a, target)
    for hi_pc, lo_pc, form in found:
        i = bisect.bisect_right(starts, hi_pc) - 1
        if i < 0:
            continue
        fs, fe, name = funcs[i]
        if not (fs <= hi_pc < fe and fs <= lo_pc < fe):
            continue
        m = match.get("0x%08x" % fs)
        if not m or m.get("how") not in ACCEPT:
            continue
        got = formed(b, int(m["b"], 16) + (hi_pc - fs), int(m["b"], 16) + (lo_pc - fs))
        if not got or got[1] != form:
            continue
        votes.append(Vote(name, m["how"], hi_pc, got[0]))
    return votes, len(found)


def resolve(target, **kw):
    """(address, votes, n_sites) -- the unanimous answer of the twinned referrers, or None for the
    address when there are none or they disagree. A split vote fills nothing."""
    votes, n = twin_votes(target, **kw)
    tally = Counter(v.b_addr for v in votes)
    best = tally.most_common(1)
    addr = best[0][0] if len(tally) == 1 and best else None
    return addr, votes, n


def vtable_by_contents(target, a=None, b=None, match=None, slots=VTABLE_SLOTS):
    """(address, n_translated, candidates) -- a vtable placed by its function pointers. The r0001 slots
    are translated through match.json; the answer is the one place in the r0004 image that holds all of
    the translated ones at their own offsets."""
    a = a or Image(A_ELF)
    b = b or Image(B_ELF)
    match = match if match is not None else load_match()
    need = []
    for i in range(slots):
        w = a.word(target + 4 * i)
        m = match.get("0x%08x" % w) if w else None
        if m and m.get("how") in ACCEPT:
            need.append((i, int(m["b"], 16)))
    hits = []
    for v, sz, off, _fl in b.segs:
        for cand in range(v, v + sz - 4 * slots, 4):
            base = off + (cand - v)
            if all(struct.unpack_from("<I", b.d, base + 4 * i)[0] == t for i, t in need):
                hits.append(cand)
    return (hits[0] if len(hits) == 1 else None), len(need), hits


# The control, and the column this tool exists to keep honest.
CONTROL = ("cameraHolder", 0x00415FF0, 0x004429B0)
COLUMN = (("camera_record", 0x00416054, 0x00442A14, "twin"),
          ("player_actor", 0x00408C58, 0x00435618, "twin"),
          ("guest_clock", 0x004365C0, 0x00442FD0, "twin"),
          ("actor_vtable", 0x006691A0, 0x00668B20, "vtable"))


def _report(name, target, addr, votes, n, expect=None):
    tally = Counter(v.b_addr for v in votes)
    print("%-14s r0001 0x%08x -> %s   (%d sites, %d evidence-twinned%s)"
          % (name, target, ("0x%08x" % addr) if addr else "UNRESOLVED", n, len(votes),
             "; SPLIT: " + " ".join("0x%08x:%d" % kv for kv in tally.most_common()) if len(tally) > 1 else ""))
    for v in votes[:3]:
        print("                 e.g. %s (%s) hi@0x%08x -> 0x%08x" % (v.func, v.how, v.hi_pc, v.b_addr))
    if expect is not None:
        print("                 %s expected 0x%08x" % ("MATCHES" if addr == expect else "DIFFERS FROM", expect))
    return addr


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tools_py.data_via_twin", description=__doc__.split("\n")[0])
    ap.add_argument("addr", nargs="*", help="r0001 data addresses, hex")
    ap.add_argument("--control", action="store_true", help="reproduce socom2_addresses.h's cameraHolder")
    ap.add_argument("--column", action="store_true", help="the four tools_py/parity/guest_addresses values")
    ap.add_argument("--vtable", help="place a vtable by its contents instead of by its referrers")
    ap.add_argument("--a-elf", default=A_ELF)
    ap.add_argument("--b-elf", default=B_ELF)
    ap.add_argument("--match", default=MATCH)
    ap.add_argument("--csv", default=A_CSV)
    args = ap.parse_args(argv)
    if not (args.addr or args.control or args.column or args.vtable):
        ap.error("nothing to place: give an address, --control, --column or --vtable")
    a, b = Image(args.a_elf), Image(args.b_elf)
    kw = dict(a=a, b=b, match=load_match(args.match), funcs=load_functions(args.csv))
    bad = 0
    if args.control:
        name, r1, r4 = CONTROL
        got = _report(name, r1, *resolve(r1, **kw), expect=r4)
        bad += got != r4
    if args.column:
        for name, r1, r4, how in COLUMN:
            if how == "vtable":
                got, ntr, hits = vtable_by_contents(r1, a=a, b=b, match=kw["match"])
                print("%-14s r0001 0x%08x -> %s   (%d slots translated, %d candidate(s))   %s expected 0x%08x"
                      % (name, r1, ("0x%08x" % got) if got else "UNRESOLVED", ntr, len(hits),
                         "MATCHES" if got == r4 else "DIFFERS FROM", r4))
            else:
                got = _report(name, r1, *resolve(r1, **kw), expect=r4)
            bad += got != r4
    if args.vtable:
        t = int(args.vtable, 16)
        got, ntr, hits = vtable_by_contents(t, a=a, b=b, match=kw["match"])
        print("vtable 0x%08x -> %s (%d slots translated, %d candidate(s): %s)"
              % (t, ("0x%08x" % got) if got else "UNRESOLVED", ntr, len(hits),
                 " ".join("0x%08x" % h for h in hits)))
    for x in args.addr:
        _report(x, int(x, 16), *resolve(int(x, 16), **kw))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
