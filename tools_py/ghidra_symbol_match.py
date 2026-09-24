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
        --prefix --out game/demo_symbol_matches.json --renames game/demo_symbol_renames.csv

The passes are `tools_py/address_matcher.match`'s, in its order and with its evidence rules -- exact
hash, then hash-plus-callees, then the relinked body. Nothing is reimplemented here: the whole point of
Task 10's matcher is that "the same routine, relinked" is one question, and a second answer to it that
disagreed would be worse than no answer. What this module adds is what the cross-GAME case needs and
the cross-revision case does not:

  * the demo side comes from an ELF symbol table, not a Ghidra CSV (`tools_py/elf_symbols.py`);
  * a SCORE, because a hash over four instructions is not the evidence a hash over four hundred is;
  * a PROPOSAL RULE that is stricter than the score (see `proposals`), because the `Name` column of
    `recomp/socom2_ghidra.csv` is not a comment: the recompiler makes it the generated function's C
    name AND its output filename, and a wrong one is inherited by every future reader with no record
    that it was a guess. Nothing here writes that CSV; this module only proposes.

On "hash-plus-callee-count": within a group that shares a fingerprint the callee COUNT is necessarily
equal -- `fingerprint` zeroes the `jal` target but keeps the instruction -- so the count alone can
never split such a group. The matcher's pass 2 therefore uses the callee SET, mapped through the pairs
pass 1 already proved: of the candidates wearing this hash, the one that calls the functions this one
calls. That is the same evidence the brief asks for, in the only form that carries any.
"""
import argparse
import csv
import hashlib
import json
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from tools_py import address_matcher as am
from tools_py.elf_symbols import read_elf
from tools_py.fingerprint import fingerprint

Row = Tuple[int, int, str]                      # (start, end, name) -- address_matcher.Func's shape
Pair = Tuple[str, int, float]                   # (demo_name, our_addr, score)
Key = Tuple[str, int]                           # (demo_name, our_addr) -- a pair's identity

# What each pass is worth before the body's length is taken into account. `exact` is a hash over the
# whole stream with only the address halves blanked; `hash+callees` is that same hash plus agreement
# with pairs already proved; `relinked-body` is a COARSER hash (the global-access displacements are
# blanked too) and so a weaker claim, even though its tie-breakers are strong.
METHOD_SCORE = {
    "exact": 1.0,
    "hash+callees": 0.95,
    "relinked-body": 0.85,
    # Unreachable from this module: `match` never passes `seeds`, so address_matcher's pass 4 never
    # runs. Kept rather than dropped so that a future caller that DOES seed gets a scored pair instead
    # of a silent 0.0 from the `.get` below.
    "seed+delta": 0.7,
    # The two below are the optional prefix pass (--prefix). They are under GOOD by construction and
    # `proposals` refuses them outright as well: a prefix agreeing is evidence about a PROLOGUE, not
    # about a body. It names a routine that was EDITED between the two games -- which is most of the
    # engine -- and that is worth having, but never worth renaming on unreviewed.
    "prefix": 0.6,
    "prefix+size": 0.7,
}

PREFIX_WORDS = 16                # how much of a body the prefix pass hashes -- 64 bytes

# A fingerprint is worth what the stream under it is long. These are the thresholds in BYTES.
SIZE_WEIGHTS = ((64, 1.0), (32, 0.8), (16, 0.5), (0, 0.25))
GOOD = 0.8                       # the score a proposed rename needs
PROPOSE_MIN_SIZE = 64            # ...and the body length it needs, which is not the same thing

# A rename has to survive being written into a C identifier and a filename.
IDENT_OK = re.compile(r"[A-Za-z0-9_]")
IDENT_LIMIT = 96                 # `recomp` writes <name>_0x<addr>.cpp; 269-char mangled names exist


def size_weight(nbytes: int) -> float:
    for floor, weight in SIZE_WEIGHTS:
        if nbytes >= floor:
            return weight
    return SIZE_WEIGHTS[-1][1]


def score_of(how: str, nbytes: int) -> float:
    return round(METHOD_SCORE.get(how, 0.0) * size_weight(nbytes), 4)


def c_identifier(name: str, limit: int = IDENT_LIMIT) -> str:
    """`name` as something that is legal as a C identifier AND as a filename, deterministically.

    Metrowerks mangling is not identifier-safe: templates carry `<`, `>` and `,`, an anonymous
    namespace carries `@`, and a static initialiser is named after its source file (`__sinit_ent_main
    .cpp`). Fifteen of the demo's matched names are in that shape, five of them at `exact`/1.00 -- the
    highest-confidence end of the file -- and `<`/`>` are illegal in a Windows filename as well as in
    an identifier. Every character outside `[A-Za-z0-9_]` becomes `_`; a leading digit gets a `_`; and
    a name past `limit` is cut and given eight hex digits of SHA-1 of the ORIGINAL, so two long names
    that share a prefix do not become one identifier. The mangled original is kept in its own column
    of the proposals file, so nothing is lost by this.
    """
    safe = "".join(ch if IDENT_OK.match(ch) else "_" for ch in name)
    if not safe or safe[0].isdigit():
        safe = "_" + safe
    if len(safe) > limit:
        digest = hashlib.sha1(name.encode("utf-8", "replace")).hexdigest()[:8]
        safe = safe[:limit - 9] + "_" + digest
    return safe


def is_engine(name: str) -> bool:
    """True for a routine of the GAME rather than of the Sony SDK or the C runtime.

    Metrowerks mangles a member function as `name__<len><Class>F<args>`, and the engine's free
    functions are the `z…`/`hud…` ones. `sce*`, `__ieee754*`, the IPU/MPEG decoder and libc are all
    excluded by having neither shape. This is the filter behind the note's §4 table; `--engine` on the
    command line is what reproduces it.
    """
    return bool(re.search(r"__\d+[A-Za-z_]", name)) or name.startswith(("z", "hud"))


def is_anonymous(name: str) -> bool:
    """True for a Ghidra placeholder name -- a row a rename may take over.

    Anything else is a name a human chose (113 of our 14,879 rows), and a match is not a reason to
    overwrite one: the human saw the body, the fingerprint only saw the bytes.
    """
    return name.startswith("FUN_") or name.startswith("thunk_FUN_")


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
    not proof of identity, so this pass takes ONLY what is unique on both sides, scores it below the
    rename line, and is refused by `proposals` outright. When the two bodies are also the same total
    length it says so, because that is a materially stronger claim than a prologue on its own.
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
          details: Optional[Dict[Key, Dict]] = None, prefix: bool = False) -> List[Pair]:
    """[(demo_name, our_addr, score)] for every demo function we can place in our image.

    Rows are (start, end, name) with `*_segments` given, or (start, end, name, code) without.
    Unresolved demo functions are simply absent.

    `details`, when given, is filled with {(demo_name, our_addr): {how, size, demo_addr}}. It is keyed
    by the PAIR, not by the demo name: `elf_symbols.functions` de-duplicates by address, not by name,
    so two demo addresses can carry one name -- a C `static` compiled into two translation units --
    and a name-keyed table would give one of those two pairs the other's pass and the other's size.
    That is the single case this module exists to notice, so it is the last one its own bookkeeping
    may blur.
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
        size = size_of.get(demo_addr, 0)
        score = score_of(how, size)
        if score < min_score:
            continue
        name = name_of[demo_addr]
        out.append((name, our_addr, score))
        if details is not None:
            details[(name, our_addr)] = {"how": how, "size": size, "demo_addr": demo_addr}
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


