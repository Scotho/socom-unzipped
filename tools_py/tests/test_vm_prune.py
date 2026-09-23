"""scripts/vm_sync.sh tree untars over the guest and never deleted: a `git mv` left the old header in the
guest, where it shadowed the new one and broke the VM build (Sprint 9 Goal 1, the VM ring).

Sprint 11 Task 18: the prune covered five source roots and NOT docs/, so when
docs/HANDOFF-2026-09-08.md, docs/HANDOFF-AUDIT-2026-09-14.md and twelve Sprint 1-6 spec/plan files moved
into docs/archive/ on the host, the guest kept both copies and `python3 -m tools_py.docmaint` failed on
every duplicate. The host's side of the comparison is now `git ls-files` as well as the walk: a file the
host deleted outright is gone from both, and a file the host merely stopped tracking is still protected
by the walk.

What is never touched: the directories the tar does not send (build trees, dist*, logs, vm, recomp/output,
tools/, research, node_modules, game/) and the guest's own .git. Root-level files are not pruned either --
the walk does not descend from the root, and a renamed README is not the failure this guards.
"""
import os
import subprocess
import sys
import tempfile
import unittest

from tools_py import vm_prune


def tree(root, paths):
    for rel in paths:
        path = os.path.join(root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("x\n")
    return root


def walk(root):
    """What the guest's `find <roots> -type f` prints, near enough for a test."""
    out = []
    for base in vm_prune.ROOTS:
        for dirpath, _dirs, files in os.walk(os.path.join(root, base.replace("/", os.sep))):
            out.extend(os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/") for f in files)
    return out


class VmPrune(unittest.TestCase):
    def test_a_file_gone_from_the_host_is_stale_in_the_guest(self):
        host = ["tools_py/a.py", "third_party/ps2recomp/ps2xShared/src/x.cpp"]
        guest = host + ["third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h"]
        self.assertEqual(vm_prune.stale(host, guest),
                         ["third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h"])

    def test_a_document_moved_into_docs_archive_is_stale(self):
        """The 2026-09-22 failure: fourteen files moved into docs/archive/ and the guest kept both copies."""
        host = ["docs/archive/HANDOFF-2026-09-08.md", "docs/HANDOFF.md"]
        guest = host + ["docs/HANDOFF-2026-09-08.md", "docs/HANDOFF-AUDIT-2026-09-14.md"]
        self.assertEqual(vm_prune.stale(host, guest),
                         ["docs/HANDOFF-2026-09-08.md", "docs/HANDOFF-AUDIT-2026-09-14.md"])

    def test_nothing_outside_the_pruned_roots_is_ever_named(self):
        guest = ["recomp/output/f.cpp", "third_party/ps2recomp/build-linux/x.o", "dist-linux/socom2",
                 "game/disc.iso", "tools_py/__pycache__/a.pyc", "tools_py/old.py"]
        self.assertEqual(vm_prune.stale([], guest), ["tools_py/old.py"])

    def test_what_the_sync_never_sends_is_never_deleted(self):
        """The guest's own build trees, logs, keys, extracted disc and git directory are not the host's to
        manage. server/ is in the list too: it IS synced now, but the tar deliberately leaves
        server/config/simulated.db behind, and that file is the guest's."""
        guest = ["server/config/medius.json", "server/linux/horizon-ctl.sh", "vm/keys/socom_linux",
                 "logs/run.log", "research/x.md", "node_modules/a/index.js", "tools/cmake/bin/cmake",
                 ".git/index", "dist/socom2.exe", "dist-linux-release/socom2",
                 "third_party/ps2recomp/build-clang/x.o", "third_party/ps2recomp/build-tools/y.o"]
        self.assertEqual(vm_prune.stale([], guest), [])

    def test_separators_and_dot_prefixes_do_not_matter(self):
        self.assertEqual(vm_prune.stale([r".\tools_py\a.py"], ["./tools_py/a.py"]), [])

    def test_a_name_that_could_escape_the_tree_is_refused(self):
        self.assertEqual(vm_prune.stale([], ["tools_py/../../etc/passwd", "/tools_py/x.py"]), [])


class TwoTrees(unittest.TestCase):
    """The deletion decision over a host tree and a guest tree on disk -- the shape vm_sync.sh drives,
    with nothing of the SSH/tar shell in it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.host = tree(os.path.join(self.tmp.name, "host"),
                         ["docs/HANDOFF.md", "docs/archive/HANDOFF-2026-09-08.md", "tools_py/live.py",
                          "tests/fixtures/a.json", "ghidra_scripts/Find.java"])
        self.guest = tree(os.path.join(self.tmp.name, "guest"),
                          ["docs/HANDOFF.md", "docs/HANDOFF-2026-09-08.md", "tools_py/live.py",
                           "tools_py/gone.py", "tests/fixtures/a.json", "ghidra_scripts/Find.java",
                           "logs/run.log", "dist-linux/socom2"])

    def test_the_guest_loses_exactly_what_the_host_no_longer_has(self):
        stale = vm_prune.stale(vm_prune.host_files(self.host), walk(self.guest))
        self.assertEqual(stale, ["docs/HANDOFF-2026-09-08.md", "tools_py/gone.py"])

    def test_a_host_file_git_does_not_track_still_protects_its_guest_twin(self):
        """host_files() is git ls-files AND the walk: an operator's untracked scratch file under a synced
        root is not a reason to delete the guest's copy."""
        tree(self.host, ["tools_py/scratch.py"])
        tree(self.guest, ["tools_py/scratch.py"])
        self.assertNotIn("tools_py/scratch.py", vm_prune.stale(vm_prune.host_files(self.host), walk(self.guest)))

    def test_the_host_list_carries_what_git_tracks(self):
        """In a real checkout the tracked set is in the list even when the walk misses it."""
        listed = vm_prune.host_files(vm_prune.__file__.rsplit(os.sep + "tools_py", 1)[0])
        self.assertIn("docs/HANDOFF.md", listed)
        self.assertIn("tools_py/vm_prune.py", listed)


class TheFloor(unittest.TestCase):
    """Review I6: an empty host list means "delete every guest file under the roots".

    `tracked()` swallows every git failure and returns []; `os.walk` over a root that is not there
    yields nothing. So a `sys.argv[1]` pointing anywhere without the roots -- a renamed checkout, a
    $ROOT resolved through a junction, a tree with no .git and no source dirs -- made stale() name every
    path the guest listed, and scripts/vm_sync.sh pipes that straight into `xargs -0 rm -f --` behind
    nothing but `[ -s ]`. The list is never otherwise inspected. This is the one way the prune can reach
    outside the synced set, so it refuses rather than prints."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_main(self, root, guest_lines):
        cmd = [sys.executable, "-m", "tools_py.vm_prune", root]
        return subprocess.run(cmd, input="\n".join(guest_lines), text=True, capture_output=True,
                              cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    def test_an_empty_host_list_refuses_instead_of_naming_everything(self):
        empty = os.path.join(self.tmp.name, "nothing-here")
        os.makedirs(empty)
        p = self.run_main(empty, ["tools_py/a.py", "docs/b.md", "scripts/c.sh"])
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertEqual(p.stdout.strip(), "", "it printed paths to delete from a host it could not read")
        self.assertIn("refusing to prune", p.stderr)

    def test_a_host_missing_its_roots_refuses_and_names_them(self):
        half = tree(os.path.join(self.tmp.name, "half"), ["tools_py/live.py"])
        p = self.run_main(half, ["tools_py/gone.py"])
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertEqual(p.stdout.strip(), "")
        self.assertIn("docs", p.stderr)
        self.assertIn("refusing to prune", p.stderr)

    def test_a_host_list_below_the_floor_refuses(self):
        """A checkout whose roots exist but hold almost nothing is not a host to prune against."""
        thin = tree(os.path.join(self.tmp.name, "thin"),
                    [os.path.join(r, "one.txt") for r in vm_prune.ROOTS])
        p = self.run_main(thin, ["tools_py/gone.py"])
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertIn("refusing to prune", p.stderr)

    def test_the_real_checkout_is_over_the_floor_and_still_prunes(self):
        """The floor must not refuse the thing it exists to allow."""
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        p = self.run_main(root, ["tools_py/definitely_not_a_real_file_9f3a.py", "tools_py/vm_prune.py"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.split(), ["tools_py/definitely_not_a_real_file_9f3a.py"])


class TheSyncScript(unittest.TestCase):
    """scripts/vm_sync.sh must actually ask the guest about the roots vm_prune can prune."""

    def test_the_guest_listing_covers_every_pruned_root(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        with open(os.path.join(root, "scripts", "vm_sync.sh"), encoding="utf-8") as fh:
            text = fh.read()
        find = [l for l in text.splitlines() if "-type f" in l and "find" in l]
        self.assertTrue(find, "no guest listing in vm_sync.sh")
        line = find[-1]
        for base in vm_prune.ROOTS:
            with self.subTest(base=base):
                self.assertIn(base.rstrip("/"), line)

    def test_the_tar_sends_the_server_tree(self):
        """server/config/medius.json is tracked and three Python tests read it; `--exclude=./server`
        kept it out of the guest entirely, so those tests could not run there."""
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        with open(os.path.join(root, "scripts", "vm_sync.sh"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("--exclude=./server ", text)
        self.assertNotIn("--exclude=./server\n", text)


if __name__ == "__main__":
    unittest.main()
