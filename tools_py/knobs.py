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

# Sprint 9 Goal 3 Task 4: files that still call getenv("PS2X_...") directly. Each batch takes its files off
# this list in the commit that migrates them; test_knobs_registry fails if a listed file has no raw read left,
# and if an unlisted file has one. When the set is empty, delete this comment and leave the empty set.
RAW_GETENV_PENDING = {
    "third_party/ps2recomp/ps2xIOP/src/modules/snd989.cpp",
    "third_party/ps2recomp/ps2xLauncher/src/main.cpp",
    "third_party/ps2recomp/ps2xRuntime/include/ps2_runtime_macros.h",
    "third_party/ps2recomp/ps2xRuntime/include/runtime/host_gamepad.h",
    "third_party/ps2recomp/ps2xRuntime/include/runtime/host_gamepad_select.h",
    "third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/Pad.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/host_mic.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/ps2_audio.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/ps2_pad.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/snd989_mixer.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/socom2_hostnet.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/lib/socom2_libnetb.cpp",
    "third_party/ps2recomp/ps2xRuntime/src/main.cpp",
}

_ROW = re.compile(r'^\s*X\("(PS2X_[A-Z0-9_]+)",\s*(\w+),\s*(\w+),\s*"([^"]*)",\s*"([^"]*)"\)', re.M)
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
    """[{name, cls, kind, default, meaning}, ...] in the header's order."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return [{"name": m.group(1), "cls": m.group(2), "kind": m.group(3), "default": m.group(4), "meaning": m.group(5)}
            for m in _ROW.finditer(text)]


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
           "a `PS2X_*` name that has no row, and when a row is read by nothing.", "",
           "%d names: %s." % (len(rows), ", ".join("%d %s" % (sum(1 for r in rows if r["cls"] == cls), cls)
                                                   for cls, _, _ in _CLASS_TITLES)), ""]
    for cls, title, blurb in _CLASS_TITLES:
        mine = [r for r in rows if r["cls"] == cls]
        if not mine:
            continue
        out += ["## " + title, "", blurb, "", "| Name | Kind | Default | Meaning |", "|---|---|---|---|"]
        for r in mine:
            default = "`%s`" % _cell(r["default"]) if r["default"] else "unset"
            out.append("| `%s` | %s | %s | %s |" % (r["name"], r["kind"], default, _cell(r["meaning"])))
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
