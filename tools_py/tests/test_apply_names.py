"""Sprint 12 Task 3 -- the applier (tools_py/apply_names.py; S12-R13, S12-R18, S12-R9, S12-R20).

Synthetic csv, sidecar, holds and proposals fixtures for every outcome the applier can reach (applied, noop,
held, deferred, refused, contradiction), the column variants of the proposals files, the audit gate (nothing
written, exit 2) and `--report-only`. One suite test reads the tracked csv + sidecar pair and checks every
applied row carries its provenance, as test_name_provenance's tracked-file test does for the audit.
"""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

from tools_py import apply_names as an
from tools_py import name_provenance as npv
from tools_py.readable_names import is_legal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CSV = ("Name,Start,End,Size\n"
       "SetGsCrt,0x001A3720,0x001A3730,16\n"
       "FUN_00200000,0x00200000,0x00200100,256\n"
       "FUN_00200100,0x00200100,0x00200200,256\n"
       "FUN_00200200,0x00200200,0x00200300,256\n"
       "FUN_00200300,0x00200300,0x00200400,256\n"
       "FUN_00200400,0x00200400,0x00200500,256\n")

GHIDRA_ROW = {"Address": 0x1A3720, "Name": "SetGsCrt", "Mangled": "", "Pass": "ghidra", "Score": "1.00",
              "Evidence": "EE kernel syscall stub", "Source": "test", "Date": "2026-09-04"}

TASK7 = ("Address,Current,Proposed,Mangled,Score,How,Size\n"
         "0x00200000,FUN_00200000,Update__7CPlayerFv,Update__7CPlayerFv,1.00,exact,184\n")

TASK7B = ("# game/demo_symbol_renames_7b.csv -- Sprint 11 Task 7b proposals.\n"
          "# docs/research/45-positional-and-bridge-names.md\n"
          "Address,Current,Proposed,Mangled,Source,Tier,Evidence,KeyPeers,DemoAddr,DemoSize,OurSize,Ratio,GapSize\n"
          "0x00200100,FUN_00200100,deci2Putchar,deci2Putchar,positional,B,image-wide,1/1,0x0015ccb8,176,176,1.00,1\n")

STRINGS_HEAD = ("# game/demo_symbol_renames_strings.csv -- Sprint 12 Task 12 proposals. Score 0.80\n"
                "# docs/research/53-string-correlator.md\n"
                "Address,Current,Proposed,Mangled,Score,How,Size,Evidence,Level,DemoAddr,DemoSize,OurSize,Ratio\n")
STRINGS_LOOSE_HEAD = ("# game/demo_symbol_renames_strings_loose.csv -- LOOSE (research/53 rule R0); no score.\n"
                      "# docs/research/53-string-correlator.md\n"
                      "Address,Current,Proposed,Mangled,Score,How,Size,Evidence,Level,DemoAddr,DemoSize,OurSize,Ratio\n")
CALLGRAPH_HEAD = ("# demo_symbol_renames_callgraph.csv -- Sprint 12 Task 15, round 1 at Score 0.80 (strict).\n"
                  "# docs/research/52-callgraph-propagation.md\n"
                  "Address,Current,Proposed,Mangled,Score,How,Evidence,Round,Key,KeySize,Order,DemoAddr,DemoSize,"
                  "OurSize,Ratio\n")
CALLGRAPH_LOOSE_HEAD = CALLGRAPH_HEAD.replace("callgraph.csv", "callgraph_loose.csv")
OFFSETS_LOOSE_HEAD = ("# THIS IS THE LOOSE FILE. docs/research/54-offset-multiset.md\n"
                      "Address,Current,Proposed,Mangled,Score,How,Evidence,Accesses,Order,DemoAddr,DemoSize,OurSize,"
                      "Ratio\n")


def strings_row(addr, mangled, level="strict", score="0.80", how="string-set"):
    return "0x%08x,FUN_%08x,%s,%s,%s,%s,200,strings=3;order=between;callees=overlap,%s,0x1,200,200,1.00\n" % (
        addr, addr, mangled, mangled, score, how, level)


