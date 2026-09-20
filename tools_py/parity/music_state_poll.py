#!/usr/bin/env python
"""Poll the game's EE-side CUE MANAGER (the mission's voice/music cue sequencer, FUN_0034afd0) on either
machine and log every change of what it DECIDED -- state transitions, cue-queue entries, the handle
words -- with the sound ENTRY and the sound DEF behind the playing cue decoded (name, disc sector,
group, flags, the IOP handle), so two driven runs compare by decisions and not only by sound
(sprint-10 music round four, validation item 3).

The manager (research/36 "The music manager"; decomp `game/analysis/socom2_game.elf.decomp.c`):

  DAT_0049e150  byte   the ROUTE: 0 = not initialised (FUN_0034b8c0 :246983), 1 = the 989DSTRM headset
                       extension (FUN_0034bb80 :247109), 2 = the plain 0x2c speaker path (:247104;
                       FUN_0034b410 :246844 falls back to it). FUN_0034b3b0 (:246813-246817) picks the
                       state machine by it: 2 -> FUN_0034afd0.
  DAT_0049e158  word   POINTER to the manager, a 0x40-byte heap object (FUN_0034bc60 :247129-247134:
                       FUN_00180e10(0x40) then the constructor FUN_0034b910 :246990-247023).
  manager +0x09 byte   state: 4 reset (-> zero the handle words, 3; :246701-246706), 3 idle,
                       1 playing (:246707-246725), 0 / 2 the extension route's own states.
  manager +0x0a byte   interrupt flag: set by FUN_0034aac0 (:246598) when a type-1/2 cue arrives over
                       the playing one; consumed at :246718-246723 (StopSound, free, state 3).
  manager +0x0b byte   enable: 1 from the constructor (:247015), cleared by FUN_0034aa70 (:246545); a
                       popped cue with enable 0 is dropped (:246745-246749) and FUN_0034b6c0 queues a cue
                       only when enable != 0 or the cue is type 3 / flagged (:246921-246922).
  manager +0x0c word   the current cue's id (FUN_0034b510 pops it here :246895 / :246727).
  manager +0x10 word   the current cue's sound DEF pointer (:246896; layout below).
  manager +0x14 word   the current cue's volume, vol << 10 (:246897; :242114 `iVar7 << 10`).
  manager +0x18/+0x1c/+0x20  the CUE QUEUE, a vector<int> of slot indices (capacity, SIZE, data):
                       FUN_0034b6c0 pushes at the back (:246932), FUN_0034b510 pops the front (:246898),
                       both iterate data[0..size) (:246871-246873). Occupancy = word +0x1c.
  manager +0x24/+0x28/+0x2c  the FREE-SLOT vector: 20 slots pushed by the constructor (:247008-247012),
                       popped from the back (:246923-246928). Word +0x28 = free slots = 20 - queued.
  manager +0x30 word   the slot array, 20 x {cue id, def, vol} (0xf0 bytes, :247006; filled :246929-246931).
  manager +0x34 word   [word 0xd] the sound ENTRY of the playing cue (FUN_00347960 :246752-246753; freed by
                       FUN_00347810 :246713 / :246720 / :246758); 0 = none.
  manager +0x38 word   [word 0xe] the resumable cue's def pointer (:246769-246771, cleared by FUN_0034b890 :246956).
  manager +0x3c word   [word 0xf] that cue's id (:246772 = +0xc); 0xffffffff = none (:246704, :246766).

The sound ENTRY (0x28 bytes, FUN_00347960 :244640-244656 allocates, FUN_00347690 initialises):
  +0x00  the IOP handle word: -1 = pending (FUN_00347960(-1, def)), then the 0x19 / 0x21 answer stored
         by the callback 0x346300 (research/36: handle or 0); 0 = dead (FUN_00346d70 :244263-244272).
         The poll FUN_00346ea0 (:244311-244400) sets -1 and asks again every frame; a 0 answer frees it.
  +0x04  the def pointer (FUN_00347690 `param_1[1] = param_3`; :242123).
  +0x08  volume scale float (1.0 at init); +0x0c pan / last angle; +0x10..+0x18 position.
  +0x1c  flag byte: bit 0 positioned, bits 2/3 set when freed while pending (FUN_00347810 :244603-244604),
         bit 3 stop / bit 4 pause / bit 5 continue requests (FUN_00346ea0 :244327-244340), bit 6 "alive
         regardless" (FUN_00346d70).
  +0x20  fade timer, seconds (FUN_00346dd0 :244290-244306); +0x24 the owner handed in at :242131.

The sound DEF (the fields the play path reads, FUN_00342240 :241795-241900 and FUN_00343140):
  +0x04 float volume scale; +0x0c / +0x0e u16 near / far distance; +0x10 byte bank index (into the
  table at DAT_0048dbf0, 0x18 bytes each); +0x12 u16 sound id in the bank; +0x1c flags A: bit 0 =
  streamed from a store file (:242118), bit 3 = routed through this cue manager (:242112 `<< 0x3c`),
  bit 4 = resumable, group 6 (:241880); +0x1d flags B: bits 5-7 = the cue TYPE (2 / 3 interrupt,
  :246933-246938), (B & 0x1f) >> 2 = the FORMAT selector (2 = "%s.VPK", else "%s.VAG"; 3 = gated,
  :241817-241833); +0x20 the name string pointer (FUN_001988d0(buf, "%s.VAG", name) :241829-241833),
  +0x24 a second name (a second stream, :241847). GROUP (:241875-241887): format 2 -> 1 (music), else
  flags-A bit 4 -> 6, else format 3 -> 2 (voice), else 0.
  The SECTOR is not in the def: FUN_0034d480 (:248078) looks the name up in the VAGSTORE dictionary
  (the store at 0x48dc30; FUN_0034d470 = store+0x1c = the data base sector) and returns `loc`;
  sector = base + (loc >> 11), offset = loc & 0x7ff (:246784-246788). `loc` is the record offset in
  RUN/SOUNDS/VAGSTORE.ZAR's TOC (header: u32 0, count, name-blob bytes, the blob's guest address,
  0x800; the blob at 0x64; then u32 count-1 and 16-byte records {name ptr, offset, size, 0}; the data
  section starts at the records' end rounded up to 0x800 -- verified against three of ours' 0x2c plays
  and the console's M51_048 at sector 0x102fa8).

Two targets, one log format:

  --target pcsx2   reads the words over PINE (cam_poll's pointer-chain resolver); the entry every
                   sample while one is set, the def + name once per new def, the queue slots on a
                   non-empty queue. --hz 5 has run a full mission; 20 Hz coincided with a PCSX2 exit
                   once (cause unproven).
  --target ours    reads the exe's own `[pc-sampler]` + `[peek]` rows (PS2X_PC_SAMPLER=0.05 and the
                   PS2X_PEEK spec the tool prints, exported before the capture; drive.py passes the
                   environment through) from a run log, live (--follow) or after the fact. Every block
                   is found by ADDRESS (the pointer word peeked beside it), never by item index.

One line per CHANGE: `wall=<epoch s> t=<s of the poll's own clock> [vsync=<ours' frame counter>]
[clock=MM:SS] <all fields> | <what changed> [|| the def decoded]`.

`compare` takes two such logs and each run's HUD anchor (a run directory: the drive.stdout's
`untilref(...ref_hud...)` match, timed by the next step's PNG; `t:<s>` in that log's own t= clock,
e.g. drive.stdout's step time for ours; or an epoch) and prints the two timelines side by side.

Usage:
  python -m tools_py.parity.music_state_poll --target pcsx2 --port 28011 --hz 5 --seconds 600 --out logs/parity/X/music_state.txt
  python -m tools_py.parity.music_state_poll --target ours --log logs/parity/X/game.log --out logs/parity/X/music_state.txt
  python -m tools_py.parity.music_state_poll --target ours --log latest --follow --seconds 600 --out ...
  python -m tools_py.parity.music_state_poll compare A/music_state.txt B/music_state.txt --hud-a t:310.7 --hud-b B --window=-20:200
"""
import argparse
import glob
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tools_py.parity.cam_poll import pine_port, resolve  # noqa: E402

