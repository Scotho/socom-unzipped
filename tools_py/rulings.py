"""The rulings page: every ruling, its status and its home, generated (Sprint 14 Task D1).

`python -m tools_py.rulings` writes `docs/RULINGS.md`; `--check` exits 1 when the file on disk differs from a
fresh render and prints the head of the diff. The global rulings come from `docmaint.ruling_records()` -- the
same definitions, ledger rows and vacancy notes checks 9 and 10 read (docs/DOC_MAINTENANCE.md section 4) -- so
the page and the checks can never disagree about what a ruling is. The sprint-local names `S12-R<n>` and
`S13-R<n>` (R264, R273) have no parser in docmaint; they are read here from the same documents, in the same
house shape, and listed in their own groups.

Status, strongest first (a definition and its ledger row are both read; the stronger wins):
  retracted   the definition line is struck (`~~`), its text says RETRACTED, or its ledger row's status cell
              opens with "retracted"
  withdrawn   the text says WITHDRAWN (or "withdrawn by"), or the row's cell opens with "withdrawn"
  superseded  the text says "superseded by", "amended by", "overturned by" or "retired by" a ruling, or the
              row's cell opens with one of those, or a later ruling's own words say it "overturns", "supersedes"
              or "retires" this one (R92, S12-R10); "amends", "narrows" and "corrects" leave it standing
  vacant      a vacancy note (`R<n> -- vacant: <reason>`), or a row whose cell opens with "(deliberately) vacant"
  active      anything else; a row that opens with "stands" is active even when it goes on to say a part of
              the ruling was amended (the ledger's own verdict comes first)
"""
import argparse
import difflib
import os
import re
import sys

from tools_py import docmaint

PAGE = "docs/RULINGS.md"
STATUSES = ("active", "superseded", "retracted", "withdrawn", "vacant")
STRENGTH = {"active": 0, "vacant": 1, "superseded": 2, "withdrawn": 3, "retracted": 4}
MAX_LINE = 160

# A sprint-local definition, in the lead shape docmaint.RULING_DEF_LEAD accepts for R<n>.
LOCAL_DEF = re.compile(
    r"^\s*(?:[-*+]\s+|\d+\.\s+)?\*\*(S\d{1,2})-R(\d{1,3})(?=\*\*|\s*[(:,.]|\s+(?:—|–|--?)\s)")
# A continuation line ends at a blank line, a new list item, a heading, a table row or a quote.
BREAK = re.compile(r"^\s*(?:$|[-*+]\s|\d+\.\s|#|\||>)")
REF = r"(?:S\d{1,2}-R\d{1,3}|R\d{2,3}b?)\b"
TEXT_RETRACTED = re.compile(r"\bRETRACTED\b")
TEXT_WITHDRAWN = re.compile(r"\bWITHDRAWN\b|\b[Ww]ithdrawn by\b")
TEXT_SUPERSEDED = re.compile(r"\b(?:superseded|amended|overturned|retired) by\s+\**" + REF, re.I)
TEXT_REPLACES = re.compile(r"\b(?:overturns|supersedes|retires)\s+\**(S\d{1,2}-R\d{1,3}|R\d{2,3}b?)\b")
CELL_LEADS = (
    ("retracted", re.compile(r"retracted\b")),
    ("withdrawn", re.compile(r"withdrawn\b")),
    ("superseded", re.compile(r"(?:superseded|amended|overturned|retired) by\b")),
    ("vacant", re.compile(r"(?:deliberately\s+)?vacant\b")),
)
# What is stripped between a ruling's number and its text: bold marks, the (date, task) note, a second
# number of a shared label ("**R265**, **R266** (...)"), the separator.
LABEL_TAIL = re.compile(r"^(?:\s+|\*+|\([^()\n]*\)|,\s*(?:and\s+)?\*\*R\d{2,3}\b|—|–|--?|:|,|\.)")
SENTENCE = re.compile(r"^(.+?[.!?])(?=\s+[A-Z(\"'`“]|\s*$)")


def _cells(line):
    """A markdown table row's cells, `|` inside backticks kept."""
    cells, cur, tick = [], "", False
    for ch in line.strip().strip("|"):
        if ch == "`":
            tick = not tick
        if ch == "|" and not tick:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
    cells.append(cur.strip())
    return cells


def _paragraph(lines, i):
    """The definition on line i (1-based) and its continuation lines, joined."""
    out = [lines[i - 1]]
    for line in lines[i:]:
        if BREAK.match(line):
            break
        out.append(line)
    return " ".join(part.strip() for part in out)


def _clean(text):
    text = re.sub(r"<!--.*?-->", "", text)   # a docmaint marker is the source line's, not the ruling's
    text = text.replace("**", "").replace("~~", "")
    return re.sub(r"\s+", " ", text).strip()


