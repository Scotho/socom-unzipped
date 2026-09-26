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
import re
import tempfile
import unittest

from tools_py.parity import guest_addresses as ga
from tools_py.parity import guest_probe as gp
from tools_py.parity import sp_death_probe as sp
from tools_py.parity import verdict_core as vc

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

    def test_a_field_offset_that_did_not_move_is_left_alone(self):
        """`*0x408c58+0x2e8` -- 0x2e8 is the skeleton-root field, and it is the SAME displacement on
        r0004: 31 evidence-twinned instructions use it in the r0001 image and all 31 twins read 0x2e8."""
        self.assertIn("+0x2e8", gp.peek_spec(CONSOLE, "r0004"))

    def test_a_field_offset_that_DID_move_is_translated(self):
        """MoveScale is actor+0x1368 on r0001 and actor+**0x136c** on r0004: the object gained a word at
        +0x1334 (the r0004 constructor has one extra `sw $zero, 0x1334($s0)` and its MoveScale store reads
        0x136c), and all six register-relative uses of 0x1368 in r0001 -- three `lwc1` in FUN_00551ec0,
        two `swc1` in the setter FUN_00553dc0, one `sw` in the constructor FUN_00553ea0 -- are 0x136c in
        their r0004 twins. Reading +0x1368 on r0004 reads the field below it, which is 0."""
        self.assertIn("+0x1368", gp.peek_spec(CONSOLE, "r0001"))
        spec = gp.peek_spec(CONSOLE, "r0004")
        self.assertIn("+0x136c", spec)
        self.assertNotIn("+0x1368", spec)

    def test_an_unknown_revision_fails_loudly(self):
        with self.assertRaises(ValueError):
            gp.peek_spec(CONSOLE, "r0007")


class FieldOffsets(unittest.TestCase):
    """The layout half of the per-revision table. An address column alone was not enough: `s11_r0004_probe1`
    reached the right actor (vtable 0x668b20, root_node_y 4.707) and still read MoveScale = 0, because the
    field itself had moved. A field offset is data about the build, exactly like an address."""

    def test_every_offset_resolves_in_both_columns(self):
        for name in gp.PROBE_OFFSETS:
            for revision in gp.REVISIONS:
                self.assertIsInstance(gp.offset(name, revision), int, "%s/%s" % (name, revision))

    def test_move_scale_moved_by_one_word_and_root_node_did_not(self):
        self.assertEqual(gp.offset("move_scale", "r0001"), 0x1368)
        self.assertEqual(gp.offset("move_scale", "r0004"), 0x136C)
        self.assertEqual(gp.offset("root_node", "r0001"), gp.offset("root_node", "r0004"))

    def test_an_unknown_revision_fails_loudly(self):
        with self.assertRaises(ValueError) as e:
            gp.offset("move_scale", "r0007")
        self.assertIn("r0007", str(e.exception))
        self.assertIn("r0004", str(e.exception))

    def test_an_unknown_field_name_fails_loudly(self):
        with self.assertRaises(ValueError) as e:
            gp.offset("no_such_field", "r0001")
        self.assertIn("no_such_field", str(e.exception))


