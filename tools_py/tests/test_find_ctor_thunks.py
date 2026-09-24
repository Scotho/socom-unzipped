"""tools_py/find_ctor_thunks.py against a synthetic MWo3 overlay.

The tool reads a table of static-constructor thunk pointers out of an overlay's `MWo3` header
(+0x18 begin, +0x1c end) and forces each thunk as an entry point, because the loader reaches them
only through `jalr` and the recompiler's branch discovery therefore cannot see them.

The bed below is a 0x200-byte overlay at an invented load address with a five-entry table: three
good thunks (a stack prologue, a `lui` leaf, a bare `jr ra` -- all three shapes the real tables
hold), one null pointer and one address outside the image. Nothing here needs the game.

A second class checks the real overlays when they are on this machine; on a fresh clone (and in CI)
`game/` does not exist and those checks skip.
"""
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools_py import find_ctor_thunks

LOAD = 0x00300000
IMAGE_SIZE = 0x200
TABLE = LOAD + 0x180

ADDIU_SP = 0x27BDFFF0      # addiu sp,sp,-16
LUI_A0 = 0x3C044130        # lui a0,0x4130
JR_RA = 0x03E00008
NOP = 0x00000000

THUNK_PROLOGUE = LOAD + 0x080
THUNK_LUI = LOAD + 0x0C0
THUNK_LEAF = LOAD + 0x100
OUTSIDE = LOAD + 0x4000


def build_image(entries=None, magic=b"MWo3", ctor_begin=TABLE, ctor_end=None, size=IMAGE_SIZE):
    """A minimal MWo3 image: header, three thunks, and a ctor table of `entries`."""
    entries = [THUNK_PROLOGUE, THUNK_LUI, THUNK_LEAF, 0, OUTSIDE] if entries is None else entries
    if ctor_end is None:
        ctor_end = ctor_begin + 4 * len(entries)

    image = bytearray(b"\0" * size)
    image[0:4] = magic
    struct.pack_into("<7I", image, 4,
                     1,            # version
                     LOAD,         # load address
                     0x80,         # text size
                     0x100,        # data size
                     0x40,         # bss size
                     ctor_begin,
                     ctor_end)
    image[0x20:0x2C] = b"Test.bin\0\0\0\0"

    struct.pack_into("<I", image, THUNK_PROLOGUE - LOAD, ADDIU_SP)
    struct.pack_into("<I", image, THUNK_LUI - LOAD, LUI_A0)
    struct.pack_into("<I", image, THUNK_LEAF - LOAD, JR_RA)

    for index, value in enumerate(entries):
        offset = ctor_begin - LOAD + index * 4
        if 0 <= offset <= len(image) - 4:
            struct.pack_into("<I", image, offset, value)
    return bytes(image)


def overlay(**kwargs):
    return find_ctor_thunks.Overlay("synthetic.bin", build_image(**kwargs))


class HeaderTest(unittest.TestCase):
    def test_the_header_fields_are_read_from_their_documented_offsets(self):
        header = find_ctor_thunks.read_header(build_image())
        self.assertEqual(header.load, LOAD)
        self.assertEqual(header.text_size, 0x80)
        self.assertEqual(header.ctor_begin, TABLE)
        self.assertEqual(header.ctor_end, TABLE + 20)
        self.assertEqual(header.name, "Test.bin")

    def test_a_foreign_magic_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            find_ctor_thunks.read_header(build_image(magic=b"ELF\0"))
        self.assertIn("MWo3", str(caught.exception))

    def test_a_truncated_image_is_refused(self):
        with self.assertRaises(ValueError):
            find_ctor_thunks.read_header(build_image()[:0x40])

    def test_a_table_that_ends_before_it_begins_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            find_ctor_thunks.read_header(build_image(ctor_begin=TABLE, ctor_end=TABLE - 4))
        self.assertIn("before it begins", str(caught.exception))

    def test_a_table_outside_the_image_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            find_ctor_thunks.read_header(build_image(ctor_begin=LOAD + 0x1000,
                                                     ctor_end=LOAD + 0x1010))
        self.assertIn("outside the image", str(caught.exception))

    def test_a_table_of_partial_words_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            find_ctor_thunks.read_header(build_image(ctor_begin=TABLE, ctor_end=TABLE + 6))
        self.assertIn("whole number of words", str(caught.exception))

    def test_an_unaligned_table_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            find_ctor_thunks.read_header(build_image(ctor_begin=TABLE + 2, ctor_end=TABLE + 6))
        self.assertIn("unaligned", str(caught.exception))