ROUTE_ADDR = 0x49e150            # DAT_0049e150, byte 0 of the word
MGR_PTR_ADDR = 0x49e158          # DAT_0049e158 -> the manager
MGR_WORDS = 16                   # 0x40 bytes
ENTRY_WORDS = 10                 # 0x28 bytes
DEF_WORDS = 16                   # the def's first 0x40 bytes (name pointers at +0x20 / +0x24)
NAME_WORDS = 8                   # 32 bytes of the name string
STORE_BASE_ADDR = 0x48dc48       # the VAGSTORE object 0x48dc30 + 0x18 (second store) and + 0x1c (FUN_0034d470)
CLOCK_ADDR = 0x408f10            # the HUD timer string "MM:SS" (research/19 :217)
GUEST_CLOCK_ADDR = 0x4365c0      # the guest clock, float seconds (KNOWN.md, freeze detection)
QUEUE_SLOTS = 20                 # the constructor's 0x14 free slots
SLOT_WORDS = 3

VAGSTORE_ZAR = os.path.join("game", "disc", "RUN", "SOUNDS", "VAGSTORE.ZAR")
VAGSTORE_DATA_LBN = 0xee89a      # this disc: file LBN 0xee801 + 0x99 sectors of TOC (iso_lbn + the ZAR header)

# What ours must be launched with: every block the PINE poll reads, chained from the manager pointer.
OURS_PEEK_SPEC = ",".join([
    f"{ROUTE_ADDR:#x}:1", f"{MGR_PTR_ADDR:#x}:1", f"*{MGR_PTR_ADDR:#x}:{MGR_WORDS}",
    f"*{MGR_PTR_ADDR:#x}+0x34*:{ENTRY_WORDS}",                 # the entry
    f"*{MGR_PTR_ADDR:#x}+0x34*+0x4*:{DEF_WORDS}",              # its def
    f"*{MGR_PTR_ADDR:#x}+0x34*+0x4*+0x20*:{NAME_WORDS}",       # the def's name string
    f"*{MGR_PTR_ADDR:#x}+0x20*:{QUEUE_SLOTS}",                 # the cue queue's index data
    f"*{MGR_PTR_ADDR:#x}+0x30*:{QUEUE_SLOTS * SLOT_WORDS}",    # the slot array (60 words, under the 64 cap)
    f"{STORE_BASE_ADDR:#x}:2", f"{CLOCK_ADDR:#x}:2", f"{GUEST_CLOCK_ADDR:#x}:1"])
