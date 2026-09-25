"""Sprint 13 C3 -- scripts/parity/control_round_udp_shift.sh, textually (a run launches three games).

It sources env.sh (the hosted server; V6's pair went to loopback without it) and write_env.sh, sets the round's two
knobs, runs the two-instance driver with --prefilled against instance B's shift (which the driver's own INSTANCES
table carries, so the script must not need to), boots the r0004 image with the shift and without r0001's instruments,
writes under logs/parity/, never takes the lock, and ends in the readout and a done marker."""
import os
import re
import unittest

from tools_py.parity import online_login_ours as L

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "parity", "control_round_udp_shift.sh")


def code_lines(src):
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


class UdpShiftScript(unittest.TestCase):
    def setUp(self):
        with open(SCRIPT, encoding="utf-8") as f:
            self.src = f.read()
        self.code = code_lines(self.src)

    def test_sources_env_and_the_environment_writer(self):
        self.assertRegex(self.code, r'(?m)^\. "\$\(dirname "\$0"\)/env\.sh"$')
        self.assertRegex(self.code, r'(?m)^\. "\$\(dirname "\$0"\)/write_env\.sh"')
        self.assertRegex(self.code, r'(?m)^write_env_ps2x "\$OUT"')

    def test_sets_the_rounds_knobs(self):
        self.assertRegex(self.code, r"(?m)^export PS2X_SOCOM2_RSA_KEY_B=b\b")
        self.assertRegex(self.code, r"(?m)^export PS2X_SOCOM2_NET_TRACE=1\b")

    def test_instance_b_carries_the_shift_through_the_driver(self):
        """The premise: the two-instance driver gives B the shift and reads the key variable for it."""
        self.assertEqual(L.INSTANCES["B"]["PS2X_SOCOM2_UDP_SHIFT"], "2")
        self.assertNotIn("PS2X_SOCOM2_UDP_SHIFT", L.INSTANCES["A"])
        self.assertIn("PS2X_SOCOM2_RSA_KEY_B", open(L.__file__, encoding="utf-8").read())

    def test_the_driver_runs_prefilled_with_the_existing_persona(self):
        args = re.findall(r"ARGS=\(([^)]*)\)", self.code)
        self.assertEqual(len(args), 2, "the control round and --lobby-only")
        for a in args:
            self.assertIn("--prefilled", a)
            self.assertIn("--existing-b", a)
            self.assertIn('--out "$OUT"', a)
        self.assertIn("--control-round --rounds 1", args[1].replace("\n", " "))
        self.assertIn('-m tools_py.parity.online_match_ours "${ARGS[@]}"', self.code)

    def test_the_r0004_boot_has_the_shift_and_no_r0001_instruments(self):
        block = self.code[self.code.index("R0004_ELF=") :self.code.index("# 2.")] if "# 2." in self.code else \
            self.src[self.src.index("R0004_ELF=") :self.src.index("# 2. The two-instance round.")]
        self.assertIn("unset PS2X_PEEK PS2X_CALL_TRACE", block)
        self.assertIn("PS2X_SOCOM2_UDP_SHIFT=2", block)
        self.assertIn('SOCOM_GAME_ELF="$R0004_ELF"', block)
        self.assertIn('SOCOM_EXE="$R0004_EXE"', block)
        self.assertIn("bash ./run.sh", block)
        self.assertIn("R0004_LOG=", block)

    def test_never_takes_the_lock_and_writes_under_logs_parity(self):
        self.assertNotRegex(self.code, r"loop_lock\.sh|run_detached\.sh")
        self.assertIn("logs/parity/s13_c3_udp_shift_", self.code)
        self.assertIn('> "logs/${NAME}.done"', self.code)

    def test_records_the_logs_and_reads_the_verdict(self):
        for key in ("A_LOG=", "B_LOG=", "DRIVE=", "R0004_LOG=", "SERVER="):
            self.assertIn('note "%s' % key, self.code)
        self.assertIn("-m tools_py.parity.control_round_readout udp-shift", self.code)
        self.assertIn('"$OUT/VERDICT.txt"', self.code)

    def test_names_where_the_dme_record_is_read(self):
        self.assertIn("server-dme.log", self.src)


if __name__ == "__main__":
    unittest.main()
