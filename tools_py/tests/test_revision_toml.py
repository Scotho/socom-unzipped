"""tools_py/revision_toml.py: carry a recompiler config from one build's addresses onto another's.

    python -m tools_py.revision_toml <source.toml> <match.json> --out <rev.toml>

Every address here is invented. The toml below has the *shapes* recomp/socom2.toml has -- a stub selector
(`name@0xADDR`), an [mmio] key, a jump-table address and its entry targets, an instruction patch, and the
[performance] names the recompiler never reads -- at round numbers that belong to no build. The one
exception is the two illustrative real numbers in test_libdnas2_shaped_block, which are in the Task 19
report and in the repository already.

What these cases pin:
  * a function-start address moves by its own match;
  * an address inside a matched function's body moves by that function's delta, and says so;
  * a body-interior address riding a `seed+delta` match is marked weak, because the seed pass proves the
    function's bytes, not that nothing inside it was rearranged;
  * a loader-region address is not touched at all, and gets no comment;
  * an address the matcher could not place keeps r0001's number AND is listed in [revision.unresolved],
    so the config says what it does not know;
  * --dry-run writes nothing;
  * every rewritten line carries the r0001 address it came from and the method, next to whatever comment
    the line already had.
"""
import contextlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import unittest

from tools_py import revision_toml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SOURCE = '''\
# A synthetic PS2Recomp configuration
[general]
input = "../game/overlays/socom2_game.elf"
ghidra_output = "socom2_ghidra.csv"
output = "./output/"

stubs = [
  "loaderRoutine@0x00100200",
  "overlayExact@0x00300000",
  "overlayDelta@0x00300400",
  "overlayGone@0x00300800",
]

untracked_stubs = [
  "overlayNote@0x00300000",
]

skip = []

[mmio]
"0x100210" = "0x10000000"
"0x300010" = "0x10003c00"
"0x300410" = "0x1000b020"
"0x300810" = "0x10009000"

[jump_tables]
[[jump_tables.table]]
address = "0x300c00"
entries = [
  { index = 0, target = "0x300020" },
  { index = 1, target = "0x100220" },
]

[patches]
instructions = [
  { address = "0x300018", value = "0x3c03001e" },  # Potential self-modifying code
  { address = "0x100240", value = "0x0" },  # crt0, which does not move
]

[performance]
critical = [
  "sub_00300000", # Contains heavy loops
]
'''

CSV_A = '''\
Name,Start,End,Size
loaderRoutine,0x00100200,0x00100300,256
overlayExact,0x00300000,0x00300100,256
overlayDelta,0x00300400,0x00300500,256
overlayGone,0x00300800,0x00300900,256
'''

MATCHES = {
    "0x00100200": {"name": "loaderRoutine", "b": "0x00100200", "how": "exact"},
    "0x00300000": {"name": "overlayExact", "b": "0x00310000", "how": "exact"},
    "0x00300400": {"name": "overlayDelta", "b": "0x00320400", "how": "seed+delta"},
    "0x00300800": {"name": "overlayGone", "b": None, "how": "unresolved"},
}

FIXED = [(0x00100000, 0x00200000)]


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class Bed(unittest.TestCase):
    """A source toml, a match report and a function table on disk, and the result of translating them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.addCleanup(self.tmp.cleanup)
        self.source = write(os.path.join(d, "socom2.toml"), SOURCE)
        self.csv = write(os.path.join(d, "socom2_ghidra.csv"), CSV_A)
        self.match = write(os.path.join(d, "match.json"), json.dumps({
            "a": {"elf": "a.elf", "csv": self.csv},
            "b": {"elf": "b.elf", "csv": "b.csv"},
            "matches": MATCHES,
            "summary": {"total": 4, "resolved": 3, "unresolved": 1},
        }))
        self.out = os.path.join(d, "socom2_r0004.toml")

    def run_tool(self, *extra):
        """The tool's own run summary is a report for a human; these cases read the file, not the noise."""
        argv = [self.source, self.match, "--csv-a", self.csv, "--fixed", "0x100000-0x200000"] + list(extra)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = revision_toml.main(argv)
        self.printed = buf.getvalue()
        return rc

    def translated(self, *extra):
        """Run the tool for real and return (the written text, the parsed document)."""
        rc = self.run_tool("--out", self.out, *extra)
        self.assertEqual(rc, 0)
        with open(self.out, encoding="utf-8") as fh:
            text = fh.read()
        return text, tomllib.loads(text)

    def line_with(self, text, needle):
        hits = [ln for ln in text.splitlines() if needle in ln]
        self.assertEqual(len(hits), 1, "expected one line holding %r, got %r" % (needle, hits))
        return hits[0]


class TranslationByMatch(Bed):
    def test_stub_selector_moves_to_its_matched_address(self):
        text, doc = self.translated()
        self.assertIn("overlayExact@0x00310000", doc["general"]["stubs"])
        self.assertNotIn("overlayExact@0x00300000", doc["general"]["stubs"])

    def test_a_seed_delta_function_start_is_not_weak(self):
        # The seed pass re-checked this function's fingerprint AND its length at the candidate address,
        # so the START is proven. Only what is read from INSIDE the body rides on the assumption.
        text, doc = self.translated()
        line = self.line_with(text, "overlayDelta@")
        self.assertIn("overlayDelta@0x00320400", line)
        self.assertIn("seed+delta", line)
        self.assertNotIn("weak", line)

    def test_untracked_stubs_move_too(self):
        _text, doc = self.translated()
        self.assertIn("overlayNote@0x00310000", doc["general"]["untracked_stubs"])


