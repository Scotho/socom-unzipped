"""Sprint 5 Task 2 Steps 2-6 -- `tools_py.parity.sp_death_probe`'s pure analysis.

unittest only. Rows are built as real `[peek]` log text and read back through the module's own
parser (`read_log` -> `Row`), so the actor-by-static, health/alive-by-offset and matrix extraction are
exercised end to end; every expected number is known by construction.
"""
import math
import struct
import unittest

from tools_py.parity import sp_death_probe as sp

ACTOR = 0x017941D0


def f2w(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def item(addr, words):
    return f"@{addr:x}: " + " ".join(f"{w & 0xFFFFFFFF:08x}(.)" for w in words)


def peek_line(pos=(100.0, 10.0, 200.0), theta_deg=0.0, health=1.0, alive=1, cam=None, word0=sp.ACTOR_VTABLE,
              angvel=0.0, actor=ACTOR):
    th = math.radians(theta_deg)
    c, s = math.cos(th), math.sin(th)
    blk = [0] * 64
    blk[0] = word0
    blk[7], blk[8], blk[9] = (f2w(v) for v in pos)
    blk[sp.ANGVEL_OFFSET // 4] = f2w(angvel)
    blk[sp.QUAT_OFFSET // 4:sp.QUAT_OFFSET // 4 + 4] = [0, f2w(math.sin(th / 2)), 0, f2w(math.cos(th / 2))]
    m = [c, 0, s, 0, 0, 1, 0, 0, -s, 0, c, 0, pos[0], pos[1], pos[2], 1]
    blk[sp.MATRIX_OFFSET // 4:sp.MATRIX_OFFSET // 4 + 16] = [f2w(v) for v in m]
    cam = cam or (pos[0], pos[1] + 19.7, pos[2] + 20.6)
    parts = [item(sp.CAMERA_ADDR, [f2w(v) for v in cam]),
             item(actor, blk),
             item(actor + 0xF78, [alive << 16]),
             item(actor + sp.HEALTH_OFFSET, [f2w(health)]),
             item(sp.ACTOR_STATIC, [actor, 0, 0, 0])]
    return "[peek] " + " ".join(parts)


def rows_from(lines, period=0.25):
    peek, _ = sp.read_log(lines)
    return [sp.Row(i * period, items) for i, items in peek]


class RowExtraction(unittest.TestCase):
    def test_row_reads_actor_fields_through_the_static(self):
        r = rows_from([peek_line(theta_deg=30.0, health=0.4, alive=2)])[0]
        self.assertEqual(r.actor, ACTOR)
        self.assertEqual(r.word0, sp.ACTOR_VTABLE)
        self.assertAlmostEqual(r.health, 0.4, places=5)
        self.assertEqual(r.alive, 2)
        self.assertAlmostEqual(sp.yaw_deg(r), 30.0, places=3)

    def test_facing_is_minus_row2(self):
        # theta = 0: identity, walks along -z -> atan2(-1, 0) = -90 (kill2 A's first hold: truth -90.5).
        self.assertAlmostEqual(sp.facing_deg(rows_from([peek_line(theta_deg=0.0)])[0]), -90.0, places=3)
        # theta = 90: row2 = (-1, 0, 0) -> walks along +x -> 0 deg.
        self.assertAlmostEqual(sp.facing_deg(rows_from([peek_line(theta_deg=90.0)])[0]), 0.0, places=3)

    def test_word0_survives_a_changed_block_head(self):
        r = rows_from([peek_line(word0=0x12345678)])[0]
        self.assertEqual(r.actor, ACTOR)                     # still found through the static
        self.assertEqual(r.word0, 0x12345678)
        self.assertIsNone(r.matrix)                          # but not trusted as the actor block


class Holds(unittest.TestCase):
    def test_classification(self):
        N = sp.PAD_NEUTRAL
        pads = [(0.0, 0, N, N, N, N), (1.0, 0, N + 16, N, N, N), (2.0, 0, N, N, N, N),
                (3.0, 0, N, 0, N, N), (4.0, 0, N, N, N, N), (5.0, 0, N, N, N, 0),
                (6.5, 0, N, N, N, N), (7.0, 0, N + 5, N, N, 0), (8.0, 0, N, N, N, N)]
        hs = sp.holds_from_pads(pads)
        self.assertEqual([(h.kind, h.start, h.release) for h in hs],
                         [("rx", 1.0, 2.0), ("ry", 3.0, 4.0), ("fwd", 5.0, 6.5), ("other", 7.0, 8.0)])
        self.assertEqual(hs[0].value, N + 16)

    def test_value_change_splits_a_hold(self):
        N = sp.PAD_NEUTRAL
        hs = sp.holds_from_pads([(0.0, 0, N + 16, N, N, N), (1.0, 0, N + 32, N, N, N), (2.0, 0, N, N, N, N)])
        self.assertEqual([(h.value, h.start, h.release) for h in hs], [(N + 16, 0.0, 1.0), (N + 32, 1.0, 2.0)])


class YawAndHeading(unittest.TestCase):
    def build(self, levels_rates, dead=16):
        """A 4 Hz log: rest, then for each (level, deg/s) a 1.0 s rx hold turning at that rate (zero at or
        below `dead`), then rest. Returns (rows, holds)."""
        N = sp.PAD_NEUTRAL
        lines, pads, theta, t = [], [], 0.0, 0.0
        period = 0.25

        def emit(n, rate):
            nonlocal theta, t
            for _ in range(n):
                lines.append(peek_line(theta_deg=theta))
                theta += rate * period
                t += period

        emit(8, 0.0)
        for level, rate in levels_rates:
            pads.append((t, 0, N + level, N, N, N))
            emit(4, rate if level > dead else 0.0)
            pads.append((t, 0, N, N, N, N))
            emit(10, 0.0)
        rows = rows_from(lines, period)
        return rows, sp.holds_from_pads(pads)

    def test_rates_and_dead_zone(self):
        rows, holds = self.build([(16, 40.0), (32, 20.0), (48, 40.0), (64, 60.0), (96, 80.0), (127, 110.0)])
        table = sp.yaw_table(rows, holds)
        self.assertEqual(len(table), 6)
        self.assertAlmostEqual(table[0]["sweep_deg"], 0.0, places=3)
        self.assertAlmostEqual(table[-1]["sweep_deg"], 110.0, places=2)
        self.assertAlmostEqual(table[-1]["rate_deg_s"], 110.0, places=2)
        v = sp.yaw_verdict(table)["positive"]
        self.assertEqual(v["dead_zone_level"], 16)
        self.assertTrue(v["strictly_increasing"])

    def test_non_monotonic_is_reported(self):
        rows, holds = self.build([(32, 50.0), (48, 40.0), (64, 60.0)], dead=0)
        v = sp.yaw_verdict(sp.yaw_table(rows, holds))["positive"]
        self.assertFalse(v["strictly_increasing"])

    def test_sweep_past_180_unwraps(self):
        rows, holds = self.build([(127, 300.0)], dead=0)
        self.assertAlmostEqual(sp.yaw_table(rows, holds)[0]["sweep_deg"], 300.0, places=2)

    def test_heading_validation_error_known(self):
        N = sp.PAD_NEUTRAL
        # Facing theta = 90 -> walks along +x (0 deg). The actual walk goes to +x and slightly +z: atan2(3, 40).
        lines = [peek_line(pos=(500.0, 0.0, 0.0), theta_deg=90.0)] * 4
        lines += [peek_line(pos=(500.0 + 8.0 * k, 0.0, 0.6 * k), theta_deg=90.0) for k in range(1, 6)]
        lines += [peek_line(pos=(540.0, 0.0, 3.0), theta_deg=90.0)] * 4
        rows = rows_from(lines)
        holds = sp.holds_from_pads([(0.9, 0, N, N, N, 0), (2.2, 0, N, N, N, N)])
        recs, summary = sp.heading_validation(rows, holds)
        self.assertTrue(recs[0]["used"], recs[0])
        self.assertAlmostEqual(recs[0]["error_deg"], -math.degrees(math.atan2(3.0, 40.0)), places=2)
        self.assertEqual(summary["n_used"], 1)
        self.assertFalse(summary["meets_bar"])              # fewer than six holds never meets the bar

    def test_deflected_walk_is_excluded(self):
        N = sp.PAD_NEUTRAL
        lines = [peek_line(pos=(500.0, 0.0, 0.0))] * 4
        lines += [peek_line(pos=(530.0, 0.0, 0.0)), peek_line(pos=(530.0, 0.0, -30.0)), peek_line(pos=(500.0, 0.0, -30.0))]
        lines += [peek_line(pos=(500.0, 0.0, -30.0))] * 4
        holds = sp.holds_from_pads([(0.9, 0, N, N, N, 0), (1.9, 0, N, N, N, N)])
        recs, _ = sp.heading_validation(rows_from(lines), holds)
        self.assertFalse(recs[0]["used"])
        self.assertIn("straightness", recs[0]["reason"])


class Pitch(unittest.TestCase):
    def test_elevation_delta_sign(self):
        N = sp.PAD_NEUTRAL
        lines = [peek_line(cam=(100.0, 30.0, 220.0))] * 6 + [peek_line(cam=(100.0, 40.0, 220.0))] * 12
        holds = sp.holds_from_pads([(1.0, 0, N, 0, N, N), (2.0, 0, N, N, N, N)])
        p = sp.pitch_table(rows_from(lines), holds)[0]
        self.assertGreater(p["delta_elev_deg"], 0.0)
        self.assertFalse(p["camera_frozen"])


class DeathTable(unittest.TestCase):
    def test_goal2_death(self):
        lines = [peek_line(health=1.0)] * 4 + [peek_line(health=0.62)] * 3 + [peek_line(health=0.2)] * 2
        lines += [peek_line(health=0.0, alive=1)] * 2 + [peek_line(health=0.0, alive=2)] * 8
        d = sp.death_table(rows_from(lines))
        self.assertIsNotNone(d["death"])
        x = d["death"]
        self.assertEqual(x["t"], 9 * 0.25)
        self.assertTrue(x["intermediate_before_death"])
        self.assertTrue(x["word0_is_vtable"])
        self.assertAlmostEqual(x["alive_leaves_1_dt_s"], 0.5)
        self.assertEqual(x["alive_leaves_1_value"], 2)
        self.assertTrue(x["goal2_pass"])
        self.assertEqual([round(v, 2) for _, v in d["intermediates"]], [0.62, 0.2])

    def test_first_read_zero_is_not_a_death(self):
        d = sp.death_table(rows_from([peek_line(health=0.0)] * 5 + [peek_line(health=1.0)] * 5))
        self.assertIsNone(d["death"])

    def test_death_on_another_actor_is_not_a_death(self):
        lines = [peek_line(health=1.0)] * 3 + [peek_line(health=0.0, actor=ACTOR + 0x2000)] * 3
        self.assertIsNone(sp.death_table(rows_from(lines))["death"])

    def test_straight_to_zero_fails_the_intermediate_bar(self):
        lines = [peek_line(health=1.0)] * 3 + [peek_line(health=0.0, alive=2)] * 3
        x = sp.death_table(rows_from(lines))["death"]
        self.assertFalse(x["intermediate_before_death"])
        self.assertFalse(x["goal2_pass"])

    def test_alive_leaving_late_fails(self):
        lines = [peek_line(health=1.0)] * 3 + [peek_line(health=0.5)] * 2
        lines += [peek_line(health=0.0, alive=1)] * 12 + [peek_line(health=0.0, alive=2)] * 2
        x = sp.death_table(rows_from(lines))["death"]
        self.assertAlmostEqual(x["alive_leaves_1_dt_s"], 3.0)
        self.assertFalse(x["goal2_pass"])

    def test_goal2_requires_word0_intact_at_the_death_row(self):
        # Fix round 1: identical to test_goal2_death except the block head no longer reads the vtable at
        # the death row (a destroyed actor: FUN_0029ed30 writes the base vtable 0x4061c0).
        freed = 0x004061C0
        lines = [peek_line(health=1.0)] * 4 + [peek_line(health=0.62)] * 3
        lines += [peek_line(health=0.0, alive=2, word0=freed)] * 4
        x = sp.death_table(rows_from(lines))["death"]
        self.assertIsNotNone(x)
        self.assertFalse(x["word0_is_vtable"])
        self.assertTrue(x["intermediate_before_death"])
        self.assertFalse(x["goal2_pass"])


class LiveDeathRow(unittest.TestCase):
    """sp_death_probe.live_death_row: the live stand's death detector (Probe.check_death)."""

    def test_intact_block_death_is_found(self):
        rows = rows_from([peek_line(health=1.0)] * 3 + [peek_line(health=0.0, alive=2)])
        r = sp.live_death_row(rows)
        self.assertIsNotNone(r)
        self.assertEqual(r.health, 0.0)

    def test_freed_block_reading_zero_is_not_a_death(self):
        # Run 3's mission failure: the block's word 0 became the base vtable and +0x1044 read heap data.
        rows = rows_from([peek_line(health=0.72)] * 3 + [peek_line(health=0.0, word0=0x004061C0)] * 3)
        self.assertIsNone(sp.live_death_row(rows))


class FieldSearch(unittest.TestCase):
    def test_matrix_words_are_candidates_and_position_is_not(self):
        N = sp.PAD_NEUTRAL
        lines, pads, theta, t = [], [], 0.0, 0.0
        for k in range(3):
            lines += [peek_line(theta_deg=theta)] * 12
            t += 12 * 0.25
            pads.append((t - 0.1, 0, N + 64, N, N, N))      # the pad write precedes the first turned row
            theta += 40.0
            lines += [peek_line(theta_deg=theta)] * 4
            t += 4 * 0.25
            pads.append((t, 0, N, N, N, N))
        lines += [peek_line(theta_deg=theta)] * 12
        fs = sp.field_search(rows_from(lines), sp.holds_from_pads(pads))
        fields = {c["field"] for c in fs["candidates"]}
        self.assertEqual(fs["windows"]["rx"], 3)
        for off in (0x80, 0x88, 0xA0, 0xA8, 0x74, 0x7C):
            self.assertIn(f"actor+{off:#05x}", fields)
        self.assertNotIn("actor+0x01c", fields)


class ScreenState(unittest.TestCase):
    def test_committed_hud_reference_is_hud_without_popup(self):
        """2026-09-16: the HUD reference is a lit-look gameplay frame with no pop-up; the prompt template has its own"""
        from PIL import Image
        with Image.open("scripts/parity/ref_hud_ours.png") as im:
            hud, popup, panel, text = sp.screen_state(im.convert("RGB"))
        self.assertTrue(hud, panel)
        self.assertFalse(popup, text)

    def test_committed_prompt_image_is_hud_with_popup(self):
        from PIL import Image
        with Image.open(sp.PROMPT_REF) as im:
            hud, popup, panel, text = sp.screen_state(im.convert("RGB"))
        self.assertTrue(hud, panel)
        self.assertTrue(popup, text)

    def test_black_letterbox_frame_is_not_gameplay(self):
        import numpy as np
        frame = np.zeros((448, 640, 3), dtype=np.uint8)
        frame[100:330] = 180                              # a bright picture band between black bars
        gameplay, popup, band, _ = sp.screen_state(frame)
        self.assertEqual(band, 0.0)
        self.assertFalse(gameplay)
        self.assertFalse(popup)

    def test_lit_frame_without_prompt_is_gameplay_without_popup(self):
        import numpy as np
        rng = np.random.default_rng(1)
        frame = rng.integers(20, 200, size=(448, 640, 3), dtype=np.uint8)
        gameplay, popup, _, dist = sp.screen_state(frame)
        self.assertTrue(gameplay)
        self.assertGreater(dist, sp.PROMPT_MAX_DIST)
        self.assertFalse(popup)


if __name__ == "__main__":
    unittest.main()
