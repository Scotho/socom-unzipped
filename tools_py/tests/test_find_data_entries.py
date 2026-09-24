"""tools_py/find_data_entries.py against a synthetic EE image.

The instrument exists because the r0004 gate dies on addresses no branch names: a data word that
holds a function pointer, and a *continuation* pc (a call's return address or a branch's
fallthrough) that the recompiler cannot register because the instruction producing it sits in a
different map row than the address itself. Both shapes are laid out below at invented addresses, so
the checks are on the rules, not on the game.

Layout (text 0x00100000, 0x100 bytes, executable; data 0x00200000, read/write):

    0x00100000  addiu sp,sp,-32      FUN_main starts here
    0x00100008  jal 0x00100080       return 0x00100010 is INSIDE FUN_main  -> not reported
    0x0010000c  addiu sp,sp,-32      the jal's delay slot: prologue-shaped, still not an entry
    0x00100018  bne v0,zero,+1       fallthrough 0x00100020 is OUTSIDE FUN_main -> reported
    0x0010001c                       FUN_main ends / FUN_tail starts on that delay slot
    0x00100030  jal 0x00100080       return 0x00100038 is OUTSIDE FUN_tail -> reported
    0x00100040  addiu sp,sp,-32      FUN_next starts here
    0x00100050  addiu sp,sp,-32      a mid-row prologue that only a data word names
    0x00100068  0x12345679           inside FUN_blob: a "branch" off the image -> ignored as data
    0x00100078  jr ra                a leaf in a gap, named only by a data word
    0x00100080  addiu sp,sp,-32      FUN_call
"""
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools_py import find_data_entries

TEXT_BASE = 0x00100000
DATA_BASE = 0x00200000

ADDIU_SP = 0x27BDFFE0      # addiu sp,sp,-32
SD_RA = 0xFFBF0018         # sd ra,24(sp)
JR_RA = 0x03E00008
NOP = 0x00000000
DADDU_ZERO = 0x0000002D


def jal(target):
    return (3 << 26) | ((target >> 2) & 0x03FFFFFF)


def bne_forward(words):
    """bne v0,zero,+words -- conditional, so its fallthrough is reachable."""
    return (5 << 26) | (2 << 21) | (words & 0xFFFF)


def text_words():
    w = [NOP] * 64
    w[0] = ADDIU_SP                 # 0x100000 FUN_main
    w[1] = SD_RA
    w[2] = jal(0x00100080)          # 0x100008, return 0x100010 inside FUN_main
    w[3] = ADDIU_SP                 # 0x10000c delay slot, prologue-shaped
    w[4] = JR_RA                    # 0x100010 FUN_main returns, so it is a function body
    w[6] = bne_forward(1)           # 0x100018, fallthrough 0x100020 outside FUN_main
    w[8] = DADDU_ZERO               # 0x100020
    w[10] = JR_RA                    # 0x100028 FUN_tail returns
    w[12] = jal(0x00100080)         # 0x100030, return 0x100038 outside FUN_tail
    w[14] = ADDIU_SP                # 0x100038 (gap)
    w[16] = ADDIU_SP                # 0x100040 FUN_next
    w[18] = JR_RA                   # 0x100048
    w[20] = ADDIU_SP                # 0x100050 data-referenced entry
    w[26] = 0x12345679              # 0x100068 "beq s1,a0,+0x5679": a table word, target off-image
    w[28] = ADDIU_SP                # 0x100070, the blob's continuation
    w[32] = ADDIU_SP                # 0x100080 FUN_call
    w[30] = JR_RA                   # 0x100078 a leaf in a gap: the map covers nothing here
    w[41] = 0x04210000              # 0x1000a4 "bgez at,+0": branches to its own delay slot
    w[33] = SD_RA
    w[34] = JR_RA
    w[35] = 0x27BD0020              # addiu sp,sp,32
    return w


DATA_WORDS = [
    0x00100050,   # a prologue that is not a row start  -> found
    0x00100078,   # a `jr ra` leaf in a map gap         -> found
    0x00100010,   # a `jr ra` inside FUN_main's body    -> rejected, that is its return
    0x00100000,   # FUN_main's own start                -> skipped, already an entry
    0x0010000C,   # a delay slot                        -> rejected
    0x00100080,   # FUN_call's own start                -> skipped
    0x12345678,   # not inside the text range           -> ignored
    0x00100042,   # not 4-aligned                       -> ignored
]

