"""music_state_poll: the EE cue manager's fields out of PINE words / the exe's [peek] rows, the sound entry
and def behind the playing cue (name, sector through the VAGSTORE TOC, group, flags, IOP handle), the
change log, the HUD anchor and the side-by-side compare. Synthetic data only: no PINE, no game."""
import io
import os
import struct
import tempfile
import unittest

from tools_py.parity import music_state_poll as msp
from tools_py.parity.cam_poll import resolve

MGR = 0x01b2c340                                  # a heap manager address
ENTRY = 0x0084d610                                # a sound entry (the console's real one in run s10_r4o)
DEF = 0x00deb7f0                                  # its def
NAME = 0x00e01230                                 # the def's name string
QDATA, SLOTS = 0x1b2c400, 0x1b2c500


def mgr_words(state=3, irq=0, en=1, cue=0, d=0, vol=0, q=0, free=20, h34=0, h38=0, h3c=0xffffffff):
    w = [0] * 16
    w[2] = (en << 24) | (irq << 16) | (state << 8)   # +0x08 byte (headset prio), +9 state, +0xa irq, +0xb enable
    w[3], w[4], w[5] = cue, d, vol
    w[6], w[7], w[8] = 32, q, QDATA                 # the cue-queue vector: capacity, size, data
    w[9], w[10], w[11] = 32, free, 0x1b2c480        # the free-slot vector
    w[12] = SLOTS                                   # the slot array
    w[13], w[14], w[15] = h34, h38, h3c
    return w


def entry_words(ih=0x0400029e, d=DEF, flags=0, fade=0.0):
    w = [0] * 10
    w[0], w[1] = ih & 0xffffffff, d
    w[2] = struct.unpack("<I", struct.pack("<f", 1.0))[0]
    w[7] = flags
    w[8] = struct.unpack("<I", struct.pack("<f", fade))[0]
    return w


def def_words(flags_a=0x09, flags_b=0x29, bank=3, sid=0x12, name_ptr=NAME, name2=0):
    raw = bytearray(0x40)
    struct.pack_into("<f", raw, 4, 1.0)
    struct.pack_into("<HH", raw, 0xc, 100, 400)
    raw[0x10] = bank
    struct.pack_into("<H", raw, 0x12, sid)
    raw[0x1c], raw[0x1d] = flags_a, flags_b
    struct.pack_into("<II", raw, 0x20, name_ptr, name2)
    return list(struct.unpack("<16I", bytes(raw)))


def name_words(s="M51_048"):
    return list(struct.unpack("<8I", s.encode().ljust(32, b"\0")))


def memory(route=2, ptr=MGR, mgr=None, entry=None, sdef=None, name="M51_048", clock="05:59", gclock=12.5,
           store=(0, 0xee89a), qidx=None, slots=None):
    """A fake guest RAM as {addr: word} for read32."""
    m = {msp.ROUTE_ADDR: route, msp.MGR_PTR_ADDR: ptr}
    for base, words in ((ptr, mgr or mgr_words()), (ENTRY, entry), (DEF, sdef), (NAME, name_words(name) if name else None),
                        (QDATA, qidx), (SLOTS, slots)):
        for i, w in enumerate(words or []):
            m[base + 4 * i] = w
    raw = clock.encode().ljust(8, b"\0")
    m[msp.CLOCK_ADDR], m[msp.CLOCK_ADDR + 4] = struct.unpack("<II", raw)
    m[msp.GUEST_CLOCK_ADDR] = struct.unpack("<I", struct.pack("<f", gclock))[0]
    m[msp.STORE_BASE_ADDR], m[msp.STORE_BASE_ADDR + 4] = store
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


FULL_ITEMS = [(msp.ROUTE_ADDR, 1), (msp.MGR_PTR_ADDR, 1), (MGR, 16), (ENTRY, 10), (DEF, 16), (NAME, 8),
              (QDATA, 20), (SLOTS, 60), (msp.STORE_BASE_ADDR, 2), (msp.CLOCK_ADDR, 2), (msp.GUEST_CLOCK_ADDR, 1)]

TOC = {"M51_048.VAG": (0xa387580, 0x1c280), "MUUI0003.VPK": (0x20dfb800 - 0x4c800 - 0, 0x693800), "__data__": (0x4c800, 0)}