def _row(revision, root_y=5.50391, move_scale=1.0, pos=(900.0, -145.0, 850.0), move_scale_off=None,
         camera=None):
    """One [peek] row as the runtime prints it for `revision`: the camera record, the actor block at the
    revision's actor static, the skeleton root node and the MoveScale word.

    The camera defaults to where a real run's sits -- orbiting the player at ~19 ground units -- because
    camera_orbit is a scored probe (review F7)."""
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
    cpos = camera if camera is not None else (pos[0] - 3.0, pos[1] + 25.0, pos[2] - 19.0)
    line = "[peek] @%x: %s %s %s" % (cam, w(cpos[0]), w(cpos[1]), w(cpos[2]))
    line += " @%x: %08x(0)" % (static, actor)
    line += " @%x: " % actor + " ".join(words)
    line += " @%x: %08x(0)" % (actor + gp.offset("root_node", revision), node)
    line += " @%x: 00000000(0) %s" % (node, w(root_y))
    if move_scale_off is None:
        move_scale_off = gp.offset("move_scale", revision)
    line += " @%x: %s" % (actor + move_scale_off, w(move_scale))
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

    def test_the_r0004_field_below_move_scale_is_not_mistaken_for_it(self):
        """`s11_r0004_probe1`, as a case. The run reached the right actor -- vtable 0x668b20, root_node_y
        4.707, teleport_steps 0 -- and read MoveScale 0 against the console's 1, because the word it read,
        actor+0x1368, is the field BELOW MoveScale on r0004 and that field is 0. With the r0004 layout the
        same row reads 1.0; with the r0001 layout it reads 0 and fails. A zero is the dangerous answer: it
        is a number, not silence."""
        import struct

        def w(v):
            return "%08x(%g)" % (struct.unpack("<I", struct.pack("<f", v))[0], v)

        actor = 0x01794000                              # the r0004 layout, written out as literals
        rows = [_row("r0004", move_scale_off=0x136C) + " @%x: %s" % (actor + 0x1368, w(0.0))] * 12
        good = {r.name: r for r in gp.evaluate(rows, CONSOLE, "r0004")}
        self.assertTrue(good["move_scale"].ok, good["move_scale"].detail)
        self.assertAlmostEqual(good["move_scale"].ours, 1.0, places=5)
        keep = gp.PROBE_OFFSETS["move_scale"]["r0004"]
        try:                                            # the pre-fix constant, on the same rows
            gp.PROBE_OFFSETS["move_scale"]["r0004"] = 0x1368
            stale = {r.name: r for r in gp.evaluate(rows, CONSOLE, "r0004")}
        finally:
            gp.PROBE_OFFSETS["move_scale"]["r0004"] = keep
        self.assertEqual(stale["move_scale"].ours, 0.0)
        self.assertFalse(stale["move_scale"].ok)
        self.assertTrue(stale["root_node_y"].ok, "the rest of the chain still reads -- that is the trap")

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

    def test_the_default_path_answers_r0001_only_when_asked(self):
        """game/ is git-ignored, so a clone with no disc assets has no image to read -- and no launch to
        make either (collect_pins still hashes the launch environment, which is why that caller must not
        get an exception). The answer is r0001 from the path's NAME, and only for a caller that asked:
        the same call without `default_ok` raises. Never a fallback for an image that is present and says
        something else -- that case is test_launch_revision_reads_the_elf_the_launch_will_use."""
        if os.path.isfile(ga.DEFAULT_GAME_ELF):
            self.assertEqual(gp.launch_revision({}), "r0001")        # read from the banner
        else:
            self.assertEqual(gp.launch_revision({}, default_ok=True), "r0001")
            with self.assertRaises(ValueError):
                gp.launch_revision({})

    def test_the_module_re_exports_the_shared_table_rather_than_copying_it(self):
        """Re-review N1: guest_probe kept a pre-fix COPY of these below the re-exports, so it shadowed
        them -- `gp.launch_revision` had no `default_ok` and answered r0001 unconditionally (F3's defect,
        exported), and `gp.log_revision` rejected the fallback wording, so evaluate() read NO-DATA on a
        fallback-branch log. Identity, not equality: a second definition cannot pass this."""
        for name in ("address", "offset", "revision_of_image", "launch_revision", "revision_of_peek_spec",
                     "PROBE_ADDRESSES", "PROBE_OFFSETS", "REVISIONS", "BANNER_RE", "GAME_ELF_ENV",
                     "DEFAULT_GAME_ELF"):
            self.assertIs(getattr(gp, name), getattr(ga, name), name)
        self.assertFalse(hasattr(gp, "LOG_REVISION_RE"), "the copy's regex is gone with the copy")
        # log_revision is the one wrapper: ga's returns (revision, how), this keeps the revision.
        names_itself = ["[socom2] address table: the image names itself r0004 -- using the r0004 addresses"]
        self.assertEqual(gp.log_revision(names_itself), ga.log_revision(names_itself)[0])

    def test_the_bare_clone_default_has_to_be_asked_for(self):
        """Review F3: answering r0001 from the PATH'S NAME is the one place the table's rule ("never
        r0001 unless something said r0001") is relaxed, and it used to be relaxed silently, for every
        caller. It is now a parameter: `gate.collect_pins` asks for it (a checkout with no disc assets
        must still be able to hash the launch environment), and a launch does not get it."""
        missing = {"PATH": "x"}
        self.assertEqual(ga.launch_revision(missing, default_ok=True), "r0001")
        if not os.path.isfile(ga.DEFAULT_GAME_ELF):
            with self.assertRaises(ValueError):
                ga.launch_revision(missing, default_ok=False)


