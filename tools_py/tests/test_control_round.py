"""Sprint 5 Task 1 Step 5b -- `online_match_ours.py --control-round`, the clock round-end negative
control Task 6's verdict_replay needs: after the precondition nobody fires, both sides alternate small
strafe legs, and the run ends on the round-end signal (or a cap) and reports whether total_mp_kills,
aiteam_* and the health word stepped.

unittest only; the loop runs in simulated time against fake tails (no sleeps, no game)."""
import struct
import threading
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc

ACTOR = 0x1583FC0
VALVE_ADDRS = {  # name -> (value item addr, name pointer)
    "mp_round_count": (0x694C48, 0x006B7F30),
    "mp_game_over": (0x694C20, 0x006B7F20),
    "player_team": (0x694C30, 0x006CC9FC),
    "aiteam_00": (0x694C84, 0x006CCAD4),
    "aiteam_08": (0x694C94, 0x006CCAEC),
    "total_mp_kills": (0x694CA4, 0x006B7F70),
}


def f2w(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def name_words(text):
    return list(struct.unpack("<III", (text.encode("ascii") + b"\0" * 12)[:12]))


def items(round_count=0, game_over=0, kills=0, ai00=1, ai08=1, team=0, clock="03:00", health=1.0, alive=1):
    block = [M.ACTOR_VTABLE] + [0] * 63
    out = [(0x416054, [0, 0, 0]), (ACTOR, block),
           (ACTOR + 0xF78, [(alive & 0xFF) << 16] + [0] * 23),
           (ACTOR + 0x1044, [f2w(health)] + [0] * 7)]
    values = {"mp_round_count": round_count, "mp_game_over": game_over, "total_mp_kills": kills,
              "aiteam_00": ai00, "aiteam_08": ai08, "player_team": team}
    for name, (addr, ptr) in VALVE_ADDRS.items():
        out.append((addr, [ptr, 0x00010000 | (values[name] & 0xFFFF)]))
        out.append((ptr, name_words(name)))
    out.append((0x408F10, list(struct.unpack("<II", (clock.encode() + b"\0" * 8)[:8]))))
    return out


def state(**kw):
    return M.control_round_state(items(**kw))


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.hooks = []

    def __call__(self):
        return self.t

    def wait(self, s):
        end = self.t + s
        while self.t + 0.25 <= end + 1e-9:
            self.t = round(self.t + 0.25, 6)
            for h in self.hooks:
                h(self.t)
        self.t = end


class FakeTail:
    def __init__(self):
        self._lock = threading.Lock()
        self.latest_items = None


class FakeShell:
    def __init__(self, tag, clock, pads):
        self.tag, self.clock, self.pads = tag, clock, pads

    def pad(self, seconds, buttons=(), sticks=(), abort=None):
        self.pads.append((self.tag, self.clock(), tuple(buttons), tuple(sticks), seconds))
        self.clock.wait(seconds)


class FakeClient:
    def __init__(self, tag, clock, pads):
        self.tag, self.tail, self.sh = tag, FakeTail(), FakeShell(tag, clock, pads)


def run_loop(schedule, cap=420.0, after=5.0):
    """schedule(t) -> items kwargs for the row the game writes at t (4 Hz, both sides alike)."""
    clock, pads, lines = FakeClock(), [], []
    clients = {tag: FakeClient(tag, clock, pads) for tag in ("A", "B")}

    def tick(t):
        for c in clients.values():
            c.tail.latest_items = items(**schedule(t))   # a new object every row, as RunLogTail does

    clock.hooks.append(tick)
    tick(0.0)
    series, end, score = M.control_round(clients, lines.append, clock=clock, wait=clock.wait,
                                         cap_s=cap, after_s=after)
    return series, end, score, pads, lines


def clock_str(t, start=60.0):
    left = max(0, int(start - t))
    return f"{left // 60:02d}:{left % 60:02d}"


class StateTest(unittest.TestCase):
    def test_reads_valves_by_name_clock_health_alive(self):
        st = state(round_count=2, kills=3, ai00=1, ai08=0, team=8, clock="01:02", health=0.5)
        self.assertEqual((st["mp_round_count"], st["total_mp_kills"], st["aiteam_08"], st["player_team"]),
                         (2, 3, 0, 8))
        self.assertEqual(st["clock"], "01:02")
        self.assertAlmostEqual(st["health"], 0.5)
        self.assertEqual(st["alive"], 1)

    def test_no_actor_block_is_no_data_health(self):
        its = [it for it in items() if it[0] != ACTOR]
        self.assertIsInstance(M.control_round_state(its)["health"], vc.NoData)


class RoundEndTest(unittest.TestCase):
    def test_steady_is_no_signal(self):
        rows = [(t, state(clock="02:00")) for t in range(20)]
        self.assertIsNone(M.control_round_end({"A": rows}))

    def test_round_count_step(self):
        rows = [(t, state()) for t in range(5)] + [(5, state(round_count=1))]
        end = M.control_round_end({"A": rows})
        self.assertEqual((end[0], end[1]), (5, "A"))
        self.assertIn("mp_round_count", end[2])

    def test_clock_reaching_zero(self):
        rows = [(0, state(clock="00:01")), (1, state(clock="00:00"))]
        self.assertIn("clock", M.control_round_end({"B": rows})[2])

    def test_first_read_is_history_not_a_signal(self):
        self.assertIsNone(M.control_round_end({"A": [(0, state(round_count=4, clock="00:00"))]}))

    def test_earliest_side_wins(self):
        a = [(0, state()), (9, state(round_count=1))]
        b = [(0, state()), (7, state(game_over=1))]
        self.assertEqual(M.control_round_end({"A": a, "B": b})[1], "B")


class ScoreTest(unittest.TestCase):
    def test_negative_control_holds(self):
        rows = [(t, state()) for t in range(10)] + [(10, state(round_count=1, ai00=0, ai08=0))]
        score = M.score_control_round({"A": rows}, end_t=10)
        self.assertEqual(score["sides"]["A"]["steps"], {"total_mp_kills": 0, "aiteam_00": 0, "aiteam_08": 0})
        self.assertEqual(score["sides"]["A"]["steps_after_end"], {"aiteam_00": 1, "aiteam_08": 1})
        self.assertTrue(M.control_round_ok(score, (10, "A", "mp_round_count 0->1")))

    def test_a_kill_before_the_end_breaks_it(self):
        rows = [(0, state()), (1, state(kills=1, ai08=0, health=0.0)), (2, state(kills=1, round_count=1))]
        score = M.score_control_round({"A": rows}, end_t=2)
        side = score["sides"]["A"]
        self.assertEqual((side["steps"]["total_mp_kills"], side["steps"]["aiteam_08"]), (1, 1))
        self.assertEqual((side["health_min"], side["health_changes"]), (0.0, 1))
        self.assertFalse(M.control_round_ok(score, (2, "A", "x")))

    def test_no_round_end_is_not_ok(self):
        score = M.score_control_round({"A": [(0, state())]}, end_t=None)
        self.assertFalse(M.control_round_ok(score, None))

    def test_result_line(self):
        rows = [(0, state()), (1, state(round_count=1))]
        score = M.score_control_round({"A": rows, "B": rows}, end_t=1)
        line = M.control_round_result_line(score, (1, "A", "mp_round_count 0->1"))
        self.assertTrue(line.startswith("RESULT CONTROL-ROUND round_ended=yes kills_stepped=0 "
                                        "aiteam_stepped=A:aiteam_00=0,A:aiteam_08=0,B:aiteam_00=0,B:aiteam_08=0 "
                                        "health_min=1,1"), line)
        self.assertIn("round_ended=no", M.control_round_result_line(score, None))


class LoopTest(unittest.TestCase):
    def test_strafes_both_sides_never_presses_a_button_and_stops_at_the_round_end(self):
        series, end, score, pads, lines = run_loop(
            lambda t: dict(clock=clock_str(t), round_count=int(t >= 61.0)))
        self.assertIsNotNone(end)
        self.assertIn("clock", end[2])                   # 00:00 at t=60 comes before the count step
        self.assertTrue(all(p[2] == () for p in pads), "a button was pressed")
        self.assertTrue(all(len(p[3]) == 1 and p[3][0] in (M.LATERAL_LEFT_KEY, M.LATERAL_RIGHT_KEY)
                            for p in pads))
        self.assertTrue(all(0.4 <= p[4] <= 1.0 for p in pads))
        tags = [p[0] for p in pads]
        self.assertTrue(all(tags[i] != tags[i + 1] for i in range(len(tags) - 1)), "sides must alternate")
        for tag in ("A", "B"):                           # each side strafes both ways
            self.assertEqual({p[3][0] for p in pads if p[0] == tag}, {"A", "D"})
        # the longest gap between the OTHER side's legs stays well inside the 4000 ms alarm
        b_starts = [p[1] for p in pads if p[0] == "B"]
        self.assertLess(max(b - a for a, b in zip(b_starts, b_starts[1:])), 2.0)
        self.assertTrue(M.control_round_ok(score, end))
        self.assertGreater(series["A"][-1][0], end[0])  # observed after the signal

    def test_cap_without_a_round_end(self):
        series, end, score, pads, lines = run_loop(lambda t: dict(clock="05:00"), cap=30.0)
        self.assertIsNone(end)
        self.assertFalse(M.control_round_ok(score, end))
        self.assertTrue(any("cap 30s reached" in ln for ln in lines))
        self.assertLessEqual(pads[-1][1], 30.0)

    def test_negative_control_a_kill_in_the_window_fails(self):
        series, end, score, pads, lines = run_loop(
            lambda t: dict(clock=clock_str(t), kills=int(t >= 20.0), health=0.0 if t >= 20.0 else 1.0))
        self.assertIsNotNone(end)
        self.assertFalse(M.control_round_ok(score, end))
        self.assertIn("kills_stepped=2", M.control_round_result_line(score, end))


if __name__ == "__main__":
    unittest.main()
