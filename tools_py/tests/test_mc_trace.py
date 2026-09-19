import unittest

from tools_py.parity import mc_trace

# Verbatim from logs/parity/gate/s8_empty_card_title/title.game.log (the empty-card title run of
# cef8d83): port 0 is an inserted formatted card, port 1 is empty, and the game's Chdir onto the
# save folder that does not exist yet answers -4.
EMPTY_CARD_LOG = """
[GS] frame 12
[MC] GetInfo port=0 type=2 free=8000 format=1 result=0
[MC] Sync cmd=1 result=0
[MC] Sync cmd=12 result=-4
[MC] GetInfo port=1 type=0 free=0 format=0 result=-4
[MC] Sync cmd=1 result=-4
some other line
"""

# Verbatim from the driven save on an empty card (2026-09-19, logs/parity/gate/s8_save_empty1):
# Mkdir, Chdir, then Open (result = the file descriptor), Write (result = the byte count) and Close
# per file. A Delete of a file that is not there yet answers -4 and the game carries on, so a
# negative result is not automatically the finding either.
SAVE_LOG = """
[MC] GetInfo port=0 type=2 free=8000 format=1 result=0
[MC] Sync cmd=1 result=0
[MC] Sync cmd=11 result=0
[MC] Sync cmd=12 result=0
[MC] Sync cmd=2 result=1
[MC] Sync cmd=6 result=964
[MC] Sync cmd=3 result=0
[MC] Sync cmd=15 result=-4
[MC] Sync cmd=2 result=3
[MC] Sync cmd=6 result=4784
[MC] Sync cmd=3 result=0
"""


class ParseLine(unittest.TestCase):
    def test_getinfo_fields(self):
        ev = mc_trace.parse_line("[MC] GetInfo port=0 type=2 free=8000 format=1 result=0")
        self.assertEqual(ev["kind"], "getinfo")
        self.assertEqual((ev["port"], ev["type"], ev["free"], ev["format"], ev["result"]),
                         (0, 2, 8000, 1, 0))

    def test_sync_cmd_is_named_from_the_libmc_code(self):
        self.assertEqual(mc_trace.parse_line("[MC] Sync cmd=6 result=0")["name"], "Write")
        self.assertEqual(mc_trace.parse_line("[MC] Sync cmd=2 result=0")["name"], "Open")

    def test_unknown_cmd_is_reported_not_guessed(self):
        self.assertEqual(mc_trace.parse_line("[MC] Sync cmd=99 result=0")["name"], "cmd99")

    def test_runtime_log_lines_are_kept_in_order(self):
        ev = mc_trace.parse_line("[MC] Chdir port=0 '/BASCUS-97275SOCOMII' -> -4")
        self.assertEqual((ev["kind"], ev["name"]), ("log", "Chdir"))

    def test_non_mc_lines_are_ignored(self):
        self.assertIsNone(mc_trace.parse_line("[GS] frame 12"))
        self.assertIsNone(mc_trace.parse_line(""))


class ParseLog(unittest.TestCase):
    def test_only_mc_lines_survive(self):
        events = mc_trace.parse_log(EMPTY_CARD_LOG)
        self.assertEqual([e["name"] for e in events],
                         ["GetInfo", "GetInfo", "Chdir", "GetInfo", "GetInfo"])

    def test_failures_are_the_negative_results(self):
        bad = mc_trace.failures(mc_trace.parse_log(EMPTY_CARD_LOG))
        self.assertEqual([(e["name"], e["result"]) for e in bad],
                         [("Chdir", -4), ("GetInfo", -4), ("GetInfo", -4)])

    def test_a_file_descriptor_and_a_byte_count_are_not_failures(self):
        """Open's positive result is the fd and Write's is the byte count; reading "result != 0"
        as an error called the 2026-09-19 driven save a failure when it had worked."""
        bad = mc_trace.failures(mc_trace.parse_log(SAVE_LOG))
        self.assertEqual([(e["name"], e["result"]) for e in bad], [("Delete", -4)])


class Sequence(unittest.TestCase):
    def test_repeats_collapse_into_counted_runs(self):
        self.assertEqual(mc_trace.op_sequence(mc_trace.parse_log(SAVE_LOG)),
                         [("GetInfo", 0, 2), ("Mkdir", 0, 1), ("Chdir", 0, 1), ("Open", 1, 1),
                          ("Write", 964, 1), ("Close", 0, 1), ("Delete", -4, 1), ("Open", 3, 1),
                          ("Write", 4784, 1), ("Close", 0, 1)])

    def test_format_sequence_names_the_results(self):
        self.assertEqual(mc_trace.format_sequence(mc_trace.parse_log(EMPTY_CARD_LOG)).splitlines(),
                         ["GetInfo OK x2", "Chdir NO-ENTRY x1", "GetInfo NO-ENTRY x2"])

    def test_a_positive_result_prints_as_a_value(self):
        self.assertEqual(mc_trace.result_name(964), "ok:964")
        self.assertEqual(mc_trace.result_name(-5), "DENIED")

    def test_write_ops_drop_the_getinfo_polling(self):
        self.assertEqual([e["name"] for e in mc_trace.write_ops(mc_trace.parse_log(SAVE_LOG))],
                         ["Mkdir", "Chdir", "Open", "Write", "Close", "Delete", "Open", "Write",
                          "Close"])


class ResultNames(unittest.TestCase):
    """The negative codes MemoryCard.cpp actually returns, read off its own kMcResult* constants
    (ps2xRuntime/src/lib/Kernel/Stubs/MemoryCard.cpp:27-33): -1 ChangedCard, -2 NoFormat,
    -4 NoEntry, -5 DeniedPermit, -6 NotEmpty, -7 UpLimitHandle. -3 is not defined there and the
    stub never returns it, so it is reported as the raw code rather than guessed."""

    def test_minus_three_is_not_a_code_this_runtime_returns(self):
        self.assertEqual(mc_trace.result_name(-3), "-3")

    def test_minus_four_is_no_entry(self):
        self.assertEqual(mc_trace.result_name(-4), "NO-ENTRY")

    def test_minus_five_is_denied_permit_not_no_format(self):
        self.assertEqual(mc_trace.result_name(-5), "DENIED")

    def test_minus_six_is_not_empty(self):
        self.assertEqual(mc_trace.result_name(-6), "NOT-EMPTY")

    def test_minus_seven_is_the_handle_limit(self):
        self.assertEqual(mc_trace.result_name(-7), "HANDLE-LIMIT")


if __name__ == "__main__":
    unittest.main()
