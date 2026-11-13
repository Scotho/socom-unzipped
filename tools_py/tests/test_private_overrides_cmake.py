"""Sprint 19 task E1: PS2X_PRIVATE_OVERRIDES_DIR, the CMake hook that links function bodies kept outside the public
tree into the runner.

The bar (docs/superpowers/plans/2026-10-11-sprint-19-re-foundation.md, E1): configures unset and set; the sources
land on ps2EntryRunner (not the static library, which would drop a self-registering translation unit); no public body.
The hook is ps2xRuntime/cmake/PrivateOverrides.cmake. These cases configure a small project that includes it (no
compile, no game, no generated code), once per way of setting it, and read the targets' SOURCES back through
file(GENERATE); they also hold ps2xRuntime/CMakeLists.txt to calling it on ps2EntryRunner only."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNTIME = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xRuntime")
MODULE = os.path.join(RUNTIME, "cmake", "PrivateOverrides.cmake")
CMAKE = shutil.which("cmake")

PROJECT = """cmake_minimum_required(VERSION 3.20)
project(private_overrides_probe NONE)
include("{module}")
add_custom_target(ps2EntryRunner SOURCES "${{CMAKE_CURRENT_SOURCE_DIR}}/main.cpp")
add_custom_target(ps2_runtime SOURCES "${{CMAKE_CURRENT_SOURCE_DIR}}/lib.cpp")
ps2x_add_private_overrides(ps2EntryRunner)
file(GENERATE OUTPUT "${{CMAKE_BINARY_DIR}}/runner.txt" CONTENT "$<JOIN:$<TARGET_PROPERTY:ps2EntryRunner,SOURCES>,\\n>")
file(GENERATE OUTPUT "${{CMAKE_BINARY_DIR}}/runtime.txt" CONTENT "$<JOIN:$<TARGET_PROPERTY:ps2_runtime,SOURCES>,\\n>")
"""


@unittest.skipUnless(CMAKE, "cmake is not on PATH")
class PrivateOverridesConfigureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = os.path.join(self.tmp.name, "src")
        os.makedirs(self.src)
        for name in ("main.cpp", "lib.cpp"):
            open(os.path.join(self.src, name), "w").close()
        with open(os.path.join(self.src, "CMakeLists.txt"), "w", encoding="utf-8") as fh:
            fh.write(PROJECT.format(module=MODULE.replace("\\", "/")))
        self.private = os.path.join(self.tmp.name, "private")
        os.makedirs(self.private)
        for name in ("b_body.cpp", "a_body.cpp", "contract.md"):
            with open(os.path.join(self.private, name), "w") as fh:
                fh.write("// private\n")
        self.build = os.path.join(self.tmp.name, "build")

    def configure(self, *defs, env_dir=None):
        env = {k: v for k, v in os.environ.items() if k != "PS2X_PRIVATE_OVERRIDES_DIR"}
        if env_dir is not None:
            env["PS2X_PRIVATE_OVERRIDES_DIR"] = env_dir
        p = subprocess.run([CMAKE, "-S", self.src, "-B", self.build, *defs], env=env,
                           capture_output=True, text=True)
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

    def test_the_environment_variable_sets_it_too(self):
        p = self.configure(env_dir=self.private)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.sources("runner"), ["main.cpp", "a_body.cpp", "b_body.cpp"])

    def test_unsetting_it_again_takes_the_sources_away(self):
        self.assertEqual(self.configure("-DPS2X_PRIVATE_OVERRIDES_DIR=" + self.private).returncode, 0)
        p = self.configure("-DPS2X_PRIVATE_OVERRIDES_DIR=")
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


class RunnerCallsTheHookTest(unittest.TestCase):
    def test_the_runner_target_and_only_it_gets_the_private_sources(self):
        with open(os.path.join(RUNTIME, "CMakeLists.txt"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertRegex(text, r'include\("\$\{CMAKE_CURRENT_SOURCE_DIR\}/cmake/PrivateOverrides\.cmake"\)')
        calls = re.findall(r"ps2x_add_private_overrides\((\w+)\)", text)
        self.assertEqual(calls, ["ps2EntryRunner"])
        # Inside the runner block: after the target exists, before the block closes.
        at = text.index("ps2x_add_private_overrides(ps2EntryRunner)")
        self.assertGreater(at, text.index("add_executable(ps2EntryRunner"))
        self.assertGreater(at, text.index("target_sources(ps2EntryRunner PRIVATE src/lib/game_overrides_socom2.cpp)"))

    def test_no_private_body_is_tracked(self):
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        self.assertFalse([p for p in out.split("\n") if p.startswith("overrides/") or "/private_overrides/" in p])


if __name__ == "__main__":
    unittest.main()
