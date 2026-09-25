"""tools_py/translate_extras.py: carry r0001's forced entry points onto another build's addresses.

    python -m tools_py.translate_extras recomp/extra_functions.txt game/r0004/match.json \\
        recomp/extra_functions_r0004.txt --append

`recomp/extra_functions.txt` is three weeks of forced entry points found on the r0001 image: thread
resume points, callbacks materialised as immediates, interior starts Ghidra merged away. Every one of
those numbers is an r0001 guest address, so on another build it names whatever that build happens to
have put there -- but the match report says where each r0001 FUNCTION went, and an address inside a
matched body moves by that body's delta, exactly as `tools_py/revision_toml.py` moves an instruction
patch. This module reuses that module's `Translator` rather than re-deriving the rule.

Every address here is invented. The synthetic B image is a handful of MIPS words in one executable
PT_LOAD, so the suite runs with no disc, no ELF and no recompiler.

What these cases pin:
  * a forced entry that IS an r0001 function start moves by its own match, and says which method;
  * a forced entry INSIDE a matched body moves by that body's delta, and names the r0001 function;
  * a forced entry in a byte-identical (loader) region is carried across unchanged;
  * a forced entry the matcher cannot place is LEFT OUT, and counted by the reason it was left out;
  * unless --anchor finds the window of code around it exactly once in the B image, which places it;
  * an address already in the target list is not appended twice;
  * a translated address outside the B image's text, off a 4-byte boundary, or in a branch's delay
    slot is REJECTED and counted -- a forced entry point is a claim that code starts there;
  * finds from the discovery tools ride the same verification and are tagged by the tool;
  * the whole block is written with ONE append, under one header line, so a concurrent appender
    cannot interleave inside it;
  * --dry-run writes nothing.
"""
import contextlib
import io
import json
import os
import struct
import tempfile
import unittest

from tools_py import translate_extras


# ---- a tiny assembler (the same shapes tools_py/tests/test_address_matcher.py uses) -----------

def jal(target):        return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)
def addiu(rt, rs, imm): return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def jr_ra():            return (31 << 21) | 8
NOP = 0

TEXT_A = 0x00100000          # a region byte-identical in both builds: the loader
CODE_A = 0x00200000          # where the A build's overlay code sits
TEXT_B = 0x00300000          # where the B build put the overlay code
SEG_WORDS = 0x400
A_WORDS = 0x1200
MOVED = 0x00202040           # an A address inside a function the matcher lost
LANDED = 0x00300200          # where the B build put the code around it


def minimal_elf32(segments):
    """A little-endian ELF32 with one executable PT_LOAD per segment."""
    ehsize, phentsize = 52, 32
    phoff = ehsize
    header = bytearray(b"\x7fELF\x01\x01\x01" + b"\x00" * 9)
    header += struct.pack("<HHI", 2, 8, 1)
    header += struct.pack("<III", segments[0][0], phoff, 0)
    header += struct.pack("<IHHHHHH", 0, ehsize, phentsize, len(segments), 40, 0, 0)
    body, phdrs, off = b"", b"", phoff + phentsize * len(segments)
    for vaddr, data in segments:
        phdrs += struct.pack("<8I", 1, off + len(body), vaddr, vaddr, len(data), len(data), 5, 0x10)
        body += data
    return bytes(header) + phdrs + body


def a_words():
    """The A build's overlay text. `addiu rX, zero, imm` is a constant, so normalize() keeps it whole
    and every window of it is distinctive -- which is what the anchor needs to be tested on."""
    return [addiu(2, 0, (i * 3 + 1) & 0xFFFF) for i in range(A_WORDS)]


def a_image():
    loader = struct.pack("<%dI" % SEG_WORDS, *([addiu(2, 0, 1)] * SEG_WORDS))
    return minimal_elf32([(TEXT_A, loader), (CODE_A, struct.pack("<%dI" % A_WORDS, *a_words()))])