def _first_sentence(text):
    text = _clean(text)
    m = SENTENCE.match(text)
    if m:
        text = m.group(1)
    if len(text) > MAX_LINE:
        text = text[:MAX_LINE - 1].rstrip() + "…"
    if text.count("`") % 2:
        # A cut inside a code span: an open backtick would pair with the Home cell's and swallow the
        # column bar, so the partial span goes.
        text = text[:text.rindex("`")].rstrip() + "…"
    return text


def _after_label(text, start):
    """The ruling's own words: what follows its label, with the label's tail stripped."""
    rest = text[start:]
    while True:
        m = LABEL_TAIL.match(rest)
        if not m or not m.group(0):
            return rest
        rest = rest[m.end():]


def _text_status(struck, para):
    if struck or TEXT_RETRACTED.search(para):
        return "retracted"
    if TEXT_WITHDRAWN.search(para):
        return "withdrawn"
    if TEXT_SUPERSEDED.search(para):
        return "superseded"
    return "active"


def cell_status(cell):
    """A ledger row's status cell -> a status, or None when its opening words are none the page knows."""
    lead = re.sub(r"^[\s*_~]+", "", cell).lower()
    for status, pat in CELL_LEADS:
        if pat.match(lead):
            return status
    if re.match(r"stands\b|rewritten\b|closed\b|carried\b|done\b", lead):
        return "active"
    return None


def _stronger(a, b):
    return a if STRENGTH[a] >= STRENGTH[b] else b


def _lines(path, cache):
    if path not in cache:
        cache[path] = docmaint._read(path).split("\n")
    return cache[path]


def _label_end(line, number):
    """Where the label of `number` ends on its definition line (docmaint's shapes), or 0."""
    n = re.escape(number.rstrip("b")[1:])
    for pat in (r"\*\*(?:Ruling\s+)?R%s(?!\d)" % n, r"\bR%s(?!\d)" % n):
        m = re.search(pat, line)
        if m:
            return m.end()
    return 0


