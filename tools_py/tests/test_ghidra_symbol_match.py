"""Sprint 11 Task 7 (U3) -- pairing the demo's named functions with ours (tools_py/ghidra_symbol_match).

The fixture is the brief's: two little images whose functions are hand-assembled MIPS words. One
function is byte-identical in both; one is the same code RELOCATED (the same stream with the `lui`/
`addiu` halves of an address moved, which is all a second link does to it); one reaches a global, so
its load displacement moves too and only the relinked-body pass can see through it; and each side has
a function the other does not, which must match nothing. No disc, no ELF, no demo needed.
"""
import contextlib
import csv
import io
import json
import os
import shutil
import struct
import tempfile
import unittest

from tools_py import ghidra_symbol_match as gsm


# ---- a tiny assembler (the same shapes as test_address_matcher's) --------------------------

def lui(rt, imm):        return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)
def addiu(rt, rs, imm):  return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def ori(rt, rs, imm):    return (0x0D << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def jal(target):         return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)
def lw(rt, base, imm):   return (0x23 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def sw(rt, base, imm):   return (0x2B << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def addu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21
def subu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x23
def xor(rd, rs, rt):     return (rs << 21) | (rt << 16) | (rd << 11) | 0x26
def mult(rs, rt):        return (rs << 21) | (rt << 16) | 0x18
def jr_ra():             return (31 << 21) | 8
NOP = 0

AT, V0, A0, A1, S0, T0, RA = 1, 2, 4, 5, 16, 8, 31


def _how(details, name):
    """The pass of the one pair carrying `name` -- `details` is keyed by (name, our address)."""
    hits = [v["how"] for (n, _a), v in details.items() if n == name]
    assert len(hits) == 1, hits
    return hits[0]
SIZE = 0x40                       # sixteen words: long enough to score at full weight
TINY = 0x08                       # two words: a thunk, which scores a quarter of that


def _pad(words, size=SIZE):
    return list(words) + [NOP] * (size // 4 - len(words))


def _blob(words):
    return b"".join(w.to_bytes(4, "little") for w in words)


def build(base, data, variant=0):
    """(rows, segments) for one image: four named functions of `SIZE` bytes plus one thunk.

    `base` is where the image loads, `data` is where its one global lives. Moving both is what a
    relink does; nothing about the code itself changes between the two images this returns.
    """
    order = ["identical", "relocated", "viaglobal", "onlyhere", "thunk"]
    at = {}
    cursor = base
    for name in order:
        at[name] = cursor
        cursor += TINY if name == "thunk" else SIZE
    hi, lo = ((data + 0x8000) >> 16) & 0xFFFF, data & 0xFFFF

    body = {
        # Pure register arithmetic: not one bit of this moves between links.
        "identical": _pad([addu(V0, A0, A1), subu(V0, V0, A0), xor(A1, V0, A0),
                           mult(V0, A1), addu(V0, V0, A1), subu(A0, A1, V0), jr_ra()]),
        # An address materialised into a register, and a call: every address word here moves.
        "relocated": _pad([lui(AT, hi), addiu(A0, AT, lo), jal(at["identical"]), NOP,
                           ori(A1, A0, 0x40), addu(V0, A0, A1), jr_ra()]),
        # A load and a store THROUGH the global's address: the displacement is half an address, so
        # the plain fingerprint differs between the images and only the masked one agrees.
        "viaglobal": _pad([lui(AT, hi), lw(V0, AT, lo), addiu(V0, V0, 1), lui(AT, hi),
                           sw(V0, AT, lo), lw(T0, A0, 0x18), addu(V0, V0, T0), jr_ra()]),
        "thunk": _pad([jr_ra(), NOP], TINY),
    }
    # Deliberately different code on each side, under a name the other side does not use.
    body["onlyhere"] = _pad([xor(V0, A0, A0), addu(V0, V0, V0), subu(S0, A0, A1),
                             mult(A0, A1), xor(S0, S0, V0), jr_ra()]
                            if variant == 0 else
                            [mult(A1, A1), subu(V0, A1, A0), addu(S0, V0, V0),
                             xor(A0, S0, A1), addu(V0, A0, S0), jr_ra()])

    rows, segs = [], []
    for name in order:
        blob = _blob(body[name])
        rows.append((at[name], at[name] + len(blob), name, blob))
        segs.append((at[name], blob))
    return rows, segs


DEMO_BASE, DEMO_DATA = 0x00140000, 0x00500124
OUR_BASE, OUR_DATA = 0x00280000, 0x00610ab8


def demo_side():
    return build(DEMO_BASE, DEMO_DATA)


def our_side():
    # A different load address and a different global: a second link, with `onlyhere` replaced by a
    # routine that is not in the demo at all.
    rows, segs = build(OUR_BASE, OUR_DATA, variant=1)
    renamed = [(s, e, "FUN_%08x" % s, c) for s, e, _n, c in rows]
    return renamed, segs


class ScoreTest(unittest.TestCase):
    def test_a_long_body_scores_its_method_in_full(self):
        self.assertEqual(gsm.score_of("exact", 0x100), 1.0)
        self.assertEqual(gsm.score_of("exact", 64), 1.0)

    def test_a_short_body_is_discounted(self):
        self.assertEqual(gsm.size_weight(8), 0.25)
        self.assertLess(gsm.score_of("exact", 8), gsm.score_of("exact", 64))
        self.assertLess(gsm.score_of("relinked-body", 64), gsm.score_of("exact", 64))

    def test_no_weight_can_lift_a_pass_above_its_method_score(self):
        # The prefix pass is under the rename line because 0.70 x 1.0 < 0.80. That stays true only
        # while no size weight exceeds 1.0 -- assert the premise, not just the conclusion.
        self.assertLessEqual(max(w for _floor, w in gsm.SIZE_WEIGHTS), 1.0)
        self.assertLess(max(gsm.METHOD_SCORE["prefix"], gsm.METHOD_SCORE["prefix+size"]), gsm.GOOD)


class MatchTest(unittest.TestCase):
    def setUp(self):
        demo_rows, _ = demo_side()
        our_rows, _ = our_side()
        self.details = {}
        self.pairs = gsm.match(demo_rows, our_rows, details=self.details)
        self.hows = {name: self.details[(name, addr)]["how"] for name, addr, _s in self.pairs}
        self.by_name = {name: (addr, score) for name, addr, score in self.pairs}
        self.our_at = {name: start for start, _e, name, _c in build(OUR_BASE, OUR_DATA, variant=1)[0]}

    def test_the_byte_identical_function_matches(self):
        self.assertIn("identical", self.by_name)
        self.assertEqual(self.by_name["identical"][0], self.our_at["identical"])
        self.assertEqual(self.hows["identical"], "exact")
        self.assertEqual(self.by_name["identical"][1], 1.0)

    def test_the_relocated_function_matches(self):
        self.assertIn("relocated", self.by_name)
        self.assertEqual(self.by_name["relocated"][0], self.our_at["relocated"])

    def test_the_global_toucher_needs_the_relinked_body_pass(self):
        self.assertIn("viaglobal", self.by_name)
        self.assertEqual(self.by_name["viaglobal"][0], self.our_at["viaglobal"])
        self.assertEqual(self.hows["viaglobal"], "relinked-body")

    def test_the_unrelated_function_matches_nothing(self):
        self.assertNotIn("onlyhere", self.by_name)
        self.assertNotIn(self.our_at["onlyhere"], [a for _n, a, _s in self.pairs])

    def test_a_thunk_matches_but_is_scored_low(self):
        # `jr $ra; nop` is the same in every program ever compiled. It is only here because it is
        # unique on both sides; the score is what says not to rename anything on it.
        self.assertIn("thunk", self.by_name)
        self.assertLessEqual(self.by_name["thunk"][1], 0.25)

    def test_min_score_drops_the_weak_pairs(self):
        demo_rows, _ = demo_side()
        our_rows, _ = our_side()
        strong = gsm.match(demo_rows, our_rows, min_score=gsm.GOOD)
        self.assertNotIn("thunk", [n for n, _a, _s in strong])
        self.assertIn("identical", [n for n, _a, _s in strong])

    def test_every_pairing_is_one_to_one(self):
        coll = gsm.collisions(self.pairs)
        self.assertEqual(coll["names"], [])
        self.assertEqual(coll["addrs"], [])

    def test_rows_may_carry_segments_instead_of_bytes(self):
        demo_rows, demo_segs = demo_side()
        our_rows, our_segs = our_side()
        bare_demo = [(s, e, n) for s, e, n, _c in demo_rows]
        bare_ours = [(s, e, n) for s, e, n, _c in our_rows]
        again = gsm.match(bare_demo, bare_ours, demo_segs, our_segs)
        self.assertEqual(again, self.pairs)


class CollisionTest(unittest.TestCase):
    def test_one_name_on_two_addresses_is_reported(self):
        coll = gsm.collisions([("a", 0x10, 1.0), ("a", 0x20, 1.0), ("b", 0x30, 1.0)])
        self.assertEqual(coll["names"], [("a", [0x10, 0x20])])
        self.assertEqual(coll["addrs"], [])

    def test_two_names_on_one_address_is_reported(self):
        coll = gsm.collisions([("a", 0x10, 1.0), ("b", 0x10, 1.0)])
        self.assertEqual(coll["addrs"], [(0x10, ["a", "b"])])


class PrefixPassTest(unittest.TestCase):
    """The opt-in fourth pass: a routine EDITED between the two games, found by its prologue."""

    PROLOGUE = [addiu(29, 29, -0x30), sw(RA, 29, 0x20), sw(S0, 29, 0x18), addu(S0, A0, 0),
                lw(V0, S0, 0x0C), addu(A0, V0, 0), subu(A1, A1, A0), xor(T0, A0, A1),
                mult(V0, T0), addu(V0, V0, T0), subu(T0, V0, A1), xor(A0, T0, V0),
                addu(A1, A0, T0), subu(V0, A1, A0), mult(A0, A1), addu(V0, V0, A0)]

    def _sides(self, tail_len):
        """Two images: `edited` shares a prologue and differs after it; `same` is identical."""
        same = _pad([addu(V0, A0, A1), subu(V0, V0, A0), xor(A1, V0, A0), mult(V0, A1),
                     addu(V0, V0, A1), subu(A0, A1, V0), jr_ra()])

        def image(base, tail_word, tail_words):
            edited = self.PROLOGUE + [tail_word] * tail_words + [jr_ra(), NOP]
            rows = []
            at = base
            for name, words in (("edited", edited), ("same", same)):
                blob = _blob(words)
                rows.append((at, at + len(blob), name, blob))
                at += len(blob) + 0x10
            return rows

        demo = image(0x00140000, addu(S0, S0, V0), 16)
        ours = image(0x00280000, subu(S0, V0, S0), tail_len)
        return demo, [(s, e, "FUN_%08x" % s, c) for s, e, _n, c in ours]

    def test_off_by_default(self):
        demo, ours = self._sides(16)
        self.assertNotIn("edited", [n for n, _a, _s in gsm.match(demo, ours)])

    def test_an_edited_body_is_found_by_its_prologue(self):
        demo, ours = self._sides(24)
        details = {}
        pairs = gsm.match(demo, ours, details=details, prefix=True)
        self.assertIn("edited", [n for n, _a, _s in pairs])
        self.assertEqual(_how(details, "edited"), "prefix")
        self.assertEqual(dict((n, s) for n, _a, s in pairs)["edited"], 0.6)

    def test_an_equal_length_body_says_so(self):
        demo, ours = self._sides(16)
        details = {}
        pairs = gsm.match(demo, ours, details=details, prefix=True)
        self.assertEqual(_how(details, "edited"), "prefix+size")
        self.assertEqual(dict((n, s) for n, _a, s in pairs)["edited"], 0.7)

    def test_a_prefix_pair_can_never_reach_the_rename_line(self):
        demo, ours = self._sides(16)
        strong = gsm.match(demo, ours, min_score=gsm.GOOD, prefix=True)
        self.assertNotIn("edited", [n for n, _a, _s in strong])
        self.assertLess(max(gsm.METHOD_SCORE["prefix"], gsm.METHOD_SCORE["prefix+size"]), gsm.GOOD)


# ---- the proposals file --------------------------------------------------------------------

def _details(pairs, how="exact", size=64):
    return {(n, a): {"how": how, "size": size, "demo_addr": 0x1000 + i}
            for i, (n, a, _s) in enumerate(pairs)}


class IdentifierTest(unittest.TestCase):
    def test_a_plain_name_is_left_alone(self):
        self.assertEqual(gsm.c_identifier("Mul__5CQuatCFPC5CQuatP5CQuat"),
                         "Mul__5CQuatCFPC5CQuatP5CQuat")

    def test_template_and_anonymous_namespace_forms_become_legal(self):
        for raw in ("swap__Q23std30vector<b,Q23std12allocator<b>>FRv",
                    "SetButtonState__Q221@unnamed@zui_skb_cpp@12CSkbKeyProps",
                    "__sinit_ent_main.cpp"):
            self.assertRegex(gsm.c_identifier(raw), r"\A[A-Za-z_][A-Za-z0-9_]*\Z")

    def test_a_leading_digit_is_prefixed(self):
        self.assertEqual(gsm.c_identifier("2DThing"), "_2DThing")

    def test_a_long_name_is_cut_and_hashed_deterministically(self):
        a, b = "x" * 200 + "_alpha", "x" * 200 + "_beta"
        self.assertLessEqual(len(gsm.c_identifier(a)), gsm.IDENT_LIMIT)
        self.assertEqual(gsm.c_identifier(a), gsm.c_identifier(a))
        self.assertNotEqual(gsm.c_identifier(a), gsm.c_identifier(b))


class EngineFilterTest(unittest.TestCase):
    def test_a_mangled_member_and_a_z_function_are_engine(self):
        self.assertTrue(gsm.is_engine("Init__8CMissionFv"))
        self.assertTrue(gsm.is_engine("zAnimGetDirection__Ff"))
        self.assertTrue(gsm.is_engine("hudInit__Fv"))

    def test_the_sdk_and_the_runtime_are_not(self):
        for raw in ("sceGsSyncPath", "__ieee754_sqrt", "_printf", "strncmp", "memclr"):
            self.assertFalse(gsm.is_engine(raw), raw)


class AnonymityTest(unittest.TestCase):
    def test_a_ghidra_placeholder_may_be_taken_over(self):
        self.assertTrue(gsm.is_anonymous("FUN_001801c8"))
        self.assertTrue(gsm.is_anonymous("thunk_FUN_001801c8"))

    def test_a_name_a_human_chose_may_not(self):
        for raw in ("entry", "AddDmacHandler", "CZNetGame_Tick", ""):
            self.assertFalse(gsm.is_anonymous(raw), raw)


class ProposalsTest(unittest.TestCase):
    OURS = {0x1000: "FUN_00001000", 0x2000: "FUN_00002000", 0x3000: "CustomNameSetByHand"}

    def test_a_clean_pair_is_proposed(self):
        pairs = [("Init__8CMissionFv", 0x1000, 1.0)]
        rows, held = gsm.proposals(pairs, _details(pairs), self.OURS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Proposed"], "Init__8CMissionFv")
        self.assertEqual(rows[0]["Mangled"], "Init__8CMissionFv")
        self.assertEqual(rows[0]["Address"], "0x00001000")
        self.assertEqual(held, {})

    def test_a_two_address_name_never_reaches_the_file(self):
        pairs = [("_request_end", 0x1000, 1.0), ("_request_end", 0x2000, 1.0)]
        rows, held = gsm.proposals(pairs, _details(pairs), self.OURS)
        self.assertEqual(rows, [])
        self.assertEqual(held["colliding demo name"], 2)

    def test_a_short_body_is_held_back_even_at_the_score_line(self):
        pairs = [("Tiny__5CThngFv", 0x1000, 0.8)]
        rows, held = gsm.proposals(pairs, _details(pairs, size=32), self.OURS)
        self.assertEqual(rows, [])
        self.assertEqual(held["body under 64 bytes"], 1)
        # The score line on its own would have admitted it -- that is why there are two rules.
        self.assertEqual(gsm.score_of("exact", 32), gsm.GOOD)

    def test_a_prefix_pair_is_refused_outright(self):
        pairs = [("Init__8CMissionFv", 0x1000, 0.7)]
        rows, held = gsm.proposals(pairs, _details(pairs, how="prefix+size", size=4096),
                                   self.OURS, good=0.0, min_size=0)
        self.assertEqual(rows, [])
        self.assertEqual(held["prefix pass"], 1)

    def test_a_row_we_named_by_hand_keeps_its_name(self):
        pairs = [("Init__8CMissionFv", 0x3000, 1.0)]
        rows, held = gsm.proposals(pairs, _details(pairs), self.OURS)
        self.assertEqual(rows, [])
        self.assertEqual(held["our row is already named"], 1)

    def test_two_names_that_sanitise_alike_are_both_dropped(self):
        pairs = [("f<a>", 0x1000, 1.0), ("f_a_", 0x2000, 1.0)]
        rows, held = gsm.proposals(pairs, _details(pairs), self.OURS)
        self.assertEqual(rows, [])
        self.assertEqual(held["identifier collides after sanitising"], 2)

    def test_every_proposed_name_is_a_legal_identifier(self):
        pairs = [("swap__Q23std30vector<b>FRv", 0x1000, 1.0)]
        rows, _held = gsm.proposals(pairs, _details(pairs), self.OURS)
        self.assertRegex(rows[0]["Proposed"], r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
        self.assertEqual(rows[0]["Mangled"], "swap__Q23std30vector<b>FRv")


# ---- the CLI -------------------------------------------------------------------------------

def _elf(base, blob, symbols=()):
    """A little-endian ELF32 holding `blob` at `base`, with an optional `.symtab`."""
    strtab = b"\0"
    offsets = {}
    for name, _addr, _size in symbols:
        offsets[name] = len(strtab)
        strtab += name.encode() + b"\0"
    symtab = struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0)
    for name, addr, size in symbols:
        symtab += struct.pack("<IIIBBH", offsets[name], addr, size, 2, 0, 1)
    shstr = b"\0.shstrtab\0.strtab\0.symtab\0main\0"
    names = {n: shstr.index(b"\0" + n.encode() + b"\0") + 1
             for n in (".shstrtab", ".strtab", ".symtab", "main")}

    off = 52 + 32
    blobs, offs = [blob, shstr, strtab, symtab], []
    for part in blobs:
        offs.append(off)
        off += len(part)
    sh_off = off

    def shdr(name, type_, flags, addr, offset, size, link=0, entsize=0):
        return struct.pack("<10I", name, type_, flags, addr, offset, size, link, 0, 4, entsize)

    sections = b"".join([
        shdr(0, 0, 0, 0, 0, 0),
        shdr(names["main"], 1, 7, base, offs[0], len(blob)),
        shdr(names[".shstrtab"], 3, 0, 0, offs[1], len(shstr)),
        shdr(names[".strtab"], 3, 0, 0, offs[2], len(strtab)),
        shdr(names[".symtab"], 2, 0, 0, offs[3], len(symtab), link=3, entsize=16),
    ])
    ehdr = bytearray(52)
    ehdr[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HHI", ehdr, 16, 2, 8, 1)
    struct.pack_into("<III", ehdr, 24, base, 52, sh_off)
    struct.pack_into("<HHHHHH", ehdr, 40, 52, 32, 1, 40, 5, 2)
    phdr = struct.pack("<8I", 1, offs[0], base, base, len(blob), len(blob), 5, 16)
    return bytes(ehdr) + phdr + b"".join(blobs) + sections


class CliTest(unittest.TestCase):
    """`main()` end to end, on files -- the proposals file is written by main, not by match."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        demo_rows, _ = demo_side()
        our_rows, _ = our_side()
        self.demo = os.path.join(self.dir, "demo.elf")
        self.ours = os.path.join(self.dir, "ours.elf")
        self.csv = os.path.join(self.dir, "ours.csv")
        with open(self.demo, "wb") as fh:
            fh.write(_elf(DEMO_BASE, b"".join(r[3] for r in demo_rows),
                          [(r[2], r[0], r[1] - r[0]) for r in demo_rows]))
        with open(self.ours, "wb") as fh:
            fh.write(_elf(OUR_BASE, b"".join(r[3] for r in our_rows)))
        with open(self.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Name", "Start", "End", "Size"])
            for start, end, name, _code in our_rows:
                # The first row is named by hand, so `_is_anonymous` has something to skip.
                if start == our_rows[0][0]:
                    name = "NamedByHand"
                w.writerow([name, "0x%08X" % start, "0x%08X" % end, end - start])
        self.renames = os.path.join(self.dir, "renames.csv")
        self.json = os.path.join(self.dir, "out.json")

    def run_cli(self, *extra):
        argv = [self.demo, self.ours, self.csv, "--renames", self.renames, "--out", self.json,
                "--top", "0"] + list(extra)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(gsm.main(argv), 0)
        with open(self.renames, newline="") as fh:
            return list(csv.DictReader(fh))

    def test_the_header_is_the_documented_one(self):
        self.run_cli()
        with open(self.renames, newline="") as fh:
            self.assertEqual(next(csv.reader(fh)), gsm.PROPOSAL_COLUMNS)

    def test_no_prefix_row_reaches_the_file(self):
        rows = self.run_cli("--prefix")
        self.assertTrue(rows)
        self.assertFalse([r for r in rows if r["How"].startswith("prefix")])

    def test_a_hand_named_row_is_not_proposed(self):
        rows = self.run_cli()
        self.assertNotIn("NamedByHand", [r["Current"] for r in rows])
        self.assertTrue(all(r["Current"].startswith("FUN_") for r in rows))

    def test_every_written_row_clears_both_rules(self):
        rows = self.run_cli("--prefix")
        self.assertTrue(rows)
        for row in rows:
            self.assertGreaterEqual(float(row["Score"]), gsm.GOOD)
            self.assertGreaterEqual(int(row["Size"]), gsm.PROPOSE_MIN_SIZE)

    def test_good_cannot_be_lowered_under_the_prefix_scores(self):
        rows = self.run_cli("--prefix", "--good", "0.1", "--min-size", "0")
        self.assertFalse([r for r in rows if r["How"].startswith("prefix")])
        self.assertTrue(all(int(r["Size"]) >= gsm.PROPOSE_MIN_SIZE for r in rows))

    def test_the_json_carries_the_proposal_count(self):
        self.run_cli()
        with open(self.json) as fh:
            payload = json.load(fh)
        self.assertEqual(payload["matched"], len(payload["pairs"]))
        self.assertIn("proposals", payload)
        self.assertIn("held_back", payload)

    def test_a_missing_input_is_a_sentence_and_exit_2(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gsm.main([os.path.join(self.dir, "nope.elf"), self.ours, self.csv])
        self.assertEqual(code, 2)
        self.assertIn("NO-DATA: missing", out.getvalue())

    def test_a_file_that_is_not_an_elf_is_a_sentence_and_exit_2(self):
        junk = os.path.join(self.dir, "junk.elf")
        with open(junk, "wb") as fh:
            fh.write(b"MZ" + bytes(128))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gsm.main([junk, self.ours, self.csv])
        self.assertEqual(code, 2)
        self.assertIn("NO-DATA:", out.getvalue())

    def test_verify_and_engine_modes_run(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            gsm.main([self.demo, self.ours, self.csv, "--verify", "--engine", "--top", "5"])
        text = out.getvalue()
        self.assertIn("exact-fingerprint buckets", text)
        self.assertIn("relocated words inside a demo function body", text)


class VerifyHelpersTest(unittest.TestCase):
    def test_class_of_reads_the_metrowerks_length_prefix(self):
        self.assertEqual(gsm.class_of("Init__8CMissionFv"), "CMission")
        self.assertEqual(gsm.class_of("Mul__5CQuatCFPC5CQuatP5CQuat"), "CQuat")
        self.assertIsNone(gsm.class_of("sceGsSyncPath"))

    def test_class_clusters_reports_span_and_ignores_singletons(self):
        pairs = [("A__8CMissionFv", 0x1000, 1.0), ("B__8CMissionFv", 0x1100, 1.0),
                 ("C__8CMissionFv", 0x1200, 1.0), ("D__5CQuatFv", 0x9000, 1.0)]
        self.assertEqual(gsm.class_clusters(pairs), [("CMission", 3, 0x1000, 0x1200)])

    def test_the_region_split_accounts_for_every_pair(self):
        demo_rows, demo_segs = demo_side()
        our_rows, our_segs = our_side()
        details = {}
        pairs = gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details, prefix=True)
        split = gsm.region_split(pairs, details, our_segs)
        self.assertEqual(sum(total for _v, _e, total, _p in split), len(pairs))
        self.assertLessEqual(sum(pre for _v, _e, _t, pre in split), len(pairs))

    def test_the_table_census_counts_hand_named_and_bodiless_rows(self):
        our_rows, our_segs = our_side()
        rows = [(s, e, n, c) for s, e, n, c in our_rows]
        rows[0] = (rows[0][0], rows[0][1], "NamedByHand", rows[0][3])
        rows.append((0x900000, 0x900010, "FUN_00900000", None))   # outside every segment
        census = gsm.table_census(rows, our_segs)
        self.assertEqual(census["rows"], len(rows))
        self.assertEqual(census["named_by_hand"], 1)
        self.assertEqual(census["without_bytes"], 1)

    def test_buckets_and_the_histogram_partition_the_demo(self):
        demo_rows, demo_segs = demo_side()
        our_rows, our_segs = our_side()
        details = {}
        pairs = gsm.match(demo_rows, our_rows, demo_segs, our_segs, details=details)
        buckets = gsm.fingerprint_buckets(demo_rows, demo_segs, our_rows, our_segs, details)
        self.assertEqual(sum(total for total, _placed in buckets.values()), len(demo_rows))
        self.assertEqual(sum(placed for _total, placed in buckets.values()), len(pairs))
        hist = gsm.small_body_histogram(demo_rows, demo_segs, our_rows, our_segs)
        self.assertEqual(hist["total"], buckets["ambiguous"][0])


if __name__ == "__main__":
    unittest.main()
