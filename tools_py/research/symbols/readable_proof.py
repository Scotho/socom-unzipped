"""The readable-name scheme, proven over four name sets (Sprint 12 research Q2; docs/research/47).

Run from the repo root:  python3 tools_py/research/symbols/readable_proof.py [--list]

Read-only. Inputs: game/demo_scus_972_05/SCUS_972.05 (its .symtab), game/demo_symbol_renames.csv,
game/demo_symbol_renames_7b.csv, recomp/socom2_ghidra.csv, recomp/socom2.toml. Writes nothing and
prints names, addresses and counts only, never a byte of a game image. About three seconds.

The four sets: A = the 485 proposals' Mangled names (479 Task 7 + 6 Task 7b); B = the demo's 9,703
function names; C = the toml's 656 `name@addr` stub names; D = A + C + the csv's 113 rows that are
not FUN_/thunk_FUN_, merged by address (non-auto hand > proposal > toml > auto hand), i.e. the names
that would coexist in recomp/socom2_ghidra.csv.

What it prints, by section (research/47 uses the same numbers):
  0  the sets, D's make-up and the same-address conflicts.
  1  distinct readable names and collisions before any suffix, the peer's sketch (readable() copied
     verbatim from readable_names.py) against the final rendering R1-R8; the rendering variants
     (leading underscores U1/U2/U3, templates kept/dropped, '_' runs collapsed or not).
  2  the overload suffix: (i) the argument list after F, sanitised, cut to 24; (ii) six hex digits
     of SHA-1 of the mangled name; (i)+template tag; the full chain R9. Residual collisions, what
     the residue is, suffix length histogram, three examples each; the cut's and const's share.
  3  lengths after the chain: over 96, over 87 (the recompiler's filename budget), the longest.
  4  what the recompiler's two sanitisers (code_generator.cpp, ps2_recompiler.cpp, replicated
     here) would alter, per rule, for the raw names, the sketch and the final rule.
  5  Windows filename hazards of the final names: device names, trailing dot/space, case-only.
  6  templates: what dropping the arguments costs and what the tag buys.
  7  the special forms in the demo (anonymous namespaces, thunks, __sinit, $ locals, operators,
     conversion operators, Q2/Q3 paths, free functions, plain names) with one rendering each.
  8  the proof over D with the whole rule (R1-R12): collisions, refusals, sanitiser alterations.
`--list` prints every listed item in full instead of the first twelve.
"""
import collections
import csv
import hashlib
import os
import re
import sys

sys.path.insert(0, os.getcwd())  # run from the repo root
from tools_py.elf_symbols import read_elf  # noqa: E402

DEMO = "game/demo_scus_972_05/SCUS_972.05"
RENAMES = "game/demo_symbol_renames.csv"
RENAMES_7B = "game/demo_symbol_renames_7b.csv"
OURS = "recomp/socom2_ghidra.csv"
TOML = "recomp/socom2.toml"

SHOW = None if "--list" in sys.argv else 12

# ============================================================================================
# The peer's sketch, copied verbatim from tools_py/research/symbols/readable_names.py.
# ============================================================================================
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


def sketch_readable(mangled: str) -> str:
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


# ============================================================================================
# The final rule, R1-R12 (research/47 "the recommended rule set"). One function per step.
# ============================================================================================
OPERATORS_FINAL = dict(OPERATORS, __defctor="defctor")          # R4
AUTO = re.compile(r"^(FUN_|LAB_|thunk_FUN_|caseD_|sub_)|^entry$")  # R12, spec 1.3's list
_THUNK = re.compile(r"^@(\d+)@(?:(\d+)@)?")                        # R1
_REST_OK = re.compile(r"F|Q\d|Q_\d+_|\d+")                         # R2
_ANON = re.compile(r"^@unnamed@(.*?)@$")                           # R3
_LOCAL = re.compile(r"^(.*?)\$(\d+)(.*)$")                         # R3, R5
_SINIT = re.compile(r"^__sinit(?:_(.*?))?(?:\.(?:cpp|cp|c))?$")    # R5
_FILE_EXT = re.compile(r"_(?:cpp|cp|c)$")
CUT = 24          # R9 (i)
R9 = ["args|hash", "hash"]
LIMIT = 87        # R11: 100 (clampFilenameLength) - len(".cpp") - len("_0x") - 6 hex digits


def drop_templates(s: str) -> str:
    """Every <...> at any depth removed: 'vector<Ui,Q23std13allocator<Ui>>' -> 'vector'."""
    out, depth = [], 0
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def template_args(s: str) -> str:
    """The first top-level <...> of `s` without its brackets ('' when there is none)."""
    start = s.find("<")
    if start < 0:
        return ""
    depth = 0
    for i in range(start, len(s)):
        depth += {"<": 1, ">": -1}.get(s[i], 0)
        if depth == 0:
            return s[start + 1:i]
    return s[start + 1:]