class WalkTest(unittest.TestCase):
    def test_every_sane_entry_is_a_thunk_in_table_order(self):
        found = overlay()
        self.assertEqual([addr for addr, _index in found.thunks],
                         [THUNK_PROLOGUE, THUNK_LUI, THUNK_LEAF])
        self.assertEqual([index for _addr, index in found.thunks], [0, 1, 2])

    def test_a_null_pointer_is_rejected_by_name(self):
        reasons = {addr: reason for addr, _index, reason in overlay().rejected}
        self.assertIn("null", reasons[0])

    def test_an_address_outside_the_image_is_rejected(self):
        reasons = {addr: reason for addr, _index, reason in overlay().rejected}
        self.assertIn("outside the image", reasons[OUTSIDE])

    def test_an_unaligned_entry_is_rejected(self):
        found = overlay(entries=[THUNK_PROLOGUE + 2])
        self.assertEqual(found.thunks, [])
        self.assertIn("4-aligned", found.rejected[0][2])

    def test_an_entry_that_does_not_decode_is_rejected(self):
        # primary opcode 0x13 (COP3) is reserved on the R5900: a word out of a string table or a
        # float, not a thunk.
        image = bytearray(build_image(entries=[THUNK_PROLOGUE]))
        struct.pack_into("<I", image, THUNK_PROLOGUE - LOAD, 0x4C000000)
        found = find_ctor_thunks.Overlay("synthetic.bin", bytes(image))
        self.assertEqual(found.thunks, [])
        self.assertIn("does not decode", found.rejected[0][2])

    def test_an_empty_table_is_not_an_error(self):
        found = overlay(entries=[], ctor_end=TABLE)
        self.assertEqual(found.thunks, [])
        self.assertEqual(found.rejected, [])

    def test_the_same_thunk_in_two_overlays_is_listed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name in ("a.bin", "b.bin"):
                path = os.path.join(tmp, name)
                with open(path, "wb") as f:
                    f.write(build_image())
                paths.append(path)
            _overlays, found = find_ctor_thunks.scan(paths)
            self.assertEqual(list(found), [THUNK_PROLOGUE, THUNK_LUI, THUNK_LEAF])


class Rows(object):
    """The two questions find_ctor_thunks asks a function map."""

    def __init__(self, starts, covered=()):
        self._starts = set(starts)
        self._covered = set(covered) | set(starts)

    def is_start(self, address):
        return address in self._starts

    def covers(self, address):
        return address in self._covered


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "o.bin")
            with open(path, "wb") as f:
                f.write(build_image())
            _overlays, self.found = find_ctor_thunks.scan([path])

    def test_a_thunk_that_is_a_row_start_needs_nothing(self):
        rows = Rows(starts=[THUNK_PROLOGUE, THUNK_LUI, THUNK_LEAF])
        buckets = find_ctor_thunks.classify(self.found, rows, set())
        self.assertEqual(len(buckets["row start"]), 3)
        self.assertEqual(find_ctor_thunks.missing(self.found, rows, set()), [])

    def test_a_thunk_inside_a_row_is_still_missing_an_entry(self):
        rows = Rows(starts=[THUNK_PROLOGUE], covered=[THUNK_LUI])
        buckets = find_ctor_thunks.classify(self.found, rows, set())
        self.assertEqual(buckets["inside a row"], [THUNK_LUI])
        self.assertEqual(buckets["uncovered"], [THUNK_LEAF])
        self.assertEqual(find_ctor_thunks.missing(self.found, rows, set()),
                         sorted([THUNK_LUI, THUNK_LEAF]))

    def test_an_address_already_forced_is_not_offered_again(self):
        rows = Rows(starts=[])
        known = {THUNK_PROLOGUE, THUNK_LUI, THUNK_LEAF}
        self.assertEqual(find_ctor_thunks.missing(self.found, rows, known), [])
        self.assertEqual(len(find_ctor_thunks.classify(self.found, rows, known)["listed"]), 3)

    def test_the_comment_names_the_overlay_and_the_table(self):
        text = find_ctor_thunks.comment(self.found, THUNK_LUI)
        self.assertIn("Test.bin", text)
        self.assertIn("0x%x" % TABLE, text)


