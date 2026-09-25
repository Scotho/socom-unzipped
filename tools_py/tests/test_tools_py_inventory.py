"""Every module under tools_py/ has a reason to be there (Sprint 13 Task H4; harness audit H27-H30).

A tracked `tools_py/**/*.py` outside `tools_py/tests/` and `tools_py/research/` (and not a package `__init__.py`)
must be one of:

  * INVOKED -- its name, as a whole word, appears in another CODE file: a module, a script, a workflow, `build.sh`,
    a CMake file or a test (the 2026-09-25 harness audit's Appendix A rule: `git grep -w <name>` over
    `tools_py scripts build.sh .github tests CMakeLists.txt server`, documents excluded -- a mention in a document is
    not a caller);
  * an ENTRY POINT -- its row in docs/DEVELOPING.md's "The `tools_py/` map" says "Run it as: `python -m <module>`",
    and its own docstring carries the matching "Run: python -m <module>" line, so a person can find and run it;
  * or ARCHIVED -- moved out of tools_py/ to docs/archive/tools/, which the second test holds to a banner and a row in
    docs/archive/README.md.

On 2026-09-25 this failed with the audit's 28 less its six research/terrain scanners (research/ is out of scope: those
scripts are run by hand from their notes, DEVELOPING's map says so): 22 modules invoked by nothing.
"""
import ast
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CODE_ROOTS = ("tools_py", "scripts", "build.sh", ".github", "tests", "CMakeLists.txt", "server")
CODE_EXTS = (".py", ".sh", ".ps1", ".psm1", ".bat", ".cmd", ".yml", ".yaml", ".toml", ".cmake")
MAP_HEADING = "## The `tools_py/` map"
ARCHIVE_DIR = "docs/archive/tools"


def _git_ls(*paths):
    out = subprocess.run(["git", "ls-files", "-z", "--", *paths], cwd=ROOT, capture_output=True, check=True)
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def modules():
    """The tracked modules the rule covers, as repo-relative paths."""
    mods = []
    for p in _git_ls("tools_py"):
        if not p.endswith(".py") or os.path.basename(p) == "__init__.py":
            continue
        if p.startswith(("tools_py/tests/", "tools_py/research/")):
            continue
        mods.append(p)
    return sorted(mods)


def _is_code(path):
    base = os.path.basename(path)
    if base in ("build.sh", "CMakeLists.txt"):
        return True
    if path.endswith(CODE_EXTS):
        return True
    # extensionless hook scripts (scripts/hooks/pre-commit, pre-push)
    return path.startswith("scripts/") and "." not in base


def code_words():
    """{path: set of words} over every tracked code file under the audit's roots."""
    words = {}
    for p in _git_ls(*CODE_ROOTS):
        if not _is_code(p):
            continue
        try:
            with open(os.path.join(ROOT, p), encoding="utf-8", errors="replace") as f:
                words[p] = set(re.findall(r"\w+", f.read()))
        except OSError:
            continue
    return words


def dotted(path):
    return path[:-3].replace("/", ".")


def map_entry_points(text):
    """{dotted module: row} for every row of DEVELOPING's tools_py map that says 'Run it as: `python -m X'."""
    start = text.find(MAP_HEADING)
    if start < 0:
        return {}
    end = text.find("\n## ", start + len(MAP_HEADING))
    section = text[start:end if end > 0 else len(text)]
    out = {}
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        m = re.search(r"[Rr]un it as: `python -m (tools_py(?:\.\w+)+)", line)
        if m:
            out[m.group(1)] = line
    return out


def docstring_runs(path, module):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        doc = ast.get_docstring(ast.parse(f.read())) or ""
    return re.search(r"^\s*Run: python -m %s\b" % re.escape(module), doc, re.M) is not None


def unaccounted():
    words = code_words()
    with open(os.path.join(ROOT, "docs", "DEVELOPING.md"), encoding="utf-8") as f:
        entries = map_entry_points(f.read())
    bad = []
    for mod in modules():
        stem = os.path.basename(mod)[:-3]
        if any(stem in ws for p, ws in words.items() if p != mod):
            continue
        name = dotted(mod)
        if name in entries and docstring_runs(mod, name):
            continue
        bad.append(mod)
    return bad


class ToolsPyInventory(unittest.TestCase):
    def test_every_module_is_invoked_documented_or_archived(self):
        bad = unaccounted()
        self.assertEqual(bad, [], "%d tools_py module(s) invoked by nothing and not a documented entry point "
                         "(give it a caller, a 'Run it as:' row in DEVELOPING's tools_py map and a 'Run: python -m' "
                         "docstring line, or git mv it to docs/archive/tools/):\n  %s" % (len(bad), "\n  ".join(bad)))

    def test_an_entry_point_row_names_a_module_that_exists(self):
        with open(os.path.join(ROOT, "docs", "DEVELOPING.md"), encoding="utf-8") as f:
            entries = map_entry_points(f.read())
        names = {dotted(m) for m in modules()}
        self.assertEqual(sorted(set(entries) - names), [])

    def test_every_archived_tool_has_a_banner_and_a_row(self):
        with open(os.path.join(ROOT, "docs", "archive", "README.md"), encoding="utf-8") as f:
            readme = f.read()
        for p in _git_ls(ARCHIVE_DIR):
            if not p.endswith(".py"):
                continue
            with open(os.path.join(ROOT, p), encoding="utf-8") as f:
                head = f.read(600)
            self.assertTrue(head.startswith("# ARCHIVED"), "%s: no '# ARCHIVED' banner on line 1" % p)
            self.assertIn("`tools/%s`" % os.path.basename(p), readme, "%s: no row in docs/archive/README.md" % p)


if __name__ == "__main__":
    unittest.main()
