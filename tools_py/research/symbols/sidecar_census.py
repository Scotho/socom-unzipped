"""The provenance sidecar (spec 1.3), checked against the tree. Sprint 12 research Q3, docs/research/48.

Run from the repo root:  python tools_py/research/symbols/sidecar_census.py [--no-git] [--rows]

Read-only. Reads recomp/socom2_ghidra.csv, recomp/socom2_ghidra_r0004.csv, recomp/socom2.toml,
recomp/extra_functions*.txt, game/r0004/match.json, game/demo_symbol_renames.csv and
game/demo_symbol_renames_7b.csv (and, when they are there, game/disc/socom2_game.elf for [3b] and the
SOCOM 1 demo ELF for [4]'s demo lines), and runs read-only `git log` over recomp/socom2_ghidra.csv.
Writes nothing. Prints names, addresses and counts only -- no game bytes.

What it prints, one block per section of the note:
  [1] the Name census of both csvs by class (FUN_, LAB_, thunk_FUN_, caseD_, sub_, entry, other),
      the "other" names grouped, the r0004 csv split into names equal to the r0001 name at their
      match.json source (carried) and r0004's own; duplicate names; address uniqueness
  [2] sub_ in either csv; the literal "sub_ in the recompiler/analyzer sources; extra_functions*.txt
      line counts and how many of their addresses are already rows; how many rows' ranges hold another
      row's start (what a name's "authoritative range" would swallow), overall and among the 485
  [3] for every distinct name research/44 counts as "named by hand" (the 113 rows that are neither
      FUN_ nor thunk_FUN_): the oldest commit that `git log -S'<name>'` and `git log -G'^<name>,0x'`
      find in recomp/socom2_ghidra.csv's history, the date distribution, the subjects, and the names
      whose lines a later commit also touched
  [3b] how many of the non-auto rows are 16-byte `li v1,<n>; syscall` stubs, and whether each RFUnnn
      stub loads the number its name carries (counts only)
  [4] carry_names' is_addressy (an 8-hex run anywhere) and the proposed anchored rule over readable()
      of the 485 proposals (bare and with the overload suffix), the 656 toml names, the hand names, the
      demo's 9,703; and the leak check's opaque-token rule (tools_py/release/leakrules.py) over the same
  [5] the 485 proposals' addresses against game/r0004/match.json, by pass and `how`; carry_names.carry
      itself run on a copy of the r0004 rows with the readable names in place, with today's is_addressy
      and with the proposed ADDRESS_NAME; the 16 unresolved names
  [6] header / column facts about the files the sidecar sits beside
  [7] the audit prototype: with no sidecar yet, the rows the backfill must write, in the order
      Address,Name,Mangled,Pass,Score,Evidence,Source,Date (--rows prints every row; default the count
      and the first/last three)
--no-git skips [3] (and leaves Date empty in [7]).
"""
import collections
import csv
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root

CSV1 = "recomp/socom2_ghidra.csv"
CSV4 = "recomp/socom2_ghidra_r0004.csv"
TOML = "recomp/socom2.toml"
EXTRA = ("recomp/extra_functions.txt", "recomp/extra_functions_r0004.txt")
MATCH = "game/r0004/match.json"
REN = "game/demo_symbol_renames.csv"
REN7B = "game/demo_symbol_renames_7b.csv"
SRC_DIRS = ("third_party/ps2recomp/ps2xAnalyzer", "third_party/ps2recomp/ps2xRecomp")

# carry_names' rule, copied (tools_py/carry_names.py ADDRESSY)
ADDRESSY = re.compile(r"[0-9A-Fa-f]{8}")
# spec 1.3's auto-name prefixes, as the spec writes them
SPEC_AUTO = ("FUN_", "LAB_", "thunk_FUN_", "caseD_", "sub_", "entry")
# the rule this note proposes in their place: the SHAPES Ghidra and ps2recomp give a placeholder, anchored
# at both ends, so a real word that happens to hold eight hex letters is never mistaken for one
# ADDRESS_NAME: may not travel to another address (carry_names); AUTO_PROPOSED: needs no sidecar row (the
# audit) -- the same shapes plus `entry`, which is Ghidra's placeholder but names no address, so it may travel
ADDRESS_NAME = re.compile(r"^(?:(?:FUN|LAB|DAT|SUB|sub)_[0-9A-Fa-f]{8}|thunk_(?:EXT_)?FUN_[0-9A-Fa-f]{8}"
                          r"|caseD_[0-9A-Fa-f]+|switchD_[0-9A-Fa-f]{8})$")