class SharedWithTheLadder(unittest.TestCase):
    """Review F6: before this, the same four r0001 numbers lived in three modules, and correcting one
    would have left the others reading the old value with nothing objecting. guest_addresses is the one
    home; the ladder's instruments read their r0001 constants out of it."""

    def test_verdict_core_and_sp_death_probe_read_the_r0001_column(self):
        self.assertEqual(vc.ACTOR_VTABLE, ga.address("actor_vtable", "r0001"))
        self.assertEqual(vc.CAMERA_RECORD_ADDR, ga.address("camera_record", "r0001"))
        self.assertEqual(vc.ROUND_TIME_ADDR, ga.address("guest_clock", "r0001"))
        self.assertEqual(sp.ACTOR_STATIC, ga.address("player_actor", "r0001"))

    def test_the_r0001_column_is_still_the_numbers_the_ladder_has_always_used(self):
        """The values themselves, written out once: reading them from a table must not have changed one.
        Every online-ladder verdict on record was measured with these."""
        self.assertEqual((vc.ACTOR_VTABLE, vc.CAMERA_RECORD_ADDR, vc.ROUND_TIME_ADDR, sp.ACTOR_STATIC),
                         (0x006691A0, 0x00416054, 0x004365C0, 0x00408C58))

    def test_actor_addr_is_one_rule_given_two_numbers(self):
        """Review F11: guest_probe had its own copy of sp_death_probe's actor selection. It now calls the
        same function with the revision's pair, so the r0001 defaults must still behave identically."""
        items = [(sp.ACTOR_STATIC, [0x01794000, 0, 0, 0])]
        self.assertEqual(sp.actor_addr(items), 0x01794000)
        self.assertEqual(sp.actor_addr(items, ga.address("player_actor", "r0001"), vc.ACTOR_VTABLE), 0x01794000)
        r4 = [(ga.address("player_actor", "r0004"), [0x01753D40, 0, 0, 0])]
        self.assertIsNone(sp.actor_addr(r4))                                     # r0001's pair sees nothing
        self.assertEqual(sp.actor_addr(r4, ga.address("player_actor", "r0004"),
                                       ga.address("actor_vtable", "r0004")), 0x01753D40)


class RevisionsAreDerived(unittest.TestCase):
    def test_revisions_comes_from_the_table_not_from_a_hand_kept_list(self):
        """Review F10: REVISIONS fed only the error messages and the tests, so a fifth column added to
        PROBE_ADDRESSES without touching it would have made address() print a list omitting the revision
        it had just accepted -- and the suite, iterating the same list, would not have noticed."""
        self.assertEqual(set(ga.REVISIONS), {r for col in ga.PROBE_ADDRESSES.values() for r in col})
        for col in ga.PROBE_ADDRESSES.values():
            self.assertEqual(set(col), set(ga.REVISIONS))

    def test_the_cli_revision_flag_does_not_traceback_when_it_is_last(self):
        """`--revision` with nothing after it used to read argv[i + 1] and raise IndexError."""
        with self.assertRaises(SystemExit):
            gp.main(["some.log", "--revision"])


class PeekSpecRevision(unittest.TestCase):
    """`revision_of_peek_spec`: which column a recorded PS2X_PEEK is written in. This is what lets an
    ARCHIVED stamp be re-scored with the addresses its own rows are in (review F1) -- the chains ARE the
    addresses the runtime printed the rows under."""

    def test_each_columns_own_spec_reads_back_as_that_column(self):
        for rev in ga.REVISIONS:
            self.assertEqual(ga.revision_of_peek_spec(gp.peek_spec(CONSOLE, rev)), rev)

    def test_a_wider_operator_spec_still_names_one_column(self):
        self.assertEqual(ga.revision_of_peek_spec(gp.peek_spec(CONSOLE, "r0004") + ",*0x869360:64"), "r0004")

    def test_a_spec_naming_neither_or_both_raises(self):
        with self.assertRaises(ValueError):
            ga.revision_of_peek_spec("*0x869360:64")
        with self.assertRaises(ValueError):
            ga.revision_of_peek_spec("0x416054:3,0x442fd0:1")


