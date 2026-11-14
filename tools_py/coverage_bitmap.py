"""Read a PS2X_COVERAGE dump: which recompiled functions a run called (Sprint 19 task B1).

The runtime writes one bit per dense function-table slot that PS2Runtime::lookupFunction handed out
(runtime/coverage_bitmap.h). This maps the slots back to functions: a slot on a function's first word is that
function's entry; a slot inside a function is a resume pc (a scheduler checkpoint re-entering the generated body)
and is counted for the function that holds it. A function is REACHED when its entry slot or any slot inside it is
set: one entered by a direct tail jump (no entry bit) and later resumed inside still counts. Functions come from the
Ghidra list (recomp/socom2_ghidra.csv: Name,Start,End,Size) with the readable names of recomp/socom2_names.csv laid
over them; an r0004 dump is read with recomp/socom2_ghidra_r0004.csv and recomp/socom2_names_r0004.csv.

What a bit means, printed with every report (TAIL_CALL_CAVEAT): a guest call reached the address through the
function table. An overridden or stubbed address counts although its generated body did not run, and a function
reached only by a direct tail jump (`j`, emitted as a C++ call that bypasses the table) reads as not reached.

The dump does not name its game revision. When the function list has starts outside the dump's table (base ..
base + slots * 4) the reader warns on stderr -- the usual cause is a dump read against the other revision's list.

Run: python -m tools_py.coverage_bitmap <dump> [--functions recomp/socom2_ghidra.csv]
     [--names recomp/socom2_names.csv] [--csv <out>] [--all]
--csv writes the reached functions, smallest first (address, name, size, reached, entry_hit, resume_hits); --all
writes every function.
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

TAIL_CALL_CAVEAT = ("caveat: a set bit means a guest call reached this address through the function table; an "
                    "overridden or stubbed address counts although its generated body did not run; a function "
                    "reached only by a direct tail jump reads as not reached")
R0004_HINT = ("an r0004 dump: --functions recomp/socom2_ghidra_r0004.csv --names recomp/socom2_names_r0004.csv")


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
    """One row per function: address, name, size, entry_hit (its entry slot), resume_hits (slots inside it) and
    reached (either)."""
    rows = []
    for start, end, name in funcs:
        first = (start - cov.base) // 4
        last = (end - cov.base) // 4
        entry_hit = 1 if cov.slot_hit(first) else 0
        resume_hits = sum(1 for s in range(first + 1, last) if cov.slot_hit(s))
        rows.append({
            "address": start,
            "name": name,
            "size": end - start,
            "reached": 1 if entry_hit or resume_hits else 0,
            "entry_hit": entry_hit,
            "resume_hits": resume_hits,
        })
    return rows


def hit_by_size(rows):
    """The reached functions, smallest first."""
    return sorted((r for r in rows if r["reached"]), key=lambda r: (r["size"], r["address"]))


def range_warning(cov, funcs):
    """A sentence when some listed functions start outside the dump's table, else None. The table ends at the last
    table entry's start + 4, so only starts are compared: a last function's body may run past it."""
    table_end = cov.base + cov.slot_count * 4
    outside = [start for start, _, _ in funcs if not cov.base <= start < table_end]
    if not outside:
        return None
    return ("coverage: warning: %d of %d listed functions start outside the dump's table 0x%08x..0x%08x "
            "(first 0x%08x); the dump may come from another game revision than the function list (%s)"
            % (len(outside), len(funcs), cov.base, table_end, min(outside), R0004_HINT))


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["address", "name", "size", "reached", "entry_hit", "resume_hits"])
        for r in rows:
            w.writerow(["0x%08x" % r["address"], r["name"], r["size"], r["reached"], r["entry_hit"],
                        r["resume_hits"]])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], epilog="For " + R0004_HINT + ".")
    ap.add_argument("dump")
    ap.add_argument("--functions", default=os.path.join(ROOT, "recomp", "socom2_ghidra.csv"),
                    help="the Ghidra function list (default recomp/socom2_ghidra.csv, r0001)")
    ap.add_argument("--names", default=os.path.join(ROOT, "recomp", "socom2_names.csv"),
                    help="the readable names (default recomp/socom2_names.csv, r0001)")
    ap.add_argument("--csv", help="write the reached functions, smallest first, to this file")
    ap.add_argument("--all", action="store_true", help="with --csv: every function, reached or not, by address")
    args = ap.parse_args(argv)

    cov = read_dump(args.dump)
    funcs = load_functions(args.functions, args.names)
    warning = range_warning(cov, funcs)
    if warning:
        print(warning, file=sys.stderr)
    rows = function_rows(cov, funcs)
    hot = hit_by_size(rows)
    starts = [r["address"] for r in rows]
    stray = []
    for a in cov.hit_addresses():
        i = bisect.bisect_right(starts, a) - 1
        if i < 0 or a >= rows[i]["address"] + rows[i]["size"]:
            stray.append(a)
    print("coverage: %s, table 0x%08x + %d slots, %d slots hit" % (args.dump, cov.base, cov.slot_count,
                                                                  len(cov.hit_addresses())))
    print("coverage: reached %d of %d functions (%d by entry, %d with resume pcs hit); "
          "%d hit slots outside any listed function"
          % (len(hot), len(rows), sum(1 for r in hot if r["entry_hit"]), sum(1 for r in hot if r["resume_hits"]),
             len(stray)))
    print(TAIL_CALL_CAVEAT)
    if args.csv:
        write_csv(sorted(rows, key=lambda r: r["address"]) if args.all else hot, args.csv)
        print("coverage: wrote %s" % args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
