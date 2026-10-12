"""tools_py.status_map: the README's status map, generated from docs/status/status.toml.

The map (docs/status/map.svg) and its table (docs/status/detail.md) are generated files; the data file is the
only thing edited by hand. These tests hold the arithmetic, the layout's determinism, the data file's rules
(a known status, ranges that do not overlap, no empty library) and the committed outputs to their source --
`python -m tools_py.status_map --check` fails on a stale map, and so does the last class here.
"""
import contextlib
import io
import os
import re
import shutil
import tempfile
import textwrap
import unittest

from tools_py import status_map

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A planted tree: a function map of eight functions, one forced entry, two libraries and a hardware panel.
PLANT_TOML = textwrap.dedent('''\
    [functions]
    map = "recomp/map.csv"
    extra = "recomp/extra.txt"

    [[category]]
    name = "Engine"
    percent = 50

    [[category]]
    name = "Sound"
    percent = 61

    [[category]]
    name = "Server"
    percent = 41

    [[feature]]
    label = "the game"
    categories = ["Engine", "Sound"]

    [[feature]]
    label = "server"
    categories = ["Server"]

    [[library]]
    name = "liba"
    ranges = [[0x100000, 0x100040]]
    status = "ok"
    note = "a <note> & more"

    [[library]]
    name = "libb"
    ranges = [[0x100040, 0x100080], [0x1000c0, 0x100100]]
    status = "partial"
    note = "b"

    [[hardware]]
    group = "EE"

      [[hardware.component]]
      short = "R5900"
      name = "the CPU"
      status = "ok"
      weight = 3
      note = "cpu"

      [[hardware.component]]
      short = "Timers"
      name = "timers"
      status = "pending"
      weight = 1
      note = "t"
    ''')

PLANT_CSV = "Name,Start,End,Size\n" + "".join(
    "FUN_%08x,0x%08X,0x%08X,16\n" % (a, a, a + 16)
    for a in (0x100000, 0x100010, 0x100020, 0x100040, 0x100050, 0x1000c0, 0x100200, 0x0F0000))
PLANT_EXTRA = "0x100030  # forced\n0x100010  # already in the map\n# a comment\n"


