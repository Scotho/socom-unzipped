#!/usr/bin/env python
"""Map guest addresses (e.g. the ra= of a PS2X_CALL_TRACE line) to the decomp function that
contains them, using the `// ---- FUN_xxxxxxxx @ xxxxxxxx ----` headers of the decomp file.

Usage: python tools_py/ra2fun.py 0x357028 0x356c9c ...
"""
import bisect
import re
import sys

DECOMP = "game/analysis/socom2_game.elf.decomp.c"


def main():
    starts, names = [], []
    with open(DECOMP, encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.match(r"// ---- (\S+) @ ([0-9a-fA-F]+) ----", line)
            if m:
                starts.append(int(m.group(2), 16))
                names.append(m.group(1))
    order = sorted(range(len(starts)), key=lambda i: starts[i])
    starts = [starts[i] for i in order]
    names = [names[i] for i in order]
    for arg in sys.argv[1:]:
        a = int(arg, 0)
        i = bisect.bisect_right(starts, a) - 1
        if i < 0:
            print(f"{arg}: before the first function")
        else:
            print(f"{arg}: {names[i]} (+{a - starts[i]:#x})")


if __name__ == "__main__":
    main()
