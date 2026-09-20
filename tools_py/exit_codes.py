"""The game's exit codes, read out of the C++ header that defines them.

`third_party/ps2recomp/ps2xShared/include/ps2x/exit_codes.h` is the one place a code or its sentence
is written (Sprint 9 Goal 1). This module parses its X-macro rows so Python never carries a copy."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADER = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xShared", "include", "ps2x", "exit_codes.h")

_ROW = re.compile(r'^\s*X\((\w+),\s*(\d+),\s*"([^"]+)",\s*"([^"]+)"\)', re.M)

CRASH_SIGNALS = (4, 6, 7, 8, 11)   # SIGILL, SIGABRT, SIGBUS, SIGFPE, SIGSEGV -- ExitCodes::classify's list


def table(path=HEADER):
    """[{name, code, slug, sentence}, ...] in the header's order."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return [{"name": m.group(1), "code": int(m.group(2)), "slug": m.group(3), "sentence": m.group(4)}
            for m in _ROW.finditer(text)]


def code(name, path=HEADER):
    for row in table(path):
        if row["name"] == name:
            return row["code"]
    raise KeyError(name)


def sentence(value, path=HEADER):
    for row in table(path):
        if row["code"] == value:
            return row["sentence"]
    return None


def classify(returncode, path=HEADER):
    """subprocess's returncode -> a taxonomy code. POSIX reports a signal death as -n; Windows reports an
    NT status as a large unsigned number. Mirrors ExitCodes::classify."""
    if returncode < 0:
        returncode = 128 - returncode
    if (returncode & 0xF0000000) == 0xC0000000:
        return code("Crashed", path)
    if returncode in tuple(128 + s for s in CRASH_SIGNALS):
        return code("Crashed", path)
    return returncode


def describe(returncode, path=HEADER):
    value = classify(returncode, path)
    found = sentence(value, path)
    if found is not None:
        return found
    return "The game closed with code %d. Press SAVE DIAGNOSTICS to collect the log." % value