class TestDecode(unittest.TestCase):
    def test_fields_out_of_the_manager_words(self):
        f = msp.decode(0x00000002, mgr_words(state=1, irq=1, en=1, cue=0x1234, d=0x1a2b3c0, vol=0x400, q=2, free=18,
                                              h34=0x1c00010, h38=0x1a2b3c0, h3c=0x1234), entry_words(ih=0x0400029e, flags=0x41))
        self.assertEqual((f["mode"], f["state"], f["irq"], f["en"]), (2, 1, 1, 1))
        self.assertEqual((f["cue"], f["def"], f["vol"]), (0x1234, 0x1a2b3c0, 0x400))
        self.assertEqual((f["q"], f["free"]), (2, 18))
        self.assertEqual((f["h34"], f["h38"], f["h3c"]), (0x1c00010, 0x1a2b3c0, 0x1234))
        self.assertEqual((f["ih"], f["ef"]), (0x0400029e, 0x41))

    def test_no_manager_and_no_entry(self):
        f = msp.decode(0, None)
        self.assertEqual(f["mode"], 0)
        self.assertIsNone(f["state"])
        self.assertIn("state=- ", msp.format_fields(f))
        f = msp.decode(2, mgr_words())
        self.assertIsNone(f["ih"])
        self.assertIn("ih=- ef=-", msp.format_fields(f))

    def test_pending_handle_prints_in_full_hex(self):
        f = msp.decode(2, mgr_words(state=1, h34=ENTRY), entry_words(ih=-1))
        self.assertIn("ih=0xffffffff", msp.format_fields(f))    # -1 is reserved for the SIGNED music level
        self.assertEqual(msp.parse_change_line(msp.format_change_line(1.0, 0.0, f, [("ih", None, f["ih"])]))["fields"]["ih"], 0xffffffff)

    def test_clock_string(self):
        self.assertEqual(msp.clock_string(list(struct.unpack("<II", b"05:59\0\0\0"))), "05:59")
        self.assertIsNone(msp.clock_string([0, 0]))
        self.assertIsNone(msp.clock_string(None))


class TestDef(unittest.TestCase):
    def test_voice_def(self):
        d = msp.decode_def(def_words(flags_a=0x09, flags_b=0x29), name_words("M51_048"))
        self.assertEqual(d["name"], "M51_048")
        self.assertEqual((d["type"], d["fmt"], d["ext"], d["stream"]), (1, 2, "VPK", 1))
        # (0x29 & 0x1f) >> 2 == 2 -> the "%s.VPK" format, hence group 1 by :241875-241887
        self.assertEqual(d["group"], 1)
        self.assertEqual((d["bank"], d["id"]), (3, 0x12))
        self.assertEqual(d["key"], "M51_048.VPK")

    def test_group_rules(self):
        self.assertEqual(msp.decode_def(def_words(flags_a=0x01, flags_b=0x0c), name_words())["group"], 2)   # fmt 3 -> voice
        self.assertEqual(msp.decode_def(def_words(flags_a=0x11, flags_b=0x00), name_words())["group"], 6)   # flags-A bit 4
        self.assertEqual(msp.decode_def(def_words(flags_a=0x01, flags_b=0x00), name_words())["group"], 0)
        self.assertEqual(msp.decode_def(def_words(flags_b=0x69), name_words())["type"], 3)

    def test_describe_with_the_toc_and_the_peeked_base(self):
        d = msp.decode_def(def_words(flags_a=0x01, flags_b=0x0c), name_words("M51_048"))
        s = msp.describe_def(d, ih=0x0400029e, store_words=[0, 0xee89a], toc=TOC)
        self.assertEqual(s, "def M51_048 fmt VAG type 0 flags 0x01/0x0c group 2 bank 3 id 0x12 "
                            "sector 0x102fa8+0x580 size 0x1c280 handle 0x400029e")
        # no peeked base: the disc constant; an unknown name says so
        self.assertIn("sector 0x102fa8+0x580", msp.describe_def(d, toc=TOC))
        d2 = msp.decode_def(def_words(), name_words("NOPE"))
        self.assertIn("sector ? (NOPE.VPK not in the TOC)", msp.describe_def(d2, toc=TOC))
        self.assertIsNone(msp.decode_def(None))
        self.assertIsNone(msp.describe_def(None))

    def test_toc_out_of_a_synthetic_zar(self):
        names = [b"C0_0341A.vag", b"M51_048.vag", b"MUUI0003.vpk"]
        blob = b"\0".join(names) + b"\0"
        name_va = 0x0d1e5008
        head = struct.pack("<5I", 0, len(names) + 1, len(blob), name_va, 0x800).ljust(0x64, b"\0")
        recs = struct.pack("<4I", 0, 0, 0, len(names))          # the u32 before the records = count - 1
        off = 0
        for i, n in enumerate(names):
            recs += struct.pack("<4I", name_va + off, 0x800 * i * 3, 0x800 * 3, 0)
            off += len(n) + 1
        recs += b"\xaf" * 16                                     # the filler record
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "VAGSTORE.ZAR")
            open(p, "wb").write(head + blob + recs)
            toc = msp.vagstore_toc(p)
        self.assertEqual(toc["M51_048.VAG"], (0x1800, 0x1800))
        self.assertEqual(toc["MUUI0003.VPK"][0], 0x3000)
        self.assertNotIn("__BAD__", toc)
        self.assertEqual(toc["__data__"][0], (0x64 + len(blob) + 0x10 + 16 * 4 + 0x7ff) & ~0x7ff)
        self.assertEqual(msp.store_sector("m51_048.vag", 0x1000, toc), (0x1003, 0, 0x1800))
        self.assertIsNone(msp.store_sector("X.VAG", 0x1000, toc))
        self.assertIsNone(msp.vagstore_toc(os.path.join(d, "missing.ZAR")))

    @unittest.skipUnless(os.path.exists(msp.VAGSTORE_ZAR), "game/disc/RUN/SOUNDS/VAGSTORE.ZAR not present")
    def test_the_real_disc(self):
        toc = msp.vagstore_toc()
        self.assertEqual(msp.store_sector("M51_048.VAG", None, toc), (0x102fa8, 0x580, 0x1c280))
        # three of ours' 0x2c plays (s10_r4n game.log): sector+offset -> the name
        self.assertEqual(msp.store_sector("CS_0467.VAG", None, toc)[:2], (0xf2455, 0x300))
        self.assertEqual(msp.store_sector("MUUI0003.VPK", None, toc)[:2], (0x1303f8, 0))
        self.assertEqual(toc["__data__"][0] >> 11, msp.VAGSTORE_DATA_LBN - 0xee801)


