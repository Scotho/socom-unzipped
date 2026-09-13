"""Regenerate the trimmed online-verdict fixtures from Sprint 4's full run logs (provenance tool).

Not imported by any test. `logs/` is gitignored, so this script is the record of exactly which
lines each fixture holds; see README.md in this folder for the per-fixture table.

Each fixture is a verbatim excerpt of one instance's run log over a time window, with two
reductions, both of which keep every line in the exe's own format:
  * only the line kinds the verdict scorers read are kept: `[peek]`, `[call]`/`[ret]` of the
    traced slots, `[socom2-input] state` (and the continuation line of a state line that another
    stream's write tore in two);
  * a `[peek]` line keeps only the `@416054` camera item and the FIRST 10 WORDS of the item whose
    word 0 is the actor vtable 0x006691a0 (words 7/8/9 are the position); the other items are
    dropped. Word order, addresses and the hex(float) tokens are untouched.

The window is chosen by a crude clock (peek-row index, piecewise linear through `[call] <t>s`
stamps at least 5 s apart, nominal 0.25 s/row outside them). It only has to be generous; the
scorer's own clock is `verdict_core.parse_log`'s.

    python tools_py/tests/fixtures/online/make_fixtures.py
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
OUT = os.path.dirname(os.path.abspath(__file__))

ACTOR_VTABLE_HEX = "006691a0"
KEEP_ACTOR_WORDS = 10
NOMINAL_PERIOD_S = 0.25

# (fixture name, source log, window start s, window end s) -- times on the source log's own
# `[call]` clock (seconds since that process's call-trace start).
FIXTURES = [
    ("frost1_A.txt", "logs/run_A_20260913_004754.log", 399.0, 427.0),
    ("frost1_B.txt", "logs/run_B_20260913_004754.log", 393.0, 421.5),
    ("kill2_A_probe.txt", "logs/run_A_20260912_231341.log", 446.0, 463.5),
    ("kill2_B_probe.txt", "logs/run_B_20260912_231341.log", 440.0, 458.0),
    ("kill2_A_closest.txt", "logs/run_A_20260912_231341.log", 664.0, 694.0),
    ("kill2_B_closest.txt", "logs/run_B_20260912_231341.log", 658.0, 688.0),
    ("kill3_B_probes.txt", "logs/run_B_20260912_232834.log", 440.0, 465.0),
]

# Sprint 5 Task 3 Steps 1-5: launch 1c (Frostfire, the first instrumented launch) around the point
# where A's move path stopped (MoveScale #0..#15 at 379.9-380.5 s, then silent). Trimmed with
# `_trim_peek_state`: the state items the harness reads (alive byte, +0x420, the valves and their
# name bytes, the clocks) instead of the camera record.
STATE_FIXTURES = [
    ("launch1c_A_movestop.txt", "logs/run_A_20260913_073548.log", 379.0, 391.8),
]
# Sprint 5 Task 5: launch 8c (Vigilance), the three windows in which the LIVE move-path watch fired a 10.2-10.9 s
# "stall" that was a guest freeze (research/21 §9.8: the round clock 0x4365c0 stood still while the sampler kept
# writing rows): A after MoveScale #1370 (500.2 -> 514.2 s) and #1860 (547.7 -> 560.4 s), B after #2870
# (620.6 -> 638.7 s). Trimmed with `_trim_peek_freeze` to what the move-path watch and the freeze detector read.
FREEZE_FIXTURES = [
    ("launch8c_A_freeze1.txt", "logs/run_A_20260913_132843.log", 496.0, 518.0),
    ("launch8c_A_freeze2.txt", "logs/run_A_20260913_132843.log", 543.0, 564.0),
    ("launch8c_B_freeze.txt", "logs/run_B_20260913_132843.log", 616.0, 642.0),
]
STATE_CALLS = ("MoveScale", "NetIdle")      # every line of these slots is kept
ANCHOR_EVERY_S = 2.0                         # plus one other [call] line this often, for the clock
KEEP_STATIC = ("4365c0", "45a0c0", "408f10")

_ITEM = re.compile(r"@([0-9a-fA-F]+):((?:\s+[0-9a-fA-F]{8}\([^)]*\))+)")
_TOKEN = re.compile(r"[0-9a-fA-F]{8}\([^)]*\)")
_CALL_T = re.compile(r"^\[call\] ([\d.]+)s ")
_PAD_FULL = re.compile(r"buttons=[0-9a-f]{4} rx=[0-9a-f]{2} ry=[0-9a-f]{2} lx=[0-9a-f]{2} ly=[0-9a-f]{2}\s*$")
_PAD_TAIL = re.compile(r"rx=[0-9a-f]{2} ry=[0-9a-f]{2} lx=[0-9a-f]{2} ly=[0-9a-f]{2}\s*$")


def _clock(lines):
    """peek-row index for every line, and a function index -> seconds: piecewise linear through
    `[call]` stamps at least 5 s apart, nominal 0.25 s/row outside them."""
    idx, anchors, pi = [], [], 0
    for line in lines:
        if line.startswith("[peek]"):
            idx.append(pi)
            pi += 1
            continue
        idx.append(pi - 0.5)
        m = _CALL_T.match(line)
        if m:
            t = float(m.group(1))
            if not anchors or t - anchors[-1][1] >= 5.0:
                anchors.append((pi - 0.5, t))

    def clock(i):
        if not anchors:
            return i * NOMINAL_PERIOD_S
        if i <= anchors[0][0]:
            return anchors[0][1] - (anchors[0][0] - i) * NOMINAL_PERIOD_S
        if i >= anchors[-1][0]:
            return anchors[-1][1] + (i - anchors[-1][0]) * NOMINAL_PERIOD_S
        for (i0, t0), (i1, t1) in zip(anchors, anchors[1:]):
            if i0 <= i <= i1:
                return t0 + (t1 - t0) * (i - i0) / (i1 - i0)
        return anchors[-1][1]
    return idx, clock


def _trim_peek(line):
    parts = ["[peek]"]
    for addr, words in _ITEM.findall(line):
        toks = _TOKEN.findall(words)
        if addr.lower() == "416054":
            parts.append(f"@{addr}: " + " ".join(toks))
        elif toks and toks[0].lower().startswith(ACTOR_VTABLE_HEX):
            parts.append(f"@{addr}: " + " ".join(toks[:KEEP_ACTOR_WORDS]))
    return " ".join(parts)


def _trim_peek_state(line):
    """The actor block's first 10 words, actor+0x400 (12 words, +0x420 is word 8), the first word
    of actor+0xF78 (+0xF7A is its byte 2), every 2-word (valve value) and 3-word (valve name bytes)
    item, and the static clocks. Items are chosen by address and size, never by index."""
    items = [(a, _TOKEN.findall(w)) for a, w in _ITEM.findall(line)]
    actor = next((int(a, 16) for a, t in items if t and t[0].lower().startswith(ACTOR_VTABLE_HEX)), None)
    parts = ["[peek]"]
    for addr, toks in items:
        a = int(addr, 16)
        if actor is not None and a == actor:
            parts.append(f"@{addr}: " + " ".join(toks[:KEEP_ACTOR_WORDS]))
        elif actor is not None and a == actor + 0x400:
            parts.append(f"@{addr}: " + " ".join(toks))
        elif actor is not None and a == actor + 0xF78:
            parts.append(f"@{addr}: " + " ".join(toks[:1]))
        elif len(toks) in (2, 3) or addr.lower() in KEEP_STATIC:
            parts.append(f"@{addr}: " + " ".join(toks))
    return " ".join(parts)


def _trim_peek_freeze(line):
    """The actor block's first 10 words, the first word of actor+0xF78, the round clock 0x4365c0, and
    mp_round_count's value item (2 words) and name-bytes item (3 words, spelling the name) -- nothing else."""
    items = [(a, _TOKEN.findall(w)) for a, w in _ITEM.findall(line)]
    actor = next((int(a, 16) for a, t in items if t and t[0].lower().startswith(ACTOR_VTABLE_HEX)), None)
    want_name = b"mp_round_count"[:12]                 # the name item holds the first 12 bytes
    name_addrs = set()
    for addr, toks in items:
        if len(toks) == 3:
            raw = b"".join(int(t[:8], 16).to_bytes(4, "little") for t in toks)
            if raw.startswith(want_name):
                name_addrs.add(int(addr, 16))
    parts = ["[peek]"]
    for addr, toks in items:
        a = int(addr, 16)
        if actor is not None and a == actor:
            parts.append(f"@{addr}: " + " ".join(toks[:KEEP_ACTOR_WORDS]))
        elif actor is not None and a == actor + 0xF78:
            parts.append(f"@{addr}: " + " ".join(toks[:1]))
        elif addr.lower() == "4365c0" or a in name_addrs:
            parts.append(f"@{addr}: " + " ".join(toks))
        elif len(toks) == 2 and int(toks[0][:8], 16) in name_addrs:
            parts.append(f"@{addr}: " + " ".join(toks))
    return " ".join(parts)