def callgraph_row(addr, mangled, rnd=1, score="0.80"):
    return ("0x%08x,FUN_%08x,%s,%s,%s,callgraph,callgraph round %d; key=callee; |K|=4; order=between,%d,callee,4,"
            "between,0x1,200,200,1.00\n" % (addr, addr, mangled, mangled, score, rnd, rnd))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.csv = self.put("ghidra.csv", CSV)
        self.names = os.path.join(self.dir, "names.csv")
        npv.write(self.names, [dict(GHIDRA_ROW)])
        self.holds = self.put("holds.csv", "Address,Proposed,Reason,Source\n")

    def put(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def slurp(self, path):
        with open(path, "rb") as fh:
            return fh.read()

    def run_cli(self, *files, extra=()):
        argv = [self.csv, self.names] + list(files) + ["--holds", self.holds, "--date", "2026-09-24"] + list(extra)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = an.main(argv)
        return code, out.getvalue()

    def plan_of(self, *files, sidecar=None, holds=None, demo_counts=None):
        props = []
        for f in files:
            props.extend(an.read_proposals(f))
        return an.plan(npv.read_map(self.csv), npv.read(self.names) if sidecar is None else sidecar,
                       holds or {}, props, demo_counts or {})


class ReadProposals(Fixture):
    def test_task7_row_evidence_is_composed(self):
        (p,) = an.read_proposals(self.put("demo_symbol_renames.csv", TASK7))
        self.assertEqual((p.address, p.mangled, p.pass_name, p.score, p.loose),
                         (0x200000, "Update__7CPlayerFv", "exact", 1.0, False))
        self.assertEqual(p.evidence, "fingerprint exact, 184 B")
        self.assertEqual(p.source, "demo_symbol_renames.csv; research/44")

    def test_7b_row_evidence_is_composed_and_its_pass_is_its_source_column(self):
        (p,) = an.read_proposals(self.put("demo_symbol_renames_7b.csv", TASK7B))
        self.assertEqual(p.pass_name, "positional")
        self.assertEqual(p.score, 0.80)
        self.assertEqual(p.evidence, "B; image-wide; keypeers=1/1; ratio=1.00; gap=1")
        self.assertEqual(p.source, "demo_symbol_renames_7b.csv; research/45")
        self.assertFalse(p.loose)

    def test_7c_row_evidence_is_composed(self):
        text = ("# docs/research/51-vtable-coverage.md, docs/research/60-vtable-slots.md.\n"
                "Address,Current,Proposed,Mangled,Score,How,Size,Class,Slot,FixedPoints,DemoAddr,DemoSize,OurSize,"
                "Ratio\n0x00200200,FUN_00200200,__dt__Q23std9exceptionFv,__dt__Q23std9exceptionFv,0.75,vtable-slot,"
                "76,std::exception,0,start..1:1,0x001427e0,76,76,1.00\n")
        (p,) = an.read_proposals(self.put("demo_symbol_renames_7c.csv", text))
        self.assertEqual(p.evidence, "vtable std::exception slot 0; fixed points start..1:1; ratio=1.00")
        self.assertEqual(p.source, "demo_symbol_renames_7c.csv; research/51, research/60")

    def test_a_loose_row_with_no_score_takes_0_75_and_a_derived_ui_row_its_plain_name(self):
        (p,) = an.read_proposals(self.put("demo_symbol_renames_strings_loose.csv", STRINGS_LOOSE_HEAD
                                          + strings_row(0x200200, "Foo__4CBarFv", "loose", "", "string-set-loose")))
        self.assertEqual((p.score, p.loose, p.family), (0.75, True, "strings"))
        ui = ("# docs/research/55-class-inventory.md\nAddress,Current,Proposed,Mangled,Pass,Score,Evidence,DemoAddr\n"
              "0x00200300,FUN_00200300,UIGetFoo,,ui-binding-derived,0.80,derived from the command string GetFoo,\n")
        (u,) = an.read_proposals(self.put("demo_symbol_renames_ui_derived.csv", ui))
        self.assertEqual((u.mangled, u.pass_name, u.family, u.loose), ("UIGetFoo", "ui-binding-derived", "ui", False))


class Plan(Fixture):
    def test_the_clean_case_writes_the_sidecar_and_leaves_the_csv(self):
        before = self.slurp(self.csv)
        code, out = self.run_cli(self.put("demo_symbol_renames.csv", TASK7))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.slurp(self.csv), before)
        side = npv.read(self.names)
        self.assertEqual(sorted(side), [0x1A3720, 0x200000])
        row = side[0x200000]
        self.assertEqual((row["Name"], row["Mangled"], row["Pass"], row["Score"], row["Evidence"], row["Source"],
                          row["Date"]),
                         ("CPlayer_Update", "Update__7CPlayerFv", "exact", "1.00", "exact: fingerprint exact, 184 B",
                          "demo_symbol_renames.csv; research/44", "2026-09-24"))
        self.assertEqual(side[0x1A3720]["Name"], "SetGsCrt")
        self.assertIn("applied 1", out)

    def test_a_held_address_is_printed_and_never_applied(self):
        self.put("holds.csv", "Address,Proposed,Reason,Source\n0x00200000,Update__7CPlayerFv,wrong pair,S12-R9\n")
        code, out = self.run_cli(self.put("demo_symbol_renames.csv", TASK7))
        self.assertEqual(code, 0)
        self.assertNotIn(0x200000, npv.read(self.names))
        self.assertIn("HELD 0x00200000", out)
        self.assertIn("wrong pair", out)

    def test_another_name_at_a_held_address_is_judged_like_any_other(self):
        # S12-R21: the hold is the (Address, Proposed) pair, not the address
        self.put("holds.csv", "Address,Proposed,Reason,Source\n0x00200000,Draw__7CPlayerFv,wrong pair,S12-R20\n")
        code, out = self.run_cli(self.put("demo_symbol_renames.csv", TASK7))
        self.assertEqual(code, 0, out)
        self.assertEqual(npv.read(self.names)[0x200000]["Name"], "CPlayer_Update")
        self.assertNotIn("HELD 0x00200000", out)

    def test_a_hold_un_applies_a_sidecar_row_and_nothing_else(self):
        # S12-R24: a sidecar row whose (Address, Mangled) is a hold pair is removed, and printed
        side = npv.read(self.names)
        side[0x200000] = dict(GHIDRA_ROW, Address=0x200000, Name="start", Mangled="_start", Pass="toml-stub")
        side[0x200100] = dict(GHIDRA_ROW, Address=0x200100, Name="CPlayer_Draw", Mangled="Draw__7CPlayerFv",
                              Pass="exact")
        npv.write(self.names, side.values())
        self.put("holds.csv", "Address,Proposed,Reason,Source\n0x00200000,_start,D2 keeps entry,S12-R24\n")
        code, out = self.run_cli(self.put("demo_symbol_renames.csv", TASK7.replace("0x00200000,FUN_00200000",
                                                                                   "0x00200200,FUN_00200200")))
        self.assertEqual(code, 0, out)
        got = npv.read(self.names)
        self.assertEqual(sorted(got), [0x1A3720, 0x200100, 0x200200])
        self.assertEqual(got[0x200100], side[0x200100])
        self.assertEqual(got[0x1A3720], side[0x1A3720])
        self.assertIn("UN-APPLIED by hold 0x00200000: start (D2 keeps entry)", out)

    def test_a_project_prefixed_alias_is_one_name_not_a_contradiction(self):
        # S12-R24: equal after lower-casing and stripping `socom2_` -> the unprefixed spelling, both passes
        toml = self.put("demo_symbol_renames_toml.csv",
                        "# docs/research/57-recompiler-naming-pipeline.md\n"
                        "Address,Current,Proposed,Mangled,How,Score,Evidence,Source,Key,Line,Duplicated\n"
                        "0x00200200,FUN_00200200,socom2_RsaGenerateKeyPair,socom2_RsaGenerateKeyPair,toml-stub,0.90,"
                        "recomp/socom2.toml line 25,research/57,general.stubs,25,1\n"
                        "0x00200300,FUN_00200300,socom2_Other,socom2_Other,toml-stub,0.90,line 26,research/57,"
                        "general.stubs,26,1\n")
        loose = self.put("demo_symbol_renames_callgraph_loose.csv", CALLGRAPH_LOOSE_HEAD
                         + callgraph_row(0x200200, "RSAGenerateKeyPair", 3, "0.75")
                         + callgraph_row(0x200300, "Different", 3, "0.75"))
        p = self.plan_of(toml, loose)
        got = {d.address: d.status for d in p.decisions}
        self.assertEqual(got, {0x200200: "applied", 0x200300: "contradiction"})
        (row,) = p.rows
        self.assertEqual((row["Name"], row["Mangled"], row["Pass"], row["Score"]),
                         ("RSAGenerateKeyPair", "RSAGenerateKeyPair", "toml-stub&callgraph", "0.90"))

    def test_a_csv_named_address_is_refused(self):
        text = "Address,Current,Proposed,Mangled,Score,How,Size\n0x001a3720,SetGsCrt,Foo,Foo__4CBarFv,1.00,exact,96\n"
        p = self.plan_of(self.put("demo_symbol_renames.csv", text))
        (d,) = p.decisions
        self.assertEqual((d.status, d.reason), ("refused", "csv already names it"))
        self.assertEqual(p.rows, [])

    def test_a_sidecar_noop_and_a_sidecar_disagreement(self):
        side = npv.read(self.names)
        side[0x200000] = dict(GHIDRA_ROW, Address=0x200000, Name="CPlayer_Update", Mangled="Update__7CPlayerFv",
                              Pass="exact")
        side[0x200100] = dict(GHIDRA_ROW, Address=0x200100, Name="COther_Thing", Mangled="Thing__6COtherFv",
                              Pass="exact")
        f = self.put("demo_symbol_renames.csv", TASK7 + "0x00200100,FUN_00200100,x,Update__7CEnemyFv,1.00,exact,96\n")
        p = self.plan_of(f, sidecar=side)
        got = {d.address: (d.status, d.reason) for d in p.decisions}
        self.assertEqual(got[0x200000], ("noop", ""))
        self.assertEqual(got[0x200100], ("refused", "sidecar disagrees"))
        self.assertEqual(p.rows, [])

    def test_two_files_disagreeing_on_an_address_are_both_refused_and_printed(self):
        a = self.put("demo_symbol_renames.csv", TASK7)
        b = self.put("demo_symbol_renames_strings.csv", STRINGS_HEAD + strings_row(0x200000, "Draw__7CPlayerFv"))
        code, out = self.run_cli(a, b, extra=["--strict"])
        self.assertEqual(code, 1)
        self.assertNotIn(0x200000, npv.read(self.names))
        line = [l for l in out.splitlines() if l.startswith("CONTRADICTION 0x00200000")]
        self.assertEqual(len(line), 1, out)
        self.assertIn("demo_symbol_renames.csv=Update__7CPlayerFv", line[0])
        self.assertIn("demo_symbol_renames_strings.csv=Draw__7CPlayerFv", line[0])

    def test_a_loose_only_row_is_deferred_even_with_a_second_loose_row(self):
        a = self.put("demo_symbol_renames_callgraph_loose.csv", CALLGRAPH_LOOSE_HEAD
                     + callgraph_row(0x200200, "Foo__4CBarFv", 2, "0.75"))
        b = self.put("demo_symbol_renames_offsets_loose.csv", OFFSETS_LOOSE_HEAD
                     + "0x00200200,FUN_00200200,Foo__4CBarFv,Foo__4CBarFv,0.75,offset-multiset,\"k\",8,outside,"
                       "0x1,200,200,1.00\n")
        p = self.plan_of(a, b)
        (d,) = p.decisions
        self.assertEqual((d.status, d.reason), ("deferred", "loose without a second lever"))
        self.assertEqual(p.rows, [])

    def test_a_loose_row_is_promoted_by_a_strict_row_of_another_family(self):
        a = self.put("demo_symbol_renames_strings.csv", STRINGS_HEAD + strings_row(0x200200, "Foo__4CBarFv"))
        b = self.put("demo_symbol_renames_callgraph_loose.csv", CALLGRAPH_LOOSE_HEAD
                     + callgraph_row(0x200200, "Foo__4CBarFv", 2, "0.75"))
        p = self.plan_of(a, b)
        (row,) = p.rows
        self.assertEqual((row["Address"], row["Name"], row["Pass"], row["Score"]),
                         (0x200200, "CBar_Foo", "string-set&callgraph", "0.80"))
        self.assertEqual(row["Evidence"], "string-set: strings=3;order=between;callees=overlap | "
                                          "callgraph: callgraph round 2; key=callee; |K|=4; order=between")
        self.assertEqual(row["Source"], "demo_symbol_renames_strings.csv; research/53 | "
                                        "demo_symbol_renames_callgraph_loose.csv; research/52")

    def test_illegal_and_one_name_two_addresses_are_refused(self):
        text = ("Address,Current,Proposed,Mangled,Score,How,Size\n"
                "0x00200000,FUN_00200000,x,FUN_00100000,1.00,exact,96\n")
        a = self.put("demo_symbol_renames.csv", text)
        b = self.put("demo_symbol_renames_strings.csv", STRINGS_HEAD + strings_row(0x200100, "Tick__4CBarFv"))
        c = self.put("demo_symbol_renames_callgraph.csv", CALLGRAPH_HEAD + callgraph_row(0x200200, "Tick__4CBarFv"))
        p = self.plan_of(a, b, c)
        got = {d.address: (d.status, d.reason) for d in p.decisions}
        self.assertEqual(got[0x200000][0], "refused")
        self.assertIn("R12", got[0x200000][1])
        self.assertEqual(got[0x200100][0], "refused")
        self.assertTrue(got[0x200100][1].startswith("one name, two addresses"), got[0x200100])
        self.assertEqual(got[0x200200], got[0x200100])
        self.assertEqual(p.rows, [])
        # R10: kept, unsuffixed, when the demo holds the name that many times
        p = self.plan_of(b, c, demo_counts={"Tick__4CBarFv": 2})
        self.assertEqual([(r["Address"], r["Name"]) for r in p.rows], [(0x200100, "CBar_Tick"), (0x200200, "CBar_Tick")])

    def test_an_audit_failure_writes_nothing_and_exits_2(self):
        npv.write(self.names, [])                      # SetGsCrt in the csv has no sidecar row
        before = self.slurp(self.names)
        code, out = self.run_cli(self.put("demo_symbol_renames.csv", TASK7))
        self.assertEqual(code, 2, out)
        self.assertEqual(self.slurp(self.names), before)
        self.assertIn("SetGsCrt has no sidecar row", out)

    def test_report_only_writes_nothing(self):
        before = (self.slurp(self.csv), self.slurp(self.names))
        code, out = self.run_cli(self.put("demo_symbol_renames.csv", TASK7), extra=["--report-only"])
        self.assertEqual(code, 0)
        self.assertEqual((self.slurp(self.csv), self.slurp(self.names)), before)
        self.assertIn("applied 1", out)


class TrackedFiles(unittest.TestCase):
    def test_every_applied_row_carries_its_provenance(self):
        rows = npv.read_map(os.path.join(ROOT, "recomp/socom2_ghidra.csv"))
        side = npv.read(os.path.join(ROOT, "recomp/socom2_names.csv"))
        self.assertEqual(npv.audit(rows, side), [])
        for a, r in side.items():
            if r["Pass"] == "ghidra":
                continue
            with self.subTest(address="0x%08x" % a):
                self.assertIsNone(is_legal(r["Name"]))
                for col in ("Mangled", "Pass", "Score", "Evidence", "Source", "Date"):
                    self.assertTrue(r[col], col)


if __name__ == "__main__":
    unittest.main()