class TestPeekRows(unittest.TestCase):
    def test_every_block_found_by_its_pointer_not_by_index(self):
        mem = memory(mgr=mgr_words(state=1, q=1, h34=ENTRY), entry=entry_words(), sdef=def_words(),
                     qidx=[4] + [0] * 19, slots=[0] * 12 + [0x4, DEF, 0x400] + [0] * 45)
        # a decoy block first, and the blocks in a shuffled order
        row = peek_row(mem, [(0x416054, 3)] + FULL_ITEMS[::-1])
        s = msp.sample_from_peek(msp.parse_peek_row(row))
        self.assertEqual(s.route, 2)
        self.assertEqual(s.mgr[7], 1)
        self.assertEqual(s.entry[0], 0x0400029e)
        self.assertEqual(s.sdef[8], NAME)
        self.assertEqual(msp.cstring(s.name), "M51_048")
        self.assertEqual(msp.queued_ids(s.qidx, s.slots, 1), [4])
        self.assertEqual(s.store[1], 0xee89a)
        self.assertEqual(msp.clock_string(s.clk), "05:59")
        self.assertAlmostEqual(msp.guest_clock(s.gclk), 12.5, places=3)

    def test_null_pointers_drop_the_chained_blocks(self):
        mem = memory(mgr=mgr_words(h34=0))
        row = peek_row(mem, [(msp.ROUTE_ADDR, 1), (msp.MGR_PTR_ADDR, 1), (MGR, 16), (None, 10), (None, 16), (None, 8)])
        s = msp.sample_from_peek(msp.parse_peek_row(row))
        self.assertIsNotNone(s.mgr)
        self.assertIsNone(s.entry)
        self.assertIsNone(s.sdef)
        mem[msp.MGR_PTR_ADDR] = 0
        row = peek_row(mem, [(msp.ROUTE_ADDR, 1), (msp.MGR_PTR_ADDR, 1)])
        s = msp.sample_from_peek(msp.parse_peek_row(row))
        self.assertIsNone(s.mgr)

    def test_our_spec_resolves_like_the_exe(self):
        mem = memory(mgr=mgr_words(h34=ENTRY), entry=entry_words(), sdef=def_words())
        read = lambda a: mem.get(a, 0)  # noqa: E731
        got = {}
        for item in msp.OURS_PEEK_SPEC.split(","):
            addr, words = resolve(read, item)
            self.assertIsNotNone(addr, item)
            got[addr] = words
        self.assertEqual(got[ENTRY], 10)
        self.assertEqual(got[DEF], 16)
        self.assertEqual(got[NAME], 8)
        self.assertEqual(got[SLOTS], 60)
        self.assertTrue(all(w <= 64 for w in got.values()))      # PS2X_PEEK's silent cap


