"""Sprint 5 Task 6 Step 1 -- `tools_py.parity.verdict_replay`, the valve-primary kill scorer.

unittest only. The bars are spec §5.1 (Amendment A, pre-registered 2026-09-13) and may not be
loosened: every bar a test relies on is asserted against its registered value in
`TestPreRegisteredBars`, so a silent edit of a bar fails here.

Two kinds of input:
  * trimmed raw excerpts of launch 8c (clock round-end negative control) and launch 3c (no contact)
    under `fixtures/replay/` (provenance in that folder's README.md; make_fixtures.py regenerates);
  * synthetic two-instance logs written here in the exe's own row formats (`[peek]`, `[call]`,
    `[socom2-input] state`), one hazard per test on top of one baseline kill that meets every clause.
"""
import ast
import contextlib
import io
import os
import struct
import subprocess
import sys
import tempfile
import unittest

from tools_py.parity import verdict_replay as vr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.path.join(HERE, "fixtures", "replay")

# Process-clock offsets (B + offset = A), from each instance's MoveScale #0 in the full logs
# (research/21 §8.3 and §9.1); the trimmed fixtures do not carry #0.
L8C_OFFSET_B = 5.80
L3C_OFFSET_B = 6.00


def fixture(name):
    with open(os.path.join(FIXTURES, name), "r") as f:
        return f.read().split("\n")


# ---------------------------------------------------------------------------------------------
# synthetic logs in the exe's formats
# ---------------------------------------------------------------------------------------------
VTABLE = 0x006691A0
ACTOR = {"A": 0x017941D0, "B": 0x017935C0}
# value item address, name pointer (ours, research/21 §2.1) per valve
VALVE_ITEMS = {
    "mp_round_count": (0x694C48, 0x6B7F30),
    "mp_game_over": (0x694C20, 0x6B7F20),
    "player_team": (0x694B30, 0x6CC9FC),
    "aiteam_00": (0x694C84, 0x6CCAD4),
    "aiteam_08": (0x694C98, 0x6CCAEC),
    "total_mp_kills": (0x694D10, 0x6B7F70),
}
R1 = 0x0800
GRENADE_TEST_BUTTON = 0x0200        # R2 as a stand-in grenade button (uncalibrated; plan A7)
PERIOD = 0.25
# Default guest-clock rate (guest s per host s). NOT 1.0, so every window test also tests that the
# windows are in guest seconds (spec §5.1.1: measured 0.57-0.72). Read at row-writing time, so a
# caller may set it.
GUEST_RATE = 0.65


