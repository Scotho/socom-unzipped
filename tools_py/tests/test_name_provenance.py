"""Sprint 12 Task 2 -- the names sidecar (tools_py/name_provenance.py; R261, S12-R7, research/48).

Synthetic csv and sidecar fixtures for the predicate, the reader/writer and the audit's four findings; one
suite test runs the audit over the two tracked csv pairs (recomp/socom2_ghidra*.csv and
recomp/socom2_names*.csv), which are in the tree and need no disc.
"""
import os
import shutil
import tempfile
import unittest

from tools_py import name_provenance as npv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def csv_rows(pairs):
    """[(name, start)] -> the Ghidra map's DictReader rows."""
    return [{"Name": n, "Start": "0x%08X" % s, "End": "0x%08X" % (s + 16), "Size": "16"} for n, s in pairs]


def side(pairs, **extra):
    """[(address, name)] -> a sidecar dict keyed by address."""
    out = {}
    for a, n in pairs:
        row = {"Address": a, "Name": n, "Mangled": "", "Pass": "ghidra", "Score": "1.00",
               "Evidence": "EE kernel syscall stub", "Source": "test", "Date": "2026-09-04"}
        row.update(extra)
        out[a] = row
    return out


class IsPlaceholder(unittest.TestCase):
    def test_ghidra_and_recompiler_placeholders(self):
        for name in ("FUN_00408c58", "LAB_001e7040", "DAT_00400000", "SUB_00421998", "sub_0042199C",
                     "thunk_FUN_00180008", "thunk_EXT_FUN_09481d98", "caseD_6", "caseD_a", "caseD_2b",
                     "switchD_00123456", "entry"):
            self.assertTrue(npv.is_placeholder(name), name)

    def test_readable_names_are_not(self):
        """Anchored: an 8-hex run inside a real word, or an `_ffffffff` argument suffix, is not an address."""
        for name in ("RTArray_Q23zdb6CDecal__ctor", "C2DBitmapPoly_SetUV_ffffffff", "AddDmacHandler",
                     "FUN_1234", "SetGsCrt", "RFU116_SetSyscall", "entry_point", "xFUN_00408c58",
                     "FUN_00408c58_x", "caseD_", "caseD_g", ""):
            self.assertFalse(npv.is_placeholder(name), name)


