"""Sprint 5 Task 3 Steps 1-5 -- the live wiring in `online_match_ours.py` that stops a match from
proving nothing: the controllable precondition, the move-path watch, round state from the valves
(with `respawn` demoted to a fallback), the RESULT verdict, and the valve NO-DATA report.

unittest only. The IO pieces take an injected clock and wait, so the REAL loops run here against a
fake world in simulated time (no sleeps, no game); `RunLogTail._line` is fed real `[peek]`/`[call]`
lines, including launch 1c's (fixtures/online/launch1c_A_movestop.txt).
"""
import math
import os
import struct
import tempfile
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "online")

# Launch 1's instrument environment (research/21 §6.1), with the `*0x43668c*:3` fix.
LAUNCH1_TRACE = ("0x553dc0:MoveScale,0x594cf0:PlayerUpd,0x592560:CtlAlt14,0x5979a0:CtlSpec18,"
                 "0x551ec0:ActorUpd,0x30cd80:NetIdle,0x2a7420:SetMajor")
LAUNCH1_PEEK = ("0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,"
                "*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,"
                "*0x437ce8+0x0c*:2,*0x437ce8+0x10*:2,*0x437ce8+0x14*:2,*0x437ce8+0x20*:2,*0x437ce8+0x24*:2,"
                "*0x437ce8+0x2c*:2,*0x437ce8+0x58*:2,*0x437ce8+0x5c*:2,*0x437ce8+0x70*:2,*0x43668c:2,"
                "0x4365c0:1,0x45a0c0:1,0x3df1b0:1,0x45a1c8:1,*0x44fa90:2,0x4413d8:1,"
                "*0x437ce8+0x0c**:3,*0x437ce8+0x10**:3,*0x437ce8+0x14**:3,*0x437ce8+0x20**:3,"
                "*0x437ce8+0x24**:3,*0x437ce8+0x2c**:3,*0x437ce8+0x58**:3,*0x437ce8+0x5c**:3,"
                "*0x437ce8+0x70**:3,*0x43668c*:3,0x408f10:2,0x408c58:4")
ENV_OK = {"PS2X_CALL_TRACE": LAUNCH1_TRACE, "PS2X_CALL_TRACE_EVERY": "10", "PS2X_PEEK": LAUNCH1_PEEK}


