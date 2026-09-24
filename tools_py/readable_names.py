"""The readable-name renderer: a demo mangled name -> the csv `Name` (Sprint 12 Task 1; research/47, S12-R14).

The rules are research/47's "The recommended rule set", R1-R12, with one amendment (S12-R14, readability over
injectivity) to R6:

- R1 thunks. A leading `@<n>@` / `@<n>@<m>@` is removed; `_thunk<n>` / `_thunk<n>_<m>` is appended.
- R2 the split at the first `__` (outside `<...>`, not at 0) whose tail parses as `F<args>` or a class path
  (`Q<d>` + d length-prefixed components, or one `<len><name>`), optional `C`, then `F<args>` or nothing.
- R3 class path joined with `_`: template arguments dropped; `@unnamed@<file>@` -> `anon_<file>`;
  `<X>$<n><file>` -> `X`, or `local<n>` when X is empty.
- R4 function part: templates dropped, the operator table, `__op<type>` -> `op_conv_<type words>`.
- R5 plain forms: `__sinit_<f>.cpp` -> `sinit_<f>`, `__sinit` -> `sinit`, `<X>$<n>` -> `<X>_<n>`.
- R6 (S12-R14) a leading underscore run the live sanitiser would rewrite (`__x`, `_X`) is STRIPPED
  (`__divdi3` -> `divdi3`, `_Exit` -> `Exit`); `_` + anything else is kept (`_printf`). Only in `render`,
  a stripped spelling that meets another name case-insensitively falls back to research/47's `u`xk + `_`
  (`_Exit` beside `Exit` -> `u_Exit`), that name alone.
- R7 `[^A-Za-z0-9_]` -> `_`, runs of `_` collapsed, trailing `_` stripped.
- R8 a leading digit gets `fn_`; a C++ keyword or `main` gets `ps2_`.
- R9 (render) case-insensitive collision groups, among the inputs and against `taken`: suffix (i), the
  argument list, where it splits the whole group, else (ii), six hex of SHA-1, repeated to a fixed point.
- R10 (render) one mangled name at k addresses is kept unsuffixed only if the demo holds it >= k times.
- R11 (render) over 87 characters: the first 78, `_`, eight hex of SHA-1 of the mangled original.
- R12 placeholders are never rendered, and no rendered name may be one.

The invariant every rendered name holds (`is_legal`, plus uniqueness in `render`), S12-R19: the recompiler's
LIVE sanitiser returns it unchanged (`sanitize_recomp`, ps2_recompiler.cpp:2190). `sanitize_codegen`
(code_generator.cpp:181) is kept as a documented replica only and is not a bar: it is the symbol-table
fallback, which never runs on this image (research/61 §1.5), and it would prefix every `_x` S12-R14 keeps.
Also: at most 87 characters (the filename budget, research/47 §3); not a Windows device name; no trailing `.` or space; not
a placeholder; unique case-insensitively among the outputs and against `taken`.

Pure and deterministic: names in, names out, nothing read from disk.
"""
import collections
import hashlib
import re
from typing import Dict, Iterable, List, Mapping, NamedTuple, Optional, Tuple

try:
    from tools_py.name_provenance import is_placeholder
except ImportError:  # pragma: no cover - Task 2's module absent: research/48's anchored predicate
    _PLACEHOLDER = re.compile(r"^(?:(?:FUN|LAB|DAT|SUB|sub)_[0-9A-Fa-f]{8}|thunk_(?:EXT_)?FUN_[0-9A-Fa-f]{8}"
                              r"|caseD_[0-9A-Fa-f]+|switchD_[0-9A-Fa-f]{8}|entry)$")

    def is_placeholder(name: str) -> bool:
        return bool(_PLACEHOLDER.match(name))

LIMIT = 87        # R11: 100 (clampFilenameLength) - len(".cpp") - len("_0x") - 6 hex digits
ARGS_CUT = 24     # R9 (i)
HASH_LEN = 6      # R9 (ii)
MAX_ROUNDS = 8    # R9's fixed point; a group still colliding after this is refused

# code_generator.cpp:35-47, all 92 entries of kKeywords.
KEYWORDS = frozenset({
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
    "wchar_t", "while", "xor", "xor_eq"})

