"""Research/46 (Sprint 12 research wave, question 1): who reads a function name or a raw guest offset,
and what a rename of `recomp/socom2_ghidra.csv`'s Name column would change in each of them.

Run from the repo root:  python tools_py/research/symbols/name_consumers.py [--section S] [--list]

Read-only over its inputs; writes nothing. It prints counts, names, addresses and file:line only --
never a byte of the game. Sections (all by default):

  toml        the keys of recomp/socom2.toml, their entry counts, and which of them ps2xRecomp's
              config loader (config_manager.cpp) reads at all.
  sanitise    both copies of the recompiler's identifier sanitiser, replicated from the C++ (the one
              ps2_recompiler.cpp uses for every generated name, and code_generator.cpp's variant),
              applied to the csv's 14,879 names, to the 485 proposals' Proposed names and to the 485
              readable(Mangled) names: how many each ALTERS and by which rule; how many generated
              identifiers are long enough that the output FILENAME is cut (clampFilenameLength, 100).
  behaviour   names that change what the recompiler DOES, not only what it prints: a name the runtime's
              stub list resolves (isStubFunction -> the body is not recompiled), a name equal to a toml
              stub selector's name at another address, a correctness-critical prefix (__ct__, __sinit_);
              and carry_names' address-embedding rule, merge_ranges.txt, csv-hostile characters.
  model       the recompiler's function list for the r0001 image, replicated in Python from
              ElfParser (ScanJalTargetsFallback + loadGhidraFunctionMap + extractFunctions): which name
              each csv row is emitted under today (csv FUN_, the JAL scan's sub_, or a real name), and
              for the 485 proposal rows whether a rename also changes the function's END (a row emitted
              as sub_ today runs to the next JAL target; a named row is authoritative and runs to the
              csv End). Needs game/disc/socom2_game.elf.
  runtime     replaceFunction call sites in game_overrides_socom2.cpp; socom2_addresses.h's Table fields
              (function / DATA); literal overlay addresses per ps2xRuntime file.
  suffix      readable()'s leftovers (a mangled free-function signature, `__sinit_`) and the spec's default
              overload suffix against carry_names' 8-hex rule over the demo's colliding names.
  offsets     the named struct displacements in the parity tools and runtime headers, the runtime's
              `<ptr> + 0x..` reads, and the player actor vtable's RTTI class name.
  parity      every hex literal in tools_py/parity/verdict_core.py, classified as guest address / struct
              offset / other with its line (--list prints each one).
"""
import argparse
import bisect
import collections
import csv
import os
import re
import struct
import sys
import tomllib

sys.path.insert(0, os.getcwd())  # run from the repo root

R = "third_party/ps2recomp"
CSV = "recomp/socom2_ghidra.csv"
TOML = "recomp/socom2.toml"
EXTRA = "recomp/extra_functions.txt"
MERGE = "recomp/merge_ranges.txt"
RENAMES = "game/demo_symbol_renames.csv"
RENAMES_7B = "game/demo_symbol_renames_7b.csv"
ELF = "game/disc/socom2_game.elf"
CALL_LIST = f"{R}/ps2xRuntime/include/ps2_call_list.h"
CONFIG_CPP = f"{R}/ps2xRecomp/src/lib/config_manager.cpp"
CODEGEN_CPP = f"{R}/ps2xRecomp/src/lib/code_generator.cpp"
OVERRIDES = f"{R}/ps2xRuntime/src/lib/game_overrides_socom2.cpp"
ADDR_H = f"{R}/ps2xRuntime/include/runtime/socom2_addresses.h"
VERDICT = "tools_py/parity/verdict_core.py"

# ---------------------------------------------------------------- readable(), copied from readable_names.py
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
    """'Mul__5CQuatCFPC5CQuatP5CQuat' -> 'CQuat_Mul'; 'sceCdRead' -> 'sceCdRead'. (readable_names.py)"""
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


# ---------------------------------------------------------------- the sanitisers, replicated from the C++
def cxx_keywords():
    """kKeywords, parsed out of code_generator.cpp (the one list both sanitisers use)."""
    src = open(CODEGEN_CPP).read()
    block = re.search(r"kKeywords\s*=\s*\{(.*?)\};", src, re.S).group(1)
    return set(re.findall(r'"([^"]+)"', block))


KEYWORDS = cxx_keywords()


def body(name: str) -> str:
    """sanitizeIdentifierBody: non-[A-Za-z0-9_] -> '_', then '_' before a leading non-alpha non-'_'."""
    s = "".join(c if (c.isascii() and c.isalnum()) or c == "_" else "_" for c in name)
    if s and not (s[0].isascii() and s[0].isalpha()) and s[0] != "_":
        s = "_" + s
    return s