class TestTracker(unittest.TestCase):
    def test_one_line_per_change_and_round_trip(self):
        out = io.StringIO()
        tr = msp.Tracker(out, t0=1000.0)
        idle = msp.decode(2, mgr_words())
        playing = msp.decode(2, mgr_words(state=1, cue=0x77, h34=0x1c00010), entry_words())
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
        self.assertIn("ih -->0x400029e", third["what"])
        self.assertIsNone(third["note"])

    def test_the_def_is_decoded_on_a_state_change(self):
        out = io.StringIO()
        tr = msp.Tracker(out, t0=0.0, toc=TOC)
        idle = msp.Sample(2, mgr_words(), store=[0, 0xee89a])
        tr.feed(0.0, msp.decode(idle.route, idle.mgr), sample=idle)
        play = msp.Sample(2, mgr_words(state=1, cue=4, h34=ENTRY), entry_words(), def_words(flags_a=0x01, flags_b=0x0c),
                          name_words("M51_048"), store=[0, 0xee89a])
        tr.feed(0.5, msp.decode(play.route, play.mgr, play.entry), sample=play)
        line = out.getvalue().splitlines()[1]
        ev = msp.parse_change_line(line)
        self.assertIn("state 3->1", ev["what"])
        self.assertEqual(ev["note"], "def M51_048 fmt VAG type 0 flags 0x01/0x0c group 2 bank 3 id 0x12 "
                                     "sector 0x102fa8+0x580 size 0x1c280 handle 0x400029e")
        # the handle answering 0 (the stream ended) is its own change, decorated again
        ended = msp.Sample(2, play.mgr, entry_words(ih=0), play.sdef, play.name, store=play.store)
        tr.feed(1.0, msp.decode(ended.route, ended.mgr, ended.entry), sample=ended)
        ev = msp.parse_change_line(out.getvalue().splitlines()[2])
        self.assertEqual(ev["what"], "ih 0x400029e->0x0")
        self.assertTrue(ev["note"].endswith("handle 0x0"))
        # a queue push lists the queued cue ids
        queued = msp.Sample(2, mgr_words(state=1, cue=4, h34=ENTRY, q=2), entry_words(ih=0), play.sdef, play.name,
                            qidx=[7, 9], slots=[0] * 21 + [0x9, 0, 0] + [0, 0, 0] + [0x12, 0, 0] + [0] * 30, store=play.store)
        tr.feed(1.5, msp.decode(queued.route, queued.mgr, queued.entry), sample=queued)
        ev = msp.parse_change_line(out.getvalue().splitlines()[3])
        self.assertEqual(ev["what"], "q 0->2")
        self.assertTrue(ev["note"].endswith("; queued 0x9,0x12"), ev["note"])

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
        mem = memory(mgr=mgr_words())
        items = [(msp.ROUTE_ADDR, 1), (msp.MGR_PTR_ADDR, 1), (MGR, 16), (msp.CLOCK_ADDR, 2), (msp.GUEST_CLOCK_ADDR, 1)]
        lines = ["Using argv boot path", sampler(0.25, 13), peek_row(mem, items), "[snd] noise",
                 sampler(0.30, 16), peek_row(mem, items)]
        mem2 = memory(mgr=mgr_words(state=1, cue=5, h34=ENTRY), entry=entry_words(), sdef=def_words(flags_a=1, flags_b=0x0c))
        lines += [sampler(0.35, 19), peek_row(mem2, FULL_ITEMS)]
        out = io.StringIO()
        tr = msp.Tracker(out, t0=5000.0, toc=TOC)
        msp.feed_ours_lines(lines, tr, base_epoch=5000.0)
        evs = [msp.parse_change_line(ln) for ln in out.getvalue().splitlines()]
        self.assertEqual(len(evs), 2)
        self.assertEqual((evs[0]["vsync"], evs[0]["t"]), (13, 0.25))
        self.assertAlmostEqual(evs[0]["wall"], 5000.25, places=3)
        self.assertEqual((evs[1]["vsync"], evs[1]["t"]), (19, 0.35))
        self.assertIn("state 3->1", evs[1]["what"])
        self.assertIn("def M51_048 fmt VAG type 0 flags 0x01/0x0c group 2", evs[1]["note"])
        self.assertIn("sector 0x102fa8+0x580", evs[1]["note"])
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
    def test_sample_reads_every_block_and_caches_the_def(self):
        mem = memory(mgr=mgr_words(state=1, q=2, free=18, h34=ENTRY), entry=entry_words(), sdef=def_words(),
                     qidx=[4, 6] + [0] * 18, slots=[0] * 60)
        reads = []

        def read32(a):
            reads.append(a)
            return mem.get(a, 0)
        ps = msp.PineSampler(read32)
        s = ps.sample()
        f = msp.decode(s.route, s.mgr, s.entry)
        self.assertEqual((f["mode"], f["state"], f["q"], f["free"], f["h34"], f["ih"]), (2, 1, 2, 18, ENTRY, 0x0400029e))
        self.assertEqual(msp.cstring(s.name), "M51_048")
        self.assertEqual(s.qidx, [4, 6])
        self.assertEqual(len(s.slots), 60)
        self.assertEqual(s.store[1], 0xee89a)
        n1 = len(reads)
        ps.sample()
        n2 = len(reads) - n1
        # the second sample re-reads neither the def, the name nor the store: 1+1+16+10 + 2+60 + 2+1 words
        self.assertEqual(n2, n1 - 16 - 8 - 2)

    def test_null_pointers(self):
        mem = memory(ptr=0)
        mem[msp.MGR_PTR_ADDR] = 0
        _route, mgr, _clk, _g = msp.sample_from_pine(lambda a: mem.get(a, 0))
        self.assertIsNone(mgr)
        mem = memory(mgr=mgr_words(h34=0))
        s = msp.PineSampler(lambda a: mem.get(a, 0)).sample()
        self.assertIsNotNone(s.mgr)
        self.assertIsNone(s.entry)
        self.assertIsNone(s.qidx)


