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
    "player_team": (0x694B30, 0x6CC9FC),
    "aiteam_00": (0x694C84, 0x6CCAD4),
    "aiteam_08": (0x694C98, 0x6CCAEC),
    "total_mp_kills": (0x694D10, 0x6B7F70),
}
R1 = 0x0800
GRENADE_TEST_BUTTON = 0x0200        # R2 as a stand-in grenade button (uncalibrated; plan A7)
PERIOD = 0.25


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


class Side:
    """One instance over the SHARED host timeline (A's process clock). Each field is a function of
    host time. `clock_shift` is subtracted from every `[call]` stamp to give the instance's own
    process clock; B's default -6 s means B's process started 6 s before A's (B - 6 s = A), so the
    scorer has to align the clocks (stamps stay positive, as the exe writes them)."""

    def __init__(self, tag, **kw):
        self.tag = tag
        self.clock_shift = kw.pop("clock_shift", 0.0 if tag == "A" else -6.0)
        self.guest = kw.pop("guest", (lambda t: t - 1.0) if tag == "A" else (lambda t: t - 1.3))
        self.pos = kw.pop("pos", (lambda t: (500.0, 100.0, 600.0)) if tag == "A" else (lambda t: (540.0, 100.0, 600.0)))
        self.hp = kw.pop("hp", lambda t: 1.0)
        self.alive = kw.pop("alive", None)          # default: 1 until 0.5 s after hp reaches <= 0
        self.word0 = kw.pop("word0", lambda t: VTABLE)
        self.c8 = kw.pop("c8", 0x40000001 if tag == "A" else 0x80000100)
        self.valves = {"mp_round_count": lambda t: 0,
                       "player_team": (lambda t: 0) if tag == "A" else (lambda t: 8),
                       "aiteam_00": lambda t: 1, "aiteam_08": lambda t: 1,
                       "total_mp_kills": lambda t: 0}
        self.valves.update(kw.pop("valves", {}))
        self.drop_valves = set(kw.pop("drop_valves", ()))
        self.clock_string = kw.pop("clock_string", tag == "A")      # the joiner's may be absent
        self.clock_string_fn = kw.pop("clock_string_fn", None)
        self.pad = kw.pop("pad", [])                # [(host t, buttons)]
        self.end = kw.pop("end", 80.0)
        assert not kw, kw

    def lines(self):
        out, pads, pi, k = [], sorted(self.pad), 0, 0
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
            out.append(self.row(t))
            k += 1
        return out

    def row(self, t):
        a = ACTOR[self.tag]
        x, y, z = self.pos(t)
        hp = self.hp(t)
        alive = self.alive(t) if self.alive is not None else (1 if self.hp(t - 0.5) > 0 else 0)
        words = [0] * 64
        words[0] = self.word0(t)
        words[7], words[8], words[9] = f2w(x), f2w(y), f2w(z)
        words[0xC8 // 4] = self.c8
        parts = ["[peek]", item(a, words), item(a + 0xF78, [(alive << 16) | 0x0100]), item(a + 0x1044, [f2w(hp)])]
        for name, (vaddr, nptr) in VALVE_ITEMS.items():
            if name not in self.drop_valves:
                parts.append(item(vaddr, [nptr, 0x00010000 | (self.valves[name](t) & 0xFFFF)]))
        g = self.guest(t)
        parts.append(item(0x4365C0, [f2w(g)]))
        for name, (vaddr, nptr) in VALVE_ITEMS.items():
            if name not in self.drop_valves:
                parts.append(item(nptr, name_words(name)))
        if self.clock_string:
            s = self.clock_string_fn(t) if self.clock_string_fn else "%02d:%02d" % divmod(max(0, int(360 - g)), 60)
            parts.append(item(0x408F10, str_words(s)))
        return " ".join(parts)


DEATH_T = 40.0


def kill_sides(**over):
    """Baseline: A (host, SEALS, team 0) shoots B (joiner, TERRORISTS, team 8) from 40 units on one
    floor. R1 held 38.0-39.5; B's +0x1044 <= 0 from 40.0; B's aiteam_08 drops at 40.6, A's
    total_mp_kills steps at 40.8 and A's aiteam_08 drops at 41.0 (host). Overrides: a_<field> /
    b_<field>; `*_valves` merges."""
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
    """Spec §5.1 numbers, verbatim. Editing a bar in the module fails this test."""

    def test_bars(self):
        self.assertEqual(vr.ATTRIBUTION_WINDOW_S, 3.0)
        self.assertEqual(vr.ATTRIBUTION_DY_MAX, 10.0)
        self.assertEqual(vr.ATTRIBUTION_3D_MAX, 60.0)
        self.assertEqual(vr.VALVE_WINDOW_GUEST_S, 3.0)
        self.assertEqual(vr.CROSS_INSTANCE_MAX_S, 20.0)
        self.assertEqual(vr.FALL_WINDOW_S, 2.0)
        self.assertEqual(vr.FALL_DROP_MAX, 20.0)
        self.assertEqual(vr.SELF_GRENADE_WINDOW_S, 10.0)
        self.assertEqual(vr.R1_MASK, 0x0800)
        self.assertEqual(vr.KILLS_STEP, 1)


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
        self.assertEqual((v.word, v.killer, v.victim, v.exit_code), (vr.KILL, "A", "B", 0), v.text())
        self.assertTrue(v.text().splitlines()[0].startswith("KILL killer=A victim=B t="), v.text())
        self.assertTrue(all(ok is not False for _, ok, _ in v.clauses), v.text())
        self.assertGreaterEqual(len(v.clauses), 10, v.text())

    def test_kills_step_on_the_victim_instance_only_is_enough(self):
        v = score(kill_sides(a_valves={"total_mp_kills": lambda t: 0},
                             b_valves={"total_mp_kills": step(40.5, 0, 1)}))
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_joiner_clock_string_absent_is_not_needed(self):
        v = score(kill_sides(b_clock_string=False))
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_shooter_flag_names_the_killer(self):
        self.assertEqual(score(kill_sides(), shooter="A").word, vr.KILL)
        v = score(kill_sides(), shooter="B")          # B was the victim: B killed nobody
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())

    def test_killer_grenade_is_a_kill(self):
        v = score(kill_sides(a_pad=[(38.0, GRENADE_TEST_BUTTON), (38.4, 0)]), grenade_mask=GRENADE_TEST_BUTTON)
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_killer_grenade_button_without_calibration_does_not_attribute(self):
        v = score(kill_sides(a_pad=[(38.0, GRENADE_TEST_BUTTON), (38.4, 0)]))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())

    def test_victim_actor_destroyed_at_death_is_no_data(self):
        v = score(kill_sides(b_word0=step(DEATH_T, VTABLE, 0x004061C0)))
        self.assertEqual((v.word, v.exit_code), (vr.NO_DATA, 2), v.text())

    def test_clock_zero_before_the_death_is_round_ended_first(self):
        v = score(kill_sides(a_clock_string_fn=lambda t: "00:00" if t >= 35.0 else "00:05"))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_ROUND_ENDED), v.text())

    def test_round_count_step_before_the_death_is_round_ended_first(self):
        v = score(kill_sides(b_valves={"mp_round_count": step(39.0, 0, 1)}))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_ROUND_ENDED), v.text())

    def test_killer_actor_rows_missing_is_no_data(self):
        v = score(kill_sides(a_word0=lambda t: 0x12345678))
        self.assertEqual(v.word, vr.NO_DATA, v.text())

    def test_cli_prints_and_exits(self):
        a, b = kill_sides()
        d = tempfile.mkdtemp(prefix="replay_")
        pa, pb = os.path.join(d, "run_A.log"), os.path.join(d, "run_B.log")
        for p, s in ((pa, a), (pb, b)):
            with open(p, "w") as f:
                f.write("\n".join(s.lines()) + "\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = vr.main([pa, pb, "--shooter", "A"])
        self.assertEqual(code, 0)
        self.assertTrue(buf.getvalue().startswith("KILL killer=A victim=B t="), buf.getvalue())


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


class TestSyntheticFall(unittest.TestCase):
    def test_victim_y_drop_over_20_in_the_2s_before(self):
        def fall(t):
            y = 140.0 if t < 38.5 else (100.0 if t >= 39.5 else 140.0 - 40.0 * (t - 38.5))
            return (540.0, y, 600.0)
        v = score(kill_sides(b_pos=fall))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_FALL), v.text())


