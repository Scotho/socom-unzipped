"""Sprint 19 task E1: PS2X_PRIVATE_OVERRIDES_DIR, the CMake hook that links function bodies kept outside the public
tree into the runner.

The bar (docs/superpowers/plans/2026-10-11-sprint-19-re-foundation.md, E1): configures unset and set; the sources
land on ps2EntryRunner (not the static library, which would drop a self-registering translation unit); no public body.
The hook is ps2xRuntime/cmake/PrivateOverrides.cmake. These cases configure a small project that includes it (no
compile, no game, no generated code), once per way of setting it, and read the targets' SOURCES back through
file(GENERATE); they also hold ps2xRuntime/CMakeLists.txt to calling it on ps2EntryRunner only, inside the runner block.

The R375 review (the gfsaaser24 round-up): the hook takes only the CMake variable, never the environment; the runtime
steps of build.sh, scripts/build_linux.sh and scripts/build_macos.sh pass the environment variable through as a -D
(an unset one clears the cache) and let the hook's one line through their hidden configure output; every release step
refuses a set one. BuildScripts below drives what can be driven and reads the text of what cannot."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNTIME = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xRuntime")
MODULE = os.path.join(RUNTIME, "cmake", "PrivateOverrides.cmake")
EXE = ".exe" if os.name == "nt" else ""


def _tool(name, *pinned):
    """On PATH, else the pinned copy under tools/ (scripts/bootstrap_windows.sh) -- build.sh's own PATH order."""
    pinned_path = os.path.join(ROOT, "tools", *pinned) + EXE
    return shutil.which(name) or (pinned_path if os.path.isfile(pinned_path) else None)


CMAKE = _tool("cmake", "cmake", "bin", "cmake")
# Named explicitly: with no generator CMake on Windows falls to NMake / Visual Studio and fails before the hook runs.
NINJA = _tool("ninja", "ninja", "ninja")
GIT = shutil.which("git")
# The suite may run inside a git hook (GIT_DIR, GIT_INDEX_FILE set) or with this variable exported: neither reaches here.
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "PS2X_PRIVATE_OVERRIDES_DIR"}

PROJECT = """cmake_minimum_required(VERSION 3.20)
project(private_overrides_probe NONE)
include("{module}")
add_custom_target(ps2EntryRunner SOURCES "${{CMAKE_CURRENT_SOURCE_DIR}}/main.cpp")
add_custom_target(ps2_runtime SOURCES "${{CMAKE_CURRENT_SOURCE_DIR}}/lib.cpp")
ps2x_add_private_overrides(ps2EntryRunner)
file(GENERATE OUTPUT "${{CMAKE_BINARY_DIR}}/runner.txt" CONTENT "$<JOIN:$<TARGET_PROPERTY:ps2EntryRunner,SOURCES>,\\n>")
file(GENERATE OUTPUT "${{CMAKE_BINARY_DIR}}/runtime.txt" CONTENT "$<JOIN:$<TARGET_PROPERTY:ps2_runtime,SOURCES>,\\n>")
"""


def git(cwd, *args):
    return subprocess.run([GIT, "-c", "user.name=Probe", "-c", "user.email=probe@example.com",
                           "-c", "commit.gpgsign=false", *args],
                          cwd=cwd, env=CLEAN_ENV, capture_output=True, text=True, check=True).stdout


