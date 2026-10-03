"""Sprint 18 T9: the launcher's project icon (the owner, 2026-10-03: "make the launcher have an icon for the proj").

Three holds:
  (a) the tracked socom_unzipped.ico is exactly what scripts/make_launcher_icon.py makes from the tracked PNG, so the
      asset cannot drift from its source (the generator is deterministic: Pillow's LANCZOS resize, uncompressed DIB
      entries, no zlib in the path);
  (b) the tracked .ico's ICONDIR is well formed: reserved 0, type 1, one entry per size, every entry inside the file;
  (c) a built dist/socom_unzipped_launcher.exe carries the icon as resources (RT_GROUP_ICON 14 and RT_ICON 3), read
      with a small PE parser here (no third-party module); skipped when no exe is built.
"""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGO_DIR = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xLauncher", "assets", "logo")
ICO = os.path.join(LOGO_DIR, "socom_unzipped.ico")
SOURCE_PNG = os.path.join(LOGO_DIR, "socom_unzipped_icon.png")
SCRIPT = os.path.join(ROOT, "scripts", "make_launcher_icon.py")
EXE = os.path.join(ROOT, "dist", "socom_unzipped_launcher.exe")
RC = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xLauncher", "launcher.rc")
EXPECTED_SIZES = [16, 24, 32, 48, 64]

RT_ICON = 3
RT_GROUP_ICON = 14


def parse_icondir(data):
    """(reserved, type, [(width, height, bytes, offset), ...]) of an .ico; width/height 0 means 256."""
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    entries = []
    for i in range(count):
        w, h, _colors, _res, _planes, _bpp, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        entries.append((w or 256, h or 256, size, offset))
    return reserved, kind, entries


def pe_resource_types(data):
    """The integer type IDs in a PE file's root resource directory (empty when it has no .rsrc)."""
    if data[:2] != b"MZ":
        raise ValueError("no DOS header")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("no PE signature")
    coff = pe + 4
    nsections, = struct.unpack_from("<H", data, coff + 2)
    opt_size, = struct.unpack_from("<H", data, coff + 16)
    opt = coff + 20
    magic, = struct.unpack_from("<H", data, opt)
    if magic == 0x20B:      # PE32+
        ndirs_at, dirs_at = opt + 108, opt + 112
    elif magic == 0x10B:    # PE32
        ndirs_at, dirs_at = opt + 92, opt + 96
    else:
        raise ValueError("unknown optional header magic 0x%x" % magic)
    ndirs, = struct.unpack_from("<I", data, ndirs_at)
    if ndirs <= 2:
        return []
    rsrc_rva, rsrc_size = struct.unpack_from("<II", data, dirs_at + 8 * 2)   # directory 2 = resources
    if rsrc_rva == 0 or rsrc_size == 0:
        return []
    sections = opt + opt_size
    for i in range(nsections):
        s = sections + 40 * i
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, s + 8)
        if va <= rsrc_rva < va + max(vsize, rawsize):
            root = rawptr + (rsrc_rva - va)
            break
    else:
        raise ValueError("resource RVA 0x%x in no section" % rsrc_rva)
    named, ids = struct.unpack_from("<HH", data, root + 12)
    types = []
    for k in range(named + ids):
        name, _off = struct.unpack_from("<II", data, root + 16 + 8 * k)
        if not name & 0x80000000:
            types.append(name)
    return types


class TrackedIcon(unittest.TestCase):
    def test_regenerates_byte_for_byte(self):
        self.assertTrue(os.path.isfile(SCRIPT), "scripts/make_launcher_icon.py is the asset's generator")
        self.assertTrue(os.path.isfile(ICO), "the tracked socom_unzipped.ico")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "socom_unzipped.ico")
            r = subprocess.run([sys.executable, SCRIPT, SOURCE_PNG, "--out", out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, "rb") as f:
                made = f.read()
        with open(ICO, "rb") as f:
            tracked = f.read()
        self.assertEqual(made, tracked, "socom_unzipped.ico drifted from socom_unzipped_icon.png: re-run the script")

    def test_icondir_is_consistent(self):
        with open(ICO, "rb") as f:
            data = f.read()
        reserved, kind, entries = parse_icondir(data)
        self.assertEqual(reserved, 0)
        self.assertEqual(kind, 1, "type 1 = icon")
        self.assertEqual(sorted(w for w, _h, _s, _o in entries), EXPECTED_SIZES)
        end_of_dir = 6 + 16 * len(entries)
        spans = []
        for w, h, size, offset in entries:
            self.assertEqual(w, h, "square entries")
            self.assertGreater(size, 0)
            self.assertGreaterEqual(offset, end_of_dir)
            self.assertLessEqual(offset + size, len(data))
            # each entry is a DIB whose header names its own size (height doubled: the XOR image plus the AND mask)
            hdr, bw, bh = struct.unpack_from("<Iii", data, offset)
            self.assertEqual((hdr, bw, bh), (40, w, 2 * h))
            spans.append((offset, offset + size))
        spans.sort()
        for (_a, b), (c, _d) in zip(spans, spans[1:]):
            self.assertLessEqual(b, c, "entries do not overlap")
        self.assertEqual(spans[-1][1], len(data), "nothing trails the last entry")


class PeParser(unittest.TestCase):
    def test_rejects_a_non_pe(self):
        with self.assertRaises(ValueError):
            pe_resource_types(b"not a pe file at all" * 8)


def _exe_is_current():
    """The built launcher, and newer than the icon and its resource script: an exe built before this change has no
    icon resource and would read as a red of the .rc rather than of the stale build (the T9 review's finding)."""
    if not os.path.isfile(EXE):
        return False
    built = os.path.getmtime(EXE)
    return all(built >= os.path.getmtime(p) for p in (ICO, RC) if os.path.isfile(p))


class BuiltExe(unittest.TestCase):
    @unittest.skipUnless(_exe_is_current(),
                         "no dist/socom_unzipped_launcher.exe newer than launcher.rc and the .ico (./build.sh runtime)")
    def test_exe_carries_the_icon_resources(self):
        with open(EXE, "rb") as f:
            types = pe_resource_types(f.read())
        self.assertIn(RT_GROUP_ICON, types, "RT_GROUP_ICON: the .rc's ICON statement linked in (types %r)" % types)
        self.assertIn(RT_ICON, types, "RT_ICON: the icon's images (types %r)" % types)


if __name__ == "__main__":
    unittest.main()
