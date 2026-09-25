"""Census of a ps2xRecomp output directory and its recomp_run.log, and the diff of two censuses.

Sprint 12 Task 3a (ruling S12-R11): a rename that moves a decoded range is accepted only when the cloud's own
recomp shows no new unmapped or unhandled continuation and no function dropped. This tool reads what the
recompiler wrote and says what changed between two runs.

What is read, and where the recompiler emits it (third_party/ps2recomp/ps2xRecomp/src/lib/):
  * a recompiled function's file (function_emitter.cpp, generateFunction):
        // Function: <raw csv Name>              <- unsanitised, as the csv or the JAL scan named it; a sidecar
                                                    name instead, followed by `// Name source: <names> row 0x%08x
                                                    (map name <csv Name>)` (Sprint 13 N2; not read here)
        // Address: 0x<start> - 0x<end>          <- lower-case hex, no padding; <end> is exclusive
        void <identifier>(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime) {
    The Address line is the only place the END is emitted; ps2_recompiled_functions.h and
    register_functions.cpp (function_table_emitter.cpp) carry the identifier and the start only.
  * a stub's file (ps2_recompiler.cpp, generateOutput, function.isStub/isSkipped): no Function or Address line,
        void <identifier>(...) { ... ps2_stubs::<target>(rdram, ctx, runtime); }
    so a stub's start is its identifier's `_0x<start>` suffix, its end and csv name are None, kind "stub".
  * the identifier is sanitize(Name) + "_0x<start hex>" (ps2_recompiler.cpp, generateOutput's makeName), except
    `entry_<start>` which gets `_0x<end>`; the identifier is read from the `void` line, not the filename, because
    clampFilenameLength cuts long file names to 100 characters.
  * recomp_run.log (recompiler_reporter.cpp, printSummary): one event line per report,
        [error] unhandled-instruction function=<name> addr=0x<pc> - <message> raw=0x<word>
        [warning] unmapped-continuation function=<name> addr=0x<pc> - <kind> 0x<pc> of 0x<src> lies in no ...
    The counts are the number of lines containing the category (build.sh's `grep -c`), the addresses are the
    addr= fields of those event lines.

Classes are by the identifier's prefix: FUN_, sub_, thunk_ (thunk_*), caseD_ (caseD_*), entry (entry_0x...),
other. "named" is everything that is neither FUN_ nor sub_.

extents_sha256 is the sha256 of the lines "0x%08x 0x%08x|- <identifier>\\n" sorted by start (end "-" for a stub), so
two runs compare cheaply.

Usage:
  python -m tools_py.recomp_census <output_dir> <recomp_run.log> [--json out.json]
  python -m tools_py.recomp_census --diff a.json b.json [--json diff.json]
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys

FUNC_RE = re.compile(r"^// Function: (.*)$", re.M)
ADDR_RE = re.compile(r"^// Address: 0x([0-9a-fA-F]+) - 0x([0-9a-fA-F]+)\s*$", re.M)
VOID_RE = re.compile(r"^void ([A-Za-z_][A-Za-z0-9_]*)\(uint8_t\* rdram, R5900Context\* ctx, PS2Runtime \*runtime\) \{",
                     re.M)
STUB_TARGET_RE = re.compile(r"(ps2_(?:stubs|syscalls)::[A-Za-z0-9_]+)\(")
SUFFIX_RE = re.compile(r"_0x([0-9a-f]+)$")
EVENT_RE = re.compile(r"\[\w+\] (unhandled-instruction|unmapped-continuation)\b.*? addr=0x([0-9a-fA-F]+)")

CLASSES = ("FUN_", "sub_", "thunk_", "caseD_", "entry", "other")
CATEGORIES = {"unhandled": "unhandled-instruction", "unmapped": "unmapped-continuation"}


def classify(identifier):
    for prefix in ("FUN_", "sub_", "thunk_", "caseD_"):
        if identifier.startswith(prefix):
            return prefix
    if identifier == "entry" or identifier.startswith("entry_"):
        return "entry"
    return "other"


def parse_function_file(text):
    """One generated .cpp -> (start, end, identifier, csv_name, kind, stub_target), or None when it defines
    no guest function (register_functions.cpp, headers)."""
    name = FUNC_RE.search(text)
    addr = ADDR_RE.search(text)
    void = VOID_RE.search(text, name.end() if name else 0)
    if not void:
        return None
    identifier = void.group(1)
    if name and addr:
        return (int(addr.group(1), 16), int(addr.group(2), 16), identifier, name.group(1).rstrip("\r"),
                "code", None)
    suffix = SUFFIX_RE.search(identifier)
    if not suffix:
        return None
    target = STUB_TARGET_RE.search(text[void.end():])
    return (int(suffix.group(1), 16), None, identifier, None, "stub", target.group(1) if target else None)


def parse_log(log_path):
    counts = {k: 0 for k in CATEGORIES}
    addrs = {k: [] for k in CATEGORIES}
    by_category = {v: k for k, v in CATEGORIES.items()}
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            for key, category in CATEGORIES.items():
                if category in line:
                    counts[key] += 1
            m = EVENT_RE.search(line)
            if m:
                addrs[by_category[m.group(1)]].append(int(m.group(2), 16))
    return counts, {k: sorted(v) for k, v in addrs.items()}


def extents_digest(extents):
    lines = []
    for start in sorted(extents):
        e = extents[start]
        end = "-" if e["end"] is None else "0x%08x" % e["end"]
        lines.append("0x%08x %s %s\n" % (start, end, e["identifier"]))
    return hashlib.sha256("".join(lines).encode("ascii")).hexdigest()


def census(output_dir, log_path):
    names = sorted(os.listdir(output_dir))
    extents = {}
    duplicates = []
    for fname in names:
        if not fname.endswith(".cpp"):
            continue
        with open(os.path.join(output_dir, fname), encoding="utf-8", errors="replace") as fh:
            parsed = parse_function_file(fh.read())
        if parsed is None:
            continue
        start, end, identifier, csv_name, kind, target = parsed
        if start in extents:
            duplicates.append(start)
        extents[start] = {"end": end, "identifier": identifier, "csv_name": csv_name, "kind": kind,
                          "file": fname, "stub_target": target}
    classes = collections.Counter(classify(e["identifier"]) for e in extents.values())
    counts, addrs = parse_log(log_path)
    return {
        "files": len(names),
        "functions": len(extents),
        "classes": {c: classes.get(c, 0) for c in CLASSES},
        "named": len(extents) - classes.get("FUN_", 0) - classes.get("sub_", 0),
        "stubs": sum(1 for e in extents.values() if e["kind"] == "stub"),
        "duplicate_starts": sorted(duplicates),
        "unhandled": counts["unhandled"],
        "unmapped": counts["unmapped"],
        "unhandled_addrs": addrs["unhandled"],
        "unmapped_addrs": addrs["unmapped"],
        "extents": extents,
        "extents_sha256": extents_digest(extents),
    }


def to_json(c):
    out = dict(c)
    out["extents"] = {"0x%08x" % s: e for s, e in sorted(c["extents"].items())}
    return out


def from_json(d):
    out = dict(d)
    out["extents"] = {int(s, 16): e for s, e in d["extents"].items()}
    return out


def load(path):
    with open(path, encoding="utf-8") as fh:
        return from_json(json.load(fh))


def _multiset_delta(a, b):
    ca, cb = collections.Counter(a), collections.Counter(b)
    return sorted((cb - ca).elements()), sorted((ca - cb).elements())


def diff(a, b):
    ea, eb = a["extents"], b["extents"]
    common = sorted(set(ea) & set(eb))
    renamed = [(s, ea[s]["identifier"], eb[s]["identifier"]) for s in common
               if ea[s]["identifier"] != eb[s]["identifier"]]
    extents_changed = [(s, ea[s]["end"], eb[s]["end"]) for s in common if ea[s]["end"] != eb[s]["end"]]
    kind_changed = [(s, ea[s]["kind"], eb[s]["kind"]) for s in common if ea[s]["kind"] != eb[s]["kind"]]
    out = {
        "files": (a["files"], b["files"]),
        "classes": {c: (a["classes"].get(c, 0), b["classes"].get(c, 0)) for c in CLASSES},
        "renamed": renamed,
        "extents_changed": extents_changed,
        "kind_changed": kind_changed,
        "only_in_a": sorted(set(ea) - set(eb)),
        "only_in_b": sorted(set(eb) - set(ea)),
    }
    for key in CATEGORIES:
        appeared, vanished = _multiset_delta(a[key + "_addrs"], b[key + "_addrs"])
        out[key] = {"a": a[key], "b": b[key], "delta": b[key] - a[key],
                    "appeared": appeared, "vanished": vanished}
    # S12-R11: no function dropped, no new unmapped or unhandled.
    out["r11_ok"] = (not out["only_in_a"] and not out["unmapped"]["appeared"] and not out["unhandled"]["appeared"]
                     and out["unmapped"]["delta"] <= 0 and out["unhandled"]["delta"] <= 0)
    return out


def summary_line(c):
    k = c["classes"]
    return ("recomp: %d files, unhandled=%d, unmapped=%d; %d functions: FUN_=%d sub_=%d named=%d "
            "(thunk_=%d caseD_=%d entry=%d other=%d), stubs=%d; extents_sha256=%s"
            % (c["files"], c["unhandled"], c["unmapped"], c["functions"], k["FUN_"], k["sub_"], c["named"],
               k["thunk_"], k["caseD_"], k["entry"], k["other"], c["stubs"], c["extents_sha256"]))


def _h(v):
    return "-" if v is None else "0x%x" % v


def diff_report(d, limit=20):
    lines = ["files %d -> %d" % d["files"],
             "classes " + ", ".join("%s %d->%d" % (c, *d["classes"][c]) for c in CLASSES)]
    for key, fmt in (("renamed", lambda r: "%s %s -> %s" % (_h(r[0]), r[1], r[2])),
                     ("extents_changed", lambda r: "%s end %s -> %s" % (_h(r[0]), _h(r[1]), _h(r[2]))),
                     ("kind_changed", lambda r: "%s %s -> %s" % (_h(r[0]), r[1], r[2])),
                     ("only_in_a", _h), ("only_in_b", _h)):
        rows = d[key]
        lines.append("%s: %d" % (key, len(rows)))
        lines.extend("  " + fmt(r) for r in rows[:limit])
        if len(rows) > limit:
            lines.append("  ... %d more" % (len(rows) - limit))
    for key in CATEGORIES:
        x = d[key]
        lines.append("%s: %d -> %d (delta %+d), appeared %d, vanished %d"
                     % (key, x["a"], x["b"], x["delta"], len(x["appeared"]), len(x["vanished"])))
        for tag in ("appeared", "vanished"):
            if x[tag]:
                lines.append("  %s: %s%s" % (tag, " ".join(_h(v) for v in x[tag][:limit]),
                                            " ..." if len(x[tag]) > limit else ""))
    lines.append("S12-R11 (no function dropped, no new unmapped/unhandled): %s" % ("OK" if d["r11_ok"] else "FAIL"))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m tools_py.recomp_census", description=__doc__.split("\n")[0])
    p.add_argument("paths", nargs=2, metavar="PATH",
                   help="<output_dir> <recomp_run.log>, or with --diff <a.json> <b.json>")
    p.add_argument("--diff", action="store_true", help="diff two census JSON files")
    p.add_argument("--json", metavar="OUT", help="write the census (or the diff) as JSON")
    args = p.parse_args(argv)
    if args.diff:
        result = diff(load(args.paths[0]), load(args.paths[1]))
        print(diff_report(result))
    else:
        c = census(args.paths[0], args.paths[1])
        result = to_json(c)
        print(summary_line(c))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1, sort_keys=True)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
