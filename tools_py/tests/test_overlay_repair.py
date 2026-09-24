"""tools_py/overlay_repair.py -- the capsule-stack-driven undo, on synthetic images and the real ones.

The defect, reduced to one invented function.  The victim at 0x00100000 is a frame that saves $s1
and $s0 and, in the r0004 image, has the two `lq` that restore them overwritten by a capsule stub
pair (`jr $ra` + `nop`); the r0001 twin at 0x00200000 is the same function with the two `lq` intact.

    0x00100000  addiu $sp,$sp,-0x40      0x00100014  ld    $ra,0x20($sp)
    0x00100004  sd    $ra,0x20($sp)      0x00100018  jr    $ra    <- capsule: 0x03E00008
    0x00100008  sq    $s1,0x10($sp)      0x0010001c  nop          <- capsule: 0x00000000
    0x0010000c  sq    $s0,0x00($sp)      0x00100020  jr    $ra
    0x00100010  nop                      0x00100024  addiu $sp,$sp,0x40

Nothing in the module looks for that shape.  An address is a candidate only because the capsule's
decoded write stack names it, and it fires only because the image already holds the value the
capsule writes there -- so table 2 (whose target is an untouched prologue in our image) must be a
measured no-op, and an r0001 build, which has no stack at all, cannot be touched.
"""
import json
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools_py import make_overlay_elf, overlay_repair

BASE = 0x00100000
TWIN_BASE = 0x00200000
JR_RA = 0x03E00008
NOP = 0x00000000
STUB = [(BASE + 0x18, JR_RA), (BASE + 0x1C, NOP)]


def addiu_sp(delta):
    return 0x27BD0000 | (delta & 0xFFFF)


def mem(op, rt, off):
    return (op << 26) | (29 << 21) | (rt << 16) | (off & 0xFFFF)


SD_RA, LD_RA = mem(0x3F, 31, 0x20), mem(0x37, 31, 0x20)
SQ_S1, LQ_S1 = mem(0x1F, 17, 0x10), mem(0x1E, 17, 0x10)
SQ_S0, LQ_S0 = mem(0x1F, 16, 0x00), mem(0x1E, 16, 0x00)


def image(words):
    return struct.pack("<%dI" % len(words), *words)


def victim(tail_two):
    return [addiu_sp(-0x40), SD_RA, SQ_S1, SQ_S0, NOP,
            LD_RA, tail_two[0], tail_two[1], JR_RA, addiu_sp(0x40)]


BROKEN = victim((JR_RA, NOP))            # what the r0004 image holds
WHOLE = victim((LQ_S1, LQ_S0))           # what the r0001 twin holds


def make(words, base=BASE):
    return overlay_repair.Image().add(base, image(words))


def rows(base, length):
    return [(base, base + length)]