def f2w(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def tok(w):
    return "%08x(%g)" % (w, struct.unpack("<f", struct.pack("<I", w))[0])


def item(addr, words):
    return "@%x: " % addr + " ".join(tok(w) for w in words)


def name_words(name):
    raw = (name.encode() + b"\0" * 12)[:12]
    return list(struct.unpack("<3I", raw))


def str_words(s):
    raw = (s.encode() + b"\0" * 8)[:8]
    return list(struct.unpack("<2I", raw))


def step(t0, before, after):
    return lambda t: after if t >= t0 else before


def rate_guest(rate, offset=0.0):
    return lambda t: rate * t - offset


def rounds_clock(starts):
    """A clock string counting down 6:00 from each restart time (host)."""
    def fn(t):
        s = max(x for x in [0.0] + list(starts) if x <= t)
        return "%02d:%02d" % divmod(max(0, int(360 - (t - s))), 60)
    return fn


class Side:
    """One instance over the SHARED host timeline (A's process clock). Each field is a function of
    host time. `clock_shift` is subtracted from every `[call]` stamp to give the instance's own
    process clock; B's default -6 s means B's process started 6 s before A's (B - 6 s = A), so the
    scorer has to align the clocks (stamps stay positive, as the exe writes them)."""

    def __init__(self, tag, **kw):
        self.tag = tag
        self.clock_shift = kw.pop("clock_shift", 0.0 if tag == "A" else -6.0)
        self.guest = kw.pop("guest", None)          # default GUEST_RATE * t (B 0.2 s behind)
        self.guest_missing = kw.pop("guest_missing", None)   # (t0, t1): no 0x4365c0 item
        self.pos = kw.pop("pos", (lambda t: (500.0, 100.0, 600.0)) if tag == "A" else (lambda t: (540.0, 100.0, 600.0)))
        self.hp = kw.pop("hp", lambda t: 1.0)
        self.alive = kw.pop("alive", None)          # default: 1 while hp > 0, else 0
        self.word0 = kw.pop("word0", lambda t: VTABLE)
        self.c8 = kw.pop("c8", 0x40000001 if tag == "A" else 0x80000100)
        self.valves = {"mp_round_count": lambda t: 0, "mp_game_over": lambda t: 0,
                       "player_team": (lambda t: 0) if tag == "A" else (lambda t: 8),
                       "aiteam_00": lambda t: 1, "aiteam_08": lambda t: 1,
                       "total_mp_kills": lambda t: 0}
        self.valves.update(kw.pop("valves", {}))
        self.drop_valves = set(kw.pop("drop_valves", ()))
        self.clock_string = kw.pop("clock_string", tag == "A")      # the joiner's may be absent
        self.clock_string_fn = kw.pop("clock_string_fn", None)
        self.pad = kw.pop("pad", [])                # [(host t, buttons)]
        self.torn = kw.pop("torn", [])              # [host t]: a state line whose tail never came
        self.end = kw.pop("end", 80.0)
        assert not kw, kw

    def guest_at(self, t):
        if self.guest is not None:
            return self.guest(t)
        return GUEST_RATE * t - (0.0 if self.tag == "A" else 0.2)

    def lines(self):
        out, pads, torn, pi, ti, k = [], sorted(self.pad), sorted(self.torn), 0, 0, 0
        while True:
            t = 0.125 + k * PERIOD
            if t > self.end:
                break
            edge = k * PERIOD                     # the gap between row k-1 and row k
            if k % 4 == 0:
                out.append("[call] %.1fs MoveScale #%d a0=0x%x a1=0x455f8c ra=0x595028 f12=1.0 f13=0.0"
                           % (edge - self.clock_shift, k * 5, ACTOR[self.tag]))
            while pi < len(pads) and pads[pi][0] <= edge:
                out.append("[socom2-input] state buttons=%04x rx=80 ry=80 lx=80 ly=80" % pads[pi][1])
                pi += 1
            while ti < len(torn) and torn[ti] <= edge:
                out.append("[socom2-input] state buttons=0000 rx=8")
                ti += 1
            out.append(self.row(t))
            k += 1
        return out

    def row(self, t):
        a = ACTOR[self.tag]
        x, y, z = self.pos(t)
        hp = self.hp(t)
        alive = self.alive(t) if self.alive is not None else (1 if hp > 0 else 0)
        words = [0] * 64
        words[0] = self.word0(t)
        words[7], words[8], words[9] = f2w(x), f2w(y), f2w(z)
        words[0xC8 // 4] = self.c8
        parts = ["[peek]", item(a, words), item(a + 0xF78, [(alive << 16) | 0x0100]), item(a + 0x1044, [f2w(hp)])]
        for name, (vaddr, nptr) in VALVE_ITEMS.items():
            if name not in self.drop_valves:
                parts.append(item(vaddr, [nptr, 0x00010000 | (self.valves[name](t) & 0xFFFF)]))
        g = self.guest_at(t)
        if not (self.guest_missing and self.guest_missing[0] <= t < self.guest_missing[1]):
            parts.append(item(0x4365C0, [f2w(g)]))
        for name, (vaddr, nptr) in VALVE_ITEMS.items():
            if name not in self.drop_valves:
                parts.append(item(nptr, name_words(name)))
        if self.clock_string:
            s = self.clock_string_fn(t) if self.clock_string_fn else "%02d:%02d" % divmod(max(0, int(360 - t)), 60)
            parts.append(item(0x408F10, str_words(s)))
        return " ".join(parts)


DEATH_T = 40.0


def kill_sides(**over):
    """Baseline: A (host, SEALS, team 0) shoots B (joiner, TERRORISTS, team 8) from 40 units on one
    floor, guest clocks at GUEST_RATE. R1 held 38.0-39.5; B's +0x1044 <= 0 (and +0xF7A 0) from 40.0;
    B's aiteam_08 drops at 40.6, A's total_mp_kills steps at 40.8 and A's aiteam_08 drops at 41.0
    (host). At 0.65: 3 guest s = 4.6 host s, 2 = 3.1, 10 = 15.4. Overrides: a_<field> / b_<field>;
    `*_valves` merges."""
    a = dict(pad=[(38.0, R1), (39.5, 0)],
             valves={"total_mp_kills": step(40.8, 0, 1), "aiteam_08": step(41.0, 1, 0)})
    b = dict(hp=step(DEATH_T, 1.0, 0.0), valves={"aiteam_08": step(40.6, 1, 0)})
    for k, v in over.items():
        side, fld = k.split("_", 1)
        tgt = a if side == "a" else b
        if fld == "valves":
            tgt.setdefault("valves", {}).update(v)
        else:
            tgt[fld] = v
    return Side("A", **a), Side("B", **b)


def score(sides, **kw):
    a, b = sides
    return vr.score_logs(a.lines(), b.lines(), **kw)


class TestPreRegisteredBars(unittest.TestCase):
    """Spec §5.1 / §5.1.1 numbers, verbatim. Editing a bar in the module fails this test."""

    def test_bars(self):
        self.assertEqual(vr.ATTRIBUTION_WINDOW_S, 3.0)
        self.assertEqual(vr.ATTRIBUTION_DY_MAX, 10.0)
        self.assertEqual(vr.ATTRIBUTION_3D_MAX, 60.0)
        self.assertEqual(vr.VALVE_WINDOW_GUEST_S, 3.0)
        self.assertEqual(vr.CROSS_INSTANCE_MAX_S, 20.0)
        self.assertEqual(vr.KILL_STEP_BEFORE_DEATH_S, 3.0)
        self.assertEqual(vr.FALL_WINDOW_S, 2.0)
        self.assertEqual(vr.FALL_DROP_MAX, 20.0)
        self.assertEqual(vr.SELF_GRENADE_WINDOW_S, 10.0)
        self.assertEqual(vr.R1_MASK, 0x0800)
        self.assertEqual(vr.SELF_GRENADE_MASK, 0xF700)
        self.assertEqual(vr.KILLS_STEP, 1)
        self.assertEqual(vr.AITEAM_DROP, 1)
        self.assertEqual(vr.INSTANT_S, 0.5)
        self.assertEqual(vr.ACTOR_DESTROYED_S, 2.0)
        self.assertEqual(vr.FREEZE_RATE_MAX, 0.25)
        self.assertEqual(vr.FREEZE_MIN_HOST_S, 1.0)
        self.assertEqual(vr.DEFAULT_SHOOTER, "A")


# ---------------------------------------------------------------------------------------------
# 1-2: the real negative controls
# ---------------------------------------------------------------------------------------------
class TestLaunch8cClockRoundEnd(unittest.TestCase):
    def setUp(self):
        self.v = vr.score_logs(fixture("l8c_A.txt"), fixture("l8c_B.txt"), offset_b=L8C_OFFSET_B)

    def test_no_kill(self):
        self.assertIn(self.v.word, (vr.NO_KILL,), self.v.text())
        self.assertIn(self.v.reason, (vr.R_NO_DEATH, vr.R_ROUND_ENDED))
        self.assertEqual(self.v.exit_code, 1)

    def test_kill_fields_unchanged_while_round_count_steps(self):
        for tag in "AB":
            f = self.v.facts[tag]
            self.assertEqual(f["steps"]["mp_round_count"], [(0, 1)], tag)
            self.assertEqual(f["steps"]["total_mp_kills"], [], tag)
            self.assertEqual(f["steps"]["aiteam_00"], [], tag)
            self.assertEqual(f["steps"]["aiteam_08"], [], tag)
            self.assertEqual(f["hp_values"], [1.0], tag)
            self.assertGreater(f["valve_rows"]["mp_round_count"], 0, tag)
            self.assertGreater(f["hp_rows"], 0, tag)

    def test_per_round_lines(self):
        lines = vr.score_logs(fixture("l8c_A.txt"), fixture("l8c_B.txt"), offset_b=L8C_OFFSET_B, per_round=True)
        self.assertEqual([l.headline() for l in lines], ["NO-KILL no-death round=1", "NO-KILL no-death round=2"])


class TestLaunch3cNoContact(unittest.TestCase):
    def test_no_kill_no_death(self):
        v = vr.score_logs(fixture("l3c_A.txt"), fixture("l3c_B.txt"), offset_b=L3C_OFFSET_B)
        self.assertEqual((v.word, v.reason, v.exit_code), (vr.NO_KILL, vr.R_NO_DEATH, 1), v.text())


# ---------------------------------------------------------------------------------------------
# 3-13: synthetic
# ---------------------------------------------------------------------------------------------
class TestSyntheticKill(unittest.TestCase):
    def test_every_clause_met_is_kill(self):
        v = score(kill_sides())
        self.assertEqual((v.word, v.killer, v.victim, v.exit_code, v.round), (vr.KILL, "A", "B", 0, 1), v.text())
        self.assertTrue(v.text().splitlines()[0].startswith("KILL killer=A victim=B t="), v.text())
        self.assertTrue(v.text().splitlines()[0].endswith(" round=1"), v.text())
        self.assertTrue(all(ok is not False for _, ok, _ in v.clauses), v.text())
        self.assertGreaterEqual(len(v.clauses), 10, v.text())

    def test_kills_step_on_the_victim_instance_only_is_enough(self):
        v = score(kill_sides(a_valves={"total_mp_kills": lambda t: 0},
                             b_valves={"total_mp_kills": step(40.5, 0, 1)}))
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_joiner_clock_string_absent_is_not_needed(self):
        v = score(kill_sides(b_clock_string=False))
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_shooter_defaults_to_A(self):
        self.assertEqual(score(kill_sides(), shooter="A").word, vr.KILL)
        v = score(kill_sides(), shooter="B")          # B was the victim: B killed nobody
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())
        b_kills_a = (Side("A", hp=step(DEATH_T, 1.0, 0.0), valves={"aiteam_00": step(40.6, 1, 0)}),
                     Side("B", pad=[(38.0, R1), (39.5, 0)], valves={"total_mp_kills": step(40.8, 0, 1), "aiteam_00": step(41.0, 1, 0)}))
        v = score(b_kills_a)
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())
        self.assertEqual(score(kill_sides(), shooter=None).word, vr.KILL)
        v = score(b_kills_a, shooter="B")
        self.assertEqual((v.word, v.killer, v.victim), (vr.KILL, "B", "A"), v.text())

    def test_killer_grenade_is_a_kill(self):
        v = score(kill_sides(a_pad=[(38.0, GRENADE_TEST_BUTTON), (38.4, 0)]), grenade_mask=GRENADE_TEST_BUTTON)
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_killer_grenade_button_without_calibration_does_not_attribute(self):
        v = score(kill_sides(a_pad=[(38.0, GRENADE_TEST_BUTTON), (38.4, 0)]))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())

    def test_hp_zero_with_word0_destroyed_on_the_same_row_is_no_data(self):
        # NOT §5.1.1's actor-destroyed case: the last intact row read +0x1044 = 1.0 (not < 1.0), and the
        # <= 0 read comes only from a block whose word 0 already left the vtable -- an untrusted read.
        v = score(kill_sides(b_word0=step(DEATH_T, VTABLE, 0x004061C0)))
        self.assertEqual((v.word, v.exit_code), (vr.NO_DATA, 2), v.text())

    def test_actor_destroyed_after_damage_is_kill_semantics(self):
        # §5.1.1: an intact row with +0x1044 < 1.0, word 0 leaves within 2 s, kill valves step, no intact
        # row reads <= 0 -> KILL-SEMANTICS actor-destroyed.
        v = score(kill_sides(b_hp=lambda t: 1.0 if t < 39.5 else 0.4, b_word0=step(DEATH_T, VTABLE, 0x004061C0)))
        self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "actor-destroyed"), v.text())

    def test_clock_zero_before_the_death_is_round_ended_first(self):
        v = score(kill_sides(a_clock_string_fn=lambda t: "00:00" if t >= 35.0 else "00:05"))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_ROUND_ENDED), v.text())

    def test_round_count_step_before_the_death_is_round_ended_first(self):
        v = score(kill_sides(b_valves={"mp_round_count": step(39.0, 0, 1)}))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_ROUND_ENDED), v.text())

    def test_game_over_before_the_death_is_round_ended_first(self):
        v = score(kill_sides(a_valves={"mp_game_over": step(38.0, 0, 1)}))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_ROUND_ENDED), v.text())

    def test_killer_actor_rows_missing_is_no_data(self):
        v = score(kill_sides(a_word0=lambda t: 0x12345678))
        self.assertEqual(v.word, vr.NO_DATA, v.text())

    def test_kill_in_round_two_carries_the_round_and_per_round_lines(self):
        rounds = dict(a_clock_string_fn=rounds_clock([25.6]),
                      a_valves={"mp_round_count": step(20.0, 0, 1)}, b_valves={"mp_round_count": step(20.0, 0, 1)})
        v = score(kill_sides(**rounds))
        self.assertEqual((v.word, v.round), (vr.KILL, 2), v.text())
        lines = score(kill_sides(**rounds), per_round=True)
        self.assertEqual([l.headline().split(" t=")[0] if l.word == vr.KILL else l.headline() for l in lines],
                         ["NO-KILL no-death round=1", "KILL killer=A victim=B"])
        self.assertTrue(lines[1].headline().endswith(" round=2"))

    def test_cli_prints_and_exits(self):
        a, b = kill_sides()
        d = tempfile.mkdtemp(prefix="replay_")
        pa, pb = os.path.join(d, "run_A.log"), os.path.join(d, "run_B.log")
        for p, s in ((pa, a), (pb, b)):
            with open(p, "w") as f:
                f.write("\n".join(s.lines()) + "\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = vr.main([pa, pb])
        self.assertEqual(code, 0)
        self.assertTrue(buf.getvalue().startswith("KILL killer=A victim=B t="), buf.getvalue())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = vr.main([pa, pb, "--per-round"])
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue().splitlines()[0].split(" t=")[0], "KILL killer=A victim=B")


