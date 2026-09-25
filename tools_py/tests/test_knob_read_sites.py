"""Sprint 13 Task C9: a knob's registry line against the code that reads it.

R2 found `PS2X_SOCOM2_NET_STATS` described as "the periodic [net-stats] line" when the code (socom2_libnetb.cpp,
sceInetInterfaceControl case 0x200) makes it the RX-counter fix behind the online movement defect. The class of
defect: a line written once and never read against its code again. So every Shipping and Switch row cites its read
sites (`/* read: <file>:<function> */` after the row in ps2x/knobs.h), and this suite holds the citation to the
tree both ways -- a cited function that no longer reads the name fails, and so does a read the row does not cite.
A meaning that names a log line must name one the source prints. Textual only: no build needed, so it runs in CI."""
import os
import tempfile
import unittest

from tools_py import knobs


def _tree(root, files):
    for rel, text in files.items():
        path = os.path.join(root, "third_party", "ps2recomp", *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)


def _row(name, cls="Shipping", meaning="m.", read=()):
    return {"name": name, "cls": cls, "kind": "Int", "default": "", "meaning": meaning, "read": list(read)}


class TheTreeTest(unittest.TestCase):
    def test_every_shipping_and_switch_row_cites_where_it_is_read(self):
        self.assertEqual(knobs.citation_problems(), [])

    def test_a_meaning_names_only_log_lines_the_code_prints(self):
        self.assertEqual(knobs.log_tag_problems(), [])

    def test_every_shipping_and_switch_row_carries_a_citation(self):
        rows = knobs.table()
        bare = [r["name"] for r in rows if r["cls"] in knobs.CITED_CLASSES and not r["read"]]
        self.assertEqual(bare, [])

    def test_the_unverified_mark_closes_a_meaning_when_it_is_used(self):
        for r in knobs.table():
            if knobs.UNVERIFIED in r["meaning"]:
                self.assertTrue(r["meaning"].endswith(knobs.UNVERIFIED), r)

    def test_net_stats_names_the_counter_it_switches(self):
        # The defect this task was opened for, pinned by its substance: the knob is the 0x200 RX counter.
        row = {r["name"]: r for r in knobs.table()}["PS2X_SOCOM2_NET_STATS"]
        self.assertIn("0x200", row["meaning"])
        self.assertNotIn("[net-stats]", row["meaning"])


class ParserTest(unittest.TestCase):
    def test_a_row_carries_its_citation(self):
        with tempfile.TemporaryDirectory() as root:
            header = os.path.join(root, "knobs.h")
            with open(header, "w", encoding="utf-8") as fh:
                fh.write('    X("PS2X_A", Shipping, Int, "1", "One.") /* read: ps2xRuntime/src/a.cpp:f '
                         'ps2xRuntime/include/b.h:g */ \\\n'
                         '    X("PS2X_B", Dev, Flag, "0", "Two.") \\\n')
            rows = knobs.table(header)
            self.assertEqual(rows[0]["read"], [("ps2xRuntime/src/a.cpp", "f"), ("ps2xRuntime/include/b.h", "g")])
            self.assertEqual(rows[0]["meaning"], "One.")
            self.assertEqual(rows[1]["read"], [])

    def test_the_enclosing_function_is_named_through_lambdas_and_control_blocks(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"ps2xRuntime/src/a.cpp": (
                "namespace n\n{\n"
                "    float PS2Audio::mix(int x) const\n    {\n"
                "        static const float s = [] {\n"
                "            const char *e = ps2x::knob(\"PS2X_A\");   // { a brace in a comment\n"
                "            return e ? 1.0f : \"}\"[0];\n        }();\n"
                "        if (x) { return envFlag(\"PS2X_B\", true); }\n"
                "#if defined(X)\n        {\n            ps2x::knob(\"PS2X_C\");\n        }\n#endif\n"
                "        // ps2x::knob(\"PS2X_D\") in a comment is not a read\n"
                "        env.push_back(\"PS2X_E=1\");\n        return s;\n    }\n}\n")})
            sites = knobs.read_sites(root)
            self.assertEqual(sites["PS2X_A"], [("ps2xRuntime/src/a.cpp", 6, "mix")])
            self.assertEqual(sites["PS2X_B"], [("ps2xRuntime/src/a.cpp", 9, "mix")])
            self.assertEqual(sites["PS2X_C"], [("ps2xRuntime/src/a.cpp", 12, "mix")])
            self.assertNotIn("PS2X_D", sites)
            self.assertNotIn("PS2X_E", sites)

    def test_a_constructor_initialiser_list_read_names_the_constructor(self):
        # gs_gl_backend.cpp's GSGlBackend() reads PS2X_GS_PENDING_CAP_MB this way; the brace stack alone gave None.
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"ps2xRuntime/src/a.cpp": (
                "Backend::Backend()\n    : m_a(parse(ps2x::knob(\"PS2X_A\"), 1)),\n"
                "      m_b(ps2x::knob(\"PS2X_B\"))\n{\n    if (ps2x::knobOn(\"PS2X_C\")) {\n    }\n}\n")})
            sites = knobs.read_sites(root)
            self.assertEqual(sites["PS2X_A"], [("ps2xRuntime/src/a.cpp", 2, "Backend")])
            self.assertEqual(sites["PS2X_B"], [("ps2xRuntime/src/a.cpp", 3, "Backend")])
            self.assertEqual(sites["PS2X_C"], [("ps2xRuntime/src/a.cpp", 5, "Backend")])

    def test_a_raw_string_cannot_move_the_brace_count(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"ps2xRuntime/src/a.cpp": (
                "void f()\n{\n    const char *s = R\"js(}}\" { )\" )js\";\n}\n"
                "void g()\n{\n    ps2x::knob(\"PS2X_A\");\n}\n")})
            self.assertEqual(knobs.read_sites(root)["PS2X_A"], [("ps2xRuntime/src/a.cpp", 7, "g")])


