"""tools_py/fix_ghidra_csv.py: the function map the recompiler trusts, normalised (Sprint 13 H7, harness audit #33).

It runs on every `./build.sh recomp` and in scripts/build_revision.sh step 0, both with `--out` to a build product
under recomp/build/ (build.sh rewrote recomp/socom2_ghidra.csv in place until Sprint 13 C5; `--out` is now required),
and had no test. These cases drive the script as the build does -- a subprocess over
a small synthetic map in a temporary directory -- and pin its three transformations:

  1. a non-contiguous Ghidra body (End far past Start + Size) is cut to Start + Size when the hole is large
     (> 1024 bytes, or larger than the body itself); a small hole is a cold block and is kept;
  2. each forced entry in extra_functions.txt becomes a row: to the next known start when it lands in a gap, and
     when it lands INSIDE a row, that row is truncated at it and the new row takes the rest -- no overlap;
  3. merge_ranges.txt (beside extra_functions.txt) folds every row starting inside [START, END) into the row at START.

The last two cases were RED on the script as it stood: a forced entry was placed against the map's starts as they
were BEFORE any forced entry was added, in the file's own order, so two entries in one gap listed high-then-low
(recomp/extra_functions.txt is not sorted: 8 descents in 1619 lines; the r0004 list 13 in 2956) gave overlapping
rows, and an address listed twice gave two identical rows.
"""
import csv
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "tools_py", "fix_ghidra_csv.py")
HEADER = ["Name", "Start", "End", "Size"]


def row(name, start, end, size=None):
    return [name, "0x%08X" % start, "0x%08X" % end, str(end - start if size is None else size)]