OURS_SAMPLER_S = "0.05"

FIELDS = ("mode", "state", "irq", "en", "cue", "def", "vol", "q", "free", "h34", "h38", "h3c", "ih", "ef")
HEX_FIELDS = ("cue", "def", "vol", "h34", "h38", "h3c", "ih", "ef")
STATE_NAMES = {4: "reset", 3: "idle", 1: "playing", 0: "ext-started", 2: "ext-pending"}


class Sample:
    """One reading of every block: the words as the guest holds them (None = the block was not there)."""

    def __init__(self, route=0, mgr=None, entry=None, sdef=None, name=None, qidx=None, slots=None,
                 store=None, clk=None, gclk=None):
        self.route, self.mgr, self.entry, self.sdef, self.name = route, mgr, entry, sdef, name
        self.qidx, self.slots, self.store, self.clk, self.gclk = qidx, slots, store, clk, gclk


def decode(route_word, mgr_words, entry_words=None):
    """The manager's fields out of the DAT_0049e150 word, the 16 manager words (None = no manager) and the
    entry's words (None = no entry: ih/ef read '-')."""
    f = {"mode": route_word & 0xff}
    if mgr_words is None:
        for k in FIELDS[1:]:
            f[k] = None
        return f
    w2 = mgr_words[2]
    f["state"] = (w2 >> 8) & 0xff
    f["irq"] = (w2 >> 16) & 0xff
    f["en"] = (w2 >> 24) & 0xff
    f["cue"] = mgr_words[3]
    f["def"] = mgr_words[4]
    f["vol"] = mgr_words[5]
    f["q"] = mgr_words[7]
    f["free"] = mgr_words[10]
    f["h34"] = mgr_words[13]
    f["h38"] = mgr_words[14]
    f["h3c"] = mgr_words[15]
    if entry_words is None or len(entry_words) < ENTRY_WORDS:
        f["ih"] = f["ef"] = None
    else:
        f["ih"] = entry_words[0]
        f["ef"] = entry_words[7] & 0xff
    return f


def decode_def(def_words, name_words=None):
    """The def's play-path fields: name, format, type, flags, group, bank/id, the name key for the store."""
    if def_words is None or len(def_words) < DEF_WORDS:
        return None
    raw = b"".join(w.to_bytes(4, "little") for w in def_words)
    flags_a, flags_b = raw[0x1c], raw[0x1d]
    fmt = (flags_b & 0x1f) >> 2
    d = {"vol_scale": struct.unpack_from("<f", raw, 4)[0],
         "near": struct.unpack_from("<H", raw, 0xc)[0], "far": struct.unpack_from("<H", raw, 0xe)[0],
         "bank": raw[0x10], "id": struct.unpack_from("<H", raw, 0x12)[0],
         "flags_a": flags_a, "flags_b": flags_b, "type": flags_b >> 5, "fmt": fmt,
         "stream": flags_a & 1, "name_ptr": def_words[8], "name2_ptr": def_words[9],
         "name": cstring(name_words)}
    d["group"] = 1 if fmt == 2 else 6 if flags_a & 0x10 else 2 if fmt == 3 else 0
    d["ext"] = "VPK" if fmt == 2 else "VAG"
    d["key"] = (d["name"] + "." + d["ext"]).upper() if d["name"] else None
    return d


def cstring(words):
    if not words:
        return None
    raw = b"".join(w.to_bytes(4, "little") for w in words).split(b"\0", 1)[0]
    s = raw.decode("ascii", "replace")
    return s if s and all(32 <= ord(c) < 127 for c in s) else None


def clock_string(words):
    """'MM:SS' out of the two words at 0x408f10, or None when the string is not set."""
    s = cstring(words[:2]) if words and len(words) >= 2 else None
    return s if s and re.fullmatch(r"\d\d:\d\d", s) else None


def guest_clock(word):
    if word is None:
        return None
    v = struct.unpack("<f", struct.pack("<I", word))[0]
    return v if v == v and abs(v) < 1e7 else None


def queued_ids(qidx, slots, q):
    """The cue ids of the queued slots, front first (None when the blocks were not read)."""
    if qidx is None or slots is None or q is None:
        return None
    out = []
    for i in qidx[:q]:
        if 0 <= i < QUEUE_SLOTS and len(slots) >= (i + 1) * SLOT_WORDS:
            out.append(slots[i * SLOT_WORDS])
    return out


# ---- the VAGSTORE TOC ------------------------------------------------------------------------------

_TOC_CACHE = {}