class AppendTest(unittest.TestCase):
    def test_the_missing_addresses_are_appended_once_under_the_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = os.path.join(tmp, "o.bin")
            with open(image, "wb") as f:
                f.write(build_image())
            extras = os.path.join(tmp, "extra_functions.txt")
            with open(extras, "w", encoding="utf-8", newline="\n") as f:
                f.write("0x%08x  # already listed\n" % THUNK_PROLOGUE)

            rc = find_ctor_thunks.main([image, "--extras", extras, "--append", extras,
                                        "--header", "# --- overlay ctor thunks (test) ---",
                                        "--quiet"])
            self.assertEqual(rc, 0)

            lines = open(extras, encoding="utf-8").read().splitlines()
            self.assertEqual(lines[0], "0x%08x  # already listed" % THUNK_PROLOGUE)
            self.assertEqual(lines[1], "# --- overlay ctor thunks (test) ---")
            self.assertEqual([line.split()[0] for line in lines[2:]],
                             ["0x%08x" % THUNK_LUI, "0x%08x" % THUNK_LEAF])
            self.assertEqual(len(lines), 4, "one block, one write")

    def test_nothing_is_written_when_nothing_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = os.path.join(tmp, "o.bin")
            with open(image, "wb") as f:
                f.write(build_image())
            extras = os.path.join(tmp, "extra_functions.txt")
            with open(extras, "w", encoding="utf-8", newline="\n") as f:
                for address in (THUNK_PROLOGUE, THUNK_LUI, THUNK_LEAF):
                    f.write("0x%08x\n" % address)
            before = open(extras, encoding="utf-8").read()

            find_ctor_thunks.main([image, "--extras", extras, "--append", extras, "--quiet"])
            self.assertEqual(open(extras, encoding="utf-8").read(), before,
                             "a revision that already carries every thunk gains no line")


GAME = os.path.join(ROOT, "game")


@unittest.skipUnless(os.path.isdir(GAME), "the game images are not on this machine")
class RealOverlayTest(unittest.TestCase):
    """The two revisions' real tables, when the images are here.

    0x3fd680 is the address the r0004 gate saw as an unresolved `jalr` from 0x182864 -- the loader's
    ctor walker -- and it is r0001's first FTSCore thunk, which is what makes this tool the answer
    to that class. 0x3d9e40 came from a `jalr` at 0x181fb4, a different function, and is in no ctor
    table of either revision: it is not one of these.
    """

    def overlay_or_skip(self, relative):
        path = os.path.join(GAME, relative)
        if not os.path.isfile(path):
            self.skipTest("%s is not here" % relative)
        return find_ctor_thunks.load_overlay(path)

    def test_r0001_ftscore_holds_125_thunks_starting_at_0x3fd680(self):
        fts = self.overlay_or_skip(os.path.join("overlays", "ftscore.bin"))
        self.assertEqual(fts.header.ctor_begin, 0x00404D10)
        self.assertEqual(len(fts.thunks), 125)
        self.assertEqual(fts.thunks[0][0], 0x003FD680)
        self.assertEqual(fts.rejected, [])

    def test_r0001_zsealetc_holds_16_thunks_starting_at_0x668480(self):
        zseal = self.overlay_or_skip(os.path.join("overlays", "zsealetc.bin"))
        self.assertEqual(zseal.header.ctor_begin, 0x006690E0)
        self.assertEqual(len(zseal.thunks), 16)
        self.assertEqual(zseal.thunks[0][0], 0x00668480)

    def test_r0004_moved_both_tables(self):
        fts = self.overlay_or_skip(os.path.join("overlays_r0004", "ftscore.bin"))
        zseal = self.overlay_or_skip(os.path.join("overlays_r0004", "zsealetc.bin"))
        self.assertEqual((fts.header.ctor_begin, fts.header.ctor_end), (0x004315A0, 0x00431798))
        self.assertEqual((zseal.header.ctor_begin, zseal.header.ctor_end), (0x00668A60, 0x00668AA0))
        self.assertEqual(len(fts.thunks), 126)
        self.assertEqual(len(zseal.thunks), 16)
        self.assertEqual(fts.rejected + zseal.rejected, [])

    def test_0x3d9e40_is_not_a_ctor_thunk_in_either_revision(self):
        addresses = set()
        for relative in (os.path.join("overlays", "ftscore.bin"),
                         os.path.join("overlays", "zsealetc.bin"),
                         os.path.join("overlays_r0004", "ftscore.bin"),
                         os.path.join("overlays_r0004", "zsealetc.bin")):
            # raw table entries, accepted and rejected both: the claim is "in no ctor table",
            # not "in no table the filters kept"
            found = self.overlay_or_skip(relative)
            addresses.update(a for a, _i in found.thunks)
            addresses.update(a for a, _i, _reason in found.rejected)
        self.assertIn(0x003FD680, addresses)
        self.assertNotIn(0x003D9E40, addresses)


if __name__ == "__main__":
    unittest.main()
