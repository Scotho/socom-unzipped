"""music_state_poll: the EE music manager's fields out of PINE words / the exe's [peek] rows, the change
log, the HUD anchor and the side-by-side compare. Synthetic data only: no PINE, no game."""
import io
import os
import struct
import tempfile
import unittest

from tools_py.parity import music_state_poll as msp
from tools_py.parity.cam_poll import resolve

MGR = 0x01b2c340                                  # a heap manager address


def mgr_words(state=3, irq=0, en=1, cue=0, d=0, vol=0, q=0, free=20, h34=0, h38=0, h3c=0xffffffff):
    w = [0] * 16
    w[2] = (en << 24) | (irq << 16) | (state << 8)   # +0x08 byte (headset prio), +9 state, +0xa irq, +0xb enable
    w[3], w[4], w[5] = cue, d, vol
    w[6], w[7], w[8] = 32, q, 0x1b2c400            # the cue-queue vector: capacity, size, data
    w[9], w[10], w[11] = 32, free, 0x1b2c480        # the free-slot vector
    w[12] = 0x1b2c500                               # the slot array
    w[13], w[14], w[15] = h34, h38, h3c
    return w


def memory(route=2, ptr=MGR, mgr=None, clock="05:59", gclock=12.5):
    """A fake guest RAM as {addr: word} for read32."""
    m = {msp.ROUTE_ADDR: route, msp.MGR_PTR_ADDR: ptr}
    for i, w in enumerate(mgr or mgr_words()):
        m[ptr + 4 * i] = w
    raw = clock.encode().ljust(8, b"\0")
    m[msp.CLOCK_ADDR], m[msp.CLOCK_ADDR + 4] = struct.unpack("<II", raw)
    m[msp.GUEST_CLOCK_ADDR] = struct.unpack("<I", struct.pack("<f", gclock))[0]
    return m


def hexw(w):
    return "%08x(%g)" % (w, struct.unpack("<f", struct.pack("<I", w))[0])


def peek_row(mem, items):
    """The exe's `[peek] @addr: w(f) ...` row for (addr, words) items (unresolved ones absent, as PS2X_PEEK drops them)."""
    parts = ["[peek]"]
    for addr, n in items:
        if addr is None:
            continue
        parts.append("@%x: " % addr + " ".join(hexw(mem.get(addr + 4 * i, 0)) for i in range(n)))
    return " ".join(parts)


def sampler(t, vsync):
    return ("[pc-sampler] live pc=0x180008 ra=0x0 sp=0x1fffff0 t=%.2f vsync=%d ee=%.2f seq=5 dpc=0x1c6730 idle=26 "
            "bp_pending=0 bp_waiters=0 bp_wait_ms=15 net_wait=0/0 running=0 threads: [1 pc=0x1c6730]" % (t, vsync, t))


class TestDecode(unittest.TestCase):
    def test_fields_out_of_the_manager_words(self):
        f = msp.decode(0x00000002, mgr_words(state=1, irq=1, en=1, cue=0x1234, d=0x1a2b3c0, vol=0x400, q=2, free=18,
                                              h34=0x1c00010, h38=0x1a2b3c0, h3c=0x1234))
        self.assertEqual((f["mode"], f["state"], f["irq"], f["en"]), (2, 1, 1, 1))
        self.assertEqual((f["cue"], f["def"], f["vol"]), (0x1234, 0x1a2b3c0, 0x400))
        self.assertEqual((f["q"], f["free"]), (2, 18))
        self.assertEqual((f["h34"], f["h38"], f["h3c"]), (0x1c00010, 0x1a2b3c0, 0x1234))

    def test_no_manager(self):
        f = msp.decode(0, None)
        self.assertEqual(f["mode"], 0)
        self.assertIsNone(f["state"])
        self.assertIn("state=-", msp.format_fields(f))

    def test_clock_string(self):
        self.assertEqual(msp.clock_string(list(struct.unpack("<II", b"05:59\0\0\0"))), "05:59")
        self.assertIsNone(msp.clock_string([0, 0]))
        self.assertIsNone(msp.clock_string(None))


