"""Sprint 13 -- the verdict lines of the two control rounds the sprint owes, read off the rounds' own logs.

  udp-shift    C3's F10 proof (scripts/parity/control_round_udp_shift.sh): two instances against the hosted
               server, instance B with PS2X_SOCOM2_UDP_SHIFT=2. Criteria:
                 install      B's log: `[socom2] rt_net config init at 0x.. done on the host (getter global
                              <the revision's getter>), peer UDP port 3660` -- the host performed the routine
                 port         B's log: `[socom2] rt_net base peer UDP port -> 3660` -- the guest called it
                 a-unshifted  A's log carries neither line (A runs with no shift: the install never happens)
                 dme-record   B's DME client record carries :3660 in its internal slot (the slot the fix writes)
                              and, when the server saw it, in the external one: read from the server's DME log
                              when the round directory holds one (server-dme.log, fetched from the box), else from
                              B's own `tcp send` hex (PS2X_SOCOM2_NET_TRACE=1); NO-DATA when neither shows a record
                 a-addresses-b A's `udp peer send` rows go to :3660 and never to :3658 (pre-fix, A sent to its
                              own port: research/18 section 3.3); the client-side reading of B's record (A
                              learns B's port from it), so it carries the RESULT while dme-record is NO-DATA
                 lobby        B reached the game lobby (`B_[lobby] teams: ... -> ok`, or `LOBBY class=ok`) and the
                              drive printed no `RESULT LOBBY-FAIL`
                 r0004        the r0004 boot's install line names getter global 0x654e78 (SKIP with no r0004 log)
               plus INFO lines: the NetIdle `[ret]` count on each side (C3's F11 note) and the drive's RESULT.

  paused-peer  V7's #34 proof (scripts/parity/control_round_paused_peer.sh): the peer paused mid-round, A traced
               with PS2X_PC_SAMPLER=0.25 PS2X_CLOCK_TRACE=1 PS2X_SOCOM2_NET_TRACE=1 PS2X_GS_STATS=1. The pause
               window is the byte range of A's run log between the suspend and the resume (pause.json, written
               by tools_py/parity/peer_pause.py). Criteria:
                 vsync / seq / ee   climbing across the window's [pc-sampler] rows (the executor ran)
                 net_park     at least one row with net_park >= 1 (a guest thread parked in a libnetb recv;
                              absent on an exe from before V7)
                 clock-trace  no hole in the `[clock]` lines through the window (a hole = no guest code ran)
               and the decisive question, answered from three readings -- the HUD round clock (the peeked float
               and the clock string), the `[gs-gl stats] backpressure ... guest_frames=` lines, and A's frame
               captures every 2 s through the pause:
                 all three move            -> #34 closes as fixed
                 they stand, executor ran  -> the executor theory is retracted for the visible symptom
                 a [clock] hole, net_wait=1 -> the executor was blocked (the shape before V7; the --before run)
                 anything else             -> MIXED: no clean outcome, the rows are read by hand
               (a reading with no data -- no [gs-gl stats] line, too few readable captures -- is None, not "stands")
               plus freeze_trace's windows over the pause slice (its `net-park` shape once V7's freeze_trace is in).

  chat         O2's #26 proof (scripts/parity/control_round_chat.sh): A hosts, B joins, A opens the chat box (R1) and
               types a line (online_match_ours --chat; chat.json holds each exchange's byte marks). Criteria:
                 lobby        as udp-shift's
                 keyboard-A   A's log, past the mark: the OSK wrap's `on-screen keyboard open:
                              purpose="_361_EnterChatMessage_MSG"` line (R1 opened the chat box)
                 receive-B    B's log, past its mark: `[socom2] chat receive bound: seen=<n>` (NO-DATA when the only
                              seen line predates the mark: the wrap prints its first call only, so it is unattributable)
               plus keyboard-B / receive-A when the drive typed back (A->B not seen), and R221's talk-slot reading on
               each side: the loaded controller configuration's slot bytes for actions 0x0a and 0x0b (0x10 unbound)
               through guest_addresses' talk_table_ptr, PASS whenever read (a reading, not a proof).

PURE parsers over lines and bytes; `main` does the IO. Every verdict line reads
`VERDICT <round> <criterion> <PASS|FAIL|NO-DATA|SKIP> -- <detail>` and the last line
`RESULT <ROUND> <PASS|FAIL|INCOMPLETE> ...` -- for paused-peer `RESULT PAUSED-PEER <CLOSES|RETRACT|BLOCKED|MIXED|NONE>
<PASS|FAIL|INCOMPLETE> ...`, the DECISIVE outcome first (NONE: no pause happened); exit 0 PASS, 1 FAIL, 2 INCOMPLETE
(the executor criteria, or for --before whether the hole was seen).

Run: python -m tools_py.parity.control_round_readout udp-shift <round dir>
     python -m tools_py.parity.control_round_readout paused-peer <round dir>
     python -m tools_py.parity.control_round_readout chat <round dir>
The round dir's round.txt (KEY=value lines the scripts write) names the logs; flags override it.
"""
import argparse
import json
import os
import re
import struct
import sys
from collections import namedtuple

from tools_py.parity import guest_addresses as ga
from tools_py.parity import verdict_core as vc

PASS, FAIL, NO_DATA, SKIP = "PASS", "FAIL", "NO-DATA", "SKIP"
Verdict = namedtuple("Verdict", "name status detail")