class StackDrivenTest(unittest.TestCase):
    """Axis 1: what makes an address a candidate at all."""

    def plan(self, img_words, writes=STUB, twin_words=None, base=BASE):
        twin = make(twin_words if twin_words is not None else WHOLE, TWIN_BASE)
        return overlay_repair.plan_repairs(make(img_words, base), writes, twin,
                                           rows(base, len(img_words) * 4),
                                           rows(TWIN_BASE, len(WHOLE) * 4))

    def test_a_capsule_write_the_image_already_holds_is_repaired_from_the_twin(self):
        repairs, notes = self.plan(BROKEN)
        self.assertEqual([(r.address, r.before, r.after) for r in repairs],
                         [(BASE + 0x18, JR_RA, LQ_S1), (BASE + 0x1C, NOP, LQ_S0)])
        self.assertEqual([r.twin_function for r in repairs], [TWIN_BASE, TWIN_BASE])
        self.assertEqual([r.cross_check for r in repairs], ["agrees", "agrees"])
        self.assertEqual(notes, [])

    def test_no_capsule_stack_means_no_candidate_and_no_repair(self):
        """The r0001 build path: inert by construction, not by a filter."""
        self.assertEqual(overlay_repair.plan_repairs(make(BROKEN), []), ([], []))
        self.assertEqual(overlay_repair.plan_repairs(make(BROKEN), None), ([], []))

    def test_a_capsule_target_the_image_does_not_hold_is_a_measured_no_op(self):
        """Table 2: its target is an untouched prologue in our image, so it must not fire."""
        repairs, notes = self.plan(WHOLE)
        self.assertEqual(repairs, [])
        self.assertEqual(len(notes), 2)
        self.assertIn("not baked in, no-op", notes[0])
        self.assertIn("0x00100018", notes[0])

    def test_the_repair_is_idempotent(self):
        data = image(BROKEN)
        twin = make(WHOLE, TWIN_BASE)
        once, repairs, _n = overlay_repair.apply_repairs(
            data, BASE, STUB, twin, rows(BASE, len(BROKEN) * 4), rows(TWIN_BASE, len(WHOLE) * 4))
        self.assertEqual(len(repairs), 2)
        twice, again, notes = overlay_repair.apply_repairs(
            once, BASE, STUB, twin, rows(BASE, len(BROKEN) * 4), rows(TWIN_BASE, len(WHOLE) * 4))
        self.assertEqual(twice, once)
        self.assertEqual(again, [])
        self.assertEqual(len(notes), 2)

    def test_a_target_outside_the_text_window_is_never_considered(self):
        """A capsule address that lands in the overlay's rodata is not this segment's business."""
        img = overlay_repair.Image().add(BASE, image(BROKEN), BASE, BASE + 0x10)
        self.assertEqual(overlay_repair.plan_repairs(img, STUB), ([], []))

    def test_a_fired_write_with_no_twin_to_resolve_it_refuses_loudly(self):
        with self.assertRaises(overlay_repair.RepairError) as ctx:
            overlay_repair.plan_repairs(make(BROKEN), STUB)
        self.assertIn("no twin image", str(ctx.exception))

    def test_a_fired_write_outside_every_map_row_refuses(self):
        twin = make(WHOLE, TWIN_BASE)
        with self.assertRaises(overlay_repair.RepairError) as ctx:
            overlay_repair.plan_repairs(make(BROKEN), STUB, twin, [], rows(TWIN_BASE, 40))
        self.assertIn("no row of the revision's function map", str(ctx.exception))


