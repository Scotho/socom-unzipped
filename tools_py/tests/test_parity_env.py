"""scripts/parity/env.sh -- the one place the online harness defines its server address and instruments.

Before this file the five online scripts each carried their own `PS2X_SOCOM2_SERVER=...:-<a LAN address>` and
three of them a verbatim copy of the ~570-character PS2X_PEEK block, so a drift in one copy silently changed
what that run measured. These tests hold the seam:

  * sourcing env.sh gives the default server and the full peek block;
  * SOCOM_SERVER_IP=<ip> in the environment points PS2X_SOCOM2_SERVER at another server (the one knob);
  * every script under scripts/parity/ that mentions PS2X_SOCOM2_SERVER sources env.sh rather than
    re-exporting its own copy.

bash only -- no launch, no emulator.
"""
import glob
import os
import re
import subprocess
import unittest
from tools_py.tests.shell import BASH

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_SH = os.path.join(ROOT, "scripts", "parity", "env.sh")
PEEK_LEN = 573          # the full instrument block, as ladder_frostfire.sh carried it
HOSTED = "socom.scotho.com"     # the hosted Horizon box, by the name the launcher's default preset uses


def run_bash(script, env=None):
    e = dict(os.environ)
    # A stale value in the runner's own environment would win over the default under test -- and since
    # the instruments are rendered per revision (Task 19, review F11), SOCOM_GAME_ELF decides which
    # column env.sh exports, so a machine mid-r0004 session must not steer this r0001 test.
    for k in ("SOCOM_SERVER_IP", "PS2X_SOCOM2_SERVER", "PS2X_PEEK", "PS2X_CALL_TRACE", "SOCOM_GAME_ELF"):
        e.pop(k, None)
    e.update(env or {})
    p = subprocess.run([BASH, "-c", script], cwd=ROOT, env=e,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    assert p.returncode == 0, "bash failed (%s): %s" % (p.returncode, p.stderr)
    return p.stdout.split()


class EnvShTest(unittest.TestCase):
    def test_defaults(self):
        """A bare source gives the hosted box, by name (Sprint 13 Task H6: it was the owner's LAN address),
        and the full peek block."""
        out = run_bash(". scripts/parity/env.sh; echo $PS2X_SOCOM2_SERVER; echo ${#PS2X_PEEK}")
        self.assertEqual(out[0], HOSTED)
        self.assertEqual(int(out[1]), PEEK_LEN)

    def test_socom_server_ip_overrides(self):
        """SOCOM_SERVER_IP is the one knob that points the harness at another server."""
        out = run_bash(". scripts/parity/env.sh; echo $PS2X_SOCOM2_SERVER",
                       env={"SOCOM_SERVER_IP": "198.51.100.5"})
        self.assertEqual(out[0], "198.51.100.5")

    def test_source_twice_is_harmless(self):
        out = run_bash(". scripts/parity/env.sh; . scripts/parity/env.sh; "
                       "echo $PS2X_SOCOM2_SERVER; echo ${#PS2X_PEEK}")
        self.assertEqual(out[0], HOSTED)
        self.assertEqual(int(out[1]), PEEK_LEN)

    def test_every_online_script_sources_env_sh(self):
        """No script may carry its own PS2X_SOCOM2_SERVER default any more."""
        offenders = []
        for path in sorted(glob.glob(os.path.join(ROOT, "scripts", "parity", "*.sh"))):
            if os.path.samefile(path, ENV_SH):
                continue
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if "PS2X_SOCOM2_SERVER" not in text:
                continue
            if not re.search(r'^\s*\.\s+"\$\(dirname "\$0"\)/env\.sh"', text, re.M):
                offenders.append(os.path.relpath(path, ROOT))
        self.assertEqual(offenders, [], "these scripts set PS2X_SOCOM2_SERVER without sourcing env.sh")



class ConsoleLanesNeedAnIp(unittest.TestCase):
    """Sprint 13 Task H6 fix round 1: with the hosted NAME as env.sh's default, the console lanes -- which
    bind a LAN address and answer DNS with it -- must refuse with the sentence instead of failing inside
    netstat or a Python traceback, and no private address may stand in as a default."""

    LEGS = {"mixed_match.sh": ("SOCOM_SERVER_IP",), "mixed_match2.sh": ("LAN_IP", "SOCOM_SERVER_IP"),
            "mixed_match2_leg2.sh": ("LAN_IP",)}
    PRIVATE = re.compile(r"\b(192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)\b")

    def _require(self, env):
        e = dict(os.environ)
        for k in ("SOCOM_SERVER_IP", "LAN_IP", "SOCOM_GAME_ELF"):
            e.pop(k, None)
        e.update(env)
        return subprocess.run([BASH, "-c", ". scripts/parity/env.sh; socom_require_ipv4 LAN_IP probe"],
                              cwd=ROOT, env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)

    def test_the_requirement_refuses_unset_and_a_name_and_passes_an_ip(self):
        p = self._require({})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("set LAN_IP to the LAN IP the DNS stub serves", p.stderr)
        p = self._require({"LAN_IP": "socom.scotho.com"})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("socom.scotho.com", p.stderr)
        self.assertEqual(self._require({"LAN_IP": "203.0.113.7"}).returncode, 0)

    def test_every_leg_requires_its_ips_before_the_dns_check_and_has_no_default(self):
        for leg, names in self.LEGS.items():
            with open(os.path.join(ROOT, "scripts", "parity", leg), encoding="utf-8") as f:
                body = f.read()
            code = "".join(l for l in body.splitlines(True) if not l.lstrip().startswith("#"))
            netstat = code.index("netstat")
            for name in names:
                call = "socom_require_ipv4 %s " % name
                self.assertIn(call, code, leg)
                self.assertLess(code.index(call), netstat, "%s: %s is checked after the DNS probe" % (leg, name))
            self.assertNotIn("LAN_IP:-", code, "%s gives LAN_IP a default again" % leg)
            self.assertIsNone(self.PRIVATE.search(body), "%s carries a private address" % leg)

    def test_no_parity_script_or_the_stub_carries_a_private_address(self):
        paths = glob.glob(os.path.join(ROOT, "scripts", "parity", "*.sh"))
        paths.append(os.path.join(ROOT, "tools_py", "parity", "dns_stub.py"))
        paths.append(os.path.join(ROOT, "scripts", "parity", "pcsx2", "PCSX2.ini.dev9-section"))
        for path in paths:
            with open(path, encoding="utf-8") as f:
                self.assertIsNone(self.PRIVATE.search(f.read()), path)

    def test_the_dns_stub_refuses_a_name_and_an_unset_address(self):
        import contextlib
        import io
        from tools_py.parity import dns_stub
        self.assertIsNone(dns_stub.ipv4_problem("--answer", "203.0.113.7"))
        self.assertIn("set SOCOM_SERVER_IP to the LAN IP the DNS stub serves",
                      dns_stub.ipv4_problem("--answer", "socom.scotho.com"))
        self.assertIn("<unset>", dns_stub.ipv4_problem("--bind", None))
        self.assertIsNotNone(dns_stub.ipv4_problem("--bind", "300.1.1.1"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = dns_stub.main(["--bind", "203.0.113.7", "--answer", "socom.scotho.com", "--port", "1"])
        self.assertEqual(code, 2)
        self.assertIn("socom.scotho.com", err.getvalue())


if __name__ == "__main__":
    unittest.main()