class CameraOrbit(unittest.TestCase):
    """Review F7: camera_record is launched and was never read, so a wrong r0004 value for it -- the entry
    resting on the fewest twinned referrers -- had no symptom at all. Now the probe measures the ground
    distance between the camera record and the actor, which a wrong address cannot fake."""

    def test_a_camera_in_orbit_passes_and_one_somewhere_else_fails(self):
        rows = [_row("r0004")] * 12
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE, "r0004")}
        self.assertTrue(res["camera_orbit"].ok, res["camera_orbit"].detail)
        self.assertLess(abs(res["camera_orbit"].ours - gp.CAMERA_ORBIT_U), gp.CAMERA_ORBIT_TOL_U)
        far = [_row("r0004", camera=(1500.0, -120.0, 200.0))] * 12
        self.assertFalse({r.name: r for r in gp.evaluate(far, CONSOLE, "r0004")}["camera_orbit"].ok)

    def test_the_band_holds_what_every_archived_stamp_measured(self):
        """Re-review N3 re-measured every stamp on disk: 15 r0001-column stamps span 17.156
        (s11_rtstate_gate) .. 20.659 (s11_probe_r0001b), 3 r0004-column ones 17.807 .. 22.737
        (s11_r0004_reg3). The band holds all of them with room, holds the ladder's 24.9-unit steady orbit
        radius, and rejects the 0.90 the wrong-column stamps read on every row."""
        lo = gp.CAMERA_ORBIT_U - gp.CAMERA_ORBIT_TOL_U
        hi = gp.CAMERA_ORBIT_U + gp.CAMERA_ORBIT_TOL_U
        for measured in (17.156, 18.366, 20.659, 17.807, 22.737, 24.9):
            self.assertTrue(lo <= measured <= hi, measured)
        self.assertFalse(lo <= 0.90 <= hi)
        # ... and it is not so wide that it has stopped being about this address: the observed spread is
        # 17.156..22.737, and the band is under 3x it.
        self.assertLess(hi - lo, 3 * (22.737 - 17.156))



class LadderPeekSpecBytes(unittest.TestCase):
    """The ladder's PEEK_SPEC is launched as an environment string and pinned by past runs: deriving its
    addresses from guest_addresses (Task 19 re-review N4) must leave the bytes exactly as the literals were,
    including the case of the hex digits (re-review 2, N5)."""

    def test_peek_spec_is_the_historical_string(self):
        from tools_py.parity import sp_death_probe as sp
        historical = ",".join([
            "0x416054:3", "*0x408c58:64", "*0x408c58+0xF78:1", "*0x408c58+0x1044:1", "*0x408c58+0xc0*:32",
            "0x408c58:4", "*0x408c58+0x100:64", "*0x408c58+0x200:64", "*0x408c58+0x300:64",
            "*0x408c58+0xFB4:1", "*0x408c58+0x1368:1",
        ])
        self.assertEqual(sp.PEEK_SPEC, historical)



