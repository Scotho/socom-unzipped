"""Sprint 11 Task 7 (U3): name our anonymous functions from the SOCOM 1 demo's debug symbols.

Our SOCOM II image is anonymous -- `recomp/socom2_ghidra.csv` is 14,879 rows of `FUN_00xxxxxx`. The
SOCOM 1 demo (`SCUS_972.05`, Metrowerks MIPS C 2.4.1) shipped with its symbol table intact: 9,703
functions with a name, an address and a size. The two games are one engine a year apart, so a routine
that was not touched between them is the SAME instruction stream at a different address -- and that is
exactly what `tools_py/fingerprint.py` is blind to. Fingerprint both tables, pair what only pairs one
way, and the demo's name is our function's name.

    from tools_py.ghidra_symbol_match import match
    pairs = match(demo_rows, ours_rows)      # [(demo_name, our_addr, score)]

    python -m tools_py.ghidra_symbol_match \\
        game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf recomp/socom2_ghidra.csv \\
        --out game/demo_symbol_matches.json --renames game/demo_symbol_renames.csv

The passes are `tools_py/address_matcher.match`'s, in its order and with its evidence rules -- exact
hash, then hash-plus-callees, then the relinked body. Nothing is reimplemented here: the whole point of
Task 10's matcher is that "the same routine, relinked" is one question, and a second answer to it that
disagreed would be worse than no answer. What this module adds is the three things the cross-GAME case
needs and the cross-revision case does not:

  * the demo side comes from an ELF symbol table, not a Ghidra CSV (`tools_py/elf_symbols.py`);
  * a SCORE, because a hash over four instructions is not the evidence a hash over four hundred is.
    A `jr $ra` epilogue thunk fingerprints the same in every program ever compiled; it only reaches
    the output at all when it happens to be unique on both sides, and when it does the score says
    how little that is worth. Callers filter on it; the note reports with and without;
  * a COLLISION count, because two demo names landing on one of our addresses (or one name on two)
    means the pairing is not a function, and a rename pass has to see that before it runs.

On "hash-plus-callee-count": within a group that shares a fingerprint the callee COUNT is necessarily
equal -- `fingerprint` zeroes the `jal` target but keeps the instruction -- so the count alone can
never split such a group. The matcher's pass 2 therefore uses the callee SET, mapped through the pairs
pass 1 already proved: of the candidates wearing this hash, the one that calls the functions this one
calls. That is the same evidence the brief asks for, in the only form that carries any.

This module never writes `recomp/socom2_ghidra.csv`. It proposes renames to a file; applying them is a
separate, reviewed step.
"""
import argparse
import csv
import json
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from tools_py import address_matcher as am
from tools_py.elf_symbols import read_elf
from tools_py.fingerprint import fingerprint

Row = Tuple[int, int, str]                      # (start, end, name) -- address_matcher.Func's shape
Pair = Tuple[str, int, float]                   # (demo_name, our_addr, score)

# What each pass is worth before the body's length is taken into account. `exact` is a hash over the
# whole stream with only the address halves blanked; `hash+callees` is that same hash plus agreement
# with pairs already proved; `relinked-body` is a COARSER hash (the global-access displacements are
# blanked too) and so a weaker claim, even though its tie-breakers are strong.
METHOD_SCORE = {"exact": 1.0, "hash+callees": 0.95, "relinked-body": 0.85, "seed+delta": 0.7,
                # The two below are the optional prefix pass (--prefix), and they are deliberately
                # under GOOD: a prefix agreeing is evidence about a PROLOGUE, not about a body. It
                # names a routine that was EDITED between the two games -- which is most of the
                # engine -- and that is worth having, but never worth renaming on unreviewed.
                "prefix": 0.6, "prefix+size": 0.7}

PREFIX_WORDS = 16                # how much of a body the prefix pass hashes -- 64 bytes

# A fingerprint is worth what the stream under it is long. These are the thresholds in BYTES; a body
# of sixteen instructions or more is taken at the method's face value, and anything shorter is
# discounted towards "this could be any epilogue in the program".
SIZE_WEIGHTS = ((64, 1.0), (32, 0.8), (16, 0.5), (0, 0.25))
GOOD = 0.8                       # the "confident enough to propose a rename" line used by the CLI


def size_weight(nbytes: int) -> float:
    for floor, weight in SIZE_WEIGHTS:
        if nbytes >= floor:
            return weight
    return SIZE_WEIGHTS[-1][1]


def score_of(how: str, nbytes: int) -> float:
    return round(METHOD_SCORE.get(how, 0.0) * size_weight(nbytes), 4)


