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
import sys
import tarfile
import tempfile
import unittest

from tools_py import portable_audit
from tools_py.tests.binfmt_fixtures import tiny_elf
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


FAKE_LDIST = {
    "socom2": tiny_elf(["libavcodec.so.61", "libc.so.6", "libstdc++.so.6"]),
    "socom_unzipped_launcher": tiny_elf(["libzenity_helper.so.1", "libc.so.6"]),
    "socom2_game.elf": b"x",
}
FAKE_LIBS = {
    "libavcodec.so.61": tiny_elf(["libvpx.so.9", "libc.so.6"]),
    "libvpx.so.9": tiny_elf(["libc.so.6"]),
    "libzenity_helper.so.1": tiny_elf([]),
    "libXau.so.6": tiny_elf([]),          # what only the host's libxcb needs: ldd lists it, nothing shipped reaches it
}


def fake_ldist(tmp, missing=()):
    """A dist-linux/ of tiny ELFs, a libs/ they resolve to, and an `ldd` that answers for them the way the
    real one does (one flat list, host libraries and all); `missing` names come back as 'not found'."""
    ldist = os.path.join(tmp, "dist-linux")
    libs = os.path.join(tmp, "libs")
    os.makedirs(ldist)
    os.makedirs(libs)
    for name, data in FAKE_LDIST.items():
        with open(os.path.join(ldist, name), "wb") as fh:
            fh.write(data)
    for name, data in FAKE_LIBS.items():
        with open(os.path.join(libs, name), "wb") as fh:
            fh.write(data)
    lines = ["\tlinux-vdso.so.1 (0x00007ffd)"]
    for name in FAKE_LIBS:
        lines.append("\t%s => not found" % name if name in missing else
                     "\t%s => %s (0x0)" % (name, os.path.join(libs, name).replace("\\", "/")))
    for name in missing:
        if name not in FAKE_LIBS:
            lines.append("\t%s => not found" % name)
    lines += ["\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x0)",
              "\tlibstdc++.so.6 => /lib/x86_64-linux-gnu/libstdc++.so.6 (0x0)",
              "\t/lib64/ld-linux-x86-64.so.2 (0x0)"]
    ldd = os.path.join(tmp, "ldd")
    with open(ldd, "w", newline="\n") as fh:
        fh.write("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" >/dev/null\ncat <<'LDD'\n" + "\n".join(lines) + "\nLDD\n")
    os.chmod(ldd, 0o755)
    return ldist, ldd


@unittest.skipUnless(BASH, "bash only")
class MakePortableLinuxSyntheticTest(unittest.TestCase):
    """Sprint 10 Q7 item 2: the Linux branch on any host. MakePortableLinuxTest above needs Linux and a built
    launcher, so on the Windows host -- where nearly every suite run happens -- the branch that writes the
    Linux tarball's version.txt was never exercised (KNOWN: 'the Linux packaging branch's version.txt has no
    test'). The script takes its platform from MAKE_PORTABLE_SYSTEM, its ldd from LDD and its interpreter
    from PYTHON -- scripts/python_env.sh's one rule, which used to be two here -- so a synthetic
    dist-linux/ of tiny ELFs and an ldd that answers for them drive the whole branch: the executable bits,
    lib/ from the closure walk, version.txt, the tarball, SHA256SUMS and the audit."""

    def _run(self, tmp, ldist, ldd, *args):
        env = {**os.environ, "MAKE_PORTABLE_SYSTEM": "Linux", "LDD": ldd, "PYTHON": sys.executable,
               "LDIST": ldist, "DIST": os.path.join(tmp, "nodist")}
        return subprocess.run([BASH, SCRIPT] + list(args), capture_output=True, text=True, cwd=ROOT, env=env)

    def test_the_tarball_carries_a_version_the_binaries_and_the_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            ldist, ldd = fake_ldist(tmp)
            out = os.path.join(tmp, "out")
            r = self._run(tmp, ldist, ldd, out)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            pkg = os.path.join(out, "socom2-linux")
            with open(os.path.join(pkg, "version.txt")) as fh:
                self.assertRegex(fh.read(), "^SOCOM Unzipped \\S+ \\(\\d{4}-\\d{2}-\\d{2}\\)\\n$")
            for f in ("socom2", "socom2_game.elf", "socom_unzipped_launcher", "README.txt", "THIRD_PARTY_NOTICES.md",
                      os.path.join("LICENSES", "GPL-3.0-only.txt"), os.path.join("lib", "libavcodec.so.61"),
                      os.path.join("lib", "libvpx.so.9"), os.path.join("lib", "libzenity_helper.so.1")):
                self.assertTrue(os.path.isfile(os.path.join(pkg, f)), f)
            self.assertFalse(os.path.exists(os.path.join(pkg, "lib", "libXau.so.6")), "a host-only library was carried")
            self.assertEqual(sorted(os.listdir(os.path.join(pkg, "lib"))),
                             ["libavcodec.so.61", "libvpx.so.9", "libzenity_helper.so.1"])
            self.assertIn("./socom_unzipped_launcher", open(os.path.join(pkg, "README.txt")).read())
            tarball = os.path.join(out, "socom2-linux.tar.gz")
            with tarfile.open(tarball) as tar:
                names = tar.getnames()
                self.assertIn("socom2-linux/version.txt", names)
                self.assertIn("socom2-linux/lib/libvpx.so.9", names)
                if platform.system() == "Linux":      # MSYS's chmod +x does not reach NTFS; MakePortableLinuxTest too
                    self.assertTrue(tar.getmember("socom2-linux/socom2").mode & 0o100, "socom2 lost its executable bit")
            with open(tarball, "rb") as fh:
                want = hashlib.sha256(fh.read()).hexdigest()
            with open(os.path.join(out, "SHA256SUMS")) as fh:
                self.assertEqual(fh.read(), "%s  socom2-linux.tar.gz\n" % want)
            self.assertEqual(portable_audit.audit(pkg, "Linux")["orphans"], [])

    def test_a_library_ldd_cannot_resolve_stops_the_packaging(self):
        with tempfile.TemporaryDirectory() as tmp:
            ldist, ldd = fake_ldist(tmp, missing=("libvpx.so.9",))
            r = self._run(tmp, ldist, ldd, os.path.join(tmp, "out"))
            self.assertEqual(r.returncode, 3, r.stderr + r.stdout)
            self.assertIn("libvpx.so.9", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(tmp, "out", "socom2-linux.tar.gz")))

    def test_refuses_without_a_linux_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, ldd = fake_ldist(tmp)
            r = self._run(tmp, os.path.join(tmp, "empty"), ldd, os.path.join(tmp, "out"))
            self.assertEqual(r.returncode, 2, r.stderr + r.stdout)
            self.assertIn("scripts/build_linux.sh", r.stderr)


if __name__ == "__main__":
    unittest.main()