# ---- the proposals -------------------------------------------------------------------------

PROPOSAL_COLUMNS = ["Address", "Current", "Proposed", "Mangled", "Score", "How", "Size"]


def proposals(pairs: Sequence[Pair], details: Dict[Key, Dict], our_names: Dict[int, str],
              good: float = GOOD, min_size: int = PROPOSE_MIN_SIZE):
    """(rows, held_back) -- the pairs a rename pass may apply, and a count per reason for the rest.

    A pair reaches the file only if ALL of the following hold. Each is a separate hurdle because each
    is a separate way for a rename to be wrong, and the `Name` column is a C function name and an
    output filename, not a comment.

      score >= `good`        the pass's own confidence, and
      size  >= `min_size`    a body of at least 64 bytes, which is NOT implied by the score. `exact`
                             times the 32-byte size weight is 1.0 x 0.8 = 0.80 exactly, so the score
                             line on its own admits eight-instruction bodies whose only evidence is
                             that their hash happened to be unique in two tables of different sizes.
                             At 64 bytes and up the weight is 1.0 and the score IS the method's face
                             value; below it the 0.80 is manufactured by the weighting. The pairs
                             between the two rules are not discarded -- they are in the --out JSON,
                             counted here, and discussed in docs/research/44-demo-symbols.md.
      not a prefix pass      a prologue agreeing is not a body agreeing, at any length or cut.
      not a colliding name   one demo name on two of our addresses cannot be applied to both: one C
                             `static` is not two functions, and two CSV rows with one Name give the
                             recompiler two definitions of one symbol.
      our row still FUN_*    a function we named by hand keeps its name.
      a unique C identifier  after `c_identifier`; if two proposals sanitise to the same spelling,
                             neither is written, because the pair that is wrong is not knowable here.
    """
    held: Dict[str, int] = {}

    def hold(reason: str) -> None:
        held[reason] = held.get(reason, 0) + 1

    colliding = {n for n, _addrs in collisions(pairs)["names"]}
    kept = []
    for name, addr, score in pairs:
        info = details.get((name, addr), {})
        how, size = info.get("how", ""), int(info.get("size", 0))
        if how.startswith("prefix"):
            hold("prefix pass")
        elif score < good:
            hold("score below %.2f" % good)
        elif size < min_size:
            hold("body under %d bytes" % min_size)
        elif name in colliding:
            hold("colliding demo name")
        elif not is_anonymous(our_names.get(addr, "")):
            hold("our row is already named")
        else:
            kept.append((name, addr, score, how, size))

    spelling: Dict[str, int] = {}
    for name, _addr, _score, _how, _size in kept:
        ident = c_identifier(name)
        spelling[ident] = spelling.get(ident, 0) + 1
    rows = []
    for name, addr, score, how, size in sorted(kept, key=lambda k: k[1]):
        ident = c_identifier(name)
        if spelling[ident] > 1:
            hold("identifier collides after sanitising")
            continue
        rows.append({"Address": "0x%08x" % addr, "Current": our_names.get(addr, ""),
                     "Proposed": ident, "Mangled": name, "Score": "%.2f" % score,
                     "How": how, "Size": size})
    return rows, held


