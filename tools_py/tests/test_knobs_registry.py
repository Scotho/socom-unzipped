"""Sprint 9 Goal 3: the knob registry (ps2xShared/include/ps2x/knobs.h) against the source.

The spec's bar: a knob read in code and absent from the table fails the suite. It fails the other way round
too (a row nothing reads), and docs/KNOBS.md is the table rendered -- stale is a failure. No build needed, so
this runs in CI."""
import os
import re
import tempfile
import unittest

from tools_py import knobs


class RegistryShapeTest(unittest.TestCase):
    def test_the_header_parses_and_is_sorted_and_unique(self):
        rows = knobs.table()
        names = [r["name"] for r in rows]
        self.assertGreaterEqual(len(names), 130)
        self.assertEqual(names, sorted(names), "rows are in strcmp order: ps2x::knobs::find is a binary search")
        self.assertEqual(len(names), len(set(names)))
        for r in rows:
            self.assertIn(r["cls"], ("Shipping", "Dev", "Test", "Switch"), r)
            self.assertIn(r["kind"], ("Flag", "Presence", "Int", "Float", "Text", "Path", "Spec"), r)
            self.assertTrue(0 < len(r["meaning"]) <= 110, r)

    def test_the_parser_counts_every_row_the_macro_holds(self):
        with open(knobs.HEADER, "r", encoding="utf-8") as fh:
            text = fh.read()
        # Rows start at column 0 (the header's own comment quotes the row shape after "//").
        self.assertEqual(len(knobs.table()), len(re.findall(r'^    X\("PS2X_', text, re.M)),
                         "a row the regex cannot read would vanish from docs/KNOBS.md and from every check here")

    def test_eighteen_shipping_settings_and_one_switch(self):
        # The plan counted 17 at 8e5d778; Sprint 10 Goal 8 (R174) added PS2X_INPUT_MAPPING to environmentFor, and
        # Goal 9 the two login knobs (merged after the registry was written: the first generated rebuild found them).
        # Sprint 10 Q3 (R210) deleted PS2X_SOCOM2_MOUSE and PS2X_SOCOM2_MOUSE_SENS with their code: the mouse left.
        # 2026-09-22: R238 briefly made it 21 (PS2X_MC_TRACE and PS2X_AUDIO_DUMP reclassed, PS2X_SND_MUTE_BANK
        # added) and the C++ Knobs suite refused it -- "the Shipping class is exactly what the launcher can
        # send", and none of the three has a config.json key. It was also unnecessary: PS2X_DEV=1 reaches a Dev
        # knob in any build. Back to 18; what R238 actually changed is that a FAILED card command now logs
        # unconditionally, which needs no knob at all.
        rows = knobs.table()
        self.assertEqual(sum(1 for r in rows if r["cls"] == "Shipping"), 18)
        self.assertFalse([r["name"] for r in rows if "MOUSE" in r["name"]], "no mouse knob survives Q3")
        self.assertEqual([r["name"] for r in rows if r["cls"] == "Switch"], ["PS2X_DEV"])


class SourceAgainstRegistryTest(unittest.TestCase):
    def test_no_problem_in_the_tree(self):
        self.assertEqual(knobs.problems(), [])

    def test_a_literal_with_no_row_is_a_problem(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "third_party", "ps2recomp", "ps2xRuntime", "src")
            os.makedirs(src)
            with open(os.path.join(src, "x.cpp"), "w") as fh:
                fh.write('static const bool s = ps2x::knob("PS2X_BRAND_NEW") != nullptr;\n')
            found = knobs.literals(root)
            self.assertIn("PS2X_BRAND_NEW", found)
            self.assertTrue(found["PS2X_BRAND_NEW"][0].endswith("x.cpp:1"))

    def test_a_raw_getenv_is_found_and_the_switch_file_is_exempt(self):
        with tempfile.TemporaryDirectory() as root:
            rt = os.path.join(root, "third_party", "ps2recomp", "ps2xRuntime", "src")
            sh = os.path.join(root, "third_party", "ps2recomp", "ps2xShared", "src")
            os.makedirs(rt)
            os.makedirs(sh)
            with open(os.path.join(rt, "y.cpp"), "w") as fh:
                fh.write('const char *e = std::getenv( "PS2X_GS_SCALE");\n')
            with open(os.path.join(sh, "knobs.cpp"), "w") as fh:
                fh.write('v = flagValue(std::getenv("PS2X_DEV"), false);\n')
            sites = knobs.raw_getenv_sites(root)
            self.assertEqual(len(sites), 1)
            self.assertTrue(sites[0].endswith("y.cpp:1"))

    def test_a_helper_reading_a_handed_name_is_found_and_the_accessor_and_bare_run_are_exempt(self):
        with tempfile.TemporaryDirectory() as root:
            rt = os.path.join(root, "third_party", "ps2recomp", "ps2xRuntime", "src")
            sh = os.path.join(root, "third_party", "ps2recomp", "ps2xShared", "src")
            os.makedirs(rt)
            os.makedirs(sh)
            with open(os.path.join(rt, "h.cpp"), "w") as fh:
                fh.write("bool envOn(const char *name)\n{\n    const char *e = std::getenv(name);\n")
            with open(os.path.join(sh, "bare_run.cpp"), "w") as fh:
                fh.write("if (std::getenv(key.c_str()) != nullptr)\n")
            with open(os.path.join(sh, "knobs.cpp"), "w") as fh:
                fh.write("const char *v = std::getenv(name);\n")
            sites = knobs.helper_getenv_sites(root)
            self.assertEqual(len(sites), 1, sites)
            self.assertTrue(sites[0].endswith("h.cpp:3"))

    def test_a_read_before_main_is_found(self):
        with tempfile.TemporaryDirectory() as root:
            rt = os.path.join(root, "third_party", "ps2recomp", "ps2xRuntime", "src")
            os.makedirs(rt)
            with open(os.path.join(rt, "z.cpp"), "w") as fh:
                fh.write('static const bool g_traceFifo = (ps2x::knob("PS2X_TRACE_FIFO") != nullptr);\n'
                         'namespace {\n        bool g_verbose = ps2x::knob("PS2X_SOCOM2_NET_TRACE") != nullptr;\n}\n'
                         'void f() {\n    static const bool s_on = ps2x::knob("PS2X_CD_TRACE") != nullptr;\n}\n')
            early = knobs.early_reads(root)
            self.assertEqual(len(early), 2, early)

    def test_the_pending_list_only_holds_files_that_still_need_it(self):
        raw_files = {site.rsplit(":", 1)[0] for site in knobs.raw_getenv_sites()}
        self.assertEqual(sorted(knobs.RAW_GETENV_PENDING - raw_files), [],
                         "a migrated file is still on RAW_GETENV_PENDING: take it off in the batch that migrates it")


class GeneratedDocTest(unittest.TestCase):
    def test_docs_knobs_md_is_the_registry_rendered(self):
        with open(knobs.DOC, "r", encoding="utf-8") as fh:
            on_disk = fh.read()
        self.assertEqual(on_disk, knobs.render(), "docs/KNOBS.md is stale: python -m tools_py.knobs write")

    def test_a_pipe_in_a_meaning_cannot_break_the_table(self):
        rows = [{"name": "PS2X_X", "cls": "Dev", "kind": "Text", "default": "", "meaning": "linear | integer"}]
        self.assertIn("linear \\| integer", knobs.render(rows))


if __name__ == "__main__":
    unittest.main()