AUTO_PROPOSED = re.compile(r"^(?:%s|entry)$" % ADDRESS_NAME.pattern[1:-1])
ELF = "game/disc/socom2_game.elf"
DEMO = "game/demo_scus_972_05/SCUS_972.05"

# ---- readable(), copied from tools_py/research/symbols/readable_names.py (unchanged) -------------
OPERATORS = {
    "__ct": "ctor", "__dt": "dtor", "__as": "op_assign",
    "__pl": "op_add", "__mi": "op_sub", "__ml": "op_mul", "__dv": "op_div", "__md": "op_mod",
    "__eq": "op_eq", "__ne": "op_ne", "__lt": "op_lt", "__gt": "op_gt", "__le": "op_le", "__ge": "op_ge",
    "__vc": "op_index", "__cl": "op_call", "__nw": "op_new", "__dl": "op_delete",
    "__nwa": "op_new_array", "__dla": "op_delete_array",
    "__aa": "op_and", "__oo": "op_or", "__er": "op_xor", "__ad": "op_bitand", "__or": "op_bitor",
    "__ls": "op_lsh", "__rs": "op_rsh", "__nt": "op_not", "__ng": "op_neg", "__co": "op_compl",
    "__pp": "op_inc", "__mm": "op_dec", "__rf": "op_deref", "__rm": "op_arrow",
    "__apl": "op_addassign", "__ami": "op_subassign", "__amu": "op_mulassign", "__adv": "op_divassign",
}
_SPLIT = re.compile(r"^(.*?)__(?:Q\d|\d+)")
_SAFE = re.compile(r"[^A-Za-z0-9_]")


def readable(mangled: str) -> str:
    m = _SPLIT.match(mangled)
    if not m:
        return _SAFE.sub("_", mangled)
    fn = m.group(1)
    rest = mangled[len(fn) + 2:]
    fn = OPERATORS.get(fn, fn)
    fn = re.sub(r"<.*>", "", fn)
    classes = []
    q = re.match(r"Q(\d)", rest)
    if q:
        pos = q.end()
        for _ in range(int(q.group(1))):
            n = re.match(r"(\d+)", rest[pos:])
            if not n:
                break
            length = int(n.group(1))
            pos += n.end()
            classes.append(rest[pos:pos + length])
            pos += length
    else:
        n = re.match(r"(\d+)", rest)
        if n:
            length = int(n.group(1))
            classes.append(rest[n.end():n.end() + length])
    return _SAFE.sub("_", "_".join(classes + [fn]) if classes else fn)


def arg_suffix(mangled: str) -> str:
    """Spec 1.2 rule 2's suffix: the mangled argument list after the `F`, sanitised, cut to 24."""
    m = re.search(r"(?:C?F)(.*)$", mangled.split("__", 1)[1]) if "__" in mangled else None
    return _SAFE.sub("_", m.group(1))[:24] if m else ""

# ---------------------------------------------------------------------------------------------------


def name_class(n: str) -> str:
    for p in ("thunk_FUN_", "FUN_", "LAB_", "caseD_", "sub_"):
        if n.startswith(p):
            return p
    return "entry" if n == "entry" else "other"


def spec_auto(n: str) -> bool:
    return n == "entry" or any(n.startswith(p) for p in SPEC_AUTO if p != "entry")


def group_other(n: str) -> str:
    if n.startswith("thunk_"):
        return "thunk (Ghidra, external target)"
    if n.startswith("RFU"):
        return "EE kernel syscall, reserved slot (RFUnnn)"
    if n.startswith("sceSif") or n.startswith("isceSif"):
        return "EE kernel syscall, SIF"
    return "EE kernel syscall"