class TestSyntheticMutualDeath(unittest.TestCase):
    def test_mutual_death_is_no_kill_unattributed(self):
        # Defined verdict: NO-KILL unattributed. §5.1 keeps "killer +0x1044 > 0" unchanged. When both
        # actors reach <= 0 together (here on the same row) neither side is a killer whose own health
        # was > 0 at the other's death, and the valves cannot separate a trade from one side's grenade
        # killing both (both aiteam_* drop, total_mp_kills may step twice). A trade must not be
        # called a kill for either side, and it is not a data gap (every row is present) -- so NO-KILL
        # with reason `unattributed`, for both candidate victims.
        v = score(kill_sides(a_hp=step(DEATH_T, 1.0, 0.0),
                             a_valves={"aiteam_00": step(40.7, 1, 0)},
                             b_valves={"aiteam_00": step(40.9, 1, 0), "total_mp_kills": step(40.9, 0, 1)}))
        self.assertEqual((v.word, v.reason, v.exit_code), (vr.NO_KILL, vr.R_UNATTRIBUTED, 1), v.text())

    def test_killer_dies_0_4s_after_the_victim_only_victim_valves(self):
        # The killer's +0x1044 is read over +-0.5 s of the death (every row, the strictest reading of
        # "the row nearest"): a killer at 0 within it is not a killer whose health was > 0.
        v = score(kill_sides(a_hp=step(40.5, 1.0, 0.0)))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())

    def test_killer_dead_since_before_is_unattributed(self):
        v = score(kill_sides(a_hp=step(35.0, 1.0, 0.0)))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())