class OffsetNames(unittest.TestCase):
    """Sprint 12 Task 7 (Goal 5): a name beside each PROBE_OFFSETS number, per revision, from research/50.
    A name is a SOCOM 1 field that SOCOM II's own access pattern confirmed (research/50 §4's rule); every
    other entry says `unnamed` and why. The names are documentation: this also pins the numbers, so a
    later edit that moves one without revisiting its name fails here."""

    VERDICTS = ("confirmed", "single-twin", "contradicted", "unknown")      # plus "shifted by <N>"
    SHIFTED_RE = re.compile(r"^shifted by ([+-]0x[0-9a-f]+)$")

    def _is_shift(self, verdict):
        return self.SHIFTED_RE.match(verdict)

    def test_the_numbers_are_the_numbers_they_were(self):
        """The whole table as it stood before any name was written beside it (Sprint 11 Task 19)."""
        self.assertEqual(ga.PROBE_OFFSETS, {
            "root_node": {"r0001": 0x2E8, "r0004": 0x2E8},
            "move_scale": {"r0001": 0x1368, "r0004": 0x136C},
            "actor_pos": {"r0001": 0x1C, "r0004": 0x1C},
        })

    def test_every_offset_in_every_revision_has_an_entry(self):
        self.assertEqual(set(ga.OFFSET_NAMES), set(ga.PROBE_OFFSETS))
        for name, col in ga.PROBE_OFFSETS.items():
            self.assertEqual(set(ga.OFFSET_NAMES[name]), set(col), name)

    def test_every_verdict_is_one_of_the_five(self):
        for name, col in ga.OFFSET_NAMES.items():
            for revision, entry in col.items():
                v = entry["verdict"]
                self.assertTrue(v in self.VERDICTS or self._is_shift(v), "%s/%s: %r" % (name, revision, v))
                self.assertTrue(entry["note"].startswith("research/50 §"), "%s/%s" % (name, revision))

    def test_only_a_confirmed_or_shifted_verdict_carries_a_name(self):
        for name, col in ga.OFFSET_NAMES.items():
            for revision, entry in col.items():
                where = "%s/%s" % (name, revision)
                if entry["name"] == ga.UNNAMED:
                    self.assertTrue(entry["reason"], where)
                    self.assertIsNone(entry["socom1_offset"], where)
                    continue
                v = entry["verdict"]
                self.assertTrue(v == "confirmed" or self._is_shift(v), where)
                self.assertRegex(entry["name"], r"^[A-Za-z_]\w*::[A-Za-z_][\w.]*$", where)

    def test_a_named_offset_is_its_socom1_offset_plus_the_shift(self):
        """The name and the number are tied: SOCOM 1 offset + the verdict's shift = this revision's value.
        A number moved without its name being revisited breaks this, not just the pin above."""
        for name, col in ga.OFFSET_NAMES.items():
            for revision, entry in col.items():
                if entry["name"] == ga.UNNAMED:
                    continue
                m = self._is_shift(entry["verdict"])
                shift = int(m.group(1), 16) if m else 0
                self.assertEqual(entry["socom1_offset"] + shift, ga.PROBE_OFFSETS[name][revision],
                                 "%s/%s" % (name, revision))

    def test_a_candidate_or_a_contradiction_is_recorded_as_such_never_as_a_name(self):
        for name, col in ga.OFFSET_NAMES.items():
            for revision, entry in col.items():
                where = "%s/%s" % (name, revision)
                if entry["verdict"] == "single-twin":
                    self.assertEqual(entry["name"], ga.UNNAMED, where)
                    self.assertTrue(entry["candidate"], where)
                if entry["verdict"] == "contradicted":
                    self.assertEqual(entry["name"], ga.UNNAMED, where)
                    self.assertTrue(entry["contradicts"], where)

    def test_the_names_research_50_gives_and_the_ones_it_refuses(self):
        """research/50 §4a: root_node is CZSealBody::m_root (SOCOM 1 0x26c, +0x7c); actor_pos is
        contradicted (the same-offset field CEntity::m_node sits at 0x28 in r0001; the position triple is
        new in SOCOM II); move_scale has no demo twin. The stop rule: those two stay unnamed."""
        got = {(n, r): (e["name"], e["verdict"]) for n, col in ga.OFFSET_NAMES.items() for r, e in col.items()}
        self.assertEqual(got, {
            ("root_node", "r0001"): ("CZSealBody::m_root", "shifted by +0x7c"),
            ("root_node", "r0004"): ("CZSealBody::m_root", "shifted by +0x7c"),
            ("actor_pos", "r0001"): (ga.UNNAMED, "contradicted"),
            ("actor_pos", "r0004"): (ga.UNNAMED, "contradicted"),
            ("move_scale", "r0001"): (ga.UNNAMED, "unknown"),
            ("move_scale", "r0004"): (ga.UNNAMED, "unknown"),
        })
        self.assertIn("no demo twin", ga.OFFSET_NAMES["move_scale"]["r0001"]["reason"])
        self.assertIn("new in SOCOM II", ga.OFFSET_NAMES["actor_pos"]["r0001"]["reason"])

    def test_a_name_is_never_read_by_the_harness(self):
        """Documentation for the reader: no module outside the tests refers to OFFSET_NAMES, and the
        module itself only defines it."""
        root = os.path.join("tools_py")
        for dirpath, _dirs, files in os.walk(root):
            if os.path.join("tools_py", "tests") in dirpath:
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(dirpath, f)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    code = [l for l in fh if "OFFSET_NAMES" in l and not l.lstrip().startswith("#")]
                if path == os.path.join("tools_py", "parity", "guest_addresses.py"):
                    self.assertEqual(len(code), 1, code)
                    self.assertTrue(code[0].startswith("OFFSET_NAMES = "), code)
                else:
                    self.assertEqual(code, [], path)