class TranslationByBodyDelta(Bed):
    def test_patch_inside_a_matched_body_rides_its_delta(self):
        text, doc = self.translated()
        addrs = [p["address"] for p in doc["patches"]["instructions"]]
        self.assertIn("0x310018", addrs)          # 0x300018 is 0x18 into overlayExact, which moved +0x10000

    def test_mmio_key_inside_a_matched_body_rides_its_delta(self):
        _text, doc = self.translated()
        self.assertIn("0x310010", doc["mmio"])
        self.assertNotIn("0x300010", doc["mmio"])

    def test_the_mmio_value_is_hardware_and_never_translated(self):
        _text, doc = self.translated()
        self.assertEqual(doc["mmio"]["0x310010"], "0x10003c00")

    def test_jump_table_entry_target_rides_its_delta(self):
        _text, doc = self.translated()
        entries = doc["jump_tables"]["table"][0]["entries"]
        self.assertEqual(entries[0]["target"], "0x310020")

    def test_a_body_interior_address_on_a_seed_delta_match_is_marked_weak(self):
        text, doc = self.translated()
        self.assertIn("0x320410", doc["mmio"])
        line = self.line_with(text, "0x320410")
        self.assertIn("seed+delta", line)
        self.assertIn("weak", line)

    def test_libdnas2_shaped_block(self):
        # The one place real numbers appear: the Task 19 report's wholesale +0x7AC0 move of ZSealEtc's
        # libdnas2 block, as a function start and as a byte inside that function.
        tr = revision_toml.Translator(
            matches={0x0062B168: (0x00632C28, "exact")},
            bodies=[(0x0062B168, 0x0062B948, "socom2_RsaGenerateKeyPair")],
            fixed=[(0x00100000, 0x001D5600)])
        self.assertEqual(tr.translate(0x0062B168).addr, 0x00632C28)
        self.assertEqual(tr.translate(0x0062B190).addr, 0x00632C50)
        self.assertTrue(tr.translate(0x0062B190).interior)


class LoaderRegion(Bed):
    def test_a_loader_address_is_left_exactly_as_it_was(self):
        text, doc = self.translated()
        self.assertIn("loaderRoutine@0x00100200", doc["general"]["stubs"])
        self.assertIn("0x100210", doc["mmio"])
        self.assertEqual(doc["jump_tables"]["table"][0]["entries"][1]["target"], "0x100220")
        self.assertIn('  { address = "0x100240", value = "0x0" },  # crt0, which does not move',
                      text.splitlines())

    def test_a_loader_line_gets_no_comment(self):
        text, _doc = self.translated()
        line = self.line_with(text, "loaderRoutine@")
        self.assertNotIn("r0001", line)

    def test_a_loader_address_is_not_in_the_unresolved_table(self):
        _text, doc = self.translated()
        self.assertNotIn("0x00100200", doc["revision"]["unresolved"])


class Unresolved(Bed):
    def test_an_unplaced_function_keeps_its_number(self):
        _text, doc = self.translated()
        self.assertIn("overlayGone@0x00300800", doc["general"]["stubs"])

    def test_an_unplaced_function_is_listed_not_guessed(self):
        _text, doc = self.translated()
        self.assertIn("0x00300800", doc["revision"]["unresolved"])
        self.assertIn("stubs", doc["revision"]["unresolved"]["0x00300800"])

    def test_a_site_inside_an_unplaced_function_is_listed(self):
        _text, doc = self.translated()
        self.assertIn("0x00300810", doc["revision"]["unresolved"])
        self.assertIn("mmio", doc["revision"]["unresolved"]["0x00300810"])

    def test_a_site_in_no_function_at_all_is_listed(self):
        # 0x300c00 is the jump table's own data address; no function body contains it.
        _text, doc = self.translated()
        self.assertEqual(doc["jump_tables"]["table"][0]["address"], "0x300c00")
        self.assertIn("0x00300c00", doc["revision"]["unresolved"])

    def test_an_unresolved_line_says_so_in_the_file(self):
        text, _doc = self.translated()
        self.assertIn("UNRESOLVED", self.line_with(text, "overlayGone@"))

    def test_the_counts_are_in_the_revision_table(self):
        _text, doc = self.translated()
        rev = doc["revision"]
        self.assertEqual(rev["unresolved_count"], len(rev["unresolved"]))
        self.assertGreater(rev["translated"], 0)
        self.assertGreater(rev["unchanged"], 0)


