"""guest_probe: the gate's guest-value leg (Sprint 6 Task 1c) -- a handful of guest values read from the mission
stage's [peek] rows and compared with console numbers on disk (scripts/parity/guest_probe_console.json)."""
import json
import unittest

from tools_py.parity import guest_probe as gp
from tools_py.parity.sim_walk_to_b import peek_line, _w

ACTOR = 0x01794000
NODE = 0x00C10000
CONSOLE = "scripts/parity/guest_probe_console.json"


def _line(pos, root_y=5.50391, move_scale=1.0):
    """One peek row: camera, the actor block (vtable + position), the node item and the MoveScale item."""
    line = peek_line(500.0, 100.0, 600.0, actor=pos, actor_addr=ACTOR)
    line += f" @{ACTOR + 0x2e8:x}: {NODE:08x}(0)"
    line += f" @{NODE:x}: 00000000(0) {_w(root_y)}"
    line += f" @{ACTOR + 0x1368:x}: {_w(move_scale)}"
    return line


class Evaluate(unittest.TestCase):
    def test_console_like_rows_pass_every_check(self):
        rows = [_line((900.0 + 2.0 * i, -145.0, 850.0)) for i in range(10)]
        res = gp.evaluate(rows, CONSOLE)
        self.assertEqual({r.name: r.ok for r in res}, {"root_node_y": True, "move_scale": True, "teleport_steps": True})

    def test_decayed_root_node_fails_only_that_check(self):
        rows = [_line((900.0, -145.0, 850.0), root_y=0.0)] * 5
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertFalse(res["root_node_y"].ok)
        self.assertAlmostEqual(res["root_node_y"].ours, 0.0)
        self.assertTrue(res["move_scale"].ok)
        self.assertTrue(res["teleport_steps"].ok)

    def test_a_two_hundred_unit_jump_counts_one_teleport(self):
        rows = [_line((900.0, -145.0, 850.0))] * 3 + [_line((1100.0, -145.0, 850.0))] * 3
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertEqual(res["teleport_steps"].ours, 1)
        self.assertFalse(res["teleport_steps"].ok)

    def test_a_run_at_forty_units_per_second_is_not_a_teleport(self):
        # s6_probe: the 8 s forward hold moved ~36-45 units per 1 s sampler row along one axis -- a run, not a
        # jump. research/25 §1.1's 30-unit bar was per 4 Hz row (> 120 u/s); at the gate's 1 s rows it is 120 units.
        rows = [_line((939.4, -146.5, 862.5 + 40.0 * i)) for i in range(9)]
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertEqual(res["teleport_steps"].ours, 0)
        self.assertTrue(res["teleport_steps"].ok)

    def test_the_guest_clock_sets_the_row_period_when_present(self):
        # The same 40-unit steps at 0.25 s rows (the ladder's cadence) are 160 u/s: teleports.
        rows = [_line((939.4, -146.5, 862.5 + 40.0 * i)) + f" @4365c0: {_w(100.0 + 0.25 * i)}" for i in range(9)]
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertEqual(res["teleport_steps"].ours, 8)

    def test_missing_read_is_no_data_not_a_pass(self):
        rows = [peek_line(500.0, 100.0, 600.0, actor=(900.0, -145.0, 850.0), actor_addr=ACTOR)] * 3   # no node, no scale
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertIsNone(res["root_node_y"].ours)
        self.assertFalse(res["root_node_y"].ok)
        self.assertIn("NO-DATA", res["root_node_y"].detail)

    def test_root_node_uses_the_last_rows_not_the_first(self):
        # The bind-pose value decays over the first seconds (research/17 §4.1): the probe reads the settled value.
        rows = [_line((900.0, -145.0, 850.0), root_y=11.48)] * 3 + [_line((900.0, -145.0, 850.0), root_y=0.0)] * 7
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertFalse(res["root_node_y"].ok)

    def test_peek_spec_lists_every_chain_once(self):
        spec = gp.peek_spec(CONSOLE)
        with open(CONSOLE) as f:
            entries = [c for k, v in json.load(f).items() if not k.startswith("_") for c in v["peek"].split(",")]
        for chain in entries:
            self.assertIn(chain, spec.split(","))
        self.assertIn("0x416054:3", spec.split(","))


if __name__ == "__main__":
    unittest.main()