class FixGhidraCsv(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.map = os.path.join(self.dir, "map.csv")
        self.extra = os.path.join(self.dir, "extra_functions.txt")
        self.fixed = os.path.join(self.dir, "build", "map.fixed.csv")

    def tearDown(self):
        self._tmp.cleanup()

    def write_map(self, rows):
        with open(self.map, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(rows)

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w", newline="\n") as f:
            f.write(text)

    def run_fix(self, *extra_args, extra=None):
        # --out is required (Sprint 13 C5): unless a case names its own, the product goes to self.fixed.
        args = list(extra_args)
        if not any(a == "--out" or a.startswith("--out=") for a in args):
            args += ["--out", self.fixed]
        p = subprocess.run([sys.executable, SCRIPT, self.map, extra or self.extra] + args,
                           capture_output=True, text=True)
        return p

    def read(self, path=None):
        with open(path or self.fixed, newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], HEADER)
        return [(r[0], int(r[1], 16), int(r[2], 16), int(r[3])) for r in rows[1:]]

    def assertNoOverlap(self, rows):
        spans = sorted((s, e) for _, s, e, _ in rows)
        for (s0, e0), (s1, e1) in zip(spans, spans[1:]):
            self.assertLessEqual(e0, s1, "rows [%#x,%#x) and [%#x,%#x) overlap" % (s0, e0, s1, e1))

    # 1. non-contiguous bodies
    def test_a_large_hole_is_cut_to_start_plus_size(self):
        self.write_map([row("thunk", 0x1000, 0x3000, 0x20),       # hole 0x1FE0 > 1024: a merged jump target
                        row("tiny", 0x3000, 0x3100, 0x40)])       # hole 0xC0 > size 0x40: cut too
        p = self.run_fix()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.read(), [("thunk", 0x1000, 0x1020, 0x20), ("tiny", 0x3000, 0x3040, 0x40)])
        self.assertIn("2 ranges fixed", p.stdout)

    def test_a_small_hole_is_a_cold_block_and_is_kept(self):
        self.write_map([row("body", 0x1000, 0x1300, 0x200)])      # hole 0x100: <= 1024 and <= size
        p = self.run_fix()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.read(), [("body", 0x1000, 0x1300, 0x200)])
        self.assertIn("0 ranges fixed", p.stdout)

    # 2. forced entries
    def test_a_forced_entry_in_a_gap_runs_to_the_next_start(self):
        self.write_map([row("a", 0x1000, 0x1100), row("b", 0x2000, 0x2100)])
        self.write("extra_functions.txt", "# forced\n\n0x1800  # a comment after the address\n")
        p = self.run_fix()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.read(), [("a", 0x1000, 0x1100, 0x100), ("FUN_00001800", 0x1800, 0x2000, 0x800),
                                       ("b", 0x2000, 0x2100, 0x100)])
        self.assertIn("1 forced entries added", p.stdout)

    def test_a_forced_entry_past_the_last_function_gets_0x100(self):
        self.write_map([row("a", 0x1000, 0x1100)])
        self.write("extra_functions.txt", "5000\n")               # the 0x prefix is optional
        self.run_fix()
        self.assertEqual(self.read()[-1], ("FUN_00005000", 0x5000, 0x5100, 0x100))

    def test_a_forced_entry_inside_a_row_splits_it(self):
        """Two functions Ghidra merged into one: the parent is truncated at the entry, the entry takes the rest."""
        self.write_map([row("parent", 0x1000, 0x1400), row("next", 0x1400, 0x1500)])
        self.write("extra_functions.txt", "0x1200\n")
        self.run_fix()
        rows = self.read()
        self.assertEqual(rows, [("parent", 0x1000, 0x1200, 0x200), ("FUN_00001200", 0x1200, 0x1400, 0x200),
                                ("next", 0x1400, 0x1500, 0x100)])
        self.assertNoOverlap(rows)

    def test_a_known_start_is_not_added_again(self):
        self.write_map([row("a", 0x1000, 0x1100)])
        self.write("extra_functions.txt", "0x1000\n")
        p = self.run_fix()
        self.assertEqual(self.read(), [("a", 0x1000, 0x1100, 0x100)])
        self.assertIn("0 forced entries added", p.stdout)

    def test_no_extra_file_adds_nothing(self):
        self.write_map([row("a", 0x1000, 0x1100)])
        p = self.run_fix(extra=os.path.join(self.dir, "absent.txt"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.read(), [("a", 0x1000, 0x1100, 0x100)])

    def test_forced_entries_in_one_gap_do_not_overlap_whatever_their_order(self):
        """RED before H7: 0x1800 then 0x1400 gave [0x1800,0x2000) and [0x1400,0x2000)."""
        self.write_map([row("a", 0x1000, 0x1100), row("b", 0x2000, 0x2100)])
        self.write("extra_functions.txt", "0x1800\n0x1400\n")
        self.run_fix()
        rows = self.read()
        self.assertNoOverlap(rows)
        self.assertEqual(rows, [("a", 0x1000, 0x1100, 0x100), ("FUN_00001400", 0x1400, 0x1800, 0x400),
                                ("FUN_00001800", 0x1800, 0x2000, 0x800), ("b", 0x2000, 0x2100, 0x100)])

    def test_an_address_listed_twice_is_one_row(self):
        """RED before H7: the second line was checked against the map's starts only, not the rows just added."""
        self.write_map([row("a", 0x1000, 0x1100), row("b", 0x2000, 0x2100)])
        self.write("extra_functions.txt", "0x1800\n0x1800\n")
        p = self.run_fix()
        self.assertEqual([r for r in self.read() if r[1] == 0x1800], [("FUN_00001800", 0x1800, 0x2000, 0x800)])
        self.assertIn("1 forced entries added", p.stdout)

    # 3. merge_ranges.txt
    def test_merge_ranges_fold_the_inner_rows_into_the_first(self):
        self.write_map([row("loop_head", 0x1000, 0x1010), row("inner", 0x1010, 0x1080),
                        row("tail", 0x1080, 0x1100), row("after", 0x1100, 0x1200)])
        self.write("merge_ranges.txt", "# lo hi\n0x1000 0x1100\n")
        p = self.run_fix()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.read(), [("loop_head", 0x1000, 0x1100, 0x100), ("after", 0x1100, 0x1200, 0x100)])
        self.assertIn("2 rows merged", p.stdout)

    # the output
    def test_rows_come_out_sorted_by_start(self):
        self.write_map([row("b", 0x2000, 0x2100), row("a", 0x1000, 0x1100)])
        self.run_fix()
        self.assertEqual([r[0] for r in self.read()], ["a", "b"])

    def test_out_leaves_the_map_untouched(self):
        self.write_map([row("thunk", 0x1000, 0x3000, 0x20)])
        with open(self.map, "rb") as f:
            before = f.read()
        out = os.path.join(self.dir, "build", "fixed.csv")        # the directory is created
        p = self.run_fix("--out", out)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(self.map, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(self.read(out), [("thunk", 0x1000, 0x1020, 0x20)])
        self.assertIn("-> " + out, p.stdout)

    def test_out_equals_form(self):
        self.write_map([row("a", 0x1000, 0x1100)])
        out = os.path.join(self.dir, "fixed.csv")
        p = self.run_fix("--out=" + out)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.path.isfile(out))

    def test_without_out_it_refuses_and_leaves_the_map_alone(self):
        """RED before Sprint 13 C5: no --out rewrote the map in place, which build.sh's r0001 lane did every recomp."""
        self.write_map([row("thunk", 0x1000, 0x3000, 0x20)])
        with open(self.map, "rb") as f:
            before = f.read()
        p = subprocess.run([sys.executable, SCRIPT, self.map, self.extra], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--out is required", p.stderr)
        with open(self.map, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_out_naming_the_map_itself_is_refused(self):
        self.write_map([row("thunk", 0x1000, 0x3000, 0x20)])
        with open(self.map, "rb") as f:
            before = f.read()
        p = self.run_fix("--out", os.path.join(self.dir, ".", "map.csv"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("names the map itself", p.stderr)
        with open(self.map, "rb") as f:
            self.assertEqual(f.read(), before)

    def test_help_prints_the_usage_and_succeeds(self):
        for flag in ("--help", "-h"):
            p = subprocess.run([sys.executable, SCRIPT, flag], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("usage: fix_ghidra_csv.py", p.stdout)

    def test_bad_arguments_print_the_usage(self):
        self.write_map([row("a", 0x1000, 0x1100)])
        for args in (["--out"], ["--bogus"]):
            p = self.run_fix(*args)
            self.assertNotEqual(p.returncode, 0, args)
            self.assertIn("usage: fix_ghidra_csv.py", p.stderr, args)
        p = subprocess.run([sys.executable, SCRIPT, self.map], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("usage: fix_ghidra_csv.py", p.stderr)


if __name__ == "__main__":
    unittest.main()