def b_image():
    """The B build's text, with a `jal` planted just above 0x00300080 and the block around MOVED
    copied in at LANDED -- one relocated body the function matcher never placed."""
    words = [addiu(2, 0, (i * 7 + 3) & 0xFFFF) for i in range(SEG_WORDS)]
    words[(0x80 - 4) // 4] = jal(TEXT_B)          # 0x0030007c: so 0x00300080 is a DELAY SLOT
    words[0x100 // 4] = jr_ra()
    src = a_words()
    at = (MOVED - CODE_A) // 4
    for k in range(-12, 9):                       # wider than the anchor's widest window (10 before)
        words[(LANDED - TEXT_B) // 4 + k] = src[at + k]
    data = struct.pack("<%dI" % SEG_WORDS, *words)
    loader = struct.pack("<%dI" % SEG_WORDS, *([addiu(2, 0, 1)] * SEG_WORDS))
    return minimal_elf32([(TEXT_A, loader), (TEXT_B, data)])


CSV_A = '''\
Name,Start,End,Size
loaderRoutine,0x00100200,0x00100300,256
fnExact,0x00200000,0x00200100,256
fnDelta,0x00201000,0x00201100,256
fnGone,0x00202000,0x00202100,256
fnFar,0x00203000,0x00203100,256
fnSeed,0x00204000,0x00204100,256
'''

MATCHES = {
    "0x00100200": {"name": "loaderRoutine", "b": "0x00100200", "how": "exact"},
    "0x00200000": {"name": "fnExact", "b": "0x00300000", "how": "exact"},
    "0x00201000": {"name": "fnDelta", "b": "0x00300400", "how": "relinked-body"},
    "0x00202000": {"name": "fnGone", "b": None, "how": "unresolved"},
    "0x00203000": {"name": "fnFar", "b": "0x00900000", "how": "exact"},
    "0x00204000": {"name": "fnSeed", "b": "0x00300600", "how": "seed+delta"},
}

SOURCE_LIST = '''\
0x00200000  # a function start, matched exactly
0x00200040  # imm target from 0x00200030 -- inside fnExact
0x00201010  # inside fnDelta, which was relinked
0x00204040  # inside fnSeed, placed by the seed pass
0x00202040  # inside fnGone, which the matcher lost
0x00280000  # no function body holds this at all
0x00100240  # inside the loader, which does not move
0x00200080  # lands in a delay slot in the B build
0x00200042  # lands off a 4-byte boundary
0x00203000  # matched to an address outside the B image
0x00201080  # already in the target list
'''

EXISTING = '''\
0x00300480  # imm target from 0x00300460
0x00300900  # runtime missing-target (a harvest, 2026-09-24)
'''

DISCOVERED = '''\
0x00300800  find_gap_functions
0x00300804  find_interior_functions
0x00300801  find_gap_functions
0x00300900  find_escaping_branches
'''

HEADER = "# --- translated from r0001 (2026-09-24) ---"


def write(path, text, mode="w"):
    with open(path, mode, encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


class Bed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.csv = write(os.path.join(d, "a.csv"), CSV_A)
        self.source = write(os.path.join(d, "extra_functions.txt"), SOURCE_LIST)
        self.target = write(os.path.join(d, "extra_functions_r0004.txt"), EXISTING)
        self.discovered = write(os.path.join(d, "found.txt"), DISCOVERED)
        self.elf_b = os.path.join(d, "b.elf")
        with open(self.elf_b, "wb") as fh:
            fh.write(b_image())
        self.elf_a = os.path.join(d, "a.elf")
        with open(self.elf_a, "wb") as fh:
            fh.write(a_image())
        self.match = write(os.path.join(d, "match.json"), json.dumps({
            "a": {"elf": "a.elf", "csv": self.csv},
            "b": {"elf": self.elf_b, "csv": "b.csv"},
            "matches": MATCHES,
            "summary": {"total": 6, "resolved": 5, "unresolved": 1},
        }))

    def run_tool(self, *extra):
        argv = [self.source, self.match, self.target, "--csv-a", self.csv, "--elf-b", self.elf_b,
                "--fixed", "0x100000-0x200000", "--header", HEADER, "--json"] + list(extra)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = translate_extras.main(argv)
        self.printed = buf.getvalue()
        self.assertEqual(rc, 0, self.printed)
        self.stats = json.loads(self.printed[self.printed.index("{"):])
        with open(self.target, encoding="utf-8") as fh:
            self.text = fh.read()
        return self.stats

    def appended(self):
        """The lines of the block this tool wrote, header excluded."""
        self.assertIn(HEADER, self.text)
        tail = self.text[self.text.index(HEADER) + len(HEADER):]
        return [ln for ln in tail.splitlines() if ln.strip()]

    def line_for(self, addr):
        hits = [ln for ln in self.appended() if ln.startswith("0x%08x" % addr)]
        self.assertEqual(len(hits), 1, "expected one line for 0x%08x, got %r" % (addr, hits))
        return hits[0]


class Translation(Bed):
    def test_a_function_start_moves_by_its_own_match(self):
        self.run_tool("--append")
        self.assertIn("via exact (fnExact)", self.line_for(0x00300000))

    def test_a_body_interior_address_moves_by_its_function_delta(self):
        self.run_tool("--append")
        self.assertIn("from r0001 0x00200040", self.line_for(0x00300040))

    def test_the_interior_line_names_the_method_and_the_r0001_function(self):
        self.run_tool("--append")
        line = self.line_for(0x00300410)
        self.assertIn("relinked-body", line)
        self.assertIn("(fnDelta)", line)

    def test_a_seed_placed_body_interior_says_it_is_weak(self):
        # The seed pass proves the function's fingerprint at the new address, not that the bytes
        # inside it kept their offsets -- the same rule tools_py/revision_toml.py applies.
        self.run_tool("--append")
        self.assertIn("weak", self.line_for(0x00300640))

    def test_a_loader_region_address_is_carried_across_unchanged(self):
        self.run_tool("--append")
        self.assertIn("via loader", self.line_for(0x00100240))

    def test_every_translated_address_is_counted(self):
        stats = self.run_tool("--append")
        # 1 start + 5 interior + 1 loader + 1 off-image + 1 already listed; the two the matcher
        # cannot place are not among them.
        self.assertEqual(stats["translated"], 9)


class LeftOut(Bed):
    def test_an_unplaceable_function_is_left_out(self):
        self.run_tool("--append")
        self.assertNotIn("0x00202040", self.text)

    def test_the_reasons_are_counted(self):
        stats = self.run_tool("--append")
        self.assertEqual(sum(stats["untranslatable"].values()), 2)
        self.assertEqual(stats["untranslatable"]["no function body holds it"], 1)

    def test_an_address_already_in_the_target_list_is_not_appended_twice(self):
        stats = self.run_tool("--append")
        self.assertEqual(self.text.count("0x00300480"), 1)
        self.assertEqual(stats["already_listed"], 1)


class Verification(Bed):
    def test_an_address_outside_the_b_image_text_is_rejected(self):
        stats = self.run_tool("--append")
        self.assertNotIn("0x00900000", self.text)
        self.assertEqual(stats["rejected"]["outside the image text"], 1)

    def test_an_unaligned_address_is_rejected(self):
        stats = self.run_tool("--append")
        self.assertNotIn("0x00300042", self.text)
        self.assertEqual(stats["rejected"]["not on a 4-byte boundary"], 1)

    def test_an_address_in_a_delay_slot_is_rejected(self):
        stats = self.run_tool("--append")
        self.assertNotIn("0x00300080", self.text)
        self.assertEqual(stats["rejected"]["in a branch or jump delay slot"], 1)


class DiscoveryFinds(Bed):
    def test_a_new_find_is_appended_tagged_by_its_tool(self):
        self.run_tool("--append", "--discovered", self.discovered)
        self.assertIn("find_gap_functions", self.line_for(0x00300800))

    def test_a_new_find_rides_the_same_verification(self):
        stats = self.run_tool("--append", "--discovered", self.discovered)
        self.assertNotIn("0x00300801", self.text)
        self.assertEqual(stats["rejected"]["not on a 4-byte boundary"], 2)

    def test_a_find_already_listed_is_not_appended(self):
        stats = self.run_tool("--append", "--discovered", self.discovered)
        self.assertEqual(self.text.count("0x00300900"), 1)
        self.assertEqual(stats["already_listed"], 2)

    def test_the_finds_are_counted_per_tool(self):
        stats = self.run_tool("--append", "--discovered", self.discovered)
        self.assertEqual(stats["discovered"]["find_gap_functions"], 1)
        self.assertEqual(stats["discovered"]["find_interior_functions"], 1)


class AnchorEscalation(Bed):
    """r0001's forced entries are folded into its function table as three-word rows, which have no
    fingerprint to match. The window of code around them is the evidence that is left."""

    def anchored(self, *extra):
        return self.run_tool("--append", "--elf-a", self.elf_a, "--anchor", *extra)

    def test_a_lost_address_is_placed_by_the_window_around_it(self):
        self.anchored()
        self.assertIn("via anchor", self.line_for(LANDED))

    def test_the_line_says_which_window_placed_it(self):
        self.anchored()
        self.assertIn("window 10/6", self.line_for(LANDED))

    def test_the_anchored_ones_are_counted_apart(self):
        stats = self.anchored()
        self.assertEqual(stats["anchored"], 1)

    def test_an_address_whose_code_is_not_in_the_b_image_stays_lost(self):
        stats = self.anchored()
        self.assertEqual(sum(stats["untranslatable"].values()), 1)
        self.assertEqual(stats["untranslatable"]["no function body holds it"], 1)

    def test_without_the_flag_nothing_is_anchored(self):
        stats = self.run_tool("--append", "--elf-a", self.elf_a)
        self.assertEqual(stats["anchored"], 0)
        self.assertNotIn("0x%08x" % LANDED, self.text)


class OneAppend(Bed):
    def test_the_block_is_written_once_under_one_header(self):
        self.run_tool("--append")
        self.assertEqual(self.text.count(HEADER), 1)

    def test_the_existing_content_is_untouched_and_comes_first(self):
        self.run_tool("--append")
        self.assertTrue(self.text.startswith(EXISTING))

    def test_a_second_run_appends_nothing_new(self):
        self.run_tool("--append")
        first = self.text
        stats = self.run_tool("--append")
        self.assertEqual(stats["appended"], 0)
        self.assertEqual(self.text, first)

    def test_dry_run_writes_nothing(self):
        stats = self.run_tool()
        self.assertEqual(self.text, EXISTING)
        self.assertGreater(stats["appended"], 0)


if __name__ == "__main__":
    unittest.main()
