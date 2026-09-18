"""Sprint 8 Goal 1 Task 7: scripts/portable_libs.py picks which shared libraries the Linux
portable folder carries in lib/. It reads `ldd` output on stdin and prints one absolute path
per line: everything the binaries link except glibc, libstdc++ and the graphics/X/audio stack,
which must come from the host. `missing()` reports the `not found` lines so make_portable.sh
can fail loudly instead of shipping a broken tarball."""
import importlib.util
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODULE = os.path.join(ROOT, "scripts", "portable_libs.py")


def _load():
    spec = importlib.util.spec_from_file_location("portable_libs", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# One `ldd dist-linux/socom2` as the VM prints it: the FFmpeg family and its codecs, the host's
# glibc/GL/X/audio stack, the vdso and the loader with no "=>", and one library nothing provides.
LDD = """\
\tlinux-vdso.so.1 (0x00007ffd0b5f4000)
\tlibavcodec.so.60 => /usr/lib/x86_64-linux-gnu/libavcodec.so.60 (0x00007f3a41000000)
\tlibx264.so.164 => /usr/lib/x86_64-linux-gnu/libx264.so.164 (0x00007f3a40a00000)
\tlibGL.so.1 => /usr/lib/x86_64-linux-gnu/libGL.so.1 (0x00007f3a40800000)
\tlibX11.so.6 => /usr/lib/x86_64-linux-gnu/libX11.so.6 (0x00007f3a406c0000)
\tlibpulse.so.0 => /usr/lib/x86_64-linux-gnu/libpulse.so.0 (0x00007f3a40660000)
\tlibstdc++.so.6 => /usr/lib/x86_64-linux-gnu/libstdc++.so.6 (0x00007f3a40400000)
\tlibm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0x00007f3a40318000)
\tlibpthread.so.0 => /lib/x86_64-linux-gnu/libpthread.so.0 (0x00007f3a402f0000)
\tlibdl.so.2 => /lib/x86_64-linux-gnu/libdl.so.2 (0x00007f3a402e0000)
\tlibc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f3a400d0000)
\tlibvpx.so.9 => not found
\t/lib64/ld-linux-x86-64.so.2 (0x00007f3a41400000)
"""

AVCODEC = "/usr/lib/x86_64-linux-gnu/libavcodec.so.60"
X264 = "/usr/lib/x86_64-linux-gnu/libx264.so.164"


class SelectTest(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_selects_exactly_the_copyable_paths(self):
        self.assertEqual(self.m.select(LDD), [AVCODEC, X264])

    def test_skips_the_host_stack_by_name(self):
        picked = " ".join(self.m.select(LDD))
        for excluded in ("libc.so", "libm.so", "libpthread", "libdl.so", "ld-linux",
                         "linux-vdso", "libstdc++", "libGL.so", "libX11", "libpulse"):
            self.assertNotIn(excluded, picked)

    def test_missing_reports_the_not_found_names(self):
        self.assertEqual(self.m.missing(LDD), ["libvpx.so.9"])
        self.assertEqual(self.m.missing(""), [])

    def test_two_ldd_runs_concatenated_dedupe_in_order(self):
        launcher = "\tlibswresample.so.4 => /usr/lib/libswresample.so.4 (0x00007f00)\n"
        both = LDD + launcher + LDD
        self.assertEqual(self.m.select(both), [AVCODEC, X264, "/usr/lib/libswresample.so.4"])

    def test_the_whole_ffmpeg_family_is_carried(self):
        fam = "".join("\t%s.so.60 => /usr/lib/%s.so.60 (0x00007f00)\n" % (n, n) for n in (
            "libavcodec", "libavformat", "libavutil", "libswscale", "libswresample",
            "libavfilter", "libavdevice"))
        self.assertEqual(len(self.m.select(fam)), 7)

    def test_ignores_blank_and_static_lines(self):
        self.assertEqual(self.m.select("\n\tstatically linked\n\n"), [])


class MainTest(unittest.TestCase):
    def _run(self, args, text):
        return subprocess.run([sys.executable, MODULE] + args, input=text,
                              capture_output=True, text=True)

    def test_main_prints_one_path_per_line(self):
        r = self._run([], LDD)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), [AVCODEC, X264])

    def test_missing_flag_exits_1_and_names_them(self):
        r = self._run(["--missing"], LDD)
        self.assertEqual(r.returncode, 1)
        self.assertIn("libvpx.so.9", r.stdout + r.stderr)

    def test_missing_flag_exits_0_when_nothing_is_missing(self):
        r = self._run(["--missing"], LDD.replace("\tlibvpx.so.9 => not found\n", ""))
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
