"""The PS2X_* knob registry, read out of the C++ header that defines it (Sprint 9 Goal 3).

`third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h` is the one place a knob's class, kind, default and
meaning are written. This module parses its X-macro rows (as tools_py/exit_codes.py does for the exit codes),
renders docs/KNOBS.md from them, and scans the source so the two cannot drift:

    python -m tools_py.knobs write     regenerate docs/KNOBS.md
    python -m tools_py.knobs check     exit 1 on a stale docs/KNOBS.md or any disagreement below
    python -m tools_py.knobs sites     every PS2X_* string literal with its file:line
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECOMP = os.path.join("third_party", "ps2recomp")
HEADER = os.path.join(ROOT, RECOMP, "ps2xShared", "include", "ps2x", "knobs.h")
DOC = os.path.join(ROOT, "docs", "KNOBS.md")

# Where a shipped executable's source lives. ps2xTest is scanned separately (its getenv reads only).
SHIPPED_TREES = [os.path.join(RECOMP, "ps2xRuntime", "src"), os.path.join(RECOMP, "ps2xRuntime", "include"),
                 os.path.join(RECOMP, "ps2xIOP"), os.path.join(RECOMP, "ps2xShared"), os.path.join(RECOMP, "ps2xLauncher")]
TEST_TREE = os.path.join(RECOMP, "ps2xTest")
HARNESS_PATHS = ["tools_py", os.path.join("scripts", "parity"), "run.sh"]

REGISTRY_FILE = "knobs.h"          # its rows are the registry, not reads
SWITCH_FILE = "knobs.cpp"          # the one file that may getenv("PS2X_DEV")
# Files that may call getenv with a name that is not a literal: knobs.cpp is the accessor; bare_run.cpp applies
# config.json's keys to the environment (a Shipping name each, decided by launcher::environmentFor, not a read
# of a knob). A helper that takes a knob name as a parameter (traceSkip, envFlag, envOn ...) is not exempt: it reads
# through ps2x::knob like every literal site (Task 4 rule 2), and this check is what holds it there.
HELPER_GETENV_ALLOWED = {"knobs.h", "knobs.cpp", "bare_run.cpp"}   # knobs.h: the accessor's own comment names getenv

# Names the harness uses that no C++ reads.
HARNESS_ONLY = {"PS2X_RUN_LOG", "PS2X_TEST_REPEAT", "PS2X_SOCOM2_RSA_KEY_B"}
# PS2X_* tokens in harness files that are not environment names at all.
NOT_KNOBS = {
    "PS2X_",
    # leakcheck.py: a planted control string of the shape a credential would take -- the leak gate proving it
    # does not fire on a placeholder value, not a knob (Goal 9 may register the real name later).
    "PS2X_SOCOM2_LOGIN_PASS",
}
# ps2xTest fixtures that are set and read back by one test and mean nothing to the runtime.
TEST_FIXTURE_PREFIXES = ("PS2X_BARE_TEST_",)

# Sprint 9 Goal 3 Task 4 migrated every raw getenv("PS2X_..."); a file that grows one fails test_knobs_registry.
RAW_GETENV_PENDING = set()

# A row may end with its read sites, `/* read: <file>:<function> [...] */` (Sprint 13 C9): the file relative to
# third_party/ps2recomp, the function the knob's name is read in. Required on a Shipping or Switch row.
_ROW = re.compile(r'^\s*X\("(PS2X_[A-Z0-9_]+)",\s*(\w+),\s*(\w+),\s*"([^"]*)",\s*"([^"]*)"\)'
                  r'(?:[ \t]*/\*\s*read:\s*([^*]*?)\s*\*/)?', re.M)
# A read: a call whose first argument is the name (ps2x::knob, knobOn, the file-local helpers that wrap knob --
# envFlag, traceSkip ... -- and knobs.cpp's one getenv of PS2X_DEV). "PS2X_X=" (an environment entry the launcher
# builds) and a name inside an expression (a log line's label) are not calls with the name first.
_READ_CALL = re.compile(r'\b[A-Za-z_]\w*\s*\(\s*"(PS2X_[A-Z0-9_]+)"\s*[,)]')
# The classes whose rows must cite their read sites, and the mark a meaning carries when the code alone could not
# settle it (the test allows it; the report names the knob and why).
CITED_CLASSES = ("Shipping", "Switch")
UNVERIFIED = "(unverified)"
# A log line a meaning names, e.g. "[gs-gl stats]": the tag must be printed somewhere in the shipped trees.
_LOG_TAG = re.compile(r'\[([a-z][a-z0-9 _-]*)\]')
_LITERAL = re.compile(r'"(PS2X_[A-Z0-9_]+)(?=["=])')
_RAW_GETENV = re.compile(r'getenv\s*\(\s*"PS2X_')
_HELPER_GETENV = re.compile(r'getenv\s*\(\s*(?!["\s])')   # getenv(name), getenv(env), getenv(br::kApiBaseEnv) ...
_TEST_READ = re.compile(r'getenv\s*\(\s*"(PS2X_[A-Z0-9_]+)"')
_TOKEN = re.compile(r'PS2X_[A-Z0-9_]*')
_ACCESSOR = re.compile(r'ps2x::(knobOn|knob)\s*\(\s*"(PS2X_[A-Z0-9_]+)"')
# A knob read that initialises a namespace-scope object runs before main(), where --dev has not been seen. This
# tree names its globals g_ and writes file-level statics at column 0; a function-local static is indented
# and called s_.
_EARLY = re.compile(r'^(?:static\b.*|\s*(?:static\s+)?(?:const\s+)?[\w:<>]+\s+g_\w+\s*=.*)ps2x::knob')


def table(path=HEADER):
    """[{name, cls, kind, default, meaning, read: [(file, function), ...]}, ...] in the header's order."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return [{"name": m.group(1), "cls": m.group(2), "kind": m.group(3), "default": m.group(4), "meaning": m.group(5),
             "read": _citations(m.group(6))}
            for m in _ROW.finditer(text)]