DEVICES = frozenset({"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)}
                    | {f"LPT{i}" for i in range(1, 10)})

# R4: the sketch's 38 operators plus __defctor.
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
    "__defctor": "defctor",
}

_SAFE = re.compile(r"[^A-Za-z0-9_]")
_THUNK = re.compile(r"^@(\d+)@(?:(\d+)@)?")                        # R1
_REST_OK = re.compile(r"F|Q\d|Q_\d+_|\d+")                         # R2
_ANON = re.compile(r"^@unnamed@(.*?)@$")                           # R3
_LOCAL = re.compile(r"^(.*?)\$(\d+)(.*)$")                         # R3, R5
_SINIT = re.compile(r"^__sinit(?:_(.*?))?(?:\.(?:cpp|cp|c))?$")    # R5
_FILE_EXT = re.compile(r"_(?:cpp|cp|c)$")


# ================================================================================================
# The recompiler's two sanitisers, replicated byte for byte from third_party/ps2recomp/ps2xRecomp/src/lib/.
# std::isalnum/isalpha/isupper run on each byte of the UTF-8 string in the "C" locale: ASCII only.
# ================================================================================================
def _ascii_alnum(b: int) -> bool:
    return 0x30 <= b <= 0x39 or 0x41 <= b <= 0x5A or 0x61 <= b <= 0x7A


def _sanitize_body(name: str) -> str:
    """sanitizeIdentifierBody (ps2_recompiler.cpp:49-79 = code_generator.cpp:53-79)."""
    s = "".join(chr(b) if _ascii_alnum(b) or b == 0x5F else "_" for b in name.encode("utf-8"))
    if s and not (s[0].isalpha() or s[0] == "_"):
        s = "_" + s
    return s


def _reserved(s: str) -> bool:
    """isReservedCxxIdentifier (ps2_recompiler.cpp:36-47 = code_generator.cpp:81-88): `__x` or `_X`."""
    return len(s) >= 2 and s[0] == "_" and (s[1] == "_" or "A" <= s[1] <= "Z")


def sanitize_recomp(name: str) -> str:
    """PS2Recompiler::sanitizeFunctionName (ps2_recompiler.cpp:2190): the live path, makeName's."""
    s = _sanitize_body(name)
    if not s:
        return s
    if s == "main":
        return "ps2_main"
    if s in KEYWORDS or _reserved(s):
        return "ps2_" + s
    return s


def sanitize_codegen(name: str) -> str:
    """CodeGenerator::sanitizeFunctionName (code_generator.cpp:181): the symbol-table fallback.

    A replica for reference only (S12-R19): it never runs on this image, which has no ELF symbols
    (research/61 §1.5), so `is_legal` and `render` do not consult it."""
    s = _sanitize_body(name)
    if not s:
        return s
    if s == "main":
        return "ps2_main"
    if s in KEYWORDS:
        return "ps2_" + s
    if s[0] == "_":
        return "ps2" + s
    if not _reserved(s):
        return s
    return "ps2_" + s


# ================================================================================================
# R1-R8: one name
# ================================================================================================
def _drop_templates(s: str) -> str:
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


def _type_words(s: str) -> List[str]:
    """The readable words of a mangled type list (R4's `__op<type>`): 'Ui' -> ['Ui'], 'f' -> ['f']."""
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
            words.append(_drop_templates(s[j:j + length]))
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


def _parse_rest(rest: str) -> Optional[Tuple[List[str], bool, Optional[str]]]:
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


def _split(name: str):
    """R2: (fn, classes, const, args) at the first '__' outside <...> (not at 0) whose tail parses;
    None for a plain name."""
    depth = 0
    for i in range(1, len(name) - 1):
        ch = name[i]
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif depth == 0 and name.startswith("__", i) and _REST_OK.match(name, i + 2):
            parsed = _parse_rest(name[i + 2:])
            if parsed is not None:
                return (name[:i],) + parsed
    return None


def _component(c: str) -> str:
    """R3: one class-path component."""
    m = _ANON.match(c)
    if m:
        return "anon_" + _FILE_EXT.sub("", m.group(1))
    m = _LOCAL.match(c)
    if m:
        head = _drop_templates(m.group(1)).strip("_")
        return head if head else "local" + m.group(2)
    return _drop_templates(c)


