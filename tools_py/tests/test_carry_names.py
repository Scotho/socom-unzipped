"""Sprint 11 Task 19 -- carrying r0001's function names onto r0004's addresses (tools_py/carry_names.py).

Everything here is synthetic: a three-row match report and a three-row CSV. The point of the tool is one
rule -- a name that embeds an address does not travel -- and the cases are that rule and the two ways it
can be got wrong (a carried name overwriting a live one; Start/End/Size drifting).
"""
import csv
import json
import os
import shutil
import tempfile
import unittest

from tools_py import carry_names as cn


def report(pairs):
    """{a_addr: (name, b_addr or None)} -> the matcher's --out shape."""
    return {"matches": {"0x%08x" % a: {"name": n,
                                       "b": None if b is None else "0x%08x" % b,
                                       "how": "exact" if b else "unresolved"}
                        for a, (n, b) in pairs.items()}}


def rows(triples):
    return [{"Name": n, "Start": "0x%08X" % s, "End": "0x%08X" % e, "Size": str(e - s)}
            for n, s, e in triples]


class IsAddressy(unittest.TestCase):
    def test_ghidra_defaults_are_addressy(self):
        for name in ("FUN_00408c58", "LAB_001e7040", "caseD_004c5380", "thunk_FUN_00180008",
                     "SUB_00421998"):
            self.assertTrue(cn.is_addressy(name), name)

    def test_real_names_are_not(self):
        for name in ("entry", "SetGsCrt", "_Exit", "CreateThread", "AddDmacHandler", "RFU116"):
            self.assertFalse(cn.is_addressy(name), name)


class Carry(unittest.TestCase):
    def test_named_function_travels_to_its_matched_address(self):
        r = rows([("FUN_001a3720", 0x1A3720, 0x1A3740), ("FUN_00500000", 0x500000, 0x500020)])
        counts = cn.carry(report({0x1A3720: ("SetGsCrt", 0x1A3720)})["matches"], r)
        self.assertEqual(r[0]["Name"], "SetGsCrt")
        self.assertEqual(counts["carried"], 1)
        self.assertEqual(counts["kept"], 1)

    def test_addressy_name_does_not_travel(self):
        """FUN_00408c58 on 0x435618 would name the function after where it was, and can collide."""
        r = rows([("FUN_00435618", 0x435618, 0x435640)])
        counts = cn.carry(report({0x408C58: ("FUN_00408c58", 0x435618)})["matches"], r)
        self.assertEqual(r[0]["Name"], "FUN_00435618")
        self.assertEqual(counts["carried"], 0)
        self.assertEqual(counts["kept"], 1)

    def test_unresolved_row_keeps_its_own_name(self):
        r = rows([("FUN_00500000", 0x500000, 0x500020)])
        cn.carry(report({0x1A3720: ("SetGsCrt", None)})["matches"], r)
        self.assertEqual(r[0]["Name"], "FUN_00500000")

    def test_collision_is_refused_not_duplicated(self):
        """Two generated functions must never claim one symbol."""
        r = rows([("SetGsCrt", 0x1A3720, 0x1A3740), ("FUN_00500000", 0x500000, 0x500020)])
        counts = cn.carry(report({0x400000: ("SetGsCrt", 0x500000)})["matches"], r)
        self.assertEqual([x["Name"] for x in r], ["SetGsCrt", "FUN_00500000"])
        self.assertEqual(counts["refused"], 1)

    def test_addresses_and_sizes_are_never_touched(self):
        r = rows([("FUN_001a3720", 0x1A3720, 0x1A3740)])
        before = (r[0]["Start"], r[0]["End"], r[0]["Size"])
        cn.carry(report({0x1A3720: ("SetGsCrt", 0x1A3720)})["matches"], r)
        self.assertEqual((r[0]["Start"], r[0]["End"], r[0]["Size"]), before)


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_writes_the_export_format(self):
        mj = os.path.join(self.dir, "m.json")
        raw = os.path.join(self.dir, "raw.csv")
        out = os.path.join(self.dir, "out.csv")
        with open(mj, "w", encoding="utf-8") as fh:
            json.dump(report({0x1A3720: ("SetGsCrt", 0x1A3720),
                              0x408C58: ("FUN_00408c58", 0x435618)}), fh)
        cn.write_csv(raw, rows([("FUN_001a3720", 0x1A3720, 0x1A3740),
                                ("FUN_00435618", 0x435618, 0x435640)]))
        self.assertEqual(cn.main([mj, raw, out]), 0)
        with open(out, newline="", encoding="utf-8") as fh:
            got = list(csv.DictReader(fh))
        self.assertEqual([r["Name"] for r in got], ["SetGsCrt", "FUN_00435618"])
        self.assertEqual(got[0]["Start"], "0x001A3720")
        self.assertEqual(got[1]["Size"], "40")
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(fh.readline().strip(), "Name,Start,End,Size")

    def test_empty_table_is_no_data(self):
        mj = os.path.join(self.dir, "m.json")
        raw = os.path.join(self.dir, "raw.csv")
        with open(mj, "w", encoding="utf-8") as fh:
            json.dump(report({}), fh)
        with open(raw, "w", encoding="utf-8") as fh:
            fh.write("Name,Start,End,Size\n")
        self.assertEqual(cn.main([mj, raw, os.path.join(self.dir, "o.csv")]), 2)


if __name__ == "__main__":
    unittest.main()