def type_words(s: str) -> list:
    """The readable words of a mangled type list: length-prefixed names (templates dropped),
    builtin codes and template values; qualifiers P R C V and A<n>_ skipped.
    'P3C2DQ23std14char_traits<c>' -> ['C2D', 'std', 'char_traits'];  'Ui,1' -> ['Ui', '1']."""
    words, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            if j >= n or s[j] in ",>":
                words.append(s[i:j])          # a template value, not a length
                i = j
                continue
            length = int(s[i:j])
            words.append(drop_templates(s[j:j + length]))
            i = j + length
        elif ch == "Q" and i + 1 < n and s[i + 1].isdigit():
            i += 2
        elif ch == "A" and re.match(r"A\d+_", s[i:]):
            i += re.match(r"A\d+_", s[i:]).end()
        elif ch in "PRCV,<>":
            i += 1
        elif ch in "US" and i + 1 < n and s[i + 1] in "cilsx":
            words.append(s[i:i + 2])
            i += 2
        else:
            words.append(ch)
            i += 1
    return [w for w in words if w]


def parse_rest(rest: str):
    """(class components, const, args-or-None) from what follows 'fn__', or None."""
    if rest.startswith("F"):
        return [], False, rest[1:]
    classes, pos, count = [], 0, 1
    q = re.match(r"Q(\d)|Q_(\d+)_", rest)
    if q:
        count, pos = int(q.group(1) or q.group(2)), q.end()
    for _ in range(count):
        n = re.match(r"\d+", rest[pos:])
        if not n:
            return None
        length = int(n.group(0))
        pos += n.end()
        if pos + length > len(rest):
            return None
        classes.append(rest[pos:pos + length])
        pos += length
    const = rest.startswith("C", pos)
    pos += const
    if pos == len(rest):
        return classes, const, None
    if rest[pos] != "F":
        return None
    return classes, const, rest[pos + 1:]


def split_mangled(name: str):
    """R2: (fn, classes, const, args) at the first '__' outside <...> (not at 0) whose tail
    parses as a class path or an argument list; None for a plain C name."""
    depth = 0
    for i in range(1, len(name) - 1):
        ch = name[i]
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif depth == 0 and name.startswith("__", i) and _REST_OK.match(name, i + 2):
            parsed = parse_rest(name[i + 2:])
            if parsed is not None:
                return (name[:i],) + parsed
    return None


def render_component(c: str) -> str:
    """R3: one class-path component."""
    m = _ANON.match(c)
    if m:
        return "anon_" + _FILE_EXT.sub("", m.group(1))
    m = _LOCAL.match(c)
    if m:
        head = drop_templates(m.group(1)).strip("_")
        return head if head else "local" + m.group(2)
    return drop_templates(c)


def render_fn(fn: str) -> str:
    """R4: the function part of a split name."""
    bare = drop_templates(fn)
    if bare in OPERATORS_FINAL:
        return OPERATORS_FINAL[bare]
    if fn.startswith("__op"):
        return "op_conv_" + "_".join(type_words(fn[4:]))
    return bare


def render_plain(name: str) -> str:
    """R5: a name with no class path and no argument list."""
    m = _SINIT.match(name)
    if m:
        return "sinit_" + m.group(1) if m.group(1) else "sinit"
    m = _LOCAL.match(name)
    if m:
        return m.group(1).lstrip("_") + "_" + m.group(2) + m.group(3)
    return name


def lead(s: str, how: str = "U2") -> str:
    """R6: a leading run of k underscores. U2 (chosen): 'u'*k + '_'. U1: stripped. U3: 'u_'."""
    k = len(s) - len(s.lstrip("_"))
    if not k:
        return s
    return {"U1": "", "U2": "u" * k + "_", "U3": "u_"}[how] + s[k:]


def tidy(s: str, how: str = "U2", collapse: bool = True) -> str:
    """R6-R8: leading underscores, sanitise, collapse '_' runs, strip trailing '_', the
    leading-digit and the keyword/main guards."""
    s = lead(_SAFE.sub("_", s), how)
    if collapse:
        s = re.sub(r"_+", "_", s).rstrip("_")
    if not s:
        s = "unnamed"
    if s[0].isdigit():
        s = "fn_" + s
    if s in KEYWORDS or s == "main":
        s = "ps2_" + s
    return s


