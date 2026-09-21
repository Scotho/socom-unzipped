"""server/linux/horizon-ctl.sh public-ip: the Linux twin of start-servers.ps1 -PublicIp (Sprint 8 Goal 12).

The servers hand clients an address to dial back on, in six fields across three files. A hosted box that
rewrites five of them, or the one it must not (dme.json's MPS.Ip, DME -> Medius on the same machine), lists no
games or never pairs a DME. What is pinned here:
  * the six fields take the new address, and nothing else in any file changes by a byte;
  * dme.json's MPS.Ip stays what it was;
  * an address that is neither an IP nor a hostname is refused and nothing is written;
  * a second run with the same address changes nothing and says so;
  * show-ip prints the advertised fields.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from tools_py.tests.shell import BASH

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "server", "linux", "horizon-ctl.sh")
CONFIG = os.path.join(ROOT, "server", "config")
FILES = ("medius.json", "dme.json", "muis.json", "nat.json")
NEW = "203.0.113.7"


def run_ctl(*args):
    return subprocess.run([BASH, SCRIPT, *args], capture_output=True, text=True, cwd=ROOT)


@unittest.skipUnless(BASH, "no bash on this host")
class HorizonCtlPublicIp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="horizon_ctl_")
        for name in FILES:
            shutil.copyfile(os.path.join(CONFIG, name), os.path.join(self.dir, name))
        self.before = {n: self.read(n) for n in FILES}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def read(self, name):
        with open(os.path.join(self.dir, name), "rb") as f:
            return f.read().decode("utf-8")

    def test_the_six_fields_and_nothing_else(self):
        r = run_ctl("public-ip", NEW, "--config-dir", self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        expected_fields = {"medius.json": ("PublicIpOverride", "NATIp"), "dme.json": ("PublicIpOverride",),
                           "muis.json": ("Endpoint",)}
        total = 0
        for name, keys in expected_fields.items():
            pattern = re.compile(r'("(?:%s)"\s*:\s*")[^"]*(")' % "|".join(keys))
            want, n = pattern.subn(lambda m: m.group(1) + NEW + m.group(2), self.before[name])
            total += n
            self.assertEqual(self.read(name), want, name + " differs by more than its advertised fields")
        self.assertEqual(total, 5 + (self.before["muis.json"].count('"Endpoint"') - 2),
                         "medius 2 + dme 1 + one Endpoint per universe entry")
        self.assertEqual(self.read("nat.json"), self.before["nat.json"])
        self.assertIn("medius.json: PublicIpOverride -> " + NEW, r.stdout)
        self.assertIn("medius.json: NATIp -> " + NEW, r.stdout)

    def test_mps_ip_is_never_touched(self):
        run_ctl("public-ip", NEW, "--config-dir", self.dir)
        mps = re.search(r'"MPS"\s*:\s*\{[^}]*?"Ip"\s*:\s*"([^"]*)"', self.read("dme.json"), re.S)
        self.assertIsNotNone(mps)
        self.assertEqual(mps.group(1), "127.0.0.1")

    def test_a_hostname_is_accepted(self):
        r = run_ctl("public-ip", "play.socom-unzipped.example", "--config-dir", self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"NATIp": "play.socom-unzipped.example"', self.read("medius.json"))

    def test_a_bad_address_is_refused_and_nothing_is_written(self):
        for bad in ("not an address", "1.2.3.4; rm -rf /", "", "bad_host!", '1.2.3.4"x'):
            r = run_ctl("public-ip", bad, "--config-dir", self.dir)
            self.assertNotEqual(r.returncode, 0, "accepted %r" % bad)
            for name in FILES:
                self.assertEqual(self.read(name), self.before[name], "%s written for %r" % (name, bad))

    def test_a_second_run_changes_nothing_and_says_so(self):
        run_ctl("public-ip", NEW, "--config-dir", self.dir)
        after = {n: self.read(n) for n in FILES}
        r = run_ctl("public-ip", NEW, "--config-dir", self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual({n: self.read(n) for n in FILES}, after)
        self.assertIn("already", r.stdout)
        self.assertNotIn("->", r.stdout)

    def test_show_ip_prints_the_advertised_fields(self):
        run_ctl("public-ip", NEW, "--config-dir", self.dir)
        r = run_ctl("show-ip", "--config-dir", self.dir)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreaterEqual(r.stdout.count(NEW), 5)
        self.assertIn("MPS.Ip", r.stdout)
        self.assertIn("127.0.0.1", r.stdout)


if __name__ == "__main__":
    unittest.main()
