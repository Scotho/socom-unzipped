#!/usr/bin/env python
"""Poll the game's EE-side sound DECISION machines on either machine and log every change of what they
decided, with the sound entry / def behind each decision decoded (name, disc sector, group, flags, the
IOP handle), so two driven runs compare by decisions and not only by sound (sprint-10 music round four,
validation item 3). Two machines, chosen by `--what`:

  --what cue    (default) the CUE SEQUENCER of FUN_0034afd0: the mission's voice/one-shot cue queue
                (research/36 "The music manager"; the layout below).
  --what music  the MISSION MUSIC machine of FUN_003492b0 (decomp :245200-246180): the level, the
                alert, the single playing stem or the PLAYLIST with its cursor and its entries -- and
                each entry's PAUSETIME, because an entry with no SNDNAME is a REST (FUN_00349b90).

Decomp = `game/analysis/socom2_game.elf.decomp.c`.

== The cue sequencer (--what cue) ==

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

== The mission music machine (--what music) ==

  DAT_0048e090  byte   the LEVEL (signed): -1 idle; 0 = a STEALTH_MUSIC playlist; 1 = a single def asked
                       by script; 2 = a fight playlist picked by the alert level; 3 = a single def forced
                       (FUN_00348dc0 :245378-245445; FUN_00348b20 :245296-245344 sets 0 / 2 with the playlist).
  DAT_0048e0a0  byte   the ALERT level, 0-3, from the AI threat float (FUN_00348ce0 :245349-245374: <1 -> 0,
                       1..3 -> 1 only from 0, 3..5 -> 2, >=5 -> 3; called from FUN_002a4920 :147892-147916).
  DAT_0048e0a8  byte   "alert changed" (:245372), consumed by the tick (:245570-245573).
  DAT_0048e080  word   the single playing stem's sound ENTRY (levels 1 / 3; :245398, :245407; freed :245552).
  DAT_0048e088  word   the PLAYLIST pointer (:245330-245339); 0 = none.
  DAT_0048e0b0/0b4     a pending request: def pointer + level (0xff = none; :245422-245424, :245431-245433).
  DAT_0048e098  byte   tables loaded (FUN_00349670 :245663-245692 frees first when 1).
  DAT_003e0080  byte   music OFF (FUN_00348860 :245313 sets 1 and stops; FUN_003488e0 :245329 clears; the tick
                       does nothing while set, :245547).
  DAT_0048e010 + level*0xc   per level (0 STEALTH, 1 FIGHT, 2 MED_FIGHT, 3 HEAVY_FIGHT, FUN_00349670): a
                       vector<playlist*> {capacity, COUNT (+4 = DAT_0048e014), DATA (+8 = DAT_0048e018)}.
  DAT_0048e050 + level*0xc   the matching WEIGHT vector<float> {capacity, count (DAT_0048e054), data
                       (DAT_0048e058)}; 1/n each at load (:245649-245656); the roll (FUN_00348b20) picks the
                       playlist whose cumulative weight crosses rand, multiplies its weight by 0.1 and
                       renormalises (FUN_00348900 :245338-245385), resets it (FUN_00349d90) and installs it.
  PLAYLIST (0x18 bytes, FUN_0034a0a0 :246167-246178): +0 capacity, +4 COUNT, +8 DATA (entries of 0x10),
                       +0xc CURSOR (-1 = not started), +0x10 the SEQ_NAME resource handle, +0x14 DONE byte,
                       +0x15 STOP-AFTER-CURRENT byte (FUN_00349c70 :245974-245990, the fade-out on alert 0).
  ENTRY (0x10, FUN_00349c50 :245959-245969, filled by FUN_00349e90 :246077-246135 from the .rdr node's
                       SNDNAME and PAUSETIME): [0] DEF pointer (0 = no sound: a REST), [1] the sound entry
                       while playing (FUN_00349b40 :245905-245916 plays via def vtable +0x1c), [2] PAUSETIME
                       float seconds, [3] ELAPSED float. FUN_00349b90 (:245922-245955): a REST is done when
                       elapsed + dt > PAUSETIME (elapsed reset to 0); a sound entry is done when its entry is
                       0 or FUN_00346d70 says the handle is dead (then freed). PAUSETIME is NOT consulted for
                       an entry with a def. FUN_00349db0 (:246036-246073) advances: cursor -1 -> 0 at once,
                       else on done cursor++ and play the next; past the end or on the stop flag -> DONE.
  The tick FUN_003492b0(dt) (:245541-245595; called from the sound frame update :241568 right after the
                       entries' poll FUN_00347120): playlist done -> DAT_0048e088 = 0, level -1, re-evaluate
                       (FUN_00349100 :245484-245537 -> FUN_00348dc0 -> FUN_00348b20 rolls the next playlist
                       the SAME tick). So between playlists there is no timer; inside a playlist the rests are
                       the entries with no SNDNAME -- what this mode prints per entry.

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
  streamed from a store file (:242118), bit 3 = routed through the cue sequencer (:242112 `<< 0x3c`),
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

  --target pcsx2   reads the words over PINE (cam_poll's pointer-chain resolver); defs and names once
                   per pointer. --hz 5 has run a full mission; 20 Hz coincided with a PCSX2 exit once.
  --target ours    reads the exe's own `[pc-sampler]` + `[peek]` rows (PS2X_PC_SAMPLER and the
                   PS2X_PEEK spec the tool prints for the mode -- `--spec` prints it -- exported before
                   the capture; drive.py passes the environment through) from a run log, live
                   (--follow) or after the fact. Every block is found by ADDRESS (the pointer word
                   peeked beside it), never by item index.

One line per CHANGE: `wall=<epoch s> t=<s of the poll's own clock> [vsync=<ours' frame counter>]
[clock=MM:SS] <all fields> | <what changed> [|| the decoded def / playlist]`.

`compare` takes two such logs and each run's HUD anchor (a run directory: the drive.stdout's
`untilref(...ref_hud...)` match, timed by the next step's PNG; `t:<s>` in that log's own t= clock,
e.g. drive.stdout's step time for ours; or an epoch) and prints the two timelines side by side.

Usage:
  python -m tools_py.parity.music_state_poll --what music --spec            # the PS2X_PEEK spec for ours
  python -m tools_py.parity.music_state_poll --what music --target pcsx2 --port 28011 --hz 5 --seconds 600 --out logs/parity/X/music_state.txt
  python -m tools_py.parity.music_state_poll --what music --target ours --log logs/parity/X/game.log --out logs/parity/X/music_state.txt
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

# -- the cue sequencer
ROUTE_ADDR = 0x49e150            # DAT_0049e150, byte 0 of the word
MGR_PTR_ADDR = 0x49e158          # DAT_0049e158 -> the manager
MGR_WORDS = 16                   # 0x40 bytes
QUEUE_SLOTS = 20                 # the constructor's 0x14 free slots
SLOT_WORDS = 3
# -- the music machine
MUSIC_ADDR = 0x48e080            # DAT_0048e080.. as one 14-word block (see MUSIC_W_*)
MUSIC_WORDS = 14
MUSIC_W_ENTRY, MUSIC_W_PLAYLIST, MUSIC_W_LEVEL, MUSIC_W_LOADED = 0, 2, 4, 6      # 0x48e080/88/90/98
MUSIC_W_ALERT, MUSIC_W_CHANGED, MUSIC_W_REQDEF, MUSIC_W_REQLVL = 8, 10, 12, 13   # 0x48e0a0/a8/b0/b4
MUSIC_OFF_ADDR = 0x3e0080        # DAT_003e0080
TABLES_ADDR = 0x48e010           # DAT_0048e010: 4 x {cap, count, data} playlists, then at +0x40 4 x weights
TABLES_WORDS = 28
LEVEL_NAMES = ("STEALTH", "FIGHT", "MED_FIGHT", "HEAVY_FIGHT")
PLAYLIST_WORDS = 6               # 0x18 bytes
PL_ENTRY_WORDS = 4               # 0x10 bytes
PL_MAX_ENTRIES = 16              # 64 words: PS2X_PEEK's cap
PL_PEEK_ENTRIES = 6              # entries whose def / name / sound entry ours peeks by chain
TABLE_MAX = 8                    # playlists per level peeked
# -- shared
ENTRY_WORDS = 10                 # 0x28 bytes
DEF_WORDS = 16                   # the def's first 0x40 bytes (name pointers at +0x20 / +0x24)
NAME_WORDS = 8                   # 32 bytes of the name string
STORE_BASE_ADDR = 0x48dc48       # the VAGSTORE object 0x48dc30 + 0x18 (second store) and + 0x1c (FUN_0034d470)
CLOCK_ADDR = 0x408f10            # the HUD timer string "MM:SS" (research/19 :217)
GUEST_CLOCK_ADDR = 0x4365c0      # the guest clock, float seconds (KNOWN.md, freeze detection)
RAM_LO, RAM_HI = 0x100000, 0x2000000

VAGSTORE_ZAR = os.path.join("game", "disc", "RUN", "SOUNDS", "VAGSTORE.ZAR")
VAGSTORE_DATA_LBN = 0xee89a      # this disc: file LBN 0xee801 + 0x99 sectors of TOC (iso_lbn + the ZAR header)

COMMON_PEEK = [f"{STORE_BASE_ADDR:#x}:2", f"{CLOCK_ADDR:#x}:2", f"{GUEST_CLOCK_ADDR:#x}:1"]

# What ours must be launched with, per mode: every block the PINE poll reads, chained from the pointers.
OURS_PEEK_SPEC = ",".join([
    f"{ROUTE_ADDR:#x}:1", f"{MGR_PTR_ADDR:#x}:1", f"*{MGR_PTR_ADDR:#x}:{MGR_WORDS}",
    f"*{MGR_PTR_ADDR:#x}+0x34*:{ENTRY_WORDS}",                 # the entry
    f"*{MGR_PTR_ADDR:#x}+0x34*+0x4*:{DEF_WORDS}",              # its def
    f"*{MGR_PTR_ADDR:#x}+0x34*+0x4*+0x20*:{NAME_WORDS}",       # the def's name string
    f"*{MGR_PTR_ADDR:#x}+0x20*:{QUEUE_SLOTS}",                 # the cue queue's index data
    f"*{MGR_PTR_ADDR:#x}+0x30*:{QUEUE_SLOTS * SLOT_WORDS}",    # the slot array (60 words, under the 64 cap)
] + COMMON_PEEK)
OURS_SAMPLER_S = "0.05"

MUSIC_PEEK_SPEC = ",".join(
    [f"{MUSIC_ADDR:#x}:{MUSIC_WORDS}", f"{MUSIC_OFF_ADDR:#x}:1", f"{TABLES_ADDR:#x}:{TABLES_WORDS}"]
    + [f"*{TABLES_ADDR + 0x40 + 8 + lvl * 0xc:#x}:{TABLE_MAX}" for lvl in range(4)]     # the weights per level
    + [f"*{TABLES_ADDR + 8 + lvl * 0xc:#x}:{TABLE_MAX}" for lvl in range(4)]            # the playlist pointers per level
    + [f"*{MUSIC_ADDR:#x}:{ENTRY_WORDS}", f"*{MUSIC_ADDR:#x}+0x4*:{DEF_WORDS}",          # the single stem's entry, def, name
       f"*{MUSIC_ADDR:#x}+0x4*+0x20*:{NAME_WORDS}",
       f"*{MUSIC_ADDR + 8:#x}:{PLAYLIST_WORDS}", f"*{MUSIC_ADDR + 8:#x}+0x8*:{PL_MAX_ENTRIES * PL_ENTRY_WORDS}"]
    + [s for i in range(PL_PEEK_ENTRIES) for s in (
        f"*{MUSIC_ADDR + 8:#x}+0x8*+{i * 0x10:#x}*:9",                                   # entry i's def (to +0x20)
        f"*{MUSIC_ADDR + 8:#x}+0x8*+{i * 0x10:#x}*+0x20*:{NAME_WORDS}",                  # its name
        f"*{MUSIC_ADDR + 8:#x}+0x8*+{i * 0x10 + 4:#x}*:2")]                              # its sound entry (handle, def)
    + COMMON_PEEK)
MUSIC_SAMPLER_S = "0.1"

FIELDS = ("mode", "state", "irq", "en", "cue", "def", "vol", "q", "free", "h34", "h38", "h3c", "ih", "ef")
HEX_FIELDS = ("cue", "def", "vol", "h34", "h38", "h3c", "ih", "ef")
STATE_NAMES = {4: "reset", 3: "idle", 1: "playing", 0: "ext-started", 2: "ext-pending"}

MUSIC_FIELDS = ("off", "lvl", "alert", "chg", "req", "reqdef", "ent", "eh", "pl", "pli", "n", "cur", "done", "stop", "ceh")
MUSIC_HEX_FIELDS = ("reqdef", "ent", "eh", "pl", "ceh")
MUSIC_LEVEL_NAMES = {-1: "idle", 0: "stealth-list", 1: "single", 2: "fight-list", 3: "single-forced"}


def signed8(v):
    return v - 256 if v >= 128 else v


class Sample:
    """One reading of every block: the words as the guest holds them (None = the block was not there)."""

    def __init__(self, route=0, mgr=None, entry=None, sdef=None, name=None, qidx=None, slots=None,
                 store=None, clk=None, gclk=None):
        self.route, self.mgr, self.entry, self.sdef, self.name = route, mgr, entry, sdef, name
        self.qidx, self.slots, self.store, self.clk, self.gclk = qidx, slots, store, clk, gclk


class MusicSample:
    """--what music: the globals block, the OFF byte, the tables, the single stem's entry / def / name, the
    playlist header and entries, per entry (def words, name words, sound-entry words), the weights and
    playlist pointers per level."""

    def __init__(self):
        self.globals = None
        self.off = None
        self.tables = None
        self.entry = self.sdef = self.name = None
        self.pl = None                  # the playlist header words
        self.entries = None             # the entries' words, flat
        self.entry_info = {}            # index -> (def words or None, name words or None, sound entry words or None)
        self.weights = {}               # level -> [floats]
        self.lists = {}                 # level -> [playlist pointers]
        self.store = self.clk = self.gclk = None


def decode(route_word, mgr_words, entry_words=None):
    """The cue sequencer's fields out of the DAT_0049e150 word, the 16 manager words (None = no manager)
    and the entry's words (None = no entry: ih/ef read '-')."""
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


