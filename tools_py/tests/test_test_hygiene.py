"""Every Python test under tools_py/ must be discoverable by the one runner build.sh uses:
`python -m unittest discover -s tools_py/tests -t .`.

Fails on a test_*.py outside tools_py/tests/, a pytest import, or a module-level `def test_` (unittest
never collects those). Walks tools_py/ only: the build trees under research/ps2recomp/build/_deps/
carry their own test_*.py. Before Sprint 5 Task 0, three pytest-style files in tools_py/parity/ had
never executed (docs/process-audit.md item 2).
"""
import ast
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def hygiene_violations(tools_root):
    tests_dir = os.path.normcase(os.path.join(tools_root, "tests"))
    problems = []
    for dirpath, dirnames, filenames in os.walk(tools_root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, tools_root).replace("\\", "/")
            in_tests = os.path.normcase(dirpath) == tests_dir
            if name.startswith("test_") and not in_tests:
                problems.append("%s: test file outside tools_py/tests/" % rel)
            if not (name.startswith("test_") or in_tests):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=path)
            except (SyntaxError, UnicodeDecodeError) as e:
                problems.append("%s: cannot parse (%s)" % (rel, e))
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "pytest" for a in node.names):
                    problems.append("%s:%d: imports pytest" % (rel, node.lineno))
                elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "pytest":
                    problems.append("%s:%d: imports from pytest" % (rel, node.lineno))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                    problems.append("%s:%d: module-level def %s (unittest does not collect it)"
                                    % (rel, node.lineno, node.name))
    return problems


class TestHygiene(unittest.TestCase):
    def test_tools_py_is_clean(self):
        self.assertEqual(hygiene_violations(os.path.join(ROOT, "tools_py")), [])


class TestHygieneCheckerCatchesEachDefect(unittest.TestCase):
    """The checker against a synthetic instance of each defect it exists to detect."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="hygiene_")
        os.makedirs(os.path.join(self.root, "tests"))
        os.makedirs(os.path.join(self.root, "parity"))
        self.write("tests/test_ok.py", "import unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n")
        self.write("parity/helper.py", "def test_like_name_in_a_non_test_module():\n    pass\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def test_clean_tree(self):
        self.assertEqual(hygiene_violations(self.root), [])

    def test_test_file_outside_tests(self):
        self.write("parity/test_stray.py", "import unittest\n")
        self.assertEqual(len(hygiene_violations(self.root)), 1)
        self.assertIn("outside", hygiene_violations(self.root)[0])

    def test_pytest_import(self):
        self.write("tests/test_p.py", "import pytest\n")
        self.assertIn("imports pytest", " ".join(hygiene_violations(self.root)))
        self.write("tests/test_p.py", "from pytest import mark\n")
        self.assertIn("imports from pytest", " ".join(hygiene_violations(self.root)))

    def test_module_level_test_function(self):
        self.write("tests/test_f.py", "def test_x():\n    assert True\n")
        self.assertIn("module-level def test_x", " ".join(hygiene_violations(self.root)))


if __name__ == "__main__":
    unittest.main()