def write_proposals(path: str, rows: Sequence[Dict]) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=PROPOSAL_COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row)


# ---- the checks the note's §5 and §6 report -------------------------------------------------

def mask_coverage(elf) -> Tuple[int, int]:
    """(relocated words inside a function body, how many of those the fingerprint's mask blanks).

    The demo keeps its `.relmain` relocations, which is the linker's own record of which words carry
    an address. The fingerprint blanks address-carrying words by an OPCODE rule instead, because our
    side has no relocation table and a mask only one side applies proves nothing. This measures how
    far the two agree -- i.e. whether the reason a relinked body fingerprints equal is the reason the
    module claims. Reproduces §5 of docs/research/44-demo-symbols.md.
    """
    from tools_py.fingerprint import IMM_ZEROED_OPCODES
    funcs = elf.functions
    img = am.Image.of(elf.segments, funcs)
    relocated = elf.relocated_words()
    inside = covered = 0
    for start, end, _name in funcs:
        body = img.code(start, end)
        masked = None
        for i in range(0, len(body) - 3, 4):
            if start + i not in relocated:
                continue
            inside += 1
            word = int.from_bytes(body[i:i + 4], "little")
            if (word >> 26) in IMM_ZEROED_OPCODES:
                covered += 1
                continue
            if masked is None:
                masked = am.mask_address_operands(body)
            if masked[i:i + 4] != body[i:i + 4]:
                covered += 1
    return inside, covered