def vagstore_toc(path=VAGSTORE_ZAR):
    """{NAME.EXT (upper): (record offset, size)} of a ZAR store, plus the data base in bytes under
    '__data__'. None when the file is absent."""
    if path in _TOC_CACHE:
        return _TOC_CACHE[path]
    if not os.path.exists(path):
        _TOC_CACHE[path] = None
        return None
    with open(path, "rb") as f:
        head = f.read(0x14)
        _zero, n, name_bytes, name_va, _align = struct.unpack("<5I", head)
        f.seek(0x64)
        blob = f.read(name_bytes)
        f.seek(0x64 + name_bytes)
        tab = f.read(0x10 + 16 * n)
    count = struct.unpack_from("<I", tab, 0xc)[0] + 1       # the u32 before the records is count - 1
    count = min(count, n)
    toc = {}
    for i in range(count):
        name_ptr, off, size, _ = struct.unpack_from("<4I", tab, 0x10 + 16 * i)
        o = name_ptr - name_va
        if not (0 <= o < len(blob)):
            continue
        end = blob.find(b"\0", o)
        name = blob[o:end if end >= 0 else len(blob)].decode("ascii", "replace")
        toc[name.upper()] = (off, size)
    rec_end = 0x64 + name_bytes + 0x10 + 16 * n
    toc["__data__"] = ((rec_end + 0x7ff) & ~0x7ff, 0)
    _TOC_CACHE[path] = toc
    return toc


def store_sector(key, base_lbn=None, toc=None):
    """(sector, offset, size) of a store file by its key, or None. `base_lbn` = the store's data base
    sector (the peeked FUN_0034d470 word, else this disc's constant)."""
    toc = vagstore_toc() if toc is None else toc
    if not toc or key is None or key.upper() not in toc:
        return None
    off, size = toc[key.upper()]
    base = base_lbn or VAGSTORE_DATA_LBN
    return base + (off >> 11), off & 0x7ff, size


def describe_def(d, ih=None, store_words=None, toc=None):
    """`def M51_048 fmt VAG type 1 flags 0x09/0x29 group 2 bank 3 id 0x12 sector 0x102fa8+0x0 size 0x1c280 handle 0x0400029e`."""
    if d is None:
        return None
    base = store_words[1] if store_words and len(store_words) >= 2 and store_words[1] else None
    parts = [f"def {d['name'] or '?'}", f"fmt {d['ext']}", f"type {d['type']}",
             f"flags {d['flags_a']:#04x}/{d['flags_b']:#04x}", f"group {d['group']}",
             f"bank {d['bank']}", f"id {d['id']:#x}"]
    loc = store_sector(d["key"], base, toc)
    if loc:
        parts.append(f"sector {loc[0]:#x}+{loc[1]:#x} size {loc[2]:#x}")
    elif d["key"]:
        parts.append(f"sector ? ({d['key']} not in the TOC)")
    if ih is not None:
        parts.append(f"handle {fmt_field('ih', ih)}")
    return " ".join(parts)


# ---- change lines ----------------------------------------------------------------------------------

def fmt_field(k, v):
    if v is None:
        return "-"
    if k in HEX_FIELDS:
        return f"{v:#x}" if v != 0xffffffff else "-1"
    return str(v)


def format_fields(f):
    return " ".join(f"{k}={fmt_field(k, f.get(k))}" for k in FIELDS)


def diff_fields(prev, cur):
    """[(field, old, new)] for the fields that differ (prev None = everything is new)."""
    if prev is None:
        return [(k, None, cur.get(k)) for k in FIELDS]
    return [(k, prev.get(k), cur.get(k)) for k in FIELDS if prev.get(k) != cur.get(k)]


def format_change_line(wall, t, f, changes, vsync=None, clock=None, gclock=None, note=None):
    head = f"wall={wall:.3f} t={t:.3f}"
    if vsync is not None:
        head += f" vsync={vsync}"
    if clock is not None:
        head += f" clock={clock}"
    if gclock is not None:
        head += f" gclock={gclock:.2f}"
    what = " ".join(f"{k} {fmt_field(k, o)}->{fmt_field(k, n)}" for k, o, n in changes)
    line = f"{head} {format_fields(f)} | {what}"
    if note:
        line += f" || {note}"
    return line


_LINE_RE = re.compile(r"^wall=(?P<wall>[-\d.]+) t=(?P<t>[-\d.]+)(?: vsync=(?P<vsync>\d+))?(?: clock=(?P<clock>\d\d:\d\d))?"
                      r"(?: gclock=(?P<gclock>[-\d.]+))? (?P<fields>.*?) \| (?P<what>.*?)(?: \|\| (?P<note>.*))?$")


def parse_change_line(line):
    """A change line -> dict(wall, t, vsync, clock, gclock, fields, what, note) or None for other lines."""
    m = _LINE_RE.match(line.strip())
    if not m:
        return None
    fields = {}
    for tok in m.group("fields").split():
        k, v = tok.split("=", 1)
        fields[k] = None if v == "-" else 0xffffffff if v == "-1" else int(v, 0)
    return {"wall": float(m.group("wall")), "t": float(m.group("t")),
            "vsync": int(m.group("vsync")) if m.group("vsync") else None,
            "clock": m.group("clock"), "gclock": float(m.group("gclock")) if m.group("gclock") else None,
            "fields": fields, "what": m.group("what"), "note": m.group("note")}


