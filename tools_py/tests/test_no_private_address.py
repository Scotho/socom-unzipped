"""No private address in the tracked tree unless leak_allow.txt says why (Sprint 13 Task S6).

H6's round found the owner's LAN address shipped as a DEFAULT: the Horizon configs' advertised fields, the
vendored server's SERVER_IP initialiser, the launcher's screenshot config and its C++ tests. A default is what a
stranger copies. Each became a required value (start-servers.ps1 refuses to start on the placeholder) or a
documentation address from RFC 5737 (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24).

The scan is leakcheck's own (`scan_private`, run by `tree` and `staged`), so CI's `leakcheck all` and the
pre-commit hook hold the line too; this file is the test of it, and the tree's own verdict. The planted
addresses below are built at run time, so this file carries no literal of its own.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from tools_py.release import leakcheck as L
from tools_py.release import leakrules as R

# built at run time, one per private range (10/8, 172.16/12, 192.168/16), so this file carries no literal
PRIVATE = [".".join(map(str, q)) for q in ((10, 20, 30, 40), (172, 20, 0, 9), (192, 168, 7, 7))]
DOCUMENTATION = ["192.0.2.10", "198.51.100.5", "203.0.113.7", "127.0.0.1", "0.0.0.0"]


def _hits(body):
    got = []
    L.scan_private("f.txt", body.encode("utf-8"), got)
    return got


class ScanPrivateTest(unittest.TestCase):
    def test_every_private_range_is_reported_once_per_line(self):
        for addr in PRIVATE:
            with self.subTest(addr=addr):
                got = _hits(f"server {addr}\nclean\n")
                self.assertEqual([(h.line, h.rule, h.text) for h in got], [(1, L.TRACKED_PRIVATE_RULE, addr)])
        self.assertEqual(len(_hits(" ".join(PRIVATE))), 1, "one hit per line, however many addresses")

    def test_documentation_loopback_and_lookalikes_are_not(self):
        self.assertEqual(_hits(" ".join(DOCUMENTATION)), [])
        # a version string or a longer dotted number that merely contains the shape
        lookalikes = ["v1." + PRIVATE[0] + ".5", "1" + PRIVATE[0], ".".join(("172", "32", "0", "1"))]
        self.assertEqual(_hits(" and ".join(lookalikes)), [])

    def test_a_binary_file_is_not_read_as_text(self):
        got = []
        L.scan_private("f.bin", b"\x00\x01" + PRIVATE[0].encode(), got)
        self.assertEqual(got, [])

    def test_an_allow_row_needs_the_rule_the_path_and_its_literal(self):
        allow = [(L.TRACKED_PRIVATE_RULE, "docs/archive/*", "", "the record"),
                 (L.TRACKED_PRIVATE_RULE, "src/scrub_tests.cpp", "planted lan", "a planted control")]
        mk = lambda path, ctx: L.Hit(path, 1, L.TRACKED_PRIVATE_RULE, PRIVATE[0], ctx)
        self.assertTrue(L.allowed(mk("docs/archive/x.md", "anything"), allow))
        self.assertTrue(L.allowed(mk("src/scrub_tests.cpp", "the planted lan " + PRIVATE[0]), allow))
        self.assertFalse(L.allowed(mk("src/scrub_tests.cpp", "server = " + PRIVATE[0]), allow),
                         "a new address in an allowed file is still a finding")
        self.assertFalse(L.allowed(mk("server/config/medius.json", "x"), allow))
        # and an artifact's `private-ip` is not loosened by a tracked-tree row
        art = L.Hit("docs/archive/x.md", 1, "private-ip", PRIVATE[0], "x")
        self.assertFalse(L.allowed(art, allow))

    def test_the_rule_has_a_severity_so_allow_rows_validate(self):
        self.assertIn(L.TRACKED_PRIVATE_RULE, R.SEVERITY)


def _git(cwd, *args):
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, check=True).stdout


@unittest.skipUnless(shutil.which("git"), "git is needed")
class TreeAndStagedTest(unittest.TestCase):
    """`tree` and `staged` both run the scan; `history` does not (it cannot be rewritten)."""

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="privip_")
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.name", "Test Person")
        _git(self.repo, "config", "user.email", "test@example.com")
        _git(self.repo, "config", "commit.gpgsign", "false")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def write(self, rel, body):
        p = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)

    def test_tree_and_staged_report_it_and_history_does_not(self):
        self.write("config/medius.json", '{"PublicIpOverride": "%s"}\n' % PRIVATE[2])
        self.write("config/example.json", '{"PublicIpOverride": "192.0.2.10"}\n')
        _git(self.repo, "add", "config")
        staged, _ = L.check_staged(self.repo, allow=[])
        self.assertEqual([(h.path, h.rule) for h in staged if h.rule == L.TRACKED_PRIVATE_RULE], [("config/medius.json", L.TRACKED_PRIVATE_RULE)])
        _git(self.repo, "commit", "-q", "-m", "one")
        tree, _ = L.check_tree(self.repo, allow=[])
        self.assertEqual([(h.path, h.rule) for h in tree if h.rule == L.TRACKED_PRIVATE_RULE], [("config/medius.json", L.TRACKED_PRIVATE_RULE)])
        alone, _ = L.check_tracked_private(self.repo, allow=[])
        self.assertEqual([(h.path, h.line) for h in alone], [("config/medius.json", 1)])
        hist, _ = L.check_history(self.repo, allow=[])
        self.assertEqual([h for h in hist if h.rule == L.TRACKED_PRIVATE_RULE], [])


class TheTrackedTreeTest(unittest.TestCase):
    def test_the_self_test_carries_the_control(self):
        st = L.self_test()
        self.assertEqual(st["missed"], [])

    def test_no_private_address_in_the_tracked_tree_outside_the_allow_list(self):
        """The verdict on this repository: every private address left in a tracked file has a row in
        leak_allow.txt saying why (the dated record, a planted control); a default never does."""
        hits, stats = L.check_tracked_private(L.ROOT)
        self.assertGreater(stats["files"], 1000)
        self.assertEqual([h.render() for h in hits], [])


if __name__ == "__main__":
    unittest.main()
