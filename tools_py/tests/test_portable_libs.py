"""Sprint 8 Goal 1 Task 7: scripts/portable_libs.py picks which shared libraries the Linux
portable folder carries in lib/. It reads `ldd` output on stdin and prints one absolute path
per line: everything the binaries link except glibc, libstdc++ and the graphics/X/audio stack,
which must come from the host. `missing()` reports the `not found` lines so make_portable.sh
can fail loudly instead of shipping a broken tarball."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

from tools_py.tests.binfmt_fixtures import tiny_elf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODULE = os.path.join(ROOT, "scripts", "portable_libs.py")


def _load():
    spec = importlib.util.spec_from_file_location("portable_libs", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# One `ldd dist-linux/socom2` as the VM prints it: the FFmpeg family and its codecs, the host's
# glibc/GL/X/audio stack, its driver-coupled decode and SDL libraries, the vdso and the loader
# with no "=>", and one library nothing provides.
LDD = """\
\tlinux-vdso.so.1 (0x00007ffd0b5f4000)
\tlibavcodec.so.60 => /usr/lib/x86_64-linux-gnu/libavcodec.so.60 (0x00007f3a41000000)
\tlibx264.so.164 => /usr/lib/x86_64-linux-gnu/libx264.so.164 (0x00007f3a40a00000)
\tlibGL.so.1 => /usr/lib/x86_64-linux-gnu/libGL.so.1 (0x00007f3a40800000)
\tlibX11.so.6 => /usr/lib/x86_64-linux-gnu/libX11.so.6 (0x00007f3a406c0000)
\tlibpulse.so.0 => /usr/lib/x86_64-linux-gnu/libpulse.so.0 (0x00007f3a40660000)
\tlibva-drm.so.2 => /usr/lib/x86_64-linux-gnu/libva-drm.so.2 (0x00007f3a40640000)
\tlibSDL2-2.0.so.0 => /usr/lib/x86_64-linux-gnu/libSDL2-2.0.so.0 (0x00007f3a40500000)
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
                         "linux-vdso", "libstdc++", "libGL.so", "libX11", "libpulse",
                         # Driver-coupled and host-audio libraries FFmpeg's closure drags
                         # in: a copied libva-drm talks to the wrong kernel driver and a
                         # copied SDL2 to the wrong video stack. The host owns both.
                         "libva-drm", "libSDL2"):
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


class ReachableTest(unittest.TestCase):
    """Sprint 9 Goal 2 (R151 follow-up): lib/ carries a library only when the shipped executables reach it
    through a chain of libraries we carry ourselves. ldd's list is flat, so it also names what only a HOST
    library needs -- libXau, reached through libxcb, which we never carry: the audit rightly called it an
    orphan. The walk stops at a host-prefix library, because whatever lies behind it is the host's too."""

    def setUp(self):
        self.m = _load()
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        # exe -> libX11 (host) -> libleaf ; exe -> libavcodec (carried) -> libleaf2
        self.files = {
            "socom2": ["libX11.so.6", "libavcodec.so.60", "libc.so.6"],
            "libX11.so.6": ["libleaf.so.1"],
            "libavcodec.so.60": ["libleaf2.so.2"],
            "libleaf.so.1": [],
            "libleaf2.so.2": [],
            "libc.so.6": [],
        }
        for name, needed in self.files.items():
            with open(os.path.join(self.dir, name), "wb") as fh:
                fh.write(tiny_elf(needed))
        self.exe = os.path.join(self.dir, "socom2")
        self.ldd = "".join("\t%s => %s (0x00007f00)\n" % (n, os.path.join(self.dir, n))
                           for n in self.files if n != "socom2")

    def tearDown(self):
        self._tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)

    def test_a_leaf_reached_only_through_a_host_library_is_not_carried(self):
        picked = self.m.reachable(self.ldd, [self.exe])
        self.assertNotIn(self.path("libleaf.so.1"), picked)
        self.assertNotIn(self.path("libX11.so.6"), picked)

    def test_a_leaf_reached_through_a_carried_library_is_carried(self):
        picked = self.m.reachable(self.ldd, [self.exe])
        self.assertEqual(sorted(picked), sorted([self.path("libavcodec.so.60"), self.path("libleaf2.so.2")]))

    def test_the_flat_ldd_list_is_what_used_to_carry_the_orphan(self):
        self.assertIn(self.path("libleaf.so.1"), self.m.select(self.ldd))

    def test_a_library_ldd_did_not_resolve_is_skipped_not_fatal(self):
        ldd = "".join(line if "libleaf2" not in line else "\tlibleaf2.so.2 => not found\n"
                      for line in self.ldd.splitlines(keepends=True))
        self.assertEqual(self.m.reachable(ldd, [self.exe]), [self.path("libavcodec.so.60")])

    def test_main_takes_the_executables_and_walks_them(self):
        r = subprocess.run([sys.executable, MODULE, self.exe], input=self.ldd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(r.stdout.split()),
                         sorted([self.path("libavcodec.so.60"), self.path("libleaf2.so.2")]))


if __name__ == "__main__":
    unittest.main()
