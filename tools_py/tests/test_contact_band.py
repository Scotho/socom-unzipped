"""Sprint 5 Task 5 finish, slice (iii) -- contact per spec §5.1 (Amendment A, registered pre-match; a bar CHANGE, not
a loosening -- the 22-unit / 20-row gate is replaced):

  * band: same floor |dy| <= 10 and 3-D <= 45;
  * contact: >= 5.0 s of qualifying time with >= 10 rows and row gaps <= 1.25 s; a guest-clock freeze inside the window
    PAUSES the count (neither breaks it nor adds to it); the sampler period is reported beside it;
  * the harness's own contact scorers follow: `ladder_rung`, `damage_verdict`, `ladder_contact`.

unittest only.
"""
import contextlib
import io
import os
import unittest

from tools_py.parity import online_match_ours as M
from tools_py.parity import verdict_core as vc
from tools_py.tests.online_rows import f2w

PERIOD = 0.25


def pair(n=40, gap=30.0, dy=0.0, t0=100.0, period=PERIOD):
    a = [(t0 + i * period, 500.0 + i * 0.5, 50.0, 500.0, 1) for i in range(n)]
    b = [(t0 + i * period + 0.05, 500.0 + i * 0.5 + gap, 50.0 + dy, 500.0, 2) for i in range(n)]
    return a, b


def calls(t0=95.0, t1=130.0, rate=2.0):
    return [(t0 + k / rate, 300 + 10 * k) for k in range(int((t1 - t0) * rate) + 1)]


def clock(t0=95.0, t1=130.0, still=None):
    out = []
    for k in range(int((t1 - t0) * 4) + 1):
        t = t0 + k * 0.25
        s = k * 0.25 if still is None or t < still[0] else (still[0] - t0 if t <= still[1] else k * 0.25)
        out.append((t, f"04:{59 - int(s) % 60:02d}"))
    return out


def scales(v=1.0, t0=95.0, t1=130.0):
    return [(t0 + k * 0.5, v) for k in range(int((t1 - t0) * 2) + 1)]


def guest(t0=95.0, t1=130.0, still=None):
    """0x4365c0 rows at 4 Hz advancing 0.6 guest s per host s, standing still over `still` = (t_from, t_to)."""
    out, v = [], 50.0
    for k in range(int((t1 - t0) * 4) + 1):
        t = t0 + k * 0.25
        if still is None or not (still[0] <= t <= still[1]):
            v += 0.15
        out.append((t, round(v, 4)))
    return out


def score(a, b, clk=None, rt=None, **kw):
    return vc.score_contact(a, b, calls(), calls(), clock() if clk is None else clk, (scales(), scales()),
                            round_time_rows=rt, **kw)