@unittest.skipUnless(CMAKE and NINJA, "no cmake and ninja on PATH or under tools/ (scripts/bootstrap_windows.sh)")
class PrivateOverridesConfigureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.src = os.path.join(self.tmp.name, "src")
        os.makedirs(self.src)
        for name in ("main.cpp", "lib.cpp"):
            open(os.path.join(self.src, name), "w").close()
        self.write_project(MODULE)
        self.private = os.path.join(self.tmp.name, "private")
        os.makedirs(self.private)
        for name in ("b_body.cpp", "a_body.cpp", "contract.md"):
            with open(os.path.join(self.private, name), "w") as fh:
                fh.write("// private\n")
        self.build = os.path.join(self.tmp.name, "build")

    def write_project(self, module):
        with open(os.path.join(self.src, "CMakeLists.txt"), "w", encoding="utf-8") as fh:
            fh.write(PROJECT.format(module=module.replace("\\", "/")))

    def configure(self, *defs, env_dir=None):
        env = dict(CLEAN_ENV)
        if env_dir is not None:
            env["PS2X_PRIVATE_OVERRIDES_DIR"] = env_dir
        p = subprocess.run([CMAKE, "-G", "Ninja", "-DCMAKE_MAKE_PROGRAM=" + NINJA, "-S", self.src, "-B", self.build,
                            *defs], env=env, capture_output=True, text=True)
        # CMake wraps a message at the width of the paths in it: compare its words, not its lines.
        p.stderr = " ".join(p.stderr.split())
        return p

    def sources(self, target):
        with open(os.path.join(self.build, target + ".txt"), encoding="utf-8") as fh:
            return [os.path.basename(p) for p in fh.read().split("\n") if p]

    def test_unset_changes_nothing(self):
        p = self.configure()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.sources("runner"), ["main.cpp"])
        self.assertEqual(self.sources("runtime"), ["lib.cpp"])
        self.assertNotIn("PS2X_PRIVATE_OVERRIDES_DIR", p.stdout)

    def test_set_adds_the_directorys_cpp_files_to_the_runner_only(self):
        p = self.configure("-DPS2X_PRIVATE_OVERRIDES_DIR=" + self.private)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.sources("runner"), ["main.cpp", "a_body.cpp", "b_body.cpp"])
        self.assertEqual(self.sources("runtime"), ["lib.cpp"], "never the static library")
        self.assertIn("PS2X_PRIVATE_OVERRIDES_DIR: 2 source(s)", p.stdout)

    def test_an_environment_variable_alone_adds_nothing(self):
        """Only the -D sets it: an exported variable read at configure time could not be opted out of, would lose
        to a cached -D silently, and would ride into a release configure unseen."""
        p = self.configure(env_dir=self.private)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.sources("runner"), ["main.cpp"])
        self.assertNotIn("PS2X_PRIVATE_OVERRIDES_DIR", p.stdout)

    def test_dash_d_empty_clears_a_cached_value_whatever_the_environment_says(self):
        self.assertEqual(self.configure("-DPS2X_PRIVATE_OVERRIDES_DIR=" + self.private).returncode, 0)
        p = self.configure("-DPS2X_PRIVATE_OVERRIDES_DIR=", env_dir=self.private)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.sources("runner"), ["main.cpp"])

    def test_a_missing_or_empty_directory_is_an_error_not_silence(self):
        p = self.configure("-DPS2X_PRIVATE_OVERRIDES_DIR=" + os.path.join(self.tmp.name, "nowhere"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("is not a directory", p.stderr)
        empty = os.path.join(self.tmp.name, "empty")
        os.makedirs(empty)
        shutil.rmtree(self.build, ignore_errors=True)
        p = self.configure("-DPS2X_PRIVATE_OVERRIDES_DIR=" + empty)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("holds no .cpp file", p.stderr)

    def test_a_directory_inside_the_public_tree_is_refused(self):
        p = self.configure("-DPS2X_PRIVATE_OVERRIDES_DIR=" + os.path.join(ROOT, "docs"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("inside the public tree", p.stderr)

    @unittest.skipUnless(GIT, "git is not on PATH")
    def test_a_directory_in_another_repository_passes(self):
        git(self.private, "init", "-q")
        p = self.configure("-DPS2X_PRIVATE_OVERRIDES_DIR=" + self.private)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.sources("runner"), ["main.cpp", "a_body.cpp", "b_body.cpp"])

    @unittest.skipUnless(GIT, "git is not on PATH")
    def test_a_directory_inside_another_checkout_of_this_repository_is_refused(self):
        """A linked worktree (or a clone sharing the git common dir) is this repository by another path: the
        prefix test misses it, the common dir does not. A throwaway repository stands in for this one."""
        public = os.path.join(self.tmp.name, "public")
        copy = os.path.join(public, "third_party", "ps2recomp", "ps2xRuntime", "cmake", "PrivateOverrides.cmake")
        os.makedirs(os.path.dirname(copy))
        shutil.copyfile(MODULE, copy)
        git(public, "init", "-q")
        git(public, "commit", "-q", "--allow-empty", "-m", "probe")
        linked = os.path.join(self.tmp.name, "linked")
        git(public, "worktree", "add", "-q", "--detach", linked)
        bodies = os.path.join(linked, "bodies")
        os.makedirs(bodies)
        open(os.path.join(bodies, "a_body.cpp"), "w").close()
        self.write_project(copy)
        p = self.configure("-DPS2X_PRIVATE_OVERRIDES_DIR=" + bodies)
        self.assertNotEqual(p.returncode, 0, "a body inside a linked worktree of the public repository was taken")
        self.assertIn("inside a checkout of the public repository", p.stderr)


class RunnerCallsTheHookTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(RUNTIME, "CMakeLists.txt"), encoding="utf-8") as fh:
            self.text = fh.read()

    def test_the_runner_target_and_only_it_gets_the_private_sources(self):
        self.assertRegex(self.text, r'include\("\$\{CMAKE_CURRENT_SOURCE_DIR\}/cmake/PrivateOverrides\.cmake"\)')
        calls = re.findall(r"ps2x_add_private_overrides\((\w+)\)", self.text)
        self.assertEqual(calls, ["ps2EntryRunner"])
        at = self.text.index("ps2x_add_private_overrides(ps2EntryRunner)")
        self.assertGreater(at, self.text.index("add_executable(ps2EntryRunner"))
        self.assertGreater(at, self.text.index("target_sources(ps2EntryRunner PRIVATE src/lib/game_overrides_socom2.cpp)"))

    def test_the_call_sits_inside_the_runner_block(self):
        """Inside `if(PS2X_BUILD_RUNNER)` ... its matching `endif`, by nesting, not by order alone: outside it the
        target does not exist in a clone with no generated code (CI), and the configure would fail there."""
        stack, enclosing = [], None
        for line in self.text.splitlines():
            s = line.strip()
            if re.match(r"if\s*\(", s):
                stack.append(s.split("#")[0].strip())
            elif re.match(r"endif\s*\(", s):
                stack.pop()
            elif s.startswith("ps2x_add_private_overrides("):
                enclosing = list(stack)
        self.assertEqual(stack, [], "the if/endif count does not balance -- the reader is wrong")
        self.assertIsNotNone(enclosing, "the call moved -- re-point this test")
        self.assertIn("if(PS2X_BUILD_RUNNER)", enclosing)


def write_exe(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as fh:
        fh.write(body)
    os.chmod(path, 0o755)


@unittest.skipUnless(BASH, "no Git Bash on this machine (tools_py/tests/shell.py)")
class BuildScripts(unittest.TestCase):
    """scripts/build_linux.sh is sourced (BUILD_LINUX_SOURCE_ONLY) with cmake a shell function; build.sh cannot be
    sourced, so its refusal is driven through --dry-run (it runs before the plan, as the lock consult does) and its
    two -D lines are read as text; scripts/build_macos.sh refuses any shell but an arm64 Mac's, so it is text only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name.replace("\\", "/")
        self.t, self.calls = t, t + "/cmake_args.txt"
        self.py = t + "/pyshim"
        write_exe(self.py, '#!/bin/sh\ncase "$1" in\n  -c) exit 0 ;;\nesac\nexit 0\n')

    def linux(self, body, private=None):
        env = dict(CLEAN_ENV)
        if private is not None:
            env["PS2X_PRIVATE_OVERRIDES_DIR"] = private
        script = (
            'export BUILD_LINUX_SOURCE_ONLY=1\n'
            'export PYTHON="%s"\n'
            '. scripts/build_linux.sh\n'
            'RTBUILD="%s/rt"; RELBUILD="%s/rel"; RELDIST="%s/reldist"; DIST="%s/dist"; GEN=""; JOBS=1\n'
        ) % (self.py, self.t, self.t, self.t, self.t) + body
        p = subprocess.run([BASH, "-c", script], cwd=ROOT, capture_output=True, text=True, env=env, timeout=60)
        args = ""
        if os.path.exists(self.calls):
            with open(self.calls, encoding="utf-8") as fh:
                args = fh.read()
        return p.stdout + p.stderr, args.split("\n")

    # the release configure is the first cmake call: record its arguments and end the shell there
    RELEASE_SHIM = ('cmake() { printf "%%s\\n" "$@" > "%s"; exit 0; }\n'
               'rc=0; release || rc=$?; echo "RC=$rc"\n')

    def test_linux_release_refuses_a_set_directory_before_configuring(self):
        out, args = self.linux(self.RELEASE_SHIM % self.calls, private="/somewhere/private")
        self.assertIn("RC=2", out)
        self.assertIn("PS2X_PRIVATE_OVERRIDES_DIR", out)
        self.assertIn("refused", out)
        self.assertEqual(args, [""], "release configured anyway")

    def test_linux_release_clears_it_when_unset(self):
        out, args = self.linux(self.RELEASE_SHIM % self.calls)
        self.assertNotIn("RC=", out, "the release did not reach its configure")
        self.assertIn("-DPS2X_PRIVATE_OVERRIDES_DIR=", args)

    # a configure that prints the hook's line among others, then exits with CMAKE_RC
    RUNTIME_SHIM = ('cmake() { printf "%%s\\n" "$@" > "%s"; echo "-- noise"; '
               'echo "-- PS2X_PRIVATE_OVERRIDES_DIR: 2 source(s) from /x added to ps2EntryRunner"; '
               'return ${CMAKE_RC:-0}; }\n'
               'rc=0; configure_runtime || rc=$?; echo "RC=$rc"\n')

    def test_linux_runtime_passes_the_variable_through_and_shows_its_line(self):
        out, args = self.linux(self.RUNTIME_SHIM % self.calls, private="/somewhere/private")
        self.assertIn("RC=0", out)
        self.assertIn("-DPS2X_PRIVATE_OVERRIDES_DIR=/somewhere/private", args)
        self.assertIn("PS2X_PRIVATE_OVERRIDES_DIR: 2 source(s)", out)
        self.assertNotIn("-- noise", out, "the rest of the configure output stays hidden")

    def test_linux_runtime_unset_clears_it_and_a_failed_configure_still_fails(self):
        out, args = self.linux("export CMAKE_RC=1\n" + self.RUNTIME_SHIM % self.calls)
        self.assertIn("-DPS2X_PRIVATE_OVERRIDES_DIR=", args)
        self.assertNotIn("RC=0", out, "the line filter swallowed the configure's failure")

    def build_sh(self, private=None):
        env = dict(CLEAN_ENV, BUILD_LAUNCHER_CHECK_CMD="true", LOOP_LOCK_PATH=self.t + "/lk",
                   LOOP_LOCK_PS_CMD="true")
        env.pop("LOOP_LOCK_HELD", None)
        if private is not None:
            env["PS2X_PRIVATE_OVERRIDES_DIR"] = private
        p = subprocess.run([BASH, os.path.join(ROOT, "build.sh").replace("\\", "/"), "release", "--dry-run"],
                           cwd=ROOT, capture_output=True, text=True, env=env, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def test_build_sh_release_refuses_a_set_directory(self):
        rc, out = self.build_sh(private="/somewhere/private")
        self.assertEqual(rc, 2, out)
        self.assertIn("PS2X_PRIVATE_OVERRIDES_DIR", out)
        self.assertNotIn("would run", out)
        rc, out = self.build_sh(private="")
        self.assertEqual(rc, 0, out)
        self.assertIn("would run: release", out)

    def read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return fh.read()

    def function(self, text, name):
        m = re.search(r"^%s\(\) \{.*?^\}" % name, text, re.M | re.S)
        self.assertIsNotNone(m, "%s() moved -- re-point this test" % name)
        return m.group(0)

    PASS_THROUGH = '-DPS2X_PRIVATE_OVERRIDES_DIR="${PS2X_PRIVATE_OVERRIDES_DIR-}"'

    def test_build_sh_runtime_passes_it_through_and_release_clears_it(self):
        text = self.read("build.sh")
        runtime = self.function(text, "runtime")
        self.assertIn(self.PASS_THROUGH, runtime)
        self.assertIn("grep", runtime, "the hook's line is not let through the hidden configure output")
        self.assertRegex(self.function(text, "release"), r"-DPS2X_PRIVATE_OVERRIDES_DIR=(\"\"|'')?\s")

    def test_build_macos_runtime_passes_it_through(self):
        configure = self.function(self.read("scripts/build_macos.sh"), "configure_runtime")
        self.assertIn(self.PASS_THROUGH, configure)
        self.assertIn("grep", configure)


if __name__ == "__main__":
    unittest.main()