class TestSyntheticSelfGrenade(unittest.TestCase):
    def test_grenade_on_the_victims_own_pad(self):
        v = score(kill_sides(b_pad=[(34.0, GRENADE_TEST_BUTTON), (34.4, 0)]))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_SELF), v.text())

    def test_victim_grenade_before_the_10s_window_is_not_self(self):
        v = score(kill_sides(b_pad=[(28.0, GRENADE_TEST_BUTTON), (28.4, 0)]))
        self.assertEqual(v.word, vr.KILL, v.text())


class TestSyntheticUnattributed(unittest.TestCase):
    def test_no_killer_r1_in_the_3s_before(self):
        v = score(kill_sides(a_pad=[(35.0, R1), (36.5, 0)]))
        self.assertEqual((v.word, v.reason), (vr.NO_KILL, vr.R_UNATTRIBUTED), v.text())

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


class TestSyntheticFreeze(unittest.TestCase):
    def test_victim_guest_clock_stops_across_the_window(self):
        def frozen(t):
            if t < 39.0:
                return t - 1.3
            return 39.0 - 1.3 if t < 42.0 else t - 4.3
        v = score(kill_sides(b_guest=frozen))
        self.assertEqual((v.word, v.exit_code), (vr.NO_DATA, 2), v.text())
        self.assertIn("freeze", v.reason)

    def test_freeze_elsewhere_in_the_round_does_not_change_the_verdict(self):
        def frozen(t):
            return t - 1.0 if t < 20.0 else (19.0 if t < 23.0 else t - 4.0)
        v = score(kill_sides(a_guest=frozen))
        self.assertEqual(v.word, vr.KILL, v.text())


