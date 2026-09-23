"""Where the repository's shell scripts find Python: scripts/python_env.sh, and the rule that every
script goes through it.

A Debian/Ubuntu machine has no `python` -- the distribution ships `python3` and nothing else, and
`python` only appears if somebody installs python-is-python3. Every script that typed the bare word
therefore died in the socom-linux VM on 2026-09-22 with "python: command not found"
(scripts/parity/ladder_frostfire.sh:121 and scripts/make_portable.sh:91 were the two that showed).
Linux CI never saw it, because actions/setup-python puts a `python` shim on the PATH.

One rule, in one sourced file: an explicit PYTHON in the environment wins, else `python`, else
`python3`; nothing at all is a sentence on stderr and exit 2, never a silent skip.

These tests drive bash with a temporary PATH that holds a `python3` shim and no `python` at all --
the VM's shape, reproduced on the Windows host. No launch, no emulator, no network.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

from tools_py.tests.shell import BASH

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HELPER = os.path.join(ROOT, "scripts", "python_env.sh")

# A `python` spelled out in a script, as a word of its own. `python3`, `$PYTHON`, `PYTHONPATH` and
# `python_env.sh` are not it; neither is `/^python/`, which is awk's process-name regex in
# scripts/loop_lock.sh (it has to keep matching a real python3 process).
# `-` is deliberately NOT in the lookbehind: it would hide `"${PYTHON:-python}"`, which is how two of
# these scripts spelled it before this task and the likeliest way for it to come back (review I1). The
# only thing `-` bought was the prose "python-is-python3", and whole-line comments are stripped anyway.
BARE_PYTHON = re.compile(r"(?<![\w./$^])python(?![\w.-])")


def shell_scripts():
    """Every shell script the repository ships under scripts/ -- the hooks included, they run on Linux too."""
    out = subprocess.run(["git", "ls-files", "scripts"], cwd=ROOT, capture_output=True, text=True, check=True)
    keep = []
    for rel in out.stdout.split():
        path = os.path.join(ROOT, rel)
        if rel.endswith(".sh") or rel.startswith("scripts/hooks/"):
            keep.append((rel, path))
    return sorted(keep)


def strip_comments(text):
    """Whole-line `#` comments only: a prose line may say the word without invoking it."""
    return "\n".join("" if line.lstrip().startswith("#") else line for line in text.splitlines())


class PathShim(object):
    """A PATH holding exactly the interpreters asked for, and never the host's own.

    A name given as `("python", 9009)` is a STUB: a file of that name that is on the PATH and is not a
    Python. That is what Windows 11 puts at %LOCALAPPDATA%\\Microsoft\\WindowsApps\\python.exe on a
    machine where Python was never installed -- an App Execution Alias that prints nothing and exits
    9009 (review C1)."""

    def __init__(self, tmp, names):
        self.dir = os.path.join(tmp, "bin")
        os.makedirs(self.dir, exist_ok=True)
        real = sys.executable.replace("\\", "/")
        for name in names:
            rc = None
            if isinstance(name, tuple):
                name, rc = name
            path = os.path.join(self.dir, name)
            with open(path, "w", newline="\n", encoding="utf-8") as fh:
                if rc is None:
                    fh.write("#!/bin/sh\nexec '%s' \"$@\"\n" % real)
                else:
                    fh.write("#!/bin/sh\nexit %d\n" % rc)
            os.chmod(path, 0o755)

    def env(self, **extra):
        e = dict(os.environ)
        e.pop("PYTHON", None)
        e.pop("PYTHON3", None)
        keep = []
        for part in e.get("PATH", "").split(os.pathsep):
            if not part:
                continue
            try:
                names = {n.lower() for n in os.listdir(part)}
            except OSError:
                names = set()
            if names & {"python", "python.exe", "python3", "python3.exe", "py.exe"}:
                continue          # the host's own interpreter must not answer for the shim
            keep.append(part)
        e["PATH"] = os.pathsep.join([self.dir] + keep)
        e.update(extra)
        return e


def run(script, env, cwd=ROOT):
    return subprocess.run([BASH, "-c", script], cwd=cwd, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


@unittest.skipUnless(BASH, "no Git Bash on this machine (tools_py/tests/shell.py)")
class PythonEnvSh(unittest.TestCase):
    """scripts/python_env.sh -- the one resolution rule."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_python3_only_is_enough(self):
        """The VM's shape: no `python` anywhere, and the scripts still find an interpreter."""
        shim = PathShim(self.tmp.name, ["python3"])
        p = run('. scripts/python_env.sh; echo "$PYTHON"; "$PYTHON" -c "print(7*6)"', shim.env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("command not found", p.stderr)
        self.assertTrue(p.stdout.splitlines()[0].endswith("python3"), p.stdout)
        self.assertIn("42", p.stdout)

    def test_python_is_preferred_when_both_are_there(self):
        shim = PathShim(self.tmp.name, ["python", "python3"])
        p = run('. scripts/python_env.sh; echo "$PYTHON"', shim.env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.strip().endswith("python"), p.stdout)

    def test_an_explicit_python_wins(self):
        shim = PathShim(self.tmp.name, ["python", "python3"])
        p = run('. scripts/python_env.sh; echo "$PYTHON"',
                shim.env(PYTHON=os.path.join(shim.dir, "python3").replace("\\", "/")))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.strip().endswith("python3"), p.stdout)

    def test_a_python_that_is_not_an_interpreter_is_stepped_over(self):
        """Review C1. Windows 11 ships an App Execution Alias called python.exe on a machine where
        Python was never installed: `command -v` finds it, it prints nothing and exits 9009. Finding a
        file is not proving it is a Python, and scripts/bootstrap_windows.sh -- the first script a
        contributor with no Python yet is told to run -- is one of the callers."""
        shim = PathShim(self.tmp.name, [("python", 9009), "python3"])
        p = run('. scripts/python_env.sh; echo "$PYTHON"; "$PYTHON" -c "print(7*6)"', shim.env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.splitlines()[0].endswith("python3"), p.stdout)
        self.assertIn("42", p.stdout)

    def test_a_stub_python_does_not_satisfy_the_requirement_either(self):
        """The guard re-proves it rather than asking `command -v` a second time."""
        shim = PathShim(self.tmp.name, [("python", 9009), ("python3", 9009)])
        p = run('. scripts/python_env.sh; socom_require_python demo; echo REACHED', shim.env())
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertNotIn("REACHED", p.stdout)
        self.assertIn("python3", p.stderr)

    def test_an_explicit_python_that_cannot_run_is_still_refused(self):
        shim = PathShim(self.tmp.name, [("python", 9009), "python3"])
        p = run('. scripts/python_env.sh; socom_require_python demo; echo REACHED',
                shim.env(PYTHON=os.path.join(shim.dir, "python").replace("\\", "/")))
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertNotIn("REACHED", p.stdout)

    def test_no_interpreter_at_all_dies_with_a_sentence(self):
        shim = PathShim(self.tmp.name, [])
        p = run('. scripts/python_env.sh; socom_require_python demo; echo REACHED', shim.env())
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("REACHED", p.stdout)
        self.assertIn("python3", p.stderr)
        self.assertRegex(p.stderr, r"[A-Za-z].*\.")          # a sentence, not a bare token

    def test_sourcing_twice_is_harmless(self):
        shim = PathShim(self.tmp.name, ["python3"])
        p = run('. scripts/python_env.sh; first="$PYTHON"; . scripts/python_env.sh; '
                '[ "$first" = "$PYTHON" ] && echo SAME', shim.env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("SAME", p.stdout)

    def test_it_is_safe_to_source_under_set_eu(self):
        """Every caller runs `set -euo pipefail`; the resolution must not trip it when `python` is absent."""
        shim = PathShim(self.tmp.name, ["python3"])
        p = run('set -euo pipefail; . scripts/python_env.sh; echo "$PYTHON"', shim.env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.strip().endswith("python3"), p.stdout)


class TheSweepItself(unittest.TestCase):
    """BARE_PYTHON is what stands between the tree and the defect coming back; it gets its own control.

    Review finding I1: `-` was in the negative lookbehind, so `"${PYTHON:-python}"` -- the exact spelling
    this task removed from make_portable.sh and two_machine_readout.sh, and the most likely way for it to
    return -- was invisible to the sweep."""

    CAUGHT = ('python -m tools_py.x', 'py=python', 'PY="${PYTHON:-python}"', 'exec "${PYTHON:-python}" -m x',
              'PYTHONPATH="$ROOT" python -m x', 'slug="$(python -c "import x")"', 'python - "$OUT" <<EOF',
              'PY=(env PYTHONSAFEPATH=1 python -m x)')
    LEFT_ALONE = ('python3 -m x', '"${PYTHON3:-python3}"', '"$PYTHON" -m x', 'PYTHONPATH="$ROOT"',
                  '. "$ROOT/scripts/python_env.sh"', 'if (name ~ /^python/ && cmd ~ /unittest/)',
                  'PY3="${PYTHON3:-python3}"')

    def test_it_sees_every_way_a_script_can_name_the_interpreter(self):
        for line in self.CAUGHT:
            with self.subTest(line=line):
                self.assertTrue(BARE_PYTHON.search(line), line)

    def test_it_leaves_the_resolved_spellings_alone(self):
        for line in self.LEFT_ALONE:
            with self.subTest(line=line):
                self.assertIsNone(BARE_PYTHON.search(line), line)


@unittest.skipUnless(BASH, "no Git Bash on this machine (tools_py/tests/shell.py)")
class EveryScriptUsesIt(unittest.TestCase):
    """The seam that keeps the defect from coming back one script at a time."""

    def test_no_script_invokes_a_bare_python(self):
        offenders = []
        for rel, path in shell_scripts():
            if os.path.abspath(path) == os.path.abspath(HELPER):
                continue          # the one file where the word is the point: it is looking for it
            with open(path, encoding="utf-8") as fh:
                body = strip_comments(fh.read())
            for n, line in enumerate(body.splitlines(), 1):
                if BARE_PYTHON.search(line):
                    offenders.append("%s:%d: %s" % (rel, n, line.strip()))
        self.assertEqual(offenders, [],
                         "a bare `python` is not on a Linux PATH -- resolve it through scripts/python_env.sh")

    @staticmethod
    def _needs_an_interpreter(rel, text):
        """A script that really invokes it -- not one that only mentions it in a comment.
        scripts/parity/env.sh is the case: it carries the helper for the six online scripts and names
        $PYTHON in a comment, but runs nothing itself, and being sourced it must never exit."""
        if rel == "scripts/python_env.sh":
            return False
        body = strip_comments(text)
        return "$PYTHON" in body or "${PYTHON" in body

    def test_a_script_that_needs_an_interpreter_sources_the_helper(self):
        """Directly, or through scripts/parity/env.sh, which the online harness already sources."""
        offenders = []
        for rel, path in shell_scripts():
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if not self._needs_an_interpreter(rel, text):
                continue
            if "python_env.sh" in text or re.search(r'^\s*\.\s+"\$\(dirname "\$0"\)/env\.sh"', text, re.M):
                continue
            offenders.append(rel)
        self.assertEqual(offenders, [], "these use $PYTHON without reaching scripts/python_env.sh")

    def test_a_script_that_needs_an_interpreter_also_requires_one(self):
        """Review C2. Sourcing the helper only gives a script `$PYTHON`; on a machine with no
        interpreter that is the empty string, and `"" -m foo` is bash running the empty command name --
        exit 127 with the message ": command not found", blanker than the "python3: command not found"
        the hand-rolled fallbacks used to print. It is worst in the two git hooks, where a bare 127 is
        indistinguishable from the leak gate itself crashing. Every script that invokes the interpreter
        must call socom_require_python first."""
        offenders = []
        for rel, path in shell_scripts():
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if not self._needs_an_interpreter(rel, text):
                continue
            if "socom_require_python" not in strip_comments(text):
                offenders.append(rel)
        self.assertEqual(offenders, [],
                         "these invoke $PYTHON without socom_require_python: an absent interpreter is a "
                         "bare exit 127 from the empty command name, not a sentence")

    def test_the_empty_command_name_is_what_it_saves_them_from(self):
        """The failure the call prevents, shown once rather than asserted twenty times."""
        shim = PathShim(tempfile.mkdtemp(), [])
        bare = run('set -euo pipefail; . scripts/python_env.sh; "$PYTHON" -m tools_py.docmaint', shim.env())
        self.assertEqual(bare.returncode, 127, bare.stderr)
        self.assertIn("command not found", bare.stderr)
        guarded = run('set -euo pipefail; . scripts/python_env.sh; socom_require_python demo; '
                      '"$PYTHON" -m tools_py.docmaint', shim.env())
        self.assertEqual(guarded.returncode, 2, guarded.stderr)
        self.assertIn("no Python on the PATH", guarded.stderr)

    def test_only_the_helper_resolves_the_interpreter(self):
        """One rule, one place. Three scripts and the two hooks each carried their own
        `py=python; command -v python || py=python3` before this, and a fourth resolution
        (`${PYTHON:-python3}`) disagreed with all of them."""
        offenders = []
        for rel, path in shell_scripts():
            if os.path.abspath(path) == os.path.abspath(HELPER):
                continue
            with open(path, encoding="utf-8") as fh:
                body = strip_comments(fh.read())
            if "command -v python" in body or "command -v \"$PYTHON\"" in body:
                offenders.append(rel)
        self.assertEqual(offenders, [], "the interpreter is resolved in scripts/python_env.sh and nowhere else")

    def test_parity_env_sh_carries_the_helper(self):
        """The online scripts source env.sh and nothing else; if env.sh stops carrying the rule, six
        scripts lose their interpreter at once."""
        shim = PathShim(tempfile.mkdtemp(), ["python3"])
        p = run('. scripts/parity/env.sh; echo "$PYTHON"', shim.env())
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.strip().endswith("python3"), p.stdout)

    def test_every_script_still_parses(self):
        bad = [rel for rel, path in shell_scripts()
               if subprocess.run([BASH, "-n", path], capture_output=True).returncode != 0]
        self.assertEqual(bad, [])