def _citations(text):
    """'a.cpp:f b.h:g' -> [('a.cpp', 'f'), ('b.h', 'g')]; None or '' -> []."""
    out = []
    for token in (text or "").split():
        path, _, function = token.rpartition(":")
        out.append((path, function) if path else (token, ""))
    return out


def _files(root, trees, suffixes=(".cpp", ".h")):
    for tree in trees:
        top = os.path.join(root, tree)
        if os.path.isfile(top):
            yield top
            continue
        for folder, dirs, names in os.walk(top):
            dirs[:] = [d for d in dirs if not d.startswith("build") and d != "__pycache__"]
            for name in sorted(names):
                if name.endswith(suffixes):
                    yield os.path.join(folder, name)


def _lines(path):
    # latin-1: three files in the tree carry a byte that is not UTF-8, and every name we look for is ASCII.
    with open(path, "r", encoding="latin-1") as fh:
        return fh.read().split("\n")


def _rel(root, path):
    return os.path.relpath(path, root).replace("\\", "/")


def literals(root=ROOT):
    """{name: [file:line, ...]} for every "PS2X_NAME" / "PS2X_NAME=..." string literal in the shipped trees."""
    found = {}
    for path in _files(root, SHIPPED_TREES):
        if os.path.basename(path) == REGISTRY_FILE:
            continue
        for number, line in enumerate(_lines(path), 1):
            for name in _LITERAL.findall(line):
                found.setdefault(name, []).append("%s:%d" % (_rel(root, path), number))
    return found


def raw_getenv_sites(root=ROOT):
    sites = []
    for path in _files(root, SHIPPED_TREES):
        if os.path.basename(path) == SWITCH_FILE:
            continue
        for number, line in enumerate(_lines(path), 1):
            if _RAW_GETENV.search(line):
                sites.append("%s:%d" % (_rel(root, path), number))
    return sites


