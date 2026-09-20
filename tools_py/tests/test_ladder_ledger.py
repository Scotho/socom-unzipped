"""Sprint 10 Goal 1: the scheduled ladder's ledger -- one record per run, the three rates, a rendered table."""
import json
import os
import tempfile
import unittest

from tools_py.parity import ladder_ledger as ll

DONE = ("done 0 mpexit=0 KILL harness=829e65bead626ee2c432633209f61668dda5491b path=/c/projects/socom_pc/dist/socom2.exe "
        "mtime=2026-09-19T06:01:09Z sha256=b966050ee35c36d2e6950756163e03d38c2c5048d0fb5e39b17fd5817ec0d17b\n")
DRIVE = ("   389.9s A_RUN BANNER map=frostfire route=direct rounds=4 auto_swap=True\n"
         "  1376.6s A_LADDER-SUMMARY rounds=4/4 usable=4 best_rung=3 kills=2 rungs=1,3,2,3 movers=A,A,A,A stop=rounds done "
         "RUNG0 FAIL back-pressure waits A 383 >= 100; back-pressure waits B 133 >= 100\n")


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = os.path.join(self.tmp.name, "ladder_20260920_090000")
        os.makedirs(self.run)
        with open(self.run + ".done", "w") as fh:
            fh.write(DONE)
        with open(os.path.join(self.run, "drive.log"), "w") as fh:
            fh.write(DRIVE)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_run_becomes_one_record_with_its_outcome_counts_and_identities(self):
        r = ll.read_run(self.run, server="3.143.65.100")
        self.assertEqual(r["outcome"], "KILL")
        self.assertEqual((r["rounds"], r["rounds_asked"], r["usable"], r["kills"], r["best_rung"]), (4, 4, 4, 2, 3))
        self.assertEqual(r["harness"], "829e65bead626ee2c432633209f61668dda5491b")
        self.assertEqual(r["exe_sha256"][:8], "b966050e")
        self.assertEqual(r["server"], "3.143.65.100")
        self.assertEqual(r["stamp"], "ladder_20260920_090000")

    def test_a_lobby_fail_run_records_zero_rounds_and_its_class(self):
        with open(self.run + ".done", "w") as fh:
            fh.write("done 4 mpexit=4 LOBBY-FAIL timeout harness=abc path=x mtime=y sha256=z\n")
        with open(os.path.join(self.run, "drive.log"), "w") as fh:
            fh.write("   12.0s A_LOBBY class=timeout\n")
        r = ll.read_run(self.run, server="s")
        self.assertEqual(r["outcome"], "LOBBY-FAIL")
        self.assertEqual(r["lobby_class"], "timeout")
        self.assertEqual((r["rounds"], r["usable"], r["kills"]), (0, 0, 0))

    def test_the_ledger_appends_and_the_rates_are_over_the_runs_it_holds(self):
        path = os.path.join(self.tmp.name, "ledger.jsonl")
        ll.append(path, ll.read_run(self.run, server="s"))
        ll.append(path, {"stamp": "ladder_2", "outcome": "LOBBY-FAIL", "lobby_class": "timeout", "rounds": 0, "rounds_asked": 4,
                         "usable": 0, "kills": 0, "best_rung": None, "harness": "h", "exe_sha256": "e", "server": "s",
                         "when": "2026-09-20T10:00:00Z", "rc": 4})
        ll.append(path, {"stamp": "ladder_3", "outcome": "NO-KILL", "lobby_class": None, "rounds": 4, "rounds_asked": 4,
                         "usable": 3, "kills": 0, "best_rung": 2, "harness": "h", "exe_sha256": "e", "server": "s",
                         "when": "2026-09-20T11:00:00Z", "rc": 1})
        runs = ll.load(path)
        self.assertEqual(len(runs), 3)
        rates = ll.rates(runs)
        self.assertAlmostEqual(rates["lobby_rate"], 2 / 3)
        self.assertAlmostEqual(rates["round_start_rate"], 7 / 8, msg="usable rounds over rounds played")
        self.assertAlmostEqual(rates["kill_rate"], 2 / 7, msg="kills over usable rounds")
        self.assertEqual(rates["runs"], 3)
        self.assertEqual(rates["consecutive_clean"], 1, "the streak counts from the end: the last run is clean, the one before it a LOBBY-FAIL")

    def test_seven_consecutive_clean_runs_is_the_bar(self):
        runs = [{"outcome": "KILL"}] * 3 + [{"outcome": "NO-KILL"}] * 4
        self.assertEqual(ll.rates([dict(r, rounds=4, usable=4, kills=0) for r in runs])["consecutive_clean"], 7)
        runs2 = [{"outcome": "KILL"}] * 3 + [{"outcome": "CRASH"}] + [{"outcome": "KILL"}] * 2
        self.assertEqual(ll.rates([dict(r, rounds=4, usable=4, kills=1) for r in runs2])["consecutive_clean"], 2)

    def test_the_rendered_table_names_every_run_and_the_bar(self):
        path = os.path.join(self.tmp.name, "ledger.jsonl")
        ll.append(path, ll.read_run(self.run, server="s"))
        md = ll.render(ll.load(path))
        self.assertIn("ladder_20260920_090000", md)
        self.assertIn("KILL", md)
        self.assertIn("7 consecutive", md)
        self.assertIn("829e65be", md)


if __name__ == "__main__":
    unittest.main()