@unittest.skipUnless(BASH, "no Git Bash on this machine (tools_py/tests/shell.py)")
class ScriptsRunWithoutPython(unittest.TestCase):
    """The scripts with a read-only path, driven for real on a PATH that has python3 and no python."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.shim = PathShim(self.tmp.name, ["python3"])

    def assertFoundAnInterpreter(self, p):
        both = p.stdout + p.stderr
        for sentence in ("python: command not found", "python: not found",
                         "no python on the PATH", "python: No such file"):
            self.assertNotIn(sentence, both, both)

    def test_disc_to_elf_check(self):
        p = run("bash scripts/disc_to_elf.sh --check", self.shim.env())
        self.assertFoundAnInterpreter(p)

    def test_two_machine_readout(self):
        a = os.path.join(self.tmp.name, "a.log")
        b = os.path.join(self.tmp.name, "b.log")
        for path in (a, b):
            open(path, "w").close()
        p = run('bash scripts/parity/two_machine_readout.sh "%s" "%s"' % (a, b), self.shim.env())
        self.assertFoundAnInterpreter(p)

    def test_vm_sync_usage(self):
        p = run("bash scripts/vm_sync.sh --nonsense", self.shim.env())
        self.assertFoundAnInterpreter(p)
        self.assertIn("usage", p.stderr)

    def test_make_portable_packages_a_linux_folder(self):
        """make_portable.sh:91 -- `$PY -m tools_py.release.leakcheck` -- is one of the two lines the VM
        actually died on. The synthetic Linux harness of test_make_portable_linux.py drives the whole
        branch here, on a PATH shaped like the VM's."""
        from tools_py.tests.test_make_portable_linux import fake_ldist
        ldist, ldd = fake_ldist(self.tmp.name)
        out = os.path.join(self.tmp.name, "out")
        env = self.shim.env(MAKE_PORTABLE_SYSTEM="Linux", LDD=ldd, PYTHON3=sys.executable,
                            LDIST=ldist, DIST=os.path.join(self.tmp.name, "nodist"))
        p = run('bash scripts/make_portable.sh "%s"' % out.replace("\\", "/"), env)
        self.assertFoundAnInterpreter(p)
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        self.assertTrue(os.path.isfile(os.path.join(out, "socom2-linux.tar.gz")), p.stdout)


if __name__ == "__main__":
    unittest.main()
