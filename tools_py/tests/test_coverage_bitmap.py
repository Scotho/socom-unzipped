"""Sprint 19 task B1: the coverage bitmap's reader against a synthetic dump.

The runtime (PS2X_COVERAGE=<path>, runtime/coverage_bitmap.h) writes one bit per dense function-table slot that a
dispatched call reached. The reader maps the slots back to functions through the Ghidra function list and the name
table, and must say, every time it prints, that a direct tail jump (`j`) to a known function is emitted as a C++
call and never passes the table: a function reached only that way reads as not reached. A function is reached when
its entry slot or any slot inside it (a scheduler resume pc) is set. No game and no build needed."""
import csv
import io
import os
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from tools_py import coverage_bitmap


def _dump(base, slot_count, hit_slots):
    bits = bytearray((slot_count + 7) // 8)
    for slot in hit_slots:
        bits[slot >> 3] |= 1 << (slot & 7)
    return b"PS2XCOV1" + struct.pack("<II", base, slot_count) + bytes(bits)


class CoverageBitmapTest(unittest.TestCase):
    BASE = 0x00100000

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        self.functions = os.path.join(d, "functions.csv")
        with open(self.functions, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("Name,Start,End,Size\n"
                     "FUN_00100000,0x00100000,0x00100010,16\n"
                     "FUN_00100010,0x00100010,0x00100058,72\n"
                     "FUN_00100058,0x00100058,0x00100060,8\n"
                     "FUN_00100060,0x00100060,0x00100100,160\n")
        self.names = os.path.join(d, "names.csv")
        with open(self.names, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("Address,Name,Mangled,Pass,Score,Evidence,Source,Date\n"
                     "0x00100010,CZWeaponList_GetWeapon,GetWeapon__12CZWeaponListF10EQUIP_ITEM,exact,1.00,x,y,z\n")
        # Hit: FUN_00100000's entry (slot 0), GetWeapon's entry (slot 4) and a resume pc inside it (0x100020, slot 8),
        # FUN_00100060's entry (slot 24). FUN_00100058 (slot 22) is not hit.
        self.dump = os.path.join(d, "cov.bin")
        with open(self.dump, "wb") as fh:
            fh.write(_dump(self.BASE, 0x40, [0, 4, 8, 24]))

    def test_read_dump_round_trips_header_and_bits(self):
        cov = coverage_bitmap.read_dump(self.dump)
        self.assertEqual(cov.base, self.BASE)
        self.assertEqual(cov.slot_count, 0x40)
        self.assertEqual(cov.hit_addresses(), [0x100000, 0x100010, 0x100020, 0x100060])

    def test_a_dump_that_is_not_a_bitmap_is_refused(self):
        bad = os.path.join(self.tmp.name, "bad.bin")
        with open(bad, "wb") as fh:
            fh.write(b"NOTABMP!" + struct.pack("<II", 0, 64) + bytes(8))
        with self.assertRaises(ValueError):
            coverage_bitmap.read_dump(bad)
        short = os.path.join(self.tmp.name, "short.bin")
        with open(short, "wb") as fh:
            fh.write(_dump(0, 64, [])[:-1])
        with self.assertRaises(ValueError):
            coverage_bitmap.read_dump(short)

    def test_slots_map_to_functions_by_entry_and_resume_pcs_to_their_function(self):
        cov = coverage_bitmap.read_dump(self.dump)
        funcs = coverage_bitmap.load_functions(self.functions, self.names)
        rows = coverage_bitmap.function_rows(cov, funcs)
        by_addr = {r["address"]: r for r in rows}
        self.assertEqual(by_addr[0x100010]["name"], "CZWeaponList_GetWeapon")
        self.assertEqual(by_addr[0x100010]["entry_hit"], 1)
        self.assertEqual(by_addr[0x100010]["reached"], 1)
        self.assertEqual(by_addr[0x100010]["size"], 72)
        self.assertEqual(by_addr[0x100010]["resume_hits"], 1)   # 0x100020 is inside it, not an entry
        self.assertEqual(by_addr[0x100058]["entry_hit"], 0)
        self.assertEqual(by_addr[0x100058]["reached"], 0)
        self.assertEqual(by_addr[0x100000]["name"], "FUN_00100000")   # no name row: the Ghidra name stays

    def _resume_only_dump(self):
        # FUN_00100060 entered by a direct tail jump (no entry bit) and later resumed by the scheduler at 0x100068
        # (slot 26): reached, though its entry slot is clear.
        path = os.path.join(self.tmp.name, "resume_only.bin")
        with open(path, "wb") as fh:
            fh.write(_dump(self.BASE, 0x40, [0, 4, 8, 26]))
        return path

    def test_a_function_with_a_resume_hit_but_no_entry_hit_is_reached(self):
        cov = coverage_bitmap.read_dump(self._resume_only_dump())
        funcs = coverage_bitmap.load_functions(self.functions, self.names)
        rows = coverage_bitmap.function_rows(cov, funcs)
        row = {r["address"]: r for r in rows}[0x100060]
        self.assertEqual((row["reached"], row["entry_hit"], row["resume_hits"]), (1, 0, 1))
        hot = coverage_bitmap.hit_by_size(rows)
        self.assertIn(0x100060, [r["address"] for r in hot])

    def test_the_summary_counts_reached_functions_and_of_those_how_many_by_entry(self):
        dump = self._resume_only_dump()
        out_csv = os.path.join(self.tmp.name, "all.csv")
        buf = io.StringIO()
        with redirect_stdout(buf):
            coverage_bitmap.main([dump, "--functions", self.functions, "--names", self.names,
                                  "--csv", out_csv, "--all"])
        self.assertIn("reached 3 of 4 functions (2 by entry", buf.getvalue())
        with open(out_csv, encoding="utf-8") as fh:
            rows = {r["address"]: r for r in csv.DictReader(fh)}
        self.assertEqual((rows["0x00100060"]["reached"], rows["0x00100060"]["entry_hit"],
                          rows["0x00100060"]["resume_hits"]), ("1", "0", "1"))

    def _run_main(self, dump):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = coverage_bitmap.main([dump, "--functions", self.functions, "--names", self.names])
        self.assertEqual(rc, 0)
        return out.getvalue(), err.getvalue()

    def test_a_dump_whose_table_does_not_cover_the_function_list_warns_on_stderr(self):
        # A table of 0x10 slots ends at 0x100040: FUN_00100058 and FUN_00100060 start past it -- the mark of a dump
        # read against another revision's function list (r0004's dump against the default r0001 list).
        narrow = os.path.join(self.tmp.name, "narrow.bin")
        with open(narrow, "wb") as fh:
            fh.write(_dump(self.BASE, 0x10, [0, 4]))
        out, err = self._run_main(narrow)
        self.assertIn("warning", err)
        self.assertIn("2 of 4", err)
        self.assertIn("socom2_ghidra_r0004.csv", err)
        self.assertNotIn("warning", out)

    def test_a_dump_that_covers_the_function_list_does_not_warn(self):
        _, err = self._run_main(self.dump)
        self.assertEqual(err, "")

    def test_help_names_the_r0004_function_list(self):
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit):
            coverage_bitmap.main(["--help"])
        self.assertIn("socom2_ghidra_r0004.csv", buf.getvalue())

    def test_hot_list_is_hit_functions_by_size_ascending(self):
        cov = coverage_bitmap.read_dump(self.dump)
        funcs = coverage_bitmap.load_functions(self.functions, self.names)
        hot = coverage_bitmap.hit_by_size(coverage_bitmap.function_rows(cov, funcs))
        self.assertEqual([r["address"] for r in hot], [0x100000, 0x100010, 0x100060])

    def test_main_writes_csv_and_always_prints_the_tail_call_caveat(self):
        out_csv = os.path.join(self.tmp.name, "hot.csv")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = coverage_bitmap.main([self.dump, "--functions", self.functions, "--names", self.names,
                                       "--csv", out_csv])
        self.assertEqual(rc, 0)
        text = buf.getvalue()
        self.assertIn(coverage_bitmap.TAIL_CALL_CAVEAT, text)
        self.assertIn("reached 3 of 4 functions", text)
        with open(out_csv, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["address"] for r in rows], ["0x00100000", "0x00100010", "0x00100060"])
        self.assertEqual(rows[1]["name"], "CZWeaponList_GetWeapon")
        self.assertEqual(rows[1]["entry_hit"], "1")
        self.assertEqual(rows[1]["reached"], "1")

    def test_the_caveat_names_both_blind_spots(self):
        # Not "an undercount, never an overcount": an overridden or stubbed address has its bit set although its
        # generated body never ran, and a tail-jump-only function reads as not reached.
        caveat = coverage_bitmap.TAIL_CALL_CAVEAT
        self.assertIn("through the function table", caveat)
        self.assertIn("overridden or stubbed", caveat)
        self.assertIn("tail jump", caveat)
        self.assertIn("not reached", caveat)
        self.assertNotIn("never an overcount", caveat)


if __name__ == "__main__":
    unittest.main()
