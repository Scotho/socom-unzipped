"""Documentation maintenance: the registry in docs/DOC_MAINTENANCE.md, held to the tree.

Why this exists: on 2026-09-22 an audit of `docs/ROADMAP.md` found it two sprints and two wrong
instructions past its usefulness, and the same pass found `docs/HANDOFF.md` offering the next free
ruling number as R179 while R241 was in use -- a collision that had already happened once. The
difference between the documents that stayed true and the ones that rotted was not care; it was
whether anything could fail. This module is the thing that fails.

It is deliberately small. Five checks, each one aimed at a rot mechanism that actually bit this
project. Nothing here fails on a calendar: a test that reddens because a week passed gets disabled,
and then the check is worse than nothing. Cadence is the sprint-close review in
`docs/DOC_MAINTENANCE.md`; this module only enforces what is mechanically true at any moment.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = "docs/DOC_MAINTENANCE.md"   # repo-relative, so tests can point ROOT at a planted tree

CLASSES = {
    "L": "Live -- must be true right now",
    "G": "Generated -- a tool writes it, a test holds it to its source",
    "N": "Narrative -- history and pointers, no live state",
    "S": "Snapshot -- frozen at its date, never updated",
    "C": "Contract -- rules that change only by decision",
    "A": "Archive -- superseded, kept because things cite it",
}

# What the registry must account for, one row each. Everything outside these globs is classified by
# location instead (docs/research/**, docs/superpowers/**, docs/audits/** are S; third_party/** and
# server/horizon-server/** are vendored; fixture READMEs belong to their fixtures). The rule is in
# docs/DOC_MAINTENANCE.md section 2.
COVERED = (
    ("", ("README.md", "CONTRIBUTING.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md")),
    ("docs", None),
    ("docs/parity", None),
    ("docs/story", None),
    ("docs/archive", None),
)

# Suite counts. docs/DEVELOPING.md owns the *current* ones and may state them bare; everywhere else a
# count must be a DATED fact -- a date on the same line -- because that is the difference between a
# record ("764/764 on 2026-09-21", true forever) and a baseline ("baselines: C++ 686/686", which rots.
# It had rotted in four places by 2026-09-22). This is the mechanical half of section 6's rule: if a
# claim cannot be checked, do not make it; a dated one can always be checked.
COUNT_OWNER = "docs/DEVELOPING.md"
COUNT_PATTERNS = (
    re.compile(r"Total Tests:\s*\d+"),
    re.compile(r"\bRan\s+\d{3,}\s+tests\b"),
    re.compile(r"\b(?:C\+\+|ps2x_tests)\s+\d{3,}\s*/\s*\d{3,}\b"),
)

# The counter has two homes on purpose: HANDOFF's bare line (read first by a new controller) and
# CURRENT_SPRINT's, which says which rulings belong to what. Two copies are safe only because this
# module makes them agree -- on 2026-09-22 they said R242 and R241 while R240 was the highest in use.
RULING_LINE = re.compile(r"(?:Next free ruling number|next ruling)\s*:\s*\*{0,2}R(\d+)\*{0,2}", re.I)
COUNTER_DOCS = ("docs/HANDOFF.md", "docs/CURRENT_SPRINT.md")
RULING_ANY = re.compile(r"\bR(\d{2,3})\b")
DATE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*\*{0,2}([LGNSCA])\*{0,2}\s*\|")


def _read(relpath):
    with open(os.path.join(ROOT, relpath), "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def registry():
    """[{path, cls}] parsed from the registry table. Rows are `path` | CLASS | ..."""
    rows = []
    for line in _read(REGISTRY).split("\n"):
        m = ROW.match(line.strip())
        if m:
            rows.append({"path": m.group(1), "cls": m.group(2)})
    return rows


def covered_files():
    """Every markdown file the registry must account for, as repo-relative posix paths."""
    found = []
    for folder, explicit in COVERED:
        base = os.path.join(ROOT, folder) if folder else ROOT
        if explicit is not None:
            for name in explicit:
                if os.path.isfile(os.path.join(base, name)):
                    found.append(("%s/%s" % (folder, name)).lstrip("/"))
            continue
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name.lower().endswith(".md") and os.path.isfile(os.path.join(base, name)):
                found.append("%s/%s" % (folder, name))
    return sorted(set(found))


def by_class(cls):
    return [r["path"] for r in registry() if r["cls"] == cls]


def head(relpath, lines=15):
    return "\n".join(_read(relpath).split("\n")[:lines])


def max_ruling():
    """The highest R<n> in use across the live documents, and where it was found."""
    best, where = 0, None
    # Rulings are numbered where they are made: the live documents AND the plans' own "## Rulings"
    # sections (house convention since Sprint 5). A plan-only ruling not scanned here made the
    # counter read one too high on 2026-09-22, the first night the check ran.
    plans_dir = os.path.join(ROOT, "docs", "superpowers", "plans")
    plans = []
    if os.path.isdir(plans_dir):
        plans = ["docs/superpowers/plans/" + n for n in sorted(os.listdir(plans_dir)) if n.endswith(".md")]
    for path in by_class("L") + ["docs/STATUS.md"] + plans:
        if not os.path.isfile(os.path.join(ROOT, path)):
            continue
        for line in _read(path).split("\n"):
            # The counter line itself names the number that is NOT yet in use.
            if RULING_LINE.search(line):
                continue
            for m in RULING_ANY.finditer(line):
                n = int(m.group(1))
                if n > best:
                    best, where = n, path
    return best, where


def ruling_counters():
    """{path: number} for every document that offers a next-free ruling number."""
    out = {}
    for path in COUNTER_DOCS:
        if not os.path.isfile(os.path.join(ROOT, path)):
            continue
        m = RULING_LINE.search(_read(path))
        if m:
            out[path] = int(m.group(1))
    return out


def next_free_ruling():
    """The number docs/HANDOFF.md offers, or None when the line is missing."""
    return ruling_counters().get("docs/HANDOFF.md")


def count_offenders():
    """Registered documents stating a suite count with no date on the line to pin it to."""
    bad = []
    for row in registry():
        path = row["path"]
        if path == COUNT_OWNER or row["cls"] == "A":
            continue
        if not os.path.isfile(os.path.join(ROOT, path)):
            continue
        heading_dated = False
        for i, line in enumerate(_read(path).split("\n"), 1):
            if line.startswith("#"):
                # A dated log entry dates its whole section: STATUS is written that way.
                heading_dated = bool(DATE.search(line))
            if DATE.search(line) or heading_dated:
                continue
            for pat in COUNT_PATTERNS:
                m = pat.search(line)
                if m:
                    bad.append((path, i, m.group(0)))
                    break
    return bad


def undated_snapshots():
    """Class-S files with no date in the filename and none in the first 15 lines."""
    bad = []
    for path in by_class("S"):
        if not os.path.isfile(os.path.join(ROOT, path)):
            continue
        if DATE.search(os.path.basename(path)) or DATE.search(head(path)):
            continue
        bad.append(path)
    return bad


def silent_archives():
    """Class-A files whose first 15 lines do not say they are archived or superseded."""
    bad = []
    for path in by_class("A"):
        if not os.path.isfile(os.path.join(ROOT, path)):
            continue
        if re.search(r"[Aa]rchiv|[Ss]upersed|[Rr]eplaced by", head(path)):
            continue
        bad.append(path)
    return bad


def report():
    """One dict for a human or a close-out step."""
    reg = registry()
    listed = [r["path"] for r in reg]
    files = covered_files()
    hi, where = max_ruling()
    return {
        "rows": len(reg),
        "unregistered": [p for p in files if p not in listed],
        "missing_files": [p for p in listed if not os.path.isfile(os.path.join(ROOT, p))],
        "duplicate_rows": sorted({p for p in listed if listed.count(p) > 1}),
        "max_ruling": hi,
        "max_ruling_in": where,
        "next_free_ruling": next_free_ruling(),
        "count_offenders": count_offenders(),
        "undated_snapshots": undated_snapshots(),
        "silent_archives": silent_archives(),
    }


def main(argv=None):
    r = report()
    print("doc registry: %d rows, %d files covered" % (r["rows"], len(covered_files())))
    print("rulings: highest in use R%d (%s); HANDOFF offers R%s"
          % (r["max_ruling"], r["max_ruling_in"], r["next_free_ruling"]))
    bad = 0
    for key in ("unregistered", "missing_files", "duplicate_rows", "count_offenders",
                "undated_snapshots", "silent_archives"):
        if r[key]:
            bad += len(r[key])
            print("%s:" % key)
            for item in r[key]:
                print("   ", item)
    if r["next_free_ruling"] != r["max_ruling"] + 1:
        bad += 1
        print("ruling counter: HANDOFF says R%s, should be R%d" % (r["next_free_ruling"], r["max_ruling"] + 1))
    print("OK" if not bad else "%d problem(s)" % bad)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