class ContactBandTest(unittest.TestCase):
    def test_the_band_is_45_and_10(self):
        self.assertEqual((vc.CONTACT_3D_MAX_UNITS, vc.CONTACT_DY_MAX_UNITS), (45.0, 10.0))
        self.assertEqual((vc.CONTACT_MIN_S, vc.CONTACT_MIN_ROWS), (5.0, 10))
        self.assertTrue(score(*pair(gap=45.0)).ok)
        self.assertEqual(score(*pair(gap=45.1)).contact_rows, 0)
        self.assertTrue(score(*pair(gap=5.0, dy=10.0)).ok)
        self.assertFalse(score(*pair(gap=5.0, dy=10.1)).ok)

    def test_a_standoff_at_30_units_for_9_75_s_is_contact(self):
        r = score(*pair(gap=30.0))
        self.assertEqual(r.contact_rows, 40)
        self.assertAlmostEqual(r.contact_s, 9.75, places=6)
        self.assertTrue(r.ok)
        self.assertAlmostEqual(r.sampler_period_s, PERIOD, places=6)

    def test_under_5_s_is_not_contact(self):
        r = score(*pair(n=20))                          # 19 gaps x 0.25 = 4.75 s
        self.assertAlmostEqual(r.contact_s, 4.75, places=6)
        self.assertFalse(r.ok)
        self.assertTrue(score(*pair(n=21)).ok)          # 5.0 s

    def test_fewer_than_10_rows_is_not_contact_even_over_5_s(self):
        r = score(*pair(n=9, period=0.75))              # 6.0 s over 9 rows (gaps 0.75 <= 1.25)
        self.assertAlmostEqual(r.contact_s, 6.0, places=6)
        self.assertFalse(r.ok)
        self.assertTrue(score(*pair(n=10, period=0.75)).ok)

    def test_a_gap_over_1_25_s_breaks_the_time(self):
        a, b = pair(n=60)
        a = [row for i, row in enumerate(a) if not 18 <= i < 24]       # 1.75 s without A rows
        r = score(a, b)
        self.assertAlmostEqual(r.contact_s, (59 - 25) * PERIOD, places=6)   # row 24 follows the 1.75 s gap itself

    def test_a_guest_clock_freeze_pauses_the_count(self):
        a, b = pair(n=60)                               # 100.0 .. 114.75
        still = (104.0, 108.0)                          # a 4 s freeze: both clock string and 0x4365c0 stand
        clk = clock(still=still)
        without = score(a, b, clk=clk)                  # no guest clock supplied: the frozen string breaks the run
        self.assertLess(without.contact_s, 7.0)
        r = score(a, b, clk=clk, rt=(guest(still=still), guest()))
        self.assertTrue(r.ok, r)
        self.assertAlmostEqual(r.contact_s, 14.75 - 4.0, delta=0.6)   # the freeze's span is not counted
        self.assertGreater(r.paused_rows, 10)

    def test_the_cli_prints_the_sampler_period(self):
        out = io.StringIO()
        fx = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "online")
        with contextlib.redirect_stdout(out):
            vc.main(["contact", os.path.join(fx, "kill2_A_closest.txt"), os.path.join(fx, "kill2_B_closest.txt"),
                     "--offset-b", str(418.5 - 412.7)])
        self.assertIn("sampler_s=", out.getvalue())
        self.assertIn("contact_s=", out.getvalue())


class HarnessContactTest(unittest.TestCase):
    def test_ladder_rung_reads_the_band_result(self):
        self.assertEqual(M.ladder_rung(("yes", "yes"), True, "yes"), 3)
        self.assertEqual(M.ladder_rung(("yes", "yes"), True, "no"), 2)
        self.assertEqual(M.ladder_rung(("yes", "yes"), False, "yes"), 1)
        self.assertEqual(M.ladder_rung(("yes", "yes"), None, "no"), 1)
        self.assertEqual(M.ladder_rung(("yes", "NO-DATA"), True, "yes"), 0)

    def test_damage_at_30_units_in_the_band_counts(self):
        victim = [(100.0 + 0.25 * i, 0.0, 100.0, 0.0, 1) for i in range(80)]
        shooter = [(100.0 + 0.25 * i, 30.0, 100.0, 0.0, 2) for i in range(80)]
        hist = [(100.0, f2w(1.0), 1), (110.0, f2w(0.8), 1)]
        self.assertEqual(M.damage_verdict(hist, victim, shooter, [108.5]), "yes")
        far = [(t, 46.0, y, z, a) for t, _, y, z, a in shooter]
        self.assertEqual(M.damage_verdict(hist, victim, far, [108.5]), "no")

    def test_the_ladder_line_carries_contact_seconds_and_the_sampler(self):
        line = M.ladder_line(rung=2, controllable=("yes", "yes"), contact_rows=40, rows_read=900, damage="no",
                             kill="no", starvation_alarms=0, alarms_cleared=0, max_idle_ms=(1, 2),
                             lagflag_rows=(3, 4), contact_s=9.75, sampler_s=0.25)
        self.assertIn("contact_s=9.75 contact_rows=40 sampler_s=0.25 ", line)


if __name__ == "__main__":
    unittest.main()
