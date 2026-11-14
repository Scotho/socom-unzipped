"""Read a PS2X_COVERAGE dump: which recompiled functions a run called (Sprint 19 task B1).

The runtime writes one bit per dense function-table slot that PS2Runtime::lookupFunction handed out
(runtime/coverage_bitmap.h). This maps the slots back to functions: a slot on a function's first word is that
function's entry; a slot inside a function is a resume pc (a scheduler checkpoint re-entering the generated body)
and is counted for the function that holds it. Functions come from the Ghidra list (recomp/socom2_ghidra.csv:
Name,Start,End,Size) with the readable names of recomp/socom2_names.csv laid over them.

Blind spot, printed with every report: a direct tail jump (`j`) to a known function is emitted as a C++ call and
bypasses the table, so a function reached only that way reads as not hit (an undercount, never an overcount).

Run: python -m tools_py.coverage_bitmap <dump> [--functions recomp/socom2_ghidra.csv]
     [--names recomp/socom2_names.csv] [--csv <out>] [--all]
--csv writes the hit functions, smallest first (address, name, size, hit, resume_hits); --all writes every function.
"""
import argparse
import bisect
import csv
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAGIC = b"PS2XCOV1"
HEADER = len(MAGIC) + 8

TAIL_CALL_CAVEAT = ("caveat: a direct tail jump (j) to a known function is emitted as a C++ call and bypasses the "
                    "function table, so a function reached only by tail jumps reads as not hit (an undercount)")


class Coverage:
    def __init__(self, base, slot_count, bits):
        self.base = base
        self.slot_count = slot_count
        self.bits = bits

    def slot_hit(self, slot):
        return 0 <= slot < self.slot_count and bool(self.bits[slot >> 3] & (1 << (slot & 7)))

    def hit_addresses(self):
        out = []
        for i, byte in enumerate(self.bits):
            for b in range(8):
                if byte & (1 << b) and i * 8 + b < self.slot_count:
                    out.append(self.base + (i * 8 + b) * 4)
        return out


def read_dump(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < HEADER or data[:len(MAGIC)] != MAGIC:
        raise ValueError("%s: not a PS2X_COVERAGE dump (no %r header)" % (path, MAGIC.decode()))
    base, slot_count = struct.unpack_from("<II", data, len(MAGIC))
    bits = data[HEADER:]
    if len(bits) != (slot_count + 7) // 8:
        raise ValueError("%s: %d bitmap bytes for %d slots (expected %d)"
                         % (path, len(bits), slot_count, (slot_count + 7) // 8))
    return Coverage(base, slot_count, bits)


def load_functions(functions_csv, names_csv=None):
    """[(start, end, name)] sorted by start; a names_csv row (Address,Name,...) replaces the Ghidra name."""
    names = {}
    if names_csv and os.path.exists(names_csv):
        with open(names_csv, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    names[int(row["Address"], 16)] = row["Name"]
                except (KeyError, ValueError):
                    continue
    funcs = []
    with open(functions_csv, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            start = int(row["Start"], 16)
            end = int(row["End"], 16)
            funcs.append((start, end, names.get(start, row["Name"])))
    funcs.sort()
    return funcs


def function_rows(cov, funcs):
    """One row per function: address, name, size, hit (its entry slot), resume_hits (slots inside it)."""
    rows = []
    for start, end, name in funcs:
        first = (start - cov.base) // 4
        last = (end - cov.base) // 4
        rows.append({
            "address": start,
            "name": name,
            "size": end - start,
            "hit": 1 if cov.slot_hit(first) else 0,
            "resume_hits": sum(1 for s in range(first + 1, last) if cov.slot_hit(s)),
        })
    return rows


def hit_by_size(rows):
    return sorted((r for r in rows if r["hit"]), key=lambda r: (r["size"], r["address"]))


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["address", "name", "size", "hit", "resume_hits"])
        for r in rows:
            w.writerow(["0x%08x" % r["address"], r["name"], r["size"], r["hit"], r["resume_hits"]])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dump")
    ap.add_argument("--functions", default=os.path.join(ROOT, "recomp", "socom2_ghidra.csv"))
    ap.add_argument("--names", default=os.path.join(ROOT, "recomp", "socom2_names.csv"))
    ap.add_argument("--csv", help="write the hit functions, smallest first, to this file")
    ap.add_argument("--all", action="store_true", help="with --csv: every function, hit or not, by address")
    args = ap.parse_args(argv)

    cov = read_dump(args.dump)
    rows = function_rows(cov, load_functions(args.functions, args.names))
    hot = hit_by_size(rows)
    starts = [r["address"] for r in rows]
    stray = []
    for a in cov.hit_addresses():
        i = bisect.bisect_right(starts, a) - 1
        if i < 0 or a >= rows[i]["address"] + rows[i]["size"]:
            stray.append(a)
    print("coverage: %s, table 0x%08x + %d slots, %d slots hit" % (args.dump, cov.base, cov.slot_count,
                                                                  len(cov.hit_addresses())))
    print("coverage: hit %d of %d functions (%d with resume pcs hit); %d hit slots outside any listed function"
          % (len(hot), len(rows), sum(1 for r in hot if r["resume_hits"]), len(stray)))
    print(TAIL_CALL_CAVEAT)
    if args.csv:
        write_csv(sorted(rows, key=lambda r: r["address"]) if args.all else hot, args.csv)
        print("coverage: wrote %s" % args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
