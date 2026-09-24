"""Sprint 11 Task 19 -- carrying r0001's function names onto r0004's addresses (tools_py/carry_names.py).

Everything here is synthetic: a three-row match report and a three-row CSV. The point of the tool is one
rule -- a name that embeds an address does not travel -- and the cases are that rule and the two ways it
can be got wrong (a carried name overwriting a live one; Start/End/Size drifting).

Sprint 12 Task 2 (research/48 §4-§5, S12-R7): the rule is now `name_provenance.is_placeholder`, anchored, so
`caseD_6` no longer travels and `C2DBitmapPoly_SetUV_ffffffff` no longer silently drops; a refused placeholder
is counted; `--names/--names-out` carry the names sidecar with the names.
"""
import contextlib
import csv
import io
import json
import os
import shutil
import tempfile
import unittest

from tools_py import carry_names as cn
from tools_py import name_provenance as npv


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


class PlaceholderRule(unittest.TestCase):
    """research/48 §4: the 8-hex run let `caseD_` travel and dropped a readable name without counting it."""

    def test_a_refused_placeholder_is_counted_apart_from_collisions(self):
        r = rows([("FUN_00435618", 0x435618, 0x435640), ("FUN_00500000", 0x500000, 0x500020)])
        counts = cn.carry(report({0x408C58: ("FUN_00408c58", 0x435618),
                                  0x180008: ("entry", 0x500000)})["matches"], r)
        self.assertEqual(counts["refused_placeholder"], 2)
        self.assertEqual(counts["refused"], 0)
        self.assertEqual([x["Name"] for x in r], ["FUN_00435618", "FUN_00500000"])

    def test_a_case_label_does_not_travel(self):
        r = rows([("FUN_00268378", 0x268378, 0x268380)])
        counts = cn.carry(report({0x267808: ("caseD_6", 0x268378)})["matches"], r)
        self.assertEqual(r[0]["Name"], "FUN_00268378")
        self.assertEqual((counts["carried"], counts["refused_placeholder"]), (0, 1))

    def test_a_readable_name_with_an_ffffffff_suffix_travels(self):
        r = rows([("FUN_00359140", 0x359140, 0x359200)])
        counts = cn.carry(report({0x359140: ("C2DBitmapPoly_SetUV_ffffffff", 0x359140)})["matches"], r)
        self.assertEqual(r[0]["Name"], "C2DBitmapPoly_SetUV_ffffffff")
        self.assertEqual((counts["carried"], counts["refused_placeholder"]), (1, 0))

    def test_the_cli_prints_the_placeholder_count(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        mj, raw, out = (os.path.join(d, x) for x in ("m.json", "raw.csv", "out.csv"))
        with open(mj, "w", encoding="utf-8") as fh:
            json.dump(report({0x267808: ("caseD_6", 0x268378)}), fh)
        cn.write_csv(raw, rows([("FUN_00268378", 0x268378, 0x268380)]))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(cn.main([mj, raw, out]), 0)
        self.assertIn("refused 1 (placeholder)", buf.getvalue())
        self.assertIn("refused 0 (name collision)", buf.getvalue())


class SidecarCarry(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_a_carried_name_takes_its_provenance_with_it(self):
        mj, raw, out, a_side, b_side = (os.path.join(self.dir, x) for x in
                                        ("m.json", "raw.csv", "out.csv", "a.csv", "b.csv"))
        doc = report({0x359140: ("C2DBitmapPoly_SetUV_ffffffff", 0x35A000),
                      0x408C58: ("FUN_00408c58", 0x435618)})
        doc["matches"]["0x00359140"]["how"] = "hash+callees"
        with open(mj, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        cn.write_csv(raw, rows([("FUN_0035a000", 0x35A000, 0x35A0C0), ("FUN_00435618", 0x435618, 0x435640)]))
        npv.write(a_side, [{"Address": 0x359140, "Name": "C2DBitmapPoly_SetUV_ffffffff",
                            "Mangled": "SetUV__13C2DBitmapPolyFffffffff", "Pass": "exact", "Score": "0.95",
                            "Evidence": "demo .symtab, tier A", "Source": "game/demo_symbol_renames.csv",
                            "Date": "2026-09-25"}])
        self.assertEqual(cn.main([mj, raw, out, "--names", a_side, "--names-out", b_side]), 0)
        got = npv.read(b_side)
        self.assertEqual(list(got), [0x35A000])
        self.assertEqual(got[0x35A000], {
            "Address": 0x35A000, "Name": "C2DBitmapPoly_SetUV_ffffffff",
            "Mangled": "SetUV__13C2DBitmapPolyFffffffff", "Pass": "carried:exact", "Score": "0.95",
            "Evidence": "match.json hash+callees from 0x00359140; demo .symtab, tier A",
            "Source": "game/demo_symbol_renames.csv", "Date": "2026-09-25"})
        with open(out, newline="", encoding="utf-8") as fh:
            self.assertEqual(npv.audit(list(csv.DictReader(fh)), got), [])

    def test_a_carried_name_without_an_a_row_fails(self):
        """A name without a recorded reason is a defect (R261): the carry says so and exits 1."""
        mj, raw, out, a_side, b_side = (os.path.join(self.dir, x) for x in
                                        ("m.json", "raw.csv", "out.csv", "a.csv", "b.csv"))
        with open(mj, "w", encoding="utf-8") as fh:
            json.dump(report({0x1A3720: ("SetGsCrt", 0x1A3720)}), fh)
        cn.write_csv(raw, rows([("FUN_001a3720", 0x1A3720, 0x1A3730)]))
        npv.write(a_side, [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cn.main([mj, raw, out, "--names", a_side, "--names-out", b_side]), 1)

    def test_names_and_names_out_come_together(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cn.main(["m.json", "raw.csv", "out.csv", "--names", "a.csv"])


if __name__ == "__main__":
    unittest.main()
