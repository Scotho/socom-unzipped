"""Sprint 9 Goal 2: the Linux branch of scripts/make_portable.sh, run for real. test_make_portable.py needs
PowerShell and has never run on Linux, so until now nothing checked this branch's version.txt (Goal 1, R138)
or anything else about it. CI builds the launcher and no runner; the launcher stands in for both binaries
(the script asks only that the three files exist), which is enough for ldd, lib/, the tarball, version.txt,
SHA256SUMS and the audit to be exercised on ubuntu-24.04."""
import hashlib
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from tools_py import portable_audit
from tools_py.tests.shell import BASH

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "make_portable.sh")
LAUNCHER = os.path.join(ROOT, "dist-linux", "socom_unzipped_launcher")


@unittest.skipUnless(platform.system() == "Linux" and os.path.isfile(LAUNCHER) and shutil.which("ldd")
                     and BASH, "Linux with a built launcher (dist-linux/) only")
class MakePortableLinuxTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = self._tmp.name
        self.ldist = os.path.join(tmp, "ldist")
        os.makedirs(self.ldist)
        shutil.copy2(LAUNCHER, os.path.join(self.ldist, "socom_unzipped_launcher"))
        shutil.copy2(LAUNCHER, os.path.join(self.ldist, "socom2"))
        with open(os.path.join(self.ldist, "socom2_game.elf"), "wb") as fh:
            fh.write(b"x")
        self.out = os.path.join(tmp, "out")
        self.result = subprocess.run([BASH, SCRIPT, self.out], capture_output=True, text=True, cwd=ROOT,
                                     env={**os.environ, "LDIST": self.ldist, "DIST": os.path.join(tmp, "nodist")})
        self.pkg = os.path.join(self.out, "socom2-linux")
        self.tarball = os.path.join(self.out, "socom2-linux.tar.gz")

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_tarball_unpacks_runnable_with_a_version(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr + self.result.stdout)
        with open(os.path.join(self.pkg, "version.txt")) as fh:
            self.assertRegex(fh.read(), "^SOCOM Unzipped \\S+ \\(\\d{4}-\\d{2}-\\d{2}\\)\\n$")
        with tarfile.open(self.tarball) as tar:
            names = tar.getnames()
            self.assertIn("socom2-linux/version.txt", names)
            self.assertTrue(tar.getmember("socom2-linux/socom2").mode & 0o100, "socom2 lost its executable bit")

    def test_sha256sums_sits_beside_the_tarball_and_verifies(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr + self.result.stdout)
        with open(self.tarball, "rb") as fh:
            want = hashlib.sha256(fh.read()).hexdigest()
        with open(os.path.join(self.out, "SHA256SUMS")) as fh:
            self.assertEqual(fh.read(), "%s  socom2-linux.tar.gz\n" % want)
        self.assertEqual(portable_audit.verify_sha256sums(self.out), [])
        if shutil.which("sha256sum"):
            check = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=self.out, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_lib_holds_what_the_binaries_need_and_nothing_else(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr + self.result.stdout)
        found = portable_audit.audit(self.pkg, "Linux")
        self.assertEqual((found["missing"], found["orphans"]), ({}, []))
        shutil.copy2(LAUNCHER, os.path.join(self.pkg, "lib", "libnothing_needs_me.so.1"))
        self.assertEqual(portable_audit.audit(self.pkg, "Linux")["orphans"], ["libnothing_needs_me.so.1"])


if __name__ == "__main__":
    unittest.main()
