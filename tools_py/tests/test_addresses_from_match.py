"""Sprint 11 Task 19: the kR0004 column of socom2_addresses.h, printed from match.json.

The column is filled from evidence or not at all. A field the matcher placed on evidence it is willing
to name (identity, exact, hash+callees) gets the r0004 address; everything else gets 0 -- UNAVAILABLE --
because an r0001 address sitting in the r0004 column is not a bad address, it is a crash somewhere else
entirely, hours later.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from tools_py import addresses_from_match as afm

HEADER = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xRuntime", "include", "runtime",
                      "socom2_addresses.h")


def match_file(entries, path):
    """A minimal match.json in address_matcher.py's own shape."""
    doc = {"a": {"csv": "a.csv", "elf": "a.elf"}, "b": {"csv": "b.csv", "elf": "b.elf"},
           "matches": {}}
    for a_addr, b_addr, how in entries:
        doc["matches"]["0x%08x" % a_addr] = {
            "b": None if b_addr is None else "0x%08x" % b_addr,
            "how": how,
            "name": "FUN_%08x" % a_addr,
        }
    with open(path, "w") as fh:
        json.dump(doc, fh)
    return path


class ColumnFromMatches(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def rows(self, entries, **kw):
        path = match_file(entries, os.path.join(self.tmp, "m.json"))
        with open(path) as fh:
            doc = json.load(fh)
        return {r.name: r for r in afm.column(doc["matches"], **kw)}

    def test_every_table_field_appears_once_in_order(self):
        names = [f.name for f in afm.FIELDS]
        self.assertEqual(len(names), len(set(names)), "a field is listed twice")
        rows = self.rows([])
        self.assertEqual([f.name for f in afm.FIELDS], [r.name for r in
                         afm.column({})], "column() keeps the Table's order")
        self.assertEqual(set(rows), set(names))

    def test_the_field_list_is_the_headers_struct_field_for_field(self):
        # The helper prints a C++ aggregate initialiser: one value per member, in order. If the Table
        # grows a member and this list does not, the printed column silently initialises the wrong ones.
        with open(HEADER, encoding="utf-8") as fh:
            text = fh.read()
        body = text.split("struct Table", 1)[1].split("};", 1)[0]
        members = re.findall(r"^\s*uint32_t\s+(\w+)\s*;", body, re.M)
        self.assertEqual(members, [f.name for f in afm.FIELDS])

    def test_an_exact_match_fills_the_field(self):
        cull = afm.by_name("cull").a
        rows = self.rows([(cull, 0x00291FC0, "exact")])
        self.assertEqual(rows["cull"].b, 0x00291FC0)
        self.assertEqual(rows["cull"].method, "exact")

    def test_a_hash_plus_callees_match_fills_the_field(self):
        lod = afm.by_name("lod").a
        rows = self.rows([(lod, 0x003D9CE0, "hash+callees")])
        self.assertEqual(rows["lod"].b, 0x003D9CE0)
        self.assertEqual(rows["lod"].method, "hash+callees")

    def test_an_address_that_did_not_move_is_reported_as_identity(self):
        cull = afm.by_name("cull").a
        rows = self.rows([(cull, cull, "exact")])
        self.assertEqual(rows["cull"].b, cull)
        self.assertEqual(rows["cull"].method, "identity")

    def test_an_unresolved_field_is_unavailable_and_never_the_r0001_address(self):
        cull = afm.by_name("cull").a
        rows = self.rows([(cull, None, "unresolved")])
        self.assertIsNone(rows["cull"].b)
        self.assertEqual(rows["cull"].method, "unresolved")
        self.assertNotEqual(rows["cull"].b, cull)

    def test_a_seed_delta_match_is_not_evidence_enough_by_default(self):
        # The delta only says where to look. It is not one of the three the brief accepts, so the
        # field stays UNAVAILABLE unless the caller opts in and says so in the report.
        thunk = afm.by_name("oskOpenThunk").a
        rows = self.rows([(thunk, 0x00281BE0, "seed+delta")])
        self.assertIsNone(rows["oskOpenThunk"].b)
        self.assertEqual(rows["oskOpenThunk"].method, "rejected:seed+delta")
        opted = self.rows([(thunk, 0x00281BE0, "seed+delta")], accept=afm.ACCEPT + ("seed+delta",))
        self.assertEqual(opted["oskOpenThunk"].b, 0x00281BE0)
        self.assertEqual(opted["oskOpenThunk"].method, "seed+delta")

    def test_a_field_the_match_file_never_mentions_is_unavailable(self):
        rows = self.rows([])
        self.assertIsNone(rows["cull"].b)
        self.assertEqual(rows["cull"].method, "absent")

    def test_a_data_field_is_unavailable_because_the_matcher_places_functions(self):
        rows = self.rows([])
        self.assertIsNone(rows["cameraHolder"].b)
        self.assertEqual(rows["cameraHolder"].method, "data")
        self.assertTrue(afm.by_name("cameraHolder").data)

    def test_overrides_fill_a_field_the_matcher_could_not_and_name_their_method(self):
        # Addresses established by other evidence (a string anchor, the capsule's own table) are passed
        # in rather than typed into the header by hand with no record of where they came from.
        rows = self.rows([], overrides={"dnasCheck": (0x002CF330, "capsule second table")})
        self.assertEqual(rows["dnasCheck"].b, 0x002CF330)
        self.assertEqual(rows["dnasCheck"].method, "capsule second table")

    def test_an_override_below_the_overlay_base_is_refused(self):
        # The loader is the same binary in every pressing and its addresses stay literal at their call
        # sites; one in this column would be a mistake the C++ suite also fails on.
        with self.assertRaises(ValueError):
            self.rows([], overrides={"dnasCheck": (0x001C5B30, "the loader")})


class RenderedColumn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_the_printed_column_is_a_cpp_initialiser_with_one_value_per_field(self):
        cull = afm.by_name("cull").a
        rows = afm.column({"0x%08x" % cull: {"b": "0x00291fc0", "how": "exact", "name": "x"}})
        text = afm.render(rows, "r0004")
        self.assertIn('inline constexpr Table kR0004 = {', text)
        self.assertIn('"r0004",', text)
        self.assertIn("0x00291fc0u,", text)
        values = re.findall(r"^\s+(0x[0-9a-f]+u|0u),", text, re.M)
        self.assertEqual(len(values), len(afm.FIELDS))
        self.assertIn("UNAVAILABLE", text)

    def test_the_printed_column_never_carries_an_r0001_address(self):
        rows = afm.column({})
        text = afm.render(rows, "r0004")
        for f in afm.FIELDS:
            self.assertNotIn("0x%08xu," % f.a, text, "%s: the r0001 address is in the column" % f.name)

    def test_the_cli_prints_the_column_and_a_count(self):
        cull = afm.by_name("cull").a
        path = match_file([(cull, 0x00291FC0, "exact")], os.path.join(self.tmp, "m.json"))
        out = subprocess.run([sys.executable, "-m", "tools_py.addresses_from_match", path,
                              "--revision", "r0004"],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("0x00291fc0u,", out.stdout)
        self.assertIn("kR0004", out.stdout)
        self.assertIn("resolved", out.stderr + out.stdout)


if __name__ == "__main__":
    unittest.main()