class ReadWrite(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "names.csv")

    def test_round_trip(self):
        rows = side([(0x1A3840, "AddDmacHandler"), (0x1A3720, "SetGsCrt")])
        rows[0x1A3720]["Mangled"] = "swap__Q23std30vector<b,Q23std12allocator<b>>FRQ23std30vector<b>"
        npv.write(self.path, rows.values())
        got = npv.read(self.path)
        self.assertEqual(sorted(got), [0x1A3720, 0x1A3840])
        self.assertEqual(got[0x1A3720]["Mangled"], rows[0x1A3720]["Mangled"])
        self.assertEqual(got[0x1A3840]["Name"], "AddDmacHandler")
        self.assertEqual(got[0x1A3840]["Address"], 0x1A3840)

    def test_the_file_shape(self):
        """The column line first, no `#` line, `0x%08x`, sorted by address, quoting only where csv needs it."""
        rows = side([(0x1A3840, "AddDmacHandler"), (0x1A3720, "SetGsCrt")])
        rows[0x1A3720]["Evidence"] = "a, b"
        npv.write(self.path, rows.values())
        with open(self.path, encoding="utf-8", newline="") as fh:
            lines = fh.read().split("\n")
        self.assertEqual(lines[0], ",".join(npv.COLUMNS))
        self.assertEqual(lines[1], '0x001a3720,SetGsCrt,,ghidra,1.00,"a, b",test,2026-09-04')
        self.assertEqual(lines[2], "0x001a3840,AddDmacHandler,,ghidra,1.00,EE kernel syscall stub,test,2026-09-04")
        self.assertEqual(lines[3:], [""])

    def test_a_repeated_address_is_an_error(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(",".join(npv.COLUMNS) + "\n0x001a3720,SetGsCrt,,ghidra,1.00,e,s,d\n"
                     "0x001a3720,_Exit,,ghidra,1.00,e,s,d\n")
        with self.assertRaises(ValueError):
            npv.read(self.path)

    def test_a_wrong_column_line_is_an_error(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("# a comment\n" + ",".join(npv.COLUMNS) + "\n")
        with self.assertRaises(ValueError):
            npv.read(self.path)


class Audit(unittest.TestCase):
    CSV = csv_rows([("SetGsCrt", 0x1A3720), ("FUN_001a3730", 0x1A3730), ("caseD_6", 0x1A3740), ("entry", 0x180008)])

    def test_clean(self):
        self.assertEqual(npv.audit(self.CSV, side([(0x1A3720, "SetGsCrt")])), [])

    def test_a_named_row_without_a_sidecar_row(self):
        got = npv.audit(self.CSV, {})
        self.assertEqual(len(got), 1)
        self.assertIn("0x001a3720", got[0])

    def test_an_orphan_sidecar_row(self):
        got = npv.audit(self.CSV, side([(0x1A3720, "SetGsCrt"), (0x500000, "CreateThread")]))
        self.assertEqual(len(got), 1)
        self.assertIn("0x00500000", got[0])

    def test_a_disagreeing_name(self):
        got = npv.audit(self.CSV, side([(0x1A3720, "_Exit")]))
        self.assertEqual(len(got), 1)
        self.assertIn("_Exit", got[0])

    def test_a_sidecar_row_on_a_placeholder_is_a_rename(self):
        """S12-R13: the csv's Name is never rewritten; the sidecar row IS the display name."""
        self.assertEqual(npv.audit(self.CSV, side([(0x1A3720, "SetGsCrt"), (0x1A3730, "C2DBitmapPoly_SetUV")])), [])

    def test_a_rename_to_a_placeholder_is_a_finding(self):
        got = npv.audit(self.CSV, side([(0x1A3720, "SetGsCrt"), (0x1A3730, "FUN_00001234")]))
        self.assertEqual(len(got), 1)
        self.assertIn("0x001a3730", got[0])

    def test_a_rename_to_an_illegal_name_is_a_finding(self):
        got = npv.audit(self.CSV, side([(0x1A3720, "SetGsCrt"), (0x1A3730, "Set UV"), (0x1A3740, "9lives")]))
        self.assertEqual(len(got), 2)

    def test_a_repeated_name_at_two_addresses_is_not_a_finding(self):
        rows = csv_rows([("AddDmacHandler", 0x1A3830), ("AddDmacHandler", 0x1A3840)])
        self.assertEqual(npv.audit(rows, side([(0x1A3830, "AddDmacHandler"), (0x1A3840, "AddDmacHandler")])), [])

    def test_the_cli_exits_1_on_a_finding(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        g, n = os.path.join(d, "g.csv"), os.path.join(d, "n.csv")
        with open(g, "w", encoding="utf-8") as fh:
            fh.write("Name,Start,End,Size\nSetGsCrt,0x001A3720,0x001A3730,16\n")
        npv.write(n, [])
        self.assertEqual(npv.main(["audit", g, n]), 1)
        npv.write(n, side([(0x1A3720, "SetGsCrt")]).values())
        self.assertEqual(npv.main(["audit", g, n]), 0)


class TrackedFiles(unittest.TestCase):
    def test_the_tracked_csv_and_sidecar_agree(self):
        for csv_path, names_path in (("recomp/socom2_ghidra.csv", "recomp/socom2_names.csv"),
                                     ("recomp/socom2_ghidra_r0004.csv", "recomp/socom2_names_r0004.csv")):
            with self.subTest(csv=csv_path):
                rows = npv.read_map(os.path.join(ROOT, csv_path))
                self.assertEqual(npv.audit(rows, npv.read(os.path.join(ROOT, names_path))), [])


if __name__ == "__main__":
    unittest.main()