def reserved(s: str) -> bool:
    """isReservedCxxIdentifier: `__x` or `_X` (the C++ files check only the first two characters)."""
    return len(s) >= 2 and s[0] == "_" and (s[1] == "_" or (s[1].isascii() and s[1].isupper()))


def sanitize_recompiler(name: str):
    """PS2Recompiler::sanitizeFunctionName (ps2_recompiler.cpp:2190) -- what every generated name goes
    through (generateOutput's makeName, which then appends `_0x<start>`). Returns (result, None)."""
    s = body(name)
    if not s:
        return s, None
    if s == "main":
        return "ps2_main", None
    if s in KEYWORDS or reserved(s):
        return "ps2_" + s, None
    return s, None


def sanitize_codegen(name: str):
    """CodeGenerator::sanitizeFunctionName (code_generator.cpp:181) -- reached only through getFunctionName
    for an address with no rename entry and an ELF symbol; this image has no symbols. Returns (result, rule)."""
    s = body(name)
    rule = "character map" if s != name else None
    if not s:
        return s, rule
    if s == "main":
        return "ps2_main", "main"
    if s in KEYWORDS:
        return "ps2_" + s, "keyword"
    if s[0] == "_":
        return "ps2" + s, rule or "leading underscore"
    if not reserved(s):
        return s, rule
    return "ps2_" + s, "reserved"


def body_rule(name: str):
    s = body(name)
    if s == name:
        return None
    mapped = "".join(c if (c.isascii() and c.isalnum()) or c == "_" else "_" for c in name)
    return "leading digit" if mapped != s else "character map"


def classify(name: str, fn) -> str:
    """Which rule alters `name` under sanitiser fn, or '' when it is returned unchanged."""
    out, _ = fn(name)
    if out == name:
        return ""
    s = body(name)
    if s != name:
        b = body_rule(name)
        if out != s:
            return b + " + " + ("keyword" if s in KEYWORDS else "reserved/underscore")
        return b
    if s == "main":
        return "main"
    if s in KEYWORDS:
        return "keyword"
    if fn is sanitize_codegen and s[0] == "_":
        return "leading underscore"
    return "reserved (__x / _X)"


# ---------------------------------------------------------------- inputs
def load_csv():
    with open(CSV, newline="") as fh:
        return list(csv.DictReader(fh))


def load_proposals():
    rows = []
    with open(RENAMES, newline="") as fh:
        for r in csv.DictReader(fh):
            rows.append((int(r["Address"], 16), r["Proposed"], r["Mangled"], "t7:" + r["How"]))
    with open(RENAMES_7B, newline="") as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    for r in csv.DictReader(lines):
        rows.append((int(r["Address"], 16), r["Proposed"], r["Mangled"], "t7b:" + r["Source"]))
    return rows


def call_list():
    src = open(CALL_LIST).read()
    sys_block = src[src.index("#define PS2_SYSCALL_LIST"):src.index("#define PS2_STUB_LIST")]
    stub_block = src[src.index("#define PS2_STUB_LIST"):]
    return re.findall(r"X\((\w+)\)", sys_block), re.findall(r"X\((\w+)\)", stub_block)


def resolve(name: str, entries) -> str:
    """ps2_runtime_calls.h resolveNameWithOptionalLeadingUnderscoreAlias."""
    if not name:
        return ""
    if name in entries:
        return name
    if name.startswith("_"):
        return name[1:] if name[1:] in entries else ""
    alias = "_" + name
    return alias if alias in entries else ""


def toml_selectors():
    d = tomllib.load(open(TOML, "rb"))
    out = {}
    for key in ("stubs", "untracked_stubs"):
        sel = []
        for s in d["general"].get(key, []):
            name, _, addr = s.rpartition("@")
            sel.append((name.strip(), int(addr, 16)))
        out[key] = sel
    return d, out


