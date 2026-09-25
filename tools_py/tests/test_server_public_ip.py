"""server/start-servers.ps1 -PublicIp rewrites only the advertised-address fields.

The Horizon configs used to carry the developer's LAN address in tracked files, so a hosted server could
not be brought up anywhere else without hand-editing JSON. -PublicIp <ip> sets medius.json
(PublicIpOverride, NATIp), dme.json (PublicIpOverride) and muis.json (Universes[..].Endpoint); dme.json's
MPS.Ip is DME -> Medius on the same host and must stay 127.0.0.1.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "server", "start-servers.ps1")
CONFIG = os.path.join(ROOT, "server", "config")
FILES = ("medius.json", "dme.json", "muis.json")
NEW_IP = "203.0.113.7"
# What the tracked configs advertise since Sprint 13 S6: a documentation address (RFC 5737), never a real network.
PLACEHOLDER = "192.0.2.1"
SERVER_EXES = [os.path.join(ROOT, "server", "horizon-server", d, "bin", "Release", "net9.0", d + ".exe")
               for d in ("Server.NAT", "Server.UniverseInformation", "Server.Medius", "Server.Dme", "Server.Unified.Launcher")]


def _run(args):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SCRIPT] + args,
                          capture_output=True, text=True, cwd=ROOT)


@unittest.skipUnless(shutil.which("powershell"), "PowerShell only")
class ServerPublicIpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = os.path.join(self.tmp, "config")
        os.makedirs(self.cfg)
        for name in FILES:
            shutil.copy2(os.path.join(CONFIG, name), os.path.join(self.cfg, name))
        self.raw_before = {n: self._raw(n) for n in FILES}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _raw(self, name):
        with open(os.path.join(self.cfg, name), "r", encoding="utf-8") as f:
            return f.read()

    def _json(self, name):
        return json.loads(self._raw(name))

    def _rewrite(self, ip=NEW_IP):
        r = _run(["-ConfigDir", self.cfg, "-NoStart", "-PublicIp", ip])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def _advertised(self):
        """Every field a client is told to come back on."""
        medius, dme, muis = (self._json(n) for n in FILES)
        out = {
            "medius.json:PublicIpOverride": medius["PublicIpOverride"],
            "medius.json:NATIp": medius["NATIp"],
            "dme.json:PublicIpOverride": dme["PublicIpOverride"],
        }
        for app_id, universes in muis["Universes"].items():
            for i, u in enumerate(universes):
                out['muis.json:Universes["%s"][%d].Endpoint' % (app_id, i)] = u["Endpoint"]
        return out

    # --- the rewrite ------------------------------------------------------

    def test_public_ip_sets_every_advertised_field(self):
        self._rewrite()
        advertised = self._advertised()
        self.assertGreaterEqual(len(advertised), 5)
        for field, value in advertised.items():
            self.assertEqual(value, NEW_IP, "%s was not rewritten" % field)

    def test_mps_entry_and_every_other_field_are_untouched(self):
        self._rewrite()
        self.assertEqual(self._json("dme.json")["MPS"]["Ip"], "127.0.0.1")
        self.assertEqual(self._json("dme.json")["MPS"]["Port"], 10077)
        # Nothing but the advertised string values moved: diff the raw text line by line.
        for name in FILES:
            before, after = self.raw_before[name].splitlines(), self._raw(name).splitlines()
            self.assertEqual(len(before), len(after), "%s changed shape" % name)
            for b, a in zip(before, after):
                if b != a:
                    self.assertIn(re.search(r'"(\w+)"\s*:', b).group(1),
                                  ("PublicIpOverride", "NATIp", "Endpoint"), "%s: %r" % (name, b))
                    self.assertEqual(a, b.replace(PLACEHOLDER, NEW_IP))

    def test_ports_and_the_rest_of_the_config_survive(self):
        self._rewrite()
        medius, dme, muis = (self._json(n) for n in FILES)
        self.assertEqual((medius["MASPort"], medius["MLSPort"], medius["MPSPort"], medius["NATPort"]),
                         (10075, 10078, 10077, 10070))
        self.assertEqual((dme["TCPPort"], dme["UDPPort"]), (10073, 50000))
        self.assertEqual(dme["ApplicationIds"], [10472])
        self.assertEqual(muis["Ports"], [10071])
        self.assertTrue(medius["UsePublicIp"])
        self.assertTrue(dme["UsePublicIp"])

    def test_rewrite_is_idempotent(self):
        self._rewrite()
        once = {n: self._raw(n) for n in FILES}
        self.assertEqual(self._rewrite().returncode, 0)
        self.assertEqual({n: self._raw(n) for n in FILES}, once)

    def test_it_prints_one_line_per_field_it_changed(self):
        out = self._rewrite().stdout
        for expected in ("medius.json: PublicIpOverride -> " + NEW_IP,
                         "medius.json: NATIp -> " + NEW_IP,
                         "dme.json: PublicIpOverride -> " + NEW_IP,
                         'muis.json: Universes["10472"][0].Endpoint -> ' + NEW_IP):
            self.assertIn(expected, out)

    def test_a_bad_address_is_refused_and_nothing_is_written(self):
        r = _run(["-ConfigDir", self.cfg, "-NoStart", "-PublicIp", "not an ip"])
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual({n: self._raw(n) for n in FILES}, self.raw_before)

    # --- the placeholder is a required value (Sprint 13 S6) ------------------

    def test_the_tracked_configs_advertise_only_the_documentation_placeholder(self):
        for field, value in self._advertised().items():
            self.assertEqual(value, PLACEHOLDER, "%s: the tracked default must be the RFC 5737 placeholder" % field)

    def test_starting_on_the_placeholder_is_refused_with_the_switch_named(self):
        # On a regression the script would go on to start the servers, so never run this where they are built.
        if any(os.path.exists(p) for p in SERVER_EXES):
            self.skipTest("the Horizon servers are built here; a regression would start them")
        r = _run(["-ConfigDir", self.cfg])
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("-PublicIp", r.stderr)
        self.assertIn("RFC 5737", r.stderr)
        self.assertIn("medius.json PublicIpOverride", r.stderr)
        self.assertIn("Nothing was started", r.stderr)
        self.assertNotIn("Started ", r.stdout)
        self.assertEqual({n: self._raw(n) for n in FILES}, self.raw_before)

    def test_a_real_address_is_not_refused_by_the_placeholder_check(self):
        self._rewrite()
        r = _run(["-ConfigDir", self.cfg, "-NoStart"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("RFC 5737", r.stderr)

    # --- reading it back --------------------------------------------------

    def test_no_public_ip_leaves_the_files_alone(self):
        r = _run(["-ConfigDir", self.cfg, "-NoStart", "-ShowIp"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual({n: self._raw(n) for n in FILES}, self.raw_before)

    def test_show_ip_reports_the_advertised_address_and_flags_mps_as_host_local(self):
        self._rewrite()
        r = _run(["-ConfigDir", self.cfg, "-NoStart", "-ShowIp"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(NEW_IP, r.stdout)
        self.assertNotIn(PLACEHOLDER, r.stdout)
        self.assertIn("MPS.Ip", r.stdout)
        self.assertIn("127.0.0.1", r.stdout)


if __name__ == "__main__":
    unittest.main()
