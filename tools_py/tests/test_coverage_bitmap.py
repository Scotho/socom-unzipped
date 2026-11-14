"""Sprint 19 task B1: the coverage bitmap's reader against a synthetic dump.

The runtime (PS2X_COVERAGE=<path>, runtime/coverage_bitmap.h) writes one bit per dense function-table slot that a
dispatched call reached. The reader maps the slots back to functions through the Ghidra function list and the name
table, and must say, every time it prints, that a direct tail jump (`j`) to a known function is emitted as a C++
call and never passes the table: a function reached only that way reads as not hit. No game and no build needed."""
import csv
import io
import os
import struct
import tempfile
import unittest
from contextlib import redirect_stdout

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
        self.assertEqual(by_addr[0x100010]["hit"], 1)
        self.assertEqual(by_addr[0x100010]["size"], 72)
        self.assertEqual(by_addr[0x100010]["resume_hits"], 1)   # 0x100020 is inside it, not an entry
        self.assertEqual(by_addr[0x100058]["hit"], 0)
        self.assertEqual(by_addr[0x100000]["name"], "FUN_00100000")   # no name row: the Ghidra name stays

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
        self.assertIn("hit 3 of 4 functions", text)
        with open(out_csv, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["address"] for r in rows], ["0x00100000", "0x00100010", "0x00100060"])
        self.assertEqual(rows[1]["name"], "CZWeaponList_GetWeapon")
        self.assertEqual(rows[1]["hit"], "1")

    def test_the_caveat_names_the_blind_spot(self):
        self.assertIn("tail", coverage_bitmap.TAIL_CALL_CAVEAT)
        self.assertIn("not hit", coverage_bitmap.TAIL_CALL_CAVEAT)


if __name__ == "__main__":
    unittest.main()