def write_log(path, started, events):
    """events: (t, fields dict, what[, note]) -> a poll log with the header."""
    with open(path, "w") as f:
        f.write(f"# music_state_poll target=test started={started:.3f}\n")
        for ev in events:
            t, fields, what = ev[:3]
            note = f" || {ev[3]}" if len(ev) > 3 else ""
            f.write(f"wall={started + t:.3f} t={t:.3f} {msp.format_fields(fields)} | {what}{note}\n")


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

    def test_t_anchor_uses_the_events_own_clock(self):
        # ours offline: wall = log_start + t, while the header's started= is the TOOL's clock (430 s later
        # in run s10_r4n) -- t:<s> must land on the events' clock, not the header's
        idle = msp.decode(2, mgr_words())
        log = os.path.join(self.dir, "a.txt")
        with open(log, "w") as f:
            f.write("# music_state_poll target=ours started=1789936289.156 log_start=1789935858.779\n")
            f.write(f"wall=1789935858.829 t=0.050 {msp.format_fields(idle)} | mode -->2\n")
            f.write(f"wall=1789936169.500 t=310.721 {msp.format_fields(dict(idle, q=1))} | q 0->1\n")
        evs, t0, what = msp.read_log(log)
        self.assertEqual(what, "cue")
        self.assertAlmostEqual(t0, 1789935858.779, places=3)
        epoch, _ = msp.hud_anchor("t:310.7", t0)
        self.assertAlmostEqual(evs[1]["wall"] - epoch, 0.021, places=3)

    def test_side_by_side_aligned_on_the_hud(self):
        idle = msp.decode(2, mgr_words())
        play = msp.decode(2, mgr_words(state=1, cue=0x77, h34=0x1c00010), entry_words())
        started_a, started_b = 1_700_000_000.0, 1_700_001_000.0
        run_a = self.make_run("A", started_a + 310.0)      # HUD 310 s into A's poll
        run_b = self.make_run("B", started_b + 350.0)      # HUD 350 s into B's poll (the console boots slower)
        log_a, log_b = os.path.join(self.dir, "a.txt"), os.path.join(self.dir, "b.txt")
        note = "def M51_048 fmt VAG type 0 flags 0x01/0x0c group 2 bank 3 id 0x12 sector 0x102fa8+0x580 size 0x1c280 handle 0x400029e"
        write_log(log_a, started_a, [(0.0, idle, "mode -->2 state -->3"),
                                     (314.0, play, "state 3->1 cue 0x0->0x77 h34 0x0->0x1c00010", note),
                                     (343.0, idle, "state 1->3 cue 0x77->0x0 h34 0x1c00010->0x0")])
        write_log(log_b, started_b, [(0.0, idle, "mode -->2 state -->3"),
                                     (354.5, play, "state 3->1 cue 0x0->0x77 h34 0x0->0x1c00010", note),
                                     (383.2, idle, "state 1->3 cue 0x77->0x0 h34 0x1c00010->0x0"),
                                     (390.0, dict(idle, q=1), "q 0->1")])
        out = io.StringIO()
        msp.compare(log_a, log_b, run_a, "t:350", out=out, width=64)
        text = out.getvalue()
        self.assertIn("+4.00 state idle->playing", text)
        self.assertIn("+4.50 state idle->playing", text)
        self.assertIn("(M51_048 sector 0x102fa8+0x580)", text)
        self.assertIn("plays (->1) after the HUD: A 1, B 1; first at A +4.0s B +4.5s", text)
        self.assertIn("play 1: A    +4.0  B    +4.5  d=+0.5s", text)
        self.assertIn("cue-queue pushes seen after the HUD: A 0, B 1", text)
        self.assertIn("A played: M51_048@+4.0", text)
        self.assertIn("B played: M51_048@+4.5", text)
        lines = text.splitlines()
        a_rows = [ln for ln in lines if ln.endswith(" |")]                      # A's cell, B's side empty
        b_rows = [ln for ln in lines if " | " in ln and ln.split(" | ")[0].strip() == ""]
        self.assertEqual(len(a_rows), 3)
        self.assertEqual(len(b_rows), 4)
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

    def test_negative_window_argument(self):
        self.assertEqual(msp.join_negative_window(["a", "b", "--window", "-20:200", "--hud-a", "t:1"]),
                         ["a", "b", "--window=-20:200", "--hud-a", "t:1"])
        self.assertEqual(msp.join_negative_window(["--window", "0:10"]), ["--window", "0:10"])
        self.assertEqual(msp.join_negative_window(["--window=-5:5"]), ["--window=-5:5"])


# ---- --what music --------------------------------------------------------------------------------------

PL = 0x00e2a100                                   # a playlist object
PL_DATA = 0x00e2a200                              # its entries
DEF_A, DEF_B, NAME_A, NAME_B = 0x00df0100, 0x00df0200, 0x00df0300, 0x00df0400
SENT = 0x0084e000                                 # the current entry's sound entry
LIST0, LIST1, W0, W1 = 0x00e30000, 0x00e30100, 0x00e30200, 0x00e30300


