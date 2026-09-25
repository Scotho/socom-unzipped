"""Sprint 12 Task 8 -- the `toml-stub` pass (tools_py/toml_stub_lever.py; research/57 §2-§4, S12-R4, S12-R13,
S12-R17, S12-R21).

Synthetic toml / csv / sidecar / holds fixtures only; no disc and no tracked file is read here (the agreement over
the tracked toml and sidecar is tools_py/tests/test_toml_names_agree.py).
"""
import csv
import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from tools_py import apply_names
from tools_py import name_provenance as npv
from tools_py import toml_stub_lever as tsl

TOML = """\
[general]
input = "../game/x.elf"

# Functions to stub
stubs = [
  "sceCdDelayThread@0x0018DBB8",
  "kCopy@0x00190000",
  "setD4_CHCR@0x001A3448",
]

untracked_stubs = [
  "_start@0x00180008",
  "kCopy@0x00190100",
  "__dt__Q23std9exceptionFv@0x00184BC0",
  "sceCdDiskReady@0x0018ED78",
  "sceCdDiskReady2@0x0018EF70",
  "notARow@0x001C08E8",
]
skip = []

[performance]
critical = [
  "_start", # no address: not a selector
  "memcpy@0x00191000",
]
"""


def csv_rows(pairs):
    return [{"Name": n, "Start": "0x%08X" % s, "End": "0x%08X" % (s + 16), "Size": "16"} for n, s in pairs]


def sidecar(rows):
    out = {}
    for a, name, mangled in rows:
        out[a] = {"Address": a, "Name": name, "Mangled": mangled, "Pass": "exact", "Score": "1.00",
                  "Evidence": "e", "Source": "s", "Date": "2026-09-24"}
    return out


CSV = csv_rows([("entry", 0x180008), ("FUN_00184bc0", 0x184bc0), ("FUN_0018dbb8", 0x18dbb8),
                ("FUN_0018ed78", 0x18ed78), ("FUN_0018ef70", 0x18ef70), ("FUN_00190000", 0x190000),
                ("FUN_00190100", 0x190100), ("FUN_00191000", 0x191000), ("FUN_001a3448", 0x1a3448)])
SIDE = sidecar([(0x18dbb8, "sceCdDelayThread", "sceCdDelayThread"),
                (0x184bc0, "std_locale_facet_dtor", "__dt__Q33std6locale5facetFv")])
HOLDS = {(0x18ed78, "sceCdDiskReady"), (0x1a3448, "setD3_CHCR")}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.toml = os.path.join(self.tmp, "t.toml")
        with open(self.toml, "w") as fh:
            fh.write(TOML)
        self.names = tsl.toml_names(self.toml)
        self.res = tsl.proposals(self.names, CSV, SIDE, HOLDS)
        self.by_addr = {r["Address"]: r for r in self.res.rows}

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TomlNames(Base):
    def test_every_selector_with_its_key_and_line(self):
        got = {(a, n): (k, line) for a, n, k, line in self.names}
        self.assertEqual(got[(0x18dbb8, "sceCdDelayThread")], ("general.stubs", 6))
        self.assertEqual(got[(0x180008, "_start")], ("general.untracked_stubs", 12))
        self.assertEqual(got[(0x1c08e8, "notARow")], ("general.untracked_stubs", 17))
        self.assertEqual(got[(0x191000, "memcpy")], ("performance.critical", 24))
        self.assertEqual(len(self.names), 10)          # "_start" in critical has no @addr: not a selector

    def test_a_selector_the_scanner_misses_is_an_error(self):
        # The line scanner is cross-checked against tomllib: a one-line array still parses the same.
        path = os.path.join(self.tmp, "one.toml")
        with open(path, "w") as fh:
            fh.write('[general]\nstubs = ["a@0x10", "b@0x20"]\nuntracked_stubs = []\n')
        self.assertEqual(tsl.toml_names(path), [(0x10, "a", "general.stubs", 2), (0x20, "b", "general.stubs", 2)])


