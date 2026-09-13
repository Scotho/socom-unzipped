"""Sprint 5 Task 4 Step 1 -- unit tests for the object-keyed uninitialised-field diff.

unittest only (no pytest, no module-level `def test_`), per the task-4-brief.md contract.
Synthetic RDRAM images are built under a fresh temp dir per test, with unique (uuid) filenames.
"""
import contextlib
import io
import os
import shutil
import struct
import tempfile
import unittest
import uuid

from tools_py.parity import object_diff as od

STATIC_ADDR = 0x2000       # arbitrary KSEG-style static address used by every synthetic image
IMAGE_SIZE = 0x10000        # far smaller than a real 32 MiB RDRAM image; the `& 0x1FFFFFF` mask
                             # convention (tools_py/rdr_tree.py) does not require the real size


def _blank_image(size=IMAGE_SIZE):
    return bytearray(size)


def _poke_ptr(img, addr, value):
    struct.pack_into("<I", img, addr & od.RDRAM_MASK, value)


def _write_image(tmpdir, data: bytearray) -> str:
    path = os.path.join(tmpdir, f"{uuid.uuid4().hex}.rdram")
    with open(path, "wb") as f:
        f.write(data)
    return path


class ObjectDiffTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="object_diff_test_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # -- 1. flagged 0xAF-vs-0 field -----------------------------------------------------------

    def test_flagged_field_af_on_ours_zero_on_console(self):
        block_addr = 0x400
        our1, our2 = _blank_image(), _blank_image()
        con1, con2 = _blank_image(), _blank_image()
        for img in (our1, our2, con1, con2):
            _poke_ptr(img, STATIC_ADDR, block_addr)
        our1[block_addr + 0x5] = 0xAF
        our2[block_addr + 0x5] = 0xAF
        con1[block_addr + 0x5] = 0x00
        con2[block_addr + 0x5] = 0x00

        our_blocks = [bytes(our1[block_addr:block_addr + 0x10]),
                      bytes(our2[block_addr:block_addr + 0x10])]
        con_blocks = [bytes(con1[block_addr:block_addr + 0x10]),
                      bytes(con2[block_addr:block_addr + 0x10])]
        rows = {r.offset: r for r in od.diff_blocks(our_blocks, con_blocks)}

        self.assertIn(0x5, rows)
        self.assertTrue(rows[0x5].flagged)

        # And end-to-end through the CLI, over real temp files.
        our_paths = [_write_image(self.tmpdir, our1), _write_image(self.tmpdir, our2)]
        con_paths = [_write_image(self.tmpdir, con1), _write_image(self.tmpdir, con2)]
        buf = _Sink()
        rc = od.run_image_diff([od.StaticSpec.parse(f"{STATIC_ADDR:x}:10")],
                                our_paths, con_paths, out=buf, err=buf)
        self.assertEqual(rc, 0)
        self.assertIn("FLAGGED", buf.text)
        self.assertIn("+0x0005", buf.text)

    # -- 2. a field differing but NOT flagged (non-constant on ours) --------------------------

    def test_differing_field_not_flagged_when_not_constant(self):
        block_addr = 0x400
        our1, our2 = _blank_image(), _blank_image()
        con1, con2 = _blank_image(), _blank_image()
        for img in (our1, our2, con1, con2):
            _poke_ptr(img, STATIC_ADDR, block_addr)
        # ours disagrees with itself at this offset (e.g. a live per-instance counter) -- even
        # though the console reads zero everywhere, this must not be flagged as the uninitialised
        # AF-vs-0 signature.
        our1[block_addr + 0x6] = 0x01
        our2[block_addr + 0x6] = 0x02
        con1[block_addr + 0x6] = 0x00
        con2[block_addr + 0x6] = 0x00

        our_blocks = [bytes(our1[block_addr:block_addr + 0x10]),
                      bytes(our2[block_addr:block_addr + 0x10])]
        con_blocks = [bytes(con1[block_addr:block_addr + 0x10]),
                      bytes(con2[block_addr:block_addr + 0x10])]
        rows = {r.offset: r for r in od.diff_blocks(our_blocks, con_blocks)}

        self.assertIn(0x6, rows)
        self.assertFalse(rows[0x6].flagged)

    # -- 3. unresolved static (NULL in one image) -> exit 2 ------------------------------------

    def test_unresolved_static_exits_2(self):
        block_addr = 0x400
        our1 = _blank_image()
        our2 = _blank_image()
        _poke_ptr(our1, STATIC_ADDR, block_addr)
        _poke_ptr(our2, STATIC_ADDR, 0)  # NULL: this image's chain does not resolve
        con1 = _blank_image()
        _poke_ptr(con1, STATIC_ADDR, block_addr)

        our_paths = [_write_image(self.tmpdir, our1), _write_image(self.tmpdir, our2)]
        con_paths = [_write_image(self.tmpdir, con1)]
        buf = _Sink()
        rc = od.run_image_diff([od.StaticSpec.parse(f"{STATIC_ADDR:x}:10")],
                                our_paths, con_paths, out=buf, err=buf)
        self.assertEqual(rc, 2)

    # -- 4. zero images -> exit 2 (NO-DATA) -----------------------------------------------------

    def test_zero_images_exits_2_no_data(self):
        buf = _Sink()
        rc = od.run_image_diff([od.StaticSpec.parse(f"{STATIC_ADDR:x}:10")], [], [],
                                out=buf, err=buf)
        self.assertEqual(rc, 2)
        self.assertIn("NO-DATA", buf.text)

        # Also via the full CLI arg parser, images entirely absent on both sides of `--`.
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            rc2 = od.main(["--static", f"{STATIC_ADDR:x}:10", "--"])
        self.assertEqual(rc2, 2)
        self.assertIn("NO-DATA", captured.getvalue())

    # -- 5. block at a DIFFERENT address per image, still keyed correctly by offset -----------

    def test_offset_keyed_diff_survives_different_block_addresses(self):
        # Mirrors research/19 F3/F4: the same object sits at a different absolute address in
        # every image because each side's heap places it differently. The tool must still find
        # the flagged offset by following each image's own pointer, not by a shared address.
        our1, our2 = _blank_image(), _blank_image()
        con1, con2 = _blank_image(), _blank_image()
        our_block_addrs = [0x400, 0x900]      # different placement per "ours" image
        con_block_addrs = [0x1200, 0x1300]    # different placement per "console" image, too
        for img, addr in zip((our1, our2), our_block_addrs):
            _poke_ptr(img, STATIC_ADDR, addr)
            img[addr + 0x8] = 0xAF
        for img, addr in zip((con1, con2), con_block_addrs):
            _poke_ptr(img, STATIC_ADDR, addr)
            img[addr + 0x8] = 0x00

        our_paths = [_write_image(self.tmpdir, our1), _write_image(self.tmpdir, our2)]
        con_paths = [_write_image(self.tmpdir, con1), _write_image(self.tmpdir, con2)]
        buf = _Sink()
        rc = od.run_image_diff([od.StaticSpec.parse(f"{STATIC_ADDR:x}:10")],
                                our_paths, con_paths, out=buf, err=buf)
        self.assertEqual(rc, 0)
        # Every image reports ITS OWN block address...
        self.assertIn(f"{our_block_addrs[0]:#x}", buf.text)
        self.assertIn(f"{our_block_addrs[1]:#x}", buf.text)
        self.assertIn(f"{con_block_addrs[0]:#x}", buf.text)
        self.assertIn(f"{con_block_addrs[1]:#x}", buf.text)
        # ...and the flag still fires, keyed purely by offset +0x8.
        self.assertIn("+0x0008", buf.text)
        self.assertIn("FLAGGED", buf.text)


