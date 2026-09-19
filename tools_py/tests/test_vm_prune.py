"""scripts/vm_sync.sh tree untars over the guest and never deleted: a `git mv` left the old header in the
guest, where it shadowed the new one and broke the VM build (Sprint 9 Goal 1, the VM ring)."""
import unittest

from tools_py import vm_prune


class VmPrune(unittest.TestCase):
    def test_a_file_gone_from_the_host_is_stale_in_the_guest(self):
        host = ["tools_py/a.py", "third_party/ps2recomp/ps2xShared/src/x.cpp"]
        guest = host + ["third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h"]
        self.assertEqual(vm_prune.stale(host, guest),
                         ["third_party/ps2recomp/ps2xLauncher/include/launcher/launcher_config.h"])

    def test_nothing_outside_the_pruned_roots_is_ever_named(self):
        guest = ["recomp/output/f.cpp", "third_party/ps2recomp/build-linux/x.o", "dist-linux/socom2",
                 "game/disc.iso", "tools_py/__pycache__/a.pyc", "tools_py/old.py"]
        self.assertEqual(vm_prune.stale([], guest), ["tools_py/old.py"])

    def test_separators_and_dot_prefixes_do_not_matter(self):
        self.assertEqual(vm_prune.stale([r".\tools_py\a.py"], ["./tools_py/a.py"]), [])

    def test_a_name_that_could_escape_the_tree_is_refused(self):
        self.assertEqual(vm_prune.stale([], ["tools_py/../../etc/passwd", "/tools_py/x.py"]), [])


if __name__ == "__main__":
    unittest.main()
