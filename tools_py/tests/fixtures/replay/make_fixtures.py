"""Regenerate the trimmed verdict_replay fixtures from Sprint 5's full run logs (provenance tool).

Not imported by any test. `logs/` is gitignored, so this script is the record of exactly which
lines each fixture holds; README.md in this folder has the per-fixture table.

Each fixture is a verbatim excerpt of one instance's run log, reduced three ways, every kept line
still in the exe's own format:
  * the window is cut on the source log's own `[call] <t>s` clock and starts and ends on a kept
    MoveScale `[call]` line, so every kept `[peek]` row lies between two clock anchors;
  * MoveScale `[call]` lines are kept only >= 5 s after the previous kept one (the parsers' anchor
    spacing); other slots are dropped; `[socom2-input] state` lines inside the window are all kept;
  * one `[peek]` row in every STRIDE is kept, and of it only the items verdict_replay reads: the
    first 10 words of the actor block (word 0 == vtable 0x006691a0, words 7/8/9 = x/y/z), the item
    at actor+0x1044 (health), the first word of actor+0xF78 (+0xF7A is its byte 2), the value and
    name-bytes items of the five round valves, and the statics 0x4365c0 (guest clock) and 0x408f10
    (clock string). Tokens, addresses and word order are untouched.

    python tools_py/tests/fixtures/replay/make_fixtures.py
"""
import os
import re
import struct

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
OUT = os.path.dirname(os.path.abspath(__file__))

ACTOR_VTABLE_HEX = "006691a0"
KEEP_ACTOR_WORDS = 10
ANCHOR_SPACING_S = 5.0
VALVE_NAMES = ("mp_round_count", "player_team", "aiteam_00", "aiteam_08", "total_mp_kills")
KEEP_STATIC = ("4365c0", "408f10")

# (fixture, source log, window start s, window end s, stride) -- source-log clock.
FIXTURES = [
    # launch 8c (Vigilance clock round end, research/21 §9): A's clock string 00:00 at 778.0,
    # mp_round_count 0 -> 1 at A 783.3 / B 777.5; B + 5.80 s = A.
    ("l8c_A.txt", "logs/run_A_20260913_132843.log", 764.0, 800.0, 8),
    ("l8c_B.txt", "logs/run_B_20260913_132843.log", 758.0, 795.0, 8),
    # launch 3c (Frostfire, control, no contact, research/21 §8): the whole round at one row per
    # ~20 s; B + 6.00 s = A.
    ("l3c_A.txt", "logs/run_A_20260913_115809.log", 393.0, 696.0, 80),
    ("l3c_B.txt", "logs/run_B_20260913_115809.log", 387.0, 690.0, 80),
]

_ITEM = re.compile(r"@([0-9a-fA-F]+):((?:\s+[0-9a-fA-F]{8}\([^)]*\))+)")
_TOKEN = re.compile(r"[0-9a-fA-F]{8}\([^)]*\)")
_CALL = re.compile(r"^\[call\] ([\d.]+)s (\S+) #")


def _spells(toks, name):
    raw = b"".join(struct.pack("<I", int(t[:8], 16)) for t in toks[:3])
    want = (name.encode() + b"\0")[:12]
    return raw[:len(want)] == want


def _trim_peek(line):
    items = [(a, _TOKEN.findall(w)) for a, w in _ITEM.findall(line)]
    actor = next((int(a, 16) for a, t in items if t and t[0].lower().startswith(ACTOR_VTABLE_HEX)), None)
    names = {int(a, 16) for a, t in items if len(t) == 3 and any(_spells(t, n) for n in VALVE_NAMES)}
    parts = ["[peek]"]
    for addr, toks in items:
        a = int(addr, 16)
        if actor is not None and a == actor:
            parts.append(f"@{addr}: " + " ".join(toks[:KEEP_ACTOR_WORDS]))
        elif actor is not None and a == actor + 0x1044:
            parts.append(f"@{addr}: " + " ".join(toks[:1]))
        elif actor is not None and a == actor + 0xF78:
            parts.append(f"@{addr}: " + " ".join(toks[:1]))
        elif a in names or (len(toks) == 2 and int(toks[0][:8], 16) in names):
            parts.append(f"@{addr}: " + " ".join(toks))
        elif addr.lower() in KEEP_STATIC:
            parts.append(f"@{addr}: " + " ".join(toks))
    return " ".join(parts)


def make(name, src, t0, t1, stride):
    with open(os.path.join(ROOT, src), "r", errors="replace") as f:
        lines = f.read().split("\n")
    # the window: from the first MoveScale call at >= t0 to the last at <= t1
    calls = [(i, float(m.group(1))) for i, l in enumerate(lines)
             for m in [_CALL.match(l)] if m and m.group(2) == "MoveScale"]
    inside = [(i, t) for i, t in calls if t0 <= t <= t1]
    first, last = inside[0][0], inside[-1][0]
    out, last_anchor, peek_i = [], None, 0
    kept_calls = set()
    for i, t in inside:
        if last_anchor is None or t - last_anchor >= ANCHOR_SPACING_S:
            kept_calls.add(i)
            last_anchor = t
    kept_calls.add(last)
    for i in range(first, last + 1):
        line = lines[i].rstrip("\r")
        if line.startswith("[peek]"):
            if peek_i % stride == 0:
                out.append(_trim_peek(line))
            peek_i += 1
        elif i in kept_calls:
            out.append(line)
        elif line.startswith("[socom2-input] state"):
            out.append(line)
    with open(os.path.join(OUT, name), "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    return len(out), os.path.getsize(os.path.join(OUT, name))


if __name__ == "__main__":
    for spec in FIXTURES:
        n, size = make(*spec)
        print(f"{spec[0]:<12} {n:5d} lines {size:7d} bytes  <- {spec[1]} [{spec[2]}, {spec[3]}] s stride {spec[4]}")