def f32(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def music_globals(ent=0, pl=0, lvl=-1, loaded=1, alert=0, chg=0, reqdef=0, reqlvl=-1):
    w = [0] * 14
    w[0], w[2], w[4], w[6] = ent, pl, lvl & 0xff, loaded
    w[8], w[10], w[12], w[13] = alert, chg, reqdef, reqlvl & 0xff
    return w


def playlist(n=3, cur=-1, done=0, stop=0, data=PL_DATA):
    return [8, n, data, cur & 0xffffffff, 0x1234, done | (stop << 8)]


def pl_entries(cur_sentry=0):
    """M51_M01 | rest 12.0 s | M51_M02"""
    return [DEF_A, 0, f32(0.0), f32(0.0),
            0, 0, f32(12.0), f32(3.25),
            DEF_B, cur_sentry, f32(0.0), f32(0.0)]


def tables():
    t = [0] * 28
    t[0:3] = [4, 2, LIST0]                          # STEALTH: 2 playlists
    t[3:6] = [4, 1, LIST1]                          # FIGHT: 1
    t[16:19] = [4, 2, W0]
    t[19:22] = [4, 1, W1]
    return t


def music_memory(g=None, pl=None, ents=None, cur_sentry_words=None, off=0):
    m = {}
    for base, words in ((msp.MUSIC_ADDR, g or music_globals()), (msp.TABLES_ADDR, tables()),
                        (LIST0, [PL, 0xe2a900]), (LIST1, [0xe2aa00]),
                        (W0, [f32(0.5), f32(0.5)]), (W1, [f32(1.0)]),
                        (PL, pl), (PL_DATA, ents),
                        (DEF_A, def_words(flags_a=0x01, flags_b=0x08, name_ptr=NAME_A)),
                        (DEF_B, def_words(flags_a=0x01, flags_b=0x08, name_ptr=NAME_B)),
                        (NAME_A, name_words("M51_M01")), (NAME_B, name_words("M51_M02")),
                        (SENT, cur_sentry_words), (ENTRY, entry_words(d=DEF, ih=0x04000077)),
                        (DEF, def_words(flags_a=0x01, flags_b=0x08)), (NAME, name_words("M51_048"))):
        for i, w in enumerate(words or []):
            m[base + 4 * i] = w
    m[msp.MUSIC_OFF_ADDR] = off
    m[msp.STORE_BASE_ADDR], m[msp.STORE_BASE_ADDR + 4] = 0, 0xee89a
    raw = b"05:59\0\0\0"
    m[msp.CLOCK_ADDR], m[msp.CLOCK_ADDR + 4] = struct.unpack("<II", raw)
    m[msp.GUEST_CLOCK_ADDR] = f32(12.5)
    return m


MUSIC_TOC = {"M51_M01.VPK": (0x1000, 0x800), "M51_M02.VPK": (0x2000, 0x800), "M51_048.VPK": (0xa387580, 0x1c280),
             "__data__": (0x4c800, 0)}


class TestMusicDecode(unittest.TestCase):
    def test_globals_signed_bytes(self):
        s = msp.MusicSample()
        s.globals = music_globals(lvl=-1, alert=2, chg=1, reqlvl=-1)
        s.off = 1
        f = msp.decode_music(s)
        self.assertEqual((f["off"], f["lvl"], f["alert"], f["chg"], f["req"]), (1, -1, 2, 1, -1))
        self.assertEqual((f["ent"], f["pl"], f["n"], f["cur"], f["ceh"]), (0, 0, None, None, None))
        self.assertIn("lvl=-1", msp.format_fields(f, msp.MUSIC_FIELDS))
        f2 = msp.decode_music(msp.MusicSample())
        self.assertTrue(all(f2[k] is None for k in msp.MUSIC_FIELDS))

    def test_playlist_and_entries(self):
        h, ents = msp.decode_playlist(playlist(n=3, cur=1, stop=1), pl_entries())
        self.assertEqual((h["n"], h["cur"], h["done"], h["stop"]), (3, 1, 0, 1))
        self.assertEqual(len(ents), 3)
        self.assertEqual(ents[1]["def"], 0)                         # the REST
        self.assertAlmostEqual(ents[1]["pause"], 12.0)
        self.assertAlmostEqual(ents[1]["elapsed"], 3.25)
        self.assertEqual(ents[2]["def"], DEF_B)
        h, ents = msp.decode_playlist(playlist(cur=-1), None)
        self.assertEqual((h["cur"], ents), (-1, []))
        self.assertEqual(msp.decode_playlist(None), (None, []))

    def test_describe_playlist_marks_the_cursor_and_the_rest(self):
        h, ents = msp.decode_playlist(playlist(n=3, cur=1), pl_entries())
        info = {0: (def_words(name_ptr=NAME_A, flags_a=1, flags_b=8), name_words("M51_M01"), None)}
        s = msp.describe_playlist(h, ents, info, [0, 0xee89a], MUSIC_TOC, names={DEF_B: "M51_M02"})
        self.assertEqual(s, "playlist n=3 cur=1 done=0 stop=0 [M51_M01 | >rest 12.0s at 3.2 | M51_M02]")
        h, ents = msp.decode_playlist(playlist(n=3, cur=2), pl_entries(cur_sentry=SENT))
        info[2] = (def_words(name_ptr=NAME_B, flags_a=1, flags_b=8), name_words("M51_M02"), [0x04000099, DEF_B])
        s = msp.describe_playlist(h, ents, info, [0, 0xee89a], MUSIC_TOC)
        self.assertTrue(s.startswith("playlist n=3 cur=2 done=0 stop=0 [M51_M01 | rest 12.0s | >M51_M02] cur def M51_M02 "), s)
        self.assertIn("group 1", s)
        self.assertIn("sector 0xee89e+0x0 size 0x800 handle 0x4000099", s)
        # an entry with neither its def block nor a learnt name is printed by pointer; more entries than read are counted
        h, ents = msp.decode_playlist(playlist(n=5, cur=0), pl_entries())
        s = msp.describe_playlist(h, ents, {}, None, MUSIC_TOC)
        self.assertIn(f">def@{DEF_A:#x} | rest 12.0s | def@{DEF_B:#x} | +2 more]", s)

    def test_weights_line(self):
        self.assertEqual(msp.describe_weights({0: [0.5, 0.5], 1: [1.0]}, {}), "weights STEALTH[0.50,0.50] FIGHT[1.00]")
        self.assertIsNone(msp.describe_weights({}, {}))


class TestMusicPeek(unittest.TestCase):
    def items_for(self, mem):
        got = {}
        read = lambda a: mem.get(a, 0)  # noqa: E731
        for item in msp.MUSIC_PEEK_SPEC.split(","):
            addr, words = resolve(read, item)
            if addr is not None:
                got[addr] = [mem.get(addr + 4 * i, 0) for i in range(words)]
        return got

    def test_spec_resolves_every_block_and_stays_under_the_cap(self):
        g = music_globals(pl=PL, lvl=0)
        mem = music_memory(g, playlist(n=3, cur=2), pl_entries(cur_sentry=SENT), [0x04000099, DEF_B])
        items = self.items_for(mem)
        for addr in (msp.MUSIC_ADDR, msp.TABLES_ADDR, LIST0, LIST1, W0, W1, PL, PL_DATA, DEF_A, DEF_B, NAME_A, NAME_B, SENT):
            self.assertIn(addr, items, hex(addr))
        self.assertTrue(all(len(v) <= 64 for v in items.values()))
        s = msp.music_sample_from_peek(items)
        f = msp.decode_music(s)
        self.assertEqual((f["lvl"], f["pl"], f["n"], f["cur"], f["ceh"], f["pli"]), (0, PL, 3, 2, 0x04000099, 0))
        self.assertEqual(msp.playlist_index(f["pli"]), (0, 0))
        self.assertEqual(s.weights[0], [0.5, 0.5])
        self.assertEqual(s.lists[1], [0xe2aa00])
        self.assertEqual(msp.cstring(s.entry_info[2][1]), "M51_M02")
        self.assertEqual(s.entry_info[2][2], [0x04000099, DEF_B])
        self.assertNotIn(1, s.entry_info)                            # the rest has no def and no sound entry

    def test_single_stem_by_chain(self):
        mem = music_memory(music_globals(ent=ENTRY, lvl=1))
        s = msp.music_sample_from_peek(self.items_for(mem))
        f = msp.decode_music(s)
        self.assertEqual((f["lvl"], f["ent"], f["eh"], f["pl"], f["pli"]), (1, ENTRY, 0x04000077, 0, None))
        self.assertEqual(msp.cstring(s.name), "M51_048")

    def test_rows_without_the_block_are_skipped_and_tracked_rows_carry_the_playlist(self):
        out = io.StringIO()
        tr = msp.Tracker(out, t0=0.0, toc=MUSIC_TOC, what="music")
        idle = music_memory(music_globals())
        lines = [sampler(1.0, 60), "[peek] @416054: 00000000(0)", sampler(1.1, 66),
                 peek_row(idle, [(a, len(w)) for a, w in self.items_for(idle).items()])]
        playing = music_memory(music_globals(pl=PL, lvl=0), playlist(n=3, cur=0), pl_entries(), None)
        lines += [sampler(1.2, 72), peek_row(playing, [(a, len(w)) for a, w in self.items_for(playing).items()])]
        resting = music_memory(music_globals(pl=PL, lvl=0), playlist(n=3, cur=1), pl_entries(), None)
        lines += [sampler(20.0, 1200), peek_row(resting, [(a, len(w)) for a, w in self.items_for(resting).items()])]
        msp.feed_ours_lines(lines, tr, base_epoch=0.0)
        text = out.getvalue()
        self.assertIn("# t=1.100 weights STEALTH[0.50,0.50] FIGHT[1.00]", text)
        evs = [msp.parse_change_line(ln) for ln in text.splitlines() if not ln.startswith("#")]
        self.assertEqual(len(evs), 3)
        self.assertEqual((evs[0]["vsync"], evs[0]["fields"]["lvl"], evs[0]["fields"]["off"]), (66, -1, 0))
        self.assertIn("lvl -1->0", evs[1]["what"])
        self.assertIn("pl 0x0->0xe2a100", evs[1]["what"])
        self.assertTrue(evs[1]["note"].startswith("level stealth-list; list STEALTH#0; playlist n=3 cur=0 done=0 stop=0 [>M51_M01 | rest 12.0s | M51_M02]"), evs[1]["note"])
        self.assertEqual(evs[2]["what"], "cur 0->1")                  # a REST holds no sound entry: ceh stays 0
        self.assertIn("[M51_M01 | >rest 12.0s at 3.2 | M51_M02]", evs[2]["note"])
        self.assertEqual(tr.samples, 3)


class TestMusicPine(unittest.TestCase):
    def test_sampler_reads_the_playlist_and_caches_the_defs(self):
        mem = music_memory(music_globals(pl=PL, lvl=2, alert=2), playlist(n=3, cur=2), pl_entries(cur_sentry=SENT), [0x04000099, DEF_B])
        reads = []

        def read32(a):
            reads.append(a)
            return mem.get(a, 0)
        ps = msp.MusicPineSampler(read32)
        s = ps.sample()
        f = msp.decode_music(s)
        self.assertEqual((f["lvl"], f["alert"], f["n"], f["cur"], f["ceh"]), (2, 2, 3, 2, 0x04000099))
        self.assertEqual(sorted(s.entry_info), [0, 2])
        self.assertEqual(msp.cstring(s.entry_info[0][1]), "M51_M01")
        self.assertIsNone(s.entry_info[0][2])                        # only the cursor's sound entry is read
        n1 = len(reads)
        ps.sample()
        self.assertEqual(len(reads) - n1, n1 - 2 * (9 + 8) - 2)      # the two defs + names and the store, once

    def test_nothing_installed(self):
        mem = music_memory(music_globals())
        s = msp.MusicPineSampler(lambda a: mem.get(a, 0)).sample()
        self.assertIsNone(s.pl)
        self.assertIsNone(s.entry)
        self.assertEqual(s.weights[1], [1.0])


class TestMusicCompare(unittest.TestCase):
    def test_music_logs_compare_on_the_level_and_list_the_stems(self):
        with tempfile.TemporaryDirectory() as d:
            idle = {k: None for k in msp.MUSIC_FIELDS}
            idle.update(off=0, lvl=-1, alert=0, chg=0, req=-1, reqdef=0, ent=0, pl=0)
            play = dict(idle, lvl=0, pl=PL, pli=0, n=3, cur=0, done=0, stop=0, ceh=0x4000099)
            rest = dict(play, cur=1, ceh=None)
            nxt = dict(play, cur=2)
            pl_note = "level stealth-list; list STEALTH#0; playlist n=3 cur=0 done=0 stop=0 [>M51_M01 | rest 12.0s | M51_M02] cur def M51_M01 fmt VPK type 0 flags 0x01/0x08 group 1 bank 3 id 0x12 sector 0xee89e+0x0 size 0x800 handle 0x4000099"
            rows = [(0.0, idle, " ".join(f"{k} -->{msp.fmt_field(k, idle[k])}" for k in msp.MUSIC_FIELDS)),
                    (100.0, play, "lvl -1->0 pl 0x0->0xe2a100 pli -->0 n -->3 cur -->0 done -->0 stop -->0 ceh -->0x4000099", pl_note),
                    (130.0, rest, "cur 0->1 ceh 0x4000099->-", pl_note.replace("cur=0", "cur=1").replace("[>M51_M01 | rest 12.0s | M51_M02]", "[M51_M01 | >rest 12.0s at 0.1 | M51_M02]").split(" cur def")[0]),
                    (142.0, nxt, "cur 1->2 ceh -->0x40000aa", pl_note.replace("cur=0", "cur=2").replace("[>M51_M01 | rest 12.0s | M51_M02]", "[M51_M01 | rest 12.0s | >M51_M02]").replace("cur def M51_M01", "cur def M51_M02"))]
            log = os.path.join(d, "m.txt")
            with open(log, "w") as f:
                f.write("# music_state_poll what=music target=test started=1000.000\n")
                for ev in rows:
                    t, fields, what = ev[:3]
                    note = f" || {ev[3]}" if len(ev) > 3 else ""
                    f.write(f"wall={1000 + t:.3f} t={t:.3f} {msp.format_fields(fields, msp.MUSIC_FIELDS)} | {what}{note}\n")
            evs, t0, what = msp.read_log(log)
            self.assertEqual((what, t0), ("music", 1000.0))
            out = io.StringIO()
            msp.compare(log, log, "t:90", "t:90", out=out, width=70)
            text = out.getvalue()
            self.assertIn("+10.00 lvl idle->stealth-list (0/3 M51_M01)", text)
            self.assertIn("+40.00 cur 0->1 (1/3 rest 12.0s at 0.1)", text)
            self.assertIn("lvl transitions after the HUD", text)
            self.assertIn("starts (idle->) after the HUD: A 1, B 1; first at A +10.0s B +10.0s", text)
            self.assertIn("A played: M51_M01@+10.0, rest 12.0s@+40.0, M51_M02@+52.0", text)


if __name__ == "__main__":
    unittest.main()
