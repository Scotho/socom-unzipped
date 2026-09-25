"""requirements.txt is the tree's third-party imports, pinned, and CI installs from it (Sprint 13 H7, harness audit #31).

Before H7 the only requirements file was tools_py/parity/requirements.txt -- "pillow / numpy / pytest": the runner
this suite forbids, and none of unicorn, capstone, zstandard, pycaw, comtypes, pyaudiowpatch -- while the two build
workflows installed their own hand list (numpy pillow zstandard). A stranger found the rest one traceback at a time.

The imports are read with `ast` from every tracked .py outside docs/archive/, third_party/ and server/ (the Horizon
server's Python 2 helper is not the tooling's); a module is third-party when it is not in the standard library and
no file of that name exists under tools_py/ or scripts/ (several tools put their own directory on sys.path).
"""
import ast
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REQUIREMENTS = os.path.join(ROOT, "requirements.txt")
# import name -> distribution name, where they differ
DIST = {"PIL": "pillow", "yaml": "pyyaml", "pyaudiowpatch": "pyaudiowpatch"}
# rows no module imports, and whose dependency they are
TRANSITIVE = {"psutil": "pycaw"}
SKIP_PREFIXES = ("docs/archive/", "third_party/", "server/")
ROW = re.compile(r"^([A-Za-z0-9_.-]+)==([0-9][0-9A-Za-z.]*)\s*(;\s*(.+))?$")


def requirement_rows():
    rows = {}
    with open(REQUIREMENTS, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.split("#", 1)[0].strip()
            if line:
                rows[n] = line
    return rows


def local_module_names():
    names = set()
    for base in ("tools_py", "scripts"):
        for dp, dns, fns in os.walk(os.path.join(ROOT, base)):
            names.update(fn[:-3] for fn in fns if fn.endswith(".py"))
            names.update(dns)
    return names


def third_party_imports():
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()
    std = set(sys.stdlib_module_names)
    local = local_module_names() | {"tools_py", "scripts"}
    found = {}
    for rel in files:
        if rel.startswith(SKIP_PREFIXES):
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as fh:
            try:
                tree = ast.parse(fh.read())
            except SyntaxError:
                continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            else:
                continue
            for m in mods:
                top = m.split(".")[0]
                if top not in std and top not in local:
                    found.setdefault(top, rel)
    return found


class Requirements(unittest.TestCase):
    def test_every_row_is_pinned(self):
        for n, line in requirement_rows().items():
            self.assertRegex(line, ROW, "requirements.txt:%d is not `name==version[; marker]`" % n)

    def test_no_pytest(self):
        names = [ROW.match(l).group(1).lower() for l in requirement_rows().values() if ROW.match(l)]
        self.assertNotIn("pytest", names)

    def test_no_second_requirements_file(self):
        others = [p for p in subprocess.run(["git", "ls-files", "*requirements*.txt"], cwd=ROOT, capture_output=True,
                                            text=True, check=True).stdout.split() if p != "requirements.txt"
                  and not p.startswith(SKIP_PREFIXES)]
        self.assertEqual(others, [], "one manifest: requirements.txt at the root")

    def test_every_third_party_import_has_a_row(self):
        rows = {ROW.match(l).group(1).lower() for l in requirement_rows().values() if ROW.match(l)}
        missing = {m: where for m, where in third_party_imports().items() if DIST.get(m, m).lower() not in rows}
        self.assertEqual(missing, {}, "imported but not in requirements.txt (module: first file)")

    def test_every_row_is_imported_or_says_whose_dependency_it_is(self):
        imported = {DIST.get(m, m).lower() for m in third_party_imports()}
        rows = {ROW.match(l).group(1).lower() for l in requirement_rows().values() if ROW.match(l)}
        unused = sorted(r for r in rows if r not in imported and r not in TRANSITIVE)
        self.assertEqual(unused, [], "rows nothing imports")

    def test_the_windows_audio_rows_carry_the_marker(self):
        for line in requirement_rows().values():
            m = ROW.match(line)
            if m and m.group(1).lower() in {"pycaw", "comtypes", "psutil", "pyaudiowpatch"}:
                self.assertEqual(m.group(4), 'sys_platform == "win32"', line)


class CiInstallsFromIt(unittest.TestCase):
    """Both build workflows install from requirements.txt and name no package by hand."""

    def test_build_workflows(self):
        for wf in ("linux.yml", "windows.yml"):
            with open(os.path.join(ROOT, ".github", "workflows", wf), encoding="utf-8") as f:
                text = f.read()
            installs = [l.strip() for l in text.splitlines() if "pip install" in l]
            self.assertTrue(installs, wf)
            for line in installs:
                self.assertRegex(line, r"pip install (--break-system-packages )?-r requirements\.txt$", (wf, line))


if __name__ == "__main__":
    unittest.main()