BASE_PORT = 3658            # the game's fixed peer UDP port (socom2_rtnet::kBasePort)
UDP_SHIFT = 2               # instance B's shift (online_login_ours.INSTANCES["B"])
SHIFTED_PORT = BASE_PORT + UDP_SHIFT
# The word the rt_net config init's getter returns, per revision, as the install line prints it. Read out of both
# ELFs by C3 (runtime/socom2_rtnet_config.h); the runtime decodes it from the image, so no table column holds it --
# these are the expected TEXT of a message, not a read of guest memory (bare_address_allow.txt, class message).
GETTER_GLOBAL = {"r0001": 0x656340, "r0004": 0x654e78}

INSTALL_RE = re.compile(r"\[socom2\] rt_net config init at 0x([0-9a-fA-F]+) done on the host "
                        r"\(getter global 0x([0-9a-fA-F]+)\), peer UDP port (\d+)")
PORT_RE = re.compile(r"\[socom2\] rt_net base peer UDP port -> (\d+)")
LEFT_ALONE_RE = re.compile(r"\[socom2\] (?:the routine at 0x[0-9a-fA-F]+ is not the rt_net config init[^\r\n]*"
                           r"|no function at 0x[0-9a-fA-F]+; peer UDP port shift[^\r\n]*"
                           r"|rt_net config object 0x[0-9a-fA-F]+ does not map whole[^\r\n]*)")
PEER_SEND_RE = re.compile(r"udp peer send #(\d+) to (\d+\.\d+\.\d+\.\d+):(\d+)")
TCP_SEND_RE = re.compile(r"tcp send cid \d+ len=\d+ -> -?\d+ \[([0-9a-fA-F ]*)\]")
HEX_DASH_RE = re.compile(r"(?:[0-9A-Fa-f]{2}-){13,}[0-9A-Fa-f]{2}")
LOBBY_TEAMS_B_RE = re.compile(r"B_\[lobby\] teams: seals=\d+ terrorists=\d+ -> (\w[\w-]*)")
LOBBY_OK = "LOBBY class=ok"
LOBBY_FAIL_RE = re.compile(r"RESULT LOBBY-FAIL (\S+)")
RESULT_RE = re.compile(r"RESULT [A-Z][A-Z-]*[^\r\n]*")
NETIDLE_RET_RE = re.compile(r"^\[ret\] NetIdle #\d+", re.M)

SAMPLER_FIELDS_RE = re.compile(r"\b(t|vsync|ee|seq|net_wait|net_park)=(\d+/\d+|-?\d+(?:\.\d+)?)")
CLOCK_RE = re.compile(r"\[clock\] host=([\d.]+)s eeCycle=([\d.]+)s")
GS_BACKPRESSURE_RE = re.compile(r"\[gs-gl stats\] backpressure N=\d+ guest_frames=(\d+)")

CLOCK_HOLE_S = 2.0          # [clock] prints once per host second while guest code runs; > 2 s between two is a hole
CONTEXT_BYTES = 256 * 1024  # read this much of A's log either side of the pause for the bracketing [clock] lines
FRAME_DIFF_LEVEL = 16       # a pixel "changed" when its luma moved by more than this
FRAME_DIFF_PIXELS = 20      # a capture pair "changed" when more pixels than this did (a HUD digit is ~100)


def v(name, status, detail):
    return Verdict(name, status, detail)


def fmt(round_name, verdict):
    return "VERDICT %s %s %s -- %s" % (round_name, verdict.name, verdict.status, verdict.detail)


# ------------------------------------------------------------------------------------------------------------------
# udp-shift (C3)
# ------------------------------------------------------------------------------------------------------------------
def install_verdict(text, revision="r0001", name="install", port=SHIFTED_PORT):
    want = GETTER_GLOBAL[revision]
    hits = INSTALL_RE.findall(text or "")
    if not hits:
        other = LEFT_ALONE_RE.search(text or "")
        why = ("the runtime said: %s" % other.group(0)) if other else "no install line in the log"
        return v(name, FAIL, why)
    at, getter, got_port = hits[0]
    line = "rt_net config init at 0x%s done on the host (getter global 0x%s), peer UDP port %s" % (at, getter, got_port)
    if int(getter, 16) != want or int(got_port) != port:
        return v(name, FAIL, "%s -- wanted getter global %#x and port %d (%s)" % (line, want, port, revision))
    return v(name, PASS, line)


def port_verdict(text, port=SHIFTED_PORT):
    hits = PORT_RE.findall(text or "")
    if not hits:
        return v("port", FAIL, "no `rt_net base peer UDP port ->` line: the guest never called the config init "
                               "through the override")
    if any(int(p) != port for p in hits):
        return v("port", FAIL, "port -> %s (wanted %d)" % (",".join(hits), port))
    return v("port", PASS, "port -> %d (%d line%s)" % (port, len(hits), "" if len(hits) == 1 else "s"))


def unshifted_verdict(text):
    if INSTALL_RE.search(text or "") or PORT_RE.search(text or ""):
        return v("a-unshifted", FAIL, "A carries an install or port line, so A ran with a shift too")
    return v("a-unshifted", PASS, "A has no install and no port line (shift 0)")


def byte_runs(text):
    """Every hex dump in `text` as bytes: the client's `tcp send ... [aa bb ..]` and Horizon's `AA-BB-..` form."""
    runs = []
    for m in TCP_SEND_RE.finditer(text or ""):
        tokens = m.group(1).split()
        if tokens:
            runs.append(bytes(int(t, 16) for t in tokens))
    for m in HEX_DASH_RE.finditer(text or ""):
        runs.append(bytes(int(t, 16) for t in m.group(0).split("-")))
    return runs