CSV_ROWS = """Name,Start,End,Size
FUN_main,0x00100000,0x0010001C,28
FUN_tail,0x0010001C,0x00100038,28
FUN_next,0x00100040,0x00100060,32
FUN_blob,0x00100060,0x00100070,16
FUN_call,0x00100080,0x001000A0,32
FUN_zed,0x001000A0,0x001000AC,12
"""


def write_elf(path, segments):
    """A little-endian ELF32 carrying `segments` as [(vaddr, bytes, flags)] PT_LOADs."""
    phoff = 52
    phnum = len(segments)
    body_off = phoff + 32 * phnum
    headers, body = b"", b""
    for vaddr, payload, flags in segments:
        off = body_off + len(body)
        headers += struct.pack("<IIIIIIII", 1, off, vaddr, vaddr, len(payload), len(payload), flags, 0x10)
        body += payload
    ehdr = bytearray(52)
    ehdr[0:4] = b"\x7fELF"
    ehdr[4:7] = b"\x01\x01\x01"
    struct.pack_into("<HHI", ehdr, 16, 2, 8, 1)          # ET_EXEC, EM_MIPS
    struct.pack_into("<III", ehdr, 24, segments[0][0], phoff, 0)
    struct.pack_into("<IHHHHHH", ehdr, 36, 0, 52, 32, phnum, 40, 0, 0)
    with open(path, "wb") as f:
        f.write(bytes(ehdr) + headers + body)


class SyntheticImage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="dataentries_")
        self.elf = os.path.join(self.dir, "synthetic.elf")
        self.csv = os.path.join(self.dir, "synthetic.csv")
        text = struct.pack("<64I", *text_words())
        data = struct.pack("<%dI" % len(DATA_WORDS), *DATA_WORDS)
        write_elf(self.elf, [(TEXT_BASE, text, 5), (DATA_BASE, data, 6)])
        with open(self.csv, "w", encoding="utf-8") as f:
            f.write(CSV_ROWS)
        self.image = find_data_entries.Image(self.elf)
        self.rows = find_data_entries.load_rows(self.csv)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def data_hits(self):
        return find_data_entries.data_entries(self.image, self.rows)

    def resume_hits(self):
        return find_data_entries.resume_entries(self.image, self.rows)


class DataScanTest(SyntheticImage):
    def test_a_data_word_pointing_at_a_prologue_is_found(self):
        hits = self.data_hits()
        self.assertIn(0x00100050, hits)
        self.assertEqual(hits[0x00100050].referenced_from, DATA_BASE)

    def test_a_data_word_pointing_mid_delay_slot_is_rejected(self):
        self.assertNotIn(0x0010000C, self.data_hits())

    def test_a_leaf_counts_only_where_the_map_covers_nothing(self):
        hits = self.data_hits()
        self.assertIn(0x00100078, hits)      # in the gap between FUN_blob and FUN_call
        self.assertNotIn(0x00100010, hits)   # FUN_main's own `jr ra`

    def test_a_data_word_pointing_at_a_function_start_is_skipped(self):
        hits = self.data_hits()
        self.assertNotIn(0x00100000, hits)
        self.assertNotIn(0x00100080, hits)

    def test_a_word_outside_the_text_range_or_unaligned_is_ignored(self):
        hits = self.data_hits()
        self.assertNotIn(0x12345678, hits)
        self.assertNotIn(0x00100042, hits)

    def test_the_scan_finds_nothing_else_in_this_image(self):
        self.assertEqual(sorted(self.data_hits()), [0x00100050, 0x00100078])


class ResumeScanTest(SyntheticImage):
    def test_a_call_return_that_leaves_its_row_is_found(self):
        hits = self.resume_hits()
        self.assertIn(0x00100038, hits)
        self.assertEqual(hits[0x00100038].source, 0x00100030)
        self.assertEqual(hits[0x00100038].kind, "call-return")

    def test_a_call_return_inside_its_own_row_is_not_reported(self):
        self.assertNotIn(0x00100010, self.resume_hits())

    def test_a_branch_fallthrough_that_leaves_its_row_is_found(self):
        hits = self.resume_hits()
        self.assertIn(0x00100020, hits)
        self.assertEqual(hits[0x00100020].kind, "branch-fallthrough")

    def test_a_row_that_starts_on_a_delay_slot_yields_its_start_plus_four(self):
        # FUN_tail starts at 0x0010001c, the delay slot of the beq at 0x00100018.
        self.assertIn(0x0010001C + 4, self.resume_hits())

    def test_a_branch_whose_target_is_off_the_image_is_table_data(self):
        # 0x12345679 at 0x00100068 decodes as a branch to 0x0011a04c, which is in no segment:
        # FUN_blob is a table the map mislabelled, so its "fallthrough" is not an entry.
        self.assertNotIn(0x00100070, self.resume_hits())

    def test_a_branch_to_its_own_delay_slot_is_table_data(self):
        # 0x04210000 in FUN_zed is "bgez at,+0" -- an offset no compiler emits.
        self.assertNotIn(0x001000AC, self.resume_hits())

    def test_an_overlapping_row_that_covers_both_ends_suppresses_the_hit(self):
        # The folded r0004 map has rows that overlap (FUN_00251f08 ends inside FUN_00252008).
        # When one row covers the branch *and* its fallthrough, the recompiler already resumes
        # there and the address is not missing.
        with open(self.csv, "a", encoding="utf-8") as f:
            f.write("FUN_wide,0x00100000,0x00100030,48\n")
        rows = find_data_entries.load_rows(self.csv)
        self.assertNotIn(0x00100020, find_data_entries.resume_entries(self.image, rows))

    def test_the_scan_finds_nothing_else_in_this_image(self):
        self.assertEqual(sorted(self.resume_hits()), [0x00100020, 0x00100038])


