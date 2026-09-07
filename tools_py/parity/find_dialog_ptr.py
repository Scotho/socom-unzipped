#!/usr/bin/env python
"""Find a static pointer chain to the current dialog's name in a guest RAM dump taken at a known
dialog. Usage: python tools_py/parity/find_dialog_ptr.py <dump> <dialog-name> [static_lo static_hi]

Prints: every occurrence S of the name string; every word R holding S (a record with a name
pointer); every word in the static range holding R or S. Pick a static address that also holds
the right value in a second dump at a different dialog."""
import re
import struct
import sys

dump = open(sys.argv[1], "rb").read()
name = sys.argv[2].encode()
lo = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x400000
hi = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x4c0000


def words_equal(value, lo=0, hi=len(dump)):
    needle = struct.pack("<I", value)
    out, i = [], lo
    while True:
        i = dump.find(needle, i, hi)
        if i < 0:
            return out
        if i % 4 == 0:
            out.append(i)
        i += 1


for m in re.finditer(re.escape(name) + rb"(\.rdr)?\x00", dump):
    s = m.start()
    print(f"string {name.decode()} at {s:#x} ({dump[s:s+len(name)+4]!r})")
    for r in words_equal(s):
        tag = " STATIC" if lo <= r < hi else ""
        print(f"   word@{r:#x} -> string{tag}")
        for r2 in words_equal(r):
            tag2 = " STATIC" if lo <= r2 < hi else ""
            print(f"      word@{r2:#x} -> {r:#x}{tag2}")
            if r2 < lo or r2 >= hi:
                for r3 in words_equal(r2, lo, hi):
                    print(f"         word@{r3:#x} -> {r2:#x} STATIC")