def _ip(b4):
    return ".".join(str(x) for x in reversed(b4))     # the record stores the address little-endian (research/18 3.3)


def net_address_pairs(runs, ports=(BASE_PORT, SHIFTED_PORT)):
    """[(internal ip, internal port, external ip, external port)] found in the byte runs: the DME client record's
    two NetAddress slots, `ip(4) port(2, LE) 00 00 ip(4) port(2, LE)`, with the internal port one of the game's own
    (3658 or 3660). The external port is the server's observation and may be a NAT's; it is reported, not required
    to be ours. Duplicates are dropped, order kept."""
    out = []
    for run in runs:
        for i in range(0, len(run) - 13):
            p1 = struct.unpack_from("<H", run, i + 4)[0]
            if p1 not in ports or run[i + 6:i + 8] != b"\0\0":
                continue
            p2 = struct.unpack_from("<H", run, i + 12)[0]
            if p2 == 0:
                continue
            rec = (_ip(run[i:i + 4]), p1, _ip(run[i + 8:i + 12]), p2)
            if rec not in out:
                out.append(rec)
    return out


def dme_record_verdict(dme_text, b_text):
    """B's record from the server's DME log when there is one, else from B's own tcp sends."""
    for source, text in (("the server's DME log", dme_text), ("B's tcp send hex", b_text)):
        if not text:
            continue
        recs = net_address_pairs(byte_runs(text))
        if not recs:
            continue
        shown = "; ".join("%s:%d / %s:%d" % r for r in recs[:4])
        ours = [r for r in recs if r[1] == SHIFTED_PORT]
        if ours:
            both = [r for r in ours if r[3] == SHIFTED_PORT]
            slots = "both slots :%d" % SHIFTED_PORT if both else \
                "internal :%d, external :%d (the server's observation: a NAT's port, not the client's)" % (
                    SHIFTED_PORT, ours[0][3])
            return v("dme-record", PASS, "%s -- %s (%s)" % (source, slots, shown))
        mixed = [r for r in recs if r[1] == BASE_PORT and r[3] == SHIFTED_PORT]
        if mixed:
            return v("dme-record", FAIL, "%s -- internal :%d against external :%d, the pre-fix record (%s)" % (
                source, BASE_PORT, SHIFTED_PORT, shown))
        return v("dme-record", FAIL, "%s -- no record with internal :%d (%s)" % (source, SHIFTED_PORT, shown))
    return v("dme-record", NO_DATA, "no NetAddress pair in %s -- the client's TCP bytes are encrypted or the record "
                                    "lies past the 96 bytes a send dumps; fetch the box's dme.log for the round into "
                                    "<round>/server-dme.log and re-run the readout" % (
                                        "the server's DME log or B's tcp send hex" if dme_text else
                                        "B's tcp send hex (no server-dme.log in the round)"))


def peer_address_verdict(a_text):
    sends = [(ip, int(port)) for _, ip, port in PEER_SEND_RE.findall(a_text or "")]
    if not sends:
        return v("a-addresses-b", NO_DATA, "no `udp peer send` row in A's log (PS2X_SOCOM2_NET_TRACE unset, or no "
                                           "peer traffic)")
    to_b = sum(1 for _, p in sends if p == SHIFTED_PORT)
    to_self = sum(1 for _, p in sends if p == BASE_PORT)
    detail = "%d peer sends: %d to :%d, %d to :%d" % (len(sends), to_b, SHIFTED_PORT, to_self, BASE_PORT)
    if to_b >= 1 and to_self == 0:
        return v("a-addresses-b", PASS, detail)
    return v("a-addresses-b", FAIL, detail)


def lobby_verdict(drive_text):
    t = drive_text or ""
    fail = LOBBY_FAIL_RE.findall(t)
    teams = LOBBY_TEAMS_B_RE.findall(t)
    if fail:
        return v("lobby", FAIL, "RESULT LOBBY-FAIL %s" % fail[-1])
    if LOBBY_OK in t:
        return v("lobby", PASS, "LOBBY class=ok (both in the game)")
    if teams:
        status = PASS if teams[-1] in ("ok", "unread") else FAIL
        return v("lobby", status, "B_[lobby] teams -> %s" % teams[-1])
    return v("lobby", FAIL if t else NO_DATA, "no B lobby line in the drive log" if t else "no drive log")


def udp_shift(a_text, b_text, drive_text, r0004_text=None, dme_text=None):
    verdicts = [install_verdict(b_text), port_verdict(b_text), unshifted_verdict(a_text),
                dme_record_verdict(dme_text, b_text), peer_address_verdict(a_text), lobby_verdict(drive_text)]
    if r0004_text is None:
        verdicts.append(v("r0004", SKIP, "no r0004 boot log in the round"))
    else:
        verdicts.append(install_verdict(r0004_text, "r0004", name="r0004"))
    info = ["INFO udp-shift netidle_ret A=%d B=%d" % (len(NETIDLE_RET_RE.findall(a_text or "")),
                                                     len(NETIDLE_RET_RE.findall(b_text or "")))]
    results = RESULT_RE.findall(drive_text or "")
    if results:
        info.append("INFO udp-shift drive %s" % results[-1].strip())
    # B's record is read two ways: in the record itself (dme-record) and client-side, through where A sends
    # (a-addresses-b: A learns B's port from the record the server relays). Either reading carries the round while
    # the other has NO-DATA; a FAIL in either fails it.
    status = {x.name: x.status for x in verdicts}
    record_read = PASS in (status["dme-record"], status["a-addresses-b"])
    if any(x.status == FAIL for x in verdicts):
        overall = FAIL
    elif any(status[k] == NO_DATA for k in ("install", "port", "lobby")) or not record_read:
        overall = "INCOMPLETE"
    else:
        overall = PASS
    if status["dme-record"] == NO_DATA and status["a-addresses-b"] == PASS:
        info.append("INFO udp-shift B's record read client-side: A addresses B at :%d only" % SHIFTED_PORT)
    return verdicts, info, overall


