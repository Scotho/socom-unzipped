"""Sprint 6 Task 2: the per-launch lobby summary (tools_py/parity/lobby_report.py) on synthetic drive logs."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from tools_py.parity import lobby_report as R


def log(*tagged, trailer=("mpexit=0 harness=abc path=x",)):
    """Drive-log lines from (tag, message) pairs, with Shell.log's time prefix and an untagged trailer."""
    lines = [f"{10.0 * i:6.1f}s {tag}_{msg}" for i, (tag, msg) in enumerate(tagged)]
    return lines + list(trailer)


CLEAN = log(
    ("A", "screen login after 0.6s"), ("B", "screen login after 0.8s"),
    ("A", "screen briefing_room after 0.7s"), ("B", "screen briefing_room after 0.9s"),
    ("A", "[lobby] create-game:select press=up verified=True attempt=1"),
    ("A", "[lobby] create-game:enter press=cross verified=True attempt=1"),
    ("A", "[lobby] create-game:create press=square verified=True attempt=1"),
    ("A", "map CROSS check: SELECTED MAPS panel mean |diff| 3.52"),
    ("B", "[lobby] join:list press=cross verified=True attempt=1"),
    ("B", "[lobby] join:enter press=cross verified=True attempt=1"),
    ("A", "liveness OK: 173 in-game peek rows, 14307 log lines"),
    ("B", "liveness OK: 173 in-game peek rows, 15016 log lines"),
    ("A", "LOBBY class=ok"),
    ("A", "RESULT round=1 PASS harness=171290b5524e signal=health on=B"),
)

CREATE_FAIL = log(
    ("A", "screen briefing_room after 0.7s"),
    ("A", "[lobby] create-game:select press=up verified=True attempt=1"),
    ("A", "[lobby] create-game:enter press=cross verified=False attempt=1"),
    ("A", "LOBBY RESEND create-game:enter attempt=1"),
    ("A", "[lobby] create-game:enter press=cross verified=True attempt=2"),
    ("A", "[lobby] create-game:create press=square verified=False attempt=1"),
    ("A", "LOBBY RESEND create-game:create attempt=1"),
    ("A", "[lobby] create-game:create press=square verified=False attempt=2"),
    ("A", "LOBBY RESEND create-game:create attempt=2"),
    ("A", "[lobby] create-game:create press=square verified=False attempt=3"),
    ("A", "LOBBY RESEND create-game:create attempt=3"),
    ("A", "[lobby] create-game:create press=square verified=False attempt=4"),
    ("A", "RESULT LOBBY-FAIL create-game:create -- CREATE never showed after SQUARE and 3 re-sends -- see the capture"),
    ("A", "LOBBY class=create-game:create"),
    ("A", "LADDER-SUMMARY rounds=0/4 usable=0 stop=LOBBY-FAIL create-game:create"),
    trailer=("mpexit=4 harness=abc path=x",),
)

PRE_LOGIN = log(
    ("B", "main menu after 2 presses"),
    ("B", "TIMEOUT waiting for login"),
    ("B", "RESULT LOBBY-FAIL pre-login -- the LOGIN screen never showed"),
    ("B", "LOBBY class=pre-login"),
    trailer=("mpexit=4 harness=abc path=x",),
)