NOTE_ON = ("state", "h34", "ih", "q")     # the changes that earn the decoded def / queue on the line


class Tracker:
    """Feeds samples in, writes the change lines out (the first sample is a change of everything)."""

    def __init__(self, out, t0=None, toc=None):
        self.out = out
        self.t0 = t0
        self.prev = None
        self.changes = 0
        self.samples = 0
        self.toc = toc

    def feed(self, wall, fields, vsync=None, clock=None, gclock=None, t=None, sample=None):
        if self.t0 is None:
            self.t0 = wall
        self.samples += 1
        changes = diff_fields(self.prev, fields)
        if not changes:
            return None
        self.prev = dict(fields)
        self.changes += 1
        note = None
        if sample is not None and any(k in NOTE_ON for k, _o, _n in changes):
            bits = []
            d = describe_def(decode_def(sample.sdef, sample.name), fields.get("ih"), sample.store, self.toc)
            if d:
                bits.append(d)
            ids = queued_ids(sample.qidx, sample.slots, fields.get("q"))
            if ids:
                bits.append("queued " + ",".join(f"{i:#x}" for i in ids))
            note = "; ".join(bits) or None
        line = format_change_line(wall, wall - self.t0 if t is None else t, fields, changes, vsync, clock, gclock, note)
        self.out.write(line + "\n")
        self.out.flush()
        return line


# ---- ours: the exe's [pc-sampler] + [peek] rows -------------------------------------------------

_SAMPLER_RE = re.compile(r"\[pc-sampler\].*?\bt=(?P<t>[\d.]+)\b.*?\bvsync=(?P<vsync>\d+)")
_PEEK_ITEM_RE = re.compile(r"@([0-9a-fA-F]+):((?: [0-9a-fA-F]{8}\([^)]*\))+)")


def parse_peek_row(line):
    """A `[peek]` row -> {addr: [words]} (the exe's `@addr: 00000000(0) ...` layout)."""
    items = {}
    for m in _PEEK_ITEM_RE.finditer(line):
        addr = int(m.group(1), 16)
        items[addr] = [int(w, 16) for w in re.findall(r"([0-9a-fA-F]{8})\(", m.group(2))]
    return items


def _block(items, addr, words):
    b = items.get(addr) if addr else None
    return b if b is not None and len(b) >= words else None


def sample_from_peek(items):
    """A Sample out of a peek row's items. Every block is the item at the address the pointer beside
    it holds (the manager at *0x49e158, the entry at manager+0x34, the def at entry+4, the name at
    def+0x20, the queue data / slots at manager+0x20 / +0x30) -- never an index."""
    s = Sample(route=items.get(ROUTE_ADDR, [0])[0])
    s.mgr = _block(items, items.get(MGR_PTR_ADDR, [0])[0], MGR_WORDS)
    if s.mgr:
        s.entry = _block(items, s.mgr[13], ENTRY_WORDS)
        s.qidx = _block(items, s.mgr[8], 1)
        s.slots = _block(items, s.mgr[12], 1)
    if s.entry:
        s.sdef = _block(items, s.entry[1], DEF_WORDS)
    if s.sdef:
        s.name = _block(items, s.sdef[8], 1)
    s.store = items.get(STORE_BASE_ADDR)
    s.clk = items.get(CLOCK_ADDR)
    s.gclk = items.get(GUEST_CLOCK_ADDR, [None])[0]
    return s


def log_start_epoch(path):
    """The launch second out of `run_[A_|B_]YYYYmmdd_HHMMSS.log` (local time), else the file's mtime."""
    m = re.search(r"(\d{8})_(\d{6})", os.path.basename(path))
    if m:
        return time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))
    return os.path.getmtime(path)


def feed_ours_lines(lines, tracker, base_epoch=None, now=None):
    """Feed a run log's lines: each `[peek]` row is stamped with the preceding `[pc-sampler]`'s t= and
    vsync=; wall = now() when following live, else base_epoch + t."""
    t = vsync = None
    for line in lines:
        if line.startswith("[pc-sampler]"):
            m = _SAMPLER_RE.search(line)
            if m:
                t, vsync = float(m.group("t")), int(m.group("vsync"))
            continue
        if not line.startswith("[peek]"):
            continue
        items = parse_peek_row(line)
        if ROUTE_ADDR not in items and MGR_PTR_ADDR not in items:
            continue
        s = sample_from_peek(items)
        wall = now() if now else (base_epoch or 0.0) + (t or 0.0)
        tracker.feed(wall, decode(s.route, s.mgr, s.entry), vsync=vsync, clock=clock_string(s.clk),
                     gclock=guest_clock(s.gclk), t=t, sample=s)


