"""Sprint 5 close-out fix wave, slice (a) -- RESULT honesty (the acceptance verification of ladder launch 2):

  1. a round whose victim health never moved reads damage=no, not NO-DATA: RunLogTail.watch_hist stores changes only,
     so each round's slice is seeded with the last value known at the round start (launch 2 round 4);
     a round with no watch READ inside it stays NO-DATA;
  2. RESULT contact= prints the spec §5.1 contact verdict (verdict_core via ladder_contact), not the retired 22-unit
     approach() flag;
  3. the kill screens' frame ages and the peeked clock string are recorded: screen_age_s=<A,B> screen_clock=<A,B>.

unittest only; no game.
"""
import os
import time
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import ACTOR, Clock, f2w, peek, tail


def fed_tail(values_by_t):
    clk = Clock(100.0)
    tl = tail(clk)
    tl.watch_offset = 0x1044
    for t, h in values_by_t:
        clk.t = t
        tl._line(peek(health=h))
    return tl


class RoundWatchHistTest(unittest.TestCase):
    def launch2_like(self):
        # round 3: 1.0 -> 0.298 -> 0.0 at ~110; respawn 1.0 at 140; round 4 [200, 400]: 1.0 on every read
        rows = [(100.0 + 0.25 * i, 1.0) for i in range(40)]
        rows += [(110.0, 0.298), (110.25, 0.0)]
        rows += [(110.5 + 0.25 * i, 0.0) for i in range(118)]
        rows += [(140.0 + 0.25 * i, 1.0) for i in range(1200)]
        return fed_tail(rows)

    def test_round_4_of_launch_2_reads_no(self):
        tl = self.launch2_like()
        hist = M.round_watch_hist(tl, 200.0, 400.0)
        self.assertEqual(hist, [(200.0, f2w(1.0), ACTOR)])
        victim = [(t, 0.0, 50.0, 0.0, ACTOR) for t in (200.0, 250.0)]
        self.assertEqual(M.damage_verdict(hist, victim, victim, [210.0]), "no")

    def test_the_seed_does_not_hide_a_drop_inside_the_round(self):
        tl = self.launch2_like()
        hist = M.round_watch_hist(tl, 105.0, 115.0)
        self.assertEqual(hist[0], (105.0, f2w(1.0), ACTOR))
        self.assertEqual([h[0] for h in hist[1:]], [110.0, 110.25])

    def test_no_read_inside_the_round_stays_no_data(self):
        tl = self.launch2_like()
        self.assertEqual(M.round_watch_hist(tl, 500.0, 600.0), [])
        self.assertEqual(M.damage_verdict(M.round_watch_hist(tl, 500.0, 600.0), [], [], []), vc.NO_DATA)

    def test_the_round_loop_uses_the_seeded_slice(self):
        with open(M.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("damage_verdict(round_watch_hist(v.tail, t_round, t_end)", src)
        self.assertNotIn("inside(v.tail.watch_hist)", src)


class ContactTokenTest(unittest.TestCase):
    def test_the_token_is_the_verdict_core_contact_verdict(self):
        mk = lambda status, ok: vc.ContactResult(10, 5.0, 20, status, "", 20.0, 0.0, contact_s=5.0, ok=ok)
        self.assertEqual(M.contact_token(mk("ok", True)), "yes")
        self.assertEqual(M.contact_token(mk("ok", False)), "no")
        self.assertEqual(M.contact_token(mk(vc.NO_DATA, False)), vc.NO_DATA)

    def test_the_result_line_no_longer_prints_the_approach_flag(self):
        with open(M.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("contact={duel.contact.is_set()}", src)
        self.assertIn("contact={contact_token(contact)}", src)


class ScreenFieldsTest(unittest.TestCase):
    def test_fields_for_both_screens_and_missing_ones(self):
        self.assertEqual(M.screen_fields({"A": (0.28, "03:21"), "B": (0.334, "03:21")}),
                         "screen_age_s=0.28,0.33 screen_clock=03:21,03:21")
        self.assertEqual(M.screen_fields({"A": (0.28, None)}),
                         "screen_age_s=0.28,NO-DATA screen_clock=NO-DATA,NO-DATA")
        self.assertEqual(M.screen_fields({}), "screen_age_s=NO-DATA,NO-DATA screen_clock=NO-DATA,NO-DATA")

    def test_evidence_shot_records_the_frame_age_and_the_clock_string(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="closeout_shot_")
        frame = os.path.join(d, "latest.png")
        with open(frame, "wb") as f:
            f.write(b"x")
        old = time.time() - 0.7
        os.utime(frame, (old, old))
        clk = Clock(100.0)
        tl = tail(clk)
        tl._line(peek(clock="03:21"))
        logs = []

        class Sh:
            latest_frame = frame

            def shot(self, label, max_age=None):
                pass

        class C:
            tag, sh = "A", Sh()
        C.tail = tl
        info = {}
        M.evidence_shot(C, "kill_r1", [], logs.append, [], info=info)
        age, clock = info["A"]
        self.assertAlmostEqual(age, 0.7, delta=0.3)
        self.assertEqual(clock, "03:21")
        # a failed capture records nothing (the field reads NO-DATA)
        class ShBad:
            def shot(self, label, max_age=None):
                raise RuntimeError("no frame")
        C.sh = ShBad()
        C.tag = "B"
        M.evidence_shot(C, "kill_r1", [], logs.append, [], info=info)
        self.assertNotIn("B", info)

    def test_the_result_and_ladder_lines_carry_the_fields(self):
        with open(M.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("{screen_fields(kill_screens)}", src)
        line = M.ladder_line(rung=3, controllable=("yes", "yes"), contact_rows=5, rows_read=10, damage="yes",
                             kill="yes", starvation_alarms=0, alarms_cleared=0, max_idle_ms=(1, 2),
                             lagflag_rows=(3, 4), mover="A", screens="screen_age_s=0.28,0.33 screen_clock=03:21,03:21",
                             rung0="PASS")
        self.assertTrue(line.endswith(" mover=A screen_age_s=0.28,0.33 screen_clock=03:21,03:21 RUNG0 PASS"), line)


if __name__ == "__main__":
    unittest.main()