def parts(mangled: str, how: str = "U2", templates: str = "drop", collapse: bool = True):
    """(base readable name, args or None, template tag) of one name under R1-R8."""
    if AUTO.match(mangled):
        return mangled, None, ""
    thunk, body = "", mangled
    m = _THUNK.match(mangled)
    if m:
        thunk = "thunk" + m.group(1) + ("_" + m.group(2) if m.group(2) else "")
        body = mangled[m.end():]
    sp = split_mangled(body)
    if sp is None:
        base, args, tag = render_plain(body), None, ""
    else:
        fn, classes, _const, args = sp
        if templates == "keep":
            comps = [c if "<" not in c else _SAFE.sub("_", c) for c in classes]
            f = render_fn(fn) if "<" not in fn else _SAFE.sub("_", fn)
            base = "_".join([render_component(c) if "<" not in c else c for c in comps] + [f])
        else:
            base = "_".join([render_component(c) for c in classes] + [render_fn(fn)])
        tag = "_".join(type_words(template_args(fn))
                       or [w for c in classes for w in type_words(template_args(c))])
    if thunk:
        base += "_" + thunk
    return tidy(base, how, collapse), args, tag


def base_name(mangled: str, **kw) -> str:
    return parts(mangled, **kw)[0]


def suffix_args(mangled: str, cut: int = CUT) -> str:
    """Suffix (i): the mangled argument list after F, sanitised to [A-Za-z0-9_], cut."""
    args = parts(mangled)[1]
    s = _SAFE.sub("_", args or "")
    return s[:cut] if cut else s


def suffix_hash(mangled: str) -> str:
    """Suffix (ii): six hex digits of SHA-1 of the full mangled name."""
    return hashlib.sha1(mangled.encode()).hexdigest()[:6]


def suffix_tag(mangled: str) -> str:
    return parts(mangled)[2][:CUT]


def cap(name: str, mangled: str, limit: int = LIMIT) -> str:
    """R11: over `limit`, cut and add '_' + eight hex digits of SHA-1 of the original."""
    if len(name) <= limit:
        return name
    return name[:limit - 9].rstrip("_") + "_" + hashlib.sha1(mangled.encode()).hexdigest()[:8]


# ============================================================================================
# The recompiler's sanitisers, replicated from third_party/ps2recomp/ps2xRecomp/src/lib/:
# code_generator.cpp 35-99 (kKeywords, sanitizeIdentifierBody, isReservedCxxIdentifier,
# isReservedCxxKeyword) and 181-201 (CodeGenerator::sanitizeFunctionName, the symbol-table
# fallback); ps2_recompiler.cpp 36-80 (its own copies) and 2190-2208 (PS2Recompiler::
# sanitizeFunctionName, which makeName uses for every generated function's identifier and file).
# ============================================================================================
KEYWORDS = {
    "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand", "bitor", "bool",
    "break", "case", "catch", "char", "char8_t", "char16_t", "char32_t", "class",
    "compl", "concept", "const", "consteval", "constexpr", "constinit", "const_cast",
    "continue", "co_await", "co_return", "co_yield", "decltype", "default", "delete",
    "do", "double", "dynamic_cast", "else", "enum", "explicit", "export", "extern",
    "false", "float", "for", "friend", "goto", "if", "inline", "int", "long", "mutable",
    "namespace", "new", "noexcept", "not", "not_eq", "nullptr", "operator", "or", "or_eq",
    "private", "protected", "public", "register", "reinterpret_cast", "requires", "return",
    "short", "signed", "sizeof", "static", "static_assert", "static_cast", "struct",
    "switch", "template", "this", "thread_local", "throw", "true", "try", "typedef",
    "typeid", "typename", "union", "unsigned", "using", "virtual", "void", "volatile",
    "wchar_t", "while", "xor", "xor_eq"}


def sanitize_body(name: str) -> str:
    s = "".join(c if (c.isascii() and c.isalnum()) or c == "_" else "_" for c in name)
    if s and not ((s[0].isascii() and s[0].isalpha()) or s[0] == "_"):
        s = "_" + s
    return s


def reserved(s: str) -> bool:
    return len(s) >= 2 and s[0] == "_" and (s[1] == "_" or s[1].isupper())


def sanitize_codegen(name: str) -> str:
    s = sanitize_body(name)
    if not s:
        return s
    if s == "main":
        return "ps2_main"
    if s in KEYWORDS:
        return "ps2_" + s
    if s[0] == "_":
        return "ps2" + s
    return s if not reserved(s) else "ps2_" + s


def sanitize_recomp(name: str) -> str:
    s = sanitize_body(name)
    if not s:
        return s
    if s == "main":
        return "ps2_main"
    if s in KEYWORDS or reserved(s):
        return "ps2_" + s
    return s