def helper_getenv_sites(root=ROOT):
    """getenv calls whose argument is not a string literal, outside HELPER_GETENV_ALLOWED: a helper that reads a
    knob for its callers and has not been taught ps2x::knob."""
    sites = []
    for path in _files(root, SHIPPED_TREES):
        if os.path.basename(path) in HELPER_GETENV_ALLOWED:
            continue
        for number, line in enumerate(_lines(path), 1):
            if _HELPER_GETENV.search(line):
                sites.append("%s:%d" % (_rel(root, path), number))
    return sites


def test_reads(root=ROOT):
    found = {}
    for path in _files(root, [TEST_TREE]):
        for number, line in enumerate(_lines(path), 1):
            for name in _TEST_READ.findall(line):
                if not name.startswith(TEST_FIXTURE_PREFIXES):
                    found.setdefault(name, []).append("%s:%d" % (_rel(root, path), number))
    return found


def harness_names(root=ROOT):
    found = {}
    for path in _files(root, HARNESS_PATHS, suffixes=(".py", ".sh", ".txt", ".json")):
        rel = _rel(root, path)
        if rel.startswith("tools_py/tests/") or rel == "tools_py/knobs.py":
            continue
        for number, line in enumerate(_lines(path), 1):
            for name in _TOKEN.findall(line):
                if name not in NOT_KNOBS and not name.endswith("_"):
                    found.setdefault(name, []).append("%s:%d" % (rel, number))
    return found


def early_reads(root=ROOT):
    sites = []
    for path in _files(root, SHIPPED_TREES):
        for number, line in enumerate(_lines(path), 1):
            if _EARLY.search(line):
                sites.append("%s:%d" % (_rel(root, path), number))
    return sites


def accessor_mismatches(root=ROOT, rows=None):
    kinds = {r["name"]: r["kind"] for r in (table() if rows is None else rows)}
    out = []
    for path in _files(root, SHIPPED_TREES):
        for number, line in enumerate(_lines(path), 1):
            for accessor, name in _ACCESSOR.findall(line):
                kind = kinds.get(name)
                where = "%s:%d" % (_rel(root, path), number)
                if kind == "Flag" and accessor == "knob":
                    out.append("%s: %s is a Flag and is read with ps2x::knob (use knobOn: the one flag rule)" % (where, name))
                if kind is not None and kind != "Flag" and accessor == "knobOn":
                    out.append("%s: %s is read with ps2x::knobOn but its row says %s" % (where, name, kind))
    return out


_PREPROCESSOR = re.compile(r'^[ \t]*#(?:[^\n]*\\\n)*[^\n]*', re.M)


def _code_only(text):
    """The text with comments and string/char literals blanked (newlines kept), so every offset still lines up and
    a brace inside a string or comment cannot move the brace count. Preprocessor lines are blanked too: an
    `#if defined(X)` above a block is not the block's function."""
    text = _PREPROCESSOR.sub(lambda m: re.sub(r'[^\n]', " ", m.group()), text)
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            for k in range(i, end):
                if text[k] != "\n":
                    out[k] = " "
            i = end
        elif c == '"' and i > 0 and text[i - 1] == "R" and (i < 2 or not (text[i - 2].isalnum() or text[i - 2] == "_")
                                                             or text[i - 2] in "uUL8"):
            # A raw string literal, R"TAG(...)TAG": no escapes, may span lines, may hold quotes and braces.
            paren = text.find("(", i + 1)
            close = text.find(")" + text[i + 1:paren] + '"', paren) if paren >= 0 else -1
            end = n if close < 0 else close + (paren - i) + 1        # one past the closing quote
            for j in range(i + 1, min(end, n)):
                if text[j] != "\n":
                    out[j] = " "
            i = end
        elif c in "\"'":
            k = i + 1
            while k < n and text[k] != c and text[k] != "\n":
                k += 2 if text[k] == "\\" else 1
            for j in range(i + 1, min(k, n)):
                out[j] = " "
            i = k + 1
        else:
            i += 1
    return "".join(out)


_CONTROL = {"if", "for", "while", "switch", "catch", "return", "sizeof", "decltype", "alignof", "static_assert"}
_SCOPE = re.compile(r'\b(namespace|struct|class|enum|union|extern)\b')
_TAIL = re.compile(r'\)\s*(?:(?:const|noexcept|override|final|mutable|volatile)\b\s*|->\s*[\w:<>*&\s]+?\s*)*$')


