"""Issue #38: every capture that produces evidence writes the PS2X_* environment it ran with beside its output.

docs/HAZARDS.md harness, "A capture that does not record its own environment cannot prove the 'off' half of an A/B": the W6
A/B (2026-09-23, `logs/parity/mission_music_ours_20260922_224425` against `logs/parity/w6_norevalidate`) took two
mission captures, one with `PS2X_GS_NO_TEX_REVALIDATE=1`, and neither run directory could say which was which. The
closing bar: a test that runs one capture entry point dry and finds the file, in the gate's pin format.

The entry point is the one the W6 A/B used, `scripts/parity/mission_music_long.sh`, whose `--dry-run` writes the
generated drive script and stops before any launch (no lock, no game). The two halves of an A/B, run dry, must be
told apart from their artefacts alone -- that is the whole point of the record.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tools_py.parity import capture_env, pins
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PARITY = os.path.join(ROOT, "scripts", "parity")
LONG_SH = os.path.join(PARITY, "mission_music_long.sh")
KNOB = "PS2X_GS_NO_TEX_REVALIDATE"
# A script that launches the game itself: a drive, or one of the online drivers, run as a module.
LAUNCH_RE = re.compile(r"-m\s+tools_py\.parity\.(drive|online_match_ours|online_login_ours)\b")
PY_PARITY = os.path.join(ROOT, "tools_py", "parity")
# A Python module that starts the game: drive.py as a subprocess, run.sh, or the exe and the image directly.
PY_LAUNCH_RE = re.compile(r"\"tools_py\.parity\.drive\"|\"\./run\.sh\"|Popen\(\[exe, elf\]")
# The drivers (covered by the record their launcher wrote) and the gate (which pins its own environment).
# online_match_ours.py launches through online_login_ours.launch, so it is not matched here in its own right.
PY_EXEMPT = ("drive.py", "online_login_ours.py", "gate.py")


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PS2X_")}
    env.update(extra)
    return env


class TheWriter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_the_pin_is_the_gates_env_pin_byte_for_byte(self):
        env = {"PS2X_DEV": "1", KNOB: "1", "PS2X_MC_DIR": "C:/cards/x", "PATH": "/usr/bin"}
        pin = capture_env.write(self.tmp, env=env)
        self.assertEqual(pin.sha256, pins.env_pin(env).sha256)
        record = pins.load_record(os.path.join(self.tmp, capture_env.RECORD_NAME))
        self.assertEqual(record["env"].sha256, pins.env_pin(env).sha256, "pins.load_record reads the record")
        with open(os.path.join(self.tmp, capture_env.TEXT_NAME), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("%s=1\n" % KNOB, text)
        self.assertIn("PS2X_MC_DIR=C:/cards/x\n", text, "the card path is written for the reader ...")
        self.assertNotIn("PS2X_MC_DIR", " ".join(record["env"].detail), "... and left out of the pin, as the gate's")
        self.assertIn("PIN env sha256=%s recorded; PS2X_DEV=1 %s=1\n" % (pin.sha256, KNOB), text)
        self.assertNotIn("PATH=", text)

    def test_the_executable_is_hashed_into_the_record(self):
        exe = os.path.join(self.tmp, "socom2.exe")
        with open(exe, "wb") as f:
            f.write(b"MZ\0stand-in")
        capture_env.write(self.tmp, env={}, exe=exe)
        with open(os.path.join(self.tmp, capture_env.TEXT_NAME), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("# no PS2X_* in the environment\n", text)
        self.assertIn("SOCOM_EXE_SHA256=%s\n" % pins.file_sha256(exe), text)
        with open(os.path.join(self.tmp, capture_env.RECORD_NAME), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["exe"], "EXE " + exe)


@unittest.skipUnless(BASH, "bash not found")
class TheMissionCaptureRunDry(unittest.TestCase):
    STAMP = "test_s13_h3_capture_env_dryrun"

    def tearDown(self):
        shutil.rmtree(os.path.join(ROOT, "logs", "parity", self.STAMP), ignore_errors=True)

    def dry_run(self, env):
        shutil.rmtree(os.path.join(ROOT, "logs", "parity", self.STAMP), ignore_errors=True)
        p = subprocess.run([BASH, LONG_SH, "--dry-run", "--walk", "--minutes", "1", "--stamp", self.STAMP],
                           cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        out = os.path.join(ROOT, "logs", "parity", self.STAMP)
        self.assertTrue(os.path.isfile(os.path.join(out, capture_env.TEXT_NAME)),
                        "no %s beside the capture: %s" % (capture_env.TEXT_NAME, sorted(os.listdir(out))))
        with open(os.path.join(out, capture_env.TEXT_NAME), encoding="utf-8") as f:
            text = f.read()
        return text, pins.load_record(os.path.join(out, capture_env.RECORD_NAME))

    def test_the_dry_run_writes_the_environment_beside_the_capture(self):
        text, record = self.dry_run(clean_env(**{KNOB: "1"}))
        self.assertIn("%s=1\n" % KNOB, text)
        self.assertIsNotNone(record, "env_pins.json, the gate's record format, is written too")
        self.assertIn("%s=1" % KNOB, record["env"].detail)

    def test_the_two_halves_of_an_ab_are_told_apart_from_their_artefacts(self):
        on_text, on = self.dry_run(clean_env(**{KNOB: "1"}))
        off_text, off = self.dry_run(clean_env())
        self.assertNotIn(KNOB, off_text)
        self.assertNotEqual(on["env"].sha256, off["env"].sha256)
        self.assertEqual([d.name for d in pins.compare(on, {"env": off["env"].sha256})], ["env"])


class EveryLaunchingScriptWritesIt(unittest.TestCase):
    """The rule, derived rather than listed: a script under scripts/parity/ that launches the game itself (a
    drive, or an online driver run as a module) sources write_env.sh and calls write_env_ps2x. A wrapper that
    launches through one of those (capture_audio_out.sh, endpoint_ab.sh, the queues) inherits the record."""

    def test_each_launcher_calls_the_shared_writer(self):
        launchers, missing = [], []
        for name in sorted(os.listdir(PARITY)):
            if not name.endswith(".sh"):
                continue
            with open(os.path.join(PARITY, name), encoding="utf-8") as f:
                text = f.read()
            if not LAUNCH_RE.search(text):
                continue
            launchers.append(name)
            if "write_env.sh" not in text or not re.search(r"^\s*write_env_ps2x\s", text, re.M):
                missing.append(name)
        self.assertIn("audio_parity.sh", launchers, "the derivation found the launchers")
        self.assertEqual(missing, [], "these launch a game and record no environment")

    def test_each_python_launcher_calls_the_writer_or_is_named_exempt(self):
        """The same rule for tools_py/parity: a module that starts the game (drive.py as a subprocess, run.sh,
        or the exe itself) calls capture_env.write, or is one of the exemptions capture_env's docstring names
        and argues -- the drivers, covered by their callers' records, and the gate, which pins its own."""
        launchers, missing = [], []
        for name in sorted(os.listdir(PY_PARITY)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(PY_PARITY, name), encoding="utf-8") as f:
                text = f.read()
            if not PY_LAUNCH_RE.search(text):
                continue
            launchers.append(name)
            if name not in PY_EXEMPT and "capture_env.write(" not in text:
                missing.append(name)
        self.assertEqual(missing, [], "these launch a game and record no environment")
        self.assertEqual(sorted(n for n in PY_EXEMPT if n not in launchers), [],
                         "an exemption for a module that no longer launches anything is stale")
        for name in ("sp_death_probe.py", "scale_shot.py"):
            self.assertIn(name, launchers, "the derivation found the launchers")
        with open(os.path.join(PY_PARITY, "capture_env.py"), encoding="utf-8") as f:
            doc = f.read()
        for name in PY_EXEMPT:
            self.assertIn(name, doc, "capture_env's docstring argues each exemption")


if __name__ == "__main__":
    unittest.main()