class TwinTest(unittest.TestCase):
    """Axis 2: where the replacement words come from, and what must hold afterwards."""

    def test_no_matching_twin_refuses_rather_than_inventing_words(self):
        other = [addiu_sp(-0x40), SD_RA, SQ_S1, SQ_S0, NOP, LD_RA, LQ_S1, LQ_S0,
                 JR_RA, addiu_sp(0x30)]          # differs outside the masked words
        twin = make(other, TWIN_BASE)
        with self.assertRaises(overlay_repair.RepairError) as ctx:
            overlay_repair.plan_repairs(make(BROKEN), STUB, twin, rows(BASE, 40), rows(TWIN_BASE, 40))
        self.assertIn("no r0001 twin", str(ctx.exception))

    def test_two_twins_that_disagree_on_the_replacement_refuse(self):
        twin = overlay_repair.Image().add(TWIN_BASE, image(WHOLE) + image(victim((LQ_S0, LQ_S1))))
        twin_rows = [(TWIN_BASE, TWIN_BASE + 40), (TWIN_BASE + 40, TWIN_BASE + 80)]
        with self.assertRaises(overlay_repair.RepairError) as ctx:
            overlay_repair.plan_repairs(make(BROKEN), STUB, twin, rows(BASE, 40), twin_rows)
        self.assertIn("disagree on the replacement words", str(ctx.exception))

    def test_the_whole_body_matches_the_twin_after_the_restore(self):
        data = image(BROKEN)
        twin = make(WHOLE, TWIN_BASE)
        out, repairs, _n = overlay_repair.apply_repairs(
            data, BASE, STUB, twin, rows(BASE, 40), rows(TWIN_BASE, 40))
        self.assertEqual(len(repairs), 2)
        self.assertEqual(out, image(WHOLE))

    def test_a_twin_row_shorter_than_the_image_function_must_match_past_its_own_end(self):
        """The compare runs over max(image row, twin row): a prefix match is not a twin."""
        prefix_only = WHOLE[:7] + [NOP, NOP, NOP]      # agrees for 28 B, diverges after
        twin = make(prefix_only, TWIN_BASE)
        with self.assertRaises(overlay_repair.RepairError) as ctx:
            overlay_repair.plan_repairs(make(BROKEN), STUB, twin, rows(BASE, 40),
                                        [(TWIN_BASE, TWIN_BASE + 28)])
        self.assertIn("no r0001 twin", str(ctx.exception))

    def test_a_twin_whose_row_is_short_but_whose_body_matches_is_accepted_over_the_longer_window(self):
        twin = make(WHOLE, TWIN_BASE)                  # 40 B of body behind a 28 B row
        repairs, _notes = overlay_repair.plan_repairs(make(BROKEN), STUB, twin, rows(BASE, 40),
                                                      [(TWIN_BASE, TWIN_BASE + 28)])
        self.assertEqual([r.after for r in repairs], [LQ_S1, LQ_S0])
        self.assertEqual({r.twin_bytes for r in repairs}, {40})

    def test_a_twin_window_too_short_to_identify_is_not_used(self):
        short = [addiu_sp(-0x40), SD_RA, SQ_S1, SQ_S0, NOP]
        twin = make(short, TWIN_BASE)
        with self.assertRaises(overlay_repair.RepairError):
            overlay_repair.plan_repairs(make(BROKEN), STUB, twin, rows(BASE, 40),
                                        rows(TWIN_BASE, len(short) * 4))


class CrossCheckTest(unittest.TestCase):
    """Axis 3: the prologue-implied reconstruction can veto, never supply."""

    def test_a_twin_that_contradicts_the_frame_s_own_prologue_refuses(self):
        """The twin says restore $s2/$s3; the frame only ever saved $s1/$s0."""
        liar = victim((mem(0x1E, 18, 0x10), mem(0x1E, 19, 0x00)))
        twin = make(liar, TWIN_BASE)
        with self.assertRaises(overlay_repair.RepairError) as ctx:
            overlay_repair.plan_repairs(make(BROKEN), STUB, twin, rows(BASE, 40), rows(TWIN_BASE, 40))
        self.assertIn("refusing", str(ctx.exception))

    def test_a_64_bit_spill_reloaded_as_32_bits_is_not_a_missing_restore(self):
        """The false positive the shape rule had: sd $a0 / lw $a0 is a well-formed frame."""
        body = [addiu_sp(-0x40), SD_RA, SQ_S0, mem(0x3F, 4, 0x30), mem(0x3F, 5, 0x38),
                mem(0x23, 4, 0x30), mem(0x23, 5, 0x38), LQ_S0, LD_RA, NOP]
        self.assertEqual(overlay_repair.implied_restores(image(body), []), [])

    def test_a_missing_restore_of_a_caller_saved_register_is_not_a_frame_the_check_can_read(self):
        body = [addiu_sp(-0x40), SD_RA, mem(0x3F, 4, 0x30), NOP, NOP, LD_RA, NOP, NOP, NOP, NOP]
        self.assertIsNone(overlay_repair.implied_restores(image(body), []))

    def test_the_check_reads_a_daddiu_framed_prologue_too(self):
        body = list(BROKEN)
        body[0] = 0x67BD0000 | (-0x40 & 0xFFFF)          # daddiu $sp,$sp,-0x40
        self.assertEqual(overlay_repair.implied_restores(image(body), [0x18, 0x1C]),
                         [LQ_S1, LQ_S0])

    def test_a_duplicated_save_does_not_imply_two_restores(self):
        body = [addiu_sp(-0x40), SD_RA, SQ_S1, SQ_S1, NOP, LD_RA, NOP, NOP, JR_RA, addiu_sp(0x40)]
        self.assertEqual(overlay_repair.implied_restores(image(body), [0x18, 0x1C]), [LQ_S1])


