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
    python -m tools_py.data_via_twin --column                     # every guest_addresses r0004 value
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
          ("actor_vtable", 0x006691A0, 0x00668B20, "vtable"),
          # Sprint 11 Task 19, the online lane: scripts/parity/env.sh's PS2X_PEEK bases.
          ("net_game", 0x00437CE8, 0x004446F8, "twin"),
          ("mission_abort_valve", 0x0043668C, 0x0044309C, "twin"),
          ("mp_flag_word", 0x0045A0C0, 0x0045D480, "twin"),
          ("input_enable", 0x003DF1B0, 0x0040A378, "twin"),
          ("r7_flag", 0x0045A1C8, 0x0045D58C, "twin"),
          ("clock_string", 0x00408F10, 0x004358D0, "twin"),
          # ... and PS2X_CALL_TRACE's two FUNCTIONS, neither of which the twin scan can place.
          ("move_scale_setter", 0x00553DC0, 0x005590E0, "masked-body"),
          ("net_idle", 0x0030CD80, 0x0032A2B0, "thunk"),
          # Sprint 13 Task H6: guest_addresses.INSTRUMENT_ADDRESSES' placed r0004 cells (the audio poll's
          # statics and cam_poll's camera pointer). The cells it could NOT place are absent there, not here.
          ("cue_route", 0x0049E150, 0x004A1510, "twin"),
          ("cue_manager_ptr", 0x0049E158, 0x004A1518, "twin"),
          ("music_globals", 0x0048E080, 0x00491440, "twin"),
          ("music_off", 0x003E0080, 0x0040B250, "twin"),
          ("music_tables", 0x0048E010, 0x004913D0, "twin"),
          ("camera_ptr", 0x00488DE8, 0x0048C1B8, "twin"),
          # Sprint 13 Task O2: R221's talk-slot table pointer (the loaded controller configuration).
          ("talk_table_ptr", 0x004415A8, 0x0044DFC8, "twin"))


# ---------------------------------------------------------------------------
# TWO FUNCTIONS THE TWIN SCAN CANNOT PLACE (Sprint 11 Task 19, PS2X_CALL_TRACE).
#
# A traced FUNCTION is not a data address: no lui/lo pair materialises it, so `resolve` is silent. And
# `match.json` will not place either of these two on its own --
#
#   * `FUN_00553dc0` (SetMoveScale) is `unresolved` there, because its object displacements moved
#     (0x1368 -> 0x136c) and a body whose displacements moved is exactly a body the matcher leaves alone;
#   * `thunk_FUN_0030be80` (NetIdle) is `seed+delta`, which `ACCEPT` does not count as evidence -- a
#     two-word thunk has nothing in it for a body hash to be about.
#
# So each gets the reading its shape allows. A MASKED BODY compares the two bodies instruction for
# instruction with every load/store displacement and immediate blanked: what survives is the opcodes and
# the registers, which is what "the same function, relinked and re-displaced" means. A THUNK is placed by
# its TARGET -- the target is an ordinary function `match.json` can place by evidence -- and by being the
# only thunk to that target on either side, so there is no second one the trace could have meant.
#
# THE TWO ARE NOT EQUALLY STRONG, and the difference is worth stating (review F4). The vtable path
# asserts ONE place in the whole image; the thunk path asserts ONE thunk to the target on either side.
# The masked body asserts neither: it answers "does the r0004 address I was HANDED match the r0001 body
# under the mask", so it CONFIRMS a value somebody else derived -- for move_scale_setter that is
# `task-19-move-report.md`'s six-use displacement scan -- rather than placing one. Note also that
# MASKED_OPS blanks `addiu` and `ori` immediates, so literal constants are not compared at all; only
# `lui` survives unmasked, and this particular sixteen-instruction body contains none.
MASKED_OPS = frozenset(LOADSTORE) | {0x09, 0x0D}       # loads, stores, addiu, ori


def body_span(funcs, start):
    """(start, instruction count) of the function at `start` in the r0001 CSV, or None."""
    for s, e, _name in funcs:
        if s == start:
            return start, (e - s) // 4
    return None