class InstrumentStatics(unittest.TestCase):
    """Sprint 13 Task H6: INSTRUMENT_ADDRESSES may leave a cell ABSENT, and an absent cell refuses with its
    reason -- never answers another column's number, never a guessed one."""

    def test_every_absent_cell_has_a_reason_and_every_reason_an_absent_cell(self):
        absent = {(n, r) for n, col in ga.INSTRUMENT_ADDRESSES.items() for r in ga.REVISIONS if r not in col}
        self.assertEqual(absent, set(ga.UNPLACED))

    def test_every_instrument_name_has_its_r0001_column(self):
        for n in ga.instrument_names():
            self.assertIsInstance(ga.address(n, "r0001"), int, n)

    def test_every_placed_r0004_cell_is_one_data_via_twin_re_derives(self):
        """The reverse of test_data_via_twin's check: a cell written here without a COLUMN row would be a
        number `python -m tools_py.data_via_twin --column` never re-derives."""
        from tools_py import data_via_twin as dvt
        column = {name: (r1, r4) for name, r1, r4, _how in dvt.COLUMN}
        for name, col in ga.INSTRUMENT_ADDRESSES.items():
            if "r0004" in col:
                self.assertEqual(column.get(name), (col["r0001"], col["r0004"]), name)

    def test_an_absent_cell_refuses_with_its_reason(self):
        with self.assertRaises(ValueError) as e:
            ga.address("vagstore_base", "r0004")
        self.assertIn("UNPLACED on r0004", str(e.exception))

    def test_addresses_refuses_the_whole_set_naming_every_absent_one(self):
        with self.assertRaises(ValueError) as e:
            ga.addresses(["cue_route", "motion_pack_ptr", "motion_pack_size"], "r0004")
        self.assertIn("2 of 3", str(e.exception))
        self.assertEqual(ga.addresses(["cue_route", "camera_ptr"], "r0004"),
                         {"cue_route": 0x004A1510, "camera_ptr": 0x0048C1B8})

    def test_the_instrument_names_do_not_widen_all_names(self):
        """all_names() promises both columns for every name; the instrument statics do not."""
        self.assertFalse(set(ga.instrument_names()) & set(ga.all_names()))

    def test_no_placed_cell_shares_an_address_with_another_name(self):
        for r in ga.REVISIONS:
            seen = {}
            for n in ga.all_names() + ga.instrument_names():
                col = ga.INSTRUMENT_ADDRESSES.get(n) or {r: ga.address(n, r)}
                if r not in col:
                    continue
                self.assertNotIn(col[r], seen, "%s and %s are both 0x%x on %s" % (n, seen.get(col[r]), col[r], r))
                seen[col[r]] = n

    def test_cam_poll_renders_its_default_from_the_table(self):
        from tools_py.parity import cam_poll
        self.assertEqual(cam_poll.DEFAULT_SPEC, "*0x488de8+0x120:96")

    def test_cam_poll_refuses_the_r0004_default_the_window_offset_is_r0001s(self):
        """The pointer is placed on r0004; the +0x120 window inside the object is not (docs/HAZARDS.md recompiler: a wrong
        struct offset answers with a number). The default refuses rather than render r0001's offset."""
        from tools_py.parity import cam_poll
        with self.assertRaises(ValueError) as e:
            cam_poll.default_spec("r0004")
        self.assertIn("unverified", str(e.exception))
        self.assertIn("0x48c1b8", str(e.exception))


class PointerModeIsR0001Only(unittest.TestCase):
    """Sprint 13 Task H6 (audit H22): verdict_core's valve pointer mode compares against heap name
    pointers the table has no r0004 column for; --round-name-ptr refuses a log that is not r0001's."""

    def test_the_valves_chains_and_pointers_come_from_the_table(self):
        self.assertEqual(vc.VALVES["mp_round_count"].value_item, "*0x437ce8+0x0c*:2")
        self.assertEqual(vc.VALVES["mission_abort"].name_item, "*0x43668c*:3")
        for name, v in vc.VALVES.items():
            self.assertEqual(v.ours_name_ptr, ga.address("valve_name." + name, "r0001"), name)
            with self.assertRaises(ValueError):
                ga.address("valve_name." + name, "r0004")

    def test_the_refusal_reads_the_log_line_then_the_rows(self):
        r4 = ["[socom2] address table: the image names itself r0004 -- using the r0004 addresses"]
        self.assertIn("r0004", vc.pointer_mode_refusal(r4, []))
        r1 = ["[socom2] address table: the image names itself r0001 -- using the r0001 addresses"]
        self.assertIsNone(vc.pointer_mode_refusal(r1, []))
        rows_r4 = [(0.0, [(ga.address("guest_clock", "r0004"), [0])])]
        self.assertIn("r0004", vc.pointer_mode_refusal([], rows_r4))
        rows_r1 = [(0.0, [(ga.address("guest_clock", "r0001"), [0])])]
        self.assertIsNone(vc.pointer_mode_refusal([], rows_r1))

    def test_a_log_that_says_nothing_is_refused_not_assumed_r0001(self):
        self.assertIn("does not say", vc.pointer_mode_refusal([], []))
        self.assertIn("does not say", vc.pointer_mode_refusal([], [(0.0, [(0x01794000, [0])])]))


if __name__ == "__main__":
    unittest.main()