def alteration_rules(name: str) -> list:
    """The sanitiser rules that fire on `name` (either path)."""
    rules = []
    if _SAFE.search(name):
        rules.append("non-identifier character")
    if name[:1].isdigit():
        rules.append("leading digit")
    body = sanitize_body(name)
    if body == "main":
        rules.append("main")
    if body in KEYWORDS:
        rules.append("keyword")
    if reserved(body):
        rules.append("reserved __x/_X (both paths)")
    elif body.startswith("_"):
        rules.append("leading _ (code_generator path only)")
    return rules


# ============================================================================================
# Windows filenames
# ============================================================================================
DEVICES = ({"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)}
           | {f"LPT{i}" for i in range(1, 10)})


def windows_hazards(names):
    names = set(names)
    dev = sorted(n for n in names if n.split(".")[0].upper() in DEVICES)
    trail = sorted(n for n in names if n.endswith((".", " ")))
    bad = sorted(n for n in names if re.search(r'[<>:"/\\|?*\x00-\x1f]', n))
    fold = collections.defaultdict(set)
    for n in names:
        fold[n.lower()].add(n)
    return dev, trail, bad, sorted(sorted(v) for v in fold.values() if len(v) > 1)


# ============================================================================================
# Inputs
# ============================================================================================
def load():
    a = [(int(r["Address"], 16), r["Mangled"], "7") for r in csv.DictReader(open(RENAMES))]
    lines = [ln for ln in open(RENAMES_7B) if not ln.startswith("#")]
    a += [(int(r["Address"], 16), r["Mangled"], "7b") for r in csv.DictReader(lines)]
    b = [(start, name, "demo") for start, _end, name in read_elf(DEMO).functions]
    c = [(int(addr, 16), name, "toml")
         for name, addr in re.findall(r'"([^"@]+)@(0x[0-9A-Fa-f]+)"', open(TOML).read())]
    rows = list(csv.DictReader(open(OURS)))
    hand = [(int(r["Start"], 16), r["Name"], "hand" if not AUTO.match(r["Name"]) else "auto")
            for r in rows if not r["Name"].startswith(("FUN_", "thunk_FUN_"))]
    return a, b, c, hand, rows


def merge_d(a, c, hand, starts):
    """D by address, csv row starts only; precedence non-auto hand > proposal > toml > auto hand.
    Returns (entries, same-address conflicts, entries whose address is not a csv Start)."""
    order = ([e for e in hand if e[2] == "hand"], a, c, [e for e in hand if e[2] == "auto"])
    by_addr, conflicts, outside = {}, [], []
    for src in order:
        for addr, name, tag in src:
            if addr not in starts:
                outside.append((addr, name, tag))
                continue
            if addr in by_addr:
                if by_addr[addr][1] != name:
                    conflicts.append((addr, by_addr[addr], (addr, name, tag)))
                continue
            by_addr[addr] = (addr, name, tag)
    return sorted(by_addr.values()), conflicts, outside


# ============================================================================================
# Resolution (R9, R10) and measurement helpers
# ============================================================================================
def collisions(pairs, fold=False):
    """{name: [entries]} for every name held by more than one entry (auto names exempt)."""
    groups = collections.defaultdict(list)
    for e, n in pairs:
        if not AUTO.match(e[1]):
            groups[n.lower() if fold else n].append(e)
    return {n: es for n, es in groups.items() if len(es) > 1}


def resolve(entries, steps, fold=False, stats=None, **kw):
    """R9: base names; then each step's suffix is added to every member of a group that still
    collides. steps: sequence of 'tag', 'args', 'hash' (or 'args0' = uncut)."""
    fns = {"tag": suffix_tag, "args": suffix_args, "hash": suffix_hash,
           "args0": lambda m: suffix_args(m, 0)}
    names = {e: base_name(e[1], **kw) for e in entries}
    for step in steps:
        for group in collisions(names.items(), fold).values():
            if len({e[1] for e in group}) == 1:
                continue  # one mangled name at several addresses: no suffix can split it (R10)
            if step == "args|hash":  # R9 as recommended: (i) when it splits the group, else (ii)
                cand = {e: tidy(names[e] + "_" + suffix_args(e[1])) if suffix_args(e[1]) else names[e]
                        for e in group}
                if len({(n.lower() if fold else n) for n in cand.values()}) == len(group):
                    names.update(cand)
                    if stats is not None:
                        stats["(i)"] += 1
                else:
                    names.update({e: tidy(names[e] + "_" + suffix_hash(e[1])) for e in group})
                    if stats is not None:
                        stats["(ii)"] += 1
                continue
            for e in group:
                suf = fns[step](e[1])
                if suf:
                    names[e] = tidy(names[e] + "_" + suf)
    return names


def worst(d, k=SHOW):
    items = sorted(((n, len(v)) for n, v in d.items()), key=lambda kv: (-kv[1], kv[0]))
    return items[:k] if k else items


def residue(col):
    kinds = collections.Counter()
    for es in col.values():
        kinds["identical mangled" if len({e[1] for e in es}) == 1 else "distinct mangled"] += 1
    return dict(kinds)


def length_bucket(n):
    return ("0" if n == 0 else "1-4" if n <= 4 else "5-8" if n <= 8 else "9-16" if n <= 16
            else "17-23" if n < 24 else "24+")


def static_ok(group, demo_count):
    """R10: an identical mangled name at k addresses is kept iff the demo holds it k times."""
    return len({e[1] for e in group}) == 1 and demo_count[group[0][1]] >= len(group)


def main() -> None:
    a, b, c, hand, rows = load()
    d, conflicts, outside = merge_d(a, c, hand, {int(r["Start"], 16) for r in rows})
    demo_count = collections.Counter(e[1] for e in b)
    sets = collections.OrderedDict([("A", a), ("B", b), ("C", c), ("D", d)])

    print("# 0. the sets")
    print(f"A {len(a)} (Task 7 {sum(e[2] == '7' for e in a)}, 7b {sum(e[2] == '7b' for e in a)}); "
          f"B {len(b)}; C {len(c)} (addresses {len({e[0] for e in c})}, distinct names "
          f"{len({e[1] for e in c})}); csv {len(rows)} rows, not FUN_/thunk_FUN_ {len(hand)}: "
          f"hand {sum(e[2] == 'hand' for e in hand)}, auto by spec 1.3 {sum(e[2] == 'auto' for e in hand)} "
          f"(caseD_ {sum(e[1].startswith('caseD_') for e in hand)}, entry {sum(e[1] == 'entry' for e in hand)})")
    print(f"D {len(d)} addresses: " + ", ".join(f"{t} {n}" for t, n in
          sorted(collections.Counter(e[2] for e in d).items())) +
          f"; same address, different name {len(conflicts)}")
    for addr, kept, lost in conflicts:
        print(f"   0x{addr:08x} kept {kept[2]}:{kept[1]}  over {lost[2]}:{lost[1]}")
    toml = open(TOML).read()
    for key in ("stubs", "untracked_stubs"):
        body = re.search(r"^" + key + r"\s*=\s*\[(.*?)^\]", toml, re.S | re.M).group(1)
        ents = re.findall(r'"([^"@]+)@(0x[0-9A-Fa-f]+)"', body)
        print(f"toml {key}: {len(ents)} entries, {sum(n.startswith('_') for n, _a in ents)} with a leading _")
    print(f"A and C: same address and same name {len({e[:2] for e in a} & {e[:2] for e in c})}")
    print(f"not a csv row Start (left out of D, a name cannot be applied there without a new row): "
          f"{len(outside)} ({dict(collections.Counter(e[2] for e in outside))}); "
          + ", ".join(f"{n}@0x{x:x}" for x, n, _t in outside[:SHOW]))

    print("\n# 1. distinct readable names; collisions before any suffix")
    for label, es in sets.items():
        for how, fn in (("sketch", sketch_readable), ("final", base_name)):
            col = collisions([(e, fn(e[1])) for e in es])
            print(f"{label} {how:6} {len(es)} -> {len({fn(e[1]) for e in es})} distinct; "
                  f"{len(col)} colliding names over {sum(map(len, col.values()))}")
            print("   worst:", worst(col))
    print("rendering variants (colliding names / functions, before any suffix):")
    for label, es in sets.items():
        row = []
        for tag, kw in (("U2 final", {}), ("U1 strip", {"how": "U1"}), ("U3 u_", {"how": "U3"}),
                        ("templates kept", {"templates": "keep"}), ("no collapse", {"collapse": False})):
            col = collisions([(e, base_name(e[1], **kw)) for e in es])
            row.append(f"{tag} {len(col)}/{sum(map(len, col.values()))}")
        print(f"   {label}: " + "; ".join(row))
    for label, es in sets.items():
        u1 = collisions([(e, base_name(e[1], how="U1")) for e in es])
        twins = sorted(n for n, g in u1.items() if any(x[1].startswith("_") for x in g)
                       and any(not x[1].startswith("_") for x in g) and len({x[1] for x in g}) > 1)
        print(f"   {label}: U1 makes a name meet its un-underscored twin: {len(twins)} {twins[:SHOW]}")

    print("\n# 2. the overload suffix")
    chains = (("(i) args", ["args"]), ("(i) uncut", ["args0"]), ("(ii) hash", ["hash"]),
              ("(i)+tag", ["args", "tag"]), ("tag+(i)", ["tag", "args"]),
              ("tag,(i),(ii)", ["tag", "args", "hash"]), ("R9 (i)|(ii)", ["args|hash", "hash"]))
    for label, es in sets.items():
        col0 = collisions([(e, base_name(e[1])) for e in es])
        print(f"{label}: {len(col0)} colliding bases over {sum(map(len, col0.values()))}")
        for tag, steps in chains:
            names = resolve(es, steps)
            col = collisions(names.items())
            suffixed = [e for e in es if names[e] != base_name(e[1])]
            lens = [len(names[e]) - len(base_name(e[1])) - 1 for e in suffixed]
            print(f"   {tag:16} suffixed {len(suffixed):4}; left {len(col):3} names over "
                  f"{sum(map(len, col.values())):4} {residue(col)}; mean added "
                  f"{(sum(lens) / len(lens)) if lens else 0:.1f}; added chars "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(collections.Counter(
                      length_bucket(x) for x in lens).items())))
            if tag in ("(i) args", "(ii) hash", "R9 (i)|(ii)"):
                for e in sorted(suffixed, key=lambda e: e[1])[:3]:
                    print(f"        {e[1]}  ->  {names[e]}")
                if col and tag != "(ii) hash":
                    print("        left:", worst(col))
    for label, es in sets.items():
        stats = collections.Counter()
        resolve(es, R9, stats=stats)
        print(f"   {label}: R9 groups settled by (i) {stats['(i)']}, by (ii) {stats['(ii)']}")
    const_pairs = collections.defaultdict(set)
    for e in b:
        sp = split_mangled(_THUNK.sub("", e[1]))
        if sp and sp[1]:
            const_pairs[(base_name(e[1]), sp[3])].add(sp[2])
    print(f"   B const-only overloads (same base and args, one const, one not): "
          f"{sum(1 for v in const_pairs.values() if len(v) == 2)}")

    print("\n# 3. length after R9 (the recompiler writes <name>_0x<addr>.cpp, clamped to 100)")
    for path in (OURS, "recomp/socom2_ghidra_r0004.csv"):
        if os.path.exists(path):
            starts = [int(r["Start"], 16) for r in csv.DictReader(open(path))]
            print(f"{path}: Start 0x{min(starts):x}..0x{max(starts):x}, at most "
                  f"{max(len('%x' % x) for x in starts)} hex digits -> name budget "
                  f"{100 - len('.cpp') - len('_0x') - max(len('%x' % x) for x in starts)}")
    for label, es in sets.items():
        names = resolve(es, R9)
        over96 = [n for n in names.values() if len(n) > 96]
        over87 = [n for n in names.values() if len(n) > LIMIT]
        longest = max(names.values(), key=len)
        raw = sum(len(sanitize_body(e[1])) > 96 for e in es)
        capped = collisions([(e, cap(n, e[1])) for e, n in names.items()], fold=True)
        print(f"{label}: > 96 {len(over96)}; > 87 {len(over87)}; longest {len(longest)} ({longest}); "
              f"the raw sanitised mangled name > 96: {raw}; new collisions from the R11 cut: "
              f"{len(capped) - len(collisions(names.items(), fold=True))}")
        for e, n in sorted(((e, n) for e, n in names.items() if len(n) > LIMIT),
                           key=lambda en: -len(en[1]))[:2]:
            print(f"   {len(n)} {n} -> {cap(n, e[1])}")

    print("\n# 4. what the recompiler's sanitisers would alter")
    print(f"keywords copied: {len(KEYWORDS)} (code_generator.cpp kKeywords); plus 'main'")
    for label, es in sets.items():
        final = resolve(es, R9)
        for how, names in (("raw", [e[1] for e in es]), ("sketch", [sketch_readable(e[1]) for e in es]),
                           ("final", [final[e] for e in es])):
            per, ex = collections.Counter(), collections.defaultdict(list)
            for n in names:
                for r in alteration_rules(n):
                    per[r] += 1
                    if len(ex[r]) < 3:
                        ex[r].append(n)
            either = sum(sanitize_recomp(n) != n or sanitize_codegen(n) != n for n in names)
            mk = sum(sanitize_recomp(n) != n for n in names)
            print(f"{label} {how:6}: altered {either} (makeName path {mk}); "
                  + "; ".join(f"{r} {per[r]}" for r in sorted(per)))
            if how == "raw":
                for r in sorted(ex):
                    print(f"      {r}: {ex[r]}")
    hand_alt = [(e[1], sanitize_recomp(e[1])) for e in hand if sanitize_recomp(e[1]) != e[1]]
    print(f"csv hand/auto rows the makeName path alters today: {len(hand_alt)} {hand_alt[:SHOW]}")

    print("\n# 5. Windows filenames (final names alone)")
    for label, es in sets.items():
        names = resolve(es, R9)
        dev, trail, bad, case = windows_hazards(names.values())
        print(f"{label}: devices {len(dev)} {dev}; trailing dot/space {len(trail)}; illegal chars "
              f"{len(bad)}; case-only groups {len(case)} {case[:SHOW]}")
        folded = resolve(es, R9, fold=True)
        print(f"   with R9 case-insensitive: case-only groups "
              f"{len(windows_hazards(folded.values())[3])}")

    print("\n# 6. templates")
    for label, es in sets.items():
        tmpl = [e for e in es if "<" in e[1]]
        col = collisions([(e, base_name(e[1])) for e in es])
        caused = {n: g for n, g in col.items() if any("<" in e[1] for e in g)}
        kept = collisions([(e, base_name(e[1], templates="keep")) for e in es])
        after_i = collisions(resolve(es, ["args"]).items())
        t_after = {n: g for n, g in after_i.items() if any("<" in e[1] for e in g)}
        after_it = collisions(resolve(es, ["args", "tag"]).items())
        t_after_it = {n: g for n, g in after_it.items() if any("<" in e[1] for e in g)}
        print(f"{label}: names with <> {len(tmpl)}; base collisions involving one {len(caused)} over "
              f"{sum(map(len, caused.values()))}; with templates kept {len(kept)}; after (i) {len(t_after)}; "
              f"after (i)+tag {len(t_after_it)}")
        for n, g in list(t_after_it.items())[:6]:
            print(f"   left: {n}: " + " | ".join(sorted({e[1] for e in g}))[:240])
    for s in ("DrawFunc<11CDynGrenade>__2aiFQ22ai9LINE_TYPEffUi11CDynGrenade",
              "@8@72@__dt__Q23std39basic_ostream<c,Q23std14char_traits<c>>Fv",
              "release__15_zmalloc<4four>FPv"):
        base, args, tag = parts(s)
        print(f"   {s}: base {base}; tag {tag}; (i) {suffix_args(s)}")

    print("\n# 7. the special forms in the demo (set B)")
    names = [e[1] for e in b]
    sp = {n: split_mangled(_THUNK.sub("", n)) for n in names}
    forms = [
        ("anonymous namespace @unnamed@", [n for n in names if "@unnamed@" in n]),
        ("this-adjusting thunk @n@[m@]", [n for n in names if _THUNK.match(n)]),
        ("__sinit static initialiser", [n for n in names if n.startswith("__sinit")]),
        ("$ local (__arraydtor$n, X$n<file>)", [n for n in names if "$" in n]),
        ("operator in the table", [n for n in names if sp[n] and drop_templates(sp[n][0]) in OPERATORS]),
        ("operator the sketch misses (template <>)", [n for n in names if sp[n] and "<" in sp[n][0]
                                                      and drop_templates(sp[n][0]) in OPERATORS]),
        ("conversion operator __op<type>", [n for n in names if n.startswith("__op")]),
        ("__defctor", [n for n in names if n.startswith("__defctor")]),
        ("Q2 class path", [n for n in names if sp[n] and len(sp[n][1]) == 2]),
        ("Q3 class path", [n for n in names if sp[n] and len(sp[n][1]) == 3]),
        ("free C++ function fn__F", [n for n in names if sp[n] and not sp[n][1]]),
        ("plain C name", [n for n in names if sp[n] is None]),
        ("plain C name with leading _", [n for n in names if sp[n] is None and n.startswith("_")]),
    ]
    for form, ns in forms:
        eg = ns[0] if ns else ""
        print(f"{form}: {len(ns)}; e.g. {eg} -> {base_name(eg) if ns else '-'}"
              f"   (sketch {sketch_readable(eg) if ns else '-'})")
    ops = collections.Counter(drop_templates(sp[n][0]) for n in names
                              if sp[n] and drop_templates(sp[n][0]) in OPERATORS_FINAL)
    print("operators seen:", ", ".join(f"{k}->{OPERATORS_FINAL[k]} {v}" for k, v in ops.most_common()))
    print("table entries never seen:", len(set(OPERATORS) - set(ops)))
    finals = [base_name(n) for n in names]
    print(f"R8 guards that fire: fn_ (leading digit) {sum(f.startswith('fn_') for f in finals)}; "
          f"ps2_ (keyword or main) {sum(f.startswith('ps2_') for f in finals)}; the sketch leaves "
          f"{sum(1 for n in names if sp[n] and not sp[n][1] and sketch_readable(n) == _SAFE.sub('_', n))} "
          f"free C++ functions with their argument list in the name")
    print("conversion operators:", [base_name(n) for n in names if n.startswith("__op")])

    print("\n# 8. the proof over D (R1-R12)")
    names = resolve(d, R9, fold=True)
    names = {e: cap(n, e[1]) for e, n in names.items()}
    col = collisions(names.items(), fold=True)
    kept = {n: g for n, g in col.items() if static_ok(g, demo_count)}
    refused = {n: g for n, g in col.items() if n not in kept}
    applied = {e: n for e, n in names.items() if not AUTO.match(e[1])}
    alt = [(e, n) for e, n in applied.items() if sanitize_recomp(n) != n or sanitize_codegen(n) != n]
    dev, trail, bad, case = windows_hazards(applied.values())
    into_auto = [n for e, n in applied.items() if AUTO.match(n)]
    print(f"D {len(d)} addresses, {len(applied)} non-auto names; still colliding after R9: {len(col)} names "
          f"over {sum(map(len, col.values()))}; kept by R10 (demo holds the name as often): {len(kept)} over "
          f"{sum(map(len, kept.values()))}; refused: {len(refused)} over {sum(map(len, refused.values()))}")
    for n, g in sorted(kept.items()):
        n = names[g[0]]
        print(f"   R10 kept  {n}: demo x{demo_count[g[0][1]]}; " + ", ".join(f"0x{e[0]:08x} {e[2]}" for e in g))
    size_at = {int(r["Start"], 16): int(r["Size"]) for r in rows}
    how_at = {int(r["Address"], 16): f"{r['How']} {r['Score']}" for r in csv.DictReader(open(RENAMES))}
    for n, g in sorted(refused.items()):
        n = names[g[0]]
        print(f"   refused   {n}: demo x{demo_count[g[0][1]]}; "
              + ", ".join(f"0x{e[0]:08x} {e[2]}:{e[1]} {size_at[e[0]]} B"
                          + (f" ({how_at[e[0]]})" if e[0] in how_at else "") for e in g))
    print(f"sanitiser alterations {len(alt)}; > 87 chars {sum(len(n) > LIMIT for n in applied.values())}; "
          f"devices {len(dev)}; trailing dot/space {len(trail)}; illegal chars {len(bad)}; case-only "
          f"groups {len(case)}; render into the auto namespace {len(into_auto)}")
    suffixed = sorted((e, n) for e, n in applied.items() if n != base_name(e[1]))
    print(f"names that carry a suffix: {len(suffixed)}")
    for e, n in suffixed[:SHOW]:
        print(f"   0x{e[0]:08x} {e[1]} -> {n}")
    demo_fns = read_elf(DEMO).functions
    ours = sorted((int(r["Start"], 16), int(r["Size"]), r["Name"]) for r in rows)
    toml_at = {e[0]: e[1] for e in c}
    for anchor, lo, hi in (("AddDmacHandler", 0x1a3800, 0x1a3860), ("kCopy", 0x1ac0c0, 0x1ac130)):
        i = next(k for k, f in enumerate(demo_fns) if f[2] == anchor)
        print("   positional hint, demo: " + ", ".join(f"{n} {e - st}" for st, e, n in demo_fns[i - 1:i + 4]))
        print("                    ours: " + ", ".join(f"0x{a:x} {toml_at.get(a, n)} {sz}" for a, sz, n in ours
                                                    if lo <= a < hi)
              + "".join(f"; toml {n}@0x{a:x} in a {min(x for x, _s, _n in ours if x > a) - a} B gap, no csv row"
                        for a, n in sorted(toml_at.items())
                        if lo <= a < hi and a not in {x for x, _s, _n in ours}))
    changed = sorted((e, n) for e, n in applied.items() if e[2] == "hand" and n != e[1])
    print(f"hand names the rule respells: {len(changed)}: " + ", ".join(f"{e[1]}->{n}" for e, n in changed[:SHOW]))
    auto_groups = collections.Counter(e[1] for e in d if AUTO.match(e[1]))
    auto_col = {n: k for n, k in auto_groups.items() if k > 1}
    print(f"auto rows (exempt, R12): {sum(1 for e in d if AUTO.match(e[1]))}; their own repeats "
          f"{len(auto_col)} names over {sum(auto_col.values())}")


if __name__ == "__main__":
    main()
