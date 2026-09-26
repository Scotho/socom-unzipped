"""The rulings page: every ruling, its status and its home, generated (Sprint 14 Task D1).

`python -m tools_py.rulings` writes `docs/RULINGS.md`; `--check` exits 1 when the file on disk differs from a
fresh render and prints the head of the diff. The global rulings come from `docmaint.ruling_records()` -- the
same definitions, ledger rows and vacancy notes checks 9 and 10 read (docs/DOC_MAINTENANCE.md section 4) -- so
the page and the checks can never disagree about what a ruling is. The sprint-local names `S12-R<n>` and
`S13-R<n>` (R264, R273) have no parser in docmaint; they are read here from the same documents, in the same
house shape, and listed in their own groups.

Status, strongest first (a definition and its ledger row are both read; the stronger wins). "Its own words" are
the ruling's label with its (date, task) note and its first sentence -- never the rest of the paragraph, where a
ruling may name another's RETRACTED -- or its own ledger row's status cell:
  retracted   the definition is struck (`~~`), its own words say RETRACTED, or its row's cell opens "retracted"
  withdrawn   its own words say WITHDRAWN (or "withdrawn by"), or its row's cell opens "withdrawn"
  superseded  its own words say "superseded by", "overturned by" or "retired by" a ruling, or its row's cell
              opens with one of those, or a later ruling's words say it "overturns", "supersedes" or "retires"
              this one (R92, S12-R10)
  vacant      a vacancy note (`R<n> -- vacant: <reason>`), or a row whose cell opens "(deliberately) vacant"
  active      anything else. An amendment leaves a ruling standing, as the ledger treats it: "amended by" in
              its own words, a row that opens "stands" and goes on to say a part was amended or superseded, or
              a later ruling that "amends", "narrows" or "corrects" it -- the row stays active and its line
              ends "(amended: see the ledger)".

Home is the path and a stable anchor -- the ruling's label, its ledger row or its vacancy note -- never a line
number, so the page goes stale only when a ruling changes. Dates come only from the label and its note.
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
CONTEXT = 80   # the sentence shown before a mid-paragraph label's own words, cut here

# A sprint-local definition, in the lead shape docmaint.RULING_DEF_LEAD accepts for R<n>.
LOCAL_DEF = re.compile(
    r"^\s*(?:[-*+]\s+|\d+\.\s+)?\*\*(S\d{1,2})-R(\d{1,3})(?=\*\*|\s*[(:,.]|\s+(?:—|–|--?)\s)")
# A continuation line ends at a blank line, a new list item, a heading, a table row or a quote.
BREAK = re.compile(r"^\s*(?:$|[-*+]\s|\d+\.\s|#|\||>)")
REF = r"(?:S\d{1,2}-R\d{1,3}|R\d{2,3}b?)\b"
TEXT_RETRACTED = re.compile(r"\bRETRACTED\b")
TEXT_WITHDRAWN = re.compile(r"\bWITHDRAWN\b|\b[Ww]ithdrawn by\b")
TEXT_SUPERSEDED = re.compile(r"\b(?:superseded|overturned|retired) by\s+\**" + REF, re.I)
# An amendment leaves a ruling standing (the ledger's "stands as amended by R262"): shown active, flagged.
TEXT_AMENDED = re.compile(r"\b(?:superseded|amended|overturned|narrowed|corrected) by\s+\**" + REF, re.I)
TEXT_AMENDS = re.compile(r"\b(?:amends|narrows|corrects)\s+\**(S\d{1,2}-R\d{1,3}|R\d{2,3}b?)\b")
# A ledger cell that opens "stands" and goes on to say a part was changed: R257's "Amended there already",
# R259's "as amended by R262", R248's "its second half ... is superseded by R250", R238's "as corrected in place".
CELL_AMENDED = re.compile(r"\b(?:amended|superseded|overturned|narrowed)\b|\bas corrected\b|\bcorrected in place\b",
                          re.I)
AMENDED = " (amended: see the ledger)"
TEXT_REPLACES = re.compile(r"\b(?:overturns|supersedes|retires)\s+\**(S\d{1,2}-R\d{1,3}|R\d{2,3}b?)\b")
CELL_LEADS = (
    ("retracted", re.compile(r"retracted\b")),
    ("withdrawn", re.compile(r"withdrawn\b")),
    ("superseded", re.compile(r"(?:superseded|overturned|retired) by\b")),
    ("vacant", re.compile(r"(?:deliberately\s+)?vacant\b")),
)
# What is stripped between a ruling's number and its text: bold marks, the (date, task) note, a second
# number of a shared label ("**R265**, **R266** (...)"), the separator.
LABEL_TAIL = re.compile(r"^(?:\s+|\*+|\([^()\n]*\)|,\s*(?:and\s+)?\*\*R\d{2,3}\b|—|–|--?|:|,|\.)")
# The first words that cannot be read without the sentence before them (R264's "they keep those names"): only these
# earn a mid-paragraph label its "(after: ...)" context; R173's and R184's "the ..." read on their own (S14 D4).
ANTECEDENT = re.compile(r"^(?:they|them|their|it|its|this|that|these|those|the same|both|such)\b", re.I)
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


def _sentence(text):
    """The first sentence of cleaned text, uncut."""
    text = _clean(text)
    m = SENTENCE.match(text)
    return m.group(1) if m else text


def _first_sentence(text):
    text = _sentence(text)
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


def _label_span(line, number):
    """(start, end) of the label of `number` on its definition line (docmaint's shapes), or (0, 0)."""
    n = re.escape(number.rstrip("b")[1:])
    for pat in (r"\*\*(?:Ruling\s+)?R%s(?!\d)" % n, r"\bR%s(?!\d)" % n):
        m = re.search(pat, line)
        if m:
            return m.start(), m.end()
    return 0, 0


def _own_segment(rest, number):
    """One label for several rulings ("**R265**, **R266** (...): R265 the first; R266 the second"): the words
    after `number` up to the next ruling's number, or None when `rest` is not a list of that shape."""
    parts = re.split(r";\s*(?=R\d{2,3}b?\s)", _clean(rest))
    if len(parts) < 2 or not re.match(r"R\d{2,3}b?\s", parts[0]):
        return None
    bare = number.rstrip("b")
    for part in parts:
        m = re.match(r"(R\d{2,3})b?\s+", part)
        if m and m.group(1) == bare:
            return part[m.end():]
    return None


def needs_antecedent(words):
    """True when `words` open with a pronoun or determiner that needs its antecedent (ANTECEDENT)."""
    return bool(ANTECEDENT.match(_clean(words).lstrip("*_ ")))


def _context(before):
    """The sentence just before a label that sits mid-paragraph ("**Rulings.** Sprint 12's rulings are ... **R264**
    (...): they keep those names"), cut at CONTEXT characters; "" when the label opens its paragraph."""
    text = _clean(re.sub(r"^\s*(?:[-*+]\s+|\d+\.\s+)", "", before))
    if not text:
        return ""
    pieces = [p for p in re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'`“])", text) if p]
    ctx = pieces[-1] if pieces else text
    if len(ctx) > CONTEXT:
        ctx = ctx[:CONTEXT - 1].rstrip() + "…"
        if ctx.count("`") % 2:
            ctx = ctx[:ctx.rindex("`")].rstrip() + "…"
    return ctx


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
    amended = set()
    for number in set(defs) | set(ledger) | set(vacant) | set(local):
        date, line, status, home = None, "", "active", None
        if number in defs or number in local:
            path, i = (defs.get(number) or local[number])[0]
            text = _lines(path, cache)[i - 1]
            para = _paragraph(_lines(path, cache), i)
            if number in local:
                begin, start = 0, LOCAL_DEF.match(text).end()
            else:
                begin, start = _label_span(para, number)
            rest = _after_label(para, start)
            label = para[:len(para) - len(rest)]   # the label and its (date, task) note
            segment = _own_segment(rest, number)
            if segment is not None:
                rest = segment                           # a shared label: this ruling's own words only
            own = label + " " + _sentence(rest)     # the only words whose status is this ruling's
            d = docmaint.DATE.search(label)
            date = d.group(0) if d else None
            struck = rest.startswith("~~") or "~~" in label
            # A label mid-paragraph whose words open with a pronoun ("they keep those names") reads only after the
            # sentence before it, which is shown first; any other opening reads on its own.
            ctx = _context(para[:begin]) if segment is None and needs_antecedent(rest) else ""
            line = _first_sentence(("(after: %s) " % ctx if ctx else "") + _sentence(rest))
            status = _text_status(struck, own)       # the label's note can carry it: R122's
            if TEXT_AMENDED.search(own):
                amended.add(number)
            home = "%s **%s**" % (path, number)
            said.append((number, para))
        if number in vacant:
            path, i = vacant[number][0]
            status = _stronger(status, "vacant")
            if home is None:
                text = _lines(path, cache)[i - 1]
                m = docmaint.RULING_VACANT.search(text)
                line = _first_sentence(text[m.end():])
                home = "%s vacancy note %s" % (path, number)
        if number in ledger:
            path, i = ledger[number][0]
            said.append((number, _lines(path, cache)[i - 1]))
            cells = _cells(_lines(path, cache)[i - 1])
            found = cell_status(cells[-1]) if len(cells) >= 2 else None
            if found:
                status = _stronger(status, found)
            if found == "active" and CELL_AMENDED.search(cells[-1]):
                amended.add(number)   # "stands as amended by R262", "stands ... superseded by R250"
            if home is None:
                said_cell = cells[1] if len(cells) > 1 else ""
                if said_cell.strip("-– ") == "":   # R229's row has no decision; its status cell says why
                    said_cell = cells[-1]
                line = _first_sentence(said_cell)
                home = "%s ledger %s" % (path, number)
        out.append({"number": number, "date": date, "line": line, "status": status, "home": home})
    # The active voice, said by the later ruling: "it overturns R92" and "retires S12-R10" supersede;
    # "amends", "narrows" and "corrects" leave the earlier ruling standing, flagged.
    replaced = {m.group(1) for number, text in said for m in TEXT_REPLACES.finditer(text) if m.group(1) != number}
    amended |= {m.group(1) for number, text in said for m in TEXT_AMENDS.finditer(text) if m.group(1) != number}
    for r in out:
        if r["number"] in replaced:
            r["status"] = _stronger(r["status"], "superseded")
        if r["status"] == "active" and r["number"] in amended:
            r["line"] += AMENDED
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
            path, anchor = r["home"].split(" ", 1)
            out.append("| %s | %s | %s | %s | `%s` %s |" % (
                r["number"], r["date"] or "--", r["status"], _esc(r["line"]) or "--", path, anchor))
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