class CitationRuleTest(unittest.TestCase):
    FILES = {"ps2xRuntime/src/a.cpp": "int f()\n{\n    return ps2x::knob(\"PS2X_A\") != nullptr;\n}\n"
                                      "int g()\n{\n    return 0;\n}\n"}

    def test_a_correct_citation_passes(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, self.FILES)
            rows = [_row("PS2X_A", read=[("ps2xRuntime/src/a.cpp", "f")])]
            self.assertEqual(knobs.citation_problems(root, rows), [])

    def test_a_shipping_or_switch_row_without_a_citation_fails_and_a_dev_row_need_not_cite(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, self.FILES)
            found = knobs.citation_problems(root, [_row("PS2X_A", cls="Switch"), _row("PS2X_Z", cls="Dev")])
            self.assertEqual(len(found), 1, found)
            self.assertIn("PS2X_A is Switch and its row cites no read site", found[0])

    def test_a_cited_function_that_no_longer_reads_the_name_fails(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, self.FILES)
            found = knobs.citation_problems(root, [_row("PS2X_A", read=[("ps2xRuntime/src/a.cpp", "f"),
                                                                         ("ps2xRuntime/src/a.cpp", "g")])])
            self.assertEqual(found, ["PS2X_A cites ps2xRuntime/src/a.cpp:g and that function does not read it"])

    def test_a_cited_file_that_does_not_exist_fails(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, self.FILES)
            found = knobs.citation_problems(root, [_row("PS2X_A", read=[("ps2xRuntime/src/a.cpp", "f"),
                                                                         ("ps2xRuntime/src/gone.cpp", "f")])])
            self.assertEqual(len(found), 1, found)
            self.assertIn("no such file", found[0])

    def test_a_read_at_a_site_the_row_does_not_cite_fails(self):
        with tempfile.TemporaryDirectory() as root:
            files = dict(self.FILES)
            files["ps2xShared/src/b.cpp"] = "void h()\n{\n    if (ps2x::knobOn(\"PS2X_A\", true)) {}\n}\n"
            _tree(root, files)
            found = knobs.citation_problems(root, [_row("PS2X_A", read=[("ps2xRuntime/src/a.cpp", "f")])])
            self.assertEqual(found, ["PS2X_A is read at ps2xShared/src/b.cpp:3 in h and its row does not cite it"])

    def test_a_log_line_no_source_prints_fails(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"ps2xRuntime/src/a.cpp": "std::cout << \"[gs-gl stats] n=\" << n;\n"})
            rows = [_row("PS2X_A", cls="Dev", meaning="The [gs-gl stats] line."),
                    _row("PS2X_B", cls="Dev", meaning="The periodic [net-stats] line; 0 silences it.")]
            self.assertEqual(knobs.log_tag_problems(root, rows),
                             ["PS2X_B's meaning names the log line [net-stats] and no shipped source prints it"])

    def test_a_log_tag_matches_only_with_its_closing_bracket(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, {"ps2xRuntime/src/a.cpp": "std::cout << \"[net-stats-old] n\";\n"})
            rows = [_row("PS2X_B", cls="Dev", meaning="The [net-stats] line.")]
            self.assertEqual(len(knobs.log_tag_problems(root, rows)), 1)

    def test_a_dev_row_that_cites_is_held_to_the_citation(self):
        with tempfile.TemporaryDirectory() as root:
            _tree(root, self.FILES)
            found = knobs.citation_problems(root, [_row("PS2X_A", cls="Dev", read=[("ps2xRuntime/src/a.cpp", "g")])])
            self.assertEqual(len(found), 2, found)


if __name__ == "__main__":
    unittest.main()
