"""The guest probe's per-revision address column (Sprint 11 Task 19).

Every address the mission lane's probes reach into the guest with was written as an r0001 literal --
`0x416054` in `peek_spec`, `*0x408c58+0x2e8` and `0x4365c0` in `scripts/parity/guest_probe_console.json`,
the actor vtable `0x6691a0` the position read keys on. On the r0004 build those four addresses are
somebody else's memory: `logs/parity/gate/s11_r0004_reg2` read 0 rows of 479 and the mission lane failed
`GUEST PROBE FAILED: root_node_y` with all three probes NO-DATA.

The defect to guard against is not "the r0004 run failed" -- it is a run that reads r0001's addresses and
says nothing. So: both columns resolve, a revision the table has no column for raises, and a revision the
probe cannot establish (an image with no build banner, a run log that never says which column the runtime
installed) raises rather than falling back to r0001.
"""
import os
import tempfile
import unittest

from tools_py.parity import guest_probe as gp

CONSOLE = os.path.join("scripts", "parity", "guest_probe_console.json")
R0001_BANNER = b"SOCOM 2 r0001 17:22:21 Oct 11 2003\x00"
R0004_BANNER = b"SOCOM 2 r0004 10:14:38 Nov  3 2004\x00"


class Column(unittest.TestCase):
    def test_both_columns_resolve_every_probe_address(self):
        for name in gp.PROBE_ADDRESSES:
            for revision in gp.REVISIONS:
                a = gp.address(name, revision)
                self.assertIsInstance(a, int)
                self.assertGreater(a, 0x00100000, "%s/%s" % (name, revision))

    def test_the_two_columns_never_share_an_address(self):
        """A column that repeated the other's number would be exactly the silent defect: the same value
        read under a different name. r0004 relinked every one of these four."""
        for name, col in gp.PROBE_ADDRESSES.items():
            self.assertNotEqual(col["r0001"], col["r0004"], name)

    def test_an_unknown_revision_fails_loudly(self):
        with self.assertRaises(ValueError) as e:
            gp.address("player_actor", "r0007")
        self.assertIn("r0007", str(e.exception))
        self.assertIn("r0001", str(e.exception))       # the message names the columns there ARE

    def test_an_unknown_probe_name_fails_loudly(self):
        with self.assertRaises(ValueError) as e:
            gp.address("no_such_probe", "r0001")
        self.assertIn("no_such_probe", str(e.exception))


class PeekSpec(unittest.TestCase):
    def test_the_r0001_spec_is_what_it_has_always_been(self):
        spec = gp.peek_spec(CONSOLE, "r0001").split(",")
        self.assertIn("0x416054:3", spec)
        self.assertIn("*0x408c58+0x2e8:1", spec)
        self.assertIn("0x4365c0:1", spec)

    def test_the_r0004_spec_carries_no_r0001_address(self):
        spec = gp.peek_spec(CONSOLE, "r0004")
        for name, col in gp.PROBE_ADDRESSES.items():
            if name == "actor_vtable":
                continue                                # a value read from a row, never a chain
            self.assertNotIn("%x" % col["r0001"], spec.lower(), "%s leaked into %s" % (name, spec))
            self.assertIn("%x" % col["r0004"], spec.lower(), "%s missing from %s" % (name, spec))

    def test_struct_offsets_are_not_translated(self):
        """`*0x408c58+0x2e8` -- 0x2e8 is a field offset inside the actor, not an address: a relink does
        not move it, and a translation that touched it would read the wrong field."""
        self.assertIn("+0x2e8", gp.peek_spec(CONSOLE, "r0004"))
        self.assertIn("+0x1368", gp.peek_spec(CONSOLE, "r0004"))

    def test_an_unknown_revision_fails_loudly(self):
        with self.assertRaises(ValueError):
            gp.peek_spec(CONSOLE, "r0007")


