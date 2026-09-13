"""Sprint 5 Task 4 Step 2 -- unit tests for the HLE stub consumer census.

unittest only (no pytest). Every test runs over synthetic bytes: a hand-assembled MIPS buffer, and
for the ELF/CLI paths a minimal ELF32 with one PT_LOAD, written under a fresh temp dir.
"""
import contextlib
import io
import os
import shutil
import struct
import tempfile
import unittest

from tools_py import hle_constants as hc

BASE = 0x00100000
STUB = 0x00100400          # the bound stub's address in every synthetic image
OTHER = 0x00100800         # some unrelated function


# ---- a tiny assembler ----------------------------------------------------------------------

def jal(t): return (3 << 26) | (t >> 2)
def j(t): return (2 << 26) | (t >> 2)
NOP = 0
def beqz(rs, off=4): return (4 << 26) | (rs << 21) | (off & 0xFFFF)
def beq(rs, rt, off=4): return (4 << 26) | (rs << 21) | (rt << 16) | (off & 0xFFFF)
def b(off): return (4 << 26) | (off & 0xFFFF)
def sw(rt, base, imm=0): return (43 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def lw(rt, base, imm=0): return (35 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def addiu(rt, rs, imm): return (9 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def sltiu(rt, rs, imm): return (11 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def addu(rd, rs, rt): return (rs << 21) | (rt << 16) | (rd << 11) | 33
def move(rd, rs): return (rs << 21) | (rd << 11) | 45              # daddu rd, rs, $zero
def movz(rd, rs, rt): return (rs << 21) | (rt << 16) | (rd << 11) | 10
def jr_ra(): return (31 << 21) | 8
def swc1(ft, base, imm=0): return (57 << 26) | (base << 21) | (ft << 16) | (imm & 0xFFFF)

V0, V1, A0, S0, S1, SP = 2, 3, 4, 16, 17, 29


def image_of(words, base=BASE):
    return hc.Image([(base, struct.pack("<%dI" % len(words), *words))])


def classify_after_call(tail_words, is_float=False):
    """jal STUB at BASE, delay-slot nop, then `tail_words`, padded with nops."""
    words = [jal(STUB), NOP] + list(tail_words) + [NOP] * 16
    img = image_of(words)
    return hc.classify(img.read_word, BASE, is_float)


class Classification(unittest.TestCase):
    def test_zero_test(self):
        self.assertEqual(classify_after_call([beqz(V0)])[0], "zero-test")

    def test_sltiu_one_is_a_zero_test_not_a_constant_compare(self):
        # strcmp's `== 0` idiom: xor/sltiu 1. Magnitude never reaches the guest.
        self.assertEqual(classify_after_call([sltiu(V0, V0, 1), beqz(V0)])[0], "zero-test")

    def test_movz_condition_is_a_zero_test(self):
        self.assertEqual(classify_after_call([addiu(V1, 0, 11), movz(A0, V1, V0)])[0], "zero-test")

    def test_stored(self):
        self.assertEqual(classify_after_call([sw(V0, SP, 8)])[0], "stored")

    def test_deref(self):
        self.assertEqual(classify_after_call([lw(V1, V0, 4)])[0], "deref")

    def test_arithmetic_wins_over_a_later_zero_test(self):
        cls, uses, _ = classify_after_call([addu(V1, V0, A0), beqz(V0)])
        self.assertEqual(cls, "arithmetic")
        self.assertIn("zero-test", uses)

    def test_const_compare_against_a_loaded_constant(self):
        self.assertEqual(classify_after_call([addiu(V1, 0, 0x14), beq(V0, V1)])[0], "const-compare")

    def test_var_compare_against_an_unknown_register(self):
        self.assertEqual(classify_after_call([beq(V0, S1)])[0], "var-compare")

    def test_overwritten_before_use_is_ignored(self):
        self.assertEqual(classify_after_call([addiu(V0, 0, 5), jr_ra(), NOP])[0], "ignored")

    def test_register_copy_is_unresolved_with_a_hint(self):
        cls, _, hint = classify_after_call([move(S0, V0), addiu(V0, 0, 0), beqz(S0)])
        self.assertEqual(cls, "unresolved")
        self.assertIn("s0->zero-test", hint)

    def test_copy_overwritten_after_its_use_keeps_the_hint(self):
        # xor s4,v0,$zero ; sltiu s4,s4,1 -- the copy is consumed then replaced.
        cls, _, hint = classify_after_call([move(S0, V0), sltiu(S0, S0, 1), addiu(V0, 0, 0), jr_ra(), NOP])
        self.assertEqual(cls, "unresolved")
        self.assertIn("s0->zero-test", hint)

    def test_returned_value_is_unresolved_consumer_upstream(self):
        cls, _, hint = classify_after_call([jr_ra(), NOP])
        self.assertEqual(cls, "unresolved")
        self.assertIn("upstream", hint)

    def test_unconditional_b_is_followed(self):
        # b over one garbage word to a zero test
        self.assertEqual(classify_after_call([b(2), NOP, sw(V0, SP), beqz(V0)])[0], "zero-test")

    def test_conditional_branch_before_use_is_unresolved(self):
        self.assertEqual(classify_after_call([beqz(S1), NOP, beqz(V0)])[0], "unresolved")

    def test_float_return_stored(self):
        self.assertEqual(classify_after_call([swc1(0, SP)], is_float=True)[0], "stored")


class Census(unittest.TestCase):
    def build(self):
        words = [NOP] * 0x400
        words[0x010 // 4] = jal(STUB)             # direct site in function A
        words[0x018 // 4] = beqz(V0)
        words[0x100 // 4] = j(STUB)               # tail site in function B
        words[0x404 // 4] = jal(OTHER)            # inside the stub's own body: dead
        words[0x300 // 4] = STUB                  # a data word holding the address
        words[0x600 // 4] = jal(STUB | 0x4)       # a call to a different address: not a site
        return image_of(words)

    def test_sites_tail_dead_and_address_taken(self):
        funcs = hc.FunctionIndex([(BASE, BASE + 0x100, "A"), (BASE + 0x100, BASE + 0x200, "B"),
                                  (STUB, STUB + 0x100, "stub"), (OTHER, OTHER + 0x10, "other")])
        stubs = [("stub", STUB), ("other", OTHER)]
        sites, taken = hc.census(self.build(), stubs, funcs)
        s = {x.addr: x for x in sites["stub"]}
        self.assertEqual(sorted(s), [BASE + 0x10, BASE + 0x100])
        self.assertEqual((s[BASE + 0x10].kind, s[BASE + 0x10].cls, s[BASE + 0x10].func), ("direct", "zero-test", "A"))
        self.assertEqual((s[BASE + 0x100].kind, s[BASE + 0x100].cls), ("tail", "tail"))
        self.assertEqual(taken["stub"], 1)
        other = sites["other"]
        self.assertEqual(len(other), 1)
        self.assertTrue(other[0].dead)
        self.assertEqual(hc.summarize(other), {"dead": 1})


def elf32(vaddr, code):
    phoff, off = 52, 0x100
    hdr = bytearray(52)
    hdr[0:4] = b"\x7fELF"
    hdr[4], hdr[5], hdr[6] = 1, 1, 1
    struct.pack_into("<HHIIIIIHHHHHH", hdr, 16, 2, 8, 1, vaddr, phoff, 0, 0, 52, 32, 1, 0, 0, 0)
    ph = struct.pack("<8I", 1, off, vaddr, vaddr, len(code), len(code), 5, 4)
    return bytes(hdr) + ph + b"\0" * (off - 52 - 32) + code


class Inputs(unittest.TestCase):
    TOML = ('stubs = [\n  "stub@0x00100400",\n  "other@0x00100800",\n]\n'
            'untracked_stubs = [\n  "ghost@0x00100000",\n]\n')

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="hle_constants_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_parse_stubs_reads_only_the_bound_list(self):
        self.assertEqual(hc.parse_stubs(self.TOML), [("stub", STUB), ("other", OTHER)])

    def test_load_segments(self):
        code = struct.pack("<2I", jal(STUB), NOP)
        segs = hc.load_segments(elf32(BASE, code))
        self.assertEqual(segs, [(BASE, code)])

    def test_cli_end_to_end_and_no_data_exit(self):
        words = [NOP] * 0x300
        words[0] = jal(STUB)
        words[2] = sw(V0, SP)
        elf = os.path.join(self.dir, "t.elf")
        toml = os.path.join(self.dir, "t.toml")
        with open(elf, "wb") as fh:
            fh.write(elf32(BASE, struct.pack("<%dI" % len(words), *words)))
        with open(toml, "w") as fh:
            fh.write(self.TOML)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = hc.main(["--toml", toml, "--elf", elf, "--csv", "", "--extra", "x@0x00100004"])
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("stub", text)
        self.assertIn("direct=1", text)
        self.assertIn("stored", text)
        with open(toml, "w") as fh:
            fh.write("stubs = [\n]\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(hc.main(["--toml", toml, "--elf", elf, "--csv", ""]), 2)


if __name__ == "__main__":
    unittest.main()