def make_state(name, src, t0, t1, trim=None):
    with open(os.path.join(ROOT, src), "r", errors="replace") as f:
        lines = f.read().split("\n")
    idx, clock = _clock(lines)
    out, last_anchor, keep_ret = [], None, set()
    for i, line in enumerate(lines):
        if not (t0 <= clock(idx[i]) <= t1):
            continue
        if line.startswith("[peek]"):
            out.append((trim or _trim_peek_state)(line))
        elif line.startswith("[call]"):
            m = re.match(r"^\[call\] ([\d.]+)s (\S+) #(\d+)", line)
            if not m:
                continue
            t, slot = float(m.group(1)), m.group(2)
            if slot in STATE_CALLS:
                out.append(line)
                keep_ret.add((slot, m.group(3)))
            elif last_anchor is None or t - last_anchor >= ANCHOR_EVERY_S:
                out.append(line)
                last_anchor = t
        elif line.startswith("[ret]"):
            m = re.match(r"^\[ret\] (\S+) #(\d+)", line)
            if m and (m.group(1), m.group(2)) in keep_ret:
                out.append(line)
    with open(os.path.join(OUT, name), "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    return len(out), os.path.getsize(os.path.join(OUT, name))


def make(name, src, t0, t1):
    with open(os.path.join(ROOT, src), "r", errors="replace") as f:
        lines = f.read().split("\n")
    idx, clock = _clock(lines)
    out, torn = [], False
    for i, line in enumerate(lines):
        inside = t0 <= clock(idx[i]) <= t1
        if line.startswith("[socom2-input] state"):
            # a state line another stream's write tore in two keeps its head verbatim; its tail is the
            # next line, kept below if it is the rx=.. ry=.. lx=.. ly=.. remainder
            torn = not _PAD_FULL.search(line)
            if inside:
                out.append(line)
            continue
        if torn:
            torn = False
            if _PAD_TAIL.search(line):
                if inside:
                    out.append(line)
                continue
        if not inside:
            continue
        if line.startswith("[peek]"):
            out.append(_trim_peek(line))
        elif line.startswith("[call]") or line.startswith("[ret]"):
            out.append(line)
    with open(os.path.join(OUT, name), "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    return len(out), os.path.getsize(os.path.join(OUT, name))


if __name__ == "__main__":
    for spec in FIXTURES:
        n, size = make(*spec)
        print(f"{spec[0]:<22} {n:5d} lines {size:7d} bytes  <- {spec[1]} [{spec[2]}, {spec[3]}] s")
    for spec in STATE_FIXTURES:
        n, size = make_state(*spec)
        print(f"{spec[0]:<22} {n:5d} lines {size:7d} bytes  <- {spec[1]} [{spec[2]}, {spec[3]}] s")
    for spec in FREEZE_FIXTURES:
        n, size = make_state(*spec, trim=_trim_peek_freeze)
        print(f"{spec[0]:<22} {n:5d} lines {size:7d} bytes  <- {spec[1]} [{spec[2]}, {spec[3]}] s")