class PeekLogTest(unittest.TestCase):
    """Light coverage of mode 2 (not in the brief's required list, but it backs the frost1/kill2
    reproducibility claim in the report, so it gets the same TDD treatment)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="object_diff_peeklog_test_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_log(self, lines):
        path = os.path.join(self.tmpdir, f"{uuid.uuid4().hex}.log")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def test_field_read_across_two_blocks_and_uncovered_offset(self):
        vtable = 0x6691a0
        # item1: actor block @0x17941d0, words 0..2 given (offsets 0x0/0x4/0x8); word at index 2
        # sits at +0x8 = 0x17941d8.
        # item2: dependent block @0x17941fd0... use a clean +0x200 offset to mirror the real logs.
        actor = 0x17941d0
        dep = actor + 0x200
        line_a = (f"[peek] @{actor:x}: 006691a0(0) 00000003(0) 00000004(0) "
                  f"@{dep:x}: 3f800000(1) 00000000(0)")
        line_b = (f"[peek] @{actor:x}: 006691a0(0) 00000003(0) 00000008(0) "
                  f"@{dep:x}: 3f800000(1) 00000000(0)")
        not_actor_row = "[peek] @416054: 00000000(0) 00000000(0) 00000000(0)"
        path = self._write_log([line_a, line_b, not_actor_row])

        buf = _Sink()
        rc = od.run_peek_log([("frost1", path)], vtable, [0x8, 0x200, 0xd0], out=buf, err=buf)
        self.assertEqual(rc, 0)
        # +0x8 is covered by the actor block itself and varies (0x4 then 0x8).
        self.assertIn("+0x8: 2 covered row(s)", buf.text)
        # +0x200 is covered by the dependent block and is constant (1.0 both rows).
        self.assertIn("+0x200: 2 covered row(s)", buf.text)
        # +0xd0 is never covered by either peeked block on either row.
        self.assertIn("+0xd0: NOT COVERED", buf.text)
        # The row with no actor vtable match is simply not counted.
        self.assertIn("2 rows with actor vtable", buf.text)


class _Sink:
    """A tiny stand-in for a text stream that just remembers what was printed to it."""

    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s

    def flush(self):
        pass


if __name__ == "__main__":
    unittest.main()
