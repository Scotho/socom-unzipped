"""Sprint 6 Task 3 Step 1 -- freeze_trace: guest-clock stall windows out of one instance's run log.

Synthetic logs only (the exe's own `[peek]` / `[pc-sampler]` / `[call]` / `[ret]` formats); no IO, no game.
"""
import io
import struct
import unittest
from contextlib import redirect_stdout

from tools_py.parity import freeze_trace as ft

PARK_PC = 0x3B00A4          # launch 8c: the main thread parked here while the round clock stood still
RUN_PC = 0x3097F8


def hexf(x):
    return "%08x(%g)" % (struct.unpack("<I", struct.pack("<f", x))[0], x)


def clock_words(s):
    raw = s.encode("ascii").ljust(8, b"\0")[:8]
    return " ".join("%08x(0)" % w for w in struct.unpack("<II", raw))


def peek(clock=None, clock_str=None, extra="@45a0c0: 00000000(0)"):
    parts = ["[peek]"]
    if clock is not None:
        parts.append("@4365c0: " + hexf(clock))
    if clock_str is not None:
        parts.append("@408f10: " + clock_words(clock_str))
    parts.append(extra)
    return " ".join(parts)


def sampler(main_pc, running=1):
    return ("[pc-sampler] live pc=0x25e9f0 ra=0x25e9f0 sp=0x1f7fa70 running=%d threads: "
            "[1 pc=0x%x ra=0x%x sp=0x1f7fd00 st=%d wait=%d/0] "
            "[2 pc=0x1a3a48 ra=0x3b1e00 sp=0x4b4560 st=2 wait=1/0]"
            % (running, main_pc, main_pc, 0 if running else 2, 0 if running else 4))


def netidle(n, t, ms):
    return ["[call] %.1fs NetIdle #%d a0=0x45a0c0 a1=0x0 a2=0xd4f340 a3=0x0 ra=0x594f88 f12=0.0 f13=0.0 f14=590.0"
            % (t, n),
            "[ret] NetIdle #%d v0=0x%x f0=0.6" % (n, ms)]


def synth(clocks, stall_rows=(), idle_ms_at=None, period=0.25, stamps=False, strings=False):
    """One log: per row a sampler line then a peek row; `clocks` are the row clock values; rows in `stall_rows`
    sample the parked PC; `idle_ms_at` {row: ms} puts a NetIdle call/ret just before that row; `stamps` adds a
    stamped [call] line every row at `period` seconds so host time follows `period` rather than the 0.25 s nominal."""
    lines, n = [], 0
    for i, c in enumerate(clocks):
        t = i * period
        if stamps:
            lines.append("[call] %.1fs MoveScale #%d a0=0x869360 ra=0x2c4000 f12=1.0" % (t, i))
            lines.append("[ret] MoveScale #%d v0=0x0 f0=1.0" % i)
        if idle_ms_at and i in idle_ms_at:          # printed between rows i-1 and i: stamped half a period back
            lines += netidle(n, t - period / 2, idle_ms_at[i])
            n += 1
        lines.append(sampler(PARK_PC if i in stall_rows else RUN_PC, running=0 if i in stall_rows else 1))
        if strings:
            lines.append(peek(clock_str="%02d:%02d" % divmod(int(c), 60)))
        else:
            lines.append(peek(clock=c))
    return lines


def advancing(n, start=10.0, step=0.15):
    return [round(start + k * step, 4) for k in range(n)]