class TestSyntheticFall(unittest.TestCase):
    def test_victim_y_drop_over_20_in_the_2s_before(self):
        def fall(t):
            y = 140.0 if t < 38.5 else (100.0 if t >= 39.5 else 140.0 - 40.0 * (t - 38.5))
            return (540.0, y, 600.0)
        v = score(kill_sides(b_pos=fall))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_FALL), v.text())

    def test_drop_of_22_is_a_fall(self):
        def fall(t):
            y = 122.0 if t < 38.5 else (100.0 if t >= 39.5 else 122.0 - 22.0 * (t - 38.5))
            return (540.0, y, 600.0)
        v = score(kill_sides(b_pos=fall))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_FALL), v.text())

    def test_drop_before_the_2_guest_s_window_is_not_a_fall(self):
        # 25-unit drop at host 34.5-35.0, i.e. >= 3.3 guest s before the death: outside the fall window,
        # and the pair is on one floor for the whole attribution window (from host ~35.5).
        def early(t):
            y = 125.0 if t < 34.5 else (100.0 if t >= 35.0 else 125.0 - 50.0 * (t - 34.5))
            return (540.0, y, 600.0)
        v = score(kill_sides(b_pos=early))
        self.assertEqual(v.word, vr.KILL, v.text())


class TestSyntheticSelfGrenade(unittest.TestCase):
    def test_grenade_on_the_victims_own_pad(self):
        v = score(kill_sides(b_pad=[(34.0, GRENADE_TEST_BUTTON), (34.4, 0)]))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_SELF), v.text())

    def test_victim_grenade_7_5_guest_s_before_is_self(self):
        v = score(kill_sides(b_pad=[(28.6, GRENADE_TEST_BUTTON), (28.9, 0)]))      # 11.5 host s = 7.5 guest s
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_SELF), v.text())

    def test_victim_circle_counts_as_a_possible_grenade(self):
        v = score(kill_sides(b_pad=[(34.0, 0x2000), (34.4, 0)]))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_SELF), v.text())

    def test_victim_grenade_before_the_10_guest_s_window_is_not_self(self):
        v = score(kill_sides(b_pad=[(22.0, GRENADE_TEST_BUTTON), (22.4, 0)]))      # 18 host s = 11.7 guest s
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_victim_dpad_is_not_a_grenade(self):
        v = score(kill_sides(b_pad=[(34.0, 0x0010), (34.4, 0)]))                  # UP
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_torn_pad_line_in_the_victims_self_window_is_no_data(self):
        v = score(kill_sides(b_torn=[35.0]))
        self.assertEqual(v.word, vr.NO_DATA, v.text())

    def test_torn_pad_line_in_the_killers_attribution_window_is_no_data(self):
        v = score(kill_sides(a_torn=[37.0]))
        self.assertEqual(v.word, vr.NO_DATA, v.text())


