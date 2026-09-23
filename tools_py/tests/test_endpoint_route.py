"""Fix wave A (2026-09-22): the endpoint A/B's tool, tools_py/parity/endpoint_route.py. The registry and the audio
policy interface are not touched here; these are the selection and the refusal, which are what decide whether a
capture is scored as one leg of the A/B at all."""
import os
import subprocess
import sys
import unittest
from unittest import mock

from tools_py.parity import endpoint_route as er

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JBL_LINE = "[audio] 989snd mix stream open (48000 Hz stereo, device Speakers (JBL Flip 6), period 20 ms x 4, engine 48000 Hz)\n"
WIRED_LINE = "[audio] 989snd mix stream open (48000 Hz stereo, device Haut-parleurs (HyperX QuadCast S), period 20 ms x 4, engine 48000 Hz, dump C:\\x.wav)\n"


class TheRefusal(unittest.TestCase):
    def test_the_device_is_read_off_the_runs_own_line(self):
        self.assertEqual(er.mix_open_device("boot\n" + JBL_LINE + "more\n"), "Speakers (JBL Flip 6)")
        self.assertEqual(er.mix_open_device(WIRED_LINE), "Haut-parleurs (HyperX QuadCast S)")
        self.assertIsNone(er.mix_open_device("no audio line at all\n"))

    def test_a_run_on_the_wrong_device_is_refused(self):
        ok, msg = er.check_device(JBL_LINE, "HyperX")
        self.assertFalse(ok)
        self.assertIn("JBL Flip 6", msg)
        self.assertIn("not scored", msg)

    def test_a_run_with_no_line_is_refused_as_unknown(self):
        ok, msg = er.check_device("nothing\n", "HyperX")
        self.assertFalse(ok)
        self.assertIn("unknown", msg)

    def test_the_right_device_passes_case_insensitively(self):
        ok, msg = er.check_device(WIRED_LINE, "hyperx")
        self.assertTrue(ok, msg)

    def test_check_is_a_command_with_exit_5(self):
        log = os.path.join(ROOT, "logs", "parity", "test_endpoint_route_check.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "w", encoding="utf-8") as f:
            f.write(JBL_LINE)
        try:
            p = subprocess.run([sys.executable, "-m", "tools_py.parity.endpoint_route", "check", log, "--expect", "HyperX"],
                               cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 5, p.stdout + p.stderr)
            self.assertIn("REFUSED", p.stdout)
            p = subprocess.run([sys.executable, "-m", "tools_py.parity.endpoint_route", "check", log, "--expect", "JBL"],
                               cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        finally:
            os.remove(log)


class TheSelection(unittest.TestCase):
    ENTRIES = {
        "2130659e_0": r"{2}.\\?\bthenum#x\src/00010001|\Device\HarddiskVolume3\Projects\socom_pc\dist\socom2.exe%b{0}",
        "40efcb24_0": r"{2}.\\?\bthenum#x\src/00010001|\Device\HarddiskVolume3\Projects\socom_pc\third_party\ps2recomp\build-clang\ps2xRuntime\ps2EntryRunner.exe%b{0}",
        "6aafc465_0": r"{2}.\\?\hdaudio#y\rtspdiftopo/00010001|\Device\HarddiskVolume3\Projects\socom_pc\dist\socom2.exe%b{0}",
        "ea4c56d4_0": r"{2}.\\?\bthenum#x\src/00010001|\Device\HarddiskVolume3\Projects\wt-menu-movie\socom_pc\dist\socom2.exe%b{0}",
        "aaaa0000_0": r"{2}.\\?\bthenum#x\src/00010001|\Device\HarddiskVolume3\Users\U\Downloads\socom2-portable\socom2\socom2.exe%b{0}",
        "bbbb0000_0": r"{2}.\\?\bthenum#x\src/00010001|\Device\HarddiskVolume3\Projects\socom_pc\tools\pcsx2\pcsx2-qt.exe%b{0}",
    }

    def test_only_the_entries_for_the_exes_the_harness_launches_are_chosen(self):
        # every device's entry for dist\socom2.exe and the runner's; not a worktree's copy, not the owner's
        # Downloads copy, not PCSX2 (KNOWN section 4: the PCSX2 A entry was removed once already, and restored)
        self.assertEqual(er.entries_for_our_exes(self.ENTRIES), ["2130659e_0", "40efcb24_0", "6aafc465_0"])

    def test_the_device_must_match_exactly_one_active_render_endpoint(self):
        devices = [("id-jbl", "Speakers (JBL Flip 6)", "Active"),
                   ("id-hx", "Haut-parleurs (HyperX QuadCast S)", "Active"),
                   ("id-old", "Haut-parleurs (Realtek(R) Audio)", "NotPresent"),
                   ("id-hdmi", "Odyssey G91F (NVIDIA High Definition Audio)", "Active")]
        self.assertEqual(er.pick_device(devices, "hyperx"), ("id-hx", "Haut-parleurs (HyperX QuadCast S)"))
        with self.assertRaises(SystemExit):
            er.pick_device(devices, "Haut-parleurs (Realtek")           # not present: never a target
        with self.assertRaises(SystemExit):
            er.pick_device(devices, "e")                                # several

    def test_status_set_restore_check_are_the_commands(self):
        p = subprocess.run([sys.executable, "-m", "tools_py.parity.endpoint_route", "--help"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        for c in ("status", "set", "restore", "check"):
            self.assertIn(c, p.stdout)


class FakeRegistry:
    """The handful of winreg calls the deletion makes, over a dict of key path -> its subkey names.

    It reproduces the one rule that broke the first A/B run: RegDeleteKey (winreg.DeleteKey) refuses a key that
    still has subkeys, and refuses it with the same WinError 5 an ACL denial gives. `deny` is the second cause,
    so a test can tell the two apart.
    """
    HKEY_CURRENT_USER = object()

    class _Key:
        def __init__(self, reg, path):
            self.reg, self.path = reg, path

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.reg.closed.append(self.path)
            return False

    def __init__(self, tree, deny=()):
        self.tree = {p: list(kids) for p, kids in tree.items()}
        self.deny = set(deny)
        self.deleted = []
        self.opened = []
        self.closed = []

    def OpenKey(self, root, path):
        assert root is self.HKEY_CURRENT_USER
        if path not in self.tree:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        self.opened.append(path)
        return self._Key(self, path)

    def EnumKey(self, key, index):
        kids = self.tree[key.path]
        if index >= len(kids):
            raise OSError(22, "No more data is available")
        return kids[index]

    def DeleteKey(self, root, path):
        assert root is self.HKEY_CURRENT_USER
        if path in self.deny:
            raise PermissionError(13, "Access is denied", None, 5)
        if path not in self.tree:
            raise FileNotFoundError(2, "The system cannot find the file specified")
        if self.tree[path]:
            raise PermissionError(13, "Access is denied", None, 5)   # non-empty: RegDeleteKey will not
        del self.tree[path]
        parent, _sep, leaf = path.rpartition("\\")
        if leaf in self.tree.get(parent, []):
            self.tree[parent].remove(leaf)
        self.deleted.append(path)


class TheRoutingEntryDeletion(unittest.TestCase):
    """2026-09-22: `set` died with WinError 5 on the first entry it tried to remove. The entry has a
    {219ED5A0-...} property-store subkey (the per-app volume Windows writes when the app's slider is touched),
    and RegDeleteKey will not delete a key that has one."""
    SUB = "2130659e_0"
    PATH = er.POLICY_KEY + "\\" + SUB
    PROPS_NAME = "{219ED5A0-9CBF-4F3A-B927-37C9E5C5F14F}"
    PROPS = PATH + "\\" + PROPS_NAME

    def run_delete(self, fake):
        with mock.patch.dict(sys.modules, {"winreg": fake}):
            er.delete_routing_entry(self.SUB)

    def test_an_entry_with_a_property_store_subkey_is_removed_children_first(self):
        fake = FakeRegistry({er.POLICY_KEY: [self.SUB], self.PATH: [self.PROPS_NAME], self.PROPS: []})
        self.run_delete(fake)
        self.assertEqual(fake.deleted, [self.PROPS, self.PATH])
        self.assertNotIn(self.PATH, fake.tree)
        self.assertEqual(fake.tree[er.POLICY_KEY], [])

    def test_a_whole_subtree_goes_deepest_first(self):
        deep = self.PROPS + "\\" + "deeper"
        fake = FakeRegistry({er.POLICY_KEY: [self.SUB], self.PATH: [self.PROPS_NAME],
                             self.PROPS: ["deeper"], deep: []})
        self.run_delete(fake)
        self.assertEqual(fake.deleted, [deep, self.PROPS, self.PATH])

    def test_a_leaf_entry_is_removed_as_before(self):
        fake = FakeRegistry({er.POLICY_KEY: [self.SUB], self.PATH: []})
        self.run_delete(fake)
        self.assertEqual(fake.deleted, [self.PATH])

    def test_a_denied_entry_is_not_swallowed(self):
        # the other cause of WinError 5: the ACL. It must still reach the operator, not be hidden by the retry.
        fake = FakeRegistry({er.POLICY_KEY: [self.SUB], self.PATH: []}, deny={self.PATH})
        with self.assertRaises(PermissionError):
            self.run_delete(fake)
        self.assertIn(self.PATH, fake.tree)


if __name__ == "__main__":
    unittest.main()