def follow(path, seconds, poll_s=0.05):
    """Yield a file's lines as they arrive, for `seconds` (a stopped writer ends it after 30 s of nothing)."""
    t0 = time.time()
    while not os.path.exists(path) and time.time() - t0 < seconds:
        time.sleep(0.5)
    if not os.path.exists(path):
        return
    with open(path, "r", errors="replace") as f:
        last = time.time()
        while time.time() - t0 < seconds:
            line = f.readline()
            if line:
                last = time.time()
                if line.endswith("\n"):
                    yield line
                continue
            if time.time() - last > 30.0:
                return
            time.sleep(poll_s)


def newest_run_log():
    logs = sorted(glob.glob(os.path.join("logs", "run_*.log")), key=os.path.getmtime)
    return logs[-1] if logs else None


# ---- pcsx2: PINE -----------------------------------------------------------------------------------

class PineSampler:
    """Reads the blocks through `read32`, the cheap ones every sample and the def / name / store once per
    new pointer (a cache keyed by address), the queue data and slots only while the queue is non-empty."""

    def __init__(self, read32):
        self.read32 = read32
        self.defs = {}          # def addr -> (def words, name words)
        self.store = None

    def words(self, addr, n):
        return [self.read32(addr + 4 * i) for i in range(n)]

    def sample(self):
        s = Sample(route=self.read32(ROUTE_ADDR))
        ptr = self.read32(MGR_PTR_ADDR)
        if 0x100000 <= ptr < 0x2000000:
            s.mgr = self.words(ptr, MGR_WORDS)
            ent = s.mgr[13]
            if 0x100000 <= ent < 0x2000000:
                s.entry = self.words(ent, ENTRY_WORDS)
                dp = s.entry[1]
                if 0x100000 <= dp < 0x2000000:
                    if dp not in self.defs:
                        dw = self.words(dp, DEF_WORDS)
                        np_ = dw[8]
                        nw = self.words(np_, NAME_WORDS) if 0x100000 <= np_ < 0x2000000 else None
                        self.defs[dp] = (dw, nw)
                    s.sdef, s.name = self.defs[dp]
            if s.mgr[7] and 0x100000 <= s.mgr[8] < 0x2000000 and 0x100000 <= s.mgr[12] < 0x2000000:
                s.qidx = self.words(s.mgr[8], min(s.mgr[7], QUEUE_SLOTS))
                s.slots = self.words(s.mgr[12], QUEUE_SLOTS * SLOT_WORDS)
        if self.store is None or not self.store[1]:
            self.store = self.words(STORE_BASE_ADDR, 2)
        s.store = self.store
        s.clk = self.words(CLOCK_ADDR, 2)
        s.gclk = self.read32(GUEST_CLOCK_ADDR)
        return s


def sample_from_pine(read32):
    """One-shot: (route word, manager words or None, clock words, guest clock word) -- the first tool's shape."""
    s = PineSampler(read32).sample()
    return s.route, s.mgr, s.clk, s.gclk


def poll_pcsx2(port, out, seconds, hz):
    from tools_py.parity.pine import Pine
    t0 = time.time()
    p = None
    while p is None and time.time() - t0 < 120:
        try:
            p = Pine(port=port)
        except OSError:
            time.sleep(1.0)
    if p is None:
        raise SystemExit(f"no PINE on port {port}")
    tr = Tracker(out, t0=time.time())
    sampler = PineSampler(p.read32)
    period = 1.0 / hz
    while time.time() - t0 < seconds:
        tick = time.time()
        try:
            s = sampler.sample()
            tr.feed(tick, decode(s.route, s.mgr, s.entry), clock=clock_string(s.clk), gclock=guest_clock(s.gclk), sample=s)
        except Exception as e:  # noqa: BLE001 - PCSX2 may be between states
            out.write(f"# t={tick - t0:.3f} error {e}\n")
            out.flush()
            try:
                p.close()
            except Exception:  # noqa: BLE001
                pass
            p = None
            while p is None and time.time() - t0 < seconds:
                try:
                    p = Pine(port=port)
                except OSError:
                    time.sleep(1.0)
            if p is None:
                break
            sampler = PineSampler(p.read32)
        rest = period - (time.time() - tick)
        if rest > 0:
            time.sleep(rest)
    return tr


# ---- compare ---------------------------------------------------------------------------------------

def read_log(path):
    """([change dicts], t0) of a poll log: t0 = the epoch of the log's own t=0 (wall - t of the first
    event, so `t:<s>` anchors land in the same clock the events carry), else the header's started=."""
    events, started = [], None
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith("#"):
                m = re.search(r"started=([\d.]+)", line)
                if m:
                    started = float(m.group(1))
                continue
            ev = parse_change_line(line)
            if ev:
                events.append(ev)
    t0 = events[0]["wall"] - events[0]["t"] if events else started
    return events, t0


_STEP_RE = re.compile(r"^(s\d+_\S+)\s+t=\s*([\d.]+)s")