def _split(rows: Sequence[Sequence], segments=None):
    """(funcs, segments) from rows that are either (start, end, name) or (start, end, name, code).

    The four-element form is what the tests use: each row carries its own bytes, and each becomes a
    one-function segment. That is enough for every pass except the relinked body's string anchor,
    which needs the image's data to read a string out of -- pass `segments` for that.
    """
    funcs: List[Row] = []
    carried: List[Tuple[int, bytes]] = []
    for row in rows:
        start, end, name = int(row[0]), int(row[1]), str(row[2])
        funcs.append((start, end, name))
        if len(row) > 3 and row[3] is not None:
            carried.append((start, bytes(row[3])))
    if segments is not None:
        return funcs, list(segments)
    if not carried:
        raise ValueError("rows carry no bytes and no segments were given")
    return funcs, carried


def _prefix_pass(demo_funcs, demo_segs, our_funcs, our_segs, matches):
    """Place what is left over by its PROLOGUE: the first `PREFIX_WORDS` instructions, hashed.

    A routine that was changed between SOCOM 1 and SOCOM II is not the same stream, so no pass above
    can see it -- and that is most of the engine. Its prologue usually survives the edit, though: the
    frame set-up, the register saves, the first few calls. Sixty-four bytes of masked instruction is
    not proof of identity, so this pass takes ONLY what is unique on both sides and scores it below
    the rename line. When the two bodies are also the same total length it says so, because that is a
    materially stronger claim than a prologue on its own.
    """
    a_img = am.Image.of(demo_segs, demo_funcs)
    b_img = am.Image.of(our_segs, our_funcs)
    width = PREFIX_WORDS * 4

    def index(funcs, img, skip):
        groups: Dict[str, List[Tuple[int, int]]] = {}
        for start, end, _name in funcs:
            if start in skip or end - start < width:
                continue
            body = img.code(start, end)
            if len(body) < width:
                continue
            groups.setdefault(fingerprint(body[:width]), []).append((start, end - start))
        return groups

    placed = {a for a, (b, how) in matches.items() if b is not None and how != "unresolved"}
    taken = {b for b, _how in matches.values() if b is not None}
    a_groups = index(demo_funcs, a_img, placed)
    b_groups = index(our_funcs, b_img, taken)
    out: Dict[int, Tuple[int, str]] = {}
    for h, a_hits in a_groups.items():
        b_hits = b_groups.get(h, ())
        if len(a_hits) != 1 or len(b_hits) != 1:
            continue
        (a_addr, a_size), (b_addr, b_size) = a_hits[0], b_hits[0]
        out[a_addr] = (b_addr, "prefix+size" if a_size == b_size else "prefix")
    return out


def match(demo_rows: Sequence[Sequence], ours_rows: Sequence[Sequence],
          demo_segments=None, our_segments=None, min_score: float = 0.0,
          hows: Optional[Dict[str, str]] = None, prefix: bool = False) -> List[Pair]:
    """[(demo_name, our_addr, score)] for every demo function we can place in our image.

    Rows are (start, end, name) with `*_segments` given, or (start, end, name, code) without.
    Unresolved demo functions are simply absent; `hows`, when given, is filled with
    {demo_name: pass} so a caller can report the breakdown without matching twice. `prefix` adds the
    weak fourth pass described in `_prefix_pass` -- off by default, because everything above it is
    evidence about a whole body and it is not.
    """
    demo_funcs, demo_segs = _split(demo_rows, demo_segments)
    our_funcs, our_segs = _split(ours_rows, our_segments)
    matches = am.match(demo_funcs, demo_segs, our_funcs, our_segs)
    if prefix:
        matches.update(_prefix_pass(demo_funcs, demo_segs, our_funcs, our_segs, matches))

    size_of = {start: end - start for start, end, _name in demo_funcs}
    name_of = {start: name for start, _end, name in demo_funcs}
    out: List[Pair] = []
    for demo_addr in sorted(matches):
        our_addr, how = matches[demo_addr]
        if our_addr is None or how == "unresolved":
            continue
        score = score_of(how, size_of.get(demo_addr, 0))
        if score < min_score:
            continue
        name = name_of[demo_addr]
        out.append((name, our_addr, score))
        if hows is not None:
            hows[name] = how
    return out