class TestSyntheticUnattributed(unittest.TestCase):
    def test_no_killer_r1_in_the_3_guest_s_before(self):
        v = score(kill_sides(a_pad=[(33.0, R1), (34.5, 0)]))       # release 5.6 host s = 3.7 guest s before
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())

    def test_r1_tap_3_2_guest_s_before_is_outside(self):
        v = score(kill_sides(a_pad=[(35.2, R1), (35.3, 0)]))       # 4.9 host s = 3.2 guest s before
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())

    def test_r1_4_host_s_before_is_inside_3_guest_s(self):
        v = score(kill_sides(a_pad=[(36.0, R1), (36.2, 0)]))       # 4.1 host s = 2.7 guest s
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_r1_but_pair_70_apart(self):
        v = score(kill_sides(b_pos=lambda t: (570.0, 100.0, 600.0)))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())

    def test_r1_but_dy_15(self):
        v = score(kill_sides(b_pos=lambda t: (540.0, 115.0, 600.0)))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())

    def test_55_apart_same_floor_is_kill(self):
        v = score(kill_sides(b_pos=lambda t: (555.0, 100.0, 600.0)))
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_pair_leaves_the_band_inside_the_window(self):
        v = score(kill_sides(b_pos=lambda t: (570.0 if 37.5 <= t < 38.5 else 540.0, 100.0, 600.0)))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())


class TestSyntheticTeam(unittest.TestCase):
    def test_wrong_teams_aiteam_drops(self):
        v = score(kill_sides(a_valves={"aiteam_08": lambda t: 1, "aiteam_00": step(41.0, 1, 0)},
                             b_valves={"aiteam_08": lambda t: 1, "aiteam_00": step(40.6, 1, 0)}))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_TEAM), v.text())

    def test_wrong_team_drop_on_the_killer_only_is_team(self):
        v = score(kill_sides(a_valves={"aiteam_00": step(52.0, 1, 0)}))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_TEAM), v.text())

    def test_wrong_team_drop_on_the_victim_only_is_team(self):
        v = score(kill_sides(b_valves={"aiteam_00": step(42.0, 1, 0)}))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_TEAM), v.text())

    def test_same_team_is_team(self):
        v = score(kill_sides(a_valves={"player_team": lambda t: 8}))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_TEAM), v.text())


class TestSyntheticMissingValve(unittest.TestCase):
    def test_missing_valve_item(self):
        v = score(kill_sides(b_drop_valves={"total_mp_kills"}))
        self.assertEqual((v.word, v.exit_code), (vr.NO_DATA, 2), v.text())
        self.assertIn("total_mp_kills", v.reason)
        self.assertTrue(v.text().startswith("NO-DATA "), v.text())

    def test_missing_valve_on_a_no_death_run_is_still_no_data(self):
        v = score((Side("A"), Side("B", drop_valves={"aiteam_08"})))
        self.assertEqual(v.word, vr.NO_DATA, v.text())

    def test_unreadable_guest_delta_on_a_kill_step_is_no_data(self):
        v = score(kill_sides(a_guest_missing=(40.5, 41.9)))
        self.assertEqual(v.word, vr.NO_DATA, v.text())


def frozen_rate(t0, t1, offset=0.0, rate=None):
    """Guest at GUEST_RATE (or `rate`) that stops from host t0 to t1 and resumes from there."""
    r = GUEST_RATE if rate is None else rate
    return lambda t: r * t - offset if t < t0 else (r * t0 - offset if t < t1 else r * (t - (t1 - t0)) - offset)


