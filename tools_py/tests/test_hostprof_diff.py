"""Sprint 13 Task N1 -- tools_py/hostprof_diff.py pairs functions by their guest address, not their name.

Every generated function's identifier ends `_0x<start>` (research/61 §1), and Sprint 12 renamed 1,771 of them
(`sub_00338480_0x338480` -> `node_0x338480`). The diff used to count generated code by a `FUN_` prefix, so a
renamed function counted as runtime, and it could not pair a function across two executables whose names
differ. These tests build two tiny synthetic profiles, each with its own symbol table, and check that the
renamed function pairs with its old profile and still counts as generated code.
"""
import os
import shutil
import tempfile
import unittest

from tools_py import hostprof_diff as hd

BASE = 0x140000000


class GuestKey(unittest.TestCase):
    def test_the_address_suffix_and_the_placeholder_forms(self):
        self.assertEqual(hd.guest_key("node_0x338480"), 0x338480)
        self.assertEqual(hd.guest_key("sub_00338480_0x338480"), 0x338480)
        self.assertEqual(hd.guest_key("FUN_00338480"), 0x338480)
        self.assertEqual(hd.guest_key("_FUN_00338480"), 0x338480)
        self.assertEqual(hd.guest_key("sub_001C59C0"), 0x1C59C0)

    def test_a_mangled_or_demangled_symbol_keys_on_its_name(self):
        mangled = "_Z%d%s%s" % (len("node_0x338480"), "node_0x338480", "PhP12R5900ContextP9PS2Runtime")
        self.assertEqual(hd.guest_key(mangled), 0x338480)
        self.assertEqual(hd.guest_key("node_0x338480(unsigned char*, R5900Context*, PS2Runtime*)"), 0x338480)

    def test_a_runtime_symbol_has_no_key(self):
        self.assertIsNone(hd.guest_key("memcpy"))
        self.assertIsNone(hd.guest_key("_ZN10PS2Runtime3runEv"))
        self.assertIsNone(hd.guest_key("socom2_CullTrace"))


class DiffByKey(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def put(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_a_renamed_function_pairs_with_its_old_profile(self):
        # The start profile came from the pre-rename exe, the end one from the renamed exe: the same guest
        # function sits at a different host address under a different name.
        old_syms = [(BASE + 0x1000, "sub_00338480_0x338480"), (BASE + 0x2000, "memcpy")]
        new_syms = [(BASE + 0x1800, "node_0x338480"), (BASE + 0x2000, "memcpy")]
        start = self.put("pre.txt", "hostprof v1\n1010 100\n2010 50\n0 7 ext\n")
        end = self.put("end.txt", "hostprof v1\n1810 160\n2010 80\n0 9 ext\n")
        c0, e0 = hd.load(start)
        c1, e1 = hd.load(end)
        f0 = hd.per_function(c0, BASE, old_syms)
        f1 = hd.per_function(c1, BASE, new_syms)
        per, gen = hd.diff_by_key(f0, f1)
        self.assertEqual(per["node_0x338480"], 60)          # 160 - 100: paired across the rename
        self.assertEqual(per["memcpy"], 30)
        self.assertNotIn("sub_00338480_0x338480", per)
        self.assertEqual(gen, 60)                            # the renamed function is generated code
        self.assertEqual(hd.ext_delta(e0, e1), 2)

    def test_the_same_exe_on_both_sides_is_the_plain_difference(self):
        syms = [(BASE + 0x1000, "FUN_00200000_0x200000"), (BASE + 0x3000, "runtime_fn")]
        f0 = hd.per_function({0x1004: 5, 0x3000: 1}, BASE, syms)
        f1 = hd.per_function({0x1004: 12, 0x1008: 3, 0x3000: 1}, BASE, syms)
        per, gen = hd.diff_by_key(f0, f1)
        self.assertEqual(dict(per), {"FUN_00200000_0x200000": 10})
        self.assertEqual(gen, 10)


if __name__ == "__main__":
    unittest.main()