def _function_of(code, brace):
    """The name of the function whose body opens at `brace`, or None (a lambda, a control block, a scope)."""
    start = max(code.rfind(";", 0, brace), code.rfind("{", 0, brace), code.rfind("}", 0, brace)) + 1
    head = code[start:brace].strip()
    if not head or _SCOPE.search(head.split("(")[0]):
        return None
    constructor = _constructor_head(head)
    if constructor:
        return constructor[0]
    tail = _TAIL.search(head)
    if not tail:
        return None
    depth, k = 0, tail.start()
    while k >= 0:
        depth += {")": 1, "(": -1}.get(head[k], 0)
        if depth == 0:
            break
        k -= 1
    before = head[:max(k, 0)].rstrip()
    if before.endswith("]"):
        return None
    m = re.search(r'([~A-Za-z_][\w:~]*)$', before)
    if not m:
        return None
    name = m.group(1).split("::")[-1]
    return None if name in _CONTROL else name


def _constructor_head(head):
    """(name, index just past the parameter list) when `head` is `Name(params) [noexcept] : inits`, else None."""
    m = re.match(r'\s*([~A-Za-z_][\w:~]*)\s*\(', head)
    if not m or m.group(1).split("::")[-1] in _CONTROL:
        return None
    depth, k = 0, m.end() - 1
    while k < len(head):
        depth += {"(": 1, ")": -1}.get(head[k], 0)
        if depth == 0:
            break
        k += 1
    rest = head[k + 1:].lstrip()
    if rest.startswith("noexcept"):
        rest = rest[len("noexcept"):].lstrip()
    if not rest.startswith(":") or rest.startswith("::"):
        return None
    return m.group(1).split("::")[-1], k + 1


def _constructor_of(code, offset):
    """The constructor whose member-initialiser list holds `offset` (`Foo::Foo() : m_x(knob("PS2X_X")) {`), or None.
    Such a read sits before the body's brace, so the brace stack alone cannot name it. (An initialiser written with
    braces, m_x{...}, ends the search early: the tree has none around a knob read.)"""
    brace = code.find("{", offset)
    if brace < 0 or any(c in code[offset:brace] for c in ";}"):
        return None
    start = max(code.rfind(";", 0, offset), code.rfind("{", 0, offset), code.rfind("}", 0, offset)) + 1
    found = _constructor_head(code[start:brace])
    if not found or start + found[1] > offset:
        return None
    return found[0]


def read_sites(root=ROOT):
    """{name: [(file relative to third_party/ps2recomp, line, enclosing function or None), ...]} for every read of
    a PS2X_* name (_READ_CALL) in the shipped trees.

    A read is ANY call whose first argument is the name as a string literal: ps2x::knob, knobOn, the file-local
    wrappers (envFlag, traceSkip ...) and knobs.cpp's getenv("PS2X_DEV") -- and so would a setenv("PS2X_X", ...) or a
    find("PS2X_X"), were the shipped trees to grow one. The function is the innermost enclosing named function
    (lambdas and control blocks are looked through); a read in a constructor's member-initialiser list names the
    constructor. None when neither applies (a namespace-scope initialiser)."""
    found = {}
    base = os.path.join(root, RECOMP)
    for path in _files(root, SHIPPED_TREES):
        if os.path.basename(path) == REGISTRY_FILE:
            continue
        with open(path, "r", encoding="latin-1") as fh:
            text = fh.read()
        if "PS2X_" not in text:
            continue
        code = _code_only(text)
        stack = []
        reads = [(m.start(), m.group(1)) for m in _READ_CALL.finditer(text)
                 if code[m.start():m.start() + 1].strip()]          # the call itself is code, not a comment
        if not reads:
            continue
        ri = 0
        for pos, ch in enumerate(code):
            while ri < len(reads) and reads[ri][0] <= pos:
                offset, name = reads[ri]
                function = _constructor_of(code, offset)
                for brace in ([] if function else reversed(stack)):
                    function = _function_of(code, brace)
                    if function:
                        break
                rel = os.path.relpath(path, base).replace("\\", "/")
                found.setdefault(name, []).append((rel, text.count("\n", 0, offset) + 1, function))
                ri += 1
            if ch == "{":
                stack.append(pos)
            elif ch == "}" and stack:
                stack.pop()
    return found