def hud_anchor_from_drive(run_dir):
    """The epoch of the HUD reference match in a drive run: the first `untilref(...ref_hud...)` line
    with matched=True, timed by the mtime of the NEXT step's PNG (drive.py prints the step line right
    after saving it). Returns (epoch, note) or raises."""
    stdout = os.path.join(run_dir, "drive.stdout")
    lines = open(stdout, "r", errors="replace").read().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("untilref(") and "ref_hud" in line and "matched=True" in line:
            for nxt in lines[i + 1:]:
                m = _STEP_RE.match(nxt)
                if m:
                    png = os.path.join(run_dir, m.group(1) + ".png")
                    if not os.path.exists(png):
                        raise SystemExit(f"{png}: the step after the HUD match has no PNG")
                    return os.path.getmtime(png), f"{os.path.basename(run_dir)}: HUD matched, {m.group(1)} at t={m.group(2)}s"
            raise SystemExit(f"{stdout}: no step line after the HUD match")
    raise SystemExit(f"{stdout}: no `untilref(...ref_hud...)` matched=True line")


def hud_anchor(spec, log_t0):
    """`spec` = a run directory (or its drive.stdout), `t:<seconds in the poll log's own t= clock>`, or
    an epoch. `log_t0` = the epoch of that log's t=0 (read_log)."""
    if spec.startswith("t:"):
        if log_t0 is None:
            raise SystemExit("t:<s> needs a poll log with events or a `started=` header")
        return log_t0 + float(spec[2:]), f"t={spec[2:]}s of the poll log"
    if os.path.isdir(spec):
        return hud_anchor_from_drive(spec)
    if os.path.isfile(spec) and os.path.basename(spec) == "drive.stdout":
        return hud_anchor_from_drive(os.path.dirname(spec))
    return float(spec), "epoch given"


def state_name(v):
    """4 -> 'reset' etc.; accepts the change line's text form ('3', '-')."""
    if v is None or v == "-":
        return "-"
    try:
        return STATE_NAMES.get(int(str(v), 0), str(v))
    except ValueError:
        return str(v)


def _parse_what(what):
    return re.findall(r"(\w+) (\S+)->(\S+)", what)


def event_summary(ev):
    """The short form of an event for the side-by-side listing."""
    parts = []
    for k, o, n in _parse_what(ev["what"]):
        parts.append(f"state {state_name(o)}->{state_name(n)}" if k == "state" else f"{k} {o}->{n}")
    if ev.get("note"):
        # the decoded def right after the first change, ahead of the raw diffs the column may cut off
        m = re.search(r"def (\S+)(?:.*?(sector \S+))?", ev["note"])
        if m and parts:
            parts[0] += f" ({m.group(1)}{' ' + m.group(2) if m.group(2) else ''})"
    extra = f" [{ev['clock']}]" if ev["clock"] else ""
    if ev["vsync"] is not None:
        extra += f" [f{ev['vsync']}]"
    return ", ".join(parts) + extra


def transitions(events):
    """[(hud_rel, old, new)] of the state field."""
    out = []
    for ev in events:
        for k, o, n in _parse_what(ev["what"]):
            if k == "state" and o != "-":
                out.append((ev["rel"], o, n))
    return out


def compare(log_a, log_b, hud_a, hud_b, out=sys.stdout, width=58, window=None):
    ev_a, t0_a = read_log(log_a)
    ev_b, t0_b = read_log(log_b)
    ep_a, note_a = hud_anchor(hud_a, t0_a)
    ep_b, note_b = hud_anchor(hud_b, t0_b)
    for evs, ep in ((ev_a, ep_a), (ev_b, ep_b)):
        for ev in evs:
            ev["rel"] = ev["wall"] - ep
    out.write(f"A: {log_a} ({len(ev_a)} changes) HUD anchor {note_a}\n")
    out.write(f"B: {log_b} ({len(ev_b)} changes) HUD anchor {note_b}\n")
    out.write(f"{'A (s from HUD)':<{width}} | B (s from HUD)\n")
    out.write("-" * (2 * width + 3) + "\n")
    merged = [(ev["rel"], 0, ev) for ev in ev_a] + [(ev["rel"], 1, ev) for ev in ev_b]
    merged.sort(key=lambda x: (x[0], x[1]))
    for rel, side, ev in merged:
        if window is not None and not (window[0] <= rel <= window[1]):
            continue
        cell = f"{rel:+8.2f} {event_summary(ev)}"
        if len(cell) > width:
            cell = cell[:width - 1] + "~"
        out.write(f"{cell:<{width}} |\n" if side == 0 else f"{'':<{width}} | {cell}\n")
    ta, tb = transitions(ev_a), transitions(ev_b)
    out.write("\nstate transitions after the HUD (s from HUD):\n")
    for name, tr in (("A", ta), ("B", tb)):
        post = [x for x in tr if x[0] >= 0]
        out.write(f"  {name}: {len(post)} -- " + ", ".join(f"{o}->{n}@{r:+.1f}" for r, o, n in post[:40])
                  + (" ..." if len(post) > 40 else "") + "\n")
    pa = [x for x in ta if x[0] >= 0 and x[2] == "1"]
    pb = [x for x in tb if x[0] >= 0 and x[2] == "1"]
    out.write(f"  plays (->1) after the HUD: A {len(pa)}, B {len(pb)}; first at A {pa[0][0]:+.1f}s B {pb[0][0]:+.1f}s\n"
              if pa and pb else f"  plays (->1) after the HUD: A {len(pa)}, B {len(pb)}\n")
    for k, (x, y) in enumerate(zip(pa, pb)):
        if k >= 20:
            break
        out.write(f"    play {k + 1}: A {x[0]:+7.1f}  B {y[0]:+7.1f}  d={y[0] - x[0]:+.1f}s\n")

    def pushes(evs):
        return sum(1 for ev in evs if ev["rel"] >= 0 and
                   any(k == "q" and o != "-" and int(n) > int(o) for k, o, n in _parse_what(ev["what"])))
    out.write(f"  cue-queue pushes seen after the HUD: A {pushes(ev_a)}, B {pushes(ev_b)} "
              "(a push and its pop inside one sample period are invisible)\n")
    # the cues each side played, by def name, in order: the decision list the two runs are compared on
    for name, evs in (("A", ev_a), ("B", ev_b)):
        played = []
        for ev in evs:
            if ev["rel"] >= 0 and ev.get("note") and any(k == "state" and n == "1" for k, _o, n in _parse_what(ev["what"])):
                m = re.search(r"def (\S+)", ev["note"])
                played.append(f"{m.group(1) if m else '?'}@{ev['rel']:+.1f}")
        if played:
            out.write(f"  {name} played: " + ", ".join(played[:40]) + (" ..." if len(played) > 40 else "") + "\n")