class Summarise(unittest.TestCase):
    def test_clean_launch(self):
        s = R.summarise(CLEAN)
        self.assertEqual(s["outcome"], R.OUTCOME_GAMEPLAY)
        self.assertEqual(s["cls"], "ok")
        self.assertEqual(s["mpexit"], 0)
        a, b = s["instances"]["A"], s["instances"]["B"]
        self.assertEqual(dict(a["presses"]), {"create-game:select": 1, "create-game:enter": 1, "create-game:create": 1})
        self.assertEqual(dict(b["presses"]), {"join:list": 1, "join:enter": 1})
        self.assertEqual(dict(a["unverified"]), {})
        self.assertEqual(dict(a["resends"]), {})
        self.assertEqual(dict(b["resends"]), {})
        self.assertTrue(a["gameplay"] and b["gameplay"])
        self.assertEqual(a["last_stage"], "create-game:create")
        self.assertEqual(b["last_stage"], "join:enter")
        self.assertEqual(a["results"], ["round=1"])
        self.assertEqual(s["ended_stage"], "join:enter")     # the last [lobby] line was B's

    def test_create_game_failure_after_three_resends(self):
        s = R.summarise(CREATE_FAIL)
        self.assertEqual(s["outcome"], R.OUTCOME_LOBBY_FAIL)
        self.assertEqual(s["cls"], "create-game:create")
        self.assertEqual(s["ended_stage"], "create-game:create")
        self.assertEqual(s["mpexit"], 4)
        a = s["instances"]["A"]
        self.assertEqual(a["presses"]["create-game:create"], 4)
        self.assertEqual(a["unverified"]["create-game:create"], 4)
        self.assertEqual(a["resends"]["create-game:create"], 3)
        self.assertEqual(a["presses"]["create-game:enter"], 2)
        self.assertEqual(a["unverified"]["create-game:enter"], 1)
        self.assertEqual(a["resends"]["create-game:enter"], 1)
        self.assertEqual(a["results"], ["LOBBY-FAIL"])
        self.assertFalse(a["gameplay"])
        self.assertEqual(dict(s["instances"]["B"]["presses"]), {})

    def test_pre_login_failure(self):
        s = R.summarise(PRE_LOGIN)
        self.assertEqual(s["outcome"], R.OUTCOME_LOBBY_FAIL)
        self.assertEqual(s["cls"], "pre-login")
        self.assertIsNone(s["ended_stage"])            # no [lobby] press and no screen was ever reached
        self.assertEqual(dict(s["instances"]["B"]["presses"]), {})
        self.assertEqual(dict(s["instances"]["A"]["presses"]), {})

    def test_pre_lobby_line_era_reports_outcome_only(self):
        # A Sprint 5 ladder: no [lobby] lines, a map-CROSS re-send, liveness OK.
        s = R.summarise(log(("A", "screen briefing_room after 0.7s"),
                            ("A", "LOBBY RESEND map-cross-dropped attempt=1"),
                            ("A", "liveness OK: 171 in-game peek rows"),
                            ("A", "LOBBY class=ok"),
                            ("A", "RESULT round=1 ROUND-END (round; unattributed -- NOT a kill)")))
        self.assertEqual(s["outcome"], R.OUTCOME_GAMEPLAY)
        self.assertEqual(s["instances"]["A"]["resends"]["map-cross-dropped"], 1)
        self.assertEqual(s["ended_stage"], "map-cross-dropped")

    def test_other_result_and_no_result(self):
        s = R.summarise(log(("A", "screen login after 0.6s"), ("A", "RESULT NO-CONTROL no pad rows")))
        self.assertEqual((s["outcome"], s["cls"], s["ended_stage"]), (R.OUTCOME_RESULT, "NO-CONTROL", "login"))
        s = R.summarise(["A_on-screen keyboard never opened for 'socom': refusing to type", "mpexit=1"])
        self.assertEqual((s["outcome"], s["cls"], s["mpexit"]), (R.OUTCOME_NONE, None, 1))

    def test_lobby_fail_on_one_instance_names_that_instance_stage(self):
        s = R.summarise(log(("A", "[lobby] create-game:create press=square verified=True attempt=1"),
                            ("B", "[lobby] join:list press=cross verified=False attempt=1"),
                            ("B", "RESULT LOBBY-FAIL join:list")))
        self.assertEqual(s["cls"], "join:list")
        self.assertEqual(s["ended_stage"], "join:list")

    def test_split_line_without_time_prefix_and_untagged(self):
        self.assertEqual(R.split_line(" 305.8s A_LOBBY RESEND x attempt=1"), ("A", "LOBBY RESEND x attempt=1"))
        self.assertEqual(R.split_line("B_TIMEOUT waiting for login"), ("B", "TIMEOUT waiting for login"))
        self.assertEqual(R.split_line("[run_detached] RELEASED"), (None, "[run_detached] RELEASED"))
        self.assertEqual(R.summarise([]), {"instances": R.summarise([])["instances"], "outcome": R.OUTCOME_NONE,
                                           "cls": None, "ended_stage": None, "mpexit": None})


class Cli(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="lobby_report_")

    def write(self, name, lines):
        p = os.path.join(self.dir, f"drive_{name}.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return p

    def test_two_launch_totals(self):
        paths = [self.write("s6_l1", CLEAN), self.write("s6_l2", CREATE_FAIL)]
        out = io.StringIO()
        with redirect_stdout(out):
            rc = R.main(paths)
        self.assertEqual(rc, 0)
        rows = out.getvalue().splitlines()
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0].startswith("s6_l1 "))
        self.assertIn("gameplay", rows[0])
        self.assertIn("resends=-", rows[0])
        self.assertIn("unverified=-", rows[0])
        self.assertTrue(rows[1].startswith("s6_l2 "))
        self.assertIn("lobby-fail", rows[1])
        self.assertIn("create-game:create", rows[1])
        self.assertIn("ended=create-game:create", rows[1])
        self.assertIn("resends=A:create-game:create=3 A:create-game:enter=1", rows[1])
        self.assertIn("unverified=A:create-game:create=4 A:create-game:enter=1", rows[1])
        self.assertEqual(rows[2], "TOTAL launches=2 gameplay=1/2 classes: create-game:create=1")

    def test_totals_counts_every_class(self):
        s = [R.summarise(CLEAN), R.summarise(CREATE_FAIL), R.summarise(PRE_LOGIN), R.summarise(PRE_LOGIN),
             R.summarise(["A_RESULT NO-CONTROL"]), R.summarise([])]
        self.assertEqual(R.totals(s), "TOTAL launches=6 gameplay=1/6 classes: create-game:create=1 none=1 "
                                      "pre-login=2 result:NO-CONTROL=1")

    def test_usage_without_args(self):
        err = io.StringIO()
        from contextlib import redirect_stderr
        with redirect_stderr(err):
            self.assertEqual(R.main([]), 2)
        self.assertIn("usage", err.getvalue())

    def test_launch_name(self):
        self.assertEqual(R.launch_name("logs/parity/drive_s5_t5_ladder2.txt"), "s5_t5_ladder2")
        self.assertEqual(R.launch_name("C:\\x\\detached_s6_ladder1.txt"), "s6_ladder1")


if __name__ == "__main__":
    unittest.main()