def collisions(pairs: Iterable[Pair]) -> Dict[str, List]:
    """The pairings that are not a one-to-one function, which a rename pass must not walk into.

    `names` is one demo name sitting on two of our addresses (a `static` compiled into two translation
    units, or a real mismatch); `addrs` is two demo names on one of our addresses. The matcher takes
    each of our functions at most once, so `addrs` should be empty -- it is checked rather than
    assumed, because "should be" is not a measurement.
    """
    by_name: Dict[str, List[int]] = {}
    by_addr: Dict[int, List[str]] = {}
    for name, addr, _score in pairs:
        by_name.setdefault(name, []).append(addr)
        by_addr.setdefault(addr, []).append(name)
    return {
        "names": sorted((n, sorted(a)) for n, a in by_name.items() if len(set(a)) > 1),
        "addrs": sorted((a, sorted(n)) for a, n in by_addr.items() if len(set(n)) > 1),
    }


# ---- the CLI -------------------------------------------------------------------------------

def load_demo(path: str):
    """(rows, segments) for the demo ELF, straight out of its symbol table."""
    elf = read_elf(path)
    return elf.functions, elf.segments


def load_ours(elf_path: str, csv_path: str):
    """(rows, segments) for our image: the Ghidra table plus the bytes the recompiler consumes."""
    with open(elf_path, "rb") as fh:
        segments = am.load_segments(fh.read())
    return am.load_functions(csv_path), segments


def _is_anonymous(name: str) -> bool:
    return name.startswith("FUN_") or name.startswith("thunk_FUN_")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="name our functions from the demo's debug symbols")
    ap.add_argument("demo_elf")
    ap.add_argument("our_elf")
    ap.add_argument("our_csv")
    ap.add_argument("--out", help="JSON: every pair, with its pass and score")
    ap.add_argument("--renames", help="CSV: the proposed renames (never applied here)")
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--good", type=float, default=GOOD, help="the score a proposed rename needs")
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--prefix", action="store_true",
                    help="add the weak prologue pass; its pairs never reach --good")
    args = ap.parse_args(list(argv) if argv is not None else None)

    demo_rows, demo_segs = load_demo(args.demo_elf)
    our_rows, our_segs = load_ours(args.our_elf, args.our_csv)
    hows: Dict[str, str] = {}
    pairs = match(demo_rows, our_rows, demo_segs, our_segs, min_score=args.min_score, hows=hows,
                  prefix=args.prefix)

    size_of = {name: end - start for start, end, name in demo_rows}
    our_name = {start: name for start, _end, name in our_rows}
    rate = len(pairs) / len(demo_rows) if demo_rows else 0.0
    print("demo functions %d, ours %d, matched %d (%.1f%%)"
          % (len(demo_rows), len(our_rows), len(pairs), 100 * rate))
    per_how: Dict[str, int] = {}
    for name, _addr, _score in pairs:
        per_how[hows[name]] = per_how.get(hows[name], 0) + 1
    print("  by pass: " + ", ".join("%s %d" % kv for kv in sorted(per_how.items())))
    good = [p for p in pairs if p[2] >= args.good]
    print("  score >= %.2f: %d" % (args.good, len(good)))
    coll = collisions(pairs)
    print("  collisions: %d names on several addresses, %d addresses under several names"
          % (len(coll["names"]), len(coll["addrs"])))

    print("\ntop %d by body size:" % args.top)
    for name, addr, score in sorted(pairs, key=lambda p: -size_of.get(p[0], 0))[:args.top]:
        print("  %7d  0x%08x  %-10s %.2f  %s"
              % (size_of.get(name, 0), addr, hows[name], score, name))

    if args.out:
        payload = {
            "demo_functions": len(demo_rows),
            "our_functions": len(our_rows),
            "matched": len(pairs),
            "rate": round(rate, 6),
            "by_pass": per_how,
            "collisions": coll,
            "pairs": [{"name": n, "addr": "0x%08x" % a, "score": s, "how": hows[n],
                       "size": size_of.get(n, 0)} for n, a, s in pairs],
        }
        with open(args.out, "w", newline="") as fh:
            json.dump(payload, fh, indent=1, sort_keys=True)
        print("\nwrote %s" % args.out)

    if args.renames:
        with open(args.renames, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Address", "Current", "Proposed", "Score", "How", "Size"])
            for name, addr, score in sorted(good, key=lambda p: p[1]):
                current = our_name.get(addr, "")
                if not _is_anonymous(current):
                    continue                     # a function we already named by hand keeps its name
                w.writerow(["0x%08x" % addr, current, name, "%.2f" % score, hows[name],
                            size_of.get(name, 0)])
        print("wrote %s (proposals only -- applying them is a separate, reviewed step)" % args.renames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