# ---- main ------------------------------------------------------------------------------------------

def join_negative_window(argv):
    """`--window -20:200` -> `--window=-20:200` (argparse reads a leading '-' as an option)."""
    out, i = [], 0
    while i < len(argv):
        if argv[i] == "--window" and i + 1 < len(argv) and argv[i + 1].startswith("-"):
            out.append(f"--window={argv[i + 1]}")
            i += 2
            continue
        out.append(argv[i])
        i += 1
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "compare":
        ap = argparse.ArgumentParser(prog="music_state_poll compare")
        ap.add_argument("log_a")
        ap.add_argument("log_b")
        ap.add_argument("--hud-a", required=True, help="run dir (drive.stdout + PNGs), t:<s> of the log's own clock, or an epoch")
        ap.add_argument("--hud-b", required=True)
        ap.add_argument("--window", default=None, help="lo:hi seconds from the HUD to list (write --window=-20:200)")
        a = ap.parse_args(join_negative_window(argv[1:]))
        win = tuple(float(v) for v in a.window.split(":")) if a.window else None
        compare(a.log_a, a.log_b, a.hud_a, a.hud_b, window=win)
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=("pcsx2", "ours"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=600.0)
    ap.add_argument("--hz", type=float, default=10.0, help="pcsx2 sample rate (5 has run a whole mission)")
    ap.add_argument("--port", type=int, default=0, help="PINE port (default: PINESlot from PCSX2.ini)")
    ap.add_argument("--log", default="latest", help="ours: the run log (`latest` = newest logs/run_*.log)")
    ap.add_argument("--follow", action="store_true", help="ours: tail the log live (wall = now)")
    ap.add_argument("--log-start", type=float, default=None, help="ours, offline: the log's launch epoch")
    a = ap.parse_args(argv)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    toc = vagstore_toc()
    with open(a.out, "w") as out:
        started = time.time()
        if a.target == "pcsx2":
            port = a.port or pine_port()
            out.write(f"# music_state_poll target=pcsx2 port={port} hz={a.hz} started={started:.3f} "
                      f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started))} toc={'yes' if toc else 'no'}\n")
            tr = poll_pcsx2(port, out, a.seconds, a.hz)
        else:
            path = a.log
            if path == "latest":
                t0 = time.time()
                path = newest_run_log()
                while a.follow and (path is None or os.path.getmtime(path) < started - 5) and time.time() - t0 < 120:
                    time.sleep(1.0)
                    path = newest_run_log()
                if path is None:
                    raise SystemExit("no logs/run_*.log")
            base = a.log_start if a.log_start is not None else log_start_epoch(path)
            out.write(f"# music_state_poll target=ours log={path} follow={a.follow} started={started:.3f} "
                      f"log_start={base:.3f} toc={'yes' if toc else 'no'} peek={OURS_PEEK_SPEC}\n")
            tr = Tracker(out, t0=started if a.follow else base, toc=toc)
            if a.follow:
                feed_ours_lines(follow(path, a.seconds), tr, now=time.time)
            else:
                with open(path, "r", errors="replace") as f:
                    feed_ours_lines(f, tr, base_epoch=base)
        out.write(f"# done samples={tr.samples} changes={tr.changes}\n")
    print(f"{tr.samples} samples, {tr.changes} changes -> {a.out}")
    if a.target == "ours" and tr.samples == 0:
        print(f"no manager rows: launch ours with PS2X_PC_SAMPLER={OURS_SAMPLER_S} PS2X_PEEK=\"{OURS_PEEK_SPEC}\"")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
