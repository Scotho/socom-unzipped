"""Sprint 9 Goal 1: the launcher's diagnostics zip, written by the real launcher and opened by Python's
zipfile -- an independent reader for ps2x/zip_store.h -- and searched for anything a stranger should not
be handing over. Runs wherever the launcher is built, CI included (--diagnostics opens no window)."""
import json
import os
import subprocess
import tempfile
import unittest
import zipfile

from tools_py.parity import hostplatform

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAUNCHER = os.path.join(ROOT, os.path.dirname(hostplatform.runtime_exe()),
                        hostplatform.exe_name("socom_unzipped_launcher"))

LOG = "\n".join([
    "INFO:     > Renderer: Test Renderer",
    "[gs-gl] initialised: 3.3.0 Test",
    "[socom2] CD image: {home}/Games/socom2.iso",
    "[crash] code=0xc0000005 host=0x1 module+0x1 access=read at 0x10",
    "",
])


@unittest.skipUnless(os.path.isfile(LAUNCHER), "no launcher build at " + LAUNCHER)
class DiagnosticsZipTest(unittest.TestCase):
    def test_the_zip_opens_holds_the_five_files_and_no_credential(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = os.path.join(tmp, "Users", "secretuser")
            game = os.path.join(tmp, "game")
            os.makedirs(os.path.join(game, "logs"))
            os.makedirs(fake_home)
            with open(os.path.join(game, "config.json"), "w") as fh:
                json.dump({"isoPath": os.path.join(fake_home, "Games", "socom2.iso"), "gsScale": 2,
                           "password": "hunter2", "token": "abc123token", "profile": "viper"}, fh)
            with open(os.path.join(game, "logs", "run_20200101_000000.log"), "w") as fh:
                fh.write("an older run\n")
            with open(os.path.join(game, "logs", "run_20260101_000000.log"), "w") as fh:
                fh.write(LOG.format(home=fake_home))
            with open(os.path.join(game, "version.txt"), "w") as fh:
                fh.write("SOCOM Unzipped test (2026-01-01)\n")
            out = os.path.join(tmp, "out.zip")
            env = {**os.environ, "USERPROFILE": fake_home, "HOME": fake_home}
            r = subprocess.run([LAUNCHER, "--diagnostics", out, game], capture_output=True, text=True,
                               timeout=20, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with zipfile.ZipFile(out) as z:
                self.assertIsNone(z.testzip())   # every CRC-32 checks out under an independent reader
                names = sorted(z.namelist())
                self.assertEqual(names, ["config.json", "crash.txt", "gl_caps.txt",
                                         "log/run_20260101_000000.log", "versions.txt"])
                for info in z.infolist():
                    self.assertEqual(info.compress_type, zipfile.ZIP_STORED, info.filename)
                blob = b"".join(z.read(n) for n in names)
                config = json.loads(z.read("config.json"))
                versions = z.read("versions.txt").decode()
                crash = z.read("crash.txt").decode()
            for secret in (b"hunter2", b"abc123token", b"password", b"secretuser"):
                self.assertNotIn(secret, blob)
            self.assertEqual(config["isoPath"], "socom2.iso")
            self.assertEqual(config["gsScale"], 2)
            self.assertNotIn("password", config)
            self.assertIn("launcher: SOCOM Unzipped test (2026-01-01)", versions)
            self.assertTrue(crash.startswith("[crash] code=0xc0000005"))


if __name__ == "__main__":
    unittest.main()
