"""Sprint 5 Task 5 finish, slice (v) -- Amendment A2 `--rounds N` and A1's per-round stop rules:

  * run_ladder plays up to N rounds (default 4), one `LADDER round=<n>` line each and a final LADDER-SUMMARY;
  * three usable rounds at rung 1 without rung 2 -> SWAP-MOVER (with --auto-swap the next rounds swap the mover);
    two usable rounds at rung 2 without rung 3 -> DAMAGE-PATH-DECISION, the ladder stops engaging;
  * between rounds: mp_round_count moved on, the guest clock runs again and the actor is re-found by its vtable;
    per-round state resets (KillWatch.rearm, StarvationWatch.new_round, MovePathWatch.rearm).

unittest only; simulated time.
"""
import unittest

from tools_py.parity import online_ladder as LD
from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import Clock, peek, tail


def scores(*rungs, verdicts=None, kills=()):
    out = []
    for i, r in enumerate(rungs):
        v = (verdicts or {}).get(i + 1, "FAIL no kill")
        out.append(LD.RoundScore(n=i + 1, mover="A", rung=r, verdict=v, kill=(i + 1) in kills,
                                 line=f"LADDER round={i + 1} rung={r}"))
    return out


class StopRuleTest(unittest.TestCase):
    def test_three_usable_rung1_rounds_swap(self):
        self.assertIsNone(LD.stop_rule(scores(1, 1)))
        self.assertEqual(LD.stop_rule(scores(1, 1, 1)), LD.SWAP_MOVER)

    def test_no_data_rounds_are_not_usable(self):
        self.assertIsNone(LD.stop_rule(scores(1, 1, 1, verdicts={2: "NO-DATA freeze in a fire window"})))
        self.assertIsNone(LD.stop_rule(scores(0, 1, 1)))

    def test_two_usable_rung2_rounds_decide(self):
        self.assertEqual(LD.stop_rule(scores(2, 1, 2)), LD.DAMAGE_PATH_DECISION)
        self.assertIsNone(LD.stop_rule(scores(2, 3, 2)))
        self.assertIsNone(LD.stop_rule(scores(2, 2, kills=(2,))))

    def test_a_rung2_round_stops_the_swap_rule(self):
        self.assertIsNone(LD.stop_rule(scores(1, 2, 1, 1)))


class RunLadderTest(unittest.TestCase):
    def run_it(self, rungs, n=4, auto_swap=False, next_ok=True, fatal_round=None):
        lines, played, nexts = [], [], []

        def play(k, mover):
            played.append((k, mover))
            s = LD.RoundScore(n=k, mover=mover, rung=rungs[k - 1], verdict="FAIL no kill",
                              line=f"LADDER round={k} rung={rungs[k - 1]} mover={mover}")
            if k == fatal_round:
                s.fatal = "RUNG0-FAIL movescale"
            return s

        def nxt(k):
            nexts.append(k)
            return (True, "") if next_ok else (False, "timed out")
        hist, stop = LD.run_ladder(n, play, nxt, lines.append, auto_swap=auto_swap)
        return hist, stop, lines, played, nexts

    def test_four_rounds_by_default_with_one_line_each_and_a_summary(self):
        self.assertEqual(LD.LADDER_ROUNDS_DEFAULT, 4)
        hist, stop, lines, played, nexts = self.run_it([2, 3, 1, 1])
        self.assertEqual([p[0] for p in played], [1, 2, 3, 4])
        self.assertEqual(nexts, [2, 3, 4])
        self.assertEqual(sum(1 for m in lines if m.startswith("LADDER round=")), 4)
        self.assertTrue(lines[-1].startswith("LADDER-SUMMARY rounds=4/4 usable=4 best_rung=3"), lines[-1])

    def test_swap_mover_without_auto_swap_stops(self):
        hist, stop, lines, played, _ = self.run_it([1, 1, 1, 1])
        self.assertEqual(len(played), 3)
        self.assertIn(LD.SWAP_MOVER, stop)
        self.assertTrue(any(m.startswith(LD.SWAP_MOVER) and "--mover B" in m for m in lines), lines)

    def test_auto_swap_walks_the_other_side_next(self):
        hist, stop, lines, played, _ = self.run_it([1, 1, 1, 1, 2], n=5, auto_swap=True)
        self.assertEqual([p[1] for p in played], ["A", "A", "A", "B", "B"])
        self.assertIsNone(stop)

    def test_damage_path_decision_stops_engaging(self):
        hist, stop, lines, played, _ = self.run_it([2, 2, 1, 1])
        self.assertEqual(len(played), 2)
        self.assertIn(LD.DAMAGE_PATH_DECISION, stop)

    def test_a_missing_next_round_or_a_fatal_round_ends_the_ladder(self):
        hist, stop, lines, played, _ = self.run_it([1, 1, 1, 1], next_ok=False)
        self.assertEqual(len(played), 1)
        self.assertIn("no round 2", stop)
        hist, stop, lines, played, _ = self.run_it([1, 1, 1, 1], fatal_round=1)
        self.assertEqual(len(played), 1)
        self.assertIn("RUNG0-FAIL", stop)


