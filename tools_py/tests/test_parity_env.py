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
                       env={"SOCOM_SERVER_IP": "10.0.0.5"})
        self.assertEqual(out[0], "10.0.0.5")

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


if __name__ == "__main__":
    unittest.main()
