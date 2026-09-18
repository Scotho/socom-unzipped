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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "make_server_zip.sh")


def _run(out, env=None):
    return subprocess.run(["bash", SCRIPT, out], capture_output=True, text=True, cwd=ROOT,
                          env={**os.environ, **(env or {})})


@unittest.skipUnless(shutil.which("bash") and shutil.which("powershell"), "bash and PowerShell only")
class MakeServerZipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

    def test_refuses_without_a_built_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "server")
            os.makedirs(empty)
            r = _run(os.path.join(tmp, "out"), {"SERVER": empty})
            self.assertEqual(r.returncode, 2, r.stderr + r.stdout)
            self.assertIn("start-servers.ps1", r.stderr)


if __name__ == "__main__":
    unittest.main()