def _local_records():
    """{'S12-R4': [(path, line)]}: the sprint-local definitions, fences and quotes skipped as docmaint does."""
    defs = {}
    for path in docmaint.ruling_definition_sources():
        if not os.path.isfile(os.path.join(docmaint.ROOT, path)):
            continue
        fenced = False
        for i, line in enumerate(docmaint._read(path).split("\n"), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced or line.lstrip().startswith(">"):
                continue
            m = LOCAL_DEF.match(line)
            if m:
                defs.setdefault("%s-R%s" % (m.group(1), m.group(2)), []).append((path, i))
    return defs


def _group(number):
    m = re.match(r"(S\d+)-", number)
    return m.group(1) if m else "global"


def _sort_key(number):
    """Page order: global before the namespaces (newest namespace first), newest number first inside each."""
    m = re.match(r"(?:S(\d+)-)?R(\d+)(b?)$", number)
    sprint = int(m.group(1)) if m.group(1) else 10 ** 6
    return (-sprint, -int(m.group(2)), "" if m.group(3) else "~")


def _rows():
    defs, ledger, vacant = docmaint.ruling_records()
    local = _local_records()
    cache, out, said = {}, [], []   # said: (number, text) -- what each ruling's own words say of others
    for number in set(defs) | set(ledger) | set(vacant) | set(local):
        date, line, status, home = None, "", "active", None
        if number in defs or number in local:
            path, i = (defs.get(number) or local[number])[0]
            text = _lines(path, cache)[i - 1]
            para = _paragraph(_lines(path, cache), i)
            if number in local:
                start = LOCAL_DEF.match(text).end()
            else:
                start = _label_end(para, number)
            d = docmaint.DATE.search(text)
            date = d.group(0) if d else None
            rest = _after_label(para, start)
            struck = rest.startswith("~~") or "~~" in para[:start]
            line = _first_sentence(rest)
            status = _text_status(struck, para)   # the label's note can carry it: R122's
            home = "%s:%d" % (path, i)
            said.append((number, para))
        if number in vacant:
            path, i = vacant[number][0]
            status = _stronger(status, "vacant")
            if home is None:
                text = _lines(path, cache)[i - 1]
                m = docmaint.RULING_VACANT.search(text)
                line = _first_sentence(text[m.end():])
                home = "%s:%d" % (path, i)
        if number in ledger:
            path, i = ledger[number][0]
            said.append((number, _lines(path, cache)[i - 1]))
            cells = _cells(_lines(path, cache)[i - 1])
            found = cell_status(cells[-1]) if len(cells) >= 2 else None
            if found:
                status = _stronger(status, found)
            if home is None:
                said_cell = cells[1] if len(cells) > 1 else ""
                if said_cell.strip("-– ") == "":   # R229's row has no decision; its status cell says why
                    said_cell = cells[-1]
                line = _first_sentence(said_cell)
                home = "%s:%d" % (path, i)
        out.append({"number": number, "date": date, "line": line, "status": status, "home": home})
    # The active voice, said by the later ruling: "it overturns R92", "retires S12-R10". A partial change
    # ("amends", "narrows", "corrects") leaves the earlier ruling standing and is not read here.
    replaced = {m.group(1) for number, text in said for m in TEXT_REPLACES.finditer(text) if m.group(1) != number}
    for r in out:
        if r["number"] in replaced:
            r["status"] = _stronger(r["status"], "superseded")
    return sorted(out, key=lambda r: _sort_key(r["number"]))


def rows(root=None):
    """[{number, date, line, status, home}] in page order; `root` points the scan at another tree."""
    saved = docmaint.ROOT
    if root is not None:
        docmaint.ROOT = root
    try:
        return _rows()
    finally:
        docmaint.ROOT = saved


def undecided(root=None):
    """The ledger rows whose status cell opens with words cell_status() does not know (shown as active)."""
    saved = docmaint.ROOT
    if root is not None:
        docmaint.ROOT = root
    try:
        _, ledger, _ = docmaint.ruling_records()
        out = []
        for number, locs in ledger.items():
            path, i = locs[0]
            cells = _cells(docmaint._read(path).split("\n")[i - 1])
            if len(cells) < 2 or cell_status(cells[-1]) is None:
                out.append(number)
        return sorted(out, key=_sort_key)
    finally:
        docmaint.ROOT = saved


def _esc(text):
    return text.replace("|", "\\|")


def render(rows):
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    groups = []
    for r in rows:
        g = _group(r["number"])
        if g not in groups:
            groups.append(g)
    n_global = sum(1 for r in rows if _group(r["number"]) == "global")
    out = [
        "# Rulings: every ruling and its status",
        "",
        "> **Generated -- do not edit.** Written by `python -m tools_py.rulings` from the ruling records "
        "`tools_py/docmaint.py` reads for checks 9 and 10 (`ruling_records()`: the definitions in the plans, the "
        "sprint file and `docs/archive/`, the ledger rows and the vacancy notes), plus the sprint-local "
        "`S12-R<n>` and `S13-R<n>` definitions in the same documents. Change the source and regenerate; "
        "`python -m tools_py.rulings --check` exits 1 when this file is stale. The status rules are the module's "
        "docstring; the conventions are `docs/DOC_MAINTENANCE.md` section 4.",
        "",
        "%d rulings (%d global, %d sprint-local): %s." % (
            len(rows), n_global, len(rows) - n_global,
            ", ".join("%d %s" % (counts[s], s) for s in STATUSES)),
        "",
        "*Home* is where the ruling is written: its definition, else its ledger row, else its vacancy note. "
        "*The line* is its first sentence, cut at %d characters." % MAX_LINE,
    ]
    for g in groups:
        members = [r for r in rows if _group(r["number"]) == g]
        title = "Global (R<n>), newest first" if g == "global" else \
            "%s (the Sprint %s namespace, %s-R<n>)" % (g, g[1:], g)
        out += ["", "## " + title, "", "%d rulings." % len(members), "",
                "| Number | Date | Status | The line | Home |", "|---|---|---|---|---|"]
        for r in members:
            out.append("| %s | %s | %s | %s | `%s` |" % (
                r["number"], r["date"] or "--", r["status"], _esc(r["line"]) or "--", r["home"]))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tools_py.rulings", description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when %s differs from a fresh render" % PAGE)
    ap.add_argument("--root", default=None, help="the tree to read and write (default: this repository)")
    args = ap.parse_args(argv)
    root = args.root or docmaint.ROOT
    fresh = render(rows(root=root))
    target = os.path.join(root, PAGE)
    if args.check:
        try:
            with open(target, "r", encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            print("rulings: %s is missing; run python -m tools_py.rulings" % PAGE)
            return 1
        if current == fresh:
            print("rulings: %s is current" % PAGE)
            return 0
        diff = list(difflib.unified_diff(current.split("\n"), fresh.split("\n"),
                                         "%s (on disk)" % PAGE, "%s (fresh render)" % PAGE, lineterm=""))
        sys.stdout.write("\n".join(diff[:40]) + "\n")
        if len(diff) > 40:
            print("... %d more diff lines" % (len(diff) - 40))
        print("rulings: %s is stale; run python -m tools_py.rulings" % PAGE)
        return 1
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fresh)
    counts = {s: sum(1 for line in fresh.split("\n") if ("| %s |" % s) in line) for s in STATUSES}
    print("rulings: wrote %s (%s)" % (PAGE, ", ".join("%d %s" % (counts[s], s) for s in STATUSES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