def _row(revision, root_y=5.50391, move_scale=1.0, pos=(900.0, -145.0, 850.0)):
    """One [peek] row as the runtime prints it for `revision`: the camera record, the actor block at the
    revision's actor static, the skeleton root node and the MoveScale word."""
    import struct

    def w(v):
        return "%08x(%g)" % (struct.unpack("<I", struct.pack("<f", v))[0], v)

    actor, node = 0x01794000, 0x00C10000
    cam = gp.address("camera_record", revision)
    static = gp.address("player_actor", revision)
    vtable = gp.address("actor_vtable", revision)
    words = ["%08x(0)" % vtable] + ["00000000(0)"] * 63
    for slot, v in zip((7, 8, 9), pos):
        words[slot] = w(v)
    line = "[peek] @%x: %s %s %s" % (cam, w(500.0), w(100.0), w(600.0))
    line += " @%x: %08x(0)" % (static, actor)
    line += " @%x: " % actor + " ".join(words)
    line += " @%x: %08x(0)" % (actor + 0x2E8, node)
    line += " @%x: 00000000(0) %s" % (node, w(root_y))
    line += " @%x: %s" % (actor + 0x1368, w(move_scale))
    return line


class Evaluate(unittest.TestCase):
    def test_r0004_rows_are_read_with_the_r0004_column(self):
        rows = [_row("r0004")] * 12
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE, "r0004")}
        self.assertTrue(res["root_node_y"].ok, res["root_node_y"].detail)
        self.assertTrue(res["move_scale"].ok, res["move_scale"].detail)
        self.assertTrue(res["teleport_steps"].ok, res["teleport_steps"].detail)

    def test_r0004_rows_read_with_the_r0001_column_are_no_data_not_a_pass(self):
        """The defect, stated as a case: this is what s11_r0004_reg2 did -- 0 reads of 479 rows. It must
        read as NO-DATA, and NO-DATA is a FAIL on a stage the gate launched itself (gate.probe_lines)."""
        rows = [_row("r0004")] * 12
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE, "r0001")}
        self.assertIsNone(res["root_node_y"].ours)
        self.assertIn("NO-DATA", res["root_node_y"].detail)
        self.assertFalse(res["root_node_y"].ok)

    def test_r0001_rows_still_read_with_the_r0001_column(self):
        rows = [_row("r0001")] * 12
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE, "r0001")}
        self.assertTrue(res["root_node_y"].ok, res["root_node_y"].detail)

    def test_the_revision_is_taken_from_the_run_log_when_not_given(self):
        rows = ["[socom2] address table: the image names itself r0004 -- using the r0004 addresses\n"] + [_row("r0004")] * 12
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertTrue(res["root_node_y"].ok, res["root_node_y"].detail)

    def test_a_log_that_never_names_a_revision_raises(self):
        with self.assertRaises(ValueError) as e:
            gp.evaluate([_row("r0001")] * 3, CONSOLE)
        self.assertIn("revision", str(e.exception))


class RevisionOfImage(unittest.TestCase):
    def _elf(self, tmp, banner, name="socom2_game.elf"):
        p = os.path.join(tmp, name)
        with open(p, "wb") as f:
            f.write(b"\x7fELF" + b"\0" * 64 + banner + b"\0" * 64)
        return p

    def test_the_build_banner_names_the_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gp.revision_of_image(self._elf(tmp, R0001_BANNER)), "r0001")
            self.assertEqual(gp.revision_of_image(self._elf(tmp, R0004_BANNER, "b.elf")), "r0004")

    def test_an_image_with_no_banner_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as e:
                gp.revision_of_image(self._elf(tmp, b"no banner here\x00"))
            self.assertIn("banner", str(e.exception))

    def test_launch_revision_reads_the_elf_the_launch_will_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            elf = self._elf(tmp, R0004_BANNER)
            self.assertEqual(gp.launch_revision({"SOCOM_GAME_ELF": elf}), "r0004")

    def test_a_named_elf_that_is_not_there_raises(self):
        with self.assertRaises(ValueError) as e:
            gp.launch_revision({"SOCOM_GAME_ELF": os.path.join("no", "such", "image.elf")})
        self.assertIn("SOCOM_GAME_ELF", str(e.exception))

    def test_the_default_path_answers_r0001_on_a_bare_clone(self):
        """game/ is git-ignored, so a clone with no disc assets has no image to read -- and no launch to
        make either (collect_pins still hashes the launch environment, which is why this must not raise).
        Either way the answer is r0001: read from the banner when the default image is there, and the
        revision that path NAMES when it is not. Never a fallback for an image that is present and says
        something else -- that case is test_launch_revision_reads_the_elf_the_launch_will_use."""
        self.assertEqual(gp.launch_revision({}), "r0001")


if __name__ == "__main__":
    unittest.main()