def _function(fn: str) -> str:
    """R4: the function part of a split name."""
    bare = _drop_templates(fn)
    if bare in OPERATORS:
        return OPERATORS[bare]
    if fn.startswith("__op"):
        return "op_conv_" + "_".join(_type_words(fn[4:]))
    return bare


def _plain(name: str) -> str:
    """R5: a name with no class path and no argument list."""
    m = _SINIT.match(name)
    if m:
        return "sinit_" + m.group(1) if m.group(1) else "sinit"
    m = _LOCAL.match(name)
    if m:
        return m.group(1).lstrip("_") + "_" + m.group(2) + m.group(3)
    return name


def _lead(s: str, fallback: bool) -> str:
    """R6 with S12-R14: only a spelling the live sanitiser rewrites (`__x`, `_X`) is touched. Stripped
    by default; with `fallback`, research/47's `u`xk + `_` (`__divdi3` -> `uu_divdi3`)."""
    if not _reserved(s):
        return s
    k = len(s) - len(s.lstrip("_"))
    return ("u" * k + "_" if fallback else "") + s[k:]


def _tidy(s: str, fallback: bool = False) -> str:
    """R6-R8."""
    s = _lead(_SAFE.sub("_", s), fallback)
    s = re.sub(r"_+", "_", s).rstrip("_")
    if not s:
        s = "unnamed"
    if s[0].isdigit():
        s = "fn_" + s
    if s in KEYWORDS or s == "main":
        s = "ps2_" + s
    return s


def _parts(mangled: str, fallback: bool = False) -> Tuple[str, Optional[str]]:
    """(readable base, the mangled argument list or None) under R1-R8."""
    thunk, body = "", mangled
    m = _THUNK.match(mangled)
    if m:
        thunk = "thunk" + m.group(1) + ("_" + m.group(2) if m.group(2) else "")
        body = mangled[m.end():]
    sp = _split(body)
    if sp is None:
        base, args = _plain(body), None
    else:
        fn, classes, _const, args = sp
        base = "_".join([_component(c) for c in classes] + [_function(fn)])
    if thunk:
        base += "_" + thunk
    return _tidy(base, fallback), args


def readable(mangled: str) -> str:
    """R1-R8 (R6 as amended by S12-R14): 'Mul__5CQuatCFPC5CQuatP5CQuat' -> 'CQuat_Mul', '__divdi3' ->
    'divdi3', '_printf' -> '_printf'. A placeholder is returned as it is (R12: never rendered)."""
    if is_placeholder(mangled):
        return mangled
    return _parts(mangled)[0]


def overload_suffix(mangled: str, kind: str) -> str:
    """R9's two candidates. "args": the mangled argument list after `F`, sanitised to [A-Za-z0-9_] and cut
    to 24 ('' for a plain name). "hash": six hex digits of SHA-1 of the whole mangled name."""
    if kind == "args":
        return _SAFE.sub("_", _parts(mangled)[1] or "")[:ARGS_CUT]
    if kind == "hash":
        return hashlib.sha1(mangled.encode("utf-8")).hexdigest()[:HASH_LEN]
    raise ValueError(f"kind must be 'args' or 'hash', not {kind!r}")


def _suffixed(name: str, suffix: str) -> str:
    if not suffix:
        return name
    return re.sub(r"_+", "_", name + "_" + suffix).rstrip("_")


def _cap(name: str, mangled: str) -> str:
    """R11: over 87, the first 78 (a trailing `_` dropped, keeping R7), `_`, eight hex of SHA-1."""
    if len(name) <= LIMIT:
        return name
    return name[:LIMIT - 9].rstrip("_") + "_" + hashlib.sha1(mangled.encode("utf-8")).hexdigest()[:8]


# ================================================================================================
# The invariant
# ================================================================================================
def is_legal(name: str) -> Optional[str]:
    """None, or why `name` may not be a rendered csv Name (one name; uniqueness is `render`'s)."""
    if not name:
        return "empty"
    if is_placeholder(name):
        return "R12: matches the placeholder pattern"
    live = sanitize_recomp(name)
    if live != name:
        return f"the live sanitiser (ps2_recompiler.cpp:2190) rewrites it to {live}"
    if len(name) > LIMIT:
        return f"{len(name)} characters, over {LIMIT}"
    if name.split(".")[0].upper() in DEVICES:
        return "a Windows device name"
    if name.endswith((".", " ")):
        return "a trailing dot or space"
    return None


