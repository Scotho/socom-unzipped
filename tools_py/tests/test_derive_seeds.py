"""Sprint 12 Task 5 -- the r0004 seed list (tools_py/derive_seeds.py).

A seed is an (a, b) pair whose offset b - a the matcher's seed+delta pass tries on every function the
fingerprint passes left over. `derive_seeds` reads those offsets off the matcher's own `exact`
placements, so the seed list is a pure function of a seedless match.json and the whole run is
reproducible from tracked inputs. Every image here is SYNTHETIC (the assembler and the minimal ELF
writer are test_address_matcher's); nothing reads game/.
"""
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from tools_py import address_matcher as am
from tools_py import derive_seeds as ds
from tools_py.tests.test_address_matcher import (
    A0, A1, S0, V0, addiu, addu, jr_ra, lui, lw, minimal_elf32, subu, sw, NOP, _hi_lo, _pad)


def row(b, how):
    return {"name": "", "b": b, "how": how, "tie": None}


# Offsets: +0x10 three times, +0x100 twice, -0x10 and 0 once each; the rest are not `exact`.
SYNTHETIC = {"matches": {
    "0x00100020": row("0x00100030", "exact"),        # +0x10, listed before the lower address
    "0x00100000": row("0x00100010", "exact"),        # +0x10, the lowest a with that offset
    "0x00100040": row("0x00100050", "exact"),        # +0x10
    "0x00200040": row("0x00200140", "exact"),        # +0x100
    "0x00200000": row("0x00200100", "exact"),        # +0x100, the lowest
    "0x00300000": row("0x002ffff0", "exact"),        # -0x10
    "0x00400000": row("0x00400000", "exact"),        # 0
    "0x00500000": row("0x00555500", "hash+callees"),  # +0x55500 -- not an exact placement
    "0x00600000": row("0x00666600", "relinked-body"),
    "0x00700000": row("0x00777700", "seed+delta"),
    "0x00800000": row(None, "unresolved"),
}}


class TestDerive(unittest.TestCase):
    def test_one_seed_per_offset_most_frequent_first_then_ascending_offset(self):
        self.assertEqual(ds.derive_seeds(SYNTHETIC), [
            (0x00100000, 0x00100010),      # +0x10  x3
            (0x00200000, 0x00200100),      # +0x100 x2
            (0x00300000, 0x002FFFF0),      # -0x10  x1 (ties broken by the offset, ascending)
            (0x00400000, 0x00400000),      # 0      x1
        ])

    def test_only_exact_placements_give_an_offset(self):
        # Pinned: hash+callees is left out. On the real r0004 pair adding its offsets gains three
        # functions but re-pairs four seed+delta placements, so it does not "never hurt".
        offsets = {b - a for a, b in ds.derive_seeds(SYNTHETIC)}
        for other in (0x55500, 0x66600, 0x77700):
            self.assertNotIn(other, offsets)

    def test_min_count_drops_the_rare_offsets(self):
        self.assertEqual(ds.derive_seeds(SYNTHETIC, min_count=2),
                         [(0x00100000, 0x00100010), (0x00200000, 0x00200100)])

    def test_the_bare_matches_mapping_is_accepted_too(self):
        self.assertEqual(ds.derive_seeds(SYNTHETIC["matches"]), ds.derive_seeds(SYNTHETIC))

    def test_the_histogram_counts_each_offset(self):
        self.assertEqual(ds.offset_histogram(SYNTHETIC)[:2], [(0x10, 3), (0x100, 2)])


class TestSeedFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="seeds_")
        self.path = os.path.join(self.dir, "seeds.txt")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_seed_file_round_trips(self):
        seeds = ds.derive_seeds(SYNTHETIC)
        ds.write_seeds(self.path, seeds, header="python -m tools_py.derive_seeds x.json")
        self.assertEqual(ds.read_seeds(self.path), seeds)

    def test_the_format_is_one_upper_hex_pair_per_line_under_one_header(self):
        ds.write_seeds(self.path, [(0x180008, 0x180008), (0x2FFFF0, 0x300000)], header="cmd; a 3 rows")
        with open(self.path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(lines, ["# cmd; a 3 rows", "0x00180008=0x00180008", "0x002FFFF0=0x00300000"])

    def test_the_header_is_kept_out_of_read_seeds(self):
        ds.write_seeds(self.path, [(0x10, 0x20)], header="0x99=0x99 looks like a seed but is a comment")
        self.assertEqual(ds.read_seeds(self.path), [(0x10, 0x20)])

    def test_the_file_parses_as_address_matcher_seed_arguments(self):
        seeds = ds.derive_seeds(SYNTHETIC)
        ds.write_seeds(self.path, seeds, header="h")
        with open(self.path, encoding="utf-8") as fh:
            args = [ln for ln in fh.read().splitlines() if not ln.startswith("#")]
        self.assertEqual([am.parse_seed(x) for x in args], seeds)


# ---- end to end: a two-segment relink --------------------------------------------------------

BASE1, BASE2 = 0x00100000, 0x00200000
DATA1, DATA2 = 0x00400000, 0x00480000
D1, D2 = 0x2C9C0, 0x1240                   # each segment relinked by its own offset
SIZE = 0x20


def build_two_segment(relinked):
    """(funcs, segments): two code segments, each with unique bodies and a pair of GLOBAL TWINS.

    A twin pair reaches a moved global (`lui`/`addiu` then a load through it) with bodies identical to
    the last register. The global's address moves with the link, but a `lui`/`addiu` pair is zeroed out
    of both hashes, so each twin fingerprints the same in both images -- and the same as its sibling.
    `exact` needs one occurrence, `hash+callees` needs a call, `relinked-body` sees one masked hash
    twice with no callee and no string to break the tie: none of them can say which twin is which.
    Only the segment's offset can.
    """
    d1, d2 = (D1, D2) if relinked else (0, 0)
    g1hi, g1lo = _hi_lo(DATA1 + d1)
    g2hi, g2lo = _hi_lo(DATA2 + d2)
    seg1 = [
        ("leafA", [addu(V0, A0, A1), jr_ra(), NOP]),
        ("leafB", [subu(V0, A0, A1), jr_ra(), NOP]),
        ("fieldC", [lw(V0, S0, 0xB4), addu(V0, V0, A0), sw(V0, S0, 0xB8), jr_ra(), NOP]),
        ("gTwin1", [lui(A0, g1hi), addiu(A0, A0, g1lo), lw(V0, A0, 0), addu(V0, V0, A1), jr_ra(), NOP]),
        ("gTwin2", [lui(A0, g1hi), addiu(A0, A0, g1lo), lw(V0, A0, 0), addu(V0, V0, A1), jr_ra(), NOP]),
    ]
    seg2 = [
        ("fieldD", [lw(V0, S0, 0x40), jr_ra(), NOP]),
        ("fieldE", [sw(A0, S0, 0x44), jr_ra(), NOP]),
        ("gTwin3", [lui(A1, g2hi), addiu(A1, A1, g2lo), lw(V0, A1, 8), subu(V0, V0, A0), jr_ra(), NOP]),
        ("gTwin4", [lui(A1, g2hi), addiu(A1, A1, g2lo), lw(V0, A1, 8), subu(V0, V0, A0), jr_ra(), NOP]),
    ]
    funcs, segs = [], []
    for base, body in ((BASE1 + d1, seg1), (BASE2 + d2, seg2)):
        blob = b"".join(w.to_bytes(4, "little") for _n, words in body for w in _pad(words))
        funcs += [(base + i * SIZE, base + (i + 1) * SIZE, n) for i, (n, _w) in enumerate(body)]
        segs.append((base, blob))
    return funcs, segs


def as_doc(matches):
    """The address_matcher --out shape, from match()'s return value."""
    return {"matches": {"0x%08x" % a: {"b": None if b is None else "0x%08x" % b, "how": how}
                        for a, (b, how) in matches.items()}}


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.a_funcs, self.a_segs = build_two_segment(False)
        self.b_funcs, self.b_segs = build_two_segment(True)
        self.truth = {a: b for (a, _e, _n), (b, _f, _m) in zip(self.a_funcs, self.b_funcs)}
        self.name = {a: n for a, _e, n in self.a_funcs}

    def test_seeds_from_the_seedless_run_place_the_global_twins(self):
        first = am.match(self.a_funcs, self.a_segs, self.b_funcs, self.b_segs)
        left = sorted(self.name[a] for a, (b, how) in first.items() if how == "unresolved")
        self.assertEqual(left, ["gTwin1", "gTwin2", "gTwin3", "gTwin4"])

        seeds = ds.derive_seeds(as_doc(first))
        self.assertEqual([b - a for a, b in seeds], [D1, D2])     # 3 exact in seg 1, 2 in seg 2
        for a, b in seeds:
            self.assertEqual(b, self.truth[a])                    # every seed is a real pair

        second = am.match(self.a_funcs, self.a_segs, self.b_funcs, self.b_segs, seeds=dict(seeds))
        before, after = am.summary(first), am.summary(second)
        self.assertLess(after["unresolved"], before["unresolved"])
        self.assertEqual(after["unresolved"], 0)
        self.assertEqual(after["seed+delta"], 4)
        for a, (b, how) in second.items():
            self.assertEqual(b, self.truth[a], self.name[a])       # every placement correct
            if how == "seed+delta":
                self.assertIn(self.name[a], ("gTwin1", "gTwin2", "gTwin3", "gTwin4"))
        for a, placed in first.items():                          # passes 1-3 unchanged by seeds
            if placed[1] != "unresolved":
                self.assertEqual(second[a], placed)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="derive_")

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

    def test_the_two_pass_recipe(self):
        a = self.write_pair("a", *build_two_segment(False))
        b = self.write_pair("b", *build_two_segment(True))
        noseed = os.path.join(self.dir, "match_noseed.json")
        seeds_txt = os.path.join(self.dir, "seeds.txt")
        final = os.path.join(self.dir, "match.json")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(am.main([a[0], a[1], b[0], b[1], "--out", noseed]), 0)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(ds.main([noseed, "--out", seeds_txt]), 0)
        self.assertIn("2 seeds", out.getvalue())
        self.assertIn("+0x0002C9C0 x3", out.getvalue())
        with open(seeds_txt, encoding="utf-8") as fh:
            header = fh.readline()
        self.assertTrue(header.startswith("# python -m tools_py.derive_seeds"), header)
        self.assertIn("a %s: 9 rows" % a[1], header)
        self.assertIn("b %s: 9 rows" % b[1], header)
        args = []
        for a_addr, b_addr in ds.read_seeds(seeds_txt):
            args += ["--seed", "0x%08X=0x%08X" % (a_addr, b_addr)]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(am.main([a[0], a[1], b[0], b[1], "--out", final] + args), 0)
        with open(final, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["summary"]["unresolved"], 0)


if __name__ == "__main__":
    unittest.main()
