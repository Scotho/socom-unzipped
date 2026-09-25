"""Sprint 7 Task 4 Step 1: scripts/make_server_zip.sh packages server/ for the hosted machine.

Modelled on test_make_portable.py. One real packaging run is shared by the tests that inspect
the zip (setUpClass), because the run copies the whole horizon-server tree; the refusal test
points SERVER at an empty tree of its own, the way the portable test points DIST at one.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "make_server_zip.sh")
# What the script packages: the built .NET server. A fresh clone and the Windows CI runner have not built it
# (Sprint 10 H3's fresh-clone trial found these two tests failing there), so the packaging run is skipped, not
# failed, where it is absent -- the refusal test below still runs, because it needs no build.
SERVER_EXE = os.path.join(ROOT, "server", "horizon-server", "Server.Unified.Launcher", "bin", "Release", "net9.0",
                          "Server.Unified.Launcher.exe")


def _run(out, env=None):
    return subprocess.run([BASH, SCRIPT, out], capture_output=True, text=True, cwd=ROOT,
                          env={**os.environ, **(env or {})})


@unittest.skipUnless(BASH and shutil.which("powershell"), "bash and PowerShell only")
class MakeServerZipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(SERVER_EXE):
            raise unittest.SkipTest("the .NET server is not built here (server/start-servers.ps1 -Build)")
        cls.tmp = tempfile.mkdtemp()
        cls.result = _run(os.path.join(cls.tmp, "out"))
        zip_path = os.path.join(cls.tmp, "out", "socom-unzipped-server.zip")
        cls.names = zipfile.ZipFile(zip_path).namelist() if os.path.isfile(zip_path) else []

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_the_zip_carries_the_server_and_its_readme(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr + self.result.stdout)
        for tail in ("start-servers.ps1", "seed-simulated-db.ps1", "README.md",
                     "Server.Medius.exe", "medius.json"):
            self.assertTrue(any(n.endswith(tail) for n in self.names), (tail, self.names[:20]))
        for d in ("dme-plugins", "medius-plugins", "config"):
            self.assertTrue(any("/%s/" % d in n or n.endswith("/%s/" % d) for n in self.names),
                            (d, self.names[:20]))
        pkg = os.path.join(self.tmp, "out", "socom-unzipped-server")
        with open(os.path.join(pkg, "config", "README.txt")) as fh:
            self.assertIn("seed-simulated-db.ps1", fh.read())

    def test_the_simulated_db_is_never_shipped(self):
        self.assertTrue(self.names, "no zip was produced: " + self.result.stderr)
        self.assertFalse(any(n.endswith("simulated.db") for n in self.names),
                         "a seeded database must not ship")


@unittest.skipUnless(BASH and shutil.which("powershell"), "bash and PowerShell only")
class MakeServerZipRefusalTest(unittest.TestCase):
    """Needs no built server, so it runs on a fresh clone too."""

    def test_refuses_without_a_built_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "server")
            os.makedirs(empty)
            r = _run(os.path.join(tmp, "out"), {"SERVER": empty})
            self.assertEqual(r.returncode, 2, r.stderr + r.stdout)
            self.assertIn("start-servers.ps1", r.stderr)


@unittest.skipUnless(BASH and shutil.which("powershell"), "bash and PowerShell only")
class MakeServerZipBuildIdTest(unittest.TestCase):
    """Sprint 13 Task O3: the package says which commit it is (BUILD_ID, served as the stats JSON's "build") and
    carries the box scripts but never their ops.env. A stand-in server tree -- empty files where the binaries go --
    so it runs on a fresh clone too."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server = os.path.join(self.tmp, "server")
        for rel in ("start-servers.ps1", "seed-simulated-db.ps1", "README.md", "linux/install.sh",
                    "config/medius.json", "ops/backup.sh", "ops/health.sh", "ops/backup.cron",
                    "ops/ops.env.example", "ops/ops.env"):
            path = os.path.join(self.server, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                fh.write("{}\n" if rel.endswith(".json") else "x\n")
        for p in ("Server.Unified.Launcher", "Server.NAT", "Server.UniverseInformation", "Server.Medius", "Server.Dme"):
            d = os.path.join(self.server, "horizon-server", p, "bin", "Release", "net9.0")
            os.makedirs(d)
            open(os.path.join(d, p + ".exe"), "w").close()
        self.pkg = os.path.join(self.tmp, "out", "socom-unzipped-server")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _build_id(self):
        with open(os.path.join(self.pkg, "BUILD_ID")) as fh:
            return fh.read()

    def test_the_override_is_written(self):
        r = _run(os.path.join(self.tmp, "out"), {"SERVER": self.server, "SERVER_BUILD_ID": "0123456789ab"})
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self._build_id(), "0123456789ab\n")

    def test_the_repository_commit_is_the_default(self):
        env = {k: v for k, v in os.environ.items() if k != "SERVER_BUILD_ID"}
        r = subprocess.run([BASH, SCRIPT, os.path.join(self.tmp, "out")], capture_output=True, text=True, cwd=ROOT,
                           env={**env, "SERVER": self.server})
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        head = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True,
                              cwd=ROOT, check=True).stdout.strip()
        # the stand-in tree is not this checkout's server/, so the id says it came from a copy
        self.assertRegex(self._build_id(), r"^%s(-dirty)?-copy\n$" % head)

    def test_the_box_scripts_ship_and_their_env_file_does_not(self):
        r = _run(os.path.join(self.tmp, "out"), {"SERVER": self.server, "SERVER_BUILD_ID": "x"})
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        shipped = sorted(os.listdir(os.path.join(self.pkg, "ops")))
        self.assertEqual(shipped, ["backup.cron", "backup.sh", "health.sh", "ops.env.example"])
        names = zipfile.ZipFile(os.path.join(self.tmp, "out", "socom-unzipped-server.zip")).namelist()
        self.assertFalse(any(n.endswith("ops.env") for n in names), "ops.env must never ship")


if __name__ == "__main__":
    unittest.main()