def f2w(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def tok(w):
    return f"{w:08x}(.)"


def item(addr, words):
    return f"@{addr:x}: " + " ".join(tok(w) for w in words)


def name_words(text):
    return list(struct.unpack("<III", (text.encode("ascii") + b"\0" * 12)[:12]))


ACTOR = 0x1583F60


def peek(x=100.0, z=200.0, alive=1, round_count=0, game_over=0, aiteam00=1, clock="05:00",
         with_valves=True, actor=ACTOR, stamp=0.0, round_time=None):
    block = [M.ACTOR_VTABLE] + [0] * 9
    block[7], block[8], block[9] = f2w(x), f2w(50.0), f2w(z)
    parts = ["[peek]", item(0x416054, [f2w(x - 20.0), f2w(70.0), f2w(z)]), item(actor, block)]
    b400 = [0] * 12
    b400[8] = f2w(stamp)
    parts.append(item(actor + 0x400, b400))
    parts.append(item(actor + 0xF78, [(alive & 0xFF) << 16]))
    if with_valves:
        for name, ptr, value, addr in (("mp_round_count", 0x006B7F30, round_count, 0x694C48),
                                       ("mp_game_over", 0x006B7F20, game_over, 0x694C20),
                                       ("aiteam_00", 0x006CCAD4, aiteam00, 0x694C84)):
            parts.append(item(addr, [ptr, 0x00010000 | (value & 0xFFFF)]))
            parts.append(item(ptr, name_words(name)))
    if clock is not None:
        parts.append(item(0x408F10, list(struct.unpack("<II", (clock.encode() + b"\0" * 8)[:8]))))
    if round_time is not None:
        parts.append(item(0x4365C0, [f2w(round_time)]))
        parts.append(item(0x45A0C0, [0x01010101]))
    return " ".join(parts)


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t
        self.worlds = []

    def __call__(self):
        return self.t

    def wait(self, seconds):
        end = self.t + seconds
        while self.t + 0.25 <= end + 1e-9:
            self.t = round(self.t + 0.25, 6)
            for w in self.worlds:
                w.tick(self.t)
        self.t = end


class FakeWorld:
    """A player in simulated time: 4 Hz actor rows; 'W' walks at `speed` along the facing unless
    `responds` is False or the facing is inside `blocked` (deg ranges); 'L'/'J' turn."""

    def __init__(self, clock, responds=True, speed=40.0, facing=0.0, blocked=(), drift_per_s=0.0):
        self.clock, self.responds, self.speed, self.facing = clock, responds, speed, facing
        self.blocked, self.drift = blocked, drift_per_s
        self.x, self.z = 500.0, 500.0
        self.state = set()
        self.rows = []
        clock.worlds.append(self)

    def tick(self, t):
        dt = 0.25
        self.x += self.drift * dt
        if "W" in self.state and self.responds:
            f = M.wrap_deg(self.facing)
            if not any(lo <= f <= hi for lo, hi in self.blocked):
                self.x += self.speed * dt * math.cos(math.radians(self.facing))
                self.z += self.speed * dt * math.sin(math.radians(self.facing))
        if "L" in self.state and self.responds:
            self.facing += M.LOOK_DEG_PER_S * dt
        if "J" in self.state and self.responds:
            self.facing -= M.LOOK_DEG_PER_S * dt
        self.rows.append((t, self.x, 50.0, self.z, ACTOR))

    def actor_ingame(self):
        return list(self.rows)


class ScaledWorld(FakeWorld):
    """A FakeWorld whose MoveScale f12 reads `scale` every 0.5 s (scale=None: the slot is silent)."""

    def __init__(self, clock, scale=None, **kw):
        super().__init__(clock, **kw)
        self.scale = scale

    def scale_ok(self, t0, t1, pad=2.5):
        if self.scale is None:
            return False, 0, None, None
        n = int((t1 - t0 + 2 * pad) / 0.5)
        return self.scale == 1.0, n, self.scale, self.scale


class FakeShell:
    def __init__(self, world, clock):
        self.world, self.clock = world, clock
        self.lines, self.pads = [], []

    def log(self, m):
        self.lines.append(m)

    def shot(self, label, max_age=None):
        pass

    def pad(self, seconds, buttons=(), sticks=(), abort=None):
        self.pads.append((self.clock(), tuple(buttons), tuple(sticks), seconds))
        self.world.state = {k.upper() for k in sticks}
        self.clock.wait(seconds)
        self.world.state = set()


def run_precondition(world_cls=None, **world_kw):
    clock = FakeClock()
    world = (world_cls or FakeWorld)(clock, **world_kw)
    clock.wait(3.0)                                   # rows exist before the precondition starts
    sh = FakeShell(world, clock)
    side = M.assert_controllable("A", world, sh, clock=clock, wait=clock.wait)
    return side, sh


# ---------------------------------------------------------------------------------------------
class AssertControllableTest(unittest.TestCase):
    def test_frozen_player_is_no_control_after_four_holds(self):
        side, sh = run_precondition(responds=False)
        self.assertEqual(side.status, vc.NO_CONTROL)
        self.assertEqual([v.status for v in side.holds], ["FAIL"] * 4)

    def test_every_hold_has_a_measured_drift_window(self):
        # carried item 1: 10 s of fully neutral pad before EACH hold, or holds 2-4 are drift NO-DATA
        side, sh = run_precondition(responds=False)
        self.assertEqual([v.drift_units is not None for v in side.holds], [True] * 4, [v.reason for v in side.holds])

    def test_heading_is_varied_between_holds(self):
        side, sh = run_precondition(responds=False)
        turns = [p for p in sh.pads if M.LOOK_RIGHT_KEY in p[2]]
        fwd = [p for p in sh.pads if M.WALK_FORWARD_KEY in p[2]]
        self.assertEqual((len(turns), len(fwd)), (3, 4))
        self.assertTrue(all(abs(p[3] - M.PRECONDITION_HOLD_S) < 1e-9 for p in fwd))
        # every turn ends at least 10 s before the next forward hold starts
        for t in turns:
            nxt = min(p[0] for p in fwd if p[0] > t[0])
            self.assertGreaterEqual(nxt - (t[0] + t[3]), vc.CONTROL_DRIFT_WINDOW_S)

    def test_no_buttons_are_pressed(self):
        side, sh = run_precondition(responds=False)
        self.assertTrue(all(not p[1] for p in sh.pads))

    def test_controllable_player_passes_on_the_first_hold(self):
        side, sh = run_precondition(responds=True)
        self.assertEqual(side.status, vc.CONTROLLABLE)
        self.assertEqual([v.status for v in side.holds], ["PASS"])
        self.assertGreaterEqual(side.holds[0].net_units, vc.CONTROL_NET_MIN_UNITS)

    def test_geometry_on_the_first_heading_passes_on_a_later_hold(self):
        # the kill2 A Aapp00_walk class: a controllable player whose first hold runs into a wall
        side, sh = run_precondition(responds=True, facing=0.0, blocked=((-45.0, 45.0),))
        self.assertEqual(side.status, vc.CONTROLLABLE)
        self.assertEqual(side.holds[0].status, "FAIL")
        self.assertEqual(side.holds[-1].status, "PASS")

    def test_monotonic_in_speed(self):
        # a slower player never passes where a faster one fails
        results = []
        for speed in (0.0, 10.0, 19.0, 21.0, 30.0, 40.0):
            side, _ = run_precondition(responds=True, speed=speed)
            results.append(side.status == vc.CONTROLLABLE)
        first = results.index(True)
        self.assertTrue(all(results[first:]), results)
        self.assertFalse(results[0])

    def test_neutral_drift_of_6_units_per_s_is_no_control(self):
        side, _ = run_precondition(responds=True, drift_per_s=6.0)
        self.assertEqual(side.status, vc.NO_CONTROL)
        self.assertTrue(all("drift" in v.reason for v in side.holds))

    def test_no_actor_rows_is_no_data(self):
        clock = FakeClock()
        world = FakeWorld(clock, responds=True)
        world.tick = lambda t: None                   # the actor block never resolves
        sh = FakeShell(world, clock)
        side = M.assert_controllable("B", world, sh, clock=clock, wait=clock.wait)
        self.assertEqual(side.status, vc.NO_DATA)
        self.assertLessEqual(len(side.holds), M.PRECONDITION_MAX_ATTEMPTS)

    def test_starved_scale_hold_is_no_data_and_retried(self):
        # I-2: MoveScale logged (n > 0) with f12 < 1.0 -> the hold measured the lag freeze, not the
        # controls: NO-DATA, retried up to PRECONDITION_MAX_ATTEMPTS, never a decisive FAIL
        side, sh = run_precondition(world_cls=ScaledWorld, scale=0.4, responds=False)
        self.assertEqual(side.status, vc.NO_DATA)
        self.assertEqual([v.status for v in side.holds], [vc.NO_DATA] * M.PRECONDITION_MAX_ATTEMPTS)
        self.assertTrue(all("scale" in v.reason for v in side.holds))

    def test_silent_move_path_hold_stays_a_fail(self):
        # the Frostfire case: zero MoveScale lines around the hold -> still decisive
        side, sh = run_precondition(world_cls=ScaledWorld, scale=None, responds=False)
        self.assertEqual(side.status, vc.NO_CONTROL)
        self.assertEqual([v.status for v in side.holds], ["FAIL"] * 4)

    def test_negative_control_full_scale_frozen_player_fails(self):
        side, sh = run_precondition(world_cls=ScaledWorld, scale=1.0, responds=False)
        self.assertEqual([v.status for v in side.holds], ["FAIL"] * 4)

    def test_hold_lines_are_logged_with_the_row_period(self):
        side, sh = run_precondition(responds=True)
        self.assertTrue(any("CONTROL A hold" in m and "period=" in m for m in sh.lines), sh.lines)


class ControlResultTest(unittest.TestCase):
    def test_exit_codes(self):
        self.assertEqual(M.control_exit_code(vc.CONTROLLABLE), 0)
        self.assertEqual(M.control_exit_code(vc.NO_CONTROL), 3)
        self.assertEqual(M.control_exit_code("NO-CONTROL side=B"), 3)
        self.assertEqual(M.control_exit_code(vc.NO_DATA), 2)

    def test_fixture_pairs(self):
        def side(name):
            p = vc.parse_log(open(os.path.join(FIXTURES, name)).read().split("\n"))
            return vc.score_control_side(p.actor_rows, p.pad_events)
        self.assertEqual(M.control_exit_code(vc.control_result({"A": side("frost1_A.txt"), "B": side("frost1_B.txt")})), 3)
        self.assertEqual(vc.control_result({"A": side("kill2_A_probe.txt"), "B": side("frost1_B.txt")}),
                         "NO-CONTROL side=B")
        self.assertEqual(M.control_exit_code(vc.control_result({"A": side("kill2_A_probe.txt"),
                                                                "B": side("kill2_B_probe.txt")})), 0)


# ---------------------------------------------------------------------------------------------
class PeekSpecTest(unittest.TestCase):
    def test_launch1_environment_is_accepted(self):
        self.assertEqual(M.move_path_preconditions(ENV_OK), [])

    def test_every_over_20_or_unset_is_refused(self):
        for every in ("21", "500", None):
            with self.subTest(every=every):
                env = dict(ENV_OK)
                if every is None:
                    del env["PS2X_CALL_TRACE_EVERY"]
                else:
                    env["PS2X_CALL_TRACE_EVERY"] = every
                self.assertTrue(M.move_path_preconditions(env))

    def test_every_20_is_accepted(self):
        self.assertEqual(M.move_path_preconditions(dict(ENV_OK, PS2X_CALL_TRACE_EVERY="20")), [])

    def test_no_movescale_slot_is_refused(self):
        env = dict(ENV_OK, PS2X_CALL_TRACE="0x30cd80:NetIdle")
        self.assertTrue(any("MoveScale" in p for p in M.move_path_preconditions(env)))

    def test_no_alive_byte_peek_is_refused(self):
        env = dict(ENV_OK, PS2X_PEEK=LAUNCH1_PEEK.replace("*0x408c58+0xF78:24,", ""))
        self.assertTrue(any("0xf7a" in p.lower() for p in M.move_path_preconditions(env)))

    def test_alive_byte_covered_by_a_differently_shaped_item_is_accepted(self):
        env = dict(ENV_OK, PS2X_PEEK=LAUNCH1_PEEK.replace("*0x408c58+0xF78:24", "*0x408c58+0xF7A:1"))
        self.assertEqual(M.move_path_preconditions(env), [])

    def test_no_round_valve_name_item_is_refused(self):
        env = dict(ENV_OK, PS2X_PEEK=LAUNCH1_PEEK.replace("*0x437ce8+0x0c**:3,", ""))
        self.assertTrue(any("mp_round_count" in p for p in M.move_path_preconditions(env)))

    def test_spec_lint_names_the_double_dereference(self):
        spec = LAUNCH1_PEEK.replace("*0x43668c*:3", "*0x43668c**:3")
        probs = M.peek_spec_problems(spec)
        self.assertTrue(any("mission_abort" in p and "*0x43668c*:3" in p for p in probs), probs)
        self.assertEqual(M.peek_spec_problems(LAUNCH1_PEEK), [])

    def test_spec_lint_names_the_64_word_cap(self):
        self.assertTrue(any("64" in p for p in M.peek_spec_problems("*0x408c58:80")))


class MovePathWatchTest(unittest.TestCase):
    def make(self, env=ENV_OK):
        self.clock = FakeClock(0.0)
        self.tails = {tag: M.RunLogTail(os.path.join(tempfile.gettempdir(), f"none_{tag}.log"),
                                        clock=self.clock) for tag in ("A", "B")}
        self.logged = []
        return M.MovePathWatch(self.tails, self.logged.append, env=env, clock=self.clock)

    def test_refuses_to_start_on_every_500(self):
        with self.assertRaises(M.MovePathWatchRefused):
            self.make(dict(ENV_OK, PS2X_CALL_TRACE_EVERY="500"))

    def feed(self, tag, seconds, calls=True, **peek_kw):
        n = getattr(self, "n_" + tag, 0)
        end = self.clock.t + seconds
        while self.clock.t < end - 1e-9:
            self.clock.t = round(self.clock.t + 0.25, 6)
            if calls:
                self.tails[tag]._line(f"[call] {self.clock.t:.1f}s MoveScale #{n} a0=0x1 ra=0x595028 f12=1.0")
                n += 5
            self.tails[tag]._line(peek(**peek_kw))
        setattr(self, "n_" + tag, n)

    def test_stalled_while_alive_names_the_side_and_the_r6_gap(self):
        w = self.make()
        # The round clock ADVANCES with the rows, as it did on launch 1c's real stall. (It used to be fed as two
        # constants, 5.0 then 16.0; since Sprint 5 Task 5 a clock standing still for >= 2 s is a guest FREEZE,
        # which disarms the watch -- launch 8c.)
        rt = 0.0
        for _ in range(20):
            rt += 0.25
            self.feed("A", 0.25, round_time=rt)
        for _ in range(44):
            rt += 0.25
            self.feed("A", 0.25, calls=False, round_time=rt)
        v = w.check()
        self.assertEqual(v["A"].status, "stalled")
        self.assertEqual(w.stalled[0], "A")
        line = next(m for m in self.logged if "MOVE-PATH A stalled" in m)
        self.assertIn("actor+0x420=0.000", line)
        self.assertIn("clock@0x4365c0=16.000", line)

    def test_negative_control_advancing(self):
        w = self.make()
        self.feed("A", 20.0)
        self.assertEqual(w.check()["A"].status, "ok")
        self.assertIsNone(w.stalled)

    def test_disarmed_while_dead(self):
        w = self.make()
        self.feed("A", 5.0)
        self.feed("A", 11.0, calls=False, alive=0)
        self.assertEqual(w.check()["A"].status, "disarmed")
        self.assertIsNone(w.stalled)

    def test_never_logged_slot_is_no_data(self):
        w = self.make()
        self.feed("A", 20.0)
        self.assertEqual(w.check()["B"].status, vc.NO_DATA)
        self.assertTrue(any("MOVE-PATH B NO-DATA" in m for m in self.logged))

    def test_launch1c_fixture_is_stalled_with_actor_420_zero(self):
        w = self.make()
        with open(os.path.join(FIXTURES, "launch1c_A_movestop.txt")) as f:
            for line in f.read().split("\n"):
                if line.startswith("[peek]"):
                    self.clock.t = round(self.clock.t + 0.25, 6)
                self.tails["A"]._line(line)
        v = w.check()
        self.assertEqual(v["A"].status, "stalled", v["A"].detail)
        line = next(m for m in self.logged if "MOVE-PATH A stalled" in m)
        self.assertIn("actor+0x420=0.000", line)


# ---------------------------------------------------------------------------------------------
class RoundSignalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = FakeClock(0.0)
        self.tail = M.RunLogTail(os.path.join(self.tmp.name, "run.log"), clock=self.clock)
        self.watch = M.KillWatch({"A": self.tail}, {}, server_log=os.path.join(self.tmp.name, "none.log"),
                                 clock=self.clock)

    def feed(self, n, **kw):
        for _ in range(n):
            self.clock.t = round(self.clock.t + 0.25, 6)
            self.tail._line(peek(**kw))
            self.watch._check_round()
            self.watch._check_positions()

    def test_round_count_step_fires_round(self):
        self.feed(8, round_count=0)
        self.feed(2, round_count=1)
        self.assertEqual(self.watch.fired["kind"], "round")

    def test_game_over_fires_round(self):
        self.feed(8)
        self.feed(2, game_over=1)
        self.assertEqual(self.watch.fired["kind"], "round")

    def test_clock_at_zero_fires_round(self):
        self.feed(8, clock="00:01")
        self.feed(2, clock="00:00")
        self.assertEqual(self.watch.fired["kind"], "round")

    def test_negative_control_steady_valves_do_not_fire(self):
        self.feed(40)
        self.assertIsNone(self.watch.fired)

    def test_respawn_with_live_valves_is_recorded_not_fired(self):
        self.feed(8, x=100.0)
        self.feed(8, x=600.0)                         # a 500-unit jump: respawn
        kinds = [(e["kind"], e["firing"]) for e in self.watch.events]
        self.assertIn(("respawn", False), kinds)
        self.assertIsNone(self.watch.fired)

    def test_respawn_is_the_fallback_when_the_valves_are_no_data(self):
        self.feed(8, x=100.0, with_valves=False)
        self.feed(8, x=600.0, with_valves=False)
        self.assertEqual(self.watch.fired["kind"], "respawn")
        self.assertTrue(self.watch.fired["detail"].get("fallback"))

    def test_aiteam_drop_is_an_observation(self):
        self.feed(8, aiteam00=2)
        self.feed(2, aiteam00=1)
        self.assertIn("aiteam", [e["kind"] for e in self.watch.events])
        self.assertIsNone(self.watch.fired)


class ResultVerdictTest(unittest.TestCase):
    EV_RESPAWN = {"kind": "respawn", "tag": "A", "t": 1.0, "detail": {}, "firing": True}
    EV_ROUND = {"kind": "round", "tag": "A", "t": 1.0, "detail": {}, "firing": True}
    EV_HEALTH = {"kind": "health", "tag": "B", "t": 1.0, "detail": {}, "firing": True}

    def test_respawn_alone_is_not_pass(self):
        verdict, kill = M.result_verdict(self.EV_RESPAWN, [self.EV_RESPAWN], health_armed=False, watch_reads={})
        self.assertFalse(verdict.startswith("PASS"), verdict)
        self.assertFalse(kill)

    def test_round_alone_is_not_pass(self):
        verdict, kill = M.result_verdict(self.EV_ROUND, [self.EV_ROUND], health_armed=False, watch_reads={})
        self.assertFalse(verdict.startswith("PASS"))
        self.assertFalse(kill)

    def test_armed_health_watch_with_zero_reads_is_fail(self):
        verdict, kill = M.result_verdict(None, [], health_armed=True, watch_reads={"A": 0, "B": 0})
        self.assertTrue(verdict.startswith("FAIL health watch"), verdict)
        self.assertFalse(kill)

    def test_zero_reads_on_one_side_fails_even_with_a_health_event(self):
        verdict, kill = M.result_verdict(self.EV_HEALTH, [self.EV_HEALTH], health_armed=True,
                                         watch_reads={"A": 0, "B": 900})
        self.assertTrue(verdict.startswith("FAIL"), verdict)
        self.assertFalse(kill)

    def test_negative_control_health_with_reads_is_pass(self):
        verdict, kill = M.result_verdict(self.EV_HEALTH, [self.EV_HEALTH], health_armed=True,
                                         watch_reads={"A": 900, "B": 900})
        self.assertEqual(verdict, "PASS")
        self.assertTrue(kill)

    def test_a_stale_kill_screen_is_not_pass(self):
        verdict, kill = M.result_verdict(self.EV_HEALTH, [self.EV_HEALTH], health_armed=True,
                                         watch_reads={"A": 900, "B": 900}, stale_shots=["B_kill"])
        self.assertTrue(verdict.startswith("FAIL"), verdict)
        self.assertFalse(kill)

    def test_missing_evidence_frame_is_not_pass(self):
        verdict, kill = M.result_verdict(self.EV_HEALTH, [self.EV_HEALTH], health_armed=True,
                                         watch_reads={"A": 900, "B": 900}, missing_shots=["A_kill"])
        self.assertTrue(verdict.startswith("FAIL evidence-missing"), verdict)
        self.assertFalse(kill)

    def test_evidence_shot_records_stale_and_missing(self):
        class Sh:
            def __init__(self, exc):
                self.exc = exc

            def shot(self, label, max_age=None):
                raise self.exc

        class C:
            def __init__(self, tag, exc):
                self.tag, self.sh = tag, Sh(exc)

        stale, missing, logged = [], [], []
        M.evidence_shot(C("A", M.winshot.StaleFrameError("f", 9.0, 2.0)), "kill", stale, logged.append, missing)
        M.evidence_shot(C("B", OSError("no frame file")), "kill", stale, logged.append, missing)
        M.evidence_shot(C("B", RuntimeError("no frame file at x")), "final", stale, logged.append, missing)
        self.assertEqual((stale, missing), (["A_kill"], ["B_kill", "B_final"]))

    def test_no_signal_is_fail(self):
        verdict, kill = M.result_verdict(None, [], health_armed=False, watch_reads={})
        self.assertTrue(verdict.startswith("FAIL"))


class ValveReportTest(unittest.TestCase):
    def test_unresolved_or_misnamed_valves_are_no_data(self):
        clock = FakeClock(0.0)
        tail = M.RunLogTail(os.path.join(tempfile.gettempdir(), "none.log"), clock=clock)
        with open(os.path.join(FIXTURES, "launch1c_A_movestop.txt")) as f:
            for line in f.read().split("\n"):
                tail._line(line)
        lines = M.valve_report("A", tail, M.requested_valves(LAUNCH1_PEEK))
        joined = "\n".join(lines)
        self.assertIn("NO-DATA mission_abort side=A", joined)
        self.assertIn("VALVE mp_round_count side=A ok", joined)
        self.assertNotIn("NO-DATA mp_round_count", joined)

    def test_a_requested_valve_never_seen_is_no_data(self):
        tail = M.RunLogTail(os.path.join(tempfile.gettempdir(), "none.log"), clock=FakeClock(0.0))
        lines = M.valve_report("B", tail, ["mp_game_over"])
        self.assertEqual(lines, [l for l in lines if l.startswith("NO-DATA mp_game_over side=B")])
        self.assertEqual(len(lines), 1)


if __name__ == "__main__":
    unittest.main()
