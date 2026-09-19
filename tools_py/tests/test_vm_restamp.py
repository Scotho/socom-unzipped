"""scripts/vm_sync.sh tree carries the host's mtimes with the tar, so a file edited BEFORE the guest's
last build but synced AFTER it arrives looking older than the object built from its previous content.
ninja then skips it: the VM linked a launcher whose pad_render.cpp.o still held the old signature of
ui::drawPad and the link failed on a symbol the source no longer has (Sprint 9 Goal 2, the Linux ring).
The sync takes an md5 listing before and after the untar; what changed is touched with the guest's clock."""
import unittest

from tools_py import vm_restamp


class VmRestamp(unittest.TestCase):
    def test_a_file_whose_content_changed_is_restamped(self):
        before = ["aaa  tools_py/a.py", "bbb  scripts/b.sh"]
        after = ["aaa  tools_py/a.py", "ccc  scripts/b.sh"]
        self.assertEqual(vm_restamp.changed(before, after), ["scripts/b.sh"])

    def test_a_file_the_guest_did_not_have_is_restamped_too(self):
        # tar gives a brand new file the host's mtime as well, which can predate the guest's objects.
        self.assertEqual(vm_restamp.changed([], ["aaa  third_party/ps2recomp/ps2xShared/src/x.cpp"]),
                         ["third_party/ps2recomp/ps2xShared/src/x.cpp"])

    def test_a_file_that_is_gone_is_not_named_here(self):
        # Deleting is scripts/vm_sync.sh's prune step (tools_py/vm_prune.py), not this one's.
        self.assertEqual(vm_restamp.changed(["aaa  tools_py/old.py"], []), [])

    def test_two_spaces_in_the_md5sum_format_and_a_path_with_spaces(self):
        self.assertEqual(vm_restamp.changed(["aaa  a b.cpp"], ["bbb  a b.cpp"]), ["a b.cpp"])

    def test_blank_lines_and_dot_prefixes_do_not_matter(self):
        self.assertEqual(vm_restamp.changed(["aaa  ./tools_py/a.py", ""], ["aaa  tools_py/a.py", ""]), [])

    def test_a_name_that_could_escape_the_tree_is_refused(self):
        after = ["aaa  ../etc/passwd", "bbb  /etc/passwd", "ccc  tools_py/a.py"]
        self.assertEqual(vm_restamp.changed([], after), ["tools_py/a.py"])

    def test_the_order_is_stable(self):
        after = ["a  z.py", "b  a.py", "c  m.py"]
        self.assertEqual(vm_restamp.changed([], after), ["a.py", "m.py", "z.py"])


if __name__ == "__main__":
    unittest.main()
