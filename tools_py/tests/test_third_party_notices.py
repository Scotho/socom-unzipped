"""THIRD_PARTY_NOTICES.md and LICENSES/ (Sprint 10 H5; Sprint 11 Goal 5's bar): a dependency the build fetches, a
directory vendored under third_party/ or server/, a DLL in the release folder, or a library in the Linux tarball's
lib/ (Sprint 13 C6: a fixture listing always, a real tarball when one is here) that has no inventory row fails
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
OWN_DIRS = {"server/config", "server/linux", "server/scripts", "server/ops",  # the box's backup/health/pull scripts, the project's own (Sprint 13 O3)
}


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
    The cell is ids and SPDX operators only; a parenthetical belongs in another column. An id may begin lower-case
    (`libpng-2.0`, `bzip2-1.0.6`, `libtiff` are SPDX ids; Sprint 13 C6)."""
    return set(re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", cell)) - {"WITH", "OR", "AND"}


# Sprint 13 C6: the Linux tarball's lib/. No tarball is tracked; the fixture stands in (its header says how it was
# derived), and a real one is walked as well when a local build made it.
LINUX_LIB_FIXTURE = os.path.join(ROOT, "tools_py", "tests", "fixtures", "linux_tarball_lib.txt")
LINUX_PORTABLE = [os.path.join(ROOT, d, "portable") for d in ("dist-linux-release", "dist-linux")]


def fixture_linux_libs():
    with open(LINUX_LIB_FIXTURE, encoding="utf-8") as fh:
        return [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]


def real_linux_libs():
    """lib/ of a local socom2-linux folder or tarball (make_portable's shape), or None when there is neither."""
    import tarfile
    for base in LINUX_PORTABLE:
        lib = os.path.join(base, "socom2-linux", "lib")
        if os.path.isdir(lib):
            return sorted(os.listdir(lib))
        tgz = os.path.join(base, "socom2-linux.tar.gz")
        if os.path.isfile(tgz):
            with tarfile.open(tgz) as tf:
                return sorted(m.name.rsplit("/", 1)[-1] for m in tf.getmembers()
                              if m.name.startswith("socom2-linux/lib/") and not m.isdir())
    return None


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

    def _every_library_has_a_row(self, names, where):
        self.assertTrue(names, where)
        for so in names:
            with self.subTest(library=so):
                self.assertIn(f"`{so}`".lower(), self.text, f"{so} is in {where} and has no row")

    def _every_shipped_linux_row_is_in(self, names, where):
        """The reverse: a Linux row claims only libraries the tarball carries (a row for one it does not is noise
        that reads as a licence obligation)."""
        have = set(names)
        claimed = [so for r in self.rows if r[1].startswith("Ubuntu 24.04")
                   for so in re.findall(r"`([^`]+\.so\.[^`]+)`", r[5])]
        self.assertGreater(len(claimed), 50)
        for so in claimed:
            with self.subTest(library=so):
                self.assertIn(so, have, f"a Linux row names {so}, which {where} does not carry")

    def test_every_library_in_the_linux_tarball_fixture_has_a_row(self):
        self._every_library_has_a_row(fixture_linux_libs(), "the Linux tarball's lib/ (the fixture)")

    def test_every_linux_row_names_only_libraries_of_the_fixture(self):
        self._every_shipped_linux_row_is_in(fixture_linux_libs(), "the Linux tarball's lib/ (the fixture)")

    def test_every_library_in_a_real_linux_tarball_has_a_row_and_back(self):
        names = real_linux_libs()
        if names is None:
            self.skipTest("no dist-linux*/portable/socom2-linux here (scripts/make_portable.sh on Linux makes it)")
        self._every_library_has_a_row(names, "the Linux tarball's lib/")
        self._every_shipped_linux_row_is_in(names, "the real tarball's lib/")

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

    # Sprint 13 C6 widened the notices: the libraries linked INSIDE the FFmpeg DLLs and the Linux tarball's lib/ have
    # rows too. ABOUT is the Windows launcher's page, so its scope is the Windows closure: a row in the Windows
    # sections (vendored, fetched, the toolchain's runtime) with Ships 'yes' MUST be credited; a row inside a DLL MAY
    # be credited (through its carrier's licence or its own) and is otherwise carried by the FFmpeg credit; the Linux
    # section is out of scope (a Linux row's licence never overrides a Windows row's).
    WINDOWS_SECTIONS = ("## Vendored in the tree", "## Fetched at configure time", "## The toolchain's runtime")
    INSIDE_SECTION = "## Inside the FFmpeg DLLs"

    def rows_by_section(self):
        out, section = [], ""
        with open(NOTICES, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("## "):
                    section = line.strip()
                elif line.startswith("|") and not line.startswith("|---") and not line.startswith("| Component"):
                    out.append((section, [c.strip() for c in line.strip().strip("|").split("|")]))
        return out

    def shipped(self):
        """{name: licence ids} of the Windows closure's shipping rows (required on ABOUT)."""
        out = {}
        for section, r in self.rows_by_section():
            if section.startswith(self.WINDOWS_SECTIONS) and r[5].lower().startswith("yes"):
                for name in component_names(r[0]):
                    out[name] = licence_ids(r[3])
        self.assertGreater(len(out), 8)
        return out

    def carried(self):
        """{name: licence ids} of the rows inside the FFmpeg DLLs (creditable, not required)."""
        out = {}
        for section, r in self.rows_by_section():
            if section.startswith(self.INSIDE_SECTION) and r[5].lower().startswith("yes"):
                for name in component_names(r[0]):
                    out[name] = licence_ids(r[3])
        return out

    def test_every_credit_ships_under_the_licence_the_notices_give(self):
        shipped = self.shipped()
        carried = self.carried()
        for names, licence in about_credits():
            for name in names:
                with self.subTest(credit=name):
                    row = shipped.get(name, carried.get(name))
                    self.assertIsNotNone(row, f"ABOUT credits {name}, which the notices do not list as shipping on Windows")
                    self.assertEqual(licence_ids(licence), row, f"{name}: ABOUT says {licence!r}")

    def test_every_shipped_component_is_credited(self):
        credited = set().union(*(names for names, _ in about_credits()))
        for name in sorted(self.shipped()):
            with self.subTest(component=name):
                self.assertIn(name, credited, f"{name} ships and ABOUT's BUILT FROM does not credit it")


if __name__ == "__main__":
    unittest.main()