class StackParsingTest(unittest.TestCase):
    def test_a_decoded_stack_is_read_into_the_capsule_s_pair_tables(self):
        base = 0x80099250
        lines = []
        for i, (a, v) in enumerate([(0x00ABC670, JR_RA), (0x00ABC674, NOP)]):
            lines.append("w %08X %08X" % (base + i * 8, a))
            lines.append("w %08X %08X" % (base + i * 8 + 4, v))
        lines.append("w %08X %08X" % (base + 16, 0))
        lines.append("w %08X %08X" % (base + 20, 0))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "stack.txt")
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(lines) + "\n")
            writes = overlay_repair.read_stack(path)
            self.assertEqual(len(writes), 6)
            self.assertEqual(overlay_repair.stub_writes(writes),
                             [(0x00ABC670, JR_RA), (0x00ABC674, NOP)])


class SidecarFreshnessTest(unittest.TestCase):
    """`<elf>.repair.json` records the sha256 of everything the answer depends on, and the next
    build compares them. An mtime against two modules saw neither a re-decoded capsule stack nor a
    new function map, both of which change an answer the merged ELF has already baked in."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.input = os.path.join(self.tmp.name, "stack.txt")
        with open(self.input, "w", encoding="utf-8") as fh:
            fh.write("w 80031250 002CC670\n")
        self.log = os.path.join(self.tmp.name, "merged.elf.repair.json")

    def write(self):
        overlay_repair.write_log(self.log, [], [], overlay_repair.source_digests({"stub-writes": self.input}))

    def test_a_sidecar_written_from_the_same_inputs_is_current(self):
        self.write()
        current, why = overlay_repair.log_is_current(
            self.log, overlay_repair.source_digests({"stub-writes": self.input}))
        self.assertTrue(current, why)
        self.assertIn("match the sha256", why)

    def test_an_input_that_changed_under_the_image_makes_it_stale(self):
        self.write()
        with open(self.input, "a", encoding="utf-8") as fh:
            fh.write("w 80031258 002CC674\n")
        current, why = overlay_repair.log_is_current(
            self.log, overlay_repair.source_digests({"stub-writes": self.input}))
        self.assertFalse(current)
        self.assertIn("stub-writes changed", why)

    def test_a_different_set_of_inputs_makes_it_stale(self):
        self.write()
        current, why = overlay_repair.log_is_current(self.log, overlay_repair.source_digests({}))
        self.assertFalse(current)
        self.assertIn("set of repair inputs changed", why)

    def test_a_malformed_sidecar_is_stale_rather_than_a_traceback(self):
        with open(self.log, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        current, why = overlay_repair.log_is_current(self.log, overlay_repair.source_digests({}))
        self.assertFalse(current)
        self.assertIn("could not be read", why)

    def test_a_missing_sidecar_is_stale(self):
        current, why = overlay_repair.log_is_current(
            os.path.join(self.tmp.name, "nope.json"), overlay_repair.source_digests({}))
        self.assertFalse(current)
        self.assertIn("could not be read", why)

    def test_the_three_modules_that_decide_are_hashed_alongside_the_data(self):
        digests = overlay_repair.source_digests({"stub-writes": self.input})
        self.assertEqual(sorted(digests),
                         ["capsule.py", "make_overlay_elf.py", "overlay_repair.py", "stub-writes"])
        for name, entry in digests.items():
            self.assertEqual(len(entry["sha256"]), 64, name)

    def test_an_input_that_does_not_exist_is_recorded_as_absent_and_compares_equal(self):
        gone = os.path.join(self.tmp.name, "not-there")
        digests = overlay_repair.source_digests({"twin": gone})
        self.assertIsNone(digests["twin"]["sha256"])
        overlay_repair.write_log(self.log, [], [], digests)
        current, why = overlay_repair.log_is_current(self.log, overlay_repair.source_digests({"twin": gone}))
        self.assertTrue(current, why)


# ---- the make_overlay_elf integration -------------------------------------------------------------

def loader_elf(segments):
    """A minimal ELF with one PT_LOAD per (vaddr, bytes)."""
    ehsize, phentsize = 52, 32
    off = ehsize + phentsize * len(segments)
    hdr = bytearray(bytes.fromhex("7f454c46010101") + bytes(9))
    hdr += struct.pack("<HHIIIIIHHHHHH", 2, 8, 1, segments[0][0], ehsize, 0, 0, ehsize,
                       phentsize, len(segments), 0, 0, 0)
    body = b""
    for va, data in segments:
        hdr += struct.pack("<8I", 1, off + len(body), va, va, len(data), len(data), 7, 0x1000)
        body += data
    return bytes(hdr) + body


def mwo3(load, text_words, data_bytes=b""):
    text = image(text_words)
    header = b"MWo3" + struct.pack("<7I", 1, load, len(text), len(data_bytes), 0, 0, 0)
    header += bytes(0x20 - len(header)) + b"ftscore\0" + bytes(0x40 - 0x28)
    return header + bytes(0x80 - len(header)) + text + data_bytes


class BuildIntegrationTest(unittest.TestCase):
    def build(self, tmp, **kw):
        loader = os.path.join(tmp, "SCUS_972.75")
        overlay = os.path.join(tmp, "over.bin")
        out = os.path.join(tmp, "merged.elf")
        with open(loader, "wb") as fh:
            fh.write(loader_elf([(0x00080000, image([NOP] * 8))]))
        with open(overlay, "wb") as fh:
            fh.write(mwo3(BASE - 0x80, BROKEN, b"\x08\x00\xe0\x03" * 4))
        twin_path = os.path.join(tmp, "twin.elf")
        with open(twin_path, "wb") as fh:
            fh.write(loader_elf([(TWIN_BASE, image(WHOLE))]))
        kw.setdefault("stub_writes", STUB)
        kw.setdefault("twin", overlay_repair.Image.from_file(twin_path))
        kw.setdefault("rows", rows(BASE, 40))
        kw.setdefault("twin_rows", rows(TWIN_BASE, 40))
        repairs = make_overlay_elf.build(out, loader, [overlay], None, **kw)
        return out, repairs

    def test_the_overlay_text_is_repaired_and_the_sidecar_records_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, repairs = self.build(tmp)
            self.assertEqual([r.address for r in repairs], [BASE + 0x18, BASE + 0x1C])
            merged = overlay_repair.Image.from_file(out)
            self.assertEqual(merged.word(BASE + 0x18), LQ_S1)
            self.assertEqual(merged.word(BASE + 0x1C), LQ_S0)
            with open(out + ".repair.json", "r", encoding="utf-8") as fh:
                log = json.load(fh)
            self.assertEqual([r["address"] for r in log["repairs"]], ["0x00100018", "0x0010001C"])
            self.assertEqual(log["repairs"][0]["after"], "0x7BB10010")

    def test_without_a_capsule_stack_the_merged_elf_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            repaired, _r = self.build(tmp)
            with open(repaired, "rb") as fh:
                with_repair = fh.read()
        with tempfile.TemporaryDirectory() as tmp:
            plain, repairs = self.build(tmp, stub_writes=None)
            self.assertEqual(repairs, [])
            with open(plain, "rb") as fh:
                without = fh.read()
            self.assertTrue(os.path.isfile(plain + ".repair.json"))
        self.assertNotEqual(with_repair, without)
        self.assertEqual(struct.unpack_from("<I", without, without.index(image(BROKEN)) + 0x18)[0], JR_RA)

    def test_a_non_executable_segment_is_not_scanned(self):
        """boot.data is RW-; a capsule address inside it must not be rewritten."""
        with tempfile.TemporaryDirectory() as tmp:
            loader = os.path.join(tmp, "SCUS_972.75")
            overlay = os.path.join(tmp, "over.bin")
            out = os.path.join(tmp, "merged.elf")
            with open(loader, "wb") as fh:                # 0x80000..0x80028, text ends at 0x80008
                fh.write(loader_elf([(0x00080000, image(BROKEN))]))
            with open(overlay, "wb") as fh:
                fh.write(mwo3(BASE - 0x80, [NOP] * 10))
            repairs = make_overlay_elf.build(
                out, loader, [overlay], 0x00080008,
                stub_writes=[(0x00080018, JR_RA), (0x0008001C, NOP)],
                twin=make(WHOLE, TWIN_BASE), rows=rows(0x00080000, 40), twin_rows=rows(TWIN_BASE, 40))
            self.assertEqual(repairs, [])
            # Image.from_file reads only executable PT_LOADs, so read the RW- segment's bytes back
            # out of the merged file directly.
            with open(out, "rb") as fh:
                merged = fh.read()
            self.assertIn(image(BROKEN)[0x18:0x20], merged)
            self.assertNotIn(struct.pack("<2I", LQ_S1, LQ_S0), merged)


# ---- the real images ----------------------------------------------------------------------------

R0001_ELF = os.path.join(ROOT, "game", "disc", "socom2_game.elf")
R0004_FTSCORE = os.path.join(ROOT, "game", "overlays_r0004", "ftscore.bin")
R0004_STACK = os.path.join(ROOT, "game", "r0004", "decoded", "stack.txt")
R0004_ROWS = os.path.join(ROOT, "recomp", "socom2_ghidra_r0004.csv")
R0001_ROWS = os.path.join(ROOT, "recomp", "socom2_ghidra.csv")


@unittest.skipUnless(all(os.path.isfile(p) for p in (R0001_ELF, R0004_STACK, R0001_ROWS)),
                     "the game bytes are not in this tree")
class RealImageTest(unittest.TestCase):
    """The invariants the report claims, asserted instead of measured by hand."""

    @classmethod
    def setUpClass(cls):
        cls.writes = overlay_repair.stub_writes(overlay_repair.read_stack(R0004_STACK))
        cls.twin = overlay_repair.Image.from_file(R0001_ELF)
        cls.twin_rows = overlay_repair.read_rows(R0001_ROWS)

    def test_the_capsule_stack_carries_the_two_stub_tables(self):
        self.assertEqual(self.writes, [(0x002CC670, JR_RA), (0x002CC674, NOP),
                                       (0x002CF330, JR_RA), (0x002CF334, NOP)])

    def test_the_r0001_image_is_untouched_by_the_r0004_capsule_s_own_addresses(self):
        """The player-facing lane: zero repairs even when handed the r0004 stack."""
        rows_r4 = overlay_repair.read_rows(R0004_ROWS) if os.path.isfile(R0004_ROWS) else []
        repairs, _notes = overlay_repair.plan_repairs(self.twin, self.writes, self.twin,
                                                      rows_r4, self.twin_rows)
        self.assertEqual(repairs, [])

    @unittest.skipUnless(os.path.isfile(R0004_FTSCORE) and os.path.isfile(R0004_ROWS),
                         "the r0004 overlay is not in this tree")
    def test_the_r0004_overlay_yields_exactly_the_two_known_words(self):
        image_r4 = overlay_repair.Image.from_file(R0004_FTSCORE)
        repairs, notes = overlay_repair.plan_repairs(
            image_r4, self.writes, self.twin, overlay_repair.read_rows(R0004_ROWS), self.twin_rows)
        self.assertEqual({r.address: r.after for r in repairs},
                         {0x002CC670: 0x7BB10010, 0x002CC674: 0x7BB00000})
        self.assertEqual({r.twin_function for r in repairs}, {0x0022E560})
        self.assertEqual({r.cross_check for r in repairs}, {"agrees"})
        self.assertEqual(len(notes), 2)                  # table 2, twice: a measured no-op


if __name__ == "__main__":
    unittest.main()