class RenderResult(NamedTuple):
    """`names`: mangled -> final name, one entry per DISTINCT mangled input; a caller applying per-address
    rows gives every row whose mangled name is `m` the name `names[m]` (a rendered name is a function of the
    mangled string alone, and R10 keeps or refuses all of a name's rows together). `refused`: mangled ->
    reason, for every row carrying it. `counts`: mangled -> how many times it was given (its addresses).
    Every distinct input is in exactly one of `names` and `refused`."""
    names: Dict[str, str]
    refused: Dict[str, str]
    counts: Dict[str, int]


def render(mangled_names: Iterable[str], taken: Iterable[str] = (),
           demo_counts: Optional[Mapping[str, int]] = None) -> RenderResult:
    """R1-R12 over a set of names, one entry per address (duplicates are R10's multiplicity).

    `taken`: the non-placeholder names already in the csv/sidecar at addresses this call is not renaming
    (a placeholder in it is ignored); no output equals one case-insensitively. `demo_counts`: how often the
    demo's `.symtab` holds each mangled name (R10). Never raises for a name: a violation is a refusal."""
    demo_counts = demo_counts or {}
    counts = dict(collections.Counter(mangled_names))
    taken_fold = {t.lower() for t in taken if not is_placeholder(t)}
    refused: Dict[str, str] = {}
    base: Dict[str, str] = {}
    for m in counts:
        if not m:
            refused[m] = "empty name"
        elif is_placeholder(m):
            refused[m] = "R12: a placeholder is never rendered"
        else:
            base[m] = _parts(m)[0]

    # S12-R14: a stripped spelling that meets another name (case-insensitively) takes research/47's u x k.
    fold = collections.Counter(n.lower() for n in base.values())
    for m, n in list(base.items()):
        u = _parts(m, fallback=True)[0]
        if u != n and (fold[n.lower()] > 1 or n.lower() in taken_fold):
            base[m] = u

    for m, n in list(base.items()):
        if is_placeholder(n):                                  # R12
            refused[m] = f"R12: renders into the placeholder pattern ({n})"
            del base[m]

    for m in list(base):                                       # R10, before R9: a refused row forces no suffix
        k, have = counts[m], demo_counts.get(m, 0)
        if k > 1 and have < k:
            refused[m] = (f"R10: one name at {k} addresses and the demo holds it {have} time(s); "
                          "every row refused")
            del base[m]

    names = dict(base)                                         # R9, to a fixed point
    suffixed = set()
    for _round in range(MAX_ROUNDS):
        groups = collections.defaultdict(list)
        for m, n in names.items():
            groups[n.lower()].append(m)
        changed = False
        for key, members in groups.items():
            if len(members) < 2 and key not in taken_fold:
                continue
            cand = {m: _suffixed(names[m], overload_suffix(m, "args")) for m in members}
            folded = [c.lower() for c in cand.values()]
            if (not suffixed.intersection(members) and len(set(folded)) == len(members)
                    and not taken_fold.intersection(folded)):
                names.update(cand)                             # (i) splits the whole group
            else:
                names.update({m: _suffixed(names[m], overload_suffix(m, "hash")) for m in members})
            suffixed.update(members)
            changed = True
        if not changed:
            break

    names = {m: _cap(n, m) for m, n in names.items()}           # R11

    for m, n in list(names.items()):                           # the invariant, one name
        why = is_legal(n)
        if why:
            refused[m] = f"{n}: {why}"
            del names[m]
    groups = collections.defaultdict(list)                     # the invariant, uniqueness
    for m, n in names.items():
        groups[n.lower()].append(m)
    for key, members in groups.items():
        if len(members) > 1 or key in taken_fold:
            for m in members:
                others = sorted(set(members) - {m})
                refused[m] = (f"{names[m]}: still collides case-insensitively after R9"
                              + (f" with {', '.join(others)}" if others else "")
                              + (" with a taken name" if key in taken_fold else ""))
                del names[m]
    return RenderResult(names, refused, counts)