class TestSyntheticFreeze(unittest.TestCase):
    def test_victim_guest_clock_stops_across_the_window(self):
        v = score(kill_sides(b_guest=frozen_rate(39.0, 42.0, 0.2)))
        self.assertEqual((v.word, v.exit_code), (vr.NO_DATA, 2), v.text())
        self.assertIn("freeze", v.reason)

    def test_killer_guest_clock_stops_in_the_attribution_window(self):
        v = score(kill_sides(a_guest=frozen_rate(34.0, 39.0), a_pad=[(33.5, R1), (33.8, 0)]))
        self.assertEqual(v.word, vr.NO_DATA, v.text())
        self.assertIn("freeze", v.reason)

    def test_killer_freeze_only_in_the_attribution_window(self):
        # A stops 34.0-36.0 (guest 22.1): inside the attribution window (guest 21.8-24.8, from host ~33.5),
        # outside the kill row's +-3 guest s window (guest from 22.3, host ~36.3).
        v = score(kill_sides(a_guest=frozen_rate(34.0, 36.0)))
        self.assertEqual(v.word, vr.NO_DATA, v.text())
        self.assertIn("A:guest-clock-freeze", v.reason)

    def test_slow_killer_clock_with_short_stalls_is_a_freeze_by_window_rate(self):
        # From host 20: 0.75 s stopped, 0.5 s at rate 0.55, repeated -- no stall reaches 1 s and none
        # merge (>= two advancing pairs between), but the window's overall rate is ~0.23 < 0.25.
        def slow(t):
            if t < 20.0:
                return GUEST_RATE * t
            n, rem = divmod(t - 20.0, 1.25)
            return GUEST_RATE * 20.0 + 0.275 * n + (0.0 if rem < 0.75 else 0.55 * (rem - 0.75))
        v = score(kill_sides(a_guest=slow))
        self.assertEqual(v.word, vr.NO_DATA, v.text())
        self.assertIn("rate", v.reason)

    def test_killer_guest_clock_stops_around_its_kill_row(self):
        v = score(kill_sides(a_guest=frozen_rate(41.5, 44.0)))
        self.assertEqual(v.word, vr.NO_DATA, v.text())
        self.assertIn("freeze", v.reason)

    def test_freeze_elsewhere_in_the_round_does_not_change_the_verdict(self):
        v = score(kill_sides(a_guest=frozen_rate(20.0, 23.0)))
        self.assertEqual(v.word, vr.KILL, v.text())


class TestSyntheticSemantics(unittest.TestCase):
    def test_alive_byte_stays_1(self):
        v = score(kill_sides(b_alive=lambda t: 1))
        self.assertEqual((v.word, v.reason, v.exit_code), (vr.KILL_SEMANTICS, "+0xF7A", 1), v.text())
        self.assertTrue(v.text().startswith("KILL-SEMANTICS +0xF7A"), v.text())

    def test_total_mp_kills_steps_on_neither(self):
        v = score(kill_sides(a_valves={"total_mp_kills": lambda t: 0}))
        self.assertEqual((v.word, v.reason, v.exit_code), (vr.KILL_SEMANTICS, "total_mp_kills", 1), v.text())

    def test_total_mp_kills_steps_by_two(self):
        v = score(kill_sides(a_valves={"total_mp_kills": step(40.8, 0, 2)}))
        self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "total_mp_kills"), v.text())

    def test_aiteam_drops_by_two_on_both(self):
        v = score(kill_sides(b_valves={"aiteam_08": step(40.6, 2, 0)}, a_valves={"aiteam_08": step(41.0, 2, 0)}))
        self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "aiteam_08"), v.text())

    def test_aiteam_drops_by_two_on_the_victim_instance_only(self):
        v = score(kill_sides(b_valves={"aiteam_08": step(40.6, 2, 0)}))
        self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "aiteam_08"), v.text())

    def test_aiteam_drops_by_two_on_the_killer_instance_only(self):
        v = score(kill_sides(a_valves={"aiteam_08": step(41.0, 2, 0)}))
        self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "aiteam_08"), v.text())

    def test_killer_aiteam_outside_3_guest_s_of_its_kill_row(self):
        v = score(kill_sides(a_valves={"aiteam_08": step(50.0, 1, 0)}))       # 9.1 host s = 5.9 guest s after
        self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "aiteam_08"), v.text())

    def test_aiteam_drops_on_the_victim_instance_only(self):
        v = score(kill_sides(a_valves={"aiteam_08": lambda t: 1}))
        self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "aiteam_08"), v.text())

    def test_several_misbehaving_valves_are_all_listed(self):
        v = score(kill_sides(a_valves={"total_mp_kills": lambda t: 0}, b_alive=lambda t: 1))
        self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "total_mp_kills,+0xF7A"), v.text())


class TestSyntheticCrossInstanceDelay(unittest.TestCase):
    def test_12s_host_delay_is_kill(self):
        v = score(kill_sides(a_valves={"total_mp_kills": step(52.8, 0, 1), "aiteam_08": step(53.0, 1, 0)}))
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_25s_host_delay_is_no_kill_timing(self):
        # §5.1.1 (R56): a cross-instance delay beyond 20 s host is NO-KILL timing.
        v = score(kill_sides(a_valves={"total_mp_kills": step(65.8, 0, 1), "aiteam_08": step(66.0, 1, 0)}))
        self.assertEqual((v.word, v.reason, v.exit_code), (vr.NO_KILL, vr.R_TIMING, 1), v.text())