class CommentTrail(Bed):
    def test_a_rewritten_line_names_the_r0001_address_and_the_method(self):
        text, _doc = self.translated()
        line = self.line_with(text, "overlayExact@0x00310000")
        self.assertIn("0x00300000", line)
        self.assertIn("exact", line)

    def test_a_body_line_names_the_function_it_rode(self):
        text, _doc = self.translated()
        line = self.line_with(text, "0x310018")
        self.assertIn("0x00300000", line)          # the function whose delta moved it

    def test_an_existing_comment_survives(self):
        text, _doc = self.translated()
        line = self.line_with(text, "0x310018")
        self.assertIn("Potential self-modifying code", line)
        self.assertIn("0x00300018", line)

    def test_the_output_is_still_valid_toml(self):
        _text, doc = self.translated()
        self.assertEqual(doc["general"]["skip"], [])
        self.assertEqual(doc["performance"]["critical"], ["sub_00300000"])


class GeneralPaths(Bed):
    def test_the_three_paths_are_rewritten(self):
        _text, doc = self.translated("--set-input", "../game/overlays_r0004/x.elf",
                                     "--set-output", "./output_r0004/",
                                     "--set-ghidra-output", "socom2_ghidra_r0004.csv")
        self.assertEqual(doc["general"]["input"], "../game/overlays_r0004/x.elf")
        self.assertEqual(doc["general"]["output"], "./output_r0004/")
        self.assertEqual(doc["general"]["ghidra_output"], "socom2_ghidra_r0004.csv")

    def test_without_them_the_paths_are_untouched(self):
        _text, doc = self.translated()
        self.assertEqual(doc["general"]["input"], "../game/overlays/socom2_game.elf")


