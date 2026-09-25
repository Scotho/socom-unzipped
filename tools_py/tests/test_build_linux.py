"""scripts/build_linux.sh test: both suites run, both verdicts print, non-zero if either failed.

The socom-linux VM's run on 2026-09-22 produced 18 Python failures, 7 errors -- and no idea whether
ps2x_tests passed, because the Python line was a bare command under `set -e` and ended the step. The fix
landed with a careful read and a `bash -n` and nothing that would fail if somebody put the bare command
back (review I5).

So `test_step` is driven here, on the Windows host, with its four moving parts replaced: PYTHON is a shim
that exits on demand, `configure_runtime` and `cmake` are shell functions, and RTBUILD points at a temp
tree holding a `ps2xTest/ps2x_tests` that exits on demand. Nothing is configured, nothing is compiled,
no lock is taken. The script exposes BUILD_LINUX_SOURCE_ONLY for exactly this -- the same testability
knob scripts/make_portable.sh already carries for MAKE_PORTABLE_SYSTEM and LDD.
"""
import os
import re
import stat
import subprocess
import tempfile
import unittest

from tools_py.tests.shell import BASH

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "build_linux.sh")


def write_exe(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@unittest.skipUnless(BASH, "no Git Bash on this machine (tools_py/tests/shell.py)")
class TestStep(unittest.TestCase):
    """The control flow itself, run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = self.tmp.name.replace("\\", "/")
        # a "python" that answers the interpreter probe and then exits with what the case asks for
        self.py = tmp + "/pyshim"
        write_exe(self.py, "#!/bin/sh\ncase \"$1\" in\n  -c) exit 0 ;;\nesac\nexit ${PYSHIM_RC:-0}\n")
        # ps2x_tests, likewise
        self.rtbuild = tmp + "/rtbuild"
        write_exe(self.rtbuild + "/ps2xTest/ps2x_tests", "#!/bin/sh\nexit ${CXXSHIM_RC:-0}\n")

    def drive(self, py_rc=0, cxx_rc=0, cmake_rc=0):
        script = (
            'export BUILD_LINUX_SOURCE_ONLY=1\n'
            'export PYTHON="%s"\n'
            '. scripts/build_linux.sh\n'
            'RTBUILD="%s"\n'
            'JOBS=1\n'
            'configure_runtime() { return 0; }\n'
            'cmake() { return %d; }\n'
            'export PYSHIM_RC=%d CXXSHIM_RC=%d\n'
            # `|| rc=$?`, because the script's own `set -e` is still in force here: a plain call that
            # returns non-zero would end this harness before it could report, which is precisely the
            # production behaviour (test_step is the script's last command, so its return is the exit
            # status) but tells the test nothing.
            'rc=0\n'
            'test_step || rc=$?\n'
            'echo "STEP_RC=$rc"\n'
        ) % (self.py, self.rtbuild, cmake_rc, py_rc, cxx_rc)
        p = subprocess.run([BASH, "-c", script], cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, "PS2X_TEST_REPEAT": "1"})
        return p, p.stdout + p.stderr

    def step_rc(self, out):
        m = re.search(r"STEP_RC=(\d+)", out)
        self.assertIsNotNone(m, out)
        return int(m.group(1))

    def test_both_pass(self):
        p, out = self.drive()
        self.assertEqual(self.step_rc(out), 0, out)
        self.assertIn("tests: Python: ok", out)
        self.assertIn("C++   : ok", out)
        self.assertIn("tests: ok", out)

    def test_a_failing_python_suite_does_not_stop_the_c_plus_plus_one(self):
        """The regression this guards: the VM learned nothing about ps2x_tests because the step ended."""
        p, out = self.drive(py_rc=1)
        self.assertIn("tests: Python: FAILED (exit 1)", out)
        self.assertIn("C++   : ok", out)          # it ran, and it is reported
        self.assertEqual(self.step_rc(out), 1, out)
        self.assertNotIn("tests: ok", out)

    def test_a_failing_c_plus_plus_suite_fails_the_step(self):
        p, out = self.drive(cxx_rc=1)
        self.assertIn("tests: Python: ok", out)
        self.assertIn("C++   : FAILED", out)
        self.assertEqual(self.step_rc(out), 1, out)

    def test_both_failing_reports_both(self):
        p, out = self.drive(py_rc=1, cxx_rc=1)
        self.assertIn("tests: Python: FAILED", out)
        self.assertIn("C++   : FAILED", out)
        self.assertEqual(self.step_rc(out), 1, out)

    def test_a_c_plus_plus_suite_that_did_not_build_says_did_not_measure(self):
        p, out = self.drive(cmake_rc=1)
        self.assertIn("did not run", out)
        self.assertIn("C++   : FAILED (exit 2)", out)   # 2 is "did not measure", not "failed"
        self.assertEqual(self.step_rc(out), 1, out)

    def test_sourcing_it_builds_nothing(self):
        """BUILD_LINUX_SOURCE_ONLY must stop before the case that runs a step, or this file would
        configure CMake on whoever ran the suite."""
        p = subprocess.run([BASH, "-c", 'export BUILD_LINUX_SOURCE_ONLY=1\n. scripts/build_linux.sh\n'
                                        'echo SOURCED; type -t test_step'],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("SOURCED", p.stdout)
        self.assertIn("function", p.stdout)
        self.assertNotIn("cmake", p.stderr.lower())


class TheScriptText(unittest.TestCase):
    """The one line whose shape is the whole fix, pinned as text as well as behaviour."""

    def setUp(self):
        with open(SCRIPT, encoding="utf-8") as fh:
            self.body = fh.read()

    def test_the_python_suite_is_not_a_bare_command_under_set_e(self):
        m = re.search(r"^\s*\(\s*cd \"\$ROOT\".*unittest discover.*$", self.body, re.M)
        self.assertIsNotNone(m, "the Python suite line moved -- re-point this test")
        self.assertIn("|| py_rc=$?", m.group(0),
                      "a bare command here ends the step under `set -e` and the C++ result is never measured")

    def test_the_step_is_still_the_scripts_last_word(self):
        """test_step's return has to become the script's exit status, or the non-zero is lost."""
        self.assertRegex(self.body, r"test\)\s+test_step ;;")