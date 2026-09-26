"""Sprint 6 Task 4: the burst-to-burst aim correction, against the simulator's aim-bias world (sim_walk_to_b.run_aim_bias).

Ladder launch 2 round 4 (research/22 "Ladder launch 2", docs/HAZARDS.md harness) read the same -4.1 deg aim error on all 111 cycles --
inside the tolerance, so aim_yaw never pulsed -- and fired 111 bursts with no damage. The world here carries that
signature as a FIXED bias on the actor-matrix heading; the hit model is the sim's (a burst hits iff the TRUE aim error
is inside half the subtended angle; a hit lowers the stander's actor+0x1044 word, read by the health watch exactly
as live). Both tests are wall-clock simulations (~30-60 s each)."""
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.parity import sim_walk_to_b as S


def first_hit_burst(r):
    return next((i + 1 for i, b in enumerate(r["bursts"]) if b[2]), None)


class AimBiasCorrectionTest(unittest.TestCase):
    def test_a_fixed_heading_bias_is_walked_off_by_the_lead_table(self):
        r = S.run_aim_bias("wip_aim_bias")
        out = r["out"]
        # round 4's signature: the first aim read in-tolerance and made no pulse, and the first bursts all missed
        a0 = r["aims"][0]
        self.assertIsNotNone(a0["err_after"])
        self.assertLessEqual(abs(a0["err_after"]), a0["tol"], a0)
        self.assertEqual(a0["holds"], [], a0)
        self.assertGreaterEqual(len(r["bursts"]), M.AIM_MISS_BURSTS)
        self.assertTrue(all(not b[2] for b in r["bursts"][:M.AIM_MISS_BURSTS]), r["bursts"][:3])
        # the new behaviour: a hit within 12 bursts, the lead stepped every AIM_MISS_BURSTS misses through the table
        fh = first_hit_burst(r)
        self.assertIsNotNone(fh, ("no burst hit", out["bursts"], [round(b[1], 1) for b in r["bursts"]]))
        self.assertLessEqual(fh, 12, (fh, out.get("lead")))
        lead = out["lead"]
        self.assertEqual(M.AIM_MISS_BURSTS, 3)
        self.assertEqual(tuple(M.AIM_LEAD_TABLE_DEG), (1.5, -1.5, 3.0, -3.0))
        steps = [s["lead"] for s in lead["steps"]]
        self.assertTrue(steps, lead)
        self.assertEqual(steps, list(M.AIM_LEAD_TABLE_DEG[:len(steps)]), steps)
        for s in lead["steps"]:
            self.assertEqual(s["bursts_since_damage"] % M.AIM_MISS_BURSTS, 0, s)
        # the damage was read from the stander's +0x1044 word and reset the miss count; the lead that hit is kept
        self.assertGreaterEqual(lead["hits"], 1, lead)
        self.assertLess(r["health"], 1.0)
        self.assertGreaterEqual(lead["resets"], 1, lead)
        self.assertIn(lead["lead"], M.AIM_LEAD_TABLE_DEG, lead)
        self.assertLess(lead["bursts_since_damage"], M.AIM_MISS_BURSTS * len(M.AIM_LEAD_TABLE_DEG), lead)
        self.assertIsNone(out["stop_reason"], out["stop_reason"])

    def test_an_unreachable_bias_ends_the_engagement_aim_exhausted(self):
        r = S.run_aim_bias("wip_aim_exhausted", bias_deg=S.AIM_BIAS_UNREACHABLE_DEG)
        out = r["out"]
        self.assertEqual(r["hits"], [])
        self.assertEqual(r["health"], 1.0)
        self.assertTrue((out["stop_reason"] or "").startswith(M.AIM_EXHAUSTED_REASON), out["stop_reason"])
        self.assertEqual(M.AIM_EXHAUSTED_REASON, "NO-KILL aim-exhausted")
        lead = out["lead"]
        table = list(M.AIM_LEAD_TABLE_DEG) * M.AIM_LEAD_ROUNDS
        self.assertEqual([s["lead"] for s in lead["steps"]], table, lead)
        # 3 bursts at the bearing, then 3 per lead step, then stop -- never firing forever
        want = M.AIM_MISS_BURSTS * (1 + len(table))
        self.assertGreaterEqual(out["bursts"], want, (out["bursts"], want))
        self.assertLessEqual(out["bursts"], want + 2, (out["bursts"], want))
        self.assertTrue(any("aim-exhausted" in ln for ln in r["lines"]), r["lines"][-5:])


if __name__ == "__main__":
    unittest.main()