class TestPeekRows(unittest.TestCase):
    def test_manager_found_by_the_pointer_word_not_by_index(self):
        mem = memory(mgr=mgr_words(state=1, q=1, h34=0x1c00010))
        # a decoy block first, then the route word, the pointer, the manager, the clocks
        row = peek_row(mem, [(0x416054, 3), (msp.ROUTE_ADDR, 1), (msp.MGR_PTR_ADDR, 1), (MGR, 16),
                             (msp.CLOCK_ADDR, 2), (msp.GUEST_CLOCK_ADDR, 1)])
        route, mgr, clk, gclk = msp.sample_from_peek(msp.parse_peek_row(row))
        self.assertEqual(route, 2)
        self.assertEqual(mgr[7], 1)
        self.assertEqual(mgr[13], 0x1c00010)
        self.assertEqual(msp.clock_string(clk), "05:59")
        self.assertAlmostEqual(msp.guest_clock(gclk), 12.5, places=3)

    def test_null_pointer_means_no_manager(self):
        mem = memory(ptr=0)
        mem[msp.MGR_PTR_ADDR] = 0
        row = peek_row(mem, [(msp.ROUTE_ADDR, 1), (msp.MGR_PTR_ADDR, 1), (None, 16)])   # PS2X_PEEK drops *0x49e158
        route, mgr, _clk, _g = msp.sample_from_peek(msp.parse_peek_row(row))
        self.assertEqual(route, 2)
        self.assertIsNone(mgr)

    def test_our_spec_resolves_like_the_exe(self):
        mem = memory()
        for item in msp.OURS_PEEK_SPEC.split(","):
            addr, words = resolve(lambda a: mem.get(a, 0), item)
            self.assertIsNotNone(addr, item)
        addr, words = resolve(lambda a: mem.get(a, 0), "*0x49e158:16")
        self.assertEqual((addr, words), (MGR, 16))


class TestTracker(unittest.TestCase):
    def test_one_line_per_change_and_round_trip(self):
        out = io.StringIO()
        tr = msp.Tracker(out, t0=1000.0)
        idle = msp.decode(2, mgr_words())
        playing = msp.decode(2, mgr_words(state=1, cue=0x77, h34=0x1c00010))
        tr.feed(1000.0, idle, clock="05:59")
        tr.feed(1000.05, idle, clock="05:59")           # unchanged: no line
        tr.feed(1000.10, dict(idle, q=1))
        tr.feed(1000.15, playing, vsync=42)
        lines = [ln for ln in out.getvalue().splitlines() if ln]
        self.assertEqual(len(lines), 3)
        self.assertEqual(tr.samples, 4)
        first = msp.parse_change_line(lines[0])
        self.assertEqual(first["clock"], "05:59")
        self.assertEqual(first["fields"]["state"], 3)
        self.assertEqual(first["fields"]["h3c"], 0xffffffff)
        self.assertIn("q 0->1", lines[1])
        self.assertNotIn("state", lines[1].split("|")[1])
        third = msp.parse_change_line(lines[2])
        self.assertEqual(third["vsync"], 42)
        self.assertAlmostEqual(third["t"], 0.15, places=3)
        self.assertEqual(third["fields"], playing)
        self.assertIn("state 3->1", third["what"])
        self.assertIn("h34 0x0->0x1c00010", third["what"])
        self.assertIn("cue 0x0->0x77", third["what"])

    def test_the_manager_appearing_is_a_change(self):
        out = io.StringIO()
        tr = msp.Tracker(out, t0=0.0)
        tr.feed(0.0, msp.decode(0, None))
        tr.feed(0.5, msp.decode(2, mgr_words()))
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("mode 0->2", lines[1])
        self.assertIn("state -->3", lines[1])
        self.assertIsNone(msp.parse_change_line("# header"))


