"""Task 8b Step 5: scripts/make_portable.sh assembles the portable folder (outline section 2 A) from dist/."""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@unittest.skipUnless(shutil.which("bash") and shutil.which("powershell"), "bash and PowerShell only")
class MakePortableTest(unittest.TestCase):
    def test_folder_has_the_game_the_launcher_the_dlls_the_readme_and_the_licences(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = os.path.join(tmp, "dist")
            os.makedirs(dist)
            for f in ("socom2.exe", "socom2_game.elf", "socom_unzipped_launcher.exe", "raylib.dll", "avcodec-61.dll"):
                with open(os.path.join(dist, f), "wb") as fh:
                    fh.write(b"x")
            out = os.path.join(tmp, "out")
            r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "make_portable.sh"), out],
                               capture_output=True, text=True, cwd=ROOT, env={**os.environ, "DIST": dist})
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            pkg = os.path.join(out, "socom2")
            for f in ("socom2.exe", "socom2_game.elf", "socom_unzipped_launcher.exe", "raylib.dll", "avcodec-61.dll",
                      "README.txt", os.path.join("LICENSES", "PS2Recomp-GPL-3.0.txt"), os.path.join("LICENSES", "README.txt")):
                self.assertTrue(os.path.isfile(os.path.join(pkg, f)), f)
            for d in ("cards", "logs"):
                self.assertTrue(os.path.isdir(os.path.join(pkg, d)), d)
            self.assertIn("Run socom_unzipped_launcher.exe", open(os.path.join(pkg, "README.txt")).read())
            # Sprint 9 Goal 1: the About page and the diagnostics zip read version.txt; nothing wrote it before.
            with open(os.path.join(pkg, "version.txt")) as fh:
                self.assertRegex(fh.read(), "^SOCOM Unzipped \\S+ \\(\\d{4}-\\d{2}-\\d{2}\\)\\n$")
            self.assertTrue(os.path.isfile(os.path.join(out, "socom2-portable.zip")))

    def test_refuses_without_a_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "make_portable.sh"), os.path.join(tmp, "out")],
                               capture_output=True, text=True, cwd=ROOT, env={**os.environ, "DIST": os.path.join(tmp, "nodist")})
            self.assertEqual(r.returncode, 2)
            self.assertIn("run ./build.sh runtime first", r.stderr)


if __name__ == "__main__":
    unittest.main()