class WindowsTest(unittest.TestCase):
    def test_steady_clock_yields_no_window(self):
        self.assertEqual(ft.windows(synth(advancing(200))), [])

    def test_one_five_second_stall_is_one_window_with_row_bounds(self):
        clocks = advancing(40) + [54.402] * 21 + advancing(40, start=55.5)   # rows 40..60 still: 5.0 s at 4 Hz
        stall = set(range(40, 61))
        lines = synth(clocks, stall_rows=stall, idle_ms_at={20: 300, 45: 1200, 50: 4800, 80: 200})
        ws = ft.windows(lines, min_stall_s=2.0)
        self.assertEqual(len(ws), 1)
        w = ws[0]
        self.assertEqual((w["start_row"], w["end_row"], w["rows"]), (40, 60, 21))
        self.assertAlmostEqual(w["stall_s"], 5.0, delta=0.05)     # [call] stamps carry 0.1 s resolution
        self.assertAlmostEqual(w["guest_clock_before"], 54.402, places=3)
        self.assertAlmostEqual(w["guest_clock_after"], 55.5, places=3)
        self.assertEqual(w["main_pc"], PARK_PC)
        self.assertEqual(w["netidle_peak_ms"], 4800)

    def test_stall_shorter_than_min_stall_is_ignored(self):
        clocks = advancing(30) + [20.0] * 5 + advancing(30, start=21.0)       # rows 30..34 still: 1.0 s
        lines = synth(clocks, stall_rows=set(range(30, 35)))
        self.assertEqual(ft.windows(lines, min_stall_s=2.0), [])
        ws = ft.windows(lines, min_stall_s=1.0)
        self.assertEqual([(w["start_row"], w["end_row"]) for w in ws], [(30, 34)])

    def test_two_stalls_are_two_windows_in_order(self):
        clocks = advancing(10) + [5.0] * 13 + advancing(10, start=6.0) + [8.0] * 9 + advancing(10, start=9.0)
        ws = ft.windows(synth(clocks), min_stall_s=2.0)
        self.assertEqual([(w["start_row"], w["end_row"]) for w in ws], [(10, 22), (33, 41)])

    def test_stall_at_end_of_log_is_reported_and_has_no_clock_after(self):
        clocks = advancing(10) + [7.0] * 12
        ws = ft.windows(synth(clocks), min_stall_s=2.0)
        self.assertEqual(len(ws), 1)
        self.assertEqual((ws[0]["start_row"], ws[0]["end_row"]), (10, 21))
        self.assertIsNone(ws[0]["guest_clock_after"])

    def test_clock_string_fallback_when_the_float_is_not_peeked(self):
        clocks = list(range(100, 130)) + [130] * 12 + list(range(131, 160))
        ws = ft.windows(synth(clocks, strings=True), min_stall_s=2.0)
        self.assertEqual([(w["start_row"], w["end_row"]) for w in ws], [(30, 41)])
        self.assertEqual(ws[0]["guest_clock_before"], "02:10")
        self.assertEqual(ws[0]["guest_clock_after"], "02:11")
        self.assertEqual(ws[0]["clock_source"], "string@0x408f10")

    def test_no_clock_items_at_all_yields_no_windows(self):
        lines = ["[peek] @45a0c0: 00000000(0)"] * 40
        self.assertEqual(ft.windows(lines), [])

    def test_host_time_follows_call_stamps_not_the_nominal_period(self):
        # 8 still rows = 1.75 s at the nominal 0.25 s/row, but the [call] stamps say 0.5 s/row (3.5 s under load)
        clocks = advancing(20) + [9.0] * 8 + advancing(20, start=10.0)
        self.assertEqual(ft.windows(synth(clocks), min_stall_s=2.0), [])
        ws = ft.windows(synth(clocks, period=0.5, stamps=True), min_stall_s=2.0)
        self.assertEqual([(w["start_row"], w["end_row"]) for w in ws], [(20, 27)])
        self.assertAlmostEqual(ws[0]["stall_s"], 3.5, places=6)

    def test_no_sampler_lines_means_no_main_pc(self):
        clocks = advancing(10) + [3.0] * 12 + advancing(10, start=4.0)
        lines = [l for l in synth(clocks) if not l.startswith("[pc-sampler]")]
        ws = ft.windows(lines)
        self.assertEqual(len(ws), 1)
        self.assertIsNone(ws[0]["main_pc"])
        self.assertIsNone(ws[0]["netidle_peak_ms"])

    def test_torn_line_with_a_call_glued_to_a_sampler_line_still_parses(self):
        clocks = advancing(10) + [3.0] * 12 + advancing(10, start=4.0)
        lines = synth(clocks, stall_rows=set(range(10, 22)))
        k = next(i for i, l in enumerate(lines) if l.startswith("[pc-sampler]") and "0x3b00a4" in l)
        lines[k] = lines[k] + "[call] 3.0s NetIdle #7 a0=0x45a0c0 ra=0x594f88 f12=0.0"
        lines.insert(k + 1, "[ret] NetIdle #7 v0=0x2019 f0=0.6")
        ws = ft.windows(lines)
        self.assertEqual(len(ws), 1)
        self.assertEqual(ws[0]["rows"], 12)
        self.assertEqual(ws[0]["main_pc"], PARK_PC)
        self.assertEqual(ws[0]["netidle_peak_ms"], 0x2019)


