"""tools_py/overlay_repair.py against synthetic MIPS frames.

The defect the module exists for, reduced to two invented functions:

    0x00100000  addiu $sp,$sp,-0x40     the victim's prologue
    0x00100004  sd    $ra,0x20($sp)
    0x00100008  sq    $s1,0x10($sp)
    0x0010000c  sq    $s0,0x00($sp)
    ...
    0x00100020  ld    $ra,0x20($sp)
    0x00100024  jr    $ra               <- the foreign stub pair: should be lq $s1,0x10($sp)
    0x00100028  nop                     <-                       and  lq $s0,0x00($sp)
    0x0010002c  jr    $ra               the real return
    0x00100030  addiu $sp,$sp,0x40      which gives the frame back

Two returns back to back, the first without restoring $sp, is not code any compiler
emits; the two words it sits on are the restores of the registers the prologue saved.
The ordinary `jr $ra; nop` of an early return in front of a later `jr $ra` has all its
restores and must be left alone -- that shape occurs 65 times in the real overlays.
"""
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools_py import overlay_repair

BASE = 0x00100000
JR_RA = 0x03E00008
NOP = 0x00000000


def addiu_sp(delta):
    return 0x27BD0000 | (delta & 0xFFFF)


def mem(op, rt, off):
    return (op << 26) | (29 << 21) | (rt << 16) | (off & 0xFFFF)


SD_RA = mem(0x3F, 31, 0x20)
LD_RA = mem(0x37, 31, 0x20)
SQ_S1 = mem(0x1F, 17, 0x10)
SQ_S0 = mem(0x1F, 16, 0x00)
LQ_S1 = mem(0x1E, 17, 0x10)
LQ_S0 = mem(0x1E, 16, 0x00)


def image(words):
    return struct.pack("<%dI" % len(words), *words)


def broken_frame(tail=()):
    """The victim above: the two restores replaced by the stub's `jr $ra; nop`."""
    return [addiu_sp(-0x40), SD_RA, SQ_S1, SQ_S0, NOP,
            LD_RA, JR_RA, NOP, JR_RA, addiu_sp(0x40)] + list(tail)


def whole_frame():
    """The same frame with its restores intact, and an early return in front of them."""
    return [addiu_sp(-0x40), SD_RA, SQ_S1, SQ_S0, JR_RA, NOP, JR_RA, NOP,
            LD_RA, LQ_S1, LQ_S0, JR_RA, addiu_sp(0x40)]


class FindRepairsTest(unittest.TestCase):
    def test_the_stub_pair_over_two_restores_is_found_and_rebuilt_from_the_prologue(self):
        repairs = overlay_repair.find_repairs(image(broken_frame()), BASE)
        self.assertEqual([(r.address, r.before, r.after) for r in repairs],
                         [(BASE + 0x18, JR_RA, LQ_S1), (BASE + 0x1C, NOP, LQ_S0)])
        self.assertEqual({r.function for r in repairs}, {BASE})

    def test_the_repaired_image_holds_the_restores_and_nothing_else_moves(self):
        before = image(broken_frame())
        after, repairs = overlay_repair.apply_repairs(before, BASE)
        self.assertEqual(len(repairs), 2)
        self.assertEqual(after[:0x18], before[:0x18])
        self.assertEqual(after[0x20:], before[0x20:])
        self.assertEqual(struct.unpack_from("<2I", after, 0x18), (LQ_S1, LQ_S0))

    def test_an_early_return_in_front_of_a_complete_epilogue_is_left_alone(self):
        data = image(whole_frame())
        self.assertEqual(overlay_repair.find_repairs(data, BASE), [])
        self.assertEqual(overlay_repair.apply_repairs(data, BASE), (data, []))

    def test_a_frame_missing_only_one_restore_is_not_touched(self):
        """Two words were overwritten; one missing restore means this is some other shape."""
        words = [addiu_sp(-0x40), SD_RA, SQ_S1, NOP, NOP,
                 LD_RA, JR_RA, NOP, JR_RA, addiu_sp(0x40)]
        self.assertEqual(overlay_repair.find_repairs(image(words), BASE), [])

    def test_a_return_that_does_not_give_the_frame_back_is_not_the_real_one(self):
        words = broken_frame()
        words[9] = NOP                       # the second jr $ra's delay slot is not addiu $sp
        self.assertEqual(overlay_repair.find_repairs(image(words), BASE), [])

    def test_a_frame_whose_prologue_takes_a_different_amount_is_not_matched(self):
        words = broken_frame()
        words[0] = addiu_sp(-0x30)           # prologue -0x30 against an epilogue of +0x40
        self.assertEqual(overlay_repair.find_repairs(image(words), BASE), [])

    def test_a_stub_pair_with_no_prologue_above_it_is_not_matched(self):
        words = [NOP, LD_RA, JR_RA, NOP, JR_RA, addiu_sp(0x40)]
        self.assertEqual(overlay_repair.find_repairs(image(words), BASE), [])

    def test_the_search_for_a_prologue_stops_at_the_start_and_does_not_wrap(self):
        """A prologue-shaped word at the end of the segment is not above the stub pair."""
        words = [NOP, LD_RA, JR_RA, NOP, JR_RA, addiu_sp(0x40), SD_RA, SQ_S1, SQ_S0, addiu_sp(-0x40)]
        self.assertEqual(overlay_repair.find_repairs(image(words), BASE), [])

    def test_the_address_and_slot_reported_are_the_ones_rewritten(self):
        r = overlay_repair.find_repairs(image(broken_frame()), BASE)[0]
        self.assertEqual((r.register, r.slot), (17, 0x10))
        self.assertIn("0x00100018", r.describe())

    def test_two_broken_frames_in_one_segment_are_both_repaired(self):
        words = broken_frame() + [NOP] * 4 + broken_frame()
        after, repairs = overlay_repair.apply_repairs(image(words), BASE)
        self.assertEqual(len(repairs), 4)
        self.assertEqual(struct.unpack_from("<2I", after, 0x18), (LQ_S1, LQ_S0))
        self.assertEqual(struct.unpack_from("<2I", after, (14 + 6) * 4), (LQ_S1, LQ_S0))


class SegmentsTest(unittest.TestCase):
    def test_an_mwo3_overlay_is_read_at_its_own_load_address(self):
        import tempfile
        header = b"MWo3" + struct.pack("<7I", 1, BASE, 0x40, 0, 0, 0, 0) + bytes(0x80 - 0x20)
        body = image(broken_frame())
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "over.bin")
            with open(path, "wb") as fh:
                fh.write(header + body)
            segs = overlay_repair._segments(path)
        self.assertEqual(len(segs), 1)
        va, data, executable = segs[0]
        self.assertEqual((va, executable), (BASE, True))
        # the header is part of the load, so the frame sits 0x80 in
        self.assertEqual([r.address for r in overlay_repair.find_repairs(data, va)],
                         [BASE + 0x80 + 0x18, BASE + 0x80 + 0x1C])


if __name__ == "__main__":
    unittest.main()
