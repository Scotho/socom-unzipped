"""Sprint 9 Goal 1: a test per exit code that drives the failing condition on the real runner and asserts
the code and the sentence. Every case stops before a window opens (Preflight and BareRun run in front of
PS2Runtime::initialize), so this is a handful of sub-second processes, not a launch -- but it obeys the quiet
gate like every other suite. Skipped where there is no runner build (CI builds --no-runner)."""
import glob
import json
import os
import struct
import subprocess
import tempfile
import unittest

from tools_py import exit_codes
from tools_py.parity import hostplatform

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXE = os.path.join(ROOT, hostplatform.runtime_exe())


def _both(value):
    return struct.pack("<I", value) + struct.pack(">I", value)


def _record(extent, size, name, flags):
    length = (33 + len(name) + 1) & ~1
    rec = bytearray(length)
    rec[0] = length
    rec[2:10] = _both(extent)
    rec[10:18] = _both(size)
    rec[25] = flags
    rec[32] = len(name)
    rec[33:33 + len(name)] = name
    return bytes(rec)


def iso_with(name):
    """A 20-sector ISO 9660 image whose root directory holds one 5-byte file called `name` (bytes)."""
    img = bytearray(20 * 2048)
    pvd = 16 * 2048
    img[pvd] = 1
    img[pvd + 1:pvd + 6] = b"CD001"
    img[pvd + 156:pvd + 156 + 34] = _record(18, 2048, b"\x00", 2)
    body = _record(18, 2048, b"\x00", 2) + _record(18, 2048, b"\x01", 2) + _record(19, 5, name, 0)
    img[18 * 2048:18 * 2048 + len(body)] = body
    img[19 * 2048:19 * 2048 + 5] = b"hello"
    return bytes(img)


@unittest.skipUnless(os.path.isfile(EXE), "no runner build at " + EXE)
class RunnerExitCodeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # outer/home: "one folder up" from the ELF is ours too, so a stray .iso in %TEMP% cannot be found.
        self.home = os.path.join(self._tmp.name, "outer", "home")
        os.makedirs(self.home)
        # The developer's PS2X_* must not leak in: in a bare run the environment wins over config.json.
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("PS2X_")}

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, data):
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(os.path.join(self.home, name), mode) as fh:
            fh.write(data)

    def _run(self, *args):
        return subprocess.run([EXE, *args], capture_output=True, text=True, errors="replace",
                              timeout=60, env=self.env, cwd=self.home)

    def _log(self):
        logs = sorted(glob.glob(os.path.join(self.home, "logs", "run_*.log")))
        self.assertTrue(logs, "the bare run writes logs/run_<stamp>.log")
        with open(logs[-1], "r", errors="replace") as fh:
            return fh.read()

    def _assert_code(self, result, name):
        row = next(r for r in exit_codes.table() if r["name"] == name)
        self.assertEqual(exit_codes.classify(result.returncode), row["code"], result.stdout + result.stderr)
        line = "exit %d %s: %s" % (row["code"], row["slug"], row["sentence"])
        self.assertIn(line, self._log())

    def test_68_no_game_elf_beside_the_runner(self):
        self._assert_code(self._run("--home", self.home), "ElfMissing")

    def test_69_config_json_that_cannot_be_read(self):
        self._write("socom2_game.elf", "elf")
        self._write("config.json", '{ "isoPath": ')
        self._assert_code(self._run("--home", self.home), "ConfigUnreadable")

    def test_72_memory_card_folder_that_cannot_be_written(self):
        self._write("socom2_game.elf", "elf")
        self._write("cards", "a file where the cards folder should be")
        self._assert_code(self._run("--home", self.home), "CardDirUnwritable")

    def test_66_no_disc_anywhere(self):
        self._write("socom2_game.elf", "elf")
        self._assert_code(self._run("--home", self.home), "DiscNotFound")

    def test_66_the_configured_disc_is_gone(self):
        self._write("socom2_game.elf", "elf")
        self._write("config.json", json.dumps({"isoPath": os.path.join(self.home, "gone.iso")}))
        self._assert_code(self._run("--home", self.home), "DiscNotFound")

    def test_67_a_disc_that_is_not_r0001(self):
        self._write("socom2_game.elf", "elf")
        self._write("other.iso", iso_with(b"SCUS_972.75;1"))   # SCUS_972.75 is "hello": not the pinned digest
        self._write("config.json", json.dumps({"isoPath": os.path.join(self.home, "other.iso")}))
        self._assert_code(self._run("--home", self.home), "DiscNotR0001")

    def test_70_a_crash_is_classified_from_the_native_status(self):
        result = self._run("--fail-test", "crash")
        self.assertEqual(exit_codes.classify(result.returncode), exit_codes.code("Crashed"), result.returncode)
        self.assertEqual(exit_codes.describe(result.returncode), exit_codes.sentence(70))

    def test_71_out_of_memory(self):
        result = self._run("--fail-test", "oom")
        self.assertEqual(result.returncode, exit_codes.code("OutOfMemory"), result.stdout + result.stderr)
        self.assertIn("[oom] exit 71 out-of-memory: " + exit_codes.sentence(71), result.stderr)


if __name__ == "__main__":
    unittest.main()
