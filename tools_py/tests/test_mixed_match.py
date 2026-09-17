"""Sprint 6 Task 7: the mixed match's pure pieces -- the PCSX2 controller's macro plans, the host's wait for a
foreign joiner, and the console-side motion verdict over window captures."""
import unittest

import numpy as np

from tools_py.parity import motion_diff
from tools_py.parity import online_match_ours as M


class Pcsx2PlanTest(unittest.TestCase):
    def test_join_plan_boots_logs_in_joins_and_readies(self):
        from tools_py.parity import pcsx2_ctl
        steps = pcsx2_ctl.plan("join", name="socomq", game="test")
        kinds = [k for k, _, _ in steps]
        self.assertEqual(kinds[0], "wait")                              # the cold boot
        typed = [arg for k, arg, _ in steps if k == "type"]
        self.assertEqual(typed, ["socomq", "socomq"], "persona name, then password = name")
        shots = [arg for k, arg, _ in steps if k == "shot"]
        self.assertEqual(shots[-2:], ["05_game_lobby", "06_ready"])
        self.assertTrue(all(w >= 0 for _, _, w in steps))

    def test_host_plan_creates_the_named_game(self):
        from tools_py.parity import pcsx2_ctl
        steps = pcsx2_ctl.plan("host", name="socomp", game="mixed")
        self.assertIn(("type", "mixed", 3.0), steps)
        self.assertEqual([arg for k, arg, _ in steps if k == "shot"][-1], "05_game_lobby")
        with self.assertRaises(ValueError):
            pcsx2_ctl.plan("nonsense")


class WaitForJoinerTest(unittest.TestCase):
    def _clock(self):
        t = {"now": 0.0}
        return (lambda: t["now"]), (lambda s: t.__setitem__("now", t["now"] + s))

    def test_returns_once_both_columns_carry_a_name(self):
        reads = iter([(143, 0), (143, 0), (143, 144)])
        clock, wait = self._clock()
        lines = []
        waited = M.wait_for_joiner(lambda: next(reads), lines.append, timeout_s=60, poll_s=5, clock=clock, wait=wait)
        self.assertEqual(waited, 10.0)
        self.assertTrue(any("-> ok" in ln for ln in lines))

    def test_times_out_when_nobody_comes(self):
        clock, wait = self._clock()
        waited = M.wait_for_joiner(lambda: (143, 0), lambda s: None, timeout_s=30, poll_s=5, clock=clock, wait=wait)
        self.assertIsNone(waited)
        self.assertGreaterEqual(clock(), 30.0)


class MotionVerdictTest(unittest.TestCase):
    def _frames(self, n, drift, noise=0.2, seed=1):
        rng = np.random.default_rng(seed)
        base = rng.uniform(0, 255, size=(112, 160)).astype(np.float32)
        out = []
        for i in range(n):
            f = np.roll(base, i * drift, axis=1) + rng.normal(0, noise, size=base.shape).astype(np.float32)
            out.append(f)
        return out

    def test_a_walking_player_is_seen_and_a_still_scene_is_not(self):
        still = self._frames(6, drift=0)
        moving = self._frames(6, drift=3)
        ok, detail = motion_diff.motion_verdict(still, moving)
        self.assertTrue(ok, detail)
        ok, detail = motion_diff.motion_verdict(still, self._frames(6, drift=0, seed=2))
        self.assertFalse(ok, detail)

    def test_too_few_frames_is_no_data(self):
        ok, detail = motion_diff.motion_verdict(self._frames(3, 0), self._frames(2, 3))
        self.assertFalse(ok)
        self.assertIn("NO-DATA", detail)


if __name__ == "__main__":
    unittest.main()
