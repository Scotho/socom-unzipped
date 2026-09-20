"""Sprint 9 Goal 2: what the portable folder must carry is read from the import tables of the two shipped
executables, by a reader that needs no objdump and no ldd -- so the same audit runs on the Windows host,
in CI and in the VM, over either platform's folder."""
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

from tools_py import portable_audit
from tools_py.tests.binfmt_fixtures import tiny_elf, tiny_pe

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL_EXE = os.path.join(ROOT, "dist", "socom2.exe")


def put(folder, name, data):
    path = os.path.join(folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


class ImportReadersTest(unittest.TestCase):
    def test_pe_imports_in_table_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = put(tmp, "a.exe", tiny_pe(["KERNEL32.dll", "avcodec-61.dll", "libc++.dll"]))
            self.assertEqual(portable_audit.pe_imports(exe), ["KERNEL32.dll", "avcodec-61.dll", "libc++.dll"])
            self.assertEqual(portable_audit.pe_imports(put(tmp, "b.dll", tiny_pe([]))), [])

    def test_elf_needed_in_table_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            so = put(tmp, "socom2", tiny_elf(["libavcodec.so.60", "libc.so.6"]))
            self.assertEqual(portable_audit.elf_needed(so), ["libavcodec.so.60", "libc.so.6"])

    def test_anything_else_is_a_value_error_naming_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            junk = put(tmp, "junk.bin", b"x")
            for reader in (portable_audit.pe_imports, portable_audit.elf_needed):
                with self.assertRaises(ValueError) as caught:
                    reader(junk)
                self.assertIn("junk.bin", str(caught.exception))

    @unittest.skipUnless(os.path.isfile(REAL_EXE), "no dist/socom2.exe on this machine")
    def test_the_real_runner_imports_the_three_ffmpeg_libraries_it_calls(self):
        names = {n.lower() for n in portable_audit.pe_imports(REAL_EXE)}
        self.assertLessEqual({"avcodec-61.dll", "avutil-59.dll", "swscale-8.dll", "libc++.dll", "kernel32.dll"}, names)
        self.assertNotIn("avformat-61.dll", names)


class WindowsFolderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        put(self.dir, "socom2.exe", tiny_pe(["KERNEL32.dll", "api-ms-win-crt-heap-l1-1-0.dll", "AVCODEC-61.DLL"]))
        put(self.dir, "socom_unzipped_launcher.exe", tiny_pe(["USER32.dll", "libc++.dll"]))
        put(self.dir, "avcodec-61.dll", tiny_pe(["zlib1.dll", "bcrypt.dll"]))
        put(self.dir, "zlib1.dll", tiny_pe(["KERNEL32.dll"]))
        put(self.dir, "libc++.dll", tiny_pe([]))

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_closed_folder_has_no_findings(self):
        result = portable_audit.audit(self.dir, "Windows")
        self.assertEqual(result["needed"], ["avcodec-61.dll", "libc++.dll", "zlib1.dll"])
        self.assertEqual(result["missing"], {})
        self.assertEqual(result["orphans"], [])

    def test_winhttp_is_windows_and_does_not_have_to_be_shipped(self):
        """Sprint 9 P7. Goal 8 gave the launcher a WinHTTP transport for the bug report and the status
        line, and WINHTTP.dll was not in WINDOWS_SYSTEM -- so the first release packaging after Goal 8
        called it a missing import and refused to build the archive. It is a Windows system library
        (C:/Windows/System32/winhttp.dll, present since Vista); shipping a copy would be wrong."""
        put(self.dir, "socom_unzipped_launcher.exe", tiny_pe(["KERNEL32.dll", "WINHTTP.dll"]))
        result = portable_audit.audit(self.dir, "Windows")
        self.assertEqual(result["missing"], {},
                         "a system library the launcher imports is not a missing file")
        self.assertNotIn("winhttp.dll", [n.lower() for n in result["needed"]],
                         "and it is not something the portable folder has to carry")

    def test_a_dll_nothing_imports_is_an_orphan(self):
        put(self.dir, "OpenEXR-3_3.dll", tiny_pe(["KERNEL32.dll"]))
        put(self.dir, "avformat-61.dll", tiny_pe(["avcodec-61.dll"]))   # imports, but is imported by nothing
        self.assertEqual(portable_audit.audit(self.dir, "Windows")["orphans"], ["OpenEXR-3_3.dll", "avformat-61.dll"])

    def test_an_import_that_is_not_in_the_folder_is_missing_and_says_who_wanted_it(self):
        os.remove(os.path.join(self.dir, "zlib1.dll"))
        put(self.dir, "socom_unzipped_launcher.exe", tiny_pe(["USER32.dll", "libc++.dll", "VCRUNTIME140.dll"]))
        self.assertEqual(portable_audit.audit(self.dir, "Windows")["missing"],
                         {"zlib1.dll": "avcodec-61.dll", "VCRUNTIME140.dll": "socom_unzipped_launcher.exe"})

    def test_the_cli_prints_the_closure_with_lf_and_fails_on_a_missing_import(self):
        tool = os.path.join(ROOT, "tools_py", "portable_audit.py")
        exes = [os.path.join(self.dir, "socom2.exe"), os.path.join(self.dir, "socom_unzipped_launcher.exe")]
        r = subprocess.run([sys.executable, tool, "closure", "--dir", self.dir] + exes, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"avcodec-61.dll\nlibc++.dll\nzlib1.dll\n")
        os.remove(os.path.join(self.dir, "libc++.dll"))
        r = subprocess.run([sys.executable, tool, "closure", "--dir", self.dir] + exes, capture_output=True)
        self.assertEqual(r.returncode, 3)
        self.assertIn(b"libc++.dll", r.stderr)
        r = subprocess.run([sys.executable, tool, "audit", self.dir, "--system", "Windows"], capture_output=True)
        self.assertEqual(r.returncode, 4)


class LinuxFolderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        put(self.dir, "socom2", tiny_elf(["libavcodec.so.60", "libGL.so.1", "libc.so.6", "libstdc++.so.6"]))
        put(self.dir, "socom_unzipped_launcher", tiny_elf(["libc.so.6", "libX11.so.6"]))
        put(self.dir, "lib/libavcodec.so.60", tiny_elf(["libvpx.so.9", "libc.so.6"]))
        put(self.dir, "lib/libvpx.so.9", tiny_elf(["libc.so.6"]))

    def tearDown(self):
        self._tmp.cleanup()

    def test_host_libraries_are_neither_missing_nor_wanted_in_lib(self):
        result = portable_audit.audit(self.dir, "Linux")
        self.assertEqual(result, {"needed": ["libavcodec.so.60", "libvpx.so.9"], "missing": {}, "orphans": []})

    def test_a_library_nothing_needs_is_an_orphan_and_a_needed_one_gone_is_missing(self):
        put(self.dir, "lib/libavformat.so.60", tiny_elf(["libavcodec.so.60"]))
        os.remove(os.path.join(self.dir, "lib", "libvpx.so.9"))
        result = portable_audit.audit(self.dir, "Linux")
        self.assertEqual(result["orphans"], ["libavformat.so.60"])
        self.assertEqual(result["missing"], {"libvpx.so.9": "libavcodec.so.60"})


class OtherPlatformTest(unittest.TestCase):
    """Sprint 9 Goal 2 (R151 follow-up): the reader is chosen by the FILE's magic, not by the host, so CI
    (Linux) audits a Windows folder and the Windows host audits a Linux one. The CI failure was the CLI
    reaching for the ELF reader on socom2.exe because it ran on Linux."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.windows = os.path.join(self.dir, "win")
        put(self.windows, "socom2.exe", tiny_pe(["KERNEL32.dll", "avcodec-61.dll"]))
        put(self.windows, "socom_unzipped_launcher.exe", tiny_pe(["USER32.dll"]))
        put(self.windows, "avcodec-61.dll", tiny_pe(["bcrypt.dll"]))
        self.linux = os.path.join(self.dir, "lin")
        put(self.linux, "socom2", tiny_elf(["libavcodec.so.60", "libc.so.6"]))
        put(self.linux, "socom_unzipped_launcher", tiny_elf(["libc.so.6"]))
        put(self.linux, "lib/libavcodec.so.60", tiny_elf(["libc.so.6"]))

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_magic_names_the_platform(self):
        self.assertEqual(portable_audit.system_of(os.path.join(self.windows, "socom2.exe")), "Windows")
        self.assertEqual(portable_audit.system_of(os.path.join(self.linux, "socom2")), "Linux")
        with self.assertRaises(ValueError):
            portable_audit.system_of(put(self.dir, "junk.bin", b"x"))

    def test_audit_with_no_system_reads_the_folder_it_was_given(self):
        for folder, needed in ((self.windows, ["avcodec-61.dll"]), (self.linux, ["libavcodec.so.60"])):
            result = portable_audit.audit(folder)
            self.assertEqual((result["needed"], result["missing"], result["orphans"]), (needed, {}, []))

    def test_the_cli_audits_either_folder_with_no_system_flag(self):
        tool = os.path.join(ROOT, "tools_py", "portable_audit.py")
        for folder, count in ((self.windows, 1), (self.linux, 1)):
            r = subprocess.run([sys.executable, tool, "audit", folder], capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(b"%d needed, 0 missing, 0 orphans" % count, r.stdout)
        exes = [os.path.join(self.windows, n) for n in ("socom2.exe", "socom_unzipped_launcher.exe")]
        r = subprocess.run([sys.executable, tool, "closure", "--dir", self.windows] + exes, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"avcodec-61.dll\n")


class Sha256SumsTest(unittest.TestCase):
    def test_written_in_sha256sum_format_and_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            put(tmp, "b.zip", b"bbb")
            put(tmp, "a.tar.gz", b"aaa")
            path = portable_audit.write_sha256sums(tmp, ["b.zip", "a.tar.gz"])
            self.assertEqual(os.path.basename(path), "SHA256SUMS")
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), ("%s  a.tar.gz\n%s  b.zip\n" % (
                    hashlib.sha256(b"aaa").hexdigest(), hashlib.sha256(b"bbb").hexdigest())).encode())
            self.assertEqual(portable_audit.verify_sha256sums(tmp), [])

    def test_a_changed_archive_a_missing_one_and_a_missing_file_are_each_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(portable_audit.verify_sha256sums(tmp), ["SHA256SUMS: not found"])
            put(tmp, "a.zip", b"aaa")
            put(tmp, "b.zip", b"bbb")
            portable_audit.write_sha256sums(tmp, ["a.zip", "b.zip"])
            put(tmp, "a.zip", b"aaX")
            os.remove(os.path.join(tmp, "b.zip"))
            self.assertEqual(portable_audit.verify_sha256sums(tmp), ["a.zip: checksum differs", "b.zip: not found"])


if __name__ == "__main__":
    unittest.main()
