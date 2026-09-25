"""THIRD_PARTY_NOTICES.md and LICENSES/ (Sprint 10 H5; Sprint 11 Goal 5's bar): a dependency the build fetches, a
directory vendored under third_party/ or server/, or a DLL in the release folder that has no inventory row fails
here -- and so does a row naming a licence whose text is not in LICENSES/.

The inventory is read as the tables in the notices file; the FetchContent and ExternalProject names are read from
the tracked CMakeLists.txt files, so a new `FetchContent_Declare(foo ...)` fails this test until foo has a row.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NOTICES = os.path.join(ROOT, "THIRD_PARTY_NOTICES.md")
LICENSES = os.path.join(ROOT, "LICENSES")

# What a FetchContent name is called in the notices (the row text is matched case-insensitively).
ALIASES = {"rlimgui": "rlImGui", "elfio": "ELFIO", "nlohmann_json": "nlohmann/json", "ffmpeg_external": "FFmpeg",
           "imgui_colortextedit": "ImGuiColorTextEdit", "imgui_file_dialog": "ImGuiFileDialog"}
# Directories under third_party/ and server/ that are the project's own, not a vendored component.
OWN_DIRS = {"server/config", "server/linux", "server/scripts"}


def rows():
    """Every table row of the notices file as a list of cells."""
    out = []
    with open(NOTICES, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("|") and not line.startswith("|---") and not line.startswith("| Component"):
                out.append([c.strip() for c in line.strip().strip("|").split("|")])
    return out


def licence_ids(cell):
    """The SPDX ids a Licence cell names: `Apache-2.0 WITH LLVM-exception` is two, `FTL OR GPL-2.0-only` is two.
    The cell is ids and SPDX operators only; a parenthetical belongs in another column."""
    return set(re.findall(r"[A-Z][A-Za-z0-9.+-]*(?:-[0-9.]+(?:-(?:only|or-later))?)?", cell)) - {"WITH", "OR", "AND"}


def cmake_dependencies():
    files = subprocess.run(["git", "ls-files", "--", "third_party/ps2recomp/**CMakeLists.txt",
                            "third_party/ps2recomp/CMakeLists.txt"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    names = set()
    for rel in files:
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        names |= set(re.findall(r"FetchContent_Declare\(\s*([A-Za-z0-9_]+)", text))
        names |= set(re.findall(r"ExternalProject_Add\(\s*([A-Za-z0-9_]+)", text))
    return names


class Notices(unittest.TestCase):
    def setUp(self):
        self.rows = rows()
        self.text = "\n".join("|".join(r) for r in self.rows).lower()
        self.assertGreater(len(self.rows), 10)

    def test_every_row_has_six_cells_and_a_licence(self):
        for r in self.rows:
            with self.subTest(row=r[0]):
                self.assertEqual(len(r), 6, r)
                self.assertTrue(licence_ids(r[3]), f"{r[0]}: no licence id in {r[3]!r}")

    def test_every_licence_named_has_its_text(self):
        have = {os.path.splitext(f)[0] for f in os.listdir(LICENSES) if f.endswith(".txt")}
        for r in self.rows:
            for lid in licence_ids(r[3]):
                with self.subTest(component=r[0], licence=lid):
                    self.assertIn(lid, have, f"{r[0]} names {lid}; add LICENSES/{lid}.txt")

    def test_every_fetched_dependency_has_a_row(self):
        deps = cmake_dependencies()
        self.assertGreater(len(deps), 8)
        for name in sorted(deps):
            with self.subTest(dependency=name):
                shown = ALIASES.get(name.lower(), name).lower()
                self.assertIn(shown, self.text, f"FetchContent {name}: no row in THIRD_PARTY_NOTICES.md")

    def test_every_vendored_directory_has_a_row(self):
        tracked = subprocess.run(["git", "ls-files", "--", "third_party", "server"], cwd=ROOT,
                                 capture_output=True, text=True).stdout.split()
        dirs = set()
        for rel in tracked:
            parts = rel.split("/")
            if len(parts) > 2:
                dirs.add("/".join(parts[:2]))
        for d in sorted(dirs - OWN_DIRS):
            with self.subTest(directory=d):
                self.assertIn(f"`{d}/`".lower(), self.text, f"{d}/ is vendored and has no row")

    def test_every_release_dll_has_a_row(self):
        rel = os.path.join(ROOT, "dist-release")
        if not os.path.isdir(rel):
            self.skipTest("no dist-release/ here (a release build makes it)")
        dlls = sorted(f for f in os.listdir(rel) if f.lower().endswith(".dll"))
        self.assertTrue(dlls)
        for dll in dlls:
            with self.subTest(dll=dll):
                self.assertIn(f"`{dll}`".lower(), self.text, f"{dll} ships and has no row")

    def test_the_root_licence_is_the_gpl_the_recompiler_carries(self):
        with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as fh:
            root = fh.read()
        self.assertIn("gnu general public license", root.lower())
        self.assertIn("version 3", root.lower())


ABOUT = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xLauncher", "src", "ui", "page_about.cpp")


def component_names(cell):
    """A notices Component cell -> the names it credits: 'libc++, libunwind (llvm-mingw)' is two; a parenthetical
    is a description, not a name; 'the PS2Recomp fork' on the ABOUT page is 'PS2Recomp'."""
    cell = re.sub(r"\s*\([^)]*\)", "", cell)
    out = set()
    for part in cell.split(","):
        name = re.sub(r"^the |\s+fork$", "", part.strip())
        if name:
            out.add(name.lower())
    return out


def about_credits():
    """page_about.cpp's BUILT FROM rows: [(names, licence cell), ...]."""
    with open(ABOUT, encoding="utf-8") as fh:
        text = fh.read()
    block = re.search(r"credits\[\]\[2\]\s*=\s*\{(.*?)\n\s*\};", text, re.S).group(1)
    return [(component_names(what), licence) for what, licence in re.findall(r'\{"([^"]+)",\s*"([^"]+)"\}', block)]


class AboutAgreesWithTheNotices(unittest.TestCase):
    """Sprint 13 V8 (stranger audit row 14): ABOUT's BUILT FROM credited SDL2, which the notices say does not ship,
    and left out Dear ImGui, libjxl, libwebp and Brotli, which do. Every credit is a shipping row (Ships 'yes'; a
    'when the closure needs it' row is not shipping -- winpthreads, which nothing imports today), with the same
    licence ids, and every shipping row is credited."""

    def shipped(self):
        out = {}
        for r in rows():
            if r[5].lower().startswith("yes"):
                for name in component_names(r[0]):
                    out[name] = licence_ids(r[3])
        self.assertGreater(len(out), 8)
        return out

    def test_every_credit_ships_under_the_licence_the_notices_give(self):
        shipped = self.shipped()
        for names, licence in about_credits():
            for name in names:
                with self.subTest(credit=name):
                    self.assertIn(name, shipped, f"ABOUT credits {name}, which the notices do not list as shipping")
                    self.assertEqual(licence_ids(licence), shipped[name], f"{name}: ABOUT says {licence!r}")

    def test_every_shipped_component_is_credited(self):
        credited = set().union(*(names for names, _ in about_credits()))
        for name in sorted(self.shipped()):
            with self.subTest(component=name):
                self.assertIn(name, credited, f"{name} ships and ABOUT's BUILT FROM does not credit it")


if __name__ == "__main__":
    unittest.main()