def cp(path, pattern):
    """file:line of every line matching pattern."""
    hits = []
    with open(path, errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if re.search(pattern, line):
                hits.append(i)
    return hits


# ---------------------------------------------------------------- sections
def sec_toml(_args):
    d, sel = toml_selectors()
    print("== toml: recomp/socom2.toml keys and what ps2xRecomp reads")
    g = d["general"]
    for k, v in g.items():
        print(f"  [general].{k:22s} {('list of %d' % len(v)) if isinstance(v, list) else repr(v)}")
    print(f"  [mmio]                        {len(d.get('mmio', {}))} instruction-address keys")
    jt = d.get("jump_tables", {}).get("table", [])
    print(f"  [[jump_tables.table]]         {len(jt)} tables, {sum(len(t.get('entries', [])) for t in jt)} entries "
          f"({len({t['address'] for t in jt})} distinct table addresses)")
    print(f"  [patches].instructions        {len(d.get('patches', {}).get('instructions', []))}")
    crit = d.get("performance", {}).get("critical", [])
    print(f"  [performance].critical        {len(crit)} names "
          f"({sum(1 for n in crit if n.startswith('sub_'))} sub_*, {sum(1 for n in crit if not n.startswith('sub_'))} other)")
    src = open(CONFIG_CPP).read()
    load = src[src.index("loadConfig()"):src.index("return config;")]
    read = sorted(set(re.findall(r'"([a-z_0-9]+)"', load)))
    print("  keys config_manager.cpp::loadConfig names:", ", ".join(read))
    present = set(g) | {k for k in d if k != "general"}
    for k in sorted(present):
        print(f"    {k:22s} {'READ' if k in read else 'NOT READ by ps2xRecomp'}")
    print(f"  stub selectors: stubs {len(sel['stubs'])}, untracked_stubs {len(sel['untracked_stubs'])}, "
          f"total {len(sel['stubs']) + len(sel['untracked_stubs'])}")
    ex = [ln.split("#")[0].strip() for ln in open(EXTRA)]
    ex = [int(a, 16) for a in ex if a]
    starts = {int(r["Start"], 16) for r in load_csv()}
    print(f"  recomp/extra_functions.txt: {len(ex)} bare addresses, {sum(a in starts for a in ex)} already csv "
          f"rows (fix_ghidra_csv.py adds a missing one as FUN_<addr>)")


def sec_sanitise(_args):
    rows = load_csv()
    props = load_proposals()
    print("== sanitise: what the recompiler's identifier sanitisers do to each name set")
    print(f"  kKeywords parsed from code_generator.cpp: {len(KEYWORDS)}")
    sets = [
        ("csv Name (%d)" % len(rows), [(int(r["Start"], 16), r["Name"]) for r in rows]),
        ("proposals Proposed (%d)" % len(props), [(a, p) for a, p, _m, _h in props]),
        ("proposals Mangled (%d)" % len(props), [(a, m) for a, _p, m, _h in props]),
        ("proposals readable(Mangled) (%d)" % len(props), [(a, readable(m)) for a, _p, m, _h in props]),
    ]
    for label, names in sets:
        for fname, fn in (("PS2Recompiler (effective)", sanitize_recompiler), ("CodeGenerator (variant)", sanitize_codegen)):
            c = collections.Counter(classify(n, fn) for _a, n in names)
            altered = sum(v for k, v in c.items() if k)
            detail = ", ".join(f"{k} {v}" for k, v in sorted(c.items()) if k)
            print(f"  {label:36s} {fname:26s} altered {altered:5d}  [{detail}]")
        long_ = [(a, n) for a, n in names
                 if len(sanitize_recompiler(n)[0] + "_0x%x" % a) + len(".cpp") > 100]
        print(f"  {label:36s} identifier+'.cpp' over 100 chars (filename cut, identifier kept): {len(long_)}"
              + (f"; longest name {max(len(n) for _a, n in long_)}" if long_ else ""))
        ids = collections.Counter(sanitize_recompiler(n)[0] for _a, n in names)
        dup = {k: v for k, v in ids.items() if v > 1}
        print(f"  {label:36s} sanitised spellings shared by >1 row: {len(dup)} names over {sum(dup.values())} rows "
              f"(the _0x<start> suffix keeps every identifier unique)")
    if _args.list:
        for label, names in sets[1:]:
            for a, n in names:
                k = classify(n, sanitize_recompiler)
                if k:
                    print(f"    {label}: 0x{a:08x} {n} -> {sanitize_recompiler(n)[0]}  ({k})")


def sec_behaviour(_args):
    rows = load_csv()
    props = load_proposals()
    syscalls, stubs = call_list()
    _d, sel = toml_selectors()
    sel_names = collections.defaultdict(set)
    for n, a in sel["stubs"]:
        sel_names[n].add(a)
    print("== behaviour: names that change what the recompiler does")
    print(f"  ps2_call_list.h: {len(syscalls)} syscall names, {len(stubs)} stub names")
    resolved = sum(1 for n, _a in sel["stubs"] if resolve(n, syscalls) or resolve(n, stubs))
    print(f"  toml stubs whose selector name resolves to a runtime handler: {resolved} of {len(sel['stubs'])}"
          f" (the rest emit ps2_stubs::TODO_NAMED)")
    csv_at = {int(r["Start"], 16): r["Name"] for r in rows}
    agree = sum(1 for n, a in sel["stubs"] + sel["untracked_stubs"] if csv_at.get(a) == n)
    absent = sum(1 for _n, a in sel["stubs"] + sel["untracked_stubs"] if a not in csv_at)
    print(f"  toml selectors (656) whose csv row at that address carries the same Name: {agree}; "
          f"address not a csv Start: {absent} (stubs {sum(1 for _n, a in sel['stubs'] if a not in csv_at)}, "
          f"untracked {sum(1 for _n, a in sel['untracked_stubs'] if a not in csv_at)})")
    stub_starts = {a for _n, a in sel["stubs"]}
    crit = ("__ct__", "__sinit_", "_GLOBAL__sub_I_", "GLOBAL__sub_I_",
            "__static_initialization_and_destruction_0", "__do_global_ctors")
    sets = [
        ("csv Name", [(int(r["Start"], 16), r["Name"]) for r in rows]),
        ("proposals Proposed", [(a, p) for a, p, _m, _h in props]),
        ("proposals readable", [(a, readable(m)) for a, _p, m, _h in props]),
    ]
    addressy = re.compile(r"[0-9A-Fa-f]{8}")
    merges = []
    for ln in open(MERGE):
        ln = ln.split("#")[0].strip()
        if ln:
            lo, hi = (int(x, 16) for x in ln.split())
            merges.append((lo, hi))
    for label, names in sets:
        stubhit = [(a, n) for a, n in names if resolve(n, stubs)]
        newstub = [(a, n) for a, n in stubhit + [(a, n) for a, n in names if n in sel_names]
                   if a not in stub_starts]
        newstub = sorted(set(newstub))
        syshit = [(a, n) for a, n in names if resolve(n, syscalls) and not resolve(n, stubs)]
        selhit = [(a, n) for a, n in names if n in sel_names and a not in sel_names[n]]
        selsame = [(a, n) for a, n in names if n in sel_names and a in sel_names[n]]
        crithit = [(a, n) for a, n in names if n.startswith(crit)]
        addr = [(a, n) for a, n in names if addressy.search(n)]
        hostile = [(a, n) for a, n in names if re.search(r'[,"\s@]', n)]
        inmerge = [(a, n) for a, n in names if any(lo < a < hi for lo, hi in merges)]
        print(f"  {label:20s} names {len(names):5d} | stub-list name (isStubFunction -> stubbed): {len(stubhit):3d}"
              f" | syscall-only name: {len(syshit)} | = a toml stub selector name at ANOTHER address: {len(selhit)}"
              f" (at the same address: {len(selsame)}) | correctness-critical prefix: {len(crithit)}"
              f" | 8-hex run (carry_names will not carry): {len(addr)} | csv-hostile char: {len(hostile)}"
              f" | inside a merge range: {len(inmerge)}"
              f" | NEWLY stubbed by name (address not a [general].stubs selector): {len(newstub)}")
        if _args.list and label != "csv Name":
            for tag, lst in (("newly-stubbed", newstub), ("stub-list", stubhit), ("other-address selector", selhit), ("critical", crithit),
                             ("8-hex", addr)):
                for a, n in lst:
                    print(f"      {tag}: 0x{a:08x} {n}")
        if label == "csv Name" and stubhit:
            print("      csv rows already stubbed by name:", ", ".join(f"{n}@0x{a:x}" for a, n in stubhit[:12]))


def sec_suffix(args):
    """The spec's default overload suffix (1.2 rule 2: the mangled argument list after the F, sanitised, cut to 24)
    against carry_names' 8-hex rule, over the demo's colliding readable names; and what readable() leaves as is."""
    props = load_proposals()
    rd = [readable(m) for _a, _p, m, _h in props]
    print("== suffix: readable() leftovers and the overload suffix against carry_names.py:32")
    print(f"  485 readable names still holding a mangled free-function signature '__F': "
          f"{sum(1 for r in rd if '__F' in r)}; still starting '__sinit_': {sum(1 for r in rd if r.startswith('__sinit_'))}")
    demo = "game/demo_scus_972_05/SCUS_972.05"
    if not os.path.isfile(demo):
        print(f"  {demo} absent -- the demo-wide half skipped")
        return
    from tools_py.elf_symbols import read_elf
    names = [n for _s, _e, n in read_elf(demo).functions]

    def suffix(m):
        i = m.find("__")
        j = m.find("F", i + 2) if i >= 0 else -1
        return re.sub(r"[^A-Za-z0-9_]", "_", m[j + 1:])[:24] if j >= 0 else ""
    cnt = collections.Counter(readable(n) for n in names)
    coll = [n for n in names if cnt[readable(n)] > 1]
    hexy = [n for n in coll if re.search(r"[0-9A-Fa-f]{8}", readable(n) + "_" + suffix(n))]
    print(f"  demo functions whose readable name collides: {len(coll)}; of those, readable+'_'+suffix holding an "
          f"8-hex run (carry_names would withhold it): {len(hexy)}: {', '.join(hexy)}")


def read_segments(path):
    d = open(path, "rb").read()
    phoff = struct.unpack_from("<I", d, 0x1C)[0]
    phnum = struct.unpack_from("<H", d, 0x2C)[0]
    entry = struct.unpack_from("<I", d, 0x18)[0]
    segs = []
    for i in range(phnum):
        t, off, va, _pa, fsz, _msz, fl, _al = struct.unpack_from("<IIIIIIII", d, phoff + i * 32)
        if t == 1 and fsz:
            segs.append((va, fsz, bool(fl & 1), d[off:off + fsz]))
    return entry, sorted(segs)


def is_auto(n):
    return n.startswith(("sub_", "FUN_", "LAB_", "DAT_"))


def model(rows, rename=None):
    """ElfParser's function list for this image: {start: (name, end)}. `rename` = {start: new name}."""
    entry, segs = read_segments(ELF)
    code = [(va, va + fsz) for va, fsz, x, _b in segs if x]

    def code_sec(a):
        for lo, hi in code:
            if lo <= a < hi:
                return (lo, hi)
        return None
    # ScanJalTargetsFallback (the image has no DWARF, so m_extraFunctions starts as this list)
    starts = {entry} if code_sec(entry) else set()
    for va, fsz, x, b in segs:
        if not x:
            continue
        words = struct.unpack_from("<%dI" % (fsz // 4), b)
        for i, w in enumerate(words):
            if (w >> 26) == 0x03:
                pc = va + 4 * i
                t = ((pc + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
                if code_sec(t):
                    starts.add(t)
    ss = sorted(starts)
    jal = {}
    for i, s in enumerate(ss):
        _lo, hi = code_sec(s)
        nxt = ss[i + 1] if i + 1 < len(ss) and ss[i + 1] < hi else hi
        jal[s] = ("sub_%08X" % s, nxt if nxt > s else s + 4)
    # loadGhidraFunctionMap
    extras = []
    mapstarts = set()
    for r in rows:
        s, e = int(r["Start"], 16), int(r["End"], 16)
        sec = code_sec(s)
        if not sec:
            continue
        e = sec[1] if (e == 0 or e > sec[1]) else e
        if e <= s:
            continue
        n = (rename or {}).get(s, r["Name"])
        extras.append((s, e, n, "csv"))
        mapstarts.add(s)
    extras += [(s, e, n, "jal") for s, (n, e) in jal.items() if s in mapstarts]
    extras.sort(key=lambda f: (f[0], is_auto(f[2]), -f[1], f[2]))
    uniq = {}
    for f in extras:
        uniq.setdefault(f[0], f)
    # extractFunctions (no ELF symbols in this image)
    auth = sorted((f[0], f[1]) for f in uniq.values() if not is_auto(f[2]))
    astarts = [s for s, _e in auth]
    authset = {s for s, _e in auth}

    def inside(a):
        i = bisect.bisect_right(astarts, a) - 1
        return i >= 0 and auth[i][0] < a < auth[i][1]
    out = {}
    dropped = []
    for s, f in sorted(uniq.items()):
        if inside(s) and (s not in authset or is_auto(f[2])):
            dropped.append(s)
            continue
        out[s] = (f[2], f[1], f[3])
    return out, dropped, len(ss)


def sec_model(args):
    if not os.path.isfile(ELF):
        print(f"== model: {ELF} absent -- skipped")
        return
    rows = load_csv()
    props = load_proposals()
    out, dropped, njal = model(rows)
    kinds = collections.Counter("FUN_" if n.startswith("FUN_") else "sub_" if n.startswith("sub_") else "named"
                                for n, _e, _src in out.values())
    print("== model: ElfParser's function list, replicated (not observed: no recomp/output here)")
    print(f"  JAL-scan starts {njal}; functions {len(out)}; dropped inside a named row's range {len(dropped)}")
    print(f"  emitted name today: {dict(kinds)}")
    named = [n for n, _e, _src in out.values() if not is_auto(n)]
    print(f"  of the named: thunk_* {sum(1 for n in named if n.startswith('thunk_'))}, "
          f"caseD_* {sum(1 for n in named if n.startswith('caseD_'))}, "
          f"other {sum(1 for n in named if not n.startswith(('thunk_', 'caseD_')))}")
    csv_end = {int(r["Start"], 16): int(r["End"], 16) for r in rows}
    wide = [s for s, (n, e, _src) in out.items() if n.startswith("sub_") and e - csv_end[s] > 16]
    print(f"  rows emitted as sub_ whose decoded range runs more than 16 bytes past the csv End: {len(wide)}")
    ren = {a: readable(m) for a, _p, m, _h in props}
    out2, dropped2, _ = model(rows, ren)
    now_sub = [a for a in ren if a in out and out[a][0].startswith("sub_")]
    now_fun = [a for a in ren if a in out and out[a][0].startswith("FUN_")]
    end_changes = [a for a in ren if a in out and a in out2 and out[a][1] != out2[a][1]]
    print(f"  the 485 proposal rows today: emitted as sub_ {len(now_sub)}, as FUN_ {len(now_fun)}, "
          f"absent {sum(1 for a in ren if a not in out)}")
    print(f"  after the rename: rows whose END changes (sub_ today -> csv End) {len(end_changes)}; "
          f"functions newly dropped inside a renamed row {len(set(dropped2) - set(dropped))}; "
          f"function count {len(out)} -> {len(out2)}")
    if end_changes:
        grow = [out[a][1] - out2[a][1] for a in end_changes]
        print(f"  bytes the END moves in by: min {min(grow)}, median {sorted(grow)[len(grow) // 2]}, max {max(grow)}; "
              f"by 4/8/12/16: {sum(g == 4 for g in grow)}/{sum(g == 8 for g in grow)}/{sum(g == 12 for g in grow)}/"
              f"{sum(g == 16 for g in grow)}, by more than 16: {sum(g > 16 for g in grow)}")
        big = max(end_changes, key=lambda a: out[a][1] - out2[a][1])
        print(f"  the largest: 0x{big:08x} {ren[big]} ({out[big][0]} today)")
    tsel = toml_selectors()[1]["stubs"]
    tstub = {a for _n, a in tsel}
    print(f"  toml [general].stubs addresses emitted today as sub_: "
          f"{sum(1 for a in tstub if a in out and out[a][0].startswith('sub_'))} of {len(tstub)} "
          f"(FUN_ {sum(1 for a in tstub if a in out and out[a][0].startswith('FUN_'))}, "
          f"named {sum(1 for a in tstub if a in out and not is_auto(out[a][0]))}, absent {sum(1 for a in tstub if a not in out)})")
    print("  the absent ones (no function starts there, so the selector binds nothing):",
          ", ".join(f"{n}@0x{a:x}" for n, a in tsel if a not in out))
    if args.list:
        for a in sorted(end_changes):
            print(f"    end change 0x{a:08x} {ren[a]}: {out[a][0]} [..0x{out[a][1]:x}) -> [..0x{out2[a][1]:x})")


def sec_runtime(_args):
    print("== runtime")
    sites = cp(OVERRIDES, r"replaceFunction\(")
    print(f"  replaceFunction( call sites in game_overrides_socom2.cpp: {len(sites)} at lines {sites}")
    bah = cp(OVERRIDES, r"bindAddressHandler\(")
    print(f"  bindAddressHandler( (handler chosen by NAME string) in game_overrides_socom2.cpp: lines {bah}")
    src = open(ADDR_H).read()
    struct_body = src[src.index("struct Table"):src.index("inline constexpr Table kR0001")]
    fields = re.findall(r"uint32_t\s+(\w+);\s*(//[^\n]*)?", struct_body)
    data = [f for f, c in fields if "DATA" in (c or "")] + ["ctorTableFtsEnd", "ctorTableZsealEnd"]
    data = sorted(set(data))
    print(f"  socom2_addresses.h Table fields: {len(fields)}; DATA {len(data)} ({', '.join(data)}); "
          f"functions {len(fields) - len(data)}")
    counts = collections.Counter()
    base = f"{R}/ps2xRuntime"
    for dp, _dn, fns in os.walk(base):
        for fn in fns:
            if not fn.endswith((".cpp", ".h", ".inl")):
                continue
            p = os.path.join(dp, fn)
            for i, line in enumerate(open(p, errors="replace"), 1):
                code = line.split("//")[0]
                for m in re.finditer(r"\b0[xX]([0-9A-Fa-f]{5,8})u?\b", code):
                    v = int(m.group(1), 16)
                    if 0x001D5600 <= v < 0x00700000:
                        counts[os.path.relpath(p, base)] += 1
    print("  overlay-range literals (0x1d5600..0x700000, outside // comments) per ps2xRuntime file:")
    for k, v in counts.most_common():
        print(f"    {v:4d}  {k}")
    kinds = collections.Counter()
    for sub in ("src", "include"):
        for dp, _dn, fns in os.walk(os.path.join(base, sub)):
            for fn in fns:
                if not fn.endswith((".cpp", ".h")):
                    continue
                for line in open(os.path.join(dp, fn), errors="replace"):
                    code = line.split("//")[0]
                    for m in re.finditer(r"\b(?:thunk_FUN|FUN|sub|DAT|LAB)_[0-9a-fA-F]{8}\b", line):
                        if m.start() >= len(code) or line.lstrip().startswith(("*", "/*")):
                            kinds["comment"] += 1
                        elif code.count('"', 0, m.start()) % 2 == 1:
                            kinds["string literal"] += 1
                        else:
                            kinds["code"] += 1
    print(f"  address-derived names (FUN_/sub_/DAT_/LAB_/thunk_FUN_ + 8 hex) in ps2xRuntime src+include: {dict(kinds)}")
    props = {a: readable(m) for a, _p, m, _h in load_proposals()}
    cites = collections.defaultdict(list)
    for root in (f"{base}/src", f"{base}/include", "tools_py"):
        for dp, _dn, fns in os.walk(root):
            if "/tests" in dp or "/research" in dp:
                continue
            for fn in fns:
                if not fn.endswith((".cpp", ".h", ".py")):
                    continue
                path = os.path.join(dp, fn)
                for i, line in enumerate(open(path, errors="replace"), 1):
                    for m in re.finditer(r"\b(?:thunk_FUN|FUN|sub)_([0-9a-fA-F]{8})\b", line):
                        if int(m.group(1), 16) in props:
                            cites[path].append(i)
    print(f"  FUN_/sub_ citations of a proposal address in ps2xRuntime + tools_py (no tests, no research): "
          f"{sum(len(v) for v in cites.values())} in {len(cites)} files:",
          "; ".join(f"{k.replace(base + '/', '')}:{','.join(map(str, v))}" for k, v in sorted(cites.items())))
    from tools_py.addresses_from_match import FIELDS
    on_table = [(f.name, f.a, props[f.a]) for f in FIELDS if f.a in props]
    print(f"  proposals on a socom2_addresses.h r0001 address: {len(on_table)}",
          ", ".join(f"{n} 0x{a:x} -> {r}" for n, a, r in on_table))
    loader = [(a, props[a]) for a in (0x1C59C0, 0x1C5B30, 0x181C90, 0x1A6110, 0x1BCD80, 0x1BD050, 0x1BD320,
                                        0x1BD200, 0x1AC9D8) if a in props]
    print(f"  proposals on a literal loader replaceFunction/bindAddressHandler address: {len(loader)}",
          ", ".join(f"0x{a:x} -> {r}" for a, r in loader))


def sec_parity(args):
    print("== parity: hex literals in", VERDICT)
    occ = []
    for i, line in enumerate(open(VERDICT), 1):
        for m in re.finditer(r"0[xX][0-9a-fA-F]+", line):
            occ.append((i, m.group(0), m.start(), line))
    lines = {i for i, *_ in occ}
    print(f"  lines with a hex literal {len(lines)}; occurrences {len(occ)}; "
          f"distinct values {len({int(t, 16) for _i, t, _p, _l in occ})}")
    cls = collections.Counter()
    listed = []
    for i, tok, pos, line in occ:
        v = int(tok, 16)
        before = line[:pos].rstrip()
        if 0x00100000 <= v < 0x02000000:
            k = "address"
        elif before.endswith("+") or re.search(r"_OFFSET\s*=\s*$|_WORD\s*=\s*$", before) or \
                re.search(r"(ng|actor|mgr|def)\+$", before):
            k = "offset"
        elif re.search(r"\b0x118 // 4", line) and tok == "0x118":
            k = "offset"
        else:
            k = "other"
        cls[k] += 1
        listed.append((k, i, tok))
    print("  by class (occurrences):", dict(cls))
    for k in ("address", "offset"):
        vals = collections.defaultdict(list)
        for kk, i, tok in listed:
            if kk == k:
                vals[int(tok, 16)].append(i)
        print(f"  {k}: {len(vals)} distinct values:",
              "; ".join(f"0x{v:x} @{','.join(map(str, ls))}" for v, ls in sorted(vals.items())))
    if args.list:
        for k, i, tok in listed:
            print(f"    {VERDICT}:{i} {tok} {k}")


OFFSET_FILES = [
    "tools_py/parity/guest_addresses.py", "tools_py/parity/verdict_core.py", "tools_py/parity/sp_death_probe.py",
    "tools_py/parity/verdict_replay.py", "tools_py/parity/online_match_ours.py",
    f"{R}/ps2xRuntime/include/runtime/socom2_chat.h", f"{R}/ps2xRuntime/include/runtime/socom2_osk_prefill.h",
]


def sec_offsets(_args):
    """Named struct displacements (constants and PROBE_OFFSETS rows), and the runtime's `<ptr> + 0x..`
    reads in game_overrides_socom2.cpp, each with file:line."""
    print("== offsets: named struct displacements, file:line")
    named = re.compile(r"^\s*(\w*(?:OFFSET|_OFF|Off|WORDS?)\w*)\s*=\s*(.*)$|"
                       r"constexpr\s+\S+\s+(k\w*Off\w*)\s*=\s*(0[xX][0-9A-Fa-f]+)|"
                       r'^\s*"(\w+)":\s*\{"r0001":\s*(0x[0-9A-Fa-f]+),\s*"r0004":\s*(0x[0-9A-Fa-f]+)\}')
    n = 0
    for path in OFFSET_FILES:
        for i, line in enumerate(open(path), 1):
            m = named.search(line)
            if not m or "re.compile" in line or (m.group(1) or "").endswith("_ADDR"):
                continue
            if m.group(5) and "PROBE_ADDRESSES" not in "".join(open(path).readlines()[max(0, i - 8):i]):
                print(f"  {path}:{i}  {m.group(5)} r0001 {m.group(6)} r0004 {m.group(7)}")
                n += 1
            elif m.group(1) and "0x" in (m.group(2) or "") or m.group(3):
                print(f"  {path}:{i}  {line.strip()[:110]}")
                n += 1
    print(f"  named offset lines: {n}")
    disp = re.compile(r"\b(mgr|def|obj|camera|cam|pn|pc|pr|holder|pl|list)\s*\+\s*(0x[0-9a-fA-F]+)u?")
    rows = collections.defaultdict(list)
    for i, line in enumerate(open(OVERRIDES, errors="replace"), 1):
        code = line.split("//")[0]
        for m in disp.finditer(code):
            rows[(m.group(1), int(m.group(2), 16))].append(i)
    if os.path.isfile(ELF):
        from tools_py.elf_symbols import read_elf
        segs = read_elf(ELF).segments

        def word(a):
            for va, b in segs:
                if va <= a and a + 4 <= va + len(b):
                    return struct.unpack_from("<I", b, a - va)[0]
            return None

        def cstr(a):
            for va, b in segs:
                if va <= a < va + len(b):
                    end = b.find(b"\0", a - va, a - va + 64)
                    return b[a - va:end].decode("ascii", "replace") if end > 0 else ""
            return ""
        vt = 0x006691A0   # guest_addresses PROBE_ADDRESSES["actor_vtable"]["r0001"]
        rtti = word(vt)
        name = cstr(word(rtti)) if rtti else ""
        print(f"  actor_vtable r0001 0x{vt:08x}: word 0 -> RTTI object 0x{rtti or 0:08x} -> class name {name!r} "
              f"(Metrowerks [RTTI, 0, slots...] layout, research/symbols README)")
    print(f"  game_overrides_socom2.cpp `<ptr> + 0x..` reads in code (not comments): {len(rows)} distinct (base, offset):")
    for (b, off), ls in sorted(rows.items()):
        print(f"    {b}+0x{off:x} @{','.join(map(str, ls))}")


SECTIONS = {"toml": sec_toml, "offsets": sec_offsets, "suffix": sec_suffix, "sanitise": sec_sanitise, "behaviour": sec_behaviour, "model": sec_model,
            "runtime": sec_runtime, "parity": sec_parity}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--section", choices=sorted(SECTIONS), action="append")
    ap.add_argument("--list", action="store_true", help="also print the per-row / per-literal listing")
    args = ap.parse_args()
    for name in args.section or list(SECTIONS):
        SECTIONS[name](args)


if __name__ == "__main__":
    main()