class SamplerFieldsTest(unittest.TestCase):
    """Sprint 7 Task 2e: the [pc-sampler] line's freeze fields (research/29 section 4 items 1-8)."""

    SAMPLE = ("[pc-sampler] live pc=0x350d90 ra=0x0 sp=0x0 t=612.50 vsync=41233 ee=612.10 seq=8891 "
              "dpc=0x350d90 idle=140 bp_pending=0 bp_waiters=0 bp_wait_ms=12 net_wait=1/3300 running=3 threads:")

    def test_the_new_sampler_fields_are_parsed(self):
        row = ft.parse([self.SAMPLE])[0]
        self.assertAlmostEqual(row["t"], 612.50)
        self.assertEqual(row["vsync"], 41233)
        self.assertEqual(row["seq"], 8891)
        self.assertEqual(row["dpc"], 0x350d90)
        self.assertEqual(row["bp_waiters"], 0)
        self.assertEqual(row["net_wait"], 1)

    def test_shape_two_classifies_as_net_wait(self):
        rows = ft.parse([self.SAMPLE, self.SAMPLE.replace("t=612.50", "t=615.80")])
        self.assertEqual(ft.classify(rows), "net-wait")

    def test_a_host_load_window_classifies_as_host_load(self):
        a = self.SAMPLE.replace("net_wait=1/3300", "net_wait=0/0").replace("bp_waiters=0", "bp_waiters=1")
        b = a.replace("t=612.50", "t=615.80").replace("bp_wait_ms=12", "bp_wait_ms=3200").replace("seq=8891", "seq=9100")
        self.assertEqual(ft.classify(ft.parse([a, b])), "host-load")

    def test_a_runtime_oversleep_window_classifies_as_runtime_oversleep(self):
        a = self.SAMPLE.replace("net_wait=1/3300", "net_wait=0/0")
        b = a.replace("t=612.50", "t=615.80").replace("idle=140", "idle=9400").replace("seq=8891", "seq=9100")
        self.assertEqual(ft.classify(ft.parse([a, b])), "runtime-oversleep")

    def test_the_thread_table_parses_with_task_2as_prio_field(self):
        line = (self.SAMPLE.replace("threads:", "threads:")
                + " [1 pc=0x1a3b68 ra=0x33aa1c sp=0x1f7fd00 st=0 prio=48 wait=0/0]"
                  " [2 pc=0x1a3a48 ra=0x3b1e00 sp=0x4b4560 st=2 prio=50 wait=1/0]")
        row = ft.parse([line])[0]
        self.assertEqual(row["threads"][1], (0x1a3b68, 0, 0))
        self.assertEqual(row["threads"][2], (0x1a3a48, 2, 1))

    def test_an_old_sampler_line_without_the_fields_still_parses(self):
        rows = ft.parse([sampler(PARK_PC)])
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["t"])
        self.assertIsNone(rows[0]["vsync"])
        self.assertEqual(rows[0]["threads"][1][0], PARK_PC)


class PeerTest(unittest.TestCase):
    def test_peer_netidle_peak_reads_the_other_log_over_the_window_plus_slack(self):
        peer = []
        for k, (t, ms) in enumerate([(100.0, 200), (104.0, 3100), (106.0, 5200), (109.5, 8217), (120.0, 150)]):
            peer += netidle(k, t, ms)
        rets = ft.peer_netidle(peer)
        self.assertEqual(ft.peer_netidle_peak(rets, 103.0, 107.0, slack_s=0.0), 5200)
        self.assertEqual(ft.peer_netidle_peak(rets, 103.0, 107.0, slack_s=5.0), 8217)
        self.assertIsNone(ft.peer_netidle_peak(rets, 50.0, 60.0))
        self.assertIsNone(ft.peer_netidle_peak([], 103.0, 107.0))


class CliTest(unittest.TestCase):
    def test_cli_prints_one_line_per_window_and_a_summary(self):
        import os
        import tempfile
        clocks = advancing(10) + [5.0] * 13 + advancing(10, start=6.0) + [8.0] * 9 + advancing(10, start=9.0)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "run_A_test.log")
            with open(path, "w") as f:
                f.write("\n".join(synth(clocks, stall_rows=set(range(10, 23)) | set(range(33, 42)))) + "\n")
            out = io.StringIO()
            with redirect_stdout(out):
                rc = ft.main([path])
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertEqual(sum(1 for l in text.splitlines() if l.startswith("window ")), 2)
        self.assertIn("windows=2", text)
        self.assertIn("longest=3.00s", text)
        self.assertIn("stalled_rows=22", text)
        self.assertIn("0x3b00a4", text)


if __name__ == "__main__":
    unittest.main()
