"""Task 8b Step 5: scripts/make_portable.sh assembles the portable folder (outline section 2 A) from dist/.
Sprint 9 Goal 2: the folder carries the import closure of the two executables and nothing else, and a
SHA256SUMS sits beside the archive."""
import os
import shutil
import subprocess
import tempfile
import unittest

from tools_py import portable_audit
from tools_py.tests.binfmt_fixtures import tiny_pe

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "make_portable.sh")

FAKE_DIST = {
    "socom2.exe": tiny_pe(["KERNEL32.dll", "avcodec-61.dll", "libc++.dll"]),
    "socom_unzipped_launcher.exe": tiny_pe(["USER32.dll", "libc++.dll"]),
    "avcodec-61.dll": tiny_pe(["zlib1.dll", "KERNEL32.dll"]),
    "zlib1.dll": tiny_pe(["KERNEL32.dll"]),
    "libc++.dll": tiny_pe([]),
    "avformat-61.dll": tiny_pe(["avcodec-61.dll"]),      # in dist/, imported by nothing shipped
    "OpenEXR-3_3.dll": tiny_pe(["KERNEL32.dll"]),        # likewise
    "vu1_replay.exe": tiny_pe(["libc++.dll"]),           # a harness tool: never shipped
    "socom2_game.elf": b"x",
}


def fake_dist(tmp, without=()):
    dist = os.path.join(tmp, "dist")
    os.makedirs(dist)
    for name, data in FAKE_DIST.items():
        if name not in without:
            with open(os.path.join(dist, name), "wb") as fh:
                fh.write(data)
    return dist


@unittest.skipUnless(shutil.which("bash") and shutil.which("powershell"), "bash and PowerShell only")
class MakePortableTest(unittest.TestCase):
    def _run(self, dist, *args):
        return subprocess.run(["bash", SCRIPT] + list(args), capture_output=True, text=True, cwd=ROOT,
                              env={**os.environ, "DIST": dist})

    def test_folder_has_the_game_the_launcher_the_closure_the_readme_and_the_licences(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            r = self._run(fake_dist(tmp), out)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            pkg = os.path.join(out, "socom2")
            for f in ("socom2.exe", "socom2_game.elf", "socom_unzipped_launcher.exe", "avcodec-61.dll", "zlib1.dll",
                      "libc++.dll", "README.txt", os.path.join("LICENSES", "PS2Recomp-GPL-3.0.txt"),
                      os.path.join("LICENSES", "README.txt")):
                self.assertTrue(os.path.isfile(os.path.join(pkg, f)), f)
            for d in ("cards", "logs"):
                self.assertTrue(os.path.isdir(os.path.join(pkg, d)), d)
            self.assertIn("Run socom_unzipped_launcher.exe", open(os.path.join(pkg, "README.txt")).read())
            # Sprint 9 Goal 1: the About page and the diagnostics zip read version.txt; nothing wrote it before.
            with open(os.path.join(pkg, "version.txt")) as fh:
                self.assertRegex(fh.read(), "^SOCOM Unzipped \\S+ \\(\\d{4}-\\d{2}-\\d{2}\\)\\n$")
            self.assertTrue(os.path.isfile(os.path.join(out, "socom2-portable.zip")))

    def test_what_nothing_imports_stays_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            self.assertEqual(self._run(fake_dist(tmp), out).returncode, 0)
            pkg = os.path.join(out, "socom2")
            for f in ("avformat-61.dll", "OpenEXR-3_3.dll", "vu1_replay.exe"):
                self.assertFalse(os.path.exists(os.path.join(pkg, f)), f)
            self.assertEqual(portable_audit.audit(pkg, "Windows"),
                             {"needed": ["avcodec-61.dll", "libc++.dll", "zlib1.dll"], "missing": {}, "orphans": []})

    def test_sha256sums_sits_beside_the_zip_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            self.assertEqual(self._run(fake_dist(tmp), out).returncode, 0)
            with open(os.path.join(out, "SHA256SUMS")) as fh:
                self.assertRegex(fh.read(), "^[0-9a-f]{64}  socom2-portable\\.zip\\n$")
            self.assertEqual(portable_audit.verify_sha256sums(out), [])
            with open(os.path.join(out, "socom2-portable.zip"), "ab") as fh:
                fh.write(b"tampered")
            self.assertEqual(portable_audit.verify_sha256sums(out), ["socom2-portable.zip: checksum differs"])

    def test_an_import_that_is_nowhere_stops_the_packaging(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self._run(fake_dist(tmp, without=("zlib1.dll",)), os.path.join(tmp, "out"))
            self.assertEqual(r.returncode, 3, r.stderr + r.stdout)
            self.assertIn("zlib1.dll", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(tmp, "out", "socom2-portable.zip")))

    def test_release_flag_is_accepted_in_front_of_the_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            r = self._run(fake_dist(tmp), "--release", out)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertTrue(os.path.isfile(os.path.join(out, "socom2-portable.zip")))

    def test_refuses_without_a_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self._run(os.path.join(tmp, "nodist"), os.path.join(tmp, "out"))
            self.assertEqual(r.returncode, 2)
            self.assertIn("run ./build.sh runtime first", r.stderr)


if __name__ == "__main__":
    unittest.main()


class ReleaseConfigurationTest(unittest.TestCase):
    """Sprint 9 P7. R151 was decided on a measurement -- `-O2` made the generated code's exe 9.9% smaller
    and the ZIP 4.6 MB LARGER, so the release keeps `-O1` -- and `docs/KNOWN.md` records it as settled.
    The ruling was never applied to the script: `build.sh`'s release default was introduced as `-O2` in
    443238e and never changed, so every `./build.sh release` since has built the configuration R151
    rejected. Found when the playtest candidate came out 62.8 MB against Goal 2's recorded 55.7 MB.
    A ruling that is written down but not wired to anything is not a decision, it is a note."""

    def setUp(self):
        with open(os.path.join(ROOT, "build.sh"), encoding="utf-8") as fh:
            self.text = fh.read()

    def test_the_release_default_is_the_optimisation_r151_chose(self):
        line = [ln for ln in self.text.splitlines() if "REL_GENOPT" in ln]
        self.assertEqual(len(line), 1, "one place sets the release's generated-code optimisation")
        self.assertIn("${REL_GENOPT:--O1}", line[0],
                      "R151 measured -O2 as a LARGER download and chose -O1; the default must be what was chosen")
        self.assertNotIn(":--O2", line[0], "the rejected value is not the default")
