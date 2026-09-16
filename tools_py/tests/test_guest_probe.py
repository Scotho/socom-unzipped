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


class RestWindow(unittest.TestCase):
    """s6_gamepad2 (2026-09-16): root_node_y read 5.0312 against the console's 5.5039 -- the settled median came from
    the LAST quarter of rows, after the mission script's holds (a muzzle-up hold, walks, a turn), where the pose is not
    the at-rest pose research/17 measured. The console number is the standing at-rest value seconds after spawn, so the
    probe reads its scalars from the REST window: rows REST_SKIP_ROWS..REST_SKIP_ROWS+REST_WINDOW_ROWS after the actor
    first appears (past the bind-pose decay, before any scripted hold)."""

    def test_scalars_come_from_the_rest_window_not_the_tail(self):
        rows = ([_line((900.0, -145.0, 850.0), root_y=11.48)] * 12                           # bind pose plateau
                + [_line((900.0, -145.0, 850.0), root_y=5.50391)] * (gp.REST_SETTLE_ROWS + gp.REST_WINDOW_ROWS)  # at rest
                + [_line((900.0, -145.0, 850.0), root_y=5.03)] * 40)                       # holds change the pose
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertTrue(res["root_node_y"].ok, res["root_node_y"].detail)
        # The lowest sustained plateau: the holds' pose here sits 0.47 lower than the at-rest value and wins, which
        # is inside the tolerance (1.5) and, unlike the tail median, never a decay stall (s6_lum8).
        self.assertAlmostEqual(res["root_node_y"].ours, 5.50391, delta=0.5)

    def test_a_gradual_decay_is_read_after_it_settles(self):
        """s6_water_state / s6_clut (2026-09-16): the root node decayed over ~25 rows (11.48 -> 10.98 -> ... -> 5.56) instead
        of stepping, and the window opened on the decay's first rows (10.407 read, console 5.5039). The window must open
        where consecutive rows stop moving (REST_SETTLE_DELTA), not where the value first leaves its initial plateau."""
        decay = [10.98, 10.98, 10.98, 10.41, 10.41, 9.63, 9.63, 7.88, 7.88, 7.12, 6.57, 6.16, 5.65]   # the 1 Hz sampler repeats values
        rows = ([_line((900.0, -145.0, 850.0), root_y=11.48)] * 12
                + [_line((900.0, -145.0, 850.0), root_y=v) for v in decay]
                + [_line((900.0, -145.0, 850.0), root_y=v) for v in (5.56, 5.56, 5.56, 5.56, 5.51, 5.51, 5.50, 5.50, 5.50, 5.48)]
                + [_line((900.0, -145.0, 850.0), root_y=8.2)] * 40)                        # holds raise it again
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertTrue(res["root_node_y"].ok, res["root_node_y"].detail)
        self.assertAlmostEqual(res["root_node_y"].ours, 5.5, delta=0.1)

    def test_a_long_stall_inside_the_decay_is_not_rest(self):
        """s6_lum8 (2026-09-16): the decay stalled for eight rows at 10.73 and nine at 6.83 before reaching 5.4-5.5 (the
        1 Hz sampler over a slow blend). Four quiet deltas accepted the first stall (10.732 read). The rest value is the
        LOWEST sustained plateau after the departure: the node decays down to rest and only later holds raise it."""
        series = ([11.48] * 12 + [11.43] * 3 + [10.73] * 8 + [9.2] * 2 + [8.32] * 3 + [6.83] * 9 + [5.98] * 3 + [5.73] * 4
                  + [5.53] * 12 + [5.5] * 9 + [5.44] * 4 + [5.39] * 15 + [5.55] * 8 + [5.8] * 18 + [6.21] * 11 + [6.5] * 15
                  + [7.5] * 11 + [7.91] * 19)
        rows = [_line((900.0, -145.0, 850.0), root_y=v) for v in series]
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertTrue(res["root_node_y"].ok, res["root_node_y"].detail)
        self.assertAlmostEqual(res["root_node_y"].ours, 5.45, delta=0.12)

    def test_a_short_log_falls_back_to_what_it_has(self):
        rows = [_line((900.0, -145.0, 850.0), root_y=5.50391)] * 5
        res = {r.name: r for r in gp.evaluate(rows, CONSOLE)}
        self.assertTrue(res["root_node_y"].ok, res["root_node_y"].detail)