def decode_playlist(pl_words, entries_words=None):
    """The playlist header -> dict(cap, n, data, cur, done, stop) and its entries -> [dict(def, sentry,
    pause, elapsed)] (n entries, as far as the words go)."""
    if pl_words is None or len(pl_words) < PLAYLIST_WORDS:
        return None, []
    h = {"cap": pl_words[0], "n": pl_words[1], "data": pl_words[2], "cur": signed32(pl_words[3]),
         "done": pl_words[5] & 0xff, "stop": (pl_words[5] >> 8) & 0xff}
    ents = []
    if entries_words:
        for i in range(min(h["n"], len(entries_words) // PL_ENTRY_WORDS)):
            w = entries_words[i * PL_ENTRY_WORDS:(i + 1) * PL_ENTRY_WORDS]
            ents.append({"def": w[0], "sentry": w[1], "pause": as_float(w[2]), "elapsed": as_float(w[3])})
    return h, ents


def signed32(v):
    return v - (1 << 32) if v >= (1 << 31) else v


def as_float(w):
    return struct.unpack("<f", struct.pack("<I", w & 0xffffffff))[0]


def decode_music(s):
    """The music machine's fields out of a MusicSample (None = the block was not there)."""
    f = {k: None for k in MUSIC_FIELDS}
    f["off"] = s.off & 0xff if s.off is not None else None
    g = s.globals
    if g is None or len(g) < MUSIC_WORDS:
        return f
    f["lvl"] = signed8(g[MUSIC_W_LEVEL] & 0xff)
    f["alert"] = g[MUSIC_W_ALERT] & 0xff
    f["chg"] = g[MUSIC_W_CHANGED] & 0xff
    f["req"] = signed8(g[MUSIC_W_REQLVL] & 0xff)
    f["reqdef"] = g[MUSIC_W_REQDEF]
    f["ent"] = g[MUSIC_W_ENTRY]
    f["eh"] = s.entry[0] if s.entry else None
    f["pl"] = g[MUSIC_W_PLAYLIST]
    h, ents = decode_playlist(s.pl, s.entries)
    if h:
        f["n"], f["cur"], f["done"], f["stop"] = h["n"], h["cur"], h["done"], h["stop"]
        if 0 <= h["cur"] < len(ents):
            se = s.entry_info.get(h["cur"], (None, None, None))[2]
            f["ceh"] = se[0] if se else (0 if ents[h["cur"]]["sentry"] == 0 else None)
    if f["pl"] and s.lists:
        for lvl, ptrs in s.lists.items():
            if f["pl"] in ptrs:
                f["pli"] = lvl * 16 + ptrs.index(f["pl"])     # level in the high nibble, index in the low
    return f


def playlist_index(pli):
    return None if pli is None else (pli >> 4, pli & 0xf)


def decode_def(def_words, name_words=None):
    """The def's play-path fields: name, format, type, flags, group, bank/id, the name key for the store."""
    if def_words is None or len(def_words) < 9:
        return None
    raw = b"".join(w.to_bytes(4, "little") for w in def_words[:9])
    flags_a, flags_b = raw[0x1c], raw[0x1d]
    fmt = (flags_b & 0x1f) >> 2
    d = {"vol_scale": struct.unpack_from("<f", raw, 4)[0],
         "near": struct.unpack_from("<H", raw, 0xc)[0], "far": struct.unpack_from("<H", raw, 0xe)[0],
         "bank": raw[0x10], "id": struct.unpack_from("<H", raw, 0x12)[0],
         "flags_a": flags_a, "flags_b": flags_b, "type": flags_b >> 5, "fmt": fmt,
         "stream": flags_a & 1, "name_ptr": def_words[8],
         "name2_ptr": def_words[9] if len(def_words) > 9 else 0,
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
    v = as_float(word)
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


def describe_playlist(h, ents, entry_info, store_words=None, toc=None, names=None):
    """`playlist n=5 cur=2 done=0 stop=0 [M51_M01 | rest 12.0s | >M51_M02 ...] cur M51_M02 sector ... handle ...`
    (`>` marks the cursor; a REST entry shows its PAUSETIME and, at the cursor, its elapsed seconds).
    `names` = {def ptr: name} for entries whose def block was not read this sample."""
    if h is None:
        return None
    cells = []
    for i, e in enumerate(ents):
        mark = ">" if i == h["cur"] else ""
        if e["def"] == 0:
            cell = f"rest {e['pause']:.1f}s"
            if i == h["cur"]:
                cell += f" at {e['elapsed']:.1f}"
        else:
            dw, nw, _se = entry_info.get(i, (None, None, None))
            d = decode_def(dw, nw)
            nm = (d["name"] if d and d["name"] else None) or (names or {}).get(e["def"]) or f"def@{e['def']:#x}"
            cell = nm
        cells.append(mark + cell)
    if h["n"] > len(ents):
        cells.append(f"+{h['n'] - len(ents)} more")
    s = f"playlist n={h['n']} cur={h['cur']} done={h['done']} stop={h['stop']} [" + " | ".join(cells) + "]"
    if 0 <= h["cur"] < len(ents) and ents[h["cur"]]["def"]:
        dw, nw, se = entry_info.get(h["cur"], (None, None, None))
        d = describe_def(decode_def(dw, nw), se[0] if se else None, store_words, toc)
        if d:
            s += " cur " + d
    return s


def describe_weights(weights, lists):
    """`weights STEALTH[0.50,0.50] FIGHT[1.00] ...` (the roll's decision table)."""
    parts = []
    for lvl in range(4):
        w = weights.get(lvl)
        if w:
            parts.append(f"{LEVEL_NAMES[lvl]}[" + ",".join(f"{x:.2f}" for x in w) + "]")
    return "weights " + " ".join(parts) if parts else None


# ---- change lines ----------------------------------------------------------------------------------

def fmt_field(k, v, hexf=None):
    hexf = HEX_FIELDS + MUSIC_HEX_FIELDS if hexf is None else hexf
    if v is None:
        return "-"
    if k in hexf:
        return f"{v:#x}"
    return str(v)


def format_fields(f, fields=None):
    fields = FIELDS if fields is None else fields
    return " ".join(f"{k}={fmt_field(k, f.get(k))}" for k in fields)


def diff_fields(prev, cur, fields=None):
    """[(field, old, new)] for the fields that differ (prev None = everything is new)."""
    fields = FIELDS if fields is None else fields
    if prev is None:
        return [(k, None, cur.get(k)) for k in fields]
    return [(k, prev.get(k), cur.get(k)) for k in fields if prev.get(k) != cur.get(k)]


def format_change_line(wall, t, f, changes, vsync=None, clock=None, gclock=None, note=None, fields=None):
    head = f"wall={wall:.3f} t={t:.3f}"
    if vsync is not None:
        head += f" vsync={vsync}"
    if clock is not None:
        head += f" clock={clock}"
    if gclock is not None:
        head += f" gclock={gclock:.2f}"
    what = " ".join(f"{k} {fmt_field(k, o)}->{fmt_field(k, n)}" for k, o, n in changes)
    line = f"{head} {format_fields(f, fields)} | {what}"
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
        fields[k] = None if v == "-" else int(v, 0)
    return {"wall": float(m.group("wall")), "t": float(m.group("t")),
            "vsync": int(m.group("vsync")) if m.group("vsync") else None,
            "clock": m.group("clock"), "gclock": float(m.group("gclock")) if m.group("gclock") else None,
            "fields": fields, "what": m.group("what"), "note": m.group("note")}


NOTE_ON = ("state", "h34", "ih", "q")     # cue: the changes that earn the decoded def / queue on the line
MUSIC_NOTE_ON = ("lvl", "ent", "eh", "pl", "cur", "done", "stop", "ceh", "n")


class Tracker:
    """Feeds samples in, writes the change lines out (the first sample is a change of everything).
    `what` = "cue" (Sample) or "music" (MusicSample)."""

    def __init__(self, out, t0=None, toc=None, what="cue"):
        self.out = out
        self.t0 = t0
        self.prev = None
        self.changes = 0
        self.samples = 0
        self.toc = toc
        self.what = what
        self.fields = MUSIC_FIELDS if what == "music" else FIELDS
        self.names = {}                 # music: def ptr -> name, learnt from any sample that carried the def
        self.last_weights = None

    def feed(self, wall, fields, vsync=None, clock=None, gclock=None, t=None, sample=None):
        if self.t0 is None:
            self.t0 = wall
        self.samples += 1
        if self.what == "music" and sample is not None:
            self._learn(sample)
            self._weights_line(wall, t, sample)
        changes = diff_fields(self.prev, fields, self.fields)
        if not changes:
            return None
        self.prev = dict(fields)
        self.changes += 1
        note = None
        if sample is not None:
            note = self._music_note(fields, sample, changes) if self.what == "music" else self._cue_note(fields, sample, changes)
        line = format_change_line(wall, wall - self.t0 if t is None else t, fields, changes, vsync, clock, gclock, note,
                                  self.fields)
        self.out.write(line + "\n")
        self.out.flush()
        return line

    def _cue_note(self, fields, sample, changes):
        if not any(k in NOTE_ON for k, _o, _n in changes):
            return None
        bits = []
        d = describe_def(decode_def(sample.sdef, sample.name), fields.get("ih"), sample.store, self.toc)
        if d:
            bits.append(d)
        ids = queued_ids(sample.qidx, sample.slots, fields.get("q"))
        if ids:
            bits.append("queued " + ",".join(f"{i:#x}" for i in ids))
        return "; ".join(bits) or None

    def _learn(self, s):
        """Remember def ptr -> name for the playlist entries whose def block this sample carried, so a later
        sample that lost the chain (ours peeks 6 entries by chain; the rest only by pointer) still names them."""
        if not s.entries:
            return
        for i, (dw, nw, _se) in s.entry_info.items():
            d = decode_def(dw, nw)
            if d and d["name"] and len(s.entries) > i * PL_ENTRY_WORDS:
                self.names[s.entries[i * PL_ENTRY_WORDS]] = d["name"]

    def _weights_line(self, wall, t, s):
        w = describe_weights(s.weights, s.lists)
        if w and w != self.last_weights:
            self.last_weights = w
            self.out.write(f"# t={(wall - self.t0) if t is None else t:.3f} {w}\n")

    def _music_note(self, fields, s, changes):
        if not any(k in MUSIC_NOTE_ON for k, _o, _n in changes):
            return None
        bits = []
        if fields.get("lvl") is not None:
            bits.append(f"level {MUSIC_LEVEL_NAMES.get(fields['lvl'], fields['lvl'])}")
        pli = playlist_index(fields.get("pli"))
        if pli:
            bits.append(f"list {LEVEL_NAMES[pli[0]]}#{pli[1]}")
        if fields.get("ent"):
            d = describe_def(decode_def(s.sdef, s.name), fields.get("eh"), s.store, self.toc)
            bits.append("single " + d if d else f"single entry {fields['ent']:#x}")
        if fields.get("pl"):
            h, ents = decode_playlist(s.pl, s.entries)
            p = describe_playlist(h, ents, s.entry_info, s.store, self.toc, self.names)
            if p:
                bits.append(p)
        return "; ".join(bits) or None


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
    """A cue Sample out of a peek row's items. Every block is the item at the address the pointer beside
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


def music_sample_from_peek(items):
    """A MusicSample out of a peek row's items, every block by the pointer beside it."""
    s = MusicSample()
    s.globals = _block(items, MUSIC_ADDR, MUSIC_WORDS)
    s.off = items.get(MUSIC_OFF_ADDR, [None])[0]
    s.tables = _block(items, TABLES_ADDR, TABLES_WORDS)
    if s.tables:
        for lvl in range(4):
            n, data = s.tables[lvl * 3 + 1], s.tables[lvl * 3 + 2]
            ptrs = _block(items, data, 1)
            if ptrs is not None and n:
                s.lists[lvl] = ptrs[:n]
            wn, wdata = s.tables[16 + lvl * 3 + 1], s.tables[16 + lvl * 3 + 2]
            ws = _block(items, wdata, 1)
            if ws is not None and wn:
                s.weights[lvl] = [as_float(w) for w in ws[:wn]]
    if s.globals:
        s.entry = _block(items, s.globals[MUSIC_W_ENTRY], 2)
        if s.entry:
            s.sdef = _block(items, s.entry[1], 9)
            if s.sdef:
                s.name = _block(items, s.sdef[8], 1)
        s.pl = _block(items, s.globals[MUSIC_W_PLAYLIST], PLAYLIST_WORDS)
        if s.pl:
            s.entries = _block(items, s.pl[2], 1)
            if s.entries:
                for i in range(min(s.pl[1], len(s.entries) // PL_ENTRY_WORDS)):
                    dp, sp = s.entries[i * PL_ENTRY_WORDS], s.entries[i * PL_ENTRY_WORDS + 1]
                    dw = _block(items, dp, 9)
                    nw = _block(items, dw[8], 1) if dw else None
                    se = _block(items, sp, 2)
                    if dw or se:
                        s.entry_info[i] = (dw, nw, se)
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
    music = tracker.what == "music"
    for line in lines:
        if line.startswith("[pc-sampler]"):
            m = _SAMPLER_RE.search(line)
            if m:
                t, vsync = float(m.group("t")), int(m.group("vsync"))
            continue
        if not line.startswith("[peek]"):
            continue
        items = parse_peek_row(line)
        wall = now() if now else (base_epoch or 0.0) + (t or 0.0)
        if music:
            if MUSIC_ADDR not in items:
                continue
            s = music_sample_from_peek(items)
            tracker.feed(wall, decode_music(s), vsync=vsync, clock=clock_string(s.clk), gclock=guest_clock(s.gclk),
                         t=t, sample=s)
        else:
            if ROUTE_ADDR not in items and MGR_PTR_ADDR not in items:
                continue
            s = sample_from_peek(items)
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

def _ptr(v):
    return RAM_LO <= v < RAM_HI


class PineSampler:
    """--what cue: reads the blocks through `read32`, the cheap ones every sample and the def / name / store
    once per new pointer (a cache keyed by address), the queue data and slots only while the queue is non-empty."""

    def __init__(self, read32):
        self.read32 = read32
        self.defs = {}          # def addr -> (def words, name words)
        self.store = None

    def words(self, addr, n):
        return [self.read32(addr + 4 * i) for i in range(n)]

    def def_and_name(self, dp, words=DEF_WORDS):
        if dp not in self.defs:
            dw = self.words(dp, words)
            np_ = dw[8]
            nw = self.words(np_, NAME_WORDS) if _ptr(np_) else None
            self.defs[dp] = (dw, nw)
        return self.defs[dp]

    def common(self, s):
        if self.store is None or not self.store[1]:
            self.store = self.words(STORE_BASE_ADDR, 2)
        s.store = self.store
        s.clk = self.words(CLOCK_ADDR, 2)
        s.gclk = self.read32(GUEST_CLOCK_ADDR)

    def sample(self):
        s = Sample(route=self.read32(ROUTE_ADDR))
        ptr = self.read32(MGR_PTR_ADDR)
        if _ptr(ptr):
            s.mgr = self.words(ptr, MGR_WORDS)
            ent = s.mgr[13]
            if _ptr(ent):
                s.entry = self.words(ent, ENTRY_WORDS)
                if _ptr(s.entry[1]):
                    s.sdef, s.name = self.def_and_name(s.entry[1])
            if s.mgr[7] and _ptr(s.mgr[8]) and _ptr(s.mgr[12]):
                s.qidx = self.words(s.mgr[8], min(s.mgr[7], QUEUE_SLOTS))
                s.slots = self.words(s.mgr[12], QUEUE_SLOTS * SLOT_WORDS)
        self.common(s)
        return s


class MusicPineSampler(PineSampler):
    """--what music: the globals every sample; the tables' counts and weights every sample (a few words);
    the playlist header + entries while one is installed; each entry's def / name once per pointer; the
    current entry's sound entry (2 words)."""

    def sample(self):
        s = MusicSample()
        s.globals = self.words(MUSIC_ADDR, MUSIC_WORDS)
        s.off = self.read32(MUSIC_OFF_ADDR)
        s.tables = self.words(TABLES_ADDR, TABLES_WORDS)
        for lvl in range(4):
            n, data = s.tables[lvl * 3 + 1], s.tables[lvl * 3 + 2]
            if n and _ptr(data):
                s.lists[lvl] = self.words(data, min(n, TABLE_MAX))
            wn, wdata = s.tables[16 + lvl * 3 + 1], s.tables[16 + lvl * 3 + 2]
            if wn and _ptr(wdata):
                s.weights[lvl] = [as_float(w) for w in self.words(wdata, min(wn, TABLE_MAX))]
        ent = s.globals[MUSIC_W_ENTRY]
        if _ptr(ent):
            s.entry = self.words(ent, 2)
            if _ptr(s.entry[1]):
                s.sdef, s.name = self.def_and_name(s.entry[1])
        pl = s.globals[MUSIC_W_PLAYLIST]
        if _ptr(pl):
            s.pl = self.words(pl, PLAYLIST_WORDS)
            n, data, cur = min(s.pl[1], PL_MAX_ENTRIES), s.pl[2], signed32(s.pl[3])
            if n and _ptr(data):
                s.entries = self.words(data, n * PL_ENTRY_WORDS)
                for i in range(n):
                    dp, sp = s.entries[i * PL_ENTRY_WORDS], s.entries[i * PL_ENTRY_WORDS + 1]
                    dw, nw = self.def_and_name(dp, 9) if _ptr(dp) else (None, None)
                    se = self.words(sp, 2) if i == cur and _ptr(sp) else None
                    if dw or se:
                        s.entry_info[i] = (dw, nw, se)
        self.common(s)
        return s


def sample_from_pine(read32):
    """One-shot: (route word, manager words or None, clock words, guest clock word) -- the first tool's shape."""
    s = PineSampler(read32).sample()
    return s.route, s.mgr, s.clk, s.gclk


def poll_pcsx2(port, out, seconds, hz, what="cue", toc=None):
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
    tr = Tracker(out, t0=time.time(), toc=toc, what=what)
    cls = MusicPineSampler if what == "music" else PineSampler
    sampler = cls(p.read32)
    period = 1.0 / hz
    while time.time() - t0 < seconds:
        tick = time.time()
        try:
            s = sampler.sample()
            f = decode_music(s) if what == "music" else decode(s.route, s.mgr, s.entry)
            tr.feed(tick, f, clock=clock_string(s.clk), gclock=guest_clock(s.gclk), sample=s)
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
            sampler = cls(p.read32)
        rest = period - (time.time() - tick)
        if rest > 0:
            time.sleep(rest)
    return tr


# ---- compare ---------------------------------------------------------------------------------------

def read_log(path):
    """([change dicts], t0, what) of a poll log: t0 = the epoch of the log's own t=0 (wall - t of the
    first event, so `t:<s>` anchors land in the same clock the events carry), else the header's started=;
    what = the mode from the header ("cue" when absent)."""
    events, started, what = [], None, "cue"
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith("#"):
                m = re.search(r"started=([\d.]+)", line)
                if m:
                    started = float(m.group(1))
                m = re.search(r"\bwhat=(\w+)", line)
                if m:
                    what = m.group(1)
                continue
            ev = parse_change_line(line)
            if ev:
                events.append(ev)
    t0 = events[0]["wall"] - events[0]["t"] if events else started
    return events, t0, what


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


def state_name(v, what="cue"):
    """4 -> 'reset' etc. (cue) / -1 -> 'idle', 2 -> 'fight-list' (music); accepts the text form ('3', '-')."""
    if v is None or v == "-":
        return "-"
    try:
        n = int(str(v), 0)
    except ValueError:
        return str(v)
    return (MUSIC_LEVEL_NAMES if what == "music" else STATE_NAMES).get(n, str(v))


def _parse_what(what):
    return re.findall(r"(\w+) (\S+)->(\S+)", what)


# per mode: the state field, and whether a transition starts a play
MODE_STATE_KEY = {"cue": "state", "music": "lvl"}


def is_play_start(what, old, new):
    if what == "music":
        return old != "-" and int(old) == -1 and int(new) != -1
    return new == "1"


def event_summary(ev, what="cue"):
    """The short form of an event for the side-by-side listing."""
    parts = []
    key = MODE_STATE_KEY[what]
    for k, o, n in _parse_what(ev["what"]):
        parts.append(f"{k} {state_name(o, what)}->{state_name(n, what)}" if k == key else f"{k} {o}->{n}")
    if ev.get("note"):
        # the decoded def / playlist cursor right after the first change, ahead of the raw diffs the column may cut off
        if what == "music":
            m = re.search(r"playlist n=(\d+) cur=(-?\d+)[^\[]*\[([^\]]*)\]", ev["note"])
            tag = None
            if m:
                cells = [c.strip() for c in m.group(3).split("|")]
                at = [c[1:] for c in cells if c.startswith(">")]
                tag = f"{m.group(2)}/{m.group(1)} {at[0]}" if at else f"{m.group(2)}/{m.group(1)}"
            else:
                m = re.search(r"single def (\S+)", ev["note"])
                tag = f"single {m.group(1)}" if m else None
            if tag and parts:
                parts[0] += f" ({tag})"
        else:
            m = re.search(r"def (\S+)(?:.*?(sector \S+))?", ev["note"])
            if m and parts:
                parts[0] += f" ({m.group(1)}{' ' + m.group(2) if m.group(2) else ''})"
    extra = f" [{ev['clock']}]" if ev["clock"] else ""
    if ev["vsync"] is not None:
        extra += f" [f{ev['vsync']}]"
    return ", ".join(parts) + extra


def transitions(events, what="cue"):
    """[(hud_rel, old, new)] of the mode's state field."""
    key = MODE_STATE_KEY[what]
    out = []
    for ev in events:
        for k, o, n in _parse_what(ev["what"]):
            if k == key and o != "-":
                out.append((ev["rel"], o, n))
    return out


def stem_starts(events, what):
    """[(hud_rel, name)] of every stem start: cue mode = state ->1 with a def; music mode = the playlist
    cursor landing on a sound entry, or a single stem starting."""
    out = []
    for ev in events:
        if ev["rel"] < 0 or not ev.get("note"):
            continue
        ws = _parse_what(ev["what"])
        if what == "music":
            if any(k == "cur" for k, _o, _n in ws) or any(k == "ent" and n != "0x0" for k, _o, n in ws):
                m = re.search(r" cur def (\S+)", ev["note"]) or re.search(r"single def (\S+)", ev["note"])
                if m:
                    out.append((ev["rel"], m.group(1)))
                else:
                    m = re.search(r">rest ([\d.]+)s", ev["note"])
                    if m:
                        out.append((ev["rel"], f"rest {m.group(1)}s"))
        elif any(k == "state" and n == "1" for k, _o, n in ws):
            m = re.search(r"def (\S+)", ev["note"])
            out.append((ev["rel"], m.group(1) if m else "?"))
    return out


def compare(log_a, log_b, hud_a, hud_b, out=sys.stdout, width=58, window=None):
    ev_a, t0_a, what_a = read_log(log_a)
    ev_b, t0_b, what_b = read_log(log_b)
    what = what_a if what_a == what_b else "cue"
    ep_a, note_a = hud_anchor(hud_a, t0_a)
    ep_b, note_b = hud_anchor(hud_b, t0_b)
    for evs, ep in ((ev_a, ep_a), (ev_b, ep_b)):
        for ev in evs:
            ev["rel"] = ev["wall"] - ep
    out.write(f"A: {log_a} ({len(ev_a)} changes, {what_a}) HUD anchor {note_a}\n")
    out.write(f"B: {log_b} ({len(ev_b)} changes, {what_b}) HUD anchor {note_b}\n")
    if what_a != what_b:
        out.write("WARNING: the two logs are of different machines (--what); the summaries below use the cue rules\n")
    out.write(f"{'A (s from HUD)':<{width}} | B (s from HUD)\n")
    out.write("-" * (2 * width + 3) + "\n")
    merged = [(ev["rel"], 0, ev) for ev in ev_a] + [(ev["rel"], 1, ev) for ev in ev_b]
    merged.sort(key=lambda x: (x[0], x[1]))
    for rel, side, ev in merged:
        if window is not None and not (window[0] <= rel <= window[1]):
            continue
        cell = f"{rel:+8.2f} {event_summary(ev, what)}"
        if len(cell) > width:
            cell = cell[:width - 1] + "~"
        out.write(f"{cell:<{width}} |\n" if side == 0 else f"{'':<{width}} | {cell}\n")
    ta, tb = transitions(ev_a, what), transitions(ev_b, what)
    key = MODE_STATE_KEY[what]
    out.write(f"\n{key} transitions after the HUD (s from HUD):\n")
    for name, tr in (("A", ta), ("B", tb)):
        post = [x for x in tr if x[0] >= 0]
        out.write(f"  {name}: {len(post)} -- " + ", ".join(f"{o}->{n}@{r:+.1f}" for r, o, n in post[:40])
                  + (" ..." if len(post) > 40 else "") + "\n")
    pa = [x for x in ta if x[0] >= 0 and is_play_start(what, x[1], x[2])]
    pb = [x for x in tb if x[0] >= 0 and is_play_start(what, x[1], x[2])]
    label = "plays (->1)" if what == "cue" else "starts (idle->)"
    out.write(f"  {label} after the HUD: A {len(pa)}, B {len(pb)}; first at A {pa[0][0]:+.1f}s B {pb[0][0]:+.1f}s\n"
              if pa and pb else f"  {label} after the HUD: A {len(pa)}, B {len(pb)}\n")
    for k, (x, y) in enumerate(zip(pa, pb)):
        if k >= 20:
            break
        out.write(f"    {label.split()[0][:-1] if what == 'cue' else 'start'} {k + 1}: A {x[0]:+7.1f}  B {y[0]:+7.1f}  d={y[0] - x[0]:+.1f}s\n")
    if what == "cue":
        def pushes(evs):
            return sum(1 for ev in evs if ev["rel"] >= 0 and
                       any(k == "q" and o != "-" and int(n) > int(o) for k, o, n in _parse_what(ev["what"])))
        out.write(f"  cue-queue pushes seen after the HUD: A {pushes(ev_a)}, B {pushes(ev_b)} "
                  "(a push and its pop inside one sample period are invisible)\n")
    # the stems each side played, by def name, in order: the decision list the two runs are compared on
    for name, evs in (("A", ev_a), ("B", ev_b)):
        played = stem_starts(evs, what)
        if played:
            out.write(f"  {name} played: " + ", ".join(f"{n}@{r:+.1f}" for r, n in played[:40])
                      + (" ..." if len(played) > 40 else "") + "\n")


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


def peek_spec(what):
    return MUSIC_PEEK_SPEC if what == "music" else OURS_PEEK_SPEC


def sampler_period(what):
    return MUSIC_SAMPLER_S if what == "music" else OURS_SAMPLER_S


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
    ap.add_argument("--what", choices=("cue", "music"), default="cue", help="the cue sequencer (default) or the mission music machine")
    ap.add_argument("--spec", action="store_true", help="print the PS2X_PEEK spec ours needs for --what and exit")
    ap.add_argument("--target", choices=("pcsx2", "ours"))
    ap.add_argument("--out")
    ap.add_argument("--seconds", type=float, default=600.0)
    ap.add_argument("--hz", type=float, default=10.0, help="pcsx2 sample rate (5 has run a whole mission)")
    ap.add_argument("--port", type=int, default=0, help="PINE port (default: PINESlot from PCSX2.ini)")
    ap.add_argument("--log", default="latest", help="ours: the run log (`latest` = newest logs/run_*.log)")
    ap.add_argument("--follow", action="store_true", help="ours: tail the log live (wall = now)")
    ap.add_argument("--log-start", type=float, default=None, help="ours, offline: the log's launch epoch")
    a = ap.parse_args(argv)
    if a.spec:
        print(f"PS2X_PC_SAMPLER={sampler_period(a.what)} PS2X_PEEK=\"{peek_spec(a.what)}\"")
        return 0
    if not a.target or not a.out:
        ap.error("--target and --out are required (or --spec)")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    toc = vagstore_toc()
    with open(a.out, "w") as out:
        started = time.time()
        if a.target == "pcsx2":
            port = a.port or pine_port()
            out.write(f"# music_state_poll what={a.what} target=pcsx2 port={port} hz={a.hz} started={started:.3f} "
                      f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started))} toc={'yes' if toc else 'no'}\n")
            tr = poll_pcsx2(port, out, a.seconds, a.hz, a.what, toc)
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
            out.write(f"# music_state_poll what={a.what} target=ours log={path} follow={a.follow} started={started:.3f} "
                      f"log_start={base:.3f} toc={'yes' if toc else 'no'} peek={peek_spec(a.what)}\n")
            tr = Tracker(out, t0=started if a.follow else base, toc=toc, what=a.what)
            if a.follow:
                feed_ours_lines(follow(path, a.seconds), tr, now=time.time)
            else:
                with open(path, "r", errors="replace") as f:
                    feed_ours_lines(f, tr, base_epoch=base)
        out.write(f"# done samples={tr.samples} changes={tr.changes}\n")
    print(f"{tr.samples} samples, {tr.changes} changes -> {a.out}")
    if a.target == "ours" and tr.samples == 0:
        print(f"no rows for --what {a.what}: launch ours with PS2X_PC_SAMPLER={sampler_period(a.what)} PS2X_PEEK=\"{peek_spec(a.what)}\"")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