# ------------------------------------------------------------------------------------------------------------------
# paused-peer (V7, #34)
# ------------------------------------------------------------------------------------------------------------------
def sampler_rows(lines):
    """[{t, vsync, ee, seq, net_wait, net_wait_ms, net_park, net_park_ms}] of the [pc-sampler] lines; a field the
    line does not print is None (net_park before V7)."""
    rows = []
    for line in lines:
        i = line.find("[pc-sampler] ")
        if i < 0:
            continue
        row = dict.fromkeys(("t", "vsync", "ee", "seq", "net_wait", "net_wait_ms", "net_park", "net_park_ms"))
        seg = line[i:]
        j = seg.find(" threads:")
        for key, raw in SAMPLER_FIELDS_RE.findall(seg if j < 0 else seg[:j]):
            if key in ("net_wait", "net_park"):
                flag, _, ms = raw.partition("/")
                row[key], row[key + "_ms"] = int(flag), int(ms or 0)
            elif key in ("t", "ee"):
                row[key] = float(raw)
            else:
                row[key] = int(float(raw))
        rows.append(row)
    return rows


def peek_clock(line):
    """(float round clock, clock string) of one [peek] row -- either None when the row does not carry it. The
    float is the guest_clock item of either revision (verdict_core.ROUND_TIME_ADDRS), the string clock_string."""
    i = line.find("[peek] ")
    if i < 0:
        return None, None
    items = [(int(a, 16), [int(w, 16) for w in vc._WORD.findall(ws)]) for a, ws in vc._ITEM.findall(line[i:])]
    f = None
    for a, words in items:
        for addr in vc.ROUND_TIME_ADDRS:
            if a <= addr < a + 4 * len(words) and (addr - a) % 4 == 0:
                f = vc.f32(words[(addr - a) // 4])
    s = vc.row_clock_string(items)
    return f, (s if isinstance(s, str) else None)


def clock_hosts(lines):
    return [float(m.group(1)) for m in (CLOCK_RE.search(ln) for ln in lines) if m]


def guest_frames(lines):
    return [int(m.group(1)) for m in (GS_BACKPRESSURE_RE.search(ln) for ln in lines) if m]


def _climb(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    if len(vals) < 2:
        return v(key, NO_DATA, "%d sampler row%s carry %s=" % (len(vals), "" if len(vals) == 1 else "s", key))
    status = PASS if vals[-1] > vals[0] else FAIL
    return v(key, status, "%s -> %s over %d rows" % (vals[0], vals[-1], len(vals)))


def net_park_verdict(rows):
    vals = [r["net_park"] for r in rows if r.get("net_park") is not None]
    if not vals:
        return v("net_park", FAIL if rows else NO_DATA,
                 "no net_park= field on the sampler rows (an exe from before V7)" if rows else "no sampler rows")
    ms = [r["net_park_ms"] for r in rows if r.get("net_park_ms") is not None]
    detail = "max %d thread(s) parked on %d of %d rows, parked ms %d -> %d" % (
        max(vals), sum(1 for x in vals if x >= 1), len(vals), ms[0], ms[-1])
    return v("net_park", PASS if max(vals) >= 1 else FAIL, detail)


def clock_trace_verdict(hosts, before=None, after=None):
    """No gap over CLOCK_HOLE_S between consecutive [clock] lines, the last line before the window and the first
    after it included (a hole that straddles the window's edges is still a hole in it)."""
    seq = ([before] if before is not None else []) + list(hosts) + ([after] if after is not None else [])
    if len(seq) < 2:
        return v("clock-trace", NO_DATA, "fewer than two [clock] lines about the window (PS2X_CLOCK_TRACE unset?)")
    gaps = [b - a for a, b in zip(seq, seq[1:])]
    worst = max(gaps)
    detail = "%d [clock] lines in the window, the widest gap %.1f s" % (len(hosts), worst)
    return v("clock-trace", PASS if worst <= CLOCK_HOLE_S else FAIL, detail + ("" if worst <= CLOCK_HOLE_S else
                                                                              " -- a hole: no guest code ran"))


def hud_clock_reading(clocks):
    """'moves' / 'stands' / None from the (float, string) pairs of the window's peek rows."""
    floats = [f for f, _ in clocks if f is not None]
    strings = [s for _, s in clocks if s is not None]
    if not floats and not strings:
        return None, "no round clock on the window's peek rows"
    moved = (len(floats) >= 2 and floats[-1] != floats[0]) or (len(strings) >= 2 and strings[-1] != strings[0])
    detail = "round clock %s -> %s, string %r -> %r" % (
        ("%.3f" % floats[0]) if floats else "-", ("%.3f" % floats[-1]) if floats else "-",
        strings[0] if strings else None, strings[-1] if strings else None)
    return ("moves" if moved else "stands"), detail


def guest_frames_reading(frames):
    if not frames:
        return None, "no [gs-gl stats] backpressure line in the window (fewer than 60 presents, or GS_STATS unset)"
    total = sum(frames)
    return ("moves" if total > 0 else "stands"), "%d [gs-gl stats] lines, guest_frames %d" % (len(frames), total)


def changed_pixels(img_a, img_b, level=FRAME_DIFF_LEVEL):
    """How many pixels' luma differ by more than `level` between two same-size grayscale arrays."""
    import numpy as np
    a = np.asarray(img_a, dtype=np.int16)
    b = np.asarray(img_b, dtype=np.int16)
    if a.shape != b.shape:
        return a.size
    return int((abs(a - b) > level).sum())


def captures_reading(frames, load=None):
    """'moves' / 'stands' / 'partial' / None from the pause-phase captures (pause.json's frames): a pair of
    consecutive captures changed when more than FRAME_DIFF_PIXELS pixels did; moves when at least half the pairs
    changed, stands when none did. A capture that does not load (a torn copy of a file the runtime rewrites every
    ~150 ms) is skipped and counted, never voiding the rest."""
    shots = [f for f in frames if f.get("phase") == "pause"]
    if len(shots) < 2:
        return None, "%d capture(s) in the pause" % len(shots)
    if load is None:
        from PIL import Image

        def load(path):
            with Image.open(path) as im:
                return im.convert("L")
    imgs, kept, skipped = [], [], 0
    for f in shots:
        try:
            if not f.get("path"):
                raise OSError("no capture")
            imgs.append(load(f["path"]))
            kept.append(f)
        except (OSError, ValueError, SyntaxError):
            skipped += 1
    shots = kept
    if len(imgs) < 2:
        return None, "%d readable capture(s) in the pause, %d skipped" % (len(imgs), skipped)
    counts = [changed_pixels(a, b) for a, b in zip(imgs, imgs[1:])]
    changed = sum(1 for c in counts if c > FRAME_DIFF_PIXELS)
    mt = [f.get("mtime") for f in shots if f.get("mtime") is not None]
    fresh = len(set(mt))
    detail = "%d of %d consecutive pairs changed (pixels %s), %d distinct frame-file mtimes, %d skipped" % (
        changed, len(counts), ",".join(str(c) for c in counts), fresh, skipped)
    if changed == 0:
        return "stands", detail
    return ("moves" if 2 * changed >= len(counts) else "partial"), detail


def decisive(hud, gf, caps, executor_ran, parked, hole, net_wait_seen):
    """The #34 question in one line (commit 70d5dae4's two outcomes, and the BEFORE shape)."""
    frames_move = gf in ("moves", None) and caps in ("moves", None) and "moves" in (gf, caps)
    frames_stand = gf in ("stands", None) and caps in ("stands", None) and "stands" in (gf, caps)
    if hud == "moves" and frames_move:
        return ("CLOSES", "the HUD round clock and the guest frames moved through the peer's pause: #34 closes as "
                          "fixed")
    if hole and net_wait_seen:
        return ("BLOCKED", "a [clock] hole with net_wait=1: the executor stood inside waitReadable (the shape before "
                           "V7)")
    if hud == "stands" and frames_stand and executor_ran and parked:
        return ("RETRACT", "the frames and the HUD clock stood while the executor ran (vsync/seq climbing, no [clock] "
                           "hole, net_park>=1): the executor theory is retracted for the visible symptom; the item "
                           "becomes why the peer goes quiet and whether the 10 s cap is faithful")
    return ("MIXED", "no clean outcome -- read the rows above (hud=%s frames=%s captures=%s executor_ran=%s "
                     "parked=%s hole=%s)" % (hud, gf, caps, executor_ran, parked, hole))


def paused_peer(window_lines, before_lines=(), after_lines=(), frames=(), before_mode=False, window_rows=None,
                load=None, freeze_windows=None):
    rows = sampler_rows(window_lines)
    verdicts = [_climb(rows, "vsync"), _climb(rows, "seq"), _climb(rows, "ee"), net_park_verdict(rows)]
    b_hosts, a_hosts = clock_hosts(before_lines), clock_hosts(after_lines)
    ck = clock_trace_verdict(clock_hosts(window_lines), b_hosts[-1] if b_hosts else None,
                             a_hosts[0] if a_hosts else None)
    verdicts.append(ck)
    net_wait_rows = sum(1 for r in rows if r.get("net_wait") == 1)
    wait_ms = [r["net_wait_ms"] for r in rows if r.get("net_wait_ms") is not None]
    info = ["INFO paused-peer net_wait=1 on %d of %d rows, net_wait ms %s" % (
        net_wait_rows, len(rows), ("%d -> %d" % (wait_ms[0], wait_ms[-1])) if wait_ms else "-")]
    hud, hud_detail = hud_clock_reading([peek_clock(ln) for ln in window_lines if "[peek] " in ln])
    gf, gf_detail = guest_frames_reading(guest_frames(window_lines))
    caps, caps_detail = captures_reading(list(frames), load=load)
    info += ["INFO paused-peer hud-clock %s -- %s" % (hud, hud_detail),
             "INFO paused-peer guest-frames %s -- %s" % (gf, gf_detail),
             "INFO paused-peer captures %s -- %s" % (caps, caps_detail)]
    for w in freeze_windows or ():
        info.append("INFO paused-peer freeze_trace %s" % w)
    executor_ran = all(x.status == PASS for x in verdicts if x.name in ("vsync", "seq")) and ck.status == PASS
    parked = verdicts[3].status == PASS
    hole = ck.status == FAIL
    outcome, sentence = decisive(hud, gf, caps, executor_ran, parked, hole, net_wait_rows > 0)
    info.append("DECISIVE paused-peer %s -- %s" % (outcome, sentence))
    if before_mode:
        seen = hole and net_wait_rows > 0
        info.append("EXPECT paused-peer before: a [clock] hole with net_wait=1 -- %s" % ("seen" if seen else "NOT seen"))
        overall = PASS if seen else FAIL
    elif any(x.status == NO_DATA for x in verdicts) or not rows:
        overall = "INCOMPLETE"
    else:
        overall = PASS if all(x.status == PASS for x in verdicts) else FAIL
    return verdicts, info, overall, outcome


# ------------------------------------------------------------------------------------------------------------------
# chat (O2)
# ------------------------------------------------------------------------------------------------------------------
# R221's peek (research/39 section 2.3): FUN_002c64e0 reads the action -> pad-slot table as
# `*(byte *)((action & 0xff) + DAT_004415a8 + 0x12)`, and DAT_004415a8 is a POINTER (it is assigned, compared with 0
# and copied to DAT_004415b0 in the same unit): the talk actions' bytes are at *(ptr) + 0x1c (action 0x0a) and
# *(ptr) + 0x1d (action 0x0b). R221's pair of addresses added the offsets to the global's own address, which reads
# the global's neighbours, not the table. The pointer is guest_addresses' `talk_table_ptr` (both columns).
TALK_TABLE_NAME = "talk_table_ptr"
TALK_TABLE_WORDS = 12                       # *(ptr) + 0x00..0x2f: the table from +0x12, both talk bytes inside
TALK_ACTION_OFFSETS = {0x0a: 0x12 + 0x0a, 0x0b: 0x12 + 0x0b}
SLOT_UNBOUND = 0x10
PEEK_WORD_RE = re.compile(r"([0-9a-f]{8})\(")
CHAT_PURPOSE = "_361_EnterChatMessage_MSG"
OSK_OPEN_RE = re.compile(r'\[socom2\] on-screen keyboard open: purpose="([^"]*)" skb="([^"]*)"')
CHAT_SEEN_RE = re.compile(r"\[socom2\] chat receive bound: seen=(\d+) fixed=(\d+) skipped=(\d+)")


def talk_table_ptr(revision="r0001"):
    return ga.address(TALK_TABLE_NAME, revision)


def chat_peek_items(revision="r0001"):
    """The PS2X_PEEK items the chat round appends to env.sh's spec (scripts/parity/control_round_chat.sh): the
    pointer itself and the words it points at."""
    ptr = talk_table_ptr(revision)
    return "0x%x:1,*0x%x:%d" % (ptr, ptr, TALK_TABLE_WORDS)


def peek_cells(line):
    """{cell key: [words] | 'unresolved ...'} of one `[peek]` row. A resolved cell's key is the address it read, in
    the runtime's lower-case hex without the 0x (`@416054:`); an unresolved one keeps its chain as written."""
    cells = {}
    if "[peek]" not in line:
        return cells
    for part in line.split("[peek]", 1)[1].split(" @")[1:]:
        key, _, rest = part.partition(":")
        rest = rest.strip()
        if rest.startswith("unresolved"):
            cells[key] = rest
        else:
            cells[key] = [int(w, 16) for w in PEEK_WORD_RE.findall(rest)]
    return cells


def _byte(words, off):
    if off // 4 >= len(words):
        return None
    return (words[off // 4] >> (8 * (off % 4))) & 0xff


def talk_slot_reading(lines, ptr_addr):
    """What the peek rows say about the two talk actions' slot bytes: a dict with `rows` (peek rows carrying the
    pointer's cell), `resolved` (rows where the pointer was non-null and the words it points at were read), `values`
    ({(pointer, byte for action 0x0a, byte for action 0x0b): rows}) and `first` / `last` of those tuples."""
    ptr_key = "%x" % ptr_addr
    out = {"rows": 0, "resolved": 0, "values": {}, "first": None, "last": None}
    for line in lines:
        cells = peek_cells(line)
        if ptr_key not in cells:
            continue
        out["rows"] += 1
        ptr_words = cells[ptr_key]
        if not isinstance(ptr_words, list) or not ptr_words or ptr_words[0] == 0:
            continue
        table = cells.get("%x" % ptr_words[0])
        if not isinstance(table, list) or len(table) < TALK_TABLE_WORDS:
            continue
        t = (ptr_words[0], _byte(table, TALK_ACTION_OFFSETS[0x0a]), _byte(table, TALK_ACTION_OFFSETS[0x0b]))
        out["resolved"] += 1
        out["values"][t] = out["values"].get(t, 0) + 1
        out["first"] = out["first"] or t
        out["last"] = t
    return out


def slot_word(b):
    return "unbound (0x10)" if b == SLOT_UNBOUND else "slot 0x%02x" % b


def talk_slot_verdict(reading, tag, ptr_addr):
    """PASS when the table was read at least once: the peek is a reading, not a proof, so either answer passes and
    the detail carries it (0x10 = unbound, research/39 section 2.3)."""
    name = "talk-slot-%s" % tag
    if not reading["rows"]:
        return v(name, NO_DATA, "no [peek] row carries the %s cell (PS2X_PEEK without it, or no sampler)" % TALK_TABLE_NAME)
    if not reading["resolved"]:
        return v(name, NO_DATA, "%d rows, %s null (or its target unread) in every one" % (reading["rows"], TALK_TABLE_NAME))
    ptr, a, b = reading["last"]
    distinct = ", ".join("*=0x%x: 0x0a=0x%02x 0x0b=0x%02x x%d" % (p, x, y, n)
                         for (p, x, y), n in sorted(reading["values"].items()))
    return v(name, PASS, "last row: %s (0x%x) -> 0x%x, action 0x0a %s, action 0x0b %s; %d of %d rows resolved; "
             "distinct: %s" % (TALK_TABLE_NAME, ptr_addr, ptr, slot_word(a), slot_word(b), reading["resolved"],
                               reading["rows"], distinct))


def chat_keyboard_verdict(chat, sender_bytes):
    """The sender's R1 opened the chat keyboard: the OSK wrap's open line with the chat Purpose after the mark (a
    byte offset of the sender's log)."""
    mark = int(chat.get("mark") or 0)
    tail = sender_bytes[mark:].decode("utf-8", errors="replace") if sender_bytes is not None else ""
    opens = [o for o in OSK_OPEN_RE.findall(tail) if o[0] == CHAT_PURPOSE]
    tag = "keyboard-%s" % chat.get("sender", "?")
    if opens:
        return v(tag, PASS, 'purpose="%s" skb="%s" after byte %d; by=%s closed=%s exited=%s'
                 % (opens[0][0], opens[0][1], mark, chat.get("by"), chat.get("closed"), chat.get("exited")))
    if sender_bytes is None:
        return v(tag, NO_DATA, "no sender log")
    return v(tag, FAIL, "no %s open line after byte %d (by=%s: %s)" % (CHAT_PURPOSE, mark, chat.get("by"),
             "the screen saw a keyboard" if chat.get("by") == "screen" else "nothing opened"))


def chat_receive_verdict(chat, receiver_bytes):
    """The receiver's chat receive wrap printed `seen=` after the sender's press (byte offsets of the receiver's log).
    A seen line only BEFORE the mark is NO-DATA: the wrap prints its first call and then only changed ones, so a
    receive that came from someone else first leaves the round's own line unprintable."""
    mark = int(chat.get("receiver_mark") or 0)
    tag = "receive-%s" % chat.get("receiver", "?")
    if receiver_bytes is None:
        return v(tag, NO_DATA, "no receiver log")
    seen = [(m.start(), int(m.group(1))) for m in re.finditer(CHAT_SEEN_RE.pattern.encode(), receiver_bytes)]
    after = [s for s in seen if s[0] >= mark]
    before = [s for s in seen if s[0] < mark]
    if after:
        return v(tag, PASS, "[socom2] chat receive bound: seen=%d at byte %d (mark %d)" % (after[0][1], after[0][0], mark))
    if before:
        return v(tag, NO_DATA, "seen=%d printed at byte %d, BEFORE the sender's press (mark %d): not attributable"
                 % (before[-1][1], before[-1][0], mark))
    return v(tag, FAIL, "no chat receive bound: seen= line in the receiver's log after byte %d" % mark)


def chat_round(chats, logs, drive_text, peek_lines, revision="r0001"):
    """Verdicts of the chat round. `chats` is chat.json's list (A->B first, B->A only when A->B was not seen);
    `logs` is {tag: bytes}; `peek_lines` is {tag: lines}. The RESULT is A->B's: lobby, keyboard-A and receive-B."""
    verdicts, info = [lobby_verdict(drive_text)], []
    if not chats:
        verdicts.append(v("keyboard-A", NO_DATA, "no chat.json (the drive never reached the chat step)"))
    for chat in chats:
        s, r = chat.get("sender"), chat.get("receiver")
        s_bytes, r_bytes = logs.get(s), logs.get(r)
        verdicts.append(chat_keyboard_verdict(chat, s_bytes))
        verdicts.append(chat_receive_verdict(chat, r_bytes))
    ptr_addr = talk_table_ptr(revision)
    for tag in sorted(peek_lines):
        verdicts.append(talk_slot_verdict(talk_slot_reading(peek_lines[tag], ptr_addr), tag, ptr_addr))
    for line in RESULT_RE.findall(drive_text or ""):
        info.append("INFO drive %s" % line.strip())
    need = [x for x in verdicts if x.name in ("lobby", "keyboard-A", "receive-B")]
    if len(need) < 3 or any(x.status == NO_DATA for x in need):
        overall = "INCOMPLETE" if not any(x.status == FAIL for x in need) else FAIL
    else:
        overall = PASS if all(x.status == PASS for x in need) else FAIL
    return verdicts, info, overall


# ------------------------------------------------------------------------------------------------------------------
# IO
# ------------------------------------------------------------------------------------------------------------------
def read_round(round_dir):
    """round.txt's KEY=value lines as a dict (a missing file is an empty dict)."""
    out = {}
    try:
        with open(os.path.join(round_dir, "round.txt"), encoding="utf-8", errors="replace") as f:
            for line in f:
                k, sep, val = line.rstrip("\r\n").partition("=")
                if sep and k.strip():
                    out[k.strip()] = val.strip()
    except OSError:
        pass
    return out


def read_text(path):
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def read_slice(path, start, end, context=CONTEXT_BYTES):
    """(before, window, after) line lists of the byte range [start, end) of `path`, with `context` bytes either
    side (the first and last context line may be torn; only whole [clock] lines are read from them)."""
    with open(path, "rb") as f:
        f.seek(max(0, start - context))
        before = f.read(start - max(0, start - context))
        window = f.read(max(0, end - start))
        after = f.read(context)

    def lines(b):
        return b.decode("utf-8", errors="replace").splitlines()
    return lines(before), lines(window), lines(after)


def _emit(round_name, verdicts, info, overall, extra="", outcome=None):
    for x in verdicts:
        print(fmt(round_name, x))
    for line in info:
        print(line)
    tally = " ".join("%s=%s" % (x.name, x.status) for x in verdicts)
    head = overall if outcome is None else "%s %s" % (outcome, overall)     # paused-peer: the DECISIVE outcome first
    print("RESULT %s %s %s%s" % (round_name.upper(), head, tally, extra), flush=True)
    return {PASS: 0, FAIL: 1}.get(overall, 2)


def read_bytes(path):
    if not path or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def peek_rows(data):
    """The `[peek]` lines of a log's bytes."""
    if data is None:
        return []
    return [ln for ln in data.decode("utf-8", errors="replace").splitlines() if "[peek]" in ln]


def chat_main(a, meta):
    chat_path = a.chat or os.path.join(a.round_dir, "chat.json")
    try:
        with open(chat_path, encoding="utf-8") as f:
            chats = json.load(f)
    except (OSError, ValueError):
        chats = []
    logs = {"A": read_bytes(a.a or meta.get("A_LOG")), "B": read_bytes(a.b or meta.get("B_LOG"))}
    peeks = {tag: peek_rows(data) for tag, data in logs.items() if data is not None}
    verdicts, info, overall = chat_round(chats, logs, read_text(a.drive or meta.get("DRIVE")), peeks,
                                         a.revision or meta.get("REVISION") or "r0001")
    return _emit("chat", verdicts, info, overall)


def main(argv=None):
    ap = argparse.ArgumentParser(description="the Sprint 13 control rounds' verdict lines")
    sub = ap.add_subparsers(dest="round", required=True)
    u = sub.add_parser("udp-shift", help="C3's F10 round")
    u.add_argument("round_dir")
    for flag in ("--a", "--b", "--drive", "--r0004", "--dme"):
        u.add_argument(flag, default=None)
    p = sub.add_parser("paused-peer", help="V7's #34 round")
    p.add_argument("round_dir")
    p.add_argument("--a", default=None)
    p.add_argument("--pause", default=None, help="pause.json (default <round_dir>/pause.json)")
    p.add_argument("--before", action="store_true", help="read as the BEFORE run (a pre-V7 exe)")
    c = sub.add_parser("chat", help="O2's #26 round (and R221's talk-slot peek)")
    c.add_argument("round_dir")
    c.add_argument("--chat", default=None, help="chat.json (default <round_dir>/chat.json)")
    for flag in ("--a", "--b", "--drive"):
        c.add_argument(flag, default=None)
    c.add_argument("--revision", default=None, help="the image's revision (default round.txt's REVISION, else r0001)")
    a = ap.parse_args(argv)
    meta = read_round(a.round_dir)
    if a.round == "chat":
        return chat_main(a, meta)
    if a.round == "udp-shift":
        dme = a.dme or meta.get("DME_LOG") or os.path.join(a.round_dir, "server-dme.log")
        r0004 = a.r0004 or meta.get("R0004_LOG")
        verdicts, info, overall = udp_shift(read_text(a.a or meta.get("A_LOG")), read_text(a.b or meta.get("B_LOG")),
                                            read_text(a.drive or meta.get("DRIVE")),
                                            read_text(r0004) if r0004 else None, read_text(dme))
        return _emit("udp-shift", verdicts, info, overall)
    pause_path = a.pause or os.path.join(a.round_dir, "pause.json")
    try:
        with open(pause_path, encoding="utf-8") as f:
            pause = json.load(f)
    except (OSError, ValueError) as e:
        print("RESULT PAUSED-PEER NONE INCOMPLETE no pause record (%s)" % e, flush=True)
        return 2
    a_log = a.a or pause.get("a_log") or meta.get("A_LOG")
    start, end = pause.get("a_log_bytes_at_suspend"), pause.get("a_log_bytes_at_resume")
    if not a_log or not os.path.isfile(a_log) or start is None or end is None:
        print("RESULT PAUSED-PEER NONE INCOMPLETE the pause never happened: %s" % (pause.get("error") or "no byte range"),
              flush=True)
        return 2
    before, window, after = read_slice(a_log, int(start), int(end))
    windows = []
    try:
        from tools_py.parity import freeze_trace
        windows = [freeze_trace.format_window(w) for w in freeze_trace.windows(window, min_stall_s=2.0)]
    except Exception as e:  # noqa: BLE001 - the verdict does not depend on it
        windows = ["unavailable: %s" % e]
    before_mode = a.before or pause.get("mode") == "before" or meta.get("MODE") == "before"
    verdicts, info, overall, outcome = paused_peer(window, before, after, pause.get("frames") or [], before_mode,
                                          freeze_windows=windows)
    extra = " pause=%.1fs peer=%s mode=%s" % (float(pause.get("t_resume", 0)) - float(pause.get("t_suspend", 0)),
                                              pause.get("peer"), "before" if before_mode else "after")
    return _emit("paused-peer", verdicts, info, overall, extra, outcome=outcome)


if __name__ == "__main__":
    sys.exit(main())