# ---------------------------------------------------------------------------------------------
# fix round 1: every false KILL of the adversarial review (scratchpad rvvr/adv*.py), at the review's
# guest rate 1.0, plus the realistic kill that must still pass. Each failed on 312ea8b.
# ---------------------------------------------------------------------------------------------
RATE1 = dict(a_guest=rate_guest(1.0, 1.0), b_guest=rate_guest(1.0, 1.3))


def rate1_sides(**over):
    kw = dict(RATE1)
    kw.update(over)
    return kill_sides(**kw)


def stutter(t):
    """0.9 s stalls separated by 0.25 s of advance from host 28 (rate ~0.22)."""
    if t < 28:
        return t - 1.0
    base, tt = 27.0, 28.0
    while tt + 1.15 <= t:
        tt += 1.15
        base += 0.25
    rem = t - tt
    return base + (0.0 if rem < 0.9 else (rem - 0.9))


def frag(t):
    """Three 0.9 s stalls 36-39.2 separated by one advancing row pair each (8c's real shape)."""
    if t < 36.0:
        return t - 1.0
    if t < 36.9:
        return 35.0
    if t < 37.15:
        return 35.0 + (t - 36.9)
    if t < 38.05:
        return 35.25
    if t < 38.3:
        return 35.25 + (t - 38.05)
    if t < 39.2:
        return 35.5
    return 35.5 + (t - 39.2)


class TestAdversarialRegressions(unittest.TestCase):
    def assertNotKill(self, v):
        self.assertNotEqual(v.word, vr.KILL, v.text())

    def test_3a_previous_rounds_kill_step_registered_late(self):
        v = score(rate1_sides(a_clock_string_fn=rounds_clock([22.0]),
                              a_valves={"mp_round_count": step(20.0, 0, 1), "total_mp_kills": step(23.0, 0, 1),
                                        "aiteam_08": lambda t: 0 if 23.2 <= t < 24.0 else 1},
                              b_valves={"mp_round_count": step(20.0, 0, 1), "aiteam_08": step(40.6, 1, 0)}))
        self.assertNotKill(v)

    def test_4b_block_reused_at_round_end_with_late_valves(self):
        v = score(rate1_sides(a_clock_string_fn=rounds_clock([30.0]), b_hp=lambda t: 0.0 if 30.0 <= t < 30.25 else 1.0,
                              b_pos=lambda t: (540.0, 100.0, 600.0) if t < 30.0 else (548.0, 100.0, 610.0),
                              a_valves={"mp_round_count": step(29.0, 0, 1), "total_mp_kills": step(31.5, 0, 1), "aiteam_08": step(31.7, 1, 0)},
                              b_valves={"mp_round_count": step(29.0, 0, 1), "aiteam_08": step(30.9, 1, 0)}, a_pad=[(28.0, R1), (30.5, 0)]))
        self.assertNotKill(v)

    def test_7c_round_change_kill(self):
        v = score(rate1_sides(a_clock_string_fn=rounds_clock([37.5]), b_hp=step(37.5, 1.0, 0.0), a_pad=[(35.0, R1), (37.6, 0)],
                              a_valves={"mp_round_count": step(32.0, 0, 1), "total_mp_kills": step(38.0, 0, 1), "aiteam_08": step(38.2, 1, 0)},
                              b_valves={"mp_round_count": step(32.0, 0, 1), "aiteam_08": step(38.0, 1, 0)}))
        self.assertNotKill(v)

    def test_8a_killer_stutters(self):
        v = score(rate1_sides(a_guest=stutter, a_pad=[(31.0, R1), (31.3, 0)]))
        self.assertEqual(v.word, vr.NO_DATA, v.text())

    def test_8d_killer_fragmented_stalls(self):
        v = score(rate1_sides(a_guest=frag, a_pad=[(34.6, R1), (34.9, 0)]))
        self.assertEqual(v.word, vr.NO_DATA, v.text())

    def test_11_round_values_differ_at_death(self):
        v = score(rate1_sides(a_clock_string_fn=rounds_clock([22.0]), a_valves={"mp_round_count": step(20.0, 0, 1)}))
        self.assertNotKill(v)

    def test_12_alive_byte_stays_1_until_2_5s_after(self):
        v = score(rate1_sides(b_alive=lambda t: 0 if t >= 42.5 else 1))
        self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "+0xF7A"), v.text())

    def test_13_alive_byte_1_on_intact_rows_then_destroyed(self):
        v = score(rate1_sides(b_alive=lambda t: 1 if t < 41 else 7, b_word0=lambda t: VTABLE if t < 41 else 0))
        self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "+0xF7A"), v.text())

    def test_14_killer_valves_step_18s_before_the_death(self):
        # (14b in the review is the same input)
        v = score(rate1_sides(a_valves={"total_mp_kills": step(22.0, 0, 1), "aiteam_08": step(22.2, 1, 0)}))
        self.assertNotKill(v)

    def test_one_kill_step_corroborates_one_death(self):
        # the victim dies twice in the round (revived between); one kill-valve set steps -> at most one KILL
        v = score(kill_sides(b_hp=lambda t: 0.0 if 38.0 <= t < 38.5 or t >= 40.0 else 1.0,
                             b_valves={"aiteam_08": lambda t: 0 if 38.6 <= t < 39.0 or t >= 40.6 else 1}), per_round=True)
        note = next(n for n in v[0].notes if "2 candidate deaths" in n)
        self.assertEqual(note.count("KILL killer="), 1, v[0].text())      # the second death is not a KILL
        self.assertEqual(v[0].word, vr.KILL, v[0].text())

    def test_ff2abc_actor_destroyed(self):
        D = 40.0
        for hp, w0 in ((lambda t: 1.0 if t < D - 0.5 else 0.4, lambda t: VTABLE if t < D else 0),
                       (lambda t: 1.0 if t < D - 0.5 else (0.4 if t < D else 0.0), lambda t: VTABLE if t < D else 0),
                       (lambda t: 1.0 if t < D - 0.5 else 0.4, lambda t: VTABLE if t < D else 0x0066AA00)):
            v = score(rate1_sides(b_hp=hp, b_word0=w0))
            self.assertEqual((v.word, v.reason), (vr.KILL_SEMANTICS, "actor-destroyed"), v.text())

    def test_ff1_realistic_kill_still_passes(self):
        rate, D = 0.62, 160.0
        steps_, restarts = (60.0, 120.0), (65.6, 125.6)
        rc = lambda t: sum(1 for s in steps_ if t >= s)

        def guest_b(t):                    # a 5 s freeze two rounds earlier
            return rate * t + 0.1 if t < 30.0 else (rate * 30.0 + 0.1 if t < 35.0 else rate * (t - 5.0) + 0.1)
        a = Side("A", guest=rate_guest(rate), clock_string_fn=rounds_clock(restarts), end=200.0,
                 pad=[(156.0, R1), (157.2, 0), (158.0, R1), (159.6, 0)],
                 valves={"mp_round_count": rc, "total_mp_kills": step(D + 8.3, 0, 1), "aiteam_08": step(D + 8.5, 1, 0)})
        b = Side("B", guest=guest_b, clock_string=False, end=200.0, hp=step(D, 1.0, 0.0),
                 valves={"mp_round_count": rc, "aiteam_08": step(D + 0.5, 1, 0)})
        v = vr.score_logs(a.lines(), b.lines())
        self.assertEqual((v.word, v.killer, v.victim, v.round), (vr.KILL, "A", "B", 3), v.text())