CLASS_RE = re.compile(r"__(\d+)([A-Za-z_][A-Za-z0-9_]*)")


def class_of(name: str) -> Optional[str]:
    """The class a Metrowerks-mangled member belongs to -- `__<len><Class>` -- or None."""
    m = CLASS_RE.search(name)
    if not m:
        return None
    length = int(m.group(1))
    cls = name[m.end(1):m.end(1) + length]
    return cls if len(cls) == length else None


def class_clusters(pairs: Sequence[Pair], members: int = 3, window: int = 0x40000):
    """[(class, count, low, high)] for every class with `members` or more matched members, sorted.

    A class whose members all land inside one window of our image is evidence the pairings are real:
    random pairings do not cluster. Reproduces the second check in §5 of the note.
    """
    by_class: Dict[str, List[int]] = {}
    for name, addr, _score in pairs:
        cls = class_of(name)
        if cls:
            by_class.setdefault(cls, []).append(addr)
    out = [(cls, len(a), min(a), max(a)) for cls, a in by_class.items() if len(a) >= members]
    return sorted(out, key=lambda row: (-row[1], row[0]))


def fingerprint_buckets(demo_rows, demo_segs, our_rows, our_segs, details: Dict[Key, Dict]):
    """{bucket: (demo functions, of those placed)} by what the PLAIN fingerprint can see.

    Every demo function is in exactly one bucket: its fingerprint is absent from our image, present
    but ambiguous, or present and unique on both sides. Reproduces §6's table. `details` is `match`'s
    out-parameter, which carries each pair's DEMO address -- the thing a name cannot be trusted for.
    """
    demo_funcs, demo_segs = _split(demo_rows, demo_segs)
    our_funcs, our_segs = _split(our_rows, our_segs)
    a, b = am.Side(demo_funcs, demo_segs), am.Side(our_funcs, our_segs)
    placed = {info["demo_addr"] for info in details.values()}
    out: Dict[str, List[int]] = {k: [0, 0] for k in ("absent", "ambiguous", "unique")}
    for start in a.starts:
        fp = a.fp[start]
        cands = b.by_fp.get(fp) if fp else None
        if not cands:
            kind = "absent"
        elif len(a.by_fp[fp]) == 1 and len(cands) == 1:
            kind = "unique"
        else:
            kind = "ambiguous"
        out[kind][0] += 1
        if start in placed:
            out[kind][1] += 1
    return {k: tuple(v) for k, v in out.items()}


def region_split(pairs: Sequence[Pair], details: Dict[Key, Dict], our_segments):
    """[(vaddr, end, total, prefix)] -- where in OUR image the pairs land, per PT_LOAD.

    Reported with the prefix subset broken out because the two are different claims: the non-prefix
    pairs are the ones a rename could ever be built on. Reproduces §3's last bullet, which was
    previously three numbers from a session script that summed to 828, not 987.
    """
    out = []
    for vaddr, data in sorted(our_segments):
        end = vaddr + len(data)
        inside = [p for p in pairs if vaddr <= p[1] < end]
        prefix = [p for p in inside if details[(p[0], p[1])]["how"].startswith("prefix")]
        out.append((vaddr, end, len(inside), len(prefix)))
    return out