class TestSyntheticSemantics(unittest.TestCase):
    def test_alive_byte_stays_1(self):
        v = score(kill_sides(b_alive=lambda t: 1))
        self.assertEqual((v.word, v.reason, v.exit_code), (vr.KILL_SEMANTICS, "+0xF7A", 1), v.text())
        self.assertTrue(v.text().startswith("KILL-SEMANTICS +0xF7A"), v.text())

    def test_total_mp_kills_steps_on_neither(self):
        v = score(kill_sides(a_valves={"total_mp_kills": lambda t: 0}))
        self.assertEqual((v.word, v.reason, v.exit_code), (vr.KILL_SEMANTICS, "total_mp_kills", 1), v.text())


class TestSyntheticCrossInstanceDelay(unittest.TestCase):
    def test_12s_host_delay_is_kill(self):
        v = score(kill_sides(a_valves={"total_mp_kills": step(52.8, 0, 1), "aiteam_08": step(53.0, 1, 0)}))
        self.assertEqual(v.word, vr.KILL, v.text())

    def test_25s_host_delay_is_no_data(self):
        # NO-DATA, not NO-KILL: the killer instance's steps exist and match the believed semantics,
        # but 25 s on the host clock is past the registered 20 s pairing bar, so they cannot be tied
        # to THIS death (a host backlog or a later event could equally explain them). That is an
        # unpairable read, not evidence that the kill did not happen -- and never a PASS.
        v = score(kill_sides(a_valves={"total_mp_kills": step(65.8, 0, 1), "aiteam_08": step(66.0, 1, 0)}))
        self.assertEqual((v.word, v.exit_code), (vr.NO_DATA, 2), v.text())


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