class Proposals(Base):
    def test_a_stub_on_a_placeholder_row_proposes(self):
        r = self.by_addr["0x0018ef70"]
        self.assertEqual(r["How"], "toml-stub")
        self.assertEqual(r["Score"], "0.90")
        self.assertEqual(r["Mangled"], "sceCdDiskReady2")
        self.assertEqual(r["Proposed"], "sceCdDiskReady2")
        self.assertEqual(r["Current"], "FUN_0018ef70")
        self.assertEqual(r["Evidence"],
                         "recomp/socom2.toml line 16 (general.untracked_stubs): the project's own stub selector")
        self.assertEqual(r["Source"], "research/57")
        self.assertIn("0x00191000", self.by_addr)      # a performance.critical selector counts too

    def test_proposed_is_a_c_identifier(self):
        res = tsl.proposals([(0x190000, "a<b>::c", "general.stubs", 3)], CSV, {}, set())
        self.assertEqual(res.rows[0]["Proposed"], "a_b___c")
        self.assertEqual(res.rows[0]["Mangled"], "a<b>::c")

    def test_a_non_csv_address_is_refused(self):
        self.assertNotIn("0x001c08e8", self.by_addr)
        self.assertEqual(self.res.census["not a csv row"], 1)
        self.assertIn((0x1c08e8, "notARow"), [(a, n) for a, n, _k, _l in self.res.refused["not a csv row"]])

    def test_a_duplicated_name_is_proposed_at_every_address_with_its_count(self):
        # R10 (unsuffixed only when the demo holds the name that many times) is the applier's render, not ours.
        self.assertEqual(self.by_addr["0x00190000"]["Mangled"], "kCopy")
        self.assertEqual(self.by_addr["0x00190000"]["Duplicated"], "2")
        self.assertEqual(self.by_addr["0x00190100"]["Duplicated"], "2")
        self.assertEqual(self.by_addr["0x0018ef70"]["Duplicated"], "1")
        self.assertNotIn("duplicated", self.res.census)
        self.assertEqual(self.res.duplicated, {"kCopy": [0x190000, 0x190100]})
        self.assertEqual(tsl.duplicated_rows(self.res), 2)

    def test_an_already_named_agreeing_address_is_counted(self):
        self.assertNotIn("0x0018dbb8", self.by_addr)
        self.assertEqual(self.res.census["already named, agrees"], 1)

    def test_a_differing_address_is_reported(self):
        self.assertNotIn("0x00184bc0", self.by_addr)
        self.assertEqual(self.res.census["already named, differs"], 1)
        self.assertEqual(self.res.differs, [(0x184bc0, "__dt__Q23std9exceptionFv", "general.untracked_stubs", 14,
                                             "__dt__Q33std6locale5facetFv")])

    def test_a_held_pair_is_refused_and_another_name_there_is_not(self):
        self.assertNotIn("0x0018ed78", self.by_addr)
        self.assertEqual(self.res.census["held"], 1)
        # (0x1a3448, setD3_CHCR) is held; the toml's setD4_CHCR there is judged like any other (S12-R21).
        self.assertEqual(self.by_addr["0x001a3448"]["Mangled"], "setD4_CHCR")

    def test_entry_is_a_placeholder_row(self):
        self.assertEqual(self.by_addr["0x00180008"]["Mangled"], "_start")

    def test_a_named_csv_row_without_a_sidecar_row_is_refused(self):
        rows = csv_rows([("sceCdRead", 0x190000)])
        res = tsl.proposals([(0x190000, "sceCdRead2", "general.stubs", 3)], rows, {}, set())
        self.assertEqual(res.rows, [])
        self.assertEqual(res.census["csv names it"], 1)

    def test_the_census_adds_up(self):
        self.assertEqual(sum(self.res.census[k] for k in tsl.CENSUS), len(self.names))
        self.assertEqual(self.res.census["proposed"], len(self.res.rows))


class File(Base):
    def test_the_header_carries_the_rule_and_the_applier_reads_the_file(self):
        out = os.path.join(self.tmp, "demo_symbol_renames_toml.csv")
        tsl.write_proposals(out, self.res.rows, tsl.header_lines(out, self.res))
        with open(out) as fh:
            text = fh.read()
        header = "".join(l for l in text.splitlines(True) if l.startswith("#"))
        for line in tsl.TOML_STUB_RULE.splitlines():
            self.assertIn(line, header)
        props = apply_names.read_proposals(out)
        self.assertEqual(len(props), len(self.res.rows))
        p = [x for x in props if x.address == 0x18ef70][0]
        self.assertEqual((p.pass_name, p.score, p.loose, p.mangled), ("toml-stub", 0.90, False, "sceCdDiskReady2"))
        self.assertIn("research/57", p.source)

    def test_cli(self):
        ghidra = os.path.join(self.tmp, "g.csv")
        with open(ghidra, "w", newline="") as fh:
            w = csv.DictWriter(fh, ["Name", "Start", "End", "Size"])
            w.writeheader()
            w.writerows(CSV)
        names = os.path.join(self.tmp, "n.csv")
        npv.write(names, SIDE.values())
        holds = os.path.join(self.tmp, "h.csv")
        with open(holds, "w") as fh:
            fh.write("Address,Proposed,Reason,Source\n0x0018ed78,sceCdDiskReady,r,s\n")
        out = os.path.join(self.tmp, "out.csv")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tsl.main([self.toml, ghidra, names, "--out", out, "--holds", holds])
        self.assertEqual(rc, 0)
        # 0x180008, 0x18ef70, 0x190000, 0x190100, 0x191000, 0x1a3448
        self.assertEqual(len(apply_names.read_proposals(out)), 6)
        self.assertIn("0x00190100 kCopy Duplicated=2", buf.getvalue())
        with open(out) as fh:
            self.assertIn("Proposed with a duplicated name (Duplicated > 1): 2", fh.read())


if __name__ == "__main__":
    unittest.main()