def masked_body(img, start, n):
    """`n` instructions from `start` with every load/store displacement and immediate blanked, or None
    when the range is not all in the image."""
    out = []
    for i in range(n):
        w = img.word(start + 4 * i)
        if w is None:
            return None
        out.append(w & 0xFFFF0000 if op(w) in MASKED_OPS else w)
    return out


def masked_body_matches(a_img, a_start, b_img, b_start, n):
    """(equal, differing raw word offsets) for the two bodies under the mask."""
    ma, mb = masked_body(a_img, a_start, n), masked_body(b_img, b_start, n)
    if ma is None or mb is None or ma != mb:
        return False, []
    differ = [i for i in range(n) if a_img.word(a_start + 4 * i) != b_img.word(b_start + 4 * i)]
    return True, differ


def thunk_target(img, addr):
    """The target of a two-word `j <target>; nop` at `addr`, or None when that is not what is there."""
    w, delay = img.word(addr), img.word(addr + 4)
    if w is None or (w >> 26) != 2 or delay != 0:
        return None
    return ((addr + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)


def thunks_to(img, target):
    """Every address in the executable segments holding `j target; nop`."""
    out = []
    for base, size in img.exec_ranges():
        for pc in range(base, base + size - 4, 4):
            if thunk_target(img, pc) == target:
                out.append(pc)
    return out


def resolve_thunk(target, a, b, match):
    """(r0004 address or None, a sentence of evidence) for a two-word thunk, placed by its target."""
    t_a = thunk_target(a, target)
    if t_a is None:
        return None, "0x%08x is not a `j <target>; nop` thunk in r0001" % target
    row = match.get("0x%08x" % t_a) or {}
    if row.get("how") not in ACCEPT or not row.get("b"):
        return None, ("its target 0x%08x is %s in match.json, which is not evidence"
                      % (t_a, row.get("how")))
    t_b = int(row["b"], 16)
    here, there = thunks_to(a, t_a), thunks_to(b, t_b)
    if len(here) != 1 or len(there) != 1:
        return None, ("not unique: %d thunk(s) to 0x%08x in r0001, %d to 0x%08x in r0004"
                      % (len(here), t_a, len(there), t_b))
    return there[0], ("j 0x%08x -> j 0x%08x; the target is %s/%s in match.json, and the thunk is the only "
                      "one to it on either side" % (t_a, t_b, row["how"], row.get("tie")))


def _report(name, target, addr, votes, n, expect=None):
    # The unit of evidence is the referrer FUNCTION, not the materialising site (review F3): one function
    # that forms the address twice votes once, because if its twinning were wrong both of its "votes"
    # would be wrong together. Both counts are printed, and the function count is the one the
    # UNCONFIRMED rule reads.
    tally = Counter(v.b_addr for v in votes)
    print("%-20s r0001 0x%08x -> %s   (%d sites, %d evidence-twinned in %d function(s)%s)"
          % (name, target, ("0x%08x" % addr) if addr else "UNRESOLVED", n, len(votes),
             len({v.func for v in votes}),
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
    ap.add_argument("--column", action="store_true", help="every r0004 value tools_py/parity/guest_addresses carries")
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
            elif how == "thunk":
                got, note = resolve_thunk(r1, a, b, kw["match"])
                print("%-14s r0001 0x%08x -> %s   (thunk: %s)   %s expected 0x%08x"
                      % (name, r1, ("0x%08x" % got) if got else "UNRESOLVED", note,
                         "MATCHES" if got == r4 else "DIFFERS FROM", r4))
            elif how == "masked-body":
                span = body_span(kw["funcs"], r1)
                ok, differ = masked_body_matches(a, r1, b, r4, span[1]) if span else (False, [])
                got = r4 if ok else None
                print("%-14s r0001 0x%08x -> %s   (masked body: %s of %s instructions equal, %d raw "
                      "word(s) differ)   %s expected 0x%08x"
                      % (name, r1, ("0x%08x" % got) if got else "UNRESOLVED",
                         span[1] if ok and span else 0, span[1] if span else "?", len(differ),
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