class TestOursLog(unittest.TestCase):
    def test_peek_rows_take_the_preceding_sampler_time_and_frame(self):
        mem = memory()
        items = [(msp.ROUTE_ADDR, 1), (msp.MGR_PTR_ADDR, 1), (MGR, 16), (msp.CLOCK_ADDR, 2), (msp.GUEST_CLOCK_ADDR, 1)]
        lines = ["Using argv boot path", sampler(0.25, 13), peek_row(mem, items), "[snd] noise",
                 sampler(0.30, 16), peek_row(mem, items)]
        mem2 = memory(mgr=mgr_words(state=1, cue=5, h34=0x1c00010))
        lines += [sampler(0.35, 19), peek_row(mem2, items)]
        out = io.StringIO()
        tr = msp.Tracker(out, t0=5000.0)
        msp.feed_ours_lines(lines, tr, base_epoch=5000.0)
        evs = [msp.parse_change_line(ln) for ln in out.getvalue().splitlines()]
        self.assertEqual(len(evs), 2)
        self.assertEqual((evs[0]["vsync"], evs[0]["t"]), (13, 0.25))
        self.assertAlmostEqual(evs[0]["wall"], 5000.25, places=3)
        self.assertEqual((evs[1]["vsync"], evs[1]["t"]), (19, 0.35))
        self.assertIn("state 3->1", evs[1]["what"])
        self.assertEqual(tr.samples, 3)

    def test_rows_without_the_manager_words_are_ignored(self):
        out = io.StringIO()
        tr = msp.Tracker(out, t0=0.0)
        msp.feed_ours_lines([sampler(1.0, 60), "[peek] @416054: 00000000(0) 00000000(0) 00000000(0)"], tr, base_epoch=0.0)
        self.assertEqual(tr.samples, 0)

    def test_log_start_epoch_from_the_file_name(self):
        import time
        e = msp.log_start_epoch("logs/run_A_20260920_125528.log")
        self.assertEqual(time.strftime("%Y%m%d_%H%M%S", time.localtime(e)), "20260920_125528")


class TestPine(unittest.TestCase):
    def test_sample_from_a_fake_read32(self):
        mem = memory(mgr=mgr_words(state=1, q=2, free=18, h34=0x1c00010))
        route, mgr, clk, gclk = msp.sample_from_pine(lambda a: mem.get(a, 0))
        f = msp.decode(route, mgr)
        self.assertEqual((f["mode"], f["state"], f["q"], f["free"], f["h34"]), (2, 1, 2, 18, 0x1c00010))
        self.assertEqual(msp.clock_string(clk), "05:59")

    def test_null_pointer(self):
        mem = memory(ptr=0)
        mem[msp.MGR_PTR_ADDR] = 0
        _route, mgr, _clk, _g = msp.sample_from_pine(lambda a: mem.get(a, 0))
        self.assertIsNone(mgr)


def write_log(path, started, events):
    """events: (t, fields dict, what) -> a poll log with the header."""
    with open(path, "w") as f:
        f.write(f"# music_state_poll target=test started={started:.3f}\n")
        for t, fields, what in events:
            f.write(f"wall={started + t:.3f} t={t:.3f} {msp.format_fields(fields)} | {what}\n")