class PlantedTree(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="status_map_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.write("docs/status/status.toml", PLANT_TOML)
        self.write("recomp/map.csv", PLANT_CSV)
        self.write("recomp/extra.txt", PLANT_EXTRA)

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def data(self):
        return status_map.load(os.path.join(self.root, "docs", "status", "status.toml"))


class TestArithmetic(unittest.TestCase):
    def test_percent_counts_only_ok_by_weight(self):
        pct, ok, total = status_map.percent([(3, "ok"), (1, "partial"), (1, "pending")])
        self.assertEqual((ok, total), (3, 5))
        self.assertAlmostEqual(pct, 60.0)

    def test_percent_of_nothing_is_zero(self):
        self.assertEqual(status_map.percent([]), (0.0, 0, 0))

    def test_format_percent_one_decimal(self):
        self.assertEqual(status_map.fmt_pct(2 / 3 * 100), "66.7%")
        self.assertEqual(status_map.fmt_pct(100.0), "100.0%")

    def test_squarify_fills_the_box_exactly(self):
        rects = status_map.squarify([6, 6, 4, 3, 2, 2, 1], 0, 0, 600, 400)
        self.assertEqual(len(rects), 7)
        self.assertAlmostEqual(sum(w * h for _, _, w, h in rects), 600 * 400, places=6)
        for x, y, w, h in rects:
            self.assertGreaterEqual(x, -1e-9)
            self.assertGreaterEqual(y, -1e-9)
            self.assertLessEqual(x + w, 600 + 1e-6)
            self.assertLessEqual(y + h, 400 + 1e-6)


class TestLibraries(PlantedTree):
    def test_function_starts_merge_the_forced_entries_once(self):
        starts = status_map.function_starts(self.root, self.data())
        self.assertEqual(len(starts), 9)              # eight map rows + one new forced entry
        self.assertEqual(starts, sorted(starts))
        self.assertIn(0x100030, starts)

    def test_each_function_counts_in_its_range(self):
        rows = status_map.library_rows(self.data(), status_map.function_starts(self.root, self.data()))
        by_name = {r["name"]: r for r in rows}
        self.assertEqual(by_name["liba"]["count"], 4)   # 0x100000, 10, 20 and the forced 30
        self.assertEqual(by_name["libb"]["count"], 3)   # 0x100040, 50 and the second range's c0
        self.assertEqual(sum(r["count"] for r in rows), 7)   # 0x0F0000 and 0x100200 are outside every range

    def test_overlapping_ranges_are_refused(self):
        data = self.data()
        data["library"][1]["ranges"][0] = [0x100030, 0x100080]
        with self.assertRaises(ValueError):
            status_map.library_rows(data, status_map.function_starts(self.root, data))

    def test_an_unknown_status_is_refused(self):
        data = self.data()
        data["library"][0]["status"] = "done"
        with self.assertRaises(ValueError):
            status_map.library_rows(data, status_map.function_starts(self.root, data))
        data = self.data()
        data["hardware"][0]["component"][0]["status"] = "working"
        with self.assertRaises(ValueError):
            status_map.hardware_rows(data)

    def test_a_zero_weight_or_an_empty_group_is_refused(self):
        data = self.data()
        data["hardware"][0]["component"][1]["weight"] = 0
        with self.assertRaises(ValueError):
            status_map.hardware_rows(data)
        data = self.data()
        data["hardware"][0]["component"] = []
        with self.assertRaises(ValueError):
            status_map.hardware_rows(data)

    def test_an_empty_library_is_refused(self):
        data = self.data()
        data["library"][1]["ranges"] = [[0x100300, 0x100400]]
        with self.assertRaises(ValueError):
            status_map.library_rows(data, status_map.function_starts(self.root, data))


class TestFeatures(PlantedTree):
    def test_a_badge_is_the_plain_mean_of_its_categories(self):
        rows = status_map.feature_rows(self.data())
        self.assertEqual([(r["label"], r["percent"]) for r in rows], [("the game", 55.5), ("server", 41.0)])

    def test_an_unknown_category_is_refused(self):
        data = self.data()
        data["feature"][0]["categories"].append("Web companion")
        with self.assertRaises(ValueError):
            status_map.feature_rows(data)

    def test_detail_says_how_each_badge_is_computed(self):
        md = status_map.outputs(self.root)["docs/status/detail.md"]
        self.assertIn("| Engine | 50 | the game |", md)
        self.assertIn("plain mean of 2 category scores", md)


class TestRender(PlantedTree):
    def outputs(self):
        return status_map.outputs(self.root)

    def test_render_is_deterministic(self):
        self.assertEqual(self.outputs(), self.outputs())

    def test_svg_names_every_library_and_component(self):
        svg = self.outputs()["docs/status/map.svg"]
        self.assertTrue(svg.startswith("<svg "), svg[:40])
        for name in ("liba", "libb", "R5900", "Timers", "EE"):
            self.assertIn(name, svg)
        self.assertIn("a &lt;note&gt; &amp; more", svg)     # notes are escaped into the tooltips
        self.assertIn("57.1%", svg)                          # libraries: 4 of 7 functions work
        self.assertIn("75.0%", svg)                          # hardware: weight 3 of 4
        self.assertIn(">56%<", svg)                          # the game: the mean of 50 and 61, rounded
        self.assertIn(">41%<", svg)                          # server: its one category

    def test_every_library_block_has_its_own_outline(self):
        """An unlabelled block must not read as part of a labelled neighbour: each library is outlined."""
        svg = self.outputs()["docs/status/map.svg"]
        self.assertEqual(svg.count('class="lib-edge"'), 2)

    def test_percentage_badges_are_not_status_coloured(self):
        """A badge's value is a number, not a status: '41%' must not read as the legend's 'Partial'."""
        svg = self.outputs()["docs/status/map.svg"]
        values = [line for line in svg.splitlines() if 'font-weight="600" text-anchor="middle"' in line]
        self.assertEqual(len(values), 4, values)             # two panel badges, two feature badges
        for line in values:
            self.assertIn('class="pct-t"', line)
        self.assertIn('class="pct"', svg)

    def test_detail_lists_every_row(self):
        md = self.outputs()["docs/status/detail.md"]
        self.assertIn("| `liba` | 4 |", md)
        self.assertIn("| `libb` | 3 |", md)
        self.assertIn("| EE | R5900 | the CPU | 3 |", md)
        self.assertIn("map.svg", md)


class TestCheckMode(PlantedTree):
    def setUp(self):
        super().setUp()
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def test_check_fails_while_stale_and_passes_once_written(self):
        self.assertEqual(status_map.main(["--check"], root=self.root), 1)      # nothing written yet
        self.assertEqual(status_map.main([], root=self.root), 0)
        self.assertEqual(status_map.main(["--check"], root=self.root), 0)
        self.write("docs/status/map.svg", "<svg/>\n")                           # a hand edit
        self.assertEqual(status_map.main(["--check"], root=self.root), 1)
        self.assertEqual(status_map.main([], root=self.root), 0)
        self.write("recomp/extra.txt", PLANT_EXTRA + "0x100060\n")              # a new function in libb
        self.assertEqual(status_map.main(["--check"], root=self.root), 1)


class TestCommittedTree(unittest.TestCase):
    """The real data file and the files generated from it."""

    def test_committed_outputs_are_current(self):
        def committed(rel):
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                return None
            with open(path, encoding="utf-8") as f:       # universal newlines: a CRLF checkout is current too
                return f.read()

        stale = [rel for rel, text in status_map.outputs(ROOT).items() if committed(rel) != text]
        self.assertEqual(stale, [], "run: python -m tools_py.status_map")

    def test_every_library_has_functions_and_a_note(self):
        data = status_map.load(os.path.join(ROOT, "docs", "status", "status.toml"))
        rows = status_map.library_rows(data, status_map.function_starts(ROOT, data))
        self.assertGreaterEqual(len(rows), 10)
        for r in rows:
            self.assertGreater(r["count"], 0, r["name"])
            self.assertTrue(r["note"].strip(), r["name"])
        for group in status_map.hardware_rows(data):
            for c in group["components"]:
                self.assertTrue(c["note"].strip(), c["short"])

    def test_an_ok_row_cites_no_open_issue(self):
        """The status rule: any open defect makes a row partial. A row marked ok whose note names an issue that
        docs/BACKLOG.md still lists as open is a contradiction in the data file."""
        with open(os.path.join(ROOT, "docs", "BACKLOG.md"), encoding="utf-8") as f:
            open_issues = set(re.findall(r"^\| #(\d+) \|[^\n]*\| backlog \|", f.read(), re.M))
        self.assertIn("60", open_issues)                     # the reader itself works
        data = status_map.load(os.path.join(ROOT, "docs", "status", "status.toml"))
        rows = [(lib["name"], lib["status"], lib.get("note", "")) for lib in data["library"]]
        rows += [(c["short"], c["status"], c.get("note", "")) for g in data["hardware"] for c in g["component"]]
        bad = [(name, n) for name, status, note in rows if status == "ok"
               for n in re.findall(r"#(\d+)\b", note) if n in open_issues]
        self.assertEqual(bad, [])

    def test_no_web_or_infrastructure_figure(self):
        """Owner ruling 2026-10-12: the web part is not in the status map; the audit's 'around it' blends it in."""
        data = status_map.load(os.path.join(ROOT, "docs", "status", "status.toml"))
        names = [c["name"].lower() for c in data.get("category", [])]
        self.assertFalse([n for n in names if "web" in n or "infrastructure" in n], names)
        labels = [f["label"].lower() for f in data.get("feature", [])]
        self.assertNotIn("around it", labels)

    def test_readme_shows_the_map_linked_to_its_table(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        status = readme.split("## Current status", 1)[1].split("\n## ", 1)[0]
        self.assertIn('href="docs/status/detail.md"', status)
        self.assertIn('src="docs/status/map.svg"', status)
        self.assertLess(status.index("docs/status/map.svg"), status.index("docs/story/img/"))
        self.assertIn("python -m tools_py.status_map", status)


if __name__ == "__main__":
    unittest.main()
