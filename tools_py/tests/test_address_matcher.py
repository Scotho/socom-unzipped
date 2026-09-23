"""Sprint 11 Task 10 Step 1 -- the fingerprint matcher (tools_py/address_matcher.py).

Given two images and their function tables, `match` answers "where did this routine go in the other
build". Every image here is SYNTHETIC: a handful of hand-assembled MIPS words laid out as fixed-size
functions, so the suite runs in CI with no disc, no ELF and no recompiler. The relocated image is the
same bytes with every absolute immediate moved by a constant, which is what a relink does.
"""
import json
import os
import shutil
import tempfile
import unittest

from tools_py import address_matcher as am


# ---- a tiny assembler ----------------------------------------------------------------------

def lui(rt, imm):        return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)
def addiu(rt, rs, imm):  return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def jal(target):         return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)
def beq(rs, rt, off):    return (0x04 << 26) | (rs << 21) | (rt << 16) | (off & 0xFFFF)
def lw(rt, base, imm):   return (0x23 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def sw(rt, base, imm):   return (0x2B << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def addu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21
def subu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x23
def jr_ra():             return (31 << 21) | 8
NOP = 0

def ori(rt, rs, imm):    return (0x0D << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)

V0, A0, A1, S0, SP, RA = 2, 4, 5, 16, 29, 31
AT, GP = 1, 28

BASE = 0x00100000          # where the synthetic image loads
DATA = 0x00400000          # a static the loader routine materialises
SIZE = 0x20                # every synthetic function is eight words
CORE = ["leafA", "leafB", "callerA", "callerB", "mathy", "loader"]


def _pad(words):
    return list(words) + [NOP] * (SIZE // 4 - len(words))


def build_image(delta=0, twins=False, call_twins=False):
    """(funcs, segments) for the synthetic image, relocated by `delta`.

    funcs is the CSV's shape -- (start, end, name) -- and segments is load_segments()'s shape.
    """
    names = list(CORE)
    if twins:
        names += ["twin1", "twin2"]
    if call_twins:
        names += ["callTwinA", "callTwinB"]
    at = {n: BASE + delta + i * SIZE for i, n in enumerate(names)}
    data = DATA + delta
    hi, lo = ((data + 0x8000) >> 16) & 0xFFFF, data & 0xFFFF

    body = {
        "leafA": [addu(V0, A0, A1), jr_ra(), NOP],
        "leafB": [subu(V0, A0, A1), jr_ra(), NOP],
        "callerA": [addiu(SP, SP, -16), sw(RA, SP, 0), jal(at["leafA"]), NOP,
                    jal(at["leafB"]), NOP, lw(RA, SP, 0), jr_ra()],
        "callerB": [addiu(SP, SP, -16), sw(RA, SP, 0), jal(at["callerA"]), NOP,
                    lw(RA, SP, 0), addiu(SP, SP, 16), jr_ra(), NOP],
        "mathy": [lw(V0, S0, 0xB4), addu(V0, V0, A0), sw(V0, S0, 0xB8),
                  beq(A0, A1, 4), NOP, subu(V0, A0, A1), jr_ra(), NOP],
        "loader": [lui(A0, hi), addiu(A0, A0, lo), lw(V0, A0, 0), jal(at["mathy"]),
                   NOP, sw(V0, A0, 4), jr_ra(), NOP],
        # Two leaves with the same body and no calls at all: the hash alone cannot tell them apart and
        # neither can their callees, so only a seed delta places them.
        "twin1": [lw(V0, A0, 0x10), addu(V0, V0, A1), jr_ra(), NOP],
        "twin2": [lw(V0, A0, 0x10), addu(V0, V0, A1), jr_ra(), NOP],
    }
    if call_twins:
        # The same body twice again, but each calls a different already-resolved leaf: the jal immediate
        # is zeroed out of the hash, so the callee is the only thing that separates them.
        body["callTwinA"] = [addiu(SP, SP, -16), sw(RA, SP, 0), jal(at["leafA"]), NOP,
                             lw(RA, SP, 0), addiu(SP, SP, 16), jr_ra(), NOP]
        body["callTwinB"] = [addiu(SP, SP, -16), sw(RA, SP, 0), jal(at["leafB"]), NOP,
                             lw(RA, SP, 0), addiu(SP, SP, 16), jr_ra(), NOP]

    blob = b"".join(w.to_bytes(4, "little") for n in names for w in _pad(body[n]))
    funcs = [(at[n], at[n] + SIZE, n) for n in names]
    return funcs, [(BASE + delta, blob)]


def build_custom(names_bodies, delta=0):
    """(funcs, segments) for an image of fixed-size functions with exactly the bodies given."""
    at = {n: BASE + delta + i * SIZE for i, (n, _b) in enumerate(names_bodies)}
    blob = b"".join(w.to_bytes(4, "little") for _n, body in names_bodies for w in _pad(body))
    funcs = [(at[n], at[n] + SIZE, n) for n, _b in names_bodies]
    return funcs, [(BASE + delta, blob)]


def replace_body(segments, funcs, name, words):
    """A copy of `segments` with `name`'s eight words overwritten (the "one function rewritten" case)."""
    start = next(s for s, _e, n in funcs if n == name)
    base, blob = segments[0]
    off = start - base
    new = bytearray(blob)
    new[off:off + SIZE] = b"".join(w.to_bytes(4, "little") for w in _pad(words))
    return [(base, bytes(new))] + list(segments[1:])


GARBAGE = [lw(V0, S0, 0x111), lw(V0, S0, 0x222), lw(V0, S0, 0x333), lw(V0, S0, 0x444),
           sw(V0, S0, 0x555), sw(V0, S0, 0x666), sw(V0, S0, 0x777), jr_ra()]

RELOC = 0x2C9C0            # the brief's ftscore delta

STRINGS = 0x00500000       # where the synthetic string pool loads
POOL = b"ALPHA\x00\x00\x00" + b"BETA\x00\x00\x00\x00"      # "ALPHA" at +0, "BETA" at +8

RELINK_CORE = ["leafA", "leafB", "common", "globalUser"]


def _hi_lo(addr):
    """The `lui` half and the sign-extended low half that together form `addr`."""
    return ((addr + 0x8000) >> 16) & 0xFFFF, addr & 0xFFFF


def build_relinked(delta=0, extras=()):
    """(funcs, segments) for an image whose bodies REACH GLOBALS AND STRINGS.

    This is the relink case the plain fingerprint cannot see: `lui $at, hi` + `lw rt, lo($at)` is how the
    EE compiler reaches a global, so for a global the load's displacement is half an address and it moves
    with the link. `tools_py/fingerprint.py` deliberately keeps load/store displacements (a struct offset
    is part of the code), so these bodies fingerprint DIFFERENTLY in the two builds however unchanged
    their instructions are -- and `exact`/`hash+callees` cannot place them.
    """
    names = list(RELINK_CORE) + list(extras)
    at = {n: BASE + delta + i * SIZE for i, n in enumerate(names)}
    ghi, glo = _hi_lo(DATA + delta)                 # a global nothing in the image spells out
    alpha, beta = STRINGS + delta, STRINGS + delta + 8

    def form(reg, addr):
        hi, lo = _hi_lo(addr)
        return [lui(reg, hi), addiu(reg, reg, lo)]

    body = {
        "leafA": [addu(V0, A0, A1), jr_ra(), NOP],
        "leafB": [subu(V0, A0, A1), jr_ra(), NOP],
        "common": [addiu(SP, SP, -16), addu(V0, A0, A1), jr_ra(), NOP],
        # One global read. Only the `lw`'s displacement moves; the `sw`'s 0x10 off s0 is a struct
        # offset and must survive the mask, or the mask is throwing away the shape of the code.
        "globalUser": [lui(AT, ghi), lw(V0, AT, glo), addu(V0, V0, A0), sw(V0, S0, 0x10), jr_ra(), NOP],
        # Two bodies the same to the last register, differing only in which leaf they call. The `jal`
        # target is zeroed out of every hash, so the callee is the only thing that separates them --
        # and the global read means no fingerprint pass ever sees them as candidates at all.
        "relTwinA": [lui(AT, ghi), lw(A1, AT, glo), jal(at["leafA"]), NOP, jr_ra(), NOP],
        "relTwinB": [lui(AT, ghi), lw(A1, AT, glo), jal(at["leafB"]), NOP, jr_ra(), NOP],
        # Same body, same callee, different string: only the bytes at the address they form tell them
        # apart.
        "strTwinA": form(A0, alpha) + [jal(at["common"]), NOP, jr_ra(), NOP],
        "strTwinB": form(A0, beta) + [jal(at["common"]), NOP, jr_ra(), NOP],
        # Same body, same callee, same string. Nothing separates these, and nothing should pretend to.
        "dupTwinA": form(A0, alpha) + [jal(at["common"]), NOP, addu(V0, A0, A1), jr_ra()],
        "dupTwinB": form(A0, alpha) + [jal(at["common"]), NOP, addu(V0, A0, A1), jr_ra()],
        # A global reached gp-relative: the displacement off $gp names the global, not a field.
        "gpUser": [lw(V0, GP, glo), addu(V0, V0, A0), sw(V0, S0, 0x24), jr_ra(), NOP],
    }
    blob = b"".join(w.to_bytes(4, "little") for n in names for w in _pad(body[n]))
    funcs = [(at[n], at[n] + SIZE, n) for n in names]
    return funcs, [(BASE + delta, blob), (STRINGS + delta, POOL)]


class TestIdentity(unittest.TestCase):
    def test_an_image_against_itself_is_one_hundred_percent_exact(self):
        funcs, segs = build_image()
        m = am.match(funcs, segs, funcs, segs)
        self.assertEqual(len(m), len(funcs))
        for start, _end, name in funcs:
            self.assertEqual(m[start], (start, "exact"), name)

    def test_the_rate_of_an_identity_run_is_one(self):
        funcs, segs = build_image()
        stats = am.summary(am.match(funcs, segs, funcs, segs))
        self.assertEqual(stats["resolved"], len(funcs))
        self.assertEqual(stats["unresolved"], 0)
        self.assertEqual(stats["rate"], 1.0)


class TestSyntheticRelocation(unittest.TestCase):
    """Every absolute immediate +0x2C9C0, bytes otherwise the same."""

    def setUp(self):
        self.a_funcs, self.a_segs = build_image(0, twins=True)
        self.b_funcs, self.b_segs = build_image(RELOC, twins=True)

    def test_it_resolves_one_hundred_percent(self):
        seeds = {DATA: DATA + RELOC}          # one static pair: 0x400000 -> 0x42c9c0
        m = am.match(self.a_funcs, self.a_segs, self.b_funcs, self.b_segs, seeds=seeds)
        self.assertEqual(len(m), len(self.a_funcs))
        for start, _end, name in self.a_funcs:
            b_addr, how = m[start]
            self.assertEqual(b_addr, start + RELOC, name)
            self.assertIn(how, ("exact", "seed+delta"), "%s: %s" % (name, how))
        self.assertEqual(am.summary(m)["unresolved"], 0)

    def test_the_twins_are_the_ones_the_seed_places(self):
        seeds = {DATA: DATA + RELOC}
        m = am.match(self.a_funcs, self.a_segs, self.b_funcs, self.b_segs, seeds=seeds)
        by_name = {n: m[s] for s, _e, n in self.a_funcs}
        self.assertEqual(by_name["leafA"][1], "exact")
        self.assertEqual(by_name["twin1"][1], "seed+delta")
        self.assertEqual(by_name["twin2"][1], "seed+delta")

    def test_without_a_seed_the_twins_are_all_that_is_left_unresolved(self):
        m = am.match(self.a_funcs, self.a_segs, self.b_funcs, self.b_segs)
        left = sorted(n for s, _e, n in self.a_funcs if m[s][1] == "unresolved")
        self.assertEqual(left, ["twin1", "twin2"])


class TestCalleeDisambiguation(unittest.TestCase):
    def test_two_identical_bodies_are_separated_by_their_callees(self):
        a_funcs, a_segs = build_image(0, call_twins=True)
        b_funcs, b_segs = build_image(RELOC, call_twins=True)
        m = am.match(a_funcs, a_segs, b_funcs, b_segs)
        by_name = {n: m[s] for s, _e, n in a_funcs}
        at_b = {n: s for s, _e, n in b_funcs}
        self.assertEqual(by_name["callTwinA"], (at_b["callTwinA"], "hash+callees"))
        self.assertEqual(by_name["callTwinB"], (at_b["callTwinB"], "hash+callees"))


class TestOneFunctionRewritten(unittest.TestCase):
    def test_exactly_that_one_is_unresolved(self):
        funcs, segs = build_image()
        b_segs = replace_body(segs, funcs, "mathy", GARBAGE)
        m = am.match(funcs, segs, funcs, b_segs)
        unresolved = [n for s, _e, n in funcs if m[s][1] == "unresolved"]
        self.assertEqual(unresolved, ["mathy"])
        self.assertIsNone(m[next(s for s, _e, n in funcs if n == "mathy")][0])
        for start, _end, name in funcs:
            if name != "mathy":
                self.assertEqual(m[start], (start, "exact"), name)


class TestSeedDeltaIsVerified(unittest.TestCase):
    """A seed is a hint, not a licence. The delta says WHERE to look; the fingerprint still has to agree,
    or one wrong seed turns the whole report into confident nonsense."""

    def test_a_wrong_seed_never_invents_a_match(self):
        a_funcs, a_segs = build_custom([
            ("one", [addu(V0, A0, A1), jr_ra()]),
            ("two", [subu(V0, A0, A1), jr_ra()]),
            ("three", [lw(V0, S0, 0xB4), addu(V0, V0, A0), jr_ra()]),
        ])
        # Three unrelated bodies, laid out so the bad delta lands exactly on a function start each time.
        b_funcs, b_segs = build_custom([
            ("alpha", [sw(V0, S0, 0x10), jr_ra()]),
            ("beta", [lw(V0, A0, 0x20), subu(V0, A0, A1), jr_ra()]),
            ("gamma", [addiu(SP, SP, -32), jr_ra()]),
        ], delta=RELOC)
        m = am.match(a_funcs, a_segs, b_funcs, b_segs, seeds={DATA: DATA + RELOC})
        for start, _end, name in a_funcs:
            self.assertEqual(m[start], (None, "unresolved"), name)
        self.assertEqual(am.summary(m)["rate"], 0.0)

    def test_a_relocated_body_at_the_seed_delta_resolves(self):
        """Two leaves with the same body: only the seed can place them, and the bytes back it up."""
        def body(data):
            hi, lo = ((data + 0x8000) >> 16) & 0xFFFF, data & 0xFFFF
            return [lui(A0, hi), addiu(A0, A0, lo), lw(V0, A0, 0), jr_ra()]

        a_funcs, a_segs = build_custom([("t1", body(DATA)), ("t2", body(DATA))])
        b_funcs, b_segs = build_custom([("t1", body(DATA + RELOC)), ("t2", body(DATA + RELOC))],
                                       delta=RELOC)
        self.assertNotEqual(a_segs[0][1], b_segs[0][1], "the bodies really were relocated, not copied")
        m = am.match(a_funcs, a_segs, b_funcs, b_segs, seeds={DATA: DATA + RELOC})
        for start, _end, name in a_funcs:
            self.assertEqual(m[start], (start + RELOC, "seed+delta"), name)

    def test_a_seed_that_lands_on_nothing_leaves_it_unresolved(self):
        a_funcs, a_segs = build_image(0, twins=True)
        b_funcs, b_segs = build_image(RELOC, twins=True)
        m = am.match(a_funcs, a_segs, b_funcs, b_segs, seeds={DATA: DATA + RELOC + 0x40})
        left = sorted(n for s, _e, n in a_funcs if m[s][1] == "unresolved")
        self.assertEqual(left, ["twin1", "twin2"])


class TestUnreadableBodies(unittest.TestCase):
    """A function row whose bytes are not in the image has no evidence at all. It must not be hashed:
    fingerprint(b"") is the FNV basis, so every such row would otherwise share one fingerprint and the
    single-occurrence rule would marry two of them as `exact`."""

    def rows_with_a_body_off_the_end(self, delta=0):
        funcs, segs = build_custom([("one", [addu(V0, A0, A1), jr_ra()]),
                                    ("two", [subu(V0, A0, A1), jr_ra()])], delta=delta)
        base, blob = segs[0]
        ghost = base + len(blob) + 0x1000            # a CSV row pointing outside every segment
        return funcs + [(ghost, ghost + SIZE, "ghost")], segs

    def test_a_body_outside_every_segment_is_unresolved(self):
        a_funcs, a_segs = self.rows_with_a_body_off_the_end()
        b_funcs, b_segs = self.rows_with_a_body_off_the_end()
        m = am.match(a_funcs, a_segs, b_funcs, b_segs)
        by_name = {n: m[s] for s, _e, n in a_funcs}
        self.assertEqual(by_name["one"][1], "exact")
        self.assertEqual(by_name["two"][1], "exact")
        self.assertEqual(by_name["ghost"], (None, "unresolved"), "no bytes, no evidence, no match")

    def test_a_seed_cannot_place_a_body_that_cannot_be_read(self):
        a_funcs, a_segs = self.rows_with_a_body_off_the_end()
        b_funcs, b_segs = self.rows_with_a_body_off_the_end()
        m = am.match(a_funcs, a_segs, b_funcs, b_segs, seeds={BASE: BASE})
        ghost = next(s for s, _e, n in a_funcs if n == "ghost")
        self.assertEqual(m[ghost], (None, "unresolved"))


class TestRelinkedBody(unittest.TestCase):
    """The fourth method: the same instruction stream relinked.

    A routine that touches a global has a different fingerprint in the two builds even when not one of
    its instructions changed, because the low half of the address lives in the load's displacement.
    `relinked-body` masks those away too, and then demands more than `exact` does: the same body length,
    a masked hash unique on BOTH sides, and -- implied by masked equality -- every differing word the
    same opcode with the same register fields, differing only in an immediate.
    """

    def pair(self, extras=()):
        return (build_relinked(0, extras), build_relinked(RELOC, extras))

    def run_match(self, extras=()):
        (a_funcs, a_segs), (b_funcs, b_segs) = self.pair(extras)
        ties = {}
        m = am.match(a_funcs, a_segs, b_funcs, b_segs, ties=ties)
        return m, ties, {n: s for s, _e, n in a_funcs}, {n: s for s, _e, n in b_funcs}

    def test_the_plain_fingerprint_really_cannot_place_these(self):
        """The premise of the whole pass: without it these bodies are unresolved, not merely slower."""
        (a_funcs, a_segs), (b_funcs, b_segs) = self.pair(("gpUser",))
        a = am._Side(a_funcs, a_segs)
        b = am._Side(b_funcs, b_segs)
        at_a = {n: s for s, _e, n in a_funcs}
        at_b = {n: s for s, _e, n in b_funcs}
        for name in ("globalUser", "gpUser"):
            self.assertNotEqual(a.fp[at_a[name]], b.fp[at_b[name]], name)

    def test_a_body_identical_after_masking_matches(self):
        m, ties, at_a, at_b = self.run_match(("gpUser",))
        for name in ("globalUser", "gpUser"):
            self.assertEqual(m[at_a[name]], (at_b[name], "relinked-body"), name)
            self.assertEqual(ties[at_a[name]], "unique", name)

    def test_a_struct_offset_is_not_masked_away(self):
        """The mask takes the address halves and nothing else. `sw v0, 0x10(s0)` is the shape of the
        code: change it and the two bodies are different routines, and must not match."""
        (a_funcs, a_segs), (b_funcs, b_segs) = self.pair()
        at_a = {n: s for s, _e, n in a_funcs}
        ghi, glo = _hi_lo(DATA + RELOC)
        moved = [lui(AT, ghi), lw(V0, AT, glo), addu(V0, V0, A0), sw(V0, S0, 0x14), jr_ra(), NOP]
        b_segs = replace_body(b_segs, b_funcs, "globalUser", moved)
        m = am.match(a_funcs, a_segs, b_funcs, b_segs)
        self.assertEqual(m[at_a["globalUser"]], (None, "unresolved"))

    def test_two_candidates_with_equal_masked_hash_resolve_by_their_callees(self):
        m, ties, at_a, at_b = self.run_match(("relTwinA", "relTwinB"))
        for name in ("relTwinA", "relTwinB"):
            self.assertEqual(m[at_a[name]], (at_b[name], "relinked-body"), name)
            self.assertEqual(ties[at_a[name]], "callees", name)

    def test_equal_callees_and_different_strings_resolve_by_the_string(self):
        m, ties, at_a, at_b = self.run_match(("strTwinA", "strTwinB"))
        for name in ("strTwinA", "strTwinB"):
            self.assertEqual(m[at_a[name]], (at_b[name], "relinked-body"), name)
            self.assertEqual(ties[at_a[name]], "string", name)

    def test_equal_everything_stays_unresolved(self):
        m, ties, at_a, _at_b = self.run_match(("dupTwinA", "dupTwinB"))
        for name in ("dupTwinA", "dupTwinB"):
            self.assertEqual(m[at_a[name]], (None, "unresolved"), name)
            self.assertNotIn(at_a[name], ties, name)

    def test_a_body_that_genuinely_changed_does_not_match(self):
        (a_funcs, a_segs), (b_funcs, b_segs) = self.pair()
        at_a = {n: s for s, _e, n in a_funcs}
        b_segs = replace_body(b_segs, b_funcs, "globalUser", GARBAGE)
        m = am.match(a_funcs, a_segs, b_funcs, b_segs)
        self.assertEqual(m[at_a["globalUser"]], (None, "unresolved"))
        for name in ("leafA", "leafB", "common"):
            self.assertEqual(m[at_a[name]][1], "exact", name)

    def test_it_runs_after_hash_callees_and_before_seed_delta(self):
        """Order is evidence: a function the earlier passes can prove keeps their `how`, and the seed
        pass only ever sees what relinked-body could not place."""
        (a_funcs, a_segs), (b_funcs, b_segs) = self.pair(("dupTwinA", "dupTwinB"))
        at_a = {n: s for s, _e, n in a_funcs}
        m = am.match(a_funcs, a_segs, b_funcs, b_segs, seeds={DATA: DATA + RELOC})
        self.assertEqual(m[at_a["leafA"]][1], "exact")
        self.assertEqual(m[at_a["globalUser"]][1], "relinked-body")
        self.assertEqual(m[at_a["dupTwinA"]][1], "seed+delta")
        self.assertEqual(am.HOWS.index("relinked-body"), am.HOWS.index("hash+callees") + 1)
        self.assertEqual(am.HOWS.index("seed+delta"), am.HOWS.index("relinked-body") + 1)

    def test_a_masked_hash_shared_on_one_side_only_is_not_unique(self):
        """`unique on both sides` means what it says: one a-body with two indistinguishable b-bodies to
        choose from proves nothing on the hash alone."""
        (a_funcs, a_segs), (b_funcs, b_segs) = self.pair(("dupTwinA",))
        b_funcs, b_segs = build_relinked(RELOC, ("dupTwinA", "dupTwinB"))
        at_a = {n: s for s, _e, n in a_funcs}
        m = am.match(a_funcs, a_segs, b_funcs, b_segs)
        self.assertEqual(m[at_a["dupTwinA"]], (None, "unresolved"))

    def test_the_identity_run_never_loses_a_function_to_the_new_pass(self):
        """The new pass must never take work away from the ones that prove more: an image against
        itself still places every function on itself, and everything `exact` could prove stays
        `exact`."""
        funcs, segs = build_relinked(0, ("relTwinA", "relTwinB", "strTwinA", "strTwinB"))
        m = am.match(funcs, segs, funcs, segs)
        for start, _end, name in funcs:
            self.assertEqual(m[start][0], start, name)
        by_name = {n: m[s][1] for s, _e, n in funcs}
        for name in ("leafA", "leafB", "common", "globalUser"):
            self.assertEqual(by_name[name], "exact", name)


class TestMaskingUnit(unittest.TestCase):
    """The mask itself, word by word -- the one place the rule is written down."""

    def words(self, code):
        return [int.from_bytes(code[i:i + 4], "little") for i in range(0, len(code), 4)]

    def masked(self, words):
        return self.words(am.mask_address_operands(b"".join(w.to_bytes(4, "little") for w in words)))

    def test_a_load_off_a_lui_register_loses_its_displacement(self):
        out = self.masked([lui(AT, 0x40), lw(V0, AT, 0x1234)])
        self.assertEqual(out[1] & 0xFFFF, 0)
        self.assertEqual(out[1] >> 16, lw(V0, AT, 0) >> 16, "opcode and registers untouched")

    def test_a_load_off_gp_loses_its_displacement(self):
        out = self.masked([lw(V0, GP, 0x1234)])
        self.assertEqual(out[0] & 0xFFFF, 0)

    def test_a_load_off_a_frame_pointer_keeps_it(self):
        out = self.masked([lw(V0, S0, 0xB4), lw(RA, SP, 0x10)])
        self.assertEqual(out[0] & 0xFFFF, 0xB4)
        self.assertEqual(out[1] & 0xFFFF, 0x10)

    def test_the_taint_ends_when_the_register_is_written_again(self):
        out = self.masked([lui(AT, 0x40), addu(AT, A0, A1), lw(V0, AT, 0xB4)])
        self.assertEqual(out[2] & 0xFFFF, 0xB4, "$at no longer holds half an address")

    def test_a_loaded_value_is_not_an_address_half(self):
        out = self.masked([lui(AT, 0x40), lw(S0, AT, 0x10), lw(V0, S0, 0xB4)])
        self.assertEqual(out[1] & 0xFFFF, 0)
        self.assertEqual(out[2] & 0xFFFF, 0xB4)

    def test_a_float_load_does_not_end_a_general_register_s_taint(self):
        """`lwc1 $f1, x($at)` writes COPROCESSOR register 1, not `$at`. Reading its `rt` as a general
        register threw the live `lui` away, and the float store to the global that followed kept half
        an address in its displacement -- which cost two real matches on the r0001/r0004 pair."""
        lwc1 = (0x31 << 26) | (SP << 21) | (AT << 16) | 0x30
        swc1 = (0x39 << 26) | (AT << 21) | (2 << 16) | 0x4D80
        out = self.masked([lui(AT, 0x4B), lwc1, swc1])
        self.assertEqual(out[2] & 0xFFFF, 0, "the store still reaches the global $at names")

    def test_a_move_from_a_coprocessor_does_end_it(self):
        mfc1 = (0x11 << 26) | (0x00 << 21) | (AT << 16)
        out = self.masked([lui(AT, 0x4B), mfc1, lw(V0, AT, 0xB4)])
        self.assertEqual(out[2] & 0xFFFF, 0xB4, "$at was written after all")

    def test_an_ori_pair_carries_the_taint(self):
        out = self.masked([lui(AT, 0x40), ori(V0, AT, 0x1234), lw(A0, V0, 0x20)])
        self.assertEqual(out[2] & 0xFFFF, 0, "v0 holds a formed address")

    def test_the_masked_hash_is_a_coarsening_of_the_fingerprint(self):
        """Anything `exact` proves, the mask still sees as equal -- so the fourth pass can never
        contradict the first."""
        body = b"".join(w.to_bytes(4, "little")
                        for w in [lui(AT, 0x40), lw(V0, AT, 0x10), addu(V0, V0, A0), jr_ra()])
        self.assertEqual(am.relinked_fingerprint(body), am.relinked_fingerprint(body))
        other = b"".join(w.to_bytes(4, "little")
                         for w in [lui(AT, 0x43), lw(V0, AT, 0xC9C0), addu(V0, V0, A0), jr_ra()])
        self.assertEqual(am.relinked_fingerprint(body), am.relinked_fingerprint(other))

    def test_the_strings_a_body_reaches_are_read_out_of_the_image(self):
        funcs, segs = build_relinked(0, ("strTwinA", "strTwinB"))
        side = am._Side(funcs, segs)
        at = {n: s for s, _e, n in funcs}
        self.assertEqual(side.anchors(at["strTwinA"]), (b"ALPHA",))
        self.assertEqual(side.anchors(at["strTwinB"]), (b"BETA",))
        self.assertEqual(side.anchors(at["globalUser"]), (), "the global holds no string")


class TestCli(unittest.TestCase):
    """The CLI over two written-out ELF32 images -- the only place a file format is involved."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="matcher_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write_pair(self, tag, funcs, segments):
        elf = os.path.join(self.dir, tag + ".elf")
        with open(elf, "wb") as fh:
            fh.write(minimal_elf32(segments))
        csv = os.path.join(self.dir, tag + ".csv")
        with open(csv, "w", newline="") as fh:
            fh.write("Name,Start,End,Size\n")
            for s, e, n in funcs:
                fh.write("%s,0x%08X,0x%08X,%d\n" % (n, s, e, e - s))
        return elf, csv

    def test_it_writes_the_matches_and_reports_the_rate(self):
        a_funcs, a_segs = build_image(0, twins=True)
        b_funcs, b_segs = build_image(RELOC, twins=True)
        a_elf, a_csv = self.write_pair("a", a_funcs, a_segs)
        b_elf, b_csv = self.write_pair("b", b_funcs, b_segs)
        out = os.path.join(self.dir, "matches.json")
        rc = am.main([a_elf, a_csv, b_elf, b_csv, "--seed", "0x%x=0x%x" % (DATA, DATA + RELOC),
                      "--out", out])
        self.assertEqual(rc, 0)
        with open(out, encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["summary"]["unresolved"], 0)
        self.assertEqual(doc["summary"]["rate"], 1.0)
        self.assertEqual(doc["matches"]["0x%08x" % (BASE)]["b"], "0x%08x" % (BASE + RELOC))

    def test_the_report_says_which_tie_breaker_placed_each_relinked_body(self):
        a_funcs, a_segs = build_relinked(0, ("relTwinA", "relTwinB", "strTwinA", "strTwinB"))
        b_funcs, b_segs = build_relinked(RELOC, ("relTwinA", "relTwinB", "strTwinA", "strTwinB"))
        a_elf, a_csv = self.write_pair("ra", a_funcs, a_segs)
        b_elf, b_csv = self.write_pair("rb", b_funcs, b_segs)
        out = os.path.join(self.dir, "relinked.json")
        self.assertEqual(am.main([a_elf, a_csv, b_elf, b_csv, "--out", out]), 0)
        with open(out, encoding="utf-8") as fh:
            doc = json.load(fh)
        at = {n: s for s, _e, n in a_funcs}
        rows = {n: doc["matches"]["0x%08x" % at[n]] for n in ("leafA", "globalUser", "relTwinA",
                                                             "strTwinB")}
        self.assertEqual(rows["leafA"]["how"], "exact")
        self.assertIsNone(rows["leafA"]["tie"])
        self.assertEqual((rows["globalUser"]["how"], rows["globalUser"]["tie"]),
                         ("relinked-body", "unique"))
        self.assertEqual((rows["relTwinA"]["how"], rows["relTwinA"]["tie"]),
                         ("relinked-body", "callees"))
        self.assertEqual((rows["strTwinB"]["how"], rows["strTwinB"]["tie"]),
                         ("relinked-body", "string"))
        self.assertEqual(doc["summary"]["relinked-body"], 5)


def minimal_elf32(segments):
    """A little-endian ELF32 with one PT_LOAD per segment -- what load_segments() reads."""
    import struct
    ehsize, phentsize = 52, 32
    phoff = ehsize
    header = bytearray(b"\x7fELF\x01\x01\x01" + b"\x00" * 9)
    header += struct.pack("<HHI", 2, 8, 1)                       # ET_EXEC, EM_MIPS, EV_CURRENT
    header += struct.pack("<III", segments[0][0], phoff, 0)      # entry, phoff, shoff
    header += struct.pack("<IHHHHHH", 0, ehsize, phentsize, len(segments), 40, 0, 0)
    body, off = b"", phoff + phentsize * len(segments)
    phdrs = b""
    for vaddr, data in segments:
        phdrs += struct.pack("<8I", 1, off + len(body), vaddr, vaddr, len(data), len(data), 5, 0x10)
        body += data
    return bytes(header) + phdrs + body


if __name__ == "__main__":
    unittest.main()