class TestCompare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def make_run(self, name, hud_epoch):
        run = os.path.join(self.dir, name)
        os.makedirs(run)
        with open(os.path.join(run, "drive.stdout"), "w") as f:
            f.write("untilref(scripts/parity/ref_main_menu_ours.png): 3 presses, dist=4.9, matched=True\n")
            f.write("s149_none                t= 280.4s stable=False waited=40.3s\n")
            f.write("untilref pacing: presses at t+0.0,3.2,15.4 (step t0+292.5s)\n")
            f.write("untilref(scripts/parity/ref_hud_ours.png): 3 presses, dist=1.5 bands=1.00, matched=True\n")
            f.write("s150_none                t= 310.7s stable=True waited=0.0s\n")
        for png in ("s149_none.png", "s150_none.png"):
            open(os.path.join(run, png), "wb").close()
        os.utime(os.path.join(run, "s150_none.png"), (hud_epoch, hud_epoch))
        return run

    def test_hud_anchor_is_the_step_after_the_match(self):
        run = self.make_run("A", 1_700_000_310.0)
        epoch, note = msp.hud_anchor_from_drive(run)
        self.assertAlmostEqual(epoch, 1_700_000_310.0, places=2)
        self.assertIn("s150_none", note)
        self.assertEqual(msp.hud_anchor("t:12.5", 100.0)[0], 112.5)
        self.assertEqual(msp.hud_anchor("1234.5", None)[0], 1234.5)

    def test_side_by_side_aligned_on_the_hud(self):
        idle = msp.decode(2, mgr_words())
        play = msp.decode(2, mgr_words(state=1, cue=0x77, h34=0x1c00010))
        started_a, started_b = 1_700_000_000.0, 1_700_001_000.0
        run_a = self.make_run("A", started_a + 310.0)      # HUD 310 s into A's poll
        run_b = self.make_run("B", started_b + 350.0)      # HUD 350 s into B's poll (the console boots slower)
        log_a, log_b = os.path.join(self.dir, "a.txt"), os.path.join(self.dir, "b.txt")
        write_log(log_a, started_a, [(0.0, idle, "mode -->2 state -->3"),
                                     (314.0, play, "state 3->1 cue 0x0->0x77 h34 0x0->0x1c00010"),
                                     (343.0, idle, "state 1->3 cue 0x77->0x0 h34 0x1c00010->0x0")])
        write_log(log_b, started_b, [(0.0, idle, "mode -->2 state -->3"),
                                     (354.5, play, "state 3->1 cue 0x0->0x77 h34 0x0->0x1c00010"),
                                     (383.2, idle, "state 1->3 cue 0x77->0x0 h34 0x1c00010->0x0"),
                                     (390.0, dict(idle, q=1), "q 0->1")])
        out = io.StringIO()
        msp.compare(log_a, log_b, run_a, run_b, out=out, width=50)
        text = out.getvalue()
        self.assertIn("+4.00 state idle->playing", text)
        self.assertIn("+4.50 state idle->playing", text)
        self.assertIn("plays (->1) after the HUD: A 1, B 1; first at A +4.0s B +4.5s", text)
        self.assertIn("play 1: A    +4.0  B    +4.5  d=+0.5s", text)
        self.assertIn("cue-queue pushes seen after the HUD: A 0, B 1", text)
        lines = text.splitlines()
        a_rows = [ln for ln in lines if ln.endswith(" |")]                      # A's cell, B's side empty
        b_rows = [ln for ln in lines if " | " in ln and ln.split(" | ")[0].strip() == ""]
        self.assertEqual(len(a_rows), 3)
        self.assertEqual(len(b_rows), 4)
        # merged by HUD-relative time: the two -310/-350 rows, then A +4.0, B +4.5, A +33.0, B +33.2, B +40.0
        keys = ["-350.00", "-310.00", "+4.00 state", "+4.50 state", "+33.00 state", "+33.20 state", "+40.00 q 0->1"]
        positions = [text.index(k) for k in keys]
        self.assertEqual(positions, sorted(positions))

    def test_window_filters_the_listing(self):
        idle = msp.decode(2, mgr_words())
        started = 1_700_000_000.0
        run = self.make_run("A", started + 100.0)
        log = os.path.join(self.dir, "a.txt")
        write_log(log, started, [(0.0, idle, "mode -->2 state -->3"), (150.0, dict(idle, q=1), "q 0->1")])
        out = io.StringIO()
        msp.compare(log, log, run, run, out=out, window=(0, 30))
        listing = out.getvalue().split("state transitions")[0]
        self.assertNotIn("q 0->1", listing)               # +50 s: outside the window
        self.assertNotIn("-100.00", listing)              # the pre-HUD row: outside too
        self.assertIn("pushes seen after the HUD: A 1, B 1", out.getvalue())   # the summary still counts it


if __name__ == "__main__":
    unittest.main()