def citation_problems(root=ROOT, rows=None):
    """A Shipping or Switch row names where its knob is read; this holds the citation to the tree both ways."""
    rows = table(os.path.join(root, os.path.relpath(HEADER, ROOT))) if rows is None else rows
    sites = read_sites(root)
    out = []
    for r in rows:
        if not r["read"]:
            if r["cls"] in CITED_CLASSES:
                out.append("%s is %s and its row cites no read site: end the row with /* read: <file>:<function> */"
                           % (r["name"], r["cls"]))
            continue
        actual = sites.get(r["name"], [])
        for path, function in r["read"]:
            if not os.path.isfile(os.path.join(root, RECOMP, path)):
                out.append("%s cites %s:%s and there is no such file under %s" % (r["name"], path, function, RECOMP))
            elif not any(p == path and f == function for p, _, f in actual):
                out.append("%s cites %s:%s and that function does not read it" % (r["name"], path, function))
        for path, line, function in actual:
            if (path, function) not in r["read"]:
                out.append("%s is read at %s:%d in %s and its row does not cite it"
                           % (r["name"], path, line, function or "no named function"))
    return out


def log_tag_problems(root=ROOT, rows=None):
    """A meaning that names a log line ("[gs-gl stats]") names one the shipped source prints."""
    rows = table(os.path.join(root, os.path.relpath(HEADER, ROOT))) if rows is None else rows
    tags = {t for r in rows for t in _LOG_TAG.findall(r["meaning"])}
    if not tags:
        return []
    seen = set()
    for path in _files(root, SHIPPED_TREES):
        if os.path.basename(path) == REGISTRY_FILE:
            continue
        with open(path, "r", encoding="latin-1") as fh:
            text = fh.read()
        seen.update(t for t in tags if "[" + t + "]" in text)
    return ["%s's meaning names the log line [%s] and no shipped source prints it" % (r["name"], t)
            for r in rows for t in _LOG_TAG.findall(r["meaning"]) if t not in seen]


def problems(root=ROOT):
    """Every disagreement between the registry and the tree, as sentences. [] is the bar."""
    rows = table(os.path.join(root, os.path.relpath(HEADER, ROOT)))
    by_name = {r["name"]: r for r in rows}
    out = []
    lits = literals(root)
    for name in sorted(lits):
        if name not in by_name:
            out.append("%s is read at %s and has no row in knobs.h" % (name, lits[name][0]))
        elif by_name[name]["cls"] == "Test":
            out.append("%s is class Test and a shipped executable names it at %s" % (name, lits[name][0]))
    reads = test_reads(root)
    for name in sorted(reads):
        if name not in by_name:
            out.append("%s is read by ps2x_tests at %s and has no row in knobs.h" % (name, reads[name][0]))
    for r in rows:
        if r["cls"] == "Test" and r["name"] not in reads:
            out.append("%s is class Test and ps2x_tests does not read it: delete the row" % r["name"])
        if r["cls"] in ("Shipping", "Dev", "Switch") and r["name"] not in lits:
            out.append("%s has a row in knobs.h and no shipped executable reads it: delete the row" % r["name"])
    harness = harness_names(root)
    for name in sorted(harness):
        if name not in by_name and name not in HARNESS_ONLY:
            out.append("%s is used by the harness at %s and the runtime does not know it (a deleted knob, or a typo)"
                       % (name, harness[name][0]))
    pending = {p.replace("\\", "/") for p in RAW_GETENV_PENDING}
    for site in raw_getenv_sites(root):
        if site.rsplit(":", 1)[0] not in pending:
            out.append("%s calls getenv on a PS2X_* name: read it with ps2x::knob (ps2x/knobs.h)" % site)
    for site in helper_getenv_sites(root):
        if site.rsplit(":", 1)[0] not in pending:
            out.append("%s calls getenv with a name it was handed: read it with ps2x::knob (ps2x/knobs.h)" % site)
    for site in early_reads(root):
        out.append("%s reads a knob while initialising a namespace-scope object, before main() has seen --dev: "
                   "make it a function with a function-local static" % site)
    out.extend(accessor_mismatches(root, rows))
    out.extend(citation_problems(root, rows))
    out.extend(log_tag_problems(root, rows))
    return out