def table_census(our_rows, our_segments) -> Dict[str, int]:
    """{rows, named_by_hand, without_bytes} for our Ghidra table -- §1's last row."""
    funcs, segments = _split(our_rows, our_segments)
    image = am.Image.of(segments, funcs)
    return {"rows": len(funcs),
            "named_by_hand": sum(1 for _s, _e, name in funcs if not is_anonymous(name)),
            "without_bytes": sum(1 for start, end, _n in funcs if not image.code(start, end))}


def small_body_histogram(demo_rows, demo_segs, our_rows, our_segs):
    """{threshold: how many AMBIGUOUS demo bodies are that size or smaller} -- §6's second claim."""
    demo_funcs, demo_segs = _split(demo_rows, demo_segs)
    our_funcs, our_segs = _split(our_rows, our_segs)
    a, b = am.Side(demo_funcs, demo_segs), am.Side(our_funcs, our_segs)
    sizes = []
    for start in a.starts:
        fp = a.fp[start]
        cands = b.by_fp.get(fp) if fp else None
        if cands and not (len(a.by_fp[fp]) == 1 and len(cands) == 1):
            sizes.append(a.size[start])
    return {"total": len(sizes), "<=16": sum(1 for s in sizes if s <= 16),
            ">=64": sum(1 for s in sizes if s >= 64), ">=128": sum(1 for s in sizes if s >= 128)}


# ---- the CLI -------------------------------------------------------------------------------

def load_demo(path: str):
    """(rows, segments) for the demo ELF, straight out of its symbol table."""
    elf = read_elf(path)
    return elf.functions, elf.segments