# ---------------------------------------------------------------------------------------------
# 14-15: independence from the other scorer
# ---------------------------------------------------------------------------------------------
class TestImportSet(unittest.TestCase):
    FORBIDDEN = ("verdict_core", "online_match_ours")

    def test_module_source_imports(self):
        path = os.path.join(ROOT, "tools_py", "parity", "verdict_replay.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
                names.update("%s.%s" % (node.module, a.name) for a in node.names)
        for n in names:
            for bad in self.FORBIDDEN:
                self.assertNotIn(bad, n)
        self.assertLessEqual({n.split(".")[0] for n in names},
                             {"argparse", "bisect", "math", "os", "re", "struct", "sys", "dataclasses"})

    def test_importing_loads_neither(self):
        code = ("import sys; import tools_py.parity.verdict_replay; "
                "print(sorted(m for m in sys.modules if 'verdict_core' in m or 'online_' in m))")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "[]")


class TestParserParity(unittest.TestCase):
    """The same raw fixtures through both parsers: a divergence is a test disagreement."""

    def test_row_counts_agree_with_verdict_core(self):
        from tools_py.parity import verdict_core as vc
        for name in ("l8c_A.txt", "l8c_B.txt", "l3c_A.txt", "l3c_B.txt"):
            lines = fixture(name)
            p = vc.parse_log(lines)
            mine = vr.row_counts(vr.parse_log(lines))
            theirs = {"peek": len(p.peek_rows),
                      "actor": len(p.actor_rows),
                      "health": len(vc.actor_field_rows(p.peek_rows, 0x1044, "f32")),
                      "alive": len(vc.actor_field_rows(p.peek_rows, 0xF7A, "u8")),
                      "clock_string": len(vc.clock_rows(p.peek_rows)),
                      "guest_clock": sum(1 for _, it in p.peek_rows if vc.row_static(it, vc.ROUND_TIME_ADDR) is not None),
                      "pad": len(p.pad_events)}
            for valve in vr.REQUIRED_VALVES:
                theirs[valve] = len(vc.valve_rows_by_name(p.peek_rows, valve))
            self.assertEqual(mine, theirs, name)
            self.assertGreater(mine["actor"], 0, name)
            self.assertGreater(mine["total_mp_kills"], 0, name)

    def test_row_times_and_values_agree_with_verdict_core(self):
        from tools_py.parity import verdict_core as vc
        for name in ("l8c_A.txt", "l8c_B.txt", "l3c_A.txt", "l3c_B.txt"):
            lines = fixture(name)
            p = vc.parse_log(lines)
            mine = vr.parse_log(lines)
            theirs_t = [r[0] for r in p.actor_rows]
            mine_t = [r.t for r in mine.rows if r.actor is not None and r.actor.intact and r.actor.pos_nonzero]
            self.assertEqual(len(mine_t), len(theirs_t), name)
            for a, b in zip(mine_t, theirs_t):
                self.assertAlmostEqual(a, b, places=6)
            for valve in vr.REQUIRED_VALVES:
                self.assertEqual([v for _, v in vc.valve_rows_by_name(p.peek_rows, valve)],
                                 [r.valves[valve] for r in mine.rows if r.valves.get(valve) is not None], name)
            self.assertEqual([s for _, s in vc.clock_rows(p.peek_rows)],
                             [r.clock_string for r in mine.rows if r.clock_string is not None], name)


if __name__ == "__main__":
    unittest.main()
