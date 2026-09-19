"""Read the runtime's `[MC]` trace lines out of a game run log (Sprint 8 Goal 11).

`PS2X_MC_TRACE=1` makes the libmc stub (ps2xRuntime .../Kernel/Stubs/MemoryCard.cpp) print two
kinds of line on stdout, which run.sh captures into logs/run_<stamp>.log:

    [MC] GetInfo port=0 type=2 free=8000 format=1 result=0
    [MC] Sync cmd=2 result=0

`sceMcSync` reports the command code of the operation that has just completed, so the Sync lines
ARE the op sequence of a save: 0x02 Open, 0x06 Write, 0x03 Close, 0x0B Mkdir ... The names come
from MemoryCard.cpp's `kMcCmd*` constants. Chdir and GetDir additionally print their own
RUNTIME_LOG lines ("[MC] Chdir port=..", "[MC] GetDir port=.."), which are kept verbatim as
`kind="log"` events so a reader sees them in order with the rest.

Nothing here launches or reads anything: it is a parser over text, so the driven-save run's
finding can be re-derived from a stored log.
"""
import re

# MemoryCard.cpp kMcCmd* (2026-09-19). Anything else is reported as "cmd<N>" rather than guessed.
CMD_NAMES = {
    0x01: "GetInfo", 0x02: "Open", 0x03: "Close", 0x04: "Seek", 0x05: "Read", 0x06: "Write",
    0x0A: "Flush", 0x0B: "Mkdir", 0x0C: "Chdir", 0x0D: "GetDir", 0x0E: "SetFileInfo",
    0x0F: "Delete", 0x10: "Format", 0x11: "Unformat", 0x12: "GetEntSpace", 0x13: "Rename",
}
# libmc results the stub returns: 0 succeed, -1 not ready/none, -2 not formatted, -4 no entry.
RESULT_NAMES = {0: "OK", -1: "NOT-READY", -2: "NOT-FORMATTED", -3: "DENIED", -4: "NO-ENTRY",
                -5: "NO-FORMAT", -10: "NO-SPACE"}
# A POSITIVE result is a value, not a code: Open returns the file descriptor, Write/Read the byte
# count, GetDir the number of entries filled in (measured on the 2026-09-19 driven save).

_GETINFO = re.compile(r"\[MC\] GetInfo port=(-?\d+) type=(-?\d+) free=(-?\d+) format=(-?\d+) result=(-?\d+)")
_SYNC = re.compile(r"\[MC\] Sync cmd=(-?\d+) result=(-?\d+)")
_OTHER = re.compile(r"\[MC\] (\w+) (.*)")


def cmd_name(cmd):
    """The libmc command's name, or "cmd<N>" for one this runtime does not define."""
    return CMD_NAMES.get(int(cmd), "cmd%d" % int(cmd))


def result_name(result):
    """The libmc code's name for 0 and the negatives; `ok:<n>` for a positive value."""
    result = int(result)
    if result > 0:
        return "ok:%d" % result
    return RESULT_NAMES.get(result, str(result))


def parse_line(line):
    """One `[MC]` line -> an event dict, or None for anything else.

    kinds: "getinfo" (port/type/free/format/result), "sync" (cmd/name/result), "log" (the
    RUNTIME_LOG Chdir/GetDir lines, kept as `text`)."""
    m = _GETINFO.search(line)
    if m:
        port, type_, free, fmt, result = (int(v) for v in m.groups())
        return {"kind": "getinfo", "port": port, "type": type_, "free": free,
                "format": fmt, "result": result, "name": "GetInfo", "text": line.strip()}
    m = _SYNC.search(line)
    if m:
        cmd, result = (int(v) for v in m.groups())
        return {"kind": "sync", "cmd": cmd, "name": cmd_name(cmd), "result": result,
                "text": line.strip()}
    m = _OTHER.search(line)
    if m:
        return {"kind": "log", "name": m.group(1), "text": line.strip()}
    return None


def parse_log(text):
    """Every `[MC]` event in `text` (a whole run log), in order."""
    out = []
    for line in text.splitlines():
        ev = parse_line(line)
        if ev is not None:
            out.append(ev)
    return out


def op_sequence(events):
    """The Sync/GetInfo ops as (name, result, count) runs, consecutive identical pairs collapsed.

    A boot polls GetInfo hundreds of times; what a save looks like is the SHAPE -- GetInfo,
    Mkdir, Open, Write, Close -- so the repeats are counted, not listed."""
    runs = []
    for ev in events:
        if ev["kind"] == "log":
            continue
        key = (ev["name"], ev["result"])
        if runs and runs[-1][0] == key[0] and runs[-1][1] == key[1]:
            runs[-1][2] += 1
        else:
            runs.append([key[0], key[1], 1])
    return [tuple(r) for r in runs]


def failures(events):
    """Every event the runtime answered with an ERROR, i.e. a NEGATIVE result.

    A non-zero result is not a failure: the driven save of 2026-09-19 shows `Sync cmd=2 result=1`
    (Open returns the file descriptor), `Sync cmd=6 result=964` (Write returns the byte count) and
    `Sync cmd=13 result=13` (GetDir returns the number of entries filled in). Only libmc's negative
    codes are errors -- -4 NO-ENTRY, -5 NO-FORMAT, -2 NOT-FORMATTED. "log" events carry no result."""
    return [ev for ev in events if ev["kind"] != "log" and ev.get("result", 0) < 0]


def format_sequence(events):
    """One line per collapsed run: `Open ok:1 x1`, `GetInfo NO-ENTRY x12`."""
    return "\n".join("%s %s x%d" % (name, result_name(result), count)
                     for name, result, count in op_sequence(events))


def write_ops(events):
    """The ops a save is made of, in order, with no GetInfo/Sync polling noise: the answer to
    "did the game actually write files". Open/Write/Close/Mkdir/Seek/SetFileInfo/Delete/Format."""
    wanted = {"Open", "Write", "Close", "Mkdir", "Seek", "SetFileInfo", "Delete", "Format",
              "Rename", "Flush", "Chdir", "GetDir"}
    return [ev for ev in events if ev["kind"] == "sync" and ev["name"] in wanted]