class DryRun(Bed):
    def test_it_writes_nothing(self):
        rc = self.run_tool("--out", self.out, "--dry-run")
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(self.out))

    def test_it_prints_the_translation_table(self):
        proc = subprocess.run([sys.executable, "-m", "tools_py.revision_toml", self.source, self.match,
                               "--csv-a", self.csv, "--fixed", "0x100000-0x200000", "--dry-run"],
                              capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("0x00300000 -> 0x00310000", proc.stdout)
        self.assertIn("0x00300800", proc.stdout)
        self.assertIn("unresolved", proc.stdout)


class Regions(unittest.TestCase):
    def test_a_byte_identical_segment_is_a_fixed_region(self):
        a = [(0x100000, b"loader"), (0x1e7000, b"AAAA")]
        b = [(0x100000, b"loader"), (0x1e7000, b"BBBBBB")]
        self.assertEqual(revision_toml.fixed_regions(a, b), [(0x100000, 0x100006)])

    def test_adjacent_fixed_segments_merge(self):
        a = [(0x100000, b"aaaa"), (0x100004, b"bb")]
        b = [(0x100000, b"aaaa"), (0x100004, b"bb")]
        self.assertEqual(revision_toml.fixed_regions(a, b), [(0x100000, 0x100006)])


# ---- the data-reference pass ----------------------------------------------------------------
#
# A jump table's base is not a function start, so the function matcher never has an opinion about it
# (Task 19's concern 1: all 24 overlay bases unresolved). The base IS loaded, by a lui/lo pair, inside
# the function that switches through it -- so it can be read out of the other image instead of guessed.
# Everything below is synthetic: two little ELFs built here, holding functions whose only real property
# is the shape of a MIPS switch.

def elf32(segments):
    """The smallest little-endian ELF32 that `address_matcher.load_segments` will read."""
    phoff, phent = 52, 32
    head = bytearray(52)
    head[0:4] = b"\x7fELF"
    head[4:6] = b"\x01\x01"
    struct.pack_into("<I", head, 28, phoff)
    struct.pack_into("<HH", head, 42, phent, len(segments))
    body, phdrs = bytearray(), bytearray()
    off = phoff + phent * len(segments)
    for vaddr, data in segments:
        phdrs += struct.pack("<8I", 1, off + len(body), vaddr, vaddr, len(data), len(data), 5, 0x1000)
        body += data
    return bytes(head) + bytes(phdrs) + bytes(body)


def switch_body(seed, base, cases=None):
    """28 words: filler, then `sll/lui/addu/lw/jr` -- the switch that reads its table at `base`.

    The filler is `addiu v0, zero, imm`, whose immediate is a constant and not an address, so it is
    part of the shape the anchor matches on; the lui's and the lw's immediates are the address and are
    exactly what the anchor must NOT match on. `cases` puts the switch's own `sltiu v0, v0, N` guard in
    front of it, which is how many entries its table really has."""
    pre = [0x24020000 | ((seed * 0x137 + i * 7) & 0xFFFF) for i in range(14)]
    if cases is not None:
        pre[12] = 0x2C420000 | cases              # sltiu v0, v0, cases
    core = [0x00021080,                       # sll   v0, v0, 2
            0x3C030000 | ((base >> 16) & 0xFFFF),   # lui   v1, %hi(base)
            0x00621821,                       # addu  v1, v1, v0
            0x8C630000 | (base & 0xFFFF),     # lw    v1, %lo(base)(v1)
            0x00600008,                       # jr    v1
            0x00000000]                       # nop
    post = [0x00000021 | (((seed * 0x1D + i) & 0xFFFF) << 6) for i in range(8)]
    return pre + core + post


LUI_INDEX = 15                                # where switch_body puts the lui
SW_BYTES = 28 * 4
MMIO_AT = 5                                   # where with_mmio puts the access in switch_body's filler


def with_mmio(words, reg):
    """`lui at, %hi(reg)` then `sw t5, %lo(reg)(at)` in the filler: an access to a hardware register.

    Both immediates are addresses, so `normalize` drops both -- which is exactly the point. The anchor
    has to place this instruction on the shape of the code around it, and the REGISTER is then a
    separate, independent thing to check at whatever address it landed on."""
    out = list(words)
    hi = ((reg >> 16) + (1 if (reg & 0xFFFF) >= 0x8000 else 0)) & 0xFFFF
    out[MMIO_AT - 1] = 0x3C010000 | hi                    # lui at, %hi(reg)
    out[MMIO_AT] = 0xAC2D0000 | (reg & 0xFFFF)            # sw  t5, %lo(reg)(at)
    return out


def blob(words):
    return b"".join(w.to_bytes(4, "little") for w in words)


def image(size, placements):
    """One segment's bytes: {offset: [words]} laid into `size` zero bytes."""
    buf = bytearray(size)
    for off, words in placements.items():
        buf[off:off + 4 * len(words)] = blob(words)
    return bytes(buf)


# The A build: four switching functions, their tables, a patch site and an [mmio] access inside each.
A_MOVED, A_DRIFT, A_GONE, A_RECAST, A_RELABEL = (0x00300040, 0x003000B0, 0x00300120,
                                                 0x00300190, 0x00300200)
A_T1, A_T2, A_T3, A_T4, A_TR = 0x00300C00, 0x00300C40, 0x00300C80, 0x00300CC0, 0x00300D00
# The B build: `moved` moved (and the matcher placed it), `drifted` moved and the matcher did NOT,
# `recast` moved and its own code changed, so nothing anchors it, `relabelled` moved and anchors but
# its access now forms a different register, and `vanished` is not there at all.
B_MOVED, B_DRIFT, B_RECAST, B_RELABEL = 0x00300240, 0x003002B0, 0x00300320, 0x00300390
B_T1, B_T4, B_T2, B_TR = 0x00300E00, 0x00300E20, 0x00300E40, 0x00300D40

# The hardware registers the [mmio] keys annotate. They belong to the machine, not to the build, so
# they read the same in both images -- which is what makes them evidence about a placement.
MMIO_MOVED, MMIO_DRIFT, MMIO_GONE, MMIO_RELABEL = 0x10003C00, 0x1000E000, 0x10009000, 0x1000B400

_a_moved = with_mmio(switch_body(1, A_T1, cases=2), MMIO_MOVED)
_b_moved = with_mmio(switch_body(1, B_T1, cases=2), MMIO_MOVED)
_a_drift = with_mmio(switch_body(2, A_T2), MMIO_DRIFT)
_b_drift = with_mmio(switch_body(2, B_T2), MMIO_DRIFT)
_b_drift[22] = 0x00000025                     # one word changed, well outside the anchor's window
_a_gone = with_mmio(switch_body(3, A_T3), MMIO_GONE)
_a_recast = switch_body(4, A_T4, cases=2)
_b_recast = switch_body(4, B_T4, cases=9)     # a bound nine entries long, over a table two entries long
_b_recast[13] = 0x24020123                    # a word INSIDE every window: this site cannot be anchored
_a_relabel = with_mmio(switch_body(5, A_TR), MMIO_RELABEL)
# The same code, and the same shape once the addresses are masked out -- but this build's store forms
# a register 0x20 along. The window lands here; the key's own claim does not.
_b_relabel = with_mmio(switch_body(5, B_TR), MMIO_RELABEL + 0x20)

A_ELF = elf32([(0x00300000, image(0x1000, {
    A_MOVED - 0x300000: _a_moved,
    A_DRIFT - 0x300000: _a_drift,
    A_GONE - 0x300000: _a_gone,
    A_T1 - 0x300000: [A_MOVED + 0x40, A_MOVED + 0x50],
    A_T2 - 0x300000: [A_DRIFT + 0x40, A_DRIFT + 0x50],
    A_T3 - 0x300000: [A_GONE + 0x40, A_GONE + 0x50],
    A_RECAST - 0x300000: _a_recast,
    A_T4 - 0x300000: [A_RECAST + 0x40, A_RECAST + 0x50],
    A_RELABEL - 0x300000: _a_relabel,
    A_TR - 0x300000: [A_RELABEL + 0x40, A_RELABEL + 0x50],
}))])
B_ELF = elf32([(0x00300000, image(0x1000, {
    B_MOVED - 0x300000: _b_moved,
    B_DRIFT - 0x300000: _b_drift,
    B_T1 - 0x300000: [B_MOVED + 0x40, B_MOVED + 0x50],
    B_T2 - 0x300000: [B_DRIFT + 0x40, B_DRIFT + 0x50, B_DRIFT + 0x60],   # r0004 grew a case
    B_RECAST - 0x300000: _b_recast,
    B_T4 - 0x300000: [B_RECAST + 0x40, B_RECAST + 0x50],
    B_RELABEL - 0x300000: _b_relabel,
    B_TR - 0x300000: [B_RELABEL + 0x40, B_RELABEL + 0x50],
}))])

ANCHOR_SOURCE = '''\
[general]
input = "../game/overlays/socom2_game.elf"
ghidra_output = "socom2_ghidra.csv"
output = "./output/"

stubs = []
untracked_stubs = []
skip = []

[mmio]
"0x300054" = "0x10003c00"  # inside `moved`, which the matcher placed
"0x3000c4" = "0x1000e000"  # inside `drifted`: only the code around it can place this
"0x300134" = "0x10009000"  # inside `vanished`, which is not in the B build at all
"0x300214" = "0x1000b400"  # inside `relabelled`: the window lands, the register does not

[jump_tables]
[[jump_tables.table]]
address = "0x300c00"
entries = [
  { index = 0, target = "0x300080" },
  { index = 1, target = "0x300090" },
]

[[jump_tables.table]]
address = "0x300cc0"
entries = [
  { index = 0, target = "0x3001d0" },
  { index = 1, target = "0x3001e0" },
]

[[jump_tables.table]]
address = "0x300c40"
entries = [
  { index = 0, target = "0x3000f0" },
  { index = 1, target = "0x300100" },
]

[[jump_tables.table]]
address = "0x300c80"
entries = [
  { index = 0, target = "0x300160" },
  { index = 1, target = "0x300170" },
]

[patches]
instructions = [
  { address = "0x3000b4", value = "0x0" },  # inside `drifted`, which the matcher could not place
  { address = "0x300124", value = "0x0" },  # inside `vanished`, which is not in the B build at all
]
'''

ANCHOR_CSV = '''\
Name,Start,End,Size
moved,0x00300040,0x003000B0,112
drifted,0x003000B0,0x00300120,112
vanished,0x00300120,0x00300190,112
recast,0x00300190,0x00300200,112
relabelled,0x00300200,0x00300270,112
'''

ANCHOR_MATCHES = {
    "0x00300040": {"name": "moved", "b": "0x00300240", "how": "exact"},
    "0x003000B0": {"name": "drifted", "b": None, "how": "unresolved"},
    "0x00300120": {"name": "vanished", "b": None, "how": "unresolved"},
    "0x00300190": {"name": "recast", "b": None, "how": "unresolved"},
    "0x00300200": {"name": "relabelled", "b": None, "how": "unresolved"},
}


class AnchorBed(unittest.TestCase):
    """Both images on disk, so the tool can read a base out of the B build instead of guessing it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        self.source = write(os.path.join(d, "socom2.toml"), ANCHOR_SOURCE)
        self.csv = write(os.path.join(d, "socom2_ghidra.csv"), ANCHOR_CSV)
        self.elf_a = os.path.join(d, "a.elf")
        self.elf_b = os.path.join(d, "b.elf")
        with open(self.elf_a, "wb") as fh:
            fh.write(A_ELF)
        with open(self.elf_b, "wb") as fh:
            fh.write(B_ELF)
        self.match = write(os.path.join(d, "match.json"), json.dumps({
            "a": {"elf": self.elf_a, "csv": self.csv},
            "b": {"elf": self.elf_b, "csv": "b.csv"},
            "matches": ANCHOR_MATCHES,
            "summary": {"total": 5, "resolved": 1, "unresolved": 4},
        }))
        self.out = os.path.join(d, "socom2_r0004.toml")

    def translated(self, *extra):
        argv = [self.source, self.match, "--csv-a", self.csv, "--fixed", "0x100000-0x200000",
                "--elf-a", self.elf_a, "--elf-b", self.elf_b, "--out", self.out] + list(extra)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = revision_toml.main(argv)
        self.printed = buf.getvalue()
        self.assertEqual(rc, 0, self.printed)
        with open(self.out, encoding="utf-8") as fh:
            text = fh.read()
        return text, tomllib.loads(text)

    def table(self, doc, base):
        for t in doc["jump_tables"]["table"]:
            if int(t["address"], 16) == base:
                return t
        return None

    line_with = Bed.line_with


class JumpTableBases(AnchorBed):
    def test_a_base_inside_a_matched_function_is_read_from_the_b_image(self):
        # `moved` matched exact, so the lui is at the same offset in the B body; the base is whatever
        # that lui and its lw form -- not an r0001 number, and not a guess.
        _text, doc = self.translated()
        self.assertIsNotNone(self.table(doc, B_T1))
        self.assertIsNone(self.table(doc, A_T1))

    def test_a_base_in_a_function_the_matcher_lost_is_found_by_the_code_around_it(self):
        _text, doc = self.translated()
        self.assertIsNotNone(self.table(doc, B_T2))
        self.assertIsNone(self.table(doc, A_T2))

    def test_the_line_names_the_r0001_base_the_count_and_the_use_site(self):
        text, _doc = self.translated()
        line = [ln for ln in text.splitlines() if ln.startswith('address = "0x300e00"')][0]
        self.assertIn("0x00300c00", line)
        self.assertIn("2 entries", line)
        self.assertIn("0x%08x" % (A_MOVED + LUI_INDEX * 4), line)      # the r0001 use site
        self.assertIn("moved", line)                                   # the function that switches

    def test_the_entries_are_the_b_image_s_own_words(self):
        _text, doc = self.translated()
        targets = [e["target"] for e in self.table(doc, B_T1)["entries"]]
        self.assertEqual([int(t, 16) for t in targets], [B_MOVED + 0x40, B_MOVED + 0x50])

    def test_the_count_comes_from_the_switch_s_own_bound_when_it_has_one(self):
        text, _doc = self.translated()
        line = [ln for ln in text.splitlines() if ln.startswith('address = "0x300e00"')][0]
        self.assertIn("sltiu", line)

    def test_a_bound_that_does_not_read_as_a_table_is_not_taken(self):
        # `recast`'s guard admits nine cases; only two words after its base read as targets. The bound
        # is evidence, not an instruction: when it does not hold up, the run of targets answers instead.
        text, doc = self.translated()
        self.assertEqual(len(self.table(doc, B_T4)["entries"]), 2)
        line = [ln for ln in text.splitlines() if ln.startswith('address = "0x300e20"')][0]
        self.assertIn("run of targets", line)

    def test_a_grown_table_gets_the_extra_entry(self):
        _text, doc = self.translated()
        entries = self.table(doc, B_T2)["entries"]
        self.assertEqual(len(entries), 3)
        self.assertEqual(int(entries[2]["target"], 16), B_DRIFT + 0x60)
        self.assertEqual([e["index"] for e in entries], [0, 1, 2])

    def test_a_function_that_is_not_in_the_b_image_leaves_its_table_unresolved(self):
        text, doc = self.translated()
        self.assertIsNotNone(self.table(doc, A_T3))
        self.assertIn("0x00300c80", doc["revision"]["unresolved"])
        self.assertIn("UNRESOLVED", [ln for ln in text.splitlines()
                                     if ln.startswith('address = "0x300c80"')][0])

    def test_the_counts_say_how_many_tables_were_placed(self):
        _text, doc = self.translated()
        self.assertEqual(doc["revision"]["jump_tables_resolved"], 3)
        self.assertEqual(doc["revision"]["jump_tables_unresolved"], 1)

    def test_a_site_nothing_anchors_is_placed_by_order_and_by_the_table_s_own_pattern(self):
        # `recast`'s own code changed around the site, so no window matches it. What is still true is
        # that its table sits between its neighbours' tables in this build too, and that a switch has
        # the same pattern of repeated targets in both builds. One candidate survives both; if two had,
        # the table would stay unresolved.
        text, doc = self.translated()
        self.assertIsNotNone(self.table(doc, B_T4))
        self.assertIsNone(self.table(doc, A_T4))
        line = [ln for ln in text.splitlines() if ln.startswith('address = "0x300e20"')][0]
        self.assertIn("0x00300cc0", line)
        self.assertIn("pattern", line)
        self.assertIn("0x%08x" % B_T1, line)
        self.assertIn("0x%08x" % B_T2, line)

    def test_that_table_s_entries_are_this_build_s_own_words(self):
        _text, doc = self.translated()
        targets = [int(e["target"], 16) for e in self.table(doc, B_T4)["entries"]]
        self.assertEqual(targets, [B_RECAST + 0x40, B_RECAST + 0x50])


class AnchoredPatches(AnchorBed):
    def test_a_patch_in_a_function_the_matcher_lost_is_anchored_by_its_window(self):
        _text, doc = self.translated()
        addrs = [int(p["address"], 16) for p in doc["patches"]["instructions"]]
        self.assertIn(B_DRIFT + 4, addrs)
        self.assertNotIn(A_DRIFT + 4, addrs)

    def test_a_patch_with_nowhere_to_land_stays_unresolved(self):
        _text, doc = self.translated()
        addrs = [int(p["address"], 16) for p in doc["patches"]["instructions"]]
        self.assertIn(A_GONE + 4, addrs)
        self.assertIn("0x%08x" % (A_GONE + 4), doc["revision"]["unresolved"])

    def test_the_anchored_line_says_how_it_was_placed(self):
        text, _doc = self.translated()
        line = [ln for ln in text.splitlines() if "0x%x" % (B_DRIFT + 4) in ln][0]
        self.assertIn("0x%08x" % (A_DRIFT + 4), line)
        self.assertIn("window", line)


class AnchoredMmio(AnchorBed):
    """An [mmio] key is an INSTRUCTION address, so the same anchor places it -- and unlike a patch it
    carries its own evidence: the hardware register it says that instruction touches."""

    def keys(self, doc):
        return sorted(int(k, 16) for k in doc["mmio"])

    def test_a_key_in_a_function_the_matcher_lost_is_anchored_by_its_window(self):
        _text, doc = self.translated()
        self.assertIn(B_DRIFT + MMIO_AT * 4, self.keys(doc))
        self.assertNotIn(A_DRIFT + MMIO_AT * 4, self.keys(doc))

    def test_a_key_inside_a_matched_function_still_rides_that_match(self):
        text, doc = self.translated()
        self.assertIn(B_MOVED + MMIO_AT * 4, self.keys(doc))
        line = self.line_with(text, "0x%x" % (B_MOVED + MMIO_AT * 4))
        self.assertIn("body+0x%x of 0x%08x exact" % (MMIO_AT * 4, A_MOVED), line)

    def test_the_value_is_the_hardware_register_and_is_never_touched(self):
        _text, doc = self.translated()
        self.assertEqual(doc["mmio"]["0x%x" % (B_DRIFT + MMIO_AT * 4)], "0x%x" % MMIO_DRIFT)

    def test_a_key_with_nowhere_to_land_stays_unresolved_and_listed(self):
        _text, doc = self.translated()
        self.assertIn(A_GONE + MMIO_AT * 4, self.keys(doc))
        self.assertIn("0x%08x" % (A_GONE + MMIO_AT * 4), doc["revision"]["unresolved"])

    def test_that_reason_says_the_code_around_it_does_not_recur(self):
        _text, doc = self.translated()
        self.assertIn("window", doc["revision"]["unresolved"]["0x%08x" % (A_GONE + MMIO_AT * 4)])

    def test_a_placement_whose_code_forms_another_register_is_refused(self):
        # `relabelled`'s window lands squarely on the B body -- every address immediate is masked out,
        # so a store to a different register has the same shape. What is NOT the same is the register
        # the key annotates, and that is the whole content of the key. Refuse, do not guess.
        _text, doc = self.translated()
        self.assertIn(A_RELABEL + MMIO_AT * 4, self.keys(doc))
        self.assertNotIn(B_RELABEL + MMIO_AT * 4, self.keys(doc))
        why = doc["revision"]["unresolved"]["0x%08x" % (A_RELABEL + MMIO_AT * 4)]
        self.assertIn("0x%08x" % (MMIO_RELABEL + 0x20), why)
        self.assertIn("0x%08x" % MMIO_RELABEL, why)

    def test_the_anchored_line_says_how_it_was_placed_and_that_the_register_holds(self):
        text, _doc = self.translated()
        line = self.line_with(text, "0x%x" % (B_DRIFT + MMIO_AT * 4))
        self.assertIn("0x%08x" % (A_DRIFT + MMIO_AT * 4), line)
        self.assertIn("window", line)
        self.assertIn("0x%08x" % MMIO_DRIFT, line)

    def test_the_counts_say_how_many_were_anchored(self):
        _text, doc = self.translated()
        self.assertEqual(doc["revision"]["anchored"], 2)       # one [mmio] key, one patch

    def test_no_data_refs_leaves_every_key_where_it_was(self):
        _text, doc = self.translated("--no-data-refs")
        self.assertIn(A_DRIFT + MMIO_AT * 4, self.keys(doc))
        self.assertNotIn(B_DRIFT + MMIO_AT * 4, self.keys(doc))


class DataRefsOffWithoutBothImages(Bed):
    def test_without_the_two_images_a_base_is_still_left_alone(self):
        # The pass needs both builds' bytes. The original bed passes --fixed and no ELFs, so the tool
        # must behave exactly as it did before: the base keeps r0001's number and says so.
        _text, doc = self.translated()
        self.assertEqual(doc["jump_tables"]["table"][0]["address"], "0x300c00")
        self.assertIn("0x00300c00", doc["revision"]["unresolved"])

    def test_without_the_two_images_an_mmio_key_in_a_lost_function_stays_unresolved(self):
        _text, doc = self.translated()
        self.assertIn("0x300810", doc["mmio"])
        self.assertIn("0x00300810", doc["revision"]["unresolved"])


class AnchorUnits(unittest.TestCase):
    def test_normalize_keeps_the_shape_and_drops_the_address(self):
        lui_a = 0x3C030030
        lui_b = 0x3C030031
        self.assertEqual(revision_toml.normalize(lui_a), revision_toml.normalize(lui_b))
        self.assertNotEqual(revision_toml.normalize(lui_a), revision_toml.normalize(0x3C040030))

    def test_normalize_keeps_a_stack_offset_because_it_is_not_an_address(self):
        self.assertNotEqual(revision_toml.normalize(0xFFBF0010), revision_toml.normalize(0xFFBF0020))

    def test_a_lui_addiu_pair_forms_the_address_with_the_sign_carried(self):
        self.assertEqual(revision_toml.form_address(0x3C030030, 0x24630C00), 0x00300C00)
        self.assertEqual(revision_toml.form_address(0x3C030031, 0x2463FFF0), 0x0030FFF0)

    def test_the_switch_s_bound_is_read_off_the_guard_in_front_of_it(self):
        img = revision_toml.CodeImage([(0x00300000, blob(switch_body(1, 0x00300C00, cases=7)))])
        self.assertEqual(img.switch_bound(0x00300000 + LUI_INDEX * 4), 7)
        plain = revision_toml.CodeImage([(0x00300000, blob(switch_body(1, 0x00300C00)))])
        self.assertIsNone(plain.switch_bound(0x00300000 + LUI_INDEX * 4))

    def test_a_store_that_happens_to_form_the_address_is_not_a_use_site(self):
        # `sw v0, 0xc00(v1)` after `lui v1,0x30` adds up to 0x300c00 as surely as the lw does -- and it
        # is a write into somebody's struct, not a read of a jump table. Counting it made two of the
        # real 24 bases look ambiguous.
        words = switch_body(1, 0x00300C00) + [0x3C030030, 0xAC620C00]
        img = revision_toml.CodeImage([(0x00300000, blob(words))])
        self.assertEqual(img.lui_sites_for(0x00300C00),
                         [(0x00300000 + LUI_INDEX * 4, 0x00300000 + (LUI_INDEX + 2) * 4)])

    def test_the_image_finds_the_pair_that_forms_a_base(self):
        img = revision_toml.CodeImage([(0x00300000, blob(switch_body(1, 0x00300C00)))])
        self.assertEqual(img.lui_sites_for(0x00300C00),
                         [(0x00300000 + LUI_INDEX * 4, 0x00300000 + (LUI_INDEX + 2) * 4)])


class MmioUnits(unittest.TestCase):
    """What an [mmio] key claims -- that the instruction here touches that register -- read back out
    of the image, so a placement can be checked instead of trusted."""

    def img(self, words):
        return revision_toml.CodeImage([(0x00300000, blob(words))])

    def test_the_register_is_read_off_the_lui_that_sets_the_base(self):
        img = self.img(with_mmio(switch_body(1, 0x00300C00), 0x1000E000))
        self.assertEqual(img.formed_register(0x00300000 + MMIO_AT * 4), 0x1000E000)

    def test_an_access_with_no_lui_in_reach_is_not_checkable(self):
        # The base register came from somewhere else -- an argument, a struct field, a `lui` further
        # back than the reach. Nothing is wrong; this key's claim just cannot be read off the code.
        words = switch_body(1, 0x00300C00)
        words[MMIO_AT] = 0xAC2DE000                       # sw t5, -0x2000(at), with no lui above it
        self.assertIsNone(self.img(words).formed_register(0x00300000 + MMIO_AT * 4))

    def test_a_base_register_written_in_between_is_not_derivable(self):
        words = with_mmio(switch_body(1, 0x00300C00), 0x1000E000)
        words[MMIO_AT - 1], words[MMIO_AT - 2] = 0x24010004, words[MMIO_AT - 1]   # addiu at, zero, 4
        self.assertIsNone(self.img(words).formed_register(0x00300000 + MMIO_AT * 4))

    def test_an_instruction_that_is_not_a_load_or_a_store_forms_nothing(self):
        img = self.img(with_mmio(switch_body(1, 0x00300C00), 0x1000E000))
        self.assertIsNone(img.formed_register(0x00300000 + LUI_INDEX * 4))

class RepoRelativeProvenance(Bed):
    """The `[revision]` table names the two files it was written from, and names them the way the
    repository does.

    `scripts/build_revision.sh` resolves every input to an absolute path before step 1, and step 3 rewrites
    the TRACKED `recomp/socom2_<rev>.toml` on every build. So writing the caller's paths through meant the
    generated file said `C:/projects/socom_pc/recomp/socom2.toml` -- true on the machine that built it, and
    a modification in `git status` for every other machine that builds that revision. The provenance is
    about files in this repository; it names them relative to its root.

    The temporary directory these cases work in is made under `recomp/build/`, which is git-ignored, so a
    run killed before its cleanup leaves nothing for `git status` to find either.
    """

    def setUp(self):
        super().setUp()
        build = os.path.join(ROOT, "recomp", "build")
        os.makedirs(build, exist_ok=True)
        self.inside = tempfile.mkdtemp(dir=build, prefix="revision_toml_test_")
        self.addCleanup(shutil.rmtree, self.inside, True)
        self.rel = "recomp/build/" + os.path.basename(self.inside)
        self.source = shutil.copy(self.source, os.path.join(self.inside, "socom2.toml"))
        self.match = shutil.copy(self.match, os.path.join(self.inside, "match.json"))

    def test_an_absolute_path_inside_the_repository_is_written_relative_to_its_root(self):
        _text, doc = self.translated()
        self.assertEqual(doc["revision"]["source"], self.rel + "/socom2.toml")
        self.assertEqual(doc["revision"]["match"], self.rel + "/match.json")

    def test_the_written_config_holds_no_absolute_path_at_all(self):
        text, _doc = self.translated()
        hits = [ln for ln in text.splitlines() if re.search(r"[A-Za-z]:[\\/]", ln)]
        self.assertEqual(hits, [], "a tracked generated file cannot carry one machine's paths: %r" % hits)

    def test_the_comment_above_the_table_says_the_same_two_paths(self):
        text, _doc = self.translated()
        line = self.line_with(text, "Written by tools_py/revision_toml.py from")
        self.assertIn(self.rel + "/socom2.toml", line)
        self.assertIn(self.rel + "/match.json", line)


class RepoRelativeHelper(unittest.TestCase):
    def test_a_path_inside_the_repository_loses_the_root_and_the_backslashes(self):
        self.assertEqual(revision_toml.repo_relative(os.path.join(ROOT, "recomp", "socom2.toml")),
                         "recomp/socom2.toml")

    def test_a_path_relative_to_the_working_directory_is_resolved_and_stays_relative(self):
        here = os.getcwd()
        os.chdir(ROOT)
        self.addCleanup(os.chdir, here)
        self.assertEqual(revision_toml.repo_relative("recomp/socom2.toml"), "recomp/socom2.toml")

    def test_a_path_outside_the_repository_is_left_as_it_came(self):
        outside = os.path.abspath(os.path.join(ROOT, os.pardir, "elsewhere", "socom2.toml"))
        self.assertEqual(revision_toml.repo_relative(outside), outside.replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()