class WaitNextRoundTest(unittest.TestCase):
    def feed(self, c, tails, seconds, rc, running=True, rt=None, actor=0x1583F60):
        rt = rt if rt is not None else {"v": 100.0}
        end = c.t + seconds
        while c.t < end - 1e-9:
            c.t = round(c.t + 0.25, 6)
            if running:
                rt["v"] += 0.15
            for g, tl in tails.items():
                tl._line(peek(round_time=rt["v"], round_count=rc, actor=actor))
        return rt

    def test_the_next_round_needs_the_step_the_clock_and_a_fresh_actor(self):
        c = Clock(0.0)
        tails = {g: tail(c, g) for g in "AB"}
        rt = self.feed(c, tails, 2.0, rc=0)
        rt = self.feed(c, tails, 5.5, rc=1, running=False, rt=rt)          # the round boundary: stepped, clock still
        spawns = {g: (100.0, 50.0, 200.0) for g in "AB"}                # peek()'s default position
        ok, reason, _ = LD.wait_next_round(tails, 0, clock=c, wait=lambda s: self.feed(c, tails, s, rc=1, running=False,
                                                                                      rt=rt), timeout=3.0, spawns=spawns)
        self.assertFalse(ok)
        self.assertIn("clock_running=False", reason)
        ok, reason, actors = LD.wait_next_round(tails, 0, clock=c, wait=lambda s: self.feed(c, tails, s, rc=1, rt=rt),
                                                timeout=5.0, spawns=spawns)
        self.assertTrue(ok, reason)
        self.assertEqual(set(actors), {"A", "B"})

    def test_game_over_ends_the_wait(self):
        c = Clock(0.0)
        tails = {"A": tail(c, "A")}
        tails["A"]._line(peek(round_time=5.0).replace("00010000(.)", "00010001(.)", 2))
        ok, reason, _ = LD.wait_next_round(tails, 0, clock=c, wait=c.wait, timeout=1.0)
        self.assertFalse(ok)


class PerRoundResetTest(unittest.TestCase):
    def test_killwatch_rearm_allows_the_next_round_to_fire(self):
        c = Clock(0.0)
        t = tail(c, "A")
        w = M.KillWatch({"A": t}, {"A": (0.0, 0.0)}, server_log="no_such.log", health=0x1044, clock=c)
        t.watch_offset = 0x1044
        for h in (1.0, 0.5, 0.0):
            c.t += 0.25
            t._line(peek(health=h))
            w._check_health()
        self.assertEqual(w.fired["kind"], "health")
        w.rearm()
        self.assertIsNone(w.fired)
        for h in (1.0, 0.0):
            c.t += 0.25
            t._line(peek(health=h))
            w._check_health()
        self.assertEqual(w.fired["kind"], "health")
        self.assertGreater(w.fired["t"], w.rearmed_at)

    def test_starvation_watch_new_round_clears_the_stop_and_the_grace(self):
        c = Clock(0.0)
        tails = {g: tail(c, g) for g in "AB"}
        w = M.StarvationWatch(tails, lambda m: None, clock=c)
        w.stop_reason = "NO-DATA starvation side=A: old round"
        w.alarms.append({"side": "B", "t": 1.0, "t_clear": None, "cause": "starvation", "mover": "A", "t_move": None,
                         "asked": True, "window_s": 4.2, "idle_ms": 4200, "signal": "NetIdle"})
        w.new_round(10.0)
        self.assertIsNone(w.stop_reason)
        self.assertEqual(w.t0, 10.0)
        self.assertTrue(all(a["t_clear"] is not None for a in w.alarms))
        self.assertEqual(w.round_alarms(10.0), [])

    def test_move_path_watch_rearm_disarms_the_transition(self):
        env = {"PS2X_CALL_TRACE": "0x553dc0:MoveScale,0x30cd80:NetIdle", "PS2X_CALL_TRACE_EVERY": "10",
               "PS2X_PEEK": "*0x408c58:64,*0x408c58+0xF78:24,*0x437ce8+0x0c*:2,*0x437ce8+0x0c**:3,0x4365c0:1"}
        c = Clock(0.0)
        tl = tail(c, "S")
        w = M.MovePathWatch({"X": tl}, lambda m: None, env=env, clock=c)
        n, rt = 0, 10.0
        for k in range(16):
            c.t = round(c.t + 0.25, 6)
            rt += 0.15
            tl._line(f"[call] {c.t:.1f}s MoveScale #{n} a0=0x1 ra=0x595028 f12=1.0")
            n += 5
            tl._line(peek(round_time=rt))
        w.rearm(c.t)
        for k in range(48):                                  # 12 s silent move path, clock running
            c.t = round(c.t + 0.25, 6)
            rt += 0.15
            tl._line(peek(round_time=rt))
        self.assertEqual(w.check()["X"].status, "disarmed")
        for k in range(56):                                  # the stall clock restarts when the disarm ends
            c.t = round(c.t + 0.25, 6)
            rt += 0.15
            tl._line(peek(round_time=rt))
        self.assertEqual(w.check()["X"].status, "stalled")


class RoundsArgTest(unittest.TestCase):
    def test_rounds_argument_problems(self):
        class A:
            rounds, auto_swap, endgame, control_round, until_kill = 4, False, "route", False, True
        a = A()
        self.assertIsNone(M.rounds_arg_problem(a))
        a.rounds = 0
        self.assertIn("--rounds", M.rounds_arg_problem(a))
        a.rounds, a.endgame = 2, "converge"
        self.assertIn("--rounds", M.rounds_arg_problem(a))


if __name__ == "__main__":
    unittest.main()
