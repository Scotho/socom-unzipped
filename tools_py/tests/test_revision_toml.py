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


if __name__ == "__main__":
    unittest.main()