class PlausibilityTest(unittest.TestCase):
    def test_prologue_shapes_are_accepted(self):
        for word in (ADDIU_SP, SD_RA, JR_RA, 0x3C1C001D, 0xFFBF0000, 0x7FBF0000, 0xAFBF0010):
            self.assertTrue(find_data_entries.looks_like_entry(word), hex(word))

    def test_a_leaf_inside_a_mapped_function_is_its_return_not_an_entry(self):
        self.assertFalse(find_data_entries.looks_like_entry(JR_RA, in_a_gap=False))
        self.assertTrue(find_data_entries.looks_like_entry(ADDIU_SP, in_a_gap=False))

    def test_ordinary_mid_body_instructions_are_not_entries(self):
        for word in (NOP, DADDU_ZERO, 0x24040001, 0x8C620000):
            self.assertFalse(find_data_entries.looks_like_entry(word), hex(word))


class SanityTest(unittest.TestCase):
    """The filter that keeps a string table from decoding into entry points.

    Every word below is real ZSealEtc data that the first cut of this tool reported as an entry:
    0xffff003d is "sd ra,0x3d(ra)" (a displacement no compiler emits for an 8-byte store), and
    0x00444549 is the ASCII "IED\\0" of ..._JUSTIFIED that decodes as a jalr with a non-zero rt.
    """

    def test_an_unaligned_doubleword_access_is_not_an_instruction(self):
        self.assertFalse(find_data_entries.is_sane_instruction(0xFFFF003D))
        self.assertFalse(find_data_entries.is_sane_instruction(0xFF08FF03))
        self.assertTrue(find_data_entries.is_sane_instruction(0xFFBF0018))    # sd ra,24(sp)

    def test_a_jalr_with_a_nonzero_rt_is_not_an_instruction(self):
        self.assertFalse(find_data_entries.is_sane_instruction(0x00444549))
        self.assertTrue(find_data_entries.is_sane_instruction(0x0040F809))    # jalr ra,v0

    def test_a_transfer_through_zero_is_not_an_instruction(self):
        self.assertFalse(find_data_entries.is_sane_instruction(0x00002949))   # "jalr a1,zero"
        self.assertFalse(find_data_entries.is_sane_instruction(0x04000000))   # "bltz zero,+0"

    def test_a_syscall_with_a_code_field_is_not_an_instruction(self):
        self.assertFalse(find_data_entries.is_sane_instruction(0x01E00C0C))   # data, in r0001
        self.assertTrue(find_data_entries.is_sane_instruction(0x0000000C))    # syscall

    def test_an_unconditional_branch_has_no_reachable_fallthrough(self):
        self.assertTrue(find_data_entries.is_unconditional_branch(0x10000034))   # b +0x34
        self.assertFalse(find_data_entries.falls_through(0x10000034))
        self.assertTrue(find_data_entries.falls_through(bne_forward(4)))


class KnownListTest(SyntheticImage):
    def test_addresses_already_listed_are_filtered_out(self):
        known = {0x00100050, 0x00100078, 0x00100038}
        self.assertEqual(find_data_entries.new_addresses(self.data_hits(), known), [])
        self.assertEqual(find_data_entries.new_addresses(self.resume_hits(), known), [0x00100020])

    def test_parsing_an_extras_file_keeps_only_the_addresses(self):
        path = os.path.join(self.dir, "extras.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# a comment\n0x00100050  # new find: whatever\n\n0x100038\n")
        self.assertEqual(find_data_entries.load_known(path), {0x00100050, 0x00100038})


if __name__ == "__main__":
    unittest.main()