def rows_of(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def proposals():
    """[(address, mangled, pass, score, evidence, source)] for the 479 + the 6."""
    out = []
    for r in rows_of(REN):
        out.append((int(r["Address"], 16), r["Mangled"], r["How"], r["Score"],
                    "size %s" % r["Size"], "research/44 command A"))
    with open(REN7B, newline="", encoding="utf-8") as fh:
        body = [ln for ln in fh if not ln.startswith("#")]
    for r in csv.DictReader(body):
        out.append((int(r["Address"], 16), r["Mangled"], r["Source"], "0.80",
                    "tier %s %s, ratio %s, gap %s" % (r["Tier"], r["Evidence"], r["Ratio"], r["GapSize"]),
                    "research/45 command A"))
    return out


def git(*args):
    return subprocess.run(("git",) + args, capture_output=True, text=True, check=True).stdout


def oldest(args):
    lines = [ln for ln in git("log", "--format=%h %ad %s", "--date=short", *args, "--", CSV1).splitlines() if ln]
    return lines[-1] if lines else None


def main() -> int:
    use_git = "--no-git" not in sys.argv
    all_rows = "--rows" in sys.argv
    r1 = rows_of(CSV1)
    r4 = rows_of(CSV4)

    # ---- [1] -----------------------------------------------------------------------------------
    print("[1] name census")
    for label, rows in ((CSV1, r1), (CSV4, r4)):
        c = collections.Counter(name_class(r["Name"]) for r in rows)
        addrs = collections.Counter(int(r["Start"], 16) for r in rows)
        print("  %s: %d rows, %d distinct Start; %s" % (
            label, len(rows), len(addrs),
            ", ".join("%s %d" % (k, c.get(k, 0)) for k in ("FUN_", "LAB_", "thunk_FUN_", "caseD_", "sub_",
                                                           "entry", "other"))))
        hand44 = [r for r in rows if not (r["Name"].startswith("FUN_") or r["Name"].startswith("thunk_FUN_"))]
        nonauto = [r for r in rows if not spec_auto(r["Name"])]
        print("    research/44's 'named by hand' (neither FUN_ nor thunk_FUN_): %d rows; "
              "non-auto under spec 1.3's prefix list: %d rows, %d distinct names"
              % (len(hand44), len(nonauto), len({r["Name"] for r in nonauto})))
        dups = {k: v for k, v in collections.Counter(r["Name"] for r in rows).items() if v > 1}
        dnon = {k: v for k, v in dups.items() if not spec_auto(k)}
        print("    duplicate names: %d names over %d rows; of them non-auto: %s"
              % (len(dups), sum(dups.values()), dnon))
    print("  r0001 'other' names, grouped:")
    groups = collections.defaultdict(list)
    for r in r1:
        if name_class(r["Name"]) == "other":
            groups[group_other(r["Name"])].append("%s@%s" % (r["Name"], r["Start"].lower()))
    for g, names in sorted(groups.items()):
        print("    %s (%d): %s" % (g, len(names), " ".join(names)))
    cased = collections.Counter(r["Name"] for r in r1 if r["Name"].startswith("caseD_"))
    print("    caseD_ (%d rows, %d distinct): %s" % (sum(cased.values()), len(cased), dict(sorted(cased.items()))))
    print("  FUN_ names that are not exactly FUN_ + 8 lower-case hex: %d; thunk_FUN_ likewise: %d"
          % (sum(1 for r in r1 + r4 if r["Name"].startswith("FUN_") and not re.match(r"^FUN_[0-9a-f]{8}$", r["Name"])),
             sum(1 for r in r1 + r4 if r["Name"].startswith("thunk_FUN_")
                 and not re.match(r"^thunk_FUN_[0-9a-f]{8}$", r["Name"]))))
    print("  proposed auto rule over r0001: auto %d, not auto %d (the latter: %s other names)"
          % (sum(bool(AUTO_PROPOSED.match(r["Name"])) for r in r1),
             sum(not AUTO_PROPOSED.match(r["Name"]) for r in r1),
             len({r["Name"] for r in r1 if not AUTO_PROPOSED.match(r["Name"])})))

    with open(MATCH, encoding="utf-8") as fh:
        match = json.load(fh)
    m = match["matches"]
    by_b = {int(v["b"], 16): (int(a, 16), v) for a, v in m.items() if v.get("b")}
    print("  match.json: %d r0001 rows, %d placed; summary %s; its b csv %s"
          % (len(m), len(by_b), match["summary"], match["b"]["csv"]))
    split = collections.Counter()
    for r in r4:
        n, a = r["Name"], int(r["Start"], 16)
        src = by_b.get(a)
        kind = "carried" if src and src[1]["name"] == n else "own"
        split[(name_class(n), kind, src[1]["how"] if src and kind == "carried" else "-")] += 1
    print("  r0004 csv, name equal to the r0001 name at its match.json source (carried) vs own:")
    for (cls, kind, how), k in sorted(split.items()):
        print("    %-10s %-7s %-14s %6d" % (cls, kind, how, k))
    moved = [(hex(a), r["Name"], hex(by_b[a][0])) for r in r4 for a in [int(r["Start"], 16)]
             if a in by_b and by_b[a][1]["name"] == r["Name"] and by_b[a][0] != a]
    print("  r0004 rows whose carried-equal name came from a DIFFERENT r0001 address: %d %s"
          % (len(moved), [x for x in moved if not x[1].startswith("FUN_")][:20]))

    # ---- [2] -----------------------------------------------------------------------------------
    print("[2] sub_")
    for label, rows in ((CSV1, r1), (CSV4, r4)):
        print("  %s: names starting sub_ %d, containing sub_/SUB_ %d"
              % (label, sum(r["Name"].startswith("sub_") for r in rows),
                 sum("sub_" in r["Name"].lower() for r in rows)))
    for d in SRC_DIRS:
        hits = []
        for root, _dirs, files in os.walk(d):
            for f in files:
                if not f.endswith((".cpp", ".h", ".hpp", ".c")) or "sce_symbol_database_data" in f:
                    continue
                p = os.path.join(root, f)
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for i, ln in enumerate(fh, 1):
                        if '"sub_' in ln:
                            hits.append("%s:%d" % (p, i))
        print("  literal \"sub_ in %s (excluding the SDK signature database): %s" % (d, hits))
    for path, rows in zip(EXTRA, (r1, r4)):
        have = {int(r["Start"], 16) for r in rows}
        addrs, commented = [], 0
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        for ln in lines:
            if "#" in ln:
                commented += 1
            s = ln.split("#")[0].strip()
            if s:
                addrs.append(int(s, 16))
        print("  %s: %d lines, %d addresses (%d distinct), %d with a # note; already a row of %s: %d; "
              "fix_ghidra_csv would add as FUN_ rows: %d"
              % (path, len(lines), len(addrs), len(set(addrs)), commented, os.path.basename(
                  CSV1 if rows is r1 else CSV4), sum(a in have for a in set(addrs)),
                 sum(a not in have for a in set(addrs))))

    # a non-auto name makes its row's range authoritative to the recompiler, which then drops any start
    # inside it (elf_parser.cpp addOrMerge); how many rows hold another row's start, and how many of the 485
    import bisect
    spans = sorted((int(r["Start"], 16), int(r["End"], 16)) for r in r1)
    starts = [a for a, _e in spans]
    holders = {a: bisect.bisect_left(starts, e) - bisect.bisect_right(starts, a) for a, e in spans}
    prop_addrs = {p[0] for p in proposals()}
    print("  %s rows whose [Start,End) holds another row's Start: %d; of the 485 proposal rows: %d"
          % (CSV1, sum(1 for v in holders.values() if v > 0), sum(1 for a in prop_addrs if holders.get(a, 0) > 0)))

    # ---- [3] -----------------------------------------------------------------------------------
    hand = [r for r in r1 if not (r["Name"].startswith("FUN_") or r["Name"].startswith("thunk_FUN_"))]
    dates = {}
    if use_git:
        print("[3] git history of the %d hand-named rows' %d distinct names (oldest commit touching each)"
              % (len(hand), len({r["Name"] for r in hand})))
        by_commit = collections.defaultdict(list)
        disagree = []
        for n in sorted({r["Name"] for r in hand}):
            s = oldest(["-S" + n])
            g = oldest(["-G^" + re.escape(n) + ",0x"])
            if (s or "").split(" ")[0] != (g or "").split(" ")[0]:
                disagree.append((n, s, g))
            dates[n] = (g or s).split(" ")[1]
            by_commit[g or s].append(n)
        for c, names in sorted(by_commit.items(), key=lambda kv: kv[0].split(" ")[1]):
            print("  %s\n    %d names: %s" % (c, len(names), " ".join(names)))
        print("  -S and -G disagree on the oldest commit for: %s" % (disagree or "none"))
        later = {}
        for n in sorted({r["Name"] for r in hand}):
            hs = git("log", "--format=%h", "-G^" + re.escape(n) + ",0x", "--", CSV1).split()
            if len(hs) > 1:
                later[n] = hs[:-1]
        print("  names whose lines a LATER commit also touched (-G): %d %s" % (len(later), later))
        print("  date distribution: %s" % dict(collections.Counter(
            dates[r["Name"]] for r in hand)))

    if os.path.exists(ELF):
        import struct
        with open(ELF, "rb") as fh:
            data = fh.read()
        phoff, = struct.unpack_from("<I", data, 0x1C)
        phentsize, phnum = struct.unpack_from("<HH", data, 0x2A)
        segs = []
        for i in range(phnum):
            p_type, off, va, _pa, fsz = struct.unpack_from("<5I", data, phoff + i * phentsize)
            if p_type == 1:
                segs.append((va, off, fsz))

        def word(a):
            for va, off, fsz in segs:
                if va <= a < va + fsz:
                    return struct.unpack_from("<I", data, off + a - va)[0]
            return None
        named = [r for r in r1 if not AUTO_PROPOSED.match(r["Name"])]
        shape, rfu, rfu_ok = 0, 0, 0
        for r in named:
            a = int(r["Start"], 16)
            w0, w1 = word(a), word(a + 4)
            if w0 is None or w1 is None:
                continue
            if (w0 >> 16) == 0x2403 and (w1 & 0xFC00003F) == 0x0C and r["Size"] == "16":
                shape += 1
                num = struct.unpack("<h", struct.pack("<H", w0 & 0xFFFF))[0]
                mm = re.match(r"RFU(\d{3})", r["Name"])
                if mm:
                    rfu += 1
                    rfu_ok += int(mm.group(1)) == num
        print("[3b] %s: of the %d non-auto rows, %d are 16-byte `li v1,<n>; syscall` stubs; "
              "of the RFUnnn ones, %d of %d load the number their name carries (counts only, no bytes)"
              % (ELF, len(named), shape, rfu_ok, rfu))

    # ---- [4] -----------------------------------------------------------------------------------
    print("[4] is_addressy (8-hex run) and the leak check's opaque-token rule")
    from tools_py.release.leakrules import opaque_matches
    props = proposals()
    mangled = [p[1] for p in props]
    rd = [readable(x) for x in mangled]
    rdc = collections.Counter(rd)
    applied = [readable(x) + ("_" + arg_suffix(x) if rdc[readable(x)] > 1 and arg_suffix(x) else "")
               for x in mangled]
    suffixed_all = [readable(x) + ("_" + arg_suffix(x) if arg_suffix(x) else "") for x in mangled]
    toml_names = [n for n, _a in re.findall(r'"([^"@]+)@0x([0-9A-Fa-f]+)"', open(TOML).read())]
    hand_names = [r["Name"] for r in hand]
    nonauto_names = [r["Name"] for r in r1 if not spec_auto(r["Name"])]
    for label, names in (("485 proposals, mangled (the Proposed column)", mangled),
                         ("485 proposals, readable()", rd),
                         ("485 proposals, readable() + suffix where it collides (spec 1.2 rule 2)", applied),
                         ("485 proposals, readable() + suffix on every row (worst case)", suffixed_all),
                         ("656 toml names", toml_names),
                         ("113 hand-named rows (research/44)", hand_names),
                         ("non-auto rows under spec 1.3", nonauto_names)):
        hits = sorted({n for n in names if ADDRESSY.search(n)})
        opq = sorted({n for n in names if any(True for _ in opaque_matches(n))})
        auto = sorted({n for n in names if AUTO_PROPOSED.match(n)})
        print("  %-72s %4d names: addressy %d %s; proposed-auto %d %s; opaque-token %d %s"
              % (label, len(names), len(hits), hits[:12], len(auto), auto[:3], len(opq), opq[:6]))
    collide_hand = sorted(set(applied) & set(r["Name"] for r in r1 if not spec_auto(r["Name"])))
    collide_toml = sorted(set(applied) & set(toml_names))
    print("  applied readable names equal to a csv non-auto name: %d %s; equal to a toml name: %d"
          % (len(collide_hand), collide_hand, len(collide_toml)))
    tv_auto = ("FUN_00408c58", "LAB_001e7040", "caseD_004c5380", "thunk_FUN_00180008", "SUB_00421998")
    tv_real = ("entry", "SetGsCrt", "_Exit", "CreateThread", "AddDmacHandler", "RFU116")
    print("  tools_py/tests/test_carry_names.py IsAddressy vectors under ADDRESS_NAME: auto %d/5, real %d/6 not auto"
          % (sum(bool(ADDRESS_NAME.match(n)) for n in tv_auto), sum(not ADDRESS_NAME.match(n) for n in tv_real)))
    print("  readable collisions inside the 485 (suffix needed): %s"
          % sorted(k for k, v in rdc.items() if v > 1))
    if os.path.exists(DEMO):
        from tools_py.elf_symbols import read_elf
        dn = [n for _s, _e, n in read_elf(DEMO).functions]
        drd = [readable(n) for n in dn]
        dc = collections.Counter(drd)
        dap = [x + ("_" + arg_suffix(n) if dc[x] > 1 and arg_suffix(n) else "") for n, x in zip(dn, drd)]
        for label, names in (("demo .symtab, mangled", dn), ("demo .symtab, readable() + suffix where it collides", dap)):
            hits = [n for n in names if ADDRESSY.search(n)]
            opq = [n for n in names if any(True for _ in opaque_matches(n))]
            print("  %-72s %4d names: addressy %d %s; proposed-auto %d; opaque-token %d"
                  % (label, len(names), len(hits), hits[:10] if names is dap else "",
                     sum(bool(AUTO_PROPOSED.match(n)) for n in names), len(opq)))

    # ---- [5] -----------------------------------------------------------------------------------
    print("[5] the 485 proposals against game/r0004/match.json")
    hows = collections.Counter()
    unresolved = []
    for (addr, mg, ps, _sc, _ev, _src) in props:
        v = m.get("0x%08x" % addr)
        how = v["how"] if v else "absent from match.json"
        hows[(ps, how)] += 1
        if how == "unresolved":
            unresolved.append((addr, readable(mg), "%s %s" % (ps, _sc)))
    tot = collections.Counter()
    for (ps, how), k in sorted(hows.items()):
        tot[how] += k
        print("    pass %-14s how %-22s %4d" % (ps, how, k))
    print("  by how: %s" % dict(tot))
    # carry_names itself, run on a copy of the r0004 rows with the 485 readable names in match.json's `name`
    from tools_py import carry_names as cn
    applied_at = {}
    for (addr, mg, _ps, _sc, _ev, _src) in props:
        x = readable(mg)
        applied_at["0x%08x" % addr] = x + ("_" + arg_suffix(mg) if rdc[x] > 1 and arg_suffix(mg) else "")
    sim = {a: dict(v, name=applied_at.get(a, v["name"])) for a, v in m.items()}
    rows_copy = [dict(r) for r in r4]
    before = {r["Start"]: r["Name"] for r in rows_copy}
    counts = cn.carry(sim, rows_copy)
    landed = {r["Name"] for r in rows_copy if before[r["Start"]] != r["Name"]}
    reached = sorted(set(applied_at.values()) & {r["Name"] for r in rows_copy})
    print("  carry_names.carry over a copy of the r0004 rows with the readable names in place: %s; "
          "readable names now in the copy: %d of %d; newly written rows %d"
          % (counts, len(reached), len(applied_at), len(landed)))
    placed_not_reached = sorted(n for a, n in applied_at.items()
                                if m.get(a, {}).get("b") and n not in reached)
    print("  placed but not written: %s" % placed_not_reached)
    saved = cn.is_addressy
    try:
        cn.is_addressy = lambda n: bool(ADDRESS_NAME.match(n))
        rows_copy = [dict(r) for r in r4]
        counts2 = cn.carry(sim, rows_copy)
    finally:
        cn.is_addressy = saved
    reached2 = set(applied_at.values()) & {r["Name"] for r in rows_copy}
    print("  the same with is_addressy replaced by the proposed anchored ADDRESS_NAME: %s; readable names in the copy: %d"
          % (counts2, len(reached2)))
    engine = [n for a, n, ps in unresolved if re.match(r"C[A-Z0-9]\w*_|zdb_|ai_", n)]
    print("  unresolved: %d; of them class methods (C*/zdb_/ai_ class path): %d" % (len(unresolved), len(engine)))
    for a, n, ps in unresolved:
        print("    0x%08x %-26s %s" % (a, n, ps))

    # ---- [6] -----------------------------------------------------------------------------------
    print("[6] the files beside")
    for p in (CSV1, CSV4):
        with open(p, encoding="utf-8") as fh:
            first = fh.readline().rstrip("\n")
        print("  %s header %r; any '#' line: %s; any quoted field: %s; any comma in a Name: %s"
              % (p, first, any(ln.startswith("#") for ln in open(p)), any('"' in ln for ln in open(p)),
                 any(len(ln.rstrip("\n").split(",")) != 4 for ln in open(p))))
    print("  names in the 485 containing a comma or a quote: %d"
          % sum(("," in x or '"' in x) for x in mangled + applied))

    # ---- [7] -----------------------------------------------------------------------------------
    sidecar = "recomp/socom2_names.csv"
    print("[7] the audit prototype: every non-auto Name needs a sidecar row (sidecar present: %s)"
          % os.path.exists(sidecar))
    first_commit = oldest(["--diff-filter=A"]) if use_git else None
    since = first_commit.split(" ")[0] if first_commit else "?"
    evidence = {
        "EE kernel syscall": "EE kernel syscall stub, 16 B (li v1 + syscall); the Ghidra export's name, in the csv since %s",
        "EE kernel syscall, SIF": "EE kernel syscall stub (SIF), 16 B (li v1 + syscall); the Ghidra export's name, in the csv since %s",
        "EE kernel syscall, reserved slot (RFUnnn)": "EE kernel syscall stub, reserved slot, 16 B; the number in the name is the one it loads; the Ghidra export's name, in the csv since %s",
    }
    backfill = []
    for r in r1:
        if AUTO_PROPOSED.match(r["Name"]):
            continue
        n = r["Name"]
        backfill.append(("0x%08x" % int(r["Start"], 16), n, "", "ghidra", "1.00", evidence[group_other(n)] % since,
                         "scripts/ghidra_export_functions.sh; research/48 [3]", dates.get(n, "")))
    print("  non-auto rows under spec 1.3's literal prefix list: %d; under the proposed anchored rule: %d "
          "(spec 1.3 says 113)" % (sum(not spec_auto(r["Name"]) for r in r1), len(backfill)))
    print("  rows the backfill must write: %d" % len(backfill))
    print("  Address,Name,Mangled,Pass,Score,Evidence,Source,Date")
    show = backfill if all_rows else backfill[:3] + [None] + backfill[-3:]
    w = csv.writer(sys.stdout, lineterminator="\n")
    for b in show:
        if b is None:
            print("  ...")
        else:
            sys.stdout.write("  ")
            w.writerow(b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
