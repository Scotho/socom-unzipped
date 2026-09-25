"""Sprint 11 Task 10 Step 1 -- the per-function fingerprint (tools_py/fingerprint.py).

The fingerprint exists so that the same routine in two builds of the game hashes to the same value even
though the linker gave it different addresses: every immediate that carries an address (lui/addiu/ori
upper and lower halves, the jal/j target field, a branch displacement) is zeroed before hashing, while a
load/store displacement -- a structure offset, which a relink does not move -- is kept.

Everything here runs over hand-assembled MIPS words. No disc, no ELF, no recompiler.
"""
import unittest

from tools_py import fingerprint as fp


# ---- a tiny assembler (the same shape as tools_py/tests/test_hle_constants.py) --------------

def word(*ws):
    return b"".join(w.to_bytes(4, "little") for w in ws)


def lui(rt, imm):        return (0x0F << 26) | (rt << 16) | (imm & 0xFFFF)
def addiu(rt, rs, imm):  return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def ori(rt, rs, imm):    return (0x0D << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def jal(target):         return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)
def j(target):           return (0x02 << 26) | ((target >> 2) & 0x03FFFFFF)
def beq(rs, rt, off):    return (0x04 << 26) | (rs << 21) | (rt << 16) | (off & 0xFFFF)
def bne(rs, rt, off):    return (0x05 << 26) | (rs << 21) | (rt << 16) | (off & 0xFFFF)
def lw(rt, base, imm):   return (0x23 << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def sw(rt, base, imm):   return (0x2B << 26) | (base << 21) | (rt << 16) | (imm & 0xFFFF)
def addu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21
def subu(rd, rs, rt):    return (rs << 21) | (rt << 16) | (rd << 11) | 0x23
def jr_ra():             return (31 << 21) | 8
NOP = 0

V0, A0, A1, S0, SP, RA = 2, 4, 5, 16, 29, 31


class TestFingerprintIgnoresRelocatedImmediates(unittest.TestCase):
    def test_a_relocated_lui_addiu_pair_hashes_equal(self):
        """The classic `lui $a0, hi; addiu $a0, $a0, lo` address materialisation, moved by the linker."""
        a = word(lui(A0, 0x0040), addiu(A0, A0, 0x4D10), jr_ra(), NOP)
        b = word(lui(A0, 0x0043), addiu(A0, A0, 0x5618), jr_ra(), NOP)
        self.assertNotEqual(a, b)
        self.assertEqual(fp.fingerprint(a), fp.fingerprint(b))

    def test_a_relocated_call_and_branch_hash_equal(self):
        a = word(jal(0x00290C30), NOP, j(0x00338480), beq(A0, A1, 4), jr_ra(), NOP)
        b = word(jal(0x002BD5F0), NOP, j(0x00364E40), beq(A0, A1, 12), jr_ra(), NOP)
        self.assertNotEqual(a, b)
        self.assertEqual(fp.fingerprint(a), fp.fingerprint(b))

    def test_a_relocated_ori_hashes_equal(self):
        a = word(lui(V0, 0x0034), ori(V0, V0, 0xAFD0), jr_ra(), NOP)
        b = word(lui(V0, 0x0037), ori(V0, V0, 0x7990), jr_ra(), NOP)
        self.assertEqual(fp.fingerprint(a), fp.fingerprint(b))

    def test_the_register_fields_of_a_zeroed_immediate_still_count(self):
        """Only the immediate is dropped: `lui $a0` and `lui $v0` are different code."""
        a = word(lui(A0, 0x0040), jr_ra(), NOP)
        b = word(lui(V0, 0x0040), jr_ra(), NOP)
        self.assertNotEqual(fp.fingerprint(a), fp.fingerprint(b))


class TestFingerprintSeparatesRealDifferences(unittest.TestCase):
    def test_a_different_opcode_hashes_differently(self):
        a = word(addu(V0, A0, A1), jr_ra(), NOP)
        b = word(subu(V0, A0, A1), jr_ra(), NOP)
        self.assertNotEqual(fp.fingerprint(a), fp.fingerprint(b))

    def test_a_load_store_displacement_is_kept(self):
        """A structure offset is not a relocation: +0xb4 and +0xc8 are different routines."""
        a = word(lw(V0, S0, 0x00B4), sw(V0, SP, 0x0010), jr_ra(), NOP)
        b = word(lw(V0, S0, 0x00C8), sw(V0, SP, 0x0010), jr_ra(), NOP)
        self.assertNotEqual(fp.fingerprint(a), fp.fingerprint(b))

    def test_a_reordered_body_hashes_differently(self):
        a = word(addu(V0, A0, A1), lw(V0, S0, 4), jr_ra(), NOP)
        b = word(lw(V0, S0, 4), addu(V0, A0, A1), jr_ra(), NOP)
        self.assertNotEqual(fp.fingerprint(a), fp.fingerprint(b))

    def test_a_different_branch_opcode_hashes_differently(self):
        a = word(beq(A0, A1, 4), NOP, jr_ra(), NOP)
        b = word(bne(A0, A1, 4), NOP, jr_ra(), NOP)
        self.assertNotEqual(fp.fingerprint(a), fp.fingerprint(b))


class TestFingerprintShape(unittest.TestCase):
    def test_an_empty_stream_is_the_fnv_offset_basis(self):
        self.assertEqual(fp.fingerprint(b""), "%016x" % fp.FNV_OFFSET)

    def test_the_value_is_sixteen_lowercase_hex_digits(self):
        h = fp.fingerprint(word(addu(V0, A0, A1), jr_ra(), NOP))
        self.assertEqual(len(h), 16)
        self.assertEqual(h, h.lower())
        int(h, 16)

    def test_a_trailing_partial_word_is_ignored(self):
        body = word(addu(V0, A0, A1), jr_ra(), NOP)
        self.assertEqual(fp.fingerprint(body), fp.fingerprint(body + b"\x01\x02\x03"))

    def test_the_constants_are_the_fnv_1a_64_pair(self):
        self.assertEqual(fp.FNV_OFFSET, 0xCBF29CE484222325)
        self.assertEqual(fp.FNV_PRIME, 0x100000001B3)


if __name__ == "__main__":
    unittest.main()