_CLASS_TITLES = [
    ("Shipping", "Shipping settings",
     "Player-facing. Each is a field of `config.json` that the launcher (and a bare run of `socom2`) turns into "
     "this variable. Always honoured. Through the launcher `config.json` wins over an inherited variable; in a "
     "bare run or a harness run the variable wins over `config.json`."),
    ("Switch", "The switch",
     "`PS2X_DEV=1` is the same as `--dev` on the runner's command line. `run.sh`, `scripts/parity/env.sh` and the "
     "parity harness set it; the launcher never does, and it removes inherited `PS2X_*` variables from the "
     "game's environment unless it was itself started with `PS2X_DEV=1`."),
    ("Dev", "Developer knobs",
     "Probes, traces, dumps and A/B switches. **Ignored unless the process is in developer mode**; the game's "
     "`[knobs]` log line names the ones it ignored. A `Presence` knob is switched on by any value, including `0`."),
    ("Test", "Test-only",
     "Read by `ps2x_tests`, never by a shipped executable."),
]


def _cell(text):
    return text.replace("|", "\\|")


def render(rows=None):
    rows = table() if rows is None else rows
    out = ["# Knobs", "",
           "Generated by `python -m tools_py.knobs write` from "
           "`third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h`. **Do not edit**: change the header and "
           "regenerate. `tools_py/tests/test_knobs_registry.py` fails when this file is stale, when the source reads "
           "a `PS2X_*` name that has no row, and when a row is read by nothing. A Shipping or Switch row names the "
           "function that reads it (under `third_party/ps2recomp/`); `tools_py/tests/test_knob_read_sites.py` fails "
           "when that function no longer reads the name or a read is not cited.", "",
           "%d names: %s." % (len(rows), ", ".join("%d %s" % (sum(1 for r in rows if r["cls"] == cls), cls)
                                                   for cls, _, _ in _CLASS_TITLES)), ""]
    for cls, title, blurb in _CLASS_TITLES:
        mine = [r for r in rows if r["cls"] == cls]
        if not mine:
            continue
        cited = cls in CITED_CLASSES
        out += ["## " + title, "", blurb, "",
                "| Name | Kind | Default | Meaning |" + (" Read in |" if cited else ""),
                "|---|---|---|---|" + ("---|" if cited else "")]
        for r in mine:
            default = "`%s`" % _cell(r["default"]) if r["default"] else "unset"
            line = "| `%s` | %s | %s | %s |" % (r["name"], r["kind"], default, _cell(r["meaning"]))
            if cited:
                line += " %s |" % "<br>".join("`%s` `%s`" % (path, function) for path, function in r.get("read", []))
            out.append(line)
        out.append("")
    out += ["## Harness-only names", "",
            "Used by the scripts and the Python harness; no C++ reads them: " +
            ", ".join("`%s`" % n for n in sorted(HARNESS_ONLY)) + ".", ""]
    return "\n".join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else "check"
    if command == "write":
        with open(DOC, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(render())
        print("wrote %s (%d names)" % (os.path.relpath(DOC, ROOT), len(table())))
        return 0
    if command == "sites":
        found = literals()
        for name in sorted(found):
            print("%-36s %s" % (name, " ".join(found[name])))
        return 0
    if command == "check":
        found = problems()
        try:
            with open(DOC, "r", encoding="utf-8") as fh:
                if fh.read() != render():
                    found.append("docs/KNOBS.md is stale: python -m tools_py.knobs write")
        except OSError:
            found.append("docs/KNOBS.md is missing: python -m tools_py.knobs write")
        for line in found:
            print(line)
        return 1 if found else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
