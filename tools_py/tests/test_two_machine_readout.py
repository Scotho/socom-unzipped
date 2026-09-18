"""Sprint 7 Task 5: the two-machine readout (tools_py/parity/two_machine_readout.py).

Every `[peek]` row below is a REAL row out of the 2026-09-17 two-instance control round
(`logs/run_A_20260917_155520.log` / `logs/run_B_20260917_155520.log`,
`logs/parity/ours_control_foxhunt_guard/`), reduced the way this repo's other log fixtures are
(tools_py/tests/fixtures/online/README.md): a row keeps only the item whose word 0 is the actor
vtable `006691a0` -- and only its first 10 words, 7/8/9 being x/y/z -- and the `@408f10` round-clock
item. Addresses, word order and every `hex(float)` token are verbatim. The two RESULT lines are
verbatim drive-log messages (`logs/parity/drive_ours_control_foxhunt_guard.txt` and
`logs/parity/drive_s6_ladder4.txt`), minus Shell.log's time-and-tag prefix -- which is exactly what a
single machine's own log carries.
"""
import unittest

from tools_py.parity import two_machine_readout as tmr

# The first row of either run log: the sampler is running, nothing has resolved yet -- no actor item,
# and `@408f10` is all zeros, so no clock string. A round in which neither side ever moved.
ZERO = ("[peek] @416054: 00000000(0) 00000000(0) 00000000(0) @4365c0: 00000000(0) @45a0c0: 00000000(0) "
        "@3df1b0: 00000001(1.4013e-45) @45a1c8: 00000000(0) @408f10: 00000000(0) 00000000(0) "
        "@408c58: 00000000(0) 00000000(0) 00000000(0) 00000000(0)")

# The control round's own RESULT line, and a real lobby failure from a Sprint 6 ladder.
RESULT = ("RESULT CONTROL-ROUND round_ended=yes kills_stepped=0 "
          "aiteam_stepped=A:aiteam_00=0,A:aiteam_08=0,B:aiteam_00=0,B:aiteam_08=0 health_min=1,1 "
          "health_changes=0,0 alive_changed=0,0 signal=clock00:01->00:00 on=A fall_damage=B:0 "
          "harness=2ef451fa9e3e-live exe=a04af956c091ceb0")
LOBBY_FAIL = ("RESULT LOBBY-FAIL login:keyboard-enter -- keyboard still up after ENTER and 2 re-presses "
              "(5 of 5 characters)")

A = [ZERO, RESULT]
B = [ZERO, RESULT]

# A's actor at the round's first clock row (05:59) and at 02:00: (3403.56, 4880.99) -> (3657.17, 4929.95),
# 258.3 units across the ground plane.
A_0559 = ("[peek] @16fce60: 006691a0(9.41946e-39) 00000003(4.2039e-45) 00000000(0) 00000000(0) "
          "00000002(2.8026e-45) 006f7bd8(1.02382e-38) 00000000(0) 4554b8f1(3403.56) 42ed6666(118.7) "
          "459887f0(4880.99) @408f10: 353a3530(6.93678e-07) 00000039(7.9874e-44)")
A_0200 = ("[peek] @16fce60: 006691a0(9.41946e-39) 00000003(4.2039e-45) 00000000(0) 00000000(0) "
          "00000002(2.8026e-45) 006f7bd8(1.02382e-38) 00000000(0) 456492ad(3657.17) 42fefc66(127.493) "
          "459a0f9f(4929.95) @408f10: 303a3230(6.77377e-10) 00000030(6.72623e-44)")
# B's actor at ITS first clock row (05:59, ~5 s earlier in host time) and at 01:58:
# (3214.46, 1839.21) -> (2805.60, 1754.87), 417.5 units.
B_0559 = ("[peek] @16fe230: 006691a0(9.41946e-39) 00000066(1.42932e-43) 00000000(0) 00000000(0) "
          "00000002(2.8026e-45) 006f7bd8(1.02382e-38) 00000000(0) 4548e759(3214.46) 433b2333(187.137) "
          "44e5e69d(1839.21) @408f10: 353a3530(6.93678e-07) 00000039(7.9874e-44)")
B_0158 = ("[peek] @16fe230: 006691a0(9.41946e-39) 00000066(1.42932e-43) 00000000(0) 00000000(0) "
          "00000002(2.8026e-45) 006f7bd8(1.02382e-38) 00000000(0) 452f59a3(2805.6) 42261ccc(41.5281) "
          "44db5bdc(1754.87) @408f10: 353a3130(6.9362e-07) 00000038(7.84727e-44)")


class Readout(unittest.TestCase):
    def test_a_round_where_neither_side_moved_reports_no_peer_movement(self):
        out = tmr.read_lines(A, B)
        self.assertFalse(out["saw_peer_move"]["A"])
        self.assertFalse(out["saw_peer_move"]["B"])

    def test_both_sides_walking_reads_as_each_seeing_the_other_move(self):
        """The positive control: a False that a `return False` would also give proves nothing."""
        out = tmr.read_lines([A_0559, A_0200], [B_0559, B_0158])
        self.assertTrue(out["saw_peer_move"]["A"])
        self.assertTrue(out["saw_peer_move"]["B"])
        self.assertAlmostEqual(out["peer_move_units"]["A"], 417.5, delta=1.0)   # A's peer is B
        self.assertAlmostEqual(out["peer_move_units"]["B"], 258.3, delta=1.0)

    def test_clock_skew_is_the_difference_of_the_round_clocks(self):
        a = A + [A_0200]
        b = B + [B_0158]
        self.assertAlmostEqual(tmr.read_lines(a, b)["clock_skew_s"], 2.0, places=1)

    def test_a_lobby_failure_carries_its_class(self):
        out = tmr.read_lines([LOBBY_FAIL], B)
        self.assertEqual(out["classes"]["A"], "login:keyboard-enter")


if __name__ == "__main__":
    unittest.main()