def load_ours(elf_path: str, csv_path: str):
    """(rows, segments) for our image: the Ghidra table plus the bytes the recompiler consumes.

    Both images go through `elf_symbols.read_elf`, so one PT_LOAD reader serves both sides of the
    match; only the function table differs (ours is Ghidra's, the demo's is its own `.symtab`).
    """
    return am.load_functions(csv_path), read_elf(elf_path).segments


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="name our functions from the demo's debug symbols")
    ap.add_argument("demo_elf")
    ap.add_argument("our_elf")
    ap.add_argument("our_csv")
    ap.add_argument("--out", help="JSON: every pair, with its pass and score")
    ap.add_argument("--renames", help="CSV: the proposed renames (never applied here)")
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--good", type=float, default=GOOD,
                    help="the score a proposed rename needs; never lowered below %.2f" % GOOD)
    ap.add_argument("--min-size", type=int, default=PROPOSE_MIN_SIZE,
                    help="the body a proposed rename needs, in bytes; never lowered below %d"
                         % PROPOSE_MIN_SIZE)
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--engine", action="store_true",
                    help="restrict the printed table to engine routines (not sce*/libc)")
    ap.add_argument("--prefix", action="store_true",
                    help="add the weak prologue pass; its pairs can never be proposed")
    ap.add_argument("--verify", action="store_true",
                    help="print the .relmain mask coverage, the class clustering and the buckets")
    args = ap.parse_args(list(argv) if argv is not None else None)

    missing = [p for p in (args.demo_elf, args.our_elf, args.our_csv) if not os.path.exists(p)]
    if missing:
        for path in missing:
            print("NO-DATA: missing %s" % path)
        print("NO-DATA: the SOCOM 1 demo ELF is git-ignored; see docs/research/44-demo-symbols.md §1")
        return 2
    try:
        demo_rows, demo_segs = load_demo(args.demo_elf)
        our_rows, our_segs = load_ours(args.our_elf, args.our_csv)
    except ValueError as exc:
        print("NO-DATA: %s" % exc)
        return 2

    details: Dict[Key, Dict] = {}
    pairs = match(demo_rows, our_rows, demo_segs, our_segs, min_score=args.min_score,
                  details=details, prefix=args.prefix)

    our_name = {start: name for start, _end, name in our_rows}
    rate = len(pairs) / len(demo_rows) if demo_rows else 0.0
    print("demo functions %d, ours %d, matched %d (%.1f%%)"
          % (len(demo_rows), len(our_rows), len(pairs), 100 * rate))
    per_how: Dict[str, int] = {}
    for key in details:
        per_how[details[key]["how"]] = per_how.get(details[key]["how"], 0) + 1
    print("  by pass: " + ", ".join("%s %d" % kv for kv in sorted(per_how.items())))
    coll = collisions(pairs)
    print("  collisions: %d names on several addresses, %d addresses under several names"
          % (len(coll["names"]), len(coll["addrs"])))
    # The cut is clamped, not merely documented: --good 0.60 would otherwise put all 159 prefix pairs
    # into the proposals file in the same columns as an `exact` at 1.00.
    good, min_size = max(args.good, GOOD), max(args.min_size, PROPOSE_MIN_SIZE)
    rows, held = proposals(pairs, details, our_name, good=good, min_size=min_size)
    print("  proposals: %d (score >= %.2f AND body >= %d bytes)" % (len(rows), good, min_size))
    for reason in sorted(held):
        print("    held back: %-34s %d" % (reason, held[reason]))

    if args.top:
        shown = [p for p in pairs if not args.engine or is_engine(p[0])]
        print("\ntop %d by body size%s:" % (args.top, " (engine only)" if args.engine else ""))
        for name, addr, score in sorted(shown, key=lambda p: -details[(p[0], p[1])]["size"])[:args.top]:
            info = details[(name, addr)]
            print("  %7d  0x%08x  %-13s %.2f  %s" % (info["size"], addr, info["how"], score, name))

    if args.verify:
        inside, covered = mask_coverage(read_elf(args.demo_elf))
        print("\nrelocated words inside a demo function body: %d; blanked by the mask: %d (%.2f%%)"
              % (inside, covered, 100 * covered / inside if inside else 0.0))
        clusters = class_clusters(pairs)
        tight = [c for c in clusters if c[3] - c[2] <= 0x40000]
        print("classes with >=3 matched members: %d; all members within 256 KB: %d"
              % (len(clusters), len(tight)))
        for cls, count, low, high in clusters[:12]:
            print("  %-22s %2d  0x%06x..0x%06x  span %d KB" % (cls, count, low, high,
                                                              (high - low) // 1024))
        buckets = fingerprint_buckets(demo_rows, demo_segs, our_rows, our_segs, details)
        print("exact-fingerprint buckets (demo functions, of those placed):")
        for kind in ("absent", "ambiguous", "unique"):
            print("  %-10s %5d  placed %d" % ((kind,) + buckets[kind]))
        print("ambiguous by body size: %s"
              % small_body_histogram(demo_rows, demo_segs, our_rows, our_segs))
        census = table_census(our_rows, our_segs)
        print("our table: %d rows, %d already named by hand, %d with no bytes in any segment"
              % (census["rows"], census["named_by_hand"], census["without_bytes"]))
        print("where the %d pairs land in our image, per PT_LOAD:" % len(pairs))
        for vaddr, end, total, prefix in region_split(pairs, details, our_segs):
            print("  0x%06x-0x%06x  %4d  (of which prefix %d)" % (vaddr, end, total, prefix))

    if args.out:
        payload = {
            "demo_functions": len(demo_rows), "our_functions": len(our_rows),
            "matched": len(pairs), "rate": round(rate, 6), "by_pass": per_how,
            "collisions": coll, "proposals": len(rows), "held_back": held,
            "pairs": [{"name": n, "addr": "0x%08x" % a, "score": s,
                       "how": details[(n, a)]["how"], "size": details[(n, a)]["size"]}
                      for n, a, s in pairs],
        }
        with open(args.out, "w", newline="") as fh:
            json.dump(payload, fh, indent=1, sort_keys=True)
        print("\nwrote %s" % args.out)

    if args.renames:
        write_proposals(args.renames, rows)
        print("wrote %s (proposals only -- applying them is a separate, reviewed step)" % args.renames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
